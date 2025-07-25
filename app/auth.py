"""
Authentication and authorization middleware for BigQuery API
Handles Firebase Auth integration and multi-tenancy logic
"""

import json
import time
from typing import Optional, Dict, Any, List
import structlog
from fastapi import Request, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from starlette.middleware.base import BaseHTTPMiddleware
from cachetools import TTLCache
import firebase_admin
from firebase_admin import credentials, auth as firebase_auth, firestore

from .config import get_settings
from .exceptions import (
    AuthenticationError, 
    AuthorizationError,
    UserNotFoundError,
    CompanyNotFoundError,
    InvalidTokenError,
    MissingTokenError,
    ProjectAccessDeniedError
)

logger = structlog.get_logger()

# Initialize Firebase Admin
settings = get_settings()

if not firebase_admin._apps:
    try:
        if settings.firebase_service_account_key:
            # Use service account key from environment
            service_account_info = json.loads(settings.firebase_service_account_key)
            cred = credentials.Certificate(service_account_info)
        elif settings.google_application_credentials:
            # Use service account file
            cred = credentials.Certificate(settings.google_application_credentials)
        else:
            # Use default credentials (ADC)
            cred = credentials.ApplicationDefault()
        
        firebase_admin.initialize_app(cred, {
            'projectId': settings.firebase_project_id
        })
        logger.info("Firebase Admin initialized successfully")
    except Exception as e:
        logger.error("Failed to initialize Firebase Admin", error=str(e))
        raise

# Cache for user data (5 minute TTL, max 1000 entries)
user_cache = TTLCache(maxsize=1000, ttl=300)

# Firestore client
db = firestore.client()


class UserInfo:
    """User information with multi-tenancy data"""
    
    def __init__(
        self,
        uid: str,
        email: str,
        email_verified: bool,
        company_id: str,
        gcp_project_id: str,
        company_name: str,
        is_super_admin: bool = False,
        accessible_projects: List[str] = None,
        permissions: List[str] = None,
        client_metadata: Dict[str, Any] = None
    ):
        self.uid = uid
        self.email = email
        self.email_verified = email_verified
        self.company_id = company_id
        self.gcp_project_id = gcp_project_id
        self.company_name = company_name
        self.is_super_admin = is_super_admin
        self.accessible_projects = accessible_projects or [gcp_project_id]
        self.permissions = permissions or ["read"]
        self.client_metadata = client_metadata or {}
    
    def can_access_project(self, project_id: str) -> bool:
        """Check if user can access a specific project"""
        return self.is_super_admin or project_id in self.accessible_projects
    
    def has_permission(self, permission: str) -> bool:
        """Check if user has a specific permission"""
        return self.is_super_admin or permission in self.permissions
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for logging/serialization"""
        return {
            "uid": self.uid,
            "email": self.email,
            "email_verified": self.email_verified,
            "company_id": self.company_id,
            "gcp_project_id": self.gcp_project_id,
            "company_name": self.company_name,
            "is_super_admin": self.is_super_admin,
            "accessible_projects": self.accessible_projects,
            "permissions": self.permissions
        }


async def validate_firebase_token(token: str) -> Dict[str, Any]:
    """Validate Firebase ID token"""
    try:
        decoded_token = firebase_auth.verify_id_token(token, check_revoked=True)
        return {
            "uid": decoded_token["uid"],
            "email": decoded_token.get("email"),
            "email_verified": decoded_token.get("email_verified", False),
            "exp": decoded_token.get("exp"),
            "iat": decoded_token.get("iat")
        }
    except firebase_auth.InvalidIdTokenError:
        raise InvalidTokenError()
    except firebase_auth.ExpiredIdTokenError:
        raise InvalidTokenError()
    except firebase_auth.RevokedIdTokenError:
        raise InvalidTokenError()
    except Exception as e:
        logger.error("Token validation error", error=str(e))
        raise AuthenticationError(f"Token validation failed: {str(e)}")


async def get_user_info(uid: str, email: str) -> UserInfo:
    """Get user information with multi-tenancy data"""
    cache_key = f"user_{uid}"
    
    # Check cache first
    if cache_key in user_cache:
        return user_cache[cache_key]
    
    try:
        # Check if user is super admin
        is_super_admin = False
        if email:
            email_domain = email.split("@")[-1] if "@" in email else ""
            is_super_admin = email_domain in settings.super_admin_domains
        
        if is_super_admin:
            user_info = UserInfo(
                uid=uid,
                email=email,
                email_verified=True,  # Assume verified for super admins
                company_id="super-admin",
                gcp_project_id=settings.gcp_project_id,
                company_name="Be-Luma Admin",
                is_super_admin=True,
                accessible_projects=settings.accessible_projects or [settings.gcp_project_id],
                permissions=["read", "write", "admin"]
            )
        else:
            # Get user document from Firestore
            user_doc = db.collection("users").document(uid).get()
            
            if not user_doc.exists:
                raise UserNotFoundError()
            
            user_data = user_doc.to_dict()
            company_id = user_data.get("company_id")
            
            if not company_id:
                raise AuthorizationError("User not associated with any company")
            
            # Get client document
            client_doc = db.collection("clients").document(company_id).get()
            
            if not client_doc.exists:
                raise CompanyNotFoundError()
            
            client_data = client_doc.to_dict()
            gcp_project_id = client_data.get("gcpProjectId")
            
            if not gcp_project_id:
                raise AuthorizationError("Company does not have an associated GCP project")
            
            user_info = UserInfo(
                uid=uid,
                email=email,
                email_verified=user_data.get("email_verified", False),
                company_id=company_id,
                gcp_project_id=gcp_project_id,
                company_name=client_data.get("onboardingData", {}).get("companyName", "Unknown Company"),
                is_super_admin=False,
                accessible_projects=[gcp_project_id],
                permissions=user_data.get("permissions", ["read"]),
                client_metadata={
                    "status": client_data.get("status"),
                    "created_at": client_data.get("createdAt"),
                    "bigquery_dataset_id": client_data.get("bigQueryDatasetId")
                }
            )
        
        # Cache the result
        user_cache[cache_key] = user_info
        return user_info
        
    except (UserNotFoundError, CompanyNotFoundError, AuthorizationError):
        raise
    except Exception as e:
        logger.error("Error getting user info", uid=uid, error=str(e))
        raise AuthenticationError(f"Failed to get user information: {str(e)}")


class AuthMiddleware(BaseHTTPMiddleware):
    """Authentication middleware for FastAPI"""
    
    def __init__(self, app):
        super().__init__(app)
        self.public_paths = {
            "/health", "/health/", "/health/live", "/health/ready",
            "/metrics", "/", "/docs", "/redoc", "/openapi.json"
        }
    
    async def dispatch(self, request: Request, call_next):
        # Skip authentication for public paths
        if any(request.url.path.startswith(path) for path in self.public_paths):
            return await call_next(request)
        
        try:
            # Extract token from Authorization header
            auth_header = request.headers.get("authorization")
            
            if not auth_header or not auth_header.startswith("Bearer "):
                raise MissingTokenError()
            
            token = auth_header[7:]  # Remove "Bearer " prefix
            
            if not token:
                raise MissingTokenError()
            
            # Validate Firebase token
            firebase_user = await validate_firebase_token(token)
            
            # Check token expiration
            now = int(time.time())
            if firebase_user["exp"] <= now:
                raise InvalidTokenError()
            
            # Get user information with multi-tenancy data
            user_info = await get_user_info(firebase_user["uid"], firebase_user["email"])
            
            # Attach user info to request state
            request.state.user = user_info
            
            # Log successful authentication
            logger.info(
                "User authenticated successfully",
                user_id=user_info.uid,
                email=user_info.email,
                company_id=user_info.company_id,
                is_super_admin=user_info.is_super_admin,
                gcp_project_id=user_info.gcp_project_id
            )
            
            return await call_next(request)
            
        except (AuthenticationError, AuthorizationError) as e:
            logger.warning(
                "Authentication failed",
                error=str(e),
                path=request.url.path,
                method=request.method,
                client_ip=request.client.host if request.client else "unknown"
            )
            raise e
        except Exception as e:
            logger.error(
                "Authentication middleware error",
                error=str(e),
                path=request.url.path,
                method=request.method,
                exc_info=True
            )
            raise AuthenticationError("Authentication service unavailable")


# Dependency functions for route handlers
async def get_current_user(request: Request) -> UserInfo:
    """Dependency to get current authenticated user"""
    if not hasattr(request.state, "user"):
        raise AuthenticationError("User not authenticated")
    return request.state.user


async def get_current_super_admin(request: Request) -> UserInfo:
    """Dependency to ensure current user is super admin"""
    user = await get_current_user(request)
    if not user.is_super_admin:
        raise AuthorizationError("Super admin access required")
    return user


def require_permission(permission: str):
    """Factory for permission-based dependencies"""
    async def permission_dependency(request: Request) -> UserInfo:
        user = await get_current_user(request)
        if not user.has_permission(permission):
            raise AuthorizationError(f"Permission required: {permission}")
        return user
    return permission_dependency


def require_project_access(project_id: str):
    """Factory for project-specific access dependencies"""
    async def project_access_dependency(request: Request) -> UserInfo:
        user = await get_current_user(request)
        if not user.can_access_project(project_id):
            raise ProjectAccessDeniedError(project_id)
        return user
    return project_access_dependency


# Utility functions
def clear_user_cache(uid: str):
    """Clear user cache for specific user"""
    cache_key = f"user_{uid}"
    if cache_key in user_cache:
        del user_cache[cache_key]


def clear_all_cache():
    """Clear all user cache"""
    user_cache.clear()


def get_cache_stats() -> Dict[str, Any]:
    """Get cache statistics"""
    return {
        "size": len(user_cache),
        "max_size": user_cache.maxsize,
        "ttl": user_cache.ttl,
        "hits": getattr(user_cache, "hits", 0),
        "misses": getattr(user_cache, "misses", 0)
    } 