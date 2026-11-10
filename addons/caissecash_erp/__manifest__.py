{
    "name": "CaisseCash ERP",
    "version": "19.0.2.3.1",
    "category": "Services/Field Service",
    "summary": "ERP interne CaisseCash : associés, achats, dépenses, établissements, installations, garanties, SAV, abonnements, objectifs",
    "description": """
CaisseCash ERP
==============
Addon interne complementant Odoo Community pour l'activite de CaisseCash
(vente/installation de solutions caisse pour restaurants au Maroc).

Ne remplace ni le POS ni les applications CaisseCash existantes (POS, KDS,
Kiosk, Waiter App, Dashboard). Sert uniquement d'ERP interne : associés et
financement (suivi indicatif), CRM, ventes, achats, dépenses, stock/SAV,
installations, garanties, abonnements logiciels et objectifs de l'année
(cible annuelle répartie par trimestre, suivie automatiquement ou à la main).
""",
    "author": "CaisseCash",
    "license": "LGPL-3",
    "depends": [
        "base",
        "mail",
        "contacts",
        "crm",
        "sale_management",
        "account",
        "purchase",
        "stock",
        "mrp",
        "project",
        "hr_timesheet",
        "hr",
        "maintenance",
        "calendar",
    ],
    "data": [
        "security/caissecash_security.xml",
        "security/ir.model.access.csv",
        "data/ir_sequence_data.xml",
        "data/caissecash_software_module_data.xml",
        "data/caissecash_catalog_data.xml",
        "data/caissecash_expense_category_data.xml",
        "data/crm_stage_data.xml",
        "data/caissecash_onboarding_data.xml",
        "data/caissecash_subscription_cron.xml",
        "data/caissecash_hide_generic_menus.xml",
        "views/caissecash_equipment_views.xml",
        "views/caissecash_establishment_views.xml",
        "views/caissecash_installation_views.xml",
        "views/caissecash_warranty_views.xml",
        "views/caissecash_sav_ticket_views.xml",
        "views/caissecash_subscription_views.xml",
        "views/caissecash_founder_views.xml",
        "views/caissecash_expense_views.xml",
        "views/crm_lead_views.xml",
        "views/res_partner_views.xml",
        "views/purchase_order_views.xml",
        "views/hr_employee_views.xml",
        "views/caissecash_menus.xml",
        "views/caissecash_onboarding_views.xml",
        "views/caissecash_financial_snapshot_views.xml",
        "views/caissecash_dashboard_views.xml",
        "views/caissecash_objective_views.xml",
        "report/caissecash_reports.xml",
        "report/caissecash_installation_report_templates.xml",
        "report/caissecash_warranty_report_templates.xml",
        "report/caissecash_sav_report_templates.xml",
    ],
    "demo": [
        "demo/caissecash_demo.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "caissecash_erp/static/src/dashboard/*",
        ],
    },
    "installable": True,
    "application": True,
    "auto_install": False,
}
