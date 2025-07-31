# ===== tests/test_session_flow.py =====
import pytest
import asyncio
from pathlib import Path
from unittest.mock import patch
from core.session_manager import SecureSessionManager

@pytest.fixture
async def session_manager():
    mgr = SecureSessionManager()
    yield mgr
    # Cleanup after test
    await mgr.cleanup_expired_async(timeout=0)

@pytest.mark.asyncio
@pytest.mark.parametrize("agent,compressed_content,metadata", [
    ('vscode', 'compressed_vscode', {'key': 'value'}),
    ('cursor', 'compressed_cursor', {}),
    ('claude', 'compressed_claude', {'extra': 42}),
])
async def test_session_creation_and_retrieval(session_manager, agent, compressed_content, metadata):
    """
    Test session creation and retrieval with different agents.
    """
    file_path = Path('/test.py')
    
    sid = await session_manager.create_session_async(
        file_path=file_path,
        agent=agent,
        compressed_content=compressed_content,
        metadata=metadata
    )
    
    assert sid is not None
    assert isinstance(sid, str)
    
    session = session_manager.get_session(sid)
    assert session is not None
    assert session.file_path == file_path
    assert session.agent == agent
    assert session.compressed_content == compressed_content
    assert session.metadata == metadata

@pytest.mark.asyncio
async def test_session_expiration(session_manager):
    """
    Test session expiration and cleanup.
    """
    file_path = Path('/expiring.py')
    sid = await session_manager.create_session_async(
        file_path=file_path,
        agent='vscode',
        compressed_content='compressed',
        metadata={}
    )
    
    # Mock expiration time to immediate
    with patch.object(session_manager, 'session_ttl', 0):
        await asyncio.sleep(0.1)  # Small delay to simulate time passage
        await session_manager.cleanup_expired_async()
    
    session = session_manager.get_session(sid)
    assert session is None

@pytest.mark.asyncio
async def test_invalid_session_retrieval(session_manager):
    """
    Test retrieval of non-existent session.
    """
    non_existent_sid = 'invalid-123'
    session = session_manager.get_session(non_existent_sid)
    assert session is None

@pytest.mark.asyncio
async def test_multiple_sessions(session_manager):
    """
    Test handling multiple sessions and selective cleanup.
    """
    sid1 = await session_manager.create_session_async(Path('/file1.py'), 'vscode', 'comp1', {})
    sid2 = await session_manager.create_session_async(Path('/file2.py'), 'cursor', 'comp2', {})
    
    assert session_manager.get_session(sid1) is not None
    assert session_manager.get_session(sid2) is not None
    
    # Expire only one by mocking
    with patch.object(session_manager.sessions[sid1], 'is_expired', return_value=True):
        await session_manager.cleanup_expired_async()
    
    assert session_manager.get_session(sid1) is None
    assert session_manager.get_session(sid2) is not None

@pytest.mark.asyncio
async def test_session_creation_errors():
    """
    Test error handling in session creation.
    """
    mgr = SecureSessionManager()
    
    with pytest.raises(ValueError):
        await mgr.create_session_async(Path('/invalid.txt'), 'unknown_agent', 'comp', {})