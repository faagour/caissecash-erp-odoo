from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestHome(TransactionCase):
    """Mon espace : parcours et phrases réglables par l'administrateur, guide
    « Bien démarrer » selon le rôle, raccourcis « Créer » selon les droits."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        group_user = cls.env.ref("base.group_user")

        def user(login, *groups):
            return cls.env["res.users"].create({
                "name": login, "login": login,
                "group_ids": [(6, 0, [group_user.id, *(cls.env.ref(g).id for g in groups)])],
            })

        cls.commercial = user("commercial.espace", "caissecash_erp.group_commercial")
        cls.technician = user("technicien.espace", "caissecash_erp.group_technicien")
        cls.director = user("direction.espace", "caissecash_erp.group_direction")
        cls.employee = user("equipe.espace")

    def home(self, user):
        return self.env["caissecash.espace"].with_user(user).get_home_data()

    def test_journey_steps_follow_settings(self):
        step = self.env.ref("caissecash_espace.journey_sav")
        labels = [s["label"] for s in self.home(self.director)["journey"]]
        self.assertIn("SAV", labels)
        step.write({"name": "Après-vente", "sequence": 1})
        self.assertEqual(self.home(self.director)["journey"][0]["label"], "Après-vente")
        step.visible = False
        self.assertNotIn("Après-vente", [s["label"] for s in self.home(self.director)["journey"]])

    def test_quotes_come_from_settings(self):
        params = self.env["ir.config_parameter"].sudo()
        params.set_param("caissecash_espace.quotes", "Première phrase\n\n  Deuxième phrase  \n")
        self.assertEqual(self.home(self.commercial)["quotes"], ["Première phrase", "Deuxième phrase"])
        params.set_param("caissecash_espace.quotes", "")
        self.assertTrue(self.home(self.commercial)["quotes"])

    def test_settings_are_saved(self):
        settings = self.env["res.config.settings"].create({
            "caissecash_weekly_goal": 25,
            "caissecash_objective_at_risk_gap": 10,
            "caissecash_objective_late_gap": 30,
        })
        settings.execute()
        self.assertEqual(self.home(self.commercial)["weekly_goal"], 25)
        self.assertEqual(self.env["caissecash.objective"]._status_gaps(), (10, 30))

    def test_guide_depends_on_role(self):
        self.assertEqual(self.home(self.director)["guide"]["role"], "Direction")
        self.assertEqual(self.home(self.commercial)["guide"]["role"], "Commercial")
        self.assertEqual(self.home(self.technician)["guide"]["role"], "Technicien")
        self.assertEqual(self.home(self.employee)["guide"]["role"], "Équipe")
        for user in (self.director, self.commercial, self.technician, self.employee):
            self.assertTrue(self.home(user)["guide"]["steps"], user.login)

    def test_guide_can_be_hidden(self):
        espace = self.env["caissecash.espace"].with_user(self.commercial)
        espace.set_guide_hidden(True)
        self.assertTrue(self.home(self.commercial)["guide"]["hidden"])
        espace.set_guide_hidden(False)
        self.assertFalse(self.home(self.commercial)["guide"]["hidden"])

    def test_create_shortcuts_follow_rights(self):
        technician = {s["key"] for s in self.home(self.technician)["create"]}
        director = {s["key"] for s in self.home(self.director)["create"]}
        self.assertNotIn("expense", technician)
        self.assertNotIn("installation", technician)
        self.assertIn("sav", technician)
        self.assertTrue({"customer", "partner", "stock_entry", "stock_exit"}.isdisjoint(technician))
        self.assertTrue({"prospect", "customer", "partner", "installation", "sav", "stock_entry", "stock_exit", "expense"} <= director)
        commercial = {s["key"] for s in self.home(self.commercial)["create"]}
        self.assertTrue({"customer", "partner"} <= commercial)
        self.assertNotIn("stock_entry", commercial)
        stock = self.env["res.users"].create({
            "name": "stock.espace", "login": "stock.espace",
            "group_ids": [(6, 0, [self.env.ref("base.group_user").id, self.env.ref("caissecash_erp.group_stock").id])],
        })
        shortcuts = {s["key"]: s for s in self.home(stock)["create"]}
        self.assertTrue({"stock_entry", "stock_exit"} <= set(shortcuts))
        self.assertEqual(shortcuts["stock_entry"]["action"], "caissecash_erp.action_caissecash_stock_entry")
        self.assertEqual(self.home(stock)["guide"]["role"], "Stock")

    def test_home_without_caissecash_role(self):
        data = self.home(self.employee)
        self.assertEqual(data["objectives"]["items"], [])
        self.assertEqual(data["create"], [])
