from odoo import fields, models


class CaissecashDashboard(models.TransientModel):
    """Tableau de bord résultat : combine facturation (account.move) et
    dépenses (caissecash.expense), deux modèles distincts qu'Odoo Community
    n'agrège pas nativement dans une seule vue. Recalculé à chaque ouverture
    (modèle transient, aucune donnée stockée en dur)."""

    _name = "caissecash.dashboard"
    _description = "Tableau de bord résultat CaisseCash"

    currency_id = fields.Many2one(
        "res.currency", default=lambda self: self.env.company.currency_id
    )

    total_invoiced = fields.Monetary(string="Total facturé (clients)", compute="_compute_kpis")
    total_paid = fields.Monetary(string="Total encaissé", compute="_compute_kpis")
    total_unpaid = fields.Monetary(string="Total impayé (débiteurs)", compute="_compute_kpis")
    unpaid_invoice_count = fields.Integer(string="Nombre de factures impayées", compute="_compute_kpis")

    total_expenses = fields.Monetary(string="Total dépenses validées/payées", compute="_compute_kpis")
    total_purchases = fields.Monetary(
        string="Total achats confirmés (hors frais annexes)", compute="_compute_kpis"
    )

    result = fields.Monetary(
        string="Résultat approximatif (facturé − dépenses)", compute="_compute_kpis",
        help="Vue simplifiée : total facturé moins total des dépenses enregistrées. "
             "Ne remplace pas un compte de résultat officiel établi par le comptable.",
    )

    def _compute_kpis(self):
        Move = self.env["account.move"]
        Expense = self.env["caissecash.expense"]
        Purchase = self.env["purchase.order"]

        for rec in self:
            invoices = Move.search([("move_type", "=", "out_invoice"), ("state", "=", "posted")])
            rec.total_invoiced = sum(invoices.mapped("amount_total"))
            paid = invoices.filtered(lambda m: m.payment_state in ("paid", "in_payment"))
            rec.total_paid = sum(paid.mapped("amount_total"))
            unpaid = invoices.filtered(lambda m: m.payment_state not in ("paid", "in_payment", "reversed"))
            rec.total_unpaid = sum(unpaid.mapped("amount_total"))
            rec.unpaid_invoice_count = len(unpaid)

            expenses = Expense.search([("state", "in", ("validated", "paid"))])
            rec.total_expenses = sum(expenses.mapped("amount_total"))

            purchases = Purchase.search([("state", "in", ("purchase", "done"))])
            rec.total_purchases = sum(purchases.mapped("amount_total"))

            rec.result = rec.total_invoiced - rec.total_expenses

    def action_refresh(self):
        """Rouvrir le formulaire relance le calcul des KPI ; on reconstruit
        aussi l'historique ici (jamais dans un compute : une écriture en
        base au milieu d'un calcul de champ corrompt le calcul en cours)."""
        self.env["caissecash.financial.snapshot"]._rebuild()
        return {
            "type": "ir.actions.act_window",
            "res_model": "caissecash.dashboard",
            "view_mode": "form",
            "target": "current",
        }

    def action_view_expense_graph(self):
        """Ouvre le vrai graphique natif Dépenses (modèle stocké, robuste)
        plutôt que d'essayer d'en intégrer un dans cette fiche virtuelle."""
        return {
            "type": "ir.actions.act_window",
            "name": "Dépenses",
            "res_model": "caissecash.expense",
            "view_mode": "graph,pivot,list,form",
            "domain": [("state", "in", ("validated", "paid"))],
        }

    def action_view_invoice_graph(self):
        return {
            "type": "ir.actions.act_window",
            "name": "Factures clients",
            "res_model": "account.move",
            "view_mode": "graph,pivot,list,form",
            "domain": [("move_type", "=", "out_invoice"), ("state", "=", "posted")],
        }

    def action_view_value_graph(self):
        """Courbe de la valeur de l'entreprise dans le temps (résultat cumulé) :
        descend à chaque dépense, monte à chaque vente facturée."""
        self.env["caissecash.financial.snapshot"]._rebuild()
        return {
            "type": "ir.actions.act_window",
            "name": "Valeur de l'entreprise dans le temps",
            "res_model": "caissecash.financial.snapshot",
            "view_mode": "graph,list",
        }
