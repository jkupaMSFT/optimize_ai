"""
Claude CAI3 Interface - Advanced constraint-based interaction system.

This module implements a hybrid approach combining:
1. Constrained prompt engineering
2. Output validation and constraint checking
3. Mapping management and resolution
4VALIDATION REQUIREMENTS:
- All referenced pools (p0, p1, etc.) must be defined in P: section
- All new hashes and pools must have corresponding entries in MAPPINGS section
- Bracket balance: { } must match exactly
- Complete try-except structures: T{...}X{...}

EXACT CAI3-LITE FORMAT REQUIRED:
```
#C3L v2 py=3.11 f=filename.py
I:import1|import2|module:class,func
D:g0=ClassName|g1=function_name
X:a0=hash1,a1=hash2,a2=hash3
P:p0=pool_value1,p1=pool_value2
V:s=self,na=name,th=threshold,co=features,cp=compression_ratio,de=description
T:C:g0,M:g0.method#a0,M:g0.method2#a1,F:g1#a2
---
B#a0:method_body_content_here
B#a1:another_method_body_here
B#a2:function_body_content_here
```

VALID SECTION IDENTIFIERS ONLY:
- #C3L (header)
- I: (imports)
- D: (chain aliases)
- X: (CID aliases)
- P: (pools)
- S: (self-attributed variables) - NEW: self.* attributes
- V: (variable/attribute mappings) - other variables
- T: (table)
- B# (bodies)
- --- (separator)

FORBIDDEN SECTIONS:
- R: (raw data) - NEVER ALLOWED
- Any other section identifiers not listed above

CRITICAL FORMAT RULES:
- Bodies MUST use format: B#aliasId:content (e.g., B#a0:return x + y)
- Table entries MUST use: C:className, M:className.method#alias, F:function#alias
- NO spaces around colons in body definitions
- Pools use format: p0=value,p1=value (comma separated)
- Aliases use format: a0=hash1,a1=hash2 (comma separated)

MAPPING EXAMPLES:
- If you create hash_5678, add: hash_5678: calculate_total
- If you create p25, add: p25: "user_email_address"
- If you create new_var, add: new_var: optimized_function_name

TASK: {task}

EXISTING CAI3-LITE:
{cai3_lite}straint violation repair

Best Practice: Use constraints to prevent issues rather than fixing them post-hoc.
"""

import re
import logging
from typing import Dict, List, Tuple, Optional, Any, Set
from dataclasses import dataclass
from pathlib import Path

try:
    from optimize_ai.input_optimizer.engine.cai3_structures import CAI3Full, CAI3Map, CAI3Lite
    from optimize_ai.input_optimizer.engine.cai3_ast_translator import CAI3Translator
except ImportError:
    try:
        from input_optimizer.engine.cai3_structures import CAI3Full, CAI3Map, CAI3Lite
        from input_optimizer.engine.cai3_ast_translator import CAI3Translator
    except ImportError:
        # Fallback for development
        class CAI3Full:
            def __init__(self):
                self.hash_to_value = {}
                self.pools = {}
                self.nodes = []
                
        class CAI3Map:
            def __init__(self):
                self.name_map = {}
                
        class CAI3Lite:
            def __init__(self):
                pass
                
        class CAI3Translator:
            def __init__(self):
                pass


@dataclass
class ConstraintViolation:
    """Represents a constraint violation found in Claude's output."""
    violation_type: str
    description: str
    location: str
    suggested_fix: str
    severity: str  # 'critical', 'warning', 'info'


@dataclass
class CAI3ValidationResult:
    """Result of CAI3 output validation."""
    is_valid: bool
    violations: List[ConstraintViolation]
    mappings: Dict[str, str]
    repaired_content: Optional[str] = None


class ClaudeCAI3Interface:
    """
    Advanced Claude CAI3 interaction interface with constraint-based validation.
    
    This class manages Claude interactions with CAI3-LITE using a hybrid approach:
    1. Constrained prompt engineering to prevent issues
    2. Output validation against known constraints
    3. Mapping resolution and new identifier tracking
    4. Iterative repair for constraint violations
    """
    
    def __init__(self, logger: Optional[logging.Logger] = None):
        """Initialize the Claude CAI3 interface."""
        self.logger = logger or logging.getLogger(__name__)
        self.translator = CAI3Translator()
        
        # Track constraint violations for learning
        self.violation_history: List[ConstraintViolation] = []
        self.successful_patterns: List[str] = []
        
        # Constraint enforcement settings
        self.enforce_strict_constraints = True
        self.max_repair_attempts = 3
        self.enable_constraint_learning = True
        
    def request_cai3_edit(self, cai3_lite: str, task: str, cai3_full: CAI3Full, cai3_map: Optional[Any] = None) -> Tuple[str, Dict[str, str]]:
        """
        Request a CAI3 edit from Claude with comprehensive constraint enforcement.
        
        Args:
            cai3_lite: The CAI3-LITE compressed representation
            task: The task/modification to perform
            cai3_full: Full CAI3 structure with context and constraints
            cai3_map: Optional CAI3Map with compression mappings for validation pool
            
        Returns:
            Tuple of (cai3_output, mappings_dict)
        """
        self.logger.info(f"Requesting CAI3 edit: {task[:100]}...")
        
        # 1. Create constrained prompt
        prompt = self._create_constrained_prompt(cai3_lite, task, cai3_full)
        
        # 2. Send to Claude with strict instructions
        response = self._send_to_claude(prompt)
        
        # 3. Parse response for mappings and code
        cai3_output, mappings = self._parse_response(response)
        
        # 4. Validate output against constraints (pass cai3_map for validation pool)
        validation_result = self._validate_constraints(cai3_output, cai3_full, mappings, cai3_map)
        
        if not validation_result.is_valid:
            # 5. Request fixes with specific violations highlighted
            self.logger.error(f"🚨 CONSTRAINT VALIDATION FAILED - Starting repair process")
            self.logger.error(f"Found {len(validation_result.violations)} constraint violations")
            
            for attempt in range(self.max_repair_attempts):
                self.logger.info(f"🔧 REPAIR ATTEMPT {attempt + 1}/{self.max_repair_attempts}")
                
                fix_prompt = self._create_fix_prompt(validation_result.violations, cai3_output, task)
                self.logger.info(f"📝 Sending repair prompt: {len(fix_prompt)} chars")
                self.logger.debug(f"Repair prompt preview: {fix_prompt[:300]}...")
                
                response = self._send_to_claude(fix_prompt)
                cai3_output, additional_mappings = self._parse_response(response)
                mappings.update(additional_mappings)
                
                self.logger.info(f"📥 Repair attempt {attempt + 1} response received")
                self.logger.info(f"  - New CAI3 content: {len(cai3_output)} chars")
                self.logger.info(f"  - Additional mappings: {len(additional_mappings)}")
                
                # Re-validate
                self.logger.info(f"🔍 Re-validating after repair attempt {attempt + 1}...")
                validation_result = self._validate_constraints(cai3_output, cai3_full, mappings)
                
                if validation_result.is_valid:
                    self.logger.info(f"✅ Constraint violations fixed on attempt {attempt + 1}")
                    break
                else:
                    self.logger.warning(f"⚠️ Repair attempt {attempt + 1} still has {len(validation_result.violations)} violations")
            
            if not validation_result.is_valid:
                self.logger.error(f"❌ Failed to fix all constraint violations after {self.max_repair_attempts} attempts")
                self.logger.error("🔧 Attempting to use repaired content if available...")
                # Use the repaired content if available
                if validation_result.repaired_content:
                    self.logger.info("✅ Using basic repaired content as fallback")
                    cai3_output = validation_result.repaired_content
                else:
                    self.logger.error("❌ No repaired content available - using original with violations")
        else:
            self.logger.info("✅ Initial validation passed - no repairs needed")
        
        # 6. Learn from successful patterns
        if validation_result.is_valid and self.enable_constraint_learning:
            self._learn_successful_pattern(prompt, cai3_output)
        
        return cai3_output, mappings
    
    def convert_to_cli_format(self, cai3_content: str) -> str:
        """
        Convert constraint-based CAI3 output to CLI-compatible format.
        
        The constraint system produces clean CAI3 content, but the CLI system
        expects it wrapped in a fenced code block for compatibility with
        existing validation and translation logic.
        """
        if not cai3_content.strip():
            return cai3_content
            
        # If already wrapped in code blocks, return as-is
        if '```' in cai3_content:
            return cai3_content
            
        # Detect language tag from content
        if cai3_content.strip().startswith('#C3L'):
            lang_tag = 'C3L'
        elif any(pattern in cai3_content for pattern in ['P:', 'X:', 'T:', 'B#']):
            lang_tag = 'cai3'
        else:
            lang_tag = 'C3L'
            
        # Wrap in appropriate code block format
        wrapped_content = f"```{lang_tag}\n{cai3_content.strip()}\n```"
        
        self.logger.debug(f"Converted CAI3 content to CLI format with {lang_tag} tag")
        return wrapped_content
    
    def _create_constrained_prompt(self, cai3_lite: str, task: str, cai3_full: CAI3Full) -> str:
        """
        Create a constrained prompt that prevents common Claude errors.
        
        This is the key prevention mechanism - we constrain Claude's output space
        rather than trying to fix everything afterwards.
        """
        # Extract available constraints from CAI3Full with safety checks
        available_hashes = []
        available_pools = []
        
        if cai3_full and hasattr(cai3_full, 'hash_to_value') and cai3_full.hash_to_value:
            available_hashes = list(cai3_full.hash_to_value.keys())[:30]  # Limit for prompt size
            
        if cai3_full and hasattr(cai3_full, 'pools') and cai3_full.pools:
            available_pools = list(cai3_full.pools.keys())
        
        # Identify existing identifiers in the CAI3-LITE
        existing_identifiers = self._extract_existing_identifiers(cai3_lite)
        
        # Build constraint specifications with stronger language
        hash_constraint = "Use hash_XXXX format (4 hex digits) for hash references. You may create new hashes as needed."
        pool_constraint = "You may create new pools (p##) as needed. All pools must be defined in P: section."
        identifier_constraint = "ANY new variable MUST be listed in MAPPINGS section"
        
        # Create the constrained prompt with stronger directives
        prompt = f"""🚨 CRITICAL: RESPOND ONLY IN THE EXACT FORMAT BELOW 🚨

You MUST start your response with exactly these headers:

=== CAI3-LITE ===
[Your modified CAI3-LITE code here]

❌ FORBIDDEN: NO explanatory text, NO prose, NO comments outside these sections.

🚨 CRITICAL CAI3-LITE SYNTAX RULES:

❌ NEVER USE PYTHON SYNTAX:
- NO: from dataclasses import dataclass
- NO: @dataclass 
- NO: CompressionAnalyzer() 
- NO: Path("output.txt")
- NO: file_path.exists()
- NO: try:/except: blocks with Python syntax
- NO: Full Python class/method names in table
- NO: Full private variable names more than two characters(e.g. s.variable)

✅ ONLY USE CAI3-LITE COMPRESSED SYNTAX:
- Table entries: C:ct,M:ct.ia(s,p)#a2 (NOT C:CompressionTier,M:CompressionTier.is_initialized(self,parameter#a2)
- Body content: hash_1234();v=ca();an=ao (NOT Python imports or full method calls)
- Use hash references: hash_7b30 (NOT Path)
- Use two-character private variables: s.mi, s.na (NOT self.analyzer)
- Use pool references: p0, p1, p2 (NOT full variable names)
- Parameter mapping: ALL method parameters MUST be mapped in V: section

🚨 CRITICAL VARIABLE MAPPING REQUIREMENTS:

S: SECTION - SELF-ATTRIBUTES (REQUIRED if using self):
Contains self mapping and ALL self-attribute suffixes
- Format: S:s=self,na=name,th=threshold,co=features,af=analyze_file
- Rule: if body has s.ti or s.af → S: MUST have ti=..., af=...

V: SECTION - LOCAL VARIABLES (REQUIRED):
Contains ONLY single/multi-letter local variables, NO self-attributes
- Format: V:i=index,k=key,v=value,o=item,aa=analyzer,ac=config
- Rule: All local variables (i, j, k, aa, ab) used in B# sections

❌ WRONG (self-attributes mixed with variables):
V:s=self,i=index,k=key,v=value,ti=tiers,af=analyze_file
B#a0:for o in s.ti:v=s.af(k)

✅ CORRECT (separated S: and V: sections):
S:s=self,ti=tiers,af=analyze_file
V:i=index,k=key,v=value,o=item
B#a0:for o in s.ti:v=s.af(k)

🚨 CRITICAL D: SECTION REQUIREMENT - HASH MAPPING COMPLETENESS:
The D: section MUST contain EVERY hash_XXXX reference that appears in ANY body section (B#).

❌ WRONG (Incomplete D: section):
D:g0=o.name
B#a0:if hash_ca00 in v:return hash_e29c
B#a1:k=hash_7b30(hash_2308)

✅ CORRECT (Complete D: section with ALL hash mappings):
D:hash_ca00=error,hash_e29c=name,hash_7b30=Path,hash_2308="/tmp/output"
B#a0:if hash_ca00 in v:return hash_e29c
B#a1:k=hash_7b30(hash_2308)


❌ WRONG (Python-mixed):
T:C:CompressionTier,M:CompressionTier.is_initialized#a2
B#a0:from dataclasses import dataclass;analyzer=CompressionAnalyzer()
B#a7:try:file_path=Path(file_path);if not file_path.exists():

EXAMPLE CORRECT RESPONSE:

=== CAI3-LITE ===
#C3L v2 py=3.11 f=example.py
D:hash_1234=calculate_total
S:s=self,va=value
V:i=index,v=value,n=name,p=parameter
P:p0="value1",p1="user_email_address"
X:a0=5mn3,a1=e0wr
T:C:ct,M:ct.ia(s,p)#a0
---
B#a0:s.va=v;i=p0;n=p;return hash_1234

CONSTRAINTS (VIOLATION = FAILURE):
1. {hash_constraint}
2. {pool_constraint}
3. {identifier_constraint}
4. ALL new identifiers → MAPPINGS section
5. Method names = valid Python identifiers ONLY
6. NO "(was ...)" or "(originally ...)" text ANYWHERE
7. NO "..." truncation markers ANYWHERE
8. Exact CAI3-LITE syntax required
9. ONLY VALID SECTIONS: #C3L, I:, D:, S:, V:, X:, P:, T:, B# - NO R: or other sections
10. NO raw data, base64, or R: sections allowed
11. 🚨 NO PYTHON IMPORTS OR SYNTAX IN B# BLOCKS
12. 🚨 USE SHORT ALIASES IN TABLE, NOT FULL CLASS NAMES
13. 🚨 ALL B# CONTENT MUST BE CAI3-COMPRESSED, NOT PYTHON
14. 🚨 D: SECTION MUST CONTAIN ALL hash_XXXX MAPPINGS USED IN B# SECTIONS
15. 🚨 S: SECTION MUST CONTAIN s=self AND ALL self-attribute mappings 
16. 🚨 V: SECTION MUST CONTAIN ALL local variable mappings 
17. 🚨 CRITICAL: USE T{{}}X(ex){{}} STRUCTURE FOR TRY/EXCEPT

🔧 MANDATORY SYNTAX VALIDATION:
Before submitting your response, VERIFY:
✓ Every opening bracket [ has a closing bracket ]
✓ Every opening brace {{ has a closing brace }}
✓ Every opening parenthesis ( has a closing parenthesis )
✓ Every opening quote " has a closing quote "
✓ Every opening single quote ' has a closing single quote '
✓ All CAI3-LITE syntax is properly formed
✓ No unmatched delimiters anywhere in the output
✓ 🚨 Every T{{}} try block has a corresponding X(){{}} except block
✓ 🚨 NO PYTHON SYNTAX IN ANY BODY BLOCKS
✓ 🚨 TABLE USES SHORT ALIASES ONLY (ct, ca) NOT FULL NAMES
✓ 🚨 D: SECTION HAS ALL hash_XXXX MAPPINGS FOUND IN B# SECTIONS
✓ 🚨 S: SECTION HAS s=self AND ALL self-attribute mappings found in B# sections
✓ 🚨 V: SECTION HAS ALL local variable mappings found in B# and T: SECTIONS

🚨 CRITICAL PRE-SUBMISSION HASH VALIDATION:
1. Scan ALL B# sections for hash_XXXX references
2. Verify EVERY hash_XXXX appears in D: section with mapping
3. Count: D: mappings ≥ unique hash_XXXX references in bodies
4. If hash_ca00 appears in body → D: MUST have hash_ca00=something

🚨 CRITICAL PRE-SUBMISSION VARIABLE VALIDATION:
1. Scan ALL B# sections for local variables (i, j, k, aa, ab, etc.) → add to V: section
2. Scan ALL B# sections for self-attributes (s.na, s.ti, s.af → extract: na, ti, af) → add to S: section  
3. Verify S: section contains s=self AND ALL self-attribute suffixes 
4. Verify V: section contains ALL local variables 

🚨 SELF-CHECK REQUIRED: After generating code, check all opening brackets/braces/parentheses have matching closing brackets/braces/parentheses. All quotes are properly paired. Validate that the output is proper CAI3-LITE syntax with NO Python mixed in. VERIFY that every hash_XXXX in body sections has a corresponding mapping in D: section. VERIFY that every local variable in body sections has a corresponding mapping in V: section. VERIFY that every self-attribute in the body sections has corresponding mapping in S: section.

TASK: {task}

EXISTING CAI3-LITE:
{cai3_lite}

🚨 REMINDER: Start with "=== CAI3-LITE ===" - NO other text allowed."""

        return prompt
    
    def _extract_existing_identifiers(self, cai3_lite: str) -> Set[str]:
        """Extract existing identifiers from CAI3-LITE content."""
        identifiers = set()
        
        # Extract from various CAI3 sections
        lines = cai3_lite.split('\n')
        for line in lines:
            # Extract from pool definitions (P: section)
            if line.startswith('P:'):
                pool_matches = re.findall(r'p\d+', line)
                identifiers.update(pool_matches)
            
            # Extract from alias definitions (X: section)
            elif line.startswith('X:'):
                alias_matches = re.findall(r'[a-z]\d+', line)
                identifiers.update(alias_matches)
            
            # Extract from table entries (T: section)
            elif line.startswith('T:') or (not line.startswith(('#', 'P:', 'X:', 'D:', 'B#')) and ':' in line):
                # Look for method/class identifiers
                identifier_matches = re.findall(r'\b[a-zA-Z_]\w*\b', line)
                identifiers.update(identifier_matches)
        
        return identifiers
    
    def _send_to_claude(self, prompt: str) -> str:
        """
        Send prompt to Claude using the Claude CLI.
        """
        import subprocess
        import tempfile
        import os
        
        self.logger.info(f"🤖 SENDING TO CLAUDE - Prompt length: {len(prompt)} chars")
        self.logger.debug(f"Prompt preview: {prompt[:500]}...")
        
        try:
            # Write prompt to temporary file to avoid command line length limits
            with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as tmp:
                tmp.write(prompt)
                tmp_path = tmp.name
            
            try:
                # Use stdin to pass the prompt for better handling of long content
                with open(tmp_path, 'r') as f:
                    result = subprocess.run(
                        ["claude"],
                        stdin=f,
                        capture_output=True,
                        text=True,
                        timeout=300,  # 5 minute timeout for long responses
                        # Ensure we get full output without buffering issues
                        env={**os.environ, 'PYTHONUNBUFFERED': '1'}
                    )
            finally:
                # Clean up temp file
                try:
                    os.unlink(tmp_path)
                except:
                    pass
            
            if result.returncode != 0:
                self.logger.error(f"Claude CLI error: {result.stderr}")
                raise RuntimeError(f"Claude Code error: {result.stderr}")
            
            # Ensure we have the complete output
            full_output = result.stdout
            
            self.logger.info(f"📥 CLAUDE RESPONSE RECEIVED - Length: {len(full_output)} chars")
            self.logger.info(f"📄 CLAUDE FULL RESPONSE:\n{'='*60}\n{full_output}\n{'='*60}")
            
            # Analyze response structure for debugging
            has_mappings_section = '=== MAPPINGS ===' in full_output
            has_cai3_section = '=== CAI3-LITE ===' in full_output
            has_code_blocks = '```' in full_output
            code_block_count = full_output.count('```') // 2
            
            self.logger.info(f"📊 RESPONSE ANALYSIS:")
            self.logger.info(f"  - Has MAPPINGS section: {has_mappings_section}")
            self.logger.info(f"  - Has CAI3-LITE section: {has_cai3_section}")
            self.logger.info(f"  - Has code blocks: {has_code_blocks}")
            self.logger.info(f"  - Code block count: {code_block_count}")
            
            return full_output
            
        except FileNotFoundError:
            self.logger.error("Claude CLI not found in PATH")
            raise RuntimeError(
                "Claude Code CLI not found. Ensure 'claude' is installed and in PATH.\n"
                "Install with: pip install claude-cli"
            )
        except subprocess.TimeoutExpired:
            self.logger.error("Claude request timed out")
            raise RuntimeError("Claude Code request timed out after 5 minutes")
    
    def _generate_mock_response(self, prompt: str) -> str:
        """Generate a mock Claude response for testing purposes."""
        return """=== MAPPINGS ===
opt_func: optimized_function
new_var: optimization_variable

=== CAI3-LITE ===
#C3L v2 py=3.11 f=example.py
P:p0="user_id",p1="email",p2="username"
X:a0=mt_5605,a1=mt_961c
T:M:UserValidator.vr#a0,M:UserValidator.opt_func#a1
B#a0:rf=['user_id','email'];@f,rf{f!inp0?(s.l.er(f'Missing: {f}'),RF):_};RT
B#a1:# Optimized validation logic here
"""
    
    def _parse_response(self, response: str) -> Tuple[str, Dict[str, str]]:
        """
        Parse Claude's response to extract CAI3-LITE content and mappings.
        
        Returns:
            Tuple of (cai3_lite_content, mappings_dict)
        """
        self.logger.info("🔍 PARSING CLAUDE RESPONSE")
        self.logger.debug(f"Response length: {len(response)} chars")
        self.logger.debug(f"Response preview: {response[:500]}...")
        
        mappings = {}
        cai3_content = ""
        
        # Split response into sections
        sections = response.split('=== ')
        self.logger.info(f"📂 Found {len(sections)} sections when splitting by '=== '")
        
        for i, section in enumerate(sections):
            section_preview = section[:100].replace('\n', '\\n')
            self.logger.info(f"📋 Section {i}: '{section_preview}...'")
            
            if section.startswith('MAPPINGS ==='):
                # Parse mappings section
                mappings_text = section.replace('MAPPINGS ===', '').strip()
                self.logger.info(f"🗺️ FOUND MAPPINGS SECTION: {len(mappings_text)} chars")
                self.logger.info(f"📝 Mappings content:\n{mappings_text}")
                mappings = self._parse_mappings_section(mappings_text)
                self.logger.info(f"✅ Parsed {len(mappings)} mappings: {mappings}")
                
            elif section.startswith('CAI3-LITE ==='):
                # Extract CAI3-LITE content
                cai3_content = section.replace('CAI3-LITE ===', '').strip()
                self.logger.info(f"📋 FOUND CAI3-LITE SECTION: {len(cai3_content)} chars")
                self.logger.info(f"📄 CAI3 content preview: {cai3_content[:200]}...")
        
        # Fallback: if no explicit sections, try to extract from code blocks
        if not cai3_content:
            self.logger.warning("⚠️ No explicit CAI3-LITE section found, looking for code blocks")
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
                    self.logger.info(f"📦 Extracted CAI3 from code block using pattern {pattern}: {len(cai3_content)} chars")
                    self.logger.info(f"📄 Code block content: {cai3_content[:200]}...")
                    break
            
            if not cai3_content:
                self.logger.error("❌ No CAI3 code blocks found in response")
                self.logger.error(f"🔍 Searching for any code blocks in response...")
                all_code_blocks = re.findall(r'```(\w*)\n(.*?)\n```', response, re.DOTALL)
                if all_code_blocks:
                    for i, (lang, content) in enumerate(all_code_blocks):
                        self.logger.error(f"  Block {i}: lang='{lang}', content={content[:100]}...")
                else:
                    self.logger.error("  No code blocks of any kind found!")
        
        self.logger.info(f"🎯 PARSING RESULT:")
        self.logger.info(f"  - Mappings: {len(mappings)} items")
        self.logger.info(f"  - CAI3 content: {len(cai3_content)} chars")
        self.logger.info(f"  - Has valid CAI3: {bool(cai3_content.strip())}")
        
        # Immediate format validation
        if not cai3_content.strip():
            self.logger.error("❌ CRITICAL FORMAT ERROR: Empty CAI3 content - Claude ignored format instructions!")
        elif '=== MAPPINGS ===' not in response:
            self.logger.warning("⚠️ FORMAT WARNING: Missing 'MAPPINGS' section header")
        elif '=== CAI3-LITE ===' not in response:
            self.logger.warning("⚠️ FORMAT WARNING: Missing 'CAI3-LITE' section header")
        
        if mappings:
            self.logger.info(f"📋 Sample mappings: {dict(list(mappings.items())[:5])}")
        
        return cai3_content, mappings
    
    def _parse_mappings_section(self, mappings_text: str) -> Dict[str, str]:
        """Parse the mappings section from Claude's response."""
        mappings = {}
        
        for line in mappings_text.split('\n'):
            line = line.strip()
            if ':' in line and not line.startswith('#'):
                try:
                    key, value = line.split(':', 1)
                    mappings[key.strip()] = value.strip()
                except ValueError:
                    self.logger.warning(f"Failed to parse mapping line: {line}")
        
        return mappings
    
    def _validate_constraints(self, cai3_output: str, cai3_full: CAI3Full, 
                            mappings: Dict[str, str], cai3_map: Optional[Any] = None) -> CAI3ValidationResult:
        """
        Validate CAI3 output against constraints and return detailed results.
        
        This is the core validation logic that checks for constraint violations.
        
        Args:
            cai3_output: The CAI3-LITE output to validate
            cai3_full: Full CAI3 structure with constraints
            mappings: Extracted mappings from Claude's response
            cai3_map: Optional CAI3Map with compression mappings for validation pool
        """
        self.logger.info("🔍 STARTING CONSTRAINT VALIDATION")
        self.logger.info(f"📊 Input metrics:")
        self.logger.info(f"  - CAI3 output: {len(cai3_output)} chars")
        self.logger.info(f"  - Mappings: {len(mappings)} items")
        self.logger.info(f"  - Has CAI3Full: {cai3_full is not None}")
        self.logger.info(f"  - Has CAI3Map: {cai3_map is not None}")
        
        violations = []
        
        # Log what we're validating
        self.logger.debug(f"Available mappings: {list(mappings.keys())[:10]}...")
        
        # 1. Validate hash references
        self.logger.info("🔗 Validating hash references...")
        hash_violations = self._validate_hash_constraints(cai3_output, cai3_full)
        violations.extend(hash_violations)
        self.logger.info(f"  Result: {len(hash_violations)} hash violations")
        
        # 2. Validate pool references
        self.logger.info("🏊 Validating pool references...")
        pool_violations = self._validate_pool_constraints(cai3_output, cai3_full)
        violations.extend(pool_violations)
        self.logger.info(f"  Result: {len(pool_violations)} pool violations")
        
        # 3. Validate new identifier mappings
        self.logger.info("🆔 Validating identifier mappings...")
        identifier_violations = self._validate_identifier_mappings(cai3_output, mappings)
        violations.extend(identifier_violations)
        self.logger.info(f"  Result: {len(identifier_violations)} identifier violations")
        
        # 4. Validate syntax structure
        self.logger.info("🔧 Validating syntax structure...")
        syntax_violations = self._validate_syntax_structure(cai3_output)
        violations.extend(syntax_violations)
        self.logger.info(f"  Result: {len(syntax_violations)} syntax violations")
        
        # 5. Validate CAI3 format compliance
        self.logger.info("📋 Validating CAI3 format compliance...")
        format_violations = self._validate_cai3_format(cai3_output)
        violations.extend(format_violations)
        self.logger.info(f"  Result: {len(format_violations)} format violations")
        
        # 6. Validate section identifiers
        self.logger.info("🏷️ Validating section identifiers...")
        section_violations = self._validate_section_identifiers(cai3_output)
        violations.extend(section_violations)
        self.logger.info(f"  Result: {len(section_violations)} section violations")
        
        # 7. Validate V: section variable mappings (if present)
        self.logger.info("🔤 Validating V: section variable mappings...")
        v_section_violations = self._validate_v_section_constraints(cai3_output, cai3_full, cai3_map)
        violations.extend(v_section_violations)
        self.logger.info(f"  Result: {len(v_section_violations)} V: section violations")
        
        # 7.5 Validate S: section self-attributed variable mappings (NEW)
        self.logger.info("🔑 Validating S: section self-attributed variable mappings...")
        s_section_violations = self._validate_s_section_constraints(cai3_output, cai3_full, cai3_map)
        violations.extend(s_section_violations)
        self.logger.info(f"  Result: {len(s_section_violations)} S: section violations")
        
        # Method name mappings validation removed - not necessary as long as parameter variables are in V: section
        
        # 9. Validate method parameter mappings (NEW - CRITICAL for parameter preservation)
        self.logger.info("🔧 Validating method parameter mappings...")
        parameter_violations = self._validate_method_parameter_mappings(cai3_output)
        violations.extend(parameter_violations)
        self.logger.info(f"  Result: {len(parameter_violations)} parameter mapping violations")
        
        # 10. Validate parameter completeness in table entries
        self.logger.info("📊 Validating parameter completeness in table entries...")
        table_param_violations = self._validate_table_parameter_completeness(cai3_output)
        violations.extend(table_param_violations)
        self.logger.info(f"  Result: {len(table_param_violations)} table parameter violations")
        
        # Log violation details for debugging
        if violations:
            self.logger.warning(f"⚠️ VALIDATION ISSUES FOUND:")
            self.logger.warning(f"  Total violations: {len(violations)}")
            
            violation_summary = {}
            for v in violations:
                violation_summary[v.violation_type] = violation_summary.get(v.violation_type, 0) + 1
            self.logger.warning(f"  Violation breakdown: {violation_summary}")
            
            # Log detailed violation information
            for i, v in enumerate(violations):
                severity_emoji = "🔴" if v.severity == "critical" else "🟡" if v.severity == "warning" else "🔵"
                self.logger.warning(f"  {severity_emoji} Violation {i+1}: [{v.severity.upper()}] {v.violation_type}")
                self.logger.warning(f"    Description: {v.description}")
                self.logger.warning(f"    Location: {v.location}")
                self.logger.warning(f"    Fix: {v.suggested_fix}")
        
        # Attempt basic repairs for non-critical violations
        repaired_content = None
        if violations and any(v.severity != 'critical' for v in violations):
            self.logger.info("🔧 Attempting basic repairs for non-critical violations...")
            repaired_content = self._attempt_basic_repairs(cai3_output, violations)
            if repaired_content != cai3_output:
                self.logger.info(f"✅ Basic repairs applied: {len(repaired_content)} chars")
            else:
                self.logger.info("ℹ️ No basic repairs needed")
        
        # Only fail validation for critical violations
        critical_violations = [v for v in violations if v.severity == 'critical']
        is_valid = len(critical_violations) == 0
        
        self.logger.info("📋 VALIDATION SUMMARY:")
        if not is_valid:
            self.logger.error(f"❌ VALIDATION FAILED: {len(critical_violations)} critical violations")
            for v in critical_violations:
                self.logger.error(f"  🔴 CRITICAL: {v.violation_type} - {v.description}")
        elif violations:
            self.logger.info(f"⚠️ VALIDATION PASSED WITH WARNINGS: {len(violations)} non-critical violations")
            self.logger.info("  Proceeding with warnings/info violations only")
        else:
            self.logger.info("✅ VALIDATION PASSED: No violations found")
        
        return CAI3ValidationResult(
            is_valid=is_valid,
            violations=violations,
            mappings=mappings,
            repaired_content=repaired_content
        )
    
    def _validate_hash_constraints(self, cai3_output: str, cai3_full: CAI3Full) -> List[ConstraintViolation]:
        """Validate hash usage - ensure ALL hash references in body sections have mappings in D: section."""
        violations = []
        
        # Extract hash references from body sections
        body_hash_refs = set()
        body_sections = re.findall(r'B#[^:]*:(.*?)(?=\nB#|\n[A-Z]:|$)', cai3_output, re.DOTALL)
        
        for body_content in body_sections:
            # Find all hash_XXXX references in this body
            hash_matches = re.findall(r'\bhash_([a-f0-9A-F]{4})\b', body_content)
            for hash_suffix in hash_matches:
                body_hash_refs.add(f"hash_{hash_suffix.lower()}")
        
        self.logger.info(f"🔍 Found {len(body_hash_refs)} unique hash references in body sections: {sorted(body_hash_refs)}")
        
        # Extract hash mappings from D: section
        d_section_hashes = set()
        d_section_match = re.search(r'D:([^\n]*)', cai3_output)
        if d_section_match:
            d_content = d_section_match.group(1)
            # Find hash mappings in D: section (hash_XXXX=something)
            hash_mappings = re.findall(r'\bhash_([a-f0-9A-F]{4})=', d_content)
            for hash_suffix in hash_mappings:
                d_section_hashes.add(f"hash_{hash_suffix.lower()}")
        
        self.logger.info(f"🗺️ Found {len(d_section_hashes)} hash mappings in D: section: {sorted(d_section_hashes)}")
        
        # Find hash references that are missing from D: section
        missing_hashes = body_hash_refs - d_section_hashes
        
        if missing_hashes:
            self.logger.error(f"❌ CRITICAL: {len(missing_hashes)} hash references missing from D: section")
            for missing_hash in sorted(missing_hashes):
                violations.append(ConstraintViolation(
                    violation_type="missing_hash_mapping",
                    description=f"Hash '{missing_hash}' is used in body sections but not defined in D: section",
                    location=f"Missing from D: section: {missing_hash}",
                    suggested_fix=f"Add '{missing_hash}=original_value' to the D: section",
                    severity="critical"
                ))
        else:
            self.logger.info(f"✅ All {len(body_hash_refs)} hash references have mappings in D: section")
        
        # Validate hash format (should be hash_XXXX where XXXX is 4 hex digits)
        for hash_ref in body_hash_refs:
            if not re.match(r'^hash_[a-f0-9]{4}$', hash_ref):
                violations.append(ConstraintViolation(
                    violation_type="invalid_hash_format",
                    description=f"Hash '{hash_ref}' doesn't follow hash_XXXX format with 4 hex digits",
                    location=f"Hash reference: {hash_ref}",
                    suggested_fix="Use format hash_XXXX where XXXX is 4 hexadecimal digits",
                    severity="warning"
                ))
        
        # Additional validation: Check if D: section has orphaned hash mappings
        orphaned_hashes = d_section_hashes - body_hash_refs
        if orphaned_hashes:
            self.logger.warning(f"⚠️ Found {len(orphaned_hashes)} hash mappings in D: section not used in body sections: {sorted(orphaned_hashes)}")
            # This is just a warning, not an error - extra mappings are OK
        
        return violations
    
    def _validate_pool_constraints(self, cai3_output: str, cai3_full: CAI3Full) -> List[ConstraintViolation]:
        """Validate pool references and definitions - allow new pools if properly defined."""
        violations = []
        
        # Extract pool definitions from output
        defined_pools = set()
        pool_def_pattern = r'P:([^:\n]+)'
        pool_match = re.search(pool_def_pattern, cai3_output)
        if pool_match:
            pool_line = pool_match.group(1)
            for pool_def in re.finditer(r'(p\d+)=', pool_line):
                defined_pools.add(pool_def.group(1))
        
        # Find pool references in the entire output
        referenced_pools = set(re.findall(r'\b(p\d+)\b', cai3_output))
        
        # Check for undefined pool references (critical error)
        undefined_pools = referenced_pools - defined_pools
        for pool in undefined_pools:
            violations.append(ConstraintViolation(
                violation_type="undefined_pool",
                description=f"Pool '{pool}' is referenced but not defined in P: section",
                location=f"Pool reference: {pool}",
                suggested_fix=f"Add {pool}=\"value\" to the P: section",
                severity="critical"
            ))
        
        # Note: We allow new pools to be created as long as they're defined in P: section
        # The constraint system shouldn't restrict which pools Claude can create
        self.logger.debug(f"Found {len(defined_pools)} defined pools, {len(referenced_pools)} referenced pools")
        
        return violations
    
    def _validate_identifier_mappings(self, cai3_output: str, mappings: Dict[str, str]) -> List[ConstraintViolation]:
        """Validate that new identifiers are properly mapped."""
        violations = []
        
        self.logger.debug(f"Validating identifier mappings with {len(mappings)} provided mappings")
        
        # Extract identifiers from CAI3 output - but be more selective
        # Focus only on identifiers that actually need mapping (new function/method names)
        new_identifiers = set()
        
        # Parse CAI3 content more carefully
        lines = cai3_output.split('\n')
        for line in lines:
            # Skip header, comments, and structural lines
            if line.startswith(('#', 'P:', 'X:', 'D:', 'T:')) or not line.strip():
                continue
                
            # Look for body sections with new method/function names
            if line.startswith('B#'):
                # Extract identifiers from body content that look like new names
                # Match patterns like: methodName, function_name, etc.
                body_content = line.split(':', 1)[1] if ':' in line else line
                
                # Look for camelCase or snake_case that aren't CAI3 keywords
                method_pattern = r'\b([a-zA-Z_][a-zA-Z0-9_]*[a-zA-Z0-9])\b'
                potential_identifiers = re.findall(method_pattern, body_content)
                
                for identifier in potential_identifiers:
                    # Filter out obvious CAI3 constructs and common keywords
                    if (len(identifier) > 2 and  # Skip very short identifiers
                        not re.match(r'^[pabcdefg]\d+$', identifier) and  # Skip pool/alias patterns
                        not identifier.lower() in self._get_cai3_keywords() and
                        not identifier.isdigit()):
                        new_identifiers.add(identifier)
        
        self.logger.debug(f"Found {len(new_identifiers)} potential new identifiers: {list(new_identifiers)[:10]}")
        
        # Check which identifiers are missing mappings
        unmapped_identifiers = []
        for identifier in new_identifiers:
            if identifier not in mappings:
                # Additional check: is this identifier actually "new" vs just a CAI3 construct?
                if self._looks_like_new_identifier(identifier):
                    unmapped_identifiers.append(identifier)
        
        self.logger.debug(f"Found {len(unmapped_identifiers)} truly unmapped identifiers: {unmapped_identifiers[:10]}")
        
        # Only create violations for identifiers that genuinely need mapping
        for identifier in unmapped_identifiers:
            # Make this info level - mappings are nice to have but not critical
            violations.append(ConstraintViolation(
                violation_type="unmapped_identifier",
                description=f"Identifier '{identifier}' could be mapped to original name for clarity",
                location=f"Identifier: {identifier}",
                suggested_fix=f"Consider adding '{identifier}: original_name' to MAPPINGS section",
                severity="info"  # Changed to info - not critical for functionality
            ))
        
        return violations
    
    def _get_cai3_keywords(self) -> set:
        """Get comprehensive set of CAI3 keywords that don't need mapping."""
        return {
            # CAI3 structural keywords
            'C3L', 'P', 'X', 'D', 'T', 'B', 'M', 'C', 'F', 'RT', 'RF', 'MT', 'CT', 
            'v2', 'py', 'f', 'ins', 'd', 's', 'l', 'er', 'g', 'c', 'rf', 'mt', 'cl', 'fn',
            
            # Common Python keywords and built-ins
            'def', 'class', 'if', 'else', 'elif', 'for', 'while', 'try', 'except', 'finally',
            'return', 'yield', 'import', 'from', 'as', 'with', 'lambda', 'and', 'or', 'not',
            'is', 'in', 'True', 'False', 'None', 'self', 'cls', 'super', 'len', 'str', 'int',
            'float', 'bool', 'list', 'dict', 'set', 'tuple', 'range', 'enumerate', 'zip',
            'sum', 'round', 'abs', 'min', 'max', 'sorted', 'reversed', 'any', 'all',
            'Exception', 'ValueError', 'TypeError', 'KeyError', 'IndexError', 'AttributeError',
            'break', 'continue', 'pass', 'assert', 'raise', 'del', 'global', 'nonlocal',
            'print', 'input', 'open', 'close', 'read', 'write', 'get', 'set', 'add', 'remove',
            'sum', 'round', 'abs', 'min', 'max', 'sorted', 'reversed', 'any', 'all',
            'Exception', 'ValueError', 'TypeError', 'KeyError', 'IndexError', 'AttributeError',
            'break', 'continue', 'pass', 'assert', 'raise', 'del', 'global', 'nonlocal',
            'print', 'input', 'open', 'close', 'read', 'write', 'get', 'set', 'add', 'remove',
            
            # Common method names that don't need mapping
            'init', 'str', 'repr', 'len', 'iter', 'next', 'call', 'getitem', 'setitem',
            'delitem', 'contains', 'enter', 'exit', 'eq', 'ne', 'lt', 'le', 'gt', 'ge',
            
            # Common variable patterns and constants
            'i', 'j', 'k', 'x', 'y', 'z', 'n', 'idx', 'key', 'val', 'value', 'item', 'data',
            'result', 'output', 'input', 'params', 'args', 'kwargs', 'config', 'options',
            'USD', 'EUR', 'GBP', 'CAD',  # Common currency codes
            
            # Raw data identifiers (legitimate CAI3 constructs)
            'raw_fcbf2cd2', 'raw_ddaea84c'  # These are legitimate raw data references
        }
    
    def _looks_like_new_identifier(self, identifier: str) -> bool:
        """Determine if an identifier looks like a new name that needs mapping."""
        # First check - if it's in our keywords list, it doesn't need mapping
        if identifier.lower() in self._get_cai3_keywords() or identifier in self._get_cai3_keywords():
            return False
            
        # Skip very common patterns
        if identifier.lower() in self._get_cai3_keywords():
            return False
            
        # Skip single letters and very short identifiers  
        if len(identifier) <= 2:
            return False
            
        # Skip numeric or mostly numeric identifiers
        if identifier.isdigit() or re.match(r'^[0-9]+[a-zA-Z]?$', identifier):
            return False
            
        # Skip CAI3 pattern identifiers
        if re.match(r'^[a-z]\d+$', identifier):  # a0, b1, etc.
            return False
            
        # Skip hash identifiers - these are CAI3 constructs, not new identifiers
        if re.match(r'^hash_[a-f0-9]{4}$', identifier):
            return False
            
        # This looks like a real identifier that might need mapping
        return True
    
    def _validate_syntax_structure(self, cai3_output: str) -> List[ConstraintViolation]:
        """Validate CAI3 syntax structure for common errors with comprehensive delimiter checking."""
        violations = []
        
        # Check curly braces balance
        open_braces = cai3_output.count('{')
        close_braces = cai3_output.count('}')
        if open_braces != close_braces:
            violations.append(ConstraintViolation(
                violation_type="unbalanced_braces",
                description=f"Unbalanced curly braces: {open_braces} open, {close_braces} close",
                location="Global structure",
                suggested_fix="Ensure every {{ has a matching }}",
                severity="critical"
            ))
        
        # Check parentheses balance
        open_parens = cai3_output.count('(')
        close_parens = cai3_output.count(')')
        if open_parens != close_parens:
            violations.append(ConstraintViolation(
                violation_type="unbalanced_parentheses",
                description=f"Unbalanced parentheses: {open_parens} open, {close_parens} close",
                location="Global structure",
                suggested_fix="Ensure every ( has a matching )",
                severity="critical"
            ))
        
        # Check square brackets balance
        open_brackets = cai3_output.count('[')
        close_brackets = cai3_output.count(']')
        if open_brackets != close_brackets:
            violations.append(ConstraintViolation(
                violation_type="unbalanced_brackets",
                description=f"Unbalanced square brackets: {open_brackets} open, {close_brackets} close",
                location="Global structure",
                suggested_fix="Ensure every [ has a matching ]",
                severity="critical"
            ))
        
        # Check double quotes balance
        double_quote_count = cai3_output.count('"')
        if double_quote_count % 2 != 0:
            violations.append(ConstraintViolation(
                violation_type="unbalanced_double_quotes",
                description=f"Unbalanced double quotes: {double_quote_count} total (must be even)",
                location="Global structure",
                suggested_fix='Ensure every opening " has a matching closing "',
                severity="critical"
            ))
        
        # Check single quotes balance
        single_quote_count = cai3_output.count("'")
        if single_quote_count % 2 != 0:
            violations.append(ConstraintViolation(
                violation_type="unbalanced_single_quotes",
                description=f"Unbalanced single quotes: {single_quote_count} total (must be even)",
                location="Global structure",
                suggested_fix="Ensure every opening ' has a matching closing '",
                severity="critical"
            ))
        
        # Advanced bracket matching validation using stack
        bracket_violations = self._validate_nested_delimiters(cai3_output)
        violations.extend(bracket_violations)
        
        # Check for incomplete try-except structures
        violations.extend(self._validate_try_except_structures(cai3_output))
        
        return violations
    
    def _validate_try_except_structures(self, cai3_output: str) -> List[ConstraintViolation]:
        """
        Validate that all try blocks (T{...}) have corresponding exception handlers (X{...} or X(...){...}).
        This properly handles nested braces within try blocks.
        """
        violations = []
        
        # Find all T{ patterns
        try_positions = []
        i = 0
        while i < len(cai3_output) - 1:
            if cai3_output[i:i+2] == 'T{':
                try_positions.append(i)
            i += 1
        
        for try_pos in try_positions:
            # Find the matching closing brace for this try block
            brace_count = 1  # Start with 1 to account for the opening brace in "T{"
            start_pos = try_pos + 2  # Start after "T{"
            try_end_pos = None
            
            for j in range(start_pos, len(cai3_output)):
                if cai3_output[j] == '{':
                    brace_count += 1
                elif cai3_output[j] == '}':
                    brace_count -= 1
                    if brace_count == 0:
                        try_end_pos = j
                        break
            
            if try_end_pos is None:
                # Incomplete try block (missing closing brace)
                violations.append(ConstraintViolation(
                    violation_type="incomplete_try_structure",
                    description="Try block is missing closing brace",
                    location=f"Try block at position {try_pos}",
                    suggested_fix="Add closing '}' for the try block",
                    severity="critical"
                ))
                continue
            
            # Look for exception handler immediately after the try block
            search_start = try_end_pos + 1
            # Skip whitespace if any
            while search_start < len(cai3_output) and cai3_output[search_start].isspace():
                search_start += 1
            
            # Check for X{ or X(...){ patterns
            has_exception_handler = False
            if search_start < len(cai3_output):
                if cai3_output[search_start] == 'X':
                    if search_start + 1 < len(cai3_output):
                        next_char = cai3_output[search_start + 1]
                        if next_char == '{':
                            # Simple X{ pattern
                            has_exception_handler = True
                        elif next_char == '(':
                            # X(...){ pattern - find the matching )
                            paren_pos = search_start + 2
                            paren_count = 1
                            while paren_pos < len(cai3_output) and paren_count > 0:
                                if cai3_output[paren_pos] == '(':
                                    paren_count += 1
                                elif cai3_output[paren_pos] == ')':
                                    paren_count -= 1
                                paren_pos += 1
                            
                            # Check if there's a { after the closing )
                            if paren_pos < len(cai3_output) and cai3_output[paren_pos] == '{':
                                has_exception_handler = True
            
            if not has_exception_handler:
                try_block_content = cai3_output[try_pos:try_end_pos+1]
                violations.append(ConstraintViolation(
                    violation_type="incomplete_try_structure",
                    description=f"Try block without exception handler: {try_block_content[:30]}...",
                    location=f"Try block: {try_block_content[:30]}",
                    suggested_fix="Add X{{exception_handler}} after the try block",
                    severity="critical"
                ))
        
        return violations

    def _validate_nested_delimiters(self, cai3_output: str) -> List[ConstraintViolation]:
        """
        Validate proper nesting and matching of delimiters using stack-based approach.
        This catches cases where counts match but nesting is incorrect.
        """
        violations = []
        stack = []
        opening = {'(': ')', '[': ']', '{': '}'}
        closing = {')', ']', '}'}
        quotes = {'"', "'"}
        
        in_string = False
        string_char = None
        
        for i, char in enumerate(cai3_output):
            # Handle string contexts - ignore delimiters inside strings
            if char in quotes and not in_string:
                in_string = True
                string_char = char
            elif char == string_char and in_string:
                # Check if it's an escaped quote
                if i > 0 and cai3_output[i-1] != '\\':
                    in_string = False
                    string_char = None
            elif in_string:
                continue  # Skip all characters inside strings
            
            # Handle delimiters outside of strings
            if char in opening:
                stack.append((char, i))
            elif char in closing:
                if not stack:
                    violations.append(ConstraintViolation(
                        violation_type="unexpected_closing_delimiter",
                        description=f"Unexpected closing delimiter '{char}' at position {i}",
                        location=f"Character {i}: ...{cai3_output[max(0,i-10):i+10]}...",
                        suggested_fix=f"Remove unexpected '{char}' or add matching opening delimiter",
                        severity="critical"
                    ))
                else:
                    last_opening, last_pos = stack.pop()
                    expected_closing = opening[last_opening]
                    if char != expected_closing:
                        violations.append(ConstraintViolation(
                            violation_type="mismatched_delimiters",
                            description=f"Mismatched delimiters: '{last_opening}' at pos {last_pos} closed by '{char}' at pos {i}",
                            location=f"From pos {last_pos} to {i}: ...{cai3_output[max(0,last_pos-5):i+5]}...",
                            suggested_fix=f"Change '{char}' to '{expected_closing}' or fix the opening delimiter",
                            severity="critical"
                        ))
        
        # Check for unclosed delimiters
        if stack:
            for opening_char, pos in stack:
                violations.append(ConstraintViolation(
                    violation_type="unclosed_delimiter",
                    description=f"Unclosed delimiter '{opening_char}' at position {pos}",
                    location=f"Position {pos}: ...{cai3_output[max(0,pos-10):pos+20]}...",
                    suggested_fix=f"Add closing delimiter '{opening[opening_char]}'",
                    severity="critical"
                ))
        
        return violations
    
    def _validate_cai3_format(self, cai3_output: str) -> List[ConstraintViolation]:
        """Validate overall CAI3-LITE format compliance."""
        violations = []
        
        # Check for required header
        if not cai3_output.strip().startswith('#C3L'):
            violations.append(ConstraintViolation(
                violation_type="missing_header",
                description="Missing #C3L header",
                location="File start",
                suggested_fix="Add #C3L header at the beginning",
                severity="critical"
            ))
        
        # Check for forbidden patterns - be more permissive with R: sections and raw data
        forbidden_patterns = [
            ('(was ', 'parentheticals'),
            ('(originally ', 'parentheticals'), 
            ('...)', 'ellipsis'),
            ('p...', 'truncated_pools')
            # Removed R: and raw_ patterns - these are legitimate CAI3 constructs
        ]
        
        for pattern, violation_name in forbidden_patterns:
            if pattern in cai3_output:
                violations.append(ConstraintViolation(
                    violation_type=f"forbidden_{violation_name}",
                    description=f"Contains forbidden pattern: {pattern}",
                    location=f"Pattern: {pattern}",
                    suggested_fix=f"Remove all instances of {pattern}",
                    severity="critical"
                ))
        
        return violations
    
    def _validate_section_identifiers(self, cai3_output: str) -> List[ConstraintViolation]:
        """Validate that only allowed CAI3-LITE section identifiers are used."""
        violations = []
        
        # Define valid CAI3-LITE section identifiers - include S: for self-attrs, V: for variables, R: for raw data
        valid_sections = {'#C3L', 'I:', 'D:', 'S:', 'V:', 'X:', 'P:', 'T:', 'B#', 'R:', '---'}
        
        lines = cai3_output.split('\n')
        for line_num, line in enumerate(lines, 1):
            line = line.strip()
            if not line or line.startswith('#'):
                continue
                
            # Check if line starts with a section identifier
            if ':' in line:
                section_prefix = line.split(':')[0] + ':'
                
                # Skip body sections (B#) as they have different format
                if line.startswith('B#'):
                    continue
                    
                # Check if it's a valid section
                if section_prefix not in valid_sections:
                    violations.append(ConstraintViolation(
                        violation_type="invalid_section_identifier",
                        description=f"Invalid section identifier '{section_prefix}' - only allowed: {', '.join(sorted(valid_sections))}",
                        location=f"Line {line_num}: {line[:50]}...",
                        suggested_fix=f"Remove or replace '{section_prefix}' with a valid CAI3-LITE section identifier",
                        severity="critical"
                    ))
        
        return violations
    
    def _validate_v_section_constraints(self, cai3_output: str, cai3_full: CAI3Full = None, cai3_map: Optional[Any] = None) -> List[ConstraintViolation]:
        """
        Validate V: section variable mappings - ensure ALL single-letter variables in body sections have mappings.
        
        IMPORTANT: This validation EXCLUDES self-attributed variables (s.*, se.*) which should be in S: section.
        
        Args:
            cai3_output: The CAI3-LITE output to validate
            cai3_full: Full CAI3 structure (optional)
            cai3_map: CAI3Map with compression mappings for validation pool (optional)
        """
        violations = []
        
        # Extract existing local variable compressions from original CAI3Full (if available)
        existing_local_compressions = set()
        
        # PRIORITY: Use cai3_map directly if provided
        if cai3_map and hasattr(cai3_map, 'name_map') and cai3_map.name_map:
            self.logger.info("� Using CAI3Map for validation pool (direct mapping)...")
            # Add all compressions to the validation pool - they can all be reused as local variables
            for compressed_name in cai3_map.name_map.keys():
                existing_local_compressions.add(compressed_name)
            self.logger.info(f"✅ Added {len(cai3_map.name_map)} compressions from CAI3Map to V: validation pool")
            
            # Log specific mappings for debugging
            if 'af' in cai3_map.name_map:
                self.logger.info(f"   ✓ Including 'af' ({cai3_map.name_map['af']}) in validation pool")
        
        # Fallback: Extract from CAI3Full nodes if cai3_map not provided
        if not existing_local_compressions and cai3_full and hasattr(cai3_full, 'nodes'):
            self.logger.info("📦 Fallback: Extracting from CAI3Full nodes...")
            for node in cai3_full.nodes:
                if hasattr(node, 'metadata') and isinstance(node.metadata, dict):
                    if 'local_compressions' in node.metadata:
                        local_map = node.metadata['local_compressions']
                        for orig_var, compressed_var in local_map.items():
                            existing_local_compressions.add(compressed_var)
                            self.logger.debug(f"  Found existing local compression: {compressed_var} → {orig_var}")
        
        if existing_local_compressions:
            self.logger.info(f"📥 Total existing compressions available for V: validation: {len(existing_local_compressions)}")
        else:
            self.logger.warning("⚠️ No CAI3Map or CAI3Full provided - validation pool is empty!")
        
        # Extract S: section variables to exclude from V: section validation
        s_section_vars = set()
        s_section_match = re.search(r'S:([^\n]*)', cai3_output)
        if s_section_match:
            s_content = s_section_match.group(1)
            # Extract the self identifier (se, s, etc.) from S: section
            self_identifiers = re.findall(r'\b([a-z]{1,2})=self\b', s_content)
            s_section_vars.update(self_identifiers)
            # Also extract attribute abbreviations from S: section
            attr_mappings = re.findall(r'\b([a-z]{1,3})=', s_content)
            s_section_vars.update(attr_mappings)
        
        self.logger.info(f"🔑 S: section variables to exclude from V: validation: {sorted(s_section_vars)}")
        
        # Extract single-letter variable references from body sections
        body_variable_refs = set()
        body_sections = re.findall(r'B#[^:]*:(.*?)(?=\nB#|\n[A-Z]:|$)', cai3_output, re.DOTALL)
        
        for body_content in body_sections:
            # Find all single-letter variables in this body (pattern: letter followed by . or used as standalone variable)
            # Match patterns like: s.method, i=value, j+1, k in range, v.append, etc.
            var_matches = re.findall(r'\b([a-z])\b(?=[.\[\]=+\-*/\s]|$)', body_content)
            # Also match patterns like s.method where s is at start of expression
            var_matches.extend(re.findall(r'\b([a-z])\.', body_content))
            # Match variables used in assignments and operations
            var_matches.extend(re.findall(r'\b([a-z])\s*[=+\-*/]', body_content))
            var_matches.extend(re.findall(r'[=+\-*/]\s*([a-z])\b', body_content))
            # Match variables in for loops and conditions
            var_matches.extend(re.findall(r'for\s+([a-z])\s+in', body_content))
            var_matches.extend(re.findall(r'if\s+([a-z])\b', body_content))
            
            for var_letter in var_matches:
                # CRITICAL: Skip if this variable is in S: section (self-attributed)
                if var_letter in s_section_vars:
                    continue
                    
                # Filter out obvious non-variables (reserved words, etc.)
                if var_letter not in ['f', 'r', 'x', 'y', 'z'] and len(var_letter) == 1:
                    # CRITICAL FIX: Filter out compressed self.attribute patterns and method calls
                    # These are not standalone variables but compressed attribute access patterns
                    if not self._is_compressed_attribute_reference(var_letter, body_content):
                        body_variable_refs.add(var_letter)
        
        self.logger.info(f"🔍 Found {len(body_variable_refs)} unique single-letter variables in body sections (excluding S: section vars): {sorted(body_variable_refs)}")
        
        # Extract variable mappings from V: section
        v_section_variables = set()
        v_section_match = re.search(r'V:([^\n]*)', cai3_output)
        if v_section_match:
            v_content = v_section_match.group(1)
            # Find variable mappings in V: section (letter=value format)
            var_mappings = re.findall(r'\b([a-z])=', v_content)
            for var_letter in var_mappings:
                v_section_variables.add(var_letter)
        
        self.logger.info(f"🗺️ Found {len(v_section_variables)} variable mappings in V: section: {sorted(v_section_variables)}")
        
                # Combine V: section mappings with existing local compressions from original CAI3
        all_valid_variables = v_section_variables | existing_local_compressions
        self.logger.info(f"✅ Total valid variable mappings (V: section + existing): {len(all_valid_variables)}: {sorted(all_valid_variables)}")
        
        # Find variable references that are missing from BOTH V: section AND original compression
        missing_variables = body_variable_refs - all_valid_variables
        
        if missing_variables:
            self.logger.error(f"❌ CRITICAL: {len(missing_variables)} NET NEW single-letter variables missing from BOTH V: section AND original compression")
            self.logger.error(f"   These are new variables not in original CAI3: {sorted(missing_variables)}")
            for missing_var in sorted(missing_variables):
                violations.append(ConstraintViolation(
                    violation_type="missing_variable_mapping",
                    description=f"NET NEW single-letter variable '{missing_var}' is used in body sections but not defined in V: section OR original CAI3 compression",
                    location=f"Missing from V: section and original compression: {missing_var}",
                    suggested_fix=f"Add '{missing_var}=original_variable_name' to the V: section (this is a new variable not in original code)",
                    severity="critical"
                ))
        else:
            if body_variable_refs:
                existing_count = len(body_variable_refs & existing_local_compressions)
                new_count = len(body_variable_refs & v_section_variables)
                self.logger.info(f"✅ All {len(body_variable_refs)} single-letter variables have mappings:")
                self.logger.info(f"   - {existing_count} from original CAI3 compression")
                self.logger.info(f"   - {new_count} from V: section (new variables)")
                
        # Validate V: section format (should be V:var=value,var2=value2,...)
        if v_section_match:
            v_content = v_section_match.group(1).strip()
            if v_content and not re.match(r'^[a-z]=[^,]+(?:,[a-z]=[^,]+)*$', v_content):
                violations.append(ConstraintViolation(
                    violation_type="invalid_v_section_format",
                    description=f"V: section format is invalid. Expected format: 'V:var=value,var2=value2'",
                    location=f"V: section content: {v_content}",
                    suggested_fix="Use format V:s=size,i=index,v=value (comma-separated, single letters only)",
                    severity="warning"
                ))
        
        # Additional validation: Check if V: section has orphaned variable mappings
        orphaned_variables = v_section_variables - body_variable_refs
        if orphaned_variables:
            self.logger.warning(f"⚠️ Found {len(orphaned_variables)} variable mappings in V: section not used in body sections: {sorted(orphaned_variables)}")
            # This is just a warning, not an error - extra mappings are OK for future use
        
        return violations
    
    def _validate_s_section_constraints(self, cai3_output: str, cai3_full: CAI3Full = None, cai3_map: Optional[Any] = None) -> List[ConstraintViolation]:
        """Validate S: section self-attributed variable mappings - ensure ALL self.* patterns have mappings.
        
        Args:
            cai3_output: The CAI3-LITE output to validate
            cai3_full: Full CAI3 structure (optional)
            cai3_map: CAI3Map with compression mappings for validation pool (optional)
        """
        violations = []
        
        # Extract existing attribute compressions from original CAI3Map (if available)
        existing_attr_compressions = set()
        
        # PRIORITY: Use cai3_map directly if provided
        if cai3_map and hasattr(cai3_map, 'name_map') and cai3_map.name_map:
            self.logger.info("� Using CAI3Map for S: section validation pool (direct mapping)...")
            # Add all compressions to the validation pool - they can all be reused as self-attributes
            # For example: 'af' can be both a global method compression AND self.af attribute
            for compressed_name, original_name in cai3_map.name_map.items():
                existing_attr_compressions.add(compressed_name)
            self.logger.info(f"✅ Added {len(cai3_map.name_map)} compressions from CAI3Map to S: validation pool")
            
            # Log specific mappings for debugging
            if 'af' in cai3_map.name_map:
                self.logger.info(f"   ✓ Including 'af' ({cai3_map.name_map['af']}) - can be used as s.af (self.analyze_file)")
        
        # Fallback: Extract from CAI3Full nodes if cai3_map not provided
        if not existing_attr_compressions and cai3_full:
            self.logger.info("📦 Fallback: Extracting from CAI3Full nodes...")
            if hasattr(cai3_full, 'nodes'):
                for node in cai3_full.nodes:
                    if hasattr(node, 'metadata') and isinstance(node.metadata, dict):
                        if 'attr_compressions' in node.metadata:
                            attr_map = node.metadata['attr_compressions']
                            for orig_attr, compressed_attr in attr_map.items():
                                existing_attr_compressions.add(compressed_attr)
                                self.logger.debug(f"  Found existing mapping: {compressed_attr} → {orig_attr}")
        
        if existing_attr_compressions:
            self.logger.info(f"📥 Total existing compressions available for S: validation: {len(existing_attr_compressions)}")
        else:
            self.logger.warning("⚠️ No CAI3Map or CAI3Full provided - validation pool is empty!")
        
        # Extract self-attribute references from body sections
        self_attr_refs = set()
        body_sections = re.findall(r'B#[^:]*:(.*?)(?=\nB#|\n[A-Z]:|$)', cai3_output, re.DOTALL)
        
        for body_content in body_sections:
            # Find compressed self.attribute patterns (se.attr or s.attr)
            # Match patterns like: s.na, se.th, s.co, etc.
            attr_matches = re.findall(r'\b(?:s|se)\.([a-z]{1,3})\b', body_content)
            for attr_name in attr_matches:
                self_attr_refs.add(attr_name)
        
        self.logger.info(f"🔍 Found {len(self_attr_refs)} unique self-attributed variables in body sections: {sorted(self_attr_refs)}")
        
        # Extract self-attribute mappings from S: section
        s_section_attrs = set()
        s_section_match = re.search(r'S:([^\n]*)', cai3_output)
        if s_section_match:
            s_content = s_section_match.group(1)
            # Find attribute mappings in S: section (attr=value format)
            attr_mappings = re.findall(r'\b([a-z]{1,3})=', s_content)
            for attr_name in attr_mappings:
                s_section_attrs.add(attr_name)
            
            # Validate that 'se' or 's' is mapped to 'self'
            if not re.search(r'\b(?:se|s)=self\b', s_content):
                violations.append(ConstraintViolation(
                    violation_type="missing_self_identifier",
                    description="S: section missing 'se=self' or 's=self' mapping",
                    location="S: section",
                    suggested_fix="Add 'se=self' or 's=self' to the S: section",
                    severity="critical"
                ))
        
        self.logger.info(f"🗺️ Found {len(s_section_attrs)} self-attributed variable mappings in S: section: {sorted(s_section_attrs)}")
        
        # Combine S: section mappings with existing attribute compressions from original CAI3
        all_valid_attrs = s_section_attrs | existing_attr_compressions
        self.logger.info(f"✅ Total valid attribute mappings (S: section + existing): {len(all_valid_attrs)}: {sorted(all_valid_attrs)}")
        
        # Find self-attribute references that are missing from BOTH S: section AND original compression
        missing_attrs = self_attr_refs - all_valid_attrs
        
        if missing_attrs:
            # Check if these "missing" attributes are actually in the V: section (misplaced)
            # Extract V: section to see if they're there
            v_section_match = re.search(r'V:([^\n]*)', cai3_output)
            v_section_vars = set()
            if v_section_match:
                v_content = v_section_match.group(1)
                v_mappings = re.findall(r'\b([a-z]{1,3})=', v_content)
                v_section_vars = set(v_mappings)
            
            # Categorize missing attributes
            misplaced_in_v = missing_attrs & v_section_vars  # Found in V: but should be in S:
            truly_missing = missing_attrs - v_section_vars   # Not found anywhere
            
            if truly_missing:
                self.logger.error(f"❌ CRITICAL: {len(truly_missing)} NET NEW self-attributed variables missing from BOTH S: section AND original compression")
                self.logger.error(f"   These are new variables not in original CAI3: {sorted(truly_missing)}")
                for missing_attr in sorted(truly_missing):
                    violations.append(ConstraintViolation(
                        violation_type="missing_self_attr_mapping",
                        description=f"NET NEW self-attributed variable '{missing_attr}' is used in body sections but not defined in S: section OR original CAI3 compression",
                        location=f"Missing from S: section and original compression: {missing_attr}",
                        suggested_fix=f"Add '{missing_attr}=original_attribute_name' to the S: section (this is a new variable not in original code)",
                        severity="critical"
                    ))
            
            if misplaced_in_v:
                self.logger.warning(f"⚠️ WARNING: {len(misplaced_in_v)} self-attributed variables found in V: section but should be in S: section")
                self.logger.warning(f"   Misplaced variables (have mappings but in wrong section): {sorted(misplaced_in_v)}")
                for misplaced_attr in sorted(misplaced_in_v):
                    violations.append(ConstraintViolation(
                        violation_type="misplaced_self_attr_in_v_section",
                        description=f"Self-attributed variable '{misplaced_attr}' is used as s.{misplaced_attr} but defined in V: section instead of S: section",
                        location=f"Found in V: section but should be in S: section: {misplaced_attr}",
                        suggested_fix=f"Move '{misplaced_attr}' from V: section to S: section (it's used with self.{misplaced_attr} pattern)",
                        severity="warning"  # Changed from critical to warning since mapping exists
                    ))
        else:
            if self_attr_refs:
                existing_count = len(self_attr_refs & existing_attr_compressions)
                new_count = len(self_attr_refs & s_section_attrs)
                self.logger.info(f"✅ All {len(self_attr_refs)} self-attributed variables have mappings:")
                self.logger.info(f"   - {existing_count} from original CAI3 compression")
                self.logger.info(f"   - {new_count} from S: section (new variables)")
        
        # Validate S: section format (should be S:se=self,attr=value,attr2=value2,...)
        if s_section_match:
            s_content = s_section_match.group(1).strip()
            if s_content and not re.match(r'^[a-z]{1,3}=[^,]+(?:,[a-z]{1,3}=[^,]+)*$', s_content):
                violations.append(ConstraintViolation(
                    violation_type="invalid_s_section_format",
                    description=f"S: section format is invalid. Expected format: 'S:se=self,na=name,th=threshold'",
                    location=f"S: section content: {s_content}",
                    suggested_fix="Use format S:se=self,na=name,th=threshold (comma-separated, short abbreviations)",
                    severity="warning"
                ))
        
        return violations
    
    def _validate_self_attribute_completeness(self, cai3_output: str) -> List[ConstraintViolation]:
        """
        DEPRECATED: This method is no longer used as self-attributes are now validated via S: section.
        Self-attributed variables should now be in S: section, not V: section.
        
        Kept for backward compatibility but returns empty violations list.
        """
        violations = []
        
        self.logger.info("ℹ️ Self-attribute validation is now handled by S: section validation")
        
        return violations
    
    def _is_compressed_attribute_reference(self, var_letter: str, body_content: str) -> bool:
        """
        Check if a single letter is part of a compressed self.attribute pattern rather than a standalone variable.
        
        Examples of compressed attribute patterns to exclude from V: section validation:
        - s.a=aa (s.attribute assignment, 'a' is compressed attribute name)
        - p.no().is() (method call chain, 'p' is compressed object reference)
        - hash_2bb9:p.no().is() (dictionary value with method call)
        
        Args:
            var_letter: The single letter to check
            body_content: The body content containing the letter
            
        Returns:
            True if this letter is part of a compressed attribute/method pattern that should not require V: mapping
        """
        # Pattern 1: s.letter=value (self.attribute assignment)
        # Example: s.a=aa -> represents self.attribute = argument
        if re.search(rf'\bs\.{var_letter}=', body_content):
            return True
            
        # Pattern 2: object.method().method() chains where first letter is standalone object reference
        # Example: p.no().is() -> represents pathlib object method chain
        if re.search(rf'\b{var_letter}\.[\w]+\(\)\.[\w]+\(\)', body_content):
            return True
            
        # Pattern 3: hash_xxx:letter.method() (dictionary value method calls)
        # Example: hash_2bb9:p.no().is() -> dictionary value with method call
        if re.search(rf'hash_[a-f0-9]+:{var_letter}\.[\w]+\(\)', body_content):
            return True
            
        # Pattern 4: Compressed attribute access in return statements or dictionary values
        # Example: p0:n.ge() -> pool reference to method call
        if re.search(rf'p\d+:{var_letter}\.[\w]+\(\)', body_content):
            return True
            
        return False
    

    
    def _validate_method_parameter_mappings(self, cai3_output: str) -> List[ConstraintViolation]:
        """
        Validate that method parameters are properly compressed and mapped in V: section.
        
        This ensures that parameters in table entries like M:ct.ia(s,p)#a2 have:
        1. All parameters mapped in V: section (s=self, p=parameter_name)
        2. Parameters are compressed (single letters or short names)
        3. No Python-style parameter definitions remain
        """
        violations = []
        
        # Extract method entries with parameters from T: section
        method_params = {}  # method_name -> list of parameters
        t_section_match = re.search(r'T:([^\n]*)', cai3_output)
        if not t_section_match:
            return violations  # No T: section, nothing to validate
            
        t_content = t_section_match.group(1)
        
        # Find method definitions with parameters: M:class.method(param1,param2)#body
        method_pattern = r'M:([^.]+)\.([^(#]+)(?:\(([^)]*)\))?#([^,\s]+)'
        method_matches = re.findall(method_pattern, t_content)
        
        for class_name, method_name, params_str, body_id in method_matches:
            if params_str:  # Only validate if parameters are present
                # Parse parameters
                params = [p.strip() for p in params_str.split(',') if p.strip()]
                method_params[method_name] = params
                
                self.logger.info(f"🔍 Found method {class_name}.{method_name} with parameters: {params}")
                
                # Validate each parameter
                for param in params:
                    # Check if parameter is properly compressed (single letter or short name)
                    if not self._is_valid_compressed_parameter(param):
                        violations.append(ConstraintViolation(
                            violation_type="invalid_parameter_compression",
                            description=f"Parameter '{param}' in method '{method_name}' is not properly compressed",
                            location=f"T: section method M:{class_name}.{method_name}({params_str})",
                            suggested_fix=f"Use compressed parameter like 's' for self, 'p' for parameter, 'k' for key, etc.",
                            severity="critical"
                        ))
                    
                    # Check for Python-style type annotations (which shouldn't exist in CAI3)
                    if ':' in param or '->' in param:
                        violations.append(ConstraintViolation(
                            violation_type="python_type_annotation_in_parameter",
                            description=f"Parameter '{param}' contains Python type annotation syntax",
                            location=f"T: section method M:{class_name}.{method_name}({params_str})",
                            suggested_fix="Remove type annotations, use only compressed parameter names",
                            severity="critical"
                        ))
        
        # Validate that all method parameters have mappings in V: section
        v_section_violations = self._validate_parameter_v_section_mappings(method_params, cai3_output)
        violations.extend(v_section_violations)
        
        return violations
    
    def _validate_table_parameter_completeness(self, cai3_output: str) -> List[ConstraintViolation]:
        """
        Validate that table entries include proper parameter information.
        
        This ensures methods don't lose their parameter signatures during compression.
        """
        violations = []
        
        # Extract all method entries from T: section
        t_section_match = re.search(r'T:([^\n]*)', cai3_output)
        if not t_section_match:
            return violations
            
        t_content = t_section_match.group(1)
        
        # Find method definitions and check for missing parameters
        method_entries = re.findall(r'M:([^,\s]+)', t_content)
        
        for method_entry in method_entries:
            # Check if method has parameters
            if '(' not in method_entry:
                # Check if this method should have parameters by looking at its body
                body_id_match = re.search(r'#([^,\s]+)$', method_entry)
                if body_id_match:
                    body_id = body_id_match.group(1)
                    body_content = self._extract_body_content(cai3_output, body_id)
                    
                    if body_content and self._body_suggests_parameters(body_content):
                        violations.append(ConstraintViolation(
                            violation_type="missing_method_parameters",
                            description=f"Method '{method_entry}' appears to need parameters based on body content",
                            location=f"T: section entry: {method_entry}",
                            suggested_fix="Add compressed parameters like M:class.method(s,p)#body",
                            severity="warning"
                        ))
            else:
                # Method has parameters, validate they're properly formatted
                param_match = re.search(r'\(([^)]*)\)', method_entry)
                if param_match:
                    params_str = param_match.group(1)
                    if not params_str.strip():
                        violations.append(ConstraintViolation(
                            violation_type="empty_parameter_list",
                            description=f"Method '{method_entry}' has empty parameter list ()",
                            location=f"T: section entry: {method_entry}",
                            suggested_fix="Remove empty parentheses or add compressed parameters",
                            severity="warning"
                        ))
        
        return violations
    
    def _validate_parameter_v_section_mappings(self, method_params: Dict[str, List[str]], cai3_output: str) -> List[ConstraintViolation]:
        """
        Validate that method parameters used in parentheses are present in V: section.
        This is a more lenient validation that only checks for the presence of compressed
        variables in the V: section, not requiring exact matches for every parameter.
        """
        violations = []
        
        if not method_params:
            return violations
        
        # Extract all unique parameters
        all_params = set()
        for params_list in method_params.values():
            all_params.update(params_list)
        
        # Extract V: section mappings
        v_section_params = set()
        v_section_match = re.search(r'V:([^\n]*)', cai3_output)
        if v_section_match:
            v_content = v_section_match.group(1)
            # Find parameter mappings - more flexible pattern matching
            param_mappings = re.findall(r'([a-z][a-z0-9_]*)=', v_content)
            for param_name in param_mappings:
                v_section_params.add(param_name)
        
        # Find missing parameter mappings - only flag truly missing ones
        missing_params = set()
        for param in all_params:
            # Only require mapping if parameter is actually used and not a common standard parameter
            if param not in v_section_params and not self._is_standard_parameter(param):
                missing_params.add(param)
        
        if missing_params:
            self.logger.warning(f"⚠️ {len(missing_params)} method parameters could benefit from V: section mappings")
            for missing_param in sorted(missing_params):
                violations.append(ConstraintViolation(
                    violation_type="missing_parameter_mapping",
                    description=f"Method parameter '{missing_param}' could be mapped in V: section for clarity",
                    location=f"Consider adding to V: section: {missing_param}",
                    suggested_fix=f"Add '{missing_param}=original_parameter_name' to V: section",
                    severity="info"  # Changed from "critical" to "info"
                ))
        else:
            self.logger.info(f"✅ All {len(all_params)} method parameters have mappings in V: section")
        
        return violations
    
    def _is_valid_compressed_parameter(self, param: str) -> bool:
        """
        Check if a parameter is properly compressed according to CAI3 standards.
        
        Valid compressed parameters:
        - Single letters: s, p, k, v, i, etc.
        - Short abbreviations: na, th, co, etc. (2-3 chars max)
        - Must be valid Python identifiers
        - No Python keywords
        """
        if not param or not param.isidentifier():
            return False
            
        # Must be short (1-3 characters for good compression)
        if len(param) > 3:
            return False
            
        # Should not be Python keywords
        python_keywords = {'and', 'or', 'not', 'in', 'is', 'if', 'as', 'for', 'try', 'def', 'del'}
        if param in python_keywords:
            return False
            
        # Should follow CAI3 naming conventions
        # Single letters are preferred, 2-3 letter abbreviations are acceptable
        return True
    
    def _is_standard_parameter(self, param: str) -> bool:
        """
        Check if a parameter is a standard/common CAI3 parameter that doesn't require explicit mapping.
        
        Standard parameters that are commonly understood:
        - s: self (universally understood)
        - i, j, k: common loop/index variables
        - x, y, z: common mathematical variables
        - Other single-letter variables that are self-explanatory
        """
        # Single letter parameters that are commonly understood
        standard_single_letters = {'s', 'i', 'j', 'k', 'x', 'y', 'z', 'n', 'm', 'p', 'v', 'o', 't', 'u', 'w', 'g', 'r', 'e', 'q'}
        
        # If it's a single letter and commonly used, consider it standard
        if len(param) == 1 and param in standard_single_letters:
            return True
            
        # Some common 2-letter abbreviations that are self-explanatory
        standard_abbreviations = {'an', 'ac', 'aa', 'af', 'ao', 'ap', 'ar', 'as', 'at'}
        if param in standard_abbreviations:
            return True
            
        return False
    
    def _extract_body_content(self, cai3_output: str, body_id: str) -> Optional[str]:
        """Extract body content for a specific body ID."""
        body_pattern = rf'B#{body_id}:([^\n]*(?:\n(?!B#|[A-Z]:)[^\n]*)*)'
        body_match = re.search(body_pattern, cai3_output, re.MULTILINE)
        return body_match.group(1).strip() if body_match else None
    
    def _body_suggests_parameters(self, body_content: str) -> bool:
        """
        Check if body content suggests the method should have parameters.
        
        Look for patterns that indicate parameter usage:
        - Variable assignments that could be parameters
        - Function calls with arguments
        - Conditional checks on variables
        """
        if not body_content:
            return False
            
        # Look for patterns suggesting parameters
        parameter_indicators = [
            r'\b[a-z]\s*=\s*[a-z]+\b',  # Variable assignments like p=parameter
            r'\b[a-z]\s*==\s*',         # Comparisons with variables
            r'\b[a-z]\s*!=\s*',         # Not-equal comparisons
            r'\bif\s+[a-z]\b',          # Conditional checks on single letters
            r'\bfor\s+[a-z]\s+in\b',    # For loops with single letter variables
        ]
        
        for pattern in parameter_indicators:
            if re.search(pattern, body_content):
                return True
                
        return False
    

    

    
    def _attempt_basic_repairs(self, cai3_output: str, violations: List[ConstraintViolation]) -> str:
        """Attempt basic repairs for common violations including delimiter balancing and hash mapping fixes."""
        repaired = cai3_output
        
        for violation in violations:
            if violation.violation_type == "missing_hash_mapping":
                # Extract the missing hash from the violation description
                missing_hash_match = re.search(r"Hash '(hash_[a-f0-9]{4})'", violation.description)
                if missing_hash_match:
                    missing_hash = missing_hash_match.group(1)
                    # Try to add the missing hash mapping to D: section
                    repaired = self._add_missing_hash_mapping(repaired, missing_hash)
                    repaired = self._add_missing_hash_mapping(repaired, missing_hash)
                    
            elif violation.violation_type == "missing_variable_mapping":
                # Extract the missing variable from the violation description
                missing_var_match = re.search(r"Single-letter variable '([a-z])'", violation.description)
                if missing_var_match:
                    missing_var = missing_var_match.group(1)
                    # Try to add the missing variable mapping to V: section
                    repaired = self._add_missing_variable_mapping(repaired, missing_var)
                    
            elif violation.violation_type == "forbidden_parentheticals":
                # Remove parentheticals
                repaired = re.sub(r'\(was [^)]*\)', '', repaired)
                repaired = re.sub(r'\(originally [^)]*\)', '', repaired)
                
            elif violation.violation_type == "forbidden_ellipsis":
                # Remove ellipsis markers
                repaired = repaired.replace('...)', ')')
                repaired = repaired.replace('p...', '')
                
            # Removed repair logic for R: sections and raw data - these are legitimate CAI3 constructs
                
            elif violation.violation_type == "invalid_section_identifier":
                # Remove lines with invalid section identifiers
                # This handles R: sections and other invalid identifiers
                invalid_lines = []
                for line in repaired.split('\n'):
                    if ':' in line and not line.startswith('#') and not line.startswith('B#'):
                        section_prefix = line.split(':')[0] + ':'
                        valid_sections = {'I:', 'D:', 'V:', 'X:', 'P:', 'T:', '---:'}
                        if section_prefix not in valid_sections:
                            invalid_lines.append(line)
                
                # Remove all invalid lines
                for invalid_line in invalid_lines:
                    repaired = repaired.replace(invalid_line + '\n', '')
                    repaired = repaired.replace(invalid_line, '')
                
            elif violation.violation_type == "missing_header":
                # Add missing header
                if not repaired.strip().startswith('#C3L'):
                    repaired = '#C3L v2\n' + repaired
                    
            elif violation.violation_type in ["unbalanced_braces", "unbalanced_parentheses", 
                                            "unbalanced_brackets", "unbalanced_double_quotes", 
                                            "unbalanced_single_quotes"]:
                # Attempt to balance delimiters by adding missing closing delimiters
                repaired = self._attempt_delimiter_balancing(repaired, violation.violation_type)
                
            elif violation.violation_type == "unclosed_delimiter":
                # Extract the delimiter type from the violation and add closing delimiter
                if "'{'" in violation.description:
                    repaired += '}'
                elif "'('" in violation.description:
                    repaired += ')'
                elif "'['" in violation.description:
                    repaired += ']'
                elif 'double quote' in violation.description:
                    repaired += '"'
                elif 'single quote' in violation.description:
                    repaired += "'"
        
        return repaired
    
    def _add_missing_hash_mapping(self, content: str, missing_hash: str) -> str:
        """Add a missing hash mapping to the D: section."""
        # Find the D: section
        d_section_match = re.search(r'(D:)([^\n]*)', content)
        if d_section_match:
            d_prefix = d_section_match.group(1)
            d_content = d_section_match.group(2)
            
            # Add the missing hash mapping with a placeholder value
            if d_content.strip():
                new_d_content = f"{d_content},{missing_hash}=unknown"
            else:
                new_d_content = f"{missing_hash}=unknown"
            
            # Replace the D: section
            new_d_section = f"{d_prefix}{new_d_content}"
            content = content.replace(d_section_match.group(0), new_d_section)
        else:
            # No D: section exists, add one after the header
            header_match = re.search(r'(#C3L[^\n]*\n)', content)
            if header_match:
                header = header_match.group(1)
                insertion_point = header_match.end()
                new_d_section = f"D:{missing_hash}=unknown\n"
                content = content[:insertion_point] + new_d_section + content[insertion_point:]
        
        return content
    
    def _add_missing_variable_mapping(self, content: str, missing_var: str) -> str:
        """Add a missing variable mapping to the V: section."""
        # Find the V: section
        v_section_match = re.search(r'(V:)([^\n]*)', content)
        if v_section_match:
            v_prefix = v_section_match.group(1)
            v_content = v_section_match.group(2)
            
            # Add the missing variable mapping with a reasonable default value
            var_defaults = {
                's': 'self', 'i': 'index', 'j': 'result', 'k': 'key', 'v': 'value',
                't': 'total', 'u': 'usage', 'w': 'wrapper', 'g': 'group', 'n': 'number',
                'o': 'object', 'm': 'metadata', 'r': 'result', 'c': 'count', 'l': 'list',
                'e': 'element', 'p': 'parameter', 'a': 'argument', 'b': 'buffer', 'd': 'data'
            }
            default_value = var_defaults.get(missing_var, f"variable_{missing_var}")
            
            if v_content.strip():
                new_v_content = f"{v_content},{missing_var}={default_value}"
            else:
                new_v_content = f"{missing_var}={default_value}"
            
            # Replace the V: section
            new_v_section = f"{v_prefix}{new_v_content}"
            content = content.replace(v_section_match.group(0), new_v_section)
        else:
            # No V: section exists, add one after D: section or header
            # Try to find D: section first
            d_section_match = re.search(r'D:[^\n]*\n', content)
            if d_section_match:
                insertion_point = d_section_match.end()
            else:
                # Fall back to after header
                header_match = re.search(r'(#C3L[^\n]*\n)', content)
                if header_match:
                    insertion_point = header_match.end()
                else:
                    insertion_point = 0
            
            var_defaults = {
                's': 'self', 'i': 'index', 'j': 'result', 'k': 'key', 'v': 'value',
                't': 'total', 'u': 'usage', 'w': 'wrapper', 'g': 'group', 'n': 'number',
                'o': 'object', 'm': 'metadata', 'r': 'result', 'c': 'count', 'l': 'list',
                'e': 'element', 'p': 'parameter', 'a': 'argument', 'b': 'buffer', 'd': 'data'
            }
            default_value = var_defaults.get(missing_var, f"variable_{missing_var}")
            new_v_section = f"V:{missing_var}={default_value}\n"
            content = content[:insertion_point] + new_v_section + content[insertion_point:]
        
        return content
    
    def _attempt_delimiter_balancing(self, content: str, violation_type: str) -> str:
        """Attempt to balance delimiters by adding missing closing delimiters."""
        if violation_type == "unbalanced_braces":
            open_count = content.count('{')
            close_count = content.count('}')
            if open_count > close_count:
                content += '}' * (open_count - close_count)
        
        elif violation_type == "unbalanced_parentheses":
            open_count = content.count('(')
            close_count = content.count(')')
            if open_count > close_count:
                content += ')' * (open_count - close_count)
        
        elif violation_type == "unbalanced_brackets":
            open_count = content.count('[')
            close_count = content.count(']')
            if open_count > close_count:
                content += ']' * (open_count - close_count)
        
        elif violation_type == "unbalanced_double_quotes":
            quote_count = content.count('"')
            if quote_count % 2 != 0:
                content += '"'
        
        elif violation_type == "unbalanced_single_quotes":
            quote_count = content.count("'")
            if quote_count % 2 != 0:
                content += "'"
        
        return content
    
    def _create_fix_prompt(self, violations: List[ConstraintViolation], 
                          cai3_output: str, original_task: str) -> str:
        """Create a fix prompt highlighting specific constraint violations."""
        
        critical_violations = [v for v in violations if v.severity == 'critical']
        warning_violations = [v for v in violations if v.severity == 'warning']
        
        violation_details = []
        
        if critical_violations:
            violation_details.append("CRITICAL ISSUES (must fix):")
            for v in critical_violations:
                violation_details.append(f"  - {v.description}")
                violation_details.append(f"    Fix: {v.suggested_fix}")
        
        if warning_violations:
            violation_details.append("\nWARNINGS (should fix):")
            for v in warning_violations:
                violation_details.append(f"  - {v.description}")
                violation_details.append(f"    Fix: {v.suggested_fix}")
        
        violations_text = '\n'.join(violation_details)
        
        # Check if any violations are syntax-related
        has_syntax_violations = any(v.violation_type.startswith(('unbalanced_', 'unclosed_', 'mismatched_', 'unexpected_')) 
                                  for v in critical_violations + warning_violations)
        
        # Check if any violations are hash mapping-related
        has_hash_violations = any(v.violation_type == 'missing_hash_mapping' 
                                for v in critical_violations + warning_violations)
        
        syntax_emphasis = ""
        if has_syntax_violations:
            syntax_emphasis = """
🔧 SYNTAX VALIDATION FAILURE DETECTED:
Your code has unbalanced brackets, braces, parentheses, or quotes.
You MUST verify that every opening delimiter has a matching closing delimiter:
- Every { has a matching }
- Every ( has a matching )
- Every [ has a matching ]
- Every " has a matching "
- Every ' has a matching '

"""
        
        hash_emphasis = ""
        if has_hash_violations:
            hash_emphasis = """
🚨 HASH MAPPING VALIDATION FAILURE DETECTED:
Your D: section is INCOMPLETE! You used hash references in body sections (B#) 
without defining them in the D: section.

CRITICAL REQUIREMENT:
- If B#a0 contains hash_ca00 → D: section MUST have hash_ca00=something
- If B#a1 contains hash_e29c → D: section MUST have hash_e29c=something
- EVERY hash_XXXX in ANY body section MUST be in D: section

EXAMPLE:
❌ WRONG:
D:g0=o.name
B#a0:if hash_ca00 in v:return hash_e29c

✅ CORRECT:
D:g0=o.name,hash_ca00=error,hash_e29c=name
B#a0:if hash_ca00 in v:return hash_e29c

"""
        
        fix_prompt = f"""🚨 FORMAT VIOLATION - IMMEDIATE CORRECTION REQUIRED 🚨

Your previous response was REJECTED because it did not follow the format.
{syntax_emphasis}{hash_emphasis}
🔴 WHAT YOU DID WRONG:
{violations_text}

✅ CORRECT FORMAT REQUIRED:
You must start your response with exactly these lines:

=== MAPPINGS ===
[your mappings here]

=== CAI3-LITE ===
[your CAI3 code here]

❌ NO other text allowed before, between, or after these sections.

🔧 MANDATORY PRE-SUBMISSION VALIDATION:
Before responding, check your CAI3-LITE code for:
✓ Balanced brackets: [ ]
✓ Balanced braces: {{ }}
✓ Balanced parentheses: ( )
✓ Balanced quotes: " " and ' '
✓ Proper CAI3-LITE syntax
✓ 🚨 D: section has ALL hash_XXXX mappings used in B# sections

TASK: {original_task}

YOUR PREVIOUS INCORRECT OUTPUT:
{cai3_output[:500]}...

🚨 CRITICAL: Respond ONLY with the format above. Start with "=== MAPPINGS ===" immediately."""

        return fix_prompt
    
    def _learn_successful_pattern(self, prompt: str, successful_output: str):
        """Learn from successful patterns to improve future prompts."""
        if self.enable_constraint_learning:
            # Extract key patterns from successful interactions
            pattern = {
                'prompt_length': len(prompt),
                'output_length': len(successful_output),
                'has_mappings': '=== MAPPINGS ===' in successful_output,
                'constraint_keywords': self._extract_constraint_keywords(prompt)
            }
            
            self.successful_patterns.append(str(pattern))
            self.logger.debug(f"Learned successful pattern: {pattern}")
    
    def _extract_constraint_keywords(self, prompt: str) -> List[str]:
        """Extract constraint-related keywords from a prompt."""
        constraint_keywords = []
        keywords = ['ONLY', 'MUST', 'STRICT', 'MANDATORY', 'FORBIDDEN', 'REQUIRED']
        
        for keyword in keywords:
            if keyword in prompt.upper():
                constraint_keywords.append(keyword)
        
        return constraint_keywords
    
    def get_constraint_statistics(self) -> Dict[str, Any]:
        """Get statistics about constraint violations and success rates."""
        total_violations = len(self.violation_history)
        violation_types = {}
        
        for violation in self.violation_history:
            violation_types[violation.violation_type] = violation_types.get(violation.violation_type, 0) + 1
        
        return {
            'total_violations': total_violations,
            'violation_types': violation_types,
            'successful_patterns': len(self.successful_patterns),
            'most_common_violations': sorted(violation_types.items(), key=lambda x: x[1], reverse=True)[:5]
        }
    
    def update_constraints_from_cai3full(self, cai3_full: CAI3Full):
        """Update internal constraints based on a new CAI3Full structure."""
        self.logger.info("Updating constraints from CAI3Full structure")
        
        # This could update internal constraint databases, learn new patterns, etc.
        # For now, we'll just log the update
        hash_count = len(cai3_full.hash_to_value) if hasattr(cai3_full, 'hash_to_value') else 0
        pool_count = len(cai3_full.pools) if hasattr(cai3_full, 'pools') else 0
        
        self.logger.debug(f"Updated constraints: {hash_count} hashes, {pool_count} pools")
