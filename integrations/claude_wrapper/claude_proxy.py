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
from input_optimizer.engine.cai3_waterfall_integration import CAI3WaterfallEnhancement
from input_optimizer.engine.waterfall_compressor import WaterfallCompressor, count_tokens
from output_translator.core.translator import CAIToPythonTranslator
from input_optimizer.engine.cai3_translator import CAI3Translator
from input_optimizer.engine.cai3_structures import CAI3Patch, CAI3Cache
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
        # self.compressor = WaterfallCompressor(
        #     llm_model=llm_model,
        #     llm_token_limit=128000
        # )
        
        self.llm_model = llm_model
        
        # Initialize CAI3 components
        self.cai3_enhancer = CAI3WaterfallEnhancement()
        self.cai3_enhancer.include_all_methods = True  # All bodies mode for better context
        self.cai3_translator = CAI3Translator(cache_dir)
        self.cai3_cache = CAI3Cache(cache_dir) if cache_dir else CAI3Cache()
        
        self.translator = CAIToPythonTranslator()
        self.session_manager = SecureSessionManager()
        self.logger = setup_logger(__name__)
        
        # Setup cache directory
        self.cache_dir = cache_dir or Path.home() / ".optimize_ai" / "claude_cache"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        # Track current session
        self.current_session_id = None
        self.compression_metadata = {}
        self.source_path = None  # Track current file being processed
        
    def process_input(self, prompt: str, file_path: Optional[str] = None) -> Tuple[str, Dict[str, Any]]:
        """
        Process and compress input using CAI3 compression
        """
        if not self.enable_compression:
            return prompt, {"compressed": False}
        
        try:
            # Store source path for later translation
            self.source_path = Path(file_path) if file_path else None
            
            # Create session
            self.current_session_id = self.session_manager.create_session(
                file_path=self.source_path or Path("direct_input"),
                agent="claude_code",
                compressed_content="",
                metadata={"original_content": prompt}
            )
            
            # Read file content if provided
            file_content = None
            if file_path and Path(file_path).exists():
                file_content = Path(file_path).read_text()
            else:
                file_content = prompt  # Use prompt as content if no file
            
            # Count original tokens
            original_tokens = count_tokens(file_content, self.llm_model)
            
            # Use CAI3 compression
            compression_result = self.cai3_enhancer._standard_compression_cai3(
                content=file_content,
                original_tokens=original_tokens,
                source_path=self.source_path
            )
            
            # Build metadata
            metadata = {
                "compressed": True,
                "compression_type": "CAI3",
                "original_tokens": original_tokens,
                "compressed_tokens": compression_result.compressed_tokens,
                "compression_ratio": compression_result.compression_ratio,
                "tier": compression_result.tier_used.value,
                "session_id": self.current_session_id,
                "timestamp": datetime.now().isoformat(),
                "source_path": str(self.source_path) if self.source_path else None,
                "tokens_saved": original_tokens - compression_result.compressed_tokens,
                "potential_cost_savings": self._calculate_cost_savings(
                    original_tokens - compression_result.compressed_tokens
                ),
                "original_source": file_content,  # PRESERVE ORIGINAL SOURCE FOR CONTEXT VALIDATION
                "cai3_cache": True
            }
            
            # Store metadata for later use
            self.compression_metadata[self.current_session_id] = metadata
            
            # Wrap CAI3 content with instructions
            wrapped_prompt = self._wrap_cai3_prompt(
                compression_result.content,
                metadata,
                prompt
            )
            
            self.logger.info(
                f"🗜️ CAI3 Compression: {original_tokens} → {compression_result.compressed_tokens} tokens "
                f"({compression_result.compression_ratio:.1f}% reduction)"
            )
            
            return wrapped_prompt, metadata
            
        except Exception as e:
            self.logger.error(f"CAI3 compression failed: {e}")
            return prompt, {"compressed": False, "error": str(e)}

    def _wrap_cai3_prompt(self, cai3_content: str, metadata: Dict, user_prompt: str) -> str:
        """
        Wrap CAI3 content with clear instructions for Claude
        """
        return f"""[CAI3 COMPRESSED CODE - Session: {metadata['session_id']}]
    [Saved {metadata['tokens_saved']} tokens ({metadata['compression_ratio']:.1f}% reduction)]

    INSTRUCTIONS: The following code is in CAI3 ultra-dense format:
    - #C3L header indicates CAI3-LITE format
    - Single letters are method/variable compressions (see mappings)
    - FLOW syntax: L=assign, R=return, I=if, F=for, etc.
    - Pool references: p0, p1... are string constants
    - Chain aliases: g0, g1... are method chains
    - CID aliases: a0, a1... are method identifiers

    When editing, maintain CAI3 format and use #C3-PATCH format for changes:
    1:TGT:cid=<method_id> OP:RB F=B1
    B:
    <new_body_in_FLOW>
    E

    User request: {user_prompt}

    ---CAI3 CODE START---
    {cai3_content}
    ---CAI3 CODE END---"""

    def _calculate_cost_savings(self, tokens_saved: int) -> float:
        """Calculate approximate cost savings based on token reduction"""
        # Rough estimates: $0.01 per 1K tokens for GPT-4
        cost_per_1k = 0.01
        return (tokens_saved / 1000) * cost_per_1k
    
    def process_output(self, claude_output: str, metadata: Dict[str, Any]) -> str:
        """
        Enhanced output processing for both patches and full CAI3 code.
        """
        if not metadata.get("compressed", False):
            return claude_output
        
        try:
            # Check what type of CAI3 output we have
            if "#C3-PATCH" in claude_output:
                # Handle patch format
                return self._process_patch_output(claude_output, metadata)
            elif "#C3L" in claude_output or self._contains_full_cai3(claude_output):
                # Handle full CAI3-LITE output
                return self._process_full_cai3_output(claude_output, metadata)
            else:
                # No CAI3 content, return as-is
                return claude_output
                
        except Exception as e:
            self.logger.error(f"Output processing failed: {e}")
            return self._format_error_output(claude_output, e, metadata)

    def _contains_full_cai3(self, text: str) -> bool:
        """Check if output contains full CAI3-LITE format."""
        cai3_indicators = [
            'X:',  # CID aliases
            'D:',  # Chain aliases  
            'T:',  # Table section
            'B#',  # Body sections
            'C:',  # Class definitions
            'M:',  # Method definitions
            'F:'   # Function definitions
        ]
        
        # Count how many indicators are present
        indicator_count = sum(1 for indicator in cai3_indicators if indicator in text)
        return indicator_count >= 3  # Need multiple indicators for full CAI3

    def _process_full_cai3_output(self, claude_output: str, metadata: Dict) -> str:
        """Process full CAI3-LITE output from Claude."""
        self.logger.info("🔄 Processing full CAI3-LITE output...")
        
        # Extract CAI3-LITE content
        cai3_content = self._extract_cai3_content(claude_output)
        
        if not cai3_content or not self.source_path:
            return claude_output
        
        try:
            # Translate full CAI3-LITE to Python
            python_code = self.cai3_translator.translate_lite_to_python(
                cai3_lite_content=cai3_content,
                source_path=self.source_path
            )
            
            # Format the output
            return self._format_full_translation_output(
                claude_output=claude_output,
                python_code=python_code,
                metadata=metadata
            )
            
        except Exception as e:
            self.logger.error(f"Failed to translate CAI3-LITE: {e}")
            return f"⚠️ Translation failed: {e}\n\nOriginal CAI3 output:\n{claude_output}"

    def _extract_cai3_content(self, text: str) -> Optional[str]:
        """Extract CAI3 content from Claude's response."""
        import re
        
        # Try to find CAI3 block markers
        pattern = r'---CAI3.*?START---(.*?)---CAI3.*?END---'
        match = re.search(pattern, text, re.DOTALL)
        
        if match:
            return match.group(1).strip()
        
        # Try to find content after header
        if '#C3L' in text:
            # Extract everything after the header
            start_idx = text.index('#C3L')
            # Find the end (usually before explanation text)
            end_markers = ['\n\n---', '\n\nThe', '\n\nThis', '\n\nI', '\n\nNote']
            end_idx = len(text)
            for marker in end_markers:
                if marker in text[start_idx:]:
                    end_idx = text.index(marker, start_idx)
                    break
            
            return text[start_idx:end_idx].strip()
        
        return None

    def _process_patch_output(self, claude_output: str, metadata: Dict) -> str:
        """Process CAI3 patch output from Claude."""
        self.logger.info("🔄 Processing CAI3 patch...")
        
        # Extract patch content
        patch_content = self._extract_patch_content(claude_output)
        
        if not patch_content or not self.source_path:
            return claude_output
        
        try:
            # Get the original source that was used for compression (if available)
            original_source = metadata.get('original_source')
            
            if original_source:
                self.logger.debug(f"Using preserved original source for patch application:")
                self.logger.debug(f"  Length: {len(original_source)}")
                self.logger.debug(f"  Repr: {repr(original_source)}")
                self.logger.debug(f"  Lines: {original_source.count(chr(10)) + 1}")
            
            # Apply the patch using CAI3Translator.apply_patch
            if original_source:
                # Use the same source that was compressed to avoid context mismatch
                patched_code = self.cai3_translator.apply_patch(
                    patch_content=patch_content,
                    source_path=self.source_path,
                    original_source=original_source
                )
            else:
                # Fallback to reading from file
                patched_code = self.cai3_translator.apply_patch(
                    patch_content=patch_content,
                    source_path=self.source_path
                )
            
            # Format the output
            return self._format_patch_output(
                claude_output=claude_output,
                patched_code=patched_code,
                metadata=metadata
            )
            
        except Exception as e:
            self.logger.error(f"Failed to apply CAI3 patch: {e}")
            return f"⚠️ Patch application failed: {e}\n\nOriginal patch output:\n{claude_output}"

    def _extract_patch_content(self, text: str) -> Optional[str]:
        """Extract CAI3 patch content from Claude's response."""
        import re
        
        # Look for #C3-PATCH blocks
        pattern = r'#C3-PATCH\s*(.*?)(?=\n\n|\Z)'
        match = re.search(pattern, text, re.DOTALL)
        
        if match:
            return match.group(1).strip()
        
        return None

    def _format_patch_output(self, claude_output: str, patched_code: str, 
                           metadata: Dict) -> str:
        """Format output for CAI3 patch application."""
        # Extract Claude's explanation
        explanation = self._extract_explanation(claude_output)
        
        return f"""✅ CAI3 Patch Processed
    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    📊 Compression Analytics:
    • Original: {metadata['original_tokens']:,} tokens
    • Compressed: {metadata['compressed_tokens']:,} tokens
    • Net Savings: {metadata['tokens_saved']:,} tokens ({metadata['compression_ratio']:.1f}%)
    • Est. Cost Saved: ${metadata['potential_cost_savings']:.3f}

    📝 Claude's Analysis:
    {explanation}

    📄 Patched Python Code:
    ```python
    {patched_code}
    ```

    💾 Patch processed successfully
    """

    def _extract_explanation(self, claude_output: str) -> str:
        """Extract Claude's explanation from the output."""
        # Remove CAI3 code blocks and patches to get the explanation
        import re
        
        # Remove CAI3 code blocks
        text = re.sub(r'---CAI3.*?START---(.*?)---CAI3.*?END---', '', claude_output, flags=re.DOTALL)
        
        # Remove patch blocks
        text = re.sub(r'#C3-PATCH\s*(.*?)(?=\n\n|\Z)', '', text, flags=re.DOTALL)
        
        # Clean up and extract meaningful explanation
        lines = text.strip().split('\n')
        explanation_lines = []
        
        for line in lines:
            line = line.strip()
            if line and not line.startswith('#') and not line.startswith('---'):
                explanation_lines.append(line)
        
        explanation = '\n'.join(explanation_lines).strip()
        
        # If no explanation found, provide a default
        if not explanation or len(explanation) < 10:
            explanation = "Code processed successfully with CAI3 compression."
        
        return explanation

    def _format_full_translation_output(self, claude_output: str, python_code: str, 
                                    metadata: Dict) -> str:
        """Format output for full CAI3 translation."""
        # Extract Claude's explanation
        explanation = self._extract_explanation(claude_output)
        
        # Calculate effective compression
        patched_tokens = count_tokens(python_code, self.llm_model)
        
        return f"""✅ CAI3 Patch Applied
    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    📊 Compression Analytics:
    • Original: {metadata['original_tokens']:,} tokens
    • Compressed: {metadata['compressed_tokens']:,} tokens
    • Patched: {patched_tokens:,} tokens
    • Net Savings: {metadata['tokens_saved']:,} tokens ({metadata['compression_ratio']:.1f}%)
    • Est. Cost Saved: ${metadata['potential_cost_savings']:.3f}

    📝 Claude's Analysis:
    {explanation}

    📄 Patched Python Code:
    ```python
    {python_code}
    ```
    💾 Patch applied successfully
    """
    
    def _format_error_output(self, claude_output: str, error: Exception, metadata: Dict) -> str:
        """Format error output with helpful context."""
        return f"""⚠️ CAI3 Processing Error
        ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        Error: {error}
        📊 Session Info:
        • Session ID: {metadata.get('session_id', 'unknown')}
        • Compression Type: {metadata.get('compression_type', 'unknown')}
        • Source Path: {metadata.get('source_path', 'unknown')}
        💡 Suggestions:
        • Check if the CAI3 output format is valid
        • Ensure the cache files exist for this session
        • Try running with --verbose for more details
        📄 Original Claude Output:
        {claude_output[:500]}{'...' if len(claude_output) > 500 else ''}
        """

    
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