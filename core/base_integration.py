import asyncio
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, Any, Optional
import logging
from functools import wraps
import time
import os  # Addition: For specific error handling (e.g., os errors in file ops)

# Additions: Import shared components (assume from architecture; for configurability/observability)
try:
    from core.config import ConfigManager  # To make retry params tunable
except ImportError:
    class ConfigManager:
        def __init__(self): pass
        def get(self, key, default=None): return default

try:
    from core.metrics_collector import EnhancedMetricsCollector
except ImportError:
    class EnhancedMetricsCollector:
        def __init__(self, *args, **kwargs): pass
        async def record_async(self, *args, **kwargs): pass

from utils.logger import MinifierLogger  # Your enhanced logger for structured output

def retry_on_failure(max_attempts: int = 3, backoff_base: int = 2):
    """Decorator for retry logic with exponential backoff.
    
    Additions:
    - Make params configurable (passed at decorator use, but can pull from config in class).
    - Add docstring with example for maintainability.
    
    >>> # Doctest: Mock failing async func
    >>> async def failing_func(): raise ValueError("Fail")
    >>> decorated = retry_on_failure(2)(failing_func)
    >>> try: await decorated()
    ... except ValueError: pass  # Should retry once before raise
    """
    def decorator(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            for attempt in range(max_attempts):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:  # Keep broad, but log type
                    logging.warning(f"Attempt {attempt + 1} failed ({type(e).__name__}): {e}. Retrying in {backoff_base ** attempt}s...")
                    if attempt == max_attempts - 1:
                        raise
                    await asyncio.sleep(backoff_base ** attempt)
                    
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    logging.warning(f"Attempt {attempt + 1} failed ({type(e).__name__}): {e}. Retrying in {backoff_base ** attempt}s...")
                    if attempt == max_attempts - 1:
                        raise
                    time.sleep(backoff_base ** attempt)
                    
        return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper
    return decorator

class BaseIntegrationWithErrorHandling(ABC):
    """Enhanced base class with error handling and metrics.
    
    Additions:
    - Inject ConfigManager and MinifierLogger for tunable retries and structured logging.
    - Make retry params pull from config (agent-specific, e.g., more attempts for unreliable agents).
    - Refine exception handling in compress_file_safe: Specific catches (e.g., FileNotFoundError) with custom messages; re-raise with context.
    - Enhanced docstrings with doctests for self-testing/maintainability.
    - Fallbacks if metrics/config/logger None (defaults prevent crashes).
    - Risks Mitigated: Hardcoded params (config), vague errors (specific catches/logs), no logging (structured).
    """
    
    def __init__(
        self,
        session_manager: Any,
        compressor: Any,
        metrics_collector: Optional[EnhancedMetricsCollector] = None,
        config_manager: Optional[ConfigManager] = None,
        logger: Optional[MinifierLogger] = None
    ):
        self.sessions = session_manager
        self.compressor = compressor
        self.metrics = metrics_collector or EnhancedMetricsCollector()  # Addition: Fallback default
        self.config = config_manager or ConfigManager()  # Addition: Fallback for configs
        self.logger = logger or MinifierLogger()  # Addition: Fallback structured logger
        # Addition: Set class-level retry params from config (configurable)
        self.retry_attempts = self.config.get('retry_attempts', 3)
        self.retry_backoff = self.config.get('backoff_base', 2)
    
    def _get_retry_decorator(self):
        """Addition: Dynamic decorator factory using config params."""
        return retry_on_failure(max_attempts=self.retry_attempts, backoff_base=self.retry_backoff)
    
    @property
    def compress_file_safe(self):  # Addition: Make it a property to apply dynamic decorator
        """Compress with retry and metrics (dynamic decorator for config changes)."""
        @_get_retry_decorator(self)
        async def wrapped_compress(file_path: Path) -> Dict[str, Any]:
            start_time = time.time()
            try:
                result = await asyncio.to_thread(
                    self.compressor.compress_file, file_path
                )
                duration = (time.time() - start_time) * 1000
                # Addition: Enhanced metrics (add file type, e.g., extension)
                self.metrics.record('compression_success', {
                    'file': str(file_path),
                    'size_before': file_path.stat().st_size,
                    'tokens_after': result.compressed_tokens,
                    'ratio': result.compression_ratio,
                    'duration_ms': duration,
                    'file_ext': file_path.suffix  # Addition: For analysis (e.g., .py vs others)
                })
                # Addition: Structured log
                self.logger.info(f"Compressed {file_path} successfully in {duration:.2f}ms")
                return result
            except FileNotFoundError as e:  # Addition: Specific catch for common I/O
                self.logger.error(f"File not found: {file_path}")
                self.metrics.record('compression_failure', {'error': 'FileNotFound', 'file': str(file_path)})
                raise ValueError(f"File not found: {file_path}") from e
            except PermissionError as e:  # Addition: Handle read permissions
                self.logger.error(f"Permission denied for {file_path}")
                self.metrics.record('compression_failure', {'error': 'PermissionError', 'file': str(file_path)})
                raise PermissionError(f"Cannot access {file_path}") from e
            except Exception as e:
                self.metrics.record('compression_failure', {
                    'file': str(file_path),
                    'error': str(e),
                    'duration_ms': (time.time() - start_time) * 1000
                })
                self.logger.exception(f"Unexpected compression error: {e}")
                raise
        
        return wrapped_compress  # Return the decorated async function

    # Abstract methods remain unchanged, but ensure subclasses use the property