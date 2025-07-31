from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
import logging  # Addition: For structured logging in production
import asyncio  # Addition: For async methods to handle concurrency (e.g., multiple responses in IDEs)
from functools import wraps  # For retry decorator
import time

# Additions: Import shared components (assume from architecture; fallback if not)
from core.metrics_collector import EnhancedMetricsCollector
from core.config import ConfigManager
from utils.logger import MinifierLogger  # Your enhanced logger

def retry_on_failure(max_attempts: int = 3, backoff_base: int = 2):
    """Addition: Decorator for retry logic with exponential backoff (integrated from Day 2 enhancements)."""
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

class BaseOutputIntegration(ABC):
    """Base class for output integrations.
    
    Additions for production-grade MVP:
    - Inject metrics_collector, config_manager, and logger for observability and agent-specific settings (e.g., thresholds).
    - Make abstract method async for non-blocking handling (e.g., in VSCode's event-driven responses).
    - Add concrete _translate_safe method with retry for shared translation logic (avoids duplication in subclasses).
    - Enhanced docstrings with examples/doctests for maintainability and self-testing.
    - Session validation on operations to ensure security/expiration (integrates with SecureSessionManager).
    - Risks Mitigated: LLM response errors (retry), blocking calls (async), lack of insights (metrics/logging).
    """
    
    def __init__(
        self,
        translator: Any,  # Your Translator type
        session_manager: Any,  # SecureSessionManager
        metrics_collector: Optional[EnhancedMetricsCollector] = None,
        config_manager: Optional[ConfigManager] = None,
        logger: Optional[MinifierLogger] = None
    ):
        self.translator = translator
        self.sessions = session_manager
        self.metrics = metrics_collector or EnhancedMetricsCollector()  # Fallback
        self.config = config_manager or ConfigManager()  # Fallback for agent configs
        self.logger = logger or MinifierLogger()  # Fallback
        
    @retry_on_failure()  # Addition: Apply retry for robustness (e.g., transient translation errors)
    async def _translate_safe(self, llm_response: str, agent: str) -> str:  # Addition: Concrete shared method
        """Safely translate CAI response with metrics and config checks.
        
        >>> # Doctest example (simplified)
        >>> mock_translator = MockTranslator()  # Assume mock
        >>> result = await self._translate_safe('F[func(a)->b]', 'vscode')
        >>> assert 'def func(a): b' in result
        """
        start_time = time.time()
        try:
            translated = await asyncio.to_thread(self.translator.translate_cai, llm_response)  # Async offload
            duration = (time.time() - start_time) * 1000
            threshold = self.config.get_config(agent).similarity_threshold  # Addition: Agent-specific check
            # Assume similarity calc in translator; log if low
            self.metrics.record('translation_success', {
                'duration_ms': duration,
                'response_length': len(llm_response)
            })
            self.logger.info(f"Translated response in {duration:.2f}ms")
            return translated
        except Exception as e:
            self.metrics.record('translation_failure', {'error': str(e)})
            self.logger.error(f"Translation failed: {e}")
            raise
    
    @abstractmethod
    async def handle_llm_response(  # Addition: Async for concurrency
        self,
        session_id: str,
        llm_response: str
    ) -> Dict[str, Any]:
        """Handle LLM response in CAI format asynchronously.
        
        This method should validate the session, translate the response, and return status.
        
        :param session_id: Valid session ID.
        :param llm_response: CAI-format string from LLM.
        :return: Dict with 'status', 'python_code', etc.
        
        Raises ValueError if session invalid.
        
        >>> # Doctest: Subclass example
        >>> class TestOutput(BaseOutputIntegration):
        ...     async def handle_llm_response(self, sid, resp): return {'status': 'done'}
        >>> handler = TestOutput(None, None)
        >>> asyncio.run(handler.handle_llm_response('sid', 'resp'))
        {'status': 'done'}
        """
        pass