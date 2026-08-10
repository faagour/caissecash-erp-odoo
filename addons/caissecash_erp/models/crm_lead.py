from odoo import fields, models


class CrmLead(models.Model):
    """Champs complémentaires CaisseCash sur les prospects/opportunités CRM.

    Les champs déjà natifs à Odoo (raison sociale, contact, téléphone,
    e-mail, adresse, ville, source, commercial responsable) ne sont pas
    dupliqués ici : voir partner_name, contact_name, phone, email_from,
    street, city, source_id, user_id sur crm.lead.
    """

    _inherit = "crm.lead"

    whatsapp = fields.Char(string="WhatsApp")
    ice = fields.Char(string="ICE")
    identifiant_fiscal = fields.Char(string="IF")
    rc = fields.Char(string="RC")

    business_type = fields.Selection(
        [
            ("restaurant", "Restaurant"),
            ("snack", "Snack"),
            ("cafe", "Café"),
            ("commerce", "Commerce"),
            ("autre", "Autre"),
        ],
        string="Type de commerce",
    )
    pos_count = fields.Integer(string="Nombre de points de vente", default=1)
    requested_module_ids = fields.Many2many(
        "caissecash.software.module", string="Solution demandée"
    )
