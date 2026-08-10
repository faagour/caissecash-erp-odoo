from odoo import api, fields, models
from odoo.exceptions import UserError


class CaissecashFounder(models.Model):
    """Fiche associé/cofondateur.

    Suivi purement indicatif (cahier des charges §8) : aucun lien avec la
    comptabilité officielle, aucun apport n'est traité comme du chiffre
    d'affaires. Les vraies écritures comptables restent du ressort du
    comptable marocain de l'entreprise, sur la base des exports de ce module.
    """

    _name = "caissecash.founder"
    _description = "Associé / Cofondateur CaisseCash"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "name"

    name = fields.Char(string="Nom complet", required=True, tracking=True)
    email = fields.Char(string="E-mail")
    phone = fields.Char(string="Téléphone")
    whatsapp = fields.Char(string="WhatsApp")

    role = fields.Char(string="Rôle dans l'entreprise")
    date_start = fields.Date(string="Date d'entrée")
    participation_percent = fields.Float(string="Participation (%)")

    state = fields.Selection(
        [("actif", "Actif"), ("inactif", "Inactif"), ("sorti", "Sorti")],
        default="actif",
        string="Statut",
        tracking=True,
    )
    notes = fields.Text(string="Notes")

    currency_id = fields.Many2one(
        "res.currency", default=lambda self: self.env.company.currency_id
    )
    movement_ids = fields.One2many(
        "caissecash.founder.movement", "founder_id", string="Mouvements"
    )

    total_capital = fields.Monetary(compute="_compute_totals", string="Total apports au capital")
    total_advance = fields.Monetary(compute="_compute_totals", string="Total avances")
    total_personal_expense = fields.Monetary(compute="_compute_totals", string="Total dépenses personnelles")
    total_reimbursed = fields.Monetary(compute="_compute_totals", string="Total remboursé")
    total_withdrawal = fields.Monetary(compute="_compute_totals", string="Total retiré")
    balance_indicative = fields.Monetary(
        compute="_compute_totals",
        string="Solde indicatif restant dû",
        help="(Avances + dépenses personnelles + corrections) − (remboursements + retraits). "
             "Indicatif uniquement, ne remplace pas la comptabilité officielle.",
    )

    @api.depends(
        "movement_ids.amount", "movement_ids.movement_type", "movement_ids.state"
    )
    def _compute_totals(self):
        for founder in self:
            validated = founder.movement_ids.filtered(lambda m: m.state == "validated")
            by_type = {
                mtype: sum(validated.filtered(lambda m, t=mtype: m.movement_type == t).mapped("amount"))
                for mtype in (
                    "capital_contribution", "current_account_advance",
                    "personal_expense", "reimbursement", "withdrawal", "correction",
                )
            }
            founder.total_capital = by_type["capital_contribution"]
            founder.total_advance = by_type["current_account_advance"]
            founder.total_personal_expense = by_type["personal_expense"]
            founder.total_reimbursed = by_type["reimbursement"]
            founder.total_withdrawal = by_type["withdrawal"]
            founder.balance_indicative = (
                by_type["current_account_advance"]
                + by_type["personal_expense"]
                + by_type["correction"]
                - by_type["reimbursement"]
                - by_type["withdrawal"]
            )


class CaissecashFounderMovement(models.Model):
    """Mouvement financier lié à un associé (apport, avance, dépense
    personnelle, remboursement, retrait, correction).

    Une fois validé, un mouvement n'est plus supprimable (cf. unlink override) :
    seule une annulation tracée (changement de statut) est possible, jamais
    une suppression physique de l'historique.
    """

    _name = "caissecash.founder.movement"
    _description = "Mouvement associé CaisseCash"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "date desc, id desc"

    name = fields.Char(
        string="Référence", required=True, copy=False, readonly=True,
        default=lambda self: self.env["ir.sequence"].next_by_code("caissecash.founder.movement") or "Nouveau",
    )
    founder_id = fields.Many2one(
        "caissecash.founder", string="Associé", required=True, tracking=True
    )
    date = fields.Date(string="Date", required=True, default=fields.Date.context_today)
    amount = fields.Monetary(string="Montant", required=True, currency_field="currency_id")
    currency_id = fields.Many2one(
        "res.currency", default=lambda self: self.env.company.currency_id
    )

    movement_type = fields.Selection(
        [
            ("capital_contribution", "Apport au capital"),
            ("current_account_advance", "Avance en compte courant d'associé"),
            ("personal_expense", "Dépense payée personnellement pour l'entreprise"),
            ("reimbursement", "Remboursement à l'associé"),
            ("withdrawal", "Retrait autorisé"),
            ("correction", "Correction"),
        ],
        string="Type de mouvement",
        required=True,
        tracking=True,
    )
    payment_mode = fields.Selection(
        [("virement", "Virement"), ("cheque", "Chèque"), ("especes", "Espèces"), ("autre", "Autre")],
        string="Moyen de paiement",
    )
    account_reference = fields.Char(
        string="Compte bancaire / caisse concerné",
        help="Référence libre en attendant un module trésorerie dédié.",
    )
    description = fields.Text(string="Description")

    state = fields.Selection(
        [
            ("draft", "Brouillon"),
            ("to_verify", "À vérifier"),
            ("validated", "Validé"),
            ("cancelled", "Annulé"),
        ],
        default="draft",
        string="Statut",
        tracking=True,
    )
    validated_by = fields.Many2one("res.users", string="Validé par", readonly=True, copy=False)
    validation_date = fields.Datetime(string="Date de validation", readonly=True, copy=False)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "Nouveau") == "Nouveau":
                vals["name"] = self.env["ir.sequence"].next_by_code("caissecash.founder.movement") or "Nouveau"
        return super().create(vals_list)

    def action_submit_for_verification(self):
        self.filtered(lambda m: m.state == "draft").write({"state": "to_verify"})

    def action_validate(self):
        self.write({
            "state": "validated",
            "validated_by": self.env.user.id,
            "validation_date": fields.Datetime.now(),
        })

    def action_cancel(self):
        """Annulation tracée : le mouvement reste dans l'historique, il ne
        compte simplement plus dans les totaux (cf. _compute_totals)."""
        self.write({"state": "cancelled"})

    def action_reset_to_draft(self):
        self.filtered(lambda m: m.state != "validated").write({"state": "draft"})

    def unlink(self):
        if any(m.state == "validated" for m in self):
            raise UserError(
                "Un mouvement validé ne peut pas être supprimé. "
                "Utilisez l'action \"Annuler\" pour tracer l'annulation."
            )
        return super().unlink()
