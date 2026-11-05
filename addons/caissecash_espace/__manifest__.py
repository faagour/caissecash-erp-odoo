{
    "name": "CaisseCash ERP — Mon espace",
    "version": "19.0.1.1.0",
    "category": "Productivity",
    "summary": "Page d'accueil « Mon espace », pointage en un clic, animations et classement de l'équipe",
    "description": """
CaisseCash ERP — Mon espace
===========================
- Page d'accueil « Mon espace » (accueil par défaut de chaque utilisateur) :
  pointage en un clic, mes tâches du jour, messages non lus, raccourcis,
  qui est présent aujourd'hui, classement de la semaine, et le parcours
  client « Du prospect au SAV » avec le nombre de dossiers à chaque étape.
- Menu des applications rangé par rubrique (Au quotidien, Du prospect au SAV,
  Gestion), noms clairs (Clients, Stock, Pointage…) ; les applications
  inutilisées n'apparaissent qu'en mode développeur.
- Tâche terminée (bouton ✔, glisser dans « Terminé » ou case « Fait ») :
  animation « Bravo » et annonce dans le canal du pôle.
- Pointage sans géolocalisation.
- Icônes d'applications et tableau des tâches aux couleurs vives.
""",
    "author": "CaisseCash",
    "license": "LGPL-3",
    "depends": ["web", "mail", "bus", "calendar", "hr", "hr_attendance", "project", "caissecash_erp"],
    "data": [
        "data/espace_data.xml",
        "views/project_project_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "caissecash_espace/static/src/**/*.js",
            "caissecash_espace/static/src/**/*.xml",
            "caissecash_espace/static/src/**/*.scss",
        ],
    },
    "post_init_hook": "post_init_hook",
    "installable": True,
    "application": True,
    "auto_install": False,
}
