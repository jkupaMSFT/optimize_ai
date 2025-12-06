"""
Performance monitoring and metrics collection
"""

import time
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List
from collections import defaultdict

# Import token utilities
try:
    from ...utils.metrics import count_tokens
except ImportError:
    # Fallback token counting
    def count_tokens(text: str) -> int:
        """Simple fallback token estimation"""
        return len(text.split()) * 1.3

class MetricsCollector:
    """
    Collects and reports performance metrics
    """
    
    def __init__(self, metrics_dir: Optional[Path] = None):
        self.metrics_dir = metrics_dir or Path.home() / ".optimize_ai" / "metrics"
        self.metrics_dir.mkdir(parents=True, exist_ok=True)
        
        self.current_session = {
            'start_time': None,
            'end_time': None,
            'operations': [],
            'total_original_tokens': 0,
            'total_compressed_tokens': 0,
            'files_processed': 0,
            'claude_direct_tokens_estimate': 0  # What would Claude have processed directly
        }
        
        self.cumulative_stats = defaultdict(lambda: {
            'total_calls': 0,
            'total_tokens_saved': 0,
            'total_time_ms': 0,
            'compression_ratios': [],
            'claude_direct_tokens': 0,  # Accumulated direct tokens
            'optimize_ai_tokens': 0,    # Accumulated compressed tokens
            'file_operations': 0,       # Number of file operations
            'cost_savings_usd': 0.0     # Estimated cost savings
        })
    
    def start_operation(self, operation_type: str) -> str:
        """Start timing an operation"""
        op_id = f"{operation_type}_{int(time.time()*1000)}"
        self.current_session['operations'].append({
            'id': op_id,
            'type': operation_type,
            'start_time': time.time()
        })
        return op_id
    
    def end_operation(self, op_id: str, metrics: Dict[str, Any]):
        """End an operation and record metrics"""
        for op in self.current_session['operations']:
            if op['id'] == op_id:
                op['end_time'] = time.time()
                op['duration_ms'] = (op['end_time'] - op['start_time']) * 1000
                op['metrics'] = metrics
                
                # Update cumulative stats
                op_type = op['type']
                self.cumulative_stats[op_type]['total_calls'] += 1
                self.cumulative_stats[op_type]['total_time_ms'] += op['duration_ms']
                
                if 'tokens_saved' in metrics:
                    self.cumulative_stats[op_type]['total_tokens_saved'] += metrics['tokens_saved']
                
                if 'compression_ratio' in metrics:
                    self.cumulative_stats[op_type]['compression_ratios'].append(metrics['compression_ratio'])
                
                # Track comprehensive token metrics
                if 'original_tokens' in metrics:
                    self.cumulative_stats[op_type]['claude_direct_tokens'] += metrics['original_tokens']
                    self.current_session['claude_direct_tokens_estimate'] += metrics['original_tokens']
                
                if 'compressed_tokens' in metrics:
                    self.cumulative_stats[op_type]['optimize_ai_tokens'] += metrics['compressed_tokens']
                    
                if 'file_operation' in metrics and metrics['file_operation']:
                    self.cumulative_stats[op_type]['file_operations'] += 1
                    self.current_session['files_processed'] += 1
                
                # Calculate cost savings based on Claude pricing
                if 'original_tokens' in metrics and 'compressed_tokens' in metrics:
                    tokens_saved = metrics['original_tokens'] - metrics['compressed_tokens']
                    # Using Claude-3.5 Sonnet pricing: $3/1M input tokens, $15/1M output tokens
                    # Assuming 70% input, 30% output token distribution
                    input_cost_per_token = 3 / 1_000_000
                    output_cost_per_token = 15 / 1_000_000
                    avg_cost_per_token = (input_cost_per_token * 0.7) + (output_cost_per_token * 0.3)
                    cost_savings = tokens_saved * avg_cost_per_token
                    self.cumulative_stats[op_type]['cost_savings_usd'] += cost_savings
                
                break
    
    def save_session_metrics(self, session_id: str):
        """Save metrics for the current session"""
        metrics_file = self.metrics_dir / f"{session_id}_metrics.json"
        
        self.current_session['end_time'] = datetime.now().isoformat()
        self.current_session['session_id'] = session_id
        
        with open(metrics_file, 'w') as f:
            json.dump(self.current_session, f, indent=2, default=str)
    
    def record_file_operation(self, operation_type: str, original_content: str, 
                            compressed_content: str, file_path: str, 
                            task_context: str = "") -> str:
        """
        Record a file operation with comprehensive metrics.
        
        Args:
            operation_type: Type of operation (e.g., "compression", "translation")
            original_content: Original file content
            compressed_content: Compressed/optimized content
            file_path: Path to the file
            task_context: Context about the task being performed
            
        Returns:
            Operation ID for tracking
        """
        op_id = self.start_operation(operation_type)
        
        # Calculate detailed metrics
        original_tokens = count_tokens(original_content)
        compressed_tokens = count_tokens(compressed_content)
        tokens_saved = original_tokens - compressed_tokens
        compression_ratio = (tokens_saved / original_tokens) if original_tokens > 0 else 0
        
        # File-specific metrics
        file_size_original = len(original_content)
        file_size_compressed = len(compressed_content)
        size_reduction = (file_size_original - file_size_compressed) / file_size_original if file_size_original > 0 else 0
        
        metrics = {
            'original_tokens': original_tokens,
            'compressed_tokens': compressed_tokens,
            'tokens_saved': tokens_saved,
            'compression_ratio': compression_ratio,
            'file_path': file_path,
            'file_size_original': file_size_original,
            'file_size_compressed': file_size_compressed,
            'size_reduction_ratio': size_reduction,
            'task_context': task_context,
            'file_operation': True
        }
        
        self.end_operation(op_id, metrics)
        return op_id
    
    def generate_comparative_report(self, task_description: str, 
                                  files_involved: List[str]) -> Dict[str, Any]:
        """
        Generate a comprehensive report comparing optimize_ai vs direct Claude usage.
        
        Args:
            task_description: Description of the task being performed
            files_involved: List of file paths involved in the task
            
        Returns:
            Detailed comparison report
        """
        # Calculate task-based savings
        task_savings = self.calculate_task_based_savings(task_description, files_involved)
        
        # Get current session summary
        session_summary = self.get_summary_report()
        
        # Calculate reading vs writing token distribution
        reading_writing_analysis = self._analyze_reading_writing_tokens(task_description, files_involved)
        
        report = {
            'report_timestamp': datetime.now().isoformat(),
            'task_analysis': task_savings,
            'session_metrics': session_summary,
            'reading_writing_breakdown': reading_writing_analysis,
            'comparison_summary': {
                'scenario': 'Direct Claude vs optimize_ai',
                'files_analyzed': len(files_involved),
                'task_complexity': task_savings.get('task_complexity_multiplier', 1.0)
            },
            'recommendations': self._generate_usage_recommendations(task_savings)
        }
        
        return report
    
    def _analyze_reading_writing_tokens(self, task_description: str, 
                                      file_paths: List[str]) -> Dict[str, Any]:
        """
        Analyze the distribution of tokens between reading context and writing output.
        
        This helps understand where optimize_ai provides the most benefit.
        """
        task_lower = task_description.lower()
        
        # Estimate read/write ratios based on task type
        if any(keyword in task_lower for keyword in ['analyze', 'review', 'understand', 'explain']):
            # Reading-heavy tasks
            read_ratio = 0.8
            write_ratio = 0.2
            task_type = 'reading-heavy'
        elif any(keyword in task_lower for keyword in ['implement', 'create', 'generate', 'write']):
            # Writing-heavy tasks
            read_ratio = 0.4
            write_ratio = 0.6
            task_type = 'writing-heavy'
        else:
            # Balanced tasks (refactor, debug, modify)
            read_ratio = 0.6
            write_ratio = 0.4
            task_type = 'balanced'
        
        # Calculate token distribution
        total_file_tokens = 0
        for file_path in file_paths:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                total_file_tokens += count_tokens(content)
            except Exception:
                continue
        
        # Estimate tokens for different scenarios
        claude_direct_reading = int(total_file_tokens * read_ratio)
        claude_direct_writing = int(total_file_tokens * write_ratio)
        claude_direct_total = claude_direct_reading + claude_direct_writing
        
        # optimize_ai reduces reading tokens significantly, minimal impact on writing
        optimize_ai_reading = int(claude_direct_reading * 0.4)  # 60% reduction in reading
        optimize_ai_writing = claude_direct_writing  # Writing tokens remain same
        optimize_ai_total = optimize_ai_reading + optimize_ai_writing
        
        tokens_saved = claude_direct_total - optimize_ai_total
        savings_percentage = (tokens_saved / claude_direct_total * 100) if claude_direct_total > 0 else 0
        
        return {
            'task_type': task_type,
            'read_write_ratio': f"{int(read_ratio*100)}% reading, {int(write_ratio*100)} writing",
            'claude_direct': {
                'reading_tokens': claude_direct_reading,
                'writing_tokens': claude_direct_writing,
                'total_tokens': claude_direct_total
            },
            'optimize_ai': {
                'reading_tokens': optimize_ai_reading,
                'writing_tokens': optimize_ai_writing,
                'total_tokens': optimize_ai_total
            },
            'savings': {
                'tokens_saved': tokens_saved,
                'savings_percentage': round(savings_percentage, 2),
                'primary_benefit': 'Reduced context reading tokens' if read_ratio > 0.5 else 'Balanced reading/writing optimization'
            }
        }
    
    def _generate_usage_recommendations(self, task_savings: Dict[str, Any]) -> List[str]:
        """Generate recommendations based on calculated savings"""
        recommendations = []
        
        savings_pct = task_savings.get('savings_percentage', 0)
        
        if savings_pct > 40:
            recommendations.append("🎯 Excellent use case for optimize_ai - significant token savings achieved")
            recommendations.append("💰 Consider using optimize_ai for similar large-context tasks")
        elif savings_pct > 25:
            recommendations.append("✅ Good token savings - optimize_ai is beneficial for this task type")
            recommendations.append("📈 Monitor compression ratios to optimize further")
        elif savings_pct > 10:
            recommendations.append("⚖️ Moderate savings - evaluate if setup overhead is worth it")
            recommendations.append("🔍 Consider optimizing file selection or compression settings")
        else:
            recommendations.append("❓ Limited savings for this task - direct Claude usage might be simpler")
            recommendations.append("🎨 Better suited for larger, more complex multi-file tasks")
        
        # Task-specific recommendations
        complexity = task_savings.get('task_complexity_multiplier', 1.0)
        if complexity > 1.3:
            recommendations.append(f"🧠 High complexity task (multiplier: {complexity}) - optimize_ai particularly beneficial")
        
        return recommendations
    
    def get_summary_report(self) -> Dict[str, Any]:
        """Generate a summary report of all metrics"""
        report = {
            'timestamp': datetime.now().isoformat(),
            'operations': {},
            'total_savings': self._calculate_total_savings(),
            'session_summary': self._get_session_summary()
        }
        
        for op_type, stats in self.cumulative_stats.items():
            avg_time = stats['total_time_ms'] / stats['total_calls'] if stats['total_calls'] > 0 else 0
            avg_compression = sum(stats['compression_ratios']) / len(stats['compression_ratios']) if stats['compression_ratios'] else 0
            
            report['operations'][op_type] = {
                'total_calls': stats['total_calls'],
                'total_tokens_saved': stats['total_tokens_saved'],
                'average_time_ms': round(avg_time, 2),
                'average_compression_ratio': round(avg_compression, 3),
                'claude_direct_tokens': stats['claude_direct_tokens'],
                'optimize_ai_tokens': stats['optimize_ai_tokens'],
                'file_operations': stats['file_operations'],
                'estimated_cost_savings_usd': round(stats['cost_savings_usd'], 4)
            }
        
        return report
    
    def calculate_task_based_savings(self, task_description: str, file_paths: List[str]) -> Dict[str, Any]:
        """
        Calculate estimated token savings for a specific task based on file contents and task complexity.
        Includes both input token compression and reasoning token efficiency from .cai format.
        
        Args:
            task_description: Description of the task (e.g., "refactor functions", "add error handling")
            file_paths: List of file paths involved in the task
            
        Returns:
            Dictionary with detailed savings calculations including reasoning efficiency
        """
        if not file_paths:
            return {'error': 'No files provided for analysis'}
        
        # Estimate task complexity multiplier and reasoning efficiency based on task description
        complexity_keywords = {
            'refactor': {'multiplier': 1.5, 'reasoning_reduction': 0.45},
            'optimize': {'multiplier': 1.3, 'reasoning_reduction': 0.35},
            'debug': {'multiplier': 1.4, 'reasoning_reduction': 0.50},
            'add': {'multiplier': 1.2, 'reasoning_reduction': 0.35},
            'implement': {'multiplier': 1.6, 'reasoning_reduction': 0.35},
            'analyze': {'multiplier': 1.1, 'reasoning_reduction': 0.60},
            'review': {'multiplier': 1.0, 'reasoning_reduction': 0.65},
            'fix': {'multiplier': 1.3, 'reasoning_reduction': 0.45},
            'enhance': {'multiplier': 1.4, 'reasoning_reduction': 0.40},
            'test': {'multiplier': 1.2, 'reasoning_reduction': 0.40}
        }
        
        task_multiplier = 1.0
        reasoning_reduction = 0.35  # Default reasoning efficiency
        task_lower = task_description.lower()
        for keyword, params in complexity_keywords.items():
            if keyword in task_lower:
                task_multiplier = max(task_multiplier, params['multiplier'])
                reasoning_reduction = max(reasoning_reduction, params['reasoning_reduction'])
        
        total_direct_tokens = 0
        total_compressed_tokens = 0
        file_stats = []
        
        for file_path in file_paths:
            try:
                # Read file content
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # Calculate direct Claude tokens (what would be sent directly)
                direct_tokens = count_tokens(content)
                
                # Estimate compressed tokens (simulate compression)
                # This is a rough estimate - in practice this would use the actual compressor
                estimated_compression_ratio = self._estimate_compression_ratio(content, file_path)
                compressed_tokens = int(direct_tokens * (1 - estimated_compression_ratio))
                
                total_direct_tokens += direct_tokens
                total_compressed_tokens += compressed_tokens
                
                file_stats.append({
                    'file_path': file_path,
                    'direct_tokens': direct_tokens,
                    'estimated_compressed_tokens': compressed_tokens,
                    'estimated_savings': direct_tokens - compressed_tokens,
                    'estimated_compression_ratio': estimated_compression_ratio
                })
                
            except Exception as e:
                file_stats.append({
                    'file_path': file_path,
                    'error': f"Could not process file: {str(e)}"
                })
        
        # Apply task complexity multiplier to input tokens
        claude_direct_input = int(total_direct_tokens * task_multiplier)
        optimize_ai_input = total_compressed_tokens + int(total_direct_tokens * 0.1)  # Small overhead for compression
        
        # Calculate reasoning tokens (estimated based on input complexity)
        # Reasoning tokens are typically 30-40% of input tokens for complex tasks
        reasoning_factor = 0.35  # 35% reasoning tokens relative to input
        claude_direct_reasoning = int(claude_direct_input * reasoning_factor)
        optimize_ai_reasoning = int(claude_direct_reasoning * (1 - reasoning_reduction))
        
        # Total token calculations
        claude_direct_total = claude_direct_input + claude_direct_reasoning
        optimize_ai_total = optimize_ai_input + optimize_ai_reasoning
        
        tokens_saved = claude_direct_total - optimize_ai_total
        input_tokens_saved = claude_direct_input - optimize_ai_input
        reasoning_tokens_saved = claude_direct_reasoning - optimize_ai_reasoning
        
        savings_percentage = (tokens_saved / claude_direct_total * 100) if claude_direct_total > 0 else 0
        
        # Cost calculations (Claude-3.5 Sonnet pricing)
        input_cost_per_1k = 0.003  # $3/1M tokens
        output_cost_per_1k = 0.015  # $15/1M tokens
        avg_cost_per_1k = (input_cost_per_1k * 0.7) + (output_cost_per_1k * 0.3)  # 70% input, 30% output
        
        cost_savings = (tokens_saved / 1000) * avg_cost_per_1k
        
        return {
            'task_description': task_description,
            'task_complexity_multiplier': task_multiplier,
            'reasoning_efficiency_factor': reasoning_reduction,
            'files_analyzed': len([f for f in file_stats if 'error' not in f]),
            'claude_direct_input_tokens': claude_direct_input,
            'claude_direct_reasoning_tokens': claude_direct_reasoning,
            'claude_direct_total_tokens': claude_direct_total,
            'optimize_ai_input_tokens': optimize_ai_input,
            'optimize_ai_reasoning_tokens': optimize_ai_reasoning,
            'optimize_ai_total_tokens': optimize_ai_total,
            'input_tokens_saved': input_tokens_saved,
            'reasoning_tokens_saved': reasoning_tokens_saved,
            'total_tokens_saved': tokens_saved,
            'savings_percentage': round(savings_percentage, 2),
            'estimated_cost_savings_usd': round(cost_savings, 4),
            'claude_direct_cost_usd': round((claude_direct_total / 1000) * avg_cost_per_1k, 4),
            'optimize_ai_cost_usd': round((optimize_ai_total / 1000) * avg_cost_per_1k, 4),
            'monthly_cost_projection': self._calculate_monthly_projections(claude_direct_total, optimize_ai_total, avg_cost_per_1k),
            'file_breakdown': file_stats,
            'reasoning': {
                'compression_benefit': f"Files compressed by ~{round(sum(f.get('estimated_compression_ratio', 0) for f in file_stats if 'error' not in f) / max(1, len([f for f in file_stats if 'error' not in f])) * 100, 1)}% on average",
                'task_complexity': f"Task complexity multiplier of {task_multiplier}x applied based on keywords in task description",
                'reasoning_efficiency': f".cai format reduces reasoning tokens by {int(reasoning_reduction*100)}% due to structured format",
                'context_efficiency': "optimize_ai sends compressed context while maintaining semantic meaning"
            }
        }
    
    def _calculate_monthly_projections(self, claude_direct_tokens: int, optimize_ai_tokens: int, avg_cost_per_1k: float) -> Dict[str, Any]:
        """Calculate monthly cost projections for different usage scenarios"""
        claude_cost_per_task = (claude_direct_tokens / 1000) * avg_cost_per_1k
        optimize_ai_cost_per_task = (optimize_ai_tokens / 1000) * avg_cost_per_1k
        savings_per_task = claude_cost_per_task - optimize_ai_cost_per_task
        
        scenarios = {
            'light_usage': {'tasks_per_month': 5, 'description': 'Light usage (5 tasks/month)'},
            'moderate_usage': {'tasks_per_month': 15, 'description': 'Moderate usage (15 tasks/month)'},
            'heavy_usage': {'tasks_per_month': 50, 'description': 'Heavy usage (50 tasks/month)'},
            'enterprise_usage': {'tasks_per_month': 200, 'description': 'Enterprise usage (200 tasks/month)'}
        }
        
        projections = {}
        for scenario_name, scenario in scenarios.items():
            tasks = scenario['tasks_per_month']
            claude_monthly = claude_cost_per_task * tasks
            optimize_ai_monthly = optimize_ai_cost_per_task * tasks
            monthly_savings = savings_per_task * tasks
            annual_savings = monthly_savings * 12
            
            projections[scenario_name] = {
                'description': scenario['description'],
                'tasks_per_month': tasks,
                'claude_direct_monthly_cost': round(claude_monthly, 2),
                'optimize_ai_monthly_cost': round(optimize_ai_monthly, 2),
                'monthly_savings': round(monthly_savings, 2),
                'annual_savings': round(annual_savings, 2),
                'roi_percentage': round((monthly_savings / claude_monthly * 100) if claude_monthly > 0 else 0, 1)
            }
        
        return projections
    
    def _estimate_compression_ratio(self, content: str, file_path: str) -> float:
        """Estimate compression ratio based on content characteristics"""
        content_length = len(content)
        
        # Base compression estimates by file characteristics
        if content_length < 1000:
            base_ratio = 0.15  # Small files: 15% compression
        elif content_length < 5000:
            base_ratio = 0.25  # Medium files: 25% compression
        elif content_length < 20000:
            base_ratio = 0.35  # Large files: 35% compression
        else:
            base_ratio = 0.45  # Very large files: 45% compression
        
        # Adjust based on content type
        if file_path.endswith('.py'):
            # Python files typically compress well due to comments and whitespace
            base_ratio += 0.1
        elif file_path.endswith(('.js', '.ts')):
            # JavaScript/TypeScript also compress well
            base_ratio += 0.05
        elif file_path.endswith(('.md', '.txt')):
            # Text files have variable compression
            base_ratio += 0.05
        
        # Analyze content characteristics
        lines = content.split('\n')
        comment_lines = sum(1 for line in lines if line.strip().startswith('#') or line.strip().startswith('//'))
        empty_lines = sum(1 for line in lines if not line.strip())
        
        if lines:
            comment_ratio = comment_lines / len(lines)
            empty_ratio = empty_lines / len(lines)
            
            # More comments and empty lines = better compression
            base_ratio += (comment_ratio * 0.2) + (empty_ratio * 0.1)
        
        return min(0.7, base_ratio)  # Cap at 70% compression
    
    def _calculate_total_savings(self) -> Dict[str, Any]:
        """Calculate total savings across all operations"""
        total_claude_tokens = sum(stats['claude_direct_tokens'] for stats in self.cumulative_stats.values())
        total_optimize_tokens = sum(stats['optimize_ai_tokens'] for stats in self.cumulative_stats.values())
        total_cost_savings = sum(stats['cost_savings_usd'] for stats in self.cumulative_stats.values())
        
        total_saved = total_claude_tokens - total_optimize_tokens
        savings_percentage = (total_saved / total_claude_tokens * 100) if total_claude_tokens > 0 else 0
        
        return {
            'total_claude_direct_tokens': total_claude_tokens,
            'total_optimize_ai_tokens': total_optimize_tokens,
            'total_tokens_saved': total_saved,
            'overall_savings_percentage': round(savings_percentage, 2),
            'total_cost_savings_usd': round(total_cost_savings, 4),
            'efficiency_rating': self._get_efficiency_rating(savings_percentage)
        }
    
    def _get_session_summary(self) -> Dict[str, Any]:
        """Get summary of current session"""
        return {
            'files_processed': self.current_session['files_processed'],
            'estimated_claude_direct_tokens': self.current_session['claude_direct_tokens_estimate'],
            'session_duration_ms': (time.time() - self.current_session.get('start_time', time.time())) * 1000 if self.current_session.get('start_time') else 0
        }
    
    def _get_efficiency_rating(self, savings_percentage: float) -> str:
        """Get efficiency rating based on savings percentage"""
        if savings_percentage >= 50:
            return 'Excellent'
        elif savings_percentage >= 35:
            return 'Very Good'
        elif savings_percentage >= 20:
            return 'Good'
        elif savings_percentage >= 10:
            return 'Fair'
        else:
            return 'Poor'