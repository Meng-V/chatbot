# Setup and Deployment Guide

**Last Updated:** December 16, 2025  
**Version:** 3.0.0

---

## Table of Contents
1. [Prerequisites](#prerequisites)
2. [Initial Setup](#initial-setup)
3. [Database Setup](#database-setup)
4. [Environment Configuration](#environment-configuration)
5. [Running Locally](#running-locally)
6. [Production Deployment](#production-deployment)
7. [Server Maintenance](#server-maintenance)

---

## Prerequisites

### Required Software

**On Development Machine:**
- Python 3.13
- Node.js 18+ and npm
- Git
- PostgreSQL client (for database access)

**On Production Server:**
- Ubuntu/Linux server
- Python 3.13
- Node.js 18+
- PostgreSQL database (can be remote)
- Nginx or Apache (for frontend serving)
- Process manager (systemd recommended)

### Required Accounts & API Keys

You'll need accounts and API keys for:
- **OpenAI** - For o4-mini model
- **SpringShare** - For LibCal, LibGuides, LibAnswers APIs
- **Google** - For Custom Search Engine API
- **Weaviate Cloud** - For RAG correction pool
- **PostgreSQL Database** - For conversation storage

---

## Initial Setup

### 1. Clone Repository

```bash
git clone <repository-url>
cd chatbot
```

### 2. Backend Setup

```bash
cd ai-core

# Create Python virtual environment
python3.13 -m venv venv

# Activate virtual environment
source venv/bin/activate  # On macOS/Linux
# OR
venv\Scripts\activate  # On Windows

# Install dependencies
pip install -e .

# Generate Prisma client
prisma generate
```

### 3. Frontend Setup

```bash
cd client

# Install dependencies
npm install

# Build for production (optional)
npm run build
```

---

## Database Setup

### PostgreSQL Database

**Connection Details:**
- Host: ulblwebt04.lib.miamioh.edu
- Database: smartchatbot_db
- Schema: public

### Initialize Database Schema

```bash
cd /path/to/chatbot

# Using JavaScript Prisma (recommended)
npx prisma db push --schema=./prisma/schema.prisma

# Verify tables created
npx prisma studio --schema=./prisma/schema.prisma
```

### Seed Library Location Data

```bash
cd ai-core
source venv/bin/activate

# Seed campuses, libraries, and spaces
python -m scripts.seed_library_locations
```

**This creates:**
- 3 Campuses (Oxford, Hamilton, Middletown)
- 4 Libraries with contact info and LibCal IDs
- 2 Library spaces (Makerspace, Special Collections)

### Load Subject-Librarian Mappings

Subject mappings should be pre-loaded in the database. If starting fresh:

```bash
# Contact development team for MuGuide data dump
# Or use existing database backup
```

---

## Environment Configuration

### Create .env File

Copy the example environment file:

```bash
cp .env.example .env
```

### Required Environment Variables

See `07-ENVIRONMENT-VARIABLES.md` for complete reference.

**Critical Variables:**

```bash
# OpenAI
OPENAI_API_KEY=sk-...
OPENAI_MODEL=o4-mini

# Database
DATABASE_URL=postgresql://user:password@host/database?sslmode=require

# Weaviate
WEAVIATE_URL=https://your-cluster.weaviate.network
WEAVIATE_API_KEY=...

# LibCal API
LIBCAL_CLIENT_ID=...
LIBCAL_CLIENT_SECRET=...
LIBCAL_TOKEN_URL=https://miamioh.libcal.com/1.1/oauth/token
LIBCAL_API_BASE_URL=https://miamioh.libcal.com/1.1

# LibCal Location IDs (Hours API)
LIBCAL_KING_LOCATION_ID=8113
LIBCAL_ART_LOCATION_ID=8116
LIBCAL_HAMILTON_LOCATION_ID=9226
LIBCAL_MIDDLETOWN_LOCATION_ID=9227

# LibCal Building IDs (Reservations API)
LIBCAL_KING_BUILDING_ID=2047
LIBCAL_ART_BUILDING_ID=4089
LIBCAL_HAMILTON_BUILDING_ID=4792
LIBCAL_MIDDLETOWN_BUILDING_ID=4845

# LibCal Ask Us Hours
LIBCAL_ASKUS_ID=8876

# LibGuides API
LIBGUIDES_SITE_ID=2047
LIBGUIDES_API_KEY=...
LIBGUIDES_API_URL=https://lgapi-us.libapps.com/1.1

# LibAnswers (Chat Handoff)
LIBANSWERS_IID=2047
LIBANSWERS_CLIENT_ID=...
LIBANSWERS_CLIENT_SECRET=...

# Google Custom Search
GOOGLE_CSE_API_KEY=...
GOOGLE_CSE_CX=...
```

---

## Running Locally

### Quick Start (Both Backend + Frontend)

```bash
# From project root
./local-auto-start.sh
```

This script:
1. Starts backend on port 8000
2. Starts frontend on port 5173
3. Opens browser automatically

### Manual Start

**Backend Only:**
```bash
cd ai-core
source venv/bin/activate
python -m uvicorn src.main:app --reload --port 8000
```

**Frontend Only:**
```bash
cd client
npm run dev
```

### Access the Application

- **Frontend**: http://localhost:5173
- **Backend API**: http://localhost:8000
- **API Docs**: http://localhost:8000/docs
- **Health Check**: http://localhost:8000/health

---

## Production Deployment

### Server Preparation

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install Python 3.13
sudo apt install python3.13 python3.13-venv python3-pip

# Install Node.js 18+
curl -fsSL https://deb.nodesource.com/setup_18.x | sudo -E bash -
sudo apt install -y nodejs

# Install nginx
sudo apt install nginx
```

### Deploy Backend

```bash
# Clone repository
cd /var/www
sudo git clone <repository-url> chatbot
sudo chown -R www-data:www-data chatbot

# Setup Python environment
cd chatbot/ai-core
python3.13 -m venv venv
source venv/bin/activate
pip install -e .
prisma generate

# Create .env file (copy from secure location)
nano ../.env
# Paste environment variables

# Test backend
python -m uvicorn src.main:app --host 0.0.0.0 --port 8000
```

### Create Systemd Service

Create `/etc/systemd/system/chatbot-backend.service`:

```ini
[Unit]
Description=Miami Libraries Chatbot Backend
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory=/var/www/chatbot/ai-core
Environment="PATH=/var/www/chatbot/ai-core/venv/bin"
ExecStart=/var/www/chatbot/ai-core/venv/bin/python -m uvicorn src.main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl daemon-reload
sudo systemctl enable chatbot-backend
sudo systemctl start chatbot-backend
sudo systemctl status chatbot-backend
```

### Deploy Frontend

```bash
cd /var/www/chatbot/client

# Install dependencies
npm install

# Build for production
npm run build

# Built files are in dist/ folder
```

### Configure Nginx

Create `/etc/nginx/sites-available/chatbot`:

```nginx
server {
    listen 80;
    server_name new.lib.miamioh.edu;

    # Frontend (React app)
    location /smartchatbot {
        alias /var/www/chatbot/client/dist;
        try_files $uri $uri/ /smartchatbot/index.html;
    }

    # Backend API
    location /smartchatbot/api {
        proxy_pass http://localhost:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_cache_bypass $http_upgrade;
    }

    # WebSocket for Socket.IO
    location /smartchatbot/socket.io {
        proxy_pass http://localhost:8000/socket.io;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "Upgrade";
        proxy_set_header Host $host;
    }
}
```

Enable site:
```bash
sudo ln -s /etc/nginx/sites-available/chatbot /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

### SSL Certificate (Let's Encrypt)

```bash
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d new.lib.miamioh.edu
```

---

## Server Maintenance

### View Logs

```bash
# Backend logs
sudo journalctl -u chatbot-backend -f

# Nginx logs
sudo tail -f /var/log/nginx/access.log
sudo tail -f /var/log/nginx/error.log
```

### Restart Services

```bash
# Backend
sudo systemctl restart chatbot-backend

# Nginx
sudo systemctl reload nginx
```

### Update Application

```bash
cd /var/www/chatbot

# Pull latest code
sudo git pull

# Update backend
cd ai-core
source venv/bin/activate
pip install -e .
prisma generate

# Update frontend
cd ../client
npm install
npm run build

# Restart services
sudo systemctl restart chatbot-backend
sudo systemctl reload nginx
```

### Database Migrations

```bash
cd /var/www/chatbot

# Apply schema changes
npx prisma db push --schema=./prisma/schema.prisma

# Or create migration
npx prisma migrate dev --schema=./prisma/schema.prisma --name descriptive_name
```

### Monitor System Health

```bash
# Check backend status
curl http://localhost:8000/health

# Check database connection
cd ai-core
source venv/bin/activate
python -c "from prisma import Prisma; import asyncio; async def t(): c=Prisma(); await c.connect(); print('OK'); await c.disconnect(); asyncio.run(t())"

# Check disk space
df -h

# Check memory
free -h

# Check CPU
top
```

### Backup Database

```bash
# Full database backup
pg_dump -h ulblwebt04.lib.miamioh.edu -U username -d smartchatbot_db > backup.sql

# Backup with Prisma Studio
npx prisma studio --schema=./prisma/schema.prisma
# Export data via UI
```

---

## Troubleshooting

### Backend Won't Start

**Check:**
1. Python version: `python --version` (should be 3.13)
2. Virtual environment activated
3. `.env` file exists and has all required variables
4. Database connection: Check DATABASE_URL
5. Port 8000 not in use: `lsof -i :8000`

**Logs:**
```bash
sudo journalctl -u chatbot-backend -n 100
```

### Frontend Build Fails

**Check:**
1. Node version: `node --version` (should be 18+)
2. npm dependencies: `rm -rf node_modules && npm install`
3. Disk space: `df -h`

### Database Connection Issues

**Check:**
1. DATABASE_URL format correct
2. Database server accessible: `pg_isready -h ulblwebt04.lib.miamioh.edu`
3. Firewall rules allow connection
4. SSL mode set if required

### API Integration Failures

**Check:**
1. API keys in .env are correct
2. API endpoints accessible from server
3. OAuth tokens not expired
4. Rate limits not exceeded

**Test individual APIs:**
```bash
# Test LibCal
curl -X POST https://miamioh.libcal.com/1.1/oauth/token \
  -d "client_id=YOUR_ID&client_secret=YOUR_SECRET&grant_type=client_credentials"

# Test LibGuides
curl "https://lgapi-us.libapps.com/1.1/guides?site_id=2047&key=YOUR_KEY"
```

---

## Security Checklist

- [ ] `.env` file permissions: `chmod 600 .env`
- [ ] API keys stored securely (not in git)
- [ ] Database uses SSL connection
- [ ] Nginx configured with SSL/TLS
- [ ] Firewall rules configured (UFW or iptables)
- [ ] Backend only accessible via reverse proxy
- [ ] Regular security updates applied
- [ ] Logs rotated and managed
- [ ] Backup strategy in place

---

## Performance Tuning

### Backend Optimization

**Uvicorn Workers:**
```bash
# Run with multiple workers
uvicorn src.main:app --host 0.0.0.0 --port 8000 --workers 4
```

**Database Connection Pooling:**
Already handled by Prisma, but verify in Prisma config.

### Frontend Optimization

**Build optimization:**
- Code splitting (automatic with Vite)
- Asset compression
- CDN for static assets (if needed)

### Caching

**Nginx caching:**
```nginx
location /smartchatbot/api {
    proxy_cache my_cache;
    proxy_cache_valid 200 5m;
    # ... rest of config
}
```

---

## Next Steps

- **Database Details**: See `03-DATABASE-SETUP.md`
- **API Configuration**: See `04-API-INTEGRATIONS.md`
- **RAG Correction Pool**: See `05-WEAVIATE-RAG-CORRECTION-POOL.md`
- **Maintenance Guide**: See `06-MAINTENANCE-GUIDE.md`
- **Environment Variables**: See `07-ENVIRONMENT-VARIABLES.md`

---

**Document Version:** 3.0.0  
**Last Updated:** December 16, 2025
