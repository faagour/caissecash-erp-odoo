#!/usr/bin/env bash
# Sauvegarde manuelle a la demande (en plus des sauvegardes automatiques
# quotidiennes du service "backup" defini dans docker-compose.yml).
# Sauvegarde : 1) le dump SQL Postgres  2) le filestore Odoo (pieces jointes).
set -euo pipefail

cd "$(dirname "$0")/.."
set -a; source .env; set +a

STAMP=$(date +%Y%m%d_%H%M%S)
OUT_DIR="backups/manual_${STAMP}"
mkdir -p "$OUT_DIR"

echo "==> Dump PostgreSQL (${POSTGRES_DB})"
docker compose exec -T db pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -F c -f "/tmp/${POSTGRES_DB}.dump"
docker compose cp "db:/tmp/${POSTGRES_DB}.dump" "$OUT_DIR/db.dump"
docker compose exec -T db rm "/tmp/${POSTGRES_DB}.dump"

echo "==> Archive du filestore Odoo"
docker compose exec -T odoo tar -czf "/tmp/filestore.tar.gz" -C /var/lib/odoo filestore
docker compose cp "odoo:/tmp/filestore.tar.gz" "$OUT_DIR/filestore.tar.gz"
docker compose exec -T odoo rm "/tmp/filestore.tar.gz"

echo "==> Sauvegarde terminée : $OUT_DIR"
