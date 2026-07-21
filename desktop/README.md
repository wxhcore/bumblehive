# Bumblehive Desktop

Tauri desktop shell for the Bumblehive WebUI and local Python Server.

The desktop app embeds the frontend from `../webui` and starts the bundled sidecar built from `../server`.

From the repository root, activate the Python environment and install all workspace dependencies:

```bash
conda activate bumblehive_env
npm run setup
npm run build:sidecar
npm run doctor:desktop
```

`npm run setup` installs dependencies but does not generate the sidecar checked by `doctor:desktop`.

Start the desktop application in development mode:

```bash
npm run dev:desktop
```

Build the macOS app and DMG, or the Windows NSIS installer:

```bash
npm run build:mac
npm run build:win
```

These commands build the sidecar first with the currently active Python interpreter. To rebuild only the sidecar:

```bash
npm run build:sidecar
```

The application is written to
`src-tauri/target/release/bundle/macos/BumbleHive.app`. It starts the bundled
sidecar when opened and stops it when the desktop process exits. Stop any
manually started Server on port `18421` before launching the desktop app.
