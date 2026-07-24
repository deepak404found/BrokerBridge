# Light load harness notes

BrokerBridge does **not** claim a fixed 5k orders/min in CI. For demos:

1. Ensure mock infra has an assigned+attached IP for the target broker.
2. Prefer `EVENT_PROVIDER=memory` or a healthy Redpanda for outbox drain.
3. Use `hey` / Locust against `/api/v1/orders/buy` with unique `client_order_id`s.
4. Watch Dashboard KPIs and `/health/ready` under Redis-stop chaos separately.

See `docs/demo/INTERVIEWER_CHECKLIST.md` for a copy-paste `hey` example.
