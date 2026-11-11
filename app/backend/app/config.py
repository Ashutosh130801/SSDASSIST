from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg2://ssd:ssd_password@localhost:5432/ssd_recovery"
    secret_key: str = "dev-secret-change-me"
    access_token_expire_minutes: int = 720
    algorithm: str = "HS256"

    google_client_id: str = ""
    google_maps_api_key: str = ""

    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.8-flash"

    # LocationIQ geocoding (address -> lat/long). Free tier key from locationiq.com.
    # Swappable: set google_maps_api_key later to move geocoding to Google (see memory note).
    locationiq_key: str = ""
    # Google Geocoding API key (much better for Indian addresses). When set, address lookup uses
    # Google; LocationIQ stays as the fallback when this is blank.  .env: GOOGLE_GEOCODING_KEY=...
    google_geocoding_key: str = ""
    # Backup lookup for hard (landmark-style / informal) addresses: Google Places text search, the
    # same search as the Google Maps app. Used ONLY when Geocoding finds just the area/pincode.
    # Max Places lookups per day (0 = off). Needs "Places API (New)" enabled on the same key.
    google_places_daily_cap: int = 300

    # OpenRouter (OpenAI-compatible) for the AI address-cleaning step. If set, it's used in
    # preference to Gemini. Pick any model on openrouter.ai; a small cheap one is plenty here.
    openrouter_api_key: str = ""
    openrouter_model: str = "openai/gpt-4o-mini"

    location_ping_seconds: int = 3

    # In-app WebRTC voice calling (staff↔staff over the chat). Self-hosted coturn provides STUN+TURN
    # for NAT traversal. Leave blank to use only public STUN (works on many networks, not all).
    #   STUN_URL=stun:your.server:3478
    #   TURN_URL=turn:your.server:3478   TURN_USER=recoveriq   TURN_PASSWORD=<secret>
    stun_url: str = "stun:stun.l.google.com:19302"
    turn_url: str = ""
    # Preferred: a shared secret (matches eturnal's `secret` / coturn `static-auth-secret`).
    # The server mints short-lived per-user TURN credentials from it — nothing static is shipped.
    turn_secret: str = ""
    turn_ttl_seconds: int = 3600
    # Fallback: a fixed username/password (only used if turn_secret is blank).
    turn_user: str = ""
    turn_password: str = ""

    # RazorpayX Payouts (salary via gateway). Keys live ONLY here (.env) — never in the DB or UI.
    #   RAZORPAYX_KEY_ID=rzp_test_...   RAZORPAYX_KEY_SECRET=...
    #   RAZORPAYX_ACCOUNT_NUMBER=<your RazorpayX business account number (Dashboard → My Account)>
    #   RAZORPAYX_WEBHOOK_SECRET=<the secret you type when adding the webhook in the Dashboard>
    # Live keys (rzp_live_...) are REFUSED unless RAZORPAYX_ALLOW_LIVE=true is also set.
    razorpayx_key_id: str = ""
    razorpayx_key_secret: str = ""
    razorpayx_account_number: str = ""
    razorpayx_webhook_secret: str = ""
    razorpayx_allow_live: bool = False
    # 💳 Payment links add-on (Razorpay Payment Links). Test keys (rzp_test_…) only unless RAZORPAY_ALLOW_LIVE=true.
    razorpay_key_id: str = ""
    razorpay_key_secret: str = ""
    razorpay_webhook_secret: str = ""
    razorpay_allow_live: bool = False
    # Public address customers open (/pay/<token>), e.g. https://recoveriq.ssdenterprises.org.in
    public_base_url: str = ""
    # 📣 Outreach add-on providers
    msg91_auth_key: str = ""
    msg91_sender: str = ""
    whatsapp_token: str = ""
    whatsapp_phone_id: str = ""
    payout_max_item_rupees: int = 200000      # hard cap per employee per payout
    payout_max_batch_rupees: int = 2500000    # hard cap per batch

    # Product branding (shown on login + sidebar). Change to your own brand.
    brand_name: str = "RecoverIQ"
    brand_tagline: str = "Collections & Recovery Intelligence"

    # Google Cloud Storage for visit photos. When empty, photos save to the local
    # ./uploads folder (fine for one server; ephemeral on Cloud Run). Set a bucket
    # name to store photos in GCS and serve them via short-lived signed URLs.
    gcs_bucket: str = ""
    gcs_signed_url_seconds: int = 604800   # 7 days

    # Login brute-force protection
    login_max_attempts: int = 5            # wrong passwords before a temporary lock
    login_lockout_minutes: int = 15        # how long the account is locked

    # WebAuthn / passkeys (biometric login). Leave blank to auto-derive from the request
    # host; set explicitly in production, e.g. RP_ID=app.yourco.com, ORIGIN=https://app.yourco.com
    webauthn_rp_id: str = ""
    webauthn_origin: str = ""

    # UPI collection (for payment links/QR). Set your collection UPI id.
    upi_vpa: str = ""
    upi_payee_name: str = "SSD Enterprises"
    # Geo-fence: flag a field visit logged more than this many metres from the case location.
    geofence_metres: int = 250

    # Comma-separated list of allowed browser origins (CORS). Empty = same-origin only,
    # which is correct when the backend serves the frontend (our default deploy).
    cors_origins: str = ""
    environment: str = "development"   # set ENVIRONMENT=production in the cloud

    admin_email: str = "admin@ssdenterprises.in"
    admin_password: str = "Admin@2006"

    # SMTP for HR emails (offer letters). Use an app password for Gmail.
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""              # falls back to smtp_user
    company_name: str = "SSD Enterprises"

    # Dialer scheme telecallers use — Zoiper (registered on the phone, wired to the Dinstar
    # gateway) picks up "zoiper:<number>" links. Change to sip / callto / tel if needed.
    call_scheme: str = "zoiper"

    # Set to true (env SEED_ON_START=1) for the first cloud deploy to create the
    # demo staff/admin, then redeploy with it off.
    seed_on_start: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()
# config end
