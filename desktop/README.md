# Bumblehive Desktop

Tauri desktop shell for the Bumblehive WebUI and local Python Server.

The desktop app embeds the frontend from `../webui` and starts the bundled sidecar built from `../server`.

From the repository root, activate the Python environment and install all workspace dependencies:

```bash
pnpm run setup
```

See the root README for the Node.js, pnpm, Python, and platform prerequisites. The shared setup installs all project-managed desktop dependencies. Platform toolchains are verified when a desktop command starts.

Start the desktop application in development mode:

```bash
pnpm run dev:desktop
```

Build the app and installer for the current platform:

```bash
pnpm run build:desktop
```

Both commands verify the desktop environment and automatically build the Python Server sidecar with the currently active Python interpreter before starting Tauri. On macOS, `build:desktop` creates a DMG containing the app bundle; on Windows, it creates the NSIS installer.

The application starts the bundled sidecar when opened and stops it when the desktop process exits. Stop any manually started Server on port `18421` before launching the desktop app.
