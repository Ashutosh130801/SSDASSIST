# RecoverIQ + ViciDial: complete connection guide

Updated: 8 October 2026. Audience: organisation administrator, ViciDial vendor, and RecoverIQ server administrator.

This guide connects an **existing, working ViciDial installation** to RecoverIQ. It covers manual calling, predictive screen-pop, call outcomes, recordings, agent setup, and troubleshooting. It does not install a telephone carrier, configure a new Asterisk server, or replace your dialer vendor.

**Important: the current code is not cleared for production dialer use.** Code inspection found the issues in Step 1. You can prepare configuration and run an isolated test with consenting staff; do not load real borrower portfolios or enable unattended calling until the applicable blockers are fixed and tested. A green connection test is not a production approval.

All domains, IDs and employee codes below are examples. Keep passwords and generated callback URLs in your organisation's password manager, never in GitHub, chat, screenshots, or this document.

## Quick navigation

- [1. Understand the current readiness limits](#1-understand-the-current-readiness-limits)
- [2. Collect the connection information](#2-collect-the-connection-information)
- [3. Establish network access](#3-establish-network-access)
- [4. Prepare ViciDial](#4-prepare-vicidial)
- [5. Prepare each employee and phone](#5-prepare-each-employee-and-phone)
- [6. Save the RecoverIQ connection](#6-save-the-recoveriq-connection)
- [7. Test manual click-to-call](#7-test-manual-click-to-call)
- [8. Choose predictive routing](#8-choose-predictive-routing)
- [9. Load predictive leads](#9-load-predictive-leads)
- [10. Enable answered-call screen-pop](#10-enable-answered-call-screen-pop)
- [11. Verify WebSocket delivery](#11-verify-websocket-delivery)
- [12. Connect dispositions and recordings](#12-connect-dispositions-and-recordings)
- [13. Run the acceptance tests](#13-run-the-acceptance-tests)
- [14. Give agents their daily instructions](#14-give-agents-their-daily-instructions)
- [15. Troubleshoot by symptom](#15-troubleshoot-by-symptom)
- [16. Maintain and safely stop the integration](#16-maintain-and-safely-stop-the-integration)
- [17. Administrator handoff checklist](#17-administrator-handoff-checklist)

## How the parts fit together

```text
MANUAL CALL
RecoverIQ case → RecoverIQ backend → ViciDial agent API
                                        ↓
                           logged-in agent audio session ↔ customer
                                        ↓
                                Zoiper / phone audio

PREDICTIVE ANSWER
ViciDial assigns answered call to an available agent
    ├─ audio → that agent's connected phone
    └─ Start Call URL → RecoverIQ backend → authenticated /ws connection
                                               ↓
                                  matching case opens for that agent

CALL RESULT
ViciDial disposition → Dispo Call URL → RecoverIQ case history
```

RecoverIQ's login, ViciDial's agent login, and Zoiper's SIP registration are separate. Screen-pop does not replace the agent's dialer session or softphone. eturnal is a STUN/TURN server for network traversal, **not** RecoverIQ's WebSocket server. See the [eturnal description](https://eturnal.net/).

## 1. Understand the current readiness limits

The following are findings in the checked-out application, not settings you can fix by entering another API key. Give this table to the developer before production sign-off.

| Area | Current behaviour / required correction |
|---|---|
| Manual case identification | `external_dial` currently sends `vendor_lead_code`; the documented Agent API parameter is `vendor_id`. Correct and test it, including two accounts sharing one phone number. Phone-based `search=YES` alone is not reliable case identification. |
| Manual-call access control | The click-to-call handler loads a case by ID without checking the caller's case scope. Add server-side role, assignment, and branch checks; a hidden button is not protection. |
| Branch routing | Legacy manual/push selection can fall back to the first enabled connection from another branch. The Cases push button does not send an explicit branch/connection. Correct both before multi-branch use. The newer predictive screen-pop has stricter checks. |
| Secure API connections | Older test, manual-call and lead-push requests disable TLS certificate verification and send credentials in URL parameters. Enforce certificate verification and protect credentials from proxy/dialer logs; use a supported safer request method where available. |
| Disposition callback | It lacks duplicate-event protection and sufficient connection-to-case scope checks; it also does not reject a disabled connection. Correct these before real financial workflows. |
| Duration template | Generated Dispo URL uses `len` and `talk_sec`, but the handler expects `length`. Step 12 describes the template correction to verify on your installed dialer version. |
| Credential storage | API/SFTP passwords are stored server-side in connection JSON, not encrypted by the application. Add managed-secret/encryption controls and restrict database/backup access. Masked UI output is not encryption. |
| Optional SFTP recordings | Current code automatically trusts unknown SSH host keys. Pin/validate the server host key. Recording links are bearer URLs, expire after seven days by default, and are not automatically refreshed. Add authenticated, case-scoped access and fresh signing for long-term use. |
| Browser focus | Manual dialing currently requests ViciDial screen focus. Change/test this if agents should stay visually inside RecoverIQ. |

The manual parameter/focus distinction is documented in the [official Agent API reference](https://vicidial.org/docs/AGENT_API.txt). Other findings above come from this repository's `app/backend/app/routers/integrations.py` and frontend.

This documentation task **does not change application code**. No live ViciDial server, carrier, or real customer call has been validated as part of writing it.

## 2. Collect the connection information

Have your dialer vendor fill in a private worksheet. Do not send secrets through ordinary support messages.

| Information | Example / meaning | Supplied by |
|---|---|---|
| RecoverIQ public address | `https://recoveriq.example.com` | Web/server administrator |
| ViciDial base address | `https://dialer.example.com` — not the admin.php page | Dialer vendor |
| API service username/password | Dedicated integration account; not an employee login | Dialer vendor |
| Outbound server IP / VPN route | Address the dialer will actually see from RecoverIQ | Server administrator |
| Campaign ID | `RIQTEST` | Dialer vendor |
| List ID | `9101`, already linked to that campaign | Dialer vendor |
| Phone country code | `91` for an Indian-number test | Dialer vendor |
| Number format and dial prefix | Confirm national/international format and trunk rules | Dialer vendor |
| RecoverIQ branch | Exact existing branch value, e.g. `Bhubaneswar` | RecoverIQ administrator |
| Employee-to-agent mapping | `TC001=8001` | Both administrators |
| Agent login credentials | Unique ViciDial user for each person | Dialer vendor |
| SIP account credentials | SIP server, auth ID, password, port/transport | Dialer vendor |
| Optional recording access | HTTPS recording location OR restricted SFTP account/folder | Dialer vendor |

**Do not request ViciDial MySQL access for this connector.** The current implementation uses APIs and callbacks, not a MySQL recording poller. Do not expose database port 3306 publicly.

Keep these identifiers distinct:

| Identifier | Example | Where it belongs |
|---|---|---|
| RecoverIQ employee code | `TC001` | Left side of Agent map |
| ViciDial agent user | `8001` | Right side of Agent map |
| SIP/phone account | Vendor-issued extension/auth ID | Zoiper and ViciDial phone login |
| RecoverIQ internal case ID | `12345` | ViciDial lead's `vendor_lead_code` |
| ViciDial lead ID | Dialer-generated | Dialer's own lead record; not the RecoverIQ case ID |
| Bank account/card number | Customer's financial reference | Case data; not the screen-pop identifier |

## 3. Establish network access

Ask the server administrator to verify all three directions independently:

1. **RecoverIQ backend → ViciDial:** API access over HTTPS or an approved private network/VPN.
2. **ViciDial callback execution environment → RecoverIQ:** public HTTPS access to the callback routes. Confirm callback execution behaviour on your installed ViciDial release; do not assume a successful browser test proves the dialer can reach them.
3. **Agent browser → RecoverIQ:** HTTPS pages, authenticated API requests, and WSS `/ws`.

Optional fourth direction: RecoverIQ backend → recording SFTP server, usually TCP 22.

A cloud backend cannot directly reach an office-only `192.168.x.x` address without network routing/VPN. Installing Zoiper on a laptop does not establish that server route. Ask the vendor to restrict API exposure to your actual backend egress addresses; Cloud Run may need configured static egress if an IP allowlist is used.

Do not expose the entire PBX, SSH, database, or administration panel just to make a connection test pass. Do not disable firewalls or certificate checking as a workaround.

**Checkpoint:** both administrators confirm network reachability, valid certificates, and protected logs. No calls are placed yet.

## 4. Prepare ViciDial

Menu names differ by installed version. The dialer vendor should perform this section, recording the original settings before changing them.

1. Prove an ordinary ViciDial call works first: agent login, registered phone, outbound trunk, two-way audio, hang-up, and disposition. Use a consenting staff member's number.
2. Create a dedicated integration API account. Enable the Agent and Non-Agent API permissions needed by the connector, limited to the relevant users/groups and functions. Do not grant unrestricted administrator access merely to bypass an error.
3. Permit `external_dial` for manual calling. For predictive loading permit `add_lead`; for reconnection recovery permit `agent_status`. The latter needs the installed version's required reporting/user permissions. Current RecoverIQ guidance expects level 7+, View Reports, and relevant groups. Check these against the server's own [Non-Agent API reference](https://vicidial.org/docs/NON-AGENT_API.txt).
4. Create a **test campaign** or have the vendor isolate an existing campaign. Allow manual dialing for the manual test, and configure its manual-dial list, phone format, caller ID and trunk prefix.
5. Create an empty test lead list and attach it to the intended campaign. Keep predictive dialing/list activation paused until the mapping and callback tests are ready.
6. Enable the organisation's approved recording policy if recordings are needed. Confirm a test recording actually exists and is playable in ViciDial before troubleshooting RecoverIQ playback.
7. Record the exact campaign/list IDs, approved call statuses, and recording filename/folder format.

**Checkpoint:** standalone ViciDial calling works. If it fails here, fix the dialer/phone/trunk before continuing.

## 5. Prepare each employee and phone

### RecoverIQ administrator

1. Create or verify each employee in RecoverIQ's staff/user administration.
2. Use an individual telecaller account, unique employee code, correct branch, and permitted portfolio. Never share an administrator login among callers.
3. Assign the test cases to the intended caller and confirm that caller can open them.
4. Record the employee code exactly; the integration maps codes, not display names or email addresses.

### Dialer administrator and employee

1. Issue an individual ViciDial agent account and its allowed campaign access.
2. Issue a SIP/phone account. In Zoiper's account setup, enter the vendor's SIP server, authentication username, password and prescribed transport/port. These are not automatically the employee's RecoverIQ credentials.
3. Confirm Zoiper shows registered. Allow microphone/audio permissions and select the correct headset.
4. Sign into ViciDial's agent interface with the required phone-login and agent credentials; select the test campaign.
5. Establish the agent's audio/conference session as instructed by the vendor. Registration alone is not enough.
6. Keep the agent session open, then sign into RecoverIQ as the same mapped employee.

The audio may stay connected to the dialer throughout a shift. **Do not expect Zoiper to ring afresh on every customer call.** Test the actual configured call flow.

## 6. Save the RecoverIQ connection

Sign into RecoverIQ with an administrator/head-office account authorised to manage integrations.

1. Open **Connections**.
2. Find **ViciDial (existing office dialer)**. Do not use the separate generic **Autodialer** form.
3. Fill these fields:

| RecoverIQ field | Enter |
|---|---|
| Name | A recognisable label, e.g. `Office test dialer` |
| ViciDial URL | Base address, e.g. `https://dialer.example.com` |
| API user / API password | Dedicated integration service credentials |
| Campaign ID | `RIQTEST` or the actual campaign |
| List ID (for campaign push) | Actual list, e.g. `9101` |
| Source tag | `recoveriq` |
| Phone code | Vendor-approved country code, e.g. `91` |
| Recording URL base | Leave blank initially unless HTTPS recordings are configured |
| Branch | Exact branch; blank means a global connection, not a branch restriction |
| SFTP fields | Leave blank initially unless using SFTP recordings |
| Agent map | One employee-to-agent mapping per line, as below |

```text
TC001=8001
TC002=8002
```

4. Click **Save ViciDial connection**.
5. Securely retain the generated Start Call and Dispo callback URLs. They contain an integration secret generated by RecoverIQ; this is **not** your ViciDial API password.
6. Click **Test** on the saved connection. Inspect the returned message, not just the badge.

**What Test proves:** the existing test requests the API's `version` function. It does not prove permission to dial, add leads, inspect agent status, receive callbacks, access recordings, or route to the correct branch.

**Important when updating:** the form does not reliably prefill the saved configuration. Saving uses the branch to identify an existing connection. A blank Agent map submitted by the form can clear existing mappings; default values can also overwrite saved fields. Re-enter/check the complete configuration when changing it. Blank password fields preserve stored passwords. Do not create overlapping connections or vary branch spelling/capitalisation to edit one. Use the row's **Start Call URL** button if you only need that URL again.

## 7. Test manual click-to-call

Complete the Step 1 manual-call fixes before treating this as a production workflow.

1. Keep only the intended test integration active. Prepare one non-sensitive test case assigned to employee `TC001`.
2. Confirm `TC001=8001`, then log agent `8001` into ViciDial and connect their phone/audio session.
3. Log into RecoverIQ as `TC001`. Open that case and use the integrated dialer call action. Confirm the request goes to RecoverIQ's `/api/integration/click-to-call`; a plain `tel:` link is a device phone action, not this integration.
4. Answer the consenting test customer's phone. Verify two-way audio and that the intended agent received it.
5. Hang up and complete the dialer disposition. Once Step 12 is configured, verify the correct case history receives it.
6. Repeat with a second agent, then with two test cases sharing a phone number. Stop if the wrong case is selected.

**Do I need Campaign ID and List ID for manual calling?** RecoverIQ's current manual request does not send either. The agent still needs a valid ViciDial campaign/session and its manual-dial configuration. RecoverIQ's List ID field is used for predictive lead pushes, not to select the manual caller's campaign. Manual dialing targets the logged-in RecoverIQ user's mapped ViciDial agent.

## 8. Choose predictive routing

Choose this before exporting leads:

| Requirement | Approach | Important limit |
|---|---|---|
| Caller handles only their assigned cases | Manual click-to-call | Most straightforward starting workflow, after access-control fixes |
| Shared predictive pool | Common campaign and eligible agents | Receiving agents must have authorised access to those cases in RecoverIQ; allocation is not changed by screen-pop |
| Predictive but strict individual ownership | Isolated campaign per caller, containing only that caller's leads | Only that caller may receive calls there; prevent overflow/cross-campaign routing and keep allocations synchronised |

Separate lists **inside one shared campaign do not, by themselves, bind a lead to its RecoverIQ owner**. The current exporter does not send an owner-routing instruction. Creating multiple campaigns also does not automatically synchronise RecoverIQ reallocations.

For a one-caller campaign pilot, have the dialer vendor use conservative pacing and approved call-time/abandonment controls. Do not assume a one-agent predictive campaign is operationally efficient. A RecoverIQ-managed owner-aware progressive queue is not implemented in this connector.

If ViciDial sends a call to someone who cannot access the case, audio can arrive while RecoverIQ correctly refuses the screen-pop. Resolve routing/permissions; do not disable case security to hide the mismatch.

## 9. Load predictive leads

**Current UI limitation:** the Cases **Send to ViciDial** button sends the currently loaded case IDs, without an explicit branch or destination list override. Do not use it for a multi-branch rollout until destination selection/routing is corrected. Filtering the displayed cases is not proof the destination connection is correct.

For an isolated, single-connection test:

1. Confirm the destination list is empty/inactive and belongs to the intended campaign.
2. Confirm the saved connection contains that list ID.
3. Show only the intended test cases in Cases. Check the button's case count; do not assume it includes every page.
4. As an authorised head-office user, click **Send to ViciDial** and review the confirmation.
5. Record pushed, skipped and failed counts. Missing-phone, paid or closed cases may be skipped. Investigate failures before retrying an entire batch.
6. Open each test lead in ViciDial and verify phone, list and **Vendor Lead Code = RecoverIQ internal case ID**.
7. Verify the lead is eligible for the campaign before deliberately activating the test list.

Changing the Campaign ID text in RecoverIQ does not move a list into another ViciDial campaign. The list-to-campaign relationship is controlled in ViciDial. Lead reassignment/removal in RecoverIQ is not automatically propagated to previously queued dialer leads; pause and reconcile those leads before resuming.

## 10. Enable answered-call screen-pop

1. Deploy the matching backend and complete frontend, including `predictive-screenpop.js`, using your existing release process. Back up the database first; normal app startup creates the new predictive-event table. No database reset is required.
2. Restart the backend and hard-refresh the browser. This feature targets the web interface; it does not add a native Android screen-pop or require an Android build for the browser feature.
3. Open **Connections → saved ViciDial connection → Start Call URL**.
4. Verify its origin is your real HTTPS RecoverIQ domain, not `localhost` or an internal proxy name.
5. In ViciDial campaign settings, paste the complete value into **Start Call URL**, including the `VAR` prefix. Preserve any existing callback integration with vendor-supported multiple callbacks or a relay; do not overwrite it without a replacement plan.
6. If using inbound calls, have the vendor verify the equivalent in-group configuration.
7. Save, connect a test predictive call, and verify only the mapped authorised caller sees the correct case.

Shape of the generated URL — **illustration only**, not a usable credential:

```text
VARhttps://recoveriq.example.com/api/integration/vicidial/start-call?key=REPLACE_WITH_GENERATED_SECRET&agent=--A--user--B--&case=--A--vendor_lead_code--B--&call_id=--A--call_id--B--
```

Use **Start Call URL**, not Web Form. ViciDial documents it for calls delivered to an agent, not manual dialing. The variable substitution syntax must be preserved. See [Call URL features](https://vicidial.org/docs/CALL_URL_FEATURES.txt).

RecoverIQ stores a validated event, sends its identifier to the mapped user's WebSocket, then checks normal authentication/case access before opening it. Duplicate callbacks do not repeatedly pop the same call. Old or superseded events are rejected. Reconnection/tab return performs a recovery check; normal operation does not poll ViciDial every two seconds.

The banner is **Latest call received**, not a live hang-up indicator. It does not prove the customer is still connected. For detailed behaviour and tests, see [Predictive screen-pop](PREDICTIVE_SCREENPOP.md).

## 11. Verify WebSocket delivery

There is no extra WebSocket account, API key, or eturnal configuration to enter. The FastAPI backend serves `/ws`; the web app uses its RecoverIQ login token.

Ask the server administrator to:

1. Serve frontend, API and `/ws` through the same HTTPS origin, with WebSocket Upgrade support. Browser traffic should use `wss://`.
2. Keep the Python server running with WebSocket-capable dependencies.
3. Run **one Uvicorn worker and one service instance** for the current in-memory delivery hub. Multi-worker/multi-instance delivery needs a shared broker such as Redis, which is not implemented. Affinity alone is insufficient.
4. Configure proxy idle timeouts appropriately. For Nginx, adapt the example in [the WebSocket setup section](PREDICTIVE_SCREENPOP.md#what-websocket-delivery-needs), validate with `nginx -t`, and only then reload. Do not replace the whole server configuration with that snippet.
5. Exclude/redact query-string secrets from access logs for `/ws` and both callback routes, including `/api/integration/vicidial/dispo`. Application log redaction does not automatically protect cloud, proxy or dialer logs.
6. In browser DevTools → Network → WS, confirm `/ws` connects (normally HTTP 101), and a predictive answer produces a `predictive_screenpop` event. Do not share the request URL containing the JWT.

On Cloud Run, allow a long request timeout (up to 60 minutes), expect reconnects, and account for active-connection costs. Multiple instances need coordinated delivery. See [Google Cloud's WebSocket guidance](https://cloud.google.com/run/docs/triggering/websockets). Changes to deployment scripts in the repository do not alter an already deployed service until applied. Do not assume Firebase/static hosting rewrites support this connection.

**Checkpoint:** a successful WebSocket connection AND a real test callback are demonstrated. Either alone is insufficient.

## 12. Connect dispositions and recordings

### 12.1 Disposition callback

1. Securely retrieve the generated **Dispo Call URL** shown when saving the connection. Avoid re-saving an incomplete form merely to regenerate the display.
2. Have the vendor place it in the campaign's **Dispo Call URL** configuration and preserve existing integrations.
3. Correct the current generated duration segment: replace `&len=--A--talk_sec--B--` with `&length=--A--talk_time--B--`, verifying that the installed version expands this token. Use the documented `VAR` prefix for variable substitution.
4. Confirm case, agent, disposition and recording tokens are substituted, rather than arriving as literal `--A--...--B--` text.
5. Complete one test call, select its disposition in ViciDial, and verify its RecoverIQ history. Inspect callback response content: HTTP 200 with `ok:false` is a failure.

Illustrative corrected template; retain your actual generated key privately:

```text
VARhttps://recoveriq.example.com/api/integration/vicidial/dispo?key=REPLACE_WITH_GENERATED_SECRET&case=--A--vendor_lead_code--B--&dispo=--A--dispo--B--&rec=--A--recording_filename--B--&agent=--A--user--B--&phone=--A--phone_number--B--&length=--A--talk_time--B--
```

The documented disposition callback includes disposition/talk-time substitutions; confirm support in your installed release using [Call URL features](https://vicidial.org/docs/CALL_URL_FEATURES.txt). This template adjustment does not fix the security/idempotency blockers in Step 1.

**What the present handler does:** adds a call-history entry, updates last contact and disposition, and marks a PTP/PROMISE outcome as PTP status.

**What it does not do:** import a promised date/amount, create the full scheduled callback workflow, verify a payment, post a received amount, or automatically send RecoverIQ's feedback back to ViciDial. Continue using RecoverIQ's normal feedback/PTP/payment forms, and complete the dialer disposition separately. A dialer label `PAID` is not evidence of a received payment.

### 12.2 Choose recording access

First prove recording is enabled and the final audio file exists on the dialer.

**Option A — HTTPS recording access**

1. Obtain the exact approved recording base address from the vendor.
2. Enter it under Recording URL base.
3. Test the resulting URL from an authorised agent's browser. The current handler constructs `base/filename.mp3`; confirm filenames do not already include an extension that produces `.mp3.mp3`.
4. Do not make all recordings public to fix playback. The current direct-link approach does not add arbitrary recording-server authentication headers. Use an authenticated recording gateway if required.

**Option B — SFTP access through RecoverIQ**

1. Complete the SFTP security corrections in Step 1 before production.
2. Ask for a dedicated read-only account restricted to the recordings directory, never root/admin credentials.
3. Enter SFTP host, port, user, password and the exact recordings folder in Connections. Multiple approved folders can be comma-separated. Do not use `/` as a general search root.
4. Allow server-to-server access. Paramiko is already listed in backend requirements; ensure those dependencies were installed in the deployed environment.
5. Complete a test call and play its history recording as an authorised user.

Current SFTP links expire seven days after signing by default; the stored history URL is not refreshed automatically. Long-term playback needs a fresh-authorised-link implementation. Recording retention is controlled separately from GPS route retention. If the audio is not ready when the callback arrives, no later recording-poller service automatically repairs that entry.

## 13. Run the acceptance tests

Use two test agents, two allocated cases, and consenting phone numbers. Record pass/fail, timestamp/timezone, case ID, agent ID and dialer call ID—without secrets or unnecessary personal data.

| Test | Required result |
|---|---|
| ViciDial alone | Working outbound call, two-way audio, disposition and recording |
| API version test | Successful response; followed by separate function-permission tests |
| Manual caller A / caller B | Each action reaches its own mapped agent and the correct customer |
| Same phone, two cases | Outcome attaches to the intended case, never just an arbitrary phone match |
| Cross-branch/unallocated manual case | Backend rejects unauthorised access; current code needs fixing to pass |
| Predictive answer to A | Correct authorised case opens only for A, not B |
| Missing/wrong vendor code | No guessed case; visible/logged integration error |
| Duplicate Start Call delivery | No repeated pop or second predictive event |
| Browser reconnect | Active call recovered when the recovery API permits it |
| New call with an unsaved note | Earlier draft remains accessible; verify before relying on it |
| Disposition callback | Correct case, agent, result and duration |
| Duplicate disposition delivery | No duplicate business history after the idempotency fix |
| Payment/PTP | Amount/date entered through proper forms; no automatic money credit from dialer labels |
| Recording | Correct audio; unauthorised access denied after the recording-access fixes |
| Disabled/revoked integration | All callback paths reject it after lifecycle-control fixes |
| Destination list/branch | Export goes only to the explicitly intended destination |

Stop on any wrong-customer, wrong-agent, cross-branch, duplicate-payment or secret-exposure issue. Do not activate the customer campaign while a security/correlation test is failing.

For developers, isolated screen-pop tests are documented in [PREDICTIVE_SCREENPOP.md](PREDICTIVE_SCREENPOP.md). Mocked tests are not proof of your live dialer configuration, and they do not certify the older manual/disposition paths.

## 14. Give agents their daily instructions

1. Connect headset/network and open Zoiper. Confirm registration.
2. Log into the correct ViciDial agent/phone session and campaign. Establish audio.
3. Log into RecoverIQ with your own account. Keep one main RecoverIQ tab open.
4. For manual work, open your case and use the integrated dial action.
5. For predictive work, become available in ViciDial only when ready. The matching case should open in RecoverIQ after connection; verify the customer before discussing account details.
6. If no case opens or the details look wrong, do not guess or disclose financial information. Pause and alert the supervisor.
7. Finish the ViciDial disposition, and enter required RecoverIQ notes/PTP date/payment details. They are not a complete two-way synchronisation today.
8. Pause the dialer before breaks. At shift end, finish the call, log out of ViciDial, then RecoverIQ, and disconnect the phone session as instructed.

Closing RecoverIQ alone does not pause or log out the dialer. The current connector does not provide every ViciDial agent control inside RecoverIQ, so a completely ViciDial-screen-free shift is not yet implemented.

## 15. Troubleshoot by symptom

| Symptom | Check next |
|---|---|
| Test times out | Backend-to-dialer route, correct base URL, VPN/egress firewall; not only the laptop browser |
| Test passes, Call fails | Agent API permissions and a real logged-in agent/audio session; version is a limited test |
| `agent_user is not logged in` | Employee mapping, ViciDial login, campaign and phone session |
| Zoiper registered, no audio | Agent conference/session, headset/microphone, SIP/RTP routing; ask dialer vendor |
| Wrong number format | Country code added twice, trunk prefix, uploaded number contents |
| Wrong agent/case | Stop calls; verify mapping, IDs, allocation, branch destination and manual correlation bug |
| Missing integration call action | Confirm authorised role, enabled ViciDial connection and current frontend; distinguish `tel:` link |
| Leads reach wrong campaign | Check destination list's campaign in ViciDial; RecoverIQ campaign text does not move it |
| Lead push partially fails | Inspect individual dialer errors and duplicates before retrying the batch |
| Answered audio but no case pop | Callback reachability, VAR expansion, vendor code, mapped agent case access and `/ws` |
| Pop only after tab switch | Push/callback or worker routing problem; recovery check works but live delivery may not |
| `/ws` fails / no 101 | HTTPS/WSS origin, proxy Upgrade, backend process/dependencies, token validity |
| Intermittent pop with several workers | Current delivery hub is process-local; use one worker/instance until shared delivery is built |
| All `--A--...--B--` values arrive literally | Wrong callback field or missing/unsupported VAR substitution |
| No call-history outcome | Dispo Call URL, generated key, exact internal case ID, completion of dialer disposition |
| Duration absent | Correct `len`/`talk_sec` mismatch as described in Step 12 |
| Duplicate history | Current disposition callback lacks deduplication; developer fix, not another retry loop |
| Recording 404 | Recording generation delay, wrong folder/filename/extension, browser reachability |
| Recording 410 after days | Existing signed link expired; fresh-signing implementation required |
| Disabled connection still accepts disposition | Known legacy enabled-state validation gap; stop vendor callback/revoke securely |
| Browser closes/sleeps and no popup | A closed/suspended browser cannot display a case; reconnect recovery is not guaranteed continuous delivery |

Support packet: application version/commit, dialer version, timestamp with timezone, affected employee/case/call IDs, which checkpoint failed, and sanitised response text. Never attach `.env`, SIP/API passwords, full callback URLs, JWT-bearing WS URLs, or borrower exports.

## 16. Maintain and safely stop the integration

### Routine administration

- Review agent maps and campaign access on joiner/leaver/branch changes. Deactivate accounts and sessions in both systems.
- Reconcile assignment changes with already-exported leads before resuming campaigns.
- Back up RecoverIQ's database and the dialer's relevant configuration using restricted access. Test restoration away from production.
- Monitor callback failures, wrong-case rejections, API errors, duplicate outcomes, recording availability and WebSocket reconnections. Do not retain secret-bearing request URLs.
- Agree separate retention/access policies for recordings, customer records, call events and GPS data; do not assume one setting covers all.
- Schedule credential rotation with the vendor. Revoking outbound API credentials does not revoke RecoverIQ's inbound callback key, or vice versa.

### Stop/rollback procedure

1. Pause the affected predictive campaign/list and agents in ViciDial; allow active calls to finish safely.
2. Restore/remove the new Start Call and Dispo callback configurations according to the vendor's saved pre-change settings.
3. Disable the RecoverIQ integration to stop enabled-checked operations. **Do not rely on this alone to revoke legacy disposition/recording access** until the Step 1 fixes are deployed; have the administrator block the affected callback route or securely revoke the integration credential as appropriate.
4. If a code rollback is required, use the previous known-good application release under the normal deployment procedure. Preserve current database records and call history; do not drop the event table or restore an old database over new payments.
5. Re-test standalone ViciDial before resuming its prior workflow. Document the issue and reconcile any partially imported outcomes.

## 17. Administrator handoff checklist

- [ ] Named ViciDial vendor contact and RecoverIQ server administrator.
- [ ] Step 1 code/security blockers resolved and independently tested.
- [ ] Dedicated API service account and function permissions confirmed.
- [ ] Safe network routes, certificates and log redaction confirmed.
- [ ] Existing dialer calls/recordings proven with test numbers.
- [ ] Unique RecoverIQ users, branches and case assignments verified.
- [ ] Unique ViciDial users and SIP registrations verified.
- [ ] Complete employee-to-agent map saved securely.
- [ ] Campaign/list IDs and phone format confirmed.
- [ ] Manual/shared/individual predictive routing decision documented.
- [ ] Start Call URL and Dispo Call URL securely configured and tested.
- [ ] WebSocket upgrade AND actual event delivery verified.
- [ ] One-worker/one-instance limit respected or shared delivery implemented.
- [ ] Case correlation, branch isolation and duplicate-event tests passed.
- [ ] Payment/PTP workflow understood; no assumed two-way financial sync.
- [ ] Recording access, expiration and retention plan approved.
- [ ] Daily agent instructions and stop procedure shared.
- [ ] Organisation owner authorises limited rollout, then monitored expansion.

Keep a private completion record: tested release, date/time, campaign/list, participating agents, test results, unresolved items, and approving administrator. Do not record passwords here.

### Code and reference locations

- Current connector: `app/backend/app/routers/integrations.py`
- Predictive validation/recovery: `app/backend/app/vicidial_live.py`
- WebSocket server: `app/backend/app/routers/realtime.py`
- Connections and calling UI: `app/frontend/app.jsx`
- Predictive browser helper: `app/frontend/predictive-screenpop.js`
- Focused setup: [Predictive screen-pop and WebSockets](PREDICTIVE_SCREENPOP.md)
- Official: [Agent API](https://vicidial.org/docs/AGENT_API.txt), [Non-Agent API](https://vicidial.org/docs/NON-AGENT_API.txt), [Call URL features](https://vicidial.org/docs/CALL_URL_FEATURES.txt)

Treat the installed ViciDial release's documentation as authoritative for version-specific names and options. This guide describes the inspected RecoverIQ code, not a promise that every vendor deployment behaves identically.
