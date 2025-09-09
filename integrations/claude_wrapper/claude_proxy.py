"""
Claude Code Proxy - Intercepts and compresses Claude Code CLI calls
Integrates with existing WaterfallCompressor and CAIToPythonTranslator
"""

import subprocess
import json
import sys
import os
import tempfile
import re
import hashlib
import traceback
from pathlib import Path
from typing import Dict, Tuple, Optional, Any, List
import logging
from datetime import datetime

# Import existing Optimize AI components
sys.path.append(str(Path(__file__).parent.parent.parent))
from input_optimizer.engine.cai3_waterfall_integration import CAI3WaterfallEnhancement
from input_optimizer.engine.waterfall_compressor import WaterfallCompressor, count_tokens
from output_translator.core.translator import CAIToPythonTranslator
from input_optimizer.engine.cai3_ast_translator import CAI3Translator
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
                 cache_dir: Optional[Path] = None,
                 enable_constraint_system: bool = True):
        """
        Initialize the Claude Code proxy
        
        Args:
            enable_compression: Whether to enable CAI compression
            llm_model: Model for token counting
            cache_dir: Directory for caching compressed results
            enable_constraint_system: Whether to enable advanced constraint-based interface
        """
        self.enable_compression = enable_compression
        # self.compressor = WaterfallCompressor(
        #     llm_model=llm_model,
        #     llm_token_limit=128000
        # )
        
        self.llm_model = llm_model
        
        # Initialize CAI3 components with consistent cache directory
        # Setup cache directory first
        self.cache_dir = cache_dir or Path.home() / ".optimize_ai" / "claude_cache"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        # Create shared CAI3 cache instance
        self.cai3_cache = CAI3Cache(self.cache_dir)
        
        # Initialize CAI3 enhancer and set its cache to use the same directory
        self.cai3_enhancer = CAI3WaterfallEnhancement()
        self.cai3_enhancer.cai3_cache = self.cai3_cache  # Use shared cache
        self.cai3_enhancer.include_all_methods = True  # All bodies mode for better context
        
        # Initialize translator with the same cache directory
        self.cai3_translator = CAI3Translator(self.cache_dir)
        
        self.translator = CAIToPythonTranslator()
        self.session_manager = SecureSessionManager()
        self.logger = setup_logger(__name__)
        
        # Initialize constraint-based CAI3 interface
        self.enable_constraint_system = enable_constraint_system
        if enable_constraint_system:
            try:
                from .claude_cai3_interface import ClaudeCAI3Interface
                self.cai3_interface = ClaudeCAI3Interface(logger=self.logger)
                self.logger.info("Constraint-based CAI3 interface enabled")
            except ImportError as e:
                self.logger.warning(f"Could not load constraint interface: {e}")
                self.cai3_interface = None
                self.enable_constraint_system = False
        else:
            self.cai3_interface = None
        
        # Track current session
        self.current_session_id = None
        self.compression_metadata = {}
        self.source_path = None  # Track current file being processed
        
    def process_input(self, prompt: str, file_path: Optional[str] = None) -> Tuple[str, Dict[str, Any]]:
        """
        Process and compress input using CAI3 compression with enhanced path tracking
        """
        if not self.enable_compression:
            return prompt, {"compressed": False}
        
        try:
            # Store source path for later translation
            self.source_path = Path(file_path) if file_path else None
            
            # Create session with enhanced metadata
            session_metadata = {
                "original_content": prompt,
                "original_source_path": str(self.source_path) if self.source_path else None
            }
            
            self.current_session_id = self.session_manager.create_session(
                file_path=self.source_path or Path("direct_input"),
                agent="claude_code",
                compressed_content="",
                metadata=session_metadata
            )
            
            # Read file content if provided
            file_content = None
            if file_path and Path(file_path).exists():
                file_content = Path(file_path).read_text()
                # Store content hash for cache matching
                import hashlib
                content_hash = hashlib.md5(file_content.encode()).hexdigest()
                session_metadata["content_hash"] = content_hash
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
            
            # Debug CAI3 compression result
            self.logger.info(f"CAI3 Debug - Original size: {len(file_content)} chars")
            self.logger.info(f"CAI3 Debug - Compressed size: {len(compression_result.content)} chars")
            self.logger.info(f"CAI3 Debug - Original tokens: {original_tokens}")
            self.logger.info(f"CAI3 Debug - Compressed tokens: {compression_result.compressed_tokens}")
            
            # Check if compression actually worked
            if compression_result.compressed_tokens >= original_tokens * 0.8:
                # Compression saved less than 20% - not worth it
                self.logger.warning(f"CAI3 compression ineffective: only {original_tokens - compression_result.compressed_tokens} tokens saved")
                return prompt, {"compressed": False, "reason": "compression_ineffective"}
            
            if len(compression_result.content) >= len(file_content) * 0.9:
                # Character compression is minimal - likely not worth wrapper overhead
                self.logger.warning(f"CAI3 character compression minimal: {len(file_content)} → {len(compression_result.content)} chars")
                return prompt, {"compressed": False, "reason": "minimal_character_reduction"}
            
            # Build initial metadata (needed for wrapper creation)
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
            
            # Create ultra-minimal wrapper and check actual token savings
            wrapped_prompt = self._wrap_cai3_prompt_concise(
                compression_result.content,
                metadata,
                prompt
            )
            
            # LOG COMPRESSION INPUT TO CLAUDE
            self.logger.info("=" * 80)
            self.logger.info("🔍 CAI3 INPUT TO CLAUDE ANALYSIS")
            self.logger.info("=" * 80)
            self.logger.info(f"📊 Original Content ({len(file_content)} chars, {original_tokens} tokens):")
            self.logger.info(f"First 500 chars: {file_content[:500]}...")
            self.logger.info("-" * 40)
            self.logger.info(f"📦 Compressed CAI3 ({len(compression_result.content)} chars, {compression_result.compressed_tokens} tokens):")
            self.logger.info(f"Full CAI3 content:\n{compression_result.content}")
            self.logger.info("-" * 40)
            self.logger.info(f"🎯 Final Wrapped Prompt ({len(wrapped_prompt)} chars):")
            self.logger.info(f"Full wrapped prompt:\n{wrapped_prompt}")
            self.logger.info("=" * 80)
            
            # Check if wrapping actually saves tokens
            wrapped_tokens = count_tokens(wrapped_prompt, self.llm_model)
            
            if wrapped_tokens >= original_tokens:
                # Compression is not beneficial - return original
                self.logger.warning(
                    f"⚠️ CAI3 wrapper overhead ({wrapped_tokens - compression_result.compressed_tokens} tokens) "
                    f"exceeds compression savings. Skipping compression."
                )
                return prompt, {"compressed": False, "reason": "wrapper_overhead_too_large"}
            
            # Update metadata with actual wrapped token count
            metadata["wrapped_tokens"] = wrapped_tokens
            metadata["net_tokens_saved"] = original_tokens - wrapped_tokens
            metadata["compression_ratio"] = ((original_tokens - wrapped_tokens) / original_tokens) * 100
            metadata["tokens_saved"] = original_tokens - wrapped_tokens  # Use actual wrapped savings
            metadata["potential_cost_savings"] = self._calculate_cost_savings(
                original_tokens - wrapped_tokens  # Use actual wrapped savings
            )
            
            # Store metadata for later use
            self.compression_metadata[self.current_session_id] = metadata
            
            self.logger.info(
                f"🗜️ CAI3 Compression: {original_tokens} → {wrapped_tokens} tokens "
                f"({metadata['compression_ratio']:.1f}% net reduction after wrapper)"
            )
            
            return wrapped_prompt, metadata
            
        except Exception as e:
            self.logger.error(f"CAI3 compression failed: {e}")
            return prompt, {"compressed": False, "error": str(e)}

    def _wrap_cai3_prompt_concise(self, cai3_content: str, metadata: Dict, user_prompt: str) -> str:
        """
        Ultra-strict CAI3 wrapper with explicit syntax validation and examples.
        Uses constraint-based prompting when constraint system is enabled.
        """
        # Extract just the user's prompt part (before the file content)
        if "\n\n```python\n" in user_prompt:
            actual_user_prompt = user_prompt.split("\n\n```python\n")[0].strip()
        else:
            actual_user_prompt = user_prompt.strip()
        
        # Check if constraint system is enabled and use constraint-based prompting
        if self.enable_constraint_system and self.cai3_interface:
            self.logger.info("🔧 Using constraint-based CAI3 prompting")
            
            # Use the constraint interface to create a properly constrained prompt
            try:
                # Load CAI3Full from cache for constraints
                cai3_full = None
                if self.source_path:
                    cai3_full = self.cai3_cache.load_full(self.source_path)
                
                # Create constraint-based prompt using the interface
                constrained_prompt = self.cai3_interface._create_constrained_prompt(
                    cai3_lite=cai3_content,
                    task=actual_user_prompt,
                    cai3_full=cai3_full
                )
                
                self.logger.debug(f"Generated constraint-based prompt ({len(constrained_prompt)} chars)")
                return constrained_prompt
                
            except Exception as e:
                self.logger.warning(f"Failed to create constraint-based prompt: {e}, falling back to standard wrapper")
                # Fall through to standard wrapper
        
        # Standard CAI3 wrapper (fallback or when constraints disabled)
        self.logger.info("🔧 Using standard CAI3 prompting")
        
        # Ultra-strict syntax validation with examples
        syntax_instructions = """
🚨 ULTRA-CRITICAL CAI3-LITE SYNTAX RULES 🚨

MANDATORY BRACKET VALIDATION:
1. Count { braces: opening = closing (EXACT MATCH REQUIRED)
2. Count ( parentheses: opening = closing (EXACT MATCH REQUIRED)  
3. Count [ brackets: opening = closing (EXACT MATCH REQUIRED)

REQUIRED SECTIONS (MUST BE COMPLETE):
- P: section with ALL pool definitions (p0="value",p1="value",...)
- X: section with all aliases (a0=code,a1=code,...)
- D: section with dependencies
- T: section with table structure
- B#cid: body sections (complete, no truncation)

FORBIDDEN ELEMENTS:
❌ ABSOLUTELY NO parentheticals: "(was B#a0)", "(originally...)", "(was p0)", etc.
❌ NO annotations or explanations of any kind
❌ NO humanization or clarification text
❌ NO comments or explanations outside ```C3L block
❌ NO truncation markers: "...", "p5..."
❌ NO malformed structures

CRITICAL INSTRUCTION: 
The CAI3 code you receive is ALREADY CORRECT. Do NOT add any "(was ...)" annotations, explanations, or modifications to it. Return the corrected CAI3 code with fixes applied but NO additional annotations.

VALIDATION CHECKLIST BEFORE OUTPUT:
□ All { have matching }
□ All ( have matching )
□ All [ have matching ]
□ All p0,p1,etc have P: definitions
□ NO "(was ...)" text anywhere
□ NO explanatory annotations
□ Exactly one ```C3L block
□ Complete body sections

OUTPUT RULE: Generate EXACTLY ONE ```C3L code block with fixes applied. NO ANNOTATIONS. NO EXPLANATIONS.

"""
        
        # Format CAI3 content in proper fenced code block for compliance
        return f"{actual_user_prompt}\n{syntax_instructions}\n```cai3\n{cai3_content}\n```"

    def _wrap_cai3_prompt(self, cai3_content: str, metadata: Dict, user_prompt: str) -> str:
        """
        Wrap CAI3 content with comprehensive syntax validation instructions for Claude.
        """
        
        # Enhanced instructions for proper CAI3-LITE syntax
        syntax_rules = """
🔧 CAI3-LITE SYNTAX REQUIREMENTS (CRITICAL):

1. BRACKET BALANCE VALIDATION:
   - Count opening braces { and ensure equal closing braces }
   - Count opening parentheses ( and ensure equal closing parentheses )
   - Count opening brackets [ and ensure equal closing brackets ]
   - Validate T{} try blocks have matching X{} exception handlers

2. REQUIRED SECTIONS:
   - P: section MUST define ALL referenced pools (p0, p1, p2, etc.)
   - Every #pN reference in code must have P:pN="value" definition
   - X: section for CID aliases (a0, a1, b0, etc.)
   - D: section for chain aliases
   - T: section for table structure

3. SYNTAX COMPLIANCE:
   - Use EXACTLY ONE ```C3L code block
   - NO explanatory text, comments, or prose outside the code block
   - NO parentheticals like "(was B#a0)" or "(originally...)"
   - NO truncation markers like "..." anywhere
   - Body lines MUST be complete: B#cid:complete_body_content

4. BODY STRUCTURE VALIDATION:
   - If using T{}, ensure it ends with }X{exception_handler}
   - Check that all conditional expressions have balanced operators
   - Verify method calls have proper parameter lists

"""
        
        return f"""[CAI3 COMPRESSED CODE - Session: {metadata['session_id']}]
[Saved {metadata['tokens_saved']} tokens ({metadata['compression_ratio']:.1f}% reduction)]

{syntax_rules}

TASK: {user_prompt}

IMPORTANT: Before outputting, mentally verify:
- All {{}} braces are balanced
- All () parentheses are balanced  
- All [] brackets are balanced
- All pools referenced are defined
- Output is exactly one ```C3L block

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
        Enhanced output processing with robust error recovery and retry logic.
        """
        # CRITICAL: Skip humanization to prevent CAI3lite corruption
        # claude_output = self._strip_humanization_annotations(claude_output)
        
        # LOG RAW CLAUDE OUTPUT FIRST
        self.logger.info("=" * 80)
        self.logger.info("🔍 RAW CLAUDE OUTPUT ANALYSIS")
        self.logger.info("=" * 80)
        self.logger.info(f"📊 Claude Output ({len(claude_output)} chars):")
        self.logger.info(f"Full Claude response:\n{claude_output}")
        self.logger.info("-" * 40)
        
        # Analyze CAI3 structure in raw output
        code_blocks = re.findall(r'```(\w+)?\n(.*?)\n```', claude_output, re.DOTALL)
        self.logger.info(f"🔍 Code blocks found: {len(code_blocks)}")
        for i, (lang, content) in enumerate(code_blocks):
            self.logger.info(f"Block {i+1}: Language='{lang}', Content length={len(content)}")
            if len(content) < 1000:
                self.logger.info(f"Block {i+1} content:\n{content}")
            else:
                self.logger.info(f"Block {i+1} content (first 500 chars):\n{content[:500]}...")
        
        # Check for CAI3 patterns
        cai3_patterns = ['#C3L', 'X:', 'D:', 'T:', 'B#', 'P:']
        found_patterns = [pattern for pattern in cai3_patterns if pattern in claude_output]
        self.logger.info(f"🔍 CAI3 patterns found: {found_patterns}")
        
        # Check bracket balance in raw output
        if found_patterns:
            open_braces = claude_output.count('{')
            close_braces = claude_output.count('}')
            open_parens = claude_output.count('(')
            close_parens = claude_output.count(')')
            open_brackets = claude_output.count('[')
            close_brackets = claude_output.count(']')
            
            self.logger.info(f"🔍 Bracket analysis in raw output:")
            self.logger.info(f"  Braces: {open_braces} open, {close_braces} close (balanced: {open_braces == close_braces})")
            self.logger.info(f"  Parentheses: {open_parens} open, {close_parens} close (balanced: {open_parens == close_parens})")
            self.logger.info(f"  Brackets: {open_brackets} open, {close_brackets} close (balanced: {open_brackets == close_brackets})")
        
        self.logger.info("=" * 80)
        
        if not metadata.get("compressed", False):
            return claude_output
        
        max_translation_retries = 3
        
        for attempt in range(max_translation_retries):
            try:
                # Skip humanization - user only needs final Python output
                # Humanization adds forbidden parentheticals that break CAI3 compliance
                raw_output = claude_output
                
                # Log what we're processing
                self.logger.debug(f"Processing output ({len(claude_output)} chars). Contains CAI3 patterns: {self._contains_full_cai3(raw_output)}")
                
                # Check what type of CAI3 output we have
                if "#C3-PATCH" in raw_output:
                    # Handle patch format
                    self.logger.info("Detected CAI3 patch format")
                    return self._process_patch_output_with_retry(raw_output, metadata, attempt)
                elif "#C3L" in raw_output or self._contains_full_cai3(raw_output):
                    # Handle full CAI3-LITE output
                    self.logger.info(f"Detected full CAI3-LITE format (attempt {attempt + 1}/{max_translation_retries})")
                    
                    # Skip legacy validation if constraint system is enabled
                    if self.enable_constraint_system and self.cai3_interface:
                        self.logger.info("🔧 Using constraint-based validation - skipping legacy CAI3 compliance checks")
                        # Constraint system has already validated the output, proceed directly to processing
                        return self._process_full_cai3_output_with_retry(raw_output, metadata, attempt)
                    
                    # Legacy validation for when constraint system is disabled
                    # Validate CAI3 compliance before translation
                    is_compliant, compliance_result = self._validate_cai3_compliance(raw_output)
                    
                    # LOG COMPLIANCE VALIDATION RESULTS
                    self.logger.info("-" * 40)
                    self.logger.info("🔍 CAI3 COMPLIANCE VALIDATION")
                    self.logger.info("-" * 40)
                    self.logger.info(f"✅ Compliant: {is_compliant}")
                    if not is_compliant:
                        self.logger.info(f"❌ Issues found: {compliance_result.get('issues', [])}")
                        self.logger.info(f"🔍 Missing pools: {compliance_result.get('missing_pools', [])}")
                    self.logger.info("-" * 40)
                    
                    if not is_compliant:
                        self.logger.warning(f"CAI3-LITE compliance failed: {compliance_result['issues']}")
                        
                        # Enhanced repair with bracket validation
                        self.logger.info("🔧 STARTING CAI3 REPAIR PROCESS")
                        self.logger.info(f"Pre-repair content:\n{raw_output}")
                        
                        repaired_output = self._comprehensive_cai3_repair(raw_output, metadata)
                        
                        self.logger.info("🔧 REPAIR COMPLETED")
                        self.logger.info(f"Post-repair content:\n{repaired_output}")
                        self.logger.info(f"Changes made: {len(repaired_output) - len(raw_output)} characters")
                        
                        # Re-validate after repair
                        is_compliant, validation_result = self._validate_cai3_compliance(repaired_output)
                        self.logger.info(f"🔍 Post-repair compliance: {is_compliant}")
                        if not is_compliant:
                            self.logger.warning(f"❌ Still has issues: {validation_result.get('issues', [])}")
                        
                        if is_compliant:
                            self.logger.info("CAI3-LITE format successfully repaired")
                            raw_output = repaired_output
                        else:
                            self.logger.warning("CAI3-LITE repair failed, attempting fallback")
                            return self._extract_python_code_directly(raw_output, metadata)
                    else:
                        # Even if compliant, run bracket validation as extra safety
                        validated_output = self._validate_bracket_balance(raw_output)
                        if validated_output != raw_output:
                            self.logger.info("Applied bracket balance corrections")
                            raw_output = validated_output
                    
                    return self._process_full_cai3_output_with_retry(raw_output, metadata, attempt)
                else:
                    # No CAI3 content, but compression was used - this might be direct Python
                    self.logger.info("No CAI3 format detected but compression was used, checking for direct Python")
                    python_extracted = self._extract_python_code_directly(raw_output, metadata)
                    if "Python Code Extracted" in python_extracted:
                        return python_extracted
                    else:
                        # Return raw version
                        return raw_output
                        
            except ValueError as e:
                if "No CAI3 cache found" in str(e) and attempt < max_translation_retries - 1:
                    self.logger.warning(f"CAI3 cache miss on attempt {attempt + 1}, trying cache recovery...")
                    # Try to recover cache using alternative path strategies
                    if self._attempt_cache_recovery(metadata):
                        continue  # Retry with recovered cache
                    else:
                        # Try alternative translation strategies
                        self.logger.info(f"Cache recovery failed, attempting direct code extraction...")
                        return self._extract_python_code_directly(claude_output, metadata)
                else:
                    # Final attempt or non-cache error
                    self.logger.error(f"Translation attempt {attempt + 1} failed: {e}")
                    if attempt == max_translation_retries - 1:
                        return self._extract_python_code_directly(claude_output, metadata)
                    
            except Exception as e:
                self.logger.error(f"Output processing failed on attempt {attempt + 1}: {e}")
                if attempt == max_translation_retries - 1:
                    return self._format_error_output(claude_output, e, metadata)
        
        # Should never reach here, but safety fallback
        return self._extract_python_code_directly(claude_output, metadata)

    def _attempt_cache_recovery(self, metadata: Dict[str, Any]) -> bool:
        """
        Attempt to recover CAI3 cache using alternative path strategies.
        Returns True if cache recovery succeeded, False otherwise.
        """
        try:
            if not self.source_path:
                return False
            
            # Strategy 1: Try alternative cache keys based on file content hash
            import hashlib
            if self.source_path.exists():
                content_hash = hashlib.md5(self.source_path.read_bytes()).hexdigest()[:12]
                # Try to find cache files with this content hash
                cache_dir = Path(".cai3_cache")
                if cache_dir.exists():
                    # Look for any cache files that might match this content
                    for cache_file in cache_dir.glob(f"*_full.json"):
                        try:
                            cache_data = json.loads(cache_file.read_text())
                            if cache_data.get('file_hash') == content_hash:
                                self.logger.info(f"Found matching cache by content hash: {cache_file}")
                                # Create symbolic links with the expected cache key
                                expected_key = self.cai3_cache.get_cache_key(self.source_path)
                                expected_full = cache_dir / f"{expected_key}_full.json"
                                expected_map = cache_dir / f"{expected_key}_map.json"
                                
                                if not expected_full.exists():
                                    expected_full.symlink_to(cache_file)
                                map_file = cache_dir / cache_file.name.replace('_full.json', '_map.json')
                                if map_file.exists() and not expected_map.exists():
                                    expected_map.symlink_to(map_file)
                                    
                                return True
                        except (json.JSONDecodeError, KeyError):
                            continue
            
            # Strategy 2: Check if there's a recent cache file for similar paths
            if hasattr(metadata, 'original_source_path'):
                original_path = Path(metadata['original_source_path'])
                if original_path != self.source_path:
                    # Try using the original path for cache lookup
                    original_full = self.cai3_cache.load_full(original_path)
                    original_map = self.cai3_cache.load_map(original_path)
                    if original_full and original_map:
                        # Copy cache to current path
                        self.cai3_cache.store_full(self.source_path, original_full)
                        self.cai3_cache.store_map(self.source_path, original_map)
                        self.logger.info(f"Recovered cache from original path: {original_path}")
                        return True
            
            # Strategy 3: Try to find the most recent cache file and use it
            cache_dir = Path(".cai3_cache")
            if cache_dir.exists():
                cache_files = list(cache_dir.glob("*_full.json"))
                if cache_files:
                    # Sort by modification time and try the most recent
                    latest_cache = max(cache_files, key=lambda f: f.stat().st_mtime)
                    try:
                        cache_data = json.loads(latest_cache.read_text())
                        # Create CAI3Full from the cache data
                        from input_optimizer.engine.cai3_structures import CAI3Full
                        recovered_full = CAI3Full.from_json(latest_cache.read_text())
                        
                        # Try to load corresponding map
                        map_file = cache_dir / latest_cache.name.replace('_full.json', '_map.json')
                        if map_file.exists():
                            from input_optimizer.engine.cai3_structures import CAI3Map
                            recovered_map = CAI3Map.from_json(map_file.read_text())
                            
                            # Store under current path
                            self.cai3_cache.store_full(self.source_path, recovered_full)
                            self.cai3_cache.store_map(self.source_path, recovered_map)
                            self.logger.info(f"Recovered cache from latest file: {latest_cache}")
                            return True
                    except Exception as e:
                        self.logger.debug(f"Failed to recover from {latest_cache}: {e}")
            
            return False
            
        except Exception as e:
            self.logger.error(f"Cache recovery failed: {e}")
            return False

    def _process_full_cai3_output_with_retry(self, humanized_output: str, metadata: Dict[str, Any], attempt: int) -> str:
        """Process full CAI3 output with retry logic for cache issues."""
        try:
            return self._process_full_cai3_output(humanized_output, metadata)
        except ValueError as e:
            if "No CAI3 cache found" in str(e):
                self.logger.warning(f"CAI3 cache not found on attempt {attempt + 1}, falling back to direct extraction")
                return self._extract_python_code_directly(humanized_output, metadata)
            else:
                raise

    def _process_patch_output_with_retry(self, humanized_output: str, metadata: Dict[str, Any], attempt: int) -> str:
        """Process patch output with retry logic for cache issues."""
        try:
            return self._process_patch_output(humanized_output, metadata)
        except ValueError as e:
            if "No CAI3 cache found" in str(e):
                self.logger.warning(f"CAI3 cache not found for patch on attempt {attempt + 1}, returning raw output")
                return humanized_output
            else:
                raise

    def _repair_cai3_format(self, malformed_response: str, original_prompt: str = "", 
                            max_retries: int = 2, verbose: bool = False) -> str:
        """Attempt to repair malformed CAI3-LITE response."""
        
        # If no original_prompt provided, use existing simple repair
        if not original_prompt:
            return self._simple_repair_cai3_format(malformed_response)
        
        for retry_num in range(max_retries):
            # Validate current response
            is_valid, validation_info = self._validate_cai3_compliance(malformed_response)
            
            if is_valid:
                return malformed_response
            
            # Build repair prompt
            issues_text = '\n'.join(f"- {issue}" for issue in validation_info['issues'])
            missing_pools = validation_info.get('missing_pools', [])
            
            repair_prompt = f"""Your output violated the contract:
{issues_text}

Re-emit the ENTIRE program as exactly one ```C3L``` block, no prose.
"""
            
            if missing_pools:
                repair_prompt += f"Define these pools in P: section: {', '.join(missing_pools)}\n"
            
            repair_prompt += "Do not include any parentheticals or explanations."
            
            if verbose:
                self.logger.info(f"Repair attempt {retry_num + 1}/{max_retries}")
                self.logger.debug(f"Repair prompt: {repair_prompt}")
            
            # Execute repair (simplified - would use actual Claude API)
            repaired_response = self._execute_claude_repair(repair_prompt, malformed_response)
            
            if repaired_response:
                malformed_response = repaired_response
            else:
                break
        
        # After max retries, request Python fallback
        if verbose:
            self.logger.warning(f"CAI3 repair failed after {max_retries} attempts, requesting Python")
        
        fallback_prompt = """Cannot produce valid CAI3-LITE. 
Return exactly one ```python``` block with the corrected program. No prose."""
        
        return self._execute_python_fallback(original_prompt, fallback_prompt)

    def _simple_repair_cai3_format(self, output: str) -> str:
        """Enhanced CAI3 format repair with comprehensive validation and repair."""
        import re
        
        self.logger.info("Attempting comprehensive CAI3 format repair")
        
        # Extract the code block content
        code_blocks = re.findall(r'```(\w+)?\n(.*?)\n```', output, re.DOTALL)
        if not code_blocks:
            # No code blocks found, try to repair the entire output
            content = output
            lang = 'C3L'
        else:
            lang, content = code_blocks[0]
        
        # Use comprehensive validator to repair the content
        is_valid, repaired_content, issues = self._validate_and_repair_cai3_content(content)
        
        if issues:
            self.logger.info(f"Applied {len(issues)} CAI3 repairs: {', '.join(issues)}")
        
        # Fix language tag
        if lang not in ['C3L', 'CAI3', 'cai3']:
            lang = 'C3L'
        
        # Reconstruct the output
        repaired = f"```{lang}\n{repaired_content}\n```"
        
        self.logger.info("CAI3 format repair completed")
        return repaired
    
    def _validate_and_repair_cai3_content(self, content: str) -> tuple:
        """Validate and repair CAI3-LITE content using comprehensive repair logic."""
        issues = []
        repaired_content = content
        
        # 1. Fix missing header
        if not repaired_content.strip().startswith('#C3L'):
            if 'C3L' in repaired_content[:50]:
                repaired_content = '#C3L\n' + repaired_content
                issues.append("Added missing #C3L header")
            else:
                repaired_content = '#C3L cai3_output\n' + repaired_content
                issues.append("Added CAI3-LITE header")
        
        # 2. Fix unbalanced brackets
        repaired_content, bracket_issues = self._repair_bracket_structures(repaired_content)
        issues.extend(bracket_issues)
        
        # 3. Fix missing pool definitions
        repaired_content, pool_issues = self._repair_missing_pool_definitions(repaired_content)
        issues.extend(pool_issues)
        
        # 4. Remove forbidden commentary and parentheticals
        repaired_content, comment_issues = self._remove_forbidden_commentary(repaired_content)
        issues.extend(comment_issues)
        
        # 5. Fix section structure issues
        repaired_content, section_issues = self._repair_section_structures(repaired_content)
        issues.extend(section_issues)
        
        is_valid = len(issues) == 0 or all('Added' in issue or 'Fixed' in issue or 'Repaired' in issue for issue in issues)
        
        return is_valid, repaired_content, issues
    
    def _repair_bracket_structures(self, content: str) -> tuple:
        """Repair unbalanced bracket structures in CAI3 content."""
        issues = []
        lines = content.split('\n')
        repaired_lines = []
        
        for i, line in enumerate(lines):
            original_line = line
            
            # Fix T{} structures without proper exception handlers
            if line.startswith('B#') and 'T{' in line:
                line = self._repair_try_structure_in_line(line)
                if line != original_line:
                    issues.append(f"Repaired T{{}} structure in body line {i+1}")
            
            # Fix general bracket imbalances
            line = self._balance_brackets_in_line(line)
            if line != original_line:
                issues.append(f"Balanced brackets in line {i+1}")
            
            repaired_lines.append(line)
        
        return '\n'.join(repaired_lines), issues
    
    def _repair_try_structure_in_line(self, line: str) -> str:
        """Repair incomplete T{} try-except structures in a line."""
        if 'T{' not in line:
            return line
        
        # Count braces in the line
        open_braces = line.count('{')
        close_braces = line.count('}')
        
        # If unbalanced, try to repair
        if open_braces > close_braces:
            missing = open_braces - close_braces
            
            # Check if there's an exception handler pattern
            if 'X{' not in line:
                # Add exception handler with proper closing
                line += '}' * (missing - 1) + 'X{_}'
            else:
                # Just add missing closing braces
                line += '}' * missing
        
        return line
    
    def _balance_brackets_in_line(self, line: str) -> str:
        """Balance brackets in a single line."""
        # Track bracket counts
        brackets = {'(': 0, '[': 0, '{': 0}
        bracket_pairs = {'(': ')', '[': ']', '{': '}'}
        
        for char in line:
            if char in brackets:
                brackets[char] += 1
            elif char in bracket_pairs.values():
                # Find the corresponding opening bracket
                for open_bracket, close_bracket in bracket_pairs.items():
                    if char == close_bracket and brackets[open_bracket] > 0:
                        brackets[open_bracket] -= 1
                        break
        
        # Add missing closing brackets
        for open_bracket, count in brackets.items():
            if count > 0:
                line += bracket_pairs[open_bracket] * count
        
        return line
    
    def _repair_missing_pool_definitions(self, content: str) -> tuple:
        """Add missing pool definitions to CAI3 content."""
        import re
        issues = []
        
        # Check if P: section exists
        if 'P:' not in content:
            # Find pool references (p0, p1, etc.)
            pool_refs = set(re.findall(r'#([p][0-9]+)', content))
            
            if pool_refs:
                # Create pool definitions
                pool_definitions = []
                for i, ref in enumerate(sorted(pool_refs)):
                    pool_definitions.append(f'{ref}="placeholder_{i}"')
                
                pool_section = 'P:' + ','.join(pool_definitions)
                
                # Insert pool section after header
                lines = content.split('\n')
                if lines and lines[0].startswith('#C3L'):
                    lines.insert(1, pool_section)
                else:
                    lines.insert(0, pool_section)
                
                content = '\n'.join(lines)
                issues.append(f"Added missing pool definitions: {', '.join(pool_refs)}")
        
        return content, issues
    
    def _remove_forbidden_commentary(self, content: str) -> tuple:
        """Remove forbidden commentary and parentheticals from CAI3 content."""
        import re
        issues = []
        original_content = content
        
        # Remove inline comments that aren't part of the CAI3 syntax
        content = re.sub(r'```C3L\s*', '', content)
        content = re.sub(r'```\s*$', '', content, flags=re.MULTILINE)
        
        # Remove explanatory parentheticals that aren't valid CAI3 syntax
        content = re.sub(r'\([^)]*\)\s*(?=[A-Z]:)', '', content)
        
        # Remove parentheticals like "(was B#a0)"
        content = re.sub(r'\(was [^)]+\)', '', content)
        
        # Remove ellipsis patterns
        content = re.sub(r'\.\.\.', '', content)
        
        if content != original_content:
            issues.append("Removed forbidden commentary and truncation markers")
        
        return content, issues
    
    def _repair_section_structures(self, content: str) -> tuple:
        """Repair section structure issues in CAI3 content."""
        issues = []
        lines = content.split('\n')
        repaired_lines = []
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # Fix malformed section headers
            if ':' in line and not line.startswith('#'):
                # Check for valid section prefixes
                valid_sections = ['D:', 'X:', 'P:', 'T:', 'B#']
                section_prefix = line.split(':')[0] + ':'
                
                if section_prefix not in valid_sections and not line.startswith('B#'):
                    # Try to fix common issues
                    if line.startswith('M '):
                        # Method line without proper B# prefix - convert to table entry
                        line = 'T:' + line
                        issues.append("Fixed malformed method line")
                    elif '=' in line and not line.startswith('P:'):
                        # Assignment without proper section - convert to pool definition
                        line = 'P:' + line
                        issues.append("Fixed malformed assignment")
            
            repaired_lines.append(line)
        
        return '\n'.join(repaired_lines), issues

    def _execute_claude_repair(self, repair_prompt: str, malformed_response: str) -> Optional[str]:
        """Execute Claude API call for repair (placeholder implementation)."""
        # This would be implemented with actual Claude API calls
        # For now, return a basic repair attempt
        self.logger.info("Executing Claude repair (placeholder implementation)")
        
        # Try basic format cleaning
        import re
        
        # Extract code blocks
        code_blocks = re.findall(r'```(\w+)?\n(.*?)\n```', malformed_response, re.DOTALL)
        if code_blocks:
            lang, content = code_blocks[0]
            
            # Fix language tag
            if lang not in ['C3L', 'CAI3', 'cai3']:
                lang = 'C3L'
            
            # Remove problematic patterns
            content = re.sub(r'\(was [^)]+\)', '', content)
            content = re.sub(r'\.\.\.', '', content)
            
            # Clean up whitespace
            content = '\n'.join(line.strip() for line in content.split('\n') if line.strip())
            
            return f"```{lang}\n{content}\n```"
        
        return None

    def _execute_python_fallback(self, original_prompt: str, fallback_prompt: str) -> str:
        """Execute Python fallback when CAI3 repair fails."""
        self.logger.warning("Executing Python fallback due to CAI3 repair failure")
        
        # This would ideally call Claude API for Python generation
        # For now, return a placeholder response
        return f"""⚠️ CAI3 repair failed after maximum retries. Fallback to Python requested.

Original prompt: {original_prompt[:200]}...

```python
# Placeholder: CAI3 repair failed
# Manual intervention required
pass
```

Please manually review and correct the code."""

    def _validate_cai3_compliance(self, response: str) -> Tuple[bool, Dict[str, Any]]:
        """Validate CAI3-LITE response compliance before translation."""
        import re
        
        issues = []
        
        # Check for single fenced block
        code_blocks = re.findall(r'```(\w+)?\n(.*?)\n```', response, re.DOTALL)
        if len(code_blocks) != 1:
            issues.append(f"Expected 1 code block, found {len(code_blocks)}")
            return False, {"valid": False, "issues": issues}
        
        lang, content = code_blocks[0]
        
        # Check language tag
        if lang not in ['C3L', 'CAI3', 'cai3']:
            issues.append(f"Wrong language tag: {lang}")
        
        # Check for forbidden patterns
        if '(was ' in content or '...)' in content:
            issues.append("Contains forbidden commentary/parentheticals")
        
        # Check for truncated pools
        if 'P:p...' in content or re.search(r'P:.*\.\.\.', content):
            issues.append("Truncated pool definitions detected")
        
        # Extract and validate pools
        pool_defs = set()
        pool_refs = set()
        
        # Find defined pools
        pool_def_pattern = r'P:([^:\n]+)'
        pool_match = re.search(pool_def_pattern, content)
        if pool_match:
            pool_line = pool_match.group(1)
            for pool_def in re.finditer(r'(p\d+)=', pool_line):
                pool_defs.add(pool_def.group(1))
        
        # Find referenced pools
        for pool_ref in re.finditer(r'\b(p\d+)\b', content):
            if pool_ref.start() > content.find('T:'):  # Only in table/body sections
                pool_refs.add(pool_ref.group(1))
        
        # Check for missing pools
        missing_pools = pool_refs - pool_defs
        if missing_pools:
            issues.append(f"Missing pool definitions: {', '.join(sorted(missing_pools))}")
        
        return len(issues) == 0, {
            "valid": len(issues) == 0,
            "issues": issues,
            "missing_pools": list(missing_pools),
            "content": content,
            "language": lang
        }

    def _humanize_cai3_references(self, text: str, metadata: Dict[str, Any]) -> str:
        """
        Convert CAI3 references in Claude's response to human-readable explanations.
        
        This function identifies CAI3 references like "Block B#b9 (Function `ac`)" and 
        replaces them with readable explanations like "Function `add_config` in ConfigManager class".
        """
        if not metadata.get("compressed", False) or not self.source_path:
            return text
        
        try:
            # Load the CAI3 mapping data
            cai3_full = self.cai3_cache.load_full(self.source_path)
            cai3_map = self.cai3_cache.load_map(self.source_path)
            
            if not cai3_full or not cai3_map:
                self.logger.debug("CAI3 mapping data not available for humanization")
                return text
            
            # Create mapping from short names to full context
            humanized_text = text
            
            # Extract and replace various CAI3 reference patterns
            import re
            
            # Pattern 1: Block references like "Block B#b9" or "B#b9"
            block_pattern = r'(?:Block\s+)?B#([a-z0-9]+)'
            for match in re.finditer(block_pattern, text, re.IGNORECASE):
                block_id = match.group(1)
                full_match = match.group(0)
                
                # Find the corresponding node in CAI3Full
                readable_name = self._find_readable_name_for_block(block_id, cai3_full)
                if readable_name:
                    humanized_text = humanized_text.replace(full_match, f"{readable_name} (was {full_match})")
            
            # Pattern 2: Function references like "Function `ac`"
            func_pattern = r'Function\s+`([a-z0-9]+)`'
            for match in re.finditer(func_pattern, text, re.IGNORECASE):
                short_name = match.group(1)
                full_match = match.group(0)
                
                # Find the full function name
                readable_name = self._find_readable_name_for_short(short_name, cai3_full)
                if readable_name:
                    humanized_text = humanized_text.replace(full_match, f"Function `{readable_name}` (was `{short_name}`)")
            
            # Pattern 3: Method references like "method `vr`"
            method_pattern = r'(?:method|Method)\s+`([a-z0-9]+)`'
            for match in re.finditer(method_pattern, text, re.IGNORECASE):
                short_name = match.group(1)
                full_match = match.group(0)
                
                # Find the full method name with class context
                readable_name = self._find_readable_name_for_short(short_name, cai3_full, include_class=True)
                if readable_name:
                    humanized_text = humanized_text.replace(full_match, f"Method `{readable_name}` (was `{short_name}`)")
            
            # Pattern 4: CID references like "cid=fn_1a2c" or similar
            cid_pattern = r'(?:cid=|CID:\s*)([a-z_0-9]+)'
            for match in re.finditer(cid_pattern, text, re.IGNORECASE):
                cid = match.group(1)
                full_match = match.group(0)
                
                # Find the node with this CID
                readable_name = self._find_readable_name_for_cid(cid, cai3_full)
                if readable_name:
                    humanized_text = humanized_text.replace(full_match, f"{full_match} ({readable_name})")
            
            # Pattern 5: Pool references like "p0", "p1" etc
            pool_pattern = r'\bp([0-9]+)\b'
            for match in re.finditer(pool_pattern, text):
                pool_ref = match.group(0)
                pool_id = match.group(1)
                
                # Look up in pools
                if hasattr(cai3_full, 'pools') and pool_ref in cai3_full.pools:
                    pool_value = cai3_full.pools[pool_ref]
                    humanized_text = humanized_text.replace(pool_ref, f'"{pool_value}" (was {pool_ref})')
            
            # Add a summary of what was humanized if changes were made
            if humanized_text != text:
                changes_count = len(re.findall(r'\(was [^)]+\)', humanized_text))
                humanized_text = f"🔍 **Humanized {changes_count} CAI3 references for clarity:**\n\n{humanized_text}"
            
            return humanized_text
            
        except Exception as e:
            self.logger.debug(f"Could not humanize CAI3 references: {e}")
            return text

    def _strip_humanization_annotations(self, text: str) -> str:
        """
        Remove humanization annotations that Claude may add despite instructions.
        Removes patterns like "(was p0)", "(originally...)", etc.
        """
        if not text:
            return text
        
        try:
            original_text = text
            changes_made = []
            
            # Remove "(was ...)" patterns
            was_pattern = r'\s*\(was [^)]+\)'
            was_matches = re.findall(was_pattern, text)
            if was_matches:
                text = re.sub(was_pattern, '', text)
                changes_made.append(f"Removed {len(was_matches)} '(was ...)' annotations")
            
            # Remove "(originally ...)" patterns
            orig_pattern = r'\s*\(originally [^)]+\)'
            orig_matches = re.findall(orig_pattern, text)
            if orig_matches:
                text = re.sub(orig_pattern, '', text)
                changes_made.append(f"Removed {len(orig_matches)} '(originally ...)' annotations")
            
            # Remove other common annotation patterns
            which_pattern = r'\s*\(which was [^)]+\)'
            which_matches = re.findall(which_pattern, text)
            if which_matches:
                text = re.sub(which_pattern, '', text)
                changes_made.append(f"Removed {len(which_matches)} '(which was ...)' annotations")
                
            former_pattern = r'\s*\(formerly [^)]+\)'
            former_matches = re.findall(former_pattern, text)
            if former_matches:
                text = re.sub(former_pattern, '', text)
                changes_made.append(f"Removed {len(former_matches)} '(formerly ...)' annotations")
            
            # Remove any duplicate quotes that might result from cleaning
            quote_before = text.count('""')
            text = re.sub(r'""', '"', text)
            if quote_before > 0:
                changes_made.append(f"Fixed {quote_before} double quotes")
            
            # Remove empty parentheses
            empty_paren_pattern = r'\(\s*\)'
            empty_parens = len(re.findall(empty_paren_pattern, text))
            if empty_parens > 0:
                text = re.sub(empty_paren_pattern, '', text)
                changes_made.append(f"Removed {empty_parens} empty parentheses")
            
            # Clean up any double spaces
            text = re.sub(r'\s+', ' ', text)
            
            if changes_made:
                self.logger.info(f"🧹 Humanization cleanup: {', '.join(changes_made)}")
                self.logger.info(f"📊 Text length: {len(original_text)} → {len(text)} chars")
                
                # Show examples of what was removed for debugging
                if was_matches:
                    self.logger.info(f"🔍 Examples of removed '(was ...)': {was_matches[:3]}")
            else:
                self.logger.debug(f"✅ No humanization annotations found in {len(text)} chars of text")
            
            return text
            
        except Exception as e:
            self.logger.warning(f"Error stripping humanization annotations: {e}")
            return text

    def _find_readable_name_for_block(self, block_id: str, cai3_full) -> Optional[str]:
        """Find readable name for a block ID like 'b9'."""
        # Block IDs typically correspond to body content
        # Look for nodes with matching body references
        for node in cai3_full.nodes:
            if node.body_content and f"B#{block_id}" in node.body_content:
                return f"{node.type.value} `{node.name}`"
            # Also check if the block_id matches any part of the CID
            if block_id in node.cid:
                return f"{node.type.value} `{node.name}`"
        return None

    def _find_readable_name_for_short(self, short_name: str, cai3_full, include_class: bool = False) -> Optional[str]:
        """Find readable name for a short name like 'ac' or 'vr'."""
        for node in cai3_full.nodes:
            if node.short_name == short_name:
                if include_class and node.parent_cid:
                    # Find parent class
                    parent_node = next((n for n in cai3_full.nodes if n.cid == node.parent_cid), None)
                    if parent_node:
                        return f"{node.name}` in class `{parent_node.name}"
                return node.name
        return None

    def _find_readable_name_for_cid(self, cid: str, cai3_full) -> Optional[str]:
        """Find readable name for a CID like 'fn_1a2c'."""
        for node in cai3_full.nodes:
            if node.cid == cid:
                if node.parent_cid:
                    # Find parent class
                    parent_node = next((n for n in cai3_full.nodes if n.cid == node.parent_cid), None)
                    if parent_node:
                        return f"{node.type.value} `{node.name}` in class `{parent_node.name}`"
                return f"{node.type.value} `{node.name}`"
        return None

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
        """Process full CAI3-LITE output from Claude with robust fallback."""
        self.logger.info("🔄 Processing full CAI3-LITE output...")
        
        # LOG DETAILED EXTRACTION PROCESS
        self.logger.info("=" * 80)
        self.logger.info("🔍 CAI3 CONTENT EXTRACTION ANALYSIS")
        self.logger.info("=" * 80)
        
        # Extract CAI3-LITE content
        cai3_content = self._extract_cai3_content(claude_output)
        
        if not cai3_content:
            self.logger.warning("No CAI3 content found, trying alternative extraction methods")
            cai3_content = self._extract_cai3_content_fallback(claude_output)
        
        if cai3_content:
            self.logger.info(f"✅ Extracted CAI3 content ({len(cai3_content)} chars):")
            self.logger.info(f"First 500 chars:\n{cai3_content[:500]}")
            if len(cai3_content) > 500:
                self.logger.info(f"Last 500 chars:\n{cai3_content[-500:]}")
        else:
            self.logger.warning("❌ Failed to extract CAI3 content from Claude output")
        
        if not cai3_content or not self.source_path:
            self.logger.warning("No CAI3 content available, attempting direct Python extraction")
            return self._extract_python_code_directly(claude_output, metadata)
        
        # LOG TRANSLATION ATTEMPT
        self.logger.info("=" * 80)
        self.logger.info("🔄 CAI3 TO PYTHON TRANSLATION ANALYSIS")
        self.logger.info("=" * 80)
        self.logger.info(f"Source path: {self.source_path}")
        self.logger.info(f"CAI3 content length: {len(cai3_content)} chars")
        
        try:
            # Log what we're about to translate
            self.logger.info(f"🔄 Attempting to translate CAI3 content...")
            self.logger.info(f"Full CAI3 content being sent to translator:\n{cai3_content}")
            
            # Extract mappings from Claude's response if present
            claude_mappings = self._extract_claude_mappings(claude_output)
            
            # Translate CAI3-LITE to Python using the proper pipeline
            python_code = self._translate_cai3_to_python(
                cai3_lite_content=cai3_content,
                source_path=self.source_path,
                claude_mappings=claude_mappings
            )
            
            # LOG TRANSLATION RESULT
            self.logger.info("=" * 80)
            self.logger.info("📝 TRANSLATION RESULT ANALYSIS")
            self.logger.info("=" * 80)
            self.logger.info(f"✅ Translation completed!")
            self.logger.info(f"Python code length: {len(python_code) if python_code else 0} chars")
            
            if python_code:
                # Count pass statements
                pass_count = python_code.count('pass')
                line_count = len(python_code.strip().split('\n'))
                self.logger.info(f"📊 Pass statements: {pass_count}")
                self.logger.info(f"📊 Total lines: {line_count}")
                self.logger.info(f"📊 Pass ratio: {pass_count/line_count*100:.1f}% of lines are pass statements")
                
                # Show first part of translated code
                self.logger.info(f"🔍 First 1000 chars of translated Python:\n{python_code[:1000]}")
                
                # Check for specific patterns that indicate translation issues
                if pass_count > line_count * 0.5:
                    self.logger.warning(f"⚠️ HIGH PASS RATIO: {pass_count}/{line_count} lines are pass statements!")
                    self.logger.warning("This suggests CAI3 translation may have failed")
                    
                # Check if code looks like skeleton (mostly pass statements)
                non_pass_lines = [line.strip() for line in python_code.split('\n') 
                                if line.strip() and not line.strip().startswith('pass')]
                substantial_code_lines = [line for line in non_pass_lines 
                                        if not line.startswith(('class ', 'def ', '#', 'import ', 'from '))]
                
                self.logger.info(f"📊 Substantial code lines (non-pass, non-skeleton): {len(substantial_code_lines)}")
                if len(substantial_code_lines) < 5:
                    self.logger.warning("⚠️ Very few substantial code lines - translation may have produced skeleton only")
            else:
                self.logger.error("❌ Translation returned empty/null result")
            
            # Validate the translation result
            if not python_code or len(python_code.strip()) < 50:
                self.logger.warning(f"CAI3 translation produced minimal output ({len(python_code)} chars), trying fallback")
                return self._extract_python_code_directly(claude_output, metadata)
            
            # Format the output
            formatted_output = self._format_full_translation_output(
                claude_output=claude_output,
                python_code=python_code,
                metadata=metadata
            )
            
            # CRITICAL: Write the translated Python code back to the source file
            self.logger.info(f"💾 Writing translated Python code to {self.source_path}")
            try:
                with open(self.source_path, 'w', encoding='utf-8') as f:
                    f.write(python_code)
                self.logger.info(f"✅ Successfully wrote {len(python_code)} characters to {self.source_path}")
            except Exception as write_error:
                self.logger.error(f"❌ Failed to write to {self.source_path}: {write_error}")
                # Continue with formatted output even if file writing fails
            
            return formatted_output
            
        except Exception as e:
            self.logger.error(f"❌ Failed to translate CAI3-LITE: {e}")
            import traceback
            self.logger.error(f"📍 Translation stack trace:\n{traceback.format_exc()}")
            self.logger.info("🔄 Attempting fallback to direct Python extraction")
            return self._extract_python_code_directly(claude_output, metadata)

    def _extract_cai3_content(self, text: str) -> Optional[str]:
        """Extract CAI3 content from Claude's response."""
        import re
        
        self.logger.info("🔍 Extracting CAI3 content from Claude response...")
        
        # Try to find CAI3 block markers
        pattern = r'---CAI3.*?START---(.*?)---CAI3.*?END---'
        match = re.search(pattern, text, re.DOTALL)
        
        if match:
            content = match.group(1).strip()
            self.logger.info(f"✅ Found CAI3 content using block markers ({len(content)} chars)")
            return content
        
        # Try to find code blocks containing CAI3
        code_block_pattern = r'```(?:cai3lite?|cai3?|CAI3?|C3L)?[\s\n]*(.*?)```'
        matches = re.findall(code_block_pattern, text, re.DOTALL | re.IGNORECASE)
        
        for i, content in enumerate(matches):
            content = content.strip()
            # Check if this looks like CAI3 content
            if '#C3L' in content or any(marker in content for marker in ['X:', 'D:', 'T:', 'B#', 'P:']):
                self.logger.info(f"✅ Found CAI3 content in code block {i+1} ({len(content)} chars)")
                self.logger.info(f"Code block content preview: {content[:200]}...")
                return content
        
        # Try to find content after header
        if '#C3L' in text:
            self.logger.info("🔍 Found #C3L header, extracting content after it...")
            # Extract everything after the header
            start_idx = text.index('#C3L')
            # Find the end (usually before explanation text)
            end_markers = ['\n\n---', '\n\nThe', '\n\nThis', '\n\nI', '\n\nNote', '```']
            end_idx = len(text)
            used_marker = "end of text"
            
            for marker in end_markers:
                marker_pos = text.find(marker, start_idx + 4)  # +4 to skip past #C3L
                if marker_pos != -1 and marker_pos < end_idx:
                    end_idx = marker_pos
                    used_marker = marker.strip()
            
            content = text[start_idx:end_idx].strip()
            self.logger.info(f"✅ Extracted CAI3 content from #{start_idx} to #{end_idx} (stopped at: {used_marker})")
            self.logger.info(f"Extracted content ({len(content)} chars): {content[:200]}...")
            
            return content
        
        self.logger.warning("❌ No CAI3 content found using primary extraction methods")
        return None
        
        return None

    def _extract_cai3_content_fallback(self, text: str) -> Optional[str]:
        """Enhanced CAI3 content extraction with multiple strategies."""
        import re
        
        # Strategy 1: Look for code blocks containing CAI3
        code_block_pattern = r'```(?:cai3?|CAI3?)\s*(.*?)```'
        match = re.search(code_block_pattern, text, re.DOTALL | re.IGNORECASE)
        if match:
            self.logger.debug("Found CAI3 content in code block")
            return match.group(1).strip()
        
        # Strategy 2: Look for any code block that contains CAI3 patterns
        generic_code_pattern = r'```\w*\s*(.*?)```'
        for match in re.finditer(generic_code_pattern, text, re.DOTALL):
            content = match.group(1).strip()
            if any(marker in content for marker in ['#C3L', 'I:', 'C:', 'F:', 'M:']):
                self.logger.debug("Found CAI3 patterns in generic code block")
                return content
        
        # Strategy 3: Look for structured content after CAI3 header
        if any(marker in text for marker in ['#C3L', 'CAI3', 'I:', 'C:', 'F:']):
            lines = text.split('\n')
            collecting = False
            collected_lines = []
            
            for line in lines:
                if any(marker in line for marker in ['#C3L', 'CAI3-LITE', 'I:', 'C:', 'F:']):
                    collecting = True
                elif collecting and line.strip() and not line.startswith(' ') and len(line) > 50:
                    # Likely explanation text, stop collecting
                    break
                
                if collecting and line.strip():
                    collected_lines.append(line)
            
            if collected_lines:
                result = '\n'.join(collected_lines).strip()
                self.logger.debug(f"Extracted {len(result)} chars using structured collection")
                return result
        
        return None

    def _extract_python_code_directly(self, claude_output: str, metadata: Dict) -> str:
        """Extract Python code directly from Claude's response as fallback."""
        import re
        
        self.logger.info("Attempting direct Python code extraction from Claude response")
        
        # Strategy 1: Look for Python code blocks
        python_code_pattern = r'```python\s*(.*?)```'
        match = re.search(python_code_pattern, claude_output, re.DOTALL | re.IGNORECASE)
        if match:
            python_code = match.group(1).strip()
            self.logger.info(f"Found Python code block ({len(python_code)} chars)")
            
            # Format as if it came from CAI3 translation
            return self._format_fallback_output(claude_output, python_code, metadata)
        
        # Strategy 2: Look for any code block that looks like Python
        generic_code_pattern = r'```\w*\s*(.*?)```'
        for match in re.finditer(generic_code_pattern, claude_output, re.DOTALL):
            content = match.group(1).strip()
            # Check if it looks like Python (has common Python keywords/patterns)
            if any(keyword in content for keyword in ['def ', 'class ', 'import ', 'from ', 'if __name__']):
                self.logger.info(f"Found Python-like code block ({len(content)} chars)")
                return self._format_fallback_output(claude_output, content, metadata)
        
        # Strategy 3: Extract text that looks like code (indented lines)
        lines = claude_output.split('\n')
        code_lines = []
        collecting_code = False
        
        for line in lines:
            # Start collecting if we see Python-like patterns
            if any(pattern in line for pattern in ['def ', 'class ', 'import ', 'from ', '#!/usr/bin/env python']):
                collecting_code = True
            
            # Collect indented lines or lines that look like code
            if collecting_code and (line.startswith('    ') or line.startswith('\t') or 
                                   any(pattern in line for pattern in ['def ', 'class ', 'import ', 'return ', 'if ', 'for ', 'while '])):
                code_lines.append(line)
            elif collecting_code and not line.strip():
                code_lines.append(line)  # Keep empty lines
            elif collecting_code and line.strip() and not line.startswith(' '):
                # Non-indented non-empty line, might be end of code
                if len(line) > 60 and not any(kw in line for kw in ['def ', 'class ', '=', '(']):
                    break  # Likely explanation text
                code_lines.append(line)
        
        if code_lines:
            extracted_code = '\n'.join(code_lines).strip()
            self.logger.info(f"Extracted code from structured text ({len(extracted_code)} chars)")
            return self._format_fallback_output(claude_output, extracted_code, metadata)
        
        # Final fallback: return original with warning
        self.logger.warning("Could not extract Python code, returning original output")
        return f"⚠️ CAI3 translation failed and no Python code found in response.\n\n{claude_output}"

    def _format_fallback_output(self, claude_output: str, python_code: str, metadata: Dict) -> str:
        """Format output when using fallback Python extraction."""
        # Extract Claude's explanation (everything that's not code)
        explanation = self._extract_explanation(claude_output)
        
        return f"""✅ Python Code Extracted (CAI3 Translation Fallback)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⚠️  Note: CAI3 translation failed, extracted Python code directly from response.
📊 Compression Analytics: 
• Original: {metadata.get('original_tokens', 0):,} tokens
• Compressed: {metadata.get('compressed_tokens', 0):,} tokens  
• Extracted: {len(python_code.split())} words

📝 Claude's Analysis:
{explanation}

📄 Extracted Python Code:
```python
{python_code}
```
💾 Code extraction completed (fallback mode)
"""

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
        
        # Add a note about CAI3 humanization if references were found
        humanization_note = ""
        if "(was " in claude_output:
            humanization_note = "\n💡 CAI3 references have been humanized for clarity above.\n"
        
        return f"""✅ CAI3 Patch Processed
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 Compression Analytics:
• Original: {metadata['original_tokens']:,} tokens
• Compressed: {metadata['compressed_tokens']:,} tokens
• Net Savings: {metadata['tokens_saved']:,} tokens ({metadata['compression_ratio']:.1f}%)
• Est. Cost Saved: ${metadata['potential_cost_savings']:.3f}
{humanization_note}
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
        
        # Add a note about CAI3 humanization if references were found
        humanization_note = ""
        if "(was " in claude_output:
            humanization_note = "\n💡 CAI3 references have been humanized for clarity above.\n"
        
        return f"""✅ CAI3 Translation Complete
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 Compression Analytics:
• Original: {metadata['original_tokens']:,} tokens
• Compressed: {metadata['compressed_tokens']:,} tokens
• Translated: {patched_tokens:,} tokens
• Net Savings: {metadata['tokens_saved']:,} tokens ({metadata['compression_ratio']:.1f}%)
• Est. Cost Saved: ${metadata['potential_cost_savings']:.3f}
{humanization_note}
📝 Claude's Analysis:
{explanation}

📄 Translated Python Code:
```python
{python_code}
```
💾 Translation completed successfully
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

    def _comprehensive_cai3_repair(self, malformed_output: str, metadata: Dict) -> str:
        """
        Comprehensive CAI3 repair combining prompt-level prevention with post-processing fixes.
        """
        self.logger.info("Performing comprehensive CAI3 repair")
        
        # First apply standard repair
        repaired = self._simple_repair_cai3_format(malformed_output)
        
        # Then apply bracket-specific validation
        repaired = self._validate_bracket_balance(repaired)
        
        # Finally, ensure all pool references are defined
        repaired = self._ensure_pool_completeness(repaired)
        
        return repaired
    
    def _validate_bracket_balance(self, content: str) -> str:
        """
        Validate and fix bracket balance in CAI3-LITE content.
        """
        import re
        
        # Extract the code block content
        code_blocks = re.findall(r'```(\w+)?\n(.*?)\n```', content, re.DOTALL)
        if not code_blocks:
            return content
        
        lang, code_content = code_blocks[0]
        
        # Track bracket balance
        open_braces = 0
        close_braces = 0
        open_parens = 0
        close_parens = 0
        open_brackets = 0
        close_brackets = 0
        
        # Check balance in each line
        lines = code_content.split('\n')
        for i, line in enumerate(lines):
            # Count opening brackets
            open_braces += line.count('{')
            open_parens += line.count('(')
            open_brackets += line.count('[')
            
            # Count closing brackets
            close_braces += line.count('}')
            close_parens += line.count(')')
            close_brackets += line.count(']')
        
        # Generate correction strategy
        corrections = []
        if open_braces > close_braces:
            corrections.append('}' * (open_braces - close_braces))
        if open_parens > close_parens:
            corrections.append(')' * (open_parens - close_parens))
        if open_brackets > close_brackets:
            corrections.append(']' * (open_brackets - close_brackets))
        
        if corrections:
            # Apply corrections to the last line (naive approach)
            lines[-1] += ''.join(corrections)
            self.logger.info(f"Applied bracket balance corrections: {corrections}")
        
        return content.replace(code_content, '\n'.join(lines))
    
    def _ensure_pool_completeness(self, content: str) -> str:
        """
        Ensure all pool references have corresponding definitions.
        """
        import re
        
        # Extract the code block content
        code_blocks = re.findall(r'```(\w+)?\n(.*?)\n```', content, re.DOTALL)
        if not code_blocks:
            return content
        
        lang, code_content = code_blocks[0]
        
        # Find all pool references
        pool_refs = set(re.findall(r'#(p\d+)', code_content))
        
        # Find existing pool definitions
        pool_defs = set()
        pool_match = re.search(r'P:([^\n]+)', code_content)
        if pool_match:
            pool_line = pool_match.group(1)
            pool_defs.update(re.findall(r'(p\d+)=', pool_line))
        else:
            # No P: section, all pools are undefined
            pool_defs = set()
        
        # Add missing pool definitions
        missing_pools = pool_refs - pool_defs
        if missing_pools:
            self.logger.info(f"Adding missing pool definitions: {missing_pools}")
            
            # Create new pool definitions
            new_pools = [f'{pool}="auto_generated_{pool}"' for pool in sorted(missing_pools)]
            
            if pool_match:
                # Append to existing P: line
                existing_pools = pool_match.group(1)
                new_pool_line = f"P:{existing_pools},{','.join(new_pools)}"
                code_content = code_content.replace(f"P:{existing_pools}", new_pool_line)
            else:
                # Add new P: line after header
                lines = code_content.split('\n')
                if lines and lines[0].startswith('#C3L'):
                    lines.insert(1, f"P:{','.join(new_pools)}")
                else:
                    lines.insert(0, f"P:{','.join(new_pools)}")
                code_content = '\n'.join(lines)
        
        return content.replace(code_blocks[0][1], code_content)
    
    def process_with_constraints(self, cai3_lite: str, task: str, 
                               cai3_full = None) -> Tuple[str, Dict[str, str]]:
        """
        Process CAI3 edits using the advanced constraint-based interface.
        
        This method uses the new ClaudeCAI3Interface for better constraint enforcement
        and violation prevention through prompt engineering.
        
        Args:
            cai3_lite: CAI3-LITE compressed representation
            task: Task description for Claude
            cai3_full: Full CAI3 structure with constraints (loaded from cache if None)
            
        Returns:
            Tuple of (processed_cai3_output, mappings_dict)
        """
        if not self.enable_constraint_system or not self.cai3_interface:
            self.logger.warning("Constraint system not available, falling back to standard processing")
            return self._fallback_processing(cai3_lite, task)
        
        # Load CAI3Full from cache if not provided
        if cai3_full is None and self.source_path:
            cai3_full = self.cai3_cache.load_full(self.source_path)
        
        # Check if we have valid CAI3Full structure
        if cai3_full is None:
            self.logger.warning("CAI3Full structure not available, using fallback processing")
            return self._fallback_processing(cai3_lite, task)
        
        # Validate CAI3Full has required attributes
        if not hasattr(cai3_full, 'hash_to_value') or not hasattr(cai3_full, 'pools'):
            self.logger.warning("CAI3Full structure missing required attributes, using fallback processing")
            return self._fallback_processing(cai3_lite, task)
        
        try:
            # Use the constraint-based interface
            self.logger.info("Processing with constraint-based interface")
            cai3_output, mappings = self.cai3_interface.request_cai3_edit(
                cai3_lite=cai3_lite,
                task=task,
                cai3_full=cai3_full
            )
            
            # Convert output to CLI-compatible format for translation system
            formatted_output = self.cai3_interface.convert_to_cli_format(cai3_output)
            self.logger.debug(f"Converted constraint output to CLI format: {len(formatted_output)} chars")
            
            # Log constraint statistics
            stats = self.cai3_interface.get_constraint_statistics()
            self.logger.debug(f"Constraint stats: {stats}")
            
            return formatted_output, mappings
            
        except Exception as e:
            self.logger.error(f"Constraint-based processing failed: {e}")
            self.logger.info("Falling back to standard processing")
            return self._fallback_processing(cai3_lite, task)
    
    def _fallback_processing(self, cai3_lite: str, task: str) -> Tuple[str, Dict[str, str]]:
        """
        Fallback processing method when constraint system is unavailable.
        
        Uses the existing prompt wrapping and validation approach.
        """
        # Create a basic prompt using existing methods
        metadata = {
            'session_id': self.current_session_id or 'fallback',
            'tokens_saved': 0,
            'compression_ratio': 0
        }
        
        prompt = self._wrap_cai3_prompt_concise(cai3_lite, metadata, task)
        
        # Simulate Claude call (would be replaced with actual implementation)
        response = self._simulate_claude_response(prompt)
        
        # Parse response
        cai3_output, mappings = self._parse_claude_response(response)
        
        # Apply basic validation and repair
        is_compliant, _ = self._validate_cai3_compliance(cai3_output)
        if not is_compliant:
            cai3_output = self._simple_repair_cai3_format(cai3_output)
        
        return cai3_output, mappings
    
    def _parse_claude_response(self, response: str) -> Tuple[str, Dict[str, str]]:
        """
        Parse Claude response to extract CAI3 content and mappings.
        
        This method looks for structured MAPPINGS and CAI3-LITE sections first,
        then falls back to code block extraction.
        """
        mappings = {}
        cai3_content = ""
        
        # Try to parse structured response first
        if '=== MAPPINGS ===' in response and '=== CAI3-LITE ===' in response:
            sections = response.split('=== ')
            
            for section in sections:
                if section.startswith('MAPPINGS ==='):
                    mappings_text = section.replace('MAPPINGS ===', '').split('=== CAI3-LITE ===')[0].strip()
                    mappings = self._parse_mappings_from_text(mappings_text)
                    
                elif section.startswith('CAI3-LITE ==='):
                    cai3_content = section.replace('CAI3-LITE ===', '').strip()
        
        # Fallback to code block extraction
        if not cai3_content:
            # Try different regex patterns to capture CAI3 code blocks
            cai3_patterns = [
                r'```cai3lite\n(.*?)\n```',  # Specifically for cai3lite
                r'```(?:C3L|cai3|CAI3)\n(.*?)\n```',  # Other CAI3 formats
                r'```\n(#C3L.*?)\n```'  # Any code block starting with #C3L
            ]
            
            for pattern in cai3_patterns:
                code_blocks = re.findall(pattern, response, re.DOTALL)
                if code_blocks:
                    cai3_content = code_blocks[0]
                    break
        
        return cai3_content, mappings
    
    def _parse_mappings_from_text(self, mappings_text: str) -> Dict[str, str]:
        """Parse mappings from text format."""
        mappings = {}
        
        for line in mappings_text.split('\n'):
            line = line.strip()
            if ':' in line and not line.startswith('#'):
                try:
                    key, value = line.split(':', 1)
                    mappings[key.strip()] = value.strip()
                except ValueError:
                    continue
        
        return mappings
    
    def _simulate_claude_response(self, prompt: str) -> str:
        """
        Simulate Claude response for testing.
        In production, this would be replaced with actual Claude API calls.
        """
        # This is a placeholder - in real implementation, this would call Claude
        return """=== MAPPINGS ===
optimized_validator: optimized_validation_function
enhanced_check: enhanced_validation_check

=== CAI3-LITE ===
#C3L v2 py=3.11 f=example.py
P:p0="user_id",p1="email",p2="required_fields"
X:a0=mt_5605,a1=mt_961c
T:M:UserValidator.vr#a0,M:UserValidator.optimized_validator#a1
B#a0:rf=p2;@f,rf{f!inp0?(s.l.er(f'Missing: {f}'),RF):_};RT
B#a1:# Enhanced validation with optimized logic here
"""
    
    def get_constraint_interface_stats(self) -> Optional[Dict[str, Any]]:
        """Get statistics from the constraint-based interface."""
        if self.cai3_interface:
            return self.cai3_interface.get_constraint_statistics()
        return None

    # Add this method implementation to claude_proxy.py

    def _extract_claude_mappings(self, claude_output: str) -> Dict[str, Any]:
        """
        Extract mappings from Claude's response including MAPPINGS section and inline definitions.
        
        Returns:
            Dict containing hash_mappings, pools, variables, and methods
        """
        mappings = {
            'hash_mappings': {},
            'pools': {},
            'variables': {},
            'methods': {}
        }
        
        # Pattern 1: Extract from "=== MAPPINGS ===" section
        mappings_pattern = r'===\s*MAPPINGS\s*===\s*\n(.*?)(?:===|$)'
        mappings_match = re.search(mappings_pattern, claude_output, re.DOTALL)
        
        if mappings_match:
            mappings_content = mappings_match.group(1)
            self.logger.info(f"Found MAPPINGS section with {len(mappings_content)} chars")
            
            # Parse each line in MAPPINGS section
            for line in mappings_content.split('\n'):
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                    
                # Parse mapping entries like "hash_0a21: dataclasses"
                if ':' in line:
                    key, value = line.split(':', 1)
                    key = key.strip()
                    value = value.strip()
                    
                    # Normalize hash keys
                    if key.startswith('hash_') or key.startswith('#'):
                        # Normalize: #0a21 -> hash_0a21, hash_0A21 -> hash_0a21
                        normalized_key = key.replace('#', 'hash_').lower()
                        if not normalized_key.startswith('hash_'):
                            normalized_key = f'hash_{normalized_key}'
                        mappings['hash_mappings'][normalized_key] = value
                        self.logger.debug(f"Added hash mapping: {normalized_key} -> {value}")
                    
                    # Pool mappings (p0, p1, etc.)
                    elif re.match(r'^p\d+$', key):
                        # Ensure string values are quoted
                        if value and not (value.startswith('"') or value.startswith("'")):
                            # Check if it's a Python literal that needs quoting
                            if not value.replace('.', '').replace('_', '').isalnum():
                                value = f'"{value}"'
                        mappings['pools'][key] = value
                        self.logger.debug(f"Added pool mapping: {key} -> {value}")
                    
                    # Variable/identifier mappings
                    else:
                        mappings['variables'][key] = value
        
        # Pattern 2: Extract pools from P: section in CAI3 block
        cai3_pattern = r'```(?:C3L|CAI3|cai3)?\s*\n(.*?)```'
        cai3_match = re.search(cai3_pattern, claude_output, re.DOTALL | re.IGNORECASE)
        
        if cai3_match:
            cai3_content = cai3_match.group(1)
            
            # Extract P: section
            p_section_pattern = r'^P:\s*(.+?)(?=^[A-Z]:|^B#|^---|$)'
            p_match = re.search(p_section_pattern, cai3_content, re.MULTILINE | re.DOTALL)
            
            if p_match:
                pool_content = p_match.group(1).strip()
                # Parse pool assignments like p0="value",p1="value2"
                pool_pattern = r'(p\d+)=("(?:[^"\\]|\\.)*"|\'(?:[^\'\\]|\\.)*\'|[^,\n]+)'
                
                for match in re.finditer(pool_pattern, pool_content):
                    pool_id = match.group(1)
                    pool_value = match.group(2).strip()
                    
                    # Don't override if already in mappings from MAPPINGS section
                    if pool_id not in mappings['pools']:
                        mappings['pools'][pool_id] = pool_value
                        self.logger.debug(f"Added pool from P: section: {pool_id} -> {pool_value}")
        
        # Log summary
        self.logger.info(f"Extracted mappings summary: "
                        f"{len(mappings['hash_mappings'])} hashes, "
                        f"{len(mappings['pools'])} pools, "
                        f"{len(mappings['variables'])} variables")
        
        return mappings

    def _translate_cai3_to_python(self, cai3_lite_content: str, source_path: Path, 
                                claude_mappings: Dict[str, Any]) -> str:
        """
        Translate CAI3-LITE to Python with Claude's mappings properly integrated.
        """
        self.logger.info(f"Starting CAI3 to Python translation with {len(claude_mappings.get('hash_mappings', {}))} hash mappings")
        
        try:
            # Forward to translator with mappings
            python_code = self.cai3_translator.translate_cai3_lite_to_python(
                cai3_lite_content,
                source_path,
                claude_mappings  # Pass the full mappings dict
            )
            
            return python_code
            
        except Exception as e:
            self.logger.error(f"CAI3 to Python translation failed: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            
            # Fallback
            return self._fallback_cai3_reconstruction(cai3_lite_content, claude_mappings)

    # Update _process_full_cai3_output to properly extract and pass mappings
    def _process_full_cai3_output(self, claude_output: str, metadata: Dict) -> str:
        """Process full CAI3-LITE output from Claude with proper mapping extraction."""
        self.logger.info("🔄 Processing full CAI3-LITE output...")
        
        # Extract mappings FIRST
        claude_mappings = self._extract_claude_mappings(claude_output)
        
        # Extract CAI3 content
        cai3_content = self._extract_cai3_content(claude_output)
        
        if not cai3_content:
            self.logger.error("❌ No CAI3 content found in Claude output")
            return self._extract_python_code_directly(claude_output, metadata)
        
        if not self.source_path:
            self.logger.error("❌ No source path set for translation")
            return self._format_error_output(claude_output, Exception("No source path"), metadata)
        
        try:
            # Translate with mappings
            python_code = self._translate_cai3_to_python(cai3_content, self.source_path, claude_mappings)
            
            self.logger.info(f"✅ CAI3 translation successful: {len(python_code)} chars")
            return self._format_full_translation_output(claude_output, python_code, metadata)
            
        except Exception as e:
            self.logger.error(f"❌ CAI3 translation failed: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            return self._format_error_output(claude_output, e, metadata)
    
    def _extract_inline_mappings(self, text: str, mappings: Dict[str, Any]):
        """Extract mappings from inline comments and patterns in the text."""
        
        # Look for pool definitions like "p0: datetime", "p1: 'Tier 1 - Basic'"
        pool_pattern = r'(p\d+):\s*["\']?([^,\n"\']+)["\']?'
        for match in re.finditer(pool_pattern, text):
            pool_id, pool_value = match.groups()
            mappings['pools'][pool_id] = pool_value.strip()
        
        # Look for variable mappings like "min_tokens: min_t"
        var_pattern = r'(\w+):\s*(\w+)'
        lines = text.split('\n')
        in_mapping_section = False
        
        for line in lines:
            if 'mappings' in line.lower() or 'variable mappings' in line.lower():
                in_mapping_section = True
                continue
            elif in_mapping_section and (line.strip() == '' or line.startswith('#')):
                continue
            elif in_mapping_section and not line.startswith(' '):
                in_mapping_section = False
            
            if in_mapping_section:
                match = re.search(var_pattern, line)
                if match:
                    original, compressed = match.groups()
                    if len(compressed) < len(original):  # Likely a compression mapping
                        mappings['variables'][compressed] = original
                        
    # Update the _translate_cai3_to_python method



    
    def _fallback_cai3_reconstruction(self, cai3_lite_content: str, claude_mappings: Dict[str, Any]) -> str:
        """
        Fallback reconstruction when the full pipeline fails.
        Uses simple string replacement and pattern matching.
        """
        self.logger.warning("🚨 Using fallback CAI3 reconstruction")
        
        try:
            # Extract basic structure
            lines = cai3_lite_content.split('\n')
            imports = []
            classes = []
            methods = []
            
            current_section = None
            
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                    
                if line.startswith('I:'):
                    # Imports section
                    import_line = line[2:].strip()
                    imports.extend(self._parse_import_line(import_line))
                elif line.startswith('T:'):
                    # Table section - extract class and method definitions
                    table_content = line[2:].strip()
                    classes_and_methods = self._parse_table_section(table_content)
                    classes.extend(classes_and_methods.get('classes', []))
                    methods.extend(classes_and_methods.get('methods', []))
                elif line.startswith('B#'):
                    # Body section - extract method implementations
                    pass  # Would need more complex parsing
            
            # Simple reconstruction
            python_lines = []
            
            # Add imports
            for imp in imports:
                python_lines.append(imp)
            python_lines.append("")
            
            # Add classes with stub methods
            for class_name in classes:
                python_lines.append(f"class {class_name}:")
                
                class_methods = [m for m in methods if m.get('class') == class_name]
                if not class_methods:
                    python_lines.append("    pass")
                else:
                    for method in class_methods:
                        python_lines.append(f"    def {method['name']}(self):")
                        python_lines.append("        # Method implementation would be reconstructed here")
                        python_lines.append("        pass")
                        python_lines.append("")
                
                python_lines.append("")
            
            result = '\n'.join(python_lines)
            self.logger.info(f"✅ Fallback reconstruction completed: {len(result)} chars")
            return result
            
        except Exception as e:
            self.logger.error(f"❌ Fallback reconstruction failed: {e}")
            return f"""# CAI3 Reconstruction Failed
# Original CAI3-LITE content:
# {cai3_lite_content[:500]}...

# Error: {e}
# Manual reconstruction required.
pass
"""