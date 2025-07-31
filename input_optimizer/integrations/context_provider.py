import asyncio
from pathlib import Path
from typing import List, Optional, Dict
from optimize_ai.input_optimizer.engine.waterfall_compressor import WaterfallCompressor, CompressionResult
from optimize_ai.utils.logger import get_simple_logger
from optimize_ai.input_optimizer.engine.cai.cache_manager import CacheManager

logger = get_simple_logger(__name__)

class WaterfallContextProvider:
    """
    Builds optimized multi-file context for LLM prompts using waterfall compression.
    
    Args:
        waterfall_compressor: WaterfallCompressor instance.
        cache_manager: CacheManager for per-file caching (optional).
        use_async: Use async I/O for file operations (default: False).
    """
    def __init__(self, waterfall_compressor: WaterfallCompressor,
                 cache_manager: Optional[CacheManager] = None,
                 use_async: bool = False) -> None:
        self.compressor = waterfall_compressor
        self.cache = cache_manager or CacheManager()
        self.use_async = use_async
        self.model_limits: Dict[str, int] = {
            "gpt-4": 128000,
            "claude-3": 200000,
            "gpt-3.5": 16000
        }

    def get_context_for_files(self, py_files: List[Path], 
                              target_model: str = "gpt-4") -> str:
        """
        Build optimized context for LLM from multiple Python files.
        
        Args:
            py_files: List of Python file paths.
            target_model: Target LLM model for token limits (default: gpt-4).
        
        Returns:
            str: Optimized context string.
        
        Raises:
            ValueError: If files are invalid or compression fails critically.
        """
        if not py_files:
            return ""
        
        limit = self.model_limits.get(target_model, 128000)
        safety_margin = 0.8  # 80% of limit
        
        if self.use_async:
            return asyncio.run(self._async_get_context(py_files, limit, safety_margin))
        else:
            return self._sync_get_context(py_files, limit, safety_margin)

    def _sync_get_context(self, py_files: List[Path], limit: int, safety_margin: float) -> str:
        """Synchronous context building."""
        results = self._compress_files(py_files)
        total_tokens = sum(r.compressed_tokens for r in results)
        
        if total_tokens > limit * safety_margin:
            return self._build_prioritized_context(results, limit)
        
        return self._build_context(results)

    async def _async_get_context(self, py_files: List[Path], limit: int, safety_margin: float) -> str:
        """Asynchronous context building for performance."""
        loop = asyncio.get_running_loop()
        results = await asyncio.gather(
            *[loop.run_in_executor(None, self._compress_single_file, py) for py in py_files],
            return_exceptions=True
        )
        
        # Handle exceptions
        valid_results = []
        for r in results:
            if isinstance(r, Exception):
                logger.error(f"Failed to compress file: {r}")
                continue
            valid_results.append(r)
        
        total_tokens = sum(r.compressed_tokens for r in valid_results)
        
        if total_tokens > limit * safety_margin:
            return self._build_prioritized_context(valid_results, limit)
        
        return self._build_context(valid_results)

    def _compress_single_file(self, py_path: Path) -> CompressionResult:
        """Compress a single file, using cache if available."""
        try:
            # Check cache
            cached = self.cache._check_cache(py_path)
            if cached:
                return cached
            result = self.compressor.compress_file(py_path)
            self.cache._cache_result(py_path, result)
            return result
        except Exception as e:
            logger.error(f"Failed to compress {py_path}: {e}")
            raise ValueError(f"Compression failed for {py_path}: {e}") from e

    def _compress_files(self, py_files: List[Path]) -> List[CompressionResult]:
        """Compress multiple files synchronously."""
        results = []
        for py in py_files:
            try:
                results.append(self._compress_single_file(py))
            except ValueError as e:
                logger.warning(str(e))
                continue  # Skip failed files
        return results

    def _build_context(self, results: List[CompressionResult]) -> str:
        """Build context string from compression results."""
        context_parts = []
        for r in results:
            context_parts.append(f"# File: {r.metadata['source_path']}")
            context_parts.append(f"# Tier: {r.tier_used.value}, Method: {r.method_used}")
            context_parts.append(f"# Tokens: {r.original_tokens} → {r.compressed_tokens} ({r.compression_ratio:.1f}% reduction)")
            context_parts.append(r.content)
            context_parts.append("")
        return '\n'.join(context_parts)

    def _build_prioritized_context(self, results: List[CompressionResult], limit: int) -> str:
        """Build prioritized context when total tokens exceed safety margin."""
        # Prioritize by file modification time (most recent first) and size (smaller first)
        prioritized = sorted(
            results,
            key=lambda r: (
                -Path(r.metadata['source_path']).stat().st_mtime,  # Recent first
                r.original_tokens  # Smaller first
            )
        )
        
        context_parts = []
        current_tokens = 0
        max_tokens = int(limit * 0.8)  # Safety margin
        
        for r in prioritized:
            if current_tokens + r.compressed_tokens > max_tokens:
                # Truncate: Add summary if possible
                summary = f"# Summary for {r.metadata['source_path']}: {r.original_tokens} tokens (truncated)"
                summary_tokens = self.compressor.compressor.count_tokens(summary)  # Use internal token counter
                if current_tokens + summary_tokens <= max_tokens:
                    context_parts.append(summary)
                    current_tokens += summary_tokens
                continue
            
            context_parts.append(f"# File: {r.metadata['source_path']}")
            context_parts.append(r.content)
            context_parts.append("")
            current_tokens += r.compressed_tokens
        
        return '\n'.join(context_parts)