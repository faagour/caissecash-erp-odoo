from odoo.tests import Form, TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestCustomers(TransactionCase):
    """Fiche client simplifiée : alerte doublon et compteurs."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Partner = cls.env["res.partner"]
        cls.atlas = cls.Partner.create({
            "name": "Café Atlas", "is_company": True, "phone": "+212 6 12-34-56-78", "ice": "001234567000089",
        })

    def form(self):
        return Form(self.Partner.with_context(default_is_company=True, default_customer_rank=1),
                    view="caissecash_erp.view_caissecash_customer_form")

    def test_same_phone_in_another_format(self):
        form = self.form()
        form.name = "Snack Zahra"
        form.phone = "0612345678"
        self.assertIn("« Café Atlas » (même téléphone)", form.caissecash_duplicate_message)

    def test_same_whatsapp_ice_or_name(self):
        form = self.form()
        form.name = "Autre"
        form.whatsapp = "06 12 34 56 78"
        self.assertIn("« Café Atlas » (même téléphone)", form.caissecash_duplicate_message)
        form = self.form()
        form.name = "Société Nouvelle"
        form.ice = "001 234 567 000 089"
        self.assertIn("même ICE", form.caissecash_duplicate_message)
        form = self.form()
        form.name = "  café atlas "
        self.assertIn("« Café Atlas » (même nom)", form.caissecash_duplicate_message)

    def test_no_warning_for_itself_or_its_contacts(self):
        self.assertFalse(self.atlas.caissecash_duplicate_ids)
        contact = self.Partner.create({"name": "Gérant", "parent_id": self.atlas.id, "phone": "0612345678"})
        self.assertFalse(contact.caissecash_duplicate_ids)
        form = self.form()
        form.name = "Boulangerie Nour"
        form.phone = "0522000000"
        self.assertFalse(form.caissecash_duplicate_message)

    def test_counts(self):
        self.env["caissecash.establishment"].create({"name": "Atlas centre", "partner_id": self.atlas.id})
        self.atlas.invalidate_recordset()
        self.assertEqual(self.atlas.caissecash_establishment_count, 1)
        action = self.atlas.action_caissecash_establishments()
        self.assertEqual(action["domain"], [("partner_id", "=", self.atlas.id)])
