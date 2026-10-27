# DIALOG Pizza — Security Guidelines

> **Last updated:** 2026-10-20  
> **Status:** Local development — Not for public deployment without additional hardening

---

## 🔒 Credentials & Configuration Security

### Required Environment Variables

The following environment variables **MUST** be set with strong, unique values:

```bash
# Generate admin password (minimum 16 characters)
ADMIN_PASSWORD=$(openssl rand -hex 16)

# Generate auth secret (minimum 32 bytes)
AUTH_SECRET=$(openssl rand -hex 32)
```

**Never use the example values** from old documentation:
- ❌ `ADMIN_PASSWORD=dialog2026` (insecure default, rejected by the app)
- ❌ `AUTH_SECRET=change-me-in-production` (insecure default, app auto-generates if missing)

### Auto-Generated Secrets

If `AUTH_SECRET` is not set in `.env`, the application will:
1. Generate a cryptographically secure random secret (64 hex characters)
2. Save it to `.auth_secret` in the project root (gitignored)
3. Issue a warning to set `AUTH_SECRET` in `.env` for production

**For production:** Always set `AUTH_SECRET` explicitly in `.env`. The auto-generated file is for local development convenience only.

### API Keys

Third-party API keys should be treated as secrets:

| Service | Environment Variable | Where to Get |
|---------|---------------------|--------------|
| Groq (LLM) | `GROQ_API_KEY` | https://console.groq.com |
| Deepgram (STT/TTS) | `DEEPGRAM_API_KEY` | https://console.deepgram.com |
| LiveKit (Voice RTC) | `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET` | https://cloud.livekit.io |
| Twilio (SMS) | `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN` | https://console.twilio.com |
| Razorpay (Payments) | `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET` | https://dashboard.razorpay.com |

**All keys must be kept private.** Never commit them to version control.

---

## 📁 Files Protected from Git

The `.gitignore` file excludes:

```
.env                    # Active configuration with real credentials
.env.local              # Alternative local config
*.db                    # SQLite database files
*.db-journal, *.db-wal  # SQLite journal files
data/voice_ordering.db  # Production database
data/tickets/*.json     # Kitchen tickets (may contain PII)
data/notifications/     # Order notifications (may contain phone numbers)
.auth_secret            # Auto-generated auth secret
```

**Before initializing Git:** Verify no secrets are tracked:
```powershell
git status --ignored
```

---

## 🚨 Error Messages & Logging

### Client-Facing Errors

API errors exposed to clients (web dashboard, voice agent) are sanitized:

✅ **Safe:**
```
"I'm having trouble reaching the AI service right now."
"This item is not available please order something else"
```

❌ **Unsafe (removed):**
```
"I'm having trouble reaching the AI service (AuthenticationError: Invalid API key gsk_...)"
```

### Server-Side Logging

Internal errors are logged server-side with full details for debugging, but never sent to the client.

**Example:**
```python
try:
    reply, tool_results = self._run_groq_loop()
except Exception as exc:
    # Client gets generic error
    reply = "I'm having trouble reaching the AI service right now."
    
    # Server logs the full error
    logging.error(f"Groq chat error for session {self._session_id}: {exc}")
```

---

## 🔍 Credential Exposure Checks

### Scripts That Handle Credentials

These PowerShell scripts validate credentials **without printing values:**

- `scripts/check_groq_key.ps1` — Validates `GROQ_API_KEY` format (gsk_ prefix, length)
- `scripts/check_deepgram.ps1` — Validates `DEEPGRAM_API_KEY` is set
- `scripts/check_prerequisites.ps1` — Checks all required keys

They print **only**:
- ✅ Whether the key is set
- ✅ Key length
- ✅ Format validation (prefix check)
- ❌ Never the actual key value

### Frontend Security

The web dashboard (`apps/web/web/static/`) is vanilla HTML/CSS/JS with:

✅ **Safe:**
- LiveKit tokens are generated server-side (FastAPI endpoint)
- Admin tokens are stored in localStorage (requires XSS fix — see DIALOG_PROGRESS.md)
- No API keys embedded in frontend code

❌ **Not included in frontend:**
- GROQ_API_KEY
- DEEPGRAM_API_KEY
- LIVEKIT_API_SECRET
- Database credentials
- Admin password

---

## 🛡️ Security Checklist for Production

**Before any deployment:**

- [ ] Set `ADMIN_PASSWORD` to a strong unique password (min 16 chars)
- [ ] Set `AUTH_SECRET` to a strong unique secret (min 32 hex chars)
- [ ] Review all API keys are valid and have appropriate rate limits configured at the provider
- [ ] Verify `.env` is not tracked by Git
- [ ] Verify `data/voice_ordering.db` is not tracked by Git
- [ ] Change `host="0.0.0.0"` to `host="127.0.0.1"` in `apps/web/web/main.py:323` if running locally
- [ ] Enable HTTPS/TLS for all external connections
- [ ] Implement rate limiting on authentication endpoints
- [ ] Fix XSS vulnerabilities (see DIALOG_PROGRESS.md findings F04-F05)
- [ ] Add authentication to tool/chat endpoints (see findings F08-F09)
- [ ] Review and rotate all API keys if any were previously exposed

---

## 🔄 Credential Rotation

If credentials were exposed (committed to Git, posted publicly, etc.):

### 1. Rotate API Keys

| Provider | Rotation Steps |
|----------|----------------|
| **Groq** | 1. Login to console.groq.com<br>2. Navigate to API Keys<br>3. Revoke the exposed key<br>4. Create a new key<br>5. Update `.env` |
| **Deepgram** | 1. Login to console.deepgram.com<br>2. Navigate to API Keys<br>3. Delete the exposed key<br>4. Create a new key<br>5. Update `.env` |
| **LiveKit** | 1. Login to cloud.livekit.io<br>2. Navigate to Settings → Keys<br>3. Delete the exposed key pair<br>4. Create new API Key + Secret<br>5. Update `.env` |
| **Twilio** | 1. Login to console.twilio.com<br>2. Reset Auth Token<br>3. Update `.env` |
| **Razorpay** | 1. Login to dashboard.razorpay.com<br>2. Navigate to Settings → API Keys<br>3. Regenerate keys<br>4. Update `.env` |

### 2. Regenerate Local Secrets

```powershell
# Regenerate admin password
$newPassword = -join ((48..57) + (65..90) + (97..122) | Get-Random -Count 20 | ForEach-Object {[char]$_})
# Update .env: ADMIN_PASSWORD=$newPassword

# Regenerate auth secret
$newSecret = [System.Convert]::ToBase64String((1..32 | ForEach-Object { Get-Random -Minimum 0 -Maximum 256 }))
# Update .env: AUTH_SECRET=$newSecret

# Or use OpenSSL (Git Bash):
openssl rand -hex 32
```

### 3. Clear Git History (if exposed)

**⚠️ Only if credentials were committed to Git history:**

```powershell
# This project currently has no Git repo, so this is not needed yet
# If Git is initialized later and secrets are accidentally committed:

# Option 1: Reset to before the commit (if caught early)
git reset --hard HEAD~1

# Option 2: Use git-filter-repo to rewrite history (advanced)
# Install: pip install git-filter-repo
git filter-repo --invert-paths --path .env
git filter-repo --replace-text <(echo "GROQ_API_KEY=***REMOVED***")
```

**Important:** Rewriting Git history requires force-push, which breaks clones. Only do this on local-only repositories.

---

## 📊 Current Security Status

| Check | Status | Notes |
|-------|--------|-------|
| Git initialized | ❌ No | No risk of committed secrets yet |
| `.env` gitignored | ✅ Yes | `.env` is in `.gitignore` |
| Database gitignored | ✅ Yes | `*.db` patterns added (2026-10-20) |
| Hardcoded secrets removed | ✅ Yes | F01, F02 fixed (2026-10-20) |
| Error message sanitization | ✅ Yes | Client errors sanitized (2026-10-20) |
| API keys in frontend | ✅ No | All keys are server-side only |
| Source maps exposed | ✅ No | No app source maps generated |

---

## 📞 Security Incident Response

If you discover a security issue:

1. **Do not** post the issue publicly or commit sensitive details
2. Document the exposure scope (what was exposed, where, when)
3. Rotate affected credentials immediately (see Credential Rotation section)
4. Update `.gitignore` if files were tracked unintentionally
5. Review logs for unauthorized access if applicable
6. Update DIALOG_PROGRESS.md with the incident details

---

## 🔗 Related Documentation

- **DIALOG_PROGRESS.md** — Full security audit findings and remediation plan
- **README.md** — Quick start guide
- **.env.example** — Template for environment configuration

---

**Remember:** This project is for **local development** only. Production deployment requires additional security hardening beyond these guidelines.
