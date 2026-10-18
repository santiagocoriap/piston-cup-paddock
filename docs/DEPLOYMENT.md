# Deployment

The app runs as one Docker Compose stack with three services:

| Service | Job |
| --- | --- |
| `db` | PostgreSQL. Stores all data and the background tasks |
| `web` | Django and the built React app on port 8000. Runs the database migrations at each start |
| `worker` | Runs the background tasks |

The `media-data` volume keeps the uploaded result files.

## Deploy with Coolify

1. In Coolify, add a new resource of the type "Docker Compose" from this Git repository.
2. Set the environment variables from `.env.example` in Coolify. Use new random values for `DJANGO_SECRET_KEY` and `POSTGRES_PASSWORD`.
3. Set `DJANGO_ALLOWED_HOSTS` to the domain and `localhost`, for example `paddock.example.com,localhost`. The health check of the `web` container calls `localhost`. Without it, the check fails and Coolify stops the deploy.
4. Set `DJANGO_CSRF_TRUSTED_ORIGINS` to the full URL, for example `https://paddock.example.com`.
5. Set `TRUSTED_PROXY_COUNT` to `1`. The login limit then uses the real client address behind the Coolify proxy.
6. Give the `web` service the domain on port 8000. Coolify then gives HTTPS through its proxy.

After the first deploy, make the first admin account from the Coolify terminal of the `web` service:

```bash
python manage.py create_first_admin --username <name>
```

## Settings

| Variable | Required | Meaning |
| --- | --- | --- |
| `DJANGO_SECRET_KEY` | Yes | A long random value. Keep it secret |
| `DJANGO_DEBUG` | No | `false` in production. Default `false` |
| `DJANGO_ALLOWED_HOSTS` | Yes | Domains of the app, separated by commas |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | Yes | Full URLs of the app, separated by commas |
| `POSTGRES_DB`, `POSTGRES_USER` | No | Default `paddock` |
| `POSTGRES_PASSWORD` | Yes | A long random value |
| `TRUSTED_PROXY_COUNT` | Yes behind a proxy | `1` behind Coolify. `0` with no proxy. A wrong value lets a client fake the address for the login limit |

## Login limit

After 5 wrong passwords for one username in 15 minutes, the login refuses that username for 15 minutes. After 20 wrong passwords from one address in 15 minutes, the login refuses that address for 15 minutes. A correct login clears the count of the username.

With `DJANGO_DEBUG=false`, the session and CSRF cookies need HTTPS. Browsers accept them on `http://localhost` only.

## Health check

`GET /api/health` gives `{"status": "ok", "database": true}` when the app can reach the database. Docker Compose uses it as the health check of `web`.

## Upgrade

Deploy the new version. The `web` service runs the migrations before it starts.

## Backup

One command backs up the database and the stored files (the result files) into one zip file:

```bash
docker compose exec web python manage.py backup
```

A league admin can also start a backup from the data health card of a championship. The card shows the last backup, its size, and its result. The worker does the backup, so the `worker` service also needs the `backups` volume.

The file goes to the `backups` volume, for example `backups/paddock-20261012-213000.zip`. Copy it out of the container and keep it on another computer:

```bash
docker compose cp web:/app/backend/backups/paddock-20261012-213000.zip .
```

Do a backup before each upgrade, and after each race night. Login sessions and background tasks are not in the backup.

## Restore

A restore **deletes all current data and stored files**, then loads the backup. Users must sign in again.

1. Copy the backup into the container:

   ```bash
   docker compose cp paddock-20261012-213000.zip web:/app/backend/backups/
   ```

2. Run the restore:

   ```bash
   docker compose exec web python manage.py restore backups/paddock-20261012-213000.zip --confirm
   ```

The command checks the row counts after the restore and stops with an error when they differ.

## Exports

The season page has links to CSV files of the results, the standings, and the restart history. The records page has a link to a CSV file of the track records. The files open in Excel and Google Sheets.
