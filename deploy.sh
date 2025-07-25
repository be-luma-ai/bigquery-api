#!/bin/bash

# BigQuery API Deployment to Cloud Run
# Usage: ./deploy.sh [PROJECT_ID] [REGION]

set -e

# Configuration
PROJECT_ID=${1:-"gama-454419"}
REGION=${2:-"us-central1"}
SERVICE_NAME="bigquery-api"
IMAGE_NAME="gcr.io/${PROJECT_ID}/${SERVICE_NAME}"

echo "🚀 Deploying BigQuery API to Cloud Run"
echo "Project: ${PROJECT_ID}"
echo "Region: ${REGION}"
echo "Service: ${SERVICE_NAME}"
echo ""

# Check if gcloud is authenticated
if ! gcloud auth list --filter=status:ACTIVE --format="value(account)" | grep -q .; then
    echo "❌ No active gcloud authentication found. Please run 'gcloud auth login'"
    exit 1
fi

# Set the project
echo "📋 Setting project to ${PROJECT_ID}..."
gcloud config set project ${PROJECT_ID}

# Enable required APIs
echo "🔧 Enabling required APIs..."
gcloud services enable cloudbuild.googleapis.com
gcloud services enable run.googleapis.com
gcloud services enable containerregistry.googleapis.com

# Build the image
echo "🏗️  Building Docker image..."
gcloud builds submit --tag ${IMAGE_NAME} .

# Deploy to Cloud Run
echo "🚀 Deploying to Cloud Run..."
gcloud run deploy ${SERVICE_NAME} \
    --image ${IMAGE_NAME} \
    --platform managed \
    --region ${REGION} \
    --allow-unauthenticated \
    --port 8080 \
    --memory 2Gi \
    --cpu 2 \
    --max-instances 100 \
    --min-instances 1 \
    --timeout 900 \
    --concurrency 80 \
    --set-env-vars "ENVIRONMENT=production,PORT=8080,LOG_LEVEL=INFO"

# Get the service URL
SERVICE_URL=$(gcloud run services describe ${SERVICE_NAME} --region=${REGION} --format="value(status.url)")

echo ""
echo "✅ Deployment completed successfully!"
echo "🌍 Service URL: ${SERVICE_URL}"
echo "📊 Health check: ${SERVICE_URL}/health"
echo "📚 API docs: ${SERVICE_URL}/docs"
echo ""
echo "📋 Next steps:"
echo "1. Set up your environment variables in Cloud Run console"
echo "2. Configure Firebase service account key"
echo "3. Set up your domain and SSL certificate"
echo "4. Configure monitoring and alerting" 