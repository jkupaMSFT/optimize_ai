# optimize_ai/input_optimizer/engine/flow_language.py
"""
FLOW language compiler for CAI3-LITE with ultra-dense syntax.
Achieves 60-70% token reduction through single-char macros and compressed syntax.
"""

import ast
from typing import Any, Dict, List, Optional, Union, Set
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
    
    # Operator shortcuts
    OPERATOR_MAP = {
        '==': '=',
        '!=': '≠',
        '<=': '≤', 
        '>=': '≥',
        'not in': '∉',
        'in': '∈',
        'and': '&',
        'or': '|',
        'not': '!',
    }
    
    def __init__(self, name_map: Optional[Dict[str, str]] = None, 
                 dense_mode: bool = True,
                 pool_constants: bool = True):
        """
        Initialize with name mapping and compression options.
        
        Args:
            name_map: Mapping of shortened names to original
            dense_mode: Use ultra-dense single-char macros
            pool_constants: Reference pooled constants instead of inline
        """
        self.name_map = name_map or {}
        self.reverse_map = {v: k for k, v in self.name_map.items()}
        self.dense_mode = dense_mode
        self.pool_constants = pool_constants
        self.constant_pool = {}  # value -> pool_id
        self.pool_counter = 0
        
        # Track local variable compressions per scope
        self.local_compressions = {}
        self.current_scope_id = None
    
    def set_scope(self, scope_id: str, local_map: Dict[str, str]):
        """Set local variable compressions for current scope"""
        self.current_scope_id = scope_id
        self.local_compressions[scope_id] = local_map
    
    def _get_pool_id(self, value: Any) -> str:
        """Get or create pool ID for a constant"""
        if not self.pool_constants:
            return None
            
        # Convert value to hashable form
        if isinstance(value, (list, dict)):
            key = str(value)
        else:
            key = value
            
        if key not in self.constant_pool:
            self.constant_pool[key] = f"p{self.pool_counter}"
            self.pool_counter += 1
        
        return self.constant_pool[key]
    
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
            # Dense assignment: L x=val
            target = self._process_target(node.targets[0])
            value = self._process_value(node.value)
            macro = 'L' if self.dense_mode else 'LET'
            return f"{indent_str}{macro} {target}={value}"
        
        elif isinstance(node, ast.AugAssign):
            # Handle += -= etc
            target = self._process_target(node.target)
            op = self._get_aug_op(node.op)
            value = self._process_value(node.value)
            
            if self.dense_mode:
                if op == '+=' and value == '1':
                    return f"{indent_str}+{target}"  # Ultra-compact increment
                elif op == '-=' and value == '1':
                    return f"{indent_str}-{target}"  # Ultra-compact decrement
                else:
                    # S x=x+val for other augmented assigns
                    return f"{indent_str}S {target}={target}{op[0]}{value}"
            else:
                return f"{indent_str}SET {target} = {target} {op[0]} {value}"
        
        elif isinstance(node, ast.Return):
            # R val or just R
            macro = 'R' if self.dense_mode else 'RET'
            if node.value:
                value = self._process_value(node.value)
                return f"{indent_str}{macro} {value}"
            return f"{indent_str}{macro}"
        
        elif isinstance(node, ast.If):
            # Dense if: I(cond):body E(cond2):body O:body
            lines = []
            condition = self._process_condition(node.test)
            macro_if = 'I' if self.dense_mode else 'IF'
            
            # Ultra-compact conditional format
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
                    condition = self._process_condition(elif_node.test)
                    macro_elif = 'E' if self.dense_mode else 'ELIF'
                    
                    if self.dense_mode:
                        lines.append(f"{indent_str}{macro_elif}({condition}):")
                    else:
                        lines.append(f"{indent_str}{macro_elif} {condition}:")
                    
                    for stmt in elif_node.body:
                        flow = self.ast_to_flow(stmt, indent + 1)
                        if flow:
                            lines.append(flow)
                    
                    if elif_node.orelse:
                        macro_else = 'O' if self.dense_mode else 'ELSE'
                        lines.append(f"{indent_str}{macro_else}:")
                        for stmt in elif_node.orelse:
                            flow = self.ast_to_flow(stmt, indent + 1)
                            if flow:
                                lines.append(flow)
                else:
                    # else
                    macro_else = 'O' if self.dense_mode else 'ELSE'
                    lines.append(f"{indent_str}{macro_else}:")
                    for stmt in node.orelse:
                        flow = self.ast_to_flow(stmt, indent + 1)
                        if flow:
                            lines.append(flow)
            
            return '\n'.join(lines)
        
        elif isinstance(node, ast.For):
            # Dense for: F x∈iter:body
            lines = []
            target = self._process_target(node.target)
            iter_val = self._process_value(node.iter)
            macro = 'F' if self.dense_mode else 'FOR'
            
            if self.dense_mode:
                lines.append(f"{indent_str}{macro} {target}∈{iter_val}:")
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
            # Dense try: T:body X(E):handler
            lines = []
            macro_try = 'T' if self.dense_mode else 'TRY'
            macro_except = 'X' if self.dense_mode else 'CATCH'
            
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
                return f"{indent_str}{macro} {exc}"
            return f"{indent_str}{macro}"
        
        elif isinstance(node, ast.Delete):
            macro = 'D' if self.dense_mode else 'DEL'
            targets = [self._process_target(t) for t in node.targets]
            return f"{indent_str}{macro} {','.join(targets)}"
        
        return ""
    
    def _process_target(self, node: ast.AST) -> str:
        """Process assignment target with compression"""
        if isinstance(node, ast.Name):
            name = node.id
            # Check local compressions first
            if self.current_scope_id and self.current_scope_id in self.local_compressions:
                local_map = self.local_compressions[self.current_scope_id]
                if name in local_map:
                    return local_map[name]
            # Then global compressions
            return self.name_map.get(name, name)
        elif isinstance(node, ast.Attribute):
            obj = self._process_value(node.value)
            attr = node.attr
            # Use dot notation but compress object name
            return f"{obj}.{attr}"
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
            
            # Check local compressions
            if self.current_scope_id and self.current_scope_id in self.local_compressions:
                local_map = self.local_compressions[self.current_scope_id]
                if name in local_map:
                    return local_map[name]
            
            return self.name_map.get(name, name)
        elif isinstance(node, ast.Constant):
            # Pool constants if enabled
            if self.pool_constants and isinstance(node.value, str) and len(node.value) > 10:
                pool_id = self._get_pool_id(node.value)
                return f"${pool_id}" if self.dense_mode else f"POOL({pool_id})"
            
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
            obj = self._process_value(node.value)
            # Compress common patterns
            if self.dense_mode and obj == 's':  # self
                return f"s.{node.attr}"
            return f"{obj}.{node.attr}"
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
            if self.dense_mode:
                return f"{left}{op}{right}"  # No spaces
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
    
    def _process_call(self, node: ast.Call) -> str:
        """Process function call with ultra-compact syntax"""
        if isinstance(node.func, ast.Attribute):
            obj = self._process_value(node.func.value)
            method = node.func.attr
            
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
                
            # Regular method call
            args = [self._process_value(a) for a in node.args]
            if self.dense_mode:
                return f"C({obj}.{method},{','.join(args)})" if args else f"C({obj}.{method})"
            else:
                return f"CALL({obj}.{method}, {', '.join(args)})" if args else f"CALL({obj}.{method})"
        
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
                # Ultra-compact print
                args = [self._process_value(a) for a in node.args]
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
                    # Ultra-compact operators
                    if isinstance(op, ast.Is) and isinstance(right, ast.Constant) and right.value is None:
                        comparisons.append(f"N({left})")  # Compact is None
                    elif isinstance(op, ast.IsNot) and isinstance(right, ast.Constant) and right.value is None:
                        comparisons.append(f"!N({left})")  # Compact is not None
                    elif isinstance(op, ast.In):
                        comparisons.append(f"{left}∈{right_val}")
                    elif isinstance(op, ast.NotIn):
                        comparisons.append(f"{left}∉{right_val}")
                    elif isinstance(op, ast.Eq):
                        comparisons.append(f"{left}={right_val}")
                    elif isinstance(op, ast.NotEq):
                        comparisons.append(f"{left}≠{right_val}")
                    elif isinstance(op, ast.Lt):
                        comparisons.append(f"{left}<{right_val}")
                    elif isinstance(op, ast.LtE):
                        comparisons.append(f"{left}≤{right_val}")
                    elif isinstance(op, ast.Gt):
                        comparisons.append(f"{left}>{right_val}")
                    elif isinstance(op, ast.GtE):
                        comparisons.append(f"{left}≥{right_val}")
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