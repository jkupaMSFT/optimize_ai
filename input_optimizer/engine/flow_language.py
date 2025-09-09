# optimize_ai/input_optimizer/engine/flow_language.py
"""
FLOW language compiler for CAI3-LITE with ultra-dense syntax.
Achieves 60-70% token reduction through single-char macros and compressed syntax.
"""

import ast
from typing import Any, Dict, List, Optional, Union, Set, Tuple
import re
import logging
import hashlib
from collections import OrderedDict
import itertools
import keyword
import string
import base64
import zlib
import json

logger = logging.getLogger(__name__)

class FLOWCompiler:
    """Converts Python AST to dense FLOW representation and back"""
    
    # Add these class constants for keyword and operator filtering
    PYTHON_KEYWORDS = {
        'and', 'as', 'assert', 'break', 'class', 'continue', 'def', 'del',
        'elif', 'else', 'except', 'finally', 'for', 'from', 'global', 'if',
        'import', 'in', 'is', 'lambda', 'not', 'or', 'pass', 'raise', 'return',
        'try', 'while', 'with', 'yield', 'True', 'False', 'None'
    }
    
    INVALID_IDENTIFIER_CHARS = set('%#@$&*!?<>[]{}()/\\')
    
    # MACROS v2 - Ultra-dense single-character vocabulary
    MACROS_V2_DENSE = {
        # Core operations (single char)
        'L': 'let/assign',          # LET → L
        'C': 'call',                 # CALL → C
        'F': 'for',                  # FOR → F
        'I': 'if',                   # IF → I
        'E': 'elif',                 # ELIF → E
        'O': 'else',                 # ELSE → O
        'T': 'try',                  # TRY → T
        'X': 'except',               # CATCH → X
        'R': 'return',               # RET → R
        'Y': 'yield',                # YIELD → Y
        '+': 'increment',            # INC → +
        '-': 'decrement',            # DEC → -
        'A': 'append',               # APPEND → A
        'P': 'pop',                  # POP → P
        'N': 'is_none',              # ISNONE → N
        '!': 'not',                  # NOT → !
        '&': 'and',                  # AND → &
        '|': 'or',                   # OR → |
        'B': 'break',                # BREAK → B
        'K': 'continue',             # CONTINUE → K
        'W': 'while',                # WHILE → W
        'Z': 'with',                 # WITH → Z
        'D': 'del',                  # DEL → D
        '@': 'print',                # PRINT → @
        '_': 'pass',                 # PASS → _
        'S': 'setattr/item',         # SET → S
    }
    
    # Method abbreviation map for attribute expansion
    METHOD_ABBREVIATIONS = {
        'ap': 'append',
        'ex': 'extend', 
        'ge': 'get',
        'se': 'set',
        'up': 'update',
        'po': 'pop',
        'pu': 'push',
        'cl': 'clear',
        'co': 'copy',
        're': 'remove',
        'in': 'insert',
        'it': 'items',
        'ke': 'keys',
        'va': 'values',
        'sp': 'split',
        'jo': 'join',
        'st': 'strip',
        'lo': 'lower',
        'up': 'upper',
        'fi': 'find',
        'no': 'now',
        'ld': 'loads',  # Changed from 'lo' to 'ld' to avoid conflict
        'du': 'dumps',
        'pa': 'path',    # Added missing path abbreviation
        'is': 'is_directory'  # Added missing is_directory abbreviation
    }
    
    # Operator shortcuts - ASCII only, no Unicode
    OPERATOR_MAP = {
        '!=': '!=',
        '<=': '<=', 
        '>=': '>=',
        'not in': '!in',
        'in': 'in',
        'and': '&',
        'or': '|',
        'not': '!',
        # Keep == unchanged to avoid equality/assignment ambiguity
    }
    
    # Reverse mapping for decompression
    REVERSE_OPERATOR_MAP = {
        '!in': ' not in ',
        '!': 'not ',
        '&': ' and ',
        '|': ' or ',
        '!=': ' != ',
        '<=': ' <= ',
        '>=': ' >= ',
    }
    
    def __init__(self, name_map: Optional[Dict[str, str]] = None, 
                 dense_mode: bool = True,
                 pool_constants: bool = True,
                 # Change these defaults for reliability:
                 ascii_ops: bool = True,
                 no_spaces: bool = False,  # Keep spaces for clarity
                 inline_blocks: bool = False,  # Disable risky inline syntax
                 alias_chains: bool = True,
                 pool_strings_min_len: int = 10,  # Only pool longer strings
                 strict_mode: bool = True):  # NEW: enforce safe patterns
        """
        Initialize with name mapping and compression options.
        
        Args:
            name_map: Mapping of shortened names to original
            dense_mode: Use ultra-dense single-char macros
            pool_constants: Reference pooled constants instead of inline
            ascii_ops: Use ASCII operators like !=, <=, >=, in, !in instead of Unicode
            no_spaces: Remove spaces in expressions: x=y+z instead of x = y + z
            inline_blocks: Allow {…} and ; separators for compact blocks
            alias_chains: Emit D: alias dictionary for chained references
            pool_strings_min_len: Pool strings >= this length
            strict_mode: Enforce safe patterns by disabling risky optimizations
        """
        self.name_map = name_map or {}
        self.reverse_map = {v: k for k, v in self.name_map.items()}
        self.dense_mode = dense_mode
        self.pool_constants = pool_constants
        self.constant_pool = {}  # value -> pool_id
        self.pool_counter = 0
        
        # Initialize logger
        self.logger = logging.getLogger(__name__)
        
        # New feature flags
        self.ascii_ops = ascii_ops
        self.no_spaces = no_spaces
        self.inline_blocks = inline_blocks
        self.alias_chains = alias_chains
        self.pool_strings_min_len = pool_strings_min_len
        self.strict_mode = strict_mode
        
        # Initialize ultra dense flag
        self.use_ultra_dense = True  # Default value
        
        # Apply strict mode overrides if enabled
        if strict_mode:
            self.inline_blocks = False
            self.no_spaces = False
            # Disable ultra-dense try/for patterns
            self.use_ultra_dense = False
        
        # Track local variable compressions per scope
        self.local_compressions = {}
        self.current_scope_id = None
        
        # Alias chain tracking for D: dictionary
        self.alias_chains_dict = {}  # full_chain -> alias
        self.chain_aliases = {}  # alias -> full_chain
        
        # Hash to value mapping for resolving #xxxx references
        self.hash_to_value = {}  # #xxxx -> original_value
        
        # RAW fallback infrastructure
        self.unsupported_nodes = set()  # Track what we can't handle
        self.raw_blocks = {}  # Store RAW block mappings
        self.raw_counter = 0
    
    def _stable_hash(self, value: str, length: int = 8) -> str:
        """Generate deterministic hash for any string value."""
        return hashlib.sha256(value.encode()).hexdigest()[:length]

    def _create_raw_block(self, node: ast.AST, source_segment: str = None) -> str:
        """Create a RAW block for unsupported AST nodes."""
        # Generate stable ID
        raw_id = f"raw_{self._stable_hash(ast.dump(node), 8)}"
        
        # Store the node for later recovery
        if source_segment:
            # Store original source if available
            compressed = base64.b64encode(zlib.compress(source_segment.encode())).decode()
            self.raw_blocks[raw_id] = {
                'type': 'source',
                'data': compressed,
                'node_type': type(node).__name__
            }
        else:
            # Store AST as JSON
            ast_json = self._ast_to_json(node)
            compressed = base64.b64encode(zlib.compress(json.dumps(ast_json).encode())).decode()
            self.raw_blocks[raw_id] = {
                'type': 'ast',
                'data': compressed,
                'node_type': type(node).__name__
            }
        
        return f"RAW{{{raw_id}}}"
    
    def _ast_to_json(self, node: ast.AST) -> dict:
        """Convert AST to JSON-serializable format."""
        if isinstance(node, ast.AST):
            result = {'_type': type(node).__name__}
            for field, value in ast.iter_fields(node):
                if isinstance(value, list):
                    result[field] = [self._ast_to_json(item) for item in value]
                elif isinstance(value, ast.AST):
                    result[field] = self._ast_to_json(value)
                else:
                    result[field] = value
            return result
        return node
    
    def _json_to_ast(self, data: dict) -> ast.AST:
        """Reconstruct AST from JSON."""
        if isinstance(data, dict) and '_type' in data:
            node_class = getattr(ast, data['_type'])
            kwargs = {}
            for key, value in data.items():
                if key == '_type':
                    continue
                if isinstance(value, list):
                    kwargs[key] = [self._json_to_ast(item) for item in value]
                elif isinstance(value, dict):
                    kwargs[key] = self._json_to_ast(value)
                else:
                    kwargs[key] = value
            
            node = node_class(**kwargs)
            
            # Add required AST attributes if they're missing
            return self._fix_ast_node_attributes(node)
            
        return data

    def _get_or_create_pool_id(self, value: Any) -> str:
        """Deterministically assign pool IDs based on sorted order."""
        key = str(value) if not isinstance(value, str) else value
        if key not in self.constant_pool:
            # Use deterministic numbering based on sorted insertion
            pool_num = len(self.constant_pool)
            self.constant_pool[key] = f"p{pool_num}"
        return self.constant_pool[key]
    
    def set_scope(self, scope_id: str, local_map: Dict[str, str]):
        """Set local variable compressions for current scope"""
        self.current_scope_id = scope_id
        self.local_compressions[scope_id] = local_map
    
    def set_pools(self, pools: Dict[str, str]):
        """Set external string/constant pools for reference"""
        # Reverse the mapping for lookup: value -> pool_id
        for pool_id, value in pools.items():
            self.constant_pool[value] = pool_id
    
    def set_pool_map(self, pool_map: Dict[str, str]):
        """Set centralized pool map (value -> pool_id) directly"""
        self.constant_pool = pool_map.copy()
    
    def set_pools(self, pools: Dict[str, Any]):
        """Set pools for p\d+ resolution"""
        self.pools = pools if pools else {}
    
    def set_chain_aliases(self, chain_aliases: Dict[str, str]):
        """Set chain aliases from external source (e.g., g1=s.config.get)"""
        self.chain_aliases = chain_aliases if chain_aliases else {}
        # Also reverse the mapping for lookup: full_chain -> alias
        for alias, full_chain in chain_aliases.items():
            self.alias_chains_dict[full_chain] = alias

    def set_hash_mapping(self, hash_to_value: Dict[str, str]):
        """Set hash-to-value mapping for resolving #xxxx references"""
        if hash_to_value:
            # Convert external string format to internal metadata format
            self.hash_to_value = {}
            for hash_ref, value in hash_to_value.items():
                if isinstance(value, str):
                    # Convert to metadata format for internal use
                    self.hash_to_value[hash_ref] = {
                        'value': value,
                        'type': 'string',
                        'needs_quotes': True
                    }
                else:
                    # For non-string values, store directly (backward compatibility)
                    self.hash_to_value[hash_ref] = value
        else:
            self.hash_to_value = {}
    
    def get_hash_value(self, hash_ref: str):
        """Get hash value with backward compatibility for both old and new formats"""
        if hash_ref not in self.hash_to_value:
            return None
        
        hash_entry = self.hash_to_value[hash_ref]
        if isinstance(hash_entry, dict):
            return hash_entry['value']  # Extract value from metadata
        else:
            return hash_entry  # Old format, return directly
    
    def get_hash_metadata(self, hash_ref: str):
        """Get full hash metadata (new format only)"""
        if hash_ref not in self.hash_to_value:
            return None
        
        hash_entry = self.hash_to_value[hash_ref]
        if isinstance(hash_entry, dict):
            return hash_entry
        else:
            # Convert old format to metadata format
            return {
                'value': hash_entry,
                'type': 'string' if isinstance(hash_entry, str) else 'other',
                'needs_quotes': isinstance(hash_entry, str)
            }
    
    def get_hash_value_for_compatibility(self, hash_ref: str):
        """
        Get hash value in old format for external compatibility.
        This ensures that external code still receives the raw string value.
        """
        return self.get_hash_value(hash_ref)
    
    def get_legacy_hash_mapping(self):
        """
        Get hash mapping in legacy format (hash_ref -> raw_value) for external compatibility.
        Used when transferring to CAI3Full or other external systems.
        """
        legacy_mapping = {}
        for hash_ref, hash_entry in self.hash_to_value.items():
            if isinstance(hash_entry, dict):
                legacy_mapping[hash_ref] = hash_entry['value']
            else:
                legacy_mapping[hash_ref] = hash_entry
        return legacy_mapping
    
    def _get_pool_id(self, value: Any) -> str:
        """Get pool ID for a constant from centralized pool"""
        if not self.pool_constants:
            return None
            
        # Convert value to hashable form
        if isinstance(value, (list, dict)):
            key = str(value)
        else:
            key = value
            
        # Check if string meets minimum length requirement
        if isinstance(value, str) and len(value) < self.pool_strings_min_len:
            return None
            
        # Only return pool ID if it exists in the centralized pool
        return self.constant_pool.get(key)
    
    def _can_inline_block(self, statements: List[ast.AST]) -> bool:
        """Check if a block can be inlined (short and simple enough)"""
        if not self.inline_blocks or not self.dense_mode:
            return False
        
        # Only inline blocks with 1-2 statements
        if len(statements) > 2:
            return False
        
        # Don't inline if there are nested control structures
        for stmt in statements:
            if NodeSupportValidator.is_control_structure(stmt):
                return False
        
        return True
    
    def _inline_statements(self, statements: List[ast.AST]) -> str:
        """Convert statements to inline form with ; separators"""
        flows = []
        for stmt in statements:
            flow = self.ast_to_flow(stmt, 0)  # No indentation for inline
            if flow:
                flows.append(flow.strip())  # Remove any leading/trailing whitespace
        return ';'.join(flows)
    
    def ast_to_flow(self, node: ast.AST, indent: int = 0, source_lines: List[str] = None) -> str:
        """Convert AST to FLOW with RAW fallback for unsupported nodes."""
        indent_str = ' ' * indent if self.dense_mode else '  ' * indent
        
        # Check if node needs RAW fallback using comprehensive validator
        if NodeSupportValidator.needs_raw_fallback(node):
            # Unsupported node - use RAW fallback
            node_type = type(node).__name__
            self.unsupported_nodes.add(node_type)
            
            # Try to get original source if available
            source_segment = None
            if source_lines and hasattr(node, 'lineno'):
                try:
                    start_line = max(0, node.lineno - 1)
                    end_line = min(len(source_lines), getattr(node, 'end_lineno', node.lineno))
                    source_segment = '\n'.join(source_lines[start_line:end_line])
                except (AttributeError, IndexError):
                    pass
            
            raw_block = self._create_raw_block(node, source_segment)
            return f"{indent_str}{raw_block}"
        
        # Node is supported - use existing implementation
        node_type = type(node).__name__
        
        if isinstance(node, ast.FunctionDef):
            return self._existing_function_def_handler(node, indent, source_lines)
        elif isinstance(node, ast.Assign):
            return self._existing_assign_handler(node, indent)
        elif isinstance(node, ast.AugAssign):
            return self._existing_aug_assign_handler(node, indent)
        elif isinstance(node, ast.Return):
            return self._existing_return_handler(node, indent)
        elif isinstance(node, ast.If):
            return self._existing_if_handler(node, indent, source_lines)
        elif isinstance(node, ast.For):
            return self._existing_for_handler(node, indent, source_lines)
        elif isinstance(node, ast.While):
            return self._existing_while_handler(node, indent, source_lines)
        elif isinstance(node, ast.Try):
            return self._existing_try_handler(node, indent, source_lines)
        elif isinstance(node, ast.Expr):
            return self._existing_expr_handler(node, indent)
        elif isinstance(node, ast.Break):
            return self._existing_break_handler(node, indent)
        elif isinstance(node, ast.Continue):
            return self._existing_continue_handler(node, indent)
        elif isinstance(node, ast.Pass):
            return self._existing_pass_handler(node, indent)
        elif isinstance(node, ast.Raise):
            return self._existing_raise_handler(node, indent)
        elif isinstance(node, ast.Delete):
            return self._existing_delete_handler(node, indent)
        elif isinstance(node, ast.With):
            return self._existing_with_handler(node, indent, source_lines)
        else:
            # This should not happen if validator is working correctly
            # Fallback to RAW block just in case
            node_type = type(node).__name__
            self.unsupported_nodes.add(node_type)
            raw_block = self._create_raw_block(node, None)
            return f"{indent_str}{raw_block}"

    def _existing_function_def_handler(self, node: ast.FunctionDef, indent: int, source_lines: List[str] = None) -> str:
        """Existing FunctionDef logic, refactored."""
        indent_str = ' ' * indent if self.dense_mode else '  ' * indent
        
        # Build function signature
        args = []
        for arg in node.args.args:
            args.append(arg.arg)
        
        # Handle defaults
        if node.args.defaults:
            num_defaults = len(node.args.defaults)
            for i, default in enumerate(node.args.defaults):
                arg_index = len(args) - num_defaults + i
                default_val = self._process_value(default)
                args[arg_index] = f"{args[arg_index]}={default_val}"
        
        if self.dense_mode:
            func_header = f"{indent_str}def {node.name}({','.join(args)}):"
        else:
            func_header = f"{indent_str}def {node.name}({', '.join(args)}):"
        
        # Function body processing
        body_flows = [func_header]
        for stmt in node.body:
            # Skip docstrings (string constants as first statement)
            if (isinstance(stmt, ast.Expr) and 
                isinstance(stmt.value, (ast.Str, ast.Constant)) and
                isinstance(getattr(stmt.value, 'value', getattr(stmt.value, 's', None)), str)):
                continue  # Skip docstrings
            flow = self.ast_to_flow(stmt, indent + 1, source_lines)
            if flow:
                body_flows.append(flow)
        return '\n'.join(body_flows)

    def _existing_assign_handler(self, node: ast.Assign, indent: int) -> str:
        """Existing Assign logic, refactored."""
        # Use minimal indentation in dense mode (single space per level)
        indent_str = ' ' * indent if self.dense_mode else '  ' * indent
        
        # Dense assignment: Lx=val or L x=val based on no_spaces flag
        target = self._process_target(node.targets[0])
        value = self._process_value(node.value)
        macro = 'L' if self.dense_mode else 'LET'
        
        if self.no_spaces and self.dense_mode:
            return f"{indent_str}{macro}{target}={value}"  # No space after macro
        elif self.dense_mode:
            return f"{indent_str}{macro} {target} = {value}"
        else:
            return f"{indent_str}{macro} {target} = {value}"

    def _existing_aug_assign_handler(self, node: ast.AugAssign, indent: int) -> str:
        """Existing AugAssign logic, refactored."""
        # Use minimal indentation in dense mode (single space per level)
        indent_str = ' ' * indent if self.dense_mode else '  ' * indent
        
        # Handle += -= etc
        target = self._process_target(node.target)
        op = self._get_aug_op(node.op)
        value = self._process_value(node.value)
        
        if self.dense_mode:
            if op == '+=' and value == '1':
                return f"{indent_str}+{target}"  # Ultra-compact increment, no space after macro
            elif op == '-=' and value == '1':
                return f"{indent_str}-{target}"  # Ultra-compact decrement, no space after macro
            else:
                # S x=x+val for other augmented assigns, no space after macro
                return f"{indent_str}S{target}={target}{op[0]}{value}"
        else:
            return f"{indent_str}SET {target} = {target} {op[0]} {value}"

    def _existing_return_handler(self, node: ast.Return, indent: int) -> str:
        """Existing Return logic, refactored."""
        # Use minimal indentation in dense mode (single space per level)
        indent_str = ' ' * indent if self.dense_mode else '  ' * indent
        
        # R val or just R, no space after macro in dense mode
        macro = 'R' if self.dense_mode else 'RET'
        if node.value:
            value = self._process_value(node.value)
            if self.dense_mode:
                return f"{indent_str}{macro}{value}"  # No space after macro
            else:
                return f"{indent_str}{macro} {value}"
        return f"{indent_str}{macro}"
    
    def _existing_if_handler(self, node: ast.If, indent: int, source_lines: List[str] = None) -> str:
        """Existing If logic, refactored."""
        # Use minimal indentation in dense mode (single space per level)
        indent_str = ' ' * indent if self.dense_mode else '  ' * indent
        
        # Dense if: I(cond):{body} or I(cond):body for inline vs multiline
        lines = []
        condition = self._process_condition(node.test)
        macro_if = 'I' if self.dense_mode else 'IF'
        
        # Check if we can inline the if body
        if self._can_inline_block(node.body):
            inline_body = self._inline_statements(node.body)
            if self.dense_mode:
                lines.append(f"{indent_str}{macro_if}({condition}):{{{inline_body}}}")
            else:
                lines.append(f"{indent_str}{macro_if} {condition}: {{{inline_body}}}")
        else:
            # Traditional multiline format
            if self.dense_mode:
                lines.append(f"{indent_str}{macro_if}({condition}):")
            else:
                lines.append(f"{indent_str}{macro_if} {condition}:")
            
            for stmt in node.body:
                flow = self.ast_to_flow(stmt, indent + 1, source_lines)
                if flow:
                    lines.append(flow)
        
        # Handle elif/else
        if node.orelse:
            if len(node.orelse) == 1 and isinstance(node.orelse[0], ast.If):
                # elif
                elif_node = node.orelse[0]
                elif_condition = self._process_condition(elif_node.test)
                macro_elif = 'E' if self.dense_mode else 'ELIF'
                
                # Check if we can inline the elif body
                if self._can_inline_block(elif_node.body):
                    elif_inline_body = self._inline_statements(elif_node.body)
                    if self.dense_mode:
                        lines.append(f"{indent_str}{macro_elif}({elif_condition}):{{{elif_inline_body}}}")
                    else:
                        lines.append(f"{indent_str}{macro_elif} {elif_condition}: {{{elif_inline_body}}}")
                else:
                    if self.dense_mode:
                        lines.append(f"{indent_str}{macro_elif}({elif_condition}):")
                    else:
                        lines.append(f"{indent_str}{macro_elif} {elif_condition}:")
                    
                    for stmt in elif_node.body:
                        flow = self.ast_to_flow(stmt, indent + 1, source_lines)
                        if flow:
                            lines.append(flow)
                
                # Handle else after elif
                if elif_node.orelse:
                    macro_else = 'O' if self.dense_mode else 'ELSE'
                    if self._can_inline_block(elif_node.orelse):
                        else_inline_body = self._inline_statements(elif_node.orelse)
                        if self.dense_mode:
                            lines.append(f"{indent_str}{macro_else}:{{{else_inline_body}}}")
                        else:
                            lines.append(f"{indent_str}{macro_else}: {{{else_inline_body}}}")
                    else:
                        if self.dense_mode:
                            lines.append(f"{indent_str}{macro_else}:")
                        else:
                            lines.append(f"{indent_str}{macro_else}:")
                        
                        for stmt in elif_node.orelse:
                            flow = self.ast_to_flow(stmt, indent + 1, source_lines)
                            if flow:
                                lines.append(flow)
            else:
                # Regular else (not elif)
                macro_else = 'O' if self.dense_mode else 'ELSE'
                if self._can_inline_block(node.orelse):
                    else_inline_body = self._inline_statements(node.orelse)
                    if self.dense_mode:
                        lines.append(f"{indent_str}{macro_else}:{{{else_inline_body}}}")
                    else:
                        lines.append(f"{indent_str}{macro_else}: {{{else_inline_body}}}")
                else:
                    if self.dense_mode:
                        lines.append(f"{indent_str}{macro_else}:")
                    else:
                        lines.append(f"{indent_str}{macro_else}:")
                    
                    for stmt in node.orelse:
                        flow = self.ast_to_flow(stmt, indent + 1, source_lines)
                        if flow:
                            lines.append(flow)
        
        return '\n'.join(lines)
    
    def _existing_for_handler(self, node: ast.For, indent: int, source_lines: List[str] = None) -> str:
        """Existing For logic, refactored."""
        indent_str = ' ' * indent if self.dense_mode else '  ' * indent
        
        target = self._process_target(node.target)
        iter_val = self._process_value(node.iter)
        macro = 'F' if self.dense_mode else 'FOR'
        
        lines = []
        
        # Check if we can inline the for body
        if self._can_inline_block(node.body):
            inline_body = self._inline_statements(node.body)
            if self.dense_mode:
                lines.append(f"{indent_str}{macro}{target}in{iter_val}:{{{inline_body}}}")
            else:
                lines.append(f"{indent_str}{macro} {target} in {iter_val}: {{{inline_body}}}")
        else:
            # Traditional multiline format
            if self.dense_mode:
                lines.append(f"{indent_str}{macro}{target}in{iter_val}:")
            else:
                lines.append(f"{indent_str}{macro} {target} in {iter_val}:")
            
            for stmt in node.body:
                flow = self.ast_to_flow(stmt, indent + 1, source_lines)
                if flow:
                    lines.append(flow)
        
        # Handle else clause
        if node.orelse:
            macro_else = 'O' if self.dense_mode else 'ELSE'
            if self._can_inline_block(node.orelse):
                else_inline_body = self._inline_statements(node.orelse)
                if self.dense_mode:
                    lines.append(f"{indent_str}{macro_else}:{{{else_inline_body}}}")
                else:
                    lines.append(f"{indent_str}{macro_else}: {{{else_inline_body}}}")
            else:
                if self.dense_mode:
                    lines.append(f"{indent_str}{macro_else}:")
                else:
                    lines.append(f"{indent_str}{macro_else}:")
                
                for stmt in node.orelse:
                    flow = self.ast_to_flow(stmt, indent + 1, source_lines)
                    if flow:
                        lines.append(flow)
        
        return '\n'.join(lines)
    
    def _existing_while_handler(self, node: ast.While, indent: int, source_lines: List[str] = None) -> str:
        """Existing While logic, refactored."""
        indent_str = ' ' * indent if self.dense_mode else '  ' * indent
        
        condition = self._process_condition(node.test)
        macro = 'W' if self.dense_mode else 'WHILE'
        
        lines = []
        
        # Check if we can inline the while body
        if self._can_inline_block(node.body):
            inline_body = self._inline_statements(node.body)
            if self.dense_mode:
                lines.append(f"{indent_str}{macro}({condition}):{{{inline_body}}}")
            else:
                lines.append(f"{indent_str}{macro} {condition}: {{{inline_body}}}")
        else:
            # Traditional multiline format
            if self.dense_mode:
                lines.append(f"{indent_str}{macro}({condition}):")
            else:
                lines.append(f"{indent_str}{macro} {condition}:")
            
            for stmt in node.body:
                flow = self.ast_to_flow(stmt, indent + 1, source_lines)
                if flow:
                    lines.append(flow)
        
        # Handle else clause
        if node.orelse:
            macro_else = 'O' if self.dense_mode else 'ELSE'
            if self._can_inline_block(node.orelse):
                else_inline_body = self._inline_statements(node.orelse)
                if self.dense_mode:
                    lines.append(f"{indent_str}{macro_else}:{{{else_inline_body}}}")
                else:
                    lines.append(f"{indent_str}{macro_else}: {{{else_inline_body}}}")
            else:
                if self.dense_mode:
                    lines.append(f"{indent_str}{macro_else}:")
                else:
                    lines.append(f"{indent_str}{macro_else}:")
                
                for stmt in node.orelse:
                    flow = self.ast_to_flow(stmt, indent + 1, source_lines)
                    if flow:
                        lines.append(flow)
        
        return '\n'.join(lines)
    
    def _existing_try_handler(self, node: ast.Try, indent: int, source_lines: List[str] = None) -> str:
        """Existing Try logic, refactored."""
        indent_str = ' ' * indent if self.dense_mode else '  ' * indent
        
        macro = 'T' if self.dense_mode else 'TRY'
        lines = []
        
        # Check if we can inline the try body
        if self._can_inline_block(node.body):
            inline_body = self._inline_statements(node.body)
            if self.dense_mode:
                lines.append(f"{indent_str}{macro}:{{{inline_body}}}")
            else:
                lines.append(f"{indent_str}{macro}: {{{inline_body}}}")
        else:
            # Traditional multiline format
            if self.dense_mode:
                lines.append(f"{indent_str}{macro}:")
            else:
                lines.append(f"{indent_str}{macro}:")
            
            for stmt in node.body:
                flow = self.ast_to_flow(stmt, indent + 1, source_lines)
                if flow:
                    lines.append(flow)
        
        # Handle exception handlers
        for handler in node.handlers:
            macro_except = 'X' if self.dense_mode else 'EXCEPT'
            
            if handler.type:
                exc_type = self._process_value(handler.type)
                if handler.name:
                    if self.dense_mode:
                        lines.append(f"{indent_str}{macro_except}({exc_type}){handler.name}:")
                    else:
                        lines.append(f"{indent_str}{macro_except} {exc_type} as {handler.name}:")
                else:
                    if self.dense_mode:
                        lines.append(f"{indent_str}{macro_except}({exc_type}):")
                    else:
                        lines.append(f"{indent_str}{macro_except} {exc_type}:")
            else:
                if self.dense_mode:
                    lines.append(f"{indent_str}{macro_except}:")
                else:
                    lines.append(f"{indent_str}{macro_except}:")
            
            # Check if we can inline the handler body
            if self._can_inline_block(handler.body):
                inline_body = self._inline_statements(handler.body)
                if self.dense_mode:
                    lines[-1] = lines[-1] + f"{{{inline_body}}}"
                else:
                    lines[-1] = lines[-1] + f" {{{inline_body}}}"
            else:
                for stmt in handler.body:
                    flow = self.ast_to_flow(stmt, indent + 1, source_lines)
                    if flow:
                        lines.append(flow)
        
        # Handle else clause
        if node.orelse:
            macro_else = 'O' if self.dense_mode else 'ELSE'
            if self._can_inline_block(node.orelse):
                else_inline_body = self._inline_statements(node.orelse)
                if self.dense_mode:
                    lines.append(f"{indent_str}{macro_else}:{{{else_inline_body}}}")
                else:
                    lines.append(f"{indent_str}{macro_else}: {{{else_inline_body}}}")
            else:
                if self.dense_mode:
                    lines.append(f"{indent_str}{macro_else}:")
                else:
                    lines.append(f"{indent_str}{macro_else}:")
                
                for stmt in node.orelse:
                    flow = self.ast_to_flow(stmt, indent + 1, source_lines)
                    if flow:
                        lines.append(flow)
        
        # Handle finally clause
        if node.finalbody:
            macro_finally = 'Y' if self.dense_mode else 'FINALLY'
            if self._can_inline_block(node.finalbody):
                finally_inline_body = self._inline_statements(node.finalbody)
                if self.dense_mode:
                    lines.append(f"{indent_str}{macro_finally}:{{{finally_inline_body}}}")
                else:
                    lines.append(f"{indent_str}{macro_finally}: {{{finally_inline_body}}}")
            else:
                if self.dense_mode:
                    lines.append(f"{indent_str}{macro_finally}:")
                else:
                    lines.append(f"{indent_str}{macro_finally}:")
                
                for stmt in node.finalbody:
                    flow = self.ast_to_flow(stmt, indent + 1, source_lines)
                    if flow:
                        lines.append(flow)
        
        return '\n'.join(lines)
    
    def _existing_expr_handler(self, node: ast.Expr, indent: int) -> str:
        """Existing Expr logic, refactored."""
        indent_str = ' ' * indent if self.dense_mode else '  ' * indent
        
        # Expression statement
        value = self._process_value(node.value)
        return f"{indent_str}{value}"
    
    def _existing_break_handler(self, node: ast.Break, indent: int) -> str:
        """Existing Break logic, refactored."""
        indent_str = ' ' * indent if self.dense_mode else '  ' * indent
        macro = 'B' if self.dense_mode else 'BREAK'
        return f"{indent_str}{macro}"
    
    def _existing_continue_handler(self, node: ast.Continue, indent: int) -> str:
        """Existing Continue logic, refactored."""
        indent_str = ' ' * indent if self.dense_mode else '  ' * indent
        macro = 'K' if self.dense_mode else 'CONTINUE'
        return f"{indent_str}{macro}"
    
    def _existing_pass_handler(self, node: ast.Pass, indent: int) -> str:
        """Existing Pass logic, refactored."""
        indent_str = ' ' * indent if self.dense_mode else '  ' * indent
        macro = '_' if self.dense_mode else 'PASS'
        return f"{indent_str}{macro}"
    
    def _existing_raise_handler(self, node: ast.Raise, indent: int) -> str:
        """Existing Raise logic, refactored."""
        indent_str = ' ' * indent if self.dense_mode else '  ' * indent
        macro = 'R' if self.dense_mode else 'RAISE'  # Note: conflicts with Return, need different macro
        
        if node.exc:
            exc = self._process_value(node.exc)
            if node.cause:
                cause = self._process_value(node.cause)
                if self.dense_mode:
                    return f"{indent_str}RZ{exc},{cause}"  # Use RZ for raise to avoid conflict
                else:
                    return f"{indent_str}{macro} {exc} from {cause}"
            else:
                if self.dense_mode:
                    return f"{indent_str}RZ{exc}"
                else:
                    return f"{indent_str}{macro} {exc}"
        else:
            if self.dense_mode:
                return f"{indent_str}RZ"
            else:
                return f"{indent_str}{macro}"
    
    def _existing_delete_handler(self, node: ast.Delete, indent: int) -> str:
        """Existing Delete logic, refactored."""
        indent_str = ' ' * indent if self.dense_mode else '  ' * indent
        macro = 'D' if self.dense_mode else 'DEL'
        
        targets = [self._process_target(target) for target in node.targets]
        if self.dense_mode:
            return f"{indent_str}{macro}{','.join(targets)}"
        else:
            return f"{indent_str}{macro} {', '.join(targets)}"
    
    def _existing_with_handler(self, node: ast.With, indent: int, source_lines: List[str] = None) -> str:
        """Existing With logic, refactored."""
        indent_str = ' ' * indent if self.dense_mode else '  ' * indent
        
        macro = 'Z' if self.dense_mode else 'WITH'
        lines = []
        
        # Handle with items (context managers)
        items = []
        for item in node.items:
            context_expr = self._process_value(item.context_expr)
            if item.optional_vars:
                var = self._process_target(item.optional_vars)
                if self.dense_mode:
                    items.append(f"{context_expr}>{var}")
                else:
                    items.append(f"{context_expr} as {var}")
            else:
                items.append(context_expr)
        
        # Check if we can inline the with body
        if self._can_inline_block(node.body):
            inline_body = self._inline_statements(node.body)
            if self.dense_mode:
                lines.append(f"{indent_str}{macro}{','.join(items)}:{{{inline_body}}}")
            else:
                lines.append(f"{indent_str}{macro} {', '.join(items)}: {{{inline_body}}}")
        else:
            # Traditional multiline format
            if self.dense_mode:
                lines.append(f"{indent_str}{macro}{','.join(items)}:")
            else:
                lines.append(f"{indent_str}{macro} {', '.join(items)}:")
            
            for stmt in node.body:
                flow = self.ast_to_flow(stmt, indent + 1, source_lines)
                if flow:
                    lines.append(flow)
        
        return '\n'.join(lines)

    def _process_target(self, node: ast.AST) -> str:
        """Process assignment target."""
        if isinstance(node, ast.Name):
            # Apply name mapping if available
            name = node.id
            if self.current_scope_id and self.current_scope_id in self.local_compressions:
                return self.local_compressions[self.current_scope_id].get(name, name)
            # Only apply global compressions when no local scope is present
            return self.name_map.get(name, name)
        elif isinstance(node, ast.Attribute):
            obj = self._process_value(node.value)
            attr = node.attr
            return f"{obj}.{attr}"
        elif isinstance(node, ast.Subscript):
            obj = self._process_value(node.value)
            index = self._process_value(node.slice)
            return f"{obj}[{index}]"
        elif isinstance(node, ast.Tuple):
            elements = [self._process_target(elt) for elt in node.elts]
            return f"({','.join(elements)})" if self.dense_mode else f"({', '.join(elements)})"
        elif isinstance(node, ast.List):
            elements = [self._process_target(elt) for elt in node.elts]
            return f"[{','.join(elements)}]" if self.dense_mode else f"[{', '.join(elements)}]"
        return "?"
    
    def _process_value(self, node: ast.AST) -> str:
        """Process value with compression and alias resolution."""
        # Check if this node needs RAW fallback first
        if NodeSupportValidator.needs_raw_fallback(node):
            # Create a RAW block for unsupported expressions
            node_type = type(node).__name__
            self.unsupported_nodes.add(node_type)
            raw_block = self._create_raw_block(node, None)
            return raw_block
        
        if isinstance(node, ast.Name):
            # Apply name mapping if available
            name = node.id
            if self.current_scope_id and self.current_scope_id in self.local_compressions:
                return self.local_compressions[self.current_scope_id].get(name, name)
            # Only apply global compressions when no local scope is present
            return self.name_map.get(name, name)
        elif isinstance(node, ast.Constant):
            # Pool constants if enabled and meet minimum length
            if (self.pool_constants and isinstance(node.value, str) and 
                len(node.value) >= self.pool_strings_min_len):
                pool_id = self._get_pool_id(node.value)
                if pool_id:
                    return pool_id  # Return pN directly, not $pN
            
            if isinstance(node.value, str):
                # In dense mode, apply hash compression for long strings like _compress_value does
                if self.dense_mode and len(node.value) > 8:  # Changed from 3 to 8 to be less aggressive
                    # Check for pool reference first
                    pool_id = self._get_pool_id(node.value)
                    if pool_id:
                        return pool_id  # Return pN directly
                    
                    # Generate hash reference for long strings
                    hash_ref = f"hash_{self._stable_hash(node.value, 10)}"
                    self.hash_to_value[hash_ref] = {
                        'value': node.value,
                        'type': 'string',
                        'needs_quotes': True
                    }
                    return hash_ref
                else:
                    # Use single quotes for compactness (short strings or non-dense mode)
                    return f"'{node.value}'"
            elif node.value is None:
                return "N" if self.dense_mode else "None"
            elif node.value is True:
                return "T" if self.dense_mode else "True"
            elif node.value is False:
                return "F" if self.dense_mode else "False"
            return str(node.value)
        elif isinstance(node, ast.Attribute):
            # Build full chain once
            chain = []
            cur = node
            while isinstance(cur, ast.Attribute):
                chain.append(cur.attr)
                cur = cur.value
            base = self._process_value(cur)  # will return 's' for self, etc.
            chain.append(base)
            chain.reverse()
            full = ".".join(chain)            # e.g., s.config.get
            ali = self._maybe_alias(full)
            return ali if ali else full
        elif isinstance(node, ast.Call):
            return self._process_call(node)
        elif isinstance(node, ast.List):
            if not node.elts:  # Empty list
                return "[]"
            items = [self._process_value(e) for e in node.elts]
            if self.dense_mode:
                return f"[{','.join(items)}]"
            return f"[{', '.join(items)}]"
        elif isinstance(node, ast.Dict):
            if not node.keys:  # Empty dict
                return "{}"
            pairs = []
            for k, v in zip(node.keys, node.values):
                key = self._process_value(k) if k else ''
                val = self._process_value(v)
                if k:
                    if self.dense_mode:
                        pairs.append(f"{key}:{val}")
                    else:
                        pairs.append(f"{key}: {val}")
            if self.dense_mode:
                return f"{{{','.join(pairs)}}}"
            return f"{{{', '.join(pairs)}}}"
        elif isinstance(node, ast.BinOp):
            left = self._process_value(node.left)
            right = self._process_value(node.right)
            op = self._get_binop(node.op)
            if self.no_spaces and self.dense_mode:
                return f"{left}{op}{right}"  # No spaces
            elif self.dense_mode:
                return f"{left} {op} {right}"  # With spaces
            return f"{left} {op} {right}"
        elif isinstance(node, ast.UnaryOp):
            operand = self._process_value(node.operand)
            if isinstance(node.op, ast.Not):
                return f"!{operand}" if self.dense_mode else f"NOT {operand}"
            elif isinstance(node.op, ast.USub):
                return f"-{operand}"
            elif isinstance(node.op, ast.UAdd):
                return f"+{operand}"
            return f"?{operand}"
        elif isinstance(node, ast.Compare):
            return self._process_condition(node)
        elif isinstance(node, ast.BoolOp):
            # Handle boolean operations (and, or)
            if isinstance(node.op, ast.And):
                parts = [self._process_value(v) for v in node.values]
                if self.dense_mode:
                    return f"({'&'.join(parts)})"
                return f"({' and '.join(parts)})"
            elif isinstance(node.op, ast.Or):
                parts = [self._process_value(v) for v in node.values]
                if self.dense_mode:
                    return f"({'|'.join(parts)})"
                return f"({' or '.join(parts)})"
            return "?"
        elif isinstance(node, ast.IfExp):
            # Ternary: compact form
            cond = self._process_condition(node.test)
            true_val = self._process_value(node.body)
            false_val = self._process_value(node.orelse)
            if self.dense_mode:
                return f"({true_val}?{cond}:{false_val})"  # C-style ternary
            return f"({true_val} if {cond} else {false_val})"
        elif isinstance(node, ast.Subscript):
            obj = self._process_value(node.value)
            index = self._process_value(node.slice)
            return f"{obj}[{index}]"
        elif isinstance(node, ast.Slice):
            lower = self._process_value(node.lower) if node.lower else ''
            upper = self._process_value(node.upper) if node.upper else ''
            step = f":{self._process_value(node.step)}" if node.step else ''
            return f"{lower}:{upper}{step}"
        elif isinstance(node, ast.JoinedStr):
            # f-string - ultra compact
            parts = []
            for part in node.values:
                if isinstance(part, ast.Str):
                    parts.append(part.s)
                elif isinstance(part, ast.FormattedValue):
                    val = self._process_value(part.value)
                    parts.append(f"{{{val}}}")
                return f'f"{" ".join(parts)}"'
        return "?"
    
    def get_alias_chains_dict(self) -> Dict[str, str]:
        """Get the alias chains dictionary for D: section"""
        return self.alias_chains_dict
    
    def get_referenced_pools(self) -> Set[str]:
        """Get set of pool IDs that were actually referenced during compilation"""
        referenced_pools = set()
        for value, pool_id in self.constant_pool.items():
            # This is a simple implementation - in practice, we'd track usage during compilation
            # For now, we'll scan the current constant_pool for referenced values
            referenced_pools.add(pool_id)
        return referenced_pools
    
    def add_alias_chain(self, full_chain: str, alias: str):
        """Add an alias chain for repeated attribute access patterns"""
        if self.alias_chains:
            self.alias_chains_dict[full_chain] = alias
    
    def _maybe_alias(self, full_chain: str) -> Optional[str]:
        """Check if a full chain has an alias and return it"""
        alias = self.alias_chains_dict.get(full_chain)
        return alias
    
    def _process_call(self, node: ast.Call) -> str:
        """Process function call with ultra-compact syntax"""
        if isinstance(node.func, ast.Attribute):
            # reconstruct chain like above
            chain = []
            cur = node.func
            while isinstance(cur, ast.Attribute):
                chain.append(cur.attr)
                cur = cur.value
            base = self._process_value(cur)
            chain.append(base)
            chain.reverse()
            full = ".".join(chain)            # s.config.get
            ali = self._maybe_alias(full)
            func_str = ali if ali else full
            
            # Extract method for special compact patterns
            method = node.func.attr
            obj = self._process_value(node.func.value)
            
            # Special compact patterns
            if self.dense_mode:
                # List operations
                if method == 'append' and len(node.args) == 1:
                    arg = self._process_value(node.args[0])
                    return f"A {obj},{arg}"  # Compact append
                elif method == 'pop':
                    if node.args:
                        arg = self._process_value(node.args[0])
                        return f"P {obj},{arg}"
                    return f"P {obj}"
                elif method == 'get' and obj.endswith('.config'):
                    # Compress config.get calls
                    args = [self._process_value(a) for a in node.args]
                    return f"C({obj}.g,{','.join(args)})"
                
            # Regular method call - use aliased function string
            args = [self._process_value(a) for a in node.args]
            if self.dense_mode:
                return f"C({func_str},{','.join(args)})" if args else f"C({func_str})"
            else:
                return f"CALL({func_str}, {', '.join(args)})" if args else f"CALL({func_str})"
        
        elif isinstance(node.func, ast.Name):
            func_name = self.name_map.get(node.func.id, node.func.id)
            
            # Special built-in functions
            if self.dense_mode:
                builtin_shortcuts = {
                    'isinstance': 'is',
                    'len': 'ln',
                    'str': 'st',
                    'int': 'i',
                    'float': 'f',
                    'list': 'ls',
                    'dict': 'dc',
                    'print': '@',
                }
                if node.func.id in builtin_shortcuts:
                    func_name = builtin_shortcuts[node.func.id]
            
            if func_name == '@' and self.dense_mode:
                # Ultra-compact print, no space after @ in dense mode
                args = [self._process_value(a) for a in node.args]
                if self.no_spaces:
                    return f"@{','.join(args)}"  # No space after @
                else:
                    return f"@ {','.join(args)}"
            else:
                args = [self._process_value(a) for a in node.args]
                if self.dense_mode:
                    return f"C({func_name},{','.join(args)})" if args else f"C({func_name})"
                else:
                    return f"CALL({func_name}, {', '.join(args)})" if args else f"CALL({func_name})"
        
        return "C(?)" if self.dense_mode else "CALL(?)"
    
    def _process_condition(self, node: ast.AST) -> str:
        """Process condition with ultra-compact operators"""
        if isinstance(node, ast.Compare):
            left = self._process_value(node.left)
            comparisons = []
            
            for op, right in zip(node.ops, node.comparators):
                right_val = self._process_value(right)
                
                if self.dense_mode:
                    # Ultra-compact operators based on ascii_ops flag
                    if isinstance(op, ast.Is) and isinstance(right, ast.Constant) and right.value is None:
                        comparisons.append(f"N({left})")  # Compact is None
                    elif isinstance(op, ast.IsNot) and isinstance(right, ast.Constant) and right.value is None:
                        comparisons.append(f"!N({left})")  # Compact is not None
                    elif isinstance(op, ast.In):
                        if self.no_spaces:
                            comparisons.append(f"{left}in{right_val}")  # ASCII, no spaces
                        else:
                            comparisons.append(f"{left} in {right_val}")
                    elif isinstance(op, ast.NotIn):
                        if self.no_spaces:
                            comparisons.append(f"{left}!in{right_val}")  # ASCII, no spaces
                        else:
                            comparisons.append(f"{left} !in {right_val}")
                    elif isinstance(op, ast.Eq):
                        if self.no_spaces:
                            comparisons.append(f"{left}=={right_val}")  # Keep == to avoid ambiguity
                        else:
                            comparisons.append(f"{left} == {right_val}")
                    elif isinstance(op, ast.NotEq):
                        if self.no_spaces:
                            comparisons.append(f"{left}!={right_val}")  # ASCII !=
                        else:
                            comparisons.append(f"{left} != {right_val}")
                    elif isinstance(op, ast.Lt):
                        if self.no_spaces:
                            comparisons.append(f"{left}<{right_val}")
                        else:
                            comparisons.append(f"{left} < {right_val}")
                    elif isinstance(op, ast.LtE):
                        if self.no_spaces:
                            comparisons.append(f"{left}<={right_val}")  # ASCII <=
                        else:
                            comparisons.append(f"{left} <= {right_val}")
                    elif isinstance(op, ast.Gt):
                        if self.no_spaces:
                            comparisons.append(f"{left}>{right_val}")
                        else:
                            comparisons.append(f"{left} > {right_val}")
                    elif isinstance(op, ast.GtE):
                        if self.no_spaces:
                            comparisons.append(f"{left}>={right_val}")  # ASCII >=
                        else:
                            comparisons.append(f"{left} >= {right_val}")
                    else:
                        comparisons.append(f"{left}?{right_val}")
                else:
                    # Standard operators
                    if isinstance(op, ast.Is) and isinstance(right, ast.Constant) and right.value is None:
                        comparisons.append(f"ISNONE({left})")
                    elif isinstance(op, ast.IsNot) and isinstance(right, ast.Constant) and right.value is None:
                        comparisons.append(f"ISNOTNONE({left})")
                    elif isinstance(op, ast.In):
                        comparisons.append(f"({left} in {right_val})")
                    elif isinstance(op, ast.NotIn):
                        comparisons.append(f"({left} not in {right_val})")
                    elif isinstance(op, ast.Eq):
                        comparisons.append(f"({left} == {right_val})")
                    elif isinstance(op, ast.NotEq):
                        comparisons.append(f"({left} != {right_val})")
                    elif isinstance(op, ast.Lt):
                        comparisons.append(f"({left} < {right_val})")
                    elif isinstance(op, ast.LtE):
                        comparisons.append(f"({left} <= {right_val})")
                    elif isinstance(op, ast.Gt):
                        comparisons.append(f"({left} > {right_val})")
                    elif isinstance(op, ast.GtE):
                        comparisons.append(f"({left} >= {right_val})")
            
            if self.dense_mode and len(comparisons) > 1:
                return '&'.join(comparisons)  # Implicit AND
            elif len(comparisons) > 1:
                return ' and '.join(comparisons)
            else:
                return comparisons[0] if comparisons else "?"
        
        elif isinstance(node, ast.BoolOp):
            if isinstance(node.op, ast.And):
                parts = [self._process_condition(v) for v in node.values]
                if self.dense_mode:
                    return f"({'&'.join(parts)})"
                return f"({' and '.join(parts)})"
            elif isinstance(node.op, ast.Or):
                parts = [self._process_condition(v) for v in node.values]
                if self.dense_mode:
                    return f"({'|'.join(parts)})"
                return f"({' or '.join(parts)})"
        
        elif isinstance(node, ast.UnaryOp):
            if isinstance(node.op, ast.Not):
                operand = self._process_condition(node.operand)
                return f"!{operand}" if self.dense_mode else f"NOT {operand}"
        
        return self._process_value(node)
    
    def _get_binop(self, op: ast.AST) -> str:
        """Get binary operator string"""
        ops = {
            ast.Add: '+',
            ast.Sub: '-',
            ast.Mult: '*',
            ast.Div: '/',
            ast.FloorDiv: '//',
            ast.Mod: '%',
            ast.Pow: '**',
            ast.LShift: '<<',
            ast.RShift: '>>',
            ast.BitOr: '|',
            ast.BitXor: '^',
            ast.BitAnd: '&',
        }
        return ops.get(type(op), '?')
    
    def _get_aug_op(self, op: ast.AST) -> str:
        """Get augmented assignment operator"""
        ops = {
            ast.Add: '+=',
            ast.Sub: '-=',
            ast.Mult: '*=',
            ast.Div: '/=',
            ast.FloorDiv: '//=',
            ast.Mod: '%=',
            ast.Pow: '**=',
            ast.LShift: '<<=',
            ast.RShift: '>>=',
            ast.BitOr: '|=',
            ast.BitXor: '^=',
            ast.BitAnd: '&=',
        }
        return ops.get(type(op), '?=')
    
    def _get_name(self, node: ast.AST) -> str:
        """Get name from a node"""
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            return f"{self._get_name(node.value)}.{node.attr}"
        return "?"
    
    # ===== PARSER METHODS FOR READING DENSE FLOW BACK TO AST =====
    
    def _safe_parse_statement(self, stmt_str: str) -> ast.AST:
        """Safely parse a statement with fallback to Pass if parsing fails."""
        try:
            # Clean the statement string
            stmt_str = stmt_str.strip()
            if not stmt_str:
                return self._fix_ast_node_attributes(ast.Pass())
            
            # Quick validation: check for obviously invalid characters
            if any(char in stmt_str for char in ['#@$%', '{}{}', '][[']):
                logger.warning(f"Statement contains invalid characters: '{stmt_str}'")
                return self._fix_ast_node_attributes(ast.Pass())
            
            # Try normal parsing
            stmt, _ = self._parse_flow_statement([stmt_str], 0)
            if stmt is None:
                logger.warning(f"Parsing returned None for statement '{stmt_str}', using Pass")
                return self._fix_ast_node_attributes(ast.Pass())
            
            # Validate the parsed statement by trying to compile it
            try:
                import ast as ast_module
                # Fix AST attributes before validation
                stmt = self._fix_ast_node_attributes(stmt)
                # Create a module to test compilation
                module = ast_module.Module(body=[stmt], type_ignores=[])
                compile(module, '<string>', 'exec')
                return stmt
            except Exception as validation_error:
                logger.warning(f"Statement validation failed for '{stmt_str}': {validation_error}")
                return self._fix_ast_node_attributes(ast.Pass())
                
        except Exception as e:
            logger.warning(f"Failed to parse statement '{stmt_str}': {e}")
            # Return a Pass statement as fallback
            return self._fix_ast_node_attributes(ast.Pass())
    
    def _parse_flow_lines(self, lines: List[str], indent_level: int = 0) -> Tuple[List[ast.AST], int]:
        """
        Parse FLOW lines back to Python AST statements.
        
        Args:
            lines: List of FLOW lines to parse
            indent_level: Current indentation level
            
        Returns:
            Tuple of (parsed_statements, lines_consumed)
        """
        statements = []
        i = 0
        
        while i < len(lines):
            line = lines[i].rstrip()
            
            # Skip empty lines
            if not line.strip():
                i += 1
                continue
            
            # Check indentation level
            current_indent = len(line) - len(line.lstrip())
            if current_indent < indent_level:
                # Dedent - return to previous level
                break
            elif current_indent > indent_level:
                # This shouldn't happen at the start of parsing
                i += 1
                continue
            
            # Parse the line
            stmt, consumed = self._parse_flow_statement(lines[i:], indent_level)
            if stmt:
                statements.append(stmt)
            
            i += consumed
        
        return statements, i
    
    def _parse_flow_statement(self, lines: List[str], indent_level: int) -> Tuple[Optional[ast.AST], int]:
        """
        Parse a single FLOW statement with RAW block support and enhanced error handling.
        
        Returns:
            Tuple of (parsed_statement, lines_consumed)
        """
        if not lines:
            return None, 0
    
        line = lines[0].strip()
        
        # Check for RAW block first
        if line.startswith('RAW{') and '}' in line:
            return self._parse_raw_block(line), 1
        
        # Apply operator normalization first
        line = self._fix_operator_spacing(line)
        
        try:
            # Check for conditional expression FIRST before other patterns
            if self._is_conditional_expression(line):
                return self._parse_conditional_expression(line), 1
        
            # Handle inline blocks first
            if '{' in line and '}' in line:
                return self._parse_inline_statement(line), 1
            
            # Check for function definition first
            if line.startswith('def '):
                return self._parse_function_definition(lines, indent_level)
            
            # Parse based on macro
            if line.startswith('L') or (line and line[0] in 'LCFIEOTXYRBKA_WZD@+S-'):
                macro = line[0]
                
                if macro == 'L':
                    return self._parse_assignment(line), 1
                elif macro == 'F':
                    return self._parse_for_loop(lines, indent_level)
                elif macro == 'I':
                    return self._parse_if_statement(lines, indent_level)
                elif macro == 'E':
                    # This should be handled by the if parser
                    return None, 0
                elif macro == 'O':
                    # This should be handled by the if parser
                    return None, 0
                elif macro == 'T':
                    return self._parse_try_statement(lines, indent_level)
                elif macro == 'X':
                    # This should be handled by the try parser
                    return None, 0
                elif macro == 'R':
                    return self._parse_return(line), 1
                elif macro == 'B':
                    return self._fix_ast_node_attributes(ast.Break()), 1
                elif macro == 'K':
                    return self._fix_ast_node_attributes(ast.Continue()), 1
                elif macro == '_':
                    return self._fix_ast_node_attributes(ast.Pass()), 1
                elif macro == 'W':
                    return self._parse_while_loop(lines, indent_level)
                elif macro == 'Z':
                    return self._parse_with_statement(lines, indent_level)
                elif macro == 'D':
                    return self._parse_delete(line), 1
                elif macro == '@':
                    return self._parse_print(line), 1
                elif macro in '+':
                    return self._parse_increment(line), 1
                elif macro in '-':
                    return self._parse_decrement(line), 1
                elif macro == 'S':
                    return self._parse_setattr(line), 1
                elif macro == 'C':
                    return self._parse_call(line), 1
                elif macro == 'A':
                    return self._parse_append(line), 1
            
            # Add handling for compressed for loop: @f,r{...}
            elif line.startswith('@') and ',' in line and '{' in line:
                # Handle compressed for loop: @variable,iterable{body}
                # Extract parts: @variable,iterable{body}
                try:
                    at_idx = line.index('@')
                    comma_idx = line.index(',')
                    brace_idx = line.index('{')
                    
                    target_str = line[at_idx+1:comma_idx]
                    iter_str = line[comma_idx+1:brace_idx]
                    body_str = line[brace_idx+1:line.rindex('}')]
                    
                    # Parse target and iterator
                    target = ast.Name(id=self._expand_compressed_name(target_str), ctx=ast.Store())
                    iter_expr = self._parse_expression_string(iter_str)
                    
                    # Parse body statements
                    body_stmts = []
                    for stmt_str in body_str.split(';'):
                        if stmt_str.strip():
                            stmt, _ = self._parse_flow_statement_safe([stmt_str.strip()], 0)
                            if stmt:
                                body_stmts.append(stmt)
                    
                    for_node = ast.For(target=target, iter=iter_expr, body=body_stmts or [ast.Pass()], orelse=[])
                    return self._fix_ast_node_attributes(for_node), 1
                except Exception as e:
                    logger.warning(f"Failed to parse compressed for loop '{line}': {e}")
                    return self._fix_ast_node_attributes(ast.Pass()), 1
            
            # Check for assignment without L prefix (e.g., "r=g1(...)")
            if '=' in line and not any(op in line for op in ['==', '!=', '<=', '>=']):
                # This is likely an assignment without L prefix
                return self._parse_assignment(line), 1
            
            # If we can't parse it, treat as expression
            return self._parse_expression(line), 1
            
        except Exception as parse_error:
            self.logger.warning(f"Failed to parse statement: {parse_error}")
            return self._safe_parse_statement(line), 1

    def _is_conditional_expression(self, line: str) -> bool:
        """Check if line contains a conditional expression pattern."""
        # Pattern: (condition?{true}:{false}) or variants
        return '?' in line and '{' in line and '}' in line and ':' in line

    def _parse_conditional_expression(self, expr: str) -> ast.AST:
        """Parse CAI3 conditional expression (condition?{true}:{false}) to Python if-else."""
        # Extract the conditional expression pattern
        # Handle nested braces properly
        pattern = r'\(([^?]+)\?\{([^}]+)\}:\{([^}]+)\}\)'
        match = re.search(pattern, expr)
        
        if not match:
            # Try simpler pattern without outer parens
            pattern = r'([^?]+)\?\{([^}]+)\}:\{([^}]+)\}'
            match = re.search(pattern, expr)
        
        if match:
            condition_str = match.group(1).strip()
            true_body = match.group(2).strip()
            false_body = match.group(3).strip()
            
            # Parse the condition
            condition = self._parse_condition_string(condition_str)
            
            # Parse the true and false branches
            true_stmts = self._parse_conditional_body(true_body)
            false_stmts = self._parse_conditional_body(false_body)
            
            # Create If node
            return ast.If(
                test=condition,
                body=true_stmts,
                orelse=false_stmts
            )
        
        # Fallback for malformed conditional
        return ast.Pass()

    def _parse_conditional_body(self, body_str: str) -> List[ast.AST]:
        """Parse body of conditional expression which may have multiple statements."""
        statements = []
        
        # Split by semicolons for multiple statements
        parts = body_str.split(';')
        
        for part in parts:
            part = part.strip()
            if not part:
                continue
                
            # Handle special cases
            if part == 'return':
                statements.append(ast.Return(value=None))
            elif part.startswith('return '):
                # Parse return value
                value_str = part[7:].strip()
                try:
                    value_ast = ast.parse(value_str, mode='eval').body
                    statements.append(ast.Return(value=value_ast))
                except:
                    statements.append(ast.Return(value=ast.Constant(value=value_str)))
            elif part.startswith('print('):
                # Parse print statement
                try:
                    stmt_ast = ast.parse(part, mode='exec').body[0]
                    statements.append(stmt_ast)
                except:
                    # Fallback: create print with string
                    statements.append(
                        ast.Expr(value=ast.Call(
                            func=ast.Name(id='print', ctx=ast.Load()),
                            args=[ast.Constant(value=part)],
                            keywords=[]
                        ))
                    )
            else:
                # Try to parse as Python statement
                try:
                    parsed = ast.parse(part, mode='exec').body
                    statements.extend(parsed)
                except:
                    # Fallback: expression statement
                    statements.append(ast.Expr(value=ast.Constant(value=f"# {part}")))
        
        return statements if statements else [ast.Pass()]

    def _parse_inline_statement(self, line: str) -> ast.AST:
        """Parse an inline statement with braces"""
        # Extract the main part and the inline body
        if '{' in line and '}' in line:
            main_part = line[:line.index('{')]
            inline_body = line[line.index('{') + 1:line.rindex('}')]
            
            # Parse the main statement
            if main_part.startswith('I('):
                # Inline if: I(cond):{body}
                condition_str = main_part[2:-2]  # Remove I( and ):
                
                # FUNDAMENTAL FIX: Preprocess conditional to prevent malformed expressions
                condition_str = self._preprocess_conditional_expression(condition_str)
                
                condition = self._parse_condition_string(condition_str)
                
                # Parse inline body (semicolon separated)
                body_stmts = []
                for stmt_str in inline_body.split(';'):
                    stmt_str = stmt_str.strip()
                    if stmt_str:
                        # FUNDAMENTAL FIX: Preprocess body statements to prevent malformed expressions
                        stmt_str = self._preprocess_body_statement(stmt_str)
                        
                        # Parse individual statement
                        if '=' in stmt_str and not any(op in stmt_str for op in ['==', '!=', '<=', '>=']):
                            # Assignment (with or without L prefix)
                            stmt = self._parse_assignment(stmt_str)
                        elif stmt_str == 'RF':
                            # Return False
                            stmt = ast.Return(value=ast.Constant(value=False))
                        elif stmt_str == 'RT':
                            # Return True  
                            stmt = ast.Return(value=ast.Constant(value=True))
                        elif stmt_str == 'RN':
                            # Return None
                            stmt = ast.Return(value=None)
                        elif stmt_str.startswith('R') and len(stmt_str) > 1:
                            # Return with value
                            value_str = stmt_str[1:]
                            value = self._parse_expression_string(value_str)
                            stmt = ast.Return(value=value)
                        elif stmt_str == '_':
                            stmt = ast.Pass()
                        elif stmt_str == 'B':
                            stmt = ast.Break()
                        elif stmt_str == 'K':
                            stmt = ast.Continue()
                        elif stmt_str.startswith('@'):
                            stmt = self._parse_print(stmt_str)
                        elif stmt_str.endswith('+=1') or stmt_str.endswith('+= 1'):
                            # Increment operation: x+=1
                            target_str = stmt_str.split('+=')[0].strip()
                            target_name = self._expand_compressed_name(target_str)
                            if target_name in self.reverse_map:
                                target_name = self.reverse_map[target_name]
                            target = ast.Name(id=target_name, ctx=ast.Store())
                            value = ast.BinOp(
                                left=ast.Name(id=target_name, ctx=ast.Load()),
                                op=ast.Add(),
                                right=ast.Constant(value=1)
                            )
                            stmt = ast.Assign(targets=[target], value=value)
                            # Add required AST attributes
                            stmt.lineno = 1
                            stmt.col_offset = 0
                        else:
                            # Try parsing as expression statement
                            try:
                                expr_ast = self._parse_expression_string(stmt_str)
                                stmt = ast.Expr(value=expr_ast)
                            except:
                                stmt = ast.Pass()
                        
                        if stmt:
                            body_stmts.append(stmt)
                
                return ast.If(test=condition, body=body_stmts, orelse=[])
            
            elif main_part.startswith('F') and 'in' in main_part:
                # Inline for: Fxiniter:{body}
                for_parts = main_part[1:].split('in', 1)
                target_str = for_parts[0].strip()
                iter_str = for_parts[1].rstrip(':').strip()
                
                target = ast.Name(id=target_str, ctx=ast.Store())
                iter_expr = self._parse_expression_string(iter_str)
                
                # Parse inline body
                body_stmts = []
                for stmt_str in inline_body.split(';'):
                    stmt_str = stmt_str.strip()
                    if stmt_str:
                        # Parse individual statement
                        if stmt_str.startswith('L') and '=' in stmt_str:
                            stmt = self._parse_assignment(stmt_str)
                        elif stmt_str == 'RF':
                            # Return False
                            stmt = ast.Return(value=ast.Constant(value=False))
                        elif stmt_str == 'RT':
                            # Return True  
                            stmt = ast.Return(value=ast.Constant(value=True))
                        elif stmt_str == 'RN':
                            # Return None
                            stmt = ast.Return(value=None)
                        elif stmt_str.startswith('R') and len(stmt_str) > 1:
                            # Return with value
                            value_str = stmt_str[1:]
                            value = self._parse_expression_string(value_str)
                            stmt = ast.Return(value=value)
                        elif stmt_str == '_':
                            stmt = ast.Pass()
                        elif stmt_str == 'B':
                            stmt = ast.Break()
                        elif stmt_str == 'K':
                            stmt = ast.Continue()
                        elif stmt_str.startswith('@'):
                            stmt = self._parse_print(stmt_str)
                        elif stmt_str.startswith('A '):
                            # Parse append operation: A list,item
                            parts = stmt_str[2:].split(',', 1)
                            if len(parts) == 2:
                                list_name = parts[0].strip()
                                item_expr = self._parse_expression_string(parts[1].strip())
                                list_obj = ast.Name(id=list_name, ctx=ast.Load())
                                append_call = ast.Call(
                                    func=ast.Attribute(value=list_obj, attr='append', ctx=ast.Load()),
                                    args=[item_expr],
                                    keywords=[]
                                )
                                stmt = ast.Expr(value=append_call)
                            else:
                                stmt = ast.Pass()
                        else:
                            # Try parsing as expression
                            stmt, _ = self._parse_flow_statement([stmt_str], 0)
                            if not stmt:
                                stmt = ast.Pass()
                        
                        if stmt:
                            body_stmts.append(stmt)
                
                return ast.For(target=target, iter=iter_expr, body=body_stmts, orelse=[])
            
            elif main_part.startswith('T'):
                # Check for ultra-dense try-except format T{body}X{handler}
                if '}X{' in line:
                    # Use the new ultra-dense parser
                    return self._parse_ultra_dense_try_except(line)
                
                # Inline try: T:{body} (old format)
                # Parse inline body
                body_stmts = []
                for stmt_str in inline_body.split(';'):
                    stmt_str = stmt_str.strip()
                    if stmt_str:
                        # Parse individual statement
                        if stmt_str.startswith('L') and '=' in stmt_str:
                            stmt = self._parse_assignment(stmt_str)
                        elif stmt_str == 'RF':
                            # Return False
                            stmt = ast.Return(value=ast.Constant(value=False))
                        elif stmt_str == 'RT':
                            # Return True  
                            stmt = ast.Return(value=ast.Constant(value=True))
                        elif stmt_str == 'RN':
                            # Return None
                            stmt = ast.Return(value=None)
                        elif stmt_str.startswith('R') and len(stmt_str) > 1:
                            # Return with value
                            value_str = stmt_str[1:]
                            value = self._parse_expression_string(value_str)
                            stmt = ast.Return(value=value)
                        elif stmt_str == '_':
                            stmt = ast.Pass()
                        elif stmt_str == 'B':
                            stmt = ast.Break()
                        elif stmt_str == 'K':
                            stmt = ast.Continue()
                        elif stmt_str.startswith('@'):
                            stmt = self._parse_print(stmt_str)
                        elif stmt_str.startswith('A '):
                            # Parse append operation: A list,item
                            parts = stmt_str[2:].split(',', 1)
                            if len(parts) == 2:
                                list_name = parts[0].strip()
                                item_expr = self._parse_expression_string(parts[1].strip())
                                list_obj = ast.Name(id=list_name, ctx=ast.Load())
                                append_call = ast.Call(
                                    func=ast.Attribute(value=list_obj, attr='append', ctx=ast.Load()),
                                    args=[item_expr],
                                    keywords=[]
                                )
                                stmt = ast.Expr(value=append_call)
                            else:
                                stmt = ast.Pass()
                        else:
                            # Try parsing as expression
                            stmt, _ = self._parse_flow_statement([stmt_str], 0)
                            if not stmt:
                                stmt = ast.Pass()
                        
                        if stmt:
                            body_stmts.append(stmt)
                
                return ast.Try(body=body_stmts, handlers=[], orelse=[], finalbody=[])
        
        # Fallback
        return ast.Pass()
    
    def _parse_raw_block(self, line: str) -> ast.AST:
        """Recover AST from RAW block."""
        # Extract raw_id
        try:
            start = line.index('RAW{') + 4
            end = line.index('}', start)
            raw_id = line[start:end]
        except (ValueError, IndexError):
            logger.warning(f"Malformed RAW block: {line}")
            return self._fix_ast_node_attributes(ast.Expr(value=ast.Constant(value=f"# Malformed RAW block: {line}")))
        
        if raw_id not in self.raw_blocks:
            # Fallback: create a pass statement with comment
            logger.warning(f"RAW block {raw_id} not found in raw_blocks")
            return self._fix_ast_node_attributes(ast.Expr(value=ast.Constant(value=f"# RAW block {raw_id} not found")))
        
        block_info = self.raw_blocks[raw_id]
        
        try:
            if block_info['type'] == 'source':
                # Decompress and parse source
                source = zlib.decompress(base64.b64decode(block_info['data'])).decode()
                parsed = ast.parse(source)
                if parsed.body:
                    return self._fix_ast_node_attributes(parsed.body[0])
                else:
                    return self._fix_ast_node_attributes(ast.Pass())
            else:
                # Reconstruct from AST JSON
                ast_json = json.loads(zlib.decompress(base64.b64decode(block_info['data'])).decode())
                return self._fix_ast_node_attributes(self._json_to_ast(ast_json))
        except Exception as e:
            logger.warning(f"RAW recovery failed for {raw_id}: {e}")
            # Safety fallback
            return self._fix_ast_node_attributes(ast.Expr(value=ast.Constant(value=f"# RAW recovery failed: {e}")))
    
    def _parse_assignment(self, line: str) -> ast.AST:
        """Parse assignment: Lx=value or x=value with enhanced error handling"""
        try:
            # Remove L prefix if present
            if line.startswith('L'):
                assign_str = line[1:]
            else:
                assign_str = line
            
            if '=' in assign_str:
                target_str, value_str = assign_str.split('=', 1)
                target_name = target_str.strip()
                
                # Validate target name
                if not target_name or not target_name.replace('_', '').replace('.', '').replace('[', '').replace(']', '').isalnum():
                    logger.warning(f"Invalid target name in assignment: '{target_name}'")
                    return self._fix_ast_node_attributes(ast.Pass())
                
                # Apply name mapping for target
                if target_name in self.reverse_map:
                    target_name = self.reverse_map[target_name]
                elif target_name in self.name_map:
                    target_name = self.name_map[target_name]
                
                # Handle different target types (name, attribute, subscript)
                if '.' in target_name:
                    # Attribute assignment
                    target = self._parse_attribute_access(target_name)
                    target.ctx = ast.Store()
                elif '[' in target_name and ']' in target_name:
                    # Subscript assignment
                    obj_name = target_name[:target_name.index('[')]
                    index_str = target_name[target_name.index('[')+1:target_name.rindex(']')]
                    obj = ast.Name(id=obj_name, ctx=ast.Load())
                    index = self._parse_expression_string(index_str)
                    target = ast.Subscript(value=obj, slice=index, ctx=ast.Store())
                else:
                    # Simple name assignment
                    target = ast.Name(id=target_name, ctx=ast.Store())
                
                # Parse value with error handling
                try:
                    value = self._parse_expression_string(value_str.strip())
                except Exception as value_error:
                    logger.warning(f"Failed to parse assignment value '{value_str}': {value_error}")
                    # Use None as fallback value
                    value = ast.Constant(value=None)
                
                assign_node = ast.Assign(targets=[target], value=value)
                # Add required AST attributes
                return self._fix_ast_node_attributes(assign_node)
            
            # If no = found, return Pass
            logger.warning(f"No assignment operator found in: '{line}'")
            return self._fix_ast_node_attributes(ast.Pass())
            
        except Exception as e:
            logger.warning(f"Failed to parse assignment '{line}': {e}")
            return self._fix_ast_node_attributes(ast.Pass())
    
    def _parse_for_loop(self, lines: List[str], indent_level: int) -> Tuple[ast.AST, int]:
        """Parse for loop: Fxiniter: or Fxiniter:{inline}"""
        line = lines[0].strip()
        
        # Extract for components
        if line.startswith('F') and 'in' in line:
            for_parts = line[1:].split('in', 1)
            target_str = for_parts[0].strip()
            rest = for_parts[1].strip()
            
            if rest.endswith(':'):
                iter_str = rest[:-1]
            else:
                iter_str = rest
            
            target = ast.Name(id=target_str, ctx=ast.Store())
            iter_expr = self._parse_expression_string(iter_str)
            
            # Parse body
            if '{' in line:
                # Inline body
                return self._parse_inline_statement(line), 1
            else:
                # Multiline body
                body_stmts, consumed = self._parse_flow_lines(lines[1:], indent_level + 1)
                for_node = ast.For(target=target, iter=iter_expr, body=body_stmts or [ast.Pass()], orelse=[])
                return self._fix_ast_node_attributes(for_node), consumed + 1
        
        return ast.Pass(), 1
    
    def _parse_elif_statement(self, lines: List[str], indent_level: int) -> Tuple[ast.AST, int]:
        """Parse elif statement: E(cond): or E(cond):{inline}"""
        line = lines[0].strip()
        
        # Extract condition
        if line.startswith('E(') and '):' in line:
            condition_str = line[2:line.index('):')]
            condition = self._parse_condition_string(condition_str)
            
            # Check for inline body
            if '{' in line:
                return self._parse_inline_statement(line), 1
            
            # Parse multiline body
            body_stmts, consumed = self._parse_flow_lines(lines[1:], indent_level + 1)
            consumed += 1
            
            # Check for elif/else
            orelse_stmts = []
            current_line_idx = consumed
            
            while current_line_idx < len(lines):
                next_line = lines[current_line_idx].strip()
                if next_line.startswith('E('):
                    # elif
                    elif_stmt, elif_consumed = self._parse_elif_statement(lines[current_line_idx:], indent_level)
                    orelse_stmts = [elif_stmt]
                    consumed += elif_consumed
                    break
                elif next_line.startswith('O:'):
                    # else
                    else_body, else_consumed = self._parse_flow_lines(lines[current_line_idx + 1:], indent_level + 1)
                    orelse_stmts = else_body
                    consumed += else_consumed + 1
                    break
                else:
                    break
            
            return ast.If(test=condition, body=body_stmts or [ast.Pass()], orelse=orelse_stmts), consumed
        
        return ast.Pass(), 1

    def _parse_if_statement(self, lines: List[str], indent_level: int) -> Tuple[ast.AST, int]:
        """Parse if statement: I(cond): or I(cond):{inline}"""
        line = lines[0].strip()
        
        # Extract condition
        if line.startswith('I(') and '):' in line:
            condition_str = line[2:line.index('):')]
            condition = self._parse_condition_string(condition_str)
            
            # Check for inline body
            if '{' in line:
                return self._parse_inline_statement(line), 1
            
            # Parse multiline body
            body_stmts, consumed = self._parse_flow_lines(lines[1:], indent_level + 1)
            consumed += 1
            
            # Check for elif/else
            orelse_stmts = []
            current_line_idx = consumed
            
            while current_line_idx < len(lines):
                next_line = lines[current_line_idx].strip()
                if next_line.startswith('E('):
                    # elif
                    elif_stmt, elif_consumed = self._parse_elif_statement(lines[current_line_idx:], indent_level)
                    orelse_stmts = [elif_stmt]
                    consumed += elif_consumed
                    break
                elif next_line.startswith('O:'):
                    # else
                    else_body, else_consumed = self._parse_flow_lines(lines[current_line_idx + 1:], indent_level + 1)
                    orelse_stmts = else_body
                    consumed += else_consumed + 1
                    break
                else:
                    break
            
            return ast.If(test=condition, body=body_stmts or [ast.Pass()], orelse=orelse_stmts), consumed
        
        return ast.Pass(), 1
    
    def _parse_try_statement(self, lines: List[str], indent_level: int) -> Tuple[ast.AST, int]:
        """Parse try statement: T: or T:{inline} or T{body}X{handler}"""
        line = lines[0].strip()
        
        # Check for ultra-dense try-except format T{body}X{handler}
        if line.startswith('T{') and '}X{' in line:
            result = self._parse_ultra_dense_try_except(line)
            if result:
                return result, 1
        
        # Check for inline body
        if '{' in line:
            return self._parse_inline_statement(line), 1
        
        # Parse multiline body
        body_stmts, consumed = self._parse_flow_lines(lines[1:], indent_level + 1)
        consumed += 1
        
        # Parse except handlers
        handlers = []
        current_line_idx = consumed
        
        while current_line_idx < len(lines):
            next_line = lines[current_line_idx].strip()
            if next_line.startswith('X('):
                # except handler
                handler, handler_consumed = self._parse_except_handler(lines[current_line_idx:], indent_level)
                if handler:
                    handlers.append(handler)
                consumed += handler_consumed
                current_line_idx += handler_consumed
            else:
                break
        
        return ast.Try(body=body_stmts or [ast.Pass()], handlers=handlers, orelse=[], finalbody=[]), consumed
    
    def _parse_except_handler(self, lines: List[str], indent_level: int) -> Tuple[Optional[ast.ExceptHandler], int]:
        """Parse except handler: X(Exception)name:"""
        line = lines[0].strip()
        
        if line.startswith('X(') and '):' in line:
            # Extract exception type and name
            handler_str = line[2:line.index('):')]
            rest = line[line.index('):') + 2:]
            
            # Parse exception type
            exc_type = ast.Name(id=handler_str, ctx=ast.Load()) if handler_str != 'E' else None
            
            # Parse exception name - fix for empty names
            name_part = rest.rstrip(':').strip()
            exc_name = name_part if name_part and name_part != '_' and name_part else None
            
            # Parse handler body
            if '{' in line:
                # Inline handler
                inline_part = line[line.index('{') + 1:line.rindex('}')]
                body_stmts = []
                for stmt_str in inline_part.split(';'):
                    if stmt_str.strip():
                        stmt, _ = self._parse_flow_statement([stmt_str.strip()], 0)
                        if stmt:
                            body_stmts.append(stmt)
                return ast.ExceptHandler(type=exc_type, name=exc_name, body=body_stmts), 1
            else:
                # Multiline handler
                body_stmts, consumed = self._parse_flow_lines(lines[1:], indent_level + 1)
                return ast.ExceptHandler(type=exc_type, name=exc_name, body=body_stmts or [ast.Pass()]), consumed + 1
        
        return None, 1
    
    def _parse_while_loop(self, lines: List[str], indent_level: int) -> Tuple[ast.AST, int]:
        """Parse while loop: W(cond):"""
        line = lines[0].strip()
        
        if line.startswith('W(') and '):' in line:
            condition_str = line[2:line.index('):')]
            condition = self._parse_condition_string(condition_str)
            
            # Parse body
            body_stmts, consumed = self._parse_flow_lines(lines[1:], indent_level + 1)
            return ast.While(test=condition, body=body_stmts or [ast.Pass()], orelse=[]), consumed + 1
        
        return ast.Pass(), 1
    
    def _parse_with_statement(self, lines: List[str], indent_level: int) -> Tuple[ast.AST, int]:
        """Parse with statement: Z expr:"""
        line = lines[0].strip()
        
        if line.startswith('Z '):
            context_str = line[2:].rstrip(':')
            context_expr = self._parse_expression_string(context_str)
            
            # Parse body
            body_stmts, consumed = self._parse_flow_lines(lines[1:], indent_level + 1)
            withitem = ast.withitem(context_expr=context_expr, optional_vars=None)
            return ast.With(items=[withitem], body=body_stmts or [ast.Pass()]), consumed + 1
        
        return ast.Pass(), 1
    
    def _parse_function_definition(self, lines: List[str], indent_level: int) -> Tuple[ast.AST, int]:
        """Parse function definition: def name(args):"""
        line = lines[0].strip()
        
        # Parse function signature: def name(args):
        if not line.startswith('def ') or not line.endswith(':'):
            # Malformed function definition
            return ast.Pass(), 1
        
        # Extract function name and arguments
        func_signature = line[4:-1]  # Remove 'def ' and ':'
        
        if '(' in func_signature and ')' in func_signature:
            func_name = func_signature[:func_signature.index('(')]
            args_str = func_signature[func_signature.index('(') + 1:func_signature.rindex(')')]
            
            # Parse arguments
            args = []
            defaults = []
            
            if args_str.strip():
                for arg_str in args_str.split(','):
                    arg_str = arg_str.strip()
                    if '=' in arg_str:
                        # Default argument
                        arg_name, default_val = arg_str.split('=', 1)
                        arg_name = arg_name.strip()
                        default_val = default_val.strip()
                        args.append(ast.arg(arg=arg_name, annotation=None))
                        defaults.append(self._parse_expression_string(default_val))
                    else:
                        # Regular argument
                        args.append(ast.arg(arg=arg_str, annotation=None))
            
            # Parse function body
            body_stmts, consumed = self._parse_flow_lines(lines[1:], indent_level + 1)
            
            # Create function definition
            func_def = ast.FunctionDef(
                name=func_name,
                args=ast.arguments(
                    posonlyargs=[],
                    args=args,
                    vararg=None,
                    kwonlyargs=[],
                    kw_defaults=[],
                    kwarg=None,
                    defaults=defaults
                ),
                body=body_stmts or [ast.Pass()],
                decorator_list=[],
                returns=None
            )
            
            return self._fix_ast_node_attributes(func_def), consumed + 1
        
        # Fallback for malformed function
        return ast.Pass(), 1
    
    def _parse_return(self, line: str) -> ast.AST:
        """Parse return statement: Rvalue or R"""
        if len(line) > 1:
            value_str = line[1:]
            value = self._parse_expression_string(value_str)
            return self._fix_ast_node_attributes(ast.Return(value=value))
        else:
            return self._fix_ast_node_attributes(ast.Return(value=None))
    
    def _parse_delete(self, line: str) -> ast.AST:
        """Parse delete statement: Dtargets"""
        if len(line) > 1:
            targets_str = line[1:]
            targets = []
            for target_str in targets_str.split(','):
                target = ast.Name(id=target_str.strip(), ctx=ast.Del())
                targets.append(target)
            return ast.Delete(targets=targets)
        return ast.Pass()
    
    def _parse_print(self, line: str) -> ast.AST:
        """Parse print statement: @args"""
        if len(line) > 1:
            args_str = line[1:]
            args = []
            for arg_str in args_str.split(','):
                if arg_str.strip():
                    arg = self._parse_expression_string(arg_str.strip())
                    args.append(arg)
            
            # Create print function call
            func = ast.Name(id='print', ctx=ast.Load())
            return ast.Expr(value=ast.Call(func=func, args=args, keywords=[]))
        return ast.Pass()
    
    def _parse_increment(self, line: str) -> ast.AST:
        """Parse increment: +target"""
        if len(line) > 1:
            target_str = line[1:]
            target = ast.Name(id=target_str, ctx=ast.Store())
            value = ast.BinOp(left=ast.Name(id=target_str, ctx=ast.Load()), op=ast.Add(), right=ast.Constant(value=1))
            assign_node = ast.Assign(targets=[target], value=value)
            # Add required AST attributes
            assign_node.lineno = 1
            assign_node.col_offset = 0
            return assign_node
        return ast.Pass()
    
    def _parse_decrement(self, line: str) -> ast.AST:
        """Parse decrement: -target"""
        if len(line) > 1:
            target_str = line[1:]
            target = ast.Name(id=target_str, ctx=ast.Store())
            value = ast.BinOp(left=ast.Name(id=target_str, ctx=ast.Load()), op=ast.Sub(), right=ast.Constant(value=1))
            assign_node = ast.Assign(targets=[target], value=value)
            # Add required AST attributes
            assign_node.lineno = 1
            assign_node.col_offset = 0
            return assign_node
        return ast.Pass()
    
    def _parse_setattr(self, line: str) -> ast.AST:
        """Parse setattr: Starget=value"""
        if len(line) > 1 and '=' in line:
            assign_str = line[1:]
            target_str, value_str = assign_str.split('=', 1)
            
            # This could be augmented assignment
            if '+' in target_str or '-' in target_str or '*' in target_str:
                # Handle augmented assignment
                op_char = next((c for c in target_str if c in '+-*'), None)
                if op_char:
                    actual_target = target_str[:target_str.index(op_char)]
                    target = ast.Name(id=actual_target, ctx=ast.Store())
                    left = ast.Name(id=actual_target, ctx=ast.Load())
                    right = self._parse_expression_string(value_str.strip())
                    
                    op_map = {'+': ast.Add(), '-': ast.Sub(), '*': ast.Mult()}
                    op = op_map.get(op_char, ast.Add())
                    
                    value = ast.BinOp(left=left, op=op, right=right)
                    assign_node = ast.Assign(targets=[target], value=value)
                    # Add required AST attributes
                    assign_node.lineno = 1
                    assign_node.col_offset = 0
                    return assign_node
            
            # Regular assignment
            target = ast.Name(id=target_str.strip(), ctx=ast.Store())
            value = self._parse_expression_string(value_str.strip())
            assign_node = ast.Assign(targets=[target], value=value)
            # Add required AST attributes
            assign_node.lineno = 1
            assign_node.col_offset = 0
            return assign_node
        
        return ast.Pass()
    
    def _parse_call(self, line: str) -> ast.AST:
        """Parse function call: C(func,args)"""
        if line.startswith('C(') and line.endswith(')'):
            call_str = line[2:-1]
            if ',' in call_str:
                func_str, args_str = call_str.split(',', 1)
                func = self._parse_expression_string(func_str.strip())
                
                args = []
                for arg_str in args_str.split(','):
                    if arg_str.strip():
                        arg = self._parse_expression_string(arg_str.strip())
                        args.append(arg)
                
                return ast.Expr(value=ast.Call(func=func, args=args, keywords=[]))
            else:
                # No arguments
                func = self._parse_expression_string(call_str.strip())
                return ast.Expr(value=ast.Call(func=func, args=[], keywords=[]))
        
        return ast.Pass()

    def _parse_append(self, line: str) -> ast.AST:
        """Parse append statement: A target,value or Atarget,value"""
        if line.startswith('A') and len(line) > 1:
            # Handle both "A target,value" and "Atarget,value" formats
            if line[1] == ' ':
                # Format: A target,value
                rest = line[2:]  # Remove 'A '
            else:
                # Format: Atarget,value
                rest = line[1:]  # Remove 'A'
            
            if ',' in rest:
                target_str, value_str = rest.split(',', 1)
                target_str = target_str.strip()
                value_str = value_str.strip()
                
                # Parse target and value
                target = self._parse_expression_string(target_str)
                value = self._parse_expression_string(value_str)
                
                # Create target.append(value) call
                append_call = ast.Call(
                    func=ast.Attribute(value=target, attr='append', ctx=ast.Load()),
                    args=[value],
                    keywords=[]
                )
                
                return self._fix_ast_node_attributes(ast.Expr(value=append_call))
        
        return self._fix_ast_node_attributes(ast.Pass())

    def expand_compressed_operators(self, expr: str) -> str:
        """Expand compressed operators back to Python syntax."""
        result = expr
        
        # Handle operators in order of specificity (most specific first)
        # This prevents conflicts like != being affected by standalone !
        
        import re
        
        # FIRST: Handle FLOW syntax patterns like @i,ran(10){pri(i)}
        # Pattern: @variable,iterable{body} -> for variable in iterable: body
        for_loop_pattern = r'@([^,]+),([^{]+)\{([^}]*)\}'
        for_matches = list(re.finditer(for_loop_pattern, result))
        
        # Process matches in reverse to maintain string positions
        for match in reversed(for_matches):
            target = match.group(1).strip()
            iterable = match.group(2).strip()
            body = match.group(3).strip()
            
            # Convert FLOW for-loop to Python syntax
            start, end = match.span()
            if body:
                # Simple body - convert to Python for-loop syntax
                if ';' in body:
                    # Multiple statements in body
                    body_parts = [stmt.strip() for stmt in body.split(';') if stmt.strip()]
                    body_python = '; '.join(body_parts)
                else:
                    body_python = body
                
                python_for = f'for {target} in {iterable}: {body_python}'
            else:
                python_for = f'for {target} in {iterable}: pass'
            
            result = result[:start] + python_for + result[end:]

        # SECOND: Handle try-except patterns T{...}X{...}
        # Pattern: T{try_body}X{except_body} -> try: try_body except: except_body
        try_except_pattern = r'T\{([^}]*)\}X\{([^}]*)\}'
        try_matches = list(re.finditer(try_except_pattern, result))
        
        # Process matches in reverse to maintain string positions
        for match in reversed(try_matches):
            try_body = match.group(1).strip()
            except_body = match.group(2).strip()
            
            # Convert FLOW try-except to Python syntax
            start, end = match.span()
            
            # Handle try body
            if try_body:
                if ';' in try_body:
                    # Multiple statements in try body
                    try_parts = [stmt.strip() for stmt in try_body.split(';') if stmt.strip()]
                    try_python = '; '.join(try_parts)
                else:
                    try_python = try_body
            else:
                try_python = 'pass'
            
            # Handle except body
            if except_body:
                if except_body.startswith('@'):
                    # Exception variable pattern like @e
                    except_var = except_body[1:] if len(except_body) > 1 else 'e'
                    except_python = f'Exception as {except_var}: pass'
                elif ';' in except_body:
                    # Multiple statements in except body
                    except_parts = [stmt.strip() for stmt in except_body.split(';') if stmt.strip()]
                    except_python = '; '.join(except_parts)
                else:
                    except_python = except_body if except_body else 'pass'
            else:
                except_python = 'pass'
            
            # Build the Python try-except
            if except_body.startswith('@'):
                python_try = f'try: {try_python} except {except_python}'
            else:
                python_try = f'try: {try_python} except: {except_python}'
            
            result = result[:start] + python_try + result[end:]

        # Enhanced: Handle multiple !?var,container patterns with better boundary detection
        # Use a more precise pattern that handles complex containers better
        # Updated pattern to be more flexible and handle edge cases including spaces and word boundaries
        not_in_patterns = list(re.finditer(r'!\?([^,\s]+?),\s*([^\s&|)}\],]+)', result))

        # Process matches in reverse to maintain string positions
        for match in reversed(not_in_patterns):
            var_part = match.group(1).strip()
            container_part = match.group(2).strip()
            
            # Clean up container_part - remove trailing punctuation that shouldn't be part of the container
            container_part = re.sub(r'[,\s]*$', '', container_part)
            
            # Special handling for placeholder containers
            if container_part == '?':
                # Try to infer the container from context if possible
                # For now, keep the placeholder but mark it for later resolution
                container_part = '?'  # Will be resolved in next phase
            
            # Replace this specific match, preserving surrounding content
            start, end = match.span()
            result = result[:start] + f'{var_part} not in {container_part}' + result[end:]

        # Second pass: Clean up any remaining standalone !? that might have been missed
        # This handles edge cases where the pattern might be malformed
        result = re.sub(r'!\?(?![^,]*,)', 'not ', result)
        
        # First: Multi-character operators
        if '!in' in result:
            result = result.replace('!in', ' not in ')
        
        if '!=' in result:
            result = result.replace('!=', ' != ')
            
        if '<=' in result:
            result = result.replace('<=', ' <= ')
            
        if '>=' in result:
            result = result.replace('>=', ' >= ')
        
        # FIX: Handle == operator with proper spacing
        if '==' in result:
            # Use regex to add spaces around == if not already present
            result = re.sub(r'(\S)==(\S)', r'\1 == \2', result)
            # Clean up multiple spaces
            result = re.sub(r' +== +', ' == ', result)
        
        # Then: Single character operators (but not already handled)
        if '&' in result:
            result = result.replace('&', ' and ')
            
        if '|' in result:
            result = result.replace('|', ' or ')
        
        # Finally: Standalone ! (but not those already in !=, !in, !?, or !N())
        # Use regex to only replace ! that's not part of !=, !in, !?, or !N(
        result = re.sub(r'!(?![=in?N])', 'not ', result)
        
        return result

    def _fix_ambiguous_names(self, text: str) -> str:
        """Fix ambiguous name expansions in context."""
        # Fix os.st -> os.stat in os module context
        import re
        
        # Pattern: os.st( -> os.stat(
        text = re.sub(r'\bos\.st\(', 'os.stat(', text)
        
        # Pattern: os.st(var).st_something -> os.stat(var).st_something  
        text = re.sub(r'\bos\.st\(([^)]+)\)\.st_', r'os.stat(\1).st_', text)
        
        # Fix common stat attributes that might get truncated
        text = re.sub(r'\.st_siz\b', '.st_size', text)
        text = re.sub(r'\.st_si\b', '.st_size', text)
        text = re.sub(r'\.st_mti\b', '.st_mtime', text)
        text = re.sub(r'\.st_cti\b', '.st_ctime', text)
        
        return text

    def _parse_condition_string(self, condition_str: str) -> ast.AST:
        """Parse a condition string with proper operator expansion and error handling."""
        condition_str = condition_str.strip()
        
        try:
            # Apply operator normalization first
            condition_str = self._fix_operator_spacing(condition_str)
            
            # CRITICAL: Expand compressed operators FIRST
            condition_str = self.expand_compressed_operators(condition_str)
            
            # Handle chain alias in compressed operators BEFORE existing !in check
            # Pattern: x!ing0 -> x not in self.config (where g0 -> s.c)
            import re
            chain_pattern = r'(\w+)!in(g\d+)'
            match = re.match(chain_pattern, condition_str)
            if match:
                left_var = match.group(1)
                chain_alias = match.group(2)
                
                # Resolve chain alias
                if hasattr(self, 'chain_aliases') and chain_alias in self.chain_aliases:
                    chain = self.chain_aliases[chain_alias]
                    # Parse left side
                    left = self._parse_expression_string(left_var)
                    # Parse right side (the chain)
                    right = self._parse_literal_attribute_chain(chain)
                    return ast.Compare(left=left, ops=[ast.NotIn()], comparators=[right])
            
            # CRITICAL: Handle compressed "not in" pattern: d!inb -> d not in b
            if '!in' in condition_str:
                # Find the position of !in
                not_in_idx = condition_str.index('!in')
                left_str = condition_str[:not_in_idx].strip()
                right_str = condition_str[not_in_idx+3:].strip()  # Skip the "!in"
                
                # Parse left and right expressions
                left = self._parse_expression_string(left_str)
                right = self._parse_expression_string(right_str)
                
                return ast.Compare(left=left, ops=[ast.NotIn()], comparators=[right])
            
            # Handle special dense conditions BEFORE general expansion
            if condition_str.startswith('N(') and condition_str.endswith(')'):
                # is None check: N(var)
                var_str = condition_str[2:-1]
                var = ast.Name(id=var_str, ctx=ast.Load())
                return ast.Compare(left=var, ops=[ast.Is()], comparators=[ast.Constant(value=None)])
            
            if condition_str.startswith('!N(') and condition_str.endswith(')'):
                # is not None check: !N(var)
                var_str = condition_str[3:-1]
                var = ast.Name(id=var_str, ctx=ast.Load())
                return ast.Compare(left=var, ops=[ast.IsNot()], comparators=[ast.Constant(value=None)])
            
            # Handle compressed "not in" pattern: f!ina -> f not in a
            if '!' in condition_str and 'in' in condition_str:
                # Look for pattern like "f!ina" which should be "f not in a"
                exclamation_idx = condition_str.index('!')
                if exclamation_idx > 0:
                    if condition_str[exclamation_idx:exclamation_idx+3] == '!in':
                        # Split at the exclamation mark
                        left_str = condition_str[:exclamation_idx]
                        right_str = condition_str[exclamation_idx+3:]  # Skip "!in"
                        left = self._parse_expression_string(left_str.strip())
                        right = self._parse_expression_string(right_str.strip())
                        return ast.Compare(left=left, ops=[ast.NotIn()], comparators=[right])
                    elif condition_str[exclamation_idx:exclamation_idx+4] == '!ins':
                        # Special case: "!ins" means "!in s" (not in s/self)
                        left_str = condition_str[:exclamation_idx]
                        right_str = 's' + condition_str[exclamation_idx+4:]  # Replace "!ins" with "s"
                        left = self._parse_expression_string(left_str.strip())
                        right = self._parse_expression_string(right_str.strip())
                        return ast.Compare(left=left, ops=[ast.NotIn()], comparators=[right])
            
            # Handle binary operators with ASCII - order matters!
            # CRITICAL: Check for 'not in' before 'in' to avoid incorrect splitting
            for op_text, op_class in [
                ('!=', ast.NotEq),
                ('==', ast.Eq),
                ('<=', ast.LtE),
                ('>=', ast.GtE),
                (' not in ', ast.NotIn),  # Check ' not in ' before 'in' - with spaces
                ('!in', ast.NotIn),       # This should come after the compressed pattern above
                (' in ', ast.In),         # Check ' in ' with spaces
                ('in ', ast.In),          # Check 'in ' with trailing space
                (' in', ast.In),          # Check ' in' with leading space
                ('<', ast.Lt),
                ('>', ast.Gt),
            ]:
                if op_text in condition_str:
                    parts = condition_str.split(op_text, 1)
                    if len(parts) == 2:
                        left_str, right_str = parts
                        left = self._parse_expression_string(left_str.strip())
                        right = self._parse_expression_string(right_str.strip())
                        return ast.Compare(left=left, ops=[op_class()], comparators=[right])
            
            # Fallback: parse as expression with error handling
            try:
                result = self._parse_expression_string(condition_str)
                # If we get a Name node for what should be a condition, it might be malformed
                if isinstance(result, ast.Name) and (' ' in condition_str or '(' in condition_str):
                    # This is likely a malformed condition with spaces or unclosed parentheses - return safe fallback
                    error_id = self._stable_hash(condition_str, 6)
                    logger.warning(f"Malformed condition [{error_id}]: {condition_str[:30]}...")
                    return ast.Constant(value=False)
                return result
            except Exception:
                # If expression parsing fails, return safe fallback
                error_id = self._stable_hash(condition_str, 6)
                logger.warning(f"Failed to parse condition [{error_id}]: {condition_str[:30]}...")
                return ast.Constant(value=False)
            
        except Exception as e:
            # Enhanced error handling with stable identifier
            error_id = self._stable_hash(condition_str, 6)
            logger.warning(f"Condition parse fail [{error_id}]: {condition_str[:30]}...")
            
            # Return a safe constant condition (False)
            return ast.Constant(value=False)
    
    def _parse_expression_string(self, expr_str: str) -> ast.AST:
        """Parse an expression string, handling dense notation with improved error handling"""
        expr_str = expr_str.strip()
        
        # Apply operator normalization first
        expr_str = self._fix_operator_spacing(expr_str)
        
        # Pre-process to fix known ambiguous expansions
        expr_str = self._fix_ambiguous_names(expr_str)
        
        try:
            # Handle braced expressions FIRST - distinguish between dictionaries, statement blocks, and expressions
            # This must come before attribute access parsing to prevent misinterpretation
            if expr_str.startswith('{') and expr_str.endswith('}'):
                inner_content = expr_str[1:-1].strip()
                
                # Check if this is a statement block (contains assignments or statements)
                if self._is_statement_block(inner_content):
                    # This is a statement block, parse as assignment or statement
                    return self._parse_statement_block(inner_content)
                elif self._is_dictionary_literal(inner_content):
                    # This is a dictionary literal with key:value pairs
                    return self._parse_ultra_dense_dict(expr_str)
                else:
                    # This is just an expression wrapped in braces - unwrap and parse as expression
                    return self._parse_expression_string(inner_content)
            
            # Handle pooled constants first
            if expr_str.startswith('p') and expr_str[1:].isdigit():
                # Pool reference
                pool_id = expr_str
                if hasattr(self, 'pools') and pool_id in self.pools:
                    return ast.Constant(value=self.pools[pool_id])
                elif pool_id in self.constant_pool:
                    # Find the original value
                    for value, pid in self.constant_pool.items():
                        if pid == pool_id:
                            return ast.Constant(value=value)
                return ast.Constant(value=f"POOL_{pool_id}")
            
            # Handle hash references like #911, #495, hash_xxxx
            if expr_str.startswith('#') or expr_str.startswith('hash_'):
                # Resolve to actual value
                hash_key = expr_str.replace('hash_', '#') if expr_str.startswith('hash_') else expr_str
                if hasattr(self, 'hash_to_value') and hash_key in self.hash_to_value:
                    hash_entry = self.hash_to_value[hash_key]
                    value = hash_entry['value'] if isinstance(hash_entry, dict) else hash_entry
                    return ast.Constant(value=value)
                # Check if it's using the new hash_ format in storage
                if hasattr(self, 'hash_to_value') and expr_str in self.hash_to_value:
                    hash_entry = self.hash_to_value[expr_str]
                    value = hash_entry['value'] if isinstance(hash_entry, dict) else hash_entry
                    return ast.Constant(value=value)
                # Fallback: try to parse as number if it looks like one (for legacy # format)
                if expr_str.startswith('#'):
                    try:
                        if expr_str[1:].isdigit():
                            return ast.Constant(value=int(expr_str[1:]))
                    except ValueError:
                        pass
                # Fallback
                return ast.Constant(value=expr_str)
            
            # Handle chain aliases (gN) - including function calls
            if expr_str.startswith('g') and len(expr_str) > 1:
                # Check if it's a function call like g1(...)
                if '(' in expr_str:
                    paren_idx = expr_str.index('(')
                    alias_id = expr_str[:paren_idx]
                    args_part = expr_str[paren_idx:]
                    
                    # Resolve the alias
                    if hasattr(self, 'chain_aliases') and alias_id in self.chain_aliases:
                        chain = self.chain_aliases[alias_id]
                        # IMPORTANT: Don't apply CID resolution to the chain components
                        # The chain should be treated as literal attribute access
                        # Remove trailing () if present in the stored chain
                        if chain.endswith('()'):
                            chain = chain[:-2]
                        # Parse the full expression with args using literal chain expansion
                        return self._parse_literal_chain_with_args(chain, args_part)
                else:
                    # Non-function alias
                    alias_id = expr_str
                    if hasattr(self, 'chain_aliases') and alias_id in self.chain_aliases:
                        chain = self.chain_aliases[alias_id]
                        # IMPORTANT: Don't apply CID resolution to the chain components
                        # Parse as literal attribute chain without name mapping
                        return self._parse_literal_attribute_chain(chain)
                
                # Fallback to existing logic for backward compatibility
                if expr_str[1:].isdigit():
                    alias_id = expr_str
                    if alias_id in self.alias_chains_dict:
                        chain = self.alias_chains_dict[alias_id]
                        return self._parse_expression_string(chain)
                    return ast.Name(id=f"ALIAS_{alias_id}", ctx=ast.Load())
            
            # Handle compressed patterns first
            if '!ins' in expr_str:
                expr_str = expr_str.replace('!ins', '!in s')
            
            # Fix Division Operator Misuse - handle patterns like "ar / '#5787.wr(as)'"
            if '/' in expr_str and "'" in expr_str:
                # This is likely a misparse of method call
                parts = expr_str.split('/')
                if len(parts) == 2 and parts[1].strip().startswith("'"):
                    # Convert to method call
                    obj = parts[0].strip()
                    method_str = parts[1].strip().strip("'")
                    if '.' in method_str:
                        method_parts = method_str.split('.', 1)
                        # Extract method name without parentheses
                        method_name = method_parts[1].split('(')[0]
                        # Return attribute access
                        return ast.Attribute(
                            value=ast.Name(id=obj, ctx=ast.Load()),
                            attr=method_name,
                            ctx=ast.Load()
                        )
            
            # Check for clearly invalid syntax BEFORE trying to parse as binary operations
            if any(pattern in expr_str for pattern in ['!@', '#$', '$%', '%^', '!@#', '@#$', '#$%']) or \
               ('unclosed' in expr_str and '[' in expr_str and ']' not in expr_str) or \
               ('malformed' in expr_str and '{' in expr_str and ':' in expr_str):
                # This looks like invalid syntax, return error constant
                error_id = self._stable_hash(expr_str, 6)
                logger.warning(f"Invalid syntax detected [{error_id}]: {expr_str[:30]}...")
                return ast.Constant(value=f"PARSE_ERROR_{error_id}")
            
            # Handle binary operations BEFORE method calls to catch expressions like method()+1
            for op_char, op_class in [
                ('==', ast.Eq), ('!=', ast.NotEq), ('<=', ast.LtE), ('>=', ast.GtE),
                ('<', ast.Lt), ('>', ast.Gt), ('!in', ast.NotIn), ('in', ast.In),
                ('+', ast.Add), ('-', ast.Sub), ('*', ast.Mult), ('/', ast.Div),
            ]:
                if op_char in expr_str:
                    # Split by the operator, but be careful with parentheses
                    parts = self._split_by_operator(expr_str, op_char)
                    if len(parts) == 2:
                        left = self._parse_expression_string(parts[0].strip())
                        right = self._parse_expression_string(parts[1].strip())
                        if op_char in ['==', '!=', '<=', '>=', '<', '>', 'in', '!in']:
                            op_map = {
                                '==': ast.Eq(), '!=': ast.NotEq(), '<=': ast.LtE(), '>=': ast.GtE(),
                                '<': ast.Lt(), '>': ast.Gt(), 'in': ast.In(), '!in': ast.NotIn()
                            }
                            return ast.Compare(left=left, ops=[op_map[op_char]], comparators=[right])
                        else:
                            return ast.BinOp(left=left, op=op_class(), right=right)
            
            # Handle FLOW function calls FIRST (before general method calls)
            if expr_str.startswith('C(') and expr_str.endswith(')'):
                return self._parse_call_expression(expr_str)
            
            # Handle method calls with arguments: obj.method(args)
            if '(' in expr_str and ')' in expr_str:
                return self._parse_call_with_args(expr_str)
            
            # Handle attribute access: obj.attr
            if '.' in expr_str and not self._is_number(expr_str):
                return self._parse_attribute_access(expr_str)
            
            # Handle placeholder with better context resolution
            if expr_str == '?':
                # Check if we're in a 'not in' context and can infer the container
                # This is a common pattern in validation loops
                if hasattr(self, 'current_loop_iterator'):
                    # Use the loop iterator as the container (common pattern)
                    return ast.Name(id=self.current_loop_iterator, ctx=ast.Load())
                elif hasattr(self, 'last_defined_list'):
                    # Use the most recently defined list/container
                    return ast.Name(id=self.last_defined_list, ctx=ast.Load())
                else:
                    # As a last resort, check for common validation patterns
                    # In validation contexts, it's often 'required_fields' or similar
                    return ast.Name(id='_container', ctx=ast.Load())
            
            # Handle dense builtins
            dense_builtins = {
                'T': 'True',
                'F': 'False', 
                'N': 'None',
                's': 'self',
                'c': 'cls',
            }
            if expr_str in dense_builtins:
                name = dense_builtins[expr_str]
                if name in ['True', 'False', 'None']:
                    return ast.Constant(value=eval(name))
                return ast.Name(id=name, ctx=ast.Load())
            
            # Handle literal Python constants
            if expr_str in ['True', 'False', 'None']:
                return ast.Constant(value=eval(expr_str))
            
            # Handle lists
            if expr_str.startswith('[') and expr_str.endswith(']'):
                if expr_str == '[]':
                    return ast.List(elts=[], ctx=ast.Load())
                else:
                    items_str = expr_str[1:-1]
                    items = []
                    for item_str in items_str.split(','):
                        if item_str.strip():
                            items.append(self._parse_expression_string(item_str.strip()))
                    return ast.List(elts=items, ctx=ast.Load())
            
            # Handle string literals
            if (expr_str.startswith('"') and expr_str.endswith('"')) or (expr_str.startswith("'") and expr_str.endswith("'")):
                return ast.Constant(value=expr_str[1:-1])
            
            # Handle numbers
            try:
                if '.' in expr_str and self._is_number(expr_str):
                    return ast.Constant(value=float(expr_str))
                elif expr_str.isdigit() or (expr_str.startswith('-') and expr_str[1:].isdigit()):
                    return ast.Constant(value=int(expr_str))
            except ValueError:
                pass
            
            # Handle subscripts: obj[index]
            if '[' in expr_str and ']' in expr_str and not self._is_number(expr_str):
                bracket_start = expr_str.index('[')
                bracket_end = expr_str.rindex(']')
                if bracket_end > bracket_start:
                    obj_str = expr_str[:bracket_start]
                    index_str = expr_str[bracket_start+1:bracket_end]
                    
                    # Parse the object and index
                    obj = self._parse_expression_string(obj_str.strip())
                    index = self._parse_expression_string(index_str.strip())
                    
                    return ast.Subscript(value=obj, slice=index, ctx=ast.Load())
            
            # Handle compressed patterns first
            if '!ins' in expr_str:
                expr_str = expr_str.replace('!ins', '!in s')
            
            # Apply name mapping if available, but with context awareness
            if expr_str in self.reverse_map:
                expr_str = self.reverse_map[expr_str]
            elif expr_str in self.name_map:
                # Context-aware expansion for ambiguous cases
                if expr_str == 'st' and hasattr(self, '_current_context'):
                    # If we're in an os module context, prefer 'stat' over 'strip'
                    if self._current_context and 'os.' in self._current_context:
                        expr_str = 'stat'
                    else:
                        expr_str = self.name_map[expr_str]
                else:
                    expr_str = self.name_map[expr_str]
            
            # Default: treat as variable name
            return ast.Name(id=expr_str, ctx=ast.Load())
            
        except Exception as e:
            # Enhanced error handling - provide fallback with stable identifier
            error_id = self._stable_hash(expr_str, 6)
            logger.warning(f"Expression parse fail [{error_id}]: {expr_str[:30]}...")
            
            # Return a safe constant with error information
            return ast.Constant(value=f"PARSE_ERROR_{error_id}")
    
    def _parse_ultra_dense_dict(self, dict_str: str) -> ast.AST:
        """
        Parse ultra-dense dictionary: {p2:#466,#758:F,p0:100,p1:30}
        """
        if not dict_str.startswith('{') or not dict_str.endswith('}'):
            return ast.Dict(keys=[], values=[])
        
        inner = dict_str[1:-1]  # Remove braces
        if not inner:
            return ast.Dict(keys=[], values=[])
        
        keys = []
        values = []
        
        # Split by comma, but handle nested structures
        pairs = self._split_dict_pairs(inner)
        
        for pair in pairs:
            if ':' in pair:
                key_str, val_str = pair.split(':', 1)
                
                # Parse key
                if key_str.startswith('p') and key_str[1:].isdigit():
                    # Pool reference as key
                    if hasattr(self, 'pools') and key_str in self.pools:
                        key = ast.Constant(value=self.pools[key_str])
                    else:
                        key = ast.Constant(value=key_str)  # Fallback
                elif key_str.startswith('#') or key_str.startswith('hash_'):
                    # Hash reference - resolve to actual value
                    hash_key = key_str.replace('hash_', '#') if key_str.startswith('hash_') else key_str
                    if hasattr(self, 'hash_to_value') and hash_key in self.hash_to_value:
                        hash_entry = self.hash_to_value[hash_key]
                        value = hash_entry['value'] if isinstance(hash_entry, dict) else hash_entry
                        key = ast.Constant(value=value)
                    elif hasattr(self, 'hash_to_value') and key_str in self.hash_to_value:
                        hash_entry = self.hash_to_value[key_str]
                        value = hash_entry['value'] if isinstance(hash_entry, dict) else hash_entry
                        key = ast.Constant(value=value)
                    else:
                        key = ast.Constant(value=key_str)  # Fallback
                elif key_str.startswith('claude_mapping_'):
                    # Claude mapping identifiers - treat as string keys directly
                    key = ast.Constant(value=key_str)
                else:
                    key = self._parse_expression_string(key_str)
                
                # Parse value
                value = self._parse_expression_string(val_str)
                
                keys.append(key)
                values.append(value)
        
        return ast.Dict(keys=keys, values=values)

    def _is_statement_block(self, content: str) -> bool:
        """
        Determine if braced content represents a statement block vs dictionary.
        
        Args:
            content: Inner content of braces (without { })
            
        Returns:
            True if this is a statement block, False if dictionary
        """
        if not content.strip():
            return False
        
        # Check for statement keywords that indicate this is code, not data
        statement_indicators = ['return', 'break', 'continue', 'pass', 'if ', 'for ', 
                               'while ', 'try', 'except', '@', 'R', 'B', 'K', '_']
        for indicator in statement_indicators:
            if content.startswith(indicator) or f';{indicator}' in content:
                return True
        
        # Check for semicolon-separated statements (common in CAI3)
        if ';' in content:
            return True
        
        # Check for assignment operators (excluding comparison operators)
        # This regex matches '=' but not '==', '!=', '<=', '>='
        assignment_pattern = r'(?<![!<>=])=(?!=)'
        has_assignment = re.search(assignment_pattern, content)
        
        if has_assignment:
            # For mixed content, analyze the structure more carefully
            # Split by comma to check individual parts
            parts = [part.strip() for part in content.split(',')]
            
            assignment_parts = 0
            dict_parts = 0
            
            for part in parts:
                if re.search(assignment_pattern, part):
                    # Check if this looks like key = value vs key: value
                    if ':' in part and part.find(':') < part.find('='):
                        # Format like "key: x = y" - likely dictionary with assignment value
                        dict_parts += 1
                    else:
                        # Format like "x = y" or "x = y: z" - likely assignment
                        assignment_parts += 1
                elif ':' in part and '=' not in part:
                    # Pure key:value - dictionary part
                    dict_parts += 1
                else:
                    # Ambiguous, but if it contains assignment, lean towards statement
                    if '=' in part:
                        assignment_parts += 1
                    else:
                        dict_parts += 1
            
            # If more assignment-like parts than dictionary parts, it's a statement block
            # For ties (equal parts), if there are any assignments, lean towards statement
            return assignment_parts >= dict_parts
        
        # If it looks like key:value pairs, it's likely a dictionary
        if ':' in content and '=' not in content:
            return False
        
        # Default to False to preserve existing behavior for actual dictionaries
        return False

    def _is_dictionary_literal(self, content: str) -> bool:
        """
        Determine if braced content represents a dictionary literal vs expression.
        
        Args:
            content: Inner content of braces (without { })
            
        Returns:
            True if this is a dictionary literal, False otherwise
        """
        if not content.strip():
            return True  # Empty braces = empty dictionary
        
        # Check for clear dictionary patterns: key:value pairs
        if ':' in content and '=' not in content:
            # Likely dictionary if it has colons but no assignments
            return True
        
        # Check for mixed key:value and key=value patterns
        if ':' in content and '=' in content:
            # Need to analyze more carefully - this could be a complex dictionary
            # or a statement with both types of syntax
            parts = [part.strip() for part in content.split(',')]
            dict_parts = 0
            
            for part in parts:
                if ':' in part and part.find(':') < part.find('=') if '=' in part else True:
                    dict_parts += 1
            
            # If more than half the parts look like dictionary entries, treat as dictionary
            return dict_parts > len(parts) / 2
        
        # Default to False - this is likely an expression or statement
        return False

    def _parse_statement_block(self, content: str) -> ast.AST:
        """
        Parse braced content as a statement block instead of dictionary.
        
        Args:
            content: Inner content of braces (without { })
            
        Returns:
            AST node representing the statement(s)
        """
        content = content.strip()
        
        if not content or content == '_':
            return self._fix_ast_node_attributes(ast.Pass())
        
        # For CAI3 translation context, we need to parse this as an assignment
        # Check if this is an assignment pattern
        assignment_pattern = r'(?<![!<>=])=(?!=)'
        if re.search(assignment_pattern, content):
            # This is an assignment statement
            equals_match = re.search(assignment_pattern, content)
            if equals_match:
                equals_pos = equals_match.start()
                target_str = content[:equals_pos].strip()
                value_str = content[equals_pos + 1:].strip()
                
                try:
                    # For statement blocks, try using Python's built-in AST parser first
                    # This avoids the compressed name expansion issues
                    try:
                        # Try parsing the full assignment as standard Python
                        full_assignment = f"{target_str} = {value_str}"
                        parsed = ast.parse(full_assignment, mode='exec')
                        if parsed.body and isinstance(parsed.body[0], ast.Assign):
                            assign_node = parsed.body[0]
                            
                            # Special handling for CAI3: if value is a set with single element,
                            # extract the element (since {expr} in CAI3 means expr, not set)
                            if (isinstance(assign_node.value, ast.Set) and 
                                len(assign_node.value.elts) == 1 and
                                value_str.startswith('{') and value_str.endswith('}')):
                                # Extract the single expression from the set
                                assign_node.value = assign_node.value.elts[0]
                            
                            return self._fix_ast_node_attributes(assign_node)
                    except SyntaxError:
                        # Fall back to custom parsing if standard Python fails
                        pass
                    
                    # Parse target (left side of assignment)
                    target = self._parse_expression_string(target_str)
                    
                    # Parse value (right side of assignment)
                    # IMPORTANT: If value starts with '{', parse it recursively
                    if value_str.startswith('{') and value_str.endswith('}'):
                        # This might be a nested expression
                        inner_content = value_str[1:-1].strip()
                        
                        # For CAI3 context, always try to parse braced content as expression first
                        # since {expression} is common notation for computed values
                        try:
                            # Try parsing the inner content as a Python expression
                            parsed_inner = ast.parse(inner_content, mode='eval')
                            value = parsed_inner.body
                        except SyntaxError:
                            # If that fails, check if it's a statement block or dictionary
                            if self._is_statement_block(inner_content):
                                # Fall back to custom parsing for statement block
                                value = self._parse_expression_string(inner_content)
                            else:
                                # It's a dictionary value
                                value = self._parse_ultra_dense_dict(value_str)
                    else:
                        # Try Python AST parsing for the value first
                        try:
                            parsed_value = ast.parse(value_str, mode='eval')
                            value = parsed_value.body
                        except SyntaxError:
                            # Fall back to custom parsing
                            value = self._parse_expression_string(value_str)
                    
                    # Set proper context for assignment target
                    if isinstance(target, ast.Name):
                        target.ctx = ast.Store()
                    elif isinstance(target, (ast.Attribute, ast.Subscript)):
                        target.ctx = ast.Store()
                    
                    assign_node = ast.Assign(targets=[target], value=value)
                    return self._fix_ast_node_attributes(assign_node)
                    
                except Exception as e:
                    logger.warning(f"Failed to parse assignment in statement block '{content}': {e}")
                    return self._fix_ast_node_attributes(ast.Pass())
        
        # Handle multiple semicolon-separated statements
        if ';' in content:
            # For now, parse the first statement
            first_stmt = content.split(';')[0].strip()
            if first_stmt:
                return self._parse_statement_block(first_stmt)
        
        # Try to parse as a simple expression
        try:
            # Try Python AST parsing first
            parsed = ast.parse(content, mode='eval')
            expr = parsed.body
            return self._fix_ast_node_attributes(ast.Expr(value=expr))
        except SyntaxError:
            # Fall back to custom parsing
            try:
                expr = self._parse_expression_string(content)
                return self._fix_ast_node_attributes(ast.Expr(value=expr))
            except:
                return self._fix_ast_node_attributes(ast.Pass())

    def _split_dict_pairs(self, inner: str) -> List[str]:
        """Split dictionary pairs respecting nested structures."""
        pairs = []
        current = ""
        depth = 0
        
        for char in inner:
            if char in '{[(':
                depth += 1
            elif char in '}])':
                depth -= 1
            elif char == ',' and depth == 0:
                pairs.append(current.strip())
                current = ""
                continue
            current += char
        
        if current.strip():
            pairs.append(current.strip())
        
        return pairs
    
    def _is_number(self, s: str) -> bool:
        """Check if string represents a number"""
        try:
            float(s)
            return True
        except ValueError:
            return False
    
    def _parse_call_with_args(self, expr_str: str) -> ast.AST:
        """Parse method call with arguments: obj.method(args) or g1(args)"""
        # Find the function part and args part
        paren_idx = expr_str.index('(')
        func_part = expr_str[:paren_idx]
        
        # Find the matching closing parenthesis for the first opening parenthesis
        paren_count = 0
        closing_paren_idx = -1
        for i in range(paren_idx, len(expr_str)):
            if expr_str[i] == '(':
                paren_count += 1
            elif expr_str[i] == ')':
                paren_count -= 1
                if paren_count == 0:
                    closing_paren_idx = i
                    break
        
        if closing_paren_idx == -1:
            # Fallback to old behavior if no matching parenthesis found
            args_part = expr_str[paren_idx+1:-1]  # Remove ( and )
            remainder = ""
        else:
            args_part = expr_str[paren_idx+1:closing_paren_idx]  # Arguments between matching parentheses
            remainder = expr_str[closing_paren_idx+1:]  # Everything after the closing parenthesis
        
        # Check if func_part is a chain alias first (gN)
        if func_part.startswith('g') and func_part[1:].isdigit():
            alias_id = func_part
            if hasattr(self, 'chain_aliases') and alias_id in self.chain_aliases:
                chain = self.chain_aliases[alias_id]
                # Parse the chain as an attribute access
                func_ast = self._parse_expression_string(chain)
            elif alias_id in self.alias_chains_dict:
                chain = self.alias_chains_dict[alias_id]
                # Parse the chain as an attribute access
                func_ast = self._parse_expression_string(chain)
            else:
                # Fallback to treating as a regular name
                func_ast = ast.Name(id=f"ALIAS_{alias_id}", ctx=ast.Load())
        else:
            # Parse the function (could be an attribute access)
            func_ast = self._parse_attribute_access(func_part)
        
        # Parse arguments
        args = []
        if args_part.strip():
            # Split by commas, but handle nested structures
            arg_strs = self._split_args(args_part)
            for arg_str in arg_strs:
                if arg_str.strip():
                    args.append(self._parse_expression_string(arg_str.strip()))
        
        # Create the function call
        call_ast = ast.Call(func=func_ast, args=args, keywords=[])
        
        # Handle remainder (like [1].lo() after the function call)
        if remainder:
            remainder = remainder.strip()
            if remainder:
                # Parse the remainder as additional operations on the call result
                # For now, create a composite expression by recursively parsing
                full_expr = f"_temp{remainder}"
                remainder_ast = self._parse_expression_string(full_expr)
                
                # Replace the _temp with our call_ast
                if isinstance(remainder_ast, ast.Attribute) and isinstance(remainder_ast.value, ast.Name) and remainder_ast.value.id == '_temp':
                    remainder_ast.value = call_ast
                    return remainder_ast
                elif isinstance(remainder_ast, ast.Subscript) and isinstance(remainder_ast.value, ast.Name) and remainder_ast.value.id == '_temp':
                    remainder_ast.value = call_ast
                    return remainder_ast
                elif isinstance(remainder_ast, ast.Call) and hasattr(remainder_ast.func, 'value') and isinstance(remainder_ast.func.value, ast.Name) and remainder_ast.func.value.id == '_temp':
                    remainder_ast.func.value = call_ast
                    return remainder_ast
                else:
                    # Fallback: try to parse manually
                    return self._handle_chained_operations(call_ast, remainder)
        
        return call_ast
    
    def _handle_chained_operations(self, base_ast: ast.AST, remainder: str) -> ast.AST:
        """Handle chained operations like [1].method() after a function call"""
        current = base_ast
        remainder = remainder.strip()
        
        # Process the remainder step by step
        i = 0
        while i < len(remainder):
            if remainder[i] == '[':
                # Handle subscript like [1]
                closing_bracket = remainder.find(']', i)
                if closing_bracket == -1:
                    break
                index_str = remainder[i+1:closing_bracket]
                index_ast = self._parse_expression_string(index_str)
                current = ast.Subscript(value=current, slice=index_ast, ctx=ast.Load())
                i = closing_bracket + 1
            elif remainder[i] == '.':
                # Handle attribute access or method call
                i += 1  # Skip the dot
                # Find the end of the attribute/method name
                attr_start = i
                while i < len(remainder) and (remainder[i].isalnum() or remainder[i] == '_'):
                    i += 1
                attr_name = remainder[attr_start:i]
                
                # Expand abbreviations
                expanded_attr = self.METHOD_ABBREVIATIONS.get(attr_name, attr_name)
                if expanded_attr == attr_name:
                    expanded_attr = self._expand_compressed_name(attr_name)
                
                # Check if this is a method call
                if i < len(remainder) and remainder[i] == '(':
                    # This is a method call
                    paren_count = 0
                    args_start = i + 1
                    for j in range(i, len(remainder)):
                        if remainder[j] == '(':
                            paren_count += 1
                        elif remainder[j] == ')':
                            paren_count -= 1
                            if paren_count == 0:
                                args_end = j
                                args_str = remainder[args_start:args_end]
                                # Parse arguments
                                args = []
                                if args_str.strip():
                                    arg_strs = self._split_args(args_str)
                                    for arg_str in arg_strs:
                                        if arg_str.strip():
                                            args.append(self._parse_expression_string(arg_str.strip()))
                                
                                func_ast = ast.Attribute(value=current, attr=expanded_attr, ctx=ast.Load())
                                current = ast.Call(func=func_ast, args=args, keywords=[])
                                i = j + 1
                                break
                else:
                    # This is just an attribute access
                    current = ast.Attribute(value=current, attr=expanded_attr, ctx=ast.Load())
            else:
                # Skip unknown characters
                i += 1
        
        return current
    
    def _preprocess_conditional_expression(self, condition_str: str) -> str:
        """
        FUNDAMENTAL FIX: Preprocess conditional expressions to prevent malformed generation.
        This addresses the root cause rather than applying post-processing fixes.
        """
        import re
        
        # Fix compressed patterns that create parsing issues
        # Pattern: '#hashins.object' -> '#hash' in s.object
        condition_str = re.sub(r"'(#\w+)'ins\.", r"'\1' in s.", condition_str)
        
        # Pattern: 'hash_xxxxins.object' -> 'hash_xxxx' in s.object  
        condition_str = re.sub(r"'(hash_\w+)'ins\.", r"'\1' in s.", condition_str)
        
        # Pattern: hashins.object -> hash in s.object (without quotes)
        condition_str = re.sub(r"([#\w]+)ins\.", r"\1 in s.", condition_str)
        
        # Pattern: hash_xxxxins.object -> hash_xxxx in s.object (without quotes)
        condition_str = re.sub(r"(hash_\w+)ins\.", r"\1 in s.", condition_str)
        
        # Ensure proper spacing around 'in' operator
        condition_str = re.sub(r"([^'\s])in([^'\s])", r"\1 in \2", condition_str)
        
        return condition_str
    
    def _preprocess_body_statement(self, stmt_str: str) -> str:
        """
        FUNDAMENTAL FIX: Preprocess body statements to prevent malformed expressions.
        This ensures proper statement structure before AST parsing.
        """
        import re
        
        # Fix redundant chained access: obj[key].obj[key].method -> obj[key].method
        redundant_pattern = r'(\w+\[[^\]]+\])\.\1\.'
        stmt_str = re.sub(redundant_pattern, r'\1.', stmt_str)
        
        # Fix method calls that lack proper object reference
        # Pattern: .method[args] -> proper_object.method[args]
        if stmt_str.startswith('.') and '[' in stmt_str:
            # This is likely a malformed method call
            method_part = stmt_str[1:]  # Remove leading dot
            if '.' in method_part:
                # Multiple dots - likely s.data_buffer['key'].append(...)
                # Fix to proper conditional execution
                parts = method_part.split('.')
                if len(parts) >= 2 and 'append(' in stmt_str:
                    # Convert to proper append statement
                    base_obj = 's.' + parts[0]  # e.g., s.data_buffer
                    remaining = '.'.join(parts[1:])  # e.g., data_buffer['key'].append(...)
                    
                    # Extract the key and append value
                    key_match = re.search(r"\['([^']+)'\]", remaining)
                    append_match = re.search(r"append\(([^)]+)\)", remaining)
                    
                    if key_match and append_match:
                        key = key_match.group(1)
                        value = append_match.group(1)
                        return f"{base_obj}['{key}'].append({value})"
            
            # Fallback: assume s. prefix
            stmt_str = 's' + stmt_str
        
        # Fix malformed conditional expressions that become statements
        # Pattern: (condition).object.method -> if condition: object.method
        paren_method_pattern = r'\(([^)]+)\)\.(.+)$'
        match = re.match(paren_method_pattern, stmt_str)
        if match:
            condition = match.group(1)
            method_call = match.group(2)
            
            # If this looks like a membership test followed by method call
            if ' in ' in condition:
                # Convert to proper conditional block
                # This should be handled at a higher level, but return a comment for now
                return f"# CONDITIONAL: if {condition}: {method_call}"
        
        return stmt_str
    
    def _split_by_operator(self, expr_str: str, operator: str) -> List[str]:
        """Split expression by operator, respecting parentheses and brackets"""
        parts = []
        current_part = ""
        paren_depth = 0
        bracket_depth = 0
        i = 0
        
        while i < len(expr_str):
            if expr_str[i] == '(':
                paren_depth += 1
                current_part += expr_str[i]
            elif expr_str[i] == ')':
                paren_depth -= 1
                current_part += expr_str[i]
            elif expr_str[i] == '[':
                bracket_depth += 1
                current_part += expr_str[i]
            elif expr_str[i] == ']':
                bracket_depth -= 1
                current_part += expr_str[i]
            elif (paren_depth == 0 and bracket_depth == 0 and 
                  expr_str[i:i+len(operator)] == operator):
                # Found the operator at the top level
                parts.append(current_part)
                current_part = ""
                i += len(operator) - 1  # Skip the operator
            else:
                current_part += expr_str[i]
            i += 1
        
        if current_part:
            parts.append(current_part)
        
        return parts
    
    def _parse_attribute_access(self, expr_str: str) -> ast.AST:
        """Parse attribute access: obj.attr or s.c.ge"""
        parts = expr_str.split('.')
        
        # Start with the first part (might include subscripts)
        result = self._parse_name_with_subscripts(parts[0])
        
        # Build the attribute chain
        for attr in parts[1:]:
            # Check if this attribute has subscripts (like e[l])
            if '[' in attr and ']' in attr:
                # Split the attribute and subscript
                bracket_idx = attr.index('[')
                attr_name = attr[:bracket_idx]
                subscript_part = attr[bracket_idx:]
                
                # First apply attribute access
                expanded_attr = self.METHOD_ABBREVIATIONS.get(attr_name, attr_name)
                if expanded_attr == attr_name:
                    expanded_attr = self._expand_compressed_name(attr_name)
                
                result = ast.Attribute(value=result, attr=expanded_attr, ctx=ast.Load())
                
                # Then handle subscripts
                result = self._apply_subscripts(result, subscript_part)
            else:
                # Regular attribute access
                expanded_attr = self.METHOD_ABBREVIATIONS.get(attr, attr)
                if expanded_attr == attr:
                    expanded_attr = self._expand_compressed_name(attr)
                
                result = ast.Attribute(value=result, attr=expanded_attr, ctx=ast.Load())
        
        return result
    
    def _parse_name_with_subscripts(self, name_expr: str) -> ast.AST:
        """Parse a name that might have subscripts like 'arr[0]' or just 'name'"""
        if '[' not in name_expr:
            return self._parse_simple_name(name_expr)
        
        # Split name and subscripts
        bracket_idx = name_expr.index('[')
        name = name_expr[:bracket_idx]
        subscript_part = name_expr[bracket_idx:]
        
        # Parse the base name
        result = self._parse_simple_name(name)
        
        # Apply subscripts
        return self._apply_subscripts(result, subscript_part)
    
    def _apply_subscripts(self, base_ast: ast.AST, subscript_part: str) -> ast.AST:
        """Apply subscripts like [0][1] to a base AST node"""
        current = base_ast
        i = 0
        
        while i < len(subscript_part):
            if subscript_part[i] == '[':
                # Find the matching closing bracket
                bracket_count = 0
                start = i + 1
                for j in range(i, len(subscript_part)):
                    if subscript_part[j] == '[':
                        bracket_count += 1
                    elif subscript_part[j] == ']':
                        bracket_count -= 1
                        if bracket_count == 0:
                            index_str = subscript_part[start:j]
                            index_ast = self._parse_expression_string(index_str)
                            current = ast.Subscript(value=current, slice=index_ast, ctx=ast.Load())
                            i = j + 1
                            break
                else:
                    # No matching bracket found
                    break
            else:
                i += 1
        
        return current
    
    def _parse_simple_name(self, name: str) -> ast.AST:
        """Parse a simple name, applying mappings"""
        # Apply reverse name mapping
        if name in self.reverse_map:
            name = self.reverse_map[name]
        elif name in self.name_map:
            name = self.name_map[name]
        
        # Handle dense builtins
        dense_builtins = {
            'T': 'True', 'F': 'False', 'N': 'None',
            's': 'self', 'c': 'cls'
        }
        if name in dense_builtins:
            expanded = dense_builtins[name]
            if expanded in ['True', 'False', 'None']:
                return ast.Constant(value=eval(expanded))
            return ast.Name(id=expanded, ctx=ast.Load())
        
        return ast.Name(id=name, ctx=ast.Load())
    
    def _expand_compressed_name(self, name: str) -> str:
        """Expand compressed attribute names"""
        # Common compression mappings
        attr_expansions = {
            'c': 'config',
            'ge': 'get',
            'se': 'set', 
            'it': 'items',
            'no': 'now',
            'lo': 'loads',
            'x': 'processed_count',
            'e': 'error_count', 
            'd': 'data_buffer'
        }
        
        # Apply reverse name mapping first
        if name in self.reverse_map:
            return self.reverse_map[name]
        elif name in self.name_map:
            return self.name_map[name]
        
        # Apply common expansions
        return attr_expansions.get(name, name)
    
    def _parse_literal_attribute_chain(self, chain: str) -> ast.AST:
        """
        Parse an attribute chain literally without applying CID resolution.
        This is used for chain aliases to preserve the original attribute names.
        """
        parts = chain.split('.')
        
        # Start with the first part - only apply basic builtins, no CID resolution
        first_part = parts[0]
        dense_builtins = {
            'T': 'True', 'F': 'False', 'N': 'None',
            's': 'self', 'c': 'cls'
        }
        
        if first_part in dense_builtins:
            expanded = dense_builtins[first_part]
            if expanded in ['True', 'False', 'None']:
                result = ast.Constant(value=eval(expanded))
            else:
                result = ast.Name(id=expanded, ctx=ast.Load())
        else:
            result = ast.Name(id=first_part, ctx=ast.Load())
        
        # Build the attribute chain - use literal attribute names
        for attr in parts[1:]:
            # For chain aliases, preserve the literal attribute name without compression
            # Only apply basic expansions for known compressed forms
            attr_expansions = {
                'c': 'config',
                'ge': 'get',
                'se': 'set', 
                'it': 'items',
                'no': 'now',
                'lo': 'loads'
            }
            # Apply expansion but don't use CID resolution
            literal_attr = attr_expansions.get(attr, attr)
            result = ast.Attribute(value=result, attr=literal_attr, ctx=ast.Load())
        
        return result
    
    def _parse_literal_chain_with_args(self, chain: str, args_part: str) -> ast.AST:
        """
        Parse a chain alias with function call arguments, treating the chain literally.
        """
        # Parse the chain without CID resolution
        func_ast = self._parse_literal_attribute_chain(chain)
        
        # Parse arguments normally
        args_str = args_part[1:-1]  # Remove ( and )
        args = []
        if args_str.strip():
            arg_strings = self._split_args(args_str)
            for arg_str in arg_strings:
                if arg_str.strip():
                    args.append(self._parse_expression_string(arg_str.strip()))
        
        return ast.Call(func=func_ast, args=args, keywords=[])

    def _split_args(self, args_str: str) -> List[str]:
        """Split argument string by commas, respecting nested structures"""
        args = []
        current_arg = ""
        paren_depth = 0
        bracket_depth = 0
        in_quotes = False
        quote_char = None
        
        for char in args_str:
            if char in ['"', "'"]:
                if not in_quotes:
                    in_quotes = True
                    quote_char = char
                elif char == quote_char:
                    in_quotes = False
                    quote_char = None
            elif not in_quotes:
                if char == '(':
                    paren_depth += 1
                elif char == ')':
                    paren_depth -= 1
                elif char == '[':
                    bracket_depth += 1
                elif char == ']':
                    bracket_depth -= 1
                elif char == ',' and paren_depth == 0 and bracket_depth == 0:
                    args.append(current_arg)
                    current_arg = ""
                    continue
            
            current_arg += char
        
        if current_arg:
            args.append(current_arg)
        
        return args
    
    def _parse_call_expression(self, call_str: str) -> ast.AST:
        """Parse a function call expression: C(func,args)"""
        if call_str.startswith('C(') and call_str.endswith(')'):
            inner = call_str[2:-1]
            if ',' in inner:
                func_str, args_str = inner.split(',', 1)
                func = self._parse_expression_string(func_str.strip())
                
                args = []
                for arg_str in args_str.split(','):
                    if arg_str.strip():
                        args.append(self._parse_expression_string(arg_str.strip()))
                
                return ast.Call(func=func, args=args, keywords=[])
            else:
                # No arguments
                func = self._parse_expression_string(inner.strip())
                return ast.Call(func=func, args=[], keywords=[])
        
        return ast.Name(id='unknown_call', ctx=ast.Load())
    
    def _parse_expression(self, expr_str: str) -> ast.AST:
        """Parse a complete expression as a statement"""
        expr = self._parse_expression_string(expr_str)
        return ast.Expr(value=expr)

    def generate_ultra_dense_body(self, method_node: ast.FunctionDef, cid: str, 
                                local_compressions: Dict[str, str],
                                attr_compressions: Dict[str, str]) -> str:
        """
        Generate ultra-dense single-line body representation for maximum compression.
        Uses semicolon separation and aggressive abbreviation.
        """
        body_parts = []
        
        for stmt in method_node.body:
            # Skip docstrings completely in ultra-dense mode
            if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant):
                if isinstance(stmt.value.value, str):
                    continue
            
            # Convert statement to ultra-compact form
            compact_stmt = self._stmt_to_ultra_compact(stmt, local_compressions, attr_compressions)
            if compact_stmt:
                body_parts.append(compact_stmt)
        
        # Join with semicolons for single-line representation
        return ';'.join(body_parts)

    def _stmt_to_ultra_compact(self, stmt: ast.AST, 
                            locals_map: Dict[str, str],
                            attrs_map: Dict[str, str]) -> str:
        """Convert a statement to ultra-compact inline form."""
        
        if isinstance(stmt, ast.Assign):
            # Ultra-compact assignment: x=v instead of Lx=v
            target = self._compress_target(stmt.targets[0], locals_map, attrs_map)
            value = self._compress_value(stmt.value, locals_map, attrs_map)
            return f"{target}={value}"
        
        elif isinstance(stmt, ast.AugAssign):
            # Compact augmented: x+=1 instead of Sx=x+1
            target = self._compress_target(stmt.target, locals_map, attrs_map)
            op_map = {ast.Add: '+', ast.Sub: '-', ast.Mult: '*', ast.Div: '/'}
            op = op_map.get(type(stmt.op), '?')
            value = self._compress_value(stmt.value, locals_map, attrs_map)
            return f"{target}{op}={value}"
        
        elif isinstance(stmt, ast.Return):
            if stmt.value:
                value = self._compress_value(stmt.value, locals_map, attrs_map)
                return f"R{value}"  # No space after R
            return "R"
        
        elif isinstance(stmt, ast.If):
            # Ultra-compact if: (cond?t:f) for ternary, or (cond)t for simple
            cond = self._compress_condition(stmt.test, locals_map, attrs_map)
            
            # Check if this is effectively a ternary
            if len(stmt.body) == 1 and isinstance(stmt.body[0], ast.Return) and stmt.orelse:
                if len(stmt.orelse) == 1 and isinstance(stmt.orelse[0], ast.Return):
                    # Ternary return pattern
                    true_val = self._compress_value(stmt.body[0].value, locals_map, attrs_map) if stmt.body[0].value else ""
                    false_val = self._compress_value(stmt.orelse[0].value, locals_map, attrs_map) if stmt.orelse[0].value else ""
                    return f"R({cond}?{true_val}:{false_val})"
            
            # Simple if with single statement
            if len(stmt.body) == 1 and not stmt.orelse:
                body_stmt = self._stmt_to_ultra_compact(stmt.body[0], locals_map, attrs_map)
                return f"({cond}){body_stmt}"
            
            # Multi-statement if - use compact block notation
            then_part = ';'.join(self._stmt_to_ultra_compact(s, locals_map, attrs_map) for s in stmt.body)
            if stmt.orelse:
                else_part = ';'.join(self._stmt_to_ultra_compact(s, locals_map, attrs_map) for s in stmt.orelse)
                return f"({cond}?{{{then_part}}}:{{{else_part}}})"
            return f"({cond}){{{then_part}}}"
        
        elif isinstance(stmt, ast.For):
            # Ultra-compact for: @x,y{body} for iteration
            target = self._compress_target(stmt.target, locals_map, attrs_map)
            iter_val = self._compress_value(stmt.iter, locals_map, attrs_map)
            body_parts = [self._stmt_to_ultra_compact(s, locals_map, attrs_map) for s in stmt.body]
            body = ';'.join(filter(None, body_parts))
            return f"@{target},{iter_val}{{{body}}}"
        
        elif isinstance(stmt, ast.Expr):
            # Expression statement (usually function call)
            if isinstance(stmt.value, ast.Call):
                return self._compress_call(stmt.value, locals_map, attrs_map)
            return self._compress_value(stmt.value, locals_map, attrs_map)
        
        elif isinstance(stmt, ast.Try):
            # Ultra-compact try: T{body}X{handler}
            body = self._generate_ultra_dense_try_body(stmt, locals_map, attrs_map)
            
            if stmt.handlers:
                handler = stmt.handlers[0]  # Take first handler
                handler_parts = [self._stmt_to_ultra_compact(s, locals_map, attrs_map) for s in handler.body]
                handler_body = ';'.join(filter(None, handler_parts))
                exc_type = handler.type.id if handler.type and hasattr(handler.type, 'id') else ""
                if exc_type:
                    return f"T{{{body}}}X({exc_type}){{{handler_body}}}"
                return f"T{{{body}}}X{{{handler_body}}}"
            return f"T{{{body}}}"
        
        elif isinstance(stmt, ast.Pass):
            return "_"  # Single underscore for pass
        
        elif isinstance(stmt, ast.Break):
            return "B"
        
        elif isinstance(stmt, ast.Continue):
            return "K"
        
        # For unsupported statement types in ultra-dense mode, create RAW blocks
        if hasattr(self, '_create_raw_block'):
            try:
                raw_id = self._create_raw_block(stmt)
                if raw_id:
                    return f"RAW{{{raw_id}}}"
            except Exception:
                pass  # Fall through to empty string
        
        return ""

    def _compress_target(self, node: ast.AST, locals_map: Dict[str, str], 
                        attrs_map: Dict[str, str]) -> str:
        """Compress assignment target with local and attribute mappings."""
        if isinstance(node, ast.Name):
            return locals_map.get(node.id, node.id[:1] if len(node.id) > 2 else node.id)
        elif isinstance(node, ast.Attribute):
            if isinstance(node.value, ast.Name) and node.value.id == 'self':
                # Compress self.attr to s.x where x is compressed attr name
                compressed_attr = attrs_map.get(node.attr, node.attr[:2])
                return f"s.{compressed_attr}"
            obj = self._compress_value(node.value, locals_map, attrs_map)
            attr = attrs_map.get(node.attr, node.attr[:2])
            return f"{obj}.{attr}"
        elif isinstance(node, ast.Subscript):
            obj = self._compress_value(node.value, locals_map, attrs_map)
            idx = self._compress_value(node.slice, locals_map, attrs_map)
            return f"{obj}[{idx}]"
        return "?"

    def _compress_value(self, node: ast.AST, locals_map: Dict[str, str],
                    attrs_map: Dict[str, str]) -> str:
        """Compress value with validation to prevent invalid identifiers."""
        if node is None:
            return "N"
        elif isinstance(node, ast.Constant):
            if node.value is True:
                return "T"
            elif node.value is False:
                return "F"
            elif node.value is None:
                return "N"
            elif isinstance(node.value, (int, float)):
                # CRITICAL FIX: Preserve scientific notation format
                if 'e' in str(node.value).lower():
                    return str(node.value).replace(' ', '')  # Remove any spaces
                return str(node.value)
            elif isinstance(node.value, str):
                # Check for pool reference
                pool_id = self._get_pool_id(node.value)
                if pool_id:
                    return pool_id  # Return pN directly
                
                # For non-pooled strings
                if len(node.value) <= 3:
                    return f"'{node.value}'"
                
                # Generate hash reference but store properly
                hash_ref = f"hash_{self._stable_hash(node.value, 10)}"  # Use hash_ prefix instead of #
                self.hash_to_value[hash_ref] = {
                    'value': node.value,
                    'type': 'string',
                    'needs_quotes': True
                }
                return hash_ref  # Will be resolved during AST generation
            return str(node.value)
        elif isinstance(node, ast.Name):
            name = node.id
            if name == 'self':
                return 's'
            elif name == 'True':
                return 'T'
            elif name == 'False':
                return 'F'
            elif name == 'None':
                return 'N'
            
            # CRITICAL FIX: Validate compressed names
            compressed = locals_map.get(name, name[:1] if len(name) > 2 else name)
            
            # Filter out invalid characters and keywords
            if compressed in self.PYTHON_KEYWORDS:
                compressed = f"{compressed}_var"  # Add suffix to avoid keyword collision
            
            # Remove invalid characters
            if any(c in self.INVALID_IDENTIFIER_CHARS for c in compressed):
                # Use alternative compression
                stable_hash = self._stable_hash(name, 6)  # Get 6-char deterministic hash
                compressed = f"v{stable_hash[:3]}"  # v001, v002, etc.
            
            return compressed
        elif isinstance(node, ast.Attribute):
            obj = self._compress_value(node.value, locals_map, attrs_map)
            attr = attrs_map.get(node.attr, node.attr[:2])
            # Check for chain alias
            full_chain = f"{obj}.{attr}"
            alias = self._maybe_alias(full_chain)
            return alias if alias else full_chain
        elif isinstance(node, ast.Call):
            return self._compress_call(node, locals_map, attrs_map)
        elif isinstance(node, ast.List):
            if not node.elts:
                return "[]"
            items = [self._compress_value(e, locals_map, attrs_map) for e in node.elts]
            return f"[{','.join(items)}]"
        elif isinstance(node, ast.Dict):
            if not node.keys:
                return "{}"
            pairs = []
            for k, v in zip(node.keys, node.values):
                key = self._compress_value(k, locals_map, attrs_map) if k else ''
                val = self._compress_value(v, locals_map, attrs_map)
                pairs.append(f"{key}:{val}")
            return f"{{{','.join(pairs)}}}"
        elif isinstance(node, ast.BinOp):
            left = self._compress_value(node.left, locals_map, attrs_map)
            right = self._compress_value(node.right, locals_map, attrs_map)
            op_map = {ast.Add: '+', ast.Sub: '-', ast.Mult: '*', ast.Div: '/'}
            op = op_map.get(type(node.op), '?')
            return f"{left}{op}{right}"
        elif isinstance(node, ast.Compare):
            return self._compress_condition(node, locals_map, attrs_map)
        elif isinstance(node, ast.BoolOp):
            # Handle boolean operations (and, or)
            if isinstance(node.op, ast.And):
                parts = [self._compress_value(v, locals_map, attrs_map) for v in node.values]
                return f"({'&'.join(parts)})"
            elif isinstance(node.op, ast.Or):
                parts = [self._compress_value(v, locals_map, attrs_map) for v in node.values]
                return f"({'|'.join(parts)})"
            return "?"
        elif isinstance(node, ast.UnaryOp):
            operand = self._compress_value(node.operand, locals_map, attrs_map)
            if isinstance(node.op, ast.Not):
                return f"!{operand}"
            elif isinstance(node.op, ast.USub):
                return f"-{operand}"
            return f"?{operand}"
        elif isinstance(node, ast.Subscript):
            obj = self._compress_value(node.value, locals_map, attrs_map)
            idx = self._compress_value(node.slice, locals_map, attrs_map)
            return f"{obj}[{idx}]"
        
        # Handle specific unsupported expression types that commonly appear in assignments
        elif isinstance(node, (ast.Lambda, ast.ListComp, ast.DictComp, ast.SetComp, 
                              ast.GeneratorExp, ast.Await)):
            # These need RAW blocks in ultra-dense mode
            if hasattr(self, '_create_raw_block'):
                try:
                    raw_id = self._create_raw_block(node)
                    if raw_id:
                        # Extract just the raw_id from the returned string
                        if raw_id.startswith('RAW{') and raw_id.endswith('}'):
                            raw_id = raw_id[4:-1]  # Remove RAW{ and }
                        return f"RAW{{{raw_id}}}"
                except Exception:
                    pass  # Fall through to placeholder
        
        return "?"

    def _expand_name(self, name: str) -> str:
        """Expand compressed names using all available mappings."""
        # Check dense builtins first
        dense_builtins = {
            's': 'self',
            'c': 'cls',
            'T': 'True',
            'F': 'False',
            'N': 'None',
        }
        if name in dense_builtins:
            return dense_builtins[name]
        
        # Check reverse name map
        if name in self.reverse_map:
            return self.reverse_map[name]
        
        # Check name map (shouldn't normally happen but for safety)
        if name in self.name_map:
            return self.name_map[name]
        
        # Return as-is if no mapping found
        return name

    def _compress_call(self, node: ast.Call, locals_map: Dict[str, str],
                    attrs_map: Dict[str, str]) -> str:
        """Ultra-compact call notation."""
        if isinstance(node.func, ast.Attribute):
            obj = self._compress_value(node.func.value, locals_map, attrs_map)
            method = attrs_map.get(node.func.attr, node.func.attr[:2])
            
            # Special compact patterns
            if method == 'append' and len(node.args) == 1:
                arg = self._compress_value(node.args[0], locals_map, attrs_map)
                return f"{obj}+={arg}"  # Append as +=
            elif method == 'get' and len(node.args) >= 1:
                key = self._compress_value(node.args[0], locals_map, attrs_map)
                if len(node.args) > 1:
                    default = self._compress_value(node.args[1], locals_map, attrs_map)
                    return f"{obj}[{key}]|{default}"  # get with default
                return f"{obj}[{key}]?"  # get without default
            
            # General method call
            args = [self._compress_value(a, locals_map, attrs_map) for a in node.args]
            if args:
                return f"{obj}.{method}({','.join(args)})"
            return f"{obj}.{method}()"
        elif isinstance(node.func, ast.Name):
            func = locals_map.get(node.func.id, node.func.id[:2])
            
            # Built-in shortcuts
            builtin_map = {
                'print': '@',
                'len': '#',
                'str': '$',
                'int': '%',
                'isinstance': '?',
            }
            if node.func.id in builtin_map:
                func = builtin_map[node.func.id]
            
            args = [self._compress_value(a, locals_map, attrs_map) for a in node.args]
            if func in '@#$%?':
                # Ultra-compact built-ins
                return f"{func}{','.join(args)}"
            return f"{func}({','.join(args)})"
        return "?()"

    def _compress_condition(self, node: ast.AST, locals_map: Dict[str, str],
                        attrs_map: Dict[str, str]) -> str:
        """Ultra-compact condition."""
        if isinstance(node, ast.Compare):
            left = self._compress_value(node.left, locals_map, attrs_map)
            
            if len(node.ops) == 1 and len(node.comparators) == 1:
                right = self._compress_value(node.comparators[0], locals_map, attrs_map)
                op = node.ops[0]
                
                # Ultra-compact operators
                if isinstance(op, ast.Is) and isinstance(node.comparators[0], ast.Constant) and node.comparators[0].value is None:
                    return f"{left}=N"  # is None
                elif isinstance(op, ast.IsNot) and isinstance(node.comparators[0], ast.Constant) and node.comparators[0].value is None:
                    return f"{left}!N"  # is not None
                elif isinstance(op, ast.Eq):
                    return f"{left}=={right}"
                elif isinstance(op, ast.NotEq):
                    return f"{left}!={right}"
                elif isinstance(op, ast.In):
                    return f"{left}in{right}"  # Use in 
                elif isinstance(op, ast.NotIn):
                    return f"{left}!in{right}"  # Use !in 
                elif isinstance(op, ast.Lt):
                    return f"{left}<{right}"
                elif isinstance(op, ast.LtE):
                    return f"{left}<={right}"
                elif isinstance(op, ast.Gt):
                    return f"{left}>{right}"
                elif isinstance(op, ast.GtE):
                    return f"{left}>={right}"

            return f"{left}?"
        
        elif isinstance(node, ast.BoolOp):
            # Handle boolean operations (and, or)
            if isinstance(node.op, ast.And):
                parts = [self._compress_condition(v, locals_map, attrs_map) for v in node.values]
                return f"({'&'.join(parts)})"
            elif isinstance(node.op, ast.Or):
                parts = [self._compress_condition(v, locals_map, attrs_map) for v in node.values]
                return f"({'|'.join(parts)})"
            return "?"
        
        # Fallback to general value compression
        return self._compress_value(node, locals_map, attrs_map)

    def _generate_ultra_dense_try_body(self, try_node: ast.Try, locals_map: Dict[str, str], attrs_map: Dict[str, str]) -> str:
        """Generate properly formatted ultra-dense try body."""
        body_parts = []
        
        for stmt in try_node.body:
            if isinstance(stmt, ast.For):
                # Special handling for for-loops in try blocks
                target = self._compress_target(stmt.target, locals_map, attrs_map)
                iter_val = self._compress_value(stmt.iter, locals_map, attrs_map)
                
                # Generate for-loop body parts
                loop_body_parts = []
                for loop_stmt in stmt.body:
                    loop_part = self._stmt_to_ultra_compact(loop_stmt, locals_map, attrs_map)
                    if loop_part:
                        loop_body_parts.append(loop_part)
                
                # CRITICAL: Ensure proper bracket structure
                # Format: @target,iter{body} NOT @target,iter{) = ...
                loop_body = ';'.join(loop_body_parts)
                body_parts.append(f"@{target},{iter_val}{{{loop_body}}}")
            else:
                # Regular statement handling
                compact_stmt = self._stmt_to_ultra_compact(stmt, locals_map, attrs_map)
                if compact_stmt:
                    body_parts.append(compact_stmt)
        
        return ';'.join(body_parts)

    def _parse_literal_chain_with_args(self, chain: str, args_part: str) -> ast.AST:
        """
        Parse a chain like 's.config.get' with args like '(arg1, arg2)' 
        without applying CID resolution to the chain components.
        This preserves literal attribute names for chain aliases.
        """
        # Parse the chain into attribute access
        chain_ast = self._parse_literal_attribute_chain(chain)
        
        # Parse arguments from the args_part
        if args_part.startswith('(') and args_part.endswith(')'):
            args_str = args_part[1:-1]  # Remove parentheses
            args = []
            
            if args_str.strip():
                # Split arguments carefully, respecting nested structures
                arg_strings = self._split_args(args_str)
                for arg_str in arg_strings:
                    arg_str = arg_str.strip()
                    if arg_str:
                        arg_ast = self._parse_expression_string(arg_str)
                        args.append(arg_ast)
            
            # Create function call
            call_node = ast.Call(func=chain_ast, args=args, keywords=[])
            return self._fix_ast_node_attributes(call_node)
        
        return chain_ast

    def _parse_literal_attribute_chain(self, chain: str) -> ast.AST:
        """
        Parse a chain like 's.config.get' into AST attribute access
        without applying name mapping to preserve literal chains.
        This is critical for chain aliases to work correctly.
        """
        parts = chain.split('.')
        
        # Handle the first part - expand common abbreviations
        first_part = parts[0]
        if first_part == 's':
            result = ast.Name(id='self', ctx=ast.Load())
        elif first_part == 'c':
            result = ast.Name(id='cls', ctx=ast.Load())
        else:
            result = ast.Name(id=first_part, ctx=ast.Load())
        
        # Build the attribute chain
        for part in parts[1:]:
            # DON'T apply name mapping here - keep literal attribute names
            result = ast.Attribute(value=result, attr=part, ctx=ast.Load())
        
        return self._fix_ast_node_attributes(result)

    def _parse_ultra_dense_try_except(self, stmt_str: str) -> ast.AST:
        """
        Parse T{body}X{handler} format with improved bracket matching and for-loop handling.
        """
        logger.debug(f"Parsing ultra-dense try-except: {stmt_str}")
        
        try:
            if not stmt_str.startswith('T{'):
                return self._fix_ast_node_attributes(ast.Pass())
            
            # Improved brace matching that handles nested for-loops
            brace_depth = 0
            try_body_end = -1
            in_for_loop = False
            
            i = 2  # Start after 'T{'
            while i < len(stmt_str):
                char = stmt_str[i]
                
                # Check for for-loop pattern @
                if char == '@' and i + 1 < len(stmt_str):
                    # This might be a for-loop
                    in_for_loop = True
                
                if char == '{':
                    brace_depth += 1
                elif char == '}':
                    if brace_depth == 0:
                        # This is the closing brace for the try block
                        try_body_end = i
                        break
                    brace_depth -= 1
                
                i += 1
            
            if try_body_end == -1:
                self.logger.warning("Could not find end of try body")
                return self._fix_ast_node_attributes(ast.Pass())
            
            # Extract and parse try body
            body_str = stmt_str[2:try_body_end]
            
            # Special handling for for-loops in try blocks
            if '@' in body_str and ',' in body_str and '{' in body_str:
                # This is a for-loop, parse it specially
                body_stmts = [self._parse_for_loop_statement(body_str)]
            else:
                body_stmts = self._parse_block_statements(body_str)
            
            # Check for except handler
            if try_body_end + 1 < len(stmt_str) and stmt_str[try_body_end + 1] == 'X':
                # Parse except handler
                handler_start = try_body_end + 1
                handler = self._parse_except_handler_safe(stmt_str[handler_start:])
                handlers = [handler] if handler else []
            else:
                handlers = []
            
            return self._fix_ast_node_attributes(
                ast.Try(body=body_stmts or [ast.Pass()], 
                       handlers=handlers, 
                       orelse=[], 
                       finalbody=[])
            )
            
        except Exception as e:
            self.logger.error(f"Error parsing try-except: {e}")
            return self._fix_ast_node_attributes(ast.Pass())

    def _parse_except_handler_safe(self, handler_str: str) -> ast.ExceptHandler:
        """
        Safely parse an except handler from X{...} format.
        
        Args:
            handler_str: Handler string starting with 'X'
            
        Returns:
            AST ExceptHandler node
        """
        logger.debug(f"Parsing except handler: {handler_str}")
        
        try:
            if not handler_str.startswith('X'):
                return None
            
            # Determine handler pattern: X{body} or X(exception_type){body}
            has_exc_type = (len(handler_str) > 1 and handler_str[1] == '(')
            
            if has_exc_type:
                # Pattern: X(exception_type){handler_body}
                handler_start = 2  # Skip X(
                # Find the closing ) for exception type
                paren_end = handler_str.find(')', handler_start)
                if paren_end == -1:
                    logger.warning("Malformed exception type specification")
                    return ast.ExceptHandler(type=None, name=None, body=[ast.Pass()])
                
                exc_type_str = handler_str[handler_start:paren_end]
                exc_type = ast.Name(id=exc_type_str, ctx=ast.Load()) if exc_type_str.strip() else None
                
                # Find handler body after ){
                brace_start = handler_str.find('{', paren_end)
                if brace_start == -1:
                    logger.warning("Missing { after exception type")
                    return ast.ExceptHandler(type=exc_type, name=None, body=[ast.Pass()])
                
                # Find the handler body end by tracking nested braces
                brace_depth = 0
                handler_body_end = -1
                
                for i, char in enumerate(handler_str[brace_start + 1:], brace_start + 1):
                    if char == '{':
                        brace_depth += 1
                    elif char == '}':
                        if brace_depth == 0:
                            handler_body_end = i
                            break
                        brace_depth -= 1
                
                if handler_body_end == -1:
                    handler_body_end = len(handler_str) - 1
                
                handler_body_str = handler_str[brace_start+1:handler_body_end]
                logger.debug(f"Exception type: {exc_type_str}, handler body: {handler_body_str}")
            else:
                # Pattern: X{handler_body}
                handler_start = 2  # Skip X{
                
                # Find the handler body end by tracking nested braces
                brace_depth = 0
                handler_body_end = -1
                
                for i, char in enumerate(handler_str[handler_start:], handler_start):
                    if char == '{':
                        brace_depth += 1
                    elif char == '}':
                        if brace_depth == 0:
                            handler_body_end = i
                            break
                        brace_depth -= 1
                
                if handler_body_end == -1:
                    handler_body_end = len(handler_str) - 1
                
                handler_body_str = handler_str[handler_start:handler_body_end]
                exc_type = None
                logger.debug(f"No exception type specified, handler body: {handler_body_str}")
            
            # Parse handler body statements
            handler_stmts = self._parse_block_statements(handler_body_str) if handler_body_str.strip() else [ast.Pass()]
            
            return ast.ExceptHandler(
                type=exc_type,
                name=None,
                body=handler_stmts or [ast.Pass()]
            )
            
        except Exception as e:
            logger.error(f"Error parsing except handler: {e}")
            return ast.ExceptHandler(type=None, name=None, body=[ast.Pass()])

    def _parse_block_statements(self, block_str: str) -> List[ast.AST]:
        """Parse semicolon-separated statements in a block with support for nested structures."""
        logger.debug(f"Parsing block statements: {block_str}")
        stmts = []
        
        # Split statements respecting nested structures
        stmt_parts = []
        current_stmt = ""
        brace_depth = 0
        paren_depth = 0
        
        i = 0
        while i < len(block_str):
            char = block_str[i]
            current_stmt += char
            
            if char == '{':
                brace_depth += 1
            elif char == '}':
                brace_depth -= 1
            elif char == '(':
                paren_depth += 1
            elif char == ')':
                paren_depth -= 1
            elif char == ';' and brace_depth == 0 and paren_depth == 0:
                # Found a statement separator at top level
                stmt_parts.append(current_stmt[:-1])  # Remove the semicolon
                current_stmt = ""
            i += 1
        
        # Add the last statement if any
        if current_stmt.strip():
            stmt_parts.append(current_stmt)
        
        for stmt_str in stmt_parts:
            stmt_str = stmt_str.strip()
            if stmt_str:
                logger.debug(f"Parsing statement: {stmt_str}")
                
                # Use safe parsing with fallback for each statement
                try:
                    # Parse each statement type with enhanced error handling
                    if stmt_str.startswith('@') and '{' in stmt_str:
                        # For-loop pattern like @key,s.v.items(){...}
                        stmt = self._parse_for_loop_statement(stmt_str)
                        logger.debug(f"Parsed as for-loop")
                    elif '=' in stmt_str and not any(op in stmt_str for op in ['==', '!=', '<=', '>=']):
                        stmt = self._parse_assignment(stmt_str)
                        logger.debug(f"Parsed as assignment")
                    elif stmt_str.startswith('R'):
                        stmt = self._parse_return(stmt_str)
                        logger.debug(f"Parsed as return")
                    elif stmt_str == '_':
                        stmt = ast.Pass()
                        logger.debug(f"Parsed as pass")
                    else:
                        # Try as expression with safe fallback
                        try:
                            expr = self._parse_expression_string(stmt_str)
                            stmt = ast.Expr(value=expr)
                            logger.debug(f"Parsed as expression")
                        except Exception as e:
                            logger.debug(f"Failed to parse as expression, using pass: {e}")
                            stmt = ast.Pass()
                    
                    # Fix AST attributes BEFORE validation
                    if stmt:
                        stmt = self._fix_ast_node_attributes(stmt)
                    
                    # Validate the parsed statement by checking if it can be converted to code
                    try:
                        import ast as ast_module
                        # Try to compile the statement to catch any subtle issues
                        module = ast_module.Module(body=[stmt], type_ignores=[])
                        compile(module, '<string>', 'exec')
                        logger.debug(f"Statement validation successful")
                    except Exception as validation_error:
                        logger.warning(f"Statement validation failed for '{stmt_str}': {validation_error}")
                        # Use Pass as safe fallback with proper attributes
                        stmt = self._fix_ast_node_attributes(ast.Pass())
                
                except Exception as parse_error:
                    logger.warning(f"Failed to parse statement '{stmt_str}': {parse_error}")
                    # Always fall back to Pass for unparseable statements with proper attributes
                    stmt = self._fix_ast_node_attributes(ast.Pass())
                
                # Ensure AST attributes are set (redundant safety check)
                if stmt and not hasattr(stmt, 'lineno'):
                    stmt = self._fix_ast_node_attributes(stmt)
                
                if stmt:
                    stmts.append(stmt)
        
        logger.debug(f"Parsed {len(stmts)} statements from block")
        return stmts

    def _parse_for_loop_statement(self, stmt_str: str) -> ast.AST:
        """Parse for-loop statement like @key,s.v.items(){...}"""
        logger.debug(f"Parsing for-loop statement: {stmt_str}")
        
        try:
            # Extract parts: @target,iterable{body}
            at_idx = stmt_str.index('@')
            comma_idx = stmt_str.index(',')
            brace_idx = stmt_str.index('{')
            close_brace_idx = stmt_str.rindex('}')
            
            target_str = stmt_str[at_idx+1:comma_idx].strip()
            iter_str = stmt_str[comma_idx+1:brace_idx].strip()
            body_str = stmt_str[brace_idx+1:close_brace_idx].strip()
            
            # Parse target
            target = self._parse_expression_string(target_str)
            if isinstance(target, ast.Name):
                target.ctx = ast.Store()
            
            # Parse iterable
            iter_expr = self._parse_expression_string(iter_str)
            
            # Parse body statements
            body_stmts = self._parse_block_statements(body_str) if body_str else [ast.Pass()]
            
            for_node = ast.For(target=target, iter=iter_expr, body=body_stmts, orelse=[])
            return self._fix_ast_node_attributes(for_node)
            
        except Exception as e:
            logger.debug(f"Error parsing for-loop statement: {e}")
            return self._fix_ast_node_attributes(ast.Pass())

    def _parse_flow_statement_safe(self, lines: List[str], indent_level: int) -> Tuple[Optional[ast.AST], int]:
        """Parse with deterministic fallback handling."""
        if not lines:
            return None, 0
        
        line = lines[0].strip()
        
        try:
            # Try standard parsing first
            result = self._parse_flow_statement(lines, indent_level)
            if result[0] is not None:
                return result
        except Exception as e:
            # Log with stable reference
            error_id = self._stable_hash(line, 6)
            logger.warning(f"Parse fail [{error_id}]: {line[:50]}...")
        
        # Deterministic fallback: preserve as comment
        comment_value = f"UNPARSED_{self._stable_hash(line, 6)}: {line}"
        return ast.Expr(value=ast.Constant(value=comment_value)), 1

    def _fix_operator_spacing(self, expr: str) -> str:
        """Normalize operators with proper spacing to avoid ambiguity."""
        import re
        
        # Critical: handle assignment vs comparison - order matters!
        # First normalize != to avoid issues with assignment regex
        expr = re.sub(r'!=', ' != ', expr)
        expr = re.sub(r'<=', ' <= ', expr)
        expr = re.sub(r'>=', ' >= ', expr)
        expr = re.sub(r'==', ' == ', expr)  # Comparison
        
        # Then handle assignment (but not comparison operators)
        expr = re.sub(r'(?<![!<>=])=(?!=)', ' = ', expr)  # Assignment
        
        # Handle 'in' and 'not in' carefully
        expr = re.sub(r'\s+not\s+in\s+', ' not in ', expr)
        expr = re.sub(r'(?<![a-zA-Z])in(?![a-zA-Z])', ' in ', expr)
        
        # Clean up multiple spaces
        expr = re.sub(r'\s+', ' ', expr).strip()
        
        return expr

    def _safe_parse_statement(self, stmt_str: str) -> ast.AST:
        """Safely parse a statement with fallback to Pass if parsing fails."""
        try:
            # Try normal parsing
            return self._parse_flow_statement([stmt_str], 0)[0]
        except Exception as e:
            self.logger.warning(f"Failed to parse statement '{stmt_str}': {e}")
            # Return a Pass statement as fallback
            return ast.Pass()

    def build_deterministic_local_map(self, func_node: ast.FunctionDef) -> Dict[str, str]:
        """Build deterministic local variable mappings based on AST order."""
        # Collect all local variables in order of first assignment
        locals_in_order = []
        
        class LocalCollector(ast.NodeVisitor):
            def visit_Name(self, node):
                if isinstance(node.ctx, ast.Store) and node.id not in ['self', 'cls']:
                    if node.id not in locals_in_order:
                        locals_in_order.append(node.id)
        
        LocalCollector().visit(func_node)
        
        # Generate names deterministically: a, b, c, ... aa, ab, ...
        name_gen = self._name_generator()
        local_map = {}
        
        for var in locals_in_order:
            compressed = next(name_gen)
            # Skip Python keywords and already used names
            while keyword.iskeyword(compressed) or compressed in self.PYTHON_KEYWORDS:
                compressed = next(name_gen)
            local_map[var] = compressed
        
        return local_map

    def _name_generator(self):
        """Generate names: a, b, c... z, aa, ab... az, ba..., skipping Python keywords."""
        chars = string.ascii_lowercase
        length = 1
        while True:
            for combo in itertools.product(chars, repeat=length):
                name = ''.join(combo)
                # Skip Python keywords and our custom keyword list
                if not keyword.iskeyword(name) and name not in self.PYTHON_KEYWORDS:
                    yield name
            length += 1

    def _fix_ast_node_attributes(self, node: ast.AST, lineno: int = 1, col_offset: int = 0) -> ast.AST:
        """Fix AST nodes by adding missing lineno and col_offset attributes."""
        for child in ast.walk(node):
            if not hasattr(child, 'lineno') or child.lineno is None:
                child.lineno = lineno
            if not hasattr(child, 'col_offset') or child.col_offset is None:
                child.col_offset = col_offset
        
        ast.fix_missing_locations(node)
        return node

    def _build_stable_pools(self, tree: ast.AST):
        """Pre-scan AST to build stable constant pools."""
        # Collect all string constants that meet pooling criteria
        string_constants = []
        
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                if len(node.value) >= self.pool_strings_min_len:
                    string_constants.append(node.value)
        
        # Sort for deterministic ordering
        unique_strings = sorted(set(string_constants))
        
        # Assign pool IDs deterministically
        for i, string_val in enumerate(unique_strings):
            if string_val not in self.constant_pool:
                self.constant_pool[string_val] = f"p{i}"

    def generate_flow_file(self, source_code: str) -> str:
        """Generate complete FLOW file with metadata."""
        import sys
        
        # Parse source
        tree = ast.parse(source_code)
        source_lines = source_code.split('\n')
        
        # Pre-scan for pools
        self._build_stable_pools(tree)
        
        # Convert with RAW fallback
        flow_parts = []
        for node in tree.body:
            flow = self.ast_to_flow(node, 0, source_lines)
            flow_parts.append(flow)
        
        # Build header
        header_parts = [
            f"#FLOW v2.0",
            f"#PY {sys.version_info.major}.{sys.version_info.minor}",
            f"#MODE {'strict' if self.strict_mode else 'normal'}"
        ]
        
        # Add pools if used
        if self.constant_pool:
            pools = ','.join(f"{pid}={repr(val)[:50]}" 
                            for val, pid in sorted(self.constant_pool.items(), 
                                                  key=lambda x: x[1]))
            header_parts.append(f"P:{pools}")
        
        # Add RAW block registry if used
        if self.raw_blocks:
            header_parts.append(f"#RAW_BLOCKS {len(self.raw_blocks)}")
            for raw_id, info in sorted(self.raw_blocks.items()):
                header_parts.append(f"#RAW {raw_id}:{info['node_type']}:{len(info['data'])}")
        
        # Add unsupported node warning
        if self.unsupported_nodes:
            header_parts.append(f"#UNSUPPORTED {','.join(sorted(self.unsupported_nodes))}")
        
        # Combine
        header = '\n'.join(header_parts)
        body = '\n'.join(flow_parts)
        
        # Add RAW data section at end
        raw_section = ""
        if self.raw_blocks:
            raw_section = "\n#RAW_DATA\n"
            for raw_id, info in sorted(self.raw_blocks.items()):
                raw_section += f"{raw_id}={info['data']}\n"
        
        return f"{header}\n\n{body}{raw_section}"

    def parse_flow_file(self, flow_content: str) -> str:
        """Parse FLOW file back to Python source code."""
        lines = flow_content.split('\n')
        
        # Parse header and extract metadata
        header_end = 0
        pools = {}
        raw_blocks = {}
        
        for i, line in enumerate(lines):
            if line.startswith('#'):
                if line.startswith('P:'):
                    # Parse pool definitions
                    pool_data = line[2:]
                    for item in pool_data.split(','):
                        if '=' in item:
                            pid, val = item.split('=', 1)
                            # Safely parse string literals without eval()
                            if val.startswith("'") and val.endswith("'"):
                                pools[pid] = val[1:-1]  # Remove quotes
                            elif val.startswith('"') and val.endswith('"'):
                                pools[pid] = val[1:-1]  # Remove quotes
                            else:
                                # Try to parse as literal
                                try:
                                    pools[pid] = ast.literal_eval(val)
                                except:
                                    pools[pid] = val  # Fallback to raw string
                elif line.startswith('#RAW_DATA'):
                    # RAW data section starts after this
                    break
            elif line.strip() == '':
                continue
            else:
                header_end = i
                break
        
        # Parse RAW data section if present
        raw_data_start = -1
        for i, line in enumerate(lines):
            if line.startswith('#RAW_DATA'):
                raw_data_start = i + 1
                break
        
        if raw_data_start > 0:
            for i in range(raw_data_start, len(lines)):
                line = lines[i].strip()
                if '=' in line:
                    raw_id, data = line.split('=', 1)
                    # Parse the RAW block info properly
                    self.raw_blocks[raw_id] = {
                        'type': 'ast',  # Assume AST type for now
                        'data': data,
                        'node_type': 'Unknown'
                    }
        
        # Set up compiler state
        self.set_pools(pools)
        # RAW blocks are already set up above
        
        # Parse body
        body_lines = []
        if raw_data_start > 0:
            body_lines = lines[header_end:raw_data_start]
        else:
            body_lines = lines[header_end:]
        
        # Remove empty lines and comments
        body_lines = [line for line in body_lines if line.strip() and not line.startswith('#')]
        
        # Parse statements using the new lexer and parser system
        body_content = '\n'.join(body_lines)
        statements = self._parse_ultra_dense_body(body_content)
        
        # Convert back to Python source
        module = ast.Module(body=statements, type_ignores=[])
        module = self._fix_ast_node_attributes(module)
        
        try:
            import astor
            return astor.to_source(module)
        except ImportError:
            # Fallback if astor is not available - use the global ast module
            import sys
            ast_module = sys.modules['ast']
            return ast_module.unparse(module) if hasattr(ast_module, 'unparse') else str(module)

    def _fix_ast_node_attributes(self, node: ast.AST) -> ast.AST:
        """Add missing AST attributes required for compilation."""
        if not hasattr(node, 'lineno'):
            node.lineno = 1
        if not hasattr(node, 'col_offset'):
            node.col_offset = 0
        
        # Recursively fix all child nodes
        for child in ast.iter_child_nodes(node):
            self._fix_ast_node_attributes(child)
        
        return node

    def _parse_ultra_dense_body(self, body_content: str) -> List[ast.AST]:
        """Parse ultra-dense body using tokenizer"""
        from .flow_tokenizer import FLOWLexer
        from .flow_parser import FLOWParser
        
        # Tokenize
        lexer = FLOWLexer(body_content)
        tokens = lexer.tokenize()
        
        # Parse with pools and chains
        parser = FLOWParser(
            tokens=tokens,
            pools=self.pools if hasattr(self, 'pools') else {},
            chains=self.chain_aliases if hasattr(self, 'chain_aliases') else {}
        )
        
        try:
            statements = parser.parse_statements()
            return statements
        except SyntaxError as e:
            logger.error(f"Parse error: {e}")
            return [ast.Pass()]

    def flow_to_python(self, flow_code: str) -> str:
        """Convert FLOW to Python using proper parser with black formatting"""
        from .flow_tokenizer import FLOWLexer
        from .flow_parser import FLOWParser
        
        # Parse the entire flow code as a single unit for better multiline handling
        lexer = FLOWLexer(flow_code)
        tokens = lexer.tokenize()
        
        parser = FLOWParser(
            tokens, 
            self.pools if hasattr(self, 'pools') else {}, 
            self.chain_aliases if hasattr(self, 'chain_aliases') else {}
        )
        statements = parser.parse_statements()
        
        # Convert to Python
        python_lines = []
        for stmt in statements:
            python_code = ast.unparse(stmt)
            python_lines.append(python_code)
        
        python_code = '\n'.join(python_lines)
        
        # Use black for formatting if available
        try:
            import black
            # Configure black mode for consistent formatting
            mode = black.FileMode(
                target_versions={black.TargetVersion.PY39},
                line_length=88,
                string_normalization=True,
                is_pyi=False,
            )
            formatted_code = black.format_str(python_code, mode=mode)
            return formatted_code.strip()
        except ImportError:
            # Fall back to basic formatting if black is not available
            return python_code
        except Exception as e:
            # If black formatting fails, return unformatted code
            logger.warning(f"Black formatting failed: {e}")
            return python_code


class NodeSupportValidator:
    """Check which nodes we can handle vs need RAW fallback."""
    
    FULLY_SUPPORTED = {
        # Statements
        'Module', 'FunctionDef', 'Assign', 'AugAssign', 'Return', 'If', 'For',
        'While', 'Try', 'ExceptHandler', 'With', 'Break', 'Continue',
        'Pass', 'Delete', 'Raise', 'Expr',
        
        # Expressions  
        'BinOp', 'UnaryOp', 'Compare', 'BoolOp', 'Call', 'Attribute',
        'Subscript', 'Name', 'Constant', 'List', 'Dict', 'Tuple',
        'IfExp', 'FormattedValue',
        
        # Function components
        'arguments', 'arg',
        
        # Operators
        'Add', 'Sub', 'Mult', 'Div', 'Mod', 'Pow', 'FloorDiv',
        'And', 'Or', 'Not', 'Eq', 'NotEq', 'Lt', 'LtE', 'Gt', 'GtE',
        'Is', 'IsNot', 'In', 'NotIn',
        
        # Contexts
        'Load', 'Store', 'Del'
    }
    
    PARTIAL_SUPPORT = {
        'JoinedStr': 'Basic f-strings only',
        'FormattedValue': 'Simple format specs',
        'Slice': 'Basic slicing'
    }
    
    NEEDS_RAW = {
        # These always use RAW fallback
        'ClassDef', 'Import', 'ImportFrom', 'Global', 'Nonlocal',
        'Lambda', 'ListComp', 'SetComp', 'DictComp', 'GeneratorExp',
        'Yield', 'YieldFrom', 'Await', 'AsyncFunctionDef', 'AsyncFor',
        'AsyncWith', 'Match', 'match_case', 'NamedExpr', 'AnnAssign',
        'Assert', 'Starred', 'Decorator'
    }
    
    @classmethod
    def needs_raw_fallback(cls, node: ast.AST) -> bool:
        """Check if node requires RAW fallback."""
        node_type = type(node).__name__
        
        if node_type in cls.NEEDS_RAW:
            return True
        
        # Special case: FunctionDef with decorators needs RAW fallback
        if node_type == 'FunctionDef' and hasattr(node, 'decorator_list') and node.decorator_list:
            return True
        
        if node_type in cls.PARTIAL_SUPPORT:
            # Check specific conditions for partial support nodes
            if node_type == 'JoinedStr' and len(node.values) > 5:
                return True  # Complex f-string
            if node_type == 'Slice' and node.step is not None:
                return True  # Advanced slicing
            # If partial support node passes conditions, treat as supported
            return False
        
        return node_type not in cls.FULLY_SUPPORTED
    
    @classmethod
    def is_control_structure(cls, node: ast.AST) -> bool:
        """Check if node is a control structure that shouldn't be inlined."""
        return isinstance(node, (ast.If, ast.For, ast.While, ast.Try, ast.With))
    
    @classmethod
    def get_support_level(cls, node: ast.AST) -> str:
        """Get the support level for a node."""
        node_type = type(node).__name__
        
        if node_type in cls.FULLY_SUPPORTED:
            return 'full'
        elif node_type in cls.PARTIAL_SUPPORT:
            return 'partial'
        elif node_type in cls.NEEDS_RAW:
            return 'raw'
        else:
            return 'unknown'
    
    @classmethod
    def get_unsupported_reason(cls, node: ast.AST) -> str:
        """Get the reason why a node is not supported."""
        node_type = type(node).__name__
        
        if node_type in cls.NEEDS_RAW:
            return f"{node_type} requires RAW fallback due to complexity"
        elif node_type in cls.PARTIAL_SUPPORT:
            reason = cls.PARTIAL_SUPPORT[node_type]
            if node_type == 'JoinedStr' and len(node.values) > 5:
                return f"Complex f-string with {len(node.values)} values (limit: 5)"
            elif node_type == 'Slice' and node.step is not None:
                return "Advanced slicing with step parameter"
            return f"Partial support: {reason}"
        elif node_type not in cls.FULLY_SUPPORTED:
            return f"Unknown node type: {node_type}"
        else:
            return "Node is fully supported"
    
    @classmethod
    def analyze_ast_tree(cls, tree: ast.AST) -> Dict[str, int]:
        """Analyze an entire AST tree and return node type counts."""
        counts = {'full': 0, 'partial': 0, 'raw': 0, 'unknown': 0}
        
        for node in ast.walk(tree):
            support_level = cls.get_support_level(node)
            counts[support_level] += 1
        
        return counts