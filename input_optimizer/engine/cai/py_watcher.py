import time
import os
import signal
import asyncio
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Dict, Any
from dataclasses import dataclass, field
from datetime import datetime

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from optimize_ai.core.waterfall_compressor import WaterfallCompressor, CompressionResult
from optimize_ai.input_optimizer.engine.adapter import performance_monitor
from optimize_ai.utils.logger import get_simple_logger
from .cache_manager import CacheManager

logger = get_simple_logger(__name__)


# ────────────────────────────────────────────────────────────────────────────────
@dataclass
class WatcherMetrics:
    """Metrics tracking for the file watcher."""
    events_processed: int = 0
    files_compressed: int = 0
    total_compression_time_ms: float = 0.0
    errors_count: int = 0
    start_time: datetime = field(default_factory=datetime.now)
    
    def get_average_compression_time(self) -> float:
        """Get average compression time in milliseconds."""
        if self.files_compressed == 0:
            return 0.0
        return self.total_compression_time_ms / self.files_compressed
    
    def get_uptime_seconds(self) -> float:
        """Get watcher uptime in seconds."""
        return (datetime.now() - self.start_time).total_seconds()


# ────────────────────────────────────────────────────────────────────────────────
class _PyHandler(FileSystemEventHandler):
    def __init__(self, cache: CacheManager, comp: WaterfallCompressor, metrics: WatcherMetrics, 
                 use_async: bool = False, max_workers: int = 4) -> None:
        self.cache = cache
        self.comp = comp
        self.metrics = metrics
        self.use_async = use_async
        self.executor = ThreadPoolExecutor(max_workers=max_workers) if use_async else None

    def on_modified(self, event) -> None:  # type: ignore[override]
        try:
            self.metrics.events_processed += 1
            
            if not event.src_path.endswith(".py"):
                return
                
            py = Path(event.src_path)
            if not self.cache.is_stale(py, self.comp._determine_tier(count_tokens(py.read_text()))):
                return
                
            if self.use_async and self.executor:
                # Submit to thread pool for async processing
                self.executor.submit(self._compress_file_with_metrics, py)
            else:
                # Synchronous processing
                self._compress_file_with_metrics(py)
                
        except Exception as e:
            self.metrics.errors_count += 1
            logger.error("Failed to process file modification %s: %s", event.src_path, e)
            # Continue watching - don't re-raise the exception

    @performance_monitor
    def _compress_file_with_metrics(self, py: Path) -> None:
        """Compress file and track metrics."""
        start_time = time.time()
        try:
            # Use waterfall compression
            result: CompressionResult = self.comp.compress_file(py)
            
            # Cache based on tier
            if result.tier_used != self.comp.thresholds["TINY"][1]:  # Assuming TINY max is 100
                cache_path = self.cache.get_compressed_path(py, result.tier_used)
                if cache_path:
                    cache_path.parent.mkdir(parents=True, exist_ok=True)
                    cache_path.write_text(result.content)
                    logger.info("Cached compressed content for %s (tier: %s)", py, result.tier_used.value)
            
            compression_time_ms = (time.time() - start_time) * 1000
            self.metrics.files_compressed += 1
            self.metrics.total_compression_time_ms += compression_time_ms
            
            logger.info("Compressed %s → %s tokens (%.2fms, tier: %s)", py, result.compressed_tokens, compression_time_ms, result.tier_used.value)
        except Exception as e:
            self.metrics.errors_count += 1
            logger.error("Failed to compress file %s: %s", py, e)
            raise

    def get_metrics_summary(self) -> str:
        """Get a formatted metrics summary."""
        uptime = self.metrics.get_uptime_seconds()
        avg_compression = self.metrics.get_average_compression_time()
        
        return (
            f"Watcher Metrics (uptime: {uptime:.1f}s):\n"
            f"  Events processed: {self.metrics.events_processed}\n"
            f"  Files compressed: {self.metrics.files_compressed}\n"
            f"  Average compression time: {avg_compression:.2f}ms\n"
            f"  Errors: {self.metrics.errors_count}"
        )

    def shutdown(self) -> None:
        """Cleanup resources."""
        if self.executor:
            self.executor.shutdown(wait=True)


# ────────────────────────────────────────────────────────────────────────────────
class PythonFileWatcher:
    def __init__(self, cache: CacheManager, comp: WaterfallCompressor, 
                 use_async: bool = False, max_workers: int = 4,
                 metrics_log_interval: int = 300) -> None:  # Log metrics every 5 minutes
        self.observer = Observer()
        self.metrics = WatcherMetrics()
        self.handler = _PyHandler(cache, comp, self.metrics, use_async, max_workers)
        self.observer.schedule(self.handler, str(Path.cwd()), recursive=True)
        self.pidfile = Path.cwd() / ".py_watcher.pid"
        self.metrics_log_interval = metrics_log_interval
        self._last_metrics_log = time.time()

    def _is_already_running(self) -> bool:
        """Check if another watcher instance is already running."""
        if not self.pidfile.exists():
            return False
        
        try:
            with open(self.pidfile, 'r') as f:
                pid = int(f.read().strip())
            
            # Check if process is still running
            os.kill(pid, 0)  # This will raise OSError if process doesn't exist
            return True
        except (OSError, ValueError, FileNotFoundError):
            # Process doesn't exist or pidfile is corrupted, safe to proceed
            if self.pidfile.exists():
                self.pidfile.unlink()  # Clean up stale pidfile
            return False

    def _create_pidfile(self) -> None:
        """Create pidfile with current process ID."""
        with open(self.pidfile, 'w') as f:
            f.write(str(os.getpid()))

    def _cleanup_pidfile(self) -> None:
        """Remove pidfile on exit."""
        if self.pidfile.exists():
            self.pidfile.unlink()

    def _log_metrics_if_needed(self) -> None:
        """Log metrics periodically."""
        current_time = time.time()
        if current_time - self._last_metrics_log >= self.metrics_log_interval:
            logger.info(self.handler.get_metrics_summary())
            self._last_metrics_log = current_time

    def get_metrics(self) -> WatcherMetrics:
        """Get current metrics."""
        return self.metrics

    def start(self) -> None:
        if self._is_already_running():
            logger.error("PythonFileWatcher is already running. Exiting.")
            return
            
        self._create_pidfile()
        
        try:
            self.observer.start()
            logger.info("⌚ CAI watcher started (Ctrl-C to quit)")
            logger.info("Features: async=%s, metrics_interval=%ds", 
                       self.handler.use_async, self.metrics_log_interval)
            
            try:
                while True:
                    time.sleep(1)
                    self._log_metrics_if_needed()
            except KeyboardInterrupt:
                logger.info("Stopping CAI watcher...")
                logger.info("Final " + self.handler.get_metrics_summary())
                self.observer.stop()
        finally:
            self.handler.shutdown()
            self._cleanup_pidfile()
            self.observer.join()


# ────────────────────────────────────────────────────────────────────────────────
def create_watcher(cache: CacheManager, comp: WaterfallCompressor, 
                   enable_async: bool = True, max_workers: int = 4) -> PythonFileWatcher:
    """
    Factory function to create a PythonFileWatcher with sensible defaults.
    
    Args:
        cache: Cache manager instance
        comp: Waterfall compressor instance  
        enable_async: Whether to enable async processing (default: True)
        max_workers: Number of worker threads for async processing (default: 4)
        
    Returns:
        Configured PythonFileWatcher instance
    """
    return PythonFileWatcher(
        cache=cache,
        comp=comp,
        use_async=enable_async,
        max_workers=max_workers,
        metrics_log_interval=300  # 5 minutes
    )