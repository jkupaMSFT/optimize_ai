from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, validator
from typing import Optional, Dict, Any
import time
import ast
from datetime import datetime
import uvicorn

# Import our enhanced minifier with logging
from engine.minifier import (
    minify_code, 
    minify_with_stats, 
    estimate_tokens,
    CompressionDepth
)

# Import enhanced logger functions
from utils.logger import (
    minify_with_otpm_tracking,
    get_compression_recommendation,
    get_logger
)

# Import translators
from engine.translators.sudo_lang_translator import (
    python_to_sudolang,
    translate_with_stats as sudo_translate_with_stats
)
from engine.translators.synth_lang_translator import (
    enhanced_python_to_synthlang,
    python_to_synthlang_node_map,
    python_to_synthlang
)

# Import minifier for chaining
from engine.minifier import minify_depth

# Import our logging setup
from utils.logger import setup_minifier_logging, get_logger

# Import adapter for tier-based compression
from engine.adapter import adapt_compression

# Initialize FastAPI app
app = FastAPI(
    title="Python Code Optimization & Translation API",
    description="High-performance Python code minification and translation service with comprehensive logging and metrics. Supports Python-to-SudoLang and Python-to-SynthLang translations.",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Setup comprehensive logging for both FastAPI and minifier
fastapi_logger = setup_minifier_logging(
    log_level="INFO",
    log_file="logs/fastapi_minifier.log",
    enable_console=True,
    enable_file=True,
    production_mode=True
)

# Setup minifier-specific logging
minifier_logger = setup_minifier_logging(
    log_level="INFO",
    log_file="logs/minifier_operations.log",
    enable_console=False,  # Avoid duplicate console logs
    enable_file=True,
    enable_metrics=True,
    enable_performance=True,
    enable_ast_details=False,  # Keep AST details off for production
    production_mode=True
)

# Request/Response Models
class MinifyRequest(BaseModel):
    code: str = Field(..., description="Python source code to minify", min_length=1, max_length=1000000)
    aggressive: Optional[bool] = Field(False, description="Enable aggressive optimizations (variable name shortening)")
    validate_output: Optional[bool] = Field(True, description="Validate minified output by re-parsing")
    compression_depth: Optional[int] = Field(None, description="Compression level (1-4): 1=basic, 2=constants, 3=variables, 4=aggressive")
    
    @validator('compression_depth')
    def validate_compression_depth(cls, v):
        if v is not None and (v < 1 or v > 4):
            raise ValueError('compression_depth must be between 1 and 4')
        return v
    
    @validator('code')
    def validate_code_not_empty(cls, v):
        if not v.strip():
            raise ValueError('code cannot be empty or whitespace only')
        return v

class MinifyResponse(BaseModel):
    minified: str = Field(..., description="Minified Python code")
    estimated_tokens: int = Field(..., description="Estimated token count using len(minified)//4")
    original_size: int = Field(..., description="Original code size in characters")
    minified_size: int = Field(..., description="Minified code size in characters")
    size_reduction_percent: float = Field(..., description="Percentage reduction in size")
    processing_time_ms: float = Field(..., description="Processing time in milliseconds")
    compression_depth_used: int = Field(..., description="Compression depth level used")

class OTPMMinifyRequest(BaseModel):
    code: str = Field(..., description="Python source code to minify", min_length=1, max_length=1000000)
    remaining_pct: Optional[float] = Field(100.0, description="Percentage of remaining tokens in rate limit window", ge=0.0, le=100.0)
    compression_type: Optional[str] = Field("auto", description="Compression type: 'auto', 'minimal', 'standard', 'aggressive', 'emergency'")
    model_type: Optional[str] = Field("gpt-4", description="Model type for token counting: 'gpt-4', 'gpt-3.5-turbo', 'claude'")
    rate_limit_headers: Optional[Dict[str, str]] = Field(None, description="Rate limit headers from upstream API")
    
    @validator('code')
    def validate_code_not_empty(cls, v):
        if not v.strip():
            raise ValueError('code cannot be empty or whitespace only')
        return v
    
    @validator('compression_type')
    def validate_compression_type(cls, v):
        valid_types = ['auto', 'minimal', 'standard', 'aggressive', 'emergency']
        if v not in valid_types:
            raise ValueError(f'compression_type must be one of: {valid_types}')
        return v

class OTPMMinifyResponse(BaseModel):
    minified: str = Field(..., description="Minified Python code")
    estimated_tokens: int = Field(..., description="Estimated token count using tiktoken")
    original_tokens: int = Field(..., description="Original code token count")
    token_reduction_percent: float = Field(..., description="Percentage reduction in tokens")
    compression_type_used: str = Field(..., description="Compression type applied")
    otpm_status: str = Field(..., description="OTPM status: 'safe', 'warning', 'critical', 'summarized'")
    remaining_pct: float = Field(..., description="Remaining tokens percentage")
    processing_time_ms: float = Field(..., description="Processing time in milliseconds")
    operation_id: str = Field(..., description="Unique operation identifier for tracking")

class MinifyStatsResponse(BaseModel):
    minified: str = Field(..., description="Minified Python code")
    estimated_tokens: int = Field(..., description="Estimated token count using len(minified)//4")
    stats: Dict[str, Any] = Field(..., description="Detailed minification statistics")

class HealthResponse(BaseModel):
    status: str = Field(..., description="Service health status")
    timestamp: str = Field(..., description="Current timestamp")
    version: str = Field(..., description="API version")
    uptime_seconds: float = Field(..., description="Service uptime in seconds")

class ErrorResponse(BaseModel):
    error: str = Field(..., description="Error type")
    message: str = Field(..., description="Error message")
    timestamp: str = Field(..., description="Error timestamp")
    request_id: Optional[str] = Field(None, description="Request ID for tracing")

# Translation Request/Response Models
class TranslateRequest(BaseModel):
    code: str = Field(..., description="Python source code to translate", min_length=1, max_length=1000000)
    compact: Optional[bool] = Field(False, description="Enable compact output (SynthLang only)")
    indent_size: Optional[int] = Field(2, description="Indentation size for formatted output")
    
    @validator('code')
    def validate_code_not_empty(cls, v):
        if not v.strip():
            raise ValueError('code cannot be empty or whitespace only')
        return v
    
    @validator('indent_size')
    def validate_indent_size(cls, v):
        if v is not None and (v < 1 or v > 8):
            raise ValueError('indent_size must be between 1 and 8')
        return v

class SudoLangResponse(BaseModel):
    translated: str = Field(..., description="SudoLang translated code")
    original_size: int = Field(..., description="Original code size in characters")
    translated_size: int = Field(..., description="Translated code size in characters")
    processing_time_ms: float = Field(..., description="Processing time in milliseconds")
    ast_nodes_processed: int = Field(..., description="Number of AST nodes processed")

class SynthLangResponse(BaseModel):
    translated: str = Field(..., description="SynthLang translated code")
    original_size: int = Field(..., description="Original code size in characters")
    translated_size: int = Field(..., description="Translated code size in characters")
    processing_time_ms: float = Field(..., description="Processing time in milliseconds")
    ast_nodes_processed: int = Field(..., description="Number of AST nodes processed")
    compact_mode: bool = Field(..., description="Whether compact mode was used")
    size_reduction_percent: float = Field(..., description="Percentage change in size (negative means increase)")

class SudoLangStatsResponse(BaseModel):
    translated: str = Field(..., description="SudoLang translated code")
    stats: Dict[str, Any] = Field(..., description="Detailed translation statistics")

class SynthLangStatsResponse(BaseModel):
    translated: str = Field(..., description="SynthLang translated code")
    original_size: int = Field(..., description="Original code size in characters")
    translated_size: int = Field(..., description="Translated code size in characters")
    processing_time_ms: float = Field(..., description="Processing time in milliseconds")
    ast_nodes_processed: int = Field(..., description="Number of AST nodes processed")
    compact_mode: bool = Field(..., description="Whether compact mode was used")
    size_reduction_percent: float = Field(..., description="Percentage change in size")
    translation_method: str = Field(..., description="Translation method used")

# Chained transformation models
class ChainedTransformRequest(BaseModel):
    code: str = Field(..., description="Python source code to transform", min_length=1, max_length=1000000)
    minify_depth: Optional[int] = Field(4, description="Minification depth (1-4) before translation")
    compact: Optional[bool] = Field(True, description="Use compact mode for final translation")
    
    @validator('code')
    def validate_code_not_empty(cls, v):
        if not v.strip():
            raise ValueError('code cannot be empty or whitespace only')
        return v
    
    @validator('minify_depth')
    def validate_minify_depth(cls, v):
        if v is not None and (v < 1 or v > 4):
            raise ValueError('minify_depth must be between 1 and 4')
        return v

class ChainedTransformResponse(BaseModel):
    original_code: str = Field(..., description="Original Python code")
    minified_code: str = Field(..., description="Minified Python code")
    final_translated: str = Field(..., description="Final translated code")
    translation_type: str = Field(..., description="Type of translation (synthlang or sudolang)")
    
    # Metrics for each stage
    original_size: int = Field(..., description="Original code size in characters")
    original_tokens: int = Field(..., description="Estimated original tokens")
    
    minified_size: int = Field(..., description="Minified code size in characters")
    minified_tokens: int = Field(..., description="Estimated minified tokens")
    minification_reduction_percent: float = Field(..., description="Minification size reduction percentage")
    
    final_size: int = Field(..., description="Final translated code size in characters")
    final_tokens: int = Field(..., description="Estimated final tokens")
    overall_reduction_percent: float = Field(..., description="Overall size reduction percentage")
    
    processing_time_ms: float = Field(..., description="Total processing time in milliseconds")
    minify_depth_used: int = Field(..., description="Minification depth used")
    compact_mode: bool = Field(..., description="Whether compact mode was used")

class ChainedPipelineResponse(BaseModel):
    """Comprehensive pipeline analysis response with all transformation stages"""
    original_code: str = Field(..., description="Original Python code")
    
    # Minification stage results (depths 1-4)
    minification_stages: Dict[str, Dict[str, Any]] = Field(..., description="Results for each minification depth")
    
    # Translation stage results
    translation_stages: Dict[str, Dict[str, Any]] = Field(..., description="Results for each translation method")
    
    # Best transformation metrics
    best_method: str = Field(..., description="Best performing transformation method")
    best_compression_tokens: int = Field(..., description="Tokens for best compression")
    best_reduction_percent: float = Field(..., description="Best reduction percentage achieved")
    best_similarity_score: float = Field(..., description="Similarity score for best method")
    
    # Overall pipeline metrics
    original_tokens: int = Field(..., description="Original token count")
    processing_time_ms: float = Field(..., description="Total processing time in milliseconds")
    methods_analyzed: int = Field(..., description="Number of transformation methods analyzed")

# Global state for tracking uptime
app.start_time = time.time()

@app.get("/health", response_model=HealthResponse, tags=["Health"])
async def health_check():
    """Health check endpoint to verify service status."""
    return HealthResponse(
        status="healthy",
        timestamp=datetime.utcnow().isoformat(),
        version="1.0.0",
        uptime_seconds=time.time() - app.start_time
    )

@app.post("/minify", response_model=MinifyResponse, tags=["Minification"])
async def minify_python_code(request: MinifyRequest, http_request: Request):
    """
    Minify Python code with comprehensive logging and metrics.
    
    This endpoint provides fast Python code minification with:
    - Comments and whitespace removal
    - Optional constant folding and boolean optimization
    - Optional variable name shortening
    - Comprehensive error handling and validation
    - Performance metrics and logging
    
    Token estimation uses len(minified)//4 which approximates:
    - 4 characters per token on average for minified Python code
    - Accounts for reduced whitespace and shorter identifiers
    - Provides conservative estimates suitable for LLM context planning
    """
    start_time = time.time()
    request_id = http_request.headers.get("x-request-id", "unknown")
    
    try:
        # Log the minification request
        fastapi_logger.log_token_metrics({
            "event": "minification_request",
            "request_id": request_id,
            "original_code_length": len(request.code),
            "aggressive_mode": request.aggressive,
            "compression_depth": request.compression_depth,
            "validation_enabled": request.validate_output
        })
        
        # Use adaptive compression with tier selection
        headers = dict(http_request.headers)
        minified_code = adapt_compression(headers, request.code)
        
        # Calculate metrics
        original_size = len(request.code)
        minified_size = len(minified_code)
        size_reduction = original_size - minified_size
        size_reduction_percent = (size_reduction / original_size * 100) if original_size > 0 else 0
        processing_time_ms = (time.time() - start_time) * 1000
        
        # Enhanced token estimation using tiktoken for accuracy
        estimated_tokens = estimate_tokens(
            minified_code, 
            method="tiktoken", 
            model_type="gpt-4", 
            operation_id=request_id
        )
        
        # Determine compression depth used
        if request.compression_depth is not None:
            compression_depth_used = request.compression_depth
        else:
            compression_depth_used = CompressionDepth.AGGRESSIVE if request.aggressive else CompressionDepth.CONSTANTS
        
        # Log successful minification with enhanced metrics
        fastapi_logger.log_token_metrics({
            "event": "minification_success",
            "request_id": request_id,
            "original_size": original_size,
            "minified_size": minified_size,
            "size_reduction_percent": size_reduction_percent,
            "estimated_tokens": estimated_tokens,
            "processing_time_ms": processing_time_ms,
            "compression_depth_used": compression_depth_used,
            "method": "tiktoken"
        })
        
        return MinifyResponse(
            minified=minified_code,
            estimated_tokens=estimated_tokens,
            original_size=original_size,
            minified_size=minified_size,
            size_reduction_percent=round(size_reduction_percent, 2),
            processing_time_ms=round(processing_time_ms, 2),
            compression_depth_used=compression_depth_used
        )
        
    except ValueError as e:
        # Handle validation errors (invalid Python code, etc.)
        fastapi_logger.log_token_metrics({
            "event": "minification_validation_error",
            "request_id": request_id,
            "error_message": str(e),
            "original_code_length": len(request.code)
        })
        
        raise HTTPException(
            status_code=400,
            detail=ErrorResponse(
                error="ValidationError",
                message=str(e),
                timestamp=datetime.utcnow().isoformat(),
                request_id=request_id
            ).dict()
        )
        
    except SyntaxError as e:
        # Handle syntax errors in input code
        fastapi_logger.log_token_metrics({
            "event": "minification_syntax_error",
            "request_id": request_id,
            "error_message": str(e),
            "original_code_length": len(request.code)
        })
        
        raise HTTPException(
            status_code=422,
            detail=ErrorResponse(
                error="SyntaxError",
                message=f"Invalid Python syntax: {str(e)}",
                timestamp=datetime.utcnow().isoformat(),
                request_id=request_id
            ).dict()
        )
        
    except Exception as e:
        # Handle unexpected errors
        fastapi_logger.log_token_metrics({
            "event": "minification_unexpected_error",
            "request_id": request_id,
            "error_type": type(e).__name__,
            "error_message": str(e),
            "original_code_length": len(request.code)
        })
        
        raise HTTPException(
            status_code=500,
            detail=ErrorResponse(
                error="InternalServerError",
                message="An unexpected error occurred during minification",
                timestamp=datetime.utcnow().isoformat(),
                request_id=request_id
            ).dict()
        )

@app.post("/minify/stats", response_model=MinifyStatsResponse, tags=["Minification"])
async def minify_with_detailed_stats(request: MinifyRequest, http_request: Request):
    """
    Minify Python code and return detailed statistics.
    
    This endpoint provides the same minification as /minify but includes
    comprehensive statistics about the transformation process.
    """
    start_time = time.time()
    request_id = http_request.headers.get("x-request-id", "unknown")
    
    try:
        # Use adaptive compression with tier selection
        headers = dict(http_request.headers)
        minified_code = adapt_compression(headers, request.code)
        
        # Simple token estimation: len(minified) // 4
        estimated_tokens = len(minified_code) // 4
        
        # Create basic stats structure for consistency
        stats = {
            "original_size": len(request.code),
            "minified_size": len(minified_code),
            "processing_time_ms": (time.time() - start_time) * 1000,
            "estimated_tokens": estimated_tokens,
            "token_estimation_method": "len_divided_by_4",
            "compression_method": "adaptive_tier_selection"
        }
        
        # Log successful minification with stats
        fastapi_logger.log_token_metrics({
            "event": "minification_with_stats_success",
            "request_id": request_id,
            "stats": stats
        })
        
        return MinifyStatsResponse(
            minified=minified_code,
            estimated_tokens=estimated_tokens,
            stats=stats
        )
        
    except Exception as e:
        # Handle errors similar to main minify endpoint
        error_type = type(e).__name__
        if isinstance(e, (ValueError, SyntaxError)):
            status_code = 400 if isinstance(e, ValueError) else 422
        else:
            status_code = 500
            
        fastapi_logger.log_token_metrics({
            "event": "minification_with_stats_error",
            "request_id": request_id,
            "error_type": error_type,
            "error_message": str(e)
        })
        
        raise HTTPException(
            status_code=status_code,
            detail=ErrorResponse(
                error=error_type,
                message=str(e),
                timestamp=datetime.utcnow().isoformat(),
                request_id=request_id
            ).dict()
        )

@app.post("/minify/otpm", response_model=OTPMMinifyResponse, tags=["Minification"])
async def minify_with_otpm_awareness(request: OTPMMinifyRequest, http_request: Request):
    """
    OTPM-aware Python code minification with adaptive compression.
    
    This endpoint provides intelligent compression based on rate limit status:
    - Monitors remaining token percentage
    - Adapts compression strategy automatically
    - Uses tiktoken for precise token counting
    - Logs comprehensive OTPM metrics
    - Supports emergency compression modes
    """
    start_time = time.time()
    request_id = http_request.headers.get("x-request-id", f"otpm-{int(time.time() * 1000)}")
    
    try:
        # Determine compression type if auto
        if request.compression_type == "auto":
            compression_type = get_compression_recommendation(
                request.remaining_pct, 
                len(request.code)
            )
        else:
            compression_type = request.compression_type
        
        # Log OTPM adaptation if needed
        if request.compression_type == "auto" and compression_type != "standard":
            otpm_logger = get_logger()
            otpm_logger.log_compression_adaptation(
                operation_id=request_id,
                original_compression="standard",
                new_compression=compression_type,
                trigger_reason="otpm_threshold",
                rate_limit_info={
                    "remaining_pct": request.remaining_pct,
                    "headers": request.rate_limit_headers or {}
                }
            )
        
        # Perform OTPM-aware minification
        minified_code, stats = minify_with_otpm_tracking(
            code_str=request.code,
            operation_id=request_id,
            compression_type=compression_type,
            remaining_pct=request.remaining_pct,
            model_type=request.model_type
        )
        
        processing_time_ms = (time.time() - start_time) * 1000
        
        return OTPMMinifyResponse(
            minified=minified_code,
            estimated_tokens=stats["minified_tokens"],
            original_tokens=stats["original_tokens"],
            token_reduction_percent=stats["token_reduction_percent"],
            compression_type_used=stats["compression_type"],
            otpm_status=stats["otpm_status"],
            remaining_pct=stats["remaining_pct"],
            processing_time_ms=processing_time_ms,
            operation_id=request_id
        )
        
    except ValueError as e:
        error_type = "validation_error"
        fastapi_logger.log_token_metrics({
            "event": "otpm_minify_validation_error",
            "request_id": request_id,
            "error": str(e),
            "remaining_pct": request.remaining_pct
        })
        
        raise HTTPException(
            status_code=422,
            detail=ErrorResponse(
                error=error_type,
                message=str(e),
                timestamp=datetime.utcnow().isoformat(),
                request_id=request_id
            ).dict()
        )
    except Exception as e:
        error_type = "internal_error"
        fastapi_logger.log_token_metrics({
            "event": "otpm_minify_internal_error",
            "request_id": request_id,
            "error": str(e),
            "remaining_pct": request.remaining_pct
        })
        
        raise HTTPException(
            status_code=500,
            detail=ErrorResponse(
                error=error_type,
                message=str(e),
                timestamp=datetime.utcnow().isoformat(),
                request_id=request_id
            ).dict()
        )

@app.get("/metrics", tags=["Monitoring"])
async def get_service_metrics():
    """
    Get service-level metrics and statistics.
    
    Returns basic service metrics for monitoring and health checking.
    """
    return {
        "service": "python-optimization-translation-api",
        "version": "1.0.0",
        "uptime_seconds": time.time() - app.start_time,
        "timestamp": datetime.utcnow().isoformat(),
        "status": "operational"
    }

@app.post("/translate/sudolang", response_model=SudoLangResponse, tags=["Translation"])
async def translate_to_sudolang(request: TranslateRequest, http_request: Request):
    """
    Translate Python code to SudoLang with comprehensive logging and metrics.
    
    SudoLang is a high-level pseudocode language that represents Python logic
    in a more readable, English-like syntax. This endpoint provides:
    - Python AST parsing and transformation
    - Comprehensive error handling and validation
    - Performance metrics and logging
    - AST node processing statistics
    """
    start_time = time.time()
    request_id = http_request.headers.get("x-request-id", "unknown")
    
    try:
        # Log the translation request
        fastapi_logger.log_token_metrics({
            "event": "sudolang_translation_request",
            "request_id": request_id,
            "original_code_length": len(request.code)
        })
        
        # Use adaptive compression with tier selection
        headers = dict(http_request.headers)
        translated_code = adapt_compression(headers, request.code, is_translate=True)
        
        # Calculate metrics
        original_size = len(request.code)
        translated_size = len(translated_code)
        processing_time_ms = (time.time() - start_time) * 1000
        
        # Count AST nodes for complexity metrics
        try:
            tree = ast.parse(request.code)
            ast_nodes_processed = len([node for node in ast.walk(tree)])
        except:
            ast_nodes_processed = 0
        
        # Log successful translation
        fastapi_logger.log_token_metrics({
            "event": "sudolang_translation_success",
            "request_id": request_id,
            "original_size": original_size,
            "translated_size": translated_size,
            "processing_time_ms": processing_time_ms,
            "ast_nodes_processed": ast_nodes_processed
        })
        
        return SudoLangResponse(
            translated=translated_code,
            original_size=original_size,
            translated_size=translated_size,
            processing_time_ms=round(processing_time_ms, 2),
            ast_nodes_processed=ast_nodes_processed
        )
        
    except ValueError as e:
        fastapi_logger.log_token_metrics({
            "event": "sudolang_translation_validation_error",
            "request_id": request_id,
            "error_message": str(e),
            "original_code_length": len(request.code)
        })
        
        raise HTTPException(
            status_code=400,
            detail=ErrorResponse(
                error="ValidationError",
                message=str(e),
                timestamp=datetime.utcnow().isoformat(),
                request_id=request_id
            ).dict()
        )
        
    except SyntaxError as e:
        fastapi_logger.log_token_metrics({
            "event": "sudolang_translation_syntax_error",
            "request_id": request_id,
            "error_message": str(e),
            "original_code_length": len(request.code)
        })
        
        raise HTTPException(
            status_code=422,
            detail=ErrorResponse(
                error="SyntaxError",
                message=f"Invalid Python syntax: {str(e)}",
                timestamp=datetime.utcnow().isoformat(),
                request_id=request_id
            ).dict()
        )
        
    except Exception as e:
        fastapi_logger.log_token_metrics({
            "event": "sudolang_translation_unexpected_error",
            "request_id": request_id,
            "error_type": type(e).__name__,
            "error_message": str(e),
            "original_code_length": len(request.code)
        })
        
        raise HTTPException(
            status_code=500,
            detail=ErrorResponse(
                error="InternalServerError",
                message="An unexpected error occurred during SudoLang translation",
                timestamp=datetime.utcnow().isoformat(),
                request_id=request_id
            ).dict()
        )

@app.post("/translate/sudolang/stats", response_model=SudoLangStatsResponse, tags=["Translation"])
async def translate_to_sudolang_with_stats(request: TranslateRequest, http_request: Request):
    """
    Translate Python code to SudoLang and return detailed statistics.
    
    This endpoint provides the same translation as /translate/sudolang but includes
    comprehensive statistics about the transformation process.
    """
    start_time = time.time()
    request_id = http_request.headers.get("x-request-id", "unknown")
    
    try:
        # Use adaptive compression with tier selection
        headers = dict(http_request.headers)
        translated_code = adapt_compression(headers, request.code, is_translate=True)
        
        # Create basic stats structure for consistency
        stats = {
            "original_size": len(request.code),
            "translated_size": len(translated_code),
            "processing_time_ms": (time.time() - start_time) * 1000,
            "compression_method": "adaptive_tier_selection"
        }
        
        # Log successful translation with stats
        fastapi_logger.log_token_metrics({
            "event": "sudolang_translation_with_stats_success",
            "request_id": request_id,
            "stats": stats
        })
        
        return SudoLangStatsResponse(
            translated=translated_code,
            stats=stats
        )
        
    except Exception as e:
        error_type = type(e).__name__
        if isinstance(e, (ValueError, SyntaxError)):
            status_code = 400 if isinstance(e, ValueError) else 422
        else:
            status_code = 500
            
        fastapi_logger.log_token_metrics({
            "event": "sudolang_translation_with_stats_error",
            "request_id": request_id,
            "error_type": error_type,
            "error_message": str(e)
        })
        
        raise HTTPException(
            status_code=status_code,
            detail=ErrorResponse(
                error=error_type,
                message=str(e),
                timestamp=datetime.utcnow().isoformat(),
                request_id=request_id
            ).dict()
        )

@app.post("/translate/synthlang", response_model=SynthLangResponse, tags=["Translation"])
async def translate_to_synthlang(request: TranslateRequest, http_request: Request):
    """
    Translate Python code to SynthLang with comprehensive logging and metrics.
    
    SynthLang is a symbolic mathematical notation for Python code that uses
    mathematical symbols and operators to represent programming constructs.
    This endpoint provides:
    - Compact or formatted output options
    - Python AST parsing and transformation
    - Comprehensive error handling and validation
    - Performance metrics and logging
    - Size reduction/expansion tracking
    """
    start_time = time.time()
    request_id = http_request.headers.get("x-request-id", "unknown")
    
    try:
        # Log the translation request
        fastapi_logger.log_token_metrics({
            "event": "synthlang_translation_request",
            "request_id": request_id,
            "original_code_length": len(request.code),
            "compact_mode": request.compact,
            "indent_size": request.indent_size
        })
        
        # Use adaptive compression with tier selection
        headers = dict(http_request.headers)
        translated_code = adapt_compression(headers, request.code, is_translate=True)
        
        # Calculate metrics
        original_size = len(request.code)
        translated_size = len(translated_code)
        size_change = translated_size - original_size
        size_change_percent = (size_change / original_size * 100) if original_size > 0 else 0
        processing_time_ms = (time.time() - start_time) * 1000
        
        # Count AST nodes for complexity metrics
        try:
            tree = ast.parse(request.code)
            ast_nodes_processed = len([node for node in ast.walk(tree)])
        except:
            ast_nodes_processed = 0
        
        # Log successful translation
        fastapi_logger.log_token_metrics({
            "event": "synthlang_translation_success",
            "request_id": request_id,
            "original_size": original_size,
            "translated_size": translated_size,
            "size_change_percent": size_change_percent,
            "processing_time_ms": processing_time_ms,
            "ast_nodes_processed": ast_nodes_processed,
            "compact_mode": request.compact
        })
        
        return SynthLangResponse(
            translated=translated_code,
            original_size=original_size,
            translated_size=translated_size,
            processing_time_ms=round(processing_time_ms, 2),
            ast_nodes_processed=ast_nodes_processed,
            compact_mode=request.compact,
            size_reduction_percent=round(size_change_percent, 2)
        )
        
    except ValueError as e:
        fastapi_logger.log_token_metrics({
            "event": "synthlang_translation_validation_error",
            "request_id": request_id,
            "error_message": str(e),
            "original_code_length": len(request.code)
        })
        
        raise HTTPException(
            status_code=400,
            detail=ErrorResponse(
                error="ValidationError",
                message=str(e),
                timestamp=datetime.utcnow().isoformat(),
                request_id=request_id
            ).dict()
        )
        
    except SyntaxError as e:
        fastapi_logger.log_token_metrics({
            "event": "synthlang_translation_syntax_error",
            "request_id": request_id,
            "error_message": str(e),
            "original_code_length": len(request.code)
        })
        
        raise HTTPException(
            status_code=422,
            detail=ErrorResponse(
                error="SyntaxError",
                message=f"Invalid Python syntax: {str(e)}",
                timestamp=datetime.utcnow().isoformat(),
                request_id=request_id
            ).dict()
        )
        
    except Exception as e:
        fastapi_logger.log_token_metrics({
            "event": "synthlang_translation_unexpected_error",
            "request_id": request_id,
            "error_type": type(e).__name__,
            "error_message": str(e),
            "original_code_length": len(request.code)
        })
        
        raise HTTPException(
            status_code=500,
            detail=ErrorResponse(
                error="InternalServerError",
                message="An unexpected error occurred during SynthLang translation",
                timestamp=datetime.utcnow().isoformat(),
                request_id=request_id
            ).dict()
        )

@app.post("/translate/synthlang/stats", response_model=SynthLangStatsResponse, tags=["Translation"])
async def translate_to_synthlang_with_stats(request: TranslateRequest, http_request: Request):
    """
    Translate Python code to SynthLang and return detailed statistics.
    
    This endpoint provides the same translation as /translate/synthlang but includes
    comprehensive statistics about the transformation process, including method comparison.
    """
    start_time = time.time()
    request_id = http_request.headers.get("x-request-id", "unknown")
    
    try:
        # Use adaptive compression with tier selection
        headers = dict(http_request.headers)
        translated_code = adapt_compression(headers, request.code, is_translate=True)
        
        # Calculate metrics
        original_size = len(request.code)
        translated_size = len(translated_code)
        processing_time_ms = (time.time() - start_time) * 1000
        
        # Count AST nodes
        try:
            tree = ast.parse(request.code)
            ast_nodes_processed = len([node for node in ast.walk(tree)])
        except:
            ast_nodes_processed = 0
        
        # Use translated result as primary output
        size_change = translated_size - original_size
        size_change_percent = (size_change / original_size * 100) if original_size > 0 else 0
        
        # Create comprehensive stats for adaptive compression
        stats = {
            "adaptive_compression": {
                "size": translated_size,
                "size_change_percent": round(size_change_percent, 2)
            },
            "method": "adaptive_tier_selection"
        }
        
        # Log successful translation with stats
        fastapi_logger.log_token_metrics({
            "event": "synthlang_translation_with_stats_success",
            "request_id": request_id,
            "original_size": original_size,
            "translated_size": translated_size,
            "processing_time_ms": processing_time_ms,
            "ast_nodes_processed": ast_nodes_processed,
            "compact_mode": request.compact
        })
        
        return SynthLangStatsResponse(
            translated=translated_code,
            original_size=original_size,
            translated_size=translated_size,
            processing_time_ms=round(processing_time_ms, 2),
            ast_nodes_processed=ast_nodes_processed,
            compact_mode=request.compact,
            size_reduction_percent=round(size_change_percent, 2),
            translation_method="adaptive_compression"
        )
        
    except Exception as e:
        error_type = type(e).__name__
        if isinstance(e, (ValueError, SyntaxError)):
            status_code = 400 if isinstance(e, ValueError) else 422
        else:
            status_code = 500
            
        fastapi_logger.log_token_metrics({
            "event": "synthlang_translation_with_stats_error",
            "request_id": request_id,
            "error_type": error_type,
            "error_message": str(e)
        })
        
        raise HTTPException(
            status_code=status_code,
            detail=ErrorResponse(
                error=error_type,
                message=str(e),
                timestamp=datetime.utcnow().isoformat(),
                request_id=request_id
            ).dict()
        )

# Chained Transformation Endpoints
@app.post("/transform/minify-synthlang", response_model=ChainedTransformResponse, tags=["Chained Transformations"])
async def minify_then_synthlang(request: ChainedTransformRequest, http_request: Request):
    """
    Chain minification and SynthLang translation for optimal compression.
    
    This endpoint performs a two-stage transformation:
    1. Minify Python code using specified depth (1-4)
    2. Translate minified code to SynthLang
    
    This chaining approach typically achieves better compression than
    either transformation alone, while maintaining semantic equivalence.
    """
    start_time = time.time()
    request_id = http_request.headers.get("x-request-id", "unknown")
    
    try:
        fastapi_logger.log_token_metrics({
            "event": "chained_minify_synthlang_start",
            "request_id": request_id,
            "input_size": len(request.code),
            "minify_depth": request.minify_depth,
            "compact_mode": request.compact
        })
        
        original_code = request.code
        original_size = len(original_code)
        original_tokens = estimate_tokens(original_code)
        
        # Stage 1: Minification
        try:
            minified_code = minify_depth(original_code, request.minify_depth)
            minified_size = len(minified_code)
            minified_tokens = estimate_tokens(minified_code)
            minification_reduction = ((original_size - minified_size) / original_size) * 100 if original_size > 0 else 0
        except Exception as e:
            fastapi_logger.log_token_metrics({
                "event": "chained_minify_synthlang_error_minification",
                "request_id": request_id,
                "error": str(e)
            })
            raise HTTPException(status_code=422, detail=f"Minification failed: {str(e)}")
        
        # Stage 2: SynthLang Translation
        try:
            final_translated = python_to_synthlang(minified_code, compact=request.compact)
            final_size = len(final_translated)
            final_tokens = estimate_tokens(final_translated)
            overall_reduction = ((original_size - final_size) / original_size) * 100 if original_size > 0 else 0
        except Exception as e:
            fastapi_logger.log_token_metrics({
                "event": "chained_minify_synthlang_error_translation",
                "request_id": request_id,
                "error": str(e)
            })
            raise HTTPException(status_code=422, detail=f"SynthLang translation failed: {str(e)}")
        
        processing_time_ms = (time.time() - start_time) * 1000
        
        # Log successful chained transformation
        fastapi_logger.log_token_metrics({
            "event": "chained_minify_synthlang_success",
            "request_id": request_id,
            "original_size": original_size,
            "minified_size": minified_size,
            "final_size": final_size,
            "overall_reduction_percent": overall_reduction,
            "processing_time_ms": processing_time_ms
        })
        
        return ChainedTransformResponse(
            original_code=original_code,
            minified_code=minified_code,
            final_translated=final_translated,
            translation_type="synthlang",
            original_size=original_size,
            original_tokens=original_tokens,
            minified_size=minified_size,
            minified_tokens=minified_tokens,
            minification_reduction_percent=round(minification_reduction, 2),
            final_size=final_size,
            final_tokens=final_tokens,
            overall_reduction_percent=round(overall_reduction, 2),
            processing_time_ms=round(processing_time_ms, 2),
            minify_depth_used=request.minify_depth,
            compact_mode=request.compact
        )
    
    except HTTPException:
        raise
    except Exception as e:
        error_type = type(e).__name__
        fastapi_logger.log_token_metrics({
            "event": "chained_minify_synthlang_error",
            "request_id": request_id,
            "error_type": error_type,
            "error_message": str(e)
        })
        
        raise HTTPException(
            status_code=500,
            detail=ErrorResponse(
                error=error_type,
                message=str(e),
                timestamp=datetime.utcnow().isoformat(),
                request_id=request_id
            ).dict()
        )

@app.post("/transform/minify-sudolang", response_model=ChainedTransformResponse, tags=["Chained Transformations"])
async def minify_then_sudolang(request: ChainedTransformRequest, http_request: Request):
    """
    Chain minification and SudoLang translation for optimal compression.
    
    This endpoint performs a two-stage transformation:
    1. Minify Python code using specified depth (1-4)
    2. Translate minified code to SudoLang
    
    This chaining approach typically achieves better compression than
    either transformation alone, while maintaining semantic equivalence.
    """
    start_time = time.time()
    request_id = http_request.headers.get("x-request-id", "unknown")
    
    try:
        fastapi_logger.log_token_metrics({
            "event": "chained_minify_sudolang_start",
            "request_id": request_id,
            "input_size": len(request.code),
            "minify_depth": request.minify_depth
        })
        
        original_code = request.code
        original_size = len(original_code)
        original_tokens = estimate_tokens(original_code)
        
        # Stage 1: Minification
        try:
            minified_code = minify_depth(original_code, request.minify_depth)
            minified_size = len(minified_code)
            minified_tokens = estimate_tokens(minified_code)
            minification_reduction = ((original_size - minified_size) / original_size) * 100 if original_size > 0 else 0
        except Exception as e:
            fastapi_logger.log_token_metrics({
                "event": "chained_minify_sudolang_error_minification",
                "request_id": request_id,
                "error": str(e)
            })
            raise HTTPException(status_code=422, detail=f"Minification failed: {str(e)}")
        
        # Stage 2: SudoLang Translation
        try:
            final_translated = python_to_sudolang(minified_code)
            final_size = len(final_translated)
            final_tokens = estimate_tokens(final_translated)
            overall_reduction = ((original_size - final_size) / original_size) * 100 if original_size > 0 else 0
        except Exception as e:
            fastapi_logger.log_token_metrics({
                "event": "chained_minify_sudolang_error_translation",
                "request_id": request_id,
                "error": str(e)
            })
            raise HTTPException(status_code=422, detail=f"SudoLang translation failed: {str(e)}")
        
        processing_time_ms = (time.time() - start_time) * 1000
        
        # Log successful chained transformation
        fastapi_logger.log_token_metrics({
            "event": "chained_minify_sudolang_success",
            "request_id": request_id,
            "original_size": original_size,
            "minified_size": minified_size,
            "final_size": final_size,
            "overall_reduction_percent": overall_reduction,
            "processing_time_ms": processing_time_ms
        })
        
        return ChainedTransformResponse(
            original_code=original_code,
            minified_code=minified_code,
            final_translated=final_translated,
            translation_type="sudolang",
            original_size=original_size,
            original_tokens=original_tokens,
            minified_size=minified_size,
            minified_tokens=minified_tokens,
            minification_reduction_percent=round(minification_reduction, 2),
            final_size=final_size,
            final_tokens=final_tokens,
            overall_reduction_percent=round(overall_reduction, 2),
            processing_time_ms=round(processing_time_ms, 2),
            minify_depth_used=request.minify_depth,
            compact_mode=request.compact  # Not used for SudoLang but kept for consistency
        )
    
    except HTTPException:
        raise
    except Exception as e:
        error_type = type(e).__name__
        fastapi_logger.log_token_metrics({
            "event": "chained_minify_sudolang_error",
            "request_id": request_id,
            "error_type": error_type,
            "error_message": str(e)
        })
        
        raise HTTPException(
            status_code=500,
            detail=ErrorResponse(
                error=error_type,
                message=str(e),
                timestamp=datetime.utcnow().isoformat(),
                request_id=request_id
            ).dict()
        )

@app.post("/transform/pipeline-analysis", response_model=ChainedPipelineResponse, tags=["Chained Transformations"])
async def comprehensive_pipeline_analysis(request: ChainedTransformRequest, http_request: Request):
    """
    Comprehensive pipeline analysis: test all minification depths and translation methods.
    
    This endpoint performs extensive analysis:
    1. Tests minification at depths 1-4
    2. Tests SynthLang translation (readable and compact modes)
    3. Tests chained transformations (minify → translate)
    4. Returns detailed metrics for all methods
    5. Identifies the best performing transformation
    
    This is ideal for finding the optimal transformation pipeline for your code.
    """
    start_time = time.time()
    request_id = http_request.headers.get("x-request-id", "unknown")
    
    try:
        fastapi_logger.log_token_metrics({
            "event": "pipeline_analysis_start",
            "request_id": request_id,
            "input_size": len(request.code)
        })
        
        original_code = request.code
        original_size = len(original_code)
        original_tokens = estimate_tokens(original_code)
        
        minification_stages = {}
        translation_stages = {}
        
        # Stage 1: Test all minification depths
        for depth in range(1, 5):
            try:
                minified = minify_depth(original_code, depth)
                minified_size = len(minified)
                minified_tokens = estimate_tokens(minified)
                reduction_percent = ((original_size - minified_size) / original_size) * 100 if original_size > 0 else 0
                
                minification_stages[f"depth_{depth}"] = {
                    "code": minified,
                    "size": minified_size,
                    "tokens": minified_tokens,
                    "reduction_percent": round(reduction_percent, 2),
                    "success": True
                }
            except Exception as e:
                minification_stages[f"depth_{depth}"] = {
                    "error": str(e),
                    "success": False
                }
        
        # Stage 2: Test SynthLang translations
        best_minified = None
        for depth in range(4, 0, -1):  # Try from most aggressive to least
            if f"depth_{depth}" in minification_stages and minification_stages[f"depth_{depth}"].get("success"):
                best_minified = minification_stages[f"depth_{depth}"]["code"]
                break
        
        if best_minified is None:
            best_minified = original_code
        
        # SynthLang from original
        for mode, compact in [("readable", False), ("compact", True)]:
            try:
                translated = python_to_synthlang(original_code, compact=compact)
                translated_size = len(translated)
                translated_tokens = estimate_tokens(translated)
                reduction_percent = ((original_size - translated_size) / original_size) * 100 if original_size > 0 else 0
                
                translation_stages[f"synthlang_from_original_{mode}"] = {
                    "code": translated,
                    "size": translated_size,
                    "tokens": translated_tokens,
                    "reduction_percent": round(reduction_percent, 2),
                    "success": True,
                    "source": "original"
                }
            except Exception as e:
                translation_stages[f"synthlang_from_original_{mode}"] = {
                    "error": str(e),
                    "success": False,
                    "source": "original"
                }
        
        # SynthLang from minified
        for mode, compact in [("readable", False), ("compact", True)]:
            try:
                translated = python_to_synthlang(best_minified, compact=compact)
                translated_size = len(translated)
                translated_tokens = estimate_tokens(translated)
                reduction_percent = ((original_size - translated_size) / original_size) * 100 if original_size > 0 else 0
                
                translation_stages[f"synthlang_from_minified_{mode}"] = {
                    "code": translated,
                    "size": translated_size,
                    "tokens": translated_tokens,
                    "reduction_percent": round(reduction_percent, 2),
                    "success": True,
                    "source": "minified"
                }
            except Exception as e:
                translation_stages[f"synthlang_from_minified_{mode}"] = {
                    "error": str(e),
                    "success": False,
                    "source": "minified"
                }
        
        # Find best method
        best_method = "original"
        best_tokens = original_tokens
        best_reduction = 0.0
        best_similarity = 1.0
        methods_analyzed = 0
        
        # Check minification methods
        for method_name, data in minification_stages.items():
            if data.get("success"):
                methods_analyzed += 1
                if data["tokens"] < best_tokens:
                    best_method = f"minification_{method_name}"
                    best_tokens = data["tokens"]
                    best_reduction = data["reduction_percent"]
        
        # Check translation methods
        for method_name, data in translation_stages.items():
            if data.get("success"):
                methods_analyzed += 1
                if data["tokens"] < best_tokens:
                    best_method = f"translation_{method_name}"
                    best_tokens = data["tokens"]
                    best_reduction = data["reduction_percent"]
        
        processing_time_ms = (time.time() - start_time) * 1000
        
        # Log successful pipeline analysis
        fastapi_logger.log_token_metrics({
            "event": "pipeline_analysis_success",
            "request_id": request_id,
            "original_tokens": original_tokens,
            "best_tokens": best_tokens,
            "best_method": best_method,
            "methods_analyzed": methods_analyzed,
            "processing_time_ms": processing_time_ms
        })
        
        return ChainedPipelineResponse(
            original_code=original_code,
            minification_stages=minification_stages,
            translation_stages=translation_stages,
            best_method=best_method,
            best_compression_tokens=best_tokens,
            best_reduction_percent=round(best_reduction, 2),
            best_similarity_score=best_similarity,
            original_tokens=original_tokens,
            processing_time_ms=round(processing_time_ms, 2),
            methods_analyzed=methods_analyzed
        )
    
    except Exception as e:
        error_type = type(e).__name__
        fastapi_logger.log_token_metrics({
            "event": "pipeline_analysis_error",
            "request_id": request_id,
            "error_type": error_type,
            "error_message": str(e)
        })
        
        raise HTTPException(
            status_code=500,
            detail=ErrorResponse(
                error=error_type,
                message=str(e),
                timestamp=datetime.utcnow().isoformat(),
                request_id=request_id
            ).dict()
        )

# Error handlers
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Custom HTTP exception handler with logging."""
    request_id = request.headers.get("x-request-id", "unknown")
    
    fastapi_logger.log_token_metrics({
        "event": "http_exception",
        "request_id": request_id,
        "status_code": exc.status_code,
        "detail": exc.detail
    })
    
    return exc

@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """General exception handler for unexpected errors."""
    request_id = request.headers.get("x-request-id", "unknown")
    
    fastapi_logger.log_token_metrics({
        "event": "unexpected_exception",
        "request_id": request_id,
        "error_type": type(exc).__name__,
        "error_message": str(exc)
    })
    
    raise HTTPException(
        status_code=500,
        detail=ErrorResponse(
            error="InternalServerError",
            message="An unexpected error occurred",
            timestamp=datetime.utcnow().isoformat(),
            request_id=request_id
        ).dict()
    )

# Startup event
@app.on_event("startup")
async def startup_event():
    """Application startup tasks."""
    print("🚀 Python Optimization & Translation API starting up...")
    print("📊 Comprehensive logging enabled")
    print("🔧 Minifier with optimization ready")
    print("✅ API ready to accept requests")

# Shutdown event
@app.on_event("shutdown")
async def shutdown_event():
    """Application shutdown tasks."""
    print("🛑 Python Optimization & Translation API shutting down...")
    print("📝 Final logs flushed")
    print("✅ Shutdown complete")

# Development server runner
if __name__ == "__main__":
    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info",
        access_log=True
    )