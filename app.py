from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from pydantic import BaseModel, Field, validator
from typing import Optional, Dict, Any
import time
import ast
import json
import os
from datetime import datetime
import uvicorn
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Import our enhanced minifier with logging
from input_optimizer.engine.minifier import (
    minify_code, 
    minify_with_stats, 
    CompressionDepth,
    minify_depth
)

# Import enhanced logger functions
from utils.logger import (
    minify_with_otpm_tracking,
    get_compression_recommendation,
    get_logger,
    setup_minifier_logging,
    estimate_tokens
)

# Import translators
from input_optimizer.engine.translators.sudo_lang_translator import (
    python_to_sudolang,
    translate_with_stats as sudo_translate_with_stats
)
from input_optimizer.engine.translators.synth_lang_translator import (
    enhanced_python_to_synthlang,
    python_to_synthlang_node_map,
    python_to_synthlang
)

# Import semantic compression engine
from input_optimizer.engine.semantic_compression_engine import (
    SemanticAwareCompressionEngine,
    create_compression_engine
)

# Import adapter for tier-based compression
from input_optimizer.engine.adapter import adapt_compression

# Import session manager for tracking
from core.session_manager import SecureSessionManager

# Import production error handler
from core.error_handler import ProductionErrorHandler, create_error_handler

# Environment Configuration
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8000"))
METRICS_ENABLED = os.getenv("METRICS_ENABLED", "true").lower() == "true"

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

# Initialize session manager for tracking compression/translation flows
session_manager = SecureSessionManager()

# Initialize production error handler
error_handler = create_error_handler(fastapi_logger.logger)

# Request/Response Models
class MinifyRequest(BaseModel):
    code: str = Field(..., description="Python source code to minify", min_length=1, max_length=1000000)
    aggressive: Optional[bool] = Field(False, description="Enable aggressive optimizations (variable name shortening)")
    validate_output: Optional[bool] = Field(True, description="Validate minified output by re-parsing")
    compression_depth: Optional[int] = Field(None, description="Compression level (1-4): 1=basic, 2=constants, 3=variables, 4=aggressive")
    compression_type: Optional[str] = Field("standard", description="Compression type: 'minimal', 'standard', 'aggressive', 'emergency'")
    
    @validator('compression_depth')
    def validate_compression_depth(cls, v):
        if v is not None and (v < 1 or v > 4):
            raise ValueError('compression_depth must be between 1 and 4')
        return v
    
    @validator('compression_type')
    def validate_compression_type(cls, v):
        valid_types = ['minimal', 'standard', 'aggressive', 'emergency']
        if v not in valid_types:
            raise ValueError(f'compression_type must be one of: {valid_types}')
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
    session_id: Optional[str] = Field(None, description="Session ID for tracking this compression")
    tokens_saved: Optional[int] = Field(None, description="Number of tokens saved")
    compression_ratio: Optional[float] = Field(None, description="Compression ratio achieved")

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

# Semantic Compression Models
class SemanticCompressionRequest(BaseModel):
    code: str = Field(..., description="Python source code to compress", min_length=1, max_length=1000000)
    similarity_threshold: Optional[float] = Field(0.7, description="Minimum similarity score to maintain", ge=0.0, le=1.0)
    preserve_semantics: Optional[bool] = Field(True, description="Enable semantic preservation mode")
    
    @validator('code')
    def validate_code_not_empty(cls, v):
        if not v.strip():
            raise ValueError('code cannot be empty or whitespace only')
        return v

class SemanticCompressionResponse(BaseModel):
    original_code: str = Field(..., description="Original Python code")
    compressed_code: str = Field(..., description="Compressed Python code")
    original_tokens: int = Field(..., description="Original token count")
    compressed_tokens: int = Field(..., description="Compressed token count")
    tokens_saved: int = Field(..., description="Number of tokens saved")
    compression_ratio: float = Field(..., description="Compression ratio (0.0 to 1.0)")
    compression_percentage: float = Field(..., description="Compression percentage")
    similarity_score: float = Field(..., description="Semantic similarity score (0.0 to 1.0)")
    meets_threshold: bool = Field(..., description="Whether similarity meets threshold")
    stage_breakdown: Dict[str, Dict[str, Any]] = Field(..., description="Breakdown by compression stage")
    processing_time_ms: float = Field(..., description="Processing time in milliseconds")

class CompressionComparisonRequest(BaseModel):
    code: str = Field(..., description="Python source code to analyze", min_length=1, max_length=1000000)
    include_maximum: Optional[bool] = Field(True, description="Include maximum compression analysis")
    similarity_threshold: Optional[float] = Field(0.7, description="Similarity threshold for semantic compression")
    
    @validator('code')
    def validate_code_not_empty(cls, v):
        if not v.strip():
            raise ValueError('code cannot be empty or whitespace only')
        return v

class CompressionComparisonResponse(BaseModel):
    original: Dict[str, Any] = Field(..., description="Original code analysis")
    semantic_compression: Dict[str, Any] = Field(..., description="Semantic compression results")
    maximum_compression: Optional[Dict[str, Any]] = Field(None, description="Maximum compression results")
    recommendation: Dict[str, str] = Field(..., description="Recommended compression method with reason")
    analysis: Dict[str, Any] = Field(..., description="Code characteristics analysis")

# Global state for tracking uptime
app.start_time = time.time()

# Initialize compression engines
semantic_engine = create_compression_engine(similarity_threshold=0.7)

@app.get("/health", response_model=HealthResponse, tags=["Health"])
async def health_check():
    """Health check endpoint to verify service status."""
    return HealthResponse(
        status="healthy",
        timestamp=datetime.utcnow().isoformat(),
        version="1.0.0",
        uptime_seconds=time.time() - app.start_time
    )

@app.get("/dashboard", response_class=HTMLResponse, tags=["Dashboard"])
async def dashboard():
    """Interactive web dashboard for demos"""
    try:
        dashboard_path = Path(__file__).parent / "static" / "dashboard.html"
        with open(dashboard_path, 'r', encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        return """
        <html>
        <body>
            <h1>Dashboard Not Found</h1>
            <p>The dashboard HTML file could not be found. Please check the static directory.</p>
        </body>
        </html>
        """

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
    - Session tracking for compression flows
    
    Token estimation uses len(minified)//4 which approximates:
    - 4 characters per token on average for minified Python code
    - Accounts for reduced whitespace and shorter identifiers
    - Provides conservative estimates suitable for LLM context planning
    """
    start_time = time.time()
    request_id = http_request.headers.get("x-request-id", "unknown")
    
    # Create session for tracking
    session_id = None
    session = None
    
    try:
        # Create session for tracking this compression
        temp_file_path = Path(f"/tmp/minify_{request_id}.py")
        session_id = session_manager.create_session(
            file_path=temp_file_path,
            agent="api",
            compressed_content="",  # Will be updated after compression
            metadata={
                "compression_type": request.compression_type,
                "request_id": request_id,
                "start_time": start_time
            }
        )
        
        # Log the minification request
        fastapi_logger.log_token_metrics({
            "event": "minification_request",
            "request_id": request_id,
            "session_id": session_id,
            "original_code_length": len(request.code),
            "aggressive_mode": request.aggressive,
            "compression_depth": request.compression_depth,
            "compression_type": request.compression_type,
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
        
        # Calculate tokens saved and compression ratio
        original_tokens = estimate_tokens(
            request.code,
            method="tiktoken",
            model_type="gpt-4",
            operation_id=request_id
        )
        tokens_saved = original_tokens - estimated_tokens
        compression_ratio = estimated_tokens / original_tokens if original_tokens > 0 else 1.0
        
        # Determine compression depth used
        if request.compression_depth is not None:
            compression_depth_used = request.compression_depth
        else:
            compression_depth_used = CompressionDepth.AGGRESSIVE if request.aggressive else CompressionDepth.CONSTANTS
        
        # Update session with results
        if session_id:
            session_manager.update_session(session_id, {
                "compressed_content": minified_code,
                "tokens_saved": tokens_saved,
                "compression_ratio": compression_ratio,
                "processing_time_ms": processing_time_ms,
                "success": True
            })
        
        # Log successful minification with enhanced metrics
        fastapi_logger.log_token_metrics({
            "event": "minification_success",
            "request_id": request_id,
            "session_id": session_id,
            "original_size": original_size,
            "minified_size": minified_size,
            "size_reduction_percent": size_reduction_percent,
            "estimated_tokens": estimated_tokens,
            "tokens_saved": tokens_saved,
            "compression_ratio": compression_ratio,
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
            compression_depth_used=compression_depth_used,
            session_id=session_id,
            tokens_saved=tokens_saved,
            compression_ratio=round(compression_ratio, 4)
        )
        
    except ValueError as e:
        # Handle validation errors (invalid Python code, etc.)
        if session_id:
            session_manager.update_session(session_id, {"error": str(e), "success": False})
            
        fastapi_logger.log_token_metrics({
            "event": "minification_validation_error",
            "request_id": request_id,
            "session_id": session_id,
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
        if session_id:
            session_manager.update_session(session_id, {"error": str(e), "success": False})
            
        fastapi_logger.log_token_metrics({
            "event": "minification_syntax_error",
            "request_id": request_id,
            "session_id": session_id,
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
        if session_id:
            session_manager.update_session(session_id, {"error": str(e), "success": False})
            
        fastapi_logger.log_token_metrics({
            "event": "minification_unexpected_error",
            "request_id": request_id,
            "session_id": session_id,
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

@app.post("/compress/semantic", response_model=SemanticCompressionResponse, tags=["Semantic Compression"])
async def compress_semantic(request: SemanticCompressionRequest):
    """
    Apply semantic-aware compression that balances token efficiency with similarity preservation.
    
    This endpoint uses intelligent compression strategies including:
    - AST-aware identifier compression
    - Smart docstring optimization
    - Context-aware token reduction
    - Semantic notation substitution
    
    Returns detailed analysis with stage-by-stage breakdown.
    """
    start_time = time.time()
    request_id = str(int(time.time() * 1000))
    
    try:
        fastapi_logger.log_token_metrics({
            "event": "semantic_compression_request",
            "request_id": request_id,
            "similarity_threshold": request.similarity_threshold,
            "code_length": len(request.code)
        })
        
        # Set similarity threshold
        semantic_engine.similarity_threshold = request.similarity_threshold
        
        # Perform compression
        result = semantic_engine.compress(request.code, request.preserve_semantics)
        
        processing_time_ms = (time.time() - start_time) * 1000
        
        # Format stage breakdown for response
        stage_breakdown = {}
        for stage_name, stage_data in result.get('stage_results', {}).items():
            stage_breakdown[stage_name] = {
                'tokens_saved': stage_data.get('tokens_saved', 0),
                'compression_ratio': stage_data.get('compression_ratio', 0),
                'description': f"Stage: {stage_name.replace('_', ' ').title()}"
            }
        
        fastapi_logger.log_token_metrics({
            "event": "semantic_compression_completed",
            "request_id": request_id,
            "compression_percentage": result['compression_percentage'],
            "similarity_score": result['similarity_score'],
            "tokens_saved": result['tokens_saved'],
            "processing_time_ms": processing_time_ms
        })
        
        return SemanticCompressionResponse(
            original_code=result['original_code'],
            compressed_code=result['compressed_code'],
            original_tokens=result['original_tokens'],
            compressed_tokens=result['compressed_tokens'],
            tokens_saved=result['tokens_saved'],
            compression_ratio=result['compression_ratio'],
            compression_percentage=result['compression_percentage'],
            similarity_score=result['similarity_score'],
            meets_threshold=result['meets_threshold'],
            stage_breakdown=stage_breakdown,
            processing_time_ms=processing_time_ms
        )
        
    except ValueError as e:
        # Use error handler for validation errors
        context = {
            'code': request.code,
            'operation_id': request_id,
            'endpoint': 'semantic_compression',
            'error_type': 'validation'
        }
        
        recovery_result = await error_handler.handle_compression_error(e, context)
        
        fastapi_logger.log_token_metrics({
            "event": "semantic_compression_validation_error_recovered",
            "request_id": request_id,
            "error_type": "ValueError",
            "error_message": str(e),
            "recovery_strategy": recovery_result['error_recovery']['strategy_used']
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
    except Exception as e:
        # Use error handler for general compression errors
        context = {
            'code': request.code,
            'operation_id': request_id,
            'endpoint': 'semantic_compression',
            'error_type': 'compression'
        }
        
        try:
            recovery_result = await error_handler.handle_compression_error(e, context)
            
            # Log successful error recovery
            fastapi_logger.log_token_metrics({
                "event": "semantic_compression_error_recovered",
                "request_id": request_id,
                "error_type": type(e).__name__,
                "error_message": str(e),
                "recovery_strategy": recovery_result['error_recovery']['strategy_used'],
                "recovery_time_ms": recovery_result['error_recovery']['recovery_time_ms']
            })
            
            # Return recovered result instead of throwing error
            stage_breakdown = {}
            for stage_name, stage_data in recovery_result.get('stage_results', {}).items():
                stage_breakdown[stage_name] = {
                    'tokens_saved': stage_data.get('tokens_saved', 0),
                    'compression_ratio': stage_data.get('compression_ratio', 0),
                    'description': f"Stage: {stage_name.replace('_', ' ').title()}"
                }
            
            processing_time_ms = recovery_result['error_recovery']['recovery_time_ms']
            
            return SemanticCompressionResponse(
                original_code=request.code,
                compressed_code=recovery_result['compressed_code'],
                original_tokens=estimate_tokens(request.code),
                compressed_tokens=estimate_tokens(recovery_result['compressed_code']),
                tokens_saved=max(0, estimate_tokens(request.code) - estimate_tokens(recovery_result['compressed_code'])),
                compression_ratio=recovery_result.get('compression_ratio', 0.0),
                compression_percentage=recovery_result.get('compression_ratio', 0.0) * 100,
                similarity_score=recovery_result.get('similarity_score', 1.0),
                meets_threshold=recovery_result.get('similarity_score', 1.0) >= request.similarity_threshold,
                stage_breakdown=stage_breakdown,
                processing_time_ms=processing_time_ms
            )
            
        except Exception as recovery_error:
            # If error recovery also fails, log and raise original error
            fastapi_logger.log_token_metrics({
                "event": "semantic_compression_error_recovery_failed",
                "request_id": request_id,
                "original_error": str(e),
                "recovery_error": str(recovery_error)
            })
            
            raise HTTPException(
                status_code=500,
                detail=ErrorResponse(
                    error="CompressionError",
                    message=f"Failed to perform semantic compression: {str(e)}",
                    timestamp=datetime.utcnow().isoformat(),
                    request_id=request_id
                ).dict()
            )

@app.post("/compress/compare", response_model=CompressionComparisonResponse, tags=["Semantic Compression"])
async def compare_compression_methods(request: CompressionComparisonRequest):
    """
    Compare different compression methods and provide recommendations.
    
    Analyzes code with both semantic-aware and maximum compression approaches,
    then recommends the best method based on compression ratio and similarity preservation.
    """
    start_time = time.time()
    request_id = str(int(time.time() * 1000))
    
    try:
        fastapi_logger.log_token_metrics({
            "event": "compression_comparison_request", 
            "request_id": request_id,
            "similarity_threshold": request.similarity_threshold,
            "include_maximum": request.include_maximum
        })

        # Analyze code characteristics
        analysis = _analyze_code_characteristics(request.code)        # Run semantic compression
        semantic_engine.similarity_threshold = request.similarity_threshold
        semantic_result = semantic_engine.compress(request.code)
        
        # Prepare results
        original_tokens = estimate_tokens(request.code)
        
        comparison_result = {
            'original': {
                'code': request.code,
                'tokens': original_tokens,
                'size': len(request.code)
            },
            'semantic_compression': {
                'code': semantic_result['compressed_code'],
                'tokens': semantic_result['compressed_tokens'],
                'size': len(semantic_result['compressed_code']),
                'compression_ratio': semantic_result['compression_ratio'],
                'compression_percentage': semantic_result['compression_percentage'],
                'similarity_score': semantic_result['similarity_score'],
                'tokens_saved': semantic_result['tokens_saved'],
                'meets_threshold': semantic_result['meets_threshold']
            }
        }
        
        # Add maximum compression if requested
        maximum_result = None
        if request.include_maximum:
            try:
                # Import maximum compression pipeline if available
                from input_optimizer.samples.chaining.maximum_compression_pipeline import maximum_compression_pipeline
                max_result = maximum_compression_pipeline(request.code)
                maximum_result = {
                    'code': max_result['final']['code'],
                    'tokens': max_result['final']['tokens'],
                    'size': max_result['final']['size'],
                    'compression_ratio': max_result['pipeline_stats']['total_reduction'] / 100,
                    'compression_percentage': max_result['pipeline_stats']['total_reduction'],
                    'similarity_score': 0.25,  # Estimated low similarity for maximum compression
                    'tokens_saved': max_result['original']['tokens'] - max_result['final']['tokens']
                }
            except ImportError:
                fastapi_logger.log_token_metrics({
                    "event": "maximum_compression_unavailable",
                    "request_id": request_id
                })

        # Determine recommendation
        recommendation = _get_compression_recommendation(
            comparison_result['semantic_compression'],
            maximum_result,
            request.similarity_threshold,
            analysis
        )
        
        processing_time_ms = (time.time() - start_time) * 1000

        fastapi_logger.log_token_metrics({
            "event": "compression_comparison_completed",
            "request_id": request_id,
            "processing_time_ms": processing_time_ms
        })

        return CompressionComparisonResponse(
            original=comparison_result['original'],
            semantic_compression=comparison_result['semantic_compression'],
            maximum_compression=maximum_result,
            recommendation=recommendation,
            analysis=analysis
        )
        
    except Exception as e:
        fastapi_logger.log_token_metrics({
            "event": "compression_comparison_error",
            "request_id": request_id,
            "error_type": type(e).__name__,
            "error_message": str(e)
        })
        raise HTTPException(
            status_code=500,
            detail=ErrorResponse(
                error="ComparisonError",
                message="Failed to compare compression methods",
                timestamp=datetime.utcnow().isoformat(),
                request_id=request_id
            ).dict()
        )

# WebSocket Models and Functions
class CompressionProgressResponse(BaseModel):
    status: str = Field(..., description="Current status: 'analyzing', 'compressing', 'complete', 'error'")
    progress: int = Field(..., description="Progress percentage (0-100)")
    message: Optional[str] = Field(None, description="Status message")
    compressed: Optional[str] = Field(None, description="Compressed code (only when complete)")
    metrics: Optional[Dict[str, Any]] = Field(None, description="Compression metrics (only when complete)")

async def compress_with_progress(code: str, websocket: WebSocket, compression_type: str = "semantic") -> Dict[str, Any]:
    """
    Perform compression with progress updates via WebSocket.
    
    Args:
        code: Source code to compress
        websocket: WebSocket connection for progress updates
        compression_type: Type of compression ('semantic', 'standard', 'aggressive')
    
    Returns:
        Dictionary with compressed code and metrics
    """
    request_id = str(int(time.time() * 1000))
    
    try:
        # Phase 1: Code Analysis (25% progress)
        await websocket.send_json({
            "status": "analyzing", 
            "progress": 25,
            "message": "Analyzing code structure and characteristics..."
        })
        
        analysis = _analyze_code_characteristics(code)
        original_tokens = estimate_tokens(code)
        
        # Phase 2: Preparing Compression (50% progress)
        await websocket.send_json({
            "status": "compressing", 
            "progress": 50,
            "message": f"Preparing {compression_type} compression..."
        })
        
        # Phase 3: Performing Compression (75% progress)
        await websocket.send_json({
            "status": "compressing", 
            "progress": 75,
            "message": "Applying compression algorithms..."
        })
        
        # Perform the actual compression based on type
        if compression_type == "semantic":
            result = semantic_engine.compress(code)
            compressed_code = result['compressed_code']
            compression_metrics = {
                'compression_ratio': result['compression_ratio'],
                'compression_percentage': result['compression_percentage'],
                'similarity_score': result['similarity_score'],
                'tokens_saved': result['tokens_saved'],
                'meets_threshold': result['meets_threshold'],
                'original_tokens': original_tokens,
                'compressed_tokens': result['compressed_tokens']
            }
        else:
            # Use standard minification for other types
            if compression_type == "aggressive":
                minified_result = minify_with_otpm_tracking(
                    code=code,
                    compression_type="aggressive",
                    request_id=request_id
                )
            else:
                minified_result = minify_with_otpm_tracking(
                    code=code,
                    compression_type="standard",
                    request_id=request_id
                )
            
            # Handle the result keys properly
            compressed_code = minified_result.get('minified') or minified_result.get('compressed_code', code)
            compressed_tokens = estimate_tokens(compressed_code)
            compression_metrics = {
                'compression_ratio': compressed_tokens / original_tokens if original_tokens > 0 else 1.0,
                'compression_percentage': ((original_tokens - compressed_tokens) / original_tokens * 100) if original_tokens > 0 else 0,
                'original_tokens': original_tokens,
                'compressed_tokens': compressed_tokens,
                'tokens_saved': original_tokens - compressed_tokens,
                'otpm_status': minified_result.get('otpm_status', 'unknown'),
                'remaining_pct': minified_result.get('remaining_pct', 100.0)
            }
        
        # Phase 4: Complete (100% progress)
        final_result = {
            "status": "complete",
            "progress": 100,
            "compressed": compressed_code,
            "metrics": compression_metrics
        }
        
        return final_result
        
    except Exception as e:
        error_result = {
            "status": "error",
            "progress": 0,
            "message": f"Compression failed: {str(e)}",
            "error_type": type(e).__name__
        }
        await websocket.send_json(error_result)
        return error_result

@app.websocket("/ws/compress")
async def websocket_compress(websocket: WebSocket):
    """
    WebSocket endpoint for real-time compression with progress updates.
    
    Expected input format:
    {
        "code": "string",
        "compression_type": "semantic|standard|aggressive",
        "similarity_threshold": 0.85 (optional, for semantic compression)
    }
    
    Progress updates will be sent with status and progress percentage.
    Final result includes compressed code and detailed metrics.
    """
    await websocket.accept()
    
    try:
        while True:
            # Receive data from client
            data = await websocket.receive_text()
            
            try:
                # Parse the incoming request
                request_data = json.loads(data)
                code = request_data.get("code", "")
                compression_type = request_data.get("compression_type", "semantic")
                similarity_threshold = request_data.get("similarity_threshold", 0.85)
                
                if not code.strip():
                    await websocket.send_json({
                        "status": "error",
                        "progress": 0,
                        "message": "Code cannot be empty"
                    })
                    continue
                
                # Set similarity threshold for semantic compression
                if compression_type == "semantic":
                    semantic_engine.similarity_threshold = similarity_threshold
                
                # Log the request
                fastapi_logger.info(f"WebSocket compression request: type={compression_type}, length={len(code)}")
                
                # Perform compression with progress updates
                result = await compress_with_progress(code, websocket, compression_type)
                
                # Send final result
                await websocket.send_json(result)
                
                # Log completion
                if result["status"] == "complete":
                    fastapi_logger.info(f"WebSocket compression completed: type={compression_type}, saved={result['metrics'].get('tokens_saved', 0)} tokens")
                
            except json.JSONDecodeError as e:
                await websocket.send_json({
                    "status": "error",
                    "progress": 0,
                    "message": f"Invalid JSON format: {str(e)}"
                })
            except Exception as e:
                # Use error handler for WebSocket compression errors
                context = {
                    'code': code,
                    'operation_id': f'websocket_{int(time.time() * 1000)}',
                    'endpoint': 'websocket_compression',
                    'compression_type': compression_type,
                    'error_type': 'websocket_compression'
                }
                
                try:
                    recovery_result = await error_handler.handle_compression_error(e, context)
                    
                    # Send recovery result to client
                    await websocket.send_json({
                        "status": "complete",
                        "progress": 100,
                        "message": "Compression completed with error recovery",
                        "error_recovery": {
                            "strategy_used": recovery_result['error_recovery']['strategy_used'],
                            "original_error": str(e)
                        },
                        "metrics": {
                            "compression_percentage": recovery_result.get('compression_ratio', 0.0) * 100,
                            "similarity_score": recovery_result.get('similarity_score', 1.0),
                            "tokens_saved": max(0, estimate_tokens(code) - estimate_tokens(recovery_result['compressed_code'])),
                            "recovery_time_ms": recovery_result['error_recovery']['recovery_time_ms']
                        },
                        "compressed_code": recovery_result['compressed_code']
                    })
                    
                except Exception as recovery_error:
                    # If recovery also fails, send error message
                    await websocket.send_json({
                        "status": "error",
                        "progress": 0,
                        "message": f"Processing error: {str(e)}",
                        "error_type": type(e).__name__,
                        "recovery_failed": True,
                        "recovery_error": str(recovery_error)
                    })
                
    except WebSocketDisconnect:
        fastapi_logger.info("WebSocket client disconnected normally")
    except Exception as e:
        fastapi_logger.error(f"WebSocket error: {type(e).__name__}: {str(e)}")

def _analyze_code_characteristics(code: str) -> Dict[str, Any]:
    """Analyze code to determine optimal compression strategy"""
    lines = code.split('\n')
    total_lines = len(lines)
    
    docstring_lines = 0
    comment_lines = 0
    code_lines = 0
    
    for line in lines:
        stripped = line.strip()
        if '"""' in stripped or "'''" in stripped:
            docstring_lines += 1
        elif stripped.startswith('#'):
            comment_lines += 1
        elif stripped:
            code_lines += 1
    
    # Calculate complexity indicators
    complexity_indicators = [
        'class ', 'def ', 'async ', 'await', 'try:', 'except', 'finally:',
        'with ', 'lambda', 'yield', 'import', 'from '
    ]
    
    complexity_score = sum(code.count(indicator) for indicator in complexity_indicators) / max(len(code), 1)
    
    return {
        'total_lines': total_lines,
        'code_lines': code_lines,
        'comment_lines': comment_lines,
        'docstring_lines': docstring_lines,
        'comment_ratio': comment_lines / max(total_lines, 1),
        'docstring_ratio': docstring_lines / max(total_lines, 1),
        'has_docstrings': docstring_lines > 0,
        'complexity_score': complexity_score,
        'estimated_tokens': estimate_tokens(code)
    }

def _get_compression_recommendation(semantic_result: Dict, maximum_result: Optional[Dict], 
                                  similarity_threshold: float, analysis: Dict) -> Dict[str, str]:
    """Generate compression method recommendation"""
    
    # If semantic compression meets threshold and provides good compression
    if semantic_result['meets_threshold'] and semantic_result['compression_percentage'] >= 15:
        return {
            'method': 'semantic_compression',
            'reason': f"High similarity ({semantic_result['similarity_score']:.2f}) with good compression ({semantic_result['compression_percentage']:.1f}%)"
        }
    
    # If maximum compression is available and significantly better
    if maximum_result and maximum_result['compression_percentage'] > semantic_result['compression_percentage'] * 1.5:
        return {
            'method': 'maximum_compression',
            'reason': f"Significantly better compression ({maximum_result['compression_percentage']:.1f}% vs {semantic_result['compression_percentage']:.1f}%)"
        }
    
    # For simple code with high documentation, semantic works well
    if analysis['has_docstrings'] and analysis['complexity_score'] < 0.3:
        return {
            'method': 'semantic_compression',
            'reason': f"Well-documented simple code benefits from semantic preservation"
        }
    
    # Default to semantic for safety
    return {
        'method': 'semantic_compression',
        'reason': f"Balanced approach with {semantic_result['similarity_score']:.2f} similarity and {semantic_result['compression_percentage']:.1f}% compression"
    }


def get_example_for_endpoint(path: str, method: str) -> str:
    """
    Generate code examples for API endpoints.
    
    Args:
        path: API endpoint path  
        method: HTTP method
        
    Returns:
        Python code example for the endpoint
    """
    examples = {
        ("/minify", "post"): '''
import requests

response = requests.post(
    "http://localhost:8000/minify",
    json={
        "code": "def hello_world():\\n    print('Hello, World!')",
        "compress_strings": True,
        "compress_vars": True
    }
)
print(response.json())
        '''.strip(),
        
        ("/minify/stats", "post"): '''
import requests

response = requests.post(
    "http://localhost:8000/minify/stats", 
    json={
        "code": "class Calculator:\\n    def add(self, a, b):\\n        return a + b",
        "compress_strings": True,
        "compress_vars": True
    }
)
stats = response.json()
print(f"Compression: {stats['compression_percentage']:.1f}%")
        '''.strip(),
        
        ("/translate/sudolang", "post"): '''
import requests

response = requests.post(
    "http://localhost:8000/translate/sudolang",
    json={
        "code": "for i in range(10):\\n    if i % 2 == 0:\\n        print(i)"
    }
)
print(response.json()['sudolang_translation'])
        '''.strip(),
        
        ("/translate/synthlang", "post"): '''
import requests

response = requests.post(
    "http://localhost:8000/translate/synthlang",
    json={
        "code": "def fibonacci(n):\\n    return n if n <= 1 else fibonacci(n-1) + fibonacci(n-2)"
    }
)
print(response.json()['synthlang_translation'])
        '''.strip(),
        
        ("/compress/semantic", "post"): '''
import requests

response = requests.post(
    "http://localhost:8000/compress/semantic",
    json={
        "code": "def process_data(data):\\n    results = []\\n    for item in data:\\n        if item.is_valid():\\n            results.append(item.transform())\\n    return results",
        "compression_level": "moderate"
    }
)
compressed = response.json()
print(f"Original: {compressed['original_tokens']} tokens")
print(f"Compressed: {compressed['compressed_tokens']} tokens")
        '''.strip(),
        
        ("/health", "get"): '''
import requests

response = requests.get("http://localhost:8000/health")
health = response.json()
print(f"Status: {health['status']}")
print(f"Uptime: {health['uptime_seconds']:.1f}s")
        '''.strip(),
        
        ("/metrics", "get"): '''
import requests

response = requests.get("http://localhost:8000/metrics")
metrics = response.text
print("Prometheus Metrics:")
print(metrics[:500] + "..." if len(metrics) > 500 else metrics)
        '''.strip()
    }
    
    return examples.get((path, method), f'''
import requests

response = requests.{method}("http://localhost:8000{path}")
print(response.json())
    '''.strip())


def custom_openapi():
    """
    Generate comprehensive OpenAPI documentation with examples.
    
    Returns:
        Custom OpenAPI schema with enhanced documentation
    """
    if app.openapi_schema:
        return app.openapi_schema
        
    # Log documentation generation
    fastapi_logger.info("Generating comprehensive OpenAPI documentation")
    
    openapi_schema = get_openapi(
        title="OptimizeAI API",
        version="1.0.0",
        description="""
        ## Overview
        OptimizeAI provides intelligent code compression and translation for AI workflows.
        
        ## Key Features
        - **40-87% token reduction** across different compression tiers
        - **Semantic preservation** maintaining code functionality
        - **Multi-tier compression** (basic, moderate, aggressive, maximum)
        - **Real-time processing** with comprehensive monitoring
        - **Translation support** for SudoLang and SynthLang
        - **Chained transformations** for complex workflows
        - **Production monitoring** with Prometheus metrics
        
        ## Quick Start
        ```python
        import requests
        
        # Basic minification
        response = requests.post(
            "http://localhost:8000/minify",
            json={"code": "def hello(): print('world')"}
        )
        result = response.json()
        print(f"Compressed: {result['minified_code']}")
        print(f"Reduction: {result['compression_percentage']:.1f}%")
        ```
        
        ## Compression Tiers
        - **Basic**: Safe compression with variable/string optimization
        - **Moderate**: Balanced approach with semantic analysis  
        - **Aggressive**: High compression with advanced techniques
        - **Maximum**: Extreme compression for maximum token reduction
        
        ## Translation Languages
        - **SudoLang**: Natural language pseudocode representation
        - **SynthLang**: Synthetic compact language for AI processing
        
        ## Monitoring & Analytics
        - Real-time performance metrics via `/health` and `/metrics`
        - Comprehensive compression analytics and reporting
        - Error tracking with detailed logging
        - WebSocket support for live monitoring
        
        ## Rate Limits
        - Standard: 1000 requests/hour
        - Premium: 10000 requests/hour
        - Enterprise: Unlimited
        
        ## Support
        - Documentation: `/docs` (this page)
        - Health Check: `/health`
        - Metrics: `/metrics`
        - Dashboard: `/dashboard`
        """,
        routes=app.routes,
    )
    
    # Add code examples to each endpoint
    try:
        for path in openapi_schema["paths"]:
            for method in openapi_schema["paths"][path]:
                if "x-code-samples" not in openapi_schema["paths"][path][method]:
                    openapi_schema["paths"][path][method]["x-code-samples"] = [
                        {
                            "lang": "Python",
                            "source": get_example_for_endpoint(path, method),
                            "label": "Python Requests"
                        },
                        {
                            "lang": "curl", 
                            "source": f'curl -X {method.upper()} "http://localhost:8000{path}" \\' +
                                    ('\n  -H "Content-Type: application/json" \\' if method.lower() != 'get' else '') +
                                    ('\n  -d \'{"code": "def example(): pass"}\'' if method.lower() != 'get' else ''),
                            "label": "cURL"
                        }
                    ]
                    
                # Add detailed response examples
                if "responses" in openapi_schema["paths"][path][method]:
                    for status_code in openapi_schema["paths"][path][method]["responses"]:
                        if status_code == "200" and "content" in openapi_schema["paths"][path][method]["responses"][status_code]:
                            response_content = openapi_schema["paths"][path][method]["responses"][status_code]["content"]
                            if "application/json" in response_content:
                                if "examples" not in response_content["application/json"]:
                                    response_content["application/json"]["examples"] = {
                                        "success_example": {
                                            "summary": "Successful Response",
                                            "value": _get_example_response(path, method)
                                        }
                                    }
        
        # Add comprehensive tags descriptions
        openapi_schema["tags"] = [
            {
                "name": "Health",
                "description": "System health monitoring and status checks"
            },
            {
                "name": "Dashboard", 
                "description": "Web-based monitoring dashboard interface"
            },
            {
                "name": "Minification",
                "description": "Code compression and minification services"
            },
            {
                "name": "Translation",
                "description": "Code translation to specialized languages"
            },
            {
                "name": "Chained Transformations",
                "description": "Complex multi-step code transformations"
            },
            {
                "name": "Semantic Compression", 
                "description": "Advanced semantic-aware compression techniques"
            },
            {
                "name": "Monitoring",
                "description": "System metrics and performance monitoring"
            }
        ]
        
        fastapi_logger.info("OpenAPI documentation generated successfully with examples")
        
    except Exception as e:
        fastapi_logger.error(f"Error enhancing OpenAPI documentation: {e}")
    
    app.openapi_schema = openapi_schema
    return app.openapi_schema


def _get_example_response(path: str, method: str) -> Dict[str, Any]:
    """Generate example responses for endpoints"""
    examples = {
        ("/minify", "post"): {
            "minified_code": "def hello():print('world')",
            "original_length": 24,
            "minified_length": 21,
            "compression_percentage": 12.5,
            "status": "success"
        },
        ("/health", "get"): {
            "status": "healthy",
            "uptime_seconds": 3600.5,
            "compressions_per_minute": 45.2,
            "error_rate": 0.001,
            "last_updated": "2025-08-03T10:30:00Z"
        },
        ("/translate/sudolang", "post"): {
            "sudolang_translation": "FOR each number from 0 to 9:\n  IF number is even:\n    PRINT number",
            "original_code": "for i in range(10):\n    if i % 2 == 0:\n        print(i)",
            "translation_time": 0.045,
            "status": "success"
        }
    }
    
    return examples.get((path, method), {"status": "success", "message": "Operation completed"})


# Set custom OpenAPI
app.openapi = custom_openapi

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
        host=HOST,
        port=PORT,
        reload=ENVIRONMENT == "development",
        log_level=LOG_LEVEL.lower(),
        access_log=True
    )