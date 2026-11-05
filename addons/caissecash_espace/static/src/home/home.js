/** @odoo-module **/

import { Component, onWillStart, onWillUnmount, useState } from "@odoo/owl";
import { rpc } from "@web/core/network/rpc";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { BRAVO_IMG } from "../celebration_service";

const QUOTES = [
    "Le travail bien fait parle de lui-même. 💪",
    "Petit à petit, l'oiseau fait son nid. 🐦",
    "Chaque client installé est une victoire. 🏆",
    "Seul on va plus vite, ensemble on va plus loin. 🤝",
    "Un pas de plus chaque jour. ⭐",
    "La qualité, c'est notre meilleure publicité. 🚀",
    "Les détails font la différence. 🎯",
];

function greeting(date) {
    const hour = date.getHours();
    if (hour >= 5 && hour < 18) {
        return "Bonjour";
    }
    return "Bonsoir";
}

function formatDuration(hours) {
    const minutes = Math.max(0, Math.round(hours * 60));
    const h = Math.floor(minutes / 60);
    const m = minutes % 60;
    return h ? `${h} h ${String(m).padStart(2, "0")}` : `${m} min`;
}

export class CaissecashHome extends Component {
    static template = "caissecash_espace.Home";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.effect = useService("effect");
        this.notification = useService("notification");
        this.state = useState({ data: null, now: new Date(), busy: false });

        onWillStart(() => this.load());
        // Rafraîchit le compteur de temps de travail.
        const timer = setInterval(() => (this.state.now = new Date()), 30000);
        onWillUnmount(() => clearInterval(timer));
    }

    async load() {
        this.state.data = await this.orm.call("caissecash.espace", "get_home_data", []);
        this.state.now = new Date();
    }

    get locale() {
        return (this.state.data?.user.lang || "fr_FR").replace("_", "-");
    }

    get greeting() {
        return greeting(this.state.now);
    }

    get todayLabel() {
        return this.state.now.toLocaleDateString(this.locale, { weekday: "long", day: "numeric", month: "long" });
    }

    get quote() {
        const start = new Date(this.state.now.getFullYear(), 0, 0);
        const dayOfYear = Math.floor((this.state.now - start) / 86400000);
        return QUOTES[dayOfYear % QUOTES.length];
    }

    get attendance() {
        return this.state.data.attendance;
    }

    get checkedIn() {
        return this.attendance && this.attendance.state === "checked_in";
    }

    get workedToday() {
        const att = this.attendance;
        let hours = att.hours_previously_today || 0;
        if (this.checkedIn && att.last_check_in) {
            hours += (this.state.now - new Date(att.last_check_in)) / 3600000;
        }
        return formatDuration(hours);
    }

    get presentCount() {
        return this.state.data.team.filter((member) => member.present).length;
    }

    get goalPercent() {
        const { team_done, weekly_goal } = this.state.data;
        return weekly_goal ? Math.min(100, Math.round((team_done / weekly_goal) * 100)) : 0;
    }

    barWidth(row) {
        const maxDone = Math.max(1, ...this.state.data.leaderboard.map((r) => r.count));
        return Math.round((row.count / maxDone) * 100);
    }

    medal(count) {
        // Même score, même médaille.
        const scores = [...new Set(this.state.data.leaderboard.map((row) => row.count))].filter(Boolean);
        return count ? ["🥇", "🥈", "🥉"][scores.indexOf(count)] || "" : "";
    }

    deadlineLabel(task) {
        return new Date(task.deadline).toLocaleDateString(this.locale, { day: "numeric", month: "short" });
    }

    async toggleAttendance() {
        if (this.state.busy) {
            return;
        }
        this.state.busy = true;
        const wasIn = this.checkedIn;
        try {
            await rpc("/hr_attendance/systray_check_in_out", {});
            await this.load();
            this.notification.add(wasIn ? "Sortie enregistrée. Bonne soirée ! 🌙" : "Entrée enregistrée. Bonne journée ! 💪", {
                type: "success",
            });
        } finally {
            this.state.busy = false;
        }
    }

    async markDone(task) {
        const { message } = await this.orm.call("project.task", "caissecash_action_done", [[task.id]]);
        this.effect.add({ type: "rainbow_man", message, img_url: BRAVO_IMG, fadeout: "medium" });
        await this.load();
    }

    openTask(task) {
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "project.task",
            res_id: task.id,
            views: [[false, "form"]],
            target: "current",
        });
    }

    openMyTasks() {
        this.action.doAction("caissecash_espace.action_caissecash_my_tasks");
    }

    openDiscuss() {
        this.action.doAction("mail.action_discuss");
    }

    newTask() {
        this.action.doAction(
            {
                type: "ir.actions.act_window",
                name: "Nouvelle tâche",
                res_model: "project.task",
                views: [[false, "form"]],
                target: "new",
                context: { default_user_ids: [this.state.data.user.id] },
            },
            { onClose: () => this.load() }
        );
    }

    newExpense() {
        this.action.doAction({
            type: "ir.actions.act_window",
            name: "Nouvelle dépense",
            res_model: "caissecash.expense",
            views: [[false, "form"]],
            target: "current",
        });
    }
}

registry.category("actions").add("caissecash_espace.home", CaissecashHome);
