import { AsyncLocalStorage } from "node:async_hooks";

export interface WindOpsWorkerEnv {
  readonly ASSETS?: Fetcher;
  readonly DB?: D1Database;
  readonly IMAGES?: {
    input(stream: ReadableStream): {
      transform(options: Record<string, unknown>): {
        output(options: { format: string; quality: number }): Promise<{ response(): Response }>;
      };
    };
  };
}

const workerEnvironment = new AsyncLocalStorage<WindOpsWorkerEnv>();

export function runWithWorkerEnv<T>(env: WindOpsWorkerEnv, callback: () => T): T {
  return workerEnvironment.run(env, callback);
}

export function getWorkerEnv(): WindOpsWorkerEnv {
  return workerEnvironment.getStore() ?? {};
}
