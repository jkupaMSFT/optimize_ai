# Python to SudoLang Translator Test Suite

This comprehensive test suite validates the functionality and quality of the Python to SudoLang translator (`engine/translator.py`).

## Test Coverage

The test suite includes **36 test cases** covering a wide range of Python language constructs and edge cases:

### Core Language Features

1. **Basic Statements**

   - Simple if statements
   - Function definitions
   - Class definitions
   - Pass statements

2. **Control Flow**

   - If-elif-else statements
   - For loops
   - While loops
   - Try-except-finally blocks
   - With statements (context managers)

3. **Expressions**

   - Binary operations (+, -, \*, /, %, \*\*, //, &, |, ^, <<, >>)
   - Comparison operations (==, !=, <, <=, >, >=, is, is not, in, not in)
   - Boolean operations (and, or, not)
   - Unary operations (+, -, ~, not)

4. **Data Structures**

   - Lists: `[1, 2, 3]`
   - Tuples: `(1, 2, 3)`
   - Dictionaries: `{"a": 1, "b": 2}`
   - Sets (basic support)

5. **Advanced Features**

   - List comprehensions: `[x**2 for x in range(10) if x % 2 == 0]`
   - Dictionary comprehensions: `{k: v**2 for k, v in items.items() if v > 0}`
   - Lambda functions: `lambda x: x**2`
   - Generator expressions
   - F-strings: `f"Hello {name}"`

6. **Assignment Patterns**

   - Simple assignment: `x = 1`
   - Tuple unpacking: `a, b = 1, 2`
   - List unpacking: `[a, b] = [1, 2]`
   - Subscript assignment: `arr[0] = value`
   - Attribute assignment: `obj.attr = value`
   - Augmented assignment: `x += 1`, `x *= 2`, etc.

7. **Function Features**

   - Regular functions
   - Async functions
   - Function calls with arguments
   - Method calls and attribute access

8. **Exception Handling**

   - Try-except blocks
   - Multiple exception handlers
   - Finally clauses
   - Assert statements
   - Raise statements

9. **Literals and Constants**

   - Numeric literals (integers, floats, hex, octal, binary)
   - String literals (single quotes, double quotes, f-strings, raw strings)
   - Boolean constants (True, False, None)

10. **Advanced Constructs**
    - Global and nonlocal declarations
    - Yield and yield from statements
    - With statements with multiple contexts
    - Slice operations
    - Complex nested structures

### Edge Cases and Error Handling

- Empty code handling
- Invalid Python syntax handling
- Unsupported AST node types
- Complex nested control flow

## Test Structure

### Main Test Classes

1. **TestPythonToSudoLang**: Tests the main translation functionality
2. **TestHelperFunctions**: Tests helper functions like `render_assign_target`

### Key Test Methods

- `test_simple_if_statement()`: Basic conditional logic
- `test_function_definition()`: Function declarations
- `test_class_definition()`: Class definitions with methods
- `test_complex_control_flow()`: Nested loops, conditionals, and exception handling
- `test_list_comprehension()`: Advanced list comprehensions
- `test_async_function()`: Async/await functionality
- `test_string_literals()`: Various string formats including f-strings

## Running the Tests

```bash
# Run the complete test suite
python tests/engine_tests/test_translator.py

# Run with verbose output
python -m unittest tests.engine_tests.test_translator -v

# Run specific test class
python -m unittest tests.engine_tests.test_translator.TestPythonToSudoLang -v
```

## Test Results Summary

- **Total Tests**: 36
- **Pass Rate**: 100%
- **Coverage**: Comprehensive coverage of Python AST node types
- **Compatibility**: Python 3.7+ (includes legacy AST node support)

## Translator Quality Validation

The test suite validates:

1. **Correctness**: Proper translation of Python constructs to SudoLang syntax
2. **Completeness**: Coverage of major Python language features
3. **Edge Cases**: Handling of malformed input and unusual constructs
4. **Consistency**: Uniform formatting and style across translations
5. **Error Handling**: Graceful failure for invalid input

## SudoLang Output Examples

### Basic Translation

```python
# Input
if x > 0: print("positive")

# Output
constraint: x > 0 ? print("positive")
```

### Function Translation

```python
# Input
def greet(name):
    return f"Hello, {name}!"

# Output
function greet(name) {
  return f"Hello, {name}!"
}
```

### Class Translation

```python
# Input
class Person:
    def __init__(self, name):
        self.name = name

# Output
concept Person {
  function __init__(self, name) {
    self.name = name
  }
}
```

### Loop Translation

```python
# Input
for item in items:
    process(item)

# Output
for each item in items {
  process(item)
}
```

## Maintenance

This test suite should be updated when:

- New Python language features are added to the translator
- SudoLang syntax changes
- Bug fixes are implemented
- Performance optimizations are made

The comprehensive nature of these tests ensures that any changes to the translator maintain backward compatibility and correct functionality.
