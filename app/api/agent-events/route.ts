import { activityEvents, windFarm } from "@/lib";

export const dynamic = "force-dynamic";

const encodeEvent = (
  event: string,
  id: string,
  data: unknown,
): Uint8Array => {
  const encoder = new TextEncoder();
  return encoder.encode(
    `event: ${event}\nid: ${id}\ndata: ${JSON.stringify(data)}\n\n`,
  );
};

/**
 * A finite, deterministic SSE replay of the public agent activity timeline.
 * Clients can reconnect to replay the fixture snapshot without persistence.
 */
export function GET(): Response {
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      controller.enqueue(
        encodeEvent("snapshot", "windops-snapshot", {
          snapshotAt: windFarm.lastUpdatedAt,
          count: activityEvents.length,
        }),
      );

      for (const activity of activityEvents) {
        controller.enqueue(encodeEvent("agent-activity", activity.id, activity));
      }

      controller.enqueue(
        encodeEvent("complete", "windops-complete", {
          snapshotAt: windFarm.lastUpdatedAt,
          delivered: activityEvents.length,
        }),
      );
      controller.close();
    },
  });

  return new Response(stream, {
    headers: {
      "cache-control": "no-cache, no-transform",
      connection: "keep-alive",
      "content-type": "text/event-stream; charset=utf-8",
      "x-accel-buffering": "no",
    },
  });
}
