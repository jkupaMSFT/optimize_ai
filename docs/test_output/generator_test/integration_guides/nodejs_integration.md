# Node.js Integration Guide for OptimizeAI

This guide shows how to integrate OptimizeAI into your Node.js applications.

## Installation

```bash
npm install axios  # For HTTP requests
# or
npm install node-fetch  # Alternative HTTP client
```

## Basic Client Class

```javascript
const axios = require('axios');

class OptimizeAIClient {
    constructor(baseUrl = 'http://localhost:8000') {
        this.baseUrl = baseUrl;
        this.client = axios.create({
            baseURL: baseUrl,
            timeout: 30000,
            headers: {
                'Content-Type': 'application/json'
            }
        });
    }

    async minifyCode(code, options = {}) {
        try {
            const response = await this.client.post('/minify', {
                code,
                ...options
            });
            return response.data;
        } catch (error) {
            throw new Error(`Minification failed: ${error.message}`);
        }
    }

    async translateToSudoLang(code) {
        try {
            const response = await this.client.post('/translate/sudolang', { code });
            return response.data;
        } catch (error) {
            throw new Error(`SudoLang translation failed: ${error.message}`);
        }
    }

    async semanticCompress(code, level = 'moderate') {
        try {
            const response = await this.client.post('/compress/semantic', {
                code,
                compression_level: level
            });
            return response.data;
        } catch (error) {
            throw new Error(`Semantic compression failed: ${error.message}`);
        }
    }

    async healthCheck() {
        try {
            const response = await this.client.get('/health');
            return response.data;
        } catch (error) {
            throw new Error(`Health check failed: ${error.message}`);
        }
    }
}

module.exports = OptimizeAIClient;
```

## Usage Example

```javascript
const OptimizeAIClient = require('./optimize-ai-client');

async function main() {
    const client = new OptimizeAIClient();

    try {
        // Check health first
        const health = await client.healthCheck();
        console.log('API Status:', health.status);

        // Minify code
        const code = `
def process_data(data):
    results = []
    for item in data:
        if item.is_valid():
            results.append(item.process())
    return results
        `;

        const result = await client.minifyCode(code, {
            compress_strings: true,
            compress_vars: true
        });

        console.log(`Compression: ${result.compression_percentage.toFixed(1)}%`);
        console.log(`Minified: ${result.minified_code}`);

    } catch (error) {
        console.error('Error:', error.message);
    }
}

main();
```

## Express.js Middleware

```javascript
const express = require('express');
const OptimizeAIClient = require('./optimize-ai-client');

const app = express();
const optimizeClient = new OptimizeAIClient();

app.use(express.json());

// Middleware for code optimization
app.use('/api/optimize', async (req, res, next) => {
    try {
        const { code, operation = 'minify' } = req.body;

        let result;
        switch (operation) {
            case 'minify':
                result = await optimizeClient.minifyCode(code);
                break;
            case 'sudolang':
                result = await optimizeClient.translateToSudoLang(code);
                break;
            case 'semantic':
                result = await optimizeClient.semanticCompress(code);
                break;
            default:
                return res.status(400).json({ error: 'Invalid operation' });
        }

        res.json(result);
    } catch (error) {
        next(error);
    }
});

app.listen(3000, () => {
    console.log('Server running on port 3000');
});
```

## Batch Processing

```javascript
async function batchProcess(codes, client) {
    const results = await Promise.allSettled(
        codes.map(async (code, index) => {
            try {
                const result = await client.minifyCode(code);
                return { index, success: true, result };
            } catch (error) {
                return { index, success: false, error: error.message };
            }
        })
    );

    return results.map(result => result.value || result.reason);
}
```
