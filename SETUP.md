# Setup Instructions

## Quick Start

1. **Install dependencies:**

   ```bash
   pip install -r requirements.txt
   ```

2. **Verify setup:**

   ```bash
   python verify_setup.py
   ```

3. **Run the API server:**

   ```bash
   uvicorn app:app --reload
   ```

4. **Visit API documentation:**
   Open http://localhost:8000/docs in your browser

## Development Setup

For development work, install additional dev dependencies:

```bash
pip install -r requirements-dev.txt
```

## Package Structure

The project now uses a proper package structure:

```python
# Import from package level
from input_optimizer.engine import minify_code, python_to_sudolang
from input_optimizer.engine.translators import python_to_synthlang
from input_optimizer.engine.mapping import ASTMapper, SourceMap

# Tests are now organized within the package
from input_optimizer.tests.test_adapter_integration import TestAdapterIntegration

# Samples are also within the package
from input_optimizer.samples.minifier.minify_samples import *
```

**Directory Structure:**

```
input_optimizer/
├── engine/           # Core optimization engine
├── tests/           # All test files
├── samples/         # Sample scripts and examples
└── __init__.py

utils/               # Utility modules (root level)
```

## Dependencies

### Core Dependencies

- **FastAPI**: Web framework for the API
- **httpx**: HTTP client for testing
- **tiktoken**: Token estimation
- **intervaltree**: Efficient interval operations
- **pydantic**: Data validation

### Development Dependencies

- **pytest**: Testing framework
- **black**: Code formatting
- **httpx**: Required for FastAPI TestClient

## Running Tests

```bash
# Run all tests (from the new location)
python -m pytest input_optimizer/tests/

# Run specific test file
python -m pytest input_optimizer/tests/test_adapter_integration.py

# Run with verbose output
python -m pytest input_optimizer/tests/ -v
```
