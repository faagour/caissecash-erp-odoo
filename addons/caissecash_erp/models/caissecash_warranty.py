from dateutil.relativedelta import relativedelta

from odoo import api, fields, models


class CaissecashWarranty(models.Model):
    _name = "caissecash.warranty"
    _description = "Garantie matérielle CaisseCash"
    _inherit = ["mail.thread"]
    _order = "date_end"

    name = fields.Char(
        string="Référence", required=True, copy=False, readonly=True,
        default=lambda self: self.env["ir.sequence"].next_by_code("caissecash.warranty") or "Nouveau",
    )

    equipment_id = fields.Many2one(
        "caissecash.equipment", string="Équipement", required=True, tracking=True
    )
    lot_id = fields.Many2one(related="equipment_id.lot_id", string="Numéro de série", store=True)
    partner_id = fields.Many2one(related="equipment_id.customer_id", string="Client", store=True)
    establishment_id = fields.Many2one(related="equipment_id.establishment_id", string="Établissement", store=True)

    # Pas de valeur par défaut : tant que la date de début n'est pas renseignée
    # (ex: avant l'installation effective), la garantie reste "à activer".
    date_start = fields.Date(string="Date de début")
    # Durée par défaut = 2 ans, mais non imposée : modifiable par ligne (cf. cahier des charges §18).
    duration_months = fields.Integer(string="Durée (mois)", default=24)
    date_end = fields.Date(string="Date de fin", compute="_compute_date_end", store=True)

    warranty_type = fields.Selection(
        [
            ("standard", "Standard"),
            ("extended", "Étendue"),
            ("none", "Hors garantie"),
        ],
        default="standard",
        string="Type de garantie",
        tracking=True,
    )
    conditions = fields.Text(string="Conditions")
    cancelled = fields.Boolean(string="Annulée manuellement", copy=False)

    state = fields.Selection(
        [
            ("a_activer", "À activer"),
            ("active", "Active"),
            ("expiring_soon", "Bientôt expirée"),
            ("expired", "Expirée"),
            ("cancelled", "Annulée"),
        ],
        compute="_compute_state",
        store=True,
        string="Statut",
    )

    sav_ticket_ids = fields.One2many(
        "caissecash.sav.ticket", "warranty_id", string="Interventions associées"
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "Nouveau") == "Nouveau":
                vals["name"] = self.env["ir.sequence"].next_by_code("caissecash.warranty") or "Nouveau"
        return super().create(vals_list)

    @api.depends("date_start", "duration_months")
    def _compute_date_end(self):
        for rec in self:
            if rec.date_start and rec.duration_months:
                rec.date_end = rec.date_start + relativedelta(months=rec.duration_months)
            else:
                rec.date_end = False

    @api.depends("date_start", "date_end", "warranty_type", "cancelled")
    def _compute_state(self):
        today = fields.Date.context_today(self)
        for rec in self:
            if rec.cancelled:
                rec.state = "cancelled"
            elif rec.warranty_type == "none" or not rec.date_start or not rec.date_end:
                rec.state = "a_activer"
            elif rec.date_end < today:
                rec.state = "expired"
            elif rec.date_end <= today + relativedelta(days=30):
                rec.state = "expiring_soon"
            else:
                rec.state = "active"

    def action_cancel(self):
        self.write({"cancelled": True})

    def action_reactivate(self):
        self.write({"cancelled": False})
