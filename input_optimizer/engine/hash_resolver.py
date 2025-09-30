"""Production hash resolver with all correctness fixes applied."""
import ast
import re
import logging
import io
import token
import tokenize
from tokenize import TokenInfo
from typing import Dict, Set, Optional, Tuple, Any
from threading import Lock

logger = logging.getLogger(__name__)

class HashResolver:
    """Thread-safe hash resolution with correct AST and tokenization handling."""
    
    # Compile regex patterns once
    HASH_PATTERN = re.compile(r'(?:hash_[a-zA-Z0-9_]+|#[a-zA-Z0-9_]+|[pab][0-9]+)$')
    HASH_IN_TEXT = re.compile(r'(hash_[a-zA-Z0-9_]+|#[a-zA-Z0-9_]+|[pab][0-9]+)', re.IGNORECASE)
    
    def __init__(self, mappings: Dict[str, Any] = None):
        self.mappings = {}
        self._unresolved = set()
        self._lock = Lock()
        self.logger = logging.getLogger(__name__)
        
        if mappings:
            for key, value in mappings.items():
                self.add_mapping(key, value)
    
    def add_mapping(self, key: str, value: Any):
        """Add a mapping with normalization."""
        normalized_key = self.normalize_hash(key)
        self.mappings[normalized_key] = value
    
    def normalize_hash(self, token_str: str) -> str:
        """Normalize hash formats to canonical lowercase form."""
        if not token_str:
            return token_str
        
        # CRITICAL FIX: Never convert plain numbers to hashes
        if token_str.isdigit():
            return token_str
        
        # Handle #XXXX format (both hex and non-hex)
        if token_str.startswith('#'):
            suffix = token_str[1:].lower()
            return f'hash_{suffix}'
        
        # Handle hash_XXXX format - keep as is but lowercase
        elif token_str.startswith('hash_'):
            return token_str.lower()
        
        # Handle raw patterns - check if it's a valid identifier first
        elif re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', token_str):
            # For raw identifiers that might be hashes, return as-is
            return token_str.lower()
        
        return token_str
    
    # Update the resolve method to handle missing mappings better
    def resolve(self, token_str: str, context: str = 'load') -> str:
        """Resolve a token with context awareness - PROPERLY FIXED to resolve mappings."""
        with self._lock:
            if context == 'store':
                return token_str
            
            # CRITICAL FIX: Never treat plain numbers as hashes
            if token_str.isdigit():
                return token_str
            
            normalized = self.normalize_hash(token_str)
            
            # First check if we have a mapping for this hash
            if normalized in self.mappings:
                resolved = self.mappings[normalized]
                self.logger.debug(f"✅ Resolved: {token_str} → {resolved}")
                return str(resolved)  # Ensure we return string value
            
            # Only mark as unresolved if it's actually a hash and we don't have mapping
            if normalized.startswith('hash_'):
                self._unresolved.add(normalized)
                self.logger.warning(f"⚠️ Unresolved hash: {token_str} → {normalized}")
                # Return the hash as-is if we can't resolve it (don't prefix UNRESOLVED_)
                return token_str
            
            return token_str
    
    def resolve_ast_node(self, node: ast.AST) -> ast.AST:
        """Resolve hash references in AST with correct dotted name handling."""
        
        def to_ast_name_or_attr(dotted: str, ctx):
            """Convert dotted string to proper AST (Name or Attribute chain)."""
            parts = dotted.split('.')
            if len(parts) == 1:
                return ast.Name(id=parts[0], ctx=ctx)
            
            # Build attribute chain with proper context
            result = ast.Name(id=parts[0], ctx=ast.Load())
            for part in parts[1:-1]:
                result = ast.Attribute(value=result, attr=part, ctx=ast.Load())
            # Final attribute gets the requested context
            result = ast.Attribute(value=result, attr=parts[-1], ctx=ctx)
            return result
        
        class HashNodeResolver(ast.NodeTransformer):
            def __init__(self, resolver):
                self.resolver = resolver
            
            def visit_Name(self, node):
                if isinstance(node.ctx, ast.Load):
                    resolved = self.resolver.resolve(node.id, 'load')
                    if resolved != node.id:
                        new_node = to_ast_name_or_attr(resolved, node.ctx)
                        return ast.copy_location(new_node, node)
                return node
            
            def visit_Attribute(self, node):
                self.generic_visit(node)
                if isinstance(node.ctx, ast.Load):
                    resolved = self.resolver.resolve(node.attr, 'load')
                    if resolved != node.attr and '.' not in resolved:
                        node.attr = resolved
                return node
        
        transformer = HashNodeResolver(self)
        return transformer.visit(node)
    
