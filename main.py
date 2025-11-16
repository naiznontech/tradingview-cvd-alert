import os
import time
import requests
from datetime import datetime, timezone, timedelta
import pandas as pd
import numpy as np
from flask import Flask
import threading

app = Flask(__name__)
VN_TZ = timezone(timedelta(hours=7))

@app.route('/')
def home():
    return "CVD Alert Bot (Exact Pine Script Logic)"

@app.route('/health')
def health():
    return "OK", 200

def run_server():
    app.run(host='0.0.0.0', port=10000, debug=False, use_reloader=False)

# ========== CONFIGURATION ==========

TELEGRAM_BOT_TOKEN = '8248626952:AAHaS6S4CPloeUJhJvWLSrG8HXT8whSs6w8'  # Your bot token from @BotFather

TELEGRAM_CHAT_ID = '1853898757'  # Your chat ID
EXCHANGE = "OKX"
SYMBOL = "BTC-USDT-SWAP"
TIMEFRAME = "15m"
CVD_PERIOD = 20
FRACTAL_PERIOD = 5
CHECK_INTERVAL_SECONDS = 300

def send_telegram_message(message):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        data = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}
        response = requests.post(url, data=data, timeout=10)
        return response.json()
    except Exception as e:
        print(f"Error sending Telegram: {e}")
        return None

def get_klines(exchange, symbol, interval, limit=200):
    try:
        if exchange == "OKX":
            bar_mapping = {"1m": "1m", "5m": "5m", "15m": "15m", "1h": "1H", "4h": "4H", "1d": "1D"}
            bar = bar_mapping.get(interval, "15m")
            url = "https://www.okx.com/api/v5/market/candles"
            params = {"instId": symbol, "bar": bar, "limit": limit}
            response = requests.get(url, params=params, timeout=10)
            if response.status_code != 200:
                return None
            result = response.json()
            if result.get('code') != '0':
                return None
            data = result['data']
            df = pd.DataFrame(data, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'volCcy', 'volCcyQuote', 'confirm'])
            df['timestamp'] = pd.to_datetime(pd.to_numeric(df['timestamp']), unit='ms')
            df = df.sort_values('timestamp').reset_index(drop=True)
        else:
            return None
        df['open'] = pd.to_numeric(df['open'])
        df['high'] = pd.to_numeric(df['high'])
        df['low'] = pd.to_numeric(df['low'])
        df['close'] = pd.to_numeric(df['close'])
        df['volume'] = pd.to_numeric(df['volume'])
        return df
    except Exception as e:
        print(f"Error fetching data: {e}")
        return None

def calculate_cvd(df, period=20):
    denom = df['high'] - df['low']
    denom = denom.replace(0, 1e-10)
    df['buying'] = df['volume'] * ((df['close'] - df['low']) / denom)
    df['selling'] = df['volume'] * ((df['high'] - df['close']) / denom)
    df['buying'] = df['buying'].fillna(0)
    df['selling'] = df['selling'].fillna(0)
    df['delta'] = df['buying'] - df['selling']
    df['cvd'] = df['delta'].rolling(window=period).sum()
    return df

def calculate_ema(series, period):
    return series.ewm(span=period, adjust=False).mean()

def find_divergence_pine_exact(df, fractal_n=5, cvd_period=20):
    """
    Exact implementation of Pine Script CVD Divergence logic
    """
    if len(df) < fractal_n * 2 + 50:
        return None, None
    
    df['ema50'] = calculate_ema(df['close'], 50)
    
    # Find upFractals (pivot highs in uptrend)
    upFractals = []
    for i in range(fractal_n, len(df) - fractal_n):
        is_pivot = True
        for j in range(1, fractal_n + 1):
            if df.iloc[i]['high'] <= df.iloc[i-j]['high'] or df.iloc[i]['high'] <= df.iloc[i+j]['high']:
                is_pivot = False
                break
        if is_pivot:
            # Check uptrend: close[n] > EMA
            if i >= fractal_n and df.iloc[i - fractal_n]['close'] > df.iloc[i - fractal_n]['ema50']:
                upFractals.append({
                    'bar_index': i,
                    'price': df.iloc[i - fractal_n]['high'],
                    'cvd': df.iloc[i - fractal_n]['cvd'],
                    'timestamp': df.iloc[i - fractal_n]['timestamp']
                })
    
    # Find downFractals (pivot lows in downtrend)
    downFractals = []
    for i in range(fractal_n, len(df) - fractal_n):
        is_pivot = True
        for j in range(1, fractal_n + 1):
            if df.iloc[i]['low'] >= df.iloc[i-j]['low'] or df.iloc[i]['low'] >= df.iloc[i+j]['low']:
                is_pivot = False
                break
        if is_pivot:
            # Check downtrend: close[n] > EMA
            if i >= fractal_n and df.iloc[i - fractal_n]['close'] < df.iloc[i - fractal_n]['ema50']:
                downFractals.append({
                    'bar_index': i,
                    'price': df.iloc[i - fractal_n]['low'],
                    'cvd': df.iloc[i - fractal_n]['cvd'],
                    'timestamp': df.iloc[i - fractal_n]['timestamp']
                })
    
    current_bar = len(df) - 1
    bearish_div = None
    
    # Bearish Divergence Detection
    if len(upFractals) >= 2:
        High_Last = upFractals[-1]
        High_Per = upFractals[-2]
        
        High_Last_Bar = High_Last['bar_index']
        High_Per_Bar = High_Per['bar_index']
        
        # Time_Condition_Bear: (High_Last_Bar + 30) > current_bar
        Time_Condition_Bear = (High_Last_Bar + 30) > current_bar
        
        # Distance condition: (High_Last_Bar - High_Per_Bar) < 30
        distance_ok = (High_Last_Bar - High_Per_Bar) < 30
        
        High_Last_Hist = High_Last['cvd']
        High_Per_Hist = High_Per['cvd']
        
        # Both CVD > 0
        both_positive = High_Last_Hist > 0 and High_Per_Hist > 0
        
        if both_positive and Time_Condition_Bear and distance_ok:
            High_Last_Price = High_Last['price']
            High_Per_Price = High_Per['price']
            
            # Divergence: Price Higher High + CVD Lower High
            if High_Last_Price > High_Per_Price and High_Last_Hist < High_Per_Hist:
                bearish_div = {
                    'type': 'bearish',
                    'price1': High_Last_Price,
                    'price2': High_Per_Price,
                    'cvd1': High_Last_Hist,
                    'cvd2': High_Per_Hist,
                    'time': High_Last['timestamp'],
                    'bars_ago': current_bar - High_Last_Bar
                }
                print(f"  🔴 Bearish Divergence:")
                print(f"     Price: {High_Per_Price:.2f} -> {High_Last_Price:.2f} (Higher)")
                print(f"     CVD: {High_Per_Hist:.2f} -> {High_Last_Hist:.2f} (Lower)")
                print(f"     Bars ago: {current_bar - High_Last_Bar}")
    
    bullish_div = None
    
    # Bullish Divergence Detection
    if len(downFractals) >= 2:
        Low_Last = downFractals[-1]
        Low_Per = downFractals[-2]
        
        Low_Last_Bar = Low_Last['bar_index']
        Low_Per_Bar = Low_Per['bar_index']
        
        # Time_Condition_Bull: (Low_Last_Bar + 30) > current_bar
        Time_Condition_Bull = (Low_Last_Bar + 30) > current_bar
        
        # Distance condition: (Low_Last_Bar - Low_Per_Bar) < 30
        distance_ok = (Low_Last_Bar - Low_Per_Bar) < 30
        
        Low_Last_Hist = Low_Last['cvd']
        Low_Per_Hist = Low_Per['cvd']
        
        # Both CVD < 0
        both_negative = Low_Last_Hist < 0 and Low_Per_Hist < 0
        
        if both_negative and Time_Condition_Bull and distance_ok:
            Low_Last_Price = Low_Last['price']
            Low_Per_Price = Low_Per['price']
            
            # Divergence: Price Lower Low + CVD Higher Low
            if Low_Last_Price < Low_Per_Price and Low_Last_Hist > Low_Per_Hist:
                bullish_div = {
                    'type': 'bullish',
                    'price1': Low_Last_Price,
                    'price2': Low_Per_Price,
                    'cvd1': Low_Last_Hist,
                    'cvd2': Low_Per_Hist,
                    'time': Low_Last['timestamp'],
                    'bars_ago': current_bar - Low_Last_Bar
                }
                print(f"  🟢 Bullish Divergence:")
                print(f"     Price: {Low_Per_Price:.2f} -> {Low_Last_Price:.2f} (Lower)")
                print(f"     CVD: {Low_Per_Hist:.2f} -> {Low_Last_Hist:.2f} (Higher)")
                print(f"     Bars ago: {current_bar - Low_Last_Bar}")
    
    return bullish_div, bearish_div

def main():
    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()
    print("Web server started on port 10000")
    print("=" * 70)
    print("CVD Alert Bot - EXACT Pine Script Logic")
    print("=" * 70)
    print(f"Exchange: {EXCHANGE}")
    print(f"Symbol: {SYMBOL}")
    print(f"Timeframe: {TIMEFRAME}")
    print(f"CVD Period: {CVD_PERIOD}")
    print(f"Fractal Period: {FRACTAL_PERIOD}")
    print(f"Check interval: {CHECK_INTERVAL_SECONDS} seconds")
    print("=" * 70)
    
    startup_msg = f"🤖 *CVD Alert Bot Started!*\n\n📊 Exchange: {EXCHANGE}\n💱 Symbol: {SYMBOL}\n⏱️ Timeframe: {TIMEFRAME}\n🔢 CVD Period: {CVD_PERIOD}\n🔍 Fractal Period: {FRACTAL_PERIOD}\n⏰ Check: Every 5 minutes\n\n✅ Exact Pine Script Logic\n📈 Monitoring for divergence signals..."
    send_telegram_message(startup_msg)
    
    last_bullish_alert = 0
    last_bearish_alert = 0
    cooldown_period = 3600
    consecutive_failures = 0
    
    try:
        while True:
            print(f"\n{'='*70}")
            print(f"[{datetime.now(VN_TZ).strftime('%Y-%m-%d %H:%M:%S')} VN] Checking {SYMBOL}...")
            print(f"{'='*70}")
            
            try:
                print(f"📥 Fetching data from {EXCHANGE}...")
                df = get_klines(EXCHANGE, SYMBOL, TIMEFRAME, limit=200)
                
                if df is None or len(df) < 50:
                    consecutive_failures += 1
                    print(f"❌ Failed to fetch data ({consecutive_failures}/3)")
                    if consecutive_failures >= 3:
                        error_msg = "⚠️ Failed to fetch data 3 times. Will retry..."
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
                print(f"🔍 Detecting fractals and checking divergence...")
                
                bullish_div, bearish_div = find_divergence_pine_exact(df, fractal_n=FRACTAL_PERIOD, cvd_period=CVD_PERIOD)
                
                current_time = time.time()
                
                if bullish_div:
                    if current_time - last_bullish_alert > cooldown_period:
                        vn_time = datetime.now(VN_TZ).strftime('%Y-%m-%d %H:%M')
                        bars_info = f"\n📍 Detected: {bullish_div['bars_ago']} bars ago"
                        message = f"🟢 *BULLISH DIVERGENCE DETECTED!*\n\n📊 Symbol: {SYMBOL}\n⏰ Time: {vn_time} (VN){bars_info}\n\n💰 Price: {bullish_div['price2']:.2f} → {bullish_div['price1']:.2f} (Lower)\n📈 CVD: {bullish_div['cvd2']:.2f} → {bullish_div['cvd1']:.2f} (Higher)\n\n🎯 Signal: *BULLISH REVERSAL*"
                        result = send_telegram_message(message)
                        if result:
                            last_bullish_alert = current_time
                            print("✅ Bullish alert sent!")
                        else:
                            print("❌ Failed to send alert")
                    else:
                        time_left = int((cooldown_period - (current_time - last_bullish_alert)) / 60)
                        print(f"⏳ Bullish in cooldown ({time_left} min left)")
                
                if bearish_div:
                    if current_time - last_bearish_alert > cooldown_period:
                        vn_time = datetime.now(VN_TZ).strftime('%Y-%m-%d %H:%M')
                        bars_info = f"\n📍 Detected: {bearish_div['bars_ago']} bars ago"
                        message = f"🔴 *BEARISH DIVERGENCE DETECTED!*\n\n📊 Symbol: {SYMBOL}\n⏰ Time: {vn_time} (VN){bars_info}\n\n💰 Price: {bearish_div['price2']:.2f} → {bearish_div['price1']:.2f} (Higher)\n📈 CVD: {bearish_div['cvd2']:.2f} → {bearish_div['cvd1']:.2f} (Lower)\n\n🎯 Signal: *BEARISH REVERSAL*"
                        result = send_telegram_message(message)
                        if result:
                            last_bearish_alert = current_time
                            print("✅ Bearish alert sent!")
                        else:
                            print("❌ Failed to send alert")
                    else:
                        time_left = int((cooldown_period - (current_time - last_bearish_alert)) / 60)
                        print(f"⏳ Bearish in cooldown ({time_left} min left)")
                
                if not bullish_div and not bearish_div:
                    print("📊 No divergence detected")
                
            except Exception as e:
                print(f"❌ Error in check loop: {e}")
                consecutive_failures += 1
                time.sleep(60)
                continue
            
            print(f"\n💤 Sleeping for {CHECK_INTERVAL_SECONDS} seconds...")
            next_check = datetime.now(VN_TZ) + timedelta(seconds=CHECK_INTERVAL_SECONDS)
            print(f"⏰ Next check at: {next_check.strftime('%H:%M:%S')} (VN)")
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
