def post_init_hook(env):
    """Réglages appliqués une seule fois, à l'installation."""
    # « Mon espace » devient l'écran d'accueil de tous les utilisateurs internes,
    # y compris ceux créés plus tard (valeur par défaut).
    action = env.ref("caissecash_espace.action_caissecash_home")
    env["res.users"].search([("share", "=", False)]).write({"action_id": action.id})
    env["ir.default"].set("res.users", "action_id", action.id)

    # Pointage depuis le téléphone, sans GPS ni géolocalisation IP.
    env["res.company"].search([]).write({
        "attendance_from_systray": True,
        "attendance_device_tracking": False,
    })

    # Canal d'annonce de chaque projet : le canal du même nom, sinon « Général ».
    channels = {c.name: c for c in env["discuss.channel"].search([("channel_type", "=", "channel")])}
    general = env.ref("mail.channel_all_employees", raise_if_not_found=False)
    for project in env["project.project"].with_context(active_test=False).search([]):
        project.caissecash_channel_id = channels.get(project.name) or general
