"""
Comprehensive test suite for the Python minifier.

Tests cover:
- Basic functionality
- Aggressive mode
- Edge cases and regressions
- Idempotency
- Semantic preservation
- Error handling
"""

import unittest
import sys
import ast
from pathlib import Path

# Add the project root to the path for absolute imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from input_optimizer.engine.minifier import (
    minify_code, minify_basic, minify_aggressive,
    minify_with_stats, estimate_tokens, is_idempotent
)


class TestMinifierBasic(unittest.TestCase):
    """Test basic minification functionality."""
    
    def test_simple_function(self):
        """Test minification of a simple function."""
        code = """
def hello():
    # This is a comment
    return "Hello World"
"""
        result = minify_basic(code)
        self.assertIn("def hello():", result)
        # Accept either single or double quotes after minification
        self.assertTrue('return "Hello World"' in result or "return 'Hello World'" in result)
        self.assertNotIn("# This is a comment", result)
    
    def test_docstring_preservation(self):
        """Test that docstrings are preserved correctly."""
        code = '''
def func():
    """This docstring should be kept."""
    """This string should be removed."""
    return 42
'''
        result = minify_basic(code)
        self.assertIn('"""This docstring should be kept."""', result)
        self.assertNotIn('"""This string should be removed."""', result)
    
    def test_class_docstring(self):
        """Test class docstring preservation."""
        code = '''
class MyClass:
    """Class docstring."""
    
    def method(self):
        """Method docstring."""
        pass
'''
        result = minify_basic(code)
        self.assertIn('"""Class docstring."""', result)
        self.assertIn('"""Method docstring."""', result)
    
    def test_empty_function(self):
        """Test that empty functions get a pass statement."""
        code = """
def empty():
    pass
"""
        result = minify_basic(code)
        self.assertIn("pass", result)
    
    def test_constant_folding(self):
        """Test constant folding optimizations."""
        test_cases = [
            ("x = 1 + 2", "x = 3"),
            ("y = 2 * 3", "y = 6"),
            ("z = not False", "z = True"),
            ("w = --5", "w = 5"),
        ]
        
        for input_code, expected in test_cases:
            with self.subTest(input=input_code):
                result = minify_basic(input_code)
                self.assertIn(expected, result)
    
    def test_dead_code_removal(self):
        """Test removal of unreachable code."""
        code = '''
def func():
    if True:
        return 1
        print("unreachable")
    return 2
'''
        result = minify_basic(code)
        self.assertNotIn("unreachable", result)
        self.assertNotIn("return 2", result)
    
    def test_boolean_optimization(self):
        """Test boolean expression optimizations."""
        test_cases = [
            ("x = True and y", "x = y"),
            ("x = False or y", "x = y"),
            ("x = y and True", "x = y"),
            ("x = y or False", "x = y"),
        ]
        
        for input_code, expected in test_cases:
            with self.subTest(input=input_code):
                result = minify_basic(input_code)
                self.assertIn(expected, result)


class TestMinifierAggressive(unittest.TestCase):
    """Test aggressive minification mode."""
    
    def test_variable_shortening(self):
        """Test that variables are shortened in aggressive mode."""
        code = '''
def long_function_name(parameter_name):
    local_variable = parameter_name + 1
    return local_variable
'''
        result = minify_aggressive(code)
        
        # Should have short variable names
        self.assertRegex(result, r'\b[a-z]\b')  # Should contain single letter variables
        # Should still be valid Python
        ast.parse(result)
    
    def test_builtin_preservation(self):
        """Test that built-in names are not shortened."""
        code = '''
def func():
    result = len([1, 2, 3])
    return str(result)
'''
        result = minify_aggressive(code)
        self.assertIn("len", result)
        self.assertIn("str", result)
    
    def test_parameter_shortening(self):
        """Test that function parameters are shortened."""
        code = '''
def calculate(first_number, second_number):
    return first_number + second_number
'''
        result = minify_aggressive(code)
        
        # Parameters should be shortened
        self.assertNotIn("first_number", result)
        self.assertNotIn("second_number", result)
        
        # Should still parse correctly
        ast.parse(result)


class TestMinifierEdgeCases(unittest.TestCase):
    """Test edge cases and regression scenarios."""
    
    def test_empty_code(self):
        """Test handling of empty code."""
        result = minify_basic("")
        self.assertEqual(result.strip(), "")
    
    def test_only_comments(self):
        """Test code with only comments."""
        code = """
# Just a comment
# Another comment
"""
        result = minify_basic(code)
        self.assertEqual(result.strip(), "")
    
    def test_nested_functions(self):
        """Test nested function definitions."""
        code = '''
def outer():
    """Outer docstring."""
    def inner():
        """Inner docstring."""
        return 42
    return inner
'''
        result = minify_basic(code)
        self.assertIn('"""Outer docstring."""', result)
        self.assertIn('"""Inner docstring."""', result)
        
        # Should still be valid
        ast.parse(result)
    
    def test_complex_expressions(self):
        """Test complex mathematical expressions."""
        code = "result = (1 + 2) * (3 + 4) - 5"
        result = minify_basic(code)
        # Should fold to: result = 3 * 7 - 5 = 21 - 5 = 16
        self.assertIn("result = 16", result)
    
    def test_string_operations(self):
        """Test string constant operations."""
        code = '''x = "hello" + " " + "world"'''
        result = minify_basic(code)
        # Accept either single or double quotes after minification
        self.assertTrue('x = "hello world"' in result or "x = 'hello world'" in result)
    
    def test_comparison_folding(self):
        """Test comparison operation folding."""
        test_cases = [
            ("x = 1 < 2", "x = True"),
            ("y = 5 > 10", "y = False"),
            ("z = 'a' == 'a'", "z = True"),
        ]
        
        for input_code, expected in test_cases:
            with self.subTest(input=input_code):
                result = minify_basic(input_code)
                self.assertIn(expected, result)


class TestMinifierIdempotency(unittest.TestCase):
    """Test that minification is idempotent."""
    
    def test_basic_idempotency(self):
        """Test that minify(minify(code)) == minify(code)."""
        code = '''
def func(param):
    """Docstring."""
    # Comment
    x = 1 + 2
    return x
'''
        self.assertTrue(is_idempotent(code, aggressive=False))
    
    def test_aggressive_idempotency(self):
        """Test idempotency in aggressive mode."""
        code = '''
def calculate(first_value, second_value):
    intermediate_result = first_value + second_value
    return intermediate_result
'''
        self.assertTrue(is_idempotent(code, aggressive=True))
    
    def test_complex_idempotency(self):
        """Test idempotency with complex code structures."""
        code = '''
class Calculator:
    """A simple calculator."""
    
    def __init__(self):
        self.memory = 0
    
    def add(self, value):
        """Add a value."""
        self.memory += value
        return self.memory
    
    def reset(self):
        """Reset memory."""
        self.memory = 0
'''
        self.assertTrue(is_idempotent(code, aggressive=False))
        self.assertTrue(is_idempotent(code, aggressive=True))


class TestMinifierStats(unittest.TestCase):
    """Test statistics and token estimation."""
    
    def test_minify_with_stats(self):
        """Test that stats are correctly calculated."""
        code = '''
def hello_world():
    """Say hello to the world."""
    # This is a comment
    message = "Hello, " + "World!"
    return message
'''
        minified, stats = minify_with_stats(code)
        
        # Check that stats are present and reasonable
        self.assertIn("original_size", stats)
        self.assertIn("minified_size", stats)
        self.assertIn("size_reduction_percent", stats)
        self.assertIn("token_reduction_percent", stats)
        
        # Minified should be smaller
        self.assertLess(stats["minified_size"], stats["original_size"])
        self.assertGreater(stats["size_reduction_percent"], 0)
    
    def test_token_estimation(self):
        """Test token estimation methods."""
        code = "def hello(): return 'world'"
        
        simple_tokens = estimate_tokens(code, "simple")
        words_tokens = estimate_tokens(code, "words")
        chars_tokens = estimate_tokens(code, "chars")
        
        # All should return positive integers
        self.assertIsInstance(simple_tokens, int)
        self.assertIsInstance(words_tokens, int)
        self.assertIsInstance(chars_tokens, int)
        self.assertGreater(simple_tokens, 0)
        self.assertGreater(words_tokens, 0)
        self.assertGreater(chars_tokens, 0)


class TestMinifierErrorHandling(unittest.TestCase):
    """Test error handling and validation."""
    
    def test_invalid_syntax(self):
        """Test handling of invalid Python syntax."""
        invalid_code = "def func(:\n    pass"
        
        with self.assertRaises(SyntaxError):
            minify_basic(invalid_code)
    
    def test_validation_enabled(self):
        """Test that validation catches problems."""
        # This should work normally
        valid_code = "x = 1"
        result = minify_code(valid_code, validate=True)
        self.assertEqual(result.strip(), "x = 1")
    
    def test_validation_disabled(self):
        """Test that validation can be disabled."""
        valid_code = "x = 1"
        result = minify_code(valid_code, validate=False)
        self.assertEqual(result.strip(), "x = 1")


class TestSemanticPreservation(unittest.TestCase):
    """Test that minified code preserves semantic meaning."""
    
    def test_function_execution(self):
        """Test that functions execute the same way."""
        code = '''
def factorial(n):
    """Calculate factorial."""
    if n <= 1:
        return 1
    return n * factorial(n - 1)

result = factorial(5)
'''
        
        # Execute original
        original_globals = {}
        exec(code, original_globals)
        original_result = original_globals['result']
        
        # Execute minified
        minified = minify_basic(code)
        minified_globals = {}
        exec(minified, minified_globals)
        minified_result = minified_globals['result']
        
        self.assertEqual(original_result, minified_result)
    
    def test_class_behavior(self):
        """Test that classes behave the same way."""
        code = '''
class Counter:
    """A simple counter."""
    
    def __init__(self, start=0):
        self.value = start
    
    def increment(self):
        """Increment the counter."""
        self.value += 1
        return self.value

counter = Counter(10)
counter.increment()
counter.increment()
result = counter.value
'''
        
        # Execute original
        original_globals = {}
        exec(code, original_globals)
        original_result = original_globals['result']
        
        # Execute minified
        minified = minify_basic(code)
        minified_globals = {}
        exec(minified, minified_globals)
        minified_result = minified_globals['result']
        
        self.assertEqual(original_result, minified_result)


if __name__ == "__main__":
    # Run all tests
    unittest.main(verbosity=2)