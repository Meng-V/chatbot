# Quick Start - Library Chatbot Deployment

**For Backend Managers and System Administrators**  
**Version:** 3.1.0  
**Last Updated:** December 22, 2025

---

## 🚀 Deploy in 30 Minutes

This guide helps you quickly deploy the Miami University Libraries Chatbot on a Linux server with Nginx.

---

## Prerequisites Checklist

**Before you begin, ensure you have:**

- [ ] Linux server (Ubuntu 20.04+ recommended) with sudo access
- [ ] Nginx installed
- [ ] Domain name configured (e.g., `library.yourdomain.edu`)
- [ ] PostgreSQL database accessible (can be remote)
- [ ] OpenAI API key with GPT-4 access
- [ ] SpringShare API credentials (LibCal, LibGuides, LibAnswers)
- [ ] Google Custom Search API key
- [ ] Weaviate Cloud cluster and API key

---

## Step 1: Install System Dependencies (5 minutes)

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install Python 3.13 (REQUIRED - Prisma does not support 3.14+)
sudo apt install software-properties-common
sudo add-apt-repository ppa:deadsnakes/ppa
sudo apt update
sudo apt install python3.13 python3.13-venv python3.13-dev

# Install Node.js 18+
curl -fsSL https://deb.nodesource.com/setup_18.x | sudo -E bash -
sudo apt install -y nodejs

# Install build tools
sudo apt install -y build-essential git postgresql-client

# Verify installations
python3.13 --version  # Must show 3.13.x
node --version        # Must show 18.x or higher
```

---

## Step 2: Clone and Setup Repository (5 minutes)

```bash
# Clone to /var/www
cd /var/www
sudo git clone <your-repository-url> chatbot
sudo chown -R $USER:$USER chatbot
cd chatbot

# Create .env file
cp .env.example .env
nano .env  # Edit with your API keys (see below)
```

### Configure .env File

**Minimum required variables:**

```bash
# OpenAI
OPENAI_API_KEY=sk-proj-your-key-here
OPENAI_MODEL=o4-mini

# Database
DATABASE_URL=postgresql://user:password@host:5432/database?sslmode=require

# Weaviate
WEAVIATE_URL=https://your-cluster.weaviate.network
WEAVIATE_API_KEY=your-weaviate-api-key

# LibCal OAuth
LIBCAL_CLIENT_ID=your-client-id
LIBCAL_CLIENT_SECRET=your-client-secret
LIBCAL_TOKEN_URL=https://yourdomain.libcal.com/1.1/oauth/token
LIBCAL_API_BASE_URL=https://yourdomain.libcal.com/1.1

# LibCal IDs (get from LibCal admin)
LIBCAL_KING_LOCATION_ID=8113
LIBCAL_KING_BUILDING_ID=2047

# LibGuides
LIBGUIDES_SITE_ID=2047
LIBGUIDES_API_KEY=your-api-key
LIBGUIDES_API_URL=https://lgapi-us.libapps.com/1.1

# LibAnswers
LIBANSWERS_IID=2047
LIBANSWERS_CLIENT_ID=your-client-id
LIBANSWERS_CLIENT_SECRET=your-client-secret

# Google
GOOGLE_CSE_API_KEY=your-google-api-key
GOOGLE_CSE_CX=your-search-engine-id

# Production URLs
FRONTEND_URL=https://library.yourdomain.edu
```

**Save and set permissions:**
```bash
chmod 600 .env
```

---

## Step 3: Setup Backend (5 minutes)

```bash
cd /var/www/chatbot/ai-core

# Create virtual environment
python3.13 -m venv .venv

# Activate
source .venv/bin/activate

# Install dependencies
pip install --upgrade pip
pip install -e .

# Generate Prisma client
prisma generate

# Test backend
uvicorn src.main:app_sio --host 0.0.0.0 --port 8000

# In another terminal, test:
curl http://localhost:8000/health
# Should return: {"status":"healthy"}

# Stop with Ctrl+C
```

---

## Step 4: Initialize Database (3 minutes)

```bash
cd /var/www/chatbot

# Push database schema
npx prisma db push --schema=./prisma/schema.prisma

# Seed library locations
cd ai-core
source .venv/bin/activate
python -m scripts.seed_library_locations

# Setup Weaviate (RAG classification)
python -m scripts.setup_weaviate
```

---

## Step 5: Setup Frontend (3 minutes)

```bash
cd /var/www/chatbot/client

# Install dependencies
npm install

# Build for production
npm run build

# Verify build
ls -la dist/
# Should see index.html, assets/, etc.
```

---

## Step 6: Create Systemd Service (2 minutes)

**Create `/etc/systemd/system/chatbot-backend.service`:**

```bash
sudo nano /etc/systemd/system/chatbot-backend.service
```

**Paste this configuration:**

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

---

## Step 7: Configure Nginx (5 minutes)

**Create `/etc/nginx/sites-available/chatbot`:**

```bash
sudo nano /etc/nginx/sites-available/chatbot
```

**Paste this configuration:**

```nginx
server {
    listen 80;
    server_name library.yourdomain.edu;
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name library.yourdomain.edu;

    # SSL certificates (update paths)
    ssl_certificate /etc/letsencrypt/live/library.yourdomain.edu/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/library.yourdomain.edu/privkey.pem;

    # Frontend (React app)
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

    # WebSocket for Socket.IO
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
sudo nginx -t  # Test configuration
sudo systemctl reload nginx
```

---

## Step 8: SSL Certificate (2 minutes)

```bash
# Install certbot
sudo apt install certbot python3-certbot-nginx

# Get certificate
sudo certbot --nginx -d library.yourdomain.edu

# Test auto-renewal
sudo certbot renew --dry-run
```

---

## Step 9: Verify Deployment (3 minutes)

### Backend Health Check

```bash
curl http://localhost:8000/health
```

**Expected response:**
```json
{
  "status": "healthy",
  "database": "connected",
  "weaviate": "connected",
  "timestamp": "2025-12-22T19:00:00Z"
}
```

### Test Query

```bash
curl -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"message":"What time does the library close?"}'
```

### Visit Frontend

Open browser: `https://library.yourdomain.edu/smartchatbot`

**Test these questions:**
1. "What time does the library close?"
2. "I need help with a computer" (should show clarification buttons)
3. "Who is the biology librarian?"
4. "Book a study room"

---

## Troubleshooting

### Backend Won't Start

```bash
# Check logs
sudo journalctl -u chatbot-backend -n 50 -f

# Common issues:
# 1. Python version: python3.13 --version
# 2. Virtual environment: which python (should show .venv)
# 3. Port in use: sudo lsof -i :8000
# 4. Database connection: check DATABASE_URL in .env
```

### Frontend Not Loading

```bash
# Check Nginx logs
sudo tail -f /var/log/nginx/error.log

# Common issues:
# 1. Build not created: ls /var/www/chatbot/client/dist/
# 2. Nginx config: sudo nginx -t
# 3. Permissions: sudo chown -R www-data:www-data /var/www/chatbot/client/dist
```

### Database Connection Fails

```bash
# Test connection
psql "postgresql://user:password@host:5432/database?sslmode=require"

# Common issues:
# 1. Firewall blocking: sudo ufw status
# 2. SSL mode: add ?sslmode=require to DATABASE_URL
# 3. Wrong credentials: check .env file
```

### Weaviate Connection Fails

```bash
# Test Weaviate
curl -H "Authorization: Bearer $WEAVIATE_API_KEY" \
  "$WEAVIATE_URL/v1/schema"

# Common issues:
# 1. Wrong URL format: must be https://cluster-name.weaviate.network
# 2. API key expired: regenerate in Weaviate console
```

---

## Maintenance

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
# Restart backend
sudo systemctl restart chatbot-backend

# Reload Nginx
sudo systemctl reload nginx
```

### Update Application

```bash
cd /var/www/chatbot

# Pull latest code
sudo git pull

# Update backend
cd ai-core
source .venv/bin/activate
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

---

## Security Checklist

- [ ] `.env` file permissions: `chmod 600 .env`
- [ ] API keys not in git: `.env` in `.gitignore`
- [ ] Database uses SSL: `?sslmode=require` in DATABASE_URL
- [ ] SSL/TLS enabled: HTTPS configured with valid certificate
- [ ] Firewall configured: `sudo ufw enable`
- [ ] Backend only accessible via Nginx: Port 8000 blocked externally
- [ ] Regular updates: `sudo apt update && sudo apt upgrade`

---

## Performance Benchmarks

After deployment, verify these response times:

- **Simple queries** (hours, contact): < 2 seconds
- **Complex queries** (multi-agent): 3-5 seconds  
- **Clarification flow**: 1-2 seconds + user interaction
- **Database queries**: < 100ms
- **Health check**: < 50ms

---

## Next Steps

**For detailed documentation:**
- `/docs/01-SYSTEM-OVERVIEW.md` - Architecture and components
- `/docs/02-SETUP-AND-DEPLOYMENT.md` - Comprehensive setup guide
- `/docs/12-DEPLOYMENT-CHECKLIST.md` - Complete deployment checklist
- `/docs/07-ENVIRONMENT-VARIABLES.md` - All configuration options

**For project management:**
- `BOT_WORKFLOW.md` - Detailed workflow and decision-making process
- `README.md` - Non-technical overview for administrators

---

## Support

**Technical Issues:**  
- Check logs: `sudo journalctl -u chatbot-backend -f`
- Review documentation in `/docs/`
- Contact development team

**Questions:**  
- System architecture: See `/docs/01-SYSTEM-OVERVIEW.md`
- API configuration: See `/docs/04-API-INTEGRATIONS.md`  
- Database issues: See `/docs/03-DATABASE-SETUP.md`

---

**Quick Start Version:** 3.1.0  
**Last Updated:** December 22, 2025  
**Deployment Time:** ~30 minutes  
**Difficulty:** Intermediate

✅ **You're done!** The chatbot should now be live at `https://library.yourdomain.edu/smartchatbot`
