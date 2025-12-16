#!/usr/bin/env python3
"""
Test script to validate Command Palette integration functionality
"""

import os
import sys
import json
import tempfile
from pathlib import Path

def test_command_palette_integration():
    """Test the Command Palette integration"""
    print("🧪 Testing Command Palette Integration...")
    
    # Test 1: Check if commands.ts was created
    commands_file = Path(__file__).parent / "src" / "commands.ts"
    if commands_file.exists():
        print("✅ commands.ts file created successfully")
        
        # Read the file content
        with open(commands_file, 'r') as f:
            content = f.read()
            
        # Check for required classes and methods
        required_elements = [
            "class CommandManager",
            "registerCommands",
            "compressCurrentFile",
            "showCompressionPreview",
            "getPreviewHtml",
            "optimizeai.compress",
            "optimizeai.preview"
        ]
        
        missing_elements = []
        for element in required_elements:
            if element not in content:
                missing_elements.append(element)
        
        if missing_elements:
            print(f"❌ Missing elements in commands.ts: {missing_elements}")
            return False
        else:
            print("✅ All required elements found in commands.ts")
    else:
        print("❌ commands.ts file not found")
        return False
    
    # Test 2: Check if package.json includes new commands
    package_file = Path(__file__).parent / "package.json"
    if package_file.exists():
        with open(package_file, 'r') as f:
            package_data = json.load(f)
        
        # Check commands
        commands = package_data.get('contributes', {}).get('commands', [])
        command_ids = [cmd['command'] for cmd in commands]
        
        required_commands = [
            'optimizeai.compress',
            'optimizeai.preview',
            'optimizeai.showStats',
            'optimizeai.copyCompressed',
            'optimizeai.toggleAutoCompress',
            'optimizeai.clearCache'
        ]
        
        missing_commands = [cmd for cmd in required_commands if cmd not in command_ids]
        
        if missing_commands:
            print(f"❌ Missing commands in package.json: {missing_commands}")
            return False
        else:
            print("✅ All required commands found in package.json")
    else:
        print("❌ package.json file not found")
        return False
    
    # Test 3: Check if extension.ts imports CommandManager
    extension_file = Path(__file__).parent / "src" / "extension.ts"
    if extension_file.exists():
        with open(extension_file, 'r') as f:
            content = f.read()
        
        if "CommandManager" in content and "commandManager.registerCommands" in content:
            print("✅ Extension.ts properly integrates CommandManager")
        else:
            print("❌ Extension.ts missing CommandManager integration")
            return False
    else:
        print("❌ extension.ts file not found")
        return False
    
    print("🎉 All Command Palette integration tests passed!")
    return True

def test_compilation():
    """Test if the code compiles without errors"""
    print("\n🔨 Testing TypeScript compilation...")
    
    # Change to the vscode directory
    vscode_dir = Path(__file__).parent
    os.chdir(vscode_dir)
    
    # Run npm compile
    result = os.system("npm run compile")
    
    if result == 0:
        print("✅ TypeScript compilation successful")
        return True
    else:
        print("❌ TypeScript compilation failed")
        return False

def main():
    """Main test function"""
    print("🚀 Starting Command Palette Integration Tests...\n")
    
    # Test 1: Command Palette Integration
    test1_passed = test_command_palette_integration()
    
    # Test 2: Compilation
    test2_passed = test_compilation()
    
    # Summary
    print("\n" + "="*50)
    print("📊 TEST SUMMARY")
    print("="*50)
    print(f"Command Palette Integration: {'✅ PASS' if test1_passed else '❌ FAIL'}")
    print(f"TypeScript Compilation: {'✅ PASS' if test2_passed else '❌ FAIL'}")
    
    if test1_passed and test2_passed:
        print("\n🎉 ALL TESTS PASSED! Command Palette integration is working correctly.")
        return 0
    else:
        print("\n❌ SOME TESTS FAILED. Please check the issues above.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
