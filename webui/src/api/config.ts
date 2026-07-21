const configuredUrl = import.meta.env.VITE_BUMBLEHIVE_API_URL?.trim();

export const API_URL = (configuredUrl || "http://127.0.0.1:18421").replace(
  /\/$/,
  "",
);

export const WS_URL = API_URL.replace(/^http:/, "ws:").replace(
  /^https:/,
  "wss:",
);
