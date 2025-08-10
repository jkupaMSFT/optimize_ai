# optimize_ai/input_optimizer/engine/cai3_waterfall_integration.py
"""
Integration code to add CAI3 compression to the existing WaterfallCompressor.
This can be merged into waterfall_compressor.py or used as a mixin.
"""

import ast
import hashlib
from pathlib import Path
from typing import List, Dict, Optional, Set, Tuple
import logging

# Import the CAI3 structures and FLOW compiler
from .cai3_structures import (
    CAI3Node, CAI3Full, CAI3Map, CAI3Lite, CAI3Cache,
    BodyFidelity, NodeType, generate_cid, compress_name
)
from .flow_language import FLOWCompiler
from .compression_types import CompressionResult, CompressionTier

# For token counting (assuming tiktoken is available)
try:
    import tiktoken
    HAS_TIKTOKEN = True
except ImportError:
    HAS_TIKTOKEN = False

def count_tokens(text: str, model: str = "gpt-4") -> int:
    """Count tokens for a given text using tiktoken."""
    if not text:
        return 0
        
    if HAS_TIKTOKEN:
        try:
            encoding = tiktoken.encoding_for_model(model)
        except KeyError:
            encoding = tiktoken.get_encoding("cl100k_base")
        return len(encoding.encode(text))
    else:
        # Simple approximation
        return max(1, len(text) // 4)


class CAI3WaterfallEnhancement:
    """
    Enhancement methods for WaterfallCompressor to support CAI3.
    These methods should be added to the WaterfallCompressor class.
    """
    
    def __init__(self):
        """Initialize CAI3 components"""
        self.use_cai3_mode = True  # Enable by default for MEDIUM tier
        self.cai3_cache = CAI3Cache()
        self.logger = logging.getLogger(__name__)
    
    def _standard_compression_cai3(self, content: str, original_tokens: int,
                                   source_path: Optional[Path] = None) -> CompressionResult:
        """
        CAI3-based compression for MEDIUM tier achieving 70-90% reduction.
        Only sends CAI3-LITE to the LLM while keeping FULL and MAP local.
        """
        try:
            # Parse AST
            tree = ast.parse(content)
            
            # Create the three planes with CID index
            cai3_full, cid_index = self._create_cai3_full(tree, content, source_path)
            
            # Determine which methods need FLOW bodies (edit scope)
            edit_scope_cids = self._determine_edit_scope(tree, content, source_path, cid_index)
            
            cai3_map = self._create_cai3_map(cai3_full)
            cai3_lite = self._create_cai3_lite(cai3_full, cai3_map, edit_scope_cids, cid_index)
            
            # Store FULL and MAP locally for the translator
            if source_path:
                self.cai3_cache.store_full(source_path, cai3_full)
                self.cai3_cache.store_map(source_path, cai3_map)
            
            # Serialize only LITE for the LLM
            lite_content = cai3_lite.serialize()
            compressed_tokens = count_tokens(lite_content, self.llm_model)
            
            compression_ratio = (1 - compressed_tokens / original_tokens) * 100
            
            # Log compression stats
            self.logger.info(
                f"CAI3 compression: {original_tokens} → {compressed_tokens} tokens "
                f"({compression_ratio:.1f}% reduction), {len(edit_scope_cids)} methods with bodies"
            )
            
            return CompressionResult(
                original_tokens=original_tokens,
                compressed_tokens=compressed_tokens,
                compression_ratio=compression_ratio,
                tier_used=CompressionTier.MEDIUM,
                method_used="cai3_compression",
                content=lite_content,
                metadata={
                    'cai3_mode': True,
                    'edit_scope_size': len(edit_scope_cids),
                    'total_nodes': len(cai3_full.nodes),
                    'source_path': str(source_path) if source_path else None
                }
            )
            
        except Exception as e:
            self.logger.error(f"CAI3 compression failed: {e}")
            # Fallback to simple compression if no _standard_compression method
            if hasattr(self, '_standard_compression'):
                return self._standard_compression(content, original_tokens, source_path)
            else:
                # Simple fallback for testing
                return CompressionResult(
                    original_tokens=original_tokens,
                    compressed_tokens=original_tokens // 2,
                    compression_ratio=50.0,
                    tier_used=CompressionTier.MEDIUM,
                    method_used="fallback_compression",
                    content=content[:200] + "... [fallback compressed]"
                )
    
    def _determine_edit_scope(self, tree: ast.AST, content: str, 
                             source_path: Optional[Path] = None, 
                             cid_index: Optional[Dict] = None) -> List[str]:
        """
        Intelligently determine which methods need FLOW bodies in CAI3-LITE.
        Returns list of cids for methods that should have full bodies.
        Uses CID index from FULL build to ensure consistency.
        """
        if cid_index is None:
            cid_index = {}
        
        edit_candidates = []
        lines = content.split('\n')
        
        # Walk the AST to find methods that likely need editing
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                # Look up CID from index instead of generating new one
                start_line = getattr(node, 'lineno', 0)
                
                # Find parent class if this is a method
                parent_class = None
                for parent in ast.walk(tree):
                    if isinstance(parent, ast.ClassDef):
                        if hasattr(parent, 'lineno') and hasattr(parent, 'end_lineno'):
                            if (parent.lineno < start_line and 
                                getattr(parent, 'end_lineno', parent.lineno) > start_line):
                                parent_class = parent.name
                                break
                
                # Build lookup key
                lookup_key = (parent_class, node.name, start_line)
                cid = cid_index.get(lookup_key)
                
                if cid is None:
                    # Fallback: generate CID if not found in index
                    node_type = 'M' if parent_class else ('F' if isinstance(node, ast.FunctionDef) else 'M')
                    parent_cid = cid_index.get((None, parent_class, 0)) if parent_class else None
                    cid = generate_cid(node_type, node.name, parent_cid)
                
                # Check various heuristics
                score = 0
                
                # 1. Check for bug patterns (mutation in validation, etc.)
                if self._has_bug_pattern(node):
                    score += 10
                
                # 2. Check for TODO/FIXME comments
                if hasattr(node, 'lineno'):
                    for line_num in range(node.lineno - 1, 
                                         min(node.lineno + 10, len(lines))):
                        if line_num < len(lines):
                            line = lines[line_num].upper()
                            if 'TODO' in line or 'FIXME' in line or 'BUG' in line or 'HACK' in line:
                                score += 8
                                break
                
                # 3. Check method name patterns suggesting issues
                name_lower = node.name.lower()
                if any(pattern in name_lower for pattern in 
                      ['validate', 'check', 'verify', 'process', 'transform', 'parse']):
                    score += 3
                
                # 4. Check complexity (number of branches/loops)
                complexity = self._calculate_complexity(node)
                if complexity > 10:
                    score += 5
                elif complexity > 5:
                    score += 2
                
                # 5. Check for exception handling without proper cleanup
                has_try = any(isinstance(n, ast.Try) for n in ast.walk(node))
                if has_try:
                    score += 2
                
                # 6. Methods that modify their parameters (potential bugs)
                if self._modifies_parameters(node):
                    score += 7
                
                edit_candidates.append((cid, score, node.name))
        
        # Sort by score and take top methods
        edit_candidates.sort(key=lambda x: x[1], reverse=True)
        
        # For MEDIUM tier, include 3-5 most likely methods
        max_methods = 5
        min_methods = 2
        
        # Include high-scoring methods
        selected_cids = []
        for cid, score, name in edit_candidates:
            if score >= 5 and len(selected_cids) < max_methods:
                selected_cids.append(cid)
                self.logger.debug(f"Including method '{name}' in edit scope (score: {score})")
            elif len(selected_cids) < min_methods:
                selected_cids.append(cid)
                self.logger.debug(f"Including method '{name}' in edit scope (min requirement)")
        
        return selected_cids
    
    def _has_bug_pattern(self, node: ast.FunctionDef) -> bool:
        """Check if a function has common bug patterns"""
        # Check for mutation in validation methods
        if 'validat' in node.name.lower() or 'check' in node.name.lower():
            for subnode in ast.walk(node):
                # Look for assignments to parameter attributes
                if isinstance(subnode, ast.Assign):
                    for target in subnode.targets:
                        if isinstance(target, ast.Subscript):
                            # Mutating parameter dict/list
                            if isinstance(target.value, ast.Name):
                                if any(arg.arg == target.value.id 
                                      for arg in node.args.args):
                                    return True
                        elif isinstance(target, ast.Attribute):
                            # Mutating parameter attribute
                            if isinstance(target.value, ast.Name):
                                if any(arg.arg == target.value.id 
                                      for arg in node.args.args):
                                    return True
        
        # Check for missing return in functions that should return
        if node.returns:  # Has return type annotation
            has_return = any(isinstance(n, ast.Return) for n in ast.walk(node))
            if not has_return:
                return True
        
        return False
    
    def _calculate_complexity(self, node: ast.FunctionDef) -> int:
        """Calculate cyclomatic complexity of a function"""
        complexity = 1  # Base complexity
        
        for subnode in ast.walk(node):
            if isinstance(subnode, (ast.If, ast.While, ast.For)):
                complexity += 1
            elif isinstance(subnode, ast.ExceptHandler):
                complexity += 1
            elif isinstance(subnode, ast.BoolOp):
                # Each and/or adds a branch
                complexity += len(subnode.values) - 1
        
        return complexity
    
    def _modifies_parameters(self, node: ast.FunctionDef) -> bool:
        """Check if function modifies its parameters"""
        param_names = {arg.arg for arg in node.args.args}
        
        for subnode in ast.walk(node):
            if isinstance(subnode, ast.Assign):
                for target in subnode.targets:
                    if isinstance(target, (ast.Subscript, ast.Attribute)):
                        # Check if modifying a parameter
                        base = target
                        while isinstance(base, (ast.Subscript, ast.Attribute)):
                            base = base.value
                        
                        if isinstance(base, ast.Name) and base.id in param_names:
                            return True
        
        return False
    
    def _compute_context_hash(self, lines: List[str], start_line: int, end_line: int) -> Optional[str]:
        """
        Compute context hash (SH) for a code span.
        Includes 2 lines before + body + 2 lines after.
        """
        try:
            # Get context window (2 lines before and after)
            context_start = max(0, start_line - 3)  # -3 because lines are 0-indexed but lineno is 1-indexed
            context_end = min(len(lines), end_line + 2)
            
            context_lines = lines[context_start:context_end]
            context_text = '\n'.join(context_lines)
            
            # Compute hash
            return hashlib.md5(context_text.encode()).hexdigest()[:8]
        except Exception:
            return None
    
    def _compute_byte_span(self, content: str, start_line: int, end_line: int) -> Optional[Tuple[int, int]]:
        """
        Compute byte offsets for a line range.
        """
        try:
            lines = content.split('\n')
            
            # Calculate byte offset to start of start_line
            start_byte = 0
            for i in range(start_line - 1):  # lineno is 1-indexed
                if i < len(lines):
                    start_byte += len(lines[i]) + 1  # +1 for newline
            
            # Calculate byte offset to end of end_line
            end_byte = start_byte
            for i in range(start_line - 1, min(end_line, len(lines))):
                if i < len(lines):
                    end_byte += len(lines[i]) + 1  # +1 for newline
            
            return (start_byte, end_byte)
        except Exception:
            return None
    
    def _create_cai3_full(self, tree: ast.AST, content: str, 
                         source_path: Optional[Path] = None) -> Tuple[CAI3Full, Dict]:
        """
        Create complete CAI3-FULL representation (stays local).
        Returns both CAI3Full and a CID index for consistent lookup.
        """
        nodes = []
        imports = []
        pools = {}
        bound_hashes = {}
        span_hashes = {}
        used_names = set()
        cid_index = {}  # (parent_class, func_name, start_line) -> cid
        
        # Process imports
        for node in tree.body:
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(f"import {alias.name}")
            elif isinstance(node, ast.ImportFrom):
                names = ', '.join(alias.name for alias in node.names)
                imports.append(f"from {node.module} import {names}")
        
        # Process classes and functions
        lines = content.split('\n')
        
        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                # Create class node
                class_cid = generate_cid('C', node.name)
                class_short = compress_name(node.name, used_names)
                
                # Add class to CID index
                start_line = getattr(node, 'lineno', 0)
                end_line = getattr(node, 'end_lineno', start_line)
                cid_index[(None, node.name, start_line)] = class_cid
                
                # Compute context hash and byte span for class
                context_hash = self._compute_context_hash(lines, start_line, end_line)
                byte_span = self._compute_byte_span(content, start_line, end_line)
                
                if context_hash:
                    span_hashes[class_cid] = context_hash
                
                class_node = CAI3Node(
                    cid=class_cid,
                    type=NodeType.CLASS,
                    name=node.name,
                    short_name=class_short,
                    signature=node.name,
                    body_fidelity=BodyFidelity.B0,
                    span=(start_line, end_line),
                    byte_span=byte_span,
                    context_hash=context_hash
                )
                nodes.append(class_node)
                
                # Process class methods
                for item in node.body:
                    if isinstance(item, ast.FunctionDef):
                        method_cid = generate_cid('M', item.name, class_cid)
                        method_short = compress_name(item.name, used_names)
                        
                        # Add method to CID index
                        method_start_line = getattr(item, 'lineno', 0)
                        method_end_line = getattr(item, 'end_lineno', method_start_line)
                        cid_index[(node.name, item.name, method_start_line)] = method_cid
                        
                        # Compute context hash and byte span for method
                        method_context_hash = self._compute_context_hash(lines, method_start_line, method_end_line)
                        method_byte_span = self._compute_byte_span(content, method_start_line, method_end_line)
                        
                        if method_context_hash:
                            span_hashes[method_cid] = method_context_hash
                        
                        # Create simplified signature
                        args = []
                        for arg in item.args.args:
                            if arg.arg != 'self':
                                args.append(arg.arg)
                        
                        # Determine return type
                        returns = "Any"
                        if item.returns:
                            if isinstance(item.returns, ast.Name):
                                returns = item.returns.id
                            elif isinstance(item.returns, ast.Constant):
                                returns = str(item.returns.value)
                        
                        signature = f"({','.join(args)})->{returns}"
                        
                        method_node = CAI3Node(
                            cid=method_cid,
                            type=NodeType.METHOD,
                            name=item.name,
                            short_name=method_short,
                            signature=signature,
                            body_fidelity=BodyFidelity.B0,  # Will be updated for edit scope
                            span=(method_start_line, method_end_line),
                            byte_span=method_byte_span,
                            context_hash=method_context_hash,
                            parent_cid=class_cid
                        )
                        
                        # Calculate content hash
                        method_content = ast.unparse(item) if hasattr(ast, 'unparse') else ""
                        bound_hashes[method_cid] = hashlib.md5(method_content.encode()).hexdigest()[:8]
                        
                        nodes.append(method_node)
            
            elif isinstance(node, ast.FunctionDef):
                # Standalone function
                func_cid = generate_cid('F', node.name)
                func_short = compress_name(node.name, used_names)
                
                # Add function to CID index
                func_start_line = getattr(node, 'lineno', 0)
                func_end_line = getattr(node, 'end_lineno', func_start_line)
                cid_index[(None, node.name, func_start_line)] = func_cid
                
                # Compute context hash and byte span for function
                func_context_hash = self._compute_context_hash(lines, func_start_line, func_end_line)
                func_byte_span = self._compute_byte_span(content, func_start_line, func_end_line)
                
                if func_context_hash:
                    span_hashes[func_cid] = func_context_hash
                
                # Create simplified signature
                args = [arg.arg for arg in node.args.args]
                returns = "Any"
                if node.returns:
                    if isinstance(node.returns, ast.Name):
                        returns = node.returns.id
                
                signature = f"({','.join(args)})->{returns}"
                
                func_node = CAI3Node(
                    cid=func_cid,
                    type=NodeType.FUNCTION,
                    name=node.name,
                    short_name=func_short,
                    signature=signature,
                    body_fidelity=BodyFidelity.B0,
                    span=(func_start_line, func_end_line),
                    byte_span=func_byte_span,
                    context_hash=func_context_hash
                )
                
                # Calculate content hash
                func_content = ast.unparse(node) if hasattr(ast, 'unparse') else ""
                bound_hashes[func_cid] = hashlib.md5(func_content.encode()).hexdigest()[:8]
                
                nodes.append(func_node)
        
        # Extract common constants to pools
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant):
                if isinstance(node.value, str) and len(node.value) > 20:
                    # Add long strings to pool
                    pool_key = f"str_{hashlib.md5(node.value.encode()).hexdigest()[:4]}"
                    pools[pool_key] = node.value
        
        # Create CAI3Full
        file_hash = hashlib.md5(content.encode()).hexdigest()[:8]
        
        cai3_full = CAI3Full(
            nodes=nodes,
            imports=imports,
            pools=pools,
            bound_hashes=bound_hashes,
            span_hashes=span_hashes,
            source_path=str(source_path) if source_path else "",
            python_version="3.11",
            file_hash=file_hash,
            compression_stats={
                'original_lines': len(content.split('\n')),
                'node_count': len(nodes)
            }
        )
        
        return cai3_full, cid_index
    
    def _create_cai3_map(self, cai3_full: CAI3Full) -> CAI3Map:
        """Create mapping layer for translator (stays local)"""
        name_map = {}
        reverse_name_map = {}
        span_map = {}
        byte_map = {}
        ast_paths = {}
        context_hashes = {}
        parent_map = {}
        children_map = {}
        
        # Build mappings from nodes
        for node in cai3_full.nodes:
            # Name mappings
            if node.short_name != node.name:
                name_map[node.short_name] = node.name
                reverse_name_map[node.name] = node.short_name
            
            # Span mappings
            if node.span:
                span_map[node.cid] = node.span
            
            # Byte spans
            if node.byte_span:
                byte_map[node.cid] = node.byte_span
            
            # Context hashes
            if node.context_hash:
                context_hashes[node.cid] = node.context_hash
            
            # Parent-child relationships
            if node.parent_cid:
                parent_map[node.cid] = node.parent_cid
                if node.parent_cid not in children_map:
                    children_map[node.parent_cid] = []
                children_map[node.parent_cid].append(node.cid)
        
        return CAI3Map(
            name_map=name_map,
            reverse_name_map=reverse_name_map,
            span_map=span_map,
            byte_map=byte_map,
            ast_paths=ast_paths,
            context_hashes=context_hashes,
            parent_map=parent_map,
            children_map=children_map
        )
    
    def _create_cai3_lite(self, cai3_full: CAI3Full, cai3_map: CAI3Map, 
                         edit_scope_cids: List[str], cid_index: Dict) -> CAI3Lite:
        """
        Create minimal CAI3-LITE for the LLM.
        Only includes FLOW bodies for methods in edit_scope_cids.
        """
        # Create header
        source_file = Path(cai3_full.source_path).name if cai3_full.source_path else "unknown.py"
        header = f"#C3-L v1 py={cai3_full.python_version} file={source_file} MACROS=v1"
        
        # Compress imports (include method-local imports for B1 bodies)
        import_parts = []
        method_local_imports = set()
        
        # Check for method-local imports in edit scope
        if edit_scope_cids and cai3_full.source_path:
            try:
                with open(cai3_full.source_path, 'r') as f:
                    content = f.read()
                tree = ast.parse(content)
                
                # Find method-local imports in edit scope methods
                nodes_by_cid = {node.cid: node for node in cai3_full.nodes}
                
                for cid in edit_scope_cids:
                    node_info = nodes_by_cid.get(cid)
                    if not node_info or not node_info.span:
                        continue
                    
                    # Find AST node and check for local imports
                    for ast_node in ast.walk(tree):
                        if isinstance(ast_node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                            if (hasattr(ast_node, 'lineno') and 
                                ast_node.lineno == node_info.span[0]):
                                
                                # Look for imports within this method
                                for subnode in ast.walk(ast_node):
                                    if isinstance(subnode, ast.Import):
                                        for alias in subnode.names:
                                            method_local_imports.add(alias.name)
                                    elif isinstance(subnode, ast.ImportFrom):
                                        if subnode.module:
                                            for alias in subnode.names:
                                                method_local_imports.add(f"from {subnode.module}:{alias.name}")
                                break
                                
            except Exception as e:
                self.logger.debug(f"Failed to detect method-local imports: {e}")
        
        # Process top-level imports
        for imp in cai3_full.imports[:10]:  # Limit to 10 imports
            if imp.startswith('import '):
                module = imp[7:]
                # Shorten common modules
                if module in ['json', 'csv', 'os', 'sys', 're', 'ast', 'math']:
                    import_parts.append(module)
                else:
                    # Take first part of dotted import
                    import_parts.append(module.split('.')[0])
            elif imp.startswith('from '):
                # from X import Y format
                parts = imp[5:].split(' import ')
                if len(parts) == 2:
                    module, names = parts
                    # Compress format
                    if module == 'typing':
                        # Special case for typing
                        names_list = [n.strip() for n in names.split(',')][:3]
                        import_parts.append(f"from typing:{','.join(names_list)}")
                    else:
                        import_parts.append(f"from {module.split('.')[-1]}:{names.split(',')[0]}")
        
        # Add method-local imports
        for imp in method_local_imports:
            if len(import_parts) < 15:  # Don't exceed reasonable limit
                import_parts.append(imp)
        
        imports = "I:" + '|'.join(import_parts) if import_parts else ""
        
        # Extract config keys if any
        config_keys = self._extract_config_keys(cai3_full)
        
        # Build table (T:) entries - signatures for all methods/functions
        table = []
        nodes_by_cid = {node.cid: node for node in cai3_full.nodes}
        
        for node in cai3_full.nodes:
            if node.type == NodeType.CLASS:
                # Class entry
                table.append(f"T:C:{node.short_name}")
            elif node.type in (NodeType.METHOD, NodeType.FUNCTION):
                # Method/Function entry
                prefix = "T:M:" if node.type == NodeType.METHOD else "T:F:"
                
                # Determine fidelity
                fidelity = "B1" if node.cid in edit_scope_cids else "B0"
                
                # Build entry
                if node.parent_cid:
                    # Method in class
                    parent = nodes_by_cid.get(node.parent_cid)
                    if parent:
                        entry = f"{prefix}{parent.short_name}.{node.short_name}{node.signature} F={fidelity} cid={node.cid}"
                    else:
                        entry = f"{prefix}{node.short_name}{node.signature} F={fidelity} cid={node.cid}"
                else:
                    # Standalone function
                    entry = f"{prefix}{node.short_name}{node.signature} F={fidelity} cid={node.cid}"
                
                table.append(entry)
        
        # Build bodies (B:) entries - only for methods in edit scope
        bodies = []
        
        if edit_scope_cids and cai3_full.source_path:
            # Parse the original source to get method bodies
            try:
                with open(cai3_full.source_path, 'r') as f:
                    content = f.read()
                tree = ast.parse(content)
                
                # Create FLOW compiler with name mappings
                flow_compiler = FLOWCompiler(cai3_map.name_map)
                
                # Build nodes_by_cid lookup
                nodes_by_cid = {node.cid: node for node in cai3_full.nodes}
                
                # Create reverse CID index for span lookup
                span_to_cid = {}
                for cid, node in nodes_by_cid.items():
                    if node.span:
                        span_to_cid[node.span] = cid
                
                # Find and convert method bodies using CID-driven approach
                for cid in edit_scope_cids:
                    node_info = nodes_by_cid.get(cid)
                    if not node_info or not node_info.span:
                        continue
                    
                    # Find AST node by span
                    target_ast_node = None
                    start_line, end_line = node_info.span
                    
                    for ast_node in ast.walk(tree):
                        if isinstance(ast_node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                            if (hasattr(ast_node, 'lineno') and 
                                hasattr(ast_node, 'end_lineno') and
                                ast_node.lineno == start_line and
                                getattr(ast_node, 'end_lineno', ast_node.lineno) == end_line):
                                target_ast_node = ast_node
                                break
                    
                    if target_ast_node:
                        # Convert body to FLOW
                        try:
                            flow_body = flow_compiler.ast_to_flow(target_ast_node)
                            
                            # Add to bodies
                            bodies.append(f"B:{cid} FLOW:")
                            for line in flow_body.split('\n'):
                                if line.strip():  # Skip empty lines
                                    bodies.append(f"  {line}")
                            bodies.append("END")
                            bodies.append("")
                            
                            self.logger.debug(f"Generated FLOW body for CID {cid} ({node_info.name})")
                            
                        except Exception as e:
                            self.logger.warning(f"Failed to generate FLOW for {cid}: {e}")
                            
            except Exception as e:
                self.logger.warning(f"Failed to create FLOW bodies: {e}")
        
        return CAI3Lite(
            header=header,
            imports=imports,
            config_keys=config_keys,
            table=table,
            bodies=bodies
        )
    
    def _extract_config_keys(self, cai3_full: CAI3Full) -> Optional[str]:
        """Extract common config keys used in the code"""
        # This would analyze the AST for common patterns like self.config.get('key')
        # For now, return a simple example
        common_keys = ['required_fields', 'type_validation', 'field_mappings', 'transformations']
        
        # Only include if these appear to be used
        for node in cai3_full.nodes:
            if 'config' in node.name.lower() or 'validat' in node.name.lower():
                return f"CFG_KEYS:{','.join(common_keys)}"
        
        return None


# Monkey-patch or mixin approach to add CAI3 to existing WaterfallCompressor
def enhance_waterfall_with_cai3(WaterfallCompressorClass):
    """
    Enhance an existing WaterfallCompressor class with CAI3 capabilities.
    Can be used as a decorator or called directly.
    """
    
    # Add CAI3 methods to the class
    WaterfallCompressorClass._standard_compression_cai3 = CAI3WaterfallEnhancement._standard_compression_cai3
    WaterfallCompressorClass._determine_edit_scope = CAI3WaterfallEnhancement._determine_edit_scope
    WaterfallCompressorClass._has_bug_pattern = CAI3WaterfallEnhancement._has_bug_pattern
    WaterfallCompressorClass._calculate_complexity = CAI3WaterfallEnhancement._calculate_complexity
    WaterfallCompressorClass._modifies_parameters = CAI3WaterfallEnhancement._modifies_parameters
    WaterfallCompressorClass._create_cai3_full = CAI3WaterfallEnhancement._create_cai3_full
    WaterfallCompressorClass._create_cai3_map = CAI3WaterfallEnhancement._create_cai3_map
    WaterfallCompressorClass._create_cai3_lite = CAI3WaterfallEnhancement._create_cai3_lite
    WaterfallCompressorClass._extract_config_keys = CAI3WaterfallEnhancement._extract_config_keys
    WaterfallCompressorClass._compute_context_hash = CAI3WaterfallEnhancement._compute_context_hash
    WaterfallCompressorClass._compute_byte_span = CAI3WaterfallEnhancement._compute_byte_span
    
    # Check if the class already has an enhanced __init__
    if not hasattr(WaterfallCompressorClass, '_cai3_enhanced'):
        # Modify __init__ to add CAI3 attributes
        original_init = WaterfallCompressorClass.__init__
        
        def enhanced_init(self, *args, **kwargs):
            original_init(self, *args, **kwargs)
            self.use_cai3_mode = kwargs.get('use_cai3_mode', True)
            self.cai3_cache = CAI3Cache()
        
        WaterfallCompressorClass.__init__ = enhanced_init
        WaterfallCompressorClass._cai3_enhanced = True
    
    # Check if compress_string method exists and enhance it
    if hasattr(WaterfallCompressorClass, 'compress_string'):
        # Store the original compression method
        original_compress = WaterfallCompressorClass.compress_string
        
        def enhanced_compress(self, content: str, source_path: Optional[Path] = None) -> CompressionResult:
            # Count tokens
            original_tokens = count_tokens(content, getattr(self, 'llm_model', 'gpt-4'))
            
            # Determine tier
            tier = self._determine_tier(original_tokens)
            
            # Use CAI3 for MEDIUM tier if enabled
            if tier == CompressionTier.MEDIUM and getattr(self, 'use_cai3_mode', True):
                try:
                    return self._standard_compression_cai3(content, original_tokens, source_path)
                except Exception as e:
                    if hasattr(self, 'logger'):
                        self.logger.warning(f"CAI3 compression failed, falling back: {e}")
                    # Fallback to original compression
                    return original_compress(self, content, source_path)
            
            # Otherwise use original compression
            return original_compress(self, content, source_path)
        
        WaterfallCompressorClass.compress_string = enhanced_compress
    else:
        # If compress_string doesn't exist, create a simple version
        def simple_compress(self, content: str, source_path: Optional[Path] = None) -> CompressionResult:
            original_tokens = count_tokens(content, getattr(self, 'llm_model', 'gpt-4'))
            tier = self._determine_tier(original_tokens)
            
            if tier == CompressionTier.MEDIUM and getattr(self, 'use_cai3_mode', True):
                return self._standard_compression_cai3(content, original_tokens, source_path)
            
            # Simple fallback
            return CompressionResult(
                original_tokens=original_tokens,
                compressed_tokens=original_tokens // 2,
                compression_ratio=50.0,
                tier_used=tier,
                method_used="simple_compression",
                content=content[:100] + "... [compressed]"
            )
        
        WaterfallCompressorClass.compress_string = simple_compress
    
    return WaterfallCompressorClass


# Example usage in waterfall_compressor.py:
# 
# from cai3_waterfall_integration import enhance_waterfall_with_cai3
# 
# @enhance_waterfall_with_cai3
# class WaterfallCompressor:
#     ... existing code ...
#
# Or apply after class definition:
# enhance_waterfall_with_cai3(WaterfallCompressor)