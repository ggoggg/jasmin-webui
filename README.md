# Jasmin Manager

A responsive web UI for Jasmin SMS Gateway, backed by its native Twisted Perspective Broker APIs. No jCli scraping and no browser access to PB credentials.

## Run locally

Requires Python 3.10+ (tested with Python 3.12).

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m manager.server --demo --port 8090
```

Open http://127.0.0.1:8090. Demo mode starts empty, uses native Jasmin configuration classes, and simulates connector states. All demo changes disappear when the process stops; saving in demo mode does not write to a gateway or disk.

## Connect an existing gateway

```bash
cp .env.example .env
# Edit .env with your gateway credentials and a randomly generated admin token.
# Generate a token with: python3 -c 'import secrets; print(secrets.token_urlsafe(32))'
set -a
source .env
set +a
.venv/bin/python -m manager.server --port 8090
```

Visitors can browse every gateway and inspect configuration fields without signing in. Passwords remain excluded from API responses. Add, edit, delete, enable/disable, start/stop, and save operations require authentication with `MANAGER_TOKEN`, enforced by the server as well as the UI. Choose **Sign in** to enable editing; **Sign out** restores read-only access and clears the token from sessionStorage for the current tab. A local demo without `MANAGER_TOKEN` is read-only; set the variable before starting it to enable sign-in. The server reads environment variables; it does not automatically load `.env`.

Set the router credentials from `[router]` in `jasmin.cfg`, and SMPP manager credentials from `[client-management]`. Default PB ports are 8988 and 8989 respectively; hosts, ports and usernames are configurable independently in `.env`. Use the plaintext PB login passwords, not the hashed values stored in Jasmin's configuration. Live startup requires an admin token of at least 24 characters and a password for each PB service with authentication enabled.

Set `ROUTER_AUTHENTICATION=false` or `SMPP_AUTHENTICATION=false` only when the corresponding Jasmin PB service has `authentication=False`; the manager then connects anonymously and does not require that service's password. Anonymous PB access grants administrative control, so keep those ports restricted to trusted hosts. Authentication defaults to `true`.

The client dependency is pinned to Jasmin 0.11.1. Use compatible Jasmin object definitions on client and server, and verify against your installed gateway version before production rollout. Live testing against Jasmin 0.11.0 at 10.36.34.64 passed provisioning, connector bind, MT submit_sm delivery, MO HTTP delivery, isolated profile persistence, and browser rendering. The SMSC was an isolated simulator; external carrier delivery was not exercised.

## Select a gateway

Set `JASMIN_GATEWAYS=production,test` and configure each gateway with `JASMIN_PRODUCTION_ROUTER_*`, `JASMIN_PRODUCTION_SMPP_*`, `JASMIN_TEST_ROUTER_*`, and `JASMIN_TEST_SMPP_*`. These use the same HOST, PORT, USERNAME, PASSWORD and AUTHENTICATION fields as the single-gateway settings. Named profiles do not inherit credentials or hosts from legacy settings. See `.env.example` for the full template.

`JASMIN_PRODUCTION_NAME` / `JASMIN_TEST_NAME` set the display labels, and `JASMIN_DEFAULT_GATEWAY` sets the initial selection. Restart the manager after changing profiles. The existing single-gateway configuration still works when `JASMIN_GATEWAYS` is absent.

The **Managing Jasmin** selector shows each name and hostname. Selection is remembered per browser tab. Switching clears previous data and open forms; unavailable gateways show an error. Switching is disabled during a management operation. All requests explicitly target a gateway, so separate tabs can manage different gateways. The admin token grants access to all configured profiles; credentials remain server-side.

For API clients, authenticated `GET /api/gateways` returns the available IDs, labels, hosts and default ID. Send `X-Jasmin-Gateway: production` (or another configured ID) on subsequent calls. With multiple profiles, missing or unknown IDs are rejected rather than falling back to a gateway.

## Features

- Overview with actual account, connector and route counts; service and SMPP bind state shown separately.
- Create, list, enable, disable and delete users/groups. Set and update balance, SMS count, HTTP throughput and SMPP throughput quotas. Blank quotas mean unlimited.
- Create, list, start, stop and remove SMPP client connections; configure host, port, system ID, password, bind mode and throughput.
- Create, list and remove MO/MT default, static, failover and random round robin routes.
- Manage MO/MT default and static interceptors: view/edit Python source and supported filters, create, delete, and clear a direction’s table.
- MT destinations reference existing SMPP connections. MO destinations embed HTTP connectors or SMPP server system IDs directly in the route.
- Route filters: transparent, source/destination address regex, message regex, MT user/group, and MO source connector. Multiple filters use AND matching.
- Duplicate IDs/orders are rejected rather than silently replacing existing configuration. Referential checks prevent removing groups with users or objects used by routes.
- Searchable tables, responsive layout, visible failure messages and confirmation for destructive actions.
- Save configuration persists router and connector configuration under `jcli-prod`. Changes apply immediately; save before restarting Jasmin. The two PB saves are separate operations; partial persistence is reported.

Create a group, add users and upstream connections, start a connection, then configure routes. Routes are evaluated from highest order to lowest; order 0 must be a default route. For an MO SMPP destination, use the downstream client's system ID (username); that client needs a receiver/transceiver bind. HTTP MO destinations are stored in routes, not in jCli's independent HTTP connector registry.

Existing objects created elsewhere are listed. Route definitions are changed by removing and recreating the route. Gateway config loading, traffic statistics and audit history are not included. Account deletion and multi-quota updates are not transactional across other tools managing the gateway; refresh after an error to verify partial outcomes. Management operations from this server are serialized.

## Tables, edits and filter selection

Click any data-column heading to sort ascending; click again for descending. Numeric values sort numerically, including route priorities and rates. Sorting is retained across refreshes on the current page and works with table search.

**Users → Edit** changes username, group, password and the complete MT messaging / SMPP credentials: authorizations, regex value filters, default source address and all quotas. Field names match jCli. Blank passwords preserve the current password; blank quotas mean ND and blank default source means None. Only changed credential fields are submitted, preserving untouched live balances and counters. User ID and enabled status are retained. **Quotas** remains available for quick balance/throughput changes. The backend reads the latest user before replacing it, but external traffic/admin updates are not transactional with identity edits.

**SMPP connections → Edit** changes host, port, system ID, password, bind mode and throughput. Stop the connection before saving edits; it remains stopped afterward. A blank password keeps the existing one. Jasmin PB has no connector-update call, so the manager removes/re-adds the stopped connector with the same ID and a copy of all advanced settings. It does not request queue deletion. Routes remain attached by ID. Failed replacement attempts restoration; an uncertain outcome is reported so you can inspect the gateway before retrying. Recreating the service resets its process-local counters. Save configuration after successful edits.

User, group and source-connector filter values are dropdowns drawn from the selected gateway. Choose **Use an existing filter** in a route/interceptor filter row to select a compatible filter already used by that gateway's routes or interceptors. These are reused as native filter copies, including types the form cannot otherwise create. PB does not expose jCli's standalone named filter registry, so unused jCli-only filters are not listed. If a source filter disappears or changes before saving, refresh and select it again.

## Interceptor controls

Select a gateway, then open **MT interceptors** or **MO interceptors**. Default interceptors use order 0 and no filters; static interceptors use a positive order and one or more filters. Higher orders are evaluated first. **View / edit** loads the stored Python source and filter configuration. Edits keep the order and type; remove/recreate to change those. Unsupported existing filter types are shown read-only and preserved during script edits.

Python syntax is checked without executing the script in the manager. Saving installs the source on the selected gateway immediately; it does not test runtime behavior. Jasmin's interceptor service and client connection must be available for messages to execute scripts. The existing **Save configuration** action persists both interceptor tables along with the router configuration. Requests have a 64 KiB JSON size limit.

Editing, deleting and clearing tables check the previously loaded revision to detect stale data. Refresh before retrying if another administrator changed an interceptor. These checks do not provide a transaction across external tools such as jCli. Deleting users, groups or connectors referenced by interceptor filters is blocked.

API: `POST /api/interceptors/mt` or `/mo` creates; `POST /api/interceptors/mt/ORDER` updates; `DELETE /api/interceptors/mt/ORDER` removes; `DELETE /api/interceptors/mt` clears the MT table (MO uses `/mo`). Updates/deletes include the `revision` returned in `/api/state`; clear-all uses the direction's `interceptor_revisions` value. All calls use the selected gateway header.

## Deployment

The default listener is loopback. For remote access, put the manager behind an HTTPS reverse proxy; use `--host 0.0.0.0` only on a protected network. The browser token grants full administrator access. PB is a trusted administrative protocol and Jasmin serializes native Python objects with pickle: connect only to trusted gateways over a private network or SSH tunnel, never expose PB ports publicly. Keep PB credentials server-side.

The application serves its own static frontend and HTTP API in one Twisted process. No Node build or frontend CDN is needed. There is no background polling; Refresh obtains a fresh gateway snapshot. PB calls time out; a timeout can leave the remote action completed, so check current state before retrying.

## Checks

```bash
.venv/bin/pip install pytest requests
.venv/bin/python -m pytest -q
.venv/bin/python -m tests.pb_integration
node --check manager/static/app.js
# Optional browser checks:
.venv/bin/pip install playwright
.venv/bin/playwright install chromium
.venv/bin/python -m tests.browser_smoke
```

The HTTP tests launch an isolated, authenticated demo server and verify user/connector/routing lifecycle, persistence flags, validation, secret redaction, and request protection. The PB test starts two local authenticated test services and runs the production proxy path over TCP. These test services do not bind to an SMS provider or deliver SMS.

## Live gateway integration test

The opt-in test creates unique users, groups, a connector and filtered routes, then removes them and checks the existing configuration against its baseline. It runs real MT and MO messages through the gateway to a local SMSC simulator and HTTP receiver. Requires the optional Playwright installation above, SSH access, and available local/remote test ports.

In one terminal, keep the test tunnels open:

```bash
ssh -o ExitOnForwardFailure=yes -N \
  -L 127.0.0.1:11401:127.0.0.1:1401 \
  -R 127.0.0.1:27750:127.0.0.1:27750 \
  -R 127.0.0.1:28081:127.0.0.1:28081 user@10.36.34.64
```

In another, load the gateway connection settings and run:

```bash
set -a
source .env
set +a
LIVE_GATEWAY_ID=test LIVE_SSH_TARGET=user@10.36.34.64 .venv/bin/python -m tests.live_gateway
```

`LIVE_GATEWAY_ID` selects the test profile and is required when multiple gateways are configured. This test provisions objects and sends isolated messages; select your test gateway. `LIVE_SSH_TARGET` enables persistence testing and removes the uniquely named test profile through SSH with noninteractive sudo. This cleanup assumes the gateway store is `/etc/jasmin/store`. Without it, persistence testing is skipped. PB connections use the hosts, ports and authentication settings from `.env`; use additional local forwards if needed. The script checks that Jasmin's quota auto-persistence did not leave the test account in `jcli-prod` and reports cleanup failures explicitly. Do not run concurrent copies of this test.

Results are recorded in `artifacts/live-test.json`. SMPP connector credentials are validated before provisioning: system ID at most 15 ASCII characters, password at most 8, with no embedded NUL characters.

## Documentation used

- [Twisted Perspective Broker introduction](https://docs.twistedmatrix.com/en/stable/core/howto/pb-intro.html)
- [Jasmin management architecture](https://docs.jasminsms.com/en/latest/management/jcli/)
- [Jasmin developer FAQ: PB access](https://docs.jasminsms.com/en/latest/faq/developers.html)
- [Router proxy implementation](https://github.com/jookies/jasmin/blob/master/jasmin/routing/proxies.py)
- [SMPP manager proxy implementation](https://github.com/jookies/jasmin/blob/master/jasmin/managers/proxies.py)

## Installed systemd service

Production deployment: `http://10.36.34.52:8090` (private interface), service `jasmin-manager.service`. The manager uses a dedicated virtual environment and an unprivileged dynamic user. It is enabled at boot and restarts on failure.

- Application release: `/opt/jasmin-manager/releases/20261005-credentials`
- Active release symlink: `/opt/jasmin-manager/current`
- Virtual environment: `/opt/jasmin-manager/venv`
- Configuration: `/etc/jasmin-manager/manager.env` (root-owned, mode 0600)
- Unit: `/etc/systemd/system/jasmin-manager.service` (source in `deploy/`)

On the server:

```bash
sudo systemctl status jasmin-manager
sudo journalctl -u jasmin-manager -n 100 --no-pager
sudoedit /etc/jasmin-manager/manager.env
sudo systemctl restart jasmin-manager
```

Gateway profiles and the manager token are loaded from the server environment file. Changing the local `.env` does not automatically change the deployed service. Application updates should be copied to a new root-owned release directory, then switch `current` and restart only `jasmin-manager`. Keep the preceding release for rollback. Existing Jasmin services do not need a restart.
