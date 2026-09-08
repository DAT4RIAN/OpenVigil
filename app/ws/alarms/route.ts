import { handleRealtimeWebSocket } from "../_shared";

export function GET(request: Request): Response {
  return handleRealtimeWebSocket(request, "alarms");
}
