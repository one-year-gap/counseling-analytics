#!/usr/bin/env sh
set -eu

APP_MODE="${APP_MODE:-server}"
APP_HOST="${APP_HOST:-0.0.0.0}"
APP_PORT="${APP_PORT:-8000}"
PINPOINT_ENABLED="${PINPOINT_ENABLED:-false}"
PINPOINT_APPLICATION_NAME="${PINPOINT_APPLICATION_NAME:-intelligence-server}"
PINPOINT_AGENT_ID="${PINPOINT_AGENT_ID:-intelligence-server}"
PINPOINT_COLLECTOR_AGENT_URI="${PINPOINT_COLLECTOR_AGENT_URI:-}"

child_pid=""

forward_signal() {
  signal="$1"
  if [ -n "${child_pid}" ] && kill -0 "${child_pid}" 2>/dev/null; then
    kill "-${signal}" "${child_pid}" 2>/dev/null || true
    wait "${child_pid}" || true
  fi
}

on_sigterm() {
  echo "[entrypoint] SIGTERM received. shutting down..."
  forward_signal TERM
  exit 143
}

on_sigint() {
  echo "[entrypoint] SIGINT received. shutting down..."
  forward_signal INT
  exit 130
}

trap on_sigterm TERM
trap on_sigint INT

run_bg_and_wait() {
  "$@" &
  child_pid=$!
  wait "${child_pid}"
  status=$?
  child_pid=""
  return "${status}"
}

run_server() {
  echo "[entrypoint] APP_MODE=${APP_MODE} -> starting unified intelligence server"
  if [ "${PINPOINT_ENABLED}" = "true" ]; then
    echo "[entrypoint] Pinpoint Python agent enabled app=${PINPOINT_APPLICATION_NAME} agent=${PINPOINT_AGENT_ID} collector=${PINPOINT_COLLECTOR_AGENT_URI:-unset}"
  fi
  run_bg_and_wait uvicorn app.realtime.main:app --host "${APP_HOST}" --port "${APP_PORT}"
}

run_batch() {
  echo "[entrypoint] APP_MODE=batch -> running one-off batch"
  run_bg_and_wait python -m app.batch.main
  echo "[entrypoint] batch completed."
}

case "${APP_MODE}" in
  server)
    run_server
    ;;
  realtime)
    run_server
    ;;
  analysis-server)
    run_server
    ;;
  batch)
    run_batch
    ;;
  *)
    echo "[entrypoint] Unknown APP_MODE: ${APP_MODE} (allowed: server|realtime|analysis-server|batch)"
    exit 2
    ;;
esac
