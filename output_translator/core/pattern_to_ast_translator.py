"""
Pattern to AST Translation Module

This module contains the PatternToASTTranslator class responsible for converting
CAI pattern matches into Python AST nodes. This is a focused, single-responsibility
module extracted from the main translator for better maintainability and testing.
"""

import ast
import re
import traceback
from typing import Dict, List, Any, Union, Optional, Set, TYPE_CHECKING

try:
    import black
    BLACK_AVAILABLE = True
except ImportError:
    BLACK_AVAILABLE = False

if TYPE_CHECKING:
    from .translator import PatternType, PatternMatch, TranslationContext
else:
    # Runtime imports to avoid circular dependency
    PatternType = None
    PatternMatch = None  
    TranslationContext = None

try:
    from utils.logger import MinifierLogger
except ImportError:
    # Fallback logger
    class MinifierLogger:
        def error(self, msg): print(f"ERROR: {msg}")
        def warning(self, msg): print(f"WARNING: {msg}")
        def info(self, msg): print(f"INFO: {msg}")
        def debug(self, msg): print(f"DEBUG: {msg}")


class PatternToASTTranslator:
    """
    Dedicated class for translating CAI patterns to Python AST nodes.
    
    This class takes PatternMatch objects and TranslationContext,
    returning one or more ast.AST nodes for each pattern.
    """
    
    def __init__(self, logger: Optional[MinifierLogger] = None, translator_instance=None):
        self.logger = logger or MinifierLogger()
        # Keep a reference to the main translator for helper methods
        self.translator = translator_instance
        
        # Import the shared types at runtime
        self._import_types()
    
    def _import_types(self):
        """Import shared types from main translator to avoid circular imports."""
        global PatternType, PatternMatch, TranslationContext
        if PatternType is None:
            from .translator import PatternType as PT, PatternMatch as PM, TranslationContext as TC
            # Update the global references
            PatternType = PT
            PatternMatch = PM
            TranslationContext = TC
            # Store the actual classes
            self.PatternType = PT
            self.PatternMatch = PM
            self.TranslationContext = TC
        else:
            self.PatternType = PatternType
            self.PatternMatch = PatternMatch
            self.TranslationContext = TranslationContext
    
    def translate(self, pattern, context) -> Union[ast.AST, List[ast.AST], None]:
        """
        Main entry point: translate a single pattern to AST node(s).
        
        Args:
            pattern: The pattern match to translate
            context: Translation context with state tracking
            
        Returns:
            Single AST node, list of AST nodes, or None if pattern cannot be translated
        """
        # Try to import PatternType, but handle missing translator gracefully
        try:
            from .translator import PatternType
        except ImportError:
            # Use the pattern_type from the pattern object directly
            PatternType = type(pattern.pattern_type)
        
        try:
            # Dispatch to appropriate build method based on pattern type
            if pattern.pattern_type.value == "function" or str(pattern.pattern_type) == "PatternType.FUNCTION":
                return self._build_function_def(pattern.parsed_data, context)
            elif pattern.pattern_type.value == "function_compressed" or str(pattern.pattern_type) == "PatternType.FUNCTION_COMPRESSED":
                return self._build_function_def(pattern.parsed_data, context)  # Same handler
            elif pattern.pattern_type.value == "class" or str(pattern.pattern_type) == "PatternType.CLASS":
                return self._build_class_def(pattern.parsed_data, context)
            elif pattern.pattern_type.value == "class_compressed" or str(pattern.pattern_type) == "PatternType.CLASS_COMPRESSED":
                return self._build_class_def(pattern.parsed_data, context)  # Same handler
            elif pattern.pattern_type.value == "method" or str(pattern.pattern_type) == "PatternType.METHOD":
                return self._build_method_def(pattern.parsed_data, context)
            elif pattern.pattern_type.value == "method_compressed" or str(pattern.pattern_type) == "PatternType.METHOD_COMPRESSED":
                return self._build_method_def(pattern.parsed_data, context)  # Same handler
            elif pattern.pattern_type.value == "import_from" or str(pattern.pattern_type) == "PatternType.IMPORT_FROM":
                return self._build_import_stmt(pattern.parsed_data, context)  # Same handler
            elif pattern.pattern_type.value == "nested_method" or str(pattern.pattern_type) == "PatternType.NESTED_METHOD":
                return self._build_nested_method_def(pattern.parsed_data, context)
            elif pattern.pattern_type.value == "concept_class" or str(pattern.pattern_type) == "PatternType.CONCEPT_CLASS":
                return self._build_concept_class_def(pattern.parsed_data, context)
            elif pattern.pattern_type.value == "concept_function" or str(pattern.pattern_type) == "PatternType.CONCEPT_FUNCTION":
                return self._build_concept_function_def(pattern.parsed_data, context)
            elif pattern.pattern_type.value == "symbol_class" or str(pattern.pattern_type) == "PatternType.SYMBOL_CLASS":
                return self._build_symbol_class_def(pattern.parsed_data, context)
            elif pattern.pattern_type.value == "variable" or str(pattern.pattern_type) == "PatternType.VARIABLE":
                return self._build_variable_assign(pattern.parsed_data, context)
            elif pattern.pattern_type.value == "import" or str(pattern.pattern_type) == "PatternType.IMPORT":
                return self._build_import_stmt(pattern.parsed_data, context)
            elif pattern.pattern_type.value == "decorator" or str(pattern.pattern_type) == "PatternType.DECORATOR":
                return self._build_decorator(pattern.parsed_data, context)
            elif pattern.pattern_type.value == "loop" or str(pattern.pattern_type) == "PatternType.LOOP":
                return self._build_loop(pattern.parsed_data, context)
            elif pattern.pattern_type.value == "conditional" or str(pattern.pattern_type) == "PatternType.CONDITIONAL":
                return self._build_conditional(pattern.parsed_data, context)
            elif pattern.pattern_type.value == "exception" or str(pattern.pattern_type) == "PatternType.EXCEPTION":
                return self._build_exception_handler(pattern.parsed_data, context)
            elif pattern.pattern_type.value == "js_try_catch" or str(pattern.pattern_type) == "PatternType.JS_TRY_CATCH":
                return self._build_js_try_catch(pattern.parsed_data, context)
            elif pattern.pattern_type.value == "context_manager" or str(pattern.pattern_type) == "PatternType.CONTEXT_MANAGER":
                return self._build_with_stmt(pattern.parsed_data, context)
            elif pattern.pattern_type.value == "yield" or str(pattern.pattern_type) == "PatternType.YIELD":
                return self._build_yield_expr(pattern.parsed_data, context)
            elif pattern.pattern_type.value == "async" or str(pattern.pattern_type) == "PatternType.ASYNC":
                return self._build_async_def(pattern.parsed_data, context)
            elif pattern.pattern_type.value == "lambda" or str(pattern.pattern_type) == "PatternType.LAMBDA":
                return self._build_lambda_expr(pattern.parsed_data, context)
            elif pattern.pattern_type.value == "comprehension" or str(pattern.pattern_type) == "PatternType.COMPREHENSION":
                return self._build_comprehension(pattern.parsed_data, context)
            else:
                # Fallback for unrecognized patterns - wrap in comment
                return ast.Expr(ast.Constant(f"# TODO: {pattern.raw_match}"))
                
        except Exception as e:
            self.logger.error(f"Failed to convert pattern {pattern.pattern_type} to AST: {e}")
            # Add more detailed error information for debugging
            self.logger.error(f"Exception details: {traceback.format_exc()}")
            # Return a comment node instead of None to keep the AST valid
            return ast.Expr(ast.Constant(f"# ERROR: Failed to translate {pattern.pattern_type}: {pattern.raw_match}"))
    
    # ============= AST BUILDER METHODS =============
    # These methods convert pattern data into Python AST nodes
    
    def _build_function_def(self, data: Dict[str, Any], context) -> ast.FunctionDef:
        """Build AST FunctionDef node from function pattern data."""
        name = self._expand_name(data.get('name', 'unnamed_function'))
        args_str = data.get('args', '') or ''  # Handle None values
        body_str = data.get('body', '') or 'pass'  # Handle None values
        
        # Parse arguments
        args = self._build_function_args(args_str)
        
        # Parse body statements using our improved method
        body_stmts = self._build_body_statements(body_str, context)
        
        return ast.FunctionDef(
            name=name,
            args=args,
            body=body_stmts,
            decorator_list=[],
            returns=None,
            lineno=1,
            col_offset=0
        )
    
    def _build_class_def(self, data: Dict[str, Any], context) -> ast.ClassDef:
        """Build AST ClassDef node with proper nested method handling."""
        name = self._expand_name(data.get('name', 'UnnamedClass'))
        bases_str = data.get('bases', '')
        body_str = data.get('body', 'pass')
        
        self.logger.info(f"Building class definition: {name} with body length: {len(body_str)}")
        
        # Parse base classes
        bases = self._build_base_classes(bases_str)
        
        # Parse class body with method detection
        body_stmts = self._build_class_body_statements(body_str, context)
        
        context.current_class = name
        
        return ast.ClassDef(
            name=name,
            bases=bases,
            keywords=[],
            body=body_stmts,
            decorator_list=[],
            lineno=1,
            col_offset=0
        )
    
    def _build_class_body_statements(self, body_str: str, context) -> List[ast.stmt]:
        """Build class body with proper method detection."""
        if not body_str.strip():
            return [ast.Pass(lineno=1, col_offset=0)]
        
        self.logger.info(f"Building class body statements from: {body_str[:100]}...")
        
        statements = []
        
        # Detect and parse methods using a more robust approach
        # Split by method definitions and process each section
        method_pattern = re.compile(r'def\s+(\w+)\s*\((.*?)\)\s*:', re.MULTILINE)
        
        method_matches = list(method_pattern.finditer(body_str))
        
        if not method_matches:
            # No methods found, try to parse the entire body as regular statements
            try:
                self.logger.debug("No methods found, parsing as regular statements")
                parsed_stmts = ast.parse(body_str).body
                statements.extend(parsed_stmts)
            except Exception as e:
                self.logger.warning(f"Failed to parse body as regular statements: {e}")
                # Preserve as comment
                comment_node = ast.Expr(
                    value=ast.Constant(value=f"# Class body content: {body_str}"),
                    lineno=1,
                    col_offset=0
                )
                statements.append(comment_node)
        else:
            # Process each method and the content between them
            last_end = 0
            for i, match in enumerate(method_matches):
                # Add any statements before this method
                pre_method = body_str[last_end:match.start()].strip()
                if pre_method:
                    try:
                        self.logger.debug(f"Parsing pre-method content: {pre_method[:50]}...")
                        pre_stmts = ast.parse(pre_method).body
                        statements.extend(pre_stmts)
                        self.logger.debug(f"Successfully parsed {len(pre_stmts)} pre-method statements")
                    except Exception as e:
                        self.logger.warning(f"Failed to parse pre-method content, preserving as comment: {e}")
                        # Preserve as comment
                        comment_node = ast.Expr(
                            value=ast.Constant(value=f"# Pre-method content: {pre_method}"),
                            lineno=1,
                            col_offset=0
                        )
                        statements.append(comment_node)
                
                # Extract method body by finding the next method or end of string
                method_start = match.end()
                if i + 1 < len(method_matches):
                    # There's another method after this one
                    method_end = method_matches[i + 1].start()
                else:
                    # This is the last method
                    method_end = len(body_str)
                
                method_body = body_str[method_start:method_end].strip()
                
                # Build the method
                method_data = {
                    'name': match.group(1),
                    'args': match.group(2),  
                    'body': method_body
                }
                self.logger.debug(f"Building method: {method_data['name']} with body: {method_body[:50]}...")
                method_ast = self._build_nested_method_def(method_data, context)
                statements.append(method_ast)
                
                last_end = method_end
            
            # Add any remaining statements after all methods (only if we processed methods)
            remaining = body_str[last_end:].strip()
            if remaining:
                try:
                    self.logger.debug(f"Parsing remaining content: {remaining[:50]}...")
                    remaining_stmts = ast.parse(remaining).body
                    statements.extend(remaining_stmts)
                    self.logger.debug(f"Successfully parsed {len(remaining_stmts)} remaining statements")
                except Exception as e:
                    self.logger.warning(f"Failed to parse remaining content, preserving as comment: {e}")
                    # Preserve as comment
                    comment_node = ast.Expr(
                        value=ast.Constant(value=f"# Remaining content: {remaining}"),
                        lineno=1,
                        col_offset=0
                    )
                    statements.append(comment_node)
        
        # If no statements were parsed, return a pass statement
        result = statements if statements else [ast.Pass(lineno=1, col_offset=0)]
        self.logger.info(f"Built class body with {len(result)} statements")
        return result
    
    def _build_concept_class_def(self, data: Dict[str, Any], context) -> ast.ClassDef:
        """Build AST ClassDef node from concept class pattern data."""
        name = self._expand_name(data.get('name', 'ConceptClass'))
        bases_str = data.get('bases', '')
        body_str = data.get('body', 'pass')
        
        # Parse base classes
        bases = self._build_base_classes(bases_str)
        
        # Parse body statements with concept-specific handling
        try:
            # FIXED: Bypass the main translator's indentation-corrupting expansion
            # Instead, directly process the body using our indentation-safe method
            self.logger.info(f"Processing concept class body: {body_str[:100]}...")
            
            # Clean and process the body string directly without indentation corruption
            clean_body = self._clean_body_for_parsing(body_str)
            body_stmts = self._build_body_statements(clean_body, context)
            
            # If we still have the translator and it has concept expansion, 
            # try it but strip indentation before parsing
            if (self.translator and hasattr(self.translator, '_expand_concept_body_sync') 
                and len(body_stmts) == 1 and isinstance(body_stmts[0], ast.Pass)):
                try:
                    expanded_code = self.translator._expand_concept_body_sync(body_str, context, base_indent=0)
                    # CRITICAL FIX: Strip indentation that corrupts parsing
                    clean_expanded = self._strip_corrupting_indentation(expanded_code)
                    formatted_code = self.format_and_validate_code(clean_expanded)
                    body_ast = ast.parse(formatted_code)
                    if body_ast.body:
                        body_stmts = body_ast.body
                        self.logger.info(f"Successfully used expanded concept body with {len(body_stmts)} statements")
                except Exception as expansion_error:
                    self.logger.warning(f"Concept expansion failed, using direct parsing: {expansion_error}")
                    # Keep the direct parsing result
                    pass
                    
        except Exception as e:
            self.logger.error(f"Error in concept class body processing: {e}")
            # Fallback to basic body statements
            body_stmts = self._build_body_statements(body_str, context)
        
        context.current_class = name
        
        return ast.ClassDef(
            name=name,
            bases=bases,
            keywords=[],
            body=body_stmts,
            decorator_list=[],
            lineno=1,
            col_offset=0
        )
    
    def _build_concept_function_def(self, data: Dict[str, Any], context) -> ast.FunctionDef:
        """Build AST FunctionDef node from concept function pattern data."""
        name = self._expand_name(data.get('name', 'concept_function'))
        args_str = data.get('args', '')
        body_str = data.get('body', 'pass')
        
        # Parse arguments
        args = self._build_function_args(args_str)
        
        # Parse body statements - concept functions use similar expansion to regular functions
        body_stmts = self._build_body_statements(body_str, context)
        
        return ast.FunctionDef(
            name=name,
            args=args,
            body=body_stmts,
            decorator_list=[],
            returns=None,
            lineno=1,
            col_offset=0
        )
    
    def _build_method_def(self, data: Dict[str, Any], context) -> ast.FunctionDef:
        """Build AST FunctionDef node from method pattern data."""
        name = self._expand_name(data.get('name', 'method'))
        args_str = data.get('args', '')
        body_str = data.get('body', 'pass')
        
        # Parse arguments - ensure 'self' is first parameter for methods
        args = self._build_function_args(args_str)
        
        # Add 'self' parameter if not already present
        if not args.args or args.args[0].arg != 'self':
            self_arg = ast.arg(arg='self', annotation=None, lineno=1, col_offset=0)
            args.args.insert(0, self_arg)
        
        # Parse body statements
        body_stmts = self._build_body_statements(body_str, context)
        
        return ast.FunctionDef(
            name=name,
            args=args,
            body=body_stmts,
            decorator_list=[],
            returns=None,
            lineno=1,
            col_offset=0
        )
    
    def _build_nested_method_def(self, data: Dict[str, Any], context) -> ast.FunctionDef:
        """Build method definitions that are nested within class bodies."""
        name = data.get('name', 'method')
        args_str = data.get('args', '')
        body_str = data.get('body', 'pass')
        
        self.logger.info(f"Building nested method: {name} with body length: {len(body_str)}")
        
        # Parse arguments with proper self handling
        args = self._build_function_args(args_str)
        if not any(arg.arg == 'self' for arg in args.args):
            self_arg = ast.arg(arg='self', annotation=None, lineno=1, col_offset=0)
            args.args.insert(0, self_arg)
        
        # Parse body as complete block using our improved method
        body_stmts = self._build_method_body_statements(body_str, context)
        
        return ast.FunctionDef(
            name=name,
            args=args, 
            body=body_stmts,
            decorator_list=[],
            returns=None,
            lineno=1,
            col_offset=0
        )

    def _build_method_body_statements(self, body_str: str, context) -> List[ast.stmt]:
        """Build method body with proper indentation and context."""
        if not body_str.strip():
            return [ast.Pass(lineno=1, col_offset=0)]
        
        self.logger.info(f"Processing method body: {repr(body_str[:100])}")
        
        # Method bodies need special handling for self references
        processed_body = self._process_method_body(body_str)
        
        # PRIORITY 1: Try direct parsing of the processed body
        try:
            parsed_ast = ast.parse(processed_body)
            if parsed_ast.body:
                self.logger.info(f"Successfully parsed method body with {len(parsed_ast.body)} statements")
                return parsed_ast.body
        except SyntaxError as e:
            self.logger.debug(f"Direct parsing failed: {e}")
            
        # PRIORITY 2: Try using the main translator's body processing if available
        if self.translator and hasattr(self.translator, '_build_body_statements'):
            try:
                body_stmts = self.translator._build_body_statements(processed_body, context)
                if body_stmts and not (len(body_stmts) == 1 and isinstance(body_stmts[0], ast.Pass)):
                    self.logger.info(f"Used translator _build_body_statements with {len(body_stmts)} statements")
                    return body_stmts
            except Exception as e:
                self.logger.debug(f"Translator _build_body_statements failed: {e}")
        
        # PRIORITY 3: Try wrapped parsing with proper indentation
        try:
            # Clean the body and ensure proper indentation
            clean_body = self._clean_body_for_parsing(processed_body)
            indented_body = self._indent_code(clean_body, 1)
            wrapped = f"def _temp_method(self):\n{indented_body}"
            
            self.logger.debug(f"Trying wrapped parsing: {wrapped[:200]}...")
            module = ast.parse(wrapped)
            
            if module.body and isinstance(module.body[0], ast.FunctionDef):
                extracted_body = module.body[0].body
                if extracted_body:
                    self.logger.info(f"Successfully used wrapped parsing with {len(extracted_body)} statements")
                    return extracted_body
                    
        except Exception as e:
            self.logger.debug(f"Wrapped parsing failed: {e}")
        
        # PRIORITY 4: Try statement-by-statement parsing
        try:
            statements = self._parse_statements_individually(processed_body)
            if statements:
                self.logger.info(f"Used individual statement parsing with {len(statements)} statements")
                return statements
        except Exception as e:
            self.logger.debug(f"Individual statement parsing failed: {e}")
        
        # FINAL FALLBACK: Preserve content as comments and add pass
        self.logger.warning(f"All parsing methods failed for method body, preserving as comments")
        comment_lines = []
        for line in body_str.split('\n'):
            if line.strip():
                comment_lines.append(ast.Expr(ast.Constant(f"# Original: {line.strip()}")))
        
        # Add at least one executable statement
        comment_lines.append(ast.Pass(lineno=1, col_offset=0))
        return comment_lines if comment_lines else [ast.Pass(lineno=1, col_offset=0)]

    def _parse_statements_individually(self, body_str: str) -> List[ast.stmt]:
        """Parse method body by trying to parse individual statements with proper indentation."""
        if not body_str.strip():
            return [ast.Pass(lineno=1, col_offset=0)]
        
        self.logger.debug(f"Parsing statements individually from: {body_str[:200]}...")
        
        # First, let's try to fix the indentation issues
        fixed_body = self._fix_method_indentation(body_str)
        
        try:
            # Try parsing the fixed body as a whole first
            parsed = ast.parse(fixed_body)
            if parsed.body:
                self.logger.debug(f"Fixed indentation parsing succeeded with {len(parsed.body)} statements")
                return parsed.body
        except SyntaxError as e:
            self.logger.debug(f"Fixed indentation parsing failed: {e}")
        
        # If that fails, fall back to preserving content as comments with proper AST attributes
        statements = []
        lines = body_str.split('\n')
        line_num = 1
        
        for line in lines:
            if line.strip():
                # Convert each line to a comment to preserve the content
                comment_node = ast.Expr(
                    value=ast.Constant(value=f"# Method content: {line.strip()}"),
                    lineno=line_num,
                    col_offset=0
                )
                statements.append(comment_node)
                line_num += 1
        
        # Add at least one executable statement with proper attributes
        pass_node = ast.Pass(lineno=line_num, col_offset=0)
        statements.append(pass_node)
        return statements

    def _fix_method_indentation(self, body_str: str) -> str:
        """Fix indentation issues in method bodies using a more aggressive approach."""
        if not body_str.strip():
            return 'pass'
        
        lines = body_str.split('\n')
        fixed_lines = []
        
        # First pass: normalize all indentation and identify block structure
        current_indent = 0
        
        for line in lines:
            if not line.strip():
                fixed_lines.append('')
                continue
            
            stripped = line.strip()
            
            # Detect block starters that need indentation
            if stripped.endswith(':'):
                # This starts a new block
                fixed_lines.append('    ' * current_indent + stripped)
                current_indent += 1
            elif stripped in ['else:', 'elif', 'except:', 'finally:'] or stripped.startswith(('elif ', 'except ')):
                # These are at the same level as their matching statement
                if current_indent > 0:
                    current_indent -= 1
                fixed_lines.append('    ' * current_indent + stripped)
                current_indent += 1
            else:
                # Regular statement - check if we need to dedent
                if (stripped.startswith(('return ', 'break', 'continue', 'pass')) or
                    not any(prev_line.strip().endswith(':') for prev_line in fixed_lines[-3:] if prev_line.strip())):
                    # This might be at a dedented level
                    # Simple heuristic: if the last few lines don't end with :, we might need to dedent
                    pass
                
                fixed_lines.append('    ' * current_indent + stripped)
        
        result = '\n'.join(fixed_lines).strip()
        
        # Second pass: try to fix obvious indentation errors
        result = self._fix_obvious_indentation_errors(result)
        
        if not result:
            return 'pass'
        
        self.logger.debug(f"Fixed method indentation: {result[:200]}...")
        return result

    def _fix_obvious_indentation_errors(self, code: str) -> str:
        """Fix obvious indentation errors in Python code."""
        lines = code.split('\n')
        fixed_lines = []
        
        for i, line in enumerate(lines):
            if not line.strip():
                fixed_lines.append('')
                continue
            
            stripped = line.strip()
            
            # Special case: statements that should be indented after control structures
            if i > 0 and lines[i-1].strip().endswith(':'):
                # Previous line ended with :, this line should be indented
                if not line.startswith('    '):
                    fixed_lines.append('    ' + stripped)
                else:
                    fixed_lines.append(line)
            elif stripped.startswith(('else', 'elif', 'except', 'finally')):
                # These should align with their matching statement
                # For simplicity, put them at base level
                fixed_lines.append(stripped)
            else:
                fixed_lines.append(line)
        
        return '\n'.join(fixed_lines)

    def _process_method_body(self, body_str: str) -> str:
        """Process method body with self reference handling and robust indentation normalization."""
        body = body_str
        
        # Step 1: Normalize indentation to avoid parsing issues
        body = self._normalize_method_body_indentation(body)
        
        # Step 2: Convert 'this' to 'self'
        body = re.sub(r'\bthis\.', 'self.', body)
        
        # Step 3: Convert JavaScript method call syntax
        body = re.sub(r'\.(\w+)\(\)', r'.\1()', body)  # Clean up method calls
        
        # Step 4: Handle f-string patterns that might get corrupted
        body = self._preserve_f_strings(body)
        
        # Step 5: Ensure proper Python syntax
        body = self._convert_cai_to_python(body)
        
        return body

    def _normalize_method_body_indentation(self, body_str: str) -> str:
        """Normalize indentation in method bodies to prevent parsing issues."""
        if not body_str.strip():
            return 'pass'
        
        lines = body_str.split('\n')
        non_empty_lines = [line for line in lines if line.strip()]
        
        if not non_empty_lines:
            return 'pass'
        
        # Find minimum indentation from ALL non-empty lines (including unindented ones)
        min_indent = float('inf')
        for line in non_empty_lines:
            if line.strip():
                indent = len(line) - len(line.lstrip())
                min_indent = min(min_indent, indent)
        
        # If no lines found or all lines are unindented, no normalization needed
        if min_indent == float('inf') or min_indent == 0:
            # Just remove leading/trailing whitespace and semicolons
            normalized_lines = []
            for line in lines:
                if line.strip():
                    cleaned = line.strip().rstrip(';')
                    normalized_lines.append(cleaned)
                else:
                    normalized_lines.append('')
            result = '\n'.join(normalized_lines).strip()
            return result if result else 'pass'
        
        # Remove common indentation but preserve relative indentation
        normalized_lines = []
        for line in lines:
            if line.strip():
                if len(line) >= min_indent:
                    cleaned = line[min_indent:].rstrip(';')
                    normalized_lines.append(cleaned)
                else:
                    # Line has less indentation than minimum - preserve it but clean semicolons
                    cleaned = line.lstrip().rstrip(';')
                    normalized_lines.append(cleaned)
            else:
                normalized_lines.append('')  # Preserve empty lines
        
        result = '\n'.join(normalized_lines).strip()
        return result if result else 'pass'

    def _preserve_f_strings(self, body: str) -> str:
        """Preserve f-string formatting during method body processing."""
        # Find and temporarily replace f-strings to prevent corruption
        f_string_pattern = r'f["\']([^"\']*?)["\']'
        f_strings = {}
        counter = 0
        
        def replace_f_string(match):
            nonlocal counter
            placeholder = f"__F_STRING_{counter}__"
            f_strings[placeholder] = match.group(0)
            counter += 1
            return placeholder
        
        # Replace f-strings with placeholders
        body = re.sub(f_string_pattern, replace_f_string, body)
        
        # Process the body normally
        # (This will be done by the calling function)
        
        # Note: We'll restore f-strings after other processing
        # Store them in the body for restoration later
        if f_strings:
            # Add a marker so we can restore them later
            for placeholder, original in f_strings.items():
                body = body.replace(placeholder, original)
        
        return body
    
    def _build_js_try_catch(self, data: Dict[str, Any], context) -> ast.Try:
        """Build AST Try node from JavaScript-style try/catch pattern data."""
        # JavaScript try/catch/finally should be converted to Python try/except/finally
        full_js_block = data.get('body', 'try { pass } catch(e) { pass }')
        
        # Parse the JavaScript try/catch/finally block
        try_body_str = 'pass'
        catch_body_str = 'pass'
        finally_body_str = ''
        catch_name = 'e'
        catch_type = 'Exception'
        
        # Extract try block
        try_match = re.search(r'try\s*\{\s*(.*?)\s*\}', full_js_block, re.DOTALL)
        if try_match:
            try_body_str = try_match.group(1).strip() or 'pass'
        
        # Extract catch block
        catch_match = re.search(r'catch\s*\(\s*(\w*)\s*\)\s*\{\s*(.*?)\s*\}', full_js_block, re.DOTALL)
        if catch_match:
            catch_name = catch_match.group(1) or 'e'
            catch_body_str = catch_match.group(2).strip() or 'pass'
        else:
            # Try catch without parentheses
            catch_match = re.search(r'catch\s*\{\s*(.*?)\s*\}', full_js_block, re.DOTALL)
            if catch_match:
                catch_body_str = catch_match.group(1).strip() or 'pass'
        
        # Extract finally block
        finally_match = re.search(r'finally\s*\{\s*(.*?)\s*\}', full_js_block, re.DOTALL)
        if finally_match:
            finally_body_str = finally_match.group(1).strip()
        
        # Parse try body
        try_body = self._build_body_statements(try_body_str, context)
        
        # Parse catch/except handler
        except_type_node = None  # Default to catch all exceptions
        except_body = self._build_body_statements(catch_body_str, context)
        
        # Convert JavaScript console.log to Python print
        if 'console.log' in catch_body_str:
            catch_body_str = catch_body_str.replace('console.log', 'print')
            except_body = self._build_body_statements(catch_body_str, context)
        
        handler = ast.ExceptHandler(
            type=except_type_node,  # None means catch all exceptions
            name=catch_name if catch_name else None,  # Exception variable name
            body=except_body,
            lineno=1,
            col_offset=0
        )
        
        # Parse finally body (optional)
        finally_body = []
        if finally_body_str:
            finally_body = self._build_body_statements(finally_body_str, context)
        
        return ast.Try(
            body=try_body,
            handlers=[handler],
            orelse=[],
            finalbody=finally_body,
            lineno=1,
            col_offset=0
        )
    
    def _build_symbol_class_def(self, data: Dict[str, Any], context) -> ast.ClassDef:
        """Build AST ClassDef node from symbol class pattern data."""
        name = self._expand_name(data.get('name', 'SymbolClass'))
        bases_str = data.get('bases', '')
        body_str = data.get('body', 'pass')
        
        # Parse base classes
        bases = self._build_base_classes(bases_str)
        
        # Parse body statements with symbol-specific handling
        body_stmts = self._build_symbol_body_statements(body_str, context)
        
        context.current_class = name
        
        return ast.ClassDef(
            name=name,
            bases=bases,
            keywords=[],
            body=body_stmts,
            decorator_list=[],
            lineno=1,
            col_offset=0
        )
    
    def _build_variable_assign(self, data: Dict[str, Any], context) -> ast.Assign:
        """Build AST Assign node from variable pattern data."""
        name = self._expand_name(data.get('name', 'var'))
        value_str = data.get('value', 'None')
        
        target = ast.Name(id=name, ctx=ast.Store())
        
        try:
            # Parse the value expression
            value_ast = ast.parse(value_str, mode='eval')
            value = value_ast.body
        except:
            # Fallback to string constant
            value = ast.Constant(value=value_str)
        
        context.variables[name] = value_str
        
        return ast.Assign(targets=[target], value=value, lineno=1, col_offset=0)
    
    def _build_import_stmt(self, data: Dict[str, Any], context) -> Union[ast.Import, ast.ImportFrom]:
        """Build AST Import or ImportFrom node from import pattern data."""
        stmt = data.get('statement', '')
        
        # Distinguish between 'import module' and 'from module import name'
        if stmt.startswith('from '):
            # Parse 'from module import name'
            match = re.match(r'from\s+(\S+)\s+import\s+(.+)', stmt)
            if match:
                module_name = match.group(1)
                import_names = [n.strip() for n in match.group(2).split(',')]
                aliases = [ast.alias(name=name, asname=None) for name in import_names]
                context.imports.add(stmt)
                return ast.ImportFrom(module=module_name, names=aliases, level=0, lineno=1, col_offset=0)
        
        # Parse 'import module'
        if stmt.startswith('import '):
            module_name = stmt[7:].strip()  # Remove 'import '
            alias = ast.alias(name=module_name, asname=None)
            context.imports.add(stmt)
            return ast.Import(names=[alias], lineno=1, col_offset=0)
        
        # Fallback - treat as regular import
        alias = ast.alias(name=stmt, asname=None)
        return ast.Import(names=[alias], lineno=1, col_offset=0)
    
    def _build_decorator(self, data: Dict[str, Any], context) -> ast.FunctionDef:
        """Build AST node for decorator pattern."""
        # Decorators are typically attached to functions, so we return a decorated function
        decorator_name = data.get('name', 'decorator')
        target_func = data.get('target', 'decorated_function')
        
        # Create decorator
        decorator = ast.Name(id=decorator_name, ctx=ast.Load())
        
        # Create simple function to be decorated
        args = ast.arguments(
            posonlyargs=[], args=[], vararg=None, kwonlyargs=[],
            kw_defaults=[], kwarg=None, defaults=[]
        )
        
        return ast.FunctionDef(
            name=target_func,
            args=args,
            body=[ast.Pass()],
            decorator_list=[decorator],
            returns=None,
            lineno=1,
            col_offset=0
        )
    
    def _build_loop(self, data: Dict[str, Any], context) -> Union[ast.For, ast.While]:
        """Build AST node for loop pattern."""
        loop_type = data.get('type', 'for')
        
        if loop_type == 'while':
            condition_str = data.get('condition', 'True')
            body_str = data.get('body', 'pass')
            
            # Parse condition
            try:
                condition_ast = ast.parse(condition_str, mode='eval')
                condition = condition_ast.body
            except:
                condition = ast.Constant(value=True)
            
            # Parse body
            body_stmts = self._build_body_statements(body_str, context)
            
            return ast.While(test=condition, body=body_stmts, orelse=[], lineno=1, col_offset=0)
        else:
            # For loop
            target_str = data.get('target', 'item')
            iter_str = data.get('iter', 'range(10)')
            body_str = data.get('body', 'pass')
            
            # Parse target
            target = ast.Name(id=target_str, ctx=ast.Store())
            
            # Parse iterator
            try:
                iter_ast = ast.parse(iter_str, mode='eval')
                iter_expr = iter_ast.body
            except:
                iter_expr = ast.Name(id='range(10)', ctx=ast.Load())
            
            # Parse body
            body_stmts = self._build_body_statements(body_str, context)
            
            return ast.For(target=target, iter=iter_expr, body=body_stmts, orelse=[], lineno=1, col_offset=0)
    
    def _build_conditional(self, data: Dict[str, Any], context) -> ast.If:
        """Build AST node for conditional pattern."""
        condition_str = data.get('condition', 'True')
        then_body_str = data.get('then_body', 'pass')
        else_body_str = data.get('else_body', '')
        
        # Parse condition
        try:
            condition_ast = ast.parse(condition_str, mode='eval')
            condition = condition_ast.body
        except:
            condition = ast.Constant(value=True)
        
        # Parse then body
        then_body = self._build_body_statements(then_body_str, context)
        
        # Parse else body (optional)
        else_body = []
        if else_body_str:
            else_body = self._build_body_statements(else_body_str, context)
        
        return ast.If(test=condition, body=then_body, orelse=else_body, lineno=1, col_offset=0)
    
    def _build_exception_handler(self, data: Dict[str, Any], context) -> ast.Try:
        """Build AST node for exception handling pattern."""
        try_body_str = data.get('try_body', 'pass')
        except_type = data.get('except_type', 'Exception')
        except_name = data.get('except_name', 'e')
        except_body_str = data.get('except_body', 'pass')
        finally_body_str = data.get('finally_body', '')
        
        # Parse try body
        try_body = self._build_body_statements(try_body_str, context)
        
        # Parse except handler
        except_type_node = ast.Name(id=except_type, ctx=ast.Load()) if except_type != 'Exception' else None
        except_name_node = except_name if except_name else None
        except_body = self._build_body_statements(except_body_str, context)
        
        handler = ast.ExceptHandler(
            type=except_type_node,
            name=except_name_node,
            body=except_body,
            lineno=1,
            col_offset=0
        )
        
        # Parse finally body (optional)
        finally_body = []
        if finally_body_str:
            finally_body = self._build_body_statements(finally_body_str, context)
        
        return ast.Try(
            body=try_body,
            handlers=[handler],
            orelse=[],
            finalbody=finally_body,
            lineno=1,
            col_offset=0
        )
    
    def _build_with_stmt(self, data: Dict[str, Any], context) -> ast.With:
        """Build AST node for context manager pattern."""
        context_expr_str = data.get('context_expr', 'open("file.txt")')
        var_name = data.get('var_name', 'f')
        body_str = data.get('body', 'pass')
        
        # Parse context expression
        try:
            context_expr_ast = ast.parse(context_expr_str, mode='eval')
            context_expr = context_expr_ast.body
        except:
            context_expr = ast.Constant(value=context_expr_str)
        
        # Create with item
        with_item = ast.withitem(
            context_expr=context_expr,
            optional_vars=ast.Name(id=var_name, ctx=ast.Store()) if var_name else None
        )
        
        # Parse body
        body_stmts = self._build_body_statements(body_str, context)
        
        return ast.With(items=[with_item], body=body_stmts, lineno=1, col_offset=0)
    
    def _build_yield_expr(self, data: Dict[str, Any], context) -> ast.Expr:
        """Build AST node for yield expression pattern."""
        value_str = data.get('value', 'None')
        
        # Parse yield value
        try:
            value_ast = ast.parse(value_str, mode='eval')
            value = value_ast.body
        except:
            value = ast.Constant(value=None)
        
        yield_expr = ast.Yield(value=value, lineno=1, col_offset=0)
        return ast.Expr(value=yield_expr, lineno=1, col_offset=0)
    
    def _build_async_def(self, data: Dict[str, Any], context) -> ast.AsyncFunctionDef:
        """Build AST node for async function pattern."""
        name = self._expand_name(data.get('name', 'async_function'))
        args_str = data.get('args', '')
        body_str = data.get('body', 'pass')
        
        # Parse arguments
        args = self._build_function_args(args_str)
        
        # Parse body statements
        body_stmts = self._build_body_statements(body_str, context)
        
        return ast.AsyncFunctionDef(
            name=name,
            args=args,
            body=body_stmts,
            decorator_list=[],
            returns=None,
            lineno=1,
            col_offset=0
        )
    
    def _build_lambda_expr(self, data: Dict[str, Any], context) -> ast.Expr:
        """Build AST node for lambda expression pattern."""
        args_str = data.get('args', '')
        body_str = data.get('body', 'None')
        
        # Parse arguments
        args = self._build_function_args(args_str)
        
        # Parse body expression
        try:
            body_ast = ast.parse(body_str, mode='eval')
            body_expr = body_ast.body
        except:
            body_expr = ast.Constant(value=None)
        
        lambda_expr = ast.Lambda(args=args, body=body_expr, lineno=1, col_offset=0)
        return ast.Expr(value=lambda_expr, lineno=1, col_offset=0)
    
    def _build_comprehension(self, data: Dict[str, Any], context) -> ast.Expr:
        """Build AST node for comprehension pattern."""
        comp_type = data.get('type', 'list')  # list, dict, set, generator
        expr_str = data.get('expr', 'item')
        target_str = data.get('target', 'item')
        iter_str = data.get('iter', 'iterable')
        condition_str = data.get('condition', '')
        
        # Parse expression
        try:
            expr_ast = ast.parse(expr_str, mode='eval')
            expr = expr_ast.body
        except:
            expr = ast.Name(id='item', ctx=ast.Load())
        
        # Parse target
        target = ast.Name(id=target_str, ctx=ast.Store())
        
        # Parse iterator
        try:
            iter_ast = ast.parse(iter_str, mode='eval')
            iter_expr = iter_ast.body
        except:
            iter_expr = ast.Name(id='iterable', ctx=ast.Load())
        
        # Parse condition (optional)
        condition = None
        if condition_str:
            try:
                condition_ast = ast.parse(condition_str, mode='eval')
                condition = condition_ast.body
            except:
                pass
        
        # Create comprehension
        comprehension = ast.comprehension(target=target, iter=iter_expr, ifs=[condition] if condition else [], is_async=0)
        
        # Create appropriate comprehension type
        if comp_type == 'dict':
            # For dict comprehension, we need key and value
            key_str = data.get('key', 'key')
            try:
                key_ast = ast.parse(key_str, mode='eval')
                key = key_ast.body
            except:
                key = ast.Name(id='key', ctx=ast.Load())
            
            comp_expr = ast.DictComp(key=key, value=expr, generators=[comprehension], lineno=1, col_offset=0)
        elif comp_type == 'set':
            comp_expr = ast.SetComp(elt=expr, generators=[comprehension], lineno=1, col_offset=0)
        elif comp_type == 'generator':
            comp_expr = ast.GeneratorExp(elt=expr, generators=[comprehension], lineno=1, col_offset=0)
        else:  # list
            comp_expr = ast.ListComp(elt=expr, generators=[comprehension], lineno=1, col_offset=0)
        
        return ast.Expr(value=comp_expr, lineno=1, col_offset=0)
    
    
    # ============= BLACK FORMATTING & AST VALIDATION =============
    # Single-point formatting and validation methods
    
    def format_and_validate_code(self, code: str) -> str:
        """
        Apply Black formatting and AST validation in a single pass.
        
        Args:
            code: Raw Python code string
            
        Returns:
            Formatted and validated Python code
        """
        if not code or not code.strip():
            return "pass"
            
        # Step 1: Apply Black formatting if available
        formatted_code = self._apply_black_formatting(code)
        
        # Step 2: Validate AST and attempt single repair if needed
        validated_code = self._validate_and_repair_ast(formatted_code)
        
        return validated_code
    
    def _apply_black_formatting(self, code: str) -> str:
        """Apply Black formatting to code string."""
        if not BLACK_AVAILABLE:
            return code
            
        try:
            return black.format_str(code, mode=black.FileMode())
        except Exception as e:
            self.logger.warning(f"Black formatting failed: {e}")
            return code
    
    def _validate_and_repair_ast(self, code: str) -> str:
        """
        Validate AST and attempt single repair if parsing fails.
        
        Args:
            code: Python code string to validate
            
        Returns:
            Valid Python code (repaired if necessary)
        """
        # First attempt: try to parse as-is
        try:
            ast.parse(code)
            return code  # Success, no repair needed
        except SyntaxError as e:
            self.logger.warning(f"AST validation failed, attempting syntax repair: {e}")
            
            # Single repair attempt
            repaired_code = self._attempt_syntax_repair(code)
            
            # Verify repair worked
            try:
                ast.parse(repaired_code)
                self.logger.info("Syntax repair successful")
                return repaired_code
            except SyntaxError as e2:
                self.logger.error(f"Syntax repair failed: {e2}")
                # Return a safe fallback
                return "# ERROR: Failed to parse and repair code\npass"
    
    def _attempt_syntax_repair(self, code: str) -> str:
        """
        Single-pass syntax repair for common issues.
        
        Args:
            code: Code with syntax errors
            
        Returns:
            Repaired code string
        """
        lines = code.split('\n')
        repaired_lines = []
        
        for line in lines:
            if not line.strip():
                repaired_lines.append(line)
                continue
                
            repaired_line = line
            
            # Auto-insert missing colons for control structures
            if (re.match(r'^\s*(if|elif|else|for|while|def|class|try|except|finally|with)\b', repaired_line) and 
                not repaired_line.rstrip().endswith(':')):
                repaired_line = repaired_line.rstrip() + ':'
            
            # Remove stray braces (JavaScript artifacts)
            repaired_line = re.sub(r'\s*[{}]\s*', '', repaired_line)
            
            # Fix common indentation issues
            stripped = repaired_line.lstrip()
            if stripped:
                # Normalize indentation to multiples of 4 spaces
                indent_level = len(repaired_line) - len(stripped)
                normalized_indent = '    ' * (indent_level // 4)
                repaired_line = normalized_indent + stripped
            
            repaired_lines.append(repaired_line)
        
        return '\n'.join(repaired_lines)

    # ============= HELPER METHODS =============
    # These methods support the AST builders above
    
    def _expand_name(self, name: str) -> str:
        """Expand abbreviated names using the abbreviation map."""
        if self.translator and hasattr(self.translator, 'abbreviation_map'):
            return self.translator.abbreviation_map.get(name, name)
        # Fallback defaults
        abbreviation_map = {
            'fn': 'function', 'cls': 'class', 'var': 'variable',
            'init': '__init__', 'str': '__str__', 'repr': '__repr__'
        }
        return abbreviation_map.get(name, name)
    
    def _expand_js_body(self, body: str, base_indent: int = 0) -> str:
        """Expand JavaScript-style function body."""
        if self.translator and hasattr(self.translator, '_expand_js_body'):
            return self.translator._expand_js_body(body, base_indent)
        
        # Simple fallback - don't add extra indentation, just clean up the body
        if not body or not body.strip():
            return 'pass'
        
        # Clean up the body string - remove extra indentation and make it parseable
        lines = body.split('\n')
        cleaned_lines = []
        
        for line in lines:
            stripped = line.strip()
            if stripped:
                cleaned_lines.append(stripped)
        
        # Join lines and ensure it's valid Python
        result = '\n'.join(cleaned_lines)
        
        # If it's just a single expression, return it as-is
        if '\n' not in result:
            return result
        
        return result
    
    def _expand_js_body_clean(self, body: str, base_indent: int = 0) -> str:
        """Expand function body without corrupting f-strings and fix indentation."""
        if not body or not body.strip():
            return 'pass'
        
        # Split into lines and process each one
        lines = body.split('\n')
        processed_lines = []
        
        for line in lines:
            if line.strip():  # Non-empty line
                stripped = line.strip()
                # Convert JavaScript-style semicolons to Python
                if stripped.endswith(';'):
                    stripped = stripped.rstrip(';').rstrip()
                
                # Detect if this is a method definition or method body
                if stripped.startswith('def '):
                    # Method definition - no extra indentation needed
                    processed_lines.append(stripped)
                elif any(processed_lines) and processed_lines[-1].strip().startswith('def '):
                    # This is the first line after a method definition - indent it
                    processed_lines.append('    ' + stripped)
                elif any(processed_lines) and not stripped.startswith('def ') and processed_lines[-1].startswith('    '):
                    # This is a continuation of method body - keep same indentation
                    processed_lines.append('    ' + stripped)
                else:
                    # Regular line - use as is
                    processed_lines.append(stripped)
            else:
                # Keep empty lines
                processed_lines.append('')
        
        # Join with newlines
        result = '\n'.join(processed_lines).strip()
        
        # If result is empty, return pass
        if not result:
            return 'pass'
        
        return result
    
    def _clean_body_for_parsing_preserve_content(self, body_str: str) -> str:
        """Clean body string to prepare it for safe AST parsing while preserving all content."""
        if not body_str or not body_str.strip():
            return 'pass'
        
        # Don't strip content aggressively - preserve structure but make it parseable
        lines = body_str.split('\n')
        cleaned_lines = []
        
        for line in lines:
            # Only remove excessive leading whitespace, but preserve the content
            stripped = line.strip()
            if stripped:
                # Keep the line but normalize basic syntax issues
                # Remove trailing semicolons that break Python
                if stripped.endswith(';'):
                    stripped = stripped[:-1]
                
                # Fix obvious JavaScript-isms that prevent parsing
                stripped = stripped.replace('&&', ' and ')
                stripped = stripped.replace('||', ' or ')
                stripped = stripped.replace('true', 'True')
                stripped = stripped.replace('false', 'False')
                
                cleaned_lines.append(stripped)
        
        result = '\n'.join(cleaned_lines)
        if not result:
            return 'pass'
        
        self.logger.debug(f"Preserved body content: {result[:200]}...")
        return result
    
    def _convert_cai_to_python_preserve_content(self, body_str: str) -> str:
        """Convert CAI to Python while preserving all content - no aggressive changes."""
        code = body_str
        
        # Only apply essential conversions that are necessary for Python parsing
        
        # Phase 1: Essential boolean and operator conversions
        code = code.replace('console.log', 'print')
        code = code.replace('this.', 'self.')
        
        # Phase 2: Boolean conversions with word boundaries to avoid corrupting variable names
        code = re.sub(r'\btrue\b', 'True', code)
        code = re.sub(r'\bfalse\b', 'False', code)
        code = re.sub(r'\s*&&\s*', ' and ', code)
        code = re.sub(r'\s*\|\|\s*', ' or ', code)
        
        # Phase 3: Remove JavaScript variable declarations (conservative)
        code = re.sub(r'\b(var|let|const)\s+', '', code)
        
        # Phase 4: Handle control structures with braces - but only convert obvious ones
        if re.search(r'\b(if|for|while|try|catch|finally)\s*[({]', code):
            # Convert control structures with braces to Python syntax
            code = re.sub(r'\bif\s*\(\s*(.*?)\s*\)\s*\{', r'if \1:', code)
            code = re.sub(r'\bfor\s*\(\s*(.*?)\s*\)\s*\{', r'for \1:', code)
            code = re.sub(r'\bwhile\s*\(\s*(.*?)\s*\)\s*\{', r'while \1:', code)
            code = re.sub(r'\btry\s*\{', r'try:', code)
            code = re.sub(r'\bcatch\s*\(\s*(.*?)\s*\)\s*\{', r'except \1:', code)
            code = re.sub(r'\bcatch\s*\{', r'except:', code)
            code = re.sub(r'\bfinally\s*\{', r'finally:', code)
            
            # Remove orphaned braces
            code = re.sub(r'\s*\{\s*', '', code)
            code = re.sub(r'\s*\}\s*', '', code)
        
        # Phase 5: Handle semicolons carefully - only remove if they're statement terminators
        lines = code.split('\n')
        clean_lines = []
        for line in lines:
            if line.strip():
                # Remove trailing semicolons but preserve structure
                if line.rstrip().endswith(';'):
                    line = line.rstrip()[:-1].rstrip()
                clean_lines.append(line)
        
        result = '\n'.join(clean_lines)
        
        # Don't return empty result
        if not result.strip():
            return body_str  # Return original if conversion failed
        
        return result
    
    def _strip_corrupting_indentation(self, code: str) -> str:
        """Strip indentation patterns that corrupt AST parsing.
        
        The main translator's expansion methods add indentation that breaks
        our AST parsing. This method removes problematic indentation while
        preserving the code structure.
        """
        if not code or not code.strip():
            return 'pass'
        
        lines = code.split('\n')
        cleaned_lines = []
        min_indent = float('inf')
        
        # Find minimum indentation level (excluding empty lines)
        for line in lines:
            if line.strip():  # Non-empty line
                indent_level = len(line) - len(line.lstrip())
                min_indent = min(min_indent, indent_level)
        
        # If all lines are empty or no indentation found
        if min_indent == float('inf'):
            min_indent = 0
        
        # Remove the common indentation prefix
        for line in lines:
            if line.strip():  # Non-empty line
                if len(line) >= min_indent:
                    cleaned_lines.append(line[min_indent:])
                else:
                    cleaned_lines.append(line.lstrip())
            else:
                cleaned_lines.append('')  # Preserve empty lines
        
        result = '\n'.join(cleaned_lines).strip()
        if not result:
            return 'pass'
            
        self.logger.debug(f"Stripped indentation from {len(lines)} lines, min_indent={min_indent}")
        return result

    def _build_function_args(self, args_str: str) -> ast.arguments:
        """Build AST arguments from argument string."""
        if not args_str.strip():
            return ast.arguments(
                posonlyargs=[],
                args=[],
                vararg=None,
                kwonlyargs=[],
                kw_defaults=[],
                kwarg=None,
                defaults=[]
            )
        
        # Simple parsing - split by comma and create args
        arg_names = [arg.strip() for arg in args_str.split(',') if arg.strip()]
        args = [ast.arg(arg=name, annotation=None, lineno=1, col_offset=0) for name in arg_names]
        
        return ast.arguments(
            posonlyargs=[],
            args=args,
            vararg=None,
            kwonlyargs=[],
            kw_defaults=[],
            kwarg=None,
            defaults=[]
        )
    
    def _build_base_classes(self, bases_str: str) -> List[ast.expr]:
        """Build list of base class expressions from string."""
        if not bases_str or not bases_str.strip():
            return []
        
        bases = []
        base_names = [base.strip() for base in bases_str.split(',') if base.strip()]
        
        for base_name in base_names:
            try:
                # Try to parse as expression in case it's complex (e.g., module.Class)
                base_ast = ast.parse(base_name, mode='eval')
                bases.append(base_ast.body)
            except:
                # Fallback to simple name
                bases.append(ast.Name(id=base_name, ctx=ast.Load()))
        
        return bases
    
    def _build_body_statements(self, body_str: str, context) -> List[ast.stmt]:
        """Build AST statements with proper block structure detection - FIXED VERSION."""
        if not body_str or not body_str.strip() or body_str.strip() == 'pass':
            return [ast.Pass(lineno=1, col_offset=0)]
        
        self.logger.info(f"Building body statements from: {repr(body_str[:200])}")
        
        # CRITICAL FIX: Don't lose content - preserve everything we can
        
        # PRIORITY 1: Try direct Python parsing first (if it looks like Python already)
        try:
            # Quick test: if it parses as Python already, use it
            test_code = body_str.strip()
            
            # First try parsing directly as a module
            body_ast = ast.parse(test_code)
            if body_ast.body:
                self.logger.info(f"Successfully parsed {len(body_ast.body)} statements directly")
                return body_ast.body
        except SyntaxError:
            pass  # Continue to other methods
        
        # PRIORITY 2: Try wrapped parsing with proper indentation handling
        try:
            # Clean the body for proper parsing - but don't lose content
            cleaned_body = self._clean_body_for_parsing_preserve_content(body_str)
            
            # Wrap in a dummy function to provide proper context
            wrapped_code = f"def _dummy():\n{self._indent_code(cleaned_body, 1)}"
            module_ast = ast.parse(wrapped_code)
            
            # Extract the body from the dummy function
            if module_ast.body and isinstance(module_ast.body[0], ast.FunctionDef):
                body_stmts = module_ast.body[0].body
                self.logger.info(f"Successfully parsed {len(body_stmts)} statements with wrapping")
                return body_stmts
                
        except SyntaxError as e:
            self.logger.warning(f"Wrapped parsing failed: {e}")
        
        # PRIORITY 3: Try the translator's proven expansion methods
        python_code = None
        
        if self.translator:
            # Try the most sophisticated method first
            if hasattr(self.translator, '_expand_body_sync'):
                try:
                    python_code = self.translator._expand_body_sync(body_str, context, 0)
                    self.logger.info(f"Used translator _expand_body_sync, result length: {len(python_code)}")
                except Exception as e:
                    self.logger.debug(f"_expand_body_sync failed: {e}")
            
            # Try other translator methods as fallbacks
            if not python_code and hasattr(self.translator, '_process_body_statements'):
                try:
                    lines = self.translator._process_body_statements(body_str, 0)
                    if lines:
                        python_code = '\n'.join(lines)
                        self.logger.info(f"Used translator _process_body_statements, {len(lines)} lines")
                except Exception as e:
                    self.logger.debug(f"_process_body_statements failed: {e}")
        
        # PRIORITY 4: Use our improved conversion when needed
        if not python_code:
            python_code = self._convert_cai_to_python_preserve_content(body_str)
            self.logger.info(f"Used improved CAI to Python conversion, result length: {len(python_code)}")
        
        # STEP 2: Parse the converted code with multiple attempts
        if python_code and python_code.strip():
            try:
                # First try to parse directly
                body_ast = ast.parse(python_code)
                if body_ast.body:
                    self.logger.info(f"Successfully parsed {len(body_ast.body)} statements from converted code")
                    return body_ast.body
            except SyntaxError:
                pass  # Continue to wrapped parsing
            
            try:
                # Wrap in a dummy function to provide proper context
                wrapped_code = f"def _dummy():\n" + self._indent_code(python_code, 1)
                module_ast = ast.parse(wrapped_code)
                
                # Extract the body from the dummy function
                if module_ast.body and isinstance(module_ast.body[0], ast.FunctionDef):
                    body_stmts = module_ast.body[0].body
                    self.logger.info(f"Successfully parsed {len(body_stmts)} statements with wrapped converted code")
                    return body_stmts
                    
            except SyntaxError as e:
                self.logger.warning(f"Wrapped converted code parsing failed: {e}")
        
        # FINAL FALLBACK: Don't lose the content - preserve as comments with at least one executable statement
        self.logger.warning(f"All parsing methods failed for body content, preserving as comments")
        comment_lines = []
        
        # Split by lines and preserve each line as a comment
        for i, line in enumerate(body_str.split('\n'), 1):
            if line.strip():
                comment_lines.append(ast.Expr(
                    value=ast.Constant(value=f"# Body line {i}: {line.strip()}"),
                    lineno=i,
                    col_offset=0
                ))
        
        # Add at least one executable statement
        comment_lines.append(ast.Pass(lineno=len(comment_lines) + 1, col_offset=0))
        
        self.logger.info(f"Preserved {len(comment_lines)-1} lines of original body content as comments")
        return comment_lines if comment_lines else [ast.Pass(lineno=1, col_offset=0)]
    
    def _split_statements_on_semicolon(self, line: str) -> List[str]:
        """Split a line on semicolons while preserving quoted strings."""
        if ';' not in line:
            return [line]
        
        parts = []
        current_part = []
        in_string = False
        string_char = None
        i = 0
        
        while i < len(line):
            char = line[i]
            
            if not in_string:
                if char in ['"', "'"]:
                    in_string = True
                    string_char = char
                    current_part.append(char)
                elif char == ';':
                    # End of statement
                    parts.append(''.join(current_part))
                    current_part = []
                else:
                    current_part.append(char)
            else:
                current_part.append(char)
                if char == string_char:
                    # Check if it's escaped
                    if i == 0 or line[i-1] != '\\':
                        in_string = False
                        string_char = None
            
            i += 1
        
        # Add the last part
        if current_part:
            parts.append(''.join(current_part))
        
        return [part.strip() for part in parts if part.strip()]
    
    def _build_symbol_body_statements(self, body_str: str, context) -> List[ast.stmt]:
        """Build AST statements for symbol class bodies with special tuple syntax handling."""
        if not body_str.strip() or body_str.strip() == 'pass':
            return [ast.Pass(lineno=1, col_offset=0)]
        
        expanded_code = None
        
        # Try symbol-specific body expansion first
        try:
            if self.translator and hasattr(self.translator, '_expand_symbol_body_sync'):
                expanded_code = self.translator._expand_symbol_body_sync(body_str, context, base_indent=0)
        except Exception as e:
            pass
        
        # Fallback to old method if available
        if not expanded_code:
            try:
                if self.translator and hasattr(self.translator, '_process_symbol_method_body'):
                    lines = self.translator._process_symbol_method_body(body_str, 1)
                    if lines:
                        expanded_code = '\n'.join(lines)
            except Exception as e:
                pass
        
        # Use the code we have (expanded or original)
        code_to_format = expanded_code if expanded_code else body_str
        
        # Apply single-pass Black formatting and AST validation
        formatted_code = self.format_and_validate_code(code_to_format)
        
        # Parse the final formatted code
        try:
            body_ast = ast.parse(formatted_code)
            return body_ast.body if body_ast.body else [ast.Pass(lineno=1, col_offset=0)]
        except:
            # Final fallback
            return [ast.Pass(lineno=1, col_offset=0)]
    
    def _split_statements(self, body_str: str) -> List[str]:
        """Split body string into individual statements."""
        # Simple statement splitting - can be enhanced
        statements = []
        
        # Split by newlines first
        lines = body_str.split('\n')
        current_stmt = []
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
                
            current_stmt.append(line)
            
            # Check if this completes a statement (ends with certain patterns)
            if (line.endswith(':') or 
                line.endswith(';') or 
                line.startswith('return') or
                line.startswith('break') or
                line.startswith('continue') or
                not line.endswith('\\')):
                
                if current_stmt:
                    statements.append(' '.join(current_stmt))
                    current_stmt = []
        
        # Add any remaining statement
        if current_stmt:
            statements.append(' '.join(current_stmt))
        
        return statements
    
    def _parse_javascript_methods(self, body_str: str) -> List[ast.stmt]:
        """Parse JavaScript-style methods in class bodies."""
        statements = []
        
        # Pattern to match JavaScript function definitions: function methodName(args) { body }
        # This is more precise than matching any word with parentheses
        method_pattern = re.compile(
            r'function\s+(\w+)\s*\(\s*(.*?)\s*\)\s*\{\s*(.*?)\s*\}',
            re.DOTALL
        )
        
        for match in method_pattern.finditer(body_str):
            method_name = match.group(1)
            args_str = match.group(2)
            method_body = match.group(3)
            
            # Handle special cases
            if method_name == 'constructor':
                method_name = '__init__'
            
            # Build arguments - add self as first parameter
            args = self._build_function_args(args_str)
            if not args.args or args.args[0].arg != 'self':
                self_arg = ast.arg(arg='self', annotation=None, lineno=1, col_offset=0)
                args.args.insert(0, self_arg)
            
            # Parse method body with JavaScript to Python conversion
            if method_body.strip():
                # Convert JavaScript constructs to Python
                python_body = method_body
                python_body = python_body.replace('this.', 'self.')
                python_body = python_body.replace(';', '')
                python_body = re.sub(r'\bvar\s+', '', python_body)
                python_body = re.sub(r'\blet\s+', '', python_body)
                python_body = re.sub(r'\bconst\s+', '', python_body)
                
                try:
                    body_ast = ast.parse(python_body)
                    body_stmts = body_ast.body if body_ast.body else [ast.Pass(lineno=1, col_offset=0)]
                except:
                    # Fallback to pass
                    body_stmts = [ast.Pass(lineno=1, col_offset=0)]
            else:
                body_stmts = [ast.Pass(lineno=1, col_offset=0)]
            
            # Create method definition
            method_def = ast.FunctionDef(
                name=method_name,
                args=args,
                body=body_stmts,
                decorator_list=[],
                returns=None,
                lineno=1,
                col_offset=0
            )
            
            statements.append(method_def)
        
        return statements

    def _parse_with_block_detection(self, code: str, context) -> List[ast.stmt]:
        """Parse code with proper block structure detection."""
        blocks = self._detect_statement_blocks(code)
        statements = []
        
        for block in blocks:
            try:
                if block['type'] == 'block':
                    # Parse complete block structure
                    block_ast = ast.parse(block['content'])
                    statements.extend(block_ast.body)
                else:
                    # Parse single statement
                    stmt_ast = ast.parse(block['content'])
                    statements.extend(stmt_ast.body)
            except SyntaxError as e:
                self.logger.warning(f"Failed to parse block: {e}")
                # Create a comment for debugging
                comment = ast.Expr(ast.Constant(f"# PARSE FAILED: {block['content'][:50]}..."))
                statements.append(comment)
        
        return statements if statements else [ast.Pass(lineno=1, col_offset=0)]

    def _detect_statement_blocks(self, code: str) -> List[Dict[str, Any]]:
        """Detect complete statement blocks including their bodies."""
        blocks = []
        lines = code.split('\n')
        i = 0
        
        while i < len(lines):
            line = lines[i].strip()
            if not line:
                i += 1
                continue
                
            # Check if this starts a block
            if re.match(r'^(def|class|if|elif|else|for|while|try|except|finally|with)\b', line):
                block_start = i
                block_indent = len(lines[i]) - len(lines[i].lstrip())
                
                # Find the end of this block
                j = i + 1
                while j < len(lines):
                    if lines[j].strip():  # Non-empty line
                        current_indent = len(lines[j]) - len(lines[j].lstrip())
                        if current_indent <= block_indent:
                            break
                    j += 1
                
                blocks.append({
                    'type': 'block',
                    'start': block_start,
                    'end': j - 1,
                    'lines': lines[block_start:j],
                    'content': '\n'.join(lines[block_start:j])
                })
                i = j
            else:
                # Single statement
                blocks.append({
                    'type': 'statement', 
                    'start': i,
                    'end': i,
                    'lines': [lines[i]],
                    'content': lines[i]
                })
                i += 1
        
        return blocks

    def _indent_code(self, code: str, level: int) -> str:
        """Properly indent code to a specific level."""
        lines = code.split('\n')
        indented_lines = []
        
        for line in lines:
            if line.strip():
                indented_lines.append('    ' * level + line.strip())
            else:
                indented_lines.append('')
        
        return '\n'.join(indented_lines)

    def _convert_cai_to_python(self, body_str: str) -> str:
        """Conservative CAI to Python conversion fallback - preserves working patterns."""
        code = body_str
        
        # Only apply conversions that are clearly safe and necessary
        
        # Phase 1: Essential JavaScript to Python conversions
        code = code.replace('console.log', 'print')
        code = code.replace('this.', 'self.')
        
        # Phase 2: Boolean and operator conversions (only if not in strings)
        # Use word boundaries to avoid corrupting variable names
        code = re.sub(r'\btrue\b', 'True', code)
        code = re.sub(r'\bfalse\b', 'False', code)
        code = re.sub(r'\s*&&\s*', ' and ', code)
        code = re.sub(r'\s*\|\|\s*', ' or ', code)
        
        # Phase 3: Remove JavaScript variable declarations (conservative)
        code = re.sub(r'\b(var|let|const)\s+', '', code)
        
        # Phase 4: Handle semicolons carefully
        # Only convert semicolons to newlines if they're not inside strings
        if ';' in code:
            lines = []
            for line in code.split('\n'):
                if ';' in line and not self._is_in_string_context(line):
                    # Split on semicolons but preserve the structure
                    parts = [part.strip() for part in line.split(';') if part.strip()]
                    lines.extend(parts)
                else:
                    lines.append(line)
            code = '\n'.join(lines)
        
        # Phase 5: Only apply brace conversion if it's clearly a JS control structure
        if re.search(r'\b(if|for|while)\s*\([^)]*\)\s*\{', code):
            code = self._convert_js_braces_to_python(code)
        
        # Phase 6: Clean up whitespace but preserve structure
        lines = code.split('\n')
        cleaned_lines = []
        for line in lines:
            if line.strip():
                # Normalize internal whitespace but preserve the line structure
                cleaned_line = re.sub(r'\s+', ' ', line.strip())
                cleaned_lines.append(cleaned_line)
        
        return '\n'.join(cleaned_lines)

    def _is_in_string_context(self, line: str) -> bool:
        """Check if semicolons in a line are likely inside strings."""
        # Simple heuristic: if there are quotes and semicolons, be conservative
        quote_count = line.count('"') + line.count("'")
        return quote_count >= 2 and ';' in line

    def _convert_js_braces_to_python(self, code: str) -> str:
        """Convert JavaScript brace-based blocks to Python indentation."""
        # Handle simple if-else statements
        code = re.sub(
            r'if\s*\((.*?)\)\s*\{\s*(.*?)\s*\}\s*else\s*\{\s*(.*?)\s*\}',
            r'if \1:\n    \2\nelse:\n    \3',
            code,
            flags=re.DOTALL
        )
        
        # Handle if statements without else
        code = re.sub(
            r'if\s*\((.*?)\)\s*\{\s*(.*?)\s*\}',
            r'if \1:\n    \2',
            code,
            flags=re.DOTALL
        )
        
        # Handle for loops
        code = re.sub(
            r'for\s*\((.*?)\)\s*\{\s*(.*?)\s*\}',
            r'for \1:\n    \2',
            code,
            flags=re.DOTALL
        )
        
        # Handle while loops
        code = re.sub(
            r'while\s*\((.*?)\)\s*\{\s*(.*?)\s*\}',
            r'while \1:\n    \2',
            code,
            flags=re.DOTALL
        )
        
        # Handle simple blocks that are just semicolon-separated statements
        if '{' in code and '}' in code:
            # Replace { } with newlines for simple cases
            code = re.sub(r'\{\s*', '\n    ', code)
            code = re.sub(r'\s*\}', '\n', code)
        
        # Fix semicolons to newlines
        code = re.sub(r';\s*', '\n', code)
        
        return code
