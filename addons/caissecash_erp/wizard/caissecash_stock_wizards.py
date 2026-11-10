"""Mouvements de stock simplifiés : entrée, sortie, correction.

Chaque assistant crée et valide un vrai mouvement Odoo (réception, livraison ou
ajustement d'inventaire) : l'historique, la valorisation et les commandes
fournisseur/client restent justes, sans que l'utilisateur ait à passer par les
écrans détaillés (opérations, lignes détaillées, numéros de série…)."""
import re

from odoo import Command, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import float_compare, float_is_zero

ADJUST_REASONS = [
    ("comptage", "Comptage (inventaire)"),
    ("casse", "Casse"),
    ("perte", "Perte ou vol"),
    ("autre", "Autre"),
]


def split_serials(text):
    """Un numéro par ligne, ou séparés par virgule / point-virgule ; sans doublon."""
    seen = []
    for serial in re.split(r"[\n,;]+", text or ""):
        serial = serial.strip()
        if serial and serial not in seen:
            seen.append(serial)
    return seen


def qty(value):
    return f"{value:g}"


class CaissecashStockMixin(models.AbstractModel):
    _name = "caissecash.stock.mixin"
    _description = "Outils communs aux mouvements de stock simplifiés"

    def _warehouse(self):
        warehouse = self.env["stock.warehouse"].search([("company_id", "=", self.env.company.id)], limit=1)
        if not warehouse:
            raise UserError("Aucun entrepôt n'est configuré pour cette société.")
        return warehouse

    def _fill_from_picking(self, picking):
        """Lignes proposées à partir d'une réception / livraison en attente."""
        lines = [Command.clear()]
        for move in picking.move_ids.filtered(lambda m: m.state not in ("done", "cancel")):
            lines.append(Command.create({"product_id": move.product_id.id, "quantity": move.product_uom_qty}))
        return lines

    def _prepare_picking(self, picking_type, partner, origin):
        picking = self.picking_id
        if not picking:
            picking = self.env["stock.picking"].create({
                "picking_type_id": picking_type.id,
                "partner_id": partner.id,
                "origin": origin or False,
            })
        return picking

    def _moves_for(self, picking, quantities):
        """{article: quantité} -> {article: mouvement du bon}, en reprenant le
        mouvement attendu de l'article ou en l'ajoutant au bon."""
        moves = {}
        new_moves = self.env["stock.move"]
        for product, quantity in quantities.items():
            move = picking.move_ids.filtered(
                lambda m: m.product_id == product and m.state not in ("done", "cancel")
            )[:1]
            if not move:
                move = self.env["stock.move"].create({
                    "picking_id": picking.id,
                    "product_id": product.id,
                    "product_uom": product.uom_id.id,
                    "product_uom_qty": quantity,
                    "location_id": picking.location_id.id,
                    "location_dest_id": picking.location_dest_id.id,
                })
                new_moves |= move
            moves[product] = move
        if picking.state == "draft":
            picking.action_confirm()
        elif new_moves:
            new_moves._action_confirm()
        return moves

    def _validate(self, picking, prepared_moves):
        """Ne garde que les quantités saisies, puis valide le bon. Ce qui était
        attendu et n'a pas été traité reste attendu (reliquat)."""
        for move in picking.move_ids.filtered(lambda m: m.state not in ("done", "cancel")):
            if move not in prepared_moves:
                move.move_line_ids.unlink()
                move.picked = False
        picking.with_context(skip_backorder=True, skip_sms=True).button_validate()
        if picking.state != "done":
            raise UserError(f"Le bon {picking.name} n'a pas pu être validé.")
        return picking

    def _done_notification(self, title, message):
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": title,
                "message": message,
                "type": "success",
                "sticky": False,
                "next": {"type": "ir.actions.act_window_close"},
            },
        }


# --- Entrée de stock ---------------------------------------------------------------

class CaissecashStockEntry(models.TransientModel):
    _name = "caissecash.stock.entry"
    _inherit = "caissecash.stock.mixin"
    _description = "Entrée de stock"

    picking_id = fields.Many2one(
        "stock.picking", string="Commande fournisseur attendue",
        domain="[('picking_type_code', '=', 'incoming'), ('state', 'in', ('confirmed', 'waiting', 'assigned'))]",
        help="Si le matériel arrive d'une commande fournisseur, choisissez-la : ses articles sont repris.",
    )
    has_pending = fields.Boolean(compute="_compute_has_pending")
    partner_id = fields.Many2one("res.partner", string="Fournisseur")
    reference = fields.Char("Référence", help="N° du bon de livraison ou de la facture du fournisseur.")
    line_ids = fields.One2many("caissecash.stock.entry.line", "wizard_id", string="Articles reçus")

    def _compute_has_pending(self):
        pending = bool(self.env["stock.picking"].search_count([
            ("picking_type_code", "=", "incoming"), ("state", "in", ("confirmed", "waiting", "assigned")),
        ], limit=1))
        for wizard in self:
            wizard.has_pending = pending

    @api.onchange("picking_id")
    def _onchange_picking_id(self):
        if self.picking_id:
            self.partner_id = self.picking_id.partner_id
            self.reference = self.reference or self.picking_id.origin
            self.line_ids = self._fill_from_picking(self.picking_id)

    def _next_serial(self, product, taken):
        """Numéro automatique pour un appareil dont le numéro n'a pas été saisi."""
        Lot = self.env["stock.lot"]
        candidate = Lot._get_next_serial(self.env.company, product)
        while not candidate or candidate in taken or Lot.search_count(
            [("product_id", "=", product.id), ("name", "=", candidate)], limit=1,
        ):
            sequence = product.lot_sequence_id
            candidate = sequence.next_by_id() if sequence else self.env["ir.sequence"].next_by_code("stock.lot.serial")
        return candidate

    def action_validate(self):
        self.ensure_one()
        lines = self.line_ids.filtered("product_id")
        if not lines:
            raise UserError("Ajoutez au moins un article reçu.")
        Lot = self.env["stock.lot"]
        # Une entrée par article, même s'il a été saisi sur plusieurs lignes.
        plans = {}
        for line in lines:
            product = line.product_id
            if float_compare(line.quantity, 0, precision_rounding=product.uom_id.rounding) <= 0:
                raise UserError(f"Indiquez la quantité reçue pour « {product.display_name} ».")
            plan = plans.setdefault(product, {"quantity": 0.0, "serials": []})
            plan["quantity"] += line.quantity
            if product.tracking == "serial":
                serials = split_serials(line.serial_numbers)
                missing = int(line.quantity) - len(serials)
                if line.quantity != int(line.quantity) or missing < 0:
                    raise UserError(
                        f"« {product.display_name} » : {len(serials)} numéro(s) de série pour une quantité de "
                        f"{qty(line.quantity)}. Il faut un numéro par appareil."
                    )
                doubles = set(serials) & set(plan["serials"])
                if doubles:
                    raise UserError(f"Le numéro de série {sorted(doubles)[0]} est saisi deux fois.")
                plan["serials"] += serials
                # Numéros non saisis : Odoo les génère (comme un étiquetage interne).
                for _i in range(missing):
                    plan["serials"].append(self._next_serial(product, plan["serials"]))
        for product, plan in plans.items():
            for serial in plan["serials"]:
                lot = Lot.search([("product_id", "=", product.id), ("name", "=", serial)], limit=1)
                if lot and lot.product_qty > 0:
                    raise UserError(f"Le numéro de série {serial} de « {product.display_name} » est déjà en stock.")

        warehouse = self._warehouse()
        picking = self._prepare_picking(warehouse.in_type_id, self.partner_id, self.reference)
        if self.partner_id and not picking.partner_id:
            picking.partner_id = self.partner_id
        moves = self._moves_for(picking, {product: plan["quantity"] for product, plan in plans.items()})

        for product, plan in plans.items():
            move = moves[product]
            move.move_line_ids.unlink()
            base = {
                "move_id": move.id,
                "picking_id": picking.id,
                "product_id": product.id,
                "product_uom_id": move.product_uom.id,
                "location_id": move.location_id.id,
                "location_dest_id": move.location_dest_id.id,
                "picked": True,
            }
            if plan["serials"]:
                vals = []
                for serial in plan["serials"]:
                    lot = Lot.search([("product_id", "=", product.id), ("name", "=", serial)], limit=1)
                    vals.append({**base, "quantity": 1, **({"lot_id": lot.id} if lot else {"lot_name": serial})})
                self.env["stock.move.line"].create(vals)
            else:
                self.env["stock.move.line"].create({**base, "quantity": plan["quantity"]})
            move.picked = True
        self._validate(picking, self.env["stock.move"].union(*moves.values()))

        total = sum(lines.mapped("quantity"))
        return self._done_notification(
            "Entrée enregistrée",
            f"{qty(total)} article(s) ajouté(s) au stock ({picking.name}).",
        )


class CaissecashStockEntryLine(models.TransientModel):
    _name = "caissecash.stock.entry.line"
    _description = "Article d'une entrée de stock"

    wizard_id = fields.Many2one("caissecash.stock.entry", required=True, ondelete="cascade")
    product_id = fields.Many2one(
        "product.product", string="Article", required=True, domain="[('is_storable', '=', True)]",
    )
    tracking = fields.Selection(related="product_id.tracking")
    quantity = fields.Float("Quantité", default=1.0, digits="Product Unit")
    serial_numbers = fields.Text(
        "Numéros de série",
        help="Un numéro par ligne (un scanner de codes-barres fonctionne). Laissez vide pour "
             "qu'Odoo les numérote automatiquement.",
    )
    serial_count = fields.Integer("Numéros saisis", compute="_compute_serial_count")

    @api.depends("serial_numbers")
    def _compute_serial_count(self):
        for line in self:
            line.serial_count = len(split_serials(line.serial_numbers))

    @api.onchange("serial_numbers")
    def _onchange_serial_numbers(self):
        if self.tracking == "serial" and self.serial_count:
            self.quantity = self.serial_count


# --- Sortie de stock ---------------------------------------------------------------

class CaissecashStockExit(models.TransientModel):
    _name = "caissecash.stock.exit"
    _inherit = "caissecash.stock.mixin"
    _description = "Sortie de stock"

    picking_id = fields.Many2one(
        "stock.picking", string="Livraison prévue (commande client)",
        domain="[('picking_type_code', '=', 'outgoing'), ('state', 'in', ('confirmed', 'waiting', 'assigned'))]",
        help="Si le matériel part pour une commande client, choisissez sa livraison : ses articles sont repris.",
    )
    has_pending = fields.Boolean(compute="_compute_has_pending")
    partner_id = fields.Many2one("res.partner", string="Client", required=True)
    establishment_id = fields.Many2one(
        "caissecash.establishment", string="Établissement", domain="[('partner_id', '=', partner_id)]",
    )
    installation_id = fields.Many2one(
        "caissecash.installation", string="Pour l'installation",
        domain="[('partner_id', '=', partner_id), ('state', 'not in', ('terminee', 'annulee'))]",
    )
    reference = fields.Char("Motif / référence")
    pack_id = fields.Many2one(
        "product.product", string="Ajouter un pack", domain="[('is_kits', '=', True)]",
        help="Ajoute d'un coup tous les articles qui composent le pack.",
    )
    line_ids = fields.One2many("caissecash.stock.exit.line", "wizard_id", string="Articles qui sortent")

    def _compute_has_pending(self):
        pending = bool(self.env["stock.picking"].search_count([
            ("picking_type_code", "=", "outgoing"), ("state", "in", ("confirmed", "waiting", "assigned")),
        ], limit=1))
        for wizard in self:
            wizard.has_pending = pending

    @api.onchange("picking_id")
    def _onchange_picking_id(self):
        if self.picking_id:
            self.partner_id = self.picking_id.partner_id
            self.reference = self.reference or self.picking_id.origin
            self.line_ids = self._fill_from_picking(self.picking_id)

    @api.onchange("partner_id")
    def _onchange_partner_id(self):
        if self.establishment_id.partner_id != self.partner_id:
            self.establishment_id = False
        if self.installation_id.partner_id != self.partner_id:
            self.installation_id = False

    @api.onchange("installation_id")
    def _onchange_installation_id(self):
        if self.installation_id:
            self.establishment_id = self.installation_id.establishment_id

    @api.onchange("pack_id")
    def _onchange_pack_id(self):
        if not self.pack_id:
            return
        bom = self.env["mrp.bom"]._bom_find(self.pack_id, bom_type="phantom")[self.pack_id]
        if bom:
            _boms, components = bom.explode(self.pack_id, 1)
            self.line_ids = [
                Command.create({"product_id": bom_line.product_id.id, "quantity": data["qty"]})
                for bom_line, data in components if bom_line.product_id.is_storable
            ]
        self.pack_id = False

    def _available_lots(self, product):
        """Numéros de série de l'article réellement en stock (emplacements internes)."""
        quants = self.env["stock.quant"].search([
            ("product_id", "=", product.id), ("location_id.usage", "=", "internal"),
            ("lot_id", "!=", False), ("quantity", ">", 0),
        ])
        return {quant.lot_id: quant.location_id for quant in quants}

    def action_validate(self):
        self.ensure_one()
        lines = self.line_ids.filtered("product_id")
        if not lines:
            raise UserError("Ajoutez au moins un article qui sort.")
        warehouse = self._warehouse()
        # Une sortie par article, même s'il a été saisi sur plusieurs lignes.
        plans = {}
        for line in lines:
            product = line.product_id
            rounding = product.uom_id.rounding
            if float_compare(line.quantity, 0, precision_rounding=rounding) <= 0:
                raise UserError(f"Indiquez la quantité qui sort pour « {product.display_name} ».")
            if product.tracking == "serial" and len(line.lot_ids) != line.quantity:
                raise UserError(
                    f"« {product.display_name} » : choisissez les numéros de série qui sortent "
                    f"({len(line.lot_ids)} choisi(s) pour une quantité de {qty(line.quantity)})."
                )
            plan = plans.setdefault(product, {"quantity": 0.0, "lots": self.env["stock.lot"]})
            plan["quantity"] += line.quantity
            plan["lots"] |= line.lot_ids
        for product, plan in plans.items():
            if product.tracking == "serial":
                available = self._available_lots(product)
                absent = plan["lots"].filtered(lambda lot: lot not in available)
                if absent:
                    raise UserError(f"Le numéro de série {absent[0].name} n'est plus en stock.")
                if len(plan["lots"]) != plan["quantity"]:
                    raise UserError(f"Un numéro de série de « {product.display_name} » est choisi deux fois.")
            else:
                in_stock = product.with_context(warehouse_id=warehouse.id).qty_available
                if float_compare(plan["quantity"], in_stock, precision_rounding=product.uom_id.rounding) > 0:
                    raise UserError(
                        f"Stock insuffisant pour « {product.display_name} » : {qty(in_stock)} en stock, "
                        f"{qty(plan['quantity'])} demandé(s)."
                    )

        origin = self.reference or (self.installation_id and self.installation_id.name)
        picking = self._prepare_picking(warehouse.out_type_id, self.partner_id, origin)
        moves = self._moves_for(picking, {product: plan["quantity"] for product, plan in plans.items()})
        picking.action_assign()

        for product, plan in plans.items():
            move = moves[product]
            if product.tracking == "serial":
                available = self._available_lots(product)
                move.move_line_ids.unlink()
                self.env["stock.move.line"].create([{
                    "move_id": move.id,
                    "picking_id": picking.id,
                    "product_id": product.id,
                    "product_uom_id": move.product_uom.id,
                    "location_id": available[lot].id,
                    "location_dest_id": move.location_dest_id.id,
                    "lot_id": lot.id,
                    "quantity": 1,
                    "picked": True,
                } for lot in plan["lots"]])
            else:
                move.quantity = plan["quantity"]
            move.picked = True
        self._validate(picking, self.env["stock.move"].union(*moves.values()))
        self._register_equipment(lines)

        total = sum(lines.mapped("quantity"))
        return self._done_notification(
            "Sortie enregistrée",
            f"{qty(total)} article(s) sorti(s) pour {self.partner_id.display_name} ({picking.name}).",
        )

    def _register_equipment(self, lines):
        """Chaque appareil suivi par numéro de série devient le « matériel installé »
        du client (garantie, SAV)."""
        Equipment = self.env["caissecash.equipment"]
        equipments = Equipment
        today = fields.Date.context_today(self)
        for line in lines.filtered(lambda l: l.product_id.tracking == "serial"):
            for lot in line.lot_ids:
                values = {
                    "customer_id": self.partner_id.id,
                    "establishment_id": self.establishment_id.id,
                    "install_date": today,
                    "sav_status": "en_service",
                }
                equipment = Equipment.search([("lot_id", "=", lot.id)], limit=1)
                if equipment:
                    equipment.write(values)
                else:
                    equipment = Equipment.create({"product_id": line.product_id.id, "lot_id": lot.id, **values})
                equipments |= equipment
        if equipments and self.installation_id:
            self.installation_id.equipment_ids = [Command.link(e.id) for e in equipments]


class CaissecashStockExitLine(models.TransientModel):
    _name = "caissecash.stock.exit.line"
    _description = "Article d'une sortie de stock"

    wizard_id = fields.Many2one("caissecash.stock.exit", required=True, ondelete="cascade")
    product_id = fields.Many2one(
        "product.product", string="Article", required=True, domain="[('is_storable', '=', True)]",
    )
    tracking = fields.Selection(related="product_id.tracking")
    available_qty = fields.Float("En stock", related="product_id.qty_available", digits="Product Unit")
    quantity = fields.Float("Quantité", default=1.0, digits="Product Unit")
    lot_ids = fields.Many2many(
        "stock.lot", string="Numéros de série",
        domain="[('product_id', '=', product_id), ('product_qty', '>', 0)]",
    )

    @api.onchange("lot_ids")
    def _onchange_lot_ids(self):
        if self.tracking == "serial" and self.lot_ids:
            self.quantity = len(self.lot_ids)


# --- Correction de stock -----------------------------------------------------------

class CaissecashStockAdjust(models.TransientModel):
    _name = "caissecash.stock.adjust"
    _inherit = "caissecash.stock.mixin"
    _description = "Correction de stock"

    product_id = fields.Many2one(
        "product.product", string="Article", required=True, domain="[('is_storable', '=', True)]",
    )
    tracking = fields.Selection(related="product_id.tracking")
    lot_id = fields.Many2one(
        "stock.lot", string="Numéro de série", domain="[('product_id', '=', product_id)]",
        help="L'appareil concerné. Pour un appareil retrouvé qui n'a jamais été enregistré, "
             "tapez son numéro dans « Nouveau numéro ».",
    )
    lot_name = fields.Char("Nouveau numéro")
    current_qty = fields.Float("En stock actuellement", compute="_compute_current_qty", digits="Product Unit")
    new_qty = fields.Float("Quantité réelle", digits="Product Unit")
    reason = fields.Selection(ADJUST_REASONS, string="Raison", required=True, default="comptage")
    note = fields.Char("Précision")

    @api.depends("product_id", "lot_id")
    def _compute_current_qty(self):
        for wizard in self:
            if wizard.lot_id:
                wizard.current_qty = wizard.lot_id.product_qty
            elif wizard.product_id and wizard.tracking != "serial":
                wizard.current_qty = wizard.product_id.qty_available
            else:
                wizard.current_qty = 0.0

    @api.onchange("product_id")
    def _onchange_product_id(self):
        self.lot_id = False
        self.lot_name = False
        self.new_qty = self.current_qty

    @api.onchange("lot_id", "lot_name")
    def _onchange_lot(self):
        if self.lot_id:
            self.lot_name = False
            # Un appareil en stock que l'on corrige est le plus souvent cassé ou perdu.
            self.new_qty = 0.0 if self.current_qty else 1.0
        elif self.lot_name:
            self.new_qty = 1.0

    def action_apply(self):
        self.ensure_one()
        user = self.env.user
        if not (user.has_group("caissecash_erp.group_stock") or user.has_group("caissecash_erp.group_direction")):
            raise UserError("Seuls le responsable stock et la direction peuvent corriger le stock.")
        product = self.product_id
        if self.new_qty < 0:
            raise UserError("La quantité réelle ne peut pas être négative.")
        warehouse = self._warehouse()
        Quant = self.env["stock.quant"].sudo()
        lot = self.lot_id
        location = warehouse.lot_stock_id
        if product.tracking == "serial":
            if not lot and not self.lot_name:
                raise UserError("Choisissez l'appareil concerné (son numéro de série).")
            if self.new_qty not in (0, 1):
                raise UserError("Pour un appareil suivi par numéro de série, la quantité réelle est 0 ou 1.")
            if not lot:
                lot = self.env["stock.lot"].search([("product_id", "=", product.id), ("name", "=", self.lot_name.strip())], limit=1) \
                    or self.env["stock.lot"].create({"product_id": product.id, "name": self.lot_name.strip()})
            quant = Quant.search([
                ("product_id", "=", product.id), ("lot_id", "=", lot.id),
                ("location_id.usage", "=", "internal"), ("quantity", ">", 0),
            ], limit=1)
            location = quant.location_id or location
            current, target = quant.quantity, self.new_qty
        else:
            quant = Quant.search([("product_id", "=", product.id), ("location_id", "=", location.id),
                                  ("lot_id", "=", False)], limit=1)
            # Le stock peut être réparti sur plusieurs emplacements : l'écart avec le
            # total est reporté sur l'emplacement principal.
            total = product.with_context(warehouse_id=warehouse.id).qty_available
            current = quant.quantity
            target = current + self.new_qty - total
            if target < 0:
                raise UserError("Une partie du stock est rangée ailleurs : corrigez-la depuis « Stock détaillé ».")
        if float_is_zero(target - current, precision_rounding=product.uom_id.rounding):
            raise UserError("La quantité réelle est déjà celle du stock : rien à corriger.")

        reason = dict(ADJUST_REASONS)[self.reason]
        label = f"{reason} : {self.note}" if self.note else reason
        quant = Quant.with_context(inventory_mode=True, inventory_name=f"Correction — {label}").create({
            "product_id": product.id,
            "location_id": location.id,
            "lot_id": lot.id,
            "inventory_quantity": target,
        })
        quant.with_context(inventory_name=f"Correction — {label}").action_apply_inventory()
        return self._done_notification(
            "Stock corrigé",
            f"« {product.display_name} »{f' ({lot.name})' if lot else ''} : {label.lower()}.",
        )
