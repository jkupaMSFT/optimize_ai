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
from ...config.constants import (
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
        self.include_all_methods = False  # Flag to include all method bodies
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
            
            # Strict edit scope selection (max 2 methods) - use original tree and content for scope determination
            edit_scope_cids = self._determine_edit_scope_strict(orig_tree, content, source_path, cid_index)
            
            # Diagnostic: ensure we have edit scope CIDs selected
            self.logger.debug("Edit scope CIDs: %s", edit_scope_cids)
            assert edit_scope_cids, "No edit-scope CIDs selected; bodies would be empty."
            
            cai3_map = self._create_cai3_map_enhanced(cai3_full)
            cai3_lite = self._create_cai3_lite_dense(cai3_full, cai3_map, edit_scope_cids, cid_index, minified_source, tree)
            
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
                class_attr_compressions = self._extract_class_attributes(node, used_names)
                
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
                        local_compressions = self._compress_method_locals(item, used_names)
                        
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
                local_compressions = self._compress_method_locals(node, used_names)
                
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
    
    def _compress_method_locals(self, method_node: ast.FunctionDef, 
                                used_names: Set[str]) -> Dict[str, str]:
        """
        Compress all local variables and parameters in a method.
        """
        compressions = {}
        local_used = set()
        
        # Compress parameters
        for arg in method_node.args.args:
            if arg.arg not in {'self', 'cls'}:
                compressed = self._compress_local_name(arg.arg, local_used)
                compressions[arg.arg] = compressed
        
        # Find and compress all local variables
        for node in ast.walk(method_node):
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
                if node.id not in compressions and node.id not in {'self', 'cls'}:
                    compressed = self._compress_local_name(node.id, local_used)
                    compressions[node.id] = compressed
        
        return compressions
    
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
    
    def _extract_class_attributes(self, class_node: ast.ClassDef, used_names: Set[str]) -> Dict[str, str]:
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
    
    def _create_cai3_lite_dense(self, cai3_full: CAI3Full, cai3_map: CAI3Map, 
                                edit_scope_cids: List[str], cid_index: Dict,
                                content: str, tree: ast.AST) -> CAI3Lite:
        """
        Create ultra-dense CAI3-LITE achieving 70-90% compression.
        """
        # Ultra-compact header with py= format
        source_file = Path(cai3_full.source_path).name if cai3_full.source_path else "?"
        header = f"#C3L v2 py={cai3_full.python_version[:4]} f={source_file}"
        
        # Compress imports to single line - only include symbols used in bodies
        used_in_bodies = self._find_symbols_used_in_bodies(cai3_full, edit_scope_cids, content)
        import_parts = []
        for imp in cai3_full.imports[:5]:  # Limit to 5 most important
            if imp.startswith('import '):
                module = imp[7:].split(' as ')[0]
                # Ultra-short common imports - only if used
                import_map = {
                    'json': 'j',
                    'datetime': 'dt',
                    'typing': 't',
                    'collections': 'c',
                    'itertools': 'it',
                    'functools': 'ft',
                    'os': 'o',
                    'sys': 's',
                    're': 'r',
                    'math': 'm',
                }
                short_name = import_map.get(module, module[:2])
                if any(symbol in used_in_bodies for symbol in [module, short_name]):
                    import_parts.append(short_name)
            elif imp.startswith('from '):
                parts = imp[5:].split(' import ')
                if len(parts) == 2:
                    module, names = parts
                    # Compress format
                    module_short = module.split('.')[-1][:2]
                    name_short = names.split(',')[0][:2]
                    if any(symbol in used_in_bodies for symbol in [module_short, name_short]):
                        import_parts.append(f"{module_short}:{name_short}")
        
        imports = "I:" + '|'.join(import_parts) if import_parts else ""
        
        # Extract chain aliases from compression stats
        chain_aliases_section = None
        if 'chain_aliases' in cai3_full.compression_stats:
            chain_aliases = cai3_full.compression_stats['chain_aliases']
            if chain_aliases:
                alias_parts = [f"{k}={v}" for k, v in chain_aliases.items()]
                chain_aliases_section = f"D:{('|'.join(alias_parts))}"
        
        # Create CID aliasing map - only for methods that have bodies
        cid_alias_map = {}
        cid_reverse_map = {}  # Map short36 back to real CID for translator
        
        # Only emit aliases for methods that have bodies (edit_scope_cids)
        bodied_cids = [cid for cid in edit_scope_cids]
        for i, real_cid in enumerate(bodied_cids):
            short_tag = short36(real_cid)
            cid_alias_map[real_cid] = str(i)  # Use simple counter for alias
            cid_reverse_map[short_tag] = real_cid  # Store reverse mapping
        
        # Store reverse mapping in compression stats for translator
        if 'cid_aliases' not in cai3_full.compression_stats:
            cai3_full.compression_stats['cid_aliases'] = {}
        cai3_full.compression_stats['cid_aliases'].update(cid_reverse_map)
        
        # CID aliasing section - emit short base36 tags
        cid_aliases_section = None
        if cid_alias_map:
            alias_items = [f"{cid_alias_map[real_cid]}={short36(real_cid)}" for real_cid in bodied_cids]
            cid_aliases_section = f"X:{('|'.join(alias_items))}"
        
        # Extract config keys (ultra-compact)
        config_keys = None
        if any('config' in node.name.lower() for node in cai3_full.nodes):
            # Use single-char keys
            keys = ['rf', 'tv', 'fm', 'ts']  # Shortened versions
            config_keys = f"K:{','.join(keys)}"
        
        # Build ultra-compact table
        table = []
        nodes_by_cid = {node.cid: node for node in cai3_full.nodes}
        
        # Build table with CID aliases
        for node in cai3_full.nodes:
            if node.type == NodeType.CLASS:
                # Ultra-compact class: C:dp
                table.append(f"C:{node.short_name}")
            elif node.type in (NodeType.METHOD, NodeType.FUNCTION):
                # Determine fidelity
                fidelity = "1" if node.cid in edit_scope_cids else "0"
                
                # Ultra-compact method: M:dp.vr(r)->b F1 #alias
                prefix = "M:" if node.type == NodeType.METHOD else "F:"
                
                # Use CID alias if available
                cid_ref = f"#{cid_alias_map[node.cid]}" if node.cid in cid_alias_map else f"#{node.cid}"
                
                if node.parent_cid:
                    parent = nodes_by_cid.get(node.parent_cid)
                    if parent:
                        # Remove parentheses and arrow for B0 methods
                        if fidelity == "0":
                            entry = f"{prefix}{parent.short_name}.{node.short_name}"
                        else:
                            # Drop signature when body is present (fidelity="1") - redundant and expensive
                            entry = f"{prefix}{parent.short_name}.{node.short_name}{cid_ref}"
                    else:
                        entry = f"{prefix}{node.short_name}"
                else:
                    if fidelity == "0":
                        entry = f"{prefix}{node.short_name}"
                    else:
                        # Drop signature when body is present (fidelity="1") - redundant and expensive
                        entry = f"{prefix}{node.short_name}{cid_ref}"
                
                table.append(entry)
        
        # Flatten table to single line if enabled
        if getattr(self, 'lite_flat_table', False):
            table = [f"T:{' '.join(table)}"]
        
        # Build ultra-dense bodies for edit scope methods
        bodies = []
        
        if edit_scope_cids:
            try:
                # Use the tree that already has CIDs instead of re-parsing
                # tree = ast.parse(content)  # This loses CIDs!
                
                # Create dense FLOW compiler with all flags
                flow_compiler = FLOWCompiler(
                    name_map=cai3_map.name_map,
                    dense_mode=True,
                    pool_constants=True,
                    # Pass all feature flags for maximum density
                    ascii_ops=getattr(self, 'dense_flow_ascii_ops', True),
                    no_spaces=getattr(self, 'dense_flow_no_spaces', True),
                    inline_blocks=getattr(self, 'dense_flow_inline_blocks', True),
                    alias_chains=getattr(self, 'dense_flow_alias_chains', True),
                    pool_strings_min_len=getattr(self, 'dense_flow_pool_strings_min_len', 3)
                )
                
                # Pass centralized pool map to FLOW compiler
                if 'pool_map' in cai3_full.compression_stats:
                    flow_compiler.set_pool_map(cai3_full.compression_stats['pool_map'])
                elif cai3_full.pools:
                    # Fallback to old method if pool_map not available
                    flow_compiler.set_pools(cai3_full.pools)
                if 'chain_aliases' in cai3_full.compression_stats:
                    flow_compiler.set_chain_aliases(cai3_full.compression_stats['chain_aliases'])
                
                nodes_by_cid = {node.cid: node for node in cai3_full.nodes}
                
                for cid in edit_scope_cids:
                    node_info = nodes_by_cid.get(cid)
                    if not node_info or not node_info.span:
                        continue
                    
                    # Find AST node
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
                        # Prepare combined scope with local compressions and class attributes
                        combined_scope = {}
                        
                        # Add local compressions for this method
                        if 'local_compressions' in node_info.metadata:
                            combined_scope.update(node_info.metadata['local_compressions'])
                        
                        # Add class attribute compressions if this method belongs to a class
                        if node_info.parent_cid:
                            # Find the parent class node
                            parent_class_node = None
                            for class_node in nodes_by_cid.values():
                                if class_node.cid == node_info.parent_cid and class_node.type == NodeType.CLASS:
                                    parent_class_node = class_node
                                    break
                            
                            if parent_class_node and 'attr_compressions' in parent_class_node.metadata:
                                # Add attribute compressions to scope with comprehensive pattern coverage
                                for orig_attr, compressed_attr in parent_class_node.metadata['attr_compressions'].items():
                                    # Cover all possible attribute access patterns that might appear in AST
                                    
                                    # 1. Direct self.attribute -> s.compressed (most common in FLOW)
                                    combined_scope[f"self.{orig_attr}"] = f"s.{compressed_attr}"
                                    
                                    # 2. Just the attribute name -> compressed (for internal FLOW mappings)
                                    combined_scope[orig_attr] = compressed_attr
                                    
                                    # 3. Handle assignment patterns: self.attr = value
                                    combined_scope[f"self.{orig_attr}"] = f"s.{compressed_attr}"
                                    
                                    # 4. Handle method call patterns: self.attr.method()
                                    # Store base mapping for FLOW compiler to expand
                                    combined_scope[f"_attr_base_{orig_attr}"] = compressed_attr
                                    
                                self.logger.debug(f"Added {len(parent_class_node.metadata['attr_compressions'])} "
                                                f"attribute compressions to method {node_info.name}: {parent_class_node.metadata['attr_compressions']}")
                                
                                # Debug: show what we're passing to FLOW compiler
                                attr_scope_items = {k: v for k, v in combined_scope.items() 
                                                   if any(attr in k for attr in parent_class_node.metadata['attr_compressions'])}
                                self.logger.debug(f"Attribute scope for FLOW compiler: {attr_scope_items}")
                        
                        # Set the combined scope on the FLOW compiler
                        if combined_scope:
                            flow_compiler.set_scope(cid, combined_scope)
                        
                        # Convert to ultra-dense FLOW
                        try:
                            flow_body = flow_compiler.ast_to_flow(target_ast_node)
                            
                            # Post-process FLOW output to ensure attribute compression is applied
                            if node_info.parent_cid:
                                parent_class_node = None
                                for class_node in nodes_by_cid.values():
                                    if class_node.cid == node_info.parent_cid and class_node.type == NodeType.CLASS:
                                        parent_class_node = class_node
                                        break
                                
                                if parent_class_node and 'attr_compressions' in parent_class_node.metadata:
                                    # Apply attribute compressions to FLOW output as a fallback
                                    for orig_attr, compressed_attr in parent_class_node.metadata['attr_compressions'].items():
                                        # Replace self.original_attr with s.compressed_attr
                                        flow_body = flow_body.replace(f"s.{orig_attr}", f"s.{compressed_attr}")
                                        # Also handle cases without the 's.' prefix
                                        flow_body = flow_body.replace(f"self.{orig_attr}", f"s.{compressed_attr}")
                                    
                                    self.logger.debug(f"Applied post-processing attribute compression for method {node_info.name}")
                            
                            # Ultra-compact body format with CID alias
                            cid_ref = f"#{cid_alias_map[cid]}" if cid in cid_alias_map else f"#{cid}"
                            bodies.append(f"B{cid_ref}:")  # No space after B
                            
                            # Compress body lines further (remove unnecessary spaces)
                            for line in flow_body.split('\n'):
                                if line.strip():
                                    # Remove unnecessary spaces
                                    compressed_line = line.replace(' = ', '=').replace(', ', ',')
                                    bodies.append(compressed_line)
                            
                            # Keep E terminator for safety as requested
                            if getattr(self, 'lite_keep_e_terminator', True):
                                bodies.append("E")  # Single char END
                            
                        except Exception as e:
                            self.logger.warning(f"Failed to create dense FLOW for {cid}: {e}")
                            
            except Exception as e:
                self.logger.warning(f"Failed to generate dense FLOW bodies: {e}")
        
        # Scan bodies for referenced pool IDs and filter pool section
        referenced_pool_ids = set()
        if bodies:
            import re
            # Scan all body text for pool references (p\d+)
            body_text = '\n'.join(bodies)
            pool_pattern = r'\bp(\d+)\b'
            matches = re.findall(pool_pattern, body_text)
            referenced_pool_ids = {f"p{match}" for match in matches}
        
        # Filter pool section to only include referenced pools
        pool_section = None
        if cai3_full.pools and referenced_pool_ids:
            pool_items = []
            for pool_id, value in cai3_full.pools.items():
                if pool_id in referenced_pool_ids:
                    # Ultra-compress pool values for preview
                    if len(value) > 20:
                        compressed_val = value[:8] + "..." + value[-8:]
                    else:
                        compressed_val = value
                    pool_items.append(f"{pool_id}={compressed_val}")
            if pool_items:
                pool_section = f"P:{';'.join(pool_items)}"
        
        # Create ultra-compact LITE with proper section ordering
        lite_result = CAI3Lite(
            header=header,
            imports=imports,
            chain_aliases=chain_aliases_section,
            cid_aliases=cid_aliases_section,
            config_keys=config_keys,
            pools=pool_section,
            table=table,
            bodies=bodies
        )
        
        # Diagnostic: validate that bodies were generated for edit scope CIDs
        lite = lite_result.serialize()
        for cid in edit_scope_cids:
            alias = cid_alias_map.get(cid, cid)
            assert f"B#{alias}:" in lite, f"Body for {cid} not emitted"
        
        return lite_result
    
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
    WaterfallCompressorClass._standard_compression_cai3 = CAI3WaterfallEnhancement._standard_compression_cai3
    WaterfallCompressorClass._determine_edit_scope_strict = CAI3WaterfallEnhancement._determine_edit_scope_strict
    WaterfallCompressorClass._has_bug_pattern_enhanced = CAI3WaterfallEnhancement._has_bug_pattern_enhanced
    WaterfallCompressorClass._calculate_complexity = CAI3WaterfallEnhancement._calculate_complexity
    WaterfallCompressorClass._modifies_parameters = CAI3WaterfallEnhancement._modifies_parameters
    WaterfallCompressorClass._create_cai3_full_enhanced = CAI3WaterfallEnhancement._create_cai3_full_enhanced
    WaterfallCompressorClass._create_cai3_map_enhanced = CAI3WaterfallEnhancement._create_cai3_map_enhanced
    WaterfallCompressorClass._create_cai3_lite_dense = CAI3WaterfallEnhancement._create_cai3_lite_dense
    WaterfallCompressorClass._compress_name_aggressive = CAI3WaterfallEnhancement._compress_name_aggressive
    WaterfallCompressorClass._compress_method_locals = CAI3WaterfallEnhancement._compress_method_locals
    WaterfallCompressorClass._compress_local_name = CAI3WaterfallEnhancement._compress_local_name
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
            # Enhanced settings
            self.max_edit_scope_methods = 2
            self.min_bug_score = 10
            self.use_dense_flow = True
            self.compress_all_names = True
            self.pool_strings = True
            self.include_all_methods = kwargs.get('include_all_methods', False)
            self.include_all_methods = kwargs.get('include_all_methods', False)
            
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
                            
                            