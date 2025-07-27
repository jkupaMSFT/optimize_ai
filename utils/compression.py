from enum import Enum
from typing import Tuple, Callable, Optional

# Type aliases for injected functions
MinifyFn = Callable[[str, bool], str]
TranslateFn = Callable[[str], str]


class CompressionType(Enum):
    """Compression types with built-in size thresholds."""
    BASIC = (0, 500)
    AGGRESSIVE = (500, 2000)
    TRANSLATE = (2000, 10000)
    SUMMARIZE = (10000, float("inf"))
    
    def __init__(self, min_len: int, max_len: float):
        self.min_len = min_len
        self.max_len = max_len
    
    @classmethod
    def from_length(cls, length: int) -> "CompressionType":
        """Get compression type based on content length."""
        return next(ct for ct in cls if ct.min_len <= length < ct.max_len)


def get_compression_type(content: str) -> CompressionType:
    """Determine compression type based on content length."""
    return CompressionType.from_length(len(content))


def compress_content(
    content: str,
    minify_code_func: Optional[MinifyFn] = None,
    translate_to_sudolang_func: Optional[TranslateFn] = None,
    summary_limit: int = 5000
) -> str:
    """
    Compress content based on size thresholds.
    
    Args:
        content: The code/content to compress
        minify_code_func: Function that takes (code, aggressive=bool) params
        translate_to_sudolang_func: Function that translates to sudolang
        summary_limit: Character limit for summarized content
        
    Returns:
        Compressed content based on threshold rules
    """
    compression_type = get_compression_type(content)
    
    if compression_type == CompressionType.BASIC:
        if minify_code_func:
            return minify_code_func(content, aggressive=False)
        return content
    
    if compression_type == CompressionType.AGGRESSIVE:
        if minify_code_func:
            return minify_code_func(content, aggressive=True)
        return content
    
    if compression_type == CompressionType.TRANSLATE:
        if minify_code_func and translate_to_sudolang_func:
            # First minify aggressively, then translate
            minified = minify_code_func(content, aggressive=True)
            return translate_to_sudolang_func(minified)
        return content
    
    # CompressionType.SUMMARIZE
    return f"Summarized: {content[:summary_limit]}"


# Example usage
def process_code(
    code: str,
    minify_func: MinifyFn,
    sudolang_func: TranslateFn,
    summary_limit: int = 5000
) -> str:
    """Example of how to use the compression system."""
    compression_type = get_compression_type(code)
    print(f"Code length: {len(code)} chars")
    print(f"Compression type: {compression_type.name}")
    print(f"Threshold range: {compression_type.min_len}-{compression_type.max_len}")
    
    compressed = compress_content(code, minify_func, sudolang_func, summary_limit)
    print(f"Compressed length: {len(compressed)} chars")
    
    return compressed


# Utility functions for threshold introspection
def get_all_thresholds() -> list[Tuple[str, int, float]]:
    """Get all compression thresholds for documentation/debugging."""
    return [(ct.name, ct.min_len, ct.max_len) for ct in CompressionType]


def find_threshold_for_size(size: int) -> str:
    """Find which compression type would be used for a given size."""
    return CompressionType.from_length(size).name