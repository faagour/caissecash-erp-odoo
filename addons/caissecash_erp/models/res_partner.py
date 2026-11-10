import re

from odoo import api, fields, models
from odoo.tools import SQL

# Boutons de la fiche client simplifiée : (champ compteur, modèle, champ client, titre).
RELATED = [
    ("caissecash_establishment_count", "caissecash.establishment", "partner_id", "Établissements"),
    ("caissecash_equipment_count", "caissecash.equipment", "customer_id", "Matériel installé"),
    ("caissecash_subscription_count", "caissecash.subscription", "partner_id", "Abonnements"),
    ("caissecash_installation_count", "caissecash.installation", "partner_id", "Installations"),
    ("caissecash_sav_ticket_count", "caissecash.sav.ticket", "partner_id", "Tickets SAV"),
]


def phone_key(number):
    """Les 9 derniers chiffres : « +212 6 12-34-56-78 » et « 0612345678 » se valent."""
    digits = re.sub(r"\D", "", number or "")
    return digits[-9:] if len(digits) >= 8 else None


class ResPartner(models.Model):
    """Champs complémentaires CaisseCash sur la fiche client/fournisseur
    (cahier des charges §14). Les champs déjà natifs à Odoo ne sont pas
    dupliqués : name (raison sociale), phone, email, street, city,
    comment (notes), user_id (commercial, ajouté par le module sale),
    property_payment_term_id (conditions de paiement).
    """

    _inherit = "res.partner"

    commercial_name = fields.Char(string="Nom commercial")
    responsable_name = fields.Char(string="Responsable")
    whatsapp = fields.Char(string="WhatsApp")

    ice = fields.Char(string="ICE")
    identifiant_fiscal = fields.Char(string="IF")
    rc = fields.Char(string="RC")
    taxe_professionnelle = fields.Char(string="Taxe professionnelle")

    business_type = fields.Selection(
        [
            ("restaurant", "Restaurant"),
            ("snack", "Snack"),
            ("cafe", "Café"),
            ("commerce", "Commerce"),
            ("autre", "Autre"),
        ],
        string="Type de commerce",
    )
    source_id = fields.Many2one("utm.source", string="Source du prospect")

    establishment_ids = fields.One2many(
        "caissecash.establishment", "partner_id", string="Établissements"
    )

    vendor_lead_time_days = fields.Integer(
        string="Délai moyen fournisseur (jours)",
        help="Délai moyen constaté entre commande et réception, à titre indicatif.",
    )

    caissecash_duplicate_ids = fields.Many2many(
        "res.partner", string="Doublons possibles", compute="_compute_caissecash_duplicates",
    )
    caissecash_duplicate_message = fields.Char(compute="_compute_caissecash_duplicates")

    caissecash_establishment_count = fields.Integer(compute="_compute_caissecash_counts")
    caissecash_equipment_count = fields.Integer(compute="_compute_caissecash_counts")
    caissecash_subscription_count = fields.Integer(compute="_compute_caissecash_counts")
    caissecash_installation_count = fields.Integer(compute="_compute_caissecash_counts")
    caissecash_sav_ticket_count = fields.Integer(compute="_compute_caissecash_counts")

    # --- Doublons -----------------------------------------------------------------

    @api.depends("name", "phone", "whatsapp", "ice", "caissecash_is_partner")
    def _compute_caissecash_duplicates(self):
        for partner in self:
            matches = partner._caissecash_find_duplicates()
            partner.caissecash_duplicate_ids = [(6, 0, list(matches))]
            partner.caissecash_duplicate_message = (
                ("Ce partenaire" if partner.caissecash_is_partner else "Ce client")
                + " existe peut-être déjà : " + " ; ".join(
                    f"« {self.browse(pid).display_name} » ({', '.join(reasons)})"
                    for pid, reasons in matches.items()
                )
            ) if matches else False

    def _caissecash_find_duplicates(self):
        """Autres contacts avec le même téléphone/WhatsApp, le même ICE ou le même nom.
        Retourne {id: [raisons]} (au plus 5), limité à ce que l'utilisateur peut lire."""
        self.ensure_one()
        keys = sorted({k for k in (phone_key(self.phone), phone_key(self.whatsapp)) if k})
        ice = re.sub(r"\s", "", self.ice or "")
        name = (self.name or "").strip()
        if not keys and not ice and len(name) < 4:
            return {}
        # Le contact lui-même, sa société et ses contacts ne sont pas des doublons.
        family = [pid for pid in {self._origin.id, self._origin.parent_id.id, self.parent_id.id} if pid] or [0]

        def phone_sql(column):
            return SQL(
                "right(regexp_replace(coalesce(%s, ''), '\\D', '', 'g'), 9) = ANY(%s)",
                SQL.identifier(column), keys,
            )

        checks = [
            ("même téléphone", SQL("(%s OR %s)", phone_sql("phone"), phone_sql("whatsapp")) if keys else None),
            ("même ICE", SQL("regexp_replace(coalesce(ice, ''), '\\s', '', 'g') = %s", ice) if ice else None),
            ("même nom", SQL("lower(trim(name)) = lower(%s)", name) if len(name) >= 4 else None),
        ]
        found = {}
        for reason, condition in checks:
            if condition is None:
                continue
            self.env.cr.execute(SQL(
                "SELECT id FROM res_partner WHERE active AND %s AND id <> ALL(%s)"
                " AND (parent_id IS NULL OR parent_id <> ALL(%s)) ORDER BY id LIMIT 5",
                condition, family, family,
            ))
            for (pid,) in self.env.cr.fetchall():
                found.setdefault(pid, []).append(reason)
        readable = set(self.browse(list(found))._filtered_access("read").ids)
        return {pid: reasons for pid, reasons in list(found.items())[:5] if pid in readable}

    # --- Boutons de la fiche ------------------------------------------------------

    def _compute_caissecash_counts(self):
        partners = self.filtered("id")
        for count_field, model, partner_field, _title in RELATED:
            counts = {}
            if partners and self.env[model].has_access("read"):
                counts = {
                    partner.id: total
                    for partner, total in self.env[model]._read_group(
                        [(partner_field, "in", partners.ids)], [partner_field], ["__count"],
                    )
                }
            for partner in self:
                partner[count_field] = counts.get(partner._origin.id, 0)

    def _caissecash_open_related(self, count_field):
        self.ensure_one()
        _field, model, partner_field, title = next(row for row in RELATED if row[0] == count_field)
        return {
            "type": "ir.actions.act_window",
            "name": f"{title} — {self.display_name}",
            "res_model": model,
            "view_mode": "list,form",
            "domain": [(partner_field, "=", self.id)],
            "context": {f"default_{partner_field}": self.id},
        }

    def action_caissecash_establishments(self):
        return self._caissecash_open_related("caissecash_establishment_count")

    def action_caissecash_equipments(self):
        return self._caissecash_open_related("caissecash_equipment_count")

    def action_caissecash_subscriptions(self):
        return self._caissecash_open_related("caissecash_subscription_count")

    def action_caissecash_installations(self):
        return self._caissecash_open_related("caissecash_installation_count")

    def action_caissecash_sav_tickets(self):
        return self._caissecash_open_related("caissecash_sav_ticket_count")

    def action_caissecash_full_form(self):
        """Ouvre la fiche Odoo complète (comptabilité, conditions de vente…)."""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": self.display_name,
            "res_model": "res.partner",
            "res_id": self.id,
            "views": [(self.env.ref("base.view_partner_form").id, "form")],
            "target": "current",
        }
