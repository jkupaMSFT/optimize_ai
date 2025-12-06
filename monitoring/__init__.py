"""
OptimizeAI Monitoring Module

Provides production monitoring capabilities including:
- Prometheus metrics collection
- Performance dashboard
- Health status monitoring
- Real-time compression analytics
"""

from .dashboard import (
    MonitoringDashboard, 
    get_dashboard, 
    dashboard,
    compression_counter,
    compression_duration,
    active_sessions,
    error_counter,
    compression_ratio_gauge
)

__all__ = [
    'MonitoringDashboard',
    'get_dashboard', 
    'dashboard',
    'compression_counter',
    'compression_duration',
    'active_sessions',
    'error_counter',
    'compression_ratio_gauge'
]
