# core/session_manager.py
import uuid
import time
import hmac
import hashlib
import asyncio
from pathlib import Path
from typing import Dict, Optional, Any
from dataclasses import dataclass, field
import json
import threading
import sys
import functools
import contextvars
import concurrent.futures

# Python version compatibility for asyncio.to_thread
if sys.version_info < (3, 9):
    # Backport for Python < 3.9
    async def _to_thread(func, *args, **kwargs):
        """Backport of asyncio.to_thread for Python < 3.9"""
        loop = asyncio.get_running_loop()
        ctx = contextvars.copy_context()
        func_call = functools.partial(ctx.run, func, *args, **kwargs)
        return await loop.run_in_executor(None, func_call)
    
    # Monkey patch asyncio
    asyncio.to_thread = _to_thread

# Additions: Import shared components for MVP (observability, configurability; assume from architecture)
try:
    from optimize_ai.core.metrics_collector import EnhancedMetricsCollector  # For session metrics (e.g., create count)
except ImportError:
    class EnhancedMetricsCollector:
        def __init__(self, *args, **kwargs): pass
        def record(self, *args, **kwargs): pass

# Use lazy loading for ConfigManager to avoid circular imports
# ConfigManager will be imported only when needed

try:
    from optimize_ai.utils.logger import MinifierLogger  # For structured logging
except ImportError:
    import logging
    class MinifierLogger:
        def __init__(self): 
            self.logger = logging.getLogger(__name__)
        def info(self, msg): self.logger.info(msg)
        def warning(self, msg): self.logger.warning(msg)
        def error(self, msg): self.logger.error(msg)
        def debug(self, msg): self.logger.debug(msg)

@dataclass
class Session:
    id: str
    file_path: Path
    agent: str
    compressed_content: str
    original_content: str
    created_at: float
    last_accessed: float
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def is_expired(self, timeout: int = 3600) -> bool:
        return time.time() - self.last_accessed > timeout

class SecureSessionManager:
    """Thread-safe session management with security and async support."""
    
    def __init__(
        self,
        secret_key: str = None,
        metrics_collector: Optional[EnhancedMetricsCollector] = None,  # Addition: Inject for observability (track creates/accesses)
        config_manager = None,  # Addition: Inject for tunable params (e.g., per-agent timeouts)
        logger = None  # Addition: Inject logger for production tracing
    ):
        self.sessions: Dict[str, Session] = {}
        self.secret_key = secret_key or self._generate_secret()
        self._lock = threading.Lock()
        self._cleanup_task = None
        self.metrics = metrics_collector or EnhancedMetricsCollector()  # Fallback
        
        # Lazy load ConfigManager to avoid circular imports
        if config_manager is None:
            try:
                from optimize_ai.core.config import ConfigManager
                self.config = ConfigManager()
            except ImportError:
                # Fallback config
                class MockConfig:
                    def get(self, key, default=None): return default
                    def get_config(self, agent): 
                        class MockAgentConfig:
                            session_timeout = 3600
                        return MockAgentConfig()
                self.config = MockConfig()
        else:
            self.config = config_manager
            
        # Setup logger
        if logger is None:
            self.logger = MinifierLogger()
        else:
            self.logger = logger
        
        # Addition: Start cleanup task manually when event loop is available
        self._start_cleanup_on_demand()
    
    def _start_cleanup_on_demand(self):
        """Start cleanup task if event loop is running, otherwise defer."""
        try:
            loop = asyncio.get_running_loop()
            if self._cleanup_task is None:
                self._cleanup_task = asyncio.create_task(self.start_cleanup_task())
                self.logger.info("Cleanup task started")
        except RuntimeError:
            # No event loop running, cleanup will be started manually when needed
            self.logger.debug("No event loop available, cleanup task deferred")
            pass
    
    def _generate_secret(self) -> str:
        """Generate secure secret for session validation."""
        return hashlib.sha256(str(uuid.uuid4()).encode()).hexdigest()
        
    def _generate_session_id(self, file_path: Path, agent: str) -> str:
        """Generate HMAC-signed session ID."""
        base_id = f"{file_path.stem}_{agent}_{int(time.time())}"
        signature = hmac.new(
            self.secret_key.encode(),
            base_id.encode(),
            hashlib.sha256
        ).hexdigest()[:8]
        return f"{base_id}_{signature}"
        
    def validate_session_id(self, session_id: str) -> bool:
        """Validate session ID hasn't been tampered with."""
        try:
            parts = session_id.rsplit('_', 1)
            if len(parts) != 2:
                return False
            base_id, signature = parts
            expected_sig = hmac.new(
                self.secret_key.encode(),
                base_id.encode(),
                hashlib.sha256
            ).hexdigest()[:8]
            return hmac.compare_digest(signature, expected_sig)
        except:
            return False
            
    async def create_session_async(
        self,
        file_path: Path,
        agent: str,
        compressed_content: str,
        metadata: Dict = None
    ) -> str:
        """Async session creation for concurrent operations."""
        return await asyncio.to_thread(
            self.create_session,
            file_path, agent, compressed_content, metadata
        )
        
    def create_session(
        self,
        file_path: Path,
        agent: str,
        compressed_content: str,
        metadata: Dict = None
    ) -> str:
        """Create secure session with validation."""
        with self._lock:
            session_id = self._generate_session_id(file_path, agent)
            
            # Handle case where file might not exist yet
            try:
                original_content = file_path.read_text() if file_path.exists() else ""
            except Exception as e:
                self.logger.warning(f"Could not read file {file_path}: {e}")
                original_content = ""
            
            self.sessions[session_id] = Session(
                id=session_id,
                file_path=file_path,
                agent=agent,
                compressed_content=compressed_content,
                original_content=original_content,
                created_at=time.time(),
                last_accessed=time.time(),
                metadata=metadata or {}
            )
            
            # Addition: Log and record metric on create (observability)
            self.logger.info(f"Created session {session_id} for agent {agent}")
            self.metrics.record('session_create', {'agent': agent, 'file': str(file_path)})
            return session_id
            
    def get_session(self, session_id: str) -> Optional[Session]:
        """Get session with validation and access time update."""
        if not self.validate_session_id(session_id):
            # Addition: Log invalid access (security monitoring)
            self.logger.warning(f"Invalid session ID access attempt: {session_id}")
            self.metrics.record('session_invalid_access', {'id': session_id})
            return None
            
        with self._lock:
            session = self.sessions.get(session_id)
            if session:
                # Addition: Use config for agent-specific timeout (configurability)
                timeout = self.config.get_config(session.agent).session_timeout or 3600
                if time.time() - session.last_accessed > timeout:
                    del self.sessions[session_id]
                    self.logger.info(f"Expired session {session_id} on access")
                    self.metrics.record('session_expired_on_access', {'id': session_id})
                    return None
                session.last_accessed = time.time()
                # Addition: Log successful access
                self.logger.debug(f"Accessed session {session_id}")
                self.metrics.record('session_access', {'id': session_id})
                return session
            return None
    
    def update_session(self, session_id: str, updates: Dict[str, Any]) -> bool:
        """Update session metadata and content."""
        session = self.get_session(session_id)
        if not session:
            self.logger.warning(f"Attempt to update non-existent session: {session_id}")
            return False
            
        with self._lock:
            # Update metadata
            if updates:
                session.metadata.update(updates)
                
                # Update specific fields if provided
                if 'compressed_content' in updates:
                    session.compressed_content = updates['compressed_content']
                
                session.last_accessed = time.time()
                
                self.logger.debug(f"Updated session {session_id} with {len(updates)} fields")
                self.metrics.record('session_update', {'id': session_id, 'fields': len(updates)})
                
        return True
            
    def cleanup_expired(self, timeout: int = 3600) -> int:
        """Clean expired sessions, return count removed."""
        with self._lock:
            expired = [
                sid for sid, sess in self.sessions.items()
                if time.time() - sess.last_accessed > timeout
            ]
            for sid in expired:
                del self.sessions[sid]
            # Addition: Log and metric if cleaned
            if expired:
                self.logger.info(f"Cleaned {len(expired)} expired sessions")
                self.metrics.record('session_cleanup', {'removed': len(expired)})
            return len(expired)
            
    async def start_cleanup_task(self, interval: int = 300):
        """Start async cleanup task (runs every 5 min)."""
        while True:
            await asyncio.sleep(interval)
            removed = self.cleanup_expired()
            if removed > 0:
                self.logger.info(f"Cleaned up {removed} expired sessions")
    
    def start_cleanup_when_ready(self, interval: int = 300):
        """Start cleanup task when event loop is available."""
        if self._cleanup_task is None:
            try:
                self._cleanup_task = asyncio.create_task(self.start_cleanup_task(interval))
                self.logger.info("Manual cleanup task started")
            except RuntimeError:
                self.logger.warning("Cannot start cleanup task - no event loop available")

    # Addition: Explicit delete method (for manual invalidation, e.g., on logout/file close)
    def delete_session(self, session_id: str) -> bool:
        """Delete a session explicitly."""
        if self.get_session(session_id):  # Validates implicitly
            with self._lock:
                del self.sessions[session_id]
            self.logger.info(f"Deleted session {session_id}")
            self.metrics.record('session_delete', {'id': session_id})
            return True
        return False

    # Addition: Optional persistence (dump to JSON for restarts; in-memory for MVP, but hook for V2)
    def persist_sessions(self, file_path: Path = Path(".optimize_ai/sessions.json")):
        """Persist active sessions to file (optional for MVP restarts)."""
        with self._lock:
            data = [sess.__dict__ for sess in self.sessions.values()]  # Serialize (custom if needed)
            file_path.write_text(json.dumps(data))
        self.logger.info("Persisted sessions")
        self.metrics.record('session_persist', {'count': len(self.sessions)})