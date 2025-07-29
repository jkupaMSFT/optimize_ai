#!/usr/bin/env python3
"""
Script to translate the entire sudo_lang_translator.py file to SynthLang 
and provide comprehensive statistical analysis of token reduction.
"""
import sys
from pathlib import Path
from datetime import datetime

# Add project paths
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from input_optimizer.engine.translators.synth_lang_translator import python_to_synthlang
from input_optimizer.engine.minifier import estimate_tokens

def load_sudo_lang_translator_code():
    """Load the entire sudo_lang_translator.py file as a code sample."""
    sudo_lang_file = project_root / "engine" / "translators" / "sudo_lang_translator.py"
    
    with open(sudo_lang_file, 'r', encoding='utf-8') as f:
        code = f.read()
    
    return code

def analyze_code_structure(code: str) -> dict:
    """Analyze the structure of the Python code for detailed statistics."""
    import ast
    
    try:
        tree = ast.parse(code)
        stats = {
            'total_lines': len(code.splitlines()),
            'total_chars': len(code),
            'functions': 0,
            'classes': 0,
            'imports': 0,
            'async_functions': 0,
            'decorators': 0,
            'comprehensions': 0,
            'try_except_blocks': 0,
            'if_statements': 0,
            'for_loops': 0,
            'while_loops': 0,
            'docstrings': 0
        }
        
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                stats['functions'] += 1
                if node.decorator_list:
                    stats['decorators'] += len(node.decorator_list)
                # Check for docstring
                if (node.body and isinstance(node.body[0], ast.Expr) and
                    ((isinstance(node.body[0].value, ast.Str)) or
                     (isinstance(node.body[0].value, ast.Constant) and isinstance(node.body[0].value.value, str)))):
                    stats['docstrings'] += 1
            elif isinstance(node, ast.AsyncFunctionDef):
                stats['async_functions'] += 1
                if node.decorator_list:
                    stats['decorators'] += len(node.decorator_list)
                if (node.body and isinstance(node.body[0], ast.Expr) and
                    ((isinstance(node.body[0].value, ast.Str)) or
                     (isinstance(node.body[0].value, ast.Constant) and isinstance(node.body[0].value.value, str)))):
                    stats['docstrings'] += 1
            elif isinstance(node, ast.ClassDef):
                stats['classes'] += 1
                if node.decorator_list:
                    stats['decorators'] += len(node.decorator_list)
                if (node.body and isinstance(node.body[0], ast.Expr) and
                    ((isinstance(node.body[0].value, ast.Str)) or
                     (isinstance(node.body[0].value, ast.Constant) and isinstance(node.body[0].value.value, str)))):
                    stats['docstrings'] += 1
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                stats['imports'] += 1
            elif isinstance(node, (ast.ListComp, ast.DictComp, ast.SetComp, ast.GeneratorExp)):
                stats['comprehensions'] += 1
            elif isinstance(node, ast.Try):
                stats['try_except_blocks'] += 1
            elif isinstance(node, ast.If):
                stats['if_statements'] += 1
            elif isinstance(node, ast.For):
                stats['for_loops'] += 1
            elif isinstance(node, ast.While):
                stats['while_loops'] += 1
        
        return stats
    except:
        return {'error': 'Failed to parse AST'}

def translate_sudo_lang_file(output_file="sudo_lang_to_synth_lang_translation.txt"):
    """
    Translate the entire sudo_lang_translator.py file to SynthLang and provide detailed analysis.
    """
    script_dir = Path(__file__).parent
    output_path = script_dir / output_file
    
    # Load the sudo_lang_translator.py file
    code = load_sudo_lang_translator_code()
    
    # Analyze code structure
    structure_stats = analyze_code_structure(code)
    
    # Open output file
    with open(output_path, 'w', encoding='utf-8') as f:
        # Write header
        f.write("=" * 80 + "\n")
        f.write("SUDO_LANG_TRANSLATOR.PY TO SYNTHLANG TRANSLATION ANALYSIS\n")
        f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write("=" * 80 + "\n\n")
        
        # Write file information
        f.write("SOURCE FILE ANALYSIS:\n")
        f.write("-" * 40 + "\n")
        f.write(f"File: engine/translators/sudo_lang_translator.py\n")
        f.write(f"Total Lines: {structure_stats.get('total_lines', 'N/A')}\n")
        f.write(f"Total Characters: {structure_stats.get('total_chars', 'N/A')}\n")
        
        if 'error' not in structure_stats:
            f.write(f"Functions: {structure_stats['functions']}\n")
            f.write(f"Async Functions: {structure_stats['async_functions']}\n")
            f.write(f"Classes: {structure_stats['classes']}\n")
            f.write(f"Import Statements: {structure_stats['imports']}\n")
            f.write(f"Decorators: {structure_stats['decorators']}\n")
            f.write(f"Docstrings: {structure_stats['docstrings']}\n")
            f.write(f"Comprehensions: {structure_stats['comprehensions']}\n")
            f.write(f"Try/Except Blocks: {structure_stats['try_except_blocks']}\n")
            f.write(f"If Statements: {structure_stats['if_statements']}\n")
            f.write(f"For Loops: {structure_stats['for_loops']}\n")
            f.write(f"While Loops: {structure_stats['while_loops']}\n")
        
        f.write("\n" + "=" * 80 + "\n\n")
        
        # Estimate tokens for original
        print("Analyzing original file...")
        original_tokens = estimate_tokens(code)
        f.write(f"ORIGINAL PYTHON CODE TOKEN ANALYSIS:\n")
        f.write("-" * 40 + "\n")
        f.write(f"Estimated Tokens: {original_tokens}\n\n")
        
        # Translate to SynthLang (both modes)
        print("Translating to SynthLang (readable mode)...")
        try:
            synthlang_readable = python_to_synthlang(code, compact=False, indent_size=2)
            readable_success = True
        except Exception as e:
            synthlang_readable = f"Translation failed: {str(e)}"
            readable_success = False
        
        print("Translating to SynthLang (compact mode)...")
        try:
            synthlang_compact = python_to_synthlang(code, compact=True)
            compact_success = True
        except Exception as e:
            synthlang_compact = f"Translation failed: {str(e)}"
            compact_success = False
        
        # Write readable version
        f.write("SYNTHLANG TRANSLATION (Readable Mode):\n")
        f.write("=" * 80 + "\n")
        if readable_success:
            f.write(synthlang_readable + "\n")
            readable_tokens = estimate_tokens(synthlang_readable)
        else:
            f.write(synthlang_readable + "\n")
            readable_tokens = original_tokens  # No reduction on error
        f.write("\n" + "=" * 80 + "\n\n")
        
        # Write compact version
        f.write("SYNTHLANG TRANSLATION (Compact Mode):\n")
        f.write("=" * 80 + "\n")
        if compact_success:
            f.write(synthlang_compact + "\n")
            compact_tokens = estimate_tokens(synthlang_compact)
        else:
            f.write(synthlang_compact + "\n")
            compact_tokens = original_tokens  # No reduction on error
        f.write("\n" + "=" * 80 + "\n\n")
        
        # Calculate detailed statistics
        readable_reduction = ((original_tokens - readable_tokens) / original_tokens) * 100 if original_tokens > 0 else 0
        compact_reduction = ((original_tokens - compact_tokens) / original_tokens) * 100 if original_tokens > 0 else 0
        
        readable_size = len(synthlang_readable) if readable_success else len(code)
        compact_size = len(synthlang_compact) if compact_success else len(code)
        
        readable_size_reduction = ((len(code) - readable_size) / len(code)) * 100 if len(code) > 0 else 0
        compact_size_reduction = ((len(code) - compact_size) / len(code)) * 100 if len(code) > 0 else 0
        
        # Write comprehensive statistics
        f.write("COMPREHENSIVE TRANSLATION STATISTICS:\n")
        f.write("=" * 80 + "\n\n")
        
        f.write("CHARACTER COUNT ANALYSIS:\n")
        f.write("-" * 40 + "\n")
        f.write(f"Original:           {len(code):8,} characters\n")
        f.write(f"Readable SynthLang: {readable_size:8,} characters ({readable_size_reduction:+.1f}%)\n")
        f.write(f"Compact SynthLang:  {compact_size:8,} characters ({compact_size_reduction:+.1f}%)\n\n")
        
        f.write("TOKEN COUNT ANALYSIS:\n")
        f.write("-" * 40 + "\n")
        f.write(f"Original:           {original_tokens:8,} tokens\n")
        f.write(f"Readable SynthLang: {readable_tokens:8,} tokens ({readable_reduction:+.1f}%)\n")
        f.write(f"Compact SynthLang:  {compact_tokens:8,} tokens ({compact_reduction:+.1f}%)\n\n")
        
        f.write("LINE COUNT ANALYSIS:\n")
        f.write("-" * 40 + "\n")
        original_lines = len(code.splitlines())
        readable_lines = len(synthlang_readable.splitlines()) if readable_success else original_lines
        compact_lines = len(synthlang_compact.splitlines()) if compact_success else original_lines
        
        readable_line_reduction = ((original_lines - readable_lines) / original_lines) * 100 if original_lines > 0 else 0
        compact_line_reduction = ((original_lines - compact_lines) / original_lines) * 100 if original_lines > 0 else 0
        
        f.write(f"Original:           {original_lines:8,} lines\n")
        f.write(f"Readable SynthLang: {readable_lines:8,} lines ({readable_line_reduction:+.1f}%)\n")
        f.write(f"Compact SynthLang:  {compact_lines:8,} lines ({compact_line_reduction:+.1f}%)\n\n")
        
        # Translation success analysis
        f.write("TRANSLATION SUCCESS ANALYSIS:\n")
        f.write("-" * 40 + "\n")
        f.write(f"Readable Mode Success: {'✓' if readable_success else '✗'}\n")
        f.write(f"Compact Mode Success:  {'✓' if compact_success else '✗'}\n\n")
        
        # Feature complexity analysis
        if 'error' not in structure_stats:
            f.write("CODE COMPLEXITY METRICS:\n")
            f.write("-" * 40 + "\n")
            total_constructs = (structure_stats['functions'] + structure_stats['async_functions'] + 
                              structure_stats['classes'] + structure_stats['comprehensions'] + 
                              structure_stats['try_except_blocks'])
            f.write(f"Total Complex Constructs: {total_constructs}\n")
            f.write(f"Average Lines per Construct: {structure_stats['total_lines'] / max(total_constructs, 1):.1f}\n")
            f.write(f"Average Tokens per Line: {original_tokens / structure_stats['total_lines']:.1f}\n")
            f.write(f"Documentation Ratio: {structure_stats['docstrings'] / max(structure_stats['functions'] + structure_stats['async_functions'] + structure_stats['classes'], 1):.1%}\n")
        
        # Best mode recommendation
        f.write("\nRECOMMENDATION:\n")
        f.write("-" * 40 + "\n")
        if compact_success and readable_success:
            if compact_reduction > readable_reduction:
                f.write(f"Compact mode provides better token reduction ({compact_reduction:.1f}% vs {readable_reduction:.1f}%)\n")
            else:
                f.write(f"Readable mode provides better balance of reduction and readability\n")
        elif compact_success:
            f.write("Only compact mode translation succeeded\n")
        elif readable_success:
            f.write("Only readable mode translation succeeded\n")
        else:
            f.write("Translation failed in both modes - file may contain unsupported Python features\n")
    
    return {
        'output_path': output_path,
        'original_tokens': original_tokens,
        'readable_tokens': readable_tokens if readable_success else original_tokens,
        'compact_tokens': compact_tokens if compact_success else original_tokens,
        'readable_success': readable_success,
        'compact_success': compact_success,
        'structure_stats': structure_stats
    }

def main():
    """Main function to run the translation and analysis."""
    print("Starting comprehensive translation analysis of sudo_lang_translator.py...")
    print("=" * 80)
    
    # Load and display file info
    code = load_sudo_lang_translator_code()
    print(f"Loaded file: {len(code):,} characters, {len(code.splitlines()):,} lines")
    
    # Perform translation and analysis
    results = translate_sudo_lang_file()
    
    # Print summary
    print("\n" + "=" * 80)
    print("TRANSLATION ANALYSIS SUMMARY:")
    print("=" * 80)
    print(f"Output file: {results['output_path']}")
    print(f"Original tokens: {results['original_tokens']:,}")
    
    if results['readable_success']:
        readable_reduction = ((results['original_tokens'] - results['readable_tokens']) / results['original_tokens']) * 100
        print(f"Readable mode: {results['readable_tokens']:,} tokens ({readable_reduction:+.1f}%)")
    else:
        print("Readable mode: Translation failed")
    
    if results['compact_success']:
        compact_reduction = ((results['original_tokens'] - results['compact_tokens']) / results['original_tokens']) * 100
        print(f"Compact mode: {results['compact_tokens']:,} tokens ({compact_reduction:+.1f}%)")
    else:
        print("Compact mode: Translation failed")
    
    # Show best result
    if results['compact_success'] or results['readable_success']:
        if results['compact_success']:
            best_tokens = results['compact_tokens']
            best_mode = "compact"
        else:
            best_tokens = results['readable_tokens']
            best_mode = "readable"
        
        best_reduction = ((results['original_tokens'] - best_tokens) / results['original_tokens']) * 100
        print(f"\nBest result: {best_mode} mode with {best_reduction:+.1f}% token reduction")
        
        # Calculate potential savings in a real scenario
        if best_reduction > 0:
            print(f"In a 100,000 token context: ~{int(100000 * (best_reduction/100)):,} tokens saved")
    
    print(f"\nDetailed analysis saved to: {results['output_path']}")

if __name__ == "__main__":
    main()
