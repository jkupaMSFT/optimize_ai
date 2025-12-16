# ===== input_optimizer/integrations/cursor_input.py =====
"""
Cursor IDE integration for input compression.
Handles Cursor-specific events and protocols.
"""

import asyncio
from pathlib import Path
from typing import Dict, Any, Optional, List
import json
import logging
import os
import time

from .base_integration import BaseInputIntegration
from ...core.session_manager import SessionManager
from ...core.metrics_collector import MetricsCollector
from ..engine.waterfall_compressor import WaterfallCompressor


class CursorInputIntegration(BaseInputIntegration):
    """
    Cursor-specific input handling with support for Sonnet 3.7 features.
    Handles autonomous workflows and multi-file editing.
    """
    
    def __init__(self, session_manager: SessionManager, 
                 waterfall_compressor: WaterfallCompressor,
                 metrics_collector: MetricsCollector):
        super().__init__(session_manager, waterfall_compressor, metrics_collector)
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging.INFO)
        self.agent_name = "cursor"
        self.config = {
            "max_context_tokens": int(os.getenv("CURSOR_MAX_CONTEXT_TOKENS", 120000)),
            "similarity_threshold": float(os.getenv("CURSOR_SIMILARITY_THRESHOLD", 0.7)),
            "features": ["autonomous_workflow", "multi_file_edit", "composer"],
            "compression_preference": "aggressive",  # Cursor can handle more compression
            "multi_file_batch_size": int(os.getenv("CURSOR_MULTI_FILE_BATCH_SIZE", 10))
        }
        self.active_workflows = {}
        
    async def on_file_open(self, file_path: Path) -> Dict[str, Any]:
        """
        Handle file open event in Cursor.
        
        Args:
            file_path: Path to opened Python file
            
        Returns:
            Response with session info and compressed content
        """
        try:
            if not file_path.exists() or not file_path.is_file():
                return {
                    "status": "error",
                    "reason": "invalid_file_path",
                    "file_path": str(file_path),
                    "timestamp": time.time()
                }
            
            # Check if file is Python
            if file_path.suffix != '.py':
                return {
                    "status": "ignored",
                    "reason": "not_python_file",
                    "file_type": file_path.suffix,
                    "timestamp": time.time()
                }
                
            # Check file size for appropriate compression
            file_size = file_path.stat().st_size
            if file_size > 1_000_000:  # 1MB limit
                return {
                    "status": "error",
                    "reason": "file_too_large",
                    "size_bytes": file_size,
                    "timestamp": time.time()
                }
                
            if file_size == 0:
                compression_result = type('CompressionResult', (), {
                    'content': '',
                    'tier_used': type('Tier', (), {'value': 'none'}),
                    'original_tokens': 0,
                    'compressed_tokens': 0,
                    'compression_ratio': 0.0
                })()
            else:
                # Compress file
                compression_result = await self._compress_file_safe(file_path)
            
            # Create session
            session_id = await self.session_manager.create_session(
                file_path=file_path,
                agent=self.agent_name,
                compressed_content=compression_result.content,
                metadata={
                    "compression_tier": compression_result.tier_used.value,
                    "original_tokens": compression_result.original_tokens,
                    "compressed_tokens": compression_result.compressed_tokens,
                    "cursor_features": self.config["features"]
                }
            )
            
            # Record metrics
            await self.metrics_collector.record_async("cursor_file_open", {
                "file": str(file_path),
                "compression_ratio": compression_result.compression_ratio,
                "tier": compression_result.tier_used.value,
                "tokens_saved": compression_result.original_tokens - compression_result.compressed_tokens
            })
            
            self.logger.info(f"Successfully opened file {file_path} with session {session_id}")
            
            return {
                "status": "success",
                "session_id": session_id,
                "compressed_content": compression_result.content,
                "compression_stats": {
                    "original_tokens": compression_result.original_tokens,
                    "compressed_tokens": compression_result.compressed_tokens,
                    "reduction_percentage": compression_result.compression_ratio,
                    "tier_used": compression_result.tier_used.value
                },
                "cursor_config": {
                    "max_context": self.config["max_context_tokens"],
                    "features_enabled": self.config["features"]
                },
                "timestamp": time.time()
            }
            
        except FileNotFoundError as e:
            self.logger.error(json.dumps({"event": "file_not_found", "details": str(e), "file": str(file_path)}))
            return {"status": "error", "reason": "file_not_found", "error": str(e), "timestamp": time.time()}
        except PermissionError as e:
            self.logger.error(json.dumps({"event": "permission_denied", "details": str(e), "file": str(file_path)}))
            return {"status": "error", "reason": "permission_denied", "error": str(e), "timestamp": time.time()}
        except Exception as e:
            self.logger.error(json.dumps({"event": "error_opening_file", "details": str(e), "file": str(file_path)}))
            await self.metrics_collector.record_async("cursor_file_open_error", {
                "file": str(file_path),
                "error": str(e)
            })
            
            return {
                "status": "error",
                "error": str(e),
                "file_path": str(file_path),
                "timestamp": time.time()
            }
            
    async def on_file_change(self, file_path: Path) -> Dict[str, Any]:
        """
        Handle file change event in Cursor.
        Re-compress and update session.
        """
        try:
            if not file_path.exists() or not file_path.is_file():
                return {
                    "status": "error",
                    "reason": "invalid_file_path",
                    "file_path": str(file_path),
                    "timestamp": time.time()
                }
            
            # Find existing session
            session_id = await self._find_session_for_file(file_path)
            
            if not session_id:
                # Create new session if none exists
                return await self.on_file_open(file_path)
                
            # Re-compress file
            file_size = file_path.stat().st_size
            if file_size == 0:
                compression_result = type('CompressionResult', (), {
                    'content': '',
                    'tier_used': type('Tier', (), {'value': 'none'}),
                    'original_tokens': 0,
                    'compressed_tokens': 0,
                    'compression_ratio': 0.0
                })()
            else:
                compression_result = await self._compress_file_safe(file_path)
            
            # Update session
            session = self.session_manager.get_session(session_id)
            if session:
                session.compressed_content = compression_result.content
                session.metadata.update({
                    "last_change_compression": compression_result.tier_used.value,
                    "change_count": session.metadata.get("change_count", 0) + 1
                })
                
            await self.metrics_collector.record_async("cursor_file_change", {
                "file": str(file_path),
                "session_id": session_id,
                "new_compression_ratio": compression_result.compression_ratio
            })
            
            self.logger.info(f"Successfully handled file change for {file_path} in session {session_id}")
            
            return {
                "status": "updated",
                "session_id": session_id,
                "compressed_content": compression_result.content,
                "change_stats": {
                    "new_tokens": compression_result.compressed_tokens,
                    "change_count": session.metadata.get("change_count", 1)
                },
                "timestamp": time.time()
            }
            
        except FileNotFoundError as e:
            self.logger.error(json.dumps({"event": "file_not_found", "details": str(e), "file": str(file_path)}))
            return {"status": "error", "reason": "file_not_found", "error": str(e), "timestamp": time.time()}
        except PermissionError as e:
            self.logger.error(json.dumps({"event": "permission_denied", "details": str(e), "file": str(file_path)}))
            return {"status": "error", "reason": "permission_denied", "error": str(e), "timestamp": time.time()}
        except Exception as e:
            self.logger.error(json.dumps({"event": "error_handling_file_change", "details": str(e), "file": str(file_path)}))
            return {
                "status": "error",
                "error": str(e),
                "file_path": str(file_path),
                "timestamp": time.time()
            }
            
    async def on_autonomous_workflow_start(self, workflow_id: str, 
                                         files: List[Path], 
                                         instructions: str) -> Dict[str, Any]:
        """
        Handle Cursor's autonomous workflow start.
        Compress multiple files for workflow context.
        """
        try:
            if not workflow_id or not files or not instructions.strip():
                return {
                    "status": "error",
                    "reason": "invalid_workflow_params",
                    "workflow_id": workflow_id,
                    "timestamp": time.time()
                }
            if workflow_id in self.active_workflows:
                return {
                    "status": "error",
                    "reason": "workflow_id_already_exists",
                    "workflow_id": workflow_id,
                    "timestamp": time.time()
                }
            
            truncated = False
            if len(files) > self.config["multi_file_batch_size"]:
                self.logger.warning(f"Workflow {workflow_id} has {len(files)} files; processing only first {self.config['multi_file_batch_size']}")
                files = files[:self.config["multi_file_batch_size"]]
                truncated = True
            
            compressed_files = {}
            total_original_tokens = 0
            total_compressed_tokens = 0
            
            # Batch compress files
            compression_tasks = []
            for file_path in files:
                if file_path.suffix == '.py':
                    compression_tasks.append(self._compress_file_safe(file_path))
                    
            compression_results = await asyncio.gather(*compression_tasks, return_exceptions=True)
            
            # Process results
            for i, result in enumerate(compression_results):
                if isinstance(result, Exception):
                    self.logger.warning(f"Failed to compress {files[i]}: {result}")
                    await self.metrics_collector.record_async("compression_failure", {
                        "file": str(files[i]),
                        "error": str(result)
                    })
                    continue
                    
                file_path = files[i]
                compressed_files[str(file_path)] = {
                    "compressed_content": result.content,
                    "original_tokens": result.original_tokens,
                    "compressed_tokens": result.compressed_tokens,
                    "tier": result.tier_used.value
                }
                
                total_original_tokens += result.original_tokens
                total_compressed_tokens += result.compressed_tokens
                
            # Create workflow session
            workflow_session = {
                "workflow_id": workflow_id,
                "files": compressed_files,
                "instructions": instructions,
                "total_original_tokens": total_original_tokens,
                "total_compressed_tokens": total_compressed_tokens,
                "start_time": asyncio.get_event_loop().time()
            }
            
            self.active_workflows[workflow_id] = workflow_session
            
            # Record metrics
            await self.metrics_collector.record_async("cursor_autonomous_workflow_start", {
                "workflow_id": workflow_id,
                "file_count": len(compressed_files),
                "total_compression_ratio": (1 - total_compressed_tokens/total_original_tokens) * 100 if total_original_tokens > 0 else 0
            })
            
            self.logger.info(f"Successfully started autonomous workflow {workflow_id} with {len(compressed_files)} files")
            
            return {
                "status": "workflow_ready",
                "workflow_id": workflow_id,
                "compressed_files": compressed_files,
                "context_stats": {
                    "total_files": len(compressed_files),
                    "total_original_tokens": total_original_tokens,
                    "total_compressed_tokens": total_compressed_tokens,
                    "fits_in_context": total_compressed_tokens < self.config["max_context_tokens"]
                },
                "truncated_files": truncated,
                "processed_count": len(files),
                "timestamp": time.time()
            }
            
        except Exception as e:
            self.logger.error(json.dumps({"event": "error_starting_workflow", "details": str(e), "workflow_id": workflow_id}))
            return {
                "status": "error",
                "error": str(e),
                "workflow_id": workflow_id,
                "timestamp": time.time()
            }
            
    async def on_composer_request(self, files: List[Path], 
                                 prompt: str,
                                 composer_mode: str = "edit") -> Dict[str, Any]:
        """
        Handle Cursor Composer requests for multi-file editing.
        """
        try:
            if not files or not prompt.strip():
                return {
                    "status": "error",
                    "reason": "invalid_composer_params",
                    "timestamp": time.time()
                }
            
            # Similar to autonomous workflow but for composer
            compressed_context = await self._build_compressed_context(files)
            
            # Add composer-specific formatting
            composer_prompt = self._format_composer_prompt(prompt, compressed_context, composer_mode)
            
            self.logger.info(f"Successfully handled composer request with {len(files)} files in mode {composer_mode}")
            
            return {
                "status": "composer_ready",
                "compressed_prompt": composer_prompt,
                "context_size": len(composer_prompt),
                "mode": composer_mode,
                "file_count": len(files),
                "timestamp": time.time()
            }
            
        except Exception as e:
            self.logger.error(json.dumps({"event": "error_handling_composer", "details": str(e)}))
            return {
                "status": "error",
                "error": str(e),
                "timestamp": time.time()
            }
            
    async def get_compressed_context(self, session_id: str) -> str:
        """Get compressed context for a session."""
        session = self.session_manager.get_session(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")
            
        # Add Cursor-specific context formatting
        context = f"""# Cursor Context (Session: {session_id})
# Agent: Cursor with Sonnet 3.7
# Features: {', '.join(self.config['features'])}
# Compression: {session.metadata.get('compression_tier', 'unknown')}

{session.compressed_content}
"""
        return context
        
    async def _find_session_for_file(self, file_path: Path) -> Optional[str]:
        """Find active session for a file."""
        # Search through active sessions
        expired_sessions = []
        for session_id, session in self.session_manager.sessions.items():
            if session.is_expired():
                expired_sessions.append(session_id)
            elif session.file_path == file_path and session.agent == self.agent_name:
                return session_id
        
        for sid in expired_sessions:
            del self.session_manager.sessions[sid]  # Cleanup expired sessions
        
        return None
        
    async def _build_compressed_context(self, files: List[Path]) -> Dict[str, str]:
        """Build compressed context for multiple files."""
        context = {}
        
        compression_tasks = []
        for file_path in files:
            if file_path.suffix == '.py' and file_path.exists():
                compression_tasks.append(self._compress_file_safe(file_path))
                
        results = await asyncio.gather(*compression_tasks, return_exceptions=True)
        
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                self.logger.warning(f"Failed to compress {files[i]}: {result}")
                await self.metrics_collector.record_async("compression_failure", {
                    "file": str(files[i]),
                    "error": str(result)
                })
                continue
                
            context[str(files[i])] = result.content
                
        return context
        
    def _format_composer_prompt(self, prompt: str, context: Dict[str, str], mode: str) -> str:
        """Format prompt for Cursor Composer."""
        formatted = f"""# Cursor Composer Request
Mode: {mode}
Instructions: {prompt}

# Compressed File Context:
"""
        
        for file_path, compressed_content in context.items():
            formatted += f"\n## {file_path}\n{compressed_content}\n"
            
        return formatted

    async def cleanup_workflows(self):
        """Cleanup completed or expired workflows to prevent memory leaks."""
        to_remove = []
        current_time = asyncio.get_event_loop().time()
        for workflow_id, workflow in self.active_workflows.items():
            # Example expiration: 1 hour, adjust as needed
            if current_time - workflow["start_time"] > 3600:
                to_remove.append(workflow_id)
        
        for wid in to_remove:
            del self.active_workflows[wid]
            self.logger.info(f"Cleaned up expired workflow {wid}")