# 1. Simple function with docstring
sample1 = """def calculate_area(radius):
    #Calculate the area of a circle given its radius.
    import math
    return math.pi * radius ** 2"""


# 2. List comprehension with conditional
sample2 = """def filter_even_squares(numbers):
    return [x**2 for x in numbers if x % 2 == 0 and x > 0]"""


# 3. Class with properties and f-strings
sample3 = """class Person:
    def __init__(self, first_name, last_name, age):
        self.first_name = first_name
        self.last_name = last_name
        self._age = age
    
    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"
    
    @property
    def age(self):
        return self._age
    
    def __str__(self):
        return f"Person(name='{self.full_name}', age={self.age})"
"""


# 4. Async function with try-except
sample4 = """async def fetch_data(url):
    import aiohttp
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                return await response.json()
    except Exception as e:
        print(f"Error fetching data: {e}")
        return None
"""


# 5. Nested functions and closures
sample5 = """def create_multiplier(factor):
    def multiplier(x):
        return x * factor
    return multiplier
"""


# 6. Generator with yield
sample6 = """def fibonacci_generator(n):
    a, b = 0, 1
    count = 0
    while count < n:
        yield a
        a, b = b, a + b
        count += 1
"""


# 7. Dictionary comprehension with multiple conditions
sample7 = """def process_data(items):
    return {
        item['id']: {
            'name': item['name'].upper(),
            'valid': True
        }
        for item in items
        if item.get('active', False) and len(item.get('name', '')) > 3
    }
"""


# 8. Lambda functions and map/filter
sample8 = """def transform_numbers(numbers):
    squared = list(map(lambda x: x**2, numbers))
    filtered = list(filter(lambda x: x > 10, squared))
    return sorted(filtered, key=lambda x: x % 10)
"""


# 9. Context manager class
sample9 = """class FileManager:
    def __init__(self, filename, mode='r'):
        self.filename = filename
        self.mode = mode
        self.file = None
    
    def __enter__(self):
        self.file = open(self.filename, self.mode)
        return self.file
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.file:
            self.file.close()
"""


# 10. Decorator with arguments
sample10 = """def retry(max_attempts=3, delay=1):
    def decorator(func):
        import time
        import functools
        
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    if attempt == max_attempts - 1:
                        raise
                    time.sleep(delay)
            return None
        return wrapper
    return decorator
"""
