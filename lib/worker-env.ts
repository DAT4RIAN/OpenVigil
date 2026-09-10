import { AsyncLocalStorage } from "node:async_hooks";

export interface OpenVigilWorkerEnv {
  readonly ASSETS?: Fetcher;
  readonly DB?: D1Database;
  readonly WINDOPS_RUNTIME_MODE?: string;
  readonly WINDOPS_BACKEND_BASE_URL?: string;
  readonly WINDOPS_BACKEND_AUTH_MODE?: string;
  readonly WINDOPS_BACKEND_API_TOKEN?: string;
  readonly WINDOPS_BACKEND_DELEGATION_SECRET?: string;
  readonly WINDOPS_BACKEND_REQUEST_TIMEOUT_MS?: string;
  readonly WINDOPS_BACKEND_EXPECTED_RELEASE_ID?: string;
  readonly WINDOPS_BACKEND_EXPECTED_COMMIT_SHA?: string;
  readonly WINDOPS_BACKEND_EXPECTED_IMAGE_DIGEST?: string;
  readonly IMAGES?: {
    input(stream: ReadableStream): {
      transform(options: Record<string, unknown>): {
        output(options: { format: string; quality: number }): Promise<{ response(): Response }>;
      };
    };
  };
}

const workerEnvironment = new AsyncLocalStorage<OpenVigilWorkerEnv>();

export function runWithWorkerEnv<T>(env: OpenVigilWorkerEnv, callback: () => T): T {
  return workerEnvironment.run(env, callback);
}

export function getWorkerEnv(): OpenVigilWorkerEnv {
  return workerEnvironment.getStore() ?? {};
}
