ARG ODOO_VERSION=19
FROM odoo:${ODOO_VERSION}

# gettext fournit envsubst, utilise par l'entrypoint pour injecter les
# variables d'environnement (mot de passe maitre, etc.) dans odoo.conf
# sans jamais ecrire de secret en dur dans l'image ou le depot Git.
USER root
RUN apt-get update \
    && apt-get install -y --no-install-recommends gettext-base \
    && rm -rf /var/lib/apt/lists/*

COPY config/odoo.conf.template /etc/odoo/odoo.conf.template
COPY scripts/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh && chown odoo:odoo /etc/odoo/odoo.conf.template

USER odoo
ENTRYPOINT ["/entrypoint.sh"]
CMD ["odoo"]
