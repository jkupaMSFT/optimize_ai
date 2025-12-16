"""
CAI3 Python Reconstructor - Reconstructs Python code from CAI3 structure.
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
    
    # Update the reconstruct method to use new hierarchical approach
    def reconstruct(self, ast_obj, structure: StructureInfo, 
                   cai3_full=None, cai3_map=None) -> str:
        """Reconstruct Python file with PROPER hierarchy."""
        self.logger.info("🏗️  Starting Python code reconstruction...")
        
        from .cai3_ast_translator import SimpleCodeBuilder
        
        # Use simple builder
        builder = SimpleCodeBuilder()
        self.logger.info("✅ Created SimpleCodeBuilder")
        
        # Add imports
        self.logger.info(f"📦 Adding {len(structure.imports)} imports")
        for imp in structure.imports:
            self.logger.info(f"   ➕ import {imp}")
            builder.add_import(f"import {imp}")
        
        # Add regular classes with methods FIRST
        self.logger.info(f"🏗️  Adding {len(structure.classes)} classes")
        for class_name, class_def in structure.classes.items():
            if class_def.get('is_enum'):
                self.logger.info(f"   ⏭️  Skipping enum class {class_name}")
                continue  # Already handled
                
            self.logger.info(f"   🏗️  Building class {class_name} with {len(class_def['methods'])} methods")
            
            # Build all methods for this class
            method_codes = []
            for method_name, method_info in class_def['methods'].items():
                self.logger.info(f"      ⚙️  Building method {method_name}")
                method_code = self._build_method_content(
                    method_name, method_info, ast_obj, cai3_full, cai3_map
                )
                self.logger.info(f"      ✅ Method {method_name} code: {method_code[:100]}...")
                method_codes.append(method_code)
            
            # Add the class with all its methods
            parent = class_def.get('parent')
            self.logger.info(f"   🎯 Adding class {class_name} to builder (parent: {parent})")
            builder.add_class(class_name, method_codes, parent)
        
        # Add functions (at module level) AFTER classes
        # Handle both dictionary and list formats for functions
        functions_data = structure.get('functions', []) if isinstance(structure, dict) else (structure.functions if hasattr(structure, 'functions') else [])
        self.logger.info(f"🔧 Adding {len(functions_data)} functions")
        
        # Handle functions as either dictionary or list
        if isinstance(functions_data, dict):
            # Dictionary format: {func_name: func_def}
            for func_name, func_def in functions_data.items():
                self.logger.info(f"   🔧 Building function {func_name}")
                func_code = self._build_standalone_function(
                    func_name, func_def, ast_obj, cai3_full, cai3_map
                )
                self.logger.info(f"   ✅ Function {func_name} code: {func_code[:100]}...")
                self.logger.info(f"   🎯 Adding function {func_name} to module level")
                builder.add_function(func_code)
        elif isinstance(functions_data, list):
            # List format: [{name: func_name, ...}, ...]
            for func_def in functions_data:
                if isinstance(func_def, dict) and 'name' in func_def:
                    func_name = func_def['name']
                    self.logger.info(f"   🔧 Building function {func_name}")
                    func_code = self._build_standalone_function(
                        func_name, func_def, ast_obj, cai3_full, cai3_map
                    )
                    self.logger.info(f"   ✅ Function {func_name} code: {func_code[:100]}...")
                    self.logger.info(f"   🎯 Adding function {func_name} to module level")
                    builder.add_function(func_code)
        
        # Add main block
        if structure.main_block:
            main_code = self._build_main_block(structure.main_block, ast_obj.pools)
            builder.add_main_block(main_code)
        
        # Build and format
        self.logger.info("🔨 Building final code...")
        code = builder.build()
        self.logger.info(f"📄 Generated code length: {len(code)} characters")
        self.logger.info(f"📄 First 200 chars: {code[:200]}...")
        
        # Validate before returning
        self.logger.info("🔍 Starting validation...")
        try:
            from .cai3_validation import CAI3CodeValidator
            validator = CAI3CodeValidator()
        except ImportError:
            self.logger.warning("⚠️  CAI3CodeValidator not available, skipping validation")
            return self._format_code(code)
        is_valid, fixed_code, issues = validator.validate(code)
        
        if issues:
            self.logger.warning(f"Reconstruction issues: {issues}")
        
        return self._format_code(fixed_code)
    
    def _build_method_content(self, method_name: str, method_info: Dict,
                         ast_obj, cai3_full, cai3_map) -> str:
        """Build method content without extra class context."""
        self.logger.info(f"🔨 Building method {method_name}")
        
        body_content = method_info.get('body_content', '')
        args = method_info.get('args', ['self'])
        
        self.logger.info(f"   📋 Args: {args}")
        self.logger.info(f"   📝 Body content: {body_content}")
        
        method_def = f"def {method_name}({', '.join(args)}):"
        
        if body_content:
            # Resolve and parse body
            self.logger.info(f"   🔄 Resolving method body...")
            resolved_body = self._resolve_method_body(body_content, ast_obj)
            
            if resolved_body:
                self.logger.info(f"   ✅ Resolved body: {resolved_body[:100]}...")
                lines = [method_def]
                
                # CRITICAL FIX: Check if resolved_body already contains proper Python structure
                # If it contains try/except blocks, preserve the existing indentation
                if 'try:' in resolved_body and 'except ' in resolved_body:
                    # The resolved body already has proper Python structure with indentation
                    # Split by lines and preserve existing indentation, just add base method indent
                    for line in resolved_body.split('\n'):
                        if line.strip():  # Only process non-empty lines
                            # Add the base method indentation (4 spaces) to existing indentation
                            lines.append(f"    {line}")
                        else:
                            lines.append(line)  # Preserve empty lines
                else:
                    # For simple statements without try/except, add basic indentation
                    for stmt in resolved_body.split('\n'):
                        if stmt.strip():
                            lines.append(f"    {stmt}")
                
                result = '\n'.join(lines)
                self.logger.info(f"   🎯 Final method: {result}")
                return result
        
        self.logger.info(f"   ⚠️  No body content, using 'pass'")
        return f"{method_def}\n    pass"
    
    def _resolve_method_body(self, body_content: str, ast_obj) -> str:
        """Resolve method body content."""
        if not body_content:
            return ""
        
        # Apply pool resolution
        resolved = body_content
        if hasattr(ast_obj, 'pools'):
            for pool_id, value in ast_obj.pools.items():
                resolved = resolved.replace(pool_id, str(value))
        
        # CRITICAL FIX: Only apply CAI3 syntax fixing if the content appears to need it
        # If the content already has proper Python syntax (try/except blocks, etc.), don't process it
        needs_cai3_fixing = False
        
        # Check for CAI3-specific markers that indicate content needs processing
        cai3_markers = ['T{', 'X(', 'I(', 'W(', '@', 'R{', '#C3L', 'CAI3:', 'P:', 'B#']
        if any(marker in resolved for marker in cai3_markers):
            needs_cai3_fixing = True
        
        # Check if content has malformed syntax that needs fixing
        try:
            import ast
            ast.parse(resolved)
            # Content is already valid Python - don't process it further
            self.logger.info("✅ Method body already valid Python - skipping CAI3 syntax fixes")
        except SyntaxError:
            # Content has syntax issues - may need CAI3 fixing
            needs_cai3_fixing = True
        
        if needs_cai3_fixing:
            # Fix CAI3 syntax
            from .cai3_resolution_pipeline import CAI3ResolutionPipeline
            pipeline = CAI3ResolutionPipeline({}, ast_obj.pools if hasattr(ast_obj, 'pools') else {})
            resolved = pipeline._fix_cai3_syntax(resolved)
        
        return resolved
    
    def _format_code(self, code: str) -> str:
        """Format code with black or manual formatting."""
        try:
            import black
            return black.format_str(code, mode=black.Mode())
        except Exception:
            # Manual formatting fallback
            return self._manual_format(code)
    
    def _manual_format(self, code: str) -> str:
        """Basic manual formatting."""
        lines = code.split('\n')
        formatted = []
        
        for i, line in enumerate(lines):
            # Add blank lines after class/function definitions
            if i > 0 and line.strip().startswith(('class ', 'def ')):
                prev = lines[i-1].strip()
                if prev and not prev.startswith('@'):
                    formatted.append('')
            
            formatted.append(line)
        
        return '\n'.join(formatted)
    
    def _build_enum(self, enum_name: str, enum_def: Dict) -> str:
        """Build enum class code."""
        base = enum_def.get('base', 'Enum')
        values = enum_def.get('values', [])
        
        lines = [f"class {enum_name}({base}):"]
        if values:
            for name, value in values:
                lines.append(f"    {name} = {repr(value)}")
        else:
            lines.append("    pass")
        
        return '\n'.join(lines)
    
    def _build_dataclass(self, class_name: str, dc_def: Dict) -> str:
        """Build dataclass code."""
        decorator = dc_def.get('decorator', 'dataclass')
        fields = dc_def.get('fields', [])
        
        lines = [f"@{decorator}", f"class {class_name}:"]
        
        if fields:
            for field in fields:
                field_name = field['name']
                field_type = field['type']
                default = field.get('default')
                
                if default:
                    lines.append(f"    {field_name}: {field_type} = {default}")
                else:
                    lines.append(f"    {field_name}: {field_type}")
        else:
            lines.append("    pass")
        
        return '\n'.join(lines)
    
    def _build_standalone_function(self, func_name: str, func_def: Dict, 
                                  ast_obj, cai3_full, cai3_map) -> str:
        """Build standalone function code."""
        self.logger.info(f"🔧 Building standalone function {func_name}")
        
        # Handle both formats: direct name or name from dict
        actual_func_name = func_def.get('name', func_name) if isinstance(func_def, dict) else func_name
        args = func_def.get('args', [])
        body_content = func_def.get('body_content', '')
        
        self.logger.info(f"   📋 Function name: {actual_func_name}")
        self.logger.info(f"   📋 Args: {args}")
        self.logger.info(f"   📝 Body content: {body_content[:200] if body_content else 'None'}...")
        
        func_def_line = f"def {actual_func_name}({', '.join(args)}):"
        
        if body_content:
            self.logger.info(f"   🔄 Resolving function body...")
            resolved_body = self._resolve_method_body(body_content, ast_obj)
            if resolved_body:
                self.logger.info(f"   ✅ Resolved body: {resolved_body[:100]}...")
                lines = [func_def_line]
                
                # Handle multi-line body content properly
                for stmt in resolved_body.split('\n'):
                    if stmt.strip():
                        lines.append(f"    {stmt}")
                
                result = '\n'.join(lines)
                self.logger.info(f"   🎯 Final function: {result}")
                return result
        
        self.logger.info(f"   ⚠️  No body content, using 'pass'")
        return f"{func_def_line}\n    pass"
    
    def _build_main_block(self, main_block: str, pools: Dict) -> str:
        """Build main block code."""
        if not main_block:
            return ""
        
        # Apply pool resolution
        resolved = main_block
        for pool_id, value in pools.items():
            resolved = resolved.replace(pool_id, str(value))
        
        return resolved