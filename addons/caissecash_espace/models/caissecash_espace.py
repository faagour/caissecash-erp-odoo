from collections import Counter
from datetime import datetime, time, timedelta

import pytz

from odoo import api, fields, models

from .project_task import DONE, first_name
from .res_config_settings import DEFAULT_QUOTES, QUOTES_PARAM, WEEKLY_GOAL_PARAM


def iso_utc(dt):
    return dt and dt.isoformat() + "Z"


# Guide « Bien démarrer », selon le rôle : (groupe, rôle, étapes). Chaque étape :
# (icône, titre, explication, action ouverte au clic). Le premier rôle trouvé
# l'emporte (la direction hérite de tous les autres).
ROLE_GUIDES = [
    ("caissecash_erp.group_direction", "Direction", [
        ("🎯", "Fixer les objectifs de l'année", "Toutes les cibles dans un seul tableau",
         "caissecash_erp.action_caissecash_objective_plan"),
        ("📊", "Suivre le tableau de bord", "Facturé, encaissé, dépenses et objectifs",
         "caissecash_erp.action_caissecash_dashboard_home"),
        ("👥", "Donner les accès à l'équipe", "Un rôle par personne : commercial, technicien…",
         "base.action_res_users"),
        ("⚙️", "Régler CaisseCash", "Objectif de l'équipe, parcours client, seuils de retard",
         "caissecash_espace.action_caissecash_settings"),
    ]),
    ("caissecash_erp.group_comptabilite", "Finance", [
        ("🧾", "Factures à encaisser", "Relancer les clients en retard de paiement",
         "account.action_move_out_invoice"),
        ("💸", "Enregistrer une dépense", "Ticket, facture, frais", "caissecash_erp.action_caissecash_expense"),
        ("📊", "Suivre le tableau de bord", "Facturé, encaissé et dépenses",
         "caissecash_erp.action_caissecash_dashboard_home"),
        ("🏆", "Voir les objectifs", "Où en est l'entreprise sur l'année", "caissecash_erp.action_caissecash_objective"),
    ]),
    ("caissecash_erp.group_commercial", "Commercial", [
        ("🎯", "Ajouter un prospect", "Chaque restaurant intéressé, même à peine", "crm.crm_lead_action_pipeline"),
        ("📝", "Préparer un devis", "À envoyer au client pour validation", "sale.action_quotations_with_onboarding"),
        ("🏪", "Suivre les établissements", "Les restaurants équipés et leur matériel",
         "caissecash_erp.action_caissecash_establishment"),
        ("🏆", "Voir mes objectifs", "Où j'en suis sur l'année", "caissecash_erp.action_caissecash_objective"),
    ]),
    ("caissecash_erp.group_stock", "Stock", [
        ("📦", "Réceptions et livraisons", "Ce qui entre et ce qui sort", "stock.action_picking_tree_ready"),
        ("🛒", "Commander du matériel", "Demandes de prix et achats fournisseurs", "purchase.purchase_rfq"),
        ("🔧", "Préparer les installations", "Le matériel à sortir pour chaque intervention",
         "caissecash_erp.action_caissecash_installation"),
    ]),
    ("caissecash_erp.group_technicien", "Technicien", [
        ("🔧", "Voir mes installations", "Matériel, checklist, puis « Marquer terminée »",
         "caissecash_erp.action_caissecash_installation"),
        ("🛠️", "Traiter mes tickets SAV", "Diagnostic, actions, solution", "caissecash_erp.action_caissecash_sav_ticket"),
        ("✅", "Terminer mes tâches", "Le bouton ✓ suffit", "caissecash_espace.action_caissecash_my_tasks"),
    ]),
    ("caissecash_erp.group_stagiaire", "Stagiaire", [
        ("🔧", "Voir mes installations", "Celles qui me sont confiées", "caissecash_erp.action_caissecash_installation"),
        ("🛠️", "Voir mes tickets SAV", "Ceux qui me sont confiés", "caissecash_erp.action_caissecash_sav_ticket"),
        ("✅", "Terminer mes tâches", "Le bouton ✓ suffit", "caissecash_espace.action_caissecash_my_tasks"),
    ]),
]
TEAM_GUIDE = ("Équipe", [
    ("✅", "Mes tâches", "Ce que j'ai à faire, le bouton ✓ quand c'est fait",
     "caissecash_espace.action_caissecash_my_tasks"),
    ("💬", "Discussion", "Les canaux de l'équipe", "mail.action_discuss"),
    ("📅", "Agenda", "Rendez-vous et réunions", "calendar.action_calendar_event"),
])

# Raccourcis « Créer » : (clé, icône, libellé, modèle, valeurs par défaut).
CREATE_SHORTCUTS = [
    ("prospect", "🎯", "Prospect", "crm.lead", {"default_type": "opportunity"}),
    ("installation", "🔧", "Installation", "caissecash.installation", {}),
    ("sav", "🛠️", "Ticket SAV", "caissecash.sav.ticket", {}),
    ("expense", "🧾", "Dépense", "caissecash.expense", {}),
]


class CaissecashEspace(models.AbstractModel):
    _name = "caissecash.espace"
    _description = "Données de la page d'accueil « Mon espace »"

    @api.model
    def get_home_data(self):
        user = self.env.user
        now = fields.Datetime.now()
        tz = pytz.timezone(user.tz or "Africa/Casablanca")
        today = now.replace(tzinfo=pytz.utc).astimezone(tz).date()
        week_start = (
            tz.localize(datetime.combine(today - timedelta(days=today.weekday()), time.min))
            .astimezone(pytz.utc)
            .replace(tzinfo=None)
        )

        Task = self.env["project.task"]
        open_domain = [("user_ids", "in", user.id), ("project_id", "!=", False), ("is_closed", "=", False)]
        tasks = Task.search(open_domain, order="date_deadline asc, priority desc, id desc", limit=6)

        partner = user.partner_id
        unread = sum(
            self.env["discuss.channel.member"].search([("partner_id", "=", partner.id)]).mapped("message_unread_counter")
        ) + self.env["mail.notification"].sudo().search_count(
            [("res_partner_id", "=", partner.id), ("is_read", "=", False), ("notification_type", "=", "inbox")]
        )

        # Équipe : employés liés à un utilisateur interne, hors compte administrateur.
        # sudo limité au nom, à la photo et à la présence du jour.
        admin = self.env.ref("base.user_admin")
        employees = self.env["hr.employee"].sudo().search(
            [("user_id", "!=", False), ("user_id.share", "=", False), ("user_id", "!=", admin.id)], order="name"
        )

        done_this_week = Task.sudo().search([("caissecash_done_date", ">=", week_start), ("state", "=", DONE)])
        done_by_user = Counter(uid for task in done_this_week for uid in task.user_ids.ids)
        leaderboard = sorted(
            (
                {
                    "user_id": e.user_id.id,
                    "name": first_name(e.user_id),
                    "avatar": f"/web/image/res.users/{e.user_id.id}/avatar_128",
                    "count": done_by_user[e.user_id.id],
                }
                for e in employees
            ),
            key=lambda row: (-row["count"], row["name"]),
        )

        employee = user.employee_id.sudo()
        attendance = employee and {
            "state": employee.attendance_state,
            "last_check_in": iso_utc(employee.last_check_in),
            "hours_previously_today": employee.hours_previously_today,
        }

        create_shortcuts = [
            {"key": key, "icon": icon, "label": label, "model": model, "context": context}
            for key, icon, label, model, context in CREATE_SHORTCUTS
            if model in self.env and self.env[model].has_access("create")
        ]

        # Étapes affichées (réglables par l'administrateur) que l'utilisateur peut consulter.
        journey = self.env["caissecash.journey.step"]._home_data()

        # Objectifs de l'année dont l'utilisateur est responsable.
        Objective = self.env["caissecash.objective"]
        my_objectives = (
            Objective.search([("user_id", "=", user.id), ("year", "=", today.year)])._caissecash_card_data()
            if Objective.has_access("read") else []
        )

        return {
            "user": {"id": user.id, "first_name": first_name(user), "lang": user.lang},
            "attendance": attendance or False,
            "tasks": [
                {
                    "id": t.id,
                    "name": t.name,
                    "project": t.project_id.name,
                    "deadline": iso_utc(t.date_deadline),
                    "overdue": bool(t.date_deadline and t.date_deadline < now),
                    "priority": t.priority == "1",
                }
                for t in tasks
            ],
            "counts": {
                "tasks": Task.search_count(open_domain),
                "overdue": Task.search_count(open_domain + [("date_deadline", "<", now)]),
                "unread": unread,
                "done_week": done_by_user[user.id],
            },
            "team": [
                {
                    "id": e.id,
                    "name": first_name(e),
                    "avatar": f"/web/image/hr.employee.public/{e.id}/avatar_128",
                    "job": e.job_title or "",
                    "present": e.attendance_state == "checked_in",
                }
                for e in employees
            ],
            "leaderboard": leaderboard,
            "team_done": len(done_this_week),
            "weekly_goal": self._weekly_goal(),
            "create": create_shortcuts,
            "journey": journey,
            "objectives": {
                "year": today.year,
                "items": my_objectives,
                "update_view_id": self.env.ref("caissecash_erp.view_caissecash_objective_update_form").id,
            },
            "quotes": self._quotes(),
            "guide": self._guide(user),
        }

    @api.model
    def _weekly_goal(self):
        try:
            return max(1, int(self.env["ir.config_parameter"].sudo().get_param(WEEKLY_GOAL_PARAM, 15)))
        except (TypeError, ValueError):
            return 15

    @api.model
    def _quotes(self):
        text = self.env["ir.config_parameter"].sudo().get_param(QUOTES_PARAM) or ""
        quotes = [line.strip() for line in text.splitlines() if line.strip()]
        return quotes or DEFAULT_QUOTES

    @api.model
    def _guide(self, user):
        """Guide « Bien démarrer » du rôle de l'utilisateur, limité aux écrans
        qu'il a le droit d'ouvrir."""
        role, steps = next(
            ((role, steps) for group, role, steps in ROLE_GUIDES if user.has_group(group)), TEAM_GUIDE
        )
        visible = []
        for icon, title, hint, xmlid in steps:
            action = self.env.ref(xmlid, raise_if_not_found=False)
            if not action:
                continue
            model = action._name == "ir.actions.act_window" and action.sudo().res_model
            if model and (model not in self.env or not self.env[model].has_access("read")):
                continue
            visible.append({"icon": icon, "title": title, "hint": hint, "action": xmlid})
        return {"role": role, "steps": visible, "hidden": user.caissecash_hide_guide}

    @api.model
    def set_guide_hidden(self, hidden=True):
        """Masque ou réaffiche le guide « Bien démarrer » de l'utilisateur."""
        self.env.user.sudo().caissecash_hide_guide = bool(hidden)
        return True
