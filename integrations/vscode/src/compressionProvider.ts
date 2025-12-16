// integrations/vscode/src/compressionProvider.ts
import * as vscode from "vscode";
import { CAIClient } from "./cai-client";

interface CompressionResult {
  compressed: string;
  tokensSaved: number;
  ratio: number;
  originalTokens: number;
  compressedTokens: number;
}

export class CompressionProvider {
  private client: CAIClient;
  private statusBar: vscode.StatusBarItem;
  private compressedCache: Map<string, CompressionResult> = new Map();
  private logger: vscode.OutputChannel;
  private config: vscode.WorkspaceConfiguration;

  constructor() {
    this.client = new CAIClient();
    this.logger = vscode.window.createOutputChannel("OptimizeAI Compression");
    this.config = vscode.workspace.getConfiguration("optimize-ai");

    // Create status bar item
    this.statusBar = vscode.window.createStatusBarItem(
      vscode.StatusBarAlignment.Right,
      100
    );
    this.statusBar.text = "$(sync~spin) OptimizeAI";
    this.statusBar.command = "optimize-ai.showStats";
    this.statusBar.show();

    this.logger.appendLine("CompressionProvider initialized");
  }

  async compressOnSave(document: vscode.TextDocument): Promise<void> {
    // Only process Python files for now
    if (document.languageId !== "python") {
      this.logger.appendLine(
        `Skipping compression for ${document.languageId} file: ${document.fileName}`
      );
      return;
    }

    // Skip untitled or non-file documents
    if (document.uri.scheme !== "file") {
      this.logger.appendLine(
        `Skipping compression for non-file URI: ${document.uri.toString()}`
      );
      return;
    }

    const filePath = document.uri.fsPath;
    this.logger.appendLine(`Starting compression for: ${filePath}`);

    // Update status to show compression in progress
    this.statusBar.text = "$(sync~spin) Compressing...";
    this.statusBar.tooltip = "OptimizeAI is compressing your code...";

    try {
      // Get or create session for this file
      let session = this.client.getSession(filePath);
      if (!session) {
        this.logger.appendLine(
          `No existing session found, starting new session for: ${filePath}`
        );
        session = await this.client.startSession(filePath);
      } else {
        this.logger.appendLine(`Using existing session: ${session.session_id}`);
        // Update session with current file content
        await this.client.updateSession(session.session_id, filePath);
      }

      // Perform compression
      const compressionStats = await this.client.compressCurrentFile(filePath);

      // Calculate compression results
      const result: CompressionResult = {
        compressed: await this.client.getCompressedContext(session.session_id),
        tokensSaved:
          compressionStats.original_tokens - compressionStats.compressed_tokens,
        ratio: Math.round(
          (1 -
            compressionStats.compressed_tokens /
              compressionStats.original_tokens) *
            100
        ),
        originalTokens: compressionStats.original_tokens,
        compressedTokens: compressionStats.compressed_tokens,
      };

      // Update status bar with success
      this.statusBar.text = `$(check) Saved ${result.tokensSaved} tokens`;
      this.statusBar.tooltip = `Compression: ${result.ratio}% reduction (${result.originalTokens} → ${result.compressedTokens} tokens)`;

      // Store compressed version for quick access
      this.storeCompressed(document.uri, result);

      // Log success
      this.logger.appendLine(`Compression completed for ${filePath}:`);
      this.logger.appendLine(`  Original tokens: ${result.originalTokens}`);
      this.logger.appendLine(`  Compressed tokens: ${result.compressedTokens}`);
      this.logger.appendLine(`  Tokens saved: ${result.tokensSaved}`);
      this.logger.appendLine(`  Compression ratio: ${result.ratio}%`);

      // Show user notification if enabled
      if (this.config.get("showCompressionNotifications", true)) {
        vscode.window.showInformationMessage(
          `OptimizeAI: Saved ${result.tokensSaved} tokens (${result.ratio}% compression)`
        );
      }
    } catch (error) {
      const errorMessage =
        error instanceof Error ? error.message : String(error);
      this.logger.appendLine(
        `Compression failed for ${filePath}: ${errorMessage}`
      );

      // Update status bar to show error
      this.statusBar.text = "$(error) Compression failed";
      this.statusBar.tooltip = `OptimizeAI compression error: ${errorMessage}`;

      // Show error to user
      vscode.window.showErrorMessage(`OptimizeAI: ${errorMessage}`);

      // Reset status bar after a delay
      setTimeout(() => {
        this.statusBar.text = "$(sync~spin) OptimizeAI";
        this.statusBar.tooltip =
          "OptimizeAI - Code compression for AI development";
      }, 5000);
    }
  }

  private storeCompressed(uri: vscode.Uri, result: CompressionResult): void {
    const key = uri.fsPath;
    this.compressedCache.set(key, result);
    this.logger.appendLine(`Stored compressed version for: ${key}`);

    // Limit cache size to prevent memory issues
    const maxCacheSize = this.config.get("maxCacheSize", 50);
    if (this.compressedCache.size > maxCacheSize) {
      const firstKey = this.compressedCache.keys().next().value;
      if (firstKey) {
        this.compressedCache.delete(firstKey);
        this.logger.appendLine(
          `Cache size limit reached, removed: ${firstKey}`
        );
      }
    }
  }

  getCompressedVersion(uri: vscode.Uri): CompressionResult | undefined {
    return this.compressedCache.get(uri.fsPath);
  }

  async copyCompressedToClipboard(uri: vscode.Uri): Promise<void> {
    const result = this.getCompressedVersion(uri);
    if (result) {
      await vscode.env.clipboard.writeText(result.compressed);
      vscode.window.showInformationMessage(
        `Copied compressed version to clipboard (${result.tokensSaved} tokens saved)`
      );
      this.logger.appendLine(
        `Copied compressed version to clipboard for: ${uri.fsPath}`
      );
    } else {
      vscode.window.showWarningMessage(
        "No compressed version available. Please save the file first."
      );
      this.logger.appendLine(
        `No compressed version available for: ${uri.fsPath}`
      );
    }
  }

  getCompressionStats(uri: vscode.Uri): CompressionResult | undefined {
    return this.getCompressedVersion(uri);
  }

  clearCache(): void {
    this.compressedCache.clear();
    this.logger.appendLine("Compression cache cleared");
    vscode.window.showInformationMessage(
      "OptimizeAI: Compression cache cleared"
    );
  }

  dispose(): void {
    this.statusBar.dispose();
    this.logger.dispose();
    this.compressedCache.clear();
    this.logger.appendLine("CompressionProvider disposed");
  }
}
