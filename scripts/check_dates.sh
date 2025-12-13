#!/usr/bin/env bash
set -euo pipefail

# Poll for available dates for a specific doctor every INTERVAL seconds
# Uses the termin-ator CLI and auto-fetches tokens via scripts/get_tokens.py if missing.

# Config via env vars (override as needed)
: "${PORTAL:=S55299BD3}"
: "${DOCTOR:=USER-1-DOC-1}"
: "${INSURANCE:=Gesetzlich}"
: "${VISITREASON:=Spezial}"
: "${INTERVAL:=1800}"   # 30 minutes
: "${INSECURE:=}"       # set to any non-empty value to disable TLS verification
: "${NOTIFY:=}"         # set to any non-empty value to enable macOS notifications

cmd_insecure=()
if [[ -n "${INSECURE}" ]]; then
  cmd_insecure=(--insecure)
fi

# Bootstrap headers unless already set
if [[ -z "${TERMIN_COOKIE:-}" || -z "${TERMIN_XSRF_TOKEN:-}" ]]; then
  if ! eval "$(python3 scripts/get_tokens.py --portal "${PORTAL}" ${INSECURE:+--insecure})"; then
    echo "[info] token bootstrap failed; continuing without tokens" 1>&2
  fi
fi

fetch_dates() {
  termin-ator dates \
    --portal "${PORTAL}" \
    --doctor "${DOCTOR}" \
    --insurance "${INSURANCE}" \
    --visitreason "${VISITREASON}" \
    ${TERMIN_XSRF_TOKEN:+--xsrf "${TERMIN_XSRF_TOKEN}"} \
    ${TERMIN_COOKIE:+--cookie "${TERMIN_COOKIE}"} \
    "${cmd_insecure[@]}"
}

tmp_old=$(mktemp)
trap 'rm -f "${tmp_old}"' EXIT

echo "[check-dates] Portal=${PORTAL} Doctor=${DOCTOR} Interval=${INTERVAL}s" 1>&2

# initial fetch
fetch_dates | tee "${tmp_old}"

while true; do
  sleep "${INTERVAL}"
  tmp_new=$(mktemp)
  if ! fetch_dates > "${tmp_new}"; then
    echo "[warn] fetch failed at $(date -Is)" 1>&2
    rm -f "${tmp_new}"
    continue
  fi
  # Compare JSON arrays and show newly appeared dates
  tmp_added=$(mktemp)
  python3 - "$tmp_old" "$tmp_new" "$tmp_added" << 'PY'
import json, sys
old, new, out = sys.argv[1], sys.argv[2], sys.argv[3]
try:
    with open(old) as f: a = set(json.load(f))
    with open(new) as f: b = set(json.load(f))
except Exception:
    # On parse error, just print the new file
    with open(new) as f: sys.stdout.write(f.read())
    sys.exit(0)
added = sorted(b - a)
if added:
    print("\n[update] new dates detected at", __import__('datetime').datetime.now().isoformat())
    print(json.dumps(added, indent=2, ensure_ascii=False))
    # Write a CSV line for shell consumption
    with open(out, 'w') as outf:
        outf.write(','.join(added))
PY
  # macOS notification (optional)
  if [[ -n "${NOTIFY}" ]]; then
    if [[ -s "$tmp_added" ]]; then
      csv=$(cat "$tmp_added")
      # show up to 5 dates in the notification
      first5=$(echo "$csv" | awk -F',' '{for (i=1;i<=NF && i<=5;i++){if(i>1)printf ","; printf $i}}')
      total=$(echo "$csv" | awk -F',' '{print NF}')
      suffix=""
      if [[ "$total" -gt 5 ]]; then
        suffix=" …"
      fi
      if [[ "$(uname -s)" == "Darwin" ]] && command -v osascript >/dev/null 2>&1; then
        osascript -e "display notification \"New dates: ${first5}${suffix}\" with title \"Termin_ator\" subtitle \"${DOCTOR}\""
      fi
    fi
  fi
  rm -f "$tmp_added"
  mv "${tmp_new}" "${tmp_old}"
done
