from odoo import api, models
from odoo.fields import Command

# Menu des applications, rangé par rubrique et dans l'ordre du travail :
# (rubrique, menu racine, nom affiché ou None pour garder le sien, icône).
DAILY = "Au quotidien"
CUSTOMER_JOURNEY = "Du prospect au SAV"
MANAGEMENT = "Gestion"
OTHER = "Autres applications"
ADMIN = "Administration"
SECTIONS = [DAILY, CUSTOMER_JOURNEY, MANAGEMENT, OTHER, ADMIN]

APPS = [
    (DAILY, "caissecash_espace.menu_caissecash_home", None, "espace"),
    (DAILY, "mail.menu_root_discuss", "Discussion", "discussion"),
    (DAILY, "project.menu_main_pm", "Tâches", "projet"),
    (DAILY, "hr_attendance.menu_hr_attendance_root", "Pointage", "presences"),
    (DAILY, "calendar.mail_menu_calendar", "Agenda", "calendrier"),
    (CUSTOMER_JOURNEY, "crm.crm_menu_root", "Clients", "clients"),
    (CUSTOMER_JOURNEY, "sale.sale_menu_root", "Ventes", "ventes"),
    (CUSTOMER_JOURNEY, "stock.menu_stock_root", "Stock", "stock"),
    (CUSTOMER_JOURNEY, "purchase.menu_purchase_root", "Achats", "achats"),
    (CUSTOMER_JOURNEY, "caissecash_erp.menu_caissecash_field", None, "installations"),
    (CUSTOMER_JOURNEY, "account.menu_finance", "Facturation", "facturation"),
    (CUSTOMER_JOURNEY, "caissecash_erp.menu_caissecash_billing", None, "abonnements"),
    (MANAGEMENT, "caissecash_erp.menu_caissecash_dashboard", None, "tableau"),
    (MANAGEMENT, "caissecash_erp.menu_caissecash_expense_root", None, "depenses"),
    (MANAGEMENT, "caissecash_erp.menu_founders_root", None, "associes"),
    (MANAGEMENT, "hr.menu_hr_root", "Employés", "employes"),
    (ADMIN, "base.menu_management", "Applications", None),
    (ADMIN, "base.menu_administration", "Paramètres", None),
]

# Sous-menus remontés ou renommés pour que l'essentiel soit au premier niveau :
# (menu, nouveau parent, séquence, nom).
SUBMENUS = [
    # Clients : prospects, fiches clients puis établissements (caissecash_erp).
    ("crm.menu_crm_opportunities", "crm.crm_menu_root", 1, "Prospects"),
    ("crm.res_partner_menu_customer", "crm.crm_menu_root", 2, "Clients"),
    # Stock : ce qu'on a en stock en premier, puis ce qui entre et sort.
    ("stock.menu_product_stock", "stock.menu_stock_root", 0, "Quantités en stock"),
    ("stock.stock_picking_type_menu", "stock.menu_stock_root", 1, "Réceptions et livraisons"),
    ("mrp.menu_mrp_bom_form_action", "stock.menu_stock_inventory_control", 3, "Composition des packs"),
]

# Installés comme dépendances mais inutiles au quotidien (ou en double avec les
# menus ci-dessus) : visibles seulement en mode développeur.
HIDDEN = [
    "contacts.menu_contacts",
    "project_todo.menu_todo_todos",
    "hr_timesheet.timesheet_menu_root",
    "mrp.menu_mrp_root",
    "maintenance.menu_maintenance_title",
    "utm.menu_link_tracker_root",
    "base.menu_tests",
    "crm.crm_menu_sales",
    "crm.menu_import_crm",
]


class IrUiMenu(models.Model):
    _inherit = "ir.ui.menu"

    @api.model
    def _caissecash_apply_navigation(self):
        """Range le menu des applications. Appelé à chaque installation ou mise à
        jour du module (une mise à jour d'Odoo remettrait sinon ses menus)."""
        langs = [code for code, _name in self.env["res.lang"].get_installed()]

        def ref(xmlid):
            return self.env.ref(xmlid, raise_if_not_found=False)

        def rename(menu, name):
            menu.update_field_translations("name", dict.fromkeys(langs, name))

        for sequence, (section, xmlid, name, icon) in enumerate(APPS, start=1):
            menu = ref(xmlid)
            if not menu:
                continue
            if section != ADMIN:
                menu.sequence = sequence
            if icon:
                menu.web_icon = f"caissecash_espace,static/src/img/apps/{icon}.svg"
            if name:
                rename(menu, name)

        for xmlid, parent_xmlid, sequence, name in SUBMENUS:
            menu, parent = ref(xmlid), ref(parent_xmlid)
            if menu and parent:
                menu.write({"parent_id": parent.id, "sequence": sequence})
                rename(menu, name)

        developer_mode = self.env.ref("base.group_no_one")
        for xmlid in HIDDEN:
            if menu := ref(xmlid):
                menu.group_ids = [Command.set(developer_mode.ids)]

    def load_web_menus(self, debug):
        """Ajoute à chaque application sa rubrique dans le menu des applications."""
        menus = super().load_web_menus(debug)
        sections = {xmlid: section for section, xmlid, _name, _icon in APPS}
        for menu in menus.values():
            if menu["id"] != "root" and menu["id"] == menu["appID"]:
                section = sections.get(menu["xmlid"], OTHER)
                menu["caissecashSection"] = section
                menu["caissecashSectionRank"] = SECTIONS.index(section)
        return menus
