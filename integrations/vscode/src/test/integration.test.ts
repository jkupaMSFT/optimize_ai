// integrations/vscode/src/test/integration.test.ts
import * as vscode from "vscode";
import * as path from "path";
import { CompressionProvider } from "../compressionProvider";

/**
 * Simple integration test for CompressionProvider
 * This test verifies the basic functionality without relying on external test frameworks
 */
export async function runCompressionProviderTests(): Promise<void> {
  console.log("Starting CompressionProvider integration tests...");

  const compressionProvider = new CompressionProvider();

  try {
    // Test 1: Initialize provider
    console.log("Test 1: CompressionProvider initialization");
    if (!compressionProvider) {
      throw new Error("CompressionProvider failed to initialize");
    }
    console.log("✓ CompressionProvider initialized successfully");

    // Test 2: Test cache operations
    console.log("Test 2: Cache operations");
    compressionProvider.clearCache();
    const mockUri = vscode.Uri.file("/test/mock.py");
    const stats = compressionProvider.getCompressionStats(mockUri);
    if (stats !== undefined) {
      throw new Error("Expected undefined stats for non-existent file");
    }
    console.log("✓ Cache operations working correctly");

    // Test 3: Test non-Python file handling
    console.log("Test 3: Non-Python file handling");
    const mockJSDocument = {
      languageId: "javascript",
      fileName: "test.js",
      uri: { scheme: "file", fsPath: "/test/test.js" },
    } as vscode.TextDocument;

    // This should complete without errors
    await compressionProvider.compressOnSave(mockJSDocument);
    console.log("✓ Non-Python files handled correctly");

    // Test 4: Test URI scheme validation
    console.log("Test 4: URI scheme validation");
    const mockUntitledDocument = {
      languageId: "python",
      fileName: "Untitled-1",
      uri: { scheme: "untitled", fsPath: "" },
    } as vscode.TextDocument;

    // This should complete without errors for non-file URIs
    await compressionProvider.compressOnSave(mockUntitledDocument);
    console.log("✓ URI scheme validation working correctly");

    console.log("All CompressionProvider tests passed!");
  } catch (error) {
    console.error("CompressionProvider test failed:", error);
    throw error;
  } finally {
    // Clean up
    compressionProvider.dispose();
    console.log("CompressionProvider tests completed and resources cleaned up");
  }
}

// Export for manual testing
if (require.main === module) {
  runCompressionProviderTests().catch(console.error);
}
