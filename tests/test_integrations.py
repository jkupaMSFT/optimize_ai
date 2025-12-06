# ===== tests/test_integrations.py =====
import pytest
from pathlib import Path
from unittest.mock import Mock, AsyncMock, patch
import asyncio
from input_optimizer.integrations.unified_input import UnifiedInputHandler
from output_translator.integrations.unified_output import UnifiedOutputHandler

@pytest.fixture
def mock_setup():
    mock_mgr = Mock()
    mock_comp = Mock()
    mock_trans = Mock()
    input_handler = UnifiedInputHandler(mock_mgr, mock_comp)
    output_handler = UnifiedOutputHandler(mock_trans, mock_mgr)
    return input_handler, output_handler

@pytest.mark.asyncio
@pytest.mark.parametrize("agent,event,kwargs,expected_status", [
    ('vscode', 'file_open', {'file_path': '/test.py'}, 'success'),
    ('cursor', 'file_change', {'file_path': '/test.py'}, 'updated'),
    ('claude', 'command', {'command': ['claude-code', 'edit', 'test.py']}, 'intercepted'),
])
async def test_unified_input(mock_setup, agent, event, kwargs, expected_status):
    input_handler, _ = mock_setup
    
    # Mock internal methods if needed
    with patch.object(input_handler, '_get_integration', new=AsyncMock()) as mock_get:
        mock_integration = AsyncMock()
        mock_integration.handle_event = AsyncMock(return_value={'status': expected_status})
        mock_get.return_value = mock_integration
        
        result = await input_handler.handle_event(agent, event, kwargs)
        
        assert 'status' in result
        assert result['status'] == expected_status
        mock_get.assert_called_once_with(agent)

@pytest.mark.asyncio
@pytest.mark.parametrize("agent,event,kwargs,expected_status", [
    ('vscode', 'completion', {'completion_text': 'compressed_code'}, 'translated'),
    ('cursor', 'workflow_output', {'output': 'cai_output'}, 'translated'),
])
async def test_unified_output(mock_setup, agent, event, kwargs, expected_status):
    _, output_handler = mock_setup
    
    # Mock internal methods
    with patch.object(output_handler, '_get_translator', new=AsyncMock()) as mock_get:
        mock_translator = AsyncMock()
        mock_translator.translate_output = AsyncMock(return_value={'status': expected_status, 'python_code': 'translated_code'})
        mock_get.return_value = mock_translator
        
        result = await output_handler.handle_event(agent, event, kwargs)
        
        assert 'status' in result
        assert result['status'] == expected_status
        mock_get.assert_called_once_with(agent)

@pytest.mark.asyncio
async def test_unified_input_error(mock_setup):
    input_handler, _ = mock_setup
    
    with patch.object(input_handler, '_get_integration', new=AsyncMock()) as mock_get:
        mock_integration = AsyncMock()
        mock_integration.handle_event = AsyncMock(side_effect=ValueError("Invalid file"))
        mock_get.return_value = mock_integration
        
        with pytest.raises(ValueError):
            await input_handler.handle_event('vscode', 'file_open', {'file_path': '/invalid'})

@pytest.mark.asyncio
async def test_unified_output_no_session(mock_setup):
    _, output_handler = mock_setup
    
    with patch.object(output_handler, '_get_translator', new=AsyncMock()) as mock_get:
        mock_translator = AsyncMock()
        mock_translator.translate_output = AsyncMock(return_value={'status': 'error', 'error': 'No session'})
        mock_get.return_value = mock_translator
        
        result = await output_handler.handle_event('claude', 'response', {'output': 'no_session'})
        
        assert result['status'] == 'error'