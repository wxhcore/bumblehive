import { after } from "node:test";
import { fileURLToPath } from "node:url";
import { createServer } from "vite";

// Each test file gets its own Vite instance through Node's process isolation.
export const server = await createServer({
  root: fileURLToPath(new URL("../..", import.meta.url)),
  appType: "custom",
  logLevel: "silent",
  server: { middlewareMode: true, hmr: false },
});

after(async () => {
  await server.close();
});
