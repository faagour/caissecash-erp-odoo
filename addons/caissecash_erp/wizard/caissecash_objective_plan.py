from datetime import date

from odoo import api, fields, models
from odoo.fields import Command

from ..models.caissecash_objective import INDICATORS

# Nom proposé pour chaque indicateur de l'ERP ({year} = année des objectifs).
SUGGESTED_NAMES = {
    "invoiced": "Chiffre d'affaires facturé {year}",
    "paid": "Encaissements {year}",
    "new_clients": "Nouveaux clients {year}",
    "installations": "Installations réalisées {year}",
    "subscriptions": "Abonnements actifs fin {year}",
}


class CaissecashObjectivePlan(models.TransientModel):
    """Assistant « Fixer les objectifs de l'année » : un seul tableau pour
    saisir toutes les cibles, avec le réalisé de l'année précédente en repère."""

    _name = "caissecash.objective.plan"
    _description = "Fixer les objectifs de l'année"

    year = fields.Integer(string="Année", required=True, default=lambda self: self._default_year())
    line_ids = fields.One2many("caissecash.objective.plan.line", "plan_id", string="Objectifs")

    @api.model
    def _default_year(self):
        # À partir d'octobre, on prépare l'année suivante.
        today = fields.Date.context_today(self)
        return today.year + 1 if today.month >= 10 else today.year

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        if "line_ids" in fields_list:
            values["line_ids"] = self._line_commands(values.get("year") or self._default_year())
        return values

    @api.onchange("year")
    def _onchange_year(self):
        if self.year and 2000 <= self.year <= 2100:
            self.line_ids = [Command.clear(), *self._line_commands(self.year)]

    @api.model
    def _line_commands(self, year):
        """Une ligne par indicateur de l'ERP (avec l'objectif existant s'il y en
        a un), puis les objectifs suivis à la main déjà créés pour l'année."""
        Objective = self.env["caissecash.objective"]
        existing = Objective.search([("year", "=", year)])
        previous_start, previous_end = date(year - 1, 1, 1), date(year - 1, 12, 31)
        commands = []
        for sequence, indicator in enumerate(INDICATORS, start=1):
            objective = existing.filtered(lambda o: o.tracking_mode == "auto" and o.indicator == indicator)[:1]
            sample = objective or Objective.new({"tracking_mode": "auto", "indicator": indicator, "year": year})
            level = INDICATORS[indicator][3]
            previous = Objective._compute_indicator(indicator, previous_start if not level else previous_end, previous_end)
            commands.append(Command.create({
                "sequence": sequence,
                "objective_id": objective.id,
                "tracking_mode": "auto",
                "indicator": indicator,
                "name": objective.name or SUGGESTED_NAMES[indicator].format(year=year),
                "unit": sample.unit_label,
                "last_year_label": sample._format_value(previous),
                "target": objective.target,
                "user_id": objective.user_id.id,
                "project_id": objective.project_id.id,
            }))
        for sequence, objective in enumerate(existing.filtered(lambda o: o.tracking_mode == "manual"), start=10):
            commands.append(Command.create({
                "sequence": sequence,
                "objective_id": objective.id,
                "tracking_mode": "manual",
                "name": objective.name,
                "unit": objective.unit,
                "last_year_label": "",
                "target": objective.target,
                "user_id": objective.user_id.id,
                "project_id": objective.project_id.id,
            }))
        return commands

    def action_apply(self):
        """Crée les objectifs qui ont une cible et met à jour ceux qui existent ;
        les lignes laissées sans cible sont ignorées."""
        self.ensure_one()
        Objective = self.env["caissecash.objective"]
        for line in self.line_ids:
            values = {
                "name": line.name,
                "target": line.target,
                "user_id": line.user_id.id,
                "project_id": line.project_id.id,
            }
            if line.objective_id:
                changed = {
                    key: value for key, value in values.items()
                    if (line.objective_id[key].id if key in ("user_id", "project_id") else line.objective_id[key]) != value
                }
                if changed:
                    line.objective_id.write(changed)
            elif line.target and line.name:
                Objective.create({
                    **values,
                    "year": self.year,
                    "tracking_mode": line.tracking_mode,
                    "indicator": line.indicator if line.tracking_mode == "auto" else False,
                    "unit": line.unit if line.tracking_mode == "manual" else False,
                    "sequence": line.sequence,
                })
        action = self.env["ir.actions.act_window"]._for_xml_id("caissecash_erp.action_caissecash_objective")
        action["context"] = {}
        action["domain"] = [("year", "=", self.year)]
        return action


class CaissecashObjectivePlanLine(models.TransientModel):
    _name = "caissecash.objective.plan.line"
    _description = "Ligne de l'assistant « Fixer les objectifs de l'année »"
    _order = "sequence, id"

    plan_id = fields.Many2one("caissecash.objective.plan", required=True, ondelete="cascade")
    sequence = fields.Integer(default=50)
    objective_id = fields.Many2one("caissecash.objective", string="Objectif existant")
    tracking_mode = fields.Selection(
        [("auto", "Calculé automatiquement"), ("manual", "Mis à jour à la main")],
        string="Suivi", required=True, default="manual",
    )
    indicator = fields.Selection(
        [(key, values[0]) for key, values in INDICATORS.items()], string="Mesuré par",
    )
    name = fields.Char(string="Objectif", required=True)
    unit = fields.Char(string="Unité")
    last_year_label = fields.Char(string="Réalisé l'an dernier")
    target = fields.Float(string="Cible")
    user_id = fields.Many2one("res.users", string="Responsable", domain=[("share", "=", False)])
    project_id = fields.Many2one("project.project", string="Pôle")
