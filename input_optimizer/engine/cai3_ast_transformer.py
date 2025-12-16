"""
CAI3 AST Transformer - Fixed version
Provides ResolutionTransformer with correct AST Constant constructor.
"""

import ast
from typing import Dict, Any, Optional


class ResolutionTransformer(ast.NodeTransformer):
    """Fixed AST transformer with correct Constant constructor."""
    
    def __init__(self, pools: Dict[str, Any], aliases: Dict[str, str], resolver):
        self.pools = pools or {}
        self.aliases = aliases or {}
        self.resolver = resolver
    
    def visit_Name(self, node: ast.Name):
        """Resolve Name nodes in Load context only."""
        if not isinstance(node.ctx, ast.Load):
            return node
        
        # 1. Check pools - replace with constant (FIXED)
        if node.id in self.pools:
            value = self.pools[node.id]
            # FIX: Use value= keyword argument
            return ast.copy_location(ast.Constant(value=value), node)
        
        # 2. Check aliases - may be dotted
        if node.id in self.aliases:
            replacement = self.aliases[node.id]
            return ast.copy_location(
                self._dotted_to_ast(replacement, node.ctx), 
                node
            )
        
        # 3. Apply hash resolution - may be dotted
        if self.resolver:
            resolved = self.resolver.resolve(node.id, 'load')
            if resolved != node.id:
                return ast.copy_location(
                    self._dotted_to_ast(resolved, node.ctx),
                    node
                )
        
        return node
    
    def _dotted_to_ast(self, dotted: str, ctx) -> ast.AST:
        """Convert dotted string to AST attribute chain."""
        parts = dotted.split('.')
        if len(parts) == 1:
            return ast.Name(id=parts[0], ctx=ctx)
        
        # Build attribute chain
        node = ast.Name(id=parts[0], ctx=ast.Load())
        for part in parts[1:-1]:
            node = ast.Attribute(value=node, attr=part, ctx=ast.Load())
        
        # Last attribute gets the requested context
        node = ast.Attribute(value=node, attr=parts[-1], ctx=ctx)
        return node
    
    def visit_Import(self, node: ast.Import):
        """Resolve import module names."""
        for alias in node.names:
            # Resolve first segment of dotted imports
            parts = alias.name.split('.')
            if self.resolver and parts[0]:
                resolved = self.resolver.resolve(parts[0], 'load')
                parts[0] = resolved
            alias.name = '.'.join(parts)
        return node
    
    def visit_ImportFrom(self, node: ast.ImportFrom):
        """Resolve from-import modules and names."""
        # Resolve module
        if node.module:
            parts = node.module.split('.')
            if self.resolver and parts[0]:
                resolved = self.resolver.resolve(parts[0], 'load')
                parts[0] = resolved
            node.module = '.'.join(parts)
        
        # Resolve imported names
        for alias in node.names:
            if self.resolver:
                resolved = self.resolver.resolve(alias.name, 'load')
                alias.name = resolved
        
        return node
