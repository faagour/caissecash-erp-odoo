# Guide d'installation

## Prérequis

- Docker Desktop (Windows/Mac) ou Docker Engine + Compose plugin (Linux)
- Ports libres : `127.0.0.1:8069`, `127.0.0.1:8072`, `127.0.0.1:5433` (dev)

## 1. Configuration

```bash
cp .env.example .env
```

Éditer `.env` :
- `POSTGRES_PASSWORD` : mot de passe fort, dédié à cette base (ne jamais réutiliser un mot de passe de production existant).
- `ODOO_ADMIN_PASSWORD` : mot de passe maître Odoo (protège la création/suppression de bases).
- Le reste peut rester aux valeurs par défaut pour un premier test local.

## 2. Démarrage

```bash
docker compose up -d --build
docker compose ps          # les 3 services doivent passer "healthy"
docker compose logs -f odoo
```

Premier démarrage : téléchargement des images (`odoo:19`, `postgres:16-alpine`,
`prodrigestivill/postgres-backup-local`) puis build de l'image Odoo custom
(ajout de `gettext-base` pour l'injection de config). Peut prendre plusieurs
minutes selon la connexion.

> Si l'image `odoo:19` n'est pas encore disponible sur Docker Hub au moment
> de l'installation, définir `ODOO_VERSION=18` dans `.env` puis relancer
> `docker compose up -d --build` (l'addon `caissecash_erp` est compatible
> Odoo 18/19 sans modification).

## 3. Création de la base

Ouvrir http://127.0.0.1:8069 → l'assistant de création de base s'affiche
(car aucune base `caissecash_erp` n'existe encore, malgré `list_db=False` —
ce mode ne masque que le sélecteur multi-bases, pas la création initiale).

- Nom de la base : `caissecash_erp` (doit correspondre à `POSTGRES_DB` / `ODOO_DB_FILTER` dans `.env`)
- Mot de passe maître : celui défini dans `ODOO_ADMIN_PASSWORD`
- Langue : Français
- Cocher "Données de démonstration" pour un premier test avec un client/établissement/installation d'exemple.

## 4. Installer le module CaisseCash ERP

Apps → retirer le filtre "Apps" → rechercher **CaisseCash ERP** → Installer.
Cela installe automatiquement ses dépendances Community (Contacts, CRM,
Ventes, Achats, Facturation, Inventaire, Projet, Feuilles de temps, Employés,
Maintenance, Calendrier, Discuss) et masque les apps non listées au cahier
des charges — désactivez manuellement (Réglages → Utilisateurs & Sociétés →
Applications) celles que vous ne souhaitez pas voir dans le menu principal.

## 5. Créer les utilisateurs et leur assigner un rôle

Réglages → Utilisateurs → créer un utilisateur par personne, puis cocher
dans la catégorie **CaisseCash ERP** le groupe correspondant : Direction,
Commercial, Responsable stock, Technicien, Comptabilité, ou Administrateur.

## Localisation marocaine (optionnel, recommandé)

Le module `l10n_ma` (plan comptable CGNC, TVA marocaine) est inclus dans
Odoo Community : Apps → rechercher `l10n_ma` → Installer, puis configurer
ICE/IF/RC dans Réglages → Sociétés.

## Tests

```bash
docker compose run --rm odoo odoo -c /etc/odoo/odoo.conf \
  -d caissecash_erp_test --test-enable --stop-after-init \
  -i caissecash_erp
```

Utilise une base `caissecash_erp_test` séparée (créée à la volée, à
supprimer ensuite si besoin) : `docker compose exec db dropdb -U $POSTGRES_USER caissecash_erp_test`.
Les tests couvrent notamment l'idempotence du cron de facturation
d'abonnement (`addons/caissecash_erp/tests/test_subscription_cron.py`).
