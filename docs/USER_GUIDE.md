# Guide utilisateur court par rôle

Menu principal : **CaisseCash ERP**.

## Direction

Accès en lecture/écriture à tous les modules CaisseCash ERP et aux apps
Odoo standards (Ventes, Achats, Comptabilité, Projet) en mode gestionnaire.
Utiliser les vues **Pivot/Graphique** (icônes en haut à droite des listes :
Établissements, Abonnements, Tickets SAV) pour les tableaux de bord :
CA facturé, abonnements actifs, tickets ouverts, garanties proches
d'expiration (filtre "Expire bientôt" sur Garanties).

## Commercial

- **CRM** : pipeline Nouveau prospect → Contacté → Démo planifiée → Démo réalisée → Devis envoyé → Négociation → Gagné/Perdu.
- **Établissements** : créer un établissement par point de vente du client (un client peut en avoir plusieurs).
- **Ventes** : devis → bon de commande.
- **Abonnements** : créer l'abonnement une fois le client actif (formule, périodicité, montant).
- Accès en lecture seule au matériel/installations (pas de modification du stock).

## Responsable stock

- **Équipements** : chaque unité de matériel vendu (caisse, imprimante...) suivie individuellement par numéro de série.
- Réceptionner les achats (app Achats) puis créer/lier l'équipement à son numéro de série.
- **Garanties** : la garantie standard (24 mois) se crée automatiquement en lien avec l'équipement, modifiable si besoin (matériel avec garantie différente).
- Ne voit pas les pipelines commerciaux ni les données RH.

## Technicien

- **Installations** et **Tickets SAV** : uniquement ceux qui vous sont assignés.
- Sur une installation : remplir la checklist, cocher "Formation réalisée", faire valider par le client, puis bouton **Marquer terminée** (met à jour automatiquement le matériel comme installé chez le client).
- Sur un ticket SAV : suivre le statut (Nouveau → Diagnostic → ... → Résolu → Fermé), enregistrer les pièces utilisées et le temps passé.
- **Le coût d'achat du matériel et les marges commerciales ne sont pas visibles** (masqués volontairement).

## Finance

- **Facturation** : factures, paiements, avoirs, relances (app Invoicing standard).
- **Abonnements** : suivi des échéances et des factures générées par abonnement (onglet "Historique de facturation" sur chaque abonnement) — les factures générées par le cron sont en **brouillon**, à vérifier et valider manuellement.
- **Associés et financement** : accès complet (associés, mouvements, validation) — voir section dédiée ci-dessous.
- **Dépenses** : création, validation, suivi des charges fixes/variables/personnel.
- N'a pas accès aux fiches techniques d'installation ni aux tickets SAV.

## Stagiaire

Accès minimal : uniquement les installations et tickets SAV qui lui sont explicitement assignés (même logique que Technicien). Aucun accès aux associés, dépenses, coûts ou marges.

## Comptable externe

Accès à l'app **Facturation** standard uniquement (factures, paiements). Aucun accès aux modules CaisseCash internes (associés, dépenses, installations, marges) — pensé pour un comptable externe à l'entreprise.

## Associés et financement (Direction/Finance/Admin uniquement)

- App séparée **Associés et financement** (icône dédiée dans le lanceur).
- Chaque associé a une fiche avec ses soldes **indicatifs** : total apports, avances, dépenses personnelles, remboursé, retiré, solde restant dû.
- Un mouvement passe par un workflow **Brouillon → À vérifier → Validé**. Une fois **validé, il ne peut plus être supprimé** — seule une **annulation tracée** (bouton "Annuler") est possible, l'historique reste visible.
- **Important** : ce module ne génère aucune écriture comptable officielle et ne traite jamais un apport comme du chiffre d'affaires. Les vraies écritures comptables restent à faire par le comptable marocain de l'entreprise, sur la base de ces mouvements validés.

## Administrateur

Accès technique complet (Réglages, utilisateurs, configuration des
séquences/cron). Le cron de facturation d'abonnement peut être suspendu
sans désinstallation via Réglages → Technique → Paramètres système →
`caissecash_erp.subscription_cron_active` = `False`.
