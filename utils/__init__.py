"""
Utility modules for the input optimizer package.
"""

from .logger import get_logger, setup_minifier_logging, MinifierLogger
from .compression import CompressionType
from .text_utils import *

__all__ = [
    'get_logger',
    'setup_minifier_logging', 
    'MinifierLogger',
    'CompressionType'
]
