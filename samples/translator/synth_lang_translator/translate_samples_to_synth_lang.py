#!/usr/bin/env python3
"""
Script to translate all samples from samples.py to SynthLang and save results to a text file.
This script analyzes token reduction and provides statistics for each translation.
"""
import sys
from pathlib import Path
from datetime import datetime

# Add project paths
project_root = Path(__file__).parent.parent.parent.parent  # Go up 4 levels to optimize_ai/
sys.path.insert(0, str(project_root))

from engine.translators.synth_lang_translator import python_to_synthlang
from utils.logger import estimate_tokens

def load_samples():
    """Load samples directly from the samples.py file."""
    samples_file = project_root / "samples" / "samples.py"
    
    # Execute the samples file to get the variables
    namespace = {}
    with open(samples_file, 'r') as f:
        exec(f.read(), namespace)
    
    # Extract sample variables
    samples_dict = {name: value for name, value in namespace.items() 
                   if name.startswith('sample') and isinstance(value, str)}
    
    # Sort by sample number
    sorted_samples = sorted(samples_dict.items(), 
                          key=lambda x: int(x[0].replace('sample', '')))
    
    return dict(sorted_samples)

def translate_all_samples(output_file="translated_samples_synthlang.txt"):
    """
    Translate all samples to SynthLang and save results to a text file.
    
    Args:
        output_file: Path to the output text file (relative to script directory)
    """
    
    # Ensure output file is in the script directory
    script_dir = Path(__file__).parent
    output_path = script_dir / output_file
    
    samples = load_samples()
    
    # Open output file
    with open(output_path, 'w', encoding='utf-8') as f:
        # Write header
        f.write("=" * 80 + "\n")
        f.write("PYTHON TO SYNTHLANG TRANSLATION RESULTS WITH TIKTOKEN\n")
        f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Total Samples: {len(samples)}\n")
        f.write("Token counting: tiktoken (precise) + simple (comparison)\n")
        f.write("=" * 80 + "\n\n")
        
        total_original_tokens = 0
        total_translated_tokens = 0
        
        # Process each sample
        for name, code in samples.items():
            sample_num = name.replace('sample', '')
            print(f"Translating {name}...")
            
            # Write sample header
            f.write(f"{'='*60}\n")
            f.write(f"SAMPLE {sample_num}\n")
            f.write(f"{'='*60}\n\n")
            
            # Write original Python code
            f.write("ORIGINAL PYTHON:\n")
            f.write("-" * 40 + "\n")
            f.write(code + "\n")
            f.write("-" * 40 + "\n")
            
            # Estimate tokens for original using both tiktoken and simple methods
            original_tokens_tiktoken = estimate_tokens(code, method="tiktoken", model_type="gpt-4")
            original_tokens_simple = estimate_tokens(code, method="simple", model_type="gpt-4")
            f.write(f"Tokens (tiktoken): {original_tokens_tiktoken}\n")
            f.write(f"Tokens (simple): {original_tokens_simple}\n\n")
            
            # Translate to SynthLang
            try:
                # First try compact mode for better token reduction
                synthlang_code_compact = python_to_synthlang(code, compact=True)
                synthlang_code_readable = python_to_synthlang(code, compact=False)
                
                # Write readable version
                f.write("SYNTHLANG TRANSLATION (Readable):\n")
                f.write("-" * 40 + "\n")
                f.write(synthlang_code_readable + "\n")
                f.write("-" * 40 + "\n")
                
                # Estimate tokens for readable version using both methods
                readable_tokens_tiktoken = estimate_tokens(synthlang_code_readable, method="tiktoken", model_type="gpt-4")
                readable_tokens_simple = estimate_tokens(synthlang_code_readable, method="simple", model_type="gpt-4")
                f.write(f"Tokens (tiktoken): {readable_tokens_tiktoken}\n")
                f.write(f"Tokens (simple): {readable_tokens_simple}\n\n")
                
                # Write compact version
                f.write("SYNTHLANG TRANSLATION (Compact):\n")
                f.write("-" * 40 + "\n")
                f.write(synthlang_code_compact + "\n")
                f.write("-" * 40 + "\n")
                
                # Estimate tokens for compact version using both methods
                compact_tokens_tiktoken = estimate_tokens(synthlang_code_compact, method="tiktoken", model_type="gpt-4")
                compact_tokens_simple = estimate_tokens(synthlang_code_compact, method="simple", model_type="gpt-4")
                f.write(f"Tokens (tiktoken): {compact_tokens_tiktoken}\n")
                f.write(f"Tokens (simple): {compact_tokens_simple}\n\n")
                
                # Calculate reduction using tiktoken (primary) and simple (comparison)
                readable_reduction_tiktoken = ((original_tokens_tiktoken - readable_tokens_tiktoken) / original_tokens_tiktoken) * 100
                compact_reduction_tiktoken = ((original_tokens_tiktoken - compact_tokens_tiktoken) / original_tokens_tiktoken) * 100
                readable_reduction_simple = ((original_tokens_simple - readable_tokens_simple) / original_tokens_simple) * 100
                compact_reduction_simple = ((original_tokens_simple - compact_tokens_simple) / original_tokens_simple) * 100
                
                f.write("TOKEN REDUCTION:\n")
                f.write("-" * 40 + "\n")
                f.write("Tiktoken (Precise) Method:\n")
                f.write(f"  Original:  {original_tokens_tiktoken:4d} tokens\n")
                f.write(f"  Readable:  {readable_tokens_tiktoken:4d} tokens ({readable_reduction_tiktoken:+.1f}%)\n")
                f.write(f"  Compact:   {compact_tokens_tiktoken:4d} tokens ({compact_reduction_tiktoken:+.1f}%)\n\n")
                f.write("Simple Estimation Method:\n")
                f.write(f"  Original:  {original_tokens_simple:4d} tokens\n")
                f.write(f"  Readable:  {readable_tokens_simple:4d} tokens ({readable_reduction_simple:+.1f}%)\n")
                f.write(f"  Compact:   {compact_tokens_simple:4d} tokens ({compact_reduction_simple:+.1f}%)\n")
                
                # Update totals (use tiktoken for statistics)
                total_original_tokens += original_tokens_tiktoken
                total_translated_tokens += compact_tokens_tiktoken
                
            except Exception as e:
                f.write(f"ERROR: Failed to translate - {str(e)}\n")
                # Still count original tokens
                total_original_tokens += original_tokens_tiktoken
                total_translated_tokens += original_tokens_tiktoken  # No reduction on error
            
            f.write("\n\n")
        
        # Write summary statistics
        f.write("=" * 80 + "\n")
        f.write("SUMMARY STATISTICS\n")
        f.write("=" * 80 + "\n\n")
        
        total_reduction = ((total_original_tokens - total_translated_tokens) / total_original_tokens) * 100
        
        f.write(f"Total Original Tokens:    {total_original_tokens:6d}\n")
        f.write(f"Total Translated Tokens:  {total_translated_tokens:6d}\n")
        f.write(f"Overall Token Reduction:  {total_reduction:+.1f}%\n")
        f.write(f"Average Tokens/Sample:    {total_translated_tokens/len(samples):.1f}\n")
        
        # Sample breakdown
        f.write("\nPER-SAMPLE SUMMARY (Compact Mode):\n")
        f.write("-" * 60 + "\n")
        f.write(f"{'Sample':<10} {'Original':>10} {'Translated':>12} {'Reduction':>12}\n")
        f.write("-" * 60 + "\n")
        
        # Reprocess for summary table
        for name, code in samples.items():
            try:
                original_tokens = estimate_tokens(code)
                synthlang_compact = python_to_synthlang(code, compact=True)
                translated_tokens = estimate_tokens(synthlang_compact)
                reduction = ((original_tokens - translated_tokens) / original_tokens) * 100
                f.write(f"{name:<10} {original_tokens:>10d} {translated_tokens:>12d} {reduction:>11.1f}%\n")
            except:
                f.write(f"{name:<10} {'ERROR':>10} {'ERROR':>12} {'N/A':>12}\n")
    
    print(f"\nTranslation complete! Results saved to: {output_path}")
    print(f"Total token reduction: {total_reduction:.1f}%")
    return output_path

def main():
    """Main function to run the translation."""
    print("Starting Python to SynthLang translation...")
    print("=" * 60)
    
    # Load and display sample count
    samples = load_samples()
    print(f"Found {len(samples)} samples to translate")
    
    # Translate all samples
    output_path = translate_all_samples()
    
    # Print final message
    print("\n" + "=" * 60)
    print("Translation Summary:")
    print(f"- Input: samples.py")
    print(f"- Output: {output_path}")
    print(f"- Samples processed: {len(samples)}")
    
    # Quick token comparison for first few samples
    print("\nQuick Preview (first 3 samples):")
    print("-" * 60)
    for i, (name, code) in enumerate(list(samples.items())[:3]):
        try:
            original_tokens = estimate_tokens(code)
            synthlang_compact = python_to_synthlang(code, compact=True)
            translated_tokens = estimate_tokens(synthlang_compact)
            reduction = ((original_tokens - translated_tokens) / original_tokens) * 100
            print(f"{name}: {original_tokens} → {translated_tokens} tokens ({reduction:+.1f}%)")
        except Exception as e:
            print(f"{name}: Translation error - {str(e)}")
    
    print("\nDone! Check the output file for detailed results.")

if __name__ == "__main__":
    main()