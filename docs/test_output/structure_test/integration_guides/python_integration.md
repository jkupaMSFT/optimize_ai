# Python Integration Guide for OptimizeAI

This guide shows how to integrate OptimizeAI into your Python applications.

## Installation

```bash
pip install requests  # For API communication
```

## Basic Client Class

```python
import requests
import json
from typing import Dict, Any, Optional

class OptimizeAIClient:
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
        self.session = requests.Session()
    
    def minify_code(self, code: str, **options) -> Dict[str, Any]:
        """Minify Python code"""
        response = self.session.post(
            f"{self.base_url}/minify",
            json={"code": code, **options}
        )
        response.raise_for_status()
        return response.json()
    
    def translate_to_sudolang(self, code: str) -> Dict[str, Any]:
        """Translate Python to SudoLang"""
        response = self.session.post(
            f"{self.base_url}/translate/sudolang",
            json={"code": code}
        )
        response.raise_for_status()
        return response.json()
    
    def semantic_compress(self, code: str, level: str = "moderate") -> Dict[str, Any]:
        """Perform semantic compression"""
        response = self.session.post(
            f"{self.base_url}/compress/semantic",
            json={"code": code, "compression_level": level}
        )
        response.raise_for_status()
        return response.json()
    
    def health_check(self) -> Dict[str, Any]:
        """Check API health"""
        response = self.session.get(f"{self.base_url}/health")
        response.raise_for_status()
        return response.json()

# Usage example
client = OptimizeAIClient()

# Minify code
code_to_minify = """
def fibonacci(n):
    if n <= 1:
        return n
    return fibonacci(n-1) + fibonacci(n-2)
"""

result = client.minify_code(code_to_minify)
print(f"Compression: {result['compression_percentage']:.1f}%")
print(f"Minified: {result['minified_code']}")
```

## Async Client

```python
import aiohttp
import asyncio

class AsyncOptimizeAIClient:
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
    
    async def minify_code(self, code: str, **options) -> Dict[str, Any]:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.base_url}/minify",
                json={"code": code, **options}
            ) as response:
                return await response.json()

# Usage
async def main():
    client = AsyncOptimizeAIClient()
    result = await client.minify_code("def hello(): print('world')")
    print(result)

asyncio.run(main())
```

## Batch Processing

```python
def batch_minify(codes: list, client: OptimizeAIClient):
    """Process multiple code snippets"""
    results = []
    for i, code in enumerate(codes):
        try:
            result = client.minify_code(code)
            results.append({
                'index': i,
                'success': True,
                'result': result
            })
        except Exception as e:
            results.append({
                'index': i,
                'success': False,
                'error': str(e)
            })
    return results
```

## Error Handling

```python
import requests
from requests.exceptions import RequestException, HTTPError, Timeout

def safe_minify(client: OptimizeAIClient, code: str, retries: int = 3):
    """Minify with error handling and retries"""
    for attempt in range(retries):
        try:
            return client.minify_code(code)
        except Timeout:
            print(f"Timeout on attempt {attempt + 1}")
            if attempt == retries - 1:
                raise
        except HTTPError as e:
            if e.response.status_code >= 500:
                print(f"Server error on attempt {attempt + 1}: {e}")
                if attempt == retries - 1:
                    raise
            else:
                raise  # Don't retry client errors
        except RequestException as e:
            print(f"Request error on attempt {attempt + 1}: {e}")
            if attempt == retries - 1:
                raise
```
