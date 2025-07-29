"""
Translation engines for converting Python code to specialized languages.
"""

from .sudo_lang_translator import python_to_sudolang, ast_to_sudolang
from .synth_lang_translator import python_to_synthlang

__all__ = [
    'python_to_sudolang', 
    'ast_to_sudolang', 
    'python_to_synthlang'
]
