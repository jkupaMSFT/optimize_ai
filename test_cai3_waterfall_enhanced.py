#!/usr/bin/env python3
"""
Test enhanced CAI3 waterfall integration with better string pooling,
chain aliasing, name safety, CID aliasing, and LITE scaffolding density.
"""

import ast
import tempfile
from pathlib import Path
from optimize_ai.input_optimizer.engine.cai3_waterfall_integration import CAI3WaterfallEnhancement

# Sample Python code with various patterns to test
SAMPLE_CODE = '''
import datetime
import json
from collections import defaultdict

class DataProcessor:
    def __init__(self, config):
        self.config = config
        self.validator = self.config.get("validator", None)
        self.transform_registry = {}
    
    def validate_record(self, record):
        """Validate a record - this method should be in edit scope"""
        # TODO: Add proper validation
        if not record:
            return False
        
        # Bug pattern: modifying parameter
        record["validated"] = True
        result = self.config.get("strict_mode", False)
        
        # Chain patterns that should be aliased
        timestamp = datetime.now().isoformat()
        items_list = record.items()
        
        for key, value in items_list:
            if self.validator and self.validator.check(value):
                continue
            return False
        
        return result
    
    def transform_record(self, record):
        """Transform record data"""
        # More chain patterns
        config_value = self.config.get("transform_type", "default")
        now_str = datetime.now().isoformat()
        
        transformed = {
            "timestamp": now_str,
            "original": record,
            "config": config_value
        }
        
        return transformed
    
    def process_batch(self, records):
        """Process a batch of records"""
        results = []
        for record in records:
            if self.validate_record(record):
                transformed = self.transform_record(record)
                results.append(transformed)
        return results

def utility_function():
    """Standalone function"""
    return "utility"
'''

def test_enhanced_cai3_compression():
    """Test the enhanced CAI3 compression features"""
    print("Testing Enhanced CAI3 Compression...")
    
    # Create enhancer
    enhancer = CAI3WaterfallEnhancement()
    
    # Test with temporary file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
        f.write(SAMPLE_CODE)
        source_path = Path(f.name)
    
    try:
        # Perform compression
        result = enhancer._standard_compression_cai3(
            SAMPLE_CODE, 
            original_tokens=1000,  # Mock token count
            source_path=source_path
        )
        
        print(f"Original tokens: {result.original_tokens}")
        print(f"Compressed tokens: {result.compressed_tokens}")
        print(f"Compression ratio: {result.compression_ratio:.1f}%")
        print(f"Method used: {result.method_used}")
        print(f"Edit scope size: {result.metadata.get('edit_scope_size', 0)}")
        
        print("\n--- Compressed Content ---")
        print(result.content)
        print("--- End ---\n")
        
        # Verify compression ratio
        assert result.compression_ratio > 50, f"Expected >50% compression, got {result.compression_ratio}%"
        
        # Verify metadata
        assert result.metadata['cai3_mode'] == True
        assert result.metadata['dense_flow'] == True
        assert 'edit_scope_size' in result.metadata
        
        print("✓ Enhanced CAI3 compression test passed!")
        
    finally:
        # Clean up temp file
        source_path.unlink()

def test_string_pooling():
    """Test string pooling with frequency counting"""
    print("\nTesting String Pooling...")
    
    enhancer = CAI3WaterfallEnhancement()
    tree = ast.parse(SAMPLE_CODE)
    
    # Test chain pattern extraction
    patterns = {}
    for node in ast.walk(tree):
        pattern = enhancer._extract_chain_pattern(node)
        if pattern:
            patterns[pattern] = patterns.get(pattern, 0) + 1
    
    print("Detected chain patterns:")
    for pattern, count in sorted(patterns.items(), key=lambda x: x[1], reverse=True):
        print(f"  {pattern}: {count} times")
    
    # Verify some expected patterns - updated for our enhanced compression
    assert any('dt.now' in pattern for pattern in patterns), "Should detect datetime.now patterns"
    assert any('.items' in pattern for pattern in patterns), "Should detect .items() patterns"
    assert any('s.c.g' in pattern for pattern in patterns), "Should detect config.get patterns (compressed as s.c.g)"
    
    print("✓ String pooling test passed!")

def test_name_safety():
    """Test name safety (avoiding p\\d+ and g\\d+ patterns)"""
    print("\nTesting Name Safety...")
    
    enhancer = CAI3WaterfallEnhancement()
    used_names = set()
    
    # Test various names
    test_names = ['pool', 'get', 'param0', 'global1', 'result', 'data']
    
    for name in test_names:
        compressed = enhancer._compress_local_name(name, used_names)
        print(f"  {name} -> {compressed}")
        
        # Verify no reserved patterns
        assert not enhancer._is_reserved_pattern(compressed), f"Generated reserved pattern: {compressed}"
    
    # Test reserved pattern detection
    assert enhancer._is_reserved_pattern('p0'), "Should detect p0 as reserved"
    assert enhancer._is_reserved_pattern('g1'), "Should detect g1 as reserved" 
    assert enhancer._is_reserved_pattern('p99'), "Should detect p99 as reserved"
    assert not enhancer._is_reserved_pattern('pa'), "Should not detect pa as reserved"
    assert not enhancer._is_reserved_pattern('g'), "Should not detect g as reserved"
    
    print("✓ Name safety test passed!")

def test_include_all_methods_mode():
    """Test include_all_methods mode"""
    print("\nTesting include_all_methods mode...")
    
    # Test with include_all_methods=False (default selective mode)
    enhancer1 = CAI3WaterfallEnhancement()
    enhancer1.include_all_methods = False
    
    tree = ast.parse(SAMPLE_CODE)
    edit_scope_1 = enhancer1._determine_edit_scope_strict(tree, SAMPLE_CODE)
    print(f"Selective mode: {len(edit_scope_1)} methods selected")
    
    # Test with include_all_methods=True
    enhancer2 = CAI3WaterfallEnhancement()
    enhancer2.include_all_methods = True
    
    edit_scope_2 = enhancer2._determine_edit_scope_strict(tree, SAMPLE_CODE)
    print(f"Include all mode: {len(edit_scope_2)} methods selected")
    
    # In include_all mode, should have more methods
    assert len(edit_scope_2) >= len(edit_scope_1), "Include all mode should select same or more methods"
    
    print("✓ Include all methods mode test passed!")

if __name__ == "__main__":
    print("Running Enhanced CAI3 Waterfall Integration Tests")
    print("=" * 50)
    
    test_enhanced_cai3_compression()
    test_string_pooling() 
    test_name_safety()
    test_include_all_methods_mode()
    
    print("\n" + "=" * 50)
    print("All tests passed! ✓")
