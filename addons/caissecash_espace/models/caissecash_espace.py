from collections import Counter
from datetime import datetime, time, timedelta

import pytz

from odoo import api, fields, models

from .project_task import DONE, first_name


def iso_utc(dt):
    return dt and dt.isoformat() + "Z"


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

        can_expense = "caissecash.expense" in self.env and self.env["caissecash.expense"].has_access("create")

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
            "weekly_goal": int(self.env["ir.config_parameter"].sudo().get_param("caissecash_espace.weekly_goal", 15)),
            "can_expense": can_expense,
        }
