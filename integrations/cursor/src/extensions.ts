// ===== integrations/cursor/src/extension.ts =====
import * as vscode from 'vscode';  // Cursor uses VSCode API
import { CAIClient } from './cai-client';

// Global logger for observability
const logger = vscode.window.createOutputChannel('Optimize AI');

export function activate(context: vscode.ExtensionContext) {
  const caiClient = new CAIClient();
  logger.appendLine('Optimize AI extension activated for Cursor');

  // Read configuration
  const config = vscode.workspace.getConfiguration('optimize-ai');
  const enabled = config.get<boolean>('enabled', true);
  if (!enabled) {
    logger.appendLine('Extension is disabled in settings');
    return;
  }

  // Watch for file opens
  const openDisposable = vscode.workspace.onDidOpenTextDocument(async (document) => {
    if (document.languageId === 'python') {
      try {
        const result = await caiClient.startSession(document.uri.fsPath);
        logger.appendLine(`Session started: ${result.session_id}`);
        vscode.window.showInformationMessage(`Optimize AI: Compression ready (Session ${result.session_id})`);
      } catch (error) {
        logger.appendLine(`Error starting session: ${error}`);
        vscode.window.showErrorMessage('Optimize AI: Session start failed');
      }
    }
  });
  context.subscriptions.push(openDisposable);

  // Cursor-specific autonomous mode handling
  const autonomousCommand = vscode.commands.registerCommand('cursor.autonomous.start', async () => {
    try {
      const editor = vscode.window.activeTextEditor;
      if (editor && editor.document.languageId === 'python') {
        const result = await caiClient.startAutonomousWorkflow(editor.document.uri.fsPath);
        vscode.window.showInformationMessage(`Autonomous workflow started: ${result.workflow_id}`);
      } else {
        vscode.window.showWarningMessage('No active Python file');
      }
    } catch (error) {
      vscode.window.showErrorMessage(`Autonomous start failed: ${error}`);
    }
  });
  context.subscriptions.push(autonomousCommand);

  // Register additional commands
  const compressCommand = vscode.commands.registerCommand('optimize-ai.compress', async () => {
    const editor = vscode.window.activeTextEditor;
    if (editor && editor.document.languageId === 'python') {
      try {
        const result = await caiClient.compressCurrentFile(editor.document.uri.fsPath);
        vscode.window.showInformationMessage(`Compression complete. Ratio: ${result.compression_ratio}%`);
      } catch (error) {
        vscode.window.showErrorMessage(`Compression failed: ${error}`);
      }
    } else {
      vscode.window.showWarningMessage('No active Python file');
    }
  });
  context.subscriptions.push(compressCommand);

  const showStatsCommand = vscode.commands.registerCommand('optimize-ai.showStats', async () => {
    const editor = vscode.window.activeTextEditor;
    if (editor && editor.document.languageId === 'python') {
      const session = caiClient.getSession(editor.document.uri.fsPath);
      if (session) {
        try {
          const stats = await caiClient.getCompressionStats(session.id);
          vscode.window.showInformationMessage(`Compression Stats: Original: ${stats.original_tokens}, Compressed: ${stats.compressed_tokens}`);
        } catch (error) {
          vscode.window.showErrorMessage(`Failed to get stats: ${error}`);
        }
      } else {
        vscode.window.showWarningMessage('No active session');
      }
    }
  });
  context.subscriptions.push(showStatsCommand);

  const copyCompressedCommand = vscode.commands.registerCommand('optimize-ai.copyCompressed', async () => {
    const editor = vscode.window.activeTextEditor;
    if (editor && editor.document.languageId === 'python') {
      const session = caiClient.getSession(editor.document.uri.fsPath);
      if (session) {
        try {
          const context = await caiClient.getCompressedContext(session.id);
          await vscode.env.clipboard.writeText(context);
          vscode.window.showInformationMessage('Compressed content copied to clipboard');
        } catch (error) {
          vscode.window.showErrorMessage(`Failed to copy: ${error}`);
        }
      } else {
        vscode.window.showWarningMessage('No active session');
      }
    }
  });
  context.subscriptions.push(copyCompressedCommand);

  const toggleAutoCompressCommand = vscode.commands.registerCommand('optimize-ai.toggleAutoCompress', async () => {
    const current = config.get<boolean>('autoCompress', true);
    await config.update('autoCompress', !current, vscode.ConfigurationTarget.Global);
    vscode.window.showInformationMessage(`Auto compression ${!current ? 'enabled' : 'disabled'}`);
  });
  context.subscriptions.push(toggleAutoCompressCommand);

  // Status bar item
  const statusBarItem = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Right, 100);
  statusBarItem.text = '$(gear) Optimize AI';
  statusBarItem.tooltip = 'Optimize AI Status';
  statusBarItem.show();
  context.subscriptions.push(statusBarItem);

  // Update status bar on file change
  const changeDisposable = vscode.window.onDidChangeActiveTextEditor((editor) => {
    if (editor && editor.document.languageId === 'python') {
      const session = caiClient.getSession(editor.document.uri.fsPath);
      if (session) {
        statusBarItem.text = `$(check) Optimized (Session ${session.id})`;
      } else {
        statusBarItem.text = '$(alert) Not Optimized';
      }
    } else {
      statusBarItem.text = '$(gear) Optimize AI';
    }
  });
  context.subscriptions.push(changeDisposable);
}

export function deactivate() {
  logger.appendLine('Optimize AI extension deactivated');
}