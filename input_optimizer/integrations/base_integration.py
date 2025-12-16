from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, Any, Optional
import logging  # Addition: For structured logging
import asyncio  # Addition: For async support in performance-critical methods
from functools import wraps  # For decorators if needed (e.g., retry)
import time

# Additions: Import shared components from architecture (assume they exist)
from core.session_manager import SecureSessionManager
from core.metrics_collector import EnhancedMetricsCollector
from core.config import ConfigManager
from utils.logger import MinifierLogger  # Your enhanced logger

def retry_on_failure(max_attempts: int = 3, backoff_base: int = 2):
    """Addition: Decorator for retry logic with exponential backoff (from Day 2 enhancements)."""
    def decorator(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            for attempt in range(max_attempts):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    if attempt == max_attempts - 1:
                        raise
                    wait_time = backoff_base ** attempt
                    logging.warning(f"Attempt {attempt + 1} failed: {e}. Retrying in {wait_time}s...")
                    await asyncio.sleep(wait_time)
        return async_wrapper
    return decorator

class BaseInputIntegration(ABC):
    """Base class for all input integrations.
    
    Additions:
    - Inject metrics_collector, config_manager, and logger for observability and agent-specific configs.
    - Make methods async for concurrency (e.g., handling multiple file opens in VSCode).
    - Add concrete _compress_safe method with retry for shared compression logic.
    - Enhanced docstrings with examples/doctests for better maintainability.
    - Type hints for all params/returns.
    """
    
    def __init__(
        self,
        session_manager: SecureSessionManager,
        compressor: Any,  # Your WaterfallCompressor type
        metrics_collector: Optional[EnhancedMetricsCollector] = None,
        config_manager: Optional[ConfigManager] = None,
        logger: Optional[MinifierLogger] = None
    ):
        self.sessions = session_manager
        self.compressor = compressor
        self.metrics = metrics_collector or EnhancedMetricsCollector()  # Fallback to default
        self.config = config_manager or ConfigManager()  # Fallback
        self.logger = logger or MinifierLogger()  # Fallback
        
    @retry_on_failure()  # Addition: Apply retry for robustness
    async def _compress_safe(self, file_path: Path) -> Dict[str, Any]:  # Addition: Concrete shared method
        """Safely compress file with metrics logging.
        
        >>> # Doctest example (simplified)
        >>> mock_compressor = MockCompress()  # Assume mock
        >>> result = await self._compress_safe(Path('test.py'))
        >>> assert 'content' in result
        """
        start_time = time.time()
        try:
            result = await asyncio.to_thread(self.compressor.compress_file, file_path)  # Async offload
            duration = (time.time() - start_time) * 1000
            self.metrics.record('compression_success', {
                'file': str(file_path),
                'duration_ms': duration,
                'ratio': result.compression_ratio
            })
            self.logger.info(f"Compressed {file_path} in {duration:.2f}ms")
            return result.__dict__  # Or as dict for serialization
        except Exception as e:
            self.metrics.record('compression_failure', {'error': str(e)})
            self.logger.error(f"Compression failed for {file_path}: {e}")
            raise

    @abstractmethod
    async def on_file_open(self, file_path: Path) -> Dict[str, Any]:  # Addition: Async
        """Handle file open event asynchronously.
        
        This method should compress the file, create a session, and return status.
        
        :param file_path: Path to the opened file.
        :return: Dict with 'status', 'session_id', etc.
        
        >>> # Doctest: Subclass example
        >>> class TestInput(BaseInputIntegration):
        ...     async def on_file_open(self, file_path): return {'status': 'ready'}
        >>> handler = TestInput(None, None)
        >>> asyncio.run(handler.on_file_open(Path('test.py')))
        {'status': 'ready'}
        """
        pass
        
    @abstractmethod
    async def on_file_change(self, file_path: Path) -> Dict[str, Any]:  # Addition: Async
        """Handle file change event asynchronously.
        
        This method should re-compress if needed and update the session.
        
        :param file_path: Path to the changed file.
        :return: Dict with update status.
        """
        pass
        
    @abstractmethod
    async def get_compressed_context(self, session_id: str) -> str:  # Addition: Async
        """Get compressed content for LLM asynchronously.
        
        This method should validate the session and return CAI content.
        
        :param session_id: Valid session ID.
        :return: Compressed CAI string.
        
        Raises ValueError if session invalid/expired.
        """
        pass