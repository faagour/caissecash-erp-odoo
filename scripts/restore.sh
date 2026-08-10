#!/usr/bin/env bash
# Restauration a partir d'une sauvegarde produite par backup.sh
# (ou par le service "backup" automatique, meme format de dump pg_dump -F c).
#
# Usage : ./scripts/restore.sh backups/manual_20260805_120000
#
# ATTENTION : ecrase la base et le filestore Odoo actuels. Destructif.
# Confirmation manuelle demandee avant execution.
set -euo pipefail

cd "$(dirname "$0")/.."
set -a; source .env; set +a

BACKUP_DIR="${1:?Usage: restore.sh <dossier_de_sauvegarde>}"
DB_DUMP="$BACKUP_DIR/db.dump"
FILESTORE_ARCHIVE="$BACKUP_DIR/filestore.tar.gz"

[ -f "$DB_DUMP" ] || { echo "Introuvable : $DB_DUMP"; exit 1; }
[ -f "$FILESTORE_ARCHIVE" ] || { echo "Introuvable : $FILESTORE_ARCHIVE"; exit 1; }

echo "Ceci va ECRASER la base '${POSTGRES_DB}' et le filestore Odoo actuels."
read -r -p "Confirmer la restauration depuis '${BACKUP_DIR}' ? (taper 'oui') " CONFIRM
[ "$CONFIRM" = "oui" ] || { echo "Annulé."; exit 1; }

echo "==> Arrêt d'Odoo (la base reste accessible pour la restauration)"
docker compose stop odoo

echo "==> Restauration de la base PostgreSQL"
docker compose exec -T db dropdb -U "$POSTGRES_USER" --if-exists "$POSTGRES_DB"
docker compose exec -T db createdb -U "$POSTGRES_USER" "$POSTGRES_DB"
docker compose cp "$DB_DUMP" "db:/tmp/restore.dump"
docker compose exec -T db pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --no-owner "/tmp/restore.dump"
docker compose exec -T db rm "/tmp/restore.dump"

echo "==> Restauration du filestore Odoo"
docker compose cp "$FILESTORE_ARCHIVE" "odoo:/tmp/filestore.tar.gz"
docker compose run --rm --no-deps --entrypoint bash odoo -c \
  "rm -rf /var/lib/odoo/filestore && tar -xzf /tmp/filestore.tar.gz -C /var/lib/odoo && rm /tmp/filestore.tar.gz"

echo "==> Redémarrage d'Odoo"
docker compose start odoo

echo "==> Restauration terminée."
