// ===== integrations/vscode/src/cai-client.ts =====
import * as child_process from 'child_process';
import * as util from 'util';
import * as vscode from 'vscode';
import * as path from 'path';

const exec = util.promisify(child_process.exec);

interface SessionResult {
  session_id: string;
  // Add other expected fields as needed
}

interface CompressionResult {
  compression_ratio: number;
  original_tokens: number;
  compressed_tokens: number;
  // Add other fields as needed
}

class CAIClient {
  private sessions: Map<string, SessionResult> = new Map();
  private config = vscode.workspace.getConfiguration('optimize-ai');
  private debug: boolean = this.config.get('debugMode', false);

  private getCliPath(): string {
    // Allow configuration of CLI path if needed
    return 'optimize-ai';  // Assume in PATH, or configure via settings
  }

  private async executeCommand(command: string): Promise<string> {
    try {
      const { stdout, stderr } = await exec(command, { timeout: 30000 });  // 30s timeout
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
      const stdout = await this.executeCommand(`${this.getCliPath()} session start "${sanitizedPath}"`);
      const result: SessionResult = JSON.parse(stdout);
      this.sessions.set(filePath, result);
      return result;
    } catch (error) {
      throw new Error(`Session start failed: ${error.message}`);
    }
  }

  getSession(filePath: string): SessionResult | undefined {
    return this.sessions.get(filePath);
  }

  async getCompressedContext(sessionId: string): Promise<string> {
    try {
      const stdout = await this.executeCommand(`${this.getCliPath()} session get-context "${sessionId}"`);
      return stdout.trim();
    } catch (error) {
      throw new Error(`Get context failed: ${error.message}`);
    }
  }

  async requestCompletion(context: string, position: vscode.Position): Promise<string> {
    // Implement actual LLM request logic here
    // For MVP, use a placeholder or integrate with an API
    // Example placeholder:
    return `// Completion at line ${position.line + 1}, character ${position.character}`;
  }

  async compressCurrentFile(filePath: string): Promise<CompressionResult> {
    try {
      const sanitizedPath = path.resolve(filePath).replace(/"/g, '\\"');
      const stdout = await this.executeCommand(`${this.getCliPath()} compress "${sanitizedPath}"`);
      return JSON.parse(stdout);
    } catch (error) {
      throw new Error(`Compression failed: ${error.message}`);
    }
  }

  async getCompressionStats(sessionId: string): Promise<{ original_tokens: number; compressed_tokens: number }> {
    try {
      const stdout = await this.executeCommand(`${this.getCliPath()} session get-stats "${sessionId}"`);
      return JSON.parse(stdout);
    } catch (error) {
      throw new Error(`Get stats failed: ${error.message}`);
    }
  }
}

export { CAIClient };