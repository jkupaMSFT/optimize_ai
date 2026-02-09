# Portcullis Backend Component Inventory
## Date: 2026-02-09
## Repo analyzed: /home/user/optimize_ai
## Auditor: Claude (automated audit)

---

## CRITICAL FINDING: Repository Mismatch

**This repository does NOT contain a Portcullis/Historepo backend.** The repo at `/home/user/optimize_ai` is **"Optimize AI"** — an AI-powered Python code compression and token optimization system (v0.1.0, MIT license). It compresses Python into a proprietary "CAI" format to reduce LLM token usage.

An exhaustive search was conducted across all 163 Python files (85,825 LOC), all branches (`main`, `claude/audit-backend-components-TxkSr`), git history, configuration files, and dependencies. **Zero** references were found to: Portcullis, Historepo, SCIP, rustworkx, networkx, MCP, sentinel, risk scoring, blast radius, temporal analysis, revert detection, oscillation detection, zombie patterns, Chesterton's Fence, or any of the other named components.

**Implication for Codebase MRI**: Every component listed below must be built from scratch. However, this repo does contain some reusable infrastructure (AST parsing, CLI framework, FastAPI server, source mapping) that could serve as a foundation.

---

## What This Repository Actually Contains

| Layer | Purpose | Key Files |
|-------|---------|-----------|
| CLI | Click-based CLI for compression/translation | `cli/main.py`, `cli/commands/*.py` |
| API Server | FastAPI server with REST + WebSocket endpoints | `app.py`, `start_server.py` |
| Compression Engine | Multi-tier Python → CAI format compression | `input_optimizer/engine/*.py` |
| Decompression | CAI → Python translation | `output_translator/core/*.py` |
| IDE Integrations | VSCode, Cursor, Claude Code plugins | `integrations/` |
| Monitoring | Prometheus + Grafana stack | `monitoring/`, `monitor.py` |
| Config | Agent-specific config management with hot-reload | `core/config.py` |
| Session Management | Stateful compression session tracking | `core/session_manager.py` |

---

## Component-by-Component Audit

### Component 1: SCIP Indexing Pipeline

- **Files**: None
- **Entry point**: Does not exist
- **Input**: N/A
- **Output**: N/A
- **Status**: **Does not exist**
- **Dependencies**: N/A
- **Limitations**: N/A
- **MRI Relevance**: High — SCIP indexing is the foundation for symbol-level analysis
- **MRI Gaps**: Must build from scratch. Needs:
  - SCIP binary management (scip-python, scip-typescript, scip-java, etc.)
  - Language detection (file extension + heuristic)
  - Index storage strategy (.scip protobuf files)
  - Incremental vs full reindex logic
  - Temporal indexing across commits (the `temporal_scip_service` concept)
  - Symbol/reference/relationship extraction from SCIP index

**Note**: The existing codebase DOES have extensive AST parsing for Python (`input_optimizer/engine/cai3_ast_translator.py` — 3,778 lines, `cai3_structure_analyzer.py` — 1,945 lines). This code understands Python class/method/function structure deeply but only for compression purposes, not for cross-file dependency analysis. It is Python-only and does not produce SCIP-compatible output.

---

### Component 2: Dependency Graph Construction (Rustworkx)

- **Files**: None
- **Entry point**: Does not exist
- **Input**: N/A
- **Output**: N/A
- **Status**: **Does not exist**
- **Dependencies**: N/A
- **Limitations**: N/A
- **MRI Relevance**: High — the dependency graph is the core data structure for architecture analysis
- **MRI Gaps**: Must build from scratch. Needs:
  - rustworkx (or networkx) as a dependency
  - Graph construction from SCIP symbol data
  - Node type definitions (function, class, module, file)
  - Edge type definitions (IMPORT, CALL, INSTANTIATION, INHERITANCE, TYPE_REFERENCE)
  - NetworkX fallback for when rustworkx is unavailable
  - Graph query operations: BFS, shortest path, cycle detection, connected components, centrality
  - Performance profiling at scale

**Note**: The existing `source_map_production.py` (676 lines) implements an `IntervalTree` and `BinarySearchIndex` for O(log n) range queries, and tracks parent-child relationships via `parent_id`/`children_ids` on `EnhancedMappedNode`. This is tree-structured, not a general graph, and is scoped to line-range mapping within a single file. Not directly reusable but shows the team has implemented non-trivial data structure code.

---

### Component 3: Temporal Analysis

- **Files**: None
- **Entry point**: Does not exist
- **Input**: N/A
- **Output**: N/A
- **Status**: **Does not exist**
- **Dependencies**: N/A
- **Limitations**: N/A
- **MRI Relevance**: High — temporal patterns (reverts, oscillation, zombies, co-change) are central to MRI's value proposition
- **MRI Gaps**: Must build entirely. Needs:
  - **Revert detection**: Git diff analysis to identify commits that undo previous changes. Data structure to represent revert relationships.
  - **Oscillation detection**: Track file/symbol state over time, compute oscillation index (frequency of back-and-forth changes).
  - **Zombie pattern detection**: Cross-reference revert history with subsequent reintroductions.
  - **Stability scoring**: Time-since-last-change metric per file/symbol.
  - **Co-change analysis**: Statistical coupling between files that frequently change together.
  - **Configurable time window**: Depth of git history to analyze.

**Note**: The only "revert" reference in the codebase is `semantic_compression_engine.py` line ~125 — a simple "revert to original" fallback in compression, not a detection system.

---

### Component 4: Risk Scoring

- **Files**: None
- **Entry point**: Does not exist
- **Input**: N/A
- **Output**: N/A
- **Status**: **Does not exist**
- **Dependencies**: N/A
- **Limitations**: N/A
- **MRI Relevance**: High — risk scores are the primary MRI output metric
- **MRI Gaps**: Must build entirely. Needs:
  - Risk scoring formula combining multiple signals (change frequency, revert history, complexity, dependency fan-out, test coverage)
  - `RiskAssessment` data model
  - Deterministic scoring (same input → same output)
  - Configurable thresholds or calibrated baselines from repo history
  - Output formatting (JSON, human-readable)

---

### Component 5: Domain / Architecture Detection

- **Files**: None
- **Entry point**: Does not exist
- **Input**: N/A
- **Output**: N/A
- **Status**: **Does not exist**
- **Dependencies**: N/A
- **Limitations**: N/A
- **MRI Relevance**: High — understanding architectural boundaries is key to MRI
- **MRI Gaps**: Must build entirely. Needs:
  - Directory-based domain grouping (baseline)
  - Graph-based clustering (community detection, modularity algorithms on dependency graph)
  - Boundary/interface node identification
  - Cross-domain dependency detection and metrics
  - Domain coupling scores

---

### Component 6: Blast Radius Calculation

- **Files**: None
- **Entry point**: Does not exist
- **Input**: N/A
- **Output**: N/A
- **Status**: **Does not exist**
- **Dependencies**: N/A
- **Limitations**: N/A
- **MRI Relevance**: High — blast radius is a core MRI analysis feature
- **MRI Gaps**: Must build entirely. Needs:
  - BFS/DFS traversal on dependency graph from a given node
  - Result structure: affected nodes, depth, paths
  - Edge risk weights and their application
  - Hotspot detection (nodes with disproportionate downstream impact)
  - `BlastRadiusResult` and `AffectedNode` data models

---

### Component 7: Chesterton's Fence / Living Legends

- **Files**: None
- **Entry point**: Does not exist
- **Input**: N/A
- **Output**: N/A
- **Status**: **Does not exist**
- **Dependencies**: N/A
- **Limitations**: N/A
- **MRI Relevance**: Medium — adds narrative value to MRI reports but is not structurally critical
- **MRI Gaps**: Must build entirely. Needs:
  - Analysis combining: commit messages, surrounding changes, temporal context, code comments
  - Deterministic component: heuristic signals (age, change frequency, author patterns, comment density)
  - Optional LLM component: natural language explanation of "why this code exists"
  - Data model linking code regions to their historical context

---

### Component 8: Sentinel / Guardrail System

- **Files**: None
- **Entry point**: Does not exist
- **Input**: N/A
- **Output**: N/A
- **Status**: **Does not exist**
- **Dependencies**: N/A
- **Limitations**: N/A
- **MRI Relevance**: Low/None — sentinels are for real-time enforcement, not one-time analysis
- **MRI Gaps**: For a read-only MRI product, this is likely out of scope. If needed later:
  - Check definitions (what rules to enforce)
  - Enforcement mechanism (cryptographic verification tokens)
  - Integration with CI/CD pipelines

---

### Component 9: MCP Tools / API Surface

- **Files**: None (no MCP implementation)
- **Entry point**: Does not exist
- **Input**: N/A
- **Output**: N/A
- **Status**: **Does not exist**
- **Dependencies**: N/A
- **Limitations**: N/A
- **MRI Relevance**: Medium — MCP tools could expose MRI analysis as a service, but not required for v1
- **MRI Gaps**: Must build if MCP integration is desired. Needs:
  - MCP server implementation (e.g., using `mcp` Python package)
  - Tool definitions for each analysis function
  - Input/output schema definitions

**Note**: The existing `app.py` (2000+ lines) implements a full FastAPI server with REST endpoints and WebSocket support. This infrastructure could be adapted to serve MRI analysis results via HTTP API if MCP is not needed for v1.

---

### Component 10: CLI / Orchestration

- **Files**: `cli/main.py`, `cli/commands/*.py`
- **Entry point**: `cli()` in `cli/main.py` (Click group)
- **Input**: CLI arguments (file paths, flags)
- **Output**: Console output, compressed/translated files
- **Status**: **Working** — but for compression/translation, not analysis
- **Dependencies**: Click, input_optimizer, output_translator
- **Limitations**: All commands are compression-related. No analysis commands exist.
- **MRI Relevance**: Medium — the CLI framework is reusable
- **MRI Gaps**: Need to add analysis-specific commands:
  - `optimize-ai analyze <repo-path>` — run full MRI analysis
  - `optimize-ai report <repo-path>` — generate MRI report
  - Progress reporting for long-running analysis
  - Configuration for analysis depth, language filters, output format

**Existing CLI commands** (all compression-related, not analysis):
- `compress` — Compress Python file to CAI format
- `translate` — Translate CAI back to Python
- `session` — Manage compression sessions
- `integrate` — Install IDE integrations
- `demo` — Run demo examples
- `claude-code` — Claude Code integration

---

### Component 11: Output / Reporting

- **Files**: None (no report generation)
- **Entry point**: Does not exist
- **Input**: N/A
- **Output**: N/A
- **Status**: **Does not exist**
- **Dependencies**: N/A
- **Limitations**: N/A
- **MRI Relevance**: High — the report IS the MRI product
- **MRI Gaps**: Must build entirely. Needs:
  - Report template system (Markdown at minimum, optionally HTML/PDF)
  - Section generators for each analysis dimension (architecture, risk, hotspots, temporal patterns)
  - Visualization support (dependency graphs, heatmaps, trend charts)
  - Executive summary generation
  - JSON export for programmatic consumption
  - PR comment template for CI integration

**Note**: The existing codebase has `docs/test_output/` with generated test documentation, and the FastAPI server returns structured JSON responses. These patterns could inform report generation design but are not directly applicable.

---

### Component 12: Data Models

- **Files**: Scattered across `app.py`, `core/`, `input_optimizer/engine/`, `output_translator/core/`
- **Entry point**: N/A (data structures)
- **Status**: **Working** — but all models are compression-related
- **MRI Relevance**: Low — none of the existing 47 data models are relevant to code analysis

**Existing models (all compression/translation related)**:

| Model | File | Purpose |
|-------|------|---------|
| `MinifyRequest/Response` | `app.py` | API compression request/response |
| `TranslateRequest` | `app.py` | API translation request |
| `SemanticCompressionRequest/Response` | `app.py` | Semantic compression API |
| `CompressionResult` | `compression_types.py` | Internal compression result |
| `CAI3Node`, `CAI3Full`, `CAI3Lite`, `CAI3Patch` | `cai3_structures.py` | CAI format structures |
| `AgentConfig` | `config.py` | Agent configuration |
| `Session` | `session_manager.py` | Compression session |
| `ValidationResult` | `validators.py` | Translation validation |
| `PatternMatch`, `TranslationContext`, `TranslationResult` | `translator.py` | Translation pipeline |
| `MappedNode`, `EnhancedMappedNode` | `source_map*.py` | Source mapping |
| `SourceMapping` | `semantic_compression_engine.py` | Compression mapping |
| `MinifyResult` | `minifier.py` | Minification result |
| `Token` | `flow_tokenizer.py` | Flow language token |
| `HealthResponse`, `ErrorResponse` | `app.py` | API health/error |

**MRI models that must be created**:
- `RiskAssessment` — risk score with contributing factors
- `AffectedNode` — node in blast radius result
- `BlastRadiusResult` — full blast radius computation
- `TemporalPattern` — revert/oscillation/zombie pattern
- `ArchitectureDomain` — detected domain/module grouping
- `DependencyEdge` — typed edge in dependency graph
- `SymbolNode` — node in dependency graph
- `MRIReport` — top-level report container
- `HotspotResult` — hotspot analysis result
- `CoChangeCluster` — co-change coupling result

---

### Component 13: Configuration

- **Files**: `core/config.py`, `.env.production`, `setup.py`, `pyproject.toml`
- **Entry point**: `ConfigManager` in `core/config.py`
- **Input**: JSON config file at `.optimize_ai/config.json`
- **Output**: `AgentConfig` dataclass instances
- **Status**: **Working** — for compression agent config
- **Dependencies**: Standard library (json, pathlib, asyncio)
- **Limitations**: Config is agent-specific (VSCode, Cursor, Claude), not analysis-specific
- **MRI Relevance**: Medium — the `ConfigManager` pattern with hot-reload, validation, and secure file permissions is solid and reusable
- **MRI Gaps**: Need to extend or create parallel config for:
  - Repository path / git remote URL
  - Analysis scope (languages to include, directories to exclude)
  - Analysis depth (full history vs. last N commits)
  - SCIP indexer binary paths
  - Risk threshold configuration
  - Output format and destination
  - No hardcoded paths found, but no dynamic repo targeting either — the system assumes a fixed workspace

---

## Existing Infrastructure Reusable for MRI

While none of the 13 requested components exist, the following infrastructure could accelerate MRI development:

### 1. Python AST Parsing (Reusable: Moderate)
- **Files**: `input_optimizer/engine/cai3_ast_translator.py` (3,778 lines), `cai3_structure_analyzer.py` (1,945 lines)
- **What it does**: Deep Python AST traversal, extracts class/method/function structure, understands decorators, async patterns, dataclasses, enums
- **MRI use**: Could be adapted for Python-only symbol extraction as a fallback when SCIP is unavailable
- **Limitation**: Python-only, compression-oriented, no cross-file analysis

### 2. Source Mapping with Interval Trees (Reusable: Low)
- **Files**: `input_optimizer/engine/mapping/source_map_production.py` (676 lines)
- **What it does**: O(log n) range queries, hierarchical parent-child node tracking, thread-safe index building
- **MRI use**: Data structure patterns could inform graph node indexing
- **Limitation**: Designed for line-range mapping, not dependency graphs

### 3. FastAPI Server (Reusable: High)
- **Files**: `app.py` (2,000+ lines), `start_server.py`
- **What it does**: REST API, WebSocket support, health checks, structured JSON responses, Pydantic validation
- **MRI use**: Could serve MRI results via API; add analysis endpoints alongside existing compression endpoints
- **Limitation**: Would need new routes and handlers for analysis

### 4. CLI Framework (Reusable: High)
- **Files**: `cli/main.py`, `cli/commands/*.py`
- **What it does**: Click-based CLI with subcommands, verbose logging, version management
- **MRI use**: Add `analyze` and `report` commands to existing CLI
- **Limitation**: Only compression commands exist today

### 5. Configuration Management (Reusable: High)
- **Files**: `core/config.py`
- **What it does**: JSON config with validation, hot-reload, secure file permissions, metrics integration
- **MRI use**: Extend for analysis-specific configuration
- **Limitation**: Agent-oriented config model, not repo-analysis oriented

### 6. Monitoring Stack (Reusable: Moderate)
- **Files**: `monitoring/`, `docker-compose.yml`, `core/metrics_collector.py`
- **What it does**: Prometheus metrics, Grafana dashboards, structured logging
- **MRI use**: Track analysis performance, indexing progress
- **Limitation**: Dashboards are compression-specific

---

## Summary: MRI Readiness Assessment

### Ready to Use (no changes needed)
- **Nothing.** No component from the requested inventory exists in this codebase.

### Needs Adaptation (exists but requires modification)
- **CLI Framework** (`cli/main.py`): Add analysis commands (`analyze`, `report`). The Click infrastructure, argument parsing, and error handling are solid.
- **FastAPI Server** (`app.py`): Add analysis API endpoints. Server infrastructure, middleware, health checks, and Pydantic response models are production-ready.
- **Configuration Management** (`core/config.py`): Extend `AgentConfig` or create `AnalysisConfig` for repo targeting, analysis depth, language filters.
- **Python AST Parsing** (`input_optimizer/engine/cai3_*.py`): Could be extracted and adapted as a Python-specific symbol extractor when SCIP is unavailable. Would need significant refactoring to separate from compression logic.

### Must Be Built (does not exist)
1. **SCIP Indexing Pipeline** — Language detection, SCIP binary management, index storage, temporal indexing across commits. This is foundational; almost everything else depends on it.
2. **Dependency Graph (rustworkx)** — Graph construction from SCIP data, node/edge types, query operations (BFS, cycle detection, centrality, connected components). Second foundational piece.
3. **Temporal Analysis** — Revert detection, oscillation scoring, zombie patterns, stability metrics, co-change coupling. Requires git history parsing infrastructure.
4. **Risk Scoring** — Formula design, signal aggregation, deterministic scoring, calibrated baselines. Depends on temporal analysis + dependency graph.
5. **Domain/Architecture Detection** — Directory-based grouping, graph-based clustering (community detection), boundary identification, cross-domain coupling.
6. **Blast Radius Calculation** — BFS traversal with edge weights, hotspot detection, impact scoring. Depends on dependency graph.
7. **Chesterton's Fence / Living Legends** — Historical context analysis combining commit messages, temporal patterns, and optionally LLM reasoning.
8. **Report Generation** — Markdown/HTML/PDF templates, section generators, visualizations, executive summary. This is the MRI product itself.
9. **MRI Data Models** — `RiskAssessment`, `BlastRadiusResult`, `AffectedNode`, `TemporalPattern`, `ArchitectureDomain`, `SymbolNode`, `DependencyEdge`, `MRIReport`, etc.
10. **MCP Tools** (if needed) — MCP server, tool definitions, schema contracts. Could be deferred to v2.
11. **Sentinel / Guardrail System** — Likely out of scope for a read-only MRI product.

### Estimated Complexity

| Component | Size Estimate | Dependencies | Priority |
|-----------|--------------|--------------|----------|
| SCIP Indexing Pipeline | Large — requires multi-language support, binary management, protobuf parsing | External: scip-python, scip-typescript, protobuf | P0 (foundational) |
| Dependency Graph | Large — core data structure, many query operations | External: rustworkx/networkx; Internal: SCIP pipeline | P0 (foundational) |
| Temporal Analysis | Large — multiple sub-systems (revert, oscillation, zombie, co-change) | Internal: git history parser | P0 (core MRI value) |
| Risk Scoring | Medium — formula design, signal aggregation | Internal: temporal analysis, dependency graph | P1 |
| Domain Detection | Medium — directory heuristics + graph clustering | Internal: dependency graph | P1 |
| Blast Radius | Medium — BFS with weights, hotspot detection | Internal: dependency graph | P1 |
| MRI Data Models | Small-Medium — Pydantic/dataclass definitions | None | P0 (define first) |
| Report Generation | Medium-Large — templates, formatting, visualizations | Internal: all analysis components | P1 |
| Chesterton's Fence | Medium — historical context assembly, optional LLM | Internal: temporal analysis, git history | P2 |
| MCP Tools | Medium — server setup, tool definitions | Internal: analysis components | P2 (defer to v2) |
| Sentinel System | N/A for MRI | N/A | Not needed |
| CLI Commands | Small — add commands to existing framework | Internal: analysis orchestrator | P1 |
| API Endpoints | Small — add routes to existing FastAPI server | Internal: analysis orchestrator | P2 |

### Build Order Recommendation

```
Phase 0: Foundation
├── Define MRI data models (all Pydantic/dataclass types)
├── SCIP Indexing Pipeline (multi-language)
└── Dependency Graph Construction (rustworkx)

Phase 1: Core Analysis
├── Temporal Analysis (git history → revert/oscillation/zombie/co-change)
├── Risk Scoring (combine signals from temporal + graph)
├── Domain/Architecture Detection (directory + graph clustering)
└── Blast Radius Calculation (BFS on dependency graph)

Phase 2: Output
├── Report Generation (Markdown + JSON at minimum)
├── CLI Commands (analyze, report)
└── Chesterton's Fence / Living Legends

Phase 3: Polish (optional for v1)
├── MCP Tools
├── API Endpoints
├── HTML/PDF reports
└── Visualizations
```

### Honest Assessment

This codebase provides **zero** analytical capability relevant to Codebase MRI. It is a token compression tool. The MRI product must be built from the ground up.

However, the codebase demonstrates competent Python engineering: proper AST handling, production-grade config management, working CLI/API infrastructure, Docker deployment, and monitoring. These patterns and infrastructure pieces (especially the CLI, FastAPI server, and config system) can be extended rather than replaced.

The gap between "what exists" and "what MRI needs" is not a modification effort — it is a greenfield build that happens to share a repository with an existing compression tool.
