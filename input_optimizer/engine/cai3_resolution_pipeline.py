"""
Unified resolution pipeline for CAI3 translation.
Integrates hash resolution, pool resolution, and AST transformation.
"""

import re
import ast
from typing import Dict, Any, List, Optional
from .hash_resolver import HashResolver
import logging

class CAI3ResolutionPipeline:
    """Unified pipeline for resolving all CAI3 references."""
    
    def __init__(self, hash_mappings: Dict[str, str], pools: Dict[str, Any], variables: Dict[str, str] = None):
        self.hash_resolver = HashResolver(hash_mappings)
        self.pools = pools
        self.variables = variables or {}
        self.logger = logging.getLogger(__name__)
    
    def resolve_content(self, content: str) -> str:
        """Apply all resolutions in the correct order."""
        self.logger.info(f"🔄 Starting content resolution...")
        self.logger.info(f"📝 Input content: {content[:200]}...")
        
        # Step 0: Resolve special number references (before hash resolution)
        self.logger.info("🔍 Step 0: Resolving special number references...")
        content = self._resolve_special_numbers(content)
        self.logger.info(f"✅ After number resolution: {content[:200]}...")
        
        # Step 1: Resolve hash references
        self.logger.info("🔍 Step 1: Resolving hash references...")
        content = self._resolve_hashes(content)
        self.logger.info(f"✅ After hash resolution: {content[:200]}...")
        
        # Step 2: Resolve pool references
        self.logger.info("🔍 Step 2: Resolving pool references...")
        content = self._resolve_pools(content)
        self.logger.info(f"✅ After pool resolution: {content[:200]}...")
        
        # Step 3: Resolve variable references
        self.logger.info("🔍 Step 3: Resolving variable references...")
        content = self._resolve_variables(content)
        self.logger.info(f"✅ After variable resolution: {content[:200]}...")
        
        # Step 4: Fix CAI3 syntax
        self.logger.info("🔍 Step 4: Fixing CAI3 syntax...")
        content = self._fix_cai3_syntax(content)
        self.logger.info(f"✅ After syntax fixes: {content[:200]}...")
        
        self.logger.info("🎉 Content resolution complete!")
        return content
    
    def _resolve_special_numbers(self, content: str) -> str:
        """
        Resolve special number references like num_1024 -> 1024.
        This prevents the hash resolver from treating numbers as hash references.
        """
        self.logger.info("🔢 Resolving special number references...")
        self.logger.info(f"   📝 Input content: {content}")
        
        # CRITICAL DEBUG: Check for existing patterns before resolution
        existing_num_patterns = re.findall(r'num_\w+', content)
        existing_plain_numbers = re.findall(r'\b\d+\b', content)
        existing_hash_patterns = re.findall(r'hash_\w+', content)
        
        self.logger.info(f"   🔍 BEFORE RESOLUTION:")
        self.logger.info(f"      num_ patterns found: {existing_num_patterns}")
        self.logger.info(f"      plain numbers found: {existing_plain_numbers}")
        self.logger.info(f"      hash patterns found: {existing_hash_patterns}")
        
        # Define special number patterns
        number_patterns = [
            # num_1024 -> 1024
            (r'num_(\d+)', r'\1'),
            # num_0_1 -> 0.1  
            (r'num_(\d+)_(\d+)', r'\1.\2'),
            # num_0_01 -> 0.01
            (r'num_0_0(\d+)', r'0.0\1'),
        ]
        
        numbers_resolved = 0
        
        for pattern, replacement in number_patterns:
            matches = re.findall(pattern, content)
            if matches:
                old_content = content
                content = re.sub(pattern, replacement, content)
                if old_content != content:
                    numbers_resolved += len(matches)
                    self.logger.info(f"   📊 Resolved {len(matches)} instances of pattern: {pattern}")
                    self.logger.info(f"      ✅ Example: {matches[0]} -> {re.sub(pattern, replacement, f'num_{matches[0]}' if pattern.count('_') == 1 else f'num_{matches[0][0]}_{matches[0][1]}')}")
        
        # CRITICAL DEBUG: Check patterns after resolution
        final_num_patterns = re.findall(r'num_\w+', content)
        final_plain_numbers = re.findall(r'\b\d+\b', content)
        final_hash_patterns = re.findall(r'hash_\w+', content)
        
        self.logger.info(f"   🔍 AFTER RESOLUTION:")
        self.logger.info(f"      num_ patterns remaining: {final_num_patterns}")
        self.logger.info(f"      plain numbers now present: {final_plain_numbers}")
        self.logger.info(f"      hash patterns present: {final_hash_patterns}")
        
        if "1024" in final_plain_numbers:
            self.logger.warning(f"   ⚠️ CRITICAL: Plain number '1024' is now in content - this may get converted to hash_1024 later!")
        
        self.logger.info(f"   📝 Output content: {content}")
        
        if numbers_resolved > 0:
            self.logger.info(f"✅ Resolved {numbers_resolved} special number references")
        else:
            self.logger.info("ℹ️ No special number references found")
            
        return content
    
    def _resolve_hashes(self, content: str) -> str:
        """Resolve all hash references in content with proper Python string quoting."""
        self.logger.info("🔍 Starting hash resolution...")
        self.logger.info(f"   📝 Input content: {content}")
        
        if not self.hash_resolver or not self.hash_resolver.mappings:
            self.logger.warning("⚠️ No hash mappings available for resolution!")
            return content
        
        # CRITICAL DEBUG: Check for plain numbers that might get converted to hashes
        plain_numbers = re.findall(r'\b\d+\b', content)
        hash_patterns_before = re.findall(r'hash_\w+', content)
        
        self.logger.info(f"   🔍 BEFORE HASH RESOLUTION:")
        self.logger.info(f"      plain numbers found: {plain_numbers}")
        self.logger.info(f"      hash patterns found: {hash_patterns_before}")
        
        if "1024" in plain_numbers:
            self.logger.warning(f"   ⚠️ CRITICAL: Plain number '1024' detected - will monitor for unwanted conversion!")
        
        # Pattern to match hash references - FIXED: Use non-hex lookahead instead of word lookahead
        # Also ensure we only match actual hash_ prefixed tokens, not plain numbers
        hash_pattern = r'\b(hash_[a-f0-9]+)\b'
        self.logger.info(f"   📋 Using hash pattern: {hash_pattern}")
        
        resolved_count = 0
        unresolved_count = 0
        
        def replace_hash(match):
            nonlocal resolved_count, unresolved_count
            hash_ref = match.group(1)
            resolved = self.hash_resolver.resolve(hash_ref, 'load')
            
            self.logger.debug(f"   🔄 Processing: {hash_ref} → {resolved}")
            
            if resolved != hash_ref and not resolved.startswith('UNRESOLVED_'):
                resolved_count += 1
                self.logger.debug(f"✅ Resolved {hash_ref} → {resolved}")
                
                # CONTEXT-AWARE FIX: Only quote if used as dictionary key or string literal
                context_quoted = self._get_context_aware_quoted_value(resolved, hash_ref, content, match)
                self.logger.debug(f"🔧 Final value: {hash_ref} → {context_quoted}")
                return context_quoted
            else:
                unresolved_count += 1
                self.logger.warning(f"❌ Failed to resolve {hash_ref}")
                return resolved
        
        # Apply hash resolution
        result = re.sub(hash_pattern, replace_hash, content)
        
        # CRITICAL DEBUG: Check if any plain numbers got converted to hashes
        hash_patterns_after = re.findall(r'hash_\w+', result)
        plain_numbers_after = re.findall(r'\b\d+\b', result)
        
        self.logger.info(f"   🔍 AFTER HASH RESOLUTION:")
        self.logger.info(f"      hash patterns now: {hash_patterns_after}")
        self.logger.info(f"      plain numbers now: {plain_numbers_after}")
        
        # Check if 1024 got converted to hash_1024
        if "hash_1024" in result and "hash_1024" not in content:
            self.logger.error(f"   ❌ CRITICAL BUG: Plain number '1024' was converted to 'hash_1024' during hash resolution!")
            self.logger.error(f"   🔍 This should NOT happen with our hash pattern: {hash_pattern}")
        
        self.logger.info(f"📊 Hash resolution: {resolved_count} resolved, {unresolved_count} failed")
        self.logger.info(f"   📝 Output content: {result}")
        
        return result
    
    def _resolve_pools(self, content: str) -> str:
        """Resolve pool references with context-aware quoting - FIXED pattern matching."""
        if not self.pools:
            self.logger.warning("⚠️ No pools to resolve")
            return content
        
        self.logger.info(f"🔄 Resolving {len(self.pools)} pool references...")
        
        # Sort by key length (longest first) to avoid partial replacements
        sorted_pools = sorted(self.pools.items(), key=lambda x: len(x[0]), reverse=True)
        
        for pool_id, value in sorted_pools:
            # Use word boundary pattern to avoid partial matches
            pattern = rf'\b{re.escape(pool_id)}\b'
            
            # Find all matches with context
            matches = list(re.finditer(pattern, content))
            
            if matches:
                self.logger.info(f"   📋 Found {len(matches)} occurrences of {pool_id}")
                
            # Replace each match with context-aware resolution
            for match in reversed(matches):  # Reverse to maintain positions
                resolved_value = self._resolve_pool_value_with_context(
                    pool_id, value, content, match
                )
                content = content[:match.start()] + resolved_value + content[match.end():]
                
        return content
    
    def _resolve_pool_value_with_context(self, pool_id: str, value: str, context: str, match) -> str:
        """Resolve pool value with context-aware quoting for dictionary keys and string literals."""
        # Get surrounding context
        start = max(0, match.start() - 30)
        end = min(len(context), match.end() + 30)
        surrounding = context[start:end]
        
        self.logger.debug(f"Context for {pool_id}: ...{surrounding}...")
        
        # If the value is already quoted, preserve it as-is
        if ((value.startswith('"') and value.endswith('"')) or
            (value.startswith("'") and value.endswith("'"))):
            self.logger.debug(f"   ✅ Already quoted string literal, preserving: {value}")
            return value
        
        # Check if it's a Python built-in/keyword that should NEVER be quoted
        python_builtins = {
            'dataclass', 'frozen', 'Path', 'datetime', 'time', 'json', 
            'pandas', 'numpy', 'os', 'sys', 'pathlib', 'logging',
            'True', 'False', 'None', 'int', 'str', 'dict', 'list',
            'tuple', 'set', 'float', 'bool', 'len', 'range', 'sum',
            'max', 'min', 'abs', 'round', 'print', 'type', 'isinstance',
            'error', 'data'  # Common variable names that shouldn't be quoted
        }
        
        clean_value = str(value).strip('\'"')
        
        if clean_value in python_builtins:
            self.logger.debug(f"   ✅ Python built-in/keyword, never quote: {clean_value}")
            return clean_value
        
        # Numbers should never be quoted
        if re.match(r'^[\d\.\-\+e]+$', clean_value):
            self.logger.debug(f"   ✅ Numeric value, never quote: {clean_value}")
            return clean_value
        
        # CONTEXT-BASED QUOTING LOGIC:
        
        # Check if used as dictionary key: {key: or [key]
        # FIXED: Handle cases where there are already quoted keys in the dictionary
        dict_key_patterns = [
            rf'\{{\s*{re.escape(pool_id)}\s*:',           # {pool_id:
            rf'\{{\s*"[^"]*"\s*:\s*[^,}}]*,\s*{re.escape(pool_id)}\s*:',  # {"key":val,pool_id:
            rf',\s*{re.escape(pool_id)}\s*:',             # ,pool_id: (anywhere in dict)
            rf'\[\s*{re.escape(pool_id)}\s*\]',           # [pool_id]
        ]
        
        for pattern in dict_key_patterns:
            if re.search(pattern, surrounding):
                self.logger.debug(f"   ✅ Used as dictionary key, quoting: \"{clean_value}\"")
                return f'"{clean_value}"'
        
        # Check if used in string comparison context: in, ==, !=
        string_comparison_patterns = [
            rf'{re.escape(pool_id)}\s+not\s+in\s+',      # pool_id not in
            rf'{re.escape(pool_id)}\s+in\s+',            # pool_id in  
            rf'if\s+{re.escape(pool_id)}\s*==',          # if pool_id ==
            rf'elif\s+{re.escape(pool_id)}\s*==',        # elif pool_id ==
            rf'==\s*{re.escape(pool_id)}',               # == pool_id
            rf'!=\s*{re.escape(pool_id)}',               # != pool_id
            rf'return\s+{re.escape(pool_id)}\s*$',       # return pool_id
            rf'return\s+{re.escape(pool_id)}\s*;',       # return pool_id;
        ]
        
        for pattern in string_comparison_patterns:
            if re.search(pattern, surrounding):
                self.logger.debug(f"   ✅ Used in string comparison, quoting: \"{clean_value}\"")
                return f'"{clean_value}"'
        
        # Check for file paths or strings with special characters - should be quoted
        if ('/' in clean_value or '\\' in clean_value or 
            ' ' in clean_value or '-' in clean_value or '_' in clean_value):
            self.logger.debug(f"   ✅ File path or special string, quoting: \"{clean_value}\"")
            return f'"{clean_value}"'
        
        # Default: if it's a simple identifier used in other contexts (assignments, function calls, etc.)
        # don't quote it - it's likely a variable name or attribute
        self.logger.debug(f"   ✅ Used as identifier/variable, not quoting: {clean_value}")
        return clean_value
    
    def _is_python_identifier(self, name: str) -> bool:
        """Check if a string is a valid Python identifier."""
        if not name:
            return False
        
        # Must start with letter or underscore
        if not (name[0].isalpha() or name[0] == '_'):
            return False
        
        # Rest must be alphanumeric or underscore
        return all(c.isalnum() or c == '_' for c in name[1:])
    
    def _resolve_variables(self, content: str) -> str:
        """Resolve variable references using the variables mapping."""
        if not self.variables:
            self.logger.warning("⚠️ No variable mappings available for resolution!")
            return content
        
        self.logger.info(f"🔄 Resolving {len(self.variables)} variable references...")
        
        # Sort by key length (longest first) to avoid partial replacements
        sorted_variables = sorted(self.variables.items(), key=lambda x: len(x[0]), reverse=True)
        
        for var_id, value in sorted_variables:
            # Use word boundary pattern to avoid partial matches
            pattern = rf'\b{re.escape(var_id)}\b'
            
            # Find all matches with context
            matches = list(re.finditer(pattern, content))
            
            if matches:
                self.logger.info(f"   📋 Found {len(matches)} occurrences of {var_id}")
                
            # Replace each match - only quote if clearly a string literal
            for match in reversed(matches):  # Reverse to maintain positions
                # Only quote file paths or strings with special characters
                if ('/' in value or '\\' in value or ' ' in value or '-' in value):
                    quoted_value = f'"{value}"'
                else:
                    quoted_value = value
                content = content[:match.start()] + quoted_value + content[match.end():]
                
        return content
    
    def _fix_cai3_syntax(self, content: str) -> str:
        """Fix CAI3 syntax issues - FIXED to prevent over-aggressive changes."""
        self.logger.info(f"🔧 Starting CAI3 syntax fixing...")
        
        # CRITICAL: Check if content is still in CAI3 format
        cai3_markers = ['#C3L', 'CAI3:', 'P:', 'T:', 'B#', 'I:', 'D:', 'X:']
        if any(marker in content for marker in cai3_markers):
            self.logger.info("🚨 Content appears to be in CAI3 format - SKIPPING syntax fixes")
            return content
        
        original_content = content
        
        # Remove the problematic "fix_missing_for_keyword" pattern entirely
        # This was causing "for for k in r:" issues
        
        # Only apply safe, necessary fixes:
        
        # 1. Fix semicolon-separated statements
        def fix_semicolon_statements(content):
            """Convert semicolon-separated statements to proper Python lines."""
            lines = []
            for line in content.split('\n'):
                if ';' in line and not line.strip().startswith('#'):
                    # Split on semicolons and clean up
                    statements = [stmt.strip() for stmt in line.split(';') if stmt.strip()]
                    
                    # Handle special case where for loop is followed by assignment
                    processed_statements = []
                    for stmt in statements:
                        # If this statement starts with 'for' and contains an assignment
                        if stmt.startswith('for ') and '=' in stmt and ':' in stmt:
                            # Split the for loop from the assignment
                            colon_pos = stmt.find(':')
                            for_part = stmt[:colon_pos + 1]
                            rest = stmt[colon_pos + 1:].strip()
                            
                            processed_statements.append(for_part)
                            if rest:  # Add the rest as a separate statement
                                processed_statements.append(rest)
                        # Handle if statements that get concatenated with assignments
                        elif stmt.startswith('if ') and ':' in stmt:
                            # Split if statement from any following statements
                            colon_pos = stmt.find(':')
                            # Check if there's content after the colon (not just a condition)
                            after_colon = stmt[colon_pos + 1:].strip()
                            if after_colon and not after_colon.startswith('\n'):
                                # This has a statement after the colon, split it
                                if_part = stmt[:colon_pos + 1]
                                processed_statements.append(if_part)
                                # Process the part after colon as indented content
                                processed_statements.append(f"    {after_colon}")
                            else:
                                processed_statements.append(stmt)
                        else:
                            processed_statements.append(stmt)
                    
                    lines.extend(processed_statements)
                else:
                    lines.append(line)
            return '\n'.join(lines)
        
        content = fix_semicolon_statements(content)
        
        # 2. Fix missing colons on control structures and clean up assignments
        def fix_missing_colons_and_assignments(content):
            """Add missing colons to if, for, while, etc. and fix assignments."""
            lines = []
            for line in content.split('\n'):
                stripped = line.strip()
                
                # Check if it's a control structure missing a colon
                if any(stripped.startswith(kw) for kw in ['if ', 'elif ', 'for ', 'while ', 'try', 'except', 'finally', 'with ']):
                    if not stripped.endswith(':') and ' in ' in stripped:
                        # Add colon
                        line = line.rstrip() + ':'
                
                # Fix assignment statements (add spaces around =)
                if '=' in stripped and not any(op in stripped for op in ['==', '!=', '<=', '>=']):
                    # Simple assignment - add spaces
                    line = re.sub(r'([a-zA-Z_]\w*)\s*=\s*([^=])', r'\1 = \2', line)
                
                lines.append(line)
            return '\n'.join(lines)
        
        content = fix_missing_colons_and_assignments(content)
        
        # 3. Fix malformed dictionary returns and add quotes to dictionary keys
        def fix_return_dict(match):
            return_content = match.group(1).strip()
            if '"' in return_content and ':' in return_content:
                return f'return {{{return_content}}}'
            elif ':' in return_content and '{' in return_content:
                # This is a dictionary without proper quotes
                # Add quotes around unquoted keys
                return f'return {{{return_content}}}'
            else:
                return f'return {return_content}'
        
        content = re.sub(r'return\s+([^{\n][^}\n]+)$', fix_return_dict, content, flags=re.MULTILINE)
        
        # 3b. Fix dictionary keys that need quotes
        def fix_dict_keys(content):
            """Add quotes around dictionary keys that need them."""
            # Pattern: {key:value,key2:value2} where keys are unquoted identifiers
            def quote_dict_keys(match):
                dict_content = match.group(1)
                # Split by commas but respect nesting
                items = []
                current_item = ""
                depth = 0
                
                for char in dict_content:
                    if char in '({[':
                        depth += 1
                    elif char in ')}]':
                        depth -= 1
                    elif char == ',' and depth == 0:
                        if current_item.strip():
                            items.append(current_item.strip())
                        current_item = ""
                        continue
                    current_item += char
                
                if current_item.strip():
                    items.append(current_item.strip())
                
                # Process each key:value pair
                quoted_items = []
                for item in items:
                    if ':' in item:
                        key, value = item.split(':', 1)
                        key = key.strip()
                        value = value.strip()
                        
                        # Quote the key if it's not already quoted and is an identifier
                        if not (key.startswith('"') and key.endswith('"')) and not (key.startswith("'") and key.endswith("'")):
                            if key.replace('_', '').replace('-', '').isalnum():
                                key = f'"{key}"'
                        
                        quoted_items.append(f'{key}: {value}')
                    else:
                        quoted_items.append(item)
                
                return '{' + ', '.join(quoted_items) + '}'
            
            # Apply to dictionary patterns
            content = re.sub(r'\{([^{}]+)\}', quote_dict_keys, content)
            return content
        
        content = fix_dict_keys(content)
        
        # 4. Generate meaningful content for control blocks
        def fix_empty_blocks(content):
            """Generate meaningful content for control blocks instead of pass."""
            lines = content.split('\n')
            result_lines = []
            
            for i, line in enumerate(lines):
                result_lines.append(line)
                
                # If this line is a control structure that ends with ':'
                stripped = line.strip()
                if stripped.endswith(':'):
                    # Check if the next line is another control structure or end of file
                    next_line = lines[i + 1] if i + 1 < len(lines) else None
                    expected_indent = len(line) - len(line.lstrip()) + 4
                    
                    if not next_line or not next_line.strip() or not next_line.startswith(' ' * expected_indent):
                        # This block is empty, generate meaningful content
                        
                        if stripped.startswith('for '):
                            # For loops - add a basic operation
                            if 'in ' in stripped:
                                var_name = stripped.split()[1]
                                result_lines.append(' ' * expected_indent + f'print(f"Processing: {{{var_name}}}")')
                            else:
                                result_lines.append(' ' * expected_indent + 'continue')
                        
                        elif stripped.startswith('if ') or stripped.startswith('elif '):
                            # If statements - add a basic operation based on condition
                            if '==' in stripped or '!=' in stripped or '<' in stripped or '>' in stripped:
                                result_lines.append(' ' * expected_indent + '# Condition met - add specific logic here')
                                result_lines.append(' ' * expected_indent + 'return True')
                            else:
                                result_lines.append(' ' * expected_indent + 'return True')
                        
                        elif stripped.startswith('while '):
                            # While loops - add break to prevent infinite loop
                            result_lines.append(' ' * expected_indent + '# Add loop logic here')
                            result_lines.append(' ' * expected_indent + 'break')
                        
                        elif stripped.startswith('def '):
                            # Method definitions - add meaningful return
                            if '__init__' in stripped:
                                result_lines.append(' ' * expected_indent + '# Initialize instance variables')
                                result_lines.append(' ' * expected_indent + 'super().__init__()')
                            elif 'get_' in stripped.lower():
                                result_lines.append(' ' * expected_indent + 'return self._value')
                            elif 'set_' in stripped.lower():
                                result_lines.append(' ' * expected_indent + 'self._value = value')
                            else:
                                result_lines.append(' ' * expected_indent + '# Implement method logic')
                                result_lines.append(' ' * expected_indent + 'return None')
                        
                        elif stripped.startswith('class '):
                            # Class definitions - should not be empty in normal cases
                            result_lines.append(' ' * expected_indent + 'pass')
                        
                        else:
                            # Default case - use pass for other structures
                            result_lines.append(' ' * expected_indent + 'pass')
            
            return '\n'.join(result_lines)
        
        content = fix_empty_blocks(content)
        
        # 5. Fix try-except blocks
        content = re.sub(r'try:\{([^}]+)\}except\s*\(([^)]+)\):\{([^}]+)\}',
                         lambda m: f'try:\n    {m.group(1)}\nexcept {m.group(2)}:\n    {m.group(3)}',
                         content)
        
        # Log changes made
        if content != original_content:
            self.logger.info("✅ Applied syntax fixes")
        else:
            self.logger.info("ℹ️ No syntax fixes needed")
        
        return content
    
    def _log_problematic_patterns(self, content: str) -> None:
        """Log all problematic syntax patterns found in content."""
        patterns = {
            'incomplete_dicts': r'\{[^{}]*:[^{}]*(?:\s*$|\s*\n)',
            'orphaned_closing_braces': r'[^{]*}(?![^{]*{)',
            'malformed_else': r'else:\{[^}]*\}',
            'missing_dict_quotes': r'\{[^{}]*:\s*[a-zA-Z_][a-zA-Z0-9_]*[^,}\s]*\}',
            'incomplete_returns': r'return\s*\{[^}]*(?:\s*$|\s*\n)',
            'orphaned_else_braces': r'\}else:',
            'malformed_conditions': r'\([^)]+\):\{[^}]*\}',
            'incomplete_config_dicts': r'\{[^{}]*"[^{}]*:\s*[^,}]*(?:\s*$|\s*\n)',
            'missing_closing_braces': r'\{[^{}]*:[^{}]*$',
            'double_closing_braces': r'}}',
            'compound_else_statements': r'[^:\s]+else:',
            'malformed_try_blocks': r'try:\{[^}]*\}',
            'ternary_operators': r'\([^)]+\)\?[^:]+:[^,\s}]+',
            'for_loop_braces': r'for [^{]+:\{[^}]+\}',
            'semicolon_statements': r';(?=\s*[a-zA-Z_])',
            'string_concat_issues': r'[a-zA-Z_][a-zA-Z0-9_]*\+_[a-zA-Z0-9_]+\.json'
        }
        
        self.logger.info("🔍 COMPREHENSIVE PATTERN ANALYSIS:")
        for pattern_name, pattern in patterns.items():
            matches = re.findall(pattern, content, re.MULTILINE)
            if matches:
                self.logger.info(f"   ❌ Found {len(matches)} instances of {pattern_name}:")
                for i, match in enumerate(matches[:3]):  # Show first 3 matches
                    self.logger.info(f"      {i+1}: '{match[:100]}{'...' if len(match) > 100 else ''}'")
                if len(matches) > 3:
                    self.logger.info(f"      ... and {len(matches) - 3} more")
            else:
                self.logger.info(f"   ✅ No {pattern_name} found")
        
        # Check for specific problematic lines
        lines = content.split('\n')
        problematic_lines = []
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            if any([
                stripped.endswith('else:{') and not stripped.startswith('else:'),
                stripped.count('{') != stripped.count('}') and ('{' in stripped or '}' in stripped),
                'return {' in stripped and not stripped.endswith('}'),
                '}else:' in stripped,
                stripped.endswith(':') and '{' in stripped and '}' not in stripped
            ]):
                problematic_lines.append((i, line))
        
        if problematic_lines:
            self.logger.info(f"🚨 Found {len(problematic_lines)} problematic lines:")
            for line_num, line in problematic_lines[:5]:  # Show first 5
                self.logger.info(f"   Line {line_num}: '{line.strip()}'")
            if len(problematic_lines) > 5:
                self.logger.info(f"   ... and {len(problematic_lines) - 5} more problematic lines")
    
        return content
    
    def _log_problematic_patterns(self, content: str) -> None:
        """Log comprehensive analysis of problematic patterns in the content."""
        self.logger.info("🔍 COMPREHENSIVE PATTERN ANALYSIS:")
        
        patterns = {
            'incomplete_dicts': r'\{[^{}]*:[^{}]*[^}]$',
            'orphaned_closing_braces': r'^\s*\}\s*$',
            'malformed_else': r'[a-zA-Z_][a-zA-Z0-9_]*else:',
            'missing_for_keyword': r'^\s*[a-zA-Z_]\w*\s+in\s+[^:]+:\s*$',
            'incomplete_returns': r'return\s+[^{][^}]*[^}]$',
            'malformed_conditions': r'\([^)]+\):\{[^}]*\}',
            'ternary_operators': r'\([^)]+\)\?[^:]+:[^,\s}]+',
            'string_concat_errors': r'[a-zA-Z_]\w*\+_[a-zA-Z0-9_]+\.json',
            'missing_quotes': r'print\(f"[^"]*\{[^}]*\}[^"]*\)',
            'compound_statements': r'[a-zA-Z_]\w*else:',
            'orphaned_braces_after_statements': r'(results\s*=\s*\[\]|\w+\[[^\]]+\]\s*\+=\s*1)\s*\}',
            'malformed_exceptions': r'exceptif\s+\w+:',
            'incomplete_config_dicts': r'\{"[^}]*$',
            'missing_dict_braces': r'return\s+[^{][^}]*"[^}]*:[^}]*',
            'double_braces': r'\{\{[^}]*\}\}',
            'for_loop_braces': r'for\s+[^{]+:\{[^}]+\}'
        };
        
        for pattern_name, pattern in patterns.items():
            matches = re.findall(pattern, content, re.MULTILINE)
            if matches:
                self.logger.info(f"   🚨 {pattern_name}: {len(matches)} occurrences")
                for i, match in enumerate(matches[:3]):  # Show first 3 examples
                    self.logger.info(f"      Example {i+1}: {match[:100]}...")
            else:
                self.logger.info(f"   ✅ {pattern_name}: No issues found")
        
        # Log specific problematic lines
        lines = content.split('\n')
        problematic_lines = []
        
        for i, line in enumerate(lines, 1):
            line_stripped = line.strip()
            if (line_stripped.endswith('}') and not line_stripped.startswith('return') and 
                line_stripped != '}' and ':' not in line_stripped):
                problematic_lines.append(f"Line {i}: {line_stripped}")
            elif line_stripped.startswith('{') and not line_stripped.endswith('}'):
                problematic_lines.append(f"Line {i}: {line_stripped}")
            elif '"' in line_stripped and line_stripped.count('"') % 2 != 0:
                problematic_lines.append(f"Line {i}: {line_stripped}")
        
        if problematic_lines:
            self.logger.info(f"🔍 SPECIFIC PROBLEMATIC LINES ({len(problematic_lines)} found):")
            for line_info in problematic_lines[:10]:  # Show first 10
                self.logger.info(f"   {line_info}")
        else:
            self.logger.info("✅ No specific problematic lines identified")
    
    def resolve_ast_node(self, node: ast.AST) -> ast.AST:
        """Resolve references in an AST node."""
        from .cai3_ast_transformer import ResolutionTransformer
        
        transformer = ResolutionTransformer(
            self.pools, 
            {},  # chain aliases
            self.hash_resolver
        )
        
        return transformer.visit(node)
    
    def _fix_dictionary_structure(self, content: str) -> str:
        """Fix malformed dictionary structures - TARGETED fix."""
        # Fix the specific pattern from the example:
        # return {hash_e29ccc00b2:\n    s.na, hash_e0f857c210:\n        s.th, ...
        
        # Pattern: multiple key:value pairs with incorrect indentation
        lines = content.split('\n')
        fixed_lines = []
        in_dict = False
        dict_entries = []
        
        for line in lines:
            stripped = line.strip()
            
            # Detect start of malformed dictionary
            if 'return {' in line and ':' in line:
                in_dict = True
                # Start collecting entries
                if stripped.endswith(':'):
                    dict_entries.append(stripped[:-1])  # Remove trailing colon
                else:
                    # Extract first entry
                    match = re.match(r'return\s*{([^:]+):\s*(.+)', line)
                    if match:
                        key = match.group(1).strip()
                        value = match.group(2).strip()
                        dict_entries.append(f'{key}: {value}')
                        fixed_lines.append(f'return {{')
                        continue
            
            elif in_dict:
                # Continue collecting dictionary entries
                if '}' in stripped:
                    # End of dictionary
                    in_dict = False
                    # Format the dictionary properly
                    if dict_entries:
                        for i, entry in enumerate(dict_entries):
                            if i < len(dict_entries) - 1:
                                fixed_lines.append(f'    {entry},')
                            else:
                                fixed_lines.append(f'    {entry}')
                    fixed_lines.append('}')
                    dict_entries = []
                elif ':' in stripped:
                    # Another dictionary entry
                    key, value = stripped.split(':', 1)
                    dict_entries.append(f'{key.strip()}: {value.strip()}')
                else:
                    # This might be a value continuation
                    if dict_entries:
                        dict_entries[-1] += f', {stripped}'
            else:
                fixed_lines.append(line)
        
        return '\n'.join(fixed_lines)
    
    def _get_context_aware_quoted_value(self, resolved_value: str, original_hash: str, full_content: str, match) -> str:
        """
        Determine if a resolved hash value needs to be quoted based on context.
        Apply the same logic as pool resolution for consistency.
        
        Args:
            resolved_value: The resolved value (e.g., "error", "name", "Path")
            original_hash: The original hash (e.g., "hash_ca00")
            full_content: The full content being processed
            match: The regex match object for context analysis
            
        Returns:
            Contextually appropriate value (quoted or unquoted)
        """
        self.logger.debug(f"🔍 Context analysis for: {resolved_value}")
        
        # Get surrounding context (50 chars before and after)
        start_pos = max(0, match.start() - 50)
        end_pos = min(len(full_content), match.end() + 50)
        context = full_content[start_pos:end_pos]
        
        self.logger.debug(f"   📝 Context: ...{context}...")
        
        # CRITICAL FIX: If the resolved value is already a quoted string literal,
        # preserve it as-is. This is much more robust than trying to guess context.
        if ((resolved_value.startswith('"') and resolved_value.endswith('"')) or
            (resolved_value.startswith("'") and resolved_value.endswith("'"))):
            self.logger.debug(f"   ✅ Already quoted string literal, preserving: {resolved_value}")
            return resolved_value
        
        # Strip quotes for analysis (but we'll add them back if needed)
        clean_value = resolved_value.strip('\'"')
        
        # Check if it's a Python built-in/import that should NEVER be quoted
        python_builtins = {
            'dataclass', 'frozen', 'Path', 'datetime', 'time', 'json', 
            'pandas', 'numpy', 'os', 'sys', 'pathlib', 'logging',
            'True', 'False', 'None', 'int', 'str', 'dict', 'list',
            'tuple', 'set', 'float', 'bool', 'len', 'range', 'sum',
            'max', 'min', 'abs', 'round', 'print', 'type', 'isinstance'
        }
        
        if clean_value in python_builtins:
            self.logger.debug(f"   ✅ Python built-in/import, never quote: {clean_value}")
            return clean_value
        
        # Numbers should never be quoted
        if re.match(r'^[\d\.\-\+e]+$', clean_value):
            self.logger.debug(f"   ✅ Numeric value, never quote: {clean_value}")
            return clean_value
        
        # CONTEXT-BASED QUOTING LOGIC (same as pool resolution):
        
        # Check if used as dictionary key: {key: or [key]
        dict_key_patterns = [
            rf'\{{\s*{re.escape(original_hash)}\s*:',  # {hash:
            rf'\[\s*{re.escape(original_hash)}\s*\]',  # [hash]
        ]
        
        for pattern in dict_key_patterns:
            if re.search(pattern, context):
                self.logger.debug(f"   ✅ Used as dictionary key, quoting: \"{clean_value}\"")
                return f'"{clean_value}"'
        
        # Check if used in string comparison context: in, ==, !=
        string_comparison_patterns = [
            rf'{re.escape(original_hash)}\s+not\s+in\s+',      # hash not in
            rf'{re.escape(original_hash)}\s+in\s+',            # hash in  
            rf'if\s+{re.escape(original_hash)}\s*==',          # if hash ==
            rf'elif\s+{re.escape(original_hash)}\s*==',        # elif hash ==
            rf'==\s*{re.escape(original_hash)}',               # == hash
            rf'!=\s*{re.escape(original_hash)}',               # != hash
            rf'return\s+{re.escape(original_hash)}\s*$',       # return hash
            rf'return\s+{re.escape(original_hash)}\s*;',       # return hash;
        ]
        
        for pattern in string_comparison_patterns:
            if re.search(pattern, context):
                self.logger.debug(f"   ✅ Used in string comparison, quoting: \"{clean_value}\"")
                return f'"{clean_value}"'
        
        # Check for file paths or strings with special characters - should be quoted
        if ('/' in clean_value or '\\' in clean_value or 
            ' ' in clean_value or '-' in clean_value or '_' in clean_value):
            self.logger.debug(f"   ✅ File path or special string, quoting: \"{clean_value}\"")
            return f'"{clean_value}"'
        
        # Default: if it's a simple identifier used in other contexts (assignments, function calls, etc.)
        # don't quote it - it's likely a variable name or attribute
        self.logger.debug(f"   ✅ Used as identifier/variable, not quoting: {clean_value}")
        return clean_value