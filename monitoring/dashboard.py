#!/usr/bin/env python3
"""
Production Monitoring Dashboard for OptimizeAI

Provides comprehensive monitoring capabilities including:
- Prometheus metrics collection
- Real-time performance tracking
- Health status monitoring
- Compression analytics and reporting
"""

import time
import logging
from typing import Dict, Any, Optional, List
from collections import defaultdict, deque
from datetime import datetime, timedelta

try:
    from prometheus_client import Counter, Histogram, Gauge, CollectorRegistry, generate_latest
    PROMETHEUS_AVAILABLE = True
except ImportError:
    # Fallback when prometheus_client is not available
    PROMETHEUS_AVAILABLE = False
    
    class Counter:
        def __init__(self, *args, **kwargs):
            self._value = defaultdict(int)
        def labels(self, **kwargs):
            return self
        def inc(self, amount=1):
            self._value['default'] += amount
            
    class Histogram:
        def __init__(self, *args, **kwargs):
            self._observations = []
        def observe(self, value):
            self._observations.append(value)
            
    class Gauge:
        def __init__(self, *args, **kwargs):
            self._value = defaultdict(float)
        def set(self, value):
            self._value['default'] = value
        def inc(self, amount=1):
            self._value['default'] += amount
        def dec(self, amount=1):
            self._value['default'] -= amount


# Initialize metrics
if PROMETHEUS_AVAILABLE:
    # Production metrics with Prometheus
    compression_counter = Counter('optimizeai_compressions_total', 
                                'Total compressions', ['agent', 'tier'])
    compression_duration = Histogram('optimizeai_compression_duration_seconds',
                                   'Compression duration')
    active_sessions = Gauge('optimizeai_active_sessions', 
                           'Currently active sessions')
    error_counter = Counter('optimizeai_errors_total',
                          'Total errors', ['error_type', 'severity'])
    compression_ratio_gauge = Gauge('optimizeai_compression_ratio',
                                  'Current compression ratio')
else:
    # Fallback metrics without Prometheus
    compression_counter = Counter('optimizeai_compressions_total', 
                                'Total compressions', ['agent', 'tier'])
    compression_duration = Histogram('optimizeai_compression_duration_seconds',
                                   'Compression duration')
    active_sessions = Gauge('optimizeai_active_sessions', 
                           'Currently active sessions')
    error_counter = Counter('optimizeai_errors_total',
                          'Total errors', ['error_type', 'severity'])
    compression_ratio_gauge = Gauge('optimizeai_compression_ratio',
                                  'Current compression ratio')


class MonitoringDashboard:
    """
    Production monitoring dashboard with comprehensive metrics tracking.
    
    Features:
    - Real-time compression metrics
    - Performance monitoring
    - Error tracking and alerting
    - Health status reporting
    - Historical data analysis
    """
    
    def __init__(self, logger: Optional[logging.Logger] = None):
        """
        Initialize monitoring dashboard.
        
        Args:
            logger: Optional logger instance for monitoring operations
        """
        self.logger = logger or self._create_default_logger()
        self.metrics = {}
        self.start_time = time.time()
        
        # In-memory storage for metrics (fallback when Prometheus unavailable)
        self.compression_history = deque(maxlen=1000)  # Last 1000 compressions
        self.error_history = deque(maxlen=500)  # Last 500 errors
        self.session_data = {}
        
        # Performance tracking
        self.performance_window = deque(maxlen=100)  # Last 100 operations
        
        self.logger.info("MonitoringDashboard initialized successfully")
        
    def _create_default_logger(self) -> logging.Logger:
        """Create default logger for monitoring operations"""
        logger = logging.getLogger('optimizeai.monitoring')
        if not logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            handler.setFormatter(formatter)
            logger.addHandler(handler)
            logger.setLevel(logging.INFO)
        return logger
        
    def track_compression(self, agent: str, tier: str, duration: float, 
                         original_size: int = 0, compressed_size: int = 0):
        """
        Track compression operation metrics.
        
        Args:
            agent: AI agent used for compression
            tier: Compression tier applied
            duration: Time taken for compression in seconds
            original_size: Original content size in characters
            compressed_size: Compressed content size in characters
        """
        try:
            # Update Prometheus metrics
            compression_counter.labels(agent=agent, tier=tier).inc()
            compression_duration.observe(duration)
            
            # Calculate compression ratio
            ratio = 0.0
            if original_size > 0:
                ratio = compressed_size / original_size
                compression_ratio_gauge.set(ratio)
            
            # Store in local history for analytics
            compression_record = {
                'timestamp': datetime.now(),
                'agent': agent,
                'tier': tier,
                'duration': duration,
                'original_size': original_size,
                'compressed_size': compressed_size,
                'ratio': ratio
            }
            self.compression_history.append(compression_record)
            self.performance_window.append(duration)
            
            self.logger.info(
                f"Compression tracked: {agent}/{tier}, "
                f"duration={duration:.3f}s, ratio={ratio:.3f}"
            )
            
        except Exception as e:
            self.logger.error(f"Error tracking compression: {e}")
            
    def track_error(self, error_type: str, severity: str, details: Optional[Dict] = None):
        """
        Track error occurrences for monitoring.
        
        Args:
            error_type: Type of error encountered
            severity: Severity level of the error
            details: Additional error details
        """
        try:
            error_counter.labels(error_type=error_type, severity=severity).inc()
            
            error_record = {
                'timestamp': datetime.now(),
                'error_type': error_type,
                'severity': severity,
                'details': details or {}
            }
            self.error_history.append(error_record)
            
            self.logger.warning(
                f"Error tracked: {error_type} ({severity})"
            )
            
        except Exception as e:
            self.logger.error(f"Error tracking error: {e}")
            
    def update_active_sessions(self, count: int):
        """Update the count of active sessions"""
        try:
            active_sessions.set(count)
            self.logger.debug(f"Active sessions updated: {count}")
        except Exception as e:
            self.logger.error(f"Error updating active sessions: {e}")
            
    def get_health_status(self) -> Dict[str, Any]:
        """
        Get comprehensive health status of the system.
        
        Returns:
            Dictionary containing health metrics and status
        """
        try:
            uptime = time.time() - self.start_time
            
            health_data = {
                "status": "healthy",
                "uptime_seconds": uptime,
                "compressions_per_minute": self._calculate_cpm(),
                "average_compression_ratio": self._get_avg_ratio(),
                "error_rate": self._get_error_rate(),
                "active_sessions": self._get_active_sessions_count(),
                "average_compression_time": self._get_avg_compression_time(),
                "system_performance": self._get_performance_metrics(),
                "last_updated": datetime.now().isoformat()
            }
            
            # Determine overall health status
            if health_data["error_rate"] > 0.1:  # More than 10% error rate
                health_data["status"] = "degraded"
            elif health_data["error_rate"] > 0.05:  # More than 5% error rate
                health_data["status"] = "warning"
                
            return health_data
            
        except Exception as e:
            self.logger.error(f"Error getting health status: {e}")
            return {
                "status": "error",
                "error": str(e),
                "last_updated": datetime.now().isoformat()
            }
            
    def get_compression_analytics(self, hours: int = 24) -> Dict[str, Any]:
        """
        Get detailed compression analytics for the specified time period.
        
        Args:
            hours: Number of hours to analyze (default: 24)
            
        Returns:
            Dictionary containing compression analytics
        """
        try:
            cutoff_time = datetime.now() - timedelta(hours=hours)
            recent_compressions = [
                c for c in self.compression_history 
                if c['timestamp'] > cutoff_time
            ]
            
            if not recent_compressions:
                return {"message": "No compression data available for the specified period"}
                
            # Calculate analytics
            total_compressions = len(recent_compressions)
            avg_duration = sum(c['duration'] for c in recent_compressions) / total_compressions
            avg_ratio = sum(c['ratio'] for c in recent_compressions if c['ratio'] > 0) / max(1, len([c for c in recent_compressions if c['ratio'] > 0]))
            
            # Agent breakdown
            agent_stats = defaultdict(int)
            tier_stats = defaultdict(int)
            
            for compression in recent_compressions:
                agent_stats[compression['agent']] += 1
                tier_stats[compression['tier']] += 1
                
            return {
                "period_hours": hours,
                "total_compressions": total_compressions,
                "average_duration": avg_duration,
                "average_compression_ratio": avg_ratio,
                "compressions_per_hour": total_compressions / hours,
                "agent_breakdown": dict(agent_stats),
                "tier_breakdown": dict(tier_stats),
                "performance_trend": self._calculate_performance_trend(recent_compressions)
            }
            
        except Exception as e:
            self.logger.error(f"Error getting compression analytics: {e}")
            return {"error": str(e)}
            
    def export_metrics(self) -> str:
        """
        Export metrics in Prometheus format.
        
        Returns:
            Prometheus-formatted metrics string
        """
        try:
            if PROMETHEUS_AVAILABLE:
                metrics_bytes = generate_latest()
                # Convert bytes to string if needed
                if isinstance(metrics_bytes, bytes):
                    return metrics_bytes.decode('utf-8')
                return metrics_bytes
            else:
                # Fallback: return basic metrics as text
                metrics_text = f"""
# OptimizeAI Metrics (Fallback Format)
# HELP optimizeai_compressions_total Total compressions
# TYPE optimizeai_compressions_total counter
optimizeai_compressions_total {len(self.compression_history)}

# HELP optimizeai_active_sessions Currently active sessions
# TYPE optimizeai_active_sessions gauge
optimizeai_active_sessions {self._get_active_sessions_count()}

# HELP optimizeai_errors_total Total errors
# TYPE optimizeai_errors_total counter
optimizeai_errors_total {len(self.error_history)}
"""
                return metrics_text.strip()
                
        except Exception as e:
            self.logger.error(f"Error exporting metrics: {e}")
            return f"# Error exporting metrics: {e}"
            
    def _calculate_cpm(self) -> float:
        """Calculate compressions per minute based on recent activity"""
        if not self.compression_history:
            return 0.0
            
        # Calculate based on last hour of data
        one_hour_ago = datetime.now() - timedelta(hours=1)
        recent_compressions = [
            c for c in self.compression_history 
            if c['timestamp'] > one_hour_ago
        ]
        
        return len(recent_compressions) / 60.0  # Convert to per-minute
        
    def _get_avg_ratio(self) -> float:
        """Calculate average compression ratio from recent history"""
        if not self.compression_history:
            return 0.0
            
        ratios = [c['ratio'] for c in self.compression_history if c['ratio'] > 0]
        if not ratios:
            return 0.0
            
        return sum(ratios) / len(ratios)
        
    def _get_error_rate(self) -> float:
        """Calculate error rate based on recent activity"""
        total_operations = len(self.compression_history) + len(self.error_history)
        if total_operations == 0:
            return 0.0
            
        return len(self.error_history) / total_operations
        
    def _get_active_sessions_count(self) -> int:
        """Get current count of active sessions"""
        try:
            if PROMETHEUS_AVAILABLE:
                return int(active_sessions._value.get())
            else:
                return len(self.session_data)
        except:
            return 0
            
    def _get_avg_compression_time(self) -> float:
        """Calculate average compression time from recent performance data"""
        if not self.performance_window:
            return 0.0
            
        return sum(self.performance_window) / len(self.performance_window)
        
    def _get_performance_metrics(self) -> Dict[str, Any]:
        """Get detailed performance metrics"""
        if not self.performance_window:
            return {}
            
        durations = list(self.performance_window)
        durations.sort()
        
        # Calculate proper median for even/odd number of elements
        n = len(durations)
        if n % 2 == 0:
            median = (durations[n // 2 - 1] + durations[n // 2]) / 2
        else:
            median = durations[n // 2]
        
        return {
            "min_duration": min(durations),
            "max_duration": max(durations),
            "median_duration": median,
            "p95_duration": durations[int(len(durations) * 0.95)],
            "p99_duration": durations[int(len(durations) * 0.99)]
        }
        
    def _calculate_performance_trend(self, compressions: List[Dict]) -> str:
        """Calculate performance trend over time"""
        if len(compressions) < 10:
            return "insufficient_data"
            
        # Sort by timestamp
        compressions.sort(key=lambda x: x['timestamp'])
        
        # Split into first and second half
        mid_point = len(compressions) // 2
        first_half_avg = sum(c['duration'] for c in compressions[:mid_point]) / mid_point
        second_half_avg = sum(c['duration'] for c in compressions[mid_point:]) / (len(compressions) - mid_point)
        
        # Determine trend
        if second_half_avg < first_half_avg * 0.95:
            return "improving"
        elif second_half_avg > first_half_avg * 1.05:
            return "degrading"
        else:
            return "stable"


# Global dashboard instance for easy access
dashboard = MonitoringDashboard()


def get_dashboard() -> MonitoringDashboard:
    """Get the global dashboard instance"""
    return dashboard
