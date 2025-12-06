import asyncio  # Addition: For async methods (non-blocking in IDE events)
from pathlib import Path
from typing import Dict, Any
import logging

from .base_integration import BaseInputIntegration  # Assume enhanced base with _compress_safe, retry

class VSCodeInputIntegration(BaseInputIntegration):
    """VSCode-specific input handling.
    
    Additions for production-grade MVP:
    - Implement all abstract methods (on_file_change, get_compressed_context) to satisfy ABC.
    - Make methods async for concurrency (e.g., handling multiple file opens in VSCode tabs without blocking).
    - Use _compress_safe from base for retry/error handling (avoids crashes on locked files).
    - Add logging and metrics recording on key actions (observability for MVP debugging/benchmarks).
    - Integrate config for agent-specific settings (e.g., max_context_tokens for VSCode).
    - Validation: Check session existence before operations; handle non-existent paths gracefully.
    - Risks Mitigated: I/O errors (retry), performance bottlenecks (async), incomplete subclass (all methods).
    """
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.logger = logging.getLogger(__name__)  # Addition: Dedicated logger for this integration
        self.agent_config = self.config.get_config('vscode')  # Addition: Pull VSCode-specific config (e.g., thresholds)
    
    async def on_file_open(self, file_path: Path) -> Dict[str, Any]:  # Addition: Async for non-blocking
        """Handle file open event asynchronously."""
        if not file_path.exists():  # Addition: Validate file existence (edge case handling)
            self.logger.error(f"File not found: {file_path}")
            self.metrics.record('file_open_failure', {'path': str(file_path)})
            return {"status": "error", "message": "File not found"}
        
        try:
            result = await self._compress_safe(file_path)  # Addition: Use safe compress with retry/metrics
            session_id = await self.sessions.create_session_async(  # Addition: Async session create
                file_path=file_path,
                agent="vscode",
                compressed_content=result['content'],  # From dict (enhanced base)
                metadata={
                    "compression_tier": result['tier_used'].value,
                    "original_tokens": result['original_tokens'],
                    "max_context": self.agent_config.max_context_tokens  # Addition: Agent-specific metadata
                }
            )
            self.logger.info(f"Opened and compressed {file_path} (session: {session_id})")
            return {
                "status": "ready",
                "session_id": session_id,
                "compression_ratio": result['compression_ratio']
            }
        except Exception as e:  # Addition: Broad catch with logging (fallback for unexpected)
            self.logger.exception(f"File open failed: {e}")
            self.metrics.record('file_open_exception', {'error': str(e)})
            return {"status": "error", "message": str(e)}
    
    async def on_file_change(self, file_path: Path) -> Dict[str, Any]:  # Addition: Implement abstract (re-compress on edit)
        """Handle file change event asynchronously.
        
        This re-compresses the file and updates the existing session if found.
        """
        session = self.sessions.get_session_for_file(file_path)  # Assume helper in SessionManager (add if needed)
        if not session:
            self.logger.warning(f"No active session for changed file: {file_path}")
            return await self.on_file_open(file_path)  # Fallback: Treat as new open
        
        try:
            result = await self._compress_safe(file_path)
            self.sessions.update_session(session.id, result['content'])  # Assume update method in SessionManager
            self.logger.info(f"Updated compression for changed {file_path} (session: {session.id})")
            return {
                "status": "updated",
                "session_id": session.id,
                "compression_ratio": result['compression_ratio']
            }
        except Exception as e:
            self.logger.exception(f"File change failed: {e}")
            return {"status": "error", "message": str(e)}
    
    async def get_compressed_context(self, session_id: str) -> str:  # Addition: Implement abstract (fetch CAI)
        """Get compressed content for LLM asynchronously."""
        session = self.sessions.get_session(session_id)
        if not session:
            self.logger.error(f"Invalid/expired session: {session_id}")
            self.metrics.record('invalid_session_access', {'id': session_id})
            raise ValueError("Invalid or expired session")
        
        self.logger.debug(f"Retrieved context for {session_id}")
        self.metrics.record('context_access', {'session_id': session_id, 'agent': session.agent})
        return session.compressed_content