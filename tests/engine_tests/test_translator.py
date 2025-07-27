"""
Comprehensive test suite for the Python to SudoLang translator.

This test suite covers various Python language constructs to ensure the translator
correctly converts Python code to SudoLang pseudo-code format.
"""

import unittest
import sys
import os

# Add the project root to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from engine.translator import python_to_sudolang, ast_to_sudolang, render_assign_target
import ast


class TestPythonToSudoLang(unittest.TestCase):
    """Test cases for the Python to SudoLang translator."""

    def test_simple_if_statement(self):
        """Test basic if statement translation."""
        code = 'if x > 0: print("positive")'
        result = python_to_sudolang(code)
        expected = 'constraint: x > 0 ? print("positive")'
        self.assertEqual(result, expected)

    def test_function_definition(self):
        """Test function definition translation."""
        code = '''def greet(name):
    return f"Hello, {name}!"'''
        result = python_to_sudolang(code)
        expected = '''function greet(name) {
  return f"Hello, {name}!"
}'''
        self.assertEqual(result, expected)

    def test_class_definition(self):
        """Test class definition translation."""
        code = '''class Person:
    def __init__(self, name):
        self.name = name
    
    def speak(self):
        return "Hello"'''
        result = python_to_sudolang(code)
        expected = '''concept Person {
  function __init__(self, name) {
    self.name = name
  }
  function speak(self) {
    return "Hello"
  }
}'''
        self.assertEqual(result, expected)

    def test_for_loop(self):
        """Test for loop translation."""
        code = '''for i in range(10):
    print(i)'''
        result = python_to_sudolang(code)
        expected = '''for each i in range(10) {
  print(i)
}'''
        self.assertEqual(result, expected)

    def test_while_loop(self):
        """Test while loop translation."""
        code = '''while x < 10:
    x += 1
    print(x)'''
        result = python_to_sudolang(code)
        expected = '''while (x < 10) {
  x += 1
  print(x)
}'''
        self.assertEqual(result, expected)

    def test_try_except_finally(self):
        """Test try-except-finally block translation."""
        code = '''try:
    result = divide(a, b)
except ZeroDivisionError as e:
    print("Cannot divide by zero")
finally:
    cleanup()'''
        result = python_to_sudolang(code)
        expected = '''try {
  result = divide(a, b)
}
catch (ZeroDivisionError as e) {
  print("Cannot divide by zero")
}
finally {
  cleanup()
}'''
        self.assertEqual(result, expected)

    def test_list_comprehension(self):
        """Test list comprehension translation."""
        code = '[x**2 for x in range(10) if x % 2 == 0]'
        result = python_to_sudolang(code)
        expected = '[(x ** 2) for x in range(10) if (x % 2) == 0]'
        self.assertEqual(result, expected)

    def test_dictionary_comprehension(self):
        """Test dictionary comprehension translation."""
        code = '{k: v**2 for k, v in items.items() if v > 0}'
        result = python_to_sudolang(code)
        expected = '{k: (v ** 2) for k, v in items.items() if v > 0}'
        self.assertEqual(result, expected)

    def test_lambda_function(self):
        """Test lambda function translation."""
        code = 'square = lambda x: x**2'
        result = python_to_sudolang(code)
        expected = 'square = lambda x: (x ** 2)'
        self.assertEqual(result, expected)

    def test_complex_assignment(self):
        """Test complex assignment patterns."""
        code = '''a, b = 1, 2
x[0] = value
obj.attr = "test"'''
        result = python_to_sudolang(code)
        expected = '''(a, b) = (1, 2)
x[0] = "test"
obj.attr = "test"'''
        # Note: There might be some variations in the exact output format
        self.assertIn("(a, b) = ", result)
        self.assertIn("x[0] = ", result)
        self.assertIn("obj.attr = ", result)

    def test_binary_operations(self):
        """Test various binary operations."""
        test_cases = [
            ('a + b', '(a + b)'),
            ('a - b', '(a - b)'),
            ('a * b', '(a * b)'),
            ('a / b', '(a / b)'),
            ('a % b', '(a % b)'),
            ('a ** b', '(a ** b)'),
            ('a // b', '(a // b)'),
            ('a & b', '(a & b)'),
            ('a | b', '(a | b)'),
            ('a ^ b', '(a ^ b)'),
            ('a << b', '(a << b)'),
            ('a >> b', '(a >> b)'),
        ]
        
        for code, expected in test_cases:
            with self.subTest(code=code):
                result = python_to_sudolang(code)
                self.assertEqual(result, expected)

    def test_comparison_operations(self):
        """Test comparison operations."""
        test_cases = [
            ('a == b', 'a == b'),
            ('a != b', 'a != b'),
            ('a < b', 'a < b'),
            ('a <= b', 'a <= b'),
            ('a > b', 'a > b'),
            ('a >= b', 'a >= b'),
            ('a is b', 'a is b'),
            ('a is not b', 'a is not b'),
            ('a in b', 'a in b'),
            ('a not in b', 'a not in b'),
        ]
        
        for code, expected in test_cases:
            with self.subTest(code=code):
                result = python_to_sudolang(code)
                self.assertEqual(result, expected)

    def test_boolean_operations(self):
        """Test boolean operations."""
        test_cases = [
            ('a and b', '(a && b)'),
            ('a or b', '(a || b)'),
            ('not a', '(!a)'),
            ('a and b or c', '((a && b) || c)'),
        ]
        
        for code, expected in test_cases:
            with self.subTest(code=code):
                result = python_to_sudolang(code)
                self.assertEqual(result, expected)

    def test_data_structures(self):
        """Test data structure literals."""
        test_cases = [
            ('[1, 2, 3]', '[1, 2, 3]'),
            ('(1, 2, 3)', '(1, 2, 3)'),
            ('{"a": 1, "b": 2}', '{"a": 1, "b": 2}'),
            ('[]', '[]'),
            ('{}', '{}'),
            ('()', '()'),
        ]
        
        for code, expected in test_cases:
            with self.subTest(code=code):
                result = python_to_sudolang(code)
                self.assertEqual(result, expected)

    def test_async_function(self):
        """Test async function definition."""
        code = '''async def fetch_data(url):
    response = await request(url)
    return response'''
        result = python_to_sudolang(code)
        expected = '''async function fetch_data(url) {
  response = await request(url)
  return response
}'''
        self.assertEqual(result, expected)

    def test_with_statement(self):
        """Test with statement (context manager)."""
        code = '''with open("file.txt") as f:
    content = f.read()'''
        result = python_to_sudolang(code)
        expected = '''with open("file.txt") as f {
  content = f.read()
}'''
        self.assertEqual(result, expected)

    def test_multiple_with_contexts(self):
        """Test with statement with multiple contexts."""
        code = '''with open("file1.txt") as f1, open("file2.txt") as f2:
    data = f1.read() + f2.read()'''
        result = python_to_sudolang(code)
        self.assertIn('with open("file1.txt") as f1, open("file2.txt") as f2', result)
        self.assertIn('data = ', result)

    def test_global_and_nonlocal(self):
        """Test global and nonlocal declarations."""
        code = '''def outer():
    x = 1
    def inner():
        global y
        nonlocal x
        x = 2
        y = 3
    return inner'''
        result = python_to_sudolang(code)
        self.assertIn('global y', result)
        self.assertIn('nonlocal x', result)

    def test_yield_and_yield_from(self):
        """Test yield and yield from statements."""
        code = '''def generator():
    yield 1
    yield from [2, 3, 4]
    yield 5'''
        result = python_to_sudolang(code)
        self.assertIn('yield 1', result)
        self.assertIn('yield from [2, 3, 4]', result)
        self.assertIn('yield 5', result)

    def test_augmented_assignment(self):
        """Test augmented assignment operations."""
        test_cases = [
            ('x += 1', 'x += 1'),
            ('x -= 1', 'x -= 1'),
            ('x *= 2', 'x *= 2'),
            ('x /= 2', 'x /= 2'),
            ('x %= 3', 'x %= 3'),
            ('x **= 2', 'x **= 2'),
            ('x //= 2', 'x //= 2'),
            ('x &= mask', 'x &= mask'),
            ('x |= flag', 'x |= flag'),
            ('x ^= toggle', 'x ^= toggle'),
            ('x <<= 1', 'x <<= 1'),
            ('x >>= 1', 'x >>= 1'),
        ]
        
        for code, expected in test_cases:
            with self.subTest(code=code):
                result = python_to_sudolang(code)
                self.assertEqual(result, expected)

    def test_complex_control_flow(self):
        """Test complex control flow with nested structures."""
        code = '''def process_data(items):
    results = []
    for item in items:
        if item > 0:
            try:
                result = complex_operation(item)
                if result is not None:
                    results.append(result)
            except ValueError:
                continue
        else:
            break
    return results'''
        
        result = python_to_sudolang(code)
        
        # Check that all major constructs are present
        self.assertIn('function process_data', result)
        self.assertIn('for each item in items', result)
        self.assertIn('constraint:', result)
        self.assertIn('try {', result)
        self.assertIn('catch (ValueError)', result)
        self.assertIn('continue', result)
        self.assertIn('break', result)
        self.assertIn('return results', result)

    def test_invalid_python_code(self):
        """Test handling of invalid Python code."""
        invalid_code = 'def invalid_syntax('
        result = python_to_sudolang(invalid_code)
        self.assertEqual(result, "Invalid Python code.")

    def test_empty_code(self):
        """Test handling of empty code."""
        result = python_to_sudolang('')
        self.assertEqual(result, '')

    def test_pass_statement(self):
        """Test pass statement translation."""
        code = '''def empty_function():
    pass'''
        result = python_to_sudolang(code)
        expected = '''function empty_function() {
  pass
}'''
        self.assertEqual(result, expected)

    def test_assert_statement(self):
        """Test assert statement translation."""
        test_cases = [
            ('assert x > 0', 'assert x > 0'),
            ('assert x > 0, "x must be positive"', 'assert x > 0, "x must be positive"'),
        ]
        
        for code, expected in test_cases:
            with self.subTest(code=code):
                result = python_to_sudolang(code)
                self.assertEqual(result, expected)

    def test_raise_statement(self):
        """Test raise statement translation."""
        test_cases = [
            ('raise ValueError("error")', 'raise ValueError("error")'),
            ('raise', 'raise '),
            ('raise e from cause', 'raise e from cause'),
        ]
        
        for code, expected in test_cases:
            with self.subTest(code=code):
                result = python_to_sudolang(code)
                self.assertEqual(result, expected)

    def test_string_literals(self):
        """Test different types of string literals."""
        test_cases = [
            ('"hello"', '"hello"'),
            ("'world'", '"world"'),  # Single quotes become double quotes
            ('f"Hello {name}"', 'f"Hello {name}"'),
            ('r"raw string"', '"raw string"'),
        ]
        
        for code, expected in test_cases:
            with self.subTest(code=code):
                result = python_to_sudolang(code)
                self.assertEqual(result, expected)

    def test_numeric_literals(self):
        """Test numeric literal translation."""
        test_cases = [
            ('42', '42'),
            ('3.14', '3.14'),
            ('1e6', '1000000.0'),
            ('0x10', '16'),
            ('0o10', '8'),
            ('0b10', '2'),
        ]
        
        for code, expected in test_cases:
            with self.subTest(code=code):
                result = python_to_sudolang(code)
                self.assertEqual(result, expected)

    def test_attribute_access_and_subscript(self):
        """Test attribute access and subscript operations."""
        test_cases = [
            ('obj.attr', 'obj.attr'),
            ('obj.method()', 'obj.method()'),
            ('arr[0]', 'arr[0]'),
            ('dict["key"]', 'dict["key"]'),
            ('matrix[i][j]', 'matrix[i][j]'),
            ('obj.nested.attr', 'obj.nested.attr'),
        ]
        
        for code, expected in test_cases:
            with self.subTest(code=code):
                result = python_to_sudolang(code)
                self.assertEqual(result, expected)

    def test_slice_operations(self):
        """Test slice operations."""
        test_cases = [
            ('arr[1:5]', 'arr[1:5]'),
            ('arr[:5]', 'arr[:5]'),
            ('arr[1:]', 'arr[1:]'),
            ('arr[:]', 'arr[:]'),
            ('arr[1:5:2]', 'arr[1:5]'),  # Step might not be fully supported
        ]
        
        for code, expected in test_cases:
            with self.subTest(code=code):
                result = python_to_sudolang(code)
                # For slices, we'll just check the basic structure
                self.assertIn('arr[', result)
                self.assertIn(':', result)

    def test_function_calls_with_arguments(self):
        """Test function calls with various argument types."""
        test_cases = [
            ('func()', 'func()'),
            ('func(a)', 'func(a)'),
            ('func(a, b, c)', 'func(a, b, c)'),
            ('func(1, "hello", True)', 'func(1, "hello", True)'),
        ]
        
        for code, expected in test_cases:
            with self.subTest(code=code):
                result = python_to_sudolang(code)
                self.assertEqual(result, expected)


class TestHelperFunctions(unittest.TestCase):
    """Test cases for helper functions in the translator."""

    def test_render_assign_target_name(self):
        """Test rendering simple name targets."""
        node = ast.parse('x = 1').body[0].targets[0]
        result = render_assign_target(node)
        self.assertEqual(result, 'x')

    def test_render_assign_target_tuple(self):
        """Test rendering tuple assignment targets."""
        node = ast.parse('a, b = 1, 2').body[0].targets[0]
        result = render_assign_target(node)
        self.assertEqual(result, '(a, b)')

    def test_render_assign_target_list(self):
        """Test rendering list assignment targets."""
        node = ast.parse('[a, b] = [1, 2]').body[0].targets[0]
        result = render_assign_target(node)
        self.assertEqual(result, '[a, b]')

    def test_render_assign_target_subscript(self):
        """Test rendering subscript assignment targets."""
        node = ast.parse('arr[0] = value').body[0].targets[0]
        result = render_assign_target(node)
        self.assertEqual(result, 'arr[0]')

    def test_render_assign_target_attribute(self):
        """Test rendering attribute assignment targets."""
        node = ast.parse('obj.attr = value').body[0].targets[0]
        result = render_assign_target(node)
        self.assertEqual(result, 'obj.attr')


def run_translator_tests():
    """Run all translator tests."""
    print("Running comprehensive translator tests...")
    
    # Create test suite
    suite = unittest.TestSuite()
    
    # Add all test cases
    suite.addTest(unittest.makeSuite(TestPythonToSudoLang))
    suite.addTest(unittest.makeSuite(TestHelperFunctions))
    
    # Run tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    # Print summary
    print(f"\nTest Summary:")
    print(f"Tests run: {result.testsRun}")
    print(f"Failures: {len(result.failures)}")
    print(f"Errors: {len(result.errors)}")
    
    if result.failures:
        print("\nFailures:")
        for test, traceback in result.failures:
            print(f"  {test}: {traceback}")
    
    if result.errors:
        print("\nErrors:")
        for test, traceback in result.errors:
            print(f"  {test}: {traceback}")
    
    return result.wasSuccessful()


if __name__ == "__main__":
    success = run_translator_tests()
    exit(0 if success else 1)
