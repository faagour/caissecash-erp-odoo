from odoo import fields, models


class ResUsers(models.Model):
    _inherit = "res.users"

    caissecash_hide_guide = fields.Boolean(
        string="Masquer le guide « Bien démarrer »",
        help="Coché quand la personne a masqué le guide de Mon espace (elle peut le réafficher en bas de la page).",
    )
