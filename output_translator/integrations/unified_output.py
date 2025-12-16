"""
Unified handler for output integrations.
Routes responses to appropriate agent handlers.
"""
from typing import Dict, Any, Optional
import asyncio
import time
import logging

from .base_output import BaseOutputIntegration
from .vscode_output import VSCodeOutputIntegration
from .cursor_output import CursorOutputIntegration
from .claude_code_output import ClaudeCodeOutputIntegration
from ...core.session_manager import SecureSessionManager
from ...core.metrics_collector import EnhancedMetricsCollector
from ...core.config import ConfigManager
from ...utils.logger import MinifierLogger
from ..core.translator import CAIToPythonTranslator, TranslationResult

logger = logging.getLogger(__name__)

class UnifiedOutputHandler:
    """
    Unified handler for output integrations.
    Routes LLM responses to agent-specific handlers and records unified metrics.
    """
    def __init__(
        self,
        translator: CAIToPythonTranslator,
        session_manager: SecureSessionManager,
        metrics_collector: Optional[EnhancedMetricsCollector] = None,
        config_manager: Optional[ConfigManager] = None,
        logger: Optional[MinifierLogger] = None,
    ):
        self.translator = translator
        self.session_manager = session_manager
        self.metrics = metrics_collector or EnhancedMetricsCollector()
        self.config = config_manager or ConfigManager()
        self.logger = logger or MinifierLogger()

        # Initialize handlers for supported agents
        self.handlers: Dict[str, BaseOutputIntegration] = {
            'vscode': VSCodeOutputIntegration(
                translator, session_manager, self.metrics, self.config, self.logger
            ),
            'cursor': CursorOutputIntegration(
                translator, session_manager, self.metrics, self.config, self.logger
            ),
            'claude': ClaudeCodeOutputIntegration(
                translator, session_manager, self.metrics, self.config, self.logger
            ),
        }

    def supported_agents(self) -> list:
        """Return a list of supported agent names."""
        return list(self.handlers.keys())

    async def handle_response_async(
        self,
        agent: str,
        session_id: str,
        llm_response: str
    ) -> Dict[str, Any]:
        """
        Route LLM response to the appropriate handler.
        Args:
            agent: Agent name (vscode, cursor, claude)
            session_id: Active session ID
            llm_response: Raw LLM response
        Returns:
            Processed response dict from handler
        Raises:
            ValueError: If the agent is unsupported
        """
        agent_key = agent.lower()
        if agent_key not in self.handlers:
            msg = f"Unknown agent: {agent_key}. Supported: {self.supported_agents()}"
            self.logger.log_error(message=msg)
            await self.metrics.record_async('unified_output_failure', {
                'agent': agent_key,
                'error': 'unknown_agent'
            })
            raise ValueError(msg)

        handler = self.handlers[agent_key]
        start = asyncio.get_event_loop().time()
        try:
            result = await handler.handle_llm_response(session_id, llm_response)

            # Normalize similarity score across handlers
            similarity = result.get('similarity_score', result.get('avg_similarity', 0.0))

            elapsed_ms = int((asyncio.get_event_loop().time() - start) * 1000)
            self.logger.log_info(
                message=f"Handled response for {agent_key} in {elapsed_ms}ms",
                session_id=session_id
            )
            await self.metrics.record_async('unified_output_success', {
                'agent': agent_key,
                'duration_ms': elapsed_ms,
                'status': result.get('status'),
                'similarity': similarity
            })

            return result

        except Exception as e:
            err = str(e)
            self.logger.log_error(message=err, session_id=session_id)
            elapsed_ms = int((asyncio.get_event_loop().time() - start) * 1000)
            await self.metrics.record_async('unified_output_error', {
                'agent': agent_key,
                'error': err,
                'duration_ms': elapsed_ms
            })
            return {
                'status': 'error',
                'error': err,
                'agent': agent_key,
                'session_id': session_id
            }
