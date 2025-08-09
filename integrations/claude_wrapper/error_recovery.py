"""
Error Recovery Manager for Claude Code integration
"""

import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime, timedelta

class ErrorRecoveryManager:
    """
    Manages error recovery and fallback strategies for Claude Code integration
    """
    
    def __init__(self, cache_dir: Path):
        """
        Initialize the error recovery manager
        
        Args:
            cache_dir: Directory for storing recovery data
        """
        self.cache_dir = cache_dir
        self.recovery_dir = cache_dir / "recovery"
        self.recovery_dir.mkdir(parents=True, exist_ok=True)
        self.logger = logging.getLogger(__name__)
        
        # Error handling strategies
        self.strategies = {
            'compression_failed': self._handle_compression_failure,
            'translation_failed': self._handle_translation_failure,
            'claude_timeout': self._handle_claude_timeout,
            'claude_error': self._handle_claude_error,
            'session_lost': self._handle_session_lost
        }
    
    def recover_from_error(self, error_type: str, context: Dict[str, Any]) -> str:
        """
        Attempt to recover from an error
        
        Args:
            error_type: Type of error that occurred
            context: Context information for recovery
            
        Returns:
            Recovered content or fallback
        """
        try:
            if error_type in self.strategies:
                return self.strategies[error_type](context)
            else:
                self.logger.warning(f"No recovery strategy for error type: {error_type}")
                return self._fallback_recovery(context)
                
        except Exception as e:
            self.logger.error(f"Recovery failed for {error_type}: {e}")
            return self._fallback_recovery(context)
    
    def _handle_compression_failure(self, context: Dict[str, Any]) -> str:
        """Handle compression failure by returning original content"""
        self.logger.info("Recovering from compression failure - using original content")
        
        # Try to get original content from context
        original = context.get('original_prompt', '')
        if original:
            # Log the failure for analysis
            self._log_recovery_event('compression_failed', {
                'original_length': len(original),
                'context': context
            })
            return original
        
        # Try to load from session cache
        session_id = context.get('session_id')
        if session_id:
            cached_content = self._load_from_session_cache(session_id)
            if cached_content:
                return cached_content
        
        return "# Recovery Error: Could not restore original content"
    
    def _handle_translation_failure(self, context: Dict[str, Any]) -> str:
        """Handle translation failure by returning CAI content with warning"""
        self.logger.info("Recovering from translation failure - returning CAI with warning")
        
        cai_content = context.get('cai_content', '')
        warning = "# WARNING: Translation from CAI format failed\n# The following is in CAI format:\n\n"
        
        self._log_recovery_event('translation_failed', {
            'cai_length': len(cai_content),
            'context': context
        })
        
        return warning + cai_content
    
    def _handle_claude_timeout(self, context: Dict[str, Any]) -> str:
        """Handle Claude timeout by suggesting retry"""
        self.logger.info("Recovering from Claude timeout")
        
        self._log_recovery_event('claude_timeout', context)
        
        return """# Claude Code Timeout Recovery

The request to Claude Code timed out. This could be due to:
1. Large input size
2. Network issues
3. Claude service being busy

Suggestions:
- Try breaking down the input into smaller chunks
- Check your network connection
- Retry the request

Original prompt was preserved and can be reprocessed."""
    
    def _handle_claude_error(self, context: Dict[str, Any]) -> str:
        """Handle general Claude errors"""
        error_msg = context.get('error', 'Unknown error')
        self.logger.info(f"Recovering from Claude error: {error_msg}")
        
        self._log_recovery_event('claude_error', {
            'error': error_msg,
            'context': context
        })
        
        return f"""# Claude Code Error Recovery

An error occurred while processing your request:
{error_msg}

The original content has been preserved. You can:
1. Check the error message above for specific issues
2. Retry with modified input
3. Use the original content without compression

Original prompt is available for reprocessing."""
    
    def _handle_session_lost(self, context: Dict[str, Any]) -> str:
        """Handle lost session data"""
        self.logger.info("Recovering from lost session")
        
        session_id = context.get('session_id')
        if session_id:
            # Try to recover from cache
            cached_content = self._load_from_session_cache(session_id)
            if cached_content:
                self._log_recovery_event('session_recovered', context)
                return cached_content
        
        self._log_recovery_event('session_lost', context)
        
        return """# Session Recovery

Session data was lost, but recovery options are available:
1. Check recent cache files for your content
2. Review backup files if edits were being applied
3. Restart with fresh input

Session ID was: """ + context.get('session_id', 'unknown')
    
    def _fallback_recovery(self, context: Dict[str, Any]) -> str:
        """Last resort recovery strategy"""
        self.logger.info("Using fallback recovery strategy")
        
        # Try various context fields for content
        content_sources = [
            'original_prompt',
            'original_content', 
            'prompt',
            'content',
            'input'
        ]
        
        for source in content_sources:
            if source in context and context[source]:
                self._log_recovery_event('fallback_recovery', {
                    'source': source,
                    'context_keys': list(context.keys())
                })
                return str(context[source])
        
        # Ultimate fallback
        self._log_recovery_event('total_failure', context)
        return "# Total Recovery Failure\n# Could not recover any content from context"
    
    def _load_from_session_cache(self, session_id: str) -> Optional[str]:
        """Load content from session cache"""
        try:
            cache_file = self.cache_dir / f"{session_id}.json"
            if cache_file.exists():
                with open(cache_file, 'r') as f:
                    data = json.load(f)
                    return data.get('original_content', '')
        except Exception as e:
            self.logger.error(f"Failed to load session cache: {e}")
        
        return None
    
    def _log_recovery_event(self, event_type: str, data: Dict[str, Any]):
        """Log recovery events for analysis"""
        try:
            log_file = self.recovery_dir / "recovery_log.jsonl"
            
            event = {
                'timestamp': datetime.now().isoformat(),
                'event_type': event_type,
                'data': data
            }
            
            with open(log_file, 'a') as f:
                f.write(json.dumps(event) + '\n')
                
        except Exception as e:
            self.logger.error(f"Failed to log recovery event: {e}")
    
    def get_recovery_stats(self) -> Dict[str, Any]:
        """Get statistics about recovery events"""
        try:
            log_file = self.recovery_dir / "recovery_log.jsonl"
            if not log_file.exists():
                return {"total_events": 0, "events_by_type": {}}
            
            events = []
            with open(log_file, 'r') as f:
                for line in f:
                    try:
                        events.append(json.loads(line.strip()))
                    except json.JSONDecodeError:
                        continue
            
            # Calculate stats
            stats = {
                "total_events": len(events),
                "events_by_type": {},
                "recent_events": 0
            }
            
            # Count by type
            for event in events:
                event_type = event.get('event_type', 'unknown')
                stats["events_by_type"][event_type] = stats["events_by_type"].get(event_type, 0) + 1
            
            # Count recent events (last 24 hours)
            now = datetime.now()
            for event in events:
                try:
                    event_time = datetime.fromisoformat(event['timestamp'])
                    if now - event_time < timedelta(hours=24):
                        stats["recent_events"] += 1
                except (ValueError, KeyError):
                    continue
            
            return stats
            
        except Exception as e:
            self.logger.error(f"Failed to get recovery stats: {e}")
            return {"error": str(e)}
    
    def cleanup_old_logs(self, days: int = 7):
        """Clean up old recovery logs"""
        try:
            cutoff = datetime.now() - timedelta(days=days)
            log_file = self.recovery_dir / "recovery_log.jsonl"
            
            if not log_file.exists():
                return
            
            # Read and filter events
            kept_events = []
            with open(log_file, 'r') as f:
                for line in f:
                    try:
                        event = json.loads(line.strip())
                        event_time = datetime.fromisoformat(event['timestamp'])
                        if event_time > cutoff:
                            kept_events.append(event)
                    except (json.JSONDecodeError, ValueError, KeyError):
                        continue
            
            # Write back filtered events
            with open(log_file, 'w') as f:
                for event in kept_events:
                    f.write(json.dumps(event) + '\n')
            
            self.logger.info(f"Cleaned up recovery logs older than {days} days")
            
        except Exception as e:
            self.logger.error(f"Failed to cleanup recovery logs: {e}")
