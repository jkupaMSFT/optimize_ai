#!/usr/bin/env python3
"""
OptimizeAI Comprehensive Performance Analysis & Reporting Tool
Generates detailed performance reports for scaling analysis and customer benefit modeling
"""

import json
import os
import re
import time
from pathlib import Path
from typing import Dict, List, Any
from datetime import datetime
import statistics

class OptimizeAIPerformanceAnalyzer:
    def __init__(self, data_dir: str = "."):
        self.data_dir = Path(data_dir)
        self.report_data = {}
        self.timestamp = datetime.now()
        
    def analyze_cai_translation_performance(self):
        """Analyze CAI translation test results for pattern recognition and accuracy"""
        try:
            with open(self.data_dir / 'comprehensive_cai_test_results.json', 'r') as f:
                cai_results = json.load(f)
            
            pattern_types = set()
            processing_details = []
            pattern_complexity_scores = []
            
            for test_name, test_data in cai_results.items():
                # Extract pattern information
                pattern_analysis = test_data.get('pattern_analysis', {})
                pattern_types.update(pattern_analysis.get('pattern_types', []))
                
                # Calculate pattern complexity score
                patterns_found = pattern_analysis.get('patterns_found', 0)
                raw_patterns = pattern_analysis.get('raw_patterns', [])
                complexity_score = sum(len(p.get('raw_match', '')) for p in raw_patterns) / max(patterns_found, 1)
                pattern_complexity_scores.append(complexity_score)
                
                # Extract processing metrics
                translation_result = test_data.get('translation_result', {})
                if translation_result.get('success'):
                    cai_input_length = test_data.get('test_case', {}).get('cai_code_length', 0)
                    generated_code_length = len(translation_result.get('generated_code', ''))
                    
                    processing_details.append({
                        'test_name': test_name,
                        'patterns_found': patterns_found,
                        'generated_code_length': generated_code_length,
                        'cai_input_length': cai_input_length,
                        'expansion_ratio': generated_code_length / max(cai_input_length, 1),
                        'complexity_score': complexity_score
                    })
            
            # Calculate statistics
            successful_tests = sum(1 for test in cai_results.values() 
                                 if test.get('translation_result', {}).get('success', False))
            
            expansion_ratios = [d['expansion_ratio'] for d in processing_details]
            
            self.report_data['cai_translation'] = {
                'total_tests': len(cai_results),
                'successful_tests': successful_tests,
                'success_rate': successful_tests / len(cai_results),
                'pattern_types_supported': list(pattern_types),
                'pattern_complexity': {
                    'avg_complexity_score': statistics.mean(pattern_complexity_scores) if pattern_complexity_scores else 0,
                    'max_complexity': max(pattern_complexity_scores) if pattern_complexity_scores else 0,
                    'min_complexity': min(pattern_complexity_scores) if pattern_complexity_scores else 0
                },
                'code_expansion': {
                    'avg_expansion_ratio': statistics.mean(expansion_ratios) if expansion_ratios else 0,
                    'median_expansion_ratio': statistics.median(expansion_ratios) if expansion_ratios else 0,
                    'expansion_range': [min(expansion_ratios), max(expansion_ratios)] if expansion_ratios else [0, 0]
                },
                'processing_details': processing_details[:5]  # Sample for detailed analysis
            }
            
        except Exception as e:
            print(f"Error analyzing CAI translation: {e}")
            self.report_data['cai_translation'] = {'error': str(e)}
    
    def analyze_output_translator_performance(self):
        """Analyze output translator latency, throughput, and accuracy metrics"""
        try:
            with open(self.data_dir / 'output_translator_benchmark_results.json', 'r') as f:
                ot_results = json.load(f)
            
            successful_results = [r for r in ot_results if r.get('success')]
            
            # Extract performance metrics
            latencies = [r.get('translation_time_ms', 0) for r in successful_results]
            output_sizes = [r.get('size', 0) for r in successful_results]
            similarities = [r.get('similarity_score', 0) for r in successful_results]
            
            # Calculate statistics
            self.report_data['output_translator'] = {
                'total_tests': len(ot_results),
                'successful_tests': len(successful_results),
                'success_rate': len(successful_results) / len(ot_results),
                'latency_metrics': {
                    'avg_latency_ms': statistics.mean(latencies) if latencies else 0,
                    'median_latency_ms': statistics.median(latencies) if latencies else 0,
                    'p95_latency_ms': self._percentile(latencies, 0.95) if latencies else 0,
                    'p99_latency_ms': self._percentile(latencies, 0.99) if latencies else 0,
                    'latency_range': [min(latencies), max(latencies)] if latencies else [0, 0]
                },
                'throughput_metrics': {
                    'avg_throughput_per_second': 1000 / statistics.mean(latencies) if latencies else 0,
                    'theoretical_max_throughput': 1000 / min(latencies) if latencies else 0
                },
                'quality_metrics': {
                    'avg_similarity_score': statistics.mean(similarities) if similarities else 0,
                    'min_similarity_score': min(similarities) if similarities else 0,
                    'similarity_consistency': statistics.stdev(similarities) if len(similarities) > 1 else 0
                },
                'output_size_metrics': {
                    'avg_output_size': statistics.mean(output_sizes) if output_sizes else 0,
                    'output_size_range': [min(output_sizes), max(output_sizes)] if output_sizes else [0, 0]
                }
            }
            
        except Exception as e:
            print(f"Error analyzing output translator: {e}")
            self.report_data['output_translator'] = {'error': str(e)}
    
    def analyze_waterfall_compression_performance(self):
        """Analyze waterfall compression efficiency and semantic preservation"""
        try:
            with open(self.data_dir / 'waterfall_compression_report.txt', 'r') as f:
                content = f.read()
            
            compression_ratios = []
            semantic_similarities = []
            file_sizes = []
            
            # Parse compression data from report
            for line in content.split('\n'):
                # Extract compression ratios
                ratio_match = re.search(r'compression: ([\d.]+)%', line.lower())
                if ratio_match:
                    compression_ratios.append(float(ratio_match.group(1)))
                
                # Extract semantic similarities
                sim_match = re.search(r'semantic similarity: ([\d.]+)', line.lower())
                if sim_match:
                    semantic_similarities.append(float(sim_match.group(1)))
                
                # Extract file sizes if available
                size_match = re.search(r'(\d+)\s*bytes?', line.lower())
                if size_match:
                    file_sizes.append(int(size_match.group(1)))
            
            self.report_data['waterfall_compression'] = {
                'samples_processed': len(compression_ratios),
                'compression_efficiency': {
                    'avg_compression_ratio': statistics.mean(compression_ratios) if compression_ratios else 0,
                    'median_compression_ratio': statistics.median(compression_ratios) if compression_ratios else 0,
                    'best_compression': max(compression_ratios) if compression_ratios else 0,
                    'worst_compression': min(compression_ratios) if compression_ratios else 0,
                    'compression_consistency': statistics.stdev(compression_ratios) if len(compression_ratios) > 1 else 0
                },
                'semantic_preservation': {
                    'avg_semantic_similarity': statistics.mean(semantic_similarities) if semantic_similarities else 0,
                    'min_semantic_similarity': min(semantic_similarities) if semantic_similarities else 0,
                    'semantic_consistency': statistics.stdev(semantic_similarities) if len(semantic_similarities) > 1 else 0
                },
                'token_savings_estimate': {
                    'avg_token_reduction_percent': statistics.mean(compression_ratios) if compression_ratios else 0,
                    'estimated_cost_savings_per_1k_tokens': self._calculate_cost_savings(statistics.mean(compression_ratios) if compression_ratios else 0)
                }
            }
            
        except Exception as e:
            print(f"Error analyzing waterfall compression: {e}")
            self.report_data['waterfall_compression'] = {'error': str(e)}
    
    def analyze_system_scalability_metrics(self):
        """Calculate scalability projections and bottleneck analysis"""
        
        # Extract key metrics for scalability analysis
        output_translator = self.report_data.get('output_translator', {})
        cai_translation = self.report_data.get('cai_translation', {})
        compression = self.report_data.get('waterfall_compression', {})
        
        if output_translator and 'latency_metrics' in output_translator:
            avg_latency = output_translator['latency_metrics']['avg_latency_ms']
            p95_latency = output_translator['latency_metrics']['p95_latency_ms']
            
            # Calculate scaling projections
            concurrent_capacity_estimates = {
                'single_instance_rps': 1000 / avg_latency if avg_latency > 0 else 0,
                'p95_concurrent_capacity': 1000 / p95_latency if p95_latency > 0 else 0,
                'estimated_instances_for_1000_rps': max(1, int((1000 * avg_latency) / 1000)) if avg_latency > 0 else 1,
                'memory_scaling_factor': self._estimate_memory_scaling(),
                'cpu_utilization_estimate': min(100, (avg_latency / 10) * 2)  # Rough estimate
            }
            
            self.report_data['scalability_analysis'] = {
                'performance_projections': concurrent_capacity_estimates,
                'bottleneck_analysis': self._identify_bottlenecks(),
                'scaling_recommendations': self._generate_scaling_recommendations()
            }
    
    def calculate_customer_benefit_metrics(self):
        """Calculate concrete customer benefit metrics for ROI analysis"""
        
        compression_data = self.report_data.get('waterfall_compression', {})
        output_translator_data = self.report_data.get('output_translator', {})
        
        if compression_data and 'compression_efficiency' in compression_data:
            avg_compression = compression_data['compression_efficiency']['avg_compression_ratio']
            
            # Token cost savings calculations (using typical LLM pricing)
            token_costs = {
                'gpt4_input_per_1k': 0.03,  # $0.03 per 1K tokens
                'gpt4_output_per_1k': 0.06,  # $0.06 per 1K tokens
                'claude_input_per_1k': 0.015,  # $0.015 per 1K tokens
                'claude_output_per_1k': 0.075   # $0.075 per 1K tokens
            }
            
            # Calculate savings for different usage volumes
            usage_scenarios = {
                'small_team': 100000,      # 100K tokens/month
                'medium_company': 1000000,  # 1M tokens/month  
                'enterprise': 10000000     # 10M tokens/month
            }
            
            customer_benefits = {}
            for scenario, monthly_tokens in usage_scenarios.items():
                tokens_saved = monthly_tokens * (avg_compression / 100)
                
                customer_benefits[scenario] = {
                    'monthly_tokens_processed': monthly_tokens,
                    'tokens_saved_per_month': tokens_saved,
                    'cost_savings_gpt4': tokens_saved * token_costs['gpt4_input_per_1k'] / 1000,
                    'cost_savings_claude': tokens_saved * token_costs['claude_input_per_1k'] / 1000,
                    'annual_savings_gpt4': tokens_saved * token_costs['gpt4_input_per_1k'] / 1000 * 12,
                    'annual_savings_claude': tokens_saved * token_costs['claude_input_per_1k'] / 1000 * 12,
                    'compression_ratio': avg_compression
                }
            
            # Add latency benefits
            if output_translator_data and 'latency_metrics' in output_translator_data:
                avg_latency = output_translator_data['latency_metrics']['avg_latency_ms']
                for scenario in customer_benefits:
                    requests_per_month = usage_scenarios[scenario] / 100  # Assume 100 tokens per request
                    time_saved_seconds = (requests_per_month * 200) / 1000  # Assume 200ms saved per request
                    customer_benefits[scenario]['time_savings_hours_per_month'] = time_saved_seconds / 3600
            
            self.report_data['customer_benefits'] = customer_benefits
    
    def _percentile(self, data: List[float], percentile: float) -> float:
        """Calculate percentile value"""
        if not data:
            return 0
        sorted_data = sorted(data)
        index = int(len(sorted_data) * percentile)
        return sorted_data[min(index, len(sorted_data) - 1)]
    
    def _calculate_cost_savings(self, compression_ratio: float) -> float:
        """Calculate estimated cost savings per 1K tokens"""
        avg_token_cost = 0.025  # Average cost per 1K tokens across major LLMs
        return (compression_ratio / 100) * avg_token_cost
    
    def _estimate_memory_scaling(self) -> float:
        """Estimate memory scaling factor"""
        # Simplified model - actual implementation would analyze memory usage patterns
        return 1.2  # 20% memory overhead per instance
    
    def _identify_bottlenecks(self) -> Dict[str, Any]:
        """Identify potential system bottlenecks"""
        bottlenecks = {}
        
        # Analyze latency distribution to identify bottlenecks
        output_translator = self.report_data.get('output_translator', {})
        if 'latency_metrics' in output_translator:
            avg_latency = output_translator['latency_metrics']['avg_latency_ms']
            p95_latency = output_translator['latency_metrics']['p95_latency_ms']
            
            if p95_latency > avg_latency * 2:
                bottlenecks['latency_variance'] = {
                    'severity': 'high',
                    'description': 'High latency variance detected',
                    'recommendation': 'Investigate outlier patterns and optimize worst-case scenarios'
                }
        
        return bottlenecks
    
    def _generate_scaling_recommendations(self) -> List[str]:
        """Generate scaling recommendations based on performance data"""
        recommendations = []
        
        output_translator = self.report_data.get('output_translator', {})
        if 'latency_metrics' in output_translator:
            avg_latency = output_translator['latency_metrics']['avg_latency_ms']
            
            if avg_latency > 50:
                recommendations.append("Consider implementing caching layer to reduce average latency")
            
            if avg_latency < 20:
                recommendations.append("Excellent latency performance - suitable for real-time applications")
        
        compression = self.report_data.get('waterfall_compression', {})
        if 'compression_efficiency' in compression:
            avg_compression = compression['compression_efficiency']['avg_compression_ratio']
            
            if avg_compression > 40:
                recommendations.append("High compression ratios achieved - excellent token cost savings potential")
            
            if avg_compression < 20:
                recommendations.append("Consider optimizing compression algorithms for better cost efficiency")
        
        return recommendations
    
    def generate_comprehensive_report(self) -> Dict[str, Any]:
        """Generate the complete performance report"""
        print("🔍 Analyzing OptimizeAI System Performance...")
        
        # Run all analyses
        self.analyze_cai_translation_performance()
        self.analyze_output_translator_performance()
        self.analyze_waterfall_compression_performance()
        self.analyze_system_scalability_metrics()
        self.calculate_customer_benefit_metrics()
        
        # Add metadata
        self.report_data['report_metadata'] = {
            'generated_at': self.timestamp.isoformat(),
            'analysis_version': '1.0',
            'data_sources': [
                'comprehensive_cai_test_results.json',
                'output_translator_benchmark_results.json', 
                'waterfall_compression_report.txt'
            ]
        }
        
        return self.report_data
    
    def export_report(self, filename: str = None):
        """Export report to JSON file"""
        if not filename:
            filename = f"optimize_ai_performance_report_{self.timestamp.strftime('%Y%m%d_%H%M%S')}.json"
        
        filepath = self.data_dir / filename
        with open(filepath, 'w') as f:
            json.dump(self.report_data, f, indent=2, default=str)
        
        print(f"📊 Comprehensive performance report exported to: {filepath}")
        return filepath
    
    def print_executive_summary(self):
        """Print executive summary of key metrics"""
        print("\n" + "="*80)
        print("🚀 OPTIMIZE_AI SYSTEM PERFORMANCE EXECUTIVE SUMMARY")
        print("="*80)
        
        # CAI Translation Performance
        if 'cai_translation' in self.report_data:
            cai = self.report_data['cai_translation']
            success_rate = cai.get('success_rate', 0) * 100
            pattern_types = len(cai.get('pattern_types_supported', []))
            
            print(f"\n📋 CAI TRANSLATION ENGINE:")
            print(f"   Success Rate: {success_rate:.1f}% ({cai.get('successful_tests', 0)}/{cai.get('total_tests', 0)} tests)")
            print(f"   Pattern Types: {pattern_types} supported ({', '.join(cai.get('pattern_types_supported', []))})")
            
            if 'code_expansion' in cai:
                expansion = cai['code_expansion']['avg_expansion_ratio']
                print(f"   Code Expansion: {expansion:.2f}x average")
        
        # Output Translator Performance  
        if 'output_translator' in self.report_data:
            ot = self.report_data['output_translator']
            success_rate = ot.get('success_rate', 0) * 100
            
            print(f"\n⚡ OUTPUT TRANSLATOR:")
            print(f"   Success Rate: {success_rate:.1f}%")
            
            if 'latency_metrics' in ot:
                latency = ot['latency_metrics']
                print(f"   Avg Latency: {latency.get('avg_latency_ms', 0):.1f}ms")
                print(f"   P95 Latency: {latency.get('p95_latency_ms', 0):.1f}ms")
            
            if 'throughput_metrics' in ot:
                throughput = ot['throughput_metrics']
                print(f"   Throughput: {throughput.get('avg_throughput_per_second', 0):.1f} translations/sec")
        
        # Compression Performance
        if 'waterfall_compression' in self.report_data:
            wc = self.report_data['waterfall_compression']
            
            print(f"\n🗜️  WATERFALL COMPRESSION:")
            if 'compression_efficiency' in wc:
                comp_eff = wc['compression_efficiency']
                print(f"   Avg Compression: {comp_eff.get('avg_compression_ratio', 0):.1f}%")
                print(f"   Best Compression: {comp_eff.get('best_compression', 0):.1f}%")
            
            if 'semantic_preservation' in wc:
                semantic = wc['semantic_preservation']
                print(f"   Semantic Similarity: {semantic.get('avg_semantic_similarity', 0):.3f}")
        
        # Customer Benefits
        if 'customer_benefits' in self.report_data:
            benefits = self.report_data['customer_benefits']
            
            print(f"\n💰 CUSTOMER COST SAVINGS:")
            for scenario, data in benefits.items():
                scenario_name = scenario.replace('_', ' ').title()
                annual_savings = data.get('annual_savings_gpt4', 0)
                monthly_tokens = data.get('monthly_tokens_processed', 0)
                print(f"   {scenario_name}: ${annual_savings:,.2f}/year (processing {monthly_tokens:,} tokens/month)")
        
        # Scaling Analysis
        if 'scalability_analysis' in self.report_data:
            scaling = self.report_data['scalability_analysis']
            
            print(f"\n📈 SCALABILITY PROJECTIONS:")
            if 'performance_projections' in scaling:
                proj = scaling['performance_projections']
                print(f"   Single Instance: {proj.get('single_instance_rps', 0):.1f} requests/sec")
                print(f"   1000 RPS Needs: {proj.get('estimated_instances_for_1000_rps', 0)} instances")
            
            if 'scaling_recommendations' in scaling:
                recommendations = scaling['scaling_recommendations']
                print(f"\n🎯 KEY RECOMMENDATIONS:")
                for i, rec in enumerate(recommendations[:3], 1):
                    print(f"   {i}. {rec}")
        
        print("="*80)

def main():
    """Main execution function"""
    analyzer = OptimizeAIPerformanceAnalyzer()
    
    # Generate comprehensive report
    report_data = analyzer.generate_comprehensive_report()
    
    # Print executive summary
    analyzer.print_executive_summary()
    
    # Export detailed report
    report_file = analyzer.export_report()
    
    return report_data, report_file

if __name__ == "__main__":
    main()
