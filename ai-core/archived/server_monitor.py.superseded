"""
Server Health Monitor with Auto-Restart and Email Alerts

Monitors the FastAPI server and automatically restarts it if it crashes.
Sends email alerts when errors occur.

Usage:
    python server_monitor.py
"""

import asyncio
import httpx
import smtplib
import os
import subprocess
import time
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

# Load environment
root_dir = Path(__file__).resolve().parent.parent
load_dotenv(dotenv_path=root_dir / ".env")

# Configuration
SERVER_URL = "http://localhost:8000/health"
CHECK_INTERVAL = 30  # seconds
MAX_RESTART_ATTEMPTS = 3
RESTART_COOLDOWN = 60  # seconds between restart attempts

# Email configuration
SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USERNAME = os.getenv("SMTP_USERNAME", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
ALERT_EMAIL = os.getenv("ALERT_EMAIL", "")

# Logging
LOG_FILE = Path(__file__).parent / "logs" / "server_monitor.log"
LOG_FILE.parent.mkdir(exist_ok=True)


def log(message: str):
    """Log message to file and console."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_message = f"[{timestamp}] {message}"
    print(log_message)
    
    with open(LOG_FILE, "a") as f:
        f.write(log_message + "\n")


def send_email_alert(subject: str, body: str):
    """Send email alert about server issues."""
    if not all([SMTP_USERNAME, SMTP_PASSWORD, ALERT_EMAIL]):
        log("⚠️ Email not configured - skipping alert")
        return
    
    try:
        msg = MIMEMultipart()
        msg['From'] = SMTP_USERNAME
        msg['To'] = ALERT_EMAIL
        msg['Subject'] = f"[Chatbot Server Alert] {subject}"
        
        msg.attach(MIMEText(body, 'plain'))
        
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(SMTP_USERNAME, SMTP_PASSWORD)
        server.send_message(msg)
        server.quit()
        
        log(f"📧 Email alert sent: {subject}")
    except Exception as e:
        log(f"❌ Failed to send email: {str(e)}")


async def check_server_health() -> dict:
    """Check if server is responding and healthy."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(SERVER_URL)
            
            if response.status_code == 200:
                data = response.json()
                return {
                    "healthy": True,
                    "status": data.get("status"),
                    "uptime": data.get("uptime"),
                    "memory": data.get("memory")
                }
            else:
                return {
                    "healthy": False,
                    "error": f"HTTP {response.status_code}"
                }
    except Exception as e:
        return {
            "healthy": False,
            "error": str(e)
        }


def restart_server():
    """Restart the FastAPI server."""
    log("🔄 Attempting to restart server...")
    
    try:
        # Kill existing server process
        subprocess.run(
            ["pkill", "-f", "uvicorn src.main:app"],
            check=False
        )
        time.sleep(2)
        
        # Start new server process
        log_dir = Path(__file__).parent / "logs"
        log_dir.mkdir(exist_ok=True)
        
        server_log = log_dir / "server.log"
        error_log = log_dir / "server_error.log"
        
        with open(server_log, "a") as out, open(error_log, "a") as err:
            subprocess.Popen(
                [".venv/bin/uvicorn", "src.main:app_sio", "--host", "0.0.0.0", "--port", "8000", "--reload"],
                cwd=Path(__file__).parent,
                stdout=out,
                stderr=err,
                start_new_session=True
            )
        
        log("✅ Server restart initiated")
        return True
    except Exception as e:
        log(f"❌ Failed to restart server: {str(e)}")
        return False


async def monitor_loop():
    """Main monitoring loop."""
    log("🚀 Server monitor started")
    log(f"   Checking {SERVER_URL} every {CHECK_INTERVAL} seconds")
    
    consecutive_failures = 0
    last_restart_time = 0
    restart_attempts = 0
    
    while True:
        try:
            health = await check_server_health()
            
            if health["healthy"]:
                if consecutive_failures > 0:
                    log(f"✅ Server recovered after {consecutive_failures} failures")
                    consecutive_failures = 0
                    restart_attempts = 0
                
                # Log healthy status periodically
                if int(time.time()) % 300 == 0:  # Every 5 minutes
                    log(f"✅ Server healthy - Uptime: {health.get('uptime', 'unknown')}s")
            
            else:
                consecutive_failures += 1
                error = health.get("error", "Unknown error")
                log(f"❌ Server unhealthy ({consecutive_failures} consecutive failures): {error}")
                
                # Attempt restart after 3 consecutive failures
                if consecutive_failures >= 3:
                    current_time = time.time()
                    
                    # Check cooldown period
                    if current_time - last_restart_time < RESTART_COOLDOWN:
                        log(f"⏳ Restart cooldown active - waiting...")
                    elif restart_attempts >= MAX_RESTART_ATTEMPTS:
                        log(f"🛑 Max restart attempts ({MAX_RESTART_ATTEMPTS}) reached - sending alert")
                        send_email_alert(
                            "Server Down - Manual Intervention Required",
                            f"Server has failed {consecutive_failures} health checks.\n"
                            f"Restart attempts: {restart_attempts}/{MAX_RESTART_ATTEMPTS}\n"
                            f"Last error: {error}\n\n"
                            f"Manual intervention required."
                        )
                        restart_attempts = 0  # Reset for next cycle
                        consecutive_failures = 0
                    else:
                        restart_attempts += 1
                        last_restart_time = current_time
                        
                        if restart_server():
                            log(f"⏳ Waiting 10 seconds for server to start...")
                            await asyncio.sleep(10)
                            
                            # Check if restart was successful
                            health_check = await check_server_health()
                            if health_check["healthy"]:
                                log("✅ Server restart successful")
                                send_email_alert(
                                    "Server Restarted Successfully",
                                    f"Server was down for {consecutive_failures} checks.\n"
                                    f"Automatic restart successful.\n"
                                    f"Server is now healthy."
                                )
                                consecutive_failures = 0
                                restart_attempts = 0
                            else:
                                log(f"❌ Server restart failed - attempt {restart_attempts}/{MAX_RESTART_ATTEMPTS}")
                        else:
                            log(f"❌ Failed to execute restart command")
            
            await asyncio.sleep(CHECK_INTERVAL)
            
        except KeyboardInterrupt:
            log("🛑 Monitor stopped by user")
            break
        except Exception as e:
            log(f"❌ Monitor error: {str(e)}")
            await asyncio.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    asyncio.run(monitor_loop())
