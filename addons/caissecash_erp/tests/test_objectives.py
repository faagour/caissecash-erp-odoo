from datetime import date

from odoo.exceptions import AccessError, ValidationError
from odoo.tests import Form, TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestObjectives(TransactionCase):
    """Objectifs de l'année : répartition par trimestre, état par rapport à
    l'attendu, cibles réservées à la direction, assistant de saisie."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Objective = cls.env["caissecash.objective"]
        group_user = cls.env.ref("base.group_user")

        def user(login, *groups):
            return cls.env["res.users"].create({
                "name": login, "login": login,
                "group_ids": [(6, 0, [group_user.id, *(cls.env.ref(g).id for g in groups)])],
            })

        cls.director = user("direction.objectifs", "caissecash_erp.group_direction")
        cls.commercial = user("commercial.objectifs", "caissecash_erp.group_commercial")
        cls.other_commercial = user("commercial2.objectifs", "caissecash_erp.group_commercial")
        cls.finance = user("finance.objectifs", "caissecash_erp.group_comptabilite")
        cls.year = date.today().year

    def objective(self, **values):
        return self.Objective.create({"name": "Objectif test", "year": self.year, **values})

    # --- Répartition -------------------------------------------------------------

    def test_even_split_counts_stay_whole(self):
        objective = self.objective(indicator="installations", target=10)
        self.assertEqual(objective._quarters(), [3, 3, 2, 2])

    def test_even_split_amounts_keep_the_total(self):
        objective = self.objective(indicator="invoiced", target=100000.01)
        self.assertAlmostEqual(sum(objective._quarters()), 100000.01, places=2)

    def test_level_split_goes_from_start_to_target(self):
        objective = self.objective(tracking_mode="manual", measure="level", manual_start_value=4.2, target=4.6)
        self.assertEqual(objective._quarters(), [4.3, 4.4, 4.5, 4.6])

    def test_level_indicator_is_detected_at_creation(self):
        self.assertEqual(self.objective(indicator="subscriptions", target=6).measure, "level")

    def test_new_target_rescales_custom_quarters(self):
        objective = self.objective(indicator="installations", target=12,
                                   target_q1=3, target_q2=3, target_q3=2, target_q4=4)
        objective.target = 24
        self.assertEqual(objective._quarters(), [6, 6, 4, 8])

    def test_quarters_must_add_up(self):
        objective = self.objective(indicator="installations", target=8)
        with self.assertRaises(ValidationError):
            objective.target_q1 = 5

    def test_form_editing_one_quarter_keeps_the_others(self):
        form = Form(self.Objective)
        form.name = "Installations"
        form.indicator = "installations"
        form.target = 10
        form.target_q4 = 4
        self.assertEqual(form.target, 12)
        self.assertEqual([form.target_q1, form.target_q2, form.target_q3], [3, 3, 2])
        form.save()

    # --- État ----------------------------------------------------------------------

    def test_status_follows_expected_progress(self):
        objective = self.objective(tracking_mode="manual", target=100, manual_value=40, year=2030)
        mid_year = date(2030, 6, 30)  # attendu : 50
        self.assertEqual(objective._progress_values(mid_year)["status"], "at_risk")
        self.assertEqual(objective._progress_values(mid_year, gaps=(15, 30))["status"], "on_track")
        objective.manual_value = 20
        self.assertEqual(objective._progress_values(mid_year)["status"], "late")
        objective.manual_value = 100
        self.assertEqual(objective._progress_values(mid_year)["status"], "done")

    def test_status_before_and_after_the_year(self):
        objective = self.objective(tracking_mode="manual", target=10, manual_value=3, year=2030)
        self.assertEqual(objective._progress_values(date(2029, 12, 1))["status"], "upcoming")
        self.assertEqual(objective._progress_values(date(2031, 1, 5))["status"], "missed")

    def test_gaps_come_from_settings(self):
        params = self.env["ir.config_parameter"].sudo()
        params.set_param("caissecash_erp.objective_at_risk_gap", "2")
        params.set_param("caissecash_erp.objective_late_gap", "40")
        self.assertEqual(self.Objective._status_gaps(), (2, 40))

    def test_units_in_french(self):
        objective = self.objective(tracking_mode="manual", unit="recrutements", target=2, manual_value=1)
        self.assertEqual(objective.progress_label.replace(" ", " ").replace("\xa0", " "), "1 recrutement / 2 recrutements")

    # --- Droits --------------------------------------------------------------------

    def test_responsible_updates_progress_but_not_targets(self):
        objective = self.objective(tracking_mode="manual", target=10, user_id=self.commercial.id)
        mine = objective.with_user(self.commercial)
        mine.manual_value = 4
        mine.description = "<p>Relancer les prospects</p>"
        self.assertEqual(objective.manual_value, 4)
        for values in ({"target": 20}, {"target_q1": 1}, {"name": "Autre"}, {"user_id": self.other_commercial.id}):
            with self.assertRaises(AccessError):
                mine.write(values)
        self.assertFalse(mine.can_manage)

    def test_direction_changes_targets(self):
        objective = self.objective(tracking_mode="manual", target=10, user_id=self.commercial.id)
        objective.with_user(self.director).target = 20
        self.assertEqual(objective.target, 20)
        self.assertTrue(objective.with_user(self.director).can_manage)

    def test_everyone_sees_only_their_objectives_except_finance_and_direction(self):
        mine = self.objective(tracking_mode="manual", target=1, user_id=self.commercial.id)
        other = self.objective(tracking_mode="manual", target=1, user_id=self.other_commercial.id)
        visible = self.Objective.with_user(self.commercial).search([("id", "in", (mine | other).ids)])
        self.assertEqual(visible, mine)
        for reader in (self.finance, self.director):
            self.assertEqual(self.Objective.with_user(reader).search([("id", "in", (mine | other).ids)]), mine | other)
        with self.assertRaises(AccessError):
            other.with_user(self.finance).manual_value = 3

    # --- Assistant « Fixer les objectifs de l'année » ---------------------------------

    def test_plan_creates_and_updates_objectives(self):
        existing = self.objective(name="CA existant", indicator="invoiced", target=1000, year=2031)
        Plan = self.env["caissecash.objective.plan"].with_user(self.director)
        plan = Plan.create({"year": 2031})
        plan._onchange_year()
        lines = {line.indicator: line for line in plan.line_ids if line.indicator}
        self.assertEqual(set(lines), {"invoiced", "paid", "new_clients", "installations", "subscriptions"})
        self.assertEqual(lines["invoiced"].objective_id, existing)
        lines["invoiced"].target = 5000
        lines["installations"].target = 40
        plan.line_ids = [(0, 0, {"tracking_mode": "manual", "name": "Recrutements", "unit": "techniciens", "target": 2})]
        plan.action_apply()

        objectives = self.Objective.search([("year", "=", 2031)])
        self.assertEqual(existing.target, 5000)
        self.assertEqual(
            sorted(objectives.mapped("name")),
            sorted(["CA existant", "Installations réalisées 2031", "Recrutements"]),
        )
        manual = objectives.filtered(lambda o: o.name == "Recrutements")
        self.assertEqual((manual.tracking_mode, manual.unit, manual._quarters()), ("manual", "techniciens", [1, 1, 0, 0]))

    def test_plan_is_for_direction_only(self):
        with self.assertRaises(AccessError):
            self.env["caissecash.objective.plan"].with_user(self.commercial).create({"year": 2031})
