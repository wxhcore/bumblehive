# Bumblehive Desktop

Tauri desktop shell for the Bumblehive WebUI and local Python Server.

The desktop app embeds the frontend from `../webui` and starts the bundled sidecar built from `../server`.

From the repository root, activate the Python environment and install all workspace dependencies:

```bash
npm run setup:desktop
```

`npm run setup:desktop` installs the core workspace and optional desktop dependencies, then verifies the complete environment.

Start the desktop application in development mode:

```bash
npm run dev:desktop
```

Build the app and installer for the current platform:

```bash
npm run build:desktop
```

Both commands verify the desktop environment and automatically build the Python Server sidecar with the currently active Python interpreter before starting Tauri. On macOS, `build:desktop` creates the app and DMG; on Windows, it creates the NSIS installer.

The application starts the bundled sidecar when opened and stops it when the desktop process exits. Stop any manually started Server on port `18421` before launching the desktop app.
