def migrate(cr, version):
    """Installations déjà terminées avant l'ajout de « Terminée le » : date du
    passage à « Terminée » d'après l'historique, sinon date prévue, sinon date
    de dernière modification."""
    cr.execute(
        """
        UPDATE caissecash_installation i
           SET date_done = COALESCE(
                   (SELECT max(m.date)::date
                      FROM mail_tracking_value v
                      JOIN mail_message m ON m.id = v.mail_message_id
                      JOIN ir_model_fields f ON f.id = v.field_id
                     WHERE m.model = 'caissecash.installation'
                       AND m.res_id = i.id
                       AND f.model = 'caissecash.installation'
                       AND f.name = 'state'
                       AND v.new_value_char = 'Terminée'),
                   i.date_planned::date,
                   i.write_date::date)
         WHERE i.state = 'terminee'
           AND i.date_done IS NULL
        """
    )
