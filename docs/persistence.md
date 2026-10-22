# TenderMatch Durable Persistence Architecture & Operational Runbook

## 1. Audit of GitHub Actions Encrypted Cache (Phase 1.1)

TenderMatch previously used GitHub Actions with an encrypted cache (`tender-db-encrypted-v1-${{ github.run_id }}`). While authenticated encryption (`cryptography.fernet`) prevents token leakage in public repositories, GitHub Actions caches **cannot provide durable production persistence**.

### Failure Modes & Limitations:
1. **Cache Eviction**: GitHub Actions caches operate under a strict 10 GB per-repository quota with an LRU (Least Recently Used) eviction policy. A burst of CI runs or test builds can silently evict the production database cache.
2. **Cache Expiration**: Any cache entry not accessed within 7 days is permanently purged by GitHub.
3. **Runner Crashes & Timeouts**: If a runner crashes, runs out of memory, or exceeds workflow timeouts after the pipeline modifies `data/tenders.db` but before `actions/cache/save` finishes, all state mutations (new tender versions, feedback, notification records) are completely lost.
4. **Race Conditions & Cache Clobbering**: Actions concurrency `queue: max` serializes execution but does not guarantee atomic CAS across workflow runs. If two runs overlap or a queued job is cancelled, cache lineage can diverge.
5. **Decryption Key / Secret Failure**: If `TENDERMATCH_DB_CACHE_KEY` is missing or rotated without re-encrypting the cache, workflows fail closed and cannot start without manual intervention.

---

## 2. Production Persistence Design (Phase 1.2)

For TenderMatch's single-customer workload, the simplest and most reliable production design is a **supervised Python runtime on a host with a durable mounted POSIX volume for SQLite**.

### Key Characteristics:
- **Zero Microservice Overhead**: Avoids unnecessary complexity of cloud PostgreSQL clusters, message brokers, or Kubernetes pods.
- **Volume Mount**: The database is stored at `/var/lib/tendermatch/tenders.db` on a persistent volume with private filesystem permissions (`0700` directory, `0600` file).
- **Process Supervisor**: Managed by `systemd` (`deploy/tendermatch.service`), ensuring automatic restart on crashes (`Restart=always`), sandboxed execution, and structured logging via `journald`.
- **Scheduled Ingestion**: `scheduler.py` runs periodically (default 30 minutes) and inspects `is_maintenance_active()` to cleanly pause executions when administrative backups or restores are in progress.

---

## 3. Reversible Migration Procedure (Phase 1.3)

To transition state safely from the Actions cache (or any snapshot) to a durable mounted volume:

### Automated Migration Command:
```bash
python -m deploy.migrate_cache_to_durable \
  data/tenders.db.enc \
  /var/lib/tendermatch/tenders.db \
  --key "${TENDERMATCH_DB_CACHE_KEY}"
```

### Safety Guarantees:
1. **Integrity & Schema Verification**: Decrypts into an isolated temporary directory and performs SQLite `PRAGMA integrity_check` plus schema compatibility checks on all core tables before touching the target.
2. **Automatic Rollback Snapshot**: If the target database already exists, creates an atomic backup (`/var/lib/tendermatch/tenders.db.rollback.<timestamp>.sqlite3`).
3. **Maintenance Locking**: Acquires `MaintenanceLock` at `/var/lib/tendermatch/tenders.db.maintenance`, ensuring running schedulers pause immediately.
4. **Reconciliation**: Verifies table counts (`tenders`, `tender_versions`, `tender_amendments`, `salesperson_feedback`, `email_batches`, `email_notifications`, `pipeline_runs`) match between source and destination. If a discrepancy occurs, automatically rolls back to the prior snapshot.
5. **Manual Rollback**:
```bash
python -m deploy.migrate_cache_to_durable \
  --rollback /var/lib/tendermatch/tenders.db.rollback.<timestamp>.sqlite3 \
  /var/lib/tendermatch/tenders.db
```

---

## 4. Operational Backup & Recovery Policy (Phase 1.4)

### Scheduled Daily Snapshots:
A cron job or systemd timer runs `deploy/backup_cron.sh` daily:
```bash
# Create atomic snapshot and retain last 7 snapshots
python -m data.backup backup /var/lib/tendermatch/tenders.db /var/backups/tendermatch/tenders_$(date +%Y%m%d_%H%M%S).sqlite3
python -m data.backup prune /var/backups/tendermatch --keep 7
```

### Recovery Procedure:
To restore an integrity-checked snapshot:
```bash
# Safely restore with schema verification and maintenance pause
python -m data.backup restore /var/backups/tendermatch/tenders_<timestamp>.sqlite3 /var/lib/tendermatch/tenders.db --replace --verify-schema
```

### Pending Outbox Recovery:
On service startup, `deploy/entrypoint.sh` calls `deliver_due_batches()` to automatically retry any notification batches that were interrupted or scheduled for retry, ensuring no duplicate emails or lost notifications.
