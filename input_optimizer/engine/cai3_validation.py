"""CAI3 Python code validation pipeline."""

import ast
import re
from typing import Tuple, List, Dict, Any

class CAI3CodeValidator:
    """Multi-stage validation for translated Python code."""
    
    def __init__(self):
        self.errors = []
        self.warnings = []
    
    def validate(self, code: str) -> Tuple[bool, str, List[str]]:
        """
        Perform comprehensive validation.
        Returns: (is_valid, fixed_code, issues)
        """
        self.errors = []
        self.warnings = []
        
        # Stage 1: Basic syntax validation
        code = self._validate_syntax(code)
        
        # Stage 2: Fix structural issues
        code = self._fix_structural_issues(code)
        
        # Stage 3: Resolve remaining references
        code = self._resolve_remaining_references(code)
        
        # Stage 4: Final AST validation
        is_valid = self._final_ast_validation(code)
        
        issues = self.errors + self.warnings
        return is_valid, code, issues
    
    def _validate_syntax(self, code: str) -> str:
        """Basic syntax validation and fixes."""
        try:
            ast.parse(code)
            return code
        except SyntaxError as e:
            # Apply targeted fixes based on error
            if "unexpected indent" in str(e):
                code = self._fix_indentation(code)
            elif "invalid syntax" in str(e):
                code = self._fix_common_syntax_errors(code, e)
            
            self.warnings.append(f"Applied syntax fix at line {e.lineno}: {e.msg}")
        
        return code
    
    def _fix_structural_issues(self, code: str) -> str:
        """Fix structural problems like nested classes/functions."""
        lines = code.split('\n')
        fixed_lines = []
        
        for i, line in enumerate(lines):
            stripped = line.strip()
            current_indent = len(line) - len(line.lstrip()) if line.strip() else 0
            
            # Check for structural issues based on indentation patterns
            if stripped.startswith('class ') and current_indent > 0:
                # Class inside function/method - this is wrong
                self.errors.append(f"Line {i+1}: Class defined inside function")
                # Move to module level by removing indentation
                line = stripped
                
            elif stripped.startswith('def ') and current_indent > 4:
                # Function nested too deep (more than class method level)
                self.errors.append(f"Line {i+1}: Function nested too deeply (indent={current_indent})")
                # Reset to appropriate level - either module level or class method level
                if current_indent > 8:
                    # Very deep nesting - move to module level
                    line = stripped
                else:
                    # Move to class method level
                    line = '    ' + stripped
                    
            fixed_lines.append(line)
            
        return '\n'.join(fixed_lines)
    
    def _resolve_remaining_references(self, code: str) -> str:
        """Find and fix any remaining unresolved references."""
        # Pattern for unresolved hash references
        hash_pattern = r'\b([0-9a-f]{4})\b(?!\w)'
        
        def check_hash(match):
            token = match.group(1)
            # Check if it's a valid hex number that might be a hash
            try:
                int(token, 16)
                self.warnings.append(f"Possible unresolved hash: {token}")
                return f'hash_{token}'  # Add hash_ prefix
            except ValueError:
                return token
        
        code = re.sub(hash_pattern, check_hash, code)
        
        # Check for unresolved pool references
        pool_pattern = r'\bp(\d+)\b'
        pools_found = re.findall(pool_pattern, code)
        if pools_found:
            self.warnings.append(f"Unresolved pool references: {', '.join(set(pools_found))}")
        
        return code
    
    def _final_ast_validation(self, code: str) -> bool:
        """Final validation using AST."""
        try:
            tree = ast.parse(code)
            
            # Additional structural checks
            class StructureValidator(ast.NodeVisitor):
                def __init__(self):
                    self.issues = []
                    self.context_stack = []
                
                def visit_ClassDef(self, node):
                    if 'function' in self.context_stack:
                        self.issues.append(f"Class {node.name} defined inside function")
                    self.context_stack.append('class')
                    self.generic_visit(node)
                    self.context_stack.pop()
                
                def visit_FunctionDef(self, node):
                    if 'function' in self.context_stack and 'class' not in self.context_stack:
                        self.issues.append(f"Function {node.name} defined inside function")
                    self.context_stack.append('function')
                    self.generic_visit(node)
                    self.context_stack.pop()
            
            validator = StructureValidator()
            validator.visit(tree)
            
            if validator.issues:
                self.errors.extend(validator.issues)
                return False
            
            # Try to compile
            compile(tree, '<string>', 'exec')
            return True
            
        except Exception as e:
            self.errors.append(f"Validation failed: {str(e)}")
            return False
    
    def _fix_indentation(self, code: str) -> str:
        """Fix indentation issues."""
        lines = code.split('\n')
        fixed = []
        indent_stack = [0]
        
        for line in lines:
            stripped = line.strip()
            if not stripped:
                fixed.append('')
                continue
            
            # Determine proper indent
            if stripped.startswith(('elif', 'else', 'except', 'finally')):
                # Same level as previous if/try
                indent = indent_stack[-2] if len(indent_stack) > 1 else 0
            elif any(line.lstrip().startswith(kw + ' ') for kw in ['class', 'def', 'if', 'for', 'while', 'try', 'with']):
                indent = indent_stack[-1]
            else:
                indent = indent_stack[-1]
            
            fixed.append(' ' * indent + stripped)
            
            # Update indent stack
            if stripped.endswith(':'):
                indent_stack.append(indent + 4)
            elif stripped in ['pass', 'return', 'break', 'continue'] or stripped.startswith('return '):
                if len(indent_stack) > 1:
                    indent_stack.pop()
        
        return '\n'.join(fixed)
    
    def _fix_common_syntax_errors(self, code: str, error: SyntaxError) -> str:
        """Fix common syntax errors."""
        lines = code.split('\n')
        
        if error.lineno and 0 < error.lineno <= len(lines):
            problem_line = lines[error.lineno - 1]
            
            # Fix missing colons
            if "expected ':'" in error.msg:
                lines[error.lineno - 1] = problem_line + ':'
            
            # Fix invalid function calls
            elif re.search(r'\.\d+\(', problem_line):
                lines[error.lineno - 1] = re.sub(r'\.(\d+)\(', r'.hash_\1(', problem_line)
        
        return '\n'.join(lines)