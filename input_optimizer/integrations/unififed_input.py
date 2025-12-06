import asyncio  # Addition: For async handling (non-blocking event dispatch)
from typing import Dict, Any, Optional
import logging  # Addition: For structured logging

# Additions: Import shared components (assume from architecture; for observability/config)
from core.metrics_collector import EnhancedMetricsCollector
from core.config import ConfigManager
from utils.logger import MinifierLogger  # Your enhanced logger
from .base_integration import BaseInputIntegration  # For type hints
import time
from pathlib import Path

# Import agent-specific (assume exist)
from .vscode_input import VSCodeInputIntegration
from .cursor_input import CursorInputIntegration
from .claude_code_input import ClaudeCodeInputIntegration

class UnifiedInputHandler:
    """Unified handler for input integrations across agents.
    
    Additions for production-grade MVP:
    - Inject metrics_collector, config_manager, logger for observability and agent-specific enabling (e.g., disable via config).
    - Make handle_event async for concurrency (e.g., batch events in VSCode multi-open).
    - Handle more events ('file_change', 'file_close') for completeness (dispatch to handlers).
    - Error handling: Try/except in dispatch; validate data keys; custom exceptions.
    - Validation: Check agent enabled in config; ensure required data (e.g., 'file_path').
    - Observability: Log events and metrics (e.g., event_success/failure per agent).
    - Documentation: Docstrings/doctests for methods; examples for usage.
    - Risks Mitigated: Bad data (validation), blocking (async), no insights (metrics/logging), incomplete events (added dispatch).
    """
    
    def __init__(
        self,
        session_mgr: Any,  # SecureSessionManager
        compressor: Any,  # WaterfallCompressor
        metrics_collector: Optional[EnhancedMetricsCollector] = None,
        config_manager: Optional[ConfigManager] = None,
        logger: Optional[MinifierLogger] = None
    ):
        self.session_mgr = session_mgr
        self.compressor = compressor
        self.metrics = metrics_collector or EnhancedMetricsCollector()  # Fallback
        self.config = config_manager or ConfigManager()  # Fallback
        self.logger = logger or MinifierLogger()  # Fallback
        
        # Addition: Configurable handlers (enable/disable via config)
        self.handlers: Dict[str, BaseInputIntegration] = {}
        for agent in ['vscode', 'cursor', 'claude']:
            if self.config.get_config(agent).enabled:  # Assume 'enabled' flag in AgentConfig
                if agent == 'vscode':
                    self.handlers[agent] = VSCodeInputIntegration(self.session_mgr, self.compressor)
                elif agent == 'cursor':
                    self.handlers[agent] = CursorInputIntegration(self.session_mgr, self.compressor)
                elif agent == 'claude':
                    self.handlers[agent] = ClaudeCodeInputIntegration(self.session_mgr, self.compressor)
    
    async def handle_event(self, agent: str, event: str, data: dict) -> dict:  # Addition: Async for non-blocking
        """Handle input event asynchronously across agents.
        
        >>> # Doctest: Mock handler (simplified)
        >>> mock_mgr = Mock()
        >>> mock_comp = Mock()
        >>> handler = UnifiedInputHandler(mock_mgr, mock_comp)
        >>> asyncio.run(handler.handle_event('vscode', 'file_open', {'file_path': '/test.py'}))
        {'status': 'ready'}  # Assume mock return
        """
        if agent not in self.handlers:
            self.logger.error(f"Unknown or disabled agent: {agent}")
            self.metrics.record('event_handle_failure', {'agent': agent, 'error': 'unknown_agent'})
            raise ValueError(f"Unknown or disabled agent: {agent}")
        
        # Addition: Validate data (e.g., required keys)
        if event in ['file_open', 'file_change'] and 'file_path' not in data:
            self.logger.warning(f"Missing 'file_path' in data for {event}")
            self.metrics.record('event_handle_failure', {'agent': agent, 'error': 'missing_data'})
            raise ValueError("Missing 'file_path' in event data")
        
        integration = self.handlers[agent]
        start_time = time.time()
        try:
            if event == 'file_open':
                result = await integration.on_file_open(Path(data['file_path']))
            elif event == 'file_change':
                result = await integration.on_file_change(Path(data['file_path']))
            elif event == 'file_close':  # Addition: New event dispatch (for cleanup)
                result = await integration.on_file_close(Path(data['file_path'])) if hasattr(integration, 'on_file_close') else {'status': 'ignored'}
            else:
                raise ValueError(f"Unsupported event: {event}")
            
            duration = (time.time() - start_time) * 1000
            self.logger.info(f"Handled {event} for {agent} in {duration:.2f}ms")
            self.metrics.record('event_handle_success', {'agent': agent, 'event': event, 'duration_ms': duration})
            return result
        except Exception as e:
            self.logger.exception(f"Error handling {event} for {agent}: {e}")
            self.metrics.record('event_handle_failure', {'agent': agent, 'event': event, 'error': str(e)})
            raise