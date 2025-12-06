import ast
import time
from typing import Dict, Any, Union, List, Callable
from pathlib import Path
from utils.logger import MinifierLogger

# Initialize logger for SynthLang translator
translator_logger = MinifierLogger(
    log_path=Path("logs/translator.log"),
    log_level="INFO"
)

# Extended mappings for modern Python features
ENHANCED_AST_TO_SYNTHLANG = {
    # Async/await
    'async': '⏳',
    'await': '⏸',
    'async for': '⏳∀',
    'async with': '⏳◊',
    
    # Pattern matching
    'match': '⊡',
    'case': '▷',
    '_': '◯',  # Wildcard pattern
    
    # Assignment expressions
    'walrus': '≔',
    
    # Starred expressions
    'starred': '✦',
}

# Helper functions for node_map
def _get_indent_str(indent_level: int, indent_size: int = 2) -> str:
    """Get indentation string for given level."""
    return ' ' * (indent_level * indent_size)

def _render_decorators(decorators: List[ast.AST], indent_str: str) -> str:
    """Render decorator list for node_map."""
    if not decorators:
        return ''
    return ''.join(f'{indent_str}@{_ast_to_synthlang_node_map(dec, 0)}\n' for dec in decorators)

def _extract_docstring(body: List[ast.AST]) -> tuple:
    """Extract docstring and remaining body for node_map."""
    if (body and isinstance(body[0], ast.Expr) and 
        isinstance(body[0].value, (ast.Str, ast.Constant)) and
        isinstance(getattr(body[0].value, 's', getattr(body[0].value, 'value', None)), str)):
        
        docstring_node = body[0].value
        docstring = getattr(docstring_node, 's', getattr(docstring_node, 'value', ''))
        return f'""""{docstring}""""', body[1:]
    return '', body

def _render_function_args(args: ast.arguments) -> str:
    """Render function arguments with type annotations and defaults."""
    arg_strs = []
    
    # Regular arguments with potential defaults
    num_defaults = len(args.defaults)
    num_args = len(args.args)
    
    for i, arg in enumerate(args.args):
        arg_str = arg.arg
        
        # Add type annotation if present
        if arg.annotation:
            arg_str += f':{_ast_to_synthlang_node_map(arg.annotation, 0)}'
        
        # Add default value if present
        default_index = i - (num_args - num_defaults)
        if default_index >= 0:
            default_val = _ast_to_synthlang_node_map(args.defaults[default_index], 0)
            arg_str += f'={default_val}'
            
        arg_strs.append(arg_str)
    
    # *args
    if args.vararg:
        vararg_str = f'*{args.vararg.arg}'
        if args.vararg.annotation:
            vararg_str += f':{_ast_to_synthlang_node_map(args.vararg.annotation, 0)}'
        arg_strs.append(vararg_str)
    
    # **kwargs  
    if args.kwarg:
        kwarg_str = f'**{args.kwarg.arg}'
        if args.kwarg.annotation:
            kwarg_str += f':{_ast_to_synthlang_node_map(args.kwarg.annotation, 0)}'
        arg_strs.append(kwarg_str)
    
    return ','.join(arg_strs)

def _render_for_target(target: ast.AST) -> str:
    """Render for loop target, handling tuple unpacking without parentheses."""
    if isinstance(target, ast.Tuple):
        # For tuple unpacking in for loops, don't use parentheses to match old behavior
        return ','.join(_ast_to_synthlang_node_map(elt, 0) for elt in target.elts)
    else:
        return _ast_to_synthlang_node_map(target, 0)

def _ast_to_synthlang_node_map(node: ast.AST, indent_level: int, annotate_lines: bool = False) -> str:
    """Convert AST node to SynthLang using node_map."""
    if node is None:
        return ''
    
    node_type = type(node).__name__
    indent_str = _get_indent_str(indent_level)
    
    def _get_line_annotation(n: ast.AST) -> str:
        """Generate line annotation for a node if annotate_lines is enabled."""
        if not annotate_lines or not hasattr(n, 'lineno'):
            return ""
        
        # Check if node has end_lineno for range
        if hasattr(n, 'end_lineno') and n.end_lineno and n.end_lineno != n.lineno:
            return f"# [source lines {n.lineno}–{n.end_lineno}]\n{indent_str}"
        else:
            return f"# [source line {n.lineno}]\n{indent_str}"

    def _recursive_map(n: ast.AST, i: int) -> str:
        """Recursive call to _ast_to_synthlang_node_map with current annotate_lines setting."""
        return _ast_to_synthlang_node_map(n, i, annotate_lines)
    
    # Log detailed AST transformation for complex nodes
    if indent_level == 0:  # Only log at root level to avoid spam
        translator_logger.log_ast_transformation(
            transformation_type="ast_to_synthlang_node_map",
            node_type=node_type,
            details={"indent_level": indent_level, "annotate_lines": annotate_lines},
            optimization_applied=True
        )
    
    # Handle special cases with annotations first
    if annotate_lines and node_type in ['FunctionDef', 'AsyncFunctionDef']:
        annotation = _get_line_annotation(node)
        if node_type == 'FunctionDef':
            result = (
                annotation +
                _render_decorators(node.decorator_list, _get_indent_str(indent_level)) +
                f'{_get_indent_str(indent_level)}{node.name}({_render_function_args(node.args)})' +
                (f':{_recursive_map(node.returns, 0)}' if node.returns else '') +
                '→' +
                ((_recursive_map(node.body[0].value, 0) if len(node.body) == 1 and isinstance(node.body[0], ast.Return) else
                  '{\n' + '\n'.join(_recursive_map(stmt, indent_level + 1) for stmt in node.body) + f'\n{_get_indent_str(indent_level)}}}'))
            )
            return result
        elif node_type == 'AsyncFunctionDef':
            result = (
                annotation +
                _render_decorators(node.decorator_list, _get_indent_str(indent_level)) +
                f'{_get_indent_str(indent_level)}⏳{node.name}({_render_function_args(node.args)})' +
                (f':{_recursive_map(node.returns, 0)}' if node.returns else '') +
                '→' +
                ((_recursive_map(node.body[0].value, 0) if len(node.body) == 1 and isinstance(node.body[0], ast.Return) else
                  '{\n' + '\n'.join(_recursive_map(stmt, indent_level + 1) for stmt in node.body) + f'\n{_get_indent_str(indent_level)}}}'))
            )
            return result
    
    # Fall back to NODE_MAP for all other cases
    if node_type in NODE_MAP:
        try:
            # For recursive calls, we need to patch the NODE_MAP function to use our _recursive_map
            original_func = NODE_MAP[node_type]
            if annotate_lines:
                # We need to create a temporary modified version that uses _recursive_map
                import types
                func_code = original_func.__code__
                func_globals = original_func.__globals__.copy()
                func_globals['_ast_to_synthlang_node_map'] = _recursive_map
                modified_func = types.FunctionType(func_code, func_globals)
                result = modified_func(node, indent_level)
            else:
                result = original_func(node, indent_level)
            
            if indent_level == 0:  # Log successful translation at root
                translator_logger._safe_log(
                    translator_logger.logger.debug,
                    f"Successfully mapped {node_type} node using NODE_MAP",
                    {"node_type": node_type, "result_length": len(result)}
                )
            return result
        except Exception as e:
            translator_logger.log_error(
                error=e,
                operation_id=None,
                code_context=f"Node type: {node_type}",
                stage="node_mapping"
            )
            # Fallback to class-based visitor
            converter = EnhancedASTToSynthLang(use_spaces=True)
            return converter.visit(node)
    else:
        # Fallback to class-based visitor
        translator_logger._safe_log(
            translator_logger.logger.debug,
            f"Node type {node_type} not in NODE_MAP, using fallback converter",
            {"node_type": node_type}
        )
        converter = EnhancedASTToSynthLang(use_spaces=True)
        return converter.visit(node)

# Node mapping for lambda-based AST to SynthLang conversion
NODE_MAP: Dict[str, Callable[[ast.AST, int], str]] = {
    'Module': lambda n, i: '\n'.join(_ast_to_synthlang_node_map(stmt, i) for stmt in n.body).rstrip(),
    
    'FunctionDef': lambda n, i: (
        _render_decorators(n.decorator_list, _get_indent_str(i)) +
        f'{_get_indent_str(i)}{n.name}({_render_function_args(n.args)})' +
        (f':{_ast_to_synthlang_node_map(n.returns, 0)}' if n.returns else '') +
        '→' +
        ((_ast_to_synthlang_node_map(n.body[0].value, 0) if len(n.body) == 1 and isinstance(n.body[0], ast.Return) else
          '{\n' + '\n'.join(_ast_to_synthlang_node_map(stmt, i + 1) for stmt in n.body) + f'\n{_get_indent_str(i)}}}'))
    ),
    
    'AsyncFunctionDef': lambda n, i: (
        _render_decorators(n.decorator_list, _get_indent_str(i)) +
        f'{_get_indent_str(i)}⏳{n.name}({_render_function_args(n.args)})' +
        (f':{_ast_to_synthlang_node_map(n.returns, 0)}' if n.returns else '') +
        '→' +
        ((_ast_to_synthlang_node_map(n.body[0].value, 0) if len(n.body) == 1 and isinstance(n.body[0], ast.Return) else
          '{\n' + '\n'.join(_ast_to_synthlang_node_map(stmt, i + 1) for stmt in n.body) + f'\n{_get_indent_str(i)}}}'))
    ),
    
    'ClassDef': lambda n, i: (
        _render_decorators(n.decorator_list, _get_indent_str(i)) +
        f'{_get_indent_str(i)}τ {n.name}' +
        (f'({", ".join(_ast_to_synthlang_node_map(base, 0) for base in n.bases)})' if n.bases else '') +
        ' {\n' +
        (_extract_docstring(n.body)[0] and f'{_get_indent_str(i + 1)}{_extract_docstring(n.body)[0]}\n' or '') +
        '\n'.join(_ast_to_synthlang_node_map(stmt, i + 1) for stmt in _extract_docstring(n.body)[1]) +
        f'\n{_get_indent_str(i)}}}'
    ),
    
    'Return': lambda n, i: f'{_get_indent_str(i)}→{_ast_to_synthlang_node_map(n.value, 0) if n.value else ""}',
    
    'Assign': lambda n, i: (
        f'{_get_indent_str(i)}' +
        ','.join(_ast_to_synthlang_node_map(target, 0) for target in n.targets) +
        f'={_ast_to_synthlang_node_map(n.value, 0)}'
    ),
    
    'AnnAssign': lambda n, i: (
        f'{_get_indent_str(i)}{_ast_to_synthlang_node_map(n.target, 0)}:' +
        f'{_ast_to_synthlang_node_map(n.annotation, 0)}' +
        (f'={_ast_to_synthlang_node_map(n.value, 0)}' if n.value else '')
    ),
    
    'AugAssign': lambda n, i: (
        f'{_get_indent_str(i)}{_ast_to_synthlang_node_map(n.target, 0)}' +
        f'{_get_binop_symbol(n.op)}=' +
        f'{_ast_to_synthlang_node_map(n.value, 0)}'
    ),
    
    'For': lambda n, i: (
        f'{_get_indent_str(i)}∀{_render_for_target(n.target)}∈{_ast_to_synthlang_node_map(n.iter, 0)}:\n' +
        '\n'.join(_ast_to_synthlang_node_map(stmt, i + 1) for stmt in n.body) +
        ('\n' + f'{_get_indent_str(i)}◊:\n' + '\n'.join(_ast_to_synthlang_node_map(stmt, i + 1) for stmt in n.orelse) if n.orelse else '')
    ),
    
    'AsyncFor': lambda n, i: (
        f'{_get_indent_str(i)}⏳∀{_render_for_target(n.target)}∈{_ast_to_synthlang_node_map(n.iter, 0)}:\n' +
        '\n'.join(_ast_to_synthlang_node_map(stmt, i + 1) for stmt in n.body) +
        ('\n' + f'{_get_indent_str(i)}◊:\n' + '\n'.join(_ast_to_synthlang_node_map(stmt, i + 1) for stmt in n.orelse) if n.orelse else '')
    ),
    
    'While': lambda n, i: (
        f'{_get_indent_str(i)}↻{_ast_to_synthlang_node_map(n.test, 0)}:\n' +
        '\n'.join(_ast_to_synthlang_node_map(stmt, i + 1) for stmt in n.body) +
        ('\n' + f'{_get_indent_str(i)}◊:\n' + '\n'.join(_ast_to_synthlang_node_map(stmt, i + 1) for stmt in n.orelse) if n.orelse else '')
    ),
    
    'If': lambda n, i: (
        f'{_get_indent_str(i)}?{_ast_to_synthlang_node_map(n.test, 0)}:\n' +
        '\n'.join(_ast_to_synthlang_node_map(stmt, i + 1) for stmt in n.body) +
        ('\n' + f'{_get_indent_str(i)}◊:\n' + '\n'.join(_ast_to_synthlang_node_map(stmt, i + 1) for stmt in n.orelse) if n.orelse else '')
    ),
    
    'With': lambda n, i: (
        f'{_get_indent_str(i)}◊' +
        ','.join(f'{_ast_to_synthlang_node_map(item.context_expr, 0)}' + 
                (f'→{_ast_to_synthlang_node_map(item.optional_vars, 0)}' if item.optional_vars else '') 
                for item in n.items) +
        ':\n' +
        '\n'.join(_ast_to_synthlang_node_map(stmt, i + 1) for stmt in n.body)
    ),
    
    'AsyncWith': lambda n, i: (
        f'{_get_indent_str(i)}⏳◊' +
        ','.join(f'{_ast_to_synthlang_node_map(item.context_expr, 0)}' + 
                (f'⇨{_ast_to_synthlang_node_map(item.optional_vars, 0)}' if item.optional_vars else '') 
                for item in n.items) +
        ':\n' +
        '\n'.join(_ast_to_synthlang_node_map(stmt, i + 1) for stmt in n.body)
    ),
    
    'Try': lambda n, i: (
        f'{_get_indent_str(i)}⟦\n' +
        '\n'.join(_ast_to_synthlang_node_map(stmt, i + 1) for stmt in n.body) +
        ''.join(f'\n{_get_indent_str(i)}⟧{_ast_to_synthlang_node_map(handler.type, 0) if handler.type else ""}' +
               (f'⇨{handler.name}' if handler.name else '') + ':\n' +
               '\n'.join(_ast_to_synthlang_node_map(stmt, i + 1) for stmt in handler.body) 
               for handler in n.handlers) +
        ('\n' + f'{_get_indent_str(i)}⟧:\n' + '\n'.join(_ast_to_synthlang_node_map(stmt, i + 1) for stmt in n.orelse) if n.orelse else '') +
        ('\n' + f'{_get_indent_str(i)}⟨⟩:\n' + '\n'.join(_ast_to_synthlang_node_map(stmt, i + 1) for stmt in n.finalbody) if n.finalbody else '')
    ),
    
    'Match': lambda n, i: (
        f'{_get_indent_str(i)}⊡{_ast_to_synthlang_node_map(n.subject, 0)}:\n' +
        '\n'.join(_ast_to_synthlang_node_map(case, i + 1) for case in n.cases)
    ),
    
    'ImportFrom': lambda n, i: (
        f'{_get_indent_str(i)}⊲{n.module or "."}⊳' +
        ','.join(alias.name + (f'→{alias.asname}' if alias.asname else '') for alias in n.names)
    ),
    
    'Import': lambda n, i: (
        f'{_get_indent_str(i)}⊲' +
        ','.join(alias.name + (f'→{alias.asname}' if alias.asname else '') for alias in n.names)
    ),
    
    'Expr': lambda n, i: f'{_get_indent_str(i)}{_ast_to_synthlang_node_map(n.value, 0)}',
    'Pass': lambda n, i: f'{_get_indent_str(i)}⋯',
    'Break': lambda n, i: f'{_get_indent_str(i)}⊣',
    'Continue': lambda n, i: f'{_get_indent_str(i)}⊢',
    
    'Delete': lambda n, i: f'{_get_indent_str(i)}⌫{",".join(_ast_to_synthlang_node_map(target, 0) for target in n.targets)}',
    
    'Global': lambda n, i: f'{_get_indent_str(i)}🌐{",".join(n.names)}',
    'Nonlocal': lambda n, i: f'{_get_indent_str(i)}🔗{",".join(n.names)}',
    
    'Raise': lambda n, i: (
        f'{_get_indent_str(i)}⚡' +
        (_ast_to_synthlang_node_map(n.exc, 0) if n.exc else '') +
        (f'⇦{_ast_to_synthlang_node_map(n.cause, 0)}' if n.cause else '')
    ),
    
    'Assert': lambda n, i: (
        f'{_get_indent_str(i)}⟨{_ast_to_synthlang_node_map(n.test, 0)}⟩' +
        (f':{_ast_to_synthlang_node_map(n.msg, 0)}' if n.msg else '')
    ),
    
    # Expressions
    'Name': lambda n, i: n.id,
    'Constant': lambda n, i: _format_constant(n.value),
    'Num': lambda n, i: str(n.n),  # Python < 3.8
    'Str': lambda n, i: _format_string(n.s),  # Python < 3.8
    'NameConstant': lambda n, i: _format_constant(n.value),  # Python < 3.8
    'Bytes': lambda n, i: _format_bytes(n.s),
    
    'List': lambda n, i: f'[{",".join(_ast_to_synthlang_node_map(elt, 0) for elt in n.elts)}]',
    'Tuple': lambda n, i: f'({",".join(_ast_to_synthlang_node_map(elt, 0) for elt in n.elts)})',
    'Set': lambda n, i: f'{{{",".join(_ast_to_synthlang_node_map(elt, 0) for elt in n.elts)}}}',
    'Dict': lambda n, i: f'{{{",".join(f"{_ast_to_synthlang_node_map(k, 0)}:{_ast_to_synthlang_node_map(v, 0)}" for k, v in zip(n.keys, n.values))}}}',
    
    'ListComp': lambda n, i: (
        f'[{_ast_to_synthlang_node_map(n.elt, 0)}' +
        ''.join(f'∀{_ast_to_synthlang_node_map(gen.target, 0)}∈{_ast_to_synthlang_node_map(gen.iter, 0)}' +
               ''.join(f'?{_ast_to_synthlang_node_map(if_, 0)}' for if_ in gen.ifs)
               for gen in n.generators) + ']'
    ),
    
    'SetComp': lambda n, i: (
        f'{{{_ast_to_synthlang_node_map(n.elt, 0)}' +
        ''.join(f'∀{_ast_to_synthlang_node_map(gen.target, 0)}∈{_ast_to_synthlang_node_map(gen.iter, 0)}' +
               ''.join(f'?{_ast_to_synthlang_node_map(if_, 0)}' for if_ in gen.ifs)
               for gen in n.generators) + '}'
    ),
    
    'DictComp': lambda n, i: (
        f'{{{_ast_to_synthlang_node_map(n.key, 0)}:{_ast_to_synthlang_node_map(n.value, 0)}' +
        ''.join(f'∀{_ast_to_synthlang_node_map(gen.target, 0)}∈{_ast_to_synthlang_node_map(gen.iter, 0)}' +
               ''.join(f'?{_ast_to_synthlang_node_map(if_, 0)}' for if_ in gen.ifs)
               for gen in n.generators) + '}'
    ),
    
    'GeneratorExp': lambda n, i: (
        f'({_ast_to_synthlang_node_map(n.elt, 0)}' +
        ''.join(f'∀{_ast_to_synthlang_node_map(gen.target, 0)}∈{_ast_to_synthlang_node_map(gen.iter, 0)}' +
               ''.join(f'?{_ast_to_synthlang_node_map(if_, 0)}' for if_ in gen.ifs)
               for gen in n.generators) + ')'
    ),
    
    'Await': lambda n, i: f'⏸{_ast_to_synthlang_node_map(n.value, 0)}',
    'Yield': lambda n, i: f'⟸{_ast_to_synthlang_node_map(n.value, 0) if n.value else ""}',
    'YieldFrom': lambda n, i: f'⟸✦{_ast_to_synthlang_node_map(n.value, 0)}',
    
    'Compare': lambda n, i: (
        _ast_to_synthlang_node_map(n.left, 0) +
        ''.join(f'{_get_compare_symbol(op)}{_ast_to_synthlang_node_map(comp, 0)}' 
               for op, comp in zip(n.ops, n.comparators))
    ),
    
    'Call': lambda n, i: (
        _get_function_symbol(_ast_to_synthlang_node_map(n.func, 0)) + '(' +
        ','.join(_ast_to_synthlang_node_map(arg, 0) for arg in n.args) +
        (',' if n.args and n.keywords else '') +
        ','.join(f'{kw.arg}={_ast_to_synthlang_node_map(kw.value, 0)}' if kw.arg else f'✦✦{_ast_to_synthlang_node_map(kw.value, 0)}' 
                for kw in n.keywords) + ')'
    ),
    
    'Attribute': lambda n, i: f'{_ast_to_synthlang_node_map(n.value, 0)}.{n.attr}',
    'Subscript': lambda n, i: f'{_ast_to_synthlang_node_map(n.value, 0)}[{_ast_to_synthlang_node_map(n.slice, 0)}]',
    'Starred': lambda n, i: f'✦{_ast_to_synthlang_node_map(n.value, 0)}',
    'Slice': lambda n, i: (
        (_ast_to_synthlang_node_map(n.lower, 0) if n.lower else '') + ':' +
        (_ast_to_synthlang_node_map(n.upper, 0) if n.upper else '') +
        (':' + _ast_to_synthlang_node_map(n.step, 0) if n.step else '')
    ),
    
    'BinOp': lambda n, i: f'{_ast_to_synthlang_node_map(n.left, 0)}{_get_binop_symbol(n.op)}{_ast_to_synthlang_node_map(n.right, 0)}',
    'UnaryOp': lambda n, i: f'{_get_unaryop_symbol(n.op)}{_ast_to_synthlang_node_map(n.operand, 0)}',
    'BoolOp': lambda n, i: _get_boolop_symbol(n.op).join(_ast_to_synthlang_node_map(val, 0) for val in n.values),
    
    'NamedExpr': lambda n, i: f'({_ast_to_synthlang_node_map(n.target, 0)}≔{_ast_to_synthlang_node_map(n.value, 0)})',
    
    'Lambda': lambda n, i: (
        'λ(' + ','.join(arg.arg for arg in n.args.args) +
        (f',*{n.args.vararg.arg}' if n.args.vararg else '') +
        (f',**{n.args.kwarg.arg}' if n.args.kwarg else '') +
        f')→{_ast_to_synthlang_node_map(n.body, 0)}'
    ),
    
    'IfExp': lambda n, i: f'{_ast_to_synthlang_node_map(n.body, 0)}?{_ast_to_synthlang_node_map(n.test, 0)}:{_ast_to_synthlang_node_map(n.orelse, 0)}',
    
    'JoinedStr': lambda n, i: (
        'ƒ"' + ''.join(_ast_to_synthlang_node_map(val, 0) for val in n.values) + '"'
    ),
    
    'FormattedValue': lambda n, i: (
        f'{{{_ast_to_synthlang_node_map(n.value, 0)}' +
        (f':{_ast_to_synthlang_node_map(n.format_spec, 0)}' if n.format_spec else '') + '}'
    ),
    
    # Pattern matching
    'match_case': lambda n, i: (
        f'{_get_indent_str(i)}▷{_ast_to_synthlang_node_map(n.pattern, 0)}' +
        (f'?{_ast_to_synthlang_node_map(n.guard, 0)}' if n.guard else '') + ':\n' +
        '\n'.join(_ast_to_synthlang_node_map(stmt, i + 1) for stmt in n.body)
    ),
    
    'MatchValue': lambda n, i: _ast_to_synthlang_node_map(n.value, 0),
    'MatchSingleton': lambda n, i: _format_constant(n.value),
    'MatchSequence': lambda n, i: f'[{",".join(_ast_to_synthlang_node_map(p, 0) for p in n.patterns)}]',
    'MatchMapping': lambda n, i: (
        f'{{{",".join(f"{_ast_to_synthlang_node_map(k, 0)}:{_ast_to_synthlang_node_map(p, 0)}" for k, p in zip(n.keys, n.patterns))}' +
        (f',**{n.rest}' if n.rest else '') + '}'
    ),
    'MatchClass': lambda n, i: (
        f'{_ast_to_synthlang_node_map(n.cls, 0)}(' +
        ','.join(_ast_to_synthlang_node_map(p, 0) for p in n.patterns) +
        (',' if n.patterns and n.kwd_patterns else '') +
        ','.join(f'{attr}={_ast_to_synthlang_node_map(p, 0)}' for attr, p in zip(n.kwd_attrs, n.kwd_patterns)) + ')'
    ),
    'MatchAs': lambda n, i: (
        (_ast_to_synthlang_node_map(n.pattern, 0) if n.pattern else '') +
        ('⇨' if n.pattern and n.name else '') +
        (n.name if n.name else '◯')
    ),
    'MatchOr': lambda n, i: '|'.join(_ast_to_synthlang_node_map(p, 0) for p in n.patterns),
    'MatchStar': lambda n, i: f'✦{n.name if n.name else ""}',
}

def _get_function_symbol(func_name: str) -> str:
    """Get special symbol for function names."""
    special_functions = {
        'complex': 'ℂ',
        'print': '↪',
        'input': '↩', 
        'len': '|⋅|',
        'range': '…',
        'encrypt': 'encrypt',  # Keep as-is for test
        'verify': 'verify',    # Keep as-is for test
    }
    
    result = special_functions.get(func_name, func_name)
    
    # Log function symbol optimization
    if func_name in special_functions:
        translator_logger.log_optimization(
            optimization_type="function_symbol_mapping",
            before_value=func_name,
            after_value=result,
            node_location="function_call"
        )
    
    return result

def _get_binop_symbol(op: ast.AST) -> str:
    """Get symbol for binary operations."""
    op_map = {
        'Add': '+', 'Sub': '-', 'Mult': '×', 'Div': '÷', 'Mod': '%', 'Pow': '^',
        'LShift': '<<', 'RShift': '>>', 'BitOr': '|', 'BitXor': '⊕', 'BitAnd': '&', 'FloorDiv': '÷÷'
    }
    return op_map.get(type(op).__name__, f'[{type(op).__name__}]')

def _get_unaryop_symbol(op: ast.AST) -> str:
    """Get symbol for unary operations."""
    op_map = {'Not': '¬', 'UAdd': '+', 'USub': '-', 'Invert': '~'}
    return op_map.get(type(op).__name__, f'[{type(op).__name__}]')

def _get_boolop_symbol(op: ast.AST) -> str:
    """Get symbol for boolean operations."""
    op_map = {'And': '∧', 'Or': '∨'}
    return op_map.get(type(op).__name__, f'[{type(op).__name__}]')

def _get_compare_symbol(op: ast.AST) -> str:
    """Get symbol for comparison operations."""
    op_map = {
        'Eq': '=', 'NotEq': '≠', 'Lt': '<', 'LtE': '≤', 'Gt': '>', 'GtE': '≥',
        'Is': '≡', 'IsNot': '≢', 'In': '∈', 'NotIn': '∉'
    }
    return op_map.get(type(op).__name__, f'[{type(op).__name__}]')

def _format_constant(value: Any) -> str:
    """Format constant values."""
    if value is True:
        return '✓'
    elif value is False:
        return '✗'
    elif value is None:
        return '∅'
    elif isinstance(value, str):
        return _format_string(value)
    else:
        return str(value)

def _format_string(s: str) -> str:
    """Format string literals."""
    lines = s.split('\n')
    is_multiline = len(lines) > 1 and any(line.strip() for line in lines)
    
    if is_multiline:
        return f'""""{s}""""'
    else:
        escaped_str = repr(s)
        if escaped_str.startswith("'") and escaped_str.endswith("'"):
            inner = escaped_str[1:-1].replace('"', '\\"')
            return f'"{inner}"'
        return escaped_str

def _format_bytes(b: bytes) -> str:
    """Format bytes literals."""
    repr_str = repr(b)
    if repr_str.startswith("b'") and repr_str.endswith("'"):
        # Convert b'...' to b"..."
        inner = repr_str[2:-1]  # Remove b' and '
        inner = inner.replace('"', '\\"')  # Escape any double quotes
        return f'b"{inner}"'
    return repr_str

class EnhancedASTToSynthLang(ast.NodeVisitor):
    """Enhanced converter with support for Python 3.10+ features."""
    
    def __init__(self, indent_size=2, use_spaces=True):
        self.result = []
        self.indent_level = 0
        self.indent_size = indent_size
        self.use_spaces = use_spaces
        self.in_single_line = False
        self.nodes_processed = 0
        self.start_time = time.time()
        
        translator_logger._safe_log(
            translator_logger.logger.debug,
            f"Initialized EnhancedASTToSynthLang converter",
            {"indent_size": indent_size, "use_spaces": use_spaces}
        )
        
    def _indent(self):
        """Add indentation to output."""
        if self.use_spaces and not self.in_single_line:
            self.result.append(' ' * (self.indent_level * self.indent_size))
    
    def _newline(self):
        """Add newline to output."""
        if self.use_spaces and not self.in_single_line:
            self.result.append('\n')
    
    def visit(self, node):
        """Visit a node and return its SynthLang representation."""
        if node is None:
            return ''
        
        self.nodes_processed += 1
        node_type = type(node).__name__
        
        # Log processing of complex nodes
        if node_type in ['FunctionDef', 'ClassDef', 'AsyncFunctionDef', 'Match']:
            translator_logger.log_ast_transformation(
                transformation_type="ast_node_visit",
                node_type=node_type,
                details={"nodes_processed": self.nodes_processed},
                optimization_applied=True
            )
        
        # Reset result for this node
        old_result = self.result
        self.result = []
        
        method_name = f'visit_{type(node).__name__}'
        visitor = getattr(self, method_name, self.generic_visit)
        
        try:
            visitor(node)
        except Exception as e:
            translator_logger.log_error(
                error=e,
                operation_id=None,
                code_context=f"Node type: {node_type}, method: {method_name}",
                stage="node_visit"
            )
            # Fallback to generic visit
            self.generic_visit(node)
        
        # Get the result and restore previous state
        result = ''.join(str(r) for r in self.result)
        self.result = old_result
        
        return result
    
    def generic_visit(self, node):
        """Generic visitor for unsupported nodes."""
        node_type = type(node).__name__
        translator_logger._safe_log(
            translator_logger.logger.warning,
            f"Using generic visitor for unsupported node type: {node_type}",
            {"node_type": node_type, "nodes_processed": self.nodes_processed}
        )
        self.result.append(f'[{node_type}]')
    
    def visit_Module(self, node):
        """Module: collection of statements"""
        results = []
        for stmt in node.body:
            result = self.visit(stmt)
            if result:
                results.append(result)
                if self.use_spaces:
                    results.append('\n')
        
        final_result = ''.join(results).rstrip()
        self.result.append(final_result)
    
    def visit_FunctionDef(self, node):
        """Function definition: name(params) → body"""
        self._indent()
        self.result.append(node.name)
        self.result.append('(')
        
        # Handle parameters
        args = node.args
        all_args = []
        for arg in args.args:
            all_args.append(arg.arg)
        if args.vararg:
            all_args.append(f'*{args.vararg.arg}')
        if args.kwarg:
            all_args.append(f'**{args.kwarg.arg}')
        
        self.result.append(','.join(all_args))
        self.result.append(')→')
        
        # Handle body
        if len(node.body) == 1 and isinstance(node.body[0], ast.Return):
            self.in_single_line = True
            body_result = self.visit(node.body[0].value)
            self.result.append(body_result)
            self.in_single_line = False
        else:
            if self.use_spaces:
                self.result.append('{')
                self._newline()
            self.indent_level += 1
            for stmt in node.body:
                if self.use_spaces:
                    self._indent()
                stmt_result = self.visit(stmt)
                self.result.append(stmt_result)
                if self.use_spaces:
                    self._newline()
            self.indent_level -= 1
            if self.use_spaces:
                self._indent()
                self.result.append('}')
    
    def visit_Return(self, node):
        """Return statement: → expr"""
        self._indent()
        self.result.append('→')
        if node.value:
            value_result = self.visit(node.value)
            self.result.append(value_result)
    
    def visit_Assign(self, node):
        """Assignment: target = value"""
        self._indent()
        for target in node.targets:
            target_result = self.visit(target)
            self.result.append(target_result)
        self.result.append('=')
        value_result = self.visit(node.value)
        self.result.append(value_result)
    
    def visit_Name(self, node):
        """Variable name"""
        self.result.append(node.id)
    
    def visit_Constant(self, node):
        """Enhanced constant handling with multiline strings"""
        if node.value is True:
            self.result.append('✓')
        elif node.value is False:
            self.result.append('✗')
        elif node.value is None:
            self.result.append('∅')
        elif isinstance(node.value, str):
            s = node.value
            # Only treat as multiline if it has multiple actual lines with content
            lines = s.split('\n')
            is_multiline = len(lines) > 1 and any(line.strip() for line in lines)
            
            if is_multiline:
                self.result.append('"""' + s + '"""')
            else:
                # Use repr to get proper escaping for the actual string value
                escaped_str = repr(s)
                
                # Convert single quotes to double quotes for consistency
                if escaped_str.startswith("'") and escaped_str.endswith("'"):
                    # Extract the content and wrap in double quotes
                    inner = escaped_str[1:-1]
                    # Escape any double quotes in the content
                    inner = inner.replace('"', '\\"')
                    self.result.append(f'"{inner}"')
                else:
                    self.result.append(escaped_str)
        else:
            self.result.append(str(node.value))
    
    # Support for older Python AST node types (Python < 3.8)
    def visit_Num(self, node):
        """Numeric literal (older Python versions)"""
        self.result.append(str(node.n))
    
    def visit_Str(self, node):
        """String literal (older Python versions)"""
        # Get the raw string representation preserving escape sequences
        s = node.s
        
        # Only treat as multiline if it has multiple actual lines with content
        lines = s.split('\n')
        is_multiline = len(lines) > 1 and any(line.strip() for line in lines)
        
        if is_multiline:
            self.result.append('"""' + s + '"""')
        else:
            # Use repr to get proper escaping for the actual string value
            # This will give us the escaped representation that Python sees
            escaped_str = repr(s)
            
            # Convert single quotes to double quotes for consistency
            if escaped_str.startswith("'") and escaped_str.endswith("'"):
                # Extract the content and wrap in double quotes
                inner = escaped_str[1:-1]
                # Escape any double quotes in the content
                inner = inner.replace('"', '\\"')
                self.result.append(f'"{inner}"')
            else:
                self.result.append(escaped_str)
    
    def visit_NameConstant(self, node):
        """Name constants like True, False, None (older Python versions)"""
        if node.value is True:
            self.result.append('✓')
        elif node.value is False:
            self.result.append('✗')
        elif node.value is None:
            self.result.append('∅')
        else:
            self.result.append(str(node.value))
    
    def visit_Pass(self, node):
        """Pass statement"""
        self._indent()
        self.result.append('⋯')
    
    def visit_Expr(self, node):
        """Expression statement"""
        self._indent()
        value_result = self.visit(node.value)
        self.result.append(value_result)
    
    def visit_Delete(self, node):
        """Delete statement: ⌫ targets"""
        self._indent()
        self.result.append('⌫')
        for i, target in enumerate(node.targets):
            if i > 0:
                self.result.append(',')
            target_result = self.visit(target)
            self.result.append(target_result)
    
    def visit_Attribute(self, node):
        """Attribute access: obj.attr"""
        value_result = self.visit(node.value)
        self.result.append(value_result)
        self.result.append('.')
        self.result.append(node.attr)
    
    def visit_Subscript(self, node):
        """Subscript operation: obj[key]"""
        value_result = self.visit(node.value)
        self.result.append(value_result)
        self.result.append('[')
        slice_result = self.visit(node.slice)
        self.result.append(slice_result)
        self.result.append(']')
    
    def visit_Index(self, node):
        """Index node (for older Python versions)"""
        value_result = self.visit(node.value)
        self.result.append(value_result)
    
    def visit_Starred(self, node):
        """Starred expression: *args"""
        self.result.append('✦')
        value_result = self.visit(node.value)
        self.result.append(value_result)
    
    def visit_Bytes(self, node):
        """Bytes literal: b'...'"""
        # Get repr and convert single quotes to double quotes for consistency
        repr_str = repr(node.s)
        if repr_str.startswith("b'") and repr_str.endswith("'"):
            # Convert b'...' to b"..."
            inner = repr_str[2:-1]  # Remove b' and '
            inner = inner.replace('"', '\\"')  # Escape any double quotes
            self.result.append(f'b"{inner}"')
        else:
            self.result.append(repr_str)
    
    def visit_For(self, node):
        """For loop: ∀var∈iterable:"""
        self._indent()
        self.result.append('∀')
        
        # Handle tuple unpacking without parentheses for cleaner syntax
        if isinstance(node.target, ast.Tuple):
            for i, elt in enumerate(node.target.elts):
                if i > 0:
                    self.result.append(',')
                elt_result = self.visit(elt)
                self.result.append(elt_result)
        else:
            target_result = self.visit(node.target)
            self.result.append(target_result)
            
        self.result.append('∈')
        iter_result = self.visit(node.iter)
        self.result.append(iter_result)
        self.result.append(':')
        
        # Handle body
        if node.body:
            self._newline()
            self.indent_level += 1
            for stmt in node.body:
                self._indent()
                stmt_result = self.visit(stmt)
                self.result.append(stmt_result)
                self._newline()
            self.indent_level -= 1
        
        # Handle else clause if present
        if node.orelse:
            self._indent()
            self.result.append('◊:')
            self._newline()
            self.indent_level += 1
            for stmt in node.orelse:
                self._indent()
                stmt_result = self.visit(stmt)
                self.result.append(stmt_result)
                self._newline()
            self.indent_level -= 1
    
    def visit_If(self, node):
        """If statement: ?condition:"""
        self._indent()
        self.result.append('?')
        test_result = self.visit(node.test)
        self.result.append(test_result)
        self.result.append(':')
        
        # Handle body
        if node.body:
            self._newline()
            self.indent_level += 1
            for stmt in node.body:
                self._indent()
                stmt_result = self.visit(stmt)
                self.result.append(stmt_result)
                self._newline()
            self.indent_level -= 1
        
        # Handle else clause if present
        if node.orelse:
            self._indent()
            self.result.append('◊:')
            self._newline()
            self.indent_level += 1
            for stmt in node.orelse:
                self._indent()
                stmt_result = self.visit(stmt)
                self.result.append(stmt_result)
                self._newline()
            self.indent_level -= 1
    
    def visit_ImportFrom(self, node):
        """Import from statement: ⊲module⊳names"""
        self._indent()
        self.result.append('⊲')
        if node.module:
            self.result.append(node.module)
        else:
            self.result.append('.')
        self.result.append('⊳')
        
        # Handle import names
        if node.names:
            names = []
            for alias in node.names:
                if alias.name == '*':
                    names.append('*')
                elif alias.asname:
                    names.append(f'{alias.name}→{alias.asname}')
                else:
                    names.append(alias.name)
            self.result.append(','.join(names))
    
    def visit_With(self, node):
        """With statement: ◊context:"""
        self._indent()
        self.result.append('◊')
        
        # Handle context managers
        for i, item in enumerate(node.items):
            if i > 0:
                self.result.append(',')
            context_result = self.visit(item.context_expr)
            self.result.append(context_result)
            if item.optional_vars:
                self.result.append('→')
                vars_result = self.visit(item.optional_vars)
                self.result.append(vars_result)
        
        self.result.append(':')
        
        # Handle body
        if node.body:
            if self.use_spaces:
                self._newline()
            self.indent_level += 1
            for stmt in node.body:
                if self.use_spaces:
                    self._indent()
                stmt_result = self.visit(stmt)
                self.result.append(stmt_result)
                if self.use_spaces:
                    self._newline()
            self.indent_level -= 1
    
    def visit_Slice(self, node):
        """Slice operation: start:stop:step"""
        if node.lower:
            lower_result = self.visit(node.lower)
            self.result.append(lower_result)
        self.result.append(':')
        if node.upper:
            upper_result = self.visit(node.upper)
            self.result.append(upper_result)
        if node.step:
            self.result.append(':')
            step_result = self.visit(node.step)
            self.result.append(step_result)
    
    def visit_List(self, node):
        """List literal: [items]"""
        self.result.append('[')
        for i, elt in enumerate(node.elts):
            if i > 0:
                self.result.append(',')
            elt_result = self.visit(elt)
            self.result.append(elt_result)
        self.result.append(']')
    
    def visit_Tuple(self, node):
        """Tuple literal: (items)"""
        self.result.append('(')
        for i, elt in enumerate(node.elts):
            if i > 0:
                self.result.append(',')
            elt_result = self.visit(elt)
            self.result.append(elt_result)
        self.result.append(')')
    
    def visit_Set(self, node):
        """Set literal: {items}"""
        self.result.append('{')
        for i, elt in enumerate(node.elts):
            if i > 0:
                self.result.append(',')
            elt_result = self.visit(elt)
            self.result.append(elt_result)
        self.result.append('}')
    
    def visit_Dict(self, node):
        """Dictionary literal: {key: value}"""
        self.result.append('{')
        for i, (key, value) in enumerate(zip(node.keys, node.values)):
            if i > 0:
                self.result.append(',')
            key_result = self.visit(key)
            self.result.append(key_result)
            self.result.append(':')
            value_result = self.visit(value)
            self.result.append(value_result)
        self.result.append('}')
    
    def visit_ListComp(self, node):
        """List comprehension: [expr ∀ vars ∈ iter ? condition]"""
        self.result.append('[')
        
        # Visit the element expression
        elt_result = self.visit(node.elt)
        self.result.append(elt_result)
        
        # Process generators (for loops and conditions)
        for generator in node.generators:
            self.result.append('∀')
            
            # Handle target (variable being iterated)
            target_result = self.visit(generator.target)
            self.result.append(target_result)
            
            self.result.append('∈')
            
            # Handle iterable
            iter_result = self.visit(generator.iter)
            self.result.append(iter_result)
            
            # Handle conditions (if clauses)
            for if_ in generator.ifs:
                self.result.append('?')
                if_result = self.visit(if_)
                self.result.append(if_result)
        
        self.result.append(']')
    
    def visit_SetComp(self, node):
        """Set comprehension: {expr ∀ vars ∈ iter ? condition}"""
        self.result.append('{')
        
        # Visit the element expression
        elt_result = self.visit(node.elt)
        self.result.append(elt_result)
        
        # Process generators
        for generator in node.generators:
            self.result.append('∀')
            target_result = self.visit(generator.target)
            self.result.append(target_result)
            self.result.append('∈')
            iter_result = self.visit(generator.iter)
            self.result.append(iter_result)
            
            for if_ in generator.ifs:
                self.result.append('?')
                if_result = self.visit(if_)
                self.result.append(if_result)
        
        self.result.append('}')
    
    def visit_DictComp(self, node):
        """Dict comprehension: {key:value ∀ vars ∈ iter ? condition}"""
        self.result.append('{')
        
        # Visit key and value expressions
        key_result = self.visit(node.key)
        self.result.append(key_result)
        self.result.append(':')
        value_result = self.visit(node.value)
        self.result.append(value_result)
        
        # Process generators
        for generator in node.generators:
            self.result.append('∀')
            target_result = self.visit(generator.target)
            self.result.append(target_result)
            self.result.append('∈')
            iter_result = self.visit(generator.iter)
            self.result.append(iter_result)
            
            for if_ in generator.ifs:
                self.result.append('?')
                if_result = self.visit(if_)
                self.result.append(if_result)
        
        self.result.append('}')
    
    def visit_GeneratorExp(self, node):
        """Generator expression: (expr ∀ vars ∈ iter ? condition)"""
        self.result.append('(')
        
        # Visit the element expression
        elt_result = self.visit(node.elt)
        self.result.append(elt_result)
        
        # Process generators
        for generator in node.generators:
            self.result.append('∀')
            target_result = self.visit(generator.target)
            self.result.append(target_result)
            self.result.append('∈')
            iter_result = self.visit(generator.iter)
            self.result.append(iter_result)
            
            for if_ in generator.ifs:
                self.result.append('?')
                if_result = self.visit(if_)
                self.result.append(if_result)
        
        self.result.append(')')
    
    def visit_Call(self, node):
        """Function call: func(args)"""
        # Special function mappings
        special_functions = {
            'complex': 'ℂ',
            'print': '↪',
            'input': '↩', 
            'len': '|⋅|',
            'range': '…',
            'encrypt': 'encrypt',  # Keep as-is for test
            'verify': 'verify',    # Keep as-is for test
        }
        
        # Check if this is a special function
        if (isinstance(node.func, ast.Name) and 
            node.func.id in special_functions):
            func_symbol = special_functions[node.func.id]
            self.result.append(func_symbol)
        else:
            func_result = self.visit(node.func)
            self.result.append(func_result)
        
        self.result.append('(')
        
        # Handle positional arguments
        for i, arg in enumerate(node.args):
            if i > 0:
                self.result.append(',')
            arg_result = self.visit(arg)
            self.result.append(arg_result)
        
        # Handle keyword arguments
        if node.args and node.keywords:
            self.result.append(',')
        for i, keyword in enumerate(node.keywords):
            if i > 0:
                self.result.append(',')
            if keyword.arg:  # Regular keyword argument
                self.result.append(keyword.arg)
                self.result.append('=')
                value_result = self.visit(keyword.value)
                self.result.append(value_result)
            else:  # **kwargs
                self.result.append('✦✦')
                value_result = self.visit(keyword.value)
                self.result.append(value_result)
        
        self.result.append(')')
    
    def visit_UnaryOp(self, node):
        """Unary operation: op operand"""
        op_map = {
            'UAdd': '+',
            'USub': '-',
            'Not': '¬',
            'Invert': '~'
        }
        op_name = type(node.op).__name__
        op_symbol = op_map.get(op_name, f'[{op_name}]')
        self.result.append(op_symbol)
        operand_result = self.visit(node.operand)
        self.result.append(operand_result)
    
    def visit_BinOp(self, node):
        """Binary operation: left op right"""
        op_map = {
            'Add': '+',
            'Sub': '-',
            'Mult': '×',
            'Div': '÷',
            'Mod': '%',
            'Pow': '^',
            'LShift': '<<',
            'RShift': '>>',
            'BitOr': '|',
            'BitXor': '⊕',
            'BitAnd': '&',
            'FloorDiv': '÷÷'
        }
        
        left_result = self.visit(node.left)
        self.result.append(left_result)
        
        op_name = type(node.op).__name__
        op_symbol = op_map.get(op_name, f'[{op_name}]')
        self.result.append(op_symbol)
        
        right_result = self.visit(node.right)
        self.result.append(right_result)
    
    def visit_Compare(self, node):
        """Comparison operations: a > b, a == b, etc."""
        # Map comparison operators
        op_map = {
            'Eq': '=',      # ==
            'NotEq': '≠',   # !=
            'Lt': '<',      # <
            'LtE': '≤',     # <=
            'Gt': '>',      # >
            'GtE': '≥',     # >=
            'Is': '≡',      # is
            'IsNot': '≢',   # is not
            'In': '∈',      # in
            'NotIn': '∉',   # not in
        }
        
        left_result = self.visit(node.left)
        self.result.append(left_result)
        
        for i, (op, comparator) in enumerate(zip(node.ops, node.comparators)):
            op_name = type(op).__name__
            op_symbol = op_map.get(op_name, f'[{op_name}]')
            self.result.append(op_symbol)
            
            comp_result = self.visit(comparator)
            self.result.append(comp_result)
    
    def visit_BoolOp(self, node):
        """Boolean operations: and, or"""
        op_map = {
            'And': '∧',  # and
            'Or': '∨',   # or
        }
        
        op_name = type(node.op).__name__
        op_symbol = op_map.get(op_name, f'[{op_name}]')
        
        for i, value in enumerate(node.values):
            if i > 0:
                self.result.append(op_symbol)
            value_result = self.visit(value)
            self.result.append(value_result)
    
    def visit_UnaryOp(self, node):
        """Unary operations: not, -, +"""
        op_map = {
            'Not': '¬',    # not
            'UAdd': '+',   # +
            'USub': '-',   # -
            'Invert': '~', # ~
        }
        
        op_name = type(node.op).__name__
        op_symbol = op_map.get(op_name, f'[{op_name}]')
        self.result.append(op_symbol)
        
        operand_result = self.visit(node.operand)
        self.result.append(operand_result)
    
    def visit_ClassDef(self, node):
        """Class definition: τ Name { body }"""
        self._indent()
        self.result.append('τ ')
        self.result.append(node.name)
        
        # Handle inheritance
        if node.bases:
            self.result.append('(')
            for i, base in enumerate(node.bases):
                if i > 0:
                    self.result.append(',')
                base_result = self.visit(base)
                self.result.append(base_result)
            self.result.append(')')
        
        self.result.append('{')
        if self.use_spaces:
            self._newline()
        
        self.indent_level += 1
        for stmt in node.body:
            stmt_result = self.visit(stmt)
            self._indent()
            self.result.append(stmt_result)
            if self.use_spaces:
                self._newline()
        self.indent_level -= 1
        
        if self.use_spaces:
            self._indent()
        self.result.append('}')

    # Async/Await support
    def visit_AsyncFunctionDef(self, node):
        """Async function definition: ⏳ name(params) → body"""
        self._indent()
        self.result.append('⏳')
        # Reuse regular function definition logic
        self.result.append(node.name)
        self.result.append('(')
        
        args = node.args
        all_args = []
        for arg in args.args:
            all_args.append(arg.arg)
        if args.vararg:
            all_args.append(f'*{args.vararg.arg}')
        if args.kwarg:
            all_args.append(f'**{args.kwarg.arg}')
        
        self.result.append(','.join(all_args))
        self.result.append(')→')
        
        if len(node.body) == 1 and isinstance(node.body[0], ast.Return):
            self.in_single_line = True
            return_result = self.visit(node.body[0].value)
            self.result.append(return_result)
            self.in_single_line = False
        else:
            if self.use_spaces:
                self.result.append('{')
                self._newline()
            self.indent_level += 1
            for stmt in node.body:
                if self.use_spaces:
                    self._indent()
                stmt_result = self.visit(stmt)
                self.result.append(stmt_result)
                if self.use_spaces:
                    self._newline()
            self.indent_level -= 1
            if self.use_spaces:
                self._indent()
                self.result.append('}')
    
    def visit_Await(self, node):
        """Await expression: ⏸ expr"""
        self.result.append('⏸')
        self.visit(node.value)
    
    def visit_AsyncFor(self, node):
        """Async for loop: ⏳∀ target ∈ iter : body"""
        self._indent()
        self.result.append('⏳∀')
        self.visit(node.target)
        self.result.append('∈')
        self.visit(node.iter)
        self.result.append(':')
        
        if self.use_spaces:
            self.result.append('{')
            self._newline()
        
        self.indent_level += 1
        for stmt in node.body:
            self.visit(stmt)
            if self.use_spaces:
                self._newline()
        self.indent_level -= 1
        
        if self.use_spaces:
            self._indent()
            self.result.append('}')
    
    def visit_AsyncWith(self, node):
        """Async with statement: ⏳◊ expr ⇨ target : body"""
        self._indent()
        self.result.append('⏳◊')
        
        # Handle multiple context managers
        for i, item in enumerate(node.items):
            if i > 0:
                if self.use_spaces:
                    self.result.append(',')
                    self._newline()
                    self._indent()
                    self.result.append('  ')
                else:
                    self.result.append(',')
            
            context_result = self.visit(item.context_expr)
            self.result.append(context_result)
            if item.optional_vars:
                self.result.append('⇨')
                vars_result = self.visit(item.optional_vars)
                self.result.append(vars_result)
        
        self.result.append(':')
        
        if self.use_spaces:
            self.result.append('{')
            self._newline()
        
        self.indent_level += 1
        for stmt in node.body:
            if self.use_spaces:
                self._indent()
            stmt_result = self.visit(stmt)
            self.result.append(stmt_result)
            if self.use_spaces:
                self._newline()
        self.indent_level -= 1
        
        if self.use_spaces:
            self._indent()
            self.result.append('}')
    
        
        if self.use_spaces:
            self._indent()
            self.result.append('}')
    
    # Pattern Matching (Python 3.10+)
    def visit_Match(self, node):
        """Match statement: ⊡ subject : cases"""
        self._indent()
        self.result.append('⊡')
        self.visit(node.subject)
        self.result.append(':')
        
        if self.use_spaces:
            self.result.append('{')
            self._newline()
        
        self.indent_level += 1
        for case in node.cases:
            self.visit(case)
        self.indent_level -= 1
        
        if self.use_spaces:
            self._indent()
            self.result.append('}')
    
    def visit_match_case(self, node):
        """Match case: ▷ pattern : body"""
        self._indent()
        self.result.append('▷')
        self.visit(node.pattern)
        
        if node.guard:
            self.result.append('?')
            self.visit(node.guard)
        
        self.result.append(':')
        
        if self.use_spaces:
            self.result.append('{')
            self._newline()
        
        self.indent_level += 1
        for stmt in node.body:
            self.visit(stmt)
            if self.use_spaces:
                self._newline()
        self.indent_level -= 1
        
        if self.use_spaces:
            self._indent()
            self.result.append('}')
            self._newline()
    
    # Pattern types for match/case
    def visit_MatchValue(self, node):
        """Match value pattern"""
        self.visit(node.value)
    
    def visit_MatchSingleton(self, node):
        """Match singleton pattern (None, True, False)"""
        if node.value is True:
            self.result.append('✓')
        elif node.value is False:
            self.result.append('✗')
        elif node.value is None:
            self.result.append('∅')
    
    def visit_MatchSequence(self, node):
        """Match sequence pattern [patterns]"""
        self.result.append('[')
        for i, pattern in enumerate(node.patterns):
            if i > 0:
                self.result.append(',')
            self.visit(pattern)
        self.result.append(']')
    
    def visit_MatchMapping(self, node):
        """Match mapping pattern {key: pattern}"""
        self.result.append('{')
        for i, (key, pattern) in enumerate(zip(node.keys, node.patterns)):
            if i > 0:
                self.result.append(',')
            self.visit(key)
            self.result.append(':')
            self.visit(pattern)
        if node.rest:
            if node.keys:
                self.result.append(',')
            self.result.append('**')
            self.result.append(node.rest)
        self.result.append('}')
    
    def visit_MatchClass(self, node):
        """Match class pattern Class(args)"""
        self.visit(node.cls)
        self.result.append('(')
        
        patterns = []
        for pattern in node.patterns:
            patterns.append(pattern)
        for kwd, pattern in zip(node.kwd_attrs, node.kwd_patterns):
            patterns.append(f'{kwd}=')
            patterns.append(pattern)
        
        for i, item in enumerate(patterns):
            if i > 0:
                self.result.append(',')
            if isinstance(item, str):
                self.result.append(item)
            else:
                self.visit(item)
        
        self.result.append(')')
    
    def visit_MatchAs(self, node):
        """Match as pattern: pattern ⇨ name"""
        if node.pattern:
            self.visit(node.pattern)
            self.result.append('⇨')
        if node.name:
            self.result.append(node.name)
        else:
            self.result.append('◯')  # Wildcard
    
    def visit_MatchOr(self, node):
        """Match or pattern: pattern | pattern"""
        for i, pattern in enumerate(node.patterns):
            if i > 0:
                self.result.append('|')
            self.visit(pattern)
    
    def visit_MatchStar(self, node):
        """Match star pattern: *name"""
        self.result.append('✦')
        if node.name:
            self.result.append(node.name)
    
    # Named expressions (walrus operator)
    def visit_NamedExpr(self, node):
        """Named expression: (target ≔ value)"""
        self.result.append('(')
        self.visit(node.target)
        self.result.append('≔')
        self.visit(node.value)
        self.result.append(')')
    
    # Enhanced Try/Except/Else/Finally
    def visit_Try(self, node):
        """Try block with full else support"""
        self._indent()
        self.result.append('⟦')
        if self.use_spaces:
            self._newline()
        
        self.indent_level += 1
        for stmt in node.body:
            if self.use_spaces:
                self._indent()
            stmt_result = self.visit(stmt)
            self.result.append(stmt_result)
            if self.use_spaces:
                self._newline()
        self.indent_level -= 1
        
        # Exception handlers
        for handler in node.handlers:
            if self.use_spaces:
                self._indent()
            self.result.append('⟧')
            if handler.type:
                type_result = self.visit(handler.type)
                self.result.append(type_result)
            if handler.name:
                self.result.append('⇨')
                self.result.append(handler.name)
            self.result.append(':')
            
            if self.use_spaces:
                self.result.append('{')
                self._newline()
            
            self.indent_level += 1
            for stmt in handler.body:
                if self.use_spaces:
                    self._indent()
                stmt_result = self.visit(stmt)
                self.result.append(stmt_result)
                if self.use_spaces:
                    self._newline()
            self.indent_level -= 1
            
            if self.use_spaces:
                self._indent()
                self.result.append('}')
        
        # Else block
        if node.orelse:
            if self.use_spaces:
                self._indent()
            self.result.append('⟧:')  # else after except
            if self.use_spaces:
                self.result.append('{')
                self._newline()
            
            self.indent_level += 1
            for stmt in node.orelse:
                if self.use_spaces:
                    self._indent()
                stmt_result = self.visit(stmt)
                self.result.append(stmt_result)
                if self.use_spaces:
                    self._newline()
            self.indent_level -= 1
            
            if self.use_spaces:
                self._indent()
                self.result.append('}')
        
        # Finally block
        if node.finalbody:
            if self.use_spaces:
                self._indent()
            self.result.append('⟨⟩')
            if self.use_spaces:
                self.result.append('{')
                self._newline()
            
            self.indent_level += 1
            for stmt in node.finalbody:
                if self.use_spaces:
                    self._indent()
                stmt_result = self.visit(stmt)
                self.result.append(stmt_result)
                if self.use_spaces:
                    self._newline()
            self.indent_level -= 1
            
            if self.use_spaces:
                self._indent()
                self.result.append('}')
    
    # Enhanced string formatting
    def visit_JoinedStr(self, node):
        """F-string: f"...{expr}..." """
        self.result.append('ƒ"')
        for value in node.values:
            if isinstance(value, ast.FormattedValue):
                self.result.append('{')
                self.visit(value.value)
                if value.format_spec:
                    self.result.append(':')
                    self.visit(value.format_spec)
                self.result.append('}')
            else:
                self.visit(value)
        self.result.append('"')
    
    def log_performance_summary(self):
        """Log performance summary for this converter instance."""
        processing_time = time.time() - self.start_time
        translator_logger.log_performance_metrics(
            operation_id=None,
            stage="ast_visitor_completion",
            duration=processing_time,
            additional_metrics={
                "nodes_processed": self.nodes_processed,
                "nodes_per_second": round(self.nodes_processed / processing_time, 2) if processing_time > 0 else 0,
                "use_spaces": self.use_spaces,
                "indent_size": self.indent_size
            }
        )


def _ast_to_synthlang_compact(node: ast.AST, indent_level: int = 0, annotate_lines: bool = False) -> str:
    """
    Convert AST node to compact SynthLang (no spacing/indentation) using node_map.
    
    Args:
        node: AST node to convert
        indent_level: Unused in compact mode, kept for compatibility
        
    Returns:
        Compact SynthLang representation of the node
    """
    if node is None:
        return ''
    
    node_type = type(node).__name__
    
    # Log compact mode transformation
    if indent_level == 0:  # Only log at root level
        translator_logger.log_ast_transformation(
            transformation_type="ast_to_synthlang_compact",
            node_type=node_type,
            details={"compact_mode": True},
            optimization_applied=True
        )
    
    if node_type in NODE_MAP:
        try:
            # Use NODE_MAP but with compact formatting (no indentation)
            result = NODE_MAP[node_type](node, 0)  # Always use 0 indent for compact
            # Remove all newlines and extra spaces for compact mode
            compact_result = result.replace('\n', '').replace('  ', '').replace(' {', '{').replace('} ', '}')
            
            if indent_level == 0:  # Log successful compact translation
                translator_logger.log_optimization(
                    optimization_type="compact_formatting",
                    before_value=f"length:{len(result)}",
                    after_value=f"length:{len(compact_result)}",
                    node_location=node_type
                )
            
            return compact_result
        except Exception as e:
            translator_logger.log_error(
                error=e,
                operation_id=None,
                code_context=f"Compact mode for node type: {node_type}",
                stage="compact_translation"
            )
            return f'[{node_type}]'
    else:
        # Fallback - should rarely be needed now with comprehensive NODE_MAP
        translator_logger._safe_log(
            translator_logger.logger.warning,
            f"Node type {node_type} not in NODE_MAP for compact translation",
            {"node_type": node_type}
        )
        return f'[{node_type}]'

def enhanced_python_to_synthlang(code: str, compact: bool = False, indent_size: int = 2, annotate_lines: bool = False) -> str:
    """
    Convert Python code to SynthLang notation with full Python 3.10+ support.
    
    Args:
        code: Python source code as a string
        compact: If True, produces compact output without indentation using node_map
        indent_size: Number of spaces for indentation (if not compact)
        annotate_lines: If True, add inline source line annotations
        
    Returns:
        SynthLang notation as a string
    """
    start_time = time.time()
    operation_id = translator_logger.log_minification_start(
        code_length=len(code),
        compression_depth=1,  # Single-pass translation
        aggressive=compact
    )
    
    try:
        translator_logger._safe_log(
            translator_logger.logger.info,
            f"Starting Python to SynthLang translation (compact={compact}, indent_size={indent_size})",
            {"operation_id": operation_id, "input_length": len(code)}
        )
        
        tree = ast.parse(code)
        translator_logger.log_ast_transformation(
            transformation_type="python_to_synthlang",
            node_type="Module",
            details={"compact_mode": compact, "indent_size": indent_size},
            optimization_applied=True
        )
        
        if compact:
            # Use the node_map for compact mode (no spacing)
            result = _ast_to_synthlang_compact(tree, 0, annotate_lines)
            translator_logger._safe_log(
                translator_logger.logger.debug,
                "Using compact translation mode",
                {"operation_id": operation_id}
            )
        else:
            # Use the node_map for formatted mode
            result = _ast_to_synthlang_node_map(tree, 0, annotate_lines)
            translator_logger._safe_log(
                translator_logger.logger.debug,
                "Using formatted translation mode",
                {"operation_id": operation_id}
            )
        
        processing_time = time.time() - start_time
        translator_logger.log_minification_complete(
            operation_id=operation_id,
            original_size=len(code),
            minified_size=len(result),
            processing_time=processing_time,
            token_metrics={
                "translation_type": "python_to_synthlang",
                "compact_mode": compact,
                "ast_nodes_processed": len([node for node in ast.walk(tree)])
            }
        )
        
        return result
        
    except SyntaxError as e:
        # Graceful fallback for broken code - useful for debugging scenarios
        fallback_result = _fallback_translate_broken_code_synthlang(code, e)
        
        translator_logger.log_error(
            error=e,
            operation_id=operation_id,
            code_context=code[:500],  # First 500 chars for context
            stage="parsing"
        )
        
        translator_logger._safe_log(
            translator_logger.logger.warning,
            f"Syntax error in code, using fallback translation: {str(e)}",
            {
                "operation_id": operation_id,
                "error_type": type(e).__name__,
                "fallback_used": True
            }
        )
        
        return fallback_result
        
    except Exception as e:
        # Attempt graceful fallback even for other errors
        fallback_result = f"# TRANSLATION ERROR: {type(e).__name__}\n# Original code with issues:\n" + _format_code_as_comments_synthlang(code)
        
        translator_logger.log_error(
            error=e,
            operation_id=operation_id,
            code_context=code[:500],
            stage="translation"
        )
        
        return fallback_result

def _format_code_as_comments_synthlang(code: str) -> str:
    """Format code as comments for SynthLang fallback scenarios."""
    lines = code.split('\n')
    return '\n'.join(f"# {line}" if line.strip() else "#" for line in lines)

def _fallback_translate_broken_code_synthlang(code: str, syntax_error: SyntaxError) -> str:
    """
    Attempt to translate broken Python code to SynthLang by processing line-by-line
    and providing helpful information about syntax errors.
    """
    try:
        lines = code.split('\n')
        error_line = getattr(syntax_error, 'lineno', None)
        error_col = getattr(syntax_error, 'offset', None)
        error_msg = str(syntax_error).replace('(<unknown>, line ', '(line ')
        
        result_lines = []
        
        # Add error information header using SynthLang symbols
        result_lines.append(f"# ⚡ SYNTAX ERROR: {error_msg}")
        if error_line:
            result_lines.append(f"# Error at line {error_line}" + (f", column {error_col}" if error_col else ""))
        result_lines.append("# Attempting partial SynthLang translation...")
        result_lines.append("")
        
        # Try to process code in smaller chunks
        for i, line in enumerate(lines, 1):
            line = line.rstrip()
            if not line.strip():
                result_lines.append("")
                continue
                
            # Mark the error line
            if error_line and i == error_line:
                result_lines.append(f"# ⚠ >>> SYNTAX ERROR ON THIS LINE <<<")
                result_lines.append(f"# {line}")
                if error_col and error_col > 0:
                    result_lines.append(f"# {' ' * (error_col - 1)}^-- Error here")
                continue
            
            # Try basic SynthLang transformation
            try:
                if line.strip() and not line.strip().startswith('#'):
                    translated_line = _basic_line_translation_synthlang(line)
                    result_lines.append(translated_line)
                else:
                    result_lines.append(f"# {line}")
            except:
                result_lines.append(f"# ⟨UNPARSEABLE⟩ {line}")
        
        return '\n'.join(result_lines)
        
    except Exception as fallback_error:
        # Final fallback - just format as comments with error info  
        return f"# ⚡ SYNTAX ERROR: {syntax_error}\n# Unable to parse - original code below:\n" + _format_code_as_comments_synthlang(code)

def _basic_line_translation_synthlang(line: str) -> str:
    """
    Basic line-by-line translation to SynthLang symbols for common Python patterns.
    Used when full AST parsing fails.
    """
    line = line.strip()
    
    # Function definitions
    if line.startswith('def '):
        return f"ƒ{line[4:].replace(':', '→')}..."
    
    # Class definitions  
    if line.startswith('class '):
        return f"τ {line[6:].replace(':', '→')}..."
    
    # If statements
    if line.startswith('if '):
        return f"?{line[3:].replace(':', '→')}..."
    
    # For loops
    if line.startswith('for '):
        parts = line[4:].split(' in ', 1)
        if len(parts) == 2:
            return f"∀{parts[0]}∈{parts[1].replace(':', '→')}..."
        return f"∀{line[4:].replace(':', '→')}..."
    
    # While loops
    if line.startswith('while '):
        return f"↻{line[6:].replace(':', '→')}..."
    
    # Return statements
    if line.startswith('return '):
        return f"→{line[7:]}"
    
    # Import statements - use special symbols
    if line.startswith('import '):
        return f"⊲{line[7:]}"
    if line.startswith('from '):
        return f"⊲{line[5:].replace(' import ', '⊳')}"
    
    # Comments
    if line.startswith('#'):
        return line
    
    # Try to handle assignments with symbols
    if '=' in line and not any(op in line for op in ['==', '!=', '<=', '>=']):
        parts = line.split('=', 1)
        if len(parts) == 2:
            return f"{parts[0].strip()}={parts[1].strip()}"
    
    # Default: return as symbolic comment
    return f"⟨{line}⟩"


def python_to_synthlang_node_map(code: str, indent_size: int = 2) -> str:
    """
    Convert Python code to SynthLang notation using the node_map approach.
    
    Args:
        code: Python source code as a string
        indent_size: Number of spaces for indentation
        
    Returns:
        SynthLang notation as a string
    """
    start_time = time.time()
    operation_id = translator_logger.log_minification_start(
        code_length=len(code),
        compression_depth=1,
        aggressive=False
    )
    
    try:
        translator_logger._safe_log(
            translator_logger.logger.info,
            f"Starting Python to SynthLang translation using node_map (indent_size={indent_size})",
            {"operation_id": operation_id, "input_length": len(code)}
        )
        
        tree = ast.parse(code)
        translator_logger.log_ast_transformation(
            transformation_type="python_to_synthlang_node_map",
            node_type="Module",
            details={"indent_size": indent_size},
            optimization_applied=True
        )
        
        result = _ast_to_synthlang_node_map(tree, 0)
        
        processing_time = time.time() - start_time
        translator_logger.log_minification_complete(
            operation_id=operation_id,
            original_size=len(code),
            minified_size=len(result),
            processing_time=processing_time,
            token_metrics={
                "translation_type": "node_map",
                "ast_nodes_processed": len([node for node in ast.walk(tree)])
            }
        )
        
        return result
        
    except SyntaxError as e:
        error_msg = f"Syntax error: {e}"
        translator_logger.log_error(
            error=e,
            operation_id=operation_id,
            code_context=code[:500],
            stage="parsing"
        )
        return error_msg
        
    except Exception as e:
        error_msg = f"Conversion error: {e}"
        translator_logger.log_error(
            error=e,
            operation_id=operation_id,
            code_context=code[:500],
            stage="translation"
        )
        return error_msg
    except Exception as e:
        return f"Conversion error: {e}"


# Alias for backward compatibility
python_to_synthlang = enhanced_python_to_synthlang

# Log translator initialization
translator_logger.info(
    "SynthLang translator module initialized successfully",
    {
        "node_map_entries": len(NODE_MAP),
        "enhanced_features": list(ENHANCED_AST_TO_SYNTHLANG.keys())
    }
)


# Example usage with modern Python features
if __name__ == "__main__":
    translator_logger._safe_log(
        translator_logger.logger.info,
        "Starting SynthLang translator demonstration",
        {"demo_mode": True}
    )
    
    # Test async/await
    async_code = """
async def fetch_data(url):
    async with aiohttp.ClientSession() as session:
        response = await session.get(url)
        return await response.json()
    """
    
    # Test pattern matching
    match_code = """
def process_command(command):
    match command:
        case ["move", x, y]:
            return move_to(x, y)
        case ["rotate", angle]:
            return rotate(angle)
        case {"action": "jump", "height": h}:
            return jump(h)
        case _:
            return "Unknown command"
    """
    
    # Test walrus operator
    walrus_code = """
if (n := len(data)) > 10:
    print(f"Too many items: {n}")
    """
    
    # Test complex try/except/else/finally
    try_code = """
try:
    file = open('data.txt')
    data = file.read()
except FileNotFoundError:
    print("File not found")
except IOError as e:
    print(f"IO error: {e}")
else:
    process_data(data)
finally:
    file.close()
    """
    
    # Test class definition with inheritance
    class_code = """
class DataProcessor(BaseProcessor):
    \"\"\"Processes data efficiently\"\"\"
    
    def __init__(self, config):
        self.config = config
        
    def process(self, data):
        return self.transform(data)
    """
    
    examples = [
        ("Async/Await", async_code),
        ("Pattern Matching", match_code),
        ("Walrus Operator", walrus_code),
        ("Try/Except/Else/Finally", try_code),
        ("Class Definition", class_code),
    ]
    
    print("=== Modern Python Features ===")
    translator_logger._safe_log(
        translator_logger.logger.info,
        f"Running demonstration with {len(examples)} code examples",
        {"example_count": len(examples)}
    )
    
    for i, (title, code) in enumerate(examples):
        translator_logger._safe_log(
            translator_logger.logger.debug,
            f"Processing example {i+1}: {title}",
            {"example_index": i+1, "example_title": title, "code_length": len(code)}
        )
        
        print(f"\n{title}:")
        print("Python:")
        print(code)
        print("\nSynthLang (compact - class-based):")
        print(enhanced_python_to_synthlang(code, compact=True))
        print("\nSynthLang (formatted - node_map):")
        print(python_to_synthlang_node_map(code))
        print("-" * 50)
    
    translator_logger._safe_log(
        translator_logger.logger.info,
        "SynthLang translator demonstration completed successfully",
        {"examples_processed": len(examples)}
    )