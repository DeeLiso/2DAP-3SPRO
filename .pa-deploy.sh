#!/usr/bin/env bash
set -e

cd "$(dirname "$0")"

echo "==> git pull origin main"
git pull origin main

echo "==> python manage.py migrate"
python manage.py migrate

echo "==> python manage.py collectstatic --noinput"
python manage.py collectstatic --noinput

echo ""
echo "==> Done. Go to the PythonAnywhere Web tab and click Reload to apply."