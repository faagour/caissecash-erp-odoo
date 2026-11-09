from collections import defaultdict

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models

PAID_STATES = ("paid", "in_payment")


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

    @api.model
    def get_dashboard_data(self, period="all"):
        """Données de la page « Tableau de bord » (action client).

        La période (all / year / month) s'applique aux indicateurs, aux
        catégories et aux listes ; les deux courbes couvrent toujours les
        12 derniers mois.
        """
        self.check_access("read")
        Move = self.env["account.move"]
        Expense = self.env["caissecash.expense"]
        Purchase = self.env["purchase.order"]
        currency = self.env.company.currency_id

        today = fields.Date.context_today(self)
        start = {"year": today.replace(month=1, day=1), "month": today.replace(day=1)}.get(period)

        invoice_domain = [("move_type", "=", "out_invoice"), ("state", "=", "posted")]
        expense_domain = [("state", "in", ("validated", "paid"))]
        purchase_domain = [("state", "in", ("purchase", "done"))]
        if start:
            invoice_domain += [("invoice_date", ">=", start)]
            expense_domain += [("date", ">=", start)]
            purchase_domain += [("date_order", ">=", start)]

        invoices = Move.search(invoice_domain)
        paid = invoices.filtered(lambda m: m.payment_state in PAID_STATES)
        unpaid = invoices.filtered(lambda m: m.payment_state not in (*PAID_STATES, "reversed"))
        expenses = Expense.search(expense_domain, order="date desc, id desc")
        invoiced = sum(invoices.mapped("amount_total"))
        spent = sum(expenses.mapped("amount_total"))

        by_category = defaultdict(float)
        for expense in expenses:
            by_category[expense.category_id.name or "Sans catégorie"] += expense.amount_total
        categories = sorted(by_category.items(), key=lambda item: -item[1])
        if len(categories) > 6:
            categories = categories[:5] + [("Autres", sum(amount for _, amount in categories[5:]))]

        # 12 derniers mois : montants du mois, et résultat cumulé (depuis le début) en fin de mois.
        all_invoices = Move.search([("move_type", "=", "out_invoice"), ("state", "=", "posted")])
        all_expenses = Expense.search([("state", "in", ("validated", "paid"))])
        monthly = []
        for offset in range(11, -1, -1):
            month_start = today.replace(day=1) - relativedelta(months=offset)
            month_end = month_start + relativedelta(months=1)

            def total(records, date_field, lower=None):
                return sum(
                    r.amount_total for r in records
                    if r[date_field] and r[date_field] < month_end and (lower is None or r[date_field] >= lower)
                )

            monthly.append({
                "month": month_start.isoformat(),
                "invoiced": total(all_invoices, "invoice_date", month_start),
                "expenses": total(all_expenses, "date", month_start),
                "value": total(all_invoices, "invoice_date") - total(all_expenses, "date"),
            })

        founders = self.env["caissecash.founder"].search([("state", "=", "actif")])
        capital_total = sum(founders.mapped("total_capital"))

        # Objectifs de l'année en cours, quelle que soit la période choisie.
        Objective = self.env["caissecash.objective"]
        objective_cards = Objective.search([("year", "=", today.year)])._caissecash_card_data()

        return {
            "currency": {"symbol": currency.symbol, "position": currency.position},
            "objectives": {
                "year": today.year,
                "items": objective_cards,
                "counts": Objective._caissecash_summary(objective_cards),
                "can_plan": self.env["caissecash.objective.plan"].has_access("create"),
            },
            "kpis": {
                "invoiced": invoiced,
                "invoice_count": len(invoices),
                "paid": sum(paid.mapped("amount_total")),
                "unpaid": sum(unpaid.mapped("amount_residual")),
                "unpaid_count": len(unpaid),
                "expenses": spent,
                "expense_count": len(expenses),
                "purchases": sum(Purchase.search(purchase_domain).mapped("amount_total")),
                "result": invoiced - spent,
            },
            "categories": [{"name": name, "amount": amount} for name, amount in categories],
            "monthly": monthly,
            "founders": [
                {
                    "id": f.id,
                    "name": f.name,
                    "capital": f.total_capital,
                    "share": capital_total and f.total_capital / capital_total * 100,
                }
                for f in founders.sorted(lambda f: -f.total_capital)
            ],
            "capital_total": capital_total,
            "latest_expenses": [
                {
                    "id": e.id,
                    "date": e.date and e.date.isoformat(),
                    "label": e.description or e.name,
                    "category": e.category_id.name or "",
                    "founder": e.founder_id.name or "",
                    "amount": e.amount_total,
                }
                for e in expenses[:6]
            ],
            "unpaid_invoices": [
                {
                    "id": m.id,
                    "name": m.name,
                    "partner": m.partner_id.display_name or "",
                    "due": m.invoice_date_due and m.invoice_date_due.isoformat(),
                    "overdue": bool(m.invoice_date_due and m.invoice_date_due < today),
                    "amount": m.amount_residual,
                }
                for m in unpaid.sorted(lambda m: -m.amount_residual)[:6]
            ],
        }

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
