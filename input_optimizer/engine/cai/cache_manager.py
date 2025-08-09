from pathlib import Path
import hashlib
import os
import fcntl  # For file locking
from typing import Optional

try:
    # Try relative import first
    from ....utils.logger import get_logger
    from ..compression_types import CompressionTier
except ImportError:
    # Fallback to absolute imports
    try:
        import sys
        import os
        
        # Get the project root directory
        current_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(current_dir)))
        
        if project_root not in sys.path:
            sys.path.insert(0, project_root)
            
        from utils.logger import get_logger
        from input_optimizer.engine.compression_types import CompressionTier
    except ImportError:
        # Final fallback - create minimal logger
        import logging
        def get_logger(name):
            return logging.getLogger(name)
        
        # Create fallback CompressionTier
        from enum import Enum, auto
        class CompressionTier(Enum):
            TINY = auto()
            SMALL = auto()
            MEDIUM = auto()
            LARGE = auto()
            HUGE = auto()

logger = get_logger(__name__)

class CacheManager:
    """Hidden-file manager for .cai cache, ensuring idempotent operations and robust error handling."""

    def __init__(self, cache_dir: str = ".optimize_ai") -> None:
        """
        Initialize cache manager with specified directory.

        Args:
            cache_dir: Directory for .cai files (default: .optimize_ai).
        """
        self.cache_dir = Path(cache_dir)
        self.waterfall_dir = self.cache_dir / 'waterfall'
        self.stats_file = self.cache_dir / 'compression_stats.json'
        self._hash_cache: dict[str, str] = {}  # Cache file hashes
        self._mtime_cache: dict[str, float] = {}  # Cache file modification times
        try:
            self.cache_dir.mkdir(exist_ok=True)
            self.waterfall_dir.mkdir(exist_ok=True)
            self._ensure_gitignore()
        except (PermissionError, OSError) as e:
            logger.error(f"Failed to initialize cache directory {self.cache_dir}: {e}")
            raise RuntimeError(f"Cannot create cache directory: {e}") from e

    def get_compressed_path(self, py_path: Path, tier: CompressionTier) -> Optional[Path]:
        """
        Get corresponding compressed path for a given .py file and tier.

        Args:
            py_path: Path to the Python file.
            tier: Compression tier used.

        Returns:
            Optional[Path]: Corresponding compressed file path in cache, or None for TINY tier.

        Raises:
            ValueError: If py_path is not under current working directory.
        """
        try:
            relative = py_path.relative_to(Path.cwd())
            if tier == CompressionTier.TINY:
                return None  # No caching for tiny files
            elif tier in (CompressionTier.SMALL, CompressionTier.MEDIUM):
                return self.cache_dir / relative.with_suffix('.cai')
            else:  # LARGE, HUGE
                return self.waterfall_dir / relative.with_suffix(f'.{tier.value}.cai')
        except ValueError as e:
            logger.error(f"Cannot compute relative path for {py_path}: {e}")
            raise ValueError(f"Python file {py_path} must be under current directory") from e

    def is_stale(self, py_path: Path, tier: CompressionTier) -> bool:
        """
        Check if the cached compressed file is stale or missing for the given tier.

        Args:
            py_path: Path to the Python file.
            tier: Compression tier to check.

        Returns:
            bool: True if compressed file is missing, outdated, or content differs.

        Raises:
            RuntimeError: If file access fails.
        """
        cai_path = self.get_compressed_path(py_path, tier)
        if cai_path is None or not cai_path.exists():
            logger.debug(f"No cache for {py_path} in tier {tier.value}")
            return True

        try:
            # Compute or retrieve cached hashes, but invalidate if file has been modified
            py_key = f"{str(py_path)}:{tier.value}"
            cai_key = str(cai_path)
            
            # Check if the python file hash needs to be recomputed
            current_py_mtime = py_path.stat().st_mtime
            cached_py_mtime = self._mtime_cache.get(py_key)
            
            py_digest = self._hash_cache.get(py_key)
            if not py_digest or (cached_py_mtime and current_py_mtime > cached_py_mtime):
                # File was modified or no cache - recompute hash
                py_digest = hashlib.md5(py_path.read_bytes()).hexdigest()
                self._hash_cache[py_key] = py_digest
                self._mtime_cache[py_key] = current_py_mtime

            # Check if the cai file hash needs to be recomputed
            current_cai_mtime = cai_path.stat().st_mtime
            cached_cai_mtime = self._mtime_cache.get(cai_key)
            
            cai_digest = self._hash_cache.get(cai_key)
            cai_content = None
            if not cai_digest or (cached_cai_mtime and current_cai_mtime > cached_cai_mtime):
                # File was modified or no cache - recompute hash
                cai_content = cai_path.read_text()
                cai_digest = hashlib.md5(cai_content.encode()).hexdigest()
                self._hash_cache[cai_key] = cai_digest
                self._mtime_cache[cai_key] = current_cai_mtime

            # Extract source hash from compressed file if available
            if cai_content is None:
                cai_content = cai_path.read_text()
            
            source_hash_from_cai = None
            for line in cai_content.splitlines():
                if line.startswith('# Source-Hash: '):
                    source_hash_from_cai = line.replace('# Source-Hash: ', '').strip()
                    break

            # Check staleness - compare current py file hash with stored source hash
            if source_hash_from_cai:
                is_stale = py_digest[:8] != source_hash_from_cai
                if is_stale:
                    logger.debug(f"Cache stale for {py_path} in tier {tier.value}: source_hash_mismatch={py_digest[:8]} != {source_hash_from_cai}")
            else:
                # Fallback: use modification time if no source hash found (backward compatibility)
                is_stale = py_path.stat().st_mtime > cai_path.stat().st_mtime
                if is_stale:
                    logger.debug(f"Cache stale for {py_path} in tier {tier.value}: mtime={py_path.stat().st_mtime > cai_path.stat().st_mtime}")
            return is_stale
        except (PermissionError, FileNotFoundError, OSError) as e:
            logger.warning(f"Cannot access files for staleness check {py_path}: {e}")
            return True  # Treat as stale to trigger recompression

    def get_cai_path(self, py_path: Path) -> Path:
        """
        Get the cache path for a Python file. Uses MEDIUM tier as default for waterfall compatibility.
        
        Args:
            py_path: Path to the Python file.
            
        Returns:
            Path: The cache file path.
        """
        # For waterfall compressor compatibility, default to MEDIUM tier
        result = self.get_compressed_path(py_path, CompressionTier.MEDIUM)
        if result is None:
            # Fallback for cases where get_compressed_path returns None
            try:
                relative = py_path.relative_to('.')
                return self.cache_dir / relative.with_suffix('.cai')
            except ValueError:
                # If not under current directory, use the filename with hash
                hash_suffix = hashlib.md5(str(py_path).encode()).hexdigest()[:8]
                return self.cache_dir / f"{py_path.stem}_{hash_suffix}.cai"
        return result

    def update_cache(self, py_path: Path, tier: CompressionTier, cai_content: str) -> None:
        """
        Update the compressed cache file for a given .py file and tier.

        Args:
            py_path: Path to the Python file.
            tier: Compression tier used.
            cai_content: Content to write to the compressed file.

        Raises:
            RuntimeError: If writing to cache fails.
        """
        cai_path = self.get_compressed_path(py_path, tier)
        if cai_path is None:
            logger.debug(f"No caching for tier {tier.value}")
            return
        try:
            cai_path.parent.mkdir(parents=True, exist_ok=True)
            cai_path.write_text(cai_content)
            # Update hash and mtime cache
            py_key = f"{str(py_path)}:{tier.value}"
            cai_key = str(cai_path)
            self._hash_cache[py_key] = hashlib.md5(py_path.read_bytes()).hexdigest()
            self._hash_cache[cai_key] = hashlib.md5(cai_content.encode()).hexdigest()
            self._mtime_cache[py_key] = py_path.stat().st_mtime
            self._mtime_cache[cai_key] = cai_path.stat().st_mtime
            logger.info(f"Updated cache for {py_path} at {cai_path} for tier {tier.value}")
        except (PermissionError, OSError) as e:
            logger.error(f"Failed to update cache for {py_path}: {e}")
            raise RuntimeError(f"Cannot update cache: {e}") from e

    def _ensure_gitignore(self) -> None:
        """
        Ensure .optimize_ai/ is in .gitignore, idempotently.

        Uses file locking to prevent race conditions in concurrent writes.
        """
        gi = Path(".gitignore")
        entry = ".optimize_ai/\n"

        try:
            # Open file with locking
            mode = 'a+' if gi.exists() else 'w+'
            with open(gi, mode) as f:
                # Acquire exclusive lock
                fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                f.seek(0)
                content = f.read()
                if entry.strip() not in content:
                    f.write(entry)
                    logger.info("Added .optimize_ai/ to .gitignore")
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        except (PermissionError, OSError) as e:
            logger.warning(f"Cannot update .gitignore: {e}")
            raise RuntimeError(f"Failed to update .gitignore: {e}") from e