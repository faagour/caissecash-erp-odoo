from odoo import api, fields, models


class CaissecashEstablishment(models.Model):
    """Un point de vente / etablissement physique d'un client CaisseCash.

    Un client (res.partner) peut posseder plusieurs etablissements
    (ex: plusieurs succursales d'une chaine de restaurants).
    """

    _name = "caissecash.establishment"
    _description = "Établissement client CaisseCash"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "name"

    name = fields.Char(string="Nom commercial", required=True, tracking=True)
    partner_id = fields.Many2one(
        "res.partner", string="Client", required=True, tracking=True,
    )
    street = fields.Char(string="Adresse")
    city = fields.Char(string="Ville")
    contact_name = fields.Char(string="Contact sur place")
    phone = fields.Char(string="Téléphone")
    opening_hours = fields.Text(string="Horaires")

    software_module_ids = fields.Many2many(
        "caissecash.software.module", string="Modules CaisseCash activés"
    )
    equipment_ids = fields.One2many(
        "caissecash.equipment", "establishment_id", string="Matériel installé"
    )
    equipment_count = fields.Integer(compute="_compute_equipment_count")

    commissioning_date = fields.Date(string="Date de mise en service")
    technician_id = fields.Many2one("res.users", string="Technicien responsable")

    state = fields.Selection(
        [
            ("draft", "Brouillon"),
            ("active", "Actif"),
            ("suspended", "Suspendu"),
            ("closed", "Fermé"),
        ],
        default="draft",
        tracking=True,
        string="Statut",
    )

    @api.depends("equipment_ids")
    def _compute_equipment_count(self):
        for rec in self:
            rec.equipment_count = len(rec.equipment_ids)
