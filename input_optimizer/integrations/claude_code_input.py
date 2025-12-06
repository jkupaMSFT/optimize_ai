# ===== input_optimizer/integrations/claude_code_input.py =====
"""
Claude Code CLI integration for input compression.
Handles command-line based interactions with Claude.
"""

import asyncio
import subprocess
import json
from pathlib import Path
from typing import Dict, Any, List, Optional
import tempfile
import os
import time
import logging

from .base_integration import BaseInputIntegration
from ...core.session_manager import SessionManager
from ...core.metrics_collector import MetricsCollector
from ..engine.waterfall_compressor import WaterfallCompressor


class ClaudeCodeInputIntegration(BaseInputIntegration):
    """
    Claude Code CLI-specific input handling.
    Intercepts and modifies Claude Code commands for compression.
    """
    
    def __init__(self, session_manager: SessionManager,
                 waterfall_compressor: WaterfallCompressor,
                 metrics_collector: MetricsCollector):
        super().__init__(session_manager, waterfall_compressor, metrics_collector)
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging.INFO)
        self.agent_name = "claude_code"
        self.config = {
            "max_context_tokens": int(os.getenv("CLAUDE_MAX_CONTEXT_TOKENS", 100000)),
            "similarity_threshold": float(os.getenv("CLAUDE_SIMILARITY_THRESHOLD", 0.65)),
            "retry_attempts": int(os.getenv("CLAUDE_RETRY_ATTEMPTS", 3)),
            "retry_backoff": int(os.getenv("CLAUDE_RETRY_BACKOFF", 2)),
            "rate_limit_patterns": [
                "rate limit exceeded",
                "too many requests",
                "please try again"
            ],
            "temp_dir": Path(os.getenv("CLAUDE_TEMP_DIR", str(Path(tempfile.gettempdir()) / "optimize_ai_claude")))
        }
        self.config["temp_dir"].mkdir(exist_ok=True)
        
    async def intercept_command(self, command: List[str]) -> Dict[str, Any]:
        """
        Intercept Claude Code command and prepare compressed context.
        
        Args:
            command: Original Claude Code command parts
            
        Returns:
            Modified command info with compressed context
        """
        try:
            if not command or command[0] not in ['claude-code', 'claude']:
                return {
                    "status": "passthrough",
                    "reason": "not_claude_command",
                    "original_command": command,
                    "timestamp": time.time()
                }
                
            # Extract action and files
            action = command[1] if len(command) > 1 else None
            if action not in ['edit', 'refactor', 'review', 'explain']:
                return {
                    "status": "passthrough",
                    "reason": "unsupported_action",
                    "action": action,
                    "original_command": command,
                    "timestamp": time.time()
                }
                
            # Extract Python files and instruction
            py_files = []
            instruction = ""
            instruction_flag = False
            
            for i, arg in enumerate(command[2:], 2):
                if arg in ['--instruction', '-i']:
                    instruction_flag = True
                    continue
                    
                if instruction_flag:
                    instruction = arg
                    instruction_flag = False
                    continue
                    
                if arg.endswith('.py'):
                    file_path = Path(arg)
                    if file_path.exists() and file_path.is_file():
                        py_files.append(file_path)
                    else:
                        self.logger.warning(f"Invalid file path: {arg}")
                        
            if not py_files:
                return {
                    "status": "error",
                    "reason": "no_python_files",
                    "original_command": command,
                    "timestamp": time.time()
                }
                
            # Compress files
            compressed_context = await self._compress_files_for_claude(py_files)
            
            # Create session
            session_data = {
                "files": [str(f) for f in py_files],
                "compressed_files": compressed_context,
                "instruction": instruction,
                "action": action
            }
            
            session_id = await self.session_manager.create_session(
                file_path=py_files[0],  # Primary file
                agent=self.agent_name,
                compressed_content=json.dumps(compressed_context),
                metadata=session_data
            )
            
            # Create modified prompt
            prompt_file = await self._create_prompt_file(
                compressed_context, 
                instruction,
                action,
                session_id
            )
            
            # Build modified command
            modified_command = [
                command[0],  # claude-code
                action,
                str(prompt_file),
                '--format', 'cai',  # Signal CAI format
                '--session', session_id
            ]
            
            # Record metrics
            total_original = sum(ctx["original_tokens"] for ctx in compressed_context.values())
            total_compressed = sum(ctx["compressed_tokens"] for ctx in compressed_context.values())
            
            await self.metrics_collector.record_async("claude_command_intercepted", {
                "action": action,
                "file_count": len(py_files),
                "total_original_tokens": total_original,
                "total_compressed_tokens": total_compressed,
                "compression_ratio": (1 - total_compressed/total_original) * 100 if total_original > 0 else 0
            })
            
            self.logger.info(f"Successfully intercepted Claude command for action {action} with session {session_id}")
            
            return {
                "status": "intercepted",
                "session_id": session_id,
                "modified_command": modified_command,
                "original_command": command,
                "compressed_context": compressed_context,
                "prompt_file": str(prompt_file),
                "timestamp": time.time()
            }
            
        except Exception as e:
            self.logger.error(json.dumps({"event": "error_intercepting_command", "details": str(e), "command": command}))
            return {
                "status": "error",
                "error": str(e),
                "original_command": command,
                "timestamp": time.time()
            }
            
    async def execute_with_retry(self, command: List[str]) -> Dict[str, Any]:
        """
        Execute Claude Code command with retry logic for rate limits.
        """
        for attempt in range(self.config["retry_attempts"]):
            try:
                # Execute command
                result = await asyncio.create_subprocess_exec(
                    *command,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                
                stdout, stderr = await result.communicate()
                
                # Check for rate limit
                stderr_text = stderr.decode('utf-8', errors='ignore').lower()
                if any(pattern in stderr_text for pattern in self.config["rate_limit_patterns"]):
                    if attempt < self.config["retry_attempts"] - 1:
                        wait_time = self.config["retry_backoff"] ** attempt
                        self.logger.warning(f"Rate limit hit, waiting {wait_time}s...")
                        await asyncio.sleep(wait_time)
                        continue
                    else:
                        return {
                            "status": "rate_limited",
                            "error": "Max retries exceeded for rate limit",
                            "stderr": stderr_text,
                            "timestamp": time.time()
                        }
                        
                # Success
                self.logger.info(f"Successfully executed command after {attempt + 1} attempts")
                
                return {
                    "status": "success",
                    "stdout": stdout.decode('utf-8'),
                    "stderr": stderr.decode('utf-8'),
                    "return_code": result.returncode,
                    "attempts": attempt + 1,
                    "timestamp": time.time()
                }
                
            except Exception as e:
                if attempt < self.config["retry_attempts"] - 1:
                    wait_time = self.config["retry_backoff"] ** attempt
                    self.logger.warning(f"Execution error, retrying after {wait_time}s: {e}")
                    await asyncio.sleep(wait_time)
                    continue
                else:
                    self.logger.error(json.dumps({"event": "error_executing_command", "details": str(e), "command": command}))
                    return {
                        "status": "error",
                        "error": str(e),
                        "attempts": attempt + 1,
                        "timestamp": time.time()
                    }
                    
    async def on_file_open(self, file_path: Path) -> Dict[str, Any]:
        """Handle file open - not typically used for CLI but implemented for consistency."""
        return await self._prepare_file_context(file_path)
        
    async def on_file_change(self, file_path: Path) -> Dict[str, Any]:
        """Handle file change - not typically used for CLI but implemented for consistency."""
        return await self._prepare_file_context(file_path)
        
    async def get_compressed_context(self, session_id: str) -> str:
        """Get compressed context for a session."""
        session = self.session_manager.get_session(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")
            
        return session.compressed_content
        
    async def _compress_files_for_claude(self, files: List[Path]) -> Dict[str, Dict[str, Any]]:
        """Compress multiple files for Claude Code context."""
        compressed_context = {}
        
        # Parallel compression
        compression_tasks = []
        for file_path in files:
            compression_tasks.append(self._compress_file_safe(file_path))
            
        results = await asyncio.gather(*compression_tasks, return_exceptions=True)
        
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                self.logger.warning(f"Failed to compress {files[i]}: {result}")
                await self.metrics_collector.record_async("compression_failure", {
                    "file": str(files[i]),
                    "error": str(result)
                })
                # Include original on failure
                compressed_context[str(files[i])] = {
                    "compressed_content": files[i].read_text(encoding='utf-8'),
                    "original_tokens": 0,
                    "compressed_tokens": 0,
                    "compression_failed": True,
                    "error": str(result)
                }
            else:
                compressed_context[str(files[i])] = {
                    "compressed_content": result.content,
                    "original_tokens": result.original_tokens,
                    "compressed_tokens": result.compressed_tokens,
                    "compression_tier": result.tier_used.value,
                    "compression_ratio": result.compression_ratio
                }
                
        return compressed_context
        
    async def _create_prompt_file(self, compressed_context: Dict[str, Dict],
                                 instruction: str,
                                 action: str,
                                 session_id: str) -> Path:
        """Create temporary prompt file with compressed context."""
        prompt_content = f"""# Claude Code Request
Session: {session_id}
Action: {action}
Format: CAI (Compressed AI)

## Instructions
{instruction}

## Compression Statistics
"""
        
        total_original = 0
        total_compressed = 0
        
        for file_path, ctx in compressed_context.items():
            if not ctx.get("compression_failed"):
                total_original += ctx["original_tokens"]
                total_compressed += ctx["compressed_tokens"]
                prompt_content += f"- {Path(file_path).name}: {ctx['compression_ratio']:.1f}% reduction ({ctx['original_tokens']} → {ctx['compressed_tokens']} tokens)\n"
                
        prompt_content += f"\nTotal: {(1 - total_compressed/total_original) * 100:.1f}% reduction\n" if total_original > 0 else "\nTotal: 0% reduction (no compressible content)\n"
        
        prompt_content += """
## CAI Format Guide
- Functions: F[name(args)->body]
- Classes: C[name->methods]
- Imports: I[module1,module2]
- Variables: V[name=value]

## Compressed Files
"""
        
        for file_path, ctx in compressed_context.items():
            prompt_content += f"\n### {file_path}\n"
            prompt_content += f"Tier: {ctx.get('compression_tier', 'unknown')}\n"
            prompt_content += "```cai\n"
            prompt_content += ctx["compressed_content"]
            prompt_content += "\n```\n"
            
        # Save to temp file
        prompt_file = self.config["temp_dir"] / f"claude_prompt_{session_id}.txt"
        prompt_file.write_text(prompt_content, encoding='utf-8')
        
        return prompt_file
        
    async def _prepare_file_context(self, file_path: Path) -> Dict[str, Any]:
        """Prepare compressed context for a single file."""
        try:
            if not file_path.exists() or not file_path.is_file():
                return {
                    "status": "error",
                    "reason": "invalid_file_path",
                    "file_path": str(file_path),
                    "timestamp": time.time()
                }
            
            if file_path.suffix != '.py':
                return {
                    "status": "ignored",
                    "reason": "not_python_file",
                    "file_type": file_path.suffix,
                    "timestamp": time.time()
                }
            
            file_size = file_path.stat().st_size
            if file_size > 1_000_000:  # 1MB limit
                return {
                    "status": "error",
                    "reason": "file_too_large",
                    "size_bytes": file_size,
                    "timestamp": time.time()
                }
            
            if file_size == 0:
                result = type('CompressionResult', (), {
                    'content': '',
                    'tier_used': type('Tier', (), {'value': 'none'}),
                    'original_tokens': 0,
                    'compressed_tokens': 0,
                    'compression_ratio': 0.0
                })()
            else:
                result = await self._compress_file_safe(file_path)
            
            self.logger.info(f"Successfully prepared context for file {file_path}")
            
            return {
                "status": "ready",
                "file_path": str(file_path),
                "compressed_content": result.content,
                "compression_stats": {
                    "original_tokens": result.original_tokens,
                    "compressed_tokens": result.compressed_tokens,
                    "reduction": result.compression_ratio,
                    "tier": result.tier_used.value
                },
                "timestamp": time.time()
            }
        except FileNotFoundError as e:
            self.logger.error(json.dumps({"event": "file_not_found", "details": str(e), "file": str(file_path)}))
            return {"status": "error", "reason": "file_not_found", "error": str(e), "timestamp": time.time()}
        except PermissionError as e:
            self.logger.error(json.dumps({"event": "permission_denied", "details": str(e), "file": str(file_path)}))
            return {"status": "error", "reason": "permission_denied", "error": str(e), "timestamp": time.time()}
        except Exception as e:
            self.logger.error(json.dumps({"event": "error_preparing_context", "details": str(e), "file": str(file_path)}))
            return {
                "status": "error",
                "error": str(e),
                "file_path": str(file_path),
                "timestamp": time.time()
            }
    
    async def cleanup_temp_files(self):
        """Cleanup temporary files to prevent disk space issues."""
        current_time = time.time()
        for file in self.config["temp_dir"].iterdir():
            if file.is_file() and current_time - file.stat().st_mtime > 3600:  # 1 hour old
                try:
                    file.unlink()
                    self.logger.info(f"Cleaned up temp file: {file}")
                except Exception as e:
                    self.logger.warning(f"Failed to clean up {file}: {e}")