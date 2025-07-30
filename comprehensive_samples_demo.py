#!/usr/bin/env python3
"""
Comprehensive Waterfall Compression Demo - All Samples
Demonstrates token reduction, semantic similarity, and compression results on all individual samples.
"""

import os
import sys
from pathlib import Path
import json
import re
import ast

# Add the project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# Set test mode for imports
os.environ["WATERFALL_TEST_MODE"] = "1"

from input_optimizer.engine.waterfall_compressor import WaterfallCompressor, count_tokens

def extract_samples_from_file(samples_file: Path) -> dict:
    """Extract all individual samples from samples.py file."""
    content = samples_file.read_text(encoding='utf-8')
    samples = {}
    
    # Use regex to find sample definitions
    pattern = r'(sample\d+)\s*=\s*"""(.*?)"""'
    matches = re.findall(pattern, content, re.DOTALL)
    
    for sample_name, sample_code in matches:
        # Clean up the sample code
        sample_code = sample_code.strip()
        if sample_code:
            samples[sample_name] = sample_code
    
    return samples

def calculate_semantic_similarity(original: str, compressed: str) -> float:
    """Enhanced semantic similarity calculation."""
    try:
        # Extract key elements from original
        orig_functions = [line.strip() for line in original.split('\n') if line.strip().startswith('def ')]
        orig_classes = [line.strip() for line in original.split('\n') if line.strip().startswith('class ')]
        orig_imports = [line.strip() for line in original.split('\n') if line.strip().startswith(('import ', 'from '))]
        
        # Extract key elements from compressed (accounting for CAI format)
        comp_functions = []
        comp_classes = []
        comp_imports = []
        
        for line in compressed.split('\n'):
            line = line.strip()
            if line.startswith('def ') or 'def ' in line:
                comp_functions.append(line)
            elif line.startswith('class ') or 'class ' in line:
                comp_classes.append(line)
            elif line.startswith(('import ', 'from ')) or ('import ' in line):
                comp_imports.append(line)
            elif line.startswith('F[') and 'def ' in line:
                # CAI format function
                comp_functions.append(line)
            elif line.startswith('C[') and 'class ' in line:
                # CAI format class
                comp_classes.append(line)
        
        # Calculate preservation ratios
        total_elements = len(orig_functions) + len(orig_classes) + len(orig_imports)
        if total_elements == 0:
            return 100.0  # Empty files are semantically identical
        
        # Check function preservation
        preserved_functions = 0
        for orig_func in orig_functions:
            func_name = orig_func.split('(')[0].split()[-1]
            if any(func_name in comp_func for comp_func in comp_functions):
                preserved_functions += 1
        
        # Check class preservation
        preserved_classes = 0
        for orig_class in orig_classes:
            class_name = orig_class.split(':')[0].split()[-1]
            if any(class_name in comp_class for comp_class in comp_classes):
                preserved_classes += 1
        
        # Check import preservation (less critical for CAI)
        preserved_imports = 0
        for orig_import in orig_imports:
            if any(orig_import in comp_import for comp_import in comp_imports):
                preserved_imports += 1
        
        # Weight functions and classes more heavily than imports
        function_weight = 0.6
        class_weight = 0.3
        import_weight = 0.1
        
        weighted_preservation = (
            (preserved_functions / max(1, len(orig_functions))) * function_weight +
            (preserved_classes / max(1, len(orig_classes))) * class_weight +
            (preserved_imports / max(1, len(orig_imports))) * import_weight
        )
        
        return min(100.0, weighted_preservation * 100)
        
    except Exception:
        # Fallback to simple line-based comparison
        orig_lines = set(line.strip() for line in original.split('\n') if line.strip())
        comp_lines = set(line.strip() for line in compressed.split('\n') if line.strip())
        
        if not orig_lines:
            return 100.0
        
        preserved = len(orig_lines.intersection(comp_lines))
        return (preserved / len(orig_lines)) * 100

def categorize_sample(sample_name: str, sample_code: str) -> str:
    """Categorize the sample based on its content."""
    code = sample_code.lower()
    
    if 'async def' in code or 'await' in code:
        return "Async/Concurrency"
    elif 'class ' in code and ('__enter__' in code or '__exit__' in code):
        return "Context Manager"
    elif 'class ' in code:
        return "Object-Oriented"
    elif 'yield' in code:
        return "Generator"
    elif 'lambda' in code:
        return "Functional Programming"
    elif 'def ' in code and 'def ' in code[code.find('def ')+4:]:
        return "Nested Functions"
    elif 'import' in code and 'pandas' in code:
        return "Data Processing"
    elif 'import' in code and 'threading' in code:
        return "Threading"
    elif 'def ' in code:
        return "Function"
    elif 'import' in code:
        return "Module/Import"
    else:
        return "Other"

def format_code_comparison(original: str, compressed: str, max_lines: int = 8) -> str:
    """Format a compact side-by-side comparison."""
    orig_lines = original.split('\n')[:max_lines]
    comp_lines = compressed.split('\n')[:max_lines]
    
    # Pad shorter side
    max_len = max(len(orig_lines), len(comp_lines))
    orig_lines.extend([''] * (max_len - len(orig_lines)))
    comp_lines.extend([''] * (max_len - len(comp_lines)))
    
    comparison = []
    comparison.append("-" * 70)
    comparison.append("ORIGINAL".ljust(34) + " | " + "COMPRESSED")
    comparison.append("-" * 70)
    
    for orig, comp in zip(orig_lines, comp_lines):
        orig_truncated = orig[:32] + ".." if len(orig) > 32 else orig.ljust(34)
        comp_truncated = comp[:32] + ".." if len(comp) > 32 else comp
        comparison.append(f"{orig_truncated} | {comp_truncated}")
    
    if len(original.split('\n')) > max_lines or len(compressed.split('\n')) > max_lines:
        comparison.append("... (more lines truncated)")
    
    comparison.append("-" * 70)
    return '\n'.join(comparison)

def create_comprehensive_samples_report(results: list, report_file: Path, compressor) -> None:
    """Create a comprehensive report for all samples."""
    with open(report_file, 'w', encoding='utf-8') as f:
        f.write("🌊 WATERFALL COMPRESSION - ALL SAMPLES ANALYSIS\n")
        f.write("=" * 80 + "\n")
        f.write(f"Total Samples Analyzed: {len(results)}\n")
        f.write(f"Compressor: WaterfallCompressor (gpt-4, 128k token limit)\n\n")
        
        # Executive Summary
        f.write("📊 EXECUTIVE SUMMARY\n")
        f.write("-" * 40 + "\n")
        
        if results:
            total_original = sum(r['original_tokens'] for r in results)
            total_compressed = sum(r['compressed_tokens'] for r in results)
            total_reduction = total_original - total_compressed
            avg_compression = (total_reduction / total_original * 100) if total_original > 0 else 0
            avg_similarity = sum(r['semantic_similarity'] for r in results) / len(results)
            
            f.write(f"Total Original Tokens: {total_original:,}\n")
            f.write(f"Total Compressed Tokens: {total_compressed:,}\n")
            f.write(f"Total Token Reduction: {total_reduction:,}\n")
            f.write(f"Average Compression Ratio: {avg_compression:.1f}%\n")
            f.write(f"Average Semantic Similarity: {avg_similarity:.1f}%\n")
            
            # Performance distribution
            excellent = sum(1 for r in results if r['compression_ratio'] > 50)
            good = sum(1 for r in results if 25 < r['compression_ratio'] <= 50)
            moderate = sum(1 for r in results if 0 < r['compression_ratio'] <= 25)
            minimal = sum(1 for r in results if r['compression_ratio'] <= 0)
            
            f.write(f"\nPerformance Distribution:\n")
            f.write(f"  🟢 Excellent (>50%): {excellent} samples\n")
            f.write(f"  🟡 Good (25-50%): {good} samples\n")
            f.write(f"  🟠 Moderate (0-25%): {moderate} samples\n")
            f.write(f"  🔴 Minimal/Expansion (≤0%): {minimal} samples\n")
        
        # Category Analysis
        f.write(f"\n📁 CATEGORY ANALYSIS\n")
        f.write("-" * 40 + "\n")
        
        categories = {}
        for r in results:
            cat = r['category']
            if cat not in categories:
                categories[cat] = {
                    'count': 0,
                    'total_original': 0,
                    'total_compressed': 0,
                    'total_similarity': 0
                }
            categories[cat]['count'] += 1
            categories[cat]['total_original'] += r['original_tokens']
            categories[cat]['total_compressed'] += r['compressed_tokens']
            categories[cat]['total_similarity'] += r['semantic_similarity']
        
        for category, stats in sorted(categories.items()):
            compression_ratio = ((stats['total_original'] - stats['total_compressed']) / stats['total_original'] * 100) if stats['total_original'] > 0 else 0
            avg_similarity = stats['total_similarity'] / stats['count']
            
            f.write(f"\n{category}:\n")
            f.write(f"  Samples: {stats['count']}\n")
            f.write(f"  Avg Compression: {compression_ratio:.1f}%\n")
            f.write(f"  Avg Semantic Similarity: {avg_similarity:.1f}%\n")
            f.write(f"  Token Reduction: {stats['total_original'] - stats['total_compressed']:,}\n")
        
        # Tier Analysis
        f.write(f"\n🎯 TIER ANALYSIS\n")
        f.write("-" * 40 + "\n")
        
        tier_stats = {}
        for r in results:
            tier = r['tier']
            if tier not in tier_stats:
                tier_stats[tier] = {
                    'count': 0,
                    'total_original': 0,
                    'total_compressed': 0,
                    'avg_similarity': 0
                }
            tier_stats[tier]['count'] += 1
            tier_stats[tier]['total_original'] += r['original_tokens']
            tier_stats[tier]['total_compressed'] += r['compressed_tokens']
            tier_stats[tier]['avg_similarity'] += r['semantic_similarity']
        
        for tier, stats in sorted(tier_stats.items()):
            compression_ratio = ((stats['total_original'] - stats['total_compressed']) / stats['total_original'] * 100) if stats['total_original'] > 0 else 0
            avg_similarity = stats['avg_similarity'] / stats['count']
            
            f.write(f"\n{tier.upper()} Tier:\n")
            f.write(f"  Samples: {stats['count']}\n")
            f.write(f"  Compression Ratio: {compression_ratio:.1f}%\n")
            f.write(f"  Average Semantic Similarity: {avg_similarity:.1f}%\n")
        
        # Top Performers
        f.write(f"\n🏆 TOP PERFORMERS\n")
        f.write("-" * 40 + "\n")
        
        # Best compression
        best_compression = sorted(results, key=lambda x: x['compression_ratio'], reverse=True)[:5]
        f.write("Best Compression Ratios:\n")
        for i, r in enumerate(best_compression, 1):
            f.write(f"  {i}. {r['sample_name']}: {r['compression_ratio']:.1f}% ({r['category']})\n")
        
        # Best semantic preservation
        best_semantic = sorted(results, key=lambda x: x['semantic_similarity'], reverse=True)[:5]
        f.write(f"\nBest Semantic Preservation:\n")
        for i, r in enumerate(best_semantic, 1):
            f.write(f"  {i}. {r['sample_name']}: {r['semantic_similarity']:.1f}% ({r['category']})\n")
        
        # Sample Details (first 10 for brevity)
        f.write(f"\n📋 SAMPLE DETAILS (Top 10 by Compression)\n")
        f.write("=" * 80 + "\n")
        
        top_samples = sorted(results, key=lambda x: x['compression_ratio'], reverse=True)[:10]
        for i, result in enumerate(top_samples, 1):
            f.write(f"\n{i}. {result['sample_name']} ({result['category']})\n")
            f.write("-" * 50 + "\n")
            f.write(f"Tier: {result['tier'].upper()}, Method: {result['method']}\n")
            f.write(f"Tokens: {result['original_tokens']:,} → {result['compressed_tokens']:,} ({result['token_reduction']:,})\n")
            f.write(f"Compression: {result['compression_ratio']:.1f}%, Semantic: {result['semantic_similarity']:.1f}%\n")
        
        f.write(f"\nEnd of Report\n")
        f.write("=" * 80 + "\n")

def run_comprehensive_samples_demo():
    """Run comprehensive waterfall compression demo on all samples."""
    print("🌊 COMPREHENSIVE WATERFALL COMPRESSION DEMO - ALL SAMPLES")
    print("=" * 70)
    
    # Initialize compressor
    compressor = WaterfallCompressor(
        llm_model="gpt-4",
        llm_token_limit=128000,
        chunk_size=5000
    )
    
    # Extract all samples
    samples_file = project_root / "input_optimizer" / "samples" / "waterfall_samples.py"
    print(f"📁 Extracting samples from: {samples_file.name}")
    
    samples = extract_samples_from_file(samples_file)
    print(f"📊 Found {len(samples)} samples to analyze")
    print("-" * 70)
    
    results = []
    
    for i, (sample_name, sample_code) in enumerate(samples.items(), 1):
        print(f"\n[{i:2d}/{len(samples)}] {sample_name}")
        
        try:
            # Analyze sample
            original_tokens = count_tokens(sample_code)
            category = categorize_sample(sample_name, sample_code)
            
            # Compress using waterfall method
            result = compressor.compress_string(sample_code)
            
            # Calculate metrics
            compression_ratio = result.compression_ratio
            token_reduction = original_tokens - result.compressed_tokens
            semantic_similarity = calculate_semantic_similarity(sample_code, result.content)
            
            # Performance indicator
            if compression_ratio > 50:
                performance = "🟢"
            elif compression_ratio > 25:
                performance = "🟡"
            elif compression_ratio > 0:
                performance = "🟠"
            else:
                performance = "🔴"
            
            print(f"  {performance} {category:<20} | {result.tier_used.value.upper():<6} | {compression_ratio:5.1f}% | {semantic_similarity:5.1f}% | {original_tokens:4d}→{result.compressed_tokens:3d}")
            
            # Store result
            results.append({
                'sample_name': sample_name,
                'category': category,
                'tier': result.tier_used.value,
                'method': result.method_used,
                'original_tokens': original_tokens,
                'compressed_tokens': result.compressed_tokens,
                'compression_ratio': compression_ratio,
                'semantic_similarity': semantic_similarity,
                'token_reduction': token_reduction,
                'original_code': sample_code,
                'compressed_code': result.content
            })
            
        except Exception as e:
            print(f"  ❌ Error processing {sample_name}: {e}")
    
    # Summary
    if results:
        print(f"\n📈 SUMMARY")
        print("=" * 70)
        
        total_original = sum(r['original_tokens'] for r in results)
        total_compressed = sum(r['compressed_tokens'] for r in results)
        total_reduction = total_original - total_compressed
        avg_compression = (total_reduction / total_original * 100) if total_original > 0 else 0
        avg_similarity = sum(r['semantic_similarity'] for r in results) / len(results)
        
        print(f"Samples Processed: {len(results)}")
        print(f"Total Token Reduction: {total_reduction:,} ({avg_compression:.1f}% average)")
        print(f"Average Semantic Similarity: {avg_similarity:.1f}%")
        
        # Performance breakdown
        excellent = sum(1 for r in results if r['compression_ratio'] > 50)
        good = sum(1 for r in results if 25 < r['compression_ratio'] <= 50)
        moderate = sum(1 for r in results if 0 < r['compression_ratio'] <= 25)
        minimal = sum(1 for r in results if r['compression_ratio'] <= 0)
        
        print(f"\nPerformance Breakdown:")
        print(f"  🟢 Excellent (>50%): {excellent}")
        print(f"  🟡 Good (25-50%): {good}")
        print(f"  🟠 Moderate (0-25%): {moderate}")
        print(f"  🔴 Minimal (≤0%): {minimal}")
        
        # Export results
        results_file = project_root / "comprehensive_samples_results.json"
        detailed_report_file = project_root / "comprehensive_samples_report.txt"
        
        # Save JSON results
        with open(results_file, 'w') as f:
            json.dump(results, f, indent=2)
        
        # Create comprehensive report
        create_comprehensive_samples_report(results, detailed_report_file, compressor)
        
        print(f"\n💾 Detailed results: {results_file}")
        print(f"📄 Comprehensive report: {detailed_report_file}")

if __name__ == "__main__":
    run_comprehensive_samples_demo()
