"""
Claude Code integration command for OptimizeAI CLI.
Provides middleware compression for Claude Code interactions.
"""

import warnings
# Suppress SSL warnings for urllib3 (must be before any imports that use urllib3)
warnings.filterwarnings("ignore", category=UserWarning, module="urllib3")
warnings.filterwarnings("ignore", message=".*urllib3.*", category=UserWarning)

import click
import subprocess
import json
import sys
import os
from pathlib import Path
from typing import Optional, Dict, Any
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
from rich.table import Table
from rich.panel import Panel
from rich.syntax import Syntax

# Import existing OptimizeAI components
# Add the parent directory to Python path for imports
import os
project_root = str(Path(__file__).parent.parent.parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Import with improved error handling (excluding interactive to avoid circular imports)
ClaudeCodeProxy = None
WaterfallCompressor = None
CompressionResult = None
setup_logger = None

try:
    # Try absolute imports without package prefix (should work now)
    from integrations.claude_wrapper.claude_proxy import ClaudeCodeProxy
    from input_optimizer.engine.waterfall_compressor import WaterfallCompressor
    from input_optimizer.engine.compression_types import CompressionResult
    from utils.logger import setup_logger
except ImportError as e:
    try:
        # Try package-relative imports as fallback
        from optimize_ai.integrations.claude_wrapper.claude_proxy import ClaudeCodeProxy
        from optimize_ai.input_optimizer.engine.waterfall_compressor import WaterfallCompressor
        from optimize_ai.input_optimizer.engine.compression_types import CompressionResult
        from optimize_ai.utils.logger import setup_logger
    except ImportError as e2:
        # Only print error if both import attempts failed
        print(f"Import error: Failed to import required modules - using fallback mode")
        print(f"  First error: {e}")
        print(f"  Second error: {e2}")
        # Create fallback classes to prevent crashes
        class ClaudeCodeProxy:
            def __init__(self, **kwargs):
                pass
            def process_input(self, text, file=None):
                return text, {"compressed": False}
            def process_output(self, text, metadata):
                return text
        
        class WaterfallCompressor:
            pass
        
        class CompressionResult:
            pass
        
        def setup_logger(name):
            import logging
            return logging.getLogger(name)

console = Console()
logger = setup_logger(__name__)

@click.group()
def claude_code():
    """Interact with Claude Code through OptimizeAI compression middleware."""
    pass

@claude_code.command()
@click.argument('prompt', type=str)
@click.option('--file', '-f', type=click.Path(exists=True), help='Python file to analyze')
@click.option('--no-compress', is_flag=True, help='Disable compression (compare costs)')
@click.option('--apply-patch', is_flag=True, help='Auto-apply suggested changes')
@click.option('--output', '-o', type=click.Path(), help='Save result to file')
@click.option('--show-stats', is_flag=True, default=True, help='Show compression statistics')
@click.option('--verbose', '-v', is_flag=True, help='Verbose output')
def ask(prompt: str, file: Optional[str], no_compress: bool, apply_patch: bool, 
        output: Optional[str], show_stats: bool, verbose: bool):
    """
    Ask Claude Code a question about your code with automatic compression.
    
    Examples:
        optimize-ai claude-code ask "Fix the validation bug" -f app.py
        optimize-ai claude-code ask "Explain this function" -f module.py --no-compress
        optimize-ai claude-code ask "Add error handling" -f service.py --apply-patch
    """
    try:
        # Initialize the proxy
        proxy = ClaudeCodeProxy(
            enable_compression=not no_compress,
            cache_dir=Path.home() / ".optimize_ai" / "claude_cache"
        )
        
        # Read file content if provided
        file_content = None
        if file:
            file_path = Path(file)
            file_content = file_path.read_text()
            
        # Show compression preview
        if show_stats and not no_compress:
            with console.status("[cyan]Analyzing code for compression...") as status:
                compressed_prompt, metadata = proxy.process_input(
                    prompt if not file_content else f"{prompt}\n\n```python\n{file_content}\n```",
                    file
                )
                
            _display_compression_preview(metadata)
            
            # Ask for confirmation
            if not click.confirm("Proceed with compressed request?", default=True):
                console.print("[yellow]Aborted by user[/yellow]")
                return
        
        # Execute with Claude Code
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            console=console,
        ) as progress:
            
            # Compression phase
            if not no_compress:
                task = progress.add_task("[cyan]Compressing code...", total=100)
                compressed_prompt, metadata = proxy.process_input(
                    prompt if not file_content else f"{prompt}\n\n```python\n{file_content}\n```",
                    file
                )
                progress.update(task, completed=100)
            else:
                compressed_prompt = prompt if not file_content else f"{prompt}\n\n```python\n{file_content}\n```"
                metadata = {"compressed": False}
            
            # Claude Code execution
            task = progress.add_task("[yellow]Sending to Claude Code...", total=100)
            
            # Execute through actual Claude Code CLI
            result = _execute_claude_code(compressed_prompt, verbose)
            progress.update(task, completed=100)
            
            # Translation phase (if compressed)
            if not no_compress and _contains_cai3(result):
                task = progress.add_task("[green]Translating CAI3 response...", total=100)
                final_output = proxy.process_output(result, metadata)
                progress.update(task, completed=100)
            else:
                final_output = result
        
        # Display results
        _display_results(final_output, metadata, show_stats)
        
        # Save output if requested
        if output:
            Path(output).write_text(final_output)
            console.print(f"[green]✓ Saved to {output}[/green]")
        
        # Apply patch if requested
        if apply_patch and file and _has_code_changes(final_output):
            _apply_patch(file, final_output)
            
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        if verbose:
            import traceback
            console.print(traceback.format_exc())
        sys.exit(1)

def _execute_claude_code(prompt: str, verbose: bool) -> str:
    """Execute Claude Code CLI with the given prompt."""
    try:
        # Use the actual claude CLI command
        cmd = ["claude", prompt]
        
        if verbose:
            console.print(f"[dim]Executing: {' '.join(cmd)}[/dim]")
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120
        )
        
        if result.returncode != 0:
            raise RuntimeError(f"Claude Code error: {result.stderr}")
        
        return result.stdout
        
    except FileNotFoundError:
        raise RuntimeError(
            "Claude Code CLI not found. Ensure 'claude' is installed and in PATH.\n"
            "Install with: pip install claude-cli"
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError("Claude Code request timed out after 120 seconds")

def _contains_cai3(text: str) -> bool:
    """Check if response contains CAI3 compressed code."""
    cai3_markers = ['#C3L', '#C3-PATCH', 'CAI3 CODE', 'B#', 'X:', 'D:', 'T:']
    return any(marker in text for marker in cai3_markers)

def _display_compression_preview(metadata: Dict[str, Any]):
    """Display compression statistics and cost savings."""
    if not metadata.get("compressed"):
        return
    
    # Create comparison table
    table = Table(title="� Estimated Compression Analysis", show_header=True, header_style="bold cyan")
    table.add_column("Metric", style="cyan", width=20)
    table.add_column("Original (Est.)", style="red", width=15)
    table.add_column("Compressed (Est.)", style="green", width=15)
    table.add_column("Est. Savings", style="bold yellow", width=15)
    
    original_tokens = metadata.get('original_tokens', 0)
    compressed_tokens = metadata.get('compressed_tokens', 0)
    saved_tokens = metadata.get('tokens_saved', 0)
    compression_ratio = metadata.get('compression_ratio', 0)
    
    # Token row
    table.add_row(
        "Tokens",
        f"{original_tokens:,}",
        f"{compressed_tokens:,}",
        f"{saved_tokens:,} ({compression_ratio:.1f}%)"
    )
    
    # Cost estimation (Claude's pricing)
    input_cost_per_1k = 0.003  # $3 per 1M tokens
    output_cost_per_1k = 0.015  # $15 per 1M tokens
    
    original_input_cost = (original_tokens / 1000) * input_cost_per_1k
    compressed_input_cost = (compressed_tokens / 1000) * input_cost_per_1k
    
    # Estimate output tokens proportionally to input complexity
    # Original input should generate more detailed response than compressed input
    estimated_original_output_tokens = original_tokens * 2.5
    estimated_compressed_output_tokens = compressed_tokens * 2.5
    
    original_output_cost = (estimated_original_output_tokens / 1000) * output_cost_per_1k
    compressed_output_cost = (estimated_compressed_output_tokens / 1000) * output_cost_per_1k
    
    original_total_cost = original_input_cost + original_output_cost
    compressed_total_cost = compressed_input_cost + compressed_output_cost
    cost_savings = original_total_cost - compressed_total_cost
    
    # Cost row
    table.add_row(
        "Est. Cost",
        f"${original_total_cost:.4f}",
        f"${compressed_total_cost:.4f}",
        f"${cost_savings:.4f} ({(cost_savings/original_total_cost*100):.1f}%)"
    )
    
    # Compression tier
    table.add_row(
        "Compression",
        "None",
        metadata.get('tier_used', 'CAI3').upper(),
        metadata.get('method_used', 'cai3_enhanced')
    )
    
    console.print(table)
    
    # Add estimation disclaimer
    console.print("\n[dim italic]💡 Note: This is an estimated analysis based on proportional scaling (2.5x output ratio).[/dim italic]")
    console.print("[dim italic]For actual savings with real Claude responses, use the interactive session:[/dim italic]")
    console.print("[dim italic]   claude-interactive --live-metrics[/dim italic]")
    
    # Visual token bar
    _display_token_bar(original_tokens, compressed_tokens)

def _display_token_bar(original: int, compressed: int):
    """Display visual representation of token savings."""
    max_width = 50
    compressed_width = int((compressed / original) * max_width) if original > 0 else 0
    saved_width = max_width - compressed_width
    
    console.print("\n📊 Token Usage:")
    console.print(f"Original:   [red]{'█' * max_width}[/red] {original:,}")
    console.print(f"Compressed: [green]{'█' * compressed_width}[/green][dim]{'░' * saved_width}[/dim] {compressed:,}")

def _display_results(output: str, metadata: Dict[str, Any], show_stats: bool):
    """Display the final results with formatting."""
    console.print("\n" + "─" * 80)
    
    # Extract code blocks if present
    import re
    code_blocks = re.findall(r'```(?:python)?\n(.*?)```', output, re.DOTALL)
    
    if code_blocks:
        for i, code in enumerate(code_blocks, 1):
            console.print(f"\n[bold cyan]Code Block {i}:[/bold cyan]")
            syntax = Syntax(code, "python", theme="monokai", line_numbers=True)
            console.print(syntax)
    
    # Display non-code content
    non_code = re.sub(r'```(?:python)?\n.*?```', '', output, flags=re.DOTALL).strip()
    if non_code:
        console.print(Panel(non_code, title="Claude's Response", border_style="blue"))
    
    # Final statistics
    if show_stats and metadata.get("compressed"):
        console.print(f"\n[bold green]✨ Token Savings: {metadata['tokens_saved']:,} tokens "
                     f"({metadata['compression_ratio']:.1f}% reduction)[/bold green]")
        console.print(f"[bold cyan]💰 Estimated Savings: "
                     f"${metadata.get('potential_cost_savings', 0):.4f}[/bold cyan]")

def _has_code_changes(output: str) -> bool:
    """Check if output contains code changes."""
    indicators = ['```python', 'def ', 'class ', 'import ', '#C3-PATCH']
    return any(indicator in output for indicator in indicators)

def _apply_patch(file_path: str, output: str):
    """Apply code changes to the file."""
    import re
    
    # Extract Python code from output
    code_match = re.search(r'```python\n(.*?)```', output, re.DOTALL)
    if not code_match:
        console.print("[yellow]No code changes found to apply[/yellow]")
        return
    
    new_code = code_match.group(1)
    
    # Backup original
    backup_path = Path(file_path).with_suffix('.bak')
    Path(file_path).rename(backup_path)
    console.print(f"[dim]Backup created: {backup_path}[/dim]")
    
    # Write new code
    Path(file_path).write_text(new_code)
    console.print(f"[green]✓ Applied changes to {file_path}[/green]")

@claude_code.command()
@click.argument('files', type=click.Path(exists=True), nargs=-1, required=True)
@click.option('--output', '-o', type=click.Path(), help='Output directory for analysis')
def analyze(files, output):
    """Analyze multiple files with compression statistics."""
    total_original = 0
    total_compressed = 0
    
    results = []
    
    for file_path in files:
        console.print(f"\n[cyan]Analyzing {file_path}...[/cyan]")
        
        # Compress the file
        proxy = ClaudeCodeProxy(enable_compression=True)
        content = Path(file_path).read_text()
        
        compressed, metadata = proxy.process_input(content, file_path)
        
        total_original += metadata.get('original_tokens', 0)
        total_compressed += metadata.get('compressed_tokens', 0)
        
        results.append({
            'file': file_path,
            'original': metadata.get('original_tokens', 0),
            'compressed': metadata.get('compressed_tokens', 0),
            'ratio': metadata.get('compression_ratio', 0)
        })
    
    # Display summary
    table = Table(title="📊 Compression Analysis Summary")
    table.add_column("File", style="cyan")
    table.add_column("Original", style="red")
    table.add_column("Compressed", style="green")
    table.add_column("Reduction", style="yellow")
    
    for r in results:
        table.add_row(
            Path(r['file']).name,
            f"{r['original']:,}",
            f"{r['compressed']:,}",
            f"{r['ratio']:.1f}%"
        )
    
    table.add_row("─" * 20, "─" * 10, "─" * 10, "─" * 10)
    table.add_row(
        "TOTAL",
        f"{total_original:,}",
        f"{total_compressed:,}",
        f"{(1 - total_compressed/total_original)*100:.1f}%" if total_original > 0 else "0%"
    )
    
    console.print(table)
    
    if output:
        # Save analysis to JSON
        import json
        output_path = Path(output) / "compression_analysis.json"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_path, 'w') as f:
            json.dump({
                'files': results,
                'summary': {
                    'total_original': total_original,
                    'total_compressed': total_compressed,
                    'overall_reduction': (1 - total_compressed/total_original)*100 if total_original > 0 else 0
                }
            }, f, indent=2)
        
        console.print(f"\n[green]✓ Analysis saved to {output_path}[/green]")

# Try to add interactive command if available
try:
    from cli.commands.claude_interactive import interactive
    claude_code.add_command(interactive)
except ImportError:
    # Interactive command not available
    pass