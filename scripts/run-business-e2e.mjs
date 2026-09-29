import { existsSync } from "node:fs";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { resolve } from "node:path";

const root = fileURLToPath(new URL("../", import.meta.url));
const python = resolve(
  root,
  "backend/.venv",
  process.platform === "win32" ? "Scripts/python.exe" : "bin/python",
);
if (!existsSync(python)) {
  throw new Error(
    "Install the backend environment first: cd backend && uv sync --frozen --extra test",
  );
}
const result = spawnSync(python, [resolve(root, "backend/scripts/run_business_e2e.py")], {
  cwd: root,
  stdio: "inherit",
  windowsHide: true,
});
if (result.error) throw result.error;
process.exitCode = result.status ?? 1;
