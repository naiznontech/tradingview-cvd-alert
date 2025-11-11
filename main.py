# TradingView CVD Divergence Alert Bot
# Detect divergence by COLOR LINES (not OCR text)
# Check every 5 minutes - Optimized for Render free tier

import os
import time
import requests
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from PIL import Image
import numpy as np
import io
from flask import Flask
import threading
import gc

# ========== WEB SERVER ==========
app = Flask(__name__)

@app.route('/')
def home():
    return "CVD Alert Bot is running! (Color Detection Mode)"

@app.route('/health')
def health():
    return "OK", 200

def run_server():
    app.run(host='0.0.0.0', port=10000, debug=False, use_reloader=False)

# Replace these with your values

TRADINGVIEW_CHART_URL = 'https://in.tradingview.com/chart/bXSKmqRP/'  # Your public chart URL

TELEGRAM_BOT_TOKEN = '8248626952:AAHaS6S4CPloeUJhJvWLSrG8HXT8whSs6w8'  # Your bot token from @BotFather

TELEGRAM_CHAT_ID = '1853898757'  # Your chat ID



CHECK_INTERVAL_SECONDS = 300  # Check every 5 minutes
WAIT_FOR_CHART_LOAD = 20
MAX_RETRIES = 3

# Color detection thresholds
RED_THRESHOLD = 5000    # Minimum red pixels for bearish line
GREEN_THRESHOLD = 5000  # Minimum green pixels for bullish line

# ========== TELEGRAM FUNCTIONS ==========
def send_telegram_message(message, image_bytes=None):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        data = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
            "parse_mode": "Markdown"
        }
        response = requests.post(url, data=data, timeout=10)
        
        if image_bytes:
            photo_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
            files = {'photo': image_bytes}
            data = {'chat_id': TELEGRAM_CHAT_ID}
            requests.post(photo_url, files=files, data=data, timeout=30)
        
        return response.json()
    except Exception as e:
        print(f"Error sending Telegram: {e}")
        return None

# ========== BROWSER SETUP ==========
def setup_browser():
    chrome_options = Options()
    chrome_options.add_argument('--headless')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--disable-gpu')
    chrome_options.add_argument('--window-size=1920,1080')
    chrome_options.add_argument('--disable-blink-features=AutomationControlled')
    chrome_options.add_argument('--disable-extensions')
    chrome_options.add_argument('--disable-logging')
    chrome_options.add_argument('--log-level=3')
    chrome_options.add_argument('--single-process')
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option('useAutomationExtension', False)
    
    try:
        driver = webdriver.Chrome(options=chrome_options)
        driver.set_page_load_timeout(30)
        return driver
    except Exception as e:
        print(f"Error setting up browser: {e}")
        return None

# ========== COLOR DETECTION ==========
def detect_divergence_by_color(screenshot):
    """
    Detect divergence lines by color:
    - Red line = Bearish divergence (-RD)
    - Green line = Bullish divergence (+RD)
    """
    try:
        print("Processing image for color detection...")
        image = Image.open(io.BytesIO(screenshot))
        
        # Convert to RGB numpy array
        img_array = np.array(image.convert('RGB'))
        height, width, _ = img_array.shape
        
        print(f"Image size: {width}x{height}")
        
        # Focus on upper half of chart (where divergence lines are)
        upper_half = img_array[:height//2, :, :]
        
        # Detect RED color (Bearish divergence line)
        # Looking for bright red: R>200, G<100, B<100
        red_mask = (
            (upper_half[:,:,0] > 180) &  # Red channel high
            (upper_half[:,:,1] < 120) &   # Green channel low
            (upper_half[:,:,2] < 120)     # Blue channel low
        )
        red_pixels = np.sum(red_mask)
        
        # Detect GREEN color (Bullish divergence line)
        # Looking for bright green: R<100, G>200, B<100
        green_mask = (
            (upper_half[:,:,0] < 120) &   # Red channel low
            (upper_half[:,:,1] > 180) &   # Green channel high
            (upper_half[:,:,2] < 120)     # Blue channel low
        )
        green_pixels = np.sum(green_mask)
        
        print(f"Red pixels detected: {red_pixels}")
        print(f"Green pixels detected: {green_pixels}")
        
        # Determine if divergence lines exist
        bearish_found = red_pixels > RED_THRESHOLD
        bullish_found = green_pixels > GREEN_THRESHOLD
        
        if bearish_found:
            print("🔴 BEARISH DIVERGENCE LINE DETECTED!")
        if bullish_found:
            print("🟢 BULLISH DIVERGENCE LINE DETECTED!")
        
        # Clean up memory
        del image, img_array, upper_half, red_mask, green_mask
        gc.collect()
        
        return {
            'bullish': bullish_found,
            'bearish': bearish_found,
            'red_pixels': int(red_pixels),
            'green_pixels': int(green_pixels),
            'screenshot': screenshot
        }
        
    except Exception as e:
        print(f"Error in color detection: {e}")
        return None

# ========== CHART CAPTURE ==========
def capture_and_analyze_chart(driver):
    try:
        print(f"Navigating to chart...")
        driver.get(TRADINGVIEW_CHART_URL)
        
        print(f"Waiting {WAIT_FOR_CHART_LOAD}s for chart to load...")
        time.sleep(WAIT_FOR_CHART_LOAD)
        
        print("Taking screenshot...")
        screenshot = driver.get_screenshot_as_png()
        
        # Analyze screenshot for color lines
        result = detect_divergence_by_color(screenshot)
        
        return result
        
    except Exception as e:
        print(f"Error capturing chart: {e}")
        return None

# ========== MAIN LOOP ==========
def main():
    # Start web server
    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()
    print("Web server started on port 10000")
    
    print("=" * 60)
    print("TradingView CVD Alert Bot Started!")
    print("COLOR LINE DETECTION MODE")
    print("=" * 60)
    print(f"Chart URL: {TRADINGVIEW_CHART_URL}")
    print(f"Check interval: {CHECK_INTERVAL_SECONDS} seconds (5 minutes)")
    print(f"Telegram Chat ID: {TELEGRAM_CHAT_ID}")
    print(f"Detection method: Color-based (Red/Green lines)")
    print("=" * 60)
    
    # Send startup message
    startup_msg = (
        "🤖 *CVD Alert Bot Started!*\n\n"
        "✅ Detection: Color lines (Red/Green)\n"
        "⏱️ Interval: 5 minutes\n"
        "📊 Monitoring for divergence signals..."
    )
    send_telegram_message(startup_msg)
    
    last_bullish_alert = 0
    last_bearish_alert = 0
    cooldown_period = 600  # 10 minutes cooldown
    
    driver = None
    retry_count = 0
    
    try:
        while True:
            # Setup browser if needed
            if driver is None:
                print("\nSetting up browser...")
                driver = setup_browser()
                if driver is None:
                    retry_count += 1
                    if retry_count >= MAX_RETRIES:
                        error_msg = "❌ Failed to setup browser after 3 retries"
                        print(error_msg)
                        send_telegram_message(error_msg)
                        break
                    print(f"Retry {retry_count}/{MAX_RETRIES} after 60s...")
                    time.sleep(60)
                    continue
                retry_count = 0
            
            print(f"\n{'='*60}")
            print(f"[{datetime.now()}] Checking chart...")
            print(f"{'='*60}")
            
            try:
                result = capture_and_analyze_chart(driver)
                
                if result:
                    current_time = time.time()
                    
                    # Check for Bullish Divergence
                    if result['bullish']:
                        if current_time - last_bullish_alert > cooldown_period:
                            message = (
                                "🟢 *BULLISH DIVERGENCE DETECTED!*\n\n"
                                "✅ Green divergence line found\n"
                                f"📊 Green pixels: {result['green_pixels']}\n"
                                f"⏰ Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                            )
                            send_telegram_message(message, result['screenshot'])
                            last_bullish_alert = current_time
                            print("✅ Bullish alert sent to Telegram!")
                        else:
                            time_left = int((cooldown_period - (current_time - last_bullish_alert)) / 60)
                            print(f"⏳ Bullish divergence in cooldown ({time_left} min left)")
                    
                    # Check for Bearish Divergence
                    if result['bearish']:
                        if current_time - last_bearish_alert > cooldown_period:
                            message = (
                                "🔴 *BEARISH DIVERGENCE DETECTED!*\n\n"
                                "✅ Red divergence line found\n"
                                f"📊 Red pixels: {result['red_pixels']}\n"
                                f"⏰ Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                            )
                            send_telegram_message(message, result['screenshot'])
                            last_bearish_alert = current_time
                            print("✅ Bearish alert sent to Telegram!")
                        else:
                            time_left = int((cooldown_period - (current_time - last_bearish_alert)) / 60)
                            print(f"⏳ Bearish divergence in cooldown ({time_left} min left)")
                    
                    if not result['bullish'] and not result['bearish']:
                        print("📊 No divergence lines detected")
                
            except Exception as e:
                print(f"❌ Error in check loop: {e}")
                # Restart browser on error
                try:
                    if driver:
                        driver.quit()
                except:
                    pass
                driver = None
                time.sleep(30)
                continue
            
            # Clean up memory
            gc.collect()
            
            print(f"\n💤 Sleeping for {CHECK_INTERVAL_SECONDS} seconds (5 minutes)...")
            print(f"Next check at: {datetime.fromtimestamp(time.time() + CHECK_INTERVAL_SECONDS).strftime('%H:%M:%S')}")
            time.sleep(CHECK_INTERVAL_SECONDS)
            
    except KeyboardInterrupt:
        print("\n🛑 Bot stopped by user")
        send_telegram_message("🛑 CVD Alert Bot Stopped")
    except Exception as e:
        error_msg = f"❌ Fatal error: {str(e)}"
        print(error_msg)
        send_telegram_message(error_msg)
    finally:
        if driver:
            try:
                driver.quit()
            except:
                pass

if __name__ == "__main__":
    main()
