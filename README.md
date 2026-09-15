# Black Python Devs — Django site

A Django + Wagtail rebuild of [blackpythondevs.github.io](https://github.com/BlackPythonDevs/blackpythondevs.github.io),
carrying over the existing "Luminous Monolith" design system unchanged.

- **Django 5.2** + **Wagtail 7** for content management
- **PostgreSQL 17** for data, **Valkey 8** for cache and sessions
- **django-allauth** for passwordless accounts (email sign-in codes) with
  Discord as a connect-only integration that grants a community role
- **WhiteNoise** serves static files; media goes to S3-compatible object storage
  in production and the local filesystem in development

## Quick start

```bash
cp .env.example .env
docker compose up -d                      # db, valkey, and the web app

docker compose exec web python manage.py migrate
docker compose exec web python manage.py bootstrap_site
docker compose exec web python manage.py createsuperuser
```

The site is at <http://localhost:8000>, the CMS at <http://localhost:8000/cms/>.

To pull in the existing markdown content (41 posts, events, and pages) from the
static site repo:

```bash
docker compose exec web python manage.py import_content --source ../blackpythondevs.github.io
```

### Task shortcuts and reloading

Every command in this README is also a [mise](https://mise.jdx.dev) task —
`mise tasks` lists them, `mise run <name>` runs one, and `mise install` provides
`uv` if it is not already on the host. The tasks are thin wrappers; nothing here
depends on mise.

In development the source is bind-mounted and `runserver` autoreloads, so **most
changes need no command at all** — Python, templates, and `static/` (WhiteNoise
runs with `WHITENOISE_AUTOREFRESH` in dev) are picked up on the next request.
The rest:

| Change | Command | Task |
| --- | --- | --- |
| Settings, or a wedged worker | `docker compose restart web` | `mise run restart` |
| `pyproject.toml` / `uv.lock` | `docker compose up -d --build web` | `mise run rebuild` |
| New migrations | `docker compose exec web python manage.py migrate` | `mise run migrate` |

Production bakes the code into the image, so there is no live reload — a change
to Python, templates, or static files means a rebuild (`mise run deploy`, see
[Redeploying](#redeploying)). Two things reload without one:

| Change | Command | Task |
| --- | --- | --- |
| `Caddyfile` (bind-mounted read-only) | `fnox exec -- docker compose -f compose.prod.yaml exec caddy caddy reload --config /etc/caddy/Caddyfile` | `mise run caddy-reload` |
| Environment only, no new code | `fnox exec -- docker compose -f compose.prod.yaml kill -s HUP web` | `mise run gunicorn-reload` |

### Running outside Docker

Keep Postgres and Valkey in containers, run Django on the host:

```bash
docker compose up -d db valkey
uv sync
export DATABASE_URL=postgres://bpd:bpd@localhost:5432/bpd
export VALKEY_URL=redis://localhost:6379/0
uv run python manage.py migrate && uv run python manage.py bootstrap_site
uv run python manage.py runserver
```

## Management commands

| Command | What it does |
| --- | --- |
| `bootstrap_site` | Creates the page tree, site settings, and snippets. Idempotent. |
| `import_content` | Imports markdown posts, events, and pages from the static repo, pulling referenced images into the Wagtail image library. Matches on slug, so re-running updates rather than duplicates. |
| `import_foundational_supporters` | Loads the supporter roster from a CSV or JSON file. `--replace` makes the file the truth, clearing the old roster first; `--dry-run` parses and reports without writing. |

Seed data for the snippets lives in `fixtures/`, carried over from the static
site's `_data/` directory.

### Re-uploading the supporter roster

```bash
uv run python manage.py import_foundational_supporters supporters.csv --replace
```

CSV needs a header row with `name`, `year`, and ideally `email`; `status`
(`listed` / `anonymous` / `pending`) and `note` are optional. JSON works too,
either as a flat list of those keys or the year-keyed shape in
`fixtures/foundational_supporters.json`.

**Include emails.** A supporter with an email gets an unverified account they
claim themselves — they sign in with an emailed code, allauth verifies the
address on the way through, and their whole support history is already
attached. A name with no email gets a placeholder account on a reserved
`.invalid` domain that nobody can sign into; re-importing that person later
*with* an address upgrades the same account rather than duplicating them, so
their earlier years follow along.

`--replace` deletes every support record, then removes placeholder accounts
left with nothing attached. Real accounts are never deleted — a member who also
donated keeps their account. The whole import is one transaction, and rows are
validated before anything is written, so a bad line aborts cleanly instead of
leaving a half-replaced roster.

## Content model

Everything the old site kept in `_data/*.json` is now editable in the CMS.

**Page types**

| Model | Purpose |
| --- | --- |
| `home.HomePage` | Hero, principles grid, latest posts, sponsor strip |
| `home.AboutPage` | Story, presence map, leadership roster |
| `home.SupportPage` | Donation widget, partners, foundational supporters, pitch deck |
| `home.StandardPage` | Generic content (code of conduct, sponsorships, ambassadors) |
| `blog.BlogIndexPage` / `blog.BlogPage` | Paginated news with tags and authors |
| `events.EventIndexPage` / `events.EventPage` | BPD events plus the sponsored-events record |

**Sponsored events** (`events.SponsoredEvent`) carry a `status`
(requested → approved → completed → cancelled) and a `paid` flag. Only
**completed** sponsorships appear on the public events page; requested, approved,
and cancelled ones stay internal to the CMS. Completed-but-unpaid entries still
show, carrying a "community" badge for non-monetary support (visibility,
volunteer time). The `amount` and `notes` fields are internal and never render.

**Snippets** — `Author`, `Leader`, `Sponsor`, `Partner`, `FoundationalSupport` (a user's $200+ support in one year, with a listed / anonymous / pending status; imported supporters hold unverified placeholder accounts on a `.invalid` domain until they claim them).

**Site settings** (Wagtail Settings menu) — navigation, announcement toast,
social links, footer copy.

Page bodies are StreamFields. Blocks include headings, rich text, images,
quotes, embeds, iframes (for the Canva deck and presence map), callouts, and the
four-up card grid used for "Our Principles".

## Membership and accounts

Membership is **passwordless**. At `/become-a-member/` a visitor enters an email
address; allauth emails a verification code, and from then on they sign in with
a fresh code each time — no password is ever set. Signed-in members get a member
area at `/members/`.

**Discord is connect-only.** It is never a sign-in method (`is_open_for_signup`
returns `False` in `users/adapters.py`, and email authentication is disabled, so
a Discord login can't be matched to an account). A member connects Discord from
`/members/`; if `DISCORD_GUILD_ID`, `DISCORD_BOT_TOKEN`, and
`DISCORD_MEMBER_ROLE_ID` are set, `users/signals.py` adds them to the server and
grants the role that permits posting (`users/discord.py`). With those unset,
connecting just links the account and members follow the plain invite link.

Setup: register a Discord application, add the redirect
`<base>/accounts/discord/login/callback/`, and create a Social Application in the
CMS (Snippets → Social applications) with the client id and secret. For the
auto-join, invite a bot with the *Manage Roles* permission whose role sits above
the member role in the server hierarchy.

## Permissions

The `wagtailcore` migrations create the standard `Editors` and `Moderators`
groups, managed under Settings → Groups in the CMS. Accounts created through
allauth belong to no group, so they have site access but no CMS access; grant
CMS rights by adding a user to a group.

## Static files and media

Static assets (`static/`) are served by WhiteNoise in every environment, so dev
behaves like production. `collectstatic` runs at image build time in the
production stage, producing hashed and pre-compressed files.

User uploads are separate. In development they land in `media/` on the local
filesystem. In production, setting `AWS_STORAGE_BUCKET_NAME` switches Wagtail's
images and documents to S3-compatible object storage via django-storages — AWS
S3, Cloudflare R2, Backblaze B2, DigitalOcean Spaces, or MinIO (set
`AWS_S3_ENDPOINT_URL` for non-AWS providers). With the variable unset,
production falls back to the local filesystem — Caddy serves that volume at
`/media` — so nothing breaks before storage is provisioned.

## Deployment

Production runs the same four services behind [Caddy](https://caddyserver.com),
which terminates TLS and gets Let's Encrypt certificates automatically — no
certbot, no renewal cron. A Tailscale sidecar puts the admin surfaces on a
private tailnet. Only Caddy publishes ports; Postgres, Valkey, and Tailscale
stay on the internal Docker network.

```
          :80/:443                         tailnet (no published port)
  Caddy ──────────── public site           Tailscale ── bpd.<tailnet>.ts.net
    │                /cms, /django-admin → 404   │
    │                                            │
    └────────────── caddy:8080 ──────────────────┘  everything, admins included
    │
  web   gunicorn, bpd.settings.production (DEBUG = False)
    ├── db      postgres:17
    └── valkey  valkey:8
```

**Before the first deploy**, point `A` (and `AAAA`) records for the apex and
`www` at the server, and open ports 80 and 443. Port 80 has to stay open —
renewals use it too.

Secrets live in `fnox.toml` and are injected as environment variables by
`fnox exec`, which is where compose's `${VAR}` interpolation reads them from.
Because fnox maps each secret to an env var of the same name, the keys in
`fnox.toml` must match the names compose expects exactly. `.env.production` is
the fallback for hosts without fnox; don't maintain both.

Outbound mail goes through [Forward Email](https://forwardemail.net). The only
secret to fill in is `EMAIL_HOST_PASSWORD` — generate it per alias from the
Forward Email dashboard ("Generate Password"), and note that it is shown once.
`EMAIL_HOST_USER` is the full alias address, not a bare username. Sign-in codes
ride this path, so `EMAIL_HOST`, `EMAIL_HOST_USER`, and `EMAIL_HOST_PASSWORD`
are required rather than defaulted: compose aborts at `up` if any is missing,
because the alternative is a stack that passes its healthcheck while no one can
log in.

```bash
fnox exec -- docker compose -f compose.prod.yaml up -d --build
fnox exec -- docker compose -f compose.prod.yaml exec web python manage.py migrate
```

Every compose subcommand needs the same `fnox exec --` prefix — the required
variables are checked on `exec` and `logs`, not just `up`. Verify what compose
resolved before deploying, which fails loudly on anything missing:

```bash
fnox exec -- docker compose -f compose.prod.yaml config
```

`DOMAIN` is the single source of truth: it sets the certificate hostname,
`ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, and `WAGTAILADMIN_BASE_URL`. It
defaults to `blackpythondevs.org`, so a missing or half-filled env file can't
quietly fall back to `localhost` and 400 every request; override it to deploy a
staging host. `SECRET_KEY` and `POSTGRES_PASSWORD` have no defaults on purpose —
compose refuses to start without them. There is no `DEBUG` setting to get
wrong: `production.py` hardcodes `DEBUG = False`.

Verify the security posture at any time with:

```bash
fnox exec -- docker compose -f compose.prod.yaml exec web python manage.py check --deploy
```

### Admin access over Tailscale

The Wagtail admin (`/cms`) and the Django admin (`/django-admin`) return 404 on
the public domain. They are served only through the `tailscale` sidecar, at
`https://<TS_HOSTNAME>.<your-tailnet>.ts.net/cms/`. Sign-in is unchanged once
you are there — being on the tailnet is a gate in front of the login, not a
replacement for it.

The sidecar runs in userspace networking mode, so it needs no `NET_ADMIN`
capability, no `/dev/net/tun`, and no access to the host's network namespace: it
can reach the compose network and nothing else on the box. It does not advertise
a subnet route or an exit node either, so joining the tailnet grants access to
this stack alone.

Set up, in the Tailscale admin console:

1. **DNS** → enable MagicDNS *and* HTTPS Certificates. Without both, the sidecar
   cannot get a certificate for its `ts.net` name and will serve nothing.
2. **Access controls** → define `tag:server` with an owner.
3. **Settings → Keys** → generate a *reusable*, *pre-approved* auth key tagged
   `tag:server`.

Then set `TS_AUTHKEY`, `TS_HOSTNAME`, and `TS_FQDN` in `fnox.toml`.
`TS_FQDN` is the full MagicDNS name (`<TS_HOSTNAME>.<tailnet>.ts.net`) and gets
appended to `ALLOWED_HOSTS` and `CSRF_TRUSTED_ORIGINS` — a mismatch shows up as
a 400 rather than anything more obvious.

```bash
fnox exec -- docker compose -f compose.prod.yaml logs tailscale
fnox exec -- docker compose -f compose.prod.yaml exec tailscale tailscale status
```

The auth key is only used to register. Once the node is in the `tailscale_state`
volume it authenticates with its own key, so keep that volume across deploys —
losing it re-registers the node under a new identity and needs a fresh key.

To add someone, invite them to the tailnet; to cut access, remove them there.
Nothing about it touches Django's own permissions.

### Trying it locally under the real hostname

Set `CADDY_TLS_INTERNAL="tls internal"` and Caddy signs with its own local CA
instead of contacting Let's Encrypt — a failed validation from a machine the
domain does not point at would otherwise count against a rate limit of five per
hour for the domain.

```bash
CADDY_TLS_INTERNAL="tls internal" \
  fnox exec -- docker compose -f compose.prod.yaml up -d --build
curl -k --resolve blackpythondevs.org:443:127.0.0.1 https://blackpythondevs.org/
```

`--resolve` points curl at the local stack without touching `/etc/hosts`. Leave
the variable unset on the server; production issues real certificates.

### Loading a database dump

`pg_dump` custom-format dumps (`.dump`) restore with `pg_restore`, not `psql`:

```bash
fnox exec -- docker compose -f compose.prod.yaml exec -T db pg_restore -U bpd -d bpd --no-owner --no-privileges --clean --if-exists < bpd.dump
```

The dump carries the `CustomImage` rows but not the uploaded files, so on a
fresh `media_data` volume every blog and event header image points at a
`/media/...` path with nothing behind it. The originals are checked into
`static/images/`, so restoring them needs no backup:

```bash
fnox exec -- docker compose -f compose.prod.yaml exec web python manage.py restore_media --dry-run   # report, change nothing
fnox exec -- docker compose -f compose.prod.yaml exec web python manage.py restore_media
```

It copies each file back under the exact name the database already records — no
rows are rewritten — and drops the stale rendition rows so Wagtail regenerates
the resized versions on the next request. Images already in storage are skipped,
so re-running it is safe. Anything uploaded through the CMS since the export has
no counterpart in `static/images/` and is reported as unmatched; that needs a
real backup of the volume.

### Redeploying

```bash
git pull
fnox exec -- docker compose -f compose.prod.yaml up -d --build
fnox exec -- docker compose -f compose.prod.yaml exec web python manage.py migrate
```

Or `mise run deploy`, which is the two commands above.

Static files are collected into the image at build time, so a rebuild is all
that ships new CSS. The `caddy_data` volume holds issued certificates — keep it
across deploys, since Let's Encrypt rate-limits repeat issuance for a domain.

## Settings layout

```
bpd/settings/base.py         shared configuration
bpd/settings/dev.py          DEBUG, console email, debug toolbar   (manage.py default)
bpd/settings/production.py   HSTS, S3 media, SMTP, manifest static (wsgi.py default)
bpd/settings/local.py        optional, gitignored, imported by dev.py
```

## Tests

```bash
docker compose up -d db valkey
export DATABASE_URL=postgres://bpd:bpd@localhost:5432/bpd
export VALKEY_URL=redis://localhost:6379/0
uv run pytest
```

Coverage includes the bootstrap being idempotent, every page type rendering,
blog pagination and tag filtering, the allauth pages (which render without a
`page` in context), the Valkey cache round-trip, and the production storage
switch.

## Notes on the port

- Templates were ported from Jinja2 to the Django template language; `bpd.css`
  and the design system are unchanged apart from one absolute `/assets/` URL in
  the hero background, made relative so it survives static file hashing.
- The jQuery language switcher was dropped — the site is single-locale for now.
  `wagtail-localize` is the path back to multi-language if needed.
- Base templates use `{% firstof %}` rather than chained `default:` filters,
  because filter *arguments* raise when `page` is absent from the context.
