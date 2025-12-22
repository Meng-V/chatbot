# Deployment Checklist for New Environments

**Last Updated:** December 22, 2025  
**Version:** 3.1.0

---

## Table of Contents
1. [Pre-Deployment Checklist](#pre-deployment-checklist)
2. [Environment Setup](#environment-setup)
3. [Backend Deployment](#backend-deployment)
4. [Frontend Deployment](#frontend-deployment)
5. [Database Configuration](#database-configuration)
6. [API Integration Setup](#api-integration-setup)
7. [Testing & Verification](#testing-verification)
8. [Production Hardening](#production-hardening)

---

## Pre-Deployment Checklist

### Required Accounts & Access

- [ ] **OpenAI Account**
  - API key with GPT-4 access (o4-mini model)
  - Billing enabled and payment method configured
  - Rate limits appropriate for expected traffic

- [ ] **SpringShare APIs**
  - [ ] LibCal OAuth credentials (Client ID + Secret)
  - [ ] LibGuides API key and site ID
  - [ ] LibAnswers OAuth credentials
  - [ ] Access to LibCal admin for location/building IDs

- [ ] **Google Cloud Platform**
  - [ ] Custom Search Engine created
  - [ ] API key with Custom Search API enabled
  - [ ] Search engine configured to search `lib.miamioh.edu` or your domain

- [ ] **Weaviate Cloud**
  - [ ] Cluster created
  - [ ] API key generated
  - [ ] Note cluster URL

- [ ] **PostgreSQL Database**
  - [ ] Database server accessible
  - [ ] Database created
  - [ ] User credentials with full access
  - [ ] SSL connection configured (if required)

- [ ] **Server/Hosting**
  - [ ] Linux server (Ubuntu 20.04+ recommended)
  - [ ] Root or sudo access
  - [ ] Nginx or Apache installed
  - [ ] SSL certificate (Let's Encrypt or purchased)
  - [ ] Domain name configured

---

## Environment Setup

### 1. Install System Dependencies

**Ubuntu/Debian:**
```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install Python 3.13
sudo apt install software-properties-common
sudo add-apt-repository ppa:deadsnakes/ppa
sudo apt update
sudo apt install python3.13 python3.13-venv python3.13-dev

# Install Node.js 18+
curl -fsSL https://deb.nodesource.com/setup_18.x | sudo -E bash -
sudo apt install -y nodejs

# Install build tools
sudo apt install -y build-essential git nginx postgresql-client

# Verify installations
python3.13 --version  # Should show 3.13.x
node --version        # Should show 18.x or higher
npm --version
```

**macOS (Development):**
```bash
# Install Homebrew if not installed
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Install Python 3.13
brew install python@3.13

# Install Node.js
brew install node@18

# Install PostgreSQL client
brew install postgresql
```

### 2. Clone Repository

```bash
# Production
cd /var/www
sudo git clone <your-repository-url> chatbot
sudo chown -R $USER:$USER chatbot
cd chatbot

# Development
cd ~/projects
git clone <your-repository-url> chatbot
cd chatbot
```

---

## Backend Deployment

### 1. Create Python Virtual Environment

```bash
cd chatbot/ai-core

# Create virtual environment
python3.13 -m venv .venv

# Activate
source .venv/bin/activate  # macOS/Linux
# OR
.venv\Scripts\activate     # Windows

# Upgrade pip
pip install --upgrade pip
```

### 2. Install Python Dependencies

```bash
# Install all dependencies
pip install -e .

# This installs:
# - FastAPI + Uvicorn (web server)
# - LangGraph (AI orchestration)
# - Prisma (database ORM)
# - OpenAI Python SDK
# - httpx (async HTTP)
# - python-socketio
# - weaviate-client
# - All other dependencies from setup.py
```

### 3. Configure Environment Variables

```bash
# Navigate to project root
cd ..

# Copy example file
cp .env.example .env

# Edit configuration
nano .env  # or vim, code, etc.
```

**Required Variables:**
```bash
# OpenAI
OPENAI_API_KEY=sk-proj-...
OPENAI_MODEL=o4-mini

# Database
DATABASE_URL=postgresql://username:password@host:5432/database?sslmode=require

# Weaviate
WEAVIATE_URL=https://your-cluster.weaviate.network
WEAVIATE_API_KEY=your-api-key

# LibCal OAuth
LIBCAL_CLIENT_ID=your-client-id
LIBCAL_CLIENT_SECRET=your-client-secret
LIBCAL_TOKEN_URL=https://yourdomain.libcal.com/1.1/oauth/token
LIBCAL_API_BASE_URL=https://yourdomain.libcal.com/1.1

# LibCal Location IDs (get from LibCal admin)
LIBCAL_KING_LOCATION_ID=8113
LIBCAL_ART_LOCATION_ID=8116
LIBCAL_HAMILTON_LOCATION_ID=9226
LIBCAL_MIDDLETOWN_LOCATION_ID=9227

# LibCal Building IDs (get from LibCal admin)
LIBCAL_KING_BUILDING_ID=2047
LIBCAL_ART_BUILDING_ID=4089
LIBCAL_HAMILTON_BUILDING_ID=4792
LIBCAL_MIDDLETOWN_BUILDING_ID=4845

# LibGuides API
LIBGUIDES_SITE_ID=2047
LIBGUIDES_API_KEY=your-api-key
LIBGUIDES_API_URL=https://lgapi-us.libapps.com/1.1

# LibAnswers OAuth
LIBANSWERS_IID=2047
LIBANSWERS_CLIENT_ID=your-client-id
LIBANSWERS_CLIENT_SECRET=your-client-secret

# Google Custom Search
GOOGLE_CSE_API_KEY=your-api-key
GOOGLE_CSE_CX=your-search-engine-id

# CORS (adjust for your domain)
CORS_ORIGINS=["http://localhost:5173","https://your-domain.edu"]
```

**Security:**
```bash
# Set proper permissions
chmod 600 .env
```

### 4. Initialize Database

```bash
# Generate Prisma client
cd ai-core
prisma generate

# Push schema to database
cd ..
npx prisma db push --schema=./prisma/schema.prisma

# Seed library locations
cd ai-core
source .venv/bin/activate
python -m scripts.seed_library_locations
```

### 5. Set Up Weaviate Collections

```bash
# Load classification examples
python -m scripts.setup_weaviate

# This creates:
# - QuestionCategory collection (for RAG classification)
# - Loads category examples from category_examples.py
```

### 6. Test Backend

```bash
# Run backend
cd ai-core
source .venv/bin/activate
uvicorn src.main:app_sio --host 0.0.0.0 --port 8000 --reload

# In another terminal, test health endpoint
curl http://localhost:8000/health

# Expected response:
# {"status":"healthy","database":"connected","weaviate":"connected"}
```

---

## Frontend Deployment

### 1. Install Dependencies

```bash
cd chatbot/client

# Install npm packages
npm install

# This installs:
# - React 19
# - Vite 7
# - TailwindCSS 4
# - Radix UI components
# - Socket.IO client
# - All other dependencies from package.json
```

### 2. Configure Frontend

**Update `client/src/config.js`** (if needed):
```javascript
export const API_URL = import.meta.env.PROD 
  ? 'https://your-domain.edu/smartchatbot/api'
  : 'http://localhost:8000';

export const SOCKET_URL = import.meta.env.PROD
  ? 'https://your-domain.edu'
  : 'http://localhost:8000';

export const SOCKET_PATH = '/smartchatbot/socket.io';
```

### 3. Build Frontend

```bash
# Development (with hot reload)
npm run dev

# Production build
npm run build

# Built files will be in dist/ folder
ls -la dist/
```

### 4. Test Frontend (Development)

```bash
# Start dev server
npm run dev

# Visit http://localhost:5173
# Should see chatbot interface
# Test: "What time does the library close?"
```

---

## Database Configuration

### 1. Verify Database Connection

```bash
# Test connection
psql "postgresql://username:password@host:5432/database?sslmode=require"

# List tables
\dt

# Expected tables:
# - Conversation
# - Message
# - ToolExecution
# - Campus
# - Library
# - LibrarySpace
# - Subject
# - SubjectLibGuide
# - SubjectMajorCode
# - SubjectRegCode
# - SubjectDeptCode
```

### 2. Seed Library Data

**Edit `ai-core/scripts/seed_library_locations.py`** with your library information:

```python
# Update with your campuses
campuses = [
    {"name": "main", "displayName": "Main Campus", "isMain": True},
    {"name": "branch", "displayName": "Branch Campus", "isMain": False},
]

# Update with your libraries
libraries = [
    {
        "campusName": "main",
        "name": "Main Library",
        "displayName": "Main University Library",
        "shortName": "main",
        "libcalBuildingId": "YOUR_BUILDING_ID",
        "libcalLocationId": "YOUR_LOCATION_ID",
        "phone": "(XXX) XXX-XXXX",
        "address": "123 Main St, City, ST 12345",
        "website": "https://library.yourdomain.edu",
        "isMain": True
    },
]
```

Then run:
```bash
python -m scripts.seed_library_locations
```

### 3. Load Subject-Librarian Mappings

If you have MuGuide API or similar:
```bash
# Contact development team for data import scripts
# OR manually add to database via Prisma Studio

npx prisma studio --schema=./prisma/schema.prisma
```

---

## API Integration Setup

### 1. LibCal Configuration

**Get OAuth Credentials:**
1. Log in to LibCal admin panel
2. Navigate to System Settings → API
3. Create new OAuth application
4. Copy Client ID and Client Secret
5. Set Token URL: `https://yourdomain.libcal.com/1.1/oauth/token`

**Get Location/Building IDs:**
1. In LibCal admin, go to Hours
2. Note Location IDs for each library
3. Go to Spaces, note Building IDs
4. Add to `.env` file

**Test LibCal:**
```bash
cd ai-core
source .venv/bin/activate
python

>>> from src.api.libcal import get_oauth_token
>>> import asyncio
>>> asyncio.run(get_oauth_token())
# Should return access token
```

### 2. LibGuides Configuration

**Get API Key:**
1. Log in to LibGuides admin
2. Navigate to Admin → API
3. Generate API key
4. Note your Site ID
5. Add to `.env`

**Test LibGuides:**
```bash
python

>>> from src.api.libguides import search_guides
>>> import asyncio
>>> asyncio.run(search_guides("biology"))
# Should return list of guides
```

### 3. Google Custom Search

**Create Search Engine:**
1. Go to https://programmablesearchengine.google.com/
2. Click "Add"
3. Sites to search: `library.yourdomain.edu/*`
4. Create and copy Search Engine ID (CX)

**Get API Key:**
1. Go to Google Cloud Console
2. Enable Custom Search API
3. Create credentials (API key)
4. Add to `.env`

**Test Google Search:**
```bash
python

>>> from src.api.google_cse import search_library_website
>>> import asyncio
>>> asyncio.run(search_library_website("borrowing policies"))
# Should return search results
```

### 4. Weaviate Setup

**Create Cluster:**
1. Sign up at https://console.weaviate.cloud
2. Create new cluster (free tier available)
3. Copy cluster URL and API key
4. Add to `.env`

**Load Data:**
```bash
cd ai-core
source .venv/bin/activate
python -m scripts.setup_weaviate
```

---

## Testing & Verification

### 1. Backend Health Check

```bash
curl http://localhost:8000/health

# Expected:
{
  "status": "healthy",
  "database": "connected",
  "weaviate": "connected",
  "timestamp": "2025-12-22T14:00:00Z"
}
```

### 2. Test Queries

```bash
# Simple hours query
curl -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"message":"What time does the library close?"}'

# Subject librarian query
curl -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"message":"Who is the biology librarian?"}'

# Clarification test
curl -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"message":"I need help with a computer"}'
# Should return clarification choices
```

### 3. Frontend Integration Test

1. Start backend: `uvicorn src.main:app_sio --port 8000`
2. Start frontend: `npm run dev`
3. Visit http://localhost:5173
4. Test conversations:
   - "What time does the library close?"
   - "I need help with a computer" (should show buttons)
   - "Who is the biology librarian?"
   - "Talk to a librarian"

### 4. Socket.IO Test

```javascript
// In browser console on localhost:5173
socket.emit('message', 'What time does the library close?');

// Should see response in chat
```

---

## Production Hardening

### 1. Create Systemd Service

**Create `/etc/systemd/system/chatbot-backend.service`:**
```ini
[Unit]
Description=Library Chatbot Backend
After=network.target postgresql.service

[Service]
Type=simple
User=www-data
WorkingDirectory=/var/www/chatbot/ai-core
Environment="PATH=/var/www/chatbot/ai-core/.venv/bin"
ExecStart=/var/www/chatbot/ai-core/.venv/bin/uvicorn src.main:app_sio --host 0.0.0.0 --port 8000
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

**Enable and start:**
```bash
sudo systemctl daemon-reload
sudo systemctl enable chatbot-backend
sudo systemctl start chatbot-backend
sudo systemctl status chatbot-backend
```

### 2. Configure Nginx

**Create `/etc/nginx/sites-available/chatbot`:**
```nginx
server {
    listen 80;
    server_name library.yourdomain.edu;
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name library.yourdomain.edu;

    ssl_certificate /etc/letsencrypt/live/library.yourdomain.edu/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/library.yourdomain.edu/privkey.pem;

    # Frontend
    location /smartchatbot {
        alias /var/www/chatbot/client/dist;
        try_files $uri $uri/ /smartchatbot/index.html;
        
        # Cache static assets
        location ~* \.(js|css|png|jpg|jpeg|gif|ico|svg|woff|woff2)$ {
            expires 1y;
            add_header Cache-Control "public, immutable";
        }
    }

    # Backend API
    location /smartchatbot/api {
        proxy_pass http://localhost:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_cache_bypass $http_upgrade;
    }

    # WebSocket
    location /smartchatbot/socket.io {
        proxy_pass http://localhost:8000/socket.io;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "Upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_read_timeout 86400;
    }
}
```

**Enable site:**
```bash
sudo ln -s /etc/nginx/sites-available/chatbot /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

### 3. SSL Certificate

```bash
# Install certbot
sudo apt install certbot python3-certbot-nginx

# Get certificate
sudo certbot --nginx -d library.yourdomain.edu

# Auto-renewal
sudo systemctl enable certbot.timer
```

### 4. Firewall Configuration

```bash
# Install UFW
sudo apt install ufw

# Configure rules
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow ssh
sudo ufw allow 'Nginx Full'

# Enable
sudo ufw enable
sudo ufw status
```

### 5. Log Rotation

**Create `/etc/logrotate.d/chatbot`:**
```
/var/log/chatbot/*.log {
    daily
    rotate 14
    compress
    delaycompress
    missingok
    notifempty
    create 0644 www-data www-data
}
```

### 6. Monitoring

**Create health check script `/usr/local/bin/check-chatbot.sh`:**
```bash
#!/bin/bash
HEALTH_URL="http://localhost:8000/health"
RESPONSE=$(curl -s -o /dev/null -w "%{http_code}" $HEALTH_URL)

if [ $RESPONSE -ne 200 ]; then
    echo "Chatbot health check failed (HTTP $RESPONSE)"
    systemctl restart chatbot-backend
    # Optional: send email alert
fi
```

**Add to crontab:**
```bash
sudo chmod +x /usr/local/bin/check-chatbot.sh
sudo crontab -e

# Add line:
*/5 * * * * /usr/local/bin/check-chatbot.sh
```

---

## Post-Deployment Verification

### Checklist

- [ ] Backend health endpoint returns 200
- [ ] Database connection working
- [ ] Weaviate connection working
- [ ] All API integrations tested
- [ ] Frontend loads correctly
- [ ] Socket.IO connection established
- [ ] Test conversations work end-to-end
- [ ] Clarification buttons appear for ambiguous questions
- [ ] SSL certificate valid
- [ ] Logs writing correctly
- [ ] Systemd service starts on boot
- [ ] Nginx proxying correctly
- [ ] Firewall rules active

### Performance Benchmarks

Test with realistic queries:
- Simple query: < 2 seconds
- Complex query: 3-5 seconds
- Clarification flow: 1-2 seconds + user interaction time
- Database queries: < 100ms
- External API calls: 500ms - 2 seconds

---

## Troubleshooting Common Issues

### Backend Won't Start

**Check:**
```bash
# Logs
sudo journalctl -u chatbot-backend -n 100 -f

# Python version
python3.13 --version

# Virtual environment
which python  # Should show .venv path

# Dependencies
pip list | grep fastapi
```

### Database Connection Fails

**Check:**
```bash
# Connection string
echo $DATABASE_URL

# Test connection
psql "$DATABASE_URL"

# Firewall
sudo ufw status
```

### Weaviate Connection Fails

**Check:**
```bash
# Environment variables
echo $WEAVIATE_URL
echo $WEAVIATE_API_KEY

# Test connection
curl -H "Authorization: Bearer $WEAVIATE_API_KEY" "$WEAVIATE_URL/v1/schema"
```

### Frontend Build Fails

**Check:**
```bash
# Node version
node --version  # Should be 18+

# Clear cache
rm -rf node_modules package-lock.json
npm install

# Disk space
df -h
```

---

## Maintenance Procedures

### Regular Updates

```bash
# Weekly
cd /var/www/chatbot
sudo git pull
cd ai-core
source .venv/bin/activate
pip install -e .
prisma generate
sudo systemctl restart chatbot-backend

cd ../client
npm install
npm run build
sudo systemctl reload nginx
```

### Database Backups

```bash
# Daily backup script
pg_dump "$DATABASE_URL" > backup-$(date +%Y%m%d).sql
```

### Monitor Logs

```bash
# View logs
sudo journalctl -u chatbot-backend -f

# Nginx logs
sudo tail -f /var/log/nginx/access.log
sudo tail -f /var/log/nginx/error.log
```

---

## Support & Resources

**Documentation:**
- [System Overview](./01-SYSTEM-OVERVIEW.md)
- [Setup Guide](./02-SETUP-AND-DEPLOYMENT.md)
- [Clarification System](./11-CLARIFICATION-SYSTEM.md)
- [Environment Variables](./07-ENVIRONMENT-VARIABLES.md)

**Community:**
- GitHub Issues (if open source)
- Development team contact
- Library IT support

---

**Document Version:** 3.1.0  
**Last Updated:** December 22, 2025  
**Status:** Production Ready ✅
