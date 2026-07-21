# Bumblehive WebUI

React + TypeScript + Vite frontend for the local Bumblehive Server.

From the repository root:

```bash
conda activate bumblehive_env
npm run setup
npm run dev:web
```

Use `npm run dev` to start the Server and WebUI together.

The development server listens on `127.0.0.1:1420` and connects to
`http://127.0.0.1:18421` by default. Override the API address in
`webui/.env.local`:

```dotenv
VITE_BUMBLEHIVE_API_URL=http://127.0.0.1:18421
```

Create a production build with:

```bash
npm --prefix webui run build
```

