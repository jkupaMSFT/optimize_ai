# Waterfall tier thresholds - making values constant for maintainability
BASIC_THRESHOLD = 1000
STANDARD_THRESHOLD = 5000
AGGRESSIVE_THRESHOLD = 10000

# Performance monitoring constants
LATENCY_WARNING_THRESHOLD = 200  # ms
LARGE_PAYLOAD_THRESHOLD = 10000  # chars

# OTPM (One Token Per Message) threshold for token limit protection
OTPM_THRESHOLD = 8000

# Configurable thresholds
MAX_IMPORTS = 10
MAX_METHODS = 5
MAX_FUNCTIONS = 8
COMPRESSION_RATIO = 0.7
MAX_STATEMENT_LENGTH = 100

from utils.compression import CompressionType
from utils.logger import MinifierLogger, estimate_tokens
from .mapping.source_map import MappedNode, SourceMap
from typing import Dict, Tuple, Union, Optional, Any, Callable
from functools import lru_cache, wraps
from dataclasses import dataclass, asdict, field
from enum import Enum
import time
import ast
import warnings
import json
import os

# Tier adjustment mappings as module constants for easier configuration
COMPRESSION_TIER_DOWNGRADES = {
    CompressionType.SUMMARIZE: (CompressionType.AGGRESSIVE, "Downgraded from SUMMARIZE (abundant resources)"),
    CompressionType.AGGRESSIVE: (CompressionType.STANDARD, "Downgraded to STANDARD (abundant resources)"),
    CompressionType.STANDARD: (CompressionType.BASIC, "Downgraded to BASIC (abundant resources)")
}

COMPRESSION_TIER_UPGRADES = {
    CompressionType.BASIC: (CompressionType.STANDARD, "Bumped to STANDARD (high pressure)"),
    CompressionType.STANDARD: (CompressionType.AGGRESSIVE, "Bumped to AGGRESSIVE (high pressure)"),
    CompressionType.AGGRESSIVE: (CompressionType.SUMMARIZE, "Bumped to SUMMARIZE (high pressure)")
}

# Initialize logger for tier selection and compression tracking
logger = MinifierLogger(
    name="tier_adapter",
    level="INFO",
    log_file="logs/tier_selection.log",
    enable_metrics=True,
    enable_performance=True
)
cached_estimate_tokens = lambda text, model: len(text.split())  # Placeholder

def performance_monitor(func: Callable) -> Callable:
    """
    Decorator to monitor function performance and warn about slow operations.
    
    Args:
        func: Function to monitor
        
    Returns:
        Wrapped function with performance monitoring
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        start_time = time.time()
        
        # Try to extract payload size from arguments
        payload_size = 0
        for arg in args:
            if isinstance(arg, str) and len(arg) > 100:  # Likely code content
                payload_size = len(arg)
                break
        
        try:
            result = func(*args, **kwargs)
            processing_time_ms = (time.time() - start_time) * 1000
            
            # Log performance metrics
            logger._safe_log(
                logger.logger.info,
                f"Performance: {func.__name__} completed in {processing_time_ms:.2f}ms "
                f"(payload: {payload_size} chars)"
            )
            
            # Warn if exceeding latency threshold for large payloads
            if payload_size > LARGE_PAYLOAD_THRESHOLD and processing_time_ms > LATENCY_WARNING_THRESHOLD:
                warning_msg = (
                    f"⚠️  LATENCY WARNING: {func.__name__} took {processing_time_ms:.2f}ms "
                    f"for {payload_size} char payload (threshold: {LATENCY_WARNING_THRESHOLD}ms). "
                    f"Consider optimization for large payloads."
                )
                logger._safe_log(logger.logger.warning, warning_msg)
                warnings.warn(warning_msg, UserWarning)
            
            return result
            
        except Exception as e:
            processing_time_ms = (time.time() - start_time) * 1000
            logger._safe_log(
                logger.logger.error,
                f"Performance: {func.__name__} failed after {processing_time_ms:.2f}ms "
                f"(payload: {payload_size} chars) - {str(e)}"
            )
            raise
    
    return wrapper


def calculate_savings_metrics(original_tokens: int, final_tokens: int, 
                              operation_context: str = "", 
                              target_threshold: float = 50.0) -> Dict[str, Any]:
    """
    Calculate comprehensive savings metrics for token reduction.
    
    Formula: (original_tokens - final_tokens) / original_tokens * 100%
    Target: > 50% savings for large/constrained cases
    
    Args:
        original_tokens: Original token count before compression
        final_tokens: Final token count after compression
        operation_context: Context for logging purposes
        target_threshold: Target savings percentage (default 50%)
        
    Returns:
        Dictionary with comprehensive savings metrics
    """
    if original_tokens <= 0:
        return {
            "savings_percent": 0.0,
            "tokens_saved": 0,
            "meets_target": False,
            "target_threshold": target_threshold,
            "efficiency_rating": "invalid",
            "compression_ratio": 0.0
        }
    
    # Calculate core metrics
    tokens_saved = original_tokens - final_tokens
    savings_percent = (tokens_saved / original_tokens) * 100
    compression_ratio = final_tokens / original_tokens if original_tokens > 0 else 1.0
    meets_target = savings_percent >= target_threshold
    
    # Determine efficiency rating
    if savings_percent >= 75:
        efficiency_rating = "excellent"
    elif savings_percent >= 60:
        efficiency_rating = "very_good"
    elif savings_percent >= 50:
        efficiency_rating = "good"
    elif savings_percent >= 30:
        efficiency_rating = "moderate"
    elif savings_percent >= 10:
        efficiency_rating = "minimal"
    else:
        efficiency_rating = "poor"
    
    metrics = {
        "original_tokens": original_tokens,
        "final_tokens": final_tokens,
        "tokens_saved": tokens_saved,
        "savings_percent": round(savings_percent, 2),
        "compression_ratio": round(compression_ratio, 3),
        "meets_target": meets_target,
        "target_threshold": target_threshold,
        "efficiency_rating": efficiency_rating,
        "operation_context": operation_context
    }
    
    # Log savings metrics
    logger._safe_log(
        logger.logger.info,
        f"Savings Metrics | Context: {operation_context} | "
        f"Tokens: {original_tokens}→{final_tokens} | "
        f"Saved: {tokens_saved} ({savings_percent:.1f}%) | "
        f"Target: {target_threshold}% {'✓' if meets_target else '✗'} | "
        f"Rating: {efficiency_rating}"
    )
    
    return metrics


def validate_no_infinite_loops(func: Callable) -> Callable:
    """
    Decorator to prevent infinite loops by setting a maximum execution time.
    
    Args:
        func: Function to protect from infinite loops
        
    Returns:
        Wrapped function with timeout protection
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        start_time = time.time()
        max_execution_time = 30  # 30 seconds max
        
        # Store original function for potential timeout handling
        original_func = func
        
        try:
            result = func(*args, **kwargs)
            execution_time = time.time() - start_time
            
            # Log if execution took a long time (potential infinite loop indicator)
            if execution_time > 5:  # 5 seconds is concerning
                logger._safe_log(
                    logger.logger.warning,
                    f"Long execution detected: {func.__name__} took {execution_time:.2f}s"
                )
            
            return result
            
        except RecursionError as e:
            logger._safe_log(
                logger.logger.error,
                f"Recursion limit exceeded in {func.__name__}: {str(e)}"
            )
            raise ValueError(f"Infinite recursion detected in {func.__name__}")
            
        except Exception as e:
            execution_time = time.time() - start_time
            if execution_time > max_execution_time:
                logger._safe_log(
                    logger.logger.error,
                    f"Timeout exceeded in {func.__name__} after {execution_time:.2f}s"
                )
                raise TimeoutError(f"Function {func.__name__} exceeded maximum execution time")
            raise
    
    return wrapper


@dataclass
class CompressionResult:
    """Data class for compression results with comprehensive metadata."""
    compressed_code: str
    tier: str
    pre_tokens: int
    post_tokens: int
    token_reduction_percent: float
    size_reduction_percent: float
    processing_time_ms: float
    operation_id: str
    additional_metrics: Optional[Dict[str, Any]] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        base = asdict(self)
        # Remove additional_metrics from base and merge it at the top level
        additional = base.pop('additional_metrics', {})
        base.update(additional)
        return base


def validate_input(content: Any, param_name: str, expected_type: type) -> None:
    """
    Validate input parameters and raise descriptive errors.
    
    Args:
        content: The value to validate
        param_name: Name of the parameter for error messages
        expected_type: Expected type of the parameter
        
    Raises:
        ValueError: If content is None or empty string
        TypeError: If content is not of expected type
    """
    if content is None:
        raise ValueError(f"{param_name} cannot be None")
    
    actual_type = type(content).__name__
    if not isinstance(content, expected_type):
        raise TypeError(
            f"{param_name} must be {expected_type.__name__}, "
            f"got {actual_type} instead"
        )
    
    if expected_type == str and not content.strip():
        raise ValueError(f"{param_name} cannot be empty or whitespace")


def validate_semantic_preservation(original_code: str, compressed_code: str) -> Dict[str, Any]:
    """
    Validate that compressed code maintains semantic equivalence with original.
    
    Args:
        original_code: The original source code
        compressed_code: The compressed/transformed code
        
    Returns:
        Dict containing validation results and metrics
        
    Raises:
        SyntaxError: If compressed code has syntax errors
        ValueError: If critical semantic violations are detected
    """
    validation_results = {
        "syntax_valid": False,
        "function_count_preserved": False,
        "class_count_preserved": False,
        "import_count_preserved": False,
        "semantic_score": 0.0,
        "warnings": [],
        "errors": []
    }
    
    try:
        # Parse both versions
        original_ast = ast.parse(original_code)
        compressed_ast = ast.parse(compressed_code)
        
        validation_results["syntax_valid"] = True
        
        # Count different node types
        def count_nodes(tree, node_type):
            return len([node for node in ast.walk(tree) if isinstance(node, node_type)])
        
        original_functions = count_nodes(original_ast, ast.FunctionDef)
        compressed_functions = count_nodes(compressed_ast, ast.FunctionDef)
        
        original_classes = count_nodes(original_ast, ast.ClassDef)
        compressed_classes = count_nodes(compressed_ast, ast.ClassDef)
        
        original_imports = count_nodes(original_ast, (ast.Import, ast.ImportFrom))
        compressed_imports = count_nodes(compressed_ast, (ast.Import, ast.ImportFrom))
        
        # Validate preservation
        validation_results["function_count_preserved"] = original_functions == compressed_functions
        validation_results["class_count_preserved"] = original_classes == compressed_classes
        validation_results["import_count_preserved"] = original_imports == compressed_imports
        
        # Calculate semantic score (0-100)
        score = 100
        
        if not validation_results["function_count_preserved"]:
            func_diff = abs(original_functions - compressed_functions)
            score -= min(30, func_diff * 10)  # Penalize function loss heavily
            validation_results["warnings"].append(
                f"Function count changed: {original_functions} → {compressed_functions}"
            )
        
        if not validation_results["class_count_preserved"]:
            class_diff = abs(original_classes - compressed_classes)
            score -= min(20, class_diff * 10)  # Penalize class loss
            validation_results["warnings"].append(
                f"Class count changed: {original_classes} → {compressed_classes}"
            )
        
        if not validation_results["import_count_preserved"]:
            import_diff = abs(original_imports - compressed_imports)
            score -= min(10, import_diff * 5)  # Imports less critical
            validation_results["warnings"].append(
                f"Import count changed: {original_imports} → {compressed_imports}"
            )
        
        validation_results["semantic_score"] = max(0, score)
        
        # Check for critical violations
        if compressed_functions == 0 and original_functions > 0:
            validation_results["errors"].append("All functions were removed during compression")
        
        if compressed_classes == 0 and original_classes > 0:
            validation_results["errors"].append("All classes were removed during compression")
        
    except SyntaxError as e:
        validation_results["syntax_valid"] = False
        validation_results["errors"].append(f"Syntax error in compressed code: {str(e)}")
        validation_results["semantic_score"] = 0
        
    except Exception as e:
        validation_results["errors"].append(f"Validation error: {str(e)}")
        validation_results["semantic_score"] = 0
    
    return validation_results


def check_otpm_safeguard(output: str, original_content: str, token_threshold: int = None) -> Tuple[str, str, int]:
    """
    Check for One Token Per Message (OTPM) vulnerability.
    
    Args:
        output: The compressed output to check
        original_content: The original content for fallback
        token_threshold: Optional token count threshold (uses OTPM_THRESHOLD if None)
        
    Returns:
        Tuple of (safe_output, warning_message, severity_level)
        severity_level: 0=safe, 1=warning, 2=critical
    """
    if token_threshold is None:
        token_threshold = OTPM_THRESHOLD
        
    lines = output.strip().split('\n')
    if not lines:
        return output, "", 0
    
    # Calculate average tokens per line for OTPM pattern detection
    total_tokens = estimate_tokens(output, method="simple")
    avg_tokens_per_line = total_tokens / len(lines)
    
    # Check for OTPM pattern
    if avg_tokens_per_line < 1.5 and len(lines) > 10:
        warning = f"OTPM pattern detected: {avg_tokens_per_line:.2f} tokens/line average"
        logger._safe_log(logger.logger.warning, warning)
        
        # Determine severity
        if avg_tokens_per_line < 1.1:
            return original_content, f"Critical {warning} - reverting to original", 2
        else:
            return output, f"Warning: {warning}", 1
    
    return output, "", 0


@lru_cache(maxsize=128)
def cached_estimate_tokens(content: str, method: str = "tiktoken", model_type: str = "gpt-4") -> int:
    """
    Cached version of token estimation to improve performance.
    Note: Only caches for identical content/method/model combinations.
    """
    try:
        return estimate_tokens(content, method=method, model_type=model_type)
    except Exception as e:
        logger._safe_log(logger.logger.warning, f"Token estimation failed: {e}, using fallback")
        return estimate_tokens(content, method="simple", model_type=model_type)


def select_waterfall_tier(input_length: int, content: str = "", model_type: str = "gpt-4") -> CompressionType:
    """
    Select compression tier based on input length using waterfall logic.
    
    Args:
        input_length: Length of the input content in characters
        content: The actual content (for token estimation)
        model_type: Model type for token estimation
        
    Returns:
        CompressionType: The appropriate compression tier
        
    Raises:
        ValueError: If input_length is negative
        TypeError: If inputs are not of expected types
    """
    # Input validation
    if input_length < 0:
        raise ValueError("input_length cannot be negative")
    validate_input(model_type, "model_type", str)
    
    start_time = time.time()
    
    # Estimate pre-compression tokens if content provided
    pre_compression_tokens = 0
    if content:
        validate_input(content, "content", str)
        pre_compression_tokens = cached_estimate_tokens(content, "tiktoken", model_type)
    
    # Determine tier based on thresholds
    if input_length <= BASIC_THRESHOLD:
        selected_tier = CompressionType.BASIC
    elif input_length <= STANDARD_THRESHOLD:
        selected_tier = CompressionType.STANDARD
    elif input_length <= AGGRESSIVE_THRESHOLD:
        selected_tier = CompressionType.AGGRESSIVE
    else:
        selected_tier = CompressionType.SUMMARIZE
    
    # Calculate processing time
    processing_time = time.time() - start_time
    
    # Log tier selection with comprehensive metrics
    tier_selection_data = {
        "event": "tier_selection",
        "timestamp": time.time(),
        "input_length": input_length,
        "selected_tier": selected_tier.name,
        "pre_compression_tokens": pre_compression_tokens,
        "model_type": model_type,
        "processing_time_ms": round(processing_time * 1000, 2),
        "thresholds": {
            "BASIC": BASIC_THRESHOLD,
            "STANDARD": STANDARD_THRESHOLD, 
            "AGGRESSIVE": AGGRESSIVE_THRESHOLD
        }
    }
    
    logger._safe_log(
        logger.logger.info,
        f"Tier Selection: {input_length} chars → {selected_tier.name} tier | "
        f"Pre-compression tokens: {pre_compression_tokens} | "
        f"Processing time: {processing_time * 1000:.2f}ms"
    )
    
    # Log detailed metrics
    logger.log_performance_metrics(
        operation_id=f"tier_select_{int(time.time() * 1000)}",
        stage="tier_selection",
        duration=processing_time,
        additional_metrics=tier_selection_data
    )
    
    return selected_tier


@performance_monitor
@validate_no_infinite_loops
def process_content_with_logging(
    content: str,
    compression_func=None,
    model_type: str = "gpt-4",
    operation_context: str = "compression",
    return_metadata: bool = False
) -> Union[Tuple[str, Dict], CompressionResult]:
    """
    Process content with comprehensive tier selection and token logging.
    
    Args:
        content: The content to process/compress
        compression_func: Optional compression function to apply
        model_type: Model type for token estimation
        operation_context: Context for logging (e.g., "minification", "translation")
        return_metadata: If True, return CompressionResult object instead of tuple
        
    Returns:
        If return_metadata=False: Tuple of (processed_content, metrics_dict)
        If return_metadata=True: CompressionResult object with full metadata
        
    Raises:
        TypeError: If inputs are not of expected types
        ValueError: If content is empty or invalid
    """
    # Input validation
    validate_input(content, "content", str)
    validate_input(model_type, "model_type", str)
    validate_input(operation_context, "operation_context", str)
    
    start_time = time.time()
    operation_id = f"{operation_context}_{int(time.time() * 1000)}"
    
    # Initial measurements
    input_length = len(content)
    
    # Pre-compression token estimation
    pre_tokens = cached_estimate_tokens(content, "tiktoken", model_type)
    
    # Tier selection with logging
    selected_tier = select_waterfall_tier(input_length, content, model_type)
    
    # Apply compression if function provided
    processed_content = content
    compression_time = 0
    otpm_warning = ""
    otpm_severity = 0
    
    if compression_func:
        try:
            compression_start = time.time()
            compressed = compression_func(content, selected_tier)
            compression_time = time.time() - compression_start
            
            # Check for OTPM vulnerability
            processed_content, otpm_warning, otpm_severity = check_otpm_safeguard(
                compressed, content
            )
            
        except Exception as e:
            logger.log_error(e, operation_id, content[:200], "compression")
            processed_content = content  # Fall back to original
    
    # Post-compression measurements
    output_length = len(processed_content)
    post_tokens = cached_estimate_tokens(processed_content, "tiktoken", model_type)
    
    # Calculate metrics
    total_time = time.time() - start_time
    size_reduction = input_length - output_length
    size_reduction_percent = (size_reduction / input_length * 100) if input_length > 0 else 0
    token_reduction = pre_tokens - post_tokens
    token_reduction_percent = (token_reduction / pre_tokens * 100) if pre_tokens > 0 else 0
    
    # Additional metrics
    additional_metrics = {
        "operation_context": operation_context,
        "model_type": model_type,
        "input_length": input_length,
        "output_length": output_length,
        "size_reduction": size_reduction,
        "token_reduction": token_reduction,
        "compression_time_ms": round(compression_time * 1000, 2),
        "compression_efficiency": round(token_reduction / total_time, 2) if total_time > 0 else 0,
        "otpm_check": {
            "warning": otpm_warning,
            "severity": otpm_severity
        }
    }
    
    # Log comprehensive results
    log_msg = (
        f"Content Processing Complete | "
        f"Tier: {selected_tier.name} | "
        f"Size: {input_length}→{output_length} chars ({size_reduction_percent:+.1f}%) | "
        f"Tokens: {pre_tokens}→{post_tokens} ({token_reduction_percent:+.1f}%) | "
        f"Time: {total_time*1000:.1f}ms"
    )
    
    if otpm_warning:
        log_msg += f" | OTPM: {otpm_warning}"
    
    logger._safe_log(logger.logger.info, log_msg)
    
    # Log detailed metrics for analysis
    logger.log_minification_complete(
        operation_id=operation_id,
        original_size=input_length,
        minified_size=output_length,
        processing_time=total_time,
        token_metrics={
            "pre_tokens": pre_tokens,
            "post_tokens": post_tokens,
            "token_reduction": token_reduction,
            "token_reduction_percent": token_reduction_percent
        }
    )
    
    if return_metadata:
        # Return comprehensive result object
        return CompressionResult(
            compressed_code=processed_content,
            tier=selected_tier.name,
            pre_tokens=pre_tokens,
            post_tokens=post_tokens,
            token_reduction_percent=round(token_reduction_percent, 2),
            size_reduction_percent=round(size_reduction_percent, 2),
            processing_time_ms=round(total_time * 1000, 2),
            operation_id=operation_id,
            additional_metrics=additional_metrics
        )
    else:
        # Return legacy tuple format
        metrics = {
            "operation_id": operation_id,
            "selected_tier": selected_tier.name,
            "pre_compression_tokens": pre_tokens,
            "post_compression_tokens": post_tokens,
            "token_reduction_percent": round(token_reduction_percent, 2),
            "size_reduction_percent": round(size_reduction_percent, 2),
            "total_time_ms": round(total_time * 1000, 2),
            **additional_metrics
        }
        return processed_content, metrics


def get_waterfall_thresholds() -> Dict[str, Union[int, float]]:
    """Get the waterfall tier thresholds for documentation/debugging."""
    return {
        'BASIC': BASIC_THRESHOLD,
        'STANDARD': STANDARD_THRESHOLD,
        'AGGRESSIVE': AGGRESSIVE_THRESHOLD,
        'SUMMARIZE': float('inf')
    }


def select_tier_from_enum_thresholds(input_length: int) -> CompressionType:
    """
    Alternative approach: Use the existing enum's built-in thresholds.
    
    This leverages the CompressionType.from_length() method which uses
    the enum's min_len and max_len values for threshold determination.
    """
    return CompressionType.from_length(input_length)


def get_enum_thresholds() -> Dict[str, Tuple[int, float]]:
    """Get the enum's built-in thresholds for comparison."""
    return {ct.name: (ct.min_len, ct.max_len) for ct in CompressionType}


def calculate_remaining_pct(headers: Dict[str, str]) -> float:
    """
    Calculate remaining token percentage from rate limit headers.
    
    Args:
        headers: Dictionary containing rate limit headers
        
    Returns:
        Percentage of remaining tokens (0-100)
        
    Raises:
        ValueError: If headers are missing or invalid
    """
    validate_input(headers, "headers", dict)
    
    try:
        remaining = int(headers.get("x-ratelimit-remaining-tokens", "0"))
        limit = int(headers.get("x-ratelimit-limit-tokens", "1"))
        
        if limit <= 0:
            raise ValueError("Invalid limit value")
            
        return (remaining / limit) * 100
    except (ValueError, KeyError) as e:
        logger._safe_log(logger.logger.warning, f"Error calculating remaining percentage: {e}")
        return 50.0  # Default to moderate pressure


@performance_monitor
@validate_no_infinite_loops
def adapt_compression(
    headers: Dict[str, str], 
    code: str, 
    is_translate: bool = False, 
    model_type: str = "gpt-4",
    return_metadata: bool = False
) -> Union[str, CompressionResult]:
    """
    Enhanced adapt_compression with input validation, caching, and metadata return.
    
    Flow:
    1. Validate inputs and calculate metrics
    2. Determine base tier via select_waterfall_tier
    3. Adjust tier based on remaining_pct from headers
    4. Apply compression based on final_tier
    5. Enhanced OTPM safeguard with exact tiktoken counting:
       - If > 0.8 * OTPM_THRESHOLD (6400): apply summarization fallback
       - If > OTPM_THRESHOLD (8000): error logging and truncation
    6. Return result with optional metadata
    
    Args:
        headers: Rate-limit headers dict
        code: Input Python code string
        is_translate: If True, bias toward translation tiers
        model_type: For token estimation
        return_metadata: If True, return CompressionResult object
    
    Returns:
        If return_metadata=False: Compressed code string
        If return_metadata=True: CompressionResult object
        
    Raises:
        TypeError: If inputs are not of expected types
        ValueError: If inputs are invalid
    """
    # Input validation
    validate_input(headers, "headers", dict)
    validate_input(code, "code", str)
    validate_input(model_type, "model_type", str)
    
    start_time = time.time()
    operation_id = f"adapt_compression_{int(time.time() * 1000)}"
    input_length = len(code)
    
    # Step 1: Metrics calculation
    remaining_pct = calculate_remaining_pct(headers)
    pre_tokens = cached_estimate_tokens(code, "tiktoken", model_type)
    
    # Step 2: Base tier from waterfall
    base_tier = select_waterfall_tier(input_length, code, model_type)
    
    # Bias for translation if requested
    if is_translate and base_tier in [CompressionType.BASIC, CompressionType.STANDARD]:
        base_tier = CompressionType.STANDARD if base_tier == CompressionType.BASIC else CompressionType.AGGRESSIVE
        logger._safe_log(logger.logger.info, f"Translation bias applied: adjusted to {base_tier.name}")
    
    # Step 3: Dynamic adjustment based on remaining_pct
    final_tier = base_tier
    adjustment_reason = "No adjustment"
    
    if remaining_pct > 80:
        # Abundant resources: Consider downgrading
        if final_tier in COMPRESSION_TIER_DOWNGRADES:
            final_tier, adjustment_reason = COMPRESSION_TIER_DOWNGRADES[final_tier]
            
    elif 20 <= remaining_pct <= 80:
        # Moderate pressure: Optimize for balance
        if final_tier == CompressionType.BASIC:
            final_tier = CompressionType.STANDARD
            adjustment_reason = "Upgraded to STANDARD (moderate pressure)"
        elif final_tier == CompressionType.SUMMARIZE:
            final_tier = CompressionType.AGGRESSIVE
            adjustment_reason = "Downgraded from SUMMARIZE (moderate pressure)"
            
    else:  # remaining_pct < 20
        # High pressure: Bump to next higher tier
        if final_tier in COMPRESSION_TIER_UPGRADES:
            final_tier, adjustment_reason = COMPRESSION_TIER_UPGRADES[final_tier]
    
    # Log tier adjustment
    logger._safe_log(
        logger.logger.info,
        f"Tier Adaptation: Base {base_tier.name} → Final {final_tier.name} | "
        f"Remaining: {remaining_pct:.1f}% | Reason: {adjustment_reason}"
    )
    
    # Step 4: Apply compression based on final tier
    try:
        if final_tier == CompressionType.BASIC:
            output = minify_code(code, aggressive=False)
        elif final_tier == CompressionType.STANDARD:
            output = minify_code(code, aggressive=True)
        elif final_tier == CompressionType.AGGRESSIVE:
            minified = minify_code(code, aggressive=True)
            output = translate_to_sudolang(ast.parse(minified), aggressive=True)
        else:  # SUMMARIZE
            output = summarize_code(code, return_mapping=False)
    except Exception as e:
        logger.log_error(e, operation_id, code[:200], f"compression_{final_tier.name}")
        output = code  # Fallback to original
    
        # Step 5: Enhanced OTPM Safeguard with exact tiktoken counting
    safe_output, otpm_warning, otpm_severity = check_otpm_safeguard(output, code, OTPM_THRESHOLD)
    
    # Count exact tokens using tiktoken for precise OTPM detection
    post_tokens = cached_estimate_tokens(safe_output, "tiktoken", model_type)
    otpm_status = "safe"
    
    # Apply summarization if approaching threshold (80% of limit)
    if post_tokens > OTPM_THRESHOLD * 0.8:
        logger._safe_log(
            logger.logger.warning, 
            f"Approaching OTPM threshold: {post_tokens} tokens (80% of {OTPM_THRESHOLD})"
        )
        
        # Log OTPM_triggered event for monitoring
        logger._safe_log(
            logger.logger.info,
            f"OTPM_triggered: Threshold approaching | "
            f"Operation: {operation_id} | Tokens: {post_tokens} | "
            f"Threshold: 80% of {OTPM_THRESHOLD} | Action: summarization"
        )
        
        try:
            safe_output = summarize_code(safe_output)
            post_tokens = cached_estimate_tokens(safe_output, "tiktoken", model_type)
            otpm_status = "summarized (approaching threshold)"
            
            # Calculate savings achieved
            original_tokens_for_savings = cached_estimate_tokens(output, "tiktoken", model_type)
            savings_percent = ((original_tokens_for_savings - post_tokens) / original_tokens_for_savings * 100) if original_tokens_for_savings > 0 else 0
            
            logger._safe_log(
                logger.logger.info,
                f"OTPM_triggered: Summarization completed | "
                f"Operation: {operation_id} | Reduced: {post_tokens} tokens | "
                f"Savings: {savings_percent:.1f}%"
            )
        except Exception as e:
            logger._safe_log(logger.logger.error, f"OTPM_triggered: Summarization failed | Error: {e}")
            otpm_status = "summarization_failed"
    
    # Error handling or truncation if still over threshold
    if post_tokens > OTPM_THRESHOLD:
        logger._safe_log(
            logger.logger.error,
            f"OTPM threshold exceeded: {post_tokens} tokens > {OTPM_THRESHOLD}"
        )
        
        # Log OTPM_triggered critical event
        logger._safe_log(
            logger.logger.error,
            f"OTPM_triggered: Critical threshold exceeded | "
            f"Operation: {operation_id} | Tokens: {post_tokens} | "
            f"Threshold: {OTPM_THRESHOLD} | Action: truncation"
        )
        
        # Last resort: truncate to stay within limits
        char_limit = OTPM_THRESHOLD * 4  # Approximate 4 chars per token
        safe_output = safe_output[:char_limit] + "\n# ... [TRUNCATED: exceeded OTPM threshold] ..."
        post_tokens = cached_estimate_tokens(safe_output, "tiktoken", model_type)
        otpm_status = "truncated (exceeded threshold)"
        
        logger._safe_log(
            logger.logger.warning,
            f"OTPM_triggered: Content truncated | "
            f"Operation: {operation_id} | Final tokens: {post_tokens} | "
            f"OTPM limit: {OTPM_THRESHOLD}"
        )
        
        # Endpoint error handling - raise exception for critical cases
        if not return_metadata:
            raise ValueError(
                f"OTPM threshold exceeded: {post_tokens} tokens > {OTPM_THRESHOLD}. "
                f"Content was truncated to respect limits. Operation: {operation_id}"
            )
    
    # Calculate final metrics
    total_time = time.time() - start_time
    output_length = len(safe_output)
    size_reduction = input_length - output_length
    size_reduction_percent = (size_reduction / input_length * 100) if input_length > 0 else 0
    token_reduction = pre_tokens - post_tokens
    token_reduction_percent = (token_reduction / pre_tokens * 100) if pre_tokens > 0 else 0
    
    # Calculate comprehensive savings metrics
    savings_metrics = calculate_savings_metrics(
        original_tokens=pre_tokens,
        final_tokens=post_tokens,
        operation_context=f"adapt_compression_{final_tier.name}",
        target_threshold=50.0  # Target > 50% for large/constrained cases
    )
    
    # Log comprehensive results
    logger._safe_log(
        logger.logger.info,
        f"Adapt Compression Complete | "
        f"Tier: {base_tier.name}→{final_tier.name} | "
        f"Tokens: {pre_tokens}→{post_tokens} ({token_reduction_percent:+.1f}%) | "
        f"Savings: {savings_metrics['savings_percent']:.1f}% ({savings_metrics['efficiency_rating']}) | "
        f"Remaining: {remaining_pct:.1f}% | "
        f"OTPM: {otpm_status} | "
        f"Time: {total_time*1000:.1f}ms"
    )
    
    # Prepare metadata
    additional_metrics = {
        "operation_context": "adapt_compression",
        "input_length": input_length,
        "output_length": output_length,
        "remaining_pct": round(remaining_pct, 2),
        "base_tier": base_tier.name,
        "final_tier": final_tier.name,
        "adjustment_reason": adjustment_reason,
        "is_translate": is_translate,
        "otpm_status": otpm_status,
        "otpm_warning": otpm_warning,
        "otpm_severity": otpm_severity,
        "otpm_threshold": OTPM_THRESHOLD,
        "size_reduction": size_reduction,
        "token_reduction": token_reduction,
        "compression_efficiency": round(token_reduction / total_time, 2) if total_time > 0 else 0,
        "savings_metrics": savings_metrics  # Add comprehensive savings metrics
    }
    
    # Log performance metrics
    logger.log_performance_metrics(
        operation_id=operation_id,
        stage="adapt_compression",
        duration=total_time,
        additional_metrics=additional_metrics
    )
    
    if return_metadata:
        return CompressionResult(
            compressed_code=safe_output,
            tier=final_tier.name,
            pre_tokens=pre_tokens,
            post_tokens=post_tokens,
            token_reduction_percent=round(token_reduction_percent, 2),
            size_reduction_percent=round(size_reduction_percent, 2),
            processing_time_ms=round(total_time * 1000, 2),
            operation_id=operation_id,
            additional_metrics=additional_metrics
        )
    else:
        return safe_output


# Stub functions for compression methods (replace with actual implementations)
def minify_code(code: str, aggressive: bool = False) -> str:
    """Stub for code minification."""
    # Replace with actual minification logic
    if aggressive:
        return code.replace("    ", "\t").replace("\n\n", "\n")
    return code.replace("    ", "  ")


def translate_to_sudolang(ast_tree, aggressive: bool = False) -> str:
    """Stub for SudoLang translation."""
    # Replace with actual translation logic
    return f"# SudoLang translation\n# Original had {len(ast_tree.body)} statements"


def summarize_code(code: str, 
                   max_imports: int = MAX_IMPORTS,
                   max_methods: int = MAX_METHODS,
                   max_functions: int = MAX_FUNCTIONS,
                   compression_ratio: float = COMPRESSION_RATIO,
                   docstring_max_len: int = 100,
                   return_mapping: bool = True,
                   output_map_file: Optional[str] = None) -> Union[str, Tuple[str, SourceMap]]:
    """
    Intelligent code summarization that preserves essential structure with line mapping.
    
    Strategy:
    1. Parse AST to identify key components
    2. Preserve imports, classes, and function signatures
    3. Summarize function bodies to docstrings/comments
    4. Keep critical logic patterns
    5. Track line mappings between source and summary
    
    Args:
        code: Python source code to summarize
        max_imports: Maximum number of imports to include
        max_methods: Maximum number of methods per class to include
        max_functions: Maximum number of standalone functions to include
        compression_ratio: Target compression ratio (0-1)
        docstring_max_len: Maximum length for docstring display
        return_mapping: Whether to return mapping data
        output_map_file: Optional file path to write mapping as JSON
        
    Returns:
        If return_mapping=True: Tuple of (summarized code, SourceMap)
        If return_mapping=False: Just the summarized code string
    """
    try:
        tree = ast.parse(code)
        source_lines = code.split('\n')
        summary_parts = []
        summary_line_index = 1  # Track current summary line (1-indexed)
        mapped_nodes = []  # Collect mapping nodes
        
        logger._safe_log(logger.logger.info, "Using AST summarization with mapping")
        
        # Helper function to add lines and track mapping
        def add_summary_lines(lines: list, node_info: Optional[dict] = None):
            nonlocal summary_line_index
            start_summary_line = summary_line_index
            
            for line in lines:
                summary_parts.append(line)
                summary_line_index += 1
            
            end_summary_line = summary_line_index - 1
            
            # Create mapping node if node info provided
            if node_info and return_mapping:
                mapped_node = MappedNode(
                    type=node_info['type'],
                    name=node_info['name'],
                    source_start=node_info['source_start'],
                    source_end=node_info['source_end'],
                    summary_start=start_summary_line,
                    summary_end=end_summary_line
                )
                mapped_nodes.append(mapped_node)
            
            return start_summary_line, end_summary_line
        
        # Collect imports with mapping
        imports = []
        import_nodes = []
        for node in tree.body:
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                imports.append(ast.unparse(node))
                import_nodes.append(node)
        
        if imports:
            import_lines = ["# Essential imports"]
            selected_imports = imports[:max_imports]
            import_lines.extend(selected_imports)
            
            if len(imports) > max_imports:
                import_lines.append(f"# ... {len(imports) - max_imports} more imports omitted")
            
            # Calculate source range for imports section
            if import_nodes:
                first_import = import_nodes[0]
                last_included = import_nodes[min(len(import_nodes)-1, max_imports-1)]
                
                add_summary_lines(import_lines, {
                    'type': 'imports',
                    'name': 'module_imports',
                    'source_start': first_import.lineno,
                    'source_end': last_included.end_lineno or last_included.lineno
                })
            else:
                add_summary_lines(import_lines)
        
        # Summarize classes with individual method mapping for granular context
        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                class_lines = []
                class_start_summary_line = summary_line_index + 1  # Track where class starts in summary
                
                class_summary = f"class {node.name}:"
                if node.bases:
                    bases = [ast.unparse(base) for base in node.bases]
                    class_summary = f"class {node.name}({', '.join(bases)}):"
                
                class_lines.append(f"\n{class_summary}")
                
                # Enhanced docstring detection
                docstring = extract_docstring(node)
                if docstring:
                    class_lines.append(f'    """{docstring}"""')
                
                # Add class header mapping (only the class declaration line, not the whole class)
                add_summary_lines(class_lines, {
                    'type': 'class_declaration',
                    'name': f"{node.name}",
                    'source_start': node.lineno,
                    'source_end': node.lineno,  # Only map the class declaration line
                })
                
                # Summarize methods with individual mapping for granular context
                methods = [n for n in node.body if isinstance(n, ast.FunctionDef)]
                
                if methods:
                    for i, method in enumerate(methods[:max_methods]):
                        method_lines = []
                        method_start_summary = summary_line_index
                        
                        args = [arg.arg for arg in method.args.args]
                        method_sig = f"    def {method.name}({', '.join(args)}):"
                        method_lines.append(method_sig)
                        
                        # Try to include first few lines of method body
                        method_body = get_method_body_sample(code, method)
                        if method_body:
                            method_lines.extend(method_body)
                        else:
                            method_lines.append("        ...")
                        
                        # Add individual method mapping for granular context
                        add_summary_lines(method_lines, {
                            'type': 'method',
                            'name': f"{node.name}.{method.name}",
                            'source_start': method.lineno,
                            'source_end': method.end_lineno or method.lineno,
                        })
                    
                    if len(methods) > max_methods:
                        omitted_methods_line = [f"    # ... {len(methods) - max_methods} more methods"]
                        add_summary_lines(omitted_methods_line, {
                            'type': 'omitted_methods',
                            'name': f"{node.name}.omitted_methods",
                            'source_start': methods[max_methods].lineno,
                            'source_end': methods[-1].end_lineno or methods[-1].lineno,
                        })
        
        # Summarize standalone functions with individual mapping for granular context
        functions = [node for node in tree.body if isinstance(node, ast.FunctionDef)]
        if functions:
            # Add functions section header
            func_header_lines = ["\n# Main functions:"]
            add_summary_lines(func_header_lines)
            
            for i, func in enumerate(functions[:max_functions]):
                func_lines = []
                
                args = [arg.arg for arg in func.args.args]
                returns = f" -> {ast.unparse(func.returns)}" if func.returns else ""
                func_sig = f"def {func.name}({', '.join(args)}){returns}:"
                func_lines.append(func_sig)
                
                # Include docstring if present
                docstring = extract_docstring(func)
                if docstring:
                    truncated = docstring[:docstring_max_len]
                    ellipsis = "..." if len(docstring) > docstring_max_len else ""
                    func_lines.append(f'    """{truncated}{ellipsis}"""')
                else:
                    func_lines.append("    ...")
                
                # Add individual function mapping for granular context
                add_summary_lines(func_lines, {
                    'type': 'function',
                    'name': func.name,
                    'source_start': func.lineno,
                    'source_end': func.end_lineno or func.lineno,
                })
            
            if len(functions) > max_functions:
                omitted_funcs_line = [f"# ... {len(functions) - max_functions} more functions"]
                add_summary_lines(omitted_funcs_line, {
                    'type': 'omitted_functions', 
                    'name': 'omitted_functions',
                    'source_start': functions[max_functions].lineno,
                    'source_end': functions[-1].end_lineno or functions[-1].lineno,
                })
        
        # Enhanced main execution block handling with mapping
        main_code = []
        main_nodes = []
        for node in tree.body:
            if not isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.Import, ast.ImportFrom)):
                unparsed = ast.unparse(node)
                if len(unparsed) > MAX_STATEMENT_LENGTH:
                    main_code.append("# [complex statement omitted]")
                else:
                    main_code.append(unparsed)
                main_nodes.append(node)
        
        if main_code:
            main_lines = ["\n# Main execution:"]
            if len(main_code) <= 3:
                main_lines.extend(main_code)
            else:
                main_lines.extend(main_code[:2])
                main_lines.append(f"# ... {len(main_code) - 2} more statements")
            
            if main_nodes and return_mapping:
                first_main = main_nodes[0]
                last_main = main_nodes[-1] if len(main_code) <= 3 else main_nodes[1]
                
                add_summary_lines(main_lines, {
                    'type': 'main_execution',
                    'name': 'main_code',
                    'source_start': first_main.lineno,
                    'source_end': last_main.end_lineno or last_main.lineno
                })
            else:
                add_summary_lines(main_lines)
        
        # Add summary statistics
        class_count = len([n for n in tree.body if isinstance(n, ast.ClassDef)])
        stats_lines = [f"\n# Summary: {len(functions)} functions, {class_count} classes"]
        add_summary_lines(stats_lines)
        
        result = '\n'.join(summary_parts)
        
        # Guard against empty output
        if not summary_parts or not result.strip():
            logger.warning("AST summarization produced empty output; using fallback")
            return _fallback_summarize(code, return_mapping)
        
        # Token-based compression check
        original_tokens = cached_estimate_tokens(code, "tiktoken")
        summary_tokens = cached_estimate_tokens(result, "tiktoken")
        
        if summary_tokens > compression_ratio * original_tokens:
            logger._safe_log(logger.logger.info, "Falling back to aggressive summarization due to insufficient compression")
            return _aggressive_summarize(code, return_mapping)
        
        # Add compression stats
        reduction = ((original_tokens - summary_tokens) / original_tokens * 100)
        compression_lines = [f"# Compression: {original_tokens} → {summary_tokens} tokens ({reduction:.1f}% reduction)"]
        add_summary_lines(compression_lines)
        
        # Create final result
        final_result = '\n'.join(summary_parts)
        
        # Create source map
        if return_mapping:
            source_map = SourceMap(mapped_nodes)
            
            # Optionally write mapping to disk
            if output_map_file:
                try:
                    # Ensure directory exists if path includes directory
                    if os.path.dirname(output_map_file):
                        os.makedirs(os.path.dirname(output_map_file), exist_ok=True)
                    
                    with open(output_map_file, 'w') as f:
                        json.dump(source_map.to_dict(), f, indent=2)
                    
                    logger._safe_log(logger.logger.info, f"Source map written to {output_map_file}")
                except Exception as e:
                    logger._safe_log(logger.logger.warning, f"Failed to write source map to {output_map_file}: {e}")
            
            return final_result, source_map
        
        return final_result
        
    except Exception as e:
        logger._safe_log(logger.logger.warning, f"AST parsing failed; using fallback summarization. Error: {e}")
        return _fallback_summarize(code, return_mapping)


def extract_docstring(node):
    """
    Enhanced docstring detection that checks first few statements.
    
    Args:
        node: AST node (function or class)
        
    Returns:
        Docstring if found, None otherwise
    """
    for stmt in node.body[:3]:  # Check first 3 statements
        if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant):
            value = stmt.value.value
            if isinstance(value, str):
                return value
    return None


def get_method_body_sample(code: str, method: ast.FunctionDef, max_lines: int = 2):
    """
    Get first few lines of method body for context.
    
    Args:
        code: Original source code
        method: AST FunctionDef node
        max_lines: Maximum lines to include
        
    Returns:
        List of indented body lines or None
    """
    try:
        # Get the source segment for the method
        src = ast.get_source_segment(code, method)
        if not src:
            return None
            
        lines = src.splitlines()
        
        # Find where the body starts (after the signature and docstring)
        body_start = 1
        for i, line in enumerate(lines[1:], 1):
            stripped = line.strip()
            # Skip docstrings
            if stripped.startswith(('"""', "'''")):
                # Find end of docstring
                quote = stripped[:3]
                if stripped.count(quote) == 2:  # Single-line docstring
                    body_start = i + 1
                else:
                    for j in range(i + 1, len(lines)):
                        if quote in lines[j]:
                            body_start = j + 1
                            break
                break
            elif stripped and not stripped.startswith('#'):
                body_start = i
                break
        
        # Get the body lines
        body_lines = []
        indent = "        "  # Two levels of indentation
        
        for line in lines[body_start:body_start + max_lines]:
            if line.strip():
                body_lines.append(indent + line.strip())
        
        return body_lines if body_lines else None
        
    except Exception:
        return None


def _aggressive_summarize(code: str, return_mapping: bool = False) -> Union[str, Tuple[str, SourceMap]]:
    """Aggressive summarization for when AST approach doesn't compress enough."""
    logger._safe_log(logger.logger.info, "Using aggressive summarization")
    lines = code.split('\n')
    summary = []
    
    # Keep first 5 and last 5 lines
    if len(lines) <= 15:
        result = code
        if return_mapping:
            return result, SourceMap([])
        return result
    
    summary.extend(lines[:5])
    summary.append(f"# ... {len(lines) - 10} lines omitted for brevity ...")
    summary.extend(lines[-5:])
    
    # Add compression stats
    original_tokens = cached_estimate_tokens(code, "tiktoken")
    compressed_tokens = cached_estimate_tokens('\n'.join(summary), "tiktoken")
    reduction = ((original_tokens - compressed_tokens) / original_tokens * 100)
    summary.append(f"# Compression: {original_tokens} → {compressed_tokens} tokens ({reduction:.1f}% reduction)")
    
    result = '\n'.join(summary)
    
    if return_mapping:
        # Create a simple mapping for the preserved sections
        mapped_nodes = []
        if len(lines) > 15:
            # Map first 5 lines
            mapped_nodes.append(MappedNode(
                type='preserved_header',
                name='file_header',
                source_start=1,
                source_end=5,
                summary_start=1,
                summary_end=5
            ))
            
            # Map last 5 lines
            mapped_nodes.append(MappedNode(
                type='preserved_footer',
                name='file_footer',
                source_start=len(lines) - 4,
                source_end=len(lines),
                summary_start=7,  # After omission comment
                summary_end=11
            ))
        
        return result, SourceMap(mapped_nodes)
    
    return result


def _fallback_summarize(code: str, return_mapping: bool = False) -> Union[str, Tuple[str, SourceMap]]:
    """Simple fallback summarization when AST parsing fails."""
    logger._safe_log(logger.logger.info, "Using fallback summarization")
    lines = code.split('\n')
    
    if len(lines) <= 10:
        result = code
        if return_mapping:
            return result, SourceMap([])
        return result
    
    # Keep imports, class/function definitions, and some content
    important_lines = []
    important_line_numbers = []
    
    for i, line in enumerate(lines):
        stripped = line.strip()
        if (stripped.startswith(('import ', 'from ', 'class ', 'def ', '@')) or
            stripped.startswith('#') or
            i < 3 or i >= len(lines) - 3):
            important_lines.append(line)
            important_line_numbers.append(i + 1)  # 1-indexed
        elif len(important_lines) < 20:  # Limit total lines
            important_lines.append(line)
            important_line_numbers.append(i + 1)  # 1-indexed
    
    if len(important_lines) < len(lines):
        important_lines.append(f"# ... {len(lines) - len(important_lines)} lines omitted ...")
    
    result = '\n'.join(important_lines)
    
    if return_mapping:
        # Create mapping for preserved lines
        mapped_nodes = []
        if important_line_numbers:
            # Group consecutive line numbers
            groups = []
            current_group = [important_line_numbers[0]]
            
            for line_num in important_line_numbers[1:]:
                if line_num == current_group[-1] + 1:
                    current_group.append(line_num)
                else:
                    groups.append(current_group)
                    current_group = [line_num]
            groups.append(current_group)
            
            # Create mapping nodes for each group
            summary_line = 1
            for i, group in enumerate(groups):
                if len(group) > 0:
                    mapped_nodes.append(MappedNode(
                        type='preserved_section',
                        name=f'fallback_section_{i+1}',
                        source_start=group[0],
                        source_end=group[-1],
                        summary_start=summary_line,
                        summary_end=summary_line + len(group) - 1
                    ))
                    summary_line += len(group)
        
        return result, SourceMap(mapped_nodes)
    
    return result

# Test utility functions
def mock_compression(content: str, tier: CompressionType) -> str:
    """
    Mock compression function for testing.
    
    Simulates different compression strategies based on tier.
    
    Args:
        content: The content to compress
        tier: The compression tier to apply
        
    Returns:
        Mock compressed content
    """
    if tier == CompressionType.BASIC:
        # Basic: Replace spaces with tabs
        return content.replace("    ", "\t")
    elif tier == CompressionType.STANDARD:
        # Standard: Remove double newlines and compress spaces
        return content.replace("\n\n", "\n").replace("    ", "\t")
    elif tier == CompressionType.AGGRESSIVE:
        # Aggressive: Strip empty lines and leading spaces
        lines = content.split('\n')
        return '\n'.join(line.strip() for line in lines if line.strip())
    else:  # SUMMARIZE
        # Summarize: Return abbreviated version
        return f"# Summarized content ({len(content)} chars)\n# Original content too large"


# Test samples with input validation
def run_waterfall_tests():
    """Run test cases for the waterfall tier selection with logging demonstration."""
    test_cases = [
        (300, CompressionType.BASIC, "# Small Python script\nprint('Hello, World!')"),
        (1500, CompressionType.STANDARD, "# Medium Python script\n" + "x = 1\n" * 75),
        (7500, CompressionType.AGGRESSIVE, "# Large Python script\n" + "def func():\n    pass\n" * 500),
        (15000, CompressionType.SUMMARIZE, "# Very large Python script\n" + "class TestClass:\n    def method(self):\n        return True\n" * 500),
        (1000, CompressionType.BASIC, "# Boundary test\n" + "y = 2\n" * 50),
        (5000, CompressionType.STANDARD, "# Boundary test\n" + "z = 3\n" * 250),
        (10000, CompressionType.AGGRESSIVE, "# Boundary test\n" + "a = 4\n" * 500),
    ]

    logger._safe_log(logger.logger.info, "=" * 60)
    logger._safe_log(logger.logger.info, "STARTING WATERFALL TIER SELECTION TESTS WITH LOGGING")
    logger._safe_log(logger.logger.info, "=" * 60)

    print("Waterfall Tier Selection Tests with Enhanced Features:")
    print("=" * 70)
    
    all_metrics = []
    all_results = []
    
    for i, (expected_length, expected_tier, sample_content) in enumerate(test_cases, 1):
        print(f"\nTest Case {i}:")
        print("-" * 40)
        
        # Test basic tier selection
        actual_length = len(sample_content)
        result = select_waterfall_tier(actual_length, sample_content)
        enum_result = select_tier_from_enum_thresholds(actual_length)
        status = '✓' if result == expected_tier else '✗'
        
        print(f"Expected: {expected_length:>6} chars → {expected_tier.name}")
        print(f"Actual:   {actual_length:>6} chars → {result.name:<10} | Enum: {enum_result.name:<10} {status}")
        
        # Test full processing pipeline with mock compression
        compression_result = process_content_with_logging(
            sample_content,
            compression_func=mock_compression,
            model_type="gpt-4",
            operation_context=f"test_case_{i}",
            return_metadata=True
        )
        
        all_results.append(compression_result)
        metrics = compression_result.to_dict()
        all_metrics.append(metrics)
        
        print(f"Processed: {compression_result.post_tokens} tokens | "
              f"Reduction: {compression_result.token_reduction_percent:+.1f}% | "
              f"Time: {compression_result.processing_time_ms:.1f}ms")
        
        if metrics['otpm_check']['warning']:
            print(f"OTPM Check: {metrics['otpm_check']['warning']}")
    
    # Test input validation
    print("\n" + "=" * 70)
    print("INPUT VALIDATION TESTS:")
    print("=" * 70)
    
    validation_tests = [
        ("Empty string", lambda: select_waterfall_tier(0, "", "gpt-4"), "Should succeed"),
        ("Negative length", lambda: select_waterfall_tier(-1), "Should raise ValueError"),
        ("None content", lambda: process_content_with_logging(None), "Should raise ValueError"),
        ("Invalid type", lambda: process_content_with_logging(123), "Should raise TypeError"),
    ]
    
    for test_name, test_func, expected in validation_tests:
        try:
            test_func()
            print(f"{test_name}: ✓ Passed ({expected})")
        except (ValueError, TypeError) as e:
            print(f"{test_name}: ✓ Caught expected error: {type(e).__name__}")
        except Exception as e:
            print(f"{test_name}: ✗ Unexpected error: {type(e).__name__}: {e}")
    
    # Summary statistics
    print("\n" + "=" * 70)
    print("SUMMARY STATISTICS:")
    print("=" * 70)
    
    avg_size_reduction = sum(m['size_reduction_percent'] for m in all_metrics) / len(all_metrics)
    avg_token_reduction = sum(m['token_reduction_percent'] for m in all_metrics) / len(all_metrics)
    total_processing_time = sum(m.get('total_time_ms', m.get('processing_time_ms', 0)) for m in all_metrics)
    
    print(f"Average Size Reduction:  {avg_size_reduction:>6.1f}%")
    print(f"Average Token Reduction: {avg_token_reduction:>6.1f}%")
    print(f"Total Processing Time:   {total_processing_time:>6.1f}ms")
    
    # Cache statistics
    cache_info = cached_estimate_tokens.cache_info()
    print(f"\nToken Estimation Cache Stats:")
    print(f"  Hits:   {cache_info.hits}")
    print(f"  Misses: {cache_info.misses}")
    print(f"  Size:   {cache_info.currsize}/{cache_info.maxsize}")
    
    return all_results


def run_adapt_tests():
    """Run comprehensive tests for adapt_compression with various scenarios."""
    print("\n" + "=" * 70)
    print("ADAPT COMPRESSION TESTS")
    print("=" * 70)
    
    # Test scenarios with different resource levels
    test_scenarios = [
        {
            "name": "Abundant Resources (90%)",
            "headers": {"x-ratelimit-remaining-tokens": "90000", "x-ratelimit-limit-tokens": "100000"},
            "code_samples": [
                ("Small", "def hello(): return 'world'" * 10),
                ("Medium", "class Example:\n    def __init__(self):\n        self.value = 42\n" * 100),
                ("Large", "def process_data(data):\n    result = []\n    for item in data:\n        result.append(item * 2)\n    return result\n" * 500)
            ]
        },
        {
            "name": "Moderate Resources (50%)",
            "headers": {"x-ratelimit-remaining-tokens": "50000", "x-ratelimit-limit-tokens": "100000"},
            "code_samples": [
                ("Small", "x = 1; y = 2; z = x + y" * 20),
                ("Medium", "def calculate(a, b, c):\n    return (a + b) * c\n" * 200),
                ("Large", "import math\n\ndef complex_calculation(values):\n    return sum(math.sqrt(v) for v in values)\n" * 300)
            ]
        },
        {
            "name": "Low Resources (10%)",
            "headers": {"x-ratelimit-remaining-tokens": "10000", "x-ratelimit-limit-tokens": "100000"},
            "code_samples": [
                ("Small", "print('test')" * 50),
                ("Medium", "for i in range(100):\n    if i % 2 == 0:\n        print(i)\n" * 100),
                ("Large", "class DataProcessor:\n    def __init__(self):\n        self.data = []\n    def process(self):\n        return sorted(self.data)\n" * 400)
            ]
        }
    ]
    
    all_results = []
    
    for scenario in test_scenarios:
        print(f"\n{scenario['name']}:")
        print("-" * 50)
        
        for size_name, code in scenario['code_samples']:
            print(f"\n  {size_name} code sample ({len(code)} chars):")
            
            # Test without metadata
            compressed = adapt_compression(
                scenario['headers'], 
                code,
                is_translate=False,
                model_type="gpt-4"
            )
            
            # Test with metadata
            result = adapt_compression(
                scenario['headers'],
                code,
                is_translate=False,
                model_type="gpt-4",
                return_metadata=True
            )
            
            all_results.append(result)
            
            print(f"    Base tier: {result.additional_metrics['base_tier']}")
            print(f"    Final tier: {result.additional_metrics['final_tier']}")
            print(f"    Adjustment: {result.additional_metrics['adjustment_reason']}")
            print(f"    Tokens: {result.pre_tokens} → {result.post_tokens} ({result.token_reduction_percent:+.1f}%)")
            print(f"    Size: {len(code)} → {len(result.compressed_code)} ({result.size_reduction_percent:+.1f}%)")
            print(f"    OTPM Status: {result.additional_metrics['otpm_status']}")
            print(f"    Time: {result.processing_time_ms:.1f}ms")
    
    # Test translation bias
    print("\n" + "=" * 70)
    print("TRANSLATION BIAS TESTS")
    print("=" * 70)
    
    translation_code = "def translate_me(): return 'hello world'" * 50
    headers = {"x-ratelimit-remaining-tokens": "50000", "x-ratelimit-limit-tokens": "100000"}
    
    regular_result = adapt_compression(headers, translation_code, is_translate=False, return_metadata=True)
    translate_result = adapt_compression(headers, translation_code, is_translate=True, return_metadata=True)
    
    print(f"Regular compression: {regular_result.additional_metrics['final_tier']}")
    print(f"Translation-biased: {translate_result.additional_metrics['final_tier']}")
    
    # Test error handling
    print("\n" + "=" * 70)
    print("ERROR HANDLING TESTS")
    print("=" * 70)
    
    error_tests = [
        ("Invalid headers", lambda: adapt_compression({"invalid": "headers"}, "code")),
        ("Empty headers", lambda: adapt_compression({}, "code")),
        ("None code", lambda: adapt_compression({"x-ratelimit-remaining-tokens": "1000"}, None)),
        ("Invalid header values", lambda: adapt_compression({"x-ratelimit-remaining-tokens": "abc"}, "code")),
    ]
    
    for test_name, test_func in error_tests:
        try:
            test_func()
            print(f"{test_name}: Handled gracefully")
        except (ValueError, TypeError) as e:
            print(f"{test_name}: Caught expected {type(e).__name__}: {str(e)[:50]}")
        except Exception as e:
            print(f"{test_name}: Unexpected error: {type(e).__name__}")
    
    # Summary statistics
    print("\n" + "=" * 70)
    print("SUMMARY STATISTICS")
    print("=" * 70)
    
    # Group by resource level
    resource_groups = {"90%": [], "50%": [], "10%": []}
    for i, result in enumerate(all_results):
        if i < 3:
            resource_groups["90%"].append(result)
        elif i < 6:
            resource_groups["50%"].append(result)
        else:
            resource_groups["10%"].append(result)
    
    for level, results in resource_groups.items():
        if results:
            avg_reduction = sum(r.token_reduction_percent for r in results) / len(results)
            avg_time = sum(r.processing_time_ms for r in results) / len(results)
            print(f"\nResource Level {level}:")
            print(f"  Average token reduction: {avg_reduction:+.1f}%")
            print(f"  Average processing time: {avg_time:.1f}ms")
            
            tier_counts = {}
            for r in results:
                tier = r.additional_metrics['final_tier']
                tier_counts[tier] = tier_counts.get(tier, 0) + 1
            print(f"  Tier distribution: {tier_counts}")
    
    return all_results


if __name__ == "__main__":
    # Run original tests
    print("Running waterfall tier selection tests...")
    run_waterfall_tests()
    
    # Run adapt compression tests
    print("\nRunning adapt compression tests...")
    adapt_results = run_adapt_tests()
    
    # Clear cache and show final statistics
    print("\n" + "=" * 70)
    print("FINAL CACHE STATISTICS")
    print("=" * 70)
    cache_info = cached_estimate_tokens.cache_info()
    print(f"Cache hits: {cache_info.hits}")
    print(f"Cache misses: {cache_info.misses}")
    print(f"Cache size: {cache_info.currsize}/{cache_info.maxsize}")
    print(f"Hit rate: {(cache_info.hits / (cache_info.hits + cache_info.misses) * 100):.1f}%")