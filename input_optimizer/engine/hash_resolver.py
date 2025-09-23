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
    
    def resolve_imports_ast(self, code: str) -> str:
        """Resolve imports using AST with correct dotted name handling."""
        try:
            tree = ast.parse(code)
            
            class ImportResolver(ast.NodeTransformer):
                def __init__(self, resolver):
                    self.resolver = resolver
                    self.modified = False
                
                def visit_Import(self, node):
                    for alias in node.names:
                        new_name = self._resolve_dotted(alias.name)
                        if new_name != alias.name:
                            alias.name = new_name
                            self.modified = True
                    return node
                
                def visit_ImportFrom(self, node):
                    if node.module:
                        new_module = self._resolve_dotted(node.module)
                        if new_module != node.module:
                            node.module = new_module
                            self.modified = True
                    
                    for alias in node.names:
                        new_name = self.resolver.resolve(alias.name, 'load')
                        if new_name != alias.name:
                            alias.name = new_name
                            self.modified = True
                    return node
                
                def _resolve_dotted(self, name: str) -> str:
                    """Resolve first segment of dotted name."""
                    parts = name.split('.')
                    parts[0] = self.resolver.resolve(parts[0], 'load')
                    return '.'.join(parts)
            
            transformer = ImportResolver(self)
            tree = transformer.visit(tree)
            
            if transformer.modified:
                return ast.unparse(tree)
            return code
            
        except SyntaxError:
            # Fallback to robust regex
            return self.resolve_imports_regex(code)
    
    def resolve_imports_regex(self, code: str) -> str:
        """Robust regex-based import resolution that preserves indentation."""
        def fix_first_segment(name: str) -> str:
            """Resolve first segment of dotted import."""
            head, *tail = name.split('.')
            head = self.resolve(head, 'load')
            return '.'.join([head] + tail) if tail else head
        
        out_lines = []
        for line in code.splitlines():
            # Handle import statements with preserved indentation
            m_import = re.match(r'^(\s*)import\s+(.+)$', line)
            if m_import:
                indent, rest = m_import.groups()
                parts = []
                for part in rest.split(','):
                    part = part.strip()
                    if ' as ' in part:
                        name, alias = part.split(' as ', 1)
                        parts.append(f"{fix_first_segment(name.strip())} as {alias.strip()}")
                    else:
                        parts.append(fix_first_segment(part))
                out_lines.append(f"{indent}import " + ', '.join(parts))
                continue
            
            # Handle from imports with preserved indentation
            m_from = re.match(r'^(\s*)from\s+(\S+)\s+import\s+(.+)$', line)
            if m_from:
                indent, module, names = m_from.groups()
                module = fix_first_segment(module)
                name_parts = []
                for part in names.split(','):
                    part = part.strip()
                    if ' as ' in part:
                        name, alias = part.split(' as ', 1)
                        name_parts.append(f"{self.resolve(name.strip(), 'load')} as {alias.strip()}")
                    else:
                        name_parts.append(self.resolve(part, 'load'))
                out_lines.append(f"{indent}from {module} import " + ', '.join(name_parts))
                continue
            
            out_lines.append(line)
        
        return '\n'.join(out_lines)
    
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
    
    def validate_resolution(self, code: str) -> Tuple[bool, Set[str]]:
        """Validate using proper tokenization, skipping strings/comments."""
        unresolved = set()
        
        try:
            tokens = tokenize.generate_tokens(io.StringIO(code).readline)
            for tok in tokens:
                # Only check NAME and OP tokens (OP for # prefix)
                if tok.type in (token.NAME, token.OP):
                    if self.HASH_PATTERN.match(tok.string):
                        # Verify it's truly unresolved
                        normalized = self.normalize_hash(tok.string)
                        if normalized not in self.mappings:
                            unresolved.add(tok.string)
        except tokenize.TokenError as e:
            # Continue processing on partial tokenization
            self.logger.debug(f"Tokenization error (continuing): {e}")
        
        return len(unresolved) == 0, unresolved
    
    def resolve_in_python_code(self, code: str) -> str:
        """Resolve hashes in generated Python code using proper tokenization."""
        try:
            tokens = list(tokenize.generate_tokens(io.StringIO(code).readline))
            out = []
            
            for tok in tokens:
                if tok.type == token.NAME and self.HASH_PATTERN.match(tok.string):
                    resolved = self.resolve(tok.string, 'load')
                    if resolved != tok.string:
                        # Create new TokenInfo with resolved string
                        tok = TokenInfo(tok.type, resolved, tok.start, tok.end, tok.line)
                out.append(tok)
            
            return tokenize.untokenize(out)
            
        except tokenize.TokenError:
            self.logger.warning("Failed to tokenize for resolution, returning original")
            return code
    
    def get_unresolved(self) -> Set[str]:
        """Get all unresolved hashes."""
        with self._lock:
            return self._unresolved.copy()