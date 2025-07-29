#!/usr/bin/env python3
"""
Script to minify all samples from tests/samples.py and save results to a text file.
"""

import sys
from pathlib import Path
from datetime import datetime

# Add project paths
project_root = Path(__file__).parent.parent.parent  # Go up to optimize_ai root
sys.path.insert(0, str(project_root))

import sys
from pathlib import Path

# Add project root to path for imports
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from input_optimizer.engine.minifier import (
    minify_basic, minify_aggressive, minify_with_stats, 
    minify_depth, CompressionDepth
)
from utils.logger import estimate_tokens

def load_samples():
    """Load samples directly from the samples.py file."""
    samples_file = project_root / "input_optimizer" / "samples" / "samples.py"
    
    # Execute the samples file to get the variables
    namespace = {}
    with open(samples_file, 'r') as f:
        exec(f.read(), namespace)
    
    # Extract sample variables
    samples_dict = {name: value for name, value in namespace.items() 
                   if name.startswith('sample') and isinstance(value, str)}
    
    return samples_dict

def minify_all_samples(output_file="minified_samples.txt"):
    """
    Minify all samples and save results to a text file.
    
    Args:
        output_file: Path to the output text file
    """
    
    # Load samples from file
    samples_dict = load_samples()
    sample_vars = sorted(samples_dict.keys())  # Sort to get sample1, sample2, etc. in order
    
    results = []
    
    print(f"Found {len(sample_vars)} samples to minify...")
    
    for var_name in sample_vars:
        sample_code = samples_dict[var_name]
        sample_num = var_name.replace('sample', '')
        
        print(f"Processing Sample {sample_num}...")
        
        try:
            # Get minification results for all 4 compression depths
            depth_results = {}
            depth_names = {
                1: "comments_only",
                2: "constants", 
                3: "variables",
                4: "aggressive"
            }
            
            for depth in range(1, 5):
                minified = minify_depth(sample_code, depth)
                
                # Enhanced token counting with tiktoken
                original_tokens_tiktoken = estimate_tokens(sample_code, method="tiktoken", model_type="gpt-4")
                original_tokens_simple = estimate_tokens(sample_code, method="simple", model_type="gpt-4")
                minified_tokens_tiktoken = estimate_tokens(minified, method="tiktoken", model_type="gpt-4")
                minified_tokens_simple = estimate_tokens(minified, method="simple", model_type="gpt-4")
                
                stats = {
                    "original_size": len(sample_code),
                    "minified_size": len(minified),
                    "size_reduction": len(sample_code) - len(minified),
                    "size_reduction_percent": ((len(sample_code) - len(minified)) / len(sample_code)) * 100,
                    "original_tokens_tiktoken": original_tokens_tiktoken,
                    "original_tokens_simple": original_tokens_simple,
                    "minified_tokens_tiktoken": minified_tokens_tiktoken,
                    "minified_tokens_simple": minified_tokens_simple,
                    "compression_depth": depth
                }
                
                # Calculate reductions using tiktoken (primary) and simple (comparison)
                stats["token_reduction_tiktoken"] = original_tokens_tiktoken - minified_tokens_tiktoken
                stats["token_reduction_percent_tiktoken"] = (stats["token_reduction_tiktoken"] / original_tokens_tiktoken) * 100 if original_tokens_tiktoken > 0 else 0
                stats["token_reduction_simple"] = original_tokens_simple - minified_tokens_simple
                stats["token_reduction_percent_simple"] = (stats["token_reduction_simple"] / original_tokens_simple) * 100 if original_tokens_simple > 0 else 0
                
                # Legacy fields for backward compatibility (using tiktoken)
                stats["original_tokens"] = original_tokens_tiktoken
                stats["minified_tokens"] = minified_tokens_tiktoken
                stats["token_reduction"] = stats["token_reduction_tiktoken"]
                stats["token_reduction_percent"] = stats["token_reduction_percent_tiktoken"]
                
                depth_results[depth] = {
                    'minified': minified,
                    'stats': stats,
                    'name': depth_names[depth]
                }
            
            # Store results
            results.append({
                'number': sample_num,
                'original': sample_code,
                'depth_results': depth_results
            })
            
        except Exception as e:
            print(f"Error processing Sample {sample_num}: {e}")
            results.append({
                'number': sample_num,
                'original': sample_code,
                'error': str(e)
            })
    
    # Write results to file
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write("="*80 + "\n")
        f.write("PYTHON CODE MINIFIER RESULTS WITH TIKTOKEN INTEGRATION\n")
        f.write(f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Total samples processed: {len(results)}\n")
        f.write("Token counting: tiktoken (precise) + simple (comparison)\n")
        f.write("="*80 + "\n\n")
        
        for result in results:
            f.write(f"SAMPLE {result['number']}\n")
            f.write("-" * 40 + "\n\n")
            
            if 'error' in result:
                f.write("ERROR during minification:\n")
                f.write(f"{result['error']}\n\n")
                f.write("Original code:\n")
                f.write(result['original'] + "\n\n")
                continue
            
            # Original code
            f.write("ORIGINAL CODE:\n")
            f.write(result['original'] + "\n\n")
            
            # All compression depths
            depth_names = {1: "COMMENTS ONLY", 2: "CONSTANTS", 3: "VARIABLES", 4: "AGGRESSIVE"}
            
            for depth in range(1, 5):
                depth_data = result['depth_results'][depth]
                
                f.write(f"{depth_names[depth]} MINIFICATION (Depth {depth}):\n")
                f.write(depth_data['minified'] + "\n\n")
                
                stats = depth_data['stats']
                f.write(f"Depth {depth} Stats:\n")
                f.write(f"  Size reduction: {stats['size_reduction_percent']:.1f}%\n")
                f.write(f"  Token reduction (tiktoken): {stats['token_reduction_percent_tiktoken']:.1f}%\n")
                f.write(f"  Token reduction (simple): {stats['token_reduction_percent_simple']:.1f}%\n")
                f.write(f"  Original: {stats['original_size']} chars, {stats['original_tokens_tiktoken']} tokens (tiktoken), {stats['original_tokens_simple']} tokens (simple)\n")
                f.write(f"  Minified: {stats['minified_size']} chars, {stats['minified_tokens_tiktoken']} tokens (tiktoken), {stats['minified_tokens_simple']} tokens (simple)\n\n")
            
            f.write("="*80 + "\n\n")
    
    # Print summary
    print(f"\n✅ Minification complete!")
    print(f"Results saved to: {output_file}")
    
    # Calculate overall stats for all compression depths
    successful_results = [r for r in results if 'error' not in r]
    if successful_results:
        total_original_size = sum(r['depth_results'][1]['stats']['original_size'] for r in successful_results)
        
        depth_names = {1: "Comments Only", 2: "Constants", 3: "Variables", 4: "Aggressive"}
        
        print(f"\nOVERALL STATISTICS:")
        print(f"  Samples processed: {len(successful_results)}")
        print(f"  Total original size: {total_original_size:,} characters")
        
        for depth in range(1, 5):
            total_depth_size = sum(r['depth_results'][depth]['stats']['minified_size'] for r in successful_results)
            depth_reduction = ((total_original_size - total_depth_size) / total_original_size) * 100
            print(f"  Depth {depth} ({depth_names[depth]}): {total_depth_size:,} characters ({depth_reduction:.1f}% reduction)")
        
        # Show progressive improvement
        print(f"\nPROGRESSIVE IMPROVEMENT:")
        prev_size = total_original_size
        for depth in range(1, 5):
            total_depth_size = sum(r['depth_results'][depth]['stats']['minified_size'] for r in successful_results)
            additional_reduction = ((prev_size - total_depth_size) / total_original_size) * 100
            if depth == 1:
                print(f"  Depth {depth}: {additional_reduction:.1f}% reduction from original")
            else:
                print(f"  Depth {depth}: +{additional_reduction:.1f}% additional reduction")
            prev_size = total_depth_size


def create_comparison_file(output_file="sample_comparison.txt"):
    """
    Create a side-by-side comparison file for easier viewing.
    """
    samples_dict = load_samples()
    sample_vars = sorted(samples_dict.keys())
    
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write("SAMPLE COMPARISON - ALL COMPRESSION DEPTHS\n")
        f.write("="*150 + "\n\n")
        
        for var_name in sample_vars:
            sample_code = samples_dict[var_name]
            sample_num = var_name.replace('sample', '')
            
            try:
                # Get all 4 compression depths
                minified_results = {}
                for depth in range(1, 5):
                    minified_results[depth] = minify_depth(sample_code, depth)
                
                f.write(f"SAMPLE {sample_num}\n")
                f.write("-" * 80 + "\n")
                f.write("ORIGINAL → DEPTH 1 → DEPTH 2 → DEPTH 3 → DEPTH 4\n")
                f.write("(Comments Only → Constants → Variables → Aggressive)\n\n")
                
                # Split into lines for comparison
                orig_lines = sample_code.strip().split('\n')
                depth_lines = {}
                max_lines = len(orig_lines)
                
                for depth in range(1, 5):
                    depth_lines[depth] = minified_results[depth].strip().split('\n')
                    max_lines = max(max_lines, len(depth_lines[depth]))
                
                for i in range(max_lines):
                    orig_line = orig_lines[i] if i < len(orig_lines) else ""
                    depth1_line = depth_lines[1][i] if i < len(depth_lines[1]) else ""
                    depth2_line = depth_lines[2][i] if i < len(depth_lines[2]) else ""
                    depth3_line = depth_lines[3][i] if i < len(depth_lines[3]) else ""
                    depth4_line = depth_lines[4][i] if i < len(depth_lines[4]) else ""
                    
                    f.write(f"{orig_line:<25} | {depth1_line:<25} | {depth2_line:<25} | {depth3_line:<25} | {depth4_line}\n")
                
                # Show size progression
                f.write(f"\nSize progression:\n")
                f.write(f"Original: {len(sample_code)} chars\n")
                for depth in range(1, 5):
                    size = len(minified_results[depth])
                    reduction = ((len(sample_code) - size) / len(sample_code)) * 100
                    f.write(f"Depth {depth}: {size} chars ({reduction:.1f}% reduction)\n")
                
                f.write("\n" + "="*150 + "\n\n")
                
            except Exception as e:
                f.write(f"Error processing Sample {sample_num}: {e}\n\n")


if __name__ == "__main__":
    print("🔧 Python Code Minifier - Sample Processing")
    print("=" * 50)
    
    # Create detailed results file
    minify_all_samples("minified_samples.txt")
    
    # Create comparison file
    print("\n📊 Creating comparison file...")
    create_comparison_file("sample_comparison.txt")
    print("✅ Comparison file saved to: sample_comparison.txt")
    
    print("\n🎉 All done! Check the generated files:")
    print("  - minified_samples.txt (detailed results with all 4 compression depths)")
    print("  - sample_comparison.txt (side-by-side comparison across all depths)") 