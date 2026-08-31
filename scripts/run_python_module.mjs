import { existsSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";
import { spawnSync } from "node:child_process";

const moduleName = process.argv[2];
const args = process.argv.slice(3);

if (!moduleName) {
  console.error("Usage: node scripts/run_python_module.mjs <module> [...args]");
  process.exit(1);
}

const candidates = [
  process.env.PYTHON,
  "python",
  "python3",
  "py",
  join(
    homedir(),
    ".cache",
    "codex-runtimes",
    "codex-primary-runtime",
    "dependencies",
    "python",
    "python.exe",
  ),
].filter(Boolean);

let lastError = "";

for (const python of candidates) {
  if (python.includes("\\") || python.includes("/")) {
    if (!existsSync(python)) continue;
  }

  const result = spawnSync(python, ["-m", moduleName, ...args], {
    stdio: "inherit",
    shell: false,
  });

  if (result.error) {
    lastError = result.error.message;
    continue;
  }

  process.exit(result.status ?? 0);
}

console.error(`Python executable not found. Last error: ${lastError || "none"}`);
process.exit(1);
