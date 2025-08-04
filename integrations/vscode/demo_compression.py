#!/usr/bin/env python3
"""
Demo script to test the VS Code compression functionality
This file will be used to test the compression provider integration
"""

import os
import sys
import json
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from pathlib import Path

@dataclass
class CompressionTestData:
    """Test data structure for compression testing"""
    name: str
    content: str
    expected_compression_ratio: float
    metadata: Dict[str, Any]

class CompressionDemo:
    """
    Demonstration class to show compression capabilities
    This class contains various Python constructs that should be compressed well
    """
    
    def __init__(self, config_path: Optional[str] = None):
        self.config_path = config_path or "default_config.json"
        self.data_cache: Dict[str, Any] = {}
        self.compression_stats: List[Dict[str, float]] = []
        
    def load_configuration(self) -> Dict[str, Any]:
        """Load configuration from file"""
        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, 'r') as f:
                    config = json.load(f)
                    print(f"Configuration loaded from {self.config_path}")
                    return config
            else:
                print(f"Configuration file {self.config_path} not found, using defaults")
                return self.get_default_config()
        except Exception as e:
            print(f"Error loading configuration: {e}")
            return self.get_default_config()
    
    def get_default_config(self) -> Dict[str, Any]:
        """Return default configuration"""
        return {
            "compression_enabled": True,
            "compression_level": "high",
            "output_format": "json",
            "debug_mode": False,
            "max_file_size": 1024 * 1024,  # 1MB
            "supported_extensions": [".py", ".js", ".ts", ".json"],
            "exclusion_patterns": ["__pycache__", "node_modules", ".git"]
        }
    
    def process_files(self, directory: str) -> List[CompressionTestData]:
        """Process files in directory for compression testing"""
        results = []
        directory_path = Path(directory)
        
        if not directory_path.exists():
            print(f"Directory {directory} does not exist")
            return results
        
        for file_path in directory_path.rglob("*.py"):
            if any(pattern in str(file_path) for pattern in self.get_default_config()["exclusion_patterns"]):
                continue
                
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    
                test_data = CompressionTestData(
                    name=file_path.name,
                    content=content,
                    expected_compression_ratio=0.3,  # Expect 30% compression
                    metadata={
                        "file_size": len(content),
                        "line_count": content.count('\n') + 1,
                        "path": str(file_path)
                    }
                )
                results.append(test_data)
                
            except Exception as e:
                print(f"Error processing file {file_path}: {e}")
                
        return results
    
    def simulate_compression(self, content: str) -> Dict[str, Any]:
        """Simulate compression algorithm (placeholder)"""
        original_size = len(content)
        # Simulate compression by removing comments and extra whitespace
        lines = content.split('\n')
        compressed_lines = []
        
        for line in lines:
            stripped = line.strip()
            if stripped and not stripped.startswith('#'):
                # Remove extra spaces
                compressed_line = ' '.join(stripped.split())
                compressed_lines.append(compressed_line)
        
        compressed_content = '\n'.join(compressed_lines)
        compressed_size = len(compressed_content)
        
        return {
            "original_size": original_size,
            "compressed_size": compressed_size,
            "compression_ratio": (original_size - compressed_size) / original_size if original_size > 0 else 0,
            "compressed_content": compressed_content,
            "tokens_saved": max(0, (original_size - compressed_size) // 4)  # Rough token estimation
        }
    
    def run_demo(self, test_directory: str = ".") -> None:
        """Run the compression demonstration"""
        print("=== VS Code Compression Provider Demo ===")
        print(f"Testing compression on files in: {test_directory}")
        
        config = self.load_configuration()
        print(f"Using configuration: {json.dumps(config, indent=2)}")
        
        test_files = self.process_files(test_directory)
        print(f"Found {len(test_files)} Python files to process")
        
        total_original_size = 0
        total_compressed_size = 0
        
        for test_data in test_files[:5]:  # Process first 5 files
            print(f"\nProcessing: {test_data.name}")
            compression_result = self.simulate_compression(test_data.content)
            
            total_original_size += compression_result["original_size"]
            total_compressed_size += compression_result["compressed_size"]
            
            print(f"  Original size: {compression_result['original_size']} bytes")
            print(f"  Compressed size: {compression_result['compressed_size']} bytes")
            print(f"  Compression ratio: {compression_result['compression_ratio']:.2%}")
            print(f"  Tokens saved: {compression_result['tokens_saved']}")
        
        if total_original_size > 0:
            overall_ratio = (total_original_size - total_compressed_size) / total_original_size
            print(f"\n=== Overall Results ===")
            print(f"Total original size: {total_original_size} bytes")
            print(f"Total compressed size: {total_compressed_size} bytes")
            print(f"Overall compression ratio: {overall_ratio:.2%}")
            print(f"Total tokens saved: {(total_original_size - total_compressed_size) // 4}")

if __name__ == "__main__":
    demo = CompressionDemo()
    test_dir = sys.argv[1] if len(sys.argv) > 1 else "."
    demo.run_demo(test_dir)
