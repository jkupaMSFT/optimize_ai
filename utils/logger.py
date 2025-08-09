# ===== utils/logger.py =====
import logging
import sys
from typing import Any, Dict, Optional
from datetime import datetime
from pathlib import Path
import os
from logging.handlers import RotatingFileHandler
import json

class JsonFormatter(logging.Formatter):
    """Custom JSON formatter for structured logging."""
    def format(self, record):
        log_object = {
            "timestamp": datetime.fromtimestamp(record.created).isoformat(),
            "level": record.levelname,
            "name": record.name,
            "message": record.msg,
            "extra": record.__dict__.get('extra', {})
        }
        return json.dumps(log_object)

class MinifierLogger:
    """Enhanced logger for Optimize AI with rotation and structured logging."""
    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(MinifierLogger, cls).__new__(cls)
        return cls._instance

    def __init__(self, log_path: Optional[Path] = None, log_level: Optional[str] = None):
        if hasattr(self, 'initialized') and self.initialized:
            return
        self.logger = logging.getLogger("optimize_ai")
        
        # Set log level from env var or argument, default to INFO
        level = log_level or os.getenv('OPTIMIZE_AI_LOG_LEVEL', 'INFO').upper()
        self.logger.setLevel(getattr(logging, level, logging.INFO))
        
        # Console handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        console_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        console_handler.setFormatter(console_formatter)
        self.logger.addHandler(console_handler)
        
        # File handler with rotation
        log_path = log_path or Path(os.getenv('OPTIMIZE_AI_LOG_PATH', '.optimize_ai/app.log'))
        log_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            log_path,
            maxBytes=10*1024*1024,  # 10MB
            backupCount=5  # Keep 5 backups
        )
        file_handler.setLevel(logging.DEBUG)
        
        # Use JSON formatter if env var set
        if os.getenv('OPTIMIZE_AI_LOG_FORMAT', 'text').lower() == 'json':
            file_formatter = JsonFormatter()
        else:
            file_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(name)s - %(message)s')
        
        file_handler.setFormatter(file_formatter)
        self.logger.addHandler(file_handler)
        
        self.initialized = True

    def info(self, msg: str, extra: Optional[Dict[str, Any]] = None):
        self.logger.info(msg, extra=extra or {})

    def error(self, msg: str, extra: Optional[Dict[str, Any]] = None):
        self.logger.error(msg, extra=extra or {})

    def debug(self, msg: str, extra: Optional[Dict[str, Any]] = None):
        self.logger.debug(msg, extra=extra or {})

    def warning(self, msg: str, extra: Optional[Dict[str, Any]] = None):
        self.logger.warning(msg, extra=extra or {})

    def critical(self, msg: str, extra: Optional[Dict[str, Any]] = None):
        self.logger.critical(msg, extra=extra or {})

    def log_error(self, msg: str = "", extra: Optional[Dict[str, Any]] = None, **kwargs):
        """Alias for error method for backward compatibility."""
        # Handle the 'error' keyword argument and merge it into extra
        if 'error' in kwargs:
            if extra is None:
                extra = {}
            extra['error'] = kwargs['error']
        # If no message provided, try to get it from kwargs or extra
        if not msg:
            msg = kwargs.get('message', extra.get('message', 'Error occurred') if extra else 'Error occurred')
        self.error(msg, extra)

    def log_minification_start(self, msg: str = "Minification started", **kwargs):
        """Log minification start with optional metadata."""
        extra = kwargs if kwargs else {}
        self.info(msg, extra)
    
    def log_minification_complete(self, msg: str = "Minification completed", **kwargs):
        """Log minification completion with optional metadata."""
        extra = kwargs if kwargs else {}
        self.info(msg, extra)

    def log_ast_transformation(self, msg: str = "AST transformation", **kwargs):
        """Log AST transformation with optional metadata."""
        extra = kwargs if kwargs else {}
        self.info(msg, extra)

    def log_optimization(self, msg: str = "Optimization", **kwargs):
        """Log optimization with optional metadata."""
        extra = kwargs if kwargs else {}
        self.info(msg, extra)

    def log_token_metrics(self, data: Dict[str, Any]):
        """Log token metrics data."""
        self.info("Token metrics", data)

    def _safe_log(self, log_method, message: str, extra: Optional[Dict[str, Any]] = None):
        """Safe logging method that handles exceptions."""
        try:
            if extra:
                log_method(message, extra=extra)
            else:
                log_method(message)
        except Exception as e:
            # Fallback to basic logging if extra data causes issues
            try:
                log_method(f"{message} (logging error: {e})")
            except Exception:
                # Ultimate fallback - just print
                print(f"LOGGING ERROR: {message}")


def get_logger(name: str = "optimize_ai") -> MinifierLogger:
    """Get a logger instance."""
    return MinifierLogger()


def setup_minifier_logging(
    log_level: str = "INFO",
    log_file: Optional[str] = None,
    enable_console: bool = True,
    enable_file: bool = True,
    production_mode: bool = False,
    **kwargs  # Accept any additional arguments and ignore them
) -> MinifierLogger:
    """Setup enhanced logging for the minifier with comprehensive options."""
    log_path = Path(log_file) if log_file else None
    return MinifierLogger(log_path=log_path, log_level=log_level)


def estimate_tokens(text: str, method: str = "simple", **kwargs) -> int:
    """Estimate token count using simple heuristic."""
    # Ignore the method parameter for now and use simple estimation
    return int(len(text.split()) * 1.3)  # Rough approximation, return as int


def minify_with_otpm_tracking(code: str, remaining_pct: float = 100.0, **kwargs) -> Dict[str, Any]:
    """
    Minify code with OTPM (Optimize Token Per Message) tracking.
    This is a placeholder implementation for compatibility.
    """
    try:
        from input_optimizer.engine.minifier import minify_code
        minified = minify_code(code)
        original_tokens = estimate_tokens(code)
        minified_tokens = estimate_tokens(minified)
        
        return {
            "minified_code": minified,
            "original_tokens": original_tokens,
            "minified_tokens": minified_tokens,
            "compression_type": "standard",
            "otpm_status": "tracked",
            "remaining_pct": remaining_pct,
            "token_reduction_percent": ((original_tokens - minified_tokens) / original_tokens * 100) if original_tokens > 0 else 0
        }
    except Exception as e:
        return {
            "minified_code": code,
            "original_tokens": estimate_tokens(code),
            "minified_tokens": estimate_tokens(code),
            "compression_type": "none",
            "otpm_status": "error",
            "remaining_pct": remaining_pct,
            "token_reduction_percent": 0,
            "error": str(e)
        }


def setup_logger(name: str = "optimize_ai", log_level: str = "INFO", log_file: Optional[str] = None) -> logging.Logger:
    """
    Setup a logger instance for backwards compatibility.
    Returns a standard Python logger.
    """
    logger = logging.getLogger(name)
    
    # Avoid adding handlers multiple times
    if logger.handlers:
        return logger
        
    # Set log level
    logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(name)s - %(message)s')
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)
    
    # File handler if specified
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            log_path,
            maxBytes=10*1024*1024,  # 10MB
            backupCount=5  # Keep 5 backups
        )
        file_handler.setLevel(logging.DEBUG)
        file_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(name)s - %(message)s')
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)
    
    return logger


def get_compression_recommendation(length: int) -> str:
    """Get compression recommendation based on input length."""
    if length < 1000:
        return "basic"
    elif length < 5000:
        return "standard"
    elif length < 20000:
        return "aggressive"
    else:
        return "summarize"