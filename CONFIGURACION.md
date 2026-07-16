# Configuración y despliegue del stack

Guía única para levantar la plataforma de gobernanza completa en los dos entornos soportados: **local** y **Railway**. Siguiendo los pasos en orden, el stack queda funcionando sin conocimiento previo del proyecto.

## Arquitectura

El stack tiene 5 piezas. Las mismas en local y en Railway:

```
Vapi (nube) ──webhooks──> API FastAPI ──> Postgres  (persistencia)
                              │
                              ├──> Redis            (broker + sesiones activas)
                              └──> Worker Celery    (construye evidencias async)

Dashboard Next.js ──HTTP/WS──> API FastAPI
```

| Pieza | Tecnología | Puerto local |
|---|---|---|
| API | FastAPI (Python 3.12, uv) | 8000 |
| Worker | Celery | — (no expone HTTP) |
| Base de datos | Postgres 16 | 5432 |
| Broker/caché | Redis 7 | 6379 |
| Dashboard | Next.js 16 (Node 22) | 3000 |

---

## Parte 1 — Entorno LOCAL

### Requisitos previos

Instala estas herramientas si no las tienes. Cada comando de verificación debe responder con una versión, no con `command not found`:

| Herramienta | Para qué | Verificación |
|---|---|---|
| Docker Desktop | Postgres y Redis en contenedores | `docker --version` |
| uv | Gestor de Python del backend | `uv --version` |
| Node.js 22.x | Frontend Next.js | `node --version` → `v22.x.x` |
| ngrok | Túnel para que Vapi alcance tu máquina | `ngrok version` |

> Si falta alguna: Docker Desktop desde <https://docker.com>, uv con `curl -LsSf https://astral.sh/uv/install.sh | sh`, Node con `brew install node@22`, ngrok desde <https://ngrok.com/download>.

### Paso 1 — Clonar el repositorio

```sh
git clone https://github.com/Dm19brea/VoiceAgent_Gobernance.git
cd VoiceAgent_Gobernance
```

### Paso 2 — Arrancar Postgres y Redis

Desde la **raíz del repositorio** (donde está `docker-compose.yml`):

```sh
docker compose up -d db redis
```

Verificación — ambos contenedores deben aparecer como `running` (el de `db`, además, `healthy`):

```sh
docker compose ps
```

### Paso 3 — Crear el archivo de configuración del backend

El repositorio ya incluye una plantilla (`backend/.env.example`) con todos los valores locales correctos. Cópiala:

```sh
cp backend/.env.example backend/.env
```

Después abre `backend/.env` y rellena las **dos únicas variables vacías**:

- `VAPI_API_KEY`: dashboard de Vapi → **Settings → API Keys**.
- `OPENROUTER_API_KEY`: <https://openrouter.ai/keys> (la usa el juez LLM del scoring).

El resto de valores (Postgres, Redis, CORS, URLs base) ya vienen configurados para el `docker-compose.yml` de este repo — no los toques.

> `backend/.env` está en `.gitignore`: tus claves reales nunca se suben a git.

### Paso 4 — Instalar dependencias y migrar la base de datos

```sh
cd backend
uv sync
uv run alembic upgrade head
```

Verificación: la última línea del alembic debe decir `Running upgrade ... -> <revision>, ...` sin errores.

### Paso 5 — Arrancar la API

En la misma terminal (dentro de `backend/`):

```sh
uv run uvicorn src.main:app --port 8000
```

Verificación (en otra terminal):

```sh
curl http://localhost:8000/health
```

Debe responder: `{"status":"ok"}`.

### Paso 6 — Arrancar el worker Celery

**Nueva terminal**, dentro de `backend/`:

```sh
uv run celery -A src.infrastructure.celery.app.celery_app worker --loglevel=info
```

Verificación: el arranque termina con `celery@<tu-máquina> ready.`. Sin el worker las llamadas se ingieren, pero **no se construyen las evidencias** al cerrar cada sesión.

### Paso 7 — Arrancar el frontend

**Nueva terminal**, dentro de `frontend/`. En local **no hace falta configurar nada**: el código ya usa `http://localhost:8000` como API y nivel de log `info` por defecto.

```sh
npm install
npm run dev
```

> Solo si necesitas apuntar a otra API o cambiar el nivel de log, crea `frontend/.env.local` con `NEXT_PUBLIC_API_URL` y/o `NEXT_PUBLIC_LOG_LEVEL` (valores: `trace | debug | info | warn | error`). El WebSocket se deriva automáticamente de la URL de la API.

Verificación: abre <http://localhost:3000> — el dashboard debe cargar sin errores en la consola del navegador.

### Paso 8 — Exponer la API a Vapi (túnel)

Vapi está en la nube y no puede llegar a `localhost`. **Nueva terminal**:

```sh
ngrok http 8000
```

Copia la URL `Forwarding` que muestra (formato `https://xxxx.ngrok-free.app`). En el dashboard de Vapi, en tu asistente → **Server URL**, pon:

```
https://xxxx.ngrok-free.app/webhooks/vapi
```

> La URL de ngrok gratuito cambia en cada arranque: si reinicias ngrok, actualiza el Server URL en Vapi.

### Paso 9 — Registrar el asistente como agente gobernado

La plataforma **descarta** todo webhook de un asistente no registrado. En el dashboard local (<http://localhost:3000>), registra el agente usando el `assistantId` real de Vapi (dashboard de Vapi → tu asistente → **ID**).

### Paso 10 — Prueba de extremo a extremo

1. Haz una llamada de prueba al asistente desde Vapi (botón **Talk** del dashboard de Vapi).
2. En la terminal de la API deben aparecer líneas `Vapi webhook received: type=...` y `Vapi webhook persisted`.
3. En <http://localhost:3000> la sesión debe aparecer como activa y, al colgar, cerrarse y generar evidencias (visible en la terminal del worker).

Si el log dice `Vapi webhook discarded for ungoverned assistant`, el `assistantId` registrado en el paso 9 no coincide con el del asistente que llamó.

---

## Parte 2 — Entorno RAILWAY

El proyecto en Railway tiene **5 servicios**. Créalos en este orden:

| # | Servicio | Origen | Config |
|---|---|---|---|
| 1 | Postgres | Plugin oficial de Railway | — |
| 2 | Redis | Plugin oficial de Railway | — |
| 3 | backend | Este repo, root dir `backend/` | `backend/railway.json` (Dockerfile) |
| 4 | worker | Este repo, root dir `backend/` | `backend/railway.worker.json` (Dockerfile) |
| 5 | frontend | Este repo, root dir `frontend/` | `frontend/railway.json` |

### Servicio 3 — backend

Variables (dashboard de Railway → servicio backend → **Variables**):

```sh
DATABASE_URL=${{Postgres.DATABASE_URL}}
REDIS_URL=${{Redis.REDIS_URL}}
CORS_ORIGINS=https://<frontend>.up.railway.app
VAPI_API_KEY=tu-api-key-de-vapi
OPENROUTER_API_KEY=tu-api-key-de-openrouter
```

- Las referencias `${{Servicio.VARIABLE}}` las resuelve Railway automáticamente.
- Sustituye `<frontend>` por el dominio real del servicio frontend (visible tras crearlo — puedes volver y completar esta variable después).
- `PORT` lo inyecta Railway; el Dockerfile lo expande solo.
- No hace falta comando de arranque: el `CMD` del Dockerfile aplica las migraciones Alembic y arranca uvicorn.
- Healthcheck ya configurado en `backend/railway.json`: ruta `/health`.

Verificación:

```sh
curl https://<backend>.up.railway.app/health
```

Debe responder `{"status":"ok"}`.

### Servicio 4 — worker

Mismas variables de conexión y secretos que el backend (sin `CORS_ORIGINS`):

```sh
DATABASE_URL=${{Postgres.DATABASE_URL}}
REDIS_URL=${{Redis.REDIS_URL}}
VAPI_API_KEY=tu-api-key-de-vapi
OPENROUTER_API_KEY=tu-api-key-de-openrouter
```

El start command ya viene en `backend/railway.worker.json`:

```
uv run --no-dev celery -A src.infrastructure.celery.app.celery_app worker --loglevel=info
```

Verificación: los logs del servicio deben terminar el arranque con `celery@... ready.`.

### Servicio 5 — frontend

```sh
NEXT_PUBLIC_API_URL=https://<backend>.up.railway.app
NEXT_PUBLIC_LOG_LEVEL=info
```

> **Importante**: `NEXT_PUBLIC_API_URL` se lee en **build time**. Si la cambias, debes redesplegar el frontend. El WebSocket (`wss://<backend>.up.railway.app/ws/active-sessions`) se deriva automáticamente.

### Conectar Vapi a Railway

En el dashboard de Vapi, **Server URL** del asistente (sin túnel — Railway ya es público):

```
https://<backend>.up.railway.app/webhooks/vapi
```

Y registra el asistente como agente gobernado en el dashboard de Railway (`https://<frontend>.up.railway.app`), igual que en el paso 9 local.

---

## Referencia de variables

| Variable | Quién la usa | Local | Railway |
|---|---|---|---|
| `DATABASE_URL` | API, worker | `postgresql+asyncpg://governance:governance@localhost:5432/governance` | `${{Postgres.DATABASE_URL}}` |
| `REDIS_URL` | API, worker | `redis://localhost:6379/0` | `${{Redis.REDIS_URL}}` |
| `CORS_ORIGINS` | API | `http://localhost:3000` | URL pública del frontend |
| `VAPI_API_KEY` | API, worker | secreto | secreto |
| `VAPI_BASE_URL` | API, worker | `https://api.vapi.ai` (defecto) | igual |
| `VAPI_TIMEOUT_SECONDS` | API, worker | `10.0` (defecto) | igual |
| `OPENROUTER_API_KEY` | API, worker | secreto | secreto |
| `OPENROUTER_BASE_URL` | API, worker | `https://openrouter.ai/api/v1` (defecto) | igual |
| `OPENROUTER_TIMEOUT_SECONDS` | API, worker | `10.0` (defecto) | igual |
| `NEXT_PUBLIC_API_URL` | frontend (build time) | `http://localhost:8000` (defecto, no definir) | URL pública del backend |
| `NEXT_PUBLIC_LOG_LEVEL` | frontend | `info` (defecto, no definir) | `info` |
| `GOVERNANCE_DISABLE_DOTENV` | solo pytest | no definir | no definir |

Notas:

- Railway entrega `DATABASE_URL` como `postgresql://...`; el backend la normaliza a `postgresql+asyncpg://` automáticamente (`Settings.async_database_url`).
- Los secretos van **solo** en `backend/.env` (está en `.gitignore`) o en el dashboard de Railway. Nunca en archivos commiteados.

## Problemas comunes

| Síntoma | Causa | Solución |
|---|---|---|
| `curl /health` no responde | API no arrancada o puerto ocupado | Revisa la terminal de uvicorn; `lsof -i :8000` para ver qué ocupa el puerto |
| `connection refused` al migrar | Postgres no está arriba | `docker compose ps` — el servicio `db` debe estar `healthy` |
| Dashboard sin datos y errores CORS en consola | `CORS_ORIGINS` no incluye el origen del frontend | Añade la URL exacta del frontend y reinicia la API |
| Log: `webhook discarded for ungoverned assistant` | Asistente no registrado como agente gobernado | Registra el `assistantId` exacto en el dashboard |
| Llamadas sin evidencias al cerrar | Worker Celery no está corriendo | Arranca el worker (paso 6) |
| Vapi no envía webhooks en local | ngrok caído o Server URL desactualizada | Reinicia ngrok y actualiza el Server URL en Vapi |
