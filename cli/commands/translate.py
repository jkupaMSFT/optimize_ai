# ===== cli/commands/translate.py =====
import click
from pathlib import Path
import logging
import json
import time
from datetime import datetime
from output_translator.core.translator import CAIToPythonTranslator

# Try to import metrics collector and token utilities
try:
    from integrations.claude_wrapper.metrics import MetricsCollector
    HAS_METRICS = True
except ImportError:
    HAS_METRICS = False

try:
    from utils.logger import estimate_tokens
    HAS_TOKEN_UTILS = True
except ImportError:
    # Fallback token counting
    def estimate_tokens(text: str) -> int:
        """Simple fallback token estimation"""
        return max(1, len(text.split()) * 1.3)
    HAS_TOKEN_UTILS = False

# Set up logging
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

@click.command()
@click.argument('cai_file', type=click.Path(exists=True, file_okay=True, dir_okay=False, readable=True))
@click.option('--output', type=click.Path(), help='Output Python file path (default: stdout)')
@click.option('--json-output', is_flag=True, help='Output translation stats in JSON format')
@click.option('--verbose', is_flag=True, help='Enable verbose logging')
@click.option('--show-metrics', is_flag=True, default=True, help='Show comprehensive metrics (default: enabled)')
@click.option('--hide-metrics', is_flag=True, help='Hide metrics display')
def translate(cai_file: str, output: str, json_output: bool, verbose: bool, show_metrics: bool, hide_metrics: bool):
    """
    Translate CAI file back to Python with comprehensive cost analysis.
    
    This command takes a CAI (Compressed AI) file, translates it back
    to executable Python code, and shows detailed metrics about the
    translation process including cost savings from compression.
    """
    if verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Determine if we should show metrics
    display_metrics = show_metrics and not hide_metrics
    
    path = Path(cai_file)
    
    # Optional: Check file extension, but since CAI might not have strict extension, warn if not .cai
    if path.suffix != '.cai':
        logger.warning(f"File extension is {path.suffix}, expected .cai. Proceeding anyway.")
    
    # Initialize metrics collector if available
    metrics_collector = None
    if HAS_METRICS and display_metrics:
        metrics_collector = MetricsCollector()
    
    start_time = time.time()
    
    try:
        translator = CAIToPythonTranslator()
        
        # Read CAI content for metrics
        cai_content = path.read_text(encoding='utf-8')
        cai_size = len(cai_content)
        cai_tokens = estimate_tokens(cai_content)
        
        # Create a temporary session for CLI usage
        session_id = "cli_translate_session"
        result = translator.translate(session_id, cai_content)
        
        end_time = time.time()
        processing_time = end_time - start_time
        
        if result.success:
            python_code = result.python_code
            python_size = len(python_code)
            python_tokens = estimate_tokens(python_code)
            
            # Calculate expansion metrics
            size_expansion_bytes = python_size - cai_size
            size_expansion_pct = (size_expansion_bytes / cai_size) * 100 if cai_size > 0 else 0
            token_expansion = python_tokens - cai_tokens
            token_expansion_pct = (token_expansion / cai_tokens) * 100 if cai_tokens > 0 else 0
            
            # Calculate cost savings from using compressed format
            # Assume we saved tokens during compression (reverse calculation)
            # This shows the benefit of having worked with compressed format
            input_cost_per_1k = 0.03  # GPT-4 input pricing
            output_cost_per_1k = 0.06  # GPT-4 output pricing
            
            # Cost if we had processed the full Python code directly
            full_processing_cost = (python_tokens / 1000) * input_cost_per_1k
            
            # Cost of processing the compressed CAI format
            compressed_processing_cost = (cai_tokens / 1000) * input_cost_per_1k
            
            # Translation output cost (generating Python from CAI)
            translation_output_cost = (python_tokens / 1000) * output_cost_per_1k
            
            # Total cost with compression workflow
            total_compressed_workflow_cost = compressed_processing_cost + translation_output_cost
            
            # Cost savings from compression
            compression_savings = full_processing_cost - compressed_processing_cost
            
            # Output the translated content
            if output:
                Path(output).write_text(python_code, encoding='utf-8')
                click.echo(f"✅ Translated file saved to {output}")
            else:
                # Separate translated content from metrics with clear dividers
                if display_metrics and not json_output:
                    click.echo("=" * 60)
                    click.echo("🔄 TRANSLATED PYTHON CODE")
                    click.echo("=" * 60)
                
                click.echo(python_code)
                
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
                        "translation_metrics": {
                            "success": True,
                            "similarity_score_percent": round(result.similarity_score * 100, 2),
                            "error_count": len(result.errors),
                            "translation_quality": "High" if result.similarity_score > 0.95 else "Medium" if result.similarity_score > 0.8 else "Low"
                        },
                        "size_metrics": {
                            "cai_size_bytes": cai_size,
                            "python_size_bytes": python_size,
                            "size_expansion_bytes": size_expansion_bytes,
                            "size_expansion_percent": round(size_expansion_pct, 2)
                        },
                        "token_metrics": {
                            "cai_tokens": cai_tokens,
                            "python_tokens": python_tokens,
                            "token_expansion": token_expansion,
                            "token_expansion_percent": round(token_expansion_pct, 2)
                        },
                        "cost_analysis": {
                            "full_processing_cost_usd": round(full_processing_cost, 4),
                            "compressed_processing_cost_usd": round(compressed_processing_cost, 4),
                            "translation_output_cost_usd": round(translation_output_cost, 4),
                            "total_compressed_workflow_cost_usd": round(total_compressed_workflow_cost, 4),
                            "compression_savings_usd": round(compression_savings, 4),
                            "cost_efficiency_percent": round((compression_savings / full_processing_cost) * 100, 2) if full_processing_cost > 0 else 0
                        },
                        "performance": {
                            "tokens_per_second": round(python_tokens / processing_time, 2) if processing_time > 0 else 0,
                            "translation_efficiency": "Fast" if processing_time < 1 else "Medium" if processing_time < 5 else "Slow"
                        }
                    }
                    
                    if result.errors:
                        metrics_data["warnings"] = result.errors
                    
                    click.echo(json.dumps(metrics_data, indent=2))
                else:
                    # Pretty-printed metrics display
                    click.echo("📊 TRANSLATION METRICS")
                    click.echo("=" * 60)
                    
                    # File information
                    click.echo(f"📁 File: {path.name}")
                    click.echo(f"⏱️  Processing time: {processing_time:.3f}s")
                    click.echo(f"✅ Translation: {'Success' if result.success else 'Failed'}")
                    click.echo(f"🎯 Quality: {result.similarity_score * 100:.1f}% similarity")
                    
                    quality_label = "High" if result.similarity_score > 0.95 else "Medium" if result.similarity_score > 0.8 else "Low"
                    click.echo(f"⭐ Quality rating: {quality_label}")
                    
                    click.echo("\n🔄 Expansion Analysis:")
                    click.echo(f"   CAI size:          {cai_size:,} bytes")
                    click.echo(f"   Python size:       {python_size:,} bytes")
                    click.echo(f"   Size expansion:    {size_expansion_bytes:,} bytes ({size_expansion_pct:.1f}%)")
                    
                    click.echo("\n🎫 Token Analysis:")
                    click.echo(f"   CAI tokens:        {cai_tokens:,}")
                    click.echo(f"   Python tokens:     {python_tokens:,}")
                    click.echo(f"   Token expansion:   {token_expansion:,} ({token_expansion_pct:.1f}%)")
                    
                    click.echo("\n💰 Cost Impact Analysis:")
                    click.echo(f"   Direct processing:     ${full_processing_cost:.4f}")
                    click.echo(f"   Compressed processing: ${compressed_processing_cost:.4f}")
                    click.echo(f"   Translation output:    ${translation_output_cost:.4f}")
                    click.echo(f"   Total workflow cost:   ${total_compressed_workflow_cost:.4f}")
                    click.echo(f"   💡 Compression savings: ${compression_savings:.4f}")
                    
                    if compression_savings > 0:
                        efficiency_pct = (compression_savings / full_processing_cost) * 100
                        click.echo(f"   📈 Cost efficiency:    {efficiency_pct:.1f}%")
                    
                    click.echo("\n⚡ Performance:")
                    tokens_per_sec = python_tokens / processing_time if processing_time > 0 else 0
                    click.echo(f"   Translation speed:  {tokens_per_sec:,.0f} tokens/second")
                    
                    perf_label = "Fast" if processing_time < 1 else "Medium" if processing_time < 5 else "Slow"
                    click.echo(f"   Performance rating: {perf_label}")
                    
                    # Show workflow summary
                    click.echo("\n🔍 Workflow Summary:")
                    click.echo(f"   CAI → Python translation completed successfully")
                    click.echo(f"   Compression workflow saved ${compression_savings:.4f} vs direct processing")
                    click.echo(f"   Translation quality: {result.similarity_score * 100:.1f}%")
                    
                    if result.errors:
                        click.echo(f"\n⚠️  Warnings ({len(result.errors)}):")
                        for error in result.errors[:3]:  # Show first 3 errors
                            click.echo(f"   • {error}")
                        if len(result.errors) > 3:
                            click.echo(f"   • ... and {len(result.errors) - 3} more")
                    
                    # Record operation in metrics collector if available
                    if metrics_collector:
                        try:
                            metrics_collector.record_file_operation(
                                operation_type="translation",
                                original_content=cai_content,
                                compressed_content=python_code,
                                file_path=str(path),
                                task_context=f"CLI translation with {result.similarity_score:.1%} similarity"
                            )
                        except Exception as e:
                            if verbose:
                                click.echo(f"⚠️  Warning: Could not record metrics: {e}")
                    
                    click.echo("=" * 60)
            elif not json_output:
                # Minimal metrics when metrics are disabled
                click.echo(f"✅ Translation complete: {result.similarity_score * 100:.1f}% similarity")
            
            logger.info("Translation completed successfully")
        
        else:
            # Handle translation failure
            if display_metrics:
                if json_output:
                    error_data = {
                        "file_info": {
                            "input_file": str(path),
                            "processing_time_seconds": round(processing_time, 3)
                        },
                        "translation_metrics": {
                            "success": False,
                            "similarity_score_percent": 0,
                            "error_count": len(result.errors)
                        },
                        "errors": result.errors
                    }
                    click.echo(json.dumps(error_data, indent=2))
                else:
                    click.echo("❌ TRANSLATION FAILED")
                    click.echo("=" * 60)
                    click.echo(f"📁 File: {path.name}")
                    click.echo(f"⏱️  Processing time: {processing_time:.3f}s")
                    click.echo(f"❌ Errors: {len(result.errors)}")
                    click.echo("\n🚨 Error Details:")
                    for i, error in enumerate(result.errors, 1):
                        click.echo(f"   {i}. {error}")
                    click.echo("=" * 60)
            else:
                click.echo("Translation failed")
                for error in result.errors:
                    click.echo(f"Error: {error}")
            
            logger.error("Translation failed")
            raise click.ClickException("Translation failed")
    
    except FileNotFoundError as e:
        logger.error(f"File not found: {str(e)}")
        raise click.BadArgumentUsage(str(e))
    except UnicodeDecodeError as e:
        logger.error(f"Encoding error: {str(e)}")
        raise click.ClickException("File encoding error; ensure UTF-8")
    except ValueError as e:
        logger.error(f"Invalid input: {str(e)}")
        raise click.BadArgumentUsage(str(e))
    except Exception as e:
        logger.error(f"Translation failed: {str(e)}")
        raise click.ClickException(f"Translation failed: {str(e)}")