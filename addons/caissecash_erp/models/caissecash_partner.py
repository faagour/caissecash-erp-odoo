from odoo import api, fields, models

# Le partenariat avance comme un prospect : on le contacte, on en discute,
# puis il devient partenaire actif (ou s'arrête).
PARTNER_STATES = [
    ("a_contacter", "À contacter"),
    ("discussion", "En discussion"),
    ("actif", "Partenaire actif"),
    ("inactif", "Inactif"),
]


class CaissecashPartnerCategory(models.Model):
    """Activité d'un partenaire (aménagement de cuisine, matériel de cuisine…),
    modifiable par l'équipe commerciale."""

    _name = "caissecash.partner.category"
    _description = "Activité d'un partenaire"
    _order = "sequence, name"

    name = fields.Char(string="Activité", required=True)
    sequence = fields.Integer(default=10)
    color = fields.Integer(string="Couleur")
    active = fields.Boolean(default=True)

    _name_uniq = models.Constraint("unique(name)", "Cette activité existe déjà.")


class ResPartner(models.Model):
    """Partenaires : les sociétés qui travaillent pour les mêmes restaurants que
    CaisseCash (aménagement et matériel de cuisine…). Ce sont des contacts Odoo
    marqués « partenaire », avec leur fiche, leur statut et leur contrat ;
    l'historique (notes, appels, rendez-vous, documents) est dans le chatter."""

    _inherit = "res.partner"

    caissecash_is_partner = fields.Boolean(string="Partenaire CaisseCash", index=True)
    caissecash_partner_category_ids = fields.Many2many(
        "caissecash.partner.category", "caissecash_partner_category_rel", "partner_id", "category_id",
        string="Activités",
    )
    caissecash_partner_state = fields.Selection(
        PARTNER_STATES, string="Statut du partenariat", tracking=True, group_expand=True,
    )
    caissecash_partner_zone = fields.Char(
        string="Zone couverte", help="Villes ou régions où le partenaire travaille.",
    )
    caissecash_partner_offer = fields.Text(string="Ce qu'ils proposent")
    caissecash_partner_conditions = fields.Text(string="Conditions convenues")
    caissecash_partner_date_start = fields.Date(string="Partenaire depuis", tracking=True)
    caissecash_partner_date_end = fields.Date(string="Fin ou renouvellement du contrat", tracking=True)
    caissecash_partner_contract = fields.Binary(string="Contrat signé", attachment=True)
    caissecash_partner_contract_name = fields.Char(string="Nom du fichier du contrat")
    caissecash_partner_contract_expired = fields.Boolean(compute="_compute_caissecash_partner_contract_expired")

    @api.depends("caissecash_partner_date_end", "caissecash_partner_state")
    def _compute_caissecash_partner_contract_expired(self):
        today = fields.Date.context_today(self)
        for partner in self:
            partner.caissecash_partner_contract_expired = bool(
                partner.caissecash_partner_state == "actif"
                and partner.caissecash_partner_date_end
                and partner.caissecash_partner_date_end < today
            )

    def _caissecash_partner_defaults(self, vals):
        """Un nouveau partenaire commence « À contacter » ; quand il devient actif,
        la date de début du partenariat est notée si elle manque."""
        if vals.get("caissecash_is_partner") and not vals.get("caissecash_partner_state"):
            vals["caissecash_partner_state"] = "a_contacter"
        if vals.get("caissecash_partner_state") == "actif" and not vals.get("caissecash_partner_date_start"):
            vals["caissecash_partner_date_start"] = fields.Date.context_today(self)
        return vals

    @api.model_create_multi
    def create(self, vals_list):
        return super().create([self._caissecash_partner_defaults(dict(vals)) for vals in vals_list])

    def write(self, vals):
        if vals.get("caissecash_partner_state") == "actif" and "caissecash_partner_date_start" not in vals:
            without_date = self.filtered(lambda p: not p.caissecash_partner_date_start)
            if without_date:
                super(ResPartner, without_date).write(
                    {"caissecash_partner_date_start": fields.Date.context_today(self)})
        return super().write(vals)
