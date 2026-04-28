#!/bin/sh
# entrypoint.sh — Docker container startup script
# Runs database setup tasks before launching Gunicorn.
# Executed every time the container starts; safe to run multiple times.

set -e  # Exit immediately on any error

echo "=== SCDRRMO FMSWGIS Startup ==="

# -------------------------------------------------------
# 1. Wait for PostgreSQL to be ready before doing anything
# -------------------------------------------------------
echo "[1/5] Waiting for database..."
until python manage.py inspectdb > /dev/null 2>&1; do
    echo "  Database not ready yet — retrying in 2s..."
    sleep 2
done
echo "  Database is ready."

# -------------------------------------------------------
# 2. Apply any pending database migrations
# -------------------------------------------------------
echo "[2/5] Running migrations..."
python manage.py migrate --no-input

# -------------------------------------------------------
# 3. Collect static files into STATIC_ROOT for WhiteNoise
# -------------------------------------------------------
echo "[3/5] Collecting static files..."
python manage.py collectstatic --no-input --clear

# -------------------------------------------------------
# 4. Load GIS shapefiles (barangay + flood susceptibility)
#    Only runs if the Barangay table is empty to avoid
#    re-importing on every container restart.
# -------------------------------------------------------
echo "[4/5] Checking GIS data..."
BARANGAY_COUNT=$(python manage.py shell -c "from maps.models import Barangay; print(Barangay.objects.count())" 2>/dev/null | tail -1 || echo "0")
if [ "$BARANGAY_COUNT" = "0" ]; then
    echo "  Loading shapefiles (first run)..."
    python manage.py load_shapefiles
else
    echo "  GIS data already loaded ($BARANGAY_COUNT barangays). Skipping."
fi

# -------------------------------------------------------
# 5. Start Gunicorn WSGI server
#    Workers = (2 * CPU_CORES) + 1 is the standard formula.
#    Default 3 workers is appropriate for a small VPS.
# -------------------------------------------------------
WORKERS=${GUNICORN_WORKERS:-3}
echo "[5/5] Starting Gunicorn with $WORKERS workers..."
exec gunicorn silay_drrmo.wsgi:application \
    --bind 0.0.0.0:8000 \
    --workers "$WORKERS" \
    --timeout 120 \
    --access-logfile - \
    --error-logfile - \
    --log-level info
