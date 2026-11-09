/** @odoo-module **/

import { Component, onMounted, onWillStart, onWillUnmount, useRef, useState } from "@odoo/owl";
import { loadBundle } from "@web/core/assets";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

// Facturé = bleu, Dépenses = orange partout sur la page (couleurs validées,
// y compris pour les daltoniens) ; la valeur de l'entreprise en marine.
const COLORS = {
    invoiced: "#2a78d6",
    expenses: "#eb6834",
    value: "#1d3a8a",
    valueFill: "rgba(29, 58, 138, 0.08)",
    grid: "#e1e0d9",
    axis: "#c3c2b7",
    muted: "#898781",
};

const PERIODS = [
    { key: "all", label: "Depuis le début" },
    { key: "year", label: "Cette année" },
    { key: "month", label: "Ce mois" },
];

const numberFormat = new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 0 });
const compactFormat = new Intl.NumberFormat("fr-FR", { notation: "compact", maximumFractionDigits: 1 });

export class CaissecashDashboard extends Component {
    static template = "caissecash_erp.Dashboard";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.periods = PERIODS;
        this.colors = COLORS;
        this.state = useState({ period: "all", data: null, loading: false });
        this.barRef = useRef("barChart");
        this.lineRef = useRef("lineChart");
        this.charts = [];

        onWillStart(async () => {
            await loadBundle("web.chartjs_lib");
            await this.load();
        });
        onMounted(() => this.renderCharts());
        onWillUnmount(() => this.destroyCharts());
    }

    async load() {
        this.state.loading = true;
        try {
            this.state.data = await this.orm.call("caissecash.dashboard", "get_dashboard_data", [], {
                period: this.state.period,
            });
        } finally {
            this.state.loading = false;
        }
    }

    async setPeriod(key) {
        if (key !== this.state.period) {
            this.state.period = key;
            await this.load();
        }
    }

    async refresh() {
        await this.load();
        this.renderCharts();
    }

    // --- Formatage -----------------------------------------------------------

    money(value) {
        const { symbol, position } = this.state.data.currency;
        const amount = numberFormat.format(Math.round(value || 0)).replace("-", "−");
        return position === "before" ? `${symbol} ${amount}` : `${amount} ${symbol}`;
    }

    shortDate(iso) {
        return iso ? new Date(iso).toLocaleDateString("fr-FR", { day: "numeric", month: "short" }) : "";
    }

    percent(value) {
        return Math.round(value || 0);
    }

    get periodLabel() {
        return PERIODS.find((p) => p.key === this.state.period).label;
    }

    get kpis() {
        return this.state.data.kpis;
    }

    get paidPercent() {
        const { invoiced, paid } = this.kpis;
        return invoiced ? Math.round((paid / invoiced) * 100) : 0;
    }

    get objectivesHint() {
        const counts = this.state.data.objectives.counts;
        const parts = [];
        for (const [key, singular, plural] of [
            ["done", "atteint", "atteints"],
            ["on_track", "dans les temps", "dans les temps"],
            ["at_risk", "en léger retard", "en léger retard"],
            ["late", "en retard", "en retard"],
            ["missed", "non atteint", "non atteints"],
            ["upcoming", "à venir", "à venir"],
            ["no_target", "sans cible", "sans cible"],
        ]) {
            if (counts[key]) {
                parts.push(`${counts[key]} ${counts[key] > 1 ? plural : singular}`);
            }
        }
        return parts.join(" · ");
    }

    categoryWidth(category) {
        const max = Math.max(...this.state.data.categories.map((c) => c.amount), 1);
        return Math.max(2, Math.round((category.amount / max) * 100));
    }

    // --- Graphiques ------------------------------------------------------------

    destroyCharts() {
        this.charts.forEach((chart) => chart.destroy());
        this.charts = [];
    }

    renderCharts() {
        this.destroyCharts();
        const monthly = this.state.data.monthly;
        const labels = monthly.map((m) =>
            new Date(m.month).toLocaleDateString("fr-FR", { month: "short", year: "2-digit" })
        );
        const yAxis = {
            grid: { color: COLORS.grid },
            border: { display: false },
            ticks: { color: COLORS.muted, maxTicksLimit: 5, callback: (v) => compactFormat.format(v) },
        };
        // Mois à l'horizontale ; Chart.js en saute un sur deux si la place manque (téléphone).
        const xAxis = {
            grid: { display: false },
            border: { color: COLORS.axis },
            ticks: { color: COLORS.muted, maxRotation: 0, autoSkip: true, autoSkipPadding: 8 },
        };
        const tooltip = { callbacks: { label: (ctx) => ` ${ctx.dataset.label} : ${this.money(ctx.parsed.y)}` } };

        this.charts.push(
            new Chart(this.barRef.el, {
                type: "bar",
                data: {
                    labels,
                    datasets: [
                        { label: "Facturé", data: monthly.map((m) => m.invoiced), backgroundColor: COLORS.invoiced },
                        { label: "Dépenses", data: monthly.map((m) => m.expenses), backgroundColor: COLORS.expenses },
                    ].map((dataset) => ({
                        ...dataset,
                        borderRadius: 4,
                        maxBarThickness: 16,
                        categoryPercentage: 0.7,
                        barPercentage: 0.88,
                    })),
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    interaction: { mode: "index", intersect: false },
                    plugins: { legend: { display: false }, tooltip },
                    scales: { x: xAxis, y: { ...yAxis, beginAtZero: true } },
                },
            }),
            new Chart(this.lineRef.el, {
                type: "line",
                data: {
                    labels,
                    datasets: [
                        {
                            label: "Valeur",
                            data: monthly.map((m) => m.value),
                            borderColor: COLORS.value,
                            backgroundColor: COLORS.valueFill,
                            fill: "origin",
                            borderWidth: 2,
                            tension: 0,
                            pointRadius: 0,
                            pointHoverRadius: 5,
                            pointHitRadius: 14,
                            pointBackgroundColor: COLORS.value,
                        },
                    ],
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    interaction: { mode: "index", intersect: false },
                    plugins: { legend: { display: false }, tooltip },
                    scales: {
                        x: xAxis,
                        // Ligne du zéro plus marquée : au-dessus = l'entreprise a gagné plus qu'elle n'a dépensé.
                        y: { ...yAxis, grid: { color: (ctx) => (ctx.tick.value === 0 ? COLORS.axis : COLORS.grid) } },
                    },
                },
            })
        );
    }

    // --- Navigation ------------------------------------------------------------

    async openGraph(method) {
        const action = await this.orm.call("caissecash.dashboard", method, [[]]);
        this.action.doAction(action);
    }

    openAction(xmlid) {
        this.action.doAction(xmlid);
    }

    openObjectives() {
        this.action.doAction("caissecash_erp.action_caissecash_objective");
    }

    planObjectives() {
        this.action.doAction("caissecash_erp.action_caissecash_objective_plan", {
            onClose: () => this.refresh(),
        });
    }

    openRecord(model, id) {
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: model,
            res_id: id,
            views: [[false, "form"]],
            target: "current",
        });
    }
}

registry.category("actions").add("caissecash_erp.dashboard", CaissecashDashboard);
