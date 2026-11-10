from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestConfidentiality(TransactionCase):
    """Vérifie le principe du moindre privilège (cahier des charges §22/§25) :
    un technicien ne doit pas pouvoir accéder aux associés, dépenses, ni aux
    installations/tickets SAV qui ne lui sont pas assignés."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        group_technicien = cls.env.ref("caissecash_erp.group_technicien")
        cls.technician_user = cls.env["res.users"].create({
            "name": "Technicien Test",
            "login": "technicien_test@example.com",
            "group_ids": [(6, 0, [group_technicien.id])],
        })
        cls.other_technician_user = cls.env["res.users"].create({
            "name": "Autre Technicien",
            "login": "autre_technicien_test@example.com",
            "group_ids": [(6, 0, [group_technicien.id])],
        })
        cls.partner = cls.env["res.partner"].create({"name": "Client Confidentialité"})
        cls.founder = cls.env["caissecash.founder"].create({"name": "Associé Confidentiel"})

    def test_technician_cannot_read_founders(self):
        with self.assertRaises(AccessError):
            self.env["caissecash.founder"].with_user(self.technician_user).search([])

    def test_technician_cannot_read_expenses(self):
        with self.assertRaises(AccessError):
            self.env["caissecash.expense"].with_user(self.technician_user).search([])

    def test_technician_only_sees_own_installations(self):
        own = self.env["caissecash.installation"].create({
            "partner_id": self.partner.id,
            "establishment_id": self.env["caissecash.establishment"].create({
                "name": "Étab. Test", "partner_id": self.partner.id,
            }).id,
            "technician_id": self.technician_user.id,
        })
        other = own.copy({"technician_id": self.other_technician_user.id})

        visible = self.env["caissecash.installation"].with_user(self.technician_user).search([])
        self.assertIn(own.id, visible.ids)
        self.assertNotIn(other.id, visible.ids)

    def test_direction_sees_every_installation_and_ticket(self):
        """La direction hérite du rôle technicien : elle doit quand même voir
        les fiches assignées à d'autres ou à personne."""
        director = self.env["res.users"].create({
            "name": "Direction Test",
            "login": "direction_test@example.com",
            "group_ids": [(6, 0, [self.env.ref("caissecash_erp.group_direction").id])],
        })
        establishment = self.env["caissecash.establishment"].create({
            "name": "Étab. Direction", "partner_id": self.partner.id,
        })
        installations = self.env["caissecash.installation"].create([
            {"partner_id": self.partner.id, "establishment_id": establishment.id,
             "technician_id": self.technician_user.id},
            {"partner_id": self.partner.id, "establishment_id": establishment.id},
        ])
        tickets = self.env["caissecash.sav.ticket"].create([
            {"partner_id": self.partner.id, "description": "Assigné",
             "technician_id": self.technician_user.id},
            {"partner_id": self.partner.id, "description": "Pas encore assigné"},
        ])
        seen = self.env["caissecash.installation"].with_user(director).search([])
        self.assertTrue(set(installations.ids) <= set(seen.ids))
        seen = self.env["caissecash.sav.ticket"].with_user(director).search([])
        self.assertTrue(set(tickets.ids) <= set(seen.ids))
        # Le technicien, lui, reste limité à ses tickets.
        seen = self.env["caissecash.sav.ticket"].with_user(self.technician_user).search([])
        self.assertIn(tickets[0].id, seen.ids)
        self.assertNotIn(tickets[1].id, seen.ids)
