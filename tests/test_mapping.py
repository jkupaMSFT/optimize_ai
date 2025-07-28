#!/usr/bin/env python3
"""
Test script for the mapping engine.

This script demonstrates the usage of MappedNode and SourceMap classes
with various test scenarios.
"""

import sys
import os

# Add the parent directory to sys.path to import from engine
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.mapping import MappedNode, SourceMap


def test_mapped_node():
    """Test MappedNode functionality."""
    print("Testing MappedNode:")
    print("=" * 50)
    
    # Create a sample node
    node = MappedNode(
        type="function",
        name="calculate_total",
        source_start=10,
        source_end=25,
        summary_start=5,
        summary_end=8
    )
    
    print(f"Node: {node}")
    print(f"Contains source line 15: {node.contains_source_line(15)}")
    print(f"Contains source line 30: {node.contains_source_line(30)}")
    print(f"Contains summary line 6: {node.contains_summary_line(6)}")
    print(f"Contains summary line 10: {node.contains_summary_line(10)}")
    print(f"Node as dict: {node.to_dict()}")
    print()


def test_source_map():
    """Test SourceMap functionality."""
    print("Testing SourceMap:")
    print("=" * 50)
    
    # Create sample nodes
    nodes = [
        MappedNode("function", "main", 1, 10, 1, 3),
        MappedNode("class", "DataProcessor", 15, 45, 5, 12),
        MappedNode("function", "process_data", 20, 35, 7, 9),
        MappedNode("comment", "documentation", 50, 55, 15, 16),
    ]
    
    # Create source map
    source_map = SourceMap()
    
    # Add nodes one by one
    for node in nodes:
        try:
            source_map.add_node(node)
            print(f"Added node: {node.name}")
        except ValueError as e:
            print(f"Failed to add node {node.name}: {e}")
    
    print(f"\nSourceMap contains {len(source_map)} nodes")
    print()


def test_bidirectional_lookup():
    """Test bidirectional lookup functionality."""
    print("Testing Bidirectional Lookup:")
    print("=" * 50)
    
    # Create a simple source map
    nodes = [
        MappedNode("function", "setup", 1, 5, 1, 2),
        MappedNode("class", "Calculator", 10, 30, 5, 10),
        MappedNode("function", "cleanup", 35, 40, 12, 13),
    ]
    
    source_map = SourceMap(nodes)
    
    # Test source to summary lookups
    test_source_lines = [3, 15, 37, 50]
    for line in test_source_lines:
        node = source_map.find_summary_for_source_line(line)
        summary_line = source_map.get_summary_line_for_source_line(line)
        if node:
            print(f"Source line {line} → Node: {node.name} → Summary line: {summary_line}")
        else:
            print(f"Source line {line} → No mapping found")
    
    print()
    
    # Test summary to source lookups
    test_summary_lines = [1, 7, 12, 20]
    for line in test_summary_lines:
        node = source_map.find_source_for_summary_line(line)
        source_line = source_map.get_source_line_for_summary_line(line)
        if node:
            print(f"Summary line {line} → Node: {node.name} → Source line: {source_line}")
        else:
            print(f"Summary line {line} → No mapping found")
    
    print()


def test_serialization():
    """Test serialization functionality."""
    print("Testing Serialization:")
    print("=" * 50)
    
    # Create a source map
    nodes = [
        MappedNode("function", "init", 1, 5, 1, 2),
        MappedNode("class", "Processor", 10, 25, 5, 8),
    ]
    
    source_map = SourceMap(nodes)
    
    # Test to_dict
    map_dict = source_map.to_dict()
    print("Map as dictionary:")
    print(map_dict)
    print()
    
    # Test to_json
    map_json = source_map.to_json(indent=2)
    print("Map as JSON:")
    print(map_json)
    print()
    
    # Test round-trip serialization
    reconstructed_map = SourceMap.from_json(map_json)
    print(f"Original map nodes: {len(source_map)}")
    print(f"Reconstructed map nodes: {len(reconstructed_map)}")
    print("Round-trip serialization successful!")
    print()


def test_statistics():
    """Test statistics functionality."""
    print("Testing Statistics:")
    print("=" * 50)
    
    # Create a diverse source map
    nodes = [
        MappedNode("function", "func1", 1, 10, 1, 3),
        MappedNode("function", "func2", 15, 25, 5, 7),
        MappedNode("class", "Class1", 30, 50, 10, 15),
        MappedNode("comment", "header", 55, 60, 18, 19),
        MappedNode("comment", "footer", 65, 70, 22, 23),
    ]
    
    source_map = SourceMap(nodes)
    
    # Get statistics
    stats = source_map.get_coverage_stats()
    print("Coverage Statistics:")
    for key, value in stats.items():
        print(f"  {key}: {value}")
    
    print()
    
    # Test filtering by type
    functions = source_map.get_nodes_by_type("function")
    comments = source_map.get_nodes_by_type("comment")
    print(f"Functions found: {len(functions)}")
    print(f"Comments found: {len(comments)}")
    print()


def test_error_handling():
    """Test error handling."""
    print("Testing Error Handling:")
    print("=" * 50)
    
    try:
        # Test invalid node creation
        invalid_node = MappedNode("test", "invalid", 10, 5, 1, 2)  # start > end
        print("ERROR: Should have failed on invalid node creation")
    except ValueError as e:
        print(f"✓ Correctly caught invalid node: {e}")
    
    try:
        # Test overlapping ranges
        nodes = [
            MappedNode("function", "func1", 1, 10, 1, 3),
            MappedNode("function", "func2", 5, 15, 2, 4),  # Overlaps with func1
        ]
        source_map = SourceMap(nodes)
        print("ERROR: Should have failed on overlapping ranges")
    except ValueError as e:
        print(f"✓ Correctly caught overlapping ranges: {e}")
    
    print()


def main():
    """Run all tests."""
    print("Mapping Engine Test Suite")
    print("=" * 80)
    print()
    
    test_mapped_node()
    test_source_map()
    test_bidirectional_lookup()
    test_serialization()
    test_statistics()
    test_error_handling()
    
    print("All tests completed!")


if __name__ == "__main__":
    main()
