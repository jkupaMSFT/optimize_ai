# ===== cli/commands/compress.py =====
import click
from pathlib import Path
import logging
import json
import time
from datetime import datetime
from input_optimizer.engine.waterfall_compressor import WaterfallCompressor, CompressionTier

# Try to import metrics collector for enhanced reporting
try:
    from integrations.claude_wrapper.metrics import MetricsCollector
    HAS_METRICS = True
except ImportError:
    HAS_METRICS = False

# Set up logging
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

@click.command()
@click.argument('file_path', type=click.Path(exists=True, file_okay=True, dir_okay=False, readable=True))
@click.option('--tier', type=click.Choice(['tiny', 'small', 'medium', 'large', 'huge'], case_sensitive=False), help='Force specific compression tier')
@click.option('--output', type=click.Path(), help='Output file path (default: stdout)')
@click.option('--json-output', is_flag=True, help='Output compression stats in JSON format')
@click.option('--verbose', is_flag=True, help='Enable verbose logging')
@click.option('--show-metrics', is_flag=True, default=True, help='Show comprehensive metrics (default: enabled)')
@click.option('--hide-metrics', is_flag=True, help='Hide metrics display')
def compress(file_path: str, tier: str, output: str, json_output: bool, verbose: bool, show_metrics: bool, hide_metrics: bool):
    """
    Compress a Python file using waterfall compression.
    
    This command takes a Python file, applies multi-tier compression,
    and outputs the compressed content either to stdout or a file.
    Comprehensive metrics are shown by default.
    """
    if verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Determine if we should show metrics
    display_metrics = show_metrics and not hide_metrics
    
    path = Path(file_path)
    
    if path.suffix != '.py':
        logger.error("File must be a Python (.py) file")
        raise click.BadArgumentUsage("File must be a Python (.py) file")
    
    # Initialize metrics collector if available
    metrics_collector = None
    if HAS_METRICS and display_metrics:
        metrics_collector = MetricsCollector()
    
    start_time = time.time()
    
    try:
        compressor = WaterfallCompressor()
        
        if tier:
            logger.info(f"Note: Tier '{tier}' specified, but compression tier is auto-determined by file size")
        
        # Read original content for metrics
        original_content = path.read_text(encoding='utf-8')
        original_size = len(original_content)
        
        result = compressor.compress_file(path)
        
        end_time = time.time()
        processing_time = end_time - start_time
        
        output_content = result.content
        compressed_size = len(output_content)
        
        # Calculate additional metrics
        size_reduction_bytes = original_size - compressed_size
        size_reduction_pct = (size_reduction_bytes / original_size) * 100 if original_size > 0 else 0
        tokens_saved = result.original_tokens - result.compressed_tokens
        
        # Estimate cost savings (using GPT-4 pricing: ~$0.03/1K tokens input, ~$0.06/1K tokens output)
        input_cost_per_1k = 0.03
        output_cost_per_1k = 0.06
        # Assume 50/50 split for cost calculation
        avg_cost_per_1k = (input_cost_per_1k + output_cost_per_1k) / 2
        estimated_cost_savings = (tokens_saved / 1000) * avg_cost_per_1k
        
        # Output the compressed content
        if output:
            Path(output).write_text(output_content, encoding='utf-8')
            click.echo(f"✅ Compressed file saved to {output}")
        else:
            # Separate compressed content from metrics with clear dividers
            if display_metrics and not json_output:
                click.echo("=" * 60)
                click.echo("🗜️  COMPRESSED CONTENT")
                click.echo("=" * 60)
            
            click.echo(output_content)
            
            if display_metrics and not json_output:
                click.echo("=" * 60)
        
        # Display comprehensive metrics
        if display_metrics:
            if json_output:
                # Comprehensive JSON output
                metrics_data = {
                    "file_info": {
                        "input_file": str(path),
                        "output_file": output if output else "stdout",
                        "processing_time_seconds": round(processing_time, 3)
                    },
                    "compression_metrics": {
                        "tier_used": result.tier_used.value,
                        "method_used": result.method_used,
                        "compression_ratio_percent": round(result.compression_ratio, 2),
                        "original_tokens": result.original_tokens,
                        "compressed_tokens": result.compressed_tokens,
                        "tokens_saved": tokens_saved,
                        "token_reduction_percent": round((tokens_saved / result.original_tokens) * 100, 2) if result.original_tokens > 0 else 0
                    },
                    "size_metrics": {
                        "original_size_bytes": original_size,
                        "compressed_size_bytes": compressed_size,
                        "size_reduction_bytes": size_reduction_bytes,
                        "size_reduction_percent": round(size_reduction_pct, 2)
                    },
                    "cost_analysis": {
                        "estimated_cost_savings_usd": round(estimated_cost_savings, 4),
                        "cost_savings_per_1k_tokens": round(avg_cost_per_1k, 4)
                    },
                    "efficiency": {
                        "tokens_per_second": round(result.original_tokens / processing_time, 2) if processing_time > 0 else 0,
                        "compression_efficiency": "High" if result.compression_ratio > 20 else "Medium" if result.compression_ratio > 10 else "Low"
                    }
                }
                
                click.echo(json.dumps(metrics_data, indent=2))
            else:
                # Pretty-printed metrics display
                click.echo("📊 COMPRESSION METRICS")
                click.echo("=" * 60)
                
                # File information
                click.echo(f"📁 File: {path.name}")
                click.echo(f"⏱️  Processing time: {processing_time:.3f}s")
                click.echo(f"🔧 Method: {result.method_used}")
                click.echo(f"🎯 Tier: {result.tier_used.value}")
                
                click.echo("\n🗜️  Token Analysis:")
                click.echo(f"   Original tokens:    {result.original_tokens:,}")
                click.echo(f"   Compressed tokens:  {result.compressed_tokens:,}")
                click.echo(f"   Tokens saved:       {tokens_saved:,}")
                click.echo(f"   Token reduction:    {(tokens_saved / result.original_tokens) * 100:.1f}%" if result.original_tokens > 0 else "   Token reduction:    0%")
                
                click.echo("\n📏 Size Analysis:")
                click.echo(f"   Original size:      {original_size:,} bytes")
                click.echo(f"   Compressed size:    {compressed_size:,} bytes")
                click.echo(f"   Size reduction:     {size_reduction_bytes:,} bytes ({size_reduction_pct:.1f}%)")
                
                click.echo("\n💰 Cost Impact:")
                click.echo(f"   Estimated savings:  ${estimated_cost_savings:.4f}")
                click.echo(f"   Cost per 1K tokens: ${avg_cost_per_1k:.4f}")
                
                click.echo("\n⚡ Performance:")
                tokens_per_sec = result.original_tokens / processing_time if processing_time > 0 else 0
                click.echo(f"   Processing speed:   {tokens_per_sec:,.0f} tokens/second")
                
                efficiency = "High" if result.compression_ratio > 20 else "Medium" if result.compression_ratio > 10 else "Low"
                click.echo(f"   Compression efficiency: {efficiency}")
                
                # Record operation in metrics collector if available
                if metrics_collector:
                    try:
                        metrics_collector.record_file_operation(
                            operation_type="compression",
                            original_content=original_content,
                            compressed_content=output_content,
                            file_path=str(path),
                            task_context=f"CLI compression using {result.method_used}"
                        )
                    except Exception as e:
                        if verbose:
                            click.echo(f"⚠️  Warning: Could not record metrics: {e}")
                
                click.echo("=" * 60)
        elif not json_output:
            # Minimal metrics when metrics are disabled
            click.echo(f"✅ Compression complete: {result.compression_ratio:.1f}% reduction (Tier: {result.tier_used.value})")
        
        logger.info("Compression completed successfully")
    
    except ValueError as e:
        logger.error(f"Invalid input: {str(e)}")
        raise click.BadArgumentUsage(str(e))
    except Exception as e:
        logger.error(f"Compression failed: {str(e)}")
        raise click.ClickException(f"Compression failed: {str(e)}")