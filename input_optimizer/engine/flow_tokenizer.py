from enum import Enum, auto
from dataclasses import dataclass
from typing import List, Optional, Iterator
import re

class TokenType(Enum):
    # Literals
    ID = auto()
    NUM = auto()
    STR = auto()
    
    # Keywords/Macros
    MACRO_L = auto()  # Let/assign
    MACRO_F = auto()  # For
    MACRO_I = auto()  # If
    MACRO_E = auto()  # Elif
    MACRO_O = auto()  # Else
    MACRO_T = auto()  # Try
    MACRO_X = auto()  # Except
    MACRO_R = auto()  # Return
    MACRO_W = auto()  # While
    AT = auto()       # @ for loops
    
    # Operators
    EQ = auto()       # =
    EQEQ = auto()     # ==
    NE = auto()       # !=
    LE = auto()       # <=
    GE = auto()       # >=
    LT = auto()       # 
    GT = auto()       # >
    PLUS = auto()
    MINUS = auto()
    STAR = auto()
    SLASH = auto()
    PERCENT = auto()
    
    # Special operators
    NOTIN = auto()    # !in (single token!)
    IN = auto()       # in
    NOT = auto()      # !
    AND = auto()      # &
    OR = auto()       # |
    
    # Delimiters
    LPAR = auto()     # (
    RPAR = auto()     # )
    LBRACE = auto()   # {
    RBRACE = auto()   # }
    LBRACK = auto()   # [
    RBRACK = auto()   # ]
    COLON = auto()    # :
    COMMA = auto()    # ,
    SEMI = auto()     # ;
    DOT = auto()      # .
    
    # Special
    POOL = auto()     # pN references
    HASH = auto()     # hash_xxx references
    CHAIN = auto()    # gN chain aliases
    EOF = auto()
    NEWLINE = auto()
    INDENT = auto()   # Indentation level increase
    DEDENT = auto()   # Indentation level decrease

@dataclass
class Token:
    type: TokenType
    value: str = ""
    pos: int = 0
    line: int = 1
    col: int = 0

class FLOWLexer:
    """Enhanced tokenizer with INDENT/DEDENT support for FLOW language"""
    
    # Token specifications in order of precedence
    TOKEN_SPECS = [
        # Multi-char operators first (maximal munch)
        (TokenType.EQEQ, r'=='),
        (TokenType.NE, r'!='),
        (TokenType.LE, r'<='),
        (TokenType.GE, r'>='),
        (TokenType.NOTIN, r'!in'),  # Must come before NOT and IN
        
        # Keywords/macros
        (TokenType.IN, r'\bin\b'),
        (TokenType.AND, r'&'),
        (TokenType.OR, r'\|'),
        (TokenType.NOT, r'!'),
        
        # Single char operators
        (TokenType.EQ, r'='),
        (TokenType.LT, r'<'),
        (TokenType.GT, r'>'),
        (TokenType.PLUS, r'\+'),
        (TokenType.MINUS, r'-'),
        (TokenType.STAR, r'\*'),
        (TokenType.SLASH, r'/'),
        (TokenType.PERCENT, r'%'),
        (TokenType.AT, r'@'),
        
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
        
        # Literals
        (TokenType.STR, r"'([^'\\]|\\.)*'|\"([^\"\\]|\\.)*\""),
        (TokenType.NUM, r'\d+(\.\d+)?([eE][+-]?\d+)?'),
        
        # Special identifiers
        (TokenType.POOL, r'p\d+'),
        (TokenType.HASH, r'hash_[0-9a-fA-F]+|#\d+'),
        (TokenType.CHAIN, r'g\d+'),
        
        # Macros (single letter)
        (TokenType.MACRO_L, r'\bL\b'),
        (TokenType.MACRO_F, r'\bF\b'),
        (TokenType.MACRO_I, r'\bI\b'),
        (TokenType.MACRO_E, r'\bE\b'),
        (TokenType.MACRO_O, r'\bO\b'),
        (TokenType.MACRO_T, r'\bT\b'),
        (TokenType.MACRO_X, r'\bX\b'),
        (TokenType.MACRO_R, r'\bR\b'),
        (TokenType.MACRO_W, r'\bW\b'),
        
        # General identifier
        (TokenType.ID, r'[a-zA-Z_][a-zA-Z0-9_]*'),
    ]
    
    def __init__(self, src: str):
        self.lines = src.splitlines(keepends=True)
        self.line_no = 0
        self.col = 0
        self.indent_stack = [0]
        self.paren_level = 0
        self.tokens = []
        
    def tokenize(self) -> List[Token]:
        for line_no, line in enumerate(self.lines):
            self.line_no = line_no + 1
            self._tokenize_line(line)
        
        # Emit trailing NEWLINE if needed
        if self.tokens and self.tokens[-1].type != TokenType.NEWLINE:
            self.tokens.append(Token(TokenType.NEWLINE, line=self.line_no))
        
        # Flush DEDENTs to baseline
        while len(self.indent_stack) > 1:
            self.indent_stack.pop()
            self.tokens.append(Token(TokenType.DEDENT, line=self.line_no))
        
        self.tokens.append(Token(TokenType.EOF, line=self.line_no))
        return self.tokens
    
    def _tokenize_line(self, line: str):
        # Skip blank/comment lines for indentation
        if line.strip() == '' or line.strip().startswith('#'):
            self.tokens.append(Token(TokenType.NEWLINE, line=self.line_no))
            return
        
        # Handle indentation only at paren_level == 0
        if self.paren_level == 0:
            indent = len(line) - len(line.lstrip())
            current = self.indent_stack[-1]
            
            if indent > current:
                self.indent_stack.append(indent)
                self.tokens.append(Token(TokenType.INDENT, line=self.line_no, col=0))
            elif indent < current:
                while indent < self.indent_stack[-1]:
                    self.indent_stack.pop()
                    self.tokens.append(Token(TokenType.DEDENT, line=self.line_no, col=0))
                if indent != self.indent_stack[-1]:
                    raise IndentationError(f"Unaligned dedent at line {self.line_no}")
        
        # Now tokenize the actual line content (reuse existing tokenization logic)
        self._tokenize_line_content(line.lstrip())
        
        # Always emit NEWLINE at end
        self.tokens.append(Token(TokenType.NEWLINE, line=self.line_no))
    
    def _tokenize_line_content(self, content: str):
        """Tokenize the content of a line (after stripping leading whitespace)"""
        pos = 0
        col = 0
        
        while pos < len(content):
            # Skip whitespace (spaces and tabs)
            if content[pos] in ' \t':
                pos += 1
                col += 1
                continue
            
            # Skip newline at end of content - it will be handled by _tokenize_line
            if content[pos] == '\n':
                break
            
            # Track parentheses level for indentation handling
            if content[pos] == '(':
                self.paren_level += 1
            elif content[pos] == ')':
                self.paren_level -= 1
            elif content[pos] == '[':
                self.paren_level += 1
            elif content[pos] == ']':
                self.paren_level -= 1
            elif content[pos] == '{':
                self.paren_level += 1
            elif content[pos] == '}':
                self.paren_level -= 1
            
            # Try each token pattern
            matched = False
            for token_type, pattern in self.TOKEN_SPECS:
                regex = re.compile(pattern)
                match = regex.match(content, pos)
                if match:
                    value = match.group(0)
                    token = Token(token_type, value, pos, self.line_no, col)
                    self.tokens.append(token)
                    
                    # Update position
                    pos = match.end()
                    col += len(value)
                    matched = True
                    break
            
            if not matched:
                raise SyntaxError(f"Unexpected character '{content[pos]}' at line {self.line_no}, col {col}")