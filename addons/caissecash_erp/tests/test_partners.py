import base64
from datetime import timedelta

from odoo import fields
from odoo.exceptions import AccessError
from odoo.tests import Form, TransactionCase, tagged
from odoo.tools.safe_eval import safe_eval

ACTION_CONTEXT = {
    "default_caissecash_is_partner": True, "default_is_company": True,
    "default_caissecash_partner_state": "a_contacter",
}


@tagged("post_install", "-at_install")
class TestPartners(TransactionCase):
    """Partenaires (aménagement et matériel de cuisine) : fiche, statut,
    contrat, et séparation d'avec les clients."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        group = cls.env.ref
        cls.commercial = cls.env["res.users"].create({
            "name": "Commercial partenaires", "login": "commercial.partners",
            "group_ids": [(6, 0, [group("base.group_user").id, group("caissecash_erp.group_commercial").id])],
        })
        cls.technician = cls.env["res.users"].create({
            "name": "Technicien partenaires", "login": "technicien.partners",
            "group_ids": [(6, 0, [group("base.group_user").id, group("caissecash_erp.group_technicien").id])],
        })
        cls.Partner = cls.env["res.partner"].with_user(cls.commercial)
        cls.layout = group("caissecash_erp.partner_category_kitchen_layout")
        cls.equipment = group("caissecash_erp.partner_category_kitchen_equipment")
        cls.domain = safe_eval(cls.env.ref("caissecash_erp.action_caissecash_partners").domain)

    def form(self):
        return Form(self.Partner.with_context(ACTION_CONTEXT, default_user_id=self.commercial.id),
                    view="caissecash_erp.view_caissecash_partner_form")

    def partners(self):
        return self.env["res.partner"].search(self.domain)

    def test_new_partner_from_the_menu(self):
        form = self.form()
        form.name = "Cuisines Pro Maroc"
        form.caissecash_partner_category_ids.add(self.layout)
        form.caissecash_partner_category_ids.add(self.equipment)
        form.phone = "0522 11 22 33"
        form.city = "Casablanca"
        form.caissecash_partner_zone = "Casablanca, Rabat"
        partner = form.save()
        self.assertTrue(partner.caissecash_is_partner)
        self.assertEqual(partner.caissecash_partner_state, "a_contacter")
        self.assertEqual(partner.user_id, self.commercial)
        self.assertEqual(partner.caissecash_partner_category_ids, self.layout | self.equipment)
        self.assertIn(partner, self.partners())
        clients = self.env["res.partner"].search([("customer_rank", ">", 0)])
        self.assertNotIn(partner, clients, "un partenaire n'est pas un client")

    def test_contacts_of_a_partner_are_not_partners(self):
        form = self.form()
        form.name = "Froid Service"
        with form.child_ids.new() as contact:
            contact.name = "Karim, commercial"
            contact.phone = "0661000000"
        partner = form.save()
        self.assertTrue(partner.child_ids)
        self.assertFalse(partner.child_ids.caissecash_is_partner)
        self.assertNotIn(partner.child_ids, self.partners())

    def test_becoming_active_sets_the_start_date(self):
        partner = self.Partner.create({"name": "Inox Atlas", "caissecash_is_partner": True})
        self.assertEqual(partner.caissecash_partner_state, "a_contacter")
        partner.caissecash_partner_state = "discussion"
        self.assertFalse(partner.caissecash_partner_date_start)
        partner.caissecash_partner_state = "actif"
        self.assertEqual(partner.caissecash_partner_date_start, fields.Date.context_today(partner))
        started = self.Partner.create({
            "name": "Hottes Maroc", "caissecash_is_partner": True, "caissecash_partner_state": "actif",
            "caissecash_partner_date_start": "2025-01-15",
        })
        started.caissecash_partner_state = "inactif"
        started.caissecash_partner_state = "actif"
        self.assertEqual(str(started.caissecash_partner_date_start), "2025-01-15", "la date existante est gardée")

    def test_kanban_shows_every_status(self):
        self.Partner.create({"name": "Seul partenaire", "caissecash_is_partner": True})
        # Le kanban demande les colonnes vides (contexte read_group_expand).
        groups = self.env["res.partner"].with_context(read_group_expand=True).formatted_read_group(
            [("caissecash_is_partner", "=", True)], ["caissecash_partner_state"], ["__count"])
        self.assertEqual([g["caissecash_partner_state"] for g in groups],
                         ["a_contacter", "discussion", "actif", "inactif"])

    def test_contract_to_renew(self):
        today = fields.Date.context_today(self.env["res.partner"])
        partner = self.Partner.create({
            "name": "Mobilier Café", "caissecash_is_partner": True, "caissecash_partner_state": "actif",
            "caissecash_partner_date_end": today - timedelta(days=1),
            "caissecash_partner_contract": base64.b64encode(b"%PDF-1.4 contrat"),
            "caissecash_partner_contract_name": "contrat.pdf",
        })
        self.assertTrue(partner.caissecash_partner_contract_expired)
        partner.caissecash_partner_date_end = today + timedelta(days=365)
        self.assertFalse(partner.caissecash_partner_contract_expired)
        # Le contrat est lisible par le reste de l'équipe commerciale.
        colleague = self.env["res.users"].create({
            "name": "Autre commercial", "login": "commercial.partners.2",
            "group_ids": [(6, 0, self.commercial.group_ids.ids)],
        })
        self.assertTrue(partner.with_user(colleague).caissecash_partner_contract)

    def test_duplicate_alert_on_partner_form(self):
        self.env["res.partner"].create({"name": "Cuisines Atlas", "is_company": True, "phone": "+212 6 61 22 33 44"})
        form = self.form()
        form.name = "Atlas Cuisines"
        form.phone = "0661223344"
        self.assertEqual(form.caissecash_duplicate_message,
                         "Ce partenaire existe peut-être déjà : « Cuisines Atlas » (même téléphone)")

    def test_activities_rights(self):
        category = self.env["caissecash.partner.category"].with_user(self.commercial).create({"name": "Plomberie"})
        self.assertTrue(category)
        with self.assertRaises(AccessError):
            self.env["caissecash.partner.category"].with_user(self.technician).create({"name": "Électricité"})
        self.assertTrue(self.env["caissecash.partner.category"].with_user(self.technician).search([]))
