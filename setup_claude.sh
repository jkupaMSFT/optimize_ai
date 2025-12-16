#!/bin/bash

echo "🚀 Setting up OptimizeAI Claude Code Integration..."

# Check for Claude CLI
if ! command -v claude &> /dev/null; then
    echo "⚠️  Claude CLI not found. Installing..."
    pip install anthropic-claude-cli
fi

# Create directories
mkdir -p ~/.optimize_ai/claude_cache
mkdir -p ~/.optimize_ai/sessions

# Install dependencies
pip install -r requirements.txt

# Add to PATH
echo 'alias opt-claude="python -m cli.main claude-code"' >> ~/.bashrc
echo 'alias opt-interactive="python -m cli.main claude-code interactive"' >> ~/.bashrc

echo "✅ Setup complete!"
echo ""
echo "Usage examples:"
echo "  opt-claude ask 'Fix the bug' -f app.py"
echo "  opt-claude analyze *.py -o reports/"
echo "  opt-interactive -f main.py"