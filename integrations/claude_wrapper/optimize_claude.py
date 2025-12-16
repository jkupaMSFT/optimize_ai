#!/usr/bin/env python3
"""
Master CLI for Optimize Claude with all features
"""

import argparse
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent.parent.parent))

from optimize_ai.integrations.claude_wrapper.claude_proxy import ClaudeCodeProxy
from optimize_ai.integrations.claude_wrapper.post_processor import ClaudeEditApplicator

def main():
    parser = argparse.ArgumentParser(
        description="Optimize Claude - Complete wrapper with compression and edit application"
    )
    
    parser.add_argument("prompt", help="Prompt for Claude")
    parser.add_argument("--file", "-f", help="Source file")
    parser.add_argument("--apply-edits", action="store_true", 
                       help="Automatically apply suggested edits")
    parser.add_argument("--no-compress", action="store_true",
                       help="Disable compression")
    
    args = parser.parse_args()
    
    # Initialize components
    proxy = ClaudeCodeProxy(enable_compression=not args.no_compress)
    
    # Execute with Claude
    result = proxy.execute_with_claude(args.prompt, args.file)
    print(result)
    
    # Apply edits if requested
    if args.apply_edits and args.file:
        applicator = ClaudeEditApplicator()
        if applicator.apply_edits_to_file(args.file, result):
            print("\n✅ Edits applied successfully!")

if __name__ == "__main__":
    main()