#!/usr/bin/env python3
"""
Test suite for the production mapping engine.

This script tests the enhanced features including performance optimizations,
thread safety, error handling, and advanced functionality.
"""

import sys
import os
import time
import threading
import json
from concurrent.futures import ThreadPoolExecutor, as_completed

# Add the parent directory to sys.path to import from engine
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from engine.mapping_production import (
        EnhancedMappedNode, 
        ProductionSourceMap,
        LinearIndex,
        BinarySearchIndex,
        HAS_INTERVAL_TREE
    )
    
    if HAS_INTERVAL_TREE:
        from engine.mapping_production import IntervalTreeIndex
        print("✓ Interval tree support available")
    else:
        print("⚠ Interval tree support not available (install intervaltree package)")
        
except ImportError as e:
    print(f"Import error: {e}")
    sys.exit(1)


def test_enhanced_mapped_node():
    """Test EnhancedMappedNode features."""
    print("Testing EnhancedMappedNode:")
    print("=" * 50)
    
    # Create enhanced node
    node = EnhancedMappedNode(
        type="function",
        name="calculate_total",
        source_start=10,
        source_end=25,
        summary_start=5,
        summary_end=8
    )
    
    # Test metadata
    node.add_metadata("compression_ratio", 0.65)
    node.add_metadata("author", "test_user")
    
    print(f"Node: {node.name}")
    print(f"Metadata: {node.metadata}")
    print(f"Compression ratio: {node.get_metadata('compression_ratio')}")
    print(f"Version: {node.version}")
    print(f"Created at: {node.created_at}")
    
    # Test content hashing
    sample_content = "def calculate_total(x, y):\n    return x + y"
    node.set_content_hash(sample_content)
    print(f"Content hash set: {node.content_hash[:16]}...")
    print(f"Content validates: {node.validate_content(sample_content)}")
    print(f"Wrong content validates: {node.validate_content('wrong content')}")
    
    # Test enhanced serialization
    node_dict = node.to_dict()
    print(f"Enhanced dict keys: {list(node_dict.keys())}")
    print()


def test_index_performance():
    """Test different index implementations for performance."""
    print("Testing Index Performance:")
    print("=" * 50)
    
    # Create test nodes
    nodes = []
    for i in range(1000):
        node = EnhancedMappedNode(
            type="function",
            name=f"func_{i}",
            source_start=i * 10 + 1,
            source_end=i * 10 + 8,
            summary_start=i * 2 + 1,
            summary_end=i * 2 + 2
        )
        nodes.append(node)
    
    # Test different index types
    index_types = ["linear", "binary"]
    if HAS_INTERVAL_TREE:
        index_types.append("interval")
    
    results = {}
    
    for index_type in index_types:
        print(f"\nTesting {index_type} index:")
        
        # Create source map
        start_time = time.time()
        source_map = ProductionSourceMap(nodes, index_type=index_type, thread_safe=False)
        build_time = time.time() - start_time
        
        # Test lookup performance
        test_lines = [500, 1500, 2500, 7500]
        lookup_times = []
        
        for line in test_lines:
            start_time = time.time()
            result = source_map.find_summary_for_source_line(line)
            lookup_time = time.time() - start_time
            lookup_times.append(lookup_time)
            
            if result:
                print(f"  Line {line} → {result.name} ({lookup_time*1000:.3f}ms)")
            else:
                print(f"  Line {line} → Not found ({lookup_time*1000:.3f}ms)")
        
        avg_lookup_time = sum(lookup_times) / len(lookup_times)
        results[index_type] = {
            'build_time': build_time,
            'avg_lookup_time': avg_lookup_time
        }
        
        print(f"  Build time: {build_time*1000:.3f}ms")
        print(f"  Average lookup time: {avg_lookup_time*1000:.6f}ms")
    
    # Summary
    print(f"\nPerformance Summary:")
    for index_type, metrics in results.items():
        print(f"  {index_type:>8}: build={metrics['build_time']*1000:.3f}ms, "
              f"lookup={metrics['avg_lookup_time']*1000:.6f}ms")
    print()


def test_thread_safety():
    """Test thread-safe operations."""
    print("Testing Thread Safety:")
    print("=" * 50)
    
    # Create source map
    source_map = ProductionSourceMap(thread_safe=True)
    
    # Add initial nodes
    initial_nodes = [
        EnhancedMappedNode("function", f"func_{i}", i*10+1, i*10+5, i*2+1, i*2+2)
        for i in range(100)
    ]
    source_map.add_nodes_batch(initial_nodes)
    
    results = []
    errors = []
    
    def worker_lookup(worker_id, iterations=100):
        """Worker function for lookup operations."""
        local_results = []
        local_errors = []
        
        for i in range(iterations):
            try:
                line = (worker_id * 100 + i) % 500 + 1
                result = source_map.find_summary_for_source_line(line)
                local_results.append((worker_id, line, result is not None))
            except Exception as e:
                local_errors.append((worker_id, str(e)))
        
        return local_results, local_errors
    
    def worker_add_nodes(worker_id, node_count=10):
        """Worker function for adding nodes."""
        local_errors = []
        
        for i in range(node_count):
            try:
                base_line = worker_id * 1000 + i * 10 + 1000
                node = EnhancedMappedNode(
                    "function", 
                    f"worker_{worker_id}_func_{i}",
                    base_line, base_line + 3,
                    base_line // 2, base_line // 2 + 1
                )
                source_map.add_node(node)
            except Exception as e:
                local_errors.append((worker_id, str(e)))
        
        return [], local_errors
    
    # Run concurrent operations
    with ThreadPoolExecutor(max_workers=8) as executor:
        # Submit lookup tasks
        lookup_futures = [
            executor.submit(worker_lookup, i, 50) 
            for i in range(4)
        ]
        
        # Submit add node tasks
        add_futures = [
            executor.submit(worker_add_nodes, i, 5)
            for i in range(4)
        ]
        
        # Collect results
        for future in as_completed(lookup_futures + add_futures):
            try:
                worker_results, worker_errors = future.result()
                results.extend(worker_results)
                errors.extend(worker_errors)
            except Exception as e:
                errors.append(("executor", str(e)))
    
    print(f"Completed {len(results)} lookup operations")
    print(f"Final node count: {len(source_map)}")
    print(f"Errors encountered: {len(errors)}")
    
    if errors:
        print("Sample errors:")
        for error in errors[:3]:
            print(f"  {error}")
    
    # Check metrics
    metrics = source_map.get_metrics()
    print(f"Lookup hit rate: {metrics['lookup_hit_rate']:.3f}")
    print(f"Total lookups: {metrics['raw_metrics']['source_lookups']}")
    print()


def test_error_recovery():
    """Test error recovery and validation."""
    print("Testing Error Recovery:")
    print("=" * 50)
    
    # Test invalid JSON recovery
    invalid_json = '{"nodes": [{"invalid": "data"'
    source_map = ProductionSourceMap.from_json(invalid_json)
    print(f"✓ Recovered from invalid JSON, nodes: {len(source_map)}")
    
    # Test partial node data recovery
    partial_data = {
        'nodes': [
            {
                'type': 'function',
                'name': 'valid_func',
                'source_start': 1,
                'source_end': 5,
                'summary_start': 1,
                'summary_end': 2
            },
            {
                'type': 'function',
                'name': 'invalid_func',
                'source_start': -1,  # Invalid
                'source_end': 5,
                'summary_start': 1,
                'summary_end': 2
            },
            {
                'incomplete': 'node'  # Missing required fields
            }
        ]
    }
    
    source_map = ProductionSourceMap.from_dict(partial_data)
    print(f"✓ Recovered from partial data, valid nodes: {len(source_map)}")
    
    # Test overlapping node detection
    try:
        overlapping_nodes = [
            EnhancedMappedNode("function", "func1", 1, 10, 1, 3),
            EnhancedMappedNode("function", "func2", 5, 15, 2, 4),  # Overlaps in source
        ]
        source_map = ProductionSourceMap(overlapping_nodes)
        print("✗ Failed to detect overlapping nodes")
    except ValueError as e:
        print(f"✓ Correctly detected overlap: {str(e)[:60]}...")
    
    print()


def test_advanced_features():
    """Test advanced features like hierarchical mapping and metadata."""
    print("Testing Advanced Features:")
    print("=" * 50)
    
    # Create hierarchical nodes
    parent_node = EnhancedMappedNode(
        "class", "Calculator", 1, 20, 1, 8
    )
    parent_node.add_metadata("complexity", "medium")
    parent_node.add_metadata("test_coverage", 0.95)
    
    # Child nodes
    method1 = EnhancedMappedNode(
        "method", "add", 5, 8, 3, 4
    )
    method1.parent_id = "Calculator"
    method1.add_metadata("cyclomatic_complexity", 1)
    
    method2 = EnhancedMappedNode(
        "method", "multiply", 12, 16, 5, 6
    )
    method2.parent_id = "Calculator"
    method2.add_metadata("cyclomatic_complexity", 2)
    
    # Update parent with children
    parent_node.children_ids.update(["add", "multiply"])
    
    # Create source map with non-overlapping ranges
    nodes = [
        EnhancedMappedNode("class", "Calculator", 1, 20, 1, 8),
        EnhancedMappedNode("function", "main", 25, 35, 10, 12),
        EnhancedMappedNode("comment", "header", 40, 45, 15, 16)
    ]
    
    for i, node in enumerate(nodes):
        node.add_metadata("order", i)
        node.add_metadata("importance", ["high", "medium", "low"][i])
    
    source_map = ProductionSourceMap(nodes)
    
    # Test metadata queries
    important_nodes = [
        node for node in source_map.nodes 
        if node.get_metadata("importance") == "high"
    ]
    print(f"High importance nodes: {len(important_nodes)}")
    
    # Test serialization with metadata
    json_data = source_map.to_json(indent=2)
    reconstructed = ProductionSourceMap.from_json(json_data)
    
    print(f"Original nodes: {len(source_map)}")
    print(f"Reconstructed nodes: {len(reconstructed)}")
    print(f"Metadata preserved: {bool(reconstructed.nodes[0].metadata)}")
    
    # Test content validation
    sample_content = "class Calculator:\n    pass"
    nodes[0].set_content_hash(sample_content)
    print(f"Content validation: {nodes[0].validate_content(sample_content)}")
    
    print()


def test_metrics_and_monitoring():
    """Test metrics collection and monitoring features."""
    print("Testing Metrics and Monitoring:")
    print("=" * 50)
    
    # Create source map with non-overlapping ranges
    nodes = [
        EnhancedMappedNode("function", f"func_{i}", i*10+1, i*10+5, i*3+1, i*3+2)
        for i in range(50)
    ]
    source_map = ProductionSourceMap(nodes, index_type="binary")
    
    # Perform various operations to generate metrics
    for i in range(100):
        line = i % 400 + 1  # Within the source range
        source_map.find_summary_for_source_line(line)
        source_map.find_source_for_summary_line(i % 100 + 1)  # Within summary range
    
    # Add some nodes with non-overlapping ranges
    for i in range(5):
        node = EnhancedMappedNode(
            "function", f"new_func_{i}",
            1000 + i*10, 1000 + i*10 + 5,  # Well separated from existing nodes
            500 + i*3, 500 + i*3 + 2
        )
        source_map.add_node(node)
    
    # Get metrics
    metrics = source_map.get_metrics()
    
    print("Performance Metrics:")
    print(f"  Node count: {metrics['node_count']}")
    print(f"  Index type: {metrics['index_type']}")
    print(f"  Lookup hit rate: {metrics['lookup_hit_rate']:.3f}")
    
    print("\nDetailed Metrics:")
    for key, value in metrics['raw_metrics'].items():
        print(f"  {key}: {value}")
    
    print()


def benchmark_large_dataset():
    """Benchmark with larger dataset."""
    print("Benchmarking Large Dataset:")
    print("=" * 50)
    
    sizes = [100, 1000, 5000] if HAS_INTERVAL_TREE else [100, 1000]
    
    for size in sizes:
        print(f"\nTesting with {size} nodes:")
        
        # Create nodes
        nodes = [
            EnhancedMappedNode(
                "function", f"func_{i}",
                i * 20 + 1, i * 20 + 15,
                i * 5 + 1, i * 5 + 3
            )
            for i in range(size)
        ]
        
        # Test with auto index selection
        start_time = time.time()
        source_map = ProductionSourceMap(nodes, index_type="auto")
        build_time = time.time() - start_time
        
        # Benchmark lookups
        test_lines = [size//4 * 20, size//2 * 20, size*3//4 * 20]
        total_lookup_time = 0
        
        for line in test_lines:
            start_time = time.time()
            result = source_map.find_summary_for_source_line(line)
            lookup_time = time.time() - start_time
            total_lookup_time += lookup_time
        
        avg_lookup_time = total_lookup_time / len(test_lines)
        
        print(f"  Index: {type(source_map.index).__name__}")
        print(f"  Build time: {build_time*1000:.3f}ms")
        print(f"  Avg lookup: {avg_lookup_time*1000000:.3f}μs")
        print(f"  Memory usage: ~{size * 100} bytes (estimated)")


def main():
    """Run all tests."""
    print("Production Mapping Engine Test Suite")
    print("=" * 80)
    print()
    
    test_enhanced_mapped_node()
    test_index_performance()
    test_thread_safety()
    test_error_recovery()
    test_advanced_features()
    test_metrics_and_monitoring()
    benchmark_large_dataset()
    
    print("All tests completed!")
    
    if not HAS_INTERVAL_TREE:
        print("\n⚠ Note: Install 'intervaltree' package for optimal performance")
        print("   pip install intervaltree")


if __name__ == "__main__":
    main()
