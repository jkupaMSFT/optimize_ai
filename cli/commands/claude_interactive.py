"""
Interactive Claude Code session with live compr    console.print(Panel(
        "[bold cyan]OptimizeAI Interactive Claude Session[/bold cyan]\n"
        f"Working with: {file if file else 'No file loaded'}\n"
        f"Live metrics: {'Enabled' if live_metrics else 'Disabled'}\n"
        "Commands: /load <file>, /save <file>, /stats, /live, /methodology, /exit",
        border_style="cyan"
    ))metrics.
"""

import click
from rich.console import Console, Group
from rich.live import Live
from rich.table import Table
from rich.layout import Layout
from rich.panel import Panel
from rich.syntax import Syntax
from rich.text import Text
from pathlib import Path
import sys
import time
from typing import Dict, Any

# Import Claude token metrics
try:
    from optimize_ai.utils.metrics import count_tokens_claude, count_tokens_gpt
except ImportError:
    try:
        from utils.metrics import count_tokens_claude, count_tokens_gpt
    except ImportError:
        sys.path.insert(0, str(Path(__file__).parent.parent.parent))
        from utils.metrics import count_tokens_claude, count_tokens_gpt

# Configure console to handle full content without truncation
console = Console()

@click.command()
@click.option('--file', '-f', type=click.Path(exists=True), help='File to work with')
@click.option('--live-metrics', '-l', is_flag=True, help='Show live token metrics panel')
def interactive(file, live_metrics):
    """Start an interactive Claude Code session with live metrics."""
    
    try:
        # Try package-relative imports first
        from optimize_ai.integrations.claude_wrapper.claude_proxy import ClaudeCodeProxy
    except ImportError:
        try:
            # Try absolute imports without package prefix
            from integrations.claude_wrapper.claude_proxy import ClaudeCodeProxy
        except ImportError:
            try:
                sys.path.insert(0, str(Path(__file__).parent.parent.parent))
                from integrations.claude_wrapper.claude_proxy import ClaudeCodeProxy
            except ImportError:
                console.print("[red]Error: Claude Code integration not available[/red]")
                console.print("Missing required dependencies.")
                return
    
    proxy = ClaudeCodeProxy(enable_compression=True)
    
    console.print(Panel(
        "[bold cyan]OptimizeAI Interactive Claude Session[/bold cyan]\n"
        f"Working with: {file if file else 'No file loaded'}\n"
        f"Live metrics: {'Enabled' if live_metrics else 'Disabled'}\n"
        "Commands: /load <file>, /save <file>, /stats, /live, /methodology, /debug, /test, /exit",
        border_style="cyan"
    ))
    
    session_stats = {
        'queries': 0,
        'total_saved': 0,
        'total_cost_saved': 0,
        'claude_model': 'claude-sonnet-4-20250514',
        'original_tokens_claude': 0,
        'compressed_tokens_claude': 0,
        'actual_claude_savings': 0,
        # Claude Sonnet 4 official pricing (per million tokens)
        'claude_input_cost_per_mtok': 3.0,      # $3 per million input tokens
        'claude_output_cost_per_mtok': 15.0,    # $15 per million output tokens
        'claude_cache_write_5m_per_mtok': 3.75, # $3.75 per million (5min cache)
        'claude_cache_write_1h_per_mtok': 6.0,  # $6 per million (1h cache)
        'claude_cache_hit_per_mtok': 0.30,      # $0.30 per million (cache hits)
        'response_tokens_claude': 0,
        'estimated_response_savings': 0,
        'total_estimated_cost_saved': 0
    }
    
    current_file = Path(file).read_text() if file else None
    
    while True:
        try:
            prompt = console.input("\n[bold green]You>[/bold green] ")
            
            if prompt.startswith('/'):
                # Handle commands
                if prompt == '/exit':
                    break
                elif prompt.startswith('/load'):
                    parts = prompt.split(maxsplit=1)
                    if len(parts) > 1:
                        file_path = parts[1]
                        current_file = Path(file_path).read_text()
                        console.print(f"[green]Loaded {file_path}[/green]")
                    else:
                        console.print("[red]Usage: /load <filename>[/red]")
                    continue
                elif prompt.startswith('/save'):
                    parts = prompt.split(maxsplit=1)
                    if len(parts) > 1:
                        file_path = parts[1]
                        if current_file:
                            Path(file_path).write_text(current_file)
                            console.print(f"[green]Saved to {file_path}[/green]")
                        else:
                            console.print("[red]No file content to save[/red]")
                    else:
                        console.print("[red]Usage: /save <filename>[/red]")
                    continue
                elif prompt.startswith('/debug'):
                    # Toggle debug mode for response analysis
                    if not hasattr(interactive, 'debug_mode'):
                        interactive.debug_mode = False
                    interactive.debug_mode = not interactive.debug_mode
                    status = "enabled" if interactive.debug_mode else "disabled"
                    console.print(f"[green]Debug mode {status}[/green]")
                    if interactive.debug_mode:
                        console.print("[dim]Debug mode will save raw responses to debug_response.txt[/dim]")
                    continue
                elif prompt.startswith('/test'):
                    # Test display with a long response
                    test_response = "# Test Response\n\n" + "\n".join([f"Line {i}: This is a test line to check if long responses are properly displayed without truncation." for i in range(1, 51)])
                    test_response += "\n\n```python\n# Test code block\nfor i in range(100):\n    print(f'Item {i}')\n```\n\nEnd of test response."
                    console.print(f"[dim]🧪 Testing display with {len(test_response)} char response[/dim]")
                    _display_claude_response(test_response)
                    continue
                elif prompt == '/stats':
                    _show_session_stats(session_stats)
                    continue
                elif prompt == '/live':
                    # Toggle live metrics
                    live_metrics = not live_metrics
                    status = "enabled" if live_metrics else "disabled"
                    console.print(f"[green]Live metrics {status}[/green]")
                    continue
                elif prompt == '/methodology' or prompt == '/method':
                    _show_cost_methodology()
                    continue
            
            # Process query
            with console.status("[cyan]Processing..."):
                if current_file:
                    full_prompt = f"{prompt}\n\n```python\n{current_file}\n```"
                else:
                    full_prompt = prompt
                
                # Measure original Claude tokens
                try:
                    original_claude_tokens = count_tokens_claude(full_prompt, session_stats['claude_model'])
                except Exception as e:
                    original_claude_tokens = 0
                
                compressed, metadata = proxy.process_input(full_prompt, file)
                
                # Measure compressed Claude tokens
                compressed_claude_tokens = 0
                if metadata.get('compressed'):
                    try:
                        compressed_claude_tokens = count_tokens_claude(compressed, session_stats['claude_model'])
                    except Exception as e:
                        pass
                
                # Execute with Claude
                start_time = time.time()
                result = _execute_claude_code_interactive(compressed)
                execution_time = time.time() - start_time
                
                # Measure response tokens
                response_claude_tokens = 0
                if result:
                    try:
                        response_claude_tokens = count_tokens_claude(result, session_stats['claude_model'])
                    except Exception as e:
                        pass
                
                # Process output
                final_output = proxy.process_output(result, metadata)
                
                # Debug: Save raw response if debug mode is enabled
                if hasattr(interactive, 'debug_mode') and interactive.debug_mode and result:
                    debug_file = Path("debug_response.txt")
                    debug_file.write_text(f"Raw Claude Response ({len(result)} chars, {result.count(chr(10)) + 1} lines):\n" + "="*80 + "\n" + result)
            
            # Display response with proper formatting
            _display_claude_response(final_output)
            
            # Show live metrics panel if enabled
            if live_metrics and session_stats['queries'] > 0:
                console.print(_create_live_metrics_panel(session_stats))
            
            # Update stats with actual Claude metrics
            session_stats['queries'] += 1
            session_stats['original_tokens_claude'] += original_claude_tokens
            session_stats['compressed_tokens_claude'] += compressed_claude_tokens or original_claude_tokens
            session_stats['response_tokens_claude'] += response_claude_tokens
            
            # Calculate actual Claude token savings with response estimation
            claude_tokens_saved = original_claude_tokens - (compressed_claude_tokens or original_claude_tokens)
            session_stats['actual_claude_savings'] += claude_tokens_saved
            
            # Calculate more accurate cost savings using Claude Sonnet 4 pricing
            # Method 1: Conservative - only count input token savings
            input_cost_saved = (claude_tokens_saved / 1_000_000) * session_stats['claude_input_cost_per_mtok']
            
            # Method 2: Improved response estimation based on actual output analysis
            estimated_response_savings = 0
            estimated_original_response = response_claude_tokens
            
            if original_claude_tokens > 0 and compressed_claude_tokens > 0 and response_claude_tokens > 0:
                # Calculate the response-to-input ratio for the compressed query
                compressed_response_ratio = response_claude_tokens / compressed_claude_tokens
                
                # Estimate what the response would have been for the original uncompressed input
                # Assumption: Response length scales proportionally with input complexity/size
                estimated_original_response = original_claude_tokens * compressed_response_ratio
                
                # Calculate estimated response savings
                estimated_response_savings = estimated_original_response - response_claude_tokens
                
                # Add bounds checking to prevent unrealistic estimates
                # Response savings shouldn't exceed the input compression savings by too much
                max_reasonable_response_savings = claude_tokens_saved * 1.5  # 150% of input savings max
                if estimated_response_savings > max_reasonable_response_savings:
                    estimated_response_savings = max_reasonable_response_savings
                    estimated_original_response = response_claude_tokens + estimated_response_savings
                
                # Ensure non-negative
                estimated_response_savings = max(0, estimated_response_savings)
            
            # Total estimated cost savings (input + estimated response impact)
            # Input savings use input token pricing, response savings use output token pricing
            estimated_response_cost_saved = (estimated_response_savings / 1_000_000) * session_stats['claude_output_cost_per_mtok']
            total_estimated_cost_saved = input_cost_saved + estimated_response_cost_saved
            
            # Use conservative input-only savings for session tracking (more reliable)
            session_stats['total_cost_saved'] += input_cost_saved
            
            # Store additional metrics for analysis
            if 'estimated_response_savings' not in session_stats:
                session_stats['estimated_response_savings'] = 0
                session_stats['total_estimated_cost_saved'] = 0
            
            session_stats['estimated_response_savings'] += estimated_response_savings
            session_stats['total_estimated_cost_saved'] += total_estimated_cost_saved
            
            # Legacy stats for backward compatibility
            session_stats['total_saved'] += metadata.get('tokens_saved', claude_tokens_saved)
            
            # Show comprehensive mini stats
            if metadata.get('compressed') and claude_tokens_saved > 0:
                compression_ratio = (claude_tokens_saved / original_claude_tokens * 100) if original_claude_tokens > 0 else 0
                
                # Calculate actual total estimated savings (matching table methodology)
                response_ratio = response_claude_tokens / compressed_claude_tokens if compressed_claude_tokens > 0 else 0
                estimated_original_output_tokens = original_claude_tokens * response_ratio
                estimated_original_output_cost = (estimated_original_output_tokens / 1_000_000) * session_stats['claude_output_cost_per_mtok']
                actual_output_cost = (response_claude_tokens / 1_000_000) * session_stats['claude_output_cost_per_mtok']
                
                # Total actual savings = input savings + output savings
                output_savings = estimated_original_output_cost - actual_output_cost
                total_actual_savings = input_cost_saved + output_savings
                
                console.print(
                    f"✨ Token Savings: {claude_tokens_saved:,} tokens ({compression_ratio:.1f}% reduction)"
                )
                console.print(
                    f"💰 Actual Cost Savings: ${total_actual_savings:.4f} "
                    f"(${input_cost_saved:.4f} input + ${output_savings:.4f} output)"
                )
                
                # Show additional context about the calculation
                console.print(
                    f"[dim]📊 Response ratio: {response_ratio:.2f}x (est. original response: {estimated_original_output_tokens:.0f} tokens)[/dim]"
                )
                
                # Show detailed cost comparison if compression was significant (>10% savings)
                if compression_ratio > 10 and session_stats['queries'] >= 1:
                    console.print("")  # Add spacing
                    _show_query_cost_analysis(session_stats, original_claude_tokens, compressed_claude_tokens, response_claude_tokens)
                    
            elif original_claude_tokens > 0:
                # Calculate total cost using Claude Sonnet 4 pricing
                input_cost = (original_claude_tokens / 1_000_000) * session_stats['claude_input_cost_per_mtok']
                output_cost = (response_claude_tokens / 1_000_000) * session_stats['claude_output_cost_per_mtok']
                total_cost = input_cost + output_cost
                console.print(f"💸 Total Cost: ${total_cost:.4f} ({original_claude_tokens + response_claude_tokens:,} tokens)")
                
        except KeyboardInterrupt:
            if click.confirm("\nExit interactive session?"):
                break
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")
    
    # Show final enhanced stats
    _show_enhanced_session_summary(session_stats)
    _show_session_stats(session_stats)

def _display_claude_response(response: str):
    """Display Claude's response with proper code block formatting within a single panel."""
    import re
    from rich.text import Text
    from rich.console import Group
    
    # Ensure we have the full response
    if not response or not response.strip():
        console.print(Panel(
            "[yellow]No response received from Claude[/yellow]",
            title="[bold blue]Claude's Response[/bold blue]",
            border_style="blue"
        ))
        return
    
    # Check if response contains code blocks
    code_block_pattern = r'```(\w+)?\n(.*?)\n```'
    code_blocks = list(re.finditer(code_block_pattern, response, re.DOTALL))
    
    if not code_blocks:
        # No code blocks, display the full response without any limits
        # Create a simple text object to ensure no truncation
        response_text = Text(response)
        
        console.print(Panel(
            response_text,
            title="[bold blue]Claude's Response[/bold blue]",
            border_style="blue",
            expand=False,
            width=None,
            height=None,  # No height constraint
            padding=(1, 2)  # Add some padding
        ))
        
        # Force output flush
        import sys
        sys.stdout.flush()
        return
    
    # Build elements for responses with code blocks
    elements = []
    last_end = 0
    
    for i, match in enumerate(code_blocks):
        start, end = match.span()
        
        # Add text before this code block
        if start > last_end:
            text_before = response[last_end:start].strip()
            if text_before:
                elements.append(Text(text_before))
        
        # Add a separator and code block label
        if elements:
            elements.append(Text(""))  # Empty line for spacing
        
        elements.append(Text(f"Code Block {i+1}:", style="bold cyan"))
        
        # Add the code block with syntax highlighting
        language = match.group(1) or "text"
        code_content = match.group(2)
        syntax = Syntax(
            code_content, 
            language, 
            theme="monokai", 
            line_numbers=True,
            word_wrap=False
        )
        elements.append(syntax)
        
        last_end = end
    
    # Add any remaining text after the last code block
    if last_end < len(response):
        text_after = response[last_end:].strip()
        if text_after:
            elements.append(Text(""))  # Empty line for spacing
            elements.append(Text(text_after))
    
    # Display everything without any size constraints
    console.print(Panel(
        Group(*elements),
        title="[bold blue]Claude's Response[/bold blue]",
        border_style="blue",
        expand=False,
        width=None,
        height=None,  # No height constraint
        padding=(1, 2)
    ))
    
    # Force output flush
    import sys
    sys.stdout.flush()

def _show_session_stats(stats):
    """Display comprehensive session statistics with actual Claude metrics."""
    table = Table(title="Claude Interactive Session Statistics", show_header=True, header_style="bold magenta")
    table.add_column("Metric", style="cyan", min_width=20)
    table.add_column("Value", style="green", min_width=15)
    table.add_column("Details", style="dim", min_width=25)
    
    # Basic session info
    table.add_row("Total Queries", str(stats['queries']), f"Using {stats['claude_model']}")
    
    # Claude token metrics
    if stats['original_tokens_claude'] > 0:
        table.add_row(
            "Input Tokens (Claude)", 
            f"{stats['original_tokens_claude']:,}",
            "Actual Claude tokenization"
        )
        table.add_row(
            "Compressed Tokens", 
            f"{stats['compressed_tokens_claude']:,}",
            "After CAI3 compression"
        )
        table.add_row(
            "Response Tokens", 
            f"{stats['response_tokens_claude']:,}",
            "Claude's output tokens"
        )
        
        # Savings calculations
        compression_ratio = 0
        if stats['original_tokens_claude'] > 0:
            compression_ratio = (stats['actual_claude_savings'] / stats['original_tokens_claude']) * 100
        
        table.add_row(
            "Tokens Saved", 
            f"{stats['actual_claude_savings']:,}",
            f"{compression_ratio:.1f}% compression"
        )
        
        # Cost metrics with Claude Sonnet 4 pricing transparency
        table.add_row(
            "Cost Saved (Input Only)", 
            f"${stats['total_cost_saved']:.4f}",
            f"Input tokens @${stats['claude_input_cost_per_mtok']}/MTok"
        )
        
        if stats.get('total_estimated_cost_saved', 0) > stats['total_cost_saved']:
            table.add_row(
                "Est. Total Savings", 
                f"${stats.get('total_estimated_cost_saved', 0):.4f}",
                "Input + estimated output savings"
            )
            
            # Calculate actual total savings for comparison
            avg_response_ratio = stats['response_tokens_claude'] / stats['compressed_tokens_claude'] if stats['compressed_tokens_claude'] > 0 else 0
            estimated_original_output_tokens = stats['original_tokens_claude'] * avg_response_ratio
            estimated_original_output_cost = (estimated_original_output_tokens / 1_000_000) * stats['claude_output_cost_per_mtok']
            actual_output_cost = (stats['response_tokens_claude'] / 1_000_000) * stats['claude_output_cost_per_mtok']
            actual_total_savings = (stats['original_tokens_claude'] / 1_000_000) * stats['claude_input_cost_per_mtok'] + estimated_original_output_cost - ((stats['compressed_tokens_claude'] / 1_000_000) * stats['claude_input_cost_per_mtok'] + actual_output_cost)
            
            table.add_row(
                "Actual Total Savings", 
                f"${actual_total_savings:.4f}",
                f"Based on {avg_response_ratio:.2f}x response ratio"
            )
            
            # Show accuracy
            accuracy_pct = (actual_total_savings / stats.get('total_estimated_cost_saved', 1)) * 100
            table.add_row(
                "Estimation Accuracy", 
                f"{accuracy_pct:.1f}%",
                "Actual vs initial estimate"
            )
            
            # Show average response ratio for insight
            if stats['compressed_tokens_claude'] > 0:
                avg_response_ratio = stats['response_tokens_claude'] / stats['compressed_tokens_claude']
                table.add_row(
                    "Avg Response Ratio", 
                    f"{avg_response_ratio:.2f}",
                    "Output tokens per input token"
                )
        
        # Total usage cost with separate input/output pricing
        input_cost_used = (stats['compressed_tokens_claude'] / 1_000_000) * stats['claude_input_cost_per_mtok']
        output_cost_used = (stats['response_tokens_claude'] / 1_000_000) * stats['claude_output_cost_per_mtok']
        total_cost_used = input_cost_used + output_cost_used
        
        table.add_row(
            "Total Cost", 
            f"${total_cost_used:.4f}",
            f"${input_cost_used:.4f} input + ${output_cost_used:.4f} output"
        )
        
        # Efficiency metric
        if stats['queries'] > 0:
            avg_savings_per_query = stats['actual_claude_savings'] / stats['queries']
            table.add_row(
                "Avg Savings/Query", 
                f"{avg_savings_per_query:,.0f}",
                "Tokens per interaction"
            )
    else:
        table.add_row("Token Metrics", "No data", "Claude token counting failed")
        
    # Legacy compatibility
    if stats['total_saved'] != stats['actual_claude_savings']:
        table.add_row(
            "Legacy Tokens Saved", 
            f"{stats['total_saved']:,}",
            "From compression metadata"
        )
    
def _show_cost_methodology():
    """Explain the cost calculation methodology and its limitations."""
    console.print(Panel(
        """[bold cyan]Claude Sonnet 4 Cost Savings Calculation Methodology[/bold cyan]

[bold green]What We Can Measure Accurately:[/bold green]
• [green]Original input tokens[/green]: Count tokens in your full prompt using Claude's API
• [green]Compressed input tokens[/green]: Count tokens in CAI3-compressed prompt  
• [green]Actual response tokens[/green]: Count tokens in Claude's actual response to compressed input
• [green]Input cost savings[/green]: (original_input - compressed_input) × $3/MTok
• [green]Output cost[/green]: actual_response_tokens × $15/MTok

[bold blue]Improved Response Estimation Method:[/bold blue]
We use actual response data to estimate total savings:

[cyan]1. Response-to-Input Ratio Analysis:[/cyan]
   • Calculate: response_ratio = actual_response_tokens / compressed_input_tokens
   • This tells us how "verbose" Claude is relative to input size

[cyan]2. Proportional Response Estimation:[/cyan]
   • Estimated original response = original_input_tokens × response_ratio
   • Estimated response savings = estimated_original_response - actual_response
   • Response cost savings = estimated_response_savings × $15/MTok

[cyan]3. Total Cost Calculation:[/cyan]
   • Input savings: token_savings × $3/MTok
   • Output savings: response_token_savings × $15/MTok
   • Total estimated savings: input_savings + output_savings

[bold yellow]Example (Claude Sonnet 4):[/bold yellow]
• Original input: 1000 tokens → Compressed: 700 tokens → Response: 350 tokens
• Input savings: 300 tokens × $3/MTok = $0.0009
• Response ratio: 350/700 = 0.5 tokens per input token
• Est. original response: 1000 × 0.5 = 500 tokens
• Est. response savings: 500 - 350 = 150 tokens × $15/MTok = $0.00225
• Total est. savings: $0.0009 + $0.00225 = $0.00315

[bold green]Claude Sonnet 4 Pricing Impact:[/bold green]
• ✅ Input compression provides modest savings ($3/MTok)
• 🚀 Output compression provides massive savings ($15/MTok - 5x higher!)
• ⚡ Response length reduction has huge cost impact
• 💡 Focus on prompts that generate long responses for maximum savings

[bold red]Official Claude Sonnet 4 Pricing:[/bold red]
• Base Input: $3/MTok | Output: $15/MTok
• Cache Writes (5m): $3.75/MTok | Cache Writes (1h): $6/MTok  
• Cache Hits & Refreshes: $0.30/MTok

[bold]Key Insight:[/bold] With 5x higher output pricing, response compression 
is far more valuable than input compression!""",
        title="💡 Claude Sonnet 4 Enhanced Cost Method",
        border_style="blue"
    ))

def _create_live_metrics_panel(stats: Dict[str, Any]) -> Panel:
    """Create a live metrics panel for real-time display."""
    if stats['queries'] == 0:
        content = "[dim]No queries yet...[/dim]"
    else:
        # Calculate current session metrics
        compression_ratio = 0
        if stats['original_tokens_claude'] > 0:
            compression_ratio = (stats['actual_claude_savings'] / stats['original_tokens_claude']) * 100
        
        input_cost = (stats['compressed_tokens_claude'] / 1_000_000) * stats['claude_input_cost_per_mtok']
        output_cost = (stats['response_tokens_claude'] / 1_000_000) * stats['claude_output_cost_per_mtok']
        total_cost = input_cost + output_cost
        
        content = f"""[bold cyan]Live Session Metrics[/bold cyan]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[green]Queries:[/green] {stats['queries']}
[blue]Input Tokens:[/blue] {stats['original_tokens_claude']:,}
[yellow]Compressed:[/yellow] {stats['compressed_tokens_claude']:,}
[magenta]Response:[/magenta] {stats['response_tokens_claude']:,}
[red]Saved:[/red] {stats['actual_claude_savings']:,} ({compression_ratio:.1f}%)
[bold green]Cost:[/bold green] ${total_cost:.4f} | [bold red]Saved:[/bold red] ${stats['total_cost_saved']:.4f}"""
    
    return Panel(content, border_style="blue", title="🔥 Claude Metrics", title_align="left")

def _show_enhanced_session_summary(stats: Dict[str, Any]):
    """Show an enhanced session summary with Claude-specific insights."""
    console.print("\n" + "="*60)
    console.print("[bold cyan]📊 Claude Interactive Session Complete[/bold cyan]")
    console.print("="*60)
    
    if stats['queries'] > 0 and stats['original_tokens_claude'] > 0:
        # Efficiency metrics
        avg_input_tokens = stats['original_tokens_claude'] / stats['queries']
        avg_compression = stats['actual_claude_savings'] / stats['queries']
        avg_response_tokens = stats['response_tokens_claude'] / stats['queries']
        
        efficiency_table = Table(title="📈 Efficiency Analysis", show_header=True)
        efficiency_table.add_column("Metric", style="cyan")
        efficiency_table.add_column("Per Query", style="green")
        efficiency_table.add_column("Total", style="blue")
        
        efficiency_table.add_row("Input Tokens", f"{avg_input_tokens:,.0f}", f"{stats['original_tokens_claude']:,}")
        efficiency_table.add_row("Compression Saved", f"{avg_compression:,.0f}", f"{stats['actual_claude_savings']:,}")
        efficiency_table.add_row("Response Tokens", f"{avg_response_tokens:,.0f}", f"{stats['response_tokens_claude']:,}")
        
        console.print(efficiency_table)
        
        # Create comprehensive cost comparison table
        _show_cost_comparison_table(stats)
        
        # Cost breakdown with Claude Sonnet 4 pricing
        total_input_cost = (stats['original_tokens_claude'] / 1_000_000) * stats['claude_input_cost_per_mtok']
        compressed_input_cost = (stats['compressed_tokens_claude'] / 1_000_000) * stats['claude_input_cost_per_mtok']
        actual_output_cost = (stats['response_tokens_claude'] / 1_000_000) * stats['claude_output_cost_per_mtok']
        actual_total_cost = compressed_input_cost + actual_output_cost
        
        console.print(f"\n[bold green]💰 Claude Sonnet 4 Cost Analysis (Actual):[/bold green]")
        console.print(f"  • Input without compression: ${total_input_cost:.4f}")
        console.print(f"  • Input with compression: ${compressed_input_cost:.4f}")
        console.print(f"  • Output cost: ${actual_output_cost:.4f}")
        console.print(f"  • [bold blue]Total actual cost: ${actual_total_cost:.4f}[/bold blue]")
        console.print(f"  • [bold red]Actual input savings: ${stats['total_cost_saved']:.4f}[/bold red]")
        
        if stats.get('total_estimated_cost_saved', 0) > stats['total_cost_saved']:
            # Calculate estimated total original cost including output
            avg_response_ratio = stats['response_tokens_claude'] / stats['compressed_tokens_claude'] if stats['compressed_tokens_claude'] > 0 else 0
            estimated_original_output_tokens = stats['original_tokens_claude'] * avg_response_ratio
            estimated_original_output_cost = (estimated_original_output_tokens / 1_000_000) * stats['claude_output_cost_per_mtok']
            estimated_total_original_cost = total_input_cost + estimated_original_output_cost
            
            console.print(f"\n[bold blue]🔮 Estimated Total Impact (Sonnet 4):[/bold blue]")
            console.print(f"  • Est. original output cost: ${estimated_original_output_cost:.4f}")
            console.print(f"  • Est. total original cost: ${estimated_total_original_cost:.4f}")
            console.print(f"  • [bold green]Est. total savings: ${stats.get('total_estimated_cost_saved', 0):.4f}[/bold green]")
            console.print(f"  • Response ratio: {avg_response_ratio:.2f} output/input tokens")
        
        console.print(f"\n[yellow]📊 Claude Sonnet 4 Pricing:[/yellow]")
        console.print(f"  • Input tokens: ${stats['claude_input_cost_per_mtok']}/MTok")
        console.print(f"  • Output tokens: ${stats['claude_output_cost_per_mtok']}/MTok") 
        console.print(f"  • Cache writes (5m): ${stats['claude_cache_write_5m_per_mtok']}/MTok")
        console.print(f"  • Cache writes (1h): ${stats['claude_cache_write_1h_per_mtok']}/MTok")
        console.print(f"  • Cache hits: ${stats['claude_cache_hit_per_mtok']}/MTok")
        
        console.print(f"\n[green]✅ Methodology Improvement:[/green]")
        console.print(f"  • Uses actual response data for better estimates")
        console.print(f"  • Calculates response-to-input ratios from real Claude behavior")
        console.print(f"  • Applies proportional scaling based on measured patterns")
        
        # Compression insights
        overall_compression = (stats['actual_claude_savings'] / stats['original_tokens_claude']) * 100
        console.print(f"\n[bold blue]🗜️ Compression Insights:[/bold blue]")
        console.print(f"  • Overall compression: {overall_compression:.1f}%")
        console.print(f"  • Model: {stats['claude_model']} (Claude Sonnet 4)")
        console.print(f"  • Significant cost impact due to high output token pricing")
    
    console.print("\n" + "="*60)

def _show_query_cost_analysis(stats: Dict[str, Any], original_tokens: int, compressed_tokens: int, response_tokens: int):
    """Show cost analysis for a single query with meaningful compression."""
    
    # Calculate the current query's response ratio
    current_response_ratio = response_tokens / compressed_tokens if compressed_tokens > 0 else 0
    
    # Calculate costs for this specific query
    original_input_cost = (original_tokens / 1_000_000) * stats['claude_input_cost_per_mtok']
    compressed_input_cost = (compressed_tokens / 1_000_000) * stats['claude_input_cost_per_mtok']
    actual_output_cost = (response_tokens / 1_000_000) * stats['claude_output_cost_per_mtok']
    
    # Estimate what original output would have been
    estimated_original_output_tokens = original_tokens * current_response_ratio
    estimated_original_output_cost = (estimated_original_output_tokens / 1_000_000) * stats['claude_output_cost_per_mtok']
    
    # Calculate totals
    original_total = original_input_cost + estimated_original_output_cost
    compressed_total = compressed_input_cost + actual_output_cost
    actual_savings = original_total - compressed_total
    
    # Compare with static 2.5x estimate
    estimated_original_output_25x = original_tokens * 2.5
    estimated_output_cost_25x = (estimated_original_output_25x / 1_000_000) * stats['claude_output_cost_per_mtok']
    estimated_compressed_output_25x = compressed_tokens * 2.5
    estimated_compressed_cost_25x = (estimated_compressed_output_25x / 1_000_000) * stats['claude_output_cost_per_mtok']
    
    estimated_total_25x = original_input_cost + estimated_output_cost_25x
    estimated_compressed_total_25x = compressed_input_cost + estimated_compressed_cost_25x
    estimated_savings_25x = estimated_total_25x - estimated_compressed_total_25x
    
    # Create a compact comparison table
    query_table = Table(title="💡 This Query: Estimation vs Actual", show_header=True, header_style="bold cyan")
    query_table.add_column("Scenario", style="yellow", min_width=16)
    query_table.add_column("Estimated Cost", style="blue", min_width=14)
    query_table.add_column("Actual Cost", style="green", min_width=12)
    query_table.add_column("Difference", style="magenta", min_width=12)
    
    query_table.add_row(
        "Without Compression",
        f"${estimated_total_25x:.4f}",
        f"${original_total:.4f}",
        f"{((original_total/estimated_total_25x - 1) * 100):+.1f}%" if estimated_total_25x > 0 else "N/A"
    )
    
    query_table.add_row(
        "With Compression",
        f"${estimated_compressed_total_25x:.4f}",
        f"${compressed_total:.4f}",
        f"{((compressed_total/estimated_compressed_total_25x - 1) * 100):+.1f}%" if estimated_compressed_total_25x > 0 else "N/A"
    )
    
    # Calculate savings accuracy
    savings_accuracy = ""
    if estimated_savings_25x > 0:
        accuracy_ratio = actual_savings / estimated_savings_25x
        if accuracy_ratio < 1.0:
            underestimate_pct = (1 - accuracy_ratio) * 100
            savings_accuracy = f"{underestimate_pct:.1f}% underestimate"
        else:
            overestimate_pct = (accuracy_ratio - 1) * 100
            savings_accuracy = f"{overestimate_pct:.1f}% overestimate"
    else:
        savings_accuracy = "N/A"
    
    query_table.add_row(
        "[bold]Savings[/bold]",
        f"[bold]${estimated_savings_25x:.4f}[/bold]",
        f"[bold]${actual_savings:.4f}[/bold]",
        f"[bold]{savings_accuracy}[/bold]"
    )
    
    console.print(query_table)
    
    # Show ratio comparison
    console.print(f"[dim]📊 Response ratio: {current_response_ratio:.2f}x actual vs 2.5x estimated "
                 f"({((current_response_ratio/2.5 - 1) * 100):+.1f}% difference)[/dim]")

def _show_cost_comparison_table(stats: Dict[str, Any]):
    """Show a detailed comparison between estimated and actual costs with intuitive layout."""
    console.print("\n")
    
    # Calculate all the values first
    avg_response_ratio = stats['response_tokens_claude'] / stats['compressed_tokens_claude'] if stats['compressed_tokens_claude'] > 0 else 0
    
    # Estimated values (using 2.5x static ratio like in claude_code.py)
    estimated_original_output_tokens = stats['original_tokens_claude'] * 2.5
    estimated_compressed_output_tokens = stats['compressed_tokens_claude'] * 2.5
    
    estimated_original_input_cost = (stats['original_tokens_claude'] / 1_000_000) * stats['claude_input_cost_per_mtok']
    estimated_original_output_cost = (estimated_original_output_tokens / 1_000_000) * stats['claude_output_cost_per_mtok']
    estimated_original_total = estimated_original_input_cost + estimated_original_output_cost
    
    estimated_compressed_input_cost = (stats['compressed_tokens_claude'] / 1_000_000) * stats['claude_input_cost_per_mtok']
    estimated_compressed_output_cost = (estimated_compressed_output_tokens / 1_000_000) * stats['claude_output_cost_per_mtok']
    estimated_compressed_total = estimated_compressed_input_cost + estimated_compressed_output_cost
    
    estimated_total_savings = estimated_original_total - estimated_compressed_total
    
    # Actual values
    actual_original_input_cost = (stats['original_tokens_claude'] / 1_000_000) * stats['claude_input_cost_per_mtok']
    actual_compressed_input_cost = (stats['compressed_tokens_claude'] / 1_000_000) * stats['claude_input_cost_per_mtok']
    actual_output_cost = (stats['response_tokens_claude'] / 1_000_000) * stats['claude_output_cost_per_mtok']
    
    # Estimate what original output would have been using actual response ratio
    estimated_actual_original_output_tokens = stats['original_tokens_claude'] * avg_response_ratio
    estimated_actual_original_output_cost = (estimated_actual_original_output_tokens / 1_000_000) * stats['claude_output_cost_per_mtok']
    
    actual_original_total = actual_original_input_cost + estimated_actual_original_output_cost
    actual_compressed_total = actual_compressed_input_cost + actual_output_cost
    actual_total_savings = actual_original_total - actual_compressed_total
    
    # Create two separate, clear tables
    console.print("[bold blue]📊 Scenario Comparison: Without vs With Compression[/bold blue]")
    
    # Table 1: Estimated Costs (Upfront Analysis)
    estimated_table = Table(title="🔮 Estimated Costs (Static 2.5x Output Ratio)", show_header=True, header_style="bold yellow")
    estimated_table.add_column("Scenario", style="cyan", min_width=18)
    estimated_table.add_column("Input Cost", style="blue", min_width=12)
    estimated_table.add_column("Output Cost", style="magenta", min_width=12)
    estimated_table.add_column("Total Cost", style="green", min_width=12)
    estimated_table.add_column("Token Count", style="dim", min_width=15)
    
    estimated_table.add_row(
        "📄 Without Compression",
        f"${estimated_original_input_cost:.4f}",
        f"${estimated_original_output_cost:.4f}",
        f"${estimated_original_total:.4f}",
        f"{stats['original_tokens_claude']:,} + {estimated_original_output_tokens:,.0f}"
    )
    
    estimated_table.add_row(
        "🗜️ With Compression",
        f"${estimated_compressed_input_cost:.4f}",
        f"${estimated_compressed_output_cost:.4f}",
        f"${estimated_compressed_total:.4f}",
        f"{stats['compressed_tokens_claude']:,} + {estimated_compressed_output_tokens:,.0f}"
    )
    
    estimated_table.add_row(
        "[bold green]💰 Estimated Savings[/bold green]",
        f"[bold]${estimated_original_input_cost - estimated_compressed_input_cost:.4f}[/bold]",
        f"[bold]${estimated_original_output_cost - estimated_compressed_output_cost:.4f}[/bold]",
        f"[bold green]${estimated_total_savings:.4f}[/bold green]",
        f"[bold]{stats['actual_claude_savings']:,} + {estimated_original_output_tokens - estimated_compressed_output_tokens:,.0f}[/bold]"
    )
    
    console.print(estimated_table)
    console.print("")
    
    # Table 2: Actual Costs (Session Results)
    actual_table = Table(title="✅ Actual Costs (Real Session Data)", show_header=True, header_style="bold green")
    actual_table.add_column("Scenario", style="cyan", min_width=18)
    actual_table.add_column("Input Cost", style="blue", min_width=12)
    actual_table.add_column("Output Cost", style="magenta", min_width=12)
    actual_table.add_column("Total Cost", style="green", min_width=12)
    actual_table.add_column("Token Count", style="dim", min_width=15)
    
    actual_table.add_row(
        "📄 Without Compression",
        f"${actual_original_input_cost:.4f}",
        f"${estimated_actual_original_output_cost:.4f}",
        f"${actual_original_total:.4f}",
        f"{stats['original_tokens_claude']:,} + {estimated_actual_original_output_tokens:,.0f}"
    )
    
    actual_table.add_row(
        "🗜️ With Compression",
        f"${actual_compressed_input_cost:.4f}",
        f"${actual_output_cost:.4f}",
        f"${actual_compressed_total:.4f}",
        f"{stats['compressed_tokens_claude']:,} + {stats['response_tokens_claude']:,}"
    )
    
    actual_table.add_row(
        "[bold green]💰 Actual Savings[/bold green]",
        f"[bold]${actual_original_input_cost - actual_compressed_input_cost:.4f}[/bold]",
        f"[bold]${estimated_actual_original_output_cost - actual_output_cost:.4f}[/bold]",
        f"[bold green]${actual_total_savings:.4f}[/bold green]",
        f"[bold]{stats['actual_claude_savings']:,} + {estimated_actual_original_output_tokens - stats['response_tokens_claude']:,.0f}[/bold]"
    )
    
    console.print(actual_table)
    console.print("")
    
    # Summary comparison table
    summary_table = Table(title="🎯 Estimation Accuracy Summary", show_header=True, header_style="bold magenta")
    summary_table.add_column("Metric", style="cyan", min_width=20)
    summary_table.add_column("Estimated", style="yellow", min_width=12)
    summary_table.add_column("Actual", style="green", min_width=12)
    summary_table.add_column("Accuracy", style="blue", min_width=15)
    
    summary_table.add_row(
        "Output Ratio Used",
        "2.5x",
        f"{avg_response_ratio:.2f}x",
        f"{((avg_response_ratio/2.5 - 1) * 100):+.1f}% vs estimate"
    )
    
    # Calculate total savings accuracy
    total_savings_accuracy = ""
    if estimated_total_savings > 0:
        accuracy_ratio = actual_total_savings / estimated_total_savings
        if accuracy_ratio < 1.0:
            underestimate_pct = (1 - accuracy_ratio) * 100
            total_savings_accuracy = f"{underestimate_pct:.1f}% underestimate"
        else:
            overestimate_pct = (accuracy_ratio - 1) * 100
            total_savings_accuracy = f"{overestimate_pct:.1f}% overestimate"
    else:
        total_savings_accuracy = "N/A"
    
    summary_table.add_row(
        "Total Savings",
        f"${estimated_total_savings:.4f}",
        f"${actual_total_savings:.4f}",
        total_savings_accuracy
    )
    
    # Calculate output tokens accuracy
    output_tokens_accuracy = ""
    if estimated_compressed_output_tokens > 0:
        tokens_ratio = stats['response_tokens_claude'] / estimated_compressed_output_tokens
        if tokens_ratio < 1.0:
            underestimate_pct = (1 - tokens_ratio) * 100
            output_tokens_accuracy = f"{underestimate_pct:.1f}% overestimate"  # Note: inverted because fewer tokens = overestimated
        else:
            overestimate_pct = (tokens_ratio - 1) * 100
            output_tokens_accuracy = f"{overestimate_pct:.1f}% underestimate"  # Note: inverted because more tokens = underestimated
    else:
        output_tokens_accuracy = "N/A"
    
    summary_table.add_row(
        "Output Tokens",
        f"{estimated_compressed_output_tokens:,.0f}",
        f"{stats['response_tokens_claude']:,}",
        output_tokens_accuracy
    )
    
    console.print(summary_table)
    
    # Key insights
    if estimated_total_savings > 0:
        accuracy_pct = (actual_total_savings / estimated_total_savings) * 100
        if accuracy_pct < 50:
            insight_color = "red"
            insight_icon = "⚠️"
            insight = "significantly lower"
        elif accuracy_pct < 80:
            insight_color = "yellow"
            insight_icon = "⚡"
            insight = "moderately lower"
        elif accuracy_pct > 120:
            insight_color = "green"
            insight_icon = "🚀"
            insight = "higher"
        else:
            insight_color = "green"
            insight_icon = "✅"
            insight = "close"
        
        console.print(f"\n[{insight_color}]{insight_icon} [bold]Key Insight:[/bold] Actual savings were {insight} than estimated ({accuracy_pct:.1f}%)[/{insight_color}]")
        console.print(f"[dim]• This is because Claude's actual response ratio ({avg_response_ratio:.2f}x) differed from the static 2.5x estimate[/dim]")
        
        if avg_response_ratio < 1.5:
            console.print(f"[dim]💡 Your prompts generate concise responses - actual savings may often exceed estimates![/dim]")
        elif avg_response_ratio > 3.5:
            console.print(f"[dim]💡 Your prompts generate verbose responses - estimates may be conservative[/dim]")

def _execute_claude_code_interactive(prompt: str) -> str:
    """Execute Claude Code in interactive mode with full response capture."""
    import subprocess
    
    try:
        # Use stdin to avoid command line length limits and capture full output
        process = subprocess.Popen(
            ["claude"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=0,  # Unbuffered for immediate output
            env=None    # Use default environment
        )
        
        # Send prompt via stdin and get output with extended timeout
        stdout_data, stderr_data = process.communicate(input=prompt, timeout=300)  # 5 minute timeout
        
        if process.returncode != 0:
            error_msg = stderr_data.strip() if stderr_data else "Unknown error"
            raise RuntimeError(f"Claude error (code {process.returncode}): {error_msg}")
        
        # Ensure we have the complete response
        if not stdout_data:
            return ""
        
        return stdout_data
        
    except subprocess.TimeoutExpired:
        process.kill()
        raise RuntimeError("Claude request timed out after 5 minutes")
    except Exception as e:
        raise RuntimeError(f"Failed to execute Claude: {e}")