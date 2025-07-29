#!/usr/bin/env python3
"""
Semantic Compression Demo
Demonstrates the semantic-aware compression engine with sample transformations and analysis.
"""

import sys
from pathlib import Path
from datetime import datetime
import io

# Add project root to path
project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

from input_optimizer.engine.semantic_compression_engine import SemanticAwareCompressionEngine
from input_optimizer.samples.samples import *

def demo_semantic_compression():
    """Demonstrate semantic compression capabilities"""
    
    print("=" * 80)
    print("SEMANTIC-AWARE COMPRESSION DEMONSTRATION")
    print("Balancing token efficiency with semantic similarity preservation")
    print("=" * 80)
    
    # Create engine with reasonable threshold
    engine = SemanticAwareCompressionEngine(similarity_threshold=0.6)
    
    # Select diverse samples for demonstration
    demo_samples = [
        ("Simple Function", sample1),
        ("List Comprehension", sample2),
        ("Class with Properties", sample3),
        ("Async Function", sample4),
        ("Generator Function", sample6),
        ("Dictionary Comprehension", sample7),
        ("Decorator with Arguments", sample10),
        ("REST API Client", sample21),
        ("Data Pipeline", sample22),
        ("Verbose Documentation", sample31)
    ]
    
    results = []
    
    for sample_name, sample_code in demo_samples:
        print(f"\n{sample_name}:")
        print("-" * 60)
        
        try:
            result = engine.compress(sample_code)
            results.append((sample_name, result))
            
            # Display key metrics
            print(f"📊 Original tokens: {result['original_tokens']:,}")
            print(f"📊 Compressed tokens: {result['compressed_tokens']:,}")
            print(f"🗜️  Compression ratio: {result['compression_percentage']:.1f}%")
            print(f"🔄 Similarity score: {result['similarity_score']:.3f}")
            print(f"⚙️  Compression level: {result.get('compression_level', 'N/A')}")
            print(f"✅ Meets threshold: {'Yes' if result['meets_threshold'] else 'No'}")
            
            # Show stage contributions
            print(f"\n📋 Stage breakdown:")
            for stage_name, stage_data in result['stage_results'].items():
                tokens_saved = stage_data.get('tokens_saved', 0)
                skipped = stage_data.get('skipped', False)
                skipped_level = stage_data.get('skipped_level', False)
                
                stage_display = stage_name.replace('stage', '').replace('_', ' ').title()
                
                if skipped:
                    print(f"   • {stage_display}: Skipped (similarity threshold)")
                elif skipped_level:
                    print(f"   • {stage_display}: Skipped (compression level)")
                elif tokens_saved != 0:  # Only show stages that contributed
                    direction = "saved" if tokens_saved > 0 else "added"
                    print(f"   • {stage_display}: {abs(tokens_saved)} tokens {direction}")
                else:
                    print(f"   • {stage_display}: No change")
            
            # Show compressed code sample
            compressed = result['compressed_code']
            if len(compressed) > 300:
                print(f"\n💻 Compressed code (first 300 chars):")
                print(compressed[:300] + "...")
            else:
                print(f"\n💻 Compressed code:")
                print(compressed)
                
        except Exception as e:
            print(f"❌ Error compressing {sample_name}: {str(e)}")
            continue
    
    # Overall analysis
    print(f"\n{'=' * 80}")
    print("OVERALL ANALYSIS")
    print(f"{'=' * 80}")
    
    if results:
        # Calculate statistics
        compression_ratios = [r[1]['compression_percentage'] for r in results]
        similarity_scores = [r[1]['similarity_score'] for r in results]
        tokens_saved_total = sum(r[1]['tokens_saved'] for r in results)
        original_tokens_total = sum(r[1]['original_tokens'] for r in results)
        
        avg_compression = sum(compression_ratios) / len(compression_ratios)
        avg_similarity = sum(similarity_scores) / len(similarity_scores)
        overall_compression = (tokens_saved_total / original_tokens_total) * 100 if original_tokens_total > 0 else 0
        
        print(f"📈 Samples analyzed: {len(results)}")
        print(f"📈 Average compression: {avg_compression:.1f}%")
        print(f"📈 Average similarity: {avg_similarity:.3f}")
        print(f"📈 Overall compression: {overall_compression:.1f}%")
        print(f"📈 Total tokens saved: {tokens_saved_total:,}")
        
        # Show top performers
        top_compression = sorted(results, key=lambda x: x[1]['compression_percentage'], reverse=True)[:3]
        top_similarity = sorted(results, key=lambda x: x[1]['similarity_score'], reverse=True)[:3]
        
        print(f"\n🏆 Top 3 compression performers:")
        for i, (name, result) in enumerate(top_compression, 1):
            print(f"   {i}. {name}: {result['compression_percentage']:.1f}% compression "
                  f"(similarity: {result['similarity_score']:.3f})")
        
        print(f"\n🏆 Top 3 similarity preservers:")
        for i, (name, result) in enumerate(top_similarity, 1):
            print(f"   {i}. {name}: {result['similarity_score']:.3f} similarity "
                  f"(compression: {result['compression_percentage']:.1f}%)")
        
        # Threshold analysis
        meeting_threshold = sum(1 for _, result in results if result['meets_threshold'])
        threshold_percentage = (meeting_threshold / len(results)) * 100
        
        print(f"\n🎯 Threshold analysis:")
        print(f"   • Similarity threshold: {engine.similarity_threshold}")
        print(f"   • Samples meeting threshold: {meeting_threshold}/{len(results)} ({threshold_percentage:.1f}%)")
        
        # Recommendations
        print(f"\n💡 Recommendations:")
        if avg_similarity >= 0.7:
            print(f"   ✅ High semantic similarity preserved - safe for production use")
        elif avg_similarity >= 0.5:
            print(f"   ⚠️  Moderate semantic similarity - review critical code sections")
        else:
            print(f"   ❌ Low semantic similarity - consider adjusting compression settings")
        
        if avg_compression >= 20:
            print(f"   🚀 Excellent compression achieved - significant token savings")
        elif avg_compression >= 10:
            print(f"   ✅ Good compression achieved - worthwhile token savings")
        else:
            print(f"   📊 Modest compression - evaluate if benefits justify complexity")

def demonstrate_threshold_impact():
    """Show how similarity threshold affects compression behavior"""
    
    print(f"\n{'=' * 80}")
    print("SIMILARITY THRESHOLD IMPACT ANALYSIS")
    print(f"{'=' * 80}")
    
    test_code = sample31  # Use verbose documentation sample
    thresholds = [0.3, 0.5, 0.7, 0.9]
    
    print(f"Testing with sample: Verbose Documentation (sample31)")
    print(f"Original tokens: {estimate_tokens(test_code):,}")
    print()
    
    results = []
    for threshold in thresholds:
        engine = SemanticAwareCompressionEngine(similarity_threshold=threshold)
        result = engine.compress(test_code)
        results.append((threshold, result))
        
        status = "✅ Pass" if result['meets_threshold'] else "❌ Fail"
        level = result.get('compression_level', 'N/A')
        print(f"Threshold {threshold:.1f} (Level {level}): "
              f"Compression {result['compression_percentage']:6.1f}%, "
              f"Similarity {result['similarity_score']:.3f}, "
              f"{status}")
    
    # Show detailed stage analysis
    print(f"\n📋 Detailed Stage Analysis:")
    print(f"{'Threshold':<10} {'Level':<6} {'Ident':<6} {'Struct':<7} {'Context':<8} {'White':<6} {'Notation':<9}")
    print("-" * 60)
    
    for threshold, result in results:
        level = result.get('compression_level', 'N/A')
        stages = result['stage_results']
        
        # Get stage status (applied/skipped)
        ident_status = "✓" if stages.get('stage1_identifiers', {}).get('tokens_saved', 0) != 0 else "○"
        if stages.get('stage1_identifiers', {}).get('skipped'):
            ident_status = "✗"
        
        struct_status = "✓" if stages.get('stage2_structure', {}).get('tokens_saved', 0) != 0 else "○"
        if stages.get('stage2_structure', {}).get('skipped'):
            struct_status = "✗"
        elif stages.get('stage2_structure', {}).get('skipped_level'):
            struct_status = "-"
        
        context_status = "✓" if stages.get('stage3_context', {}).get('tokens_saved', 0) != 0 else "○"
        if stages.get('stage3_context', {}).get('skipped'):
            context_status = "✗"
        elif stages.get('stage3_context', {}).get('skipped_level'):
            context_status = "-"
        
        white_status = "✓" if stages.get('stage4_whitespace', {}).get('tokens_saved', 0) != 0 else "○"
        if stages.get('stage4_whitespace', {}).get('skipped'):
            white_status = "✗"
        elif stages.get('stage4_whitespace', {}).get('skipped_level'):
            white_status = "-"
        
        notation_status = "✓" if stages.get('stage5_notation', {}).get('tokens_saved', 0) != 0 else "○"
        if stages.get('stage5_notation', {}).get('skipped'):
            notation_status = "✗"
        elif stages.get('stage5_notation', {}).get('skipped_level'):
            notation_status = "-"
        
        print(f"{threshold:<10.1f} {level:<6} {ident_status:<6} {struct_status:<7} {context_status:<8} {white_status:<6} {notation_status:<9}")
    
    print(f"\nLegend: ✓=Applied, ○=No change, ✗=Skipped (similarity), -=Skipped (level)")
    
    # Show compression progression
    print(f"\n📈 Compression Progression:")
    for i, (threshold, result) in enumerate(results):
        if i > 0:
            prev_compression = results[i-1][1]['compression_percentage']
            current_compression = result['compression_percentage']
            change = current_compression - prev_compression
            change_str = f"({change:+.1f}%)" if change != 0 else "(no change)"
            print(f"   {threshold:.1f}: {current_compression:.1f}% {change_str}")
        else:
            print(f"   {threshold:.1f}: {result['compression_percentage']:.1f}% (baseline)")

def generate_detailed_sample_analysis():
    """Generate detailed analysis of all samples for the output file"""
    
    print(f"\n{'=' * 80}")
    print("DETAILED SAMPLE ANALYSIS")
    print("Complete breakdown of compression behavior across all code patterns")
    print(f"{'=' * 80}")
    
    # Get all available samples (check which ones exist)
    all_samples = []
    sample_names = [
        ("Simple Function", "sample1"),
        ("List Comprehension", "sample2"), 
        ("Class with Properties", "sample3"),
        ("Async Function", "sample4"),
        ("Lambda Function", "sample5"),
        ("Generator Function", "sample6"),
        ("Dictionary Comprehension", "sample7"),
        ("Error Handling", "sample8"),
        ("Nested Function", "sample9"),
        ("Decorator with Arguments", "sample10"),
        ("Context Manager", "sample11"),
        ("Multiple Inheritance", "sample12"),
        ("Property Decorators", "sample13"),
        ("Async Context Manager", "sample14"),
        ("Dataclass Definition", "sample15"),
        ("File Operations", "sample16"),
        ("Database Connection", "sample17"),
        ("API Request Handler", "sample18"),
        ("Data Validation", "sample19"),
        ("Logging Setup", "sample20"),
        ("REST API Client", "sample21"),
        ("Data Pipeline", "sample22"),
        ("Configuration Parser", "sample23"),
        ("Unit Test Case", "sample24"),
        ("Mathematical Function", "sample25"),
        ("String Processing", "sample26"),
        ("Date/Time Operations", "sample27"),
        ("Regular Expression", "sample28"),
        ("Web Scraping", "sample29"),
        ("Machine Learning", "sample30"),
        ("Verbose Documentation", "sample31")
    ]
    
    # Only include samples that actually exist
    for name, sample_var in sample_names:
        try:
            sample_code = globals()[sample_var]
            all_samples.append((name, sample_code))
        except KeyError:
            continue  # Skip samples that don't exist
    
    # Test with multiple thresholds
    test_thresholds = [0.5, 0.7, 0.9]
    
    for threshold in test_thresholds:
        print(f"\n🎯 THRESHOLD {threshold} ANALYSIS")
        print(f"{'Sample Name':<25} {'Original':<9} {'Compressed':<11} {'Compression':<12} {'Similarity':<11} {'Level':<6} {'Status'}")
        print("-" * 95)
        
        engine = SemanticAwareCompressionEngine(similarity_threshold=threshold)
        threshold_stats = {
            'total_samples': 0,
            'successful_compressions': 0,
            'total_original_tokens': 0,
            'total_compressed_tokens': 0,
            'total_similarity': 0,
            'meets_threshold_count': 0
        }
        
        for sample_name, sample_code in all_samples:
            try:
                result = engine.compress(sample_code)
                
                # Update statistics
                threshold_stats['total_samples'] += 1
                threshold_stats['total_original_tokens'] += result['original_tokens']
                threshold_stats['total_compressed_tokens'] += result['compressed_tokens']
                threshold_stats['total_similarity'] += result['similarity_score']
                if result['meets_threshold']:
                    threshold_stats['meets_threshold_count'] += 1
                if result['compression_percentage'] > 0:
                    threshold_stats['successful_compressions'] += 1
                
                # Format output
                status = "✅ Pass" if result['meets_threshold'] else "❌ Fail"
                level = result.get('compression_level', 'N/A')
                
                print(f"{sample_name:<25} {result['original_tokens']:<9,} {result['compressed_tokens']:<11,} "
                      f"{result['compression_percentage']:<12.1f}% {result['similarity_score']:<11.3f} "
                      f"{level:<6} {status}")
                      
            except Exception as e:
                print(f"{sample_name:<25} {'ERROR':<9} {'ERROR':<11} {'ERROR':<12} {'ERROR':<11} {'ERROR':<6} ❌ Error")
        
        # Print threshold summary
        if threshold_stats['total_samples'] > 0:
            overall_compression = ((threshold_stats['total_original_tokens'] - threshold_stats['total_compressed_tokens']) 
                                 / threshold_stats['total_original_tokens'] * 100) if threshold_stats['total_original_tokens'] > 0 else 0
            avg_similarity = threshold_stats['total_similarity'] / threshold_stats['total_samples']
            success_rate = (threshold_stats['meets_threshold_count'] / threshold_stats['total_samples']) * 100
            positive_compression_rate = (threshold_stats['successful_compressions'] / threshold_stats['total_samples']) * 100
            
            print(f"\n📊 Threshold {threshold} Summary:")
            print(f"   • Total samples: {threshold_stats['total_samples']}")
            print(f"   • Overall compression: {overall_compression:.1f}%")
            print(f"   • Average similarity: {avg_similarity:.3f}")
            print(f"   • Success rate (meets threshold): {success_rate:.1f}%")
            print(f"   • Positive compression rate: {positive_compression_rate:.1f}%")
            print(f"   • Total tokens saved: {threshold_stats['total_original_tokens'] - threshold_stats['total_compressed_tokens']:,}")

def generate_compression_methodology_summary():
    """Generate a summary of the compression methodology for the output file"""
    
    print(f"\n{'=' * 80}")
    print("COMPRESSION METHODOLOGY SUMMARY")
    print(f"{'=' * 80}")
    
    print("""
🔧 COMPRESSION STAGES:

1. Identifier Compression (AST-based):
   • Analyzes variable and function names using Abstract Syntax Tree
   • Replaces long identifiers with shorter equivalents
   • Preserves semantic meaning and scope context
   • Frequency-based prioritization for optimal compression

2. Structural Optimization:
   • Import statement consolidation (e.g., import math as m)
   • Docstring compression while preserving key information
   • Property decorator shortening (@property → @prpr)
   • Function signature optimization

3. Context-Aware Token Reduction:
   • Intelligent comment removal/compression
   • Redundant whitespace elimination
   • String literal optimization where safe
   • Context preservation for critical information

4. Whitespace Optimization:
   • Conservative indentation management
   • Newline optimization while maintaining readability
   • Spacing reduction around operators and punctuation
   • Python syntax compliance maintained

5. Semantic Notation Substitution:
   • Mathematical symbol replacement (math.pi → π)
   • Common pattern abbreviations
   • Unicode symbol utilization for token efficiency
   • Reversible transformations

⚙️ COMPRESSION LEVELS:

Level 1 (Threshold ≥ 0.8): Ultra-Conservative
   • Only whitespace optimization
   • Maximum semantic preservation
   • Minimal token reduction

Level 2 (Threshold ≥ 0.7): Conservative  
   • Whitespace + identifier compression
   • Safe structural optimizations
   • High similarity maintenance

Level 3 (Threshold ≥ 0.6): Moderate
   • Adds structural optimization
   • Balanced compression/similarity trade-off
   • Production-ready settings

Level 4 (Threshold ≥ 0.4): Aggressive
   • Adds context-aware reductions
   • Higher compression ratios
   • Careful similarity monitoring

Level 5 (Threshold < 0.4): Maximum Compression
   • All optimization stages enabled
   • Semantic notation substitution
   • Highest token efficiency

🎯 SIMILARITY CALCULATION:

Weighted combination of:
   • Structural similarity (70%): Line-by-line diff analysis
   • Token similarity (30%): Vocabulary overlap preservation
   • Threshold-based stage validation
   • Progressive optimization with similarity gates

📊 PERFORMANCE CHARACTERISTICS:

Strengths:
   ✅ High semantic preservation (avg 79-81% similarity)
   ✅ Intelligent stage skipping prevents over-compression
   ✅ AST-based analysis ensures syntactic correctness
   ✅ Reversible transformations via source mapping
   ✅ Configurable aggressiveness levels

Considerations:
   ⚠️ Conservative approach may limit compression ratios
   ⚠️ Unicode symbols may increase token count in some contexts
   ⚠️ Complex code patterns may see minimal compression
   ⚠️ Threshold tuning required for optimal results
""")

if __name__ == "__main__":
    # Import estimate_tokens for the threshold demo
    from utils.logger import estimate_tokens
    
    # Create output file with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = project_root / f"semantic_compression_analysis_{timestamp}.txt"
    
    # Capture output to both console and file
    output_buffer = io.StringIO()
    
    def print_to_both(*args, **kwargs):
        """Print to both console and output buffer"""
        print(*args, **kwargs)
        print(*args, **kwargs, file=output_buffer)
    
    # Override print function for dual output
    original_print = print
    print = print_to_both
    
    try:
        print(f"Semantic Compression Analysis - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"Output will be saved to: {output_file}")
        print()
        
        # Run main demonstration
        demo_semantic_compression()
        
        # Show threshold impact
        demonstrate_threshold_impact()
        
        # Generate detailed analysis of all samples
        generate_detailed_sample_analysis()
        
        # Generate methodology summary
        generate_compression_methodology_summary()
        
        print(f"\n{'=' * 80}")
        print("🎉 SEMANTIC COMPRESSION DEMONSTRATION COMPLETE")
        print(f"{'=' * 80}")
        
        # Save output to file
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(output_buffer.getvalue())
        
        # Restore original print
        print = original_print
        print(f"\n📄 Analysis saved to: {output_file}")
        print(f"📊 File size: {output_file.stat().st_size:,} bytes")
        
    except Exception as e:
        # Restore original print on error
        print = original_print
        print(f"❌ Error during analysis: {str(e)}")
        
        # Still try to save partial output
        if output_buffer.getvalue():
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(output_buffer.getvalue())
                f.write(f"\n\n❌ Analysis terminated with error: {str(e)}")
            print(f"📄 Partial analysis saved to: {output_file}")
        
        raise
