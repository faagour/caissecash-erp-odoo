# Intégration future avec le système CaisseCash (non connectée dans ce MVP)

Ce document décrit l'architecture **prévue** pour synchroniser, plus tard,
Odoo (back-office) avec le système CaisseCash (orchestrateur Node.js +
Postgres/Redis multi-tenant). **Aucune connexion réseau ni base partagée
n'existe à ce stade** : les deux systèmes restent totalement indépendants
tant que ce plan n'est pas explicitement validé et implémenté séparément.

## Principe

- Communication **exclusivement via API HTTP authentifiée**, jamais par
  accès direct à la base de données de l'autre système.
- Odoo expose des endpoints REST via un contrôleur custom dans
  `caissecash_erp/controllers/` (à créer lors de l'implémentation réelle).
  L'orchestrateur CaisseCash consomme ces endpoints ; le sens inverse
  (Odoo → orchestrateur) utiliserait les webhooks déjà en place côté
  CaisseCash si besoin, sur le même principe.
- Authentification : clé API dédiée par système appelant (header
  `X-API-Key`), stockée côté Odoo comme `ir.config_parameter` (jamais en
  dur), rotation possible sans redéploiement.
- **Idempotence obligatoire** : chaque requête de création/mise à jour porte
  un `event_id` unique (UUID généré côté CaisseCash). Odoo enregistre les
  `event_id` déjà traités (table de log dédiée, même principe que
  `caissecash.subscription.invoice.log`) et renvoie le résultat déjà connu
  si l'`event_id` est rejoué, sans dupliquer l'effet.
- **Journalisation** : chaque appel entrant/sortant loggé (endpoint, payload
  résumé, résultat, durée) pour audit et débogage.

## Endpoints envisagés (côté Odoo, à construire)

| Événement CaisseCash | Endpoint Odoo (indicatif) | Effet côté Odoo |
|---|---|---|
| Création d'un client | `POST /caissecash_erp/api/v1/customers` | Crée/retrouve un `res.partner` |
| Création d'un établissement | `POST /caissecash_erp/api/v1/establishments` | Crée un `caissecash.establishment` lié au partner |
| Activation d'un abonnement | `POST /caissecash_erp/api/v1/subscriptions` | Crée un `caissecash.subscription` (état `actif`) |
| Changement de formule | `PATCH /caissecash_erp/api/v1/subscriptions/{id}` | Met à jour `product_id`/`amount`/`software_module_ids` |
| Suspension pour impayé | `POST /caissecash_erp/api/v1/subscriptions/{id}/suspend` | Passe l'état à `impaye` ou `suspendu` |
| Information d'installation | `POST /caissecash_erp/api/v1/installations/{id}/report` | Met à jour `caissecash.installation` (statut, matériel) |
| Statut d'un équipement | `PATCH /caissecash_erp/api/v1/equipments/{id}/status` | Met à jour `sav_status` sur `caissecash.equipment` |

Sens Odoo → CaisseCash (à définir précisément lors de l'implémentation,
probablement via webhook sortant déclenché sur écriture des modèles
ci-dessus) : notification de résiliation, mise à jour de statut SAV visible
côté Dashboard manager, etc.

## Mapping de données (indicatif)

| CaisseCash (multi-tenant, `tenant_id`) | Odoo |
|---|---|
| `tenant_id` + `customer_id` | `res.partner` (avec `ref` = identifiant externe CaisseCash pour retrouver le mapping) |
| Établissement / point de vente | `caissecash.establishment` |
| Abonnement / formule | `caissecash.subscription` |
| Équipement enregistré côté Dashboard | `caissecash.equipment` (rapproché par numéro de série) |

## Ce qui reste hors périmètre du MVP

- Aucun code d'intégration n'est livré dans cette version : uniquement ce
  plan, pour validation avant tout développement.
- Le connecteur définitif devra gérer : retries avec backoff, file
  d'attente en cas d'indisponibilité d'un des deux systèmes, et tests de
  bout en bout en environnement UAT avant toute mise en production.
