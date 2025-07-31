# ===== cli/commands/compress.py =====
import click
from pathlib import Path
import logging
import json
from ...input_optimizer.engine.waterfall_compressor import WaterfallCompressor, CompressionTier

# Set up logging
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

@click.command()
@click.argument('file_path', type=click.Path(exists=True, file_okay=True, dir_okay=False, readable=True))
@click.option('--tier', type=click.Choice(['tiny', 'small', 'medium', 'large', 'huge'], case_sensitive=False), help='Force specific compression tier')
@click.option('--output', type=click.Path(), help='Output file path (default: stdout)')
@click.option('--json-output', is_flag=True, help='Output compression stats in JSON format')
@click.option('--verbose', is_flag=True, help='Enable verbose logging')
def compress(file_path: str, tier: str, output: str, json_output: bool, verbose: bool):
    """
    Compress a Python file using waterfall compression.
    
    This command takes a Python file, applies multi-tier compression,
    and outputs the compressed content either to stdout or a file.
    """
    if verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    path = Path(file_path)
    
    if path.suffix != '.py':
        logger.error("File must be a Python (.py) file")
        raise click.BadArgumentUsage("File must be a Python (.py) file")
    
    try:
        compressor = WaterfallCompressor()
        
        compression_tier = None
        if tier:
            compression_tier = CompressionTier[tier.upper()]
            logger.info(f"Using forced tier: {compression_tier}")
        
        result = compressor.compress_file(path, tier=compression_tier)
        
        output_content = result.content
        
        if output:
            Path(output).write_text(output_content, encoding='utf-8')
            click.echo(f"Compressed file saved to {output}")
        else:
            click.echo(output_content)
        
        stats = {
            "original_tokens": result.original_tokens,
            "compressed_tokens": result.compressed_tokens,
            "compression_ratio": result.compression_ratio,
            "tier_used": result.tier_used.value
        }
        
        if json_output:
            click.echo(json.dumps(stats, indent=2))
        else:
            click.echo(f"Compression stats: {result.compression_ratio}% reduction (Tier: {result.tier_used.value})")
        
        logger.info("Compression completed successfully")
    
    except ValueError as e:
        logger.error(f"Invalid input: {str(e)}")
        raise click.BadArgumentUsage(str(e))
    except Exception as e:
        logger.error(f"Compression failed: {str(e)}")
        raise click.ClickException(f"Compression failed: {str(e)}")