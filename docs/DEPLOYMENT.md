# Deployment

The app runs as one Docker Compose stack with three services:

| Service | Job |
| --- | --- |
| `db` | PostgreSQL. Stores all data and the background tasks |
| `web` | Django and the built React app on port 8000. Runs the database migrations at each start |
| `worker` | Runs the background tasks |

## Deploy with Coolify

1. In Coolify, add a new resource of the type "Docker Compose" from this Git repository.
2. Set the environment variables from `.env.example` in Coolify. Use new random values for `DJANGO_SECRET_KEY` and `POSTGRES_PASSWORD`.
3. Set `DJANGO_ALLOWED_HOSTS` to the domain, for example `paddock.example.com`.
4. Set `DJANGO_CSRF_TRUSTED_ORIGINS` to the full URL, for example `https://paddock.example.com`.
5. Give the `web` service the domain on port 8000. Coolify then gives HTTPS through its proxy.

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

With `DJANGO_DEBUG=false`, the session and CSRF cookies need HTTPS. Browsers accept them on `http://localhost` only.

## Health check

`GET /api/health` gives `{"status": "ok", "database": true}` when the app can reach the database. Docker Compose uses it as the health check of `web`.

## Upgrade

Deploy the new version. The `web` service runs the migrations before it starts.

## Backup

Ticket #18 adds a backup and restore command. Until then, use the backup feature of Coolify for the `db-data` volume.
