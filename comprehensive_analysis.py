#!/usr/bin/env python3
"""
Comprehensive Sample Transformation Analysis
Tests all compression methods across representative samples for token reduction,
semantic preservation, and efficacy analysis.
"""

import sys
import json
import time
from pathlib import Path
from typing import Dict, List, Any, Tuple
import difflib

# Add project root to path
project_root = Path(__file__).resolve().parent
sys.path.insert(0, str(project_root))

# Import all required modules
from input_optimizer.samples.samples import (
    sample1, sample2, sample3, sample4, sample5, sample6, sample7, sample8, 
    sample9, sample10, sample15, sample20, sample25, sample31
)
from input_optimizer.engine.minifier import minify_code, minify_aggressive
from input_optimizer.engine.translators.sudo_lang_translator import python_to_sudolang, translate_with_stats
from input_optimizer.engine.translators.synth_lang_translator import enhanced_python_to_synthlang
from input_optimizer.engine.semantic_compression_engine import SemanticAwareCompressionEngine
from utils.logger import estimate_tokens

def calculate_similarity(original: str, compressed: str) -> float:
    """Calculate similarity score between original and compressed code"""
    # Use difflib for basic similarity
    similarity = difflib.SequenceMatcher(None, original, compressed).ratio()
    return similarity

def chained_minify_synth_compression(code: str) -> str:
    """Chain minification + synth_lang for maximum compression"""
    # First minify aggressively
    minified = minify_aggressive(code)
    # Then apply synth_lang translation in compact mode
    compressed = enhanced_python_to_synthlang(minified, compact=True)
    return compressed

def semantic_compression(code: str) -> str:
    """Apply semantic-aware compression with similarity preservation"""
    engine = SemanticAwareCompressionEngine(similarity_threshold=0.7)
    result = engine.compress(code, preserve_semantics=True)
    return result.get('compressed_code', code)

def analyze_compression_method(method_name: str, compress_func, samples: Dict[str, str]) -> Dict[str, Any]:
    """Analyze a specific compression method across all samples"""
    results = {
        "method": method_name,
        "samples": {},
        "aggregated_stats": {
            "total_samples": 0,
            "successful_compressions": 0,
            "avg_token_reduction": 0.0,
            "avg_compression_ratio": 0.0,
            "avg_similarity": 0.0,
            "total_tokens_saved": 0
        }
    }
    
    total_reduction = 0.0
    total_ratio = 0.0
    total_similarity = 0.0
    total_tokens_saved = 0
    successful = 0
    
    for sample_name, sample_code in samples.items():
        try:
            start_time = time.time()
            
            # Get compression result
            if method_name in ["minifier", "minifier_aggressive"]:
                compressed = compress_func(sample_code)
            elif method_name == "sudo_lang":
                compressed = compress_func(sample_code)
            elif method_name == "synth_lang":
                compressed = compress_func(sample_code, compact=True)
            elif method_name == "chained_minify_synth":
                compressed = compress_func(sample_code)
            elif method_name == "semantic_compression":
                compressed = compress_func(sample_code)
            else:
                compressed = compress_func(sample_code)
            
            processing_time = (time.time() - start_time) * 1000
            
            # Calculate metrics
            original_tokens = estimate_tokens(sample_code)
            compressed_tokens = estimate_tokens(compressed)
            tokens_saved = original_tokens - compressed_tokens
            compression_ratio = compressed_tokens / original_tokens if original_tokens > 0 else 0
            token_reduction = (tokens_saved / original_tokens * 100) if original_tokens > 0 else 0
            similarity = calculate_similarity(sample_code, compressed)
            
            sample_result = {
                "original_code": sample_code,
                "compressed_code": compressed,
                "original_tokens": original_tokens,
                "compressed_tokens": compressed_tokens,
                "tokens_saved": tokens_saved,
                "compression_ratio": compression_ratio,
                "token_reduction_percent": token_reduction,
                "similarity_score": similarity,
                "processing_time_ms": processing_time,
                "success": True
            }
            
            results["samples"][sample_name] = sample_result
            
            # Update aggregated stats
            total_reduction += token_reduction
            total_ratio += compression_ratio
            total_similarity += similarity
            total_tokens_saved += tokens_saved
            successful += 1
            
        except Exception as e:
            print(f"❌ Error processing {sample_name} with {method_name}: {str(e)}")
            results["samples"][sample_name] = {
                "original_code": sample_code,
                "compressed_code": "",
                "error": str(e),
                "success": False
            }
    
    # Calculate averages
    if successful > 0:
        results["aggregated_stats"]["avg_token_reduction"] = total_reduction / successful
        results["aggregated_stats"]["avg_compression_ratio"] = total_ratio / successful
        results["aggregated_stats"]["avg_similarity"] = total_similarity / successful
        results["aggregated_stats"]["total_tokens_saved"] = total_tokens_saved
    
    results["aggregated_stats"]["total_samples"] = len(samples)
    results["aggregated_stats"]["successful_compressions"] = successful
    
    return results

def main():
    """Run comprehensive compression analysis"""
    print("🚀 Starting Comprehensive Sample Transformation Analysis")
    print("=" * 80)
    
    # Prepare sample data
    samples = {
        "sample1_simple_function": sample1,
        "sample2_list_comprehension": sample2,
        "sample3_class_properties": sample3,
        "sample4_async_function": sample4,
        "sample5_nested_functions": sample5,
        "sample6_generator": sample6,
        "sample7_dict_comprehension": sample7,
        "sample8_lambda_functions": sample8,
        "sample9_context_manager": sample9,
        "sample10_decorator": sample10,
        "sample15_medium_complexity": sample15,
        "sample20_high_complexity": sample20,
        "sample25_very_complex": sample25,
        "sample31_verbose_docs": sample31
    }
    
    print(f"📊 Analyzing {len(samples)} samples across multiple compression methods")
    print()
    
    # Initialize compression methods (function-based)
    compression_methods = {
        "minifier": minify_code,
        "minifier_aggressive": minify_aggressive,
        "sudo_lang": python_to_sudolang,
        "synth_lang": enhanced_python_to_synthlang,
        "chained_minify_synth": chained_minify_synth_compression,
        "semantic_compression": semantic_compression
    }
    
    all_results = {}
    
    # Analyze each compression method
    for method_name, method_instance in compression_methods.items():
        print(f"\n🔧 Analyzing {method_name.upper()} Compression Method")
        print("-" * 60)
        
        results = analyze_compression_method(method_name, method_instance, samples)
        all_results[method_name] = results
        
        # Display summary for this method
        stats = results["aggregated_stats"]
        print(f"✅ Successful compressions: {stats['successful_compressions']}/{stats['total_samples']}")
        print(f"📊 Average token reduction: {stats['avg_token_reduction']:.1f}%")
        print(f"🗜️  Average compression ratio: {stats['avg_compression_ratio']:.3f}")
        print(f"🔄 Average similarity score: {stats['avg_similarity']:.3f}")
        print(f"💾 Total tokens saved: {stats['total_tokens_saved']:,}")
    
    # Generate comprehensive analysis
    print("\n" + "=" * 80)
    print("📈 COMPREHENSIVE ANALYSIS RESULTS")
    print("=" * 80)
    
    # Method comparison
    method_comparison = []
    for method_name, results in all_results.items():
        stats = results["aggregated_stats"]
        method_comparison.append({
            "method": method_name,
            "success_rate": stats['successful_compressions'] / stats['total_samples'],
            "avg_token_reduction": stats['avg_token_reduction'],
            "avg_similarity": stats['avg_similarity'],
            "total_tokens_saved": stats['total_tokens_saved']
        })
    
    # Sort by token reduction
    method_comparison.sort(key=lambda x: x['avg_token_reduction'], reverse=True)
    
    print("\\n🏆 COMPRESSION METHOD RANKING (by Token Reduction):")
    for i, method in enumerate(method_comparison, 1):
        print(f"{i}. {method['method'].upper()}")
        print(f"   📊 Token Reduction: {method['avg_token_reduction']:.1f}%")
        print(f"   🔄 Similarity Score: {method['avg_similarity']:.3f}")
        print(f"   ✅ Success Rate: {method['success_rate']:.1%}")
        print(f"   💾 Tokens Saved: {method['total_tokens_saved']:,}")
        print()
    
    # Best examples for each method
    print("\\n🎯 REPRESENTATIVE EXAMPLES:")
    print("-" * 40)
    
    for method_name, results in all_results.items():
        print(f"\\n{method_name.upper()} - Best Example:")
        
        # Find sample with best token reduction
        best_sample = None
        best_reduction = -1
        
        for sample_name, sample_data in results["samples"].items():
            if sample_data.get("success", False):
                reduction = sample_data.get("token_reduction_percent", 0)
                if reduction > best_reduction:
                    best_reduction = reduction
                    best_sample = (sample_name, sample_data)
        
        if best_sample:
            sample_name, sample_data = best_sample
            print(f"Sample: {sample_name}")
            print(f"Original ({sample_data['original_tokens']} tokens):")
            print("```python")
            print(sample_data['original_code'][:200] + "..." if len(sample_data['original_code']) > 200 else sample_data['original_code'])
            print("```")
            print()
            print(f"Compressed ({sample_data['compressed_tokens']} tokens, {sample_data['token_reduction_percent']:.1f}% reduction):")
            print("```python")
            print(sample_data['compressed_code'][:200] + "..." if len(sample_data['compressed_code']) > 200 else sample_data['compressed_code'])
            print("```")
            print(f"Similarity: {sample_data['similarity_score']:.3f}")
            print()
    
    # Save detailed results
    output_file = "comprehensive_compression_analysis.json"
    with open(output_file, 'w') as f:
        json.dump(all_results, f, indent=2)
    
    print(f"💾 Detailed results saved to: {output_file}")
    print("\\n🎉 Analysis complete!")

if __name__ == "__main__":
    main()
