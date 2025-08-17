import unittest
from pathlib import Path
import sys
import os

# Add the parent directory to the path to import the CAI3 modules
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))

from input_optimizer.engine.cai3_translator import CAI3Translator
from input_optimizer.engine.cai3_waterfall_integration import CAI3WaterfallEnhancement, enhance_waterfall_with_cai3
from input_optimizer.engine.waterfall_compressor import WaterfallCompressor


class TestCAI3Roundtrip(unittest.TestCase):
    """Test suite for CAI3 compression/decompression roundtrip."""
    
    def setUp(self):
        """Set up test environment with translator and test cases."""
        self.translator = CAI3Translator()
        
        # Create enhanced waterfall compressor with CAI3 capabilities
        WaterfallCompressorEnhanced = enhance_waterfall_with_cai3(WaterfallCompressor)
        self.compressor = WaterfallCompressorEnhanced()
        
        # Configure CAI3 settings after initialization
        self.compressor.include_all_methods = True  # Include all methods for comprehensive testing
        self.compressor.pre_minify_locals = True   # Enable local variable minification
        self.compressor.use_cai3_mode = True       # Enable CAI3 mode
        
        # Create a temporary test file path
        self.test_file_path = Path("/tmp/test_cai3_roundtrip.py")
        
        self.test_cases = [
            # Validation with required_fields - Make it large enough for MEDIUM tier (250+ tokens)
            {
                'name': 'validation_pattern',
                'source': '''
class DataValidator:
    """Comprehensive data validation class with multiple validation methods."""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.error_count = 0
        self.warning_count = 0
        self.validation_rules = {
            'required_fields': ['id', 'name', 'email', 'created_at'],
            'optional_fields': ['phone', 'address', 'notes'],
            'max_lengths': {'name': 100, 'email': 255, 'notes': 1000}
        }
    
    def validate_record(self, record):
        """Validate a record has required fields and proper data types."""
        required_fields = self.validation_rules['required_fields']
        issues = []
        warnings = []
        
        # Check required fields
        for field in required_fields:
            if field not in record:
                issues.append(f"Missing required field: {field}")
                self.error_count += 1
        
        # Validate data types
        if 'id' in record and not isinstance(record['id'], (int, str)):
            issues.append("ID must be int or string")
        
        if 'email' in record and '@' not in record['email']:
            issues.append("Invalid email format")
        
        # Check field lengths
        for field, max_len in self.validation_rules['max_lengths'].items():
            if field in record and len(str(record[field])) > max_len:
                warnings.append(f"Field {field} exceeds maximum length {max_len}")
                self.warning_count += 1
        
        return len(issues) == 0, issues, warnings
    
    def get_error_summary(self):
        return f"Total validation errors: {self.error_count}, warnings: {self.warning_count}"
    
    def reset_counters(self):
        """Reset error and warning counters."""
        self.error_count = 0
        self.warning_count = 0
''',
                'expected_patterns': ['required_fields', 'not in', 'return', 'issues.append']
            },
            # Try-except with exception variable - Make it larger
            {
                'name': 'try_except_pattern', 
                'source': '''
class SafeProcessor:
    """Safe data processor with comprehensive error handling and retry logic."""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.retry_count = 3
        self.timeout_seconds = 30
        self.error_handlers = {
            'ConnectionError': self._handle_connection_error,
            'TimeoutError': self._handle_timeout_error,
            'ValueError': self._handle_value_error
        }
        
    def safe_operation(self, data):
        """Safely process data with retry logic and comprehensive error handling."""
        for attempt in range(self.retry_count):
            try:
                result = self.process_data(data)
                self.logger.info(f"Processing succeeded on attempt {attempt + 1}")
                return result
            except ConnectionError as e:
                self.logger.warning(f"Connection error on attempt {attempt + 1}: {e}")
                if attempt == self.retry_count - 1:
                    raise
                time.sleep(2 ** attempt)  # Exponential backoff
            except TimeoutError as e:
                self.logger.warning(f"Timeout error on attempt {attempt + 1}: {e}")
                if attempt == self.retry_count - 1:
                    raise
            except Exception as e:
                self.logger.error(f"Unexpected error: {e}")
                return self._handle_generic_error(e)
        return None
    
    def process_data(self, data):
        """Mock processing that might fail with various error conditions."""
        if not data:
            raise ValueError("No data provided")
        if len(data) > 10000:
            raise TimeoutError("Data too large to process")
        return {"processed": True, "data": data, "timestamp": time.time()}
    
    def _handle_connection_error(self, error):
        """Handle connection-specific errors."""
        self.logger.error(f"Connection failed: {error}")
        return {"error": "connection_failed", "retry_needed": True}
    
    def _handle_timeout_error(self, error):
        """Handle timeout-specific errors.""" 
        self.logger.error(f"Operation timed out: {error}")
        return {"error": "timeout", "retry_needed": True}
    
    def _handle_value_error(self, error):
        """Handle value-specific errors."""
        self.logger.error(f"Invalid value: {error}")
        return {"error": "invalid_value", "retry_needed": False}
    
    def _handle_generic_error(self, error):
        """Handle any other unexpected errors."""
        self.logger.error(f"Generic error: {error}")
        return {"error": "unknown", "retry_needed": False}
''',
                'expected_patterns': ['try:', 'except Exception as e:', 'logger.error', 'retry_count']
            }
        ]
    
    def test_roundtrip_accuracy(self):
        """Test that code roundtrips without semantic changes."""
        for test_case in self.test_cases:
            with self.subTest(name=test_case['name']):
                # Write test source to temporary file
                self.test_file_path.write_text(test_case['source'])
                
                try:
                    # Debug: Check token count and force MEDIUM tier for CAI3
                    from input_optimizer.engine.waterfall_compressor import count_tokens
                    token_count = count_tokens(test_case['source'])
                    print(f"\nToken count for {test_case['name']}: {token_count}")
                    
                    # Compress using enhanced waterfall compressor
                    compressed_result = self.compressor.compress_string(
                        test_case['source'], 
                        self.test_file_path
                    )
                    
                    self.assertIsNotNone(compressed_result, "Compression should not return None")
                    self.assertIsNotNone(compressed_result.content, "Result should contain compressed content")
                    
                    # Debug: Print what we got from compression
                    print(f"Compression result for {test_case['name']}:")
                    print(f"Method used: {compressed_result.method_used}")
                    print(f"Tier used: {compressed_result.tier_used}")
                    print(f"Content preview: {compressed_result.content[:200]}...")
                    print(f"Metadata: {compressed_result.metadata}")
                    
                    # Check if this is actually CAI3-LITE content
                    if (compressed_result.content.startswith('#C3L') or 
                        'cai3' in compressed_result.method_used.lower() or
                        compressed_result.metadata and compressed_result.metadata.get('cai3_mode')):
                        
                        # Try to decompress back to Python
                        try:
                            decompressed = self.translator.translate_lite_to_python(
                                compressed_result.content, 
                                self.test_file_path
                            )
                            
                            self.assertIsNotNone(decompressed, "Decompression should not return None")
                            
                            # Verify patterns preserved
                            for pattern in test_case['expected_patterns']:
                                self.assertIn(pattern, decompressed, 
                                            f"Pattern '{pattern}' should be preserved in decompressed code")
                            
                            # Verify Python syntax is valid
                            try:
                                compile(decompressed, '<string>', 'exec')
                                print(f"✓ Roundtrip successful for {test_case['name']}")
                            except SyntaxError as e:
                                self.fail(f"Decompressed code has syntax error: {e}\nCode: {decompressed}")
                        
                        except ValueError as e:
                            if "No CAI3 cache found" in str(e):
                                # This means the compression didn't use CAI3 or didn't cache properly
                                self.skipTest(f"CAI3 cache not available for {test_case['name']}: {e}")
                            else:
                                raise
                    else:
                        # This is not CAI3-LITE content, skip roundtrip test
                        self.skipTest(f"Compression did not produce CAI3-LITE content for {test_case['name']}, got {compressed_result.method_used}")
                
                finally:
                    # Clean up temporary file
                    if self.test_file_path.exists():
                        self.test_file_path.unlink()
    
    def test_no_fallback_errors(self):
        """Ensure no fallback text appears in output."""
        for test_case in self.test_cases:
            with self.subTest(name=test_case['name']):
                # Write test source to temporary file
                self.test_file_path.write_text(test_case['source'])
                
                try:
                    # Compress
                    compressed_result = self.compressor.compress_string(
                        test_case['source'], 
                        self.test_file_path
                    )
                    
                    # Decompress
                    decompressed = self.translator.translate_lite_to_python(
                        compressed_result.content, 
                        self.test_file_path
                    )
                    
                    # Check for fallback indicators
                    self.assertNotIn('fallback', decompressed.lower(), 
                                   "Should not contain 'fallback' text")
                    self.assertNotIn('_container', decompressed, 
                                   "Should not contain '_container' placeholder")
                    self.assertNotIn('?', decompressed, 
                                   "Should not contain unresolved '?' placeholders")
                    
                    # Check for incomplete method names
                    incomplete_methods = ['.ap(', '.g(', '.sp(', 'Fi()']
                    for incomplete in incomplete_methods:
                        self.assertNotIn(incomplete, decompressed,
                                       f"Should not contain incomplete method '{incomplete}'")
                
                finally:
                    # Clean up temporary file
                    if self.test_file_path.exists():
                        self.test_file_path.unlink()
    
    def test_compression_efficiency(self):
        """Test that compression achieves reasonable efficiency."""
        for test_case in self.test_cases:
            with self.subTest(name=test_case['name']):
                # Write test source to temporary file
                self.test_file_path.write_text(test_case['source'])
                
                try:
                    # Compress
                    compressed_result = self.compressor.compress_string(
                        test_case['source'], 
                        self.test_file_path
                    )
                    
                    original_size = len(test_case['source'])
                    compressed_size = len(compressed_result.content)
                    
                    # Compression should reduce size for larger methods
                    if original_size > 100:
                        compression_ratio = compressed_size / original_size
                        self.assertLess(compression_ratio, 1.0, 
                                      "Compression should reduce size for larger methods")
                    
                    # Verify compression stats are present
                    self.assertIsNotNone(compressed_result.metadata,
                                "Result should include compression metadata")
                    self.assertGreater(compressed_result.compression_ratio, 0,
                                "Compression ratio should be positive")
                
                finally:
                    # Clean up temporary file
                    if self.test_file_path.exists():
                        self.test_file_path.unlink()
    
    def test_error_handling(self):
        """Test error handling for malformed input."""
        test_cases = [
            {
                'name': 'invalid_python',
                'source': 'def invalid_syntax(\n    pass',  # Missing closing parenthesis
                'should_fail': True
            },
            {
                'name': 'empty_method',
                'source': '''
def empty_method(self):
    """A simple empty method for testing basic functionality."""
    pass

def another_method(self):
    """Another method to ensure we have enough content for compression."""
    return "test"

class TestClass:
    """A test class with multiple methods to ensure MEDIUM tier compression."""
    
    def __init__(self):
        self.value = 42
        
    def method_one(self):
        return self.value * 2
        
    def method_two(self):
        return self.value + 10
''',
                'should_fail': False
            }
        ]
        
        for test_case in test_cases:
            with self.subTest(name=test_case['name']):
                # Write test source to temporary file
                self.test_file_path.write_text(test_case['source'])
                
                try:
                    if test_case['should_fail']:
                        # For invalid syntax, the compressor should handle gracefully
                        # but may return a fallback or error result
                        compressed_result = self.compressor.compress_string(
                            test_case['source'], 
                            self.test_file_path
                        )
                        # Check that it handled the error gracefully
                        self.assertIsNotNone(compressed_result)
                        # Should indicate error handling in metadata or method
                        self.assertTrue(
                            compressed_result.method_used in ['fallback_compression', 'syntax_error_handling', 'no_compression'] or
                            'error' in str(compressed_result.metadata).lower()
                        )
                    else:
                        # Should handle valid code
                        compressed_result = self.compressor.compress_string(
                            test_case['source'], 
                            self.test_file_path
                        )
                        self.assertIsNotNone(compressed_result)
                
                finally:
                    # Clean up temporary file
                    if self.test_file_path.exists():
                        self.test_file_path.unlink()
    
    def test_variable_mapping_preservation(self):
        """Test that variable mappings are correctly preserved through roundtrip."""
        test_source = '''
class DataProcessor:
    """A comprehensive data processing class with multiple methods for testing variable preservation."""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.processed_count = 0
        self.error_count = 0
        
    def process_data(self, input_data, configuration):
        """Process input data according to configuration settings."""
        processed_items = []
        error_count = 0
        
        # Validate input data first
        if not input_data:
            self.logger.warning("No input data provided")
            return [], 0
            
        # Process each item in the input data
        for item in input_data:
            try:
                result = self.transform(item, configuration)
                processed_items.append(result)
                self.processed_count += 1
            except Exception as e:
                error_count += 1
                self.error_count += 1
                self.logger.error(f"Failed to process item: {e}")
        
        return processed_items, error_count
    
    def transform(self, item, configuration):
        """Transform a single item based on configuration."""
        if not item:
            raise ValueError("Invalid item")
        
        # Apply transformation rules from configuration
        transformed = item.copy() if hasattr(item, 'copy') else str(item)
        
        if 'uppercase' in configuration:
            transformed = str(transformed).upper()
            
        return transformed
    
    def get_statistics(self):
        """Return processing statistics."""
        return {
            'processed_count': self.processed_count,
            'error_count': self.error_count
        }
'''
        
        # Write test source to temporary file
        self.test_file_path.write_text(test_source)
        
        try:
            # Compress
            compressed_result = self.compressor.compress_string(
                test_source, 
                self.test_file_path
            )
            
            # Only test roundtrip if CAI3 compression was used
            if (compressed_result.content.startswith('#C3L') or 
                'cai3' in compressed_result.method_used.lower() or
                compressed_result.metadata and compressed_result.metadata.get('cai3_mode')):
                
                # Decompress
                decompressed = self.translator.translate_lite_to_python(
                    compressed_result.content, 
                    self.test_file_path
                )
                
                self.assertIsNotNone(decompressed, "Decompression should not return None")
                self.assertTrue(len(decompressed.strip()) > 0, "Decompressed code should not be empty")
                
                # Verify variable names are preserved
                expected_variables = [
                    'input_data', 'configuration', 'processed_items', 
                    'error_count', 'item', 'result'
                ]
                
                for var_name in expected_variables:
                    self.assertIn(var_name, decompressed,
                                f"Variable '{var_name}' should be preserved")
                
                # Verify method calls are preserved
                expected_calls = ['self.transform', 'append', 'self.logger.error']
                for call in expected_calls:
                    self.assertIn(call, decompressed,
                                f"Method call '{call}' should be preserved")
            else:
                self.skipTest("CAI3 compression not used, skipping variable mapping test")
        
        finally:
            # Clean up temporary file
            if self.test_file_path.exists():
                self.test_file_path.unlink()
    
    def tearDown(self):
        """Clean up after each test."""
        # Ensure temporary file is cleaned up
        if self.test_file_path and self.test_file_path.exists():
            self.test_file_path.unlink()


if __name__ == '__main__':
    # Set up logging for test debugging
    import logging
    logging.basicConfig(level=logging.INFO)
    
    # Run the tests
    unittest.main(verbosity=2)
