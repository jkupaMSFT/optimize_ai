"""CAI3-LITE Grammar Parser using simple regex-based approach."""

import re
import logging
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from .cai3_structure_analyzer import StructureInfo

@dataclass
class CAI3LiteAST:
    """Structured representation of CAI3-LITE content."""
    header: str = ""
    version: str = ""               # Extracted from header
    python_version: str = ""        # Extracted from header  
    filename: str = ""              # Extracted from header
    imports: str = ""              # I: section
    chain_aliases: Dict[str, str] = None  # D: section
    cid_aliases: Dict[str, str] = None    # X: section
    pools: Dict[str, str] = None          # P: section
    table: List[str] = None               # T: section
    bodies: Dict[str, str] = None         # B# sections
    
    def __post_init__(self):
        """Initialize mutable default values."""
        if self.chain_aliases is None:
            self.chain_aliases = {}
        if self.cid_aliases is None:
            self.cid_aliases = {}
        if self.pools is None:
            self.pools = {}
        if self.table is None:
            self.table = []
        if self.bodies is None:
            self.bodies = {}
    
class CAI3LiteParser:
    """Parser for CAI3-LITE format using structured patterns."""
    
    def __init__(self):
        """Initialize the parser with logging."""
        self.logger = logging.getLogger(__name__)
    
    def parse(self, content: str) -> Optional[CAI3LiteAST]:
        """Parse CAI3-LITE content into structured AST."""
        
        ast = CAI3LiteAST()
        
        try:
            # Basic validation - must have some CAI3 indicators
            cai3_indicators = ['#C3L', 'CAI3:', 'P:', 'T:', 'B#', 'B0:', 'B1:', 'B2:', 'B3:', 'B4:', 'B5:', 'B6:']
            if not any(indicator in content for indicator in cai3_indicators):
                self.logger.error("No CAI3-LITE indicators found in content")
                return None
            
            # Check for general truncation patterns (not just in pools)
            if content.strip().endswith('...'):
                self.logger.error("Truncation detected in content")
                return None
            
            # Parse header
            header_match = re.search(r'^(CAI3:|#C3L)\s*(\S.*)?$', content, re.MULTILINE)
            if header_match:
                ast.header = header_match.group(1).strip()  # Only capture #C3L or CAI3:, not the whole line
                
                # Extract version, python version, and filename from header
                header_line = header_match.group(0)
                header_parts = header_line.split()
                for part in header_parts[1:]:  # Skip the #C3L part
                    if part.startswith('v'):
                        ast.version = part
                    elif part.startswith('py='):
                        ast.python_version = part[3:]
                    elif part.startswith('f='):
                        ast.filename = part[2:]
            
            # Parse I: section (imports)
            i_match = re.search(r'^I:\s*(.+?)(?=^[A-Z]:|^B\d+:|^B#|^---|$)', content, re.MULTILINE | re.DOTALL)
            if i_match:
                ast.imports = i_match.group(1).strip()
            
            # Parse D: section (chain aliases/definitions) - handle multiple D: sections
            d_matches = re.findall(r'^D:\s*(.+?)(?=^[A-Z]:|^B\d+:|^B#|^---|$)', content, re.MULTILINE | re.DOTALL)
            for d_match in d_matches:
                # Process definitions (can be multiple types)
                d_content = d_match.strip()
                # Always add to table for structure analysis
                ast.table.append(f"D: {d_content}")
                
                # Also check if it's a simple chain alias (not a definition)
                if '(' not in d_content and ':' not in d_content:
                    # This is a chain alias like g0=p1.p2
                    ast.chain_aliases.update(self._parse_assignments(d_content))
            
            # Parse X: section (CID aliases or main block)
            x_match = re.search(r'^X:\s*(.+?)(?=^[A-Z]:|^B\d+:|^B#|^---|$)', content, re.MULTILINE | re.DOTALL)
            if x_match:
                # Handle special case of main block
                x_content = x_match.group(1).strip()
                if '__name__' in x_content:
                    # This is the main execution block
                    ast.table.append(f"X: {x_content}")
                else:
                    ast.cid_aliases = self._parse_assignments(x_content)
            
            # Parse P: section (pools) - CRITICAL SECTION
            p_match = re.search(r'^P:\s*(.+?)(?=^[A-Z]:|^B\d+:|^B#|^---|$)', content, re.MULTILINE | re.DOTALL)
            if p_match:
                pool_content = p_match.group(1)
                
                # Check for truncation indicators in pools specifically
                # Only consider it truncated if it ends with ellipsis without closing quotes
                # Don't just check for trailing commas - those are valid separators
                if pool_content.rstrip().endswith('...'):
                    # Check if it's actually truncated or just a pattern that looks like ellipsis
                    # Look for patterns like p5... which indicate actual truncation
                    if re.search(r'p\d+\.\.\.\s*$', pool_content):
                        self.logger.error(f"Truncated pool section detected: {pool_content[:50]}...")
                        return None
                    # Also check for values that are just ellipsis
                    if re.search(r'=\s*\.\.\.\s*(?:,|$)', pool_content):
                        self.logger.error("Truncated pool value detected") 
                        return None
                    # Check if the ellipsis is inside quotes (which would be valid)
                    # Count quotes before the ellipsis
                    before_ellipsis = pool_content[:pool_content.rfind('...')]
                    quote_count = before_ellipsis.count('"') + before_ellipsis.count("'")
                    if quote_count % 2 == 0:
                        # Even number of quotes means we're not inside a string
                        self.logger.error(f"Truncated pool section detected: {pool_content[:50]}...")
                        return None
                
                # The original check for p\d+=\.\.\. is still valid
                if re.search(r'p\d+=\.\.\.(?:\s*,|\s*$)', pool_content):
                    self.logger.error("Truncated pool value detected")
                    return None
                
                # Also check for incomplete pool definitions like p5...
                if re.search(r'p\d+\.\.\.(?:\s*,|\s*$)', pool_content):
                    self.logger.error("Truncated pool name detected")
                    return None
                
                ast.pools = self._parse_pool_assignments(pool_content)
            
            # Parse T: section (table)
            t_match = re.search(r'^T:\s*(.+?)(?=^[A-Z]:|^B\d+:|^B#|^---|$)', content, re.MULTILINE | re.DOTALL)
            if t_match:
                table_content = t_match.group(1).strip()
                if table_content:
                    ast.table.extend([item.strip() for item in table_content.split(',') if item.strip()])
            
            # Parse B# and B0-B9 sections (bodies) - CRITICAL FIX
            # This pattern now correctly handles multi-line body content including I: conditions
            body_pattern = r'^(B#[A-Za-z0-9_]+|B\d+):\s*(.+?)(?=^(?:B#[A-Za-z0-9_]+:|B\d+:|D:|X:|F:|P:|I:|T:|---|$))'
            body_matches = list(re.finditer(body_pattern, content, re.MULTILINE | re.DOTALL))
            
            for body_match in body_matches:
                body_id = body_match.group(1)
                body_content = body_match.group(2).strip()
                
                # Clean up body_id - convert B# format to just the ID
                if body_id.startswith('B#'):
                    body_id = body_id[2:]  # Remove 'B#' prefix
                elif body_id.startswith('B'):
                    body_id = body_id[1:]  # Remove 'B' prefix for numeric IDs
                
                # Body content can contain I: conditions and multi-line statements
                # No need to validate internal structure here
                ast.bodies[body_id] = body_content
            
            # Parse F: section (standalone functions) - CRITICAL FIX
            # Pattern: F:function_name#body_id or F:function_name(args)#body_id
            f_pattern = r'^F:([A-Za-z_]\w*)(?:\(([^)]*)\))?(?:#([A-Za-z0-9_]+))?$'
            for line in content.split('\n'):
                f_match = re.match(f_pattern, line.strip())
                if f_match:
                    func_name = f_match.group(1)
                    args = f_match.group(2) or ''
                    body_id = f_match.group(3)
                    
                    # Store in table with proper structure
                    func_entry = f"F:{func_name}"
                    if args:
                        func_entry += f"({args})"
                    if body_id:
                        func_entry += f"#{body_id}"
                    
                    ast.table.append(func_entry)
        
            # Additional validation - ensure we parsed something meaningful
            if not ast.pools and not ast.bodies and not ast.table:
                self.logger.error("No meaningful content parsed from CAI3-LITE")
                return None
            
            return ast
            
        except Exception as e:
            self.logger.error(f"Failed to parse CAI3-LITE: {e}")
            return None
    
    def _parse_assignments(self, content: str) -> Dict[str, str]:
        """Parse key=value assignments."""
        result = {}
        for assignment in re.finditer(r'([a-z0-9]+)=([^,\n]+)', content):
            key = assignment.group(1)
            value = assignment.group(2).strip()
            result[key] = value
        return result
    
    def _parse_pool_assignments(self, content: str) -> Dict[str, Any]:
        """Parse pool assignments with proper type preservation."""
        import ast as _ast
        result = {}
        
        # Enhanced pattern to handle various pool formats with proper separators
        # This pattern now correctly handles:
        # - Quoted strings with commas inside: p0="hello, world"
        # - Multiple values on same line: p0="a",p1="b"
        # - Values across multiple lines
        # - Values that end with commas (not truncation, just separator)
        pattern = r'(p\d+)=("(?:[^"\\]|\\.)*"|\'(?:[^\'\\]|\\.)*\'|[^,\n]+)'
        
        for match in re.finditer(pattern, content):
            pool_id = match.group(1)
            value_str = match.group(2).strip()
            
            try:
                # Try to evaluate as Python literal for proper type conversion
                value = _ast.literal_eval(value_str)
                # For string literals, we want to preserve the original quoted format
                # so that pool resolution can handle different contexts appropriately
                if isinstance(value, str):
                    result[pool_id] = value_str  # Keep original quoted format
                else:
                    result[pool_id] = value_str  # Keep original format for non-strings
            except (ValueError, SyntaxError):
                # If literal_eval fails, keep as-is for identifiers, hex values, etc.
                result[pool_id] = value_str
        
        return result

    def validate_ast(self, ast: CAI3LiteAST) -> Tuple[bool, List[str]]:
        """Validate the parsed AST for completeness and consistency."""
        errors = []
        
        # Check for required header
        if not ast.header:
            errors.append("Missing CAI3-LITE header")
        
        # Check for truncated pools
        for pool_id, value in ast.pools.items():
            # Convert to string for checking truncation markers
            value_str = str(value)
            if value_str == "<truncated>" or "..." in value_str:
                errors.append(f"Pool {pool_id} is truncated")
        
        # Check for missing pool references in table/bodies
        all_pool_refs = set()
        
        # Collect pool references from table
        for item in ast.table:
            pool_refs = re.findall(r'\b(p\d+)\b', item)
            all_pool_refs.update(pool_refs)
        
        # Collect pool references from bodies
        for body_content in ast.bodies.values():
            pool_refs = re.findall(r'\b(p\d+)\b', body_content)
            all_pool_refs.update(pool_refs)
        
        # Check if all referenced pools are defined
        defined_pools = set(ast.pools.keys())
        missing_pools = all_pool_refs - defined_pools
        
        if missing_pools:
            errors.append(f"Missing pool definitions: {', '.join(sorted(missing_pools))}")
        
        return len(errors) == 0, errors

    def extract_python_structure(self, ast: CAI3LiteAST) -> Dict[str, any]:
        """Extract high-level Python structure information from AST."""
        structure = {
            "classes": [],
            "functions": [],
            "methods": {},
            "imports": [],
            "variables": []
        }
        
        # Parse table entries to identify structure
        for item in ast.table:
            if item.startswith('C:'):
                # Class definition
                class_info = self._parse_class_entry(item, ast)
                if class_info:
                    structure["classes"].append(class_info)
            elif item.startswith('F:'):
                # Function definition
                func_info = self._parse_function_entry(item, ast)
                if func_info:
                    structure["functions"].append(func_info)
            elif item.startswith('M:'):
                # Method definition
                method_info = self._parse_method_entry(item, ast)
                if method_info:
                    class_name = method_info.get("class", "unknown")
                    if class_name not in structure["methods"]:
                        structure["methods"][class_name] = []
                    structure["methods"][class_name].append(method_info)
        
        return structure
    
    def _parse_class_entry(self, entry: str, ast: CAI3LiteAST) -> Optional[Dict]:
        """Parse a class entry from the table."""
        try:
            # Example: C:className cid=cls_abc body=B#b1
            match = re.match(r'C:(\w+)\s+cid=(\w+)(?:\s+body=B#(\w+))?', entry)
            if match:
                return {
                    "name": match.group(1),
                    "cid": match.group(2),
                    "body_id": match.group(3),
                    "body_content": ast.bodies.get(match.group(3), "") if match.group(3) else ""
                }
        except Exception as e:
            self.logger.debug(f"Failed to parse class entry '{entry}': {e}")
        return None
    
    def _parse_function_entry(self, entry: str, ast: CAI3LiteAST) -> Optional[Dict]:
        """Parse a function entry from the table."""
        try:
            # Example: F:funcName cid=fn_abc args=a,b body=B#b2
            match = re.match(r'F:(\w+)\s+cid=(\w+)(?:\s+args=([^,\s]+))?(?:\s+body=B#(\w+))?', entry)
            if match:
                return {
                    "name": match.group(1),
                    "cid": match.group(2),
                    "args": match.group(3).split(',') if match.group(3) else [],
                    "body_id": match.group(4),
                    "body_content": ast.bodies.get(match.group(4), "") if match.group(4) else ""
                }
        except Exception as e:
            self.logger.debug(f"Failed to parse function entry '{entry}': {e}")
        return None
    
    def _parse_method_entry(self, entry: str, ast: CAI3LiteAST) -> Optional[Dict]:
        """Parse a method entry from the table."""
        try:
            # Example: M:methodName cid=mth_abc class=className args=self,x body=B#b3
            match = re.match(r'M:(\w+)\s+cid=(\w+)(?:\s+class=(\w+))?(?:\s+args=([^,\s]+))?(?:\s+body=B#(\w+))?', entry)
            if match:
                return {
                    "name": match.group(1),
                    "cid": match.group(2),
                    "class": match.group(3) or "unknown",
                    "args": match.group(4).split(',') if match.group(4) else [],
                    "body_id": match.group(5),
                    "body_content": ast.bodies.get(match.group(5), "") if match.group(5) else ""
                }
        except Exception as e:
            self.logger.debug(f"Failed to parse method entry '{entry}': {e}")
        return None

    def parse_enhanced(self, content: str) -> Tuple[Optional[CAI3LiteAST], Optional[StructureInfo]]:
        """Parse CAI3-LITE content and extract structure in one pass."""
        ast = self.parse(content)
        if not ast:
            return None, None
        
        # Use the structure analyzer to extract structure
        from .cai3_structure_analyzer import CAI3StructureAnalyzer
        analyzer = CAI3StructureAnalyzer()
        structure = analyzer.analyze(ast)
        
        return ast, structure
