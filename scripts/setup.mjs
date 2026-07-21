import { spawnSync } from "node:child_process";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const npm = "npm";
const python = process.env.BUMBLEHIVE_PYTHON || "python";

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
  "Checking the active Python interpreter",
  python,
  [
    "-c",
    [
      "import sys",
      "print('Python:', sys.version.split()[0])",
      "print('Executable:', sys.executable)",
      "raise SystemExit(0 if sys.version_info >= (3, 11) else 'BumbleHive requires Python 3.11 or newer')",
    ].join("; "),
  ],
);

const activeEnvironment =
  process.env.CONDA_DEFAULT_ENV ||
  process.env.VIRTUAL_ENV ||
  process.env.CONDA_PREFIX;
if (!activeEnvironment || process.env.CONDA_DEFAULT_ENV === "base") {
  console.warn(
    "\nWarning: no project-specific Python environment was detected. " +
      "Dependencies will be installed into the interpreter shown above.",
  );
}

run(
  "Installing workspace tooling",
  npm,
  ["ci", "--no-audit", "--no-fund"],
);
run(
  "Installing WebUI dependencies",
  npm,
  ["ci", "--no-audit", "--no-fund"],
  resolve(root, "webui"),
);
run(
  "Installing desktop dependencies",
  npm,
  ["ci", "--no-audit", "--no-fund"],
  resolve(root, "desktop"),
);
run(
  "Installing BumbleHive SDK and development dependencies",
  python,
  ["-m", "pip", "install", "-e", ".[dev]"],
);
run(
  "Installing server, test, and packaging dependencies",
  python,
  ["-m", "pip", "install", "-e", "server[test,build]"],
);
console.log("\nSetup complete.");
console.log("Run 'npm run doctor' to verify the environment.");
console.log("Run 'npm run dev' to start the server and WebUI.");
