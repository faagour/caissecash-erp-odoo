from odoo.addons.web.controllers.webmanifest import WebManifest

NAVY = "#0d1b4a"
ICON_DIR = "/caissecash_theme/static/src/img"


class CaissecashWebManifest(WebManifest):
    """Nom, couleurs et icônes de l'application installée sur téléphone (PWA).

    Seules les méthodes utilitaires sont surchargées : les routes restent
    celles du module web.
    """

    def _get_webmanifest(self):
        manifest = super()._get_webmanifest()
        # Le paramètre système web.web_app_name reste prioritaire s'il a été personnalisé.
        if manifest.get("name") == "Odoo":
            manifest["name"] = "CaisseCash"
        manifest["short_name"] = manifest["name"]
        manifest["background_color"] = "#ffffff"
        manifest["theme_color"] = NAVY
        manifest["icons"] = [
            {
                "src": f"{ICON_DIR}/icon-{size}.png",
                "sizes": size,
                "type": "image/png",
                "purpose": "any maskable",
            }
            for size in ("192x192", "512x512")
        ]
        return manifest

    def _icon_path(self):
        return "caissecash_theme/static/src/img/icon-192x192.png"
