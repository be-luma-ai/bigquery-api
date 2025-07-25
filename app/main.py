"""
BigQuery API Service - Main Application
Production-ready FastAPI service for multi-tenant BigQuery access
"""

import os
import time
from contextlib import asynccontextmanager
from typing import Dict, Any

import structlog
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse, Response
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST

from .config import get_settings
from .auth import AuthMiddleware
from .routers import bigquery, health
from .exceptions import BigQueryAPIException, AuthenticationError

# Configure structured logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer()
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()

# Metrics
REQUEST_COUNT = Counter(
    'http_requests_total', 
    'Total HTTP requests', 
    ['method', 'endpoint', 'status']
)
REQUEST_LATENCY = Histogram(
    'http_request_duration_seconds', 
    'HTTP request latency'
)

# Rate limiter
limiter = Limiter(key_func=get_remote_address)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    # Startup
    logger.info("🚀 Starting BigQuery API Service")
    
    # Initialize any startup services here
    # e.g., database connections, caches, etc.
    
    yield
    
    # Shutdown
    logger.info("🛑 Shutting down BigQuery API Service")

# Initialize FastAPI app
def create_app() -> FastAPI:
    """Create and configure FastAPI application"""
    settings = get_settings()
    
    app = FastAPI(
        title="BigQuery API Service",
        description="Production-ready multi-tenant BigQuery API for analytics",
        version="1.0.0",
        docs_url="/docs" if settings.debug else None,
        redoc_url="/redoc" if settings.debug else None,
        openapi_url="/openapi.json" if settings.debug else None,
        lifespan=lifespan
    )

    # Configure CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID", "X-RateLimit-Remaining"]
    )

    # Add gzip compression
    app.add_middleware(GZipMiddleware, minimum_size=1000)

    # Add rate limiting
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    # Add custom authentication middleware
    app.add_middleware(AuthMiddleware)

    # Add request logging and metrics middleware
    @app.middleware("http")
    async def logging_and_metrics_middleware(request: Request, call_next):
        start_time = time.time()
        
        # Generate request ID
        request_id = f"req_{int(time.time())}_{hash(str(request.url))}"
        
        # Log incoming request
        logger.info(
            "Incoming request",
            method=request.method,
            url=str(request.url),
            client_ip=get_remote_address(request),
            user_agent=request.headers.get("user-agent"),
            request_id=request_id
        )
        
        try:
            response = await call_next(request)
            
            # Calculate metrics
            duration = time.time() - start_time
            REQUEST_LATENCY.observe(duration)
            REQUEST_COUNT.labels(
                method=request.method,
                endpoint=request.url.path,
                status=response.status_code
            ).inc()
            
            # Add response headers
            response.headers["X-Request-ID"] = request_id
            response.headers["X-Response-Time"] = f"{duration:.3f}s"
            
            # Log response
            logger.info(
                "Request completed",
                method=request.method,
                url=str(request.url),
                status_code=response.status_code,
                duration=duration,
                request_id=request_id
            )
            
            return response
            
        except Exception as e:
            duration = time.time() - start_time
            REQUEST_COUNT.labels(
                method=request.method,
                endpoint=request.url.path,
                status=500
            ).inc()
            
            logger.error(
                "Request failed",
                method=request.method,
                url=str(request.url),
                error=str(e),
                duration=duration,
                request_id=request_id,
                exc_info=True
            )
            raise

    # Exception handlers
    @app.exception_handler(BigQueryAPIException)
    async def bigquery_exception_handler(request: Request, exc: BigQueryAPIException):
        logger.error(
            "BigQuery API error",
            error=exc.detail,
            status_code=exc.status_code,
            url=str(request.url)
        )
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": exc.detail,
                "code": getattr(exc, 'code', 'BIGQUERY_ERROR'),
                "timestamp": time.time()
            }
        )

    @app.exception_handler(AuthenticationError)
    async def auth_exception_handler(request: Request, exc: AuthenticationError):
        logger.warning(
            "Authentication error",
            error=exc.detail,
            url=str(request.url),
            client_ip=get_remote_address(request)
        )
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": exc.detail,
                "code": getattr(exc, 'code', 'AUTH_ERROR'),
                "timestamp": time.time()
            }
        )

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": exc.detail,
                "timestamp": time.time()
            }
        )

    @app.exception_handler(Exception)
    async def general_exception_handler(request: Request, exc: Exception):
        logger.error(
            "Unhandled exception",
            error=str(exc),
            url=str(request.url),
            exc_info=True
        )
        return JSONResponse(
            status_code=500,
            content={
                "error": "Internal server error",
                "code": "INTERNAL_ERROR",
                "timestamp": time.time()
            }
        )

    # Include routers
    app.include_router(health.router, prefix="/health", tags=["health"])
    app.include_router(
        bigquery.router, 
        prefix="/api/bigquery", 
        tags=["bigquery"],
        dependencies=[]  # Auth is handled by middleware
    )

    # Metrics endpoint
    @app.get("/metrics")
    async def metrics():
        """Prometheus metrics endpoint"""
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    # Root endpoint
    @app.get("/")
    async def root():
        """Root endpoint with API information"""
        return {
            "service": "BigQuery API",
            "version": "1.0.0",
            "status": "healthy",
            "docs": "/docs" if settings.debug else "disabled",
            "timestamp": time.time()
        }

    return app

# Create app instance
app = create_app()

if __name__ == "__main__":
    import uvicorn
    settings = get_settings()
    
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=settings.port,
        reload=settings.debug,
        access_log=True,
        log_config=None  # Use structlog instead
    ) 