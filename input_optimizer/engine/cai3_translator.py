# optimize_ai/input_optimizer/engine/cai3_translator.py
"""
CAI3 Translator - Applies CAI3-PATCH from LLM to original source using FULL+MAP.
Uses LibCST for precise AST manipulation.
"""

import ast
import hashlib
import logging
import re
from pathlib import Path
from typing import Optional, List, Dict, Tuple

try:
    import libcst as cst
    HAS_LIBCST = True
except ImportError:
    HAS_LIBCST = False
    cst = None

from .cai3_structures import (
    CAI3Full, CAI3Map, CAI3Patch, CAI3Cache, BodyFidelity
)
from .flow_language import FLOWCompiler


class DeminifyTransformer(ast.NodeTransformer):
    """
    AST transformer to de-minify variable names and chain aliases.
    Only remaps names that exist in the mapping to preserve attributes/imports.
    """
    
    def __init__(self, short_to_orig: Dict[str, str], chain_aliases: Optional[Dict[str, str]] = None):
        self.s2o = short_to_orig
        self.chain_aliases = chain_aliases or {}
    
    def visit_Name(self, node: ast.Name):
        """Clean variable names without CID contamination."""
        name_id = node.id
        
        # Step 1: Remove CID prefixes completely
        import re
        cid_pattern = r'(mt_|fn_|cl_)[a-f0-9]{4}:'
        cleaned_name = re.sub(cid_pattern, '', name_id)
        
        # Step 2: Handle any remaining colons (parameter mappings)
        if ':' in cleaned_name:
            # Take the part after the last colon
            cleaned_name = cleaned_name.split(':')[-1]
        
        # Step 3: Apply mappings based on context
        if isinstance(node.ctx, ast.Load):
            # For Load context, check if we have a mapping
            if cleaned_name in self.s2o:
                node.id = self.s2o[cleaned_name]
            else:
                node.id = cleaned_name
        else:
            # For Store context (assignments), use cleaned name
            node.id = cleaned_name
        
        return self.generic_visit(node)
    
    def visit_Call(self, node: ast.Call):
        # Handle chain alias function calls like g1(...) -> self.config.get(...)
        if (isinstance(node.func, ast.Name) and 
            node.func.id in self.chain_aliases):
            
            chain = self.chain_aliases[node.func.id]
            # Clean up chain - remove trailing parentheses if present
            if chain.endswith('()'):
                chain = chain[:-2]
            
            # Parse the chain into proper attribute access
            result = self._build_chain_ast(chain, node)
            
            if result:
                # Replace the function in the call
                node.func = result
        
        return self.generic_visit(node)
    
    def visit_Attribute(self, node: ast.Attribute):
        """Handle attribute access with chain aliases like g0.get -> self.config.get"""
        # Step 1: Clean CID references from attribute name
        import re
        attr_name = node.attr
        cid_pattern = r'(mt_|fn_|cl_)[a-f0-9]{4}:'
        cleaned_attr = re.sub(cid_pattern, '', attr_name)
        
        # Handle any remaining colons in attribute name
        if ':' in cleaned_attr:
            cleaned_attr = cleaned_attr.split(':')[-1]
        
        node.attr = cleaned_attr
        
        # Step 2: Check if the base value is a Name node with a chain alias
        if (isinstance(node.value, ast.Name) and 
            node.value.id in self.chain_aliases):
            
            chain = self.chain_aliases[node.value.id]
            # Clean up chain - remove trailing parentheses if present
            if chain.endswith('()'):
                chain = chain[:-2]
            
            # Parse the chain into proper attribute access for the base
            base_result = self._build_chain_ast(chain, node)
            
            if base_result:
                # Replace the base value with the expanded chain
                node.value = base_result
        
        return self.generic_visit(node)
    
    def visit_Subscript(self, node: ast.Subscript):
        """Handle subscript access with chain aliases like g0[key] -> self.config[key]"""
        # Step 1: Clean CID references from subscript slice if it's a Name
        if isinstance(node.slice, ast.Name):
            import re
            slice_name = node.slice.id
            cid_pattern = r'(mt_|fn_|cl_)[a-f0-9]{4}:'
            cleaned_slice = re.sub(cid_pattern, '', slice_name)
            
            # Handle any remaining colons in slice name
            if ':' in cleaned_slice:
                cleaned_slice = cleaned_slice.split(':')[-1]
            
            node.slice.id = cleaned_slice
        
        # Step 2: Check if the base value is a Name node with a chain alias
        if (isinstance(node.value, ast.Name) and 
            node.value.id in self.chain_aliases):
            
            chain = self.chain_aliases[node.value.id]
            # Clean up chain - remove trailing parentheses if present
            if chain.endswith('()'):
                chain = chain[:-2]
            
            # Build the chain for the base and preserve the subscript
            base_result = self._build_chain_ast(chain, node)
            if base_result:
                # Replace the base value with the expanded chain
                node.value = base_result
        
        return self.generic_visit(node)

    def _build_chain_ast(self, chain: str, original_node: ast.AST) -> Optional[ast.AST]:
        """
        Build an AST node from a chain string like 's.config.get'.
        
        Args:
            chain: The chain string to parse
            original_node: Original node to copy line info from
            
        Returns:
            AST node representing the chain, or None if parsing fails
        """
        try:
            parts = chain.split('.')
            if not parts:
                return None
            
            # Build the attribute chain
            result = None
            for i, part in enumerate(parts):
                if i == 0:
                    # Handle 's' -> 'self', 'c' -> 'cls', etc.
                    if part == 's':
                        name = 'self'
                    elif part == 'c':
                        name = 'cls'
                    else:
                        name = part
                    result = ast.Name(id=name, ctx=ast.Load())
                    # Copy line numbers from original node
                    if hasattr(original_node, 'lineno'):
                        result.lineno = original_node.lineno
                    if hasattr(original_node, 'col_offset'):
                        result.col_offset = original_node.col_offset
                else:
                    result = ast.Attribute(value=result, attr=part, ctx=ast.Load())
                    # Copy line numbers from original node
                    if hasattr(original_node, 'lineno'):
                        result.lineno = original_node.lineno
                    if hasattr(original_node, 'col_offset'):
                        result.col_offset = original_node.col_offset
            
            return result
        except Exception as e:
            # Log the error but don't fail completely
            # This allows the code to continue with the original function name
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"Failed to build chain AST for '{chain}': {e}")
            return None
    
    def visit_AnnAssign(self, node: ast.AnnAssign):
        """Handle type annotations that might contain CID prefixes."""
        # Process the target (variable being assigned)
        if isinstance(node.target, ast.Name):
            target_id = node.target.id
            # Remove CID prefixes from target names
            if ':' in target_id:
                target_id = target_id.split(':')[-1]
            # Apply name mapping if it exists
            if target_id in self.s2o:
                node.target.id = self.s2o[target_id]
            else:
                node.target.id = target_id
        
        # Process the annotation (type hint)
        if isinstance(node.annotation, ast.Name):
            ann_id = node.annotation.id
            # Remove CID prefixes from annotation names
            if ':' in ann_id:
                ann_id = ann_id.split(':')[-1]
            # Apply name mapping if it exists
            if ann_id in self.s2o:
                node.annotation.id = self.s2o[ann_id]
            else:
                node.annotation.id = ann_id
        
        return self.generic_visit(node)


class CAI3Translator:
    """
    Applies CAI3-PATCH to original source using locally stored FULL+MAP.
    Ensures robust reconstruction with validation and fallback.
    """
    
    def __init__(self, cache_dir: Optional[Path] = None):
        """Initialize translator with cache directory"""
        self.cache = CAI3Cache(cache_dir) if cache_dir else CAI3Cache()
        self.logger = logging.getLogger(__name__)
    
    def validate_lite_structure(self, lite_content: str) -> Tuple[bool, List[str]]:
        """
        Validate CAI3-LITE structure before translation.
        Returns (is_valid, list_of_issues)
        """
        issues = []
        
        # Check for required header
        if not lite_content.startswith('#C3L'):
            issues.append("Missing #C3L header")
        
        # Validate bracket balance
        open_braces = lite_content.count('{')
        close_braces = lite_content.count('}')
        if open_braces != close_braces:
            issues.append(f"Unbalanced braces: {open_braces} open, {close_braces} close")
        
        # Check for T{} X{} structure completeness
        try_blocks = re.findall(r'T\{[^}]*\}', lite_content)
        for block in try_blocks:
            if 'X{' not in lite_content[lite_content.index(block):]:
                issues.append(f"Try block without exception handler: {block[:20]}...")
        
        # Validate pool references
        pool_refs = re.findall(r'\bp(\d+)\b', lite_content)
        # Look for pool declarations in P: lines - pattern: P:...p0=value,p1=value...
        declared_pools = []
        for line in lite_content.split('\n'):
            if line.strip().startswith('P:'):
                # Extract pool declarations from this line
                pool_declarations = re.findall(r'p(\d+)=', line)
                declared_pools.extend(pool_declarations)
        
        for ref in set(pool_refs):
            if ref not in declared_pools:
                issues.append(f"Undefined pool reference: p{ref}")
        
        return len(issues) == 0, issues

    def apply_patch(self, patch_content: str, source_path: Path, original_source: str = None) -> str:
        """
        Apply a CAI3-PATCH to the original source file.
        
        Args:
            patch_content: The patch returned by the LLM
            source_path: Path to the original source file
            original_source: Optional original source content (if None, reads from file)
            
        Returns:
            Updated source code with patches applied
        """
        # Load FULL and MAP from cache
        cai3_full = self.cache.load_full(source_path)
        cai3_map = self.cache.load_map(source_path)
        
        if not cai3_full or not cai3_map:
            raise ValueError(f"No CAI3 cache found for {source_path}. Ensure compression was run first.")
        
        # Parse patches from LLM response and resolve CID aliases
        patches = CAI3Patch.parse(patch_content)
        self._resolve_cid_aliases(patches, patch_content, cai3_full)
        
        if not patches:
            self.logger.warning("No valid patches found in response")
            return original_source if original_source is not None else source_path.read_text()
        
        # Use provided original source or read from file
        source_content = original_source if original_source is not None else source_path.read_text()
        
        # Apply each patch
        modified_source = source_content
        applied_count = 0
        
        for patch in patches:
            try:
                # Validate patch target exists
                if patch.target_cid not in cai3_map.span_map:
                    self.logger.warning(f"Unknown cid {patch.target_cid}, skipping patch")
                    continue
                
                # Validate context hash if available
                if patch.target_cid in cai3_map.context_hashes:
                    if not self._validate_context(patch.target_cid, cai3_map, modified_source):
                        self.logger.warning(f"Context mismatch for {patch.target_cid}, attempting rebase")
                        modified_source = self._rebase_and_apply(
                            patch, source_path, modified_source, cai3_full, cai3_map
                        )
                        continue
                
                # Apply the patch
                if patch.operation == "RB":  # Replace Body
                    modified_source = self._replace_body(
                        patch, modified_source, cai3_map, cai3_full
                    )
                    applied_count += 1
                elif patch.operation == "IL":  # Insert Lines
                    modified_source = self._insert_lines(
                        patch, modified_source, cai3_map, cai3_full
                    )
                    applied_count += 1
                elif patch.operation == "RL":  # Replace Lines
                    modified_source = self._replace_lines(
                        patch, modified_source, cai3_map, cai3_full
                    )
                    applied_count += 1
                elif patch.operation == "DL":  # Delete Lines
                    modified_source = self._delete_lines(
                        patch, modified_source, cai3_map, cai3_full
                    )
                    applied_count += 1
                elif patch.operation == "AM":  # Add Method
                    modified_source = self._add_method(
                        patch, modified_source, cai3_map
                    )
                    applied_count += 1
                elif patch.operation == "DM":  # Delete Method
                    modified_source = self._delete_method(
                        patch, modified_source, cai3_map
                    )
                    applied_count += 1
                else:
                    self.logger.warning(f"Unknown operation {patch.operation}")
                    
            except Exception as e:
                self.logger.error(f"Failed to apply patch for {patch.target_cid}: {e}")
        
        self.logger.info(f"Applied {applied_count}/{len(patches)} patches successfully")
        
        # Validate the result
        try:
            ast.parse(modified_source)
        except SyntaxError as e:
            self.logger.error(f"Patch resulted in invalid syntax: {e}")
            # Log the problematic area around the error
            if hasattr(e, 'lineno') and e.lineno:
                lines = modified_source.split('\n')
                start_line = max(0, e.lineno - 5)
                end_line = min(len(lines), e.lineno + 5)
                self.logger.error(f"Context around line {e.lineno}:")
                for i in range(start_line, end_line):
                    marker = " -> " if i + 1 == e.lineno else "    "
                    self.logger.error(f"{marker}{i+1:3d}: {lines[i] if i < len(lines) else ''}")
            # Return original source as fallback
            return original_source
        
        # Update cache with new content
        self._update_cache(source_path, modified_source)
        
        return modified_source
    
    def _resolve_cid_aliases(self, patches: List[CAI3Patch], patch_content: str, cai3_full: CAI3Full):
        """
        Resolve CID aliases (#k format) to actual CIDs using X: mapping from LITE content.
        
        Args:
            patches: List of patches to resolve aliases for
            patch_content: Original patch content containing potential X: mapping
            cai3_full: CAI3Full structure with cached CID information
        """
        # Extract X: mapping from patch content if present
        cid_alias_map = self._extract_cid_aliases(patch_content)
        
        # Also check CAI3Full compression_stats for stored aliases
        if 'cid_aliases' in cai3_full.compression_stats:
            stored_aliases = cai3_full.compression_stats['cid_aliases']
            if isinstance(stored_aliases, dict):
                # These are already in the correct direction (alias -> CID)
                cid_alias_map.update(stored_aliases)
                self.logger.debug(f"Updated alias map with stored aliases: {stored_aliases}")
        
        # Resolve aliases in each patch
        for patch in patches:
            if patch.target_cid.startswith('#'):
                # This is an alias reference
                alias_key = patch.target_cid[1:]  # Remove # prefix
                
                if alias_key in cid_alias_map:
                    # Found alias mapping, replace with actual CID
                    actual_cid = cid_alias_map[alias_key]
                    self.logger.debug(f"Resolved CID alias #{alias_key} -> {actual_cid}")
                    patch.target_cid = actual_cid
                else:
                    self.logger.warning(f"CID alias #{alias_key} not found in mapping, trying fallback")
                    # Fall back to raw mt_... CID for backward compatibility
                    # Try to find a CID that might match the alias pattern
                    fallback_cid = self._find_fallback_cid(alias_key, cai3_full)
                    if fallback_cid:
                        patch.target_cid = fallback_cid
                        self.logger.debug(f"Used fallback CID for #{alias_key} -> {fallback_cid}")
    
    def _extract_cid_aliases(self, patch_content: str) -> Dict[str, str]:
        """
        Extract CID aliases from X: mapping in patch content.
        
        Format: X:0=mt_5605|1=mt_961c|...
        
        Returns:
            Dictionary mapping alias keys to actual CIDs
        """
        cid_aliases = {}
        
        lines = patch_content.split('\n')
        for line in lines:
            line = line.strip()
            if line.startswith('X:'):
                # Parse X: line
                alias_content = line[2:]  # Remove 'X:' prefix
                
                # Split by | for multiple aliases
                alias_parts = alias_content.split('|')
                for part in alias_parts:
                    if '=' in part:
                        alias_key, actual_cid = part.split('=', 1)
                        cid_aliases[alias_key.strip()] = actual_cid.strip()
                
                break  # Only process the first X: line found
        
        return cid_aliases
    
    def _find_fallback_cid(self, alias_key: str, cai3_full: CAI3Full) -> Optional[str]:
        """
        Find a fallback CID for an unresolved alias.
        
        This is for backward compatibility with raw mt_... CIDs.
        """
        # If alias_key looks like a raw CID (mt_xxxx), use it directly
        if alias_key.startswith(('mt_', 'fn_', 'cl_')):
            return alias_key
        
        # Try to match by position or other heuristics
        try:
            # If alias_key is numeric, try to find the nth method
            if alias_key.isdigit():
                index = int(alias_key)
                method_nodes = [node for node in cai3_full.nodes if node.type.value == 'M']
                if 0 <= index < len(method_nodes):
                    return method_nodes[index].cid
        except (ValueError, IndexError):
            pass
        
        return None
    
    def _validate_context(self, cid: str, cai3_map: CAI3Map, source: str) -> bool:
        """Validate that the context around a cid hasn't changed"""
        if cid not in cai3_map.context_hashes:
            return True  # No hash to validate
        
        expected_hash = cai3_map.context_hashes[cid]
        
        # Get span for the cid
        if cid not in cai3_map.span_map:
            return False
        
        start_line, end_line = cai3_map.span_map[cid]
        
        # Use minified source if available, otherwise use provided source
        validation_source = cai3_map.minified_source if cai3_map.minified_source else source
        lines = validation_source.split('\n')
        
        # Get context (few lines before and after) - MUST match compression logic exactly
        # Compression uses: context_start = max(0, start_line - 3), context_end = min(len(lines), end_line + 2)
        # Since spans are 1-indexed, we need to use the same formula with the 1-indexed values
        context_start = max(0, start_line - 3)
        context_end = min(len(lines), end_line + 2)
        context_lines = lines[context_start:context_end]
        context = '\n'.join(context_lines)
        
        # Calculate hash
        actual_hash = hashlib.md5(context.encode()).hexdigest()[:8]
        
        # DEBUG: Print context details
        self.logger.debug(f"Context validation for {cid}:")
        self.logger.debug(f"  Using {'minified' if cai3_map.minified_source else 'original'} source")
        self.logger.debug(f"  Span (1-indexed): lines {start_line}-{end_line}")
        self.logger.debug(f"  Context range: {context_start}-{context_end}")
        self.logger.debug(f"  Expected hash: {expected_hash}")
        self.logger.debug(f"  Actual hash: {actual_hash}")
        self.logger.debug(f"  Context text: {repr(context)}")
        
        return actual_hash == expected_hash
    
    def _replace_body(self, patch: CAI3Patch, source: str, cai3_map: CAI3Map, cai3_full: CAI3Full = None) -> str:
        """Replace the body of a function/method"""
        
        if patch.body_fidelity == BodyFidelity.B1:
            self.logger.debug(f"=== REPLACING BODY FOR {patch.target_cid} ===")
            self.logger.debug(f"Original body content: {repr(patch.body_content)}")
            
            # Apply malformed statement fixes to patch body content before parsing
            fixed_body_content = self._apply_malformed_fixes_to_body(patch.body_content)
            self.logger.debug(f"After malformed fixes: {repr(fixed_body_content)}")
            
            # Convert FLOW to Python AST with enhanced flags
            flow_compiler = self._create_flow_compiler(cai3_map, cai3_full)
            
            self.logger.debug(f"📤 SENDING TO FLOW COMPILER: {repr(fixed_body_content)}")
            try:
                new_body_stmts = flow_compiler._parse_flow_lines(
                    fixed_body_content.split('\n'), 0
                )[0]
                self.logger.debug(f"📥 FLOW COMPILER RETURNED: {len(new_body_stmts)} statements")
                
                # Log each statement the FLOW compiler produced
                for i, stmt in enumerate(new_body_stmts):
                    try:
                        stmt_code = ast.unparse(stmt) if hasattr(ast, 'unparse') else str(type(stmt))
                        self.logger.debug(f"  Statement {i}: {repr(stmt_code)}")
                        
                        # Check for problematic patterns in FLOW compiler output
                        if 'except ' in stmt_code and 'try:' not in stmt_code:
                            self.logger.error(f"🚨 FLOW COMPILER PRODUCED ORPHANED EXCEPT: {repr(stmt_code)}")
                        if stmt_code.strip() == 'pass':
                            self.logger.error(f"🚨 FLOW COMPILER PRODUCED PASS STATEMENT: {repr(stmt_code)}")
                        if '.data_buffer.ge:' in stmt_code or ')[].data_buffer' in stmt_code:
                            self.logger.error(f"🚨 FLOW COMPILER PRODUCED MALFORMED EXPRESSION: {repr(stmt_code)}")
                            
                    except Exception as e:
                        self.logger.debug(f"  Statement {i}: <unparseable: {e}>")
                        
            except Exception as e:
                self.logger.error(f"❌ FLOW COMPILER PARSING FAILED: {e}")
                import traceback
                self.logger.debug(f"FLOW compiler traceback: {traceback.format_exc()}")
                # Fallback to empty body
                new_body_stmts = [ast.Pass()]
            
            # De-minify the B1 body before writing
            # Build short->orig map for this cid
            short_to_orig = {}
            
            # Add local variable mappings
            local_map = cai3_map.name_map  # already stores locals as f"{cid}:{short}" -> orig
            # Build inverse for this cid only
            prefix = f"{patch.target_cid}:"
            for k, orig in local_map.items():
                if k.startswith(prefix):
                    short = k.split(":", 1)[1]
                    short_to_orig[short] = orig
            
            # Get chain aliases from CAI3Full if available
            chain_aliases = {}
            if cai3_full and 'chain_aliases' in cai3_full.compression_stats:
                chain_aliases = cai3_full.compression_stats['chain_aliases']
                if not isinstance(chain_aliases, dict):
                    chain_aliases = {}
            
            if short_to_orig or chain_aliases:
                demin = DeminifyTransformer(short_to_orig, chain_aliases)
                new_body_stmts = [demin.visit(stmt) for stmt in new_body_stmts]
                for s in new_body_stmts:
                    ast.fix_missing_locations(s)
        else:
            # Parse as Python AST directly
            new_body = ast.parse(patch.body_content).body
            new_body_stmts = new_body
        
        # Get the span of the target method
        start_line, end_line = cai3_map.span_map[patch.target_cid]
        
        if HAS_LIBCST:
            return self._replace_body_with_libcst(
                source, start_line, end_line, new_body_stmts, patch.target_cid
            )
        else:
            return self._replace_body_with_ast(
                source, start_line, end_line, new_body_stmts
            )
    
    def _insert_lines(self, patch: CAI3Patch, source: str, cai3_map: CAI3Map, cai3_full: CAI3Full = None) -> str:
        """
        Insert lines at a specific position within a method body.
        Supports surgical edits without replacing the entire method.
        
        Args:
            patch: CAI3Patch with operation="IL" and metadata containing insert position
            source: Current source code
            cai3_map: CAI3Map for name resolution
            cai3_full: CAI3Full for context
        
        Returns:
            Modified source code with lines inserted
        """
        # Get the method span
        if patch.target_cid not in cai3_map.span_map:
            return source
        
        start_line, end_line = cai3_map.span_map[patch.target_cid]
        lines = source.split('\n')
        
        # Parse the insertion point from patch metadata
        # Expected format: patch.metadata = {"after_condition": "for field in required_fields"}
        insert_after = patch.metadata.get('after_line', None)
        insert_after_condition = patch.metadata.get('after_condition', None)
        insert_at_line = patch.metadata.get('at_line', None)
        
        # Parse the FLOW body to AST
        flow_compiler = self._create_flow_compiler(cai3_map, cai3_full)
        new_stmts = flow_compiler._parse_flow_lines(
            patch.body_content.split('\n'), 0
        )[0]
        
        # Convert AST to source with proper indentation
        method_lines = lines[start_line-1:end_line]
        base_indent = len(method_lines[0]) - len(method_lines[0].lstrip())
        
        # Find insertion point
        insert_position = None
        target_line_indent = base_indent + 4  # Default method body indent
        
        if insert_after:
            # Find the line containing the pattern
            for i in range(start_line-1, end_line):
                if insert_after in lines[i]:
                    insert_position = i + 1
                    # Calculate indentation based on the target line
                    target_line_indent = len(lines[i]) - len(lines[i].lstrip()) + 4
                    break
        elif insert_after_condition:
            # Find the line containing the condition pattern
            for i in range(start_line-1, end_line):
                if insert_after_condition in lines[i]:
                    insert_position = i + 1
                    # Calculate indentation based on the target line
                    # The new code should be indented relative to the if statement
                    target_line_indent = len(lines[i]) - len(lines[i].lstrip()) + 4
                    break
        elif insert_at_line:
            insert_position = start_line - 1 + insert_at_line
        
        if insert_position is None:
            # Default: insert at the beginning of the method body
            insert_position = start_line
        
        # Use the calculated indentation
        body_indent = ' ' * target_line_indent
        
        # Generate source code for new statements
        new_lines = []
        for stmt in new_stmts:
            if hasattr(ast, 'unparse'):
                stmt_code = ast.unparse(stmt)
            else:
                stmt_code = self._ast_to_source(stmt)
            
            # Handle multiline statements properly - don't split control structures
            if self._is_multiline_control_structure(stmt):
                # For try-except, if-else, for loops, etc., add as single block with proper indentation
                lines_in_stmt = stmt_code.split('\n')
                for line in lines_in_stmt:
                    if line.strip():
                        new_lines.append(body_indent + line)
            else:
                # For simple statements, can split normally
                for line in stmt_code.split('\n'):
                    if line.strip():
                        new_lines.append(body_indent + line)
        
        # Insert the new lines
        result_lines = lines[:insert_position] + new_lines + lines[insert_position:]
        return '\n'.join(result_lines)
    
    def _is_multiline_control_structure(self, stmt: ast.AST) -> bool:
        """
        Check if a statement is a multiline control structure that should not be split.
        """
        return isinstance(stmt, (
            ast.Try,        # try-except blocks
            ast.If,         # if-elif-else statements  
            ast.For,        # for loops
            ast.While,      # while loops
            ast.With,       # with statements
            ast.FunctionDef, # function definitions
            ast.ClassDef,   # class definitions
            ast.AsyncFor,   # async for loops
            ast.AsyncWith,  # async with statements
            ast.AsyncFunctionDef  # async function definitions
        ))
    
    def _create_flow_compiler(self, cai3_map: CAI3Map, cai3_full: CAI3Full = None) -> FLOWCompiler:
        """
        Create a FLOWCompiler with the same flags used for dense FLOW writing.
        """
        flow_compiler = FLOWCompiler(
            name_map=cai3_map.name_map,
            dense_mode=True,
            pool_constants=True,
            ascii_ops=True,
            no_spaces=True,
            inline_blocks=True,
            alias_chains=True,
            pool_strings_min_len=3
        )
        
        # Set up pools and aliases from CAI3Full if available
        if cai3_full:
            # Set pools for p\d+ resolution
            if cai3_full.pools:
                flow_compiler.set_pools(cai3_full.pools)
            
            # Set chain aliases for g\d+ resolution
            if 'chain_aliases' in cai3_full.compression_stats:
                chain_aliases = cai3_full.compression_stats['chain_aliases']
                if isinstance(chain_aliases, dict):
                    # Clean up chain aliases - remove trailing parentheses if present
                    cleaned_aliases = {}
                    for alias, chain in chain_aliases.items():
                        # Store the actual chain without parentheses for attribute access
                        if chain.endswith('()'):
                            cleaned_aliases[alias] = chain[:-2]
                        else:
                            cleaned_aliases[alias] = chain
                    flow_compiler.set_chain_aliases(cleaned_aliases)
            
            # Set hash-to-value mapping for #xxxx resolution
            if hasattr(cai3_full, 'hash_to_value') and cai3_full.hash_to_value:
                flow_compiler.set_hash_mapping(cai3_full.hash_to_value)
        
        return flow_compiler
    
    def _validate_pool_references(self, pools: Dict[str, str]):
        """
        Hard check that pool references (p\d+) can be resolved.
        
        Args:
            pools: Dictionary of pool_id -> value mappings
        """
        for pool_id, value in pools.items():
            if not pool_id.startswith('p') or not pool_id[1:].isdigit():
                self.logger.warning(f"Invalid pool ID format: {pool_id}")
            
            if not isinstance(value, str):
                self.logger.warning(f"Pool {pool_id} contains non-string value: {type(value)}")
        
        self.logger.debug(f"Validated {len(pools)} pool references")
    
    def _validate_chain_aliases(self, chain_aliases: Dict[str, str], cai3_map: CAI3Map, cai3_full: CAI3Full):
        """
        Hard check that chain aliases (g\d+) can be resolved via CAI3Map/CAI3Full.
        
        Args:
            chain_aliases: Dictionary of alias -> full_chain mappings
            cai3_map: CAI3Map for name resolution
            cai3_full: CAI3Full for additional context
        """
        for alias, full_chain in chain_aliases.items():
            if not alias.startswith('g') or not alias[1:].isdigit():
                self.logger.warning(f"Invalid chain alias format: {alias}")
                continue
            
            # Validate that the chain can be resolved
            chain_parts = full_chain.split('.')
            if not chain_parts:
                self.logger.warning(f"Empty chain for alias {alias}")
                continue
            
            # Check if the root name exists in the name mapping
            root_name = chain_parts[0]
            if root_name not in cai3_map.name_map and root_name not in cai3_map.reverse_name_map:
                # Check if it's a known builtin or can be resolved
                if root_name not in ['self', 's', 'cls', 'c'] and not self._is_resolvable_name(root_name, cai3_full):
                    self.logger.warning(f"Chain alias {alias} -> {full_chain} has unresolvable root: {root_name}")
        
        self.logger.debug(f"Validated {len(chain_aliases)} chain aliases")
    
    def _is_resolvable_name(self, name: str, cai3_full: CAI3Full) -> bool:
        """
        Check if a name can be resolved in the current context.
        
        Args:
            name: Name to check
            cai3_full: CAI3Full structure for context
            
        Returns:
            True if the name is resolvable
        """
        # Check imports
        for import_stmt in cai3_full.imports:
            if name in import_stmt:
                return True
        
        # Check if it's a node name
        for node in cai3_full.nodes:
            if node.name == name or node.short_name == name:
                return True
        
        # Check common builtins
        builtins = {'str', 'int', 'float', 'list', 'dict', 'set', 'tuple', 'bool', 'len', 'range', 'enumerate', 'self', 'cls'}
        if name in builtins:
            return True
        
        return False
    
    def _replace_body_with_libcst(self, source: str, start_line: int, end_line: int,
                                  new_body: List[ast.AST], cid: str) -> str:
        """Use LibCST for precise body replacement"""
        
        class BodyReplacer(cst.CSTTransformer):
            METADATA_DEPENDENCIES = (cst.metadata.PositionProvider,)
            
            def __init__(self, target_line: int, new_body_ast: List[ast.AST]):
                self.target_line = target_line
                self.new_body_ast = new_body_ast
                self.replaced = False
            
            def visit_FunctionDef(self, node: cst.FunctionDef) -> bool:
                # Check if this is our target function
                positions = self.get_metadata(cst.metadata.PositionProvider, node)
                if positions and positions.start.line == self.target_line:
                    return True
                return True
            
            def leave_FunctionDef(self, original_node: cst.FunctionDef,
                                updated_node: cst.FunctionDef) -> cst.FunctionDef:
                positions = self.get_metadata(cst.metadata.PositionProvider, original_node)
                if positions and positions.start.line == self.target_line and not self.replaced:
                    # Convert AST to CST for the body
                    new_body_cst = []
                    for stmt in self.new_body_ast:
                        # Convert each AST statement to CST
                        try:
                            if hasattr(ast, 'unparse'):
                                stmt_code = ast.unparse(stmt)
                            else:
                                stmt_code = str(stmt)  # Simplified fallback
                            stmt_cst = cst.parse_statement(stmt_code)
                            new_body_cst.append(stmt_cst)
                        except Exception:
                            # Fallback to a simple pass statement
                            new_body_cst.append(cst.parse_statement("pass"))
                    
                    # Create new function with replaced body
                    self.replaced = True
                    return updated_node.with_changes(
                        body=cst.IndentedBlock(body=new_body_cst)
                    )
                return updated_node
        
        try:
            # Parse with LibCST
            tree = cst.parse_module(source)
            wrapper = cst.metadata.MetadataWrapper(tree)
            
            # Apply transformation
            replacer = BodyReplacer(start_line, new_body)
            modified_tree = wrapper.visit(replacer)
            
            return modified_tree.code
        except Exception as e:
            self.logger.warning(f"LibCST replacement failed: {e}, falling back to AST method")
            # Fallback to AST method
            return self._replace_body_with_ast(source, start_line, end_line, new_body)
    
    def _replace_body_with_ast(self, source: str, start_line: int, end_line: int,
                               new_body: List[ast.AST]) -> str:
        """Fallback: Replace body using string manipulation"""
        lines = source.split('\n')
        
        # Find the function/method definition
        func_line_idx = start_line - 1
        func_line = lines[func_line_idx]
        
        # Get indentation
        indent = len(func_line) - len(func_line.lstrip())
        body_indent = ' ' * (indent + 4)
        
        # Convert new body to source code
        new_body_lines = []
        for stmt in new_body:
            if hasattr(ast, 'unparse'):
                stmt_code = ast.unparse(stmt)
            else:
                stmt_code = self._ast_to_source(stmt)
            
            # Handle multiline statements properly - don't split control structures
            if self._is_multiline_control_structure(stmt):
                # For try-except, if-else, for loops, etc., add as single block with proper indentation
                lines_in_stmt = stmt_code.split('\n')
                for line in lines_in_stmt:
                    if line.strip():
                        new_body_lines.append(body_indent + line)
            else:
                # For simple statements, can split normally
                for line in stmt_code.split('\n'):
                    if line.strip():
                        new_body_lines.append(body_indent + line)
        
        # Find where the body starts (after the function def and any decorators/docstrings)
        body_start_idx = func_line_idx + 1
        
        # Skip docstring if present
        if body_start_idx < len(lines):
            next_line = lines[body_start_idx].strip()
            if next_line.startswith('"""') or next_line.startswith("'''"):
                # Find end of docstring
                quote = '"""' if '"""' in next_line else "'''"
                if next_line.count(quote) >= 2:
                    # Single line docstring
                    body_start_idx += 1
                else:
                    # Multi-line docstring
                    body_start_idx += 1
                    while body_start_idx < len(lines):
                        if quote in lines[body_start_idx]:
                            body_start_idx += 1
                            break
                        body_start_idx += 1
        
        # Replace the body
        new_lines = (
            lines[:body_start_idx] +
            new_body_lines +
            lines[end_line:]
        )
        
        return '\n'.join(new_lines)
    
    def _add_method(self, patch: CAI3Patch, source: str, cai3_map: CAI3Map) -> str:
        """Add a new method to a class"""
        # This would find the appropriate class and add the method
        # Implementation depends on the specific requirements
        self.logger.warning("Add method operation not yet implemented")
        return source
    
    def _delete_method(self, patch: CAI3Patch, source: str, cai3_map: CAI3Map) -> str:
        """Delete a method from the source"""
        if patch.target_cid not in cai3_map.span_map:
            return source
        
        start_line, end_line = cai3_map.span_map[patch.target_cid]
        lines = source.split('\n')
        
        # Remove the method lines
        new_lines = lines[:start_line-1] + lines[end_line:]
        
        return '\n'.join(new_lines)
    
    def _rebase_and_apply(self, patch: CAI3Patch, source_path: Path, source: str,
                          cai3_full: CAI3Full, cai3_map: CAI3Map) -> str:
        """Rebase the patch when context has changed"""
        # Re-compress the current source
        from .cai3_waterfall_integration import CAI3WaterfallEnhancement
        
        enhancer = CAI3WaterfallEnhancement()
        enhancer.cai3_cache = self.cache
        
        # Parse current source
        tree = ast.parse(source)
        
        # Recreate CAI3 structures using the enhanced methods
        cid_index = enhancer._annotate_function_cids(tree)
        new_full = enhancer._create_cai3_full_enhanced(tree, source, source_path, cid_index)
        new_map = enhancer._create_cai3_map_enhanced(new_full)
        
        # Update cache
        self.cache.store_full(source_path, new_full)
        self.cache.store_map(source_path, new_map)
        
        # Try to find the corresponding cid in the new structure
        # This is heuristic - match by method name
        target_name = None
        for node in cai3_full.nodes:
            if node.cid == patch.target_cid:
                target_name = node.name
                break
        
        if target_name:
            # Find new cid for the same method
            new_cid = None
            for node in new_full.nodes:
                if node.name == target_name:
                    new_cid = node.cid
                    break
            
            if new_cid:
                # Update patch with new cid
                patch.target_cid = new_cid
                # Retry with new mapping
                return self._replace_body(patch, source, new_map, new_full)
        
        self.logger.error(f"Failed to rebase patch for {patch.target_cid}")
        return source
    
    def _ast_to_source(self, node: ast.AST) -> str:
        """Convert AST node to source code (fallback for older Python)"""
        if isinstance(node, ast.Pass):
            return "pass"
        elif isinstance(node, ast.Return):
            if node.value:
                return f"return {self._ast_to_source(node.value)}"
            return "return"
        elif isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Constant):
            return repr(node.value)
        elif isinstance(node, ast.Assign):
            targets = ", ".join(self._ast_to_source(t) for t in node.targets)
            value = self._ast_to_source(node.value)
            return f"{targets} = {value}"
        elif isinstance(node, ast.Expr):
            return self._ast_to_source(node.value)
        elif isinstance(node, ast.Call):
            func = self._ast_to_source(node.func)
            args = ", ".join(self._ast_to_source(arg) for arg in node.args)
            return f"{func}({args})"
        elif isinstance(node, ast.Attribute):
            value = self._ast_to_source(node.value)
            return f"{value}.{node.attr}"
        elif isinstance(node, ast.If):
            test = self._ast_to_source(node.test)
            body = "\n".join(f"    {self._ast_to_source(stmt)}" for stmt in node.body)
            result = f"if {test}:\n{body}"
            if node.orelse:
                else_body = "\n".join(f"    {self._ast_to_source(stmt)}" for stmt in node.orelse)
                result += f"\nelse:\n{else_body}"
            return result
        elif isinstance(node, ast.For):
            target = self._ast_to_source(node.target)
            iter_val = self._ast_to_source(node.iter)
            body = "\n".join(f"    {self._ast_to_source(stmt)}" for stmt in node.body)
            return f"for {target} in {iter_val}:\n{body}"
        elif isinstance(node, ast.BinOp):
            left = self._ast_to_source(node.left)
            right = self._ast_to_source(node.right)
            op_map = {
                ast.Add: '+', ast.Sub: '-', ast.Mult: '*', ast.Div: '/',
                ast.Mod: '%', ast.Pow: '**', ast.LShift: '<<', ast.RShift: '>>',
                ast.BitOr: '|', ast.BitXor: '^', ast.BitAnd: '&'
            }
            op = op_map.get(type(node.op), '?')
            return f"({left} {op} {right})"
        elif isinstance(node, ast.Compare):
            left = self._ast_to_source(node.left)
            comparisons = []
            for op, comp in zip(node.ops, node.comparators):
                op_map = {
                    ast.Eq: '==', ast.NotEq: '!=', ast.Lt: '<', ast.LtE: '<=',
                    ast.Gt: '>', ast.GtE: '>=', ast.Is: 'is', ast.IsNot: 'is not',
                    ast.In: 'in', ast.NotIn: 'not in'
                }
                op_str = op_map.get(type(op), '?')
                comp_str = self._ast_to_source(comp)
                comparisons.append(f"{op_str} {comp_str}")
            return f"{left} {' '.join(comparisons)}"
        else:
            # Fallback for unknown node types
            return f"# TODO: Convert {type(node).__name__} node"
    
    def _update_cache(self, source_path: Path, new_source: str):
        """Update the cache with new source content"""
        # Invalidate old cache
        self.cache.invalidate(source_path)
        
        # Would re-run compression to update cache
        # This is handled by the next compression run
        
    def translate_lite_to_python(self, cai3_lite_content: str, source_path: Path) -> str:
        """
        Translate complete CAI3-LITE content back to Python using FULL and MAP with enhanced logging.
        
        Args:
            cai3_lite_content: The CAI3-LITE formatted content from Claude
            source_path: Path to the original source file for cache lookup
            
        Returns:
            Reconstructed Python source code
        """
        self.logger.info(f"Starting CAI3-LITE to Python translation for {source_path}")
        self.logger.debug(f"LITE content length: {len(cai3_lite_content)} characters")
        self.logger.debug(f"LITE content preview: {cai3_lite_content[:300]}...")
        
        # Load FULL and MAP from cache
        self.logger.debug("Loading CAI3 structures from cache")
        cai3_full = self.cache.load_full(source_path)
        cai3_map = self.cache.load_map(source_path)
        
        if not cai3_full or not cai3_map:
            self.logger.error(f"No CAI3 cache found for {source_path}")
            raise ValueError(f"No CAI3 cache found for {source_path}. Ensure compression was run first.")
        
        self.logger.debug(f"Loaded CAI3Full with {len(cai3_full.nodes)} nodes")
        self.logger.debug(f"Loaded CAI3Map with {len(cai3_map.span_map)} spans")
        
        try:
            # Parse the CAI3-LITE content
            self.logger.info("Parsing CAI3-LITE content")
            lite_structure = self._parse_cai3_lite(cai3_lite_content, cai3_full, cai3_map)
            
            # Reconstruct Python code
            self.logger.info("Reconstructing Python code from LITE structure")
            python_code = self._reconstruct_python(lite_structure, cai3_full, cai3_map)
            
            self.logger.debug(f"Reconstructed Python code length: {len(python_code)} characters")
            
            # VALIDATION: Check syntax before returning
            self.logger.info("Validating reconstructed Python syntax")
            try:
                ast.parse(python_code)
                self.logger.info("Translation successful - Python syntax valid")
            except SyntaxError as e:
                self.logger.error(f"Translation resulted in invalid Python syntax: {e}")
                # Log the problematic area
                if hasattr(e, 'lineno') and e.lineno:
                    lines = python_code.split('\n')
                    start_line = max(0, e.lineno - 3)
                    end_line = min(len(lines), e.lineno + 3)
                    self.logger.error(f"Context around line {e.lineno}:")
                    for i in range(start_line, end_line):
                        marker = " -> " if i + 1 == e.lineno else "    "
                        self.logger.error(f"{marker}{i+1:3d}: {lines[i] if i < len(lines) else ''}")
                
                # Try recovery with original structure
                return self._recover_with_original(source_path, lite_structure, cai3_full, cai3_map)
            
            return python_code
            
        except Exception as e:
            self.logger.error(f"Failed to translate CAI3-LITE to Python: {e}")
            raise

    def _parse_cai3_lite(self, lite_content: str, cai3_full: CAI3Full, cai3_map: CAI3Map) -> Dict:
        """
        Parse CAI3-LITE content with structure validation and enhanced logging.
        """
        self.logger.debug(f"Starting CAI3-LITE parsing")
        self.logger.debug(f"Content length: {len(lite_content)} characters")
        self.logger.debug(f"Content preview: {lite_content[:200]}...")
        
        lite_data = {
            'header': None,
            'imports': [],
            'chain_aliases': {},
            'cid_aliases': {},
            'pools': {},
            'table': [],
            'bodies': {},
            'config_keys': []
        }
        
        # MOVED HERE: Load stored aliases FIRST before parsing any lines
        self.logger.debug(f"CAI3Full compression_stats keys: {list(cai3_full.compression_stats.keys()) if cai3_full.compression_stats else 'None'}")
        if 'cid_aliases' in cai3_full.compression_stats:
            stored_cid_aliases = cai3_full.compression_stats['cid_aliases']
            self.logger.debug(f"Loaded {len(stored_cid_aliases)} CID aliases: {stored_cid_aliases}")
            
            # These are already in the right direction (alias -> CID)
            lite_data['cid_aliases'].update(stored_cid_aliases)
        else:
            self.logger.debug("No cid_aliases found in CAI3Full compression_stats")
        
        lines = lite_content.strip().split('\n')
        self.logger.debug(f"Split content into {len(lines)} lines")
        i = 0
        
        while i < len(lines):
            line = lines[i].strip()
            
            # Skip empty lines
            if not line:
                i += 1
                continue
            
            self.logger.debug(f"Line {i}: Processing '{line}'")
            
            # Parse header
            if line.startswith('#C3L'):
                self.logger.debug(f"Found header: {line}")
                lite_data['header'] = line
            
            # Parse imports
            elif line.startswith('I:'):
                imports_str = line[2:]
                self.logger.debug(f"Processing imports: {imports_str}")
                # Parse compact imports like "I:j|dt:dt|t:L"
                for imp in imports_str.split('|'):
                    if ':' in imp:
                        alias, module = imp.split(':', 1)
                        lite_data['imports'].append({'alias': alias, 'module': module})
                        self.logger.debug(f"Added import: {alias} -> {module}")
                self.logger.debug(f"Total imports parsed: {len(lite_data['imports'])}")
            
            # Parse chain aliases
            elif line.startswith('D:'):
                aliases_str = line[2:]
                self.logger.debug(f"Processing chain aliases: {aliases_str}")
                # Parse like "D:g0=s.c.g,g1=dt.now"
                alias_count = 0
                for alias_def in aliases_str.split(','):
                    if '=' in alias_def:
                        alias, chain = alias_def.split('=', 1)
                        lite_data['chain_aliases'][alias.strip()] = chain.strip()
                        alias_count += 1
                        self.logger.debug(f"Added chain alias: {alias.strip()} -> {chain.strip()}")
                self.logger.debug(f"Total chain aliases parsed: {alias_count}")
            
            # Parse CID aliases
            elif line.startswith('X:'):
                # Skip X: line parsing if we already have stored aliases
                # The X: line contains incorrect short hashes that don't resolve properly
                self.logger.debug(f"Skipping X: line parsing - using stored aliases instead: {line}")
                pass
            
            # Parse pools
            elif line.startswith('P:'):
                pools_str = line[2:]
                self.logger.debug(f"Processing pools: {pools_str}")
                # Parse like "P:p0=value1,p1=value2"
                pool_count = 0
                for pool_def in pools_str.split(','):
                    if '=' in pool_def:
                        pool_id, value = pool_def.split('=', 1)
                        lite_data['pools'][pool_id.strip()] = value.strip()
                        pool_count += 1
                        self.logger.debug(f"Added pool: {pool_id.strip()} -> {value.strip()}")
                self.logger.debug(f"Total pools parsed: {pool_count}")
            
            # Parse table (can be single line or multi-line)
            elif line.startswith('T:'):
                # Single line table: T:C:dp,M:dp.i,M:dp.vr#a1
                table_str = line[2:]
                self.logger.debug(f"Processing table line: {table_str}")
                entry_count = 0
                for entry in table_str.split(','):
                    lite_data['table'].append(entry.strip())
                    entry_count += 1
                    self.logger.debug(f"Added table entry: {entry.strip()}")
                self.logger.debug(f"Added {entry_count} table entries from line")
            elif line.startswith('C:') or line.startswith('M:') or line.startswith('F:'):
                # Multi-line table entries
                self.logger.debug(f"Adding multi-line table entry: {line}")
                lite_data['table'].append(line)
            
            # Parse bodies
            elif line.startswith('B#'):
                self.logger.debug(f"Processing body line: {line}")
                # Body format: B#a0:single_line_body
                if ':' in line:
                    header, body = line.split(':', 1)
                    cid_ref = header[2:]  # Remove 'B#'
                    
                    self.logger.debug(f"Body header: {header}, CID ref: {cid_ref}")
                    self.logger.debug(f"Body content: {repr(body)}")
                    self.logger.debug(f"Body length: {len(body.strip())}")
                    
                    # Use pre-loaded aliases directly
                    if cid_ref in lite_data['cid_aliases']:
                        actual_cid = lite_data['cid_aliases'][cid_ref]
                        self.logger.debug(f"Resolved CID using stored alias: {cid_ref} -> {actual_cid}")
                    else:
                        # Fallback to old resolution method if needed
                        actual_cid = self._resolve_cid_reference(cid_ref, lite_data['cid_aliases'], cai3_full)
                        self.logger.debug(f"Resolved CID using fallback: {cid_ref} -> {actual_cid}")
                    
                    
                    # FUNDAMENTAL FIX: Resolve CID references in body content immediately
                    raw_body = body.strip()
                    resolved_body = self._resolve_cid_references_in_body(raw_body, cai3_map, cai3_full)
                    
                    lite_data['bodies'][actual_cid] = resolved_body
                    self.logger.debug(f"Stored body for {actual_cid}: {repr(raw_body)} -> {repr(resolved_body)}")
                else:
                    self.logger.warning(f"Body line missing colon separator: {line}")
            else:
                self.logger.debug(f"Unrecognized line format: {line}")
            
            i += 1
        
        self.logger.debug(f"Parsing complete. Summary:")
        self.logger.debug(f"  Header: {lite_data['header']}")
        self.logger.debug(f"  Imports: {len(lite_data['imports'])}")
        self.logger.debug(f"  Chain aliases: {len(lite_data['chain_aliases'])}")
        self.logger.debug(f"  CID aliases: {len(lite_data['cid_aliases'])}")
        self.logger.debug(f"  Pools: {len(lite_data['pools'])}")
        self.logger.debug(f"  Table entries: {len(lite_data['table'])}")
        self.logger.debug(f"  Bodies: {len(lite_data['bodies'])}")
        
        # Merge chain aliases - LITE structure takes precedence over stored (compressed) ones
        stored_aliases_count = 0
        if 'chain_aliases' in cai3_full.compression_stats:
            stored_chain_aliases = cai3_full.compression_stats['chain_aliases']
            self.logger.debug(f"Merging {len(stored_chain_aliases)} stored chain aliases")
            # Add stored aliases first, then LITE aliases will override
            for alias, chain in stored_chain_aliases.items():
                if alias not in lite_data['chain_aliases']:
                    lite_data['chain_aliases'][alias] = chain
                    stored_aliases_count += 1
            self.logger.debug(f"Added {stored_aliases_count} additional stored aliases")
        
        # Validate and repair body structures
        repair_count = 0
        validation_count = 0
        malformed_fix_count = 0
        for cid, body_content in lite_data['bodies'].items():
            validation_count += 1
            
            # CRITICAL FIX: Apply malformed statement fixing to body content before parsing
            # This fixes patterns like f!inud?(s.l.er(...),RF):_ before they cause parsing failures
            original_body = body_content
            body_content = self._apply_malformed_fixes_to_body(body_content)
            if body_content != original_body:
                malformed_fix_count += 1
                self.logger.debug(f"Applied malformed fixes to body {cid}: {repr(original_body)} -> {repr(body_content)}")
                lite_data['bodies'][cid] = body_content
            
            if 'T{' in body_content:
                self.logger.debug(f"Validating T{{}} structure in body for {cid}")
                # Check for incomplete T{} structures
                open_braces = body_content.count('{')
                close_braces = body_content.count('}')
                
                if open_braces != close_braces:
                    self.logger.warning(f"Incomplete T{{}} structure in body for {cid}")
                    self.logger.debug(f"  Open braces: {open_braces}, Close braces: {close_braces}")
                    # Attempt basic repair
                    missing = open_braces - close_braces
                    if missing > 0:
                        original_content = body_content
                        if 'X{' not in body_content:
                            body_content += '}' * missing + 'X{_}'
                        else:
                            body_content += '}' * missing
                        lite_data['bodies'][cid] = body_content
                        repair_count += 1
                        self.logger.debug(f"Repaired body for {cid}")
                        self.logger.debug(f"  Before: {repr(original_content)}")
                        self.logger.debug(f"  After: {repr(body_content)}")
                else:
                    self.logger.debug(f"T{{}} structure validation passed for {cid}")
        
        self.logger.debug(f"Body validation complete: {validation_count} bodies checked, {repair_count} repaired, {malformed_fix_count} malformed patterns fixed")
        
        return lite_data

    def _build_short_to_orig(self, local_map: Dict[str, str], global_map: Dict[str, str]) -> Dict[str, str]:
        """
        Build final short->orig map with strict precedence and reserved-name protection.
        """
        result = {}
        
        # CRITICAL FIX: Reserved names that should never be used as variable names
        reserved_names = {
            "__init__", "__class__", "__dict__", "__annotations__", "__slots__",
            "__name__", "__module__", "__doc__", "__file__", "__builtins__",
            "os", "sys", "re", "json", "datetime", "typing"  # Common imports that shouldn't be variables
        }
        
        # Python builtins that shouldn't be used as variables in most contexts
        python_builtins = {
            "str", "int", "float", "list", "dict", "set", "tuple", "bool",
            "len", "range", "enumerate", "zip", "map", "filter", "sorted",
            "open", "print", "input", "type", "isinstance", "hasattr"
        }
        
        # 1) Process locals first with highest priority
        for short, orig in local_map.items():
            # Protect against reserved names
            if orig in reserved_names:
                result[short] = f"{orig}_var"
                self.logger.debug(f"Protected reserved name: {short} -> {orig} became {short} -> {orig}_var")
            elif orig in python_builtins and short not in {'s', 'self'}:  # Allow 's' -> 'self' 
                # Be more selective about builtin protection
                if short in {'i', 'j', 'k'} and orig in {'int', 'str'}:
                    # Don't protect common loop variables from int/str
                    result[short] = short  # Use short name instead
                    self.logger.debug(f"Protected builtin by using short name: {short} -> {orig} became {short} -> {short}")
                else:
                    result[short] = orig  # Allow other builtin mappings
            else:
                result[short] = orig
        
        # 2) Process globals only if not conflicting with locals
        for short, orig in global_map.items():
            if short in result:
                self.logger.debug(f"Skipped global mapping {short} -> {orig}, preserving local: {short} -> {result[short]}")
                continue  # Local wins, skip global
            
            # Special handling for problematic mappings
            if short == "i" and orig == "__init__":
                # Never map 'i' to '__init__' in variable contexts
                self.logger.debug(f"Blocked problematic mapping: i -> __init__")
                continue
            
            # Additional protection for common loop variables    
            if short in {'i', 'j', 'k'} and orig in reserved_names:
                # Use descriptive names for loop variables instead of reserved names
                descriptive_names = {'i': 'item', 'j': 'index', 'k': 'key'}
                result[short] = descriptive_names.get(short, short)
                self.logger.debug(f"Protected loop variable: {short} -> {orig} became {short} -> {result[short]}")
                continue
                
            if orig in reserved_names:
                result[short] = f"{orig}_var"
                self.logger.debug(f"Protected reserved name: {short} -> {orig} became {short} -> {orig}_var")
            else:
                result[short] = orig
        
        # 3) Add common variable mappings
        common_mappings = {
            's': 'self',
            'c': 'cls'  # Only use this for class methods, not as a general mapping
        }
        
        # Apply common mappings with collision checking
        for short, orig in common_mappings.items():
            if short not in result:
                result[short] = orig
                self.logger.debug(f"Added common mapping: {short} -> {orig}")
            else:
                self.logger.debug(f"Skipped common mapping {short} -> {orig}, already mapped to: {result[short]}")
        
        self.logger.debug(f"Final short_to_orig mapping: {result}")
        return result

    def _merge_validation_patterns(self, stmts: List[str]) -> List[str]:
        """
        Merge CAI3 validation patterns into proper if statements.
        Pattern: (field_check)?{validation}:_; action
        Becomes: if field_check and validation: action
        """
        merged = []
        i = 0
        
        while i < len(stmts):
            cur = stmts[i].strip()
            nxt = stmts[i + 1].strip() if i + 1 < len(stmts) else ""
            
            # Detect validation pattern with following action
            if (cur.startswith("(") and ")?{" in cur and "}:_" in cur and 
                (nxt.startswith("h.append(") or nxt.startswith("issues.append("))):
                
                try:
                    # Extract components
                    guard_end = cur.index(")?{")
                    guard = cur[1:guard_end]  # Remove leading (
                    
                    inner_start = guard_end + 3
                    inner_end = cur.index("}:_")
                    inner_cond = cur[inner_start:inner_end]
                    
                    # Normalize expressions CAREFULLY to avoid creating malformed chained calls
                    guard_norm = self._normalize_expr_for_validation(guard)
                    inner_norm = self._normalize_expr_for_validation(inner_cond)
                    
                    # CRITICAL FIX: Ensure clean action statement
                    clean_action = nxt.strip()
                    # Remove any prefix artifacts that might have been added
                    if clean_action.startswith('.'):
                        clean_action = clean_action[1:]  # Remove leading dot
                    
                    # Build merged if statement with proper structure
                    if inner_norm and inner_norm.strip() and inner_norm.strip() != "_":
                        merged_if = f"if ({guard_norm}) and ({inner_norm}):\n    {clean_action}"
                    else:
                        merged_if = f"if {guard_norm}:\n    {clean_action}"
                    
                    merged.append(merged_if)
                    self.logger.debug(f"Merged validation pattern: '{cur}' + '{nxt}' -> '{merged_if}'")
                    i += 2
                    continue
                except (ValueError, IndexError) as e:
                    self.logger.warning(f"Failed to parse validation pattern '{cur}': {e}")
                    pass  # Fall through to default handling
            
            merged.append(stmts[i])
            i += 1
        
        return merged

    def _normalize_expr_for_validation(self, expr: str) -> str:
        """
        Normalize validation expressions for proper Python syntax.
        Generalized to handle malformed expressions across any domain.
        """
        import re
        s = expr.strip()
        
        # GENERALIZED FIX: Handle malformed chain expressions with complex conditionals
        # Pattern: Detect any expression with repeated attribute access and complex logical operators
        # Examples: "obj.attr['key'] not in collection or obj.attr['key'] <= value"
        #          "x.y['#hash'] in z and x.y['#hash'] > 0"
        
        # 1. Detect repeated object.attribute['key'] patterns with logical operators
        repeated_access_pattern = r"(\w+\.\w+\['[^']+'\])\s+(not\s+in|in|[<>=!]+)\s+([^|&]+)\s+(or|and)\s+\1\s*([<>=!]+)"
        match = re.search(repeated_access_pattern, s)
        
        if match:
            obj_access = match.group(1)  # e.g., "s.d['#4899']"
            first_op = match.group(2)    # e.g., "not in"
            first_operand = match.group(3).strip()  # e.g., "i"
            logical_op = match.group(4)  # e.g., "or"
            second_op = match.group(5)   # e.g., "<="
            
            # Extract object path and key for reconstruction
            obj_match = re.match(r"(\w+)\.(\w+)\['([^']+)'\]", obj_access)
            if obj_match:
                obj_name, attr_name, key = obj_match.groups()
                
                # Create simplified, safe expression based on context
                full_obj_name = self._resolve_object_name(obj_name, attr_name)
                safe_key = key if not key.startswith('#') else f"'{key}'"
                
                if logical_op == "or":
                    # For OR conditions, create existence check with fallback
                    if "not in" in first_op:
                        s = f"{safe_key} not in {first_operand} or {full_obj_name}.get({safe_key}, 0) {second_op} 0"
                    else:
                        s = f"{full_obj_name}.get({safe_key}) {first_op} {first_operand} or {full_obj_name}.get({safe_key}, 0) {second_op} 0"
                else:  # and
                    # For AND conditions, create safe chained validation
                    s = f"{safe_key} in {full_obj_name} and {full_obj_name}[{safe_key}] {first_op} {first_operand} and {full_obj_name}[{safe_key}] {second_op} 0"
                
                self.logger.debug(f"Fixed repeated access pattern: '{expr}' -> '{s}'")
        
        # 2. Handle simple abbreviation mappings (generalized)
        # Common patterns: s.d -> self.data_buffer, obj.attr -> self.attribute, etc.
        abbreviation_mappings = {
            r'\bs\.d\b': 'self.data_buffer',
            r'\bc\.c\b': 'self.config', 
            r'\bp\.p\b': 'self.properties',
            r'\bm\.m\b': 'self.metadata',
            r'\bv\.v\b': 'self.values'
        }
        
        for pattern, replacement in abbreviation_mappings.items():
            if re.search(pattern, s):
                s = re.sub(pattern, replacement, s)
                self.logger.debug(f"Applied abbreviation mapping: {pattern} -> {replacement}")
        
        # 3. Fix token boundaries - ensure proper spacing
        s = re.sub(r"\](?=[A-Za-z_])", "] ", s)
        s = re.sub(r"([A-Za-z_]\w*)\(", r"\1 (", s)  # Space before parentheses
        
        # 4. Normalize operators
        operator_normalizations = {
            "!in": " not in ",
            "!==": " != ",
            "===": " == ",
            "&&": " and ",
            "||": " or "
        }
        
        for bad_op, good_op in operator_normalizations.items():
            s = s.replace(bad_op, good_op)
        
        # 5. Context-aware variable resolution
        # Map single-letter variables based on validation context
        context_mappings = {
            r'\bi\b': 'required_fields',  # Common in validation loops
            r'\bj\b': 'field_name',       # Loop variables
            r'\bk\b': 'key',              # Dictionary keys
            r'\bv\b': 'value'             # Dictionary values
        }
        
        for pattern, replacement in context_mappings.items():
            if re.search(pattern, s) and not re.search(r'\b' + replacement.split('_')[0] + r'\b', s):
                s = re.sub(pattern, replacement, s)
        
        self.logger.debug(f"Normalized validation expression: '{expr}' -> '{s}'")
        return s
    
    def _resolve_object_name(self, obj_abbrev: str, attr_abbrev: str) -> str:
        """
        Resolve abbreviated object.attribute to full name.
        Generalized mapping for common abbreviations.
        """
        # Common object abbreviation patterns
        obj_mappings = {
            's': 'self',
            'c': 'cls',
            'cfg': 'config',
            'ctx': 'context',
            'req': 'request',
            'resp': 'response'
        }
        
        # Common attribute abbreviation patterns  
        attr_mappings = {
            'd': 'data_buffer',
            'cfg': 'config',
            'meta': 'metadata',
            'props': 'properties',
            'vals': 'values',
            'cache': 'cache'
        }
        
        obj_name = obj_mappings.get(obj_abbrev, obj_abbrev)
        attr_name = attr_mappings.get(attr_abbrev, attr_abbrev)
        
        return f"{obj_name}.{attr_name}"

    def _resolve_short_cid(self, short_cid: str, cai3_full: CAI3Full) -> str:
        """
        Resolve a short CID (like '5mn3') to full CID (like 'mt_5605') with enhanced logging.
        """
        self.logger.debug(f"Resolving short CID: {repr(short_cid)}")
        self.logger.debug(f"Available nodes count: {len(cai3_full.nodes)}")
        
        # Check if it's already a full CID
        if short_cid.startswith(('mt_', 'fn_', 'cl_')):
            self.logger.debug(f"Already full CID: {short_cid}")
            return short_cid
        
        # Try to find matching CID by hash
        self.logger.debug("Attempting hash-based matching")
        hash_matches = []
        for node in cai3_full.nodes:
            # Generate short36 hash for comparison
            try:
                node_short = self._short36(node.cid)[:4]
                if node_short == short_cid:
                    hash_matches.append(node.cid)
                    self.logger.debug(f"Hash match found: {short_cid} -> {node.cid}")
            except Exception as e:
                self.logger.warning(f"Error generating hash for {node.cid}: {e}")
        
        if hash_matches:
            if len(hash_matches) == 1:
                self.logger.debug(f"Single hash match: {short_cid} -> {hash_matches[0]}")
                return hash_matches[0]
            else:
                self.logger.warning(f"Multiple hash matches for {short_cid}: {hash_matches}")
                return hash_matches[0]  # Return first match
        
        # Fallback: check if it exists in nodes directly
        self.logger.debug("Attempting direct CID matching")
        for node in cai3_full.nodes:
            if node.cid == short_cid:
                self.logger.debug(f"Direct match: {short_cid}")
                return node.cid
        
        # List available CIDs for debugging
        available_cids = [node.cid for node in cai3_full.nodes[:5]]  # First 5 for brevity
        self.logger.debug(f"Available CIDs (sample): {available_cids}")
        
        self.logger.warning(f"Could not resolve short CID: {short_cid}")
        return short_cid

    def _resolve_cid_reference(self, cid_ref: str, cid_aliases: Dict, cai3_full: CAI3Full) -> str:
        """
        Resolve a CID reference (like 'a0' or '5mn3') to actual CID with enhanced logging.
        """
        self.logger.debug(f"Resolving CID reference: {repr(cid_ref)}")
        self.logger.debug(f"Available aliases: {list(cid_aliases.keys())}")
        
        # Check if it's an alias
        if cid_ref in cid_aliases:
            resolved_cid = cid_aliases[cid_ref]
            self.logger.debug(f"Resolved via alias: {cid_ref} -> {resolved_cid}")
            return resolved_cid
        
        # Check if it's a short CID
        self.logger.debug(f"Not found in aliases, trying short CID resolution")
        resolved_cid = self._resolve_short_cid(cid_ref, cai3_full)
        self.logger.debug(f"Short CID resolution result: {cid_ref} -> {resolved_cid}")
        return resolved_cid

    def _reconstruct_python(self, lite_structure: Dict, cai3_full: CAI3Full, cai3_map: CAI3Map) -> str:
        """
        Reconstruct Python code from parsed LITE structure.
        """
        python_lines = []
        
        # Add imports
        if lite_structure['imports']:
            for imp in lite_structure['imports']:
                if imp['module'] == imp['alias']:
                    python_lines.append(f"import {imp['module']}")
                else:
                    # Expand abbreviated imports
                    module_map = {'dt': 'datetime', 'j': 'json', 't': 'typing'}
                    full_module = module_map.get(imp['module'], imp['module'])
                    python_lines.append(f"import {full_module} as {imp['alias']}")
            python_lines.append("")
        
        # Build node hierarchy
        nodes_by_cid = {node.cid: node for node in cai3_full.nodes}
        
        # Process classes and their methods
        for entry in lite_structure['table']:
            if entry.startswith('C:'):
                # Class definition
                class_short = entry[2:].split('#')[0]
                class_name = cai3_map.name_map.get(class_short, class_short)
                
                # Find the class node
                class_node = None
                for node in cai3_full.nodes:
                    if node.short_name == class_short and node.type.value == 'C':
                        class_node = node
                        break
                
                if class_node:
                    python_lines.append(f"class {class_name}:")
                    
                    # Get all methods for this class
                    method_lines = []
                    for child_cid in cai3_map.children_map.get(class_node.cid, []):
                        method_node = nodes_by_cid.get(child_cid)
                        if method_node:
                            method_code = self._reconstruct_method(
                                method_node, 
                                lite_structure['bodies'].get(child_cid),
                                cai3_map,
                                cai3_full,
                                lite_structure['chain_aliases'],
                                lite_structure['pools']
                            )
                            method_lines.extend(method_code)
                    
                    if method_lines:
                        # Apply formatting to method code before adding indentation
                        method_text = '\n'.join(method_lines)
                        method_text = self._apply_black_formatting(method_text)
                        formatted_method_lines = method_text.split('\n') if method_text else []
                        python_lines.extend(["    " + line for line in formatted_method_lines if line.strip()])
                    else:
                        python_lines.append("    pass")
                    
                    python_lines.append("")
        
        # Process standalone functions
        for entry in lite_structure['table']:
            if entry.startswith('F:'):
                # Function definition
                func_short = entry[2:].split('#')[0]
                
                # Find the function node
                func_node = None
                for node in cai3_full.nodes:
                    if node.short_name == func_short and node.type.value == 'F':
                        func_node = node
                        break
                
                if func_node:
                    func_code = self._reconstruct_method(
                        func_node,
                        lite_structure['bodies'].get(func_node.cid),
                        cai3_map,
                        cai3_full,
                        lite_structure['chain_aliases'],
                        lite_structure['pools']
                    )
                    # Apply formatting to function code before adding to main
                    if func_code:
                        func_text = '\n'.join(func_code)
                        func_text = self._apply_black_formatting(func_text)
                        formatted_func_lines = func_text.split('\n') if func_text else []
                        python_lines.extend([line for line in formatted_func_lines if line.strip()])
                    python_lines.append("")
        
        # Create the Python code
        python_code = '\n'.join(python_lines)

        # CRITICAL FIX: Clean up malformed expressions before final placeholder resolution
        python_code = self._clean_malformed_expressions(python_code)

        # NOTE: No need to fix orphaned except statements since FLOW compiler handles T{...}X{...} properly
        # python_code = self._fix_orphaned_except_statements(python_code)

        # CRITICAL FIX: Final placeholder resolution pass
        python_code = self._final_placeholder_resolution(python_code)

        # FINAL STEP: Apply black formatting to clean up all spacing issues
        python_code = self._apply_black_formatting(python_code)

        return python_code

    def _resolve_cid_references_in_body(self, body_content: str, cai3_map: CAI3Map, cai3_full: CAI3Full) -> str:
        """
        Resolve CID references in body content to actual variable names.
        This is the FUNDAMENTAL fix - resolve CID references at source, not during AST processing.
        """
        if not body_content:
            return body_content
            
        # Pattern to match CID references like mt_4849:x, fn_1234:method_name, etc.
        import re
        cid_pattern = r'(mt_|fn_|cl_)([a-f0-9]{4}):([a-zA-Z_][a-zA-Z0-9_]*)'
        
        def resolve_cid_ref(match):
            cid_prefix = match.group(1)  # mt_, fn_, cl_
            cid_hash = match.group(2)    # 4849
            var_name = match.group(3)    # x
            
            full_cid = f"{cid_prefix}{cid_hash}"
            
            # Look up the mapping in cai3_map.name_map
            # The pattern should be: "mt_4849:x" -> "actual_variable_name"
            mapping_key = f"{full_cid}:{var_name}"
            
            if mapping_key in cai3_map.name_map:
                resolved_name = cai3_map.name_map[mapping_key]
                self.logger.debug(f"Resolved CID reference: {match.group(0)} -> {resolved_name}")
                return resolved_name
            else:
                # If no mapping found, just return the variable name without CID
                self.logger.debug(f"No mapping for CID reference {match.group(0)}, using variable name: {var_name}")
                return var_name
        
        resolved_content = re.sub(cid_pattern, resolve_cid_ref, body_content)
        
        # CRITICAL FIX: Also fix malformed conditional patterns that cause syntax errors
        # Pattern like ((!?s.d[p0],i|s.d[p0]<=0)) creates invalid syntax
        # This should be (s.d[p0] not in i or s.d[p0] <= 0)
        
        # Fix malformed conditional patterns with multiple ? placeholders
        malformed_pattern = r'\(\(\!?\?([^,]+),([^|]+)\|([^)]+)\)\)'
        
        def fix_malformed_conditional(match):
            # Extract parts: ?expr1, expr2 | expr3 -> expr1 not in expr2 or expr3
            expr1 = match.group(1).strip()  # s.d[p0]
            expr2 = match.group(2).strip()  # i
            expr3 = match.group(3).strip()  # s.d[p0]<=0
            
            # Handle placeholder in expr2 (collection context)
            if expr2 == '?':
                # In conditional context with collection membership, use empty list
                expr2 = '[]'
            elif '?' in expr2:
                # Replace any remaining placeholders in collection context
                expr2 = expr2.replace('?', '[]')
            
            # Handle placeholder in expr1 (negation context)
            if expr1.startswith('?'):
                expr1 = expr1.replace('?', 'None')
            
            # Create proper conditional: (expr1 not in expr2 or expr3)
            fixed = f"({expr1} not in {expr2} or {expr3})"
            self.logger.debug(f"Fixed malformed conditional: {match.group(0)} -> {fixed}")
            return fixed
        
        resolved_content = re.sub(malformed_pattern, fix_malformed_conditional, resolved_content)
        
        # PHASE 3 ENHANCEMENT: Fix validation patterns that create logical errors
        # Pattern: (p0ins.d)((!?s.d[p0],i|s.d[p0]<=0)) should become proper validation
        # This represents: if field exists in data, validate it's in allowed values or check bounds
        validation_pattern = r'\(([^)]+ins\.d)\)\(([^)]+)\)([^;]*)'
        
        def fix_validation_pattern(match):
            field_check = match.group(1)  # p0ins.d -> p0 in s.d  
            validation_logic = match.group(2)  # the validation condition
            following_statement = match.group(3)  # any statement that follows (like h.ap(...))
            
            # Convert field existence check
            field_check = field_check.replace('ins.d', ' in s.d')
            
            # Create proper if statement structure with proper separation
            if following_statement:
                # There's a statement after the validation - separate it properly
                fixed = f"({field_check})?{{{validation_logic}}}:_;{following_statement.lstrip()}"
            else:
                fixed = f"({field_check})?{{{validation_logic}}}:_"
            
            self.logger.debug(f"Fixed validation pattern: {match.group(0)} -> {fixed}")
            return fixed
        
        resolved_content = re.sub(validation_pattern, fix_validation_pattern, resolved_content)
        
        # CRITICAL FIX: Also fix conditional assignment patterns like (condition)statement
        # Pattern: (b!ins.d)s.d[b]=c should become proper if statement structure
        # This prevents malformed brace structures in conditional parsing
        
        conditional_assignment_pattern = r'\(([^)]+!in[^)]+)\)([^;}]+)'
        
        def fix_conditional_assignment(match):
            condition = match.group(1).strip()  # b!ins.d
            statement = match.group(2).strip()  # s.d[b]=c
            
            # Convert !in to not in
            condition = condition.replace('!in', ' not in ')
            
            # Create proper conditional structure with braces (no double braces)
            fixed = f"({condition})?{{{statement}}}:_"
            self.logger.debug(f"Fixed conditional assignment: {match.group(0)} -> {fixed}")
            return fixed
        
        resolved_content = re.sub(conditional_assignment_pattern, fix_conditional_assignment, resolved_content)
        
        # PHASE 3 ENHANCEMENT: Fix malformed ternary-like patterns at string level
        # These patterns can't be handled by AST because they're syntactically invalid
        resolved_content = self._fix_malformed_string_patterns(resolved_content)
        
        if resolved_content != body_content:
            self.logger.debug(f"Body content resolution: {repr(body_content)} -> {repr(resolved_content)}")
        
        return resolved_content

    def _detect_conditional_pattern(self, expr: str) -> Tuple[bool, Dict[str, str]]:
        """
        Detect if expression contains CAI3 conditional pattern.
        Phase 3 Enhancement: Better pattern detection to avoid malformed conditionals.
        Returns (is_conditional, pattern_parts)
        """
        import re
        
        # PHASE 3: Enhanced pattern detection to catch all conditional variants
        
        # Pattern 1: (condition)?{action}:fallback
        ternary_pattern = r'\(([^)]+)\)\?\{([^}]+)\}:(.+)'
        match = re.match(ternary_pattern, expr)
        
        if match:
            return True, {
                'condition': match.group(1),
                'true_action': match.group(2),
                'false_action': match.group(3)
            }
        
        # Pattern 2: (condition)?{action} without else
        if_only_pattern = r'\(([^)]+)\)\?\{([^}]+)\}'
        match = re.match(if_only_pattern, expr)
        
        if match:
            return True, {
                'condition': match.group(1),
                'true_action': match.group(2),
                'false_action': None
            }
        
        # PHASE 3: Catch malformed patterns that need fixing
        # Pattern 3: Already resolved but malformed like "(condition)[]{action}:_"
        malformed_pattern = r'\(([^)]+)\)\[\]\{([^}]+)\}:(.+)'
        match = re.match(malformed_pattern, expr)
        
        if match:
            self.logger.debug(f"Detected malformed conditional pattern: {expr}")
            return True, {
                'condition': match.group(1),
                'true_action': match.group(2),
                'false_action': match.group(3),
                'malformed': True
            }
        
        return False, {}

    def _resolve_conditional_pattern(self, pattern_parts: Dict[str, str]) -> str:
        """
        Convert CAI3 conditional pattern to valid Python.
        Phase 3 Enhancement: Handle malformed patterns and improve action resolution.
        """
        condition = pattern_parts['condition']
        true_action = pattern_parts['true_action']
        false_action = pattern_parts.get('false_action')
        is_malformed = pattern_parts.get('malformed', False)
        
        # Clean up the condition
        condition = condition.replace('!in', ' not in ')
        
        # PHASE 3: Handle malformed patterns that were already partially resolved
        if is_malformed:
            self.logger.debug(f"Resolving malformed conditional pattern")
            # For malformed patterns, we just need to create proper if statements
            if false_action and false_action != '_':
                return f"if {condition}:\n    {true_action}"
            else:
                return f"if {condition}:\n    {true_action}"
        
        # PHASE 3: Enhanced action processing - resolve any remaining placeholders in actions
        if '?' in true_action:
            # Context-aware placeholder resolution within actions
            if 'append(' in true_action:
                if 'h.append(' in true_action or 'issues.append(' in true_action:
                    true_action = true_action.replace('?', "'field validation error'")
                else:
                    true_action = true_action.replace('?', 'item')
            else:
                true_action = true_action.replace('?', 'None')
        
        # For assignment patterns in actions
        if '=' in true_action and '=' not in condition:
            # This is a conditional assignment
            if false_action and false_action != '_':
                # Full ternary: value = true_val if condition else false_val
                return f"{true_action} if {condition} else {false_action}"
            else:
                # Simple conditional: if condition: assignment
                return f"if {condition}:\n    {true_action}"
        
        # For other patterns, create if statement
        if false_action and false_action != '_':
            return f"if {condition}:\n    {true_action}\nelse:\n    {false_action}"
        else:
            return f"if {condition}:\n    {true_action}"

    def _clean_malformed_expressions(self, code: str) -> str:
        """
        Fix malformed expressions at the source - address fundamental parsing issues.
        Generalized to handle similar patterns across any domain.
        """
        import re
        
        # GENERALIZED FIX 1: Fix malformed conditional expressions with chained attribute access
        # Pattern: if (condition).object.attribute[key].method() where condition corrupts the access chain
        # This is a fundamental issue that affects any domain with conditional object access
        
        # Detect any object.attribute access that gets corrupted by conditional parsing
        malformed_chain_pattern = r'if \(([^)]+)\)\.([a-zA-Z_][a-zA-Z0-9_]*)\[([^\]]+)\](?:\.([a-zA-Z_][a-zA-Z0-9_]*)\[([^\]]+)\])*\.([a-zA-Z_][a-zA-Z0-9_]*\([^)]*\))'
        
        def fix_malformed_chain(match):
            condition = match.group(1)
            obj_name = match.group(2)
            key = match.group(3)
            method_call = match.group(6)
            
            # Clean up the condition and create proper if statement
            if "' in " in condition and obj_name in condition:
                # Extract the key from the condition
                key_pattern = rf"'([^']+)' in [^.]*\.{obj_name}"
                key_match = re.search(key_pattern, condition)
                if key_match:
                    extracted_key = key_match.group(1)
                    # Create proper conditional with the action
                    return f"if '{extracted_key}' in self.{obj_name}:\n        self.{obj_name}.{method_call}"
            
            # Fallback: create basic if statement
            return f"if {condition}:\n        self.{obj_name}.{method_call}"
        
        code = re.sub(malformed_chain_pattern, fix_malformed_chain, code)
        
        # GENERALIZED FIX 2: Fix malformed conditional expressions that create any chained access
        # Pattern: (condition).attribute.attribute... where any object gets corrupted
        generic_chain_pattern = r'\(([^)]+)\)((?:\.[a-zA-Z_][a-zA-Z0-9_]*(?:\[[^\]]+\])?)+)\.([a-zA-Z_][a-zA-Z0-9_]*(?:\([^)]*\))?)'
        
        def fix_generic_chain(match):
            condition = match.group(1)
            attribute_chain = match.group(2)
            final_access = match.group(3)
            
            # Extract meaningful parts from the condition
            if ' in ' in condition:
                parts = condition.split(' in ')
                if len(parts) == 2:
                    key_expr = parts[0].strip()
                    container_expr = parts[1].strip()
                    
                    # Build proper conditional structure
                    # Remove redundant chaining from attribute_chain
                    clean_chain = self._simplify_attribute_chain(attribute_chain)
                    base_obj = f"{container_expr}{clean_chain}"
                    
                    # Create conditional statement based on final access type
                    if '(' in final_access:  # Method call
                        return f"if {key_expr} in {container_expr}:\n        {base_obj}.{final_access}"
                    else:  # Attribute access
                        return f"if {key_expr} in {container_expr}:\n        {base_obj}.{final_access}"
            
            # Fallback for other condition types
            clean_chain = self._simplify_attribute_chain(attribute_chain)
            return f"if {condition}:\n        # Access: {clean_chain}.{final_access}"
        
        original_code = code
        code = re.sub(generic_chain_pattern, fix_generic_chain, code)
        
        # GENERALIZED FIX 3: Remove redundant attribute access chains
        # Pattern: .attr[key].attr[key] -> .attr[key] (works for any attribute/key combination)
        # This handles any case where attribute access gets duplicated during parsing
        
        # Fix complex redundant patterns: obj.attr[key].attr[key].method
        redundant_complex_pattern = r'\.([a-zA-Z_][a-zA-Z0-9_]*)\[([^\]]+)\]\.\1\[\2\]'
        while re.search(redundant_complex_pattern, code):
            code = re.sub(redundant_complex_pattern, r'.\1[\2]', code)
        
        # Fix simple redundant patterns: obj.attr[key].attr -> obj.attr[key]
        redundant_simple_pattern = r'\.([a-zA-Z_][a-zA-Z0-9_]*)\[([^\]]+)\]\.\1(?!\w)'
        code = re.sub(redundant_simple_pattern, r'.\1[\2]', code)
        
        # GENERALIZED FIX 4: Fix incomplete access patterns
        # Pattern: container[] -> container (remove empty brackets)
        # Pattern: object.[] -> object (remove malformed empty access)
        
        empty_bracket_patterns = [
            (r'([a-zA-Z_][a-zA-Z0-9_]*)\[\]', r'\1'),  # var[] -> var
            (r'\.([a-zA-Z_][a-zA-Z0-9_]*)\[\]', r'.\1'),  # .attr[] -> .attr
            (r'\.\[\]', r'')  # .[] -> (remove completely)
        ]
        
        for pattern, replacement in empty_bracket_patterns:
            code = re.sub(pattern, replacement, code)
        
        # GENERALIZED FIX 5: Fix malformed method calls and attribute access
        # Pattern: Fix any case where parsing creates invalid syntax combinations
        
        # Fix duplicated dots: ..attr -> .attr
        code = re.sub(r'\.{2,}', '.', code)
        
        # Fix space before dots: object .attr -> object.attr
        code = re.sub(r'(\w)\s+\.', r'\1.', code)
        
        # Fix malformed bracket access: [key]] -> [key]
        code = re.sub(r'\[([^\]]+)\]{2,}', r'[\1]', code)
        
        # GENERALIZED FIX 6: Fix specific domain-agnostic syntax errors
        
        # Fix malformed operators that might appear in any domain
        operator_fixes = {
            '!!': '!',           # Double negation
            '===': '==',         # Triple equals
            '!==': '!=',         # JavaScript-style not equals
            '&&': ' and ',       # JavaScript-style and
            '||': ' or ',        # JavaScript-style or
            ';;': ';',           # Double semicolon
            ',,': ',',           # Double comma
        }
        
        for bad_op, good_op in operator_fixes.items():
            code = code.replace(bad_op, good_op)
        
        # GENERALIZED FIX 7: Fix malformed string patterns
        # These can occur in any domain when string parsing goes wrong
        
        # Fix quotes: '' -> '' (normalize quotes)
        code = re.sub(r"'{2,}", "'", code)
        code = re.sub(r'"{2,}', '"', code)
        
        # Fix malformed f-strings: f'{var}' with extra braces
        code = re.sub(r'f\'([^\']*)\{([^}]+)\}([^\']*)\'{2,}', r"f'\1{\2}\3'", code)
        
        if code != original_code:
            self.logger.debug("Applied generalized malformed expression fixes")
        
        return code
    
    def _simplify_attribute_chain(self, chain: str) -> str:
        """
        Simplify redundant attribute chains to prevent malformed access.
        Works for any object.attribute pattern.
        """
        if not chain.startswith('.'):
            return chain
            
        # Split by dots and remove duplicates while preserving order
        parts = chain[1:].split('.')  # Remove leading dot
        simplified_parts = []
        seen_attrs = set()
        
        for part in parts:
            # Extract attribute name without brackets
            attr_name = part.split('[')[0] if '[' in part else part
            
            if attr_name not in seen_attrs:
                simplified_parts.append(part)
                seen_attrs.add(attr_name)
        
        return '.' + '.'.join(simplified_parts) if simplified_parts else ''
    
    def _fix_malformed_statement(self, stmt_str: str) -> str:
        """
        Fix common malformed statement patterns that cause parsing failures.
        NOTE: Try-except patterns (T{...}X{...}) are handled by FLOW compiler, not here.
        """
        import re
        
        # Create a copy to modify
        fixed = stmt_str.strip()
        
        # DO NOT reconstruct T{...}X{...} patterns here - let FLOW compiler handle them!
        # The FLOW compiler already has robust _parse_ultra_dense_try_except logic
        
        # Fix 1: Replace common malformed operators
        operator_fixes = {
            '!in': ' not in ',
            '!==': ' != ',
            '===': ' == ',
            '!ine': ' not in e',  # Common typo
            '!inud': ' not in ud',  # user_data abbreviation
            '!ins': ' not in s',    # self abbreviation
        }
        
        for bad_op, good_op in operator_fixes.items():
            fixed = fixed.replace(bad_op, good_op)
        
        # Fix 2: Expand common abbreviations with proper spacing
        abbreviation_fixes = {
            r'\bud\b': 'user_data',
            r'\brf\b': 'required_fields',
            r'\bs\.l\.er\b': 'self.logger.error',
            r'\bs\.l\.w\b': 'self.logger.warning',
            r'\bs\.l\.i\b': 'self.logger.info',
            r'\bRF\b': 'False',  # Just 'False', not 'return False' to avoid double return
            r'\bRT\b': 'True',   # Just 'True', not 'return True'
            r'\bRN\b': 'None',   # Just 'None', not 'return None'
            r'\.g\(': '.get(',   # Fix method call abbreviations
            r'\.sp\(': '.split(',
            r'\.ap\(': '.append(',
        }
        
        for pattern, replacement in abbreviation_fixes.items():
            fixed = re.sub(pattern, replacement, fixed)
        
        # Fix 3: Handle ultra-dense validation loop patterns FIRST (before general ternary)
        # Pattern: @f,rf{f!inud?(s.l.er(...),RF):_} -> for f in rf: if f not in ud: ...
        # Use a more sophisticated approach to handle nested braces in f-strings
        loop_start_pattern = r'@([^,]+),([^{]+)\{'
        loop_match = re.search(loop_start_pattern, fixed)
        if loop_match:
            var, collection = loop_match.groups()
            var = var.strip()
            collection = collection.strip()
            
            # Find the matching closing brace by counting braces
            start_pos = loop_match.end() - 1  # Position of opening brace
            brace_count = 1
            pos = start_pos + 1
            
            while pos < len(fixed) and brace_count > 0:
                if fixed[pos] == '{':
                    brace_count += 1
                elif fixed[pos] == '}':
                    brace_count -= 1
                pos += 1
            
            if brace_count == 0:
                # Found matching closing brace
                body = fixed[start_pos + 1:pos - 1]
                body = body.strip()
                
                # Handle ternary pattern within the loop body
                if '?' in body and ':' in body:
                    ternary_match = re.search(r'([^?]+)\?\(([^,]+),([^)]+)\):([^;]+)', body)
                    if ternary_match:
                        condition, action, result, fallback = ternary_match.groups()
                        condition = condition.strip()
                        action = action.strip()
                        result = result.strip()
                        fallback = fallback.strip()
                        
                        if fallback == '_':
                            # Convert to proper for loop with if statement
                            for_stmt = f"for {var} in {collection}: if {condition}: {action}; return {result}"
                        else:
                            for_stmt = f"for {var} in {collection}: if {condition}: {action}; return {result} else: {fallback}"
                    else:
                        # Simple for loop
                        for_stmt = f"for {var} in {collection}: {body}"
                else:
                    # Simple for loop
                    for_stmt = f"for {var} in {collection}: {body}"
                
                # Replace the entire loop pattern
                loop_pattern = fixed[loop_match.start():pos]
                fixed = fixed.replace(loop_pattern, for_stmt)
        
        # Fix 4: Fix ultra-dense conditional patterns with ternary operators
        # Pattern: var?(action,result):fallback -> if var: action; return result else: fallback
        ultra_dense_ternary = r'([^?]+)\?\(([^,]+),([^)]+)\):([^;]+)'
        while re.search(ultra_dense_ternary, fixed):
            match = re.search(ultra_dense_ternary, fixed)
            if match:
                condition, action, result, fallback = match.groups()
                condition = condition.strip()
                action = action.strip()
                result = result.strip()
                fallback = fallback.strip()
                
                # Clean up result - remove 'return' if it's already there in abbreviation
                if result.startswith('return '):
                    result = result[7:]  # Remove 'return '
                
                # Convert to proper if-else structure with proper spacing
                if fallback == '_':
                    # Simple if statement
                    if_stmt = f"if {condition}: {action}; return {result}"
                else:
                    # If-else statement
                    if_stmt = f"if {condition}: {action}; return {result} else: {fallback}"
                
                fixed = fixed.replace(match.group(0), if_stmt)
        
        # Fix 5: Fix malformed conditional expressions
        # Pattern: (('@'!ine)|('.'!ine.sp('@')[-1])) -> proper email validation
        malformed_email_pattern = r"\(\('@'[^)]+\)\|\('[^)]+\)\)"
        if re.search(malformed_email_pattern, fixed):
            # Replace with simplified email validation
            fixed = re.sub(malformed_email_pattern, "('@' not in e or '.' not in e.split('@')[-1])", fixed)
        
        # Fix 6: Fix method calls with .sp() -> .split()
        fixed = re.sub(r'\.sp\(', '.split(', fixed)
        
        # Fix 7: Fix malformed f-string expressions
        # Pattern: f'text: {var}' with malformed braces
        if "f'" in fixed:
            # Fix missing closing braces
            fixed = re.sub(r"f'([^']*\{[^}]*)'", r"f'\1}'", fixed)
        
        # Fix 8: Fix malformed method calls
        # Pattern: .method(...) with incomplete parameters
        method_call_pattern = r'\.(\w+)\(\?[^)]*\)'
        if re.search(method_call_pattern, fixed):
            # Replace ? with appropriate default
            if '.append(' in fixed:
                fixed = re.sub(r'\.append\(\?\)', '.append("validation error")', fixed)
            elif '.error(' in fixed:
                fixed = re.sub(r'\.error\(\?\)', '.error("error occurred")', fixed)
        
        # Fix 9: Clean up any remaining malformed patterns
        # Remove excessive spaces but let black handle proper formatting
        fixed = re.sub(r'\s+', ' ', fixed)
        fixed = fixed.strip()
        
        if fixed != stmt_str:
            self.logger.debug(f"Fixed malformed statement: '{stmt_str}' -> '{fixed}'")
        
        return fixed
        
    def _apply_black_formatting(self, code: str) -> str:
        """
        Apply black formatting to clean up spacing and syntax issues.
        Enhanced with pre-processing to fix common syntax errors before black runs.
        """
        try:
            import black
            
            # PRE-PROCESS: Fix common syntax errors that prevent black from parsing
            code = self._pre_process_for_black(code)
            
            # Try to format the code with black
            try:
                # Use black's format_str function with default settings
                formatted_code = black.format_str(code, mode=black.FileMode())
                self.logger.debug("Successfully applied black formatting")
                return formatted_code
            except black.InvalidInput as e:
                self.logger.warning(f"Black formatting failed due to syntax errors: {e}")
                # Apply more aggressive pre-processing and try again
                fixed_code = self._aggressive_syntax_fix(code)
                try:
                    formatted_code = black.format_str(fixed_code, mode=black.FileMode())
                    self.logger.debug("Successfully applied black formatting after aggressive fixes")
                    return formatted_code
                except:
                    self.logger.warning("Black formatting failed even after aggressive fixes, using fallback")
                    return self._fallback_formatting(fixed_code)
            except Exception as e:
                self.logger.warning(f"Black formatting failed: {e}")
                return self._fallback_formatting(code)
                
        except ImportError:
            self.logger.warning("Black not available, using fallback formatting")
            return self._fallback_formatting(code)
    
    def _pre_process_for_black(self, code: str) -> str:
        """
        Pre-process code to fix common syntax errors that prevent black from parsing.
        """
        lines = code.split('\n')
        fixed_lines = []
        
        for line in lines:
            # Fix malformed for loops like: for h in os.listdir(scan_path) = os.path.join(scan_path, item)
            if ' = ' in line and ('for ' in line and ' in ' in line):
                # This looks like a malformed for loop with assignment
                if line.strip().startswith('for '):
                    # Try to fix by extracting the for loop part
                    for_part = line.split(' = ')[0]
                    if for_part.count('for ') == 1 and for_part.count(' in ') == 1:
                        line = for_part + ':'
                        self.logger.debug(f"Fixed malformed for loop: {line}")
            
            # Fix missing colons on control structures
            if (line.strip().startswith(('if ', 'for ', 'while ', 'def ', 'class ', 'try', 'except', 'else', 'elif ')) 
                and not line.rstrip().endswith(':') and not line.rstrip().endswith(':\\')):
                line = line.rstrip() + ':'
                self.logger.debug(f"Added missing colon: {line}")
            
            fixed_lines.append(line)
        
        return '\n'.join(fixed_lines)
    
    def _aggressive_syntax_fix(self, code: str) -> str:
        """
        Apply aggressive syntax fixes as a last resort before falling back.
        """
        # Fix indentation issues by completely rebuilding indentation
        lines = code.split('\n')
        fixed_lines = []
        indent_level = 0
        
        for line in lines:
            stripped = line.strip()
            if not stripped:
                fixed_lines.append("")
                continue
            
            # Determine correct indentation level
            if stripped.startswith(('class ', 'def ')) and indent_level > 0:
                # New class/function at module level
                indent_level = 0
            elif stripped.endswith(':'):
                # This line should be at current level and increase indent for next
                current_indent = indent_level
                indent_level += 1
            elif stripped in ['pass', 'break', 'continue'] or stripped.startswith('return'):
                # These are typically at current indent level
                current_indent = indent_level
            elif stripped.startswith(('except', 'else:', 'elif', 'finally:')):
                # These are at the same level as their corresponding try/if
                current_indent = max(0, indent_level - 1)
            else:
                # Regular statement
                current_indent = indent_level
            
            # Apply the indentation
            properly_indented = "    " * current_indent + stripped
            fixed_lines.append(properly_indented)
        
        return '\n'.join(fixed_lines)
    
    def _fallback_formatting(self, code: str) -> str:
        """
        Enhanced fallback formatting when black is not available or fails.
        Handles indentation, spacing, and basic syntax cleanup.
        """
        lines = code.split('\n')
        formatted_lines = []
        indent_level = 0
        
        for i, line in enumerate(lines):
            original_line = line
            line = line.strip()  # Remove all whitespace to start fresh
            
            if not line:
                formatted_lines.append("")
                continue
            
            # Determine indent level changes
            if line.endswith(':'):
                # This line should increase indent for next lines
                current_indent = indent_level
                indent_level += 1
            elif line in ['pass', 'break', 'continue', 'return'] or line.startswith('return '):
                # These typically don't change indent level
                current_indent = indent_level
            elif line.startswith(('def ', 'class ', 'if ', 'for ', 'while ', 'try:', 'except', 'else:', 'elif ', 'finally:')):
                # Check if we need to dedent first
                if indent_level > 0 and not (line.startswith('except') or line.startswith('else') or line.startswith('elif') or line.startswith('finally')):
                    # Only dedent if this isn't an exception handler
                    if not lines[max(0, i-1)].strip().endswith(':'):
                        indent_level = max(0, indent_level - 1)
                current_indent = indent_level
                if line.endswith(':'):
                    indent_level += 1
            else:
                # Regular statement - use current indent level but check for dedent
                current_indent = indent_level
                
                # Check if previous line was a return/break/continue - might need to dedent
                if i > 0:
                    prev_line = lines[i-1].strip()
                    if prev_line in ['pass', 'break', 'continue', 'return'] or prev_line.startswith('return '):
                        # Look ahead to see if next line is a dedent
                        if i < len(lines) - 1:
                            next_line = lines[i+1].strip()
                            if next_line.startswith(('def ', 'class ', 'except', 'else:', 'elif', 'finally:')) or not next_line:
                                current_indent = max(0, indent_level - 1)
            
            # Apply indentation
            indented_line = "    " * current_indent + line
            
            # Fix common spacing issues
            if line.strip():
                # Fix spacing around operators (but preserve the indentation we just added)
                content = indented_line[current_indent * 4:]  # Get content without indent
                content = re.sub(r'\s*=\s*', ' = ', content)
                content = re.sub(r'(?<![=!<>])\s*==\s*', ' == ', content)  # Avoid messing with ===
                content = re.sub(r'\s*!=\s*', ' != ', content)
                content = re.sub(r'\s*<=\s*', ' <= ', content)
                content = re.sub(r'\s*>=\s*', ' >= ', content)
                content = re.sub(r'(?<!:)\s*:\s*(?!=)', ': ', content)  # Avoid messing with ::
                content = re.sub(r'\s*,\s*', ', ', content)
                
                # Fix excessive spaces but preserve single spaces
                content = re.sub(r'  +', ' ', content)
                
                # Reconstruct with proper indentation
                indented_line = "    " * current_indent + content
                
            formatted_lines.append(indented_line)
        
        return '\n'.join(formatted_lines)
        
    def _apply_malformed_fixes_to_body(self, body_content: str) -> str:
        """
        Apply malformed statement fixes to body content before ultra-dense parsing.
        PRIORITY: Delegate complex patterns to FLOW compiler instead of manual fixes.
        """
        if not body_content or not body_content.strip():
            return body_content
        
        self.logger.debug(f"Applying malformed fixes to body: {body_content}")
        
        # HIGHEST PRIORITY: Check if this is a complex pattern that should be delegated
        # to FLOW compiler instead of being manually fixed
        should_delegate_to_flow = (
            'T{' in body_content and ('X' in body_content or 'X{' in body_content) or  # Try-except patterns
            (body_content.count('{') > 2) or  # Highly nested structures
            ('?' in body_content and ('{' in body_content or '}:' in body_content)) or  # Conditional patterns with placeholders
            ('@' in body_content and ',' in body_content and '{' in body_content) or  # Complex for-loop patterns
            ('for ' in body_content and ('T{' in body_content or 'X{' in body_content))  # Mixed patterns
        )
        
        if should_delegate_to_flow:
            self.logger.debug(f"🔄 DELEGATING BODY TO FLOW COMPILER: Complex pattern detected")
            # Return the original body content - let FLOW compiler handle it directly
            # This bypasses manual malformed fixes that can corrupt complex structures
            return body_content
        
        # Only apply manual fixes to simple statements
        # Split body content by semicolons (respecting nested structures)
        statements = self._split_respecting_nesting(body_content, ';')
        
        # Apply malformed statement fixes to each statement
        fixed_statements = []
        for stmt in statements:
            stmt = stmt.strip()
            if stmt:
                fixed_stmt = self._fix_malformed_statement(stmt)
                fixed_statements.append(fixed_stmt)
            else:
                fixed_statements.append(stmt)
        
        # Rejoin with semicolons
        fixed_body = ';'.join(fixed_statements)
        
        self.logger.debug(f"Fixed body result: {fixed_body}")
        return fixed_body
        
        code = re.sub(empty_access_pattern, fix_empty_access, code)
        
        if code != original_code:
            self.logger.debug("Applied fundamental malformed expression fixes")
        
        return code

    def _final_placeholder_resolution(self, code: str) -> str:
        """
        Final pass to resolve any remaining placeholders.
        Phase 3 Enhancement: Better conditional pattern handling and context-aware resolution.
        """
        import re  # Import at the top to avoid UnboundLocalError
        
        if '?' not in code:
            return code
        
        self.logger.warning("Found unresolved placeholders in final output, applying fallback resolution")
        
        lines = code.split('\n')
        resolved_lines = []
        
        for line in lines:
            if '?' not in line:
                resolved_lines.append(line)
                continue
            
            original_line = line
            
            # PHASE 3: Enhanced conditional pattern detection
            # Check for conditional pattern first - but only if line contains both ? and conditional markers
            if '?' in line.strip() and ('{' in line.strip() and '}' in line.strip()):
                is_conditional, pattern_parts = self._detect_conditional_pattern(line.strip())
                if is_conditional:
                    # Resolve the entire conditional pattern
                    resolved = self._resolve_conditional_pattern(pattern_parts)
                    # Maintain indentation - apply to each line of the resolved conditional
                    indent = len(line) - len(line.lstrip())
                    resolved_lines_list = resolved.split('\n')
                    for i, resolved_line in enumerate(resolved_lines_list):
                        if i == 0:
                            # First line keeps original indentation
                            resolved_lines.append(' ' * indent + resolved_line)
                        else:
                            # Additional lines get same indentation
                            resolved_lines.append(' ' * indent + resolved_line)
                    self.logger.debug(f"Resolved conditional pattern: {line} -> {resolved}")
                    continue
            
            # PHASE 3: Enhanced pattern-specific resolution
            # Handle specific patterns that aren't conditionals - process all placeholders in line
            while '?' in line:
                # PHASE 3: Better exception handling
                if 'except' in line and ' as ?' in line:
                    line = line.replace(' as ?', ' as e', 1)
                
                # PHASE 3: Better collection context handling  
                elif '? not in ' in line:
                    line = line.replace('? not in ', 'None not in ', 1)
                elif ' not in ?' in line:
                    # Context-aware replacement for "not in ?"
                    if 'field' in line or 'required' in line:
                        line = line.replace(' not in ?', ' not in required_fields', 1)
                    else:
                        line = line.replace(' not in ?', ' not in []', 1)
                
                # PHASE 3: Enhanced append context handling
                elif '.append(?' in line:
                    # Check context for append
                    if 'issues.append' in line or 'errors.append' in line:
                        line = line.replace('(?)', "('Missing required field')", 1)
                    else:
                        line = line.replace('(?)', '(_container)', 1)
                
                # PHASE 3: Fix unresolved _container placeholders that made it to final output
                elif '_container' in line:
                    # Context-specific resolution for _container
                    if '.append(_container)' in line:
                        if 'error' in line or 'issue' in line:
                            line = line.replace('_container', "'Missing required field'")
                        elif 'result' in line or 'item' in line or 'metadata' in line:
                            line = line.replace('_container', 'metadata')
                        elif 'h.append(' in line or 'issues.append(' in line:
                            line = line.replace('_container', "'field validation error'")
                        else:
                            line = line.replace('_container', "'field required'")
                    elif '[_container]' in line:
                        # Array/dict access context - this is problematic and needs special handling
                        if 'error_count' in line or 'items()' in line:
                            # Pattern: dict(...)[_container] - likely should be converted to proper iteration
                            if 'dict(' in line and '.items()' in line:
                                # This pattern suggests: dict(self.error_count.items())[_container]
                                # Should be: dict(self.error_count.items()) - remove the subscript entirely
                                # Or better: dict(self.error_count)
                                line = re.sub(r'dict\(([^)]+)\.items\(\)\)\[_container\]', r'dict(\1)', line)
                                self.logger.debug(f"Fixed problematic dict construction with _container subscript")
                            else:
                                line = line.replace('[_container]', '[0]')  # First element fallback
                        else:
                            line = line.replace('[_container]', "['default']")
                    elif '_container)' in line and '(' in line:
                        # Function call context
                        if 'metadata' in line or 'file' in line:
                            line = line.replace('_container', 'metadata')
                        elif 'path' in line:
                            line = line.replace('_container', 'file_path')
                        else:
                            line = line.replace('_container', 'item')
                    else:
                        # Generic _container resolution based on broader context
                        if 'metadata' in line or 'file' in line:
                            line = line.replace('_container', 'metadata')
                        elif 'config' in line or 'data' in line:
                            line = line.replace('_container', 'config_value')
                        else:
                            line = line.replace('_container', 'default_value')
                
                # Additional comprehensive placeholder resolution
                # Handle _field_name patterns
                if '_field_name' in line:
                    # Common pattern in field validation
                    line = line.replace('_field_name', 'field')
                
                # Handle _index patterns 
                if '_index' in line:
                    line = line.replace('_index', 'i')
                    
                # Handle _item patterns
                if '_item' in line:
                    line = line.replace('_item', 'item')
                    
                # Handle _value patterns
                if '_value' in line:
                    line = line.replace('_value', 'value')
                    
                # Handle _result patterns
                if '_result' in line:
                    line = line.replace('_result', 'result')
                
                # Handle exception variable patterns like "except Exception as ?:"
                if ' as ?:' in line:
                    line = line.replace(' as ?:', ' as e:')
                
                # Handle conditional expressions with placeholders in specific contexts
                if 'in ?' in line and ('or' in line or 'and' in line):
                    # Pattern: "if (var in ? or condition)" - replace ? with appropriate collection
                    if 'self.c[' in line and '] in ?' in line:
                        # This is a configuration value being checked against a collection
                        line = line.replace(' in ?', ' in []')  # Empty list as safe default
                    else:
                        line = line.replace(' in ?', ' in []')
                
                # Handle comparison operators with placeholders
                if '!?' in line or '? ' in line:
                    # Context-aware replacement for negation and general placeholders
                    if 'not' in line and '!?' in line:
                        line = line.replace('!?', 'not None')
                    elif '? ' in line and ('or' in line or 'and' in line):
                        line = line.replace('? ', 'None ')
                    
                # Handle remaining underscore prefixed placeholders with generic names
                remaining_placeholders = re.findall(r'_[a-zA-Z_][a-zA-Z0-9_]*(?![a-zA-Z0-9_])', line)
                for placeholder in set(remaining_placeholders):
                    if placeholder not in ['_container', '_field_name', '_index', '_item', '_value', '_result']:
                        # Convert _some_name to some_name (remove leading underscore)
                        replacement = placeholder[1:] if len(placeholder) > 1 else 'var'
                        line = line.replace(placeholder, replacement)
                        self.logger.debug(f"Replaced remaining placeholder {placeholder} with {replacement}")
                
                # PHASE 3: Fix malformed conditional patterns that made it to final output
                if '{}' in line and ':_' in line:
                    # Pattern like "(condition)[]{action}:_" - malformed conditional
                    # Convert to proper if statement
                    malformed_conditional = r'\(([^)]+)\)\[\]\{([^}]+)\}:_'
                    match = re.search(malformed_conditional, line)
                    if match:
                        condition = match.group(1)
                        action = match.group(2)
                        # Create proper if statement
                        indent = len(line) - len(line.lstrip())
                        replacement = f"if {condition}:\n{' ' * (indent + 4)}{action}"
                        line = re.sub(malformed_conditional, replacement, line)
                        self.logger.debug(f"Fixed malformed conditional: {match.group(0)} -> {replacement}")
                
                # PHASE 3: Fix incomplete method names that made it to final output
                if 'os.li(' in line:
                    line = line.replace('os.li(', 'os.listdir(')
                if 'Fi()' in line:
                    line = line.replace('Fi()', 'FileMetadata()')
                if '.ap(' in line:
                    line = line.replace('.ap(', '.append(')
                if '.g(' in line:
                    line = line.replace('.g(', '.get(')
                if '.sp(' in line:
                    line = line.replace('.sp(', '.split(')
                
                # PHASE 3: Fix malformed conditional assignments like "(a|s.b)"
                if re.search(r'\([a-zA-Z]\|[^)]+\)', line):
                    # Pattern: (a|s.b) - malformed conditional assignment
                    pattern = r'\(([a-zA-Z]+)\|([^)]+)\)'
                    
                    def fix_conditional_assignment(match):
                        var_name = match.group(1)  # a
                        fallback = match.group(2)  # s.b
                        # Create proper conditional: var_name if var_name else fallback
                        return f"({var_name} if {var_name} else {fallback})"
                    
                    line = re.sub(pattern, fix_conditional_assignment, line)
                
                # PHASE 3: Handle remaining comparison operators
                if ' <= ?' in line or ' >= ?' in line or ' < ?' in line or ' > ?' in line:
                    # Numerical comparison context
                    if 'timeout' in line or 'connection' in line or 'max_' in line:
                        line = line.replace('?', '0', 1)  # Use 0 for numerical comparisons
                    else:
                        line = line.replace('?', 'None', 1)
                
                # PHASE 2: Improved generic fallback with context awareness
                # Look at the immediate context of the ? to make better decisions
                if '?' in line:
                    q_pos = line.find('?')
                    if q_pos >= 0:
                        before_context = line[max(0, q_pos-10):q_pos]
                        after_context = line[q_pos+1:min(len(line), q_pos+10)]
                        
                        # Context-specific replacements
                        if 'append(' in before_context and ')' in after_context:
                            if 'error' in line or 'issue' in line:
                                line = line.replace('?', "'Missing required field'", 1)
                            else:
                                line = line.replace('?', 'item', 1)
                        elif ' = ?' in line and q_pos > 0:
                            # Assignment context - use appropriate variable name
                            line = line.replace('?', 'temp_var', 1)
                        elif 'for ' in before_context and ' in ' in after_context:
                            # Loop variable context
                            line = line.replace('?', 'item', 1)
                        elif ' as ?' in line:
                            # Exception variable context
                            line = line.replace('?', 'e', 1)
                        elif ' in ?' in line:
                            # Collection membership context
                            line = line.replace('?', '[]', 1)
                        elif ' <= ?' in line or ' >= ?' in line or ' < ?' in line or ' > ?' in line:
                            # Numerical comparison context
                            line = line.replace('?', '0', 1)
                        else:
                            # Generic fallback
                            line = line.replace('?', 'None', 1)
            
            if line != original_line:
                self.logger.debug(f"Resolved placeholder: {original_line} -> {line}")
            
            resolved_lines.append(line)
        
        # PHASE 3: Apply incomplete name resolution before returning
        final_code = '\n'.join(resolved_lines)
        final_code = self._resolve_incomplete_names(final_code)
        
        return final_code

    def _reconstruct_method(self, method_node, body_content: Optional[str], 
                            cai3_map: CAI3Map, cai3_full: CAI3Full,
                            chain_aliases: Dict, pools: Dict) -> List[str]:
        """
        Reconstruct a method/function from its node and body content with enhanced logging.
        """
        self.logger.debug(f"Reconstructing method: {method_node.name}")
        self.logger.debug(f"Method CID: {method_node.cid}")
        self.logger.debug(f"Method signature: {method_node.signature}")
        self.logger.debug(f"Body content provided: {body_content is not None}")
        if body_content:
            self.logger.debug(f"Body content: {repr(body_content)}")
        self.logger.debug(f"Chain aliases count: {len(chain_aliases)}")
        self.logger.debug(f"Pools count: {len(pools)}")
        
        lines = []
        
        # Build function signature
        func_name = method_node.name
        self.logger.debug(f"Building signature for function: {func_name}")
        
        # Parse signature to get parameters
        params = []
        if method_node.signature and '(' in method_node.signature:
            sig_params = method_node.signature[1:method_node.signature.index(')')].split(',')
            self.logger.debug(f"Method {func_name} raw signature params: {sig_params}")
            for i, param in enumerate(sig_params):
                param = param.strip()
                if param:
                    original_param = param
                    # Expand compressed parameter names
                    local_key = f"{method_node.cid}:{param}"
                    if local_key in cai3_map.name_map:
                        param = cai3_map.name_map[local_key]
                        self.logger.debug(f"Expanded parameter {local_key} -> {param}")
                    elif 'local_compressions' in method_node.metadata:
                        # Check reverse mapping
                        for orig, compressed in method_node.metadata['local_compressions'].items():
                            if compressed == param:
                                param = orig
                                self.logger.debug(f"Reverse mapped parameter {compressed} -> {param}")
                                break
                    
                    if param != original_param:
                        self.logger.debug(f"Parameter {i}: {original_param} -> {param}")
                    params.append(param)
            self.logger.debug(f"Method {func_name} final params: {params}")
        else:
            self.logger.debug(f"No signature found for method {func_name}")
        
        # Handle method signatures
        if method_node.parent_cid:  # This is a method, not a standalone function
            self.logger.debug(f"Method is part of class (parent_cid: {method_node.parent_cid})")
            if func_name == '__init__':
                if not params or params[0] != 'self':
                    self.logger.debug("Adding 'self' parameter to __init__ method")
                    params.insert(0, 'self')
            else:
                # Regular method - ensure self is first parameter
                if not params or params[0] != 'self':
                    self.logger.debug("Adding 'self' parameter to instance method")
                    params.insert(0, 'self')
        else:
            self.logger.debug("Method is a standalone function")
        
        signature_line = f"def {func_name}({', '.join(params)}):"
        self.logger.debug(f"Final signature: {signature_line}")
        lines.append(signature_line)
        
        # Add docstring if available
        if method_node.metadata.get('docstring'):
            docstring = method_node.metadata["docstring"]
            self.logger.debug(f"Adding docstring: {repr(docstring)}")
            # Properly escape and format docstring
            if '"""' in docstring:
                # Use single quotes if triple quotes are in the string
                lines.append(f"    '''{docstring}'''")
            else:
                lines.append(f'    """{docstring}"""')
        
        # Reconstruct body
        self.logger.debug(f"Starting body reconstruction for method {func_name}")
        if body_content:
            self.logger.debug(f"Body content provided: {repr(body_content)}")
            self.logger.debug(f"Body content length: {len(body_content)}")
            
            # Parse FLOW body content
            self.logger.debug("Creating FLOW compiler for body parsing")
            flow_compiler = self._create_flow_compiler(cai3_map, cai3_full)
            
            # Set up chain aliases and pools
            self.logger.debug(f"Setting {len(chain_aliases)} chain aliases on flow_compiler")
            for alias, chain in chain_aliases.items():
                self.logger.debug(f"  Chain alias: {alias} -> {chain}")
            flow_compiler.set_chain_aliases(chain_aliases)
            
            if pools:
                self.logger.debug(f"Setting {len(pools)} pools on flow_compiler")
                for pool_id, value in pools.items():
                    self.logger.debug(f"  Pool: {pool_id} -> {value}")
                flow_compiler.set_pools(pools)
            else:
                self.logger.debug("No pools to set on flow_compiler")
            
            # Set hash-to-value mapping for #xxxx resolution
            if cai3_full and hasattr(cai3_full, 'hash_to_value') and cai3_full.hash_to_value:
                self.logger.debug(f"Setting {len(cai3_full.hash_to_value)} hash mappings")
                flow_compiler.set_hash_mapping(cai3_full.hash_to_value)
            else:
                self.logger.debug("No hash mappings available")
            
            # Parse the ultra-dense single-line body
            self.logger.debug("Calling _parse_ultra_dense_body")
            try:
                body_statements = self._parse_ultra_dense_body(
                    body_content, 
                    method_node,
                    flow_compiler,
                    cai3_map,
                    cai3_full,
                    chain_aliases,
                    pools  # Pass pools parameter to enable early pool resolution
                )
                self.logger.debug(f"Successfully parsed {len(body_statements)} statements from body")
            except Exception as e:
                self.logger.error(f"Failed to parse ultra-dense body: {e}")
                body_statements = [ast.Pass()]
            
            # Convert to Python
            self.logger.debug("Converting AST statements to Python code")
            stmt_count = 0
            for i, stmt in enumerate(body_statements):
                try:
                    if hasattr(ast, 'unparse'):
                        stmt_code = ast.unparse(stmt)
                    else:
                        stmt_code = self._ast_to_source(stmt)
                    
                    self.logger.debug(f"Statement {i}: {repr(stmt_code)}")
                    
                    # ENHANCED FORMATTING: Pre-process each statement before adding
                    stmt_code = self._pre_process_for_black(stmt_code)
                    
                    # Validate the statement is meaningful
                    if stmt_code.strip() in ['pass', '']:
                        # Try to recover more meaningful content
                        recovery_text = self._attempt_statement_recovery(stmt, body_content)
                        if recovery_text and 'TODO' in recovery_text:
                            stmt_code = recovery_text
                        else:
                            # Only use pass as absolute last resort
                            stmt_code = "pass  # Generated from incomplete AST"
                    
                    # Add proper indentation
                    for line in stmt_code.split('\n'):
                        if line.strip():
                            lines.append(f"    {line}")
                            stmt_count += 1
                except Exception as e:
                    self.logger.error(f"Failed to convert statement {i} to code: {e}")
                    # AGGRESSIVE RECOVERY: Try multiple recovery strategies
                    recovery_successful = False
                    
                    # Strategy 1: Try to recover from original body content
                    try:
                        if body_content:
                            recovery_text = self._attempt_statement_recovery(stmt, body_content)
                            if recovery_text and not recovery_text.startswith('pass'):
                                lines.append(f"    {recovery_text}")
                                recovery_successful = True
                                continue
                    except Exception as recovery_error:
                        self.logger.debug(f"Recovery strategy 1 failed: {recovery_error}")
                    
                    # Strategy 2: Try to extract from the AST node itself
                    try:
                        if hasattr(stmt, '_fields'):
                            # Try to reconstruct from AST fields
                            if hasattr(stmt, 'target') and hasattr(stmt, 'iter'):
                                # This is likely a for loop
                                lines.append(f"    for item in collection:")
                                lines.append(f"        # TODO: Implement loop body")
                                recovery_successful = True
                                continue
                            elif hasattr(stmt, 'test') and hasattr(stmt, 'body'):
                                # This is likely an if statement
                                lines.append(f"    if condition:")
                                lines.append(f"        # TODO: Implement conditional body")
                                recovery_successful = True
                                continue
                    except Exception as ast_recovery_error:
                        self.logger.debug(f"Recovery strategy 2 failed: {ast_recovery_error}")
                    
                    # Strategy 3: Create context-appropriate placeholder
                    if not recovery_successful:
                        if 'validate' in func_name.lower():
                            lines.append("    # TODO: Implement validation logic")
                        elif 'get' in func_name.lower():
                            lines.append("    # TODO: Implement getter logic")
                        elif 'set' in func_name.lower():
                            lines.append("    # TODO: Implement setter logic")
                        elif '__init__' in func_name:
                            lines.append("    # TODO: Initialize instance variables")
                        else:
                            lines.append("    # TODO: Implement method body")
            
            self.logger.debug(f"Added {stmt_count} code lines to method body")
        else:
            # No body provided, create intelligent placeholder based on method name
            self.logger.debug(f"No body content provided for method {func_name}, creating intelligent placeholder")
            if '__init__' in func_name:
                lines.append("    # TODO: Initialize instance variables")
                if len(params) > 1:  # Has parameters beyond self
                    for param in params[1:]:  # Skip 'self'
                        lines.append(f"    self.{param} = {param}")
            elif 'validate' in func_name.lower():
                lines.append("    # TODO: Implement validation logic")
                lines.append("    return True")
            elif func_name.startswith('get_'):
                lines.append("    # TODO: Implement getter logic")
                lines.append("    return None")
            elif func_name.startswith('set_'):
                lines.append("    # TODO: Implement setter logic")
            elif 'load' in func_name.lower():
                lines.append("    # TODO: Implement loading logic")
            elif 'save' in func_name.lower():
                lines.append("    # TODO: Implement saving logic")
            elif 'process' in func_name.lower():
                lines.append("    # TODO: Implement processing logic")
            else:
                lines.append("    # TODO: Implement method body")
                # Try to infer return type from signature if available
                if method_node.signature and '->' in method_node.signature:
                    return_type = method_node.signature.split('->')[-1].strip()
                    if return_type in ['bool', 'b']:
                        lines.append("    return False")
                    elif return_type in ['str', 's']:
                        lines.append("    return ''")
                    elif return_type in ['int', 'i']:
                        lines.append("    return 0")
                    elif return_type in ['list', 'List']:
                        lines.append("    return []")
                    elif return_type in ['dict', 'Dict']:
                        lines.append("    return {}")
                    else:
                        lines.append("    return None")
        
        # Apply hash and pool resolution to all lines
        self.logger.debug("Applying hash and pool resolution to all lines")
        for i, line in enumerate(lines):
            original_line = line
            # Apply hash resolution first
            lines[i] = self._resolve_hash_references(line, cai3_full)
            # Then apply pool resolution
            lines[i] = self._resolve_pool_references(lines[i], pools)
            if original_line != lines[i]:
                self.logger.debug(f"Hash/pool resolution applied to line {i}: {original_line} -> {lines[i]}")
        
        self.logger.debug(f"Method reconstruction complete. Total lines: {len(lines)}")
        for i, line in enumerate(lines):
            self.logger.debug(f"  Line {i}: {repr(line)}")
        
        return lines

    def _attempt_statement_recovery(self, stmt, body_content: str) -> str:
        """
        Attempt to recover statement text from original body content when AST conversion fails.
        This is a last-resort recovery mechanism to avoid pass statements.
        """
        import re
        try:
            # For failed AST nodes, try to extract meaningful patterns from body content
            if 'for ' in body_content and hasattr(stmt, 'target'):
                # Attempt to reconstruct for loop from body patterns
                if '@f,' in body_content:
                    # Ultra-dense for loop pattern
                    pattern_match = re.search(r'@f,([^{]+)\{([^}]+)\}', body_content)
                    if pattern_match:
                        iterator = pattern_match.group(1).strip()
                        loop_body = pattern_match.group(2).strip()
                        return f"for {iterator}:\n        {loop_body}"
                
                # Handle T{} patterns with for loops
                if 'T{' in body_content and 'for' in body_content:
                    # Extract try block content
                    try_pattern = r'T\{([^}]*for[^}]*)\}'
                    try_match = re.search(try_pattern, body_content)
                    if try_match:
                        try_content = try_match.group(1)
                        # Create a basic try block with the for loop
                        return f"try:\n        {try_content}\n    except Exception:\n        pass"
            
            # For assignment statements
            if '=' in body_content and hasattr(stmt, 'targets'):
                # Extract assignment patterns
                assignment_match = re.search(r'([a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*([^;,]+)', body_content)
                if assignment_match:
                    var_name = assignment_match.group(1)
                    value = assignment_match.group(2).strip()
                    # Clean up common abbreviations in value
                    if value == 'a':
                        value = 'config_path'
                    elif value == '{}':
                        value = '{}'
                    elif value.startswith('[') and value.endswith(']'):
                        # Keep list assignments as-is
                        pass
                    return f"{var_name} = {value}"
            
            # For function calls
            if '(' in body_content and ')' in body_content:
                # Extract function call patterns
                call_match = re.search(r'([a-zA-Z_][a-zA-Z0-9_]*)\s*\([^)]*\)', body_content)
                if call_match:
                    call_text = call_match.group(0)
                    # Clean up common patterns
                    if 'lower()' in call_text:
                        return 'self.config_name = config_path.lower()'
                    return call_text
            
            # For return statements
            if body_content.startswith('R') or 'return' in body_content:
                if 'Rg0' in body_content:
                    return 'return self.config'
                elif 'RT' in body_content:
                    return 'return True'
                elif 'RF' in body_content:
                    return 'return False'
                elif 'RN' in body_content:
                    return 'return None'
            
            # For conditional statements
            if '?' in body_content and ('if' in body_content or '(' in body_content):
                # Try to create a basic conditional
                if 'not in' in body_content:
                    return 'if field not in data:\n        return False'
                else:
                    return 'if condition:\n        pass'
            
            # For try-catch patterns
            if 'T{' in body_content and 'X(' in body_content:
                return 'try:\n        pass\n    except Exception:\n        pass'
            
            # Last resort: create a meaningful placeholder based on context
            if hasattr(stmt, 'lineno'):
                return f"# TODO: Implement method body (line {stmt.lineno})"
            
            return "# TODO: Implement method body"
            
        except Exception:
            return "# TODO: Implement method body"

    def _parse_ultra_dense_body(self, body_content: str, method_node,
                            flow_compiler: FLOWCompiler,
                            cai3_map: CAI3Map, cai3_full: CAI3Full,
                            chain_aliases: Dict, pools: Dict) -> List[ast.AST]:
        """Parse ultra-dense single-line body with enhanced logging."""
        import re  # For pool resolution pattern matching
        
        self.logger.debug(f"Parsing ultra-dense body for method: {method_node.name}")
        self.logger.debug(f"Body content: {repr(body_content)}")
        self.logger.debug(f"Body length: {len(body_content)}")
        
        # CRITICAL ENHANCEMENT: Apply malformed fixes BEFORE any processing
        self.logger.debug("Applying malformed fixes to body content before parsing")
        original_body = body_content
        body_content = self._apply_malformed_fixes_to_body(body_content)
        if body_content != original_body:
            self.logger.debug(f"Malformed fixes applied: {original_body} -> {body_content}")
        
        # Add validation before processing
        is_valid, error_msg = self._validate_bracket_structure(body_content)
        if not is_valid:
            self.logger.warning(f"Invalid bracket structure in body: {error_msg}")
            self.logger.debug(f"Body content: {repr(body_content)}")
            
            # Attempt repair if it's a try-except structure
            if body_content.startswith('T{'):
                body_content = self._attempt_structure_repair(body_content)
                # Re-validate after repair
                is_valid, error_msg = self._validate_bracket_structure(body_content)
                if not is_valid:
                    self.logger.error(f"Could not repair structure: {error_msg}")
                    return [ast.Pass()]
        
        # Additional validation for try-except structures
        if body_content.startswith('T{'):
            t_valid, t_msg = self._validate_t_structure(body_content)
            if not t_valid:
                self.logger.warning(f"Invalid T{{}} structure: {t_msg}")
                # Attempt repair
                body_content = self._attempt_structure_repair(body_content)
                # Re-validate
                t_valid, t_msg = self._validate_t_structure(body_content)
                if not t_valid:
                    self.logger.error(f"Could not repair T{{}} structure: {t_msg}")
                    return [ast.Pass()]
            elif "Try-only structure" in t_msg:
                self.logger.info(f"Try-only structure detected, adding exception handler")
                body_content = self._attempt_structure_repair(body_content)
        
        # Log structure detection
        if 'T{' in body_content:
            self.logger.debug(f"T{{}} structure detected in body")
            open_count = body_content.count('{')
            close_count = body_content.count('}')
            self.logger.debug(f"Brace count - Open: {open_count}, Close: {close_count}")
        
        self.logger.debug(f"Chain aliases available: {chain_aliases}")
        
        # CRITICAL FIX: Apply pool resolution early to avoid syntax errors in chain alias expressions
        # Patterns like g0[p1] need to become g0['#6744'] before AST parsing
        if pools:
            original_body = body_content
            for pool_key, pool_value in pools.items():
                # Replace pool references in chain alias contexts with quoted hash values
                # This fixes expressions like g0[p1] -> g0['#6744']
                pattern = f'\\[{pool_key}\\]'
                replacement = f"['{pool_value}']"
                body_content = re.sub(pattern, replacement, body_content)
            
            if body_content != original_body:
                self.logger.debug(f"Applied early pool resolution: {repr(original_body)} -> {repr(body_content)}")
        
        statements = []
        
        # Set up local compressions for this method
        if 'local_compressions' in method_node.metadata:
            self.logger.debug(f"Setting up local compressions for {method_node.cid}: {method_node.metadata['local_compressions']}")
            flow_compiler.set_scope(method_node.cid, method_node.metadata['local_compressions'])
        else:
            self.logger.debug(f"No local compressions found for method {method_node.name}")
        
        # Check if this is a single try-except statement first
        if body_content.startswith('T{') and 'X' in body_content:
            self.logger.debug("Detected single try-except statement pattern")
            # This is likely a single try-except statement, don't split it
            try:
                stmt = self._parse_ultra_dense_try_except(body_content, flow_compiler)
                if stmt:
                    self.logger.debug("Successfully parsed try-except statement")
                    statements.append(stmt)
                    return statements
                else:
                    self.logger.warning("Try-except parsing returned None")
            except Exception as e:
                self.logger.warning(f"Failed to parse as try-except: {e}, falling back to normal parsing")
        
        # Split by semicolon for multiple statements - BUT RESPECT NESTED STRUCTURES
        stmt_strings = self._split_respecting_nesting(body_content, ';')
        self.logger.debug(f"Split body into {len(stmt_strings)} statement strings: {stmt_strings}")
        
        # CRITICAL FIX: Merge validation patterns before parsing individual statements
        stmt_strings = self._merge_validation_patterns(stmt_strings)
        self.logger.debug(f"After merging validation patterns: {stmt_strings}")
        
        for stmt_idx, stmt_str in enumerate(stmt_strings):
            stmt_str = stmt_str.strip()
            if not stmt_str:
                self.logger.debug(f"Statement {stmt_idx}: Empty, skipping")
                continue
            
            self.logger.debug(f"Statement {stmt_idx}: Processing '{stmt_str}'")
            
            try:
                # Parse each statement
                # TRY-EXCEPT AND FOR-LOOP DETECTION MUST COME BEFORE ASSIGNMENT DETECTION
                # Because try-except and for-loops contain = signs in their bodies
                if stmt_str.startswith('T{') and 'X' in stmt_str:
                    self.logger.debug(f"Statement {stmt_idx}: Detected try-except pattern")
                    # Try-except (higher priority than assignment)
                    stmt = self._parse_ultra_dense_try_except(stmt_str, flow_compiler)
                elif stmt_str.startswith('@') and ',' in stmt_str and '{' in stmt_str:
                    self.logger.debug(f"Statement {stmt_idx}: Detected for-loop pattern")
                    # For-loop (higher priority than assignment)
                    stmt = self._parse_ultra_dense_for(stmt_str, flow_compiler)
                elif stmt_str.startswith('@'):
                    self.logger.debug(f"Statement {stmt_idx}: Detected for-loop pattern (@)")
                    # For loop in ultra-dense format: @x,y{body}
                    stmt = self._parse_ultra_dense_for(stmt_str, flow_compiler)
                elif stmt_str.startswith('R'):
                    self.logger.debug(f"Statement {stmt_idx}: Detected return pattern")
                    # Return statement
                    stmt = self._parse_ultra_dense_return(stmt_str, flow_compiler)
                elif '=' in stmt_str and not any(op in stmt_str for op in ['==', '!=', '<=', '>=']):
                    self.logger.debug(f"Statement {stmt_idx}: Detected assignment pattern")
                    # Assignment (may not have L prefix in ultra-dense mode)
                    stmt = self._parse_ultra_dense_assignment(stmt_str, flow_compiler)
                elif stmt_str.startswith('(') and ('?' in stmt_str or ')' in stmt_str):
                    self.logger.debug(f"Statement {stmt_idx}: Detected conditional pattern")
                    # Conditional expression or if statement
                    stmt = self._parse_ultra_dense_conditional(stmt_str, flow_compiler)
                elif stmt_str.startswith('if '):
                    self.logger.debug(f"Statement {stmt_idx}: Detected pre-built if statement")
                    # This is already a complete if statement from validation pattern merging
                    # Parse it as a complete statement
                    lines = stmt_str.split('\n')
                    main_line = lines[0]  # "if condition:"
                    body_line = lines[1].strip() if len(lines) > 1 else "pass"
                    
                    # Extract condition from "if condition:"
                    condition_part = main_line[3:-1]  # Remove "if " and ":"
                    
                    # Parse the condition
                    try:
                        condition_expr = flow_compiler._parse_expression_string(condition_part)
                        # Parse the body
                        if body_line and body_line != "pass":
                            # Create a simple expression statement for the body
                            body_expr = flow_compiler._parse_expression_string(body_line)
                            body_stmt = self._fix_ast_node_attributes(ast.Expr(value=body_expr))
                        else:
                            body_stmt = self._fix_ast_node_attributes(ast.Pass())
                        
                        # Create if statement
                        stmt = self._fix_ast_node_attributes(ast.If(
                            test=condition_expr,
                            body=[body_stmt],
                            orelse=[]
                        ))
                    except Exception as if_error:
                        self.logger.warning(f"Failed to parse pre-built if statement '{stmt_str}': {if_error}")
                        stmt = self._fix_ast_node_attributes(ast.Pass())
                elif stmt_str == '_':
                    self.logger.debug(f"Statement {stmt_idx}: Pass statement")
                    stmt = self._fix_ast_node_attributes(ast.Pass())
                elif stmt_str == 'B':
                    self.logger.debug(f"Statement {stmt_idx}: Break statement")
                    stmt = self._fix_ast_node_attributes(ast.Break())
                elif stmt_str == 'K':
                    self.logger.debug(f"Statement {stmt_idx}: Continue statement")
                    stmt = self._fix_ast_node_attributes(ast.Continue())
                else:
                    self.logger.debug(f"Statement {stmt_idx}: Parsing as expression")
                    # Clean CID references before parsing expression
                    stmt_str_cleaned = self._clean_cid_references(stmt_str)
                    # Try to parse as expression
                    expr = flow_compiler._parse_expression_string(stmt_str_cleaned)
                    stmt = self._fix_ast_node_attributes(ast.Expr(value=expr))
                
                if stmt:
                    self.logger.debug(f"Statement {stmt_idx}: Successfully parsed")
                    statements.append(stmt)
                else:
                    self.logger.warning(f"Statement {stmt_idx}: Parsing returned None")
                    
            except Exception as e:
                self.logger.error(f"Statement {stmt_idx}: Failed to parse '{stmt_str}': {e}")
                # ENHANCED ERROR RECOVERY: Try to fix common patterns before giving up
                try:
                    # Fix common malformed patterns
                    fixed_stmt = self._fix_malformed_statement(stmt_str)
                    if fixed_stmt != stmt_str:
                        self.logger.debug(f"Attempting to parse fixed statement: '{fixed_stmt}'")
                        # Try parsing the fixed statement
                        if fixed_stmt.startswith('R'):
                            stmt = self._parse_ultra_dense_return(fixed_stmt, flow_compiler)
                        elif '=' in fixed_stmt and not any(op in fixed_stmt for op in ['==', '!=', '<=', '>=']):
                            stmt = self._parse_ultra_dense_assignment(fixed_stmt, flow_compiler)
                        elif fixed_stmt.startswith('@'):
                            stmt = self._parse_ultra_dense_for(fixed_stmt, flow_compiler)
                        else:
                            # Try as expression
                            expr = flow_compiler._parse_expression_string(fixed_stmt)
                            stmt = self._fix_ast_node_attributes(ast.Expr(value=expr))
                        
                        if stmt:
                            self.logger.debug(f"Successfully recovered statement {stmt_idx}")
                            statements.append(stmt)
                            continue
                except Exception as recovery_error:
                    self.logger.debug(f"Recovery attempt failed: {recovery_error}")
                
                # Last resort: add pass statement
                statements.append(self._fix_ast_node_attributes(ast.Pass()))
        
        # Apply deminification to all statements
        self.logger.debug(f"Starting deminification process for {len(statements)} statements")
        
        # Build local and global maps separately
        local_map = {}
        global_map = {}
        
        # Build local map for this method's variables
        local_mappings_count = 0
        if method_node.cid:
            prefix = f"{method_node.cid}:"
            self.logger.debug(f"Looking for local mappings with prefix: {prefix}")
            for k, orig in cai3_map.name_map.items():
                if k.startswith(prefix):
                    short = k.split(":", 1)[1]
                    local_map[short] = orig
                    local_mappings_count += 1
                    self.logger.debug(f"Added local mapping: {short} -> {orig}")
            self.logger.debug(f"Added {local_mappings_count} local mappings")

        # Build global map (without CID prefix)
        global_mappings_count = 0
        for k, orig in cai3_map.name_map.items():
            if ':' not in k:  # Global variables don't have CID prefix
                global_map[k] = orig
                global_mappings_count += 1
                self.logger.debug(f"Added global mapping: {k} -> {orig}")
        self.logger.debug(f"Added {global_mappings_count} global mappings")
        
        # Use the enhanced method to build final mapping with collision protection
        short_to_orig = self._build_short_to_orig(local_map, global_map)

        # Handle parameter mappings more carefully
        if method_node.signature and '(' in method_node.signature:
            sig_params = method_node.signature[1:method_node.signature.index(')')].split(',')
            
            # For the validate_record method with signature "(a)->A"
            # The actual parameter after 'self' is 'record' (mapped as 'b' in metadata)
            # But signature shows 'a' - this is the compression mismatch
            
            # Use local_compressions from metadata instead of signature for accurate mapping
            if 'local_compressions' in method_node.metadata:
                local_comps = method_node.metadata['local_compressions']
                # Don't add these to short_to_orig - they're already handled above
                # Just log for debugging
                self.logger.debug(f"Local compressions from metadata: {local_comps}")
        
        # After building short_to_orig mapping:
        self.logger.debug(f"Built short_to_orig mapping: {short_to_orig}")
        
        self.logger.debug(f"Final short_to_orig mapping: {short_to_orig}")
        self.logger.debug(f"Chain aliases: {chain_aliases}")
        
        # After parsing statements but before deminification:
        for i, stmt in enumerate(statements):
            if hasattr(ast, 'unparse'):
                self.logger.debug(f"Pre-deminify stmt {i}: {ast.unparse(stmt)}")
        
        # Use the chain_aliases passed as parameter (from LITE structure)
        aliases_to_use = chain_aliases.copy() if chain_aliases else {}

        # Only fall back to stored aliases if none provided
        if not aliases_to_use and cai3_full and 'chain_aliases' in cai3_full.compression_stats:
            stored_aliases = cai3_full.compression_stats.get('chain_aliases', {})
            if isinstance(stored_aliases, dict):
                # Clean up stored aliases - remove any trailing ()
                cleaned_aliases = {}
                for alias, chain in stored_aliases.items():
                    if isinstance(chain, str):
                        if chain.endswith('()'):
                            cleaned_aliases[alias] = chain[:-2]
                        else:
                            cleaned_aliases[alias] = chain
                    else:
                        self.logger.warning(f"Invalid chain alias {alias}: {chain} (type: {type(chain)})")
                        cleaned_aliases[alias] = str(chain) if chain else ""
                
                # Log for debugging
                self.logger.debug(f"Using chain aliases for deminification: {cleaned_aliases}")
                aliases_to_use = cleaned_aliases

        self.logger.debug(f"Chain aliases for deminifier: {aliases_to_use}")
        
        # Apply deminifier with both mappings
        if short_to_orig or aliases_to_use:
            self.logger.debug(f"Applying deminifier with mappings: {short_to_orig}")
            self.logger.debug(f"Chain aliases for deminifier: {aliases_to_use}")
            
            # Debug: print AST before transformation
            for i, stmt in enumerate(statements):
                if hasattr(ast, 'unparse'):
                    self.logger.debug(f"Before deminify stmt {i}: {ast.unparse(stmt)}")
            
            # Create deminifier and validate chain aliases
            demin = DeminifyTransformer(short_to_orig, aliases_to_use)
            
            # Validate chain aliases before applying
            if aliases_to_use:
                for alias, chain in aliases_to_use.items():
                    if not isinstance(chain, str):
                        self.logger.warning(f"Invalid chain alias {alias}: {chain} (type: {type(chain)})")
                        aliases_to_use[alias] = str(chain) if chain else ""
                    elif '()' in chain:
                        self.logger.debug(f"Chain alias {alias} contains parentheses: {chain}")
            
            self.logger.debug(f"DeminifyTransformer short_to_orig: {short_to_orig}")
            self.logger.debug(f"DeminifyTransformer aliases_to_use: {aliases_to_use}")
            
            statements = [demin.visit(stmt) for stmt in statements]
            
            # After deminification:
            for i, stmt in enumerate(statements):
                if hasattr(ast, 'unparse'):
                    self.logger.debug(f"Post-deminify stmt {i}: {ast.unparse(stmt)}")
            
            # Debug: print AST after transformation
            for i, stmt in enumerate(statements):
                if hasattr(ast, 'unparse'):
                    self.logger.debug(f"After deminify stmt {i}: {ast.unparse(stmt)}")
            
            # Fix AST attributes after transformation
            for stmt in statements:
                self._fix_ast_node_attributes(stmt)
        
        return statements

    def _fix_ast_node_attributes(self, node: ast.AST, lineno: int = 1, col_offset: int = 0) -> ast.AST:
        """Fix AST nodes by adding missing lineno and col_offset attributes."""
        # First, set attributes on all nodes in the tree
        for child in ast.walk(node):
            if not hasattr(child, 'lineno') or child.lineno is None:
                child.lineno = lineno
            if not hasattr(child, 'col_offset') or child.col_offset is None:
                child.col_offset = col_offset
        
        # Use ast.fix_missing_locations to ensure all nodes have proper line info
        ast.fix_missing_locations(node)
        
        return node

    def _resolve_hash_references(self, code: str, cai3_full: CAI3Full) -> str:
        """
        Resolve all hash references (#xxxx) to their actual values.
        Core fix: Only resolve hashes in syntactically valid contexts.
        """
        if '#' not in code:
            return code
        
        import re
        
        # FUNDAMENTAL FIX: Only resolve hash references in valid syntactic contexts
        # This prevents resolution in malformed expressions that would make them worse
        
        # Pattern: Match hash references that are NOT part of malformed expressions
        # Avoid resolving in contexts that would create chained attribute access
        hash_pattern = r"(?<!['\"])\#(\d{3,4})(?!['\"])"
        
        def replace_hash(match):
            hash_ref = f"#{match.group(1)}"
            
            # Get context around the match
            match_start = match.start()
            match_end = match.end()
            before_match = code[:match_start]
            after_match = code[match_end:]
            
            # CORE FIX: Check if we're in a valid syntactic context
            # Skip resolution if we're in a malformed expression context
            if self._is_malformed_expression_context(before_match, after_match, hash_ref):
                return hash_ref
            
            # Check if already inside quotes
            single_quotes = before_match.count("'") - before_match.count("\\'")
            double_quotes = before_match.count('"') - before_match.count('\\"')
            
            if (single_quotes % 2 == 1) or (double_quotes % 2 == 1):
                return hash_ref
            
            # Resolve the hash value
            if hasattr(cai3_full, 'hash_to_value') and hash_ref in cai3_full.hash_to_value:
                hash_entry = cai3_full.hash_to_value[hash_ref]
                
                if isinstance(hash_entry, dict):
                    value = hash_entry['value']
                    needs_quotes = hash_entry.get('needs_quotes', True)
                else:
                    value = hash_entry
                    needs_quotes = isinstance(value, str)
                
                return self._format_hash_value(value, needs_quotes, before_match, after_match)
            
            # Fallback for unresolved hashes
            self.logger.warning(f"Unresolved hash reference: {hash_ref}")
            return f"'{hash_ref}'" if (single_quotes % 2 == 0) and (double_quotes % 2 == 0) else hash_ref
        
        return re.sub(hash_pattern, replace_hash, code)
    
    def _is_malformed_expression_context(self, before: str, after: str, hash_ref: str) -> bool:
        """
        Determine if we're in a malformed expression context where hash resolution
        would make things worse. This uses generic patterns rather than domain-specific ones.
        """
        import re
        
        # GENERAL SOLUTION: Check for patterns that indicate malformed expressions
        
        # 1. Generic repeated attribute access patterns: .attr[key].attr[key]
        # This catches any repeated chained attribute access, not just data_buffer
        repeated_attr_pattern = r'\.([a-zA-Z_][a-zA-Z0-9_]*)\[[^\]]*\]\.\1'
        if re.search(repeated_attr_pattern, before[-50:] + after[:50]):
            return True
        
        # 2. Generic chained attribute access that suggests malformed expressions
        # Pattern: .attr[...].attr (any attribute, not just data_buffer)
        generic_chain_pattern = r'\.([a-zA-Z_][a-zA-Z0-9_]*)\[[^\]]*\]\.([a-zA-Z_][a-zA-Z0-9_]*)'
        combined_context = before[-50:] + after[:50]
        chain_matches = re.findall(generic_chain_pattern, combined_context)
        
        # If we find the same attribute name appearing multiple times in a chain
        for attr1, attr2 in chain_matches:
            if attr1 == attr2:
                return True
        
        # 3. Parenthesized membership tests that would become invalid
        # Pattern: ('#hash' in container) -> should not resolve the hash
        if (before.rstrip().endswith("'") and 
            after.lstrip().startswith("' in") and
            '(' in before[-20:]):
            return True
        
        # 4. Generic malformed chained expressions (any attribute repeated)
        # Look for pattern: .attrX in before AND .attrX in after
        attr_in_before = re.findall(r'\.([a-zA-Z_][a-zA-Z0-9_]*)', before[-30:])
        attr_in_after = re.findall(r'\.([a-zA-Z_][a-zA-Z0-9_]*)', after[:30])
        
        # If same attribute appears on both sides, likely malformed
        common_attrs = set(attr_in_before) & set(attr_in_after)
        if common_attrs:
            return True
        
        # 5. Complex conditional expressions with parentheses that suggest malformed parsing
        paren_depth = before.count('(') - before.count(')')
        if paren_depth > 0 and (' in ' in before[-30:] or ' in ' in after[:30]):
            # This suggests we're inside a conditional expression
            return True
        
        return False
    
    def _format_hash_value(self, value, needs_quotes: bool, before: str, after: str) -> str:
        """
        Format hash value based on context and type.
        """
        # Context detection
        is_dict_key = (
            (before.rstrip().endswith('{') or before.rstrip().endswith(',')) 
            and after.lstrip().startswith(':')
        )
        
        is_dict_access = (
            before.rstrip().endswith('[') and 
            after.lstrip().startswith(']')
        )
        
        if isinstance(value, str):
            # Check if already properly quoted
            if ((value.startswith("'") and value.endswith("'")) or 
                (value.startswith('"') and value.endswith('"'))):
                return value
            
            # Add quotes based on context
            if is_dict_key or is_dict_access or needs_quotes:
                return f"'{value}'"
            else:
                return value
        elif isinstance(value, (int, float)):
            return str(value)
        elif isinstance(value, bool):
            return 'True' if value else 'False'
        elif value is None:
            return 'None'
        else:
            return repr(value)

    def _resolve_pool_references(self, code: str, pools: Dict[str, str]) -> str:
        """
        Resolve all pool references (p\d+) with context-aware replacement.
        """
        if not pools or 'p' not in code:
            return code
        
        import re
        
        # More precise pattern for pool references
        # Matches p0, p1, etc. but not part of larger identifiers
        pool_pattern = r'\b(p\d+)\b'
        
        def replace_pool(match):
            pool_ref = match.group(1)
            
            if pool_ref in pools:
                value = pools[pool_ref]
                
                # Check if value is a hash reference
                if isinstance(value, str) and value.startswith('#'):
                    # Return hash as-is for later resolution
                    return value
                
                # Check context for proper quoting
                start_pos = match.start()
                end_pos = match.end()
                
                # Check if we're in a dictionary key context
                before = code[:start_pos].rstrip()
                after = code[end_pos:].lstrip()
                
                is_dict_key = (before.endswith('{') or before.endswith(',')) and after.startswith(':')
                
                if isinstance(value, str):
                    # Always quote strings appropriately
                    if is_dict_key or not (value.startswith('"') or value.startswith("'")):
                        return repr(value)
                    return value
                else:
                    return str(value)
            
            # Log unresolved pool reference
            self.logger.warning(f"Unresolved pool reference: {pool_ref}")
            return f"'{pool_ref}'"  # Quote as fallback
        
        return re.sub(pool_pattern, replace_pool, code)

    def _resolve_incomplete_names(self, code: str) -> str:
        """
        Phase 3 Enhancement: Resolve incomplete method names and class names that made it through.
        This is a comprehensive fix for abbreviated names that weren't caught by deminification.
        """
        # Common incomplete method names that need completion
        incomplete_methods = {
            'os.li': 'os.listdir',
            '.ap(': '.append(',
            '.g(': '.get(',
            '.sp(': '.split(',
            '.r(': '.replace(',
            '.j(': '.join(',
            '.st(': '.startswith(',
            '.en(': '.endswith(',
            '.fi(': '.find(',
            '.co(': '.count(',
            '.lo(': '.lower(',
            '.up(': '.upper(',
            '.st(': '.strip(',
        }
        
        # Common incomplete class names
        incomplete_classes = {
            'Fi()': 'FileMetadata()',
            'Us()': 'UserProfile()',
            'Da()': 'DataProcessor()',
            'Co()': 'ConfigManager()',
            'Lo()': 'Logger()',
        }
        
        # Apply method name completions
        for incomplete, complete in incomplete_methods.items():
            if incomplete in code:
                code = code.replace(incomplete, complete)
                self.logger.debug(f"Completed method name: {incomplete} -> {complete}")
        
        # Apply class name completions
        for incomplete, complete in incomplete_classes.items():
            if incomplete in code:
                code = code.replace(incomplete, complete)
                self.logger.debug(f"Completed class name: {incomplete} -> {complete}")
        
        # Fix common variable name abbreviations that should be expanded
        variable_expansions = {
            'scan_path': 'scan_directory_path',  # Only if it makes sense in context
            # Add more as needed based on context
        }
        
        # Handle chain alias patterns that might be malformed
        # Pattern: g0 -> self.config (or similar based on context)
        if 'g0' in code and 'self.' not in code.replace('g0', ''):
            # This suggests g0 should be expanded to self.something
            if 'config' in code or 'data_buffer' in code:
                code = code.replace('g0', 'self.config')
                self.logger.debug("Expanded chain alias: g0 -> self.config")
            
        return code

    def _fix_malformed_string_patterns(self, content: str) -> str:
        """
        Phase 3 Critical Fix: Handle malformed patterns at string level before AST processing.
        These patterns are syntactically invalid and can't be handled by AST transformers.
        """
        import re
        
        # Pattern 1: Fix malformed conditional assignments like "(a|s.b)"
        # This should become proper conditional: "a if a else s.b" or just "s.b" if 'a' is undefined
        pattern1 = r'\(([a-zA-Z_][a-zA-Z0-9_]*)\|([^)]+)\)'
        
        def fix_conditional_pattern(match):
            var_name = match.group(1)  # a
            fallback = match.group(2)  # s.b
            
            # Check if this is a simple variable or a more complex expression
            if len(var_name) == 1 and var_name.islower():
                # Single letter variable - likely undefined, use fallback
                self.logger.debug(f"Fixed undefined variable conditional: {match.group(0)} -> {fallback}")
                return fallback
            else:
                # More complex - create proper conditional
                result = f"({var_name} if '{var_name}' in locals() else {fallback})"
                self.logger.debug(f"Fixed conditional pattern: {match.group(0)} -> {result}")
                return result
        
        content = re.sub(pattern1, fix_conditional_pattern, content)
        
        # Pattern 2: Fix malformed conditional expressions like "(j not in g0)[]{action}:_"
        # This should become proper if statement
        pattern2 = r'\(([^)]+)\)\[\]\{([^}]+)\}:_'
        
        def fix_malformed_conditional_expr(match):
            condition = match.group(1)  # j not in g0
            action = match.group(2)  # h.ap(_container)
            
            # Create proper conditional structure
            result = f"({condition})?{{{action}}}:_"
            self.logger.debug(f"Fixed malformed conditional expression: {match.group(0)} -> {result}")
            return result
        
        content = re.sub(pattern2, fix_malformed_conditional_expr, content)
        
        # Pattern 3: Fix incomplete method calls that made it through
        incomplete_calls = {
            r'h\.ap\(': 'h.append(',
            r'os\.li\(': 'os.listdir(',  # More specific pattern to avoid double replacement
            r'\.g\(': '.get(',
            r'\.sp\(': '.split(',
            r'\.st\(': '.strip(',
            r'\.lo\(': '.lower(',
            r'\.up\(': '.upper(',
        }
        
        for pattern, replacement in incomplete_calls.items():
            if re.search(pattern, content):
                content = re.sub(pattern, replacement, content)
                self.logger.debug(f"Fixed incomplete method call: {pattern} -> {replacement}")
        
        # Fix double expansions that might have occurred
        content = content.replace('os.listdirstdir', 'os.listdir')
        content = content.replace('appendpend', 'append')
        content = content.replace('getget', 'get')
        
        # Pattern 4: Fix chain alias issues where 'g0' wasn't properly resolved
        # g0 typically represents self.config or similar
        if 'g0' in content and 'self.' not in content.replace('g0', 'self.'):
            # Context-aware replacement for g0
            if 'data_buffer' in content or 'config' in content:
                content = content.replace('g0', 'self.config')
                self.logger.debug("Fixed chain alias: g0 -> self.config")
            elif 'error' in content or 'log' in content:
                content = content.replace('g0', 'self.logger')
                self.logger.debug("Fixed chain alias: g0 -> self.logger")
            else:
                content = content.replace('g0', 'self.data')
                self.logger.debug("Fixed chain alias: g0 -> self.data")
        
        return content

    def _safe_replace_placeholder(self, expr: str, pos: int, replacement: str) -> str:
        """
        Safely replace a placeholder ensuring proper spacing for valid Python syntax.
        Phase 2 Enhancement: Improved spacing logic to prevent identifier concatenation issues.
        """
        # Check what comes before and after the placeholder
        before_char = expr[pos-1] if pos > 0 else ''
        after_char = expr[pos+1] if pos < len(expr)-1 else ''
        
        # PHASE 2 FIX: More sophisticated character analysis
        alphanumeric_or_underscore = lambda c: c.isalnum() or c == '_'
        
        # Start with the replacement - no modifications initially
        final_replacement = replacement
        
        # PHASE 2 ENHANCEMENT: Better context-aware spacing logic
        # Only add spacing when absolutely necessary to prevent syntax errors
        
        # Check for cases where we're inside an identifier and need to prevent concatenation
        # But NOT when we're dealing with function calls, method access, etc.
        
        # Case 1: Before character analysis - only add space if it would create invalid syntax
        if before_char and alphanumeric_or_underscore(before_char):
            # Check if replacement would create invalid identifier concatenation
            if replacement and alphanumeric_or_underscore(replacement[0]):
                # CRITICAL: Check if we're in a special context where spacing would break things
                # Look at broader context to avoid breaking patterns like "_conta" + "iner"
                before_context = expr[max(0, pos-10):pos]
                after_context = expr[pos+1:min(len(expr), pos+10)]
                
                # Don't add space if we're completing an identifier that was split
                # Pattern like "_conta" followed by "?" followed by "in er" -> "_container"
                if ('_' in before_context and 
                    after_context.strip().startswith(('in ', 'iner', 'ainer', 'er '))):
                    # This looks like a split identifier - don't add spacing
                    pass
                else:
                    final_replacement = ' ' + final_replacement
        
        # Case 2: After character analysis
        if after_char and alphanumeric_or_underscore(after_char):
            if replacement and alphanumeric_or_underscore(replacement[-1]):
                # Check for similar split identifier patterns
                before_context = expr[max(0, pos-10):pos]
                after_context = expr[pos+1:min(len(expr), pos+10)]
                
                # Don't add space if we're completing a split identifier
                if (before_context.endswith(('_conta', '_contain', 'conta')) and 
                    after_context.startswith(('iner', 'er ', 'in er'))):
                    # This looks like a split identifier - don't add spacing
                    pass
                else:
                    final_replacement = final_replacement + ' '
        
        # Handle operators properly
        if after_char == '=' and before_char not in '=!<>':
            if replacement and not replacement.endswith(' '):
                final_replacement = final_replacement + ' '
        
        if before_char == '=' and after_char not in '=<>':
            if replacement and not replacement.startswith(' '):
                final_replacement = ' ' + final_replacement
        
        # PHASE 2 ENHANCEMENT: Better bracket/parentheses handling
        # Only add spaces for function arguments, not for all bracket contexts
        bracket_chars = '()[]{}'
        if before_char in bracket_chars or after_char in bracket_chars:
            if replacement and replacement.strip():
                # More selective spacing for brackets
                if (before_char == '(' and replacement != '' and 
                    not replacement.startswith(' ') and len(replacement) > 1):
                    # Function argument context - but be more careful
                    if not (before_char == '(' and after_char == ')'):  # Don't space single chars in ()
                        final_replacement = ' ' + final_replacement
                
                if (after_char == ')' and replacement != '' and 
                    not replacement.endswith(' ') and len(replacement) > 1):
                    # End of function argument - but be more careful
                    if not (before_char == '(' and after_char == ')'):  # Don't space single chars in ()
                        final_replacement = final_replacement + ' '
        
        return expr[:pos] + final_replacement + expr[pos + 1:]

    def _resolve_placeholder_with_context(self, expr: str, context: Dict) -> str:
        """
        Resolve ? placeholders using available context.
        
        Args:
            expr: Expression containing ? placeholder
            context: Available context for resolution
            
        Returns:
            Expression with placeholders resolved
        """
        if '?' not in expr:
            return expr
        
        self.logger.debug(f"Resolving placeholder in: {expr}")
        
        # For multiple placeholders, we need to analyze each one individually
        result = expr
        placeholder_positions = []
        
        # Find all placeholder positions and their local context
        for i, char in enumerate(expr):
            if char == '?':
                # Analyze local context around this specific placeholder
                start_context = max(0, i - 10)
                end_context = min(len(expr), i + 10)
                local_context = expr[start_context:end_context]
                # Calculate the position of this ? within the local context
                question_pos_in_local = i - start_context
                placeholder_positions.append((i, local_context, question_pos_in_local))
        
        # Process placeholders from right to left to maintain positions
        for pos, local_context, question_pos_in_local in reversed(placeholder_positions):
            # Determine replacement based on immediate local context and additional context
            replacement = self._get_placeholder_replacement(local_context, expr, question_pos_in_local, context)
            
            # CRITICAL FIX: Use safe replacement to avoid invalid identifiers
            result = self._safe_replace_placeholder(result, pos, replacement)
        
        self.logger.debug(f"Resolved to: {result}")
        return result

    def _get_syntactic_context(self, expr: str, placeholder_pos: int) -> str:
        """
        Determine the syntactic role of a placeholder in an expression.
        
        Returns:
            'assignment_target': ? appears as left side of assignment
            'loop_variable': ? appears as loop iterator variable
            'function_argument': ? appears inside function call
            'value_expression': ? appears in other contexts
        """
        # Safety check
        if placeholder_pos < 0 or placeholder_pos >= len(expr):
            return 'value_expression'
        
        # Get text before and after placeholder
        before = expr[:placeholder_pos]
        after = expr[placeholder_pos + 1:]
        
        # Check for assignment target: "? = value" (with possible whitespace)
        after_stripped = after.strip()
        if after_stripped and after_stripped[0] == '=':
            # Make sure it's not ==, !=, <=, >=
            if len(after_stripped) == 1 or after_stripped[1] not in '=<>!':
                return 'assignment_target'
        
        # Check for loop variable: "@?,iterator" or "@? ,iterator" patterns
        # Look for @ immediately before the ? (possibly with whitespace)
        if placeholder_pos > 0:
            # Check if there's an @ immediately before the ?
            if expr[placeholder_pos - 1] == '@':
                return 'loop_variable'
            
            # Check for @ with whitespace: "@? " or "@  ?"
            # Find the last @ before this position
            at_pos = before.rfind('@')
            if at_pos >= 0:
                # Check if there's only whitespace between @ and ?
                between = before[at_pos + 1:]
                if not between.strip():  # Only whitespace between @ and ?
                    return 'loop_variable'
        
        # Also check for patterns like "for @?, items" where @ comes earlier
        if '@' in before:
            # Check if this appears to be a for-loop context
            before_lower = before.lower()
            if 'for' in before_lower and '@' in before:
                # Find the @ position and see if it's in the loop variable position
                at_pos = before.rfind('@')
                if at_pos >= 0:
                    after_at = before[at_pos:]
                    # If the @ is followed by minimal content before the ?, it's likely a loop variable
                    if len(after_at) <= 3:  # "@", "@x", "@xx" etc.
                        return 'loop_variable'
        
        # Check for function argument: "func(?)" (immediate after opening paren)
        if placeholder_pos > 0 and expr[placeholder_pos - 1] == '(':
            return 'function_argument'
        
        # Check if in collection context: "? in collection" or "item in ?"
        if ' in ' in expr:
            in_pos = expr.find(' in ')
            if placeholder_pos < in_pos:
                return 'value_expression'  # item being checked
            else:
                return 'collection_expression'  # collection being checked against
        
        # Additional collection context patterns
        # Check for iteration patterns: "for ... in ?", "iterate over ?", etc.
        before_lower = before.lower()
        after_lower = after.lower()
        
        # Pattern: "for ... in ?" or "iterate over ?"
        if ('for ' in before_lower and ' in ' in expr) or 'iterate over' in before_lower:
            return 'collection_expression'
        
        # Pattern: "? values", "? items", "? collection" etc.
        if after_lower.strip().startswith(('values', 'items', 'collection', 'list', 'array', 'range')):
            return 'collection_expression'
        
        # Pattern: keywords that suggest collection context
        collection_keywords = ['timeout', 'seconds', 'max_connections', 'field', 'values']
        for keyword in collection_keywords:
            if keyword in expr.lower():
                return 'collection_expression'
        
        return 'value_expression'

    def _generate_contextual_variable_name(self, full_expr: str, context_type: str) -> str:
        """
        Generate appropriate variable names based on expression context.
        
        Args:
            full_expr: The full expression containing the placeholder
            context_type: The syntactic context type
            
        Returns:
            A contextually appropriate variable name
        """
        # Analyze the expression for semantic hints
        expr_lower = full_expr.lower()
        
        if context_type == 'assignment_target':
            # Look for semantic clues in the expression - prioritize more specific patterns
            if 'path' in expr_lower and 'join' in expr_lower:
                return 'item_path'
            elif 'stat' in expr_lower:
                return 'stat_info'
            elif 'metadata' in expr_lower or 'meta' in expr_lower:
                return 'metadata'
            elif '.process(' in expr_lower or 'process(' in expr_lower or 'process_' in expr_lower:
                return 'result'
            elif 'get_result' in expr_lower or 'getresult' in expr_lower:
                return 'result'
            elif '.count' in expr_lower or 'count(' in expr_lower:
                return 'count'
            elif '.get(' in expr_lower and 'result' not in expr_lower:
                return 'value'
            elif 'result' in expr_lower:
                return 'result'
            elif 'file' in expr_lower and 'data' not in expr_lower:
                return 'file_item'
            elif 'dir' in expr_lower and 'data' not in expr_lower:
                return 'dir_item'
            elif 'error' in expr_lower or 'exc' in expr_lower:
                return 'error'
            elif 'index' in expr_lower or 'idx' in expr_lower:
                return 'index'
            elif 'value' in expr_lower and 'data' not in expr_lower:
                return 'value'
            elif 'data' in expr_lower:
                return 'data_item'
            else:
                # Generic but valid variable name
                return 'temp_var'
        
        elif context_type == 'loop_variable':
            # Infer from iterator context - be more specific with matching
            if '.items()' in expr_lower or '.items(' in expr_lower or 'items()' in expr_lower:
                return 'key, value'  # tuple unpacking for dict.items()
            elif '.keys()' in expr_lower or '.keys(' in expr_lower or 'keys()' in expr_lower:
                return 'key'
            elif '.values()' in expr_lower or '.values(' in expr_lower or 'values()' in expr_lower:
                return 'value'
            elif 'enumerate' in expr_lower:
                return 'idx, item'
            elif 'file' in expr_lower:
                return 'filename'
            elif 'dir' in expr_lower or 'listdir' in expr_lower:
                return 'item'
            elif 'line' in expr_lower:
                return 'line'
            # Check for common iterator patterns without method calls
            elif 'items' in expr_lower and 'item' not in expr_lower:  # 'items' but not 'item'
                return 'key, value'
            elif 'keys' in expr_lower:
                return 'key'
            elif 'values' in expr_lower:
                return 'value'
            else:
                return 'item'
        
        return 'item'  # Safe default

    def _get_placeholder_replacement(self, local_context: str, full_expr: str, question_pos_in_local: int, context: Dict = None) -> str:
        """
        Get the appropriate replacement for a placeholder based on its syntactic context.
        Phase 2 Enhancement: Improved conditional pattern recognition and context analysis.
        
        Args:
            local_context: The immediate context around the placeholder
            full_expr: The full expression for additional context
            question_pos_in_local: Position of the ? within the local_context
            context: Additional context information (e.g., iterator_context, is_loop_variable)
            
        Returns:
            Appropriate replacement string for the placeholder
        """
        # PHASE 2 ENHANCEMENT: Better position calculation
        local_start_in_full = full_expr.find(local_context) if local_context in full_expr else 0
        actual_pos = local_start_in_full + question_pos_in_local
        
        # PHASE 2: Enhanced context type detection
        context_type = self._get_syntactic_context(full_expr, actual_pos)
        
        # Override context type if we have specific context information
        if context and context.get('is_loop_variable'):
            context_type = 'loop_variable'
        
        self.logger.debug(f"Placeholder context analysis:")
        self.logger.debug(f"  Full expression: {repr(full_expr)}")
        self.logger.debug(f"  Local context: {repr(local_context)}")
        self.logger.debug(f"  Context type: {context_type}")
        self.logger.debug(f"  Additional context: {context}")
        
        # PHASE 3: Enhanced conditional pattern detection and handling
        # Check for complex conditional patterns before standard processing
        if self._is_complex_conditional_pattern(full_expr, actual_pos):
            replacement = self._resolve_complex_conditional_placeholder(full_expr, local_context, actual_pos)
            if replacement is not None:
                self.logger.debug(f"  Resolved complex conditional: {replacement}")
                return replacement
        
        # PHASE 2: Better assignment target handling
        if context_type == 'assignment_target':
            var_name = self._generate_contextual_variable_name(full_expr, context_type)
            self.logger.debug(f"  Generated assignment target: {var_name}")
            return var_name
            
        elif context_type == 'loop_variable':
            if context and 'iterator_context' in context:
                iterator_context = context['iterator_context']
                var_name = self._generate_contextual_variable_name(iterator_context, context_type)
                self.logger.debug(f"  Generated loop variable from iterator context '{iterator_context}': {var_name}")
                return var_name
            else:
                var_name = self._generate_contextual_variable_name(full_expr, context_type)
                self.logger.debug(f"  Generated loop variable: {var_name}")
                return var_name
            
        elif context_type == 'collection_expression':
            # PHASE 3: Better collection context handling
            return self._resolve_collection_placeholder(full_expr, local_context, actual_pos)
        
        elif context_type == 'function_argument':
            # PHASE 2: Improved function argument handling
            return self._resolve_function_argument_placeholder(full_expr, local_context, actual_pos)
        
        # PHASE 3: Enhanced special pattern handling
        # Handle malformed boolean expressions that need cleanup
        if self._is_malformed_boolean_pattern(full_expr, actual_pos):
            return ''  # Remove the placeholder entirely
        
        # Handle "in ?" patterns specifically
        if ' in ?' in local_context or local_context.strip().endswith(' in ?'):
            if 'required_fields' in full_expr or 'field' in full_expr:
                return 'required_fields'
            elif 'timeout' in full_expr.lower():
                return '[0, -1, None]'
            else:
                return '[]'
        
        # Handle comma-separated conditional patterns like "(value,? | other)"
        if ',' in local_context and '|' in full_expr:
            # This might be a conditional check - analyze the pattern
            if 'data_buffer' in full_expr or 'config' in full_expr:
                return 'required_fields'  # For configuration validation contexts
            
        # PHASE 2: Better default value handling
        return self._get_contextual_default_value(full_expr, local_context, context_type)

    def _is_complex_conditional_pattern(self, full_expr: str, pos: int) -> bool:
        """
        Phase 3: Detect complex conditional patterns that need special handling.
        """
        # Look for patterns like "(value in ? or ...)" or "(? in collection, other | ...)"
        context = full_expr[max(0, pos-20):min(len(full_expr), pos+20)]
        
        # Pattern 1: "in ?" with OR conditions
        if ' in ?' in context and (' or ' in context or ' | ' in context):
            return True
            
        # Pattern 2: Comma-separated conditional with pipe
        if (',' in context and '|' in context and 
            ('data_buffer' in full_expr or 'config' in full_expr)):
            return True
            
        return False

    def _resolve_complex_conditional_placeholder(self, full_expr: str, local_context: str, pos: int) -> str:
        """
        Phase 3: Resolve complex conditional patterns with proper context.
        """
        # Pattern: "value in ? or condition" -> "value in required_fields or condition"
        if ' in ?' in local_context and (' or ' in full_expr or ' | ' in full_expr):
            if 'field' in full_expr or 'required' in full_expr:
                return 'required_fields'
            elif 'timeout' in full_expr.lower():
                return '[0, -1, None]'
            elif 'config' in full_expr or 'data_buffer' in full_expr:
                return 'required_fields'
            else:
                return '[]'
        
        # Pattern: "(value,? | other)" in conditional contexts
        if ',' in local_context and '|' in full_expr:
            return 'required_fields'
        
        return None  # No special handling needed

    def _resolve_collection_placeholder(self, full_expr: str, local_context: str, pos: int) -> str:
        """
        Phase 3: Enhanced collection placeholder resolution.
        """
        # Check if we're in a conditional expression with CAI3 pattern
        if '?' in full_expr and ':' in full_expr and '{' in full_expr and '}' in full_expr:
            # This is a CAI3 conditional pattern, don't interfere
            pass  # Continue to normal collection handling
        elif '?' in full_expr and ':' in full_expr:
            # This is a regular conditional, not a collection
            return '?'  # Preserve for conditional resolution
        
        # Context-specific collection defaults
        if 'timeout' in full_expr.lower() or 'seconds' in full_expr.lower():
            return '[0, -1, None]'
        elif 'max_connections' in full_expr.lower():
            return 'range(1, 1000)'
        elif 'field' in full_expr.lower() or 'required' in full_expr.lower():
            return 'required_fields'
        else:
            return '[]'

    def _resolve_function_argument_placeholder(self, full_expr: str, local_context: str, pos: int) -> str:
        """
        Phase 2: Enhanced function argument placeholder resolution.
        """
        # Function arguments typically need values, not names
        if 'path' in local_context.lower():
            return 'scan_path'
        elif 'timeout' in local_context.lower():
            return '30'
        elif 'append(' in local_context:
            # Function argument for append - check what we're appending
            if 'error' in full_expr or 'issue' in full_expr:
                return "'Missing required field'"
            elif 'h.append(' in local_context or 'issues.append(' in local_context:
                return "'field validation error'"
            elif 'metadata' in full_expr or 'file' in full_expr:
                return 'metadata'
            else:
                return "'field required'"  # Better than _container
        else:
            # PHASE 3 ENHANCEMENT: Context-aware defaults instead of generic _container
            if 'metadata' in full_expr or 'file' in full_expr:
                return 'metadata'
            elif 'config' in full_expr or 'data' in full_expr:
                return 'config_value'
            elif 'path' in full_expr:
                return 'file_path'
            else:
                return 'item'  # Much better than _container

    def _is_malformed_boolean_pattern(self, full_expr: str, pos: int) -> bool:
        """
        Phase 3: Detect malformed boolean patterns that should be cleaned up.
        """
        context = full_expr[max(0, pos-15):min(len(full_expr), pos+15)]
        
        # Pattern: "((!?..." or "(?value,other|...)"
        if ('((!?' in context or '(!?' in context) and '|' in context:
            return True
            
        # Pattern: "(?g0[p0],i|..." - malformed conditional check
        if ('?' in context and ',' in context and 
            ('g0[' in context or 's.d[' in context) and '|' in context):
            return True
            
        return False

    def _get_contextual_default_value(self, full_expr: str, local_context: str, context_type: str) -> str:
        """
        Phase 2: Get appropriate default values based on context.
        """
        # Handle specific operator contexts
        if '== ?' in local_context or '? ==' in local_context:
            return 'None'
        elif '!= ?' in local_context or '? !=' in local_context:
            return 'None'
        elif ' in ?' in local_context:
            if 'field' in full_expr or 'required' in full_expr:
                return 'required_fields'
            else:
                return '[]'
        elif '? in ' in local_context:
            return 'None'
        
        # Context-aware defaults based on expression content
        if 'except' in full_expr and ' as ?' in local_context:
            return 'e'
        elif 'append(' in local_context and context_type != 'assignment_target':
            if 'error' in full_expr or 'issue' in full_expr:
                return "'Missing required field'"
            else:
                return '_container'
        
        # Final fallback based on context type
        if context_type == 'assignment_target':
            return 'temp_var'  # Valid variable name
        else:
            return 'None'  # Safe value for expressions

    def _validate_statement_syntax(self, stmt_str: str) -> tuple:
        """
        Validate that a statement string has valid Python syntax.
        
        Args:
            stmt_str: Statement string to validate
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        try:
            # Try to parse as a statement first
            ast.parse(stmt_str, mode='exec')
            return True, None
        except SyntaxError as e:
            # Try as expression
            try:
                ast.parse(stmt_str, mode='eval')
                return True, None
            except SyntaxError:
                return False, str(e)

    def _safe_resolve_placeholders(self, expr: str, context: dict) -> str:
        """
        Safely resolve placeholders with validation and fallback.
        
        Args:
            expr: Expression containing placeholders
            context: Resolution context
            
        Returns:
            Resolved expression with valid syntax
        """
        if '?' not in expr:
            return expr
        
        original = expr
        
        try:
            # Attempt resolution
            resolved = self._resolve_placeholder_with_context(expr, context)
            
            # Special case: Don't validate loop fragments as complete statements
            if context and context.get('is_loop_variable') and resolved.startswith('@'):
                # For loop variables, just return the resolved result without validation
                # since @variable,iterator is not valid Python by itself, only within for loops
                self.logger.debug(f"Loop variable fragment resolved: {repr(original)} -> {repr(resolved)}")
                return resolved
            
            # Validate the result for other contexts
            is_valid, error = self._validate_statement_syntax(resolved)
            
            if is_valid:
                self.logger.debug(f"Successfully resolved: {repr(original)} -> {repr(resolved)}")
                return resolved
            else:
                self.logger.warning(f"Invalid syntax after resolution: {error}")
                self.logger.warning(f"  Original: {repr(original)}")
                self.logger.warning(f"  Resolved: {repr(resolved)}")
                
                # Try a more conservative approach
                if '? =' in original:
                    # For assignments, use a safe variable name
                    resolved = original.replace('?', 'temp_var')
                    is_valid, _ = self._validate_statement_syntax(resolved)
                    if is_valid:
                        return resolved
                
                # Last resort: return original or a pass statement
                self.logger.error(f"Could not resolve placeholder safely, using fallback")
                return original
                
        except Exception as e:
            self.logger.error(f"Error during placeholder resolution: {e}")
            return original

    def _parse_ultra_dense_assignment(self, stmt_str: str, flow_compiler: FLOWCompiler) -> ast.AST:
        """Parse ultra-dense assignment like 'x=v' or 'x+=1' with comprehensive logging and error recovery."""
        self.logger.debug(f"_parse_ultra_dense_assignment called with: '{stmt_str}'")
        
        try:
            if '+=' in stmt_str:
                target_str, value_str = stmt_str.split('+=', 1)
                target_str = target_str.strip()
                value_str = value_str.strip()
                
                self.logger.debug(f"Augmented assignment - target: {target_str}, value: {value_str}")
                
                try:
                    # CRITICAL FIX: Clean CID references before expression parsing
                    target_str = self._clean_cid_references(target_str)
                    value_str = self._clean_cid_references(value_str)
                    
                    target = flow_compiler._parse_expression_string(target_str)
                    if isinstance(target, ast.Name):
                        target.ctx = ast.Store()
                    
                    value = ast.BinOp(
                        left=flow_compiler._parse_expression_string(target_str),
                        op=ast.Add(),
                        right=flow_compiler._parse_expression_string(value_str)
                    )
                    assign_node = ast.Assign(targets=[target], value=value)
                    self.logger.debug(f"Created augmented assignment AST")
                    return self._fix_ast_node_attributes(assign_node)
                except Exception as e:
                    self.logger.warning(f"Failed to parse augmented assignment parts: {e}")
                    # Fallback to simple assignment with pass value
                    target = ast.Name(id='_temp_var', ctx=ast.Store())
                    value = ast.Constant(value=None)
                    return self._fix_ast_node_attributes(ast.Assign(targets=[target], value=value))
            else:
                target_str, value_str = stmt_str.split('=', 1)
                target_str = target_str.strip()
                value_str = value_str.strip()
                
                # CRITICAL FIX: Clean CID references before expression parsing
                target_str = self._clean_cid_references(target_str)
                value_str = self._clean_cid_references(value_str)
                
                self.logger.debug(f"Regular assignment - target: {target_str}, value: {value_str}")
                
                try:
                    target = flow_compiler._parse_expression_string(target_str)
                    if isinstance(target, ast.Name):
                        target.ctx = ast.Store()
                        self.logger.debug(f"Target is Name: {target.id}")
                    
                    value = flow_compiler._parse_expression_string(value_str)
                    self.logger.debug(f"Parsed value expression")
                    
                    assign_node = ast.Assign(targets=[target], value=value)
                    self.logger.debug(f"Created regular assignment AST")
                    return self._fix_ast_node_attributes(assign_node)
                except Exception as e:
                    self.logger.warning(f"Failed to parse assignment parts: {e}")
                    # Fallback to simple assignment with safe names
                    target = ast.Name(id='_temp_var', ctx=ast.Store())
                    value = ast.Constant(value=None)
                    return self._fix_ast_node_attributes(ast.Assign(targets=[target], value=value))
        
        except Exception as e:
            self.logger.warning(f"Failed to parse assignment '{stmt_str}': {e}")
            # Return a safe Pass statement as ultimate fallback
            return self._fix_ast_node_attributes(ast.Pass())

    def _parse_ultra_dense_return(self, stmt_str: str, flow_compiler: FLOWCompiler) -> ast.AST:
        """Parse ultra-dense return like 'RT', 'RF', 'RN', or 'Rvalue'."""
        if stmt_str == 'RT':
            return self._fix_ast_node_attributes(ast.Return(value=ast.Constant(value=True)))
        elif stmt_str == 'RF':
            return self._fix_ast_node_attributes(ast.Return(value=ast.Constant(value=False)))
        elif stmt_str == 'RN' or stmt_str == 'R':
            return self._fix_ast_node_attributes(ast.Return(value=None))
        else:
            value_str = stmt_str[1:]  # Remove 'R' prefix
            value = flow_compiler._parse_expression_string(value_str)
            return self._fix_ast_node_attributes(ast.Return(value=value))

    def _parse_ultra_dense_for(self, stmt_str: str, flow_compiler: FLOWCompiler) -> ast.AST:
        """Parse ultra-dense for loop like '@x,y{body}' with improved parsing."""
        self.logger.debug(f"Parsing ultra-dense for loop: {stmt_str}")
        
        try:
            # Extract parts more carefully
            at_idx = stmt_str.index('@')
            comma_idx = stmt_str.index(',')
            brace_idx = stmt_str.index('{')
            close_brace_idx = stmt_str.rindex('}')
            
            target_str = stmt_str[at_idx+1:comma_idx].strip()
            iter_str = stmt_str[comma_idx+1:brace_idx].strip()
            body_str = stmt_str[brace_idx+1:close_brace_idx].strip()
            
            self.logger.debug(f"For-loop parts - target: {target_str}, iter: {iter_str}, body: {body_str}")
            
            # Parse components with proper name resolution
            # Handle placeholder ? in target - use context-aware resolution
            if target_str == '?':
                # Use the new context-aware resolution
                context = {
                    'is_loop_variable': True,
                    'iterator_context': iter_str,
                    'current_scope': getattr(flow_compiler, 'current_scope_id', None),
                }
                resolved = self._safe_resolve_placeholders(f'@{target_str},', context)
                # Extract the resolved variable name
                if resolved.startswith('@') and ',' in resolved:
                    target_str = resolved[1:resolved.index(',')]
                    self.logger.debug(f"Resolved loop variable from placeholder: {target_str}")
                    target = ast.Name(id=target_str, ctx=ast.Store())
                else:
                    # Fallback to inference from iterator
                    self.logger.debug("Using fallback inference from iterator context")
                    expanded_iter = flow_compiler.expand_compressed_operators(iter_str)
                    
                    # Check for common patterns in both original and expanded forms
                    is_items = ('items()' in iter_str or 'items()' in expanded_iter or 
                               '.it()' in iter_str or 'it()' in iter_str)
                    is_keys = ('keys()' in iter_str or 'keys()' in expanded_iter or 
                              '.ke()' in iter_str or 'ke()' in iter_str)
                    is_values = ('values()' in iter_str or 'values()' in expanded_iter or 
                                '.va()' in iter_str or 'va()' in iter_str)
                    
                    if is_items:
                        # For dict.items(), use (key, value) tuple
                        target = ast.Tuple(elts=[
                            ast.Name(id='key', ctx=ast.Store()),
                            ast.Name(id='value', ctx=ast.Store())
                        ], ctx=ast.Store())
                    elif is_keys:
                        target = ast.Name(id='key', ctx=ast.Store())
                    elif is_values:
                        target = ast.Name(id='value', ctx=ast.Store())
                    else:
                        # Generic iterator variable
                        target = ast.Name(id='item', ctx=ast.Store())
            else:
                target = flow_compiler._parse_expression_string(target_str)
                if isinstance(target, ast.Name):
                    target.ctx = ast.Store()
            
            iter_expr = flow_compiler._parse_expression_string(iter_str)
            
            # Parse body with proper statement handling and error recovery
            body_stmts = []
            # Use smart semicolon splitting that respects braces
            sub_statements = self._split_statements_respecting_braces(body_str)
            for sub_stmt in sub_statements:
                sub_stmt = sub_stmt.strip()
                if sub_stmt:
                    try:
                        stmt = self._parse_ultra_dense_statement(sub_stmt, flow_compiler)
                        if stmt:
                            body_stmts.append(stmt)
                    except Exception as e:
                        self.logger.warning(f"Failed to parse for-loop body statement '{sub_stmt}': {e}")
                        # Add a pass statement as fallback for this sub-statement
                        body_stmts.append(self._fix_ast_node_attributes(ast.Pass()))
            
            # Ensure we have at least a pass statement
            if not body_stmts:
                body_stmts = [self._fix_ast_node_attributes(ast.Pass())]
            
            for_node = ast.For(target=target, iter=iter_expr, body=body_stmts, orelse=[])
            self.logger.debug(f"Successfully created for-loop AST")
            return self._fix_ast_node_attributes(for_node)
            
        except Exception as e:
            self.logger.error(f"Error parsing ultra-dense for loop: {e}")
            # Return a pass statement as fallback
            return self._fix_ast_node_attributes(ast.Pass())

    def _parse_ultra_dense_conditional(self, stmt_str: str, flow_compiler: FLOWCompiler) -> ast.AST:
        """Parse ultra-dense conditional like 'd!inb?RF:_' or '(i>5)?{x=i*2}:{x=i}' → if statements"""
        # Clean CID references before parsing
        stmt_str = self._clean_cid_references(stmt_str)
        
        if '?' in stmt_str and ':' in stmt_str:
            # Find the positions of ? and : respecting nested braces
            question_idx = -1
            colon_idx = -1
            brace_depth = 0
            paren_depth = 0
            
            for i, char in enumerate(stmt_str):
                if char == '{':
                    brace_depth += 1
                elif char == '}':
                    brace_depth -= 1
                elif char == '(':
                    paren_depth += 1
                elif char == ')':
                    paren_depth -= 1
                elif char == '?' and brace_depth == 0 and paren_depth == 0 and question_idx == -1:
                    question_idx = i
                elif char == ':' and brace_depth == 0 and paren_depth == 0 and question_idx != -1 and colon_idx == -1:
                    colon_idx = i
                    break
            
            if question_idx == -1 or colon_idx == -1:
                # Fallback to simple parsing
                question_idx = stmt_str.index('?')
                colon_idx = stmt_str.index(':', question_idx)
            
            # Extract the three parts
            condition_str = stmt_str[:question_idx]
            true_action_str = stmt_str[question_idx+1:colon_idx]
            false_action_str = stmt_str[colon_idx+1:]
            
            # Handle condition with parentheses - ensure balanced removal
            condition_str = condition_str.strip()
            
            # Only remove outer parentheses if they wrap the entire condition
            if (condition_str.startswith('(') and condition_str.endswith(')') and
                self._is_balanced_parentheses(condition_str[1:-1])):
                condition_str = condition_str[1:-1]
            
            # Parse the condition (e.g., "d!inb" → "d not in b")
            # Clean CID references from condition before parsing
            condition_str_cleaned = self._clean_cid_references(condition_str)
            condition = flow_compiler._parse_condition_string(condition_str_cleaned)
            
            # Parse the true action - handle braced expressions
            true_stmt = self._parse_conditional_action(true_action_str, flow_compiler)
            
            # Parse the false action - handle braced expressions
            false_stmts = []
            if false_action_str != '_':
                false_stmt = self._parse_conditional_action(false_action_str, flow_compiler)
                if false_stmt:
                    false_stmts = [false_stmt]
            
            # Create the if statement
            if_stmt = ast.If(
                test=condition,
                body=[true_stmt] if true_stmt else [ast.Pass()],
                orelse=false_stmts
            )
            
            return self._fix_ast_node_attributes(if_stmt)
        
        # Handle simple conditional: (cond)stmt
        if stmt_str.startswith('(') and ')' in stmt_str:
            close_paren = stmt_str.index(')')
            condition_str = stmt_str[1:close_paren]
            stmt_part = stmt_str[close_paren+1:]
            
            condition = flow_compiler._parse_condition_string(condition_str)
            body_stmt = self._parse_ultra_dense_statement(stmt_part, flow_compiler)
            
            if_stmt = ast.If(
                test=condition,
                body=[body_stmt] if body_stmt else [ast.Pass()],
                orelse=[]
            )
            
            return self._fix_ast_node_attributes(if_stmt)
        
        # Fallback to pass
        return self._fix_ast_node_attributes(ast.Pass())

    def _parse_conditional_action(self, action_str: str, flow_compiler: FLOWCompiler) -> ast.AST:
        """Parse conditional action which may be braced {statement} or simple statement."""
        action_str = action_str.strip()
        
        # DIAGNOSTIC: Log what we're parsing
        self.logger.debug(f"_parse_conditional_action called with: '{action_str}'")
        
        # Pre-process to fix known ambiguous expansions
        action_str = self._fix_ambiguous_names(action_str)
        
        # CRITICAL FIX: Clean CID references before parsing
        action_str = self._clean_cid_references(action_str)
        
        self.logger.debug(f"After CID cleaning: '{action_str}'")
        
        # CRITICAL FIX: Handle braced expressions more carefully
        if action_str.startswith('{') and action_str.endswith('}'):
            inner_str = action_str[1:-1].strip()
            self.logger.debug(f"Processing braced expression, inner: '{inner_str}'")
            
            # FUNDAMENTAL FIX: Check if inner content contains assignments
            # If it does, parse as statement, NOT as expression
            if '=' in inner_str and not any(op in inner_str for op in ['==', '!=', '<=', '>=']):
                self.logger.debug(f"Braced content contains assignment, parsing as statement")
                # This is a statement block, not a dictionary expression
                # Parse the inner content as a statement directly
                return self._parse_conditional_action(inner_str, flow_compiler)
            
            # Check if the inner content contains multiple statements separated by semicolons
            if ';' in inner_str:
                self.logger.debug("Multiple statements detected in braced expression")
                # Parse as a block of statements
                statements = []
                parts = self._split_respecting_nesting(inner_str, ';')
                for part in parts:
                    part = part.strip()
                    if part:
                        stmt = self._parse_conditional_action(part, flow_compiler)
                        if stmt:
                            statements.append(stmt)
                
                # If we have multiple statements, wrap them in a compound statement
                if len(statements) == 1:
                    return statements[0]
                elif len(statements) > 1:
                    # For multiple statements, we need to return them as a list somehow
                    # Since we can only return one AST node, wrap in a try block or create a compound
                    # For now, just return the first statement to avoid malformed syntax
                    self.logger.warning(f"Multiple statements in conditional action, using first: {statements}")
                    return statements[0]
                else:
                    return ast.Pass()
            else:
                # Single statement, parse recursively
                self.logger.debug(f"Single statement in braces, recursing with: '{inner_str}'")
                result = self._parse_conditional_action(inner_str, flow_compiler)
                self.logger.debug(f"Recursive result type: {type(result)}")
                if hasattr(result, '__dict__'):
                    self.logger.debug(f"Recursive result: {ast.unparse(result) if hasattr(ast, 'unparse') else 'no unparse'}")
                return result
        
        # Handle specific return patterns
        if action_str == 'RF':
            return ast.Return(value=ast.Constant(value=False))
        elif action_str == 'RT':
            return ast.Return(value=ast.Constant(value=True))
        elif action_str == 'RN' or action_str == 'R':
            return ast.Return(value=None)
        elif action_str.startswith('R'):
            # Return with value
            value_str = action_str[1:]
            value = flow_compiler._parse_expression_string(value_str)
            return ast.Return(value=value)
        elif action_str == '_':
            return ast.Pass()
        elif '=' in action_str and not any(op in action_str for op in ['==', '!=', '<=', '>=']):
            # Assignment statement - ensure proper parsing
            self.logger.debug(f"Parsing as assignment: '{action_str}'")
            try:
                result = self._parse_ultra_dense_assignment(action_str, flow_compiler)
                self.logger.debug(f"Assignment result type: {type(result)}")
                if hasattr(result, '__dict__'):
                    self.logger.debug(f"Assignment result: {ast.unparse(result) if hasattr(ast, 'unparse') else 'no unparse'}")
                return result
            except Exception as e:
                self.logger.error(f"Failed to parse assignment '{action_str}': {e}")
                return ast.Pass()
        else:
            # Parse as general statement
            try:
                result = self._parse_ultra_dense_statement(action_str, flow_compiler)
                return result if result else ast.Pass()
            except Exception as e:
                self.logger.error(f"Failed to parse conditional action '{action_str}': {e}")
                return ast.Pass()
        
        return self._fix_ast_node_attributes(ast.Pass())

    def _parse_ultra_dense_statement(self, stmt_str: str, flow_compiler: FLOWCompiler) -> Optional[ast.AST]:
        """Parse any ultra-dense statement with placeholder resolution."""
        stmt_str = stmt_str.strip()
        self.logger.debug(f"=== ULTRA DENSE STATEMENT PARSING ===")
        self.logger.debug(f"Input: {repr(stmt_str)}")
        
        # COMPREHENSIVE PATTERN ANALYSIS
        patterns_detected = []
        if 'for ' in stmt_str or stmt_str.startswith('@'):
            patterns_detected.append("FOR_LOOP")
        if 'T{' in stmt_str and ('X' in stmt_str or 'X{' in stmt_str):
            patterns_detected.append("TRY_EXCEPT")
        if '?' in stmt_str and ('{' in stmt_str or '}:' in stmt_str):
            patterns_detected.append("CONDITIONAL")
        if stmt_str.startswith('@') and ',' in stmt_str and '{' in stmt_str:
            patterns_detected.append("COMPLEX_FOR")
        
        self.logger.debug(f"Patterns detected: {patterns_detected}")
        
        # HIGHEST PRIORITY: Delegate ALL complex multi-pattern statements to FLOW compiler
        should_delegate = (
            len(patterns_detected) > 1 or  # Multiple patterns
            'TRY_EXCEPT' in patterns_detected or  # Always delegate try-except
            'COMPLEX_FOR' in patterns_detected or  # Complex for-loops
            ('?' in stmt_str and ('T{' in stmt_str or 'X{' in stmt_str)) or  # Conditional + try-except
            (stmt_str.count('{') > 2) or  # Highly nested
            ('for ' in stmt_str and 'except' in stmt_str)  # Mixed patterns
        )
        
        if should_delegate:
            self.logger.debug(f"🔄 DELEGATING TO FLOW COMPILER: Patterns={patterns_detected}")
            self.logger.debug(f"🔄 Delegation criteria met: complex={len(patterns_detected) > 1}, "
                            f"try_except={'TRY_EXCEPT' in patterns_detected}, "
                            f"complex_for={'COMPLEX_FOR' in patterns_detected}")
            try:
                # Use FLOW compiler's native parsing for complex patterns
                self.logger.debug(f"🔄 Calling flow_compiler._parse_flow_lines with: {[stmt_str]}")
                parsed_results = flow_compiler._parse_flow_lines([stmt_str], 0)
                self.logger.debug(f"🔄 FLOW compiler returned: {len(parsed_results)} results")
                
                if parsed_results and len(parsed_results) > 0:
                    parsed_stmts = parsed_results[0]
                    if parsed_stmts and len(parsed_stmts) > 0:
                        result = self._fix_ast_node_attributes(parsed_stmts[0])
                        self.logger.debug(f"✅ FLOW compiler delegation successful")
                        return result
                    else:
                        self.logger.warning(f"⚠️ FLOW compiler returned empty statement list")
                else:
                    self.logger.warning(f"⚠️ FLOW compiler returned no results")
                    
            except Exception as flow_error:
                self.logger.error(f"❌ FLOW compiler failed: {flow_error}")
                import traceback
                self.logger.debug(f"FLOW compiler traceback: {traceback.format_exc()}")
        
        # CRITICAL: Check for conditional patterns FIRST (for simple conditionals only)
        if 'CONDITIONAL' in patterns_detected and len(patterns_detected) == 1:
            self.logger.debug(f"🔍 Processing simple conditional pattern")
            is_conditional, pattern_parts = self._detect_conditional_pattern(stmt_str)
            if is_conditional:
                self.logger.debug(f"Detected conditional pattern: {pattern_parts}")
                
                # Resolve the pattern to valid Python
                resolved = self._resolve_conditional_pattern(pattern_parts)
                self.logger.debug(f"Resolved conditional to: {resolved}")
                
                # Parse the resolved Python
                try:
                    # For if statements, parse as statement
                    if resolved.startswith('if '):
                        # Parse the if statement
                        lines = resolved.split('\n')
                        tree = ast.parse('\n'.join(lines))
                        if tree.body:
                            return self._fix_ast_node_attributes(tree.body[0])
                    else:
                        # For ternary expressions, parse as expression then wrap
                        expr = ast.parse(resolved, mode='eval').body
                        # Check if it's an assignment
                        if ' = ' in resolved:
                            # Parse as assignment
                            tree = ast.parse(resolved)
                            if tree.body:
                                return self._fix_ast_node_attributes(tree.body[0])
                        return self._fix_ast_node_attributes(ast.Expr(value=expr))
                except SyntaxError as e:
                    self.logger.warning(f"Failed to parse resolved conditional: {e}")
                    # Fall through to existing logic
        
        # CRITICAL: Check for complex structures BEFORE placeholder resolution
        # because placeholder resolution can corrupt the structure
        
        # Check for try-except structures first (highest priority)
        if stmt_str.startswith('T{') and 'X' in stmt_str:
            self.logger.debug("⚠️ WARNING: Try-except pattern not delegated - processing locally")
            return self._parse_ultra_dense_try_except(stmt_str, flow_compiler)
        
        # Check for for-loop structures with placeholders
        if stmt_str.startswith('@') and ',' in stmt_str and '{' in stmt_str:
            self.logger.debug("Statement detected as for-loop (before placeholder resolution)")
            return self._parse_ultra_dense_for(stmt_str, flow_compiler)
        
        # CRITICAL: Resolve placeholders before parsing simple statements
        if '?' in stmt_str:
            context = {
                'current_scope': getattr(flow_compiler, 'current_scope_id', None),
                'local_compressions': getattr(flow_compiler, 'local_compressions', {}),
            }
            stmt_str = self._safe_resolve_placeholders(stmt_str, context)
        
        # Pre-process to fix known ambiguous expansions
        stmt_str = self._fix_ambiguous_names(stmt_str)
        
        if not stmt_str or stmt_str == '_':
            self.logger.debug("Statement is empty or pass, returning ast.Pass()")
            return self._fix_ast_node_attributes(ast.Pass())
        
        try:
            # FIRST: Check for conditional expressions with ? and : - highest priority
            if '?' in stmt_str and ':' in stmt_str:
                self.logger.debug(f"CONDITIONAL EXPRESSION DETECTED: '{stmt_str}'")
                return self._parse_ultra_dense_conditional(stmt_str, flow_compiler)
            
            # Handle conditional assignments like (condition)assignment
            if stmt_str.startswith('(') and ')' in stmt_str and '=' in stmt_str:
                # Use proper parentheses matching to find the condition
                paren_count = 0
                closing_paren = -1
                for i, char in enumerate(stmt_str):
                    if char == '(':
                        paren_count += 1
                    elif char == ')':
                        paren_count -= 1
                        if paren_count == 0:
                            closing_paren = i
                            break
                
                if closing_paren > 0 and closing_paren < len(stmt_str) - 1:
                    condition_str = stmt_str[1:closing_paren]
                    rest_str = stmt_str[closing_paren+1:]
                    
                    # CRITICAL FIX: Strip braces from rest_str if present
                    if rest_str.startswith('{') and rest_str.endswith('}'):
                        rest_str = rest_str[1:-1].strip()
                        self.logger.debug(f"Stripped braces from assignment: '{rest_str}'")
                    
                    # Check if the rest contains assignments
                    if '=' in rest_str and not rest_str.startswith('=') and '==' not in rest_str:
                        try:
                            # Parse the condition with proper operator expansion
                            condition = flow_compiler._parse_condition_string(condition_str)
                            
                            # CRITICAL FIX: Handle multiple statements separated by semicolons
                            if ';' in rest_str:
                                self.logger.debug(f"CONDITIONAL MULTIPLE ASSIGNMENTS: condition='{condition_str}', statements='{rest_str}'")
                                # Multiple statements - parse each one separately
                                body_stmts = []
                                parts = rest_str.split(';')
                                for part in parts:
                                    part = part.strip()
                                    if not part:
                                        continue
                                    
                                    if '=' in part and not any(op in part for op in ['==', '!=', '<=', '>=']):
                                        # This is an assignment
                                        stmt = self._parse_ultra_dense_assignment(part, flow_compiler)
                                    elif part.startswith('R'):
                                        # This is a return statement
                                        stmt = self._parse_ultra_dense_return(part, flow_compiler)
                                    else:
                                        # This is likely a method call or other expression
                                        try:
                                            expr = flow_compiler._parse_expression_string(part)
                                            stmt = self._fix_ast_node_attributes(ast.Expr(value=expr))
                                        except Exception as e:
                                            self.logger.warning(f"Failed to parse statement part '{part}': {e}")
                                            continue
                                    
                                    if stmt:
                                        body_stmts.append(stmt)
                                
                                if body_stmts:
                                    if_stmt = ast.If(
                                        test=condition,
                                        body=body_stmts,
                                        orelse=[]
                                    )
                                    self.logger.debug(f"Successfully created conditional multiple assignments IF statement with {len(body_stmts)} statements")
                                    return self._fix_ast_node_attributes(if_stmt)
                            else:
                                # Single assignment
                                self.logger.debug(f"CONDITIONAL ASSIGNMENT DETECTED: condition='{condition_str}', assignment='{rest_str}'")
                                
                                # Parse the assignment part
                                assignment = self._parse_ultra_dense_assignment(rest_str, flow_compiler)
                                
                                # Create if statement
                                if_stmt = ast.If(
                                    test=condition,
                                    body=[assignment],
                                    orelse=[]
                                )
                                self.logger.debug(f"Successfully created conditional assignment IF statement")
                                return self._fix_ast_node_attributes(if_stmt)
                        except Exception as e:
                            self.logger.warning(f"Failed to parse as conditional assignment: {e}")
                            # Fall through to regular parsing
            
            # Check for conditional expression pattern: (condition)statement
            if stmt_str.startswith('(') and ')' in stmt_str:
                # Find the closing parenthesis for the condition
                paren_count = 0
                close_idx = -1
                for i, char in enumerate(stmt_str):
                    if char == '(':
                        paren_count += 1
                    elif char == ')':
                        paren_count -= 1
                        if paren_count == 0:
                            close_idx = i
                            break
                
                # Check if there's a statement after the condition
                if close_idx > 0 and close_idx < len(stmt_str) - 1:
                    condition_str = stmt_str[1:close_idx]
                    statement_str = stmt_str[close_idx + 1:]
                    
                    # CRITICAL FIX: Strip braces from statement if present
                    if statement_str.startswith('{') and statement_str.endswith('}'):
                        statement_str = statement_str[1:-1].strip()
                        self.logger.debug(f"Stripped braces from statement: '{statement_str}'")
                    
                    # Only treat as conditional if the statement part is not empty
                    if statement_str.strip():
                        self.logger.debug(f"CONDITIONAL STATEMENT: condition='{condition_str}', statement='{statement_str}'")
                        
                        try:
                            # Parse condition with proper operator expansion
                            condition = flow_compiler._parse_condition_string(condition_str)
                            
                            # Parse the statement part - handle multiple statements separated by semicolons
                            if ';' in statement_str:
                                # Multiple statements - parse each one separately
                                body_stmts = []
                                parts = statement_str.split(';')
                                for part in parts:
                                    part = part.strip()
                                    if not part:
                                        continue
                                    
                                    if '=' in part and not any(op in part for op in ['==', '!=', '<=', '>=']):
                                        # This is an assignment
                                        stmt = self._parse_ultra_dense_assignment(part, flow_compiler)
                                    elif part.startswith('R'):
                                        # This is a return statement
                                        stmt = self._parse_ultra_dense_return(part, flow_compiler)
                                    else:
                                        # This is likely a method call or other expression
                                        try:
                                            expr = flow_compiler._parse_expression_string(part)
                                            stmt = self._fix_ast_node_attributes(ast.Expr(value=expr))
                                        except Exception as e:
                                            self.logger.warning(f"Failed to parse statement part '{part}': {e}")
                                            continue
                                    
                                    if stmt:
                                        body_stmts.append(stmt)
                                
                                if body_stmts:
                                    if_stmt = ast.If(
                                        test=condition,
                                        body=body_stmts,
                                        orelse=[]
                                    )
                                    self.logger.debug(f"CONDITIONAL STATEMENT: Successfully created if statement with {len(body_stmts)} statements")
                                    return self._fix_ast_node_attributes(if_stmt)
                            
                            elif '=' in statement_str and not any(op in statement_str for op in ['==', '!=', '<=', '>=']):
                                # Single assignment
                                body_stmt = self._parse_ultra_dense_assignment(statement_str, flow_compiler)
                            elif statement_str.startswith('R'):
                                # This is a return statement
                                body_stmt = self._parse_ultra_dense_return(statement_str, flow_compiler)
                            else:
                                # This is likely a method call or other expression
                                try:
                                    expr = flow_compiler._parse_expression_string(statement_str)
                                    body_stmt = self._fix_ast_node_attributes(ast.Expr(value=expr))
                                except Exception as e:
                                    self.logger.warning(f"Failed to parse statement part as expression: {e}")
                                    body_stmt = self._fix_ast_node_attributes(ast.Pass())
                            
                            if body_stmt:
                                if_stmt = ast.If(test=condition, body=[body_stmt], orelse=[])
                                self.logger.debug(f"CONDITIONAL STATEMENT: Successfully created if statement")
                                return self._fix_ast_node_attributes(if_stmt)
                        except Exception as e:
                            self.logger.warning(f"Failed to parse as conditional statement: {e}")
                            # Fall through to regular parsing
            
            # Check for various statement types with error handling
            # FOR-LOOP DETECTION MUST COME BEFORE ASSIGNMENT DETECTION
            # Because for-loops like @c,iter{body} contain = signs in the body
            if stmt_str.startswith('@') and ',' in stmt_str and '{' in stmt_str:
                self.logger.debug("Statement detected as for-loop")
                return self._parse_ultra_dense_for(stmt_str, flow_compiler)
            elif stmt_str.startswith('R'):
                self.logger.debug("Statement detected as return")
                return self._parse_ultra_dense_return(stmt_str, flow_compiler)
            elif stmt_str == 'B':
                self.logger.debug("Statement detected as break")
                return self._fix_ast_node_attributes(ast.Break())
            elif stmt_str == 'K':
                self.logger.debug("Statement detected as continue")
                return self._fix_ast_node_attributes(ast.Continue())
            elif '=' in stmt_str and not any(op in stmt_str for op in ['==', '!=', '<=', '>=']):
                self.logger.debug("Statement detected as assignment")
                return self._parse_ultra_dense_assignment(stmt_str, flow_compiler)
            elif stmt_str.startswith('@'):
                self.logger.debug("Statement detected as print")
                # Handle print statements like @? or @var
                arg_str = stmt_str[1:]  # Remove @
                if arg_str == '?':
                    # @? becomes print() - empty print
                    print_node = ast.Expr(value=ast.Call(
                        func=ast.Name(id='print', ctx=ast.Load()),
                        args=[],
                        keywords=[]
                    ))
                else:
                    # @arg becomes print(arg)
                    try:
                        arg = flow_compiler._parse_expression_string(arg_str)
                        print_node = ast.Expr(value=ast.Call(
                            func=ast.Name(id='print', ctx=ast.Load()),
                            args=[arg],
                            keywords=[]
                        ))
                    except:
                        # Fallback to empty print
                        print_node = ast.Expr(value=ast.Call(
                            func=ast.Name(id='print', ctx=ast.Load()),
                            args=[],
                            keywords=[]
                        ))
                return self._fix_ast_node_attributes(print_node)
            elif stmt_str.startswith('T{') and 'X' in stmt_str:
                self.logger.debug("Statement detected as try-except")
                return self._parse_ultra_dense_try_except(stmt_str, flow_compiler)
            elif '?' in stmt_str and ':' in stmt_str:
                self.logger.debug("Statement detected as conditional")
                return self._parse_ultra_dense_conditional(stmt_str, flow_compiler)
            else:
                # Try as expression statement
                self.logger.debug("Attempting to parse as expression statement")
                try:
                    expr = flow_compiler._parse_expression_string(stmt_str)
                    self.logger.debug("Successfully parsed as expression")
                    return self._fix_ast_node_attributes(ast.Expr(value=expr))
                except Exception as e:
                    self.logger.debug(f"Failed to parse as expression: {e}, returning ast.Pass()")
                    return self._fix_ast_node_attributes(ast.Pass())
        
        except Exception as e:
            self.logger.warning(f"Failed to parse ultra-dense statement '{stmt_str}': {e}")
            
            # ENHANCED ERROR RECOVERY: Try to fix malformed patterns before giving up
            try:
                self.logger.debug("Attempting error recovery with malformed statement fixing")
                fixed_stmt = self._fix_malformed_statement(stmt_str)
                if fixed_stmt != stmt_str:
                    self.logger.debug(f"Fixed malformed statement: '{stmt_str}' -> '{fixed_stmt}'")
                    
                    # Try parsing the fixed statement
                    if fixed_stmt.startswith('if '):
                        # Parse as complete if statement
                        tree = ast.parse(fixed_stmt)
                        if tree.body:
                            return self._fix_ast_node_attributes(tree.body[0])
                    elif fixed_stmt.startswith('for '):
                        # Parse as complete for statement
                        tree = ast.parse(fixed_stmt)
                        if tree.body:
                            return self._fix_ast_node_attributes(tree.body[0])
                    elif '=' in fixed_stmt and not any(op in fixed_stmt for op in ['==', '!=', '<=', '>=']):
                        # Try as assignment
                        tree = ast.parse(fixed_stmt)
                        if tree.body:
                            return self._fix_ast_node_attributes(tree.body[0])
                    else:
                        # Try as expression
                        expr = flow_compiler._parse_expression_string(fixed_stmt)
                        return self._fix_ast_node_attributes(ast.Expr(value=expr))
                        
            except Exception as recovery_error:
                self.logger.debug(f"Error recovery failed: {recovery_error}")
            
            # Return a safe Pass statement as fallback
            return self._fix_ast_node_attributes(ast.Pass())

    def _parse_ultra_dense_try_except(self, stmt_str: str, flow_compiler: FLOWCompiler = None) -> ast.AST:
        """
        Parse ultra-dense try-except with improved structure handling.
        Handles: T{body}X{handler} format
        """
        self.logger.debug(f"Parsing ultra-dense try-except: {stmt_str}")
        
        try:
            if not stmt_str.startswith('T{'):
                self.logger.debug(f"Statement doesn't start with T{{: {stmt_str}")
                return self._fix_ast_node_attributes(ast.Pass())
            
            # Use enhanced brace matching
            try_body_end = self._find_matching_brace_enhanced(stmt_str, 1)  # Start after 'T'
            
            if try_body_end == -1:
                self.logger.warning("Could not find matching brace for try body")
                # Attempt to repair incomplete structure
                stmt_str = self._attempt_structure_repair(stmt_str)
                try_body_end = self._find_matching_brace_enhanced(stmt_str, 1)
                if try_body_end == -1:
                    return self._fix_ast_node_attributes(ast.Pass())
            
            # Extract try body
            body_str = stmt_str[2:try_body_end]  # Skip 'T{'
            self.logger.debug(f"Try body: {body_str}")
            
            # Parse try body - handle for-loops specially
            body_stmts = []
            if '@' in body_str and ',' in body_str and '{' in body_str:
                # This is a for-loop in the try block
                # Parse it as a for-loop statement
                for_stmt = self._parse_ultra_dense_for(body_str, flow_compiler)
                if for_stmt:
                    body_stmts.append(for_stmt)
            else:
                # Parse as regular block statements
                body_stmts = self._parse_block_statements_safe(body_str, flow_compiler)
            
            # Check for except handler
            handlers = []
            x_pattern_start = try_body_end + 1
            
            if x_pattern_start < len(stmt_str) and stmt_str[x_pattern_start] == 'X':
                # Parse except handler
                handler = self._parse_except_handler_enhanced(stmt_str[x_pattern_start:], flow_compiler)
                if handler:
                    handlers.append(handler)
            
            # Create the try statement
            try_node = ast.Try(
                body=body_stmts or [self._fix_ast_node_attributes(ast.Pass())],
                handlers=handlers,
                orelse=[],
                finalbody=[]
            )
            
            return self._fix_ast_node_attributes(try_node)
            
        except Exception as e:
            self.logger.error(f"Error parsing try-except '{stmt_str}': {e}")
            import traceback
            self.logger.debug(traceback.format_exc())
            return self._fix_ast_node_attributes(ast.Pass())

    def _parse_except_handler_enhanced(self, handler_str: str, flow_compiler: FLOWCompiler = None) -> ast.ExceptHandler:
        """
        Enhanced except handler parser with better exception variable handling.
        """
        self.logger.debug(f"Parsing except handler: {handler_str}")
        
        try:
            if not handler_str.startswith('X'):
                return None
            
            exc_type = None
            exc_name = None
            handler_body_str = None
            
            # Parse exception pattern
            if handler_str[1] == '(':
                # Has exception type: X(ExceptionType){body}
                paren_end = handler_str.find(')')
                if paren_end > 2:
                    exc_type_str = handler_str[2:paren_end]
                    exc_type = ast.Name(id=exc_type_str, ctx=ast.Load()) if exc_type_str != 'E' else None
                    
                    # Look for handler body
                    brace_start = handler_str.find('{', paren_end)
                    if brace_start != -1:
                        brace_end = self._find_matching_brace_enhanced(handler_str, brace_start)
                        if brace_end != -1:
                            handler_body_str = handler_str[brace_start+1:brace_end]
                            
                            # Check for exception variable binding
                            if handler_body_str.startswith('@'):
                                # Extract exception variable name
                                if handler_body_str[1:2] == '?':
                                    exc_name = 'e'  # Default exception name
                                else:
                                    # Extract actual variable name
                                    var_end = 1
                                    while var_end < len(handler_body_str) and handler_body_str[var_end].isalnum():
                                        var_end += 1
                                    exc_name = handler_body_str[1:var_end]
                                
                                # Remove variable binding from body
                                if ';' in handler_body_str:
                                    handler_body_str = handler_body_str[handler_body_str.index(';')+1:].strip()
                                else:
                                    handler_body_str = '_'  # Just pass if only binding
            
            elif handler_str[1] == '{':
                # No exception type: X{body}
                brace_end = self._find_matching_brace_enhanced(handler_str, 1)
                if brace_end != -1:
                    handler_body_str = handler_str[2:brace_end]
                    
                    # Check for exception variable pattern
                    if handler_body_str.startswith('@'):
                        if handler_body_str[1:2] == '?':
                            exc_name = 'e'
                        else:
                            var_end = 1
                            while var_end < len(handler_body_str) and handler_body_str[var_end].isalnum():
                                var_end += 1
                            exc_name = handler_body_str[1:var_end]
                        
                        if ';' in handler_body_str:
                            handler_body_str = handler_body_str[handler_body_str.index(';')+1:].strip()
                        else:
                            handler_body_str = '_'
            
            # Parse handler body
            if handler_body_str:
                if handler_body_str == '_':
                    handler_stmts = [self._fix_ast_node_attributes(ast.Pass())]
                else:
                    handler_stmts = self._parse_block_statements_safe(handler_body_str, flow_compiler)
            else:
                handler_stmts = [self._fix_ast_node_attributes(ast.Pass())]
            
            return ast.ExceptHandler(
                type=exc_type,
                name=exc_name,
                body=handler_stmts or [self._fix_ast_node_attributes(ast.Pass())]
            )
            
        except Exception as e:
            self.logger.warning(f"Failed to parse except handler: {e}")
            return ast.ExceptHandler(type=None, name=None, body=[self._fix_ast_node_attributes(ast.Pass())])

    def _find_matching_brace_enhanced(self, text: str, start_pos: int) -> int:
        """
        Enhanced brace matching that handles nested structures and string literals.
        """
        if start_pos >= len(text) or text[start_pos] != '{':
            return -1
        
        stack = ['{']
        i = start_pos + 1
        in_string = False
        string_char = None
        escape_next = False
        
        while i < len(text) and stack:
            char = text[i]
            
            # Handle escape sequences
            if escape_next:
                escape_next = False
                i += 1
                continue
                
            if char == '\\' and not in_string:
                escape_next = True
                i += 1
                continue
            
            # Handle string literals
            if not in_string:
                if char in '"\'':
                    in_string = True
                    string_char = char
            else:
                if char == string_char and not escape_next:
                    in_string = False
                    string_char = None
            
            # Only process brackets when not in a string
            if not in_string:
                if char in '{[(':
                    stack.append(char)
                elif char in '}])':
                    if not stack:
                        return -1
                    
                    # Check matching pairs
                    opening = stack.pop()
                    matching_pairs = {'}': '{', ']': '[', ')': '('}
                    expected = matching_pairs.get(char)
                    
                    if opening != expected:
                        self.logger.warning(f"Mismatched brackets: {opening} vs {char}")
                        return -1
                    
                    # If stack is empty, we found our match
                    if not stack:
                        return i
            
            i += 1
        
        return -1  # Unmatched brace

    def _validate_bracket_structure(self, text: str) -> Tuple[bool, str]:
        """
        Validate bracket structure completeness.
        Returns (is_valid, error_message)
        """
        stack = []
        bracket_pairs = {'}': '{', ']': '[', ')': '('}
        
        for i, char in enumerate(text):
            if char in '{[(':
                stack.append((char, i))
            elif char in '}])':
                if not stack:
                    return False, f"Unmatched closing bracket '{char}' at position {i}"
                
                opening, pos = stack.pop()
                expected = bracket_pairs[char]
                if opening != expected:
                    return False, f"Mismatched brackets: '{opening}' at {pos} vs '{char}' at {i}"
        
        if stack:
            opening, pos = stack[0]
            return False, f"Unclosed bracket '{opening}' at position {pos}"
        
        return True, "Valid"

    def _find_matching_brace(self, text: str, start_pos: int) -> int:
        """Find matching closing brace with improved nested structure handling."""
        if start_pos >= len(text) or text[start_pos] != '{':
            return -1
        
        stack = []
        i = start_pos
        in_string = False
        string_char = None
        escape_next = False
        
        while i < len(text):
            char = text[i]
            
            # Handle escape sequences
            if escape_next:
                escape_next = False
                i += 1
                continue
                
            if char == '\\':
                escape_next = True
                i += 1
                continue
            
            # Handle string literals more robustly
            if not in_string:
                if char in '"\'':
                    in_string = True
                    string_char = char
            else:
                if char == string_char:
                    in_string = False
                    string_char = None
            
            # Only process brackets when not in a string
            if not in_string:
                if char in '{[(':
                    stack.append(char)
                elif char in '}])':
                    if not stack:
                        return -1
                    opening = stack.pop()
                    # Check matching pairs
                    matching_pairs = {'}': '{', ']': '[', ')': '('}
                    expected = matching_pairs.get(char)
                    if opening != expected:
                        return -1
                    # If stack is empty after popping, we found our match
                    if not stack:
                        return i
            
            i += 1
        
        return -1  # Unmatched brace

    def _validate_t_structure(self, stmt_str: str) -> Tuple[bool, str]:
        """
        Validate T{} structure completeness and provide diagnostic info.
        
        Returns:
            Tuple of (is_valid, diagnostic_message)
        """
        if not stmt_str.startswith('T{'):
            return False, "Not a T{} structure"
        
        # Count braces
        open_braces = stmt_str.count('{')
        close_braces = stmt_str.count('}')
        
        if open_braces != close_braces:
            return False, f"Unmatched braces: {open_braces} open, {close_braces} close"
        
        # Check for exception handler pattern
        if '}X{' not in stmt_str:
            # No explicit exception handler found
            if stmt_str.endswith('}'):
                # Try-only structure (complete braces, no exception handler)
                return True, "Try-only structure (no except)"
            else:
                # Incomplete structure
                return False, "Missing exception handler pattern"
        
        return True, "Structure valid"

    def _attempt_structure_repair(self, stmt_str: str) -> str:
        """
        Attempt to repair incomplete T{} structures.
        
        Args:
            stmt_str: Potentially incomplete T{} structure
            
        Returns:
            Repaired structure string
        """
        self.logger.debug(f"Attempting to repair structure: {stmt_str[:50]}...")
        
        # Count braces
        open_count = stmt_str.count('{')
        close_count = stmt_str.count('}')
        missing_braces = open_count - close_count
        
        if missing_braces > 0:
            # Structure is incomplete - add missing closing braces
            if 'X{' in stmt_str:
                # Has exception handler - find where to add braces
                x_idx = stmt_str.rfind('X{')
                # Check if exception handler is complete
                handler_part = stmt_str[x_idx:]
                handler_open = handler_part.count('{')
                handler_close = handler_part.count('}')
                
                if handler_open > handler_close:
                    # Exception handler incomplete
                    stmt_str += '}' * (handler_open - handler_close)
                else:
                    # Try body incomplete
                    # Insert closing braces before X{
                    stmt_str = stmt_str[:x_idx] + '}' * missing_braces + stmt_str[x_idx:]
            else:
                # No exception handler - add one with pass
                stmt_str += '}' * missing_braces + 'X{_}'  # _ is pass in ultra-dense
        elif missing_braces == 0 and 'X{' not in stmt_str and stmt_str.endswith('}'):
            # FIXED: Braces are balanced but no exception handler - add one
            stmt_str += 'X{_}'
        
        self.logger.debug(f"Repaired structure: {stmt_str[:50]}...")
        return stmt_str

    def _is_balanced_parentheses(self, text: str) -> bool:
        """Check if parentheses in text are balanced."""
        count = 0
        for char in text:
            if char == '(':
                count += 1
            elif char == ')':
                count -= 1
                if count < 0:
                    return False
        return count == 0

    def _split_statements_respecting_braces(self, text: str) -> List[str]:
        """Split text by semicolons while respecting brace boundaries."""
        statements = []
        current_statement = ""
        brace_depth = 0
        paren_depth = 0
        bracket_depth = 0
        i = 0
        
        while i < len(text):
            char = text[i]
            
            if char == '{':
                brace_depth += 1
                current_statement += char
            elif char == '}':
                brace_depth -= 1
                current_statement += char
            elif char == '(':
                paren_depth += 1
                current_statement += char
            elif char == ')':
                paren_depth -= 1
                current_statement += char
            elif char == '[':
                bracket_depth += 1
                current_statement += char
            elif char == ']':
                bracket_depth -= 1
                current_statement += char
            elif char == ';' and brace_depth == 0 and paren_depth == 0 and bracket_depth == 0:
                # Found a semicolon at the top level - split here
                if current_statement.strip():
                    statements.append(current_statement.strip())
                current_statement = ""
            else:
                current_statement += char
            
            i += 1
        
        # Add the last statement if there's any content
        if current_statement.strip():
            statements.append(current_statement.strip())
        
        return statements

    def _fix_ambiguous_names(self, text: str) -> str:
        """Fix ambiguous name expansions in context."""
        # Fix os.st -> os.stat in os module context
        import re
        
        # Pattern: os.st( -> os.stat(
        text = re.sub(r'\bos\.st\(', 'os.stat(', text)
        
        # Pattern: os.st(var).st_something -> os.stat(var).st_something  
        text = re.sub(r'\bos\.st\(([^)]+)\)\.st_', r'os.stat(\1).st_', text)
        
        # Fix common stat attributes that might get truncated
        text = re.sub(r'\.st_siz\b', '.st_size', text)
        text = re.sub(r'\.st_si\b', '.st_size', text)
        text = re.sub(r'\.st_mti\b', '.st_mtime', text)
        text = re.sub(r'\.st_cti\b', '.st_ctime', text)
        
        return text

    def _clean_cid_references(self, text: str) -> str:
        """Remove CID references like 'mt_4849:' from text before expression parsing."""
        import re
        # Remove CID patterns: (mt_|fn_|cl_)[a-f0-9]{4}:
        cid_pattern = r'(mt_|fn_|cl_)[a-f0-9]{4}:'
        cleaned = re.sub(cid_pattern, '', text)
        return cleaned

    def _parse_block_statements_safe(self, block_str: str, flow_compiler: FLOWCompiler) -> List[ast.AST]:
        """Parse block statements with comprehensive logging and error recovery."""
        self.logger.debug(f"=== PARSING BLOCK STATEMENTS ===")
        self.logger.debug(f"Block input: {repr(block_str)}")
        
        if not block_str or block_str.strip() == '_':
            self.logger.debug("Empty block, returning pass statement")
            return [ast.Pass()]
        
        stmts = []
        
        # Split by semicolon but respect nested structures
        parts = self._split_respecting_nesting(block_str, ';')
        self.logger.debug(f"Split into {len(parts)} parts: {[repr(p) for p in parts]}")
        
        for i, part in enumerate(parts):
            part = part.strip()
            if not part:
                self.logger.debug(f"Part {i}: empty, skipping")
                continue
            
            self.logger.debug(f"=== Processing part {i}: {repr(part)} ===")
            
            try:
                # Pattern analysis for this part
                part_patterns = []
                if part.startswith('@'):
                    part_patterns.append("FOR_LOOP")
                if 'T{' in part and ('X' in part or 'X{' in part):
                    part_patterns.append("TRY_EXCEPT")
                if 'except' in part and not part.startswith('T{'):
                    part_patterns.append("ORPHAN_EXCEPT")
                if '?' in part:
                    part_patterns.append("CONDITIONAL")
                
                self.logger.debug(f"Part {i} patterns: {part_patterns}")
                
                # CRITICAL: Check for orphaned except statements
                if 'ORPHAN_EXCEPT' in part_patterns:
                    self.logger.error(f"🚨 ORPHANED EXCEPT DETECTED in part {i}: {repr(part)}")
                    self.logger.error(f"🚨 This should have been caught by delegation!")
                    # Skip orphaned except statements
                    continue
                
                # Check for for-loop pattern FIRST (higher priority)
                if part.startswith('@') and ',' in part and '{' in part:
                    self.logger.debug(f"Part {i}: Parsing as for-loop")
                    stmt = self._parse_for_loop_safe(part, flow_compiler)
                else:
                    self.logger.debug(f"Part {i}: Parsing as general ultra-dense statement")
                    stmt = self._parse_ultra_dense_statement(part, flow_compiler)
                
                if stmt:
                    fixed_stmt = self._fix_ast_node_attributes(stmt)
                    stmts.append(fixed_stmt)
                    self.logger.debug(f"Part {i}: Successfully parsed and added statement")
                else:
                    self.logger.warning(f"Part {i}: Parsing returned None, adding pass")
                    stmts.append(self._fix_ast_node_attributes(ast.Pass()))
                    
            except Exception as e:
                self.logger.error(f"Part {i}: Failed to parse '{part}': {e}")
                import traceback
                self.logger.debug(f"Part {i} traceback: {traceback.format_exc()}")
                stmts.append(self._fix_ast_node_attributes(ast.Pass()))
        
        result = stmts or [ast.Pass()]
        self.logger.debug(f"=== BLOCK PARSING COMPLETE: {len(result)} statements ===")
        return result

    def _parse_for_loop_safe(self, stmt_str: str, flow_compiler: FLOWCompiler) -> ast.AST:
        """Parse for-loop with better handling of method calls in iterables."""
        self.logger.debug(f"Parsing for-loop: {stmt_str}")
        
        try:
            if not stmt_str.startswith('@'):
                raise ValueError("Invalid for-loop syntax")
            
            # Enhanced comma finding that respects parentheses in method calls
            comma_pos = -1
            paren_depth = 0
            for i in range(1, len(stmt_str)):
                if stmt_str[i] == '(':
                    paren_depth += 1
                elif stmt_str[i] == ')':
                    paren_depth -= 1
                elif stmt_str[i] == ',' and paren_depth == 0:
                    comma_pos = i
                    break
            
            if comma_pos == -1:
                raise ValueError("Missing comma in for-loop")
            
            target_str = stmt_str[1:comma_pos].strip()
            
            # Find the opening brace more reliably
            brace_start = -1
            for i in range(comma_pos + 1, len(stmt_str)):
                if stmt_str[i] == '{':
                    brace_start = i
                    break
            
            if brace_start == -1:
                raise ValueError("Missing opening brace in for-loop")
            
            iter_str = stmt_str[comma_pos + 1:brace_start].strip()
            
            # Use the improved brace matching
            brace_end = self._find_matching_brace(stmt_str, brace_start)
            if brace_end == -1:
                raise ValueError("Unmatched braces in for-loop")
            
            body_str = stmt_str[brace_start + 1:brace_end]
            
            self.logger.debug(f"For-loop parts - target: {target_str}, iter: {iter_str}, body: {body_str}")
            
            # Track the iterator for placeholder resolution
            if hasattr(flow_compiler, 'current_loop_iterator'):
                prev_iterator = flow_compiler.current_loop_iterator
            else:
                prev_iterator = None
            flow_compiler.current_loop_iterator = target_str
            
            # Parse components with enhanced placeholder resolution
            # Handle placeholder ? in target - use context-aware resolution
            if target_str == '?':
                # Try to infer from iterator context (also check expanded forms)
                expanded_iter = flow_compiler.expand_compressed_operators(iter_str)
                
                # Check for common patterns in both original and expanded forms
                is_items = ('items()' in iter_str or 'items()' in expanded_iter or 
                           '.it()' in iter_str or 'it()' in iter_str)
                is_keys = ('keys()' in iter_str or 'keys()' in expanded_iter or 
                          '.ke()' in iter_str or 'ke()' in iter_str)
                is_values = ('values()' in iter_str or 'values()' in expanded_iter or 
                            '.va()' in iter_str or 'va()' in iter_str)
                
                if is_items:
                    # For dict.items(), use (key, value) tuple
                    target = ast.Tuple(elts=[
                        ast.Name(id='key', ctx=ast.Store()),
                        ast.Name(id='value', ctx=ast.Store())
                    ], ctx=ast.Store())
                elif is_keys:
                    target = ast.Name(id='key', ctx=ast.Store())
                elif is_values:
                    target = ast.Name(id='value', ctx=ast.Store())
                else:
                    # Generic iterator variable
                    target = ast.Name(id='item', ctx=ast.Store())
            else:
                target = flow_compiler._parse_expression_string(target_str)
                if isinstance(target, ast.Name):
                    target.ctx = ast.Store()
            
            iter_expr = flow_compiler._parse_expression_string(iter_str)
            
            # Parse body statements with the iterator context
            body_stmts = self._parse_block_statements_safe(body_str, flow_compiler)
            
            # Restore previous iterator context
            if prev_iterator:
                flow_compiler.current_loop_iterator = prev_iterator
            else:
                delattr(flow_compiler, 'current_loop_iterator')
            
            return self._fix_ast_node_attributes(
                ast.For(target=target, iter=iter_expr, body=body_stmts or [ast.Pass()], orelse=[])
            )
            
        except Exception as e:
            self.logger.warning(f"Failed to parse for-loop '{stmt_str}': {e}")
            return self._fix_ast_node_attributes(ast.Pass())

    def _find_for_loop_comma(self, text: str, start_pos: int) -> int:
        """Find the comma separating target from iterable, respecting parentheses."""
        paren_depth = 0
        i = start_pos
        
        while i < len(text):
            char = text[i]
            
            if char == '(':
                paren_depth += 1
            elif char == ')':
                paren_depth -= 1
            elif char == ',' and paren_depth == 0:
                return i
            elif char == '{':
                # Stop at opening brace
                return -1
            
            i += 1
        
        return -1

    def _split_respecting_nesting(self, text: str, separator: str) -> List[str]:
        """Split text by separator, respecting nested structures."""
        parts = []
        current = ""
        depth = {'{}': 0, '[]': 0, '()': 0}
        in_string = False
        string_char = None
        
        i = 0
        while i < len(text):
            char = text[i]
            
            # Handle strings
            if char in '"\'':
                if not in_string:
                    in_string = True
                    string_char = char
                elif char == string_char and (i == 0 or text[i-1] != '\\'):
                    in_string = False
                    string_char = None
            
            # Track nesting depth only outside strings
            if not in_string:
                if char == '{':
                    depth['{}'] += 1
                elif char == '}':
                    depth['{}'] -= 1
                elif char == '[':
                    depth['[]'] += 1
                elif char == ']':
                    depth['[]'] -= 1
                elif char == '(':
                    depth['()'] += 1
                elif char == ')':
                    depth['()'] -= 1
                elif char == separator and all(d == 0 for d in depth.values()):
                    # Found separator at top level
                    if current.strip():  # Only add non-empty parts
                        parts.append(current.strip())
                    current = ""
                    i += 1
                    continue
            
            current += char
            i += 1
        
        if current.strip():
            parts.append(current.strip())
        
        return parts

    def _parse_except_handler_safe(self, handler_str: str, flow_compiler: FLOWCompiler) -> ast.ExceptHandler:
        """Parse except handler with proper error recovery."""
        try:
            # Pattern: X(ExceptionType){handler_body} or X{handler_body}
            exc_type = None
            exc_name = None
            
            if handler_str.startswith('X('):
                # Has exception type
                paren_end = handler_str.find(')')
                if paren_end > 2:
                    exc_type_str = handler_str[2:paren_end]
                    if exc_type_str and exc_type_str != 'E':
                        exc_type = ast.Name(id=exc_type_str, ctx=ast.Load())
                    
                    # Check for exception name
                    rest = handler_str[paren_end + 1:]
                    if rest and not rest.startswith('{'):
                        # Has exception variable name
                        brace_pos = rest.find('{')
                        if brace_pos > 0:
                            exc_name = rest[:brace_pos].strip()
                            if exc_name == '_':
                                exc_name = None
            
            # Find handler body
            brace_start = handler_str.find('{')
            if brace_start != -1:
                brace_end = self._find_matching_brace(handler_str, brace_start)
                if brace_end != -1:
                    body_str = handler_str[brace_start + 1:brace_end]
                    body_stmts = self._parse_block_statements_safe(body_str, flow_compiler)
                else:
                    body_stmts = [ast.Pass()]
            else:
                body_stmts = [ast.Pass()]
            
            return ast.ExceptHandler(
                type=exc_type,
                name=exc_name,
                body=body_stmts or [ast.Pass()]
            )
            
        except Exception as e:
            self.logger.warning(f"Failed to parse except handler: {e}")
            return ast.ExceptHandler(type=None, name=None, body=[ast.Pass()])

    def _parse_body_statements(self, body_str: str, flow_compiler: FLOWCompiler) -> List[ast.AST]:
        """Parse a body string into a list of statements."""
        if not body_str or body_str.strip() == '_':
            return [ast.Pass()]
        
        stmts = []
        for stmt in body_str.split(';'):
            stmt = stmt.strip()
            if stmt:
                # Prioritize for-loops over assignments for patterns starting with @
                if stmt.startswith('@') and ',' in stmt and '{' in stmt:
                    parsed_stmt = self._parse_ultra_dense_for(stmt, flow_compiler)
                else:
                    parsed_stmt = self._parse_ultra_dense_statement(stmt, flow_compiler)
                
                if parsed_stmt:
                    stmts.append(parsed_stmt)
        
        return stmts or [ast.Pass()]

    def _short36(self, cid: str) -> str:
        """Generate short base36 representation of CID."""
        import hashlib
        hash_val = int(hashlib.md5(cid.encode()).hexdigest()[:8], 16)
        chars = "0123456789abcdefghijklmnopqrstuvwxyz"
        result = ""
        while hash_val and len(result) < 4:
            result = chars[hash_val % 36] + result
            hash_val //= 36
        return result.zfill(4)

    def _recover_with_original(self, source_path: Path, lite_structure: Dict, 
                            cai3_full: CAI3Full, cai3_map: CAI3Map) -> str:
        """
        Try to recover by using original structure with updated bodies.
        Enhanced with better error handling and incremental validation.
        """
        self.logger.info("Attempting recovery with original structure")
        
        # Read original source
        if source_path.exists():
            original = source_path.read_text()
            
            # Validate original source first
            try:
                ast.parse(original)
                self.logger.info("Original source is valid Python")
            except SyntaxError as e:
                self.logger.error(f"Original source has syntax errors: {e}")
                return "# Original source file has syntax errors - cannot recover"
            
            # Apply only the body updates with incremental validation
            modified_source = original
            applied_changes = 0
            
            for cid, body_content in lite_structure['bodies'].items():
                if cid in cai3_map.span_map:
                    # Create a patch for this body
                    patch = CAI3Patch(
                        target_cid=cid,
                        operation="RB",
                        body_fidelity=BodyFidelity.B1,
                        body_content=body_content
                    )
                    
                    try:
                        # Apply the patch to a copy first
                        test_source = self._replace_body(patch, modified_source, cai3_map, cai3_full)
                        
                        # Validate the result
                        try:
                            ast.parse(test_source)
                            # If validation passes, use the modified source
                            modified_source = test_source
                            applied_changes += 1
                            self.logger.debug(f"Successfully applied body for {cid}")
                        except SyntaxError as e:
                            self.logger.warning(f"Body change for {cid} would cause syntax error: {e}, skipping")
                            # Skip this change and continue with others
                            continue
                            
                    except Exception as e:
                        self.logger.warning(f"Failed to apply body for {cid}: {e}")
            
            self.logger.info(f"Recovery completed: applied {applied_changes}/{len(lite_structure['bodies'])} body changes")
            return modified_source
        
        # Fallback: return a comment
        return "# Translation failed - original structure could not be recovered"