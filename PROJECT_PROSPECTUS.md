# OptimizeAI: Project Prospectus & Post-Mortem Analysis

## For LLM Contextual Understanding

This document provides a complete technical prospectus of the OptimizeAI project — what it
does, how it works, where it succeeded, and critically, why the LLM integration layer
introduced fatal non-determinism that made the project infeasible at scale.

---

## 1. THE PROBLEM

### Token Cost and Context Window Limits in LLM-Assisted Code Editing

When using LLMs (Claude, GPT-4, etc.) for code editing tasks, the user sends entire Python
files as input. This creates two compounding costs:

1. **Token Cost**: At $0.003–$0.015 per 1K tokens, sending a 500-line Python file (≈2,000
   tokens) repeatedly for iterative edits becomes expensive.
2. **Context Window Saturation**: Large files consume context window budget that could be
   used for richer instructions, multi-file context, or conversation history.
3. **Redundancy**: Most of the file content is unchanged between edits — boilerplate imports,
   docstrings, unchanged methods — yet the full file is re-sent every time.

**The core insight**: If we could compress Python code into a dense, token-efficient
representation, send that compressed form to the LLM, have the LLM edit it in compressed
form, and then decompress the result back to valid Python — we'd save 50–87% on tokens.

---

## 2. THE PROPOSED SOLUTION

### A Two-Phase Pipeline: Deterministic Compression + LLM Editing in Compressed Space

```
PHASE 1 (Deterministic — WORKS):
  Python Source → AST Parse → Minification → CAI3 Encoding → CAI3-LITE Token Stream

PHASE 2 (Non-Deterministic — FAILS AT SCALE):
  CAI3-LITE + Edit Prompt → LLM (Claude) → Modified CAI3-LITE → Reconstruction → Python
```

### Phase 1: The Compression Engine (Deterministic)

The project built a multi-tier compression engine with five tiers:

| Tier   | Token Range  | Method                          | Compression |
|--------|-------------|----------------------------------|-------------|
| TINY   | 0–99        | Passthrough (no compression)     | 0%          |
| SMALL  | 100–249     | Conservative minification        | 10–30%      |
| MEDIUM | 250–999     | Full CAI3 compression            | 50–70%      |
| LARGE  | 1,000–9,999 | Chunked CAI3 compression         | 40–60%      |
| HUGE   | 10,000+     | Structural summarization         | 80–95%      |

The compression pipeline applies these transformations in sequence:

#### Step 1: AST Parsing & Minification
```python
# ORIGINAL (95 tokens)
def validate_record(self, record: Dict) -> bool:
    """Validate a single record - contains bug patterns."""
    required_fields = self.config.get("required_fields", [])
    for field in required_fields:
        if field not in record:
            self.error_count += 1
    timeout = self.config.get("timeout", 30)
    return True

# MINIFIED (≈40 tokens)
def vr(s,r):
    rf=s.c.g("required_fields",[])
    for f in rf:
        if f not in r:s.ec+=1
    t=s.c.g("timeout",30)
    return True
```

#### Step 2: CAI3 Structural Encoding

The minified code is then encoded into the CAI3-LITE format — an ultra-dense
domain-specific representation:

```
#C3L v2 py=3.11 f=data_processor.py
I:dt|j|t:D,L,O
D:g0=DataProcessor|hash_ca00=required_fields|hash_e29c=timeout
X:a0=mt_5605,a1=mt_961c,a2=mt_3d9a,a3=mt_7b2f
P:p0="required_fields",p1="timeout"
S:s=self,c=config,ec=error_count,pc=processed_count,db=data_buffer
V:rf=required_fields,f=field,t=timeout,r=record
T:C:g0,M:g0.__init__(s,c)#a0,M:g0.vr(s,r)->b#a1,M:g0.pb(s,rs)->L#a2,M:g0.gs(s)->D#a3
---
B#a0:s.c=c;s.pc=0;s.ec=0;s.db=[]
B#a1:rf=s.c.g(p0,[]);F:f:rf{I:f!in r{s.ec+=1}};t=s.c.g(p1,30);R:T
B#a2:rs=[];F:r:rs{T{I:s.vr(r){...}s.pc+=1}X(e){s.ec+=1}};R:rs
B#a3:R:{"processed":s.pc,"errors":s.ec,"buffer_size":G:len(s.db)}
```

**Key encoding features:**
- `I:` — Imports compressed to abbreviations (`dt` = datetime, `j` = json)
- `D:` — Chain aliases mapping hash references to original identifiers
- `X:` — CID (Component ID) aliases — deterministic MD5-based hashes of AST paths
- `P:` — String pool (`p0`, `p1`, ...) for frequently-used string literals
- `S:` — Self-attribute mappings (e.g., `s.ec` = `self.error_count`)
- `V:` — Local variable mappings (e.g., `rf` = `required_fields`)
- `T:` — Structure table listing classes, methods, functions with signatures
- `B#` — Body sections with FLOW-encoded method implementations

**FLOW Language Macros** used inside body sections:
```
F:var:iterable{...}   →  for var in iterable: ...
I:cond{...}           →  if cond: ...
T{...}X(e){...}       →  try: ... except Exception as e: ...
R:value               →  return value
G:expr                →  (expression)
```

#### Why Phase 1 Is Deterministic

1. **CID Generation**: `cid = prefix + "_" + md5(parent_cid + "." + node_type + "." + node_name)[:4]`
   Same AST path always produces the same CID.
2. **Variable Naming**: Sequential assignment (`a`, `b`, ..., `z`, `aa`, `ab`, ...) in
   deterministic AST walk order.
3. **Pool Assignment**: String literals assigned `p0`, `p1`, ... in order of first encounter.
4. **Hash References**: `hash_` + first 4 hex chars of MD5 of the original identifier.

**This means**: Given the same Python input file, the CAI3-LITE output is always identical.
Unit tests confirm this — roundtrip compression produces byte-identical output across runs.

---

### Phase 2: LLM Editing in Compressed Space (Non-Deterministic)

The idea: Instead of sending the full Python file to Claude for editing, send the CAI3-LITE
representation plus a task instruction. Claude edits the CAI3-LITE directly, and the system
reconstructs valid Python from the modified CAI3-LITE.

**The prompt sent to Claude** (from `claude_cai3_interface.py:247-409`) contains:

1. The CAI3-LITE content
2. 17 constraint rules (hash mappings, pool definitions, bracket balance, etc.)
3. Examples of correct vs. incorrect syntax
4. A mandatory validation checklist
5. The editing task

**The expected response from Claude** must follow this exact schema:

```
=== CAI3-LITE ===
#C3L v2 py=3.11 f=filename.py
I:...
D:...
X:...
P:...
S:...
V:...
T:...
---
B#a0:...
B#a1:...

=== MAPPINGS ===
new_identifier: original_name
```

---

## 3. THE GAP: NON-DETERMINISM OF THE LLM

### Why This Fails at Scale

The fundamental problem is that **an LLM cannot reliably act as a deterministic
transcompiler**. Even with the most aggressive prompt constraints, Claude's output
violates the CAI3-LITE schema in unpredictable ways. The system implements 10 validation
layers (in `claude_cai3_interface.py:620-755`) and up to 3 repair attempts per request,
but violations persist.

### Concrete Failure Categories (with examples from the codebase)

#### Failure 1: Missing Hash Mappings in D: Section

**What should happen**: Every `hash_XXXX` reference in a `B#` body section must have a
corresponding `hash_XXXX=original_name` entry in the `D:` section.

**What Claude actually does**:
```
# Claude's output (WRONG)
D:g0=DataProcessor
B#a0:if hash_ca00 in v:return hash_e29c
B#a1:k=hash_7b30(hash_2308)
```

Claude uses `hash_ca00`, `hash_e29c`, `hash_7b30`, `hash_2308` in bodies but doesn't add
them to the `D:` section. The validator (`_validate_hash_constraints`, line 757) catches this
as CRITICAL, but the repair prompt often fails to fix it completely because Claude may:
- Add some but not all missing hashes
- Invent incorrect original names for the hashes
- Change the body content in the repair, introducing new hashes that are also unmapped

**Impact**: The reconstructor cannot resolve these hash references back to Python identifiers,
producing code like `hash_ca00 in v` instead of `"required_fields" in record`.

#### Failure 2: Unbalanced Brackets and Malformed Try-Except Structures

**What should happen**: `T{...}X(Exception){...}` must have balanced braces.

**What Claude actually does**:
```
# Claude's output (WRONG)
B#a2:F:r:rs{T{I:s.vr(r){p={...};s.db.ap(p);rs.ap(p);s.pc+=1}O{s.ec+=1}X(e){s.ec+=1}
```

The closing `}` for the `T{}` block is missing. The nested delimiter validator
(`_validate_syntax_structure`, using a stack-based checker at lines 1130-1192) detects this,
but repair attempts often introduce *different* bracket imbalances because Claude doesn't
track nesting depth reliably in the compressed format.

**Impact**: The FLOW parser cannot determine where try blocks end and except blocks begin,
producing malformed Python with incorrect indentation or missing exception handlers.

#### Failure 3: Mixed Python and CAI3 Syntax in Body Sections

**What should happen**: Body sections should use only CAI3-LITE compressed syntax.

**What Claude actually does**:
```
# Claude's output (WRONG)
B#a0:from dataclasses import dataclass;analyzer=CompressionAnalyzer()
B#a7:try:file_path=Path(file_path);if not file_path.exists():
```

Despite the prompt explicitly stating "NO PYTHON IMPORTS OR SYNTAX IN B# BLOCKS" (constraint
#11), Claude frequently reverts to writing Python inside body sections. This happens because
the LLM has a strong prior for generating Python and the CAI3-LITE format is novel enough
that the LLM's natural token prediction distribution favors Python syntax over CAI3 syntax.

**Impact**: The reconstructor receives a hybrid of Python and CAI3 that neither parser can
handle cleanly. The result is either a syntax error or semantically incorrect code.

#### Failure 4: V: and S: Section Confusion

**What should happen**: The `S:` section contains self-attribute mappings
(`s=self,na=name,th=threshold`), and `V:` contains local variables (`i=index,k=key`).

**What Claude actually does**:
```
# Claude's output (WRONG)
V:s=self,i=index,k=key,v=value,ti=tiers,af=analyze_file
B#a0:for o in s.ti:v=s.af(k)
```

Claude mixes self-attributes (`ti=tiers`, `af=analyze_file`) into the `V:` section instead
of the `S:` section. The validator (`_validate_s_section_constraints`, lines 1409-1545) and
(`_validate_v_section_constraints`, lines 1262-1407) both check for this, but the repair
prompt creates a feedback loop where fixing one section breaks the other.

**Impact**: During reconstruction, the system cannot determine whether `s.ti` refers to
`self.tiers` (an instance attribute) or a local variable access, producing incorrect
attribute resolution.

#### Failure 5: Table Entry Format Violations

**What should happen**: Table entries use short aliases: `C:g0,M:g0.vr(s,r)->b#a1`

**What Claude actually does**:
```
# Claude's output (WRONG)
T:C:CompressionTier,M:CompressionTier.is_initialized(self,parameter)#a2
```

Instead of using the compressed aliases (`g0`, `s`, `p`), Claude writes full class names
and parameter names in the table. This violates the compression contract and means the table
no longer maps correctly to the body sections.

**Impact**: The structure table becomes inconsistent with the bodies, causing the
reconstructor to either mismap methods to the wrong class or fail to find method signatures.

#### Failure 6: Humanization and Annotation Injection

**What should happen**: Only CAI3-LITE content in the response, no commentary.

**What Claude actually does**:
```
# Claude's output (WRONG)
B#a0:s.va=v;i=p0 (was p1);n=p (originally "name");return hash_1234
```

Claude adds parenthetical annotations like `(was B#a0)`, `(originally ...)`, or
`(renamed from ...)` inside the CAI3-LITE content. These appear because the LLM wants to
be helpful and explain its changes, but these annotations corrupt the compressed format.

The system has a forbidden-patterns validator (lines 1209-1215 of `claude_cai3_interface.py`)
that checks for these, but they appear in varied forms that regex patterns don't catch.

**Impact**: The FLOW parser treats these annotations as code, producing syntax errors or
phantom variable references in the reconstructed Python.

### The Repair Loop Problem

The system implements a 3-attempt repair cycle (lines 170-210 of `claude_cai3_interface.py`):

```
1. Send constrained prompt → Claude responds with violations
2. Send repair prompt with specific violation details → Claude attempts fix
3. Re-validate → Often finds NEW violations introduced by the fix
4. Send another repair prompt → Claude may revert previous fixes
5. After 3 failed repairs → Fall back to "repaired_content" or original
```

**The core issue**: Each repair attempt is itself non-deterministic. Claude doesn't have
persistent state between repair attempts — it can't "remember" what it fixed last time.
Each repair prompt is a fresh generation, and the LLM may:
- Fix violation A but introduce violation B
- Revert a previous fix while addressing a new issue
- Produce an entirely different (and newly broken) output structure

This creates a **non-convergent repair loop** where the number of violations oscillates
rather than monotonically decreasing.

### Quantifying the Non-Determinism

From analysis of the test infrastructure:

| Test Category | Pass Rate | Notes |
|--------------|-----------|-------|
| Unit tests (compression only, no LLM) | ~100% | Deterministic, byte-identical |
| Unit tests (decompression only, no LLM) | ~95% | Minor reconstruction edge cases |
| Mock LLM tests (predetermined responses) | ~100% | Deterministic by definition |
| Real LLM roundtrip (compress → Claude edit → decompress) | ~30-50% | Non-deterministic |
| Real LLM with repair loop | ~50-65% | Better but still unreliable |

The test suite (`tests/mocks/llm_response.py`) uses hardcoded mock responses to achieve
deterministic testing, but this papers over the fundamental problem — real Claude responses
don't match the mocks. The real integration tests (`test_cai3_integration.py`) are either
skipped with `@pytest.mark.skipif` or produce inconsistent results.

---

## 4. ARCHITECTURAL DETAILS THAT PROVIDE UNIQUE INSIGHT

### 4.1 The CAI3 Data Model — Three Interconnected Structures

The system maintains three parallel data structures per compressed file:

```
CAI3Full (local storage — never sent to LLM)
├── nodes: List[CAI3Node]         # Full AST node information
├── imports: List[str]            # Complete import statements
├── pools: Dict[str, str]        # p0 → "required_fields"
├── bound_hashes: Dict[str, str] # cid → content hash
├── span_hashes: Dict[str, str]  # cid → span hash
├── hash_to_value: Dict          # hash_XXXX → original value
└── file_hash: str               # MD5 of original file

CAI3Map (local storage — bidirectional mapping)
├── name_map: Dict[str, str]     # short_name → original_name
├── reverse_name_map: Dict       # original_name → short_name
├── span_map: Dict               # cid → (start_line, end_line)
├── byte_map: Dict               # cid → (start_byte, end_byte)
├── ast_paths: Dict              # cid → AST node path
├── parent_map: Dict             # cid → parent_cid
├── children_map: Dict           # parent → [children]
└── minified_source: str         # Pre-minified source for validation

CAI3Lite (sent to LLM — what Claude sees and edits)
├── header: str                  # "#C3L v2 py=3.11 f=file.py"
├── imports: str                 # "I:dt|j|t:D,L,O"
├── table: List[str]             # Structure entries
├── bodies: List[str]            # Method implementations
├── pools: str                   # "P:p0=value1;p1=value2"
└── cid_aliases: str             # "X:a0=mt_5605|a1=mt_961c"
```

**The critical design decision**: Only CAI3Lite is sent to the LLM. CAI3Full and CAI3Map
stay local. Reconstruction requires merging the LLM's modified CAI3Lite back with the
local CAI3Full and CAI3Map. This merge is where non-determinism causes the most damage —
if the LLM changes a CID alias, renames a pool, or restructures the table, the local
maps can no longer align with the modified content.

### 4.2 The FLOW Language — A Novel Dense Syntax

The project invented a micro-language called FLOW for encoding Python control flow into
single-character macros:

```
FLOW Macro    Python Equivalent
─────────────────────────────────
L:x:val       x = val (assignment)
I:cond{...}   if cond: ...
E:cond{...}   elif cond: ...
O{...}        else: ...
F:v:iter{...} for v in iter: ...
W:cond{...}   while cond: ...
T{...}        try: ...
X(e){...}     except Exception as e: ...
Z:ctx{...}    with ctx: ...
R:val         return val
Y:val         yield val
@:val         print(val)
!expr         not expr
&             and
|             or
N             is None
```

**Why this matters**: FLOW achieves genuine token reduction (60-70% for method bodies) but
creates an entirely new parsing surface. When Claude generates FLOW, it must correctly
nest braces across multiple control flow levels — something it does unreliably because
FLOW is not in its training data and brace-tracking at depth > 2 exceeds the LLM's
reliable symbolic manipulation capability.

### 4.3 Cache-Dependent Reconstruction

The reconstruction pipeline (`cai3_python_reconstructor.py`) depends on the CAI3 cache:

```python
# From claude_proxy.py — the cache dependency chain:
self.cai3_cache = CAI3Cache(self.cache_dir)
self.cai3_enhancer.cai3_cache = self.cai3_cache  # Shared cache

# On reconstruction:
cai3_full = self.cai3_cache.load_full(source_path)  # Must exist
cai3_map = self.cai3_cache.load_map(source_path)     # Must exist

# If cache miss:
raise ValueError("No CAI3 cache found")
```

**The cache recovery problem** (lines 696-778 of `claude_proxy.py`): When the cache is
missing, the system tries three recovery strategies:
1. Content-hash-based lookup
2. Original-path-based lookup
3. Most-recent-cache-file fallback

If all three fail, reconstruction is impossible — the system falls back to extracting
raw Python from Claude's output, which defeats the purpose of compression entirely.

### 4.4 The Prompt Engineering Arms Race

The constraint prompt (`_create_constrained_prompt`, lines 247-409) reveals an escalating
arms race between the system's constraints and the LLM's tendency to violate them:

- **17 explicit constraints** numbered and marked as `VIOLATION = FAILURE`
- **5 "CRITICAL" validation sections** with checkmarks
- **Emoji-heavy warning markers** (`🚨`, `❌`, `✅`) attempting to override the LLM's
  default behavior
- **Explicit correct vs. incorrect examples** for each violation type
- **A mandatory self-check instruction** asking Claude to verify its own output

Despite all of this, the prompt is ~3,000 tokens of constraint overhead on every request.
This overhead partially negates the token savings from compression, especially for smaller
files. And it still doesn't prevent violations.

### 4.5 The Commented-Out Code Trail

The codebase contains significant commented-out code blocks that tell the story of abandoned
approaches:

**In `claude_proxy.py`**:
- Lines 49-52: Commented-out `WaterfallCompressor` initialization (replaced by CAI3)
- Lines 146-156: Commented-out compression effectiveness checks (disabled during testing)
- Lines 203-210: Commented-out wrapper overhead check (disabled because it kept triggering)
- Lines 540-694: An entire duplicate `process_output` method commented out (a previous version)

**In `claude_proxy.py:388-389`**:
```python
# CRITICAL: Skip humanization to prevent CAI3lite corruption
# claude_output = self._strip_humanization_annotations(claude_output)
```

This line reveals that a humanization post-processor existed but was disabled because it
was corrupting CAI3 content — another sign that the LLM's output couldn't be reliably
post-processed.

---

## 5. WHY UNIT TESTS PASS BUT INTEGRATION FAILS

### The Determinism Boundary

```
                    DETERMINISM BOUNDARY
                           │
    Python ──→ CAI3-LITE   │   CAI3-LITE ──→ LLM ──→ Modified CAI3-LITE
    (Phase 1)              │   (Phase 2)
                           │
    ✅ Deterministic        │   ❌ Non-deterministic
    ✅ Same input = same    │   ❌ Same input ≠ same output
       output              │   ❌ Output may violate schema
    ✅ Roundtrip-proven     │   ❌ Roundtrip lossy
    ✅ AST-validated        │   ❌ Cannot be reliably validated
```

**Unit tests work** because they test Phase 1 in isolation:
- `test_cai3_roundtrip.py`: Compress → Decompress without LLM. Passes reliably.
- `test_waterfall_compressor.py`: Tier selection and compression ratios. Deterministic.
- `test_minifier.py`: AST-based minification. Same input = same output.
- `test_mapping.py`: Name mapping and reverse mapping. Bijective by construction.

**Integration tests fail** because they cross the determinism boundary:
- `test_cai3_integration.py`: Real Claude invocation — output varies each run.
- `test_full_workflow.py`: End-to-end with real LLM — marked `skipif` for CI.
- `comprehensive_e2e_validation.py`: Semantic similarity checks — scores vary 30-80%.

### The Mock Response Gap

`tests/mocks/llm_response.py` provides hardcoded mock responses:
```python
'claude': {
    'success': {
        'compressed_content': '''class H:
    def __init__(s,v):s.v=v
    def get(s):return s.v''',
        'compression_ratio': 0.42
    }
}
```

These mocks represent the *ideal* response — syntactically correct, semantically preserved,
properly formatted. Real Claude responses diverge from this ideal in the ways documented
in Section 3. The gap between mock and reality is the gap between "unit tests pass" and
"the system works in production."

---

## 6. KEY METRICS AND MEASUREMENTS

### Compression Performance (Phase 1 — Proven)

| Input Size    | Method           | Token Reduction | Roundtrip Fidelity |
|--------------|------------------|-----------------|-------------------|
| 50 tokens    | Passthrough      | 0%              | 100%              |
| 150 tokens   | Minification     | 15-25%          | ~98%              |
| 500 tokens   | CAI3-LITE        | 55-65%          | ~95%              |
| 2,000 tokens | CAI3-LITE        | 65-75%          | ~93%              |
| 10,000+ tokens| Summarization   | 80-90%          | ~40% (lossy by design) |

### LLM Interaction Performance (Phase 2 — Unreliable)

| Metric                                | Value         |
|--------------------------------------|---------------|
| Prompt constraint overhead            | ~3,000 tokens |
| Schema compliance on first attempt    | ~35-50%       |
| Schema compliance after 3 repairs     | ~50-65%       |
| Semantic preservation when compliant  | ~70-85%       |
| End-to-end success (compress → LLM → valid Python) | ~30-50% |
| Cost savings after prompt overhead    | Negative for files < 300 tokens |

---

## 7. CONCLUSIONS AND LESSONS LEARNED

### What Worked
1. **The compression engine is sound.** CAI3-LITE achieves genuine 50-75% token reduction
   with deterministic, reproducible encoding. The AST-based approach with FLOW encoding
   is a legitimate contribution.
2. **The data model is well-designed.** The three-structure approach (Full/Map/Lite) correctly
   separates local state from LLM-visible state.
3. **The validation framework is comprehensive.** 10 validation layers catch most violations
   and provide actionable error messages.

### What Failed
1. **LLMs cannot reliably operate as format-preserving transcompilers.** The CAI3-LITE format
   is novel (not in training data), complex (nested braces, multiple cross-referencing sections),
   and rigid (any deviation breaks reconstruction). LLMs operate probabilistically and cannot
   guarantee structural correctness of an unfamiliar format.
2. **Prompt engineering cannot compensate for format unfamiliarity.** Despite 17 constraints,
   examples, validation checklists, and emoji emphasis, Claude still violates the format
   30-50% of the time. Adding more constraints increases prompt overhead without proportional
   compliance improvement.
3. **The repair loop doesn't converge.** Each repair attempt is itself non-deterministic,
   creating a feedback loop where fixes introduce new violations. The violation count
   oscillates rather than monotonically decreasing.
4. **The prompt overhead partially negates compression savings.** For files under ~300 tokens,
   the ~3,000-token constraint prompt makes the system net-negative on token usage.
5. **Cache dependency creates fragility.** The reconstruction pipeline requires local cache
   state that doesn't survive across sessions or machines, adding operational complexity.

### The Fundamental Lesson

**Deterministic encoding paired with non-deterministic decoding produces unreliable results.**
The project successfully solved the easy half of the problem (deterministic compression)
but could not solve the hard half (deterministic LLM-mediated editing in compressed space)
because LLMs are fundamentally probabilistic systems being asked to perform a task that
requires symbolic precision.

For this approach to work, the LLM would need to either:
- Be fine-tuned on CAI3-LITE specifically (expensive, narrow)
- Use constrained decoding / grammar-guided generation to enforce the schema at the token
  level (not available through standard APIs)
- Operate through a verified intermediate representation with formal grammar checking at
  each generation step (not supported by current LLM architectures)

Until one of these becomes practical, the gap between deterministic compression and
non-deterministic LLM editing remains an unsolved problem.

---

## 8. CODEBASE QUICK REFERENCE

| Component | Location | Purpose |
|-----------|----------|---------|
| Compression engine | `input_optimizer/engine/` | All compression logic (28 files) |
| CAI3 structures | `input_optimizer/engine/cai3_structures.py` | CAI3Full, CAI3Map, CAI3Lite dataclasses |
| FLOW language | `input_optimizer/engine/flow_language.py` | FLOW macro compiler |
| Waterfall compressor | `input_optimizer/engine/waterfall_compressor.py` | Tier selection + compression |
| Claude interface | `integrations/claude_wrapper/claude_cai3_interface.py` | LLM interaction + validation |
| Claude proxy | `integrations/claude_wrapper/claude_proxy.py` | Input/output processing |
| Reconstructor | `input_optimizer/engine/cai3_python_reconstructor.py` | CAI3 → Python reconstruction |
| Translator | `output_translator/core/translator.py` | CAI → Python translation |
| Unit tests (passing) | `input_optimizer/tests/test_cai3_roundtrip.py` | Deterministic roundtrip tests |
| Mock responses | `tests/mocks/llm_response.py` | Hardcoded ideal LLM responses |
| Integration tests | `integrations/claude_wrapper/test_cai3_integration.py` | Real LLM tests (unreliable) |
| Error recovery | `integrations/claude_wrapper/error_recovery.py` | Fallback strategies |
| E2E validation | `integrations/claude_wrapper/comprehensive_e2e_validation.py` | Full pipeline testing |
