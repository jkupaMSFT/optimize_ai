#!/bin/bash
# Comprehensive cURL Examples for OptimizeAI API

BASE_URL="http://localhost:8000"

echo "=== OptimizeAI API cURL Examples ==="

# Health Check
echo "1. Health Check:"
curl -X GET "$BASE_URL/health" | jq '.'
echo ""

# Basic Minification
echo "2. Basic Minification:"
curl -X POST "$BASE_URL/minify" \
  -H "Content-Type: application/json" \
  -d '{
    "code": "def hello():\n    print('"'"'Hello, World!'"'"')",
    "compress_strings": true,
    "compress_vars": true
  }' | jq '.'
echo ""

# Minification with Stats
echo "3. Minification with Statistics:"
curl -X POST "$BASE_URL/minify/stats" \
  -H "Content-Type: application/json" \
  -d '{
    "code": "class Test:\n    def __init__(self):\n        self.value = 42",
    "compress_strings": true,
    "compress_vars": true
  }' | jq '.'
echo ""

# SudoLang Translation
echo "4. SudoLang Translation:"
curl -X POST "$BASE_URL/translate/sudolang" \
  -H "Content-Type: application/json" \
  -d '{
    "code": "for i in range(5):\n    if i % 2 == 0:\n        print(i)"
  }' | jq '.'
echo ""

# SynthLang Translation
echo "5. SynthLang Translation:"
curl -X POST "$BASE_URL/translate/synthlang" \
  -H "Content-Type: application/json" \
  -d '{
    "code": "def add(a, b):\n    return a + b"
  }' | jq '.'
echo ""

# Semantic Compression
echo "6. Semantic Compression:"
curl -X POST "$BASE_URL/compress/semantic" \
  -H "Content-Type: application/json" \
  -d '{
    "code": "def process(data):\n    results = []\n    for item in data:\n        results.append(item * 2)\n    return results",
    "compression_level": "moderate"
  }' | jq '.'
echo ""

# Metrics
echo "7. Prometheus Metrics:"
curl -X GET "$BASE_URL/metrics"
echo ""

echo "=== All cURL examples completed ==="
