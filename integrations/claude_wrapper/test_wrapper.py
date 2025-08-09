"""
Test suite for Claude Code wrapper
"""

import unittest
from unittest.mock import patch, MagicMock
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent.parent.parent))

from optimize_ai.integrations.claude_wrapper.claude_proxy import ClaudeCodeProxy

class TestClaudeWrapper(unittest.TestCase):
    
    def setUp(self):
        """Setup test fixtures"""
        self.proxy = ClaudeCodeProxy(enable_compression=True)
        
        # Sample Python code for testing
        self.sample_code = '''
def calculate_fibonacci(n):
    """Calculate fibonacci number"""
    if n <= 1:
        return n
    return calculate_fibonacci(n-1) + calculate_fibonacci(n-2)

class MathOperations:
    def __init__(self):
        self.results = []
    
    def add(self, a, b):
        result = a + b
        self.results.append(result)
        return result
    
    def multiply(self, a, b):
        return a * b
'''
    
    def test_compression_small_input(self):
        """Test compression for small input"""
        prompt = "Write a hello world function"
        compressed, metadata = self.proxy.process_input(prompt)
        
        # Small prompts should use TINY or SMALL tier
        self.assertIn(metadata['tier'], ['TINY', 'SMALL'])
        
        # Should not compress tiny inputs
        if metadata['tier'] == 'TINY':
            self.assertFalse(metadata['compressed'])
    
    def test_compression_medium_code(self):
        """Test compression for medium-sized code"""
        compressed, metadata = self.proxy.process_input(self.sample_code)
        
        self.assertTrue(metadata['compressed'])
        self.assertGreater(metadata['original_tokens'], metadata['compressed_tokens'])
        self.assertIn('F[calculate_fibonacci', compressed)  # Should contain CAI format
    
    def test_cai_detection(self):
        """Test CAI format detection"""
        cai_text = "F[test(x) → {return x*2}]"
        self.assertTrue(self.proxy._contains_cai_format(cai_text))
        
        normal_text = "def test(x): return x*2"
        self.assertFalse(self.proxy._contains_cai_format(normal_text))
    
    def test_cai_extraction(self):
        """Test CAI block extraction"""
        text_with_cai = """
        Here's the code:
        ---CAI CODE START---
        F[test(x) → {return x*2}]
        C[MyClass → {methods}]
        ---CAI CODE END---
        """
        
        blocks = self.proxy._extract_cai_blocks(text_with_cai)
        self.assertEqual(len(blocks), 1)
        self.assertIn('F[test', blocks[0])
    
    @patch('subprocess.run')
    def test_execute_with_mock_claude(self, mock_run):
        """Test execution with mocked Claude Code"""
        # Mock Claude's response
        mock_result = MagicMock()
        mock_result.stdout = "def hello(): print('Hello from Claude')"
        mock_result.stderr = ""
        mock_result.returncode = 0
        mock_run.return_value = mock_result
        
        result = self.proxy.execute_with_claude("write a hello function")
        
        self.assertIn("hello", result)
        mock_run.assert_called_once()
    
    def test_output_translation(self):
        """Test CAI to Python translation in output"""
        # Simulate Claude output with CAI format
        claude_output = """
        Here's the compressed code:
        ---CAI CODE START---
        F[hello(name) → {return f"Hello {name}"}]
        ---CAI CODE END---
        """
        
        metadata = {
            "compressed": True,
            "session_id": "test_session"
        }
        
        processed = self.proxy.process_output(claude_output, metadata)
        
        # Should translate CAI back to Python
        self.assertIn("def hello", processed)
        self.assertNotIn("F[hello", processed)
    
    def test_error_handling(self):
        """Test error handling in compression"""
        # Test with invalid input
        compressed, metadata = self.proxy.process_input("")
        self.assertFalse(metadata.get('compressed', False))
        
        # Test with None input
        compressed, metadata = self.proxy.process_input(None)
        self.assertEqual(compressed, None)

if __name__ == '__main__':
    # Run tests with verbose output
    unittest.main(verbosity=2)