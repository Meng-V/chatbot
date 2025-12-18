# Complete Deployment Guide

**Last Updated**: December 17, 2025  
**Version**: 2.0

---

## Quick Start

### Prerequisites

- Python 3.13+
- PostgreSQL database
- Node.js 18+ (for frontend)
- LibGuides OAuth credentials

### Initial Setup

```bash
# 1. Clone repository
git clone <repository-url>
cd chatbot

# 2. Set up environment variables
cp .env.example .env
# Edit .env with your credentials

# 3. Run automated setup
bash local-auto-start.sh
```

This will:
- Install dependencies
- Sync Prisma schemas
- Check database connection
- Seed library locations
- **Sync MyGuide subjects** (710 subjects)
- Start backend and frontend servers

---

## Database Population

### Step 1: Sync MyGuide Subjects ✅

**Status**: Automatically runs during `local-auto-start.sh`

**Manual execution**:
```bash
cd ai-core
python scripts/sync_myguide_subjects.py
```

**Result**: 710 subjects with course codes synced

### Step 2: Sync LibGuides

**Required**: LibGuides OAuth credentials in `.env`

```bash
cd ai-core
python scripts/sync_libguides.py
```

**Expected output**:
- Fetches all LibGuides from API
- Populates LibGuide table with URLs
- Maps guides to subjects

### Step 3: Sync Staff Directory

**Required**: LibGuides OAuth credentials in `.env`

```bash
cd ai-core
python scripts/sync_staff_directory.py
```

**Expected output**:
- Fetches librarian profiles
- Populates Librarian table with verified contacts
- Detects regional campus librarians
- Maps librarians to subjects

### Full Sync (Recommended)

```bash
cd ai-core
python scripts/sync_all_library_data.py
```

Runs all three syncs in order.

---

## Server Monitoring

### Start Server Monitor

```bash
cd ai-core

# Start in background
nohup python server_monitor.py > logs/monitor_console.log 2>&1 &

# Or use screen
screen -S monitor
python server_monitor.py
# Ctrl+A, D to detach
```

### Configure Email Alerts

Add to `.env`:
```bash
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=your-email@gmail.com
SMTP_PASSWORD=your-app-password
ALERT_EMAIL=admin@example.com
```

**For Gmail**:
1. Enable 2-factor authentication
2. Generate app-specific password
3. Use app password in `SMTP_PASSWORD`

---

## Environment Variables

### Required

```bash
# Database
DATABASE_URL=postgresql://user:password@host:5432/database

# OpenAI
OPENAI_API_KEY=sk-...

# LibGuides OAuth (REQUIRED for subject librarian system)
LIBGUIDE_OAUTH_URL=https://lgapi-us.libapps.com/1.2/oauth/token
LIBGUIDE_CLIENT_ID=719
LIBGUIDE_CLIENT_SECRET=<your-secret>

# MyGuide API
MYGUIDE_ID=u79dXC8ZyA3SHeKm
MYGUIDE_API_KEY=VM5Buj7c298SPNzb3CxXrZGLn6RQpdHEDakh
```

### Optional

```bash
# Email alerts
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=your-email@gmail.com
SMTP_PASSWORD=your-app-password
ALERT_EMAIL=admin@example.com

# Google Site Search
GOOGLE_SEARCH_API_KEY=...
GOOGLE_SEARCH_ENGINE_ID=...

# LibCal API
LIBCAL_CLIENT_ID=...
LIBCAL_CLIENT_SECRET=...
```

---

## Verification

### 1. Check Database Connection

```bash
cd ai-core
.venv/bin/python -c "
import asyncio
from prisma import Prisma

async def test():
    db = Prisma()
    await db.connect()
    count = await db.subject.count()
    print(f'Subjects in DB: {count}')
    await db.disconnect()

asyncio.run(test())
"
```

**Expected**: `Subjects in DB: 710`

### 2. Check LibGuides Sync

```bash
cd ai-core
.venv/bin/python -c "
import asyncio
from prisma import Prisma

async def test():
    db = Prisma()
    await db.connect()
    count = await db.libguide.count()
    print(f'LibGuides in DB: {count}')
    await db.disconnect()

asyncio.run(test())
"
```

**Expected**: `LibGuides in DB: 100+`

### 3. Check Staff Directory Sync

```bash
cd ai-core
.venv/bin/python -c "
import asyncio
from prisma import Prisma

async def test():
    db = Prisma()
    await db.connect()
    total = await db.librarian.count()
    regional = await db.librarian.count(where={'isRegional': True})
    print(f'Librarians in DB: {total}')
    print(f'Regional campus: {regional}')
    await db.disconnect()

asyncio.run(test())
"
```

**Expected**: `Librarians in DB: 20+`, `Regional campus: 5+`

### 4. Test Subject Librarian Query

```bash
curl -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"message": "Who is the biology librarian?"}' \
  | python3 -m json.tool
```

**Expected response should include**:
- LibGuide URL
- Librarian name and email
- No "trouble accessing systems" error

---

## Maintenance

### Daily

- [ ] Check server monitor is running
- [ ] Review `logs/errors.log` for critical issues
- [ ] Verify server uptime

### Weekly

- [ ] Review all logs for patterns
- [ ] Check disk space usage
- [ ] Verify email alerts working
- [ ] Test health endpoint

### Monthly

- [ ] Run full data sync: `python scripts/sync_all_library_data.py`
- [ ] Archive old logs
- [ ] Test restart functionality
- [ ] Review restart frequency
- [ ] Update alert contacts if needed

### Quarterly

- [ ] Review and update subject mappings
- [ ] Verify all librarian contacts are current
- [ ] Check LibGuide URLs are valid
- [ ] Update course codes if catalog changed

---

## Troubleshooting

### Server Won't Start

**Check**:
1. Database connection: `psql $DATABASE_URL`
2. Port 8000 available: `lsof -i:8000`
3. Python environment: `cd ai-core && .venv/bin/python --version`
4. Dependencies installed: `cd ai-core && .venv/bin/pip list`

**Fix**:
```bash
# Kill any existing process
pkill -f "uvicorn src.main"

# Restart
cd ai-core
.venv/bin/uvicorn src.main:app_sio --host 0.0.0.0 --port 8000 --reload
```

### Subject Librarian Queries Failing

**Symptoms**: "Trouble accessing systems" error

**Check**:
```bash
cd ai-core

# Check if LibGuides synced
.venv/bin/python -c "
import asyncio
from prisma import Prisma
async def test():
    db = Prisma()
    await db.connect()
    print(f'LibGuides: {await db.libguide.count()}')
    print(f'Librarians: {await db.librarian.count()}')
    await db.disconnect()
asyncio.run(test())
"
```

**Fix**:
```bash
# Run syncs
python scripts/sync_libguides.py
python scripts/sync_staff_directory.py
```

### Monitor Not Sending Emails

**Check**:
1. SMTP credentials in `.env`
2. Gmail app password (not regular password)
3. Firewall not blocking port 587
4. Check `logs/server_monitor.log` for email errors

**Test**:
```python
import smtplib
from email.mime.text import MIMEText

msg = MIMEText("Test")
msg['Subject'] = 'Test'
msg['From'] = 'your-email@gmail.com'
msg['To'] = 'admin@example.com'

server = smtplib.SMTP('smtp.gmail.com', 587)
server.starttls()
server.login('your-email@gmail.com', 'your-app-password')
server.send_message(msg)
server.quit()
print("✅ Email sent")
```

### High Memory Usage

**Check**:
```bash
# Monitor memory
watch -n 5 'curl -s http://localhost:8000/health | python3 -m json.tool | grep -A5 memory'
```

**Fix**:
- Restart server
- Check for memory leaks in logs
- Increase server resources

---

## Production Checklist

### Before Deployment

- [ ] All environment variables configured
- [ ] Database connection tested
- [ ] MyGuide subjects synced (710 subjects)
- [ ] LibGuides synced (100+ guides)
- [ ] Staff directory synced (20+ librarians)
- [ ] Health endpoint responding
- [ ] Test queries working
- [ ] Email alerts configured and tested
- [ ] Server monitor running
- [ ] Logs directory created
- [ ] Log rotation configured

### After Deployment

- [ ] Monitor logs for first 24 hours
- [ ] Verify no crashes
- [ ] Check response times
- [ ] Test all major query types
- [ ] Verify email alerts working
- [ ] Set up monthly sync schedule
- [ ] Document any issues

---

## Support

### Log Files

- `logs/app.log` - General application logs
- `logs/errors.log` - Error logs
- `logs/agents.log` - Agent execution logs
- `logs/api.log` - API request logs
- `logs/server_monitor.log` - Monitor activity
- `logs/server.log` - Server stdout
- `logs/server_error.log` - Server stderr

### Common Issues

1. **"Trouble accessing systems"** → Run LibGuides and staff directory sync
2. **Server crashes frequently** → Check logs, increase resources
3. **Slow responses** → Check database connection, optimize queries
4. **Wrong librarian returned** → Verify subject mappings, re-run sync

### Getting Help

1. Check logs first
2. Review error messages
3. Test individual components
4. Check database state
5. Verify API credentials
