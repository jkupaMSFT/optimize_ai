# Optimize AI API Reference

This document provides a comprehensive reference for the core APIs in Optimize AI, focusing on key components for compression, translation, and session management. All APIs are designed for asynchronous use where applicable, supporting Python 3.8+. For full source code and examples, refer to the GitHub repository.

## Table of Contents

- [Core Components](#core-components)
  - [SecureSessionManager](#securesessionmanager)
- [Input Optimizer](#input-optimizer)
  - [WaterfallCompressor](#waterfallcompressor)
- [Output Translator](#output-translator)
  - [CAIToPythonTranslator](#caitopythontranslator)
- [Validation](#validation)
  - [SemanticValidator](#semanticvalidator)
- [Configuration](#configuration)
  - [ConfigManager](#configmanager)
- [Error Handling](#error-handling)
- [Examples](#examples)

## Core Components

### SecureSessionManager

The `SecureSessionManager` handles creation, retrieval, and cleanup of compression sessions securely.

#### create_session

Creates a new session for a file.

- **Parameters**:
  - `file_path`: `Path` - Path to the Python file.
  - `agent`: `str` - Agent type (e.g., 'vscode', 'cursor', 'claude').
  - `compressed_content`: `str` - Compressed content from the compressor.
  - `metadata`: `Dict[str, Any]` (optional) - Additional metadata.

- **Returns**: `str` - Session ID.

- **Raises**: `ValueError` if invalid parameters.

- **Example**:
  ```python
  from core.session_manager import SecureSessionManager
  from pathlib import Path

  mgr = SecureSessionManager()
  sid = mgr.create_session(Path('example.py'), 'vscode', 'compressed_content', {'key': 'value'})
  print(sid)  # Outputs: unique session ID
  ```

#### get_session

Retrieves a session by ID.

- **Parameters**:
  - `session_id`: `str` - Session ID.

- **Returns**: `Session` or `None` if not found or expired.

- **Example**:
  ```python
  session = mgr.get_session('session_id_123')
  if session:
      print(session.compressed_content)
  ```

#### cleanup_expired

Cleans up expired sessions.

- **Parameters**: None (or optional timeout).

- **Returns**: None.

- **Example**:
  ```python
  mgr.cleanup_expired()
  ```

## Input Optimizer

### WaterfallCompressor

Compresses Python code using multi-tier waterfall approach.

#### compress_file

Compresses a file.

- **Parameters**:
  - `file_path`: `Path` - Path to file.
  - `tier`: `CompressionTier` (optional) - Force specific tier.

- **Returns**: `CompressionResult` - With content, tokens, ratio, tier_used.

- **Raises**: `ValueError` if non-Python file or too large.

- **Example**:
  ```python
  from input_optimizer.engine.waterfall_compressor import WaterfallCompressor
  from pathlib import Path

  compressor = WaterfallCompressor()
  result = compressor.compress_file(Path('example.py'))
  print(result.content)  # Compressed CAI format
  print(f"Reduction: {result.compression_ratio}%")
  ```

## Output Translator

### CAIToPythonTranslator

Translates CAI back to Python.

#### translate

Translates CAI content.

- **Parameters**:
  - `cai_content`: `str` - CAI formatted string.

- **Returns**: `TranslationResult` - With python_code, success, similarity_score, errors.

- **Raises**: `ValueError` on invalid CAI.

- **Example**:
  ```python
  from output_translator.core.translator import CAIToPythonTranslator

  translator = CAIToPythonTranslator()
  result = translator.translate('F[func()->return 42]')
  if result.success:
      print(result.python_code)  # def func():\n    return 42
  ```

## Validation

### SemanticValidator

Validates translation similarity (if implemented; otherwise use utils.metrics).

#### validate

Validates similarity.

- **Parameters**:
  - `original`: `str` - Original code.
  - `translated`: `str` - Translated code.

- **Returns**: `float` - Similarity score (0-1).

- **Example**:
  ```python
  from utils.metrics import calculate_similarity  # If separate

  similarity = calculate_similarity(original_code, translated_code)
  print(f"Similarity: {similarity * 100:.1f}%")
  ```

## Configuration

### ConfigManager

Manages configurations (if implemented; load from env/files).

#### get_config

Retrieves config value.

- **Parameters**:
  - `key`: `str` - Config key.

- **Returns**: `Any` - Config value.

- **Example**:
  ```python
  # Assuming ConfigManager exists
  from core.config_manager import ConfigManager

  config = ConfigManager()
  value = config.get_config('max_context_tokens')
  ```

## Error Handling

All methods raise specific exceptions:
- `ValueError`: Invalid input.
- `FileNotFoundError`: Missing file.
- `RuntimeError`: Internal failures.

Log errors using the provided logger.

## Examples

### Full Flow

```python
from pathlib import Path
from input_optimizer.engine.waterfall_compressor import WaterfallCompressor
from output_translator.core.translator import CAIToPythonTranslator
from core.session_manager import SecureSessionManager

compressor = WaterfallCompressor()
result = compressor.compress_file(Path('script.py'))

mgr = SecureSessionManager()
sid = mgr.create_session(Path('script.py'), 'vscode', result.content, {})

translator = CAIToPythonTranslator()
trans_result = translator.translate(result.content)

print(f"Translated: {trans_result.python_code}")
```

For more, see tests/ and examples/ directories.