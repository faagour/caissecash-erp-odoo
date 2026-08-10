from odoo import api, fields, models


class PurchaseOrder(models.Model):
    """Frais annexes d'achat (cahier des charges §9) : transport, import,
    douane, autres frais — non couverts nativement par le module Achats
    Community, nécessaires pour connaître le coût total réel d'un
    approvisionnement (et donc la marge réelle en aval).
    """

    _inherit = "purchase.order"

    transport_cost = fields.Monetary(string="Frais de transport", currency_field="currency_id")
    customs_cost = fields.Monetary(string="Douane", currency_field="currency_id")
    import_cost = fields.Monetary(string="Frais d'importation", currency_field="currency_id")
    other_cost = fields.Monetary(string="Autres frais", currency_field="currency_id")
    total_landed_cost = fields.Monetary(
        string="Coût total (avec frais annexes)",
        currency_field="currency_id",
        compute="_compute_total_landed_cost",
        store=True,
    )

    payment_mode = fields.Selection(
        [("virement", "Virement"), ("cheque", "Chèque"), ("especes", "Espèces"), ("autre", "Autre")],
        string="Moyen de paiement",
    )
    paid_by_user_id = fields.Many2one("res.users", string="Personne ayant payé")

    @api.depends("amount_total", "transport_cost", "customs_cost", "import_cost", "other_cost")
    def _compute_total_landed_cost(self):
        for order in self:
            order.total_landed_cost = (
                order.amount_total
                + order.transport_cost
                + order.customs_cost
                + order.import_cost
                + order.other_cost
            )
