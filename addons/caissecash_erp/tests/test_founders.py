from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestFounderBalance(TransactionCase):
    """Vérifie le calcul des soldes indicatifs et la protection contre la
    suppression d'un mouvement validé (cahier des charges §8/§25)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.founder = cls.env["caissecash.founder"].create({"name": "Associé Test"})

    def _create_movement(self, movement_type, amount, state="validated"):
        move = self.env["caissecash.founder.movement"].create({
            "founder_id": self.founder.id,
            "movement_type": movement_type,
            "amount": amount,
        })
        if state == "validated":
            move.action_validate()
        return move

    def test_totals_and_balance(self):
        self._create_movement("capital_contribution", 10000)
        self._create_movement("current_account_advance", 2000)
        self._create_movement("personal_expense", 500)
        self._create_movement("reimbursement", 300)
        self._create_movement("withdrawal", 200)
        self._create_movement("correction", 100)
        # Un mouvement en brouillon ne doit compter dans aucun total.
        self._create_movement("capital_contribution", 5000, state="draft")

        self.assertEqual(self.founder.total_capital, 10000)
        self.assertEqual(self.founder.total_advance, 2000)
        self.assertEqual(self.founder.total_personal_expense, 500)
        self.assertEqual(self.founder.total_reimbursed, 300)
        self.assertEqual(self.founder.total_withdrawal, 200)
        # (2000 avance + 500 dépense perso + 100 correction) - (300 remb. + 200 retrait)
        self.assertEqual(self.founder.balance_indicative, 2100)

    def test_validated_movement_cannot_be_deleted(self):
        move = self._create_movement("capital_contribution", 1000)
        with self.assertRaises(UserError):
            move.unlink()

    def test_cancel_excludes_from_totals(self):
        move = self._create_movement("current_account_advance", 1000)
        self.assertEqual(self.founder.total_advance, 1000)
        move.action_cancel()
        self.assertEqual(move.state, "cancelled")
        self.assertEqual(self.founder.total_advance, 0)

    def test_draft_movement_can_be_deleted(self):
        move = self._create_movement("capital_contribution", 1000, state="draft")
        move.unlink()
        self.assertFalse(move.exists())
