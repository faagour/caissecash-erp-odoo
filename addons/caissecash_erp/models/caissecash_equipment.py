from odoo import api, fields, models


class CaissecashEquipment(models.Model):
    """Une unite de materiel CaisseCash suivie individuellement (numero de serie).

    Design : ce modele reste distinct de maintenance.equipment (pense pour du
    materiel interne a l'entreprise) et s'appuie sur stock.lot pour la
    tracabilite serie / les mouvements de stock (cf. decision d'architecture
    validee en Phase 1). La sortie de stock vers le client se fait via un
    bon de livraison standard (emplacement de type "client"), ce qui sort
    correctement la valeur du stock interne sans etre re-modelise ici.
    """

    _name = "caissecash.equipment"
    _description = "Équipement CaisseCash (matériel suivi)"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "name"

    name = fields.Char(compute="_compute_name", store=True)

    product_id = fields.Many2one("product.product", string="Produit", required=True, tracking=True)
    lot_id = fields.Many2one(
        "stock.lot", string="Numéro de série",
        domain="[('product_id', '=', product_id)]",
        tracking=True,
    )

    vendor_id = fields.Many2one("res.partner", string="Fournisseur")
    purchase_date = fields.Date(string="Date d'achat")
    cost = fields.Monetary(string="Coût d'achat", currency_field="currency_id")
    currency_id = fields.Many2one(
        "res.currency", default=lambda self: self.env.company.currency_id
    )

    customer_id = fields.Many2one("res.partner", string="Client actuel", tracking=True)
    establishment_id = fields.Many2one(
        "caissecash.establishment", string="Établissement", tracking=True
    )
    install_date = fields.Date(string="Date d'installation")

    warranty_ids = fields.One2many("caissecash.warranty", "equipment_id", string="Garanties")
    sav_ticket_ids = fields.One2many("caissecash.sav.ticket", "equipment_id", string="Tickets SAV")

    sav_status = fields.Selection(
        [
            ("en_service", "En service"),
            ("en_reparation", "En réparation"),
            ("retourne", "Retourné (SAV)"),
            ("defectueux", "Défectueux"),
            ("remplace", "Remplacé"),
        ],
        default="en_service",
        string="Statut SAV",
        tracking=True,
    )

    @api.depends("product_id", "lot_id.name")
    def _compute_name(self):
        for rec in self:
            if rec.product_id and rec.lot_id:
                rec.name = f"{rec.product_id.display_name} — {rec.lot_id.name}"
            elif rec.product_id:
                rec.name = rec.product_id.display_name
            else:
                rec.name = "Nouvel équipement"
