import { existsSync } from "node:fs";
import { spawn } from "node:child_process";
import { loadEnvFile } from "node:process";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const projectRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const environmentFile = resolve(projectRoot, ".env");
const command = process.argv[2];

if (!new Set(["dev", "start"]).has(command)) {
  throw new Error("run-vinext.mjs accepts only dev or start.");
}

if (existsSync(environmentFile)) loadEnvFile(environmentFile);

const cli = resolve(projectRoot, "node_modules", "vinext", "dist", "cli.js");
const child = spawn(process.execPath, [cli, command, ...process.argv.slice(3)], {
  cwd: projectRoot,
  env: process.env,
  stdio: "inherit",
});

for (const signal of ["SIGINT", "SIGTERM"]) {
  process.once(signal, () => child.kill(signal));
}

child.once("error", (error) => {
  console.error(error instanceof Error ? error.message : String(error));
  process.exitCode = 1;
});

child.once("exit", (code, signal) => {
  if (signal) process.kill(process.pid, signal);
  else process.exitCode = code ?? 1;
});
