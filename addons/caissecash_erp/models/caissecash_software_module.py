from odoo import fields, models


class CaissecashSoftwareModule(models.Model):
    """Etiquette representant un module logiciel CaisseCash (POS, KDS, Kiosk...).

    Volontairement un modele simple (tag) : le detail fonctionnel de ces
    applications vit dans le monorepo CaisseCash, pas dans Odoo.
    """

    _name = "caissecash.software.module"
    _description = "Module logiciel CaisseCash"
    _order = "sequence, name"

    name = fields.Char(required=True)
    code = fields.Char(help="Code technique (ex: pos, kds, kiosk, waiter, dashboard, admin)")
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)

    _code_uniq = models.Constraint(
        "UNIQUE(code)", "Le code du module logiciel doit être unique."
    )
