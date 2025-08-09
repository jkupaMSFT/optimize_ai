#!/usr/bin/env python3
"""
Live demo script for Claude Code integration with token tracking
"""

import sys
import json
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, Any
import time

# Add parent directory to path
sys.path.append(str(Path(__file__).parent.parent.parent))

from integrations.claude_wrapper.claude_proxy import ClaudeCodeProxy
from integrations.claude_wrapper.metrics import MetricsCollector
from utils.logger import setup_logger

class ClaudeLiveDemo:
    """Live demo with Claude CLI integration"""
    
    def __init__(self):
        self.logger = setup_logger("claude-demo", log_level="INFO")
        self.cache_dir = Path.home() / ".optimize_ai" / "demo_cache"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize components
        self.proxy = ClaudeCodeProxy(
            enable_compression=True,
            cache_dir=self.cache_dir
        )
        self.metrics = MetricsCollector(self.cache_dir)
        
    def analyze_file(self, file_path: str, prompt: str = None) -> Dict[str, Any]:
        """
        Analyze a file with Claude and track all metrics
        
        Args:
            file_path: Path to file to analyze
            prompt: Custom prompt (optional)
            
        Returns:
            Dictionary with analysis results and metrics
        """
        file_path = Path(file_path)
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        
        # Default prompt if none provided
        if not prompt:
            prompt = f"""Please analyze this {file_path.suffix} file and provide:
1. A high-level description of what it does
2. Main classes and their purposes
3. Key methods and functions
4. Any notable patterns or design choices
5. Potential improvements or concerns

Be thorough but concise in your analysis."""
        
        print(f"\n🔍 ANALYZING FILE: {file_path}")
        print(f"📝 PROMPT: {prompt}\n")
        
        # Start operation tracking
        operation_id = self.metrics.start_operation('file_analysis')
        
        start_time = time.time()
        
        try:
            # Step 1: Process and compress input
            print("🗜️ COMPRESSING INPUT...")
            compressed_prompt, compression_metadata = self.proxy.process_input(
                prompt, str(file_path)
            )
            
            print(f"   Original tokens: {compression_metadata.get('original_tokens', 'N/A')}")
            print(f"   Compressed tokens: {compression_metadata.get('compressed_tokens', 'N/A')}")
            print(f"   Compression ratio: {compression_metadata.get('compression_ratio', 0):.1f}%")
            print(f"   Tier used: {compression_metadata.get('tier', 'N/A')}")
            
            # Step 2: Call Claude CLI
            print("\n🤖 CALLING CLAUDE...")
            claude_start = time.time()
            claude_response, claude_metrics = self._call_claude_cli(compressed_prompt)
            claude_duration = time.time() - claude_start
            
            print(f"   Claude response time: {claude_duration:.2f}s")
            print(f"   Response length: {len(claude_response)} chars")
            
            # Step 3: Process output (translate from CAI if needed)
            print("\n🔄 PROCESSING OUTPUT...")
            final_output = self.proxy.process_output(claude_response, compression_metadata)
            
            # Calculate total metrics
            total_duration = time.time() - start_time
            
            # Record metrics
            final_metrics = {
                'total_duration': total_duration,
                'claude_duration': claude_duration,
                'compression_savings': compression_metadata.get('original_tokens', 0) - compression_metadata.get('compressed_tokens', 0),
                'compression_ratio': compression_metadata.get('compression_ratio', 0),
                'claude_response_length': len(claude_response),
                'final_output_length': len(final_output),
                'file_path': str(file_path),
                'file_size': file_path.stat().st_size,
                'prompt_length': len(prompt),
                **claude_metrics
            }
            
            self.metrics.end_operation(operation_id, final_metrics)
            
            # Prepare results
            results = {
                'file_path': str(file_path),
                'prompt': prompt,
                'analysis': final_output,
                'metrics': {
                    'compression': {
                        'original_tokens': compression_metadata.get('original_tokens', 0),
                        'compressed_tokens': compression_metadata.get('compressed_tokens', 0),
                        'compression_ratio': compression_metadata.get('compression_ratio', 0),
                        'tokens_saved': compression_metadata.get('original_tokens', 0) - compression_metadata.get('compressed_tokens', 0),
                        'tier': compression_metadata.get('tier', 'unknown')
                    },
                    'timing': {
                        'total_duration': total_duration,
                        'claude_duration': claude_duration,
                        'compression_overhead': total_duration - claude_duration
                    },
                    'claude': claude_metrics
                }
            }
            
            self._display_results(results)
            return results
            
        except Exception as e:
            self.metrics.end_operation(operation_id, {
                'error': str(e),
                'success': False,
                'duration': time.time() - start_time
            })
            self.logger.error(f"Analysis failed: {e}")
            raise
    
    def _call_claude_cli(self, prompt: str) -> tuple[str, Dict[str, Any]]:
        """Call Claude CLI and capture metrics"""
        
        # Create temporary file for large prompts
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as temp_file:
            temp_file.write(prompt)
            temp_path = temp_file.name
        
        try:
            # Call Claude CLI
            result = subprocess.run(
                ["claude", f"@{temp_path}"],
                capture_output=True,
                text=True,
                timeout=120
            )
            
            if result.returncode != 0:
                raise RuntimeError(f"Claude CLI error: {result.stderr}")
            
            response = result.stdout
            
            # Extract metrics from response if available
            # Note: Claude CLI doesn't provide token metrics directly,
            # so we'll estimate based on response length
            estimated_input_tokens = len(prompt.split()) * 1.3  # Rough estimate
            estimated_output_tokens = len(response.split()) * 1.3
            
            metrics = {
                'estimated_input_tokens': int(estimated_input_tokens),
                'estimated_output_tokens': int(estimated_output_tokens),
                'estimated_total_tokens': int(estimated_input_tokens + estimated_output_tokens),
                'response_chars': len(response),
                'success': True
            }
            
            return response, metrics
            
        except subprocess.TimeoutExpired:
            raise RuntimeError("Claude CLI timed out")
        except FileNotFoundError:
            raise RuntimeError("Claude CLI not found. Please ensure it's installed and in PATH.")
        finally:
            # Cleanup temp file
            Path(temp_path).unlink(missing_ok=True)
    
    def _display_results(self, results: Dict[str, Any]):
        """Display analysis results in a formatted way"""
        
        print("\n" + "="*80)
        print("📊 ANALYSIS RESULTS")
        print("="*80)
        
        # Compression metrics
        comp = results['metrics']['compression']
        print(f"\n🗜️ COMPRESSION METRICS:")
        print(f"   Original tokens: {comp['original_tokens']:,}")
        print(f"   Compressed tokens: {comp['compressed_tokens']:,}")
        print(f"   Tokens saved: {comp['tokens_saved']:,}")
        print(f"   Compression ratio: {comp['compression_ratio']:.1f}%")
        print(f"   Tier used: {comp['tier']}")
        
        # Timing metrics
        timing = results['metrics']['timing']
        print(f"\n⏱️ TIMING METRICS:")
        print(f"   Total duration: {timing['total_duration']:.2f}s")
        print(f"   Claude processing: {timing['claude_duration']:.2f}s")
        print(f"   Compression overhead: {timing['compression_overhead']:.2f}s")
        
        # Claude metrics
        claude = results['metrics']['claude']
        print(f"\n🤖 CLAUDE METRICS:")
        print(f"   Estimated input tokens: {claude['estimated_input_tokens']:,}")
        print(f"   Estimated output tokens: {claude['estimated_output_tokens']:,}")
        print(f"   Estimated total tokens: {claude['estimated_total_tokens']:,}")
        print(f"   Response characters: {claude['response_chars']:,}")
        
        # Analysis output
        print(f"\n📝 CLAUDE'S ANALYSIS:")
        print("-" * 80)
        print(results['analysis'])
        print("-" * 80)
        
        # Token efficiency
        efficiency = comp['tokens_saved'] / comp['original_tokens'] * 100 if comp['original_tokens'] > 0 else 0
        print(f"\n💰 TOKEN EFFICIENCY:")
        print(f"   Saved {comp['tokens_saved']:,} tokens ({efficiency:.1f}% reduction)")
        print(f"   Effective Claude cost reduction: ~{efficiency:.1f}%")
    
    def get_metrics_summary(self) -> Dict[str, Any]:
        """Get summary of all operations"""
        return self.metrics.get_summary_report()

def main():
    """Main demo function"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Live Claude Code Demo with Token Tracking")
    parser.add_argument("file", help="File to analyze")
    parser.add_argument("--prompt", "-p", help="Custom analysis prompt")
    parser.add_argument("--summary", "-s", action="store_true", help="Show metrics summary")
    
    args = parser.parse_args()
    
    demo = ClaudeLiveDemo()
    
    try:
        # Analyze file
        results = demo.analyze_file(args.file, args.prompt)
        
        # Show summary if requested
        if args.summary:
            print("\n" + "="*80)
            print("📈 METRICS SUMMARY")
            print("="*80)
            summary = demo.get_metrics_summary()
            print(json.dumps(summary, indent=2))
        
        print(f"\n✅ Analysis complete! Results saved to cache.")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
