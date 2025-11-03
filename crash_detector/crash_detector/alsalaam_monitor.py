import os, logging, traceback
from datetime import datetime
from pathlib import Path
import requests, smtplib
from email.message import EmailMessage
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

# Load config from environment variables
URL = os.getenv("TARGET_URL", "https://www.alsalaam.ca/")
TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "8"))
SMTP_HOST = os.getenv("SMTP_HOST")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASS = os.getenv("SMTP_PASS")
RECIPIENTS = [r.strip() for r in os.getenv("RECIPIENTS", "").split(",") if r.strip()]
SENDER = os.getenv("SENDER", SMTP_USER)
SCREENSHOT_DIR = Path(os.getenv("SCREENSHOT_DIR", "screenshots"))
SCREENSHOT_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

def check_site(url):
    try:
        r = requests.get(url, timeout=TIMEOUT)
        if r.status_code != 200:
            return False, f"HTTP {r.status_code}"
        if any(x in r.text.lower() for x in ["error", "exception", "unavailable", "not found"]):
            return False, "Page content suggests error"
        return True, "OK"
    except Exception as e:
        return False, f"Request failed: {e}"

def take_screenshot(url):
    ts = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    fname = f"crash_{ts}.png"
    path = SCREENSHOT_DIR / fname
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    try:
        driver.set_page_load_timeout(20)
        driver.get(url)
        driver.implicitly_wait(3)
        driver.save_screenshot(str(path))
        logging.info(f"Saved screenshot: {path}")
        return path
    finally:
        driver.quit()

def send_alert(reason, screenshot):
    ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    subject = f"[ALERT] alsalaam.ca crash detected"
    body = f"""
Website: {URL}
Status: {reason}
Time: {ts}

Screenshot attached.

-- Automated crash detector
"""
    msg = EmailMessage()
    msg["From"] = SENDER
    msg["To"] = ", ".join(RECIPIENTS)
    msg["Subject"] = subject
    msg.set_content(body)

    if screenshot and screenshot.exists():
        with open(screenshot, "rb") as f:
            msg.add_attachment(f.read(), maintype="image", subtype="png", filename=screenshot.name)

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as s:
            s.starttls()
            s.login(SMTP_USER, SMTP_PASS)
            s.send_message(msg)
        logging.info("Alert email sent successfully.")
    except Exception:
        logging.error("Failed to send email.")
        logging.error(traceback.format_exc())

def monitor():
    logging.info(f"Checking {URL}...")
    ok, reason = check_site(URL)
    if ok:
        logging.info(f"Site is healthy ({reason})")
    else:
        logging.warning(f"Detected crash ({reason})")
        screenshot = None
        try:
            screenshot = take_screenshot(URL)
        except Exception:
            logging.error("Screenshot capture failed.")
            logging.error(traceback.format_exc())
        send_alert(reason, screenshot)
    logging.info("Check complete.")

if __name__ == "__main__":
    monitor()