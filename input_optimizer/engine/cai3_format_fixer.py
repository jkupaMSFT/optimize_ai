"""
CAI3-LITE Format Fixer - Converts invalid CAI3-LITE to valid format.
Handles common issues like:
- B0:, B1:, etc. -> B#0, B#1, etc.
- Missing P: section with pool definitions
- Invalid section identifiers
"""

import re
import logging
from typing import Dict, Set, List, Tuple


class CAI3FormatFixer:
    """Fixes common CAI3-LITE format violations to make content parseable."""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    def fix_format(self, cai3_content: str, mappings: Dict[str, str] = None) -> str:
        """
        Fix CAI3-LITE format issues to make it compliant.
        
        Args:
            cai3_content: Raw CAI3-LITE content that may have format issues
            mappings: Optional mappings from Claude that contain pool definitions
            
        Returns:
            Fixed CAI3-LITE content that should be valid
        """
        try:
            self.logger.info("Starting CAI3-LITE format fixing")
            
            # Step 1: Fix body section identifiers (B0: -> B#0, etc.)
            content = self._fix_body_identifiers(cai3_content)
            
            # Step 2: Extract referenced pools and create P: section
            content = self._fix_pool_section(content, mappings)
            
            # Step 3: Fix other section identifier issues
            content = self._fix_section_identifiers(content)
            
            # Step 4: Clean up formatting
            content = self._cleanup_formatting(content)
            
            self.logger.info("CAI3-LITE format fixing completed")
            return content
            
        except Exception as e:
            self.logger.error(f"Format fixing failed: {e}")
            return cai3_content  # Return original if fixing fails
    
    def _fix_body_identifiers(self, content: str) -> str:
        """Convert B0:, B1:, etc. to B#0, B#1, etc."""
        # Pattern to match B followed by number and colon
        pattern = r'^(B)(\d+)(:)'
        
        def replace_func(match):
            return f"B#{match.group(2)}:"
        
        return re.sub(pattern, replace_func, content, flags=re.MULTILINE)
    
    def _fix_pool_section(self, content: str, mappings: Dict[str, str] = None) -> str:
        """Create or fix the P: section with all referenced pools."""
        # Extract all pool references (p0, p1, p2, etc.)
        pool_refs = set(re.findall(r'\bp(\d+)\b', content))
        
        # Get existing P: section if any
        existing_pools = {}
        p_match = re.search(r'^P:\s*(.+?)(?=^[A-Z]:|^B#|^---|$)', content, re.MULTILINE | re.DOTALL)
        if p_match:
            existing_pools = self._parse_pool_assignments(p_match.group(1))
        
        # Build complete pool definitions
        all_pools = {}
        
        # Add pools from mappings (these have actual values)
        if mappings:
            for key, value in mappings.items():
                if key.startswith('p') and key[1:].isdigit():
                    all_pools[key] = value
        
        # Add existing pools
        all_pools.update(existing_pools)
        
        # Add placeholder pools for any missing references
        for pool_num in pool_refs:
            pool_key = f"p{pool_num}"
            if pool_key not in all_pools:
                # Create a reasonable default based on context
                all_pools[pool_key] = f'"param_{pool_num}"'
        
        if not all_pools:
            return content
        
        # Create the P: section
        pool_assignments = []
        for i in range(max(int(k[1:]) for k in all_pools.keys() if k.startswith('p')) + 1):
            pool_key = f"p{i}"
            if pool_key in all_pools:
                pool_assignments.append(f"{pool_key}={all_pools[pool_key]}")
        
        pool_section = "P:" + ",".join(pool_assignments)
        
        # Remove existing P: section if present
        content = re.sub(r'^P:\s*(.+?)(?=^[A-Z]:|^B#|^---|$)', '', content, flags=re.MULTILINE | re.DOTALL)
        
        # Insert P: section after imports but before first body or definition
        insertion_point = self._find_pool_insertion_point(content)
        
        lines = content.split('\n')
        lines.insert(insertion_point, pool_section)
        
        return '\n'.join(lines)
    
    def _parse_pool_assignments(self, pool_content: str) -> Dict[str, str]:
        """Parse pool assignments from P: section content."""
        pools = {}
        
        # Handle comma-separated assignments
        assignments = []
        current = ""
        in_string = False
        quote_char = None
        
        for char in pool_content:
            if char in ('"', "'") and not in_string:
                in_string = True
                quote_char = char
                current += char
            elif char == quote_char and in_string:
                in_string = False
                quote_char = None
                current += char
            elif char == ',' and not in_string:
                if current.strip():
                    assignments.append(current.strip())
                current = ""
            else:
                current += char
        
        if current.strip():
            assignments.append(current.strip())
        
        # Parse each assignment
        for assignment in assignments:
            if '=' in assignment:
                key, value = assignment.split('=', 1)
                pools[key.strip()] = value.strip()
        
        return pools
    
    def _find_pool_insertion_point(self, content: str) -> int:
        """Find the best place to insert the P: section."""
        lines = content.split('\n')
        
        # Look for the first non-header, non-import line
        for i, line in enumerate(lines):
            line = line.strip()
            if line and not line.startswith('#C3L') and not line.startswith('I:') and not line.startswith('---'):
                return i
        
        # If no good spot found, add at the end
        return len(lines)
    
    def _fix_section_identifiers(self, content: str) -> str:
        """Fix any remaining invalid section identifiers."""
        # This is where we could add more fixes for other invalid patterns
        # For now, the main issue is body identifiers which we already fixed
        return content
    
    def _cleanup_formatting(self, content: str) -> str:
        """Clean up formatting issues."""
        # Remove extra blank lines
        content = re.sub(r'\n\s*\n\s*\n', '\n\n', content)
        
        # Ensure proper line endings
        content = content.strip() + '\n'
        
        return content


def apply_cai3_format_fixes(cai3_content: str, mappings: Dict[str, str] = None) -> str:
    """Convenience function to apply CAI3-LITE format fixes."""
    fixer = CAI3FormatFixer()
    return fixer.fix_format(cai3_content, mappings)
