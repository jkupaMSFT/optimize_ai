# ===== cli/commands/session.py =====
import click
from pathlib import Path
import logging
import json
from core.session_manager import SecureSessionManager
from input_optimizer.engine.waterfall_compressor import WaterfallCompressor

# Set up logging
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

@click.group()
def session():
    """Session management commands."""
    pass

@session.command()
@click.argument('file_path', type=click.Path(exists=True, file_okay=True, dir_okay=False, readable=True))
@click.option('--agent', type=click.Choice(['vscode', 'cursor', 'claude'], case_sensitive=False), required=True, help='The agent type for the session')
@click.option('--metadata', type=str, help='JSON string of additional metadata')
@click.option('--verbose', is_flag=True, help='Enable verbose logging')
def start(file_path: str, agent: str, metadata: str, verbose: bool):
    """
    Start a new compression session.
    
    This command creates a new session by compressing the given Python file
    and associating it with the specified agent.
    """
    if verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    path = Path(file_path)
    
    if path.suffix != '.py':
        logger.error("File must be a Python (.py) file")
        raise click.BadArgumentUsage("File must be a Python (.py) file")
    
    try:
        compressor = WaterfallCompressor()
        compression_result = compressor.compress_file(path)
        
        session_mgr = SecureSessionManager()
        
        meta_dict = {}
        if metadata:
            meta_dict = json.loads(metadata)
        
        session_id = session_mgr.create_session(
            file_path=path,
            agent=agent,
            compressed_content=compression_result.content,
            metadata=meta_dict
        )
        
        click.echo(f"Session started: {session_id}")
        logger.info(f"Session {session_id} created for file {file_path}")
    
    except json.JSONDecodeError as e:
        logger.error(f"Invalid metadata JSON: {str(e)}")
        raise click.BadArgumentUsage("Invalid metadata JSON")
    except ValueError as e:
        logger.error(f"Invalid input: {str(e)}")
        raise click.BadArgumentUsage(str(e))
    except Exception as e:
        logger.error(f"Session creation failed: {str(e)}")
        raise click.ClickException(f"Session creation failed: {str(e)}")

@session.command()
@click.argument('session_id')
@click.option('--json-output', is_flag=True, help='Output in JSON format')
@click.option('--verbose', is_flag=True, help='Enable verbose logging')
def get(session_id: str, json_output: bool, verbose: bool):
    """
    Get session details.
    
    This command retrieves and displays details of an existing session.
    """
    if verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    try:
        session_mgr = SecureSessionManager()
        session = session_mgr.get_session(session_id)
        
        if session:
            if json_output:
                click.echo(json.dumps(session.dict, default=str, indent=2))
            else:
                click.echo(f"Session ID: {session_id}")
                click.echo(f"File Path: {session.file_path}")
                click.echo(f"Agent: {session.agent}")
                click.echo(f"Compressed Content: {session.compressed_content[:100]}...")  # Truncated for brevity
                click.echo(f"Metadata: {json.dumps(session.metadata, indent=2)}")
            logger.info(f"Retrieved session {session_id}")
        else:
            click.echo("Session not found or expired")
            logger.warning(f"Session {session_id} not found")
    
    except Exception as e:
        logger.error(f"Failed to get session: {str(e)}")
        raise click.ClickException(f"Failed to get session: {str(e)}")

@session.command()
@click.option('--verbose', is_flag=True, help='Enable verbose logging')
def list_sessions(verbose: bool):
    """
    List all active sessions.
    
    This command displays a list of all current active sessions.
    """
    if verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    try:
        session_mgr = SecureSessionManager()
        sessions = session_mgr.list_sessions()
        
        if sessions:
            for sid in sessions:
                click.echo(sid)
        else:
            click.echo("No active sessions")
        
        logger.info("Listed active sessions")
    
    except Exception as e:
        logger.error(f"Failed to list sessions: {str(e)}")
        raise click.ClickException(f"Failed to list sessions: {str(e)}")

@session.command()
@click.argument('session_id')
@click.option('--verbose', is_flag=True, help='Enable verbose logging')
def delete(session_id: str, verbose: bool):
    """
    Delete a session.
    
    This command removes the specified session if it exists.
    """
    if verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    try:
        session_mgr = SecureSessionManager()
        if session_mgr.delete_session(session_id):
            click.echo(f"Session {session_id} deleted")
            logger.info(f"Deleted session {session_id}")
        else:
            click.echo("Session not found")
            logger.warning(f"Session {session_id} not found for deletion")
    
    except Exception as e:
        logger.error(f"Failed to delete session: {str(e)}")
        raise click.ClickException(f"Failed to delete session: {str(e)}")