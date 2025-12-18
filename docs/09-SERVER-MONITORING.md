# Server Monitoring and Auto-Restart System

**Last Updated**: December 17, 2025  
**Version**: 1.0

---

## Overview

The server monitoring system provides:
- **Health checks** every 30 seconds
- **Automatic restart** on server failures
- **Email alerts** for critical issues
- **Comprehensive logging** with rotation

---

## Components

### 1. Server Monitor (`server_monitor.py`)

**Features**:
- Checks server health via `/health` endpoint
- Detects consecutive failures (3+ failures triggers restart)
- Automatic restart with cooldown period
- Email alerts on critical failures
- Detailed logging

**Configuration**:
```python
CHECK_INTERVAL = 30  # seconds
MAX_RESTART_ATTEMPTS = 3
RESTART_COOLDOWN = 60  # seconds
```

### 2. Logging System (`src/utils/logging_config.py`)

**Log Files**:
- `logs/app.log` - General application logs (JSON format, 10MB rotation)
- `logs/errors.log` - Error logs only (JSON format, 10MB rotation)
- `logs/agents.log` - Agent execution logs (JSON format, 10MB rotation)
- `logs/api.log` - API request logs (JSON format, 10MB rotation)
- `logs/server_monitor.log` - Monitor activity logs
- `logs/server.log` - Server stdout
- `logs/server_error.log` - Server stderr

**Features**:
- Rotating file handlers (10MB max, 5 backups)
- Structured JSON logging
- Different log levels (INFO, ERROR, DEBUG)
- Console + file output

---

## Setup

### 1. Configure Email Alerts

Add to `.env`:
```bash
# Email configuration for server alerts
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

### 2. Start Server Monitor

```bash
cd ai-core

# Start in background
nohup python server_monitor.py > logs/monitor_console.log 2>&1 &

# Or use screen/tmux
screen -S monitor
python server_monitor.py
# Ctrl+A, D to detach
```

### 3. Verify Monitoring

```bash
# Check monitor logs
tail -f logs/server_monitor.log

# Check server logs
tail -f logs/server.log
tail -f logs/server_error.log
```

---

## How It Works

### Health Check Flow

```
Every 30 seconds:
    ↓
GET /health endpoint
    ↓
Response OK?
    ├─ Yes → Reset failure counter
    └─ No → Increment failure counter
        ↓
    3+ consecutive failures?
        ├─ No → Continue monitoring
        └─ Yes → Attempt restart
            ↓
        Within cooldown period?
            ├─ Yes → Wait
            └─ No → Restart server
                ↓
            Wait 10 seconds
                ↓
            Check health again
                ├─ Healthy → Send success email
                └─ Failed → Increment restart attempts
                    ↓
                Max attempts reached?
                    ├─ No → Try again later
                    └─ Yes → Send critical alert email
```

### Auto-Restart Process

1. **Kill existing process**: `pkill -f "uvicorn src.main:app"`
2. **Wait 2 seconds**: Allow clean shutdown
3. **Start new process**: Launch uvicorn with logging
4. **Wait 10 seconds**: Allow server to initialize
5. **Verify health**: Check `/health` endpoint
6. **Send alert**: Email notification of restart status

---

## Email Alerts

### Alert Types

#### 1. Server Restarted Successfully
**Subject**: `[Chatbot Server Alert] Server Restarted Successfully`

**Body**:
```
Server was down for X checks.
Automatic restart successful.
Server is now healthy.
```

#### 2. Server Down - Manual Intervention Required
**Subject**: `[Chatbot Server Alert] Server Down - Manual Intervention Required`

**Body**:
```
Server has failed X health checks.
Restart attempts: 3/3
Last error: [error message]

Manual intervention required.
```

---

## Logging

### Log Levels

- **INFO**: Normal operations, health checks, restarts
- **WARNING**: Failures, retry attempts
- **ERROR**: Critical errors, restart failures
- **DEBUG**: Detailed debugging information

### Log Format

**JSON Structure**:
```json
{
  "timestamp": "2025-12-17T20:00:00.000Z",
  "level": "INFO",
  "logger": "api",
  "message": "Request completed successfully",
  "module": "main",
  "function": "ask_endpoint",
  "line": 123,
  "extra": {
    "conversation_id": "abc-123",
    "response_time": 3.2
  }
}
```

### Viewing Logs

**Real-time monitoring**:
```bash
# All logs
tail -f logs/app.log

# Errors only
tail -f logs/errors.log

# Agent activity
tail -f logs/agents.log

# API requests
tail -f logs/api.log

# Monitor activity
tail -f logs/server_monitor.log
```

**Search logs**:
```bash
# Find errors
grep -i "error" logs/app.log

# Find specific conversation
grep "conversation_id" logs/api.log | grep "abc-123"

# Count errors by type
grep "ERROR" logs/errors.log | cut -d'"' -f8 | sort | uniq -c
```

---

## Monitoring Dashboard

### Health Endpoint

**URL**: `GET /health`

**Response**:
```json
{
  "status": "healthy",
  "timestamp": "12/17/2025, 08:00:00 PM EST",
  "uptime": 3600.5,
  "memory": {
    "status": "healthy",
    "used": 150,
    "total": 16384
  },
  "system": {
    "platform": "darwin",
    "pythonVersion": "3.13.9",
    "cpuUsage": {"percent": 5.2}
  },
  "services": {
    "database": {"status": "healthy", "responseTime": 45},
    "openai": {"status": "healthy"},
    "weaviate": {"status": "healthy"}
  }
}
```

### Metrics to Monitor

- **Uptime**: Should be increasing
- **Memory usage**: Should be < 80% of total
- **Database response time**: Should be < 100ms
- **CPU usage**: Should be < 50%

---

## Troubleshooting

### Monitor Not Starting

**Check**:
```bash
# Verify Python environment
cd ai-core
.venv/bin/python --version

# Test monitor script
.venv/bin/python server_monitor.py
```

### Email Alerts Not Sending

**Check**:
1. SMTP credentials in `.env`
2. Gmail app password (not regular password)
3. Firewall not blocking SMTP port
4. Check monitor logs for email errors

### Server Not Restarting

**Check**:
1. Process permissions
2. Server logs for startup errors
3. Database connection
4. Port 8000 not blocked

### High Restart Frequency

**Investigate**:
1. Check `logs/errors.log` for recurring errors
2. Review `logs/server_error.log` for startup issues
3. Check database connection stability
4. Monitor memory usage

---

## Best Practices

### Production Deployment

1. **Use process manager**: systemd, supervisor, or PM2
2. **Set up log rotation**: logrotate for Linux
3. **Monitor disk space**: Logs can grow large
4. **Regular log review**: Weekly check for patterns
5. **Alert testing**: Test email alerts monthly

### Security

1. **Secure SMTP credentials**: Use app passwords, not main password
2. **Limit log retention**: Delete old logs after 30 days
3. **Protect log files**: Restrict read permissions
4. **Sanitize logs**: Don't log sensitive data

### Performance

1. **Adjust check interval**: Increase if server is stable
2. **Log rotation**: Keep max 5 backups per log file
3. **Async operations**: All I/O is non-blocking
4. **Resource limits**: Monitor memory and CPU usage

---

## Integration with Deployment

### systemd Service (Linux)

Create `/etc/systemd/system/chatbot-monitor.service`:
```ini
[Unit]
Description=Chatbot Server Monitor
After=network.target

[Service]
Type=simple
User=chatbot
WorkingDirectory=/path/to/chatbot/ai-core
ExecStart=/path/to/chatbot/ai-core/.venv/bin/python server_monitor.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl enable chatbot-monitor
sudo systemctl start chatbot-monitor
sudo systemctl status chatbot-monitor
```

### Docker Integration

Add to `docker-compose.yml`:
```yaml
services:
  monitor:
    build: .
    command: python server_monitor.py
    volumes:
      - ./logs:/app/logs
    environment:
      - SMTP_SERVER=${SMTP_SERVER}
      - SMTP_USERNAME=${SMTP_USERNAME}
      - SMTP_PASSWORD=${SMTP_PASSWORD}
      - ALERT_EMAIL=${ALERT_EMAIL}
    restart: always
```

---

## Maintenance

### Daily
- Check monitor is running
- Review critical errors

### Weekly
- Review all logs for patterns
- Check disk space usage
- Verify email alerts working

### Monthly
- Archive old logs
- Test restart functionality
- Review restart frequency
- Update alert contacts if needed

---

## Support

For issues with monitoring system:
1. Check `logs/server_monitor.log`
2. Verify email configuration
3. Test health endpoint manually
4. Review server startup logs
