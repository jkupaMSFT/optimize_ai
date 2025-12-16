# OptimizeAI API

**Version:** 1.0.0  
**Generated:** 2025-08-03 19:19:20

## Overview


        ## Overview
        OptimizeAI provides intelligent code compression and translation for AI workflows.
        
        ## Key Features
        - **40-87% token reduction** across different compression tiers
        - **Semantic preservation** maintaining code functionality
        - **Multi-tier compression** (basic, moderate, aggressive, maximum)
        - **Real-time processing** with comprehensive monitoring
        - **Translation support** for SudoLang and SynthLang
        - **Chained transformations** for complex workflows
        - **Production monitoring** with Prometheus metrics
        
        ## Quick Start
        ```python
        import requests
        
        # Basic minification
        response = requests.post(
            "http://localhost:8000/minify",
            json={"code": "def hello(): print('world')"}
        )
        result = response.json()
        print(f"Compressed: {result['minified_code']}")
        print(f"Reduction: {result['compression_percentage']:.1f}%")
        ```
        
        ## Compression Tiers
        - **Basic**: Safe compression with variable/string optimization
        - **Moderate**: Balanced approach with semantic analysis  
        - **Aggressive**: High compression with advanced techniques
        - **Maximum**: Extreme compression for maximum token reduction
        
        ## Translation Languages
        - **SudoLang**: Natural language pseudocode representation
        - **SynthLang**: Synthetic compact language for AI processing
        
        ## Monitoring & Analytics
        - Real-time performance metrics via `/health` and `/metrics`
        - Comprehensive compression analytics and reporting
        - Error tracking with detailed logging
        - WebSocket support for live monitoring
        
        ## Rate Limits
        - Standard: 1000 requests/hour
        - Premium: 10000 requests/hour
        - Enterprise: Unlimited
        
        ## Support
        - Documentation: `/docs` (this page)
        - Health Check: `/health`
        - Metrics: `/metrics`
        - Dashboard: `/dashboard`
        

## Base URL
```
http://localhost:8000
```

## Authentication
Currently, no authentication is required for API access. This may change in future versions.

## Rate Limiting
- Standard: 1000 requests/hour
- Premium: 10000 requests/hour  
- Enterprise: Unlimited

---

## API Endpoints

### Health

#### `GET /health`

**Summary:** Health Check

**Description:** Health check endpoint to verify service status.

**Response (200):**
```json
{
  "status": "success"
}
```

**Code Examples:**

**Python Requests:**
```python
import requests

response = requests.get("http://localhost:8000/health")
health = response.json()
print(f"Status: {health['status']}")
print(f"Uptime: {health['uptime_seconds']:.1f}s")
```

**cURL:**
```curl
curl -X GET "http://localhost:8000/health" \
```


---

### Dashboard

#### `GET /dashboard`

**Summary:** Dashboard

**Description:** Interactive web dashboard for demos

**Response (200):**
```json
{
  "status": "success"
}
```

**Code Examples:**

**Python Requests:**
```python
import requests

response = requests.get("http://localhost:8000/dashboard")
print(response.json())
```

**cURL:**
```curl
curl -X GET "http://localhost:8000/dashboard" \
```


---

### Minification

#### `POST /minify`

**Summary:** Minify Python Code

**Description:** Minify Python code with comprehensive logging and metrics.

This endpoint provides fast Python code minification with:
- Comments and whitespace removal
- Optional constant folding and boolean optimization
- Optional variable name shortening
- Comprehensive error handling and validation
- Performance metrics and logging
- Session tracking for compression flows

Token estimation uses len(minified)//4 which approximates:
- 4 characters per token on average for minified Python code
- Accounts for reduced whitespace and shorter identifiers
- Provides conservative estimates suitable for LLM context planning

**Request Body:**
```json
{
  "code": "def example(): pass"
}
```

**Response (200):**
```json
{
  "status": "success"
}
```

**Response (422):**
```json
{
  "error": "Error occurred",
  "status": "error"
}
```

**Code Examples:**

**Python Requests:**
```python
import requests

response = requests.post(
    "http://localhost:8000/minify",
    json={
        "code": "def hello_world():\n    print('Hello, World!')",
        "compress_strings": True,
        "compress_vars": True
    }
)
print(response.json())
```

**cURL:**
```curl
curl -X POST "http://localhost:8000/minify" \
  -H "Content-Type: application/json" \
  -d '{"code": "def example(): pass"}'
```


---

#### `POST /minify/stats`

**Summary:** Minify With Detailed Stats

**Description:** Minify Python code and return detailed statistics.

This endpoint provides the same minification as /minify but includes
comprehensive statistics about the transformation process.

**Request Body:**
```json
{
  "code": "def example(): pass"
}
```

**Response (200):**
```json
{
  "status": "success"
}
```

**Response (422):**
```json
{
  "error": "Error occurred",
  "status": "error"
}
```

**Code Examples:**

**Python Requests:**
```python
import requests

response = requests.post(
    "http://localhost:8000/minify/stats", 
    json={
        "code": "class Calculator:\n    def add(self, a, b):\n        return a + b",
        "compress_strings": True,
        "compress_vars": True
    }
)
stats = response.json()
print(f"Compression: {stats['compression_percentage']:.1f}%")
```

**cURL:**
```curl
curl -X POST "http://localhost:8000/minify/stats" \
  -H "Content-Type: application/json" \
  -d '{"code": "def example(): pass"}'
```


---

#### `POST /minify/otpm`

**Summary:** Minify With Otpm Awareness

**Description:** OTPM-aware Python code minification with adaptive compression.

This endpoint provides intelligent compression based on rate limit status:
- Monitors remaining token percentage
- Adapts compression strategy automatically
- Uses tiktoken for precise token counting
- Logs comprehensive OTPM metrics
- Supports emergency compression modes

**Request Body:**
```json
{
  "code": "def example(): pass"
}
```

**Response (200):**
```json
{
  "status": "success"
}
```

**Response (422):**
```json
{
  "error": "Error occurred",
  "status": "error"
}
```

**Code Examples:**

**Python Requests:**
```python
import requests

response = requests.post("http://localhost:8000/minify/otpm")
print(response.json())
```

**cURL:**
```curl
curl -X POST "http://localhost:8000/minify/otpm" \
  -H "Content-Type: application/json" \
  -d '{"code": "def example(): pass"}'
```


---

### Monitoring

#### `GET /metrics`

**Summary:** Get Service Metrics

**Description:** Get service-level metrics and statistics.

Returns basic service metrics for monitoring and health checking.

**Response (200):**
```json
{
  "status": "success"
}
```

**Code Examples:**

**Python Requests:**
```python
import requests

response = requests.get("http://localhost:8000/metrics")
metrics = response.text
print("Prometheus Metrics:")
print(metrics[:500] + "..." if len(metrics) > 500 else metrics)
```

**cURL:**
```curl
curl -X GET "http://localhost:8000/metrics" \
```


---

### Translation

#### `POST /translate/sudolang`

**Summary:** Translate To Sudolang

**Description:** Translate Python code to SudoLang with comprehensive logging and metrics.

SudoLang is a high-level pseudocode language that represents Python logic
in a more readable, English-like syntax. This endpoint provides:
- Python AST parsing and transformation
- Comprehensive error handling and validation
- Performance metrics and logging
- AST node processing statistics

**Request Body:**
```json
{
  "code": "def example(): pass"
}
```

**Response (200):**
```json
{
  "status": "success"
}
```

**Response (422):**
```json
{
  "error": "Error occurred",
  "status": "error"
}
```

**Code Examples:**

**Python Requests:**
```python
import requests

response = requests.post(
    "http://localhost:8000/translate/sudolang",
    json={
        "code": "for i in range(10):\n    if i % 2 == 0:\n        print(i)"
    }
)
print(response.json()['sudolang_translation'])
```

**cURL:**
```curl
curl -X POST "http://localhost:8000/translate/sudolang" \
  -H "Content-Type: application/json" \
  -d '{"code": "def example(): pass"}'
```


---

#### `POST /translate/sudolang/stats`

**Summary:** Translate To Sudolang With Stats

**Description:** Translate Python code to SudoLang and return detailed statistics.

This endpoint provides the same translation as /translate/sudolang but includes
comprehensive statistics about the transformation process.

**Request Body:**
```json
{
  "code": "def example(): pass"
}
```

**Response (200):**
```json
{
  "status": "success"
}
```

**Response (422):**
```json
{
  "error": "Error occurred",
  "status": "error"
}
```

**Code Examples:**

**Python Requests:**
```python
import requests

response = requests.post("http://localhost:8000/translate/sudolang/stats")
print(response.json())
```

**cURL:**
```curl
curl -X POST "http://localhost:8000/translate/sudolang/stats" \
  -H "Content-Type: application/json" \
  -d '{"code": "def example(): pass"}'
```


---

#### `POST /translate/synthlang`

**Summary:** Translate To Synthlang

**Description:** Translate Python code to SynthLang with comprehensive logging and metrics.

SynthLang is a symbolic mathematical notation for Python code that uses
mathematical symbols and operators to represent programming constructs.
This endpoint provides:
- Compact or formatted output options
- Python AST parsing and transformation
- Comprehensive error handling and validation
- Performance metrics and logging
- Size reduction/expansion tracking

**Request Body:**
```json
{
  "code": "def example(): pass"
}
```

**Response (200):**
```json
{
  "status": "success"
}
```

**Response (422):**
```json
{
  "error": "Error occurred",
  "status": "error"
}
```

**Code Examples:**

**Python Requests:**
```python
import requests

response = requests.post(
    "http://localhost:8000/translate/synthlang",
    json={
        "code": "def fibonacci(n):\n    return n if n <= 1 else fibonacci(n-1) + fibonacci(n-2)"
    }
)
print(response.json()['synthlang_translation'])
```

**cURL:**
```curl
curl -X POST "http://localhost:8000/translate/synthlang" \
  -H "Content-Type: application/json" \
  -d '{"code": "def example(): pass"}'
```


---

#### `POST /translate/synthlang/stats`

**Summary:** Translate To Synthlang With Stats

**Description:** Translate Python code to SynthLang and return detailed statistics.

This endpoint provides the same translation as /translate/synthlang but includes
comprehensive statistics about the transformation process, including method comparison.

**Request Body:**
```json
{
  "code": "def example(): pass"
}
```

**Response (200):**
```json
{
  "status": "success"
}
```

**Response (422):**
```json
{
  "error": "Error occurred",
  "status": "error"
}
```

**Code Examples:**

**Python Requests:**
```python
import requests

response = requests.post("http://localhost:8000/translate/synthlang/stats")
print(response.json())
```

**cURL:**
```curl
curl -X POST "http://localhost:8000/translate/synthlang/stats" \
  -H "Content-Type: application/json" \
  -d '{"code": "def example(): pass"}'
```


---

### Chained Transformations

#### `POST /transform/minify-synthlang`

**Summary:** Minify Then Synthlang

**Description:** Chain minification and SynthLang translation for optimal compression.

This endpoint performs a two-stage transformation:
1. Minify Python code using specified depth (1-4)
2. Translate minified code to SynthLang

This chaining approach typically achieves better compression than
either transformation alone, while maintaining semantic equivalence.

**Request Body:**
```json
{
  "code": "def example(): pass"
}
```

**Response (200):**
```json
{
  "status": "success"
}
```

**Response (422):**
```json
{
  "error": "Error occurred",
  "status": "error"
}
```

**Code Examples:**

**Python Requests:**
```python
import requests

response = requests.post("http://localhost:8000/transform/minify-synthlang")
print(response.json())
```

**cURL:**
```curl
curl -X POST "http://localhost:8000/transform/minify-synthlang" \
  -H "Content-Type: application/json" \
  -d '{"code": "def example(): pass"}'
```


---

#### `POST /transform/minify-sudolang`

**Summary:** Minify Then Sudolang

**Description:** Chain minification and SudoLang translation for optimal compression.

This endpoint performs a two-stage transformation:
1. Minify Python code using specified depth (1-4)
2. Translate minified code to SudoLang

This chaining approach typically achieves better compression than
either transformation alone, while maintaining semantic equivalence.

**Request Body:**
```json
{
  "code": "def example(): pass"
}
```

**Response (200):**
```json
{
  "status": "success"
}
```

**Response (422):**
```json
{
  "error": "Error occurred",
  "status": "error"
}
```

**Code Examples:**

**Python Requests:**
```python
import requests

response = requests.post("http://localhost:8000/transform/minify-sudolang")
print(response.json())
```

**cURL:**
```curl
curl -X POST "http://localhost:8000/transform/minify-sudolang" \
  -H "Content-Type: application/json" \
  -d '{"code": "def example(): pass"}'
```


---

#### `POST /transform/pipeline-analysis`

**Summary:** Comprehensive Pipeline Analysis

**Description:** Comprehensive pipeline analysis: test all minification depths and translation methods.

This endpoint performs extensive analysis:
1. Tests minification at depths 1-4
2. Tests SynthLang translation (readable and compact modes)
3. Tests chained transformations (minify → translate)
4. Returns detailed metrics for all methods
5. Identifies the best performing transformation

This is ideal for finding the optimal transformation pipeline for your code.

**Request Body:**
```json
{
  "code": "def example(): pass"
}
```

**Response (200):**
```json
{
  "status": "success"
}
```

**Response (422):**
```json
{
  "error": "Error occurred",
  "status": "error"
}
```

**Code Examples:**

**Python Requests:**
```python
import requests

response = requests.post("http://localhost:8000/transform/pipeline-analysis")
print(response.json())
```

**cURL:**
```curl
curl -X POST "http://localhost:8000/transform/pipeline-analysis" \
  -H "Content-Type: application/json" \
  -d '{"code": "def example(): pass"}'
```


---

### Semantic Compression

#### `POST /compress/semantic`

**Summary:** Compress Semantic

**Description:** Apply semantic-aware compression that balances token efficiency with similarity preservation.

This endpoint uses intelligent compression strategies including:
- AST-aware identifier compression
- Smart docstring optimization
- Context-aware token reduction
- Semantic notation substitution

Returns detailed analysis with stage-by-stage breakdown.

**Request Body:**
```json
{
  "code": "def example(): pass"
}
```

**Response (200):**
```json
{
  "status": "success"
}
```

**Response (422):**
```json
{
  "error": "Error occurred",
  "status": "error"
}
```

**Code Examples:**

**Python Requests:**
```python
import requests

response = requests.post(
    "http://localhost:8000/compress/semantic",
    json={
        "code": "def process_data(data):\n    results = []\n    for item in data:\n        if item.is_valid():\n            results.append(item.transform())\n    return results",
        "compression_level": "moderate"
    }
)
compressed = response.json()
print(f"Original: {compressed['original_tokens']} tokens")
print(f"Compressed: {compressed['compressed_tokens']} tokens")
```

**cURL:**
```curl
curl -X POST "http://localhost:8000/compress/semantic" \
  -H "Content-Type: application/json" \
  -d '{"code": "def example(): pass"}'
```


---

#### `POST /compress/compare`

**Summary:** Compare Compression Methods

**Description:** Compare different compression methods and provide recommendations.

Analyzes code with both semantic-aware and maximum compression approaches,
then recommends the best method based on compression ratio and similarity preservation.

**Request Body:**
```json
{
  "code": "def example(): pass"
}
```

**Response (200):**
```json
{
  "status": "success"
}
```

**Response (422):**
```json
{
  "error": "Error occurred",
  "status": "error"
}
```

**Code Examples:**

**Python Requests:**
```python
import requests

response = requests.post("http://localhost:8000/compress/compare")
print(response.json())
```

**cURL:**
```curl
curl -X POST "http://localhost:8000/compress/compare" \
  -H "Content-Type: application/json" \
  -d '{"code": "def example(): pass"}'
```


---

## Data Models

### ChainedPipelineResponse

**Type:** object

**Description:** Comprehensive pipeline analysis response with all transformation stages

**Properties:**

- **original_code** (`string`)*: Original Python code
- **minification_stages** (`object`)*: Results for each minification depth
- **translation_stages** (`object`)*: Results for each translation method
- **best_method** (`string`)*: Best performing transformation method
- **best_compression_tokens** (`integer`)*: Tokens for best compression
- **best_reduction_percent** (`number`)*: Best reduction percentage achieved
- **best_similarity_score** (`number`)*: Similarity score for best method
- **original_tokens** (`integer`)*: Original token count
- **processing_time_ms** (`number`)*: Total processing time in milliseconds
- **methods_analyzed** (`integer`)*: Number of transformation methods analyzed

---

### ChainedTransformRequest

**Type:** object

**Properties:**

- **code** (`string`)*: Python source code to transform
- **minify_depth** (`unknown`): Minification depth (1-4) before translation
- **compact** (`unknown`): Use compact mode for final translation

---

### ChainedTransformResponse

**Type:** object

**Properties:**

- **original_code** (`string`)*: Original Python code
- **minified_code** (`string`)*: Minified Python code
- **final_translated** (`string`)*: Final translated code
- **translation_type** (`string`)*: Type of translation (synthlang or sudolang)
- **original_size** (`integer`)*: Original code size in characters
- **original_tokens** (`integer`)*: Estimated original tokens
- **minified_size** (`integer`)*: Minified code size in characters
- **minified_tokens** (`integer`)*: Estimated minified tokens
- **minification_reduction_percent** (`number`)*: Minification size reduction percentage
- **final_size** (`integer`)*: Final translated code size in characters
- **final_tokens** (`integer`)*: Estimated final tokens
- **overall_reduction_percent** (`number`)*: Overall size reduction percentage
- **processing_time_ms** (`number`)*: Total processing time in milliseconds
- **minify_depth_used** (`integer`)*: Minification depth used
- **compact_mode** (`boolean`)*: Whether compact mode was used

---

### CompressionComparisonRequest

**Type:** object

**Properties:**

- **code** (`string`)*: Python source code to analyze
- **include_maximum** (`unknown`): Include maximum compression analysis
- **similarity_threshold** (`unknown`): Similarity threshold for semantic compression

---

### CompressionComparisonResponse

**Type:** object

**Properties:**

- **original** (`object`)*: Original code analysis
- **semantic_compression** (`object`)*: Semantic compression results
- **maximum_compression** (`unknown`): Maximum compression results
- **recommendation** (`object`)*: Recommended compression method with reason
- **analysis** (`object`)*: Code characteristics analysis

---

### HTTPValidationError

**Type:** object

**Properties:**

- **detail** (`array`): No description

---

### HealthResponse

**Type:** object

**Properties:**

- **status** (`string`)*: Service health status
- **timestamp** (`string`)*: Current timestamp
- **version** (`string`)*: API version
- **uptime_seconds** (`number`)*: Service uptime in seconds

---

### MinifyRequest

**Type:** object

**Properties:**

- **code** (`string`)*: Python source code to minify
- **aggressive** (`unknown`): Enable aggressive optimizations (variable name shortening)
- **validate_output** (`unknown`): Validate minified output by re-parsing
- **compression_depth** (`unknown`): Compression level (1-4): 1=basic, 2=constants, 3=variables, 4=aggressive
- **compression_type** (`unknown`): Compression type: 'minimal', 'standard', 'aggressive', 'emergency'

---

### MinifyResponse

**Type:** object

**Properties:**

- **minified** (`string`)*: Minified Python code
- **estimated_tokens** (`integer`)*: Estimated token count using len(minified)//4
- **original_size** (`integer`)*: Original code size in characters
- **minified_size** (`integer`)*: Minified code size in characters
- **size_reduction_percent** (`number`)*: Percentage reduction in size
- **processing_time_ms** (`number`)*: Processing time in milliseconds
- **compression_depth_used** (`integer`)*: Compression depth level used
- **session_id** (`unknown`): Session ID for tracking this compression
- **tokens_saved** (`unknown`): Number of tokens saved
- **compression_ratio** (`unknown`): Compression ratio achieved

---

### MinifyStatsResponse

**Type:** object

**Properties:**

- **minified** (`string`)*: Minified Python code
- **estimated_tokens** (`integer`)*: Estimated token count using len(minified)//4
- **stats** (`object`)*: Detailed minification statistics

---

### OTPMMinifyRequest

**Type:** object

**Properties:**

- **code** (`string`)*: Python source code to minify
- **remaining_pct** (`unknown`): Percentage of remaining tokens in rate limit window
- **compression_type** (`unknown`): Compression type: 'auto', 'minimal', 'standard', 'aggressive', 'emergency'
- **model_type** (`unknown`): Model type for token counting: 'gpt-4', 'gpt-3.5-turbo', 'claude'
- **rate_limit_headers** (`unknown`): Rate limit headers from upstream API

---

### OTPMMinifyResponse

**Type:** object

**Properties:**

- **minified** (`string`)*: Minified Python code
- **estimated_tokens** (`integer`)*: Estimated token count using tiktoken
- **original_tokens** (`integer`)*: Original code token count
- **token_reduction_percent** (`number`)*: Percentage reduction in tokens
- **compression_type_used** (`string`)*: Compression type applied
- **otpm_status** (`string`)*: OTPM status: 'safe', 'warning', 'critical', 'summarized'
- **remaining_pct** (`number`)*: Remaining tokens percentage
- **processing_time_ms** (`number`)*: Processing time in milliseconds
- **operation_id** (`string`)*: Unique operation identifier for tracking

---

### SemanticCompressionRequest

**Type:** object

**Properties:**

- **code** (`string`)*: Python source code to compress
- **similarity_threshold** (`unknown`): Minimum similarity score to maintain
- **preserve_semantics** (`unknown`): Enable semantic preservation mode

---

### SemanticCompressionResponse

**Type:** object

**Properties:**

- **original_code** (`string`)*: Original Python code
- **compressed_code** (`string`)*: Compressed Python code
- **original_tokens** (`integer`)*: Original token count
- **compressed_tokens** (`integer`)*: Compressed token count
- **tokens_saved** (`integer`)*: Number of tokens saved
- **compression_ratio** (`number`)*: Compression ratio (0.0 to 1.0)
- **compression_percentage** (`number`)*: Compression percentage
- **similarity_score** (`number`)*: Semantic similarity score (0.0 to 1.0)
- **meets_threshold** (`boolean`)*: Whether similarity meets threshold
- **stage_breakdown** (`object`)*: Breakdown by compression stage
- **processing_time_ms** (`number`)*: Processing time in milliseconds

---

### SudoLangResponse

**Type:** object

**Properties:**

- **translated** (`string`)*: SudoLang translated code
- **original_size** (`integer`)*: Original code size in characters
- **translated_size** (`integer`)*: Translated code size in characters
- **processing_time_ms** (`number`)*: Processing time in milliseconds
- **ast_nodes_processed** (`integer`)*: Number of AST nodes processed

---

### SudoLangStatsResponse

**Type:** object

**Properties:**

- **translated** (`string`)*: SudoLang translated code
- **stats** (`object`)*: Detailed translation statistics

---

### SynthLangResponse

**Type:** object

**Properties:**

- **translated** (`string`)*: SynthLang translated code
- **original_size** (`integer`)*: Original code size in characters
- **translated_size** (`integer`)*: Translated code size in characters
- **processing_time_ms** (`number`)*: Processing time in milliseconds
- **ast_nodes_processed** (`integer`)*: Number of AST nodes processed
- **compact_mode** (`boolean`)*: Whether compact mode was used
- **size_reduction_percent** (`number`)*: Percentage change in size (negative means increase)

---

### SynthLangStatsResponse

**Type:** object

**Properties:**

- **translated** (`string`)*: SynthLang translated code
- **original_size** (`integer`)*: Original code size in characters
- **translated_size** (`integer`)*: Translated code size in characters
- **processing_time_ms** (`number`)*: Processing time in milliseconds
- **ast_nodes_processed** (`integer`)*: Number of AST nodes processed
- **compact_mode** (`boolean`)*: Whether compact mode was used
- **size_reduction_percent** (`number`)*: Percentage change in size
- **translation_method** (`string`)*: Translation method used

---

### TranslateRequest

**Type:** object

**Properties:**

- **code** (`string`)*: Python source code to translate
- **compact** (`unknown`): Enable compact output (SynthLang only)
- **indent_size** (`unknown`): Indentation size for formatted output

---

### ValidationError

**Type:** object

**Properties:**

- **loc** (`array`)*: No description
- **msg** (`string`)*: No description
- **type** (`string`)*: No description

---

## Complete Examples

### Basic Minification Workflow
```python
import requests

# Simple minification
response = requests.post(
    "http://localhost:8000/minify",
    json={
        "code": '''
def calculate_fibonacci(n):
    if n <= 1:
        return n
    return calculate_fibonacci(n-1) + calculate_fibonacci(n-2)
        ''',
        "compress_strings": True,
        "compress_vars": True
    }
)

result = response.json()
print(f"Original: {result['original_length']} chars")
print(f"Minified: {result['minified_length']} chars") 
print(f"Compression: {result['compression_percentage']:.1f}%")
print(f"Code: {result['minified_code']}")
```

### Translation Workflow
```python
import requests

# Translate to SudoLang
sudo_response = requests.post(
    "http://localhost:8000/translate/sudolang",
    json={
        "code": '''
data = [1, 2, 3, 4, 5]
filtered = [x for x in data if x % 2 == 0]
print(filtered)
        '''
    }
)

# Translate to SynthLang
synth_response = requests.post(
    "http://localhost:8000/translate/synthlang", 
    json={
        "code": '''
def process_items(items):
    return [item.upper() for item in items if len(item) > 3]
        '''
    }
)

print("SudoLang:", sudo_response.json()['sudolang_translation'])
print("SynthLang:", synth_response.json()['synthlang_translation'])
```

### Semantic Compression
```python
import requests

response = requests.post(
    "http://localhost:8000/compress/semantic",
    json={
        "code": '''
class DataProcessor:
    def __init__(self, config):
        self.config = config
        self.processed_items = []
        
    def process(self, data):
        for item in data:
            if self.validate_item(item):
                processed = self.transform_item(item)
                self.processed_items.append(processed)
        return self.processed_items
        ''',
        "compression_level": "moderate"
    }
)

result = response.json()
print(f"Semantic compression achieved {result['compression_percentage']:.1f}% reduction")
print(f"Similarity score: {result['similarity_score']:.3f}")
```

### Monitoring and Health Checks
```python
import requests
import time

# Check system health
health = requests.get("http://localhost:8000/health").json()
print(f"System Status: {health['status']}")
print(f"Uptime: {health['uptime_seconds']:.1f}s")
print(f"Error Rate: {health['error_rate']:.3f}")

# Get Prometheus metrics
metrics = requests.get("http://localhost:8000/metrics").text
print("Active metrics collected:")
print(metrics[:500] + "..." if len(metrics) > 500 else metrics)

# Performance monitoring
start_time = time.time()
response = requests.post("http://localhost:8000/minify", json={"code": "print('test')"})
duration = time.time() - start_time
print(f"Request completed in {duration:.3f}s")
```

---

## Troubleshooting

### Common Issues

#### 1. High Compression Times
**Problem:** Compression takes longer than expected
**Solutions:**
- Use lighter compression tiers for simple code
- Check system load via `/health` endpoint
- Consider semantic compression for complex code

#### 2. Translation Errors  
**Problem:** Translation fails or produces incorrect results
**Solutions:**
- Ensure code is syntactically valid Python
- Check for unsupported language constructs
- Use `/translate/sudolang/stats` for detailed analysis

#### 3. Rate Limiting
**Problem:** Requests are being rate limited
**Solutions:**
- Implement exponential backoff
- Consider premium tier for higher limits
- Batch multiple operations where possible

#### 4. Memory Issues
**Problem:** Large code files cause timeouts
**Solutions:**
- Break large files into smaller chunks
- Use streaming for very large inputs
- Monitor memory usage via metrics

### Performance Optimization

#### Best Practices
1. **Choose Appropriate Compression Tier:**
   - Basic: Simple scripts (< 100 lines)
   - Moderate: Medium complexity (100-500 lines)  
   - Aggressive: Complex applications (500+ lines)
   - Maximum: When maximum compression is critical

2. **Batch Operations:**
   ```python
   # Instead of multiple single requests
   codes = ["code1", "code2", "code3"]
   for code in codes:
       requests.post("/minify", json={"code": code})
   
   # Use pipeline analysis for efficiency
   requests.post("/transform/pipeline-analysis", json={"codes": codes})
   ```

3. **Monitor Performance:**
   ```python
   import time
   start = time.time()
   response = requests.post("/minify", json={"code": code})
   print(f"Request time: {time.time() - start:.3f}s")
   ```

### Support and Contact

- **Documentation:** This comprehensive guide
- **Health Check:** `GET /health` for system status
- **Metrics:** `GET /metrics` for detailed performance data
- **Dashboard:** `GET /dashboard` for web interface

For additional support, monitor the application logs and use the comprehensive error reporting available through the API.

---

*Documentation generated automatically by OptimizeAI Documentation Generator*
