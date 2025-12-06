# ===== cli/commands/integrate.py =====
import click
import shutil
import os
from pathlib import Path
import logging
import stat

# Set up logging
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

@click.group()
def integrate():
    """Integration management commands."""
    pass

@integrate.command()
@click.argument('agent', type=click.Choice(['vscode', 'cursor', 'claude'], case_sensitive=False))
@click.option('--verbose', is_flag=True, help='Enable verbose logging')
def install(agent: str, verbose: bool):
    """
    Install integration for specific agent.
    
    This command copies the necessary files for the specified agent
    integration and sets up the environment.
    """
    if verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Get source directory relative to this file
    base_dir = Path(__file__).parent.parent.parent  # Adjust based on structure: cli/commands -> root
    source_dir = base_dir / 'integrations' / agent
    
    if not source_dir.exists():
        logger.error(f"Source directory for {agent} not found: {source_dir}")
        raise click.ClickException(f"Integration source for {agent} not found")
    
    try:
        home = Path.home()
        
        if agent in ['vscode', 'cursor']:
            ext_base = home / ('.vscode' if agent == 'vscode' else '.cursor')
            ext_dir = ext_base / 'extensions'
            ext_dir.mkdir(parents=True, exist_ok=True)
            target_dir = ext_dir / f"optimize-ai-{agent}"
            
            # Check if exists and prompt overwrite
            if target_dir.exists():
                click.confirm(f"{target_dir} already exists. Overwrite?", default=False, abort=True)
                shutil.rmtree(target_dir)
            
            shutil.copytree(source_dir, target_dir)
            logger.info(f"Copied integration to {target_dir}")
            
            # For VSCode, if using VSIX, but since local, perhaps no --install-extension needed
            # Removed os.system('code --install-extension') as it's local copy
            
            click.echo(f"{agent.capitalize()} integration installed at {target_dir}")
        
        elif agent == 'claude':
            bin_dir = home / '.local' / 'bin'  # Use .local/bin for standards
            bin_dir.mkdir(parents=True, exist_ok=True)
            target = bin_dir / 'claude-cai'
            
            if target.exists():
                click.confirm(f"{target} already exists. Overwrite?", default=False, abort=True)
                target.unlink()
            
            shutil.copy(source_dir / 'claude-cai', target)
            target.chmod(stat.S_IRWXU | stat.S_IRGRP | stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH)  # 755
            logger.info(f"Copied Claude wrapper to {target}")
            
            click.echo(f"Claude wrapper installed at {target}")
            if str(bin_dir) not in os.environ.get('PATH', ''):
                click.echo(f"Add {bin_dir} to PATH: export PATH=\"$HOME/.local/bin:$PATH\"")
    
    except PermissionError as e:
        logger.error(f"Permission denied: {str(e)}")
        raise click.ClickException("Permission denied during installation")
    except Exception as e:
        logger.error(f"Installation failed: {str(e)}")
        raise click.ClickException(f"Installation failed: {str(e)}")

@integrate.command()
@click.option('--verbose', is_flag=True, help='Enable verbose logging')
def status(verbose: bool):
    """
    Show integration status.
    
    This command checks and reports the installation status
    for all supported agents.
    """
    if verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    for agent in ['vscode', 'cursor', 'claude']:
        if agent == 'vscode':
            path = Path.home() / '.vscode' / 'extensions' / 'optimize-ai-vscode'
        elif agent == 'cursor':
            path = Path.home() / '.cursor' / 'extensions' / 'optimize-ai-cursor'
        elif agent == 'claude':
            path = Path.home() / '.local' / 'bin' / 'claude-cai'
        
        installed = path.exists()
        status = 'Installed' if installed else 'Not Installed'
        click.echo(f"{agent.capitalize()}: {status} ({path})")
        if installed:
            logger.debug(f"{agent} found at {path}")
        else:
            logger.debug(f"{agent} not found")

@integrate.command()
@click.argument('agent', type=click.Choice(['vscode', 'cursor', 'claude'], case_sensitive=False))
@click.option('--verbose', is_flag=True, help='Enable verbose logging')
def uninstall(agent: str, verbose: bool):
    """
    Uninstall integration for specific agent.
    
    This command removes the installed files for the specified agent.
    """
    if verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    try:
        home = Path.home()
        
        if agent in ['vscode', 'cursor']:
            ext_base = home / ('.vscode' if agent == 'vscode' else '.cursor')
            target_dir = ext_base / 'extensions' / f"optimize-ai-{agent}"
            
            if target_dir.exists():
                click.confirm(f"Remove {target_dir}?", default=True, abort=True)
                shutil.rmtree(target_dir)
                click.echo(f"{agent.capitalize()} integration uninstalled")
                logger.info(f"Removed {target_dir}")
            else:
                click.echo(f"{agent.capitalize()} not installed")
        
        elif agent == 'claude':
            target = home / '.local' / 'bin' / 'claude-cai'
            
            if target.exists():
                click.confirm(f"Remove {target}?", default=True, abort=True)
                target.unlink()
                click.echo("Claude wrapper uninstalled")
                logger.info(f"Removed {target}")
            else:
                click.echo("Claude wrapper not installed")
    
    except Exception as e:
        logger.error(f"Uninstallation failed: {str(e)}")
        raise click.ClickException(f"Uninstallation failed: {str(e)}")