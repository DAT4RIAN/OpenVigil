import { handleRealtimeWebSocket } from "../_shared";

export function GET(request: Request): Promise<Response> {
  return handleRealtimeWebSocket(request, "alarms");
}
