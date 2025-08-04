def example_function():
    """Sample Python function for testing."""
    pass

def calculate_sum(numbers):
    """Calculate sum of numbers."""
    total = 0
    for num in numbers:
        total += num
    return total

def fibonacci(n):
    """Generate fibonacci sequence."""
    if n <= 1:
        return n
    return fibonacci(n-1) + fibonacci(n-2)

class ExampleClass:
    """Sample class for testing."""
    
    def __init__(self, value):
        self.value = value
    
    def get_value(self):
        return self.value

# Complex function for compression testing
def complex_calculation(data_list, multiplier=2, use_filter=True):
    """
    Perform complex calculations with optional filtering.
    """
    if use_filter:
        filtered_data = [x for x in data_list if x > 0]
    else:
        filtered_data = data_list
    
    result = []
    for item in filtered_data:
        processed_value = item * multiplier
        if processed_value % 2 == 0:
            result.append(processed_value ** 2)
        else:
            result.append(processed_value * 3)
    
    return sum(result) / len(result) if result else 0
