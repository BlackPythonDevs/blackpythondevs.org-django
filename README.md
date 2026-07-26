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

Seed data for the snippets lives in `fixtures/`, carried over from the static
site's `_data/` directory.

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

**Snippets** — `Author`, `Leader`, `Sponsor`, `Partner`, `FoundationalSupporter`.

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
production falls back to the local filesystem, so nothing breaks before storage
is provisioned.

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
