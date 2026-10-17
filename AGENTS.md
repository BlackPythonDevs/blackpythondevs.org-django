# AGENTS.md

Guidance for AI coding agents working on this repository: the Black Python Devs
community site, a Django 5.2 + Wagtail 7 application backed by PostgreSQL 17 and
Valkey 8, with django-allauth passwordless auth and WhiteNoise static files.

## The golden rule: use mise tasks

Everything runs through [mise](https://mise.jdx.dev); `mise.toml` is the
canonical task list (`mise tasks` to see it). **Unprefixed tasks act on
development; `prod-*` tasks act on production.** As an agent, never run
`prod-*` tasks or touch production in any way — contributors never need
production access or secrets.

### Common tasks

| Task | What it does |
| --- | --- |
| `mise run up` | Start the dev stack (db, valkey, web with live reload) |
| `mise run down` | Stop the dev stack, keeping volumes |
| `mise run logs` | Follow the web container's logs |
| `mise run migrate` | Apply migrations |
| `mise run makemigrations` | Generate migrations (files land in your checkout — commit them) |
| `mise run bootstrap` | Create page tree, site settings, snippets (idempotent) |
| `mise run test` | Run pytest on the host against the containerised db and valkey |
| `mise run lint` | Ruff check + format check |
| `mise run manage -- <cmd>` | Any `manage.py` command, e.g. `mise run manage -- shell` |
| `mise run restart` | Restart web (after settings changes or a wedged worker) |
| `mise run rebuild` | Rebuild web (needed after `pyproject.toml` / `uv.lock` changes) |
| `mise run shell` | Shell inside the dev web container |

### First-time setup

```bash
cp .env.example .env    # dev-only throwaway defaults; gitignored
mise run up
mise run migrate
mise run bootstrap      # idempotent
```

Site at <http://localhost:8000>, CMS at <http://localhost:8000/cms/>.

### Live reload behavior

Source is bind-mounted and `runserver` autoreloads, so Python, template, and
`static/` changes need **no command at all**. Only settings changes
(`mise run restart`) and dependency changes (`mise run rebuild`) do.

## Running tests and lint

Always run both before finishing a change:

```bash
mise run test
mise run lint
```

- Tests live in `tests/` (pytest + pytest-django + factory-boy). Add or update
  tests in `tests/` for any new behavior.
- Tests run on the host with `uv run pytest`, requiring the containerised
  db and valkey (`mise run test` handles both). Env:
  `DATABASE_URL=postgres://bpd:bpd@localhost:5432/bpd`,
  `VALKEY_URL=redis://localhost:6379/0`.
- Lint is Ruff with `line-length = 120`; migrations are excluded from
  formatting/linting.

Prefer `mise run` over raw `docker compose` / `uv` commands so behavior matches
what CI and other contributors see. Running outside Docker is possible (see
README's "Running outside Docker") but not the default.

## Project layout

```
manage.py            Django entrypoint (dev settings by default)
bpd/                 Project package
bpd/settings/        base.py, dev.py (manage.py default), production.py (wsgi.py)
home/                HomePage, AboutPage, SupportPage, StandardPage
blog/                BlogIndexPage, BlogPage
events/              EventIndexPage, EventPage, SponsoredEvent
users/               Custom user, allauth adapters, Discord integration
ambassadors/, communities/, elections/, nominations/, notifications/,
service_award/, sponsorships/, checklists/, community_messages/, core/
templates/           Django templates (ported from Jinja2)
static/              Design system assets ("Luminous Monolith", unchanged)
fixtures/            Seed data (from the static site's _data/)
tests/               pytest suite
```

## Domain conventions

- **Content model**: everything formerly in `_data/*.json` is editable in the
  Wagtail CMS. Page bodies are StreamFields. Snippets: `Author`, `Leader`,
  `Sponsor`, `Partner`, `FoundationalSupport`. Site settings live in the
  Wagtail Settings menu (navigation, announcement toast, social links, footer).
- **Sponsored events** carry a status (`requested → approved → completed →
  cancelled`) and a `paid` flag. Only **completed** ones render publicly;
  `amount` and `notes` are internal and never render.
- **Membership is passwordless**: allauth emails sign-in codes; no password is
  ever set. **Discord is connect-only, never a sign-in method** — keep
  `users/adapters.py`'s `is_open_for_signup` returning `False` for it.
- **Migrations must be backward-compatible**: a deploy runs new code briefly
  against the old schema (add a column before removing one). Never generate
  migrations inside production containers; commit ones made in dev.
- **Templates** use the Django template language, `{% firstof %}` rather than
  chained `default:` filters (filter arguments raise when `page` is absent from
  context). The design system in `static/` is unchanged from the original site.

## Secrets and safety

- **Never commit, print, or paste secrets** — not into issues, PRs, or logs.
  Gitignored on purpose: `.env`, `.env.production`, `fnox.toml`, `*.dump`,
  `bpd/settings/local.py`.
- Dev `.env` values are deliberately throwaway; nothing in it needs protecting.
- Pushes and PRs are scanned by betterleaks (`mise run scan-secrets`,
  `.betterleaks.toml`). If a scan flags a non-secret, widen the allowlist in
  `.betterleaks.toml` rather than lowering the confidence floor. Enable the
  pre-commit hook with `mise run install-hooks`.
- New production settings: add the name (empty value) to
  `.env.production.example` and tell a maintainer — real values come from
  `fnox set`, never from the repo.
- Don't run `prod-*` mise tasks, `docker stack` commands, or anything touching
  fnox. Production is deployed by maintainers with `mise run prod-deploy`;
  merging a PR does not deploy.

## Workflow for changes

1. Branch from `main`.
2. Make the change; add or update tests in `tests/`.
3. If you changed models, run `mise run makemigrations` and commit the files.
4. Run `mise run lint` and `mise run test`; fix everything they report.
5. Open a pull request describing what changed and why.

Further reading: `README.md` (architecture, deployment, content model) and
`CONTRIBUTING.md` (contributor-focused versions of the above).
