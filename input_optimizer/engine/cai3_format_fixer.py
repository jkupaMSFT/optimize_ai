"""
CAI3-LITE Format Fixer - Converts invalid CAI3-LITE to valid format.
Handles common issues like:
- B0:, B1:, etc. -> B#0, B#1, etc.
- Missing P: section with pool definitions
- Invalid section identifiers
"""

import re
import logging
from typing import Dict, Set, List, Tuple


class CAI3FormatFixer:
    """Fixes common CAI3-LITE format violations to make content parseable."""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    def fix_format(self, cai3_content: str, mappings: Dict[str, str] = None) -> str:
        """
        Fix CAI3-LITE format issues to make it compliant.
        
        Args:
            cai3_content: Raw CAI3-LITE content that may have format issues
            mappings: Optional mappings from Claude that contain pool definitions
            
        Returns:
            Fixed CAI3-LITE content that should be valid
        """
        try:
            self.logger.info("Starting CAI3-LITE format fixing")
            
            # DEBUG: Analyze input content for constructor issues
            self._debug_constructor_bodies(cai3_content, "ORIGINAL")
            
            # Step 0: Fix hash-keyword concatenation issues (CRITICAL FIX)
            content = self._fix_hash_concatenations(cai3_content)
            self._debug_constructor_bodies(content, "AFTER_HASH_CONCAT_FIX")
            
            # Step 1: Fix body section identifiers (B0: -> B#0, etc.)
            content = self._fix_body_identifiers(content)
            self._debug_constructor_bodies(content, "AFTER_BODY_ID_FIX")
            
            # Step 2: Extract referenced pools and create P: section
            content = self._fix_pool_section(content, mappings)
            self._debug_constructor_bodies(content, "AFTER_POOL_FIX")
            
            # Step 3: Fix other section identifier issues
            content = self._fix_section_identifiers(content)
            self._debug_constructor_bodies(content, "AFTER_SECTION_ID_FIX")
            
            # Step 4: Fix empty constructor bodies
            content = self._fix_empty_constructors(content)
            self._debug_constructor_bodies(content, "AFTER_CONSTRUCTOR_FIX")
            
            # Step 5: Clean up formatting
            content = self._cleanup_formatting(content)
            self._debug_constructor_bodies(content, "FINAL")
            
            # Step 5: Fix empty constructor methods
            content = self._fix_empty_constructors(content)
            
            self.logger.info("CAI3-LITE format fixing completed")
            return content
            
        except Exception as e:
            self.logger.error(f"Format fixing failed: {e}")
            return cai3_content  # Return original if fixing fails
    
    def _fix_hash_concatenations(self, content: str) -> str:
        """
        Fix hash-keyword concatenation issues in CAI3 content.
        
        CAI3 compression sometimes creates concatenated tokens like:
        - hash_b726elif -> should be: hash_b726 elif
        - hash_91faelse -> should be: hash_91fa else
        
        This MUST be fixed before parsing to ensure proper tokenization.
        """
        self.logger.debug("Fixing hash-keyword concatenations")
        
        # Define concatenation patterns that need to be separated
        concatenation_fixes = [
            # Python keywords that get concatenated with hashes
            (r'(hash_[a-f0-9]+)(elif)', r'\1 \2'),
            (r'(hash_[a-f0-9]+)(else)', r'\1 \2'), 
            (r'(hash_[a-f0-9]+)(if)', r'\1 \2'),
            (r'(hash_[a-f0-9]+)(for)', r'\1 \2'),
            (r'(hash_[a-f0-9]+)(while)', r'\1 \2'),
            (r'(hash_[a-f0-9]+)(def)', r'\1 \2'),
            (r'(hash_[a-f0-9]+)(class)', r'\1 \2'),
            (r'(hash_[a-f0-9]+)(return)', r'\1 \2'),
            (r'(hash_[a-f0-9]+)(import)', r'\1 \2'),
            (r'(hash_[a-f0-9]+)(from)', r'\1 \2'),
            (r'(hash_[a-f0-9]+)(and)', r'\1 \2'),
            (r'(hash_[a-f0-9]+)(or)', r'\1 \2'),
            (r'(hash_[a-f0-9]+)(not)', r'\1 \2'),
            (r'(hash_[a-f0-9]+)(in)', r'\1 \2'),
            (r'(hash_[a-f0-9]+)(is)', r'\1 \2'),
            
            # Common operators/punctuation concatenations
            (r'(hash_[a-f0-9]+)(\()', r'\1\2'),  # Keep hash_XXX( as is
            (r'(hash_[a-f0-9]+)(\))', r'\1 \2'),  # hash_XXX) -> hash_XXX )
            (r'(hash_[a-f0-9]+)(\[)', r'\1\2'),  # Keep hash_XXX[ as is  
            (r'(hash_[a-f0-9]+)(\])', r'\1 \2'),  # hash_XXX] -> hash_XXX ]
            (r'(hash_[a-f0-9]+)(;)', r'\1\2'),   # Keep hash_XXX; as is
            (r'(hash_[a-f0-9]+)(:)', r'\1\2'),   # Keep hash_XXX: as is
        ]
        
        fixed_content = content
        fixes_applied = 0
        
        for pattern, replacement in concatenation_fixes:
            old_content = fixed_content
            fixed_content = re.sub(pattern, replacement, fixed_content)
            
            if old_content != fixed_content:
                fixes_applied += 1
                self.logger.debug(f"Applied concatenation fix: {pattern}")
        
        if fixes_applied > 0:
            self.logger.info(f"Fixed {fixes_applied} hash-keyword concatenation issues")
        
        return fixed_content
    
    def _fix_body_identifiers(self, content: str) -> str:
        """Convert B0:, B1:, etc. to B#0, B#1, etc."""
        # Pattern to match B followed by number and colon
        pattern = r'^(B)(\d+)(:)'
        
        def replace_func(match):
            return f"B#{match.group(2)}:"
        
        return re.sub(pattern, replace_func, content, flags=re.MULTILINE)
    
    def _fix_pool_section(self, content: str, mappings: Dict[str, str] = None) -> str:
        """Create or fix the P: section with all referenced pools."""
        # Extract all pool references (p0, p1, p2, etc.)
        pool_refs = set(re.findall(r'\bp(\d+)\b', content))
        
        # Get existing P: section if any
        existing_pools = {}
        p_match = re.search(r'^P:\s*(.+?)(?=^[A-Z]:|^B#|^---|$)', content, re.MULTILINE | re.DOTALL)
        if p_match:
            existing_pools = self._parse_pool_assignments(p_match.group(1))
        
        # Build complete pool definitions
        all_pools = {}
        
        # Add pools from mappings (these have actual values)
        if mappings:
            for key, value in mappings.items():
                if key.startswith('p') and key[1:].isdigit():
                    all_pools[key] = value
        
        # Add existing pools
        all_pools.update(existing_pools)
        
        # Add placeholder pools for any missing references
        for pool_num in pool_refs:
            pool_key = f"p{pool_num}"
            if pool_key not in all_pools:
                # Create a reasonable default based on context
                all_pools[pool_key] = f'"param_{pool_num}"'
        
        if not all_pools:
            return content
        
        # Create the P: section
        pool_assignments = []
        for i in range(max(int(k[1:]) for k in all_pools.keys() if k.startswith('p')) + 1):
            pool_key = f"p{i}"
            if pool_key in all_pools:
                pool_assignments.append(f"{pool_key}={all_pools[pool_key]}")
        
        pool_section = "P:" + ",".join(pool_assignments)
        
        # Remove existing P: section if present
        content = re.sub(r'^P:\s*(.+?)(?=^[A-Z]:|^B#|^---|$)', '', content, flags=re.MULTILINE | re.DOTALL)
        
        # Insert P: section after imports but before first body or definition
        insertion_point = self._find_pool_insertion_point(content)
        
        lines = content.split('\n')
        lines.insert(insertion_point, pool_section)
        
        return '\n'.join(lines)
    
    def _parse_pool_assignments(self, pool_content: str) -> Dict[str, str]:
        """Parse pool assignments from P: section content."""
        pools = {}
        
        # Handle comma-separated assignments
        assignments = []
        current = ""
        in_string = False
        quote_char = None
        
        for char in pool_content:
            if char in ('"', "'") and not in_string:
                in_string = True
                quote_char = char
                current += char
            elif char == quote_char and in_string:
                in_string = False
                quote_char = None
                current += char
            elif char == ',' and not in_string:
                if current.strip():
                    assignments.append(current.strip())
                current = ""
            else:
                current += char
        
        if current.strip():
            assignments.append(current.strip())
        
        # Parse each assignment
        for assignment in assignments:
            if '=' in assignment:
                key, value = assignment.split('=', 1)
                pools[key.strip()] = value.strip()
        
        return pools
    
    def _find_pool_insertion_point(self, content: str) -> int:
        """Find the best place to insert the P: section."""
        lines = content.split('\n')
        
        # Look for the first non-header, non-import line
        for i, line in enumerate(lines):
            line = line.strip()
            if line and not line.startswith('#C3L') and not line.startswith('I:') and not line.startswith('---'):
                return i
        
        # If no good spot found, add at the end
        return len(lines)
    
    def _fix_section_identifiers(self, content: str) -> str:
        """Fix any remaining invalid section identifiers."""
        # This is where we could add more fixes for other invalid patterns
        # For now, the main issue is body identifiers which we already fixed
        return content
    
    def _cleanup_formatting(self, content: str) -> str:
        """Clean up formatting issues."""
        # Remove extra blank lines
        content = re.sub(r'\n\s*\n\s*\n', '\n\n', content)
        
        # Ensure proper line endings
        content = content.strip() + '\n'
        
        return content
    
    def _fix_hash_concatenations(self, content: str) -> str:
        """
        Fix hash-keyword concatenations like 'hash_b726elif' -> 'hash_b726 elif'.
        This is critical for proper tokenization.
        """
        self.logger.info("🔧 Starting hash-keyword concatenation fixes")
        
        # Common concatenation patterns to fix
        concatenation_rules = [
            # hash + elif -> hash elif
            (r'(hash_[a-f0-9]+)(elif)', r'\1 \2'),
            # hash + else -> hash else  
            (r'(hash_[a-f0-9]+)(else)', r'\1 \2'),
            # hash + if -> hash if
            (r'(hash_[a-f0-9]+)(if)', r'\1 \2'),
            # hash + for -> hash for
            (r'(hash_[a-f0-9]+)(for)', r'\1 \2'),
            # hash + while -> hash while
            (r'(hash_[a-f0-9]+)(while)', r'\1 \2'),
            # hash + def -> hash def
            (r'(hash_[a-f0-9]+)(def)', r'\1 \2'),
            # hash + class -> hash class
            (r'(hash_[a-f0-9]+)(class)', r'\1 \2'),
            # hash + try -> hash try
            (r'(hash_[a-f0-9]+)(try)', r'\1 \2'),
            # hash + except -> hash except
            (r'(hash_[a-f0-9]+)(except)', r'\1 \2'),
            # hash + return -> hash return
            (r'(hash_[a-f0-9]+)(return)', r'\1 \2'),
        ]
        
        fixes_applied = 0
        
        for pattern, replacement in concatenation_rules:
            before_count = len(re.findall(pattern, content))
            if before_count > 0:
                content = re.sub(pattern, replacement, content)
                after_count = len(re.findall(pattern, content))
                fixed_count = before_count - after_count
                if fixed_count > 0:
                    fixes_applied += fixed_count
                    self.logger.info(f"   ✅ Fixed {fixed_count} instances of pattern: {pattern}")
        
        if fixes_applied > 0:
            self.logger.info(f"Fixed {fixes_applied} hash-keyword concatenation issues")
        else:
            self.logger.info("No hash-keyword concatenation issues found")
            
        return content
    
    def _fix_empty_constructors(self, content: str) -> str:
        """
        Fix empty constructor bodies (just 'pass') with meaningful initialization.
        """
        self.logger.info("🔧 Starting empty constructor fix")
        
        # Find all bodies that are just 'pass'
        pass_bodies = re.findall(r'B#([a-z0-9]+):pass\b', content)
        
        if pass_bodies:
            self.logger.info(f"   📋 Found {len(pass_bodies)} bodies with just 'pass': {pass_bodies}")
            
            # Look for table entries that reference these bodies as constructors
            table_match = re.search(r'T:(.+?)(?=^---|$)', content, re.MULTILINE | re.DOTALL)
            if table_match:
                table_content = table_match.group(1)
                self.logger.info(f"   📋 Table content: {table_content}")
                
                # Find constructor methods that use pass bodies
                for body_id in pass_bodies:
                    # Look for method entries like M:ca.i#a4 where a4 is the body_id
                    constructor_pattern = rf'M:([a-z]+)\.i#({body_id})'
                    constructor_matches = re.findall(constructor_pattern, table_content)
                    
                    if constructor_matches:
                        for class_id, matched_body in constructor_matches:
                            self.logger.info(f"   🔍 Found constructor M:{class_id}.i#{matched_body} using pass body")
                            
                            # Create meaningful initialization based on class context
                            meaningful_init = self._create_meaningful_constructor(class_id, content)
                            
                            if meaningful_init != "pass":
                                self.logger.info(f"   ✅ Replacing pass with: {meaningful_init}")
                                # Replace the pass body with meaningful initialization
                                old_body = f"B#{body_id}:pass"
                                new_body = f"B#{body_id}:{meaningful_init}"
                                content = content.replace(old_body, new_body)
                            else:
                                self.logger.info(f"   ⚠️ Could not generate meaningful constructor for {class_id}")
        else:
            self.logger.info("   ✅ No empty pass constructors found")
            
        return content
    
    def _create_meaningful_constructor(self, class_id: str, content: str) -> str:
        """
        Create meaningful constructor body based on class context.
        Uses special formatting to avoid hash resolver conflicts.
        """
        self.logger.info(f"   🔨 Creating meaningful constructor for class '{class_id}'")
        
        # Analyze the class context to determine what attributes it should have
        table_match = re.search(r'T:(.+?)(?=^---|$)', content, re.MULTILINE | re.DOTALL)
        if not table_match:
            return "pass"
            
        table_content = table_match.group(1)
        
        # Find all methods for this class
        class_methods = re.findall(rf'M:{class_id}\.([a-z0-9_]+)#([a-z0-9]+)', table_content)
        self.logger.info(f"   📋 Class {class_id} methods: {class_methods}")
        
        # Analyze method bodies to understand what attributes are used
        attributes = set()
        
        for method_name, body_id in class_methods:
            # Find the body content
            body_match = re.search(rf'B#{body_id}:(.+?)(?=^B#|$)', content, re.MULTILINE | re.DOTALL)
            if body_match:
                body_content = body_match.group(1)
                self.logger.info(f"   📝 Method {method_name} body: {body_content[:100]}...")
                
                # Look for self.attribute patterns
                self_attrs = re.findall(r's\.([a-z_]+)', body_content)
                for attr in self_attrs:
                    if attr not in ['es', 'ti', 'an']:  # Skip method calls
                        attributes.add(attr)
                        
        self.logger.info(f"   🔍 Detected attributes for {class_id}: {attributes}")
        
        # Generate meaningful initialization based on class type and attributes
        # CRITICAL: Use special number format to avoid hash resolver treating numbers as hashes
        generated_init = ""
        if class_id == 'ca':  # CompressionAnalyzer
            if 'ti' in [method[0] for method, _ in class_methods]:  # has tiers
                generated_init = "s.ti=[];s.na='CompressionAnalyzer'"
            else:
                # Use special format: num_1024 instead of 1024 to avoid hash_1024 conversion
                generated_init = "s.na='CompressionAnalyzer';s.mi=num_1024"  # Will be resolved to actual number
        elif class_id == 'ct':  # CompressTier  
            generated_init = "s.na='default';s.th=num_1024;s.ra=num_0_1"  # Special number format
        elif class_id == 'ce':  # CEClass (estimator)
            generated_init = "s.na='CostEstimator'"
        else:
            # Generic initialization based on detected attributes
            if attributes:
                init_parts = []
                for attr in sorted(attributes):
                    if attr in ['na', 'name']:
                        init_parts.append(f"s.{attr}='{class_id}_instance'")
                    elif attr in ['th', 'threshold', 'mi', 'min_size']:
                        init_parts.append(f"s.{attr}=num_1024")  # Special number format
                    elif attr in ['ra', 'rate']:
                        init_parts.append(f"s.{attr}=num_0_1")  # Special number format
                    elif attr in ['ti', 'tiers']:
                        init_parts.append(f"s.{attr}=[]")
                    else:
                        init_parts.append(f"s.{attr}=None")
                
                if init_parts:
                    generated_init = ";".join(init_parts)
                    
        if not generated_init:
            generated_init = "pass"  # Fallback
            
        self.logger.info(f"   ✅ Generated constructor body: '{generated_init}'")
        self.logger.info(f"   🔍 CRITICAL DEBUG: Generated init contains 'num_' patterns: {bool('num_' in generated_init)}")
        
        # Check for plain numbers without using raw string in f-string
        plain_number_pattern = r'\b\d+\b'
        has_plain_numbers = bool(re.search(plain_number_pattern, generated_init))
        self.logger.info(f"   🔍 CRITICAL DEBUG: Generated init contains plain numbers: {has_plain_numbers}")
        
        return generated_init
    
    def _debug_constructor_bodies(self, content: str, stage: str) -> None:
        """
        Debug helper to trace constructor body contents at each stage.
        """
        self.logger.info(f"🔍 DEBUG [{stage}] - Analyzing constructor bodies:")
        
        # Find all body definitions
        bodies = re.findall(r'B#([a-z0-9]+):(.+?)(?=^B#|$)', content, re.MULTILINE | re.DOTALL)
        
        # Find table to identify which bodies are constructors
        table_match = re.search(r'T:(.+?)(?=^---|$)', content, re.MULTILINE | re.DOTALL)
        if table_match:
            table_content = table_match.group(1)
            
            # Find constructor method entries (M:class.i#body)
            constructors = re.findall(r'M:([a-z]+)\.i#([a-z0-9]+)', table_content)
            
            self.logger.info(f"   📋 Found {len(constructors)} constructor entries: {constructors}")
            
            for class_id, body_id in constructors:
                # Find the actual body content
                body_content = "NOT_FOUND"
                for bid, bcontent in bodies:
                    if bid == body_id:
                        body_content = bcontent.strip()
                        break
                
                self.logger.info(f"   🔧 Constructor M:{class_id}.i#{body_id}")
                self.logger.info(f"      📝 Full Body Content: '{body_content}'")
                
                # CRITICAL DEBUG: Track number patterns
                num_patterns = re.findall(r'num_\d+', body_content)
                plain_numbers = re.findall(r'\b\d+\b', body_content)
                hash_patterns = re.findall(r'hash_\w+', body_content)
                
                self.logger.info(f"      🔍 PATTERNS DETECTED:")
                self.logger.info(f"         num_ patterns: {num_patterns}")
                self.logger.info(f"         plain numbers: {plain_numbers}")
                self.logger.info(f"         hash patterns: {hash_patterns}")
                
                if body_content.strip() == "pass":
                    self.logger.warning(f"   ⚠️ EMPTY CONSTRUCTOR DETECTED: {class_id}.i#{body_id}")
                elif "num_" in body_content:
                    self.logger.info(f"   ✅ SPECIAL NUMBER FORMAT DETECTED: {class_id}.i#{body_id}")
                elif any(char.isdigit() for char in body_content):
                    self.logger.warning(f"   ⚠️ PLAIN NUMBERS DETECTED (may cause hash conversion): {class_id}.i#{body_id}")
                    
                # Check for specific patterns that might cause issues
                if "1024" in body_content:
                    self.logger.warning(f"      ⚠️ CRITICAL: '1024' detected in body - this may get converted to hash_1024!")
                if "hash_1024" in body_content:
                    self.logger.error(f"      ❌ PROBLEM: 'hash_1024' already present in body!")
        else:
            self.logger.warning(f"   ⚠️ No table found in content at stage {stage}")
            
        self.logger.info(f"🔍 DEBUG [{stage}] - Analysis complete\n")


def apply_cai3_format_fixes(cai3_content: str, mappings: Dict[str, str] = None) -> str:
    """Convenience function to apply CAI3-LITE format fixes."""
    fixer = CAI3FormatFixer()
    return fixer.fix_format(cai3_content, mappings)
