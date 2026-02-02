# Docker Setup - 5 Containers

Este proyecto usa Docker Compose para levantar 5 contenedores:

1. **Qdrant** - Base de datos vectorial
2. **API** - FastAPI backend
3. **Frontend** - Next.js frontend
4. **Prometheus** - Métricas y monitoreo
5. **Grafana** - Dashboards de visualización

## ⚠️ IMPORTANTE: Rebuild después de cambios

**Docker NO reconstruye automáticamente cuando cambias el código.** Si modificas:
- Código Python (`src/`)
- Configuraciones (`config/`)
- Código Frontend (`frontend/`)

**Debes forzar el rebuild:**

```bash
cd deployment/docker
docker compose up -d --build  # Rebuild y levantar todo
# O solo un servicio:
docker compose up -d --build api
docker compose up -d --build frontend
```

Ver [DOCKER_REBUILD_GUIDE.md](./DOCKER_REBUILD_GUIDE.md) para más detalles.

## 🚀 Levantar los Contenedores

### Opción 1: Levantar todos los servicios

```bash
cd deployment/docker
docker compose up -d
```

### Opción 2: Levantar servicios específicos

```bash
# Solo Qdrant y API (sin monitoreo)
docker compose up -d qdrant api

# Solo monitoreo (requiere API corriendo)
docker compose up -d prometheus grafana
```

## 📊 Puertos y Accesos

| Servicio    | Container Name        | Puerto Host | URL                          | Descripción                |
|-------------|----------------------|-------------|------------------------------|----------------------------|
| **Qdrant**  | `esa-iagen-qdrant`   | 6333        | http://localhost:6333         | API REST                   |
| **Qdrant**  | `esa-iagen-qdrant`   | 6334        | -                            | gRPC (interno)             |
| **API**     | `esa-iagen-api-v3`   | 8002        | http://localhost:8002        | FastAPI backend            |
| **API Docs**| `esa-iagen-api-v3`   | 8002        | http://localhost:8002/docs   | Swagger UI                 |
| **Frontend**| `esa-iagen-frontend` | 3000        | http://localhost:3000        | Next.js frontend           |
| **Prometheus** | `esa-iagen-prometheus` | 9090     | http://localhost:9090         | Métricas                   |
| **Grafana** | `esa-iagen-grafana`  | 3002        | http://localhost:3002        | Dashboards (admin/admin)   |

### Dependencias entre Servicios

```
Qdrant (sin dependencias)
  ↓
API (depende de Qdrant - espera health check)
  ↓
Frontend (depende de API)
Prometheus (depende de API)
  ↓
Grafana (depende de Prometheus)
```

**Orden de inicio:** Qdrant → API → (Frontend, Prometheus) → Grafana

## 🔍 Verificar Estado

```bash
# Ver todos los contenedores
docker compose ps

# Ver logs de todos los servicios
docker compose logs -f

# Ver logs de un servicio específico
docker compose logs -f api
docker compose logs -f qdrant
docker compose logs -f frontend

# Verificar salud de los servicios
curl http://localhost:8002/health
curl http://localhost:6333/healthz  # Qdrant uses /healthz endpoint
curl http://localhost:9090/-/healthy
curl http://localhost:3000  # Frontend health check
```

## 🛑 Detener Contenedores

```bash
# Detener todos los servicios
docker compose down

# Detener y eliminar volúmenes (⚠️ elimina datos)
docker compose down -v
```

## 🔧 Configuración

### Variables de Entorno

El contenedor de API usa el archivo `.env` del proyecto raíz:

```bash
# .env (en la raíz del proyecto)
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...
```

### Cambiar Puertos

Si necesitas cambiar los puertos (por conflictos), edita `docker-compose.yml`:

```yaml
services:
  api:
    ports:
      - "8002:8000"  # Cambia 8002 al puerto que quieras (Host:Container)
```

**Importante:** Si cambias el puerto de la API, también actualiza:
1. La variable de entorno `NEXT_PUBLIC_API_URL` en `docker-compose.yml` (sección frontend)
2. El archivo `frontend/lib/api.ts` si usas valores por defecto
3. La configuración CORS en `config/settings.yaml` si es necesario

## 📝 Notas Importantes

- **Qdrant**: 
  - Los datos se guardan en `deployment/docker/qdrant_storage/` (volumen local)
  - Container name: `esa-iagen-qdrant`
  - Health check usa TCP (no HTTP) porque el contenedor no tiene curl/wget
- **API**: 
  - Container name: `esa-iagen-api-v3`
  - Puerto interno: 8000, Puerto host: 8002
  - Workers: 1 (desarrollo) - configurado en `UVICORN_WORKERS=1`
  - ⚠️ **NO se reconstruye automáticamente** - usa `--build` después de cambios
- **Frontend**: 
  - Container name: `esa-iagen-frontend`
  - Conecta a API en `http://localhost:8002` (desde el navegador)
  - ⚠️ **NO se reconstruye automáticamente** - usa `--build` después de cambios
- **Prometheus**: 
  - Container name: `esa-iagen-prometheus`
  - Los datos se guardan en el volumen `prometheus_data`
  - Retención: 30 días
- **Grafana**: 
  - Container name: `esa-iagen-grafana`
  - Los dashboards se guardan en el volumen `grafana_data`
  - Credenciales por defecto: `admin/admin`

## 🔄 Reconstruir Imágenes

**Después de cambiar código, SIEMPRE reconstruye:**

```bash
# Opción 1: Rebuild y levantar (recomendado)
docker compose up -d --build api
docker compose up -d --build frontend

# Opción 2: Rebuild sin caché (si hay problemas)
docker compose build --no-cache api
docker compose up -d api
```

**Ver documentación completa:** [DOCKER_REBUILD_GUIDE.md](./DOCKER_REBUILD_GUIDE.md)

## 🐛 Troubleshooting

### Puerto en uso

```bash
# Ver qué está usando un puerto
lsof -i :8002
lsof -i :6333
lsof -i :9090
lsof -i :3002

# Detener contenedores de otra app
docker ps | grep <otra-app>
docker stop <container-id>
```

### Contenedor no inicia

```bash
# Ver logs detallados
docker compose logs api
docker compose logs qdrant
docker compose logs frontend

# Ver logs desde el inicio (últimas 100 líneas)
docker compose logs --tail=100 api

# Verificar configuración
docker compose config

# Verificar estado de health checks
docker compose ps
# Busca contenedores con estado "(unhealthy)" o "(starting)"
```

### Limpiar todo y empezar de nuevo

```bash
# ⚠️ Esto elimina TODOS los datos (Qdrant, Prometheus, Grafana)
docker compose down -v

# Rebuild y levantar todo desde cero
docker compose up -d --build
```

### Problemas de conexión entre servicios

```bash
# Verificar que los contenedores están en la misma red
docker network inspect esa-iagen-network

# Verificar conectividad entre contenedores
docker compose exec api ping -c 3 qdrant
docker compose exec frontend ping -c 3 api

# Verificar variables de entorno
docker compose exec api env | grep QDRANT
docker compose exec frontend env | grep NEXT_PUBLIC
```

### Primer inicio lento

**Nota:** El primer inicio puede ser lento porque:
- Los modelos de ML se descargan la primera vez (BGE-small: 130MB, reranker: 130MB)
- Los modelos se cargan en memoria al iniciar (1-2 segundos para BGE-small)
- El API espera a que Qdrant esté saludable antes de iniciar

**Solución:** Espera 30-60 segundos después de `docker compose up -d` antes de hacer requests.

