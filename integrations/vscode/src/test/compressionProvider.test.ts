// integrations/vscode/src/test/compressionProvider.test.ts
import * as assert from "assert";
import * as vscode from "vscode";
import { CompressionProvider } from "../compressionProvider";

suite("CompressionProvider Test Suite", () => {
  let compressionProvider: CompressionProvider;

  setup(() => {
    compressionProvider = new CompressionProvider();
  });

  teardown(() => {
    compressionProvider.dispose();
  });

  test("CompressionProvider should initialize properly", () => {
    assert.ok(compressionProvider);
  });

  test("Should skip non-Python files", async () => {
    // Create a mock document
    const mockDocument = {
      languageId: "javascript",
      fileName: "test.js",
      uri: { scheme: "file", fsPath: "/test.js" },
    } as vscode.TextDocument;

    // This should complete without errors for non-Python files
    await compressionProvider.compressOnSave(mockDocument);

    // Since it's not Python, no compression should be stored
    const result = compressionProvider.getCompressedVersion(mockDocument.uri);
    assert.strictEqual(result, undefined);
  });

  test("Should handle cache operations correctly", () => {
    // Test cache clearing
    compressionProvider.clearCache();

    // Test getting stats for non-existent file
    const mockUri = vscode.Uri.file("/non-existent.py");
    const stats = compressionProvider.getCompressionStats(mockUri);
    assert.strictEqual(stats, undefined);
  });
});
