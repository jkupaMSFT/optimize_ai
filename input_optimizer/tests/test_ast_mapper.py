#!/usr/bin/env python3
"""
Comprehensive test suite for the AST mapper with proper logging integration.

This script tests all functionality of the AST mapper including:
- Basic AST walking and node mapping
- Compression ratio calculations
- Coverage analysis
- Error handling and validation
- Logging integration with MinifierLogger
"""

import sys
import os
import time
import tempfile
import json
from typing import Dict, Any

# Add the parent directories to sys.path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from utils.logger import setup_minifier_logging, MinifierLogger
from input_optimizer.engine.mapping.ast_map import (
    ASTMapper, 
    MappedNode, 
    walk_ast_and_map, 
    validate_non_overlapping
)


def setup_test_logging() -> MinifierLogger:
    """Setup comprehensive logging for tests."""
    return setup_minifier_logging(
        log_level="DEBUG",
        log_file="logs/ast_mapper_test.log",
        enable_console=True,
        enable_file=True,
        enable_metrics=True,
        enable_performance=True,
        enable_ast_details=True,
        production_mode=False
    )


def test_basic_ast_walking():
    """Test basic AST walking functionality."""
    print("🧪 Testing Basic AST Walking...")
    
    logger = setup_test_logging()
    
    code = """
import os
import sys

def simple_function():
    return 42

class SimpleClass:
    def method(self):
        pass
"""
    
    start_time = time.time()
    nodes = walk_ast_and_map(code, minifier_logger=logger)
    duration = time.time() - start_time
    
    print(f"   ✓ Mapped {len(nodes)} nodes in {duration*1000:.2f}ms")
    
    # Verify basic structure
    assert len(nodes) >= 4, f"Expected at least 4 nodes, got {len(nodes)}"
    
    # Check node types
    node_types = [node.type for node in nodes]
    assert 'import' in node_types, "Should have import nodes"
    assert 'function' in node_types, "Should have function nodes"
    assert 'class' in node_types, "Should have class nodes"
    assert 'method' in node_types, "Should have method nodes"
    
    # Print results
    for node in nodes:
        print(f"     {node.type:8} | {node.name:20} | "
              f"{node.source_start:2}-{node.source_end:2} → {node.summary_start:2}-{node.summary_end:2}")
    
    print("   ✓ Basic AST walking test passed")
    return True


def test_compression_ratios():
    """Test different compression ratios."""
    print("🧪 Testing Compression Ratios...")
    
    logger = setup_test_logging()
    
    code = """
def long_function():
    # This function has many lines
    line1 = 1
    line2 = 2
    line3 = 3
    line4 = 4
    line5 = 5
    line6 = 6
    line7 = 7
    line8 = 8
    line9 = 9
    line10 = 10
    return line1 + line2 + line3 + line4 + line5
"""
    
    # Test different compression ratios
    test_ratios = [
        {'function': 0.1},  # High compression
        {'function': 0.5},  # Medium compression
        {'function': 0.9},  # Low compression
    ]
    
    for i, ratios in enumerate(test_ratios):
        print(f"   Testing ratio {ratios['function']:.1f}...")
        
        nodes = walk_ast_and_map(code, compression_ratios=ratios, minifier_logger=logger)
        func_node = nodes[0]
        
        source_lines = func_node.source_end - func_node.source_start + 1
        summary_lines = func_node.summary_end - func_node.summary_start + 1
        actual_ratio = summary_lines / source_lines
        
        print(f"     Source: {source_lines} lines → Summary: {summary_lines} lines")
        print(f"     Expected ratio: {ratios['function']:.2f}, Actual: {actual_ratio:.2f}")
        
        # Should be close to expected ratio (allowing for minimum 1 line)
        if source_lines * ratios['function'] >= 1:
            assert abs(actual_ratio - ratios['function']) < 0.2, \
                f"Ratio mismatch: expected ~{ratios['function']}, got {actual_ratio}"
    
    print("   ✓ Compression ratios test passed")
    return True


def test_decorated_functions():
    """Test handling of decorated functions."""
    print("🧪 Testing Decorated Functions...")
    
    logger = setup_test_logging()
    
    code = """
@decorator_one
@decorator_two
def decorated_function():
    '''Function with decorators'''
    return "decorated"

@property
def property_method(self):
    return self._value
"""
    
    nodes = walk_ast_and_map(code, minifier_logger=logger)
    
    # Should have 2 function nodes
    func_nodes = [node for node in nodes if node.type == 'function']
    assert len(func_nodes) == 2, f"Expected 2 function nodes, got {len(func_nodes)}"
    
    # First function should start from decorator line
    first_func = func_nodes[0]
    assert first_func.source_start == 2, \
        f"Decorated function should start at line 2 (first decorator), got {first_func.source_start}"
    
    print(f"   ✓ Decorated function mapped from line {first_func.source_start}")
    print("   ✓ Decorated functions test passed")
    return True


def test_class_with_methods():
    """Test class mapping with methods."""
    print("🧪 Testing Class with Methods...")
    
    logger = setup_test_logging()
    
    code = """
class Calculator:
    '''A simple calculator class'''
    
    def __init__(self, value=0):
        self.value = value
    
    def add(self, x):
        self.value += x
        return self.value
    
    def multiply(self, x):
        self.value *= x
        return self.value
    
    @property
    def current_value(self):
        return self.value
"""
    
    nodes = walk_ast_and_map(code, minifier_logger=logger)
    
    # Should have: 1 class + 4 methods
    class_nodes = [node for node in nodes if node.type == 'class']
    method_nodes = [node for node in nodes if node.type == 'method']
    
    assert len(class_nodes) == 1, f"Expected 1 class node, got {len(class_nodes)}"
    assert len(method_nodes) == 4, f"Expected 4 method nodes, got {len(method_nodes)}"
    
    # Check method names
    method_names = [node.name for node in method_nodes]
    expected_methods = ['Calculator.__init__', 'Calculator.add', 'Calculator.multiply', 'Calculator.current_value']
    
    for expected in expected_methods:
        assert expected in method_names, f"Expected method {expected} not found in {method_names}"
    
    print(f"   ✓ Found class: {class_nodes[0].name}")
    print(f"   ✓ Found methods: {', '.join([m.name.split('.')[-1] for m in method_nodes])}")
    print("   ✓ Class with methods test passed")
    return True


def test_coverage_analysis():
    """Test coverage analysis functionality."""
    print("🧪 Testing Coverage Analysis...")
    
    logger = setup_test_logging()
    
    code = """
import os

def function_one():
    return 1

# This comment creates a gap

def function_two():
    return 2

# Another gap

class MyClass:
    def method(self):
        pass
"""
    
    mapper = ASTMapper(minifier_logger=logger)
    nodes = mapper.walk_ast(code)
    coverage = mapper.get_mapping_coverage()
    
    print(f"   Total lines: {coverage['total_source_lines']}")
    print(f"   Covered lines: {coverage['covered_lines']}")
    print(f"   Coverage: {coverage['coverage_percentage']:.1f}%")
    print(f"   Gaps: {coverage['gaps']}")
    
    # Should have some coverage
    assert coverage['coverage_percentage'] >= 50, \
        f"Coverage too low: {coverage['coverage_percentage']:.1f}%"
    
    # Should have gaps due to comments
    assert len(coverage['gaps']) > 0, "Should have coverage gaps due to unmapped comments"
    
    print("   ✓ Coverage analysis test passed")
    return True


def test_error_handling():
    """Test error handling with invalid code."""
    print("🧪 Testing Error Handling...")
    
    logger = setup_test_logging()
    
    # Test with syntax error
    invalid_code = """
def broken_function(
    # Missing closing parenthesis
    return "broken"
"""
    
    try:
        walk_ast_and_map(invalid_code, minifier_logger=logger)
        assert False, "Should have raised SyntaxError"
    except SyntaxError:
        print("   ✓ Correctly caught SyntaxError")
    
    # Test validation with overlapping ranges (manually create invalid nodes)
    valid_code = "def func(): pass"
    try:
        # Create invalid overlapping nodes manually
        invalid_nodes = [
            MappedNode("function", "func1", 1, 5, 1, 3),
            MappedNode("function", "func2", 3, 7, 2, 4),  # Overlaps in source
        ]
        validate_non_overlapping(invalid_nodes)
        assert False, "Should have caught overlapping ranges"
    except ValueError:
        print("   ✓ Correctly caught overlapping ranges")
    
    print("   ✓ Error handling test passed")
    return True


def test_json_serialization():
    """Test JSON serialization and deserialization."""
    print("🧪 Testing JSON Serialization...")
    
    logger = setup_test_logging()
    
    code = """
import json
from typing import Dict

class DataProcessor:
    def __init__(self):
        self.data = {}
    
    def process(self, input_data: Dict):
        return json.dumps(input_data)
"""
    
    # Create mapper and process code
    mapper = ASTMapper({'import': 1.0, 'class': 0.6, 'method': 0.4}, logger)
    nodes = mapper.walk_ast(code)
    
    # Test to_dict
    mapper_dict = mapper.to_dict()
    assert 'nodes' in mapper_dict
    assert 'metadata' in mapper_dict
    assert len(mapper_dict['nodes']) == len(nodes)
    
    print(f"   ✓ Serialized {len(nodes)} nodes to dict")
    
    # Test JSON save/load
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        mapper.save_to_json(f.name)
        temp_path = f.name
    
    # Load and verify
    loaded_mapper = ASTMapper.load_from_json(temp_path)
    assert len(loaded_mapper.mapped_nodes) == len(mapper.mapped_nodes)
    assert loaded_mapper.compression_ratios == mapper.compression_ratios
    
    print(f"   ✓ Successfully saved and loaded JSON file")
    
    # Clean up
    os.unlink(temp_path)
    
    print("   ✓ JSON serialization test passed")
    return True


def test_bidirectional_mapping():
    """Test bidirectional source<->summary mapping."""
    print("🧪 Testing Bidirectional Mapping...")
    
    logger = setup_test_logging()
    
    code = """
def long_function():
    line1 = 1
    line2 = 2
    line3 = 3
    line4 = 4
    line5 = 5
    line6 = 6
    line7 = 7
    line8 = 8
    return line1 + line8

class LongClass:
    def method1(self):
        pass
    
    def method2(self):
        pass
"""
    
    mapper = ASTMapper({'function': 0.4, 'class': 0.5, 'method': 0.3}, logger)
    nodes = mapper.walk_ast(code)
    
    # Test source -> summary range mapping
    source_lines = mapper.find_source_lines_for_summary_range(1, 3)
    print(f"   Summary lines 1-3 map to source lines: {source_lines}")
    assert len(source_lines) > 0, "Should find some source lines"
    
    # Test coverage of all nodes
    for node in nodes:
        print(f"   {node.type:8} {node.name:20} | "
              f"Source: {node.source_start:2}-{node.source_end:2} | "
              f"Summary: {node.summary_start:2}-{node.summary_end:2}")
    
    print("   ✓ Bidirectional mapping test passed")
    return True


def test_performance_benchmarks():
    """Test performance with larger code samples."""
    print("🧪 Testing Performance Benchmarks...")
    
    logger = setup_test_logging()
    
    # Generate larger code sample
    large_code = """
import os
import sys
import json
from typing import Dict, List, Optional

"""
    
    # Add multiple classes and functions
    for i in range(10):
        large_code += f"""
class TestClass{i}:
    '''Test class {i}'''
    
    def __init__(self):
        self.value = {i}
    
    def method_{i}_a(self):
        return self.value + {i}
    
    def method_{i}_b(self):
        return self.value * {i}
    
    def method_{i}_c(self):
        result = 0
        for j in range({i}):
            result += j
        return result

def standalone_function_{i}():
    '''Standalone function {i}'''
    data = []
    for k in range({i * 5}):
        data.append(k ** 2)
    return sum(data)
"""
    
    print(f"   Code size: {len(large_code)} characters, {len(large_code.splitlines())} lines")
    
    # Benchmark the mapping
    start_time = time.time()
    nodes = walk_ast_and_map(large_code, minifier_logger=logger)
    duration = time.time() - start_time
    
    print(f"   ✓ Mapped {len(nodes)} nodes in {duration*1000:.2f}ms")
    print(f"   Performance: {len(nodes)/duration:.1f} nodes/second")
    
    # Verify structure
    node_counts = {}
    for node in nodes:
        node_counts[node.type] = node_counts.get(node.type, 0) + 1
    
    print(f"   Node distribution: {node_counts}")
    
    # Should have many nodes
    assert len(nodes) > 50, f"Expected many nodes for large code, got {len(nodes)}"
    
    print("   ✓ Performance benchmark test passed")
    return True


def test_async_functions():
    """Test handling of async functions."""
    print("🧪 Testing Async Functions...")
    
    logger = setup_test_logging()
    
    code = """
import asyncio

async def async_function():
    '''An async function'''
    await asyncio.sleep(1)
    return "done"

class AsyncClass:
    async def async_method(self):
        '''An async method'''
        return await self.helper()
    
    async def helper(self):
        return "helper"
"""
    
    nodes = walk_ast_and_map(code, minifier_logger=logger)
    
    # Should handle async functions
    func_nodes = [node for node in nodes if node.type in ['function', 'method']]
    assert len(func_nodes) >= 3, f"Expected at least 3 function/method nodes, got {len(func_nodes)}"
    
    print(f"   ✓ Found {len(func_nodes)} function/method nodes")
    for func in func_nodes:
        print(f"     {func.type}: {func.name}")
    
    print("   ✓ Async functions test passed")
    return True


def run_all_tests():
    """Run all test functions."""
    print("🚀 AST Mapper Test Suite")
    print("=" * 60)
    
    tests = [
        test_basic_ast_walking,
        test_compression_ratios,
        test_decorated_functions,
        test_class_with_methods,
        test_coverage_analysis,
        test_error_handling,
        test_json_serialization,
        test_bidirectional_mapping,
        test_async_functions,
        test_performance_benchmarks,
    ]
    
    passed = 0
    failed = 0
    
    for test_func in tests:
        try:
            if test_func():
                passed += 1
            else:
                failed += 1
                print(f"   ✗ {test_func.__name__} failed")
        except Exception as e:
            failed += 1
            print(f"   ✗ {test_func.__name__} failed with error: {e}")
            import traceback
            traceback.print_exc()
        
        print()  # Add spacing between tests
    
    print("=" * 60)
    print(f"Test Results: {passed} passed, {failed} failed")
    
    if failed == 0:
        print("🎉 All tests passed!")
        return True
    else:
        print(f"❌ {failed} test(s) failed")
        return False


def demo_real_world_usage():
    """Demonstrate real-world usage of the AST mapper."""
    print("\n" + "=" * 60)
    print("🌟 Real-World Usage Demo")
    print("=" * 60)
    
    logger = setup_test_logging()
    
    # Real Python code example
    real_code = '''
"""
A sample Python module for data processing.
"""
import os
import json
import logging
from typing import Dict, List, Optional, Union
from pathlib import Path


logger = logging.getLogger(__name__)


class DataProcessor:
    """
    A class for processing various data formats.
    
    This class provides methods for loading, processing, and saving
    data in different formats including JSON, CSV, and plain text.
    """
    
    def __init__(self, config_path: Optional[Path] = None):
        """Initialize the data processor with optional configuration."""
        self.config = {}
        self.data_cache = {}
        
        if config_path and config_path.exists():
            self.load_config(config_path)
    
    def load_config(self, config_path: Path) -> Dict:
        """Load configuration from a JSON file."""
        try:
            with open(config_path, 'r') as f:
                self.config = json.load(f)
            logger.info(f"Configuration loaded from {config_path}")
            return self.config
        except (FileNotFoundError, json.JSONDecodeError) as e:
            logger.error(f"Failed to load config: {e}")
            return {}
    
    @property
    def cache_size(self) -> int:
        """Get the current cache size."""
        return len(self.data_cache)
    
    def process_data(self, data: Union[Dict, List], 
                    operation: str = "normalize") -> Union[Dict, List]:
        """
        Process data with the specified operation.
        
        Args:
            data: Input data to process
            operation: Operation to perform ('normalize', 'filter', 'transform')
        
        Returns:
            Processed data
        """
        if operation == "normalize":
            return self._normalize_data(data)
        elif operation == "filter":
            return self._filter_data(data)
        elif operation == "transform":
            return self._transform_data(data)
        else:
            raise ValueError(f"Unknown operation: {operation}")
    
    def _normalize_data(self, data):
        """Internal method to normalize data."""
        # Normalization logic here
        return data
    
    def _filter_data(self, data):
        """Internal method to filter data."""
        # Filtering logic here
        return data
    
    def _transform_data(self, data):
        """Internal method to transform data."""
        # Transformation logic here
        return data
    
    async def async_process(self, data_stream):
        """Asynchronously process a data stream."""
        results = []
        async for item in data_stream:
            processed = self.process_data(item)
            results.append(processed)
        return results


def create_processor(config_path: str = "config.json") -> DataProcessor:
    """Factory function to create a configured DataProcessor."""
    path = Path(config_path)
    return DataProcessor(path if path.exists() else None)


async def batch_process(files: List[Path]) -> Dict[str, Any]:
    """Process multiple files asynchronously."""
    processor = create_processor()
    results = {}
    
    for file_path in files:
        if file_path.suffix == ".json":
            with open(file_path) as f:
                data = json.load(f)
            results[str(file_path)] = processor.process_data(data)
    
    return results


if __name__ == "__main__":
    # Example usage
    processor = create_processor()
    sample_data = {"name": "test", "value": 42}
    result = processor.process_data(sample_data)
    print(f"Processed: {result}")
'''
    
    print(f"Processing real-world Python code ({len(real_code)} chars, {len(real_code.splitlines())} lines)...")
    
    # Process with detailed logging
    start_time = time.time()
    nodes = walk_ast_and_map(real_code, minifier_logger=logger)
    duration = time.time() - start_time
    
    print(f"\n📊 Mapping Results:")
    print(f"   Total nodes mapped: {len(nodes)}")
    print(f"   Processing time: {duration*1000:.2f}ms")
    print(f"   Performance: {len(nodes)/duration:.1f} nodes/second")
    
    # Analyze node distribution
    node_counts = {}
    for node in nodes:
        node_counts[node.type] = node_counts.get(node.type, 0) + 1
    
    print(f"\n📈 Node Distribution:")
    for node_type, count in sorted(node_counts.items()):
        print(f"   {node_type:10}: {count:3} nodes")
    
    # Show coverage analysis
    mapper = ASTMapper(minifier_logger=logger)
    mapper.walk_ast(real_code)
    coverage = mapper.get_mapping_coverage()
    
    print(f"\n📋 Coverage Analysis:")
    print(f"   Total source lines: {coverage['total_source_lines']}")
    print(f"   Covered lines: {coverage['covered_lines']}")
    print(f"   Coverage percentage: {coverage['coverage_percentage']:.1f}%")
    print(f"   Coverage gaps: {len(coverage['gaps'])} ranges")
    
    # Show sample mappings
    print(f"\n🗺️  Sample Mappings:")
    print(f"   {'Type':10} | {'Name':30} | {'Source':12} | {'Summary':12}")
    print("   " + "-" * 70)
    for node in nodes[:10]:  # Show first 10 nodes
        name = node.name[:28] + ".." if len(node.name) > 30 else node.name
        print(f"   {node.type:10} | {name:30} | "
              f"{node.source_start:3}-{node.source_end:3} ({node.source_end-node.source_start+1:2}L) | "
              f"{node.summary_start:3}-{node.summary_end:3} ({node.summary_end-node.summary_start+1:2}L)")
    
    if len(nodes) > 10:
        print(f"   ... and {len(nodes) - 10} more nodes")
    
    print("\n🎯 Demo completed successfully!")


if __name__ == "__main__":
    # Ensure logs directory exists
    os.makedirs("logs", exist_ok=True)
    
    # Run all tests
    success = run_all_tests()
    
    # Run demo if tests passed
    if success:
        demo_real_world_usage()
    
    # Exit with appropriate code
    sys.exit(0 if success else 1)
