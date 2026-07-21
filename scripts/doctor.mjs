import { spawnSync } from "node:child_process";
import { existsSync } from "node:fs";
import { delimiter, dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const npm = "npm";
const python = process.env.BUMBLEHIVE_PYTHON || "python";
const desktop = process.argv.includes("--desktop");
const setupCommand = desktop ? "npm run setup:desktop" : "npm run setup";
let errors = 0;
let warnings = 0;

function ok(message) {
  console.log("[ok]    " + message);
}

function warn(message) {
  warnings += 1;
  console.warn("[warn]  " + message);
}

function fail(message) {
  errors += 1;
  console.error("[error] " + message);
}

function capture(command, args, options = {}) {
  if (process.platform === "win32") {
    args = ["/c", command, ...args];
    command = "cmd";
  }
  return spawnSync(command, args, {
    cwd: root,
    env: options.env || process.env,
    encoding: "utf8",
  });
}

function outputOf(result) {
  return ((result.stdout || "") + (result.stderr || "")).trim();
}

function firstLine(value) {
  return value.split(/\r?\n/, 1)[0];
}

function checkCommand(label, command, args) {
  const result = capture(command, args);
  if (result.error || result.status !== 0) {
    fail(label + " is unavailable");
    return null;
  }
  const output = outputOf(result);
  ok(label + (output ? ": " + firstLine(output) : ""));
  return output;
}

function checkPath(label, path, hint) {
  if (existsSync(path)) {
    ok(label);
  } else {
    fail(label + " is missing. " + hint);
  }
}

console.log("BumbleHive environment check\n");

const nodeMatch = process.versions.node.match(/^(\d+)\.(\d+)\.(\d+)/);
const nodeMajor = Number(nodeMatch?.[1] || 0);
const nodeMinor = Number(nodeMatch?.[2] || 0);
const supportedNode =
  (nodeMajor === 20 && nodeMinor >= 19) ||
  (nodeMajor === 22 && nodeMinor >= 12) ||
  nodeMajor > 22;
if (supportedNode) {
  ok("Node.js: " + process.version);
} else {
  fail(
    "Node.js " + process.version +
      " is unsupported; install Node.js 20.19+, 22.12+, or newer.",
  );
}
checkCommand("npm", npm, ["--version"]);

const pythonInfoResult = capture(python, [
  "-c",
  [
    "import json, sys",
    "print(json.dumps({'version': list(sys.version_info[:3]), 'executable': sys.executable, 'prefix': sys.prefix, 'base_prefix': sys.base_prefix}))",
  ].join("; "),
]);

let pythonInfo = null;
if (pythonInfoResult.error || pythonInfoResult.status !== 0) {
  fail("Python is unavailable. Activate a Python 3.11+ environment.");
} else {
  try {
    const lines = (pythonInfoResult.stdout || "").trim().split(/\r?\n/);
    pythonInfo = JSON.parse(lines.at(-1));
    if (
      pythonInfo.version[0] > 3 ||
      (pythonInfo.version[0] === 3 && pythonInfo.version[1] >= 11)
    ) {
      ok(
        "Python: " + pythonInfo.version.join(".") +
          " (" + pythonInfo.executable + ")",
      );
    } else {
      fail(
        "Python " + pythonInfo.version.join(".") +
          " is unsupported; activate Python 3.11 or newer.",
      );
    }
  } catch {
    fail("Python returned unreadable environment information.");
  }
}

const condaName = process.env.CONDA_DEFAULT_ENV;
const virtualEnvironment =
  process.env.VIRTUAL_ENV || process.env.CONDA_PREFIX;
if (condaName && condaName !== "base") {
  ok("Python environment: conda " + condaName);
} else if (process.env.VIRTUAL_ENV) {
  ok("Python environment: " + process.env.VIRTUAL_ENV);
} else if (condaName === "base") {
  warn("Conda base is active; a project-specific environment is recommended.");
} else if (virtualEnvironment) {
  ok("Python environment: " + virtualEnvironment);
} else {
  warn("No activated Conda or virtual environment was detected.");
}

if (pythonInfo) {
  const pythonPath = [
    resolve(root, "src"),
    resolve(root, "server", "src"),
    process.env.PYTHONPATH,
  ].filter(Boolean).join(delimiter);
  const requiredModules = [
    "openai",
    "fastmcp",
    "mcp",
    "jsonschema",
    "yaml",
    "fitz",
    "docx",
    "openpyxl",
    "pptx",
    "fastapi",
    "uvicorn",
    "httpx",
    "pytest",
    "pytest_asyncio",
    "bumblehive",
    "bumblehive_server",
  ];
  if (desktop) {
    requiredModules.push("PyInstaller");
  }
  const moduleCheck = capture(
    python,
    [
      "-c",
      [
        "import importlib.util, json",
        "modules = " + JSON.stringify(requiredModules),
        "missing = [name for name in modules if importlib.util.find_spec(name) is None]",
        "print(json.dumps(missing))",
        "raise SystemExit(1 if missing else 0)",
      ].join("; "),
    ],
    { env: { ...process.env, PYTHONPATH: pythonPath } },
  );
  if (moduleCheck.status === 0) {
    ok("Python dependencies");
  } else {
    const lines = (moduleCheck.stdout || "").trim().split(/\r?\n/);
    let missing = [];
    try {
      missing = JSON.parse(lines.at(-1));
    } catch {
      // Keep the generic dependency error below.
    }
    fail(
      "Python dependencies are incomplete" +
        (missing.length ? ": " + missing.join(", ") : "") +
        ". Run '" +
        setupCommand +
        "'.",
    );
  }
}

checkPath(
  "Workspace Node dependencies",
  resolve(root, "node_modules", "concurrently", "package.json"),
  "Run 'npm run setup'.",
);
checkPath(
  "WebUI dependencies",
  resolve(root, "webui", "node_modules", "vite", "package.json"),
  "Run 'npm run setup'.",
);
if (desktop) {
  console.log("\nDesktop packaging");
  checkPath(
    "Desktop dependencies",
    resolve(
      root,
      "desktop",
      "node_modules",
      "@tauri-apps",
      "cli",
      "package.json",
    ),
    "Run 'npm run setup:desktop'.",
  );
  const rust = checkCommand("Rust", "rustc", ["-Vv"]);
  checkCommand("Cargo", "cargo", ["--version"]);

  if (process.platform === "darwin") {
    checkCommand("Xcode Command Line Tools", "xcode-select", ["-p"]);
  } else if (process.platform === "win32") {
    if (!rust?.includes("windows-msvc")) {
      fail("The Rust MSVC Windows toolchain is required.");
    }
    const cl = capture("where.exe", ["cl.exe"]);
    if (cl.status === 0 || process.env.VCToolsInstallDir) {
      ok("Microsoft C++ Build Tools");
    } else {
      warn(
        "C++ Build Tools were not found in PATH. Install Visual Studio " +
          "Build Tools with 'Desktop development with C++' if packaging fails.",
      );
    }
  }
}

console.log(
  "\nResult: " + errors + " error(s), " + warnings + " warning(s).",
);
process.exit(errors === 0 ? 0 : 1);
