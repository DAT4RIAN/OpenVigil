import { buildRealtimeFrame, realtimeHello, type RealtimeChannel } from "@/lib/realtime-stream";
import { readServerWorkflow } from "@/db/runtime-store";
import { getWorkerEnv } from "@/lib/worker-env";
import { alarms } from "@/lib/operations-data";
import { overlayAlarmRuntimeState } from "@/db/alarm-runtime-store";

interface WorkerSocket {
  readonly readyState: number;
  accept(): void;
  send(message: string): void;
  close(code?: number, reason?: string): void;
  addEventListener(type: "message", listener: (event: MessageEvent) => void): void;
  addEventListener(type: "close" | "error", listener: () => void): void;
}

interface WorkerSocketPair {
  0: WorkerSocket;
  1: WorkerSocket;
}

type WebSocketPairConstructor = new () => WorkerSocketPair;
type UpgradeResponseInit = ResponseInit & { webSocket: WorkerSocket };

const upgradeRequired = (channel: RealtimeChannel, runtimeSupported: boolean): Response =>
  Response.json(
    {
      error: {
        code: "WEBSOCKET_UPGRADE_REQUIRED",
        message: `Use a WebSocket Upgrade request to connect to /ws/${channel}.`,
      },
      meta: {
        channel,
        protocol: "windops.realtime.v1",
        runtimeSupported,
        deterministic: true,
      },
    },
    {
      status: 426,
      headers: {
        "cache-control": "no-store",
        connection: "Upgrade",
        "content-type": "application/json; charset=utf-8",
        upgrade: "websocket",
      },
    },
  );

export function handleRealtimeWebSocket(
  request: Request,
  channel: RealtimeChannel,
): Promise<Response> {
  const pairConstructor = (
    globalThis as typeof globalThis & { WebSocketPair?: WebSocketPairConstructor }
  ).WebSocketPair;
  const wantsUpgrade = request.headers.get("upgrade")?.toLowerCase() === "websocket";

  if (!wantsUpgrade || !pairConstructor) {
    return Promise.resolve(upgradeRequired(channel, Boolean(pairConstructor)));
  }

  const pair = new pairConstructor();
  const client = pair[0];
  const server = pair[1];
  const cadenceMs = channel === "scada" ? 1_000 : 2_000;
  let sequence = 0;
  let closed = false;
  let timer: ReturnType<typeof setTimeout> | undefined;

  const stop = () => {
    closed = true;
    if (timer !== undefined) clearTimeout(timer);
  };
  const send = (message: unknown) => server.send(JSON.stringify(message));
  const tick = async () => {
    if (closed) return;
    try {
      const workflow =
        channel === "scada" ? undefined : (await readServerWorkflow(getWorkerEnv().DB)).snapshot;
      const alarmItems =
        channel === "alarms" ? await overlayAlarmRuntimeState(getWorkerEnv().DB, alarms) : alarms;
      send(buildRealtimeFrame(channel, sequence, workflow, alarmItems));
      sequence += 1;
      timer = setTimeout(() => void tick(), cadenceMs);
    } catch {
      stop();
      server.close(1011, "stream delivery failed");
    }
  };

  server.accept();
  send(realtimeHello(channel));
  void tick();
  server.addEventListener("message", (event) => {
    if (event.data === "ping") {
      send({
        protocol: "windops.realtime.v1",
        channel,
        event: "pong",
        sequence,
        deterministic: true,
      });
    }
  });
  server.addEventListener("close", stop);
  server.addEventListener("error", stop);

  return Promise.resolve(
    new Response(null, {
      status: 101,
      webSocket: client,
    } as UpgradeResponseInit),
  );
}
