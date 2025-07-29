#!/usr/bin/env python3
"""
Specific test for the "long input + low percentage → summarization" scenario.
"""

import sys
import os
import time

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from input_optimizer.engine.adapter import adapt_compression, OTPM_THRESHOLD, cached_estimate_tokens
from utils.logger import setup_minifier_logging

# Setup test logging
test_logger = setup_minifier_logging(
    log_level="INFO",
    log_file="logs/long_input_low_pct_test.log",
    enable_console=True,
    enable_file=True,
    enable_metrics=True
)

def generate_test_code():
    """Generate a large test code that should trigger summarization."""
    
    # Create a substantial Python module
    code = '''
import os
import sys
import json
import datetime
import asyncio
import concurrent.futures
from typing import Dict, List, Optional, Any, Union, Tuple
from dataclasses import dataclass, field
from abc import ABC, abstractmethod
from pathlib import Path
from collections import defaultdict, deque

@dataclass
class ConfigurationManager:
    """Comprehensive configuration management system."""
    
    config_file: str
    default_values: Dict[str, Any] = field(default_factory=dict)
    validators: Dict[str, callable] = field(default_factory=dict)
    cached_config: Optional[Dict[str, Any]] = None
    
    def load_configuration(self) -> Dict[str, Any]:
        """Load configuration from file with validation."""
        try:
            if not os.path.exists(self.config_file):
                print(f"Configuration file {self.config_file} not found, using defaults")
                return self.default_values.copy()
            
            with open(self.config_file, 'r') as f:
                config = json.load(f)
            
            # Apply validation
            validated_config = self.validate_configuration(config)
            self.cached_config = validated_config
            
            return validated_config
            
        except Exception as e:
            print(f"Error loading configuration: {e}")
            return self.default_values.copy()
    
    def validate_configuration(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Validate configuration values against registered validators."""
        validated = config.copy()
        
        for key, validator in self.validators.items():
            if key in validated:
                try:
                    if not validator(validated[key]):
                        print(f"Validation failed for {key}, using default")
                        validated[key] = self.default_values.get(key)
                except Exception as e:
                    print(f"Validator error for {key}: {e}")
                    validated[key] = self.default_values.get(key)
        
        # Add missing defaults
        for key, default_value in self.default_values.items():
            if key not in validated:
                validated[key] = default_value
        
        return validated
    
    def save_configuration(self, config: Dict[str, Any]) -> bool:
        """Save configuration to file."""
        try:
            # Validate before saving
            validated_config = self.validate_configuration(config)
            
            with open(self.config_file, 'w') as f:
                json.dump(validated_config, f, indent=2)
            
            self.cached_config = validated_config
            return True
            
        except Exception as e:
            print(f"Error saving configuration: {e}")
            return False
    
    def get_value(self, key: str, default: Any = None) -> Any:
        """Get a configuration value with optional default."""
        if self.cached_config is None:
            self.load_configuration()
        
        return self.cached_config.get(key, default)
    
    def set_value(self, key: str, value: Any) -> bool:
        """Set a configuration value with validation."""
        if self.cached_config is None:
            self.load_configuration()
        
        # Validate if validator exists
        if key in self.validators:
            try:
                if not self.validators[key](value):
                    print(f"Validation failed for {key}")
                    return False
            except Exception as e:
                print(f"Validator error for {key}: {e}")
                return False
        
        self.cached_config[key] = value
        return True

class DataProcessor:
    """Advanced data processing with multiple transformation strategies."""
    
    def __init__(self, config_manager: ConfigurationManager):
        self.config = config_manager
        self.processing_stats = {
            "items_processed": 0,
            "errors_encountered": 0,
            "processing_time": 0.0,
            "memory_usage": 0
        }
        self.transformation_pipeline = []
    
    def add_transformation(self, transform_func: callable, name: str = None):
        """Add a transformation function to the processing pipeline."""
        transform_name = name or f"transform_{len(self.transformation_pipeline)}"
        self.transformation_pipeline.append({
            "function": transform_func,
            "name": transform_name,
            "applied_count": 0,
            "error_count": 0
        })
    
    def process_item(self, item: Any) -> Dict[str, Any]:
        """Process a single item through the transformation pipeline."""
        start_time = time.time()
        
        try:
            result = {"original": item, "transformed": item, "transformations": []}
            
            for i, transform in enumerate(self.transformation_pipeline):
                try:
                    transformed = transform["function"](result["transformed"])
                    result["transformed"] = transformed
                    result["transformations"].append({
                        "step": i,
                        "name": transform["name"],
                        "success": True
                    })
                    transform["applied_count"] += 1
                    
                except Exception as e:
                    result["transformations"].append({
                        "step": i,
                        "name": transform["name"],
                        "success": False,
                        "error": str(e)
                    })
                    transform["error_count"] += 1
            
            self.processing_stats["items_processed"] += 1
            processing_time = time.time() - start_time
            self.processing_stats["processing_time"] += processing_time
            
            return result
            
        except Exception as e:
            self.processing_stats["errors_encountered"] += 1
            return {
                "original": item,
                "transformed": None,
                "error": str(e),
                "transformations": []
            }
    
    def process_batch(self, items: List[Any], parallel: bool = False) -> List[Dict[str, Any]]:
        """Process a batch of items, optionally in parallel."""
        if not parallel:
            return [self.process_item(item) for item in items]
        
        # Parallel processing using thread pool
        with concurrent.futures.ThreadPoolExecutor() as executor:
            futures = [executor.submit(self.process_item, item) for item in items]
            results = [future.result() for future in concurrent.futures.as_completed(futures)]
        
        return results
    
    def get_pipeline_stats(self) -> Dict[str, Any]:
        """Get comprehensive statistics about the processing pipeline."""
        stats = self.processing_stats.copy()
        stats["pipeline_stages"] = []
        
        for transform in self.transformation_pipeline:
            stage_stats = {
                "name": transform["name"],
                "applied_count": transform["applied_count"],
                "error_count": transform["error_count"],
                "success_rate": (transform["applied_count"] / 
                               (transform["applied_count"] + transform["error_count"]) * 100) 
                               if (transform["applied_count"] + transform["error_count"]) > 0 else 0
            }
            stats["pipeline_stages"].append(stage_stats)
        
        if stats["items_processed"] > 0:
            stats["average_processing_time"] = stats["processing_time"] / stats["items_processed"]
        
        return stats

class AsyncDataManager:
    """Asynchronous data management with advanced caching and persistence."""
    
    def __init__(self, cache_size: int = 1000):
        self.cache = {}
        self.cache_size = cache_size
        self.access_history = deque(maxlen=cache_size)
        self.pending_operations = {}
        self.lock = asyncio.Lock()
    
    async def get_data(self, key: str) -> Optional[Any]:
        """Get data from cache or load asynchronously."""
        async with self.lock:
            if key in self.cache:
                self.access_history.append((key, time.time()))
                return self.cache[key]
        
        # Data not in cache, load asynchronously
        return await self.load_data_async(key)
    
    async def set_data(self, key: str, value: Any) -> bool:
        """Set data in cache with async persistence."""
        async with self.lock:
            # Manage cache size
            if len(self.cache) >= self.cache_size:
                await self.evict_least_recently_used()
            
            self.cache[key] = value
            self.access_history.append((key, time.time()))
        
        # Persist asynchronously
        await self.persist_data_async(key, value)
        return True
    
    async def load_data_async(self, key: str) -> Optional[Any]:
        """Load data asynchronously from persistent storage."""
        try:
            # Simulate async data loading
            await asyncio.sleep(0.1)  # Simulate I/O delay
            
            # In real implementation, this would load from database/file
            loaded_data = f"loaded_data_for_{key}"
            
            async with self.lock:
                self.cache[key] = loaded_data
                self.access_history.append((key, time.time()))
            
            return loaded_data
            
        except Exception as e:
            print(f"Error loading data for {key}: {e}")
            return None
    
    async def persist_data_async(self, key: str, value: Any) -> bool:
        """Persist data asynchronously to storage."""
        try:
            # Simulate async persistence
            await asyncio.sleep(0.05)  # Simulate I/O delay
            
            # In real implementation, this would save to database/file
            print(f"Persisted {key}: {value}")
            return True
            
        except Exception as e:
            print(f"Error persisting data for {key}: {e}")
            return False
    
    async def evict_least_recently_used(self):
        """Evict least recently used item from cache."""
        if not self.access_history:
            return
        
        # Find least recently used key
        lru_key = None
        lru_time = float('inf')
        
        for key, access_time in self.access_history:
            if key in self.cache and access_time < lru_time:
                lru_time = access_time
                lru_key = key
        
        if lru_key:
            del self.cache[lru_key]
            print(f"Evicted {lru_key} from cache")

def complex_mathematical_operations(data: List[float]) -> Dict[str, float]:
    """Perform complex mathematical operations on data."""
    if not data:
        return {"error": "No data provided"}
    
    n = len(data)
    
    # Basic statistics
    mean = sum(data) / n
    variance = sum((x - mean) ** 2 for x in data) / n
    std_dev = variance ** 0.5
    
    # Advanced statistics
    sorted_data = sorted(data)
    median = sorted_data[n // 2] if n % 2 == 1 else (sorted_data[n // 2 - 1] + sorted_data[n // 2]) / 2
    
    q1_idx = n // 4
    q3_idx = 3 * n // 4
    q1 = sorted_data[q1_idx]
    q3 = sorted_data[q3_idx]
    iqr = q3 - q1
    
    # Skewness calculation
    skewness = sum((x - mean) ** 3 for x in data) / (n * std_dev ** 3) if std_dev > 0 else 0
    
    # Kurtosis calculation
    kurtosis = sum((x - mean) ** 4 for x in data) / (n * std_dev ** 4) - 3 if std_dev > 0 else 0
    
    return {
        "count": n,
        "mean": mean,
        "median": median,
        "variance": variance,
        "std_dev": std_dev,
        "min": min(data),
        "max": max(data),
        "range": max(data) - min(data),
        "q1": q1,
        "q3": q3,
        "iqr": iqr,
        "skewness": skewness,
        "kurtosis": kurtosis
    }

def string_processing_algorithms(text: str) -> Dict[str, Any]:
    """Advanced string processing and analysis."""
    if not text:
        return {"error": "No text provided"}
    
    # Basic metrics
    char_count = len(text)
    word_count = len(text.split())
    line_count = text.count('\\n') + 1
    
    # Character frequency analysis
    char_freq = {}
    for char in text.lower():
        if char.isalpha():
            char_freq[char] = char_freq.get(char, 0) + 1
    
    # Word frequency analysis
    words = text.lower().split()
    word_freq = {}
    for word in words:
        # Remove punctuation
        clean_word = ''.join(c for c in word if c.isalnum())
        if clean_word:
            word_freq[clean_word] = word_freq.get(clean_word, 0) + 1
    
    # Most common characters and words
    most_common_chars = sorted(char_freq.items(), key=lambda x: x[1], reverse=True)[:5]
    most_common_words = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)[:10]
    
    # Readability metrics (simplified)
    avg_word_length = sum(len(word) for word in words) / len(words) if words else 0
    avg_sentence_length = word_count / (text.count('.') + text.count('!') + text.count('?') + 1)
    
    return {
        "character_count": char_count,
        "word_count": word_count,
        "line_count": line_count,
        "average_word_length": avg_word_length,
        "average_sentence_length": avg_sentence_length,
        "unique_characters": len(char_freq),
        "unique_words": len(word_freq),
        "most_common_characters": most_common_chars,
        "most_common_words": most_common_words,
        "character_frequencies": char_freq,
        "word_frequencies": word_freq
    }

async def main_processing_pipeline():
    """Main asynchronous processing pipeline."""
    
    # Initialize components
    config_manager = ConfigurationManager(
        config_file="config.json",
        default_values={
            "processing_mode": "standard",
            "cache_size": 1000,
            "parallel_processing": True,
            "max_workers": 10
        }
    )
    
    # Set up validators
    config_manager.validators["cache_size"] = lambda x: isinstance(x, int) and x > 0
    config_manager.validators["max_workers"] = lambda x: isinstance(x, int) and 1 <= x <= 50
    
    # Load configuration
    config = config_manager.load_configuration()
    print(f"Loaded configuration: {config}")
    
    # Initialize data processor
    processor = DataProcessor(config_manager)
    
    # Add transformation functions
    processor.add_transformation(lambda x: x.upper() if isinstance(x, str) else x, "uppercase")
    processor.add_transformation(lambda x: x.replace(" ", "_") if isinstance(x, str) else x, "underscore")
    processor.add_transformation(lambda x: f"processed_{x}" if isinstance(x, str) else x, "prefix")
    
    # Initialize async data manager
    data_manager = AsyncDataManager(cache_size=config.get("cache_size", 1000))
    
    # Sample data for processing
    sample_data = [
        "hello world",
        "python programming",
        "data processing",
        "machine learning",
        "artificial intelligence"
    ]
    
    # Process data
    print("Processing sample data...")
    processed_results = processor.process_batch(sample_data, parallel=config.get("parallel_processing", False))
    
    # Store results in async data manager
    for i, result in enumerate(processed_results):
        await data_manager.set_data(f"result_{i}", result)
    
    # Retrieve and display results
    print("\\nProcessed Results:")
    for i in range(len(processed_results)):
        retrieved = await data_manager.get_data(f"result_{i}")
        print(f"Result {i}: {retrieved}")
    
    # Generate processing statistics
    stats = processor.get_pipeline_stats()
    print(f"\\nProcessing Statistics: {stats}")
    
    # Perform mathematical analysis on numerical data
    numerical_data = [float(i) for i in range(100)]
    math_results = complex_mathematical_operations(numerical_data)
    print(f"\\nMathematical Analysis: {math_results}")
    
    # Perform string analysis
    text_sample = "This is a sample text for analysis. It contains multiple sentences and various words."
    string_results = string_processing_algorithms(text_sample)
    print(f"\\nString Analysis: {string_results}")
    
    return {
        "processed_results": processed_results,
        "statistics": stats,
        "mathematical_analysis": math_results,
        "string_analysis": string_results
    }

if __name__ == "__main__":
    # Run the async pipeline
    result = asyncio.run(main_processing_pipeline())
    print(f"\\nFinal pipeline result: {result}")
'''
    
    # Repeat the code multiple times to make it large enough to trigger OTPM
    return code * 10  # This should create a very large code file


def test_long_input_low_percentage():
    """Test the specific scenario: long input + low percentage → summarization."""
    
    print("🧪 Testing: Long Input + Low Percentage → Summarization")
    print("=" * 60)
    
    # Generate large test code
    test_code = generate_test_code()
    initial_length = len(test_code)
    initial_tokens = cached_estimate_tokens(test_code, "tiktoken", "gpt-4")
    
    print(f"Generated test code:")
    print(f"  Length: {initial_length:,} characters")
    print(f"  Estimated tokens: {initial_tokens:,}")
    print(f"  OTPM threshold: {OTPM_THRESHOLD:,}")
    print(f"  80% threshold: {int(OTPM_THRESHOLD * 0.8):,}")
    
    # Set up low percentage headers (5% remaining)
    headers = {
        "x-ratelimit-remaining-tokens": "5000",
        "x-ratelimit-limit-tokens": "100000"
    }
    
    remaining_pct = 5000 / 100000 * 100
    print(f"\\nRate limit scenario:")
    print(f"  Remaining tokens: 5,000")
    print(f"  Total limit: 100,000") 
    print(f"  Remaining percentage: {remaining_pct:.1f}%")
    
    # Run the test
    print(f"\\n🚀 Running adapt_compression...")
    start_time = time.time()
    
    try:
        result = adapt_compression(
            headers=headers,
            code=test_code,
            model_type="gpt-4",
            return_metadata=True
        )
        
        processing_time = time.time() - start_time
        
        # Analyze results
        print(f"\\n📊 Results:")
        print(f"  Processing time: {processing_time*1000:.1f}ms")
        print(f"  Final code length: {len(result.compressed_code):,} characters")
        print(f"  Final tokens: {result.post_tokens:,}")
        print(f"  Token reduction: {result.token_reduction_percent:.1f}%")
        print(f"  OTPM status: {result.additional_metrics.get('otpm_status', 'unknown')}")
        
        # Check savings metrics
        savings_metrics = result.additional_metrics.get('savings_metrics', {})
        if savings_metrics:
            print(f"\\n💰 Savings Metrics:")
            print(f"  Savings percentage: {savings_metrics['savings_percent']:.1f}%")
            print(f"  Efficiency rating: {savings_metrics['efficiency_rating']}")
            print(f"  Meets 50% target: {'✅' if savings_metrics['meets_target'] else '❌'}")
            print(f"  Tokens saved: {savings_metrics['tokens_saved']:,}")
            print(f"  Compression ratio: {savings_metrics['compression_ratio']:.3f}")
        
        # Check if summarization was triggered
        otpm_status = result.additional_metrics.get('otpm_status', '')
        summarization_triggered = 'summarized' in otpm_status.lower()
        
        print(f"\\n🎯 Test Validation:")
        print(f"  Expected: Summarization triggered")
        print(f"  Actual: {'✅ Summarization triggered' if summarization_triggered else '❌ No summarization'}")
        
        if summarization_triggered:
            savings_target_met = savings_metrics.get('savings_percent', 0) >= 50.0
            print(f"  Expected: ≥50% token savings")
            print(f"  Actual: {'✅ Target met' if savings_target_met else '❌ Target not met'}")
            
            test_passed = savings_target_met
        else:
            test_passed = False
        
        print(f"\\n🏆 Overall Test Result: {'✅ PASSED' if test_passed else '❌ FAILED'}")
        
        # Show a sample of the compressed output
        print(f"\\n📄 Sample of compressed output (first 500 chars):")
        print("-" * 50)
        print(result.compressed_code[:500])
        if len(result.compressed_code) > 500:
            print("...")
        print("-" * 50)
        
        return test_passed
        
    except Exception as e:
        print(f"\\n❌ Test failed with exception: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = test_long_input_low_percentage()
    sys.exit(0 if success else 1)
