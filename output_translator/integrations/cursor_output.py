"""
Cursor-specific output handling.
Processes LLM responses for Cursor IDE.
"""
from typing import Dict, Any, List, Optional
import asyncio
import logging

from .base_output import BaseOutputIntegration
from ...core.session_manager import SecureSessionManager
from ...core.metrics_collector import EnhancedMetricsCollector
from ...core.config import ConfigManager
from ...utils.logger import MinifierLogger
from ..core.translator import CAIToPythonTranslator

logger = logging.getLogger(__name__)

class CursorOutputIntegration(BaseOutputIntegration):
    """
    Cursor-specific output integration.
    Handles LLM responses with Cursor features like autonomous workflows.
    """

    def __init__(
        self,
        translator: CAIToPythonTranslator,
        session_manager: SecureSessionManager,
        metrics_collector: Optional[EnhancedMetricsCollector] = None,
        config_manager: Optional[ConfigManager] = None,
        logger: Optional[MinifierLogger] = None,
    ):
        super().__init__(translator, session_manager, metrics_collector, config_manager, logger)
        self.config = config_manager or ConfigManager()
        self.agent_config = self.config.get_config('cursor')
        self.logger = logger or MinifierLogger()
        self.metrics = metrics_collector or EnhancedMetricsCollector()

    async def handle_llm_response(
        self,
        session_id: str,
        llm_response: str
    ) -> Dict[str, Any]:
        """
        Handle LLM response for Cursor.
        Supports Cursor-specific formatting, metrics, and error handling.
        """
        start_time = asyncio.get_event_loop().time()
        try:
            result = await super().handle_llm_response(session_id, llm_response)

            # Cursor-specific processing
            features = result.get("metadata", {}).get("features", [])
            if "autonomous" in features:
                result["cursor_autonomous"] = {
                    "suggested_edits": self._parse_autonomous_edits(
                        result.get("python_code", "")
                    )
                }

            # Similarity check with dynamic threshold
            similarity = result.get("similarity_score", 0.0)
            threshold = self.agent_config.get("similarity_threshold", 0.8)
            if similarity < threshold:
                warnings = result.setdefault("warnings", [])
                warnings.append(
                    "Cursor: Similarity below threshold - may require manual review"
                )

            # Record metrics including processing duration
            elapsed = asyncio.get_event_loop().time() - start_time
            await self.metrics.record_async("cursor_response_handled", {
                "session_id": session_id,
                "status": result.get("status"),
                "similarity": similarity,
                "duration_ms": int(elapsed * 1000)
            })

            return result

        except Exception as e:
            # Log and record errors
            self.logger.log_error(message=str(e), session_id=session_id)
            await self.metrics.record_async("cursor_response_error", {
                "session_id": session_id,
                "error": str(e)
            })
            return {
                "session_id": session_id,
                "status": "error",
                "error": str(e),
                "warnings": []
            }

    def _parse_autonomous_edits(self, code: str) -> List[Dict[str, Any]]:
        """
        Parse code into autonomous edit suggestions for Cursor.
        """
        # TODO: Implement detailed parsing logic for Cursor autonomous edits
        return [{"range": "full", "text": code}]
