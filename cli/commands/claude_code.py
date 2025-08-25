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
from typing import Optional, Dict, Any, Tuple
from rich.console import Console, Group
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
from rich.table import Table
from rich.panel import Panel
from rich.syntax import Syntax
from rich.text import Text
import re

# Import existing OptimizeAI components
project_root = str(Path(__file__).parent.parent.parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Import Claude token metrics
try:
    from optimize_ai.utils.metrics import count_tokens_claude, count_tokens_gpt
except ImportError:
    try:
        from utils.metrics import count_tokens_claude, count_tokens_gpt
    except ImportError:
        sys.path.insert(0, str(Path(__file__).parent.parent.parent))
        from utils.metrics import count_tokens_claude, count_tokens_gpt

# Import with improved error handling
ClaudeCodeProxy = None
WaterfallCompressor = None
CompressionResult = None
setup_logger = None

try:
    from integrations.claude_wrapper.claude_proxy import ClaudeCodeProxy
    from input_optimizer.engine.waterfall_compressor import WaterfallCompressor
    from input_optimizer.engine.compression_types import CompressionResult
    from utils.logger import setup_logger
except ImportError as e:
    try:
        from optimize_ai.integrations.claude_wrapper.claude_proxy import ClaudeCodeProxy
        from optimize_ai.input_optimizer.engine.waterfall_compressor import WaterfallCompressor
        from optimize_ai.input_optimizer.engine.compression_types import CompressionResult
        from optimize_ai.utils.logger import setup_logger
    except ImportError as e2:
        print(f"Import error: Failed to import required modules - using fallback mode")
        print(f"  First error: {e}")
        print(f"  Second error: {e2}")
        # Create fallback classes
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

# Configure console WITHOUT any output limits
console = Console(
    force_terminal=True,  # Force terminal mode for consistent behavior
    width=None,           # No width constraint
    legacy_windows=False  # Disable legacy Windows mode for better output
)
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
@click.option('--live-metrics', '-l', is_flag=True, help='Show live token metrics and cost analysis')
@click.option('--verbose', '-v', is_flag=True, help='Verbose output')
@click.option('--raw-cai3', is_flag=True, help='Show raw CAI3 references without humanization (for debugging)')
@click.option('--strict-contract', is_flag=True, help='Force strict contract enforcement for all CAI3 interactions')
@click.option('--enable-constraints', is_flag=True, default=False, help='Enable advanced constraint-based CAI3 processing')
@click.option('--disable-constraints', is_flag=True, default=False, help='Disable constraint-based CAI3 processing (default: enabled)')
def ask(prompt: str, file: Optional[str], no_compress: bool, apply_patch: bool, 
        output: Optional[str], show_stats: bool, live_metrics: bool, verbose: bool, 
        raw_cai3: bool, strict_contract: bool, enable_constraints: bool, disable_constraints: bool):
    """
    Ask Claude Code a question about your code with intelligent compression and cost analysis.
    
    Contract enforcement is automatically applied only when needed:
    - Complex CAI3 compression (>10 pools, >8 bodies, >60% compression)
    - High-risk patterns detected (inheritance, nested structures, etc.)
    - Previous CAI3 translation failures in session
    
    Examples:
        optimize-ai claude-code ask "Fix the validation bug" -f app.py --live-metrics
        optimize-ai claude-code ask "Explain this function" -f module.py --no-compress
        optimize-ai claude-code ask "Add error handling" -f service.py --apply-patch --live-metrics
        optimize-ai claude-code ask "Debug complex inheritance" -f app.py --strict-contract  # Force contract
        optimize-ai claude-code ask "Simple refactor" -f app.py  # No contract (low risk)
    """
    try:
        # Determine constraint system status - default enabled unless explicitly disabled
        use_constraints = enable_constraints or not disable_constraints
        
        # Initialize Claude pricing metrics (Claude Sonnet 4)
        claude_metrics = {
            'claude_model': 'claude-sonnet-4-20250514',
            'claude_input_cost_per_mtok': 3.0,      # $3 per million input tokens
            'claude_output_cost_per_mtok': 15.0,    # $15 per million output tokens
            'claude_cache_write_5m_per_mtok': 3.75, # $3.75 per million (5min cache)
            'claude_cache_write_1h_per_mtok': 6.0,  # $6 per million (1h cache)
            'claude_cache_hit_per_mtok': 0.30,      # $0.30 per million (cache hits)
        }
        
        # Initialize the proxy with consistent cache directory and constraint system
        cache_dir = Path.home() / ".optimize_ai" / "claude_cache"
        proxy = ClaudeCodeProxy(
            enable_compression=not no_compress,
            cache_dir=cache_dir,
            enable_constraint_system=use_constraints
        )
        
        # Log constraint system status
        if verbose and use_constraints:
            if hasattr(proxy, 'cai3_interface') and proxy.cai3_interface:
                console.print("[dim]✅ Advanced constraint-based CAI3 processing enabled[/dim]")
            else:
                console.print("[dim]⚠️ Constraint system requested but not available, using fallback[/dim]")
        elif verbose:
            console.print("[dim]ℹ️ Standard CAI3 processing mode (constraints disabled)[/dim]")
        
        # Read file content if provided
        file_content = None
        if file:
            file_path = Path(file)
            file_content = file_path.read_text()
            
        # Prepare full prompt
        full_prompt = prompt if not file_content else f"{prompt}\n\n```python\n{file_content}\n```"
        
        # Measure original Claude tokens
        original_claude_tokens = 0
        compressed_claude_tokens = 0
        response_claude_tokens = 0
        
        try:
            original_claude_tokens = count_tokens_claude(full_prompt, claude_metrics['claude_model'])
        except Exception as e:
            if verbose:
                console.print(f"[dim]Warning: Could not count original tokens: {e}[/dim]")
        
        # Show compression preview with enhanced cost analysis
        if show_stats and not no_compress:
            with console.status("[cyan]Analyzing code for compression...") as status:
                compressed_prompt, metadata = proxy.process_input(full_prompt, file)
                
                # Debug logging
                if verbose:
                    console.print(f"[dim]🔍 Compression Debug Info:[/dim]")
                    console.print(f"[dim]  Original prompt length: {len(full_prompt)} chars[/dim]")
                    console.print(f"[dim]  Compressed prompt length: {len(compressed_prompt)} chars[/dim]")
                    console.print(f"[dim]  Compression metadata: {metadata.get('compressed', 'Unknown')}[/dim]")
                    if metadata.get('reason'):
                        console.print(f"[dim]  Reason: {metadata['reason']}[/dim]")
                
                # Measure compressed tokens
                try:
                    compressed_claude_tokens = count_tokens_claude(compressed_prompt, claude_metrics['claude_model'])
                    # Update metadata with actual Claude token counts
                    metadata['original_tokens_claude'] = original_claude_tokens
                    metadata['compressed_tokens_claude'] = compressed_claude_tokens
                    metadata['claude_tokens_saved'] = original_claude_tokens - compressed_claude_tokens
                    
                    if verbose:
                        console.print(f"[dim]  Original Claude tokens: {original_claude_tokens:,}[/dim]")
                        console.print(f"[dim]  Compressed Claude tokens: {compressed_claude_tokens:,}[/dim]")
                        console.print(f"[dim]  Net token change: {compressed_claude_tokens - original_claude_tokens:+,}[/dim]")
                        
                except Exception as e:
                    if verbose:
                        console.print(f"[dim]Warning: Could not count compressed tokens: {e}[/dim]")
                    compressed_claude_tokens = metadata.get('compressed_tokens', 0)
                    # Still try to populate metadata with what we have
                    if original_claude_tokens > 0:
                        metadata['original_tokens_claude'] = original_claude_tokens
                        if compressed_claude_tokens > 0:
                            metadata['compressed_tokens_claude'] = compressed_claude_tokens
                            metadata['claude_tokens_saved'] = original_claude_tokens - compressed_claude_tokens
                
            # Display enhanced compression preview (this updates metadata with cost calculations)
            _display_enhanced_compression_preview(metadata, claude_metrics, live_metrics)
            
            # Check if compression was actually applied
            if not metadata.get("compressed", False):
                if metadata.get('reason') == 'wrapper_overhead_too_large':
                    console.print("[yellow]⚠️ Compression skipped: wrapper overhead exceeded savings[/yellow]")
                elif metadata.get('error'):
                    console.print(f"[yellow]⚠️ Compression failed: {metadata['error']}[/yellow]")
                else:
                    console.print("[yellow]⚠️ Compression was not applied[/yellow]")
                
                # Ask user if they want to proceed without compression
                if not click.confirm("Proceed without compression?", default=True):
                    console.print("[yellow]Aborted by user[/yellow]")
                    return
            else:
                # Show cost summary from enhanced metadata (now properly populated)
                estimated_total_savings = metadata.get('estimated_total_savings', 0)
                if estimated_total_savings > 0:
                    console.print(f"\n💰 Estimated Total Savings: ${estimated_total_savings:.4f}")
                    
                    # Show breakdown if available
                    input_savings = metadata.get('estimated_input_savings', 0)
                    output_savings = metadata.get('estimated_output_savings', 0)
                    if input_savings > 0 and output_savings > 0:
                        console.print(f"[dim]   └─ Input: ${input_savings:.4f} + Output: ${output_savings:.4f}[/dim]")
                
                # Ask for confirmation with compression
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
                compression_task = progress.add_task("[cyan]Compressing code...", total=100)
                compressed_prompt, metadata = proxy.process_input(full_prompt, file)
                
                # Apply strict contract flag if specified
                if strict_contract:
                    metadata['force_contract'] = True
                    if verbose:
                        console.print(f"[dim]🔒 Strict contract mode enabled[/dim]")
                
                # Add CAI3 syntax rules if constraint system is enabled
                if use_constraints:
                    metadata['cai3_syntax_rules'] = """
ULTRA-CRITICAL CAI3-LITE SYNTAX RULES 🚨

MANDATORY BRACKET VALIDATION:
1. Count { braces: opening = closing (EXACT MATCH REQUIRED)
2. Count ( parentheses: opening = closing (EXACT MATCH REQUIRED)  
3. Count [ brackets: opening = closing (EXACT MATCH REQUIRED)

REQUIRED SECTIONS (MUST BE COMPLETE):
- P: section with ALL pool definitions (p0="value",p1="value",...)
- X: section with all aliases (a0=code,a1=code,...)
- D: section with dependencies
- T: section with table structure
- B#cid: body sections (complete, no truncation)

FORBIDDEN ELEMENTS:
❌ ABSOLUTELY NO parentheticals: "(was B#a0)", "(originally...)", "(was p0)", etc.
❌ NO annotations or explanations of any kind
❌ NO humanization or clarification text
❌ NO comments or explanations outside ```C3L block
❌ NO truncation markers: "...", "p5..."
❌ NO malformed structures

CRITICAL INSTRUCTION: 
The CAI3 code you receive is ALREADY CORRECT. Do NOT add any "(was ...)" annotations, explanations, or modifications to it. Return the corrected CAI3 code with fixes applied but NO additional annotations.

OUTPUT RULE: Generate EXACTLY ONE ```C3L code block with fixes applied. NO ANNOTATIONS. NO EXPLANATIONS."""
                
                # Ensure we have Claude token counts
                if compressed_claude_tokens == 0:
                    try:
                        compressed_claude_tokens = count_tokens_claude(compressed_prompt, claude_metrics['claude_model'])
                    except Exception:
                        compressed_claude_tokens = metadata.get('compressed_tokens', 0)
                
                progress.update(compression_task, completed=100)
            else:
                compressed_prompt = full_prompt
                compressed_claude_tokens = original_claude_tokens
                metadata = {"compressed": False}
                if strict_contract:
                    # Even for uncompressed, user wants strict control
                    metadata['force_contract'] = True
            
            # Claude Code execution with constraint system integration
            claude_task = progress.add_task("[yellow]Sending to Claude Code...", total=100)
            
            # Use constraint system if enabled, otherwise fall back to original logic
            if use_constraints and hasattr(proxy, 'cai3_interface') and proxy.cai3_interface:
                # Use constraint-based processing for compressed content (requesting CAI3-LITE output)
                if metadata.get("compressed", False):
                    if verbose:
                        console.print(f"[dim]🔧 Using constraint-based CAI3 processing[/dim]")
                    # Extract task from the original prompt and pass CAI3 content
                    user_task = prompt  # Original user task
                    cai3_output, mappings = proxy.process_with_constraints(compressed_prompt, user_task)
                    result = cai3_output
                    metadata['constraint_processed'] = True
                    metadata['constraint_mappings'] = mappings
                else:
                    # For non-CAI3 content, use standard Claude call but with enhanced prompting
                    if verbose:
                        console.print(f"[dim]🔧 Using enhanced prompting (non-CAI3 content)[/dim]")
                    # Add constraint-style prompting for non-CAI3 content
                    enhanced_prompt = f"""{compressed_prompt}

CRITICAL OUTPUT REQUIREMENTS:
- Return exactly one fenced code block with proper language tag
- NO explanations, annotations, or parentheticals like "(was ...)"  
- NO truncation markers like "..." anywhere
- Complete, working code with proper syntax
- For Python: ```python\\n...\\n```
- For other formats: Use appropriate language tag

{metadata.get('cai3_syntax_rules', '')}"""
                    result = _execute_claude_code_enhanced(enhanced_prompt, verbose)
                metadata['contract_applied'] = False  # Constraints replace contract system
            else:
                # Fall back to original contract enforcement logic
                if not no_compress and metadata.get("compressed", False):
                    needs_contract = _needs_contract_enforcement(metadata, full_prompt)
                    
                    if needs_contract:
                        # High-risk scenario - apply contract
                        contracted_prompt, max_output_tokens = _prepare_cai3_prompt_with_contract(compressed_prompt, metadata)
                        if verbose:
                            console.print(f"[dim]🔒 Applied contract enforcement - high risk scenario (max tokens: {max_output_tokens})[/dim]")
                        result = _execute_claude_code_enhanced(contracted_prompt, verbose)
                        metadata['contract_applied'] = True
                    else:
                        # Low-risk scenario - use compressed prompt directly
                        if verbose:
                            console.print(f"[dim]🟢 Low-risk compression - no contract needed[/dim]")
                        result = _execute_claude_code_enhanced(compressed_prompt, verbose)
                        metadata['contract_applied'] = False
                else:
                    # Execute without any contract for uncompressed prompts
                    result = _execute_claude_code_enhanced(compressed_prompt, verbose)
                    metadata['contract_applied'] = False
            
            progress.update(claude_task, completed=100)
            
            # Measure response tokens
            try:
                response_claude_tokens = count_tokens_claude(result, claude_metrics['claude_model'])
            except Exception as e:
                if verbose:
                    console.print(f"[dim]Warning: Could not count response tokens: {e}[/dim]")
            
            # Translation phase (if compressed) with intelligent validation
            if not no_compress and _contains_cai3(result):
                translation_task = progress.add_task("[green]Translating CAI3 response...", total=100)
                if verbose:
                    console.print(f"[dim]🔄 Raw Claude response ({len(result)} chars): {result[:200]}{'...' if len(result) > 200 else ''}[/dim]")
                
                # Apply validation only when needed
                should_validate = _should_validate_response(metadata, result)
                
                if should_validate:
                    # High-risk scenario - validate CAI3-LITE format before translation
                    if use_constraints:
                        # When constraints are enabled, the sophisticated constraint system
                        # has already validated the output. Skip CLI validation to avoid conflicts.
                        if verbose:
                            console.print(f"[dim]✅ CAI3-LITE validated by constraint system[/dim]")
                        metadata['constraint_validation_used'] = True
                    else:
                        # Use legacy CLI validation when constraints are disabled
                        if not _validate_cai3_compliance(result):
                            if verbose:
                                console.print(f"[dim]⚠️ CAI3-LITE compliance failed, attempting repair...[/dim]")
                            result = _repair_cai3_format(result, compressed_prompt, max_retries=2, verbose=verbose)
                            metadata['repair_attempted'] = True
                        else:
                            if verbose:
                                console.print(f"[dim]✅ CAI3-LITE compliance validated[/dim]")
                            metadata['validation_passed'] = True
                else:
                    if verbose:
                        console.print(f"[dim]🟢 Low-risk CAI3 - skipping validation[/dim]")
                    metadata['validation_skipped'] = True
                
                final_output = proxy.process_output(result, metadata)
                if verbose:
                    console.print(f"[dim]✅ Translated output ({len(final_output)} chars): {final_output[:200]}{'...' if len(final_output) > 200 else ''}[/dim]")
                progress.update(translation_task, completed=100)
            else:
                final_output = result
                if verbose:
                    contains_cai3 = _contains_cai3(result)
                    console.print(f"[dim]ℹ️ No CAI3 translation needed (no_compress={no_compress}, contains_cai3={contains_cai3})[/dim]")
        
        # Display results with enhanced formatting
        _display_results_enhanced(final_output, metadata, show_stats, raw_cai3)
        
        # Show comprehensive cost analysis
        if live_metrics or (show_stats and (original_claude_tokens > 0 or response_claude_tokens > 0)):
            _display_comprehensive_cost_analysis(
                original_claude_tokens,
                compressed_claude_tokens or original_claude_tokens,
                response_claude_tokens,
                claude_metrics,
                metadata,
                verbose
            )
        
        # Save output if requested
        if output:
            Path(output).write_text(final_output)
            console.print(f"[green]✓ Saved to {output}[/green]")
        
        # Apply patch if requested with transactional safety
        if apply_patch and file and _has_code_changes(final_output):
            success = _apply_patch_transactional(file, final_output)
            if not success:
                console.print("[yellow]Patch application failed, file unchanged[/yellow]")
            
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        if verbose:
            import traceback
            console.print(traceback.format_exc())
        sys.exit(1)

def _needs_contract_enforcement(metadata: Dict, prompt: str) -> bool:
    """
    Determine if contract enforcement is needed based on compression context.
    
    Only enforce contracts when there are specific CAI3 compliance risks:
    1. Complex CAI3 compression with many pools/aliases
    2. Previous CAI3 translation failures in session  
    3. User explicitly requests strict format
    4. High-risk compression patterns detected
    """
    if not metadata.get("compressed", False):
        return False
    
    # Check for complex CAI3 that benefits from contracts
    pool_count = metadata.get('pool_count', 0)
    body_count = metadata.get('body_count', 0)
    compression_ratio = metadata.get('compression_ratio', 0)
    
    # High complexity indicators
    complex_compression = (
        pool_count > 10 or 
        body_count > 8 or 
        compression_ratio > 60
    )
    
    # Check for previous translation failures
    session_failures = metadata.get('previous_cai3_failures', 0)
    
    # Check for high-risk patterns in the prompt
    high_risk_patterns = [
        'many methods',
        'complex class',
        'multiple files',
        'large codebase',
        'inheritance',
        'nested structures'
    ]
    
    has_risk_patterns = any(pattern in prompt.lower() for pattern in high_risk_patterns)
    
    # Only enforce when there's genuine risk
    should_enforce = (
        complex_compression or 
        session_failures > 0 or 
        has_risk_patterns or
        metadata.get('force_contract', False)
    )
    
    return should_enforce

def _prepare_cai3_prompt_with_contract(compressed_prompt: str, metadata: Dict) -> Tuple[str, int]:
    """Prepare CAI3 prompt with strict output contract (only when needed)."""
    
    # Lightweight contract for moderate risk
    if metadata.get('compression_ratio', 0) < 50:
        contract_hint = "Please return valid CAI3-LITE format in a single ```C3L``` block."
        enhanced_prompt = f"{compressed_prompt}\n\n{contract_hint}"
        
        # Conservative token estimate
        estimated_tokens = metadata.get('compressed_tokens', 500) * 1.2
        return enhanced_prompt, int(estimated_tokens)
    
    # Full contract for high-risk scenarios
    system_preface = """CRITICAL: Return exactly one fenced code block.
For CAI3-LITE: ```C3L ...```
For Python: ```python ...```
No explanations, notes, or parentheticals like "(was ...)".

BEGIN_STRICT_CAI3"""
    
    # Calculate max tokens based on compression complexity
    estimated_pools = metadata.get('pool_count', 20)
    estimated_bodies = metadata.get('body_count', 15)
    estimated_c3l_tokens = (estimated_pools * 10) + (estimated_bodies * 50) + 200
    max_output_tokens = int(estimated_c3l_tokens * 1.3)
    
    prompt = f"""{system_preface}

Convert to corrected CAI3-LITE. Return exactly one ```C3L``` block:
- Define ALL pools in P: section (no ellipsis)
- Use exact format: P:p0="value",p1="value"  
- Include all CID aliases in X: section
- No prose or comments

{compressed_prompt}

END_STRICT_CAI3"""
    
    return prompt, max_output_tokens

def _should_validate_response(metadata: Dict, result: str) -> bool:
    """
    Determine if response validation is needed.
    
    Skip validation for:
    - Simple uncompressed responses
    - Responses that clearly don't contain CAI3
    - Low-risk compression scenarios
    """
    if not metadata.get("compressed", False):
        return False
    
    # Quick check if response likely contains CAI3
    has_cai3_markers = any(marker in result for marker in ['#C3L', 'P:', 'X:', 'T:', 'B#'])
    
    if not has_cai3_markers:
        return False
    
    # Check risk factors
    compression_ratio = metadata.get('compression_ratio', 0)
    is_complex = compression_ratio > 40 or metadata.get('pool_count', 0) > 5
    
    return is_complex

def _execute_claude_code_enhanced(prompt: str, verbose: bool) -> str:
    """Execute Claude Code CLI with enhanced output capture to prevent truncation."""
    try:
        # Write prompt to temporary file to avoid command line length limits
        import tempfile
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as tmp:
            tmp.write(prompt)
            tmp_path = tmp.name
        
        try:
            # Use stdin to pass the prompt for better handling of long content
            with open(tmp_path, 'r') as f:
                result = subprocess.run(
                    ["claude"],
                    stdin=f,
                    capture_output=True,
                    text=True,
                    timeout=300,  # 5 minute timeout for long responses
                    # Ensure we get full output without buffering issues
                    env={**os.environ, 'PYTHONUNBUFFERED': '1'}
                )
        finally:
            # Clean up temp file
            try:
                os.unlink(tmp_path)
            except:
                pass
        
        if result.returncode != 0:
            raise RuntimeError(f"Claude Code error: {result.stderr}")
        
        # Ensure we have the complete output
        full_output = result.stdout
        
        if verbose:
            console.print(f"[dim]Received {len(full_output)} characters from Claude[/dim]")
        
        return full_output
        
    except FileNotFoundError:
        raise RuntimeError(
            "Claude Code CLI not found. Ensure 'claude' is installed and in PATH.\n"
            "Install with: pip install claude-cli"
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError("Claude Code request timed out after 5 minutes")

def _display_results_enhanced(output: str, metadata: Dict[str, Any], show_stats: bool, raw_cai3: bool = False):
    """Display the final results with proper formatting that prevents truncation."""
    console.print("\n" + "─" * 80)
    
    if not output or not output.strip():
        console.print(Panel(
            "[yellow]No response received from Claude[/yellow]",
            title="[bold blue]Claude's Response[/bold blue]",
            border_style="blue"
        ))
        return
    
    # Humanize CAI3 references before displaying (unless raw mode is requested)
    if raw_cai3:
        console.print("[dim]🔧 Showing raw CAI3 references (--raw-cai3 mode)[/dim]")
        display_output = output
    else:
        display_output = _humanize_cai3_references(output, metadata)
    
    # Extract code blocks if present
    code_block_pattern = r'```(\w+)?\n(.*?)\n```'
    code_blocks = list(re.finditer(code_block_pattern, display_output, re.DOTALL))
    
    if code_blocks:
        # Build elements for mixed content (text + code blocks)
        elements = []
        last_end = 0
        
        for i, match in enumerate(code_blocks):
            start, end = match.span()
            
            # Add text before this code block
            if start > last_end:
                text_before = display_output[last_end:start].strip()
                if text_before:
                    elements.append(Text(text_before))
                    elements.append(Text(""))  # Add spacing
            
            # Add code block with syntax highlighting
            language = match.group(1) or "python"
            code_content = match.group(2)
            
            # Create code block within a sub-panel for better visual separation
            code_syntax = Syntax(
                code_content,
                language,
                theme="monokai",
                line_numbers=True,
                word_wrap=False
            )
            
            # Add label and code
            elements.append(Text(f"Code Block {i+1}:", style="bold cyan"))
            elements.append(code_syntax)
            
            last_end = end
        
        # Add any remaining text after the last code block
        if last_end < len(display_output):
            text_after = display_output[last_end:].strip()
            if text_after:
                elements.append(Text(""))  # Add spacing
                elements.append(Text(text_after))
        
        # Display everything in a single panel without height constraints
        console.print(Panel(
            Group(*elements),
            title="[bold blue]Claude's Response[/bold blue]",
            border_style="blue",
            expand=False,
            width=None,      # No width constraint
            height=None,     # No height constraint - CRITICAL FIX
            padding=(1, 2)
        ))
    else:
        # No code blocks, display plain text response
        console.print(Panel(
            Text(display_output),
            title="[bold blue]Claude's Response[/bold blue]",
            border_style="blue",
            expand=False,
            width=None,      # No width constraint
            height=None,     # No height constraint - CRITICAL FIX
            padding=(1, 2)
        ))
    
    # Force output flush to ensure everything is displayed
    sys.stdout.flush()
    sys.stderr.flush()
    
    # Enhanced final statistics with Claude token metrics
    if show_stats and metadata.get("compressed"):
        # Get Claude-specific metrics
        claude_tokens_saved = metadata.get('claude_tokens_saved', metadata.get('tokens_saved', 0))
        compression_ratio = metadata.get('compression_ratio', 0)
        
        # Calculate actual token savings if we have Claude token counts
        if metadata.get('original_tokens_claude') and metadata.get('compressed_tokens_claude'):
            original_claude = metadata['original_tokens_claude']
            compressed_claude = metadata['compressed_tokens_claude']
            claude_tokens_saved = original_claude - compressed_claude
            compression_ratio = (claude_tokens_saved / original_claude * 100) if original_claude > 0 else 0
        
        console.print(f"\n[bold green]✨ Token Savings: {claude_tokens_saved:,} tokens "
                     f"({compression_ratio:.1f}% reduction)[/bold green]")
        
        # Show estimated vs actual savings if we have enhanced metadata
        if metadata.get('estimated_total_savings'):
            estimated_savings = metadata['estimated_total_savings']
            console.print(f"[bold cyan]💰 Estimated Total Savings: ${estimated_savings:.4f}[/bold cyan]")
            
            # Show breakdown
            if metadata.get('estimated_input_savings') and metadata.get('estimated_output_savings'):
                input_savings = metadata['estimated_input_savings']
                output_savings = metadata['estimated_output_savings']
                console.print(f"[dim]   └─ Input: ${input_savings:.4f} + Output: ${output_savings:.4f}[/dim]")
        else:
            # Fallback to basic cost estimation
            potential_savings = metadata.get('potential_cost_savings', 0)
            console.print(f"[bold cyan]💰 Estimated Savings: ${potential_savings:.4f}[/bold cyan]")
        
        # Add methodology note
        console.print(f"[dim]💡 Use --live-metrics for detailed cost analysis with actual response data[/dim]")

def _validate_cai3_compliance(result: str) -> bool:
    """Validate CAI3-LITE response compliance before translation."""
    issues = []
    
    # Check for single fenced block
    code_blocks = re.findall(r'```(\w+)?\n(.*?)\n```', result, re.DOTALL)
    if len(code_blocks) != 1:
        return False
    
    lang, content = code_blocks[0]
    
    # Check language tag
    if lang not in ['C3L', 'CAI3', 'cai3']:
        return False
    
    # Check for forbidden patterns
    if '(was ' in content or '...)' in content:
        return False
    
    # Check for truncated pools
    if 'P:p...' in content or re.search(r'P:.*\.\.\.', content):
        return False
    
    # Extract and validate pools
    pool_defs = set()
    pool_refs = set()
    
    # Find defined pools
    pool_def_pattern = r'P:([^:\n]+)'
    pool_match = re.search(pool_def_pattern, content)
    if pool_match:
        pool_line = pool_match.group(1)
        for pool_def in re.finditer(r'(p\d+)=', pool_line):
            pool_defs.add(pool_def.group(1))
    
    # Find referenced pools
    for pool_ref in re.finditer(r'\b(p\d+)\b', content):
        if pool_ref.start() > content.find('T:'):  # Only in table/body sections
            pool_refs.add(pool_ref.group(1))
    
    # Check for missing pools
    missing_pools = pool_refs - pool_defs
    if missing_pools:
        return False
    
    return True

def _repair_cai3_format(result: str, compressed_prompt: str, max_retries: int = 2, verbose: bool = False) -> str:
    """Repair CAI3 format issues by re-prompting Claude with specific fixes."""
    if verbose:
        console.print(f"[dim]🔧 Attempting CAI3 format repair (max {max_retries} retries)[/dim]")
    
    for retry in range(max_retries):
        if verbose:
            console.print(f"[dim]  Retry {retry + 1}/{max_retries}...[/dim]")
        
        # Analyze the issues
        issues = _analyze_cai3_issues(result)
        
        if not issues:
            if verbose:
                console.print(f"[dim]✅ CAI3 format repaired successfully[/dim]")
            return result
        
        # Create repair prompt
        repair_prompt = _create_repair_prompt(result, issues, compressed_prompt)
        
        try:
            # Execute repair
            repaired_result = _execute_claude_code_enhanced(repair_prompt, verbose)
            
            # Validate the repair
            if _validate_cai3_compliance(repaired_result):
                if verbose:
                    console.print(f"[dim]✅ CAI3 format repair successful on retry {retry + 1}[/dim]")
                return repaired_result
            else:
                result = repaired_result  # Use for next iteration
                
        except Exception as e:
            if verbose:
                console.print(f"[dim]⚠️ Repair attempt {retry + 1} failed: {e}[/dim]")
    
    if verbose:
        console.print(f"[dim]❌ CAI3 format repair failed after {max_retries} attempts[/dim]")
    return result  # Return best attempt

def _analyze_cai3_issues(result: str) -> list:
    """Analyze CAI3 format issues."""
    issues = []
    
    # Check for single fenced block
    code_blocks = re.findall(r'```(\w+)?\n(.*?)\n```', result, re.DOTALL)
    if len(code_blocks) != 1:
        issues.append(f"multiple_code_blocks:{len(code_blocks)}")
        return issues
    
    lang, content = code_blocks[0]
    
    # Check language tag
    if lang not in ['C3L', 'CAI3', 'cai3']:
        issues.append(f"wrong_language_tag:{lang}")
    
    # Check for forbidden patterns
    if '(was ' in content:
        issues.append("contains_parentheticals")
    
    if '...)' in content:
        issues.append("contains_ellipsis")
    
    # Check for truncated pools
    if 'P:p...' in content or re.search(r'P:.*\.\.\.', content):
        issues.append("truncated_pools")
    
    # Extract and validate pools
    pool_defs = set()
    pool_refs = set()
    
    # Find defined pools
    pool_def_pattern = r'P:([^:\n]+)'
    pool_match = re.search(pool_def_pattern, content)
    if pool_match:
        pool_line = pool_match.group(1)
        for pool_def in re.finditer(r'(p\d+)=', pool_line):
            pool_defs.add(pool_def.group(1))
    
    # Find referenced pools
    for pool_ref in re.finditer(r'\b(p\d+)\b', content):
        if pool_ref.start() > content.find('T:'):  # Only in table/body sections
            pool_refs.add(pool_ref.group(1))
    
    # Check for missing pools
    missing_pools = pool_refs - pool_defs
    if missing_pools:
        issues.append(f"missing_pools:{','.join(sorted(missing_pools))}")
    
    return issues

def _create_repair_prompt(result: str, issues: list, original_compressed_prompt: str) -> str:
    """Create a repair prompt for CAI3 format issues."""
    issue_fixes = []
    
    for issue in issues:
        if issue.startswith("multiple_code_blocks"):
            issue_fixes.append("- Return exactly ONE ```C3L``` code block only")
        elif issue.startswith("wrong_language_tag"):
            issue_fixes.append("- Use ```C3L``` as the language tag")
        elif issue == "contains_parentheticals":
            issue_fixes.append("- Remove all (was ...) parentheticals")
        elif issue == "contains_ellipsis":
            issue_fixes.append("- Replace ... with complete definitions")
        elif issue == "truncated_pools":
            issue_fixes.append("- Define ALL pools completely in P: section")
        elif issue.startswith("missing_pools"):
            missing = issue.split(":")[1]
            issue_fixes.append(f"- Define missing pools: {missing}")
    
    fixes_text = "\n".join(issue_fixes)
    
    return f"""Fix the CAI3-LITE format issues:

{fixes_text}

Previous response (needs fixing):
{result}

Return corrected ```C3L``` block with all issues fixed. Use the original context:
{original_compressed_prompt[:500]}...
"""

def _contains_cai3(text: str) -> bool:
    """Check if response contains CAI3 compressed code."""
    cai3_markers = ['#C3L', '#C3-PATCH', 'CAI3 CODE', 'B#', 'X:', 'D:', 'T:']
    return any(marker in text for marker in cai3_markers)

def _humanize_cai3_references(text: str, metadata: Dict[str, Any], skip_humanization: bool = False) -> str:
    """
    Convert CAI3 references in Claude's response to human-readable explanations.
    
    This function identifies CAI3 references like "Block B#b9 (Function `ac`)" and 
    replaces them with readable explanations like "Function `add_config` in ConfigManager class".
    
    Args:
        text: The Claude output text
        metadata: Compression metadata containing source path and other info
        skip_humanization: If True, return original text without humanization
    """
    if skip_humanization or not metadata.get("compressed", False) or not metadata.get("source_path"):
        return text
    
    try:
        # Import CAI3 structures
        from integrations.claude_wrapper.claude_proxy import ClaudeCodeProxy
        from input_optimizer.engine.cai3_structures import CAI3Cache
        
        # Load the CAI3 mapping data
        cache_dir = Path.home() / ".optimize_ai" / "claude_cache"
        cai3_cache = CAI3Cache(cache_dir)
        source_path = Path(metadata["source_path"])
        
        cai3_full = cai3_cache.load_full(source_path)
        cai3_map = cai3_cache.load_map(source_path)
        
        if not cai3_full or not cai3_map:
            # Try to provide basic humanization using known patterns
            return _basic_cai3_humanization(text)
        
        # Create mapping from short names to full context
        humanized_text = text
        
        # Extract and replace various CAI3 reference patterns
        import re
        
        # Pattern 1: Block references like "Block B#b9" or "B#b9"
        block_pattern = r'(?:Block\s+)?B#([a-z0-9]+)'
        for match in re.finditer(block_pattern, text, re.IGNORECASE):
            block_id = match.group(1)
            full_match = match.group(0)
            
            # Find the corresponding node in CAI3Full
            readable_name = _find_readable_name_for_block(block_id, cai3_full)
            if readable_name:
                humanized_text = humanized_text.replace(full_match, f"{readable_name} (was {full_match})")
        
        # Pattern 2: Function references like "Function `ac`"
        func_pattern = r'Function\s+`([a-z0-9]+)`'
        for match in re.finditer(func_pattern, text, re.IGNORECASE):
            short_name = match.group(1)
            full_match = match.group(0)
            
            # Find the full function name
            readable_name = _find_readable_name_for_short(short_name, cai3_full)
            if readable_name:
                humanized_text = humanized_text.replace(full_match, f"Function `{readable_name}` (was `{short_name}`)")
        
        # Pattern 3: Method references like "method `vr`"
        method_pattern = r'(?:method|Method)\s+`([a-z0-9]+)`'
        for match in re.finditer(method_pattern, text, re.IGNORECASE):
            short_name = match.group(1)
            full_match = match.group(0)
            
            # Find the full method name with class context
            readable_name = _find_readable_name_for_short(short_name, cai3_full, include_class=True)
            if readable_name:
                humanized_text = humanized_text.replace(full_match, f"Method `{readable_name}` (was `{short_name}`)")
        
        # Pattern 4: CID references like "cid=fn_1a2c" or similar
        cid_pattern = r'(?:cid=|CID:\s*)([a-z_0-9]+)'
        for match in re.finditer(cid_pattern, text, re.IGNORECASE):
            cid = match.group(1)
            full_match = match.group(0)
            
            # Find the node with this CID
            readable_name = _find_readable_name_for_cid(cid, cai3_full)
            if readable_name:
                humanized_text = humanized_text.replace(full_match, f"{full_match} ({readable_name})")
        
        # Pattern 5: Pool references like "p0", "p1" etc
        pool_pattern = r'\bp([0-9]+)\b'
        for match in re.finditer(pool_pattern, text):
            pool_ref = match.group(0)
            pool_id = match.group(1)
            
            # Look up in pools
            if hasattr(cai3_full, 'pools') and pool_ref in cai3_full.pools:
                pool_value = cai3_full.pools[pool_ref]
                humanized_text = humanized_text.replace(pool_ref, f'"{pool_value}" (was {pool_ref})')
        
        # Add a summary of what was humanized if changes were made
        if humanized_text != text:
            changes_count = len(re.findall(r'\(was [^)]+\)', humanized_text))
            humanized_text = f"🔍 **Humanized {changes_count} CAI3 references for clarity:**\n\n{humanized_text}"
        
        return humanized_text
        
    except Exception as e:
        console.print(f"[dim]Note: Could not humanize CAI3 references: {e}[/dim]")
        return _basic_cai3_humanization(text)

def _basic_cai3_humanization(text: str) -> str:
    """
    Provide basic humanization when full CAI3 mapping data is not available.
    This uses common patterns and educated guesses to make output more readable.
    """
    import re
    
    humanized_text = text
    changes_made = False
    
    # Common short name mappings (these are typical CAI3 patterns)
    common_mappings = {
        'ac': 'add_config',
        'gc': 'get_config', 
        'sc': 'set_config',
        'vc': 'validate_config',
        'vr': 'validate_record',
        'gr': 'get_record',
        'sr': 'save_record',
        'dr': 'delete_record',
        'gs': 'get_or_set',
        'ps': 'process_string',
        'pf': 'process_file',
        'pd': 'process_data',
        'cl': 'cleanup',
        'init': '__init__',
        'str': '__str__',
        'repr': '__repr__',
    }
    
    # Pattern 1: Function references like "Function `ac`"
    func_pattern = r'Function\s+`([a-z0-9]+)`'
    for match in re.finditer(func_pattern, text, re.IGNORECASE):
        short_name = match.group(1)
        full_match = match.group(0)
        
        if short_name in common_mappings:
            readable_name = common_mappings[short_name]
            humanized_text = humanized_text.replace(full_match, f"Function `{readable_name}` (likely expansion of `{short_name}`)")
            changes_made = True
    
    # Pattern 2: Method references like "method `vr`"
    method_pattern = r'(?:method|Method)\s+`([a-z0-9]+)`'
    for match in re.finditer(method_pattern, text, re.IGNORECASE):
        short_name = match.group(1)
        full_match = match.group(0)
        
        if short_name in common_mappings:
            readable_name = common_mappings[short_name]
            humanized_text = humanized_text.replace(full_match, f"Method `{readable_name}` (likely expansion of `{short_name}`)")
            changes_made = True
    
    # Pattern 3: Block references - provide context
    block_pattern = r'(?:Block\s+)?B#([a-z0-9]+)'
    for match in re.finditer(block_pattern, text, re.IGNORECASE):
        block_id = match.group(1)
        full_match = match.group(0)
        humanized_text = humanized_text.replace(full_match, f"{full_match} (code block/function body)")
        changes_made = True
    
    # Pattern 4: Add explanatory context for CAI3 format
    if 'CAI3' in text or any(marker in text for marker in ['#C3L', 'B#', 'X:', 'D:']):
        if changes_made:
            note = "\n💡 Note: CAI3 mapping cache unavailable - showing likely expansions based on common patterns.\n"
            humanized_text = note + humanized_text
        else:
            note = "\n💡 Note: This response contains CAI3 compressed references. Full humanization requires cache data from the compression phase.\n"
            humanized_text = note + humanized_text
    
    return humanized_text

def _find_readable_name_for_block(block_id: str, cai3_full) -> Optional[str]:
    """Find readable name for a block ID like 'b9'."""
    # Block IDs typically correspond to body content
    # Look for nodes with matching body references
    for node in cai3_full.nodes:
        if node.body_content and f"B#{block_id}" in node.body_content:
            return f"{node.type.value} `{node.name}`"
        # Also check if the block_id matches any part of the CID
        if block_id in node.cid:
            return f"{node.type.value} `{node.name}`"
    return None

def _find_readable_name_for_short(short_name: str, cai3_full, include_class: bool = False) -> Optional[str]:
    """Find readable name for a short name like 'ac' or 'vr'."""
    for node in cai3_full.nodes:
        if node.short_name == short_name:
            if include_class and node.parent_cid:
                # Find parent class
                parent_node = next((n for n in cai3_full.nodes if n.cid == node.parent_cid), None)
                if parent_node:
                    return f"{node.name}` in class `{parent_node.name}"
            return node.name
    return None

def _find_readable_name_for_cid(cid: str, cai3_full) -> Optional[str]:
    """Find readable name for a CID like 'fn_1a2c'."""
    for node in cai3_full.nodes:
        if node.cid == cid:
            if node.parent_cid:
                # Find parent class
                parent_node = next((n for n in cai3_full.nodes if n.cid == node.parent_cid), None)
                if parent_node:
                    return f"{node.type.value} `{node.name}` in class `{parent_node.name}`"
            return f"{node.type.value} `{node.name}`"
    return None

def _display_enhanced_compression_preview(metadata: Dict[str, Any], claude_metrics: Dict[str, Any], show_live_metrics: bool):
    """Display enhanced compression statistics with Claude Sonnet 4 cost analysis."""
    if not metadata.get("compressed"):
        # Store zero savings for non-compressed cases
        metadata.update({
            'estimated_input_savings': 0,
            'estimated_output_savings': 0,
            'estimated_total_savings': 0,
        })
        return
    
    # Get token counts - prefer Claude tokens if available
    original_tokens = metadata.get('original_tokens_claude', metadata.get('original_tokens', 0))
    compressed_tokens = metadata.get('compressed_tokens_claude', metadata.get('compressed_tokens', 0))
    saved_tokens = metadata.get('claude_tokens_saved', metadata.get('tokens_saved', 0))
    
    # If we don't have Claude tokens yet, calculate them from the saved tokens
    if original_tokens == 0 and saved_tokens > 0 and compressed_tokens > 0:
        original_tokens = compressed_tokens + saved_tokens
    
    # If we still don't have original tokens, try to calculate from compression ratio
    if original_tokens == 0 and compressed_tokens > 0 and metadata.get('compression_ratio'):
        compression_ratio_decimal = metadata['compression_ratio'] / 100
        original_tokens = int(compressed_tokens / (1 - compression_ratio_decimal))
        saved_tokens = original_tokens - compressed_tokens
    
    compression_ratio = (saved_tokens / original_tokens * 100) if original_tokens > 0 else 0
    
    # Only skip if we absolutely cannot get any token counts
    if original_tokens == 0 and compressed_tokens == 0:
        console.print("[yellow]⚠️ Token counts unavailable - skipping cost preview[/yellow]")
        # Store minimal metadata for consistency
        metadata.update({
            'estimated_input_savings': 0,
            'estimated_output_savings': 0,
            'estimated_total_savings': 0,
        })
        return
    
    if show_live_metrics:
        console.print("\n[bold cyan]🔬 Enhanced Claude Sonnet 4 Cost Analysis[/bold cyan]")
        console.print("=" * 60)
        # Debug: Show what metadata we have
        console.print(f"[dim]Debug - Metadata keys: {list(metadata.keys())}[/dim]")
        console.print(f"[dim]Debug - Original tokens: {original_tokens}, Compressed: {compressed_tokens}, Saved: {saved_tokens}[/dim]")
    
    # Create comprehensive comparison table
    table = Table(title="📊 Claude Sonnet 4 Compression Analysis", show_header=True, header_style="bold cyan")
    table.add_column("Metric", style="cyan", width=22)
    table.add_column("Without Compression", style="red", width=18)
    table.add_column("With Compression", style="green", width=16)
    table.add_column("Savings", style="bold yellow", width=16)
    
    # Token analysis
    table.add_row(
        "Input Tokens",
        f"{original_tokens:,}",
        f"{compressed_tokens:,}",
        f"{saved_tokens:,} ({compression_ratio:.1f}%)"
    )
    
    # Cost analysis with Claude Sonnet 4 pricing
    input_cost_per_mtok = claude_metrics['claude_input_cost_per_mtok']
    output_cost_per_mtok = claude_metrics['claude_output_cost_per_mtok']
    
    # Input costs
    original_input_cost = (original_tokens / 1_000_000) * input_cost_per_mtok
    compressed_input_cost = (compressed_tokens / 1_000_000) * input_cost_per_mtok
    input_savings = original_input_cost - compressed_input_cost
    
    table.add_row(
        "Input Cost",
        f"${original_input_cost:.4f}",
        f"${compressed_input_cost:.4f}",
        f"${input_savings:.4f}"
    )
    
    # Output cost estimation (using conservative 2.5x ratio)
    estimated_original_output_tokens = original_tokens * 2.5
    estimated_compressed_output_tokens = compressed_tokens * 2.5
    
    original_output_cost = (estimated_original_output_tokens / 1_000_000) * output_cost_per_mtok
    compressed_output_cost = (estimated_compressed_output_tokens / 1_000_000) * output_cost_per_mtok
    output_savings = original_output_cost - compressed_output_cost
    
    table.add_row(
        "Est. Output Cost",
        f"${original_output_cost:.4f}",
        f"${compressed_output_cost:.4f}",
        f"${output_savings:.4f}"
    )
    
    # Total estimated costs
    original_total_cost = original_input_cost + original_output_cost
    compressed_total_cost = compressed_input_cost + compressed_output_cost
    total_savings = original_total_cost - compressed_total_cost
    
    table.add_row(
        "[bold]Total Estimated Cost[/bold]",
        f"[bold]${original_total_cost:.4f}[/bold]",
        f"[bold]${compressed_total_cost:.4f}[/bold]",
        f"[bold]${total_savings:.4f}[/bold]"
    )
    
    console.print(table)
    
    if show_live_metrics:
        # Show methodology explanation
        console.print(f"\n[bold blue]💡 Cost Calculation Method:[/bold blue]")
        console.print(f"• Input tokens: ${input_cost_per_mtok}/MTok (actual compression measured)")
        console.print(f"• Output tokens: ${output_cost_per_mtok}/MTok (2.5x response ratio estimated)")
        console.print(f"• Model: {claude_metrics['claude_model']}")
        
        console.print(f"\n[yellow]📊 Claude Sonnet 4 Pricing Impact:[/yellow]")
        console.print(f"• Input compression saves ${input_savings:.4f} (modest)")
        console.print(f"• Output compression saves ${output_savings:.4f} (5x higher rate!)")
        console.print(f"• Total estimated savings: ${total_savings:.4f}")
        
        # Show cache pricing context
        console.print(f"\n[dim]🏪 Cache Pricing Reference:[/dim]")
        console.print(f"[dim]• Cache writes (5m): ${claude_metrics['claude_cache_write_5m_per_mtok']}/MTok[/dim]")
        console.print(f"[dim]• Cache writes (1h): ${claude_metrics['claude_cache_write_1h_per_mtok']}/MTok[/dim]")
        console.print(f"[dim]• Cache hits: ${claude_metrics['claude_cache_hit_per_mtok']}/MTok[/dim]")
    
    # Visual token bar
    _display_token_bar(original_tokens, compressed_tokens)
    
    # Store enhanced metadata
    metadata.update({
        'estimated_input_savings': input_savings,
        'estimated_output_savings': output_savings,
        'estimated_total_savings': total_savings,
        'original_input_cost': original_input_cost,
        'compressed_input_cost': compressed_input_cost,
        'estimated_original_output_cost': original_output_cost,
        'estimated_compressed_output_cost': compressed_output_cost,
        'claude_metrics': claude_metrics
    })

def _display_comprehensive_cost_analysis(
    original_tokens: int,
    compressed_tokens: int,
    response_tokens: int,
    claude_metrics: Dict[str, Any],
    metadata: Dict[str, Any],
    verbose: bool
):
    """Display comprehensive cost analysis comparing estimated vs actual costs."""
    if original_tokens == 0:
        console.print("[yellow]No token data available for cost analysis[/yellow]")
        return
    
    console.print("\n" + "=" * 70)
    console.print("[bold cyan]📊 Comprehensive Claude Sonnet 4 Cost Analysis[/bold cyan]")
    console.print("=" * 70)
    
    # Calculate actual costs
    input_cost_per_mtok = claude_metrics['claude_input_cost_per_mtok']
    output_cost_per_mtok = claude_metrics['claude_output_cost_per_mtok']
    
    # Actual costs
    actual_original_input_cost = (original_tokens / 1_000_000) * input_cost_per_mtok
    actual_compressed_input_cost = (compressed_tokens / 1_000_000) * input_cost_per_mtok
    actual_output_cost = (response_tokens / 1_000_000) * output_cost_per_mtok
    actual_input_savings = actual_original_input_cost - actual_compressed_input_cost
    
    # Calculate response ratio and estimated original response cost
    response_ratio = response_tokens / compressed_tokens if compressed_tokens > 0 else 0
    estimated_original_response_tokens = original_tokens * response_ratio
    estimated_original_output_cost = (estimated_original_response_tokens / 1_000_000) * output_cost_per_mtok
    actual_output_savings = estimated_original_output_cost - actual_output_cost
    actual_total_savings = actual_input_savings + actual_output_savings
    
    # Get estimated costs from metadata if available
    estimated_total_savings = metadata.get('estimated_total_savings', 0)
    estimated_input_savings = metadata.get('estimated_input_savings', 0)
    estimated_output_savings = metadata.get('estimated_output_savings', 0)
    
    # Create comprehensive analysis table
    analysis_table = Table(title="🎯 Actual vs Estimated Cost Analysis", show_header=True, header_style="bold magenta")
    analysis_table.add_column("Cost Component", style="cyan", width=20)
    analysis_table.add_column("Estimated", style="yellow", width=12)
    analysis_table.add_column("Actual", style="green", width=12)
    analysis_table.add_column("Accuracy", style="blue", width=15)
    analysis_table.add_column("Details", style="dim", width=20)
    
    # Input savings comparison
    input_accuracy = ""
    if estimated_input_savings > 0:
        input_accuracy_ratio = actual_input_savings / estimated_input_savings
        input_accuracy = f"{input_accuracy_ratio * 100:.1f}%"
    else:
        input_accuracy = "N/A"
    
    analysis_table.add_row(
        "Input Savings",
        f"${estimated_input_savings:.4f}",
        f"${actual_input_savings:.4f}",
        input_accuracy,
        f"{original_tokens - compressed_tokens:,} tokens"
    )
    
    # Output savings comparison
    output_accuracy = ""
    if estimated_output_savings > 0:
        output_accuracy_ratio = actual_output_savings / estimated_output_savings
        output_accuracy = f"{output_accuracy_ratio * 100:.1f}%"
        if output_accuracy_ratio < 0.8:
            output_accuracy += " (low)"
        elif output_accuracy_ratio > 1.2:
            output_accuracy += " (high)"
    else:
        output_accuracy = "N/A"
    
    analysis_table.add_row(
        "Output Savings",
        f"${estimated_output_savings:.4f}",
        f"${actual_output_savings:.4f}",
        output_accuracy,
        f"{response_ratio:.2f}x vs 2.5x ratio"
    )
    
    # Total savings comparison
    total_accuracy = ""
    if estimated_total_savings > 0:
        total_accuracy_ratio = actual_total_savings / estimated_total_savings
        total_accuracy = f"{total_accuracy_ratio * 100:.1f}%"
        if total_accuracy_ratio < 0.8:
            total_accuracy += " ⚠️"
        elif total_accuracy_ratio > 1.2:
            total_accuracy += " 🚀"
        else:
            total_accuracy += " ✅"
    else:
        total_accuracy = "N/A"
    
    analysis_table.add_row(
        "[bold]Total Savings[/bold]",
        f"[bold]${estimated_total_savings:.4f}[/bold]",
        f"[bold]${actual_total_savings:.4f}[/bold]",
        f"[bold]{total_accuracy}[/bold]",
        f"[bold]{response_tokens:,} response tokens[/bold]"
    )
    
    console.print(analysis_table)
    
    # Show actual costs incurred
    actual_total_cost = actual_compressed_input_cost + actual_output_cost
    estimated_original_total = (estimated_original_response_tokens / 1_000_000) * output_cost_per_mtok + actual_original_input_cost
    
    console.print(f"\n[bold green]💰 Actual Session Costs:[/bold green]")
    console.print(f"• Input cost (compressed): ${actual_compressed_input_cost:.4f}")
    console.print(f"• Output cost (actual): ${actual_output_cost:.4f}")
    console.print(f"• [bold blue]Total paid: ${actual_total_cost:.4f}[/bold blue]")
    console.print(f"• [bold red]Total saved: ${actual_total_savings:.4f}[/bold red]")
    console.print(f"• Would have cost: ${estimated_original_total:.4f}")
    
    # Show key insights
    console.print(f"\n[bold blue]🔍 Key Insights:[/bold blue]")
    
    # Response ratio insight
    if response_ratio < 1.5:
        console.print(f"• [green]Concise responses ({response_ratio:.2f}x) → Higher savings than estimated[/green]")
    elif response_ratio > 3.5:
        console.print(f"• [yellow]Verbose responses ({response_ratio:.2f}x) → Lower savings than estimated[/yellow]")
    else:
        console.print(f"• [blue]Normal responses ({response_ratio:.2f}x) → Savings close to estimates[/blue]")
    
    # Compression impact
    compression_ratio = (original_tokens - compressed_tokens) / original_tokens * 100 if original_tokens > 0 else 0
    if compression_ratio > 30:
        console.print(f"• [green]Excellent compression ({compression_ratio:.1f}%) → Significant cost reduction[/green]")
    elif compression_ratio > 15:
        console.print(f"• [blue]Good compression ({compression_ratio:.1f}%) → Moderate cost reduction[/blue]")
    else:
        console.print(f"• [yellow]Limited compression ({compression_ratio:.1f}%) → Minimal cost reduction[/yellow]")
    
    # Model-specific insight
    console.print(f"• [cyan]Model: {claude_metrics['claude_model']} with 5x higher output pricing[/cyan]")
    
    if verbose:
        # Show detailed breakdown
        console.print(f"\n[dim]🔬 Detailed Breakdown:[/dim]")
        console.print(f"[dim]• Original tokens: {original_tokens:,} → Compressed: {compressed_tokens:,}[/dim]")
        console.print(f"[dim]• Response tokens: {response_tokens:,} (ratio: {response_ratio:.2f}x)[/dim]")
        console.print(f"[dim]• Estimated original response: {estimated_original_response_tokens:,.0f} tokens[/dim]")
        console.print(f"[dim]• Token savings: {original_tokens - compressed_tokens:,} input + {estimated_original_response_tokens - response_tokens:,.0f} output[/dim]")

def _display_compression_preview(metadata: Dict[str, Any]):
    """Legacy compression preview - replaced by enhanced version."""
    # This function is kept for backward compatibility but calls the enhanced version
    claude_metrics = {
        'claude_model': 'claude-sonnet-4-20250514',
        'claude_input_cost_per_mtok': 3.0,
        'claude_output_cost_per_mtok': 15.0,
        'claude_cache_write_5m_per_mtok': 3.75,
        'claude_cache_write_1h_per_mtok': 6.0,
        'claude_cache_hit_per_mtok': 0.30,
    }
    _display_enhanced_compression_preview(metadata, claude_metrics, False)

def _display_token_bar(original: int, compressed: int):
    """Display visual representation of token savings."""
    max_width = 50
    compressed_width = int((compressed / original) * max_width) if original > 0 else 0
    saved_width = max_width - compressed_width
    
    console.print("\n📊 Token Usage:")
    console.print(f"Original:   [red]{'█' * max_width}[/red] {original:,}")
    console.print(f"Compressed: [green]{'█' * compressed_width}[/green][dim]{'░' * saved_width}[/dim] {compressed:,}")

def _create_cost_metrics_panel(
    original_tokens: int,
    compressed_tokens: int,
    response_tokens: int,
    claude_metrics: Dict[str, Any]
) -> Panel:
    """Create a cost metrics panel for display."""
    if original_tokens == 0:
        content = "[dim]No token data available[/dim]"
    else:
        # Calculate metrics
        tokens_saved = original_tokens - compressed_tokens
        compression_ratio = (tokens_saved / original_tokens * 100) if original_tokens > 0 else 0
        
        input_cost = (compressed_tokens / 1_000_000) * claude_metrics['claude_input_cost_per_mtok']
        output_cost = (response_tokens / 1_000_000) * claude_metrics['claude_output_cost_per_mtok']
        total_cost = input_cost + output_cost
        
        # Calculate savings
        original_input_cost = (original_tokens / 1_000_000) * claude_metrics['claude_input_cost_per_mtok']
        input_savings = original_input_cost - input_cost
        
        # Estimate output savings
        response_ratio = response_tokens / compressed_tokens if compressed_tokens > 0 else 0
        estimated_original_output = original_tokens * response_ratio
        estimated_original_output_cost = (estimated_original_output / 1_000_000) * claude_metrics['claude_output_cost_per_mtok']
        output_savings = estimated_original_output_cost - output_cost
        total_savings = input_savings + output_savings
        
        content = f"""[bold cyan]Claude Sonnet 4 Cost Metrics[/bold cyan]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[blue]Input Tokens:[/blue] {compressed_tokens:,} (saved {tokens_saved:,})
[magenta]Response Tokens:[/magenta] {response_tokens:,}
[yellow]Compression:[/yellow] {compression_ratio:.1f}% reduction
[bold green]Session Cost:[/bold green] ${total_cost:.4f}
[bold red]Estimated Savings:[/bold red] ${total_savings:.4f}
[dim]Response Ratio: {response_ratio:.2f}x[/dim]"""
    
    return Panel(content, border_style="blue", title="💰 Live Metrics", title_align="left")

def _show_cost_methodology_brief():
    """Show a brief explanation of the cost calculation methodology."""
    console.print(Panel(
        """[bold cyan]Claude Sonnet 4 Cost Analysis Method[/bold cyan]

[green]✅ What We Measure:[/green]
• Original input tokens (before compression)
• Compressed input tokens (after CAI3 compression)  
• Actual response tokens (Claude's output)

[blue]💰 Cost Calculation:[/blue]
• Input savings: token_reduction × $3/MTok
• Output estimation: response_ratio × original_tokens
• Total savings: input_savings + estimated_output_savings

[yellow]⚡ Key Insight:[/yellow]
With Claude Sonnet 4's 5x higher output pricing ($15 vs $3/MTok),
response compression provides the biggest cost impact!

[dim]Use --live-metrics for detailed analysis with actual response data.[/dim]""",
        title="💡 Cost Method",
        border_style="blue"
    ))

def _has_code_changes(output: str) -> bool:
    """Check if output contains code changes."""
    indicators = ['```python', 'def ', 'class ', 'import ', '#C3-PATCH']
    return any(indicator in output for indicator in indicators)

def _apply_patch_transactional(file_path: str, output: str) -> bool:
    """Apply patch with transactional safety - rollback on failure."""
    
    if not output or not output.strip():
        console.print("[yellow]No output to apply[/yellow]")
        return False
    
    # Extract code from output
    code_match = re.search(r'```python\n(.*?)```', output, re.DOTALL)
    if code_match:
        new_code = code_match.group(1)
        console.print(f"[dim]✓ Found Python code block ({len(new_code)} chars)[/dim]")
    elif ('def ' in output or 'class ' in output or 'import ' in output) and not output.startswith('```'):
        new_code = output.strip()
        console.print(f"[dim]✓ Using entire translated output as Python code ({len(new_code)} chars)[/dim]")
    else:
        console.print("[yellow]No Python code found in output[/yellow]")
        return False
    
    if not new_code.strip():
        console.print("[yellow]Code block is empty[/yellow]")
        return False
    
    original_path = Path(file_path)
    
    # Step 1: Parse check
    try:
        import ast
        ast.parse(new_code)
        console.print("[green]✓ Syntax validation passed[/green]")
    except SyntaxError as e:
        console.print(f"[red]✗ Syntax error in generated code: {e}[/red]")
        return False
    
    # Step 2: Quick lint (if available)
    try:
        import pyflakes.api
        import pyflakes.reporter
        import io
        warnings = io.StringIO()
        # Create a proper pyflakes reporter
        reporter = pyflakes.reporter.Reporter(warnings, warnings)
        pyflakes.api.check(new_code, '<generated>', reporter)
        if warnings.getvalue():
            console.print(f"[yellow]⚠ Lint warnings: {warnings.getvalue().strip()}[/yellow]")
        else:
            console.print("[green]✓ Lint check passed[/green]")
    except ImportError:
        console.print("[dim]Pyflakes not available, skipping lint check[/dim]")
    except Exception as e:
        console.print(f"[dim]Lint check failed: {e}[/dim]")
    
    # Step 3: Backup original
    from datetime import datetime
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = original_path.with_suffix(f'.bak_{timestamp}')
    
    import shutil
    shutil.copy2(original_path, backup_path)
    console.print(f"[dim]Backup created: {backup_path}[/dim]")
    
    try:
        # Step 4: Write new code
        original_path.write_text(new_code)
        
        # Step 5: Try to compile
        compile(new_code, str(original_path), 'exec')
        
        console.print(f"[green]✓ Successfully applied patch to {file_path}[/green]")
        console.print(f"[dim]  Original: {len(backup_path.read_text())} chars → New: {len(new_code)} chars[/dim]")
        return True
        
    except Exception as e:
        # Rollback on any failure
        console.print(f"[red]✗ Failed to apply patch: {e}[/red]")
        shutil.copy2(backup_path, original_path)
        console.print(f"[yellow]↶ Rolled back to original[/yellow]")
        return False

def _apply_patch(file_path: str, output: str):
    """Apply code changes to the file."""
    if not output or not output.strip():
        console.print("[yellow]No output to apply[/yellow]")
        return
    
    # Debug: Show what we're trying to apply
    console.print(f"[dim]🔍 Attempting to apply patch from {len(output)} character output[/dim]")
    
    # Method 1: Extract Python code from markdown code blocks
    code_match = re.search(r'```python\n(.*?)```', output, re.DOTALL)
    if code_match:
        new_code = code_match.group(1)
        console.print(f"[dim]✓ Found Python code block ({len(new_code)} chars)[/dim]")
    else:
        # Method 2: Check if the entire output is already Python code (post-CAI3 translation)
        # This happens when CAI3 was translated to full Python
        if ('def ' in output or 'class ' in output or 'import ' in output) and not output.startswith('```'):
            new_code = output.strip()
            console.print(f"[dim]✓ Using entire translated output as Python code ({len(new_code)} chars)[/dim]")
        else:
            console.print("[yellow]No code changes found to apply[/yellow]")
            console.print(f"[dim]Output preview: {output[:200]}{'...' if len(output) > 200 else ''}[/dim]")
            return
    
    if not new_code.strip():
        console.print("[yellow]Code block is empty[/yellow]")
        return
    
    # Backup original
    backup_path = Path(file_path).with_suffix('.bak')
    original_path = Path(file_path)
    
    if backup_path.exists():
        # If backup already exists, create a timestamped backup
        from datetime import datetime
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = Path(file_path).with_suffix(f'.bak_{timestamp}')
    
    original_path.rename(backup_path)
    console.print(f"[dim]Backup created: {backup_path}[/dim]")
    
    # Write new code
    original_path.write_text(new_code)
    console.print(f"[green]✓ Applied changes to {file_path}[/green]")
    console.print(f"[dim]  Original: {len(Path(backup_path).read_text())} chars → New: {len(new_code)} chars[/dim]")

@claude_code.command()
@click.option('--model', default='claude-sonnet-4-20250514', help='Claude model for pricing analysis')
def cost_analysis(model):
    """Show detailed Claude cost analysis methodology and pricing information."""
    
    # Claude Sonnet 4 pricing
    claude_metrics = {
        'claude_model': model,
        'claude_input_cost_per_mtok': 3.0,      # $3 per million input tokens
        'claude_output_cost_per_mtok': 15.0,    # $15 per million output tokens
        'claude_cache_write_5m_per_mtok': 3.75, # $3.75 per million (5min cache)
        'claude_cache_write_1h_per_mtok': 6.0,  # $6 per million (1h cache)
        'claude_cache_hit_per_mtok': 0.30,      # $0.30 per million (cache hits)
    }
    
    console.print(Panel(
        f"""[bold cyan]Claude {model} Cost Analysis Methodology[/bold cyan]

[bold green]🎯 What OptimizeAI Measures Accurately:[/bold green]
• [green]Original input tokens[/green]: Full prompt before compression
• [green]Compressed input tokens[/green]: After CAI3 compression applied  
• [green]Actual response tokens[/green]: Claude's real output length
• [green]Input cost savings[/green]: Measured compression × input rate
• [green]Response cost[/green]: Actual output × output rate

[bold blue]📊 Enhanced Cost Estimation Method:[/bold blue]
[cyan]1. Response Pattern Analysis:[/cyan]
   • Measure: actual_response ÷ compressed_input = response_ratio
   • This shows how "verbose" Claude is for your specific requests

[cyan]2. Original Response Estimation:[/cyan]
   • Estimate: original_input × response_ratio = estimated_original_response
   • Estimate: estimated_original_response - actual_response = response_savings

[cyan]3. Total Savings Calculation:[/cyan]
   • Input savings: (original_input - compressed_input) × ${claude_metrics['claude_input_cost_per_mtok']}/MTok
   • Output savings: response_savings × ${claude_metrics['claude_output_cost_per_mtok']}/MTok
   • Total: input_savings + output_savings

[bold yellow]💰 Claude {model} Official Pricing:[/bold yellow]
• Base Input: ${claude_metrics['claude_input_cost_per_mtok']}/MTok | Output: ${claude_metrics['claude_output_cost_per_mtok']}/MTok
• Cache Writes (5m): ${claude_metrics['claude_cache_write_5m_per_mtok']}/MTok | Cache Writes (1h): ${claude_metrics['claude_cache_write_1h_per_mtok']}/MTok  
• Cache Hits & Refreshes: ${claude_metrics['claude_cache_hit_per_mtok']}/MTok

[bold red]🚀 Key Cost Impact Insight:[/bold red]
Output tokens cost 5x more than input tokens (${claude_metrics['claude_output_cost_per_mtok']} vs ${claude_metrics['claude_input_cost_per_mtok']}/MTok)!
This makes response length reduction far more valuable than input compression.

[bold green]📈 Example Savings Scenario:[/bold green]
• Original: 1000 input tokens → Compressed: 700 tokens (300 saved)
• Response: 350 tokens (ratio: 0.5x) → Est. original response: 500 tokens
• Input savings: 300 × ${claude_metrics['claude_input_cost_per_mtok']}/MTok = $0.0009
• Output savings: 150 × ${claude_metrics['claude_output_cost_per_mtok']}/MTok = $0.00225
• Total savings: $0.00315 (output savings are 2.5x larger!)

[bold blue]🔧 Usage Tips:[/bold blue]
• Use --live-metrics flag for real-time cost analysis
• Focus on prompts that generate long responses for max savings
• Monitor your response ratios to refine estimates
• Use interactive mode for session-wide cost tracking

[dim]This methodology uses actual Claude response data for better accuracy
than static 2.5x output estimates used in basic mode.[/dim]""",
        title=f"💡 Claude {model} Cost Analysis Guide",
        border_style="blue",
        width=None,
        height=None,
        padding=(1, 2)
    ))

@claude_code.command()
@click.argument('files', type=click.Path(exists=True), nargs=-1, required=True)
@click.option('--output', '-o', type=click.Path(), help='Output directory for analysis')
@click.option('--live-metrics', '-l', is_flag=True, help='Show detailed cost analysis')
def analyze(files, output, live_metrics):
    """Analyze multiple files with enhanced compression and cost statistics."""
    total_original = 0
    total_compressed = 0
    total_estimated_savings = 0
    
    # Claude metrics for cost analysis
    claude_metrics = {
        'claude_model': 'claude-sonnet-4-20250514',
        'claude_input_cost_per_mtok': 3.0,
        'claude_output_cost_per_mtok': 15.0,
    }
    
    results = []
    
    for file_path in files:
        console.print(f"\n[cyan]Analyzing {file_path}...[/cyan]")
        
        # Compress the file
        proxy = ClaudeCodeProxy(enable_compression=True)
        content = Path(file_path).read_text()
        
        # Get original tokens with Claude counting
        original_claude_tokens = 0
        try:
            original_claude_tokens = count_tokens_claude(content, claude_metrics['claude_model'])
        except Exception:
            pass
        
        compressed, metadata = proxy.process_input(content, file_path)
        
        # Get compressed tokens with Claude counting
        compressed_claude_tokens = 0
        try:
            compressed_claude_tokens = count_tokens_claude(compressed, claude_metrics['claude_model'])
        except Exception:
            compressed_claude_tokens = metadata.get('compressed_tokens', 0)
        
        # Use Claude token counts if available, fallback to metadata
        original_tokens = original_claude_tokens or metadata.get('original_tokens', 0)
        compressed_tokens = compressed_claude_tokens or metadata.get('compressed_tokens', 0)
        
        total_original += original_tokens
        total_compressed += compressed_tokens
        
        # Calculate cost savings
        input_savings = ((original_tokens - compressed_tokens) / 1_000_000) * claude_metrics['claude_input_cost_per_mtok']
        # Estimate output savings using 2.5x ratio
        estimated_output_savings = input_savings * 2.5 * (claude_metrics['claude_output_cost_per_mtok'] / claude_metrics['claude_input_cost_per_mtok'])
        total_file_savings = input_savings + estimated_output_savings
        total_estimated_savings += total_file_savings
        
        results.append({
            'file': file_path,
            'original': original_tokens,
            'compressed': compressed_tokens,
            'ratio': ((original_tokens - compressed_tokens) / original_tokens * 100) if original_tokens > 0 else 0,
            'estimated_savings': total_file_savings,
            'input_savings': input_savings,
            'output_savings': estimated_output_savings
        })
    
    # Display summary
    table = Table(title="📊 Enhanced Compression Analysis Summary")
    table.add_column("File", style="cyan")
    table.add_column("Original", style="red")
    table.add_column("Compressed", style="green")
    table.add_column("Reduction", style="yellow")
    
    if live_metrics:
        table.add_column("Est. Savings", style="bold blue")
    
    for r in results:
        row_data = [
            Path(r['file']).name,
            f"{r['original']:,}",
            f"{r['compressed']:,}",
            f"{r['ratio']:.1f}%"
        ]
        
        if live_metrics:
            row_data.append(f"${r['estimated_savings']:.4f}")
        
        table.add_row(*row_data)
    
    # Add totals row
    total_reduction = (1 - total_compressed/total_original)*100 if total_original > 0 else 0
    totals_data = [
        "TOTAL",
        f"{total_original:,}",
        f"{total_compressed:,}",
        f"{total_reduction:.1f}%"
    ]
    
    if live_metrics:
        totals_data.append(f"${total_estimated_savings:.4f}")
    
    table.add_row("─" * 20, "─" * 10, "─" * 10, "─" * 10, *("─" * 12,) if live_metrics else ())
    table.add_row(*totals_data)
    
    console.print(table)
    
    if live_metrics:
        # Show detailed cost breakdown
        console.print(f"\n[bold blue]💰 Claude Sonnet 4 Cost Analysis:[/bold blue]")
        total_input_savings = ((total_original - total_compressed) / 1_000_000) * claude_metrics['claude_input_cost_per_mtok']
        total_output_savings = total_estimated_savings - total_input_savings
        
        console.print(f"• Input compression savings: ${total_input_savings:.4f}")
        console.print(f"• Estimated output savings: ${total_output_savings:.4f}")
        console.print(f"• [bold green]Total estimated savings: ${total_estimated_savings:.4f}[/bold green]")
        console.print(f"• Average savings per file: ${total_estimated_savings / len(results):.4f}")
        
        console.print(f"\n[yellow]💡 Insights:[/yellow]")
        console.print(f"• Output savings are {total_output_savings / total_input_savings:.1f}x larger due to 5x higher pricing")
        console.print(f"• Total tokens compressed: {total_original - total_compressed:,}")
        console.print(f"• Average compression: {total_reduction:.1f}%")
    
    if output:
        # Save analysis to JSON
        output_path = Path(output) / "enhanced_compression_analysis.json"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        analysis_data = {
            'files': results,
            'summary': {
                'total_original': total_original,
                'total_compressed': total_compressed,
                'overall_reduction': total_reduction,
                'total_estimated_savings': total_estimated_savings,
                'claude_model': claude_metrics['claude_model'],
                'analysis_timestamp': str(Path().absolute())
            },
            'claude_metrics': claude_metrics
        }
        
        with open(output_path, 'w') as f:
            json.dump(analysis_data, f, indent=2)
        
        console.print(f"\n[green]✓ Enhanced analysis saved to {output_path}[/green]")

# Legacy analyze command
@claude_code.command(hidden=True)  # Hide the old version
@click.argument('files', type=click.Path(exists=True), nargs=-1, required=True)
@click.option('--output', '-o', type=click.Path(), help='Output directory for analysis')
def analyze_legacy(files, output):
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