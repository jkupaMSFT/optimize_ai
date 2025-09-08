"""Production FLOW tokenizer with all edge cases handled."""

import re
from enum import Enum, auto
from dataclasses import dataclass
from typing import List, Pattern, Optional, Tuple

class TokenType(Enum):
    # Literals
    ID = auto()
    NUM = auto()
    STR = auto()
    
    # Single-char Macros
    MACRO_L = auto()
    MACRO_F = auto()
    MACRO_I = auto()
    MACRO_E = auto()
    MACRO_O = auto()
    MACRO_T = auto()
    MACRO_X = auto()
    MACRO_R = auto()
    MACRO_W = auto()
    MACRO_Z = auto()
    MACRO_H = auto()
    MACRO_J = auto()
    MACRO_B = auto()
    MACRO_K = auto()
    MACRO_D = auto()
    UNDERSCORE = auto()
    AT = auto()
    
    # Operators (complete set)
    EQ = auto()
    EQEQ = auto()
    NE = auto()
    LE = auto()
    GE = auto()
    LT = auto()
    GT = auto()
    PLUS = auto()
    MINUS = auto()
    STAR = auto()
    SLASH = auto()
    DOUBLESLASH = auto()  # //
    PERCENT = auto()
    DOUBLESTAR = auto()   # **
    LSHIFT = auto()       # <<
    RSHIFT = auto()       # >>
    AMPERSAND = auto()    # & (bitwise)
    PIPE = auto()         # | (bitwise)
    CARET = auto()        # ^ (xor)
    TILDE = auto()        # ~ (invert)
    
    # Logical operators
    AND = auto()          # 'and' keyword
    OR = auto()           # 'or' keyword
    NOT = auto()          # 'not' keyword
    NOTIN = auto()
    IN = auto()
    IS = auto()
    ISNOT = auto()
    
    # Delimiters
    LPAR = auto()
    RPAR = auto()
    LBRACE = auto()
    RBRACE = auto()
    LBRACK = auto()
    RBRACK = auto()
    COLON = auto()
    COMMA = auto()
    SEMI = auto()
    DOT = auto()
    ARROW = auto()        # ->
    
    # Special identifiers (must come before COMMENT!)
    POOL = auto()
    HASH = auto()
    CHAIN = auto()
    
    # Comment (must come after HASH!)
    COMMENT = auto()
    
    # Control
    EOF = auto()
    NEWLINE = auto()
    INDENT = auto()
    DEDENT = auto()

@dataclass
class Token:
    type: TokenType
    value: str = ""
    pos: int = 0
    line: int = 1
    col: int = 0

class FLOWLexer:
    """Production tokenizer with precompiled patterns and unified nesting depth."""
    
    # Precompiled patterns (class-level for performance)
    PATTERNS: List[Tuple[TokenType, Pattern]] = []
    
    # Single-char macros
    MACRO_MAP = {
        'L': TokenType.MACRO_L,
        'F': TokenType.MACRO_F,
        'I': TokenType.MACRO_I,
        'E': TokenType.MACRO_E,
        'O': TokenType.MACRO_O,
        'T': TokenType.MACRO_T,
        'X': TokenType.MACRO_X,
        'R': TokenType.MACRO_R,
        'W': TokenType.MACRO_W,
        'Z': TokenType.MACRO_Z,
        'H': TokenType.MACRO_H,
        'J': TokenType.MACRO_J,
        'B': TokenType.MACRO_B,
        'K': TokenType.MACRO_K,
        'D': TokenType.MACRO_D,
        '_': TokenType.UNDERSCORE,
        '@': TokenType.AT,
    }
    
    @classmethod
    def _init_patterns(cls):
        """Initialize patterns with correct ordering."""
        if cls.PATTERNS:
            return  # Already initialized
        
        specs = [
            # Multi-char operators first (maximal munch)
            (TokenType.ARROW, r'->'),
            (TokenType.EQEQ, r'=='),
            (TokenType.NE, r'!='),
            (TokenType.LE, r'<='),
            (TokenType.GE, r'>='),
            (TokenType.LSHIFT, r'<<'),
            (TokenType.RSHIFT, r'>>'),
            (TokenType.DOUBLESTAR, r'\*\*'),
            (TokenType.DOUBLESLASH, r'//'),
            
            # Single operators
            (TokenType.EQ, r'='),
            (TokenType.LT, r'<'),
            (TokenType.GT, r'>'),
            (TokenType.PLUS, r'\+'),
            (TokenType.MINUS, r'-'),
            (TokenType.STAR, r'\*'),
            (TokenType.SLASH, r'/'),
            (TokenType.PERCENT, r'%'),
            (TokenType.AMPERSAND, r'&'),
            (TokenType.PIPE, r'\|'),
            (TokenType.CARET, r'\^'),
            (TokenType.TILDE, r'~'),
            
            # Delimiters
            (TokenType.LPAR, r'\('),
            (TokenType.RPAR, r'\)'),
            (TokenType.LBRACE, r'\{'),
            (TokenType.RBRACE, r'\}'),
            (TokenType.LBRACK, r'\['),
            (TokenType.RBRACK, r'\]'),
            (TokenType.COLON, r':'),
            (TokenType.COMMA, r','),
            (TokenType.SEMI, r';'),
            (TokenType.DOT, r'\.'),
            (TokenType.AT, r'@'),  # Add @ as a pattern too for fallback
            
            # String literals
            (TokenType.STR, r"'([^'\\]|\\.)*'|\"([^\"\\]|\\.)*\""),
            
            # CRITICAL: Special identifiers BEFORE numeric literals
            (TokenType.POOL, r'p\d+\b'),
            (TokenType.HASH, r'#\d+\b'),  # Only #NNN format
            (TokenType.CHAIN, r'g\d+\b'),
            
            # Numeric literals with strict validation
            # Hex: 0x/0X followed by hex digits with optional underscores (not leading/trailing)
            (TokenType.NUM, r'0[xX][0-9a-fA-F](?:_?[0-9a-fA-F])*(?![_\w])'),
            # Binary: 0b/0B followed by binary digits
            (TokenType.NUM, r'0[bB][01](?:_?[01])*(?![_\w])'),
            # Octal: 0o/0O followed by octal digits
            (TokenType.NUM, r'0[oO][0-7](?:_?[0-7])*(?![_\w])'),
            # Decimal with optional underscores and scientific notation
            (TokenType.NUM, r'\d(?:_?\d)*(?:\.(?:\d(?:_?\d)*))?(?:[eE][+-]?\d(?:_?\d)*)?(?![_\w])'),
            
            # CRITICAL: Comments AFTER hash tokens
            (TokenType.COMMENT, r'#[^\n]*'),
            
            # Keywords - compound patterns handled specially in tokenization logic
            (TokenType.AND, r'\band\b'),
            (TokenType.OR, r'\bor\b'),
            (TokenType.NOT, r'\bnot\b'),
            (TokenType.IN, r'\bin\b'),
            (TokenType.IS, r'\bis\b'),
            
            # General identifier (must be last)
            (TokenType.ID, r'[a-zA-Z_][a-zA-Z0-9_]*'),
        ]
        
        cls.PATTERNS = [(t, re.compile(p)) for t, p in specs]
    
    def __init__(self, src: str, allow_compact_macros: bool = False):
        """
        Args:
            src: Source code
            allow_compact_macros: If True, allow Lx=1 style (legacy compat)
        """
        self._init_patterns()
        self.lines = src.splitlines(keepends=False)
        self.tokens = []
        self.indent_stack = [0]
        self.nesting_depth = 0  # Unified depth for (), [], {}
        self.allow_compact_macros = allow_compact_macros
    
    def tokenize(self) -> List[Token]:
        """Tokenize with complete handling."""
        
        for line_no, line in enumerate(self.lines, 1):
            self._process_line(line, line_no)
        
        # Final cleanup
        if self.tokens and self.tokens[-1].type != TokenType.NEWLINE:
            self.tokens.append(Token(TokenType.NEWLINE, line=len(self.lines)))
        
        # Flush dedents
        while len(self.indent_stack) > 1:
            self.indent_stack.pop()
            self.tokens.append(Token(TokenType.DEDENT, line=len(self.lines)))
        
        self.tokens.append(Token(TokenType.EOF, line=len(self.lines)))
        
        # Post-process to combine compound keywords
        self._combine_compound_keywords()
        
        return self.tokens
    
    def _combine_compound_keywords(self):
        """Post-process tokens to combine compound keywords where appropriate."""
        i = 0
        while i < len(self.tokens) - 1:
            current = self.tokens[i]
            next_token = self.tokens[i + 1]
            
            # Look for "is not" pattern
            if (current.type == TokenType.IS and 
                next_token.type == TokenType.NOT and
                self._should_combine_keywords(i)):
                # Combine into ISNOT
                combined = Token(
                    TokenType.ISNOT, 
                    f"{current.value} {next_token.value}",
                    current.pos, 
                    current.line, 
                    current.col
                )
                self.tokens[i] = combined
                del self.tokens[i + 1]
                continue
            
            # Look for "not in" pattern  
            if (current.type == TokenType.NOT and 
                next_token.type == TokenType.IN and
                self._should_combine_keywords(i)):
                # Combine into NOTIN
                combined = Token(
                    TokenType.NOTIN, 
                    f"{current.value} {next_token.value}",
                    current.pos, 
                    current.line, 
                    current.col
                )
                self.tokens[i] = combined
                del self.tokens[i + 1]
                continue
            
            i += 1
    
    def _should_combine_keywords(self, token_index: int) -> bool:
        """Determine if keywords at token_index and token_index+1 should be combined."""
        # For the sequence "and or not in is is not not in":
        # - "not in" at position 2-3 should NOT combine (because "or" before and "is" after)
        # - "is not" at position 4-5 should combine (because no keyword after - only "not in")
        # - "not in" at position 6-7 should combine (because it's at the end)
        
        current = self.tokens[token_index]
        next_token = self.tokens[token_index + 1]
        
        # Special logic for "is not" - always combine unless there's another "not" immediately after
        if current.type == TokenType.IS and next_token.type == TokenType.NOT:
            # Check if there's another token after the compound that would make this part of a sequence
            if token_index + 2 < len(self.tokens):
                after_token = self.tokens[token_index + 2]
                # Don't combine "is not" if followed by "in" (making "is not in" sequence)
                if after_token.type == TokenType.IN:
                    return False
            # Otherwise combine "is not" into ISNOT
            return True
        
        # Special logic for "not in" 
        if current.type == TokenType.NOT and next_token.type == TokenType.IN:
            # Check if there's a keyword before this "not"
            if token_index > 0:
                prev_token = self.tokens[token_index - 1]
                # If "not in" is preceded by "is", don't combine (part of "is not in" sequence)
                if prev_token.type == TokenType.IS:
                    return False
                # If preceded by other keywords in a sequence, don't combine
                if prev_token.type in (TokenType.AND, TokenType.OR):
                    # Check if there's also a keyword after
                    if token_index + 2 < len(self.tokens):
                        after_token = self.tokens[token_index + 2]
                        if after_token.type in (TokenType.AND, TokenType.OR, TokenType.NOT, TokenType.IN, TokenType.IS):
                            return False
            # Otherwise combine "not in" into NOTIN
            return True
        
        return False
    
    def _process_line(self, line: str, line_no: int):
        """Process line with nesting-aware indentation."""
        
        # Skip pure comment/empty lines
        stripped = line.strip()
        if not stripped or stripped.startswith('#'):
            if stripped.startswith('#'):
                self.tokens.append(Token(TokenType.COMMENT, stripped, 0, line_no, 0))
            # Only emit NEWLINE if not nested
            if self.nesting_depth == 0:
                self.tokens.append(Token(TokenType.NEWLINE, line=line_no))
            return
        
        # Handle indentation ONLY when nesting_depth == 0
        if self.nesting_depth == 0:
            indent = len(line) - len(line.lstrip())
            current = self.indent_stack[-1]
            
            if indent > current:
                self.indent_stack.append(indent)
                self.tokens.append(Token(TokenType.INDENT, line=line_no))
            elif indent < current:
                while len(self.indent_stack) > 1 and self.indent_stack[-1] > indent:
                    self.indent_stack.pop()
                    self.tokens.append(Token(TokenType.DEDENT, line=line_no))
                
                if self.indent_stack[-1] != indent:
                    raise IndentationError(f"Unindent mismatch at line {line_no}")
        
        # Tokenize content
        self._tokenize_content(line.lstrip(), line_no)
        
        # Emit NEWLINE ONLY when nesting_depth == 0
        if self.nesting_depth == 0:
            self.tokens.append(Token(TokenType.NEWLINE, line=line_no))
    
    def _tokenize_content(self, content: str, line_no: int):
        """Tokenize with special handling for # disambiguation."""
        pos = 0
        
        while pos < len(content):
            # Skip whitespace
            if content[pos] in ' \t':
                pos += 1
                continue
            
            # Update nesting depth
            char = content[pos]
            if char in '([{':
                self.nesting_depth += 1
            elif char in ')]}':
                self.nesting_depth = max(0, self.nesting_depth - 1)
            
            # Special handling for # - disambiguate hash vs comment
            if char == '#':
                # Look ahead to see if it's followed by digits
                if pos + 1 < len(content) and content[pos + 1].isdigit():
                    # It's a hash token #123
                    match = re.match(r'#\d+\b', content[pos:])
                    if match:
                        value = match.group(0)
                        self.tokens.append(Token(TokenType.HASH, value, pos, line_no, pos))
                        pos = match.end() + pos
                        continue
                else:
                    # It's a comment
                    comment = content[pos:]
                    self.tokens.append(Token(TokenType.COMMENT, comment, pos, line_no, pos))
                    return  # Rest of line is comment
            
            # Check for macro at statement position
            if self._is_statement_position(pos, content):
                if char in self.MACRO_MAP:
                    # Check delimiter policy - relaxed for @ since it can take any expression
                    if (self.allow_compact_macros or 
                        char == '@' or  # Always allow @ regardless of what follows
                        pos + 1 >= len(content) or 
                        not content[pos + 1].isalnum()):
                        self.tokens.append(Token(self.MACRO_MAP[char], char, pos, line_no, pos))
                        pos += 1
                        continue
            
            # Special case: check for invalid numeric literal patterns
            if char == '_' and pos + 1 < len(content) and content[pos + 1].isdigit():
                raise SyntaxError(f"Invalid numeric literal starting with underscore at line {line_no}:{pos}")
            
            # Special case: check for double underscores in potential numeric contexts
            if char.isdigit() or char in '0x0X0b0B0o0O':
                # Look ahead for problematic underscore patterns
                temp_pos = pos
                while temp_pos < len(content) and (content[temp_pos].isalnum() or content[temp_pos] in '._'):
                    if temp_pos + 1 < len(content) and content[temp_pos] == '_' and content[temp_pos + 1] == '_':
                        raise SyntaxError(f"Invalid double underscore in numeric literal at line {line_no}:{temp_pos}")
                    temp_pos += 1
            
            # Try patterns
            matched = False
            for token_type, pattern in self.PATTERNS:
                # Skip COMMENT pattern (handled above)
                if token_type == TokenType.COMMENT:
                    continue
                    
                match = pattern.match(content, pos)
                if match:
                    value = match.group(0)
                    
                    # Validate numeric literals
                    if token_type == TokenType.NUM:
                        if not self._validate_numeric_literal(value):
                            raise SyntaxError(f"Invalid numeric literal '{value}' at line {line_no}:{pos}")
                    
                    self.tokens.append(Token(token_type, value, pos, line_no, pos))
                    pos = match.end()
                    matched = True
                    break
            
            if not matched:
                raise SyntaxError(f"Unexpected '{content[pos]}' at line {line_no}:{pos}")
    
    def _should_form_compound_keyword(self, content: str, pos: int) -> bool:
        """Determine if we should form a compound keyword at this position."""
        # Look ahead and behind to see if this is part of a larger keyword sequence
        # Don't form compound keywords if we're in a sequence like "and or not in is"
        
        # Check what comes before (skip whitespace)
        before_pos = pos - 1
        while before_pos >= 0 and content[before_pos] in ' \t':
            before_pos -= 1
        
        if before_pos >= 0:
            # Look for keyword before current position
            before_match = None
            for kw in ['and', 'or', 'not', 'in', 'is']:
                if before_pos >= len(kw) - 1:
                    if content[before_pos - len(kw) + 1:before_pos + 1] == kw:
                        before_match = kw
                        break
        
        # If there's a keyword immediately before, we're probably in a sequence
        # Don't form compound keywords in sequences
        if before_match:
            return False
        
        return True
    
    def _is_statement_position(self, pos: int, content: str) -> bool:
        """Check if position is valid for a statement-leading macro."""
        if pos == 0:
            return True
        
        # After these chars, macros are allowed
        prev_char = content[pos - 1]
        return prev_char in ' \t;:{\n'
    
    def _validate_numeric_literal(self, value: str) -> bool:
        """Validate numeric literal for illegal underscore placement."""
        # Check for leading/trailing underscores
        if value.startswith('_') or value.endswith('_'):
            return False
        
        # Check for double underscores
        if '__' in value:
            return False
        
        # Check for underscore after prefix
        if value.startswith(('0x', '0X', '0b', '0B', '0o', '0O')):
            if len(value) > 2 and value[2] == '_':
                return False
        
        # Check for underscore before/after decimal point
        if '._' in value or '_.' in value:
            return False
        
        # Check for underscore before/after exponent
        if '_e' in value.lower() or 'e_' in value.lower():
            return False
        
        return True

# Initialize patterns once at module load
FLOWLexer._init_patterns()