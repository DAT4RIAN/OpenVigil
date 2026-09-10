# Production identity and capability runbook

## Trust boundary

Production documents are authenticated before the application shell renders. The Sites runtime
supplies `oai-authenticated-user-id` and the optional email header. The Worker removes any incoming
trusted-session or capability header, delegates `GET /api/v1/session` to FastAPI, validates the
bounded response against the Sites subject, and only then adds an internal trusted-session header
to the server render. Anonymous requests go to the Sites-owned `/signin-with-chatgpt` route with a
validated local return path.

The browser receives the minimal session needed for UX and keeps it in React memory. It does not
derive permissions from roles, persist roles/capabilities, or receive a bearer/delegation token.
Navigation and controls are usability gates only; every backend route remains the final
authorization boundary.

## Human capability matrix

View capabilities are additionally reduced by the principal's tenant, wind-farm, turbine, entity,
and data-scope policy. The action matrix is:

| Role                   | Settings/models/resources                                                       | Alarms          | Missions                  | Work orders            |
| ---------------------- | ------------------------------------------------------------------------------- | --------------- | ------------------------- | ---------------------- |
| `operations_manager`   | `platform.manage`, `model.manage`, `resource.manage` when global scope is valid | `alarm.command` | create, comment, escalate | schedule               |
| `operations_approver`  | read only when scoped                                                           | `alarm.command` | comment, approve, reject  | read only              |
| `maintenance_reviewer` | read only when scoped                                                           | read only       | request revision          | read only              |
| `field_technician`     | read only when scoped                                                           | read only       | comment                   | complete assigned task |

`scada_ingestor` and `eam_integrator` are machine identities and cannot bootstrap the business
shell. A client-supplied capability string is ignored and cannot change a backend 403.

## Failure and recovery contract

- A document-level 401 redirects to the Sites sign-in dispatcher before business data is read. A
  client API 401 shows **重新登录** and preserves the current local return path.
- A 403 shows an explicit account/permission message and a safe sign-out/account-switch path.
- Backend release mismatch, unready, timeout, or unavailable responses remain failed closed and
  show a retry action; fixture data is never substituted.
- A browser transport failure is labelled as a network failure, separately from backend 5xx, and
  offers reload/retry.

During an incident, first inspect the session gate code and correlation ID, then backend readiness
and immutable release headers. Do not add roles in the browser or bypass the server session call.
Correct the identity mapping or backend availability, then use the visible retry/reauth action.

## Storage and validation

`openvigil-theme` is the only application preference in local storage. During the brand migration,
the client reads the legacy `windops-theme` key once and copies its valid value forward. Production
event cursors may use session storage for SSE resume; they contain only opaque/numeric cursors.
Roles, capabilities, delegation JWTs, API tokens, and secrets must never be written to either store.

Run the browser contract with `pnpm test:e2e`. It covers anonymous and machine denial, all four
human roles, desktop/mobile navigation, refresh, sign-out, client capability spoofing through the
Worker contract, 401/403/503/network recovery, the alarm-to-Mission-to-approval/work-order flow,
double-click suppression, and SSE cursor resume.
