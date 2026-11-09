"""Up-to-date in-app guide the AI quotes from (tool: app_help). One section per screen / task."""

HELP = {
    "roles": "Roles: Admin (everything), Head Office (all branches & portfolios), Manager (own branch), Team Lead (own team's cases; "
             "can also upload/allocate for the team), Tele-caller (own calling queue), Field Agent / FOS (own field cases), HR (staff, leave, "
             "letters, payroll prep), Back office, IT Support View (read-only). A person can hold two hats (e.g. Caller + Team Lead, "
             "Manager + Caller) and switch with 'Switch view' at the top.",
    "accounts": "Accounts / Portfolios: pick Bank → Product → Month → Branch. Upload a bank's allocation file with ⬆ Upload (choose month/year "
                "and branch) → Preview → Import & Allocate (FOS / caller by employee ID in the file). Re-uploading updates existing cases. "
                "'Correct columns' fixes specific columns from a corrected file. Select cases to delete / restore, re-allocate, joint-allocate "
                "to another FOS, or escalate. ⬇ Download gives a styled Excel of any portfolio. Click a case to open its drawer (details, "
                "Call / Visit / Pay tabs, history, UPI link).",
    "live_sheet": "Live Sheet: spreadsheet view of your cases with month filter; edit allowed cells (TOS, NORM, STAB, remarks…) and they save "
                  "live for everyone; 📞 calls through ViciDial when connected.",
    "calling": "Calling: open a case → Call tab → pick disposition (PTP / RTP / RNR / PAID …), PTP amount & date, remark → Save. With ViciDial, "
               "'Call via ViciDial' dials from your agent session; the live-call bar shows Dialing → On call → Call ended; Hang up and "
               "'Save & Ready' disposition the call in ViciDial and put you back to Ready.",
    "ptp": "PTP Tracker: promises split into Overdue / Today / Upcoming; filter by bank, product, dates, caller, FOS; last 5 notes per case.",
    "field": "Field visits (FOS app): open case → Log visit → 📷 capture (GPS + time stamped) → choose address → disposition / payment → Save. "
             "Managers see Field Tracking: live map, route history and replay, 🚩 Flagged visits (fake-visit trust score), route exports.",
    "mis": "MIS: live MIS per portfolio with month chips; cycle MIS; targets (default 85%); 📊 MIS Pivot opens the bank-format pivot workbook "
           "with filters, print and Excel download. My Performance shows each agent's own numbers and leaderboard.",
    "dpr": "DPR upload: Accounts → portfolio → DPR → choose month → upload the bank's daily progress file → preview → apply; paid / partial "
           "status and collections update.",
    "feedback": "Bank Feedback: per-portfolio feedback sheet that fills from call/visit logs; edit and download for the bank.",
    "attendance": "Attendance: 🕐 top-right. Check in from the app (FOS with GPS selfie). Late after 10:00, half day after 11:30, 7 pm "
                  "auto-logout; reports by day, month or salary cycle (21st→20th) with Excel download.",
    "leave": "Leave: Apply (full or half day), approvers see pending requests and approve/reject; balances per type.",
    "team": "Team / Manpower: add staff (role, branch, IDs), dual roles (Also team lead / field agent / caller), block or reactivate, "
            "documents, offer & agreement letters with signatures, profile change requests.",
    "salary": "Salary & Payslips (Admin/HR): set salary per employee, rules (cycle, LOP, components, PF/ESI/PT/LWF, income tax), monthly "
              "payroll run → approve (password + 2FA + typed total) → bank upload file or payout gateway → mark paid → release payslips. "
              "Income tax tab: regimes, declarations, Form 16 Part B statements, 24Q. Full & final for leavers. Employees: 🧾 My Payslips.",
    "dialer": "Connections (admin): ViciDial server, API user, campaigns, agent map (employee code → ViciDial user), disposition map, "
              "Dispo-call and screen-pop URLs to paste into ViciDial. Each caller sets their own agent ID in Security.",
    "chat": "Chat (bubble bottom-right): message colleagues, broadcast, voice call in the browser.",
    "security": "Security: change password, set up 2FA (authenticator app), passkeys / fingerprint login, your ViciDial agent ID.",
    "services": "⚙️ Services (top-right, Admin): turn any service on or off for the whole company and set its options. 🧩 Add-ons lists "
                "extra modules: AI Assist, Compliance, Payment links, Outreach journeys, Settlement, Smart allocation, Legal notices, "
                "Analytics, Billing, Skip tracing, Open API.",
    "ai": "AI Assist: ask in plain words about your cases, PTPs, team, visits, calls, attendance, leave or payslips — answers use only data "
          "you are allowed to see. Ask for 'an Excel / PDF / Word of …' to get a download. It can suggest actions (set a follow-up, open a "
          "case, draft a WhatsApp) which you confirm.",
}


def app_help(topic: str | None) -> dict:
    t = (topic or "").lower()
    if not t:
        return {"sections": list(HELP)}
    hits = {k: v for k, v in HELP.items() if k in t or any(w in v.lower() for w in t.split() if len(w) > 3)}
    return {"help": hits or HELP}
