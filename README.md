# Silay DRRMO Flood Monitoring System (Local Setup)

This repository now targets a straightforward local Django runserver workflow backed by a locally installed PostgreSQL/PostGIS database.

## Prerequisites
1. **Python 3.12** with `pip`.
2. **PostgreSQL 15+ with PostGIS 3.4+**.
3. **GDAL/GEOS libraries**. On Ubuntu/Debian:
   ```bash
   sudo apt install gdal-bin libgdal-dev libgeos-dev
   ```
4. **NodeJS (optional)** for rebuilding OpenLayers assets: `npm install`.

## Initial Setup
```bash
python -m venv env-drrmo
source env-drrmo/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
cp .env.example .env  # then update secrets/passwords
```
Key `.env` values for local dev:
- `DEBUG=True`
- `DB_HOST=localhost`
- `DB_NAME=silaydrrmo_db`, `DB_USER=postgres`, `DB_PASSWORD=<your local password>`

## Database Provisioning
1. Create database and enable PostGIS:
   ```sql
   CREATE DATABASE silaydrrmo_db;
   \c silaydrrmo_db
   CREATE EXTENSION IF NOT EXISTS postgis;
   CREATE EXTENSION IF NOT EXISTS postgis_topology;
   ```
2. Run migrations and seed GIS data:
   ```bash
   python manage.py migrate
   python manage.py load_shapefiles  # first run only
   ```

## Resetting the Database
To wipe all data and return to a pristine state, run:
```bash
psql -U postgres -d silaydrrmo_db -f scripts/reset_silaydrrmo_db.sql
python manage.py migrate
python manage.py load_shapefiles
```
The SQL script drops and recreates the `public` schema and extensions, ensuring the next migration run rebuilds everything cleanly.

## Running the Development Server
```bash
python manage.py runserver 0.0.0.0:8000
```
Key pages to verify:
1. `/` – login page
2. `/home/` – dashboard after logging in
3. `/monitoring/` – real-time monitoring views
4. `/maps/` – GIS map layers

Use `python manage.py createsuperuser` to create an initial admin, or leverage the admin registration key defined in `.env`.

## Static & Media
- Collect static assets when needed via `python manage.py collectstatic`.
- User uploads are stored under `media/` which is already git-ignored.

## Notes
- Docker, Gunicorn, and Nginx assets have been removed; deployers can reintroduce containerization later if needed.
- Keep the `logs/` directory for Django log outputs (rotating handlers already configured in `settings.py`).
