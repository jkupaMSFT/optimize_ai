"""
Shared test configuration and fixtures for optimize_ai test suite.
"""
import pytest
import tempfile
import asyncio
from pathlib import Path
from unittest.mock import Mock, AsyncMock
from core.session_manager import SecureSessionManager
from core.metrics_collector import EnhancedMetricsCollector
from core.config import ConfigManager


@pytest.fixture
def session_manager():
    """Create a SecureSessionManager instance for testing."""
    return SecureSessionManager()


@pytest.fixture 
async def async_session_manager():
    """Create an async SecureSessionManager instance for testing."""
    mgr = SecureSessionManager()
    yield mgr
    # Cleanup after test
    try:
        await mgr.cleanup_expired_async(timeout=0)
    except Exception:
        pass  # Ignore cleanup errors in tests


@pytest.fixture
def sample_python_code():
    """Sample Python code for testing."""
    return """
def calculate_sum(numbers):
    total = 0
    for num in numbers:
        total += num
    return total

def fibonacci(n):
    if n <= 1:
        return n
    return fibonacci(n-1) + fibonacci(n-2)

class Calculator:
    def __init__(self):
        self.history = []
    
    def add(self, a, b):
        result = a + b
        self.history.append(('add', a, b, result))
        return result
"""


@pytest.fixture  
def complex_python_code():
    """Complex Python code for compression testing."""
    return """
import asyncio
import json
from typing import Dict, List, Optional, Any
from pathlib import Path

class DataProcessor:
    def __init__(self, config_path: Path):
        self.config_path = config_path
        self.config = self._load_config()
        self.cache = {}
    
    def _load_config(self) -> Dict[str, Any]:
        try:
            with open(self.config_path, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            return {"default": True}
    
    async def process_data(self, data: List[Dict]) -> List[Dict]:
        results = []
        for item in data:
            if item.get('type') == 'numeric':
                processed = await self._process_numeric(item)
            elif item.get('type') == 'text':
                processed = await self._process_text(item)
            else:
                processed = item
            results.append(processed)
        return results
    
    async def _process_numeric(self, item: Dict) -> Dict:
        value = item.get('value', 0)
        multiplier = self.config.get('numeric_multiplier', 1)
        item['processed_value'] = value * multiplier
        return item
    
    async def _process_text(self, item: Dict) -> Dict:
        text = item.get('value', '')
        if self.config.get('uppercase', False):
            item['processed_value'] = text.upper()
        else:
            item['processed_value'] = text.lower()
        return item
"""


@pytest.fixture
def temp_test_file():
    """Create a temporary test file."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
        f.write("""
def example_function():
    return "Hello, World!"

class ExampleClass:
    def __init__(self, value):
        self.value = value
""")
        temp_path = Path(f.name)
    
    yield temp_path
    
    # Cleanup
    if temp_path.exists():
        temp_path.unlink()


@pytest.fixture
def temp_directory():
    """Create a temporary directory for testing."""
    temp_dir = tempfile.mkdtemp()
    yield Path(temp_dir)
    
    # Cleanup handled by system temp cleanup


@pytest.fixture
def mock_metrics_collector():
    """Mock metrics collector for testing."""
    mock = Mock(spec=EnhancedMetricsCollector)
    mock.record_event = Mock()
    mock.record_timing = Mock()
    mock.get_metrics = Mock(return_value={})
    return mock


@pytest.fixture  
def mock_config_manager():
    """Mock config manager for testing."""
    mock = Mock(spec=ConfigManager)
    mock.get = Mock(return_value=None)
    mock.set = Mock()
    mock.load_config = Mock()
    return mock


@pytest.fixture
def mock_compression_result():
    """Mock compression result for testing."""
    mock = Mock()
    mock.compressed_content = "compressed_code_here"
    mock.compression_ratio = 0.75
    mock.metadata = {"technique": "waterfall", "stats": {}}
    mock.success = True
    return mock


@pytest.fixture
def mock_translation_result():
    """Mock translation result for testing."""
    mock = Mock()
    mock.translated_content = "translated_code_here"
    mock.success = True
    mock.metadata = {"translator": "pattern", "confidence": 0.95}
    return mock


@pytest.fixture
def sample_file_content():
    """Sample file content with various Python constructs."""
    return {
        'simple': 'def hello(): return "world"',
        'complex': '''
import os
import sys
from typing import List, Dict

class DataHandler:
    def __init__(self, path: str):
        self.path = path
        self.data = []
    
    def load_data(self) -> List[Dict]:
        # Complex loading logic
        try:
            with open(self.path, 'r') as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading: {e}")
            return []
    
    def process_items(self, items: List[Dict]) -> List[Dict]:
        processed = []
        for item in items:
            if item.get('active', True):
                item['processed'] = True
                item['timestamp'] = time.time()
                processed.append(item)
        return processed
''',
        'with_errors': '''
def broken_function(
    # Missing closing parenthesis
    return "This has syntax errors"

class IncompleteClass
    # Missing colon
    def method(self):
        pass
'''
    }


# Mock LLM responses for testing
@pytest.fixture
def mock_llm_responses():
    """Mock LLM responses for different scenarios."""
    return {
        'compression_success': {
            'compressed_content': 'def f(x):return x*2',
            'ratio': 0.6,
            'success': True
        },
        'compression_failure': {
            'compressed_content': None,
            'ratio': 1.0,
            'success': False,
            'error': 'Compression failed'
        },
        'translation_success': {
            'translated_content': 'def multiply_by_two(x):\n    return x * 2',
            'success': True,
            'confidence': 0.9
        },
        'translation_failure': {
            'translated_content': None,
            'success': False,
            'error': 'Translation failed'
        }
    }


# Event loop fixture for async tests
@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


# Pytest configuration
def pytest_configure(config):
    """Configure pytest with custom markers."""
    config.addinivalue_line(
        "markers", "slow: marks tests as slow (deselect with '-m \"not slow\"')"
    )
    config.addinivalue_line(
        "markers", "integration: marks tests as integration tests"
    )
    config.addinivalue_line(
        "markers", "unit: marks tests as unit tests"
    )


def pytest_collection_modifyitems(config, items):
    """Automatically mark tests based on their names/paths."""
    for item in items:
        # Mark integration tests
        if "integration" in item.nodeid or "test_integrations" in item.nodeid:
            item.add_marker(pytest.mark.integration)
        # Mark unit tests  
        elif "unit" in item.nodeid or not any(marker in item.nodeid for marker in ["integration", "e2e", "end_to_end"]):
            item.add_marker(pytest.mark.unit)
        # Mark slow tests
        if "slow" in item.nodeid or "benchmark" in item.nodeid:
            item.add_marker(pytest.mark.slow)
