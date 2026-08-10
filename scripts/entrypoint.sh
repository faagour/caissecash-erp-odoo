#!/bin/bash
set -e

# Genere odoo.conf a partir du template + variables d'environnement.
# Permet de ne jamais stocker de secret en clair dans l'image ou le depot Git.
envsubst < /etc/odoo/odoo.conf.template > /etc/odoo/odoo.conf

exec odoo -c /etc/odoo/odoo.conf "${@:2}"
