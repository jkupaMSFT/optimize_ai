# Optimize AI

[![PyPI version](https://badge.fury.io/py/optimize-ai.svg)](https://badge.fury.io/py/optimize-ai)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Build Status](https://github.com/optimize-ai/optimize-ai/workflows/CI/badge.svg)](https://github.com/optimize-ai/optimize-ai/actions)
[![Documentation Status](https://readthedocs.org/projects/optimize-ai/badge/?version=latest)](https://optimize-ai.readthedocs.io/en/latest/?badge=latest)

AI-powered code compression for 10x more efficient LLM interactions. Reduce token usage by up to 87% while preserving semantic integrity through the CAI (Compressed AI) format.

## Features

- **Waterfall Compression Tiers**: Multi-level compression (tiny to huge) adapting to code complexity.
- **CAI Format**: Semantic-preserving format for functions (F[]), classes (C[]), imports (I[]), etc.
- **IDE Integrations**: Seamless plugins for VSCode and Cursor with auto-compression, status bar, and commands.
- **CLI Wrapper for Claude Code**: Intercepts commands to compress inputs automatically.
- **Reversible Translation**: Translate CAI back to executable Python with validation.
- **Metrics & Validation**: Token counting, similarity scoring, and error handling.
- **Session Management**: Secure, TTL-based sessions for stateful workflows.
- **CLI Tools**: Compress, translate, manage sessions, and install integrations.

## Installation

Install via pip:

```bash
pip install optimize-ai
```

For development:

```bash
git clone https://github.com/optimize-ai/optimize-ai.git
cd optimize-ai
pip install -e .[dev]
```

Dependencies are managed in `requirements.txt`. Ensure Python >=3.8.

## Quick Start

Compress a Python file:

```bash
optimize-ai compress example.py --output compressed.cai
```

Translate back:

```bash
optimize-ai translate compressed.cai --output translated.py
```

Manage sessions:

```bash
optimize-ai session start example.py --agent vscode
optimize-ai session get <session_id>
```

Install integrations:

```bash
optimize-ai integrate install vscode
```

For full CLI options: `optimize-ai --help`.

## Integrations

- **VSCode/Cursor**: Install via CLI or marketplace (VSCode). Enable in settings for auto-compression on Python files.
- **Claude Code**: Install wrapper: `optimize-ai integrate install claude`. Use `claude-cai` instead of `claude-code`.

See [Integration Guide](docs/integration_guide.md) for details.

## Documentation

- [API Reference](docs/api_reference.md)
- [Architecture](docs/architecture.md)
- [Benchmarking](scripts/benchmark.py) - Run `python scripts/benchmark.py` for performance tests.

Full docs in `/docs` or online at [ReadTheDocs](https://optimize-ai.readthedocs.io).

## Contributing

Contributions welcome! See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

1. Fork the repo.
2. Create a branch: `git checkout -b feature/xyz`.
3. Commit changes: `git commit -am 'Add feature'`.
4. Push: `git push origin feature/xyz`.
5. Submit PR.

Run tests: `pytest`. Format: `black .`. Lint: `flake8`.

## License

MIT License. See [LICENSE](LICENSE).

## Support

- Issues/PRs: [GitHub](https://github.com/optimize-ai/optimize-ai/issues)
- Discussions: [GitHub Discussions](https://github.com/optimize-ai/optimize-ai/discussions)
- Contact: team@optimize-ai.com

