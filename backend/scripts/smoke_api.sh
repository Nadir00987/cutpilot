#!/usr/bin/env bash
# CutPilot AI backend smoke test.
# Usage: ./scripts/smoke_api.sh [BASE_URL]   (default http://localhost:8000)
set -euo pipefail

BASE="${1:-http://localhost:8000}"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

echo "== base: $BASE"

echo "== 1. healthz (public)"
curl -fsS "$BASE/api/v1/healthz" | head -c 200; echo

echo "== 2. /admin/health WITHOUT auth must be 401/403"
code="$(curl -sS -o /dev/null -w '%{http_code}' "$BASE/api/v1/admin/health")"
echo "   -> HTTP $code"
if [[ "$code" != "401" && "$code" != "403" ]]; then
  echo "FAIL: expected 401/403, got $code"; exit 1
fi

EMAIL="smoke_$(date +%s)@example.com"
PASS="SmokePass123!"

echo "== 3. signup $EMAIL"
curl -fsS -X POST "$BASE/api/v1/auth/signup" \
  -H 'Content-Type: application/json' \
  -d "{\"email\":\"$EMAIL\",\"password\":\"$PASS\",\"name\":\"Smoke\"}" \
  -o "$TMP/signup.json"
echo "   ok"

echo "== 4. login"
curl -fsS -X POST "$BASE/api/v1/auth/login" \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  -d "username=$EMAIL&password=$PASS" \
  -o "$TMP/login.json"
TOKEN="$(python3 -c "import json;print(json.load(open('$TMP/login.json'))['access_token'])")"
echo "   token acquired (${#TOKEN} chars)"
AUTH=(-H "Authorization: Bearer $TOKEN")

echo "== 5. /auth/me"
curl -fsS "$BASE/api/v1/auth/me" "${AUTH[@]}" | head -c 200; echo

echo "== 6. create project"
curl -fsS -X POST "$BASE/api/v1/projects" \
  "${AUTH[@]}" -H 'Content-Type: application/json' \
  -d '{"name":"smoke test project"}' -o "$TMP/project.json"
PID="$(python3 -c "import json;print(json.load(open('$TMP/project.json'))['id'])")"
echo "   project id: $PID"

echo "== 7. generate 5s test mp4"
ffmpeg -y -v error \
  -f lavfi -i "testsrc2=size=640x360:rate=30:duration=5" \
  -f lavfi -i "sine=frequency=440:duration=5" \
  -c:v libx264 -pix_fmt yuv420p -c:a aac -shortest "$TMP/clip.mp4"
ls -la "$TMP/clip.mp4"

echo "== 8. upload"
curl -fsS -X POST "$BASE/api/v1/projects/$PID/upload" \
  "${AUTH[@]}" -F "file=@$TMP/clip.mp4;type=video/mp4" \
  -o "$TMP/upload.json"
python3 -c "
import json
u = json.load(open('$TMP/upload.json'))
print('   status:', u['project']['status'], '| duration:', round(u['project']['duration'],2), '| orientation:', u['project']['orientation'])
"

echo "== 9. analysis endpoint (expect 404 — no analysis run yet)"
code="$(curl -sS -o /dev/null -w '%{http_code}' "$BASE/api/v1/projects/$PID/analysis" "${AUTH[@]}")"
echo "   -> HTTP $code"
if [[ "$code" != "404" ]]; then echo "FAIL: expected 404, got $code"; exit 1; fi

echo "== 10. GET /projects/$PID/status"
curl -fsS "$BASE/api/v1/projects/$PID/status" "${AUTH[@]}" | head -c 300; echo

echo "== 11. billing plans + credits"
curl -fsS "$BASE/api/v1/billing/plans" "${AUTH[@]}" | head -c 200; echo
curl -fsS "$BASE/api/v1/billing/credits" "${AUTH[@]}" | head -c 200; echo

echo "== 12. templates (empty ok)"
curl -fsS "$BASE/api/v1/templates" "${AUTH[@]}" | head -c 200; echo

echo
echo "SMOKE OK"
