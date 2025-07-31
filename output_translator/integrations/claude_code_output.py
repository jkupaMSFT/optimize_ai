"""
Claude Code-specific output handling.
Processes LLM responses from Claude Code CLI into Python files.
"""
from typing import Dict, Any, List, Optional
import asyncio
import logging
import re

from .base_output import BaseOutputIntegration
from ...core.session_manager import SecureSessionManager
from ...core.metrics_collector import EnhancedMetricsCollector
from ...core.config import ConfigManager
from ...utils.logger import MinifierLogger
from ..core.translator import CAIToPythonTranslator, TranslationResult

logger = logging.getLogger(__name__)

class ClaudeCodeOutputIntegration(BaseOutputIntegration):
    """
    Claude Code-specific output integration.
    Handles multi-file responses from Claude CLI.
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
        self.agent_config = self.config.get_config('claude')
        self.logger = logger or MinifierLogger()
        self.metrics = metrics_collector or EnhancedMetricsCollector()

    async def handle_llm_response(
        self,
        session_id: str,
        llm_response: str
    ) -> Dict[str, Any]:
        """
        Handle LLM response for Claude Code.
        Parses multi-file responses, translates each section, records metrics, and handles errors.
        """
        start_time = asyncio.get_event_loop().time()
        try:
            # Split the CLI response into file-specific sections
            file_sections = self._parse_claude_response(llm_response)

            translated_files: Dict[str, Any] = {}
            total_similarity = 0.0

            # Translate each CAI section back to Python
            for file_path, cai_content in file_sections.items():
                translation: TranslationResult = await self._translate_section(
                    session_id, cai_content, file_path
                )
                translated_files[file_path] = {
                    "translated_code": translation.python_code,
                    "success": translation.success,
                    "similarity": translation.similarity_score,
                    "errors": translation.errors,
                    "warnings": translation.warnings
                }
                total_similarity += translation.similarity_score

            file_count = len(translated_files)
            avg_similarity = total_similarity / file_count if file_count > 0 else 0.0

            # Record success metrics including duration
            await self.metrics.record_async("claude_response_handled", {
                "session_id": session_id,
                "file_count": file_count,
                "avg_similarity": avg_similarity,
                "total_errors": sum(len(f["errors"]) for f in translated_files.values()),
                "duration_ms": int((asyncio.get_event_loop().time() - start_time) * 1000)
            })

            status = "success" if all(f["success"] for f in translated_files.values()) else "partial_success"
            return {
                "status": status,
                "translated_files": translated_files,
                "avg_similarity": avg_similarity,
                "file_count": file_count
            }

        except Exception as e:
            # Log and report any errors
            self.logger.log_error(message=str(e), session_id=session_id)
            await self.metrics.record_async("claude_handle_error", {
                "session_id": session_id,
                "error": str(e),
                "duration_ms": int((asyncio.get_event_loop().time() - start_time) * 1000)
            })
            return {
                "status": "error",
                "error": str(e),
                "session_id": session_id
            }

    def _parse_claude_response(self, response: str) -> Dict[str, str]:
        """
        Parse Claude's multi-file response format into a dict of {filename: cai_content}.
        Expected markers: lines like '=== filename ==='
        """
        sections: Dict[str, str] = {}
        current_file: Optional[str] = None
        current_content: List[str] = []

        for line in response.splitlines():
            m = re.match(r"^===\s*(.+?)\s*===$", line)
            if m:
                if current_file:
                    sections[current_file] = "\n".join(current_content).strip()
                current_file = m.group(1)
                current_content = []
            else:
                current_content.append(line)
        if current_file:
            sections[current_file] = "\n".join(current_content).strip()

        return sections

    async def _translate_section(
        self,
        session_id: str,
        cai_content: str,
        file_path: str
    ) -> TranslationResult:
        """
        Translate a single file section from CAI format back into Python.
        """
        session = self.session_manager.get_session(session_id)
        metadata = session.metadata if session else {}
        return await self.translator.translate(
            cai_content,
            source_map=metadata.get('source_map', {})
        )
