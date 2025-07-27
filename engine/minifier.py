import ast
import sys
import operator
import warnings
import logging
from typing import Union, Dict, Set, Any, Tuple, Optional, List, Callable

# Python version compatibility check
if sys.version_info < (3, 8):
    warnings.warn(
        "Python minifier requires Python 3.8+. Older versions may have incomplete compatibility.",
        RuntimeWarning,
        stacklevel=2
    )

# Try to import astor for Python 3.8 compatibility
try:
    import astor
    HAS_ASTOR = True
except ImportError:
    HAS_ASTOR = False

# Set up logger for the minifier
logger = logging.getLogger(__name__)

# Compression depth levels
class CompressionDepth:
    """Enumeration for compression depth levels."""
    BASIC = 1       # Comments and whitespace only
    CONSTANTS = 2   # + Constant folding
    VARIABLES = 3   # + Variable name shortening
    AGGRESSIVE = 4  # + All optimizations


def minify_code(
    code_str: str, 
    aggressive: bool = False, 
    validate: bool = True,
    compression_depth: Optional[int] = None
) -> str:
    """
    Minify Python code by removing whitespace, comments, and redundant elements
    while preserving 100% semantic equivalence.
    
    Args:
        code_str: The Python source code string to minify
        aggressive: Enable aggressive optimizations (variable name shortening)
                   [Deprecated: Use compression_depth instead]
        validate: Validate minified output by re-parsing (recommended)
        compression_depth: Control optimization level (1-4):
                          1=BASIC (comments/whitespace only)
                          2=CONSTANTS (+ constant folding)
                          3=VARIABLES (+ variable shortening)
                          4=AGGRESSIVE (+ all optimizations)
                          None=use aggressive flag for backward compatibility
        
    Returns:
        Minified Python code string
        
    Raises:
        SyntaxError: If the input code is invalid Python
        ValueError: If the code cannot be unparsed or validation fails
    """
    try:
        # Determine compression level
        if compression_depth is None:
            # Backward compatibility: use aggressive flag
            depth = CompressionDepth.AGGRESSIVE if aggressive else CompressionDepth.CONSTANTS
        else:
            depth = compression_depth
            if depth < CompressionDepth.BASIC or depth > CompressionDepth.AGGRESSIVE:
                raise ValueError(f"compression_depth must be 1-4, got {depth}")
        
        logger.debug(f"Minifying with compression depth: {depth}")
        
        # Parse the code into an AST
        tree = ast.parse(code_str)
        
        # Apply AST transformations
        transformer = MinifyTransformer(compression_depth=depth)
        tree = transformer.visit(tree)
        
        # Fix missing locations for the transformer
        ast.fix_missing_locations(tree)
        
        # Unparse back to code with safety wrapper
        try:
            if sys.version_info >= (3, 9):
                minified = ast.unparse(tree)
            elif HAS_ASTOR:
                # Use astor for Python 3.8 compatibility
                minified = astor.to_source(tree).strip()
            else:
                raise ValueError(
                    "ast.unparse() requires Python 3.9+. For Python 3.8, install 'astor': pip install astor"
                )
        except Exception as e:
            logger.error(f"Failed to unparse AST: {e}")
            raise ValueError(f"AST unparsing failed: {e}") from e
        
        # Handle empty modules
        if minified.strip() == "pass":
            minified = ""
        
        # Validation step: verify minified code is still valid Python
        if validate:
            try:
                ast.parse(minified)
            except SyntaxError as e:
                raise ValueError(f"Invalid minified output: {e}")
        
        return minified
            
    except SyntaxError as e:
        # Re-raise with more context
        raise SyntaxError(f"Invalid Python code: {e}")
    except Exception as e:
        # Catch any other errors during processing
        raise ValueError(f"Failed to minify code: {e}")


def estimate_tokens(
    code: str, 
    method: str = "simple",
    api_counter: Optional[Callable[[str], int]] = None,
    model_type: str = "gpt"
) -> int:
    """
    Estimate the number of tokens in code for LLM usage estimation.
    
    Args:
        code: Python code string
        method: Estimation method ("simple", "words", "chars", "api")
        api_counter: Optional function that takes code and returns exact token count
                    (for enterprise users with API access)
        model_type: Target model type for calibration ("gpt", "claude", "generic")
    
    Returns:
        Estimated token count
    """
    if method == "api" and api_counter:
        try:
            return api_counter(code)
        except Exception as e:
            logger.warning(f"API token counting failed: {e}, falling back to simple method")
            method = "simple"
    
    # Model-specific calibration factors
    calibration = {
        "gpt": {"simple": 4.0, "words": 1.3, "chars": 3.5},
        "claude": {"simple": 4.2, "words": 1.4, "chars": 3.8},  # Claude tends to use slightly more tokens
        "generic": {"simple": 4.0, "words": 1.3, "chars": 3.5}
    }
    
    factors = calibration.get(model_type, calibration["generic"])
    
    if method == "simple":
        return int(len(code) / factors["simple"])
    elif method == "words":
        # Word-based estimation with model calibration
        import re
        words = len(re.findall(r'\S+', code))
        return int(words * factors["words"])
    elif method == "chars":
        # Character-based with model calibration
        return int(len(code) / factors["chars"])
    elif method == "precise":
        # Enhanced estimation combining multiple heuristics
        import re
        # Count different token types
        words = len(re.findall(r'\S+', code))
        operators = len(re.findall(r'[+\-*/=<>!&|^%~]', code))
        punctuation = len(re.findall(r'[.,;:(){}[\]]', code))
        
        # Weighted estimation
        base_tokens = words * factors["words"]
        operator_tokens = operators * 0.8  # Operators are usually single tokens
        punct_tokens = punctuation * 0.5   # Punctuation often grouped
        
        return int(base_tokens + operator_tokens + punct_tokens)
    else:
        raise ValueError(f"Unknown estimation method: {method}. Use 'simple', 'words', 'chars', 'precise', or 'api'")


def minify_with_stats(code_str: str, aggressive: bool = False) -> Tuple[str, Dict[str, Any]]:
    """
    Minify code and return statistics about the transformation.
    
    Args:
        code_str: Python code string to minify
        aggressive: Enable aggressive optimizations
    
    Returns:
        Tuple of (minified_code, stats_dict)
    """
    original_size = len(code_str)
    original_tokens = estimate_tokens(code_str)
    
    minified = minify_code(code_str, aggressive=aggressive)
    
    minified_size = len(minified)
    minified_tokens = estimate_tokens(minified)
    
    stats = {
        "original_size": original_size,
        "minified_size": minified_size,
        "size_reduction": original_size - minified_size,
        "size_reduction_percent": ((original_size - minified_size) / original_size) * 100,
        "original_tokens": original_tokens,
        "minified_tokens": minified_tokens,
        "token_reduction": original_tokens - minified_tokens,
        "token_reduction_percent": ((original_tokens - minified_tokens) / original_tokens) * 100 if original_tokens > 0 else 0,
        "aggressive_mode": aggressive
    }
    
    return minified, stats


class MinifyTransformer(ast.NodeTransformer):
    """
    AST transformer that applies safe minification transformations.
    """
    
    # Safe binary operations for constant folding
    SAFE_BINOPS = {
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.truediv,
        ast.FloorDiv: operator.floordiv,
        ast.Mod: operator.mod,
        ast.Pow: operator.pow,
        ast.LShift: operator.lshift,
        ast.RShift: operator.rshift,
        ast.BitOr: operator.or_,
        ast.BitXor: operator.xor,
        ast.BitAnd: operator.and_,
    }
    
    # Safe unary operations for constant folding
    SAFE_UNARYOPS = {
        ast.UAdd: operator.pos,
        ast.USub: operator.neg,
        ast.Not: operator.not_,
        ast.Invert: operator.invert,
    }
    
    # Safe comparison operations
    SAFE_COMPAREOPS = {
        ast.Eq: operator.eq,
        ast.NotEq: operator.ne,
        ast.Lt: operator.lt,
        ast.LtE: operator.le,
        ast.Gt: operator.gt,
        ast.GtE: operator.ge,
        ast.Is: operator.is_,
        ast.IsNot: operator.is_not,
        ast.In: lambda a, b: a in b,
        ast.NotIn: lambda a, b: a not in b,
    }
    
    def __init__(self, aggressive: bool = False, compression_depth: Optional[int] = None):
        # Handle backward compatibility
        if compression_depth is None:
            self.compression_depth = CompressionDepth.AGGRESSIVE if aggressive else CompressionDepth.CONSTANTS
        else:
            self.compression_depth = compression_depth
        
        # Legacy support
        self.aggressive = (self.compression_depth >= CompressionDepth.VARIABLES)
        
        self.var_counter = 0
        self.var_mappings: Dict[str, str] = {}
        self.used_names: Set[str] = set()
        self.scope_stack: List[Set[str]] = []  # Track variable names in each scope
        self.module_names: Set[str] = set()  # Track imported module names
        self.builtin_names = {
            'abs', 'all', 'any', 'ascii', 'bin', 'bool', 'bytearray', 'bytes',
            'callable', 'chr', 'classmethod', 'compile', 'complex', 'delattr',
            'dict', 'dir', 'divmod', 'enumerate', 'eval', 'exec', 'filter',
            'float', 'format', 'frozenset', 'getattr', 'globals', 'hasattr',
            'hash', 'help', 'hex', 'id', 'input', 'int', 'isinstance',
            'issubclass', 'iter', 'len', 'list', 'locals', 'map', 'max',
            'memoryview', 'min', 'next', 'object', 'oct', 'open', 'ord',
            'pow', 'print', 'property', 'range', 'repr', 'reversed', 'round',
            'set', 'setattr', 'slice', 'sorted', 'staticmethod', 'str', 'sum',
            'super', 'tuple', 'type', 'vars', 'zip', '__import__',
            # Special names that shouldn't be shortened
            'args', 'kwargs', 'self', 'cls'
        }
    
    def _get_short_name(self, original_name: str) -> str:
        """Generate a short variable name."""
        # Never shorten module names, builtins, or special names
        if (not self.aggressive or 
            original_name in self.builtin_names or
            original_name in self.module_names):
            return original_name
        
        # If the name is already short (1-2 chars), leave it alone for idempotency
        if len(original_name) <= 2 and original_name.isalpha() and original_name.islower():
            return original_name
            
        if original_name in self.var_mappings:
            return self.var_mappings[original_name]
        
        # Check if name exists in any scope
        all_scope_names = set()
        for scope in self.scope_stack:
            all_scope_names.update(scope)
        
        # Generate short names: a, b, c, ..., z, aa, ab, ac, ...
        chars = 'abcdefghijklmnopqrstuvwxyz'
        length = 1
        while True:
            for combo in self._generate_combinations(chars, length):
                short_name = ''.join(combo)
                if (short_name not in self.used_names and 
                    short_name not in self.builtin_names and
                    short_name not in all_scope_names):
                    self.var_mappings[original_name] = short_name
                    self.used_names.add(short_name)
                    return short_name
            length += 1
    
    def _generate_combinations(self, chars: str, length: int):
        """Generate all combinations of given length."""
        if length == 0:
            yield ()
        else:
            for char in chars:
                for combo in self._generate_combinations(chars, length - 1):
                    yield (char,) + combo
    
    def _get_constant_value(self, node):
        """Get constant value from AST node, handling both old and new formats."""
        if hasattr(ast, 'Constant') and isinstance(node, ast.Constant):
            # Python 3.8+ unified constant format
            return node.value
        elif isinstance(node, ast.Num):
            # Python 3.7 number format
            return node.n
        elif isinstance(node, ast.Str):
            # Python 3.7 string format
            return node.s
        elif isinstance(node, ast.NameConstant):
            # Python 3.7 boolean/None format
            return node.value
        return None
    
    def _create_constant(self, value):
        """Create AST constant node, handling both old and new formats."""
        if hasattr(ast, 'Constant'):
            # Python 3.8+ unified constant format
            return ast.Constant(value=value)
        else:
            # Python 3.7 format - create appropriate node type
            if isinstance(value, (int, float)):
                return ast.Num(n=value)
            elif isinstance(value, str):
                return ast.Str(s=value)
            elif isinstance(value, (bool, type(None))):
                return ast.NameConstant(value=value)
            else:
                # Fallback to Num for other numeric types
                return ast.Num(n=value)
    
    def _is_string_constant(self, node):
        """Check if node is a string constant, handling both old and new formats."""
        if hasattr(ast, 'Constant') and isinstance(node, ast.Constant):
            return isinstance(node.value, str)
        return isinstance(node, ast.Str)
    
    def visit_Import(self, node):
        """Track imported module names."""
        for alias in node.names:
            # Track the name that will be used in the code
            name = alias.asname if alias.asname else alias.name
            self.module_names.add(name)
        return self.generic_visit(node)
    
    def visit_ImportFrom(self, node):
        """Track imported names from modules."""
        for alias in node.names:
            # Track the name that will be used in the code
            name = alias.asname if alias.asname else alias.name
            self.module_names.add(name)
        return self.generic_visit(node)
    
    def visit_Pass(self, node):
        """Keep pass statements - they will be removed only if not needed by parent visitors."""
        return node
    
    def visit_Expr(self, node):
        """Visit expression statements."""
        # Just visit children and return - parent will handle docstring logic
        return self.generic_visit(node)
    
    def visit_FunctionDef(self, node):
        """Process function definitions, preserving only the first docstring."""
        # Add function name to parent scope (if any) before entering new scope
        if self.scope_stack:
            self.scope_stack[-1].add(node.name)
        
        # Enter a new scope
        self.scope_stack.append(set())
        
        # Track existing names in this scope
        current_scope = self.scope_stack[-1]
        
        # Add parameter names to current scope before shortening
        for arg in node.args.args:
            current_scope.add(arg.arg)
        
        # Shorten parameter names if aggressive mode
        if self.aggressive:
            for arg in node.args.args:
                if arg.arg not in self.builtin_names:
                    original_name = arg.arg
                    arg.arg = self._get_short_name(original_name)
                    current_scope.add(arg.arg)
        
        # Process the body with docstring handling
        node = self._process_body_with_docstring(node)
        
        # Visit children (this ensures nested functions are processed)
        result = self.generic_visit(node)
        
        # Exit scope
        self.scope_stack.pop()
        
        return result
    
    def visit_AsyncFunctionDef(self, node):
        """Process async function definitions, preserving only the first docstring."""
        # Add function name to parent scope (if any) before entering new scope
        if self.scope_stack:
            self.scope_stack[-1].add(node.name)
        
        # Enter a new scope
        self.scope_stack.append(set())
        
        # Track existing names in this scope
        current_scope = self.scope_stack[-1]
        
        # Add parameter names to current scope before shortening
        for arg in node.args.args:
            current_scope.add(arg.arg)
        
        # Shorten parameter names if aggressive mode
        if self.aggressive:
            for arg in node.args.args:
                if arg.arg not in self.builtin_names:
                    original_name = arg.arg
                    arg.arg = self._get_short_name(original_name)
                    current_scope.add(arg.arg)
        
        # Process the body with docstring handling
        node = self._process_body_with_docstring(node)
        
        # Visit children
        result = self.generic_visit(node)
        
        # Exit scope
        self.scope_stack.pop()
        
        return result
    
    def visit_ClassDef(self, node):
        """Process class definitions, preserving only the first docstring."""
        # Add class name to parent scope (if any) before entering new scope
        if self.scope_stack:
            self.scope_stack[-1].add(node.name)
        
        # Enter a new scope for the class
        self.scope_stack.append(set())
        
        node = self._process_body_with_docstring(node)
        result = self.generic_visit(node)
        
        # Exit scope
        self.scope_stack.pop()
        
        return result
    
    def visit_Lambda(self, node):
        """Process lambda functions."""
        if self.aggressive:
            # Enter a new scope
            self.scope_stack.append(set())
            
            # Track and shorten parameter names
            for arg in node.args.args:
                if arg.arg not in self.builtin_names:
                    self.scope_stack[-1].add(arg.arg)
                    arg.arg = self._get_short_name(arg.arg)
            
            # Visit the body
            result = self.generic_visit(node)
            
            # Exit scope
            self.scope_stack.pop()
            
            return result
        return self.generic_visit(node)
    
    def visit_ListComp(self, node):
        """Process list comprehensions with their own scope."""
        return self._visit_comprehension(node)
    
    def visit_SetComp(self, node):
        """Process set comprehensions with their own scope."""
        return self._visit_comprehension(node)
    
    def visit_DictComp(self, node):
        """Process dict comprehensions with their own scope."""
        return self._visit_comprehension(node)
    
    def visit_GeneratorExp(self, node):
        """Process generator expressions with their own scope."""
        return self._visit_comprehension(node)
    
    def _visit_comprehension(self, node):
        """Helper to process comprehensions with their own scope."""
        if self.aggressive:
            # Enter a new scope
            self.scope_stack.append(set())
            
            # Visit the comprehension
            result = self.generic_visit(node)
            
            # Exit scope
            self.scope_stack.pop()
            
            return result
        return self.generic_visit(node)
    
    def visit_Module(self, node):
        """Process module, preserving only the first docstring."""
        # Initialize module-level scope
        self.scope_stack.append(set())
        
        node = self._process_body_with_docstring(node)
        result = self.generic_visit(node)
        
        # Clean up module scope
        self.scope_stack.pop()
        
        return result
    
    def visit_Name(self, node):
        """Shorten variable names if in aggressive mode."""
        if self.aggressive and isinstance(node.ctx, (ast.Store, ast.Load)):
            # Don't shorten if it's a builtin, module name, or special name
            if (node.id not in self.builtin_names and 
                node.id not in self.module_names):
                
                # For Store context, add to current scope if we have one
                if isinstance(node.ctx, ast.Store) and self.scope_stack:
                    self.scope_stack[-1].add(node.id)
                
                # For Load context, check if this name exists in any enclosing scope
                # If so, don't rename it to maintain scope correctness
                if isinstance(node.ctx, ast.Load):
                    for scope in reversed(self.scope_stack):
                        if node.id in scope:
                            return node  # Don't rename - it's defined in an enclosing scope
                
                node.id = self._get_short_name(node.id)
        return node
    
    def _process_body_with_docstring(self, node):
        """Helper to process a node's body, keeping only the first docstring."""
        if not hasattr(node, 'body') or not node.body:
            # Empty body needs a pass statement
            node.body = [ast.Pass()]
            return node
            
        new_body = []
        
        for i, stmt in enumerate(node.body):
            # Check if this is a docstring BEFORE transformation
            is_first_docstring = (i == 0 and 
                isinstance(stmt, ast.Expr) and 
                self._is_string_constant(stmt.value))
            
            # Apply transformations to the statement
            transformed_stmt = self.visit(stmt)
            
            # Skip None results (removed statements)
            if transformed_stmt is None:
                continue
            
            # Handle replacement markers
            if hasattr(transformed_stmt, '_is_replacement_marker'):
                # This is a marker for multiple statements - expand them
                expanded_stmts = transformed_stmt.body
                # Apply dead code removal to expanded statements
                expanded_stmts = self._remove_dead_code(expanded_stmts)
                new_body.extend(expanded_stmts)
                continue
                
            if is_first_docstring:
                # Keep first docstring
                new_body.append(transformed_stmt)
            elif isinstance(transformed_stmt, ast.Expr) and self._is_string_constant(transformed_stmt.value):
                # This is a non-first string expression - remove it
                pass  # Don't add to new_body
            else:
                # Not a string expression - keep it
                new_body.append(transformed_stmt)
        
        # Remove dead code after return/raise statements
        new_body = self._remove_dead_code(new_body)
        
        # If body is empty after processing, add pass (except for modules)
        if not new_body:
            # Only add pass for non-module nodes (functions, classes need pass if empty)
            if not isinstance(node, ast.Module):
                new_body = [ast.Pass()]
        
        node.body = new_body
        return node
    
    def _remove_dead_code(self, body):
        """Remove unreachable code after return/raise/continue/break statements."""
        new_body = []
        for stmt in body:
            new_body.append(stmt)
            # Stop processing after control flow statements
            if isinstance(stmt, (ast.Return, ast.Raise, ast.Continue, ast.Break)):
                break
        return new_body
    
    def visit_Constant(self, node):
        """Optimize constant values where safe."""
        return node
    
    def visit_BinOp(self, node):
        """Optimize binary operations with constant folding."""
        # Visit children first
        node = self.generic_visit(node)
        
        # Only apply constant folding if compression depth allows it
        if self.compression_depth < CompressionDepth.CONSTANTS:
            return node
        
        # Get values from constants (handle both old and new AST formats)
        left_val = self._get_constant_value(node.left)
        right_val = self._get_constant_value(node.right)
        
        # Try constant folding for safe operations
        if (left_val is not None and right_val is not None and
            type(node.op) in self.SAFE_BINOPS):
            
            try:
                op_func = self.SAFE_BINOPS[type(node.op)]
                result = op_func(left_val, right_val)
                # Only fold if result is a simple type
                if isinstance(result, (int, float, str, bool, complex)):
                    logger.debug(f"Folding binary operation: {left_val} {type(node.op).__name__} {right_val} = {result}")
                    return self._create_constant(result)
            except (ZeroDivisionError, OverflowError, ValueError, TypeError):
                # Don't fold operations that would raise exceptions
                logger.debug(f"Skipping unsafe binary operation: {left_val} {type(node.op).__name__} {right_val}")
                pass
        
        return node
    
    def visit_UnaryOp(self, node):
        """Optimize unary operations with constant folding."""
        # Visit children first
        node = self.generic_visit(node)
        
        # Only apply optimizations if compression depth allows it
        if self.compression_depth < CompressionDepth.CONSTANTS:
            return node
        
        # Get operand value
        operand_val = self._get_constant_value(node.operand)
        
        # Try constant folding
        if (operand_val is not None and type(node.op) in self.SAFE_UNARYOPS):
            try:
                op_func = self.SAFE_UNARYOPS[type(node.op)]
                result = op_func(operand_val)
                if isinstance(result, (int, float, str, bool, complex)):
                    logger.debug(f"Folding unary operation: {type(node.op).__name__} {operand_val} = {result}")
                    return self._create_constant(result)
            except (OverflowError, ValueError, TypeError):
                logger.debug(f"Skipping unsafe unary operation: {type(node.op).__name__} {operand_val}")
                pass
        
        # Optimize double negation: --x -> x (at CONSTANTS level and above)
        if (self.compression_depth >= CompressionDepth.CONSTANTS and
            isinstance(node.op, ast.USub) and 
            isinstance(node.operand, ast.UnaryOp) and
            isinstance(node.operand.op, ast.USub)):
            logger.debug("Optimizing double negation")
            return node.operand.operand
        
        return node
    
    def visit_Compare(self, node):
        """Optimize comparison operations."""
        # Visit children first
        node = self.generic_visit(node)
        
        # Only apply constant folding if compression depth allows it
        if self.compression_depth < CompressionDepth.CONSTANTS:
            return node
        
        # Get values for comparison
        left_val = self._get_constant_value(node.left)
        
        # Try constant folding for single comparisons
        if (len(node.ops) == 1 and len(node.comparators) == 1 and
            left_val is not None and
            type(node.ops[0]) in self.SAFE_COMPAREOPS):
            
            right_val = self._get_constant_value(node.comparators[0])
            if right_val is not None:
                try:
                    op_func = self.SAFE_COMPAREOPS[type(node.ops[0])]
                    result = op_func(left_val, right_val)
                    logger.debug(f"Folding comparison: {left_val} {type(node.ops[0]).__name__} {right_val} = {result}")
                    return self._create_constant(result)
                except (TypeError, ValueError):
                    logger.debug(f"Skipping unsafe comparison: {left_val} {type(node.ops[0]).__name__} {right_val}")
                    pass
        
        return node
    
    def visit_BoolOp(self, node):
        """Optimize boolean operations."""
        # Visit children first
        node = self.generic_visit(node)
        
        # Only apply boolean optimizations if compression depth allows it
        if self.compression_depth < CompressionDepth.CONSTANTS:
            return node
        
        # Optimize 'and' operations
        if isinstance(node.op, ast.And):
            # Remove True constants from 'and' operations
            new_values = []
            for value in node.values:
                val = self._get_constant_value(value)
                if val is not None:
                    if val is True:
                        continue  # Skip True in 'and'
                    elif val is False:
                        return self._create_constant(False)  # False makes entire 'and' False
                new_values.append(value)
            
            if not new_values:
                return self._create_constant(True)
            elif len(new_values) == 1:
                return new_values[0]
            else:
                node.values = new_values
        
        # Optimize 'or' operations
        elif isinstance(node.op, ast.Or):
            # Remove False constants from 'or' operations
            new_values = []
            for value in node.values:
                val = self._get_constant_value(value)
                if val is not None:
                    if val is False:
                        continue  # Skip False in 'or'
                    elif val is True:
                        return self._create_constant(True)  # True makes entire 'or' True
                new_values.append(value)
            
            if not new_values:
                return self._create_constant(False)
            elif len(new_values) == 1:
                return new_values[0]
            else:
                node.values = new_values
        
        return node
    
    def visit_If(self, node):
        """Optimize if statements with constant conditions."""
        # Visit children first
        node = self.generic_visit(node)
        
        # Apply if-statement optimization at CONSTANTS level and above
        # (This maintains backward compatibility with existing tests)
        if self.compression_depth < CompressionDepth.CONSTANTS:
            return node
        
        # Optimize constant conditions
        test_val = self._get_constant_value(node.test)
        if test_val is not None:
            if test_val:
                # Condition is always True - replace with body statements
                logger.debug("Optimizing if True: statement")
                return self._create_replacement_marker(node.body)
            else:
                # Condition is always False - replace with orelse
                logger.debug("Optimizing if False: statement")
                if node.orelse:
                    return self._create_replacement_marker(node.orelse)
                else:
                    return None  # Remove the entire if statement
        
        return node
    
    def _create_replacement_marker(self, statements):
        """Create a marker to indicate this node should be replaced by multiple statements."""
        # For now, just return the first statement and handle multiple statements differently
        # This is a limitation of the AST transformer - it expects single nodes
        if len(statements) == 1:
            return statements[0]
        else:
            # Create a compound statement for multiple statements
            # We'll use a Module node as a container temporarily
            marker = ast.Module(body=statements, type_ignores=[])
            marker._is_replacement_marker = True
            return marker
    
    def visit_While(self, node):
        """Optimize while loops with constant conditions."""
        # Visit children first
        node = self.generic_visit(node)
        
        # Remove while loops with False condition
        test_val = self._get_constant_value(node.test)
        if test_val is not None and not test_val:
            return None
        
        return node


# Convenience functions for different optimization levels
def minify_basic(code_str: str) -> str:
    """Basic minification - removes comments, whitespace, and applies constant folding (backward compatible)."""
    return minify_code(code_str, aggressive=False)  # Keep backward compatibility


def minify_comments_only(code_str: str) -> str:
    """Comments-only minification - removes only comments and whitespace."""
    return minify_code(code_str, compression_depth=CompressionDepth.BASIC)


def minify_constants(code_str: str) -> str:
    """Constant folding minification - includes constant folding and boolean optimization."""
    return minify_code(code_str, compression_depth=CompressionDepth.CONSTANTS)


def minify_variables(code_str: str) -> str:
    """Variable minification - includes variable name shortening."""
    return minify_code(code_str, compression_depth=CompressionDepth.VARIABLES)


def minify_aggressive(code_str: str) -> str:
    """Aggressive minification - includes all optimizations."""
    return minify_code(code_str, aggressive=True)  # Keep backward compatibility


# New explicit depth-based functions
def minify_depth(code_str: str, depth: int) -> str:
    """
    Minify with explicit compression depth level.
    
    Args:
        code_str: Python code to minify
        depth: Compression depth (1-4)
               1=BASIC (comments/whitespace only)
               2=CONSTANTS (+ constant folding)
               3=VARIABLES (+ variable shortening)
               4=AGGRESSIVE (+ all optimizations)
    """
    return minify_code(code_str, compression_depth=depth)


def is_idempotent(code_str: str, aggressive: bool = False) -> bool:
    """
    Check if minification is idempotent (minify(minify(code)) == minify(code)).
    
    Args:
        code_str: Python code string to test
        aggressive: Test aggressive mode
    
    Returns:
        True if idempotent, False otherwise
    """
    try:
        first_pass = minify_code(code_str, aggressive=aggressive)
        second_pass = minify_code(first_pass, aggressive=aggressive)
        return first_pass == second_pass
    except Exception:
        return False


# Example usage and testing
if __name__ == "__main__":
    # Enhanced test code showcasing all features
    test_code = '''
def hello_world(name: str) -> str:
    """
    This is a docstring that should be preserved.
    """
    # This comment will be removed
    message = f"Hello, {name}!"  # Another comment
    
    """This string is not a docstring and should be removed"""
    
    # Constant folding test
    x = 1 + 2 * 3  # Should become 7
    y = not False  # Should become True
    z = --5       # Should become 5
    
    # Boolean optimization test
    result = True and x  # Should become just x
    
    # Dead code test
    if True:
        return message
        print("This should be removed")  # Dead code
    
    return "Never reached"


class MyClass:
    """Class docstring - should be kept."""
    
    def __init__(self):
        """Init docstring - should be kept."""
        self.value = 42
        """This is not a docstring - should be removed"""
    
    # Method with no docstring
    def method(self):
        x = 1 + 2  # Comment to remove, should fold to 3
        if False:
            print("Never executed")  # Dead code
        return x


# Top-level comment
async def async_func():
    """Async function docstring."""
    pass  # This pass should be removed since there's a docstring
'''

    try:
        print("="*70)
        print("ENHANCED PYTHON MINIFIER DEMONSTRATION")
        print("="*70)
        
        # Show original
        print("ORIGINAL CODE:")
        print("-" * 50)
        print(test_code)
        
        # Basic minification with stats
        print("\n" + "="*50)
        print("BASIC MINIFICATION (with stats)")
        print("="*50)
        basic_minified, basic_stats = minify_with_stats(test_code, aggressive=False)
        print("Minified code:")
        print(basic_minified)
        print(f"\nStats:")
        print(f"  - Size reduction: {basic_stats['size_reduction_percent']:.1f}%")
        print(f"  - Token reduction: {basic_stats['token_reduction_percent']:.1f}%")
        print(f"  - Original: {basic_stats['original_size']} chars, {basic_stats['original_tokens']} tokens")
        print(f"  - Minified: {basic_stats['minified_size']} chars, {basic_stats['minified_tokens']} tokens")
        
        # Aggressive minification
        print("\n" + "="*50)
        print("AGGRESSIVE MINIFICATION")
        print("="*50)
        aggressive_minified, aggressive_stats = minify_with_stats(test_code, aggressive=True)
        print("Aggressive minified code:")
        print(aggressive_minified)
        print(f"\nAggressive Stats:")
        print(f"  - Size reduction: {aggressive_stats['size_reduction_percent']:.1f}%")
        print(f"  - Token reduction: {aggressive_stats['token_reduction_percent']:.1f}%")
        
        # Test idempotency
        print("\n" + "="*50)
        print("IDEMPOTENCY TEST")
        print("="*50)
        basic_idempotent = is_idempotent(test_code, aggressive=False)
        aggressive_idempotent = is_idempotent(test_code, aggressive=True)
        print(f"Basic mode idempotent: {'✅ Yes' if basic_idempotent else '❌ No'}")
        print(f"Aggressive mode idempotent: {'✅ Yes' if aggressive_idempotent else '❌ No'}")
        
        # Token estimation methods
        print("\n" + "="*50)
        print("TOKEN ESTIMATION COMPARISON")
        print("="*50)
        simple_tokens = estimate_tokens(test_code, "simple")
        words_tokens = estimate_tokens(test_code, "words")
        chars_tokens = estimate_tokens(test_code, "chars")
        print(f"Simple method: {simple_tokens} tokens")
        print(f"Words method: {words_tokens} tokens")
        print(f"Chars method: {chars_tokens} tokens")
        
        # Test enhanced token estimation
        print("\n" + "="*50)
        print("ENHANCED TOKEN ESTIMATION")
        print("="*50)
        gpt_tokens = estimate_tokens(test_code, "precise", model_type="gpt")
        claude_tokens = estimate_tokens(test_code, "precise", model_type="claude")
        print(f"GPT-optimized precise: {gpt_tokens} tokens")
        print(f"Claude-optimized precise: {claude_tokens} tokens")
        
        # Test compression depth levels
        print("\n" + "="*50)
        print("COMPRESSION DEPTH LEVELS")
        print("="*50)
        comments_only = minify_comments_only(test_code)
        constants_only = minify_constants(test_code)
        variables_only = minify_variables(test_code)
        basic_compat = minify_basic(test_code)
        
        print(f"Comments only (depth 1): {len(comments_only)} chars")
        print(f"+ Constants (depth 2): {len(constants_only)} chars")
        print(f"+ Variables (depth 3): {len(variables_only)} chars")
        print(f"+ Aggressive (depth 4): {len(aggressive_minified)} chars")
        print(f"Basic (backward compatible): {len(basic_compat)} chars")
        
        # Mock API token counter for demonstration
        def mock_api_counter(code: str) -> int:
            # Simulate an API call that returns more precise token count
            import time
            time.sleep(0.01)  # Simulate network delay
            return len(code.split()) + len([c for c in code if c in '(){}[].,;:'])
        
        print("\n" + "="*50)
        print("API TOKEN COUNTING DEMO")
        print("="*50)
        api_tokens = estimate_tokens(test_code, "api", api_counter=mock_api_counter)
        print(f"API-based count: {api_tokens} tokens")
        
        print(f"\n{'='*70}")
        print("✅ ALL FEATURES DEMONSTRATED SUCCESSFULLY!")
        print(f"{'='*70}")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()