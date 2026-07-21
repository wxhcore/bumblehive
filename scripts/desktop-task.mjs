import { spawnSync } from "node:child_process";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const mode = process.argv[2];

if (mode !== "dev" && mode !== "build") {
  console.error("Usage: node scripts/desktop-task.mjs <dev|build>");
  process.exit(2);
}

if (process.platform !== "darwin" && process.platform !== "win32") {
  console.error(
    "BumbleHive Desktop currently supports macOS and Windows only.",
  );
  process.exit(1);
}

function run(label, command, args, cwd = root) {
  console.log("\n==> " + label);
  if (process.platform === "win32") {
    args = ["/c", command, ...args];
    command = "cmd";
  }
  const result = spawnSync(command, args, {
    cwd,
    env: process.env,
    stdio: "inherit",
  });

  if (result.error) {
    console.error("Unable to run " + command + ": " + result.error.message);
    process.exit(1);
  }
  if (result.status !== 0) {
    process.exit(result.status ?? 1);
  }
}

run(
  "Checking the desktop environment",
  process.execPath,
  [resolve(root, "scripts", "doctor.mjs"), "--desktop"],
);

run(
  "Building the Python server sidecar",
  process.execPath,
  [resolve(root, "scripts", "python-task.mjs"), "sidecar"],
);

if (mode === "dev") {
  run(
    "Starting the desktop development application",
    "npm",
    ["--prefix", "desktop", "run", "tauri", "--", "dev"],
  );
} else {
  const bundles = process.platform === "darwin" ? "dmg" : "nsis";
  run(
    "Building the desktop application",
    "npm",
    [
      "--prefix",
      "desktop",
      "run",
      "tauri",
      "--",
      "build",
      "--bundles",
      bundles,
    ],
  );
}
