from odoo import fields, models


class ResPartner(models.Model):
    """Champs complémentaires CaisseCash sur la fiche client/fournisseur
    (cahier des charges §14). Les champs déjà natifs à Odoo ne sont pas
    dupliqués : name (raison sociale), phone, email, street, city,
    comment (notes), user_id (commercial, ajouté par le module sale),
    property_payment_term_id (conditions de paiement).
    """

    _inherit = "res.partner"

    commercial_name = fields.Char(string="Nom commercial")
    responsable_name = fields.Char(string="Responsable")
    whatsapp = fields.Char(string="WhatsApp")

    ice = fields.Char(string="ICE")
    identifiant_fiscal = fields.Char(string="IF")
    rc = fields.Char(string="RC")
    taxe_professionnelle = fields.Char(string="Taxe professionnelle")

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
    source_id = fields.Many2one("utm.source", string="Source du prospect")

    establishment_ids = fields.One2many(
        "caissecash.establishment", "partner_id", string="Établissements"
    )

    vendor_lead_time_days = fields.Integer(
        string="Délai moyen fournisseur (jours)",
        help="Délai moyen constaté entre commande et réception, à titre indicatif.",
    )
