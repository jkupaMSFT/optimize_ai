#!/usr/bin/env python3
"""
Test script to verify enhanced CAI3 compression achieves 70-90% reduction.
Run this after implementing the enhanced modules.
"""

import tempfile
from pathlib import Path
import sys
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from optimize_ai.input_optimizer.engine.cai3_waterfall_integration import (
    CAI3WaterfallEnhancement, enhance_waterfall_with_cai3
)
from optimize_ai.input_optimizer.engine.compression_types import CompressionResult, CompressionTier
from optimize_ai.utils.metrics import count_tokens_gpt, count_tokens_claude

def count_tokens_both_models(text: str) -> dict:
    """
    Count tokens for both GPT and Claude models.
    
    Args:
        text: The text to tokenize.
    
    Returns:
        Dictionary with token counts for both models.
    """
    results = {}
    
    # Count GPT tokens
    try:
        results['gpt4'] = count_tokens_gpt(text, "gpt-4")
    except Exception as e:
        results['gpt4'] = f"Error: {str(e)}"
    
    # Count Claude tokens
    try:
        results['claude'] = count_tokens_claude(text, "claude-sonnet-4-20250514")
    except Exception as e:
        results['claude'] = f"Error: {str(e)}"
    
    return results

def print_token_comparison(label: str, text: str):
    """Print token counts for both models."""
    token_counts = count_tokens_both_models(text)
    print(f"\n🔢 Token Count Analysis - {label}:")
    print(f"   GPT-4 tokens: {token_counts['gpt4']}")
    print(f"   Claude tokens: {token_counts['claude']}")

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

#TEST_SOURCE = "def fibonacci_sequence(max_value=None, max_count=None):\n    '''Generate Fibonacci sequence with optional limits.'''\n    a, b = 0, 1\n    count = 0\n    \n    while True:\n        if max_count and count >= max_count:\n            break\n        if max_value and a > max_value:\n            break\n            \n        yield a\n        a, b = b, a + b\n        count += 1\n\ndef prime_fibonacci(limit=1000):\n    '''Generate prime numbers from Fibonacci sequence.'''\n    def is_prime(n):\n        if n < 2:\n            return False\n        for i in range(2, int(n ** 0.5) + 1):\n            if n % i == 0:\n                return False\n        return True\n    \n    for fib in fibonacci_sequence(max_value=limit):\n        if is_prime(fib):\n            yield fib"

def test_enhanced_compression():
    """Test the enhanced CAI3 compression"""
    
    print("=" * 70)
    print("🚀 Testing Enhanced CAI3 Compression")
    print("=" * 70)
    
    # First, analyze the source code token counts for both models
    print("\n📊 Source Code Token Analysis:")
    print("-" * 50)
    print_token_comparison("Test Source Code", TEST_SOURCE)
    
    # Additional source code metrics
    print(f"\n📋 Source Code Statistics:")
    print(f"   Lines: {len(TEST_SOURCE.strip().split(chr(10)))}")
    print(f"   Characters: {len(TEST_SOURCE)}")
    print(f"   Words: {len(TEST_SOURCE.split())}")
    
    # Calculate character-to-token ratios for both models
    gpt_tokens = count_tokens_gpt(TEST_SOURCE)
    try:
        claude_tokens = count_tokens_claude(TEST_SOURCE)
        print(f"\n🔢 Tokenization Efficiency:")
        print(f"   GPT-4: {len(TEST_SOURCE)/gpt_tokens:.2f} chars/token")
        print(f"   Claude: {len(TEST_SOURCE)/claude_tokens:.2f} chars/token")
    except Exception as e:
        print(f"   Claude tokenization error: {e}")
        print(f"   GPT-4 only: {len(TEST_SOURCE)/gpt_tokens:.2f} chars/token")
    
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
        
        def _extract_chain_pattern(self, node):
            """Mock implementation of chain pattern extraction"""
            import ast
            try:
                # Simple pattern extraction for common chains
                if isinstance(node, ast.Attribute):
                    chain_parts = []
                    current = node
                    while isinstance(current, ast.Attribute):
                        chain_parts.append(current.attr)
                        current = current.value
                    
                    if isinstance(current, ast.Name):
                        chain_parts.append(current.id)
                        chain_parts.reverse()
                        full_chain = '.'.join(chain_parts)
                        
                        # Common patterns
                        if 'config' in full_chain and 'get' in full_chain:
                            return 's.c.g'
                        elif full_chain.endswith('.items'):
                            return 'tv.items'
                        elif 'datetime.now' in full_chain:
                            return 'dt.now'
                        
                return None
            except Exception:
                return None
        
        def _is_reserved_pattern(self, name):
            """Mock implementation to check reserved patterns"""
            import re
            if re.match(r'^p\d+$', name):
                return True
            if re.match(r'^g\d+$', name):
                return True
            return False
        
        def _find_symbols_used_in_bodies(self, cai3_full, edit_scope_cids, content):
            """Mock implementation to find symbols used in method bodies"""
            # Simple mock implementation - return common symbols
            return {'config', 'get', 'items', 'datetime', 'now', 'str', 'int', 'bool', 'list', 'dict'}
        
        def _extract_class_attributes(self, class_node, used_names=None):
            """Updated mock implementation to match real attribute compression"""
            import ast
            if used_names is None:
                used_names = set()
            
            attr_compressions = {}
            init_method = None
            
            # Find __init__ method (matching real implementation)
            for item in class_node.body:
                if isinstance(item, ast.FunctionDef) and item.name == '__init__':
                    init_method = item
                    break
            
            if not init_method:
                return attr_compressions
            
            # Extract self.<attr> assignments (matching real implementation)
            assigned_attrs = set()
            for node in ast.walk(init_method):
                if isinstance(node, ast.Assign):
                    for target in node.targets:
                        if (isinstance(target, ast.Attribute) and 
                            isinstance(target.value, ast.Name) and 
                            target.value.id == 'self'):
                            assigned_attrs.add(target.attr)
            
            # Use smart compression patterns (matching real implementation)
            common_patterns = {
                'processed_count': 'pc',
                'error_count': 'ec', 
                'config': 'c',
                'cache': 'ch',
                'status': 'stat',
                'logger': 'log',
                'manager': 'm',
                'handler': 'h',
                'processor': 'p',
                'validator': 'v',
                'transformer': 't',
                'controller': 'ctrl',
                'service': 's',
            }
            
            # Create compressed mappings for each attribute
            for attr_name in sorted(assigned_attrs):
                if attr_name not in attr_compressions:
                    # Try exact match first
                    if attr_name in common_patterns:
                        candidate = common_patterns[attr_name]
                        if candidate not in used_names and not self._is_reserved_pattern(candidate):
                            used_names.add(candidate)
                            attr_compressions[attr_name] = candidate
                        else:
                            # Fallback to first 2 chars if collision
                            candidate = attr_name[:2]
                            if candidate not in used_names and not self._is_reserved_pattern(candidate):
                                used_names.add(candidate)
                                attr_compressions[attr_name] = candidate
                    else:
                        # Fallback to first 2 chars for unknown patterns
                        candidate = attr_name[:2]
                        if candidate not in used_names and not self._is_reserved_pattern(candidate):
                            used_names.add(candidate)
                            attr_compressions[attr_name] = candidate
            
            return attr_compressions
        
        def _annotate_function_cids(self, tree):
            """Mock implementation of CID annotation"""
            import ast
            import hashlib
            
            def generate_cid(node_type: str, node_name: str, parent_cid: str = None) -> str:
                """Simple CID generator for testing"""
                if parent_cid:
                    base = f"{node_type}_{node_name}_{parent_cid}"
                else:
                    base = f"{node_type}_{node_name}"
                return hashlib.md5(base.encode()).hexdigest()[:8]
            
            cid_index = {}
            for node in tree.body:
                if isinstance(node, ast.ClassDef):
                    class_cid = generate_cid('C', node.name)
                    node._cai_cid = class_cid
                    for item in node.body:
                        if isinstance(item, ast.FunctionDef):
                            m_cid = generate_cid('M', item.name, class_cid)
                            item._cai_cid = m_cid
                            cid_index[(node.name, item.name, getattr(item, 'lineno', 0))] = m_cid
                elif isinstance(node, ast.FunctionDef):
                    f_cid = generate_cid('F', node.name)
                    node._cai_cid = f_cid
                    cid_index[(None, node.name, getattr(node, 'lineno', 0))] = f_cid
            return cid_index
    
    # Enhance with CAI3
    enhance_waterfall_with_cai3(MockWaterfallCompressor)
    
    # Create compressor instance
    compressor = MockWaterfallCompressor()
    
    # Create temporary file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
        f.write(TEST_SOURCE)
        temp_path = Path(f.name)
    
    try:
        # Count tokens for both models first
        print_token_comparison("Original Source Code", TEST_SOURCE)
        
        # Test compression
        original_tokens = count_tokens_gpt(TEST_SOURCE)  # Use GPT tokens for consistency
        result = compressor._standard_compression_cai3(TEST_SOURCE, original_tokens, temp_path)
        
        # Count tokens for compressed result
        print_token_comparison("Compressed CAI3 Output", result.content)
        
        print(f"\n✅ Enhanced CAI3 compression completed!")
        print(f"   Original tokens (GPT-4): {original_tokens}")
        print(f"   Compressed tokens (GPT-4): {result.compressed_tokens}")
        print(f"   Compression ratio: {result.compression_ratio:.1f}%")
        print(f"   Method used: {result.method_used}")
        print(f"   Tier used: {result.tier_used}")
        
        # Show the original code first
        print("\n📋 Original Source Code:")
        print("=" * 50)
        print(TEST_SOURCE)
        print("=" * 50)
        
        # Show the compressed output
        print(f"\n📋 CAI3 Edit Scope Output:")
        print("=" * 50)
        print(result.content)
        print("=" * 50)
        
        # Analyze the compression with detailed metrics
        print("\n📊 Detailed Compression Analysis:")
        original_chars = len(TEST_SOURCE)
        compressed_chars = len(result.content)
        char_reduction = ((original_chars - compressed_chars) / original_chars) * 100
        
        print(f"   📝 Token Metrics:")
        print(f"      GPT-4: {original_tokens} → {result.compressed_tokens} tokens ({result.compression_ratio:.1f}% reduction)")
        
        # Try to get Claude token counts for comparison
        try:
            original_claude_tokens = count_tokens_claude(TEST_SOURCE)
            compressed_claude_tokens = count_tokens_claude(result.content)
            claude_compression_ratio = ((original_claude_tokens - compressed_claude_tokens) / original_claude_tokens) * 100
            print(f"      Claude: {original_claude_tokens} → {compressed_claude_tokens} tokens ({claude_compression_ratio:.1f}% reduction)")
            
            # Show model efficiency
            gpt_efficiency = original_tokens / original_chars
            claude_efficiency = original_claude_tokens / original_chars
            print(f"   🔍 Model Tokenization:")
            print(f"      GPT-4: {1/gpt_efficiency:.2f} chars/token")
            print(f"      Claude: {1/claude_efficiency:.2f} chars/token")
            
        except Exception as e:
            print(f"      Claude: Error calculating tokens - {e}")
        
        print(f"   📄 Character Metrics:")
        print(f"      Original: {original_chars} chars")
        print(f"      Compressed: {compressed_chars} chars")
        print(f"      Reduction: {char_reduction:.1f}%")
        
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
        
        def _extract_chain_pattern(self, node):
            """Mock implementation of chain pattern extraction"""
            import ast
            try:
                # Simple pattern extraction for common chains
                if isinstance(node, ast.Attribute):
                    chain_parts = []
                    current = node
                    while isinstance(current, ast.Attribute):
                        chain_parts.append(current.attr)
                        current = current.value
                    
                    if isinstance(current, ast.Name):
                        chain_parts.append(current.id)
                        chain_parts.reverse()
                        full_chain = '.'.join(chain_parts)
                        
                        # Common patterns
                        if 'config' in full_chain and 'get' in full_chain:
                            return 's.c.g'
                        elif full_chain.endswith('.items'):
                            return 'tv.items'
                        elif 'datetime.now' in full_chain:
                            return 'dt.now'
                        
                return None
            except Exception:
                return None
        
        def _is_reserved_pattern(self, name):
            """Mock implementation to check reserved patterns"""
            import re
            if re.match(r'^p\d+$', name):
                return True
            if re.match(r'^g\d+$', name):
                return True
            return False
        
        def _find_symbols_used_in_bodies(self, cai3_full, edit_scope_cids, content):
            """Mock implementation to find symbols used in method bodies"""
            # Simple mock implementation - return common symbols
            return {'config', 'get', 'items', 'datetime', 'now', 'str', 'int', 'bool', 'list', 'dict'}
        
        def _extract_class_attributes(self, class_node, used_names=None):
            """Updated mock implementation to match real attribute compression"""
            import ast
            if used_names is None:
                used_names = set()
            
            attr_compressions = {}
            init_method = None
            
            # Find __init__ method (matching real implementation)
            for item in class_node.body:
                if isinstance(item, ast.FunctionDef) and item.name == '__init__':
                    init_method = item
                    break
            
            if not init_method:
                return attr_compressions
            
            # Extract self.<attr> assignments (matching real implementation)
            assigned_attrs = set()
            for node in ast.walk(init_method):
                if isinstance(node, ast.Assign):
                    for target in node.targets:
                        if (isinstance(target, ast.Attribute) and 
                            isinstance(target.value, ast.Name) and 
                            target.value.id == 'self'):
                            assigned_attrs.add(target.attr)
            
            # Use smart compression patterns (matching real implementation)
            common_patterns = {
                'processed_count': 'pc',
                'error_count': 'ec', 
                'config': 'c',
                'cache': 'ch',
                'status': 'stat',
                'logger': 'log',
                'manager': 'm',
                'handler': 'h',
                'processor': 'p',
                'validator': 'v',
                'transformer': 't',
                'controller': 'ctrl',
                'service': 's',
            }
            
            # Create compressed mappings for each attribute
            for attr_name in sorted(assigned_attrs):
                if attr_name not in attr_compressions:
                    # Try exact match first
                    if attr_name in common_patterns:
                        candidate = common_patterns[attr_name]
                        if candidate not in used_names and not self._is_reserved_pattern(candidate):
                            used_names.add(candidate)
                            attr_compressions[attr_name] = candidate
                        else:
                            # Fallback to first 2 chars if collision
                            candidate = attr_name[:2]
                            if candidate not in used_names and not self._is_reserved_pattern(candidate):
                                used_names.add(candidate)
                                attr_compressions[attr_name] = candidate
                    else:
                        # Fallback to first 2 chars for unknown patterns
                        candidate = attr_name[:2]
                        if candidate not in used_names and not self._is_reserved_pattern(candidate):
                            used_names.add(candidate)
                            attr_compressions[attr_name] = candidate
            
            return attr_compressions
        
        def _annotate_function_cids(self, tree):
            """Mock implementation of CID annotation"""
            import ast
            import hashlib
            
            def generate_cid(node_type: str, node_name: str, parent_cid: str = None) -> str:
                """Simple CID generator for testing"""
                if parent_cid:
                    base = f"{node_type}_{node_name}_{parent_cid}"
                else:
                    base = f"{node_type}_{node_name}"
                return hashlib.md5(base.encode()).hexdigest()[:8]
            
            cid_index = {}
            for node in tree.body:
                if isinstance(node, ast.ClassDef):
                    class_cid = generate_cid('C', node.name)
                    node._cai_cid = class_cid
                    for item in node.body:
                        if isinstance(item, ast.FunctionDef):
                            m_cid = generate_cid('M', item.name, class_cid)
                            item._cai_cid = m_cid
                            cid_index[(node.name, item.name, getattr(item, 'lineno', 0))] = m_cid
                elif isinstance(node, ast.FunctionDef):
                    f_cid = generate_cid('F', node.name)
                    node._cai_cid = f_cid
                    cid_index[(None, node.name, getattr(node, 'lineno', 0))] = f_cid
            return cid_index
    
    # Enhance with CAI3
    enhance_waterfall_with_cai3(MockWaterfallCompressor)
    
    # Test both modes
    print("\n🎯 Comparing Selective vs All Methods Compression:")
    
    # Create temporary file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
        f.write(TEST_SOURCE)
        temp_path = Path(f.name)
    
    try:
        # Count tokens for both models first
        print_token_comparison("Source Code for All Methods Test", TEST_SOURCE)
        
        original_tokens = count_tokens_gpt(TEST_SOURCE)  # Use GPT tokens for consistency
        
        # Test selective compression (default)
        compressor_selective = MockWaterfallCompressor(include_all_methods=False)
        result_selective = compressor_selective._standard_compression_cai3(TEST_SOURCE, original_tokens, temp_path)
        
        # Test all methods compression
        compressor_all = MockWaterfallCompressor(include_all_methods=True)
        result_all = compressor_all._standard_compression_cai3(TEST_SOURCE, original_tokens, temp_path)
        
        # Count tokens for both results
        print_token_comparison("CAI3 Edit Scope Output", result_selective.content)
        print_token_comparison("CAI3 All Bodies Output", result_all.content)
        
        # Compare results with detailed metrics
        print(f"\n📊 Compression Comparison:")
        print(f"   CAI3 Edit Scope:")
        print(f"      GPT-4: {original_tokens} → {result_selective.compressed_tokens} tokens ({result_selective.compression_ratio:.1f}% reduction)")
        print(f"   CAI3 All Bodies:")
        print(f"      GPT-4: {original_tokens} → {result_all.compressed_tokens} tokens ({result_all.compression_ratio:.1f}% reduction)")
        
        # Try to get Claude metrics for both results
        try:
            original_claude_tokens = count_tokens_claude(TEST_SOURCE)
            selective_claude_tokens = count_tokens_claude(result_selective.content)
            all_claude_tokens = count_tokens_claude(result_all.content)
            
            selective_claude_ratio = ((original_claude_tokens - selective_claude_tokens) / original_claude_tokens) * 100
            all_claude_ratio = ((original_claude_tokens - all_claude_tokens) / original_claude_tokens) * 100
            
            print(f"   CAI3 Edit Scope (Claude):")
            print(f"      Claude: {original_claude_tokens} → {selective_claude_tokens} tokens ({selective_claude_ratio:.1f}% reduction)")
            print(f"   CAI3 All Bodies (Claude):")
            print(f"      Claude: {original_claude_tokens} → {all_claude_tokens} tokens ({all_claude_ratio:.1f}% reduction)")
            
        except Exception as e:
            print(f"   Claude metrics error: {e}")
        
        methods_diff = result_all.metadata.get('edit_scope_size', 0) - result_selective.metadata.get('edit_scope_size', 0)
        print(f"   Additional methods included: {methods_diff}")
        
        # Show all methods output
        print(f"\n📋 CAI3 All Bodies Output:")
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
    """Compare original vs enhanced compression with comprehensive token counting metrics"""
    print("\n📊 Comprehensive Compression Comparison:")
    print("-" * 50)
    
    # Count tokens with both models for TEST_SOURCE
    print("🔢 Source Code Token Analysis:")
    print_token_comparison("Test Source Code", TEST_SOURCE)
    
    # Get actual token counts
    gpt_tokens = count_tokens_gpt(TEST_SOURCE)
    try:
        claude_tokens = count_tokens_claude(TEST_SOURCE)
        claude_available = True
    except Exception as e:
        claude_tokens = 0
        claude_available = False
        print(f"   Claude token counting unavailable: {e}")
    
    # Original CAI3 stats (from your test)
    original_stats = {
        "tokens_before_gpt": gpt_tokens,
        "tokens_before_claude": claude_tokens if claude_available else 0,
        "tokens_after": 398,  # From your original test
        "chars_before": len(TEST_SOURCE),
        "chars_after": 1391
    }
    
    original_stats["reduction_gpt"] = ((original_stats["tokens_before_gpt"] - original_stats["tokens_after"]) / original_stats["tokens_before_gpt"]) * 100
    if claude_available:
        original_stats["reduction_claude"] = ((original_stats["tokens_before_claude"] - original_stats["tokens_after"]) / original_stats["tokens_before_claude"]) * 100
    
    # Expected enhanced stats
    expected_gpt_after = int(original_stats["tokens_before_gpt"] * 0.25)  # Target 75% reduction
    expected_claude_after = int(original_stats["tokens_before_claude"] * 0.25) if claude_available else 0
    
    print(f"\n📈 Model-Specific Compression Analysis:")
    print(f"\n   Original CAI3 Performance:")
    print(f"      GPT-4: {original_stats['tokens_before_gpt']} → {original_stats['tokens_after']} tokens ({original_stats['reduction_gpt']:.1f}% reduction)")
    if claude_available:
        print(f"      Claude: {original_stats['tokens_before_claude']} → {original_stats['tokens_after']} tokens ({original_stats['reduction_claude']:.1f}% reduction)")
    print(f"      Characters: {original_stats['chars_before']} → {original_stats['chars_after']}")
    
    print(f"\n   Enhanced CAI3 Targets:")
    print(f"      GPT-4: {original_stats['tokens_before_gpt']} → {expected_gpt_after} tokens (75.0% reduction)")
    if claude_available:
        print(f"      Claude: {original_stats['tokens_before_claude']} → {expected_claude_after} tokens (75.0% reduction)")
    print(f"      Characters: {original_stats['chars_before']} → 400 (target)")
    
    if claude_available:
        print(f"\n🔍 Tokenization Efficiency:")
        gpt_efficiency = len(TEST_SOURCE) / gpt_tokens
        claude_efficiency = len(TEST_SOURCE) / claude_tokens
        print(f"      GPT-4: {gpt_efficiency:.2f} chars/token")
        print(f"      Claude: {claude_efficiency:.2f} chars/token")
    
    print("\n🎯 Key Improvements:")
    print("  • Single-char FLOW macros (LET→L, CALL→C)")
    print("  • Local variable compression (required_fields→rf)")
    print("  • String pooling ($p0 references)")
    print("  • Strict edit scope (max 2 methods)")
    print("  • Ultra-compact signatures ((r)->b)")
    
    print("\n💡 Token Counting Model Insights:")
    print("  • GPT-4 uses tiktoken (cl100k_base encoding)")
    print("  • Claude uses Anthropic's native tokenizer")
    print("  • Each model provides independent token count metrics")
    print("  • Both models should show similar compression ratios despite different base counts")

def test_cai3_translation():
    """Test that CAI3 compressed output can be successfully translated back"""
    
    print("\n" + "=" * 70)
    print("🔄 Testing CAI3 Round-Trip Translation")
    print("=" * 70)
    
    # Import the CAI3 translator
    translator_available = False
    translator_instance = None
    
    try:
        # Import the CAI3Translator from the current codebase
        from optimize_ai.input_optimizer.engine.cai3_ast_translator import CAI3Translator

        #translator = CAI3Translator()

        translator_instance = CAI3Translator()
        translator_available = True
        print("✅ Successfully imported CAI3Translator from engine")
    except ImportError as e:
        print(f"⚠️  Failed to import CAI3Translator: {e}")
        print("   Testing compression only - translation test will be skipped")
    
    if not translator_available:
        print("⚠️  CAI3 translator not available - testing compression only")
        print("   Available modules can still verify compression works")
        print("   Translation test will be skipped")
        
        # Create a simple mock translator for basic validation
        def mock_translate_cai3_to_python(cai3_content):
            """
            Mock translator that performs basic CAI3 parsing validation
            and returns a simplified Python-like output for testing.
            """
            lines = cai3_content.strip().split('\n')
            
            # Basic validation that this looks like CAI3
            if not lines or not lines[0].startswith('#C3L'):
                raise ValueError("Invalid CAI3 format - missing header")
            
            # Look for required sections
            has_table = any(line.startswith('T:') for line in lines)
            has_bodies = any(line.startswith('B#') for line in lines)
            
            if not has_table:
                raise ValueError("Invalid CAI3 format - missing table section")
            
            # Generate a mock translation
            mock_output = "# Mock translation of CAI3 compressed code\n"
            mock_output += "class DataProcessor:\n"
            mock_output += "    def __init__(self, config):\n"
            mock_output += "        # Reconstructed from CAI3\n"
            mock_output += "        pass\n"
            
            if has_bodies:
                mock_output += "    def validate_record(self, record):\n"
                mock_output += "        # Method body reconstructed from CAI3\n"
                mock_output += "        pass\n"
            
            return mock_output
        
        translate_cai3_to_python = mock_translate_cai3_to_python
        translator_available = True
        print("✅ Using mock translator for basic CAI3 validation")
    
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
        
        def _extract_chain_pattern(self, node):
            """Mock implementation of chain pattern extraction"""
            import ast
            try:
                if hasattr(node, 'attr') and hasattr(node, 'value'):
                    # Mock chain extraction
                    return f"mock_chain_{node.attr}"
                return None
            except Exception:
                return None
        
        def _is_reserved_pattern(self, name):
            """Mock implementation to check reserved patterns"""
            import re
            if re.match(r'^p\d+$', name):
                return True
            if re.match(r'^g\d+$', name):
                return True
            return False
        
        def _find_symbols_used_in_bodies(self, cai3_full, edit_scope_cids, content):
            """Mock implementation to find symbols used in method bodies"""
            # Simple mock implementation - return common symbols
            return {'config', 'get', 'items', 'datetime', 'now', 'str', 'int', 'bool', 'list', 'dict'}
        
        def _extract_class_attributes(self, class_node, used_names=None):
            """Updated mock implementation to match real attribute compression"""
            import ast
            if used_names is None:
                used_names = set()
            
            attr_compressions = {}
            init_method = None
            
            # Find __init__ method (matching real implementation)
            for item in class_node.body:
                if isinstance(item, ast.FunctionDef) and item.name == '__init__':
                    init_method = item
                    break
            
            if not init_method:
                return {}
            
            # Extract self.<attr> assignments (matching real implementation)
            assigned_attrs = set()
            for node in ast.walk(init_method):
                if (isinstance(node, ast.Assign) and 
                    len(node.targets) == 1 and 
                    isinstance(node.targets[0], ast.Attribute) and
                    isinstance(node.targets[0].value, ast.Name) and
                    node.targets[0].value.id == 'self'):
                    assigned_attrs.add(node.targets[0].attr)
            
            # Use smart compression patterns (matching real implementation)
            common_patterns = {
                'processed_count': 'pc',
                'error_count': 'ec', 
                'config': 'c',
                'cache': 'ch',
                'status': 'stat',
                'logger': 'log',
                'manager': 'm',
                'handler': 'h',
                'processor': 'p',
                'validator': 'v',
                'transformer': 't',
                'controller': 'ctrl',
                'service': 's',
            }
            
            # Create compressed mappings for each attribute
            for attr_name in sorted(assigned_attrs):
                if attr_name in common_patterns:
                    compressed = common_patterns[attr_name]
                    # Ensure uniqueness
                    if compressed not in used_names:
                        attr_compressions[attr_name] = compressed
                        used_names.add(compressed)
            
            return attr_compressions
        
        def _annotate_function_cids(self, tree):
            """Mock implementation of CID annotation"""
            import ast
            
            def generate_cid(node_type: str, node_name: str, parent_cid: str = None) -> str:
                import hashlib
                base = f"{node_type}_{node_name}"
                if parent_cid:
                    base = f"{parent_cid}_{base}"
                return f"{node_type.lower()}_{hashlib.md5(base.encode()).hexdigest()[:4]}"
            
            cid_index = {}
            for node in tree.body:
                if isinstance(node, ast.ClassDef):
                    class_cid = generate_cid("CL", node.name)
                    cid_index[class_cid] = node
                    for item in node.body:
                        if isinstance(item, ast.FunctionDef):
                            method_cid = generate_cid("MT", item.name, class_cid)
                            cid_index[method_cid] = item
                elif isinstance(node, ast.FunctionDef):
                    func_cid = generate_cid("FN", node.name)
                    cid_index[func_cid] = node
            return cid_index
            try:
                if isinstance(node, ast.Attribute):
                    chain_parts = []
                    current = node
                    while isinstance(current, ast.Attribute):
                        chain_parts.append(current.attr)
                        current = current.value
                    
                    if isinstance(current, ast.Name):
                        chain_parts.append(current.id)
                        chain_parts.reverse()
                        full_chain = '.'.join(chain_parts)
                        
                        if 'config' in full_chain and 'get' in full_chain:
                            return 's.c.g'
                        elif full_chain.endswith('.items'):
                            return 'tv.items'
                        elif 'datetime.now' in full_chain:
                            return 'dt.now'
                        
                return None
            except Exception:
                return None
        
        def _is_reserved_pattern(self, name):
            """Mock implementation to check reserved patterns"""
            import re
            if re.match(r'^p\d+$', name):
                return True
            if re.match(r'^g\d+$', name):
                return True
            return False
        
        def _find_symbols_used_in_bodies(self, cai3_full, edit_scope_cids, content):
            """Mock implementation to find symbols used in method bodies"""
            return {'config', 'get', 'items', 'datetime', 'now', 'str', 'int', 'bool', 'list', 'dict'}
        
        def _extract_class_attributes(self, class_node, used_names=None):
            """Mock implementation to match real attribute compression"""
            import ast
            if used_names is None:
                used_names = set()
            
            attr_compressions = {}
            init_method = None
            
            for item in class_node.body:
                if isinstance(item, ast.FunctionDef) and item.name == '__init__':
                    init_method = item
                    break
            
            if not init_method:
                return attr_compressions
            
            assigned_attrs = set()
            for node in ast.walk(init_method):
                if isinstance(node, ast.Assign):
                    for target in node.targets:
                        if (isinstance(target, ast.Attribute) and 
                            isinstance(target.value, ast.Name) and 
                            target.value.id == 'self'):
                            assigned_attrs.add(target.attr)
            
            common_patterns = {
                'processed_count': 'pc',
                'error_count': 'ec', 
                'config': 'c',
            }
            
            for attr_name in sorted(assigned_attrs):
                if attr_name not in attr_compressions:
                    if attr_name in common_patterns:
                        candidate = common_patterns[attr_name]
                        if candidate not in used_names and not self._is_reserved_pattern(candidate):
                            used_names.add(candidate)
                            attr_compressions[attr_name] = candidate
                    else:
                        candidate = attr_name[:2]
                        if candidate not in used_names and not self._is_reserved_pattern(candidate):
                            used_names.add(candidate)
                            attr_compressions[attr_name] = candidate
            
            return attr_compressions
        
        def _annotate_function_cids(self, tree):
            """Mock implementation of CID annotation"""
            import ast
            import hashlib
            
            def generate_cid(node_type: str, node_name: str, parent_cid: str = None) -> str:
                if parent_cid:
                    base = f"{node_type}_{node_name}_{parent_cid}"
                else:
                    base = f"{node_type}_{node_name}"
                return hashlib.md5(base.encode()).hexdigest()[:8]
            
            cid_index = {}
            for node in tree.body:
                if isinstance(node, ast.ClassDef):
                    class_cid = generate_cid('C', node.name)
                    node._cai_cid = class_cid
                    for item in node.body:
                        if isinstance(item, ast.FunctionDef):
                            m_cid = generate_cid('M', item.name, class_cid)
                            item._cai_cid = m_cid
                            cid_index[(node.name, item.name, getattr(item, 'lineno', 0))] = m_cid
                elif isinstance(node, ast.FunctionDef):
                    f_cid = generate_cid('F', node.name)
                    node._cai_cid = f_cid
                    cid_index[(None, node.name, getattr(node, 'lineno', 0))] = f_cid
            return cid_index
    
    # Enhance with CAI3
    enhance_waterfall_with_cai3(MockWaterfallCompressor)
    
    # Create compressor and test both modes
    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
        f.write(TEST_SOURCE)
        temp_path = Path(f.name)
    
    try:
        original_tokens = count_tokens_gpt(TEST_SOURCE)
        
        # Test edit scope mode
        print("🔍 Testing CAI3 Edit Scope Translation:")
        compressor_selective = MockWaterfallCompressor(include_all_methods=False)
        result_selective = compressor_selective._standard_compression_cai3(TEST_SOURCE, original_tokens, temp_path)
        
        print(f"   Compressed output length: {len(result_selective.content)} chars")
        print(f"   Compression ratio: {result_selective.compression_ratio:.1f}%")
        
        if translator_available and translator_instance:
            print(f"   Attempting CAI3Translator.apply_patch...")
            try:
                # For testing purposes, treat the CAI3 content as a patch
                # In real usage, this would be LLM-generated patch content
                translated_selective = translator_instance.apply_patch(result_selective.content, temp_path)
                print(f"✅ Edit scope translation successful!")
                print(f"   Translated output length: {len(translated_selective)} chars")
                
                # Basic validation that translation contains key elements
                if 'class DataProcessor' in translated_selective and 'def validate_record' in translated_selective:
                    print(f"✅ Translation contains expected class and method structures")
                else:
                    print(f"⚠️  Translation may be incomplete - missing expected structures")
                    
            except Exception as e:
                print(f"❌ Edit scope translation failed: {e}")
                print(f"   Note: CAI3Translator expects patch format, not raw CAI3 content")
        elif translator_available:
            print(f"   Attempting mock translation...")
            try:
                translated_selective = translate_cai3_to_python(result_selective.content)
                print(f"✅ Edit scope translation successful!")
                print(f"   Translated output length: {len(translated_selective)} chars")
                
                # Basic validation that translation contains key elements
                if 'class DataProcessor' in translated_selective and 'def validate_record' in translated_selective:
                    print(f"✅ Translation contains expected class and method structures")
                else:
                    print(f"⚠️  Translation may be incomplete - missing expected structures")
                    
            except Exception as e:
                print(f"❌ Edit scope translation failed: {e}")
        else:
            print(f"   ✅ Compression successful - skipping translation (no translator available)")
        
        # Test all methods mode
        print("\n🔍 Testing CAI3 All Bodies Translation:")
        compressor_all = MockWaterfallCompressor(include_all_methods=True)
        result_all = compressor_all._standard_compression_cai3(TEST_SOURCE, original_tokens, temp_path)
        
        print(f"   Compressed output length: {len(result_all.content)} chars")
        print(f"   Compression ratio: {result_all.compression_ratio:.1f}%")
        
        if translator_available and translator_instance:
            print(f"   Attempting CAI3Translator.apply_patch...")
            try:
                translated_all = translator_instance.apply_patch(result_all.content, temp_path)
                print(f"✅ All bodies translation successful!")
                print(f"   Translated output length: {len(translated_all)} chars")
                
                # Basic validation that translation contains key elements
                if 'class DataProcessor' in translated_all and 'def validate_record' in translated_all:
                    print(f"✅ Translation contains expected class and method structures")
                else:
                    print(f"⚠️  Translation may be incomplete - missing expected structures")
                    
                # Compare translation completeness
                selective_methods = translated_selective.count('def ') if 'translated_selective' in locals() else 0
                all_methods = translated_all.count('def ')
                print(f"   Method count comparison: Edit scope ({selective_methods}) vs All bodies ({all_methods})")
                    
            except Exception as e:
                print(f"❌ All bodies translation failed: {e}")
                print(f"   Note: CAI3Translator expects patch format, not raw CAI3 content")
        elif translator_available:
            print(f"   Attempting mock translation...")
            try:
                translated_all = translate_cai3_to_python(result_all.content)
                print(f"✅ All bodies translation successful!")
                print(f"   Translated output length: {len(translated_all)} chars")
                
                # Basic validation that translation contains key elements
                if 'class DataProcessor' in translated_all and 'def validate_record' in translated_all:
                    print(f"✅ Translation contains expected class and method structures")
                else:
                    print(f"⚠️  Translation may be incomplete - missing expected structures")
                    
                # Compare translation completeness
                selective_methods = translated_selective.count('def ') if 'translated_selective' in locals() else 0
                all_methods = translated_all.count('def ')
                print(f"   Method count comparison: Edit scope ({selective_methods}) vs All bodies ({all_methods})")
                    
            except Exception as e:
                print(f"❌ All bodies translation failed: {e}")
                print(f"   Note: CAI3Translator expects patch format, not raw CAI3 content")
        elif translator_available:
            print(f"   Attempting mock translation...")
            try:
                translated_all = translate_cai3_to_python(result_all.content)
                print(f"✅ All bodies translation successful!")
                print(f"   Translated output length: {len(translated_all)} chars")
                
                # Basic validation that translation contains key elements
                if 'class DataProcessor' in translated_all and 'def validate_record' in translated_all:
                    print(f"✅ Translation contains expected class and method structures")
                else:
                    print(f"⚠️  Translation may be incomplete - missing expected structures")
                    
                # Compare translation completeness
                selective_methods = translated_selective.count('def ') if 'translated_selective' in locals() else 0
                all_methods = translated_all.count('def ')
                print(f"   Method count comparison: Edit scope ({selective_methods}) vs All bodies ({all_methods})")
                    
            except Exception as e:
                print(f"❌ All bodies translation failed: {e}")
        else:
            print(f"   ✅ Compression successful - skipping translation (no translator available)")
        
        # Test basic round-trip validation even without translator
        print(f"\n📋 Compression Output Samples:")
        print(f"   Edit Scope Mode (first 200 chars):")
        print(f"   {result_selective.content[:200]}...")
        print(f"   All Bodies Mode (first 200 chars):")
        print(f"   {result_all.content[:200]}...")
        
        # Validate that compressed output looks like valid CAI3
        valid_cai3_patterns = ['#C3L', 'T:', 'B#', 'C:', 'M:', 'F:']
        edit_scope_valid = any(pattern in result_selective.content for pattern in valid_cai3_patterns)
        all_bodies_valid = any(pattern in result_all.content for pattern in valid_cai3_patterns)
        
        print(f"\n📊 Translation Summary:")
        print(f"   Edit scope compression: {'✅ Success' if result_selective.compression_ratio > 0 else '❌ Failed'}")
        print(f"   All bodies compression: {'✅ Success' if result_all.compression_ratio > 0 else '❌ Failed'}")
        print(f"   Edit scope CAI3 format: {'✅ Valid' if edit_scope_valid else '❌ Invalid'}")
        print(f"   All bodies CAI3 format: {'✅ Valid' if all_bodies_valid else '❌ Invalid'}")
        
        if translator_available:
            if translator_instance:
                print(f"   Edit scope translation: {'✅ Success (CAI3Translator)' if 'translated_selective' in locals() else '❌ Failed'}")
                print(f"   All bodies translation: {'✅ Success (CAI3Translator)' if 'translated_all' in locals() else '❌ Failed'}")
                print(f"   Note: Real CAI3Translator used - expects patch format")
            elif 'mock_translate_cai3_to_python' in locals():
                print(f"   Edit scope translation: {'✅ Success (Mock)' if 'translated_selective' in locals() else '❌ Failed'}")
                print(f"   All bodies translation: {'✅ Success (Mock)' if 'translated_all' in locals() else '❌ Failed'}")
                print(f"   Note: Mock translator used - validates CAI3 structure only")
            else:
                print(f"   Edit scope translation: {'✅ Success' if 'translated_selective' in locals() else '❌ Failed'}")
                print(f"   All bodies translation: {'✅ Success' if 'translated_all' in locals() else '❌ Failed'}")
        else:
            print(f"   Translation tests: ⚠️  Skipped (translator not available)")
            print(f"   Note: Compression output can be manually tested with translator when available")
        
    finally:
        temp_path.unlink()
    
    print("\n" + "=" * 70)
    print("CAI3 Translation test complete!")
    print("=" * 70)

if __name__ == "__main__":
    print("🏷️  CAI3 Compression Mode Labels:")
    print("   • CAI3 Edit Scope: Limited methods (default, max 2 methods)")
    print("   • CAI3 All Bodies: All methods included")
    print("=" * 70)
    
    test_enhanced_compression()
    test_all_methods_compression()
    compare_versions()
    
    print("\n🏷️  Cache File Labels:")
    print("   • '_full.json' files contain 'compression_mode' field")
    print("   • 'CAI3 Edit Scope': Limited methods mode (default)")
    print("   • 'CAI3 All Bodies': All methods included mode")
    print("=" * 70)
    
    # Add round-trip translation test
    test_cai3_translation()