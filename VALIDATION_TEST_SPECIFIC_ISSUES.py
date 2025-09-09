#!/usr/bin/env python3
"""
Specific CAI3 Translation Issue Validation
==========================================

This script runs focused tests on the specific issues identified in the comprehensive analysis.
"""

import sys
import os
import ast
import re
from pathlib import Path

# Add the project root to the path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from input_optimizer.engine.cai3_ast_translator import CAI3BodyParser
from input_optimizer.engine.hash_resolver import HashResolver

def test_pool_resolution_contexts():
    """Test the specific pool resolution context issues."""
    print("🔍 Testing Pool Resolution Context Issues")
    print("-" * 50)
    
    parser = CAI3BodyParser()
    parser.pools = {
        'p2': 'score',
        'p4': 'severity', 
        'p5': 'critical',
        'p0': 'metadata'
    }
    
    test_cases = [
        # Dictionary key contexts - should add quotes
        ('result[p2]', 'result["score"]', 'Dictionary key context'),
        ('counts[p5]', 'counts["critical"]', 'Dictionary key context'),
        ('metadata[p4]', 'metadata["severity"]', 'Dictionary key context'),
        
        # Standalone contexts - should quote for string literals
        ('p2', '"score"', 'Standalone string literal'),
        ('return p0', 'return "metadata"', 'Return statement'),
        
        # Attribute access - no quotes needed
        ('obj.p2', 'obj.score', 'Attribute access'),
        ('self.p0', 'self.metadata', 'Self attribute access'),
        
        # Complex expressions
        ('data[p0][p4]', 'data["metadata"]["severity"]', 'Nested dictionary access'),
        ('func(p2, p5)', 'func("score", "critical")', 'Function arguments'),
    ]
    
    issues = []
    for input_expr, expected, description in test_cases:
        result = parser.resolve_pool_references(input_expr)
        status = "✅" if result == expected else "❌"
        print(f"  {status} {description}")
        print(f"      Input: {input_expr}")
        print(f"      Expected: {expected}")
        print(f"      Got: {result}")
        
        if result != expected:
            issues.append({
                'input': input_expr,
                'expected': expected,
                'actual': result,
                'description': description
            })
        print()
    
    return issues

def test_conditional_parsing():
    """Test CAI3 conditional expression parsing."""
    print("🔍 Testing CAI3 Conditional Expression Parsing")
    print("-" * 50)
    
    parser = CAI3BodyParser()
    parser.pools = {'p2': 'score'}
    
    # Actual failing content from logs
    conditional_body = """(hash_ca00 not in results):{print("Analysis complete");print(f"Processed {len(files)} files");print(f"Average score: {results.get('hash_8b25', 0)}");output=create_output(analyzer)}else:{print("Analysis failed")}"""
    
    print(f"Testing conditional body parsing...")
    print(f"Input length: {len(conditional_body)} chars")
    print(f"Input preview: {conditional_body[:100]}...")
    
    try:
        statements = parser.parse_body(conditional_body, "test_conditional")
        print(f"✅ Parsed {len(statements)} statements")
        
        # Check if any statements are actual if-statements vs parse errors
        if_statements = [s for s in statements if isinstance(s, ast.If)]
        error_statements = [s for s in statements if isinstance(s, ast.Expr) and 
                          hasattr(s.value, 's') and 'Parse error' in s.value.s]
        
        print(f"  If statements: {len(if_statements)}")
        print(f"  Error statements: {len(error_statements)}")
        
        if len(if_statements) == 0 and len(error_statements) > 0:
            print("  ❌ ISSUE: Conditional parsing failed - created error comments instead of if-statements")
            return ["Conditional parsing creates error comments instead of if-statements"]
        elif len(if_statements) > 0:
            print("  ✅ Successfully created if-statements")
            return []
            
    except Exception as e:
        print(f"  ❌ CRITICAL: Conditional parsing threw exception: {e}")
        return [f"Conditional parsing exception: {e}"]
    
    return []

def test_hash_resolution_integration():
    """Test hash resolution integration in the pipeline."""
    print("🔍 Testing Hash Resolution Integration")
    print("-" * 50)
    
    # Test mappings from logs
    test_mappings = {
        'hash_ca00': 'error',
        'hash_7b30': 'Path', 
        'hash_0a21': 'dataclasses',
        'hash_3f37': 'functools',
        'hash_8b25': 'average_score'
    }
    
    resolver = HashResolver(test_mappings)
    parser = CAI3BodyParser()
    
    # Test if hash resolution is applied during body parsing
    body_with_hashes = "results.get('hash_8b25', 0);(hash_ca00 not in results)"
    
    print(f"Testing hash resolution in body parsing...")
    print(f"Input: {body_with_hashes}")
    
    # Test hash resolver directly
    resolved_by_resolver = resolver.resolve_in_python_code(body_with_hashes)
    print(f"Hash resolver output: {resolved_by_resolver}")
    
    # Test if body parser applies hash resolution  
    try:
        statements = parser.parse_body(body_with_hashes, "test_hash")
        reconstructed = []
        for stmt in statements:
            try:
                reconstructed.append(ast.unparse(stmt))
            except:
                reconstructed.append("# Failed to unparse")
        
        body_output = '; '.join(reconstructed)
        print(f"Body parser output: {body_output}")
        
        # Check if hashes are still present
        if 'hash_' in body_output:
            print("  ❌ ISSUE: Hash references still present in body parser output")  
            return ["Hash resolution not applied in body parsing pipeline"]
        else:
            print("  ✅ Hash references resolved in body parsing")
            return []
            
    except Exception as e:
        print(f"  ❌ CRITICAL: Body parsing with hashes failed: {e}")
        return [f"Body parsing with hashes exception: {e}"]

def test_import_statement_parsing():
    """Test CAI3 import statement parsing."""
    print("🔍 Testing CAI3 Import Statement Parsing")
    print("-" * 50)
    
    parser = CAI3BodyParser()
    
    # Import statements from logs
    import_statements = ["@hash_0a21", "@hash_3f37"]
    
    issues = []
    for import_stmt in import_statements:
        print(f"Testing import: {import_stmt}")
        
        try:
            statements = parser.parse_body(import_stmt, "test_import")
            
            # Check if we get actual import statements
            import_nodes = [s for s in statements if isinstance(s, (ast.Import, ast.ImportFrom))]
            if len(import_nodes) == 0:
                print(f"  ❌ No import nodes generated for {import_stmt}")
                issues.append(f"Import statement {import_stmt} not generating import nodes")
            else:
                print(f"  ✅ Generated {len(import_nodes)} import nodes")
                
        except Exception as e:
            print(f"  ❌ Import parsing failed: {e}")
            issues.append(f"Import parsing exception for {import_stmt}: {e}")
    
    return issues

def main():
    """Run all focused validation tests."""
    print("🚀 CAI3 Translation Issue Validation")
    print("=" * 60)
    
    all_issues = []
    
    # Test each identified issue area
    pool_issues = test_pool_resolution_contexts()
    all_issues.extend(pool_issues)
    
    conditional_issues = test_conditional_parsing()
    all_issues.extend(conditional_issues)
    
    hash_issues = test_hash_resolution_integration()
    all_issues.extend(hash_issues)
    
    import_issues = test_import_statement_parsing()
    all_issues.extend(import_issues)
    
    # Generate final summary
    print("\n" + "=" * 60)
    print("📊 VALIDATION SUMMARY")
    print("=" * 60)
    
    print(f"Total Issues Found: {len(all_issues)}")
    
    if all_issues:
        print("\n🔴 CRITICAL ISSUES TO FIX:")
        for i, issue in enumerate(all_issues, 1):
            if isinstance(issue, dict):
                print(f"{i}. Pool Resolution Context Issue:")
                print(f"   Input: {issue['input']}")
                print(f"   Expected: {issue['expected']}")
                print(f"   Actual: {issue['actual']}")
                print(f"   Context: {issue['description']}")
            else:
                print(f"{i}. {issue}")
    else:
        print("✅ All validation tests passed!")
    
    print("\n💡 DEBUGGING INSTRUCTIONS FOR LLM:")
    print("The above tests identify the exact failure points in the CAI3 translation pipeline.")
    print("Focus fixes on:")
    print("1. Pool reference context detection in resolve_pool_references()")
    print("2. Conditional expression parsing in parse_body()")
    print("3. Hash resolution integration in the parsing pipeline")
    print("4. Import statement translation (@hash_xxx -> import statements)")

if __name__ == "__main__":
    main()
