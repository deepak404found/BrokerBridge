#!/usr/bin/env bash
# Wave 6 Compose E2E — database mock backend (default CI/demo; socket unmounted)
set -euo pipefail
BASE="${BASE_URL:-http://localhost:8000}"
API="$BASE/api/v1"

echo "== W6 Compose E2E (database) against $BASE =="

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

# Local Lab continuity: prior expiry demos may leave client suspended / stale subs.
if command -v docker >/dev/null 2>&1; then
  docker compose exec -T postgres psql -U "${POSTGRES_USER:-brokerbridge}" -d "${POSTGRES_DB:-brokerbridge}" \
    -c "UPDATE clients SET status='active'; DELETE FROM subscriptions;" >/dev/null 2>&1 || true
fi

echo "-- activate mock/database infra --"
curl -sf -X PUT "$API/admin/providers/infrastructure" -H "$AUTH" -H 'Content-Type: application/json' \
  -d '{"provider_type":"mock","validate_first":true,"activate":true,"config":{"mock_backend":"database"}}' \
  | python3 -c 'import sys,json; d=json.load(sys.stdin); assert d["provider_type"]=="mock"; assert d["config"].get("mock_backend")=="database"'

echo "-- infra backend badge (Admin config) --"
curl -sf "$API/admin/providers/infrastructure" -H "$AUTH" \
  | python3 -c 'import sys,json; d=json.load(sys.stdin); assert d["provider_type"]=="mock"; assert d["config"].get("mock_backend","database")=="database"; print("badge=mock/database")'

echo "-- brokers --"
BROKERS=$(curl -sf "$API/brokers?limit=25&offset=0" -H "$AUTH")
CLIENT_ID=$(echo "$BROKERS" | python3 -c 'import sys,json; print(json.load(sys.stdin)["items"][0]["client_id"])')
ALPHA=$(echo "$BROKERS" | python3 -c 'import sys,json; print([b["id"] for b in json.load(sys.stdin)["items"] if "Alpha" in b["display_name"]][0])')

ensure_assignment() {
  local BROKER_ID="$1"
  local REGION="${2:-ewr}"
  local EXISTING
  EXISTING=$(curl -sf "$API/infrastructure/assignments" -H "$AUTH" | python3 -c "
import sys,json
rows=json.load(sys.stdin)
for r in rows:
  if r.get('broker_account_id')=='$BROKER_ID' and r.get('status')=='active':
    print(r['static_ip_id']); break
")
  if [[ -n "$EXISTING" ]]; then
    echo "$EXISTING"
    return 0
  fi
  local IP INST IP_ID INST_ID
  IP=$(curl -sf -X POST "$API/infrastructure/ips" -H "$AUTH" -H 'Content-Type: application/json' -d "{\"region\":\"$REGION\"}")
  IP_ID=$(echo "$IP" | python3 -c 'import sys,json; print(json.load(sys.stdin)["id"])')
  INST=$(curl -sf -X POST "$API/infrastructure/instances" -H "$AUTH" -H 'Content-Type: application/json' \
    -d "{\"client_id\":\"$CLIENT_ID\",\"region\":\"$REGION\",\"label\":\"w6-db-e2e\"}")
  INST_ID=$(echo "$INST" | python3 -c 'import sys,json; print(json.load(sys.stdin)["id"])')
  curl -sf -X POST "$API/infrastructure/ips/$IP_ID/assign" -H "$AUTH" -H 'Content-Type: application/json' \
    -d "{\"broker_account_id\":\"$BROKER_ID\"}" >/dev/null
  curl -sf -X POST "$API/infrastructure/ips/$IP_ID/attach" -H "$AUTH" -H 'Content-Type: application/json' \
    -d "{\"instance_id\":\"$INST_ID\"}" >/dev/null
  echo "$IP_ID"
}

echo "-- ensure instance + IP assign/attach --"
ensure_assignment "$ALPHA" "ewr" >/dev/null

echo "-- order succeeds --"
OID="w6-db-$(date +%s)"
curl -sf -X POST "$API/orders/buy" -H "$AUTH" -H 'Content-Type: application/json' \
  -d "{\"client_id\":\"$CLIENT_ID\",\"client_order_id\":\"$OID\",\"symbol\":\"AAPL\",\"quantity\":1,\"region_preference\":\"ewr\"}" \
  | python3 -c 'import sys,json; assert json.load(sys.stdin)["status"]=="SUBMITTED"'

echo "-- events drain --"
curl -sf -X POST "$API/monitoring/events/drain" -H "$AUTH" >/dev/null || true

echo "-- Vultr fake key validate fails; mock remains --"
PRIOR=$(curl -sf "$API/admin/providers/infrastructure" -H "$AUTH")
PRIOR_V=$(echo "$PRIOR" | python3 -c 'import sys,json; print(json.load(sys.stdin)["version"])')
set +e
BAD=$(curl -s -o /tmp/w6_vultr_bad.json -w "%{http_code}" -X PUT "$API/admin/providers/infrastructure" \
  -H "$AUTH" -H 'Content-Type: application/json' \
  -d '{"provider_type":"vultr","validate_first":true,"activate":true,"config":{"api_key":"fake-not-a-real-key","default_region":"ewr"}}')
set -e
test "$BAD" = "422"
python3 -c 'import json; d=json.load(open("/tmp/w6_vultr_bad.json")); assert d["error_code"]=="PROVIDER_VALIDATION_FAILED"'
AFTER=$(curl -sf "$API/admin/providers/infrastructure" -H "$AUTH")
echo "$AFTER" | python3 -c "import sys,json; d=json.load(sys.stdin); assert d['provider_type']=='mock'; assert d['version']==int('$PRIOR_V')"

echo "-- subscription expiry smoke --"
# Fresh client path: create short-lived sub ending in the past relative to enforce
START=$(python3 -c 'from datetime import datetime,timedelta,timezone; print((datetime.now(timezone.utc)-timedelta(days=2)).isoformat())')
END=$(python3 -c 'from datetime import datetime,timedelta,timezone; print((datetime.now(timezone.utc)-timedelta(minutes=1)).isoformat())')
SUB=$(curl -sf -X POST "$API/subscriptions" -H "$AUTH" -H 'Content-Type: application/json' \
  -d "{\"client_id\":\"$CLIENT_ID\",\"starts_at\":\"$START\",\"ends_at\":\"$END\",\"teardown_mode\":\"SUSPEND\"}")
SUB_ID=$(echo "$SUB" | python3 -c 'import sys,json; print(json.load(sys.stdin)["id"])')
curl -sf -X POST "$API/subscriptions/enforce-expiry" -H "$AUTH" \
  | python3 -c 'import sys,json; d=json.load(sys.stdin); assert d["expired"]>=1'
curl -sf "$API/subscriptions/$SUB_ID" -H "$AUTH" \
  | python3 -c 'import sys,json; d=json.load(sys.stdin); assert d["status"]=="expired"'
# New order should be blocked
OID2="w6-db-blocked-$(date +%s)"
set +e
BLOCK=$(curl -s -o /tmp/w6_order_block.json -w "%{http_code}" -X POST "$API/orders/buy" -H "$AUTH" -H 'Content-Type: application/json' \
  -d "{\"client_id\":\"$CLIENT_ID\",\"client_order_id\":\"$OID2\",\"symbol\":\"AAPL\",\"quantity\":1,\"region_preference\":\"ewr\"}")
set -e
test "$BLOCK" = "403"
python3 -c 'import json; d=json.load(open("/tmp/w6_order_block.json")); assert d["error_code"]=="SUBSCRIPTION_EXPIRED"'

echo "== W6 database E2E PASS =="
