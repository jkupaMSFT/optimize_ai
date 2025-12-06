# OptimizeAI Quick Start Guide

Get up and running with OptimizeAI in under 5 minutes!

## 1. Installation & Setup

### Option A: Docker (Recommended)
```bash
# Clone repository
git clone https://github.com/your-org/optimize-ai.git
cd optimize-ai

# Start with Docker Compose
docker-compose up -d

# Verify it's running
curl http://localhost:8000/health
```

### Option B: Local Installation
```bash
# Install dependencies
pip install -r requirements.txt

# Start the server
python app.py
```

## 2. Your First API Call

```python
import requests

# Basic minification
response = requests.post(
    "http://localhost:8000/minify",
    json={
        "code": "def hello_world():\n    print('Hello, OptimizeAI!')",
        "compress_strings": True,
        "compress_vars": True
    }
)

result = response.json()
print(f"Compression: {result['compression_percentage']:.1f}%")
print(f"Minified: {result['minified_code']}")
```

## 3. Explore Key Features

### Code Translation
```python
# Translate to SudoLang
sudo_response = requests.post(
    "http://localhost:8000/translate/sudolang",
    json={"code": "for i in range(10):\n    print(i)"}
)
print(sudo_response.json()['sudolang_translation'])
```

### Semantic Compression
```python
# Advanced compression with semantic analysis
semantic_response = requests.post(
    "http://localhost:8000/compress/semantic",
    json={
        "code": "def process(data): return [x*2 for x in data if x > 0]",
        "compression_level": "moderate"
    }
)
print(f"Semantic compression: {semantic_response.json()['compression_percentage']:.1f}%")
```

## 4. Monitor Your Usage

```python
# Check system health
health = requests.get("http://localhost:8000/health").json()
print(f"Status: {health['status']}")
print(f"Uptime: {health['uptime_seconds']:.1f}s")

# View metrics
metrics = requests.get("http://localhost:8000/metrics").text
print("System metrics available!")
```

## 5. Web Dashboard

Visit http://localhost:8000/dashboard for a web-based monitoring interface.

## Next Steps

- Check out the [comprehensive API documentation](comprehensive_api_docs.md)
- Explore [integration guides](integration_guides/) for your platform
- Review [performance optimization](performance_guide.md) tips
- See [code examples](examples/) for advanced usage

## Need Help?

- Health check: `GET /health`
- API documentation: `GET /docs`
- Metrics: `GET /metrics`

You're ready to optimize your code with OptimizeAI! 🚀
