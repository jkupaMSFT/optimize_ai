"""CAI3-LITE Grammar Parser using simple regex-based approach."""

import re
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
import logging

@dataclass
class CAI3LiteAST:
    """Structured representation of CAI3-LITE content."""
    header: str
    chain_aliases: Dict[str, str]  # D: section
    cid_aliases: Dict[str, str]    # X: section
    pools: Dict[str, str]          # P: section
    table: List[str]               # T: section
    bodies: Dict[str, str]         # B# sections
    
class CAI3LiteParser:
    """Parser for CAI3-LITE format using structured patterns."""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    def parse(self, content: str) -> Optional[CAI3LiteAST]:
        """Parse CAI3-LITE content into structured AST."""
        
        ast = CAI3LiteAST(
            header="",
            chain_aliases={},
            cid_aliases={},
            pools={},
            table=[],
            bodies={}
        )
        
        try:
            # Basic validation - must have some CAI3 indicators
            cai3_indicators = ['#C3L', 'CAI3:', 'P:', 'T:', 'B#']
            if not any(indicator in content for indicator in cai3_indicators):
                self.logger.error("No CAI3-LITE indicators found in content")
                return None
            
            # Check for general truncation patterns (not just in pools)
            if re.search(r'\.\.\.$', content.strip()) or '...' in content:
                self.logger.error("Truncation detected in content")
                return None
            
            # Validate section format - reject unknown sections
            valid_sections = ['D:', 'X:', 'P:', 'T:', 'B#', 'CAI3:']  # Added CAI3: to valid sections
            lines = content.split('\n')
            for line in lines:
                line = line.strip()
                if line and ':' in line and not line.startswith('#'):
                    section_prefix = line.split(':')[0] + ':'
                    if section_prefix not in valid_sections and not line.startswith('B#'):
                        if section_prefix not in ['---:', '']:  # Allow --- separator and empty lines
                            self.logger.error(f"Invalid section found: {section_prefix}")
                            return None
            
            # Parse header
            header_match = re.search(r'^(CAI3:|#C3L)\s*(\S.*)?', content, re.MULTILINE)
            if header_match:
                ast.header = header_match.group(0).strip()
            
            # Parse D: section (chain aliases)
            d_match = re.search(r'^D:(.+?)(?=^[A-Z]:|^B#|^---|$)', content, re.MULTILINE | re.DOTALL)
            if d_match:
                ast.chain_aliases = self._parse_assignments(d_match.group(1))
            
            # Parse X: section (CID aliases)
            x_match = re.search(r'^X:(.+?)(?=^[A-Z]:|^B#|^---|$)', content, re.MULTILINE | re.DOTALL)
            if x_match:
                ast.cid_aliases = self._parse_assignments(x_match.group(1))
            
            # Parse P: section (pools) - CRITICAL SECTION
            p_match = re.search(r'^P:(.+?)(?=^[A-Z]:|^B#|^---|$)', content, re.MULTILINE | re.DOTALL)
            if p_match:
                pool_content = p_match.group(1)
                
                # Check for truncation indicators in pools specifically
                if '...' in pool_content or pool_content.rstrip().endswith('p'):
                    self.logger.error(f"Truncated pool section detected: {pool_content[:50]}...")
                    return None
                
                ast.pools = self._parse_pool_assignments(pool_content)
            
            # Parse T: section (table)
            t_match = re.search(r'^T:(.+?)(?=^B#|^---|$)', content, re.MULTILINE | re.DOTALL)
            if t_match:
                table_content = t_match.group(1).strip()
                if table_content:  # Only split if not empty
                    ast.table = [item.strip() for item in table_content.split(',') if item.strip()]
            
            # Parse B# sections (bodies)
            for body_match in re.finditer(r'^B#([a-z0-9]+):(.+?)(?=^B#|$)', content, re.MULTILINE | re.DOTALL):
                body_id = body_match.group(1)
                body_content = body_match.group(2).strip()
                ast.bodies[body_id] = body_content
            
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
    
    def _parse_pool_assignments(self, content: str) -> Dict[str, str]:
        """Parse pool assignments with proper string handling."""
        result = {}
        
        # Enhanced pattern to handle various pool formats
        # Supports: p0="string", p1=identifier, p2=#hex, p3=123, etc.
        pattern = r'(p\d+)=("(?:[^"\\]|\\.)*"|\'(?:[^\'\\]|\\.)*\'|#[a-fA-F0-9]+|[^,\n]+)'
        
        for match in re.finditer(pattern, content):
            pool_id = match.group(1)
            value = match.group(2).strip()
            
            # Remove outer quotes if present, but preserve inner content
            if (value.startswith('"') and value.endswith('"')) or \
               (value.startswith("'") and value.endswith("'")):
                value = value[1:-1]
            
            result[pool_id] = value
        
        return result

    def validate_ast(self, ast: CAI3LiteAST) -> Tuple[bool, List[str]]:
        """Validate the parsed AST for completeness and consistency."""
        errors = []
        
        # Check for required header
        if not ast.header:
            errors.append("Missing CAI3-LITE header")
        
        # Check for truncated pools
        for pool_id, value in ast.pools.items():
            if value == "<truncated>" or "..." in value:
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
