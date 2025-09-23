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
        
        # CRITICAL FIX: Step 3: Translate T{}X{} structures BEFORE variable resolution
        self.logger.info("🔍 Step 3: Translating T{}X{} structures (BEFORE variable resolution)...")
        content = self._translate_try_except_structures(content)
        self.logger.info(f"✅ After T{{}}X{{}} translation: {content[:200]}...")
        
        # Step 4: Resolve variable references (AFTER T{}X{} translation)
        self.logger.info("🔍 Step 4: Resolving variable references...")
        content = self._resolve_variables(content)
        self.logger.info(f"✅ After variable resolution: {content[:200]}...")
        
        # Step 5: Fix remaining CAI3 syntax (excluding T{}X{} translation)
        self.logger.info("🔍 Step 5: Fixing remaining CAI3 syntax...")
        content = self._fix_cai3_syntax_without_try_except(content)
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
            # Handle decimal patterns with underscore: num_3_14 -> 3.14, num_0_1 -> 0.1
            (r'num_(\d+)_(\d+)', r'\1.\2'),
            
            # Handle special leading zero decimals: num_0_01 -> 0.01, num_0_001 -> 0.001
            (r'num_0_0(\d+)', r'0.0\1'),
            
            # Handle simple integer patterns: num_1024 -> 1024
            (r'num_(\d+)', r'\1'),
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
                    
                    # Generate example safely based on pattern type
                    try:
                        if '_(\d+)_(\d+)' in pattern:  # Decimal pattern like num_3_14 -> 3.14
                            if isinstance(matches[0], tuple) and len(matches[0]) >= 2:
                                self.logger.info(f"      ✅ Example: {matches[0]} -> {matches[0][0]}.{matches[0][1]}")
                            else:
                                self.logger.info(f"      ✅ Example: {matches[0]} -> (decimal)")
                        elif 'num_0_0' in pattern:  # Special case for num_0_01
                            self.logger.info(f"      ✅ Example: num_0_0{matches[0]} -> 0.0{matches[0]}")
                        else:  # Simple pattern like num_1024 -> 1024
                            self.logger.info(f"      ✅ Example: {matches[0]} -> {matches[0]}")
                    except (IndexError, TypeError):
                        self.logger.info(f"      ✅ Resolved {len(matches)} number patterns")
        
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
        # Get surrounding context - increased window for better detection
        start = max(0, match.start() - 50)
        end = min(len(context), match.end() + 50)
        surrounding = context[start:end]
        
        self.logger.debug(f"Context for {pool_id}: ...{surrounding}...")
        self.logger.debug(f"   Full context length: {len(context)}, surrounding: '{surrounding}'")
        
        # If the value is already quoted, preserve it as-is
        if ((value.startswith('"') and value.endswith('"')) or
            (value.startswith("'") and value.endswith("'"))):
            self.logger.debug(f"   ✅ Already quoted string literal, preserving: {value}")
            return value
        
        # Strip quotes for analysis (but we'll add them back if needed)
        clean_value = str(value).strip('\'"')
        
        # CONTEXT-BASED QUOTING LOGIC - CHECK FIRST before builtin check:
        
        # Check if used as dictionary key: {key: or [key]
        # CRITICAL: Fixed pattern to properly detect dictionary keys
        dict_key_patterns = [
            rf'\{{\s*{re.escape(pool_id)}\s*:',                           # {pool_id:
            rf'\{{\s*[^,}}]*,\s*{re.escape(pool_id)}\s*:',               # {something,pool_id:
            rf',\s*{re.escape(pool_id)}\s*:',                            # ,pool_id: (anywhere in dict)
            rf'\[\s*{re.escape(pool_id)}\s*\]',                          # [pool_id]
        ]
        
        for i, pattern in enumerate(dict_key_patterns):
            self.logger.debug(f"   Testing pattern {i}: {pattern}")
            if re.search(pattern, surrounding):
                self.logger.debug(f"   ✅ MATCHED pattern {i}! Used as dictionary key, quoting: \"{clean_value}\"")
                return f'"{clean_value}"'
            else:
                self.logger.debug(f"   ❌ Pattern {i} did not match")
        
        self.logger.debug(f"   No dictionary key patterns matched for {pool_id} in context")
        
        
        # Numbers should never be quoted
        if re.match(r'^[\d\.\-\+e]+$', clean_value):
            self.logger.debug(f"   ✅ Numeric value, never quote: {clean_value}")
            return clean_value
        
        # Check if it's a Python built-in/keyword that should NEVER be quoted
        python_builtins = {
            'dataclass', 'frozen', 'Path', 'datetime', 'time', 'json', 
            'pandas', 'numpy', 'os', 'sys', 'pathlib', 'logging',
            'True', 'False', 'None', 'int', 'str', 'dict', 'list',
            'tuple', 'set', 'float', 'bool', 'len', 'range', 'sum',
            'max', 'min', 'abs', 'round', 'print', 'type', 'isinstance'
            # NOTE: Removed 'error', 'data' - these should be context-dependent
        }
        
        if clean_value in python_builtins:
            self.logger.debug(f"   ✅ Python built-in/keyword, never quote: {clean_value}")
            return clean_value
        
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
        """Resolve variable references using the variables mapping with Python keyword protection."""
        if not self.variables:
            self.logger.warning("⚠️ No variable mappings available for resolution!")
            return content
        
        self.logger.info(f"🔄 Resolving {len(self.variables)} variable references...")
        self.logger.info(f"🔍 DEBUG: Variable mappings: {self.variables}")
        self.logger.info(f"🔍 DEBUG: Input content for variable resolution:\n{content}")
        
        # Sort by key length (longest first) to avoid partial replacements
        sorted_variables = sorted(self.variables.items(), key=lambda x: len(x[0]), reverse=True)
        
        for var_id, value in sorted_variables:
            self.logger.info(f"🔍 DEBUG: Looking for variable '{var_id}' -> '{value}'")
            
            # CRITICAL FIX: Skip Python keywords in specific grammatical contexts
            if var_id in ['as', 'is', 'in', 'and', 'or', 'not', 'if', 'else', 'elif', 'for', 'while', 'try', 'except', 'finally', 'with', 'import', 'from', 'def', 'class']:
                # IMPROVED: For mixed contexts, skip global check and rely on per-match filtering
                has_protected_context = self._is_python_keyword_in_context(var_id, content)
                if has_protected_context:
                    # Count occurrences to decide strategy
                    total_occurrences = len(re.findall(rf'\b{re.escape(var_id)}\b', content))
                    if var_id == 'as':
                        # Special handling for 'as' - check if ALL are protected
                        as_patterns = [
                            r'except\s+\w+\s+as\s+\w+\s*:',     
                            r'except\s+\w+\.\w+\s+as\s+\w+\s*:', 
                            r'import\s+\w+\s+as\s+\w+',         
                            r'from\s+\w+\s+import\s+\w+\s+as\s+\w+',  
                            r'with\s+[^:]+\s+as\s+\w+\s*:',     
                        ]
                        protected_occurrences = sum(len(re.findall(pattern, content)) for pattern in as_patterns)
                        
                        self.logger.info(f"   📊 'as' analysis: {total_occurrences} total, {protected_occurrences} protected")
                        
                        # Only skip ALL if ALL occurrences are protected
                        if protected_occurrences >= total_occurrences:
                            self.logger.info(f"⚠️ SKIPPING all 'as' - all occurrences protected")
                            continue
                        else:
                            self.logger.info(f"🔀 MIXED CONTEXT for 'as' - using per-match filtering")
                            # Continue to per-match filtering
                    else:
                        # For other keywords, if any are protected, skip all (conservative)
                        self.logger.info(f"⚠️ SKIPPING Python keyword '{var_id}' - found in grammatical context")
                        continue
            
            # Use multiple patterns to catch variables in different contexts
            patterns = [
                rf'\b{re.escape(var_id)}\b',  # Standard word boundary
                rf'(?<![a-zA-Z_]){re.escape(var_id)}(?![a-zA-Z0-9_])',  # More strict boundaries
                rf'(?<=\.){re.escape(var_id)}\b',  # After dot (like self.x)
                rf'(?<=\s){re.escape(var_id)}\b',  # After whitespace
                rf'^{re.escape(var_id)}\b',  # At start of line
                rf'(?<=[^a-zA-Z0-9_]){re.escape(var_id)}(?=[^a-zA-Z0-9_])'  # Non-identifier characters around
            ]
            
            all_matches = []
            for i, pattern in enumerate(patterns):
                matches = list(re.finditer(pattern, content, re.MULTILINE))
                if matches:
                    self.logger.info(f"🔍 DEBUG: Pattern {i} ({pattern}) found {len(matches)} matches for '{var_id}'")
                    valid_matches = []
                    for match in matches:
                        # CRITICAL FIX: Context-aware filtering - skip matches in Python keyword contexts
                        if self._should_skip_match_for_keyword(var_id, match, content):
                            self.logger.info(f"   ⚠️ Skipping match at pos {match.start()}-{match.end()} - Python keyword context")
                            continue
                        
                        # CRITICAL FIX: Also protect variables that appear in except clauses
                        if self._should_skip_variable_in_except_context(var_id, match, content):
                            self.logger.info(f"   ⚠️ Skipping match at pos {match.start()}-{match.end()} - except clause context")
                            continue
                            
                        start, end = match.span()
                        context_start = max(0, start - 20)
                        context_end = min(len(content), end + 20)
                        context = content[context_start:context_end]
                        self.logger.info(f"   Match at pos {start}-{end}: ...{context}...")
                        valid_matches.append(match)
                    all_matches.extend(valid_matches)
            
            # Remove duplicates (same position)
            unique_matches = []
            seen_positions = set()
            for match in all_matches:
                pos = (match.start(), match.end())
                if pos not in seen_positions:
                    unique_matches.append(match)
                    seen_positions.add(pos)
            
            # Sort by position for consistent replacement
            unique_matches.sort(key=lambda m: m.start())
            
            if unique_matches:
                self.logger.info(f"   📋 Found {len(unique_matches)} unique occurrences of {var_id}")
                
            # Replace each match - only quote if clearly a string literal
            for match in reversed(unique_matches):  # Reverse to maintain positions
                # ALWAYS quote file paths, paths with slashes, special characters, or file extensions
                if ('/' in value or '\\' in value or ' ' in value or '-' in value or 
                    '.' in value and value.endswith(('.py', '.txt', '.json', '.md', '.yml', '.yaml', '.xml'))):
                    quoted_value = f'"{value}"'
                    self.logger.info(f"🔧 DEBUG: Quoting variable value: '{value}' -> '{quoted_value}'")
                else:
                    quoted_value = value
                    self.logger.info(f"🔧 DEBUG: Not quoting variable value: '{value}'")
                
                old_content = content
                content = content[:match.start()] + quoted_value + content[match.end():]
                self.logger.info(f"🔧 DEBUG: Replaced '{var_id}' at position {match.start()}-{match.end()}")
                
        self.logger.info(f"🔍 DEBUG: Final content after variable resolution:\n{content}")
        return content
    
    def _is_python_keyword_in_context(self, keyword: str, content: str) -> bool:
        """
        Check if a Python keyword appears in its proper grammatical context.
        Returns True if the keyword should NOT be replaced.
        
        This method now checks for ANY occurrence in the content, not just global presence.
        """
        if keyword == 'as':
            # Check for 'except Exception as var:', 'import module as alias', 'with context as var:'
            patterns = [
                r'except\s+\w+\s+as\s+\w+\s*:',     # except Exception as e:
                r'except\s+\w+\.\w+\s+as\s+\w+\s*:',  # except module.Exception as e:
                r'import\s+\w+\s+as\s+\w+',         # import module as alias
                r'from\s+\w+\s+import\s+\w+\s+as\s+\w+',  # from module import item as alias
                r'with\s+[^:]+\s+as\s+\w+\s*:',     # with context as var:
            ]
            # If ANY occurrence is in a protected context, skip ALL replacements initially
            # This is a conservative approach to avoid partial replacements
            has_protected = any(re.search(pattern, content) for pattern in patterns)
            
            if has_protected:
                # Count total 'as' occurrences vs protected occurrences
                total_as = len(re.findall(r'\bas\b', content))
                protected_as = sum(len(re.findall(pattern, content)) for pattern in patterns)
                
                self.logger.info(f"   📊 Found {total_as} total 'as' occurrences, {protected_as} in protected contexts")
                
                # If all 'as' occurrences are protected, skip all replacements
                if protected_as >= total_as:
                    return True
                else:
                    # Mixed context - use per-match filtering instead of global skip
                    return False
            
            return False
        
        elif keyword == 'in':
            # Check for 'for item in container:', 'if item in container'
            patterns = [
                r'for\s+\w+\s+in\s+[^:]+\s*:',      # for item in container:
                r'if\s+[^:]+\s+in\s+[^:]+\s*:',     # if item in container:
                r'elif\s+[^:]+\s+in\s+[^:]+\s*:',   # elif item in container:
                r'\w+\s+not\s+in\s+\w+',            # item not in container
            ]
            return any(re.search(pattern, content) for pattern in patterns)
        
        elif keyword == 'is':
            # Check for 'if var is None:', 'var is not None'
            patterns = [
                r'if\s+\w+\s+is\s+None\s*:',        # if var is None:
                r'elif\s+\w+\s+is\s+None\s*:',      # elif var is None:
                r'\w+\s+is\s+not\s+None',           # var is not None
                r'\w+\s+is\s+\w+',                  # var is value
            ]
            return any(re.search(pattern, content) for pattern in patterns)
        
        # Add more keyword checks as needed
        return False
    
    def _should_skip_match_for_keyword(self, keyword: str, match, content: str) -> bool:
        """
        Check if a specific match should be skipped because it's a Python keyword in context.
        Uses syntax-aware statement analysis instead of fixed character windows.
        """
        if keyword not in ['as', 'is', 'in', 'and', 'or', 'not', 'if', 'else', 'elif', 'for', 'while', 'try', 'except', 'finally', 'with', 'import', 'from', 'def', 'class']:
            return False
        
        # Get the complete statement containing this match
        statement = self._extract_statement_containing_match(match, content)
        self.logger.debug(f"   🔍 Analyzing statement: {repr(statement)}")
        
        # Use the complete statement as context for more reliable pattern matching
        context = statement
        
        if keyword == 'as':
            # CRITICAL: Check for exception handling, import statements, and with statements
            patterns = [
                r'except\s+\w+(\.\w+)?\s+as\s+\w+\s*:',    # except Exception as e:
                r'import\s+\w+(\.\w+)?\s+as\s+\w+',        # import module as alias
                r'from\s+\w+\s+import\s+\w+\s+as\s+\w+',   # from module import item as alias
                r'with\s+[^:]+\s+as\s+\w+\s*:',           # with context as var:
            ]
            for pattern in patterns:
                if re.search(pattern, context):
                    self.logger.info(f"   🛡️ Protected 'as' keyword in context: {pattern}")
                    return True
        
        elif keyword == 'in':
            patterns = [
                r'for\s+\w+\s+in\s+[^:]+\s*:',      # for item in container:
                r'if\s+[^:]+\s+in\s+[^:]+\s*:',     # if item in container:
                r'elif\s+[^:]+\s+in\s+[^:]+\s*:',   # elif item in container:
                r'\w+\s+not\s+in\s+\w+',            # item not in container
            ]
            for pattern in patterns:
                if re.search(pattern, context):
                    self.logger.info(f"   🛡️ Protected 'in' keyword in context: {pattern}")
                    return True
        
        elif keyword == 'is':
            patterns = [
                r'if\s+\w+\s+is\s+(None|\w+)\s*:',     # if var is None/value:
                r'elif\s+\w+\s+is\s+(None|\w+)\s*:',   # elif var is None/value:
                r'\w+\s+is\s+not\s+(None|\w+)',        # var is not None/value
                r'\w+\s+is\s+\w+',                     # var is value
            ]
            for pattern in patterns:
                if re.search(pattern, context):
                    self.logger.info(f"   🛡️ Protected 'is' keyword in context: {pattern}")
                    return True
        
        return False
    
    def _extract_statement_containing_match(self, match, content: str) -> str:
        """
        Extract the complete Python statement containing the given match.
        This is more robust than fixed character windows as it respects Python syntax.
        """
        lines = content.split('\n')
        match_pos = match.start()
        
        # Find which line contains the match
        current_pos = 0
        match_line_idx = 0
        for i, line in enumerate(lines):
            if current_pos <= match_pos < current_pos + len(line) + 1:  # +1 for newline
                match_line_idx = i
                break
            current_pos += len(line) + 1  # +1 for newline
        
        # Start with the line containing the match
        statement_lines = [lines[match_line_idx]]
        
        # Look backwards for the start of the statement
        start_idx = match_line_idx
        while start_idx > 0:
            prev_line = lines[start_idx - 1].rstrip()
            current_line = lines[start_idx].strip()
            
            # If previous line ends with a continuation character or this line is indented more
            if (prev_line.endswith(('\\', ',', '(', '[', '{')) or
                prev_line.endswith(('and', 'or', '+', '-', '*', '/', '=')) or
                (current_line and len(lines[start_idx]) - len(lines[start_idx].lstrip()) > 
                 len(lines[start_idx - 1]) - len(lines[start_idx - 1].lstrip()))):
                statement_lines.insert(0, lines[start_idx - 1])
                start_idx -= 1
            else:
                break
        
        # Look forwards for the end of the statement
        end_idx = match_line_idx
        while end_idx < len(lines) - 1:
            current_line = lines[end_idx].rstrip()
            next_line = lines[end_idx + 1].strip()
            
            # If current line ends with continuation or next line is indented more
            if (current_line.endswith(('\\', ',', '(', '[', '{')) or
                current_line.endswith(('and', 'or', '+', '-', '*', '/', '=')) or
                (next_line and len(lines[end_idx + 1]) - len(lines[end_idx + 1].lstrip()) > 
                 len(lines[end_idx]) - len(lines[end_idx].lstrip()))):
                statement_lines.append(lines[end_idx + 1])
                end_idx += 1
            else:
                break
        
        # Join the statement lines, preserving internal structure but creating a clean single statement
        statement = ' '.join(line.strip() for line in statement_lines if line.strip())
        
        self.logger.debug(f"   📍 Statement extraction: lines {start_idx}-{end_idx}: {repr(statement)}")
        return statement
    
    def _should_skip_variable_in_except_context(self, var_id: str, match, content: str) -> bool:
        """
        Check if a variable should be skipped because it's in an except clause context.
        This protects exception variables like 'e' in 'except Exception as e:'.
        Uses syntax-aware statement analysis instead of fixed character windows.
        """
        # Get the complete statement containing this match
        statement = self._extract_statement_containing_match(match, content)
        self.logger.debug(f"   🔍 Checking except context for '{var_id}' in: {repr(statement)}")
        
        # Check if this variable appears in an except clause within this statement
        except_patterns = [
            rf'except\s+\w+(\.\w+)?\s+as\s+{re.escape(var_id)}\s*:',    # except Exception as var:
            rf'except\s+\w+\s+{re.escape(var_id)}\s*:',                 # except Exception var: (no 'as')
        ]
        
        for pattern in except_patterns:
            if re.search(pattern, statement):
                self.logger.info(f"   🛡️ Protected variable '{var_id}' in except clause context")
                return True
        
        return False
    
    def _fix_cai3_syntax(self, content: str) -> str:
        """Enhanced CAI3 syntax fixing using AST-based approach with Black formatting."""
        self.logger.info("🔧 Starting CAI3 syntax fixing...")
        
        # CRITICAL: Check if content is still in CAI3 format
        cai3_markers = ['#C3L', 'CAI3:', 'P:', 'T:', 'B#', 'I:', 'D:', 'X:']
        if any(marker in content for marker in cai3_markers):
            self.logger.info("🚨 Content appears to be in CAI3 format - SKIPPING syntax fixes")
            return content
        
        # CRITICAL FIX: Check if content already has well-formed try/except structure
        # If it does, don't process it further to avoid corruption
        if ('try:' in content and 'except ' in content and 
            content.count('try:') == content.count('except ')):
            # Validate that the try/except structure is syntactically correct
            try:
                import ast
                ast.parse(content)
                self.logger.info("✅ Content already has valid try/except structure - SKIPPING modifications")
                return content
            except SyntaxError:
                # Structure is malformed, continue with processing
                self.logger.info("⚠️ Try/except structure found but malformed - continuing with fixes")
                pass
        
        original_content = content
        
        # Step 1: Pre-process to fix CAI3-specific issues
        content = self._preprocess_cai3_content(content)
        
        # Step 2: Parse into logical blocks using AST-aware approach
        blocks = self._parse_into_logical_blocks(content)
        
        # Step 3: Fix each block individually
        fixed_blocks = []
        for block in blocks:
            fixed_block = self._fix_block_syntax(block)
            fixed_blocks.append(fixed_block)
        
        # Step 4: Reassemble with proper structure
        content = self._reassemble_blocks(fixed_blocks)
        
        # Step 5: Apply Black formatting with fallback
        formatted_content = self._apply_black_with_fallback(content)
        
        # Step 6: Final syntax cleanup
        formatted_content = self._final_syntax_cleanup(formatted_content)
        
        # Log changes made
        if formatted_content != original_content:
            self.logger.info("✅ Applied comprehensive syntax fixes")
            self.logger.debug(f"Fixed content:\n{formatted_content}")
        else:
            self.logger.info("ℹ️ No syntax fixes needed")
        
        return formatted_content

    def _fix_cai3_concatenations(self, content: str) -> str:
        """Fix hash-keyword concatenations and other CAI3 artifacts."""
        concatenation_fixes = [
            (r'(hash_[a-f0-9]+)(elif)', r'\1 \2'),
            (r'(hash_[a-f0-9]+)(else)', r'\1 \2'),
            (r'(\w+)(elif)', r'\1\n\2'),
            (r'(\w+)(else):', r'\1\nelse:'),
            (r'(pass)(return)', r'\1\n\2'),
            (r'(pass)(if)', r'\1\n\2'),
            (r'(pass)(elif)', r'\1\n\2'),
            (r'(pass)(else)', r'\1\n\2'),
            (r'(pass)(for)', r'\1\n\2'),
            (r'(break)(if)', r'\1\n\2'),
            (r'(\d)(elif)', r'\1\n\2'),
            (r'(\d)(else)', r'\1\n\2'),
        ]
        
        for pattern, replacement in concatenation_fixes:
            content = re.sub(pattern, replacement, content)
        
        return content

    def _expand_inline_control_structures(self, content: str) -> str:
        """Expand inline control structures to multi-line format."""
        lines = content.split('\n')
        expanded_lines = []
        
        for line in lines:
            # Handle multiple statements on one line
            if ':' in line and not line.strip().endswith(':'):
                # This is a control structure with inline body
                parts = line.split(':', 1)
                if len(parts) == 2 and any(keyword in parts[0] for keyword in ['if', 'elif', 'else', 'for', 'while', 'try', 'except']):
                    indent = len(line) - len(line.lstrip())
                    expanded_lines.append(parts[0] + ':')
                    # Add the body with proper indentation
                    body = parts[1].strip()
                    if body:
                        expanded_lines.append(' ' * (indent + 4) + body)
                else:
                    expanded_lines.append(line)
            else:
                expanded_lines.append(line)
        
        return '\n'.join(expanded_lines)

    def _parse_into_logical_blocks(self, content: str) -> List[dict]:
        """Parse content into logical blocks (classes, functions, etc.)."""
        self.logger.info("📦 Parsing into logical blocks...")
        
        blocks = []
        lines = content.split('\n')
        current_block = {'type': 'module', 'lines': [], 'indent': 0}
        
        i = 0
        while i < len(lines):
            line = lines[i]
            stripped = line.strip()
            indent = len(line) - len(line.lstrip())
            
            # Detect block starts
            if stripped.startswith('class '):
                # Save current block
                if current_block['lines']:
                    blocks.append(current_block)
                # Start new class block
                current_block = {
                    'type': 'class',
                    'lines': [line],
                    'indent': indent,
                    'name': stripped.split()[1].rstrip(':')
                }
            elif stripped.startswith('def '):
                # Check if we're inside a class
                if current_block['type'] == 'class':
                    # Add to class block
                    current_block['lines'].append(line)
                else:
                    # Save current block and start new function
                    if current_block['lines']:
                        blocks.append(current_block)
                    current_block = {
                        'type': 'function',
                        'lines': [line],
                        'indent': indent,
                        'name': stripped.split('(')[0].split()[1]
                    }
            elif stripped and indent <= current_block.get('indent', 0) and current_block['type'] != 'module':
                # End of current block
                blocks.append(current_block)
                current_block = {'type': 'module', 'lines': [line], 'indent': 0}
            else:
                # Add to current block
                current_block['lines'].append(line)
            
            i += 1
        
        # Don't forget the last block
        if current_block['lines']:
            blocks.append(current_block)
        
        self.logger.info(f"📦 Found {len(blocks)} logical blocks")
        return blocks

    def _fix_block_syntax(self, block: dict) -> dict:
        """Fix syntax issues within a single block."""
        self.logger.info(f"🔧 Fixing {block['type']} block")
        
        lines = block['lines']
        fixed_lines = []
        
        # Process based on block type
        if block['type'] == 'class':
            fixed_lines = self._fix_class_block(lines)
        elif block['type'] == 'function':
            fixed_lines = self._fix_function_block(lines)
        else:
            fixed_lines = self._fix_module_block(lines)
        
        block['lines'] = fixed_lines
        return block

    def _fix_class_block(self, lines: List[str]) -> List[str]:
        """Fix syntax issues in a class block."""
        fixed_lines = []
        class_indent = 0
        
        for i, line in enumerate(lines):
            if i == 0:  # Class definition
                fixed_lines.append(line)
                class_indent = len(line) - len(line.lstrip())
                continue
            
            stripped = line.strip()
            if not stripped:
                fixed_lines.append('')
                continue
            
            # Fix method definitions
            if stripped.startswith('def '):
                fixed_lines.append(' ' * (class_indent + 4) + stripped)
            else:
                # Fix method body indentation
                fixed_line = self._fix_line_indentation(line, class_indent + 4)
                fixed_lines.append(fixed_line)
        
        return fixed_lines

    def _fix_function_block(self, lines: List[str]) -> List[str]:
        """Fix syntax issues in a function block."""
        return self._fix_indented_block(lines)

    def _fix_module_block(self, lines: List[str]) -> List[str]:
        """Fix syntax issues in module-level code."""
        fixed_lines = []
        
        for line in lines:
            fixed_line = self._fix_line_syntax(line)
            fixed_lines.append(fixed_line)
    
        return fixed_lines

    def _fix_indented_block(self, lines: List[str]) -> List[str]:
        """Fix indentation in a block of code."""
        if not lines:
            return lines
        
        fixed_lines = []
        base_indent = len(lines[0]) - len(lines[0].lstrip())
        current_indent = 0
        
        for i, line in enumerate(lines):
            stripped = line.strip()
            
            if not stripped:
                fixed_lines.append('')
                continue
            
            # Calculate proper indentation
            if i == 0:  # First line (function/class def)
                fixed_lines.append(line)
                current_indent = base_indent + 4
            elif self._is_dedent_keyword(stripped):
                current_indent = max(base_indent + 4, current_indent - 4)
                fixed_lines.append(' ' * current_indent + stripped)
                if stripped.endswith(':'):
                    current_indent += 4
            elif self._is_indent_keyword(stripped):
                fixed_lines.append(' ' * current_indent + stripped)
                current_indent += 4
            else:
                fixed_lines.append(' ' * current_indent + stripped)
    
        return fixed_lines

    def _fix_line_indentation(self, line: str, min_indent: int) -> str:
        """Fix indentation for a single line."""
        stripped = line.strip()
        if not stripped:
            return ''
        
        current_indent = len(line) - len(line.lstrip())
        
        # Ensure minimum indentation
        if current_indent < min_indent:
            return ' ' * min_indent + stripped
        
        return line

    def _fix_line_syntax(self, line: str) -> str:
        """Fix syntax issues in a single line."""
        stripped = line.strip()
        indent = len(line) - len(line.lstrip())
        
        # Fix missing colons
        if re.match(r'^\s*(if|elif|else|for|while|try|except|finally|def|class)\s+[^:]+$', line):
            if not line.rstrip().endswith(':'):
                line = line.rstrip() + ':'
        
        # Handle bare 'else' case - DON'T add pass here, let _final_syntax_cleanup handle it
        if stripped == 'else:':
            return ' ' * indent + 'else:'
        elif stripped == 'else':
            return ' ' * indent + 'else:'
        
        # REMOVED: Don't add pass statements here - _final_syntax_cleanup handles this more intelligently
        # This prevents duplicate pass statements and allows proper content detection
        
        return line

    def _is_indent_keyword(self, line: str) -> bool:
        """Check if line starts a new indented block."""
        return any(line.startswith(kw) and line.rstrip().endswith(':') 
                   for kw in ['if', 'elif', 'else', 'for', 'while', 'try', 'except', 'finally', 'def', 'class', 'with'])

    def _is_dedent_keyword(self, line: str) -> bool:
        """Check if line should dedent."""
        return line.startswith(('elif', 'else', 'except', 'finally'))

    def _reassemble_blocks(self, blocks: List[dict]) -> str:
        """Reassemble blocks into complete code."""
        all_lines = []
        
        for i, block in enumerate(blocks):
            # Add blank line before classes and functions (except first)
            if i > 0 and block['type'] in ['class', 'function']:
                all_lines.append('')
            
            all_lines.extend(block['lines'])
        
        return '\n'.join(all_lines)

    def _apply_black_with_fallback(self, content: str) -> str:
        """Apply Black formatting with intelligent fallback."""
        try:
            import black
            
            # Try full formatting first
            try:
                mode = black.Mode(
                    line_length=120,  # Increased from 88 to reduce inconsistent line breaks
                    target_versions={black.TargetVersion.PY38},
                )
                return black.format_str(content, mode=mode)
            except black.InvalidInput:
                # Try line-by-line formatting
                self.logger.info("⚠️ Full Black formatting failed, trying line-by-line")
                return self._black_format_by_lines(content, black, mode)
                
        except ImportError:
            self.logger.warning("⚠️ Black not installed, using AST-based formatting")
            return self._ast_based_formatting(content)

    def _black_format_by_lines(self, content: str, black, mode) -> str:
        """Format code line by line when full formatting fails."""
        lines = content.split('\n')
        formatted_lines = []
        current_statement = []
        
        for line in lines:
            current_statement.append(line)
            
            # Try to format accumulated lines
            try:
                statement = '\n'.join(current_statement)
                formatted = black.format_str(statement, mode=mode)
                formatted_lines.extend(formatted.strip().split('\n'))
                current_statement = []
            except:
                # Continue accumulating
                if len(current_statement) > 10:  # Prevent infinite accumulation
                    # Just add the lines as-is
                    formatted_lines.extend(current_statement)
                    current_statement = []
        
        # Add any remaining lines
        formatted_lines.extend(current_statement)
        
        return '\n'.join(formatted_lines)

    def _ast_based_formatting(self, content: str) -> str:
        """Use AST to format code when Black is not available."""
        try:
            # Parse into AST
            tree = ast.parse(content)
            
            # Unparse with proper formatting
            return ast.unparse(tree)
        except:
            # Final fallback: manual formatting
            return self._manual_format_with_ast_analysis(content)

    def _manual_format_with_ast_analysis(self, content: str) -> str:
        """Manual formatting with AST-based analysis."""
        lines = content.split('\n')
        formatted_lines = []
        indent_stack = [0]
        
        for line in lines:
            stripped = line.strip()
            
            if not stripped:
                formatted_lines.append('')
                continue
            
            # Determine indentation
            if self._is_dedent_keyword(stripped):
                if len(indent_stack) > 1:
                    indent_stack.pop()
            
            current_indent = indent_stack[-1]
            formatted_lines.append(' ' * current_indent + stripped)
            
            # Update indent for next line
            if stripped.endswith(':') and not stripped.startswith(('elif', 'else')):
                indent_stack.append(current_indent + 4)
            elif stripped.startswith(('return', 'break', 'continue', 'raise', 'pass')):
                # These might end a block
                if len(indent_stack) > 1 and current_indent > 0:
                    # Check if next line is at lower indent level
                    # This is a heuristic - in production, use proper AST analysis
                    pass
        
        return '\n'.join(formatted_lines)

    def _preprocess_cai3_content(self, content: str) -> str:
        """Pre-process CAI3-specific patterns before parsing."""
        self.logger.info("🔧 Pre-processing CAI3 content...")
        
        # CRITICAL: Translate T{}X{} structures to try/except blocks FIRST
        # Do this BEFORE any statement splitting to preserve the structure
        content = self._translate_try_except_structures(content)
        
        # Fix CAI3 concatenation issues
        content = self._fix_cai3_concatenations(content)
        
        # CRITICAL: Fix inline statements separated by semicolons
        content = self._fix_inline_statements(content)
        
        # Fix malformed try-except blocks
        content = re.sub(
            r'}except\s+(\w+)\s+',
            r'}\nexcept \1:\n    ',
            content
        )
        
        # Fix inline control structures
        content = self._expand_inline_control_structures(content)
        
        return content

    def _translate_try_except_structures(self, content: str) -> str:
        """Translate CAI3 T{}X{} structures to Python try/except blocks."""
        self.logger.info("🔄 Translating T{}X{} structures to try/except blocks...")
        
        # CRITICAL DEBUG: Let's test multiple patterns
        test_patterns = [
            r'T\{([^{}]*(?:\{[^{}]*\}[^{}]*)*)\}X\(([^)]+)\)\{([^{}]*(?:\{[^{}]*\}[^{}]*)*)\}',
            r'T\{(.+?)\}X\(([^)]+)\)\{(.+?)\}',
            r'T\{(.+)\}X\(([^)]+)\)\{(.+)\}',
            r'T\{(.+?)\}X\(([^)]+)\)\{(.+)$',
            r'T\{(.+)\}X\(([^)]+)\)\{(.+)$',
        ]
        
        self.logger.info(f"🔍 Testing T{{}}X{{}} patterns on content: {content[:100]}...")
        
        for i, pattern in enumerate(test_patterns):
            matches = re.findall(pattern, content, re.DOTALL)
            self.logger.info(f"   Pattern {i}: {pattern}")
            if matches:
                self.logger.info(f"   ✅ MATCHED! Found {len(matches)} matches: {matches[0] if matches else 'None'}")
                break
            else:
                self.logger.info(f"   ❌ No match")
        
        # Use the working pattern (simplified for the actual structure)
        # The content appears to be all on one line, so we need a pattern that handles that
        pattern = r'T\{(.+)\}X\(([^)]+)\)\{(.+)\}'
        
        def replace_try_except(match):
            try_body = match.group(1).strip()
            exception_part = match.group(2).strip()
            except_body = match.group(3).strip()
            
            self.logger.info(f"🔍 Found T{{}}X{{}} pattern:")
            self.logger.info(f"   Try body: {try_body[:100]}...")
            self.logger.info(f"   Exception: {exception_part}")
            self.logger.info(f"   Except body: {except_body[:100]}...")
            
            # Parse exception part: "Exception as var_name" format (already correct in CAI3-LITE)
            exception_parts = exception_part.split()
            if len(exception_parts) >= 3 and exception_parts[1] == 'as':
                exception_type = exception_parts[0]
                var_name = exception_parts[2]
            elif len(exception_parts) >= 2:
                exception_type = exception_parts[0]
                var_name = exception_parts[1]  # Assume "Exception var" format
            else:
                exception_type = "Exception"
                var_name = "e"
            
            # CRITICAL FIX: Handle semicolon-separated statements properly
            # Convert semicolon-separated statements to newline-separated with proper indentation
            try_statements = self._split_statements_with_indentation(try_body)
            except_statements = self._split_statements_with_indentation(except_body)
            
            # Build properly indented Python try/except
            result_lines = ["try:"]
            for stmt in try_statements:
                if stmt.strip():  # Check if statement has content
                    # CRITICAL FIX: Preserve the indentation from _split_statements_with_indentation
                    # Don't strip it and re-add base indentation - the splitting logic already handled nesting
                    result_lines.append(f"    {stmt}")
            
            result_lines.append(f"except {exception_type} as {var_name}:")
            for stmt in except_statements:
                if stmt.strip():  # Check if statement has content
                    # CRITICAL FIX: Preserve the indentation from _split_statements_with_indentation
                    result_lines.append(f"    {stmt}")
            
            result = '\n'.join(result_lines)
            
            self.logger.info(f"✅ Translated T{{}}X{{}} structure: {exception_type} as {var_name}")
            self.logger.info(f"🔍 Result:\n{result}")
            return result
        
        # Apply the translation
        original_content = content
        content = re.sub(pattern, replace_try_except, content)
        
        if content != original_content:
            self.logger.info("✅ Successfully translated T{}X{} structures to try/except blocks")
        else:
            self.logger.info("ℹ️ No T{}X{} structures found to translate")
            self.logger.info(f"🔍 Content to search: {content}")
        
        return content
    
    def _split_statements_with_indentation(self, body: str) -> List[str]:
        """Split semicolon-separated statements while preserving logical structure."""
        if ';' not in body:
            return [body]
        
        # Simple split on semicolons
        raw_statements = [stmt.strip() for stmt in body.split(';') if stmt.strip()]
        
        # CRITICAL FIX: In try/except blocks, ALL statements should remain part of the try block
        # Don't remove statements as "unreachable" after return - they belong in the same scope
        statements = []
        
        for i, stmt in enumerate(raw_statements):
            
            # CRITICAL FIX: Handle for loops that have break statements after them
            stmt_clean = stmt.strip()
            
            # Check for for loop patterns with inline content
            if stmt_clean.startswith('for ') and ':' in stmt_clean:
                # This is a for loop with content after the colon
                colon_pos = stmt_clean.find(':')
                for_part = stmt_clean[:colon_pos + 1]  # "for obj in self.tiers:"
                remaining_part = stmt_clean[colon_pos + 1:].strip()  # "if obj.name==tn:to=obj"
                
                statements.append(for_part)
                
                # Handle the content after the for loop colon
                if remaining_part:
                    # Check if it contains nested control structures (like if statements)
                    if 'if ' in remaining_part and ':' in remaining_part:
                        # This is likely a nested if statement: "if obj.name==tn:to=obj"
                        if_colon_pos = remaining_part.find(':')
                        if_part = remaining_part[:if_colon_pos + 1]  # "if obj.name==tn:"
                        if_body = remaining_part[if_colon_pos + 1:].strip()  # "to=obj"
                        
                        statements.append(f"    {if_part}")
                        if if_body:
                            statements.append(f"        {if_body}")
                            
                        # The break should be at the if level (nested inside the for loop)
                        if i + 1 < len(raw_statements) and raw_statements[i + 1].strip() in ['break', 'continue']:
                            statements.append(f"        {raw_statements[i + 1].strip()}")
                            self.logger.debug(f"   ✅ Moved '{raw_statements[i + 1].strip()}' inside if statement within for loop")
                            # Mark the break statement as processed
                            raw_statements[i + 1] = ""
                    else:
                        # Simple content after for loop
                        statements.append(f"    {remaining_part}")
                        
                        # Check if next statement is break/continue - move it inside the loop
                        if i + 1 < len(raw_statements) and raw_statements[i + 1].strip() in ['break', 'continue']:
                            statements.append(f"    {raw_statements[i + 1].strip()}")
                            self.logger.debug(f"   ✅ Moved '{raw_statements[i + 1].strip()}' inside for loop")
                            # Mark the break statement as processed
                            raw_statements[i + 1] = ""
                continue
            
            # Skip empty statements (already processed break/continue)
            if not stmt_clean:
                continue
                
            statements.append(stmt)
        
        return statements

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
        
        # Check for identifier contexts where we should NEVER quote
        identifier_patterns = [
            rf'from\s+{re.escape(original_hash)}\s+import',     # from hash import
            rf'import\s+{re.escape(original_hash)}',            # import hash
            rf'{re.escape(original_hash)}\s*\.',                # hash.method()
            rf'\.\s*{re.escape(original_hash)}\s*\(',           # obj.hash()
            rf'class\s+{re.escape(original_hash)}',             # class hash:
            rf'def\s+{re.escape(original_hash)}',               # def hash():
        ]
        
        for pattern in identifier_patterns:
            if re.search(pattern, context):
                self.logger.debug(f"   ✅ Used as identifier/import, never quote: {clean_value}")
                return clean_value
        
        # Check if used as dictionary key: {key: or [key]
        dict_key_patterns = [
            rf'\{{\s*{re.escape(original_hash)}\s*:',                     # {hash:
            rf'\{{\s*[^,}}]*,\s*{re.escape(original_hash)}\s*:',         # {something,hash:
            rf',\s*{re.escape(original_hash)}\s*:',                      # ,hash: (anywhere in dict)
            rf'\[\s*{re.escape(original_hash)}\s*\]',                    # [hash]
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

    def _fix_inline_statements(self, content: str) -> str:
        """Fix inline statements separated by semicolons with intelligent indentation for break/continue/pass."""
        self.logger.info("🔧 Fixing inline statements and indentation...")
        
        lines = content.split('\n')
        fixed_lines = []
        
        for line_num, line in enumerate(lines):
            stripped = line.strip()
            
            # Skip empty lines and comments
            if not stripped or stripped.startswith('#'):
                fixed_lines.append(line)
                continue
            
            # Check if line contains semicolon-separated statements
            if ';' not in stripped:
                fixed_lines.append(line)
                continue
            
            self.logger.debug(f"   🔍 Processing line {line_num + 1}: {stripped[:100]}...")
            
            # Split on semicolons while respecting nested structures
            statements = self._split_statements_with_indentation(stripped)
            
            if len(statements) <= 1:
                fixed_lines.append(line)
                continue
            
            base_indent = len(line) - len(line.lstrip())
            
            # Process each statement with intelligent indentation
            for i, stmt in enumerate(statements):
                stmt = stmt.strip()
                if not stmt:
                    continue
                
                # CRITICAL FIX: Smart handling of break/continue/pass statements
                if stmt in ['break', 'continue', 'pass']:
                    # Check if the previous statement was a colon statement (control structure)
                    previous_stmt = statements[i-1].strip() if i > 0 else ''
                    has_preceding_colon = previous_stmt.endswith(':')
                    
                    if has_preceding_colon:
                        # Preceded by control structure - indent normally
                        indent = self._calculate_statement_indentation(stmt, fixed_lines, base_indent)
                        fixed_lines.append(' ' * indent + stmt)
                        self.logger.debug(f"   ✅ {stmt} after colon statement - using calculated indent: {indent}")
                    else:
                        # NOT preceded by colon - keep at current indentation level
                        # This preserves the original scope context
                        fixed_lines.append(' ' * base_indent + stmt)
                        self.logger.debug(f"   ✅ {stmt} without preceding colon - keeping base indent: {base_indent}")
                    
                    # For break/continue, remaining statements may be unreachable in some contexts
                    if stmt in ['break', 'continue']:
                        self.logger.debug(f"   ⚠️ Found {stmt} - continuing with remaining statements")
                    
                    continue
                
                # Handle other control flow statements
                if self._is_flow_control_statement(stmt):
                    # Control flow statements maintain base indentation
                    fixed_lines.append(' ' * base_indent + stmt)
                elif stmt.startswith('return'):
                    # Return statements maintain base indentation and BREAK the flow
                    fixed_lines.append(' ' * base_indent + stmt)
                    # CRITICAL: Don't add remaining statements after return - they're unreachable
                    self.logger.debug(f"   ⚠️ Stopping after return statement: {stmt}")
                    break
                elif stmt.startswith('raise'):
                    # Raise also breaks the flow
                    fixed_lines.append(' ' * base_indent + stmt)
                    break
                else:
                    # Regular statements get proper indentation
                    if i == 0:
                        # First statement keeps original indentation
                        fixed_lines.append(' ' * base_indent + stmt)
                    else:
                        # Subsequent statements need context-aware indentation
                        indent = self._calculate_statement_indentation(stmt, fixed_lines, base_indent)
                        fixed_lines.append(' ' * indent + stmt)
        
        result = '\n'.join(fixed_lines)
        self.logger.info(f"✅ Fixed inline statements with intelligent break/continue/pass handling")
        return result
    
    def _is_flow_control_statement(self, stmt: str) -> bool:
        """Check if statement is a flow control statement."""
        flow_keywords = ['if ', 'elif ', 'else:', 'for ', 'while ', 'try:', 'except ', 'finally:', 'with ']
        return any(stmt.startswith(keyword) for keyword in flow_keywords)
    
    def _calculate_statement_indentation(self, stmt: str, previous_lines: List[str], base_indent: int) -> int:
        """Calculate proper indentation for a statement based on context."""
        if not previous_lines:
            return base_indent
        
        # Get the last non-empty line for context
        last_line = None
        for line in reversed(previous_lines):
            if line.strip():
                last_line = line
                break
        
        if not last_line:
            return base_indent
        
        last_stripped = last_line.strip()
        last_indent = len(last_line) - len(last_line.lstrip())
        
        # If the last line was a control structure that opened a block
        if (last_stripped.endswith(':') and 
            any(last_stripped.startswith(kw) for kw in ['if ', 'elif ', 'else:', 'for ', 'while ', 'try:', 'except ', 'with '])):
            # This statement should be inside the block
            return last_indent + 4
        
        # If this is a dedent keyword
        if stmt.startswith(('elif ', 'else:', 'except ', 'finally:')):
            # Align with the original control structure
            return max(base_indent, last_indent - 4)
        
        # Default: same level as the last statement
        return last_indent

    def _final_syntax_cleanup(self, content: str) -> str:
        """Final cleanup to ensure valid Python syntax - more conservative approach."""
        lines = content.split('\n')
        cleaned_lines = []
        
        for i, line in enumerate(lines):
            stripped = line.strip()
            indent = len(line) - len(line.lstrip())
            
            # Only add pass for TRULY empty control structures
            # Be much more conservative - only add pass if we're sure it's needed
            if (stripped in ['else:', 'try:', 'finally:'] or
                stripped == 'except:' or  # Bare except
                re.match(r'^except\s+\w+(\s+as\s+\w+)?:$', stripped) or  # except Exception [as var]:
                re.match(r'^(if|elif|for|while|with|def|class)\s+[^:]*:$', stripped)):
                
                # IMPROVED: Only check the next actual line (ignore empty lines)
                has_body_content = False
                has_existing_pass = False
                
                # Look at the very next non-empty line only 
                for j in range(i + 1, min(i + 3, len(lines))):  # Only look 2 lines ahead max
                    next_line = lines[j].strip()
                    if not next_line:  # Skip empty lines
                        continue
                        
                    next_indent = len(lines[j]) - len(lines[j].lstrip())
                    
                    # If we hit a line at same or lower indentation, we've reached the end
                    if next_indent <= indent:
                        # Check if this is a continuation (like another except block)
                        if (next_line.startswith(('except ', 'elif ', 'else:', 'finally:')) and 
                            next_indent == indent):
                            # This is a continuation - no content in current block
                            break
                        elif next_indent < indent:
                            # Definitely end of block
                            break
                        # If same indent but not a continuation, might have content
                    
                    # Check if this line belongs to our control structure
                    if next_indent > indent:
                        if next_line == 'pass':
                            has_existing_pass = True
                            break
                        elif next_line.startswith('#'):
                            # Comments don't count - continue looking
                            continue
                        else:
                            # Found actual content
                            has_body_content = True
                            break
                    
                    # Only check one actual line to be conservative
                    break
                
                cleaned_lines.append(line)
                
                # CRITICAL: Only add pass for truly empty blocks that are single statements
                # Don't add pass if this looks like it's part of a larger structure
                if not has_body_content and not has_existing_pass:
                    # Extra check: don't add pass if this is likely a test case or incomplete snippet
                    if not (stripped.endswith(':') and i == len(lines) - 1):  # Don't add to last line
                        cleaned_lines.append(' ' * (indent + 4) + 'pass')
            else:
                cleaned_lines.append(line)
        
        return '\n'.join(cleaned_lines)
    
    def _fix_cai3_syntax_without_try_except(self, content: str) -> str:
        """
        Fix CAI3 syntax issues without handling T{}X{} structures.
        
        T{}X{} structures should already be translated by this point.
        """
        self.logger.info("🔧 Starting CAI3 syntax fixing (without T{}X{} translation)...")
        
        # CRITICAL: Check if content is still in CAI3 format
        cai3_markers = ['#C3L', 'CAI3:', 'P:', 'T:', 'B#', 'I:', 'D:', 'X:']
        if any(marker in content for marker in cai3_markers):
            self.logger.info("🚨 Content appears to be in CAI3 format - SKIPPING syntax fixes")
            return content
        
        original_content = content
        
        # Step 1: Pre-process to fix CAI3-specific issues (without T{}X{} translation)
        content = self._preprocess_cai3_content_without_try_except(content)
        
        # Step 2: Parse into logical blocks using AST-aware approach
        blocks = self._parse_into_logical_blocks(content)
        
        # Step 3: Fix each block individually
        fixed_blocks = []
        for block in blocks:
            fixed_block = self._fix_block_syntax(block)
            fixed_blocks.append(fixed_block)
        
        # Step 4: Reassemble with proper structure
        content = self._reassemble_blocks(fixed_blocks)
        
        # Step 5: Apply Black formatting with fallback
        formatted_content = self._apply_black_with_fallback(content)
        
        # Step 6: Final syntax cleanup
        final_content = self._final_syntax_cleanup(formatted_content)
        
        self.logger.info("✅ Applied comprehensive syntax fixes (without T{}X{} translation)")
        return final_content
    
    def _preprocess_cai3_content_without_try_except(self, content: str) -> str:
        """
        Preprocess CAI3 content without handling T{}X{} structures.
        
        This is a version of _preprocess_cai3_content that skips T{}X{} translation
        since it should have already been done earlier in the pipeline.
        """
        self.logger.info("🔧 Pre-processing CAI3 content (skipping T{}X{} translation)...")
        
        # Fix CAI3 concatenation issues
        content = self._fix_cai3_concatenations(content)
        
        # CRITICAL: Fix inline statements separated by semicolons
        content = self._fix_inline_statements(content)
        
        # Fix malformed try-except blocks (but don't translate T{}X{} structures)
        content = self._fix_malformed_try_except(content)
        
        # Fix function/method call patterns
        content = self._fix_function_call_patterns(content)
        
        # Fix incomplete dictionary/list patterns
        content = self._fix_incomplete_structures(content)
        
        # Fix malformed loops and control structures
        content = self._fix_control_structures(content)
        
        return content

    def _fix_malformed_try_except(self, content: str) -> str:
        """
        Fix malformed try/except blocks where exception variables are incorrectly mapped.
        
        This method specifically handles cases where 'ex' has been mapped to 'exists'
        in except clauses, creating invalid syntax like 'except Exception as exists:'.
        Also fixes variable references inside except blocks.
        """
        # Pattern to find malformed except clauses
        # Look for 'except Exception as {word}:' where {word} is not a valid exception variable
        malformed_pattern = r'except\s+Exception\s+as\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*:'
        
        def fix_except_clause(match):
            exception_var = match.group(1)
            
            # Common malformed mappings that should be fixed
            malformed_mappings = {
                'exists': 'e',
                'error': 'e', 
                'exception': 'e',
                'ex': 'e'  # In case it wasn't caught earlier
            }
            
            if exception_var in malformed_mappings:
                correct_var = malformed_mappings[exception_var]
                return f'except Exception as {correct_var}:'
            
            # If it's already a reasonable variable name (single letter or ends with 'e'), keep it
            if len(exception_var) == 1 or exception_var.endswith('e'):
                return match.group(0)
            
            # Default to 'e' for any other suspicious mappings
            return 'except Exception as e:'
        
        # Apply the fix to except clauses
        fixed_content = re.sub(malformed_pattern, fix_except_clause, content)
        
        # Now fix variable references inside except blocks
        lines = fixed_content.split('\n')
        fixed_lines = []
        in_except_block = False
        current_except_var = None
        
        for line in lines:
            stripped = line.strip()
            
            # Check if we're entering an except block
            except_match = re.match(r'except\s+Exception\s+as\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*:', stripped)
            if except_match:
                in_except_block = True
                current_except_var = except_match.group(1)
                fixed_lines.append(line)
                continue
            
            # Check if we're leaving the except block (dedent or new control structure)
            if in_except_block:
                if line and not line.startswith('    '):  # Back to base level
                    in_except_block = False
                    current_except_var = None
                elif stripped.startswith(('try:', 'except:', 'finally:', 'else:', 'if ', 'for ', 'while ', 'def ', 'class ')):
                    in_except_block = False
                    current_except_var = None
            
            # If we're in an except block, fix malformed variable references
            if in_except_block and current_except_var:
                # Fix common malformed variables that should reference the exception
                malformed_vars = ['exists', 'error', 'exception']
                for malformed_var in malformed_vars:
                    if malformed_var in line and current_except_var != malformed_var:
                        # Replace malformed variable with correct exception variable
                        line = re.sub(r'\b' + re.escape(malformed_var) + r'\b', current_except_var, line)
            
            fixed_lines.append(line)
        
        return '\n'.join(fixed_lines)

    def _fix_function_call_patterns(self, content: str) -> str:
        """Fix function call patterns - stub for testing."""
        return content
    
    def _fix_incomplete_structures(self, content: str) -> str:
        """Fix incomplete structures - stub for testing."""
        return content
    
    def _fix_control_structures(self, content: str) -> str:
        """Fix control structures - stub for testing."""
        return content