# ===== utils/compression.py =====
from typing import Dict, Any
import logging
from enum import Enum
from .metrics import count_tokens

# Set up logging
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

class CompressionType(Enum):
    """Compression types for different levels of compression."""
    BASIC = "basic"
    STANDARD = "standard"
    AGGRESSIVE = "aggressive"
    SUMMARIZE = "summarize"
    
    @classmethod
    def from_length(cls, length: int):
        """Select compression type based on input length."""
        if length < 1000:
            return cls.BASIC
        elif length < 5000:
            return cls.STANDARD
        elif length < 20000:
            return cls.AGGRESSIVE
        else:
            return cls.SUMMARIZE

def calculate_compression_ratio(original: str, compressed: str) -> float:
    """
    Calculate compression ratio as percentage reduction in tokens.
    
    Args:
        original: The original text.
        compressed: The compressed text.
    
    Returns:
        Percentage reduction (0-100), or 0 if no reduction or error.
    
    Raises:
        ValueError: If inputs are not strings.
    """
    if not isinstance(original, str) or not isinstance(compressed, str):
        raise ValueError("Both original and compressed must be strings")
    
    try:
        orig_tokens = count_tokens(original)
        comp_tokens = count_tokens(compressed)
        
        if orig_tokens == 0:
            logger.warning("Original text has zero tokens; ratio set to 0")
            return 0.0
        
        ratio = (1 - comp_tokens / orig_tokens) * 100
        # Clamp to non-negative; if compressed larger, consider 0% reduction
        return max(0.0, ratio)
    
    except ValueError as e:
        logger.error(f"Token counting failed: {str(e)}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error in compression ratio calculation: {str(e)}")
        return 0.0

def get_compression_stats(original: str, compressed: str) -> Dict[str, Any]:
    """
    Get detailed compression statistics.
    
    Args:
        original: Original text.
        compressed: Compressed text.
    
    Returns:
        Dict with original_tokens, compressed_tokens, and ratio.
    """
    orig_tokens = count_tokens(original)
    comp_tokens = count_tokens(compressed)
    ratio = calculate_compression_ratio(original, compressed)
    
    return {
        "original_tokens": orig_tokens,
        "compressed_tokens": comp_tokens,
        "compression_ratio": ratio
    }