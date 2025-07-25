#!/bin/bash

# Script para inicializar repositorio BigQuery API y subirlo a GitHub
# Uso: ./setup-github.sh [URL_REPOSITORIO_GITHUB]

set -e

echo "🚀 Configurando repositorio BigQuery API para GitHub"
echo ""

# Verificar si estamos en la carpeta correcta
if [ ! -f "requirements.txt" ] || [ ! -f "Dockerfile" ]; then
    echo "❌ Error: No estás en la carpeta bigquery-api"
    echo "Ejecuta este script desde dentro de la carpeta bigquery-api"
    exit 1
fi

# Inicializar repositorio git si no existe
if [ ! -d ".git" ]; then
    echo "📦 Inicializando repositorio Git..."
    git init
    git branch -M main
else
    echo "📦 Repositorio Git ya existe"
fi

# Configurar .gitignore si no existe
echo "📝 Verificando .gitignore..."

# Agregar archivos al staging area
echo "📋 Agregando archivos..."
git add .

# Crear commit inicial
echo "💾 Creando commit inicial..."
if git diff --staged --quiet; then
    echo "No hay cambios para commitear"
else
    git commit -m "Initial commit: BigQuery API service

- FastAPI application with multi-tenant support
- Firebase authentication integration
- BigQuery data access layer
- Docker containerization
- GitHub Actions CI/CD pipeline
- Cloud Run deployment configuration"
fi

# Verificar URL del repositorio
REPO_URL=${1:-""}
if [ -z "$REPO_URL" ]; then
    echo ""
    echo "📋 Para conectar con GitHub:"
    echo "1. Crea un nuevo repositorio en GitHub (ej: bigquery-api)"
    echo "2. Ejecuta:"
    echo "   git remote add origin https://github.com/TU_USUARIO/bigquery-api.git"
    echo "   git push -u origin main"
    echo ""
    echo "O ejecuta este script con la URL:"
    echo "   ./setup-github.sh https://github.com/TU_USUARIO/bigquery-api.git"
else
    echo "🔗 Conectando con repositorio: $REPO_URL"
    
    # Verificar si ya existe el remote
    if git remote get-url origin >/dev/null 2>&1; then
        echo "Remote 'origin' ya existe, actualizando..."
        git remote set-url origin "$REPO_URL"
    else
        git remote add origin "$REPO_URL"
    fi
    
    echo "📤 Subiendo a GitHub..."
    git push -u origin main
    
    echo ""
    echo "✅ ¡Repositorio subido exitosamente!"
    echo "🌍 URL: $REPO_URL"
fi

echo ""
echo "📋 Próximos pasos:"
echo "1. Configurar secretos en GitHub:"
echo "   - GCP_SA_KEY"
echo "   - FIREBASE_PROJECT_ID"
echo "   - FIREBASE_SERVICE_ACCOUNT_KEY"
echo "2. El deployment será automático en cada push a main"
echo "3. Revisa las instrucciones en README.md"
echo ""
echo "🎉 ¡Listo para deployar!" 