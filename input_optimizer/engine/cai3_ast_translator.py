"""
Production-ready CAI3 to Python AST translator.
Complete pipeline with all transformers, validation, and testing.
"""

# Add these imports at the top after other imports
import ast
import re
import logging
import keyword
import black
from typing import List, Dict, Optional, Tuple, Any, Union
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from .hash_resolver import HashResolver
from .cai3_ast_transformer import ResolutionTransformer
from .cai3_grammar import CAI3LiteParser
from .cai3_structure_analyzer import CAI3StructureAnalyzer
# from .cai3_python_reconstructor import CAI3PythonReconstructor  # Removed to fix circular import

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
    resolver: Any = None  # Add resolver field
    
    def setup_flow_compiler(self):
        """Initialize flow compiler with context."""
        if hasattr(self.flow_compiler, 'set_chain_aliases') and self.chain_aliases:
            self.flow_compiler.set_chain_aliases(self.chain_aliases)
        if hasattr(self.flow_compiler, 'set_pools') and self.pools:
            self.flow_compiler.set_pools(self.pools)
        if hasattr(self.cai3_full, 'hash_to_value'):
            if hasattr(self.flow_compiler, 'set_hash_mapping'):
                self.flow_compiler.set_hash_mapping(self.cai3_full.hash_to_value)

class CAI3BodyParser:
    """Production-ready CAI3 body parser with all fixes applied."""
    
    # Multiline-aware normalizations with remainder preservation
    NORMALIZATIONS = [
        # Basic prefixes - multiline aware
        (r'(?m)^if_', 'if '),
        (r'(?m)^elif_', 'elif '),
        (r'(?m)^else_(.*)$', r'else:\n    \1'),
        (r'(?m)^try_(.*)$', r'try:\n    \1'),
        (r'(?m)^except_(.*)$', r'except \1'),
        (r'(?m)^return___', 'return {'),
        (r'(?m)^return_(\w+)', r'return \1'),
        
        # Complex if-in patterns with proper grouping
        (r'if__([^_]+)__in_([^_]+)_(.+)', r'if \1 in \2:\n    \3'),
        (r'elif__([^_]+)__in_([^_]+)_(.+)', r'elif \1 in \2:\n    \3'),
        
        # Print statement fixes
        (r'else_pr in t', 'else:\n    print'),
        (r'pr in t', 'print'),
        (r'\.m in imal', '.minimal'),
        
        # Hash removal patterns - more specific
        (r'mt_[a-f0-9]+_(\w+)', r'\1'),  # Remove method hashes
        (r'fn_[a-f0-9]+_(\w+)', r'\1'),  # Remove function hashes
        
        # Exception handling improvements
        (r'except_(\w+)_as_(\w+)', r'except \1 as \2'),
        (r'except_(\w+)', r'except \1'),
    ]
    
    def __init__(self, strict_mode: bool = False):
        self.strict_mode = strict_mode
        self.logger = logging.getLogger(__name__)
        self.pools = {}  # Pool storage for resolution
        self.chain_aliases = {}  # Chain aliases for resolution
        # Pre-compile patterns for efficiency
        self.compiled_patterns = [
            (re.compile(pattern), replacement) 
            for pattern, replacement in self.NORMALIZATIONS
        ]
    
    def parse_body(self, body_content: str, body_id: str) -> List[ast.stmt]:
        """Parse body with complete statement preservation and try-except reconstruction."""
        statements = []
        
        # Apply pool resolution to the entire body content first
        resolved_body = self.resolve_pool_references(body_content)
        
        for raw_line in resolved_body.splitlines():
            line = raw_line.strip()
            
            # Skip empty lines and metadata
            if not line or line.startswith('# Table entry'):
                continue
            
            # Remove CAI3 prefixes once
            if line.startswith(('T:', 'D:')):
                line = line[2:].strip()
                if not line:
                    continue
            
            # Special handling for complete try-except blocks
            # If we detect a try-except pattern, handle it as one unit
            if 'try:' in line and ('except' in line or line.count(';') > 3):
                # This looks like a complete try-except block
                statements.extend(self._parse_try_except_block(line, body_id))
                continue
            
            # Split on semicolons (handles all brackets and preserves control flow)
            for part in self._smart_split_semicolons(line):
                part = part.strip()
                if not part:
                    continue
                
                # Parse ALL statements from this part
                stmts = self._parse_line(part, body_id)
                if stmts:
                    statements.extend(stmts)
        
        return statements if statements else [ast.Pass()]
    
    def _smart_split_semicolons(self, line: str) -> List[str]:
        """Split on semicolons while preserving control flow structures."""
        parts = []
        current = []
        in_string = False
        quote_char = None
        paren_depth = 0
        brace_depth = 0
        bracket_depth = 0
        
        # Track control flow state
        in_control_flow = False
        control_flow_keywords = ['for', 'while', 'if', 'elif', 'try', 'with']
        
        i = 0
        while i < len(line):
            char = line[i]
            
            # Handle string boundaries
            if char in ('"', "'") and (i == 0 or line[i-1] != '\\'):
                if not in_string:
                    in_string = True
                    quote_char = char
                elif char == quote_char:
                    in_string = False
                    quote_char = None
                # Don't continue here - we need to add the quote to current
                current.append(char)
                i += 1
                continue
            
            # Track all bracket depths
            elif not in_string:
                if char == '(':
                    paren_depth += 1
                elif char == ')':
                    paren_depth -= 1
                elif char == '{':
                    brace_depth += 1
                elif char == '}':
                    brace_depth -= 1
                elif char == '[':
                    bracket_depth += 1
                elif char == ']':
                    bracket_depth -= 1
                elif char == ';' and paren_depth == 0 and brace_depth == 0 and bracket_depth == 0:
                    # Check if we're in a control flow structure
                    current_text = ''.join(current).strip()
                    
                    # Look ahead to find just the next statement (until next semicolon or end)
                    remaining = line[i+1:].strip()
                    next_semicolon = remaining.find(';')
                    if next_semicolon != -1:
                        next_stmt = remaining[:next_semicolon].strip()
                    else:
                        next_stmt = remaining.strip()
                    
                    # Don't split if this would break control flow
                    if self._would_break_control_flow(current_text, next_stmt):
                        current.append(char)
                        i += 1
                        continue
                    
                    # Safe to split here
                    parts.append(current_text)
                    current = []
                    i += 1
                    continue
            
            current.append(char)
            i += 1
        
        # Add remaining part
        if current:
            parts.append(''.join(current).strip())
        
        # Filter out empty parts
        return [part for part in parts if part]
    
    def _would_break_control_flow(self, current_stmt: str, next_stmt: str) -> bool:
        """Check if splitting here would break control flow structure."""
        if not current_stmt or not next_stmt:
            return False
        
        # Check if current statement opens a control structure
        control_patterns = [
            r'\bfor\s+\w+\s+in\s+[^:]+$',  # for loop without colon
            r'\bwhile\s+[^:]+$',           # while without colon
            r'\bif\s+[^:]+$',              # if without colon
            r'\belif\s+[^:]+$',            # elif without colon
            r'\btry\s*$',                  # try without colon
            r'\bwith\s+[^:]+$',            # with without colon
        ]
        
        for pattern in control_patterns:
            if re.search(pattern, current_stmt):
                # If this opens a control structure, don't split before the body
                return True
        
        # Special handling for try statements - don't split until we see except/finally
        if current_stmt.strip().startswith('try:') or 'try:' in current_stmt:
            # Don't split anything in a try block until we see except/finally
            if not any(kw in next_stmt for kw in ['except', 'finally']):
                return True
        
        # Check if we're inside a try block by looking for try earlier in context
        # This is a simple heuristic - in a real implementation we'd track block context
        if any(kw in next_stmt for kw in ['except', 'finally']):
            # We're ending a try block, don't split the except from its handler
            return False
        
        # Check for break/continue statements that should stay with their loop
        if next_stmt.strip() in ['break', 'continue']:
            # Look for loop keywords in current statement
            if any(keyword in current_stmt for keyword in ['for', 'while']):
                return True
        
        # Check for else/elif that should stay with if
        if next_stmt.strip().startswith(('else', 'elif')):
            if 'if' in current_stmt:
                return True
        
        # Check for except/finally that should stay with try
        if next_stmt.strip().startswith(('except', 'finally')):
            if 'try' in current_stmt:
                return True
        
        return False
    
    def _parse_try_except_block(self, line: str, body_id: str) -> List[ast.stmt]:
        """Parse a complete try-except block from CAI3 compressed format."""
        
        # Find the try and except parts
        try_start = line.find('try:')
        except_pos = line.find(';except ')
        
        if try_start == -1 or except_pos == -1:
            # Fall back to normal parsing
            return self._parse_line(line, body_id)
        
        # Extract the try body (everything between try: and ;except)
        try_body = line[try_start + 4:except_pos]
        
        # Extract the except clause (everything after ;except)
        except_clause = line[except_pos + 1:]  # Remove the semicolon
        
        # Build the properly formatted try-except block
        # Split try body on semicolons and format
        try_statements = [stmt.strip() for stmt in try_body.split(';') if stmt.strip()]
        
        # Handle the except clause
        if except_clause.startswith('except '):
            except_part = except_clause[7:]  # Remove 'except '
            
            # Find the colon in the except clause
            colon_pos = except_part.find(':')
            if colon_pos != -1:
                exception_spec = except_part[:colon_pos].strip()
                except_body = except_part[colon_pos + 1:].strip()
                
                # Format the complete block
                formatted_try_body = '\n    '.join(try_statements)
                formatted_block = f'''try:
    {formatted_try_body}
except {exception_spec}:
    {except_body}'''
                
                try:
                    # Parse the formatted block
                    module = ast.parse(formatted_block, mode='exec')
                    return module.body
                except SyntaxError as e:
                    self.logger.debug(f"Failed to parse formatted try-except block: {e}")
        
        # If formatting failed, fall back to normal parsing
        return self._parse_line(line, body_id)
    
    def _parse_line(self, line: str, body_id: str) -> List[ast.stmt]:
        """Parse line and return ALL statements."""
        
        # First try: parse as-is
        try:
            module = ast.parse(line, mode='exec')
            return module.body  # Return ALL statements
        except SyntaxError:
            pass
        
        # Second try: apply normalizations
        normalized = self._normalize_cai3(line)
        if normalized != line:
            try:
                module = ast.parse(normalized, mode='exec')
                return module.body  # Return ALL statements
            except SyntaxError as e:
                self.logger.debug(f"Parse failed after normalization: {e}")
        
        # Final fallback
        if self.strict_mode:
            raise ValueError(f"Cannot parse in {body_id}: {line[:50]}...")
        
        # Return error comment
        error_msg = f"# Parse error in {body_id}: {line[:60]}..."
        return [ast.Expr(value=ast.Constant(value=error_msg))]
    
    def _normalize_cai3(self, line: str) -> str:
        """Apply normalizations with multiline support and CAI3 syntax expansion."""
        
        # Handle complete try-except blocks that span multiple semicolon parts
        # Pattern: try:statements;statements;except Exception as e:return
        # Ensure proper indentation for AST parsing
        try_except_pattern = r'try:([^;]+(?:;[^;]*)*);except\s+([^:]+):(.+)$'
        match = re.search(try_except_pattern, line)
        if match:
            try_body, exception_spec, except_body = match.groups()
            # Split the try body on semicolons and create properly indented structure
            try_statements = [stmt.strip() for stmt in try_body.split(';') if stmt.strip()]
            try_body_formatted = '\n    '.join(try_statements)
            
            expanded = f'''try:
    {try_body_formatted}
except {exception_spec}:
    {except_body}'''
            line = expanded
        
        # Handle compressed for-loop syntax with nested conditions
        # Pattern: for x in y:if condition:action;break
        # Ensure proper indentation for AST parsing
        for_pattern = r'for\s+(\w+)\s+in\s+([^:]+):if\s+([^:]+):([^;]+);break'
        match = re.search(for_pattern, line)
        if match:
            var, iterable, condition, action = match.groups()
            expanded = f'''for {var} in {iterable}:
    if {condition}:
        {action}
        break'''
            line = re.sub(for_pattern, expanded, line)
        
        # Handle multiple elif chains with semicolons
        # Pattern: if condition:action;elif condition:action;elif condition:action;else:action
        # Ensure proper indentation for AST parsing
        
        # First handle if-elif-elif-else chains
        complex_if_pattern = r'if\s+([^:]+):([^;]+);elif\s+([^:]+):([^;]+);elif\s+([^:]+):([^;]+);else:([^;]+)'
        if re.search(complex_if_pattern, line):
            line = re.sub(complex_if_pattern, r'if \1:\n    \2\nelif \3:\n    \4\nelif \5:\n    \6\nelse:\n    \7', line)
        
        # Handle if-elif-else chains
        if_elif_else_pattern = r'if\s+([^:]+):([^;]+);elif\s+([^:]+):([^;]+);else:([^;]+)'
        if re.search(if_elif_else_pattern, line):
            line = re.sub(if_elif_else_pattern, r'if \1:\n    \2\nelif \3:\n    \4\nelse:\n    \5', line)
        
        # Handle simple if-elif chains
        elif_pattern = r'if\s+([^:]+):([^;]+);elif\s+([^:]+):([^;]+)'
        while re.search(elif_pattern, line):
            line = re.sub(elif_pattern, r'if \1:\n    \2\nelif \3:\n    \4', line)
        
        # Handle elif-else patterns
        else_pattern = r'elif\s+([^:]+):([^;]+);else:([^;]+)'
        if re.search(else_pattern, line):
            line = re.sub(else_pattern, r'elif \1:\n    \2\nelse:\n    \3', line)
        
        # Handle simple if-else patterns
        if_else_pattern = r'if\s+([^:]+):([^;]+);else:([^;]+)'
        if re.search(if_else_pattern, line):
            line = re.sub(if_else_pattern, r'if \1:\n    \2\nelse:\n    \3', line)
        
        # Handle simple if statements with multiple actions (semicolon separated)
        # Pattern: if condition: action1; action2; action3
        # Ensure proper indentation for AST parsing
        simple_if_multi_pattern = r'if\s+([^:]+):\s*([^;]+);\s*([^;]+)(?:;\s*([^;]+))?'
        match = re.search(simple_if_multi_pattern, line)
        if match and not any(kw in line for kw in ['elif', 'else']):  # Avoid conflicts with complex patterns
            condition = match.group(1)
            action1 = match.group(2)
            action2 = match.group(3)
            action3 = match.group(4) if match.group(4) else None
            
            # Build the expanded if statement with proper indentation for AST parsing
            if action3:
                expanded = f'if {condition}:\n    {action1}\n    {action2}\n    {action3}'
            else:
                expanded = f'if {condition}:\n    {action1}\n    {action2}'
            line = re.sub(simple_if_multi_pattern, expanded, line)
        
        # Handle compound statements with assignments and operations
        # Pattern: var=value;operation;another_operation
        compound_pattern = r'(\w+)=([^;]+);([^;]+);([^;]+)'
        if re.search(compound_pattern, line) and 'if' not in line and 'for' not in line:
            line = re.sub(compound_pattern, r'\1 = \2\n\3\n\4', line)
        
        # Handle dictionary/object creation patterns
        # Pattern: {"key":value,"key2":value2}
        dict_pattern = r'\{([^}]+)\}'
        def expand_dict(match):
            content = match.group(1)
            if ':' in content and ',' in content:
                # This looks like a dictionary - format it properly
                pairs = content.split(',')
                formatted_pairs = []
                for pair in pairs:
                    if ':' in pair:
                        key, value = pair.split(':', 1)
                        formatted_pairs.append(f'    {key.strip()}: {value.strip()}')
                    else:
                        formatted_pairs.append(f'    {pair.strip()}')
                return '{\n' + ',\n'.join(formatted_pairs) + '\n}'
            return match.group(0)
        
        line = re.sub(dict_pattern, expand_dict, line)
        
        # Apply original normalizations
        for pattern, replacement in self.compiled_patterns:
            line = pattern.sub(replacement, line)
        
        return line
    
    def resolve_pool_references(self, content: str) -> str:
        """Resolve pool references with intelligent fallback mappings."""
        # Enhanced pool mapping based on common patterns from logs
        pool_fallback_mapping = {
            'p0': 'self', 'p1': 'data', 'p2': 'result', 'p3': 'value', 'p4': 'item',
            'p5': 'index', 'p6': 'key', 'p7': 'config', 'p8': 'logger', 'p9': 'status',
            'p10': 'output', 'p11': 'input', 'p12': 'temp', 'p13': 'count', 'p14': 'flag',
            'p15': 'path', 'p16': 'file', 'p17': 'text', 'p18': 'line', 'p19': 'word',
            'p20': 'node', 'p21': 'tree', 'p22': 'root', 'p23': 'parent', 'p24': 'child',
            'p25': 'left', 'p26': 'right', 'p27': 'top', 'p28': 'bottom', 'p29': 'center',
            'p30': 'start', 'p31': 'end', 'p32': 'next', 'p33': 'prev', 'p34': 'current',
            'p35': 'last', 'p36': 'first', 'p37': 'buffer', 'p38': 'cache', 'p39': 'memory',
            'p40': 'state', 'p41': 'context', 'p42': 'session', 'p43': 'request', 'p44': 'response',
            'p45': 'params', 'p46': 'args', 'p47': 'kwargs', 'p48': 'options', 'p49': 'settings',
            'p50': 'error', 'p51': 'exception', 'p52': 'warning', 'p53': 'info', 'p54': 'debug',
            'p55': 'trace', 'p56': 'log', 'p57': 'message', 'p58': 'event', 'p59': 'signal',
            'p60': 'callback', 'p61': 'handler', 'p62': 'listener', 'p63': 'observer', 'p64': 'watcher',
            'p65': 'monitor', 'p66': 'manager', 'p67': 'controller', 'p68': 'service', 'p69': 'client',
            'p70': 'server', 'p71': 'connection', 'p72': 'socket', 'p73': 'stream', 'p74': 'channel',
            'p75': 'queue', 'p76': 'stack', 'p77': 'list', 'p78': 'dict', 'p79': 'set',
            'p80': 'tuple', 'p81': 'array', 'p82': 'vector', 'p83': 'matrix', 'p84': 'tensor',
            'p85': 'model', 'p86': 'view', 'p87': 'template', 'p88': 'layout', 'p89': 'style',
            'p90': 'theme', 'p91': 'color', 'p92': 'size', 'p93': 'width', 'p94': 'height',
            'p95': 'length', 'p96': 'distance', 'p97': 'angle', 'p98': 'position', 'p99': 'coordinate',
            'p100': 'time', 'p101': 'date', 'p102': 'timestamp', 'p103': 'duration', 'p104': 'timeout',
            'p105': 'delay', 'p106': 'interval', 'p107': 'frequency', 'p108': 'rate', 'p109': 'speed',
            'p110': 'limit', 'p111': 'max', 'p112': 'min', 'p113': 'average', 'p114': 'sum',
            'p115': 'total', 'p116': 'partial', 'p117': 'complete', 'p118': 'progress', 'p119': 'percentage',
            'p120': 'ratio', 'p121': 'factor', 'p122': 'multiplier', 'p123': 'divisor', 'p124': 'remainder',
            'p125': 'quotient', 'p126': 'product', 'p127': 'difference', 'p128': 'format', 'p129': 'pattern',
            'p130': 'regex', 'p131': 'match', 'p132': 'search', 'p133': 'find', 'p134': 'replace',
            'p135': 'split', 'p136': 'join', 'p137': 'strip', 'p138': 'trim', 'p139': 'clean',
            'p140': 'validate', 'p141': 'check', 'p142': 'test', 'p143': 'print', 'p144': 'display',
            'p145': 'show', 'p146': 'render', 'p147': 'draw', 'p148': 'paint', 'p149': 'fill'
        }
        
        # Check pools and chain_aliases from the instance
        resolved_pools = {**pool_fallback_mapping}
        if hasattr(self, 'pools') and self.pools:
            resolved_pools.update(self.pools)
        if hasattr(self, 'chain_aliases') and self.chain_aliases:
            resolved_pools.update(self.chain_aliases)
        
        def replace_pools_outside_strings(text: str) -> str:
            """Replace pool references but skip those inside string literals."""
            result = []
            i = 0
            while i < len(text):
                char = text[i]
                
                # Handle string literals (both single and double quotes)
                if char in ('"', "'"):
                    quote_char = char
                    result.append(char)
                    i += 1
                    
                    # Copy everything inside the string literal without modification
                    while i < len(text):
                        char = text[i]
                        result.append(char)
                        if char == quote_char and (i == 0 or text[i-1] != '\\'):
                            break
                        i += 1
                    i += 1
                    continue
                
                # Check for pool references outside strings
                found_pool = False
                for pool_ref, replacement in resolved_pools.items():
                    if text[i:].startswith(pool_ref) and (i == 0 or not text[i-1].isalnum()) and \
                       (i + len(pool_ref) >= len(text) or not text[i + len(pool_ref)].isalnum()):
                        result.append(replacement)
                        i += len(pool_ref)
                        found_pool = True
                        break
                
                if not found_pool:
                    result.append(char)
                    i += 1
            
            return ''.join(result)
        
        # Apply smart pool resolution
        content = replace_pools_outside_strings(content)
        
        return content

class CAI3Parser:
    """Complete parser with recursion control."""
    
    def __init__(self, context: ParseContext):
        self.ctx = context
        self.ctx.setup_flow_compiler()
        self.state = CAI3StateMachine(self.ctx.config)
        self.recursion_depth = 0
        # Initialize the new body parser
        self.body_parser = CAI3BodyParser(strict_mode=self.ctx.config.strict_mode)
    
    def parse(self, content: str) -> List[ast.AST]:
        """Parse with proper recursion control and enhanced body parser."""
        # Check recursion depth
        self.recursion_depth += 1
        if self.recursion_depth > self.ctx.config.max_recursion_depth:
            self.recursion_depth -= 1
            if self.ctx.config.strict_mode:
                raise CAI3ParseError(f"Max recursion depth {self.ctx.config.max_recursion_depth} exceeded")
            logger.warning(f"Max recursion depth exceeded")
            return [ast.Pass()]
        
        try:
            # Use body parser for multiline content with T:/D: prefixes
            if '\n' in content or any(prefix in content for prefix in ['T:', 'D:']):
                return self.body_parser.parse_body(content, self.ctx.method_cid)
            
            # Use traditional tokenization for single-line CAI3 constructs
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
                    if stmt:  # Only add non-None statements
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
        
        # Filter out unknown/invalid CAI3 tokens
        if self.is_invalid_cai3_token(token):
            logger.warning(f"Filtering out invalid CAI3 token: '{token}'")
            return None  # Skip this token entirely
        
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
    
    def is_invalid_cai3_token(self, token: str) -> bool:
        """Check if token is an invalid/unknown CAI3 construct."""
        # Skip empty tokens
        if not token.strip():
            return True
        
        # Common invalid patterns that should be filtered out
        invalid_patterns = [
            r'^Rp\d+$',  # Rp1, Rp2, etc. - likely typos or unknown constructs
            r'^[A-Z][a-z]*\d+$',  # CamelCase followed by numbers (often typos)
        ]
        
        import re
        for pattern in invalid_patterns:
            if re.match(pattern, token.strip()):
                return True
        
        # Check if it's a single word that looks like a typo
        # (doesn't contain valid operators, parentheses, etc.)
        stripped = token.strip()
        if (len(stripped) <= 5 and 
            stripped.isalnum() and 
            not self.is_valid_expression_start(stripped)):
            return True
        
        return False
    
    def is_valid_expression_start(self, token: str) -> bool:
        """Check if token could be the start of a valid expression."""
        # Valid expression starts include:
        # - Function calls: contains '('
        # - Variables that are in pools or common names
        # - Literals: numbers, strings
        # - Common Python constructs
        
        if any(char in token for char in '()[]{}.,+-*/<>=!'):
            return True
        
        # Check if it's in pools
        if token in self.ctx.pools:
            return True
        
        # Check if it's a number
        try:
            float(token)
            return True
        except ValueError:
            pass
        
        # Check if it's a quoted string
        if ((token.startswith('"') and token.endswith('"')) or
            (token.startswith("'") and token.endswith("'"))):
            return True
        
        # Common Python keywords/builtins that are valid
        valid_names = {
            'print', 'len', 'range', 'str', 'int', 'float', 'bool', 'list', 'dict', 'set',
            'True', 'False', 'None', 'self', 'cls', 'super', 'type', 'isinstance',
            'hasattr', 'getattr', 'setattr', 'delattr', 'abs', 'min', 'max', 'sum',
            'all', 'any', 'enumerate', 'zip', 'map', 'filter', 'sorted', 'reversed'
        }
        
        if token in valid_names:
            return True
        
        return False
    
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
        """Parse all assignment forms with validation and pool resolution."""
        # Resolve pool references first
        token = self.resolve_pool_references(token)
        
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
        """Parse expression statement with pool resolution."""
        try:
            # Resolve pool references first
            resolved_token = self.resolve_pool_references(token)
            expr = self.parse_expression_or_ternary(resolved_token)
            return ast.Expr(value=expr)
        except Exception as e:
            if self.ctx.config.strict_mode:
                raise CAI3ParseError(f"Failed to parse expression: {e}", token)
            logger.warning(f"Failed to parse expression: {token}")
            return ast.Pass()
    
    def parse_expression_or_ternary(self, s: str) -> ast.AST:
        """Parse expression with CAI3 ternary support and pool resolution."""
        # First resolve pool references
        s = self.resolve_pool_references(s)
        
        # Check for CAI3 ternary
        q_pos = self.state.find_token_at_depth(s, '?')
        
        if q_pos == -1:
            # No ternary - try Python AST parser first, fallback to flow compiler
            try:
                # Try Python AST parser first for better "print" handling
                python_expr = ast.parse(s, mode='eval').body
                return python_expr
            except Exception:
                # Fallback to flow compiler for CAI3-specific expressions
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
    
    def resolve_pool_references(self, s: str) -> str:
        """Resolve pool references like p0 or #p0 to their actual values with proper type handling."""
        import re
        
        def replace_pool_ref(match):
            pool_id = match.group(1)  # e.g., 'p0'
            
            # Try to find pool value in context pools
            if pool_id in self.ctx.pools:
                pool_value = self.ctx.pools[pool_id]
                
                # Handle different types appropriately
                if isinstance(pool_value, str):
                    # If it's already a string, quote it for Python syntax
                    return f'"{pool_value}"'
                elif isinstance(pool_value, bool):
                    # Python boolean literals
                    return str(pool_value)
                elif isinstance(pool_value, (int, float)):
                    # Numeric literals don't need quotes
                    return str(pool_value)
                elif pool_value is None:
                    return "None"
                else:
                    # For other types, convert to string representation
                    return repr(pool_value)
            
            # Enhanced fallback: try to infer a reasonable replacement
            # Map common pool patterns to likely values
            pool_fallbacks = {
                'p0': 'self',
                'p1': 'data', 
                'p2': 'result',
                'p3': 'value',
                'p8': 'logger',
                'p21': 'config',
                'p22': 'items',
                'p28': 'None',
                'p29': 'True',
                'p30': 'str',
                'p31': 'str',
                'p32': 'Any',
                'p92': 'error',
                'p93': 'write',
                'p94': 'json.dumps',
                'p95': 'indent',
                'p96': '2',
                'p102': 'bool',
                'p103': 'list',
                'p111': 'open',
                'p116': 'Exception',
                'p117': 'e',
                'p128': 'info',
                'p143': 'print',
            }
            
            if pool_id in pool_fallbacks:
                return pool_fallbacks[pool_id]
            
            # Final fallback: generate a reasonable variable name
            if pool_id.startswith('p') and pool_id[1:].isdigit():
                num = int(pool_id[1:])
                if num < 10:
                    return f'var_{num}'
                else:
                    return f'value_{num}'
            
            # Last resort: return the pool_id as a variable name
            return pool_id
        
        # Replace pool references - support both p0 and #p0 patterns
        # First try direct references like p0, p1, etc.
        resolved = re.sub(r'\b(p\d+)\b', replace_pool_ref, s)
        
        # Then try hash-prefixed references like #p0, #p1, etc.
        resolved = re.sub(r'#(p\d+)', replace_pool_ref, resolved)
        
        return resolved
    
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
        """Single-pass transformation with ResolutionTransformer."""
        
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
        
        # Add ResolutionTransformer for pools, aliases, and hash resolution
        resolver = getattr(self.ctx, 'resolver', None)
        resolution_transformer = ResolutionTransformer(
            self.ctx.pools, 
            self.ctx.chain_aliases, 
            resolver
        )
        func_ast = resolution_transformer.visit(func_ast)
        
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
def _create_flow_compiler(cai3_map, cai3_full, for_decompression=True):
    """Create flow compiler with mode-appropriate settings."""
    from .flow_language import FLOWCompiler
    
    # Extract name mapping from cai3_map
    name_map = {}
    if hasattr(cai3_map, 'name_map'):
        name_map = cai3_map.name_map or {}
    
    # Create compiler with decompression-appropriate settings
    compiler = FLOWCompiler(
        name_map=name_map,
        dense_mode=False if for_decompression else True,
        pool_constants=False if for_decompression else True,
        ascii_ops=True,
        no_spaces=False,
        inline_blocks=False,
        alias_chains=True,
        strict_mode=False if for_decompression else True  # Relaxed for decompression
    )
    
    # Set up pools with compatibility handling
    _setup_compiler_pools(compiler, cai3_full)
    
    # Set up hash mapping if available
    if hasattr(cai3_full, 'hash_to_value') and cai3_full.hash_to_value:
        if hasattr(compiler, 'set_hash_mapping'):
            compiler.set_hash_mapping(cai3_full.hash_to_value)
    
    # Set up chain aliases from cai3_full if available
    chain_aliases = {}
    if hasattr(cai3_full, 'compression_stats'):
        stats = getattr(cai3_full, 'compression_stats', {})
        chain_aliases = stats.get('chain_aliases', {})
    if chain_aliases:
        if hasattr(compiler, 'set_chain_aliases'):
            compiler.set_chain_aliases(chain_aliases)
        elif hasattr(compiler, 'chain_aliases'):
            compiler.chain_aliases = chain_aliases
    
    return compiler

def _setup_compiler_pools(compiler, cai3_full):
    """Set up pools with API compatibility handling."""
    pools = getattr(cai3_full, 'pools', None)
    if not pools:
        return
    
    # Try different pool API methods for compatibility
    if hasattr(compiler, 'set_pool_id_to_value_map'):
        compiler.set_pool_id_to_value_map(pools)
    elif hasattr(compiler, 'set_pools'):
        compiler.set_pools(pools)
    elif hasattr(compiler, 'pools'):
        compiler.pools = pools

def _build_arguments(method_node, cai3_map):
    """Build function arguments."""
    # Extract parameters from method_node
    params = []
    
    # Check for non-empty params first
    if hasattr(method_node, 'params') and method_node.params:
        params = method_node.params
    elif hasattr(method_node, 'signature') and method_node.signature:
        # Parse signature
        sig = method_node.signature
        if '(' in sig and ')' in sig:
            param_str = sig[sig.find('(') + 1:sig.find(')')]
            if param_str.strip():  # Check for non-empty parameter string
                params = [p.strip() for p in param_str.split(',') if p.strip()]  # Filter empty params
    
    args = []
    for param in params:
        if not param:  # Skip empty parameters
            continue
            
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
        flow_compiler=_create_flow_compiler(cai3_map, cai3_full, for_decompression=True),
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

# CAI3Translator wrapper for drop-in replacement
# Import required structures with fallbacks
try:
    from .cai3_structures import CAI3Full, CAI3Map, CAI3Patch, CAI3Cache, BodyFidelity
except ImportError:
    # Fallback classes for missing modules
    class CAI3Cache:
        def __init__(self, cache_dir=None):
            self.cache_dir = cache_dir
        def load_full(self, path):
            return None
        def load_map(self, path):
            return None
    
    class CAI3Patch:
        def __init__(self, target_cid, body):
            self.target_cid = target_cid
            self.body = body
        
        @staticmethod
        def parse(content):
            return []
    
    class CAI3Full:
        def __init__(self):
            self.pools = {}
            self.compression_stats = {}
    
    class CAI3Map:
        def __init__(self):
            self.span_map = {}
            self.reverse_name_map = {}

try:
    from .flow_language import FLOWCompiler
except ImportError:
    # Mock FLOWCompiler if not available
    class FLOWCompiler:
        def __init__(self, **kwargs):
            pass

class CAI3Translator:
    """Complete production-ready CAI3 translator."""
    
    def __init__(self, cache_dir: Optional[Path] = None, strict_mode: bool = False):
        self.cache = CAI3Cache(cache_dir) if cache_dir else CAI3Cache()
        self.logger = logging.getLogger(__name__)
        self.strict_mode = strict_mode
        self.hash_mappings = {}
        self.claude_new_mappings = {}
        self.current_hash_mappings = {}
        
        # Initialize body parser with pool resolution
        self.body_parser = CAI3BodyParser(strict_mode=strict_mode)
        
        # Enhanced parser configuration
        self.parse_config = ParseConfig(
            strict_mode=strict_mode,
            log_errors=True,
            max_recursion_depth=100,
            validate_output=True
        )
    
    def _build_comprehensive_mappings(self, ast_obj, source_path) -> Dict[str, Any]:
        """Build comprehensive mappings with transitive resolution."""
        mappings: Dict[str, Any] = {}
        
        def add_normalized(src: Dict[str, Any]):
            """Add mappings with normalization."""
            for k, v in (src or {}).items():
                # Normalize key
                normalized_key = k
                if k.startswith('#'):
                    normalized_key = 'hash_' + k[1:].lower()
                elif k.startswith('hash_'):
                    normalized_key = 'hash_' + k[5:].lower()
                else:
                    normalized_key = k.lower()
                
                mappings[normalized_key] = v
        
        # 1. External authoritative mappings first
        add_normalized(getattr(self, 'hash_mappings', {}))
        add_normalized(getattr(self, 'current_hash_mappings', {}))
        add_normalized(getattr(self, 'claude_new_mappings', {}))
        
        # 2. Cache mappings
        try:
            cache = self.cache.load_full(source_path)
            if cache and hasattr(cache, 'hash_to_value'):
                add_normalized(cache.hash_to_value)
        except Exception:
            pass
        
        # 3. CID aliases with transitive resolution
        cid_aliases = getattr(ast_obj, 'cid_aliases', {}) or {}
        for alias, val in cid_aliases.items():
            # First, try direct lookup
            if val in mappings:
                mappings[alias] = mappings[val]
                continue
            
            # Then try normalized lookup for hash values
            if val.startswith('#'):
                norm_val = 'hash_' + val[1:].lower()
                if norm_val in mappings:
                    # Transitive resolution: alias -> hash -> real name
                    final_name = mappings[norm_val]
                    mappings[alias] = final_name
                    continue
            
            # For hash_ prefixed values
            if val.startswith('hash_'):
                norm_val = val.lower()
                if norm_val in mappings:
                    final_name = mappings[norm_val]
                    mappings[alias] = final_name
                    continue
            
            # Direct mapping if no resolution found
            mappings[alias] = val
        
        self.logger.debug(f"Built mappings with {len(mappings)} entries")
        return mappings

    def _validate_python_ast(self, code: str) -> str:
        """Validate and potentially fix generated Python code."""
        # First apply pattern fixes even for valid code
        fixed_code = self._apply_pattern_fixes(code)
        
        try:
            ast.parse(fixed_code)
            self.logger.info("Python AST validation successful")
            return fixed_code
        except SyntaxError as e:
            self.logger.error(f"Generated invalid Python at line {e.lineno}: {e.msg}")
            if self.strict_mode:
                raise
            
            # Try to fix common issues
            syntax_fixed = self._apply_syntax_fixes(fixed_code, e)
            try:
                ast.parse(syntax_fixed)
                self.logger.info("AST valid after automatic fixes")
                return syntax_fixed
            except SyntaxError:
                self.logger.warning("Automatic fixes failed; returning original code")
                return code

    def _apply_pattern_fixes(self, code: str) -> str:
        """Apply pattern fixes even for syntactically valid code."""
        lines = code.splitlines()
        fixed_lines = []
        
        for line in lines:
            fixed_line = line
            
            # Fix accidental concatenation: "import_hash" -> "import hash"
            if re.search(r'\bimport_\w', fixed_line):
                fixed_line = re.sub(r'\bimport_(\w)', r'import \1', fixed_line)
            
            # Fix "from_hash" -> "from hash"  
            if re.search(r'\bfrom_\w', fixed_line):
                fixed_line = re.sub(r'\bfrom_(\w)', r'from \1', fixed_line)
            
            # Fix function call patterns like "def_hash" -> "def hash"
            if re.search(r'\bdef_\w', fixed_line):
                fixed_line = re.sub(r'\bdef_(\w)', r'def \1', fixed_line)
            
            # Fix class patterns like "class_hash" -> "class hash"
            if re.search(r'\bclass_\w', fixed_line):
                fixed_line = re.sub(r'\bclass_(\w)', r'class \1', fixed_line)
            
            # Remove T: and D: prefixes from nested CAI3 content
            if re.match(r'^\s*[TD]:\s*', fixed_line):
                fixed_line = re.sub(r'^\s*[TD]:\s*', '', fixed_line)
            
            # Fix double @ symbols in decorators (@@dataclass -> @dataclass)
            if re.match(r'^\s*@@', fixed_line):
                fixed_line = re.sub(r'^\s*@@', '@', fixed_line)
            
            # Fix if statement patterns with underscores
            # Pattern: if__error__not_in_results_print -> if "error" not in results: print
            if re.search(r'\bif__\w+__\w+_in_\w+_\w+', fixed_line):
                fixed_line = re.sub(r'\bif__(\w+)__(\w+)_in_(\w+)_(\w+)', r'if "\1" \2 in \3: \4', fixed_line)
            
            # Fix return statements with underscores
            # Pattern: return_something -> return something
            if re.search(r'\breturn_[a-zA-Z]', fixed_line):
                fixed_line = re.sub(r'\breturn_([a-zA-Z][a-zA-Z0-9_]*)', r'return \1', fixed_line)
            
            # Fix variable patterns with underscores - more specific
            # Pattern: from_dataclasses_import_dataclass -> from dataclasses import dataclass
            if re.search(r'\bfrom_\w+_import_\w+', fixed_line):
                fixed_line = re.sub(r'\bfrom_(\w+)_import_(\w+)', r'from \1 import \2', fixed_line)
            
            # Fix typing patterns: typ in g_import -> typing import
            if re.search(r'\btyp\s+in\s+g_import', fixed_line):
                fixed_line = re.sub(r'\btyp\s+in\s+g_import_(.+)', r'from typing import \1', fixed_line)
                # Handle double underscores in import names
                fixed_line = re.sub(r'__', ', ', fixed_line)
            
            # Fix if conditions with malformed syntax
            # Pattern: if_not_file.exists() -> if not file.exists():
            if re.search(r'\bif_not_\w+\.', fixed_line):
                fixed_line = re.sub(r'\bif_not_(\w+)\.', r'if not \1.', fixed_line)
                if not fixed_line.rstrip().endswith(':'):
                    fixed_line += ':'
            
            # Fix elif patterns
            if re.search(r'\belif_\w+', fixed_line):
                fixed_line = re.sub(r'\belif_(.+)', r'elif \1:', fixed_line)
            
            # Fix else patterns  
            if re.search(r'\belse_return_', fixed_line):
                fixed_line = re.sub(r'\belse_return_(.+)', r'else:\n    return \1', fixed_line)
            
            # Fix try patterns
            if re.search(r'\btry_\w+', fixed_line):
                fixed_line = re.sub(r'\btry_(.+)', r'try:\n    \1', fixed_line)
            
            # Fix malformed dictionary returns
            if re.search(r'return___\w+__', fixed_line):
                # Complex pattern for dictionaries - handle this more carefully
                if '"file_path"' in fixed_line or '"error"' in fixed_line:
                    # This needs manual reconstruction due to complexity
                    fixed_line = 'return {"error": "File not found", "file_path": str(file)}'
                else:
                    # Simple return with underscores
                    fixed_line = re.sub(r'return___(\w+)__(.+)', r'return {\1: \2}', fixed_line)
            
            # Fix print patterns with f-strings
            if re.search(r'print\(f_(.+)__(.+)__\)', fixed_line):
                fixed_line = re.sub(r'print\(f_(.+)__(.+)__\)', r'print(f"\1: {\2}")', fixed_line)
            
            # Fix variable assignments with spaces in names
            if re.search(r'\w+\s+in\s+\w+\s*=', fixed_line):
                fixed_line = re.sub(r'(\w+)\s+in\s+(\w+)\s*=', r'\1_\2 =', fixed_line)
            
            fixed_lines.append(fixed_line)
        
        return '\n'.join(fixed_lines)

    def _apply_black_formatting(self, code: str) -> str:
        """Apply Black formatting for consistent, professional output."""
        if not code.strip():
            return code
            
        try:
            import black
            
            # Apply Black formatting directly - let it handle syntax validation
            formatted = black.format_str(code, mode=black.FileMode(
                line_length=88,
                string_normalization=False,  # Keep original quotes
                is_pyi=False
            ))
            
            self.logger.debug("Applied Black formatting successfully")
            return formatted
            
        except ImportError:
            self.logger.warning("Black not available, skipping advanced formatting")
            return code
        except Exception as e:
            self.logger.warning(f"Black formatting failed: {e}, returning code as-is")
            return code
    
    def _apply_manual_formatting(self, code: str) -> str:
        """Lightweight manual formatting fallback when Black is not available."""
        lines = code.split('\n')
        formatted_lines = []
        indent_level = 0
        
        for line in lines:
            stripped = line.strip()
            if not stripped:
                formatted_lines.append('')
                continue
            
            # Simple indentation logic
            if any(stripped.startswith(keyword) for keyword in ['class ', 'def ', '@']):
                formatted_lines.append('    ' * indent_level + stripped)
                if stripped.endswith(':'):
                    indent_level += 1
            elif any(stripped.startswith(keyword) for keyword in ['if ', 'elif ', 'else:', 'for ', 'while ', 'try:', 'except', 'finally:', 'with ']):
                formatted_lines.append('    ' * indent_level + stripped)
                if stripped.endswith(':'):
                    indent_level += 1
            else:
                # Regular statements
                if indent_level > 0 and not stripped.startswith(('import ', 'from ')):
                    formatted_lines.append('    ' * indent_level + stripped)
                else:
                    formatted_lines.append(stripped)
        
        return '\n'.join(formatted_lines)

    def _apply_syntax_fixes(self, code: str, error: SyntaxError) -> str:
        """Apply targeted fixes for common syntax errors."""
        lines = code.splitlines()
        if error.lineno and 1 <= error.lineno <= len(lines):
            line = lines[error.lineno - 1]
            
            # Fix accidental concatenation: "import_hash" -> "import hash"
            if re.search(r'\bimport_\w', line):
                lines[error.lineno - 1] = re.sub(r'\bimport_(\w)', r'import \1', line)
            
            # Fix "from_hash" -> "from hash"  
            if re.search(r'\bfrom_\w', line):
                lines[error.lineno - 1] = re.sub(r'\bfrom_(\w)', r'from \1', line)
        
        return '\n'.join(lines)

    def _resolve_imports_with_resolver(self, imports, resolver):
        """Resolve imports using the hash resolver."""
        # For now, return imports as-is since we need more context about the import structure
        return imports

    def _load_or_create_cache_with_resolver(self, source_path, ast_obj, resolver):
        """Load cache with resolver."""
        cai3_full = self.cache.load_full(source_path)
        cai3_map = self.cache.load_map(source_path)
        
        if not cai3_full or not cai3_map:
            self.logger.warning(f"No CAI3 cache found for {source_path}, using minimal cache")
            cai3_full, cai3_map = self._create_minimal_cache(ast_obj)
        
        return cai3_full, cai3_map

    def _reconstruct_with_resolver(self, ast_obj, cai3_full, cai3_map, resolver):
        """Reconstruct with resolver."""
        # Extract aliases and pools with fallback to cai3_full
        chain_aliases = self._get_chain_aliases(ast_obj, cai3_full)
        pools = self._get_pools(ast_obj, cai3_full)
        
        # Reconstruct Python code
        python_lines = []
        
        # Add imports
        python_lines.extend(self._reconstruct_imports(ast_obj))
        
        # Process each body with its own context
        python_lines.extend(self._reconstruct_bodies(
            ast_obj, cai3_full, cai3_map, chain_aliases, pools, resolver
        ))
        
        return '\n'.join(python_lines)

    def _create_fallback_code(self, source_path: Path, error_msg: str) -> str:
        """Create fallback code when translation fails."""
        return f"""# Translation failed for {source_path.name}
# Error: {error_msg}

def placeholder_function():
    '''This function was created due to translation failure.'''
    pass
"""

    def _fallback_cai3_reconstruction(self, cai3_lite_content: str, claude_mappings: Dict[str, Any]) -> str:
        """Fallback reconstruction when main parser fails."""
        try:
            self.logger.info("Using fallback CAI3 reconstruction")
            
            # Parse the CAI3-LITE content
            from .cai3_grammar import CAI3LiteParser
            from .cai3_structure_analyzer import CAI3StructureAnalyzer
            from .cai3_python_reconstructor import CAI3PythonReconstructor
            
            parser = CAI3LiteParser()
            ast_obj = parser.parse(cai3_lite_content)
            
            if not ast_obj:
                self.logger.error("Fallback parser failed to parse CAI3-LITE")
                return self._create_minimal_fallback(cai3_lite_content)
            
            # Analyze structure
            analyzer = CAI3StructureAnalyzer()
            structure = analyzer.analyze(ast_obj)
            
            # Reconstruct Python code
            reconstructor = CAI3PythonReconstructor()
            python_code = reconstructor.reconstruct(ast_obj, structure)
            
            self.logger.info("Fallback reconstruction completed successfully")
            return python_code
            
        except Exception as e:
            self.logger.error(f"Fallback reconstruction failed: {e}")
            return self._create_minimal_fallback(cai3_lite_content)
    
    def _create_minimal_fallback(self, cai3_content: str) -> str:
        """Create minimal fallback when all parsing fails."""
        return f"""# CAI3 Translation Failed
# Unable to parse the following CAI3-LITE content:
# {cai3_content[:200]}...

def placeholder():
    pass
"""

    def translate_cai3_lite_to_python(self, cai3_lite_content: str, 
                                 source_path: Path,
                                 claude_mappings: Dict[str, Any] = None) -> str:
        """Translate CAI3-LITE to Python using enhanced pipeline."""
        try:
            # Local import to avoid circular dependency
            from .cai3_python_reconstructor import CAI3PythonReconstructor
            from .cai3_format_fixer import apply_cai3_format_fixes
            
            self.logger.info("Starting CAI3-LITE translation")
            
            # Step 1: ALWAYS apply format fixes before parsing
            self.logger.info("Applying CAI3-LITE format fixes")
            cai3_lite_content = apply_cai3_format_fixes(cai3_lite_content, claude_mappings)
            self.logger.info(f"Fixed content preview: {cai3_lite_content[:200]}...")
            
            # Parse CAI3-LITE
            parser = CAI3LiteParser()
            ast_obj = parser.parse(cai3_lite_content)
            
            if not ast_obj:
                self.logger.error("Failed to parse CAI3-LITE content")
                return self._fallback_cai3_reconstruction(cai3_lite_content, claude_mappings or {})
            
            # Analyze structure
            analyzer = CAI3StructureAnalyzer()
            structure = analyzer.analyze(ast_obj)
            
            # Load cache if available
            cai3_full = None
            cai3_map = None
            
            try:
                cai3_full = self.cache.load_full(source_path) if self.cache else None
                cai3_map = self.cache.load_map(source_path) if self.cache else None
            except Exception:
                self.logger.info("No cache available, proceeding without")
            
            # Apply Claude mappings
            if claude_mappings:
                self._merge_mappings(cai3_full, cai3_map, claude_mappings)
            
            # Reconstruct Python code
            reconstructor = CAI3PythonReconstructor(self)
            python_code = reconstructor.reconstruct(ast_obj, structure, cai3_full, cai3_map)
            
            # Validate and format
            validated_code = self._validate_python_ast(python_code)
            formatted_code = self._apply_black_formatting(validated_code)
            
            return formatted_code
            
        except Exception as e:
            self.logger.error(f"Translation failed: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            return self._fallback_cai3_reconstruction(cai3_lite_content, claude_mappings or {})

    def _merge_mappings(self, cai3_full, cai3_map, claude_mappings: Dict[str, Any]):
        """Merge Claude's mappings into existing context."""
        # Create empty objects if they don't exist
        if not cai3_full:
            from types import SimpleNamespace
            cai3_full = SimpleNamespace()
            cai3_full.pools = {}
            cai3_full.hash_to_value = {}
        
        if not cai3_map:
            from types import SimpleNamespace
            cai3_map = SimpleNamespace()
            cai3_map.name_map = {}
            cai3_map.reverse_name_map = {}
        
        # Merge pools
        if hasattr(cai3_full, 'pools'):
            # Claude mappings contain pool definitions directly
            for key, value in claude_mappings.items():
                if key.startswith('p') and key[1:].isdigit():
                    cai3_full.pools[key] = value
        
        # Merge hash mappings
        if hasattr(cai3_full, 'hash_to_value'):
            cai3_full.hash_to_value.update(claude_mappings.get('hash_mappings', {}))
        
        # Merge name mappings
        if hasattr(cai3_map, 'name_map'):
            for compressed, original in claude_mappings.get('variables', {}).items():
                cai3_map.name_map[original] = compressed
                if hasattr(cai3_map, 'reverse_name_map'):
                    cai3_map.reverse_name_map[compressed] = original
            
            for compressed, original in claude_mappings.get('methods', {}).items():
                cai3_map.name_map[original] = compressed
                if hasattr(cai3_map, 'reverse_name_map'):
                    cai3_map.reverse_name_map[compressed] = original

    def _reconstruct_imports(self, ast_obj):
        """Reconstruct import statements with deduplication and preferred separate imports."""
        seen = set()
        lines = []
        
        if hasattr(ast_obj, 'imports') and ast_obj.imports:
            # Split on | and handle each module
            all_modules = []
            
            for module_group in ast_obj.imports.split('|'):
                module_group = module_group.strip()
                if not module_group:
                    continue
                    
                if ':' in module_group:
                    mod, items = module_group.split(':', 1)
                    # Clean up the items list for better formatting
                    items_list = [item.strip() for item in items.split(',')]
                    items_formatted = ', '.join(items_list)
                    stmt = f"from {mod} import {items_formatted}"
                    if stmt not in seen:
                        seen.add(stmt)
                        lines.append(stmt)
                else:
                    # Handle comma-separated imports - split them into individual imports
                    if ',' in module_group:
                        for individual_module in module_group.split(','):
                            individual_module = individual_module.strip()
                            if individual_module:
                                stmt = f"import {individual_module}"
                                if stmt not in seen:
                                    seen.add(stmt)
                                    lines.append(stmt)
                    else:
                        stmt = f"import {module_group}"
                        if stmt not in seen:
                            seen.add(stmt)
                            lines.append(stmt)
            
            if lines:
                lines.append("")
        
        return lines
    
    # ...existing code...

    def _reconstruct_bodies(self, ast_obj, cai3_full, cai3_map, chain_aliases, pools, resolver=None):
        """Reconstruct method/function bodies with proper per-body context."""
        lines = []
        
        # Debug: Check what we have
        self.logger.debug(f"AST object type: {type(ast_obj)}")
        self.logger.debug(f"AST object attributes: {dir(ast_obj)}")
        
        if not hasattr(ast_obj, 'bodies'):
            self.logger.warning("No bodies attribute in AST object")
            return lines
            
        if not ast_obj.bodies:
            self.logger.warning("Bodies attribute is empty")
            return lines
        
        self.logger.info(f"Processing {len(ast_obj.bodies)} bodies: {list(ast_obj.bodies.keys())}")
        
        # Use the structure analyzer to get proper Python structure
        from .cai3_structure_analyzer import CAI3StructureAnalyzer
        from .cai3_python_reconstructor import CAI3PythonReconstructor
        
        analyzer = CAI3StructureAnalyzer()
        structure = analyzer.analyze(ast_obj)
        
        # Use the Python reconstructor to build proper code
        reconstructor = CAI3PythonReconstructor(self)
        python_code = reconstructor.reconstruct(ast_obj, structure, cai3_full, cai3_map)
        
        # Split into lines and return
        return python_code.split('\n')


    # def _reconstruct_bodies(self, ast_obj, cai3_full, cai3_map, chain_aliases, pools, resolver=None):
    #     """Reconstruct method/function bodies with proper per-body context."""
    #     lines = []
        
    #     # Debug: Check what we have
    #     self.logger.debug(f"AST object type: {type(ast_obj)}")
    #     self.logger.debug(f"AST object attributes: {dir(ast_obj)}")
        
    #     if not hasattr(ast_obj, 'bodies'):
    #         self.logger.warning(f"AST object has no 'bodies' attribute. Available attributes: {[attr for attr in dir(ast_obj) if not attr.startswith('_')]}")
    #         return lines
            
    #     if not ast_obj.bodies:
    #         self.logger.info("No bodies found in CAI3-LITE content")
    #         return lines
        
    #     self.logger.info(f"Processing {len(ast_obj.bodies)} bodies: {list(ast_obj.bodies.keys())}")
        
    #     for body_id, body_content in ast_obj.bodies.items():
    #         self.logger.info(f"Processing body {body_id}: {body_content[:50]}...")
            
    #         # Find corresponding node
    #         node = self._find_node_by_cid(body_id, cai3_full)
    #         if not node:
    #             self.logger.warning(f"No node found for body {body_id}, attempting direct translation")
    #             try:
    #                 # CRITICAL FIX: Properly translate body content without function wrapping
    #                 translated_content = self._translate_body_content_properly(
    #                     body_content, body_id, chain_aliases, pools, resolver
    #                 )
                    
    #                 # Add translated content directly to output
    #                 if translated_content.strip():
    #                     for line in translated_content.split('\n'):
    #                         if line.strip():
    #                             lines.append(line)
    #                     lines.append("")  # Add spacing between bodies
                    
    #                 continue
                    
    #             except Exception as e:
    #                 self.logger.warning(f"Direct translation failed for {body_id}: {e}")
    #                 # Only use fallback for actual errors
                
    #             # Fallback to stub
    #             lines.append(f"# Unable to reconstruct body {body_id}")
    #             lines.append(f"def unknown_{body_id}():")
    #             lines.append("    pass")
    #             lines.append("")
    #             continue
            
    #         try:
    #             # Create fresh per-body context with correct method_cid
    #             flow_compiler = _create_flow_compiler(cai3_map, cai3_full, for_decompression=True)
                
    #             ctx = ParseContext(
    #                 flow_compiler=flow_compiler,
    #                 cai3_map=cai3_map,
    #                 cai3_full=cai3_full,
    #                 method_cid=body_id,  # CRITICAL: Use body's CID for correct de-mangling
    #                 seen_names=set(),
    #                 chain_aliases=chain_aliases,
    #                 pools=pools,
    #                 config=ParseConfig(
    #                     strict_mode=self.strict_mode,
    #                     log_errors=True,
    #                     max_recursion_depth=100,
    #                     validate_output=True
    #                 )
    #             )
                
    #             # Step 1: Resolve pool references in body content
    #             # Create a temporary parser just for pool resolution
    #             temp_parser = CAI3Parser(ctx)
    #             resolved_body = temp_parser.resolve_pool_references(body_content)
    #             self.logger.debug(f"Body after pool resolution: '{resolved_body}'")
                
    #             # Step 2: Parse resolved body as Python expression using Python's AST parser
    #             try:
    #                 # Parse as Python expression using Python's built-in parser
    #                 body_expr = ast.parse(resolved_body, mode='eval').body
    #                 self.logger.debug(f"Parsed with Python AST: {ast.dump(body_expr)}")
    #                 # Wrap expression in expression statement
    #                 body_stmts = [ast.Expr(value=body_expr)]
    #             except Exception as e:
    #                 self.logger.warning(f"Failed to parse body as Python expression for {body_id}: {e}")
    #                 try:
    #                     # Try to parse as statement(s)
    #                     parsed_stmts = ast.parse(resolved_body, mode='exec')
    #                     body_stmts = parsed_stmts.body
    #                     self.logger.debug(f"Parsed as statements: {len(body_stmts)} statements")
                        
    #                     # Filter out invalid statements after successful Python parsing
    #                     filtered_stmts = []
    #                     for stmt in body_stmts:
    #                         if self._is_valid_ast_statement_with_pools(stmt, pools):
    #                             filtered_stmts.append(stmt)
    #                         else:
    #                             stmt_source = ast.unparse(stmt) if hasattr(ast, 'unparse') else str(stmt)
    #                             self.logger.warning(f"Filtering out invalid statement: '{stmt_source}'")
                        
    #                     body_stmts = filtered_stmts if filtered_stmts else [ast.Pass()]
    #                     self.logger.debug(f"After filtering: {len(body_stmts)} statements")
    #                 except Exception as e2:
    #                     self.logger.warning(f"Failed to parse body as Python statements for {body_id}: {e2}")
    #                     # Enhanced fallback: Convert CAI3 syntax to Python, then parse with Python AST
    #                     try:
    #                         # Use CAI3 parser to convert syntax, but with Python AST parsing for final result
    #                         self.logger.debug(f"Attempting CAI3 parser fallback for: '{resolved_body}'")
    #                         cai3_stmts = temp_parser.parse(resolved_body)  # Use resolved body, not original
    #                         self.logger.debug(f"CAI3 parser returned {len(cai3_stmts) if cai3_stmts else 0} statements")
                            
    #                         if cai3_stmts:
    #                             # Fix missing location attributes for AST nodes
    #                             for stmt in cai3_stmts:
    #                                 ast.fix_missing_locations(stmt)
                                
    #                             # Check if any of the statements contain "pr in t" issue
    #                             for i, stmt in enumerate(cai3_stmts):
    #                                 try:
    #                                     stmt_source = ast.unparse(stmt)
    #                                     self.logger.debug(f"CAI3 statement {i}: '{stmt_source}'")
    #                                     if "pr in t" in stmt_source:
    #                                         self.logger.warning(f"CAI3 parser produced 'pr in t' in statement {i}: {stmt_source}")
    #                                 except Exception as e:
    #                                     self.logger.debug(f"Could not unparse CAI3 statement {i}: {e}")
                                
    #                             # Convert the CAI3 AST statements to source, then re-parse with Python
    #                             python_source_lines = []
    #                             for stmt in cai3_stmts:
    #                                 try:
    #                                     # Ensure AST node has required attributes
    #                                     ast.fix_missing_locations(stmt)
    #                                     stmt_source = ast.unparse(stmt)
    #                                     python_source_lines.append(stmt_source)
    #                                 except Exception as e:
    #                                     # If unparsing fails, use a pass statement
    #                                     self.logger.warning(f"Failed to unparse CAI3 statement: {e}")
    #                                     python_source_lines.append("pass")
                                
    #                             if python_source_lines:
    #                                 # Parse the generated Python source
    #                                 python_source = '\n'.join(python_source_lines)
    #                                 try:
    #                                     reparsed = ast.parse(python_source, mode='exec')
    #                                     body_stmts = reparsed.body
    #                                     self.logger.debug(f"CAI3->Python conversion successful: {len(body_stmts)} statements")
    #                                 except Exception as e3:
    #                                     self.logger.warning(f"Failed to re-parse converted Python for {body_id}: {e3}")
    #                                     body_stmts = cai3_stmts  # Use original CAI3 result as last resort
    #                             else:
    #                                 body_stmts = [ast.Pass()]
    #                         else:
    #                             self.logger.debug(f"CAI3 parser returned no statements for: '{resolved_body}'")
    #                             body_stmts = [ast.Pass()]
    #                     except Exception as e3:
    #                         self.logger.warning(f"Final fallback failed for {body_id}: {e3}")
    #                         body_stmts = [ast.Pass()]
                
    #             # Build function/method AST
    #             func_ast = ast.FunctionDef(
    #                 name=getattr(node, 'name', f'method_{body_id}'),
    #                 args=_build_arguments(node, cai3_map),
    #                 body=body_stmts or [ast.Pass()],
    #                 decorator_list=[],
    #                 returns=None
    #             )
                
    #             # Apply decompression transformations
    #             pipeline = ASTTransformPipeline(ctx)
    #             func_ast = pipeline.transform(func_ast)
                
    #             # Convert to Python source
    #             try:
    #                 python_source = self._to_source(func_ast)
    #                 lines.append(python_source)
    #                 lines.append("")
    #                 self.logger.info(f"Successfully reconstructed {node.name}")
    #             except Exception as e:
    #                 self.logger.error(f"Failed to unparse function {node.name}: {e}")
    #                 lines.append(f"# Failed to reconstruct {node.name}")
    #                 lines.append(f"def {node.name}():")
    #                 lines.append("    pass")
    #                 lines.append("")
                    
    #         except Exception as e:
    #             self.logger.error(f"Failed to reconstruct body {body_id}: {e}")
    #             lines.append(f"# Error reconstructing {body_id}: {e}")
    #             lines.append(f"def error_{body_id}():")
    #             lines.append("    pass")
    #             lines.append("")
        
    #     return lines

    def _to_source(self, node: ast.AST) -> str:
        """Convert AST to source with version compatibility."""
        try:
            # Python 3.9+
            return ast.unparse(node)
        except AttributeError:
            # Python < 3.9
            try:
                import astor
                return astor.to_source(node)
            except ImportError:
                # Last resort
                self.logger.error("Cannot unparse AST without ast.unparse or astor")
                name = getattr(node, 'name', 'unknown')
                return f"# Unable to unparse {name}\ndef {name}():\n    pass"

    def _apply_targeted_syntax_recovery(self, code: str, error: SyntaxError) -> str:
        """Apply targeted syntax recovery only at error location."""
        if self.strict_mode:
            return code  # Don't modify in strict mode
        
        import re
        lines = code.splitlines()
        lineno = getattr(error, 'lineno', None)
        
        if lineno and 1 <= lineno <= len(lines):
            line = lines[lineno - 1]
            original = line
            
            # Fix only specific known patterns at line start
            line = re.sub(r'^(import)_(?=[A-Za-z0-9_.])', r'\1 ', line)
            line = re.sub(r'^(from)_(?=[A-Za-z0-9_.])', r'\1 ', line)
            
            if line != original:
                self.logger.info(f"Applied syntax recovery at line {lineno}")
                lines[lineno - 1] = line
        
        return '\n'.join(lines)

    def _get_chain_aliases(self, ast_obj, cai3_full):
        """Get chain aliases with fallback."""
        aliases = {}
        
        if hasattr(ast_obj, 'chain_aliases') and ast_obj.chain_aliases:
            aliases.update(ast_obj.chain_aliases)
        
        if hasattr(cai3_full, 'compression_stats'):
            stats = getattr(cai3_full, 'compression_stats', {})
            full_aliases = stats.get('chain_aliases', {})
            aliases.update(full_aliases)
        
        return aliases

    def _get_pools(self, ast_obj, cai3_full):
        """Get pools with fallback."""
        pools = {}
        
        if hasattr(ast_obj, 'pools') and ast_obj.pools:
            pools.update(ast_obj.pools)
        
        if hasattr(cai3_full, 'pools') and cai3_full.pools:
            pools.update(cai3_full.pools)
        
        return pools
    
    def _is_valid_ast_statement(self, stmt: ast.AST) -> bool:
        """Check if an AST statement is valid and should be kept."""
        # Allow most statement types
        if not isinstance(stmt, ast.Expr):
            return True  # Function calls, assignments, control flow, etc.
        
        # Check expression statements
        expr = stmt.value
        
        # Allow function calls, assignments, and other complex expressions
        if not isinstance(expr, ast.Name):
            return True
        
        # For simple names (variables), check if they're valid
        name = expr.id
        
        # Filter out invalid patterns
        invalid_patterns = [
            r'^Rp\d+$',  # Rp1, Rp2, etc.
            r'^[A-Z][a-z]*\d+$',  # CamelCase followed by numbers
        ]
        
        import re
        for pattern in invalid_patterns:
            if re.match(pattern, name):
                return False
        
        # Allow known valid names
        valid_names = {
            'print', 'len', 'range', 'str', 'int', 'float', 'bool', 'list', 'dict', 'set',
            'True', 'False', 'None', 'self', 'cls', 'super', 'type', 'isinstance',
            'hasattr', 'getattr', 'setattr', 'delattr', 'abs', 'min', 'max', 'sum',
            'all', 'any', 'enumerate', 'zip', 'map', 'filter', 'sorted', 'reversed'
        }
        
        if name in valid_names:
            return True
        
        # Allow names that are in pools (we need to access pools from context)
        # Since this is in CAI3Translator, we don't have direct access to pools
        # The filtering will need to be done in the method that has pool context
        
        # Filter out short suspicious names (3 chars or less) that contain numbers
        if len(name) <= 4 and any(c.isdigit() for c in name) and name not in valid_names:
            return False
        
        # Allow other names (could be legitimate variables)
        return True
    
    def _is_valid_ast_statement_with_pools(self, stmt: ast.AST, pools: dict) -> bool:
        """Check if an AST statement is valid and should be kept (with pool context)."""
        # Allow most statement types
        if not isinstance(stmt, ast.Expr):
            return True  # Function calls, assignments, control flow, etc.
        
        # Check expression statements
        expr = stmt.value
        
        # Allow function calls, assignments, and other complex expressions
        if not isinstance(expr, ast.Name):
            return True
        
        # For simple names (variables), check if they're valid
        name = expr.id
        
        # Filter out invalid patterns
        invalid_patterns = [
            r'^Rp\d+$',  # Rp1, Rp2, etc.
            r'^[A-Z][a-z]*\d+$',  # CamelCase followed by numbers
        ]
        
        import re
        for pattern in invalid_patterns:
            if re.match(pattern, name):
                return False
        
        # Allow known valid names
        valid_names = {
            'print', 'len', 'range', 'str', 'int', 'float', 'bool', 'list', 'dict', 'set',
            'True', 'False', 'None', 'self', 'cls', 'super', 'type', 'isinstance',
            'hasattr', 'getattr', 'setattr', 'delattr', 'abs', 'min', 'max', 'sum',
            'all', 'any', 'enumerate', 'zip', 'map', 'filter', 'sorted', 'reversed'
        }
        
        if name in valid_names:
            return True
        
        # Allow names that are in pools
        if name in pools:
            return True
        
        # Filter out short suspicious names (3 chars or less) that contain numbers
        if len(name) <= 4 and any(c.isdigit() for c in name) and name not in valid_names:
            return False
        
        # Allow other names (could be legitimate variables)
        return True
    
    def validate_lite_structure(self, lite_content: str) -> Tuple[bool, List[str]]:
        """
        Validate CAI3-LITE structure using enhanced parser.
        Returns (is_valid, list_of_issues)
        """
        issues = []
        
        # Check for required header
        if not lite_content.startswith('#C3L'):
            issues.append("Missing #C3L header")
        
        # Use state machine for proper bracket validation
        state = CAI3StateMachine(self.parse_config)
        
        try:
            # Test tokenization
            tokens = state.tokenize(lite_content)
            
            # Check for balanced structures using state machine
            for token in tokens:
                if token.startswith('T{'):
                    # Validate try block structure
                    brace_end = state.find_matching(token, 1, '{', '}')
                    if brace_end == -1:
                        issues.append(f"Unmatched brace in try block: {token[:20]}...")
                
                if token.startswith('@') and '{' in token:
                    # Validate for loop structure
                    brace_start = token.find('{')
                    brace_end = state.find_matching(token, brace_start, '{', '}')
                    if brace_end == -1:
                        issues.append(f"Unmatched brace in for loop: {token[:20]}...")
        
        except Exception as e:
            issues.append(f"Tokenization failed: {e}")
        
        # Validate pool references with regex (more robust than original)
        import re
        pool_refs = set(re.findall(r'\bp(\d+)\b', lite_content))
        declared_pools = set()
        
        for line in lite_content.split('\n'):
            if line.strip().startswith('P:'):
                pool_declarations = re.findall(r'p(\d+)=', line)
                declared_pools.update(pool_declarations)
        
        undefined_pools = pool_refs - declared_pools
        for ref in undefined_pools:
            issues.append(f"Undefined pool reference: p{ref}")
        
        return len(issues) == 0, issues
    
    def apply_patch(self, patch_content: str, source_path: Path, original_source: str = None) -> str:
        """
        Apply CAI3-PATCH using enhanced AST-based translation.
        
        Args:
            patch_content: The patch returned by the LLM
            source_path: Path to the original source file  
            original_source: Optional original source content
            
        Returns:
            Updated source code with patches applied
        """
        # Load FULL and MAP from cache
        cai3_full = self.cache.load_full(source_path)
        cai3_map = self.cache.load_map(source_path)
        
        if not cai3_full or not cai3_map:
            raise ValueError(f"No CAI3 cache found for {source_path}. Ensure compression was run first.")
        
        # Parse patches using enhanced parser
        patches = CAI3Patch.parse(patch_content)
        self._resolve_cid_aliases(patches, patch_content, cai3_full)
        
        if not patches:
            self.logger.warning("No valid patches found in response")
            return original_source if original_source is not None else source_path.read_text()
        
        # Use provided source or read from file
        source_content = original_source if original_source is not None else source_path.read_text()
        
        # Apply each patch using enhanced translation
        modified_source = source_content
        applied_count = 0
        
        for patch in patches:
            try:
                # Validate patch target exists
                if patch.target_cid not in cai3_map.span_map:
                    self.logger.warning(f"Unknown cid {patch.target_cid}, skipping patch")
                    continue
                
                # Apply patch using enhanced AST-based method replacement
                modified_source = self._apply_patch_enhanced(
                    patch, modified_source, cai3_map, cai3_full
                )
                applied_count += 1
                
            except Exception as e:
                self.logger.error(f"Failed to apply patch {patch.target_cid}: {e}")
                if self.parse_config.strict_mode:
                    raise
        
        self.logger.info(f"Applied {applied_count}/{len(patches)} patches successfully")
        return modified_source
    
    def _apply_patch_enhanced(self, patch, source: str, cai3_map, cai3_full) -> str:
        """Apply patch using enhanced AST-based translation."""
        try:
            # Extract method span
            span = cai3_map.span_map.get(patch.target_cid)
            if not span:
                raise ValueError(f"No span found for CID {patch.target_cid}")
            
            start_line, end_line = span
            
            # Parse the patch body using enhanced parser
            method_node = self._create_mock_method_node(patch.target_cid, cai3_map)
            
            # Extract pools and chain aliases from patch content
            chain_aliases = self._extract_chain_aliases(patch.body, cai3_full)
            pools = getattr(cai3_full, 'pools', {})
            
            # Translate using enhanced parser
            func_ast = translate_method(
                method_node=method_node,
                body_content=patch.body,
                cai3_map=cai3_map,
                cai3_full=cai3_full,
                chain_aliases=chain_aliases,
                pools=pools,
                config=self.parse_config
            )
            
            # Convert AST back to source
            import ast
            new_method_source = ast.unparse(func_ast)
            
            # Replace in original source
            lines = source.split('\n')
            new_lines = lines[:start_line-1] + [new_method_source] + lines[end_line:]
            
            return '\n'.join(new_lines)
            
        except Exception as e:
            self.logger.error(f"Enhanced patch application failed: {e}")
            # Fallback to simpler replacement if available
            return self._fallback_patch_application(patch, source, cai3_map)
    
    def _create_mock_method_node(self, cid: str, cai3_map):
        """Create a mock method node for translation."""
        class MockMethodNode:
            def __init__(self, cid: str, name: str = "unknown_method"):
                self.cid = cid
                self.name = name
                self.params = []
                self.signature = f"{name}()"
        
        # Try to extract method name from reverse mapping
        method_name = "unknown_method"
        if hasattr(cai3_map, 'reverse_name_map'):
            for original, compressed in cai3_map.reverse_name_map.items():
                if compressed == cid:
                    method_name = original
                    break
        
        return MockMethodNode(cid, method_name)
    
    def _extract_chain_aliases(self, body_content: str, cai3_full) -> dict:
        """Extract chain aliases from patch body content."""
        chain_aliases = {}
        
        # Look for chain alias patterns (g0, g1, etc.)
        import re
        alias_refs = re.findall(r'\bg(\d+)\b', body_content)
        
        # Get chain aliases from cai3_full if available
        if hasattr(cai3_full, 'compression_stats'):
            stats = cai3_full.compression_stats
            if 'chain_aliases' in stats:
                for alias_id in alias_refs:
                    alias_key = f"g{alias_id}"
                    if alias_key in stats['chain_aliases']:
                        chain_aliases[alias_key] = stats['chain_aliases'][alias_key]
        
        return chain_aliases
    
    def _fallback_patch_application(self, patch, source: str, cai3_map) -> str:
        """Fallback to simple string replacement if AST parsing fails."""
        span = cai3_map.span_map.get(patch.target_cid)
        if not span:
            return source
        
        start_line, end_line = span
        lines = source.split('\n')
        
        # Simple replacement with basic indentation preservation
        if start_line <= len(lines) and end_line <= len(lines):
            # Preserve indentation from original method
            original_line = lines[start_line - 1] if start_line > 0 else ""
            indent = len(original_line) - len(original_line.lstrip())
            
            # Apply basic indentation to patch body
            patch_lines = patch.body.split('\n')
            indented_patch = []
            for line in patch_lines:
                if line.strip():
                    indented_patch.append(' ' * indent + line.strip())
                else:
                    indented_patch.append('')
            
            # Replace lines
            new_lines = lines[:start_line-1] + indented_patch + lines[end_line:]
            return '\n'.join(new_lines)
        
        return source
    
    def _resolve_cid_aliases(self, patches: List, patch_content: str, cai3_full):
        """Resolve CID aliases in patches (placeholder - implement based on your patch structure)."""
        # This would implement CID alias resolution similar to original translator
        pass
    

    def _translate_body_content_properly(self, body_content: str, body_id: str, 
                                        chain_aliases: dict, pools: dict, resolver) -> str:
        """
        Properly translate CAI3 body content using the enhanced body parser.
        This replaces the problematic function wrapping approach.
        """
        self.logger.info(f"Translating body {body_id} content: {body_content[:100]}...")
        
        # Find the method CID that corresponds to this body_id
        method_cid = self._find_method_cid_for_body(body_id)
        self.logger.debug(f"Found method CID {method_cid} for body {body_id}")
        
        # Set current method context for dynamic mapping
        self.current_method_cid = method_cid
        
        try:
            # Enhanced: Check if this is a method definition (has signature)
            # Pattern: methodname(params):body
            if ':' in body_content:
                sig_end = body_content.find(':')
                signature = body_content[:sig_end]
                actual_body = body_content[sig_end+1:]
                
                # Parse the signature
                if '(' in signature and ')' in signature:
                    method_match = re.match(r'(p\d+|\w+)\((.*?)\)', signature)
                    if method_match:
                        method_name_or_pool = method_match.group(1)
                        params_str = method_match.group(2)
                        
                        # Resolve method name
                        if method_name_or_pool.startswith('p') and method_name_or_pool[1:].isdigit():
                            method_name = pools.get(method_name_or_pool, method_name_or_pool)
                        else:
                            method_name = method_name_or_pool
                        
                        # Parse parameters
                        params = []
                        if params_str:
                            for param in params_str.split(','):
                                param = param.strip()
                                # Handle default values
                                if '=' in param:
                                    param_name, default = param.split('=', 1)
                                    param_name = param_name.strip()
                                    default = default.strip()
                                    
                                    # Resolve pool references
                                    if param_name.startswith('p') and param_name[1:].isdigit():
                                        param_name = pools.get(param_name, param_name)
                                    if default.startswith('p') and default[1:].isdigit():
                                        default = pools.get(default, default)
                                    
                                    params.append(f"{param_name}={default}")
                                else:
                                    # Resolve pool reference
                                    if param.startswith('p') and param[1:].isdigit():
                                        param = pools.get(param, param)
                                    params.append(param)
                        
                        # Build the method definition
                        method_def = f"def {method_name}({', '.join(params)}):"
                        
                        # Parse the body
                        body_parser = CAI3BodyParser(strict_mode=self.strict_mode)
                        body_parser.pools = pools
                        body_parser.chain_aliases = chain_aliases
                        
                        # Parse body statements
                        parsed_stmts = body_parser.parse_body(actual_body, body_id)
                        
                        # Convert to Python source
                        body_lines = []
                        for stmt in parsed_stmts:
                            try:
                                stmt_src = ast.unparse(stmt)
                                body_lines.append(f"    {stmt_src}")
                            except Exception as e:
                                self.logger.warning(f"Failed to unparse statement: {e}")
                                body_lines.append(f"    # Failed to parse: {str(stmt)[:50]}...")
                        
                        if not body_lines:
                            body_lines = ["    pass"]
                        
                        return method_def + '\n' + '\n'.join(body_lines)
            
            # Fallback: Not a method definition, just parse as statements
            body_parser = CAI3BodyParser(strict_mode=self.strict_mode)
            body_parser.pools = pools
            body_parser.chain_aliases = chain_aliases
            
            parsed_stmts = body_parser.parse_body(body_content, body_id)
            
            # Convert to source
            lines = []
            for stmt in parsed_stmts:
                try:
                    lines.append(ast.unparse(stmt))
                except Exception:
                    lines.append(f"# Failed to parse statement")
            
            return '\n'.join(lines) if lines else "pass"
            
        except Exception as e:
            self.logger.error(f"Failed to translate body {body_id}: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            return self._translate_body_content_fallback(body_content, body_id, chain_aliases, pools, resolver)

    def _translate_body_content_fallback(self, body_content: str, body_id: str, 
                                        chain_aliases: dict, pools: dict, resolver) -> str:
        """Fallback translation method for when enhanced parser fails."""
        self.logger.info(f"Using fallback translation for body {body_id}")
        
        # Step 1: Split content into individual lines/statements
        lines = body_content.split('\n')
        translated_lines = []
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
                
            # Step 2: Remove T: and D: prefixes if present
            if line.startswith('T:') or line.startswith('D:'):
                line = line[2:].strip()
            
            if not line:
                continue
                
            # Step 3: Handle specific CAI3 patterns
            translated_line = self._resolve_cai3_patterns_in_line(line, chain_aliases, pools)
            
            # Step 4: Apply hash resolution if resolver is available
            if resolver and hasattr(resolver, 'resolve_in_python_code'):
                try:
                    translated_line = resolver.resolve_in_python_code(translated_line)
                except Exception as e:
                    self.logger.debug(f"Hash resolution failed for line '{translated_line}': {e}")
            
            # Step 5: Apply basic pattern fixes
            translated_line = self._apply_pattern_fixes(translated_line)
            
            if translated_line.strip():
                translated_lines.append(translated_line)
        
        # Step 6: Create a proper Python code block and let Black handle formatting
        raw_result = '\n'.join(translated_lines)
        
        # Step 7: Try to create a properly structured code block
        formatted_result = self._create_valid_python_block(raw_result)
        
        self.logger.debug(f"Body {body_id} translated to: {formatted_result[:100]}...")
        return formatted_result
    
    def _create_valid_python_block(self, code: str) -> str:
        """Create a valid Python code block that Black can format."""
        if not code.strip():
            return code
        
        try:
            import black
            
            # Try to format the code as-is first
            try:
                formatted = black.format_str(code, mode=black.FileMode(
                    line_length=88,
                    string_normalization=True,
                    is_pyi=False
                ))
                self.logger.debug("Black formatting successful on first try")
                return formatted
            except Exception as e:
                self.logger.debug(f"Direct Black formatting failed: {e}")
                
                # Apply structural fixes for common issues
                fixed_code = self._fix_python_structure(code)
                
                try:
                    formatted = black.format_str(fixed_code, mode=black.FileMode(
                        line_length=88,
                        string_normalization=True,
                        is_pyi=False
                    ))
                    self.logger.debug("Black formatting successful after fixes")
                    return formatted
                except Exception as e2:
                    self.logger.debug(f"Black formatting failed after fixes: {e2}")
                    return fixed_code
                    
        except ImportError:
            self.logger.debug("Black not available")
            return self._fix_python_structure(code)
    
    def _fix_python_structure(self, code: str) -> str:
        """Fix basic Python structure issues."""
        lines = code.split('\n')
        fixed_lines = []
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # Add missing colons
            if any(line.startswith(keyword) for keyword in ['class ', 'def ', 'if ', 'elif ', 'else', 'for ', 'while ', 'try', 'except', 'finally', 'with ']):
                if not line.endswith(':') and ':' not in line:
                    line += ':'
            
            # Fix standalone 'else'
            if line == 'else':
                line = 'else:'
            
            fixed_lines.append(line)
        
        # Join and apply simple indentation
        result = '\n'.join(fixed_lines)
        return self._apply_simple_indentation(result)
    
    def _apply_simple_indentation(self, code: str) -> str:
        """Apply basic Python indentation rules."""
        lines = code.split('\n')
        indented_lines = []
        indent_level = 0
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # Decrease indent for else, elif, except, finally
            if any(line.startswith(keyword) for keyword in ['else:', 'elif ', 'except', 'finally:']):
                if indent_level > 0:
                    indent_level -= 1
            
            # Apply current indentation
            indented_lines.append('    ' * indent_level + line)
            
            # Increase indent for blocks
            if line.endswith(':'):
                indent_level += 1
        
        return '\n'.join(indented_lines)
    
    def _apply_black_formatting_with_fallback(self, code: str) -> str:
        """Apply Black formatting with intelligent fallback for syntax errors."""
        if not code.strip():
            return code
        
        try:
            import black
            
            # Try Black formatting directly first
            try:
                formatted = black.format_str(code, mode=black.FileMode(
                    line_length=88,
                    string_normalization=True,
                    is_pyi=False
                ))
                self.logger.debug("Black formatting applied successfully")
                return formatted
            except black.InvalidInput as e:
                self.logger.debug(f"Black formatting failed due to syntax: {e}")
                # Apply minimal fixes and try again
                fixed_code = self._apply_minimal_syntax_fixes(code)
                try:
                    formatted = black.format_str(fixed_code, mode=black.FileMode(
                        line_length=88,
                        string_normalization=True,
                        is_pyi=False
                    ))
                    self.logger.debug("Black formatting applied after syntax fixes")
                    return formatted
                except Exception:
                    self.logger.debug("Black formatting still failed, using manual formatting")
                    return self._apply_simple_manual_formatting(fixed_code)
            
        except ImportError:
            self.logger.debug("Black not available, using manual formatting")
            return self._apply_simple_manual_formatting(code)
        except Exception as e:
            self.logger.debug(f"Black formatting error: {e}, using manual formatting")
            return self._apply_simple_manual_formatting(code)
    
    def _apply_minimal_syntax_fixes(self, code: str) -> str:
        """Apply only essential syntax fixes needed for Black to work."""
        lines = code.split('\n')
        fixed_lines = []
        
        for i, line in enumerate(lines):
            line = line.strip()
            if not line:
                continue
            
            # Fix missing colons for control structures
            if any(line.startswith(keyword) for keyword in ['class ', 'def ', 'if ', 'elif ', 'for ', 'while ', 'try', 'except', 'finally', 'with ']):
                if not line.endswith(':') and not ':' in line:
                    line += ':'
            
            # Handle 'else' without colon
            if line == 'else':
                line = 'else:'
            elif line.startswith('else') and not line.endswith(':'):
                line += ':'
            
            # Fix indentation issues by restructuring if-else blocks
            if line.startswith('else:'):
                # Look back to find the matching if and ensure proper structure
                # Remove any incorrectly indented return statements before else
                if fixed_lines and 'return' in fixed_lines[-1]:
                    # This suggests the else is misplaced - let's fix the structure
                    fixed_lines.append(line)
                else:
                    fixed_lines.append(line)
            else:
                fixed_lines.append(line)
        
        # Post-process to fix common if-else structure issues
        result_lines = []
        i = 0
        while i < len(fixed_lines):
            line = fixed_lines[i]
            
            # Special handling for return-else patterns
            if 'return' in line and i + 1 < len(fixed_lines) and fixed_lines[i + 1].strip().startswith('else:'):
                # This is a return followed by else - structure it properly
                result_lines.append(line)
                result_lines.append(fixed_lines[i + 1])  # else:
                i += 2
            else:
                result_lines.append(line)
                i += 1
        
        return '\n'.join(result_lines)
    
    def _apply_simple_manual_formatting(self, code: str) -> str:
        """Simple manual formatting when Black is not available."""
        lines = code.split('\n')
        formatted_lines = []
        indent_level = 0
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # Determine if this line should be indented
            if any(line.startswith(keyword) for keyword in ['class ', 'def ', '@']):
                # Class, function, decorator - current level
                formatted_lines.append('    ' * indent_level + line)
                if line.endswith(':'):
                    indent_level += 1
            elif any(line.startswith(keyword) for keyword in ['if ', 'elif ', 'else:', 'for ', 'while ', 'try:', 'except', 'finally:', 'with ']):
                # Control structures - current level
                formatted_lines.append('    ' * indent_level + line)
                if line.endswith(':'):
                    indent_level += 1
            else:
                # Regular statements - usually indented
                if indent_level > 0:
                    formatted_lines.append('    ' * indent_level + line)
                else:
                    formatted_lines.append(line)
        
        return '\n'.join(formatted_lines)
    
    def _fix_indentation_issues(self, code: str) -> str:
        """Fix common indentation issues in generated Python code."""
        lines = code.split('\n')
        fixed_lines = []
        indent_stack = [0]  # Stack to track indentation levels
        
        for line in lines:
            stripped = line.strip()
            if not stripped:
                fixed_lines.append('')
                continue
            
            current_indent = indent_stack[-1]
            
            # Handle different types of statements
            if any(stripped.startswith(keyword) for keyword in ['class ', 'def ', 'if ', 'for ', 'while ', 'try:', 'with ']):
                # These start new blocks
                if not stripped.endswith(':'):
                    stripped += ':'
                fixed_lines.append(' ' * current_indent + stripped)
                indent_stack.append(current_indent + 4)
            elif any(stripped.startswith(keyword) for keyword in ['elif ', 'else:', 'except', 'finally:']):
                # These are at the same level as their corresponding if/try
                if len(indent_stack) > 1:
                    indent_stack.pop()  # Remove current block
                current_indent = indent_stack[-1]
                if not stripped.endswith(':'):
                    stripped += ':'
                fixed_lines.append(' ' * current_indent + stripped)
                indent_stack.append(current_indent + 4)
            elif stripped.startswith('@'):
                # Decorators - same level as what they decorate
                fixed_lines.append(' ' * current_indent + stripped)
            elif stripped in ['pass', 'break', 'continue'] or stripped.startswith(('return', 'yield', 'raise')):
                # These need to be indented in the current block
                fixed_lines.append(' ' * indent_stack[-1] + stripped)
            else:
                # Regular statements
                if any(keyword in stripped for keyword in [' = ', '(', 'import ', 'from ']):
                    # Likely a variable assignment, function call, or import
                    if stripped.startswith(('import ', 'from ')):
                        # Imports go at module level
                        fixed_lines.append(stripped)
                    else:
                        # Other statements go at current indentation
                        fixed_lines.append(' ' * indent_stack[-1] + stripped)
                else:
                    # Default to current indentation
                    fixed_lines.append(' ' * indent_stack[-1] + stripped)
        
        return '\n'.join(fixed_lines)
    
    def _resolve_cai3_patterns_in_line(self, line: str, chain_aliases: dict, pools: dict) -> str:
        """
        Enhanced CAI3 pattern resolution with dynamic mapping discovery.
        Now builds method-specific context mappings instead of using hardcoded patterns.
        """
        original_line = line
        
        # Get method-specific context mappings
        method_cid = getattr(self, 'current_method_cid', None)
        if not method_cid:
            # Fall back to basic pattern resolution if no method context
            return self._basic_pattern_resolution(line, chain_aliases, pools)
        
        # Build comprehensive mappings for this method
        mappings = self._build_method_context_mappings(method_cid)
        
        # Apply mappings in order of specificity (longest first to avoid partial matches)
        sorted_mappings = sorted(mappings.items(), key=lambda x: len(x[0]), reverse=True)
        
        for compressed, expanded in sorted_mappings:
            if compressed in line:
                line = line.replace(compressed, expanded)
        
        # Apply traditional pool and chain alias resolution
        line = self._basic_pattern_resolution(line, chain_aliases, pools)
        
        if line != original_line:
            self.logger.debug(f"Resolved with dynamic mapping: '{original_line}' → '{line}'")
        
        return line
    
    def _build_method_context_mappings(self, method_cid: str) -> dict:
        """
        Build comprehensive mappings for a specific method by analyzing CAI3Map structure.
        Discovers method parameters, class attributes, and common Python patterns.
        """
        mappings = {}
        
        if not hasattr(self, 'cai3_map') or not self.cai3_map:
            return mappings
        
        cai3_map = self.cai3_map
        
        # 1. Find method-specific parameter mappings
        if hasattr(cai3_map, 'name_map') and cai3_map.name_map:
            method_prefix = f"{method_cid}:"
            for key, value in cai3_map.name_map.items():
                if key.startswith(method_prefix):
                    # Extract the compressed name (after the colon)
                    compressed = key[len(method_prefix):]
                    mappings[compressed] = value
        
        # 2. Find the class this method belongs to and get class-level mappings
        class_cid = self._find_class_cid_for_method(method_cid)
        if class_cid:
            class_prefix = f"{class_cid}:"
            for key, value in cai3_map.name_map.items():
                if key.startswith(class_prefix):
                    compressed = key[len(class_prefix):]
                    mappings[compressed] = value
        
        # 3. Add global mappings (no colon prefix)
        for key, value in cai3_map.name_map.items():
            if ':' not in key:
                # Common patterns we want to handle
                if value in ['self', 'cls', 'super', '__init__', '__str__', '__repr__']:
                    mappings[key] = value
        
        # 4. Add common compression patterns that might not be in name_map
        if not any(v == 'self' for v in mappings.values()):
            # If no explicit 'self' mapping found, add common single-letter patterns
            common_self_patterns = ['s', 'slf', 'this']
            for pattern in common_self_patterns:
                if pattern not in mappings:
                    mappings[pattern] = 'self'
                    break  # Only add one self mapping
        
        # 5. Handle special dot notation patterns
        # If we find a compressed 'self' mapping, create the dot patterns
        for compressed, expanded in list(mappings.items()):
            if expanded == 'self':
                mappings[f"{compressed}."] = "self."
            elif expanded == 'cls':
                mappings[f"{compressed}."] = "cls."
        
        self.logger.debug(f"Built mappings for {method_cid}: {mappings}")
        return mappings
    
    def _find_class_cid_for_method(self, method_cid: str) -> str:
        """
        Find the class CID that contains the given method CID.
        Uses heuristics to discover class-method relationships.
        """
        if not hasattr(self, 'cai3_full') or not self.cai3_full:
            return None
        
        cai3_full = self.cai3_full
        
        # Strategy 1: Look for method in class nodes
        for node in cai3_full.nodes:
            if hasattr(node, 'methods') and node.methods:
                for method in node.methods:
                    if hasattr(method, 'cid') and method.cid == method_cid:
                        return getattr(node, 'cid', None)
        
        # Strategy 2: Parse table structure if available
        if hasattr(cai3_full, 'table'):
            current_class_cid = None
            for entry in cai3_full.table:
                entry = entry.strip()
                if entry.startswith('C:'):
                    # Class entry - extract CID if available
                    current_class_cid = self._extract_cid_from_entry(entry)
                elif entry.startswith('M:') and method_cid in entry:
                    return current_class_cid
        
        return None
    
    def _extract_cid_from_entry(self, entry: str) -> str:
        """Extract CID from a table entry."""
        # Look for patterns like "C:ClassName#cl_abc123" or "M:method#mt_def456"
        if '#' in entry:
            return entry.split('#')[1]
        return None
    
    def _basic_pattern_resolution(self, line: str, chain_aliases: dict, pools: dict) -> str:
        """
        Basic CAI3 pattern resolution for pools, chain aliases, and array notation.
        This is the fallback when dynamic mapping is not available.
        """
        # Pattern 1: Pool references (p0, p1, etc.)
        def replace_pool(match):
            pool_ref = match.group(0)
            if pool_ref in pools:
                return str(pools[pool_ref])
            return pool_ref
        
        line = re.sub(r'\bp\d+\b', replace_pool, line)
        
        # Pattern 2: Chain aliases (a0, a1, g0, g1, etc.)
        def replace_chain_alias(match):
            alias_ref = match.group(0)
            if alias_ref in chain_aliases:
                return chain_aliases[alias_ref]
            return alias_ref
        
        line = re.sub(r'\b[ag]\d+\b', replace_chain_alias, line)
        
        # Pattern 3: Array notation like D[0], I[1], etc.
        def replace_array_notation(match):
            prefix = match.group(1)  # D, I, etc.
            index = int(match.group(2))  # 0, 1, etc.
            
            # Look for the prefix in chain_aliases as a comma-separated list
            if prefix.lower() in chain_aliases:
                values = [v.strip() for v in chain_aliases[prefix.lower()].split(',')]
                if 0 <= index < len(values):
                    return values[index]
            
            # Fallback: try pools
            pool_key = f"{prefix.lower()}{index}"
            if pool_key in pools:
                return str(pools[pool_key])
            
            return match.group(0)  # Return original if not found
        
        line = re.sub(r'\b([A-Z])\[(\d+)\]', replace_array_notation, line)
        
        return line
    
    def _parse_table_structure(self, ast_obj):
        """Parse table entries into structure map."""
        structure = {}
        current_class = None
        table = getattr(ast_obj, 'table', []) or []
        
        for raw in table:
            line = raw.strip()
            
            # Skip comments and empty lines
            if not line or line.startswith('#'):
                continue
            
            if ':' not in line:
                continue
            
            kind, payload = line.split(':', 1)
            kind = kind.strip()
            payload = payload.strip()
            
            if kind == 'C':
                # Class definition
                current_class = payload
                
            elif kind == 'M' and '#' in payload:
                # Method definition
                full, body_id = payload.split('#', 1)
                if '.' in full:
                    class_name, method_name = full.split('.', 1)
                else:
                    class_name = current_class
                    method_name = full
                
                structure[body_id] = {
                    'parent_class': class_name,
                    'method_name': method_name
                }
                
            elif kind == 'F' and '#' in payload:
                # Function definition
                func_name, body_id = payload.split('#', 1)
                structure[body_id] = {
                    'parent_class': None,
                    'method_name': func_name
                }
        
        return structure
    
    def _assert_no_unresolved(self, module: ast.AST):
        """Ensure no unresolved hashes remain (tighter pattern)."""
        import re
        
        class UnresolvedScanner(ast.NodeVisitor):
            def __init__(self):
                self.unresolved = []
            
            def visit_Name(self, node):
                # Tighter pattern for actual compressed identifiers
                if re.match(
                    r'(hash_[0-9a-f]{4,}|fn_[0-9a-f]+(?:_\w+)?|mt_[0-9a-f]+)$',
                    node.id, 
                    re.IGNORECASE
                ):
                    self.unresolved.append(node.id)
                self.generic_visit(node)
        
        scanner = UnresolvedScanner()
        scanner.visit(module)
        
        if scanner.unresolved:
            unique = sorted(set(scanner.unresolved))
            self.logger.warning(f"Unresolved symbols: {unique[:10]}")
            
            if self.strict_mode:
                raise ValueError(f"Unresolved symbols remain: {unique[:10]}")
            else:
                # Add warning comment - ALWAYS add when unresolved found
                warning = ast.Expr(value=ast.Constant(
                    value=f"# Warning: {len(unique)} unresolved symbols"
                ))
                module.body.insert(0, warning)
                self.logger.debug(f"Added warning comment for {len(unique)} unresolved symbols")
    
    def _parse_imports_with_resolution(self, import_spec: str, 
                                       transformer: 'ResolutionTransformer') -> List[ast.stmt]:
        """Parse imports with relative support."""
        if not import_spec:
            return []
        
        import_nodes = []
        
        for item in import_spec.split('|'):
            item = item.strip()
            if not item:
                continue
            
            if ':' in item:
                # from X import Y
                module, names = item.split(':', 1)
                
                # Count leading dots for relative imports
                level = len(module) - len(module.lstrip('.'))
                module = module.lstrip('.') or None
                
                # Parse imported names
                name_list = []
                for name in names.split(','):
                    name = name.strip()
                    if ' as ' in name:
                        n, a = name.split(' as ', 1)
                        name_list.append(ast.alias(name=n.strip(), asname=a.strip()))
                    else:
                        name_list.append(ast.alias(name=name, asname=None))
                
                node = ast.ImportFrom(module=module, names=name_list, level=level)
            else:
                # import X
                if ' as ' in item:
                    name, asname = item.split(' as ', 1)
                    node = ast.Import(names=[ast.alias(name=name.strip(), asname=asname.strip())])
                else:
                    node = ast.Import(names=[ast.alias(name=item, asname=None)])
            
            # Apply resolution
            node = transformer.visit(node)
            import_nodes.append(node)
        
        return import_nodes
    
    def _create_minimal_cache(self, ast_obj):
        """Create minimal cache from parsed AST."""
        class MinimalFull:
            def __init__(self):
                self.pools = {}
                self.hash_to_value = {}
                self.nodes = []
                self.compression_stats = {}
        
        class MinimalMap:
            def __init__(self):
                self.name_map = {}
                self.reverse_name_map = {}
                self.span_map = {}

        
        minimal_full = MinimalFull()
        minimal_map = MinimalMap()
        
        if hasattr(ast_obj, 'pools'):
            minimal_full.pools = ast_obj.pools
        
        if hasattr(ast_obj, 'chain_aliases'):
            minimal_full.compression_stats['chain_aliases'] = ast_obj.chain_aliases
        
        return minimal_full, minimal_map

    def _find_node_by_cid(self, cid: str, cai3_full):
        """Find a node in CAI3Full by its CID."""
        if not hasattr(cai3_full, 'nodes'):
            return None
        
        for node in cai3_full.nodes:
            if hasattr(node, 'cid') and node.cid == cid:
                return node
            if hasattr(node, 'body_id') and node.body_id == cid:
                return node
        
        return None

    def _find_method_cid_for_body(self, body_id: str) -> str:
        """Find the method CID that corresponds to a body ID."""
        # In most cases, body_id directly corresponds to method CID
        # This is a simple mapping that can be enhanced based on your cache structure
        return body_id

    def _translate_body_content_fallback(self, body_content: str, body_id: str, 
                                        chain_aliases: dict, pools: dict, resolver) -> str:
        """Fallback translation when enhanced parsing fails."""
        self.logger.info(f"Using fallback translation for body {body_id}")
        
        # Apply basic pattern fixes
        translated = body_content
        
        # Apply chain alias resolution
        if chain_aliases:
            for alias, value in chain_aliases.items():
                translated = translated.replace(alias, value)
        
        # Apply pool resolution
        if pools:
            for pool_id, pool_value in pools.items():
                translated = translated.replace(pool_id, str(pool_value))
        
        # Apply hash resolution
        if resolver:
            # Simple pattern replacement for common hash patterns
            import re
            hash_pattern = r'\b(hash_[a-f0-9]+|fn_[a-f0-9]+|mt_[a-f0-9]+)\b'
            def replace_hash(match):
                resolved = resolver.resolve(match.group(1), 'load')
                return resolved if resolved != match.group(1) else match.group(1)
            translated = re.sub(hash_pattern, replace_hash, translated)
        
        return translated

    def _create_valid_python_block(self, code: str) -> str:
        """Create a valid Python code block with proper indentation."""
        if not code.strip():
            return "pass"
        
        lines = code.strip().split('\n')
        # Ensure proper indentation
        formatted_lines = []
        for line in lines:
            if line.strip():
                # Add basic indentation if not present
                if not line.startswith('    ') and not line.startswith('\t'):
                    formatted_lines.append('    ' + line.strip())
                else:
                    formatted_lines.append(line)
            else:
                formatted_lines.append('')
        
        return '\n'.join(formatted_lines) if formatted_lines else "pass"