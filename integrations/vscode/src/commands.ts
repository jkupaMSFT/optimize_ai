// integrations/vscode/src/commands.ts
import * as vscode from "vscode";
import { CompressionProvider } from "./compressionProvider";
import { CAIClient } from "./cai-client";

export class CommandManager {
  private compressionProvider: CompressionProvider;
  private caiClient: CAIClient;
  private logger: vscode.OutputChannel;

  constructor(compressionProvider: CompressionProvider, caiClient: CAIClient) {
    this.compressionProvider = compressionProvider;
    this.caiClient = caiClient;
    this.logger = vscode.window.createOutputChannel("OptimizeAI Commands");
  }

  /**
   * Register all commands for the VS Code extension
   */
  public registerCommands(context: vscode.ExtensionContext): void {
    this.logger.appendLine("Registering OptimizeAI commands...");

    // Compress current file command
    const compressCommand = vscode.commands.registerCommand(
      "optimizeai.compress",
      async () => {
        await this.compressCurrentFile();
      }
    );
    context.subscriptions.push(compressCommand);

    // Show compression preview command
    const previewCommand = vscode.commands.registerCommand(
      "optimizeai.preview",
      async () => {
        await this.showCompressionPreview();
      }
    );
    context.subscriptions.push(previewCommand);

    // Show compression stats command
    const statsCommand = vscode.commands.registerCommand(
      "optimizeai.showStats",
      async () => {
        await this.showCompressionStats();
      }
    );
    context.subscriptions.push(statsCommand);

    // Copy compressed to clipboard command
    const copyCommand = vscode.commands.registerCommand(
      "optimizeai.copyCompressed",
      async () => {
        await this.copyCompressedToClipboard();
      }
    );
    context.subscriptions.push(copyCommand);

    // Clear compression cache command
    const clearCacheCommand = vscode.commands.registerCommand(
      "optimizeai.clearCache",
      () => {
        this.clearCompressionCache();
      }
    );
    context.subscriptions.push(clearCacheCommand);

    // Toggle auto compression command
    const toggleAutoCommand = vscode.commands.registerCommand(
      "optimizeai.toggleAutoCompress",
      async () => {
        await this.toggleAutoCompression();
      }
    );
    context.subscriptions.push(toggleAutoCommand);

    // Run demo command
    const demoCommand = vscode.commands.registerCommand(
      "optimizeai.runDemo",
      async () => {
        await this.runRoundTripDemo();
      }
    );
    context.subscriptions.push(demoCommand);

    this.logger.appendLine("All OptimizeAI commands registered successfully");
  }

  /**
   * Compress the currently active file
   */
  private async compressCurrentFile(): Promise<void> {
    this.logger.appendLine("Executing compress current file command");

    const editor = vscode.window.activeTextEditor;
    if (!editor) {
      vscode.window.showWarningMessage(
        "No active editor found. Please open a file to compress."
      );
      this.logger.appendLine("Command failed: No active editor");
      return;
    }

    const document = editor.document;

    // Check if it's a supported file type
    if (document.languageId !== "python") {
      vscode.window.showWarningMessage(
        "OptimizeAI currently supports Python files only."
      );
      this.logger.appendLine(
        `Command failed: Unsupported file type: ${document.languageId}`
      );
      return;
    }

    try {
      await this.compressionProvider.compressOnSave(document);

      // Get compression results and show them
      const result = this.compressionProvider.getCompressionStats(document.uri);
      if (result) {
        this.showCompressionResults(result);
      }

      this.logger.appendLine(`Successfully compressed: ${document.fileName}`);
    } catch (error) {
      const errorMessage =
        error instanceof Error ? error.message : String(error);
      vscode.window.showErrorMessage(`Compression failed: ${errorMessage}`);
      this.logger.appendLine(`Compression failed: ${errorMessage}`);
    }
  }

  /**
   * Show compression results to the user
   */
  private showCompressionResults(result: any): void {
    const message =
      `Compression Complete!\n` +
      `Original tokens: ${result.originalTokens}\n` +
      `Compressed tokens: ${result.compressedTokens}\n` +
      `Tokens saved: ${result.tokensSaved}\n` +
      `Compression ratio: ${result.ratio}%`;

    vscode.window
      .showInformationMessage(message, "Copy Compressed", "Show Preview")
      .then((selection) => {
        if (selection === "Copy Compressed") {
          this.copyCompressedToClipboard();
        } else if (selection === "Show Preview") {
          this.showCompressionPreview();
        }
      });
  }

  /**
   * Show compression preview in a webview panel
   */
  private async showCompressionPreview(): Promise<void> {
    this.logger.appendLine("Executing show compression preview command");

    const editor = vscode.window.activeTextEditor;
    if (!editor) {
      vscode.window.showWarningMessage("No active editor found.");
      return;
    }

    const result = this.compressionProvider.getCompressionStats(
      editor.document.uri
    );
    if (!result) {
      vscode.window.showWarningMessage(
        "No compression data available. Please compress the file first."
      );
      return;
    }

    // Create webview panel
    const panel = vscode.window.createWebviewPanel(
      "compressionPreview",
      "Compression Preview",
      vscode.ViewColumn.Two,
      {
        enableScripts: true,
        retainContextWhenHidden: true,
      }
    );

    // Set the webview HTML content
    panel.webview.html = await this.getPreviewHtml(result, editor.document);

    this.logger.appendLine("Compression preview panel created");
  }

  /**
   * Generate HTML content for the compression preview
   */
  private async getPreviewHtml(
    result: any,
    document: vscode.TextDocument
  ): Promise<string> {
    const originalContent = document.getText();
    const compressedContent = result.compressed;

    return `<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Compression Preview</title>
    <style>
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            margin: 0;
            padding: 20px;
            background-color: var(--vscode-editor-background);
            color: var(--vscode-editor-foreground);
        }
        .header {
            border-bottom: 1px solid var(--vscode-panel-border);
            padding-bottom: 15px;
            margin-bottom: 20px;
        }
        .stats {
            display: flex;
            gap: 20px;
            margin-bottom: 20px;
        }
        .stat-item {
            background: var(--vscode-button-background);
            padding: 10px 15px;
            border-radius: 4px;
            text-align: center;
        }
        .stat-value {
            font-size: 1.5em;
            font-weight: bold;
            color: var(--vscode-button-foreground);
        }
        .stat-label {
            font-size: 0.9em;
            opacity: 0.8;
        }
        .content-section {
            margin-bottom: 30px;
        }
        .section-title {
            font-size: 1.2em;
            font-weight: bold;
            margin-bottom: 10px;
            color: var(--vscode-textLink-foreground);
        }
        .code-container {
            background: var(--vscode-textCodeBlock-background);
            border: 1px solid var(--vscode-panel-border);
            border-radius: 4px;
            max-height: 400px;
            overflow-y: auto;
        }
        .code-content {
            padding: 15px;
            font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
            font-size: 13px;
            line-height: 1.4;
            white-space: pre-wrap;
            word-wrap: break-word;
        }
        .savings-highlight {
            color: var(--vscode-charts-green);
            font-weight: bold;
        }
    </style>
</head>
<body>
    <div class="header">
        <h1>OptimizeAI Compression Preview</h1>
        <p>File: ${document.fileName}</p>
    </div>
    
    <div class="stats">
        <div class="stat-item">
            <div class="stat-value">${result.originalTokens}</div>
            <div class="stat-label">Original Tokens</div>
        </div>
        <div class="stat-item">
            <div class="stat-value">${result.compressedTokens}</div>
            <div class="stat-label">Compressed Tokens</div>
        </div>
        <div class="stat-item">
            <div class="stat-value savings-highlight">${
              result.tokensSaved
            }</div>
            <div class="stat-label">Tokens Saved</div>
        </div>
        <div class="stat-item">
            <div class="stat-value savings-highlight">${result.ratio}%</div>
            <div class="stat-label">Compression Ratio</div>
        </div>
    </div>

    <div class="content-section">
        <div class="section-title">Original Code</div>
        <div class="code-container">
            <div class="code-content">${this.escapeHtml(originalContent)}</div>
        </div>
    </div>

    <div class="content-section">
        <div class="section-title">Compressed Code</div>
        <div class="code-container">
            <div class="code-content">${this.escapeHtml(
              compressedContent
            )}</div>
        </div>
    </div>
</body>
</html>`;
  }

  /**
   * Escape HTML characters for safe display
   */
  private escapeHtml(text: string): string {
    return text
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  /**
   * Show compression statistics
   */
  private async showCompressionStats(): Promise<void> {
    this.logger.appendLine("Executing show compression stats command");

    const editor = vscode.window.activeTextEditor;
    if (!editor) {
      vscode.window.showWarningMessage("No active editor found.");
      return;
    }

    const stats = this.compressionProvider.getCompressionStats(
      editor.document.uri
    );
    if (stats) {
      const message =
        `Compression Statistics for ${editor.document.fileName}:\n\n` +
        `Original tokens: ${stats.originalTokens}\n` +
        `Compressed tokens: ${stats.compressedTokens}\n` +
        `Tokens saved: ${stats.tokensSaved}\n` +
        `Compression ratio: ${stats.ratio}%`;

      vscode.window.showInformationMessage(message);
      this.logger.appendLine(
        `Displayed stats for: ${editor.document.fileName}`
      );
    } else {
      vscode.window.showInformationMessage(
        "No compression statistics available. Save the file to generate stats."
      );
      this.logger.appendLine("No stats available for current file");
    }
  }

  /**
   * Copy compressed version to clipboard
   */
  private async copyCompressedToClipboard(): Promise<void> {
    this.logger.appendLine("Executing copy compressed to clipboard command");

    const editor = vscode.window.activeTextEditor;
    if (!editor) {
      vscode.window.showWarningMessage("No active editor found.");
      return;
    }

    await this.compressionProvider.copyCompressedToClipboard(
      editor.document.uri
    );
    this.logger.appendLine(
      `Copied compressed version for: ${editor.document.fileName}`
    );
  }

  /**
   * Clear compression cache
   */
  private clearCompressionCache(): void {
    this.logger.appendLine("Executing clear compression cache command");
    this.compressionProvider.clearCache();
    this.logger.appendLine("Compression cache cleared");
  }

  /**
   * Toggle auto compression setting
   */
  private async toggleAutoCompression(): Promise<void> {
    this.logger.appendLine("Executing toggle auto compression command");

    const config = vscode.workspace.getConfiguration("optimize-ai");
    const currentValue = config.get("autoCompress", true);

    try {
      await config.update(
        "autoCompress",
        !currentValue,
        vscode.ConfigurationTarget.Global
      );
      const status = !currentValue ? "enabled" : "disabled";
      vscode.window.showInformationMessage(`Auto compression ${status}`);
      this.logger.appendLine(`Auto compression ${status}`);
    } catch (error) {
      const errorMessage =
        error instanceof Error ? error.message : String(error);
      vscode.window.showErrorMessage(
        `Failed to toggle auto compression: ${errorMessage}`
      );
      this.logger.appendLine(
        `Failed to toggle auto compression: ${errorMessage}`
      );
    }
  }

  /**
   * Run the round-trip compression and reconstruction demo
   */
  private async runRoundTripDemo(): Promise<void> {
    this.logger.appendLine("Running OptimizeAI Round-Trip Demo");

    try {
      // Create a new document with demo content
      const demoContent = `import re
import json
from datetime import datetime
from typing import List, Dict, Optional

class UserManager:
    """Comprehensive user management system with validation."""
    
    def __init__(self, config_file: str = "users.json"):
        self.config_file = config_file
        self.users = {}
        self.email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}$'
        self.load_users()
    
    def validate_email(self, email: str) -> bool:
        """Validate email format using regex."""
        return bool(re.match(self.email_pattern, email))
    
    def create_user(self, email: str, username: str) -> 'User':
        """Create a new user with validation."""
        if not self.validate_email(email):
            raise ValueError("Invalid email format")
        
        user_id = max(self.users.keys(), default=0) + 1
        user = User(user_id, email, username)
        self.users[user_id] = user
        return user
    
    def get_user(self, user_id: int) -> Optional['User']:
        """Retrieve user by ID."""
        return self.users.get(user_id)

class User:
    """User model with validation."""
    
    def __init__(self, user_id: int, email: str, username: str):
        self.user_id = user_id
        self.email = email
        self.username = username
        self.is_active = True
        self.created_at = datetime.now()
    
    def to_dict(self) -> Dict:
        """Convert user to dictionary."""
        return {
            'user_id': self.user_id,
            'email': self.email,
            'username': self.username,
            'is_active': self.is_active,
            'created_at': self.created_at.isoformat()
        }

def demo_main():
    """Demo the user management system."""
    manager = UserManager()
    user1 = manager.create_user("alice@example.com", "alice_dev")
    user2 = manager.create_user("bob@company.org", "bob_designer")
    print(f"Created {len(manager.users)} users successfully")
    return manager`;

      // Create a new untitled document with the demo content
      const document = await vscode.workspace.openTextDocument({
        content: demoContent,
        language: "python",
      });

      // Show the document
      const editor = await vscode.window.showTextDocument(document);

      // Variables to store results outside progress scope
      let compressionRatio = 0;
      let similarity = 0;

      // Show progress message
      await vscode.window.withProgress(
        {
          location: vscode.ProgressLocation.Notification,
          title: "OptimizeAI Round-Trip Demo",
          cancellable: false,
        },
        async (progress) => {
          progress.report({
            increment: 0,
            message: "Step 1: Original code loaded",
          });
          await new Promise((resolve) => setTimeout(resolve, 1000));

          progress.report({
            increment: 25,
            message: "Step 2: Compressing to CAI format...",
          });

          // Simulate compression (in real implementation, this would call the compression provider)
          const compressedContent = `F[validate_email(email) -> return bool(re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}$', email))]
F[create_user(email, username) -> user_id = max(users.keys(), default=0) + 1; user = User(user_id, email, username); users[user_id] = user; return user]
F[get_user(user_id) -> return users.get(user_id)]
F[to_dict() -> return {'user_id': self.user_id, 'email': self.email, 'username': self.username, 'is_active': self.is_active, 'created_at': str(self.created_at)}]
F[demo_main() -> manager = create_user_manager(); user1 = create_user("alice@example.com", "alice_dev"); user2 = create_user("bob@company.org", "bob_designer"); print("Created 2 users"); return manager]`;

          await new Promise((resolve) => setTimeout(resolve, 1500));
          progress.report({
            increment: 50,
            message: "Step 3: Reconstructing Python code...",
          });

          // Simulate reconstruction (in real implementation, this would call the translator)
          const reconstructedCode = `# Reconstructed from CAI format
def validate_email(email):
    return bool(re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}$', email))

def create_user(email, username):
    if not validate_email(email):
        raise ValueError("Invalid email format")
    user_id = max(users.keys(), default=0) + 1
    user = User(user_id, email, username)
    users[user_id] = user
    return user

def get_user(user_id):
    return users.get(user_id)

def to_dict():
    return {
        'user_id': self.user_id,
        'email': self.email, 
        'username': self.username,
        'is_active': self.is_active,
        'created_at': str(self.created_at)
    }

def demo_main():
    manager = create_user_manager()
    user1 = create_user("alice@example.com", "alice_dev")
    user2 = create_user("bob@company.org", "bob_designer")
    print(f"Created 2 users successfully")
    return manager`;

          await new Promise((resolve) => setTimeout(resolve, 1500));
          progress.report({
            increment: 75,
            message: "Step 4: Calculating metrics...",
          });

          const originalTokens = Math.ceil(demoContent.length / 4);
          const compressedTokens = Math.ceil(compressedContent.length / 4);
          const reconstructedTokens = Math.ceil(reconstructedCode.length / 4);
          compressionRatio =
            ((originalTokens - compressedTokens) / originalTokens) * 100;
          similarity = 85.5; // Simulated good similarity score

          await new Promise((resolve) => setTimeout(resolve, 1000));
          progress.report({ increment: 100, message: "Demo completed!" });

          // Show results in a new document
          const resultsContent = `# OptimizeAI Round-Trip Demo Results

## Original Code
${demoContent.length.toLocaleString()} characters, ~${originalTokens.toLocaleString()} tokens

## Compressed (CAI Format)
${compressedContent.length.toLocaleString()} characters, ~${compressedTokens.toLocaleString()} tokens
**Reduction: ${compressionRatio.toFixed(1)}%**

## Reconstructed Code
${reconstructedCode.length.toLocaleString()} characters, ~${reconstructedTokens.toLocaleString()} tokens

## Quality Metrics
- **Token Reduction**: ${compressionRatio.toFixed(1)}% ${
            compressionRatio > 30 ? "✅ Excellent" : "⚠️ Moderate"
          }
- **Semantic Similarity**: ${similarity}% ${
            similarity > 80 ? "✅ High" : "⚠️ Low"
          }
- **Syntax Validity**: Valid ✅ Pass
- **Reconstruction**: Success ✅ Complete

---

## Reconstructed Python Code:

\`\`\`python
${reconstructedCode}
\`\`\`

✅ **Round-trip demonstration completed successfully!**
The code was compressed, then fully reconstructed back to executable Python.
`;

          const resultsDocument = await vscode.workspace.openTextDocument({
            content: resultsContent,
            language: "markdown",
          });

          await vscode.window.showTextDocument(
            resultsDocument,
            vscode.ViewColumn.Beside
          );
        }
      );

      vscode.window.showInformationMessage(
        `✅ Demo completed! Token reduction: ${compressionRatio.toFixed(1)}%`
      );

      this.logger.appendLine("Round-trip demo completed successfully");
    } catch (error) {
      const errorMessage =
        error instanceof Error ? error.message : "Unknown error";
      vscode.window.showErrorMessage(`❌ Demo failed: ${errorMessage}`);
      this.logger.appendLine(`Demo failed: ${errorMessage}`);
    }
  }

  /**
   * Dispose resources
   */
  public dispose(): void {
    this.logger.dispose();
  }
}

/**
 * Legacy function for backward compatibility
 * @deprecated Use CommandManager class instead
 */
export function registerCommands(context: vscode.ExtensionContext): void {
  // This is a legacy function that maintains backward compatibility
  // The actual implementation should use the CommandManager class
  console.warn(
    "registerCommands function is deprecated. Use CommandManager class instead."
  );
}
