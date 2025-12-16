# ===== scripts/install_integrations.py =====
import shutil
import os
from pathlib import Path
import logging
import argparse
import stat
import sys

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def parse_args() -> argparse.Namespace:
    """
    Parse command-line arguments.
    """
    parser = argparse.ArgumentParser(description="Install Optimize AI integrations.")
    parser.add_argument('--agents', nargs='+', choices=['vscode', 'cursor', 'claude', 'all'], default=['all'], help='Agents to install (default: all)')
    parser.add_argument('--verbose', action='store_true', help='Enable verbose logging')
    return parser.parse_args()

def install_integration(agent: str):
    """
    Install integration for a specific agent.
    """
    # Get source directory relative to this file
    base_dir = Path(__file__).parent.parent
    source_dir = base_dir / 'integrations' / agent
    
    if not source_dir.exists():
        logger.error(f"Source directory for {agent} not found: {source_dir}")
        raise RuntimeError(f"Integration source for {agent} not found")
    
    home = Path.home()
    
    if agent in ['vscode', 'cursor']:
        ext_base = home / ('.vscode' if agent == 'vscode' else '.cursor')
        ext_dir = ext_base / 'extensions'
        ext_dir.mkdir(parents=True, exist_ok=True)
        target_dir = ext_dir / f"optimize-ai-{agent}"
        
        # Check if exists and prompt overwrite
        if target_dir.exists():
            confirm = input(f"{target_dir} already exists. Overwrite? (y/n): ").lower()
            if confirm != 'y':
                logger.info(f"Skipping overwrite for {agent}")
                return
            shutil.rmtree(target_dir)
        
        shutil.copytree(source_dir, target_dir)
        logger.info(f"Copied integration to {target_dir}")
        
        print(f"{agent.capitalize()} integration installed at {target_dir}")
    
    elif agent == 'claude':
        bin_dir = home / '.local' / 'bin'
        bin_dir.mkdir(parents=True, exist_ok=True)
        target = bin_dir / 'claude-cai'
        
        if target.exists():
            confirm = input(f"{target} already exists. Overwrite? (y/n): ").lower()
            if confirm != 'y':
                logger.info(f"Skipping overwrite for {agent}")
                return
            target.unlink()
        
        shutil.copy(source_dir / 'claude-cai', target)
        target.chmod(stat.S_IRWXU | stat.S_IRGRP | stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH)  # 755
        logger.info(f"Copied Claude wrapper to {target}")
        
        print(f"Claude wrapper installed at {target}")
        if str(bin_dir) not in os.environ.get('PATH', ''):
            print(f"Add {bin_dir} to PATH: export PATH=\"$HOME/.local/bin:$PATH\"")

def install_all(agents: list):
    """
    Install specified or all integrations.
    """
    if 'all' in agents:
        agents = ['vscode', 'cursor', 'claude']
    
    for agent in set(agents):  # Deduplicate
        try:
            install_integration(agent)
        except Exception as e:
            logger.error(f"Failed to install {agent}: {str(e)}")
            print(f"Failed to install {agent}: {e}")

if __name__ == '__main__':
    args = parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    install_all(args.agents)