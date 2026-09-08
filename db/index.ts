import { drizzle } from "drizzle-orm/d1";
import { getWorkerEnv } from "../lib/worker-env";
import * as schema from "./schema";

declare global {
  // eslint-disable-next-line @typescript-eslint/no-namespace
  namespace Cloudflare {
    interface Env {
      DB?: D1Database;
    }
  }
}

export function getDb() {
  const env = getWorkerEnv();
  if (!env.DB) {
    throw new Error(
      "Cloudflare D1 binding `DB` is unavailable. Set the `d1` field in .openai/hosting.json to `DB` or let your control plane inject the real binding values before using the database.",
    );
  }

  return drizzle(env.DB, { schema });
}
