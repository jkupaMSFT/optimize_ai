#!/usr/bin/env python3
"""
Script to translate all samples from tests/samples.py to Sudolang and save results to a text file.
"""

import sys
from pathlib import Path
from datetime import datetime

# Add project paths
project_root = Path(__file__).parent.parent.parent  # Go up 3 levels: samples/translator/ -> samples/ -> optimize_ai/
sys.path.insert(0, str(project_root))

from engine.translator import python_to_sudolang
from engine.minifier import estimate_tokens

def load_samples():
    """Load samples directly from the samples.py file."""
    samples_file = project_root / "tests" / "samples.py"
    
    # Execute the samples file to get the variables
    namespace = {}
    with open(samples_file, 'r') as f:
        exec(f.read(), namespace)
    
    # Extract sample variables
    samples_dict = {name: value for name, value in namespace.items() 
                   if name.startswith('sample') and isinstance(value, str)}
    
    return samples_dict

def translate_all_samples(output_file="translated_samples.txt"):
    """
    Translate all samples to Sudolang and save results to a text file.
    
    Args:
        output_file: Path to the output text file (relative to script directory)
    """
    
    # Ensure output file is in the script directory
    script_dir = Path(__file__).parent
    output_path = script_dir / output_file
    
    # Load samples from file
    samples_dict = load_samples()
    sample_vars = sorted(samples_dict.keys())  # Sort to get sample1, sample2, etc. in order
    
    results = []
    
    print(f"Found {len(sample_vars)} samples to translate...")
    
    for var_name in sample_vars:
        sample_code = samples_dict[var_name]
        sample_num = var_name.replace('sample', '')
        
        print(f"Processing Sample {sample_num}...")
        
        try:
            # Translate Python to Sudolang
            translated_code = python_to_sudolang(sample_code)
            
            # Calculate metrics
            original_size = len(sample_code)
            translated_size = len(translated_code)
            size_change = translated_size - original_size
            size_change_percent = (size_change / original_size * 100) if original_size > 0 else 0
            
            # Token estimation
            original_tokens = estimate_tokens(sample_code)
            translated_tokens = estimate_tokens(translated_code)
            token_change = translated_tokens - original_tokens
            token_change_percent = (token_change / original_tokens * 100) if original_tokens > 0 else 0
            
            # Store results
            results.append({
                'number': sample_num,
                'original': sample_code,
                'translated': translated_code,
                'stats': {
                    "original_size": original_size,
                    "translated_size": translated_size,
                    "size_change": size_change,
                    "size_change_percent": size_change_percent,
                    "original_tokens": original_tokens,
                    "translated_tokens": translated_tokens,
                    "token_change": token_change,
                    "token_change_percent": token_change_percent,
                    "compression_ratio": translated_size / original_size if original_size > 0 else 1.0
                }
            })
            
        except Exception as e:
            print(f"Error processing Sample {sample_num}: {e}")
            results.append({
                'number': sample_num,
                'original': sample_code,
                'error': str(e)
            })
    
    # Write results to file
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write("="*80 + "\n")
        f.write("PYTHON TO SUDOLANG TRANSLATION RESULTS\n")
        f.write(f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Total samples processed: {len(results)}\n")
        f.write("="*80 + "\n\n")
        
        for result in results:
            f.write(f"SAMPLE {result['number']}\n")
            f.write("-" * 40 + "\n\n")
            
            if 'error' in result:
                f.write("ERROR during translation:\n")
                f.write(f"{result['error']}\n\n")
                f.write("Original Python code:\n")
                f.write(result['original'] + "\n\n")
                continue
            
            # Original Python code
            f.write("ORIGINAL PYTHON CODE:\n")
            f.write(result['original'] + "\n\n")
            
            # Translated Sudolang code
            f.write("TRANSLATED SUDOLANG CODE:\n")
            f.write(result['translated'] + "\n\n")
            
            # Statistics
            stats = result['stats']
            f.write("TRANSLATION STATISTICS:\n")
            f.write(f"  Size change: {stats['size_change']:+d} chars ({stats['size_change_percent']:+.1f}%)\n")
            f.write(f"  Token change: {stats['token_change']:+d} tokens ({stats['token_change_percent']:+.1f}%)\n")
            f.write(f"  Original: {stats['original_size']} chars, {stats['original_tokens']} tokens\n")
            f.write(f"  Translated: {stats['translated_size']} chars, {stats['translated_tokens']} tokens\n")
            f.write(f"  Compression ratio: {stats['compression_ratio']:.3f}x\n\n")
            
            f.write("="*80 + "\n\n")
    
    # Print summary
    print(f"\n✅ Translation complete!")
    print(f"Results saved to: {output_path}")
    
    # Calculate overall statistics
    successful_results = [r for r in results if 'error' not in r]
    if successful_results:
        total_original_size = sum(r['stats']['original_size'] for r in successful_results)
        total_translated_size = sum(r['stats']['translated_size'] for r in successful_results)
        total_original_tokens = sum(r['stats']['original_tokens'] for r in successful_results)
        total_translated_tokens = sum(r['stats']['translated_tokens'] for r in successful_results)
        
        overall_size_change = total_translated_size - total_original_size
        overall_size_change_percent = (overall_size_change / total_original_size * 100) if total_original_size > 0 else 0
        overall_token_change = total_translated_tokens - total_original_tokens
        overall_token_change_percent = (overall_token_change / total_original_tokens * 100) if total_original_tokens > 0 else 0
        overall_compression_ratio = total_translated_size / total_original_size if total_original_size > 0 else 1.0
        
        print(f"\nOVERALL TRANSLATION STATISTICS:")
        print(f"  Samples successfully translated: {len(successful_results)}")
        print(f"  Total original size: {total_original_size:,} characters")
        print(f"  Total translated size: {total_translated_size:,} characters")
        print(f"  Overall size change: {overall_size_change:+,} characters ({overall_size_change_percent:+.1f}%)")
        print(f"  Total original tokens: {total_original_tokens:,}")
        print(f"  Total translated tokens: {total_translated_tokens:,}")
        print(f"  Overall token change: {overall_token_change:+,} tokens ({overall_token_change_percent:+.1f}%)")
        print(f"  Overall compression ratio: {overall_compression_ratio:.3f}x")
        
        # Show distribution of results
        size_reductions = [r for r in successful_results if r['stats']['size_change'] < 0]
        size_increases = [r for r in successful_results if r['stats']['size_change'] > 0]
        size_same = [r for r in successful_results if r['stats']['size_change'] == 0]
        
        token_reductions = [r for r in successful_results if r['stats']['token_change'] < 0]
        token_increases = [r for r in successful_results if r['stats']['token_change'] > 0]
        token_same = [r for r in successful_results if r['stats']['token_change'] == 0]
        
        print(f"\nSIZE DISTRIBUTION:")
        print(f"  Samples with size reduction: {len(size_reductions)}")
        print(f"  Samples with size increase: {len(size_increases)}")
        print(f"  Samples with same size: {len(size_same)}")
        
        print(f"\nTOKEN DISTRIBUTION:")
        print(f"  Samples with token reduction: {len(token_reductions)}")
        print(f"  Samples with token increase: {len(token_increases)}")
        print(f"  Samples with same tokens: {len(token_same)}")

def create_comparison_file(output_file="translation_comparison.txt"):
    """
    Create a side-by-side comparison file for easier viewing.
    """
    script_dir = Path(__file__).parent
    output_path = script_dir / output_file
    
    samples_dict = load_samples()
    sample_vars = sorted(samples_dict.keys())
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write("PYTHON TO SUDOLANG SIDE-BY-SIDE COMPARISON\n")
        f.write("="*120 + "\n\n")
        
        for var_name in sample_vars:
            sample_code = samples_dict[var_name]
            sample_num = var_name.replace('sample', '')
            
            try:
                translated_code = python_to_sudolang(sample_code)
                
                f.write(f"SAMPLE {sample_num}\n")
                f.write("-" * 60 + "\n")
                f.write("PYTHON CODE                          |  SUDOLANG CODE\n")
                f.write("-" * 60 + "\n")
                
                # Split into lines for comparison
                python_lines = sample_code.strip().split('\n')
                sudolang_lines = translated_code.strip().split('\n')
                max_lines = max(len(python_lines), len(sudolang_lines))
                
                for i in range(max_lines):
                    python_line = python_lines[i] if i < len(python_lines) else ""
                    sudolang_line = sudolang_lines[i] if i < len(sudolang_lines) else ""
                    
                    # Truncate long lines for readability
                    python_display = python_line[:35] + "..." if len(python_line) > 35 else python_line
                    sudolang_display = sudolang_line[:35] + "..." if len(sudolang_line) > 35 else sudolang_line
                    
                    f.write(f"{python_display:<37} | {sudolang_display}\n")
                
                # Show metrics
                original_tokens = estimate_tokens(sample_code)
                translated_tokens = estimate_tokens(translated_code)
                token_change = translated_tokens - original_tokens
                token_change_percent = (token_change / original_tokens * 100) if original_tokens > 0 else 0
                
                f.write(f"\nTokens: {original_tokens} → {translated_tokens} ({token_change:+d}, {token_change_percent:+.1f}%)\n")
                f.write(f"Size: {len(sample_code)} → {len(translated_code)} chars\n")
                
                f.write("\n" + "="*120 + "\n\n")
                
            except Exception as e:
                f.write(f"Error translating Sample {sample_num}: {e}\n\n")

def create_summary_file(output_file="translation_summary.txt"):
    """
    Create a concise summary file showing key metrics for each sample.
    """
    script_dir = Path(__file__).parent
    output_path = script_dir / output_file
    
    samples_dict = load_samples()
    sample_vars = sorted(samples_dict.keys())
    
    results = []
    
    for var_name in sample_vars:
        sample_code = samples_dict[var_name]
        sample_num = var_name.replace('sample', '')
        
        try:
            translated_code = python_to_sudolang(sample_code)
            
            original_tokens = estimate_tokens(sample_code)
            translated_tokens = estimate_tokens(translated_code)
            token_change = translated_tokens - original_tokens
            token_change_percent = (token_change / original_tokens * 100) if original_tokens > 0 else 0
            
            results.append({
                'sample': sample_num,
                'python_tokens': original_tokens,
                'sudolang_tokens': translated_tokens,
                'token_change': token_change,
                'token_change_percent': token_change_percent,
                'python_size': len(sample_code),
                'sudolang_size': len(translated_code)
            })
            
        except Exception as e:
            results.append({
                'sample': sample_num,
                'error': str(e)
            })
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write("PYTHON TO SUDOLANG TRANSLATION SUMMARY\n")
        f.write("="*80 + "\n\n")
        
        f.write("Sample | Py Tokens | SL Tokens | Change | Change% | Py Size | SL Size\n")
        f.write("-------|-----------|-----------|--------|---------|---------|--------\n")
        
        for result in results:
            if 'error' in result:
                f.write(f"{result['sample']:>6} | ERROR: {result['error']}\n")
            else:
                f.write(f"{result['sample']:>6} | {result['python_tokens']:>9} | {result['sudolang_tokens']:>9} | "
                       f"{result['token_change']:>+6} | {result['token_change_percent']:>+6.1f}% | "
                       f"{result['python_size']:>7} | {result['sudolang_size']:>7}\n")
        
        f.write("\n")
        
        # Calculate totals for successful translations
        successful = [r for r in results if 'error' not in r]
        if successful:
            total_py_tokens = sum(r['python_tokens'] for r in successful)
            total_sl_tokens = sum(r['sudolang_tokens'] for r in successful)
            total_token_change = total_sl_tokens - total_py_tokens
            total_token_change_percent = (total_token_change / total_py_tokens * 100) if total_py_tokens > 0 else 0
            total_py_size = sum(r['python_size'] for r in successful)
            total_sl_size = sum(r['sudolang_size'] for r in successful)
            
            f.write("TOTALS:\n")
            f.write(f"Python tokens: {total_py_tokens:,}\n")
            f.write(f"Sudolang tokens: {total_sl_tokens:,}\n")
            f.write(f"Token change: {total_token_change:+,} ({total_token_change_percent:+.1f}%)\n")
            f.write(f"Python size: {total_py_size:,} chars\n")
            f.write(f"Sudolang size: {total_sl_size:,} chars\n")

if __name__ == "__main__":
    print("🔧 Python to Sudolang Translator - Sample Processing")
    print("=" * 60)
    
    # Create detailed results file
    translate_all_samples("translated_samples.txt")
    
    # Create comparison file
    print("\n📊 Creating comparison file...")
    create_comparison_file("translation_comparison.txt")
    print("✅ Comparison file saved to: samples/translator/translation_comparison.txt")
    
    # Create summary file
    print("\n📋 Creating summary file...")
    create_summary_file("translation_summary.txt")
    print("✅ Summary file saved to: samples/translator/translation_summary.txt")
    
    print("\n🎉 All done! Check the generated files in samples/translator/:")
    print("  - translated_samples.txt (detailed results with full translations)")
    print("  - translation_comparison.txt (side-by-side comparison)")
    print("  - translation_summary.txt (concise metrics table)")