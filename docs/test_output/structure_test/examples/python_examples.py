#!/usr/bin/env python3
"""
Comprehensive Python Examples for OptimizeAI API

This file contains complete working examples for all API endpoints.
Run this script to test the API functionality.
"""

import requests
import json
import time
from typing import Dict, Any

BASE_URL = "http://localhost:8000"

def test_basic_minification():
    """Test basic code minification"""
    print("=== Basic Minification Test ===")
    
    code = """
def calculate_factorial(n):
    if n <= 1:
        return 1
    else:
        return n * calculate_factorial(n - 1)

result = calculate_factorial(5)
print(f"Factorial of 5 is: {result}")
    """
    
    response = requests.post(
        f"{BASE_URL}/minify",
        json={
            "code": code,
            "compress_strings": True,
            "compress_vars": True
        }
    )
    
    if response.status_code == 200:
        result = response.json()
        print(f"✅ Success!")
        print(f"Original: {result['original_length']} chars")
        print(f"Minified: {result['minified_length']} chars")
        print(f"Compression: {result['compression_percentage']:.1f}%")
        print(f"Minified code: {result['minified_code'][:100]}...")
    else:
        print(f"❌ Error: {response.status_code}")
        print(response.text)
    
    print()

def test_minification_with_stats():
    """Test minification with detailed statistics"""
    print("=== Minification with Stats Test ===")
    
    code = """
class Calculator:
    def __init__(self):
        self.history = []
    
    def add(self, a, b):
        result = a + b
        self.history.append(('add', a, b, result))
        return result
    
    def get_history(self):
        return self.history
    """
    
    response = requests.post(
        f"{BASE_URL}/minify/stats",
        json={
            "code": code,
            "compress_strings": True,
            "compress_vars": True
        }
    )
    
    if response.status_code == 200:
        result = response.json()
        print(f"✅ Success!")
        print(f"Compression: {result['compression_percentage']:.1f}%")
        print(f"AST Analysis: {json.dumps(result['ast_analysis'], indent=2)}")
    else:
        print(f"❌ Error: {response.status_code}")
    
    print()

def test_sudolang_translation():
    """Test SudoLang translation"""
    print("=== SudoLang Translation Test ===")
    
    code = """
data = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
filtered_data = []

for number in data:
    if number % 2 == 0:
        filtered_data.append(number * 2)

print(f"Filtered and doubled: {filtered_data}")
    """
    
    response = requests.post(
        f"{BASE_URL}/translate/sudolang",
        json={"code": code}
    )
    
    if response.status_code == 200:
        result = response.json()
        print(f"✅ Success!")
        print(f"Translation time: {result['translation_time']:.3f}s")
        print(f"SudoLang:")
        print(result['sudolang_translation'])
    else:
        print(f"❌ Error: {response.status_code}")
    
    print()

def test_synthlang_translation():
    """Test SynthLang translation"""
    print("=== SynthLang Translation Test ===")
    
    code = """
def fibonacci_sequence(n):
    sequence = [0, 1]
    while len(sequence) < n:
        next_val = sequence[-1] + sequence[-2]
        sequence.append(next_val)
    return sequence[:n]
    """
    
    response = requests.post(
        f"{BASE_URL}/translate/synthlang",
        json={"code": code}
    )
    
    if response.status_code == 200:
        result = response.json()
        print(f"✅ Success!")
        print(f"Translation time: {result['translation_time']:.3f}s")
        print(f"SynthLang:")
        print(result['synthlang_translation'])
    else:
        print(f"❌ Error: {response.status_code}")
    
    print()

def test_semantic_compression():
    """Test semantic compression"""
    print("=== Semantic Compression Test ===")
    
    code = """
class DataProcessor:
    def __init__(self, configuration_settings):
        self.configuration = configuration_settings
        self.processed_items_list = []
        self.error_count = 0
    
    def process_data_items(self, input_data_list):
        for individual_item in input_data_list:
            try:
                if self.validate_data_item(individual_item):
                    processed_result = self.transform_data_item(individual_item)
                    self.processed_items_list.append(processed_result)
            except Exception as processing_error:
                self.error_count += 1
                print(f"Error processing item: {processing_error}")
        
        return self.processed_items_list
    """
    
    response = requests.post(
        f"{BASE_URL}/compress/semantic",
        json={
            "code": code,
            "compression_level": "moderate"
        }
    )
    
    if response.status_code == 200:
        result = response.json()
        print(f"✅ Success!")
        print(f"Compression: {result['compression_percentage']:.1f}%")
        print(f"Similarity: {result['similarity_score']:.3f}")
        print(f"Original tokens: {result['original_tokens']}")
        print(f"Compressed tokens: {result['compressed_tokens']}")
    else:
        print(f"❌ Error: {response.status_code}")
    
    print()

def test_health_check():
    """Test system health check"""
    print("=== Health Check Test ===")
    
    response = requests.get(f"{BASE_URL}/health")
    
    if response.status_code == 200:
        result = response.json()
        print(f"✅ System Status: {result['status']}")
        print(f"Uptime: {result['uptime_seconds']:.1f}s")
        print(f"Compressions/min: {result['compressions_per_minute']:.1f}")
        print(f"Error rate: {result['error_rate']:.3f}")
    else:
        print(f"❌ Error: {response.status_code}")
    
    print()

def test_metrics():
    """Test metrics endpoint"""
    print("=== Metrics Test ===")
    
    response = requests.get(f"{BASE_URL}/metrics")
    
    if response.status_code == 200:
        metrics = response.text
        print(f"✅ Metrics retrieved ({len(metrics)} characters)")
        print("Sample metrics:")
        print(metrics[:300] + "..." if len(metrics) > 300 else metrics)
    else:
        print(f"❌ Error: {response.status_code}")
    
    print()

if __name__ == "__main__":
    print("OptimizeAI API Comprehensive Testing")
    print("=" * 50)
    
    try:
        # Test basic functionality
        test_health_check()
        test_basic_minification()
        test_minification_with_stats()
        
        # Test translations
        test_sudolang_translation()
        test_synthlang_translation()
        
        # Test advanced features
        test_semantic_compression()
        test_metrics()
        
        print("✅ All tests completed!")
        
    except requests.exceptions.ConnectionError:
        print("❌ Connection Error: Make sure the API server is running on http://localhost:8000")
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
