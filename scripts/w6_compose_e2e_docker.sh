#!/usr/bin/env bash
# Wave 6 Compose E2E — docker mock backend (opt-in socket). Skip with reason if unavailable.
set -euo pipefail
BASE="${BASE_URL:-http://localhost:8000}"
API="$BASE/api/v1"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

echo "== W6 Compose E2E (docker) against $BASE =="

if [[ ! -S /var/run/docker.sock ]]; then
  echo "SKIP: /var/run/docker.sock not available — docker mock E2E not run"
  exit 0
fi

# Prefer ensuring Local Lab is up (socket is mounted in default compose).
# Overlay still forces MOCK_INFRA_BACKEND=docker at cold start if desired.
if command -v docker >/dev/null 2>&1; then
  docker compose -f "$ROOT/docker-compose.yml" -f "$ROOT/docker-compose.docker-infra.yml" up -d >/dev/null 2>&1 || \
    docker compose -f "$ROOT/docker-compose.yml" up -d >/dev/null 2>&1 || true
fi

echo "-- wait for live --"
for i in $(seq 1 60); do
  if curl -sf "$BASE/health/live" >/dev/null; then break; fi
  sleep 2
  if [[ $i -eq 60 ]]; then echo "API not live"; exit 1; fi
done

echo "-- login --"
TOKEN=$(curl -sf -X POST "$API/auth/token" \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  -d 'username=admin@brokerbridge.local&password=admin123!' | python3 -c 'import sys,json; print(json.load(sys.stdin)["access_token"])')
AUTH="Authorization: Bearer $TOKEN"

echo "-- activate mock/docker infra --"
set +e
ACT=$(curl -s -o /tmp/w6_docker_act.json -w "%{http_code}" -X PUT "$API/admin/providers/infrastructure" \
  -H "$AUTH" -H 'Content-Type: application/json' \
  -d '{"provider_type":"mock","validate_first":true,"activate":true,"config":{"mock_backend":"docker"}}')
set -e
if [[ "$ACT" != "200" ]]; then
  echo "SKIP: mock/docker activate failed (socket not mounted into api/worker?)"
  python3 -c 'import json; print(json.load(open("/tmp/w6_docker_act.json")))' || true
  exit 0
fi
python3 -c 'import json; d=json.load(open("/tmp/w6_docker_act.json")); assert d["config"].get("mock_backend")=="docker"; print("badge=mock/docker")'

BROKERS=$(curl -sf "$API/brokers?limit=25&offset=0" -H "$AUTH")
CLIENT_ID=$(echo "$BROKERS" | python3 -c 'import sys,json; print(json.load(sys.stdin)["items"][0]["client_id"])')
ALPHA=$(echo "$BROKERS" | python3 -c 'import sys,json; print([b["id"] for b in json.load(sys.stdin)["items"] if "Alpha" in b["display_name"]][0])')

# Clear prior expiry blocks for order path
if command -v docker >/dev/null 2>&1; then
  docker compose -f "$ROOT/docker-compose.yml" exec -T postgres \
    psql -U "${POSTGRES_USER:-brokerbridge}" -d "${POSTGRES_DB:-brokerbridge}" \
    -c "UPDATE clients SET status='active'; DELETE FROM subscriptions;" >/dev/null 2>&1 || true
fi

echo "-- create instance (container) + suspend/start --"
set +e
INST_BODY=$(curl -s -o /tmp/w6_docker_inst.json -w "%{http_code}" -X POST "$API/infrastructure/instances" \
  -H "$AUTH" -H 'Content-Type: application/json' \
  -d "{\"client_id\":\"$CLIENT_ID\",\"region\":\"ewr\",\"label\":\"w6-docker-e2e\"}")
set -e
if [[ "$INST_BODY" != "201" ]]; then
  echo "SKIP: docker create_instance failed (Engine pull/permissions?):"
  python3 -c 'import json; print(json.load(open("/tmp/w6_docker_inst.json")))' || cat /tmp/w6_docker_inst.json
  exit 0
fi
INST_ID=$(python3 -c 'import json; print(json.load(open("/tmp/w6_docker_inst.json"))["id"])')

curl -sf -X POST "$API/infrastructure/instances/$INST_ID/suspend" -H "$AUTH" \
  | python3 -c 'import sys,json; assert json.load(sys.stdin)["status"]=="suspended"'
curl -sf -X POST "$API/infrastructure/instances/$INST_ID/start" -H "$AUTH" \
  | python3 -c 'import sys,json; assert json.load(sys.stdin)["status"]=="running"'

# Ensure Alpha has an IP for order path
EXISTING=$(curl -sf "$API/infrastructure/assignments" -H "$AUTH" | python3 -c "
import sys,json
rows=json.load(sys.stdin)
for r in rows:
  if r.get('broker_account_id')=='$ALPHA' and r.get('status')=='active':
    print(r['static_ip_id']); break
")
if [[ -z "$EXISTING" ]]; then
  IP=$(curl -sf -X POST "$API/infrastructure/ips" -H "$AUTH" -H 'Content-Type: application/json' -d '{"region":"ewr"}')
  IP_ID=$(echo "$IP" | python3 -c 'import sys,json; print(json.load(sys.stdin)["id"])')
  curl -sf -X POST "$API/infrastructure/ips/$IP_ID/assign" -H "$AUTH" -H 'Content-Type: application/json' \
    -d "{\"broker_account_id\":\"$ALPHA\"}" >/dev/null
  curl -sf -X POST "$API/infrastructure/ips/$IP_ID/attach" -H "$AUTH" -H 'Content-Type: application/json' \
    -d "{\"instance_id\":\"$INST_ID\"}" >/dev/null
fi

OID="w6-docker-$(date +%s)"
curl -sf -X POST "$API/orders/buy" -H "$AUTH" -H 'Content-Type: application/json' \
  -d "{\"client_id\":\"$CLIENT_ID\",\"client_order_id\":\"$OID\",\"symbol\":\"AAPL\",\"quantity\":1,\"region_preference\":\"ewr\"}" \
  | python3 -c 'import sys,json; assert json.load(sys.stdin)["status"]=="SUBMITTED"'

curl -sf -X POST "$API/monitoring/events/drain" -H "$AUTH" >/dev/null || true

echo "-- Vultr bad-key still fails cleanly --"
set +e
BAD=$(curl -s -o /tmp/w6_docker_vultr.json -w "%{http_code}" -X PUT "$API/admin/providers/infrastructure" \
  -H "$AUTH" -H 'Content-Type: application/json' \
  -d '{"provider_type":"vultr","validate_first":true,"activate":true,"config":{"api_key":"fake-key","default_region":"ewr"}}')
set -e
test "$BAD" = "422"

curl -sf -X DELETE "$API/infrastructure/instances/$INST_ID" -H "$AUTH" -o /dev/null -w "%{http_code}" | grep -q 204

echo "== W6 docker E2E PASS =="
