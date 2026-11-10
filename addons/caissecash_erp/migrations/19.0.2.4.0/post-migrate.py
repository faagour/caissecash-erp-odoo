from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    """Donne une sorte (matériel, consommable, logiciel, pack) aux articles déjà
    créés, d'après leurs réglages Odoo. Les articles physiques sont suivis en
    stock : le catalogue de départ créait le matériel avec un numéro de série
    mais sans suivi du stock, ce qui l'empêchait d'entrer en stock."""
    env = api.Environment(cr, SUPERUSER_ID, {"active_test": False})
    templates = env["product.template"].search([("caissecash_kind", "=", False)])
    for template in templates:
        kind = template._caissecash_guess_kind()
        if kind in ("materiel", "consommable") and template.type == "consu" and not template.is_storable:
            template.with_context(caissecash_kind_sync=False).is_storable = True
        template.with_context(caissecash_kind_sync=False).caissecash_kind = kind
