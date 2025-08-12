# optimize_ai/input_optimizer/engine/flow_language.py
"""
FLOW language compiler for CAI3-LITE with ultra-dense syntax.
Achieves 60-70% token reduction through single-char macros and compressed syntax.
"""

import ast
from typing import Any, Dict, List, Optional, Union, Set, Tuple
import re

class FLOWCompiler:
    """Converts Python AST to dense FLOW representation and back"""
    
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
    
    def __init__(self, name_map: Optional[Dict[str, str]] = None, 
                 dense_mode: bool = True,
                 pool_constants: bool = True,
                 ascii_ops: bool = True,
                 no_spaces: bool = True,
                 inline_blocks: bool = True,
                 alias_chains: bool = True,
                 pool_strings_min_len: int = 3):
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
        """
        self.name_map = name_map or {}
        self.reverse_map = {v: k for k, v in self.name_map.items()}
        self.dense_mode = dense_mode
        self.pool_constants = pool_constants
        self.constant_pool = {}  # value -> pool_id
        self.pool_counter = 0
        
        # New feature flags
        self.ascii_ops = ascii_ops
        self.no_spaces = no_spaces
        self.inline_blocks = inline_blocks
        self.alias_chains = alias_chains
        self.pool_strings_min_len = pool_strings_min_len
        
        # Track local variable compressions per scope
        self.local_compressions = {}
        self.current_scope_id = None
        
        # Alias chain tracking for D: dictionary
        self.alias_chains_dict = {}  # full_chain -> alias
    
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
            if isinstance(stmt, (ast.If, ast.For, ast.While, ast.Try, ast.With)):
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
    
    def ast_to_flow(self, node: ast.AST, indent: int = 0) -> str:
        """Convert Python AST to dense FLOW representation"""
        # Use minimal indentation in dense mode (single space per level)
        indent_str = ' ' * indent if self.dense_mode else '  ' * indent
        
        if isinstance(node, ast.FunctionDef):
            # Function body processing
            body_flows = []
            for stmt in node.body:
                if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Str):
                    continue  # Skip docstrings
                flow = self.ast_to_flow(stmt, indent)
                if flow:
                    body_flows.append(flow)
            return '\n'.join(body_flows)
        
        elif isinstance(node, ast.Assign):
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
        
        elif isinstance(node, ast.AugAssign):
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
        
        elif isinstance(node, ast.Return):
            # R val or just R, no space after macro in dense mode
            macro = 'R' if self.dense_mode else 'RET'
            if node.value:
                value = self._process_value(node.value)
                if self.dense_mode:
                    return f"{indent_str}{macro}{value}"  # No space after macro
                else:
                    return f"{indent_str}{macro} {value}"
            return f"{indent_str}{macro}"
        
        elif isinstance(node, ast.If):
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
                    flow = self.ast_to_flow(stmt, indent + 1)
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
                            flow = self.ast_to_flow(stmt, indent + 1)
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
                            lines.append(f"{indent_str}{macro_else}:")
                            for stmt in elif_node.orelse:
                                flow = self.ast_to_flow(stmt, indent + 1)
                                if flow:
                                    lines.append(flow)
                else:
                    # else
                    macro_else = 'O' if self.dense_mode else 'ELSE'
                    if self._can_inline_block(node.orelse):
                        else_inline_body = self._inline_statements(node.orelse)
                        if self.dense_mode:
                            lines.append(f"{indent_str}{macro_else}:{{{else_inline_body}}}")
                        else:
                            lines.append(f"{indent_str}{macro_else}: {{{else_inline_body}}}")
                    else:
                        lines.append(f"{indent_str}{macro_else}:")
                        for stmt in node.orelse:
                            flow = self.ast_to_flow(stmt, indent + 1)
                            if flow:
                                lines.append(flow)
            
            return '\n'.join(lines)
        
        elif isinstance(node, ast.For):
            # Dense for: Fxiniter:{body} or Fxiniter:body for inline vs multiline
            lines = []
            target = self._process_target(node.target)
            iter_val = self._process_value(node.iter)
            macro = 'F' if self.dense_mode else 'FOR'
            
            # Check if we can inline the for body
            if self._can_inline_block(node.body):
                inline_body = self._inline_statements(node.body)
                if self.dense_mode:
                    if self.no_spaces:
                        lines.append(f"{indent_str}{macro}{target}in{iter_val}:{{{inline_body}}}")  # No spaces
                    else:
                        lines.append(f"{indent_str}{macro} {target} in {iter_val}: {{{inline_body}}}")
                else:
                    lines.append(f"{indent_str}{macro} {target} in {iter_val}: {{{inline_body}}}")
            else:
                # Traditional multiline format
                if self.dense_mode:
                    if self.no_spaces:
                        lines.append(f"{indent_str}{macro}{target}in{iter_val}:")  # No spaces
                    else:
                        lines.append(f"{indent_str}{macro} {target} in {iter_val}:")
                else:
                    lines.append(f"{indent_str}{macro} {target} in {iter_val}:")
                
                for stmt in node.body:
                    flow = self.ast_to_flow(stmt, indent + 1)
                    if flow:
                        lines.append(flow)
            
            return '\n'.join(lines)
        
        elif isinstance(node, ast.While):
            # Dense while: W(cond):body
            lines = []
            condition = self._process_condition(node.test)
            macro = 'W' if self.dense_mode else 'WHILE'
            
            if self.dense_mode:
                lines.append(f"{indent_str}{macro}({condition}):")
            else:
                lines.append(f"{indent_str}{macro} {condition}:")
            
            for stmt in node.body:
                flow = self.ast_to_flow(stmt, indent + 1)
                if flow:
                    lines.append(flow)
            
            return '\n'.join(lines)
        
        elif isinstance(node, ast.Try):
            # Dense try: T:{body}X(E):{handler} or T:body X(E):handler
            lines = []
            macro_try = 'T' if self.dense_mode else 'TRY'
            macro_except = 'X' if self.dense_mode else 'CATCH'
            
            # Check if we can inline the try body
            if self._can_inline_block(node.body):
                try_inline_body = self._inline_statements(node.body)
                lines.append(f"{indent_str}{macro_try}:{{{try_inline_body}}}")
            else:
                lines.append(f"{indent_str}{macro_try}:")
                for stmt in node.body:
                    flow = self.ast_to_flow(stmt, indent + 1)
                    if flow:
                        lines.append(flow)
            
            for handler in node.handlers:
                exc_type = handler.type.id if handler.type and hasattr(handler.type, 'id') else 'E'
                exc_name = handler.name if handler.name else '_'
                
                if handler.type and isinstance(handler.type, ast.Tuple):
                    exc_types = [self._get_name(e) for e in handler.type.elts]
                    exc_type = f"({','.join(exc_types)})"
                
                # Check if we can inline the handler body
                if self._can_inline_block(handler.body):
                    handler_inline_body = self._inline_statements(handler.body)
                    if self.dense_mode:
                        # Ultra-compact: X(E):{body} for except Exception as _
                        if exc_name == '_':
                            lines.append(f"{indent_str}{macro_except}({exc_type}):{{{handler_inline_body}}}")
                        else:
                            lines.append(f"{indent_str}{macro_except}({exc_type}){exc_name}:{{{handler_inline_body}}}")
                    else:
                        lines.append(f"{indent_str}{macro_except} {exc_type} as {exc_name}: {{{handler_inline_body}}}")
                else:
                    if self.dense_mode:
                        # Ultra-compact: X(E)_ for except Exception as _
                        if exc_name == '_':
                            lines.append(f"{indent_str}{macro_except}({exc_type}):")
                        else:
                            lines.append(f"{indent_str}{macro_except}({exc_type}){exc_name}:")
                    else:
                        lines.append(f"{indent_str}{macro_except} {exc_type} as {exc_name}:")
                    
                    for stmt in handler.body:
                        flow = self.ast_to_flow(stmt, indent + 1)
                        if flow:
                            lines.append(flow)
            
            return '\n'.join(lines)
        
        elif isinstance(node, ast.Expr):
            # Expression statement
            if isinstance(node.value, ast.Call):
                call_str = self._process_call(node.value)
                return f"{indent_str}{call_str}"
            else:
                value = self._process_value(node.value)
                return f"{indent_str}{value}"
        
        elif isinstance(node, ast.Break):
            return f"{indent_str}{'B' if self.dense_mode else 'BREAK'}"
        
        elif isinstance(node, ast.Continue):
            return f"{indent_str}{'K' if self.dense_mode else 'CONTINUE'}"
        
        elif isinstance(node, ast.Pass):
            return f"{indent_str}{'_' if self.dense_mode else 'PASS'}"
        
        elif isinstance(node, ast.Raise):
            macro = 'R!' if self.dense_mode else 'RAISE'
            if node.exc:
                exc = self._process_value(node.exc)
                if self.dense_mode:
                    return f"{indent_str}{macro}{exc}"  # No space after macro
                else:
                    return f"{indent_str}{macro} {exc}"
            return f"{indent_str}{macro}"
        
        elif isinstance(node, ast.Delete):
            macro = 'D' if self.dense_mode else 'DEL'
            targets = [self._process_target(t) for t in node.targets]
            if self.dense_mode:
                return f"{indent_str}{macro}{','.join(targets)}"  # No space after macro
            else:
                return f"{indent_str}{macro} {','.join(targets)}"
        
        return ""
    
    def _process_target(self, node: ast.AST) -> str:
        """Process assignment target with compression"""
        if isinstance(node, ast.Name):
            name = node.id
            # Check local compressions first - if scope exists and name is in local map, use it
            if self.current_scope_id and name in self.local_compressions.get(self.current_scope_id, {}):
                return self.local_compressions[self.current_scope_id][name]
            # If local scope exists but name not in local map, trust minified names (no double-compress)
            elif self.current_scope_id and self.current_scope_id in self.local_compressions:
                return name  # Trust the already minified name, don't apply global compression
            # Only apply global compressions when no local scope is present
            return self.name_map.get(name, name)
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
        elif isinstance(node, ast.Subscript):
            obj = self._process_value(node.value)
            index = self._process_value(node.slice)
            return f"{obj}[{index}]"
        elif isinstance(node, ast.Tuple):
            targets = [self._process_target(t) for t in node.elts]
            # Compact tuple notation
            if self.dense_mode:
                return f"({','.join(targets)})"
            return f"({', '.join(targets)})"
        return "?"
    
    def _process_value(self, node: ast.AST) -> str:
        """Process value with compression and pooling"""
        if node is None:
            return "N" if self.dense_mode else "None"
        elif isinstance(node, ast.Name):
            name = node.id
            # Compress common builtins in dense mode
            if self.dense_mode:
                builtin_map = {
                    'True': 'T',
                    'False': 'F', 
                    'None': 'N',
                    'self': 's',
                    'cls': 'c',
                }
                if name in builtin_map:
                    return builtin_map[name]
            
            # Check local compressions - if scope exists and name is in local map, use it
            if self.current_scope_id and name in self.local_compressions.get(self.current_scope_id, {}):
                return self.local_compressions[self.current_scope_id][name]
            # If local scope exists but name not in local map, trust minified names (no double-compress)
            elif self.current_scope_id and self.current_scope_id in self.local_compressions:
                return name  # Trust the already minified name, don't apply global compression
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
                # Use single quotes for compactness
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
        Parse a single FLOW statement.
        
        Returns:
            Tuple of (parsed_statement, lines_consumed)
        """
        if not lines:
            return None, 0
        
        line = lines[0].strip()
        
        # Handle inline blocks first
        if '{' in line and '}' in line:
            return self._parse_inline_statement(line), 1
        
        # Parse based on macro
        if line.startswith('L') or (len(line) > 1 and line[1:2] and line[0] in 'LCFIEOTXYRBK_WZD@+S-'):
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
                return ast.Break(), 1
            elif macro == 'K':
                return ast.Continue(), 1
            elif macro == '_':
                return ast.Pass(), 1
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
        
        # Add handling for compressed for loop: @f,r{...}
        elif line.startswith('@') and ',' in line and '{' in line:
            # Handle compressed for loop: @variable,iterable{body}
            # Extract parts: @variable,iterable{body}
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
                    stmt, _ = self._parse_flow_statement([stmt_str.strip()], 0)
                    if stmt:
                        body_stmts.append(stmt)
            
            return ast.For(target=target, iter=iter_expr, body=body_stmts or [ast.Pass()], orelse=[]), 1
        
        # Check for assignment without L prefix (e.g., "r=g1(...)")
        if '=' in line and not any(op in line for op in ['==', '!=', '<=', '>=']):
            # This is likely an assignment without L prefix
            return self._parse_assignment(line), 1
        
        # If we can't parse it, treat as expression
        try:
            return self._parse_expression(line), 1
        except:
            # Fallback: create a pass statement
            return ast.Pass(), 1
    
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
                condition = self._parse_condition_string(condition_str)
                
                # Parse inline body (semicolon separated)
                body_stmts = []
                for stmt_str in inline_body.split(';'):
                    stmt_str = stmt_str.strip()
                    if stmt_str:
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
                # Inline try: T:{body}
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
    
    def _parse_assignment(self, line: str) -> ast.AST:
        """Parse assignment: Lx=value or x=value"""
        # Remove L prefix if present
        if line.startswith('L'):
            assign_str = line[1:]
        else:
            assign_str = line
        
        if '=' in assign_str:
            target_str, value_str = assign_str.split('=', 1)
            target_name = target_str.strip()
            
            # Apply name mapping for target
            if target_name in self.reverse_map:
                target_name = self.reverse_map[target_name]
            elif target_name in self.name_map:
                target_name = self.name_map[target_name]
            
            target = ast.Name(id=target_name, ctx=ast.Store())
            value = self._parse_expression_string(value_str.strip())
            return ast.Assign(targets=[target], value=value)
        
        return ast.Pass()
    
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
                return ast.For(target=target, iter=iter_expr, body=body_stmts or [ast.Pass()], orelse=[]), consumed + 1
        
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
                    elif_stmt, elif_consumed = self._parse_if_statement(lines[current_line_idx:], indent_level)
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
        """Parse try statement: T: or T:{inline}"""
        line = lines[0].strip()
        
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
            
            # Parse exception name
            exc_name = rest.rstrip(':').strip() if rest.rstrip(':').strip() != '_' else None
            
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
    
    def _parse_return(self, line: str) -> ast.AST:
        """Parse return statement: Rvalue or R"""
        if len(line) > 1:
            value_str = line[1:]
            value = self._parse_expression_string(value_str)
            return ast.Return(value=value)
        else:
            return ast.Return(value=None)
    
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
            return ast.Assign(targets=[target], value=value)
        return ast.Pass()
    
    def _parse_decrement(self, line: str) -> ast.AST:
        """Parse decrement: -target"""
        if len(line) > 1:
            target_str = line[1:]
            target = ast.Name(id=target_str, ctx=ast.Store())
            value = ast.BinOp(left=ast.Name(id=target_str, ctx=ast.Load()), op=ast.Sub(), right=ast.Constant(value=1))
            return ast.Assign(targets=[target], value=value)
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
                    return ast.Assign(targets=[target], value=value)
            
            # Regular assignment
            target = ast.Name(id=target_str.strip(), ctx=ast.Store())
            value = self._parse_expression_string(value_str.strip())
            return ast.Assign(targets=[target], value=value)
        
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
    
    def _parse_condition_string(self, condition_str: str) -> ast.AST:
        """Parse a condition string with ASCII operators"""
        # Handle special dense conditions
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
            if exclamation_idx > 0 and condition_str[exclamation_idx:exclamation_idx+3] == '!in':
                # Split at the exclamation mark
                left_str = condition_str[:exclamation_idx]
                right_str = condition_str[exclamation_idx+3:]  # Skip "!in"
                left = self._parse_expression_string(left_str.strip())
                right = self._parse_expression_string(right_str.strip())
                return ast.Compare(left=left, ops=[ast.NotIn()], comparators=[right])
        
        # Handle binary operators with ASCII - order matters!
        for op_text, op_class in [
            ('!=', ast.NotEq),
            ('==', ast.Eq),
            ('<=', ast.LtE),
            ('>=', ast.GtE),
            ('!in', ast.NotIn),  # This should come after the compressed pattern above
            ('in', ast.In),
            ('<', ast.Lt),
            ('>', ast.Gt),
        ]:
            if op_text in condition_str:
                left_str, right_str = condition_str.split(op_text, 1)
                left = self._parse_expression_string(left_str.strip())
                right = self._parse_expression_string(right_str.strip())
                return ast.Compare(left=left, ops=[op_class()], comparators=[right])
        
        # Fallback: parse as expression
        return self._parse_expression_string(condition_str)
    
    def _parse_expression_string(self, expr_str: str) -> ast.AST:
        """Parse an expression string, handling dense notation"""
        expr_str = expr_str.strip()
        
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
                    # Handle the special case where chain already includes parentheses
                    if chain.endswith('()'):
                        chain = chain[:-2]  # Remove the () from the chain
                    return self._parse_expression_string(chain + args_part)
            else:
                # Non-function alias
                alias_id = expr_str
                if hasattr(self, 'chain_aliases') and alias_id in self.chain_aliases:
                    chain = self.chain_aliases[alias_id]
                    return self._parse_expression_string(chain)
            
            # Fallback to existing logic for backward compatibility
            if expr_str[1:].isdigit():
                alias_id = expr_str
                if alias_id in self.alias_chains_dict:
                    chain = self.alias_chains_dict[alias_id]
                    return self._parse_expression_string(chain)
                return ast.Name(id=f"ALIAS_{alias_id}", ctx=ast.Load())
        
        # Handle method calls with arguments: obj.method(args)
        if '(' in expr_str and ')' in expr_str:
            return self._parse_call_with_args(expr_str)
        
        # Handle attribute access: obj.attr
        if '.' in expr_str and not self._is_number(expr_str):
            return self._parse_attribute_access(expr_str)
        
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
        
        # Handle function calls
        if expr_str.startswith('C(') and expr_str.endswith(')'):
            return self._parse_call_expression(expr_str)
        
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
        
        # Handle binary operations
        for op_char, op_class in [
            ('==', ast.Eq), ('!=', ast.NotEq), ('<=', ast.LtE), ('>=', ast.GtE),
            ('<', ast.Lt), ('>', ast.Gt), ('!in', ast.NotIn), ('in', ast.In),
            ('+', ast.Add), ('-', ast.Sub), ('*', ast.Mult), ('/', ast.Div),
        ]:
            if op_char in expr_str:
                parts = expr_str.split(op_char, 1)
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
        
        # Apply name mapping if available
        if expr_str in self.reverse_map:
            expr_str = self.reverse_map[expr_str]
        elif expr_str in self.name_map:
            expr_str = self.name_map[expr_str]
        
        # Default: treat as variable name
        return ast.Name(id=expr_str, ctx=ast.Load())
    
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
        args_part = expr_str[paren_idx+1:-1]  # Remove ( and )
        
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
        
        return ast.Call(func=func_ast, args=args, keywords=[])
    
    def _parse_attribute_access(self, expr_str: str) -> ast.AST:
        """Parse attribute access: obj.attr or s.c.ge"""
        parts = expr_str.split('.')
        
        # Start with the first part
        result = self._parse_simple_name(parts[0])
        
        # Build the attribute chain
        for attr in parts[1:]:
            # Expand compressed attribute names
            attr = self._expand_compressed_name(attr)
            result = ast.Attribute(value=result, attr=attr, ctx=ast.Load())
        
        return result
    
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
            body_parts = [self._stmt_to_ultra_compact(s, locals_map, attrs_map) for s in stmt.body]
            body = ';'.join(filter(None, body_parts))
            
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
        """Compress value with aggressive abbreviation."""
        if node is None:
            return "N"
        elif isinstance(node, ast.Constant):
            if node.value is True:
                return "T"
            elif node.value is False:
                return "F"
            elif node.value is None:
                return "N"
            elif isinstance(node.value, str):
                # Check for pool reference
                pool_id = self._get_pool_id(node.value)
                if pool_id:
                    return pool_id
                # Short strings inline, quoted
                if len(node.value) <= 3:
                    return f"'{node.value}'"
                # Hash longer strings for ultra-compression
                return f"#{hash(node.value) % 1000:03d}"
            return str(node.value)
        elif isinstance(node, ast.Name):
            if node.id == 'self':
                return 's'
            elif node.id == 'True':
                return 'T'
            elif node.id == 'False':
                return 'F'
            elif node.id == 'None':
                return 'N'
            return locals_map.get(node.id, node.id[:1] if len(node.id) > 2 else node.id)
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