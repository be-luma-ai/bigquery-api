# BigQuery API Service

API de BigQuery para análisis de datos multi-tenant con autenticación Firebase.

## 🚀 Deployment con GitHub Actions

### Configuración de Secretos en GitHub

Para que el deployment automático funcione, necesitas configurar estos secretos en tu repositorio de GitHub:

1. Ve a tu repositorio en GitHub
2. Navega a **Settings** → **Secrets and variables** → **Actions**
3. Añade los siguientes **Repository secrets**:

#### Secretos Requeridos:

| Secreto                        | Descripción                                     | Ejemplo                            |
| ------------------------------ | ----------------------------------------------- | ---------------------------------- |
| `GCP_SA_KEY`                   | Service Account Key de GCP en formato JSON      | `{"type": "service_account", ...}` |
| `FIREBASE_PROJECT_ID`          | ID del proyecto de Firebase                     | `be-luma-infra`                    |
| `FIREBASE_SERVICE_ACCOUNT_KEY` | Service Account Key de Firebase en formato JSON | `{"type": "service_account", ...}` |

### Cómo obtener las claves de Service Account:

#### 1. GCP Service Account (para `GCP_SA_KEY`):

```bash
# 1. Crear service account
gcloud iam service-accounts create bigquery-api-deploy \
    --display-name="BigQuery API Deployment"

# 2. Otorgar permisos necesarios
gcloud projects add-iam-policy-binding gama-454419 \
    --member="serviceAccount:bigquery-api-deploy@gama-454419.iam.gserviceaccount.com" \
    --role="roles/run.admin"

gcloud projects add-iam-policy-binding gama-454419 \
    --member="serviceAccount:bigquery-api-deploy@gama-454419.iam.gserviceaccount.com" \
    --role="roles/storage.admin"

gcloud projects add-iam-policy-binding gama-454419 \
    --member="serviceAccount:bigquery-api-deploy@gama-454419.iam.gserviceaccount.com" \
    --role="roles/iam.serviceAccountUser"

# 3. Crear y descargar la clave
gcloud iam service-accounts keys create key.json \
    --iam-account=bigquery-api-deploy@gama-454419.iam.gserviceaccount.com

# 4. Copiar el contenido de key.json al secreto GCP_SA_KEY
```

#### 2. Firebase Service Account:

- Ve a [Firebase Console](https://console.firebase.google.com/)
- Selecciona tu proyecto `be-luma-infra`
- Ve a **Project Settings** → **Service accounts**
- Haz clic en **Generate new private key**
- Descarga el archivo JSON y copia su contenido al secreto `FIREBASE_SERVICE_ACCOUNT_KEY`

### 🔄 Proceso de Deployment

El workflow se ejecuta automáticamente cuando:

1. **Push a `main`**: Deploya directamente a producción
2. **Pull Request**: Solo ejecuta tests (sin deployment)
3. **Manual**: Puedes ejecutarlo manualmente desde la pestaña Actions

### Variables de Entorno en Cloud Run

El workflow configura automáticamente estas variables:

- `ENVIRONMENT=production`
- `PORT=8080`
- `LOG_LEVEL=INFO`
- `GCP_PROJECT_ID=gama-454419`
- `FIREBASE_PROJECT_ID` (desde secreto)

Para añadir más variables, edita el archivo `.github/workflows/deploy-bigquery-api.yml`

### 📊 Configuración de Cloud Run

El servicio se despliega con estas especificaciones:

- **CPU**: 2 vCPU
- **Memoria**: 2 GiB
- **Instancias**: 1-100 (auto-scaling)
- **Timeout**: 15 minutos
- **Concurrencia**: 80 requests por instancia
- **Región**: us-central1

### 🏃‍♂️ Deployment Manual (Alternativo)

Si prefieres deployar manualmente:

```bash
# 1. Autenticarse con GCP
gcloud auth login
gcloud config set project gama-454419

# 2. Ejecutar script de deployment
cd bigquery-api
./deploy.sh
```

### 📝 Logs y Monitoreo

Una vez desplegado, puedes monitorear tu API:

- **Logs**: [Google Cloud Console](https://console.cloud.google.com/run/detail/us-central1/bigquery-api/logs)
- **Métricas**: [Cloud Run Metrics](https://console.cloud.google.com/run/detail/us-central1/bigquery-api/metrics)
- **Health Check**: `https://your-service-url/health`
- **API Docs**: `https://your-service-url/docs` (solo en desarrollo)

### 🔧 Configuración Adicional

#### Dominio Personalizado:

1. Ve a Cloud Run Console
2. Selecciona tu servicio
3. Ve a la pestaña "Manage Custom Domains"
4. Añade tu dominio

#### Variables de Entorno Adicionales:

```bash
# Configurar variables desde CLI
gcloud run services update bigquery-api \
    --region=us-central1 \
    --set-env-vars="NUEVA_VARIABLE=valor"
```

#### Secretos en Cloud Run:

```bash
# Crear secreto en Secret Manager
gcloud secrets create api-key --data-file=secret.txt

# Añadir secreto al servicio
gcloud run services update bigquery-api \
    --region=us-central1 \
    --set-secrets="API_KEY=api-key:latest"
```

### 🐛 Troubleshooting

#### Error común de permisos:

```bash
# Verificar permisos del service account
gcloud projects get-iam-policy gama-454419 \
    --flatten="bindings[].members" \
    --filter="bindings.members:bigquery-api-deploy@gama-454419.iam.gserviceaccount.com"
```

#### Ver logs de deployment:

```bash
gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=bigquery-api" \
    --limit=50 --format="table(timestamp,severity,textPayload)"
```

### 📚 Recursos Útiles

- [Cloud Run Documentation](https://cloud.google.com/run/docs)
- [GitHub Actions for GCP](https://github.com/google-github-actions)
- [FastAPI Deployment Guide](https://fastapi.tiangolo.com/deployment/)
