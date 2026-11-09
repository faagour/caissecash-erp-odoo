import logging

from odoo import fields, models
from odoo.tools.safe_eval import safe_eval

_logger = logging.getLogger(__name__)


class CaissecashJourneyStep(models.Model):
    """Étape du parcours « Du prospect au SAV » de Mon espace. L'administrateur
    choisit les étapes affichées, leur nom et leur ordre (Paramètres >
    CaisseCash) ; ce qui est compté et l'écran ouvert au clic restent fixés
    par le module."""

    _name = "caissecash.journey.step"
    _description = "Étape du parcours client (Mon espace)"
    _order = "sequence, id"

    sequence = fields.Integer(default=10)
    visible = fields.Boolean(string="Affichée", default=True)
    icon = fields.Char(string="Icône", help="Un émoji, ex. 🎯")
    name = fields.Char(string="Nom affiché", required=True)
    hint = fields.Char(string="Après le nombre", help="Affiché après le nombre de dossiers, ex. « en cours ».")
    model_name = fields.Char(string="Dossiers de", required=True, readonly=True)
    domain = fields.Char(string="Dossiers comptés", default="[]", readonly=True)
    action_xmlid = fields.Char(string="Écran ouvert au clic", readonly=True)

    def _home_data(self):
        """Étapes affichées que l'utilisateur a le droit de consulter."""
        steps = []
        for step in self.search([("visible", "=", True)]):
            if step.model_name not in self.env or not self.env[step.model_name].has_access("read"):
                continue
            if not (step.action_xmlid and self.env.ref(step.action_xmlid, raise_if_not_found=False)):
                continue
            try:
                domain = safe_eval(step.domain or "[]")
                count = self.env[step.model_name].search_count(domain)
            except Exception:  # noqa: BLE001 — une étape mal réglée ne doit pas bloquer Mon espace
                _logger.exception("Étape de parcours « %s » ignorée", step.name)
                continue
            steps.append({
                "id": step.id,
                "label": step.name,
                "icon": step.icon or "",
                "count": count,
                "hint": step.hint or "",
                "action": step.action_xmlid,
            })
        return steps
