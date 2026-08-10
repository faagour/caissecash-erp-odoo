# Sauvegarde et restauration

## Sauvegarde automatique

Le service `backup` (`docker-compose.yml`, image
`prodrigestivill/postgres-backup-local`) exécute un dump PostgreSQL planifié
selon `BACKUP_SCHEDULE` (`.env`, défaut : quotidien) et conserve les fichiers
dans `./backups/`, avec rotation selon `BACKUP_KEEP_DAYS` / `_WEEKS` / `_MONTHS`.

> Ce service sauvegarde la **base de données**. Le filestore (pièces jointes,
> documents) est sauvegardé séparément via `scripts/backup.sh` (voir
> ci-dessous) — pensez à l'exécuter régulièrement, ou à l'automatiser via
> une tâche planifiée (cron/Planificateur de tâches Windows) en plus du
> service Docker.

Vérifier que les sauvegardes se produisent :
```bash
docker compose logs backup
ls -la backups/
```

## Sauvegarde manuelle complète (DB + filestore)

```bash
./scripts/backup.sh
```

Produit `backups/manual_<horodatage>/` contenant `db.dump` et
`filestore.tar.gz`. À copier régulièrement vers un stockage externe (autre
disque, cloud) — une sauvegarde qui reste sur la même machine que la
production n'est pas une vraie sauvegarde.

## Restauration

```bash
./scripts/restore.sh backups/manual_20260805_120000
```

Le script :
1. demande confirmation explicite (opération destructive) ;
2. arrête Odoo ;
3. recrée entièrement la base PostgreSQL à partir du dump ;
4. remplace le filestore ;
5. redémarre Odoo.

Après restauration, vérifier dans les logs (`docker compose logs -f odoo`)
l'absence d'erreur au démarrage, puis se connecter et contrôler quelques
enregistrements récents.

## Restauration via l'interface Odoo (alternative, base seule)

Le gestionnaire de bases Odoo (`/web/database/manager`) permet aussi de
restaurer un dump `.zip` (DB + filestore combinés) exporté depuis Odoo.
Utile en dev ; en production, préférer `scripts/restore.sh` qui ne dépend
pas de l'exposition du gestionnaire de bases (désactivé par `list_db=False`).
