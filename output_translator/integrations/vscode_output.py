# ===== output_translator/integrations/vscode_output.py =====
"""
VSCode-specific output handling.
Processes LLM responses for VSCode extension.
"""

from typing import Dict, Any, Optional
import asyncio
import logging
import time
from .base_output import BaseOutputIntegration
from ...core.session_manager import SecureSessionManager
from ...core.metrics_collector import EnhancedMetricsCollector
from ...core.config import ConfigManager
from ...utils.logger import MinifierLogger
from ...utils.metrics import calculate_similarity
from ..core.translator import CAIToPythonTranslator


class VSCodeOutputIntegration(BaseOutputIntegration):
    """
    VSCode-specific output integration.
    Handles LLM responses in VSCode context with additional formatting.
    """
    
    def __init__(
        self,
        translator: CAIToPythonTranslator,
        session_manager: SecureSessionManager,
        metrics_collector: Optional[EnhancedMetricsCollector] = None,
        config_manager: Optional[ConfigManager] = None,
        logger: Optional[MinifierLogger] = None
    ):
        super().__init__(translator, session_manager, metrics_collector, config_manager, logger)
        self.agent_config = self.config.get_config('vscode')
        self.logger.info("VSCodeOutputIntegration initialized")
    
    async def handle_llm_response(
        self,
        session_id: str,
        llm_response: str
    ) -> Dict[str, Any]:
        """
        Handle LLM response for VSCode.
        Applies VSCode-specific processing if needed.
        """
        try:
            # Use base handling
            result = await super().handle_llm_response(session_id, llm_response)
            
            # VSCode-specific additions
            if result["status"] in ["success", "partial_success"]:
                # Format for VSCode insertion
                result["vscode_format"] = {
                    "insert_text": result["python_code"],
                    "range": "full_replace"  # Placeholder; could be dynamic based on session
                }
                
                # Check against VSCode config
                if result["similarity_score"] < self.agent_config.similarity_threshold:
                    warning = f"VSCode: Similarity below threshold ({result['similarity_score']:.2f} < {self.agent_config.similarity_threshold}) - review manually"
                    result["warnings"].append(warning)
                    self.logger.warning(warning)
            
            # Record VSCode-specific metrics
            await self.metrics.record_async("vscode_response_handled", {
                "session_id": session_id,
                "status": result["status"],
                "similarity": result.get("similarity_score", 0),
                "warnings_count": len(result.get("warnings", []))
            })
            
            self.logger.debug(f"VSCode response processed: {result['status']}")
            return result
        
        except Exception as e:
            self.logger.error(f"Error in VSCode response handling: {str(e)}")
            await self.metrics.record_async("vscode_response_error", {
                "session_id": session_id,
                "error": str(e)
            })
            return {
                "status": "error",
                "error": str(e),
                "session_id": session_id
            }