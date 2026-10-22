#!/usr/bin/env bash
# Operational entrypoint for supervised TenderMatch deployment.
set -euo pipefail

DB_PATH="${TENDERMATCH_DB_PATH:-data/tenders.db}"
STORAGE_DIR="$(dirname "${DB_PATH}")"

echo "=== TenderMatch Supervised Runtime Startup ==="
echo "Configured DB Path: ${DB_PATH}"

# Ensure storage directory exists with private permissions
if [ ! -d "${STORAGE_DIR}" ]; then
    echo "Creating persistent volume storage directory: ${STORAGE_DIR}"
    mkdir -p "${STORAGE_DIR}"
    chmod 0700 "${STORAGE_DIR}"
fi

# Initialize database schema if database does not exist
python -c "
import sqlite3
from data.db import get_connection, init_db
with get_connection() as conn:
    init_db(conn)
    conn.commit()
print('Database schema initialized and verified.')
"

# Recover and attempt delivery for any due outbox batches
python -c "
from data.db import get_connection
from digest.outbox import deliver_due_batches
from digest.sender import send_email
with get_connection() as conn:
    results = deliver_due_batches(conn, send_email)
    print(f'Pending outbox recovery checked: {len(results)} batch(es) processed.')
"

# Hand over to scheduler
echo "Launching background scheduler..."
exec python scheduler.py
