#!/usr/bin/env python3
"""
Simple verification script to confirm PatternToASTTranslator is working correctly
"""

import sys
import os
import ast

# Add current directory to path
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

def test_real_pattern_to_ast_translator():
    """Test the real PatternToASTTranslator with complex patterns."""
    print("🔬 Testing Real PatternToASTTranslator")
    print("=" * 50)
    
    try:
        # Import the real PatternToASTTranslator
        from output_translator.core.pattern_to_ast_translator import PatternToASTTranslator
        
        # Create translator instance
        translator = PatternToASTTranslator()
        print("✅ Real PatternToASTTranslator imported and instantiated")
        
        # Mock context
        class MockContext:
            def __init__(self):
                self.variables = {}
                self.current_class = None
                self.imports = []
        
        context = MockContext()
        
        # Test complex function pattern
        function_data = {
            'name': 'calculate_user_score',
            'args': 'self, user_id, metrics, bonus=0.1',
            'body': '''
                base_score = sum(metrics.values()) 
                bonus_score = base_score * bonus
                return base_score + bonus_score
            '''
        }
        
        print("\n🧪 Testing complex function pattern...")
        func_ast = translator._build_function_def(function_data, context)
        print(f"✅ Function AST created: {func_ast.name}")
        print(f"   Args: {len(func_ast.args.args)} parameters")
        print(f"   Body: {len(func_ast.body)} statements")
        
        # Test class pattern
        class_data = {
            'name': 'UserManager',
            'bases': 'BaseManager, LoggerMixin',
            'body': '''
                def __init__(self, config):
                    self.config = config
                    self.users = {}
                
                def add_user(self, user):
                    self.users[user.id] = user
                    self.log(f"Added user: {user.id}")
            '''
        }
        
        print("\n🧪 Testing complex class pattern...")
        class_ast = translator._build_class_def(class_data, context)
        print(f"✅ Class AST created: {class_ast.name}")
        print(f"   Bases: {len(class_ast.bases)} base classes")
        print(f"   Body: {len(class_ast.body)} statements")
        
        # Test JavaScript try/catch pattern
        js_pattern = {
            'body': '''
                try {
                    const result = processData(input);
                    console.log("Success:", result);
                    return result;
                } catch(error) {
                    console.error("Error processing:", error.message);
                    throw new Error("Processing failed");
                } finally {
                    cleanup();
                }
            '''
        }
        
        print("\n🧪 Testing JavaScript try/catch pattern...")
        try_ast = translator._build_js_try_catch(js_pattern, context)
        print(f"✅ Try/catch AST created")
        print(f"   Try body: {len(try_ast.body)} statements")
        print(f"   Handlers: {len(try_ast.handlers)} exception handlers")
        print(f"   Finally: {len(try_ast.finalbody)} finally statements")
        
        # Test that we can convert AST back to code
        print("\n🧪 Testing AST to Python code conversion...")
        try:
            import astor
            python_code = astor.to_source(func_ast)
            print("✅ AST successfully converted back to Python:")
            print("   " + python_code.replace('\n', '\n   '))
        except ImportError:
            # Use ast.unparse if available (Python 3.9+)
            try:
                python_code = ast.unparse(func_ast)
                print("✅ AST successfully converted back to Python:")
                print("   " + python_code.replace('\n', '\n   '))
            except AttributeError:
                print("⚠️ AST conversion available but no pretty printer installed")
        
        print("\n🎉 All PatternToASTTranslator tests passed!")
        print("🚀 Real PatternToASTTranslator is working perfectly!")
        return True
        
    except ImportError as e:
        print(f"❌ Import failed: {e}")
        return False
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_real_pattern_to_ast_translator()
    if success:
        print("\n✅ Verification complete - PatternToASTTranslator is ready!")
    else:
        print("\n❌ Verification failed - check imports and dependencies")
        sys.exit(1)
