from odoo import fields, models


class ProjectProject(models.Model):
    _inherit = "project.project"

    caissecash_channel_id = fields.Many2one(
        "discuss.channel",
        string="Canal d'annonce",
        domain=[("channel_type", "=", "channel")],
        help="Canal de discussion où l'équipe est prévenue quand une tâche de ce projet est terminée.",
    )
