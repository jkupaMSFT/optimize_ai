#!/usr/bin/env python3
"""
Script to chain minification and SynthLang translation on all samples.
This script processes samples through both compression pipelines and provides
comprehensive statistics including semantic similarity analysis.
"""
import sys
import difflib
import re
import ast
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Tuple, Set

# Add project paths
project_root = Path(__file__).parent.parent.parent.parent  # Go up 4 levels to optimize_ai/
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root.parent))  # Add parent of optimize_ai for package imports

from input_optimizer.engine.minifier import minify_depth
from input_optimizer.engine.translators.synth_lang_translator import python_to_synthlang
from utils.logger import estimate_tokens

# Load samples directly from the samples.py file
def load_samples_from_file():
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

def extract_ast_features(code: str) -> Dict[str, Any]:
    """
    Extract structural features from AST for detailed similarity comparison.
    
    Returns:
        Dictionary containing various AST-based structural features
    """
    try:
        tree = ast.parse(code)
    except:
        return {
            'node_types': [],
            'function_names': [],
            'class_names': [],
            'variable_names': [],
            'control_structures': [],
            'import_statements': [],
            'decorators': [],
            'comprehensions': [],
            'exception_handlers': [],
            'ast_depth': 0,
            'node_count': 0,
            'complexity_score': 0
        }
    
    features = {
        'node_types': [],
        'function_names': [],
        'class_names': [],
        'variable_names': [],
        'control_structures': [],
        'import_statements': [],
        'decorators': [],
        'comprehensions': [],
        'exception_handlers': [],
        'ast_depth': 0,
        'node_count': 0,
        'complexity_score': 0
    }
    
    # Count nodes and track depth
    max_depth = 0
    node_count = 0
    complexity = 0
    
    def visit_node(node, depth=0):
        nonlocal max_depth, node_count, complexity
        max_depth = max(max_depth, depth)
        node_count += 1
        
        # Track node types
        node_type = type(node).__name__
        features['node_types'].append(node_type)
        
        # Calculate cyclomatic complexity
        if isinstance(node, (ast.If, ast.For, ast.While, ast.Try, ast.With, 
                           ast.ExceptHandler, ast.BoolOp)):
            complexity += 1
        
        # Extract function names and decorators
        if isinstance(node, ast.FunctionDef):
            features['function_names'].append(node.name)
            for decorator in node.decorator_list:
                if isinstance(decorator, ast.Name):
                    features['decorators'].append(decorator.id)
                elif isinstance(decorator, ast.Attribute):
                    features['decorators'].append(ast.unparse(decorator))
        
        # Extract class names
        elif isinstance(node, ast.ClassDef):
            features['class_names'].append(node.name)
            for decorator in node.decorator_list:
                if isinstance(decorator, ast.Name):
                    features['decorators'].append(decorator.id)
        
        # Extract variable assignments
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    features['variable_names'].append(target.id)
                elif isinstance(target, ast.Attribute):
                    features['variable_names'].append(target.attr)
        
        # Track control structures
        elif isinstance(node, (ast.If, ast.For, ast.While, ast.Try, ast.With)):
            features['control_structures'].append(node_type)
        
        # Track import statements
        elif isinstance(node, ast.Import):
            for alias in node.names:
                features['import_statements'].append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            for alias in node.names:
                features['import_statements'].append(f"{module}.{alias.name}")
        
        # Track comprehensions
        elif isinstance(node, (ast.ListComp, ast.DictComp, ast.SetComp, ast.GeneratorExp)):
            features['comprehensions'].append(node_type)
        
        # Track exception handlers
        elif isinstance(node, ast.ExceptHandler):
            if node.type:
                if isinstance(node.type, ast.Name):
                    features['exception_handlers'].append(node.type.id)
                else:
                    features['exception_handlers'].append(ast.unparse(node.type))
            else:
                features['exception_handlers'].append('Exception')
        
        # Recurse to children
        for child in ast.iter_child_nodes(node):
            visit_node(child, depth + 1)
    
    visit_node(tree)
    
    features['ast_depth'] = max_depth
    features['node_count'] = node_count
    features['complexity_score'] = complexity
    
    return features

def calculate_structural_similarity(original: str, transformed: str) -> Dict[str, float]:
    """
    Calculate comprehensive structural similarity metrics.
    
    Args:
        original: Original code
        transformed: Transformed code
        
    Returns:
        Dictionary with detailed structural similarity metrics
    """
    orig_features = extract_ast_features(original)
    trans_features = extract_ast_features(transformed)
    
    similarities = {}
    
    # 1. Node type distribution similarity
    orig_node_types = orig_features['node_types']
    trans_node_types = trans_features['node_types']
    
    if orig_node_types and trans_node_types:
        node_type_matcher = difflib.SequenceMatcher(None, orig_node_types, trans_node_types)
        similarities['node_type_similarity'] = node_type_matcher.ratio()
    else:
        similarities['node_type_similarity'] = 1.0 if not orig_node_types and not trans_node_types else 0.0
    
    # 2. Function name preservation
    orig_functions = set(orig_features['function_names'])
    trans_functions = set(trans_features['function_names'])
    
    if orig_functions:
        similarities['function_preservation'] = len(orig_functions & trans_functions) / len(orig_functions)
    else:
        similarities['function_preservation'] = 1.0 if not trans_functions else 0.0
    
    # 3. Class name preservation
    orig_classes = set(orig_features['class_names'])
    trans_classes = set(trans_features['class_names'])
    
    if orig_classes:
        similarities['class_preservation'] = len(orig_classes & trans_classes) / len(orig_classes)
    else:
        similarities['class_preservation'] = 1.0 if not trans_classes else 0.0
    
    # 4. Control structure preservation
    orig_controls = orig_features['control_structures']
    trans_controls = trans_features['control_structures']
    
    if orig_controls and trans_controls:
        control_matcher = difflib.SequenceMatcher(None, orig_controls, trans_controls)
        similarities['control_structure_similarity'] = control_matcher.ratio()
    else:
        similarities['control_structure_similarity'] = 1.0 if not orig_controls and not trans_controls else 0.0
    
    # 5. Import statement preservation
    orig_imports = set(orig_features['import_statements'])
    trans_imports = set(trans_features['import_statements'])
    
    if orig_imports:
        similarities['import_preservation'] = len(orig_imports & trans_imports) / len(orig_imports)
    else:
        similarities['import_preservation'] = 1.0 if not trans_imports else 0.0
    
    # 6. AST depth similarity
    orig_depth = orig_features['ast_depth']
    trans_depth = trans_features['ast_depth']
    
    if orig_depth > 0 or trans_depth > 0:
        max_depth = max(orig_depth, trans_depth)
        similarities['depth_similarity'] = 1 - abs(orig_depth - trans_depth) / max_depth
    else:
        similarities['depth_similarity'] = 1.0
    
    # 7. Complexity preservation
    orig_complexity = orig_features['complexity_score']
    trans_complexity = trans_features['complexity_score']
    
    if orig_complexity > 0 or trans_complexity > 0:
        max_complexity = max(orig_complexity, trans_complexity)
        similarities['complexity_preservation'] = 1 - abs(orig_complexity - trans_complexity) / max_complexity
    else:
        similarities['complexity_preservation'] = 1.0
    
    # 8. Comprehension preservation
    orig_comps = orig_features['comprehensions']
    trans_comps = trans_features['comprehensions']
    
    if orig_comps and trans_comps:
        comp_matcher = difflib.SequenceMatcher(None, orig_comps, trans_comps)
        similarities['comprehension_similarity'] = comp_matcher.ratio()
    else:
        similarities['comprehension_similarity'] = 1.0 if not orig_comps and not trans_comps else 0.0
    
    # 9. Overall structural similarity (weighted average)
    weights = {
        'node_type_similarity': 0.25,
        'function_preservation': 0.20,
        'class_preservation': 0.15,
        'control_structure_similarity': 0.15,
        'import_preservation': 0.10,
        'depth_similarity': 0.05,
        'complexity_preservation': 0.05,
        'comprehension_similarity': 0.05
    }
    
    similarities['structural_similarity'] = sum(
        similarities[metric] * weight for metric, weight in weights.items()
    )
    
    return similarities

def calculate_semantic_similarity(original: str, transformed: str) -> Dict[str, float]:
    """
    Calculate various similarity metrics between original and transformed code.
    
    Args:
        original: Original Python code
        transformed: Transformed code (minified or SynthLang)
        
    Returns:
        Dictionary containing various similarity metrics
    """
    # Basic string similarity using difflib
    sequence_matcher = difflib.SequenceMatcher(None, original, transformed)
    string_similarity = sequence_matcher.ratio()
    
    # Word-level similarity (split by whitespace and operators)
    original_words = re.findall(r'\w+|[^\w\s]', original)
    transformed_words = re.findall(r'\w+|[^\w\s]', transformed)
    
    word_matcher = difflib.SequenceMatcher(None, original_words, transformed_words)
    word_similarity = word_matcher.ratio()
    
    # Line-based similarity
    original_lines = [line.strip() for line in original.splitlines() if line.strip()]
    transformed_lines = [line.strip() for line in transformed.splitlines() if line.strip()]
    
    line_matcher = difflib.SequenceMatcher(None, original_lines, transformed_lines)
    line_similarity = line_matcher.ratio()
    
    # AST structure similarity (if both are valid Python)
    ast_similarity = 0.0
    try:
        original_ast = ast.dump(ast.parse(original))
        transformed_ast = ast.dump(ast.parse(transformed))
        
        ast_matcher = difflib.SequenceMatcher(None, original_ast, transformed_ast)
        ast_similarity = ast_matcher.ratio()
    except:
        # If either code isn't valid Python, AST similarity is 0
        ast_similarity = 0.0
    
    # Identifier preservation (count how many original identifiers are preserved)
    original_identifiers = set(re.findall(r'\b[a-zA-Z_][a-zA-Z0-9_]*\b', original))
    transformed_identifiers = set(re.findall(r'\b[a-zA-Z_][a-zA-Z0-9_]*\b', transformed))
    
    if original_identifiers:
        identifier_preservation = len(original_identifiers & transformed_identifiers) / len(original_identifiers)
    else:
        identifier_preservation = 1.0
    
    # Enhanced structural similarity
    structural_metrics = calculate_structural_similarity(original, transformed)
    
    # Combine all metrics
    result = {
        'string_similarity': string_similarity,
        'word_similarity': word_similarity,
        'line_similarity': line_similarity,
        'ast_similarity': ast_similarity,
        'identifier_preservation': identifier_preservation,
        'overall_similarity': (string_similarity + word_similarity + line_similarity + ast_similarity + identifier_preservation) / 5
    }
    
    # Add structural similarity metrics
    result.update(structural_metrics)
    
    # Update overall similarity to include structural similarity
    result['comprehensive_similarity'] = (
        result['overall_similarity'] * 0.6 + 
        structural_metrics['structural_similarity'] * 0.4
    )
    
    return result

def create_structural_analysis_report(sample_name: str, original: str, transformed: str, method_name: str) -> str:
    """
    Create a detailed structural analysis report for a specific transformation.
    
    Args:
        sample_name: Name of the sample
        original: Original code
        transformed: Transformed code
        method_name: Name of the transformation method
        
    Returns:
        Formatted report string
    """
    orig_features = extract_ast_features(original)
    trans_features = extract_ast_features(transformed)
    similarities = calculate_structural_similarity(original, transformed)
    
    report = []
    report.append(f"\n{'='*60}")
    report.append(f"STRUCTURAL ANALYSIS: {sample_name} - {method_name}")
    report.append(f"{'='*60}")
    
    # Feature comparison
    report.append(f"\nFEATURE COMPARISON:")
    report.append(f"{'Metric':<25} {'Original':<15} {'Transformed':<15} {'Similarity':<12}")
    report.append(f"{'-'*67}")
    
    report.append(f"{'Functions':<25} {len(orig_features['function_names']):<15} {len(trans_features['function_names']):<15} {similarities['function_preservation']:<12.3f}")
    report.append(f"{'Classes':<25} {len(orig_features['class_names']):<15} {len(trans_features['class_names']):<15} {similarities['class_preservation']:<12.3f}")
    report.append(f"{'Variables':<25} {len(set(orig_features['variable_names'])):<15} {len(set(trans_features['variable_names'])):<15} {'N/A':<12}")
    report.append(f"{'Imports':<25} {len(set(orig_features['import_statements'])):<15} {len(set(trans_features['import_statements'])):<15} {similarities['import_preservation']:<12.3f}")
    report.append(f"{'Control Structures':<25} {len(orig_features['control_structures']):<15} {len(trans_features['control_structures']):<15} {similarities['control_structure_similarity']:<12.3f}")
    report.append(f"{'AST Depth':<25} {orig_features['ast_depth']:<15} {trans_features['ast_depth']:<15} {similarities['depth_similarity']:<12.3f}")
    report.append(f"{'Node Count':<25} {orig_features['node_count']:<15} {trans_features['node_count']:<15} {'N/A':<12}")
    report.append(f"{'Complexity Score':<25} {orig_features['complexity_score']:<15} {trans_features['complexity_score']:<15} {similarities['complexity_preservation']:<12.3f}")
    
    # Detailed similarity breakdown
    report.append(f"\nSTRUCTURAL SIMILARITY BREAKDOWN:")
    report.append(f"{'Metric':<30} {'Score':<10}")
    report.append(f"{'-'*40}")
    
    for metric, score in similarities.items():
        if metric != 'structural_similarity':
            formatted_metric = metric.replace('_', ' ').title()
            report.append(f"{formatted_metric:<30} {score:<10.3f}")
    
    report.append(f"{'-'*40}")
    report.append(f"{'Overall Structural Similarity':<30} {similarities['structural_similarity']:<10.3f}")
    
    # Function and class preservation details
    if orig_features['function_names'] or trans_features['function_names']:
        report.append(f"\nFUNCTION ANALYSIS:")
        orig_funcs = set(orig_features['function_names'])
        trans_funcs = set(trans_features['function_names'])
        preserved = orig_funcs & trans_funcs
        lost = orig_funcs - trans_funcs
        added = trans_funcs - orig_funcs
        
        if preserved:
            report.append(f"  Preserved: {', '.join(preserved)}")
        if lost:
            report.append(f"  Lost: {', '.join(lost)}")
        if added:
            report.append(f"  Added: {', '.join(added)}")
    
    if orig_features['class_names'] or trans_features['class_names']:
        report.append(f"\nCLASS ANALYSIS:")
        orig_classes = set(orig_features['class_names'])
        trans_classes = set(trans_features['class_names'])
        preserved = orig_classes & trans_classes
        lost = orig_classes - trans_classes
        added = trans_classes - orig_classes
        
        if preserved:
            report.append(f"  Preserved: {', '.join(preserved)}")
        if lost:
            report.append(f"  Lost: {', '.join(lost)}")
        if added:
            report.append(f"  Added: {', '.join(added)}")
    
    return '\n'.join(report)

def analyze_compression_pipeline(code: str, sample_name: str) -> Dict[str, Any]:
    """
    Run complete compression pipeline: Original -> Minified -> SynthLang.
    
    Args:
        code: Original Python code
        sample_name: Name/identifier for the sample
        
    Returns:
        Comprehensive analysis results
    """
    results = {
        'sample_name': sample_name,
        'original_code': code,
        'stages': {},
        'pipeline_stats': {}
    }
    
    # Stage 0: Original
    original_tokens_tiktoken = estimate_tokens(code, method="tiktoken", model_type="gpt-4")
    original_tokens_simple = estimate_tokens(code, method="simple", model_type="gpt-4")
    original_size = len(code)
    
    results['stages']['original'] = {
        'code': code,
        'tokens_tiktoken': original_tokens_tiktoken,
        'tokens_simple': original_tokens_simple,
        'tokens': original_tokens_tiktoken,  # Primary for compatibility
        'size': original_size,
        'similarity_to_original': 1.0
    }
    
    # Stage 1: Minification (focus on most effective depths)
    minification_results = {}
    
    # Test all depths but emphasize aggressive compression
    for depth in range(1, 5):
        try:
            minified = minify_depth(code, depth)
            minified_tokens_tiktoken = estimate_tokens(minified, method="tiktoken", model_type="gpt-4")
            minified_tokens_simple = estimate_tokens(minified, method="simple", model_type="gpt-4")
            minified_size = len(minified)
            
            # Calculate similarity to original
            similarity = calculate_semantic_similarity(code, minified)
            
            minification_results[f'depth_{depth}'] = {
                'code': minified,
                'tokens_tiktoken': minified_tokens_tiktoken,
                'tokens_simple': minified_tokens_simple,
                'tokens': minified_tokens_tiktoken,  # Primary for compatibility
                'size': minified_size,
                'token_reduction': original_tokens_tiktoken - minified_tokens_tiktoken,
                'token_reduction_percent': ((original_tokens_tiktoken - minified_tokens_tiktoken) / original_tokens_tiktoken) * 100 if original_tokens_tiktoken > 0 else 0,
                'size_reduction': original_size - minified_size,
                'size_reduction_percent': ((original_size - minified_size) / original_size) * 100 if original_size > 0 else 0,
                'similarity_metrics': similarity
            }
        except Exception as e:
            minification_results[f'depth_{depth}'] = {
                'error': str(e),
                'code': code,  # Fallback to original
                'tokens_tiktoken': original_tokens_tiktoken,
                'tokens_simple': original_tokens_simple,
                'tokens': original_tokens_tiktoken,
                'size': original_size,
                'token_reduction': 0,
                'token_reduction_percent': 0,
                'size_reduction': 0,
                'size_reduction_percent': 0,
                'similarity_metrics': {'overall_similarity': 1.0}
            }
    
    results['stages']['minification'] = minification_results
    
    # Stage 2: SynthLang translation (from original and from best minified)
    synthlang_results = {}
    
    # SynthLang from original
    try:
        synthlang_readable = python_to_synthlang(code, compact=False)
        synthlang_compact = python_to_synthlang(code, compact=True)
        
        for mode, synthlang_code in [('readable', synthlang_readable), ('compact', synthlang_compact)]:
            synthlang_tokens_tiktoken = estimate_tokens(synthlang_code, method="tiktoken", model_type="gpt-4")
            synthlang_tokens_simple = estimate_tokens(synthlang_code, method="simple", model_type="gpt-4")
            synthlang_size = len(synthlang_code)
            
            # Calculate similarity to original
            similarity = calculate_semantic_similarity(code, synthlang_code)
            
            synthlang_results[f'from_original_{mode}'] = {
                'code': synthlang_code,
                'tokens_tiktoken': synthlang_tokens_tiktoken,
                'tokens_simple': synthlang_tokens_simple,
                'tokens': synthlang_tokens_tiktoken,  # Primary for compatibility
                'size': synthlang_size,
                'token_reduction': original_tokens_tiktoken - synthlang_tokens_tiktoken,
                'token_reduction_percent': ((original_tokens_tiktoken - synthlang_tokens_tiktoken) / original_tokens_tiktoken) * 100 if original_tokens_tiktoken > 0 else 0,
                'size_reduction': original_size - synthlang_size,
                'size_reduction_percent': ((original_size - synthlang_size) / original_size) * 100 if original_size > 0 else 0,
                'similarity_metrics': similarity
            }
    except Exception as e:
        synthlang_results['from_original_readable'] = {'error': str(e)}
        synthlang_results['from_original_compact'] = {'error': str(e)}
    
    # SynthLang from best minified (depth 4 - most aggressive)
    try:
        best_minified = minification_results['depth_4']['code']
        synthlang_from_minified_readable = python_to_synthlang(best_minified, compact=False)
        synthlang_from_minified_compact = python_to_synthlang(best_minified, compact=True)
        
        for mode, synthlang_code in [('readable', synthlang_from_minified_readable), ('compact', synthlang_from_minified_compact)]:
            synthlang_tokens_tiktoken = estimate_tokens(synthlang_code, method="tiktoken", model_type="gpt-4")
            synthlang_tokens_simple = estimate_tokens(synthlang_code, method="simple", model_type="gpt-4")
            synthlang_size = len(synthlang_code)
            
            # Calculate similarity to original
            similarity = calculate_semantic_similarity(code, synthlang_code)
            
            synthlang_results[f'from_minified_{mode}'] = {
                'code': synthlang_code,
                'tokens_tiktoken': synthlang_tokens_tiktoken,
                'tokens_simple': synthlang_tokens_simple,
                'tokens': synthlang_tokens_tiktoken,  # Primary for compatibility
                'size': synthlang_size,
                'token_reduction': original_tokens_tiktoken - synthlang_tokens_tiktoken,
                'token_reduction_percent': ((original_tokens_tiktoken - synthlang_tokens_tiktoken) / original_tokens_tiktoken) * 100 if original_tokens_tiktoken > 0 else 0,
                'size_reduction': original_size - synthlang_size,
                'size_reduction_percent': ((original_size - synthlang_size) / original_size) * 100 if original_size > 0 else 0,
                'similarity_metrics': similarity
            }
    except Exception as e:
        synthlang_results['from_minified_readable'] = {'error': str(e)}
        synthlang_results['from_minified_compact'] = {'error': str(e)}
    
    results['stages']['synthlang'] = synthlang_results
    
    # Calculate pipeline statistics
    best_compression = original_tokens_tiktoken
    best_method = 'original'
    best_similarity = 1.0
    
    # Check all compression methods
    all_methods = []
    
    # Add minification methods
    for depth in range(1, 5):
        method_data = minification_results[f'depth_{depth}']
        if 'error' not in method_data:
            all_methods.append({
                'name': f'minified_depth_{depth}',
                'tokens': method_data['tokens'],
                'similarity': method_data['similarity_metrics']['comprehensive_similarity'],
                'structural_similarity': method_data['similarity_metrics']['structural_similarity'],
                'reduction_percent': method_data['token_reduction_percent']
            })
    
    # Add SynthLang methods
    for method_name, method_data in synthlang_results.items():
        if 'error' not in method_data:
            all_methods.append({
                'name': f'synthlang_{method_name}',
                'tokens': method_data['tokens'],
                'similarity': method_data['similarity_metrics']['comprehensive_similarity'],
                'structural_similarity': method_data['similarity_metrics']['structural_similarity'],
                'reduction_percent': method_data['token_reduction_percent']
            })
    
    # Find best compression (lowest tokens) with decent similarity (>= 0.3)
    for method in all_methods:
        if method['similarity'] >= 0.3 and method['tokens'] < best_compression:
            best_compression = method['tokens']
            best_method = method['name']
            best_similarity = method['similarity']
    
    results['pipeline_stats'] = {
        'original_tokens': original_tokens_tiktoken,
        'original_tokens_tiktoken': original_tokens_tiktoken,
        'original_tokens_simple': original_tokens_simple,
        'original_size': original_size,
        'best_compression_tokens': best_compression,
        'best_compression_method': best_method,
        'best_compression_similarity': best_similarity,
        'best_reduction_percent': ((original_tokens_tiktoken - best_compression) / original_tokens_tiktoken) * 100 if original_tokens_tiktoken > 0 else 0,
        'all_methods': all_methods
    }
    
    return results

def load_samples() -> Dict[str, str]:
    """Load samples from the samples module."""
    return load_samples_from_file()

def process_all_samples(output_file: str = "compression_pipeline_results.txt") -> None:
    """
    Process all samples through the complete compression pipeline.
    
    Args:
        output_file: Output file name (relative to script directory)
    """
    # Ensure output file is in the script directory
    script_dir = Path(__file__).parent
    output_path = script_dir / output_file
    
    samples = load_samples()
    if not samples:
        print("No samples found! Make sure samples.py is imported correctly.")
        return
    
    # Sort samples by number
    sorted_samples = sorted(samples.items(), key=lambda x: int(x[0].replace('sample', '')))
    
    print(f"Processing {len(sorted_samples)} samples through compression pipeline...")
    
    all_results = []
    
    # Process each sample
    for sample_name, sample_code in sorted_samples:
        sample_num = sample_name.replace('sample', '')
        print(f"Processing Sample {sample_num}...")
        
        try:
            results = analyze_compression_pipeline(sample_code, sample_name)
            all_results.append(results)
        except Exception as e:
            print(f"Error processing Sample {sample_num}: {e}")
            all_results.append({
                'sample_name': sample_name,
                'error': str(e),
                'original_code': sample_code
            })
    
    # Write comprehensive results to file
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write("=" * 100 + "\n")
        f.write("COMPREHENSIVE COMPRESSION PIPELINE ANALYSIS\n")
        f.write("Original Python -> Minification -> SynthLang Translation\n")
        f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Total Samples: {len(all_results)}\n")
        f.write("=" * 100 + "\n\n")
        
        # Write detailed results for each sample
        for result in all_results:
            if 'error' in result:
                f.write(f"SAMPLE {result['sample_name']}\n")
                f.write("=" * 80 + "\n")
                f.write(f"ERROR: {result['error']}\n\n")
                continue
            
            sample_name = result['sample_name']
            sample_num = sample_name.replace('sample', '')
            
            f.write(f"SAMPLE {sample_num}\n")
            f.write("=" * 80 + "\n\n")
            
            # Original code
            f.write("ORIGINAL PYTHON CODE:\n")
            f.write("-" * 40 + "\n")
            f.write(result['original_code'] + "\n")
            f.write("-" * 40 + "\n")
            original_stats = result['stages']['original']
            f.write(f"Tokens: {original_stats['tokens']}, Size: {original_stats['size']} chars\n\n")
            
            # Minification results
            f.write("MINIFICATION RESULTS:\n")
            f.write("-" * 40 + "\n")
            
            for depth in range(1, 5):
                depth_key = f'depth_{depth}'
                depth_data = result['stages']['minification'][depth_key]
                
                if 'error' in depth_data:
                    f.write(f"Depth {depth}: ERROR - {depth_data['error']}\n")
                    continue
                
                f.write(f"Depth {depth} (Tokens: {depth_data['tokens']}, "
                       f"Reduction: {depth_data['token_reduction_percent']:.1f}%, "
                       f"Similarity: {depth_data['similarity_metrics']['comprehensive_similarity']:.3f}, "
                       f"Structural: {depth_data['similarity_metrics']['structural_similarity']:.3f}):\n")
                f.write(depth_data['code'] + "\n\n")
            
            # SynthLang results
            f.write("SYNTHLANG TRANSLATION RESULTS:\n")
            f.write("-" * 40 + "\n")
            
            synthlang_data = result['stages']['synthlang']
            for method_name, method_data in synthlang_data.items():
                if 'error' in method_data:
                    f.write(f"{method_name}: ERROR - {method_data['error']}\n")
                    continue
                
                f.write(f"{method_name} (Tokens: {method_data['tokens']}, "
                       f"Reduction: {method_data['token_reduction_percent']:.1f}%, "
                       f"Similarity: {method_data['similarity_metrics']['comprehensive_similarity']:.3f}, "
                       f"Structural: {method_data['similarity_metrics']['structural_similarity']:.3f}):\n")
                f.write(method_data['code'] + "\n\n")
            
            # Pipeline transformation chain
            f.write("PIPELINE TRANSFORMATION CHAIN:\n")
            f.write("-" * 40 + "\n")
            f.write("Complete transformation pipeline showing the step-by-step code evolution:\n\n")
            
            # Get pipeline stats first
            pipeline_stats = result['pipeline_stats']
            
            # Original code
            f.write("1. ORIGINAL:\n")
            f.write(f"   Tokens: {result['stages']['original']['tokens']}\n")
            f.write(f"   Code: {result['original_code'][:100]}{'...' if len(result['original_code']) > 100 else ''}\n\n")
            
            # Best minification
            best_minified = None
            best_minified_stage = None
            for depth in range(1, 5):
                depth_key = f'depth_{depth}'
                if depth_key in result['stages']['minification'] and 'error' not in result['stages']['minification'][depth_key]:
                    if best_minified is None or result['stages']['minification'][depth_key]['tokens'] < best_minified['tokens']:
                        best_minified = result['stages']['minification'][depth_key]
                        best_minified_stage = f'Minified (Depth {depth})'
            
            if best_minified:
                f.write(f"2. {best_minified_stage.upper()}:\n")
                f.write(f"   Tokens: {best_minified['tokens']} (reduced by {best_minified['token_reduction_percent']:.1f}%)\n")
                f.write(f"   Code: {best_minified['code'][:100]}{'...' if len(best_minified['code']) > 100 else ''}\n\n")
            
            # Best SynthLang translation
            best_synthlang = None
            best_synthlang_method = None
            for method_name, method_data in result['stages']['synthlang'].items():
                if 'error' not in method_data:
                    if best_synthlang is None or method_data['tokens'] < best_synthlang['tokens']:
                        best_synthlang = method_data
                        best_synthlang_method = method_name
            
            if best_synthlang:
                f.write(f"3. SYNTHLANG ({best_synthlang_method.replace('_', ' ').upper()}):\n")
                f.write(f"   Tokens: {best_synthlang['tokens']} (reduced by {best_synthlang['token_reduction_percent']:.1f}%)\n")
                f.write(f"   Code: {best_synthlang['code'][:100]}{'...' if len(best_synthlang['code']) > 100 else ''}\n\n")
            
            f.write(f"FINAL RESULT: {result['stages']['original']['tokens']} → {pipeline_stats['best_compression_tokens']} tokens "
                   f"({pipeline_stats['best_reduction_percent']:.1f}% total reduction)\n\n")

            # Pipeline summary
            f.write("PIPELINE SUMMARY:\n")
            f.write("-" * 40 + "\n")
            f.write(f"Original: {pipeline_stats['original_tokens']} tokens\n")
            f.write(f"Best compression: {pipeline_stats['best_compression_tokens']} tokens "
                   f"({pipeline_stats['best_reduction_percent']:.1f}% reduction)\n")
            f.write(f"Best method: {pipeline_stats['best_compression_method']}\n")
            f.write(f"Semantic similarity: {pipeline_stats['best_compression_similarity']:.3f}\n\n")
            
            f.write("=" * 100 + "\n\n")
        
        # Write overall statistics
        f.write("OVERALL PIPELINE STATISTICS\n")
        f.write("=" * 100 + "\n\n")
        
        successful_results = [r for r in all_results if 'error' not in r]
        
        if successful_results:
            total_original_tokens = sum(r['pipeline_stats']['original_tokens'] for r in successful_results)
            total_best_compressed_tokens = sum(r['pipeline_stats']['best_compression_tokens'] for r in successful_results)
            
            overall_reduction = ((total_original_tokens - total_best_compressed_tokens) / total_original_tokens) * 100
            average_similarity = sum(r['pipeline_stats']['best_compression_similarity'] for r in successful_results) / len(successful_results)
            
            f.write(f"Samples processed: {len(successful_results)}\n")
            f.write(f"Total original tokens: {total_original_tokens:,}\n")
            f.write(f"Total compressed tokens: {total_best_compressed_tokens:,}\n")
            f.write(f"Overall compression: {overall_reduction:.1f}%\n")
            f.write(f"Average semantic similarity: {average_similarity:.3f}\n\n")
            
            # Method effectiveness analysis
            method_performance = {}
            for result in successful_results:
                for method in result['pipeline_stats']['all_methods']:
                    method_name = method['name']
                    if method_name not in method_performance:
                        method_performance[method_name] = {
                            'total_reduction': 0,
                            'total_similarity': 0,
                            'count': 0
                        }
                    
                    method_performance[method_name]['total_reduction'] += method['reduction_percent']
                    method_performance[method_name]['total_similarity'] += method['similarity']
                    method_performance[method_name]['count'] += 1
            
            f.write("METHOD EFFECTIVENESS ANALYSIS:\n")
            f.write("-" * 60 + "\n")
            f.write(f"{'Method':<30} {'Avg Reduction':<15} {'Avg Similarity':<15} {'Samples':<10}\n")
            f.write("-" * 60 + "\n")
            
            for method_name, stats in sorted(method_performance.items()):
                avg_reduction = stats['total_reduction'] / stats['count']
                avg_similarity = stats['total_similarity'] / stats['count']
                f.write(f"{method_name:<30} {avg_reduction:>10.1f}% {avg_similarity:>12.3f} {stats['count']:>8}\n")
    
    print(f"\nCompression pipeline analysis complete!")
    print(f"Results saved to: {output_path}")
    
    # Quick summary
    if successful_results:
        print(f"\nQuick Summary:")
        print(f"- {len(successful_results)} samples processed successfully")
        print(f"- Overall compression: {overall_reduction:.1f}%")
        print(f"- Average semantic similarity: {average_similarity:.3f}")
        
        # Show top 3 most effective methods
        method_scores = []
        for method_name, stats in method_performance.items():
            avg_reduction = stats['total_reduction'] / stats['count']
            avg_similarity = stats['total_similarity'] / stats['count']
            # Score balances compression and similarity (similarity weight = 0.3)
            score = avg_reduction + (avg_similarity * 30)
            method_scores.append((method_name, score, avg_reduction, avg_similarity))
        
        method_scores.sort(key=lambda x: x[1], reverse=True)
        print(f"\nTop 3 Most Effective Methods:")
        for i, (method, score, reduction, similarity) in enumerate(method_scores[:3]):
            print(f"{i+1}. {method}: {reduction:.1f}% reduction, {similarity:.3f} similarity")

def main():
    """Main function to run the compression pipeline analysis."""
    print("🔧 Compression Pipeline Analyzer with Enhanced Structural Similarity")
    print("Chaining: Python -> Minification -> SynthLang Translation")
    print("=" * 80)
    
    # Load and display sample count
    samples = load_samples()
    print(f"Found {len(samples)} samples to process")
    
    if not samples:
        print("❌ No samples found. Please check that samples.py is correctly imported.")
        return
    
    # Process all samples through the pipeline
    process_all_samples("compression_pipeline_results.txt")
    
    # Create structural analysis report for a few interesting samples
    print("\n📊 Creating detailed structural analysis for top samples...")
    create_structural_analysis_file()
    
    print("\n🎉 Done! Check the output files for comprehensive analysis:")
    print("  - compression_pipeline_results.txt (full pipeline analysis)")
    print("  - structural_analysis_report.txt (detailed structural similarity)")

def create_structural_analysis_file():
    """Create a separate file with detailed structural analysis for selected samples."""
    script_dir = Path(__file__).parent
    output_path = script_dir / "structural_analysis_report.txt"
    
    samples = load_samples()
    if not samples:
        return
    
    # Select a few representative samples for detailed analysis
    sample_names = ['sample1', 'sample3', 'sample7', 'sample10', 'sample23']
    selected_samples = {name: code for name, code in samples.items() if name in sample_names}
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write("=" * 80 + "\n")
        f.write("DETAILED STRUCTURAL SIMILARITY ANALYSIS\n")
        f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write("=" * 80 + "\n")
        
        for sample_name, sample_code in selected_samples.items():
            sample_num = sample_name.replace('sample', '')
            f.write(f"\n\nSAMPLE {sample_num} STRUCTURAL ANALYSIS")
            f.write("=" * 60 + "\n")
            
            # Analyze different transformation methods
            try:
                # Original vs Minified (depth 4)
                minified = minify_depth(sample_code, 4)
                report = create_structural_analysis_report(sample_name, sample_code, minified, "Minified (Depth 4)")
                f.write(report + "\n")
                
                # Original vs SynthLang Compact
                synthlang_compact = python_to_synthlang(sample_code, compact=True)
                report = create_structural_analysis_report(sample_name, sample_code, synthlang_compact, "SynthLang Compact")
                f.write(report + "\n")
                
                # Minified vs SynthLang (chained)
                synthlang_from_minified = python_to_synthlang(minified, compact=True)
                report = create_structural_analysis_report(sample_name, sample_code, synthlang_from_minified, "Chained (Minified → SynthLang)")
                f.write(report + "\n")
                
            except Exception as e:
                f.write(f"\nError analyzing {sample_name}: {str(e)}\n")
    
    print(f"✅ Structural analysis saved to: {output_path}")

if __name__ == "__main__":
    main()
