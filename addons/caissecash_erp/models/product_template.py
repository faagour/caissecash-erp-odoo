from odoo import Command, api, fields, models
from odoo.exceptions import UserError

# Les quatre sortes d'articles CaisseCash. Chacune fixe les réglages techniques
# d'Odoo (type, suivi du stock, numéro de série) pour que personne n'ait à les
# connaître : on choisit « Matériel », Odoo suit chaque unité par son numéro.
KINDS = [
    ("materiel", "Matériel avec n° de série"),
    ("consommable", "Consommable"),
    ("logiciel", "Logiciel / abonnement"),
    ("pack", "Pack"),
]
KIND_VALUES = {
    "materiel": {"type": "consu", "is_storable": True, "tracking": "serial"},
    "consommable": {"type": "consu", "is_storable": True, "tracking": "none"},
    "logiciel": {"type": "service", "is_storable": False, "tracking": "none"},
    # Un pack est une « nomenclature kit » : il n'a pas de stock propre, ce sont
    # ses composants qui sortent du stock.
    "pack": {"type": "consu", "is_storable": False, "tracking": "none"},
}
TECHNICAL_FIELDS = {"type", "is_storable", "tracking"}


class ProductTemplate(models.Model):
    _inherit = "product.template"

    caissecash_kind = fields.Selection(
        KINDS, string="Sorte d'article", tracking=True,
        help="Matériel : suivi unité par unité (garantie, SAV). Consommable : compté en "
             "quantité. Logiciel / abonnement : pas de stock. Pack : plusieurs articles "
             "vendus ensemble.",
    )
    caissecash_min_qty = fields.Float(
        "Seuil d'alerte", digits="Product Unit",
        compute="_compute_caissecash_min_qty", inverse="_inverse_caissecash_min_qty",
        help="Quand le stock descend à ce niveau, l'article apparaît dans « À racheter ». "
             "0 = pas d'alerte.",
    )
    caissecash_vendor_id = fields.Many2one(
        "res.partner", string="Fournisseur habituel",
        compute="_compute_caissecash_vendor_id", inverse="_inverse_caissecash_vendor_id",
    )
    caissecash_to_restock = fields.Boolean(
        "À racheter", compute="_compute_caissecash_to_restock", search="_search_caissecash_to_restock",
    )

    # --- Sorte d'article <-> réglages techniques ---------------------------------

    def _caissecash_guess_kind(self):
        self.ensure_one()
        if self.type == "service":
            return "logiciel"
        if self.type == "combo" or self.is_kits:
            return "pack"
        if self.tracking != "none":
            return "materiel"
        return "consommable"

    @api.onchange("caissecash_kind")
    def _onchange_caissecash_kind(self):
        if self.caissecash_kind:
            self.update(KIND_VALUES[self.caissecash_kind])

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("caissecash_kind"):
                for field, value in KIND_VALUES[vals["caissecash_kind"]].items():
                    vals.setdefault(field, value)
        # Le seuil d'alerte s'applique à la variante, qui n'existe qu'après la création.
        minimums = [vals.pop("caissecash_min_qty", 0) for vals in vals_list]
        templates = super().create(vals_list)
        for template, vals, minimum in zip(templates, vals_list, minimums):
            if not vals.get("caissecash_kind"):
                template.with_context(caissecash_kind_sync=False).caissecash_kind = template._caissecash_guess_kind()
            if minimum:
                template.caissecash_min_qty = minimum
        return templates

    def write(self, vals):
        if vals.get("caissecash_kind") and self.env.context.get("caissecash_kind_sync", True):
            vals = {**KIND_VALUES[vals["caissecash_kind"]], **vals}
        res = super().write(vals)
        # Réglage technique modifié depuis la fiche complète d'Odoo : la sorte suit.
        if TECHNICAL_FIELDS & set(vals) and "caissecash_kind" not in vals:
            for template in self:
                kind = template._caissecash_guess_kind()
                if template.caissecash_kind != kind:
                    template.with_context(caissecash_kind_sync=False).caissecash_kind = kind
        return res

    # --- Seuil d'alerte (règle de réapprovisionnement manuelle) -------------------

    def _caissecash_orderpoints(self, every_product=False):
        domain = [("company_id", "=", self.env.company.id)]
        if not every_product:
            domain.append(("product_id.product_tmpl_id", "in", self.ids))
        return self.env["stock.warehouse.orderpoint"].sudo().search(domain, order="id")

    @api.depends_context("company")
    def _compute_caissecash_min_qty(self):
        by_template = {}
        for orderpoint in self.filtered("id")._caissecash_orderpoints():
            by_template.setdefault(orderpoint.product_id.product_tmpl_id.id, orderpoint.product_min_qty)
        for template in self:
            template.caissecash_min_qty = by_template.get(template._origin.id, 0.0)

    def _inverse_caissecash_min_qty(self):
        warehouse = self.env["stock.warehouse"].search([("company_id", "=", self.env.company.id)], limit=1)
        Orderpoint = self.env["stock.warehouse.orderpoint"].sudo()
        for template in self:
            product = template.product_variant_id
            if not product or not template.is_storable or not warehouse:
                continue
            orderpoint = Orderpoint.search(
                [("product_id", "=", product.id), ("location_id", "=", warehouse.lot_stock_id.id)], limit=1,
            )
            minimum = template.caissecash_min_qty
            if minimum <= 0:
                orderpoint.unlink()
            elif orderpoint:
                orderpoint.write({"product_min_qty": minimum, "product_max_qty": max(minimum, orderpoint.product_max_qty)})
            else:
                Orderpoint.create({
                    "product_id": product.id,
                    "warehouse_id": warehouse.id,
                    "location_id": warehouse.lot_stock_id.id,
                    "product_min_qty": minimum,
                    "product_max_qty": minimum,
                    "trigger": "manual",
                })

    @api.depends("qty_available", "caissecash_min_qty")
    def _compute_caissecash_to_restock(self):
        for template in self:
            template.caissecash_to_restock = (
                template.caissecash_min_qty > 0 and template.qty_available <= template.caissecash_min_qty
            )

    def _search_caissecash_to_restock(self, operator, value):
        if operator in ("=", "!="):
            operator, value = ("in" if operator == "=" else "not in"), [value]
        if operator not in ("in", "not in"):
            return NotImplemented
        values = {bool(v) for v in value}
        if operator == "not in":
            values = {True, False} - values
        if values == {True, False}:
            return []
        if not values:
            return [("id", "in", [])]
        templates = self.browse(self._caissecash_orderpoints(every_product=True).product_id.product_tmpl_id.ids)
        ids = templates.filtered("caissecash_to_restock").ids
        return [("id", "in" if True in values else "not in", ids)]

    # --- Fournisseur habituel -----------------------------------------------------

    @api.depends("seller_ids.partner_id", "seller_ids.sequence")
    def _compute_caissecash_vendor_id(self):
        for template in self:
            template.caissecash_vendor_id = template.seller_ids[:1].partner_id

    def _inverse_caissecash_vendor_id(self):
        for template in self:
            seller = template.seller_ids[:1]
            if not template.caissecash_vendor_id:
                continue
            if seller:
                seller.sudo().partner_id = template.caissecash_vendor_id
            else:
                template.sudo().seller_ids = [Command.create({"partner_id": template.caissecash_vendor_id.id})]

    # --- Boutons de la fiche simplifiée ------------------------------------------

    def action_caissecash_full_form(self):
        """Ouvre la fiche Odoo complète (tous les réglages)."""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": self.display_name,
            "res_model": "product.template",
            "res_id": self.id,
            "views": [(self.env.ref("product.product_template_form_view").id, "form")],
            "target": "current",
        }

    def action_caissecash_pack(self):
        """Ouvre la composition du pack (nomenclature kit), en la créant au besoin."""
        self.ensure_one()
        bom = self.env["mrp.bom"].search([("product_tmpl_id", "=", self.id), ("type", "=", "phantom")], limit=1)
        return {
            "type": "ir.actions.act_window",
            "name": f"Composition de « {self.name} »",
            "res_model": "mrp.bom",
            "res_id": bom.id,
            "views": [(self.env.ref("caissecash_erp.view_caissecash_pack_form").id, "form")],
            "target": "new",
            "context": {"default_product_tmpl_id": self.id, "default_type": "phantom", "default_product_qty": 1},
        }

    def action_caissecash_adjust(self):
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id("caissecash_erp.action_caissecash_stock_adjust")
        action["context"] = {"default_product_id": self.product_variant_id.id}
        return action

    def action_caissecash_order(self):
        """« Commander » : ajoute l'article à la demande de prix en cours du
        fournisseur habituel (ou en crée une) pour revenir au-dessus du seuil."""
        self.ensure_one()
        if not self.caissecash_vendor_id:
            raise UserError(f"Indiquez d'abord le fournisseur habituel de « {self.name} » sur sa fiche.")
        orderpoint = self._caissecash_orderpoints()[:1]
        target = max(orderpoint.product_max_qty, self.caissecash_min_qty)
        quantity = max(target - self.qty_available, 1.0)
        Order = self.env["purchase.order"]
        order = Order.search(
            [("partner_id", "=", self.caissecash_vendor_id.id), ("state", "=", "draft"),
             ("company_id", "=", self.env.company.id)],
            order="id desc", limit=1,
        ) or Order.create({"partner_id": self.caissecash_vendor_id.id})
        line = order.order_line.filtered(lambda l: l.product_id == self.product_variant_id)[:1]
        if line:
            line.product_qty = max(line.product_qty, quantity)
        else:
            order.order_line = [Command.create({"product_id": self.product_variant_id.id, "product_qty": quantity})]
        return {
            "type": "ir.actions.act_window",
            "name": "Commande fournisseur",
            "res_model": "purchase.order",
            "res_id": order.id,
            "views": [(False, "form")],
            "target": "current",
        }
