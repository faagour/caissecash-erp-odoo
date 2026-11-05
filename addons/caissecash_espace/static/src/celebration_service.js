/** @odoo-module **/

import { registry } from "@web/core/registry";

export const BRAVO_IMG = "/caissecash_espace/static/src/img/bravo.svg";

// Animation « Bravo » quand le serveur signale une tâche terminée
// (glisser dans « Terminé », case « Fait »… depuis n'importe quel écran).
registry.category("services").add("caissecash_celebration", {
    dependencies: ["bus_service", "effect"],
    start(env, { bus_service, effect }) {
        bus_service.subscribe("caissecash_celebrate", ({ message }) => {
            effect.add({ type: "rainbow_man", message, img_url: BRAVO_IMG, fadeout: "medium" });
        });
    },
});
