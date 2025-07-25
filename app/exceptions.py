"""
Custom exceptions for BigQuery API Service
Provides specific error types for better error handling and logging
"""

from typing import Optional, Dict, Any
from fastapi import HTTPException


class BigQueryAPIException(HTTPException):
    """Base exception for BigQuery API errors"""
    
    def __init__(
        self,
        status_code: int,
        detail: str,
        code: Optional[str] = None,
        headers: Optional[Dict[str, Any]] = None
    ):
        super().__init__(status_code=status_code, detail=detail, headers=headers)
        self.code = code or "BIGQUERY_ERROR"


class AuthenticationError(BigQueryAPIException):
    """Authentication related errors"""
    
    def __init__(
        self,
        detail: str = "Authentication failed",
        code: Optional[str] = None,
        headers: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            status_code=401,
            detail=detail,
            code=code or "AUTH_ERROR",
            headers=headers
        )


class AuthorizationError(BigQueryAPIException):
    """Authorization/permission related errors"""
    
    def __init__(
        self,
        detail: str = "Access forbidden",
        code: Optional[str] = None,
        headers: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            status_code=403,
            detail=detail,
            code=code or "AUTHORIZATION_ERROR",
            headers=headers
        )


class ValidationError(BigQueryAPIException):
    """Request validation errors"""
    
    def __init__(
        self,
        detail: str = "Invalid request data",
        code: Optional[str] = None,
        headers: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            status_code=400,
            detail=detail,
            code=code or "VALIDATION_ERROR",
            headers=headers
        )


class BigQueryError(BigQueryAPIException):
    """BigQuery service specific errors"""
    
    def __init__(
        self,
        detail: str = "BigQuery operation failed",
        code: Optional[str] = None,
        headers: Optional[Dict[str, Any]] = None,
        status_code: int = 500
    ):
        super().__init__(
            status_code=status_code,
            detail=detail,
            code=code or "BIGQUERY_OPERATION_ERROR",
            headers=headers
        )


class RateLimitError(BigQueryAPIException):
    """Rate limiting errors"""
    
    def __init__(
        self,
        detail: str = "Rate limit exceeded",
        code: Optional[str] = None,
        headers: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            status_code=429,
            detail=detail,
            code=code or "RATE_LIMIT_ERROR",
            headers=headers
        )


class MultiTenancyError(BigQueryAPIException):
    """Multi-tenancy related errors"""
    
    def __init__(
        self,
        detail: str = "Multi-tenancy violation",
        code: Optional[str] = None,
        headers: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            status_code=403,
            detail=detail,
            code=code or "MULTI_TENANCY_ERROR",
            headers=headers
        )


class ConfigurationError(BigQueryAPIException):
    """Configuration related errors"""
    
    def __init__(
        self,
        detail: str = "Service configuration error",
        code: Optional[str] = None,
        headers: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            status_code=500,
            detail=detail,
            code=code or "CONFIGURATION_ERROR",
            headers=headers
        )


# Specific error instances for common scenarios
class InvalidTokenError(AuthenticationError):
    """Invalid or expired token"""
    
    def __init__(self):
        super().__init__(
            detail="Invalid or expired authentication token",
            code="INVALID_TOKEN"
        )


class MissingTokenError(AuthenticationError):
    """Missing authentication token"""
    
    def __init__(self):
        super().__init__(
            detail="Authentication token not provided",
            code="MISSING_TOKEN"
        )


class UserNotFoundError(AuthenticationError):
    """User not found in database"""
    
    def __init__(self):
        super().__init__(
            detail="User not found in database",
            code="USER_NOT_FOUND"
        )


class CompanyNotFoundError(AuthorizationError):
    """Company/client not found"""
    
    def __init__(self):
        super().__init__(
            detail="Company not found or access denied",
            code="COMPANY_NOT_FOUND"
        )


class ProjectAccessDeniedError(AuthorizationError):
    """Access denied to GCP project"""
    
    def __init__(self, project_id: str):
        super().__init__(
            detail=f"Access denied to project: {project_id}",
            code="PROJECT_ACCESS_DENIED"
        )


class InvalidQueryError(ValidationError):
    """Invalid BigQuery SQL"""
    
    def __init__(self, details: str = ""):
        super().__init__(
            detail=f"Invalid SQL query{': ' + details if details else ''}",
            code="INVALID_QUERY"
        )


class QueryTimeoutError(BigQueryError):
    """BigQuery timeout"""
    
    def __init__(self, timeout_seconds: int):
        super().__init__(
            detail=f"Query timed out after {timeout_seconds} seconds",
            code="QUERY_TIMEOUT",
            status_code=408
        )


class QueryTooLargeError(BigQueryError):
    """Query result too large"""
    
    def __init__(self, max_results: int):
        super().__init__(
            detail=f"Query result exceeds maximum of {max_results} rows",
            code="QUERY_TOO_LARGE",
            status_code=413
        )


# Error factories for common scenarios
def create_auth_error(error_type: str, detail: str = "") -> AuthenticationError:
    """Create authentication error based on type"""
    error_map = {
        "invalid_token": InvalidTokenError(),
        "missing_token": MissingTokenError(),
        "user_not_found": UserNotFoundError(),
    }
    
    if error_type in error_map:
        return error_map[error_type]
    
    return AuthenticationError(detail=detail or f"Authentication error: {error_type}")


def create_bigquery_error(error_msg: str, error_code: str = "") -> BigQueryError:
    """Create BigQuery error from error message"""
    
    # Map common BigQuery errors to appropriate status codes
    if "timeout" in error_msg.lower():
        return QueryTimeoutError(300)
    elif "too many" in error_msg.lower() or "limit" in error_msg.lower():
        return QueryTooLargeError(10000)
    elif "syntax" in error_msg.lower() or "invalid" in error_msg.lower():
        return InvalidQueryError(error_msg)
    else:
        return BigQueryError(
            detail=error_msg,
            code=error_code or "BIGQUERY_ERROR"
        ) 