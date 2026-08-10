# CaisseCash ERP — Odoo Community

ERP interne de CaisseCash (Odoo 19 Community), **indépendant** du monorepo
produit `caisse-cash` (POS/KDS/Kiosk/Waiter/Dashboard/Admin Panel + Node
orchestrateur). Odoo ne remplace aucune de ces applications : il gère
uniquement CRM, ventes, achats, dépenses, associés/financement (suivi
indicatif), stock/SAV, installations, garanties et abonnements logiciels
côté back-office.

Aucune base de données, aucun port ni aucun fichier du projet `caisse-cash`
existant n'est modifié par ce dépôt.

## Stack

- Odoo 19 Community (image construite localement, voir `Dockerfile`)
- PostgreSQL 16 (instance dédiée, séparée de celle de `caisse-cash`)
- Docker / Docker Compose
- Addon métier custom : [`addons/caissecash_erp`](addons/caissecash_erp)

## Démarrage rapide (développement)

```bash
cp .env.example .env
# Éditer .env : POSTGRES_PASSWORD et ODOO_ADMIN_PASSWORD (obligatoire, pas de valeur par défaut utilisable)

docker compose up -d --build
docker compose logs -f odoo   # attendre "HTTP service (werkzeug) running"
```

Puis ouvrir http://127.0.0.1:8069 (port configurable via `ODOO_HOST_PORT`
dans `.env`). Créer la base `caissecash_erp` (nom fixé par `ODOO_DB_FILTER`)
via l'assistant de premier lancement, avec `ODOO_ADMIN_PASSWORD` comme mot
de passe maître.

Installer ensuite le module **CaisseCash ERP** depuis Apps (il installe
automatiquement Contacts, CRM, Ventes, Achats, Facturation, Inventaire,
Projet, Feuilles de temps, Employés, Maintenance, Calendrier, Discuss).

Pour charger des données de démonstration, cocher "Données de démonstration"
à la création de la base, ou : `docker compose exec odoo odoo -c /etc/odoo/odoo.conf -d caissecash_erp -i caissecash_erp --without-demo=False --stop-after-init`.

## Environnements dev / production

| Fichier | Rôle |
|---|---|
| `docker-compose.yml` | Base commune (services, volumes, réseau dédié `caissecash-erp-net`, aucun port publié) |
| `docker-compose.override.yml` | Chargé automatiquement en local (`docker compose up`) : publie Odoo (8069/8072) et Postgres (5433, dev uniquement) sur `127.0.0.1` |
| `docker-compose.prod.yml` | À charger explicitement en production : `docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build`. Odoo reste lié à `127.0.0.1` — un reverse proxy HTTPS (Nginx/Traefik, à déployer sur le VPS) fait le lien vers l'extérieur. Postgres n'est jamais publié. |

PostgreSQL n'est **jamais exposé publiquement**, ni en dev ni en prod.

## Sécurité / bonnes pratiques appliquées

- Base Postgres et volumes strictement séparés de `caisse-cash` (réseau Docker dédié, aucune connexion directe entre les deux stacks).
- Aucun identifiant réel dans le dépôt : `.env` est ignoré par Git, seul `.env.example` (valeurs factices) est versionné.
- `admin_passwd` et les identifiants DB sont injectés à l'exécution du container via variables d'environnement (voir `config/odoo.conf.template` + `scripts/entrypoint.sh`), jamais écrits en dur.
- `list_db` désactivé par défaut et `dbfilter` restreint à la base `caissecash_erp` (le gestionnaire de bases n'est pas exposé publiquement).
- L'ancien addon `Desktop/extraaddons/caissecash_pos` (habillage visuel du POS natif Odoo) n'est ni chargé ni modifié : `caissecash_erp` ne dépend pas de `point_of_sale`.

## Documentation

- [docs/INSTALL.md](docs/INSTALL.md) — installation détaillée pas à pas
- [docs/UPDATE.md](docs/UPDATE.md) — mise à jour du module / de la stack
- [docs/BACKUP_RESTORE.md](docs/BACKUP_RESTORE.md) — sauvegarde automatique + restauration
- [docs/USER_GUIDE.md](docs/USER_GUIDE.md) — guide court par rôle (Direction, Commercial, Stock, Technicien, Comptabilité)
- [docs/API_INTEGRATION_FUTURE.md](docs/API_INTEGRATION_FUTURE.md) — architecture prévue pour la synchronisation future avec le système CaisseCash (non connectée dans ce MVP)

## Tests

```bash
docker compose run --rm odoo odoo -c /etc/odoo/odoo.conf \
  -d caissecash_erp_test --test-enable --stop-after-init \
  -i caissecash_erp
```

Voir [docs/INSTALL.md](docs/INSTALL.md#tests) pour le détail.

## État du MVP / limites connues

- Comptabilité : module **Invoicing** (Community) + `l10n_ma` à installer selon vos besoins de localisation marocaine ; pas de rapprochement bancaire avancé (réservé à Enterprise).
- Abonnements : le cron **prépare des factures brouillon**, il ne les valide ni ne prélève automatiquement (validation manuelle requise, cf. cahier des charges).
- Intégration avec le système CaisseCash : **non connectée**, seulement documentée (voir `docs/API_INTEGRATION_FUTURE.md`).
- **Associés et financement** : suivi indicatif uniquement (soldes, historique). **Aucune écriture comptable officielle générée automatiquement** — un apport n'est jamais traité comme du chiffre d'affaires. Les écritures réelles doivent être validées et saisies par le comptable marocain de l'entreprise.
- **Dépenses/Achats** : workflow de validation fonctionnel, mais ne remplace pas une saisie comptable officielle (TVA, immobilisations, etc.) — à valider également par le comptable.
- Reverse proxy Nginx + HTTPS (déploiement VPS) : pas encore écrit, en attente que le VPS soit stable (`docker-compose.prod.yml` prévoit déjà l'emplacement).
