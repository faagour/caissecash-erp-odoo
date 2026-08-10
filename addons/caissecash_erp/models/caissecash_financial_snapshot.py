from odoo import api, fields, models


class CaissecashFinancialSnapshot(models.Model):
    """Historique de la valeur de l'entreprise (résultat cumulé dans le temps) :
    chaque dépense validée/payée et chaque facture client postée crée un point.
    La courbe monte à chaque vente, descend à chaque dépense.

    Reconstruit entièrement à chaque appel de _rebuild() (pas de saisie
    manuelle possible) — un modèle stocké classique plutôt qu'un modèle
    virtuel, pour que la vue Graphique native reste fiable."""

    _name = "caissecash.financial.snapshot"
    _description = "Historique de valeur CaisseCash"
    _order = "date"

    date = fields.Date(required=True)
    label = fields.Char(string="Événement")
    day_amount = fields.Monetary(string="Mouvement", currency_field="currency_id")
    cumulative_result = fields.Monetary(
        string="Valeur de l'entreprise (cumulé)", currency_field="currency_id", aggregator="max",
    )
    currency_id = fields.Many2one(
        "res.currency", default=lambda self: self.env.company.currency_id
    )

    @api.model
    def _rebuild(self):
        self.search([]).unlink()

        events = {}  # date -> (net_amount, [labels])

        for e in self.env["caissecash.expense"].search([("state", "in", ("validated", "paid"))]):
            if not e.date:
                continue
            amount, labels = events.get(e.date, (0.0, []))
            events[e.date] = (amount - e.amount_total, labels + [f"- {e.name}"])

        for m in self.env["account.move"].search([("move_type", "=", "out_invoice"), ("state", "=", "posted")]):
            if not m.invoice_date:
                continue
            amount, labels = events.get(m.invoice_date, (0.0, []))
            events[m.invoice_date] = (amount + m.amount_total, labels + [f"+ {m.name}"])

        cumulative = 0.0
        vals_list = []
        for event_date in sorted(events):
            day_amount, labels = events[event_date]
            cumulative += day_amount
            vals_list.append({
                "date": event_date,
                "label": " ; ".join(labels),
                "day_amount": day_amount,
                "cumulative_result": cumulative,
            })
        if vals_list:
            self.create(vals_list)
        return True
