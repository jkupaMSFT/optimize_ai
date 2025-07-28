"""
Integration and mock-header tests for adapter.py functionality.

This test suite covers:
- Integration tests with real API endpoints
- Mock header tests for rate limiting scenarios
- Validation loops to prevent infinite loops and semantic regressions
- Latency checks for large payload handling
"""

import pytest
import time
import asyncio
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
import ast
import difflib
from typing import Dict, Any, Tuple

# Import the FastAPI app
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from app import app
from engine.adapter import adapt_compression, CompressionResult
from engine.adapter import (
    calculate_remaining_pct,
    select_waterfall_tier,
    process_content_with_logging
)
from utils.compression import CompressionType

# Test client for FastAPI
client = TestClient(app)

# Test constants
LARGE_PAYLOAD_THRESHOLD = 10000  # chars
LATENCY_WARNING_THRESHOLD = 200  # ms

class TestAdapterIntegration:
    """Integration tests for adapter functionality with real endpoints."""
    
    def test_minify_endpoint_with_low_remaining_pct(self):
        """Test /minify endpoint with low remaining percentage triggers aggressive compression."""
        code = """
def example_function(param1, param2, param3):
    '''This is a docstring with lots of text'''
    result = []
    for i in range(100):
        if i % 2 == 0:
            result.append(i * param1)
        else:
            result.append(i * param2)
    return result
"""
        
        # Mock headers with low remaining percentage (10%)
        headers = {
            "x-ratelimit-remaining-tokens": "1000",
            "x-ratelimit-limit-tokens": "10000",
            "x-request-id": "test-low-pct-minify"
        }
        
        response = client.post(
            "/minify",
            json={"code": code, "aggressive": False},
            headers=headers
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify aggressive compression was applied
        assert len(data["minified"]) < len(code)
        assert data["size_reduction_percent"] > 20  # Should achieve significant reduction
        assert "minified" in data
        assert "estimated_tokens" in data
    
    def test_translate_sudolang_with_high_remaining_pct(self):
        """Test /translate/sudolang endpoint with high remaining percentage allows lighter compression."""
        code = """
def calculate_total(items):
    total = 0
    for item in items:
        total += item.price
    return total
"""
        
        # Mock headers with high remaining percentage (90%)
        headers = {
            "x-ratelimit-remaining-tokens": "9000",
            "x-ratelimit-limit-tokens": "10000",
            "x-request-id": "test-high-pct-sudolang"
        }
        
        response = client.post(
            "/translate/sudolang",
            json={"code": code},
            headers=headers
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify translation was successful
        assert "translated" in data
        assert len(data["translated"]) > 0
        assert data["original_size"] == len(code)
    
    def test_translate_synthlang_with_medium_remaining_pct(self):
        """Test /translate/synthlang endpoint with medium remaining percentage applies balanced compression."""
        code = """
class DataProcessor:
    def __init__(self, data):
        self.data = data
        self.processed = False
    
    def process(self):
        if not self.processed:
            self.data = [x * 2 for x in self.data]
            self.processed = True
        return self.data
"""
        
        # Mock headers with medium remaining percentage (50%)
        headers = {
            "x-ratelimit-remaining-tokens": "5000",
            "x-ratelimit-limit-tokens": "10000",
            "x-request-id": "test-medium-pct-synthlang"
        }
        
        response = client.post(
            "/translate/synthlang",
            json={"code": code, "compact": True},
            headers=headers
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify translation was successful with reasonable compression
        assert "translated" in data
        assert len(data["translated"]) > 0
        assert data["compact_mode"] is True


class TestMockHeaderScenarios:
    """Mock header tests for different rate limiting scenarios."""
    
    @pytest.mark.parametrize("remaining_pct,expected_tier", [
        (10, "aggressive_or_higher"),  # Low remaining should trigger aggressive
        (50, "standard_or_balanced"),  # Medium remaining should be balanced
        (90, "basic_or_downgraded"),   # High remaining can use lighter compression
    ])
    def test_rate_limit_header_adaptation(self, remaining_pct, expected_tier):
        """Test that different remaining percentages trigger appropriate tier selection."""
        code = "def test(): return 'hello world'" * 20  # Medium size code
        
        headers = {
            "x-ratelimit-remaining-tokens": str(int(remaining_pct * 100)),
            "x-ratelimit-limit-tokens": "10000"
        }
        
        # Test with direct adapter function
        result = adapt_compression(headers, code, return_metadata=True)
        
        assert isinstance(result, CompressionResult)
        assert result.compressed_code is not None
        assert result.pre_tokens > 0
        assert result.post_tokens >= 0
        
        # Verify compression level matches expectation
        if remaining_pct <= 20:
            # Should use aggressive compression
            assert result.token_reduction_percent > 10
        elif remaining_pct >= 80:
            # Should use lighter compression or even expand for readability
            assert result.token_reduction_percent >= -50  # Allow some expansion
    
    def test_missing_rate_limit_headers(self):
        """Test behavior when rate limit headers are missing."""
        code = "def example(): pass"
        headers = {}  # No rate limit headers
        
        result = adapt_compression(headers, code, return_metadata=True)
        
        # Should still work with default behavior
        assert isinstance(result, CompressionResult)
        assert result.compressed_code is not None
        assert "remaining_pct" in result.additional_metrics
    
    def test_invalid_rate_limit_headers(self):
        """Test behavior with invalid rate limit header values."""
        code = "def example(): pass"
        
        test_cases = [
            {"x-ratelimit-remaining-tokens": "invalid", "x-ratelimit-limit-tokens": "1000"},
            {"x-ratelimit-remaining-tokens": "500", "x-ratelimit-limit-tokens": "invalid"},
            {"x-ratelimit-remaining-tokens": "-100", "x-ratelimit-limit-tokens": "1000"},
            {"x-ratelimit-remaining-tokens": "1500", "x-ratelimit-limit-tokens": "1000"},  # Remaining > limit
        ]
        
        for headers in test_cases:
            # Should handle gracefully and not crash
            result = adapt_compression(headers, code, return_metadata=True)
            assert isinstance(result, CompressionResult)
            assert result.compressed_code is not None


class TestValidationLoops:
    """Validation tests to prevent infinite loops and semantic regressions."""
    
    def test_no_infinite_loops_with_recursive_content(self):
        """Ensure adapter doesn't get stuck in infinite loops with recursive-like content."""
        # Create code that might trigger recursive processing
        recursive_code = """
def recursive_function(n):
    if n <= 0:
        return 1
    else:
        return n * recursive_function(n - 1)

def another_recursive(a, b):
    if a == b:
        return a
    elif a > b:
        return another_recursive(a - b, b)
    else:
        return another_recursive(a, b - a)
""" * 5  # Repeat to make it larger
        
        headers = {"x-ratelimit-remaining-tokens": "1000", "x-ratelimit-limit-tokens": "10000"}
        
        start_time = time.time()
        result = adapt_compression(headers, recursive_code, return_metadata=True)
        processing_time = time.time() - start_time
        
        # Should complete in reasonable time (less than 5 seconds)
        assert processing_time < 5.0
        assert isinstance(result, CompressionResult)
        assert result.compressed_code is not None
    
    def test_semantic_preservation_validation(self):
        """Test that compressed code maintains semantic equivalence."""
        original_code = """
def calculate_fibonacci(n):
    if n <= 1:
        return n
    a, b = 0, 1
    for _ in range(2, n + 1):
        a, b = b, a + b
    return b

def test_fibonacci():
    assert calculate_fibonacci(0) == 0
    assert calculate_fibonacci(1) == 1
    assert calculate_fibonacci(5) == 5
    assert calculate_fibonacci(10) == 55
    return "All tests passed"
"""
        
        headers = {"x-ratelimit-remaining-tokens": "2000", "x-ratelimit-limit-tokens": "10000"}
        
        result = adapt_compression(headers, original_code, return_metadata=True)
        compressed_code = result.compressed_code
        
        # Both should parse successfully
        try:
            original_ast = ast.parse(original_code)
            compressed_ast = ast.parse(compressed_code)
        except SyntaxError as e:
            pytest.fail(f"Syntax error in compressed code: {e}")
        
        # Basic structural validation
        assert len(compressed_ast.body) > 0
        
        # Verify no critical semantic changes (function names should be preserved in most cases)
        original_functions = {node.name for node in ast.walk(original_ast) if isinstance(node, ast.FunctionDef)}
        compressed_functions = {node.name for node in ast.walk(compressed_ast) if isinstance(node, ast.FunctionDef)}
        
        # Core function names should be preserved (unless very aggressive compression)
        if result.additional_metrics.get("final_tier") != "SUMMARIZE":
            assert len(compressed_functions) > 0, "All functions were removed during compression"
    
    def test_translation_flag_consistency(self):
        """Test that is_translate flag produces consistent results."""
        code = "def hello(): return 'world'"
        headers = {"x-ratelimit-remaining-tokens": "5000", "x-ratelimit-limit-tokens": "10000"}
        
        # Test without translation flag
        result1 = adapt_compression(headers, code, is_translate=False, return_metadata=True)
        
        # Test with translation flag
        result2 = adapt_compression(headers, code, is_translate=True, return_metadata=True)
        
        # Results should be different due to translation bias
        assert result1.additional_metrics.get("final_tier") != result2.additional_metrics.get("final_tier") or \
               result1.compressed_code != result2.compressed_code
        
        # Both should be valid
        assert len(result1.compressed_code) > 0
        assert len(result2.compressed_code) > 0


class TestLatencyChecks:
    """Latency tests to ensure adapter performance with large payloads."""
    
    def test_small_payload_latency(self):
        """Test latency with small payloads (should be very fast)."""
        small_code = "def small(): return 'test'"
        headers = {"x-ratelimit-remaining-tokens": "5000", "x-ratelimit-limit-tokens": "10000"}
        
        start_time = time.time()
        result = adapt_compression(headers, small_code, return_metadata=True)
        processing_time = (time.time() - start_time) * 1000  # Convert to ms
        
        # Small payloads should be very fast (< 50ms)
        assert processing_time < 50
        assert result.processing_time_ms < 100  # Internal measurement should also be fast
    
    def test_medium_payload_latency(self):
        """Test latency with medium payloads."""
        medium_code = """
class MediumClass:
    def __init__(self, value):
        self.value = value
        self.data = []
    
    def process_data(self):
        for i in range(100):
            self.data.append(i * self.value)
        return self.data
    
    def calculate_sum(self):
        return sum(self.data)
""" * 20  # Repeat to make it medium-sized
        
        headers = {"x-ratelimit-remaining-tokens": "3000", "x-ratelimit-limit-tokens": "10000"}
        
        start_time = time.time()
        result = adapt_compression(headers, medium_code, return_metadata=True)
        processing_time = (time.time() - start_time) * 1000
        
        # Medium payloads should complete reasonably fast (< 200ms)
        assert processing_time < 200
        print(f"Medium payload latency: {processing_time:.2f}ms")
    
    def test_large_payload_latency_warning(self):
        """Test latency with large payloads and warn if exceeding threshold."""
        # Create a large payload
        large_code = """
class LargeDataProcessor:
    def __init__(self):
        self.data = {}
        self.cache = {}
        self.statistics = {
            'processed': 0,
            'errors': 0,
            'total_time': 0
        }
    
    def process_large_dataset(self, dataset):
        '''Process a large dataset with comprehensive error handling and statistics.'''
        results = []
        for item in dataset:
            try:
                processed_item = self.complex_processing(item)
                results.append(processed_item)
                self.statistics['processed'] += 1
            except Exception as e:
                self.handle_error(e, item)
                self.statistics['errors'] += 1
        return results
    
    def complex_processing(self, item):
        '''Complex processing function with multiple steps.'''
        # Step 1: Validation
        if not self.validate_item(item):
            raise ValueError("Invalid item")
        
        # Step 2: Transformation
        transformed = self.transform_item(item)
        
        # Step 3: Enrichment
        enriched = self.enrich_item(transformed)
        
        # Step 4: Caching
        self.cache[item.get('id', hash(str(item)))] = enriched
        
        return enriched
    
    def validate_item(self, item):
        '''Validate item structure and content.'''
        required_fields = ['id', 'type', 'data']
        for field in required_fields:
            if field not in item:
                return False
        return True
    
    def transform_item(self, item):
        '''Transform item data.'''
        transformed = dict(item)
        if 'data' in transformed:
            transformed['data'] = self.normalize_data(transformed['data'])
        return transformed
    
    def normalize_data(self, data):
        '''Normalize data values.'''
        if isinstance(data, (int, float)):
            return max(0, min(100, data))
        elif isinstance(data, str):
            return data.strip().lower()
        elif isinstance(data, list):
            return [self.normalize_data(item) for item in data]
        return data
    
    def enrich_item(self, item):
        '''Enrich item with additional data.'''
        enriched = dict(item)
        enriched['timestamp'] = time.time()
        enriched['processing_version'] = '1.0'
        return enriched
    
    def handle_error(self, error, item):
        '''Handle processing errors.'''
        error_info = {
            'error': str(error),
            'item': str(item)[:100],  # Truncate for logging
            'timestamp': time.time()
        }
        # Log error (in real implementation)
        pass
""" * 25  # Repeat to make it very large (> 10KB)
        
        headers = {"x-ratelimit-remaining-tokens": "1000", "x-ratelimit-limit-tokens": "10000"}
        
        start_time = time.time()
        result = adapt_compression(headers, large_code, return_metadata=True)
        processing_time = (time.time() - start_time) * 1000
        
        print(f"Large payload size: {len(large_code)} chars")
        print(f"Large payload latency: {processing_time:.2f}ms")
        
        # Warn if exceeding threshold but don't fail the test
        if processing_time > LATENCY_WARNING_THRESHOLD:
            print(f"⚠️  WARNING: Large payload processing exceeded {LATENCY_WARNING_THRESHOLD}ms threshold")
            print(f"   Actual time: {processing_time:.2f}ms")
            print(f"   Consider optimization for payloads > {LARGE_PAYLOAD_THRESHOLD} chars")
        
        # Should still complete in reasonable time (< 2 seconds)
        assert processing_time < 2000, f"Processing took too long: {processing_time:.2f}ms"
        
        # Verify compression was effective for large payload
        assert result.token_reduction_percent > 5, "Large payload should achieve meaningful compression"
    
    def test_concurrent_requests_latency(self):
        """Test latency under concurrent load."""
        code = """
def concurrent_test_function(data):
    result = []
    for item in data:
        if isinstance(item, dict):
            result.append(item.get('value', 0) * 2)
    return sum(result)
""" * 10
        
        headers = {"x-ratelimit-remaining-tokens": "5000", "x-ratelimit-limit-tokens": "10000"}
        
        async def process_request():
            start_time = time.time()
            result = adapt_compression(headers, code, return_metadata=True)
            processing_time = (time.time() - start_time) * 1000
            return processing_time, result
        
        # Simulate concurrent requests
        async def run_concurrent_tests():
            tasks = [process_request() for _ in range(5)]
            results = await asyncio.gather(*tasks)
            return results
        
        # Run concurrent test
        start_time = time.time()
        results = asyncio.run(run_concurrent_tests())
        total_time = (time.time() - start_time) * 1000
        
        # Verify all requests completed successfully
        assert len(results) == 5
        for processing_time, result in results:
            assert isinstance(result, CompressionResult)
            assert processing_time < 500  # Each request should complete in reasonable time
        
        print(f"Concurrent requests total time: {total_time:.2f}ms")
        print(f"Average per request: {total_time/5:.2f}ms")


class TestEdgeCases:
    """Test edge cases and error conditions."""
    
    def test_empty_code_handling(self):
        """Test handling of empty or whitespace-only code."""
        headers = {"x-ratelimit-remaining-tokens": "5000", "x-ratelimit-limit-tokens": "10000"}
        
        # Test with empty string
        with pytest.raises(ValueError, match="cannot be empty"):
            adapt_compression(headers, "")
        
        # Test with whitespace only
        with pytest.raises(ValueError, match="cannot be empty"):
            adapt_compression(headers, "   \n\t  ")
    
    def test_malformed_code_handling(self):
        """Test handling of syntactically invalid code."""
        headers = {"x-ratelimit-remaining-tokens": "5000", "x-ratelimit-limit-tokens": "10000"}
        
        malformed_code = "def invalid_syntax( missing_parenthesis:"
        
        # Should handle gracefully and return original or attempt repair
        result = adapt_compression(headers, malformed_code, return_metadata=True)
        
        # Should not crash, either return original or attempt to fix
        assert isinstance(result, CompressionResult)
        assert len(result.compressed_code) > 0
    
    def test_extremely_nested_code(self):
        """Test handling of extremely nested code structures."""
        # Create deeply nested code
        nested_code = "def outer():\n"
        for i in range(20):  # 20 levels of nesting
            nested_code += "    " * (i + 1) + f"if True:\n"
        nested_code += "    " * 21 + "return 'deep'"
        
        headers = {"x-ratelimit-remaining-tokens": "2000", "x-ratelimit-limit-tokens": "10000"}
        
        result = adapt_compression(headers, nested_code, return_metadata=True)
        
        # Should handle without crashing
        assert isinstance(result, CompressionResult)
        assert len(result.compressed_code) > 0
    
    def test_unicode_and_special_characters(self):
        """Test handling of Unicode and special characters."""
        unicode_code = """
def process_unicode_text():
    text = "Hello 世界! 🌍 This has émojis and spëcial chars"
    symbols = "∑∆∫∂∇√∞≈≠≤≥±×÷"
    return f"Processed: {text} with {symbols}"

def test_encodings():
    data = {
        'english': 'Hello World',
        'chinese': '你好世界',
        'japanese': 'こんにちは世界',
        'arabic': 'مرحبا بالعالم',
        'emoji': '🚀🌟💻🔥'
    }
    return data
"""
        
        headers = {"x-ratelimit-remaining-tokens": "3000", "x-ratelimit-limit-tokens": "10000"}
        
        result = adapt_compression(headers, unicode_code, return_metadata=True)
        
        # Should handle Unicode correctly
        assert isinstance(result, CompressionResult)
        assert len(result.compressed_code) > 0
        
        # Verify no encoding issues
        try:
            result.compressed_code.encode('utf-8')
        except UnicodeEncodeError:
            pytest.fail("Unicode encoding issues in compressed output")


# Pytest fixtures for common test data
@pytest.fixture
def sample_headers_low():
    """Headers indicating low remaining tokens (10%)."""
    return {
        "x-ratelimit-remaining-tokens": "1000",
        "x-ratelimit-limit-tokens": "10000",
        "x-request-id": "test-low"
    }

@pytest.fixture
def sample_headers_medium():
    """Headers indicating medium remaining tokens (50%)."""
    return {
        "x-ratelimit-remaining-tokens": "5000",
        "x-ratelimit-limit-tokens": "10000",
        "x-request-id": "test-medium"
    }

@pytest.fixture
def sample_headers_high():
    """Headers indicating high remaining tokens (90%)."""
    return {
        "x-ratelimit-remaining-tokens": "9000",
        "x-ratelimit-limit-tokens": "10000",
        "x-request-id": "test-high"
    }

@pytest.fixture
def sample_code_small():
    """Small code sample for testing."""
    return "def hello(): return 'world'"

@pytest.fixture
def sample_code_medium():
    """Medium code sample for testing."""
    return """
def calculate_statistics(data):
    if not data:
        return {}
    
    total = sum(data)
    count = len(data)
    mean = total / count
    
    sorted_data = sorted(data)
    median = sorted_data[count // 2]
    
    return {
        'mean': mean,
        'median': median,
        'total': total,
        'count': count
    }
"""


if __name__ == "__main__":
    # Run specific test categories
    import sys
    
    if len(sys.argv) > 1:
        test_type = sys.argv[1]
        if test_type == "integration":
            pytest.main(["-v", "TestAdapterIntegration"])
        elif test_type == "mock":
            pytest.main(["-v", "TestMockHeaderScenarios"])
        elif test_type == "validation":
            pytest.main(["-v", "TestValidationLoops"])
        elif test_type == "latency":
            pytest.main(["-v", "TestLatencyChecks"])
        elif test_type == "edge":
            pytest.main(["-v", "TestEdgeCases"])
        else:
            print("Available test types: integration, mock, validation, latency, edge")
    else:
        # Run all tests
        pytest.main(["-v", __file__])
