from odoo import fields, models


class HrEmployee(models.Model):
    """Type de relation avec CaisseCash (cahier des charges §13).

    Les champs natifs (identité, coordonnées, département via department_id,
    responsable via parent_id, date d'entrée via hr.contract si utilisé,
    documents via les pièces jointes) ne sont pas dupliqués ici.
    """

    _inherit = "hr.employee"

    relation_type = fields.Selection(
        [
            ("cofondateur", "Cofondateur"),
            ("salarie", "Salarié"),
            ("stagiaire", "Stagiaire"),
            ("prestataire", "Prestataire"),
        ],
        string="Type de relation",
        default="salarie",
    )
    founder_id = fields.Many2one(
        "caissecash.founder", string="Fiche associé liée",
        help="À renseigner si ce membre de l'équipe est aussi cofondateur.",
    )
    date_start = fields.Date(string="Date de début")
