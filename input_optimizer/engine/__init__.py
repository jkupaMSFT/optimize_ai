"""
Input Optimizer Engine

Core engine components for text optimization including:
- Minification engine
- Translation engines (sudo-lang, synth-lang) 
- Source mapping and AST utilities
- Compression adapters
"""

# Import main engine components
from .minifier import minify_code, minify_with_stats, estimate_tokens, CompressionDepth
from .adapter import adapt_compression, CompressionResult

# Import translators
from .translators.sudo_lang_translator import python_to_sudolang, ast_to_sudolang
from .translators.synth_lang_translator import python_to_synthlang

# Import mapping utilities
from .mapping.ast_map import ASTMapper, walk_ast_and_map, MappedNode
from .mapping.source_map import SourceMap
from .mapping.source_map_production import ProductionSourceMap

# Define what gets imported with "from input_optimizer.engine import *"
__all__ = [
    # Minifier
    'minify_code', 'minify_with_stats', 'estimate_tokens', 'CompressionDepth',
    # Adapter
    'adapt_compression', 'CompressionResult',
    # Translators
    'python_to_sudolang', 'ast_to_sudolang', 'python_to_synthlang',
    # Mapping
    'ASTMapper', 'walk_ast_and_map', 'MappedNode', 'SourceMap', 'ProductionSourceMap'
]
