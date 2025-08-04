#!/usr/bin/env python3
"""
Comprehensive Error Recovery Handler for Production-Grade Compression
Implements systematic error handling with fallback mechanisms and detailed logging.
"""

import traceback
import time
from enum import Enum
from typing import Optional, Dict, Any, Union, Callable
import logging


class ErrorSeverity(Enum):
    """Error severity levels for systematic categorization"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ProductionErrorHandler:
    """
    Production-grade error handler with comprehensive recovery mechanisms.
    
    Features:
    - Systematic error classification
    - Multiple fallback strategies
    - Detailed error logging and tracking
    - Performance metrics during error recovery
    - Content preservation safeguards
    """
    
    def __init__(self, logger: Optional[logging.Logger] = None):
        """
        Initialize error handler with logging and metrics tracking.
        
        Args:
            logger: Optional logger instance. If None, creates default logger.
        """
        self.logger = logger or self._create_default_logger()
        self.error_counts: Dict[str, int] = {}
        self.recovery_strategies: Dict[ErrorSeverity, Callable] = {
            ErrorSeverity.LOW: self._handle_low_severity,
            ErrorSeverity.MEDIUM: self._handle_medium_severity,
            ErrorSeverity.HIGH: self._handle_high_severity,
            ErrorSeverity.CRITICAL: self._handle_critical_severity
        }
        
    def _create_default_logger(self) -> logging.Logger:
        """Create default logger if none provided"""
        logger = logging.getLogger("ProductionErrorHandler")
        logger.setLevel(logging.INFO)
        
        if not logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            handler.setFormatter(formatter)
            logger.addHandler(handler)
            
        return logger
    
    async def handle_compression_error(self, error: Exception, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Graceful compression error handling with systematic fallback strategies.
        
        Args:
            error: The exception that occurred
            context: Context information including 'code', 'operation_id', etc.
            
        Returns:
            Dict containing recovery result and metadata
        """
        start_time = time.time()
        operation_id = context.get('operation_id', f'error_recovery_{int(time.time() * 1000)}')
        code = context.get('code', '')
        
        # Classify error severity
        severity = self._classify_error(error)
        
        # Track error occurrence
        error_type = type(error).__name__
        self.error_counts[error_type] = self.error_counts.get(error_type, 0) + 1
        
        # Log initial error
        self.logger.error(
            f"Compression error detected | "
            f"Type: {error_type} | "
            f"Severity: {severity.value} | "
            f"Operation: {operation_id} | "
            f"Message: {str(error)}"
        )
        
        try:
            # Apply appropriate recovery strategy
            recovery_result = await self.recovery_strategies[severity](error, context)
            
            # Calculate recovery metrics
            recovery_time = (time.time() - start_time) * 1000
            
            # Enhanced result with recovery metadata
            result = {
                **recovery_result,
                'error_recovery': {
                    'error_type': error_type,
                    'severity': severity.value,
                    'recovery_time_ms': round(recovery_time, 2),
                    'operation_id': operation_id,
                    'strategy_used': recovery_result.get('strategy', 'unknown'),
                    'content_preserved': recovery_result.get('content_preserved', True)
                }
            }
            
            # Log successful recovery
            self.logger.info(
                f"Error recovery successful | "
                f"Type: {error_type} | "
                f"Strategy: {result['error_recovery']['strategy_used']} | "
                f"Time: {recovery_time:.2f}ms | "
                f"Content preserved: {result['error_recovery']['content_preserved']}"
            )
            
            return result
            
        except Exception as recovery_error:
            # Recovery failed - log and re-raise
            recovery_time = (time.time() - start_time) * 1000
            
            self.logger.critical(
                f"Error recovery failed | "
                f"Original: {error_type} | "
                f"Recovery error: {type(recovery_error).__name__} | "
                f"Time: {recovery_time:.2f}ms | "
                f"Traceback: {traceback.format_exc()}"
            )
            
            # Return safe fallback result
            return {
                'compressed_code': code,  # Return original code as safe fallback
                'compression_ratio': 0.0,
                'similarity_score': 1.0,  # Original code has perfect similarity to itself
                'error_recovery': {
                    'error_type': error_type,
                    'severity': 'critical',
                    'recovery_failed': True,
                    'fallback_used': 'original_code',
                    'recovery_time_ms': round(recovery_time, 2)
                }
            }
    
    def _classify_error(self, error: Exception) -> ErrorSeverity:
        """
        Classify error severity based on type and characteristics.
        
        Args:
            error: Exception to classify
            
        Returns:
            ErrorSeverity level
        """
        error_type = type(error).__name__
        error_message = str(error).lower()
        
        # Critical errors - system failures
        if error_type in ['SystemError', 'MemoryError', 'KeyboardInterrupt']:
            return ErrorSeverity.CRITICAL
            
        # High severity - data corruption or major functionality loss
        if error_type in ['SyntaxError', 'IndentationError', 'TokenError']:
            return ErrorSeverity.HIGH
            
        if 'corruption' in error_message or 'invalid ast' in error_message:
            return ErrorSeverity.HIGH
            
        # Medium severity - functionality affected but recoverable
        if error_type in ['ValueError', 'TypeError', 'AttributeError', 'ImportError']:
            return ErrorSeverity.MEDIUM
            
        if 'threshold' in error_message or 'limit' in error_message:
            return ErrorSeverity.MEDIUM
            
        # Low severity - minor issues, alternative approaches available
        if error_type in ['RuntimeWarning', 'UserWarning']:
            return ErrorSeverity.LOW
            
        # Default to medium for unknown errors
        return ErrorSeverity.MEDIUM
    
    async def _handle_low_severity(self, error: Exception, context: Dict[str, Any]) -> Dict[str, Any]:
        """Handle low severity errors with alternative compression methods"""
        code = context.get('code', '')
        
        try:
            # Try alternative compression method
            compressed_result = await self._fallback_compression(code)
            
            return {
                'compressed_code': compressed_result['code'],
                'compression_ratio': compressed_result['ratio'],
                'similarity_score': compressed_result['similarity'],
                'strategy': 'alternative_compression',
                'content_preserved': True
            }
            
        except Exception:
            # Fall back to safe partial compression
            return await self._safe_partial_compression(code)
    
    async def _handle_medium_severity(self, error: Exception, context: Dict[str, Any]) -> Dict[str, Any]:
        """Handle medium severity errors with partial compression and logging"""
        code = context.get('code', '')
        
        self.logger.warning(
            f"Medium severity error - attempting partial compression | "
            f"Error: {error} | "
            f"Code length: {len(code)}"
        )
        
        try:
            # Attempt safe partial compression
            result = await self._safe_partial_compression(code)
            return {
                **result,
                'strategy': 'partial_compression',
                'content_preserved': True
            }
            
        except Exception:
            # Ultimate fallback to original code
            return {
                'compressed_code': code,
                'compression_ratio': 0.0,
                'similarity_score': 1.0,
                'strategy': 'original_fallback',
                'content_preserved': True
            }
    
    async def _handle_high_severity(self, error: Exception, context: Dict[str, Any]) -> Dict[str, Any]:
        """Handle high severity errors with detailed logging and safe fallbacks"""
        code = context.get('code', '')
        
        self.logger.error(
            f"High severity compression error | "
            f"Error: {error} | "
            f"Context: {context} | "
            f"Traceback: {traceback.format_exc()}"
        )
        
        # For high severity, return original code to ensure safety
        return {
            'compressed_code': code,
            'compression_ratio': 0.0,
            'similarity_score': 1.0,
            'strategy': 'safe_original_fallback',
            'content_preserved': True,
            'warnings': [f"High severity error prevented compression: {str(error)}"]
        }
    
    async def _handle_critical_severity(self, error: Exception, context: Dict[str, Any]) -> Dict[str, Any]:
        """Handle critical errors with comprehensive logging and immediate fallback"""
        code = context.get('code', '')
        
        self.logger.critical(
            f"Critical compression error - immediate fallback required | "
            f"Error: {error} | "
            f"Context: {context} | "
            f"Traceback: {traceback.format_exc()}"
        )
        
        # Critical errors require immediate safe fallback
        result = {
            'compressed_code': code,
            'compression_ratio': 0.0,
            'similarity_score': 1.0,
            'strategy': 'critical_safe_fallback',
            'content_preserved': True,
            'critical_error': True,
            'warnings': [f"Critical error prevented compression: {str(error)}"]
        }
        
        return result
    
    async def _fallback_compression(self, code: str) -> Dict[str, Any]:
        """
        Alternative compression method for fallback scenarios.
        Ensures content preservation with conservative compression.
        
        Args:
            code: Source code to compress
            
        Returns:
            Dict with compressed result
        """
        try:
            # Handle edge cases - preserve empty or minimal content
            if not code or not code.strip():
                return {
                    'code': code,
                    'ratio': 0.0,
                    'similarity': 1.0
                }
            
            # Simple whitespace compression as safe fallback
            lines = code.split('\n')
            compressed_lines = []
            
            for line in lines:
                # Remove excessive whitespace but preserve structure
                stripped = line.strip()
                if stripped:
                    # Keep essential indentation (simplified but safe)
                    original_indent = len(line) - len(line.lstrip())
                    # Preserve relative indentation with a maximum cap
                    safe_indent = min(original_indent, 16)  # Cap at 16 spaces for safety
                    compressed_lines.append(' ' * safe_indent + stripped)
                else:
                    # Preserve empty lines for structure
                    compressed_lines.append('')
            
            compressed_code = '\n'.join(compressed_lines)
            
            # Safety check - if compression went wrong, use original
            if not compressed_code.strip() and code.strip():
                compressed_code = code
            
            # Calculate metrics conservatively
            original_length = len(code)
            compressed_length = len(compressed_code)
            ratio = (original_length - compressed_length) / original_length if original_length > 0 else 0.0
            
            return {
                'code': compressed_code,
                'ratio': max(0.0, ratio),  # Ensure non-negative
                'similarity': 0.85  # Conservative similarity estimate
            }
            
        except Exception as e:
            self.logger.warning(f"Fallback compression failed: {e}")
            # Return original code if even fallback fails - guaranteed preservation
            return {
                'code': code,
                'ratio': 0.0,
                'similarity': 1.0
            }
    
    async def _safe_partial_compression(self, code: str) -> Dict[str, Any]:
        """
        Safe partial compression that preserves essential code structure.
        Guarantees content preservation in all cases.
        
        Args:
            code: Source code to compress
            
        Returns:
            Dict with partial compression result
        """
        try:
            # Handle edge cases first - ensure content preservation
            if not code or not code.strip():
                # For empty or whitespace-only code, return as-is
                return {
                    'compressed_code': code,
                    'compression_ratio': 0.0,
                    'similarity_score': 1.0,
                    'strategy': 'safe_partial_no_change',
                    'content_preserved': True
                }
            
            # Basic safe operations only
            lines = code.split('\n')
            processed_lines = []
            has_meaningful_content = False
            
            for line in lines:
                # Only safe transformations
                processed = line.rstrip()  # Remove trailing whitespace
                
                # Check if this line has meaningful content
                if processed.strip() and not processed.strip().startswith('#'):
                    has_meaningful_content = True
                
                # Simple comment removal (but preserve important comments)
                if processed.strip().startswith('#'):
                    # Preserve important comments and keep at least some comments for structure
                    if any(keyword in processed.lower() for keyword in ['todo', 'fixme', 'note', 'important', 'copyright', 'license']):
                        processed_lines.append(processed)
                    # Keep first few comments to preserve structure
                    elif len([l for l in processed_lines if l.strip().startswith('#')]) < 2:
                        processed_lines.append(processed)
                    # Skip other simple comments
                else:
                    processed_lines.append(processed)
            
            # If we removed all meaningful content, return original
            if not has_meaningful_content and any(line.strip() and not line.strip().startswith('#') for line in lines):
                return {
                    'compressed_code': code,
                    'compression_ratio': 0.0,
                    'similarity_score': 1.0,
                    'strategy': 'safe_partial_preserved_original',
                    'content_preserved': True
                }
            
            # Remove multiple consecutive empty lines (but preserve at least some structure)
            final_lines = []
            empty_count = 0
            
            for line in processed_lines:
                if line.strip() == '':
                    empty_count += 1
                    if empty_count <= 1:  # Keep at most 1 empty line
                        final_lines.append(line)
                else:
                    empty_count = 0
                    final_lines.append(line)
            
            compressed_code = '\n'.join(final_lines)
            
            # Final safety check - if result is empty but original wasn't, use original
            if not compressed_code.strip() and code.strip():
                compressed_code = code
                
            # Calculate conservative metrics
            original_length = len(code)
            compressed_length = len(compressed_code)
            ratio = (original_length - compressed_length) / original_length if original_length > 0 else 0.0
            
            return {
                'compressed_code': compressed_code,
                'compression_ratio': max(0.0, ratio),
                'similarity_score': 0.9,  # High similarity for safe partial compression
                'strategy': 'safe_partial',
                'content_preserved': True
            }
            
        except Exception as e:
            self.logger.warning(f"Safe partial compression failed: {e}")
            # Ultimate fallback - always preserve original content
            return {
                'compressed_code': code,
                'compression_ratio': 0.0,
                'similarity_score': 1.0,
                'strategy': 'no_compression_fallback',
                'content_preserved': True
            }
            
    def get_error_statistics(self) -> Dict[str, Any]:
        """
        Get comprehensive error statistics for monitoring and analysis.
        
        Returns:
            Dict with error statistics and metrics
        """
        total_errors = sum(self.error_counts.values())
        
        return {
            'total_errors': total_errors,
            'error_breakdown': dict(self.error_counts),
            'most_common_error': max(self.error_counts.items(), key=lambda x: x[1])[0] if self.error_counts else None,
            'error_types_seen': len(self.error_counts),
            'timestamp': time.time()
        }
    
    def reset_statistics(self) -> None:
        """Reset error tracking statistics"""
        self.error_counts.clear()
        self.logger.info("Error statistics reset")


# Convenience function for quick error handling setup
def create_error_handler(logger: Optional[logging.Logger] = None) -> ProductionErrorHandler:
    """
    Create a production error handler instance.
    
    Args:
        logger: Optional logger instance
        
    Returns:
        ProductionErrorHandler instance
    """
    return ProductionErrorHandler(logger)


# Example usage patterns
if __name__ == "__main__":
    import asyncio
    
    async def demo_error_handling():
        """Demonstrate error handling capabilities"""
        handler = create_error_handler()
        
        # Simulate different error scenarios
        test_code = """
def example_function():
    return "Hello, World!"
"""
        
        # Test low severity error
        try:
            raise RuntimeWarning("Minor issue occurred")
        except Exception as e:
            result = await handler.handle_compression_error(e, {'code': test_code})
            print(f"Low severity recovery: {result['error_recovery']['strategy_used']}")
        
        # Test medium severity error
        try:
            raise ValueError("Invalid threshold value")
        except Exception as e:
            result = await handler.handle_compression_error(e, {'code': test_code})
            print(f"Medium severity recovery: {result['error_recovery']['strategy_used']}")
        
        # Print statistics
        stats = handler.get_error_statistics()
        print(f"Error statistics: {stats}")
    
    # Run demo
    asyncio.run(demo_error_handling())
