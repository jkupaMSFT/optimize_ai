#!/usr/bin/env python3
"""
OTPM Edge-Case Tests: Comprehensive testing for One Token Per Message scenarios.

This module tests various edge cases for OTPM (One Token Per Message) protection,
including long input with low percentage scenarios, boundary conditions, and
savings metrics validation.
"""

import sys
import os
import time
from typing import Dict, Any, List, Tuple, Optional

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.adapter import (
    OTPM_THRESHOLD,
    adapt_compression,
    calculate_savings_metrics,
    cached_estimate_tokens,
    CompressionResult
)
from utils.logger import setup_minifier_logging

# Setup test logging
test_logger = setup_minifier_logging(
    log_level="DEBUG",
    log_file="logs/otpm_edge_case_tests.log",
    enable_console=True,
    enable_file=True,
    enable_metrics=True,
    production_mode=False
)


class OTPMTestCase:
    """Test case for OTPM validation."""
    
    def __init__(self, name: str, code: str, headers: Dict[str, str], 
                 expected_action: str, expected_savings_min: float = 0.0):
        self.name = name
        self.code = code
        self.headers = headers
        self.expected_action = expected_action
        self.expected_savings_min = expected_savings_min
        self.result: Optional[CompressionResult] = None
        self.passed = False
        self.error_msg = ""


def generate_large_python_code(complexity: str = "medium") -> str:
    """Generate large Python code for testing."""
    
    if complexity == "simple":
        # Simple repetitive code
        return ("def simple_function():\n    return 'hello world'\n\n" * 500 +
                "x = 1\ny = 2\nz = x + y\n" * 300 +
                "print('test message')\n" * 200)
    
    elif complexity == "medium":
        # Medium complexity with classes and methods
        base_code = '''
import os
import sys
import json
import datetime
from typing import Dict, List, Optional, Any
from dataclasses import dataclass

@dataclass
class DataProcessor:
    """A comprehensive data processing class with multiple methods."""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.data_cache = {}
        self.processing_stats = {
            "items_processed": 0,
            "errors_encountered": 0,
            "start_time": datetime.datetime.now()
        }
    
    def process_item(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """Process a single data item with validation and transformation."""
        try:
            if not self.validate_item(item):
                raise ValueError(f"Invalid item: {item}")
            
            processed = self.transform_item(item)
            self.processing_stats["items_processed"] += 1
            return processed
            
        except Exception as e:
            self.processing_stats["errors_encountered"] += 1
            return {"error": str(e), "original": item}
    
    def validate_item(self, item: Dict[str, Any]) -> bool:
        """Validate that an item meets processing requirements."""
        required_fields = self.config.get("required_fields", [])
        for field in required_fields:
            if field not in item:
                return False
        return True
    
    def transform_item(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """Apply transformations to a data item."""
        transformations = self.config.get("transformations", {})
        result = item.copy()
        
        for field, transform_config in transformations.items():
            if field in result:
                transform_type = transform_config.get("type")
                if transform_type == "uppercase":
                    result[field] = str(result[field]).upper()
                elif transform_type == "lowercase":
                    result[field] = str(result[field]).lower()
                elif transform_type == "multiply":
                    factor = transform_config.get("factor", 1)
                    result[field] = result[field] * factor
        
        return result
    
    def process_batch(self, items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Process a batch of items efficiently."""
        results = []
        for item in items:
            result = self.process_item(item)
            results.append(result)
        return results
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get processing statistics."""
        current_time = datetime.datetime.now()
        duration = current_time - self.processing_stats["start_time"]
        
        return {
            "items_processed": self.processing_stats["items_processed"],
            "errors_encountered": self.processing_stats["errors_encountered"],
            "processing_duration": str(duration),
            "items_per_second": self.processing_stats["items_processed"] / duration.total_seconds() if duration.total_seconds() > 0 else 0
        }

class AdvancedDataAnalyzer:
    """Advanced data analysis functionality."""
    
    def __init__(self, processor: DataProcessor):
        self.processor = processor
        self.analysis_cache = {}
    
    def analyze_dataset(self, dataset: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Perform comprehensive analysis on a dataset."""
        if not dataset:
            return {"error": "Empty dataset provided"}
        
        # Basic statistics
        total_items = len(dataset)
        field_counts = self._count_fields(dataset)
        data_types = self._analyze_data_types(dataset)
        value_distributions = self._analyze_value_distributions(dataset)
        
        return {
            "total_items": total_items,
            "field_counts": field_counts,
            "data_types": data_types,
            "value_distributions": value_distributions,
            "analysis_timestamp": datetime.datetime.now().isoformat()
        }
    
    def _count_fields(self, dataset: List[Dict[str, Any]]) -> Dict[str, int]:
        """Count occurrences of each field across the dataset."""
        field_counts = {}
        for item in dataset:
            for field in item.keys():
                field_counts[field] = field_counts.get(field, 0) + 1
        return field_counts
    
    def _analyze_data_types(self, dataset: List[Dict[str, Any]]) -> Dict[str, Dict[str, int]]:
        """Analyze data types for each field."""
        type_analysis = {}
        for item in dataset:
            for field, value in item.items():
                if field not in type_analysis:
                    type_analysis[field] = {}
                
                value_type = type(value).__name__
                type_analysis[field][value_type] = type_analysis[field].get(value_type, 0) + 1
        
        return type_analysis
    
    def _analyze_value_distributions(self, dataset: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Analyze value distributions for numeric fields."""
        distributions = {}
        for item in dataset:
            for field, value in item.items():
                if isinstance(value, (int, float)):
                    if field not in distributions:
                        distributions[field] = {"values": [], "min": float('inf'), "max": float('-inf'), "sum": 0}
                    
                    distributions[field]["values"].append(value)
                    distributions[field]["min"] = min(distributions[field]["min"], value)
                    distributions[field]["max"] = max(distributions[field]["max"], value)
                    distributions[field]["sum"] += value
        
        # Calculate averages
        for field, stats in distributions.items():
            if stats["values"]:
                stats["average"] = stats["sum"] / len(stats["values"])
                stats["count"] = len(stats["values"])
                del stats["values"]  # Remove raw values to save space
        
        return distributions

def main_processing_pipeline():
    """Main data processing pipeline."""
    config = {
        "required_fields": ["id", "name", "value"],
        "transformations": {
            "name": {"type": "uppercase"},
            "value": {"type": "multiply", "factor": 2}
        }
    }
    
    processor = DataProcessor(config)
    analyzer = AdvancedDataAnalyzer(processor)
    
    # Sample data
    sample_data = [
        {"id": i, "name": f"item_{i}", "value": i * 10, "category": "test"}
        for i in range(1000)
    ]
    
    # Process data
    processed_data = processor.process_batch(sample_data)
    
    # Analyze results
    analysis = analyzer.analyze_dataset(processed_data)
    
    # Generate report
    stats = processor.get_statistics()
    
    print(f"Processing completed: {stats}")
    print(f"Analysis results: {analysis}")
    
    return processed_data, analysis

if __name__ == "__main__":
    main_processing_pipeline()
'''
        return base_code * 8  # Repeat to make it large
    
    elif complexity == "complex":
        # Very complex code with nested structures
        return ('''
import asyncio
import concurrent.futures
import itertools
import functools
from abc import ABC, abstractmethod
from typing import Generic, TypeVar, Protocol, Union, Callable
from collections import defaultdict, deque
from contextlib import asynccontextmanager, contextmanager

T = TypeVar('T')
K = TypeVar('K')
V = TypeVar('V')

class AsyncProcessor(Generic[T], ABC):
    """Abstract base class for asynchronous processing."""
    
    @abstractmethod
    async def process(self, item: T) -> T:
        """Process a single item asynchronously."""
        pass
    
    @abstractmethod
    async def batch_process(self, items: List[T]) -> List[T]:
        """Process multiple items in batch."""
        pass

class ConcurrentDataManager:
    """Thread-safe data manager with advanced caching."""
    
    def __init__(self, max_workers: int = 10):
        self.max_workers = max_workers
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=max_workers)
        self.cache = {}
        self.lock = asyncio.Lock()
    
    async def parallel_process(self, func: Callable, items: List[Any]) -> List[Any]:
        """Process items in parallel using thread pool."""
        loop = asyncio.get_event_loop()
        tasks = []
        
        for item in items:
            task = loop.run_in_executor(self.executor, func, item)
            tasks.append(task)
        
        results = await asyncio.gather(*tasks)
        return results
    
    @asynccontextmanager
    async def managed_processing(self):
        """Context manager for safe processing."""
        try:
            print("Starting managed processing...")
            yield self
        finally:
            await self.cleanup()
    
    async def cleanup(self):
        """Clean up resources."""
        self.executor.shutdown(wait=True)
        print("Cleanup completed.")

def complex_algorithm(data: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Complex data processing algorithm with multiple stages."""
    
    # Stage 1: Data preprocessing
    preprocessed = []
    for item in data:
        if validate_complex_item(item):
            processed = apply_complex_transformations(item)
            preprocessed.append(processed)
    
    # Stage 2: Advanced analytics
    analytics = perform_advanced_analytics(preprocessed)
    
    # Stage 3: Result aggregation
    aggregated = aggregate_complex_results(analytics)
    
    return aggregated

def validate_complex_item(item: Dict[str, Any]) -> bool:
    """Complex validation logic."""
    validators = [
        lambda x: isinstance(x.get('id'), int),
        lambda x: len(x.get('name', '')) > 0,
        lambda x: isinstance(x.get('values'), list),
        lambda x: all(isinstance(v, (int, float)) for v in x.get('values', []))
    ]
    
    return all(validator(item) for validator in validators)

def apply_complex_transformations(item: Dict[str, Any]) -> Dict[str, Any]:
    """Apply complex transformations to data item."""
    result = item.copy()
    
    # Mathematical transformations
    if 'values' in result:
        values = result['values']
        result['statistics'] = {
            'mean': sum(values) / len(values) if values else 0,
            'variance': calculate_variance(values),
            'std_dev': calculate_std_deviation(values),
            'quartiles': calculate_quartiles(values)
        }
    
    # String transformations
    if 'name' in result:
        result['name_variants'] = {
            'upper': result['name'].upper(),
            'lower': result['name'].lower(),
            'title': result['name'].title(),
            'reversed': result['name'][::-1]
        }
    
    return result
''' * 15)  # Repeat to make it very large


def generate_otpm_test_cases() -> List[OTPMTestCase]:
    """Generate comprehensive OTPM test cases."""
    
    test_cases = []
    
    # Test Case 1: Long input + low percentage → summarization
    large_code = generate_large_python_code("medium")
    test_cases.append(OTPMTestCase(
        name="Long Input + Low Percentage → Summarization",
        code=large_code,
        headers={"x-ratelimit-remaining-tokens": "5000", "x-ratelimit-limit-tokens": "100000"},  # 5%
        expected_action="summarized",
        expected_savings_min=50.0
    ))
    
    # Test Case 2: Very long input + very low percentage → aggressive summarization
    very_large_code = generate_large_python_code("complex")
    test_cases.append(OTPMTestCase(
        name="Very Long Input + Very Low Percentage → Aggressive Summarization",
        code=very_large_code,
        headers={"x-ratelimit-remaining-tokens": "1000", "x-ratelimit-limit-tokens": "100000"},  # 1%
        expected_action="summarized",
        expected_savings_min=75.0
    ))
    
    # Test Case 3: Boundary test - exactly at 80% of OTPM threshold
    boundary_code = "def test():\n    pass\n" * 1600  # Should be close to 80% of 8000 tokens
    test_cases.append(OTPMTestCase(
        name="Boundary Test - 80% OTMP Threshold",
        code=boundary_code,
        headers={"x-ratelimit-remaining-tokens": "10000", "x-ratelimit-limit-tokens": "100000"},  # 10%
        expected_action="summarized",
        expected_savings_min=30.0
    ))
    
    # Test Case 4: Exactly at OTPM threshold
    threshold_code = "def test():\n    pass\n" * 2000  # Should be close to 8000 tokens
    test_cases.append(OTPMTestCase(
        name="Exactly at OTPM Threshold",
        code=threshold_code,
        headers={"x-ratelimit-remaining-tokens": "5000", "x-ratelimit-limit-tokens": "100000"},  # 5%
        expected_action="truncated",
        expected_savings_min=20.0
    ))
    
    # Test Case 5: Way over OTPM threshold
    massive_code = "def test():\n    pass\n" * 5000  # Should be way over 8000 tokens
    test_cases.append(OTPMTestCase(
        name="Way Over OTPM Threshold",
        code=massive_code,
        headers={"x-ratelimit-remaining-tokens": "2000", "x-ratelimit-limit-tokens": "100000"},  # 2%
        expected_action="truncated",
        expected_savings_min=50.0
    ))
    
    # Test Case 6: Small code + low percentage (should not trigger OTPM)
    small_code = "def hello():\n    return 'world'\n\nprint(hello())"
    test_cases.append(OTPMTestCase(
        name="Small Code + Low Percentage (No OTPM Trigger)",
        code=small_code,
        headers={"x-ratelimit-remaining-tokens": "1000", "x-ratelimit-limit-tokens": "100000"},  # 1%
        expected_action="safe",
        expected_savings_min=0.0
    ))
    
    # Test Case 7: Medium code + moderate percentage
    medium_code = generate_large_python_code("simple")[:5000]  # Moderate size
    test_cases.append(OTPMTestCase(
        name="Medium Code + Moderate Percentage",
        code=medium_code,
        headers={"x-ratelimit-remaining-tokens": "30000", "x-ratelimit-limit-tokens": "100000"},  # 30%
        expected_action="safe",
        expected_savings_min=0.0
    ))
    
    # Test Case 8: Edge case - empty headers
    test_cases.append(OTPMTestCase(
        name="Edge Case - Empty Headers",
        code=large_code,
        headers={},
        expected_action="safe",  # Should default to safe handling
        expected_savings_min=0.0
    ))
    
    # Test Case 9: Edge case - malformed headers
    test_cases.append(OTPMTestCase(
        name="Edge Case - Malformed Headers",
        code=medium_code,
        headers={"x-ratelimit-remaining-tokens": "invalid", "x-ratelimit-limit-tokens": "also_invalid"},
        expected_action="safe",  # Should default to safe handling
        expected_savings_min=0.0
    ))
    
    return test_cases


def run_otpm_test_case(test_case: OTPMTestCase) -> bool:
    """Run a single OTPM test case."""
    
    print(f"\n{'='*60}")
    print(f"Running Test: {test_case.name}")
    print(f"{'='*60}")
    
    try:
        # Get initial token count
        initial_tokens = cached_estimate_tokens(test_case.code, "tiktoken", "gpt-4")
        print(f"Initial code: {len(test_case.code)} chars, ~{initial_tokens} tokens")
        
        # Run adapt_compression
        start_time = time.time()
        result = adapt_compression(
            headers=test_case.headers,
            code=test_case.code,
            model_type="gpt-4",
            return_metadata=True
        )
        processing_time = time.time() - start_time
        
        test_case.result = result
        
        # Analyze results
        print(f"Processing time: {processing_time*1000:.1f}ms")
        print(f"Final tokens: {result.post_tokens}")
        print(f"OTPM status: {result.additional_metrics.get('otpm_status', 'unknown')}")
        print(f"Token reduction: {result.token_reduction_percent:.1f}%")
        
        # Check savings metrics
        savings_metrics = result.additional_metrics.get('savings_metrics', {})
        savings_percent = savings_metrics.get('savings_percent', 0.0)
        efficiency_rating = savings_metrics.get('efficiency_rating', 'unknown')
        meets_target = savings_metrics.get('meets_target', False)
        
        print(f"Savings: {savings_percent:.1f}% ({efficiency_rating})")
        print(f"Meets 50% target: {'✓' if meets_target else '✗'}")
        
        # Validate expected action
        otpm_status = result.additional_metrics.get('otpm_status', 'unknown')
        action_match = test_case.expected_action in otpm_status.lower()
        
        # Validate expected savings
        savings_match = savings_percent >= test_case.expected_savings_min
        
        # Overall test result
        test_case.passed = action_match and (savings_match or test_case.expected_savings_min == 0.0)
        
        if test_case.passed:
            print(f"✅ TEST PASSED")
        else:
            reasons = []
            if not action_match:
                reasons.append(f"Expected action '{test_case.expected_action}' not found in status '{otpm_status}'")
            if not savings_match and test_case.expected_savings_min > 0.0:
                reasons.append(f"Expected savings ≥{test_case.expected_savings_min}%, got {savings_percent:.1f}%")
            
            test_case.error_msg = "; ".join(reasons)
            print(f"❌ TEST FAILED: {test_case.error_msg}")
        
        return test_case.passed
        
    except Exception as e:
        test_case.error_msg = f"Exception during test: {str(e)}"
        print(f"❌ TEST FAILED: {test_case.error_msg}")
        return False


def run_all_otpm_tests() -> Dict[str, Any]:
    """Run all OTPM edge case tests."""
    
    print("🚀 Starting OTPM Edge Case Tests")
    print("=" * 80)
    
    test_cases = generate_otpm_test_cases()
    results = {
        "total_tests": len(test_cases),
        "passed": 0,
        "failed": 0,
        "test_results": [],
        "summary_metrics": {
            "total_savings_achieved": [],
            "otpm_triggers": 0,
            "summarizations": 0,
            "truncations": 0
        }
    }
    
    for i, test_case in enumerate(test_cases, 1):
        print(f"\n[{i}/{len(test_cases)}] ", end="")
        
        success = run_otpm_test_case(test_case)
        
        if success:
            results["passed"] += 1
        else:
            results["failed"] += 1
        
        # Collect metrics
        if test_case.result:
            savings_metrics = test_case.result.additional_metrics.get('savings_metrics', {})
            savings_percent = savings_metrics.get('savings_percent', 0.0)
            results["summary_metrics"]["total_savings_achieved"].append(savings_percent)
            
            otpm_status = test_case.result.additional_metrics.get('otpm_status', '')
            if 'summarized' in otpm_status.lower():
                results["summary_metrics"]["summarizations"] += 1
                results["summary_metrics"]["otpm_triggers"] += 1
            elif 'truncated' in otpm_status.lower():
                results["summary_metrics"]["truncations"] += 1
                results["summary_metrics"]["otpm_triggers"] += 1
        
        results["test_results"].append({
            "name": test_case.name,
            "passed": success,
            "error_msg": test_case.error_msg,
            "savings_percent": test_case.result.additional_metrics.get('savings_metrics', {}).get('savings_percent', 0.0) if test_case.result else 0.0,
            "otpm_status": test_case.result.additional_metrics.get('otpm_status', 'unknown') if test_case.result else 'unknown'
        })
    
    # Calculate summary statistics
    if results["summary_metrics"]["total_savings_achieved"]:
        avg_savings = sum(results["summary_metrics"]["total_savings_achieved"]) / len(results["summary_metrics"]["total_savings_achieved"])
        max_savings = max(results["summary_metrics"]["total_savings_achieved"])
        min_savings = min(results["summary_metrics"]["total_savings_achieved"])
        
        results["summary_metrics"]["average_savings"] = round(avg_savings, 2)
        results["summary_metrics"]["max_savings"] = round(max_savings, 2)
        results["summary_metrics"]["min_savings"] = round(min_savings, 2)
    
    # Print final summary
    print("\n" + "=" * 80)
    print("🏁 OTPM Edge Case Tests Complete")
    print("=" * 80)
    print(f"Total Tests: {results['total_tests']}")
    print(f"Passed: {results['passed']} ✅")
    print(f"Failed: {results['failed']} ❌")
    print(f"Success Rate: {(results['passed'] / results['total_tests'] * 100):.1f}%")
    print()
    print("Summary Metrics:")
    print(f"  OTPM Triggers: {results['summary_metrics']['otpm_triggers']}")
    print(f"  Summarizations: {results['summary_metrics']['summarizations']}")
    print(f"  Truncations: {results['summary_metrics']['truncations']}")
    
    if "average_savings" in results["summary_metrics"]:
        print(f"  Average Savings: {results['summary_metrics']['average_savings']:.1f}%")
        print(f"  Max Savings: {results['summary_metrics']['max_savings']:.1f}%")
        print(f"  Min Savings: {results['summary_metrics']['min_savings']:.1f}%")
    
    print("\nDetailed Results:")
    for test_result in results["test_results"]:
        status = "✅ PASS" if test_result["passed"] else "❌ FAIL"
        print(f"  {status} | {test_result['name']} | Savings: {test_result['savings_percent']:.1f}% | Status: {test_result['otpm_status']}")
        if not test_result["passed"]:
            print(f"    └─ Error: {test_result['error_msg']}")
    
    return results


def test_savings_metrics_function():
    """Test the savings metrics calculation function directly."""
    
    print("\n" + "=" * 60)
    print("Testing Savings Metrics Function")
    print("=" * 60)
    
    test_cases = [
        (1000, 500, "50% reduction"),
        (1000, 250, "75% reduction"),
        (1000, 100, "90% reduction"),
        (1000, 900, "10% reduction"),
        (1000, 1000, "0% reduction"),
        (1000, 1100, "negative reduction"),
        (0, 500, "invalid original"),
    ]
    
    for original, final, description in test_cases:
        metrics = calculate_savings_metrics(original, final, f"test_{description}")
        print(f"{description:20} | {metrics['savings_percent']:6.1f}% | {metrics['efficiency_rating']:12} | Target: {'✓' if metrics['meets_target'] else '✗'}")


if __name__ == "__main__":
    # Run savings metrics tests
    test_savings_metrics_function()
    
    # Run comprehensive OTPM tests
    results = run_all_otpm_tests()
    
    # Exit with appropriate code
    sys.exit(0 if results["failed"] == 0 else 1)
