# Bumblehive WebUI

React + TypeScript + Vite frontend for the local Bumblehive Server.

From the repository root:

```bash
conda activate bumblehive_env
pnpm run setup
pnpm run dev:web
```

See the root README for the Node.js and pnpm prerequisites. Use `pnpm run dev` to start the Server and WebUI together.

The development server listens on `127.0.0.1:1420` and connects to
`http://127.0.0.1:18421` by default. Override the API address in
`webui/.env.local`:

```dotenv
VITE_BUMBLEHIVE_API_URL=http://127.0.0.1:18421
```

Create a production build with:

```bash
pnpm --filter bumblehive-webui run build
```
