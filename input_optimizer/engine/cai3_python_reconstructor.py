"""
CAI3 Python Reconstructor - Reconstructs Python code from analyzed structure.
"""

import ast
import re
from typing import List, Dict, Any, Optional
from .cai3_structure_analyzer import StructureInfo
from .cai3_ast_translator import translate_method, CAI3BodyParser
import logging

logger = logging.getLogger(__name__)

class CAI3PythonReconstructor:
    """Reconstructs Python source code from CAI3 structure."""
    
    def __init__(self, cai3_translator=None):
        self.logger = logging.getLogger(__name__)
        self.cai3_translator = cai3_translator
    
    def reconstruct(self, ast_obj, structure: StructureInfo, 
                   cai3_full=None, cai3_map=None) -> str:
        """Reconstruct complete Python file from structure."""
        lines = []
        
        # Add imports
        if structure.imports:
            lines.append(f"import {', '.join(structure.imports)}")
            lines.append("")
        
        # Add enums
        for enum_name, enum_def in structure.enums.items():
            lines.extend(self._reconstruct_enum(enum_name, enum_def))
            lines.append("")
        
        # Add dataclasses
        for class_name, dc_def in structure.dataclasses.items():
            lines.extend(self._reconstruct_dataclass(class_name, dc_def))
            lines.append("")
        
        # Add standalone functions (BEFORE classes)
        for func_name, func_def in structure.functions.items():
            func_lines = self._reconstruct_function(
                func_name, func_def, ast_obj, cai3_full, cai3_map
            )
            lines.extend(func_lines)
            lines.append("")
        
        # Add classes with methods
        for class_name, class_def in structure.classes.items():
            lines.extend(self._reconstruct_class(
                class_name, class_def, ast_obj, cai3_full, cai3_map
            ))
            lines.append("")
        
        # Add main block
        if structure.main_block:
            lines.extend(self._reconstruct_main_block(
                structure.main_block, ast_obj.pools
            ))
        
        # Join all lines
        raw_code = '\n'.join(lines)
        
        # Use Black to format the entire output
        try:
            import black
            formatted_code = black.format_str(raw_code, mode=black.Mode())
            return formatted_code
        except Exception as black_error:
            self.logger.warning(f"Black formatting failed for full output: {black_error}")
            # Return unformatted code if Black fails
            return raw_code
    
    def _reconstruct_enum(self, enum_name: str, enum_def: Dict) -> List[str]:
        """Reconstruct enum definition."""
        lines = [f"class {enum_name}({enum_def['base']}):"]
        for value_name, value in enum_def['values']:
            lines.append(f"    {value_name} = {value}")
        return lines
    
    def _reconstruct_dataclass(self, class_name: str, dc_def: Dict) -> List[str]:
        """Reconstruct dataclass definition."""
        lines = [
            f"@{dc_def['decorator']}",
            f"class {class_name}:"
        ]
        for field in dc_def['fields']:
            if field['default'] is not None:
                lines.append(f"    {field['name']}: {field['type']} = {field['default']}")
            else:
                lines.append(f"    {field['name']}: {field['type']}")
        return lines
    
    def _reconstruct_class(self, class_name: str, class_def: Dict,
                          ast_obj, cai3_full, cai3_map) -> List[str]:
        """Reconstruct class with methods."""
        if class_def['parent']:
            lines = [f"class {class_name}({class_def['parent']}):"]
        else:
            lines = [f"class {class_name}:"]
        
        # Handle enum classes specially
        if class_def.get('is_enum') and class_def.get('enum_values'):
            # Add enum values
            for enum_value in class_def['enum_values']:
                if '=' in enum_value:
                    lines.append(f"    {enum_value}")
                else:
                    lines.append(f"    {enum_value}")
            return lines
        
        # Handle regular classes
        if not class_def['methods']:
            lines.append("    pass")
        else:
            for method_name, method_info in class_def['methods'].items():
                method_lines = self._translate_method_body(
                    method_name, method_info, ast_obj, cai3_full, cai3_map
                )
                for line in method_lines:
                    lines.append(f"    {line}")
                lines.append("")
        
        return lines
    
    def _reconstruct_function(self, func_name: str, func_def: Dict,
                            ast_obj, cai3_full, cai3_map) -> List[str]:
        """Reconstruct standalone function."""
        body_id = func_def.get('body_id')
        body_content = func_def.get('body_content', '')
        args = func_def.get('args', [])
        
        if not body_content and body_id:
            body_content = ast_obj.bodies.get(body_id, '')
        
        if not body_content:
            # Empty function
            return [f"def {func_name}({', '.join(args)}):", "    pass"]
        
        # Translate the body
        if self.cai3_translator:
            try:
                # Use the body translation logic
                translated_body = self._translate_function_body(
                    func_name, args, body_content, body_id, 
                    ast_obj.pools, ast_obj.chain_aliases
                )
                return translated_body.split('\n')
            except Exception as e:
                self.logger.warning(f"Failed to translate function {func_name}: {e}")
        
        # Fallback
        return [
            f"def {func_name}({', '.join(args)}):",
            f"    # Body translation failed for {body_id}",
            "    pass"
        ]
    
    def _translate_method_body(self, method_name: str, method_info: Dict, ast_obj, cai3_full, cai3_map) -> List[str]:
        """Translate method body for class methods."""
        try:
            body_content = method_info.get('body', '')
            
            if method_name == '__init__':
                # Handle constructor
                return self._translate_init_method(method_info, ast_obj)
            else:
                # Handle regular method
                return self._translate_regular_method(method_name, method_info, ast_obj)
        except Exception as e:
            self.logger.error(f"Error translating method body: {e}")
            return [f"def {method_name}(self):", "    pass"]
    
    def _translate_init_method(self, method_info: Dict, ast_obj) -> List[str]:
        """Translate __init__ method."""
        body_content = method_info.get('body_content', method_info.get('body', ''))
        args = method_info.get('args', ['self'])
        
        lines = [f"def __init__({', '.join(args)}):"]
        
        # Process body content for assignments
        if body_content and 'self.' in body_content:
            # Parse assignments like "self.name=p0;self.level=p1"
            assignments = body_content.split(';')
            for assignment in assignments:
                assignment = assignment.strip()
                if assignment.startswith('self.') and '=' in assignment:
                    attr_name, pool_ref = assignment.split('=', 1)
                    attr_name = attr_name.strip()
                    pool_ref = pool_ref.strip()
                    
                    # Resolve pool reference
                    if hasattr(ast_obj, 'pools') and pool_ref in ast_obj.pools:
                        resolved_value = ast_obj.pools[pool_ref]
                        # If it's a string, add quotes
                        if isinstance(resolved_value, str):
                            lines.append(f"    {attr_name} = \"{resolved_value}\"")
                        else:
                            lines.append(f"    {attr_name} = {resolved_value}")
                    else:
                        # Pool not found, use parameter name if it matches
                        param_name = pool_ref.replace('p', 'param_') if pool_ref.startswith('p') else pool_ref
                        lines.append(f"    {attr_name} = {param_name}")
        
        if len(lines) == 1:  # Only the method definition
            lines.append("    pass")
            
        return lines
    
    def _translate_regular_method(self, method_name: str, method_info: Dict, ast_obj) -> List[str]:
        """Translate regular method."""
        body_content = method_info.get('body_content', method_info.get('body', ''))
        
        lines = [f"def {method_name}(self):"]
        
        if body_content:
            # Basic body translation
            lines.append(f"    # {body_content}")
            lines.append("    pass")
        else:
            lines.append("    pass")
            
        return lines

    def _translate_function_body(self, func_name: str, args: List[str], 
                               body_content: str, body_id: str,
                               pools: Dict, chain_aliases: Dict) -> str:
        """Translate function body content using Black formatter for proper formatting."""
        from .cai3_ast_translator import CAI3BodyParser
        import black
        
        try:
            # Initialize body parser
            body_parser = CAI3BodyParser()
            body_parser.pools = pools
            body_parser.chain_aliases = chain_aliases
            
            # Parse body statements
            parsed_stmts = body_parser.parse_body(body_content, body_id)
            
            # Create a simple function template for Black to format
            if parsed_stmts:
                # Convert AST statements to source code
                stmt_sources = []
                for stmt in parsed_stmts:
                    try:
                        stmt_source = ast.unparse(stmt)
                        stmt_sources.append(stmt_source)
                    except Exception as e:
                        stmt_sources.append(f"# Failed to unparse: {e}")
                        
            # Generate raw function code and let Black handle all formatting
            stmt_sources = []
            if parsed_stmts:
                for stmt in parsed_stmts:
                    try:
                        stmt_source = ast.unparse(stmt)
                        stmt_sources.append(stmt_source)
                    except Exception as e:
                        stmt_sources.append(f"# Failed to unparse: {e}")
            
            # Create complete valid Python function - Black needs proper structure
            if stmt_sources:
                # Join statements with newlines and let Black handle indentation
                body_code = '\n'.join(stmt_sources)
                # Add minimal indentation so it's valid Python for Black
                indented_body = '\n'.join(f"    {line}" if line.strip() else "" for line in body_code.split('\n'))
                raw_func_code = f"def {func_name}({', '.join(args)}):\n{indented_body}"
            else:
                raw_func_code = f"def {func_name}({', '.join(args)}):\n    pass"
            
            # Use Black to format the function properly
            try:
                import black
                formatted_func = black.format_str(raw_func_code, mode=black.FileMode(
                    line_length=88,
                    string_normalization=False,  # Keep original quotes
                    is_pyi=False
                ))
                return formatted_func.strip()
            except ImportError:
                # Black not available, return with basic formatting
                return raw_func_code
            except Exception as e:
                self.logger.warning(f"Black formatting failed: {e}, using basic formatting")
                # Return the raw function code with basic formatting
                return raw_func_code
                
        except Exception as e:
            self.logger.error(f"Failed to parse function body: {e}")
            return f"def {func_name}({', '.join(args)}):\n    # Translation failed\n    pass"
    
    def _reconstruct_main_block(self, main_block: str, pools: Dict) -> List[str]:
        """Reconstruct main execution block."""
        lines = ['if __name__ == "__main__":']
        
        # Parse the main block content
        # Handle statements separated by semicolons or newlines
        statements = self._parse_main_statements(main_block)
        
        for stmt in statements:
            if not stmt.strip():
                continue
            
            # Resolve pool references
            resolved = self._resolve_pools_in_statement(stmt, pools)
            
            # Check if it's a for loop (uses 'in' keyword)
            if ' in ' in resolved and ':' in resolved and not resolved.strip().startswith('for'):
                # This is a for loop pattern
                lines.extend(self._format_for_loop(resolved))
            else:
                # Regular statement
                lines.append(f"    {resolved}")
        
        return lines
    
    def _parse_main_statements(self, main_block: str) -> List[str]:
        """Parse main block into individual statements."""
        statements = []
        
        # Split by semicolons but preserve those in strings
        current = []
        in_string = False
        string_char = None
        
        for char in main_block:
            if char in '"\'':
                if not in_string:
                    in_string = True
                    string_char = char
                elif char == string_char:
                    in_string = False
                    string_char = None
            elif char == ';' and not in_string:
                stmt = ''.join(current).strip()
                if stmt:
                    statements.append(stmt)
                current = []
                continue
            
            current.append(char)
        
        # Add remaining
        if current:
            stmt = ''.join(current).strip()
            if stmt:
                statements.append(stmt)
        
        return statements
    
    def _format_for_loop(self, stmt: str) -> List[str]:
        """Format a for loop statement."""
        # Pattern: var in iterable:body
        match = re.match(r'(\w+)\s+in\s+([^:]+):(.+)', stmt)
        if match:
            var = match.group(1)
            iterable = match.group(2).strip()
            body = match.group(3).strip()
            return [
                f"    for {var} in {iterable}:",
                f"        {body}"
            ]
        return [f"    {stmt}"]
    
    def _resolve_pools_in_statement(self, stmt: str, pools: Dict[str, str]) -> str:
        """Resolve pool references in a statement with intelligent fallback mappings."""
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
        
        # Merge with provided pools (provided pools take precedence)
        resolved_pools = {**pool_fallback_mapping}
        if pools:
            resolved_pools.update(pools)
        
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
        return replace_pools_outside_strings(stmt)