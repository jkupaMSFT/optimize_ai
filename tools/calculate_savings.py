#!/usr/bin/env python3
"""
Command-line tool to calculate token savings when using optimize_ai vs direct Claude usage.
"""

import argparse
import sys
import json
from pathlib import Path
from typing import List

# Add the parent directory to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from integrations.claude_wrapper.metrics import MetricsCollector
except ImportError:
    print("❌ Error: Could not import MetricsCollector. Make sure you're running from the correct directory.")
    sys.exit(1)

def main():
    parser = argparse.ArgumentParser(
        description="Calculate token savings when using optimize_ai vs direct Claude usage",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Analyze a refactoring task
  python calculate_savings.py --task "refactor authentication system" --files app.py core/auth.py

  # Analyze code review task
  python calculate_savings.py --task "review for security issues" --files "*.py"

  # Generate detailed report
  python calculate_savings.py --task "implement new features" --files src/*.py --detailed --output report.json

  # Quick analysis of current directory Python files
  python calculate_savings.py --task "debug performance issues" --auto-detect
        """
    )
    
    parser.add_argument(
        '--task',
        required=True,
        help='Description of the task you want to perform (e.g., "refactor functions", "add error handling")'
    )
    
    parser.add_argument(
        '--files',
        nargs='+',
        help='List of files to analyze (supports glob patterns like "*.py")'
    )
    
    parser.add_argument(
        '--auto-detect',
        action='store_true',
        help='Automatically detect Python files in current directory'
    )
    
    parser.add_argument(
        '--detailed',
        action='store_true',
        help='Generate detailed analysis report'
    )
    
    parser.add_argument(
        '--output',
        help='Output file to save detailed report (JSON format)'
    )
    
    parser.add_argument(
        '--format',
        choices=['simple', 'json', 'detailed'],
        default='simple',
        help='Output format (default: simple)'
    )
    
    args = parser.parse_args()
    
    # Validate arguments
    if not args.files and not args.auto_detect:
        print("❌ Error: Must specify either --files or --auto-detect")
        sys.exit(1)
    
    # Resolve file paths
    file_paths = resolve_file_paths(args.files, args.auto_detect)
    
    if not file_paths:
        print("❌ Error: No files found to analyze")
        sys.exit(1)
    
    print(f"🎯 Task: {args.task}")
    print(f"📁 Analyzing {len(file_paths)} files...")
    
    # Calculate savings
    metrics = MetricsCollector()
    
    if args.detailed:
        report = metrics.generate_comparative_report(args.task, file_paths)
        display_detailed_report(report, args.format)
        
        if args.output:
            save_report(report, args.output)
    else:
        savings = metrics.calculate_task_based_savings(args.task, file_paths)
        display_simple_savings(savings, args.format)

def resolve_file_paths(files: List[str] = None, auto_detect: bool = False) -> List[str]:
    """Resolve file paths from arguments or auto-detection."""
    file_paths = []
    
    if auto_detect:
        # Auto-detect Python files in current directory
        current_dir = Path('.')
        file_paths = [str(p) for p in current_dir.glob('**/*.py') if p.is_file()]
        file_paths = file_paths[:10]  # Limit to first 10 files for performance
    
    elif files:
        # Process file arguments (support glob patterns)
        from glob import glob
        for file_pattern in files:
            if '*' in file_pattern or '?' in file_pattern:
                # Glob pattern
                matched_files = glob(file_pattern)
                file_paths.extend(matched_files)
            else:
                # Direct file path
                if Path(file_pattern).exists():
                    file_paths.append(file_pattern)
                else:
                    print(f"⚠️  Warning: File not found: {file_pattern}")
    
    # Remove duplicates and ensure files exist
    unique_paths = []
    for path in file_paths:
        if path not in unique_paths and Path(path).exists():
            unique_paths.append(path)
    
    return unique_paths

def display_simple_savings(savings: dict, format_type: str):
    """Display simple savings analysis."""
    if 'error' in savings:
        print(f"❌ Error: {savings['error']}")
        return
    
    if format_type == 'json':
        print(json.dumps(savings, indent=2))
        return
    
    # Simple text format
    print("\n📊 Token Savings Analysis (Including Reasoning Efficiency)")
    print("=" * 65)
    
    # Input token breakdown
    print("📥 Input Tokens:")
    print(f"   Claude Direct:     {savings.get('claude_direct_input_tokens', 'N/A'):,} tokens")
    print(f"   OptimizeAI:        {savings.get('optimize_ai_input_tokens', 'N/A'):,} tokens")
    print(f"   Input Savings:     {savings.get('input_tokens_saved', 'N/A'):,} tokens")
    
    # Reasoning token breakdown  
    print("\n🧠 Reasoning Tokens (.cai efficiency):")
    print(f"   Claude Direct:     {savings.get('claude_direct_reasoning_tokens', 'N/A'):,} tokens")
    print(f"   OptimizeAI:        {savings.get('optimize_ai_reasoning_tokens', 'N/A'):,} tokens") 
    print(f"   Reasoning Savings: {savings.get('reasoning_tokens_saved', 'N/A'):,} tokens")
    
    # Total breakdown
    print("\n🎯 Total Comparison:")
    print(f"   Claude Direct:     {savings.get('claude_direct_total_tokens', savings.get('claude_direct_tokens', 'N/A')):,} tokens")
    print(f"   OptimizeAI:        {savings.get('optimize_ai_total_tokens', savings.get('optimize_ai_tokens', 'N/A')):,} tokens")
    print(f"   Total Saved:       {savings.get('total_tokens_saved', savings.get('tokens_saved', 'N/A')):,} tokens")
    print(f"   Savings Percentage: {savings['savings_percentage']}%")
    print(f"   Cost Savings:      ${savings['estimated_cost_savings_usd']}")
    
    # Efficiency details
    reasoning_reduction = savings.get('reasoning_efficiency_factor', 0) * 100
    print(f"\n⚡ Efficiency Factors:")
    print(f"   Task Complexity:   {savings.get('task_complexity_multiplier', 1.0)}x")
    print(f"   Reasoning Reduction: {reasoning_reduction:.0f}% (from .cai format)")
    
    # Efficiency rating
    savings_pct = savings['savings_percentage']
    if savings_pct >= 50:
        rating = "🎯 Excellent"
        color = "green"
    elif savings_pct >= 35:
        rating = "✅ Very Good"
        color = "green"
    elif savings_pct >= 20:
        rating = "📈 Good"
        color = "yellow"
    elif savings_pct >= 10:
        rating = "⚖️ Fair"
        color = "yellow"
    else:
        rating = "❓ Poor"
        color = "red"
    
    print(f"   Overall Rating:    {rating}")
    
    # Recommendations
    print(f"\n💡 Recommendation:")
    if savings_pct > 50:
        print("   OptimizeAI is highly beneficial for this task!")
        print("   The .cai format provides significant reasoning efficiency gains.")
        print("   Consider using it for similar large-context tasks.")
    elif savings_pct > 35:
        print("   OptimizeAI provides good value for this task.")
        print("   Reasoning efficiency from .cai format adds substantial value.")
        print("   Monitor compression ratios to optimize further.")
    elif savings_pct > 20:
        print("   OptimizeAI provides moderate benefits.")
        print("   Reasoning savings help offset compression overhead.")
        print("   Evaluate if setup overhead is worth the savings.")
    else:
        print("   Direct Claude usage might be simpler for this task.")
        print("   OptimizeAI is better suited for larger, multi-file tasks.")
        print("   Even small tasks benefit from reasoning efficiency though.")

def display_detailed_report(report: dict, format_type: str):
    """Display detailed analysis report."""
    if format_type == 'json':
        print(json.dumps(report, indent=2))
        return
    
    task_analysis = report['task_analysis']
    reading_writing = report['reading_writing_breakdown']
    
    print("\n📊 Comprehensive Token Analysis Report (With Reasoning Efficiency)")
    print("=" * 75)
    
    # Task Analysis
    print(f"\n🎯 Task Analysis:")
    print(f"   Description: {task_analysis['task_description']}")
    print(f"   Complexity Multiplier: {task_analysis['task_complexity_multiplier']}x")
    reasoning_eff = task_analysis.get('reasoning_efficiency_factor', 0) * 100
    print(f"   Reasoning Efficiency: {reasoning_eff:.0f}% reduction from .cai format")
    print(f"   Files Analyzed: {task_analysis['files_analyzed']}")
    
    # Detailed Token Breakdown
    print(f"\n📈 Detailed Token Comparison:")
    print(f"   📥 Input Tokens:")
    print(f"      Claude Direct:  {task_analysis.get('claude_direct_input_tokens', 'N/A'):,}")
    print(f"      OptimizeAI:     {task_analysis.get('optimize_ai_input_tokens', 'N/A'):,}")
    print(f"      Input Savings:  {task_analysis.get('input_tokens_saved', 'N/A'):,}")
    
    print(f"   🧠 Reasoning Tokens:")
    print(f"      Claude Direct:  {task_analysis.get('claude_direct_reasoning_tokens', 'N/A'):,}")
    print(f"      OptimizeAI:     {task_analysis.get('optimize_ai_reasoning_tokens', 'N/A'):,}")
    print(f"      Reasoning Savings: {task_analysis.get('reasoning_tokens_saved', 'N/A'):,}")
    
    print(f"   🎯 Total:")
    total_claude = task_analysis.get('claude_direct_total_tokens', task_analysis.get('claude_direct_tokens', 'N/A'))
    total_optimize = task_analysis.get('optimize_ai_total_tokens', task_analysis.get('optimize_ai_tokens', 'N/A'))
    total_saved = task_analysis.get('total_tokens_saved', task_analysis.get('tokens_saved', 'N/A'))
    print(f"      Claude Direct:  {total_claude:,}")
    print(f"      OptimizeAI:     {total_optimize:,}")
    print(f"      Total Saved:    {total_saved:,} ({task_analysis['savings_percentage']}%)")
    print(f"      Cost Savings:   ${task_analysis['estimated_cost_savings_usd']}")
    
    # Reading/Writing Breakdown
    print(f"\n📖 Reading/Writing Analysis:")
    print(f"   Task Type: {reading_writing['task_type']}")
    print(f"   Token Distribution: {reading_writing['read_write_ratio']}")
    print(f"   Primary Benefit: {reading_writing['savings']['primary_benefit']}")
    print(f"   Reading Tokens Saved: {reading_writing['savings']['tokens_saved']:,}")
    
    # Reasoning Benefits
    print(f"\n⚡ .cai Format Benefits:")
    reasoning_data = task_analysis.get('reasoning', {})
    if 'reasoning_efficiency' in reasoning_data:
        print(f"   {reasoning_data['reasoning_efficiency']}")
    print(f"   Structured format enables faster pattern recognition")
    print(f"   Reduced cognitive load on Claude for code understanding")
    print(f"   Faster debugging and analysis due to semantic clarity")
    
    # File Breakdown
    if 'file_breakdown' in task_analysis:
        print(f"\n📁 File Breakdown:")
        for file_info in task_analysis['file_breakdown'][:5]:  # Show first 5 files
            if 'error' not in file_info:
                print(f"   {Path(file_info['file_path']).name}:")
                print(f"     Direct: {file_info['direct_tokens']:,.0f} tokens")
                print(f"     Compressed: {file_info['estimated_compressed_tokens']} tokens")
                print(f"     Savings: {file_info['estimated_savings']:,.0f} tokens")
    
    # Opportunity Cost Analysis
    if 'monthly_cost_projection' in task_analysis:
        print(f"\n💰 Opportunity Cost Analysis (What You'd Pay Without OptimizeAI):")
        projections = task_analysis['monthly_cost_projection']
        
        # Show a few key scenarios
        key_scenarios = ['light_usage', 'moderate_usage', 'heavy_usage']
        for scenario_name in key_scenarios:
            if scenario_name in projections:
                scenario = projections[scenario_name]
                print(f"   {scenario['description']}:")
                print(f"     Without OptimizeAI: ${scenario['claude_direct_monthly_cost']}/month")
                print(f"     With OptimizeAI: ${scenario['optimize_ai_monthly_cost']}/month")
                print(f"     💵 Monthly savings: ${scenario['monthly_savings']}")
                print(f"     📈 Annual savings: ${scenario['annual_savings']}")
                print(f"     🎯 ROI: {scenario['roi_percentage']}%")
                print()
    
    # Show direct cost comparison for current task
    if 'claude_direct_cost_usd' in task_analysis and 'optimize_ai_cost_usd' in task_analysis:
        print(f"💸 Current Task Cost Comparison:")
        print(f"   Direct Claude cost: ${task_analysis['claude_direct_cost_usd']:.4f}")
        print(f"   OptimizeAI cost: ${task_analysis['optimize_ai_cost_usd']:.4f}")
        print(f"   💰 You saved: ${task_analysis['estimated_cost_savings_usd']:.4f} on this task alone!")
    
    # Recommendations
    print(f"\n💡 Enhanced Recommendations:")
    for rec in report['recommendations']:
        print(f"   {rec}")
    print(f"   🧠 .cai format provides significant reasoning efficiency even for small tasks")
    print(f"   ⚡ Consider OptimizeAI even for simple reviews due to reasoning benefits")

def save_report(report: dict, output_file: str):
    """Save detailed report to file."""
    try:
        with open(output_file, 'w') as f:
            json.dump(report, f, indent=2, default=str)
        print(f"\n💾 Detailed report saved to: {output_file}")
    except Exception as e:
        print(f"❌ Error saving report: {e}")

if __name__ == '__main__':
    main()
