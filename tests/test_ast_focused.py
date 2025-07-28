#!/usr/bin/env python3
"""
Quick test to identify and fix the failing test case.
"""

import sys
import os
import tempfile

# Add the parent directories to sys.path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from utils.logger import setup_minifier_logging
from engine.mapping.ast_map import ASTMapper, walk_ast_and_map, validate_non_overlapping, MappedNode


def test_json_serialization_focused():
    """Test JSON serialization and deserialization with detailed debugging."""
    print("🧪 Testing JSON Serialization (Focused)...")
    
    logger = setup_minifier_logging(
        log_level="DEBUG",
        log_file="logs/ast_mapper_test.log",
        enable_console=False,
        enable_file=True,
        enable_metrics=True,
        enable_performance=True,
        enable_ast_details=True,
        production_mode=False
    )
    
    code = """
import json
from typing import Dict

class DataProcessor:
    def __init__(self):
        self.data = {}
    
    def process(self, input_data: Dict):
        return json.dumps(input_data)
"""
    
    try:
        # Create mapper and process code
        mapper = ASTMapper({'import': 1.0, 'class': 0.6, 'method': 0.4}, logger)
        nodes = mapper.walk_ast(code)
        
        print(f"   Created mapper with {len(nodes)} nodes")
        
        # Test to_dict
        mapper_dict = mapper.to_dict()
        print(f"   to_dict() keys: {list(mapper_dict.keys())}")
        
        assert 'nodes' in mapper_dict, "Missing 'nodes' key in dict"
        assert 'metadata' in mapper_dict, "Missing 'metadata' key in dict"
        assert len(mapper_dict['nodes']) == len(nodes), f"Node count mismatch: {len(mapper_dict['nodes'])} vs {len(nodes)}"
        
        print(f"   ✓ Serialized {len(nodes)} nodes to dict")
        
        # Test JSON save/load
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            temp_path = f.name
        
        try:
            mapper.save_to_json(temp_path)
            print(f"   ✓ Saved to JSON file: {temp_path}")
            
            # Load and verify
            loaded_mapper = ASTMapper.load_from_json(temp_path)
            print(f"   ✓ Loaded mapper with {len(loaded_mapper.mapped_nodes)} nodes")
            
            assert len(loaded_mapper.mapped_nodes) == len(mapper.mapped_nodes), \
                f"Loaded node count mismatch: {len(loaded_mapper.mapped_nodes)} vs {len(mapper.mapped_nodes)}"
            assert loaded_mapper.compression_ratios == mapper.compression_ratios, \
                f"Compression ratios mismatch: {loaded_mapper.compression_ratios} vs {mapper.compression_ratios}"
            
            print(f"   ✓ Successfully saved and loaded JSON file")
            
        finally:
            # Clean up
            if os.path.exists(temp_path):
                os.unlink(temp_path)
        
        print("   ✓ JSON serialization test passed")
        return True
        
    except Exception as e:
        print(f"   ✗ JSON serialization test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_error_handling_focused():
    """Test error handling with detailed debugging."""
    print("🧪 Testing Error Handling (Focused)...")
    
    logger = setup_minifier_logging(
        log_level="DEBUG",
        log_file="logs/ast_mapper_test.log",
        enable_console=False,
        enable_file=True,
        production_mode=False
    )
    
    # Test with syntax error
    invalid_code = """
def broken_function(
    # Missing closing parenthesis
    return "broken"
"""
    
    try:
        try:
            nodes = walk_ast_and_map(invalid_code, minifier_logger=logger)
            print(f"   ✗ Should have raised SyntaxError, but got {len(nodes)} nodes")
            return False
        except SyntaxError as e:
            print(f"   ✓ Correctly caught SyntaxError: {e}")
        
        # Test validation with overlapping ranges (manually create invalid nodes)
        try:
            # Create invalid overlapping nodes manually
            invalid_nodes = [
                MappedNode("function", "func1", 1, 5, 1, 3),
                MappedNode("function", "func2", 3, 7, 2, 4),  # Overlaps in source
            ]
            validate_non_overlapping(invalid_nodes)
            print("   ✗ Should have caught overlapping ranges")
            return False
        except ValueError as e:
            print(f"   ✓ Correctly caught overlapping ranges: {e}")
        
        print("   ✓ Error handling test passed")
        return True
        
    except Exception as e:
        print(f"   ✗ Error handling test failed unexpectedly: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    # Ensure logs directory exists
    os.makedirs("logs", exist_ok=True)
    
    print("🔍 Focused Test Suite")
    print("=" * 40)
    
    tests = [
        test_json_serialization_focused,
        test_error_handling_focused,
    ]
    
    passed = 0
    failed = 0
    
    for test_func in tests:
        try:
            if test_func():
                passed += 1
            else:
                failed += 1
        except Exception as e:
            failed += 1
            print(f"   ✗ {test_func.__name__} failed with error: {e}")
            import traceback
            traceback.print_exc()
        
        print()  # Add spacing between tests
    
    print("=" * 40)
    print(f"Results: {passed} passed, {failed} failed")
    sys.exit(0 if failed == 0 else 1)
