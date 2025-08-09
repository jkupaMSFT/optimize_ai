"""
Claude Code Proxy - Intercepts and compresses Claude Code CLI calls
Integrates with existing WaterfallCompressor and CAIToPythonTranslator
"""

import subprocess
import json
import sys
import os
import tempfile
from pathlib import Path
from typing import Dict, Tuple, Optional, Any
import logging
from datetime import datetime

# Import existing Optimize AI components
sys.path.append(str(Path(__file__).parent.parent.parent))
from input_optimizer.engine.waterfall_compressor import WaterfallCompressor, count_tokens
from output_translator.core.translator import CAIToPythonTranslator
from core.session_manager import SecureSessionManager
from utils.logger import setup_logger

class ClaudeCodeProxy:
    """
    Proxy wrapper for Claude Code CLI with CAI compression/decompression
    """
    
    def __init__(self, 
                 enable_compression: bool = True,
                 llm_model: str = "gpt-4",
                 cache_dir: Optional[Path] = None):
        """
        Initialize the Claude Code proxy
        
        Args:
            enable_compression: Whether to enable CAI compression
            llm_model: Model for token counting
            cache_dir: Directory for caching compressed results
        """
        self.enable_compression = enable_compression
        self.compressor = WaterfallCompressor(
            llm_model=llm_model,
            llm_token_limit=128000
        )
        self.translator = CAIToPythonTranslator()
        self.session_manager = SecureSessionManager()
        self.logger = setup_logger(__name__)
        
        # Setup cache directory
        self.cache_dir = cache_dir or Path.home() / ".optimize_ai" / "claude_cache"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        # Track current session
        self.current_session_id = None
        self.compression_metadata = {}
        
    def process_input(self, prompt: str, file_path: Optional[str] = None) -> Tuple[str, Dict[str, Any]]:
        """
        Process and compress input before sending to Claude
        
        Args:
            prompt: The user prompt/code to compress
            file_path: Optional path to source file
            
        Returns:
            Tuple of (processed_prompt, metadata)
        """
        if not self.enable_compression:
            return prompt, {"compressed": False}
            
        try:
            # Create session for tracking
            self.current_session_id = self.session_manager.create_session(
                file_path=Path(file_path) if file_path else Path("direct_input"),
                agent="claude_code",
                compressed_content="",  # Will be updated with compressed content
                metadata={"original_content": prompt}
            )
            
            # Compress file content separately to get better structural analysis
            file_content = None
            compression_result = None
            
            if file_path and Path(file_path).exists():
                try:
                    file_content = Path(file_path).read_text()
                    # Use proper compression dispatch instead of forcing _standard_compression
                    compression_result = self.compressor.compress_string(
                        content=file_content,
                        source_path=Path(file_path)
                    )
                except Exception as e:
                    self.logger.warning(f"Could not read file {file_path}: {e}")
            
            # If no file or compression failed, compress the prompt
            if compression_result is None:
                compression_result = self.compressor.compress_string(
                    content=prompt,
                    source_path=None
                )
            
            # Build full prompt after compression
            if file_content:
                full_prompt = f"{prompt}\n\nFile: {Path(file_path).name}\n```{Path(file_path).suffix[1:]}\n{file_content}\n```"
            else:
                full_prompt = prompt
            
            # Update session with compressed content
            self.session_manager.update_session(
                self.current_session_id,
                {
                    "compressed_content": compression_result.compressed_content,
                    "original_prompt": prompt,
                    "full_prompt": full_prompt
                }
            )
            
            # Build metadata for later decompression
            metadata = {
                "compressed": True,
                "original_tokens": compression_result.original_tokens,
                "compressed_tokens": compression_result.compressed_tokens,
                "compression_ratio": compression_result.compression_ratio,
                "tier": compression_result.tier_used.value,
                "session_id": self.current_session_id,
                "timestamp": datetime.now().isoformat(),
                "original_prompt_length": len(prompt),
                "full_prompt_length": len(full_prompt)
            }
            
            # Add instruction wrapper for Claude to understand CAI format
            wrapped_prompt = self._wrap_compressed_prompt(
                compression_result.compressed_content,
                metadata
            )
            
            # Cache the compression mapping
            self._cache_compression_data(metadata, compression_result)
            
            self.logger.info(f"Compressed {metadata['original_tokens']} → {metadata['compressed_tokens']} tokens")
            
            return wrapped_prompt, metadata
            
        except Exception as e:
            self.logger.error(f"Compression failed: {e}")
            # Fallback to original prompt
            return prompt, {"compressed": False, "error": str(e)}
    
    def _wrap_compressed_prompt(self, cai_content: str, metadata: Dict) -> str:
        """
        Wrap CAI content with instructions for Claude
        """
        return f"""[CAI COMPRESSED INPUT - Session: {metadata['session_id']}]
[Compression Ratio: {metadata['compression_ratio']:.1f}% | Tier: {metadata['tier']}]

INSTRUCTIONS: The following code is in CAI (Compressed AI) format:
- F[name(args) → {{body}}] represents functions
- C[ClassName → {{methods}}] represents classes  
- M[Class.method(args) → body] represents methods
- I[import statement] represents imports
- V[var = value] represents variables

Please understand this compressed format and respond accordingly.

---CAI CODE START---
{cai_content}
---CAI CODE END---

When providing code in your response, you may use either standard Python or CAI format.
"""
    
    def process_output(self, claude_output: str, metadata: Dict[str, Any]) -> str:
        """
        Process and decompress Claude's output
        
        Args:
            claude_output: Raw output from Claude Code
            metadata: Compression metadata from input processing
            
        Returns:
            Processed output (translated from CAI if needed)
        """
        if not metadata.get("compressed", False):
            return claude_output
            
        try:
            # Check if output contains CAI format
            if self._contains_cai_format(claude_output):
                self.logger.info("Detected CAI format in output, translating...")
                
                # Extract CAI code blocks
                cai_blocks = self._extract_cai_blocks(claude_output)
                
                for cai_code in cai_blocks:
                    # Translate each CAI block back to Python
                    translation_result = self.translator.translate(
                        session_id=metadata.get("session_id", "unknown"),
                        cai_code=cai_code,
                        original_py=None  # Claude's output is new code
                    )
                    
                    if translation_result.success:
                        # Replace CAI block with Python code
                        claude_output = claude_output.replace(
                            cai_code,
                            translation_result.python_code
                        )
                        self.logger.info(f"Successfully translated CAI block")
                    else:
                        self.logger.warning(f"Translation failed: {translation_result.error}")
            
            # Update session with results
            if metadata.get("session_id"):
                self.session_manager.update_session(
                    metadata["session_id"],
                    {"output": claude_output, "processed_at": datetime.now().isoformat()}
                )
            
            return claude_output
            
        except Exception as e:
            self.logger.error(f"Output processing failed: {e}")
            return claude_output
    
    def _contains_cai_format(self, text: str) -> bool:
        """Check if text contains CAI format patterns"""
        cai_patterns = [
            r'F\[.*?\]',  # Function pattern
            r'C\[.*?\]',  # Class pattern
            r'M\[.*?\]',  # Method pattern
            r'concept\s+\w+\s*\{',  # Concept pattern
            r'τ\s+\w+\s*\{',  # Symbol class pattern
        ]
        
        import re
        for pattern in cai_patterns:
            if re.search(pattern, text, re.DOTALL):
                return True
        return False
    
    def _extract_cai_blocks(self, text: str) -> list:
        """Extract CAI code blocks from text"""
        import re
        
        # Look for CAI code blocks between markers
        pattern = r'---CAI CODE START---(.*?)---CAI CODE END---'
        matches = re.findall(pattern, text, re.DOTALL)
        
        # Also look for standalone CAI patterns
        if not matches:
            # Extract individual CAI statements
            cai_statements = []
            patterns = [
                r'F\[.*?\]',
                r'C\[.*?\]',
                r'M\[.*?\]',
                r'I\[.*?\]',
                r'V\[.*?\]',
            ]
            for p in patterns:
                cai_statements.extend(re.findall(p, text, re.DOTALL))
            
            if cai_statements:
                matches = ['\n'.join(cai_statements)]
        
        return [m.strip() for m in matches]
    
    def _cache_compression_data(self, metadata: Dict, compression_result: Any):
        """Cache compression data for potential reuse"""
        cache_file = self.cache_dir / f"{metadata['session_id']}.json"
        cache_data = {
            "metadata": metadata,
            "compressed_content": compression_result.compressed_content,
            "tier": compression_result.tier_used.value
        }
        
        with open(cache_file, 'w') as f:
            json.dump(cache_data, f, indent=2)
    
    def execute_with_claude(self, prompt: str, file_path: Optional[str] = None) -> str:
        """
        Main execution method - compress, execute, decompress
        
        Args:
            prompt: User prompt or code
            file_path: Optional source file path
            
        Returns:
            Final processed output
        """
        # Step 1: Process and compress input
        compressed_prompt, metadata = self.process_input(prompt, file_path)
        
        # Step 2: Execute with Claude Code CLI
        try:
            self.logger.info("Executing Claude Code...")
            
            # Write to temp file if prompt is large
            if len(compressed_prompt) > 10000:
                temp_file = tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False)
                temp_file.write(compressed_prompt)
                temp_file.close()
                
                result = subprocess.run(
                    ["claude_code", f"@{temp_file.name}"],
                    capture_output=True,
                    text=True,
                    timeout=120
                )
                
                # Cleanup temp file
                Path(temp_file.name).unlink()
            else:
                result = subprocess.run(
                    ["claude_code", compressed_prompt],
                    capture_output=True,
                    text=True,
                    timeout=120
                )
            
            claude_output = result.stdout
            
            if result.returncode != 0:
                self.logger.error(f"Claude Code error: {result.stderr}")
                return f"Error: {result.stderr}"
            
        except subprocess.TimeoutExpired:
            return "Error: Claude Code execution timed out"
        except FileNotFoundError:
            return "Error: claude_code CLI not found. Please ensure Claude Code is installed."
        except Exception as e:
            return f"Error executing Claude Code: {e}"
        
        # Step 3: Process and decompress output
        final_output = self.process_output(claude_output, metadata)
        
        # Log metrics
        if metadata.get("compressed"):
            self.logger.info(
                f"Compression saved {metadata['original_tokens'] - metadata['compressed_tokens']} tokens "
                f"({metadata['compression_ratio']:.1%} reduction)"
            )
        
        return final_output