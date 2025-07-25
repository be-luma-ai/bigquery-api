"""
Health check endpoints for monitoring and load balancer health checks
"""

import time
import os
from typing import Dict, Any

import structlog
from fastapi import APIRouter, Depends
from google.cloud import bigquery
from google.cloud import firestore

from ..config import get_settings, Settings

logger = structlog.get_logger()
router = APIRouter()


async def check_bigquery_connection(settings: Settings = Depends(get_settings)) -> Dict[str, Any]:
    """Check BigQuery connectivity"""
    try:
        client = bigquery.Client(project=settings.gcp_project_id)
        # Simple query to test connection
        query = "SELECT 1 as test_value"
        job = client.query(query)
        results = list(job.result())
        
        return {
            "status": "healthy",
            "service": "bigquery",
            "project_id": settings.gcp_project_id,
            "response_time_ms": 0  # Could measure actual time
        }
    except Exception as e:
        logger.error("BigQuery health check failed", error=str(e))
        return {
            "status": "unhealthy",
            "service": "bigquery",
            "error": str(e)
        }


async def check_firestore_connection(settings: Settings = Depends(get_settings)) -> Dict[str, Any]:
    """Check Firestore connectivity"""
    try:
        db = firestore.Client(project=settings.firebase_project_id)
        # Try to read from a collection (without actually reading documents)
        collections = db.collections()
        # Just check if we can list collections
        collection_names = [col.id for col in collections]
        
        return {
            "status": "healthy",
            "service": "firestore",
            "project_id": settings.firebase_project_id,
            "collections_accessible": len(collection_names)
        }
    except Exception as e:
        logger.error("Firestore health check failed", error=str(e))
        return {
            "status": "unhealthy",
            "service": "firestore",
            "error": str(e)
        }


@router.get("/")
@router.get("/live")
async def liveness_check():
    """
    Liveness probe - indicates if the application is running
    Used by Kubernetes/Cloud Run to determine if container should be restarted
    """
    return {
        "status": "alive",
        "timestamp": time.time(),
        "service": "bigquery-api",
        "version": "1.0.0"
    }


@router.get("/ready")
async def readiness_check(settings: Settings = Depends(get_settings)):
    """
    Readiness probe - indicates if the application is ready to serve traffic
    Used by load balancers to determine if traffic should be routed to this instance
    """
    checks = {}
    overall_status = "ready"
    
    # Check BigQuery connectivity
    bigquery_check = await check_bigquery_connection(settings)
    checks["bigquery"] = bigquery_check
    if bigquery_check["status"] != "healthy":
        overall_status = "not_ready"
    
    # Check Firestore connectivity
    firestore_check = await check_firestore_connection(settings)
    checks["firestore"] = firestore_check
    if firestore_check["status"] != "healthy":
        overall_status = "not_ready"
    
    # Check environment configuration
    config_issues = []
    if not settings.gcp_project_id:
        config_issues.append("Missing GCP_PROJECT_ID")
    if not settings.firebase_project_id:
        config_issues.append("Missing FIREBASE_PROJECT_ID")
    
    checks["configuration"] = {
        "status": "healthy" if not config_issues else "unhealthy",
        "issues": config_issues
    }
    
    if config_issues:
        overall_status = "not_ready"
    
    status_code = 200 if overall_status == "ready" else 503
    
    response = {
        "status": overall_status,
        "timestamp": time.time(),
        "checks": checks,
        "service": "bigquery-api",
        "version": "1.0.0"
    }
    
    if overall_status != "ready":
        logger.warning("Readiness check failed", checks=checks)
    
    return response


@router.get("/health")
async def health_check(settings: Settings = Depends(get_settings)):
    """
    Comprehensive health check with detailed component status
    """
    start_time = time.time()
    
    checks = {}
    overall_status = "healthy"
    
    # System information
    checks["system"] = {
        "status": "healthy",
        "uptime_seconds": time.time(),  # Would need to track actual uptime
        "memory_usage": "unknown",  # Could add psutil for memory info
        "cpu_usage": "unknown"
    }
    
    # BigQuery health
    bigquery_check = await check_bigquery_connection(settings)
    checks["bigquery"] = bigquery_check
    if bigquery_check["status"] != "healthy":
        overall_status = "degraded"
    
    # Firestore health
    firestore_check = await check_firestore_connection(settings)
    checks["firestore"] = firestore_check
    if firestore_check["status"] != "healthy":
        overall_status = "degraded"
    
    # Configuration health
    config_status = {
        "status": "healthy",
        "environment": settings.environment,
        "debug_mode": settings.debug,
        "gcp_project_configured": bool(settings.gcp_project_id),
        "firebase_project_configured": bool(settings.firebase_project_id),
        "cache_configured": bool(settings.redis_url)
    }
    
    if not settings.gcp_project_id or not settings.firebase_project_id:
        config_status["status"] = "unhealthy"
        overall_status = "unhealthy"
    
    checks["configuration"] = config_status
    
    # Authentication status
    checks["authentication"] = {
        "status": "healthy",
        "firebase_admin_initialized": True,  # Would check actual status
        "service_account_configured": bool(
            settings.google_application_credentials or 
            settings.firebase_service_account_key
        )
    }
    
    response_time = (time.time() - start_time) * 1000  # Convert to milliseconds
    
    response = {
        "status": overall_status,
        "timestamp": time.time(),
        "response_time_ms": round(response_time, 2),
        "checks": checks,
        "service": {
            "name": "bigquery-api",
            "version": "1.0.0",
            "environment": settings.environment,
            "started_at": time.time()  # Would track actual start time
        }
    }
    
    # Log health check results
    if overall_status == "healthy":
        logger.debug("Health check passed", status=overall_status)
    else:
        logger.warning("Health check issues detected", 
                      status=overall_status, 
                      checks=checks)
    
    # Return appropriate status code
    status_code = 200
    if overall_status == "degraded":
        status_code = 200  # Still serving traffic but with issues
    elif overall_status == "unhealthy":
        status_code = 503  # Service unavailable
    
    return response


@router.get("/metrics")
async def basic_metrics():
    """
    Basic metrics endpoint (alternative to Prometheus metrics)
    """
    return {
        "service": "bigquery-api",
        "version": "1.0.0",
        "uptime_seconds": time.time(),  # Would calculate actual uptime
        "requests_total": 0,  # Would track actual request count
        "errors_total": 0,  # Would track actual error count
        "timestamp": time.time()
    } 