#!/usr/bin/env python3
"""
Optimize Claude - CLI wrapper for Claude Code with automatic compression
"""

import argparse
import sys
from pathlib import Path

# Add parent directory to path
sys.path.append(str(Path(__file__).parent.parent.parent.parent))

from integrations.claude_wrapper.claude_proxy import ClaudeCodeProxy
from utils.logger import setup_logger

def execute_claude_with_translation(proxy: ClaudeCodeProxy, prompt: str, 
                                   file_path: Optional[str], console: Console) -> str:
    """Execute Claude and handle CAI3 translation with progress."""
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        console=console,
    ) as progress:
        
        # Compression phase
        compress_task = progress.add_task("[cyan]Compressing with CAI3...", total=100)
        compressed_prompt, metadata = proxy.process_input(prompt, file_path)
        progress.update(compress_task, completed=100)
        
        # Display compression stats
        display_compression_stats(metadata, console)
        
        # Execution phase
        execute_task = progress.add_task("[yellow]Executing Claude Code...", total=100)
        
        # Simulate Claude execution (replace with actual)
        import time
        for i in range(10):
            time.sleep(0.1)  # Simulate work
            progress.update(execute_task, advance=10)
        
        # Get Claude's response (mock for now)
        claude_response = generate_mock_cai3_response(compressed_prompt)
        progress.update(execute_task, completed=100)
        
        # Translation phase
        if "#C3" in claude_response or "CAI3" in metadata.get("compression_type", ""):
            translate_task = progress.add_task("[green]Translating CAI3 to Python...", total=100)
           
            # Process the output through translation
            final_output = proxy.process_output(claude_response, metadata)
            progress.update(translate_task, completed=100)
        else:
            final_output = claude_response
   
    return final_output

def generate_mock_cai3_response(compressed_prompt: str) -> str:
   """Generate a mock CAI3 response for testing."""
   # This would be replaced with actual Claude Code execution
   return """
I'll fix the validation bug by removing the mutation of the input record.

---CAI3 CODE START---
#C3L file.py
X:a0=mt_961c,a1=mt_549e
D:g0=s.config.get,g1=tv.items
T:C:dp,M:dp.i#a0,M:dp.vr#a1
B#a0:x=0;e=0;s.c=a
B#a1:c=g0('required_fields',[]);@d,c{d!inb?RF:_};RT
---CAI3 CODE END---

The fix ensures the validate_record method returns False when a required field is missing 
instead of mutating the input record by adding None values.
"""

def display_token_savings_bar(metadata: Dict, console: Console):
   """Display an animated token savings visualization."""
   if not metadata.get("compressed", False):
       return
   
   original = metadata.get('original_tokens', 0)
   compressed = metadata.get('compressed_tokens', 0)
   saved = metadata.get('tokens_saved', 0)
   
   # Create visual bars
   max_width = 60
   
   # Original tokens bar (full width)
   console.print("\n📊 [bold]Token Usage Comparison:[/bold]")
   console.print(f"Original:    [red]{'█' * max_width}[/red] {original:,} tokens")
   
   # Compressed tokens bar (proportional)
   if original > 0:
       compressed_width = int((compressed / original) * max_width)
       saved_width = max_width - compressed_width
       
       console.print(f"Compressed:  [green]{'█' * compressed_width}[/green][dim]{'░' * saved_width}[/dim] {compressed:,} tokens")
       console.print(f"Saved:       [bold green]{' ' * compressed_width}{'▼' * saved_width}[/bold green] {saved:,} tokens")
       
       # Animated percentage
       console.print(f"\n💰 [bold green]Compression: {metadata['compression_ratio']:.1f}% reduction[/bold green]")
       console.print(f"💵 [bold cyan]Est. Savings: ${metadata.get('potential_cost_savings', 0):.3f}[/bold cyan]")

def main():
   """Enhanced CLI main function."""
   parser = argparse.ArgumentParser(
       description="Optimize Claude - CAI3 compression wrapper for Claude Code",
       formatter_class=argparse.RawDescriptionHelpFormatter,
       epilog="""
    Examples:
    optimize-claude "fix the validation bug" --file app.py
    optimize-claude --test --file large_module.py "analyze this"
    optimize-claude --apply-patch --file buggy.py "fix all type errors"
    optimize-claude --show-mapping --file complex.py "explain the architecture"
        """
    )
   
   parser.add_argument("prompt", help="The prompt or instruction for Claude")
   parser.add_argument("--file", "-f", help="Path to Python source file")
   parser.add_argument("--no-compress", action="store_true", help="Disable CAI3 compression")
   parser.add_argument("--test", action="store_true", help="Test compression without executing")
   parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
   parser.add_argument("--apply-patch", action="store_true", help="Auto-apply patches to source")
   parser.add_argument("--show-mapping", action="store_true", help="Display CAI3 mapping details")
   parser.add_argument("--output", "-o", help="Output file for translated Python code")
   
   args = parser.parse_args()
   
   # Setup console
   console = Console()
   
   # Show header
   console.print(Panel.fit(
       "🚀 [bold cyan]Optimize Claude[/bold cyan] - CAI3 Compression Engine v2.0", 
       border_style="cyan"
   ))
   
   # Setup logger
   logger = setup_logger("optimize-claude", log_level="DEBUG" if args.verbose else "INFO")
   
   # Initialize proxy
   proxy = ClaudeCodeProxy(
       enable_compression=not args.no_compress,
       llm_model="gpt-4"
   )
   
   # Test mode
   if args.test:
       with console.status("[bold cyan]Running compression test...") as status:
           compressed_prompt, metadata = proxy.process_input(args.prompt, args.file)
           
       # Display detailed compression analysis
       display_compression_stats(metadata, console)
       display_token_savings_bar(metadata, console)
       
       if args.show_mapping:
           display_cai3_mapping(proxy, console)
       
       # Show compressed output
       console.print("\n[bold]Compressed CAI3 Output:[/bold]")
       syntax = Syntax(compressed_prompt[:1000], "python", theme="monokai", line_numbers=True)
       console.print(syntax)
       
       return
   
   # Execute with Claude
   final_output = execute_claude_with_translation(proxy, args.prompt, args.file, console)
   
   # Display result
   console.print("\n" + "─" * 80)
   console.print(final_output)
   
   # Save output if requested
   if args.output:
       # Extract Python code from output
       import re
       code_match = re.search(r'```python\n(.*?)```', final_output, re.DOTALL)
       if code_match:
           python_code = code_match.group(1)
           Path(args.output).write_text(python_code)
           console.print(f"\n✅ [green]Saved translated code to {args.output}[/green]")
   
   # Apply patch if requested
   if args.apply_patch and args.file:
       if "Modified Code:" in final_output or "Translated Python Code:" in final_output:
           console.print("\n[yellow]Applying changes to source file...[/yellow]")
           
           # Extract and apply the code
           import re
           code_match = re.search(r'```python\n(.*?)```', final_output, re.DOTALL)
           if code_match:
               new_code = code_match.group(1)
               
               # Backup original
               backup_path = Path(args.file).with_suffix('.bak')
               Path(args.file).rename(backup_path)
               console.print(f"📁 Backed up to {backup_path}")
               
               # Write new code
               Path(args.file).write_text(new_code)
               console.print(f"✅ [green]Applied changes to {args.file}[/green]")

def display_cai3_mapping(proxy: ClaudeCodeProxy, console: Console):
   """Display detailed CAI3 mapping information."""
   if not proxy.source_path:
       return
   
   # Load mapping from cache
   cai3_map = proxy.cai3_cache.load_map(proxy.source_path)
   cai3_full = proxy.cai3_cache.load_full(proxy.source_path)
   
   if not cai3_map or not cai3_full:
       return
   
   # Create mapping table
   table = Table(title="🗺️ CAI3 Name Mappings", show_header=True, header_style="bold blue")
   table.add_column("Original", style="cyan", no_wrap=True)
   table.add_column("Compressed", style="green")
   table.add_column("Type", style="yellow")
   table.add_column("CID", style="magenta")
   
   # Add class/method mappings
   for node in cai3_full.nodes:
       type_str = {"C": "Class", "M": "Method", "F": "Function"}.get(node.type.value, "Unknown")
       table.add_row(node.name, node.short_name, type_str, node.cid[:8])
   
   console.print(table)
   
   # Show compression stats
   if cai3_full.compression_stats:
       stats = cai3_full.compression_stats
       
       stats_table = Table(title="📈 Compression Statistics", show_header=True)
       stats_table.add_column("Metric", style="cyan")
       stats_table.add_column("Value", style="green")
       
       stats_table.add_row("Total Nodes", str(stats.get('node_count', 0)))
       stats_table.add_row("Pool Size", str(stats.get('pool_size', 0)))
       stats_table.add_row("Chain Aliases", str(len(stats.get('chain_aliases', {}))))
       stats_table.add_row("Compression Mode", stats.get('compression_mode', 'Standard'))
       
       console.print(stats_table)

if __name__ == "__main__":
   main()
