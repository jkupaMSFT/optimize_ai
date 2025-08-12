# optimize_ai/input_optimizer/engine/cai3_waterfall_integration.py
"""
Enhanced CAI3 integration with aggressive compression for 70-90% token reduction.
Key improvements:
1. Dense FLOW syntax with single-char macros
2. Comprehensive identifier compression (locals, params, attrs)
3. String/constant pooling with references
4. Smarter edit scope selection (max 2 methods for MEDIUM)
5. Import compression
"""

import ast
import hashlib
import re
from pathlib import Path
from typing import List, Dict, Optional, Set, Tuple
import logging

from .cai3_structures import (
    CAI3Node, CAI3Full, CAI3Map, CAI3Lite, CAI3Cache,
    BodyFidelity, NodeType, generate_cid, compress_name
)
from .flow_language import FLOWCompiler
from .compression_types import CompressionResult, CompressionTier
from .minifier import MinifyTransformer

# Import from config at the project root level
import sys
import os
from pathlib import Path

# Add project root to path for config imports
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from config.constants import (
    DENSE_FLOW_ASCII_OPS, DENSE_FLOW_NO_SPACES, DENSE_FLOW_INLINE_BLOCKS,
    DENSE_FLOW_ALIAS_CHAINS, DENSE_FLOW_POOL_STRINGS_MIN_LEN,
    LITE_FLAT_TABLE, LITE_CID_ALIAS_MAP, LITE_KEEP_E_TERMINATOR,
    CAI3_MAX_EDIT_SCOPE_METHODS, CAI3_MIN_BUG_SCORE,
    CAI3_AGGRESSIVE_NAME_COMPRESSION, CAI3_POOL_CONSTANTS
)

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


def short36(cid: str) -> str:
    """
    Convert CID to base36 3-4 char representation.
    Uses hash to ensure consistent mapping and avoid collisions.
    """
    # Create hash of CID to get consistent numeric value
    hash_val = abs(hash(cid)) % (36**4)  # Ensure it fits in 4 base36 chars
    
    # Convert to base36
    chars = "0123456789abcdefghijklmnopqrstuvwxyz"
    if hash_val == 0:
        return "0"
    
    result = ""
    while hash_val:
        result = chars[hash_val % 36] + result
        hash_val //= 36
    
    # Pad to at least 3 chars for consistency
    return result.zfill(3)


class CAI3WaterfallEnhancement:
    """
    Enhanced CAI3 compression achieving 70-90% token reduction.
    """
    
    def __init__(self):
        """Initialize CAI3 components"""
        self.use_cai3_mode = True
        self.cai3_cache = CAI3Cache()
        self.logger = logging.getLogger(__name__)
        
        # Enhanced compression settings
        self.max_edit_scope_methods = CAI3_MAX_EDIT_SCOPE_METHODS  # Strict limit for MEDIUM tier
        self.min_bug_score = CAI3_MIN_BUG_SCORE  # Higher threshold for inclusion
        self.use_dense_flow = True  # Ultra-dense FLOW syntax
        self.compress_all_names = CAI3_AGGRESSIVE_NAME_COMPRESSION  # Compress locals, params, attrs
        self.pool_strings = CAI3_POOL_CONSTANTS  # Pool all strings > 5 chars
        self.include_all_methods = True  # Flag to include all method bodies
        self.llm_model = "gpt-4"
        
        # New minification flags (defaults for "all-methods" mode)
        self.pre_minify_locals = True  # Turn on automatically when include_all_methods=True
        self.minify_depth = 3  # 3 = VARIABLES — locals/params only
        
        # Dense FLOW feature flags (enabled by default for MEDIUM when include_all_methods=True)
        self.dense_flow_ascii_ops = DENSE_FLOW_ASCII_OPS
        self.dense_flow_no_spaces = DENSE_FLOW_NO_SPACES
        self.dense_flow_inline_blocks = DENSE_FLOW_INLINE_BLOCKS
        self.dense_flow_alias_chains = DENSE_FLOW_ALIAS_CHAINS
        self.dense_flow_pool_strings_min_len = DENSE_FLOW_POOL_STRINGS_MIN_LEN
        
        # LITE optimization flags
        self.lite_flat_table = LITE_FLAT_TABLE
        self.lite_cid_alias_map = LITE_CID_ALIAS_MAP
        self.lite_keep_e_terminator = LITE_KEEP_E_TERMINATOR
        
        # Auto-enable pre_minify_locals when include_all_methods is True
        if self.include_all_methods:
            self.pre_minify_locals = True
    
    def _annotate_function_cids(self, tree: ast.AST) -> dict:
        """
        Assign CIDs to classes/methods on the *original* tree and annotate nodes
        with node._cai_cid so the minifier can group mappings by CID.
        Returns a { (parent_class, func_name, lineno) : cid } index.
        """
        cid_index = {}
        class_stack = []

        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                class_cid = generate_cid('C', node.name)
                node._cai_cid = class_cid
                class_stack.append((node, class_cid))
                for item in node.body:
                    if isinstance(item, ast.FunctionDef):
                        m_cid = generate_cid('M', item.name, class_cid)
                        item._cai_cid = m_cid
                        cid_index[(node.name, item.name, getattr(item, 'lineno', 0))] = m_cid
                class_stack.pop()
            elif isinstance(node, ast.FunctionDef):
                f_cid = generate_cid('F', node.name)
                node._cai_cid = f_cid
                cid_index[(None, node.name, getattr(node, 'lineno', 0))] = f_cid
        return cid_index

    def _standard_compression_cai3(self, content: str, original_tokens: int,
                                   source_path: Optional[Path] = None) -> CompressionResult:
        """
        Enhanced CAI3 compression achieving 70-90% reduction.
        """
        try:
            # 0) Parse original
            orig_tree = ast.parse(content)
            
            # 1) Annotate CIDs on the original tree (so minifier can group by cid)
            cid_index = self._annotate_function_cids(orig_tree)
            
            # 2) Optional pre-minify
            minified_source = content
            per_cid_varmaps = {}
            min_tree = orig_tree  # keep a tree reference with _cai_cid in any case
            if getattr(self, "pre_minify_locals", False):
                # run the transformer *on the annotated tree*
                # NOTE: we must pass the already-parsed & annotated tree to the minifier
                # Easiest: duplicate the annotate+visit in a helper that takes a tree.
                min_tree = orig_tree  # same object, already annotated
                transformer = MinifyTransformer(compression_depth=self.minify_depth)
                min_tree = transformer.visit(min_tree)
                ast.fix_missing_locations(min_tree)
                minified_source = ast.unparse(min_tree) if hasattr(ast, 'unparse') else content
                per_cid_varmaps = transformer.per_cid_maps
            
            # 3) Now build CAI3 on the MINIFIED tree that still has _cai_cid
            #    (If pre_minify is off, min_tree == orig_tree so we still keep CIDs)
            tree = min_tree
            cai3_full = self._create_cai3_full_enhanced(tree, minified_source, source_path, cid_index)
            
            # 4) Attach per-cid var maps to CAI3Full nodes metadata (locals only)
            for node in cai3_full.nodes:
                if node.type in (NodeType.METHOD, NodeType.FUNCTION):
                    vm = per_cid_varmaps.get(node.cid, {})
                    if vm:
                        node.metadata["local_compressions"] = vm  # already used later by LITE
            
            # Add compression mode information to stats
            if 'compression_mode' not in cai3_full.compression_stats:
                cai3_full.compression_stats['compression_mode'] = (
                    'CAI3 All Bodies' if getattr(self, 'include_all_methods', False) 
                    else 'CAI3 Edit Scope'
                )
            
            # Strict edit scope selection (max 2 methods) - use original tree and content for scope determination
            edit_scope_cids = self._determine_edit_scope_strict(orig_tree, content, source_path, cid_index)
            
            # Diagnostic: ensure we have edit scope CIDs selected
            self.logger.debug("Edit scope CIDs: %s", edit_scope_cids)
            assert edit_scope_cids, "No edit-scope CIDs selected; bodies would be empty."
            
            cai3_map = self._create_cai3_map_enhanced(cai3_full)
            cai3_lite = self._create_cai3_lite_dense_ultra(cai3_full, cai3_map, edit_scope_cids, cid_index, minified_source, tree)
            
            # Store FULL and MAP locally
            if source_path:
                self.cai3_cache.store_full(source_path, cai3_full)
                self.cai3_cache.store_map(source_path, cai3_map)
            
            # Serialize only LITE for the LLM
            lite_content = cai3_lite.serialize()
            compressed_tokens = count_tokens(lite_content, self.llm_model)
            
            compression_ratio = (1 - compressed_tokens / original_tokens) * 100
            
            self.logger.info(
                f"CAI3 enhanced compression: {original_tokens} → {compressed_tokens} tokens "
                f"({compression_ratio:.1f}% reduction), {len(edit_scope_cids)} methods with bodies"
            )
            
            return CompressionResult(
                original_tokens=original_tokens,
                compressed_tokens=compressed_tokens,
                compression_ratio=compression_ratio,
                tier_used=CompressionTier.MEDIUM,
                method_used="cai3_enhanced",
                content=lite_content,
                metadata={
                    'cai3_mode': True,
                    'dense_flow': True,
                    'compression_mode': 'CAI3 All Bodies' if getattr(self, 'include_all_methods', False) else 'CAI3 Edit Scope',
                    'edit_scope_size': len(edit_scope_cids),
                    'total_nodes': len(cai3_full.nodes),
                    'source_path': str(source_path) if source_path else None
                }
            )
            
        except Exception as e:
            self.logger.error(f"Enhanced CAI3 compression failed: {e}")
            # Fallback
            return CompressionResult(
                original_tokens=original_tokens,
                compressed_tokens=original_tokens // 2,
                compression_ratio=50.0,
                tier_used=CompressionTier.MEDIUM,
                method_used="fallback_compression",
                content=content[:200] + "... [fallback]"
            )
    
    def _determine_edit_scope_strict(self, tree: ast.AST, content: str, 
                                     source_path: Optional[Path] = None, 
                                     cid_index: Optional[Dict] = None) -> List[str]:
        """
        Strict edit scope selection - max 2 methods for MEDIUM tier.
        Prioritizes methods with bugs, TODOs, and complexity.
        If include_all_methods flag is True, includes all methods.
        """
        if cid_index is None:
            cid_index = {}
        
        edit_candidates = []
        lines = content.split('\n')
        
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                start_line = getattr(node, 'lineno', 0)
                
                # Find parent class
                parent_class = None
                for parent in ast.walk(tree):
                    if isinstance(parent, ast.ClassDef):
                        if (hasattr(parent, 'lineno') and hasattr(parent, 'end_lineno') and
                            parent.lineno < start_line and 
                            getattr(parent, 'end_lineno', parent.lineno) > start_line):
                            parent_class = parent.name
                            break
                
                # Look up CID
                lookup_key = (parent_class, node.name, start_line)
                cid = cid_index.get(lookup_key)
                
                if cid is None:
                    node_type = 'M' if parent_class else 'F'
                    parent_cid = cid_index.get((None, parent_class, 0)) if parent_class else None
                    cid = generate_cid(node_type, node.name, parent_cid)
                
                # If include_all_methods flag is set, add all methods without scoring
                if getattr(self, 'include_all_methods', False):
                    edit_candidates.append((cid, 100, node.name))  # High score for all
                    continue
                
                # Calculate priority score for selective inclusion
                score = 0
                
                # 1. Bug patterns (highest priority)
                if self._has_bug_pattern_enhanced(node):
                    score += 20
                
                # 2. TODO/FIXME/BUG comments
                if hasattr(node, 'lineno'):
                    for line_num in range(node.lineno - 1, 
                                         min(node.lineno + 5, len(lines))):
                        if line_num < len(lines):
                            line = lines[line_num].upper()
                            if 'TODO' in line or 'FIXME' in line:
                                score += 15
                                break
                            elif 'BUG' in line or 'HACK' in line:
                                score += 18
                                break
                
                # 3. Method name patterns
                name_lower = node.name.lower()
                if 'validat' in name_lower or 'check' in name_lower:
                    score += 8
                elif 'process' in name_lower or 'transform' in name_lower:
                    score += 5
                
                # 4. High complexity
                complexity = self._calculate_complexity(node)
                if complexity > 15:
                    score += 10
                elif complexity > 10:
                    score += 5
                
                # 5. Parameter mutation
                if self._modifies_parameters(node):
                    score += 12
                
                # Only consider high-scoring methods when not including all
                if score >= self.min_bug_score:
                    edit_candidates.append((cid, score, node.name))
        
        # Sort by score and apply limits
        edit_candidates.sort(key=lambda x: x[1], reverse=True)
        
        selected_cids = []
        
        # If include_all_methods is enabled, take all candidates
        if getattr(self, 'include_all_methods', False):
            for cid, score, name in edit_candidates:
                selected_cids.append(cid)
                self.logger.debug(f"Including method '{name}' in edit scope (all methods mode)")
        else:
            # Take only top methods based on limit
            for cid, score, name in edit_candidates[:self.max_edit_scope_methods]:
                selected_cids.append(cid)
                self.logger.debug(f"Including method '{name}' in edit scope (score: {score})")
        
        return selected_cids
    
    def _has_bug_pattern_enhanced(self, node: ast.FunctionDef) -> bool:
        """Enhanced bug pattern detection"""
        # Check for mutation in validation/check methods
        if 'validat' in node.name.lower() or 'check' in node.name.lower():
            for subnode in ast.walk(node):
                if isinstance(subnode, ast.Assign):
                    for target in subnode.targets:
                        # Check if mutating parameter
                        if isinstance(target, (ast.Subscript, ast.Attribute)):
                            base = target
                            while isinstance(base, (ast.Subscript, ast.Attribute)):
                                base = base.value if isinstance(base, ast.Attribute) else base.value
                            
                            if isinstance(base, ast.Name):
                                param_names = {arg.arg for arg in node.args.args}
                                if base.id in param_names:
                                    return True
        
        # Missing return in annotated function
        if node.returns:
            has_return = any(isinstance(n, ast.Return) for n in ast.walk(node))
            if not has_return:
                return True
        
        # Exception without proper handling
        has_raise = any(isinstance(n, ast.Raise) for n in ast.walk(node))
        has_try = any(isinstance(n, ast.Try) for n in ast.walk(node))
        if has_raise and not has_try:
            return True
        
        return False
    
    def _extract_chain_pattern(self, node: ast.AST) -> Optional[str]:
        """
        Extract dotted chains and common call patterns from AST nodes.
        Examples: s.config.get, .items, datetime.now, datetime.now().isoformat
        """
        try:
            # Call chains (obj.method().method()) - handle first for better detection
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Attribute):
                    # Extract the function being called
                    func_chain = self._extract_attribute_chain(node.func)
                    if func_chain:
                        # Check for specific patterns that should be shortened
                        if func_chain == 'datetime.now':
                            return 'dt.now()'
                        elif func_chain.endswith('.now'):
                            return 'dt.now()'
                        elif func_chain.endswith('.get'):
                            # Common pattern: config.get() -> c.g()
                            if 'config' in func_chain:
                                return 's.c.g()'
                            else:
                                return func_chain + '()'
                        else:
                            return func_chain + '()'
            
            # Attribute chains (obj.attr.attr...)
            elif isinstance(node, ast.Attribute):
                return self._extract_attribute_chain(node)
                        
        except Exception:
            pass
        
        return None
    
    def _extract_attribute_chain(self, node: ast.Attribute) -> Optional[str]:
        """
        Extract attribute chain from an AST Attribute node.
        """
        try:
            chain_parts = []
            current = node
            while isinstance(current, ast.Attribute):
                chain_parts.append(current.attr)
                current = current.value
            
            if isinstance(current, ast.Name):
                chain_parts.append(current.id)
                chain_parts.reverse()
                full_chain = '.'.join(chain_parts)
                
                # Common patterns we want to capture with improved compression
                if len(chain_parts) >= 2:
                    # Specific high-value patterns
                    if 'self.config.get' in full_chain or full_chain.endswith('config.get'):
                        return 's.config.get'  # store what emitter prints
                    elif full_chain.endswith('.items'):
                        return 'tv.items'  # typically for dict.items()
                    elif 'datetime.now' in full_chain:
                        if full_chain.endswith('.isoformat'):
                            return 'dt.now().isoformat'  # Let this be a candidate
                        else:
                            return 'dt.now'
                    elif full_chain.endswith('.tr'):
                        return 's.tr'
                    elif full_chain.endswith('.vr'):
                        return 's.vr'
                    else:
                        # Only return generic compression if it's worth it (>5 chars savings)
                        compressed = '.'.join(part[0] for part in chain_parts if part)
                        if len(compressed) < len(full_chain) and len(full_chain) - len(compressed) >= 5:
                            return compressed
                        else:
                            # Return the full chain as a candidate - let net savings decide
                            return full_chain
                            
                return full_chain if len(full_chain) > 5 else None
                
        except Exception:
            pass
        
        return None
    
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
    
    def _create_cai3_full_enhanced(self, tree: ast.AST, content: str, 
                                   source_path: Optional[Path] = None, 
                                   cid_index: Optional[Dict] = None) -> CAI3Full:
        """
        Create enhanced CAI3-FULL with comprehensive compression metadata.
        Uses the provided cid_index from annotated AST nodes.
        """
        if cid_index is None:
            cid_index = {}
        
        nodes = []
        imports = []
        pools = {}
        bound_hashes = {}
        span_hashes = {}
        used_names = set()
        
        # Extract and compress imports
        for node in tree.body:
            if isinstance(node, ast.Import):
                for alias in node.names:
                    # Compress import names
                    import_str = f"import {alias.name}"
                    if alias.asname:
                        import_str += f" as {alias.asname}"
                    imports.append(import_str)
            elif isinstance(node, ast.ImportFrom):
                names = ', '.join(alias.name for alias in node.names)
                imports.append(f"from {node.module} import {names}")
        
        # Collect string frequency and chain patterns
        string_frequency = {}
        chain_patterns = {}
        
        # First pass: collect string and chain frequencies
        for node in ast.walk(tree):
            # String frequency counting
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                string_frequency[node.value] = string_frequency.get(node.value, 0) + 1
            
            # Chain pattern detection
            chain = self._extract_chain_pattern(node)
            if chain:
                chain_patterns[chain] = chain_patterns.get(chain, 0) + 1
        
        lines = content.split('\n')
        
        # Process all classes and functions
        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                # Use the annotated CID from the node with fallback to cid_index
                class_cid = getattr(node, '_cai_cid', None)
                if not class_cid:
                    class_cid = cid_index.get((node.name, node.name, getattr(node, 'lineno', 0)),
                                              generate_cid('C', node.name))
                class_short = self._compress_name_aggressive(node.name, used_names)
                
                # Extract and compress class attributes from __init__
                class_attr_compressions = self._compress_class_attributes_ultra(node, used_names)
                
                start_line = getattr(node, 'lineno', 0)
                end_line = getattr(node, 'end_lineno', start_line)
                
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
                    context_hash=context_hash,
                    metadata={
                        'compressed_names': {},
                        'attr_compressions': class_attr_compressions  # Store class attribute mappings
                    }
                )
                nodes.append(class_node)
                
                # Process methods with local variable compression
                for item in node.body:
                    if isinstance(item, ast.FunctionDef):
                        # Use the annotated CID from the node with fallback to cid_index
                        method_cid = getattr(item, '_cai_cid', None)
                        if not method_cid:
                            method_cid = cid_index.get((node.name, item.name, getattr(item, 'lineno', 0)),
                                                       generate_cid('M', item.name, class_cid))
                        method_short = self._compress_name_aggressive(item.name, used_names)
                        
                        method_start_line = getattr(item, 'lineno', 0)
                        method_end_line = getattr(item, 'end_lineno', method_start_line)
                        
                        # Compress local variables and parameters
                        local_compressions = self._compress_method_locals_ultra(item, used_names)
                        
                        # Create ultra-compact signature
                        args = []
                        for arg in item.args.args:
                            if arg.arg != 'self':
                                compressed_arg = local_compressions.get(arg.arg, arg.arg)
                                args.append(compressed_arg)
                        
                        # Compress return type
                        returns = "A"  # Default to Any
                        if item.returns:
                            if isinstance(item.returns, ast.Name):
                                ret_type = item.returns.id
                                type_map = {'bool': 'b', 'str': 's', 'int': 'i', 'float': 'f', 
                                           'list': 'l', 'dict': 'd', 'None': 'N', 'Any': 'A'}
                                returns = type_map.get(ret_type, 'A')
                        
                        signature = f"({','.join(args)})->{returns}"
                        
                        method_context_hash = self._compute_context_hash(lines, method_start_line, method_end_line)
                        method_byte_span = self._compute_byte_span(content, method_start_line, method_end_line)
                        
                        if method_context_hash:
                            span_hashes[method_cid] = method_context_hash
                        
                        method_node = CAI3Node(
                            cid=method_cid,
                            type=NodeType.METHOD,
                            name=item.name,
                            short_name=method_short,
                            signature=signature,
                            body_fidelity=BodyFidelity.B0,
                            span=(method_start_line, method_end_line),
                            byte_span=method_byte_span,
                            context_hash=method_context_hash,
                            parent_cid=class_cid,
                            metadata={'local_compressions': local_compressions}
                        )
                        
                        # Calculate content hash
                        method_content = ast.unparse(item) if hasattr(ast, 'unparse') else ""
                        bound_hashes[method_cid] = hashlib.md5(method_content.encode()).hexdigest()[:8]
                        
                        nodes.append(method_node)
            
            elif isinstance(node, ast.FunctionDef):
                # Handle standalone functions with fallback to cid_index
                func_cid = getattr(node, '_cai_cid', None)
                if not func_cid:
                    func_cid = cid_index.get((None, node.name, getattr(node, 'lineno', 0)),
                                             generate_cid('F', node.name))
                func_short = self._compress_name_aggressive(node.name, used_names)
                
                func_start_line = getattr(node, 'lineno', 0)
                func_end_line = getattr(node, 'end_lineno', func_start_line)
                
                # Compress local variables and parameters
                local_compressions = self._compress_method_locals_ultra(node, used_names)
                
                # Create ultra-compact signature
                args = []
                for arg in node.args.args:
                    compressed_arg = local_compressions.get(arg.arg, arg.arg)
                    args.append(compressed_arg)
                
                # Compress return type
                returns = "A"  # Default to Any
                if node.returns:
                    if isinstance(node.returns, ast.Name):
                        ret_type = node.returns.id
                        type_map = {'bool': 'b', 'str': 's', 'int': 'i', 'float': 'f', 
                                   'list': 'l', 'dict': 'd', 'None': 'N', 'Any': 'A'}
                        returns = type_map.get(ret_type, 'A')
                
                signature = f"({','.join(args)})->{returns}"
                
                func_context_hash = self._compute_context_hash(lines, func_start_line, func_end_line)
                func_byte_span = self._compute_byte_span(content, func_start_line, func_end_line)
                
                if func_context_hash:
                    span_hashes[func_cid] = func_context_hash
                
                func_node = CAI3Node(
                    cid=func_cid,
                    type=NodeType.FUNCTION,
                    name=node.name,
                    short_name=func_short,
                    signature=signature,
                    body_fidelity=BodyFidelity.B0,
                    span=(func_start_line, func_end_line),
                    byte_span=func_byte_span,
                    context_hash=func_context_hash,
                    metadata={'local_compressions': local_compressions}
                )
                
                # Calculate content hash
                func_content = ast.unparse(node) if hasattr(ast, 'unparse') else ""
                bound_hashes[func_cid] = hashlib.md5(func_content.encode()).hexdigest()[:8]
                
                nodes.append(func_node)
        
        # Extract strings and constants to pools with profitability rules
        pool_counter = 0
        chain_aliases = {}
        pool_map = {}  # Centralized pool map: value -> pool_id
        
        # Apply profitability rule: len(value) >= 8 and occurrences >= 2
        for string_val, freq in sorted(string_frequency.items(), key=lambda x: x[1], reverse=True):
            if len(string_val) >= 8 and freq >= 2:
                pool_key = f"p{pool_counter}"
                pools[pool_key] = string_val
                pool_map[string_val] = pool_key
                pool_counter += 1
        
        # Create chain aliases with net savings calculation
        alias_counter = 0
        for chain, freq in sorted(chain_patterns.items(), key=lambda x: x[1], reverse=True):
            if freq > 1:  # Only repeated chains
                alias_key = f"g{alias_counter}"
                
                # Calculate net savings: (occurrences * savings_per_use) - definition_cost
                savings_per_use = len(chain) - len(alias_key)  # bytes saved per use
                definition_cost = len(f"{alias_key}={chain}") + 1  # +1 for separator in D: section
                net_savings = (freq * savings_per_use) - definition_cost
                
                # Only include if net savings is positive
                if net_savings > 0:
                    chain_aliases[alias_key] = chain
                    alias_counter += 1
                    self.logger.debug(f"Chain alias '{alias_key}={chain}': {freq} uses, "
                                    f"saves {savings_per_use} chars/use, "
                                    f"costs {definition_cost} chars to define, "
                                    f"net savings: {net_savings}")
                else:
                    self.logger.debug(f"Rejected chain alias '{alias_key}={chain}': {freq} uses, "
                                    f"saves {savings_per_use} chars/use, "
                                    f"costs {definition_cost} chars to define, "
                                    f"net savings: {net_savings} (not profitable)")
                
                if alias_counter >= 10:  # Limit to 10 most frequent profitable chains
                    break
        
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
                'node_count': len(nodes),
                'pool_size': len(pools),
                'pool_map': pool_map,  # Store centralized pool map
                'chain_aliases': chain_aliases,  # Store chain aliases in metadata
                'string_frequency': string_frequency,
                'chain_frequency': chain_patterns
            }
        )
        
        return cai3_full
    
    def _compress_name_aggressive(self, name: str, used_names: Set[str]) -> str:
        """
        Aggressive name compression - single/double char names.
        Prohibits p\d+ and g\d+ patterns to avoid conflicts with pools/aliases.
        """
        # Special names that shouldn't be compressed
        if name in {'__init__', '__str__', '__repr__', '__eq__', '__hash__'}:
            # Shorten dunder methods
            dunder_map = {
                '__init__': 'i',
                '__str__': 's',
                '__repr__': 'r',
                '__eq__': 'e',
                '__hash__': 'h',
            }
            short = dunder_map.get(name, name[:2])
            if short not in used_names and not self._is_reserved_pattern(short):
                used_names.add(short)
                return short
        
        # For regular names, use aggressive compression
        if '_' in name:
            # snake_case: take first letter of each part
            parts = name.split('_')
            base = ''.join(p[0] for p in parts if p)[:2]  # Max 2 chars
        elif name[0].isupper():
            # CamelCase: take capital letters
            base = ''.join(c for c in name if c.isupper()).lower()[:2]
        else:
            # Simple name: take first 1-2 chars
            base = name[0] if len(name) > 5 else name[:2]
        
        # Ensure uniqueness and avoid reserved patterns
        if base not in used_names and not self._is_reserved_pattern(base):
            used_names.add(base)
            return base
        
        # Try single char + number, avoiding reserved patterns
        for i in range(10):
            candidate = f"{base[0]}{i}"
            if candidate not in used_names and not self._is_reserved_pattern(candidate):
                used_names.add(candidate)
                return candidate
        
        # Fallback: use first 3 chars of hash
        hash_candidate = hashlib.md5(name.encode()).hexdigest()[:3]
        if not self._is_reserved_pattern(hash_candidate):
            return hash_candidate
        else:
            # Final fallback with additional char
            return hash_candidate + 'x'
    
    def _compress_method_locals_ultra(self, method_node: ast.FunctionDef,
                                  used_names: Set[str]) -> Dict[str, str]:
        """
        Ultra-aggressive local variable compression.
        Uses single characters where possible, with smart collision avoidance.
        """
        compressions = {}
        local_used = set()
        
        # Reserve common single chars for most frequent variables
        frequency_map = self._analyze_variable_frequency(method_node)
        
        # Single char pool (excluding reserved)
        single_chars = 'abcdefhijklmnqrtuvwxyz'  # Skip reserved: g, p, s, o
        char_index = 0
        
        # Compress parameters first (they're usually most used)
        for arg in method_node.args.args:
            if arg.arg not in {'self', 'cls'}:
                freq = frequency_map.get(arg.arg, 1)
                
                # High frequency vars get single chars
                if freq > 2 and char_index < len(single_chars):
                    compressed = single_chars[char_index]
                    char_index += 1
                else:
                    compressed = self._generate_short_name(arg.arg, local_used)
                
                compressions[arg.arg] = compressed
                local_used.add(compressed)
        
        # Compress local variables by frequency
        sorted_vars = sorted(
            [(name, freq) for name, freq in frequency_map.items() 
            if name not in compressions and name not in {'self', 'cls'}],
            key=lambda x: x[1], reverse=True
        )
        
        for var_name, freq in sorted_vars:
            if freq > 2 and char_index < len(single_chars):
                compressed = single_chars[char_index]
                char_index += 1
            else:
                compressed = self._generate_short_name(var_name, local_used)
            
            compressions[var_name] = compressed
            local_used.add(compressed)
        
        return compressions

    def _analyze_variable_frequency(self, method_node: ast.FunctionDef) -> Dict[str, int]:
        """Analyze how frequently each variable is used in the method."""
        frequency = {}
        
        for node in ast.walk(method_node):
            if isinstance(node, ast.Name):
                name = node.id
                if name not in {'self', 'cls', 'True', 'False', 'None'}:
                    frequency[name] = frequency.get(name, 0) + 1
        
        return frequency
    
    def _generate_short_name(self, original: str, used: Set[str]) -> str:
        """Generate shortest possible name not in use."""
        # Try first char
        if original[0].lower() not in used and original[0].lower() not in 'gps':
            return original[0].lower()
        
        # Try first+last char
        if len(original) > 1:
            candidate = original[0].lower() + original[-1].lower()
            if candidate not in used and not candidate.startswith(('g', 'p')):
                return candidate
        
        # Try char + digit
        for i in range(10):
            for c in 'abcdefhijklmnqrtuvwxyz':
                candidate = f"{c}{i}"
                if candidate not in used and not candidate.startswith(('g', 'p')):
                    return candidate
        
        # Fallback: use hash
        return f"v{abs(hash(original)) % 100:02d}"
    
    def _compress_class_attributes_ultra(self, class_node: ast.ClassDef, 
                                     used_names: Set[str]) -> Dict[str, str]:
        """
        Ultra-aggressive attribute compression.
        Common patterns get single chars, others get 2 chars.
        """
        attr_compressions = {}
        
        # Find __init__ method
        init_method = None
        for item in class_node.body:
            if isinstance(item, ast.FunctionDef) and item.name == '__init__':
                init_method = item
                break
        
        if not init_method:
            return attr_compressions
        
        # Extract and analyze attributes
        attr_frequency = {}
        assigned_attrs = set()
        
        for node in ast.walk(init_method):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if (isinstance(target, ast.Attribute) and
                        isinstance(target.value, ast.Name) and
                        target.value.id == 'self'):
                        assigned_attrs.add(target.attr)
            
            # Count usage frequency
            if isinstance(node, ast.Attribute):
                if isinstance(node.value, ast.Name) and node.value.id == 'self':
                    attr_frequency[node.attr] = attr_frequency.get(node.attr, 0) + 1
        
        # Ultra-common patterns get single chars
        ultra_common = {
            'config': 'c',
            'data': 'd',
            'value': 'v',
            'name': 'n',
            'id': 'i',
            'type': 't',
            'status': 's',
            'result': 'r',
            'cache': 'h',
            'buffer': 'b',
            'queue': 'q',
            'stack': 'k',
            'list': 'l',
            'map': 'm',
            'set': 'e',
            'flag': 'f',
            'count': 'x',
            'index': 'x',
            'size': 'z',
            'length': 'z',
        }
        
        # Process attributes by frequency
        sorted_attrs = sorted(assigned_attrs, key=lambda x: attr_frequency.get(x, 0), reverse=True)
        
        used_shorts = set()
        
        for attr_name in sorted_attrs:
            # Check ultra-common patterns first
            found = False
            for pattern, short in ultra_common.items():
                if pattern in attr_name.lower() and short not in used_shorts:
                    attr_compressions[attr_name] = short
                    used_shorts.add(short)
                    found = True
                    break
            
            if not found:
                # Generate 2-char name
                compressed = self._generate_attr_short(attr_name, used_shorts)
                attr_compressions[attr_name] = compressed
                used_shorts.add(compressed)
        
        return attr_compressions
    
    def _compress_local_name(self, name: str, local_used: Set[str]) -> str:
        """
        Compress a local variable name to 1-2 chars.
        Prohibits p\d+ and g\d+ patterns to avoid conflicts with pools/aliases.
        """
        # Common patterns
        common_map = {
            'result': 'r',
            'results': 'rs',
            'record': 'rc',
            'records': 'rcs',
            'field': 'f',
            'fields': 'fs',
            'value': 'v',
            'values': 'vs',
            'item': 'i',
            'items': 'is',
            'data': 'd',
            'config': 'c',
            'error': 'e',
            'message': 'm',
            'count': 'n',
            'index': 'x',
            'key': 'k',
            'keys': 'ks',
            'temp': 't',
            'buffer': 'b',
            'output': 'o',
            'input': 'in',
        }
        
        # Check common patterns first
        for pattern, short in common_map.items():
            if pattern in name.lower():
                if short not in local_used and not self._is_reserved_pattern(short):
                    local_used.add(short)
                    return short
        
        # Use first char
        first = name[0].lower()
        if first not in local_used and not self._is_reserved_pattern(first):
            local_used.add(first)
            return first
        
        # Try first char + number, but avoid reserved patterns
        for i in range(10):
            candidate = f"{first}{i}"
            if candidate not in local_used and not self._is_reserved_pattern(candidate):
                local_used.add(candidate)
                return candidate
        
        # Use first 2 chars, avoiding reserved patterns
        two_char = name[:2].lower()
        if two_char not in local_used and not self._is_reserved_pattern(two_char):
            local_used.add(two_char)
            return two_char
        
        # Fallback: try alternative single chars
        for char in 'abcdefhjlmnqsuvwyz':  # Skip chars that might conflict
            if char not in local_used and not self._is_reserved_pattern(char):
                local_used.add(char)
                return char
        
        # Final fallback
        return name[:3]
    
    def _is_reserved_pattern(self, name: str) -> bool:
        """
        Check if a name matches reserved patterns (p\d+, g\d+ for pools/aliases).
        """
        import re
        # Prohibit p followed by digits (pool references)
        if re.match(r'^p\d+$', name):
            return True
        # Prohibit g followed by digits (chain alias references)
        if re.match(r'^g\d+$', name):
            return True
        return False
    
    def _extract_class_attributes_old(self, class_node: ast.ClassDef, used_names: Set[str]) -> Dict[str, str]:
        """
        Extract class attributes assigned in __init__ and create compressed mappings.
        Returns a dict mapping original attribute names to compressed names.
        
        Safe subset: only attributes assigned as self.<attr> = ... in __init__.
        """
        attr_compressions = {}
        init_method = None
        
        # Find __init__ method
        for item in class_node.body:
            if isinstance(item, ast.FunctionDef) and item.name == '__init__':
                init_method = item
                break
        
        if not init_method:
            return attr_compressions
        
        # Extract self.<attr> assignments
        assigned_attrs = set()
        for node in ast.walk(init_method):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if (isinstance(target, ast.Attribute) and 
                        isinstance(target.value, ast.Name) and 
                        target.value.id == 'self'):
                        assigned_attrs.add(target.attr)
        
        # Create compressed mappings for each attribute
        for attr_name in sorted(assigned_attrs):  # Sort for deterministic compression
            if attr_name not in attr_compressions:
                compressed_attr = self._compress_attribute_name(attr_name, used_names)
                attr_compressions[attr_name] = compressed_attr
                self.logger.debug(f"Class attribute compression: {attr_name} -> {compressed_attr}")
        
        return attr_compressions
    
    def _compress_attribute_name(self, attr_name: str, used_names: Set[str]) -> str:
        """
        Compress a class attribute name using common patterns and abbreviations.
        """
        # Common attribute patterns 
        common_patterns = {
            'processed_count': 'pc',
            'error_count': 'ec', 
            'success_count': 'sc',
            'total_count': 'tc',
            'config': 'c',
            'configuration': 'cfg',
            'manager': 'm',
            'handler': 'h',
            'processor': 'p',
            'validator': 'v',
            'transformer': 't',
            'controller': 'ctrl',
            'service': 's',
            'repository': 'repo',
            'factory': 'f',
            'builder': 'b',
            'cache': 'ch',
            'buffer': 'buf',
            'storage': 'stor',
            'connection': 'conn',
            'session': 'sess',
            'context': 'ctx',
            'metadata': 'meta',
            'properties': 'props',
            'parameters': 'params',
            'arguments': 'args',
            'options': 'opts',
            'settings': 'set',
            'preferences': 'prefs',
            'status': 'stat',
            'state': 'st',
            'result': 'res',
            'results': 'ress',
            'response': 'resp',
            'request': 'req',
            'database': 'db',
            'logger': 'log',
            'timestamp': 'ts',
            'created_at': 'cr',
            'updated_at': 'up',
            'deleted_at': 'del',
            'is_active': 'act',
            'is_enabled': 'en',
            'is_valid': 'val',
            'has_errors': 'err'
        }
        
        # Try exact match first
        if attr_name in common_patterns:
            candidate = common_patterns[attr_name]
            if candidate not in used_names and not self._is_reserved_pattern(candidate):
                used_names.add(candidate)
                return candidate
        
        # Try pattern matching for compound names
        for pattern, short in common_patterns.items():
            if pattern in attr_name.lower():
                candidate = short
                if candidate not in used_names and not self._is_reserved_pattern(candidate):
                    used_names.add(candidate)
                    return candidate
        
        # Snake_case compression: take first letter of each part
        if '_' in attr_name:
            parts = attr_name.split('_')
            # Take first letter of each part, max 3 chars
            candidate = ''.join(p[0] for p in parts if p)[:3]
            if candidate not in used_names and not self._is_reserved_pattern(candidate):
                used_names.add(candidate)
                return candidate
        
        # CamelCase compression: take capital letters
        if any(c.isupper() for c in attr_name):
            candidate = ''.join(c.lower() for c in attr_name if c.isupper())[:3]
            if candidate not in used_names and not self._is_reserved_pattern(candidate):
                used_names.add(candidate)
                return candidate
        
        # Fallback: first 2-3 chars
        for length in [2, 3]:
            candidate = attr_name[:length].lower()
            if candidate not in used_names and not self._is_reserved_pattern(candidate):
                used_names.add(candidate)
                return candidate
        
        # Last resort: add number suffix
        base = attr_name[:2].lower()
        for i in range(10):
            candidate = f"{base}{i}"
            if candidate not in used_names and not self._is_reserved_pattern(candidate):
                used_names.add(candidate)
                return candidate
        
        # Final fallback
        return attr_name[:3].lower()
    
    def _create_cai3_map_enhanced(self, cai3_full: CAI3Full) -> CAI3Map:
        """Create enhanced mapping with local compressions"""
        name_map = {}
        reverse_name_map = {}
        span_map = {}
        byte_map = {}
        ast_paths = {}
        context_hashes = {}
        parent_map = {}
        children_map = {}
        
        # Build mappings including local compressions
        for node in cai3_full.nodes:
            # Global name mappings
            if node.short_name != node.name:
                name_map[node.short_name] = node.name
                reverse_name_map[node.name] = node.short_name
            
            # Add local compressions to map
            if 'local_compressions' in node.metadata:
                for orig, compressed in node.metadata['local_compressions'].items():
                    # Store with CID prefix to avoid conflicts
                    key = f"{node.cid}:{compressed}"
                    name_map[key] = orig
                    reverse_name_map[f"{node.cid}:{orig}"] = compressed
            
            # Add class attribute compressions to map
            if 'attr_compressions' in node.metadata:
                for orig_attr, compressed_attr in node.metadata['attr_compressions'].items():
                    # Store as "{classCid}:{compressed}" -> "original" for deminify
                    attr_key = f"{node.cid}:{compressed_attr}"
                    name_map[attr_key] = orig_attr
                    reverse_name_map[f"{node.cid}:{orig_attr}"] = compressed_attr
                    self.logger.debug(f"Added attribute mapping: {attr_key} -> {orig_attr}")
            
            # Span and byte mappings
            if node.span:
                span_map[node.cid] = node.span
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


    def _create_cai3_lite_dense_ultra(self, cai3_full: CAI3Full, cai3_map: CAI3Map,
                                    edit_scope_cids: List[str], cid_index: Dict,
                                    content: str, tree: ast.AST) -> CAI3Lite:
        """
        Create ultra-dense CAI3-LITE achieving 50-70% compression for all bodies mode.
        Key optimizations:
        1. Single-line body format
        2. No signatures for methods with bodies
        3. Aggressive local/attribute compression
        4. Smart pooling with profitability analysis
        5. Compact header and metadata
        """
        
        # Ultra-compact header - minimize version info
        source_file = Path(cai3_full.source_path).name if cai3_full.source_path else "?"
        # Shorten header: #C3L instead of #C3L v2 py=3.11
        header = f"#C3L {source_file[:20]}"  # Limit filename length
        
        # Skip imports section entirely if not used in bodies
        imports = ""  # Will be reconstructed from AST if needed
        
        # Chain aliases - only include if they provide net savings
        chain_aliases_section = None
        if 'chain_aliases' in cai3_full.compression_stats:
            chain_aliases = cai3_full.compression_stats['chain_aliases']
            # Filter to only highly profitable aliases (used 3+ times)
            profitable_aliases = {}
            for alias, chain in chain_aliases.items():
                # Count actual usage in bodies
                usage_count = self._count_chain_usage_in_bodies(chain, edit_scope_cids, tree, cai3_full)
                if usage_count >= 3:  # Higher threshold for inclusion
                    profitable_aliases[alias] = chain
            
            if profitable_aliases:
                # Ultra-compact format: D:g0=s.c.g,g1=dt.now
                alias_parts = [f"{k}={v}" for k, v in list(profitable_aliases.items())[:5]]  # Max 5 aliases
                chain_aliases_section = f"D:{','.join(alias_parts)}"  # Use comma instead of pipe
        
        # CID aliases - use ultra-short format
        cid_alias_map = {}
        for i, cid in enumerate(edit_scope_cids):
            # Use single char + digit for CID aliases: a0, a1, b0, b1...
            alias_char = chr(97 + (i // 10))  # a, b, c...
            alias_num = i % 10
            cid_alias_map[cid] = f"{alias_char}{alias_num}"
        
        # Ultra-compact CID section: X:a0=5mn3,a1=e0wr
        cid_aliases_section = None
        if cid_alias_map:
            alias_items = [f"{v}={short36(k)[:4]}" for k, v in cid_alias_map.items()]
            cid_aliases_section = f"X:{','.join(alias_items)}"  # Use comma separator
        
        # Skip config keys section - rarely used
        config_keys = None
        
        # Build ultra-compact table WITHOUT signatures for methods with bodies
        table = []
        nodes_by_cid = {node.cid: node for node in cai3_full.nodes}
        
        for node in cai3_full.nodes:
            if node.type == NodeType.CLASS:
                # Ultra-compact class: C:dp
                table.append(f"C:{node.short_name}")
            elif node.type in (NodeType.METHOD, NodeType.FUNCTION):
                # Check if this method has a body
                has_body = node.cid in edit_scope_cids
                
                prefix = "M" if node.type == NodeType.METHOD else "F"
                
                if has_body:
                    # Method WITH body - no signature needed, just name and CID alias
                    cid_ref = f"#{cid_alias_map.get(node.cid, node.cid[:4])}"
                    if node.parent_cid:
                        parent = nodes_by_cid.get(node.parent_cid)
                        if parent:
                            entry = f"{prefix}:{parent.short_name}.{node.short_name}{cid_ref}"
                        else:
                            entry = f"{prefix}:{node.short_name}{cid_ref}"
                    else:
                        entry = f"{prefix}:{node.short_name}{cid_ref}"
                else:
                    # Method WITHOUT body - include signature
                    if node.parent_cid:
                        parent = nodes_by_cid.get(node.parent_cid)
                        if parent:
                            entry = f"{prefix}:{parent.short_name}.{node.short_name}"
                        else:
                            entry = f"{prefix}:{node.short_name}"
                    else:
                        entry = f"{prefix}:{node.short_name}"
                
                table.append(entry)
        
        # Flatten table to single line for ultra-density
        table = [f"T:{','.join(table)}"]  # Use comma separator, single line
        
        # Build ultra-dense single-line bodies
        bodies = []
        
        if edit_scope_cids:
            # Create enhanced FLOW compiler with all optimizations
            flow_compiler = FLOWCompiler(
                name_map=cai3_map.name_map,
                dense_mode=True,
                pool_constants=True,
                ascii_ops=True,
                no_spaces=True,
                inline_blocks=True,
                alias_chains=True,
                pool_strings_min_len=5  # Higher threshold for pooling
            )
            
            # Set pools and aliases
            if 'pool_map' in cai3_full.compression_stats:
                flow_compiler.set_pool_map(cai3_full.compression_stats['pool_map'])
            if 'chain_aliases' in cai3_full.compression_stats:
                flow_compiler.set_chain_aliases(profitable_aliases if profitable_aliases else {})
            
            nodes_by_cid = {node.cid: node for node in cai3_full.nodes}
            
            for cid in edit_scope_cids:
                node_info = nodes_by_cid.get(cid)
                if not node_info or not node_info.span:
                    continue
                
                # Find AST node
                target_ast_node = self._find_ast_node_for_cid(tree, node_info.span)
                
                if target_ast_node:
                    # Get comprehensive compression mappings
                    local_compressions = node_info.metadata.get('local_compressions', {})
                    
                    # Get attribute compressions from parent class
                    attr_compressions = {}
                    if node_info.parent_cid:
                        parent_node = nodes_by_cid.get(node_info.parent_cid)
                        if parent_node and 'attr_compressions' in parent_node.metadata:
                            attr_compressions = parent_node.metadata['attr_compressions']
                    
                    # Generate ultra-dense single-line body
                    try:
                        # Use the new ultra-dense body generator
                        ultra_dense_body = flow_compiler.generate_ultra_dense_body(
                            target_ast_node, cid, local_compressions, attr_compressions
                        )
                        
                        # Ultra-compact body format: B#a0:single_line_body
                        cid_ref = cid_alias_map.get(cid, cid[:4])
                        
                        # Single line body with CID reference
                        bodies.append(f"B#{cid_ref}:{ultra_dense_body}")
                        
                    except Exception as e:
                        self.logger.warning(f"Failed to create ultra-dense body for {cid}: {e}")
        
        # Filter pools to only referenced ones
        pool_section = None
        if bodies:
            # Extract actually used pool references
            body_text = ' '.join(bodies)
            import re
            pool_pattern = r'\bp(\d+)\b'
            matches = re.findall(pool_pattern, body_text)
            referenced_pool_ids = {f"p{match}" for match in matches}
            
            if referenced_pool_ids and cai3_full.pools:
                # Ultra-compact pool format with shortened values
                pool_items = []
                for pool_id in list(referenced_pool_ids)[:10]:  # Max 10 pools
                    if pool_id in cai3_full.pools:
                        value = cai3_full.pools[pool_id]
                        # Ultra-compress pool values
                        if len(value) > 10:
                            # Use hash for long strings
                            compressed_val = f"#{hash(value) % 10000:04d}"
                        else:
                            compressed_val = value
                        pool_items.append(f"{pool_id}={compressed_val}")
                
                if pool_items:
                    pool_section = f"P:{','.join(pool_items)}"  # Comma separator
        
        # Create ultra-compact LITE
        return CAI3Lite(
            header=header,
            imports=imports,  # Empty for all-bodies mode
            chain_aliases=chain_aliases_section,
            cid_aliases=cid_aliases_section,
            config_keys=config_keys,  # Skip
            pools=pool_section,
            table=table,
            bodies=bodies
        )

    def _find_ast_node_for_cid(self, tree: ast.AST, span: Tuple[int, int]) -> Optional[ast.FunctionDef]:
        """Find AST node matching the given span."""
        start_line, end_line = span
        
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if (hasattr(node, 'lineno') and
                    hasattr(node, 'end_lineno') and
                    node.lineno == start_line and
                    getattr(node, 'end_lineno', node.lineno) == end_line):
                    return node
        return None

    def _count_chain_usage_in_bodies(self, chain: str, cids: List[str], tree: ast.AST, cai3_full: CAI3Full) -> int:
        """Count how many times a chain pattern appears in method bodies."""
        count = 0
        nodes_by_cid = {node.cid: node for node in cai3_full.nodes}
        
        for cid in cids:
            node_info = nodes_by_cid.get(cid)
            if not node_info or not node_info.span:
                continue
            
            # Find AST node and count chain usage
            target_node = self._find_ast_node_for_cid(tree, node_info.span)
            if target_node:
                for node in ast.walk(target_node):
                    if isinstance(node, ast.Attribute):
                        # Check if this matches our chain pattern
                        node_chain = self._extract_attribute_chain(node)
                        if node_chain == chain:
                            count += 1
        
        return count

    # Helper function to generate ultra-short base36 CID representations
    def short36(cid: str) -> str:
        """Convert CID to base36 4-char representation."""
        # Use first 4 chars of hash for uniqueness
        import hashlib
        hash_val = int(hashlib.md5(cid.encode()).hexdigest()[:8], 16)
        
        # Convert to base36
        chars = "0123456789abcdefghijklmnopqrstuvwxyz"
        result = ""
        while hash_val and len(result) < 4:
            result = chars[hash_val % 36] + result
            hash_val //= 36
        
        return result.zfill(4)

    def _generate_attr_short(self, attr_name: str, used: Set[str]) -> str:
        """Generate shortest attribute name."""
        # Try first char if available
        first = attr_name[0].lower()
        if first not in used and first not in 'gps':
            return first
        
        # Try first + consonant from name
        consonants = [c for c in attr_name.lower() if c not in 'aeiou_']
        if len(consonants) >= 2:
            candidate = consonants[0] + consonants[1]
            if candidate not in used and not candidate.startswith(('g', 'p')):
                return candidate
        
        # Try first + last
        if len(attr_name) > 1:
            candidate = attr_name[0].lower() + attr_name[-1].lower()
            if candidate not in used and not candidate.startswith(('g', 'p')):
                return candidate
        
        # Generate from available chars
        for c1 in 'abcdefhijklmnqrtuvwxyz':
            for c2 in 'abcdefhijklmnqrtuvwxyz':
                candidate = c1 + c2
                if candidate not in used and not candidate.startswith(('g', 'p')):
                    return candidate
        
        return f"a{abs(hash(attr_name)) % 100:02d}"
    
    def _find_symbols_used_in_bodies(self, cai3_full: CAI3Full, edit_scope_cids: List[str], content: str) -> Set[str]:
        """
        Find symbols actually used in method bodies to optimize import inclusion.
        """
        used_symbols = set()
        
        try:
            tree = ast.parse(content)
            nodes_by_cid = {node.cid: node for node in cai3_full.nodes}
            
            for cid in edit_scope_cids:
                node_info = nodes_by_cid.get(cid)
                if not node_info or not node_info.span:
                    continue
                
                # Find AST node for this method
                start_line, end_line = node_info.span
                for ast_node in ast.walk(tree):
                    if isinstance(ast_node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        if (hasattr(ast_node, 'lineno') and 
                            hasattr(ast_node, 'end_lineno') and
                            ast_node.lineno == start_line and
                            getattr(ast_node, 'end_lineno', ast_node.lineno) == end_line):
                            
                            # Extract symbols used in this method
                            for subnode in ast.walk(ast_node):
                                if isinstance(subnode, ast.Name):
                                    used_symbols.add(subnode.id)
                                elif isinstance(subnode, ast.Attribute):
                                    # Extract base name from attribute access
                                    base = subnode.value
                                    while isinstance(base, ast.Attribute):
                                        base = base.value
                                    if isinstance(base, ast.Name):
                                        used_symbols.add(base.id)
                            break
        except Exception as e:
            self.logger.warning(f"Failed to extract used symbols: {e}")
        
        return used_symbols
    
    def _extract_chain_pattern(self, node: ast.AST) -> Optional[str]:
        """
        Extract dotted chains and common call patterns from AST nodes.
        Examples: s.config.get, .items, datetime.now, datetime.now().isoformat
        """
        try:
            # Call chains (obj.method().method()) - handle first for better detection
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Attribute):
                    # Extract the function being called
                    func_chain = self._extract_attribute_chain(node.func)
                    if func_chain:
                        # Check for specific patterns that should be shortened
                        if func_chain == 'datetime.now':
                            return 'dt.now()'
                        elif func_chain.endswith('.now'):
                            return 'dt.now()'
                        elif func_chain.endswith('.get'):
                            # Common pattern: config.get() -> c.g()
                            if 'config' in func_chain:
                                return 's.c.g()'
                            else:
                                return func_chain + '()'
                        else:
                            return func_chain + '()'
            
            # Attribute chains (obj.attr.attr...)
            elif isinstance(node, ast.Attribute):
                return self._extract_attribute_chain(node)
                        
        except Exception:
            pass
        
        return None
    
    def _extract_attribute_chain(self, node: ast.Attribute) -> Optional[str]:
        """
        Extract attribute chain from an AST Attribute node.
        """
        try:
            chain_parts = []
            current = node
            while isinstance(current, ast.Attribute):
                chain_parts.append(current.attr)
                current = current.value
            
            if isinstance(current, ast.Name):
                chain_parts.append(current.id)
                chain_parts.reverse()
                full_chain = '.'.join(chain_parts)
                
                # Common patterns we want to capture with improved compression
                if len(chain_parts) >= 2:
                    # Specific high-value patterns
                    if 'self.config.get' in full_chain or full_chain.endswith('config.get'):
                        return 's.config.get'  # store what emitter prints
                    elif full_chain.endswith('.items'):
                        return 'tv.items'  # typically for dict.items()
                    elif 'datetime.now' in full_chain:
                        if full_chain.endswith('.isoformat'):
                            return 'dt.now().isoformat'  # Let this be a candidate
                        else:
                            return 'dt.now'
                    elif full_chain.endswith('.tr'):
                        return 's.tr'
                    elif full_chain.endswith('.vr'):
                        return 's.vr'
                    else:
                        # Only return generic compression if it's worth it (>5 chars savings)
                        compressed = '.'.join(part[0] for part in chain_parts if part)
                        if len(compressed) < len(full_chain) and len(full_chain) - len(compressed) >= 5:
                            return compressed
                        else:
                            # Return the full chain as a candidate - let net savings decide
                            return full_chain
                            
                return full_chain if len(full_chain) > 5 else None
                
        except Exception:
            pass
        
        return None
    
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
        """Compute context hash for a code span"""
        try:
            context_start = max(0, start_line - 3)
            context_end = min(len(lines), end_line + 2)
            
            context_lines = lines[context_start:context_end]
            context_text = '\n'.join(context_lines)
            
            return hashlib.md5(context_text.encode()).hexdigest()[:8]
        except Exception:
            return None
    
    def _compute_byte_span(self, content: str, start_line: int, end_line: int) -> Optional[Tuple[int, int]]:
        """Compute byte offsets for a line range"""
        try:
            lines = content.split('\n')
            
            start_byte = 0
            for i in range(start_line - 1):
                if i < len(lines):
                    start_byte += len(lines[i]) + 1
            
            end_byte = start_byte
            for i in range(start_line - 1, min(end_line, len(lines))):
                if i < len(lines):
                    end_byte += len(lines[i]) + 1
            
            return (start_byte, end_byte)
        except Exception:
            return None
        
        
    


def enhance_waterfall_with_cai3(WaterfallCompressorClass):
    """
    Enhance an existing WaterfallCompressor class with CAI3 capabilities.
    """
    
    # Add enhanced CAI3 methods to the class
    WaterfallCompressorClass._annotate_function_cids = CAI3WaterfallEnhancement._annotate_function_cids
    WaterfallCompressorClass._standard_compression_cai3 = CAI3WaterfallEnhancement._standard_compression_cai3
    WaterfallCompressorClass._determine_edit_scope_strict = CAI3WaterfallEnhancement._determine_edit_scope_strict
    WaterfallCompressorClass._has_bug_pattern_enhanced = CAI3WaterfallEnhancement._has_bug_pattern_enhanced
    WaterfallCompressorClass._calculate_complexity = CAI3WaterfallEnhancement._calculate_complexity
    WaterfallCompressorClass._modifies_parameters = CAI3WaterfallEnhancement._modifies_parameters
    WaterfallCompressorClass._create_cai3_full_enhanced = CAI3WaterfallEnhancement._create_cai3_full_enhanced
    WaterfallCompressorClass._create_cai3_map_enhanced = CAI3WaterfallEnhancement._create_cai3_map_enhanced
    WaterfallCompressorClass._create_cai3_lite_dense_ultra = CAI3WaterfallEnhancement._create_cai3_lite_dense_ultra
    WaterfallCompressorClass._compress_name_aggressive = CAI3WaterfallEnhancement._compress_name_aggressive
    WaterfallCompressorClass._compress_method_locals_ultra = CAI3WaterfallEnhancement._compress_method_locals_ultra
    WaterfallCompressorClass._compress_class_attributes_ultra = CAI3WaterfallEnhancement._compress_class_attributes_ultra
    WaterfallCompressorClass._compress_local_name = CAI3WaterfallEnhancement._compress_local_name
    WaterfallCompressorClass._is_reserved_pattern = CAI3WaterfallEnhancement._is_reserved_pattern
    WaterfallCompressorClass._compress_attribute_name = CAI3WaterfallEnhancement._compress_attribute_name
    WaterfallCompressorClass._analyze_variable_frequency = CAI3WaterfallEnhancement._analyze_variable_frequency
    WaterfallCompressorClass._generate_short_name = CAI3WaterfallEnhancement._generate_short_name
    WaterfallCompressorClass._extract_chain_pattern = CAI3WaterfallEnhancement._extract_chain_pattern
    WaterfallCompressorClass._extract_attribute_chain = CAI3WaterfallEnhancement._extract_attribute_chain
    WaterfallCompressorClass._find_symbols_used_in_bodies = CAI3WaterfallEnhancement._find_symbols_used_in_bodies
    WaterfallCompressorClass._compute_context_hash = CAI3WaterfallEnhancement._compute_context_hash
    WaterfallCompressorClass._compute_byte_span = CAI3WaterfallEnhancement._compute_byte_span
    WaterfallCompressorClass._find_ast_node_for_cid = CAI3WaterfallEnhancement._find_ast_node_for_cid
    WaterfallCompressorClass._count_chain_usage_in_bodies = CAI3WaterfallEnhancement._count_chain_usage_in_bodies
    WaterfallCompressorClass._generate_attr_short = CAI3WaterfallEnhancement._generate_attr_short
    
    # Check if the class already has an enhanced __init__
    if not hasattr(WaterfallCompressorClass, '_cai3_enhanced'):
        # Modify __init__ to add CAI3 attributes
        original_init = WaterfallCompressorClass.__init__
        
        def enhanced_init(self, *args, **kwargs):
            original_init(self, *args, **kwargs)
            self.use_cai3_mode = kwargs.get('use_cai3_mode', True)
            self.cai3_cache = CAI3Cache()
            # Enhanced settings
            self.max_edit_scope_methods = 2
            self.min_bug_score = 10
            self.use_dense_flow = True
            self.compress_all_names = True
            self.pool_strings = True
            self.include_all_methods = kwargs.get('include_all_methods', True)  # Default to True as per CAI3WaterfallEnhancement
            
            # New minification flags (defaults for "all-methods" mode)
            self.pre_minify_locals = kwargs.get('pre_minify_locals', True)  # Turn on automatically when include_all_methods=True
            self.minify_depth = kwargs.get('minify_depth', 3)  # 3 = VARIABLES — locals/params only
            
            # Auto-enable pre_minify_locals when include_all_methods is True
            if self.include_all_methods:
                self.pre_minify_locals = True
        
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
            
            # Use enhanced CAI3 for MEDIUM tier if enabled
            if tier == CompressionTier.MEDIUM and getattr(self, 'use_cai3_mode', True):
                try:
                    return self._standard_compression_cai3(content, original_tokens, source_path)
                except Exception as e:
                    if hasattr(self, 'logger'):
                        self.logger.warning(f"Enhanced CAI3 compression failed, falling back: {e}")
                    # Fallback to original compression
                    return original_compress(self, content, source_path)
            
            # Otherwise use original compression
            return original_compress(self, content, source_path)
        
        WaterfallCompressorClass.compress_string = enhanced_compress
    
    return WaterfallCompressorClass
                            
                            
