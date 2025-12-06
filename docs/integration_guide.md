# Optimize AI Integration Guide

## Prerequisites

Before integrating Optimize AI with your preferred agent, ensure the following:

- Python 3.8 or higher installed.
- Optimize AI package installed via `pip install optimize-ai`.
- For VSCode and Cursor: The respective IDE installed (VSCode >=1.74.0, Cursor >=1.0.0).
- For Claude: Claude Code CLI tool installed and API key configured.
- Access to sample Python files for testing.
- Environment variables set if needed (e.g., `OPTIMIZE_AI_SERVER_URL` for custom server).

If encountering issues, check the logs in `~/.optimize_ai/app.log` or enable debug mode in configurations.

## VSCode Integration

### Installation

1. **Via Marketplace (Recommended for Production):**
   - Search for "Optimize AI - Code Compression" in the VSCode Extensions Marketplace.
   - Click "Install".
   - Restart VSCode if prompted.

2. **Sideload for Development or Custom Builds:**
   - Clone the Optimize AI repository: `git clone https://github.com/optimize-ai/optimize-ai.git`.
   - Navigate to `integrations/vscode`.
   - Run `npm install` to install dependencies.
   - Build the extension: `npm run compile`.
   - In VSCode, go to Extensions view, click the "..." menu, and select "Install from VSIX...".
   - Choose the built VSIX file (or copy the folder to `~/.vscode/extensions/optimize-ai-vscode`).

3. **CLI Installation:**
   - Use the Optimize AI CLI: `optimize-ai integrate install vscode`.

### Configuration

Configure in VSCode's `settings.json` (accessible via Command Palette > "Preferences: Open Settings (JSON)"):

```json
{
  "optimize-ai.enabled": true,
  "optimize-ai.autoCompress": true,
  "optimize-ai.showStatusBar": true,
  "optimize-ai.compressionThreshold": 100,
  "optimize-ai.serverUrl": "http://localhost:8000",
  "optimize-ai.debugMode": false
}
```

- `enabled`: Toggle the extension on/off.
- `autoCompress`: Automatically compress on file open.
- `showStatusBar`: Display stats in status bar.
- `compressionThreshold`: Min tokens to compress.
- `serverUrl`: Custom server endpoint if self-hosted.
- `debugMode`: Enable detailed logging.

### Usage

- Open a Python file: Auto-compresses if enabled.
- Use commands (Command Palette):
  - "Compress for AI": Manual compression.
  - "Show Compression Stats": View tokens saved.
  - "Copy Compressed to Clipboard": Copy CAI format.
  - "Toggle Auto Compression": Switch auto mode.
- Status bar shows session info; click for details.

### Troubleshooting

- If compression fails: Check debug logs (Output > Optimize AI).
- Extension not activating: Ensure on Python file and restart VSCode.
- API errors: Verify server URL and network.
- Common issues: Update VSCode, reinstall extension.

## Cursor Integration

Cursor uses a similar VSCode-based API, so integration mirrors VSCode with Cursor-specific optimizations.

### Installation

1. **Sideload (Primary Method, as Cursor may not have a marketplace):**
   - Clone the repository: `git clone https://github.com/optimize-ai/optimize-ai.git`.
   - Navigate to `integrations/cursor`.
   - Run `npm install` and `npm run compile`.
   - Copy the folder to `~/.cursor/extensions/optimize-ai-cursor`.

2. **CLI Installation:**
   - `optimize-ai integrate install cursor`.

### Configuration

Similar to VSCode, edit Cursor's `settings.json`:

```json
{
  "optimize-ai.enabled": true,
  "optimize-ai.autoCompress": true,
  "optimize-ai.showStatusBar": true,
  "optimize-ai.compressionThreshold": 100,
  "optimize-ai.serverUrl": "http://localhost:8000",
  "optimize-ai.debugMode": false
}
```

Additional Cursor-specific features:
- Autonomous workflow support: Compresses multi-file contexts.
- Composer integration: Formats prompts with compressed content.

### Usage

- Same commands as VSCode.
- In autonomous mode: Optimize AI auto-handles file compression.
- Status bar and context menu integration for quick actions.

### Troubleshooting

- Similar to VSCode.
- Cursor-specific: Ensure Sonnet 3.7 features are enabled in Cursor settings.
- If workflows fail: Check multi-file batch size in config.

## Claude Code Integration

Integrate via a CLI wrapper for Claude Code commands.

### Installation

1. **Manual Installation:**
   - Clone the repository.
   - Run `integrations/claude/install.sh` (makes executable and copies to `~/.local/bin/claude-cai`).

2. **CLI Installation:**
   - `optimize-ai integrate install claude`.

Add `~/.local/bin` to PATH if not already: `export PATH="$HOME/.local/bin:$PATH"`.

### Configuration

No direct config file; uses environment variables:
- `CLAUDE_MAX_CONTEXT_TOKENS`: Default 100000.
- `CLAUDE_RETRY_ATTEMPTS`: Default 3 for rate limits.

### Usage

- Replace `claude-code` with `claude-cai` in commands:
  - Example: `claude-cai edit file.py --instruction "Refactor this"`.
- The wrapper intercepts, compresses input, and passes CAI format to Claude.
- Handles retries on rate limits.

### Troubleshooting

- Command not found: Add to PATH and restart terminal.
- Rate limits: Increase retry attempts via env var.
- Compression failures: Check logs for file size/issues.
- Verify with `claude-cai --version` if implemented.

## General Tips

- Test with small Python files first.
- Monitor metrics: Use CLI `optimize-ai session get <id>` for stats.
- Update: Re-run installation for updates.
- Uninstall: `optimize-ai integrate uninstall <agent>`.
- Support: Check GitHub issues or docs for updates.

For custom setups or self-hosting, refer to the full documentation.