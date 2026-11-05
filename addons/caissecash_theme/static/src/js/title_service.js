/** @odoo-module **/

import { registry } from "@web/core/registry";

// "CaisseCash - <écran>" dans l'onglet du navigateur, au lieu de "Odoo"
// quand aucun écran n'a encore de titre.
registry.category("services").add("caissecash_title", {
    dependencies: ["title"],
    start(env, { title }) {
        title.setParts({ brand: "CaisseCash" });
    },
});
