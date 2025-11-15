import os
import time
import requests
from datetime import datetime
import pandas as pd
import numpy as np
from flask import Flask
import threading
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from PIL import Image
import io

app = Flask(__name__)

@app.route('/')
def home():
    return "CVD Alert Bot is running! (Hybrid Mode)"

@app.route('/health')
def health():
    return "OK", 200

def run_server():
    app.run(host='0.0.0.0', port=10000, debug=False, use_reloader=False)

# ========== CONFIGURATION ==========

TELEGRAM_BOT_TOKEN = '8248626952:AAHaS6S4CPloeUJhJvWLSrG8HXT8whSs6w8'  # Your bot token from @BotFather

TELEGRAM_CHAT_ID = '1853898757'  # Your chat ID
TRADINGVIEW_CHART_URL = ""
EXCHANGE = "OKX"
SYMBOL = "BTC-USDT-SWAP"
TIMEFRAME = "15m"
CVD_PERIOD = 20
FRACTAL_PERIOD = 5
DIVERGENCE_LOOKBACK = 30
CHECK_INTERVAL_SECONDS = 300
USE_TRADINGVIEW = False

def send_telegram_message(message, image_bytes=None):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        data = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}
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

def setup_browser():
    chrome_options = Options()
    chrome_options.add_argument('--headless')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--disable-gpu')
    chrome_options.add_argument('--window-size=1920,1080')
    chrome_options.add_argument('--single-process')
    try:
        driver = webdriver.Chrome(options=chrome_options)
        driver.set_page_load_timeout(30)
        return driver
    except Exception as e:
        print(f"Error setting up browser: {e}")
        return None

def screenshot_tradingview(driver):
    try:
        print(f"📸 Taking screenshot from TradingView...")
        driver.get(TRADINGVIEW_CHART_URL)
        time.sleep(15)
        screenshot = driver.get_screenshot_as_png()
        image = Image.open(io.BytesIO(screenshot))
        img_array = np.array(image.convert('RGB'))
        height, width, _ = img_array.shape
        chart_area = img_array[:int(height*0.6), :, :]
        red_mask = (chart_area[:,:,0] > 200) & (chart_area[:,:,1] < 80) & (chart_area[:,:,2] < 80)
        red_pixels = np.sum(red_mask)
        green_mask = (chart_area[:,:,0] < 80) & (chart_area[:,:,1] > 200) & (chart_area[:,:,2] < 80)
        green_pixels = np.sum(green_mask)
        print(f"Red pixels: {red_pixels}, Green pixels: {green_pixels}")
        bearish_found = red_pixels > 8000
        bullish_found = green_pixels > 8000
        if len(screenshot) > 4000000:
            image.thumbnail((1280, 720), Image.Resampling.LANCZOS)
            buffer = io.BytesIO()
            image.save(buffer, format='PNG', optimize=True)
            screenshot = buffer.getvalue()
        return {'bullish': bullish_found, 'bearish': bearish_found, 'screenshot': screenshot}
    except Exception as e:
        print(f"Error screenshot TradingView: {e}")
        return None

def get_klines(exchange, symbol, interval, limit=200):
    try:
        if exchange == "BINANCE":
            url = "https://api.binance.com/api/v3/klines"
            params = {"symbol": symbol, "interval": interval, "limit": limit}
            response = requests.get(url, params=params, timeout=10)
            if response.status_code != 200:
                print(f"Binance API returned status {response.status_code}")
                return None
            data = response.json()
            df = pd.DataFrame(data, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'close_time', 'quote_volume', 'trades', 'taker_buy_base', 'taker_buy_quote', 'ignore'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        elif exchange == "OKX":
            bar_mapping = {"1m": "1m", "5m": "5m", "15m": "15m", "1h": "1H", "4h": "4H", "1d": "1D"}
            bar = bar_mapping.get(interval, "15m")
            url = "https://www.okx.com/api/v5/market/candles"
            params = {"instId": symbol, "bar": bar, "limit": limit}
            response = requests.get(url, params=params, timeout=10)
            if response.status_code != 200:
                print(f"OKX API returned status {response.status_code}")
                return None
            result = response.json()
            if result.get('code') != '0':
                print(f"OKX API error: {result.get('msg')}")
                return None
            data = result['data']
            df = pd.DataFrame(data, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'volCcy', 'volCcyQuote', 'confirm'])
            df['timestamp'] = pd.to_datetime(pd.to_numeric(df['timestamp']), unit='ms')
            df = df.sort_values('timestamp').reset_index(drop=True)
        else:
            print(f"Unknown exchange: {exchange}")
            return None
        df['open'] = pd.to_numeric(df['open'])
        df['high'] = pd.to_numeric(df['high'])
        df['low'] = pd.to_numeric(df['low'])
        df['close'] = pd.to_numeric(df['close'])
        df['volume'] = pd.to_numeric(df['volume'])
        return df
    except Exception as e:
        print(f"Error fetching data from {exchange}: {e}")
        return None

def calculate_cvd(df, period=21):
    df['buying'] = df['volume'] * ((df['close'] - df['low']) / (df['high'] - df['low']))
    df['selling'] = df['volume'] * ((df['high'] - df['close']) / (df['high'] - df['low']))
    df['buying'] = df['buying'].fillna(0)
    df['selling'] = df['selling'].fillna(0)
    df['delta'] = df['buying'] - df['selling']
    df['cvd'] = df['delta'].rolling(window=period).sum()
    return df

def calculate_ema(series, period):
    return series.ewm(span=period, adjust=False).mean()

def find_divergence(df, cvd_period=21, fractal_period=5, lookback=30):
    if len(df) < lookback + 10:
        return None, None
    df['ema50'] = calculate_ema(df['close'], 50)
    recent_data = df.tail(lookback).copy()
    bearish_div = None
    try:
        price_highs_idx = []
        for i in range(fractal_period, len(recent_data) - fractal_period):
            idx = recent_data.index[i]
            is_pivot_high = True
            for j in range(1, fractal_period + 1):
                if recent_data.iloc[i]['high'] <= recent_data.iloc[i-j]['high'] or recent_data.iloc[i]['high'] <= recent_data.iloc[i+j]['high']:
                    is_pivot_high = False
                    break
            if is_pivot_high and recent_data.iloc[i]['close'] > recent_data.iloc[i]['ema50']:
                price_highs_idx.append(idx)
        if len(price_highs_idx) >= 2:
            high1_idx = price_highs_idx[-1]
            high2_idx = price_highs_idx[-2]
            price1 = df.loc[high1_idx, 'high']
            price2 = df.loc[high2_idx, 'high']
            cvd1 = df.loc[high1_idx, 'cvd']
            cvd2 = df.loc[high2_idx, 'cvd']
            if price1 > price2 and cvd1 < cvd2 and cvd1 > 0 and cvd2 > 0:
                bearish_div = {'type': 'bearish', 'price1': price1, 'price2': price2, 'cvd1': cvd1, 'cvd2': cvd2, 'time': df.loc[high1_idx, 'timestamp']}
    except Exception as e:
        print(f"Error detecting bearish divergence: {e}")
    bullish_div = None
    try:
        price_lows_idx = []
        for i in range(fractal_period, len(recent_data) - fractal_period):
            idx = recent_data.index[i]
            is_pivot_low = True
            for j in range(1, fractal_period + 1):
                if recent_data.iloc[i]['low'] >= recent_data.iloc[i-j]['low'] or recent_data.iloc[i]['low'] >= recent_data.iloc[i+j]['low']:
                    is_pivot_low = False
                    break
            if is_pivot_low and recent_data.iloc[i]['close'] < recent_data.iloc[i]['ema50']:
                price_lows_idx.append(idx)
        if len(price_lows_idx) >= 2:
            low1_idx = price_lows_idx[-1]
            low2_idx = price_lows_idx[-2]
            price1 = df.loc[low1_idx, 'low']
            price2 = df.loc[low2_idx, 'low']
            cvd1 = df.loc[low1_idx, 'cvd']
            cvd2 = df.loc[low2_idx, 'cvd']
            if price1 < price2 and cvd1 > cvd2 and cvd1 < 0 and cvd2 < 0:
                bullish_div = {'type': 'bullish', 'price1': price1, 'price2': price2, 'cvd1': cvd1, 'cvd2': cvd2, 'time': df.loc[low1_idx, 'timestamp']}
    except Exception as e:
        print(f"Error detecting bullish divergence: {e}")
    return bullish_div, bearish_div

def main():
    global USE_TRADINGVIEW, TRADINGVIEW_CHART_URL
    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()
    print("Web server started on port 10000")
    print("=" * 70)
    print("CVD Alert Bot Started - HYBRID MODE")
    print("=" * 70)
    print(f"Exchange: {EXCHANGE}")
    print(f"Symbol: {SYMBOL}")
    print(f"Timeframe: {TIMEFRAME}")
    print(f"CVD Period: {CVD_PERIOD}")
    print(f"Fractal Period: {FRACTAL_PERIOD}")
    print(f"Check interval: {CHECK_INTERVAL_SECONDS} seconds")
    print("=" * 70)
    startup_msg = f"🤖 *CVD Alert Bot Started!*\n\n📊 Exchange: {EXCHANGE}\n💱 Symbol: {SYMBOL}\n⏱️ Timeframe: {TIMEFRAME}\n🔢 CVD Period: {CVD_PERIOD}\n🔍 Fractal Period: {FRACTAL_PERIOD}\n⏰ Check: Every 5 minutes\n\n✅ Using {EXCHANGE} API\n📈 Monitoring for divergence signals..."
    send_telegram_message(startup_msg)
    last_bullish_alert = 0
    last_bearish_alert = 0
    cooldown_period = 3600
    driver = None
    consecutive_failures = 0
    try:
        while True:
            print(f"\n{'='*70}")
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Checking {SYMBOL}...")
            print(f"{'='*70}")
            try:
                if USE_TRADINGVIEW and TRADINGVIEW_CHART_URL:
                    if driver is None:
                        driver = setup_browser()
                    if driver:
                        result = screenshot_tradingview(driver)
                        if result:
                            consecutive_failures = 0
                        else:
                            consecutive_failures += 1
                            print(f"⚠️ TradingView screenshot failed ({consecutive_failures}/3)")
                else:
                    print(f"📥 Fetching data from {EXCHANGE}...")
                    df = get_klines(EXCHANGE, SYMBOL, TIMEFRAME, limit=200)
                    if df is None or len(df) < 50:
                        consecutive_failures += 1
                        print(f"❌ Failed to fetch data ({consecutive_failures}/3)")
                        if consecutive_failures >= 3:
                            error_msg = "⚠️ Failed to fetch data 3 times in a row. Will retry..."
                            print(error_msg)
                            time.sleep(300)
                            consecutive_failures = 0
                        else:
                            time.sleep(60)
                        continue
                    consecutive_failures = 0
                    print(f"📊 Calculating CVD...")
                    df = calculate_cvd(df, period=CVD_PERIOD)
                    latest = df.iloc[-1]
                    current_price = latest['close']
                    current_cvd = latest['cvd']
                    print(f"💰 Current Price: ${current_price:.2f}")
                    print(f"📈 Current CVD: {current_cvd:.2f}")
                    print(f"🔍 Checking for divergence (Fractal Period: {FRACTAL_PERIOD})...")
                    bullish_div, bearish_div = find_divergence(df, cvd_period=CVD_PERIOD, fractal_period=FRACTAL_PERIOD, lookback=DIVERGENCE_LOOKBACK)
                    result = {'bullish': bullish_div is not None, 'bearish': bearish_div is not None, 'screenshot': None}
                current_time = time.time()
                if result and result.get('bullish'):
                    if current_time - last_bullish_alert > cooldown_period:
                        print(f"🟢 BULLISH DIVERGENCE DETECTED!")
                        message = f"🟢 *BULLISH DIVERGENCE DETECTED!*\n\n📊 Symbol: {SYMBOL}\n⏰ Time: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n🎯 Signal: *BULLISH REVERSAL*"
                        send_telegram_message(message, result.get('screenshot'))
                        last_bullish_alert = current_time
                        print("✅ Bullish alert sent!")
                    else:
                        time_left = int((cooldown_period - (current_time - last_bullish_alert)) / 60)
                        print(f"⏳ Bullish in cooldown ({time_left} min left)")
                if result and result.get('bearish'):
                    if current_time - last_bearish_alert > cooldown_period:
                        print(f"🔴 BEARISH DIVERGENCE DETECTED!")
                        message = f"🔴 *BEARISH DIVERGENCE DETECTED!*\n\n📊 Symbol: {SYMBOL}\n⏰ Time: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n🎯 Signal: *BEARISH REVERSAL*"
                        send_telegram_message(message, result.get('screenshot'))
                        last_bearish_alert = current_time
                        print("✅ Bearish alert sent!")
                    else:
                        time_left = int((cooldown_period - (current_time - last_bearish_alert)) / 60)
                        print(f"⏳ Bearish in cooldown ({time_left} min left)")
                if result and not result.get('bullish') and not result.get('bearish'):
                    print("📊 No divergence detected")
            except Exception as e:
                print(f"❌ Error in check loop: {e}")
                consecutive_failures += 1
                time.sleep(60)
                continue
            print(f"\n💤 Sleeping for {CHECK_INTERVAL_SECONDS} seconds...")
            next_check = datetime.fromtimestamp(time.time() + CHECK_INTERVAL_SECONDS)
            print(f"⏰ Next check at: {next_check.strftime('%H:%M:%S')}")
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
