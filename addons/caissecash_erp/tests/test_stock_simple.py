from odoo import Command
from odoo.exceptions import UserError
from odoo.tests import Form, TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestStockSimple(TransactionCase):
    """Articles (sorte, seuil d'alerte, fournisseur) et mouvements de stock
    simplifiés (entrée, sortie, correction), faits par le responsable stock."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.stock_user = cls.env["res.users"].create({
            "name": "Responsable stock test", "login": "stock.simple",
            "group_ids": [(6, 0, [cls.env.ref("base.group_user").id, cls.env.ref("caissecash_erp.group_stock").id])],
        })
        cls.env = cls.env(user=cls.stock_user)
        cls.Product = cls.env["product.template"]
        cls.vendor = cls.env["res.partner"].sudo().create({"name": "Fournisseur Test", "supplier_rank": 1})
        cls.customer = cls.env["res.partner"].sudo().create({"name": "Client Test", "customer_rank": 1})
        cls.printer = cls.Product.create({"name": "Imprimante test", "caissecash_kind": "materiel"})
        cls.paper = cls.Product.create({"name": "Rouleau test", "caissecash_kind": "consommable"})
        cls.warehouse = cls.env["stock.warehouse"].search([("company_id", "=", cls.env.company.id)], limit=1)

    def entry(self, lines, **values):
        wizard = self.env["caissecash.stock.entry"].create({
            "line_ids": [Command.create(line) for line in lines], **values,
        })
        return wizard.action_validate()

    def exit(self, lines, **values):
        wizard = self.env["caissecash.stock.exit"].create({
            "partner_id": self.customer.id, "line_ids": [Command.create(line) for line in lines], **values,
        })
        return wizard.action_validate()

    def lots(self, template):
        return self.env["stock.lot"].search([("product_id", "=", template.product_variant_id.id)])

    # --- Articles --------------------------------------------------------------

    def test_kind_sets_odoo_settings(self):
        self.assertEqual((self.printer.type, self.printer.is_storable, self.printer.tracking), ("consu", True, "serial"))
        self.assertEqual((self.paper.is_storable, self.paper.tracking), (True, "none"))
        app = self.Product.create({"name": "Application test", "caissecash_kind": "logiciel"})
        self.assertEqual(app.type, "service")
        self.paper.caissecash_kind = "materiel"
        self.assertEqual(self.paper.tracking, "serial")

    def test_kind_follows_full_form(self):
        service = self.Product.create({"name": "Service test", "type": "service"})
        self.assertEqual(service.caissecash_kind, "logiciel")
        service.type = "consu"
        self.assertEqual(service.caissecash_kind, "consommable")

    def test_kind_in_simplified_form(self):
        form = Form(self.Product.with_context(default_caissecash_kind="materiel"),
                    view="caissecash_erp.view_caissecash_product_form")
        form.name = "Caisse test"
        form.caissecash_kind = "logiciel"
        product = form.save()
        self.assertEqual((product.caissecash_kind, product.type), ("logiciel", "service"))

    def test_alert_threshold_and_restock(self):
        self.paper.caissecash_min_qty = 5
        orderpoint = self.env["stock.warehouse.orderpoint"].sudo().search(
            [("product_id", "=", self.paper.product_variant_id.id)])
        self.assertEqual(orderpoint.product_min_qty, 5)
        self.assertIn(self.paper, self.Product.search([("caissecash_to_restock", "=", True)]))
        self.entry([{"product_id": self.paper.product_variant_id.id, "quantity": 8}])
        self.assertNotIn(self.paper, self.Product.search([("caissecash_to_restock", "=", True)]))
        self.paper.caissecash_min_qty = 0
        self.assertFalse(orderpoint.exists())

    def test_alert_threshold_given_at_creation(self):
        form = Form(self.Product.with_context(default_caissecash_kind="consommable"),
                    view="caissecash_erp.view_caissecash_product_form")
        form.name = "Étiquettes test"
        form.caissecash_min_qty = 4
        labels = form.save()
        self.assertEqual(labels.caissecash_min_qty, 4)
        self.assertIn(labels, self.Product.search([("caissecash_to_restock", "=", True)]))

    def test_order_from_restock(self):
        self.paper.write({"caissecash_min_qty": 10, "caissecash_vendor_id": self.vendor.id})
        self.assertEqual(self.paper.seller_ids.partner_id, self.vendor)
        action = self.paper.action_caissecash_order()
        order = self.env["purchase.order"].browse(action["res_id"])
        self.assertEqual(order.partner_id, self.vendor)
        self.assertEqual(order.order_line.product_qty, 10)
        # Un deuxième « Commander » complète la même demande de prix.
        self.paper.action_caissecash_order()
        self.assertEqual(len(order.order_line), 1)

    def test_order_needs_vendor(self):
        self.paper.caissecash_min_qty = 3
        with self.assertRaises(UserError):
            self.paper.action_caissecash_order()

    # --- Entrée ----------------------------------------------------------------

    def test_entry_with_serial_numbers(self):
        self.entry([{"product_id": self.printer.product_variant_id.id, "quantity": 2,
                     "serial_numbers": "SN-001\nSN-002"}], partner_id=self.vendor.id)
        self.assertEqual(self.printer.qty_available, 2)
        self.assertEqual(sorted(self.lots(self.printer).mapped("name")), ["SN-001", "SN-002"])
        with self.assertRaises(UserError):  # déjà en stock
            self.entry([{"product_id": self.printer.product_variant_id.id, "quantity": 1, "serial_numbers": "SN-001"}])

    def test_entry_generates_missing_serials(self):
        self.entry([{"product_id": self.printer.product_variant_id.id, "quantity": 3, "serial_numbers": "SN-100"}])
        self.assertEqual(self.printer.qty_available, 3)
        self.assertEqual(len(set(self.lots(self.printer).mapped("name"))), 3)

    def test_entry_rejects_too_many_serials(self):
        with self.assertRaises(UserError):
            self.entry([{"product_id": self.printer.product_variant_id.id, "quantity": 1, "serial_numbers": "A\nB"}])

    def test_entry_merges_lines_of_same_product(self):
        product = self.paper.product_variant_id
        self.entry([{"product_id": product.id, "quantity": 4}, {"product_id": product.id, "quantity": 6}])
        self.assertEqual(self.paper.qty_available, 10)

    def test_entry_from_purchase_order(self):
        order = self.env["purchase.order"].sudo().create({
            "partner_id": self.vendor.id,
            "order_line": [Command.create({"product_id": self.paper.product_variant_id.id, "product_qty": 10})],
        })
        order.button_confirm()
        receipt = order.picking_ids
        wizard = Form(self.env["caissecash.stock.entry"])
        wizard.picking_id = receipt
        self.assertEqual(wizard.partner_id, self.vendor)
        with wizard.line_ids.edit(0) as line:
            self.assertEqual(line.quantity, 10)
            line.quantity = 6
        wizard.save().action_validate()
        self.assertEqual(self.paper.qty_available, 6)
        self.assertEqual(order.order_line.qty_received, 6)
        self.assertEqual(receipt.state, "done")
        backorder = order.picking_ids - receipt
        self.assertEqual(backorder.move_ids.product_uom_qty, 4, "le reste reste attendu")

    # --- Sortie ----------------------------------------------------------------

    def test_exit_registers_installed_equipment(self):
        self.entry([{"product_id": self.printer.product_variant_id.id, "quantity": 2,
                     "serial_numbers": "SN-201\nSN-202"}])
        lot = self.lots(self.printer).filtered(lambda l: l.name == "SN-201")
        establishment = self.env["caissecash.establishment"].sudo().create(
            {"name": "Café test", "partner_id": self.customer.id})
        self.exit([{"product_id": self.printer.product_variant_id.id, "quantity": 1, "lot_ids": [(6, 0, lot.ids)]}],
                  establishment_id=establishment.id)
        self.assertEqual(self.printer.qty_available, 1)
        equipment = self.env["caissecash.equipment"].search([("lot_id", "=", lot.id)])
        self.assertEqual((equipment.customer_id, equipment.establishment_id), (self.customer, establishment))
        self.assertEqual(self.customer.caissecash_equipment_count, 1)
        with self.assertRaises(UserError):  # déjà sorti
            self.exit([{"product_id": self.printer.product_variant_id.id, "quantity": 1, "lot_ids": [(6, 0, lot.ids)]}])

    def test_exit_requires_serials_and_stock(self):
        self.entry([{"product_id": self.paper.product_variant_id.id, "quantity": 2}])
        with self.assertRaises(UserError):
            self.exit([{"product_id": self.paper.product_variant_id.id, "quantity": 5}])
        self.exit([{"product_id": self.paper.product_variant_id.id, "quantity": 2}])
        self.assertEqual(self.paper.qty_available, 0)
        self.entry([{"product_id": self.printer.product_variant_id.id, "quantity": 1, "serial_numbers": "SN-300"}])
        with self.assertRaises(UserError):  # numéro de série non choisi
            self.exit([{"product_id": self.printer.product_variant_id.id, "quantity": 1}])

    def test_exit_with_pack(self):
        pack = self.Product.create({"name": "Pack test", "caissecash_kind": "pack"})
        self.env["mrp.bom"].create({
            "product_tmpl_id": pack.id, "type": "phantom",
            "bom_line_ids": [Command.create({"product_id": self.paper.product_variant_id.id, "product_qty": 2})],
        })
        self.assertEqual(pack.caissecash_kind, "pack")
        wizard = Form(self.env["caissecash.stock.exit"])
        wizard.partner_id = self.customer
        wizard.pack_id = pack.product_variant_id
        self.assertEqual(len(wizard.line_ids), 1)
        with wizard.line_ids.edit(0) as line:
            self.assertEqual((line.product_id, line.quantity), (self.paper.product_variant_id, 2))

    # --- Correction ------------------------------------------------------------

    def test_adjust_quantity_and_serial(self):
        self.entry([{"product_id": self.paper.product_variant_id.id, "quantity": 10}])
        self.env["caissecash.stock.adjust"].create({
            "product_id": self.paper.product_variant_id.id, "new_qty": 7, "reason": "comptage",
        }).action_apply()
        self.assertEqual(self.paper.qty_available, 7)
        self.entry([{"product_id": self.printer.product_variant_id.id, "quantity": 1, "serial_numbers": "SN-400"}])
        lot = self.lots(self.printer)
        self.env["caissecash.stock.adjust"].create({
            "product_id": self.printer.product_variant_id.id, "lot_id": lot.id, "new_qty": 0, "reason": "casse",
            "note": "écran fissuré",
        }).action_apply()
        self.assertEqual(self.printer.qty_available, 0)
        with self.assertRaises(UserError):  # rien à corriger
            self.env["caissecash.stock.adjust"].create({
                "product_id": self.paper.product_variant_id.id, "new_qty": 7, "reason": "comptage",
            }).action_apply()

    def test_commercial_cannot_adjust(self):
        commercial = self.env["res.users"].sudo().create({
            "name": "Commercial test", "login": "commercial.stock.simple",
            "group_ids": [(6, 0, [self.env.ref("base.group_user").id, self.env.ref("caissecash_erp.group_commercial").id])],
        })
        self.assertFalse(self.env["caissecash.stock.adjust"].with_user(commercial).has_access("create"))
