import ast
from typing import List, Optional, Union
from .flow_tokenizer import Token, TokenType, FLOWLexer

class FLOWParser:
    """Recursive descent parser for FLOW language"""
    
    def __init__(self, tokens: List[Token], pools: dict = None, chains: dict = None):
        self.tokens = tokens
        self.pos = 0
        self.pools = pools or {}
        self.chains = chains or {}
        
    def _fix_ast_attributes(self, node: ast.AST) -> ast.AST:
        """Add required AST attributes"""
        if not hasattr(node, 'lineno'):
            node.lineno = 1
        if not hasattr(node, 'col_offset'):
            node.col_offset = 0
        if not hasattr(node, 'end_lineno'):
            node.end_lineno = node.lineno
        if not hasattr(node, 'end_col_offset'):
            node.end_col_offset = node.col_offset
        
        # Recursively fix child nodes
        for child in ast.iter_child_nodes(node):
            self._fix_ast_attributes(child)
        
        return node
    
    def _create_chain_node(self, chain_value: str) -> ast.AST:
        """Create an AST node for a chain like 'self.config.get'"""
        parts = chain_value.split('.')
        if len(parts) == 1:
            return ast.Name(id=parts[0], ctx=ast.Load())
        
        # Build attribute chain
        node = ast.Name(id=parts[0], ctx=ast.Load())
        for part in parts[1:]:
            node = ast.Attribute(value=node, attr=part, ctx=ast.Load())
        
        return node
        
    def current_token(self) -> Token:
        """Get current token without consuming"""
        if self.pos < len(self.tokens):
            return self.tokens[self.pos]
        return self.tokens[-1]  # EOF
    
    def peek_token(self, offset: int = 1) -> Optional[Token]:
        """Look ahead at token"""
        pos = self.pos + offset
        if pos < len(self.tokens):
            return self.tokens[pos]
        return None
    
    def consume(self, expected_type: TokenType = None) -> Token:
        """Consume and return current token"""
        token = self.current_token()
        if expected_type and token.type != expected_type:
            raise SyntaxError(f"Expected {expected_type}, got {token.type} at line {token.line}")
        self.pos += 1
        return token
    
    def parse_statements(self) -> List[ast.AST]:
        """Parse multiple statements with proper INDENT/DEDENT handling"""
        statements = []
        
        while self.current_token().type != TokenType.EOF:
            # Skip newlines at statement level
            if self.current_token().type == TokenType.NEWLINE:
                self.consume()
                continue
            
            # Skip INDENT/DEDENT at top level
            if self.current_token().type in (TokenType.INDENT, TokenType.DEDENT):
                self.consume()
                continue
                
            stmt = self.parse_statement()
            if stmt:
                statements.append(self._fix_ast_attributes(stmt))
            else:
                # If we can't parse a statement, skip the current token to avoid infinite loops
                # But be more careful about what we skip
                current = self.current_token()
                if current.type not in (TokenType.EOF, TokenType.NEWLINE):
                    # Only skip if we're truly stuck
                    saved_pos = self.pos
                    self.consume()
                    # If we're in an infinite loop, break out
                    if self.pos == saved_pos:
                        break
                continue
                
            # Handle semicolon separators
            if self.current_token().type == TokenType.SEMI:
                self.consume()
            
            # Skip trailing newlines after statements
            while self.current_token().type == TokenType.NEWLINE:
                self.consume()
        
        return statements
    
    def parse_statement(self) -> Optional[ast.AST]:
        """Parse statement with ALL macros."""
        token = self.current_token()
        
        if token.type == TokenType.EOF:
            return None
        
        # Skip comments and newlines
        if token.type in (TokenType.COMMENT, TokenType.NEWLINE):
            self.consume()
            return self.parse_statement()
        
        # Complete macro dispatch table
        macro_handlers = {
            TokenType.MACRO_L: self.parse_assignment,
            TokenType.MACRO_I: self.parse_if,
            TokenType.MACRO_F: self.parse_for,
            TokenType.MACRO_T: self.parse_try,
            TokenType.MACRO_R: self.parse_return,
            TokenType.MACRO_W: self.parse_while,
            TokenType.MACRO_Z: self.parse_with,
            TokenType.MACRO_H: self.parse_raise,
            TokenType.MACRO_D: self.parse_delete,
            TokenType.AT: self.parse_print,
            TokenType.MACRO_B: lambda: ast.Break(),
            TokenType.MACRO_K: lambda: ast.Continue(),
            TokenType.UNDERSCORE: lambda: ast.Pass(),
        }
        
        # Dispatch to handler
        if token.type in macro_handlers:
            handler = macro_handlers[token.type]
            if callable(handler):
                result = handler()
                # Consume token for simple macros
                if token.type in (TokenType.MACRO_B, TokenType.MACRO_K, TokenType.UNDERSCORE):
                    self.consume()
                return result
        
        # Skip macros handled by parent parsers
        if token.type in (TokenType.MACRO_E, TokenType.MACRO_O, 
                          TokenType.MACRO_X, TokenType.MACRO_J):
            return None
        
        # Check for bare assignment
        if self.is_assignment():
            return self.parse_bare_assignment()
        
        # Expression statement
        try:
            expr = self.parse_expression()
            return ast.Expr(value=expr) if expr else None
        except SyntaxError:
            return None
    
    def is_assignment(self) -> bool:
        """Check if current position starts an assignment"""
        # Look for pattern: assignable_target = value
        # But NOT comparison operators
        saved_pos = self.pos
        try:
            # Avoid going past EOF
            if self.current_token().type == TokenType.EOF:
                return False
                
            # Try to parse as target
            target = self.parse_primary()
            
            # Check if followed by single =
            if self.current_token().type == TokenType.EQ:
                # Make sure it's not ==
                next_token = self.peek_token()
                if next_token and next_token.type != TokenType.EQ:
                    return True
            return False
        except (SyntaxError, IndexError):
            # If parsing fails, it's not an assignment
            return False
        finally:
            self.pos = saved_pos
    
    def parse_assignment(self) -> ast.Assign:
        """Parse L target = value or bare assignment"""
        # Consume L if present
        if self.current_token().type == TokenType.MACRO_L:
            self.consume(TokenType.MACRO_L)
        
        # Parse target
        target = self.parse_assignable_target()
        
        # Expect =
        self.consume(TokenType.EQ)
        
        # Parse value
        value = self.parse_expression()
        
        return ast.Assign(targets=[target], value=value)
    
    def parse_bare_assignment(self) -> ast.Assign:
        """Parse assignment without L macro"""
        return self.parse_assignment()
    
    def parse_assignable_target(self) -> ast.AST:
        """Parse a valid assignment target"""
        node = self.parse_primary()
        
        # Validate it's assignable
        if not isinstance(node, (ast.Name, ast.Attribute, ast.Subscript)):
            raise SyntaxError(f"Invalid assignment target at line {self.current_token().line}")
        
        # Set context to Store
        if isinstance(node, ast.Name):
            node.ctx = ast.Store()
        elif isinstance(node, (ast.Attribute, ast.Subscript)):
            node.ctx = ast.Store()
            
        return node
    
    def parse_if(self) -> ast.If:
        """Parse I(condition): body with proper indentation handling"""
        self.consume(TokenType.MACRO_I)
        self.consume(TokenType.LPAR)
        test = self.parse_expression()
        self.consume(TokenType.RPAR)
        self.consume(TokenType.COLON)
        
        body = self.parse_suite()  # Simple!
        
        orelse = []
        if self.current_token().type == TokenType.MACRO_E:
            orelse = [self.parse_elif()]
        elif self.current_token().type == TokenType.MACRO_O:
            self.consume(TokenType.MACRO_O)
            self.consume(TokenType.COLON)
            orelse = self.parse_suite()
        
        return ast.If(test=test, body=body, orelse=orelse)
    
    def parse_suite(self) -> List[ast.AST]:
        """Universal suite parser that handles both braced and indented blocks"""
        self._skip_newlines()
        
        # Braced block takes precedence
        if self.current_token().type == TokenType.LBRACE:
            return self._parse_braced_suite()
        
        # Indented block
        if self.current_token().type == TokenType.INDENT:
            return self._parse_indented_suite()
        
        # Single-line suite
        stmt = self.parse_statement()
        return [stmt] if stmt else [ast.Pass()]

    def _parse_braced_suite(self) -> List[ast.AST]:
        """Parse {stmt; stmt; ...} with resilience."""
        self.consume(TokenType.LBRACE)
        statements = []
        
        while self.current_token().type != TokenType.RBRACE:
            if self.current_token().type == TokenType.EOF:
                raise SyntaxError("Unclosed brace at EOF")
            
            # Skip all separators and whitespace tokens
            while self.current_token().type in (
                TokenType.NEWLINE, TokenType.SEMI, 
                TokenType.INDENT, TokenType.DEDENT, 
                TokenType.COMMENT
            ):
                self.consume()
            
            if self.current_token().type == TokenType.RBRACE:
                break
            
            stmt = self.parse_statement()
            if stmt:
                statements.append(self._fix_ast_attributes(stmt))
            
            # Optional trailing separator
            if self.current_token().type == TokenType.SEMI:
                self.consume()
        
        self.consume(TokenType.RBRACE)
        return statements or [ast.Pass()]

    def _parse_indented_suite(self) -> List[ast.AST]:
        """Parse INDENT stmts DEDENT with comment skipping."""
        self.consume(TokenType.INDENT)
        statements = []
        
        while self.current_token().type not in (TokenType.DEDENT, TokenType.EOF):
            # Skip pure separators
            while self.current_token().type in (TokenType.NEWLINE, TokenType.COMMENT):
                self.consume()
            
            # Check for suite-ending keywords
            if self.current_token().type in (
                TokenType.MACRO_E, TokenType.MACRO_O, 
                TokenType.MACRO_X, TokenType.MACRO_J
            ):
                break
            
            if self.current_token().type == TokenType.DEDENT:
                break
                
            stmt = self.parse_statement()
            if stmt:
                statements.append(self._fix_ast_attributes(stmt))
        
        if self.current_token().type == TokenType.DEDENT:
            self.consume(TokenType.DEDENT)
        
        return statements or [ast.Pass()]

    def _skip_newlines(self):
        while self.current_token().type == TokenType.NEWLINE:
            self.consume()
    
    def parse_expression(self) -> ast.AST:
        """Entry point - decide if we support ternary."""
        # Option 1: No ternary support (simpler, safer)
        return self.parse_or_expr()
        
        # Option 2: With ternary (uncomment if needed)
        # return self.parse_ternary()
    
    def parse_or_expr(self) -> ast.AST:
        """Parse || expression"""
        left = self.parse_and_expr()
        
        while self.current_token().type == TokenType.OR:
            self.consume()
            right = self.parse_and_expr()
            left = ast.BoolOp(op=ast.Or(), values=[left, right])
        
        return left
    
    def parse_and_expr(self) -> ast.AST:
        """Parse & expression"""
        left = self.parse_comparison()
        
        while self.current_token().type == TokenType.AND:
            self.consume()
            right = self.parse_comparison()
            left = ast.BoolOp(op=ast.And(), values=[left, right])
        
        return left
    
    def parse_comparison(self) -> ast.AST:
        """Parse comparison operators"""
        left = self.parse_bitwise_or()
        
        ops = []
        comparators = []
        
        while True:
            token = self.current_token()
            op = None
            
            if token.type == TokenType.EQEQ:
                op = ast.Eq()
            elif token.type == TokenType.NE:
                op = ast.NotEq()
            elif token.type == TokenType.LT:
                op = ast.Lt()
            elif token.type == TokenType.LE:
                op = ast.LtE()
            elif token.type == TokenType.GT:
                op = ast.Gt()
            elif token.type == TokenType.GE:
                op = ast.GtE()
            elif token.type == TokenType.IN:
                op = ast.In()
            elif token.type == TokenType.NOTIN:
                op = ast.NotIn()
            else:
                break
            
            self.consume()
            ops.append(op)
            comparators.append(self.parse_bitwise_or())
        
        if ops:
            return ast.Compare(left=left, ops=ops, comparators=comparators)
        
        return left

    def parse_bitwise_or(self) -> ast.AST:
        """Parse bitwise OR (|)"""
        left = self.parse_bitwise_xor()
        
        while self.current_token().type == TokenType.PIPE:
            self.consume()
            right = self.parse_bitwise_xor()
            left = ast.BinOp(left=left, op=ast.BitOr(), right=right)
        
        return left

    def parse_bitwise_xor(self) -> ast.AST:
        """Parse bitwise XOR (^)"""
        left = self.parse_bitwise_and()
        
        while self.current_token().type == TokenType.CARET:
            self.consume()
            right = self.parse_bitwise_and()
            left = ast.BinOp(left=left, op=ast.BitXor(), right=right)
        
        return left

    def parse_bitwise_and(self) -> ast.AST:
        """Parse bitwise AND (&)"""
        left = self.parse_shift()
        
        while self.current_token().type == TokenType.AMPERSAND:
            self.consume()
            right = self.parse_shift()
            left = ast.BinOp(left=left, op=ast.BitAnd(), right=right)
        
        return left

    def parse_shift(self) -> ast.AST:
        """Parse shift operators (<< and >>)"""
        left = self.parse_additive()
        
        while self.current_token().type in (TokenType.LSHIFT, TokenType.RSHIFT):
            op_token = self.consume()
            right = self.parse_additive()
            
            if op_token.type == TokenType.LSHIFT:
                op = ast.LShift()
            else:
                op = ast.RShift()
            
            left = ast.BinOp(left=left, op=op, right=right)
        
        return left
    
    def parse_primary(self) -> ast.AST:
        """Parse primary expression"""
        token = self.current_token()
        
        # Handle literals
        if token.type == TokenType.NUM:
            self.consume()
            # Handle different number formats
            value_str = token.value
            try:
                if value_str.startswith('0x') or value_str.startswith('0X'):
                    # Hexadecimal
                    value = int(value_str, 16)
                elif value_str.startswith('0b') or value_str.startswith('0B'):
                    # Binary
                    value = int(value_str, 2)
                elif value_str.startswith('0o') or value_str.startswith('0O'):
                    # Octal
                    value = int(value_str, 8)
                elif '.' in value_str or 'e' in value_str.lower():
                    # Float
                    value = float(value_str)
                else:
                    # Integer
                    value = int(value_str)
                return ast.Constant(value=value)
            except ValueError:
                # Fallback for invalid number formats
                raise SyntaxError(f"Invalid number literal: {value_str} at line {token.line}")
        
        elif token.type == TokenType.STR:
            self.consume()
            # Remove quotes
            value = token.value[1:-1]
            return ast.Constant(value=value)
        
        elif token.type == TokenType.POOL:
            self.consume()
            # Resolve pool reference
            if token.value in self.pools:
                return ast.Constant(value=self.pools[token.value])
            return ast.Name(id=token.value, ctx=ast.Load())
        
        elif token.type == TokenType.HASH:
            self.consume()
            # For now, keep as string
            return ast.Constant(value=token.value)
        
        elif token.type == TokenType.CHAIN:
            self.consume()
            # Resolve chain alias
            if token.value in self.chains:
                chain_value = self.chains[token.value]
                # Check if it's a function call
                if self.current_token().type == TokenType.LPAR:
                    # This is a function call - parse as call
                    self.consume(TokenType.LPAR)
                    args = []
                    while self.current_token().type != TokenType.RPAR:
                        args.append(self.parse_expression())
                        if self.current_token().type == TokenType.COMMA:
                            self.consume()
                    self.consume(TokenType.RPAR)
                    
                    # Create a call node with the chain as the function
                    func_node = self._create_chain_node(chain_value)
                    return ast.Call(func=func_node, args=args, keywords=[])
                else:
                    # Regular chain access
                    return self._create_chain_node(chain_value)
            return ast.Name(id=token.value, ctx=ast.Load())
        
        elif token.type == TokenType.ID:
            self.consume()
            # Handle built-in constants
            if token.value in ('True', 'False', 'None'):
                if token.value == 'True':
                    node = ast.Constant(value=True)
                elif token.value == 'False':
                    node = ast.Constant(value=False)
                else:  # None
                    node = ast.Constant(value=None)
            else:
                node = ast.Name(id=token.value, ctx=ast.Load())
            
            # Handle member access and calls
            while True:
                if self.current_token().type == TokenType.DOT:
                    self.consume()
                    attr = self.consume(TokenType.ID)
                    node = ast.Attribute(value=node, attr=attr.value, ctx=ast.Load())
                    
                elif self.current_token().type == TokenType.LPAR:
                    # Function call
                    node = self._parse_call(node)
                    
                elif self.current_token().type == TokenType.LBRACK:
                    # Subscript
                    node = self._parse_subscript(node)
                else:
                    break
            
            return node
        
        elif token.type == TokenType.LBRACE:
            # Dictionary literal
            return self.parse_dict()
        
        elif token.type == TokenType.LBRACK:
            # List literal
            return self.parse_list()
        
        elif token.type == TokenType.LPAR:
            # Parenthesized expression
            self.consume()
            expr = self.parse_expression()
            self.consume(TokenType.RPAR)
            return expr
        
        else:
            raise SyntaxError(f"Unexpected token {token.type} at line {token.line}")
    
    def parse_dict(self) -> ast.Dict:
        """Parse {key:value, ...}"""
        self.consume(TokenType.LBRACE)
        keys = []
        values = []
        
        while self.current_token().type != TokenType.RBRACE:
            # Parse key
            key = self.parse_expression()
            keys.append(key)
            
            self.consume(TokenType.COLON)
            
            # Parse value
            value = self.parse_expression()
            values.append(value)
            
            if self.current_token().type == TokenType.COMMA:
                self.consume()
        
        self.consume(TokenType.RBRACE)
        return ast.Dict(keys=keys, values=values)
    
    def parse_list(self) -> ast.List:
        """Parse [item1, item2, ...]"""
        self.consume(TokenType.LBRACK)
        items = []
        
        while self.current_token().type != TokenType.RBRACK:
            item = self.parse_expression()
            items.append(item)
            
            if self.current_token().type == TokenType.COMMA:
                self.consume()
        
        self.consume(TokenType.RBRACK)
        return ast.List(elts=items, ctx=ast.Load())
    
    def parse_additive(self) -> ast.AST:
        """Parse addition and subtraction"""
        left = self.parse_multiplicative()
        
        while self.current_token().type in (TokenType.PLUS, TokenType.MINUS):
            op_token = self.consume()
            right = self.parse_multiplicative()
            
            if op_token.type == TokenType.PLUS:
                left = ast.BinOp(left=left, op=ast.Add(), right=right)
            else:
                left = ast.BinOp(left=left, op=ast.Sub(), right=right)
        
        return left
    
    def parse_multiplicative(self) -> ast.AST:
        """Parse *, /, //, % (call parse_power for proper precedence)."""
        left = self.parse_power()  # FIX: Call parse_power, not parse_unary
        
        while self.current_token().type in (TokenType.STAR, TokenType.SLASH, 
                                            TokenType.DOUBLESLASH, TokenType.PERCENT):
            op_token = self.consume()
            right = self.parse_power()  # FIX: Right side also calls parse_power
            
            if op_token.type == TokenType.STAR:
                op = ast.Mult()
            elif op_token.type == TokenType.SLASH:
                op = ast.Div()
            elif op_token.type == TokenType.DOUBLESLASH:
                op = ast.FloorDiv()
            else:
                op = ast.Mod()
            
            left = ast.BinOp(left=left, op=op, right=right)
        
        return left
    
    def parse_power(self) -> ast.AST:
        """Parse ** (right-associative)."""
        left = self.parse_unary()
        
        if self.current_token().type == TokenType.DOUBLESTAR:
            self.consume()
            right = self.parse_power()  # Right-associative recursion
            return ast.BinOp(left=left, op=ast.Pow(), right=right)
        
        return left
    
    def parse_unary(self) -> ast.AST:
        """Parse unary operators like -, +, not, and ~"""
        token = self.current_token()
        
        if token.type == TokenType.MINUS:
            self.consume()
            operand = self.parse_unary()  # Allow chaining unary operators
            return ast.UnaryOp(op=ast.USub(), operand=operand)
        elif token.type == TokenType.NOT:
            self.consume()
            operand = self.parse_unary()
            return ast.UnaryOp(op=ast.Not(), operand=operand)
        elif token.type == TokenType.PLUS:
            self.consume()
            operand = self.parse_unary()
            return ast.UnaryOp(op=ast.UAdd(), operand=operand)
        elif token.type == TokenType.TILDE:
            self.consume()
            operand = self.parse_unary()
            return ast.UnaryOp(op=ast.Invert(), operand=operand)
        else:
            return self.parse_postfix()
    
    def parse_postfix(self) -> ast.AST:
        """Parse postfix with proper slice support."""
        node = self.parse_primary()
        
        while True:
            if self.current_token().type == TokenType.DOT:
                self.consume()
                attr = self.consume(TokenType.ID).value
                node = ast.Attribute(value=node, attr=attr, ctx=ast.Load())
            
            elif self.current_token().type == TokenType.LPAR:
                node = self._parse_call(node)
            
            elif self.current_token().type == TokenType.LBRACK:
                node = self._parse_subscript(node)
            
            else:
                break
        
        return node
    
    def _parse_subscript(self, node: ast.AST) -> ast.AST:
        """Parse subscript with slice support."""
        self.consume(TokenType.LBRACK)
        
        # Check if this is a slice or simple index
        if self.current_token().type == TokenType.COLON:
            # Slice starting with : (e.g., [:5])
            slice_node = self._parse_slice(None)
        else:
            # Parse first expression
            first = self.parse_expression()
            
            if self.current_token().type == TokenType.COLON:
                # It's a slice
                slice_node = self._parse_slice(first)
            else:
                # Simple index
                slice_node = first
        
        self.consume(TokenType.RBRACK)
        return ast.Subscript(value=node, slice=slice_node, ctx=ast.Load())

    def _parse_slice(self, lower: Optional[ast.AST]) -> ast.Slice:
        """Parse slice notation [lower:upper:step]."""
        # We've already parsed lower (might be None)
        # Now we're at the colon
        self.consume(TokenType.COLON)
        
        # Parse upper
        upper = None
        if self.current_token().type not in (TokenType.COLON, TokenType.RBRACK):
            upper = self.parse_expression()
        
        # Parse step
        step = None
        if self.current_token().type == TokenType.COLON:
            self.consume()
            if self.current_token().type != TokenType.RBRACK:
                step = self.parse_expression()
        
        return ast.Slice(lower=lower, upper=upper, step=step)

    def _parse_call(self, func: ast.AST) -> ast.Call:
        """Parse function call with keyword argument support."""
        self.consume(TokenType.LPAR)
        args = []
        keywords = []
        
        while self.current_token().type != TokenType.RPAR:
            # Try to parse as keyword arg
            if self.current_token().type == TokenType.ID:
                # Look ahead for =
                saved_pos = self.pos
                name = self.consume(TokenType.ID).value
                
                if self.current_token().type == TokenType.EQ:
                    # It's a keyword argument
                    self.consume()
                    value = self.parse_expression()
                    keywords.append(ast.keyword(arg=name, value=value))
                else:
                    # Not a keyword, backtrack
                    self.pos = saved_pos
                    args.append(self.parse_expression())
            else:
                # Regular positional argument
                args.append(self.parse_expression())
            
            if self.current_token().type == TokenType.COMMA:
                self.consume()
        
        self.consume(TokenType.RPAR)
        return ast.Call(func=func, args=args, keywords=keywords)
    
    def parse_try(self) -> ast.Try:
        """Parse T: body [X: handler] with proper indentation handling"""
        self.consume(TokenType.MACRO_T)
        self.consume(TokenType.COLON)
        
        body = self.parse_suite()  # Unified!
        
        handlers = []
        while self.current_token().type == TokenType.MACRO_X:
            handler = self.parse_except_handler()
            if handler:
                handlers.append(handler)
        
        orelse = []
        if self.current_token().type == TokenType.MACRO_O:
            self.consume(TokenType.MACRO_O)
            self.consume(TokenType.COLON)
            orelse = self.parse_suite()

        # Check for finally clause (using J for finally, if supported)
        finalbody = []
        if self.current_token().type == TokenType.MACRO_J:
            self.consume(TokenType.MACRO_J)
            self.consume(TokenType.COLON)
            finalbody = self.parse_suite()

        # Ensure we have either handlers or finalbody for valid Try statement
        if not handlers and not finalbody:
            # Add a minimal pass handler if none exists
            handlers = [ast.ExceptHandler(type=None, name=None, body=[ast.Pass()])]

        return ast.Try(body=body, handlers=handlers, orelse=orelse, finalbody=finalbody)

    def parse_except_handler(self) -> ast.ExceptHandler:
        """Parse X: handler or X(Exception): handler with proper indentation handling"""
        self.consume(TokenType.MACRO_X)
        
        exc_type = None
        name = None
        
        if self.current_token().type == TokenType.LPAR:
            self.consume(TokenType.LPAR)
            exc_type = self.parse_expression()
            self.consume(TokenType.RPAR)
            
            # Check for 'as name'
            if self.current_token().type == TokenType.ID:
                name = self.consume().value
        
        self.consume(TokenType.COLON)
        
        body = self.parse_suite()  # Unified!
        
        return ast.ExceptHandler(type=exc_type, name=name, body=body)
    
    def parse_elif(self) -> ast.If:
        """Parse E(condition): body with chaining"""
        self.consume(TokenType.MACRO_E)
        self.consume(TokenType.LPAR)
        test = self.parse_expression()
        self.consume(TokenType.RPAR)
        self.consume(TokenType.COLON)
        
        body = self.parse_suite()  # Unified!
        
        orelse = []
        if self.current_token().type == TokenType.MACRO_E:
            orelse = [self.parse_elif()]
        elif self.current_token().type == TokenType.MACRO_O:
            self.consume(TokenType.MACRO_O)
            self.consume(TokenType.COLON)
            orelse = self.parse_suite()
        
        return ast.If(test=test, body=body, orelse=orelse)

    def parse_for(self) -> ast.For:
        """Parse F target in iter: body with proper indentation handling"""
        self.consume(TokenType.MACRO_F)
        target = self.parse_primary()
        target.ctx = ast.Store()
        self.consume(TokenType.IN)
        iter_expr = self.parse_expression()
        self.consume(TokenType.COLON)
        
        body = self.parse_suite()  # No more infinite loops!
        
        orelse = []
        if self.current_token().type == TokenType.MACRO_O:
            self.consume(TokenType.MACRO_O)
            self.consume(TokenType.COLON)
            orelse = self.parse_suite()
        
        return ast.For(target=target, iter=iter_expr, body=body, orelse=orelse)

    def parse_while(self) -> ast.While:
        """Parse W(condition): body with proper indentation handling"""
        self.consume(TokenType.MACRO_W)
        self.consume(TokenType.LPAR)
        test = self.parse_expression()
        self.consume(TokenType.RPAR)
        self.consume(TokenType.COLON)
        
        body = self.parse_suite()  # Unified!
        
        orelse = []
        if self.current_token().type == TokenType.MACRO_O:
            self.consume(TokenType.MACRO_O)
            self.consume(TokenType.COLON)
            orelse = self.parse_suite()
        
        return ast.While(test=test, body=body, orelse=orelse)

    def parse_return(self) -> ast.Return:
        """Parse R [value]"""
        self.consume(TokenType.MACRO_R)
        
        # Check if there's a return value
        if (self.current_token().type in (TokenType.NEWLINE, TokenType.EOF, TokenType.SEMI) or
            self.current_token().type == TokenType.RBRACE):
            return ast.Return(value=None)
        
        value = self.parse_expression()
        return ast.Return(value=value)
    
    def parse_delete(self) -> ast.Delete:
        """Parse D target[, target]*"""
        self.consume(TokenType.MACRO_D)
        
        targets = []
        target = self.parse_primary()
        
        # Set Del context
        if isinstance(target, ast.Name):
            target.ctx = ast.Del()
        elif isinstance(target, (ast.Attribute, ast.Subscript)):
            target.ctx = ast.Del()
        targets.append(target)
        
        while self.current_token().type == TokenType.COMMA:
            self.consume()
            target = self.parse_primary()
            if isinstance(target, ast.Name):
                target.ctx = ast.Del()
            elif isinstance(target, (ast.Attribute, ast.Subscript)):
                target.ctx = ast.Del()
            targets.append(target)
        
        return ast.Delete(targets=targets)

    def parse_with(self) -> ast.With:
        """Parse Z expr [as target]: body"""
        self.consume(TokenType.MACRO_Z)
        
        context_expr = self.parse_expression()
        optional_vars = None
        
        if self.current_token().type == TokenType.ID and self.current_token().value == "as":
            self.consume()
            optional_vars = self.parse_primary()
            optional_vars.ctx = ast.Store()
        
        self.consume(TokenType.COLON)
        body = self.parse_suite()
        
        item = ast.withitem(context_expr=context_expr, optional_vars=optional_vars)
        return ast.With(items=[item], body=body)

    def parse_raise(self) -> ast.Raise:
        """Parse H [exception] [from cause]"""
        self.consume(TokenType.MACRO_H)
        
        exc = None
        cause = None
        
        # Check if there's an exception to raise
        if (self.current_token().type not in (TokenType.NEWLINE, TokenType.EOF, TokenType.SEMI) and
            self.current_token().type != TokenType.RBRACE):
            exc = self.parse_expression()
            
            # Check for 'from' clause
            if (self.current_token().type == TokenType.ID and 
                self.current_token().value == "from"):
                self.consume()
                cause = self.parse_expression()
        
        return ast.Raise(exc=exc, cause=cause)

    def parse_print(self) -> ast.Expr:
        """Parse @ expr[, expr]*"""
        self.consume(TokenType.AT)
        
        args = []
        args.append(self.parse_expression())
        
        while self.current_token().type == TokenType.COMMA:
            self.consume()
            args.append(self.parse_expression())
        
        return ast.Expr(value=ast.Call(
            func=ast.Name(id='print', ctx=ast.Load()),
            args=args,
            keywords=[]
        ))

    def parse_inline_for(self) -> ast.Expr:
        """Parse @expr1,expr2,... as print(expr1, expr2, ...)"""
        self.consume(TokenType.AT)
        
        # Parse comma-separated expressions
        args = []
        args.append(self.parse_expression())
        
        while self.current_token().type == TokenType.COMMA:
            self.consume(TokenType.COMMA)
            args.append(self.parse_expression())
        
        return ast.Expr(value=ast.Call(
            func=ast.Name(id='print', ctx=ast.Load()),
            args=args,
            keywords=[]
        ))