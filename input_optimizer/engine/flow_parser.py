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
        """Parse a single statement"""
        token = self.current_token()
        
        # Guard against EOF
        if token.type == TokenType.EOF:
            return None
        
        # Handle macros
        if token.type == TokenType.MACRO_L:
            return self.parse_assignment()
        elif token.type == TokenType.MACRO_I:
            return self.parse_if()
        elif token.type == TokenType.MACRO_E:
            # Elif should be handled by if parser, skip as standalone
            return None
        elif token.type == TokenType.MACRO_O:
            # Else should be handled by if/elif parser, skip as standalone
            return None
        elif token.type == TokenType.MACRO_F:
            return self.parse_for()
        elif token.type == TokenType.MACRO_T:
            return self.parse_try()
        elif token.type == TokenType.MACRO_X:
            # Except should be handled by try parser, skip as standalone
            return None
        elif token.type == TokenType.MACRO_R:
            return self.parse_return()
        elif token.type == TokenType.MACRO_W:
            return self.parse_while()
        elif token.type == TokenType.AT:
            return self.parse_inline_for()
        
        # Check for assignment without macro
        if self.is_assignment():
            return self.parse_bare_assignment()
        
        # Otherwise, parse as expression statement
        try:
            expr = self.parse_expression()
            if expr:
                return ast.Expr(value=expr)
        except SyntaxError:
            # If expression parsing fails, return None to allow recovery
            return None
        
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
            return self.parse_block()
        
        # Indented block
        if self.current_token().type == TokenType.INDENT:
            self.consume(TokenType.INDENT)
            statements = []
            
            while self.current_token().type not in (TokenType.DEDENT, TokenType.EOF):
                if self.current_token().type == TokenType.NEWLINE:
                    self.consume()
                    continue
                
                # Check for control flow keywords that signal end of current suite
                if self.current_token().type in (TokenType.MACRO_E, TokenType.MACRO_O, TokenType.MACRO_X):
                    break
                    
                stmt = self.parse_statement()
                if stmt:
                    statements.append(stmt)
                else:
                    # If we can't parse a statement, safely skip the problematic token
                    if self.current_token().type not in (TokenType.DEDENT, TokenType.EOF, TokenType.NEWLINE):
                        self.consume()
            
            if self.current_token().type == TokenType.DEDENT:
                self.consume(TokenType.DEDENT)
            
            return statements or [ast.Pass()]
        
        # Single-line suite
        stmt = self.parse_statement()
        return [stmt] if stmt else [ast.Pass()]

    def _skip_newlines(self):
        while self.current_token().type == TokenType.NEWLINE:
            self.consume()

    def parse_block(self) -> List[ast.AST]:
        """Parse {statements}"""
        self.consume(TokenType.LBRACE)
        statements = []
        
        while self.current_token().type != TokenType.RBRACE and self.current_token().type != TokenType.EOF:
            # Skip newlines in braced blocks
            if self.current_token().type == TokenType.NEWLINE:
                self.consume()
                continue
                
            stmt = self.parse_statement()
            if stmt:
                statements.append(stmt)
            else:
                # If we can't parse a statement, try to skip safely
                if self.current_token().type not in (TokenType.RBRACE, TokenType.EOF, TokenType.NEWLINE):
                    self.consume()
                
            # Handle semicolons
            if self.current_token().type == TokenType.SEMI:
                self.consume()
        
        if self.current_token().type == TokenType.RBRACE:
            self.consume(TokenType.RBRACE)
        
        return statements or [ast.Pass()]
    
    def parse_expression(self) -> ast.AST:
        """Parse expression with proper precedence"""
        return self.parse_or_expr()
    
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
        left = self.parse_additive()
        
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
            comparators.append(self.parse_additive())
        
        if ops:
            return ast.Compare(left=left, ops=ops, comparators=comparators)
        
        return left
    
    def parse_primary(self) -> ast.AST:
        """Parse primary expression"""
        token = self.current_token()
        
        # Handle literals
        if token.type == TokenType.NUM:
            self.consume()
            return ast.Constant(value=float(token.value) if '.' in token.value else int(token.value))
        
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
                    self.consume()
                    args = []
                    while self.current_token().type != TokenType.RPAR:
                        args.append(self.parse_expression())
                        if self.current_token().type == TokenType.COMMA:
                            self.consume()
                    self.consume(TokenType.RPAR)
                    node = ast.Call(func=node, args=args, keywords=[])
                    
                elif self.current_token().type == TokenType.LBRACK:
                    # Subscript
                    self.consume()
                    index = self.parse_expression()
                    self.consume(TokenType.RBRACK)
                    node = ast.Subscript(value=node, slice=index, ctx=ast.Load())
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
        """Parse multiplication and division"""
        left = self.parse_unary()
        
        while self.current_token().type in (TokenType.STAR, TokenType.SLASH):
            op_token = self.consume()
            right = self.parse_unary()
            
            if op_token.type == TokenType.STAR:
                left = ast.BinOp(left=left, op=ast.Mult(), right=right)
            else:
                left = ast.BinOp(left=left, op=ast.Div(), right=right)
        
        return left
    
    def parse_unary(self) -> ast.AST:
        """Parse unary operators like - and !"""
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
        else:
            return self.parse_primary()
    
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
        
        return ast.Try(body=body, handlers=handlers, orelse=orelse, finalbody=[])
    
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