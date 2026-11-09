import calendar
import math
from datetime import date, datetime, time, timedelta

from odoo import api, fields, models
from odoo.exceptions import AccessError, ValidationError
from odoo.tools import float_compare, float_is_zero, float_round
from odoo.tools.misc import formatLang

# Indicateurs calculés depuis l'ERP : clé -> (libellé, unité, monétaire, niveau).
# Un indicateur « niveau » mesure un état à une date (abonnements actifs) ; les
# autres s'additionnent depuis le 1er janvier.
INDICATORS = {
    "invoiced": ("CA facturé", "", True, False),
    "paid": ("CA encaissé", "", True, False),
    "new_clients": ("Nouveaux clients", "clients", False, False),
    "installations": ("Installations terminées", "installations", False, False),
    "subscriptions": ("Abonnements actifs", "abonnements", False, True),
}

STATUSES = [
    ("no_target", "Cible à fixer"),
    ("upcoming", "À venir"),
    ("on_track", "Dans les temps"),
    ("at_risk", "Léger retard"),
    ("late", "En retard"),
    ("done", "Atteint"),
    ("missed", "Non atteint"),
]

QUARTER_FIELDS = ("target_q1", "target_q2", "target_q3", "target_q4")
QUARTER_LABELS = ("janv. – mars", "avr. – juin", "juil. – sept.", "oct. – déc.")

# Écart toléré avec l'avancement attendu à date (en points de pourcentage) ;
# modifiable dans Paramètres > CaisseCash.
AT_RISK_GAP = 5
LATE_GAP = 15
AT_RISK_GAP_PARAM = "caissecash_erp.objective_at_risk_gap"
LATE_GAP_PARAM = "caissecash_erp.objective_late_gap"

# Ce que seuls l'administrateur et la direction peuvent changer : les
# responsables mettent à jour la valeur atteinte et le plan d'action.
MANAGER_GROUP = "caissecash_erp.group_direction"
PROTECTED_FIELDS = frozenset({
    "name", "year", "user_id", "project_id", "tracking_mode", "indicator", "measure", "unit",
    "target", *QUARTER_FIELDS, "manual_start_value", "active", "sequence",
})


def quarter_bounds(year):
    """Premier et dernier jour de chaque trimestre de l'année."""
    return [
        (date(year, month, 1), date(year, month + 2, calendar.monthrange(year, month + 2)[1]))
        for month in (1, 4, 7, 10)
    ]


class CaissecashObjective(models.Model):
    _name = "caissecash.objective"
    _description = "Objectif de l'année"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "year desc, sequence, id"

    name = fields.Char(string="Objectif", required=True, tracking=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    year = fields.Integer(
        string="Année", required=True, tracking=True,
        default=lambda self: fields.Date.context_today(self).year,
    )
    user_id = fields.Many2one(
        "res.users", string="Responsable", tracking=True,
        default=lambda self: self.env.user, domain=[("share", "=", False)],
    )
    project_id = fields.Many2one("project.project", string="Pôle", help="Pôle (projet) dont relève l'objectif.")
    description = fields.Html(string="Plan d'action")
    currency_id = fields.Many2one("res.currency", compute="_compute_currency_id")

    tracking_mode = fields.Selection(
        [("auto", "Calculé automatiquement"), ("manual", "Mis à jour à la main")],
        string="Suivi", required=True, default="auto", tracking=True,
    )
    indicator = fields.Selection(
        [(key, values[0]) for key, values in INDICATORS.items()],
        string="Indicateur", tracking=True,
        help="Chiffre de l'ERP utilisé pour mesurer l'avancement.\n"
             "• CA facturé : montant TTC des factures clients validées de l'année.\n"
             "• CA encaissé : paiements clients reçus dans l'année.\n"
             "• Nouveaux clients : établissements mis en service dans l'année.\n"
             "• Installations terminées : installations passées à « Terminée » dans l'année.\n"
             "• Abonnements actifs : abonnements en cours à la date du jour.",
    )
    measure = fields.Selection(
        [("cumulative", "Cumul depuis le 1er janvier"), ("level", "Niveau à atteindre")],
        # Pas de valeur par défaut : elle passerait avant le calcul à la création.
        string="Type de cible", required=True,
        compute="_compute_measure", store=True, readonly=False, precompute=True,
        help="Cumul : on additionne ce qui est réalisé dans l'année (ventes, recrutements…).\n"
             "Niveau : on vise une valeur à atteindre en fin d'année (nombre d'abonnés, note client…).",
    )
    unit = fields.Char(
        string="Unité", compute="_compute_unit", store=True, readonly=False, precompute=True,
        help="Affichée après les chiffres, ex. : recrutements, clients, %.",
    )
    is_monetary = fields.Boolean(compute="_compute_is_monetary")
    can_manage = fields.Boolean(
        compute="_compute_can_manage",
        help="L'utilisateur peut changer les cibles (administrateur et direction).",
    )
    unit_label = fields.Char(compute="_compute_is_monetary")
    current_quarter = fields.Integer(
        compute="_compute_current_quarter",
        help="Trimestre en cours : 0 avant l'année, 1 à 4 pendant, 5 après.",
    )

    target = fields.Float(string="Objectif de l'année", tracking=True)
    target_q1 = fields.Float(string="Cible T1")
    target_q2 = fields.Float(string="Cible T2")
    target_q3 = fields.Float(string="Cible T3")
    target_q4 = fields.Float(string="Cible T4")
    manual_value = fields.Float(
        string="Valeur atteinte", tracking=True,
        help="À mettre à jour par le responsable ; chaque changement est gardé dans l'historique.",
    )
    manual_start_value = fields.Float(
        string="Valeur au 1er janvier",
        help="Point de départ d'un objectif de niveau suivi à la main (ex. nombre d'abonnés au 1er janvier).",
    )

    start_value = fields.Float(string="Point de départ", compute="_compute_progress")
    current_value = fields.Float(string="Réalisé", compute="_compute_progress")
    expected_value = fields.Float(string="Attendu à date", compute="_compute_progress")
    progress = fields.Float(string="Avancement", compute="_compute_progress")
    expected_progress = fields.Float(string="Avancement attendu", compute="_compute_progress")
    status = fields.Selection(STATUSES, string="État", compute="_compute_progress")
    progress_label = fields.Char(string="Réalisé / objectif", compute="_compute_progress")
    expected_label = fields.Char(string="Attendu aujourd'hui", compute="_compute_progress")
    value_q1 = fields.Float(string="Réalisé T1", compute="_compute_progress")
    value_q2 = fields.Float(string="Réalisé T2", compute="_compute_progress")
    value_q3 = fields.Float(string="Réalisé T3", compute="_compute_progress")
    value_q4 = fields.Float(string="Réalisé T4", compute="_compute_progress")

    # --- Champs dérivés de l'indicateur ------------------------------------------

    def _compute_currency_id(self):
        self.currency_id = self.env.company.currency_id

    @api.depends("tracking_mode", "indicator")
    def _compute_measure(self):
        for rec in self:
            if rec.tracking_mode == "auto" and rec.indicator:
                rec.measure = "level" if INDICATORS[rec.indicator][3] else "cumulative"
            else:
                rec.measure = rec.measure or "cumulative"

    @api.depends("tracking_mode", "indicator")
    def _compute_unit(self):
        for rec in self:
            if rec.tracking_mode == "auto" and rec.indicator:
                rec.unit = INDICATORS[rec.indicator][1]
            else:
                rec.unit = rec.unit or ""

    @api.depends("tracking_mode", "indicator", "unit")
    def _compute_is_monetary(self):
        symbol = self.env.company.currency_id.symbol
        for rec in self:
            rec.is_monetary = bool(rec.tracking_mode == "auto" and rec.indicator and INDICATORS[rec.indicator][2])
            rec.unit_label = symbol if rec.is_monetary else rec.unit or ""

    @api.depends_context("uid")
    def _compute_can_manage(self):
        self.can_manage = self._user_can_manage()

    def _user_can_manage(self):
        return self.env.su or self.env.user.has_group(MANAGER_GROUP)

    @api.depends("year")
    def _compute_current_quarter(self):
        today = fields.Date.context_today(self)
        for rec in self:
            if not rec.year or today.year < rec.year:
                rec.current_quarter = 0
            elif today.year > rec.year:
                rec.current_quarter = 5
            else:
                rec.current_quarter = (today.month - 1) // 3 + 1

    # --- Contrôles -----------------------------------------------------------------

    @api.constrains("year")
    def _check_year(self):
        for rec in self:
            if not 2000 <= rec.year <= 2100:
                raise ValidationError("L'année doit être comprise entre 2000 et 2100.")

    @api.constrains("tracking_mode", "indicator")
    def _check_indicator(self):
        for rec in self:
            if rec.tracking_mode == "auto" and not rec.indicator:
                raise ValidationError("Choisissez l'indicateur de l'ERP qui mesure cet objectif.")

    @api.constrains("target", "measure", *QUARTER_FIELDS)
    def _check_quarters(self):
        for rec in self:
            quarters = rec._quarters()
            # Trimestres pas encore répartis (création par import ou par l'API) :
            # create() s'en charge juste après.
            if not any(quarters):
                continue
            if float_compare(rec._quarters_total(quarters), rec.target, precision_digits=2):
                if rec.measure == "level":
                    raise ValidationError(
                        f"« {rec.name} » : la cible de T4 (fin décembre) doit être égale à l'objectif de l'année."
                    )
                raise ValidationError(
                    f"« {rec.name} » : la somme des 4 trimestres ({rec._format_value(sum(quarters))}) doit être "
                    f"égale à l'objectif de l'année ({rec._format_value(rec.target)})."
                )

    # --- Répartition sur les trimestres -------------------------------------------------

    def _quarters(self):
        return [self[name] or 0.0 for name in QUARTER_FIELDS]

    def _quarters_total(self, quarters=None):
        quarters = quarters if quarters is not None else self._quarters()
        return quarters[3] if self.measure == "level" else sum(quarters)

    def _digits(self, *values):
        """Décimales des cibles : aucune pour un nombre entier (clients,
        installations…), deux pour un montant ou une valeur décimale."""
        if self.is_monetary or any(not float(value or 0).is_integer() for value in values):
            return 2
        return 0

    def _even_quarters(self, target, measure=None):
        """Cibles régulières : parts égales pour un cumul, progression linéaire
        depuis le point de départ pour un niveau (T4 = objectif de l'année)."""
        measure = measure or self.measure
        target = target or 0.0
        if measure == "level":
            start = self._start_value()
            digits = self._digits(target, start)
            steps = [float_round(start + (target - start) * i / 4, precision_digits=digits) for i in (1, 2, 3)]
            return steps + [target]
        digits = self._digits(target)
        step = 10 ** -digits
        base = float_round(math.floor(round(target / 4 / step, 6)) * step, precision_digits=digits)
        quarters = [base] * 4
        remainder = float_round(target - base * 4, precision_digits=digits)
        index = 0
        while float_compare(remainder, 0, precision_digits=digits) > 0 and index < 4:
            quarters[index] = float_round(quarters[index] + step, precision_digits=digits)
            remainder = float_round(remainder - step, precision_digits=digits)
            index += 1
        return quarters

    def _same(self, left, right):
        return all(float_compare(a, b, precision_digits=2) == 0 for a, b in zip(left, right))

    def _quarters_look_regular(self):
        quarters = self._quarters()
        if not any(quarters):
            return True
        return any(
            self._same(quarters, self._even_quarters(total, measure))
            for measure, total in (("cumulative", sum(quarters)), ("level", quarters[3]))
        )

    def _fitted_quarters(self, target):
        """Trimestres ajustés à un nouvel objectif annuel : répartition régulière
        si les trimestres l'étaient, sinon mise à l'échelle qui garde la
        saisonnalité choisie (ex. un T4 plus fort)."""
        quarters = self._quarters()
        if self._quarters_look_regular():
            return self._even_quarters(target)
        digits = self._digits(target, *quarters)
        if self.measure == "level":
            start, old_target = self._start_value(), quarters[3]
            if float_is_zero(old_target - start, precision_digits=2):
                return self._even_quarters(target)
            ratio = (target - start) / (old_target - start)
            return [float_round(start + (q - start) * ratio, precision_digits=digits) for q in quarters[:3]] + [target]
        total = sum(quarters)
        fitted = [float_round(q * target / total, precision_digits=digits) for q in quarters[:3]]
        return fitted + [float_round(target - sum(fitted), precision_digits=digits)]

    @api.onchange("target")
    def _onchange_target(self):
        quarters = self._fitted_quarters(self.target)
        if not self._same(quarters, self._quarters()):
            self.update(dict(zip(QUARTER_FIELDS, quarters)))

    @api.onchange("measure", "indicator", "manual_start_value", "year")
    def _onchange_structure(self):
        quarters = self._even_quarters(self.target)
        if not self._same(quarters, self._quarters()):
            self.update(dict(zip(QUARTER_FIELDS, quarters)))

    @api.onchange(*QUARTER_FIELDS)
    def _onchange_quarters(self):
        total = self._quarters_total()
        if float_compare(total, self.target, precision_digits=2):
            self.target = total

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for rec in records:
            if rec.target and not any(rec._quarters()):
                rec.write(dict(zip(QUARTER_FIELDS, rec._even_quarters(rec.target))))
        return records

    def write(self, vals):
        if PROTECTED_FIELDS & vals.keys() and not self._user_can_manage():
            raise AccessError(
                "Seuls l'administrateur et la direction peuvent modifier les cibles et le réglage des "
                "objectifs. Vous pouvez mettre à jour la valeur atteinte et le plan d'action."
            )
        # Nouvel objectif annuel sans trimestres fournis : on les ajuste avant
        # d'écrire, sinon le contrôle « somme des trimestres » échouerait.
        if "target" in vals and not set(QUARTER_FIELDS) & vals.keys():
            for rec in self:
                quarters = rec._fitted_quarters(vals["target"])
                super(CaissecashObjective, rec).write({**vals, **dict(zip(QUARTER_FIELDS, quarters))})
            return True
        return super().write(vals)

    # --- Calcul des indicateurs -------------------------------------------------------

    def _indicator_value(self, date_from, date_to):
        self.ensure_one()
        return self._compute_indicator(self.indicator, date_from, date_to)

    @api.model
    def _compute_indicator(self, indicator, date_from, date_to):
        """Valeur d'un indicateur : cumul entre deux dates (incluses), ou niveau
        à la date de fin pour un indicateur de niveau. Calculé pour toute
        l'entreprise, quels que soient les droits de la personne qui regarde."""
        env = self.sudo().env
        if indicator == "invoiced":
            [(total,)] = env["account.move"]._read_group(
                [
                    ("move_type", "=", "out_invoice"),
                    ("state", "=", "posted"),
                    ("company_id", "=", self.env.company.id),
                    ("invoice_date", ">=", date_from),
                    ("invoice_date", "<=", date_to),
                ],
                aggregates=["amount_total_signed:sum"],
            )
            return total or 0.0
        if indicator == "paid":
            # Montants réglés sur les factures clients (paiement ou rapprochement
            # bancaire), à la date du règlement ; les avoirs ne comptent pas.
            [(total,)] = env["account.partial.reconcile"]._read_group(
                [
                    ("debit_move_id.move_id.move_type", "=", "out_invoice"),
                    ("debit_move_id.move_id.state", "=", "posted"),
                    ("debit_move_id.company_id", "=", self.env.company.id),
                    ("credit_move_id.move_id.move_type", "!=", "out_refund"),
                    ("max_date", ">=", date_from),
                    ("max_date", "<=", date_to),
                ],
                aggregates=["amount:sum"],
            )
            return total or 0.0
        if indicator == "new_clients":
            # Date de mise en service, ou date de création si elle n'est pas renseignée.
            created_from = datetime.combine(date_from, time.min)
            created_to = datetime.combine(date_to + timedelta(days=1), time.min)
            return float(env["caissecash.establishment"].search_count([
                ("state", "!=", "draft"),
                "|",
                "&", ("commissioning_date", ">=", date_from), ("commissioning_date", "<=", date_to),
                "&", "&", ("commissioning_date", "=", False),
                ("create_date", ">=", created_from), ("create_date", "<", created_to),
            ]))
        if indicator == "installations":
            return float(env["caissecash.installation"].search_count([
                ("state", "=", "terminee"),
                ("date_done", ">=", date_from),
                ("date_done", "<=", date_to),
            ]))
        if indicator == "subscriptions":
            subscriptions = env["caissecash.subscription"].search([
                ("state", "!=", "essai"),
                ("date_start", "<=", date_to),
            ])

            def running(subscription):
                end = subscription.date_end
                if subscription.state in ("resilie", "expire") and not end:
                    end = subscription.write_date.date()
                return not end or end > date_to

            return float(len(subscriptions.filtered(running)))
        return 0.0

    def _start_value(self):
        """Point de départ : 0 pour un cumul ; pour un niveau, la valeur au
        31 décembre de l'année précédente (ou celle saisie à la main)."""
        self.ensure_one()
        if self.measure != "level":
            return 0.0
        if self.tracking_mode == "auto" and self.indicator and self.year:
            day = date(self.year - 1, 12, 31)
            return self._indicator_value(day, day)
        return self.manual_start_value or 0.0

    def _expected_at(self, day, start):
        """Valeur attendue à une date d'après les cibles trimestrielles,
        progressivement au fil de chaque trimestre."""
        quarters = self._quarters()
        bounds = quarter_bounds(self.year)
        if self.measure == "level":
            previous_day, previous_value = date(self.year - 1, 12, 31), start
            for (_first, last), value in zip(bounds, quarters):
                if day <= last:
                    share = (day - previous_day).days / (last - previous_day).days
                    return previous_value + (value - previous_value) * share
                previous_day, previous_value = last, value
            return quarters[3]
        expected = 0.0
        for (first, last), value in zip(bounds, quarters):
            if day >= last:
                expected += value
            elif day >= first:
                expected += value * ((day - first).days + 1) / ((last - first).days + 1)
        return expected

    @api.depends(
        "tracking_mode", "indicator", "measure", "year", "target", *QUARTER_FIELDS,
        "manual_value", "manual_start_value", "unit",
    )
    def _compute_progress(self):
        today = fields.Date.context_today(self)
        gaps = self._status_gaps()
        for rec in self:
            rec.update(rec._progress_values(today, gaps))

    @api.model
    def _status_gaps(self):
        """Seuils « léger retard » et « en retard » (Paramètres > CaisseCash)."""
        params = self.env["ir.config_parameter"].sudo()

        def read(key, default):
            try:
                return max(0, int(params.get_param(key, default)))
            except (TypeError, ValueError):
                return default

        at_risk, late = read(AT_RISK_GAP_PARAM, AT_RISK_GAP), read(LATE_GAP_PARAM, LATE_GAP)
        return at_risk, max(late, at_risk)

    def _progress_values(self, today, gaps=(AT_RISK_GAP, LATE_GAP)):
        self.ensure_one()
        if not self.year or not 2000 <= self.year <= 2100:
            return {
                "start_value": 0.0, "current_value": 0.0, "expected_value": 0.0, "progress": 0.0,
                "expected_progress": 0.0, "status": "no_target", "progress_label": "", "expected_label": "",
                "value_q1": 0.0, "value_q2": 0.0, "value_q3": 0.0, "value_q4": 0.0,
            }
        year_start, year_end = date(self.year, 1, 1), date(self.year, 12, 31)
        as_of = min(today, year_end)
        start = self._start_value()
        automatic = self.tracking_mode == "auto" and self.indicator
        quarter_values = [0.0] * 4

        if today < year_start:
            current = expected = start
        else:
            if automatic:
                current = self._indicator_value(year_start, as_of)
                for index, (first, last) in enumerate(quarter_bounds(self.year)):
                    if first <= as_of:
                        quarter_values[index] = self._indicator_value(first, min(last, as_of))
            else:
                current = self.manual_value
            expected = self._expected_at(as_of, start)

        target = self.target or 0.0
        span = target - start
        if span > 0:
            progress = (current - start) / span * 100
            expected_progress = (expected - start) / span * 100
        else:
            progress = 100.0 if current >= target else 0.0
            expected_progress = 100.0

        if float_is_zero(target, precision_digits=2) and self.measure == "cumulative":
            status = "no_target"
        elif today < year_start:
            status = "upcoming"
        elif float_compare(current, target, precision_digits=2) >= 0:
            status = "done"
        elif today > year_end:
            status = "missed"
        else:
            at_risk_gap, late_gap = gaps
            gap = expected_progress - progress
            status = "late" if gap > late_gap else "at_risk" if gap > at_risk_gap else "on_track"

        return {
            "start_value": start,
            "current_value": current,
            "expected_value": expected,
            "progress": progress,
            "expected_progress": expected_progress,
            "status": status,
            "progress_label": f"{self._format_value(current)} / {self._format_value(target)}",
            "expected_label": (
                self._format_value(expected, whole=self._digits(target, start) == 0)
                if year_start <= today <= year_end else ""
            ),
            "value_q1": quarter_values[0],
            "value_q2": quarter_values[1],
            "value_q3": quarter_values[2],
            "value_q4": quarter_values[3],
        }

    # --- Affichage ------------------------------------------------------------------------

    def _format_value(self, value, whole=False):
        """Valeur lisible avec son unité : « 15 000 DH », « 1 recrutement »,
        « 4,6 ». `whole` arrondit à l'unité (valeur attendue d'un comptage)."""
        self.ensure_one()
        value = value or 0.0
        if self.is_monetary or whole:
            value = round(value)
        digits = 0 if float(round(value, 2)).is_integer() else 2
        text = formatLang(self.env, value, digits=digits)
        if self.is_monetary:
            currency = self.env.company.currency_id
            return f"{currency.symbol} {text}" if currency.position == "before" else f"{text} {currency.symbol}"
        unit = self.unit or ""
        # Singulier en français pour 0 et 1 : « 1 client », « 0 recrutement ».
        if abs(value) < 2 and len(unit) > 2 and unit.endswith("s") and not unit.endswith("ss"):
            unit = unit[:-1]
        return f"{text} {unit}" if unit else text

    def _caissecash_card_data(self):
        """Objectifs prêts à afficher (tableau de bord, Mon espace)."""
        today = fields.Date.context_today(self)
        statuses = dict(STATUSES)
        indicators = dict(self._fields["indicator"].selection)
        cards = []
        for rec in self:
            automatic = rec.tracking_mode == "auto" and rec.indicator
            quarters = []
            for index, ((first, last), target) in enumerate(zip(quarter_bounds(rec.year), rec._quarters())):
                realized = rec[f"value_q{index + 1}"]
                period = "past" if today > last else "current" if today >= first else "future"
                quarters.append({
                    "label": f"T{index + 1}",
                    "months": QUARTER_LABELS[index],
                    "period": period,
                    "target": rec._format_value(target),
                    "value": rec._format_value(realized) if automatic and period != "future" else "",
                    "reached": bool(
                        automatic and period != "future" and float_compare(realized, target, precision_digits=2) >= 0
                    ),
                })
            cards.append({
                "id": rec.id,
                "name": rec.name,
                "year": rec.year,
                "indicator": indicators.get(rec.indicator, "") if automatic else "Suivi à la main",
                "manual": rec.tracking_mode == "manual",
                "user": rec.user_id and {
                    "id": rec.user_id.id,
                    "name": rec.user_id.name,
                    "avatar": f"/web/image/res.users/{rec.user_id.id}/avatar_128",
                },
                "project": rec.project_id.name or "",
                "current": rec._format_value(rec.current_value),
                "target": rec._format_value(rec.target),
                "expected": rec.expected_label,
                "progress": round(rec.progress),
                "bar": max(0, min(100, round(rec.progress))),
                "marker": max(0, min(100, round(rec.expected_progress))),
                "status": rec.status,
                "status_label": statuses.get(rec.status, ""),
                "quarters": quarters,
            })
        return cards

    @api.model
    def _caissecash_summary(self, cards):
        """Compteurs par état pour un en-tête de section."""
        counts = {key: 0 for key, _label in STATUSES}
        for card in cards:
            counts[card["status"]] += 1
        return counts
