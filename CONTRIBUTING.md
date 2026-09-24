# Contributing

Thanks for helping with the Black Python Devs site. Everything you need to
contribute runs in development; you never need production access or secrets.

## Tools

| Tool | What it is for | Who needs it |
| --- | --- | --- |
| [Docker](https://docs.docker.com/get-docker/) | runs Postgres, Valkey, and the web app | everyone |
| [mise](https://mise.jdx.dev) | the task runner; every task lives in `mise.toml` | everyone (recommended) |
| [uv](https://docs.astral.sh/uv/) | Python dependencies, tests, and lint; `mise install` provides it | everyone |
| [fnox](https://fnox.jdx.dev) | decrypts production secrets and injects them as environment variables | maintainers who deploy |

`mise tasks` lists everything you can run. **Unprefixed tasks act on development;
`prod-*` tasks act on production.** As a contributor you will only use the
unprefixed ones.

## Development environment

```bash
cp .env.example .env    # dev-only defaults, gitignored
mise run up             # db, valkey, and the web app with live reload
mise run migrate
mise run bootstrap      # page tree, site settings, snippets (idempotent)
mise run superuser
```

The site is at <http://localhost:8000> and the CMS at
<http://localhost:8000/cms/>. Source is bind-mounted and `runserver`
autoreloads, so Python, template, and static changes show up on the next
request. `mise run restart` and `mise run rebuild` cover settings changes and
dependency changes.

Development uses `bpd.settings.dev` (DEBUG on, emails printed to the console,
media on the local filesystem). The values in `.env` are throwaway, so there is
nothing in it to protect. Discord and CARTO keys are optional; leave them blank
unless you are working on those features.

## Production environment

Production is a different environment, not a bigger version of yours:

- It runs `compose.swarm.yaml` as a Docker Swarm stack with
  `bpd.settings.production` (DEBUG hardcoded off), and gunicorn behind Caddy.
- Its configuration is in `fnox.toml`, which is age-encrypted, **gitignored**,
  and specific to the deploying host. Contributors don't have the key and don't
  need one.
- It is deployed by maintainers with `mise run prod-deploy`. Merging a PR does
  not deploy it.

`.env.production.example` lists the variable names production reads, and the
README's [Tooling and environments](README.md#tooling-and-environments) section
compares the two side by side.

## Making a change

1. Branch from `main`.
2. Make the change. Add or update tests in `tests/` for new behavior.
3. Run the checks:

   ```bash
   mise run lint
   mise run test
   ```

4. Open a pull request describing what changed and why.

### Migrations

Generate migrations in development and commit them:

```bash
mise run makemigrations
```

Production bakes the code into an image, so a migration created inside a running
production container is lost on the next deploy. Migrations must also be
backward-compatible with the previous release (add a column before removing
one): a deploy starts the new code before `prod-migrate` runs, so the new
version briefly runs against the old schema.

### Secrets

Never commit secrets, and never paste one into an issue or PR. These are
gitignored on purpose: `.env`, `.env.production`, `fnox.toml`, `*.dump`, and
`bpd/settings/local.py`. If you need a new setting in production, add its name
(with an empty value) to `.env.production.example` and tell a maintainer, who
will add the real value with `fnox set`.
