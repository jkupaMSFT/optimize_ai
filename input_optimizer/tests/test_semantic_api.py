#!/usr/bin/env python3
"""
API Endpoint Test for Semantic Compression
Tests the FastAPI semantic compression endpoints to ensure proper integration.
"""

import sys
import time
import subprocess
import signal
from pathlib import Path
import requests
import json
from contextlib import contextmanager

# Add project root to path
project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

from input_optimizer.samples.samples import sample1, sample3, sample31

@contextmanager
def fastapi_server():
    """Context manager to start and stop FastAPI server for testing"""
    print("🚀 Starting FastAPI server...")
    
    # Start the server in background
    process = subprocess.Popen(
        [sys.executable, "app.py"],
        cwd=str(project_root),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    
    # Wait for server to start
    time.sleep(3)
    
    # Check if server is running
    try:
        response = requests.get("http://localhost:8000/health", timeout=5)
        if response.status_code == 200:
            print("✅ FastAPI server started successfully")
        else:
            print("⚠️  Server started but health check failed")
    except requests.exceptions.RequestException:
        print("❌ Failed to connect to server")
        process.kill()
        raise
    
    try:
        yield "http://localhost:8000"
    finally:
        print("🛑 Stopping FastAPI server...")
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        print("✅ Server stopped")

def test_semantic_compression_endpoint():
    """Test the /compress/semantic endpoint"""
    
    print("\n" + "=" * 60)
    print("TESTING /compress/semantic ENDPOINT")
    print("=" * 60)
    
    with fastapi_server() as base_url:
        endpoint = f"{base_url}/compress/semantic"
        
        # Test cases
        test_cases = [
            {
                "name": "Simple Function",
                "code": sample1,
                "similarity_threshold": 0.5
            },
            {
                "name": "Class with Properties", 
                "code": sample3,
                "similarity_threshold": 0.7
            },
            {
                "name": "Verbose Documentation",
                "code": sample31,
                "similarity_threshold": 0.6
            }
        ]
        
        for i, test_case in enumerate(test_cases, 1):
            print(f"\n📋 Test Case {i}: {test_case['name']}")
            print("-" * 40)
            
            payload = {
                "code": test_case["code"],
                "similarity_threshold": test_case["similarity_threshold"]
            }
            
            try:
                response = requests.post(
                    endpoint,
                    json=payload,
                    headers={"Content-Type": "application/json"},
                    timeout=30
                )
                
                if response.status_code == 200:
                    result = response.json()
                    
                    print(f"✅ Status: {response.status_code}")
                    print(f"📊 Original tokens: {result['original_tokens']:,}")
                    print(f"📊 Compressed tokens: {result['compressed_tokens']:,}")
                    print(f"🗜️  Compression: {result['compression_percentage']:.1f}%")
                    print(f"🔄 Similarity: {result['similarity_score']:.3f}")
                    print(f"🎯 Meets threshold: {result['meets_threshold']}")
                    
                    # Validate response structure
                    required_fields = [
                        'compressed_code', 'original_tokens', 'compressed_tokens',
                        'compression_percentage', 'similarity_score', 'meets_threshold',
                        'stage_results', 'source_mapping'
                    ]
                    
                    missing_fields = [field for field in required_fields if field not in result]
                    if missing_fields:
                        print(f"⚠️  Missing fields: {missing_fields}")
                    else:
                        print("✅ Response structure valid")
                        
                else:
                    print(f"❌ HTTP {response.status_code}: {response.text}")
                    
            except requests.exceptions.RequestException as e:
                print(f"❌ Request failed: {str(e)}")

def test_compression_compare_endpoint():
    """Test the /compress/compare endpoint"""
    
    print("\n" + "=" * 60)
    print("TESTING /compress/compare ENDPOINT")
    print("=" * 60)
    
    with fastapi_server() as base_url:
        endpoint = f"{base_url}/compress/compare"
        
        # Compare different compression methods
        test_code = sample31  # Use verbose documentation
        
        payload = {
            "code": test_code,
            "include_maximum": False,  # Don't include maximum compression for this test
            "similarity_threshold": 0.6
        }
        
        try:
            response = requests.post(
                endpoint,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                
                print(f"✅ Status: {response.status_code}")
                print(f"📊 Original tokens: {result['original']['tokens']:,}")
                
                # Show semantic compression results
                semantic = result['semantic_compression']
                print(f"\n🔧 SEMANTIC Method:")
                print(f"   📊 Compressed tokens: {semantic['tokens']:,}")
                print(f"   🗜️  Compression: {semantic['compression_percentage']:.1f}%")
                print(f"   🔄 Similarity: {semantic['similarity_score']:.3f}")
                print(f"   🎯 Meets threshold: {semantic['meets_threshold']}")
                
                # Show recommendation
                if 'recommendation' in result:
                    print(f"\n💡 Recommendation: {result['recommendation']}")
                
                print("✅ Comparison endpoint working correctly")
                
            else:
                print(f"❌ HTTP {response.status_code}: {response.text}")
                
        except requests.exceptions.RequestException as e:
            print(f"❌ Request failed: {str(e)}")

def test_error_handling():
    """Test error handling with invalid inputs"""
    
    print("\n" + "=" * 60)
    print("TESTING ERROR HANDLING")
    print("=" * 60)
    
    with fastapi_server() as base_url:
        # Test invalid code
        print("\n📋 Testing invalid Python code...")
        
        payload = {
            "code": "def invalid_syntax(\n    missing_closing_paren",
            "similarity_threshold": 0.5
        }
        
        try:
            response = requests.post(
                f"{base_url}/compress/semantic",
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=10
            )
            
            print(f"Status: {response.status_code}")
            if response.status_code == 422:
                print("✅ Properly handled syntax error")
            elif response.status_code == 200:
                print("⚠️  Unexpectedly succeeded with invalid syntax")
            else:
                print(f"Response: {response.text}")
                
        except requests.exceptions.RequestException as e:
            print(f"❌ Request failed: {str(e)}")
        
        # Test invalid threshold
        print("\n📋 Testing invalid similarity threshold...")
        
        payload = {
            "code": sample1,
            "similarity_threshold": 1.5  # Invalid - should be 0-1
        }
        
        try:
            response = requests.post(
                f"{base_url}/compress/semantic",
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=10
            )
            
            print(f"Status: {response.status_code}")
            if response.status_code == 422:
                print("✅ Properly handled invalid threshold")
            else:
                print(f"Response: {response.text}")
                
        except requests.exceptions.RequestException as e:
            print(f"❌ Request failed: {str(e)}")

if __name__ == "__main__":
    print("🧪 SEMANTIC COMPRESSION API TESTING")
    print("=" * 80)
    
    try:
        # Test semantic compression endpoint
        test_semantic_compression_endpoint()
        
        # Test comparison endpoint  
        test_compression_compare_endpoint()
        
        # Test error handling
        test_error_handling()
        
        print("\n" + "=" * 80)
        print("🎉 API TESTING COMPLETE")
        print("=" * 80)
        
    except KeyboardInterrupt:
        print("\n❌ Testing interrupted by user")
    except Exception as e:
        print(f"\n❌ Testing failed: {str(e)}")
        sys.exit(1)
