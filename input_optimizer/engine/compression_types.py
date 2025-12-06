"""
Compression types and enums for the waterfall compression system.
"""
from enum import Enum
from dataclasses import dataclass
from typing import Optional, List, Dict, Any


class CompressionTier(Enum):
    """Compression tiers based on token count."""
    TINY = "tiny"        # <100 tokens: no compression
    SMALL = "small"      # 100-1000 tokens: light compression
    MEDIUM = "medium"    # 1000-10000 tokens: standard CAI compression
    LARGE = "large"      # 10000-50000 tokens: chunked compression
    HUGE = "huge"        # >50000 tokens: summarization + RAG


@dataclass
class CompressionResult:
    """Result of waterfall compression."""
    original_tokens: int
    compressed_tokens: int
    compression_ratio: float
    tier_used: CompressionTier
    method_used: str
    content: str
    chunks: Optional[List[str]] = None
    metadata: Dict[str, Any] = None
    cai3_map: Optional[Any] = None  # CAI3Map with variable mappings
    cai3_full: Optional[Any] = None  # CAI3Full with complete structure and constraints
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}
    
    @property
    def compressed_code(self) -> str:
        """Legacy property for backward compatibility."""
        return self.content
    
    @property 
    def compressed_content(self) -> str:
        """Legacy property for backward compatibility."""
        return self.content
    
    @property
    def pre_tokens(self) -> int:
        """Legacy property for backward compatibility."""
        return self.original_tokens
        
    @property
    def post_tokens(self) -> int:
        """Legacy property for backward compatibility."""  
        return self.compressed_tokens
    
    @property
    def output_tokens(self) -> int:
        """Output tokens for benchmark compatibility."""
        return self.compressed_tokens
        
    @property
    def additional_metrics(self) -> Dict[str, Any]:
        """Legacy property for backward compatibility."""
        return self.metadata or {}
        
    @property
    def token_reduction_percent(self) -> float:
        """Legacy property for backward compatibility."""
        return self.compression_ratio
        
    @property
    def processing_time_ms(self) -> float:
        """Legacy property for processing time in milliseconds."""
        return self.metadata.get("processing_time_ms", 0.0)
