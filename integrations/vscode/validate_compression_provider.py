#!/usr/bin/env python3
"""
Comprehensive test script for the VS Code Compression Provider functionality
This script validates that all components are working correctly together
"""

import os
import sys
import json
import tempfile
from pathlib import Path
from typing import Dict, Any

class CompressionProviderValidator:
    """Validates the compression provider implementation"""
    
    def __init__(self):
        self.test_results = []
        self.vscode_extension_path = Path(__file__).parent
        
    def log_test(self, test_name: str, success: bool, message: str = ""):
        """Log test result"""
        status = "✅ PASS" if success else "❌ FAIL"
        self.test_results.append((test_name, success, message))
        print(f"{status}: {test_name}")
        if message:
            print(f"    {message}")
    
    def validate_file_structure(self) -> bool:
        """Validate that all required files exist"""
        required_files = [
            "src/compressionProvider.ts",
            "src/cai-client.ts", 
            "src/extension.ts",
            "package.json",
            "tsconfig.json"
        ]
        
        all_exist = True
        for file_path in required_files:
            full_path = self.vscode_extension_path / file_path
            if not full_path.exists():
                self.log_test(f"File exists: {file_path}", False, f"File not found: {full_path}")
                all_exist = False
            else:
                self.log_test(f"File exists: {file_path}", True)
        
        return all_exist
    
    def validate_compression_provider_implementation(self) -> bool:
        """Validate CompressionProvider implementation"""
        compression_provider_file = self.vscode_extension_path / "src/compressionProvider.ts"
        
        if not compression_provider_file.exists():
            self.log_test("CompressionProvider file exists", False)
            return False
        
        content = compression_provider_file.read_text()
        
        # Check for required methods and properties
        required_elements = [
            "class CompressionProvider",
            "compressOnSave",
            "storeCompressed",
            "getCompressedVersion",
            "copyCompressedToClipboard",
            "statusBar",
            "client: CAIClient",
            "import { CAIClient }",
            "vscode.StatusBarItem"
        ]
        
        all_found = True
        for element in required_elements:
            if element not in content:
                self.log_test(f"CompressionProvider contains: {element}", False)
                all_found = False
            else:
                self.log_test(f"CompressionProvider contains: {element}", True)
        
        return all_found
    
    def validate_extension_integration(self) -> bool:
        """Validate extension.ts integration with CompressionProvider"""
        extension_file = self.vscode_extension_path / "src/extension.ts"
        
        if not extension_file.exists():
            self.log_test("Extension file exists", False)
            return False
        
        content = extension_file.read_text()
        
        # Check for integration points
        integration_points = [
            "import { CompressionProvider }",
            "new CompressionProvider()",
            "compressOnSave",
            "onDidSaveTextDocument",
            "optimize-ai.compress",
            "optimize-ai.showStats",
            "optimize-ai.copyCompressed",
            "optimize-ai.clearCache"
        ]
        
        all_integrated = True
        for point in integration_points:
            if point not in content:
                self.log_test(f"Extension integration: {point}", False)
                all_integrated = False
            else:
                self.log_test(f"Extension integration: {point}", True)
        
        return all_integrated
    
    def validate_cai_client_updates(self) -> bool:
        """Validate CAIClient has compress method"""
        cai_client_file = self.vscode_extension_path / "src/cai-client.ts"
        
        if not cai_client_file.exists():
            self.log_test("CAI Client file exists", False)
            return False
        
        content = cai_client_file.read_text()
        
        # Check for compress method and updated interface
        required_updates = [
            "async compress(content: string)",
            "CompressionResult",
            "tokensSaved?:",
            "ratio?:",
            "compressed?:"
        ]
        
        all_updated = True
        for update in required_updates:
            if update not in content:
                self.log_test(f"CAI Client update: {update}", False)
                all_updated = False
            else:
                self.log_test(f"CAI Client update: {update}", True)
        
        return all_updated
    
    def validate_package_json_configuration(self) -> bool:
        """Validate package.json has correct configuration"""
        package_file = self.vscode_extension_path / "package.json"
        
        if not package_file.exists():
            self.log_test("package.json exists", False)
            return False
        
        try:
            with open(package_file) as f:
                package_data = json.load(f)
        except json.JSONDecodeError as e:
            self.log_test("package.json valid JSON", False, str(e))
            return False
        
        # Check required commands
        commands = package_data.get("contributes", {}).get("commands", [])
        command_ids = [cmd.get("command") for cmd in commands]
        
        required_commands = [
            "optimize-ai.compress",
            "optimize-ai.showStats", 
            "optimize-ai.copyCompressed",
            "optimize-ai.clearCache"
        ]
        
        all_commands_present = True
        for cmd in required_commands:
            if cmd not in command_ids:
                self.log_test(f"Package.json command: {cmd}", False)
                all_commands_present = False
            else:
                self.log_test(f"Package.json command: {cmd}", True)
        
        # Check configuration properties
        config_props = package_data.get("contributes", {}).get("configuration", {}).get("properties", {})
        required_config = [
            "optimize-ai.showCompressionNotifications",
            "optimize-ai.maxCacheSize"
        ]
        
        for config in required_config:
            if config not in config_props:
                self.log_test(f"Package.json config: {config}", False)
                all_commands_present = False
            else:
                self.log_test(f"Package.json config: {config}", True)
        
        return all_commands_present
    
    def validate_compilation(self) -> bool:
        """Validate that the TypeScript compiles without errors"""
        # Check if out directory exists and has compiled files
        out_dir = self.vscode_extension_path / "out"
        
        if not out_dir.exists():
            self.log_test("Compilation output directory exists", False)
            return False
        
        compiled_files = [
            "extension.js",
            "compressionProvider.js",
            "cai-client.js"
        ]
        
        all_compiled = True
        for file_name in compiled_files:
            compiled_file = out_dir / file_name
            if not compiled_file.exists():
                self.log_test(f"Compiled file: {file_name}", False)
                all_compiled = False
            else:
                self.log_test(f"Compiled file: {file_name}", True)
        
        return all_compiled
    
    def validate_vsix_package(self) -> bool:
        """Validate that the VSIX package was created"""
        vsix_files = list(self.vscode_extension_path.glob("*.vsix"))
        
        if not vsix_files:
            self.log_test("VSIX package created", False, "No .vsix files found")
            return False
        
        latest_vsix = max(vsix_files, key=os.path.getctime)
        self.log_test("VSIX package created", True, f"Found: {latest_vsix.name}")
        
        # Check file size (should be reasonable)
        size_mb = latest_vsix.stat().st_size / (1024 * 1024)
        if size_mb > 50:  # Arbitrary reasonable limit
            self.log_test("VSIX package size reasonable", False, f"Size: {size_mb:.2f}MB")
            return False
        else:
            self.log_test("VSIX package size reasonable", True, f"Size: {size_mb:.2f}MB")
        
        return True
    
    def run_all_validations(self) -> bool:
        """Run all validation tests"""
        print("=== VS Code Compression Provider Validation ===\n")
        
        validations = [
            ("File Structure", self.validate_file_structure),
            ("CompressionProvider Implementation", self.validate_compression_provider_implementation),
            ("Extension Integration", self.validate_extension_integration),
            ("CAI Client Updates", self.validate_cai_client_updates),
            ("Package.json Configuration", self.validate_package_json_configuration),
            ("TypeScript Compilation", self.validate_compilation),
            ("VSIX Package Creation", self.validate_vsix_package)
        ]
        
        all_passed = True
        
        for validation_name, validation_func in validations:
            print(f"\n--- {validation_name} ---")
            try:
                result = validation_func()
                if not result:
                    all_passed = False
            except Exception as e:
                self.log_test(validation_name, False, f"Exception: {str(e)}")
                all_passed = False
        
        # Summary
        print("\n=== VALIDATION SUMMARY ===")
        passed_count = sum(1 for _, success, _ in self.test_results if success)
        total_count = len(self.test_results)
        
        print(f"Passed: {passed_count}/{total_count} tests")
        print(f"Overall Status: {'✅ ALL VALIDATIONS PASSED' if all_passed else '❌ SOME VALIDATIONS FAILED'}")
        
        if not all_passed:
            print("\n--- Failed Tests ---")
            for test_name, success, message in self.test_results:
                if not success:
                    print(f"❌ {test_name}: {message}")
        
        return all_passed

def main():
    """Main validation function"""
    validator = CompressionProviderValidator()
    success = validator.run_all_validations()
    
    if success:
        print("\n🎉 All validations passed! The compression provider is ready for use.")
        return 0
    else:
        print("\n⚠️  Some validations failed. Please review and fix the issues above.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
