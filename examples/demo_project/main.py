"""
Demo project main module
"""
def calculate(x, y):
    """Simple calculation function for demo purposes."""
    return x * y + 10

def process_list(items):
    """Process a list of items."""
    results = []
    for item in items:
        if item > 0:
            results.append(calculate(item, 2))
    return results

class Calculator:
    """Simple calculator class."""
    
    def __init__(self, multiplier=1):
        self.multiplier = multiplier
    
    def multiply(self, a, b):
        return a * b * self.multiplier
    
    def divide(self, a, b):
        if b == 0:
            raise ValueError("Cannot divide by zero")
        return a / b

if __name__ == "__main__":
    calc = Calculator(2)
    print(f"2 * 3 = {calc.multiply(2, 3)}")
    print(f"10 / 2 = {calc.divide(10, 2)}")
    print(f"Process [1, 2, 3]: {process_list([1, 2, 3])}")
