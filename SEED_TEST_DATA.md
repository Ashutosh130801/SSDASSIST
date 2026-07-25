# Test data (ICICI FR X-BKT) — load & wipe

A one-command reset that loads a realistic **test** dataset from the ICICI FR sheet so
every dashboard, MIS table and role view has real data to work with. Use it for testing
only; wipe it before you go live.

## Load the test data

From `app/backend` (with the virtualenv active and the same `DATABASE_URL` your server uses):

```bash
python seed_fr_test.py
```

This **erases the whole database**, then creates:

| Login | Password | Role |
|-------|----------|------|
| admin@ssd.local | Test@1234 | Administrator |
| manager@ssd.local | Test@1234 | Collections Manager (branch **Vizag**) |
| backend@ssd.local | Test@1234 | Back-office Official |
| caller1@ssd.local … | Test@1234 | Tele-calling Agents (one per caller in the sheet) |
| fos1@ssd.local … | Test@1234 | Field Agents (one per FOS in the sheet) |

…and imports **993 ICICI · FR · Credit Card** cases from
`app/backend/seed_data/fr_xbkt_july26.xlsx`, each assigned to its caller (by name) and FOS.
The MIS reproduces the sheet exactly (ENR-based: PAID ≈ 44.08%, NORM + STAB split, VISITED,
by caller / FOS / area / cycle).

Restart the app after seeding and log in as `admin@ssd.local`.

## Wipe everything before production

Re-running the script always wipes first, so to go to a clean slate for live data:

1. Stop the server.
2. Point `seed_fr_test.py` at an empty branch by editing the file, **or** simply delete the
   database file / drop-and-recreate the Postgres schema.
3. Start the server and upload your real data through the app (Accounts → Upload).

The script never runs automatically — it only wipes when **you** run it.
