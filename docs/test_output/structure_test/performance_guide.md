# OptimizeAI Performance Guide

## Performance Characteristics

### Compression Ratios by Tier

| Tier | Average Compression | Processing Time | Use Case |
|------|-------------------|-----------------|----------|
| Basic | 15-30% | < 100ms | Simple scripts |
| Moderate | 30-50% | 100-500ms | Regular applications |
| Aggressive | 50-70% | 500ms-2s | Complex codebases |
| Maximum | 70-87% | 2-10s | Maximum compression needed |

### Throughput Benchmarks

- **Single Request**: 100-1000 requests/second (depending on complexity)
- **Batch Processing**: Up to 50 concurrent requests
- **Memory Usage**: 50-200MB per request
- **CPU Usage**: 1-4 cores recommended for production

## Optimization Strategies

### 1. Choose Appropriate Compression Tier

```python
# For simple code (< 100 lines)
requests.post("/minify", json={
    "code": simple_code,
    "tier": "basic"  # Fast processing
})

# For complex applications
requests.post("/compress/semantic", json={
    "code": complex_code,
    "compression_level": "moderate"  # Balanced approach
})
```

### 2. Batch Processing

```python
# Instead of multiple single requests
codes = ["code1", "code2", "code3"]

# Use pipeline analysis for efficiency
response = requests.post("/transform/pipeline-analysis", json={
    "codes": codes,
    "optimization_strategy": "balanced"
})
```

### 3. Caching Results

```python
import hashlib
import json

class OptimizeAICache:
    def __init__(self):
        self.cache = {}
    
    def get_cache_key(self, code, options):
        content = json.dumps({"code": code, "options": options}, sort_keys=True)
        return hashlib.md5(content.encode()).hexdigest()
    
    def minify_with_cache(self, code, options=None):
        cache_key = self.get_cache_key(code, options or {})
        
        if cache_key in self.cache:
            return self.cache[cache_key]
        
        result = client.minify_code(code, **(options or {}))
        self.cache[cache_key] = result
        return result
```

## Monitoring Performance

### Key Metrics to Track

1. **Response Time Distribution**
```python
import time

start_time = time.time()
result = client.minify_code(code)
duration = time.time() - start_time

print(f"Request completed in {duration:.3f}s")
```

2. **Compression Efficiency**
```python
efficiency = result['compression_percentage'] / (duration * 1000)  # % per ms
print(f"Compression efficiency: {efficiency:.2f}% per ms")
```

3. **Memory Usage**
```python
import psutil
import os

def track_memory_usage():
    process = psutil.Process(os.getpid())
    return process.memory_info().rss / 1024 / 1024  # MB

memory_before = track_memory_usage()
result = client.minify_code(large_code)
memory_after = track_memory_usage()

print(f"Memory used: {memory_after - memory_before:.1f} MB")
```

## Performance Tuning

### Server Configuration

```python
# Production uvicorn settings
uvicorn.run(
    "app:app",
    host="0.0.0.0",
    port=8000,
    workers=4,  # CPU cores
    worker_class="uvicorn.workers.UvicornWorker",
    max_requests=1000,
    max_requests_jitter=50,
    timeout_keep_alive=5
)
```

### Load Testing

```python
import concurrent.futures
import time

def load_test(num_requests=100, concurrency=10):
    def make_request():
        return client.minify_code("def test(): pass")
    
    start_time = time.time()
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = [executor.submit(make_request) for _ in range(num_requests)]
        results = [future.result() for future in concurrent.futures.as_completed(futures)]
    
    duration = time.time() - start_time
    rps = num_requests / duration
    
    print(f"Completed {num_requests} requests in {duration:.2f}s")
    print(f"Requests per second: {rps:.1f}")
    
    return results

# Run load test
load_test(100, 10)
```

## Scaling Considerations

### Horizontal Scaling

```yaml
# docker-compose.yml for scaling
version: '3.8'
services:
  optimizeai:
    build: .
    ports:
      - "8000-8010:8000"
    deploy:
      replicas: 5
  
  nginx:
    image: nginx
    ports:
      - "80:80"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf
```

### Nginx Load Balancer Configuration

```nginx
upstream optimizeai_backend {
    least_conn;
    server optimizeai:8000;
    server optimizeai:8001;
    server optimizeai:8002;
    server optimizeai:8003;
    server optimizeai:8004;
}

server {
    listen 80;
    
    location / {
        proxy_pass http://optimizeai_backend;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_connect_timeout 30s;
        proxy_read_timeout 60s;
    }
}
```

## Troubleshooting Performance Issues

### Common Issues and Solutions

1. **Slow Response Times**
   - Check system resources (CPU, memory)
   - Monitor `/health` endpoint for system status
   - Consider using lighter compression tiers
   - Implement request caching

2. **High Memory Usage**
   - Process smaller code chunks
   - Increase server memory
   - Monitor for memory leaks via `/metrics`

3. **Timeout Errors**
   - Increase client timeout settings
   - Use async processing for large requests
   - Split large operations into smaller chunks

### Performance Monitoring Dashboard

Access real-time performance metrics:
- **Health Check**: `GET /health`
- **Prometheus Metrics**: `GET /metrics` 
- **Web Dashboard**: `GET /dashboard`

Example monitoring script:
```python
import time
import requests

def monitor_performance():
    while True:
        try:
            health = requests.get("http://localhost:8000/health").json()
            print(f"Status: {health['status']}")
            print(f"CPM: {health['compressions_per_minute']:.1f}")
            print(f"Error Rate: {health['error_rate']:.3f}")
            print("-" * 30)
        except Exception as e:
            print(f"Monitoring error: {e}")
        
        time.sleep(30)

monitor_performance()
```
