# optimize_ai/input_optimizer/engine/flow_language.py
"""
FLOW language compiler for CAI3-LITE.
Converts between Python AST and FLOW representation.
"""

import ast
from typing import Any, Dict, List, Optional, Union
import re

class FLOWCompiler:
    """Converts Python AST to FLOW representation and back"""
    
    # MACROS v1 - standard vocabulary for FLOW
    MACROS_V1 = {
        'LET': 'assign',
        'SET': 'setattr/setitem',
        'CALL': 'call',
        'FOR': 'for',
        'IF': 'if',
        'ELIF': 'elif',
        'ELSE': 'else',
        'TRY': 'try',
        'CATCH': 'except',
        'FINALLY': 'finally',
        'RET': 'return',
        'YIELD': 'yield',
        'INC': 'increment',
        'DEC': 'decrement',
        'APPEND': 'append',
        'POP': 'pop',
        'COPY': 'copy',
        'ISNONE': 'is None',
        'ISNOTNONE': 'is not None',
        'AND': 'and',
        'OR': 'or',
        'NOT': 'not',
        'IN': 'in',
        'NOTIN': 'not in',
        'BREAK': 'break',
        'CONTINUE': 'continue',
        'WHILE': 'while',
        'WITH': 'with',
        'ASSERT': 'assert',
        'RAISE': 'raise',
        'PASS': 'pass',
        'DEL': 'del',
        'PRINT': 'print'
    }
    
    def __init__(self, name_map: Optional[Dict[str, str]] = None):
        """Initialize with optional name mapping"""
        self.name_map = name_map or {}
        self.reverse_map = {v: k for k, v in self.name_map.items()}
    
    def ast_to_flow(self, node: ast.AST, indent: int = 0) -> str:
        """Convert Python AST to FLOW representation"""
        indent_str = '  ' * indent
        
        if isinstance(node, ast.FunctionDef):
            # Function should already be in table, just process body
            body_flows = []
            for stmt in node.body:
                if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Str):
                    # Skip docstrings
                    continue
                flow = self.ast_to_flow(stmt, indent)
                if flow:
                    body_flows.append(flow)
            return '\n'.join(body_flows)
        
        elif isinstance(node, ast.Assign):
            # LET x = value
            target = self._process_target(node.targets[0])
            value = self._process_value(node.value)
            return f"{indent_str}LET {target} = {value}"
        
        elif isinstance(node, ast.AugAssign):
            # Handle += -= etc
            target = self._process_target(node.target)
            op = self._get_aug_op(node.op)
            value = self._process_value(node.value)
            
            if op == '+=' and value == '1':
                return f"{indent_str}INC {target}"
            elif op == '-=' and value == '1':
                return f"{indent_str}DEC {target}"
            else:
                return f"{indent_str}SET {target} = {target} {op[0]} {value}"
        
        elif isinstance(node, ast.Return):
            # RET value
            if node.value:
                value = self._process_value(node.value)
                return f"{indent_str}RET {value}"
            return f"{indent_str}RET"
        
        elif isinstance(node, ast.If):
            # IF condition:
            #   body
            # ELIF condition:
            #   body
            # ELSE:
            #   body
            lines = []
            condition = self._process_condition(node.test)
            lines.append(f"{indent_str}IF {condition}:")
            
            for stmt in node.body:
                flow = self.ast_to_flow(stmt, indent + 1)
                if flow:
                    lines.append(flow)
            
            # Handle elif/else
            if node.orelse:
                if len(node.orelse) == 1 and isinstance(node.orelse[0], ast.If):
                    # This is an elif
                    elif_node = node.orelse[0]
                    condition = self._process_condition(elif_node.test)
                    lines.append(f"{indent_str}ELIF {condition}:")
                    for stmt in elif_node.body:
                        flow = self.ast_to_flow(stmt, indent + 1)
                        if flow:
                            lines.append(flow)
                    # Check for else after elif
                    if elif_node.orelse:
                        lines.append(f"{indent_str}ELSE:")
                        for stmt in elif_node.orelse:
                            flow = self.ast_to_flow(stmt, indent + 1)
                            if flow:
                                lines.append(flow)
                else:
                    # This is an else
                    lines.append(f"{indent_str}ELSE:")
                    for stmt in node.orelse:
                        flow = self.ast_to_flow(stmt, indent + 1)
                        if flow:
                            lines.append(flow)
            
            return '\n'.join(lines)
        
        elif isinstance(node, ast.For):
            # FOR x in iterable:
            lines = []
            target = self._process_target(node.target)
            iter_val = self._process_value(node.iter)
            lines.append(f"{indent_str}FOR {target} in {iter_val}:")
            
            for stmt in node.body:
                flow = self.ast_to_flow(stmt, indent + 1)
                if flow:
                    lines.append(flow)
            
            return '\n'.join(lines)
        
        elif isinstance(node, ast.While):
            # WHILE condition:
            lines = []
            condition = self._process_condition(node.test)
            lines.append(f"{indent_str}WHILE {condition}:")
            
            for stmt in node.body:
                flow = self.ast_to_flow(stmt, indent + 1)
                if flow:
                    lines.append(flow)
            
            return '\n'.join(lines)
        
        elif isinstance(node, ast.Try):
            # TRY:
            #   body
            # CATCH Exception as e:
            #   handler
            lines = []
            lines.append(f"{indent_str}TRY:")
            
            for stmt in node.body:
                flow = self.ast_to_flow(stmt, indent + 1)
                if flow:
                    lines.append(flow)
            
            for handler in node.handlers:
                exc_type = handler.type.id if handler.type and hasattr(handler.type, 'id') else 'Exception'
                exc_name = handler.name if handler.name else '_'
                
                # Handle multiple exception types
                if handler.type and isinstance(handler.type, ast.Tuple):
                    exc_types = [self._get_name(e) for e in handler.type.elts]
                    exc_type = f"({','.join(exc_types)})"
                
                lines.append(f"{indent_str}CATCH {exc_type} as {exc_name}:")
                
                for stmt in handler.body:
                    flow = self.ast_to_flow(stmt, indent + 1)
                    if flow:
                        lines.append(flow)
            
            if node.finalbody:
                lines.append(f"{indent_str}FINALLY:")
                for stmt in node.finalbody:
                    flow = self.ast_to_flow(stmt, indent + 1)
                    if flow:
                        lines.append(flow)
            
            return '\n'.join(lines)
        
        elif isinstance(node, ast.Expr):
            # Expression statement (usually a call)
            if isinstance(node.value, ast.Call):
                call_str = self._process_call(node.value)
                return f"{indent_str}{call_str}"
            else:
                value = self._process_value(node.value)
                return f"{indent_str}{value}"
        
        elif isinstance(node, ast.Break):
            return f"{indent_str}BREAK"
        
        elif isinstance(node, ast.Continue):
            return f"{indent_str}CONTINUE"
        
        elif isinstance(node, ast.Pass):
            return f"{indent_str}PASS"
        
        elif isinstance(node, ast.Raise):
            if node.exc:
                exc = self._process_value(node.exc)
                return f"{indent_str}RAISE {exc}"
            return f"{indent_str}RAISE"
        
        elif isinstance(node, ast.Assert):
            test = self._process_condition(node.test)
            if node.msg:
                msg = self._process_value(node.msg)
                return f"{indent_str}ASSERT {test}, {msg}"
            return f"{indent_str}ASSERT {test}"
        
        elif isinstance(node, ast.Delete):
            targets = [self._process_target(t) for t in node.targets]
            return f"{indent_str}DEL {', '.join(targets)}"
        
        return ""
    
    def _process_target(self, node: ast.AST) -> str:
        """Process assignment target"""
        if isinstance(node, ast.Name):
            name = node.id
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
            targets = [self._process_target(t) for t in node.elts]
            return f"({', '.join(targets)})"
        elif isinstance(node, ast.List):
            targets = [self._process_target(t) for t in node.elts]
            return f"[{', '.join(targets)}]"
        return "?"
    
    def _process_value(self, node: ast.AST) -> str:
        """Process a value expression"""
        if node is None:
            return "None"
        elif isinstance(node, ast.Name):
            name = node.id
            return self.name_map.get(name, name)
        elif isinstance(node, ast.Constant):
            if isinstance(node.value, str):
                # Use f-string notation for strings
                return f'"{node.value}"' if '"' not in node.value else f"'{node.value}'"
            elif node.value is None:
                return "None"
            elif node.value is True:
                return "True"
            elif node.value is False:
                return "False"
            return str(node.value)
        elif isinstance(node, ast.Attribute):
            obj = self._process_value(node.value)
            return f"{obj}.{node.attr}"
        elif isinstance(node, ast.Call):
            return self._process_call(node)
        elif isinstance(node, ast.List):
            items = [self._process_value(e) for e in node.elts]
            return f"[{', '.join(items)}]"
        elif isinstance(node, ast.Dict):
            pairs = []
            for k, v in zip(node.keys, node.values):
                key = self._process_value(k) if k else ''
                val = self._process_value(v)
                if k:
                    pairs.append(f"{key}: {val}")
                else:
                    pairs.append(f"**{val}")
            return f"{{{', '.join(pairs)}}}"
        elif isinstance(node, ast.Tuple):
            items = [self._process_value(e) for e in node.elts]
            return f"({', '.join(items)})"
        elif isinstance(node, ast.BinOp):
            left = self._process_value(node.left)
            right = self._process_value(node.right)
            op = self._get_binop(node.op)
            return f"{left} {op} {right}"
        elif isinstance(node, ast.UnaryOp):
            operand = self._process_value(node.operand)
            if isinstance(node.op, ast.Not):
                return f"NOT {operand}"
            elif isinstance(node.op, ast.USub):
                return f"-{operand}"
            elif isinstance(node.op, ast.UAdd):
                return f"+{operand}"
            return f"?{operand}"
        elif isinstance(node, ast.Compare):
            return self._process_condition(node)
        elif isinstance(node, ast.IfExp):
            # Ternary: a if condition else b
            cond = self._process_condition(node.test)
            true_val = self._process_value(node.body)
            false_val = self._process_value(node.orelse)
            return f"({true_val} if {cond} else {false_val})"
        elif isinstance(node, ast.Lambda):
            # Simple lambda representation
            args = [a.arg for a in node.args.args]
            body = self._process_value(node.body)
            return f"lambda {', '.join(args)}: {body}"
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
            # f-string
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
        """Process a function call"""
        # Special handling for common patterns
        if isinstance(node.func, ast.Attribute):
            obj = self._process_value(node.func.value)
            method = node.func.attr
            
            # Special cases for list operations
            if method == 'append' and len(node.args) == 1:
                arg = self._process_value(node.args[0])
                return f"APPEND {obj}, {arg}"
            elif method == 'pop' and len(node.args) <= 1:
                if node.args:
                    arg = self._process_value(node.args[0])
                    return f"POP({obj}, {arg})"
                return f"POP({obj})"
            elif method == 'copy' and not node.args:
                return f"COPY({obj})"
            elif method == 'get' and obj.endswith('.config'):
                # Special handling for config.get
                args = [self._process_value(a) for a in node.args]
                return f"CALL({obj}.get, {', '.join(args)})"
            else:
                # Regular method call
                args = [self._process_value(a) for a in node.args]
                kwargs = [f"{k.arg}={self._process_value(v)}" for k, v in zip(node.keywords, node.keywords)]
                all_args = args + kwargs
                return f"CALL({obj}.{method}, {', '.join(all_args)})" if all_args else f"CALL({obj}.{method})"
        
        elif isinstance(node.func, ast.Name):
            func_name = self.name_map.get(node.func.id, node.func.id)
            
            # Special built-in functions
            if func_name == 'isinstance':
                args = [self._process_value(a) for a in node.args]
                return f"isinstance({', '.join(args)})"
            elif func_name == 'len':
                arg = self._process_value(node.args[0])
                return f"len({arg})"
            elif func_name == 'print':
                args = [self._process_value(a) for a in node.args]
                return f"PRINT {', '.join(args)}"
            else:
                args = [self._process_value(a) for a in node.args]
                return f"CALL({func_name}, {', '.join(args)})" if args else f"CALL({func_name})"
        
        return "CALL(?)"
    
    def _process_condition(self, node: ast.AST) -> str:
        """Process a condition expression"""
        if isinstance(node, ast.Compare):
            left = self._process_value(node.left)
            comparisons = []
            
            for op, right in zip(node.ops, node.comparators):
                right_val = self._process_value(right)
                
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
                else:
                    comparisons.append(f"({left} ? {right_val})")
            
            return ' and '.join(comparisons) if len(comparisons) > 1 else comparisons[0]
        
        elif isinstance(node, ast.BoolOp):
            if isinstance(node.op, ast.And):
                parts = [self._process_condition(v) for v in node.values]
                return f"({' and '.join(parts)})"
            elif isinstance(node.op, ast.Or):
                parts = [self._process_condition(v) for v in node.values]
                return f"({' or '.join(parts)})"
        
        elif isinstance(node, ast.UnaryOp):
            if isinstance(node.op, ast.Not):
                operand = self._process_condition(node.operand)
                return f"NOT {operand}"
        
        elif isinstance(node, ast.Name):
            name = self.name_map.get(node.id, node.id)
            return name
        
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
    
    def flow_to_ast(self, flow_text: str) -> ast.AST:
        """Convert FLOW back to Python AST"""
        lines = flow_text.strip().split('\n')
        return self._parse_flow_lines(lines, 0)[0]
    
    def _parse_flow_lines(self, lines: List[str], start_idx: int = 0) -> tuple[List[ast.AST], int]:
        """Parse FLOW lines into AST nodes"""
        stmts = []
        i = start_idx
        
        while i < len(lines):
            line = lines[i].rstrip()
            if not line or line.strip() == 'END':
                i += 1
                continue
            
            # Get indentation level
            indent = len(line) - len(line.lstrip())
            line_content = line.strip()
            
            if line_content.startswith('LET '):
                # Variable assignment
                stmt = self._parse_let(line_content)
                stmts.append(stmt)
                i += 1
            
            elif line_content.startswith('SET '):
                # Attribute/index assignment
                stmt = self._parse_set(line_content)
                stmts.append(stmt)
                i += 1
            
            elif line_content.startswith('RET'):
                # Return statement
                stmt = self._parse_return(line_content)
                stmts.append(stmt)
                i += 1
            
            elif line_content.startswith('IF '):
                # If statement
                stmt, next_i = self._parse_if(lines, i)
                stmts.append(stmt)
                i = next_i
            
            elif line_content.startswith('FOR '):
                # For loop
                stmt, next_i = self._parse_for(lines, i)
                stmts.append(stmt)
                i = next_i
            
            elif line_content.startswith('WHILE '):
                # While loop
                stmt, next_i = self._parse_while(lines, i)
                stmts.append(stmt)
                i = next_i
            
            elif line_content.startswith('TRY:'):
                # Try block
                stmt, next_i = self._parse_try(lines, i)
                stmts.append(stmt)
                i = next_i
            
            elif line_content.startswith('CALL('):
                # Function call
                stmt = self._parse_call_stmt(line_content)
                stmts.append(stmt)
                i += 1
            
            elif line_content.startswith('APPEND '):
                # List append
                stmt = self._parse_append(line_content)
                stmts.append(stmt)
                i += 1
            
            elif line_content.startswith('INC '):
                # Increment
                stmt = self._parse_inc(line_content)
                stmts.append(stmt)
                i += 1
            
            elif line_content.startswith('DEC '):
                # Decrement
                stmt = self._parse_dec(line_content)
                stmts.append(stmt)
                i += 1
            
            elif line_content.startswith('PRINT '):
                # Print statement
                stmt = self._parse_print(line_content)
                stmts.append(stmt)
                i += 1
            
            elif line_content == 'PASS':
                stmts.append(ast.Pass())
                i += 1
            
            elif line_content == 'BREAK':
                stmts.append(ast.Break())
                i += 1
            
            elif line_content == 'CONTINUE':
                stmts.append(ast.Continue())
                i += 1
            
            else:
                # Skip unknown lines
                i += 1
        
        return stmts, i
    
    def _parse_let(self, line: str) -> ast.Assign:
        """Parse LET statement"""
        # LET x = value
        match = re.match(r'LET\s+(\S+)\s*=\s*(.+)', line)
        if match:
            target_str, value_str = match.groups()
            target = self._parse_target(target_str)
            value = self._parse_expression(value_str)
            return ast.Assign(targets=[target], value=value)
        return ast.Pass()
    
    def _parse_set(self, line: str) -> ast.Assign:
        """Parse SET statement"""
        # SET x.y = value or SET x[y] = value
        match = re.match(r'SET\s+(\S+)\s*=\s*(.+)', line)
        if match:
            target_str, value_str = match.groups()
            target = self._parse_target(target_str)
            value = self._parse_expression(value_str)
            return ast.Assign(targets=[target], value=value)
        return ast.Pass()
    
    def _parse_return(self, line: str) -> ast.Return:
        """Parse RET statement"""
        if line == 'RET':
            return ast.Return(value=None)
        
        match = re.match(r'RET\s+(.+)', line)
        if match:
            value_str = match.group(1)
            value = self._parse_expression(value_str)
            return ast.Return(value=value)
        return ast.Return(value=None)
    
    def _parse_target(self, target_str: str) -> ast.AST:
        """Parse assignment target"""
        # Reverse name mapping
        target_str = self.reverse_map.get(target_str, target_str)
        
        if '.' in target_str:
            # Attribute access
            parts = target_str.split('.')
            obj = ast.Name(id=parts[0], ctx=ast.Load())
            for attr in parts[1:]:
                obj = ast.Attribute(value=obj, attr=attr, ctx=ast.Load())
            obj.ctx = ast.Store()
            return obj
        elif '[' in target_str and ']' in target_str:
            # Subscript
            obj_str = target_str[:target_str.index('[')]
            index_str = target_str[target_str.index('[')+1:target_str.rindex(']')]
            obj = ast.Name(id=self.reverse_map.get(obj_str, obj_str), ctx=ast.Load())
            index = self._parse_expression(index_str)
            return ast.Subscript(value=obj, slice=index, ctx=ast.Store())
        else:
            # Simple name
            return ast.Name(id=self.reverse_map.get(target_str, target_str), ctx=ast.Store())
    
    def _parse_expression(self, expr_str: str) -> ast.AST:
        """Parse an expression string"""
        expr_str = expr_str.strip()
        
        # Handle special values
        if expr_str == 'None':
            return ast.Constant(value=None)
        elif expr_str == 'True':
            return ast.Constant(value=True)
        elif expr_str == 'False':
            return ast.Constant(value=False)
        elif expr_str.startswith('"') and expr_str.endswith('"'):
            return ast.Constant(value=expr_str[1:-1])
        elif expr_str.startswith("'") and expr_str.endswith("'"):
            return ast.Constant(value=expr_str[1:-1])
        elif expr_str.startswith('CALL('):
            return self._parse_call_expr(expr_str)
        elif expr_str.startswith('COPY('):
            # COPY(x) -> x.copy()
            match = re.match(r'COPY\((.+)\)', expr_str)
            if match:
                obj_str = match.group(1)
                obj = self._parse_expression(obj_str)
                return ast.Call(
                    func=ast.Attribute(value=obj, attr='copy', ctx=ast.Load()),
                    args=[],
                    keywords=[]
                )
        
        # Try to parse as number
        try:
            if '.' in expr_str:
                return ast.Constant(value=float(expr_str))
            else:
                return ast.Constant(value=int(expr_str))
        except ValueError:
            pass
        
        # Parse as name or attribute
        if '.' in expr_str:
            parts = expr_str.split('.')
            obj = ast.Name(id=self.reverse_map.get(parts[0], parts[0]), ctx=ast.Load())
            for attr in parts[1:]:
                obj = ast.Attribute(value=obj, attr=attr, ctx=ast.Load())
            return obj
        
        # Simple name
        return ast.Name(id=self.reverse_map.get(expr_str, expr_str), ctx=ast.Load())
    
    def _parse_call_expr(self, expr_str: str) -> ast.Call:
        """Parse CALL expression"""
        # CALL(func, args...)
        match = re.match(r'CALL\(([^,\)]+)(?:,\s*(.+))?\)', expr_str)
        if match:
            func_str = match.group(1)
            args_str = match.group(2) if match.group(2) else ""
            
            # Parse function
            if '.' in func_str:
                parts = func_str.split('.')
                obj = ast.Name(id=self.reverse_map.get(parts[0], parts[0]), ctx=ast.Load())
                for attr in parts[1:-1]:
                    obj = ast.Attribute(value=obj, attr=attr, ctx=ast.Load())
                func = ast.Attribute(value=obj, attr=parts[-1], ctx=ast.Load())
            else:
                func = ast.Name(id=self.reverse_map.get(func_str, func_str), ctx=ast.Load())
            
            # Parse arguments
            args = []
            if args_str:
                # Simple arg parsing (doesn't handle nested commas well)
                arg_strs = args_str.split(',')
                for arg_str in arg_strs:
                    args.append(self._parse_expression(arg_str.strip()))
            
            return ast.Call(func=func, args=args, keywords=[])
        
        return ast.Call(func=ast.Name(id='unknown', ctx=ast.Load()), args=[], keywords=[])
    
    def _parse_if(self, lines: List[str], start_idx: int) -> tuple[ast.If, int]:
        """Parse IF/ELIF/ELSE block"""
        i = start_idx
        line = lines[i].strip()
        
        # Parse IF condition
        match = re.match(r'IF\s+(.+):', line)
        if not match:
            return ast.Pass(), i + 1
        
        condition = self._parse_condition(match.group(1))
        i += 1
        
        # Parse IF body
        body = []
        base_indent = len(lines[start_idx]) - len(lines[start_idx].lstrip())
        
        while i < len(lines):
            if not lines[i].strip():
                i += 1
                continue
            
            current_indent = len(lines[i]) - len(lines[i].lstrip())
            if current_indent <= base_indent:
                break
            
            # Parse body statement
            body_stmts, next_i = self._parse_flow_lines([lines[i]], 0)
            body.extend(body_stmts)
            i += 1
        
        # Check for ELIF/ELSE
        orelse = []
        if i < len(lines):
            line = lines[i].strip()
            if line.startswith('ELIF '):
                # Parse as nested If
                elif_stmt, next_i = self._parse_if(lines, i)
                orelse = [elif_stmt]
                i = next_i
            elif line.startswith('ELSE:'):
                # Parse ELSE body
                i += 1
                while i < len(lines):
                    if not lines[i].strip():
                        i += 1
                        continue
                    
                    current_indent = len(lines[i]) - len(lines[i].lstrip())
                    if current_indent <= base_indent:
                        break
                    
                    else_stmts, next_i = self._parse_flow_lines([lines[i]], 0)
                    orelse.extend(else_stmts)
                    i += 1
        
        return ast.If(test=condition, body=body or [ast.Pass()], orelse=orelse), i
    
    def _parse_for(self, lines: List[str], start_idx: int) -> tuple[ast.For, int]:
        """Parse FOR loop"""
        i = start_idx
        line = lines[i].strip()
        
        # Parse FOR target in iter
        match = re.match(r'FOR\s+(\S+)\s+in\s+(.+):', line)
        if not match:
            return ast.Pass(), i + 1
        
        target = self._parse_target(match.group(1))
        iter_expr = self._parse_expression(match.group(2))
        i += 1
        
        # Parse body
        body = []
        base_indent = len(lines[start_idx]) - len(lines[start_idx].lstrip())
        
        while i < len(lines):
            if not lines[i].strip():
                i += 1
                continue
            
            current_indent = len(lines[i]) - len(lines[i].lstrip())
            if current_indent <= base_indent:
                break
            
            body_stmts, next_i = self._parse_flow_lines([lines[i]], 0)
            body.extend(body_stmts)
            i += 1
        
        return ast.For(target=target, iter=iter_expr, body=body or [ast.Pass()], orelse=[]), i
    
    def _parse_while(self, lines: List[str], start_idx: int) -> tuple[ast.While, int]:
        """Parse WHILE loop"""
        i = start_idx
        line = lines[i].strip()
        
        # Parse WHILE condition
        match = re.match(r'WHILE\s+(.+):', line)
        if not match:
            return ast.Pass(), i + 1
        
        condition = self._parse_condition(match.group(1))
        i += 1
        
        # Parse body
        body = []
        base_indent = len(lines[start_idx]) - len(lines[start_idx].lstrip())
        
        while i < len(lines):
            if not lines[i].strip():
                i += 1
                continue
            
            current_indent = len(lines[i]) - len(lines[i].lstrip())
            if current_indent <= base_indent:
                break
            
            body_stmts, next_i = self._parse_flow_lines([lines[i]], 0)
            body.extend(body_stmts)
            i += 1
        
        return ast.While(test=condition, body=body or [ast.Pass()], orelse=[]), i
    
    def _parse_try(self, lines: List[str], start_idx: int) -> tuple[ast.Try, int]:
        """Parse TRY/CATCH/FINALLY block"""
        i = start_idx
        i += 1  # Skip TRY: line
        
        # Parse TRY body
        body = []
        handlers = []
        finalbody = []
        base_indent = len(lines[start_idx]) - len(lines[start_idx].lstrip())
        
        while i < len(lines):
            if not lines[i].strip():
                i += 1
                continue
            
            current_indent = len(lines[i]) - len(lines[i].lstrip())
            line = lines[i].strip()
            
            if current_indent <= base_indent and (line.startswith('CATCH ') or line.startswith('FINALLY:')):
                break
            
            body_stmts, next_i = self._parse_flow_lines([lines[i]], 0)
            body.extend(body_stmts)
            i += 1
        
        # Parse CATCH handlers
        while i < len(lines) and lines[i].strip().startswith('CATCH '):
            line = lines[i].strip()
            match = re.match(r'CATCH\s+(\S+)\s+as\s+(\S+):', line)
            if match:
                exc_type_str = match.group(1)
                exc_name = match.group(2)
                
                # Parse exception type
                if exc_type_str.startswith('(') and exc_type_str.endswith(')'):
                    # Multiple exception types
                    exc_types = exc_type_str[1:-1].split(',')
                    exc_type = ast.Tuple(
                        elts=[ast.Name(id=t.strip(), ctx=ast.Load()) for t in exc_types],
                        ctx=ast.Load()
                    )
                else:
                    exc_type = ast.Name(id=exc_type_str, ctx=ast.Load())
                
                i += 1
                
                # Parse handler body
                handler_body = []
                while i < len(lines):
                    if not lines[i].strip():
                        i += 1
                        continue
                    
                    current_indent = len(lines[i]) - len(lines[i].lstrip())
                    if current_indent <= base_indent:
                        break
                    
                    handler_stmts, next_i = self._parse_flow_lines([lines[i]], 0)
                    handler_body.extend(handler_stmts)
                    i += 1
                
                handlers.append(ast.ExceptHandler(
                    type=exc_type,
                    name=exc_name if exc_name != '_' else None,
                    body=handler_body or [ast.Pass()]
                ))
            else:
                i += 1
        
        # Parse FINALLY
        if i < len(lines) and lines[i].strip() == 'FINALLY:':
            i += 1
            while i < len(lines):
                if not lines[i].strip():
                    i += 1
                    continue
                
                current_indent = len(lines[i]) - len(lines[i].lstrip())
                if current_indent <= base_indent:
                    break
                
                finally_stmts, next_i = self._parse_flow_lines([lines[i]], 0)
                finalbody.extend(finally_stmts)
                i += 1
        
        return ast.Try(
            body=body or [ast.Pass()],
            handlers=handlers,
            orelse=[],
            finalbody=finalbody
        ), i
    
    def _parse_condition(self, cond_str: str) -> ast.AST:
        """Parse a condition expression"""
        cond_str = cond_str.strip()
        
        # Handle ISNONE/ISNOTNONE
        if cond_str.startswith('ISNONE('):
            match = re.match(r'ISNONE\((.+)\)', cond_str)
            if match:
                operand = self._parse_expression(match.group(1))
                return ast.Compare(
                    left=operand,
                    ops=[ast.Is()],
                    comparators=[ast.Constant(value=None)]
                )
        
        if cond_str.startswith('ISNOTNONE('):
            match = re.match(r'ISNOTNONE\((.+)\)', cond_str)
            if match:
                operand = self._parse_expression(match.group(1))
                return ast.Compare(
                    left=operand,
                    ops=[ast.IsNot()],
                    comparators=[ast.Constant(value=None)]
                )
        
        # Handle NOT
        if cond_str.startswith('NOT '):
            operand = self._parse_condition(cond_str[4:])
            return ast.UnaryOp(op=ast.Not(), operand=operand)
        
        # Handle parentheses
        if cond_str.startswith('(') and cond_str.endswith(')'):
            inner = cond_str[1:-1]
            
            # Check for AND/OR
            if ' and ' in inner:
                parts = inner.split(' and ')
                values = [self._parse_condition(p.strip()) for p in parts]
                return ast.BoolOp(op=ast.And(), values=values)
            elif ' or ' in inner:
                parts = inner.split(' or ')
                values = [self._parse_condition(p.strip()) for p in parts]
                return ast.BoolOp(op=ast.Or(), values=values)
            
            # Check for comparisons
            for op_str, op_class in [
                (' not in ', ast.NotIn),
                (' in ', ast.In),
                (' == ', ast.Eq),
                (' != ', ast.NotEq),
                (' <= ', ast.LtE),
                (' >= ', ast.GtE),
                (' < ', ast.Lt),
                (' > ', ast.Gt),
            ]:
                if op_str in inner:
                    left_str, right_str = inner.split(op_str, 1)
                    left = self._parse_expression(left_str.strip())
                    right = self._parse_expression(right_str.strip())
                    return ast.Compare(left=left, ops=[op_class()], comparators=[right])
        
        # Default: parse as expression
        return self._parse_expression(cond_str)
    
    def _parse_call_stmt(self, line: str) -> ast.Expr:
        """Parse CALL statement"""
        call_expr = self._parse_call_expr(line)
        return ast.Expr(value=call_expr)
    
    def _parse_append(self, line: str) -> ast.Expr:
        """Parse APPEND statement"""
        # APPEND list, value
        match = re.match(r'APPEND\s+(\S+),\s*(.+)', line)
        if match:
            list_str = match.group(1)
            value_str = match.group(2)
            
            list_expr = self._parse_expression(list_str)
            value_expr = self._parse_expression(value_str)
            
            return ast.Expr(value=ast.Call(
                func=ast.Attribute(value=list_expr, attr='append', ctx=ast.Load()),
                args=[value_expr],
                keywords=[]
            ))
        return ast.Pass()
    
    def _parse_inc(self, line: str) -> ast.AugAssign:
        """Parse INC statement"""
        # INC variable
        match = re.match(r'INC\s+(\S+)', line)
        if match:
            target = self._parse_target(match.group(1))
            return ast.AugAssign(
                target=target,
                op=ast.Add(),
                value=ast.Constant(value=1)
            )
        return ast.Pass()
    
    def _parse_dec(self, line: str) -> ast.AugAssign:
        """Parse DEC statement"""
        # DEC variable
        match = re.match(r'DEC\s+(\S+)', line)
        if match:
            target = self._parse_target(match.group(1))
            return ast.AugAssign(
                target=target,
                op=ast.Sub(),
                value=ast.Constant(value=1)
            )
        return ast.Pass()
    
    def _parse_print(self, line: str) -> ast.Expr:
        """Parse PRINT statement"""
        # PRINT args...
        match = re.match(r'PRINT\s+(.+)', line)
        if match:
            args_str = match.group(1)
            # Parse f-string if present
            if args_str.startswith('f"'):
                # Simple f-string handling
                return ast.Expr(value=ast.Call(
                    func=ast.Name(id='print', ctx=ast.Load()),
                    args=[self._parse_expression(args_str)],
                    keywords=[]
                ))
            else:
                # Regular print
                args = [self._parse_expression(a.strip()) for a in args_str.split(',')]
                return ast.Expr(value=ast.Call(
                    func=ast.Name(id='print', ctx=ast.Load()),
                    args=args,
                    keywords=[]
                ))
        return ast.Pass()
        