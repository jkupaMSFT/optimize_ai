"""
CAI3 Python Reconstructor - Reconstructs Python cod                    # Add imports
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
            class_builder = builder.add_class(class_name, class_def.get('parent'))
            
            # Add methods
            for method_name, method_info in class_def['methods'].items():
                self.logger.info(f"      ⚙️  Building method {method_name}")
                method_code = self._build_method_content(
                    method_name, method_info, ast_obj, cai3_full, cai3_map
                )
                self.logger.info(f"      ✅ Method {method_name} code: {method_code[:100]}...")
                self.logger.info(f"      🎯 Adding method {method_name} to class {class_name}")
                # Don't add extra indentation - ClassBuilder handles it
                class_builder.add_method(method_code)
        
        # Add functions (at module level) - AFTER classes
        for func_name, func_def in structure.functions.items():
            func_code = self._build_standalone_function(
                func_name, func_def, ast_obj, cai3_full, cai3_map
            )
            builder.add_function(func_code)
        
        # Add main blockom analyzed structure.
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
        
        from .cai3_ast_translator import HierarchicalCodeBuilder
        
        # Use hierarchical builder
        builder = HierarchicalCodeBuilder()
        self.logger.info("✅ Created HierarchicalCodeBuilder")
        
        # Add imports
        for imp in structure.imports:
            builder.add_import(f"import {imp}")
        
        # Add enums first (they're often used by other classes)
        for enum_name, enum_def in structure.enums.items():
            enum_code = self._build_enum(enum_name, enum_def)
            builder.add_class(enum_code)
        
        # Add dataclasses
        for class_name, dc_def in structure.dataclasses.items():
            dc_code = self._build_dataclass(class_name, dc_def)
            builder.add_class(dc_code)
        
        # Add regular classes with methods FIRST
        for class_name, class_def in structure.classes.items():
            if class_def.get('is_enum'):
                continue  # Already handled
                
            class_builder = builder.add_class(class_name, class_def.get('parent'))
            
            # Add methods
            for method_name, method_info in class_def['methods'].items():
                method_code = self._build_method_content(
                    method_name, method_info, ast_obj, cai3_full, cai3_map
                )
                # Don't add extra indentation - ClassBuilder handles it
                class_builder.add_method(method_code)
        
        # Add functions (at module level) AFTER classes
        self.logger.info(f"🔧 Adding {len(structure.functions)} functions")
        for func_name, func_def in structure.functions.items():
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
        
        args = func_def.get('args', [])
        body_content = func_def.get('body_content', '')
        
        self.logger.info(f"   📋 Args: {args}")
        self.logger.info(f"   📝 Body content: {body_content[:200]}...")
        
        func_def_line = f"def {func_name}({', '.join(args)}):"
        
        if body_content:
            self.logger.info(f"   🔄 Resolving function body...")
            resolved_body = self._resolve_method_body(body_content, ast_obj)
            if resolved_body:
                self.logger.info(f"   ✅ Resolved body: {resolved_body[:100]}...")
                lines = [func_def_line]
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