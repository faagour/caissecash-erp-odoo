from odoo.fields import Date
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestSubscriptionCron(TransactionCase):
    """Vérifie l'idempotence de la génération de facture d'abonnement.

    C'est la garantie demandée au cahier des charges : un double déclenchement
    du cron (ou un rejeu manuel) ne doit jamais produire deux factures pour
    la même période.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.product = cls.env["product.product"].create({
            "name": "Abonnement — Pack test",
            "type": "service",
        })
        cls.partner = cls.env["res.partner"].create({"name": "Client Test SAV"})
        cls.subscription = cls.env["caissecash.subscription"].create({
            "partner_id": cls.partner.id,
            "product_id": cls.product.id,
            "periodicity": "monthly",
            "amount": 500.0,
            "date_start": Date.today(),
            "next_invoice_date": Date.today(),
            "state": "actif",
        })

    def test_generate_invoice_once(self):
        self.assertEqual(len(self.subscription.invoice_log_ids), 0)
        self.subscription._generate_invoice_for_period()
        self.assertEqual(len(self.subscription.invoice_log_ids), 1)
        self.assertTrue(self.subscription.invoice_log_ids.move_id)
        # La prochaine échéance doit avoir avancé d'un mois.
        self.assertGreater(self.subscription.next_invoice_date, Date.today())

    def test_double_run_same_period_is_idempotent(self):
        first_period = self.subscription.next_invoice_date

        self.subscription._generate_invoice_for_period()
        self.assertEqual(len(self.subscription.invoice_log_ids), 1)
        first_move = self.subscription.invoice_log_ids.move_id

        # Simule un rejeu du cron pour la MÊME période (ex: cron relancé
        # avant que la date suivante ne soit prise en compte ailleurs).
        self.subscription.next_invoice_date = first_period
        self.subscription._generate_invoice_for_period()

        self.assertEqual(
            len(self.subscription.invoice_log_ids), 1,
            "Un rejeu sur la même période ne doit pas générer une deuxième facture.",
        )
        self.assertEqual(self.subscription.invoice_log_ids.move_id, first_move)

    def test_sql_constraint_blocks_duplicate_log(self):
        self.subscription._generate_invoice_for_period()
        log = self.subscription.invoice_log_ids
        with self.assertRaises(Exception):
            with self.env.cr.savepoint():
                self.env["caissecash.subscription.invoice.log"].create({
                    "subscription_id": self.subscription.id,
                    "period_key": log.period_key,
                    "move_id": log.move_id.id,
                })

    def test_cron_kill_switch(self):
        self.env["ir.config_parameter"].sudo().set_param(
            "caissecash_erp.subscription_cron_active", "False"
        )
        self.env["caissecash.subscription"]._cron_generate_subscription_invoices()
        self.assertEqual(
            len(self.subscription.invoice_log_ids), 0,
            "Le cron désactivé ne doit générer aucune facture.",
        )

    def test_cron_generates_for_due_subscription(self):
        self.env["ir.config_parameter"].sudo().set_param(
            "caissecash_erp.subscription_cron_active", "True"
        )
        self.env["caissecash.subscription"]._cron_generate_subscription_invoices()
        self.assertEqual(len(self.subscription.invoice_log_ids), 1)
