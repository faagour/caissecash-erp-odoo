from odoo import api, fields, models


class CaissecashInstallation(models.Model):
    _name = "caissecash.installation"
    _description = "Fiche d'installation CaisseCash"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "date_planned desc"

    name = fields.Char(
        string="Référence", required=True, copy=False, readonly=True,
        default=lambda self: self.env["ir.sequence"].next_by_code("caissecash.installation") or "Nouvelle installation",
    )

    partner_id = fields.Many2one("res.partner", string="Client", required=True, tracking=True)
    establishment_id = fields.Many2one(
        "caissecash.establishment", string="Établissement", required=True, tracking=True
    )
    address = fields.Char(related="establishment_id.street", string="Adresse", readonly=True)
    sale_order_id = fields.Many2one("sale.order", string="Commande associée")

    equipment_ids = fields.Many2many(
        "caissecash.equipment", string="Matériel prévu"
    )
    software_module_ids = fields.Many2many(
        "caissecash.software.module", string="Logiciels à activer"
    )

    technician_id = fields.Many2one("res.users", string="Technicien", tracking=True)
    date_planned = fields.Datetime(string="Date prévue", tracking=True)
    time_slot = fields.Char(string="Créneau", help="Ex : 09:00 - 11:00")

    checklist = fields.Html(string="Checklist")
    tests_done = fields.Text(string="Tests effectués")
    training_done = fields.Boolean(string="Formation réalisée")
    observations = fields.Text(string="Remarques")
    photo_ids = fields.Many2many(
        "ir.attachment", "caissecash_installation_photo_rel", "installation_id", "attachment_id",
        string="Photos",
    )

    customer_validated = fields.Boolean(string="Validé par le client", copy=False)
    customer_signature = fields.Binary(string="Signature client", copy=False)

    state = fields.Selection(
        [
            ("a_planifier", "À planifier"),
            ("planifiee", "Planifiée"),
            ("preparation", "Matériel en préparation"),
            ("prete", "Prête"),
            ("deplacement", "En déplacement"),
            ("en_cours", "En cours"),
            ("terminee", "Terminée"),
            ("reportee", "Reportée"),
            ("annulee", "Annulée"),
        ],
        default="a_planifier",
        tracking=True,
        string="Statut",
    )
    date_done = fields.Date(
        string="Terminée le", copy=False, tracking=True,
        help="Renseignée automatiquement quand l'installation passe à « Terminée » "
             "(sert aux objectifs « Installations terminées »).",
    )

    @api.model_create_multi
    def create(self, vals_list):
        today = fields.Date.context_today(self)
        for vals in vals_list:
            if not vals.get("name") or vals.get("name") == "Nouvelle installation":
                vals["name"] = self.env["ir.sequence"].next_by_code("caissecash.installation") or "Nouvelle installation"
            if vals.get("state") == "terminee" and not vals.get("date_done"):
                vals["date_done"] = today
        return super().create(vals_list)

    def write(self, vals):
        if vals.get("state") == "terminee" and "date_done" not in vals:
            finishing = self.filtered(lambda rec: rec.state != "terminee" and not rec.date_done)
            result = super().write(vals)
            if finishing:
                finishing.date_done = fields.Date.context_today(self)
            return result
        return super().write(vals)

    def action_mark_done(self):
        for rec in self:
            rec.state = "terminee"
            for equip in rec.equipment_ids:
                equip.write({
                    "customer_id": rec.partner_id.id,
                    "establishment_id": rec.establishment_id.id,
                    "install_date": fields.Date.context_today(rec),
                })
                self.env["caissecash.warranty"].create({
                    "equipment_id": equip.id,
                    "date_start": fields.Date.context_today(rec),
                })

    def action_create_subscription(self):
        """Propose l'activation d'un abonnement une fois l'installation terminée."""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "Nouvel abonnement",
            "res_model": "caissecash.subscription",
            "view_mode": "form",
            "target": "current",
            "context": {
                "default_partner_id": self.partner_id.id,
                "default_establishment_id": self.establishment_id.id,
                "default_software_module_ids": [(6, 0, self.software_module_ids.ids)],
            },
        }
