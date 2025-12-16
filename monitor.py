#!/usr/bin/env python3
"""
Monitor OptimizeAI compression statistics, debugging performance, and validate token savings
"""
import json
import hashlib
import time
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict

try:
    import tiktoken
    TIKTOKEN_AVAILABLE = True
except ImportError:
    TIKTOKEN_AVAILABLE = False

try:
    from sklearn.metrics.pairwise import cosine_similarity
    from sklearn.feature_extraction.text import TfidfVectorizer
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False

@dataclass
class DebuggingSession:
    """Represents a debugging session with performance metrics"""
    session_id: str
    file_path: str
    original_file_size: int
    compressed_file_size: int
    original_tokens: int
    compressed_tokens: int
    bugs_found: int
    bugs_fixed: int
    reasoning_tokens_used: int
    debugging_accuracy: float
    time_to_debug: float
    semantic_similarity_score: float
    compression_enabled: bool
    timestamp: str
    claude_response_tokens: int
    total_conversation_tokens: int

@dataclass
class TranslationMetrics:
    """Metrics for CAI to Python translation accuracy"""
    session_id: str
    original_cai_code: str
    translated_python_code: str
    semantic_similarity: float
    syntax_correctness: bool
    functionality_preserved: bool
    translation_time: float
    timestamp: str

@dataclass
class PostWriteMetrics:
    """Metrics for post-write hook performance"""
    session_id: str
    file_path: str
    file_size: int
    syntax_validation_time: float
    cache_invalidation_time: float
    total_processing_time: float
    syntax_valid: bool
    cache_invalidated: bool
    errors_encountered: List[str]
    hook_triggered_count: int
    timestamp: str

class CompressionMonitor:
    def __init__(self):
        # Use project cache directory instead of home directory
        project_root = Path(__file__).parent  # optimize_ai directory
        self.cache_dir = project_root / '.optimize_ai_cache'
        self.stats_file = project_root / '.optimize_ai_stats.json'
        self.debug_sessions_file = project_root / '.debug_sessions.json'
        self.translation_metrics_file = project_root / '.translation_metrics.json'
        self.post_write_metrics_file = project_root / '.post_write_metrics.json'
        
        # Initialize tiktoken encoder for accurate token counting
        if TIKTOKEN_AVAILABLE:
            self.encoder = tiktoken.encoding_for_model("gpt-4")
        else:
            self.encoder = None
        
        # Initialize TF-IDF vectorizer for semantic similarity
        if SKLEARN_AVAILABLE:
            self.vectorizer = TfidfVectorizer(stop_words='english', max_features=1000)
        else:
            self.vectorizer = None
    
    def count_tokens(self, text: str) -> int:
        """Count actual tokens using tiktoken (Claude uses similar tokenization)"""
        if self.encoder:
            return len(self.encoder.encode(text))
        else:
            # Fallback: rough estimate (4 chars per token)
            return len(text) // 4
    
    def calculate_semantic_similarity(self, text1: str, text2: str) -> float:
        """Calculate semantic similarity between two texts using TF-IDF and cosine similarity"""
        if not SKLEARN_AVAILABLE or not text1.strip() or not text2.strip():
            # Fallback to simple character-based similarity
            return self._simple_similarity(text1, text2)
        
        try:
            # Vectorize the texts
            tfidf_matrix = self.vectorizer.fit_transform([text1, text2])
            
            # Calculate cosine similarity
            similarity_matrix = cosine_similarity(tfidf_matrix[0:1], tfidf_matrix[1:2])
            return float(similarity_matrix[0][0])
        except:
            return self._simple_similarity(text1, text2)
    
    def _simple_similarity(self, text1: str, text2: str) -> float:
        """Simple character-based similarity fallback"""
        if not text1 or not text2:
            return 0.0
        
        # Simple Jaccard similarity on words
        words1 = set(text1.lower().split())
        words2 = set(text2.lower().split())
        
        if not words1 and not words2:
            return 1.0
        if not words1 or not words2:
            return 0.0
        
        intersection = words1.intersection(words2)
        union = words1.union(words2)
        
        return len(intersection) / len(union)
    
    def record_debugging_session(self, session: DebuggingSession):
        """Record a debugging session for performance analysis"""
        sessions = self._load_debug_sessions()
        sessions.append(asdict(session))
        
        with open(self.debug_sessions_file, 'w') as f:
            json.dump(sessions, f, indent=2)
    
    def record_translation_metrics(self, metrics: TranslationMetrics):
        """Record translation metrics for semantic similarity analysis"""
        translations = self._load_translation_metrics()
        translations.append(asdict(metrics))
        
        with open(self.translation_metrics_file, 'w') as f:
            json.dump(translations, f, indent=2)
    
    def record_post_write_metrics(self, metrics: PostWriteMetrics):
        """Record post-write hook performance metrics"""
        post_writes = self._load_post_write_metrics()
        post_writes.append(asdict(metrics))
        
        with open(self.post_write_metrics_file, 'w') as f:
            json.dump(post_writes, f, indent=2)
    
    def _load_debug_sessions(self) -> List[Dict]:
        """Load existing debugging sessions"""
        if self.debug_sessions_file.exists():
            try:
                with open(self.debug_sessions_file, 'r') as f:
                    return json.load(f)
            except:
                return []
        return []
    
    def _load_translation_metrics(self) -> List[Dict]:
        """Load existing translation metrics"""
        if self.translation_metrics_file.exists():
            try:
                with open(self.translation_metrics_file, 'r') as f:
                    return json.load(f)
            except:
                return []
        return []
    
    def _load_post_write_metrics(self) -> List[Dict]:
        """Load existing post-write metrics"""
        if self.post_write_metrics_file.exists():
            try:
                with open(self.post_write_metrics_file, 'r') as f:
                    return json.load(f)
            except:
                return []
        return []
    
    def create_debugging_session(self, file_path: str, compression_enabled: bool = True) -> str:
        """Create a new debugging session and return session ID"""
        session_id = hashlib.md5(f"{file_path}_{datetime.now().isoformat()}".encode()).hexdigest()[:12]
        
        # Get file info
        original_content = ""
        compressed_content = ""
        
        if Path(file_path).exists():
            with open(file_path, 'r') as f:
                original_content = f.read()
        
        # Check for compressed version if compression enabled
        if compression_enabled:
            for cache_file in self.cache_dir.glob("*.json"):
                try:
                    with open(cache_file, 'r') as f:
                        cache_data = json.load(f)
                        if cache_data.get('file_path') == str(file_path):
                            compressed_content = cache_data.get('compressed', '')
                            break
                except:
                    continue
        
        # Calculate initial metrics
        original_tokens = self.count_tokens(original_content)
        compressed_tokens = self.count_tokens(compressed_content) if compressed_content else original_tokens
        
        session = DebuggingSession(
            session_id=session_id,
            file_path=file_path,
            original_file_size=len(original_content),
            compressed_file_size=len(compressed_content) if compressed_content else len(original_content),
            original_tokens=original_tokens,
            compressed_tokens=compressed_tokens,
            bugs_found=0,
            bugs_fixed=0,
            reasoning_tokens_used=0,
            debugging_accuracy=0.0,
            time_to_debug=0.0,
            semantic_similarity_score=0.0,
            compression_enabled=compression_enabled,
            timestamp=datetime.now().isoformat(),
            claude_response_tokens=0,
            total_conversation_tokens=0
        )
        
        self.record_debugging_session(session)
        return session_id
    
    def update_debugging_session(self, session_id: str, **updates):
        """Update an existing debugging session with new metrics"""
        sessions = self._load_debug_sessions()
        
        for session_data in sessions:
            if session_data['session_id'] == session_id:
                session_data.update(updates)
                session_data['timestamp'] = datetime.now().isoformat()
                break
        
        with open(self.debug_sessions_file, 'w') as f:
            json.dump(sessions, f, indent=2)
    
    def analyze_debugging_performance(self) -> Dict[str, Any]:
        """Analyze debugging performance metrics"""
        sessions = self._load_debug_sessions()
        
        if not sessions:
            return {"error": "No debugging sessions recorded"}
        
        # Separate compressed vs uncompressed sessions
        compressed_sessions = [s for s in sessions if s['compression_enabled']]
        uncompressed_sessions = [s for s in sessions if not s['compression_enabled']]
        
        def calc_avg(sessions, key):
            return sum(s[key] for s in sessions) / len(sessions) if sessions else 0
        
        analysis = {
            'total_sessions': len(sessions),
            'compressed_sessions': len(compressed_sessions),
            'uncompressed_sessions': len(uncompressed_sessions),
            'performance_comparison': {
                'compressed': {
                    'avg_debugging_time': calc_avg(compressed_sessions, 'time_to_debug'),
                    'avg_accuracy': calc_avg(compressed_sessions, 'debugging_accuracy'),
                    'avg_reasoning_tokens': calc_avg(compressed_sessions, 'reasoning_tokens_used'),
                    'avg_total_tokens': calc_avg(compressed_sessions, 'total_conversation_tokens'),
                    'avg_token_savings': calc_avg(compressed_sessions, 'original_tokens') - calc_avg(compressed_sessions, 'compressed_tokens'),
                    'avg_semantic_similarity': calc_avg(compressed_sessions, 'semantic_similarity_score')
                },
                'uncompressed': {
                    'avg_debugging_time': calc_avg(uncompressed_sessions, 'time_to_debug'),
                    'avg_accuracy': calc_avg(uncompressed_sessions, 'debugging_accuracy'),
                    'avg_reasoning_tokens': calc_avg(uncompressed_sessions, 'reasoning_tokens_used'),
                    'avg_total_tokens': calc_avg(uncompressed_sessions, 'total_conversation_tokens'),
                    'avg_semantic_similarity': calc_avg(uncompressed_sessions, 'semantic_similarity_score')
                }
            },
            'token_efficiency': {},
            'accuracy_preservation': {},
            'last_updated': datetime.now().isoformat()
        }
        
        # Calculate efficiency metrics
        if compressed_sessions and uncompressed_sessions:
            comp_metrics = analysis['performance_comparison']['compressed']
            uncomp_metrics = analysis['performance_comparison']['uncompressed']
            
            analysis['token_efficiency'] = {
                'token_reduction_percentage': ((uncomp_metrics['avg_total_tokens'] - comp_metrics['avg_total_tokens']) / uncomp_metrics['avg_total_tokens'] * 100) if uncomp_metrics['avg_total_tokens'] > 0 else 0,
                'reasoning_efficiency_gain': ((uncomp_metrics['avg_reasoning_tokens'] - comp_metrics['avg_reasoning_tokens']) / uncomp_metrics['avg_reasoning_tokens'] * 100) if uncomp_metrics['avg_reasoning_tokens'] > 0 else 0,
                'time_efficiency_gain': ((uncomp_metrics['avg_debugging_time'] - comp_metrics['avg_debugging_time']) / uncomp_metrics['avg_debugging_time'] * 100) if uncomp_metrics['avg_debugging_time'] > 0 else 0
            }
            
            analysis['accuracy_preservation'] = {
                'accuracy_difference': comp_metrics['avg_accuracy'] - uncomp_metrics['avg_accuracy'],
                'semantic_similarity_avg': comp_metrics['avg_semantic_similarity'],
                'maintains_quality': comp_metrics['avg_accuracy'] >= uncomp_metrics['avg_accuracy'] * 0.95  # 95% threshold
            }
        
        return analysis
    
    def analyze_post_write_performance(self) -> Dict[str, Any]:
        """Analyze post-write hook performance metrics"""
        post_writes = self._load_post_write_metrics()
        
        if not post_writes:
            return {"error": "No post-write metrics recorded"}
        
        total_executions = len(post_writes)
        total_processing_time = sum(m['total_processing_time'] for m in post_writes)
        syntax_validations = sum(1 for m in post_writes if m['syntax_valid'])
        syntax_errors = sum(1 for m in post_writes if not m['syntax_valid'])
        cache_invalidations = sum(1 for m in post_writes if m['cache_invalidated'])
        total_errors = sum(len(m['errors_encountered']) for m in post_writes)
        
        # Performance metrics
        avg_total_time = total_processing_time / total_executions
        avg_syntax_time = sum(m['syntax_validation_time'] for m in post_writes) / total_executions
        avg_cache_time = sum(m['cache_invalidation_time'] for m in post_writes) / total_executions
        
        # File size analysis
        file_sizes = [m['file_size'] for m in post_writes]
        avg_file_size = sum(file_sizes) / len(file_sizes)
        max_file_size = max(file_sizes)
        min_file_size = min(file_sizes)
        
        # Recent performance (last 10 executions)
        recent_writes = post_writes[-10:] if len(post_writes) >= 10 else post_writes
        recent_avg_time = sum(m['total_processing_time'] for m in recent_writes) / len(recent_writes)
        
        # Error analysis
        all_errors = []
        for m in post_writes:
            all_errors.extend(m['errors_encountered'])
        
        error_types = {}
        for error in all_errors:
            error_type = error.split(':')[0] if ':' in error else 'Unknown'
            error_types[error_type] = error_types.get(error_type, 0) + 1
        
        analysis = {
            'execution_summary': {
                'total_executions': total_executions,
                'syntax_validations_passed': syntax_validations,
                'syntax_errors': syntax_errors,
                'cache_invalidations': cache_invalidations,
                'total_errors': total_errors,
                'success_rate': (syntax_validations / total_executions) * 100
            },
            'performance_metrics': {
                'avg_total_processing_time': avg_total_time,
                'avg_syntax_validation_time': avg_syntax_time,
                'avg_cache_invalidation_time': avg_cache_time,
                'recent_avg_processing_time': recent_avg_time,
                'performance_trend': 'improving' if recent_avg_time < avg_total_time else 'stable' if abs(recent_avg_time - avg_total_time) < 0.01 else 'degrading'
            },
            'file_analysis': {
                'avg_file_size': avg_file_size,
                'max_file_size': max_file_size,
                'min_file_size': min_file_size,
                'files_processed': list(set(m['file_path'] for m in post_writes))
            },
            'error_analysis': {
                'error_types': error_types,
                'most_common_error': max(error_types.items(), key=lambda x: x[1])[0] if error_types else None,
                'error_rate': (total_errors / total_executions) * 100
            },
            'hook_efficiency': {
                'executions_per_file': total_executions / len(set(m['file_path'] for m in post_writes)),
                'cache_invalidation_rate': (cache_invalidations / total_executions) * 100,
                'validation_overhead': avg_syntax_time / avg_total_time * 100
            },
            'last_updated': datetime.now().isoformat()
        }
        
        return analysis
    
    def validate_compression_for_file(self, file_path: str) -> Dict:
        """Validate compression for a specific file"""
        file_path = Path(file_path)
        
        # Read original file
        with open(file_path, 'r') as f:
            original_content = f.read()
        
        # Check if compressed version exists in cache
        cache_file = None
        compressed_content = None
        
        # Find cache file by file_path
        for candidate_cache in self.cache_dir.glob("*.json"):
            try:
                with open(candidate_cache, 'r') as f:
                    cache_data = json.load(f)
                    if cache_data.get('file_path') == str(file_path):
                        compressed_content = cache_data.get('compressed', '')
                        cache_file = candidate_cache
                        break
            except:
                continue
        
        # Count tokens
        original_tokens = self.count_tokens(original_content)
        compressed_tokens = self.count_tokens(compressed_content) if compressed_content else original_tokens
        
        return {
            'file_path': str(file_path),
            'original_chars': len(original_content),
            'compressed_chars': len(compressed_content) if compressed_content else 0,
            'original_tokens': original_tokens,
            'compressed_tokens': compressed_tokens,
            'char_savings': len(original_content) - (len(compressed_content) if compressed_content else 0),
            'token_savings': original_tokens - compressed_tokens,
            'char_compression_ratio': (1 - (len(compressed_content) if compressed_content else len(original_content)) / len(original_content)) * 100,
            'token_compression_ratio': (1 - compressed_tokens / original_tokens) * 100,
            'has_compressed_version': compressed_content is not None,
            'cache_file': str(cache_file) if cache_file else None
        }
    
    def collect_stats(self) -> Dict:
        """Collect compression statistics from cache"""
        stats = {
            'total_files': 0,
            'total_original_chars': 0,
            'total_compressed_chars': 0,
            'total_original_tokens': 0,
            'total_compressed_tokens': 0,
            'compression_ratios': [],
            'token_compression_ratios': [],
            'last_updated': datetime.now().isoformat()
        }
        
        for cache_file in self.cache_dir.glob("*.json"):
            try:
                with open(cache_file, 'r') as f:
                    data = json.load(f)
                
                compressed_content = data.get('compressed', '')
                file_path = data.get('file_path', '')
                
                # Read original file to compare
                if file_path and Path(file_path).exists():
                    with open(file_path, 'r') as f:
                        original_content = f.read()
                    
                    if original_content and compressed_content:
                        original_tokens = self.count_tokens(original_content)
                        compressed_tokens = self.count_tokens(compressed_content)
                        
                        stats['total_files'] += 1
                        stats['total_original_chars'] += len(original_content)
                        stats['total_compressed_chars'] += len(compressed_content)
                        stats['total_original_tokens'] += original_tokens
                        stats['total_compressed_tokens'] += compressed_tokens
                        
                        char_ratio = (1 - len(compressed_content) / len(original_content)) * 100
                        token_ratio = (1 - compressed_tokens / original_tokens) * 100
                        
                        stats['compression_ratios'].append(char_ratio)
                        stats['token_compression_ratios'].append(token_ratio)
            
            except Exception:
                pass
        
        return stats
    
    def display_stats(self):
        """Display comprehensive compression statistics"""
        stats = self.collect_stats()
        
        if stats['total_files'] == 0:
            print("No compression data available yet.")
            print("Run some Claude commands that read Python files to generate data.")
            return
        
        avg_char_ratio = sum(stats['compression_ratios']) / len(stats['compression_ratios'])
        avg_token_ratio = sum(stats['token_compression_ratios']) / len(stats['token_compression_ratios'])
        
        char_saved = stats['total_original_chars'] - stats['total_compressed_chars']
        tokens_saved = stats['total_original_tokens'] - stats['total_compressed_tokens']
        
        print("🚀 OptimizeAI Compression Validation Report")
        print("=" * 50)
        
        print(f"\n📊 OVERVIEW:")
        print(f"  Files Processed: {stats['total_files']}")
        print(f"  Last Updated: {stats['last_updated'][:19]}")
        
        print(f"\n📝 CHARACTER STATISTICS:")
        print(f"  Original: {stats['total_original_chars']:,} chars")
        print(f"  Compressed: {stats['total_compressed_chars']:,} chars")
        print(f"  Saved: {char_saved:,} chars ({char_saved/stats['total_original_chars']*100:.1f}%)")
        print(f"  Average: {avg_char_ratio:.1f}% compression")
        
        print(f"\n🎯 TOKEN STATISTICS (Actual GPT-4 Tokens):")
        print(f"  Original: {stats['total_original_tokens']:,} tokens")
        print(f"  Compressed: {stats['total_compressed_tokens']:,} tokens")
        print(f"  Saved: {tokens_saved:,} tokens ({tokens_saved/stats['total_original_tokens']*100:.1f}%)")
        print(f"  Average: {avg_token_ratio:.1f}% token compression")
        
        print(f"\n💰 COST SAVINGS ESTIMATES:")
        # Claude pricing estimates (adjust based on actual rates)
        cost_per_1k_input = 0.015  # Approximate Claude pricing
        cost_saved = tokens_saved * cost_per_1k_input / 1000
        
        print(f"  Tokens Saved: {tokens_saved:,}")
        print(f"  Estimated Cost Saved: ${cost_saved:.3f}")
        print(f"  Monthly Savings (1000 files): ${cost_saved * 1000 / stats['total_files']:.2f}")
        
        print(f"\n📈 COMPRESSION RANGES:")
        if stats['compression_ratios']:
            print(f"  Best Character Compression: {max(stats['compression_ratios']):.1f}%")
            print(f"  Worst Character Compression: {min(stats['compression_ratios']):.1f}%")
        if stats['token_compression_ratios']:
            print(f"  Best Token Compression: {max(stats['token_compression_ratios']):.1f}%")
            print(f"  Worst Token Compression: {min(stats['token_compression_ratios']):.1f}%")
    
    def display_debugging_analysis(self):
        """Display debugging performance analysis"""
        analysis = self.analyze_debugging_performance()
        
        if 'error' in analysis:
            print(f"\n❌ {analysis['error']}")
            print("Start a debugging session first using create_debugging_session()")
            return
        
        print("\n🐛 OptimizeAI Debugging Performance Analysis")
        print("=" * 60)
        
        print(f"\n📊 SESSION OVERVIEW:")
        print(f"  Total Sessions: {analysis['total_sessions']}")
        print(f"  Compressed Sessions: {analysis['compressed_sessions']}")
        print(f"  Uncompressed Sessions: {analysis['uncompressed_sessions']}")
        
        comp = analysis['performance_comparison']['compressed']
        uncomp = analysis['performance_comparison']['uncompressed']
        
        if analysis['compressed_sessions'] > 0:
            print(f"\n🚀 COMPRESSED FILE DEBUGGING:")
            print(f"  Avg Debugging Time: {comp['avg_debugging_time']:.2f}s")
            print(f"  Avg Accuracy: {comp['avg_accuracy']:.1%}")
            print(f"  Avg Reasoning Tokens: {comp['avg_reasoning_tokens']:,.0f}")
            print(f"  Avg Total Tokens: {comp['avg_total_tokens']:,.0f}")
            print(f"  Avg Token Savings: {comp['avg_token_savings']:,.0f}")
            print(f"  Avg Semantic Similarity: {comp['avg_semantic_similarity']:.3f}")
        
        if analysis['uncompressed_sessions'] > 0:
            print(f"\n📄 UNCOMPRESSED FILE DEBUGGING:")
            print(f"  Avg Debugging Time: {uncomp['avg_debugging_time']:.2f}s")
            print(f"  Avg Accuracy: {uncomp['avg_accuracy']:.1%}")
            print(f"  Avg Reasoning Tokens: {uncomp['avg_reasoning_tokens']:,.0f}")
            print(f"  Avg Total Tokens: {uncomp['avg_total_tokens']:,.0f}")
            print(f"  Avg Semantic Similarity: {uncomp['avg_semantic_similarity']:.3f}")
        
        if analysis['token_efficiency'] and analysis['compressed_sessions'] > 0 and analysis['uncompressed_sessions'] > 0:
            eff = analysis['token_efficiency']
            acc = analysis['accuracy_preservation']
            
            print(f"\n⚡ EFFICIENCY GAINS WITH COMPRESSION:")
            print(f"  Token Reduction: {eff['token_reduction_percentage']:.1f}%")
            print(f"  Reasoning Efficiency: {eff['reasoning_efficiency_gain']:.1f}%")
            print(f"  Time Efficiency: {eff['time_efficiency_gain']:.1f}%")
            
            print(f"\n🎯 ACCURACY PRESERVATION:")
            print(f"  Accuracy Difference: {acc['accuracy_difference']:+.1%}")
            print(f"  Semantic Similarity: {acc['semantic_similarity_avg']:.3f}")
            print(f"  Quality Maintained: {'✅' if acc['maintains_quality'] else '❌'}")
            
            # Cost savings calculation
            token_savings = comp['avg_token_savings']
            cost_per_1k = 0.015  # Claude pricing estimate
            cost_saved_per_session = token_savings * cost_per_1k / 1000
            
            print(f"\n💰 DEBUGGING COST SAVINGS:")
            print(f"  Tokens Saved Per Session: {token_savings:,.0f}")
            print(f"  Cost Saved Per Session: ${cost_saved_per_session:.4f}")
            print(f"  Potential Monthly Savings (100 sessions): ${cost_saved_per_session * 100:.2f}")
    
    def display_translation_metrics(self):
        """Display translation quality metrics"""
        translations = self._load_translation_metrics()
        
        if not translations:
            print("\n❌ No translation metrics recorded")
            print("Use record_translation_metrics() to track CAI to Python translations")
            return
        
        print("\n🔄 OptimizeAI Translation Quality Analysis")
        print("=" * 60)
        
        avg_similarity = sum(t['semantic_similarity'] for t in translations) / len(translations)
        syntax_correct = sum(1 for t in translations if t['syntax_correctness']) / len(translations)
        functionality_preserved = sum(1 for t in translations if t['functionality_preserved']) / len(translations)
        avg_translation_time = sum(t['translation_time'] for t in translations) / len(translations)
        
        print(f"\n📊 TRANSLATION OVERVIEW:")
        print(f"  Total Translations: {len(translations)}")
        print(f"  Avg Semantic Similarity: {avg_similarity:.3f}")
        print(f"  Syntax Correctness: {syntax_correct:.1%}")
        print(f"  Functionality Preserved: {functionality_preserved:.1%}")
        print(f"  Avg Translation Time: {avg_translation_time:.3f}s")
        
        # Quality thresholds
        high_similarity = sum(1 for t in translations if t['semantic_similarity'] >= 0.8)
        medium_similarity = sum(1 for t in translations if 0.6 <= t['semantic_similarity'] < 0.8)
        low_similarity = sum(1 for t in translations if t['semantic_similarity'] < 0.6)
        
        print(f"\n🎯 QUALITY DISTRIBUTION:")
        print(f"  High Similarity (≥0.8): {high_similarity} ({high_similarity/len(translations):.1%})")
        print(f"  Medium Similarity (0.6-0.8): {medium_similarity} ({medium_similarity/len(translations):.1%})")
        print(f"  Low Similarity (<0.6): {low_similarity} ({low_similarity/len(translations):.1%})")
        
        if avg_similarity >= 0.8:
            quality_rating = "Excellent 🟢"
        elif avg_similarity >= 0.6:
            quality_rating = "Good 🟡"
        else:
            quality_rating = "Needs Improvement 🔴"
        
        print(f"\n📈 OVERALL TRANSLATION QUALITY: {quality_rating}")
    
    def display_post_write_analysis(self):
        """Display post-write hook performance analysis"""
        analysis = self.analyze_post_write_performance()
        
        if 'error' in analysis:
            print(f"\n❌ {analysis['error']}")
            print("Post-write hook hasn't been triggered yet or no metrics recorded")
            return
        
        print("\n📝 OptimizeAI Post-Write Hook Performance Analysis")
        print("=" * 60)
        
        exec_summary = analysis['execution_summary']
        perf_metrics = analysis['performance_metrics']
        file_analysis = analysis['file_analysis']
        error_analysis = analysis['error_analysis']
        efficiency = analysis['hook_efficiency']
        
        print(f"\n📊 EXECUTION SUMMARY:")
        print(f"  Total Hook Executions: {exec_summary['total_executions']}")
        print(f"  Syntax Validations Passed: {exec_summary['syntax_validations_passed']}")
        print(f"  Syntax Errors Detected: {exec_summary['syntax_errors']}")
        print(f"  Cache Invalidations: {exec_summary['cache_invalidations']}")
        print(f"  Success Rate: {exec_summary['success_rate']:.1f}%")
        
        print(f"\n⚡ PERFORMANCE METRICS:")
        print(f"  Avg Total Processing Time: {perf_metrics['avg_total_processing_time']:.4f}s")
        print(f"  Avg Syntax Validation Time: {perf_metrics['avg_syntax_validation_time']:.4f}s")
        print(f"  Avg Cache Invalidation Time: {perf_metrics['avg_cache_invalidation_time']:.4f}s")
        print(f"  Recent Performance Trend: {perf_metrics['performance_trend'].title()}")
        print(f"  Recent Avg Time: {perf_metrics['recent_avg_processing_time']:.4f}s")
        
        print(f"\n📄 FILE ANALYSIS:")
        print(f"  Files Processed: {len(file_analysis['files_processed'])}")
        print(f"  Avg File Size: {file_analysis['avg_file_size']:,.0f} chars")
        print(f"  Largest File: {file_analysis['max_file_size']:,.0f} chars")
        print(f"  Smallest File: {file_analysis['min_file_size']:,.0f} chars")
        
        print(f"\n🔧 HOOK EFFICIENCY:")
        print(f"  Executions Per File: {efficiency['executions_per_file']:.1f}")
        print(f"  Cache Invalidation Rate: {efficiency['cache_invalidation_rate']:.1f}%")
        print(f"  Validation Overhead: {efficiency['validation_overhead']:.1f}%")
        
        if error_analysis['error_types']:
            print(f"\n⚠️  ERROR ANALYSIS:")
            print(f"  Total Errors: {exec_summary['total_errors']}")
            print(f"  Error Rate: {error_analysis['error_rate']:.1f}%")
            print(f"  Most Common Error: {error_analysis['most_common_error']}")
            
            print(f"\n  Error Types:")
            for error_type, count in sorted(error_analysis['error_types'].items(), key=lambda x: x[1], reverse=True):
                print(f"    {error_type}: {count}")
        else:
            print(f"\n✅ ERROR ANALYSIS: No errors recorded")
        
        # Performance recommendations
        print(f"\n💡 RECOMMENDATIONS:")
        
        if perf_metrics['avg_total_processing_time'] > 0.1:
            print("  • Consider optimizing syntax validation for large files")
        
        if efficiency['validation_overhead'] > 50:
            print("  • Syntax validation taking significant time - consider async processing")
        
        if error_analysis['error_rate'] > 5:
            print("  • High error rate detected - review file processing logic")
        
        if efficiency['executions_per_file'] > 3:
            print("  • Multiple hook executions per file - investigate duplicate triggers")
        
        if perf_metrics['performance_trend'] == 'degrading':
            print("  • Performance degrading over time - investigate resource usage")
        else:
            print("  • Post-write hook performance is healthy")
        
        # File processing efficiency
        files_processed = len(file_analysis['files_processed'])
        processing_rate = exec_summary['total_executions'] / files_processed if files_processed > 0 else 0
        avg_time_per_char = perf_metrics['avg_total_processing_time'] / file_analysis['avg_file_size'] if file_analysis['avg_file_size'] > 0 else 0
        
        print(f"\n📈 PROCESSING EFFICIENCY:")
        print(f"  Processing Rate: {processing_rate:.1f} executions/file")
        print(f"  Time Per Character: {avg_time_per_char * 1000:.4f}ms/char")
        print(f"  Estimated Throughput: {1/perf_metrics['avg_total_processing_time']:.1f} files/second")
    
    def validate_specific_file(self, file_path: str):
        """Validate compression for a specific file"""
        result = self.validate_compression_for_file(file_path)
        
        print(f"\n🔍 File Validation: {result['file_path']}")
        print("=" * 60)
        
        if not result['has_compressed_version']:
            print("❌ No compressed version found in cache")
            print("   Run Claude with this file first to generate compressed version")
            return
        
        print(f"✅ Compressed version found")
        print(f"\n📝 CHARACTER ANALYSIS:")
        print(f"  Original: {result['original_chars']:,} chars")
        print(f"  Compressed: {result['compressed_chars']:,} chars")
        print(f"  Saved: {result['char_savings']:,} chars ({result['char_compression_ratio']:.1f}%)")
        
        print(f"\n🎯 TOKEN ANALYSIS:")
        print(f"  Original: {result['original_tokens']:,} tokens")
        print(f"  Compressed: {result['compressed_tokens']:,} tokens")
        print(f"  Saved: {result['token_savings']:,} tokens ({result['token_compression_ratio']:.1f}%)")
        
        cost_saved = result['token_savings'] * 0.015 / 1000
        print(f"\n💰 COST IMPACT:")
        print(f"  Cost Saved Per Read: ${cost_saved:.4f}")

if __name__ == "__main__":
    import sys
    monitor = CompressionMonitor()
    
    if len(sys.argv) > 1:
        command = sys.argv[1].lower()
        
        if command == "debug":
            # Show debugging performance analysis
            monitor.display_debugging_analysis()
        elif command == "translate":
            # Show translation quality metrics
            monitor.display_translation_metrics()
        elif command == "postwrite":
            # Show post-write hook performance metrics
            monitor.display_post_write_analysis()
        elif command == "all":
            # Show all metrics
            monitor.display_stats()
            monitor.display_debugging_analysis()
            monitor.display_translation_metrics()
            monitor.display_post_write_analysis()
        elif command.startswith("session"):
            # Create or manage debugging session
            if len(sys.argv) > 2:
                file_path = sys.argv[2]
                compression = sys.argv[3].lower() == "true" if len(sys.argv) > 3 else True
                session_id = monitor.create_debugging_session(file_path, compression)
                print(f"Created debugging session: {session_id}")
            else:
                print("Usage: python monitor.py session <file_path> [true/false for compression]")
        else:
            # Validate specific file
            monitor.validate_specific_file(sys.argv[1])
    else:
        # Show overall compression stats by default
        monitor.display_stats()
        
        # Also show debugging and translation stats if available
        print("\n" + "="*60)
        print("DEBUGGING & TRANSLATION METRICS")
        print("="*60)
        print("Use 'python monitor.py debug' for debugging analysis")
        print("Use 'python monitor.py translate' for translation metrics")
        print("Use 'python monitor.py postwrite' for post-write hook performance")
        print("Use 'python monitor.py all' for comprehensive report")
        print("Use 'python monitor.py session <file_path>' to start debugging session")