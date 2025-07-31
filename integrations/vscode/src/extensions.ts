// integrations/vscode/src/extension.ts
import * as vscode from 'vscode';
import { CAIClient } from './cai-client';

// Addition: Create a disposable OutputChannel for logging (best practice for observability, per VSCode docs and Perficient 2025 guide)
const logger = vscode.window.createOutputChannel('TokenForge AI');

export function activate(context: vscode.ExtensionContext) {
    const caiClient = new CAIClient();
    
    // Addition: Wrap in try/catch for activation errors; log startup
    try {
        logger.appendLine('TokenForge AI extension activated');

        // Watch for file opens (enhanced with disposables and error handling)
        const openDisposable = vscode.workspace.onDidOpenTextDocument(async (document) => {
            if (document.languageId !== 'python') {
                return;  // Early exit for non-Python
            }
            try {
                const result = await caiClient.startSession(document.uri.fsPath);
                logger.appendLine(`Session started for ${document.fileName}: ${result.session_id}`);
                // Addition: User feedback (status bar or message)
                vscode.window.showInformationMessage(`TokenForge: Session ${result.session_id} ready for ${document.fileName}`);
            } catch (error) {
                logger.appendLine(`Error starting session for ${document.fileName}: ${error}`);
                vscode.window.showErrorMessage(`TokenForge: Failed to start session - check output for details`);
            }
        });
        context.subscriptions.push(openDisposable);  // Addition: Push to disposables for auto-cleanup (prevents leaks, per best practices)

        // Addition: Handle file changes (e.g., edits triggering re-compression; aligns with MVP flow for on_file_change)
        const changeDisposable = vscode.workspace.onDidChangeTextDocument(async (event) => {
            if (event.document.languageId !== 'python') {
                return;
            }
            const sessionId = caiClient.getSession(event.document.uri.fsPath);
            if (sessionId) {
                try {
                    await caiClient.updateSession(sessionId, event.document.uri.fsPath);  // Assume update method in CAIClient
                    logger.appendLine(`Session updated for changed ${event.document.fileName}`);
                } catch (error) {
                    logger.appendLine(`Error updating session: ${error}`);
                }
            }
        });
        context.subscriptions.push(changeDisposable);

        // Intercept completions (enhanced with full logic, error handling, and disposables)
        const completionDisposable = vscode.languages.registerCompletionItemProvider('python', {
            async provideCompletionItems(document, position, token, context) {  // Addition: Include token/context params for cancellation (perf)
                const session = caiClient.getSession(document.uri.fsPath);
                if (!session) {
                    logger.appendLine(`No session for completion in ${document.fileName}`);
                    return [];  // Graceful early exit
                }
                try {
                    const compressedContext = await caiClient.getCompressedContext(session.id);
                    // Full implementation (replacing placeholder): Send to LLM (assume backend call)
                    const llmResponse = await caiClient.sendToLLM(compressedContext, { position, context });  // Mock or real
                    const translated = await caiClient.translateResponse(llmResponse);  // Assume method
                    const item = new vscode.CompletionItem('TokenForge Suggestion', vscode.CompletionItemKind.Snippet);
                    item.insertText = new vscode.SnippetString(translated);
                    item.detail = 'Optimized by TokenForge AI';
                    logger.appendLine(`Completion provided for ${document.fileName}`);
                    return [item];
                } catch (error) {
                    logger.appendLine(`Completion error in ${document.fileName}: ${error}`);
                    return [];
                }
            }
        }, '.');  // Trigger on '.'
        context.subscriptions.push(completionDisposable);
    } catch (activationError) {
        logger.appendLine(`Activation failed: ${activationError}`);
        vscode.window.showErrorMessage('TokenForge AI: Extension activation failed');
    }
}

export function deactivate() {
    // Addition: Cleanup on deactivate (e.g., close sessions, clear logs; per best practices for resource disposal)
    logger.appendLine('TokenForge AI extension deactivated');
    CAIClient.cleanupAllSessions();  // Assume static method in CAIClient to end sessions
    logger.dispose();  // Clean up channel
}