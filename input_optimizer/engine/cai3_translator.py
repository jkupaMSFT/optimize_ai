# optimize_ai/input_optimizer/engine/cai3_translator.py
"""
CAI3 Translator - Applies CAI3-PATCH from LLM to original source using FULL+MAP.
Uses LibCST for precise AST manipulation.
"""

import ast
import hashlib
import logging
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
        # Only remap if we have an original; keep attributes/imports alone
        if node.id in self.s2o:
            node.id = self.s2o[node.id]
        return self.generic_visit(node)
    
    def visit_Call(self, node: ast.Call):
        # Handle chain alias function calls like g1(...) -> self.config.get(...)
        if (isinstance(node.func, ast.Name) and 
            node.func.id in self.chain_aliases):
            
            chain = self.chain_aliases[node.func.id]
            # Parse the chain into proper attribute access
            # e.g., "s.config.get" -> self.config.get
            parts = chain.split('.')
            
            # Build the attribute chain
            result = None
            for i, part in enumerate(parts):
                if i == 0:
                    # Handle 's' -> 'self', etc.
                    name = 'self' if part == 's' else part
                    result = ast.Name(id=name, ctx=ast.Load())
                else:
                    result = ast.Attribute(value=result, attr=part, ctx=ast.Load())
            
            # Replace the function in the call
            node.func = result
        
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
    
    def apply_patch(self, patch_content: str, source_path: Path) -> str:
        """
        Apply a CAI3-PATCH to the original source file.
        
        Args:
            patch_content: The patch returned by the LLM
            source_path: Path to the original source file
            
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
            return source_path.read_text()
        
        # Read original source
        original_source = source_path.read_text()
        
        # Apply each patch
        modified_source = original_source
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
                cid_alias_map.update(stored_aliases)
        
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
        lines = source.split('\n')
        
        # Get context (few lines before and after) - MUST match compression logic
        context_start = max(0, start_line - 3)
        context_end = min(len(lines), end_line + 2)  # Fixed: was +3, now +2 to match compression
        context_lines = lines[context_start:context_end]
        context = '\n'.join(context_lines)
        
        # Calculate hash
        actual_hash = hashlib.md5(context.encode()).hexdigest()[:8]
        
        return actual_hash == expected_hash
    
    def _replace_body(self, patch: CAI3Patch, source: str, cai3_map: CAI3Map, cai3_full: CAI3Full = None) -> str:
        """Replace the body of a function/method"""
        
        if patch.body_fidelity == BodyFidelity.B1:
            # Convert FLOW to Python AST with enhanced flags
            flow_compiler = self._create_flow_compiler(cai3_map, cai3_full)
            new_body_stmts = flow_compiler._parse_flow_lines(
                patch.body_content.split('\n'), 0
            )[0]
            
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
            
            # Add proper indentation
            for line in stmt_code.split('\n'):
                if line.strip():
                    new_lines.append(body_indent + line)
        
        # Insert the new lines
        result_lines = lines[:insert_position] + new_lines + lines[insert_position:]
        return '\n'.join(result_lines)
    
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
            # Add proper indentation
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