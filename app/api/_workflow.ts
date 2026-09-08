import { readServerWorkflow } from "@/db/runtime-store";
import { getWorkerEnv } from "@/lib/worker-env";

export const readWorkflowForApi = () => readServerWorkflow(getWorkerEnv().DB);
