"""Edit mapper for CAI compression tracking with waterfall integration."""

from pathlib import Path
from typing import Optional

from optimize_ai.input_optimizer.engine.waterfall_compressor import WaterfallCompressor, CompressionTier
from optimize_ai.utils.logger import get_simple_logger
from .cache_manager import CacheManager

logger = get_simple_logger(__name__)

class EditMapper:
    """Maps edit operations to compressed code using waterfall compression."""
    
    def __init__(self, waterfall_compressor: Optional[WaterfallCompressor] = None,
                 cache_manager: Optional[CacheManager] = None) -> None:
        """
        Initialize EditMapper.

        Args:
            waterfall_compressor: WaterfallCompressor instance (default: new instance).
            cache_manager: CacheManager instance (default: new instance).
        """
        self.compressor = waterfall_compressor or WaterfallCompressor()
        self.cache = cache_manager or CacheManager()
        # Note: Element parsing now handled within waterfall compressor

    def translate_line_edit(self, file_path: Path, line_num: int, edit_type: str) -> None:
        """
        Translate a line edit operation and update compressed cache.

        Args:
            file_path: Path to the file being edited.
            line_num: Line number being edited (1-indexed).
            edit_type: Type of edit operation (e.g., 'insert', 'delete', 'modify').
        """
        if not file_path.exists():
            logger.warning(f"File {file_path} does not exist, skipping edit translation")
            return

        if line_num < 1:
            logger.warning(f"Invalid line number {line_num} for {file_path}, skipping")
            return

        try:
            # Determine tier based on current file size
            content = file_path.read_text()
            tokens = self.compressor.count_tokens(content)
            tier = self.compressor._determine_tier(tokens)
            
            # Check if cache is stale for this tier
            if not self.cache.is_stale(file_path, tier):
                logger.debug(f"No stale cache for {file_path} in tier {tier.value}, skipping recompression")
                return

            # For MEDIUM/LARGE tiers using CAI, always recompress on edits
            # (Element-level tracking will be added in future iterations)
            touched = True
            if tier.value in ("medium", "large"):
                logger.debug(f"Edit at line {line_num} in {file_path} affects CAI compression tier, recompressing")
            
            # Recompress the file using waterfall (triggers cache update internally)
            result = self.compressor.compress_file(file_path)
            
            # Log edit translation
            logger.info(
                f"Translated {edit_type} edit at line {line_num} in {file_path}: "
                f"recompressed to {result.compressed_tokens} tokens "
                f"({result.compression_ratio:.1f}% reduction, tier: {result.tier_used.value})"
            )
            
        except Exception as e:
            logger.error(f"Failed to translate edit for {file_path}: {e}")
            # In MVP, fail gracefully - don't raise, just log