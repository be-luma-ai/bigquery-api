"""
BigQuery Router - Main API endpoints for BigQuery operations
Handles data queries, table management, and analytics operations
"""

import time
from typing import Dict, Any, List, Optional
import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, validator
from google.cloud import bigquery
from google.cloud.exceptions import NotFound, BadRequest, Forbidden

from ..auth import get_current_user, require_permission, UserInfo
from ..config import get_settings
from ..exceptions import (
    BigQueryAPIException,
    AuthorizationError,
    ProjectAccessDeniedError,
    InvalidQueryError
)

logger = structlog.get_logger()
router = APIRouter()
settings = get_settings()

# Initialize BigQuery client
bq_client = bigquery.Client()

# Request/Response Models
class QueryRequest(BaseModel):
    """Request model for BigQuery queries"""
    query: str = Field(..., description="SQL query to execute")
    project_id: Optional[str] = Field(None, description="Target GCP project ID")
    max_results: Optional[int] = Field(None, ge=1, le=10000, description="Maximum results to return")
    timeout: Optional[int] = Field(None, ge=1, le=900, description="Query timeout in seconds")
    use_cache: bool = Field(True, description="Whether to use query cache")
    dry_run: bool = Field(False, description="Validate query without executing")
    
    @validator('query')
    def validate_query(cls, v):
        """Basic query validation"""
        if not v or not v.strip():
            raise ValueError("Query cannot be empty")
        
        # Basic security checks
        dangerous_keywords = ['DROP', 'DELETE', 'TRUNCATE', 'ALTER', 'CREATE', 'INSERT', 'UPDATE']
        query_upper = v.upper()
        
        for keyword in dangerous_keywords:
            if keyword in query_upper:
                raise ValueError(f"Query contains forbidden keyword: {keyword}")
        
        return v.strip()


class TableInfo(BaseModel):
    """Model for table information"""
    table_id: str
    dataset_id: str
    project_id: str
    table_type: str
    num_rows: Optional[int] = None
    num_bytes: Optional[int] = None
    created: Optional[str] = None
    modified: Optional[str] = None


class QueryResponse(BaseModel):
    """Response model for query results"""
    success: bool
    data: List[Dict[str, Any]]
    total_rows: int
    bytes_processed: Optional[int] = None
    execution_time: float
    query_id: Optional[str] = None
    cache_hit: Optional[bool] = None


# Query execution endpoint
@router.post("/query", response_model=QueryResponse)
async def execute_query(
    request: QueryRequest,
    user: UserInfo = Depends(require_permission("read"))
):
    """Execute a BigQuery SQL query"""
    start_time = time.time()
    
    # Determine target project
    target_project = request.project_id or user.gcp_project_id
    
    # Check project access
    if not user.can_access_project(target_project):
        raise ProjectAccessDeniedError(target_project)
    
    try:
        # Configure query job
        job_config = bigquery.QueryJobConfig(
            use_query_cache=request.use_cache,
            dry_run=request.dry_run,
            maximum_bytes_billed=settings.bigquery_max_results * 1024 * 1024,  # Rough estimate
        )
        
        if request.max_results:
            job_config.maximum_bytes_billed = request.max_results * 1024
        
        # Execute query
        logger.info(
            "Executing BigQuery query",
            user_id=user.uid,
            project_id=target_project,
            query_length=len(request.query),
            dry_run=request.dry_run
        )
        
        query_job = bq_client.query(
            request.query,
            job_config=job_config,
            project=target_project
        )
        
        if request.dry_run:
            return QueryResponse(
                success=True,
                data=[],
                total_rows=0,
                bytes_processed=query_job.total_bytes_processed,
                execution_time=time.time() - start_time,
                query_id=query_job.job_id
            )
        
        # Wait for query completion with timeout
        timeout = request.timeout or settings.bigquery_job_timeout
        results = query_job.result(timeout=timeout, max_results=request.max_results)
        
        # Convert results to list of dictionaries
        data = []
        for row in results:
            data.append(dict(row))
        
        execution_time = time.time() - start_time
        
        logger.info(
            "Query executed successfully",
            user_id=user.uid,
            project_id=target_project,
            total_rows=results.total_rows,
            execution_time=execution_time,
            bytes_processed=query_job.total_bytes_processed
        )
        
        return QueryResponse(
            success=True,
            data=data,
            total_rows=results.total_rows or len(data),
            bytes_processed=query_job.total_bytes_processed,
            execution_time=execution_time,
            query_id=query_job.job_id,
            cache_hit=query_job.cache_hit
        )
        
    except BadRequest as e:
        logger.error("Invalid BigQuery query", error=str(e), user_id=user.uid)
        raise InvalidQueryError(f"Invalid query: {str(e)}")
    
    except Forbidden as e:
        logger.error("BigQuery access forbidden", error=str(e), user_id=user.uid)
        raise AuthorizationError(f"Access denied: {str(e)}")
    
    except Exception as e:
        logger.error(
            "Query execution failed",
            error=str(e),
            user_id=user.uid,
            project_id=target_project,
            exc_info=True
        )
        raise BigQueryAPIException(f"Query execution failed: {str(e)}")


# List datasets endpoint
@router.get("/datasets")
async def list_datasets(
    project_id: Optional[str] = Query(None, description="Target project ID"),
    user: UserInfo = Depends(require_permission("read"))
):
    """List available datasets in the project"""
    target_project = project_id or user.gcp_project_id
    
    if not user.can_access_project(target_project):
        raise ProjectAccessDeniedError(target_project)
    
    try:
        datasets = list(bq_client.list_datasets(project=target_project))
        
        dataset_list = []
        for dataset in datasets:
            dataset_list.append({
                "dataset_id": dataset.dataset_id,
                "project_id": dataset.project,
                "location": dataset.location,
                "created": dataset.created.isoformat() if dataset.created else None,
                "modified": dataset.modified.isoformat() if dataset.modified else None,
                "description": dataset.description
            })
        
        logger.info(
            "Listed datasets",
            user_id=user.uid,
            project_id=target_project,
            dataset_count=len(dataset_list)
        )
        
        return {
            "success": True,
            "datasets": dataset_list,
            "project_id": target_project,
            "count": len(dataset_list)
        }
        
    except NotFound:
        raise HTTPException(status_code=404, detail=f"Project {target_project} not found")
    except Exception as e:
        logger.error("Failed to list datasets", error=str(e), user_id=user.uid)
        raise BigQueryAPIException(f"Failed to list datasets: {str(e)}")


# List tables endpoint
@router.get("/datasets/{dataset_id}/tables")
async def list_tables(
    dataset_id: str,
    project_id: Optional[str] = Query(None, description="Target project ID"),
    user: UserInfo = Depends(require_permission("read"))
):
    """List tables in a specific dataset"""
    target_project = project_id or user.gcp_project_id
    
    if not user.can_access_project(target_project):
        raise ProjectAccessDeniedError(target_project)
    
    try:
        dataset_ref = bq_client.dataset(dataset_id, project=target_project)
        tables = list(bq_client.list_tables(dataset_ref))
        
        table_list = []
        for table in tables:
            # Get detailed table info
            table_ref = dataset_ref.table(table.table_id)
            table_obj = bq_client.get_table(table_ref)
            
            table_list.append({
                "table_id": table.table_id,
                "dataset_id": dataset_id,
                "project_id": target_project,
                "table_type": table.table_type,
                "num_rows": table_obj.num_rows,
                "num_bytes": table_obj.num_bytes,
                "created": table_obj.created.isoformat() if table_obj.created else None,
                "modified": table_obj.modified.isoformat() if table_obj.modified else None,
                "description": table_obj.description,
                "schema_fields": len(table_obj.schema) if table_obj.schema else 0
            })
        
        logger.info(
            "Listed tables",
            user_id=user.uid,
            project_id=target_project,
            dataset_id=dataset_id,
            table_count=len(table_list)
        )
        
        return {
            "success": True,
            "tables": table_list,
            "dataset_id": dataset_id,
            "project_id": target_project,
            "count": len(table_list)
        }
        
    except NotFound:
        raise HTTPException(
            status_code=404, 
            detail=f"Dataset {dataset_id} not found in project {target_project}"
        )
    except Exception as e:
        logger.error("Failed to list tables", error=str(e), user_id=user.uid)
        raise BigQueryAPIException(f"Failed to list tables: {str(e)}")


# Get table schema endpoint
@router.get("/datasets/{dataset_id}/tables/{table_id}/schema")
async def get_table_schema(
    dataset_id: str,
    table_id: str,
    project_id: Optional[str] = Query(None, description="Target project ID"),
    user: UserInfo = Depends(require_permission("read"))
):
    """Get schema information for a specific table"""
    target_project = project_id or user.gcp_project_id
    
    if not user.can_access_project(target_project):
        raise ProjectAccessDeniedError(target_project)
    
    try:
        table_ref = bq_client.dataset(dataset_id, project=target_project).table(table_id)
        table = bq_client.get_table(table_ref)
        
        schema_fields = []
        for field in table.schema:
            schema_fields.append({
                "name": field.name,
                "field_type": field.field_type,
                "mode": field.mode,
                "description": field.description
            })
        
        return {
            "success": True,
            "table_id": table_id,
            "dataset_id": dataset_id,
            "project_id": target_project,
            "schema": schema_fields,
            "num_rows": table.num_rows,
            "num_bytes": table.num_bytes,
            "created": table.created.isoformat() if table.created else None,
            "modified": table.modified.isoformat() if table.modified else None
        }
        
    except NotFound:
        raise HTTPException(
            status_code=404,
            detail=f"Table {dataset_id}.{table_id} not found in project {target_project}"
        )
    except Exception as e:
        logger.error("Failed to get table schema", error=str(e), user_id=user.uid)
        raise BigQueryAPIException(f"Failed to get table schema: {str(e)}")


# Quick data preview endpoint
@router.get("/datasets/{dataset_id}/tables/{table_id}/preview")
async def preview_table_data(
    dataset_id: str,
    table_id: str,
    limit: int = Query(10, ge=1, le=100, description="Number of rows to preview"),
    project_id: Optional[str] = Query(None, description="Target project ID"),
    user: UserInfo = Depends(require_permission("read"))
):
    """Get a preview of table data (first N rows)"""
    target_project = project_id or user.gcp_project_id
    
    if not user.can_access_project(target_project):
        raise ProjectAccessDeniedError(target_project)
    
    try:
        # Construct a simple SELECT query with LIMIT
        query = f"""
        SELECT *
        FROM `{target_project}.{dataset_id}.{table_id}`
        LIMIT {limit}
        """
        
        # Execute query using our existing query function
        request = QueryRequest(
            query=query,
            project_id=target_project,
            max_results=limit
        )
        
        return await execute_query(request, user)
        
    except Exception as e:
        logger.error("Failed to preview table data", error=str(e), user_id=user.uid)
        raise BigQueryAPIException(f"Failed to preview table data: {str(e)}") 