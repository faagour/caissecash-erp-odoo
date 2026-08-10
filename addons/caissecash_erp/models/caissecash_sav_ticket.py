from odoo import api, fields, models


class CaissecashSavTicket(models.Model):
    _name = "caissecash.sav.ticket"
    _description = "Ticket SAV CaisseCash"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "priority desc, date_open desc"

    name = fields.Char(
        string="Numéro", required=True, copy=False, readonly=True,
        default=lambda self: self.env["ir.sequence"].next_by_code("caissecash.sav.ticket") or "Nouveau",
    )

    partner_id = fields.Many2one("res.partner", string="Client", required=True, tracking=True)
    contact_name = fields.Char(string="Contact")
    establishment_id = fields.Many2one("caissecash.establishment", string="Établissement", tracking=True)
    equipment_id = fields.Many2one("caissecash.equipment", string="Équipement", tracking=True)
    lot_id = fields.Many2one(related="equipment_id.lot_id", string="Numéro de série", store=True)
    warranty_id = fields.Many2one("caissecash.warranty", string="Garantie liée")
    under_warranty = fields.Boolean(string="Sous garantie")
    billable = fields.Boolean(string="Facturable")

    category = fields.Selection(
        [
            ("materiel", "Matériel"),
            ("logiciel", "Logiciel"),
            ("reseau", "Réseau"),
            ("formation", "Formation / usage"),
            ("autre", "Autre"),
        ],
        default="materiel",
        string="Catégorie",
    )
    description = fields.Text(string="Description du problème", required=True)
    diagnostic = fields.Text(string="Diagnostic")
    actions_taken = fields.Text(string="Actions réalisées")

    priority = fields.Selection(
        [
            ("0", "Basse"),
            ("1", "Normale"),
            ("2", "Haute"),
            ("3", "Critique"),
        ],
        default="1",
        string="Priorité",
        tracking=True,
    )

    technician_id = fields.Many2one("res.users", string="Technicien assigné", tracking=True)
    date_open = fields.Datetime(string="Date d'ouverture", default=fields.Datetime.now, required=True)

    part_ids = fields.One2many("caissecash.sav.ticket.part", "ticket_id", string="Pièces utilisées")
    time_spent = fields.Float(string="Temps passé (h)")
    cost = fields.Monetary(string="Coût", currency_field="currency_id")
    currency_id = fields.Many2one(
        "res.currency", default=lambda self: self.env.company.currency_id
    )

    resolution = fields.Text(string="Solution")

    state = fields.Selection(
        [
            ("nouveau", "Nouveau"),
            ("diagnostic", "Diagnostic"),
            ("attente_client", "En attente du client"),
            ("attente_piece", "En attente de pièce"),
            ("planifie", "Intervention planifiée"),
            ("en_cours", "En cours"),
            ("resolu", "Résolu"),
            ("ferme", "Fermé"),
            ("annule", "Annulé"),
        ],
        default="nouveau",
        tracking=True,
        string="Statut",
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "Nouveau") == "Nouveau":
                vals["name"] = self.env["ir.sequence"].next_by_code("caissecash.sav.ticket") or "Nouveau"
        return super().create(vals_list)


class CaissecashSavTicketPart(models.Model):
    _name = "caissecash.sav.ticket.part"
    _description = "Pièce utilisée sur un ticket SAV"

    ticket_id = fields.Many2one("caissecash.sav.ticket", required=True, ondelete="cascade")
    product_id = fields.Many2one("product.product", string="Pièce", required=True)
    quantity = fields.Float(string="Quantité", default=1.0)
