# TradingView CVD Divergence Alert Bot
# Self-calculate CVD from Binance API (No TradingView needed!)
# Check every 5 minutes - Optimized for Render free tier

import os
import time
import requests
from datetime import datetime
import pandas as pd
import numpy as np
from flask import Flask
import threading

# ========== WEB SERVER ==========
app = Flask(__name__)

@app.route('/')
def home():
    return "CVD Alert Bot is running! (Binance API Mode - No TradingView)"

@app.route('/health')
def health():
    return "OK", 200

def run_server():
    app.run(host='0.0.0.0', port=10000, debug=False, use_reloader=False)

# ========== CONFIGURATION ==========
TELEGRAM_BOT_TOKEN = '8248626952:AAHaS6S4CPloeUJhJvWLSrG8HXT8whSs6w8'  # Your bot token from @BotFather

TELEGRAM_CHAT_ID = '1853898757'  # Your chat ID


# Binance settings
SYMBOL = "BTCUSDT"
TIMEFRAME = "15m"
CVD_PERIOD = 21
DIVERGENCE_LOOKBACK = 30

CHECK_INTERVAL_SECONDS = 300
MAX_RETRIES = 3

# ========== TELEGRAM FUNCTIONS ==========
def send_telegram_message(message):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        data = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
            "parse_mode": "Markdown"
        }
        response = requests.post(url, data=data, timeout=10)
        return response.json()
    except Exception as e:
        print(f"Error sending Telegram: {e}")
        return None

# ========== BINANCE API ==========
def get_klines(symbol, interval, limit=200):
    try:
        url = "https://api.binance.com/api/v3/klines"
        params = {
            "symbol": symbol,
            "interval": interval,
            "limit": limit
        }
        response = requests.get(url, params=params, timeout=10)
        data = response.json()
        
        df = pd.DataFrame(data, columns=[
            'timestamp', 'open', 'high', 'low', 'close', 'volume',
            'close_time', 'quote_volume', 'trades', 'taker_buy_base',
            'taker_buy_quote', 'ignore'
        ])
        
        df['open'] = pd.to_numeric(df['open'])
        df['high'] = pd.to_numeric(df['high'])
        df['low'] = pd.to_numeric(df['low'])
        df['close'] = pd.to_numeric(df['close'])
        df['volume'] = pd.to_numeric(df['volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        
        return df
        
    except Exception as e:
        print(f"Error fetching data from Binance: {e}")
        return None

# ========== CVD CALCULATION ==========
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

# ========== DIVERGENCE DETECTION ==========
def find_divergence(df, lookback=30):
    if len(df) < lookback + 10:
        return None, None
    
    df['ema50'] = calculate_ema(df['close'], 50)
    
    recent_data = df.tail(lookback).copy()
    
    bearish_div = None
    try:
        price_highs = recent_data.nlargest(3, 'high')
        if len(price_highs) >= 2:
            high1_idx = price_highs.index[0]
            high2_idx = price_highs.index[1]
            
            price1 = df.loc[high1_idx, 'high']
            price2 = df.loc[high2_idx, 'high']
            
            cvd1 = df.loc[high1_idx, 'cvd']
            cvd2 = df.loc[high2_idx, 'cvd']
            
            if price1 > price2 and cvd1 < cvd2 and cvd1 > 0 and cvd2 > 0:
                if df.loc[high1_idx, 'close'] > df.loc[high1_idx, 'ema50']:
                    bearish_div = {
                        'type': 'bearish',
                        'price1': price1,
                        'price2': price2,
                        'cvd1': cvd1,
                        'cvd2': cvd2,
                        'time': df.loc[high1_idx, 'timestamp']
                    }
    except Exception as e:
        print(f"Error detecting bearish divergence: {e}")
    
    bullish_div = None
    try:
        price_lows = recent_data.nsmallest(3, 'low')
        if len(price_lows) >= 2:
            low1_idx = price_lows.index[0]
            low2_idx = price_lows.index[1]
            
            price1 = df.loc[low1_idx, 'low']
            price2 = df.loc[low2_idx, 'low']
            
            cvd1 = df.loc[low1_idx, 'cvd']
            cvd2 = df.loc[low2_idx, 'cvd']
            
            if price1 < price2 and cvd1 > cvd2 and cvd1 < 0 and cvd2 < 0:
                if df.loc[low1_idx, 'close'] < df.loc[low1_idx, 'ema50']:
                    bullish_div = {
                        'type': 'bullish',
                        'price1': price1,
                        'price2': price2,
                        'cvd1': cvd1,
                        'cvd2': cvd2,
                        'time': df.loc[low1_idx, 'timestamp']
                    }
    except Exception as e:
        print(f"Error detecting bullish divergence: {e}")
    
    return bullish_div, bearish_div

# ========== MAIN LOOP ==========
def main():
    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()
    print("Web server started on port 10000")
    
    print("=" * 70)
    print("TradingView CVD Alert Bot Started!")
    print("BINANCE API MODE - Self-Calculate CVD")
    print("=" * 70)
    print(f"Symbol: {SYMBOL}")
    print(f"Timeframe: {TIMEFRAME}")
    print(f"CVD Period: {CVD_PERIOD}")
    print(f"Check interval: {CHECK_INTERVAL_SECONDS} seconds (5 minutes)")
    print(f"Telegram Chat ID: {TELEGRAM_CHAT_ID}")
    print("=" * 70)
    
    startup_msg = (
        "🤖 *CVD Alert Bot Started!*\n\n"
        f"📊 Symbol: {SYMBOL}\n"
        f"⏱️ Timeframe: {TIMEFRAME}\n"
        f"🔢 CVD Period: {CVD_PERIOD}\n"
        f"⏰ Check: Every 5 minutes\n\n"
        "✅ Using Binance API (No TradingView needed)\n"
        "📈 Monitoring for divergence signals..."
    )
    send_telegram_message(startup_msg)
    
    last_bullish_alert = 0
    last_bearish_alert = 0
    cooldown_period = 3600
    
    retry_count = 0
    
    try:
        while True:
            print(f"\n{'='*70}")
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Checking {SYMBOL}...")
            print(f"{'='*70}")
            
            try:
                print(f"📥 Fetching data from Binance...")
                df = get_klines(SYMBOL, TIMEFRAME, limit=200)
                
                if df is None or len(df) < 50:
                    print("❌ Failed to fetch data or insufficient data")
                    retry_count += 1
                    if retry_count >= MAX_RETRIES:
                        error_msg = "❌ Failed to fetch data after 3 retries"
                        print(error_msg)
                        send_telegram_message(error_msg)
                        retry_count = 0
                    time.sleep(60)
                    continue
                
                retry_count = 0
                
                print(f"📊 Calculating CVD...")
                df = calculate_cvd(df, period=CVD_PERIOD)
                
                latest = df.iloc[-1]
                current_price = latest['close']
                current_cvd = latest['cvd']
                
                print(f"💰 Current Price: ${current_price:.2f}")
                print(f"📈 Current CVD: {current_cvd:.2f}")
                
                print(f"🔍 Checking for divergence...")
                bullish_div, bearish_div = find_divergence(df, lookback=DIVERGENCE_LOOKBACK)
                
                current_time = time.time()
                
                if bullish_div:
                    if current_time - last_bullish_alert > cooldown_period:
                        print(f"🟢 BULLISH DIVERGENCE DETECTED!")
                        message = (
                            "🟢 *BULLISH DIVERGENCE DETECTED!*\n\n"
                            f"📊 Symbol: {SYMBOL}\n"
                            f"⏰ Time: {bullish_div['time'].strftime('%Y-%m-%d %H:%M')}\n\n"
                            f"💰 Price:\n"
                            f"  • Low 1: ${bullish_div['price1']:.2f}\n"
                            f"  • Low 2: ${bullish_div['price2']:.2f}\n"
                            f"  • Lower Low: ✅\n\n"
                            f"📈 CVD:\n"
                            f"  • CVD 1: {bullish_div['cvd1']:.2f}\n"
                            f"  • CVD 2: {bullish_div['cvd2']:.2f}\n"
                            f"  • Higher Low: ✅\n\n"
                            f"🎯 Signal: *BULLISH REVERSAL*"
                        )
                        result = send_telegram_message(message)
                        if result:
                            last_bullish_alert = current_time
                            print("✅ Bullish alert sent to Telegram!")
                        else:
                            print("❌ Failed to send Telegram alert")
                    else:
                        time_left = int((cooldown_period - (current_time - last_bullish_alert)) / 60)
                        print(f"⏳ Bullish divergence in cooldown ({time_left} min left)")
                
                if bearish_div:
                    if current_time - last_bearish_alert > cooldown_period:
                        print(f"🔴 BEARISH DIVERGENCE DETECTED!")
                        message = (
                            "🔴 *BEARISH DIVERGENCE DETECTED!*\n\n"
                            f"📊 Symbol: {SYMBOL}\n"
                            f"⏰ Time: {bearish_div['time'].strftime('%Y-%m-%d %H:%M')}\n\n"
                            f"💰 Price:\n"
                            f"  • High 1: ${bearish_div['price1']:.2f}\n"
                            f"  • High 2: ${bearish_div['price2']:.2f}\n"
                            f"  • Higher High: ✅\n\n"
                            f"📈 CVD:\n"
                            f"  • CVD 1: {bearish_div['cvd1']:.2f}\n"
                            f"  • CVD 2: {bearish_div['cvd2']:.2f}\n"
                            f"  • Lower High: ✅\n\n"
                            f"🎯 Signal: *BEARISH REVERSAL*"
                        )
                        result = send_telegram_message(message)
                        if result:
                            last_bearish_alert = current_time
                            print("✅ Bearish alert sent to Telegram!")
                        else:
                            print("❌ Failed to send Telegram alert")
                    else:
                        time_left = int((cooldown_period - (current_time - last_bearish_alert)) / 60)
                        print(f"⏳ Bearish divergence in cooldown ({time_left} min left)")
                
                if not bullish_div and not bearish_div:
                    print("📊 No divergence detected")
                
            except Exception as e:
                print(f"❌ Error in check loop: {e}")
                time.sleep(30)
                continue
            
            print(f"\n💤 Sleeping for {CHECK_INTERVAL_SECONDS} seconds (5 minutes)...")
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

if __name__ == "__main__":
    main()

---

## ✅ **SAU KHI PASTE CODE:**

4. Scroll xuống
5. Commit message: "Add new main.py with Binance API"
6. Click **"Commit new file"**

---

## 🔄 **DEPLOY:**

1. Render → **"Manual Deploy"** → **"Clear build cache & deploy"**
2. Build sẽ NHANH (~2 phút)
3. Logs sẽ hiển thị:
```
Successfully installed flask-3.0.0 numpy-1.24.3 pandas-2.0.3 requests-2.31.0
==> Build successful!
Web server started on port 10000
BINANCE API MODE - Self-Calculate CVD
