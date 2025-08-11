#!/usr/bin/env python3
"""
Test script to verify enhanced CAI3 compression achieves 70-90% reduction.
Run this after implementing the enhanced modules.
"""

import tempfile
from pathlib import Path
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from optimize_ai.input_optimizer.engine.cai3_waterfall_integration import (
    CAI3WaterfallEnhancement, enhance_waterfall_with_cai3
)
from optimize_ai.input_optimizer.engine.compression_types import CompressionResult, CompressionTier

# Test source code (same as your example)
TEST_SOURCE = '''
class DataProcessor:
    def __init__(self, config):
        self.config = config
        self.processed_count = 0
        self.error_count = 0
    
    def validate_record(self, record):
        """Validate a record - HAS BUG: mutates input"""
        # TODO: Fix mutation bug
        required_fields = self.config.get('required_fields', [])
        for field in required_fields:
            if field not in record or record[field] is None:
                return False
            # BUG: This mutates the input record!
            record[field] = str(record[field])
        
        type_validation = self.config.get('type_validation', {})
        for field, expected_type in type_validation.items():
            if field in record and not isinstance(record[field], expected_type):
                try:
                    record[field] = expected_type(record[field])
                except (ValueError, TypeError):
                    return False
        return True
    
    def transform_record(self, record):
        """Transform a record - this is fine"""
        result = record.copy()
        
        # Apply field mappings
        field_mappings = self.config.get('field_mappings', {})
        for old_field, new_field in field_mappings.items():
            if old_field in result:
                result[new_field] = result.pop(old_field)
        
        # Apply transformations
        transformations = self.config.get('transformations', {})
        for field, transform_func in transformations.items():
            if field in result:
                result[field] = transform_func(result[field])
        
        # Add metadata
        from datetime import datetime
        result['processed_at'] = datetime.now().isoformat()
        result['processor_version'] = "1.0"
        
        return result
    
    def process_batch(self, records):
        """Process a batch of records"""
        results = []
        for record in records:
            try:
                if self.validate_record(record):
                    transformed = self.transform_record(record)
                    results.append(transformed)
                    self.processed_count += 1
                else:
                    self.error_count += 1
            except Exception as e:
                self.error_count += 1
                print(f"Error processing record: {e}")
        return results
'''

def test_enhanced_compression():
    """Test the enhanced CAI3 compression"""
    
    print("=" * 70)
    print("🚀 Testing Enhanced CAI3 Compression")
    print("=" * 70)
    
    # Create a mock WaterfallCompressor class
    class MockWaterfallCompressor:
        def __init__(self, include_all_methods=False):
            self.llm_model = "gpt-4"
            self.use_cai3_mode = True
            self.include_all_methods = include_all_methods
            import logging
            self.logger = logging.getLogger(__name__)
        
        def _determine_tier(self, tokens):
            if tokens < 100:
                return CompressionTier.MINIMAL
            elif tokens < 500:
                return CompressionTier.MEDIUM
            else:
                return CompressionTier.AGGRESSIVE
    
    # Enhance with CAI3
    enhance_waterfall_with_cai3(MockWaterfallCompressor)
    
    # Create compressor instance
    compressor = MockWaterfallCompressor()
    
    # Create temporary file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
        f.write(TEST_SOURCE)
        temp_path = Path(f.name)
    
    try:
        # Test compression
        original_tokens = 446  # Known token count from your test
        result = compressor._standard_compression_cai3(TEST_SOURCE, original_tokens, temp_path)
        
        print(f"✅ Enhanced CAI3 compression completed!")
        print(f"   Original tokens: {original_tokens}")
        print(f"   Compressed tokens: {result.compressed_tokens}")
        print(f"   Compression ratio: {result.compression_ratio:.1f}%")
        print(f"   Method used: {result.method_used}")
        print(f"   Tier used: {result.tier_used}")
        
        # Show the original code first
        print("\n📋 Original Source Code:")
        print("=" * 50)
        print(TEST_SOURCE)
        print("=" * 50)
        
        # Show the compressed output
        print("\n📋 Enhanced CAI3-LITE Output:")
        print("=" * 50)
        print(result.content)
        print("=" * 50)
        
        # Analyze the compression
        print("\n📊 Compression Analysis:")
        original_chars = len(TEST_SOURCE)
        compressed_chars = len(result.content)
        char_reduction = ((original_chars - compressed_chars) / original_chars) * 100
        
        print(f"   Character reduction: {char_reduction:.1f}%")
        print(f"   Original: {original_chars} chars")
        print(f"   Compressed: {compressed_chars} chars")
        
        # Show line-by-line comparison
        print("\n📋 Line Count Comparison:")
        original_lines = TEST_SOURCE.strip().split('\n')
        compressed_lines = result.content.strip().split('\n')
        print(f"   Original lines: {len(original_lines)}")
        print(f"   Compressed lines: {len(compressed_lines)}")
        print(f"   Line reduction: {((len(original_lines) - len(compressed_lines)) / len(original_lines)) * 100:.1f}%")
        
        # Check if we achieved target compression
        if result.compression_ratio >= 70:
            print(f"\n✅ SUCCESS: Achieved {result.compression_ratio:.1f}% token reduction!")
            print("   Target of 70-90% compression ACHIEVED! 🎉")
        elif result.compression_ratio >= 50:
            print(f"\n⚠️  PARTIAL: Achieved {result.compression_ratio:.1f}% token reduction")
            print("   Good progress but below 70% target")
        else:
            print(f"\n❌ NEEDS WORK: Only {result.compression_ratio:.1f}% token reduction")
            print("   Compression needs further optimization")
        
        # Show what a dense FLOW body looks like
        print("\n📝 Example Dense FLOW Body:")
        print("-" * 40)
        example_flow = """Bmt_961c:
L rf=C(s.c.g,'rf',[])
F f∈rf:
 I(f∉r|N(r[f])):R F
 L r[f]=C(st,r[f])
L tv=C(s.c.g,'tv',{})
F(f,et)∈C(tv.i):
 I(f∈r&!is(r[f],et)):
  T:L r[f]=C(et,r[f])
  X(VE,TE):R F
R T
E"""
        print(example_flow)
        print("-" * 40)
        
    finally:
        # Clean up
        temp_path.unlink()
    
    print("\n" + "=" * 70)
    print("Test complete! Check the output above for compression results.")
    print("=" * 70)

def test_all_methods_compression():
    """Test compression with all methods included"""
    
    print("\n" + "=" * 70)
    print("🔬 Testing All Methods Compression Mode")
    print("=" * 70)
    
    # Create a mock WaterfallCompressor class with all methods flag
    class MockWaterfallCompressor:
        def __init__(self, include_all_methods=False):
            self.llm_model = "gpt-4"
            self.use_cai3_mode = True
            self.include_all_methods = include_all_methods
            import logging
            self.logger = logging.getLogger(__name__)
        
        def _determine_tier(self, tokens):
            if tokens < 100:
                return CompressionTier.MINIMAL
            elif tokens < 500:
                return CompressionTier.MEDIUM
            else:
                return CompressionTier.AGGRESSIVE
    
    # Enhance with CAI3
    enhance_waterfall_with_cai3(MockWaterfallCompressor)
    
    # Test both modes
    print("\n🎯 Comparing Selective vs All Methods Compression:")
    
    # Create temporary file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
        f.write(TEST_SOURCE)
        temp_path = Path(f.name)
    
    try:
        original_tokens = 446
        
        # Test selective compression (default)
        compressor_selective = MockWaterfallCompressor(include_all_methods=False)
        result_selective = compressor_selective._standard_compression_cai3(TEST_SOURCE, original_tokens, temp_path)
        
        # Test all methods compression
        compressor_all = MockWaterfallCompressor(include_all_methods=True)
        result_all = compressor_all._standard_compression_cai3(TEST_SOURCE, original_tokens, temp_path)
        
        # Compare results
        print(f"\n📊 Compression Comparison:")
        print(f"   Selective (2 methods): {result_selective.compressed_tokens} tokens ({result_selective.compression_ratio:.1f}% reduction)")
        print(f"   All methods: {result_all.compressed_tokens} tokens ({result_all.compression_ratio:.1f}% reduction)")
        
        methods_diff = result_all.metadata.get('edit_scope_size', 0) - result_selective.metadata.get('edit_scope_size', 0)
        print(f"   Additional methods included: {methods_diff}")
        
        # Show all methods output
        print("\n📋 All Methods CAI3-LITE Output:")
        print("=" * 50)
        print(result_all.content)
        print("=" * 50)
        
        # Analysis
        token_increase = result_all.compressed_tokens - result_selective.compressed_tokens
        print(f"\n📈 Analysis:")
        print(f"   Token increase with all methods: +{token_increase} tokens")
        print(f"   Trade-off: More complete code representation vs compression ratio")
        
        if result_all.compression_ratio >= 60:
            print(f"\n✅ EXCELLENT: All methods compression still achieves {result_all.compression_ratio:.1f}% reduction!")
        elif result_all.compression_ratio >= 40:
            print(f"\n⚠️  GOOD: All methods compression achieves {result_all.compression_ratio:.1f}% reduction")
        else:
            print(f"\n❌ NEEDS WORK: All methods compression only achieves {result_all.compression_ratio:.1f}% reduction")
        
    finally:
        # Clean up
        temp_path.unlink()
    
    print("\n" + "=" * 70)
    print("All methods compression test complete!")
    print("=" * 70)

def compare_versions():
    """Compare original vs enhanced compression"""
    print("\n📊 Compression Comparison:")
    print("-" * 50)
    
    # Original CAI3 stats (from your test)
    original_stats = {
        "tokens_before": 446,
        "tokens_after": 398,
        "reduction": 10.8,
        "chars_before": 2395,
        "chars_after": 1391
    }
    
    # Expected enhanced stats
    expected_stats = {
        "tokens_before": 446,
        "tokens_after": 100,  # Target
        "reduction": 77.6,
        "chars_before": 2395,
        "chars_after": 400   # Target
    }
    
    print("Original CAI3:")
    print(f"  Tokens: {original_stats['tokens_before']} → {original_stats['tokens_after']} ({original_stats['reduction']:.1f}% reduction)")
    print(f"  Chars: {original_stats['chars_before']} → {original_stats['chars_after']}")
    
    print("\nEnhanced CAI3 (Target):")
    print(f"  Tokens: {expected_stats['tokens_before']} → {expected_stats['tokens_after']} ({expected_stats['reduction']:.1f}% reduction)")
    print(f"  Chars: {expected_stats['chars_before']} → {expected_stats['chars_after']}")
    
    print("\n🎯 Key Improvements:")
    print("  • Single-char FLOW macros (LET→L, CALL→C)")
    print("  • Local variable compression (required_fields→rf)")
    print("  • String pooling ($p0 references)")
    print("  • Strict edit scope (max 2 methods)")
    print("  • Ultra-compact signatures ((r)->b)")

if __name__ == "__main__":
    test_enhanced_compression()
    test_all_methods_compression()
    compare_versions()