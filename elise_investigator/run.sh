#!/usr/bin/with-contenv bashio
set -e

# One-time cleanup of files introduced only by the failed dev.52 diagnostic
# rebuild. Never touch the historical dev.46 memory or request journal.
rm -f \
  /data/conscious_memory_dev52.sqlite3 \
  /data/conscious_memory_dev52.sqlite3-wal \
  /data/conscious_memory_dev52.sqlite3-shm \
  /data/investigator_requests_dev52.sqlite3 \
  /data/investigator_requests_dev52.sqlite3-wal \
  /data/investigator_requests_dev52.sqlite3-shm

cd /app
exec python3 main_dev46.py
