from odoo import fields, models


class CaissecashOnboardingStep(models.Model):
    """Checklist de mise en service (cahier des charges §24).

    Simple liste à cocher avec instructions détaillées par étape (où
    cliquer, quoi saisir, champs obligatoires, comment vérifier). Les 20
    étapes de départ sont fournies en données (data/caissecash_onboarding_data.xml),
    modifiables/complétables librement — ce ne sont que des cases à cocher,
    aucune donnée métier n'est créée par ce modèle.
    """

    _name = "caissecash.onboarding.step"
    _description = "Étape de mise en service CaisseCash"
    _order = "sequence"

    sequence = fields.Integer(default=10)
    name = fields.Char(string="Étape", required=True)
    instructions = fields.Html(string="Instructions")
    done = fields.Boolean(string="Fait")
    done_by = fields.Many2one("res.users", string="Complété par", readonly=True, copy=False)
    done_date = fields.Datetime(string="Date", readonly=True, copy=False)

    def action_toggle_done(self):
        for rec in self:
            if rec.done:
                rec.write({"done": False, "done_by": False, "done_date": False})
            else:
                rec.write({
                    "done": True,
                    "done_by": self.env.user.id,
                    "done_date": fields.Datetime.now(),
                })
