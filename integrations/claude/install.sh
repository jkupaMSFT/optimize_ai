#Claude Code wrapper installer#!/bin/bash
set -euo pipefail  # Enhanced error handling: exit on error, undefined vars, and pipe failures

# Install Claude Code wrapper for Optimize AI

# Function to check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Check prerequisites
if ! command_exists jq; then
    echo "Warning: 'jq' is recommended for JSON parsing in the wrapper. Install it via your package manager."
fi

# Define source and target
SOURCE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/claude-cai"
TARGET="$HOME/.local/bin/claude-cai"  # Use .local/bin for better standards compliance

# Check if source exists
if [ ! -f "$SOURCE" ]; then
    echo "Error: Source file $SOURCE does not exist."
    exit 1
fi

# Create directory if not exists
mkdir -p "$(dirname "$TARGET")"

# Handle existing file
if [ -f "$TARGET" ]; then
    read -p "File $TARGET already exists. Overwrite? (y/n): " confirm
    if [[ $confirm != [yY] ]]; then
        echo "Installation aborted."
        exit 0
    fi
fi

# Copy and make executable
cp "$SOURCE" "$TARGET"
chmod +x "$TARGET"

# Check if target directory is in PATH
if [[ ":$PATH:" != *":$(dirname "$TARGET"):"* ]]; then
    echo "Add $(dirname "$TARGET") to your PATH."
    echo "For bash/zsh: echo 'export PATH=\"\$HOME/.local/bin:\$PATH\"' >> ~/.bashrc  # or ~/.zshrc"
    echo "Then source your shell config: source ~/.bashrc"
fi

echo "Claude AI optimization wrapper installed at $TARGET"

# Provide uninstall instructions
echo "To uninstall: rm $TARGET"
echo "Note: This is an MVP installation. For updates, re-run this script."