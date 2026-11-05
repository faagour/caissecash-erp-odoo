/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { NavBar } from "@web/webclient/navbar/navbar";

patch(NavBar.prototype, {
    /**
     * Applications regroupées par rubrique (« Au quotidien », « Du prospect au
     * SAV »…), dans l'ordre des rubriques puis des applications.
     */
    caissecashAppGroups(apps) {
        const groups = new Map();
        for (const app of apps) {
            const label = app.caissecashSection || "";
            if (!groups.has(label)) {
                groups.set(label, { label, rank: app.caissecashSectionRank ?? 99, apps: [] });
            }
            groups.get(label).apps.push(app);
        }
        return [...groups.values()].sort((a, b) => a.rank - b.rank);
    },
});
