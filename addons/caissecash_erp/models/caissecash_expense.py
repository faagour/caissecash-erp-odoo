from odoo import api, fields, models
from odoo.exceptions import UserError


class CaissecashExpenseCategory(models.Model):
    """Catégorie de dépense, librement modifiable (cahier des charges §12).

    Les catégories usuelles (loyer, électricité, salaires...) sont fournies
    en données de référence ; l'utilisateur peut en ajouter/renommer/désactiver.
    """

    _name = "caissecash.expense.category"
    _description = "Catégorie de dépense CaisseCash"
    _order = "sequence, name"

    name = fields.Char(required=True)
    expense_group = fields.Selection(
        [
            ("fixe", "Charges fixes"),
            ("personnel", "Personnel"),
            ("variable", "Charges variables"),
        ],
        string="Groupe",
        required=True,
    )
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)


class CaissecashExpense(models.Model):
    _name = "caissecash.expense"
    _description = "Dépense CaisseCash"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "date desc, id desc"

    name = fields.Char(
        string="Référence", required=True, copy=False, readonly=True,
        default=lambda self: self.env["ir.sequence"].next_by_code("caissecash.expense") or "Nouveau",
    )
    date = fields.Date(string="Date", required=True, default=fields.Date.context_today)
    category_id = fields.Many2one("caissecash.expense.category", string="Catégorie", required=True)

    partner_id = fields.Many2one("res.partner", string="Fournisseur / bénéficiaire")
    description = fields.Text(string="Description")

    currency_id = fields.Many2one(
        "res.currency", default=lambda self: self.env.company.currency_id
    )
    amount_untaxed = fields.Monetary(string="Montant HT", currency_field="currency_id")
    amount_tax = fields.Monetary(string="TVA", currency_field="currency_id")
    amount_total = fields.Monetary(
        string="Montant TTC", currency_field="currency_id",
        compute="_compute_amount_total", store=True, readonly=False,
    )

    payment_mode = fields.Selection(
        [("virement", "Virement"), ("cheque", "Chèque"), ("especes", "Espèces"), ("autre", "Autre")],
        string="Moyen de paiement",
    )
    account_reference = fields.Char(string="Compte / caisse")
    paid_by_user_id = fields.Many2one("res.users", string="Personne ayant payé")
    founder_id = fields.Many2one(
        "caissecash.founder", string="Associé concerné (si paiement personnel)"
    )

    partner_related_id = fields.Many2one("res.partner", string="Client / projet concerné")

    is_recurring = fields.Boolean(string="Dépense récurrente")
    recurring_periodicity = fields.Selection(
        [("monthly", "Mensuelle"), ("quarterly", "Trimestrielle"), ("yearly", "Annuelle")],
        string="Périodicité",
    )
    next_reminder_date = fields.Date(string="Prochain rappel")

    notes = fields.Text(string="Notes")

    state = fields.Selection(
        [
            ("draft", "Brouillon"),
            ("to_validate", "À valider"),
            ("validated", "Validée"),
            ("paid", "Payée"),
            ("cancelled", "Annulée"),
        ],
        default="draft",
        string="Statut",
        tracking=True,
    )

    @api.depends("amount_untaxed", "amount_tax")
    def _compute_amount_total(self):
        for rec in self:
            if not rec.amount_total or (rec.amount_untaxed or rec.amount_tax):
                rec.amount_total = (rec.amount_untaxed or 0.0) + (rec.amount_tax or 0.0)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "Nouveau") == "Nouveau":
                vals["name"] = self.env["ir.sequence"].next_by_code("caissecash.expense") or "Nouveau"
        return super().create(vals_list)

    def action_submit(self):
        self.filtered(lambda e: e.state == "draft").write({"state": "to_validate"})

    def action_validate(self):
        self.write({"state": "validated"})

    def action_mark_paid(self):
        self.write({"state": "paid"})

    def action_cancel(self):
        self.write({"state": "cancelled"})

    def action_reset_to_draft(self):
        self.filtered(lambda e: e.state != "paid").write({"state": "draft"})

    def unlink(self):
        if any(e.state in ("validated", "paid") for e in self):
            raise UserError(
                "Une dépense validée ou payée ne peut pas être supprimée. "
                "Utilisez l'action \"Annuler\" pour tracer l'annulation."
            )
        return super().unlink()
