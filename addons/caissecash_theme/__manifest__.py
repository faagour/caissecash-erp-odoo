{
    "name": "CaisseCash ERP — Thème",
    "version": "19.0.1.0.0",
    "category": "Themes/Backend",
    "summary": "Habillage CaisseCash de l'ERP : couleurs, page de connexion, logo, icônes mobile",
    "description": """
CaisseCash ERP — Thème
======================
Habillage visuel uniquement (aucun modèle, aucune donnée) :

- couleurs du logo CaisseCash (marine / orange) dans tout le backend ;
- page de connexion aux couleurs CaisseCash, sans « Powered by Odoo » ;
- titre d'onglet, favicon, nom et icônes de l'application installée sur
  téléphone (PWA) : « CaisseCash » au lieu de « Odoo ».

Désinstallable à tout moment sans impact sur les données.
""",
    "author": "CaisseCash",
    "license": "LGPL-3",
    "depends": ["web"],
    "data": [
        "views/webclient_templates.xml",
    ],
    "assets": {
        # Chargé avant les variables Odoo (définies en !default) pour les remplacer.
        "web._assets_primary_variables": [
            ("prepend", "caissecash_theme/static/src/scss/primary_variables.scss"),
        ],
        "web.assets_backend": [
            "caissecash_theme/static/src/scss/backend.scss",
            "caissecash_theme/static/src/js/title_service.js",
        ],
        "web.assets_frontend": [
            "caissecash_theme/static/src/scss/login.scss",
        ],
    },
    "installable": True,
    "application": False,
    "auto_install": False,
}
