#!/usr/bin/env python3
"""
Test runner for the minifier test suite.
Run with: python tests/run_minifier_tests.py
"""

import sys
import unittest
from pathlib import Path

# Add project paths
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "engine"))

def run_tests():
    """Run all minifier tests."""
    print("=" * 60)
    print("RUNNING MINIFIER TEST SUITE")
    print("=" * 60)
    
    # Discover and run tests
    loader = unittest.TestLoader()
    start_dir = str(Path(__file__).parent / "engine_tests")
    suite = loader.discover(start_dir, pattern="test_*.py")
    
    # Run tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    # Print summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    print(f"Tests run: {result.testsRun}")
    print(f"Failures: {len(result.failures)}")
    print(f"Errors: {len(result.errors)}")
    print(f"Success rate: {((result.testsRun - len(result.failures) - len(result.errors)) / result.testsRun * 100):.1f}%")
    
    if result.failures:
        print("\nFAILURES:")
        for test, traceback in result.failures:
            print(f"- {test}: {traceback}")
    
    if result.errors:
        print("\nERRORS:")
        for test, traceback in result.errors:
            print(f"- {test}: {traceback}")
    
    return result.wasSuccessful()


def demo_minifier():
    """Demonstrate minifier capabilities."""
    from minifier import minify_with_stats, minify_basic, minify_aggressive
    
    print("\n" + "=" * 60)
    print("MINIFIER DEMONSTRATION")
    print("=" * 60)
    
    demo_code = '''
def calculate_fibonacci(n):
    """
    Calculate the nth Fibonacci number using recursion.
    This is an example function for demonstration.
    """
    # Base cases
    if n <= 0:
        return 0
    elif n == 1:
        return 1
    else:
        # Recursive case
        return calculate_fibonacci(n - 1) + calculate_fibonacci(n - 2)

def optimize_calculation(input_value):
    """Optimize some calculations."""
    # Some constant folding opportunities
    multiplier = 2 * 3 + 1  # Should become 7
    result = input_value * multiplier
    
    # Boolean optimization
    if True:
        result += 10
        return result
    
    # Dead code - should be removed
    print("This will never execute")
    return 0

class DataProcessor:
    """Process data efficiently."""
    
    def __init__(self, initial_data):
        self.data = initial_data
        self.processed_count = 0
    
    def process_item(self, item):
        """Process a single item."""
        processed = item.strip().lower()
        self.processed_count += 1
        return processed
'''
    
    print("ORIGINAL CODE:")
    print("-" * 40)
    print(demo_code)
    
    print("\nBASIC MINIFICATION:")
    print("-" * 40)
    basic_minified, basic_stats = minify_with_stats(demo_code, aggressive=False)
    print(basic_minified)
    print(f"\nBasic Stats: {basic_stats['size_reduction_percent']:.1f}% size reduction, {basic_stats['token_reduction_percent']:.1f}% token reduction")
    
    print("\nAGGRESSIVE MINIFICATION:")
    print("-" * 40)
    aggressive_minified, aggressive_stats = minify_with_stats(demo_code, aggressive=True)
    print(aggressive_minified)
    print(f"\nAggressive Stats: {aggressive_stats['size_reduction_percent']:.1f}% size reduction, {aggressive_stats['token_reduction_percent']:.1f}% token reduction")
    
    print("\nCOMPARISON:")
    print("-" * 40)
    print(f"Original size: {len(demo_code)} characters")
    print(f"Basic minified: {len(basic_minified)} characters ({basic_stats['size_reduction_percent']:.1f}% reduction)")
    print(f"Aggressive minified: {len(aggressive_minified)} characters ({aggressive_stats['size_reduction_percent']:.1f}% reduction)")


if __name__ == "__main__":
    # Run tests first
    success = run_tests()
    
    if success:
        # If tests pass, show demo
        demo_minifier()
        print("\n✅ All tests passed! Minifier is ready for use.")
    else:
        print("\n❌ Some tests failed. Please check the output above.")
        sys.exit(1) 