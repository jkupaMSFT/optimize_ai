#!/usr/bin/env python3
"""
Setup verification script for the optimize_ai project.
This script verifies that all dependencies are properly installed
and the package structure is working correctly.
"""

def test_imports():
    """Test that all critical imports work."""
    print("Testing imports...")
    
    try:
        # Test FastAPI and web framework
        import fastapi
        import uvicorn
        import httpx
        print("✓ Web framework dependencies (FastAPI, uvicorn, httpx)")
        
        # Test our package structure
        from input_optimizer.engine import minify_code, python_to_sudolang, python_to_synthlang
        print("✓ Input optimizer engine imports")
        
        # Test main app
        from app import app
        print("✓ Main application imports")
        
        # Test utilities
        from utils.logger import get_logger
        from utils.compression import CompressionType
        print("✓ Utility imports")
        
        # Test specific engine components
        from input_optimizer.engine.adapter import adapt_compression
        from input_optimizer.engine.mapping import ASTMapper, SourceMap
        print("✓ Engine component imports")
        
        # Test that we can import test classes
        from input_optimizer.tests.test_adapter_integration import TestAdapterIntegration
        print("✓ Test module imports")
        
        return True
        
    except ImportError as e:
        print(f"✗ Import error: {e}")
        return False

def test_basic_functionality():
    """Test basic functionality works."""
    print("\nTesting basic functionality...")
    
    try:
        from input_optimizer.engine import minify_code, estimate_tokens
        
        # Test minification
        sample_code = """
def hello_world():
    '''This is a sample function'''
    message = "Hello, World!"
    print(message)
    return message
"""
        
        minified = minify_code(sample_code)
        original_tokens = estimate_tokens(sample_code)
        minified_tokens = estimate_tokens(minified)
        
        print(f"✓ Minification: {len(sample_code)} → {len(minified)} chars")
        print(f"✓ Token estimation: {original_tokens} → {minified_tokens} tokens")
        
        return True
        
    except Exception as e:
        print(f"✗ Functionality error: {e}")
        return False

def main():
    """Main verification routine."""
    print("=" * 60)
    print("Optimize AI - Setup Verification")
    print("=" * 60)
    
    imports_ok = test_imports()
    functionality_ok = test_basic_functionality()
    
    print("\n" + "=" * 60)
    if imports_ok and functionality_ok:
        print("🎉 All tests passed! Your setup is ready.")
        print("\nNext steps:")
        print("1. Run the API server: uvicorn app:app --reload")
        print("2. Visit http://localhost:8000/docs for API documentation")
        print("3. Run tests: python -m pytest input_optimizer/tests/")
    else:
        print("❌ Some tests failed. Please check the errors above.")
        return 1
    
    return 0

if __name__ == "__main__":
    exit(main())
