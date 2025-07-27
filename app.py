from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, validator
from typing import Optional, Dict, Any
import time
from datetime import datetime
import uvicorn

# Import our enhanced minifier with logging
from engine.minifier import (
    minify_code, 
    minify_with_stats, 
    estimate_tokens,
    CompressionDepth
)

# Import our logging setup
from utils.logger import setup_minifier_logging, get_logger

# Initialize FastAPI app
app = FastAPI(
    title="Python Code Minifier API",
    description="High-performance Python code minification service with comprehensive logging and metrics",
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
    validate: Optional[bool] = Field(True, description="Validate minified output by re-parsing")
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
            "validation_enabled": request.validate
        })
        
        # Perform minification
        minified_code = minify_code(
            code_str=request.code,
            aggressive=request.aggressive,
            validate=request.validate,
            compression_depth=request.compression_depth
        )
        
        # Calculate metrics
        original_size = len(request.code)
        minified_size = len(minified_code)
        size_reduction = original_size - minified_size
        size_reduction_percent = (size_reduction / original_size * 100) if original_size > 0 else 0
        processing_time_ms = (time.time() - start_time) * 1000
        
        # Simple token estimation: len(minified) // 4
        # This is a fast, conservative estimate based on the observation that
        # minified Python code averages about 4 characters per token
        estimated_tokens = len(minified_code) // 4
        
        # Determine compression depth used
        if request.compression_depth is not None:
            compression_depth_used = request.compression_depth
        else:
            compression_depth_used = CompressionDepth.AGGRESSIVE if request.aggressive else CompressionDepth.CONSTANTS
        
        # Log successful minification
        fastapi_logger.log_token_metrics({
            "event": "minification_success",
            "request_id": request_id,
            "original_size": original_size,
            "minified_size": minified_size,
            "size_reduction_percent": size_reduction_percent,
            "estimated_tokens": estimated_tokens,
            "processing_time_ms": processing_time_ms,
            "compression_depth_used": compression_depth_used
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
        # Perform minification with detailed stats
        minified_code, stats = minify_with_stats(
            code_str=request.code,
            aggressive=request.aggressive or (request.compression_depth and request.compression_depth >= CompressionDepth.VARIABLES)
        )
        
        # Simple token estimation: len(minified) // 4
        estimated_tokens = len(minified_code) // 4
        
        # Add token estimation to stats
        stats["estimated_tokens"] = estimated_tokens
        stats["token_estimation_method"] = "len_divided_by_4"
        
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

@app.get("/metrics", tags=["Monitoring"])
async def get_service_metrics():
    """
    Get service-level metrics and statistics.
    
    Returns basic service metrics for monitoring and health checking.
    """
    return {
        "service": "python-minifier-api",
        "version": "1.0.0",
        "uptime_seconds": time.time() - app.start_time,
        "timestamp": datetime.utcnow().isoformat(),
        "status": "operational"
    }

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
    print("🚀 Python Minifier API starting up...")
    print("📊 Comprehensive logging enabled")
    print("🔧 Minifier with optimization ready")
    print("✅ API ready to accept requests")

# Shutdown event
@app.on_event("shutdown")
async def shutdown_event():
    """Application shutdown tasks."""
    print("🛑 Python Minifier API shutting down...")
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