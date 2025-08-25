"""
Production-ready CAI3 to Python AST translator.
Complete pipeline with all transformers, validation, and testing.
"""

import ast
import keyword
import logging
import re
from typing import List, Dict, Optional, Tuple, Any, Union
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)

class CAI3ParseError(Exception):
    """Custom exception for CAI3 parsing errors."""
    def __init__(self, message: str, token: str = None, position: int = None):
        self.message = message
        self.token = token
        self.position = position
        super().__init__(self.format_message())
    
    def format_message(self):
        msg = self.message
        if self.token:
            msg += f"\nToken: {self.token[:100]}..."
        if self.position is not None:
            msg += f"\nPosition: {self.position}"
        return msg

@dataclass
class ParseConfig:
    """Configuration for parser behavior."""
    strict_mode: bool = False
    log_errors: bool = True
    max_recursion_depth: int = 100
    allow_triple_quotes: bool = True
    validate_output: bool = True
    must_call_methods: set = None
    
    def __post_init__(self):
        if self.must_call_methods is None:
            self.must_call_methods = {
                'exists', 'is_dir', 'is_file', 'read_text', 'read_bytes',
                'stat', 'values', 'keys', 'items', 'iterdir', 'mkdir', 'touch'
            }

class CAI3StateMachine:
    """Enhanced state machine with complete operator support."""
    
    def __init__(self, config: ParseConfig = None):
        self.config = config or ParseConfig()
        self.reset()
    
    def reset(self):
        self.depth = {'paren': 0, 'brace': 0, 'bracket': 0}
        self.in_string = None
        self.in_triple = False
        self.escape_next = False
    
    def find_token_at_depth(self, s: str, token: str, start: int = 0) -> int:
        """Find multi-character token at depth 0."""
        depth = {'paren': 0, 'brace': 0, 'bracket': 0}
        in_str = None
        in_triple = False
        esc = False
        i = start
        n = len(token)
        
        while i <= len(s) - n:
            ch = s[i]
            
            # Handle escapes
            if esc:
                esc = False
                i += 1
                continue
            
            if in_str and ch == '\\':
                esc = True
                i += 1
                continue
            
            # Handle triple quotes
            if self.config.allow_triple_quotes and i + 2 < len(s):
                triple = s[i:i+3]
                if triple in ('"""', "'''"):
                    if not in_str:
                        in_str = triple[0]
                        in_triple = True
                        i += 3
                        continue
                    elif in_triple and in_str == triple[0]:
                        in_str = None
                        in_triple = False
                        i += 3
                        continue
            
            # Handle regular quotes
            if not in_triple and ch in ('"', "'"):
                if not in_str:
                    in_str = ch
                elif ch == in_str:
                    in_str = None
                i += 1
                continue
            
            if in_str:
                i += 1
                continue
            
            # Track depth
            if ch == '(':
                depth['paren'] += 1
            elif ch == ')':
                depth['paren'] = max(0, depth['paren'] - 1)
            elif ch == '{':
                depth['brace'] += 1
            elif ch == '}':
                depth['brace'] = max(0, depth['brace'] - 1)
            elif ch == '[':
                depth['bracket'] += 1
            elif ch == ']':
                depth['bracket'] = max(0, depth['bracket'] - 1)
            
            # Check for token at depth 0
            if all(d == 0 for d in depth.values()) and s[i:i+n] == token:
                return i
            
            i += 1
        
        return -1
    
    def find_matching(self, content: str, start: int, open_ch: str, close_ch: str) -> int:
        """Find matching bracket with complete string awareness."""
        if start >= len(content) or content[start] != open_ch:
            return -1
        
        depth = 1
        i = start + 1
        in_str = None
        in_triple = False
        esc = False
        
        while i < len(content) and depth > 0:
            ch = content[i]
            
            # Handle escapes
            if esc:
                esc = False
                i += 1
                continue
            
            if ch == '\\' and in_str:
                esc = True
                i += 1
                continue
            
            # Handle triple quotes
            if self.config.allow_triple_quotes and i + 2 < len(content):
                triple = content[i:i+3]
                if triple in ('"""', "'''"):
                    if not in_str:
                        in_str = triple[0]
                        in_triple = True
                        i += 3
                        continue
                    elif in_triple and in_str == triple[0]:
                        in_str = None
                        in_triple = False
                        i += 3
                        continue
            
            # Handle regular quotes
            if not in_triple and ch in ('"', "'"):
                if not in_str:
                    in_str = ch
                elif ch == in_str:
                    in_str = None
                i += 1
                continue
            
            if in_str:
                i += 1
                continue
            
            # Track depth
            if ch == open_ch:
                depth += 1
            elif ch == close_ch:
                depth -= 1
            
            i += 1
        
        if depth != 0 and self.config.strict_mode:
            raise CAI3ParseError(f"Unmatched {open_ch}", content[start:start+50], start)
        
        return i - 1 if depth == 0 else -1
    
    def tokenize(self, content: str) -> List[str]:
        """Tokenize with complete nesting support."""
        self.reset()
        tokens = []
        current = []
        
        i = 0
        while i < len(content):
            ch = content[i]
            
            # Handle escapes
            if self.escape_next:
                current.append(ch)
                self.escape_next = False
                i += 1
                continue
            
            if ch == '\\' and self.in_string:
                current.append(ch)
                self.escape_next = True
                i += 1
                continue
            
            # Handle triple quotes
            if self.config.allow_triple_quotes and i + 2 < len(content):
                triple = content[i:i+3]
                if triple in ('"""', "'''"):
                    if not self.in_string:
                        self.in_string = triple[0]
                        self.in_triple = True
                        current.extend(triple)
                        i += 3
                        continue
                    elif self.in_triple and self.in_string == triple[0]:
                        current.extend(triple)
                        self.in_string = None
                        self.in_triple = False
                        i += 3
                        continue
            
            # Handle regular quotes
            if not self.in_triple and ch in ('"', "'"):
                if not self.in_string:
                    self.in_string = ch
                elif ch == self.in_string:
                    self.in_string = None
                current.append(ch)
                i += 1
                continue
            
            if self.in_string:
                current.append(ch)
                i += 1
                continue
            
            # Track nesting
            if ch == '(':
                self.depth['paren'] += 1
            elif ch == ')':
                self.depth['paren'] = max(0, self.depth['paren'] - 1)
            elif ch == '{':
                self.depth['brace'] += 1
            elif ch == '}':
                self.depth['brace'] = max(0, self.depth['brace'] - 1)
            elif ch == '[':
                self.depth['bracket'] += 1
            elif ch == ']':
                self.depth['bracket'] = max(0, self.depth['bracket'] - 1)
            
            # Split on semicolon at depth 0
            if ch == ';' and all(d == 0 for d in self.depth.values()):
                if current:
                    tokens.append(''.join(current).strip())
                    current = []
            else:
                current.append(ch)
            
            i += 1
        
        # Add remaining
        if current:
            tokens.append(''.join(current).strip())
        
        return tokens

@dataclass
class ParseContext:
    """Complete parse context."""
    flow_compiler: Any
    cai3_map: Any
    cai3_full: Any
    method_cid: str
    seen_names: set
    chain_aliases: Dict[str, str]
    pools: Dict[str, str]
    config: ParseConfig
    
    def setup_flow_compiler(self):
        """Initialize flow compiler with context."""
        if hasattr(self.flow_compiler, 'set_chain_aliases') and self.chain_aliases:
            self.flow_compiler.set_chain_aliases(self.chain_aliases)
        if hasattr(self.flow_compiler, 'set_pools') and self.pools:
            self.flow_compiler.set_pools(self.pools)
        if hasattr(self.cai3_full, 'hash_to_value'):
            if hasattr(self.flow_compiler, 'set_hash_mapping'):
                self.flow_compiler.set_hash_mapping(self.cai3_full.hash_to_value)

class CAI3Parser:
    """Complete parser with recursion control."""
    
    def __init__(self, context: ParseContext):
        self.ctx = context
        self.ctx.setup_flow_compiler()
        self.state = CAI3StateMachine(self.ctx.config)
        self.recursion_depth = 0
    
    def parse(self, content: str) -> List[ast.AST]:
        """Parse with proper recursion control."""
        # Check recursion depth
        self.recursion_depth += 1
        if self.recursion_depth > self.ctx.config.max_recursion_depth:
            self.recursion_depth -= 1
            if self.ctx.config.strict_mode:
                raise CAI3ParseError(f"Max recursion depth {self.ctx.config.max_recursion_depth} exceeded")
            logger.warning(f"Max recursion depth exceeded")
            return [ast.Pass()]
        
        try:
            tokens = self.state.tokenize(content)
            statements = []
            i = 0
            
            while i < len(tokens):
                token = tokens[i]
                
                try:
                    # Handle try-except blocks with multiple handlers
                    if token.startswith('T{'):
                        # Look for complete try-except-finally block
                        try_token = token
                        j = i + 1
                        # Collect all X(...){...} and F{...} tokens that follow
                        while j < len(tokens) and (tokens[j].startswith('X(') or tokens[j].startswith('F{')):
                            try_token += ';' + tokens[j]
                            j += 1
                        
                        try_stmt = self.parse_try(try_token)
                        statements.append(try_stmt)
                        i = j  # Skip the collected tokens
                        continue
                    
                    # Skip standalone X(...) or F{...} tokens (already handled above)
                    if token.startswith('X(') or token.startswith('F{'):
                        logger.warning(f"Standalone exception handler or finally block found at position {i}, skipping")
                        i += 1
                        continue
                    
                    # Handle if/elif/else chains
                    if token.startswith('I('):
                        base_if = self.parse_if(token)
                        i += 1
                        
                        # Collect elif chain
                        current = base_if
                        while i < len(tokens) and tokens[i].startswith('E('):
                            elif_node = self.parse_elif(tokens[i])
                            current.orelse = [elif_node]
                            current = elif_node
                            i += 1
                        
                        # Collect else
                        if i < len(tokens) and (tokens[i].startswith('O:') or tokens[i].startswith('O{')):
                            current.orelse = self.parse_else(tokens[i])
                            i += 1
                        
                        statements.append(base_if)
                        continue
                    
                    # Skip standalone else
                    if token.startswith('O:') or token.startswith('O{'):
                        logger.warning(f"Standalone else found at position {i}, skipping")
                        i += 1
                        continue
                    
                    # Normal statement
                    stmt = self.parse_token(token)
                    if stmt:
                        statements.append(stmt)
                    i += 1
                    
                except CAI3ParseError as e:
                    if self.ctx.config.strict_mode:
                        raise
                    logger.error(f"Parse error at token {i}: {e}")
                    statements.append(ast.Pass())
                    i += 1
                except Exception as e:
                    if self.ctx.config.strict_mode:
                        raise CAI3ParseError(f"Unexpected error: {e}", token)
                    logger.error(f"Unexpected error parsing token {i}: {e}")
                    statements.append(ast.Pass())
                    i += 1
            
            return statements
            
        finally:
            self.recursion_depth -= 1
    
    def parse_token(self, token: str) -> Optional[ast.AST]:
        """Parse single token."""
        if not token or token == '_':
            return ast.Pass()
        
        # Try-except
        if token.startswith('T{'):
            return self.parse_try(token)
        
        # For-loop - improved detection
        if token.startswith('@'):
            return self.parse_for(token)
        
        # Control flow
        if token.startswith('I('):
            return self.parse_if(token)
        elif token.startswith('W('):
            return self.parse_while(token)
        
        # Return
        if token == 'R' or token == 'RN':
            return ast.Return(value=None)
        elif token == 'RT':
            return ast.Return(value=ast.Constant(value=True))
        elif token == 'RF':
            return ast.Return(value=ast.Constant(value=False))
        elif token.startswith('R'):
            value_str = token[1:]
            value = self.parse_expression_or_ternary(value_str)
            return ast.Return(value=value)
        
        # Break/Continue
        if token == 'B':
            return ast.Break()
        if token == 'K':
            return ast.Continue()
        
        # Assignment
        if self.is_assignment(token):
            return self.parse_assignment(token)
        
        # Expression
        return self.parse_expression(token)
    
    def is_assignment(self, token: str) -> bool:
        """Check if token is assignment using depth-aware search."""
        # Check augmented assignments
        aug_ops = ['+=', '-=', '*=', '/=', '//=', '%=', '**=',
                   '&=', '|=', '^=', '>>=', '<<=', '@=']
        
        for op in aug_ops:
            if self.state.find_token_at_depth(token, op) != -1:
                return True
        
        # Check walrus operator
        if self.state.find_token_at_depth(token, ':=') != -1:
            return True
        
        # Check regular assignment
        eq_pos = self.state.find_token_at_depth(token, '=')
        if eq_pos == -1:
            return False
        
        # Ensure it's not comparison
        if eq_pos > 0 and token[eq_pos - 1] in '!<>':
            return False
        if eq_pos < len(token) - 1 and token[eq_pos + 1] == '=':
            return False
        
        return True
    
    def parse_try(self, token: str) -> ast.Try:
        """Parse try with proper recursion."""
        # Find try body
        body_close = self.state.find_matching(token, 1, '{', '}')
        if body_close == -1:
            if self.ctx.config.strict_mode:
                raise CAI3ParseError("Unmatched brace in try statement", token)
            return ast.Pass()
        
        body_str = token[2:body_close]
        body_stmts = self.parse(body_str)  # Use same parser instance
        
        # Parse handlers and finally
        handlers = []
        finalbody = []
        i = body_close + 1
        
        while i < len(token):
            if token[i:i+1] == 'X':
                handler, i = self.parse_exception_handler(token, i)
                if handler:
                    handlers.append(handler)
            elif token[i:i+2] == 'F{':
                f_close = self.state.find_matching(token, i + 1, '{', '}')
                if f_close != -1:
                    finally_str = token[i + 2:f_close]
                    finalbody = self.parse(finally_str)  # Use same parser instance
                    i = f_close + 1
                else:
                    i += 1
            else:
                i += 1
        
        return ast.Try(
            body=body_stmts or [ast.Pass()],
            handlers=handlers,
            orelse=[],
            finalbody=finalbody
        )
    
    def parse_exception_handler(self, token: str, start: int) -> Tuple[Optional[ast.ExceptHandler], int]:
        """Parse exception handler with proper 'as' detection."""
        i = start + 1  # Skip 'X'
        exc_type = None
        exc_name = None
        
        # Parse exception type/name
        if i < len(token) and token[i] == '(':
            paren_close = self.state.find_matching(token, i, '(', ')')
            if paren_close > i:
                exc_spec = token[i + 1:paren_close]
                
                # Handle 'as' binding with word boundaries
                as_match = re.search(r'\bas\b', exc_spec)
                if as_match:
                    type_str = exc_spec[:as_match.start()].strip()
                    exc_name = exc_spec[as_match.end():].strip()
                else:
                    type_str = exc_spec.strip()
                
                # Parse type
                if type_str and type_str != 'E':
                    try:
                        # Handle tuple of exceptions
                        if ',' in type_str:
                            exc_type = self.ctx.flow_compiler._parse_expression_string(f"({type_str})")
                            if isinstance(exc_type, ast.Tuple) and len(exc_type.elts) == 1:
                                exc_type = exc_type.elts[0]
                        else:
                            exc_type = self.ctx.flow_compiler._parse_expression_string(type_str)
                    except:
                        logger.warning(f"Failed to parse exception type: {type_str}")
                
                i = paren_close + 1
        
        # Find handler body
        if i < len(token) and token[i] == '{':
            body_close = self.state.find_matching(token, i, '{', '}')
            if body_close != -1:
                body_str = token[i + 1:body_close]
                body_stmts = self.parse(body_str)  # Use same parser instance
                
                return ast.ExceptHandler(
                    type=exc_type,
                    name=exc_name,
                    body=body_stmts or [ast.Pass()]
                ), body_close + 1
        
        return None, i
    
    def parse_for(self, token: str) -> ast.For:
        """Parse for loop with proper target parsing."""
        # For CAI3 for loop format: @target,iterator:{body}
        # We need to find the comma that separates target from iterator, not commas inside parentheses
        
        # Start after the @
        i = 1
        paren_depth = 0
        comma_pos = -1
        
        # Find the comma at depth 0 (not inside parentheses)
        while i < len(token):
            ch = token[i]
            if ch == '(':
                paren_depth += 1
            elif ch == ')':
                paren_depth -= 1
            elif ch == ',' and paren_depth == 0:
                comma_pos = i
                break
            i += 1
        
        brace = token.find('{', comma_pos + 1 if comma_pos != -1 else 1)
        
        if comma_pos == -1 or brace == -1:
            if self.ctx.config.strict_mode:
                raise CAI3ParseError("Invalid for loop structure", token)
            logger.warning(f"Invalid for loop structure: {token}")
            return ast.Pass()
        
        target_str = token[1:comma_pos].strip()
        iter_str = token[comma_pos + 1:brace].strip()
        
        # Remove trailing colon from iterator if present
        if iter_str.endswith(':'):
            iter_str = iter_str[:-1].strip()
        
        # Parse target - handle tuple destructuring properly
        if target_str:
            try:
                # Handle tuple destructuring like (a,b)
                if target_str.startswith('(') and target_str.endswith(')'):
                    target_str_inner = target_str[1:-1]
                    if ',' in target_str_inner:
                        # Parse as tuple
                        elements = [name.strip() for name in target_str_inner.split(',')]
                        target = ast.Tuple(
                            elts=[ast.Name(id=elem, ctx=ast.Store()) for elem in elements if elem],
                            ctx=ast.Store()
                        )
                    else:
                        target = ast.Name(id=target_str_inner, ctx=ast.Store())
                else:
                    target = self.ctx.flow_compiler._parse_expression_string(target_str)
                    self.set_store_context(target)
            except Exception as e:
                logger.warning(f"Failed to parse for loop target: {target_str}, error: {e}")
                target = ast.Name(id='item', ctx=ast.Store())
        else:
            target = self.infer_loop_target(iter_str)
        
        # Parse iterator
        try:
            iter_expr = self.ctx.flow_compiler._parse_expression_string(iter_str)
        except Exception as e:
            if self.ctx.config.strict_mode:
                raise CAI3ParseError(f"Failed to parse iterator: {iter_str}")
            logger.warning(f"Failed to parse iterator: {iter_str}, error: {e}")
            iter_expr = ast.Name(id='items', ctx=ast.Load())
        
        # Parse body
        body_close = self.state.find_matching(token, brace, '{', '}')
        if body_close == -1:
            # Try manual search
            body_close = token.rfind('}')
        
        if body_close == -1:
            if self.ctx.config.strict_mode:
                raise CAI3ParseError("Unmatched brace in for loop body", token)
            logger.warning(f"Unmatched brace in for loop body: {token}")
            return ast.Pass()
        
        body_str = token[brace + 1:body_close]
        body_stmts = self.parse(body_str)  # Use same parser instance
        
        return ast.For(
            target=target,
            iter=iter_expr,
            body=body_stmts or [ast.Pass()],
            orelse=[]
        )
    
    def parse_if(self, token: str) -> ast.If:
        """Parse if statement."""
        # Extract condition
        paren_start = token.find('(')
        paren_close = self.state.find_matching(token, paren_start, '(', ')')
        
        if paren_close == -1:
            if self.ctx.config.strict_mode:
                raise CAI3ParseError("Unmatched parenthesis in if condition", token)
            return ast.Pass()
        
        cond_str = token[paren_start + 1:paren_close]
        try:
            condition = self.ctx.flow_compiler._parse_expression_string(cond_str)
        except:
            if self.ctx.config.strict_mode:
                raise CAI3ParseError(f"Failed to parse if condition: {cond_str}")
            logger.warning(f"Failed to parse if condition: {cond_str}")
            condition = ast.Constant(value=True)
        
        # Find body
        colon = token.find(':', paren_close)
        if colon == -1:
            if self.ctx.config.strict_mode:
                raise CAI3ParseError("Missing colon in if statement", token)
            return ast.Pass()
        
        # Parse body
        body_start = colon + 1
        body_stmts = []
        
        if body_start < len(token):
            if token[body_start] == '{':
                body_close = self.state.find_matching(token, body_start, '{', '}')
                if body_close != -1:
                    body_str = token[body_start + 1:body_close]
                    body_stmts = self.parse(body_str)  # Use same parser instance
            else:
                # Single statement
                body_str = token[body_start:].strip()
                if body_str:
                    stmt = self.parse_token(body_str)
                    if stmt:
                        body_stmts = [stmt]
        
        return ast.If(
            test=condition,
            body=body_stmts or [ast.Pass()],
            orelse=[]
        )
    
    def parse_elif(self, token: str) -> ast.If:
        """Parse elif as nested if."""
        token_as_if = 'I' + token[1:]
        return self.parse_if(token_as_if)
    
    def parse_else(self, token: str) -> List[ast.AST]:
        """Parse else block."""
        if token.startswith('O:'):
            body_start = 2
        elif token.startswith('O{'):
            body_start = 1
        else:
            return [ast.Pass()]
        
        if body_start < len(token):
            if token[body_start] == '{':
                body_close = self.state.find_matching(token, body_start, '{', '}')
                if body_close != -1:
                    body_str = token[body_start + 1:body_close]
                    return self.parse(body_str)  # Use same parser instance
            else:
                body_str = token[body_start:].strip()
                if body_str:
                    stmt = self.parse_token(body_str)
                    return [stmt] if stmt else [ast.Pass()]
        
        return [ast.Pass()]
    
    def parse_while(self, token: str) -> ast.While:
        """Parse while with single-line and braced bodies."""
        # Extract condition
        paren_start = token.find('(')
        paren_close = self.state.find_matching(token, paren_start, '(', ')')
        
        if paren_close == -1:
            if self.ctx.config.strict_mode:
                raise CAI3ParseError("Unmatched parenthesis in while condition", token)
            return ast.Pass()
        
        cond_str = token[paren_start + 1:paren_close]
        try:
            condition = self.ctx.flow_compiler._parse_expression_string(cond_str)
        except:
            if self.ctx.config.strict_mode:
                raise CAI3ParseError(f"Failed to parse while condition: {cond_str}")
            logger.warning(f"Failed to parse while condition: {cond_str}")
            condition = ast.Constant(value=True)
        
        # Find body
        colon = token.find(':', paren_close)
        if colon == -1:
            if self.ctx.config.strict_mode:
                raise CAI3ParseError("Missing colon in while statement", token)
            return ast.Pass()
        
        # Parse body
        body_start = colon + 1
        body_stmts = []
        
        if body_start < len(token):
            if token[body_start] == '{':
                body_close = self.state.find_matching(token, body_start, '{', '}')
                if body_close != -1:
                    body_str = token[body_start + 1:body_close]
                    body_stmts = self.parse(body_str)  # Use same parser instance
            else:
                body_str = token[body_start:].strip()
                if body_str:
                    stmt = self.parse_token(body_str)
                    if stmt:
                        body_stmts = [stmt]
        
        return ast.While(
            test=condition,
            body=body_stmts or [ast.Pass()],
            orelse=[]
        )
    
    def parse_assignment(self, token: str) -> ast.AST:
        """Parse all assignment forms with validation."""
        # Augmented assignments
        aug_ops = {
            '+=': ast.Add(), '-=': ast.Sub(), '*=': ast.Mult(), '/=': ast.Div(),
            '//=': ast.FloorDiv(), '%=': ast.Mod(), '**=': ast.Pow(),
            '&=': ast.BitAnd(), '|=': ast.BitOr(), '^=': ast.BitXor(),
            '>>=': ast.RShift(), '<<=': ast.LShift(), '@=': ast.MatMult()
        }
        
        for op_str, op_ast in aug_ops.items():
            pos = self.state.find_token_at_depth(token, op_str)
            if pos != -1:
                target_str = token[:pos].strip()
                value_str = token[pos + len(op_str):].strip()
                
                try:
                    target = self.ctx.flow_compiler._parse_expression_string(target_str)
                    if not self._is_assignable(target):
                        if self.ctx.config.strict_mode:
                            raise CAI3ParseError(f"Invalid assignment target: {target_str}")
                        logger.warning(f"Invalid assignment target: {target_str}")
                        return ast.Pass()
                    
                    self.set_store_context(target)
                    value = self.parse_expression_or_ternary(value_str)
                    return ast.AugAssign(target=target, op=op_ast, value=value)
                except:
                    if self.ctx.config.strict_mode:
                        raise CAI3ParseError(f"Failed to parse augmented assignment: {token}")
                    logger.warning(f"Failed to parse augmented assignment: {token}")
                    return ast.Pass()
        
        # Walrus operator
        walrus_pos = self.state.find_token_at_depth(token, ':=')
        if walrus_pos != -1:
            target_str = token[:walrus_pos].strip()
            value_str = token[walrus_pos + 2:].strip()
            
            # Validate walrus target
            if not re.match(r'^[A-Za-z_]\w*$', target_str):
                if self.ctx.config.strict_mode:
                    raise CAI3ParseError(f"Invalid walrus target (must be simple name): {target_str}")
                logger.warning(f"Invalid walrus target: {target_str}")
                return ast.Pass()
            
            try:
                target = ast.Name(id=target_str, ctx=ast.Store())
                value = self.parse_expression_or_ternary(value_str)
                return ast.NamedExpr(target=target, value=value)
            except:
                if self.ctx.config.strict_mode:
                    raise CAI3ParseError(f"Failed to parse walrus operator: {token}")
                logger.warning(f"Failed to parse walrus operator: {token}")
                return ast.Pass()
        
        # Regular assignment
        eq_pos = self.state.find_token_at_depth(token, '=')
        if eq_pos != -1:
            target_str = token[:eq_pos].strip()
            value_str = token[eq_pos + 1:].strip()
            
            try:
                target = self.ctx.flow_compiler._parse_expression_string(target_str)
                if not self._is_assignable(target):
                    if self.ctx.config.strict_mode:
                        raise CAI3ParseError(f"Invalid assignment target: {target_str}")
                    logger.warning(f"Invalid assignment target: {target_str}")
                    return ast.Pass()
                
                self.set_store_context(target)
                value = self.parse_expression_or_ternary(value_str)
                return ast.Assign(targets=[target], value=value)
            except Exception as e:
                if self.ctx.config.strict_mode:
                    raise CAI3ParseError(f"Failed to parse assignment: {e}", token)
                logger.warning(f"Failed to parse assignment: {token}")
                return ast.Pass()
        
        return ast.Pass()
    
    def _is_assignable(self, target: ast.AST) -> bool:
        """Check if target is valid for assignment."""
        return isinstance(target, (ast.Name, ast.Attribute, ast.Subscript, 
                                 ast.Tuple, ast.List, ast.Starred))
    
    def parse_expression(self, token: str) -> ast.AST:
        """Parse expression statement."""
        try:
            expr = self.parse_expression_or_ternary(token)
            return ast.Expr(value=expr)
        except Exception as e:
            if self.ctx.config.strict_mode:
                raise CAI3ParseError(f"Failed to parse expression: {e}", token)
            logger.warning(f"Failed to parse expression: {token}")
            return ast.Pass()
    
    def parse_expression_or_ternary(self, s: str) -> ast.AST:
        """Parse expression with CAI3 ternary support."""
        # Check for CAI3 ternary
        q_pos = self.state.find_token_at_depth(s, '?')
        
        if q_pos == -1:
            # No ternary
            return self.ctx.flow_compiler._parse_expression_string(s)
        
        # Extract condition
        cond_str = s[:q_pos]
        if cond_str.startswith('(') and cond_str.endswith(')'):
            cond_str = cond_str[1:-1]
        
        # Parse branches
        rest = s[q_pos + 1:]
        
        if rest.startswith('{'):
            true_close = self.state.find_matching(rest, 0, '{', '}')
            if true_close == -1:
                return self.ctx.flow_compiler._parse_expression_string(s)
            
            true_str = rest[1:true_close]
            rest2 = rest[true_close + 1:]
            
            if not rest2 or rest2[0] != ':':
                return self.ctx.flow_compiler._parse_expression_string(s)
            
            rest2 = rest2[1:]
            
            if rest2.startswith('{'):
                false_close = self.state.find_matching(rest2, 0, '{', '}')
                false_str = rest2[1:false_close] if false_close != -1 else rest2
            else:
                false_str = rest2
        else:
            colon_pos = self.state.find_token_at_depth(rest, ':')
            if colon_pos == -1:
                return self.ctx.flow_compiler._parse_expression_string(s)
            
            true_str = rest[:colon_pos]
            false_str = rest[colon_pos + 1:]
        
        # Parse all parts (recursive for nested ternaries)
        try:
            test = self.ctx.flow_compiler._parse_expression_string(cond_str)
            body = self.parse_expression_or_ternary(true_str)
            orelse = self.parse_expression_or_ternary(false_str)
            return ast.IfExp(test=test, body=body, orelse=orelse)
        except:
            return self.ctx.flow_compiler._parse_expression_string(s)
    
    def set_store_context(self, node: ast.AST):
        """Recursively set Store context."""
        if isinstance(node, ast.Name):
            node.ctx = ast.Store()
        elif isinstance(node, (ast.Tuple, ast.List)):
            for elt in node.elts:
                self.set_store_context(elt)
        elif isinstance(node, (ast.Attribute, ast.Subscript)):
            node.ctx = ast.Store()
        elif isinstance(node, ast.Starred):
            node.ctx = ast.Store()
            if hasattr(node, 'value'):
                self.set_store_context(node.value)
    
    def infer_loop_target(self, iter_str: str) -> ast.AST:
        """Infer loop target from parsed iterator AST."""
        try:
            iter_ast = self.ctx.flow_compiler._parse_expression_string(iter_str)
            
            if isinstance(iter_ast, ast.Call) and isinstance(iter_ast.func, ast.Attribute):
                method = iter_ast.func.attr
                
                if method in ('items', 'it'):
                    return ast.Tuple(
                        elts=[
                            ast.Name(id='key', ctx=ast.Store()),
                            ast.Name(id='value', ctx=ast.Store())
                        ],
                        ctx=ast.Store()
                    )
                elif method in ('keys', 'ke'):
                    return ast.Name(id='key', ctx=ast.Store())
                elif method in ('values', 'va'):
                    return ast.Name(id='value', ctx=ast.Store())
        except:
            pass
        
        return ast.Name(id='item', ctx=ast.Store())

# Transformer classes
class DeminifyTransformer(ast.NodeTransformer):
    """Deminify compressed names."""
    
    def __init__(self, name_map: Dict[str, str], chain_aliases: Dict[str, str]):
        self.name_map = name_map
        self.chain_aliases = chain_aliases or {}
    
    def visit_Name(self, node):
        if node.id in self.name_map:
            node.id = self.name_map[node.id]
        return node
    
    def visit_Call(self, node):
        # Handle chain aliases in calls
        if isinstance(node.func, ast.Name) and node.func.id in self.chain_aliases:
            chain = self.chain_aliases[node.func.id]
            parts = chain.split('.')
            
            if parts:
                result = ast.Name(id=parts[0], ctx=ast.Load())
                for part in parts[1:]:
                    result = ast.Attribute(value=result, attr=part, ctx=ast.Load())
                node.func = result
        
        return self.generic_visit(node)

class CallNormalizer(ast.NodeTransformer):
    """Add calls where needed with configurable methods."""
    
    def __init__(self, must_call_methods=None):
        self.must_call = must_call_methods or {
            'exists', 'is_dir', 'is_file', 'read_text', 'read_bytes',
            'stat', 'values', 'keys', 'items', 'iterdir', 'mkdir', 'touch'
        }
        self.stack = []
    
    def visit(self, node):
        self.stack.append(node)
        result = super().visit(node)
        self.stack.pop()
        return result
    
    def visit_Attribute(self, node):
        node = self.generic_visit(node)
        
        if node.attr not in self.must_call:
            return node
        
        # Check if already called
        parent = self.stack[-2] if len(self.stack) > 1 else None
        if isinstance(parent, ast.Call):
            if self.nodes_equal(parent.func, node):
                return node
        
        # Check context
        if self.needs_call(node):
            return ast.Call(func=node, args=[], keywords=[])
        
        return node
    
    def nodes_equal(self, a, b):
        """Structural comparison."""
        return ast.dump(a, include_attributes=False) == ast.dump(b, include_attributes=False)
    
    def needs_call(self, node):
        """Check if node needs to be called."""
        for parent in reversed(self.stack[:-1]):
            # Conditionals and assertions
            if isinstance(parent, (ast.If, ast.While, ast.Assert)):
                return True
            
            # Return context
            if isinstance(parent, ast.Return):
                return True
            
            # Boolean contexts
            if isinstance(parent, (ast.BoolOp, ast.UnaryOp, ast.Compare)):
                return True
            
            # Expression statement
            if isinstance(parent, ast.Expr):
                return True
            
            # Iteration
            if isinstance(parent, ast.For) and parent.iter is node:
                return True
            
            # Comprehensions
            if isinstance(parent, (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)):
                for gen in parent.generators:
                    if gen.iter is node:
                        return True
            
            # Comprehension generator
            if isinstance(parent, ast.comprehension) and parent.iter is node:
                return True
        
        return False

class IdentifierSanitizer(ast.NodeTransformer):
    """Sanitize identifiers for entire function."""
    
    def __init__(self, seen_names=None):
        self.seen = seen_names or set()
        self.renames = {}
    
    def visit_FunctionDef(self, node):
        node.name = self.sanitize(node.name, is_def=True)
        
        for arg in node.args.args:
            arg.arg = self.sanitize(arg.arg, is_def=True)
        
        self.generic_visit(node)
        return node
    
    def visit_Name(self, node):
        if node.id in self.renames:
            node.id = self.renames[node.id]
        elif not self.is_valid_identifier(node.id):
            clean = self.sanitize(node.id, isinstance(node.ctx, ast.Store))
            self.renames[node.id] = clean
            node.id = clean
        
        return node
    
    def is_valid_identifier(self, name: str) -> bool:
        return name.isidentifier() and not keyword.iskeyword(name)
    
    def sanitize(self, name: str, is_def=False) -> str:
        import re
        
        clean = re.sub(r'[^a-zA-Z0-9_]', '_', name)
        
        if not clean or clean[0].isdigit():
            clean = 'v_' + clean
        
        if keyword.iskeyword(clean):
            clean = clean + '_'
        
        if is_def and clean in self.seen:
            base = clean
            i = 2
            while f"{base}_{i}" in self.seen:
                i += 1
            clean = f"{base}_{i}"
        
        if is_def:
            self.seen.add(clean)
        
        return clean

class ASTTransformPipeline:
    """Apply all transformations to complete function."""
    
    def __init__(self, context: ParseContext):
        self.ctx = context
    
    def transform(self, func_ast: ast.FunctionDef) -> ast.FunctionDef:
        """Single-pass transformation."""
        
        # Build name map
        name_map = {}
        prefix = f"{self.ctx.method_cid}:"
        
        if hasattr(self.ctx.cai3_map, 'name_map'):
            for key, value in self.ctx.cai3_map.name_map.items():
                if key.startswith(prefix):
                    short = key[len(prefix):]
                    name_map[short] = value
        
        # Apply transformations
        func_ast = DeminifyTransformer(name_map, self.ctx.chain_aliases).visit(func_ast)
        func_ast = CallNormalizer(self.ctx.config.must_call_methods).visit(func_ast)
        func_ast = IdentifierSanitizer(self.ctx.seen_names).visit(func_ast)
        
        ast.fix_missing_locations(func_ast)
        
        return func_ast

def validate_function(func_ast: ast.FunctionDef, config: ParseConfig = None):
    """Validate entire function."""
    config = config or ParseConfig()
    
    module = ast.Module(body=[func_ast], type_ignores=[])
    ast.fix_missing_locations(module)
    
    try:
        compile(module, '<cai3>', 'exec')
    except SyntaxError as e:
        if config.strict_mode:
            raise CAI3ParseError(f"Function validation failed: {e}")
        logger.error(f"Function validation failed: {e}")

# Helper functions
def _create_flow_compiler(cai3_map, cai3_full):
    """Create flow compiler instance."""
    from .flow_language import FLOWCompiler
    
    # Extract name mapping from cai3_map if available
    name_map = {}
    if hasattr(cai3_map, 'name_map'):
        name_map = cai3_map.name_map or {}
    
    # Create compiler instance with appropriate settings
    compiler = FLOWCompiler(
        name_map=name_map,
        dense_mode=True,
        pool_constants=True,
        ascii_ops=True,
        no_spaces=False,
        inline_blocks=False,
        alias_chains=True,
        strict_mode=True
    )
    
    # Set up pools if available from cai3_full
    if hasattr(cai3_full, 'pools') and cai3_full.pools:
        compiler.set_pools(cai3_full.pools)
    
    # Set up hash mapping if available
    if hasattr(cai3_full, 'hash_to_value') and cai3_full.hash_to_value:
        compiler.set_hash_mapping(cai3_full.hash_to_value)
    
    return compiler

def _build_arguments(method_node, cai3_map):
    """Build function arguments."""
    # Extract parameters from method_node
    params = []
    if hasattr(method_node, 'params'):
        params = method_node.params
    elif hasattr(method_node, 'signature'):
        # Parse signature
        sig = method_node.signature
        if '(' in sig and ')' in sig:
            param_str = sig[sig.find('(') + 1:sig.find(')')]
            if param_str:
                params = [p.strip() for p in param_str.split(',')]
    
    args = []
    for param in params:
        # Sanitize parameter name
        clean_param = re.sub(r'[^a-zA-Z0-9_]', '_', param)
        if not clean_param or clean_param[0].isdigit():
            clean_param = 'p_' + clean_param
        if keyword.iskeyword(clean_param):
            clean_param = clean_param + '_'
        args.append(ast.arg(arg=clean_param, annotation=None))
    
    return ast.arguments(
        posonlyargs=[],
        args=args,
        kwonlyargs=[],
        kw_defaults=[],
        defaults=[]
    )

# Main entry point
def translate_method(method_node, body_content: str, cai3_map, cai3_full, 
                    chain_aliases=None, pools=None, config=None):
    """Translate complete method with full pipeline."""
    config = config or ParseConfig()
    
    ctx = ParseContext(
        flow_compiler=_create_flow_compiler(cai3_map, cai3_full),
        cai3_map=cai3_map,
        cai3_full=cai3_full,
        method_cid=getattr(method_node, 'cid', 'unknown'),
        seen_names=set(),
        chain_aliases=chain_aliases or {},
        pools=pools or {},
        config=config
    )
    
    parser = CAI3Parser(ctx)
    body_stmts = parser.parse(body_content)
    
    # Build function
    func_ast = ast.FunctionDef(
        name=getattr(method_node, 'name', 'unknown_method'),
        args=_build_arguments(method_node, cai3_map),
        body=body_stmts or [ast.Pass()],
        decorator_list=[],
        returns=None
    )
    
    # Transform
    pipeline = ASTTransformPipeline(ctx)
    func_ast = pipeline.transform(func_ast)
    
    # Validate
    if config.validate_output:
        validate_function(func_ast, config)
    
    return func_ast

# Test infrastructure
import unittest

class TestCAI3Parser(unittest.TestCase):
    """Comprehensive test suite."""
    
    def setUp(self):
        """Setup test context."""
        class MockCompiler:
            def _parse_expression_string(self, s):
                try:
                    # Handle special cases for test expressions
                    if s == 'items':
                        return ast.Name(id='items', ctx=ast.Load())
                    elif s == '(a,b)':
                        return ast.Tuple(
                            elts=[
                                ast.Name(id='a', ctx=ast.Load()), 
                                ast.Name(id='b', ctx=ast.Load())
                            ],
                            ctx=ast.Load()
                        )
                    elif s == 'print(a,b)':
                        return ast.Call(
                            func=ast.Name(id='print', ctx=ast.Load()),
                            args=[
                                ast.Name(id='a', ctx=ast.Load()),
                                ast.Name(id='b', ctx=ast.Load())
                            ],
                            keywords=[]
                        )
                    else:
                        return ast.parse(s, mode='eval').body
                except:
                    # Fallback to a simple name
                    return ast.Name(id='expr', ctx=ast.Load())
            
            def set_chain_aliases(self, aliases):
                pass
            
            def set_pools(self, pools):
                pass
            
            def set_hash_mapping(self, mapping):
                pass
        
        class MockMap:
            name_map = {}
        
        class MockFull:
            hash_to_value = {}
            pools = {}
        
        self.context = ParseContext(
            flow_compiler=MockCompiler(),
            cai3_map=MockMap(),
            cai3_full=MockFull(),
            method_cid='test',
            seen_names=set(),
            chain_aliases={},
            pools={},
            config=ParseConfig(strict_mode=False)
        )
        self.parser = CAI3Parser(self.context)
    
    def test_if_elif_else_chain(self):
        """Test if/elif/else chaining."""
        content = 'I(a>0):{print("pos")};E(a<0):{print("neg")};O:{print("zero")}'
        stmts = self.parser.parse(content)
        
        self.assertEqual(len(stmts), 1)
        self.assertIsInstance(stmts[0], ast.If)
        self.assertEqual(len(stmts[0].orelse), 1)
        self.assertIsInstance(stmts[0].orelse[0], ast.If)
        
    def test_nested_ternary(self):
        """Test nested ternary expressions."""
        content = 'R(x>0)?{(y>0)?{1}:{2}}:{-1}'
        stmts = self.parser.parse(content)
        
        self.assertEqual(len(stmts), 1)
        self.assertIsInstance(stmts[0], ast.Return)
        self.assertIsInstance(stmts[0].value, ast.IfExp)
        
    def test_multi_handler_try(self):
        """Test try with multiple handlers and finally."""
        content = 'T{code};X(ValueError as e){handle1};X(TypeError){handle2};F{cleanup}'
        stmts = self.parser.parse(content)
        
        self.assertEqual(len(stmts), 1)
        self.assertIsInstance(stmts[0], ast.Try)
        self.assertEqual(len(stmts[0].handlers), 2)
        self.assertEqual(len(stmts[0].finalbody), 1)
    
    def test_for_loop_destructuring(self):
        """Test for loop with tuple destructuring."""
        content = '@(a,b),items:{print(a,b)}'
        stmts = self.parser.parse(content)
        
        self.assertEqual(len(stmts), 1)
        self.assertIsInstance(stmts[0], ast.For)
        self.assertIsInstance(stmts[0].target, ast.Tuple)
    
    def test_augmented_assignment(self):
        """Test augmented assignments."""
        content = 'x += 5'
        stmts = self.parser.parse(content)
        
        self.assertEqual(len(stmts), 1)
        self.assertIsInstance(stmts[0], ast.AugAssign)
    
    def test_walrus_operator(self):
        """Test walrus operator."""
        content = 'x := 5'
        stmts = self.parser.parse(content)
        
        self.assertEqual(len(stmts), 1)
        self.assertIsInstance(stmts[0], ast.NamedExpr)
    
    def test_invalid_input_recovery(self):
        """Test recovery from invalid input."""
        content = 'T{unclosed'
        stmts = self.parser.parse(content)
        
        # Should not crash, should return Pass
        self.assertEqual(len(stmts), 1)
        self.assertIsInstance(stmts[0], ast.Pass)
    
    def test_recursion_limit(self):
        """Test recursion depth limit."""
        # Create deeply nested structure
        nested = 'I(a):{' * 150 + 'pass' + '}' * 150
        
        # Should not crash, should hit limit
        stmts = self.parser.parse(nested)
        self.assertTrue(len(stmts) > 0)

if __name__ == '__main__':
    # Run tests
    unittest.main(argv=[''], exit=False)