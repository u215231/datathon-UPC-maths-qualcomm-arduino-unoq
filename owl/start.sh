#!/usr/bin/env bash
# Started at boot by cron (see install.sh): waits for the board's model servers, then serves Uino's web page.
cd "$(dirname "$0")/.." || exit 1
set -a; . ./config.env; set +a
mkdir -p results
for _ in $(seq 180); do
  curl -sf "http://127.0.0.1:${LLM_PORT}/health" >/dev/null && curl -sf "http://127.0.0.1:${EMBED_PORT}/health" >/dev/null && break
  sleep 1
done
[ -f data/teach.db ] || python3 coach/build_bank.py >> results/owl-web.log 2>&1
exec python3 web3/server.py --host 0.0.0.0 --port "${OWL_PORT:-8000}" >> results/owl-web.log 2>&1
