import logging

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models

_logger = logging.getLogger(__name__)

CRON_ACTIVE_PARAM = "caissecash_erp.subscription_cron_active"


class CaissecashSubscription(models.Model):
    """Abonnement logiciel CaisseCash (MVP).

    Odoo Community n'inclut pas le module Subscriptions (Enterprise) : ce
    modele fournit uniquement ce qui est demande au cahier des charges
    (suivi + preparation de facture recurrente), sans prelevement bancaire
    automatique.
    """

    _name = "caissecash.subscription"
    _description = "Abonnement CaisseCash"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "next_invoice_date"

    partner_id = fields.Many2one("res.partner", string="Client", required=True, tracking=True)
    establishment_id = fields.Many2one("caissecash.establishment", string="Établissement")

    product_id = fields.Many2one(
        "product.product", string="Formule (produit de facturation)", required=True
    )
    software_module_ids = fields.Many2many(
        "caissecash.software.module", string="Modules activés"
    )

    periodicity = fields.Selection(
        [("monthly", "Mensuelle"), ("yearly", "Annuelle")],
        default="monthly",
        required=True,
        string="Périodicité",
    )
    amount = fields.Monetary(string="Montant", required=True, currency_field="currency_id")
    currency_id = fields.Many2one(
        "res.currency", default=lambda self: self.env.company.currency_id
    )

    date_start = fields.Date(string="Date de début", required=True, default=fields.Date.context_today)
    next_invoice_date = fields.Date(string="Prochaine échéance", required=True, tracking=True)
    date_end = fields.Date(string="Date de fin (optionnelle)")

    state = fields.Selection(
        [
            ("essai", "Essai"),
            ("actif", "Actif"),
            ("suspendu", "Suspendu"),
            ("impaye", "Impayé"),
            ("resilie", "Résilié"),
            ("expire", "Expiré"),
        ],
        default="essai",
        tracking=True,
        string="Statut",
    )
    payment_mode = fields.Selection(
        [("virement", "Virement"), ("cheque", "Chèque"), ("especes", "Espèces"), ("autre", "Autre")],
        string="Mode de paiement",
    )

    invoice_log_ids = fields.One2many(
        "caissecash.subscription.invoice.log", "subscription_id", string="Historique de facturation"
    )
    invoice_ids = fields.Many2many(
        "account.move", compute="_compute_invoice_ids", string="Factures générées"
    )

    @api.depends("invoice_log_ids.move_id")
    def _compute_invoice_ids(self):
        for rec in self:
            rec.invoice_ids = rec.invoice_log_ids.move_id

    def action_view_invoices(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "Factures",
            "res_model": "account.move",
            "view_mode": "list,form",
            "domain": [("id", "in", self.invoice_ids.ids)],
        }

    def _next_period_date(self, from_date):
        self.ensure_one()
        if self.periodicity == "monthly":
            return from_date + relativedelta(months=1)
        return from_date + relativedelta(years=1)

    def _period_key(self, a_date):
        self.ensure_one()
        return a_date.strftime("%Y-%m") if self.periodicity == "monthly" else a_date.strftime("%Y")

    def _prepare_invoice_vals(self, period_key):
        self.ensure_one()
        return {
            "move_type": "out_invoice",
            "partner_id": self.partner_id.id,
            "invoice_origin": f"Abonnement {self.id} - {period_key}",
            "invoice_line_ids": [
                (0, 0, {
                    "product_id": self.product_id.id,
                    "name": f"{self.product_id.display_name} — période {period_key}",
                    "quantity": 1,
                    "price_unit": self.amount,
                })
            ],
        }

    def _generate_invoice_for_period(self):
        """Prepare (draft) une facture pour la periode courante, de facon idempotente.

        Protection anti-doublon : verification applicative (recherche du log
        existant) + contrainte SQL unique (subscription_id, period_key) sur
        caissecash.subscription.invoice.log qui ferait echouer une double
        insertion concurrente.
        """
        self.ensure_one()
        period_key = self._period_key(self.next_invoice_date)

        existing = self.env["caissecash.subscription.invoice.log"].search([
            ("subscription_id", "=", self.id),
            ("period_key", "=", period_key),
        ], limit=1)
        if existing:
            _logger.info(
                "Abonnement %s : facture déjà générée pour la période %s (log #%s), ignoré.",
                self.id, period_key, existing.id,
            )
            return existing.move_id

        move = self.env["account.move"].create(self._prepare_invoice_vals(period_key))
        self.env["caissecash.subscription.invoice.log"].create({
            "subscription_id": self.id,
            "period_key": period_key,
            "move_id": move.id,
        })
        _logger.info(
            "Abonnement %s : facture brouillon %s générée pour la période %s.",
            self.id, move.id, period_key,
        )
        self.next_invoice_date = self._next_period_date(self.next_invoice_date)
        return move

    @api.model
    def _cron_generate_subscription_invoices(self):
        if self.env["ir.config_parameter"].sudo().get_param(CRON_ACTIVE_PARAM, "True") != "True":
            _logger.info("Cron de facturation des abonnements CaisseCash désactivé (%s=False).", CRON_ACTIVE_PARAM)
            return

        today = fields.Date.context_today(self)
        subscriptions = self.search([
            ("state", "=", "actif"),
            ("next_invoice_date", "<=", today),
            "|", ("date_end", "=", False), ("date_end", ">=", today),
        ])
        _logger.info("Cron abonnements CaisseCash : %s abonnement(s) à traiter.", len(subscriptions))
        for sub in subscriptions:
            try:
                with self.env.cr.savepoint():
                    sub._generate_invoice_for_period()
            except Exception:
                _logger.exception(
                    "Échec de génération de facture pour l'abonnement %s (période visée %s).",
                    sub.id, sub.next_invoice_date,
                )


class CaissecashSubscriptionInvoiceLog(models.Model):
    """Journal des factures generees par le cron d'abonnement (garde-fou anti-doublon)."""

    _name = "caissecash.subscription.invoice.log"
    _description = "Journal de facturation d'abonnement CaisseCash"
    _order = "create_date desc"

    subscription_id = fields.Many2one(
        "caissecash.subscription", required=True, ondelete="cascade", index=True
    )
    period_key = fields.Char(required=True, help="Ex: 2026-08 (mensuel) ou 2026 (annuel)")
    move_id = fields.Many2one("account.move", string="Facture", required=True)

    _subscription_period_uniq = models.Constraint(
        "UNIQUE(subscription_id, period_key)",
        "Une facture a déjà été générée pour cet abonnement sur cette période.",
    )
