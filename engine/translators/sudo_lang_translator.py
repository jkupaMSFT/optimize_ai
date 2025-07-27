import ast
import time
from typing import Dict, Callable, Any, Union, List, Tuple

# Optional logger import with fallback
try:
    from utils.logger import setup_minifier_logging, get_logger, MinifierLogger
    HAS_LOGGER = True
except ImportError:
    HAS_LOGGER = False
    # Fallback logger class
    class MinifierLogger:
        def __init__(self):
            self.logger = self  # Self-reference for compatibility
            
        def log_minification_start(self, **kwargs): return "fallback-op-id"
        def log_minification_complete(self, **kwargs): pass
        def log_ast_transformation(self, **kwargs): pass
        def log_optimization(self, **kwargs): pass
        def log_error(self, **kwargs): pass
        def _safe_log(self, func, msg, extra=None): pass
        def info(self, msg, extra=None): pass
        def error(self, msg, extra=None): pass
        def warning(self, msg, extra=None): pass

# Initialize logger for the translator module
_translator_logger = None

def get_translator_logger() -> MinifierLogger:
    """Get or create the translator logger instance."""
    global _translator_logger
    if _translator_logger is None:
        if HAS_LOGGER:
            _translator_logger = setup_minifier_logging(
                log_level="INFO",
                log_file="logs/translator.log",
                enable_console=False,  # Disable console by default for library usage
                enable_file=True,
                enable_metrics=True,
                enable_performance=True,
                enable_ast_details=False,  # Disable detailed AST logging by default
                production_mode=True  # Safe mode for production usage
            )
        else:
            _translator_logger = MinifierLogger()
    return _translator_logger

# Move OP_MAP outside to avoid redefining for every node
OP_MAP: Dict[str, str] = {
   'Add': '+', 'Sub': '-', 'Mult': '*', 'Div': '/', 'Mod': '%', 'Pow': '**',
   'LShift': '<<', 'RShift': '>>', 'BitOr': '|', 'BitXor': '^', 'BitAnd': '&',
   'FloorDiv': '//', 'And': '&&', 'Or': '||', 'Not': '!', 'Invert': '~',
   'UAdd': '+', 'USub': '-', 'Eq': '==', 'NotEq': '!=', 'Lt': '<',
   'LtE': '<=', 'Gt': '>', 'GtE': '>=', 'Is': 'is', 'IsNot': 'is not',
   'In': 'in', 'NotIn': 'not in'
}

def python_to_sudolang(code: str) -> str:
    """
    Translate Python code to SudoLang with comprehensive logging.
    
    Args:
        code: Python source code string to translate
        
    Returns:
        SudoLang translated code string
    """
    logger = get_translator_logger()
    start_time = time.time()
    operation_id = None
    
    try:
        # Log translation start
        operation_id = logger.log_minification_start(
            code_length=len(code),
            compression_depth=1,  # Basic translation depth
            aggressive=False
        )
        
        logger._safe_log(
            logger.logger.info,
            f"Starting Python to SudoLang translation",
            {"operation_id": operation_id, "input_length": len(code)}
        )
        
        # Parse and translate
        tree: ast.AST = ast.parse(code)
        result = ast_to_sudolang(tree)
        
        # Calculate metrics
        processing_time = time.time() - start_time
        
        # Log completion
        logger.log_minification_complete(
            operation_id=operation_id,
            original_size=len(code),
            minified_size=len(result),
            processing_time=processing_time
        )
        
        logger._safe_log(
            logger.logger.info,
            f"Translation completed successfully",
            {
                "operation_id": operation_id,
                "input_length": len(code),
                "output_length": len(result),
                "processing_time": processing_time
            }
        )
        
        return result
        
    except SyntaxError as e:
        processing_time = time.time() - start_time
        
        logger.log_error(
            error=e,
            operation_id=operation_id,
            code_context=code[:200] + "..." if len(code) > 200 else code,
            stage="parsing"
        )
        
        # Attempt graceful fallback for broken code - useful for debugging scenarios
        fallback_result = _fallback_translate_broken_code(code, e)
        
        logger._safe_log(
            logger.logger.warning,
            f"Syntax error in code, using fallback translation: {str(e)}",
            {
                "operation_id": operation_id,
                "processing_time": processing_time,
                "error_type": type(e).__name__,
                "fallback_used": True
            }
        )
        
        return fallback_result
        
    except Exception as e:
        processing_time = time.time() - start_time
        
        logger.log_error(
            error=e,
            operation_id=operation_id,
            code_context=code[:200] + "..." if len(code) > 200 else code,
            stage="translation"
        )
        
        logger._safe_log(
            logger.logger.error,
            f"Translation failed: {str(e)}",
            {
                "operation_id": operation_id,
                "processing_time": processing_time,
                "error_type": type(e).__name__
            }
        )
        
        # Even for non-syntax errors, attempt some fallback
        return f"# TRANSLATION ERROR: {type(e).__name__}\n# Original code with syntax issues:\n" + _format_code_as_comments(code)

def _format_code_as_comments(code: str) -> str:
    """Format code as comments for fallback scenarios."""
    lines = code.split('\n')
    return '\n'.join(f"# {line}" if line.strip() else "#" for line in lines)

def _fallback_translate_broken_code(code: str, syntax_error: SyntaxError) -> str:
    """
    Attempt to translate broken Python code by processing line-by-line
    and providing helpful information about syntax errors.
    """
    logger = get_translator_logger()
    
    try:
        lines = code.split('\n')
        error_line = getattr(syntax_error, 'lineno', None)
        error_col = getattr(syntax_error, 'offset', None)
        error_msg = str(syntax_error).replace('(<unknown>, line ', '(line ')
        
        result_lines = []
        
        # Add error information header
        result_lines.append(f"# SYNTAX ERROR: {error_msg}")
        if error_line:
            result_lines.append(f"# Error detected at line {error_line}" + (f", column {error_col}" if error_col else ""))
        result_lines.append("# Attempting partial translation of valid code sections...")
        result_lines.append("")
        
        # Try to process code in smaller chunks
        for i, line in enumerate(lines, 1):
            line = line.rstrip()
            if not line.strip():
                result_lines.append("")
                continue
                
            # Mark the error line
            if error_line and i == error_line:
                result_lines.append(f"# >>> SYNTAX ERROR ON THIS LINE <<<")
                result_lines.append(f"# {line}")
                if error_col and error_col > 0:
                    result_lines.append(f"# {' ' * (error_col - 1)}^-- Error here")
                continue
            
            # Try to parse individual statements when possible
            try:
                # Attempt to parse just this line as a statement
                if line.strip() and not line.strip().startswith('#'):
                    # Try basic transformation of common patterns
                    translated_line = _basic_line_translation(line)
                    result_lines.append(translated_line)
                else:
                    result_lines.append(f"# {line}")
            except:
                # If individual line also fails, just comment it
                result_lines.append(f"# UNPARSEABLE: {line}")
        
        return '\n'.join(result_lines)
        
    except Exception as fallback_error:
        logger._safe_log(
            logger.logger.error,
            f"Fallback translation also failed: {fallback_error}",
            {"original_syntax_error": str(syntax_error)}
        )
        # Final fallback - just format as comments with error info
        return f"# SYNTAX ERROR: {syntax_error}\n# Unable to parse - original code below:\n" + _format_code_as_comments(code)

def _basic_line_translation(line: str) -> str:
    """
    Basic line-by-line translation for common Python patterns.
    Used when full AST parsing fails.
    """
    line = line.strip()
    
    # Function definitions
    if line.startswith('def '):
        return f"function {line[4:].replace(':', ' {')}..."
    
    # Class definitions  
    if line.startswith('class '):
        return f"concept {line[6:].replace(':', ' {')}..."
    
    # If statements
    if line.startswith('if '):
        return f"if {line[3:].replace(':', ' {')}..."
    
    # For loops
    if line.startswith('for '):
        return f"for each {line[4:].replace(':', ' {')}..."
    
    # While loops
    if line.startswith('while '):
        return f"while {line[6:].replace(':', ' {')}..."
    
    # Return statements
    if line.startswith('return '):
        return f"return {line[7:]}"
    
    # Import statements
    if line.startswith('import ') or line.startswith('from '):
        return line  # Keep imports as-is
    
    # Comments
    if line.startswith('#'):
        return line
    
    # Try to handle assignments
    if '=' in line and not any(op in line for op in ['==', '!=', '<=', '>=']):
        parts = line.split('=', 1)
        if len(parts) == 2:
            return f"{parts[0].strip()} = {parts[1].strip()}"
    
    # Default: return as pseudocode comment
    return f"execute: {line}"

def render_assign_target(t: ast.expr) -> str:
   if isinstance(t, ast.Name):
       return t.id
   elif isinstance(t, ast.Tuple):
       return "(" + ", ".join(render_assign_target(elt) for elt in t.elts) + ")"
   elif isinstance(t, ast.List):
       return "[" + ", ".join(render_assign_target(elt) for elt in t.elts) + "]"
   elif isinstance(t, ast.Subscript):
       return f'{ast_to_sudolang(t.value, 0)}[{ast_to_sudolang(t.slice, 0)}]'
   elif isinstance(t, ast.Attribute):
       return f'{ast_to_sudolang(t.value, 0)}.{t.attr}'
   return "# Unsupported target"

def _handle_joinedstr_value(val: ast.AST) -> str:
   """Helper function to handle JoinedStr values (both Str and FormattedValue nodes)."""
   if isinstance(val, ast.Str):
       return val.s  # Raw string content without quotes
   elif hasattr(val, 'value'):  # FormattedValue
       return f'{{{ast_to_sudolang(val.value, 0)}}}'
   else:
       return ast_to_sudolang(val, 0)

def _render_comp_target(t: ast.expr) -> str:
   """Helper function to render comprehension targets without extra parentheses."""
   if isinstance(t, ast.Name):
       return t.id
   elif isinstance(t, ast.Tuple):
       return ", ".join(_render_comp_target(elt) for elt in t.elts)  # No parentheses for comprehensions
   elif isinstance(t, ast.List):
       return "[" + ", ".join(_render_comp_target(elt) for elt in t.elts) + "]"
   elif isinstance(t, ast.Subscript):
       return f'{ast_to_sudolang(t.value, 0)}[{ast_to_sudolang(t.slice, 0)}]'
   elif isinstance(t, ast.Attribute):
       return f'{ast_to_sudolang(t.value, 0)}.{t.attr}'
   return "# Unsupported target"

def _render_comp_condition(condition: ast.expr) -> str:
   """Helper function to render comprehension conditions without extra parentheses."""
   # For simple comparisons, don't add parentheses
   if isinstance(condition, ast.Compare):
       return f'{ast_to_sudolang(condition.left, 0)} {" ".join(OP_MAP.get(type(op).__name__, "?") + " " + ast_to_sudolang(comp, 0) for op, comp in zip(condition.ops, condition.comparators))}'
   else:
       return ast_to_sudolang(condition, 0)

def _extract_docstring(body: List[ast.stmt]) -> Tuple[str, List[ast.stmt]]:
    """Extract docstring from function/class body if present."""
    logger = get_translator_logger()
    
    if (body and isinstance(body[0], ast.Expr) and 
        ((isinstance(body[0].value, ast.Str)) or 
         (isinstance(body[0].value, ast.Constant) and isinstance(body[0].value.value, str)))):
        # Extract docstring value
        if isinstance(body[0].value, ast.Str):
            docstring = body[0].value.s
        else:
            docstring = body[0].value.value
        
        logger.log_optimization(
            optimization_type="docstring_extraction",
            before_value=f"Body with {len(body)} statements",
            after_value=f"Docstring ({len(docstring)} chars) + {len(body)-1} statements"
        )
        
        return f'"""{docstring}"""', body[1:]
    return "", body

def _render_decorators(decorator_list: List[ast.expr], indent_str: str) -> str:
    """Render decorators for functions and classes."""
    if not decorator_list:
        return ""
    
    logger = get_translator_logger()
    decorators = []
    for d in decorator_list:
        decorator_text = f'{indent_str}@{ast_to_sudolang(d, 0)}'
        decorators.append(decorator_text)
        
        # Log decorator processing
        decorator_name = getattr(d, 'id', str(d))
        logger.log_optimization(
            optimization_type="decorator_rendering",
            before_value=f"AST decorator node: {type(d).__name__}",
            after_value=f"@{decorator_name}"
        )
    
    return '\n'.join(decorators) + '\n'

def _is_property_decorator(decorator_list: List[ast.expr]) -> bool:
    """Check if function has @property decorator."""
    logger = get_translator_logger()
    has_property = any(isinstance(d, ast.Name) and d.id == "property" for d in decorator_list)
    
    if has_property:
        logger.log_optimization(
            optimization_type="property_detection",
            before_value="function",
            after_value="getter function"
        )
    
    return has_property

def _render_function_signature(n: ast.FunctionDef, is_async: bool = False) -> str:
   """Render function signature with default parameters."""
   async_prefix = "async " if is_async else ""
   
   # Handle default parameters properly
   args_with_defaults = []
   num_defaults = len(n.args.defaults)
   num_args = len(n.args.args)
   
   for idx, arg in enumerate(n.args.args):
       # Check if this argument has a default value
       default_idx = idx - (num_args - num_defaults)
       if default_idx >= 0:
           default_val = ast_to_sudolang(n.args.defaults[default_idx], 0)
           args_with_defaults.append(f"{arg.arg}={default_val}")
       else:
           args_with_defaults.append(arg.arg)
   
   # Add *args if present
   if n.args.vararg:
       args_with_defaults.append(f"*{n.args.vararg.arg}")
   
   # Add **kwargs if present
   if n.args.kwarg:
       args_with_defaults.append(f"**{n.args.kwarg.arg}")
   
   return f'{async_prefix}function {n.name}({", ".join(args_with_defaults)})'

def ast_to_sudolang(node: ast.AST, indent: int = 0) -> str:
    """
    Convert AST node to SudoLang with detailed transformation logging.
    
    Args:
        node: AST node to convert
        indent: Current indentation level
        
    Returns:
        SudoLang representation of the node
    """
    logger = get_translator_logger()
    indent_str: str = "  " * indent
    
    # Log AST transformation
    node_type = type(node).__name__
    logger.log_ast_transformation(
        transformation_type="ast_to_sudolang",
        node_type=node_type,
        details={"indent_level": indent}
    )
   
    NODE_MAP: Dict[str, Callable[[ast.AST, int], str]] = {
        'Module': lambda n, i: '\n'.join(ast_to_sudolang(stmt, i) for stmt in n.body),
        
        # Enhanced FunctionDef with decorators and docstrings
        'FunctionDef': lambda n, i: (
            _render_decorators(n.decorator_list, indent_str) +
            f'{indent_str}{"getter " if _is_property_decorator(n.decorator_list) else ""}{_render_function_signature(n)} {{\n' +
            (_extract_docstring(n.body)[0] and f'{indent_str}  {_extract_docstring(n.body)[0]}\n' or '') +
            chr(10).join(ast_to_sudolang(stmt, i + 1) for stmt in _extract_docstring(n.body)[1]) +
            f'\n{indent_str}}}'
        ),
        
        # Enhanced AsyncFunctionDef with decorators and docstrings
        'AsyncFunctionDef': lambda n, i: (
            _render_decorators(n.decorator_list, indent_str) +
            f'{indent_str}{_render_function_signature(n, is_async=True)} {{\n' +
            (_extract_docstring(n.body)[0] and f'{indent_str}  {_extract_docstring(n.body)[0]}\n' or '') +
            chr(10).join(ast_to_sudolang(stmt, i + 1) for stmt in _extract_docstring(n.body)[1]) +
            f'\n{indent_str}}}'
        ),
        
        # Enhanced ClassDef with decorators and docstrings
        'ClassDef': lambda n, i: (
            _render_decorators(n.decorator_list, indent_str) +
            f'{indent_str}concept {n.name}' +
            (f'({", ".join(ast_to_sudolang(base, 0) for base in n.bases)})' if n.bases else '') +
            ' {\n' +
            (_extract_docstring(n.body)[0] and f'{indent_str}  {_extract_docstring(n.body)[0]}\n' or '') +
            chr(10).join(ast_to_sudolang(stmt, i + 1) for stmt in _extract_docstring(n.body)[1]) +
            f'\n{indent_str}}}'
        ),
        
        'Assign': lambda n, i: f'{indent_str}{render_assign_target(n.targets[0])} = {ast_to_sudolang(n.value, 0)}',
        'AugAssign': lambda n, i: f'{indent_str}{render_assign_target(n.target)} {OP_MAP.get(type(n.op).__name__, "?")}= {ast_to_sudolang(n.value, 0)}',
        'Return': lambda n, i: f'{indent_str}return {ast_to_sudolang(n.value, 0) if n.value else ""}',
        
        # Enhanced If statement handling - use constraint syntax for simple single-line if statements
        'If': lambda n, i: (
            # Check if it's a simple single-statement if without else
            f'{indent_str}constraint: {ast_to_sudolang(n.test, 0)} ? {ast_to_sudolang(n.body[0], 0).strip()}'
            if (len(n.body) == 1 and not n.orelse and isinstance(n.body[0], ast.Expr))
            else f'{indent_str}if {ast_to_sudolang(n.test, 0)} {{\n{chr(10).join(ast_to_sudolang(stmt, i + 1) for stmt in n.body)}\n{indent_str}}}' + (f'\n{indent_str}else {{\n{chr(10).join(ast_to_sudolang(stmt, i + 1) for stmt in n.orelse)}\n{indent_str}}}' if n.orelse else '')
        ),
        'While': lambda n, i: f'{indent_str}while ({ast_to_sudolang(n.test, 0)}) {{\n{chr(10).join(ast_to_sudolang(stmt, i + 1) for stmt in n.body)}\n{indent_str}}}',
        'For': lambda n, i: f'{indent_str}for each {render_assign_target(n.target)} in {ast_to_sudolang(n.iter, 0)} {{\n{chr(10).join(ast_to_sudolang(stmt, i + 1) for stmt in n.body)}\n{indent_str}}}',
        'Expr': lambda n, i: f'{indent_str}{ast_to_sudolang(n.value, 0)}',
        
        # Enhanced Call handling with *args and **kwargs
        'Call': lambda n, i: f'{n.func.id if hasattr(n.func, "id") else ast_to_sudolang(n.func, 0)}({", ".join(list(ast_to_sudolang(arg, 0) for arg in n.args) + list(f"{kw.arg}={ast_to_sudolang(kw.value, 0)}" for kw in n.keywords if kw.arg) + list(f"*{ast_to_sudolang(kw.value, 0)}" for kw in n.keywords if not kw.arg))})',
        'Name': lambda n, i: n.id,
        
        # Enhanced Constant handling for better type representation
        'Constant': lambda n, i: (
            f'"{n.value}"' if isinstance(n.value, str) else
            'None' if n.value is None else
            'True' if n.value is True else
            'False' if n.value is False else
            str(n.value)
        ),
        
        # Support for older Python AST node types (Python < 3.8)
        'Num': lambda n, i: str(n.n),
        'Str': lambda n, i: f'"{n.s}"',
        'NameConstant': lambda n, i: str(n.value),
        'JoinedStr': lambda n, i: 'f"' + ''.join(_handle_joinedstr_value(val) for val in n.values) + '"',
        
        # Enhanced FormattedValue for better f-string representation
        'FormattedValue': lambda n, i: '{' + ast_to_sudolang(n.value, 0) + '}',
        
        'BinOp': lambda n, i: f'({ast_to_sudolang(n.left, 0)} {OP_MAP.get(type(n.op).__name__, "?")} {ast_to_sudolang(n.right, 0)})',
        'UnaryOp': lambda n, i: f'({OP_MAP.get(type(n.op).__name__, "?")}{ast_to_sudolang(n.operand, 0)})',
        'Compare': lambda n, i: f'{ast_to_sudolang(n.left, 0)} {" ".join(OP_MAP.get(type(op).__name__, "?") + " " + ast_to_sudolang(comp, 0) for op, comp in zip(n.ops, n.comparators))}',
        'BoolOp': lambda n, i: f'({(" " + OP_MAP.get(type(n.op).__name__, "?") + " ").join(ast_to_sudolang(val, 0) for val in n.values)})',
        'List': lambda n, i: f'[{", ".join(ast_to_sudolang(elt, 0) for elt in n.elts)}]',
        'Tuple': lambda n, i: f'({", ".join(ast_to_sudolang(elt, 0) for elt in n.elts)})',
        'Dict': lambda n, i: f'{{{", ".join(f"{ast_to_sudolang(k, 0)}: {ast_to_sudolang(v, 0)}" for k, v in zip(n.keys, n.values))}}}',
        'Attribute': lambda n, i: f'{ast_to_sudolang(n.value, 0)}.{n.attr}',
        'Subscript': lambda n, i: f'{ast_to_sudolang(n.value, 0)}[{ast_to_sudolang(n.slice, 0)}]',
        'Index': lambda n, i: ast_to_sudolang(n.value, 0),
        'Slice': lambda n, i: f'{ast_to_sudolang(n.lower, 0) if n.lower else ""}:{ast_to_sudolang(n.upper, 0) if n.upper else ""}',
        'Pass': lambda n, i: f'{indent_str}pass',
        'Break': lambda n, i: f'{indent_str}break',
        'Continue': lambda n, i: f'{indent_str}continue',
        'Lambda': lambda n, i: f'lambda {", ".join(arg.arg for arg in n.args.args)}: {ast_to_sudolang(n.body, 0)}',
        'ListComp': lambda n, i: f'[{ast_to_sudolang(n.elt, 0)} for {" for ".join(f"{_render_comp_target(gen.target)} in {ast_to_sudolang(gen.iter, 0)}" + "".join(f" if {_render_comp_condition(if_)}" for if_ in gen.ifs) for gen in n.generators)}]',
        'DictComp': lambda n, i: f'{{{ast_to_sudolang(n.key, 0)}: {ast_to_sudolang(n.value, 0)} for {" for ".join(f"{_render_comp_target(gen.target)} in {ast_to_sudolang(gen.iter, 0)}" + "".join(f" if {_render_comp_condition(if_)}" for if_ in gen.ifs) for gen in n.generators)}}}',
        'Assert': lambda n, i: f'{indent_str}assert {_render_comp_condition(n.test)}' + (f', {ast_to_sudolang(n.msg, 0)}' if n.msg else ''),
        'Raise': lambda n, i: f'{indent_str}raise {ast_to_sudolang(n.exc, 0) if n.exc else ""}' + (f' from {ast_to_sudolang(n.cause, 0)}' if n.cause else ''),
        'Try': lambda n, i: f'{indent_str}try {{\n{chr(10).join(ast_to_sudolang(stmt, i + 1) for stmt in n.body)}\n{indent_str}}}' + "".join(f'\n{indent_str}catch ({handler.type.id if handler.type and hasattr(handler.type, "id") else "Exception"}{" as " + handler.name if handler.name else ""}) {{\n{chr(10).join(ast_to_sudolang(stmt, i + 1) for stmt in handler.body)}\n{indent_str}}}' for handler in n.handlers) + (f'\n{indent_str}finally {{\n{chr(10).join(ast_to_sudolang(stmt, i + 1) for stmt in n.finalbody)}\n{indent_str}}}' if n.finalbody else ''),
        'ExceptHandler': lambda n, i: "# Handled in Try",
        'With': lambda n, i: f'{indent_str}with {", ".join(f"{ast_to_sudolang(item.context_expr, 0)}" + (f" as {render_assign_target(item.optional_vars)}" if item.optional_vars else "") for item in n.items)} {{\n{chr(10).join(ast_to_sudolang(stmt, i + 1) for stmt in n.body)}\n{indent_str}}}',
        'Global': lambda n, i: f'{indent_str}global {", ".join(n.names)}',
        'Nonlocal': lambda n, i: f'{indent_str}nonlocal {", ".join(n.names)}',
        'Yield': lambda n, i: f'yield {ast_to_sudolang(n.value, 0) if n.value else ""}',
        'YieldFrom': lambda n, i: f'yield from {ast_to_sudolang(n.value, 0)}',
        'Await': lambda n, i: f'await {ast_to_sudolang(n.value, 0)}',
        
        # Enhanced Import handling
        'Import': lambda n, i: f'{indent_str}import {", ".join(alias.name + (f" as {alias.asname}" if alias.asname else "") for alias in n.names)}',
        'ImportFrom': lambda n, i: f'{indent_str}from {"." * (n.level or 0)}{n.module or ""} import {", ".join(alias.name + (f" as {alias.asname}" if alias.asname else "") for alias in n.names)}',
        
        # Enhanced Async context managers
        'AsyncWith': lambda n, i: f'{indent_str}async with {", ".join(f"{ast_to_sudolang(item.context_expr, 0)}" + (f" as {render_assign_target(item.optional_vars)}" if item.optional_vars else "") for item in n.items)} {{\n{chr(10).join(ast_to_sudolang(stmt, i + 1) for stmt in n.body)}\n{indent_str}}}',
        'AsyncFor': lambda n, i: f'{indent_str}async for each {render_assign_target(n.target)} in {ast_to_sudolang(n.iter, 0)} {{\n{chr(10).join(ast_to_sudolang(stmt, i + 1) for stmt in n.body)}\n{indent_str}}}',
        
        # Enhanced Starred expressions
        'Starred': lambda n, i: f'*{ast_to_sudolang(n.value, 0)}',
    }
   
    # Process the node and log optimization details
    if node_type in NODE_MAP:
        result = NODE_MAP[node_type](node, indent)
        
        # Log successful transformation
        logger.log_optimization(
            optimization_type="node_translation",
            before_value=f"{node_type} node",
            after_value=f"SudoLang ({len(result)} chars)",
            node_location=f"line {getattr(node, 'lineno', 'unknown')}"
        )
        
        return result
    else:
        # Log unsupported node type
        unsupported_result = f'{indent_str}# Unsupported: {node_type}'
        
        logger._safe_log(
            logger.logger.warning,
            f"Unsupported AST node type encountered: {node_type}",
            {"node_type": node_type, "indent_level": indent}
        )
        
        return unsupported_result

# Enhanced translation functions with comprehensive logging and statistics

def translate_with_stats(code: str) -> Tuple[str, Dict[str, Any]]:
    """
    Translate Python code to SudoLang and return detailed statistics.
    
    Args:
        code: Python source code to translate
        
    Returns:
        Tuple of (translated_code, statistics_dict)
    """
    logger = get_translator_logger()
    start_time = time.time()
    
    original_size = len(code)
    
    # Count AST nodes for complexity metrics
    try:
        tree = ast.parse(code)
        node_count = sum(1 for _ in ast.walk(tree))
    except:
        node_count = 0
    
    # Perform translation
    translated = python_to_sudolang(code)
    
    translated_size = len(translated)
    processing_time = time.time() - start_time
    
    stats = {
        "original_size": original_size,
        "translated_size": translated_size,
        "size_change": translated_size - original_size,
        "size_change_percent": ((translated_size - original_size) / original_size) * 100 if original_size > 0 else 0,
        "processing_time": processing_time,
        "ast_node_count": node_count,
        "throughput_chars_per_second": original_size / processing_time if processing_time > 0 else 0,
        "translation_successful": not translated.startswith("Invalid Python code")
    }
    
    logger._safe_log(
        logger.logger.info,
        f"Translation statistics generated",
        stats
    )
    
    return translated, stats


def setup_translator_logging(
    log_level: str = "INFO",
    log_file: str = "logs/translator.log",
    enable_ast_details: bool = False,
    production_mode: bool = False
) -> MinifierLogger:
    """
    Setup specialized logging for the translator module.
    
    Args:
        log_level: Logging level
        log_file: Log file path
        enable_ast_details: Enable detailed AST logging
        production_mode: Enable production safety features
        
    Returns:
        Configured logger instance
    """
    if HAS_LOGGER:
        return setup_minifier_logging(
            log_level=log_level,
            log_file=log_file,
            enable_console=True,
            enable_file=True,
            enable_metrics=True,
            enable_performance=True,
            enable_ast_details=enable_ast_details,
            production_mode=production_mode
        )
    else:
        return MinifierLogger()


# Test
if __name__ == "__main__":
    # Setup comprehensive logging for testing
    logger = setup_translator_logging(
        log_level="DEBUG",
        log_file="logs/translator_test.log",
        enable_ast_details=True,
        production_mode=False
    )
    
    logger._safe_log(
        logger.logger.info,
        "Starting translator test cases with comprehensive logging"
    )
    # Test cases based on the samples
    test_cases = [
        # Sample 1 - Import handling
        '''def calculate_area(radius):
    """Calculate the area of a circle given its radius."""
    import math
    return math.pi * radius ** 2''',
        
        # Sample 2 - List comprehension (should work fine)
        '''def filter_even_squares(numbers):
    """Filter and square even numbers from a list."""
    return [x**2 for x in numbers if x % 2 == 0 and x > 0]''',
        
        # Sample 3 - Class with properties and docstrings
        '''class Person:
    """Represents a person with basic information."""
    def __init__(self, first_name, last_name, age):
        self.first_name = first_name
        self.last_name = last_name
        self._age = age
    
    @property
    def full_name(self):
        """Get the person's full name."""
        return f"{self.first_name} {self.last_name}"''',
        
        # Sample 4 - Async with context manager
        '''async def fetch_data(url):
    """Fetch data from a URL asynchronously."""
    import aiohttp
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                return await response.json()
    except Exception as e:
        print(f"Error fetching data: {e}")
        return None''',
        
        # Sample 10 - Default parameters and decorators
        '''def retry(max_attempts=3, delay=1):
    """Decorator for retrying function calls with exponential backoff."""
    def decorator(func):
        import time
        import functools
        
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            """Wrapper function that implements retry logic."""
            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    if attempt == max_attempts - 1:
                        raise
                    time.sleep(delay)
            return None
        return wrapper
    return decorator'''
    ]
    
    for i, code in enumerate(test_cases, 1):
        logger._safe_log(
            logger.logger.info,
            f"Processing test case {i}",
            {"test_case_number": i, "code_length": len(code)}
        )
        
        print(f"\n{'='*60}\nTest Case {i}:\n{'='*60}")
        print("Original Python:")
        print(code)
        print("\nTranslated SudoLang:")
        
        # Use the enhanced translation function with stats
        result, stats = translate_with_stats(code)
        print(result)
        
        # Log and display statistics
        print(f"\nTranslation Statistics:")
        print(f"  Original size: {stats['original_size']} chars")
        print(f"  Translated size: {stats['translated_size']} chars")
        print(f"  Size change: {stats['size_change']:+d} chars ({stats['size_change_percent']:+.1f}%)")
        print(f"  Processing time: {stats['processing_time']:.4f}s")
        print(f"  AST nodes: {stats['ast_node_count']}")
        print(f"  Throughput: {stats['throughput_chars_per_second']:.0f} chars/s")
        
        logger._safe_log(
            logger.logger.info,
            f"Test case {i} completed successfully",
            {
                "test_case_number": i,
                "translation_successful": stats["translation_successful"],
                **stats
            }
        )
    
    logger._safe_log(
        logger.logger.info,
        "All translator test cases completed",
        {"total_test_cases": len(test_cases)}
    )