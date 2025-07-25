"""
Configuration settings for BigQuery API Service
Using Pydantic Settings for type validation and environment variable management
"""

import os
from typing import List, Optional
from functools import lru_cache

from pydantic import Field, validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings with validation"""
    
    # Basic app settings
    debug: bool = Field(default=False, description="Enable debug mode")
    environment: str = Field(default="production", description="Environment name")
    port: int = Field(default=8080, description="Server port")
    
    # Google Cloud settings
    gcp_project_id: str = Field(..., description="Default GCP project ID")
    google_application_credentials: Optional[str] = Field(
        default=None, 
        description="Path to service account JSON file"
    )
    firebase_service_account_key: Optional[str] = Field(
        default=None,
        description="Firebase service account key as JSON string"
    )
    
    # BigQuery settings
    bigquery_location: str = Field(default="US", description="BigQuery location")
    bigquery_job_timeout: int = Field(default=300, description="BigQuery job timeout in seconds")
    bigquery_max_results: int = Field(default=10000, description="Maximum results per query")
    
    # Security settings
    allowed_origins: List[str] = Field(
        default_factory=lambda: ["http://localhost:3000"],
        description="Allowed CORS origins"
    )
    firebase_project_id: str = Field(..., description="Firebase project ID")
    
    # Multi-tenant settings
    accessible_projects: List[str] = Field(
        default_factory=list,
        description="List of accessible GCP projects for super admins"
    )
    super_admin_domains: List[str] = Field(
        default_factory=lambda: ["be-luma.com"],
        description="Email domains that have super admin access"
    )
    
    # Rate limiting
    rate_limit_requests: int = Field(default=100, description="Requests per window")
    rate_limit_window: int = Field(default=900, description="Rate limit window in seconds")
    
    # Caching
    cache_ttl: int = Field(default=300, description="Cache TTL in seconds")
    redis_url: Optional[str] = Field(default=None, description="Redis URL for caching")
    
    # Logging
    log_level: str = Field(default="INFO", description="Logging level")
    
    # Monitoring
    enable_metrics: bool = Field(default=True, description="Enable Prometheus metrics")
    
    @validator('environment')
    def validate_environment(cls, v):
        """Validate environment value"""
        valid_envs = ['development', 'staging', 'production']
        if v not in valid_envs:
            raise ValueError(f'Environment must be one of {valid_envs}')
        return v
    
    @validator('log_level')
    def validate_log_level(cls, v):
        """Validate log level"""
        valid_levels = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
        if v.upper() not in valid_levels:
            raise ValueError(f'Log level must be one of {valid_levels}')
        return v.upper()
    
    @validator('allowed_origins', pre=True)
    def parse_allowed_origins(cls, v):
        """Parse allowed origins from string if needed"""
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(',') if origin.strip()]
        return v
    
    @validator('accessible_projects', pre=True)
    def parse_accessible_projects(cls, v):
        """Parse accessible projects from string if needed"""
        if isinstance(v, str):
            return [project.strip() for project in v.split(',') if project.strip()]
        return v
    
    @validator('super_admin_domains', pre=True)
    def parse_super_admin_domains(cls, v):
        """Parse super admin domains from string if needed"""
        if isinstance(v, str):
            return [domain.strip() for domain in v.split(',') if domain.strip()]
        return v
    
    @property
    def is_development(self) -> bool:
        """Check if running in development mode"""
        return self.environment == 'development' or self.debug
    
    @property
    def is_production(self) -> bool:
        """Check if running in production mode"""
        return self.environment == 'production' and not self.debug
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
        
        # Map environment variables to settings
        fields = {
            'gcp_project_id': {'env': ['GCP_PROJECT_ID', 'GOOGLE_CLOUD_PROJECT']},
            'google_application_credentials': {'env': 'GOOGLE_APPLICATION_CREDENTIALS'},
            'firebase_service_account_key': {'env': 'FIREBASE_SERVICE_ACCOUNT_KEY'},
            'firebase_project_id': {'env': 'FIREBASE_PROJECT_ID'},
            'bigquery_location': {'env': 'BIGQUERY_LOCATION'},
            'allowed_origins': {'env': 'ALLOWED_ORIGINS'},
            'accessible_projects': {'env': 'ACCESSIBLE_PROJECTS'},
            'super_admin_domains': {'env': 'SUPER_ADMIN_DOMAINS'},
            'redis_url': {'env': ['REDIS_URL', 'CACHE_URL']},
            'log_level': {'env': 'LOG_LEVEL'},
        }


@lru_cache()
def get_settings() -> Settings:
    """
    Create cached settings instance
    The lru_cache decorator ensures we create only one instance
    """
    return Settings()


# Development/testing overrides
class TestSettings(Settings):
    """Settings for testing environment"""
    debug: bool = True
    environment: str = "testing"
    cache_ttl: int = 1  # Short cache for testing
    rate_limit_requests: int = 1000  # Higher limits for testing
    

def get_test_settings() -> TestSettings:
    """Get test settings"""
    return TestSettings()


# Example .env file content (for documentation)
ENV_EXAMPLE = """
# Basic settings
DEBUG=false
ENVIRONMENT=production
PORT=8080

# Google Cloud
GCP_PROJECT_ID=gama-454419
GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account.json
# OR
FIREBASE_SERVICE_ACCOUNT_KEY={"type":"service_account",...}

# Firebase
FIREBASE_PROJECT_ID=be-luma-infra

# BigQuery
BIGQUERY_LOCATION=US
BIGQUERY_JOB_TIMEOUT=300
BIGQUERY_MAX_RESULTS=10000

# Security
ALLOWED_ORIGINS=https://your-domain.com,https://www.your-domain.com
SUPER_ADMIN_DOMAINS=be-luma.com
ACCESSIBLE_PROJECTS=gama-454419,other-project

# Rate limiting
RATE_LIMIT_REQUESTS=100
RATE_LIMIT_WINDOW=900

# Caching
CACHE_TTL=300
REDIS_URL=redis://localhost:6379

# Logging
LOG_LEVEL=INFO

# Monitoring
ENABLE_METRICS=true
""" 