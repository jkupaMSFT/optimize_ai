#!/usr/bin/env python3
"""
Optimize Claude - CLI wrapper for Claude Code with automatic compression
"""

import argparse
import sys
from pathlib import Path

# Add parent directory to path
sys.path.append(str(Path(__file__).parent.parent.parent.parent))

from optimize_ai.integrations.claude_wrapper.claude_proxy import ClaudeCodeProxy
from optimize_ai.utils.logger import setup_logger

def main():
    parser = argparse.ArgumentParser(
        description="Optimize Claude - Intelligent compression wrapper for Claude Code",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  optimize-claude "implement a React dashboard"
  optimize-claude --file app.py "add error handling"
  optimize-claude --no-compress "debug this code"
  optimize-claude --test "show compression for this prompt"
        """
    )
    
    parser.add_argument(
        "prompt",
        help="The prompt or instruction for Claude Code"
    )
    
    parser.add_argument(
        "--file", "-f",
        help="Path to source file (for context)"
    )
    
    parser.add_argument(
        "--no-compress",
        action="store_true",
        help="Disable compression (passthrough mode)"
    )
    
    parser.add_argument(
        "--test",
        action="store_true",
        help="Test mode - show compression without executing"
    )
    
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Verbose output with metrics"
    )
    
    parser.add_argument(
        "--model",
        default="gpt-4",
        help="Model for token counting (default: gpt-4)"
    )
    
    args = parser.parse_args()
    
    # Setup logger
    logger = setup_logger("optimize-claude", log_level="DEBUG" if args.verbose else "INFO")
    
    # Initialize proxy
    proxy = ClaudeCodeProxy(
        enable_compression=not args.no_compress,
        llm_model=args.model
    )
    
    # Read file content if provided
    full_prompt = args.prompt
    if args.file:
        try:
            file_path = Path(args.file)
            if file_path.exists():
                file_content = file_path.read_text()
                full_prompt = f"{args.prompt}\n\nFile: {args.file}\n```python\n{file_content}\n```"
        except Exception as e:
            logger.error(f"Failed to read file: {e}")
    
    # Test mode - just show compression
    if args.test:
        compressed_prompt, metadata = proxy.process_input(full_prompt, args.file)
        
        print("\n" + "="*60)
        print("COMPRESSION TEST RESULTS")
        print("="*60)
        print(f"\nOriginal Tokens: {metadata.get('original_tokens', 'N/A')}")
        print(f"Compressed Tokens: {metadata.get('compressed_tokens', 'N/A')}")
        print(f"Compression Ratio: {metadata.get('compression_ratio', 0):.1f}%")
        print(f"Tier Used: {metadata.get('tier', 'N/A')}")
        print("\n" + "-"*60)
        print("COMPRESSED OUTPUT:")
        print("-"*60)
        print(compressed_prompt[:1000] + "..." if len(compressed_prompt) > 1000 else compressed_prompt)
        return
    
    # Execute with Claude
    result = proxy.execute_with_claude(full_prompt, args.file)
    print(result)

if __name__ == "__main__":
    main()