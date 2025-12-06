# ===== cli/main.py =====
import click
import logging
import sys
import os

# Add the parent directory to the Python path for absolute imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    # Try absolute imports first
    from cli.commands.compress import compress
    from cli.commands.translate import translate
    from cli.commands.session import session
    from cli.commands.integrate import integrate
    from cli.commands.demo import demo
    from cli.commands.claude_code import claude_code
    claude_code_available = True
except ImportError as e:
    print(f"Absolute import error: {e}")
    claude_code_available = False
    try:
        # Try relative imports as backup
        from .commands.compress import compress
        from .commands.translate import translate
        from .commands.session import session
        from .commands.integrate import integrate
        from .commands.demo import demo
        try:
            from .commands.claude_code import claude_code
            claude_code_available = True
        except ImportError:
            claude_code_available = False
    except ImportError as e2:
        print(f"Relative import error: {e2}")
        claude_code_available = False
    # Fallback for development/testing
    @click.command()
    def compress():
        click.echo("Compress command not available")
    
    @click.command()
    def translate():
        click.echo("Translate command not available")
    
    @click.command()
    def session():
        click.echo("Session command not available")
    
    @click.command()
    def integrate():
        click.echo("Integrate command not available")
    
    @click.command()
    def demo():
        click.echo("Demo command not available")

if not claude_code_available:
    @click.group()
    def claude_code():
        """Claude Code integration (unavailable - missing dependencies)"""
        click.echo("Claude Code integration is not available. Missing dependencies.")
        click.echo("Please check that all required modules are installed.")

__version__ = '0.1.0'  # MVP version

# Set up basic logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@click.group()
@click.version_option(__version__, message='Optimize AI CLI version %(version)s')
@click.option('--verbose', is_flag=True, help='Enable verbose logging')
def cli(verbose: bool):
    """
    Optimize AI CLI - Code compression for AI workflows.
    
    This CLI provides tools for compressing Python code, translating CAI back to Python,
    managing sessions, and integrating with agents like VSCode, Cursor, and Claude.
    """
    if verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    pass

cli.add_command(compress)
cli.add_command(translate)
cli.add_command(session)
cli.add_command(integrate)
cli.add_command(demo)
if claude_code_available:
    cli.add_command(claude_code)
else:
    cli.add_command(claude_code)  # Add the fallback version

if __name__ == '__main__':
    try:
        cli()
    except Exception as e:
        logger.error(f"CLI execution failed: {str(e)}")
        click.echo(f"Error: {str(e)}", err=True)
        exit(1)