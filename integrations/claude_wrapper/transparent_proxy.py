#!/usr/bin/env python3
"""
Transparent Claude Proxy - Zero-configuration Claude wrapper with automatic optimization
Implements intelligent compression detection and transparent optimization.
"""

from typing import List, Optional, Dict, Any, Union, Tuple
import subprocess
import tempfile
import logging
import time
from pathlib import Path
import sys
import os

# Import existing components with robust path handling
current_dir = Path(__file__).parent
root_dir = current_dir.parent.parent
sys.path.insert(0, str(root_dir))

# Minimal compression types for self-contained operation
from enum import Enum
from dataclasses import dataclass
from typing import List, Optional, Dict, Any, Union, Tuple


class CompressionTier(Enum):
    """Compression tiers based on token count."""
    TINY = "tiny"        # <100 tokens: no compression
    SMALL = "small"      # 100-1000 tokens: light compression
    MEDIUM = "medium"    # 1000-10000 tokens: standard compression
    LARGE = "large"      # 10000-50000 tokens: chunked compression
    HUGE = "huge"        # >50000 tokens: summarization


@dataclass
class CompressionResult:
    """Result of compression."""
    original_tokens: int
    compressed_tokens: int
    compression_ratio: float
    tier_used: CompressionTier
    method_used: str
    content: str
    chunks: Optional[List[str]] = None
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


# Try to import token counting, fall back to simple approximation
try:
    # Import tiktoken directly for token counting
    import tiktoken
    
    def count_tokens(text: str, model: str = "claude-3") -> int:
        """Count tokens using tiktoken."""
        if not text:
            return 0
        try:
            # Use cl100k_base encoding (GPT-4/Claude compatible)
            encoding = tiktoken.get_encoding("cl100k_base")
            return len(encoding.encode(text))
        except Exception:
            # Fallback to character approximation
            return max(1, len(text) // 4)
            
except ImportError:
    def count_tokens(text: str, model: str = "claude-3") -> int:
        """Simple token approximation."""
        return max(1, len(text) // 4)


# Try to import the real WaterfallCompressor, fall back to simple implementation
try:
    # Try to import the full waterfall compressor
    sys.path.insert(0, str(root_dir))
    from input_optimizer.engine.waterfall_compressor import WaterfallCompressor as RealWaterfallCompressor
    
    # Use the real implementation if available
    class WaterfallCompressor(RealWaterfallCompressor):
        """Wrapper around the real WaterfallCompressor for transparent proxy."""
        pass
        
except ImportError:
    # Fall back to simple implementation if real one not available
    class WaterfallCompressor:
        """Simple fallback compressor for transparent proxy."""
        
        def __init__(self, **kwargs):
            self.llm_model = kwargs.get('llm_model', 'claude-3')
            self.llm_token_limit = kwargs.get('llm_token_limit', 100000)
            
        def compress_string(self, content: str, source_path: Optional[Path] = None) -> CompressionResult:
            """Simple but effective compression - let content determine the approach."""
            try:
                # Calculate original tokens
                original_tokens = count_tokens(content, self.llm_model)
                
                # Apply intelligent compression based on content characteristics
                # rather than arbitrary token thresholds
                compressed_content, method, actual_tier = self._smart_compress_content(content, original_tokens)
                    
                compressed_tokens = count_tokens(compressed_content, self.llm_model)
                compression_ratio = (1 - compressed_tokens / original_tokens) * 100 if original_tokens > 0 else 0
                
                return CompressionResult(
                    original_tokens=original_tokens,
                    compressed_tokens=compressed_tokens,
                    compression_ratio=compression_ratio,
                    tier_used=actual_tier,
                    method_used=method,
                    content=compressed_content
                )
                
            except Exception as e:
                # Return original content if compression fails
                original_tokens = count_tokens(content, self.llm_model)
                return CompressionResult(
                    original_tokens=original_tokens,
                    compressed_tokens=original_tokens,
                    compression_ratio=0,
                    tier_used=CompressionTier.TINY,
                    method_used="no_compression_fallback",
                    content=content,
                    metadata={'error': str(e)}
                )
        
        def _smart_compress_content(self, content: str, original_tokens: int) -> tuple:
            """
            Intelligent compression that adapts to content characteristics.
            Returns: (compressed_content, method_used, tier_used)
            """
            # For very small content, don't compress
            if original_tokens < 50 or len(content.strip()) < 200:
                return content, "no_compression", CompressionTier.TINY
            
            # Try light compression first - always safe
            light_compressed = self._light_compress(content)
            light_tokens = count_tokens(light_compressed, self.llm_model)
            light_ratio = (1 - light_tokens / original_tokens) * 100 if original_tokens > 0 else 0
            
            # If light compression achieves good results (>10% reduction), use it
            if light_ratio > 10:
                return light_compressed, "light_compression", CompressionTier.SMALL
            
            # For larger content or if light compression wasn't effective, try aggressive
            if original_tokens > 200:
                aggressive_compressed = self._aggressive_compress(content)
                aggressive_tokens = count_tokens(aggressive_compressed, self.llm_model)
                aggressive_ratio = (1 - aggressive_tokens / original_tokens) * 100 if original_tokens > 0 else 0
                
                # Use aggressive compression if it's significantly better than light
                if aggressive_ratio > light_ratio + 5:  # At least 5% better
                    tier = CompressionTier.MEDIUM if original_tokens < 2000 else CompressionTier.LARGE
                    return aggressive_compressed, "aggressive_compression", tier
            
            # Fall back to light compression or no compression
            if light_ratio > 0:
                return light_compressed, "light_compression", CompressionTier.SMALL
            else:
                return content, "no_compression", CompressionTier.TINY
        
        def _light_compress(self, content: str) -> str:
            """Light compression - remove comments and reduce whitespace."""
            lines = content.split('\n')
            compressed_lines = []
            
            for line in lines:
                stripped = line.strip()
                
                # Skip empty lines and comments
                if not stripped or stripped.startswith('#'):
                    continue
                    
                # Preserve indentation but reduce extra spaces
                indent = len(line) - len(line.lstrip())
                compressed_line = ' ' * indent + ' '.join(stripped.split())
                compressed_lines.append(compressed_line)
            
            return '\n'.join(compressed_lines)
        
        def _aggressive_compress(self, content: str) -> str:
            """More aggressive compression for larger files."""
            # First apply light compression
            light_compressed = self._light_compress(content)
            
            # Then apply additional transformations
            lines = light_compressed.split('\n')
            
            # Remove docstrings and reduce variable names
            result_lines = []
            in_docstring = False
            
            for line in lines:
                stripped = line.strip()
                
                # Skip docstrings
                if '"""' in stripped or "'''" in stripped:
                    if stripped.count('"""') % 2 == 1 or stripped.count("'''") % 2 == 1:
                        in_docstring = not in_docstring
                    continue
                    
                if in_docstring:
                    continue
                    
                # Keep only essential lines
                if stripped and not stripped.startswith('#'):
                    result_lines.append(line)
            
            return '\n'.join(result_lines)


# Error handler with minimal dependencies
class SimpleErrorHandler:
    """Simple error handler for transparent proxy."""
    
    def __init__(self):
        self.logger = logging.getLogger("SimpleErrorHandler")
        
    def handle_claude_error(self, error: Exception, command: str) -> str:
        """Handle Claude errors with simple fallback."""
        error_msg = str(error)
        
        # Return user-friendly error message
        if "not found" in error_msg.lower():
            return "Claude CLI not found. Please ensure Claude is installed and in PATH."
        elif "timeout" in error_msg.lower():
            return "Claude command timed out. Try with a smaller input or increase timeout."
        elif "permission" in error_msg.lower():
            return "Permission denied. Check file permissions and Claude configuration."
        else:
            return f"Claude execution failed: {error_msg}"


ErrorHandler = SimpleErrorHandler


class TransparentClaudeProxy:
    """
    Zero-configuration Claude wrapper with automatic optimization.
    
    Features:
    - Transparent compression for large inputs
    - Silent fallback mechanisms
    - No user-facing configuration required
    - Automatic tier selection
    - Clean output processing
    """
    
    def __init__(
        self, 
        auto_mode: bool = True,
        claude_executable: str = "claude",
        timeout: int = 120
    ):
        """
        Initialize transparent proxy with zero configuration.
        
        Args:
            auto_mode: Enable automatic optimization (default: True)
            claude_executable: Path to Claude CLI executable
            timeout: Command timeout in seconds
        """
        self.auto_mode = auto_mode
        self.claude_executable = claude_executable
        self.timeout = timeout
        
        # Initialize components
        self.compressor = WaterfallCompressor(
            llm_model="claude-3",
            llm_token_limit=100000,  # Conservative Claude limit
            chunk_size=4000
        )
        self.error_handler = ErrorHandler()
        
        # Setup logging (minimal for transparency)
        self.logger = logging.getLogger("TransparentClaudeProxy")
        self.logger.setLevel(logging.WARNING)  # Only show warnings/errors
        
        # Performance tracking (internal)
        self._stats = {
            'total_requests': 0,
            'optimized_requests': 0,
            'fallbacks': 0,
            'total_tokens_saved': 0
        }
    
    def execute(self, command: List[str]) -> str:
        """
        Transparent execution with automatic optimization.
        NO user-facing compression details.
        
        Args:
            command: Claude command arguments
            
        Returns:
            Clean Claude output with optimization artifacts removed
        """
        self._stats['total_requests'] += 1
        
        try:
            # Step 1: Detect if compression needed
            input_size = self._calculate_input_size(command)
            
            if not self.auto_mode or input_size < 1000:  # tokens
                # Direct passthrough for small inputs or manual mode
                return self._execute_claude_direct(command)
            
            # Step 2: Auto-compress with best tier
            compressed_command, metadata = self._smart_compress(command)
            
            # Step 3: Execute with fallback
            result = self._execute_with_fallback(compressed_command, command, metadata)
            
            # Step 4: Clean output (remove compression artifacts)
            clean_result = self._clean_output(result, metadata)
            
            # Track optimization success
            if metadata.get('compressed', False):
                self._stats['optimized_requests'] += 1
                tokens_saved = metadata.get('tokens_saved', 0)
                self._stats['total_tokens_saved'] += tokens_saved
            
            return clean_result
            
        except Exception as e:
            # Silent fallback to direct execution
            self._stats['fallbacks'] += 1
            return self.error_handler.handle_claude_error(e, ' '.join(command))
    
    def _calculate_input_size(self, command: List[str]) -> int:
        """
        Calculate total input size in tokens.
        
        Args:
            command: Claude command arguments
            
        Returns:
            Total token count
        """
        try:
            # Combine all command arguments
            full_input = ' '.join(command)
            
            # Check for file references (@file.py, --file file.py, etc.)
            file_content = self._extract_file_content(command)
            if file_content:
                full_input += f"\n\n{file_content}"
            
            return count_tokens(full_input, "claude-3")
            
        except Exception:
            # Conservative estimate if token counting fails
            return len(' '.join(command)) // 4
    
    def _extract_file_content(self, command: List[str]) -> str:
        """
        Extract content from file references in command.
        
        Args:
            command: Claude command arguments
            
        Returns:
            Combined file content
        """
        content_parts = []
        
        for i, arg in enumerate(command):
            try:
                # Handle @file.py syntax
                if arg.startswith('@') and len(arg) > 1:
                    file_path = Path(arg[1:])
                    if file_path.exists():
                        content = file_path.read_text(encoding='utf-8')
                        content_parts.append(content)
                
                # Handle --file file.py syntax
                elif arg in ['--file', '-f'] and i + 1 < len(command):
                    file_path = Path(command[i + 1])
                    if file_path.exists():
                        content = file_path.read_text(encoding='utf-8')
                        content_parts.append(content)
                
                # Handle direct file paths that exist
                elif Path(arg).exists() and Path(arg).suffix in ['.py', '.js', '.ts', '.txt']:
                    content = Path(arg).read_text(encoding='utf-8')
                    content_parts.append(content)
                    
            except Exception:
                # Skip files that can't be read
                continue
        
        return '\n\n---\n\n'.join(content_parts)
    
    def _smart_compress(self, command: List[str]) -> Tuple[List[str], Dict[str, Any]]:
        """
        Intelligently compress command input.
        
        Args:
            command: Original command arguments
            
        Returns:
            Tuple of (compressed_command, metadata)
        """
        try:
            # Identify compressible content
            compressible_content = []
            new_command = command.copy()
            metadata = {'compressed': False, 'tokens_saved': 0}
            
            for i, arg in enumerate(command):
                # Check for file content that should be compressed
                if arg.startswith('@') and len(arg) > 1:
                    file_path = Path(arg[1:])
                    if file_path.exists():
                        content = file_path.read_text(encoding='utf-8')
                        original_tokens = count_tokens(content, "claude-3")
                        
                        if original_tokens > 500:  # Worth compressing
                            # Compress the file content
                            result = self.compressor.compress_string(content, file_path)
                            
                            if result.compressed_tokens < original_tokens:
                                # Create temporary file with compressed content
                                temp_file = self._create_temp_file(result.content)
                                new_command[i] = f'@{temp_file}'
                                
                                metadata['compressed'] = True
                                metadata['tokens_saved'] += (original_tokens - result.compressed_tokens)
                                metadata['temp_files'] = metadata.get('temp_files', [])
                                metadata['temp_files'].append(temp_file)
            
            return new_command, metadata
            
        except Exception as e:
            # Return original command if compression fails
            self.logger.warning(f"Smart compression failed: {e}")
            return command, {'compressed': False, 'error': str(e)}
    
    def _create_temp_file(self, content: str) -> str:
        """
        Create temporary file with compressed content.
        
        Args:
            content: Content to write
            
        Returns:
            Path to temporary file
        """
        temp_file = tempfile.NamedTemporaryFile(
            mode='w',
            suffix='.cai',
            delete=False,
            encoding='utf-8'
        )
        temp_file.write(content)
        temp_file.close()
        return temp_file.name
    
    def _execute_claude_direct(self, command: List[str]) -> str:
        """
        Execute Claude command directly without optimization.
        
        Args:
            command: Claude command arguments
            
        Returns:
            Raw Claude output
        """
        try:
            result = subprocess.run(
                [self.claude_executable] + command,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                encoding='utf-8'
            )
            
            if result.returncode != 0:
                error_msg = result.stderr or "Unknown Claude error"
                raise subprocess.CalledProcessError(result.returncode, command, error_msg)
            
            return result.stdout
            
        except subprocess.TimeoutExpired:
            raise RuntimeError(f"Claude command timed out after {self.timeout} seconds")
        except FileNotFoundError:
            raise RuntimeError(f"Claude executable '{self.claude_executable}' not found")
        except Exception as e:
            raise RuntimeError(f"Claude execution failed: {e}")
    
    def _execute_with_fallback(
        self, 
        command: List[str], 
        original_command: List[str], 
        metadata: Dict[str, Any]
    ) -> str:
        """
        Execute with fallback to original command.
        
        Args:
            command: Optimized command
            original_command: Original command for fallback
            metadata: Compression metadata
            
        Returns:
            Claude output
        """
        try:
            # Try optimized command first
            result = self._execute_claude_direct(command)
            return result
            
        except Exception as e:
            # Clean up temp files before fallback
            self._cleanup_temp_files(metadata)
            
            # Log fallback reason (internal only)
            self.logger.warning(f"Optimized execution failed, falling back: {e}")
            
            # Fallback to original command
            try:
                return self._execute_claude_direct(original_command)
            except Exception as fallback_error:
                # Both attempts failed
                return self.error_handler.handle_claude_error(
                    fallback_error, 
                    ' '.join(original_command)
                )
    
    def _clean_output(self, output: str, metadata: Dict[str, Any]) -> str:
        """
        Clean Claude output by removing compression artifacts.
        
        Args:
            output: Raw Claude output
            metadata: Compression metadata
            
        Returns:
            Cleaned output
        """
        try:
            # Clean up temporary files
            self._cleanup_temp_files(metadata)
            
            # Remove compression-related artifacts from output
            cleaned = output
            
            # Remove CAI format markers if present
            cai_markers = [
                "# === CAI COMPRESSED",
                "---CAI CODE START---",
                "---CAI CODE END---",
                "[CAI COMPRESSED INPUT",
                "F[", "C[", "M[", "I[", "V[",  # CAI format patterns
            ]
            
            lines = cleaned.split('\n')
            filtered_lines = []
            
            for line in lines:
                # Skip lines containing CAI artifacts
                if any(marker in line for marker in cai_markers):
                    continue
                
                # Skip compression instruction lines
                if line.strip().startswith("INSTRUCTIONS: The following code is in CAI"):
                    continue
                
                # Skip compression metadata lines
                if line.strip().startswith("[Compression Ratio:"):
                    continue
                
                filtered_lines.append(line)
            
            # Join back and clean up excessive whitespace
            cleaned = '\n'.join(filtered_lines)
            
            # Remove multiple consecutive empty lines
            while '\n\n\n' in cleaned:
                cleaned = cleaned.replace('\n\n\n', '\n\n')
            
            return cleaned.strip()
            
        except Exception as e:
            self.logger.warning(f"Output cleaning failed: {e}")
            # Return original output if cleaning fails
            self._cleanup_temp_files(metadata)
            return output
    
    def _cleanup_temp_files(self, metadata: Dict[str, Any]) -> None:
        """
        Clean up temporary files created during compression.
        
        Args:
            metadata: Compression metadata containing temp file paths
        """
        try:
            temp_files = metadata.get('temp_files', [])
            for temp_file in temp_files:
                try:
                    Path(temp_file).unlink(missing_ok=True)
                except Exception:
                    pass  # Ignore cleanup errors
        except Exception:
            pass  # Ignore all cleanup errors
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        Get proxy performance statistics (for debugging/monitoring).
        
        Returns:
            Dictionary with performance metrics
        """
        return {
            **self._stats,
            'optimization_rate': (
                self._stats['optimized_requests'] / max(1, self._stats['total_requests'])
            ),
            'fallback_rate': (
                self._stats['fallbacks'] / max(1, self._stats['total_requests'])
            )
        }
    
    def reset_statistics(self) -> None:
        """Reset performance statistics."""
        self._stats = {
            'total_requests': 0,
            'optimized_requests': 0,
            'fallbacks': 0,
            'total_tokens_saved': 0
        }


# Convenience functions for easy integration
def create_proxy(auto_mode: bool = True, **kwargs) -> TransparentClaudeProxy:
    """
    Create a transparent Claude proxy with zero configuration.
    
    Args:
        auto_mode: Enable automatic optimization
        **kwargs: Additional proxy configuration
        
    Returns:
        Configured TransparentClaudeProxy instance
    """
    return TransparentClaudeProxy(auto_mode=auto_mode, **kwargs)


def execute_claude(command: Union[str, List[str]], **proxy_kwargs) -> str:
    """
    Execute a Claude command with automatic optimization.
    
    Args:
        command: Claude command (string or list of arguments)
        **proxy_kwargs: Additional proxy configuration
        
    Returns:
        Clean Claude output
    """
    if isinstance(command, str):
        command = command.split()
    
    proxy = create_proxy(**proxy_kwargs)
    return proxy.execute(command)


# Example usage and testing
if __name__ == "__main__":
    import sys
    
    # Simple test
    proxy = create_proxy()
    
    # Test with a simple command
    if len(sys.argv) > 1:
        # Use command line arguments
        result = proxy.execute(sys.argv[1:])
        print(result)
    else:
        # Demo usage
        test_command = ["help"]
        result = proxy.execute(test_command)
        print("Demo result:", result[:100] + "..." if len(result) > 100 else result)
        
        # Show statistics
        stats = proxy.get_statistics()
        print("\nProxy Statistics:")
        for key, value in stats.items():
            print(f"  {key}: {value}")