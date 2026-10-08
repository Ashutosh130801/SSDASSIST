# Predictive answered-call screen-pop in RecoverIQ

For end-to-end setup, daily agent instructions, and known production blockers in the
older manual/disposition/recording paths, read the
[complete ViciDial connection guide](VICIDIAL_COMPLETE_SETUP_GUIDE.md) first.

ViciDial's **Start Call URL** notifies RecoverIQ, which saves the event and pushes its
identifier to the mapped employee over an authenticated WebSocket. RecoverIQ checks
case access and opens the case. There is **no regular two-second ViciDial polling**.
This is Start Call URL, not Web Form. It applies to calls sent to agents, not manual
dials. See [ViciDial Call URL documentation](https://vicidial.org/docs/CALL_URL_FEATURES.txt).

## Administrator setup

1. Deploy the updated backend and the **whole** `app/frontend` folder, including
   `predictive-screenpop.js`. Restart the backend and hard-refresh RecoverIQ.
   No Android build is involved in this web/desktop-browser change; the native Kotlin
   Android interface is not changed by this feature.
2. In **Connections → ViciDial**, enter the dialer's URL and API credentials. The
   RecoverIQ server—not just the agent's laptop—must be able to reach that URL.
   Use trusted HTTPS, or a private/VPN network for a legacy HTTP server. The new
   reconnect check validates TLS certificates and will not bypass a self-signed certificate.
3. Give the API user access to `agent_status`, user level at least 7, View Reports,
   and the relevant agent groups. Consult the installed version's
   [official ViciDial Non-Agent API documentation](https://vicidial.org/docs/NON-AGENT_API.txt).
   A successful existing **Test** button checks `version`, not these additional
   live-status permissions; verify the agent's screen-pop status as well.
4. Map each RecoverIQ employee code to one distinct ViciDial agent, for example
   `TC001=8001`. If no explicit map entry exists, the employee code is used as the
   ViciDial agent ID. Staff must have the correct branch. An exact-branch connection
   takes priority over the global connection; another branch is never used as fallback.
5. Push cases with RecoverIQ's existing ViciDial campaign export, which supplies
   `vendor_lead_code = RecoverIQ case ID`. For pre-existing leads, set that same value
   in ViciDial. **Do not put an account number or ViciDial lead ID in this field.**
6. Allocate the cases to the receiving caller in RecoverIQ. Predictive campaigns must
   route leads to agents who already have case access. Screen-pop does not silently
   reassign cases or widen permissions. Removed, inaccessible and past-portfolio cases
   follow the existing case-detail access rules.
7. Sign the employee into their ViciDial agent/audio session and RecoverIQ. Keep
   RecoverIQ visible. Customer details open here; the ViciDial session and softphone
   are still required for call delivery. This is not an embedded agent login/softphone.
8. Click **Start Call URL** beside the saved ViciDial connection (or save the connection
   to reveal it). Copy the full value, including `VAR`, into the predictive campaign's
   **Start Call URL** field. Verify the domain is your public HTTPS RecoverIQ domain,
   not `localhost` or an internal reverse-proxy hostname. Configure the corresponding
   in-group too if using inbound calls. Preserve any existing Start Call integration
   using your ViciDial version's multiple-callback configuration or a relay.
9. The callback sends `agent`, `case` (vendor lead code), `call_id`, and a secret key.
   Keep the URL private. Validate your installed version substitutes all tokens:
   unexpanded tokens are rejected, not used to guess a case. The callback URL must be
   reachable from the ViciDial installation. Both servers need the required network
   access; agents do not need to look at the ViciDial screen for customer details.

## Behaviour

Each authenticated callback is stored in `predictive_call_events` before notification.
An opaque event identifier goes only to that employee's live sockets; the browser
then fetches the event and case with its normal JWT. Repeated callbacks are deduplicated.
Superseded or more-than-two-minute-old events do not open a case. One-day callback
history is cleaned opportunistically when another callback arrives. No borrower
phone number or name is included in the WebSocket notification.

On WebSocket connection/reconnection, returning to the tab, or network restoration,
RecoverIQ makes one `agent_status` check to recover a currently connected call that
may have been missed. This is not scheduled repeatedly after success. Failed requests
retry with backoff. A closed/suspended browser cannot open a case. Delivery is normally
prompt, but network/server latency applies. A callback never received by the server
cannot be recovered until the next reconciliation check. No ViciDial callback-retry
guarantee is assumed.

The banner says **Latest call received**, not that the customer is still on the line:
this feature does not continuously monitor hang-ups. The existing disposition
callback remains responsible for call outcomes. Manual calls are not automatically
pushed through Start Call URL; the existing click-to-call case is already open.

Each call identity opens once per browser-tab session. Re-dialing the same customer
with a different call ID opens again. A failed case fetch retries without consuming
the event. Closing a drawer stops repeat popping for that call; **Open latest call case**
can reopen it. New calls retain previous predictive drawers/drafts underneath; closing
the top drawer returns to the previous one. Drafts are not persisted across reloads.
Use one active RecoverIQ tab per agent; separate visible tabs can each pop the call.

No call logs, payments or case assignments are changed by screen-pop. Continue using
the existing disposition callback and case forms for those updates.

## Acceptance test with your actual dialer

1. Use two test agents with separate mapped IDs and allocated test cases. Call only
   consenting test numbers. Confirm both show **Predictive screen-pop ready**.
2. Let a predictive call connect to agent A. Only A's matching case should open.
   Check the displayed case ID/name and dialed customer's details.
3. Close the drawer during the same call: it must not repeatedly reopen. Use the
   explicit open button to reopen it. Re-dial after ending it: the new call must pop.
4. Connect a second test case while the first drawer has an unsaved note. Close the
   second drawer and verify the first note remains intact.
5. Test a missing vendor code, an unassigned case and a removed case. The callback must
   return an error and no case should pop (there is no phone-number guessing).
6. Briefly interrupt the browser's network. Confirm a disconnected message and automatic
   WebSocket reconnection. If the call is still live, the reconciliation check should
   recover it. In DevTools, verify `/ws` upgrades with HTTP 101 and an answered call
   brings a `predictive_screenpop` frame; there must be no regular two-second status requests.

Automated tests use an isolated in-memory database and mocked ViciDial responses:

```powershell
cd app/backend
.venv/Scripts/python.exe -B tests/test_predictive_screenpop.py
```

From the repository root:

```powershell
node --test app/frontend/tests/predictive-screenpop.test.cjs
```

These tests do not certify the live dialer's configuration. Complete the acceptance
test before using the feature with real recovery calls. Disabling the connection in
Connections stops this predictive Start Call/event path. The older disposition and
recording paths do not consistently enforce that flag; do not treat it as full
credential revocation. Pause the affected campaign and remove/restore its callback
configuration with the dialer administrator when stopping the integration. Use the
previous deployment to roll back the code change while preserving database records.

## What WebSocket delivery needs

- **No extra API key or paid WebSocket service.** The existing FastAPI/Uvicorn server
  serves `/ws`. Browsers use their existing RecoverIQ login token. HTTPS gives you WSS
  on port 443; no separate public WebSocket port is needed.
- Serve the app and `/ws` from the same public origin, directly on Cloud Run or via a
  reverse proxy that forwards WebSocket Upgrade requests. Do not assume a static-site
  host or hosting rewrite supports persistent sockets. The Python server must stay running.
- **One Uvicorn worker and one service instance for this implementation.** The hub is
  in-process. Redis/pub-sub fan-out is required before using multiple workers/replicas;
  session affinity alone cannot reliably route a dialer callback to the agent's instance.
  Rolling deployments can also temporarily overlap instances, so reconnect reconciliation
  remains necessary. Redis support is not implemented in this change.
- Cloud Run deployment scripts now default to `--max-instances 1 --timeout 3600`.
  They have **not** been run. Existing services need redeployment or the same settings
  applied explicitly. Cloud Run eventually closes sockets at the request timeout; the
  client reconnects. Open sockets can incur hosting costs, even though no separate
  WebSocket subscription is required. [Cloud Run WebSocket guidance](https://cloud.google.com/run/docs/triggering/websockets).
- The server sends an idle keep-alive every 25 seconds and rechecks account/token
  validity. Expired or inactive accounts cannot open a new socket; case/event HTTP
  requests also recheck authentication and authorization.
- Do not log callback query strings (`key`) or socket query strings (`token`). Uvicorn
  application logs redact these fields, but proxies, Cloud Run request logs, ViciDial
  logs and external monitoring are separate: configure redaction/exclusion there and
  tightly restrict log access. A generated callback URL is a credential.

For Nginx, add this to the site's HTTPS server block (adapt upstream address):

```nginx
location = /ws {
    proxy_pass http://127.0.0.1:8000;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_read_timeout 3600s;
    proxy_send_timeout 3600s;
    access_log off; # JWT is in the query string
}
location = /api/integration/vicidial/start-call {
    proxy_pass http://127.0.0.1:8000;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-Proto $scheme;
    access_log off; # callback key is in the query string
}
```

Keep your existing `/` and `/api` proxy routes. Have the administrator validate
`nginx -t` before reloading; do not replace the entire server configuration with this snippet.
