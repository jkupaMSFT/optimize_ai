"""
Post-processor for applying Claude's suggested edits
"""

import re
import difflib
from pathlib import Path
from typing import List, Tuple, Optional
import logging

class ClaudeEditApplicator:
    """
    Applies edits suggested by Claude to source files
    """
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    def extract_code_blocks(self, claude_output: str) -> List[Tuple[str, str]]:
        """
        Extract code blocks from Claude's output
        
        Returns:
            List of (language, code) tuples
        """
        pattern = r'```(\w+)?\n(.*?)```'
        matches = re.findall(pattern, claude_output, re.DOTALL)
        return [(lang or 'python', code.strip()) for lang, code in matches]
    
    def find_edit_instructions(self, claude_output: str) -> List[dict]:
        """
        Parse Claude's edit instructions
        
        Returns:
            List of edit instructions
        """
        edits = []
        
        # Look for replacement patterns
        replace_pattern = r'Replace `([^`]+)` with `([^`]+)`'
        for match in re.finditer(replace_pattern, claude_output):
            edits.append({
                'type': 'replace',
                'old': match.group(1),
                'new': match.group(2)
            })
        
        # Look for insertion patterns
        insert_pattern = r'Add the following (?:after|before) ([^:]+):'
        for match in re.finditer(insert_pattern, claude_output):
            edits.append({
                'type': 'insert',
                'location': match.group(1)
            })
        
        return edits
    
    def apply_edits_to_file(self, 
                           file_path: str, 
                           claude_output: str,
                           backup: bool = True) -> bool:
        """
        Apply Claude's suggested edits to a file
        
        Args:
            file_path: Path to the file to edit
            claude_output: Claude's response containing edits
            backup: Whether to create a backup
            
        Returns:
            True if edits were applied successfully
        """
        try:
            path = Path(file_path)
            if not path.exists():
                self.logger.error(f"File not found: {file_path}")
                return False
            
            # Read original content
            original_content = path.read_text()
            
            # Create backup if requested
            if backup:
                backup_path = path.with_suffix(path.suffix + '.bak')
                backup_path.write_text(original_content)
                self.logger.info(f"Created backup: {backup_path}")
            
            # Extract code blocks from Claude's response
            code_blocks = self.extract_code_blocks(claude_output)
            
            if not code_blocks:
                self.logger.warning("No code blocks found in Claude's response")
                return False
            
            # Use the first Python code block as the new content
            new_content = None
            for lang, code in code_blocks:
                if lang in ['python', 'py', '']:
                    new_content = code
                    break
            
            if new_content:
                # Apply the new content
                path.write_text(new_content)
                self.logger.info(f"Applied edits to {file_path}")
                
                # Show diff
                self._show_diff(original_content, new_content)
                return True
            
            return False
            
        except Exception as e:
            self.logger.error(f"Failed to apply edits: {e}")
            return False
    
    def _show_diff(self, original: str, new: str):
        """Show diff between original and new content"""
        diff = difflib.unified_diff(
            original.splitlines(keepends=True),
            new.splitlines(keepends=True),
            fromfile='original',
            tofile='modified'
        )
        
        print("\n" + "="*60)
        print("CHANGES APPLIED:")
        print("="*60)
        for line in diff:
            if line.startswith('+'):
                print(f"\033[92m{line}\033[0m", end='')  # Green
            elif line.startswith('-'):
                print(f"\033[91m{line}\033[0m", end='')  # Red
            else:
                print(line, end='')