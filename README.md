# Kiro Credit Usage Web

[English](#english) · [简体中文](#简体中文)

A local-first, privacy-aware Kiro Credits usage dashboard for controlled company networks. It keeps the page shell static, refreshes a validated local JSON snapshot, preserves durable history, and keeps the last successful data visible when collection fails.

> **Status:** The repository is safe to publish as source code. It does **not** contain production AWS identifiers, credentials, refresh tokens, user records, email addresses, snapshots, or internal network addresses. Deployers must supply their own local configuration and must review the privacy and network requirements below.

---

<a id="english"></a>

## English

### What this project does

Kiro Credit Usage Web helps an administrator inspect current-month Kiro Credits usage before unused subscriptions become waste. It presents one account per row and intentionally does not merge accounts that may belong to the same person. The dashboard shows:

- current Shanghai calendar-month Credits, capacity, percentage, active dates, tier, tier source, and known monthly cost;
- overview KPIs, account-activity evidence, five usage bands, filtering, search, sorting, and the five newest historical summaries;
- a UTF-8 BOM CSV export containing `user_id`, full email, and dashboard fields;
- a local reload action that never calls AWS;
- an administrator-only full AWS refresh action;
- permanent local history and validated stale-data fallback.

The dashboard is bilingual. It selects Simplified Chinese for `navigator.language` values beginning with `zh`; all other browser languages default to English. The globe button in the existing action group switches language for the current page session. The preference is deliberately not stored in cookies, URLs, or browser storage. User names, emails, tier values, and unknown server-provided values remain unchanged.

### Project history and deliberate design choices

This repository began as a request for a quick way to review every subscriber's credit usage on demand and avoid wasting Kiro Credits. The following decisions are intentional:

1. **Independent project.** It has no runtime dependency on `kiro-user-activity-analytics` or any other local project.
2. **Local-first, portable later.** The first target is a Mac on a controlled network. The API and snapshot contract are separated so the same design can later move to another host, a reverse proxy, Linux, or containers.
3. **No production JavaScript runtime.** The production service uses Python 3.11+ standard-library HTTP components and AWS CLI v2. Node.js is only required for frontend development checks.
4. **A fixed page shell with replaceable data.** `web/` is static HTML, CSS, and JavaScript. The browser only consumes same-origin `/api/*` endpoints and never receives AWS credentials.
5. **One daily full refresh.** Upstream data commonly advances daily and may lag by one or two days. The intended external schedule is Beijing time 10:00 rather than frequent Athena polling.
6. **History over blank pages.** Successful snapshots are retained permanently. A failed refresh must preserve the last valid snapshot rather than replacing it with empty or partial data.
7. **Unknown is not zero.** An account with an unknown tier or zero capacity is classified as `unknown`, with `N/A` for capacity, percentage, and monthly cost. It is never presented as free or unused.
8. **Anonymous read access is a deployment choice, not a public-service design.** The code can support anonymous reads on a tightly controlled intranet. It must not be exposed directly to the public internet.
9. **Manual refresh requires a token.** The token is read from an owner-only file or an existing process environment variable, held by the server instance, used only for the request check, and removed from AWS CLI child-process environments.

### Architecture

```text
Browser
  └─ HTTP server on the deployment host
       ├─ static web/index.html + app.js + styles.css
       ├─ GET  /api/current      latest valid snapshot
       ├─ GET  /api/health       refresh and staleness state
       ├─ GET  /api/history      historical summary index
       ├─ GET  /api/export.csv   UTF-8 BOM export
       ├─ POST /api/reload       read local snapshot only
       └─ POST /api/refresh      token-protected AWS refresh

python -m app.refresh
  └─ AWS CLI v2 → Athena / S3 / IAM Identity Center
       └─ atomic local persistence
            ├─ data/current.json
            ├─ data/state.json
            └─ data/history/YYYY/MM/*.json
```

The browser has no AWS credentials and makes no direct AWS requests.

### Requirements

#### Production runtime

- Python **3.11+**.
- AWS CLI **v2**, already authenticated for the intended AWS account.
- Network access from the host to the configured AWS services.
- A writable local data directory.
- macOS only if using the supplied `launchd` renderer.

The application has no third-party Python runtime dependency.

#### Development and CI

- [uv](https://docs.astral.sh/uv/) 0.13.5 for locked Python development dependencies.
- Node.js 26 and npm 11 for frontend quality tooling only.
- Git.

```bash
uv sync --locked --all-groups
npm ci
```

### Quick start

1. Copy the sample without committing the result:

   ```bash
   cp config.example.toml config.local.toml
   ```

2. Edit only local values in `config.local.toml`. It is ignored by Git.

3. Confirm the AWS identity before any collection:

   ```bash
   aws sts get-caller-identity
   ```

   The resulting account must equal `aws.account_id` in the local configuration.

4. Run one refresh:

   ```bash
   python3 -m app.refresh --config config.local.toml
   ```

5. Preview locally without exposing the dashboard:

   ```bash
   python3 -m app.server \
     --config config.local.toml \
     --host 127.0.0.1 \
     --port 8080
   ```

6. Open `http://127.0.0.1:8080`.

For the manual refresh control, create an owner-only token file. Do not use an AWS secret, a personal password, or a token shared with another system.

```bash
chmod 600 .admin-token
python3 -m app.server \
  --config config.local.toml \
  --host 127.0.0.1 \
  --port 8080 \
  --admin-token-file .admin-token
```

The token must contain at least 16 characters. It is never included in API responses, logs, snapshots, CSV exports, or AWS CLI child-process environments.

### Configuration reference

`config.example.toml` is an intentionally safe template. Its server host defaults to `127.0.0.1`; setting `0.0.0.0` is an explicit deployment decision.

| Section   | Key                               | Meaning                                                                       |
| --------- | --------------------------------- | ----------------------------------------------------------------------------- |
| `server`  | `host`                            | Bind host. Keep `127.0.0.1` for local preview.                                |
| `server`  | `port`                            | TCP port, default `8080`.                                                     |
| `server`  | `web_dir`                         | Static asset directory, default `web`.                                        |
| `server`  | `stale_after_hours`               | Snapshot age that marks data stale.                                           |
| `server`  | `manual_refresh_cooldown_seconds` | Cooldown between accepted manual refreshes.                                   |
| `server`  | `request_timeout_seconds`         | Per-connection HTTP socket timeout.                                           |
| `server`  | `max_connections`                 | Maximum simultaneous HTTP connections.                                        |
| `storage` | `data_dir`                        | Local persistent snapshot directory.                                          |
| `aws`     | `profile`                         | Optional AWS CLI profile.                                                     |
| `aws`     | `region`                          | AWS region passed to AWS CLI.                                                 |
| `aws`     | `account_id`                      | Required 12-digit expected AWS account ID.                                    |
| `aws`     | `data_bucket`                     | Bucket containing optional roster and identity mapping objects.               |
| `aws`     | `database`                        | Athena database identifier.                                                   |
| `aws`     | `workgroup`                       | Athena WorkGroup with a scan cutoff.                                          |
| `aws`     | `identity_store_id`               | IAM Identity Center identity store ID.                                        |
| `aws`     | `application_arn`                 | Required when no authoritative subscription CSV is configured.                |
| `aws`     | `subscription_csv_key`            | Optional authoritative active-subscription roster object key.                 |
| `aws`     | `identity_mapping_key`            | Optional display-name/email mapping object key.                               |
| `aws`     | `max_query_scan_bytes`            | Local maximum scanned bytes per Athena query.                                 |
| `aws`     | `max_s3_object_bytes`             | Maximum roster or mapping object size.                                        |
| `aws`     | `max_athena_rows`                 | Maximum Athena result rows per query.                                         |
| `refresh` | `daily_time`                      | Intended daily local time in `HH:MM`; use `10:00` on an `Asia/Shanghai` host. |
| `refresh` | `retry_delays_seconds`            | Retry delays after a failed refresh.                                          |
| `refresh` | `jitter_ratio`                    | Retry jitter from `0` through `1`.                                            |

The loader rejects implicit type coercion, invalid account IDs, invalid Athena identifiers, malformed time values, non-positive limits, and missing roster sources.

### AWS source contract

This project is intentionally specific about its input contract. Validate these sources in a non-production environment before relying on the dashboard.

#### Athena usage table

The collector queries `"<database>"."user_report"`. The table must provide these columns:

| Column                 | Required shape                                                        | Use                                       |
| ---------------------- | --------------------------------------------------------------------- | ----------------------------------------- |
| `date`                 | `YYYY-MM-DD` text accepted by Athena `date_parse`                     | Shanghai-month cutoff and activity dates. |
| `userid`               | non-empty user identifier; a `directory-id.user-id` form is supported | Account key.                              |
| `credits_used`         | decimal-compatible value                                              | Monthly Credits.                          |
| `overage_credits_used` | decimal-compatible value                                              | Overage Credits.                          |
| `subscription_tier`    | tier label                                                            | Latest observed tier fallback.            |

The collector first queries the current Shanghai calendar month's `MAX(date)`. It then constrains monthly usage and tier fallback to that cutoff date plus one exclusive day. A missing cutoff produces `data_cutoff = null`; roster entries remain visible and zero values are explicitly not evidence of non-use.

#### Authoritative subscription CSV

`aws.subscription_csv_key` is optional. When configured and present, it is the preferred active roster source. It is decoded as UTF-8 or UTF-8 BOM and needs a header containing either `userid` or `user_id`.

Supported header aliases are:

| Canonical field    | Accepted headers                         |
| ------------------ | ---------------------------------------- |
| user ID            | `userid`, `user_id`                      |
| name               | `user_name`, `username`, `name`          |
| email              | `email`                                  |
| subscription state | `subscription_status`, `status`          |
| tier               | `subscription_tier`, `kiro_plan`, `plan` |
| activation date    | `activation_date`                        |
| source             | `plan_source`, `source`                  |

Accepted active states are `ACTIVE`, `ENABLED`, `SUBSCRIBED`, and `PENDING`. Explicit inactive states include `CANCELLED`, `CANCELED`, `INACTIVE`, `DELETED`, `DISABLED`, `EXPIRED`, `SUSPENDED`, `UNASSIGNED`, `UNSUBSCRIBED`, and `REVOKED`. A missing state defaults to `ACTIVE`; an unknown supplied state stops the refresh instead of guessing.

#### Identity mapping CSV

`aws.identity_mapping_key` is optional at runtime. If its S3 object is absent, collection continues without mapping overrides. It accepts UTF-8/UTF-8 BOM CSV and recognizes `userid` or `user_id`, `user_name`/`username`/`name`, and `email`.

#### IAM Identity Center fallback

Without an authoritative subscription CSV, the collector reads IAM Identity Center application assignments. Group display names are normalized to Kiro tier labels. Direct user assignments or unrecognized groups fall back to the last tier found at the data cutoff when available; otherwise the tier stays `Unknown`.

Recognized tier labels are normalized to `Pro`, `Pro+`, `Pro Max`, and `Power`. The capacity and known monthly USD values embedded in the current schema are: `Pro` 1,000 / $20; `Pro+` 2,000 / $40; `Pro Max` 5,000 / $100; `Power` 10,000 / $200. `Unknown` has capacity 0 and no known price. Review and update these values with tests when the authoritative pricing policy changes. Prices do not include taxes, discounts, negotiated rates, or currency conversion.

### Minimum AWS permissions

Use a dedicated, read-only role or profile with the narrowest resource scope possible. The exact resource ARNs depend on the deployment, table storage, WorkGroup output location, and IAM Identity Center setup.

The application calls these APIs:

```text
sts:GetCallerIdentity
athena:GetWorkGroup
athena:StartQueryExecution
athena:GetQueryExecution
athena:GetQueryResults
athena:StopQueryExecution
s3:HeadObject
s3:GetObject
sso:ListApplicationAssignments
identitystore:ListUsers
identitystore:DescribeUser
identitystore:DescribeGroup
identitystore:ListGroupMemberships
```

Athena may also require read permissions for the table's underlying data location, Glue metadata permissions such as `glue:GetTable` and `glue:GetPartitions`, and write/read permissions for the WorkGroup query-result location. Configure these separately according to your Athena and data-lake policy. Do not grant broad `s3:*`, `athena:*`, administrator, write, delete, or IAM mutation permissions merely to make this tool work.

Before collection, the code verifies that the configured WorkGroup has a positive `BytesScannedCutoffPerQuery` no larger than `aws.max_query_scan_bytes`. It also limits local result pages, rows, deadlines, and S3 object sizes. WorkGroup enforcement is the cost control; the post-query local scan check is an additional safeguard, not a replacement.

### Data semantics

- Time range: current Shanghai natural month.
- Cutoff: actual current-month maximum source date.
- Usage: cumulative through the cutoff.
- Tier precedence: authoritative CSV, recognized current IIC group, latest usage-record tier at the cutoff, then unknown direct assignment.
- User identity: one account row per canonical user ID; no person-level merging.
- `zero`: known capacity and Credits equal zero.
- `low`: nonzero Credits and utilization below 10%.
- `medium`: utilization from 10% through less than 50%.
- `normal`: utilization from 50% through 80% inclusive.
- `high`: utilization above 80%.
- `unknown`: missing or non-positive capacity, before zero usage is considered.
- Page and CSV Credits are rounded to an integer. Usage percentages are calculated from unrounded values, rounded upward, and capped at 100%. The snapshot retains source precision.
- The account-status panel is usage evidence only. A user is `Active` when Credits, active days, or activity dates exist at the cutoff; otherwise it remains unknown. It is not a subscription-lifecycle statement.

### Snapshot storage and recovery

Successful data is stored locally:

```text
data/current.json
data/state.json
data/history/manifest.json
data/history/YYYY/MM/<timestamp>-<hash>.json
```

A snapshot must pass the runtime schema-v1 validator before publication or serving. The validator verifies required fields, dates, tier/capacity/cost consistency, status consistency, summary totals, and content hashes.

Writes use a temporary file, `fsync`, directory synchronization, and `os.replace`. History is retained when meaningful content changes and at least once per day. On server startup, `reconcile()` rebuilds the history manifest from files and repairs a missing index entry after an interrupted write.

If `current.json` is invalid, the server uses the last validated in-memory snapshot when available, then searches validated historical snapshots. Bad `state.json` or manifest data becomes a safe error or empty-index state instead of crashing the HTTP server.

### Web API

| Method | Endpoint          | Response                                                             |
| ------ | ----------------- | -------------------------------------------------------------------- |
| `GET`  | `/api/current`    | Latest valid snapshot, or `503` if none exists.                      |
| `GET`  | `/api/health`     | Health, staleness, retry, and manual-refresh availability data.      |
| `GET`  | `/api/history`    | Newest-first historical metadata only, without historical user rows. |
| `GET`  | `/api/export.csv` | UTF-8 BOM CSV generated from the current valid snapshot.             |
| `POST` | `/api/reload`     | Reload the valid local snapshot; never calls AWS.                    |
| `POST` | `/api/refresh`    | Start background collection after `X-Refresh-Token` verification.    |

`POST` endpoints intentionally reject request bodies and transfer encodings. Responses include `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`, `X-Frame-Options: DENY`, and a restrictive same-origin Content Security Policy.

### Network and privacy deployment rules

This repository may be public; your deployment data must not be.

- Keep the default loopback bind for local use.
- A non-loopback bind prints a startup warning because the read API is anonymous and may expose names, full emails, and usage.
- Never map the port to the public internet.
- For any multi-user or cross-network deployment, place the service behind TLS, a network ACL or VPN, and individual authentication/authorization.
- Treat snapshots, CSV exports, launchd logs, and backups as personal or sensitive operational data according to your organization policy.
- Restrict the data directory to the service account, encrypt backups, define a retention policy, and test recovery from a copied data directory.
- Do not serve `data/` directly from a static server.
- Rotate a suspected leaked refresh token, restart the dashboard with a replacement token, and inspect access paths. Do not reuse AWS credentials as the refresh token.

### Refresh, retries, and daily scheduling

Run one immediate refresh:

```bash
python3 -m app.refresh --config config.local.toml
```

Run the retry wrapper:

```bash
python3 -m app.refresh --config config.local.toml --retry
```

Default retry delays are 60, 300, 900, and 1,800 seconds with ±20% jitter. Lock contention is retried without being recorded as a refresh failure. Other failures update `state.json`, retain the last successful snapshot, and leave retry metadata for health reporting.

#### macOS launchd

The renderer only creates a plist. It never installs, loads, unloads, or changes a LaunchAgent.

`launchd` schedules according to the host local timezone. The renderer refuses to create a plist unless the host timezone is confirmed as `Asia/Shanghai`, so a `daily_time = "10:00"` schedule remains Beijing 10:00.

```bash
python3 scripts/render_launchd.py --config config.local.toml
plutil -lint build/com.kiro.credit-usage.refresh.plist
```

Review the generated file before performing any system-level scheduler action. Installing, stopping, or removing a LaunchAgent changes user-level system state and must be approved by the operator. Monitor the generated `data/launchd.stdout.log` and `data/launchd.stderr.log`, rotate them according to local policy, and verify `/api/health` after the first scheduled run.

For host sleep, expired AWS SSO sessions, full disks, or exhausted retries: restore AWS authentication, free or extend storage, inspect the redacted health state and scheduler logs, run a controlled manual refresh, and confirm both `/api/health` and `/api/current`. Never delete the last valid snapshot as a first recovery action.

### Migration

`scripts/migrate_snapshot_v1.py` normalizes a legacy `data/current.json` into strict schema-v1 data.

```bash
python3 scripts/migrate_snapshot_v1.py --data-dir data
python3 scripts/migrate_snapshot_v1.py --data-dir data --apply
```

The first command is a read-only preview. The `--apply` command acquires the shared refresh lock before reading, normalizing, archiving the source in `data/legacy/`, publishing, and updating migration state. It prevents a concurrent refresh from overwriting or being overwritten by an old source snapshot.

### Quality gates and CI

Python quality commands:

```bash
.venv/bin/black --check app scripts tests
.venv/bin/ruff check app scripts tests
.venv/bin/mypy --strict app scripts tests
.venv/bin/pylint app scripts tests
.venv/bin/bandit -q -r app scripts
.venv/bin/pip-audit --strict
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -W error::ResourceWarning -m unittest discover -s tests -v
.venv/bin/coverage erase
PYTHONDONTWRITEBYTECODE=1 .venv/bin/coverage run -m unittest discover -s tests
.venv/bin/coverage report
```

Frontend quality command:

```bash
npm run check
```

The frontend gate includes ESLint, Prettier, HTML Validate, Stylelint, Vitest/JSDOM behavior tests, axe-core basic accessibility checks in both languages, and a production dependency audit. Python coverage uses branch measurement with a 75% minimum.

GitHub Actions in `.github/workflows/quality.yml` runs the locked Python and npm installs, all quality checks, secret-candidate scanning, and Git diff hygiene on pushes to `main` and pull requests. CI does not perform real AWS collection or scheduler installation. Real AWS integration testing must use an isolated account, synthetic data, a dedicated low-scan WorkGroup, and organization-approved credentials.

### Repository hygiene and contributions

Before committing:

```bash
git diff --check
git status --short
git check-ignore -v .admin-token config.local.toml data/current.json
```

Do not use blanket staging commands such as `git add .` or `git add -A`. Stage only intended source, tests, sample configuration, contracts, documentation, and lock files. Do not commit local configuration, credentials, refresh tokens, snapshots, CSV exports, real user data, AWS result files, build output, logs, virtual environments, or `node_modules`.

Run `detect-secrets` over all candidate source files before publishing or merging. `.gitignore` only prevents future staging; it cannot remove data already committed to history. If sensitive data is ever pushed, revoke or rotate it immediately and follow your platform's incident process rather than only adding it to `.gitignore`.

Contributions should include tests for behavior changes, preserve strict typing and static checks, update this document and the public snapshot contract when applicable, and explicitly review changes to tiers, costs, identity rules, privacy behavior, or AWS permissions.

### Portability and roadmap

The server and refresh process are intentionally separate:

```bash
python3 -m app.server
python3 -m app.refresh --retry
```

### Container deployment with Docker Compose

The `docker/` directory contains a portable Linux `docker/Dockerfile`, `docker/compose.yaml`, `docker/container.env.example`, and `docker/kiro-credit-usage.crontab.template`. Root `.dockerignore` remains with the repository-root build context so it excludes private configuration, credentials, snapshots, and development-only files. The image requires Docker BuildKit, which supplies `TARGETARCH`; it fails rather than guessing an architecture when that value is absent. Both the Python base image manifest and AWS CLI v2 archives are pinned by SHA-256. The image verifies the matching archive digest before installing it. Debian package downloads use the configurable Tsinghua TUNA mirror by default for China mainland connectivity; overseas deployments can override both Debian mirror variables with official `deb.debian.org` URLs. Debian repository Release signatures remain verified by APT. See the [AWS CLI v2 Linux installation documentation](https://docs.aws.amazon.com/cli/latest/userguide/install-cliv2.html).

Pushing an exact Git release tag such as `v0.1.1` runs the `Publish Docker image` GitHub Actions workflow. It builds and publishes one Docker Hub manifest for both `linux/amd64` and `linux/arm64` as `chowrex/kiro-credit-usage-web:0.1.1` and `chowrex/kiro-credit-usage-web:latest`. The workflow requires repository secrets named `DOCKERHUB_USERNAME` and `DOCKERHUB_TOKEN`. It does not publish untagged or branch builds.

Compose keeps two roles separate:

```text
web      Long-running dashboard, published directly on 0.0.0.0:8080.
refresh  One-shot refresh process, started manually or by host crontab.
```

Both services share the same writable host `data/` bind mount. The existing refresh lock prevents concurrent writers. Configuration and the host AWS profile directory are mounted read-only. The `web` service alone receives the administrator token file. Containers run as the numeric host service user, drop Linux capabilities, disallow privilege escalation, use a read-only root filesystem, and receive a writable temporary filesystem only at `/tmp`.

Bind mounts intentionally keep snapshots, configuration, and AWS profile material on the Docker daemon host rather than in the image. Web container logs remain managed by the Docker logging driver; the cron template writes its explicit refresh log to the host path you configure. Docker notes that bind mounts are tied to the host filesystem; mount only explicit paths and use read-only mounts where writes are not needed. See the [Docker bind-mount documentation](https://docs.docker.com/engine/storage/bind-mounts/).

#### Server preparation

Do not copy real files into the repository. On the server, create a protected deployment directory and a Compose environment file outside the checked-out source tree:

```bash
cp docker/container.env.example /etc/kiro-credit-usage/container.env
chmod 600 /etc/kiro-credit-usage/container.env
```

Set only absolute daemon-host paths in that environment file:

```dotenv
KIRO_UID=1000
KIRO_GID=1000
KIRO_CONFIG_FILE=/srv/kiro-credit-usage/config.local.toml
KIRO_DATA_DIR=/srv/kiro-credit-usage/data
KIRO_AWS_DIR=/srv/kiro-credit-usage/aws-profile
KIRO_ADMIN_TOKEN_FILE=/srv/kiro-credit-usage/.admin-token
KIRO_HTTP_PORT=8080
KIRO_IMAGE_TAG=0.1.1
DEBIAN_MIRROR=https://mirrors.tuna.tsinghua.edu.cn/debian
DEBIAN_SECURITY_MIRROR=https://mirrors.tuna.tsinghua.edu.cn/debian-security
```

`KIRO_UID` and `KIRO_GID` must match the owner of the config, data directory, AWS profile directory, and token file. The token file must be mode `0600` or stricter. This Compose file is designed for a standard rootful Docker daemon with matching numeric UID mapping. Verify ownership separately before using rootless Docker or userns-remap. This preserves the application's owner-only token check while allowing the container to write only the mounted data directory.

Mount a standard AWS profile directory at `KIRO_AWS_DIR`; the profile name and region remain in the private `config.local.toml`. Keep `storage.data_dir = "data"` or set it explicitly to `/app/data`, because an unrelated host absolute path resolves inside the container's read-only root filesystem. No AWS account, partition, endpoint, region, profile name, ARN, or Identity Center identifier is baked into the image. AWS CLI selects the appropriate international or China partition from the configured profile and region. An SSO profile can be read from this mount, but unattended cron refreshes will fail after the cached SSO session expires. Profiles whose credential helpers require a writable local cache may fail for the same reason. For unattended operation, use a renewable credential mechanism approved for the server.

Validate Compose interpolation before starting containers:

```bash
/usr/bin/docker compose \
  --env-file /etc/kiro-credit-usage/container.env \
  -f docker/compose.yaml config
```

For a local source build after review, set `KIRO_IMAGE_TAG=local` and start only the web service:

```bash
/usr/bin/docker compose \
  --env-file /etc/kiro-credit-usage/container.env \
  -f docker/compose.yaml up --build --detach web
```

For a server or any host testing the published multi-architecture image, retain a released `KIRO_IMAGE_TAG` such as `0.1.1`, then pull it and start without building:

```bash
/usr/bin/docker compose \
  --env-file /etc/kiro-credit-usage/container.env \
  -f docker/compose.yaml pull web
/usr/bin/docker compose \
  --env-file /etc/kiro-credit-usage/container.env \
  -f docker/compose.yaml up --no-build --detach web
```

The direct host-port binding follows the initial intranet deployment decision. It remains anonymous HTTP read access and must never be exposed to the public internet. Add TLS, network restrictions, and individual authentication before any broader deployment.

Run one controlled refresh container when needed from the already pulled or locally built image:

```bash
/usr/bin/docker compose \
  --env-file /etc/kiro-credit-usage/container.env \
  -f docker/compose.yaml run --rm --no-build refresh
```

This command can issue Athena queries and update the host data directory. It does not receive the administrator refresh token file.

#### Host crontab template

Cron is a host scheduler, not a third container. The provided template starts an ephemeral `refresh` container at Beijing 10:00 and removes it after completion:

```text
docker/kiro-credit-usage.crontab.template
```

After replacing its absolute path placeholders and reviewing it, an operator may install the line in the dedicated service account's crontab. The Compose environment file must be readable by that same account, and the parent directory of the configured cron log path must already exist and be writable before installation. The template uses `CRON_TZ=Asia/Shanghai`, an explicit Docker path, an explicit Compose environment file, and an explicit log path. The project never installs or edits crontab automatically.

Cron does not automatically catch up after host downtime. If missed-run recovery, journal integration, or stricter service isolation becomes important, replace the host cron line with a timezone-aware systemd timer such as `OnCalendar=*-*-* 10:00:00 Asia/Shanghai` and `Persistent=true`.

The frontend depends on `/api/*` and schema-v1 snapshots, so the server implementation can later change without rebuilding the page shell. Future work remains out of scope: public hosting, automatic firewall changes, Cognito setup, public-read deployment, and automatic scheduler installation.

### License and names

Copyright 2026 ChowRex. This project is licensed under the [Apache License 2.0](LICENSE).

Kiro and AWS names are used only to describe compatible services. This project is not an official product of, and is not endorsed by, Amazon Web Services or any Kiro service provider. Apache-2.0 does not grant trademark rights.

---

<a id="简体中文"></a>

## 简体中文

### 项目用途

Kiro Credit Usage Web 是一个本地优先、面向受控公司网络的 Kiro Credits 用量看板。它用于快速查看当前自然月所有订阅账号的 Credits 使用情况，帮助管理员识别闲置账号和潜在浪费。

页面每个账号单独成行。即使多个账号属于同一人，也不会合并。看板提供：

- 上海时区当月的 Credits、套餐容量、使用率、活跃日期、套餐、套餐来源和已知月成本；
- 总览 KPI、账户活跃证据、五档使用量分布、搜索、筛选、排序和最近五份历史摘要；
- 含 `user_id`、完整邮箱和页面核心字段的 UTF-8 BOM CSV 导出；
- 只重新读取本地数据、绝不调用 AWS 的“重新读取”；
- 需要管理员 Token 的完整 AWS 刷新；
- 永久本地历史，以及刷新失败或当前快照损坏时的有效旧数据回退。

页面支持中英双语。浏览器语言以 `zh` 开头时默认中文，其他语言默认 English。顶部现有操作区中的地球图标仅切换当前页面会话语言，不会将语言偏好写入 Cookie、URL 或浏览器存储。用户名、邮箱、套餐名称和无法识别的服务端原始值不会被翻译或改写。

### 项目背景与核心决策

本项目最初源于“快速查看所有订阅用户的 Credits 使用量，避免 Credits 浪费”的需求。以下设计均为刻意选择：

1. **完全独立。** 运行时不依赖 `kiro-user-activity-analytics` 或其他本地项目。
2. **先本地、后迁移。** 首先运行在受控网络中的 Mac 上；Web API 与快照契约独立，因此后续可迁移到其他主机、反向代理、Linux 或容器。
3. **生产环境不依赖 Node.js。** 服务端仅使用 Python 3.11+ 标准库和 AWS CLI v2。Node.js 只用于前端开发质量检查。
4. **固定页面，替换快照。** `web/` 中是固定 HTML、CSS 和 JavaScript。浏览器只调用同源 `/api/*`，不会得到 AWS 凭证。
5. **每天一次完整刷新。** 上游数据通常每天更新，并可能滞后 1–2 天，因此默认目标是北京时间每天 10:00，而不是频繁执行 Athena 查询。
6. **优先保留历史。** 成功快照永久保留。刷新失败时必须继续展示最后有效快照，不能用空数据或局部数据覆盖。
7. **未知不是零。** 套餐未知或容量不大于零的账号归类为 `unknown`，容量、使用率和成本显示 `N/A`，绝不显示为免费或零使用。
8. **匿名读取只是受控内网的部署选择。** 代码可以用于严格受控的企业内网匿名读取，但绝不能直接暴露到公网。
9. **手动刷新必须持有 Token。** Token 来自仅当前用户可读的文件或既有环境变量，保存在服务实例中，仅用于请求校验，并会从 AWS CLI 子进程环境中移除。

### 架构

```text
浏览器
  └─ 部署主机上的 HTTP 服务
       ├─ 固定 web/index.html + app.js + styles.css
       ├─ GET  /api/current      最新有效快照
       ├─ GET  /api/health       刷新和陈旧状态
       ├─ GET  /api/history      历史摘要索引
       ├─ GET  /api/export.csv   UTF-8 BOM CSV
       ├─ POST /api/reload       只重读本地快照
       └─ POST /api/refresh      Token 保护的 AWS 刷新

python -m app.refresh
  └─ AWS CLI v2 → Athena / S3 / IAM Identity Center
       └─ 原子化本地存储
            ├─ data/current.json
            ├─ data/state.json
            └─ data/history/YYYY/MM/*.json
```

浏览器不持有 AWS 凭证，也不会直接请求 AWS。

### 环境要求

#### 生产运行环境

- Python **3.11+**。
- 已完成预期账号认证的 AWS CLI **v2**。
- 主机到已配置 AWS 服务的网络连通性。
- 可写的本地数据目录。
- 仅在使用提供的 `launchd` 渲染器时需要 macOS。

应用运行时没有第三方 Python 包依赖。

#### 开发和 CI 环境

- 用于锁定 Python 开发依赖的 [uv](https://docs.astral.sh/uv/) 0.13.5。
- 仅用于前端质量工具的 Node.js 26 与 npm 11。
- Git。

```bash
uv sync --locked --all-groups
npm ci
```

### 快速开始

1. 复制样例，且不要提交复制后的本地文件：

   ```bash
   cp config.example.toml config.local.toml
   ```

2. 仅在 `config.local.toml` 填写本地值。该文件已经被 Git 忽略。

3. 在首次采集前确认 AWS 身份：

   ```bash
   aws sts get-caller-identity
   ```

   返回的账号必须等于本地配置中的 `aws.account_id`。

4. 执行一次刷新：

   ```bash
   python3 -m app.refresh --config config.local.toml
   ```

5. 使用仅本机监听方式预览：

   ```bash
   python3 -m app.server \
     --config config.local.toml \
     --host 127.0.0.1 \
     --port 8080
   ```

6. 打开 `http://127.0.0.1:8080`。

如需启用手动刷新按钮，请创建仅当前用户可读的 Token 文件。不要使用 AWS Secret、个人密码或其他系统共用 Token。

```bash
chmod 600 .admin-token
python3 -m app.server \
  --config config.local.toml \
  --host 127.0.0.1 \
  --port 8080 \
  --admin-token-file .admin-token
```

Token 至少 16 个字符。它不会出现在 API 响应、日志、快照、CSV 导出或 AWS CLI 子进程环境中。

### 配置说明

`config.example.toml` 是安全默认的示例。其服务监听地址为 `127.0.0.1`；改为 `0.0.0.0` 必须是部署者明确作出的内网暴露决定。

| 区段      | 键                                | 含义                                                          |
| --------- | --------------------------------- | ------------------------------------------------------------- |
| `server`  | `host`                            | 监听地址。本机预览应保持 `127.0.0.1`。                        |
| `server`  | `port`                            | TCP 端口，默认 `8080`。                                       |
| `server`  | `web_dir`                         | 静态资源目录，默认 `web`。                                    |
| `server`  | `stale_after_hours`               | 快照被标记为陈旧的小时数。                                    |
| `server`  | `manual_refresh_cooldown_seconds` | 两次可接受手动刷新之间的冷却时间。                            |
| `server`  | `request_timeout_seconds`         | 单个 HTTP 连接的 socket 超时。                                |
| `server`  | `max_connections`                 | 最大并发 HTTP 连接数。                                        |
| `storage` | `data_dir`                        | 本地持久化快照目录。                                          |
| `aws`     | `profile`                         | 可选 AWS CLI profile。                                        |
| `aws`     | `region`                          | 传递给 AWS CLI 的区域。                                       |
| `aws`     | `account_id`                      | 必填的 12 位预期 AWS 账号。                                   |
| `aws`     | `data_bucket`                     | 可选名册和身份映射对象所在 bucket。                           |
| `aws`     | `database`                        | Athena 数据库标识符。                                         |
| `aws`     | `workgroup`                       | 配有扫描上限的 Athena WorkGroup。                             |
| `aws`     | `identity_store_id`               | IAM Identity Center identity store ID。                       |
| `aws`     | `application_arn`                 | 未配置权威订阅 CSV 时必填。                                   |
| `aws`     | `subscription_csv_key`            | 可选的权威活跃订阅名册对象键。                                |
| `aws`     | `identity_mapping_key`            | 可选的显示名/邮箱映射对象键。                                 |
| `aws`     | `max_query_scan_bytes`            | 每条 Athena 查询的本地扫描字节上限。                          |
| `aws`     | `max_s3_object_bytes`             | 名册或映射对象的最大大小。                                    |
| `aws`     | `max_athena_rows`                 | 每条 Athena 查询最大结果行数。                                |
| `refresh` | `daily_time`                      | `HH:MM` 每日目标时间；在 `Asia/Shanghai` 主机上使用 `10:00`。 |
| `refresh` | `retry_delays_seconds`            | 刷新失败后的重试延迟。                                        |
| `refresh` | `jitter_ratio`                    | `0` 到 `1` 的重试抖动比例。                                   |

加载器会拒绝隐式类型转换、错误账号 ID、错误 Athena 标识符、无效时间、非正数限制和缺少名册来源的配置。

### AWS 数据源契约

项目明确约束输入数据。依赖看板前，应先在非生产环境验证这些数据源。

#### Athena 用量表

采集器查询 `"<database>"."user_report"`，表必须提供以下列：

| 列                     | 所需形态                                       | 用途                       |
| ---------------------- | ---------------------------------------------- | -------------------------- |
| `date`                 | Athena `date_parse` 可解析的 `YYYY-MM-DD` 文本 | 上海月份截止日和活动日期。 |
| `userid`               | 非空用户 ID；支持 `directory-id.user-id` 格式  | 账号键。                   |
| `credits_used`         | 可转换为 decimal 的值                          | 月度 Credits。             |
| `overage_credits_used` | 可转换为 decimal 的值                          | 超额 Credits。             |
| `subscription_tier`    | 套餐文本                                       | 观察到的最新套餐回退。     |

采集器先查询当前上海自然月的 `MAX(date)`，再将月度用量和套餐回退限制到该截止日加一天的开区间。没有截止日时，生成 `data_cutoff = null`；名册账号仍会展示，并明确说明零值不能证明未使用。

#### 权威订阅 CSV

`aws.subscription_csv_key` 可选。配置并存在时，它是优先的活跃名册来源。文件使用 UTF-8 或 UTF-8 BOM 解码，表头必须包含 `userid` 或 `user_id`。

支持的字段别名：

| 标准字段 | 支持表头                                 |
| -------- | ---------------------------------------- |
| 用户 ID  | `userid`、`user_id`                      |
| 名称     | `user_name`、`username`、`name`          |
| 邮箱     | `email`                                  |
| 订阅状态 | `subscription_status`、`status`          |
| 套餐     | `subscription_tier`、`kiro_plan`、`plan` |
| 激活日期 | `activation_date`                        |
| 来源     | `plan_source`、`source`                  |

接受的活跃状态为 `ACTIVE`、`ENABLED`、`SUBSCRIBED`、`PENDING`。明确非活跃状态包括 `CANCELLED`、`CANCELED`、`INACTIVE`、`DELETED`、`DISABLED`、`EXPIRED`、`SUSPENDED`、`UNASSIGNED`、`UNSUBSCRIBED`、`REVOKED`。缺少状态时默认 `ACTIVE`；显式提供但无法识别的状态会使刷新失败，而不是猜测。

#### 身份映射 CSV

`aws.identity_mapping_key` 在运行时可选。其 S3 对象不存在时，采集会继续执行但没有映射覆盖。文件支持 UTF-8/UTF-8 BOM CSV，识别 `userid` 或 `user_id`、`user_name`/`username`/`name`、`email`。

#### IAM Identity Center 回退

没有权威订阅 CSV 时，采集器读取 IAM Identity Center 应用分配。组显示名会归一化为 Kiro 套餐。直接分配用户或未知组优先回退到截止日内最后一次观察到的套餐；无法获得时保持 `Unknown`。

可识别套餐会归一化为 `Pro`、`Pro+`、`Pro Max`、`Power`。当前嵌入契约的容量和已知 USD 月成本为：`Pro` 1,000 / $20；`Pro+` 2,000 / $40；`Pro Max` 5,000 / $100；`Power` 10,000 / $200。`Unknown` 容量为 0，成本未知。价格变化时必须结合测试审查和更新；这些数值不含税费、折扣、协商价格和汇率。

### 最小 AWS 权限

应使用专用只读角色或 profile，并将资源范围尽量收窄。准确 ARN 依赖实际 WorkGroup、表底层数据、查询结果位置和 Identity Center 配置。

应用会调用：

```text
sts:GetCallerIdentity
athena:GetWorkGroup
athena:StartQueryExecution
athena:GetQueryExecution
athena:GetQueryResults
athena:StopQueryExecution
s3:HeadObject
s3:GetObject
sso:ListApplicationAssignments
identitystore:ListUsers
identitystore:DescribeUser
identitystore:DescribeGroup
identitystore:ListGroupMemberships
```

Athena 还可能需要表底层数据位置读取权限、如 `glue:GetTable` 和 `glue:GetPartitions` 的 Glue 元数据权限，以及 WorkGroup 查询结果位置的读写权限。应依据 Athena 与数据湖策略单独配置。不要为了运行本工具而授予宽泛的 `s3:*`、`athena:*`、管理员、写入、删除或 IAM 修改权限。

提交 Athena 查询前，代码会验证 WorkGroup 的 `BytesScannedCutoffPerQuery` 已配置、为正且不大于 `aws.max_query_scan_bytes`。同时还限制本地结果页数、结果行数、截止时间和 S3 对象大小。WorkGroup 是主要费用保护；查询完成后的本地扫描量检查只是额外保护。

### 数据口径

- 范围：当前上海自然月。
- 截止日：当月实际最大源日期。
- 用量：累计到截止日。
- 套餐优先级：权威 CSV、当前可识别 IIC 组、截止日观察到的最新用量记录套餐、未知直接分配。
- 用户身份：每个标准化用户 ID 一行，不做人员层面合并。
- `zero`：容量已知且 Credits 等于零。
- `low`：Credits 非零且使用率低于 10%。
- `medium`：使用率 10% 至小于 50%。
- `normal`：使用率 50% 至 80%（含）。
- `high`：使用率大于 80%。
- `unknown`：容量缺失或不大于零，且优先于零使用判断。
- 页面和 CSV 将 Credits 四舍五入为整数。使用率从未取整 Credits 计算、向上取整并封顶 100%。快照保留源精度。
- 账户状态面板仅表示用量证据。截止日有 Credits、活跃天数或活动日期时显示 Active，否则未知；它不是订阅生命周期状态。

### 快照存储与恢复

成功数据保存于：

```text
data/current.json
data/state.json
data/history/manifest.json
data/history/YYYY/MM/<timestamp>-<hash>.json
```

每份快照在发布和服务前都必须通过 schema-v1 运行时验证。验证器会检查字段、日期、套餐/容量/成本一致性、状态一致性、汇总和内容哈希。

写入过程使用临时文件、`fsync`、目录同步和 `os.replace`。内容变化时写入历史，且每天至少保留一份。服务启动时 `reconcile()` 会根据历史文件重建 manifest，修复中断写入后的索引缺失。

`current.json` 无法解析或验证失败时，服务优先使用内存中的最后有效快照，其次搜索有效历史快照。错误的 `state.json` 或 manifest 会变为安全错误状态或空索引，不会导致 HTTP 服务崩溃。

### Web API

| 方法   | 路径              | 响应                                       |
| ------ | ----------------- | ------------------------------------------ |
| `GET`  | `/api/current`    | 最新有效快照；没有可用快照时返回 `503`。   |
| `GET`  | `/api/health`     | 健康、陈旧、重试和手动刷新可用性。         |
| `GET`  | `/api/history`    | 按新到旧排列的历史元数据，不含历史用户行。 |
| `GET`  | `/api/export.csv` | 从当前有效快照生成 UTF-8 BOM CSV。         |
| `POST` | `/api/reload`     | 重读本地有效快照，不调用 AWS。             |
| `POST` | `/api/refresh`    | 验证 `X-Refresh-Token` 后启动后台采集。    |

POST 接口刻意拒绝请求体和 transfer encoding。响应包含 `X-Content-Type-Options: nosniff`、`Referrer-Policy: no-referrer`、`X-Frame-Options: DENY` 和严格同源 CSP。

### 网络与隐私部署规则

仓库可以公开，部署数据绝不能公开。

- 本机使用时保持 loopback 默认监听。
- 监听非 loopback 地址时，服务会打印启动警告，因为匿名读取接口可能暴露姓名、完整邮箱和用量。
- 不要把端口映射到公网。
- 多用户或跨网络部署时，必须置于 TLS、网络 ACL 或 VPN，以及个人认证/授权之后。
- 根据组织策略，将快照、CSV、launchd 日志和备份视为个人数据或敏感运营数据。
- 数据目录只授予服务账号访问，备份应加密，需定义保留策略，并定期从数据目录副本演练恢复。
- 不要将 `data/` 直接作为静态目录暴露。
- 怀疑刷新 Token 泄露时，立即轮换 Token、使用新 Token 重启看板并检查访问路径。不要复用 AWS 凭证作为刷新 Token。

### 刷新、重试与每天调度

立即执行一次刷新：

```bash
python3 -m app.refresh --config config.local.toml
```

执行带重试包装的刷新：

```bash
python3 -m app.refresh --config config.local.toml --retry
```

默认重试延迟为 60、300、900、1,800 秒，并带 ±20% 抖动。锁竞争会被重试，且不会记录为刷新失败。其他失败会更新 `state.json`、保留最后成功快照，并为健康接口留下重试元数据。

#### macOS launchd

渲染器只生成 plist，绝不会安装、加载、卸载或修改 LaunchAgent。

`launchd` 使用宿主机本地时区调度。渲染器只在宿主机时区确认是 `Asia/Shanghai` 时生成 plist，以确保 `daily_time = "10:00"` 就是北京时间每天 10:00。

```bash
python3 scripts/render_launchd.py --config config.local.toml
plutil -lint build/com.kiro.credit-usage.refresh.plist
```

任何系统级定时任务动作前都必须人工审查生成文件。安装、停止或删除 LaunchAgent 会修改用户级系统状态，必须由操作者明确确认。应监控 `data/launchd.stdout.log` 和 `data/launchd.stderr.log`，按本地策略轮转，并在首次计划运行后检查 `/api/health`。

如果主机休眠、AWS SSO 登录过期、磁盘已满或重试耗尽：恢复 AWS 认证、释放或扩展磁盘、检查脱敏健康状态和调度日志，执行受控手动刷新，并确认 `/api/health` 与 `/api/current`。恢复时不要先删除最后有效快照。

### 迁移

`scripts/migrate_snapshot_v1.py` 可以将旧版 `data/current.json` 规范化为严格 schema-v1 数据。

```bash
python3 scripts/migrate_snapshot_v1.py --data-dir data
python3 scripts/migrate_snapshot_v1.py --data-dir data --apply
```

第一条命令只读预览。`--apply` 会在一次共享刷新锁中完成读取、规范化、将源文件归档至 `data/legacy/`、发布和更新状态。因此常规刷新无法与旧快照迁移互相覆盖。

### 质量门禁与 CI

Python 质量检查：

```bash
.venv/bin/black --check app scripts tests
.venv/bin/ruff check app scripts tests
.venv/bin/mypy --strict app scripts tests
.venv/bin/pylint app scripts tests
.venv/bin/bandit -q -r app scripts
.venv/bin/pip-audit --strict
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -W error::ResourceWarning -m unittest discover -s tests -v
.venv/bin/coverage erase
PYTHONDONTWRITEBYTECODE=1 .venv/bin/coverage run -m unittest discover -s tests
.venv/bin/coverage report
```

前端完整质量检查：

```bash
npm run check
```

前端门禁包含 ESLint、Prettier、HTML Validate、Stylelint、Vitest/JSDOM 行为测试、两种语言下的 axe-core 基础无障碍检查和生产依赖审计。Python 覆盖率启用分支统计，最低门槛为 75%。

`.github/workflows/quality.yml` 会在推送到 `main` 和 Pull Request 时执行锁定依赖安装、全部质量检查、密钥候选扫描和 Git diff 检查。CI 不会执行真实 AWS 查询或安装调度器。真实 AWS 集成验证必须使用隔离账号、合成数据、低扫描量 WorkGroup 和组织批准的凭证。

### 仓库卫生与贡献

提交前执行：

```bash
git diff --check
git status --short
git check-ignore -v .admin-token config.local.toml data/current.json
```

不要使用 `git add .` 或 `git add -A` 这类全量暂存命令。只暂存明确的源码、测试、配置样例、契约、文档和锁文件。不要提交本地配置、凭证、刷新 Token、快照、CSV、真实用户数据、AWS 结果、构建物、日志、虚拟环境或 `node_modules`。

公开、合并或发布前，应使用 `detect-secrets` 扫描所有候选源码。`.gitignore` 只能阻止未来暂存，不能移除已进入历史的敏感数据。误推敏感数据时，应立即撤销或轮换，并遵循平台事件流程，而不是只追加 `.gitignore`。

贡献应为行为变化补充测试，保持严格类型和静态检查；修改套餐、成本、身份规则、隐私行为或 AWS 权限时，必须更新本文档和公开快照契约。

### 可移植性与路线图

Web 服务与刷新进程有意分离：

```bash
python3 -m app.server
python3 -m app.refresh --retry
```

### Docker Compose 容器化部署

`docker/` 目录集中保存可移植 Linux `docker/Dockerfile`、`docker/compose.yaml`、`docker/container.env.example` 和 `docker/kiro-credit-usage.crontab.template`。根目录 `.dockerignore` 与仓库根 build context 保持在一起，用于排除私有配置、凭证、快照和仅开发期文件。镜像需要 Docker BuildKit 提供 `TARGETARCH`，缺失时会明确失败而不猜测架构。Python 基础镜像 manifest 和 AWS CLI v2 安装包均使用 SHA-256 固定，安装前会验证对应归档摘要。Debian 软件包下载默认使用适配中国大陆网络的清华 TUNA 镜像；海外部署可用官方 `deb.debian.org` URL 覆盖两个 Debian 镜像变量。APT 仍会验证 Debian 仓库 Release 签名。参见 [AWS CLI v2 Linux 安装文档](https://docs.aws.amazon.com/cli/latest/userguide/install-cliv2.html)。

推送精确 Git 发布 tag，例如 `v0.1.1`，会运行 `Publish Docker image` GitHub Actions 工作流。它会构建并发布同时支持 `linux/amd64` 与 `linux/arm64` 的单个 Docker Hub manifest，标签为 `chowrex/kiro-credit-usage-web:0.1.1` 和 `chowrex/kiro-credit-usage-web:latest`。工作流需要名为 `DOCKERHUB_USERNAME` 和 `DOCKERHUB_TOKEN` 的仓库 Secret，不会发布无 tag 或分支构建。

Compose 将两个角色分离：

```text
web      长期运行的看板，按初始方案直接发布到 0.0.0.0:8080。
refresh  一次性刷新进程，仅由人工或宿主机 crontab 启动。
```

两个服务共享同一个可写的宿主机 `data/` bind mount，现有刷新锁会阻止并发写入。配置文件和宿主机 AWS profile 目录以只读方式挂载，只有 `web` 服务挂载管理员 Token 文件。容器使用宿主机服务账号的数字 UID/GID 运行，移除 Linux capabilities，禁止权限提升，根文件系统只读，只在 `/tmp` 提供可写临时文件系统。

Bind mount 有意让快照、凭证、配置和日志保留在 Docker daemon 宿主机而不是镜像中。Docker 说明 bind mount 依赖宿主机文件系统，因此只挂载明确路径，并对不需要写入的路径使用只读挂载。参见 [Docker bind-mount 文档](https://docs.docker.com/engine/storage/bind-mounts/)。

#### 服务器准备

不要把真实文件复制到仓库中。在服务器上创建受保护的部署目录，并在检出的源码目录之外创建 Compose 环境文件：

```bash
cp docker/container.env.example /etc/kiro-credit-usage/container.env
chmod 600 /etc/kiro-credit-usage/container.env
```

环境文件中只填写 Docker daemon 宿主机的绝对路径，并保留或按部署地区覆盖 Debian 镜像变量：

```dotenv
KIRO_UID=1000
KIRO_GID=1000
KIRO_CONFIG_FILE=/srv/kiro-credit-usage/config.local.toml
KIRO_DATA_DIR=/srv/kiro-credit-usage/data
KIRO_AWS_DIR=/srv/kiro-credit-usage/aws-profile
KIRO_ADMIN_TOKEN_FILE=/srv/kiro-credit-usage/.admin-token
KIRO_HTTP_PORT=8080
KIRO_IMAGE_TAG=0.1.1
DEBIAN_MIRROR=https://mirrors.tuna.tsinghua.edu.cn/debian
DEBIAN_SECURITY_MIRROR=https://mirrors.tuna.tsinghua.edu.cn/debian-security
```

`KIRO_UID` 和 `KIRO_GID` 必须与配置、数据目录、AWS profile 目录和 Token 文件的拥有者一致。Token 文件权限必须为 `0600` 或更严格。该 Compose 文件按常规 rootful Docker daemon 且数字 UID 映射一致的场景设计；使用 rootless Docker 或 userns-remap 前必须单独验证文件所有权。Debian APT 默认使用清华 TUNA 镜像以适配中国大陆网络；海外部署可将两个 `DEBIAN_*_MIRROR` 变量覆盖为官方 `https://deb.debian.org` URL。这样既保留应用的 owner-only Token 校验，也只允许容器写入挂载的数据目录。

将标准 AWS profile 目录挂载为 `KIRO_AWS_DIR`。profile 名称和 region 仍保留在私有 `config.local.toml` 中。`storage.data_dir` 必须保持为 `"data"`，或显式设为 `/app/data`，因为其他宿主机绝对路径会在容器只读根文件系统内解析。镜像不包含任何 AWS 账号、分区、端点、region、profile 名称、ARN 或 Identity Center 标识。AWS CLI 根据 profile 与 region 选择国际区或中国区对应分区。可以只读挂载 SSO profile，但无人值守的 cron 刷新会在 SSO 缓存会话过期后失败。依赖可写本地缓存的 credential helper 也可能因为同一原因失败。长期无人值守应使用服务器认可的可续期凭证机制。

启动前先验证 Compose 变量插值：

```bash
/usr/bin/docker compose \
  --env-file /etc/kiro-credit-usage/container.env \
  -f docker/compose.yaml config
```

人工审查后，如需在本地从源码构建，请设置 `KIRO_IMAGE_TAG=local` 并仅启动 Web 服务：

```bash
/usr/bin/docker compose \
  --env-file /etc/kiro-credit-usage/container.env \
  -f docker/compose.yaml up --build --detach web
```

服务器或其他测试已发布多架构镜像的主机应保留已发布的 `KIRO_IMAGE_TAG`，例如 `0.1.1`，然后拉取镜像并在不构建的情况下启动：

```bash
/usr/bin/docker compose \
  --env-file /etc/kiro-credit-usage/container.env \
  -f docker/compose.yaml pull web
/usr/bin/docker compose \
  --env-file /etc/kiro-credit-usage/container.env \
  -f docker/compose.yaml up --no-build --detach web
```

直接宿主机端口绑定遵循当前内网部署选择，但它仍是匿名 HTTP 读取，绝不能映射到公网。扩大范围前必须增加 TLS、网络限制和个人认证。

需要时，使用已经拉取或本地构建的镜像执行一次受控刷新容器：

```bash
/usr/bin/docker compose \
  --env-file /etc/kiro-credit-usage/container.env \
  -f docker/compose.yaml run --rm --no-build refresh
```

这条命令会发起 Athena 查询并更新宿主机数据目录。它不会挂载管理员刷新 Token 文件。

#### 宿主机 crontab 模板

Cron 是宿主机调度器，不是第三个容器。提供的模板会在北京时间每天 10:00 启动一次临时 `refresh` 容器，并在任务结束后移除：

```text
docker/kiro-credit-usage.crontab.template
```

替换模板中的绝对路径占位符并人工审查后，运维人员可以将其写入专用服务账号的 crontab。Compose 环境文件必须可由同一账号读取，配置的 cron 日志父目录必须在安装前创建并允许该账号写入。模板使用 `CRON_TZ=Asia/Shanghai`、明确 Docker 路径、明确 Compose 环境文件和明确日志路径。项目不会自动安装或修改 crontab。

Cron 不会在主机停机后自动补跑。若需要错过任务恢复、journal 集成或更严格的服务隔离，应将宿主机 cron 行替换为支持时区的 systemd timer，例如 `OnCalendar=*-*-* 10:00:00 Asia/Shanghai` 和 `Persistent=true`。

前端只依赖 `/api/*` 与 schema-v1 快照契约，因此后续可以替换服务端实现而不重构页面壳层。当前仍不包含：公网托管、自动防火墙变更、Cognito 配置、公开读取部署和自动安装调度器。

### 许可证与名称

Copyright 2026 ChowRex。本项目采用 [Apache License 2.0](LICENSE) 许可证。

Kiro 和 AWS 名称仅用于描述兼容服务。本项目不是 Amazon Web Services 或任何 Kiro 服务提供方的官方产品，也未获得其背书。Apache-2.0 不授予商标权。
