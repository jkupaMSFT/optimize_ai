#!/usr/bin/env python3
"""
Semantic-Aware Compression Engine
Balances token efficiency with semantic similarity preservation using intelligent compression strategies.
"""

import ast
import re
import json
import difflib
from typing import Dict, List, Tuple, Any, Optional
from dataclasses import dataclass
from pathlib import Path
import sys

# Add project root to path
project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

from utils.logger import estimate_tokens

@dataclass
class SourceMapping:
    """Maps compressed tokens back to original source locations"""
    original_line: int
    original_col: int
    compressed_line: int
    compressed_col: int
    original_text: str
    compressed_text: str
    compression_type: str

class SemanticAwareCompressionEngine:
    """
    Advanced compression engine that maintains semantic similarity while maximizing token efficiency.
    Uses source mapping to enable reversibility and semantic preservation.
    """
    
    def __init__(self, similarity_threshold: float = 0.7):
        self.similarity_threshold = similarity_threshold
        self.source_map: List[SourceMapping] = []
        self.compression_stats = {}
        
    def compress(self, code: str, preserve_semantics: bool = True) -> Dict[str, Any]:
        """
        Apply comprehensive compression strategies with semantic awareness
        Compression aggressiveness adapts based on similarity threshold
        """
        self.source_map.clear()
        original_tokens = estimate_tokens(code)
        current_code = code
        
        # Determine compression aggressiveness based on threshold
        # Lower threshold = more aggressive compression allowed
        compression_level = self._get_compression_level()
        
        stage_results = {}
        
        # Stage 1: AST-aware identifier compression (always apply conservatively)
        stage1_result = self._compress_identifiers_smartly(current_code)
        similarity_after_stage1 = self._calculate_similarity(code, stage1_result['code'])
        
        if similarity_after_stage1 >= self.similarity_threshold:
            current_code = stage1_result['code']
            stage_results['stage1_identifiers'] = stage1_result
        else:
            stage_results['stage1_identifiers'] = {'code': current_code, 'tokens_saved': 0, 'skipped': True}
        
        # Stage 2: Structural optimization (apply based on compression level)
        if compression_level >= 2:
            stage2_result = self._optimize_structure_semantically(current_code)
            similarity_after_stage2 = self._calculate_similarity(code, stage2_result['code'])
            
            if similarity_after_stage2 >= self.similarity_threshold:
                current_code = stage2_result['code']
                stage_results['stage2_structure'] = stage2_result
            else:
                stage_results['stage2_structure'] = {'code': current_code, 'tokens_saved': 0, 'skipped': True}
        else:
            stage_results['stage2_structure'] = {'code': current_code, 'tokens_saved': 0, 'skipped_level': True}
        
        # Stage 3: Context-aware reduction (apply if more aggressive compression allowed)
        if compression_level >= 3:
            stage3_result = self._reduce_tokens_contextually(current_code)
            similarity_after_stage3 = self._calculate_similarity(code, stage3_result['code'])
            
            if similarity_after_stage3 >= self.similarity_threshold:
                current_code = stage3_result['code']
                stage_results['stage3_context'] = stage3_result
            else:
                stage_results['stage3_context'] = {'code': current_code, 'tokens_saved': 0, 'skipped': True}
        else:
            stage_results['stage3_context'] = {'code': current_code, 'tokens_saved': 0, 'skipped_level': True}
        
        # Stage 4: Whitespace optimization (safe for most thresholds)
        if compression_level >= 1:
            stage4_result = self._optimize_whitespace_intelligently(current_code)
            similarity_after_stage4 = self._calculate_similarity(code, stage4_result['code'])
            
            if similarity_after_stage4 >= self.similarity_threshold:
                current_code = stage4_result['code']
                stage_results['stage4_whitespace'] = stage4_result
            else:
                stage_results['stage4_whitespace'] = {'code': current_code, 'tokens_saved': 0, 'skipped': True}
        else:
            stage_results['stage4_whitespace'] = {'code': current_code, 'tokens_saved': 0, 'skipped_level': True}
        
        # Stage 5: Semantic notation (only for very low thresholds)
        if compression_level >= 4:
            stage5_result = self._apply_semantic_notation(current_code)
            similarity_after_stage5 = self._calculate_similarity(code, stage5_result['code'])
            
            if similarity_after_stage5 >= self.similarity_threshold:
                current_code = stage5_result['code']
                stage_results['stage5_notation'] = stage5_result
            else:
                stage_results['stage5_notation'] = {'code': current_code, 'tokens_saved': 0, 'skipped': True}
        else:
            stage_results['stage5_notation'] = {'code': current_code, 'tokens_saved': 0, 'skipped_level': True}
        
        # Calculate final metrics
        final_similarity = self._calculate_similarity(code, current_code)
        final_tokens = estimate_tokens(current_code)
        
        # If compressed version is significantly larger, revert to original
        # Allow small increases if similarity is maintained well
        token_increase_threshold = max(2, original_tokens * 0.05)  # Allow 5% increase or 2 tokens, whichever is larger
        if final_tokens > original_tokens + token_increase_threshold:
            current_code = code
            final_tokens = original_tokens
            final_similarity = 1.0
        
        compression_ratio = (original_tokens - final_tokens) / original_tokens if original_tokens > 0 else 0
        # Ensure compression ratio is never negative
        compression_ratio = max(0, compression_ratio)
        
        return {
            'original_code': code,
            'compressed_code': current_code,
            'original_tokens': original_tokens,
            'compressed_tokens': final_tokens,
            'tokens_saved': original_tokens - final_tokens,
            'compression_ratio': compression_ratio,
            'compression_percentage': compression_ratio * 100,
            'similarity_score': final_similarity,
            'compression_level': compression_level,
            'source_map': self.source_map,
            'stage_results': stage_results,
            'meets_threshold': final_similarity >= self.similarity_threshold
        }
    
    def _get_compression_level(self) -> int:
        """
        Determine compression aggressiveness based on similarity threshold
        Returns compression level from 1 (conservative) to 5 (aggressive)
        """
        if self.similarity_threshold >= 0.8:
            return 1  # Very conservative - only whitespace
        elif self.similarity_threshold >= 0.7:
            return 2  # Conservative - whitespace + structure
        elif self.similarity_threshold >= 0.6:
            return 3  # Moderate - add context reduction
        elif self.similarity_threshold >= 0.4:
            return 4  # Aggressive - add semantic notation
        else:
            return 5  # Very aggressive - all optimizations
    
    def _compress_identifiers_smartly(self, code: str) -> Dict[str, Any]:
        """
        Stage 1: Intelligent identifier compression using AST analysis
        """
        try:
            tree = ast.parse(code)
            identifier_map = {}
            used_short_names = set()
            original_tokens = estimate_tokens(code)
            
            # Analyze identifier usage frequency and scope
            identifier_stats = self._analyze_identifier_usage(tree)
            
            # Create smart mappings based on frequency and semantic importance
            potential_savings = 0
            for identifier, stats in identifier_stats.items():
                # More lenient criteria for compression
                if stats['frequency'] >= 2 and not self._is_semantic_critical(identifier) and len(identifier) > 8:
                    # Only compress very long identifiers that appear multiple times
                    short_name = self._generate_unique_short_name(identifier, stats, used_short_names)
                    if len(short_name) < len(identifier):
                        # Calculate potential savings
                        potential_savings += (len(identifier) - len(short_name)) * stats['frequency']
                        identifier_map[identifier] = short_name
                        used_short_names.add(short_name)
            
            # Only apply compression if it saves some tokens
            if potential_savings < 1:
                return {'code': code, 'identifier_map': {}, 'tokens_saved': 0, 'compression_ratio': 0}
                
            # Apply mappings while preserving semantic context
            compressed_code = self._apply_identifier_mappings(code, identifier_map)
            
            # Verify compression actually helps
            compressed_tokens = estimate_tokens(compressed_code)
            if compressed_tokens >= original_tokens:
                return {'code': code, 'identifier_map': {}, 'tokens_saved': 0, 'compression_ratio': 0}
            
            return {
                'code': compressed_code,
                'identifier_map': identifier_map,
                'tokens_saved': original_tokens - compressed_tokens,
                'compression_ratio': 1 - (len(compressed_code) / len(code)) if len(code) > 0 else 0
            }
            
        except SyntaxError:
            return {'code': code, 'identifier_map': {}, 'tokens_saved': 0, 'compression_ratio': 0}
    
    def _analyze_identifier_usage(self, tree: ast.AST) -> Dict[str, Dict]:
        """Analyze identifier usage patterns for smart compression"""
        stats = {}
        
        class IdentifierAnalyzer(ast.NodeVisitor):
            def visit_Name(self, node):
                name = node.id
                if name not in stats:
                    stats[name] = {
                        'frequency': 0,
                        'contexts': [],
                        'is_function': False,
                        'is_class': False,
                        'is_variable': False,
                        'scope_depth': 0
                    }
                stats[name]['frequency'] += 1
                stats[name]['contexts'].append(type(node.ctx).__name__)
                self.generic_visit(node)
            
            def visit_FunctionDef(self, node):
                if node.name not in stats:
                    stats[node.name] = {'frequency': 0, 'contexts': [], 'is_function': True}
                stats[node.name]['frequency'] += 1  # Count the function definition
                stats[node.name]['is_function'] = True
                self.generic_visit(node)
            
            def visit_ClassDef(self, node):
                if node.name not in stats:
                    stats[node.name] = {'frequency': 0, 'contexts': [], 'is_class': True}
                stats[node.name]['frequency'] += 1  # Count the class definition
                stats[node.name]['is_class'] = True
                self.generic_visit(node)
        
        IdentifierAnalyzer().visit(tree)
        return stats
    
    def _is_semantic_critical(self, identifier: str) -> bool:
        """Determine if an identifier is semantically critical and shouldn't be compressed"""
        critical_patterns = [
            r'^__\w+__$',  # Magic methods
            r'^[A-Z][A-Z_]+$',  # Constants
            r'(main|init|enter|exit)$',  # Critical methods
        ]
        
        # Built-in or standard library indicators
        if identifier in ['self', 'cls', 'args', 'kwargs', 'super', 'len', 'range', 'enumerate']:
            return True
            
        return any(re.match(pattern, identifier) for pattern in critical_patterns)
    
    def _generate_smart_short_name(self, identifier: str, stats: Dict) -> str:
        """Generate intelligent short names based on context and frequency"""
        
        # High frequency -> very short names
        if stats['frequency'] > 10:
            return self._get_ultra_short_name(identifier)
        elif stats['frequency'] > 5:
            return self._get_short_name(identifier)
        else:
            return self._get_abbreviated_name(identifier)
    
    def _generate_unique_short_name(self, identifier: str, stats: Dict, used_names: set) -> str:
        """Generate unique short names to avoid collisions"""
        base_name = self._generate_smart_short_name(identifier, stats)
        
        if base_name not in used_names:
            return base_name
        
        # Generate variations to ensure uniqueness
        for i in range(1, 10):
            candidate = f"{base_name}{i}"
            if candidate not in used_names:
                return candidate
        
        # Fallback to a numbered version based on first few characters
        base = identifier[:3].lower()
        for i in range(1, 100):
            candidate = f"{base}{i}"
            if candidate not in used_names:
                return candidate
        
        # Last resort
        return identifier[:4]
    
    def _get_ultra_short_name(self, identifier: str) -> str:
        """Generate ultra-short names for high-frequency identifiers"""
        # Use vowel removal + first consonant pattern
        consonants = ''.join(c for c in identifier if c.lower() not in 'aeiou')
        if len(consonants) >= 2:
            return consonants[:2].lower()
        return identifier[:2].lower()
    
    def _get_short_name(self, identifier: str) -> str:
        """Generate short but recognizable names"""
        # Camel case abbreviation
        if '_' in identifier:
            parts = identifier.split('_')
            return ''.join(part[0] for part in parts if part)
        elif any(c.isupper() for c in identifier[1:]):
            # CamelCase
            return ''.join(c for c in identifier if c.isupper()).lower()
        else:
            return identifier[:3]
    
    def _get_abbreviated_name(self, identifier: str) -> str:
        """Generate abbreviated but still readable names"""
        if len(identifier) <= 4:
            return identifier
        
        # Smart vowel removal
        result = identifier[0]  # Keep first character
        for i, c in enumerate(identifier[1:], 1):
            if c.lower() not in 'aeiou' or i == len(identifier) - 1:
                result += c
            if len(result) >= 4:
                break
        
        return result
    
    def _apply_identifier_mappings(self, code: str, identifier_map: Dict[str, str]) -> str:
        """Apply identifier mappings to code using AST transformation for accuracy"""
        if not identifier_map:
            return code
        
        try:
            tree = ast.parse(code)
            
            class IdentifierReplacer(ast.NodeTransformer):
                def visit_Name(self, node):
                    if node.id in identifier_map:
                        node.id = identifier_map[node.id]
                    return node
                
                def visit_FunctionDef(self, node):
                    # Replace function name
                    if node.name in identifier_map:
                        node.name = identifier_map[node.name]
                    
                    # Replace parameter names
                    for arg in node.args.args:
                        if arg.arg in identifier_map:
                            arg.arg = identifier_map[arg.arg]
                    
                    return self.generic_visit(node)
                
                def visit_ClassDef(self, node):
                    if node.name in identifier_map:
                        node.name = identifier_map[node.name]
                    return self.generic_visit(node)
            
            transformed_tree = IdentifierReplacer().visit(tree)
            return ast.unparse(transformed_tree)
        except:
            # Fallback to regex replacement if AST transformation fails
            for old_name, new_name in identifier_map.items():
                pattern = r'\b' + re.escape(old_name) + r'\b'
                code = re.sub(pattern, new_name, code)
            return code
    
    def _optimize_structure_semantically(self, code: str) -> Dict[str, Any]:
        """
        Stage 2: Optimize code structure while preserving semantics
        """
        optimizations = [
            self._compress_docstrings_smartly,
            self._optimize_imports,
            self._compress_comments_contextually,
            self._optimize_string_literals,
            self._compress_type_hints,
        ]
        
        optimized_code = code
        total_savings = 0
        
        for optimization in optimizations:
            result = optimization(optimized_code)
            optimized_code = result['code']
            total_savings += result.get('tokens_saved', 0)
        
        return {
            'code': optimized_code,
            'tokens_saved': total_savings,
            'compression_ratio': 1 - (len(optimized_code) / len(code)) if len(code) > 0 else 0
        }
    
    def _compress_docstrings_smartly(self, code: str) -> Dict[str, Any]:
        """Compress docstrings while preserving essential information"""
        try:
            tree = ast.parse(code)
            
            class DocstringCompressor(ast.NodeTransformer):
                def visit_FunctionDef(self, node):
                    if (node.body and isinstance(node.body[0], ast.Expr) 
                        and isinstance(node.body[0].value, ast.Constant)):
                        
                        docstring = node.body[0].value.value
                        if isinstance(docstring, str):
                            # Compress docstring intelligently
                            compressed = self._compress_docstring_content(docstring)
                            node.body[0].value.value = compressed
                    
                    return self.generic_visit(node)
                
                def _compress_docstring_content(self, docstring: str) -> str:
                    # Extract essential information only
                    lines = docstring.strip().split('\n')
                    
                    # Keep first line (summary) if it's meaningful
                    summary = lines[0].strip()
                    if len(summary) > 100:
                        summary = summary[:97] + "..."
                    
                    # Extract Args/Returns sections in compressed form
                    compressed_parts = [summary]
                    
                    current_section = None
                    for line in lines[1:]:
                        line = line.strip()
                        if line.startswith(('Args:', 'Arguments:', 'Parameters:')):
                            current_section = 'args'
                            compressed_parts.append('Args:')
                        elif line.startswith(('Returns:', 'Return:')):
                            current_section = 'returns'
                            compressed_parts.append('Ret:')
                        elif current_section and line and not line.startswith(' '):
                            # End of section
                            current_section = None
                        elif current_section and line:
                            # Compress parameter descriptions
                            if ':' in line:
                                param, desc = line.split(':', 1)
                                compressed_parts.append(f"{param.strip()}: {desc.strip()[:30]}")
                    
                    return '\n'.join(compressed_parts)
            
            compressed_tree = DocstringCompressor().visit(tree)
            compressed_code = ast.unparse(compressed_tree)
            
            return {
                'code': compressed_code,
                'tokens_saved': estimate_tokens(code) - estimate_tokens(compressed_code)
            }
            
        except:
            return {'code': code, 'tokens_saved': 0}
    
    def _optimize_imports(self, code: str) -> Dict[str, Any]:
        """Optimize import statements for token efficiency"""
        lines = code.split('\n')
        optimized_lines = []
        
        import_aliases = {
            'import math': 'import math as m',
            'import statistics': 'import statistics as s',
            'import datetime': 'import datetime as dt',
            'import collections': 'import collections as c',
        }
        
        for line in lines:
            stripped = line.strip()
            
            # Apply import optimizations
            original_line = line
            for old_import, new_import in import_aliases.items():
                if stripped.startswith(old_import) and stripped == old_import:
                    line = line.replace(old_import, new_import)
                    break
            
            optimized_lines.append(line)
        
        optimized_code = '\n'.join(optimized_lines)
        
        return {
            'code': optimized_code,
            'tokens_saved': estimate_tokens(code) - estimate_tokens(optimized_code)
        }
    
    def _compress_comments_contextually(self, code: str) -> Dict[str, Any]:
        """Compress comments while preserving important information"""
        lines = code.split('\n')
        compressed_lines = []
        
        for line in lines:
            # Skip lines that are only comments for now (preserve inline comments)
            if line.strip().startswith('#') and len(line.strip()) > 50:
                # Compress long comments
                comment = line.strip()[1:].strip()
                if len(comment) > 30:
                    comment = comment[:27] + "..."
                compressed_lines.append(line[:line.find('#')] + f"# {comment}")
            else:
                compressed_lines.append(line)
        
        compressed_code = '\n'.join(compressed_lines)
        
        return {
            'code': compressed_code,
            'tokens_saved': estimate_tokens(code) - estimate_tokens(compressed_code)
        }
    
    def _optimize_string_literals(self, code: str) -> Dict[str, Any]:
        """Optimize string literals where possible"""
        # For now, just return as-is to avoid breaking functionality
        return {'code': code, 'tokens_saved': 0}
    
    def _compress_type_hints(self, code: str) -> Dict[str, Any]:
        """Compress type hints for better token efficiency"""
        # Common type hint abbreviations
        type_replacements = {
            'List[': 'L[',
            'Dict[': 'D[',
            'Tuple[': 'T[',
            'Optional[': 'O[',
            'Union[': 'U[',
            'Callable[': 'C[',
        }
        
        compressed_code = code
        for old_type, new_type in type_replacements.items():
            compressed_code = compressed_code.replace(old_type, new_type)
        
        return {
            'code': compressed_code,
            'tokens_saved': estimate_tokens(code) - estimate_tokens(compressed_code)
        }
    
    def _reduce_tokens_contextually(self, code: str) -> Dict[str, Any]:
        """
        Stage 3: Context-aware token reduction (more conservative)
        """
        original_tokens = estimate_tokens(code)
        
        # More conservative replacements to avoid increasing tokens
        context_replacements = {
            # Mathematical contexts (only if they actually save tokens)
            r'\bmath\.pi\b': 'π',
            r'\bmath\.e\b': 'ℯ',
            
            # Boolean contexts (conservative)
            r'\bTrue\b': '⊤',
            r'\bFalse\b': '⊥',
            r'\bNone\b': '∅',
        }
        
        optimized_code = code
        
        # Apply each replacement only if it reduces tokens
        for pattern, replacement in context_replacements.items():
            test_code = re.sub(pattern, replacement, optimized_code)
            if estimate_tokens(test_code) < estimate_tokens(optimized_code):
                optimized_code = test_code
        
        return {
            'code': optimized_code,
            'tokens_saved': original_tokens - estimate_tokens(optimized_code)
        }
    
    def _optimize_whitespace_intelligently(self, code: str) -> Dict[str, Any]:
        """
        Stage 4: Intelligent whitespace optimization that preserves readability
        """
        original_tokens = estimate_tokens(code)
        lines = code.split('\n')
        optimized_lines = []
        
        for line in lines:
            if not line.strip():
                continue  # Remove empty lines
            
            # Preserve indentation but minimize
            indent_match = re.match(r'^(\s*)', line)
            if indent_match:
                indent = indent_match.group(1)
                # Convert tabs to spaces and minimize to 2-space indentation
                indent = indent.replace('\t', '  ')
                # Reduce to 2-space indentation
                indent_level = len(indent) // 4
                minimal_indent = '  ' * indent_level
                line_content = line.lstrip()
                
                # Conservative whitespace optimization
                # Remove extra spaces around operators and brackets
                line_content = re.sub(r'\s*:\s*', ':', line_content)  # Remove spaces around colons
                line_content = re.sub(r'\s*,\s*', ',', line_content)  # Remove spaces around commas  
                line_content = re.sub(r'\s*\(\s*', '(', line_content)  # Remove spaces around opening parentheses
                line_content = re.sub(r'\s*\)\s*', ')', line_content)  # Remove spaces around closing parentheses
                line_content = re.sub(r'\s+', ' ', line_content)  # Collapse multiple spaces
                line_content = line_content.strip()
                
                line = minimal_indent + line_content
            
            optimized_lines.append(line)
        
        optimized_code = '\n'.join(optimized_lines)
        
        return {
            'code': optimized_code,
            'tokens_saved': original_tokens - estimate_tokens(optimized_code)
        }
    
    def _apply_semantic_notation(self, code: str) -> Dict[str, Any]:
        """
        Stage 5: Apply semantic mathematical/logical notation (very conservative)
        """
        original_tokens = estimate_tokens(code)
        
        # Conservative semantic replacements to maintain readability
        semantic_replacements = {
            # Boolean and logical replacements (apply even if neutral token count)
            r'\bTrue\b': '⊤',
            r'\bFalse\b': '⊥', 
            r'\bNone\b': '∅',
            
            # Mathematical constants and functions
            r'\bmath\.pi\b': 'π',
            r'\bmath\.e\b': 'ℯ',
            r'\.append\(': '⊕(',
            r'\blen\(': 'ł(',
        }
        
        optimized_code = code
        
        # Apply each replacement if it doesn't increase tokens significantly
        for pattern, replacement in semantic_replacements.items():
            test_code = re.sub(pattern, replacement, optimized_code)
            test_tokens = estimate_tokens(test_code)
            current_tokens = estimate_tokens(optimized_code)
            
            # Apply if tokens don't increase by more than 1 (allow neutral or slightly worse)
            if test_tokens <= current_tokens + 1:
                optimized_code = test_code
        
        return {
            'code': optimized_code,
            'tokens_saved': original_tokens - estimate_tokens(optimized_code)
        }
    
    def _calculate_similarity(self, original: str, compressed: str) -> float:
        """Calculate similarity between original and compressed code with improved accuracy"""
        
        # Basic string similarity
        sequence_matcher = difflib.SequenceMatcher(None, original, compressed)
        string_similarity = sequence_matcher.ratio()
        
        # Token-level similarity (more meaningful for code)
        original_tokens = re.findall(r'\w+|[^\w\s]', original)
        compressed_tokens = re.findall(r'\w+|[^\w\s]', compressed)
        
        token_matcher = difflib.SequenceMatcher(None, original_tokens, compressed_tokens)
        token_similarity = token_matcher.ratio()
        
        # Line structure similarity
        orig_lines = [line.strip() for line in original.splitlines() if line.strip()]
        comp_lines = [line.strip() for line in compressed.splitlines() if line.strip()]
        
        line_matcher = difflib.SequenceMatcher(None, orig_lines, comp_lines)
        line_similarity = line_matcher.ratio()
        
        # AST structure similarity (if both are valid Python)
        ast_similarity = 0.8  # Default high similarity if we can't parse
        try:
            original_ast = ast.dump(ast.parse(original))
            compressed_ast = ast.dump(ast.parse(compressed))
            
            ast_matcher = difflib.SequenceMatcher(None, original_ast, compressed_ast)
            ast_similarity = ast_matcher.ratio()
        except:
            # If parsing fails, use token similarity as fallback
            ast_similarity = token_similarity
        
        # Identifier preservation check
        orig_identifiers = set(re.findall(r'\b[a-zA-Z_][a-zA-Z0-9_]*\b', original))
        comp_identifiers = set(re.findall(r'\b[a-zA-Z_][a-zA-Z0-9_]*\b', compressed))
        
        if orig_identifiers:
            identifier_preservation = len(orig_identifiers & comp_identifiers) / len(orig_identifiers)
        else:
            identifier_preservation = 1.0
        
        # Weighted combination favoring structural preservation
        overall_similarity = (
            string_similarity * 0.15 +      # Basic string similarity
            token_similarity * 0.25 +       # Token-level similarity  
            line_similarity * 0.20 +        # Line structure similarity
            ast_similarity * 0.30 +         # AST structure (most important)
            identifier_preservation * 0.10  # Identifier preservation
        )
        
        return min(1.0, max(0.0, overall_similarity))

def create_compression_engine(similarity_threshold: float = 0.7) -> SemanticAwareCompressionEngine:
    """Factory function to create optimized compression pipeline"""
    return SemanticAwareCompressionEngine(similarity_threshold=similarity_threshold)
