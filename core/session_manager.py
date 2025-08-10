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
import os
from datetime import datetime

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
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert session to dictionary for JSON serialization."""
        return {
            'id': self.id,
            'file_path': str(self.file_path),
            'agent': self.agent,
            'compressed_content': self.compressed_content,
            'original_content': self.original_content,
            'created_at': self.created_at,
            'last_accessed': self.last_accessed,
            'metadata': self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Session':
        """Create session from dictionary (JSON deserialization)."""
        return cls(
            id=data['id'],
            file_path=Path(data['file_path']),
            agent=data['agent'],
            compressed_content=data['compressed_content'],
            original_content=data['original_content'],
            created_at=data['created_at'],
            last_accessed=data['last_accessed'],
            metadata=data.get('metadata', {})
        )

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
        
        # Initialize sessions directory
        self.sessions_dir = Path.home() / ".optimize_ai" / "sessions"
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        
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
            
        # Setup logger first
        if logger is None:
            self.logger = MinifierLogger()
        else:
            self.logger = logger
        
        # Auto-recover existing sessions on startup (after logger is ready)
        try:
            self._recover_sessions_on_startup()
        except Exception as e:
            # Don't fail initialization if recovery fails
            if hasattr(self, 'logger'):
                self.logger.warning(f"Failed to recover sessions on startup: {e}")
        
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
    
    def _recover_sessions_on_startup(self):
        """Recover all valid sessions from disk on startup."""
        if not hasattr(self, 'sessions_dir') or not self.sessions_dir.exists():
            return
            
        try:
            session_files = list(self.sessions_dir.glob("*.json"))
            recovered_count = 0
            
            for session_file in session_files:
                session_id = session_file.stem
                
                try:
                    # Load session data directly without validation (since secret_key might not be set yet)
                    with open(session_file, 'r', encoding='utf-8') as f:
                        session_data = json.load(f)
                    
                    # Validate required fields
                    required_fields = ['id', 'file_path', 'agent', 'compressed_content', 
                                     'original_content', 'created_at', 'last_accessed']
                    
                    if not all(field in session_data for field in required_fields):
                        if hasattr(self, 'logger'):
                            self.logger.error(f"Invalid session data in {session_file}: missing required fields")
                        session_file.unlink()
                        continue
                    
                    # Validate session ID matches filename
                    if session_data['id'] != session_id:
                        if hasattr(self, 'logger'):
                            self.logger.error(f"Session ID mismatch in {session_file}: expected {session_id}, got {session_data['id']}")
                        session_file.unlink()
                        continue
                    
                    # Create session object
                    session = Session.from_dict(session_data)
                    
                    # Check if session is not expired
                    timeout = 3600  # Use default timeout during startup
                    if time.time() - session.last_accessed <= timeout:
                        with self._lock:
                            self.sessions[session_id] = session
                        recovered_count += 1
                        if hasattr(self, 'logger'):
                            self.logger.debug(f"Recovered session {session_id} on startup")
                    else:
                        # Clean up expired session file
                        session_file.unlink()
                        if hasattr(self, 'logger'):
                            self.logger.debug(f"Cleaned up expired session file {session_file}")
                        
                except json.JSONDecodeError as e:
                    if hasattr(self, 'logger'):
                        self.logger.error(f"Invalid JSON in session file {session_file}: {e}")
                    session_file.unlink()
                except Exception as e:
                    if hasattr(self, 'logger'):
                        self.logger.warning(f"Failed to recover session {session_id}: {e}")
                    # Consider removing corrupted session file
                    try:
                        session_file.unlink()
                        if hasattr(self, 'logger'):
                            self.logger.debug(f"Removed corrupted session file {session_file}")
                    except:
                        pass
            
            if recovered_count > 0:
                if hasattr(self, 'logger'):
                    self.logger.info(f"Recovered {recovered_count} sessions on startup")
                if hasattr(self, 'metrics'):
                    self.metrics.record('session_startup_recovery', {'count': recovered_count})
                
        except Exception as e:
            if hasattr(self, 'logger'):
                self.logger.error(f"Failed to recover sessions on startup: {e}")
            if hasattr(self, 'metrics'):
                self.metrics.record('session_startup_recovery_error', {'error': str(e)})
    
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
            
            session = Session(
                id=session_id,
                file_path=file_path,
                agent=agent,
                compressed_content=compressed_content,
                original_content=original_content,
                created_at=time.time(),
                last_accessed=time.time(),
                metadata=metadata or {}
            )
            
            self.sessions[session_id] = session
            
            # Addition: Log and record metric on create (observability)
            self.logger.info(f"Created session {session_id} for agent {agent}")
            self.metrics.record('session_create', {'agent': agent, 'file': str(file_path)})
            
            # Auto-save to disk (pass session object to avoid deadlock)
            try:
                self.save_session_to_disk(session_id, session)
            except Exception as e:
                self.logger.warning(f"Failed to auto-save session {session_id} to disk: {e}")
                # Don't fail session creation if disk save fails
            
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
            
            # Session not in memory, try auto-recovery
            self.logger.debug(f"Session {session_id} not in memory, attempting recovery")
        
        # Release lock before recovery attempt to avoid deadlock
        recovered_session = self.auto_recover_session(session_id)
        if recovered_session:
            # Check if session is still valid after recovery
            timeout = self.config.get_config(recovered_session.agent).session_timeout or 3600
            if time.time() - recovered_session.last_accessed > timeout:
                self.logger.info(f"Recovered session {session_id} is expired")
                return None
            
            self.logger.debug(f"Successfully recovered and accessed session {session_id}")
            self.metrics.record('session_access', {'id': session_id})
            return recovered_session
        
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
                # Handle metadata updates separately
                if 'metadata' in updates:
                    session.metadata.update(updates['metadata'])
                
                # Update specific fields if provided
                if 'compressed_content' in updates:
                    session.compressed_content = updates['compressed_content']
                
                session.last_accessed = time.time()
                
                self.logger.debug(f"Updated session {session_id} with {len(updates)} fields")
                self.metrics.record('session_update', {'id': session_id, 'fields': len(updates)})
        
        # Auto-save updated session to disk (pass session object to avoid deadlock)
        try:
            self.save_session_to_disk(session_id, session)
        except Exception as e:
            self.logger.warning(f"Failed to auto-save updated session {session_id} to disk: {e}")
            # Don't fail update if disk save fails
                
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
                # Also remove session file from disk
                session_file = self.sessions_dir / f"{sid}.json"
                try:
                    if session_file.exists():
                        session_file.unlink()
                        self.logger.debug(f"Deleted expired session file for {sid}")
                except Exception as e:
                    self.logger.warning(f"Failed to delete session file for {sid}: {e}")
                    
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
            
            # Also remove from disk
            session_file = self.sessions_dir / f"{session_id}.json"
            try:
                if session_file.exists():
                    session_file.unlink()
                    self.logger.debug(f"Deleted session file for {session_id}")
            except Exception as e:
                self.logger.warning(f"Failed to delete session file for {session_id}: {e}")
            
            self.logger.info(f"Deleted session {session_id}")
            self.metrics.record('session_delete', {'id': session_id})
            return True
        return False

    def save_session_to_disk(self, session_id: str, session: Session = None) -> None:
        """Save a session to disk with error handling."""
        if session is None:
            with self._lock:
                session = self.sessions.get(session_id)
        
        if not session:
            self.logger.warning(f"Cannot save non-existent session: {session_id}")
            return
        
        session_file = self.sessions_dir / f"{session_id}.json"
        temp_file = session_file.with_suffix('.tmp')
        
        try:
            # Create a serializable version of the session
            session_data = session.to_dict()
            session_data['saved_at'] = time.time()
            
            # Write to temporary file first, then rename for atomicity
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(session_data, f, indent=2, ensure_ascii=False)
            
            # Atomic rename
            temp_file.rename(session_file)
                
            self.logger.info(f"Saved session {session_id} to disk")
            self.metrics.record('session_save_to_disk', {'id': session_id})
            
        except Exception as e:
            self.logger.error(f"Failed to save session {session_id} to disk: {e}")
            self.metrics.record('session_save_error', {'id': session_id, 'error': str(e)})
            # Clean up temp file if it exists
            if temp_file.exists():
                try:
                    temp_file.unlink()
                except:
                    pass
            raise

    def load_session_from_disk(self, session_id: str) -> Optional[Session]:
        """Load a session from disk with error handling."""
        session_file = self.sessions_dir / f"{session_id}.json"
        
        if not session_file.exists():
            self.logger.debug(f"Session file not found: {session_file}")
            return None
        
        try:
            with open(session_file, 'r', encoding='utf-8') as f:
                session_data = json.load(f)
            
            # Validate required fields
            required_fields = ['id', 'file_path', 'agent', 'compressed_content', 
                             'original_content', 'created_at', 'last_accessed']
            
            if not all(field in session_data for field in required_fields):
                self.logger.error(f"Invalid session data in {session_file}: missing required fields")
                # Clean up invalid file
                try:
                    session_file.unlink()
                except:
                    pass
                return None
            
            # Validate session ID matches filename
            if session_data['id'] != session_id:
                self.logger.error(f"Session ID mismatch in {session_file}: expected {session_id}, got {session_data['id']}")
                # Clean up invalid file
                try:
                    session_file.unlink()
                except:
                    pass
                return None
            
            # Create session object
            session = Session.from_dict(session_data)
            
            # Validate session ID signature
            if not self.validate_session_id(session_id):
                self.logger.warning(f"Invalid session ID signature for {session_id}")
                return None
            
            self.logger.info(f"Loaded session {session_id} from disk")
            self.metrics.record('session_load_from_disk', {'id': session_id})
            
            return session
            
        except json.JSONDecodeError as e:
            self.logger.error(f"Invalid JSON in session file {session_file}: {e}")
            self.metrics.record('session_load_json_error', {'id': session_id, 'error': str(e)})
            # Clean up corrupted file
            try:
                session_file.unlink()
                self.logger.debug(f"Cleaned up corrupted session file: {session_file}")
            except:
                pass
            return None
        except Exception as e:
            self.logger.error(f"Failed to load session {session_id} from disk: {e}")
            self.metrics.record('session_load_error', {'id': session_id, 'error': str(e)})
            return None

    def auto_recover_session(self, session_id: str, max_retries: int = 3) -> Optional[Session]:
        """Auto-recover a session with exponential backoff."""
        base_delay = 0.1  # Start with 100ms delay
        
        for attempt in range(max_retries):
            try:
                # First, try to get session from memory
                session = self.sessions.get(session_id)
                if session:
                    self.logger.debug(f"Session {session_id} recovered from memory on attempt {attempt + 1}")
                    self.metrics.record('session_recover_memory', {'id': session_id, 'attempt': attempt + 1})
                    return session
                
                # If not in memory, try to load from disk
                session = self.load_session_from_disk(session_id)
                if session:
                    # Add back to memory cache with lock
                    with self._lock:
                        # Update last accessed time
                        session.last_accessed = time.time()
                        self.sessions[session_id] = session
                    
                    self.logger.info(f"Session {session_id} recovered from disk on attempt {attempt + 1}")
                    self.metrics.record('session_recover_disk', {'id': session_id, 'attempt': attempt + 1})
                    return session
                
                # If neither worked, log and continue to next attempt
                self.logger.warning(f"Session {session_id} recovery attempt {attempt + 1} failed")
                
            except Exception as e:
                self.logger.error(f"Session {session_id} recovery attempt {attempt + 1} failed with error: {e}")
                self.metrics.record('session_recover_error', {
                    'id': session_id, 
                    'attempt': attempt + 1, 
                    'error': str(e)
                })
            
            # Exponential backoff, but only if we're going to retry
            if attempt < max_retries - 1:
                delay = base_delay * (2 ** attempt)
                self.logger.debug(f"Waiting {delay:.2f}s before retry {attempt + 2}")
                time.sleep(delay)
        
        # All attempts failed
        self.logger.error(f"Failed to recover session {session_id} after {max_retries} attempts")
        self.metrics.record('session_recover_failed', {'id': session_id, 'max_retries': max_retries})
        return None

    # Addition: Optional persistence (dump to JSON for restarts; in-memory for MVP, but hook for V2)
    def persist_sessions(self, file_path: Path = Path(".optimize_ai/sessions.json")):
        """Persist active sessions to file (optional for MVP restarts)."""
        with self._lock:
            data = [sess.__dict__ for sess in self.sessions.values()]  # Serialize (custom if needed)
            file_path.write_text(json.dumps(data))
        self.logger.info("Persisted sessions")
        self.metrics.record('session_persist', {'count': len(self.sessions)})