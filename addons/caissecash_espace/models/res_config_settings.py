from odoo import fields, models
from odoo.exceptions import ValidationError

# Phrases affichées par défaut dans Mon espace (une par jour, à tour de rôle).
DEFAULT_QUOTES = [
    "Le travail bien fait parle de lui-même. 💪",
    "Petit à petit, l'oiseau fait son nid. 🐦",
    "Chaque client installé est une victoire. 🏆",
    "Seul on va plus vite, ensemble on va plus loin. 🤝",
    "Un pas de plus chaque jour. ⭐",
    "La qualité, c'est notre meilleure publicité. 🚀",
    "Les détails font la différence. 🎯",
]
QUOTES_PARAM = "caissecash_espace.quotes"
WEEKLY_GOAL_PARAM = "caissecash_espace.weekly_goal"


class ResConfigSettings(models.TransientModel):
    """Réglages CaisseCash modifiables par l'administrateur (Paramètres >
    CaisseCash), sans toucher au code."""

    _inherit = "res.config.settings"

    caissecash_weekly_goal = fields.Integer(
        string="Objectif de l'équipe par semaine", default=15, config_parameter=WEEKLY_GOAL_PARAM,
    )
    # Texte sur plusieurs lignes : Odoo ne le relie pas tout seul à un paramètre
    # système, d'où get_values / set_values ci-dessous.
    caissecash_quotes = fields.Text(string="Phrases de motivation")
    caissecash_objective_at_risk_gap = fields.Integer(
        string="« Léger retard » au-delà de", default=5,
        config_parameter="caissecash_erp.objective_at_risk_gap",
    )
    caissecash_objective_late_gap = fields.Integer(
        string="« En retard » au-delà de", default=15,
        config_parameter="caissecash_erp.objective_late_gap",
    )

    def set_values(self):
        for settings in self:
            if settings.caissecash_weekly_goal < 1:
                raise ValidationError("L'objectif de l'équipe par semaine doit être d'au moins 1 tâche.")
            if not 1 <= settings.caissecash_objective_at_risk_gap < settings.caissecash_objective_late_gap <= 100:
                raise ValidationError(
                    "Les seuils de retard doivent aller de 1 à 100 points, le seuil « En retard » étant "
                    "plus grand que le seuil « Léger retard »."
                )
        super().set_values()
        self.env["ir.config_parameter"].sudo().set_param(QUOTES_PARAM, (self.caissecash_quotes or "").strip())

    def get_values(self):
        values = super().get_values()
        quotes = self.env["ir.config_parameter"].sudo().get_param(QUOTES_PARAM)
        values["caissecash_quotes"] = quotes or "\n".join(DEFAULT_QUOTES)
        return values
