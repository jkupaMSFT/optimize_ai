# ===== cli/commands/translate.py =====
import click
from pathlib import Path
import logging
import json
from ...output_translator.core.translator import CAIToPythonTranslator

# Set up logging
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

@click.command()
@click.argument('cai_file', type=click.Path(exists=True, file_okay=True, dir_okay=False, readable=True))
@click.option('--output', type=click.Path(), help='Output Python file path (default: stdout)')
@click.option('--json-output', is_flag=True, help='Output translation stats in JSON format')
@click.option('--verbose', is_flag=True, help='Enable verbose logging')
def translate(cai_file: str, output: str, json_output: bool, verbose: bool):
    """
    Translate CAI file back to Python.
    
    This command takes a CAI (Compressed AI) file, translates it back
    to executable Python code, and outputs the result either to stdout
    or a specified file.
    """
    if verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    path = Path(cai_file)
    
    # Optional: Check file extension, but since CAI might not have strict extension, warn if not .cai
    if path.suffix != '.cai':
        logger.warning(f"File extension is {path.suffix}, expected .cai. Proceeding anyway.")
    
    try:
        translator = CAIToPythonTranslator()
        
        cai_content = path.read_text(encoding='utf-8')
        
        # Create a temporary session for CLI usage
        session_id = "cli_translate_session"
        result = translator.translate(session_id, cai_content)
        
        if result.success:
            python_code = result.python_code
            
            if output:
                Path(output).write_text(python_code, encoding='utf-8')
                click.echo(f"Translated file saved to {output}")
            else:
                click.echo(python_code)
            
            stats = {
                "similarity_score": result.similarity_score * 100,
                "error_count": len(result.errors),
                "success": True
            }
            
            if json_output:
                click.echo(json.dumps(stats, indent=2))
            else:
                click.echo(f"Translation similarity: {result.similarity_score * 100:.1f}%")
            
            if result.errors:
                click.echo("Partial success with warnings:")
                for error in result.errors:
                    click.echo(f"Warning: {error}")
            
            logger.info("Translation completed successfully")
        
        else:
            stats = {
                "similarity_score": 0,
                "error_count": len(result.errors),
                "success": False
            }
            
            if json_output:
                click.echo(json.dumps(stats, indent=2))
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