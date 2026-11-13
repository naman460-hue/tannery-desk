#!/usr/bin/env bash
# One-time setup: create migrations, apply them, load demo data.
# (Migrations are generated on your machine so they always match the installed Django version.
#  Commit the generated */migrations/ folders afterwards.)
set -euo pipefail
cd "$(dirname "$0")"
python manage.py makemigrations accounts factories products rfqs orders payments notifications messaging reviews core
python manage.py migrate
python manage.py seed_demo
python manage.py check
echo "Done. Start the server with: python manage.py runserver"
