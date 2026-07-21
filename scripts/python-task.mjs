import { spawn } from "node:child_process";
import { delimiter, dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const python = process.env.BUMBLEHIVE_PYTHON || "python";
const task = process.argv[2];

const tasks = {
  server: ["-m", "bumblehive_server"],
  test: ["-m", "pytest", "-q"],
  sidecar: ["server/scripts/build_sidecar.py"],
};
const args = tasks[task];

if (!args) {
  console.error(
    "Unknown Python task: " + (task || "(missing)") + ". " +
      "Expected server, test, or sidecar.",
  );
  process.exit(2);
}

const sourcePaths = [
  resolve(root, "src"),
  resolve(root, "server", "src"),
];
if (process.env.PYTHONPATH) {
  sourcePaths.push(process.env.PYTHONPATH);
}

const child = spawn(python, args, {
  cwd: root,
  env: {
    ...process.env,
    PYTHONPATH: sourcePaths.join(delimiter),
  },
  stdio: "inherit",
});

child.on("error", (error) => {
  console.error("Unable to run " + python + ": " + error.message);
  process.exit(1);
});

child.on("exit", (code) => {
  process.exit(code ?? 1);
});
