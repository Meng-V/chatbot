# Environment Files - Quick Reference

## 📁 Current Structure

```
chatbot/
├── .env              ✅ Main configuration (YOUR production values)
├── .env.local        ✅ Local overrides (for development)
└── .env.example      ✅ Template (safe to commit)
```

**That's it! Just 3 files, all in the root directory.**

---

## 🚀 Quick Start

### New Developer Setup

```bash
# 1. Copy template
cp .env.example .env

# 2. Edit with your values
nano .env

# 3. (Optional) Create local overrides
cp .env.local .env.local
nano .env.local
```

### Existing Developer

Your environment is already configured! No action needed.

---

## 📝 What Goes Where

### .env (Production Config)
- All API keys and secrets
- Production database URLs
- Production service endpoints
- **NOT committed to git** ❌

### .env.local (Your Local Overrides)
- Local database: `postgresql://localhost:5432/dev`
- Local URLs: `http://localhost:8000`
- Test API keys (optional)
- **NOT committed to git** ❌

### .env.example (Template)
- Placeholder values
- Shows all required variables
- Documentation for developers
- **Committed to git** ✅

---

## 🔍 How to Use

### For Local Development

Create `.env.local` to override production values:

```bash
# .env.local
DATABASE_URL=postgresql://localhost:5432/chatbot_dev
FRONTEND_URL=http://localhost:5173
VITE_BACKEND_URL=http://localhost:8000
NODE_ENV=development
```

### For Production

Keep production values in `.env`:

```bash
# .env
DATABASE_URL=postgresql://prod-server/smartchatbot_db?sslmode=require
FRONTEND_URL=https://new.lib.miamioh.edu
VITE_BACKEND_URL=https://new.lib.miamioh.edu
NODE_ENV=production
```

---

## 🎯 Loading Priority

```
.env.local  ← Overrides .env (if exists)
.env        ← Base configuration
```

---

## ✅ Verification

### Check if .env is loaded:

**Backend**:
```bash
cd ai-core
source .venv/bin/activate
python -c "import os; print(os.getenv('DATABASE_URL', 'NOT LOADED'))"
```

**Frontend**:
```bash
cd client
npm run start
# Check console: import.meta.env.VITE_BACKEND_URL
```

---

## 🔧 Common Commands

```bash
# View your .env (without secrets shown in terminal history)
cat .env

# Edit .env
nano .env

# Copy template to create new .env
cp .env.example .env

# Create local overrides
cp .env.local .env.local
```

---

## ⚠️ Important

- **NEVER commit `.env` or `.env.local`** (already in .gitignore)
- **DO commit `.env.example`** (safe template)
- Restart servers after changing `.env`:
  - Backend: `Ctrl+C` and restart uvicorn
  - Frontend: `Ctrl+C` and `npm run start`

---

## 📍 File Locations

```
✅ /chatbot/.env              (ONE main file)
✅ /chatbot/.env.local         (ONE local override)
✅ /chatbot/.env.example       (ONE template)

❌ /chatbot/ai-core/.env       (DELETED)
❌ /chatbot/client/.env        (DELETED)
```

---

**Simple. Clean. Easy to manage.** ✨
