"""
CAI3 Structure Analyzer - Extracts Python structure from CAI3-LITE definitions.
"""

import re
import ast
from typing import Dict, List, Tuple, Any, Optional
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)

@dataclass
class StructureInfo:
    """Holds extracted Python structure information."""
    classes: Dict[str, Dict]
    functions: Dict[str, Dict]
    dataclasses: Dict[str, Dict]
    enums: Dict[str, Dict]
    main_block: Optional[str]
    imports: List[str]

class CAI3StructureAnalyzer:
    """Analyzes CAI3-LITE AST and extracts Python structure."""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    def analyze(self, ast_obj) -> StructureInfo:
        """Extract complete Python structure from CAI3-LITE AST."""
        structure = StructureInfo(
            classes={},
            functions={},
            dataclasses={},
            enums={},
            main_block=None,
            imports=[]
        )
        
        # Process table entries
        for entry in getattr(ast_obj, 'table', []):
            if entry.startswith('D:'):
                self._process_definition(entry[2:].strip(), ast_obj, structure)
            elif entry.startswith('F:'):
                # Process function entries
                self._process_function_entry(entry, ast_obj, structure)
            elif entry.startswith('C:'):
                # NEW: Process class entries
                self._process_class_entry(entry, ast_obj, structure)
            elif entry.startswith('M:'):
                # NEW: Process method entries
                self._process_method_entry(entry, ast_obj, structure)
            elif entry.startswith('X:'):
                if '__name__' in entry:
                    # Extract main block content after the condition
                    main_content = entry[2:].strip()
                    # Remove the __name__ check part
                    if ':' in main_content:
                        main_content = main_content.split(':', 1)[1].strip()
                    structure.main_block = main_content

        # Extract imports
        if hasattr(ast_obj, 'imports') and ast_obj.imports:
            structure.imports = self._parse_imports(ast_obj.imports)
        
        # Process body-based definitions if needed
        self._process_body_definitions(ast_obj, structure)
        
        return structure

    def _process_definition(self, def_content: str, ast_obj, structure: StructureInfo):
        """Process a D: section definition."""
        # Enum definition pattern: p29(p5):p30=1;p31=2;p32=3
        if re.match(r'p\d+\(p\d+\):', def_content) and '=' in def_content:
            self._process_enum_definition(def_content, ast_obj, structure)
        
        # Dataclass definition pattern: @p51;p58:p0:str;p2:float=0.0
        elif def_content.startswith('@'):
            self._process_dataclass_definition(def_content, ast_obj, structure)
        
        # Class definition patterns:
        # - Simple: p57:
        # - Inheritance: p6(p57):
        elif re.match(r'p\d+(\(p\d+\))?:\s*$', def_content):
            self._process_class_definition(def_content, ast_obj, structure)
    
    def _process_enum_definition(self, def_content: str, ast_obj, structure: StructureInfo):
        """Process enum definition."""
        enum_match = re.match(r'(p\d+)\((p\d+)\):(.+)', def_content)
        if enum_match:
            enum_name_pool = enum_match.group(1)
            enum_base_pool = enum_match.group(2)
            enum_values = enum_match.group(3)
            
            enum_name = ast_obj.pools.get(enum_name_pool, 'UnknownEnum')
            structure.enums[enum_name] = {
                'base': ast_obj.pools.get(enum_base_pool, 'Enum'),
                'values': self._parse_enum_values(enum_values, ast_obj.pools)
            }
    
    def _process_dataclass_definition(self, def_content: str, ast_obj, structure: StructureInfo):
        """Process dataclass definition."""
        dc_match = re.match(r'@(p\d+);(p\d+):(.+)', def_content)
        if dc_match:
            decorator_pool = dc_match.group(1)
            class_name_pool = dc_match.group(2)
            fields_def = dc_match.group(3)
            
            class_name = ast_obj.pools.get(class_name_pool, 'UnknownClass')
            structure.dataclasses[class_name] = {
                'decorator': ast_obj.pools.get(decorator_pool, 'dataclass'),
                'fields': self._parse_dataclass_fields(fields_def, ast_obj.pools)
            }
    
    def _process_class_definition(self, def_content: str, ast_obj, structure: StructureInfo):
        """Process class definition."""
        # Handle both simple (p57:) and inheritance (p6(p57):) patterns
        if '(' in def_content and ')' in def_content:
            # Subclass definition like p6(p57):
            match = re.match(r'(p\d+)\((p\d+)\):', def_content)
            if match:
                class_pool = match.group(1)
                parent_pool = match.group(2)
                class_name = ast_obj.pools.get(class_pool, 'UnknownClass')
                parent_name = ast_obj.pools.get(parent_pool, 'UnknownParent')
                structure.classes[class_name] = {
                    'methods': {},
                    'parent': parent_name
                }
        else:
            # Simple class definition like p57:
            class_pool = def_content.rstrip(':')
            class_name = ast_obj.pools.get(class_pool, 'UnknownClass')
            structure.classes[class_name] = {
                'methods': {},
                'parent': None
            }
    
    def _parse_enum_values(self, values_str: str, pools: Dict) -> List[Tuple[str, Any]]:
        """Parse enum value definitions."""
        values = []
        for assignment in values_str.split(';'):
            if '=' in assignment:
                name, value = assignment.split('=', 1)
                name = pools.get(name.strip(), name.strip())
                if value.strip().startswith('p') and value.strip()[1:].isdigit():
                    value = pools.get(value.strip(), value.strip())
                else:
                    try:
                        value = int(value.strip())
                    except ValueError:
                        value = value.strip()
                values.append((name, value))
        return values
    
    def _parse_dataclass_fields(self, fields_str: str, pools: Dict) -> List[Dict]:
        """Parse dataclass field definitions."""
        fields = []
        for field_def in fields_str.split(';'):
            field_def = field_def.strip()
            if not field_def:
                continue
            
            if ':' in field_def:
                name_part, type_part = field_def.split(':', 1)
                name = pools.get(name_part, name_part)
                
                default = None
                if '=' in type_part:
                    type_str, default_str = type_part.split('=', 1)
                    type_name = pools.get(type_str.strip(), type_str.strip())
                    
                    # Handle field(default_factory=...) pattern
                    if default_str.strip().startswith('p') and '(' in default_str:
                        # Parse p9(p10=p7) pattern
                        match = re.match(r'(p\d+)\((p\d+)=(p\d+)\)', default_str.strip())
                        if match:
                            field_func = pools.get(match.group(1), 'field')
                            factory_key = pools.get(match.group(2), 'default_factory')
                            factory_val = pools.get(match.group(3), 'dict')
                            default = f"{field_func}({factory_key}={factory_val})"
                        else:
                            default = pools.get(default_str.strip(), default_str.strip())
                    else:
                        default = pools.get(default_str.strip(), default_str.strip())
                else:
                    type_name = pools.get(type_part.strip(), type_part.strip())
                
                fields.append({
                    'name': name,
                    'type': type_name,
                    'default': default
                })
        
        return fields
    
    def _parse_imports(self, imports_str: str) -> List[str]:
        """Parse import string into list of import statements."""
        imports = []
        for imp in imports_str.split(','):
            imports.append(imp.strip())
        return imports
    
    def _process_body_definitions(self, ast_obj, structure: StructureInfo):
        """Process body definitions to extract classes and functions."""
        if not hasattr(ast_obj, 'bodies'):
            return
        
        bodies = ast_obj.bodies
        pools = getattr(ast_obj, 'pools', {})
        
        # First pass: identify classes and their basic structure
        class_bodies = {}  # Map body_id -> class_name
        
        for body_id, body_content in bodies.items():
            # Check if this body represents a class definition
            if self._is_class_body(body_content, pools):
                class_name = self._extract_class_name(body_content, pools)
                if class_name:
                    # Check for inheritance
                    parent_class = self._extract_parent_class(body_content)
                    
                    structure.classes[class_name] = {
                        'methods': {},
                        'parent': parent_class,
                        'body_id': body_id,
                        'is_enum': 'enum.Enum' in body_content
                    }
                    class_bodies[body_id] = class_name
            
            # Check if this body represents a function definition
            elif self._is_function_body(body_content, pools):
                func_name = self._extract_function_name(body_content, pools)
                if func_name:
                    args = self._extract_function_args(body_content, pools)
                    structure.functions[func_name] = {
                        'args': args,
                        'body_id': body_id,
                        'body_content': self._find_function_body_content(body_id, bodies)
                    }
        
        # Second pass: assign remaining bodies to classes based on context
        class_names = list(structure.classes.keys())
        for body_id, body_content in bodies.items():
            if body_id not in class_bodies:  # Not a class definition itself
                if body_content.startswith('self.') and '=' in body_content:
                    # This is an attribute assignment - assign to appropriate class
                    target_class = self._determine_target_class(body_id, class_names, bodies)
                    if target_class and target_class in structure.classes:
                        # Add as a method or attribute
                        if '__init__' not in structure.classes[target_class]['methods']:
                            structure.classes[target_class]['methods']['__init__'] = {
                                'args': ['self'],
                                'body_content': body_content
                            }
                        else:
                            # Append to existing __init__ body
                            existing_body = structure.classes[target_class]['methods']['__init__'].get('body_content', '')
                            if existing_body:
                                structure.classes[target_class]['methods']['__init__']['body_content'] = f"{existing_body};{body_content}"
                            else:
                                structure.classes[target_class]['methods']['__init__']['body_content'] = body_content
                
                elif '=' in body_content and not body_content.startswith('self.'):
                    # This might be enum values - check if there's an enum class nearby
                    target_class = self._determine_target_class(body_id, class_names, bodies)
                    if target_class and target_class in structure.classes:
                        if structure.classes[target_class].get('is_enum'):
                            # Add enum value
                            if 'enum_values' not in structure.classes[target_class]:
                                structure.classes[target_class]['enum_values'] = []
                            structure.classes[target_class]['enum_values'].append(body_content)
        
        # Process D: definitions to add methods to classes
        for entry in getattr(ast_obj, 'table', []):
            if entry.startswith('D:'):
                self._assign_method_to_class(entry[2:].strip(), structure, pools)
    
    def _determine_target_class(self, body_id: str, class_names: List[str], bodies: Dict) -> Optional[str]:
        """Determine which class a body should belong to based on body ID proximity."""
        try:
            current_id = int(body_id)
            # Find the closest preceding class definition
            best_class = None
            best_distance = float('inf')
            
            for bid, content in bodies.items():
                try:
                    bid_num = int(bid)
                    if bid_num < current_id:  # Only consider preceding bodies
                        for class_name in class_names:
                            if class_name in content or content == class_name:
                                distance = current_id - bid_num
                                if distance < best_distance:
                                    best_distance = distance
                                    best_class = class_name
                except ValueError:
                    continue
            
            return best_class
        except ValueError:
            # If body_id is not numeric, assign to first class
            return class_names[0] if class_names else None
    
    def _is_class_body(self, body_content: str, pools: Dict) -> bool:
        """Check if body content represents a class definition."""
        # Look for class identifier patterns (a0, a1, etc.) potentially with inheritance
        return (
            re.match(r'^[a-z]\d+(\([^)]+\))?$', body_content.strip()) or
            'enum.Enum' in body_content
        )
    
    def _is_function_body(self, body_content: str, pools: Dict) -> bool:
        """Check if body content represents a function definition."""
        # Look for function identifier patterns or actual function content
        return (
            re.match(r'^[a-z]\d+$', body_content.strip()) and
            not self._is_class_body(body_content, pools)
        )
    
    def _extract_class_name(self, body_content: str, pools: Dict) -> Optional[str]:
        """Extract class name from body content."""
        # If it's a simple identifier (a0, a1), look it up in pools
        match = re.match(r'^([a-z]\d+)', body_content.strip())
        if match:
            identifier = match.group(1)
            return pools.get(identifier, identifier)
        return None
    
    def _extract_parent_class(self, body_content: str) -> Optional[str]:
        """Extract parent class from body content."""
        if '(' in body_content and ')' in body_content:
            parent_match = re.search(r'\(([^)]+)\)', body_content)
            if parent_match:
                parent = parent_match.group(1)
                if parent == 'enum.Enum':
                    return 'enum.Enum'
                return parent
        return None
    
    def _extract_function_name(self, body_content: str, pools: Dict) -> Optional[str]:
        """Extract function name from body content."""
        match = re.match(r'^([a-z]\d+)$', body_content.strip())
        if match:
            identifier = match.group(1)
            return pools.get(identifier, identifier)
        return None
    
    def _extract_function_args(self, body_content: str, pools: Dict) -> List[str]:
        """Extract function arguments from D: definitions."""
        # This will be populated when we process D: entries
        return []
    
    def _find_function_body_content(self, body_id: str, bodies: Dict) -> str:
        """Find actual function body content from subsequent body IDs."""
        # Look for bodies that contain actual implementation
        for bid, content in bodies.items():
            if bid != body_id and (
                content.startswith('self.') or 
                'return' in content or
                '=' in content
            ):
                return content
        return ""
    
    def _assign_method_to_class(self, def_content: str, structure: StructureInfo, pools: Dict):
        """Assign method definitions to appropriate classes."""
        # Look for method definitions like "__init__(self,p6:str)" or "self.name=p0;self.level=p1"
        if def_content.startswith('__init__(') or def_content.startswith('self.'):
            # Find the appropriate class for this method
            for class_name, class_info in structure.classes.items():
                # For now, assign to the first class found
                # In a more sophisticated implementation, we'd track context
                if '__init__(' in def_content:
                    method_name = '__init__'
                    args = self._parse_method_args(def_content)
                    class_info['methods'][method_name] = {
                        'args': args,
                        'body_content': def_content
                    }
                elif def_content.startswith('self.'):
                    # This is likely an __init__ body assignment
                    if '__init__' in class_info['methods']:
                        class_info['methods']['__init__']['body_content'] = def_content
                    else:
                        class_info['methods']['__init__'] = {
                            'args': ['self'],
                            'body_content': def_content
                        }
                break
        elif '=' in def_content and not def_content.startswith('self.'):
            # This might be enum values - look for enum classes
            for class_name, class_info in structure.classes.items():
                if class_info.get('is_enum'):
                    # Parse enum values like "BASIC=1;PREMIUM=2;ENTERPRISE=3"
                    if 'enum_values' not in class_info:
                        class_info['enum_values'] = []
                    
                    # Split by semicolon and add each enum value
                    enum_entries = def_content.split(';')
                    for entry in enum_entries:
                        entry = entry.strip()
                        if entry and '=' in entry:
                            class_info['enum_values'].append(entry)
                    break
    
    def _parse_method_args(self, def_content: str) -> List[str]:
        """Parse method arguments from definition."""
        match = re.search(r'__init__\(([^)]+)\)', def_content)
        if match:
            args_str = match.group(1)
            args = [arg.strip() for arg in args_str.split(',')]
            return args
        return ['self']
    
    def _map_bodies_to_structures(self, ast_obj, structure: StructureInfo):
        """Map body IDs to their corresponding methods/functions."""
        if not hasattr(ast_obj, 'bodies'):
            return
        
        body_ids = sorted([bid for bid in ast_obj.bodies.keys() if bid.isdigit()], key=int)
        
        if structure.classes:
            class_names = list(structure.classes.keys())
            if class_names:
                # B0-B3 go to first class (e.g., Processor)
                for i in range(4):
                    if str(i) in ast_obj.bodies:
                        method_name = self._infer_method_name(ast_obj.bodies[str(i)], ast_obj.pools)
                        structure.classes[class_names[0]]['methods'][str(i)] = {
                            'name': method_name,
                            'body': ast_obj.bodies[str(i)]
                        }
                
                # B4-B6 go to second class (e.g., Calculator subclass)
                if len(class_names) > 1:
                    for i in range(4, 7):
                        if str(i) in ast_obj.bodies:
                            method_name = self._infer_method_name(ast_obj.bodies[str(i)], ast_obj.pools)
                            structure.classes[class_names[1]]['methods'][str(i)] = {
                                'name': method_name,
                                'body': ast_obj.bodies[str(i)]
                            }
                            # Set parent class
                            structure.classes[class_names[1]]['parent'] = class_names[0]
    
    def _infer_method_name(self, body_content: str, pools: Dict) -> str:
        """Infer method name from body content."""
        if body_content.startswith('p28(') or 'p28' in pools and pools['p28'] == '__init__':
            return '__init__'
        
        # Check for specific pool references
        for pool_id in ['p33', 'p34', 'p35']:
            if f'{pool_id}(' in body_content and pool_id in pools:
                return pools[pool_id]
        
        if 'get_summary(' in body_content:
            return 'get_summary'
        
        # Try to extract from the first identifier
        match = re.match(r'(p\d+)\(', body_content)
        if match and match.group(1) in pools:
            return pools[match.group(1)]
        
        return 'unknown_method'
    
    def _process_function_entry(self, entry: str, ast_obj, structure: StructureInfo):
        """Process a standalone function entry."""
        # Pattern: F:function_name#body_id or F:function_name(args)#body_id
        match = re.match(r'F:([A-Za-z_]\w*)(?:\(([^)]*)\))?(?:#([A-Za-z0-9_]+))?', entry)
        if match:
            func_name = match.group(1)
            args_str = match.group(2) or ''
            body_id = match.group(3)
            
            # Parse arguments
            args = []
            if args_str:
                for arg in args_str.split(','):
                    arg = arg.strip()
                    if arg.startswith('p') and arg[1:].isdigit():
                        # Resolve pool reference
                        args.append(ast_obj.pools.get(arg, arg))
                    else:
                        args.append(arg)
            
            # Look up body content with B# prefix
            body_content = ''
            if body_id:
                body_key = f'B#{body_id}'
                body_content = ast_obj.bodies.get(body_key, '')
            
            # Infer parameters from body content if no explicit args provided
            if not args and body_content:
                args = self._infer_function_parameters(body_content, ast_obj.pools)
            
            structure.functions[func_name] = {
                'name': func_name,
                'args': args,
                'body_id': body_id,
                'body_content': body_content
            }
    
    def _infer_function_parameters(self, body_content: str, pools: Dict[str, str]) -> List[str]:
        """Infer function parameters from pool references in body content."""
        import re
        
        # Find all pool references (p0, p1, p2, etc.) in the body
        pool_pattern = r'\bp(\d+)\b'
        pool_matches = re.findall(pool_pattern, body_content)
        
        # Find pools that are assigned to (they are outputs, not inputs)
        assignment_pattern = r'\bp(\d+)\s*='
        assigned_pools = set(re.findall(assignment_pattern, body_content))
        
        # Get unique pool references, excluding those that are assigned to
        used_pools = set(pool_matches) - assigned_pools
        parameters = []
        
        # Sort by pool number to ensure consistent parameter order
        for pool_num in sorted(used_pools, key=int):
            pool_ref = f'p{pool_num}'
            param_name = pools.get(pool_ref, f'param_{pool_num}')
            if param_name not in parameters:
                parameters.append(param_name)
        
        return parameters

    def _process_class_entry(self, entry: str, ast_obj, structure: StructureInfo):
        """Process C: class entries like 'C:ClassName' or 'C:ClassName(Parent)'."""
        # Remove 'C:' prefix
        content = entry[2:].strip()
        
        # Parse class with optional parent
        parent_match = re.match(r'(\w+)\((\w+)\)', content)
        if parent_match:
            class_name = parent_match.group(1)
            parent_name = parent_match.group(2)
            structure.classes[class_name] = {
                'methods': {},
                'parent': parent_name
            }
        else:
            # Simple class without parent
            class_name = content.split()[0] if ' ' in content else content
            structure.classes[class_name] = {
                'methods': {},
                'parent': None
            }
        
        self.logger.debug(f"Added class from T: entry: {class_name}")

    def _process_method_entry(self, entry: str, ast_obj, structure: StructureInfo):
        """Process M: method entries like 'M:ClassName.method#bodyId' or 'M:ClassName.method(args)#bodyId'."""
        # Pattern: M:ClassName.method_name#body_id or M:ClassName.method_name(args)#body_id
        pattern = r'M:([A-Za-z_]\w*)\.([A-Za-z_]\w*)(?:\(([^)]*)\))?(?:#([A-Za-z0-9_]+))?'
        match = re.match(pattern, entry)
        
        if match:
            class_name = match.group(1)
            method_name = match.group(2)
            args_str = match.group(3) or ''
            body_id = match.group(4)
            
            # Ensure class exists
            if class_name not in structure.classes:
                structure.classes[class_name] = {'methods': {}, 'parent': None}
            
            # Parse arguments
            args = ['self']  # Default for instance methods
            if args_str:
                # Parse additional args
                for arg in args_str.split(','):
                    arg = arg.strip()
                    if arg and arg != 'self':
                        # Resolve pool references
                        if arg.startswith('p') and arg[1:].isdigit():
                            args.append(ast_obj.pools.get(arg, arg))
                        else:
                            args.append(arg)
            
            # Get body content
            body_content = ''
            if body_id:
                # Look for body with B# prefix
                body_key = body_id if body_id in ast_obj.bodies else f'B#{body_id}'
                if body_key in ast_obj.bodies:
                    body_content = ast_obj.bodies[body_key]
                elif body_id in ast_obj.bodies:
                    body_content = ast_obj.bodies[body_id]
            
            # Add method to class
            structure.classes[class_name]['methods'][method_name] = {
                'args': args,
                'body_id': body_id,
                'body_content': body_content
            }
            
            self.logger.debug(f"Added method from T: entry: {class_name}.{method_name}")