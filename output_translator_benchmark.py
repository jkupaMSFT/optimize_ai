#!/usr/bin/env python3
"""
Output Translator Benchmark Test
Tests only the CAI → Python reconstruction functionality.
"""

import sys
import os
import time
import json
from pathlib import Path
from typing import Dict, Any

# Add current directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def create_test_cai_samples() -> Dict[str, str]:
    """Create various CAI test samples."""
    return {
        "simple_function": """F[greet(name) → {
    print(f"Hello, {name}!")
    return f"Greeted {name}"
}]""",
        
        "class_with_methods": """C[Person → {
    def __init__(self, name, age):
        self.name = name
        self.age = age
    
    def introduce(self):
        return f"Hi, I'm {self.name} and I'm {self.age} years old"
    
    def celebrate_birthday(self):
        self.age += 1
        print(f"Happy birthday! Now {self.age}")
}]""",
        
        "complex_function": """F[process_data(data, options={}) → {
    if not data:
        raise ValueError("Data cannot be empty")
    
    results = []
    for item in data:
        if options.get('filter', True):
            processed = transform_item(item)
            results.append(processed)
    
    return {"processed": results, "count": len(results)}
}]""",
        
        "multiple_functions": """F[add(a, b) → {
    return a + b
}]

F[multiply(x, y) → {
    result = x * y
    print(f"{x} * {y} = {result}")
    return result
}]

F[calculate(numbers) → {
    total = sum(numbers)
    average = total / len(numbers) if numbers else 0
    return {"sum": total, "average": average, "count": len(numbers)}
}]""",
        
        "exception_handling": """F[safe_divide(a, b) → {
    try:
        result = a / b
        return {"success": True, "result": result}
    except ZeroDivisionError:
        return {"success": False, "error": "Division by zero"}
    except Exception as e:
        return {"success": False, "error": str(e)}
}]"""
    }

def test_output_translator(cai_code: str, test_name: str, original_python: str = None) -> Dict[str, Any]:
    """Test the output translator with specific CAI code."""
    print(f"\n🔄 Testing {test_name}...")
    
    try:
        from output_translator.core.translator import CAIToPythonTranslator
        from core.session_manager import SecureSessionManager
        
        start_time = time.time()
        
        session_manager = SecureSessionManager()
        translator = CAIToPythonTranslator(session_manager=session_manager)
        
        session_id = session_manager.create_session(
            file_path=Path(f"{test_name}.py"),
            agent="benchmark",
            compressed_content=cai_code,
            metadata={'test_mode': True, 'test_name': test_name}
        )
        
        try:
            result = translator.translate(
                session_id=session_id,
                cai_code=cai_code,
                original_py=original_python,
                level="full"
            )
            
            translation_time = (time.time() - start_time) * 1000
            
            if result.success:
                print(f"✅ {test_name}: SUCCESS")
                print(f"   Generated {len(result.python_code)} chars in {translation_time:.1f}ms")
                print(f"   Similarity: {result.similarity_score:.1%}")
                
                # Show a preview of the generated code
                lines = result.python_code.split('\n')
                print(f"   Preview (first 5 lines):")
                for i, line in enumerate(lines[:5], 1):
                    print(f"     {i}: {line}")
                if len(lines) > 5:
                    print(f"     ... ({len(lines) - 5} more lines)")
                
                return {
                    'success': True,
                    'test_name': test_name,
                    'generated_code': result.python_code,
                    'size': len(result.python_code),
                    'similarity_score': result.similarity_score,
                    'translation_time_ms': translation_time,
                    'errors': result.errors,
                    'warnings': result.warnings
                }
            else:
                print(f"❌ {test_name}: FAILED")
                for error in result.errors:
                    print(f"   Error: {error}")
                
                if result.python_code:
                    print(f"   Partial code generated:")
                    lines = result.python_code.split('\n')
                    for i, line in enumerate(lines[:3], 1):
                        print(f"     {i}: {line}")
                
                return {
                    'success': False,
                    'test_name': test_name,
                    'errors': result.errors,
                    'warnings': result.warnings,
                    'partial_code': result.python_code
                }
            
        finally:
            session_manager.delete_session(session_id)
        
    except Exception as e:
        print(f"❌ {test_name}: EXCEPTION - {e}")
        import traceback
        traceback.print_exc()
        return {
            'success': False,
            'test_name': test_name,
            'exception': str(e)
        }

def run_syntax_validation(python_code: str, test_name: str) -> Dict[str, Any]:
    """Validate that the generated Python code has correct syntax."""
    try:
        import ast
        ast.parse(python_code)
        return {
            'valid_syntax': True,
            'test_name': test_name
        }
    except SyntaxError as e:
        return {
            'valid_syntax': False,
            'test_name': test_name,
            'syntax_error': str(e),
            'line': getattr(e, 'lineno', None),
            'offset': getattr(e, 'offset', None)
        }
    except Exception as e:
        return {
            'valid_syntax': False,
            'test_name': test_name,
            'error': str(e)
        }

def main():
    """Run comprehensive output translator benchmark."""
    print("🚀 Output Translator Benchmark Test")
    print("="*60)
    
    # Get test samples
    test_samples = create_test_cai_samples()
    
    # Run tests
    results = []
    successful_tests = 0
    total_tests = len(test_samples)
    
    for test_name, cai_code in test_samples.items():
        result = test_output_translator(cai_code, test_name)
        results.append(result)
        
        if result['success']:
            successful_tests += 1
        
        # Validate syntax of successful translations
        if result['success'] and 'generated_code' in result:
            syntax_result = run_syntax_validation(result['generated_code'], test_name)
            result['syntax_validation'] = syntax_result
            
            if syntax_result['valid_syntax']:
                print(f"   ✅ Syntax validation: PASSED")
            else:
                print(f"   ❌ Syntax validation: FAILED - {syntax_result.get('syntax_error', 'Unknown error')}")
    
    # Summary
    print(f"\n{'='*60}")
    print("📊 BENCHMARK SUMMARY")
    print(f"{'='*60}")
    
    print(f"📈 Overall Results:")
    print(f"   Tests Passed: {successful_tests}/{total_tests} ({successful_tests/total_tests*100:.1f}%)")
    
    if successful_tests > 0:
        # Calculate average metrics for successful tests
        successful_results = [r for r in results if r['success']]
        avg_time = sum(r['translation_time_ms'] for r in successful_results) / len(successful_results)
        avg_similarity = sum(r['similarity_score'] for r in successful_results) / len(successful_results)
        avg_size = sum(r['size'] for r in successful_results) / len(successful_results)
        
        print(f"   Average translation time: {avg_time:.1f}ms")
        print(f"   Average similarity score: {avg_similarity:.1%}")
        print(f"   Average output size: {avg_size:.0f} characters")
    
    print(f"\n🔍 Individual Test Results:")
    for result in results:
        status = "✅ PASS" if result['success'] else "❌ FAIL"
        print(f"   {result['test_name']}: {status}")
        
        if result['success']:
            syntax_status = "✅" if result.get('syntax_validation', {}).get('valid_syntax', False) else "❌"
            print(f"     - Translation: ✅, Syntax: {syntax_status}")
        else:
            if 'errors' in result and result['errors']:
                print(f"     - Errors: {len(result['errors'])}")
    
    # Save detailed results
    output_file = Path("output_translator_benchmark_results.json")
    with open(output_file, 'w') as f:
        json.dump(results, f, indent=2, default=str)
    
    print(f"\n💾 Detailed results saved to: {output_file}")
    
    if successful_tests == total_tests:
        print(f"\n🎉 ALL TESTS PASSED! Output translator is working perfectly!")
        print(f"🚀 Ready for production use!")
    elif successful_tests > 0:
        print(f"\n⚠️ {total_tests - successful_tests} tests failed, but output translator is partially functional.")
        print(f"🔧 Consider investigating failed test cases.")
    else:
        print(f"\n❌ ALL TESTS FAILED! Output translator needs significant fixes.")

if __name__ == "__main__":
    main()
