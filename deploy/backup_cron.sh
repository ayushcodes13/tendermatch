#!/usr/bin/env bash
# Operational backup script for TenderMatch durable SQLite volume.
set -euo pipefail

DB_PATH="${TENDERMATCH_DB_PATH:-/var/lib/tendermatch/tenders.db}"
BACKUP_DIR="${TENDERMATCH_BACKUP_DIR:-/var/backups/tendermatch}"
KEEP_COUNT="${TENDERMATCH_BACKUP_KEEP:-7}"

mkdir -p "${BACKUP_DIR}"
chmod 0700 "${BACKUP_DIR}"

TIMESTAMP="$(date -u +%Y%m%d_%H%M%S)"
SNAPSHOT="${BACKUP_DIR}/tenders_${TIMESTAMP}.sqlite3"

echo "[$(date -u --iso-8601=seconds)] Creating integrity-checked SQLite snapshot..."
python -m data.backup backup "${DB_PATH}" "${SNAPSHOT}"

echo "[$(date -u --iso-8601=seconds)] Pruning backups older than ${KEEP_COUNT} newest snapshots..."
python -m data.backup prune "${BACKUP_DIR}" --keep "${KEEP_COUNT}"

echo "[$(date -u --iso-8601=seconds)] Backup complete: ${SNAPSHOT}"
