import random

from markupsafe import Markup

from odoo import api, fields, models

DONE = "1_done"
IN_PROGRESS = "01_in_progress"

BRAVO_MESSAGES = [
    "Bravo {name} ! 🎉",
    "Excellent travail, {name} ! 💪",
    "Tâche terminée, bien joué {name} ✅",
    "Beau travail, {name} ! 🔥",
    "Une de moins, merci {name} ! 🚀",
]


def first_name(user):
    return (user.name or "").split(" ")[0].capitalize()


class ProjectTask(models.Model):
    _inherit = "project.task"

    caissecash_done_date = fields.Datetime("Terminée le", copy=False, readonly=True, index=True)

    @api.model
    def _read_group_stage_ids(self, stages, domain):
        """« Mes tâches » mélange plusieurs projets : Odoo n'affiche alors que les
        colonnes non vides. On affiche toutes les étapes de ces projets, pour
        pouvoir glisser une tâche vers « En cours » ou « Terminé »."""
        stages = super()._read_group_stage_ids(stages, domain)
        if self.env.context.get("caissecash_my_tasks"):
            projects = self.search(domain).project_id
            stages = stages.search(
                ["|", ("id", "in", stages.ids), ("project_ids", "in", projects.ids)], order=stages._order
            )
        return stages

    def write(self, vals):
        if self.env.context.get("caissecash_skip_done_sync") or not {"state", "stage_id"} & vals.keys():
            return super().write(vals)
        done_before = set(self.filtered(lambda t: t.state == DONE).ids)
        res = super().write(vals)
        self._caissecash_sync_done(done_before, stage_moved="stage_id" in vals)
        return res

    def _caissecash_sync_done(self, done_before, stage_moved):
        """Garde l'étape « Terminé » (étape repliée) et l'état « Fait » cohérents,
        quelle que soit la façon dont la tâche a été bougée, puis fête les
        tâches qui viennent d'être terminées."""
        tasks = self.with_context(caissecash_skip_done_sync=True)
        for task in tasks.filtered("project_id"):
            done_stage = task.project_id.type_ids.filtered("fold")[:1]
            if stage_moved:
                if task.stage_id.fold and task.state != DONE:
                    task.state = DONE
                elif not task.stage_id.fold and task.state == DONE:
                    task.state = IN_PROGRESS
            elif task.state == DONE and done_stage and not task.stage_id.fold:
                task.stage_id = done_stage

        newly_done = tasks.filtered(lambda t: t.state == DONE and t.id not in done_before)
        newly_done.write({"caissecash_done_date": fields.Datetime.now()})
        tasks.filtered(lambda t: t.state != DONE and t.caissecash_done_date).write({"caissecash_done_date": False})
        if newly_done:
            newly_done._caissecash_celebrate()

    def _caissecash_celebrate(self):
        user = self.env.user
        bot = self.env.ref("base.partner_root")
        general = self.env.ref("mail.channel_all_employees", raise_if_not_found=False)
        for task in self:
            channel = task.project_id.caissecash_channel_id or general
            if channel:
                channel.sudo().message_post(
                    body=Markup("✅ <b>%s</b> a terminé la tâche « <a href='/odoo/project.task/%s'>%s</a> ». Bravo ! 🎉")
                    % (first_name(user), task.id, task.name),
                    author_id=bot.id,
                    message_type="comment",
                    subtype_xmlid="mail.mt_comment",
                )
        # Le bouton ✔ de « Mon espace » affiche lui-même l'animation.
        if not self.env.context.get("caissecash_celebrate_client"):
            user.partner_id._bus_send("caissecash_celebrate", {"message": self._caissecash_bravo_message()})

    def _caissecash_bravo_message(self):
        return random.choice(BRAVO_MESSAGES).format(name=first_name(self.env.user))

    def caissecash_action_done(self):
        """Bouton ✔ de « Mon espace » : termine la tâche et renvoie le message de félicitations."""
        self.with_context(caissecash_celebrate_client=True).write({"state": DONE})
        return {"message": self._caissecash_bravo_message()}
