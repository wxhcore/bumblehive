# Bumblehive Server

FastAPI adapter for the Bumblehive Python SDK.

## Development

From the repository root:

```bash
conda activate bumblehive_env
npm run setup
npm run dev:server
```

The root launcher sets the cross-platform `PYTHONPATH` automatically. Use `npm run dev` to start the Server and WebUI together.

The server listens on `127.0.0.1:18421` by default and reads configuration from
`~/.bumblehive/config.json`.

Environment overrides:

```text
BUMBLEHIVE_CONFIG=/path/to/config.json
BUMBLEHIVE_HOST=127.0.0.1
BUMBLEHIVE_PORT=18421
BUMBLEHIVE_ALLOWED_ORIGINS=http://127.0.0.1:1420,tauri://localhost
```

## API

```text
GET    /api/v1/health
GET    /api/v1/settings
PUT    /api/v1/settings
POST   /api/v1/sessions
GET    /api/v1/sessions
GET    /api/v1/sessions/{session_id}
DELETE /api/v1/sessions/{session_id}
WS     /ws/v1/chat/{session_id}
```

## Desktop sidecar

Build the standalone binary from the repository root with the Python build
environment activated:

```bash
npm run build:sidecar
```

The script writes a standalone directory to
`desktop/src-tauri/sidecar/bumblehive-server/`. Tauri bundles that directory,
starts its executable when the desktop application opens, and stops it when
the application exits.
