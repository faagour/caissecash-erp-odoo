# Guide de mise à jour

## Mettre à jour le module `caissecash_erp` (après modification de code)

```bash
docker compose exec odoo odoo -c /etc/odoo/odoo.conf \
  -d caissecash_erp -u caissecash_erp --stop-after-init
docker compose restart odoo
```

`-u caissecash_erp` recharge les vues/sécurité/données et applique les
migrations de schéma simples (nouveaux champs, etc.). Toujours **sauvegarder
avant** une mise à jour touchant aux modèles (voir `docs/BACKUP_RESTORE.md`).

## Mettre à jour Odoo (image de base)

1. Sauvegarder (base + filestore).
2. Modifier `ODOO_VERSION` dans `.env` si changement de version majeure.
3. `docker compose up -d --build`
4. `docker compose exec odoo odoo -c /etc/odoo/odoo.conf -d caissecash_erp -u all --stop-after-init`
5. Vérifier les logs (`docker compose logs -f odoo`) et tester le parcours
   critique (création prospect → devis → installation → facture) avant de
   considérer la mise à jour validée.

## Mettre à jour les modules Odoo standards (CRM, Ventes, etc.)

Identique : `-u <nom_module>` ou `-u all` pour tout recharger. Ne jamais
utiliser `-u all` en production sans sauvegarde préalable et sans avoir testé
sur un environnement de dev/UAT au préalable.

## Rollback

En cas de problème après mise à jour : restaurer la sauvegarde précédente
(voir `docs/BACKUP_RESTORE.md`) plutôt que de tenter une correction à chaud
sur la base de production.
