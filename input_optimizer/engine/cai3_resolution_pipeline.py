"""
Unified resolution pipeline for CAI3 translation.
Integrates hash resolution, pool resolution, and AST transformation.
"""

import re
import ast
from typing import Dict, Any, List, Optional
from .hash_resolver import HashResolver
import logging

class CAI3ResolutionPipeline:
    """Unified pipeline for resolving all CAI3 references."""
    
    def __init__(self, hash_mappings: Dict[str, str], pools: Dict[str, Any]):
        self.hash_resolver = HashResolver(hash_mappings)
        self.pools = pools
        self.logger = logging.getLogger(__name__)
    
    def resolve_content(self, content: str) -> str:
        """Apply all resolutions in the correct order."""
        # Step 1: Resolve hash references
        content = self._resolve_hashes(content)
        
        # Step 2: Resolve pool references
        content = self._resolve_pools(content)
        
        # Step 3: Fix CAI3 syntax
        content = self._fix_cai3_syntax(content)
        
        return content
    
    def _resolve_hashes(self, content: str) -> str:
        """Resolve all hash references in content."""
        # Pattern to match hash references
        hash_pattern = r'\b(hash_[a-zA-Z0-9_]+)\b'
        
        def replace_hash(match):
            hash_ref = match.group(1)
            resolved = self.hash_resolver.resolve(hash_ref, 'load')
            self.logger.debug(f"Resolved {hash_ref} -> {resolved}")
            return resolved
        
        return re.sub(hash_pattern, replace_hash, content)
    
    def _resolve_pools(self, content: str) -> str:
        """Resolve all pool references in content."""
        for pool_id, pool_value in self.pools.items():
            # Create pattern for this pool reference
            pattern = rf'\b{pool_id}\b'
            
            # Determine replacement value
            if isinstance(pool_value, str):
                # For strings, ensure they're properly quoted
                if pool_value.startswith('"') and pool_value.endswith('"'):
                    replacement = pool_value
                elif pool_value.startswith("'") and pool_value.endswith("'"):
                    replacement = pool_value
                else:
                    replacement = f'"{pool_value}"'
            else:
                replacement = str(pool_value)
            
            # Apply replacement
            content = re.sub(pattern, replacement, content)
            self.logger.debug(f"Resolved {pool_id} -> {replacement}")
        
        return content
    
    def _fix_cai3_syntax(self, content: str) -> str:
        """Fix common CAI3 syntax issues."""
        fixes = [
            # Fix malformed dictionaries
            (r'{([^:]+):([^,}]+):([^}]+)}', r'{\1: \2, "error": \3}'),
            
            # Fix function calls with colon syntax
            (r'(\w+)\(([^:]+):([^)]+)\)', r'\1(\2, \3)'),
            
            # Fix numeric dictionary keys
            (r'{([0-9.e-]+):([^,}]+)}', r'{"\1": \2}'),
            
            # Fix if statements with malformed conditions
            (r'if\s+0}', 'if False:'),
            
            # Fix compressed for loops
            (r'for\s+(\w+)\s+in\s+(\w+):(\w+)=', r'for \1 in \2:\n    \3 = '),
            
            # Fix .replace with wrong quotes
            (r"\.replace\('([^']+)','([^']+)'\)", r'.replace("\1", "\2")'),
        ]
        
        for pattern, replacement in fixes:
            content = re.sub(pattern, replacement, content)
        
        return content
    
    def resolve_ast_node(self, node: ast.AST) -> ast.AST:
        """Resolve references in an AST node."""
        from .cai3_ast_transformer import ResolutionTransformer
        
        transformer = ResolutionTransformer(
            self.pools, 
            {},  # chain aliases
            self.hash_resolver
        )
        
        return transformer.visit(node)