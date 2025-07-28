#!/usr/bin/env python3
"""
Demonstration of the build_source_map function.
"""

import ast
import sys
import os

# Add the parent directories to sys.path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from engine.mapping.ast_map import build_source_map


def demonstrate_build_source_map():
    """Demonstrate the build_source_map function with a practical example."""
    print("🌟 build_source_map Demonstration")
    print("=" * 60)
    
    # Original source code
    source_code = '''import os
import json
from pathlib import Path

class FileProcessor:
    """A class for processing files."""
    
    def __init__(self, base_path: str):
        self.base_path = Path(base_path)
        self.processed_files = []
    
    @property
    def file_count(self) -> int:
        """Get the number of processed files."""
        return len(self.processed_files)
    
    def process_file(self, filename: str) -> dict:
        """Process a single file."""
        file_path = self.base_path / filename
        
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        
        with open(file_path, 'r') as f:
            content = f.read()
        
        result = {
            'filename': filename,
            'size': len(content),
            'lines': len(content.splitlines())
        }
        
        self.processed_files.append(result)
        return result
    
    async def process_multiple(self, filenames: list) -> list:
        """Process multiple files asynchronously."""
        results = []
        for filename in filenames:
            try:
                result = self.process_file(filename)
                results.append(result)
            except FileNotFoundError as e:
                print(f"Error: {e}")
        return results

@decorator_function
def utility_function(data: dict) -> str:
    """A utility function for data processing."""
    if not data:
        return "No data"
    
    return json.dumps(data, indent=2)

async def main():
    """Main function to demonstrate usage."""
    processor = FileProcessor("./data")
    
    files = ["file1.txt", "file2.txt", "file3.txt"]
    results = await processor.process_multiple(files)
    
    for result in results:
        formatted = utility_function(result)
        print(formatted)
    
    print(f"Processed {processor.file_count} files")
'''
    
    # Corresponding minified/summarized output
    summary_lines = [
        "import os",
        "import json", 
        "from pathlib import Path",
        "class FileProcessor:",
        "def __init__(self,base_path):self.base_path=Path(base_path);self.processed_files=[]",
        "def file_count(self):return len(self.processed_files)",
        "def process_file(self,filename):...",
        "async def process_multiple(self,filenames):...",
        "def utility_function(data):return json.dumps(data,indent=2)if data else 'No data'",
        "async def main():processor=FileProcessor('./data');files=['file1.txt','file2.txt','file3.txt'];results=await processor.process_multiple(files);[print(utility_function(result))for result in results];print(f'Processed {processor.file_count} files')"
    ]
    
    print("📋 Original Source Code:")
    print(f"   Lines: {len(source_code.splitlines())}")
    print(f"   Characters: {len(source_code)}")
    print()
    
    print("📦 Minified Summary:")
    print(f"   Lines: {len(summary_lines)}")
    print(f"   Characters: {sum(len(line) for line in summary_lines)}")
    print()
    
    # Parse AST and build source map
    tree = ast.parse(source_code)
    mapped_nodes = build_source_map(tree, summary_lines)
    
    print("🗺️  Source-to-Summary Mapping:")
    print(f"   {'Type':10} | {'Name':35} | {'Source Lines':12} | {'Summary Line':12}")
    print("   " + "-" * 75)
    
    for node in mapped_nodes:
        source_range = f"{node.source_start:2}-{node.source_end:2} ({node.source_end-node.source_start+1:2}L)"
        summary_range = f"{node.summary_start:2}-{node.summary_end:2} ({node.summary_end-node.summary_start+1:2}L)"
        name = node.name[:33] + ".." if len(node.name) > 35 else node.name
        
        print(f"   {node.type:10} | {name:35} | {source_range:12} | {summary_range:12}")
    
    print()
    print("📊 Mapping Statistics:")
    print(f"   Total mapped nodes: {len(mapped_nodes)}")
    
    node_counts = {}
    for node in mapped_nodes:
        node_counts[node.type] = node_counts.get(node.type, 0) + 1
    
    for node_type, count in sorted(node_counts.items()):
        print(f"   {node_type:10}: {count:3} nodes")
    
    # Calculate compression ratio
    source_lines = len(source_code.splitlines())
    summary_lines_count = len(summary_lines)
    compression_ratio = summary_lines_count / source_lines if source_lines > 0 else 0
    
    print()
    print("🎯 Compression Analysis:")
    print(f"   Source lines: {source_lines}")
    print(f"   Summary lines: {summary_lines_count}")
    print(f"   Compression ratio: {compression_ratio:.1%}")
    print(f"   Size reduction: {(1-compression_ratio)*100:.1f}%")
    
    print()
    print("✅ Example completed successfully!")
    
    return mapped_nodes


def show_reverse_mapping_example(mapped_nodes):
    """Show how to use the mapping for reverse lookups."""
    print("\n🔄 Reverse Mapping Examples:")
    print("=" * 40)
    
    # Example: Find source lines for summary line 5
    summary_line = 5
    source_lines = []
    
    for node in mapped_nodes:
        if node.summary_start <= summary_line <= node.summary_end:
            source_lines.extend(range(node.source_start, node.source_end + 1))
    
    print(f"Summary line {summary_line} maps to source lines: {sorted(set(source_lines))}")
    
    # Example: Find summary lines for source line range
    source_start, source_end = 15, 25
    summary_lines = []
    
    for node in mapped_nodes:
        if not (node.source_end < source_start or node.source_start > source_end):
            summary_lines.extend(range(node.summary_start, node.summary_end + 1))
    
    print(f"Source lines {source_start}-{source_end} map to summary lines: {sorted(set(summary_lines))}")


if __name__ == "__main__":
    mapped_nodes = demonstrate_build_source_map()
    show_reverse_mapping_example(mapped_nodes)
