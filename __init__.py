"""OptimizeAI - AI-powered code optimization platform"""
__version__ = "0.1.0"

# Import working core modules
try:
    from optimize_ai.core.config import ConfigManager, AgentConfig
    from optimize_ai.core.session_manager import SecureSessionManager
    from optimize_ai.utils.logger import MinifierLogger
    
    # Import input optimizer functions
    from optimize_ai.input_optimizer.engine.minifier import (
        minify_code, minify_basic, minify_aggressive, 
        minify_with_stats, estimate_tokens, CompressionDepth
    )
    
    __all__ = [
        'ConfigManager',
        'AgentConfig', 
        'SecureSessionManager',
        'MinifierLogger',
        'minify_code',
        'minify_basic', 
        'minify_aggressive',
        'minify_with_stats',
        'estimate_tokens',
        'CompressionDepth',
        '__version__'
    ]
except ImportError as e:
    # Fallback if some modules are not available
    __all__ = ['__version__']
    print(f"Warning: Some modules could not be imported: {e}")
