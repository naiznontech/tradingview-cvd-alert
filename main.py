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
    return "CVD Alert Bot (Final Fixed)"

@app.route('/health')
def health():
    return "OK", 200

def run_server():
    app.run(host='0.0.0.0', port=10000, debug=False, use_reloader=False)

# ========== CONFIGURATION ==========
TELEGRAM_BOT_TOKEN = '8248626952:AAHaS6S4CPloeUJhJvWLSrG8HXT8whSs6w8'
TELEGRAM_CHAT_ID = '1853898757'
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
    """Calculate CVD exactly as Pine Script"""
    denom = df['high'] - df['low']
    denom = denom.replace(0, 1e-10)
    
    # Exact Pine formula
    df['buying'] = df['volume'] * ((df['close'] - df['low']) / denom)
    df['selling'] = df['volume'] * ((df['high'] - df['close']) / denom)
    
    df['buying'] = df['buying'].fillna(0)
    df['selling'] = df['selling'].fillna(0)
    
    df['delta'] = df['buying'] - df['selling']
    
    # Periodic mode: sum over period
    df['cvd'] = df['delta'].rolling(window=period).sum()
    
    return df

def calculate_ema(series, period):
    return series.ewm(span=period, adjust=False).mean()

def find_divergence_pine_exact(df, fractal_n=5, cvd_period=20):
    """
    FINAL CORRECTED VERSION - 100% Pine Script Logic
    
    Key insight from Pine Script:
    - UpPivot = ta.pivothigh(n,n) detects at current bar i
    - up_trend = close[n] > EMA checks n bars back
    - upFractal = UpPivot and up_trend (true at bar i)
    - High_Last_Price = ta.valuewhen(upFractal, high[n], 0)
      This means: when upFractal is true at bar i, store high[i-n]
    - High_Last_Bar = ta.valuewhen(upFractal, bar_index[n], 0)
      This means: when upFractal is true at bar i, store bar_index[i-n]
    """
    if len(df) < fractal_n * 2 + 50:
        return None, None
    
    df['ema50'] = calculate_ema(df['close'], 50)
    df['bar_index'] = range(len(df))
    
    # Store when pivots are detected (at bar i, referencing i-n)
    upFractals = []
    downFractals = []
    
    # Scan for pivots
    for i in range(fractal_n, len(df) - fractal_n):
        # Check pivot high
        is_pivot_high = True
        for j in range(1, fractal_n + 1):
            if df.iloc[i]['high'] <= df.iloc[i-j]['high'] or df.iloc[i]['high'] <= df.iloc[i+j]['high']:
                is_pivot_high = False
                break
        
        # Check pivot low
        is_pivot_low = True
        for j in range(1, fractal_n + 1):
            if df.iloc[i]['low'] >= df.iloc[i-j]['low'] or df.iloc[i]['low'] >= df.iloc[i+j]['low']:
                is_pivot_low = False
                break
        
        # Pine: up_trend = close[n] > EMA (check at i-n)
        # Pine: upFractal = UpPivot and up_trend
        if is_pivot_high:
            check_idx = i - fractal_n
            if check_idx >= 0:
                # Check if close[n] > EMA at the time of detection
                if df.iloc[check_idx]['close'] > df.iloc[check_idx]['ema50']:
                    # When upFractal is true at bar i:
                    # Store high[n], Hist[n], bar_index[n]
                    upFractals.append({
                        'detection_bar': i,
                        'bar_index': check_idx,  # bar_index[n]
                        'price': df.iloc[check_idx]['high'],  # high[n]
                        'cvd': df.iloc[check_idx]['cvd'],  # CVD[n]
                        'timestamp': df.iloc[check_idx]['timestamp']
                    })
        
        # Pine: down_trend = close[n] < EMA (check at i-n)
        # Pine: downFractal = downPivot and down_trend
        if is_pivot_low:
            check_idx = i - fractal_n
            if check_idx >= 0:
                if df.iloc[check_idx]['close'] < df.iloc[check_idx]['ema50']:
                    downFractals.append({
                        'detection_bar': i,
                        'bar_index': check_idx,  # bar_index[n]
                        'price': df.iloc[check_idx]['low'],  # low[n]
                        'cvd': df.iloc[check_idx]['cvd'],  # CVD[n]
                        'timestamp': df.iloc[check_idx]['timestamp']
                    })
    
    current_bar = len(df) - 1
    bearish_div = None
    bullish_div = None
    
    # Bearish Divergence
    if len(upFractals) >= 2:
        High_Last = upFractals[-1]
        High_Per = upFractals[-2]
        
        High_Last_Bar = High_Last['bar_index']
        High_Per_Bar = High_Per['bar_index']
        High_Last_Price = High_Last['price']
        High_Per_Price = High_Per['price']
        High_Last_Hist = High_Last['cvd']
        High_Per_Hist = High_Per['cvd']
        
        # Pine conditions
        Time_Condition_Bear = (High_Last_Bar + 30) > current_bar
        distance_ok = (High_Last_Bar - High_Per_Bar) < 30
        both_positive = High_Last_Hist > 0 and High_Per_Hist > 0
        
        if both_positive and Time_Condition_Bear and distance_ok:
            # Divergence: Price HH + CVD LH
            if High_Last_Price > High_Per_Price and High_Last_Hist < High_Per_Hist:
                bearish_div = {
                    'type': 'bearish',
                    'price1': High_Last_Price,
                    'price2': High_Per_Price,
                    'cvd1': High_Last_Hist,
                    'cvd2': High_Per_Hist,
                    'time': High_Last['timestamp'],
                    'bars_ago': current_bar - High_Last_Bar,
                    'detected_at_bar': High_Last['detection_bar']
                }
                print(f"  🔴 Bearish Divergence:")
                print(f"     Price: {High_Per_Price:.2f} -> {High_Last_Price:.2f} (HH)")
                print(f"     CVD: {High_Per_Hist:.2f} -> {High_Last_Hist:.2f} (LH)")
                print(f"     Bar indices: {High_Per_Bar} -> {High_Last_Bar}")
                print(f"     Bars ago from current: {current_bar - High_Last_Bar}")
    
    # Bullish Divergence
    if len(downFractals) >= 2:
        Low_Last = downFractals[-1]
        Low_Per = downFractals[-2]
        
        Low_Last_Bar = Low_Last['bar_index']
        Low_Per_Bar = Low_Per['bar_index']
        Low_Last_Price = Low_Last['price']
        Low_Per_Price = Low_Per['price']
        Low_Last_Hist = Low_Last['cvd']
        Low_Per_Hist = Low_Per['cvd']
        
        # Pine conditions
        Time_Condition_Bull = (Low_Last_Bar + 30) > current_bar
        distance_ok = (Low_Last_Bar - Low_Per_Bar) < 30
        both_negative = Low_Last_Hist < 0 and Low_Per_Hist < 0
        
        if both_negative and Time_Condition_Bull and distance_ok:
            # Divergence: Price LL + CVD HL
            if Low_Last_Price < Low_Per_Price and Low_Last_Hist > Low_Per_Hist:
                bullish_div = {
                    'type': 'bullish',
                    'price1': Low_Last_Price,
                    'price2': Low_Per_Price,
                    'cvd1': Low_Last_Hist,
                    'cvd2': Low_Per_Hist,
                    'time': Low_Last['timestamp'],
                    'bars_ago': current_bar - Low_Last_Bar,
                    'detected_at_bar': Low_Last['detection_bar']
                }
                print(f"  🟢 Bullish Divergence:")
                print(f"     Price: {Low_Per_Price:.2f} -> {Low_Last_Price:.2f} (LL)")
                print(f"     CVD: {Low_Per_Hist:.2f} -> {Low_Last_Hist:.2f} (HL)")
                print(f"     Bar indices: {Low_Per_Bar} -> {Low_Last_Bar}")
                print(f"     Bars ago from current: {current_bar - Low_Last_Bar}")
    
    return bullish_div, bearish_div

def main():
    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()
    print("=" * 70)
    print("CVD Alert Bot - FINAL FIXED VERSION")
    print("=" * 70)
    print(f"Exchange: {EXCHANGE}")
    print(f"Symbol: {SYMBOL}")
    print(f"Timeframe: {TIMEFRAME}")
    print(f"CVD Period: {CVD_PERIOD}")
    print(f"Fractal Period: {FRACTAL_PERIOD}")
    print("=" * 70)
    
    startup_msg = f"🤖 *CVD Bot Started - FINAL FIX*\n\n📊 {EXCHANGE}:{SYMBOL}\n⏱️ TF: {TIMEFRAME}\n🔢 CVD: {CVD_PERIOD} | Fractal: {FRACTAL_PERIOD}\n\n✅ Fixed Pine Script Logic\n📈 Monitoring..."
    send_telegram_message(startup_msg)
    
    last_bullish_alert = 0
    last_bearish_alert = 0
    cooldown_period = 1800  # 30 minutes
    consecutive_failures = 0
    
    last_bearish_time = None
    last_bullish_time = None
    
    try:
        while True:
            print(f"\n{'='*70}")
            print(f"[{datetime.now(VN_TZ).strftime('%Y-%m-%d %H:%M:%S')}] Checking...")
            print(f"{'='*70}")
            
            try:
                df = get_klines(EXCHANGE, SYMBOL, TIMEFRAME, limit=200)
                
                if df is None or len(df) < 50:
                    consecutive_failures += 1
                    print(f"❌ Data fetch failed ({consecutive_failures}/3)")
                    time.sleep(60 if consecutive_failures < 3 else 300)
                    if consecutive_failures >= 3:
                        consecutive_failures = 0
                    continue
                
                consecutive_failures = 0
                df = calculate_cvd(df, period=CVD_PERIOD)
                
                latest = df.iloc[-1]
                print(f"💰 Price: ${latest['close']:.2f} | CVD: {latest['cvd']:.2f}")
                
                bullish_div, bearish_div = find_divergence_pine_exact(
                    df, fractal_n=FRACTAL_PERIOD, cvd_period=CVD_PERIOD
                )
                
                current_time = time.time()
                
                # Bullish alert
                if bullish_div:
                    div_time = bullish_div['time'].strftime('%Y-%m-%d %H:%M')
                    if div_time != last_bullish_time:
                        if current_time - last_bullish_alert > cooldown_period:
                            msg = f"🟢 *BULLISH DIVERGENCE*\n\n📊 {SYMBOL}\n⏰ {datetime.now(VN_TZ).strftime('%H:%M')} VN\n\n💰 Price: {bullish_div['price2']:.2f} → {bullish_div['price1']:.2f} (LL)\n📈 CVD: {bullish_div['cvd2']:.2f} → {bullish_div['cvd1']:.2f} (HL)\n\n🎯 *BULLISH REVERSAL*"
                            if send_telegram_message(msg):
                                last_bullish_alert = current_time
                                last_bullish_time = div_time
                                print("✅ Bullish alert sent!")
                        else:
                            print(f"⏳ Cooldown: {int((cooldown_period-(current_time-last_bullish_alert))/60)}m")
                    else:
                        print("⏭️ Already alerted")
                
                # Bearish alert
                if bearish_div:
                    div_time = bearish_div['time'].strftime('%Y-%m-%d %H:%M')
                    if div_time != last_bearish_time:
                        if current_time - last_bearish_alert > cooldown_period:
                            msg = f"🔴 *BEARISH DIVERGENCE*\n\n📊 {SYMBOL}\n⏰ {datetime.now(VN_TZ).strftime('%H:%M')} VN\n\n💰 Price: {bearish_div['price2']:.2f} → {bearish_div['price1']:.2f} (HH)\n📈 CVD: {bearish_div['cvd2']:.2f} → {bearish_div['cvd1']:.2f} (LH)\n\n🎯 *BEARISH REVERSAL*"
                            if send_telegram_message(msg):
                                last_bearish_alert = current_time
                                last_bearish_time = div_time
                                print("✅ Bearish alert sent!")
                        else:
                            print(f"⏳ Cooldown: {int((cooldown_period-(current_time-last_bearish_alert))/60)}m")
                    else:
                        print("⏭️ Already alerted")
                
                if not bullish_div and not bearish_div:
                    print("📊 No divergence")
                
            except Exception as e:
                print(f"❌ Error: {e}")
                import traceback
                traceback.print_exc()
                consecutive_failures += 1
                time.sleep(60)
                continue
            
            next_check = datetime.now(VN_TZ) + timedelta(seconds=CHECK_INTERVAL_SECONDS)
            print(f"💤 Next: {next_check.strftime('%H:%M:%S')}")
            time.sleep(CHECK_INTERVAL_SECONDS)
            
    except KeyboardInterrupt:
        print("\n🛑 Stopped")
        send_telegram_message("🛑 Bot Stopped")

if __name__ == "__main__":
    main()
