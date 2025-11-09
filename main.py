# TradingView CVD Divergence Alert Bot
# 100% Free - Detect +RD/-RD labels via screenshot + OCR
# Deploy to Railway.app free tier

import os
import time
import requests
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from PIL import Image
import pytesseract
import io

# ========== CONFIGURATION ==========
# Replace these with your values
TRADINGVIEW_CHART_URL = 'https://in.tradingview.com/chart/bXSKmqRP/'  # Your public chart URL
TELEGRAM_BOT_TOKEN = '8248626952:AAHaS6S4CPloeUJhJvWLSrG8HXT8whSs6w8'  # Your bot token from @BotFather
TELEGRAM_CHAT_ID = '1853898757'  # Your chat ID

# Settings
CHECK_INTERVAL_SECONDS = 120  # Check every 2 minutes
WAIT_FOR_CHART_LOAD = 10  # Seconds to wait for chart to load

# ========== TELEGRAM FUNCTIONS ==========
def send_telegram_message(message, image_bytes=None):
    """Send message to Telegram with optional screenshot"""
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        data = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
            "parse_mode": "Markdown"
        }
        
        response = requests.post(url, data=data)
        
        # If we have a screenshot, send it too
        if image_bytes:
            photo_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
            files = {'photo': image_bytes}
            data = {'chat_id': TELEGRAM_CHAT_ID}
            requests.post(photo_url, files=files, data=data)
        
        return response.json()
    except Exception as e:
        print(f"Error sending Telegram message: {e}")
        return None

# ========== BROWSER SETUP ==========
def setup_browser():
    """Setup headless Chrome browser for Railway deployment"""
    chrome_options = Options()
    chrome_options.add_argument('--headless')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--disable-gpu')
    chrome_options.add_argument('--window-size=1920,1080')
    chrome_options.add_argument('--disable-blink-features=AutomationControlled')
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option('useAutomationExtension', False)
    
    driver = webdriver.Chrome(options=chrome_options)
    return driver

# ========== SCREENSHOT & OCR ==========
def capture_and_analyze_chart(driver):
    """Capture chart screenshot and detect divergence labels"""
    try:
        # Navigate to chart
        driver.get(TRADINGVIEW_CHART_URL)
        
        # Wait for chart to load
        time.sleep(WAIT_FOR_CHART_LOAD)
        
        # Take screenshot
        screenshot = driver.get_screenshot_as_png()
        image = Image.open(io.BytesIO(screenshot))
        
        # Convert to grayscale for better OCR
        image = image.convert('L')
        
        # Use OCR to extract text
        text = pytesseract.image_to_string(image)
        
        print(f"[{datetime.now()}] OCR Text extracted: {text[:100]}...")
        
        # Check for divergence labels
        bullish_found = "+RD" in text or "+rd" in text.lower()
        bearish_found = "-RD" in text or "-rd" in text.lower()
        
        return {
            'bullish': bullish_found,
            'bearish': bearish_found,
            'screenshot': screenshot,
            'text': text
        }
        
    except Exception as e:
        print(f"Error capturing chart: {e}")
        return None

# ========== MAIN MONITORING LOOP ==========
def main():
    """Main monitoring loop"""
    print("=" * 50)
    print("TradingView CVD Alert Bot Started!")
    print("=" * 50)
    print(f"Chart URL: {TRADINGVIEW_CHART_URL}")
    print(f"Check interval: {CHECK_INTERVAL_SECONDS} seconds")
    print(f"Telegram Chat ID: {TELEGRAM_CHAT_ID}")
    print("=" * 50)
    
    # Send startup message
    send_telegram_message("🤖 *CVD Alert Bot Started!*\n\nMonitoring for divergence signals...")
    
    # Track last alerts to avoid spam
    last_bullish_alert = 0
    last_bearish_alert = 0
    cooldown_period = 300  # 5 minutes cooldown between same alerts
    
    # Setup browser
    driver = setup_browser()
    
    try:
        while True:
            print(f"\n[{datetime.now()}] Checking chart...")
            
            result = capture_and_analyze_chart(driver)
            
            if result:
                current_time = time.time()
                
                # Check for Bullish Divergence
                if result['bullish']:
                    if current_time - last_bullish_alert > cooldown_period:
                        message = "🟢 *BULLISH DIVERGENCE DETECTED!*\n\n"
                        message += "+RD signal found on chart\n"
                        message += f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                        
                        send_telegram_message(message, result['screenshot'])
                        last_bullish_alert = current_time
                        print("✅ Bullish divergence alert sent!")
                    else:
                        print("⏳ Bullish divergence detected but in cooldown period")
                
                # Check for Bearish Divergence
                if result['bearish']:
                    if current_time - last_bearish_alert > cooldown_period:
                        message = "🔴 *BEARISH DIVERGENCE DETECTED!*\n\n"
                        message += "-RD signal found on chart\n"
                        message += f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                        
                        send_telegram_message(message, result['screenshot'])
                        last_bearish_alert = current_time
                        print("✅ Bearish divergence alert sent!")
                    else:
                        print("⏳ Bearish divergence detected but in cooldown period")
                
                if not result['bullish'] and not result['bearish']:
                    print("📊 No divergence signals detected")
            
            # Wait before next check
            print(f"💤 Sleeping for {CHECK_INTERVAL_SECONDS} seconds...")
            time.sleep(CHECK_INTERVAL_SECONDS)
            
    except KeyboardInterrupt:
        print("\n🛑 Bot stopped by user")
        send_telegram_message("🛑 *CVD Alert Bot Stopped*")
    except Exception as e:
        error_msg = f"❌ *Error:* {str(e)}"
        print(error_msg)
        send_telegram_message(error_msg)
    finally:
        driver.quit()

if __name__ == "__main__":
    main()
```

---

## 📄 **FILE 2: requirements.txt**
```
selenium==4.15.2
pillow==10.1.0
pytesseract==0.3.10
requests==2.31.0
