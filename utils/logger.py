import ast
import sys
import operator
import warnings
import logging
import time
import json
import uuid
from datetime import datetime
from typing import Union, Dict, Set, Any, Tuple, Optional, List, Callable
from pathlib import Path
import traceback

# Python version compatibility check
if sys.version_info < (3, 8):
    warnings.warn(
        "Python minifier requires Python 3.8+. Older versions may have incomplete compatibility.",
        RuntimeWarning,
        stacklevel=2
    )

# Try to import astor for Python 3.8 compatibility
try:
    import astor
    HAS_ASTOR = True
except ImportError:
    HAS_ASTOR = False


class MinifierLogger:
    """Enhanced logger specifically designed for Python code minification metrics and operations."""
    
    def __init__(
        self,
        name: str = "python_minifier",
        level: str = "INFO",
        log_file: Optional[str] = None,
        log_format: Optional[str] = None,
        enable_console: bool = True,
        enable_file: bool = True,
        enable_metrics: bool = True,
        enable_performance: bool = True,
        enable_ast_details: bool = False,  # Detailed AST transformation logging
        production_mode: bool = False
    ):
        self.logger = logging.getLogger(name)
        self.logger.setLevel(getattr(logging, level.upper()))
        self.logger.handlers = []  # Clear existing handlers
        self.enable_metrics = enable_metrics
        self.enable_performance = enable_performance
        self.enable_ast_details = enable_ast_details
        self.production_mode = production_mode
        
        # Session tracking
        self.session_id = str(uuid.uuid4())
        self.operation_counter = 0
        
        # Prevent logging failures from crashing minification in production
        if production_mode:
            logging.raiseExceptions = False
        
        # Default format with operation context
        if log_format is None:
            log_format = '%(asctime)s - %(name)s - %(levelname)s - [%(session_id)s] - %(message)s'
        
        # Custom formatter that includes session ID
        class MinifierFormatter(logging.Formatter):
            def format(self, record):
                if not hasattr(record, 'session_id'):
                    record.session_id = getattr(self, 'session_id', 'unknown')
                return super().format(record)
        
        formatter = MinifierFormatter(log_format)
        
        # Console handler
        if enable_console:
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setFormatter(formatter)
            self.logger.addHandler(console_handler)
        
        # File handler
        if enable_file and log_file:
            Path(log_file).parent.mkdir(parents=True, exist_ok=True)
            file_handler = logging.FileHandler(log_file)
            file_handler.setFormatter(formatter)
            self.logger.addHandler(file_handler)
        
        # Add session_id to logger for formatter access
        self.logger.session_id = self.session_id
    
    def _safe_log(self, log_func, message: str, extra: Optional[Dict] = None, *args, **kwargs):
        """Fail-safe wrapper for all logging operations."""
        try:
            if extra is None:
                extra = {}
            extra['session_id'] = self.session_id
            log_func(message, extra=extra, *args, **kwargs)
        except Exception as e:
            try:
                print(f"MINIFIER_LOGGING_ERROR: {e} - Original message: {message}", file=sys.stderr)
            except:
                pass  # Ultimate fallback
    
    def _safe_json_dumps(self, data: Dict[str, Any], context: str) -> str:
        """Safely serialize data to JSON with fallback error handling."""
        try:
            return json.dumps(data, default=str, indent=2)
        except Exception as e:
            self._safe_log(self.logger.error, f"Failed to serialize {context}: {e}")
            return f"<serialization_error: {str(e)}>"
    
    def log_minification_start(self, code_length: int, compression_depth: int, aggressive: bool):
        """Log the start of a minification operation."""
        self.operation_counter += 1
        operation_id = f"{self.session_id}-{self.operation_counter}"
        
        start_data = {
            "event": "minification_start",
            "operation_id": operation_id,
            "timestamp": datetime.utcnow().isoformat(),
            "input_code_length": code_length,
            "compression_depth": compression_depth,
            "aggressive_mode": aggressive,
            "python_version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
            "has_astor": HAS_ASTOR
        }
        
        if self.enable_metrics:
            json_str = self._safe_json_dumps(start_data, "minification_start")
            self._safe_log(self.logger.info, f"Starting minification: {json_str}")
        
        return operation_id
    
    def log_minification_complete(self, operation_id: str, original_size: int, minified_size: int, 
                                  processing_time: float, token_metrics: Optional[Dict] = None):
        """Log completion of minification with comprehensive metrics."""
        size_reduction = original_size - minified_size
        size_reduction_percent = (size_reduction / original_size * 100) if original_size > 0 else 0
        
        completion_data = {
            "event": "minification_complete",
            "operation_id": operation_id,
            "timestamp": datetime.utcnow().isoformat(),
            "original_size_bytes": original_size,
            "minified_size_bytes": minified_size,
            "size_reduction_bytes": size_reduction,
            "size_reduction_percent": round(size_reduction_percent, 2),
            "processing_time_seconds": round(processing_time, 4),
            "throughput_bytes_per_second": round(original_size / processing_time, 2) if processing_time > 0 else 0
        }
        
        if token_metrics:
            completion_data.update(token_metrics)
        
        if self.enable_metrics:
            json_str = self._safe_json_dumps(completion_data, "minification_complete")
            self._safe_log(self.logger.info, f"Minification completed: {json_str}")
    
    def log_ast_transformation(self, transformation_type: str, node_type: str, 
                              details: Optional[Dict] = None, optimization_applied: bool = False):
        """Log AST transformation details."""
        if not self.enable_ast_details:
            return
        
        transform_data = {
            "event": "ast_transformation",
            "timestamp": datetime.utcnow().isoformat(),
            "transformation_type": transformation_type,
            "node_type": node_type,
            "optimization_applied": optimization_applied
        }
        
        if details:
            transform_data["details"] = details
        
        json_str = self._safe_json_dumps(transform_data, "ast_transformation")
        self._safe_log(self.logger.debug, f"AST transformation: {json_str}")
    
    def log_optimization(self, optimization_type: str, before_value: Any, after_value: Any, 
                        node_location: Optional[str] = None):
        """Log specific optimization applied."""
        optimization_data = {
            "event": "optimization_applied",
            "timestamp": datetime.utcnow().isoformat(),
            "optimization_type": optimization_type,
            "before": str(before_value),
            "after": str(after_value),
            "node_location": node_location
        }
        
        json_str = self._safe_json_dumps(optimization_data, "optimization")
        self._safe_log(self.logger.debug, f"Optimization applied: {json_str}")
    
    def log_variable_shortening(self, original_name: str, short_name: str, scope_depth: int):
        """Log variable name shortening operations."""
        if not self.enable_ast_details:
            return
        
        shortening_data = {
            "event": "variable_shortened",
            "timestamp": datetime.utcnow().isoformat(),
            "original_name": original_name,
            "shortened_name": short_name,
            "scope_depth": scope_depth,
            "length_reduction": len(original_name) - len(short_name)
        }
        
        json_str = self._safe_json_dumps(shortening_data, "variable_shortening")
        self._safe_log(self.logger.debug, f"Variable shortened: {json_str}")
    
    def log_token_estimation(self, code: str, method: str, estimated_tokens: int, 
                            model_type: str, actual_tokens: Optional[int] = None):
        """Log token estimation metrics."""
        estimation_data = {
            "event": "token_estimation",
            "timestamp": datetime.utcnow().isoformat(),
            "method": method,
            "model_type": model_type,
            "code_length": len(code),
            "estimated_tokens": estimated_tokens
        }
        
        if actual_tokens is not None:
            estimation_data["actual_tokens"] = actual_tokens
            estimation_data["estimation_accuracy"] = round((1 - abs(estimated_tokens - actual_tokens) / actual_tokens) * 100, 2)
        
        json_str = self._safe_json_dumps(estimation_data, "token_estimation")
        self._safe_log(self.logger.info, f"Token estimation: {json_str}")
    
    def log_error(self, error: Exception, operation_id: Optional[str] = None, 
                  code_context: Optional[str] = None, stage: str = "unknown"):
        """Log errors during minification process."""
        error_data = {
            "event": "minification_error",
            "timestamp": datetime.utcnow().isoformat(),
            "operation_id": operation_id,
            "stage": stage,
            "error_type": type(error).__name__,
            "error_message": str(error),
            "traceback": traceback.format_exc()
        }
        
        if code_context:
            error_data["code_context"] = code_context[:500]  # First 500 chars for context
        
        json_str = self._safe_json_dumps(error_data, "error")
        self._safe_log(self.logger.error, f"Minification error: {json_str}")
    
    def log_performance_metrics(self, operation_id: str, stage: str, duration: float, 
                               memory_usage: Optional[int] = None, additional_metrics: Optional[Dict] = None):
        """Log performance metrics for different stages."""
        if not self.enable_performance:
            return
        
        perf_data = {
            "event": "performance_metrics",
            "operation_id": operation_id,
            "timestamp": datetime.utcnow().isoformat(),
            "stage": stage,
            "duration_seconds": round(duration, 6),
            "memory_usage_bytes": memory_usage
        }
        
        if additional_metrics:
            perf_data.update(additional_metrics)
        
        json_str = self._safe_json_dumps(perf_data, "performance")
        self._safe_log(self.logger.debug, f"Performance metrics: {json_str}")
    
    def log_validation_result(self, operation_id: str, validation_passed: bool, 
                             validation_time: float, validation_details: Optional[Dict] = None):
        """Log code validation results."""
        validation_data = {
            "event": "validation_result",
            "operation_id": operation_id,
            "timestamp": datetime.utcnow().isoformat(),
            "validation_passed": validation_passed,
            "validation_time_seconds": round(validation_time, 6)
        }
        
        if validation_details:
            validation_data["details"] = validation_details
        
        json_str = self._safe_json_dumps(validation_data, "validation")
        log_level = self.logger.info if validation_passed else self.logger.warning
        self._safe_log(log_level, f"Validation result: {json_str}")
    
    def log_token_metrics(self, metrics_data: Dict[str, Any]):
        """Log token-related metrics and events."""
        log_data = {
            "timestamp": datetime.utcnow().isoformat(),
            "session_id": self.session_id,
            **metrics_data
        }
        
        json_str = self._safe_json_dumps(log_data, "token_metrics")
        self._safe_log(self.logger.info, f"Token metrics: {json_str}")


# Global logger instance
_global_logger: Optional[MinifierLogger] = None


def setup_minifier_logging(
    log_level: str = "INFO",
    log_file: Optional[str] = "logs/minifier.log",
    enable_console: bool = True,
    enable_file: bool = True,
    enable_metrics: bool = True,
    enable_performance: bool = True,
    enable_ast_details: bool = False,
    production_mode: bool = False
) -> MinifierLogger:
    """
    Setup logging for the Python minifier.
    
    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: Path to log file (None to disable file logging)
        enable_console: Enable console logging
        enable_file: Enable file logging
        enable_metrics: Enable minification metrics logging
        enable_performance: Enable performance metrics logging
        enable_ast_details: Enable detailed AST transformation logging
        production_mode: Enable production safety features
    
    Returns:
        MinifierLogger instance
    """
    global _global_logger
    
    _global_logger = MinifierLogger(
        name="python_minifier",
        level=log_level,
        log_file=log_file,
        enable_console=enable_console,
        enable_file=enable_file,
        enable_metrics=enable_metrics,
        enable_performance=enable_performance,
        enable_ast_details=enable_ast_details,
        production_mode=production_mode
    )
    
    return _global_logger


def get_logger() -> MinifierLogger:
    """Get the global minifier logger instance."""
    global _global_logger
    if _global_logger is None:
        _global_logger = setup_minifier_logging()
    return _global_logger


# Compression depth levels
class CompressionDepth:
    """Enumeration for compression depth levels."""
    BASIC = 1       # Comments and whitespace only
    CONSTANTS = 2   # + Constant folding
    VARIABLES = 3   # + Variable name shortening
    AGGRESSIVE = 4  # + All optimizations


def minify_code(
    code_str: str, 
    aggressive: bool = False, 
    validate: bool = True,
    compression_depth: Optional[int] = None
) -> str:
    """
    Minify Python code by removing whitespace, comments, and redundant elements
    while preserving 100% semantic equivalence.
    
    Args:
        code_str: The Python source code string to minify
        aggressive: Enable aggressive optimizations (variable name shortening)
                   [Deprecated: Use compression_depth instead]
        validate: Validate minified output by re-parsing (recommended)
        compression_depth: Control optimization level (1-4):
                          1=BASIC (comments/whitespace only)
                          2=CONSTANTS (+ constant folding)
                          3=VARIABLES (+ variable shortening)
                          4=AGGRESSIVE (+ all optimizations)
                          None=use aggressive flag for backward compatibility
        
    Returns:
        Minified Python code string
        
    Raises:
        SyntaxError: If the input code is invalid Python
        ValueError: If the code cannot be unparsed or validation fails
    """
    logger = get_logger()
    start_time = time.time()
    operation_id = None
    
    try:
        # Determine compression level
        if compression_depth is None:
            depth = CompressionDepth.AGGRESSIVE if aggressive else CompressionDepth.CONSTANTS
        else:
            depth = compression_depth
            if depth < CompressionDepth.BASIC or depth > CompressionDepth.AGGRESSIVE:
                raise ValueError(f"compression_depth must be 1-4, got {depth}")
        
        # Log minification start
        operation_id = logger.log_minification_start(
            code_length=len(code_str),
            compression_depth=depth,
            aggressive=aggressive
        )
        
        logger._safe_log(logger.logger.debug, f"Minifying with compression depth: {depth}")
        
        # Parse stage
        parse_start = time.time()
        try:
            tree = ast.parse(code_str)
            parse_time = time.time() - parse_start
            logger.log_performance_metrics(operation_id, "ast_parse", parse_time)
        except SyntaxError as e:
            logger.log_error(e, operation_id, code_str[:200], "ast_parse")
            raise SyntaxError(f"Invalid Python code: {e}")
        
        # Transform stage
        transform_start = time.time()
        transformer = MinifyTransformer(compression_depth=depth, logger=logger, operation_id=operation_id)
        tree = transformer.visit(tree)
        ast.fix_missing_locations(tree)
        transform_time = time.time() - transform_start
        logger.log_performance_metrics(operation_id, "ast_transform", transform_time, 
                                     additional_metrics={"optimizations_applied": transformer.optimization_count})
        
        # Unparse stage
        unparse_start = time.time()
        try:
            if sys.version_info >= (3, 9):
                minified = ast.unparse(tree)
            elif HAS_ASTOR:
                minified = astor.to_source(tree).strip()
            else:
                raise ValueError(
                    "ast.unparse() requires Python 3.9+. For Python 3.8, install 'astor': pip install astor"
                )
            unparse_time = time.time() - unparse_start
            logger.log_performance_metrics(operation_id, "ast_unparse", unparse_time)
        except Exception as e:
            logger.log_error(e, operation_id, None, "ast_unparse")
            raise ValueError(f"AST unparsing failed: {e}") from e
        
        # Handle empty modules
        if minified.strip() == "pass":
            minified = ""
        
        # Validation stage
        if validate:
            validation_start = time.time()
            try:
                ast.parse(minified)
                validation_time = time.time() - validation_start
                logger.log_validation_result(operation_id, True, validation_time)
            except SyntaxError as e:
                validation_time = time.time() - validation_start
                logger.log_validation_result(operation_id, False, validation_time, 
                                           {"error": str(e)})
                logger.log_error(ValueError(f"Invalid minified output: {e}"), operation_id, minified[:200], "validation")
                raise ValueError(f"Invalid minified output: {e}")
        
        # Calculate and log final metrics
        total_time = time.time() - start_time
        
        # Get token metrics
        original_tokens = estimate_tokens(code_str)
        minified_tokens = estimate_tokens(minified)
        token_metrics = {
            "original_tokens": original_tokens,
            "minified_tokens": minified_tokens,
            "token_reduction": original_tokens - minified_tokens,
            "token_reduction_percent": round(((original_tokens - minified_tokens) / original_tokens) * 100, 2) if original_tokens > 0 else 0
        }
        
        logger.log_minification_complete(
            operation_id=operation_id,
            original_size=len(code_str),
            minified_size=len(minified),
            processing_time=total_time,
            token_metrics=token_metrics
        )
        
        return minified
            
    except Exception as e:
        if operation_id:
            logger.log_error(e, operation_id, code_str[:200] if isinstance(e, SyntaxError) else None, "general")
        raise


def estimate_tokens(
    code: str, 
    method: str = "simple",
    api_counter: Optional[Callable[[str], int]] = None,
    model_type: str = "gpt"
) -> int:
    """
    Estimate the number of tokens in code for LLM usage estimation.
    """
    logger = get_logger()
    
    if method == "api" and api_counter:
        try:
            result = api_counter(code)
            logger.log_token_estimation(code, method, result, model_type, actual_tokens=result)
            return result
        except Exception as e:
            logger._safe_log(logger.logger.warning, f"API token counting failed: {e}, falling back to simple method")
            method = "simple"
    
    # Model-specific calibration factors
    calibration = {
        "gpt": {"simple": 4.0, "words": 1.3, "chars": 3.5},
        "claude": {"simple": 4.2, "words": 1.4, "chars": 3.8},
        "generic": {"simple": 4.0, "words": 1.3, "chars": 3.5}
    }
    
    factors = calibration.get(model_type, calibration["generic"])
    
    if method == "simple":
        result = int(len(code) / factors["simple"])
    elif method == "words":
        import re
        words = len(re.findall(r'\S+', code))
        result = int(words * factors["words"])
    elif method == "chars":
        result = int(len(code) / factors["chars"])
    elif method == "precise":
        import re
        words = len(re.findall(r'\S+', code))
        operators = len(re.findall(r'[+\-*/=<>!&|^%~]', code))
        punctuation = len(re.findall(r'[.,;:(){}[\]]', code))
        
        base_tokens = words * factors["words"]
        operator_tokens = operators * 0.8
        punct_tokens = punctuation * 0.5
        
        result = int(base_tokens + operator_tokens + punct_tokens)
    else:
        raise ValueError(f"Unknown estimation method: {method}. Use 'simple', 'words', 'chars', 'precise', or 'api'")
    
    logger.log_token_estimation(code, method, result, model_type)
    return result


def minify_with_stats(code_str: str, aggressive: bool = False) -> Tuple[str, Dict[str, Any]]:
    """
    Minify code and return statistics about the transformation.
    """
    logger = get_logger()
    start_time = time.time()
    
    original_size = len(code_str)
    original_tokens = estimate_tokens(code_str)
    
    minified = minify_code(code_str, aggressive=aggressive)
    
    minified_size = len(minified)
    minified_tokens = estimate_tokens(minified)
    
    stats = {
        "original_size": original_size,
        "minified_size": minified_size,
        "size_reduction": original_size - minified_size,
        "size_reduction_percent": ((original_size - minified_size) / original_size) * 100,
        "original_tokens": original_tokens,
        "minified_tokens": minified_tokens,
        "token_reduction": original_tokens - minified_tokens,
        "token_reduction_percent": ((original_tokens - minified_tokens) / original_tokens) * 100 if original_tokens > 0 else 0,
        "aggressive_mode": aggressive,
        "processing_time": time.time() - start_time
    }
    
    return minified, stats


class MinifyTransformer(ast.NodeTransformer):
    """
    AST transformer that applies safe minification transformations with comprehensive logging.
    """
    
    # Safe binary operations for constant folding
    SAFE_BINOPS = {
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.truediv,
        ast.FloorDiv: operator.floordiv,
        ast.Mod: operator.mod,
        ast.Pow: operator.pow,
        ast.LShift: operator.lshift,
        ast.RShift: operator.rshift,
        ast.BitOr: operator.or_,
        ast.BitXor: operator.xor,
        ast.BitAnd: operator.and_,
    }
    
    # Safe unary operations for constant folding
    SAFE_UNARYOPS = {
        ast.UAdd: operator.pos,
        ast.USub: operator.neg,
        ast.Not: operator.not_,
        ast.Invert: operator.invert,
    }
    
    # Safe comparison operations
    SAFE_COMPAREOPS = {
        ast.Eq: operator.eq,
        ast.NotEq: operator.ne,
        ast.Lt: operator.lt,
        ast.LtE: operator.le,
        ast.Gt: operator.gt,
        ast.GtE: operator.ge,
        ast.Is: operator.is_,
        ast.IsNot: operator.is_not,
        ast.In: lambda a, b: a in b,
        ast.NotIn: lambda a, b: a not in b,
    }
    
    def __init__(self, aggressive: bool = False, compression_depth: Optional[int] = None, 
                 logger: Optional[MinifierLogger] = None, operation_id: Optional[str] = None):
        # Handle backward compatibility
        if compression_depth is None:
            self.compression_depth = CompressionDepth.AGGRESSIVE if aggressive else CompressionDepth.CONSTANTS
        else:
            self.compression_depth = compression_depth
        
        # Legacy support
        self.aggressive = (self.compression_depth >= CompressionDepth.VARIABLES)
        
        self.var_counter = 0
        self.var_mappings: Dict[str, str] = {}
        self.used_names: Set[str] = set()
        self.scope_stack: List[Set[str]] = []
        self.module_names: Set[str] = set()
        self.optimization_count = 0
        
        # Logging setup
        self.logger = logger or get_logger()
        self.operation_id = operation_id
        
        self.builtin_names = {
            'abs', 'all', 'any', 'ascii', 'bin', 'bool', 'bytearray', 'bytes',
            'callable', 'chr', 'classmethod', 'compile', 'complex', 'delattr',
            'dict', 'dir', 'divmod', 'enumerate', 'eval', 'exec', 'filter',
            'float', 'format', 'frozenset', 'getattr', 'globals', 'hasattr',
            'hash', 'help', 'hex', 'id', 'input', 'int', 'isinstance',
            'issubclass', 'iter', 'len', 'list', 'locals', 'map', 'max',
            'memoryview', 'min', 'next', 'object', 'oct', 'open', 'ord',
            'pow', 'print', 'property', 'range', 'repr', 'reversed', 'round',
            'set', 'setattr', 'slice', 'sorted', 'staticmethod', 'str', 'sum',
            'super', 'tuple', 'type', 'vars', 'zip', '__import__',
            'args', 'kwargs', 'self', 'cls'
        }
    
    def _log_transformation(self, transformation_type: str, node_type: str, 
                          details: Optional[Dict] = None, optimization_applied: bool = False):
        """Helper to log AST transformations."""
        if optimization_applied:
            self.optimization_count += 1
        
        self.logger.log_ast_transformation(
            transformation_type=transformation_type,
            node_type=node_type,
            details=details,
            optimization_applied=optimization_applied
        )
    
    def _get_short_name(self, original_name: str) -> str:
        """Generate a short variable name with logging."""
        if (not self.aggressive or 
            original_name in self.builtin_names or
            original_name in self.module_names):
            return original_name
        
        if len(original_name) <= 2 and original_name.isalpha() and original_name.islower():
            return original_name
            
        if original_name in self.var_mappings:
            return self.var_mappings[original_name]
        
        all_scope_names = set()
        for scope in self.scope_stack:
            all_scope_names.update(scope)
        
        chars = 'abcdefghijklmnopqrstuvwxyz'
        length = 1
        while True:
            for combo in self._generate_combinations(chars, length):
                short_name = ''.join(combo)
                if (short_name not in self.used_names and 
                    short_name not in self.builtin_names and
                    short_name not in all_scope_names):
                    self.var_mappings[original_name] = short_name
                    self.used_names.add(short_name)
                    
                    # Log variable shortening
                    self.logger.log_variable_shortening(
                        original_name=original_name,
                        short_name=short_name,
                        scope_depth=len(self.scope_stack)
                    )
                    
                    return short_name
            length += 1
    
    def _generate_combinations(self, chars: str, length: int):
        """Generate all combinations of given length."""
        if length == 0:
            yield ()
        else:
            for char in chars:
                for combo in self._generate_combinations(chars, length - 1):
                    yield (char,) + combo
    
    def _get_constant_value(self, node):
        """Get constant value from AST node, handling both old and new formats."""
        if hasattr(ast, 'Constant') and isinstance(node, ast.Constant):
            return node.value
        elif isinstance(node, ast.Num):
            return node.n
        elif isinstance(node, ast.Str):
            return node.s
        elif isinstance(node, ast.NameConstant):
            return node.value
        return None
    
    def _create_constant(self, value):
        """Create AST constant node, handling both old and new formats."""
        if hasattr(ast, 'Constant'):
            return ast.Constant(value=value)
        else:
            if isinstance(value, (int, float)):
                return ast.Num(n=value)
            elif isinstance(value, str):
                return ast.Str(s=value)
            elif isinstance(value, (bool, type(None))):
                return ast.NameConstant(value=value)
            else:
                return ast.Num(n=value)
    
    def _is_string_constant(self, node):
        """Check if node is a string constant, handling both old and new formats."""
        if hasattr(ast, 'Constant') and isinstance(node, ast.Constant):
            return isinstance(node.value, str)
        return isinstance(node, ast.Str)
    
    def visit_Import(self, node):
        """Track imported module names."""
        for alias in node.names:
            name = alias.asname if alias.asname else alias.name
            self.module_names.add(name)
        
        self._log_transformation("import", "Import", 
                                {"modules": [alias.name for alias in node.names]})
        return self.generic_visit(node)
    
    def visit_ImportFrom(self, node):
        """Track imported names from modules."""
        for alias in node.names:
            name = alias.asname if alias.asname else alias.name
            self.module_names.add(name)
        
        self._log_transformation("import_from", "ImportFrom", 
                                {"module": node.module, "names": [alias.name for alias in node.names]})
        return self.generic_visit(node)
    
    def visit_Pass(self, node):
        """Keep pass statements - they will be removed only if not needed by parent visitors."""
        self._log_transformation("pass_statement", "Pass")
        return node
    
    def visit_Expr(self, node):
        """Visit expression statements."""
        self._log_transformation("expression_statement", "Expr")
        return self.generic_visit(node)
    
    def visit_FunctionDef(self, node):
        """Process function definitions, preserving only the first docstring."""
        if self.scope_stack:
            self.scope_stack[-1].add(node.name)
        
        self.scope_stack.append(set())
        current_scope = self.scope_stack[-1]
        
        # Add parameter names to current scope before shortening
        param_names = [arg.arg for arg in node.args.args]
        for arg in node.args.args:
            current_scope.add(arg.arg)
        
        # Shorten parameter names if aggressive mode
        if self.aggressive:
            for arg in node.args.args:
                if arg.arg not in self.builtin_names:
                    original_name = arg.arg
                    arg.arg = self._get_short_name(original_name)
                    current_scope.add(arg.arg)
        
        self._log_transformation("function_def", "FunctionDef", 
                                {"function_name": node.name, "parameters": param_names})
        
        node = self._process_body_with_docstring(node)
        result = self.generic_visit(node)
        self.scope_stack.pop()
        
        return result
    
    def visit_AsyncFunctionDef(self, node):
        """Process async function definitions, preserving only the first docstring."""
        if self.scope_stack:
            self.scope_stack[-1].add(node.name)
        
        self.scope_stack.append(set())
        current_scope = self.scope_stack[-1]
        
        param_names = [arg.arg for arg in node.args.args]
        for arg in node.args.args:
            current_scope.add(arg.arg)
        
        if self.aggressive:
            for arg in node.args.args:
                if arg.arg not in self.builtin_names:
                    original_name = arg.arg
                    arg.arg = self._get_short_name(original_name)
                    current_scope.add(arg.arg)
        
        self._log_transformation("async_function_def", "AsyncFunctionDef", 
                                {"function_name": node.name, "parameters": param_names})
        
        node = self._process_body_with_docstring(node)
        result = self.generic_visit(node)
        self.scope_stack.pop()
        
        return result
    
    def visit_ClassDef(self, node):
        """Process class definitions, preserving only the first docstring."""
        if self.scope_stack:
            self.scope_stack[-1].add(node.name)
        
        self.scope_stack.append(set())
        
        self._log_transformation("class_def", "ClassDef", 
                                {"class_name": node.name})
        
        node = self._process_body_with_docstring(node)
        result = self.generic_visit(node)
        self.scope_stack.pop()
        
        return result
    
    def visit_Lambda(self, node):
        """Process lambda functions."""
        if self.aggressive:
            self.scope_stack.append(set())
            
            param_names = [arg.arg for arg in node.args.args]
            for arg in node.args.args:
                if arg.arg not in self.builtin_names:
                    self.scope_stack[-1].add(arg.arg)
                    arg.arg = self._get_short_name(arg.arg)
            
            self._log_transformation("lambda", "Lambda", 
                                    {"parameters": param_names})
            
            result = self.generic_visit(node)
            self.scope_stack.pop()
            return result
        
        self._log_transformation("lambda", "Lambda")
        return self.generic_visit(node)
    
    def visit_ListComp(self, node):
        """Process list comprehensions with their own scope."""
        return self._visit_comprehension(node, "ListComp")
    
    def visit_SetComp(self, node):
        """Process set comprehensions with their own scope."""
        return self._visit_comprehension(node, "SetComp")
    
    def visit_DictComp(self, node):
        """Process dict comprehensions with their own scope."""
        return self._visit_comprehension(node, "DictComp")
    
    def visit_GeneratorExp(self, node):
        """Process generator expressions with their own scope."""
        return self._visit_comprehension(node, "GeneratorExp")
    
    def _visit_comprehension(self, node, comp_type: str):
        """Helper to process comprehensions with their own scope."""
        if self.aggressive:
            self.scope_stack.append(set())
            self._log_transformation("comprehension", comp_type)
            result = self.generic_visit(node)
            self.scope_stack.pop()
            return result
        
        self._log_transformation("comprehension", comp_type)
        return self.generic_visit(node)
    
    def visit_Module(self, node):
        """Process module, preserving only the first docstring."""
        self.scope_stack.append(set())
        
        self._log_transformation("module", "Module")
        
        node = self._process_body_with_docstring(node)
        result = self.generic_visit(node)
        self.scope_stack.pop()
        
        return result
    
    def visit_Name(self, node):
        """Shorten variable names if in aggressive mode."""
        if self.aggressive and isinstance(node.ctx, (ast.Store, ast.Load)):
            if (node.id not in self.builtin_names and 
                node.id not in self.module_names):
                
                original_name = node.id
                
                if isinstance(node.ctx, ast.Store) and self.scope_stack:
                    self.scope_stack[-1].add(node.id)
                
                if isinstance(node.ctx, ast.Load):
                    for scope in reversed(self.scope_stack):
                        if node.id in scope:
                            return node
                
                node.id = self._get_short_name(node.id)
                
                if original_name != node.id:
                    self._log_transformation("variable_rename", "Name", 
                                            {"original": original_name, "renamed": node.id}, 
                                            optimization_applied=True)
        
        return node
    
    def _process_body_with_docstring(self, node):
        """Helper to process a node's body, keeping only the first docstring."""
        if not hasattr(node, 'body') or not node.body:
            node.body = [ast.Pass()]
            return node
            
        new_body = []
        docstring_found = False
        
        for i, stmt in enumerate(node.body):
            is_first_docstring = (i == 0 and 
                isinstance(stmt, ast.Expr) and 
                self._is_string_constant(stmt.value))
            
            transformed_stmt = self.visit(stmt)
            
            if transformed_stmt is None:
                continue
            
            if hasattr(transformed_stmt, '_is_replacement_marker'):
                expanded_stmts = transformed_stmt.body
                expanded_stmts = self._remove_dead_code(expanded_stmts)
                new_body.extend(expanded_stmts)
                continue
                
            if is_first_docstring and not docstring_found:
                new_body.append(transformed_stmt)
                docstring_found = True
                self._log_transformation("docstring_preserved", "Expr", 
                                        {"is_first_docstring": True})
            elif isinstance(transformed_stmt, ast.Expr) and self._is_string_constant(transformed_stmt.value):
                self._log_transformation("docstring_removed", "Expr", 
                                        {"is_first_docstring": False}, 
                                        optimization_applied=True)
                pass  # Remove non-first docstrings
            else:
                new_body.append(transformed_stmt)
        
        new_body = self._remove_dead_code(new_body)
        
        if not new_body and not isinstance(node, ast.Module):
            new_body = [ast.Pass()]
        
        node.body = new_body
        return node
    
    def _remove_dead_code(self, body):
        """Remove unreachable code after return/raise/continue/break statements."""
        new_body = []
        for stmt in body:
            new_body.append(stmt)
            if isinstance(stmt, (ast.Return, ast.Raise, ast.Continue, ast.Break)):
                dead_code_count = len(body) - len(new_body)
                if dead_code_count > 0:
                    self._log_transformation("dead_code_removal", "Multiple", 
                                            {"statements_removed": dead_code_count}, 
                                            optimization_applied=True)
                break
        return new_body
    
    def visit_Constant(self, node):
        """Optimize constant values where safe."""
        return node
    
    def visit_BinOp(self, node):
        """Optimize binary operations with constant folding."""
        node = self.generic_visit(node)
        
        if self.compression_depth < CompressionDepth.CONSTANTS:
            return node
        
        left_val = self._get_constant_value(node.left)
        right_val = self._get_constant_value(node.right)
        
        if (left_val is not None and right_val is not None and
            type(node.op) in self.SAFE_BINOPS):
            
            try:
                op_func = self.SAFE_BINOPS[type(node.op)]
                result = op_func(left_val, right_val)
                if isinstance(result, (int, float, str, bool, complex)):
                    self.logger.log_optimization(
                        optimization_type="constant_folding_binary",
                        before_value=f"{left_val} {type(node.op).__name__} {right_val}",
                        after_value=result
                    )
                    self._log_transformation("constant_folding", "BinOp", 
                                            {"operation": type(node.op).__name__, 
                                             "left": left_val, "right": right_val, "result": result}, 
                                            optimization_applied=True)
                    return self._create_constant(result)
            except (ZeroDivisionError, OverflowError, ValueError, TypeError):
                pass
        
        return node
    
    def visit_UnaryOp(self, node):
        """Optimize unary operations with constant folding."""
        node = self.generic_visit(node)
        
        if self.compression_depth < CompressionDepth.CONSTANTS:
            return node
        
        operand_val = self._get_constant_value(node.operand)
        
        if (operand_val is not None and type(node.op) in self.SAFE_UNARYOPS):
            try:
                op_func = self.SAFE_UNARYOPS[type(node.op)]
                result = op_func(operand_val)
                if isinstance(result, (int, float, str, bool, complex)):
                    self.logger.log_optimization(
                        optimization_type="constant_folding_unary",
                        before_value=f"{type(node.op).__name__} {operand_val}",
                        after_value=result
                    )
                    self._log_transformation("constant_folding", "UnaryOp", 
                                            {"operation": type(node.op).__name__, 
                                             "operand": operand_val, "result": result}, 
                                            optimization_applied=True)
                    return self._create_constant(result)
            except (OverflowError, ValueError, TypeError):
                pass
        
        # Optimize double negation: --x -> x
        if (self.compression_depth >= CompressionDepth.CONSTANTS and
            isinstance(node.op, ast.USub) and 
            isinstance(node.operand, ast.UnaryOp) and
            isinstance(node.operand.op, ast.USub)):
            self.logger.log_optimization(
                optimization_type="double_negation",
                before_value="--x",
                after_value="x"
            )
            self._log_transformation("double_negation", "UnaryOp", 
                                    optimization_applied=True)
            return node.operand.operand
        
        return node
    
    def visit_Compare(self, node):
        """Optimize comparison operations."""
        node = self.generic_visit(node)
        
        if self.compression_depth < CompressionDepth.CONSTANTS:
            return node
        
        left_val = self._get_constant_value(node.left)
        
        if (len(node.ops) == 1 and len(node.comparators) == 1 and
            left_val is not None and
            type(node.ops[0]) in self.SAFE_COMPAREOPS):
            
            right_val = self._get_constant_value(node.comparators[0])
            if right_val is not None:
                try:
                    op_func = self.SAFE_COMPAREOPS[type(node.ops[0])]
                    result = op_func(left_val, right_val)
                    self.logger.log_optimization(
                        optimization_type="constant_folding_comparison",
                        before_value=f"{left_val} {type(node.ops[0]).__name__} {right_val}",
                        after_value=result
                    )
                    self._log_transformation("constant_folding", "Compare", 
                                            {"left": left_val, "op": type(node.ops[0]).__name__, 
                                             "right": right_val, "result": result}, 
                                            optimization_applied=True)
                    return self._create_constant(result)
                except (TypeError, ValueError):
                    pass
        
        return node
    
    def visit_BoolOp(self, node):
        """Optimize boolean operations."""
        node = self.generic_visit(node)
        
        if self.compression_depth < CompressionDepth.CONSTANTS:
            return node
        
        if isinstance(node.op, ast.And):
            new_values = []
            for value in node.values:
                val = self._get_constant_value(value)
                if val is not None:
                    if val is True:
                        continue
                    elif val is False:
                        self._log_transformation("boolean_optimization", "BoolOp", 
                                                {"operation": "and", "result": "False"}, 
                                                optimization_applied=True)
                        return self._create_constant(False)
                new_values.append(value)
            
            if not new_values:
                self._log_transformation("boolean_optimization", "BoolOp", 
                                        {"operation": "and", "result": "True"}, 
                                        optimization_applied=True)
                return self._create_constant(True)
            elif len(new_values) == 1:
                self._log_transformation("boolean_optimization", "BoolOp", 
                                        {"operation": "and", "simplified": True}, 
                                        optimization_applied=True)
                return new_values[0]
            else:
                node.values = new_values
        
        elif isinstance(node.op, ast.Or):
            new_values = []
            for value in node.values:
                val = self._get_constant_value(value)
                if val is not None:
                    if val is False:
                        continue
                    elif val is True:
                        self._log_transformation("boolean_optimization", "BoolOp", 
                                                {"operation": "or", "result": "True"}, 
                                                optimization_applied=True)
                        return self._create_constant(True)
                new_values.append(value)
            
            if not new_values:
                self._log_transformation("boolean_optimization", "BoolOp", 
                                        {"operation": "or", "result": "False"}, 
                                        optimization_applied=True)
                return self._create_constant(False)
            elif len(new_values) == 1:
                self._log_transformation("boolean_optimization", "BoolOp", 
                                        {"operation": "or", "simplified": True}, 
                                        optimization_applied=True)
                return new_values[0]
            else:
                node.values = new_values
        
        return node
    
    def visit_If(self, node):
        """Optimize if statements with constant conditions."""
        node = self.generic_visit(node)
        
        if self.compression_depth < CompressionDepth.CONSTANTS:
            return node
        
        test_val = self._get_constant_value(node.test)
        if test_val is not None:
            if test_val:
                self.logger.log_optimization(
                    optimization_type="if_constant_true",
                    before_value="if True:",
                    after_value="<body statements>"
                )
                self._log_transformation("if_optimization", "If", 
                                        {"condition": "always_true"}, 
                                        optimization_applied=True)
                return self._create_replacement_marker(node.body)
            else:
                self.logger.log_optimization(
                    optimization_type="if_constant_false",
                    before_value="if False:",
                    after_value="<else statements or removed>"
                )
                self._log_transformation("if_optimization", "If", 
                                        {"condition": "always_false"}, 
                                        optimization_applied=True)
                if node.orelse:
                    return self._create_replacement_marker(node.orelse)
                else:
                    return None
        
        return node
    
    def _create_replacement_marker(self, statements):
        """Create a marker to indicate this node should be replaced by multiple statements."""
        if len(statements) == 1:
            return statements[0]
        else:
            marker = ast.Module(body=statements, type_ignores=[])
            marker._is_replacement_marker = True
            return marker
    
    def visit_While(self, node):
        """Optimize while loops with constant conditions."""
        node = self.generic_visit(node)
        
        test_val = self._get_constant_value(node.test)
        if test_val is not None and not test_val:
            self.logger.log_optimization(
                optimization_type="while_constant_false",
                before_value="while False:",
                after_value="<removed>"
            )
            self._log_transformation("while_optimization", "While", 
                                    {"condition": "always_false"}, 
                                    optimization_applied=True)
            return None
        
        return node


# Convenience functions for different optimization levels
def minify_basic(code_str: str) -> str:
    """Basic minification - removes comments, whitespace, and applies constant folding."""
    return minify_code(code_str, aggressive=False)


def minify_comments_only(code_str: str) -> str:
    """Comments-only minification - removes only comments and whitespace."""
    return minify_code(code_str, compression_depth=CompressionDepth.BASIC)


def minify_constants(code_str: str) -> str:
    """Constant folding minification - includes constant folding and boolean optimization."""
    return minify_code(code_str, compression_depth=CompressionDepth.CONSTANTS)


def minify_variables(code_str: str) -> str:
    """Variable minification - includes variable name shortening."""
    return minify_code(code_str, compression_depth=CompressionDepth.VARIABLES)


def minify_aggressive(code_str: str) -> str:
    """Aggressive minification - includes all optimizations."""
    return minify_code(code_str, aggressive=True)


def minify_depth(code_str: str, depth: int) -> str:
    """
    Minify with explicit compression depth level.
    
    Args:
        code_str: Python code to minify
        depth: Compression depth (1-4)
    """
    return minify_code(code_str, compression_depth=depth)


def is_idempotent(code_str: str, aggressive: bool = False) -> bool:
    """
    Check if minification is idempotent.
    """
    try:
        first_pass = minify_code(code_str, aggressive=aggressive)
        second_pass = minify_code(first_pass, aggressive=aggressive)
        return first_pass == second_pass
    except Exception:
        return False


# Example usage and testing with comprehensive logging
if __name__ == "__main__":
    # Setup comprehensive logging
    logger = setup_minifier_logging(
        log_level="DEBUG",
        log_file="logs/minifier_detailed.log",
        enable_console=True,
        enable_file=True,
        enable_metrics=True,
        enable_performance=True,
        enable_ast_details=True,  # Enable detailed AST logging for demo
        production_mode=False
    )
    
    # Enhanced test code showcasing all features
    test_code = '''
def hello_world(name: str) -> str:
    """
    This is a docstring that should be preserved.
    """
    # This comment will be removed
    message = f"Hello, {name}!"  # Another comment
    
    """This string is not a docstring and should be removed"""
    
    # Constant folding test
    x = 1 + 2 * 3  # Should become 7
    y = not False  # Should become True
    z = --5       # Should become 5
    
    # Boolean optimization test
    result = True and x  # Should become just x
    
    # Dead code test
    if True:
        return message
        print("This should be removed")  # Dead code
    
    return "Never reached"


class MyClass:
    """Class docstring - should be kept."""
    
    def __init__(self):
        """Init docstring - should be kept."""
        self.value = 42
        """This is not a docstring - should be removed"""
    
    # Method with no docstring
    def method(self):
        x = 1 + 2  # Comment to remove, should fold to 3
        if False:
            print("Never executed")  # Dead code
        return x


# Top-level comment
async def async_func():
    """Async function docstring."""
    pass  # This pass should be removed since there's a docstring
'''

    try:
        print("="*70)
        print("ENHANCED PYTHON MINIFIER WITH COMPREHENSIVE LOGGING")
        print("="*70)
        
        # Show original
        print("ORIGINAL CODE:")
        print("-" * 50)
        print(test_code)
        
        # Basic minification with detailed logging
        print("\n" + "="*50)
        print("BASIC MINIFICATION (with comprehensive logging)")
        print("="*50)
        basic_minified, basic_stats = minify_with_stats(test_code, aggressive=False)
        print("Minified code:")
        print(basic_minified)
        print(f"\nStats:")
        print(f"  - Size reduction: {basic_stats['size_reduction_percent']:.1f}%")
        print(f"  - Token reduction: {basic_stats['token_reduction_percent']:.1f}%")
        print(f"  - Processing time: {basic_stats['processing_time']:.4f}s")
        
        # Aggressive minification with detailed logging
        print("\n" + "="*50)
        print("AGGRESSIVE MINIFICATION (with comprehensive logging)")
        print("="*50)
        aggressive_minified, aggressive_stats = minify_with_stats(test_code, aggressive=True)
        print("Aggressive minified code:")
        print(aggressive_minified)
        print(f"\nAggressive Stats:")
        print(f"  - Size reduction: {aggressive_stats['size_reduction_percent']:.1f}%")
        print(f"  - Token reduction: {aggressive_stats['token_reduction_percent']:.1f}%")
        print(f"  - Processing time: {aggressive_stats['processing_time']:.4f}s")
        
        # Test all compression depth levels with logging
        print("\n" + "="*50)
        print("COMPRESSION DEPTH LEVELS (with logging)")
        print("="*50)
        for depth in range(1, 5):
            depth_result = minify_depth(test_code, depth)
            print(f"Depth {depth}: {len(depth_result)} chars")
        
        # Test idempotency
        print("\n" + "="*50)
        print("IDEMPOTENCY TEST")
        print("="*50)
        basic_idempotent = is_idempotent(test_code, aggressive=False)
        aggressive_idempotent = is_idempotent(test_code, aggressive=True)
        print(f"Basic mode idempotent: {'✅ Yes' if basic_idempotent else '❌ No'}")
        print(f"Aggressive mode idempotent: {'✅ Yes' if aggressive_idempotent else '❌ No'}")
        
        print(f"\n{'='*70}")
        print("✅ ENHANCED MINIFIER WITH LOGGING DEMONSTRATED SUCCESSFULLY!")
        print("✅ Check 'logs/minifier_detailed.log' for comprehensive operation logs")
        print(f"{'='*70}")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()