// ===== integrations/vscode/src/cai-client.ts =====
import * as child_process from "child_process";
import * as util from "util";
import * as vscode from "vscode";
import * as path from "path";

const exec = util.promisify(child_process.exec);

interface SessionResult {
  session_id: string;
  id: string; // Adding alias for compatibility
  // Add other expected fields as needed
}

interface CompressionResult {
  compression_ratio: number;
  original_tokens: number;
  compressed_tokens: number;
  compressed?: string;
  tokensSaved?: number;
  ratio?: number;
  // Add other fields as needed
}

class CAIClient {
  private sessions: Map<string, SessionResult> = new Map();
  private config = vscode.workspace.getConfiguration("optimize-ai");
  private debug: boolean = this.config.get("debugMode", false);

  private getCliPath(): string {
    // Allow configuration of CLI path if needed
    return "optimize-ai"; // Assume in PATH, or configure via settings
  }

  private async executeCommand(command: string): Promise<string> {
    try {
      const { stdout, stderr } = await exec(command, { timeout: 30000 }); // 30s timeout
      if (stderr) {
        console.warn(`CLI warning: ${stderr}`);
      }
      return stdout;
    } catch (error) {
      if (this.debug) {
        console.error(`CLI execution error: ${error}`);
      }
      throw error;
    }
  }

  async startSession(filePath: string): Promise<SessionResult> {
    try {
      const sanitizedPath = path.resolve(filePath).replace(/"/g, '\\"');
      const stdout = await this.executeCommand(
        `${this.getCliPath()} session start "${sanitizedPath}"`
      );
      const result: SessionResult = JSON.parse(stdout);
      // Ensure both session_id and id are available
      if (!result.id && result.session_id) {
        result.id = result.session_id;
      }
      this.sessions.set(filePath, result);
      return result;
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      throw new Error(`Session start failed: ${message}`);
    }
  }

  async updateSession(sessionId: string, filePath: string): Promise<void> {
    try {
      const sanitizedPath = path.resolve(filePath).replace(/"/g, '\\"');
      await this.executeCommand(
        `${this.getCliPath()} session update "${sessionId}" "${sanitizedPath}"`
      );
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      throw new Error(`Session update failed: ${message}`);
    }
  }

  getSession(filePath: string): SessionResult | undefined {
    return this.sessions.get(filePath);
  }

  async getCompressedContext(sessionId: string): Promise<string> {
    try {
      const stdout = await this.executeCommand(
        `${this.getCliPath()} session get-context "${sessionId}"`
      );
      return stdout.trim();
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      throw new Error(`Get context failed: ${message}`);
    }
  }

  async requestCompletion(
    context: string,
    position: vscode.Position
  ): Promise<string> {
    // Implement actual LLM request logic here
    // For MVP, use a placeholder or integrate with an API
    // Example placeholder:
    return `// Completion at line ${position.line + 1}, character ${
      position.character
    }`;
  }

  async compressCurrentFile(filePath: string): Promise<CompressionResult> {
    try {
      const sanitizedPath = path.resolve(filePath).replace(/"/g, '\\"');
      const stdout = await this.executeCommand(
        `${this.getCliPath()} compress "${sanitizedPath}"`
      );
      return JSON.parse(stdout);
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      throw new Error(`Compression failed: ${message}`);
    }
  }

  async getCompressionStats(
    sessionId: string
  ): Promise<{ original_tokens: number; compressed_tokens: number }> {
    try {
      const stdout = await this.executeCommand(
        `${this.getCliPath()} session get-stats "${sessionId}"`
      );
      return JSON.parse(stdout);
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      throw new Error(`Get stats failed: ${message}`);
    }
  }

  async sendToLLM(context: string, options: any): Promise<string> {
    // Mock implementation for now - replace with actual LLM integration
    return `Mock LLM response based on context: ${context.substring(
      0,
      100
    )}...`;
  }

  async translateResponse(response: string): Promise<string> {
    // Mock implementation for now - replace with actual translation logic
    return response;
  }

  async compress(content: string): Promise<CompressionResult> {
    try {
      // For now, create a temporary file to compress
      // In a real implementation, you might want to use a different approach
      const tempPath = path.join(__dirname, "temp_compression_file.py");
      const fs = require("fs").promises;

      await fs.writeFile(tempPath, content);

      const result = await this.compressCurrentFile(tempPath);

      // Clean up temp file
      try {
        await fs.unlink(tempPath);
      } catch (cleanupError) {
        console.warn("Failed to clean up temp file:", cleanupError);
      }

      // Enhance result with additional properties expected by CompressionProvider
      const enhancedResult: CompressionResult = {
        ...result,
        compressed: content, // For now, return original content - implement actual compression
        tokensSaved: result.original_tokens - result.compressed_tokens,
        ratio: Math.round(
          (1 - result.compressed_tokens / result.original_tokens) * 100
        ),
      };

      return enhancedResult;
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      throw new Error(`Compression failed: ${message}`);
    }
  }

  static cleanupAllSessions(): void {
    // Static method to cleanup all sessions
    // This would typically clean up any global state or background processes
    console.log("Cleaning up all CAI sessions");
  }
}

export { CAIClient };
