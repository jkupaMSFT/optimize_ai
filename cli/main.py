import os
import time
from pathlib import Path
import click
import daemon
import pyperclip
import psutil  # For cross-platform process checks

from optimize_ai.input_optimizer.engine.adapter import WaterfallCompressor
from optimize_ai.input_optimizer.engine.cai.cache_manager import CacheManager
from optimize_ai.input_optimizer.engine.cai.py_watcher import PythonFileWatcher
from optimize_ai.utils.logger import get_simple_logger
from optimize_ai.utils.metrics import count_tokens

logger = get_simple_logger(__name__)

@click.group()
def cli() -> None:
    """optimize-ai CLI for managing CAI compression (MVP)."""
    pass

@cli.command()
def init() -> None:
    """Initialize optimize-ai with hidden cache and .gitignore entry."""
    try:
        CacheManager()
        click.echo("✓ optimize-ai initialized (hidden cache + .gitignore entry).")
    except RuntimeError as e:
        logger.error(f"Init failed: {e}")
        click.echo(f"Error: Failed to initialize: {e}", err=True)
        raise click.Abort()

@cli.command()
@click.option("--daemon", is_flag=True, help="Run watcher as background daemon.")
def watch(daemon: bool) -> None:
    """Start file watcher to auto-compress .py files to .cai cache."""
    try:
        # Check for existing watcher
        pid_file = Path(".optimize_ai/watcher.pid")
        if pid_file.exists():
            with open(pid_file, 'r') as f:
                pid = int(f.read().strip())
            if psutil.pid_exists(pid):
                click.echo("Error: Watcher already running.", err=True)
                raise click.Abort()

        cache = CacheManager()
        comp = WaterfallCompressor()
        watcher = PythonFileWatcher(cache, comp)
        if daemon:
            with daemon.DaemonContext(pidfile=PidFile("cai_watcher", piddir=".optimize_ai")):
                watcher.start()
        else:
            watcher.start()
    except PidFileError as e:
        logger.error(f"Failed to start watcher in daemon mode: {e}")
        click.echo(f"Error: Cannot start daemon: {e}", err=True)
        raise click.Abort()
    except Exception as e:
        logger.error(f"Watcher failed: {e}")
        click.echo(f"Error: Watcher failed: {e}", err=True)
        raise click.Abort()

@cli.command()
def status() -> None:
    """Display compression stats for cached .py/.cai pairs."""
    cache = CacheManager()
    totals, count = 0.0, 0
    for py in Path(".").rglob("*.py"):
        try:
            cai = cache.get_cai_path(py)
            if cai.exists():
                orig_tk = count_tokens(py.read_text())
                comp_tk = count_tokens(cai.read_text())
                red = (1 - comp_tk / orig_tk) * 100 if orig_tk else 0
                click.echo(f"{py}: {red:.1f}% reduction")
                totals += red
                count += 1
        except (PermissionError, OSError) as e:
            logger.warning(f"Cannot read {py} or {cai}: {e}")
            click.echo(f"Warning: Skipping {py}: {e}", err=True)
    if count:
        click.echo(f"Average reduction → {totals / count:.1f}% across {count} files.")
    else:
        click.echo("No cached .cai files found.")

@cli.command(name="clear-cache")
def clear_cache() -> None:
    """Clear the .optimize_ai cache directory."""
    from shutil import rmtree
    try:
        rmtree(".optimize_ai", ignore_errors=True)
        click.echo("🗑️ cache cleared.")
    except Exception as e:
        logger.error(f"Failed to clear cache: {e}")
        click.echo(f"Error: Failed to clear cache: {e}", err=True)
        raise click.Abort()

@cli.command()
@click.argument("py_file", type=click.Path(exists=True))
@click.option("--to-clipboard", is_flag=True, help="Copy compressed text to clipboard.")
def copy(py_file: str, to_clipboard: bool) -> None:
    """Compress a .py file and output to terminal or clipboard."""
    py = Path(py_file)
    compressor = WaterfallCompressor()
    try:
        result = compressor.compress_file(py)
        if to_clipboard:
            pyperclip.copy(result.content)
            click.echo(f"📋 {result.compressed_tokens} tokens copied ({result.compression_ratio:.1f}% reduction).")
        else:
            click.echo(f"{result.compressed_tokens} tokens ({result.compression_ratio:.1f}% reduction):\n{result.content}")
    except Exception as e:
        logger.error(f"Copy failed for {py}: {e}")
        click.echo(f"Error: Cannot process {py}: {e}", err=True)
        raise click.Abort()

@cli.command()
def stop() -> None:
    """Stop the running CAI watcher."""
    pid_file = Path(".optimize_ai/watcher.pid")
    if not pid_file.exists():
        click.echo("No watcher running.")
        return
    try:
        with open(pid_file, 'r') as f:
            pid = int(f.read().strip())
        if psutil.pid_exists(pid):
            os.kill(pid, 15)  # SIGTERM
            logger.info(f"Sent SIGTERM to watcher PID {pid}")
        else:
            logger.warning(f"Stale PID file: {pid_file} (process not running)")
        pid_file.unlink(missing_ok=True)
        click.echo("Watcher stopped.")
    except (OSError, ValueError) as e:
        logger.error(f"Failed to stop watcher: {e}")
        click.echo(f"Error: Cannot stop watcher: {e}", err=True)
        raise click.Abort()

@cli.command()
def help() -> None:
    """Show all CLI options."""
    ctx = click.get_current_context()
    click.echo(cli.get_help(ctx))

@cli.command()
@click.argument('files', nargs=-1, type=click.Path(exists=True))
@click.option('--model', default='gpt-4', help='Target LLM model')
@click.option('--stats', is_flag=True, help='Show compression statistics')
def compress(files, model, stats):
    """Compress files using waterfall method."""
    compressor = WaterfallCompressor(llm_model=model)
    
    total_original = 0
    total_compressed = 0
    
    for file_path in files:
        path = Path(file_path)
        result = compressor.compress_file(path)
        
        total_original += result.original_tokens
        total_compressed += result.compressed_tokens
        
        if stats:
            click.echo(f"{path.name}:")
            click.echo(f"  Tier: {result.tier_used.value}")
            click.echo(f"  Original: {result.original_tokens} tokens")
            click.echo(f"  Compressed: {result.compressed_tokens} tokens")
            click.echo(f"  Reduction: {result.compression_ratio:.1f}%")
            
    if len(files) > 1:
        overall_reduction = (1 - total_compressed / total_original) * 100 if total_original > 0 else 0
        click.echo(f"\nOverall compression: {overall_reduction:.1f}%")
        
@cli.command()
@click.argument("py_files", nargs=-1, type=click.Path(exists=True))
@click.option("--model", default="gpt-4", help="Target LLM model for token limits.")
@click.option("--to-clipboard", is_flag=True, help="Copy context to clipboard.")
def context(py_files: Tuple[str], model: str, to_clipboard: bool) -> None:
    """Build optimized multi-file context for LLM."""
    compressor = WaterfallCompressor()
    provider = WaterfallContextProvider(compressor)
    try:
        context_str = provider.get_context_for_files([Path(p) for p in py_files], target_model=model)
        if to_clipboard:
            pyperclip.copy(context_str)
            click.echo("📋 Multi-file context copied.")
        else:
            click.echo(context_str)
    except ValueError as e:
        logger.error(f"Context failed: {e}")
        click.echo(f"Error: {e}", err=True)
        raise click.Abort()

if __name__ == "__main__":
    cli()