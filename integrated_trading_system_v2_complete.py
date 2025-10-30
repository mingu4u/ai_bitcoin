from flask import Flask, request, jsonify
import ccxt
import json
import logging
from datetime import datetime, timedelta, timezone
import os
from dotenv import load_dotenv
import threading
import time
import requests
import pandas as pd
import ta
from ta.utils import dropna
from openai import OpenAI
from pydantic import BaseModel
import sqlite3
import numpy as np

# 환경 변수 로드
load_dotenv()

# ============ 서버별 하드코딩 설정 ============
SERVER_PORT = 5000  # 여기서 포트 변경 (5000, 5001, 5002)
ENABLE_TELEGRAM = True if SERVER_PORT == 5000 else False  # 5000번 포트만 텔레그램 활성화
AI_MONITOR_INTERVAL = 15  # AI 포지션 모니터링 간격 (분)

app = Flask(__name__)
logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s - [Port:{port}] - %(levelname)s - %(message)s'.format(port=SERVER_PORT))

# Binance 설정
exchange = ccxt.binance({
    'apiKey': os.getenv('BINANCE_API_KEY'),
    'secret': os.getenv('BINANCE_SECRET_KEY'),
    'enableRateLimit': True,
    'options': {
        'defaultType': 'future'  # 선물 거래용
    }
})

# 텔레그램 설정
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_IDS = os.getenv('TELEGRAM_CHAT_IDS', '').split(',')

# ============ AI Decision Models ============
class TradingDecision(BaseModel):
    decision: str  # 'approve' or 'reject' or 'modify'
    modified_action: str  # 'buy', 'sell', 'hold' if decision is 'modify'
    percentage: int
    reason: str
    stop_loss_price: float
    take_profit_price: float
    pl_ratio: float
    confidence: float  # 0-1 신뢰도

class PositionExitDecision(BaseModel):
    """포지션 종료 결정용 모델"""
    decision: str  # 'hold', 'close', 'partial_close'
    percentage: int  # partial_close인 경우 종료 비율
    reason: str
    exit_type: str  # 'take_profit', 'stop_loss', 'trend_reversal', 'risk_management', 'time_stop', 'none'
    confidence: float
    urgency: str  # 'immediate', 'soon', 'watch', 'none'

# ============ 다중 종목 설정 ============
SYMBOL_CONFIG = {
    'BTC/USDT': {
        'leverage': 10,
        'position_size_percent': 30,
        'min_position_size': 10,
        'max_position_size': 100000,
        'enabled': True,
        'ai_validation': True,
        'ai_monitoring': True  # AI 포지션 모니터링 활성화
    },
    'SAHARA/USDT': {
        'leverage': 10,
        'position_size_percent': 30,
        'min_position_size': 10,
        'max_position_size': 100000,
        'enabled': True,
        'ai_validation': True,
        'ai_monitoring': True
    },
    'ETH/USDT': {
        'leverage': 10,
        'position_size_percent': 30,
        'min_position_size': 10,
        'max_position_size': 100000,
        'enabled': True,
        'ai_validation': True,
        'ai_monitoring': True
    },
    'RESOLV/USDT': {
        'leverage': 10,
        'position_size_percent': 30,
        'min_position_size': 10,
        'max_position_size': 100000,
        'enabled': True,
        'ai_validation': True,
        'ai_monitoring': True
    },
    'BIO/USDT': {
        'leverage': 10,
        'position_size_percent': 30,
        'min_position_size': 10,
        'max_position_size': 100000,
        'enabled': True,
        'ai_validation': True,
        'ai_monitoring': True
    },
    'UNI/USDT': {
        'leverage': 10,
        'position_size_percent': 30,
        'min_position_size': 10,
        'max_position_size': 100000,
        'enabled': True,
        'ai_validation': True,
        'ai_monitoring': True
    },
    'PENGU/USDT': {
        'leverage': 10,
        'position_size_percent': 30,
        'min_position_size': 10,
        'max_position_size': 100000,
        'enabled': True,
        'ai_validation': True,
        'ai_monitoring': True
    },
    'UMA/USDT': {
        'leverage': 10,
        'position_size_percent': 30,
        'min_position_size': 10,
        'max_position_size': 100000,
        'enabled': True,
        'ai_validation': True,
        'ai_monitoring': True
    },
    'COMP/USDT': {
        'leverage': 10,
        'position_size_percent': 30,
        'min_position_size': 10,
        'max_position_size': 100000,
        'enabled': True,
        'ai_validation': True,
        'ai_monitoring': True
    },
    'XLM/USDT': {
        'leverage': 10,
        'position_size_percent': 30,
        'min_position_size': 10,
        'max_position_size': 100000,
        'enabled': True,
        'ai_validation': True,
        'ai_monitoring': True
    },
    'DOT/USDT': {
        'leverage': 10,
        'position_size_percent': 30,
        'min_position_size': 10,
        'max_position_size': 100000,
        'enabled': True,
        'ai_validation': True,
        'ai_monitoring': True
    },
    'ENA/USDT': {
        'leverage': 10,
        'position_size_percent': 30,
        'min_position_size': 10,
        'max_position_size': 100000,
        'enabled': True,
        'ai_validation': True,
        'ai_monitoring': True
    },
    'RLC/USDT': {
        'leverage': 10,
        'position_size_percent': 30,
        'min_position_size': 10,
        'max_position_size': 100000,
        'enabled': True,
        'ai_validation': True,
        'ai_monitoring': True
    },
    'ETHFI/USDT': {
        'leverage': 10,
        'position_size_percent': 30,
        'min_position_size': 10,
        'max_position_size': 100000,
        'enabled': True,
        'ai_validation': True,
        'ai_monitoring': True
    },
    'SOL/USDT': {
        'leverage': 10,
        'position_size_percent': 30,
        'min_position_size': 10,
        'max_position_size': 100000,
        'enabled': True,
        'ai_validation': True,
        'ai_monitoring': True
    },
    'PYTH/USDT': {
        'leverage': 10,
        'position_size_percent': 30,
        'min_position_size': 10,
        'max_position_size': 100000,
        'enabled': True,
        'ai_validation': True,
        'ai_monitoring': True
    },
    'LINK/USDT': {
        'leverage': 10,
        'position_size_percent': 30,
        'min_position_size': 10,
        'max_position_size': 100000,
        'enabled': True,
        'ai_validation': True,
        'ai_monitoring': True
    },
    'ADA/USDT': {
        'leverage': 10,
        'position_size_percent': 30,
        'min_position_size': 10,
        'max_position_size': 100000,
        'enabled': True,
        'ai_validation': True,
        'ai_monitoring': True
    },
    'XRP/USDT': {
        'leverage': 10,
        'position_size_percent': 30,
        'min_position_size': 10,
        'max_position_size': 100000,
        'enabled': True,
        'ai_validation': True,
        'ai_monitoring': True
    },
    'BNB/USDT': {
        'leverage': 10,
        'position_size_percent': 30,
        'min_position_size': 10,
        'max_position_size': 100000,
        'enabled': True,
        'ai_validation': True,
        'ai_monitoring': True
    },
    'DOGE/USDT': {
        'leverage': 10,
        'position_size_percent': 30,
        'min_position_size': 10,
        'max_position_size': 100000,
        'enabled': True,
        'ai_validation': True,
        'ai_monitoring': True
    },
    'ACH/USDT': {
        'leverage': 10,
        'position_size_percent': 30,
        'min_position_size': 10,
        'max_position_size': 100000,
        'enabled': True,
        'ai_validation': True,
        'ai_monitoring': True
    },
    'CRV/USDT': {
        'leverage': 10,
        'position_size_percent': 30,
        'min_position_size': 10,
        'max_position_size': 100000,
        'enabled': True,
        'ai_validation': True,
        'ai_monitoring': True
    },
    'RONIN/USDT': {
        'leverage': 10,
        'position_size_percent': 30,
        'min_position_size': 10,
        'max_position_size': 100000,
        'enabled': True,
        'ai_validation': True,
        'ai_monitoring': True
    },
    'BCH/USDT': {
        'leverage': 10,
        'position_size_percent': 30,
        'min_position_size': 10,
        'max_position_size': 100000,
        'enabled': True,
        'ai_validation': True,
        'ai_monitoring': True
    },
    'LSK/USDT': {
        'leverage': 10,
        'position_size_percent': 30,
        'min_position_size': 10,
        'max_position_size': 100000,
        'enabled': True,
        'ai_validation': True,
        'ai_monitoring': True
    },
    'HBAR/USDT': {
        'leverage': 10,
        'position_size_percent': 30,
        'min_position_size': 10,
        'max_position_size': 100000,
        'enabled': True,
        'ai_validation': True,
        'ai_monitoring': True
    },
    'AGLD/USDT': {
        'leverage': 10,
        'position_size_percent': 30,
        'min_position_size': 10,
        'max_position_size': 100000,
        'enabled': True,
        'ai_validation': True,
        'ai_monitoring': True
    },
    'ONDO/USDT': {
        'leverage': 10,
        'position_size_percent': 30,
        'min_position_size': 10,
        'max_position_size': 100000,
        'enabled': True,
        'ai_validation': True,
        'ai_monitoring': True
    },
    'HOME/USDT': {
        'leverage': 10,
        'position_size_percent': 30,
        'min_position_size': 10,
        'max_position_size': 100000,
        'enabled': True,
        'ai_validation': True,
        'ai_monitoring': True
    },
    'TRX/USDT': {
        'leverage': 10,
        'position_size_percent': 30,
        'min_position_size': 10,
        'max_position_size': 100000,
        'enabled': True,
        'ai_validation': True,
        'ai_monitoring': True
    }
}

# 기본 설정
DEFAULT_POSITION_SIZE_PERCENT = float(os.getenv('POSITION_SIZE_PERCENT', 10))
DEFAULT_TRAILING_STOP_PERCENT = 3.0
DEFAULT_TRAILING_ACTIVATION_PERCENT = 1.5

# 현재 포지션 추적을 위한 딕셔너리
current_positions = {}

# 모니터링 스레드 관리
position_monitor_threads = {}
ai_monitor_thread = None
ai_monitor_running = False

# ============ SQLite 데이터베이스 초기화 ============
def init_db():
    conn = sqlite3.connect('integrated_trades.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS trades
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  timestamp TEXT,
                  symbol TEXT,
                  trade_type TEXT,
                  ai_decision TEXT,
                  order_id TEXT,
                  action TEXT,
                  percentage INTEGER,
                  reason TEXT,
                  position_size REAL,
                  entry_price REAL,
                  current_price REAL,
                  stop_loss REAL,
                  take_profit REAL,
                  pl_ratio REAL,
                  confidence REAL,
                  reflection TEXT,
                  exit_type TEXT,
                  urgency TEXT)''')
    conn.commit()
    return conn

# ============ Technical Indicators 추가 ============
def add_indicators(df):
    # 볼린저 밴드 추가
    indicator_bb = ta.volatility.BollingerBands(close=df['close'], window=20, window_dev=2)
    df['bb_bbm'] = indicator_bb.bollinger_mavg()
    df['bb_bbh'] = indicator_bb.bollinger_hband()
    df['bb_bbl'] = indicator_bb.bollinger_lband()
    
    # RSI (Relative Strength Index) 추가
    df['rsi'] = ta.momentum.RSIIndicator(close=df['close'], window=14).rsi()
    
    # MACD (Moving Average Convergence Divergence) 추가
    macd = ta.trend.MACD(close=df['close'])
    df['macd'] = macd.macd()
    df['macd_signal'] = macd.macd_signal()
    df['macd_diff'] = macd.macd_diff()
    
    # 이동평균선 (단기, 장기)
    df['sma_20'] = ta.trend.SMAIndicator(close=df['close'], window=20).sma_indicator()
    df['ema_12'] = ta.trend.EMAIndicator(close=df['close'], window=12).ema_indicator()
    
    # Stochastic Oscillator 추가
    stoch = ta.momentum.StochasticOscillator(
        high=df['high'], low=df['low'], close=df['close'], window=14, smooth_window=3)
    df['stoch_k'] = stoch.stoch()
    df['stoch_d'] = stoch.stoch_signal()

    # Average True Range (ATR) 추가
    df['atr'] = ta.volatility.AverageTrueRange(
        high=df['high'], low=df['low'], close=df['close'], window=14).average_true_range()

    # On-Balance Volume (OBV) 추가
    df['obv'] = ta.volume.OnBalanceVolumeIndicator(
        close=df['close'], volume=df['volume']).on_balance_volume()    
    
    # CMF (Chaikin Money Flow) - 자금 흐름 측정
    df['cmf'] = ta.volume.ChaikinMoneyFlowIndicator(
        high=df['high'], low=df['low'], close=df['close'], volume=df['volume'], window=20).chaikin_money_flow()
    
    # ADX (Average Directional Index) - 트렌드 강도 측정
    adx = ta.trend.ADXIndicator(high=df['high'], low=df['low'], close=df['close'])
    df['adx'] = adx.adx()
    df['di_plus'] = adx.adx_pos()
    df['di_minus'] = adx.adx_neg()
    
    # Williams %R - 과매수/과매도 판단
    df['williams_r'] = ta.momentum.WilliamsRIndicator(
        high=df['high'], low=df['low'], close=df['close'], lbp=14).williams_r()
    
    # PPO (Percentage Price Oscillator) - 모멘텀과 추세 전환 감지
    df['ppo'] = ta.momentum.PercentagePriceOscillator(close=df['close']).ppo()
    
    return df

# ============ Market Data Collection ============
def get_market_data(symbol):
    """특정 심볼의 시장 데이터를 수집"""
    try:
        # 현재가격
        ticker = exchange.fetch_ticker(symbol)
        current_price = ticker['last']
        
        # 오더북 데이터
        orderbook = exchange.fetch_order_book(symbol, limit=10)
        
        # 5분봉 데이터 (최근 2.5시간)
        df_5min = pd.DataFrame(
            exchange.fetch_ohlcv(symbol, timeframe='5m', limit=93),
            columns=['timestamp', 'open', 'high', 'low', 'close', 'volume']
        )
        df_5min['timestamp'] = pd.to_datetime(df_5min['timestamp'], unit='ms').dt.tz_localize('UTC').dt.tz_convert('Asia/Seoul')
        df_5min = df_5min.set_index('timestamp')
        df_5min = dropna(df_5min)
        df_5min = add_indicators(df_5min)
        df_5min = df_5min.tail(60)
        
        # 1시간봉 데이터 (최근 24시간)
        df_hourly = pd.DataFrame(
            exchange.fetch_ohlcv(symbol, timeframe='1h', limit=57),
            columns=['timestamp', 'open', 'high', 'low', 'close', 'volume']
        )
        df_hourly['timestamp'] = pd.to_datetime(df_hourly['timestamp'], unit='ms').dt.tz_localize('UTC').dt.tz_convert('Asia/Seoul')
        df_hourly = df_hourly.set_index('timestamp')
        df_hourly = dropna(df_hourly)
        df_hourly = add_indicators(df_hourly)
        df_hourly = df_hourly.tail(24)
        
        # 4시간봉 데이터 (최근 3일)
        df_4h = pd.DataFrame(
            exchange.fetch_ohlcv(symbol, timeframe='4h', limit=51),
            columns=['timestamp', 'open', 'high', 'low', 'close', 'volume']
        )
        df_4h['timestamp'] = pd.to_datetime(df_4h['timestamp'], unit='ms').dt.tz_localize('UTC').dt.tz_convert('Asia/Seoul')
        df_4h = df_4h.set_index('timestamp')
        df_4h = dropna(df_4h)
        df_4h = add_indicators(df_4h)
        df_4h = df_4h.tail(18)
        
        # 공포 탐욕 지수 (BTC만 해당)
        fear_greed_index = None
        if 'BTC' in symbol:
            fear_greed_index = get_fear_and_greed_index()
        
        return {
            'current_price': current_price,
            'orderbook': orderbook,
            'df_5min': df_5min,
            'df_hourly': df_hourly,
            'df_4h': df_4h,
            'fear_greed_index': fear_greed_index
        }
    except Exception as e:
        logging.error(f"Error collecting market data for {symbol}: {e}")
        return None

def get_fear_and_greed_index():
    """공포 탐욕 지수 조회"""
    url = "https://api.alternative.me/fng/"
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        result = data['data'][0]
        
        # timestamp를 초 단위에서 KST datetime 문자열로 변환
        timestamp = pd.to_datetime(int(result['timestamp']), unit='s')
        kst_time = timestamp.tz_localize('UTC').tz_convert('Asia/Seoul')
        result['timestamp'] = kst_time.strftime('%Y/%m/%d %H:%M (KST)')
        
        return result
    except requests.exceptions.RequestException as e:
        logging.error(f"Error fetching Fear and Greed Index: {e}")
        return None

# ============ Reflection 기능 ============
def get_recent_trades(conn, symbol, num_trades=20):
    """특정 심볼의 최근 거래 내역 조회"""
    try:
        c = conn.cursor()
        c.execute("""
            SELECT * FROM trades 
            WHERE symbol = ?
            ORDER BY timestamp DESC
            LIMIT ?
        """, (symbol, num_trades))
        
        columns = [column[0] for column in c.description]
        return pd.DataFrame.from_records(data=c.fetchall(), columns=columns)
    
    except Exception as e:
        logging.error(f"Error fetching recent trades: {e}")
        return pd.DataFrame()

def calculate_performance(trades_df):
    """투자 성과 계산"""
    if trades_df.empty:
        return 0
    
    # 수익률 계산 로직
    total_trades = len(trades_df)
    successful_trades = len(trades_df[trades_df['ai_decision'] == 'approve'])
    
    if total_trades > 0:
        success_rate = (successful_trades / total_trades) * 100
        return success_rate
    return 0

def generate_reflection(trades_df, current_market_data):
    """AI를 사용한 반성 및 개선 사항 생성"""
    performance = calculate_performance(trades_df)
    
    client = OpenAI(api_key=os.getenv("DEEPSEEK_API_KEY"), base_url="https://api.deepseek.com")
    if not client.api_key:
        logging.error("OpenAI API key is missing or invalid.")
        return None
    
    try:
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {
                    "role": "system",
                    "content": """
You are an advanced AI trading analyst assistant. Your role is to analyze recent trading performance including position monitoring decisions and current market conditions to generate specific, actionable insights.
"""
                },
                {
                    "role": "user",
                    "content": f"""
Please analyze the following trading performance data and provide a structured analysis.

**Recent Trades:** {trades_df.to_json(orient='records') if not trades_df.empty else 'No recent trades'}
**Overall Performance:** {performance:.2f}%

Focus on:
1. Entry timing effectiveness
2. Exit timing optimization (including AI monitoring decisions)
3. Risk management improvements
4. Pattern recognition

Keep the analysis concise and actionable.
"""
                }
            ],
            max_tokens=2000
        )
        
        return response.choices[0].message.content
        
    except Exception as e:
        logging.error(f"Error generating reflection: {e}")
        return None

# ============ AI Position Monitoring ============
def ai_monitor_position(symbol, position_info):
    """AI가 포지션을 모니터링하고 종료 여부 결정"""
    
    client = OpenAI(api_key=os.getenv("DEEPSEEK_API_KEY"), base_url="https://api.deepseek.com")
    if not client.api_key:
        logging.error("OpenAI API key is missing or invalid.")
        return None
    
    # 시장 데이터 수집
    market_data = get_market_data(symbol)
    if not market_data:
        return None
    
    # 포지션 정보
    entry_price = position_info['entry_price']
    current_price = market_data['current_price']
    side = position_info['side']
    amount = position_info['amount']
    stop_loss = position_info.get('stop_loss', 0)
    take_profit = position_info.get('take_profit', 0)
    
    # PnL 계산
    if side == 'buy':
        pnl_percent = ((current_price - entry_price) / entry_price) * 100
        distance_to_sl = ((current_price - stop_loss) / current_price) * 100 if stop_loss else 100
        distance_to_tp = ((take_profit - current_price) / current_price) * 100 if take_profit else 100
    else:  # sell
        pnl_percent = ((entry_price - current_price) / entry_price) * 100
        distance_to_sl = ((stop_loss - current_price) / current_price) * 100 if stop_loss else 100
        distance_to_tp = ((current_price - take_profit) / current_price) * 100 if take_profit else 100
    
    # 포지션 보유 시간
    entry_time = position_info.get('entry_time', datetime.now())
    holding_time = (datetime.now() - entry_time).total_seconds() / 60  # 분 단위
    
    # Technical Indicators
    df_5min = market_data['df_5min']
    df_hourly = market_data['df_hourly']
    df_4h = market_data['df_4h']
    
    prompt = f"""
You are an expert AI position manager monitoring an open {side} position for {symbol}.

**POSITION DETAILS:**
- Entry Price: ${entry_price:.2f}
- Current Price: ${current_price:.2f}
- Position Size: {amount}
- Current PnL: {pnl_percent:.2f}%
- Holding Time: {holding_time:.0f} minutes
- Distance to Stop Loss: {distance_to_sl:.2f}%
- Distance to Take Profit: {distance_to_tp:.2f}%

**TECHNICAL INDICATORS:**

**5-Minute (Latest):**
- RSI: {df_5min['rsi'].iloc[-1]:.2f}
- MACD: {df_5min['macd'].iloc[-1]:.2f}
- Bollinger: Price at {((current_price - df_5min['bb_bbl'].iloc[-1]) / (df_5min['bb_bbh'].iloc[-1] - df_5min['bb_bbl'].iloc[-1]) * 100):.0f}% of band
- ADX: {df_5min['adx'].iloc[-1]:.2f}
- CMF: {df_5min['cmf'].iloc[-1]:.2f}

**1-Hour (Latest):**
- RSI: {df_hourly['rsi'].iloc[-1]:.2f}
- MACD: {df_hourly['macd'].iloc[-1]:.2f}
- ADX: {df_hourly['adx'].iloc[-1]:.2f}

**4-Hour (Latest):**
- RSI: {df_4h['rsi'].iloc[-1]:.2f}
- ADX: {df_4h['adx'].iloc[-1]:.2f}

**EXIT DECISION CRITERIA:**

1. **IMMEDIATE EXIT (urgency: immediate):**
   - Trend reversal signals on multiple timeframes
   - Breaking critical support/resistance
   - Extreme divergence in indicators
   - Risk of significant loss (approaching stop loss)

2. **SOON EXIT (urgency: soon):**
   - Weakening trend momentum
   - Approaching major resistance (for longs) or support (for shorts)
   - Overbought/oversold conditions aligning against position

3. **PARTIAL EXIT (decision: partial_close):**
   - Secure partial profits while trend remains favorable
   - Reduce risk in uncertain conditions
   - Scale out at key levels

4. **HOLD (decision: hold):**
   - Trend remains strong in favor of position
   - No reversal signals
   - Good risk/reward to continue

**REQUIRED DECISION:**
Analyze the current market conditions and decide whether to:
1. HOLD - Continue holding the position
2. CLOSE - Exit the entire position immediately
3. PARTIAL_CLOSE - Exit a portion of the position (specify %)

Consider:
- Current profit/loss status
- Market momentum and trend
- Risk of reversal
- Optimal exit timing

Be decisive and protect capital while maximizing gains.
"""
    
    try:
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": "You are a professional position manager focused on protecting capital and maximizing gains through optimal exit timing."},
                {"role": "user", "content": prompt}
            ],
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "position_exit_decision",
                    "strict": True,
                    "schema": {
                        "type": "object",
                        "properties": {
                            "decision": {"type": "string", "enum": ["hold", "close", "partial_close"]},
                            "percentage": {"type": "integer", "minimum": 0, "maximum": 100},
                            "reason": {"type": "string"},
                            "exit_type": {"type": "string", "enum": ["take_profit", "stop_loss", "trend_reversal", "risk_management", "time_stop", "none"]},
                            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                            "urgency": {"type": "string", "enum": ["immediate", "soon", "watch", "none"]}
                        },
                        "required": ["decision", "percentage", "reason", "exit_type", "confidence", "urgency"],
                        "additionalProperties": False
                    }
                }
            },
            max_tokens=1000
        )
        
        result = PositionExitDecision.model_validate_json(response.choices[0].message.content)
        
        # 결정 로깅
        logging.info(f"AI Position Monitor for {symbol}: {result.decision.upper()}")
        logging.info(f"Reason: {result.reason}")
        logging.info(f"Urgency: {result.urgency}, Confidence: {result.confidence:.2%}")
        
        # DB에 모니터링 기록 저장
        conn = init_db()
        c = conn.cursor()
        timestamp = datetime.now().isoformat()
        c.execute("""INSERT INTO trades 
                     (timestamp, symbol, trade_type, ai_decision, action, percentage, reason, 
                      entry_price, current_price, confidence, exit_type, urgency) 
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                  (timestamp, symbol, 'AI_MONITOR', result.decision, 'monitor', result.percentage, 
                   result.reason, entry_price, current_price, result.confidence, 
                   result.exit_type, result.urgency))
        conn.commit()
        conn.close()
        
        return result
        
    except Exception as e:
        logging.error(f"Error in AI position monitoring: {e}")
        return None

def execute_position_exit(symbol, decision):
    """포지션 종료 실행"""
    try:
        position = current_positions.get(symbol)
        if not position:
            logging.warning(f"No position found for {symbol}")
            return False
        
        # 현재 포지션 정보
        side = position['side']
        amount = position['amount']
        
        # 종료할 수량 계산
        if decision.decision == 'close':
            exit_amount = amount
        elif decision.decision == 'partial_close':
            exit_amount = amount * (decision.percentage / 100)
        else:
            return False
        
        # 시장가 주문으로 포지션 종료
        if side == 'buy':
            order = exchange.create_market_sell_order(symbol, exit_amount)
        else:  # sell
            order = exchange.create_market_buy_order(symbol, exit_amount)
        
        logging.info(f"Position exit executed for {symbol}: {decision.decision}")
        
        # 전체 종료인 경우 포지션 추적에서 제거
        if decision.decision == 'close':
            del current_positions[symbol]
        else:
            # 부분 종료인 경우 수량 업데이트
            current_positions[symbol]['amount'] -= exit_amount
        
        # 텔레그램 알림
        if ENABLE_TELEGRAM:
            message = f"""
🤖 <b>AI Position Exit</b>

<b>Symbol:</b> {symbol}
<b>Decision:</b> {decision.decision.upper()}
<b>Exit Type:</b> {decision.exit_type}
<b>Amount:</b> {exit_amount:.6f}
<b>Reason:</b> {decision.reason}
<b>Urgency:</b> {decision.urgency}
<b>Confidence:</b> {decision.confidence:.1%}

⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
            """.strip()
            send_telegram_notification(message, 'high' if decision.urgency == 'immediate' else 'normal')
        
        return True
        
    except Exception as e:
        logging.error(f"Error executing position exit for {symbol}: {e}")
        return False

def ai_monitoring_cycle():
    """AI 모니터링 주기 실행"""
    global current_positions
    
    logging.info("Starting AI position monitoring cycle...")
    
    monitored_count = 0
    exit_decisions = []
    
    for symbol, position in current_positions.copy().items():
        # AI 모니터링이 활성화된 심볼인지 확인
        if not SYMBOL_CONFIG.get(symbol, {}).get('ai_monitoring', True):
            continue
        
        logging.info(f"Monitoring position: {symbol}")
        
        # AI 모니터링 실행
        decision = ai_monitor_position(symbol, position)
        
        if decision:
            monitored_count += 1
            
            # 종료 결정인 경우
            if decision.decision in ['close', 'partial_close']:
                # 신뢰도와 긴급도 확인
                if decision.confidence >= 0.6 or decision.urgency == 'immediate':
                    success = execute_position_exit(symbol, decision)
                    if success:
                        exit_decisions.append({
                            'symbol': symbol,
                            'decision': decision.decision,
                            'reason': decision.reason
                        })
                else:
                    logging.info(f"Exit decision for {symbol} not executed due to low confidence ({decision.confidence:.1%})")
        
        # API 제한을 위한 짧은 대기
        time.sleep(2)
    
    # 모니터링 결과 요약
    if monitored_count > 0:
        logging.info(f"AI monitoring cycle completed: {monitored_count} positions monitored")
        if exit_decisions:
            logging.info(f"Exit decisions executed: {exit_decisions}")
    
    return monitored_count, exit_decisions

def start_ai_monitoring():
    """AI 모니터링 스레드 시작"""
    global ai_monitor_thread, ai_monitor_running
    
    def monitor_loop():
        global ai_monitor_running
        ai_monitor_running = True
        
        while ai_monitor_running:
            try:
                # 현재 포지션이 있는 경우에만 모니터링
                if current_positions:
                    ai_monitoring_cycle()
                else:
                    logging.info("No positions to monitor")
                
                # 다음 모니터링까지 대기 (15분)
                time.sleep(AI_MONITOR_INTERVAL * 60)
                
            except Exception as e:
                logging.error(f"Error in AI monitoring loop: {e}")
                time.sleep(60)  # 오류 발생 시 1분 대기
    
    if not ai_monitor_running:
        ai_monitor_thread = threading.Thread(target=monitor_loop, daemon=True)
        ai_monitor_thread.start()
        logging.info("AI position monitoring started (15-minute intervals)")

def stop_ai_monitoring():
    """AI 모니터링 중지"""
    global ai_monitor_running
    ai_monitor_running = False
    logging.info("AI position monitoring stopped")

# ============ AI Decision Making ============
def ai_validate_signal(symbol, action, market_data, recent_trades_df):
    """AI를 사용하여 거래 신호를 검증"""
    
    client = OpenAI(api_key=os.getenv("DEEPSEEK_API_KEY"), base_url="https://api.deepseek.com")
    if not client.api_key:
        logging.error("OpenAI API key is missing or invalid.")
        return None
    
    # Reflection 생성
    reflection = generate_reflection(recent_trades_df, market_data)
    
    # Technical Indicators 준비
    df_5min = market_data['df_5min']
    df_hourly = market_data['df_hourly'] 
    df_4h = market_data['df_4h']
    
    # 프롬프트 구성
    prompt = f"""
You are an expert crypto trading AI validator. You need to validate trading signals using technical analysis.

**SIGNAL TO VALIDATE:**
- Symbol: {symbol}
- Proposed Action: {action}
- Current Price: {market_data['current_price']:.2f}

**TECHNICAL INDICATORS:**

**5-Minute Chart (Latest):**
- RSI(14): {df_5min['rsi'].iloc[-1]:.2f}
- MACD: {df_5min['macd'].iloc[-1]:.2f}
- Bollinger Bands: Middle={df_5min['bb_bbm'].iloc[-1]:.2f}, Upper={df_5min['bb_bbh'].iloc[-1]:.2f}, Lower={df_5min['bb_bbl'].iloc[-1]:.2f}
- Stochastic: %K={df_5min['stoch_k'].iloc[-1]:.2f}, %D={df_5min['stoch_d'].iloc[-1]:.2f}
- ATR: {df_5min['atr'].iloc[-1]:.2f}
- Williams %R: {df_5min['williams_r'].iloc[-1]:.2f}
- CMF: {df_5min['cmf'].iloc[-1]:.2f}
- ADX: {df_5min['adx'].iloc[-1]:.2f}
- DI+: {df_5min['di_plus'].iloc[-1]:.2f}, DI-: {df_5min['di_minus'].iloc[-1]:.2f}
- PPO: {df_5min['ppo'].iloc[-1]:.2f}

**1-Hour Chart (Latest):**
- RSI(14): {df_hourly['rsi'].iloc[-1]:.2f}
- MACD: {df_hourly['macd'].iloc[-1]:.2f}
- Bollinger Bands: Middle={df_hourly['bb_bbm'].iloc[-1]:.2f}
- ATR: {df_hourly['atr'].iloc[-1]:.2f}
- ADX: {df_hourly['adx'].iloc[-1]:.2f}

**4-Hour Chart (Latest):**
- RSI(14): {df_4h['rsi'].iloc[-1]:.2f}
- MACD: {df_4h['macd'].iloc[-1]:.2f}
- ADX: {df_4h['adx'].iloc[-1]:.2f}

{'**Fear & Greed Index:** ' + str(market_data["fear_greed_index"]["value"]) + ' (' + market_data["fear_greed_index"]["value_classification"] + ')' if market_data.get("fear_greed_index") else ''}

**RECENT PERFORMANCE REFLECTION:**
{reflection if reflection else 'No previous trading data available'}

**VALIDATION CRITERIA:**

For BUY signals, validate if:
- RSI is not overbought (preferably < 70)
- MACD shows bullish momentum or crossover
- Price is near support levels or breaking resistance
- Volume and momentum indicators confirm

For SELL signals, validate if:  
- RSI is not oversold (preferably > 30)
- MACD shows bearish momentum or crossover
- Price is near resistance levels or breaking support
- Volume and momentum indicators confirm

**DECISION REQUIRED:**
Based on the technical indicators and market conditions, should this {action} signal be:
1. APPROVED - Execute the trade as proposed
2. REJECTED - Do not execute, conditions unfavorable
3. MODIFIED - Execute with adjusted parameters

Provide specific reasoning based on the indicators and suggest optimal entry, stop loss, and take profit levels.
"""
    
    try:
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": "You are a professional crypto trading AI that validates signals based on technical analysis. Be decisive and specific."},
                {"role": "user", "content": prompt}
            ],
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "trading_validation",
                    "strict": True,
                    "schema": {
                        "type": "object",
                        "properties": {
                            "decision": {"type": "string", "enum": ["approve", "reject", "modify"]},
                            "modified_action": {"type": "string", "enum": ["buy", "sell", "hold"]},
                            "percentage": {"type": "integer", "minimum": 0, "maximum": 100},
                            "reason": {"type": "string"},
                            "stop_loss_price": {"type": "number"},
                            "take_profit_price": {"type": "number"},
                            "pl_ratio": {"type": "number", "minimum": 1.0, "maximum": 5.0},
                            "confidence": {"type": "number", "minimum": 0, "maximum": 1}
                        },
                        "required": ["decision", "modified_action", "percentage", "reason", "stop_loss_price", "take_profit_price", "pl_ratio", "confidence"],
                        "additionalProperties": False
                    }
                }
            },
            max_tokens=1000
        )
        
        result = TradingDecision.model_validate_json(response.choices[0].message.content)
        
        # 거래 기록 저장
        conn = init_db()
        c = conn.cursor()
        timestamp = datetime.now().isoformat()
        c.execute("""INSERT INTO trades 
                     (timestamp, symbol, trade_type, ai_decision, action, percentage, reason, 
                      current_price, stop_loss, take_profit, pl_ratio, confidence, reflection) 
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                  (timestamp, symbol, 'AI_VALIDATION', result.decision, action, result.percentage, 
                   result.reason, market_data['current_price'], result.stop_loss_price, 
                   result.take_profit_price, result.pl_ratio, result.confidence, reflection))
        conn.commit()
        conn.close()
        
        logging.info(f"AI Decision for {symbol}: {result.decision.upper()} - Confidence: {result.confidence:.2%}")
        logging.info(f"Reason: {result.reason}")
        
        return result
        
    except Exception as e:
        logging.error(f"Error in AI validation: {e}")
        return None

# ============ Trading Functions ============
def send_telegram_notification(message, importance='normal'):
    """텔레그램 알림 전송"""
    if not ENABLE_TELEGRAM:
        return
        
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_IDS:
        logging.warning("텔레그램 설정이 완료되지 않았습니다.")
        return
    
    # HTML 파싱 모드 사용
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    
    # 중요도에 따른 이모지 추가
    emoji_map = {
        'high': '🚨',
        'normal': '📊',
        'low': 'ℹ️',
        'error': '❌',
        'success': '✅',
        'warning': '⚠️'
    }
    
    emoji = emoji_map.get(importance, '📊')
    formatted_message = f"{emoji} {message}"
    
    for chat_id in TELEGRAM_CHAT_IDS:
        if chat_id:
            try:
                payload = {
                    'chat_id': chat_id.strip(),
                    'text': formatted_message,
                    'parse_mode': 'HTML'
                }
                response = requests.post(url, json=payload)
                response.raise_for_status()
            except Exception as e:
                logging.error(f"텔레그램 알림 전송 실패 (chat_id: {chat_id}): {str(e)}")

def calculate_position_size(symbol, balance):
    """포지션 크기 계산"""
    config = SYMBOL_CONFIG.get(symbol, {})
    
    # 심볼별 포지션 크기 비율 설정
    position_size_percent = config.get('position_size_percent', DEFAULT_POSITION_SIZE_PERCENT)
    
    # 포지션 크기 계산
    position_size = balance * (position_size_percent / 100)
    
    # 최소/최대 포지션 크기 제한 적용
    min_size = config.get('min_position_size', 10)
    max_size = config.get('max_position_size', 100000)
    
    position_size = max(min_size, min(position_size, max_size))
    
    return position_size, position_size_percent

def set_leverage(symbol):
    """심볼별 레버리지 설정"""
    try:
        config = SYMBOL_CONFIG.get(symbol, {})
        leverage = config.get('leverage', 10)
        
        # 레버리지 설정
        exchange.set_leverage(leverage, symbol)
        logging.info(f"{symbol} 레버리지 설정: {leverage}x")
        return leverage
    except Exception as e:
        logging.error(f"{symbol} 레버리지 설정 실패: {str(e)}")
        return None

def place_orders_with_sl_tp(symbol, action, amount, stop_loss_price, take_profit_price, 
                            trailing_stop_percent=None, trailing_activation_percent=None):
    """스탑로스와 테이크프로핏이 포함된 주문 실행"""
    try:
        # 시장가 주문 실행
        if action == 'buy':
            order = exchange.create_market_buy_order(symbol, amount)
        elif action == 'sell':
            order = exchange.create_market_sell_order(symbol, amount)
        else:
            return None
        
        entry_price = order['average'] if order['average'] else order['price']
        
        # SL/TP 주문 설정
        time.sleep(1)
        
        # 스탑로스 주문
        sl_side = 'sell' if action == 'buy' else 'buy'
        sl_order = exchange.create_order(
            symbol=symbol,
            type='stop',
            side=sl_side,
            amount=amount,
            stopPrice=stop_loss_price
        )
        
        # 테이크프로핏 주문
        tp_side = 'sell' if action == 'buy' else 'buy'
        tp_order = exchange.create_order(
            symbol=symbol,
            type='take_profit_market',
            side=tp_side,
            amount=amount,
            stopPrice=take_profit_price
        )
        
        # 트레일링 스탑 설정 (지원하는 경우)
        if trailing_stop_percent and trailing_activation_percent:
            # 트레일링 스탑 모니터링 스레드 시작
            start_trailing_stop_monitor(symbol, action, entry_price, amount, 
                                      trailing_stop_percent, trailing_activation_percent)
        
        return {
            'entry': order,
            'sl': sl_order,
            'tp': tp_order,
            'actual_entry': entry_price,
            'adjusted_amount': amount
        }
        
    except Exception as e:
        logging.error(f"주문 실행 오류: {str(e)}")
        return None

def start_trailing_stop_monitor(symbol, side, entry_price, amount, trailing_percent, activation_percent):
    """트레일링 스탑 모니터링 스레드 시작"""
    def monitor():
        activation_price = entry_price * (1 + activation_percent/100) if side == 'buy' else entry_price * (1 - activation_percent/100)
        highest_price = entry_price
        lowest_price = entry_price
        activated = False
        
        while symbol in current_positions:
            try:
                ticker = exchange.fetch_ticker(symbol)
                current_price = ticker['last']
                
                if side == 'buy':
                    if not activated and current_price >= activation_price:
                        activated = True
                        logging.info(f"{symbol} 트레일링 스탑 활성화: {current_price}")
                    
                    if activated:
                        if current_price > highest_price:
                            highest_price = current_price
                            # 새로운 스탑로스 가격 계산
                            new_sl = highest_price * (1 - trailing_percent/100)
                            # 스탑로스 주문 업데이트 로직
                            update_stop_loss(symbol, new_sl, amount)
                            
                else:  # sell
                    if not activated and current_price <= activation_price:
                        activated = True
                        logging.info(f"{symbol} 트레일링 스탑 활성화: {current_price}")
                    
                    if activated:
                        if current_price < lowest_price:
                            lowest_price = current_price
                            new_sl = lowest_price * (1 + trailing_percent/100)
                            update_stop_loss(symbol, new_sl, amount)
                
                time.sleep(30)  # 30초마다 체크
                
            except Exception as e:
                logging.error(f"트레일링 스탑 모니터링 오류 ({symbol}): {str(e)}")
                time.sleep(60)
    
    thread = threading.Thread(target=monitor, daemon=True)
    thread.start()
    position_monitor_threads[symbol] = thread

def update_stop_loss(symbol, new_sl_price, amount):
    """스탑로스 주문 업데이트"""
    try:
        # 기존 스탑로스 주문 취소
        open_orders = exchange.fetch_open_orders(symbol)
        for order in open_orders:
            if order['type'] == 'stop':
                exchange.cancel_order(order['id'], symbol)
                time.sleep(1)
        
        # 새로운 스탑로스 주문 생성
        position = current_positions.get(symbol)
        if position:
            sl_side = 'sell' if position['side'] == 'buy' else 'buy'
            exchange.create_order(
                symbol=symbol,
                type='stop',
                side=sl_side,
                amount=amount,
                stopPrice=new_sl_price
            )
            logging.info(f"{symbol} 스탑로스 업데이트: {new_sl_price}")
            
    except Exception as e:
        logging.error(f"스탑로스 업데이트 오류 ({symbol}): {str(e)}")

def format_position_entry_message(symbol, action, amount, entry_price, sl, tp, pl_ratio, 
                                 position_size, balance, trailing_stop=None, trailing_activation=None):
    """포지션 진입 메시지 포맷팅"""
    direction = "🟢 롱" if action == 'buy' else "🔴 숏"
    
    # P&L 계산
    if action == 'buy':
        potential_loss = (entry_price - sl) * amount
        potential_profit = (tp - entry_price) * amount
    else:
        potential_loss = (sl - entry_price) * amount
        potential_profit = (entry_price - tp) * amount
    
    message = f"""
<b>📈 포지션 진입 알림</b>

<b>심볼:</b> {symbol}
<b>방향:</b> {direction}
<b>진입가:</b> ${entry_price:,.2f}
<b>수량:</b> {amount:.4f}
<b>포지션 크기:</b> ${position_size:,.2f}

<b>리스크 관리:</b>
• 스탑로스: ${sl:,.2f} (예상 손실: ${potential_loss:,.2f})
• 테이크프로핏: ${tp:,.2f} (예상 이익: ${potential_profit:,.2f})
• P/L 비율: {pl_ratio:.2f}
"""
    
    if trailing_stop and trailing_activation:
        message += f"""• 트레일링 스탑: {trailing_stop}%
• 활성화 기준: +{trailing_activation}%
"""
    
    message += f"""
<b>계좌 정보:</b>
• 잔고: ${balance:,.2f}
• 사용 비율: {(position_size/balance)*100:.1f}%

⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
    """.strip()
    
    return message

# ============ Flask Routes ============
@app.route('/webhook', methods=['POST'])
def webhook():
    """TradingView 웹훅 수신 및 처리"""
    try:
        data = request.get_json()
        
        # 기본 검증
        if not data:
            return jsonify({'error': 'No data received'}), 400
        
        action = data.get('action')
        symbol = data.get('symbol', 'BTC/USDT')
        message = data.get('message', '')
        
        # 심볼 정규화
        if not symbol.endswith('/USDT'):
            symbol = f"{symbol}/USDT"
        
        # 심볼 설정 확인
        if symbol not in SYMBOL_CONFIG:
            return jsonify({'error': f'Symbol {symbol} not configured'}), 400
        
        if not SYMBOL_CONFIG[symbol].get('enabled', True):
            return jsonify({'error': f'Symbol {symbol} is disabled'}), 400
        
        logging.info(f"웹훅 수신 - 심볼: {symbol}, 액션: {action}, 메시지: {message}")
        
        # AI 검증이 활성화되어 있는지 확인
        use_ai = SYMBOL_CONFIG[symbol].get('ai_validation', True)
        
        if use_ai:
            # 시장 데이터 수집
            market_data = get_market_data(symbol)
            if not market_data:
                return jsonify({'error': 'Failed to collect market data'}), 500
            
            # 최근 거래 내역 조회
            conn = init_db()
            recent_trades = get_recent_trades(conn, symbol)
            conn.close()
            
            # AI 검증
            ai_decision = ai_validate_signal(symbol, action, market_data, recent_trades)
            
            if not ai_decision:
                return jsonify({'error': 'AI validation failed'}), 500
            
            # AI 결정에 따른 처리
            if ai_decision.decision == 'reject':
                message = f"""
⚠️ <b>AI 신호 거부</b>

<b>심볼:</b> {symbol}
<b>원래 신호:</b> {action.upper()}
<b>AI 결정:</b> REJECT
<b>신뢰도:</b> {ai_decision.confidence:.1%}
<b>이유:</b> {ai_decision.reason}

⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
                """.strip()
                send_telegram_notification(message, 'warning')
                return jsonify({
                    'status': 'rejected',
                    'reason': ai_decision.reason,
                    'confidence': ai_decision.confidence
                }), 200
            
            elif ai_decision.decision == 'modify':
                # AI가 수정한 매매 신호 사용
                action = ai_decision.modified_action
                if action == 'hold':
                    return jsonify({'status': 'hold', 'reason': ai_decision.reason}), 200
            
            # AI가 승인하거나 수정한 경우 거래 실행
            stop_loss_price = ai_decision.stop_loss_price
            take_profit_price = ai_decision.take_profit_price
            pl_ratio = ai_decision.pl_ratio
            position_percent = ai_decision.percentage
            
        else:
            # AI 검증 없이 기본값 사용
            ticker = exchange.fetch_ticker(symbol)
            current_price = ticker['last']
            
            if action == 'buy':
                stop_loss_price = current_price * 0.98  # -2%
                take_profit_price = current_price * 1.04  # +4%
            else:
                stop_loss_price = current_price * 1.02  # +2%
                take_profit_price = current_price * 0.96  # -4%
            
            pl_ratio = 2.0
            position_percent = SYMBOL_CONFIG[symbol].get('position_size_percent', 10)
        
        # 거래 실행
        if action in ['buy', 'sell', 'close']:
            # 잔고 확인
            balance_info = exchange.fetch_balance()
            usdt_balance = balance_info['USDT']['free']
            
            if action == 'close':
                # 포지션 청산
                positions = exchange.fetch_positions([symbol])
                for position in positions:
                    if float(position['contracts']) != 0:
                        close_side = 'sell' if position['side'] == 'long' else 'buy'
                        exchange.create_market_order(symbol, close_side, abs(float(position['contracts'])))
                        
                        message = f"""
✅ <b>포지션 청산 완료</b>

<b>심볼:</b> {symbol}
<b>청산 수량:</b> {abs(float(position['contracts']))}

⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
                        """.strip()
                        send_telegram_notification(message, 'success')
                        
                        # 포지션 추적에서 제거
                        if symbol in current_positions:
                            del current_positions[symbol]
                        
                return jsonify({'status': 'closed'}), 200
            
            # 포지션 크기 계산
            position_size = usdt_balance * (position_percent / 100)
            
            # 레버리지 설정
            leverage = set_leverage(symbol)
            if not leverage:
                return jsonify({'error': 'Failed to set leverage'}), 500
            
            # 레버리지 적용한 실제 수량 계산
            ticker = exchange.fetch_ticker(symbol)
            current_price = ticker['last']
            amount = (position_size * leverage) / current_price
            
            # 트레일링 스탑 설정
            trailing_stop = DEFAULT_TRAILING_STOP_PERCENT
            trailing_activation = DEFAULT_TRAILING_ACTIVATION_PERCENT
            
            # 주문 실행
            orders = place_orders_with_sl_tp(
                symbol, action, amount, 
                stop_loss_price, take_profit_price,
                trailing_stop, trailing_activation
            )
            
            if orders:
                # 포지션 추적 (entry_time 추가)
                current_positions[symbol] = {
                    'side': action,
                    'entry_price': orders['actual_entry'],
                    'amount': orders['adjusted_amount'],
                    'stop_loss': stop_loss_price,
                    'take_profit': take_profit_price,
                    'trailing_stop_percent': trailing_stop,
                    'trailing_activation_percent': trailing_activation,
                    'entry_time': datetime.now()  # 진입 시간 추가
                }
                
                # 알림 전송
                entry_message = format_position_entry_message(
                    symbol, action, orders['adjusted_amount'], orders['actual_entry'],
                    stop_loss_price, take_profit_price,
                    pl_ratio, position_size, usdt_balance,
                    trailing_stop, trailing_activation
                )
                
                if use_ai:
                    entry_message += f"\n<b>AI 신뢰도:</b> {ai_decision.confidence:.1%}"
                
                send_telegram_notification(entry_message, 'high')
                
                return jsonify({
                    'status': 'success',
                    'action': action,
                    'symbol': symbol,
                    'amount': orders['adjusted_amount'],
                    'entry_price': orders['actual_entry'],
                    'stop_loss': stop_loss_price,
                    'take_profit': take_profit_price,
                    'ai_confidence': ai_decision.confidence if use_ai else None
                }), 200
            else:
                return jsonify({'error': 'Order execution failed'}), 500
        
        else:
            return jsonify({'error': f'Unknown action: {action}'}), 400
            
    except Exception as e:
        logging.error(f"웹훅 처리 오류: {str(e)}")
        
        error_message = f"""
❌ <b>웹훅 처리 오류</b>

<b>오류:</b> {str(e)}
⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
        """.strip()
        
        send_telegram_notification(error_message, 'error')
        return jsonify({'error': str(e)}), 500

@app.route('/ai-monitor/start', methods=['POST'])
def start_monitoring():
    """AI 모니터링 시작"""
    start_ai_monitoring()
    return jsonify({
        'status': 'success',
        'message': f'AI monitoring started with {AI_MONITOR_INTERVAL} minute intervals'
    }), 200

@app.route('/ai-monitor/stop', methods=['POST'])
def stop_monitoring():
    """AI 모니터링 중지"""
    stop_ai_monitoring()
    return jsonify({
        'status': 'success',
        'message': 'AI monitoring stopped'
    }), 200

@app.route('/ai-monitor/status', methods=['GET'])
def monitor_status():
    """AI 모니터링 상태 확인"""
    return jsonify({
        'monitoring_active': ai_monitor_running,
        'interval_minutes': AI_MONITOR_INTERVAL,
        'positions_monitored': list(current_positions.keys()),
        'total_positions': len(current_positions)
    }), 200

@app.route('/ai-monitor/force', methods=['POST'])
def force_monitor():
    """즉시 AI 모니터링 실행"""
    if not current_positions:
        return jsonify({
            'status': 'error',
            'message': 'No positions to monitor'
        }), 400
    
    monitored, exits = ai_monitoring_cycle()
    
    return jsonify({
        'status': 'success',
        'positions_monitored': monitored,
        'exit_decisions': exits
    }), 200

@app.route('/status', methods=['GET'])
def status():
    """시스템 상태 확인"""
    enabled_symbols = [s for s, c in SYMBOL_CONFIG.items() if c.get('enabled', True)]
    ai_enabled_symbols = [s for s, c in SYMBOL_CONFIG.items() if c.get('ai_validation', True)]
    ai_monitored_symbols = [s for s, c in SYMBOL_CONFIG.items() if c.get('ai_monitoring', True)]
    
    return jsonify({
        'status': 'running',
        'server_port': SERVER_PORT,
        'current_positions': current_positions,
        'telegram_enabled': ENABLE_TELEGRAM,
        'total_symbols': len(enabled_symbols),
        'ai_enabled_symbols': len(ai_enabled_symbols),
        'ai_monitored_symbols': len(ai_monitored_symbols),
        'ai_monitoring_active': ai_monitor_running,
        'ai_monitor_interval': AI_MONITOR_INTERVAL,
        'symbols': enabled_symbols,
        'timestamp': datetime.now().isoformat()
    }), 200

@app.route('/config', methods=['GET', 'POST'])
def config():
    """심볼 설정 관리"""
    global SYMBOL_CONFIG
    
    if request.method == 'GET':
        return jsonify(SYMBOL_CONFIG), 200
    
    elif request.method == 'POST':
        try:
            new_config = request.get_json()
            if not new_config:
                return jsonify({'error': 'No configuration data provided'}), 400
            
            for symbol, settings in new_config.items():
                if symbol in SYMBOL_CONFIG:
                    SYMBOL_CONFIG[symbol].update(settings)
                else:
                    SYMBOL_CONFIG[symbol] = settings
            
            logging.info(f"설정 업데이트 완료: {list(new_config.keys())}")
            
            return jsonify({
                'status': 'success',
                'updated_symbols': list(new_config.keys()),
                'config': SYMBOL_CONFIG
            }), 200
            
        except Exception as e:
            logging.error(f"설정 업데이트 실패: {str(e)}")
            return jsonify({'error': str(e)}), 500

@app.route('/ai-performance', methods=['GET'])
def ai_performance():
    """AI 거래 성과 조회"""
    try:
        conn = init_db()
        c = conn.cursor()
        
        # 전체 AI 거래 통계
        c.execute("""
            SELECT 
                COUNT(*) as total_trades,
                SUM(CASE WHEN ai_decision = 'approve' THEN 1 ELSE 0 END) as approved,
                SUM(CASE WHEN ai_decision = 'reject' THEN 1 ELSE 0 END) as rejected,
                SUM(CASE WHEN ai_decision = 'modify' THEN 1 ELSE 0 END) as modified,
                AVG(confidence) as avg_confidence
            FROM trades
            WHERE trade_type = 'AI_VALIDATION'
        """)
        
        stats = c.fetchone()
        
        # 심볼별 통계
        c.execute("""
            SELECT 
                symbol,
                COUNT(*) as trades,
                AVG(confidence) as avg_confidence,
                SUM(CASE WHEN ai_decision = 'approve' THEN 1 ELSE 0 END) as approved
            FROM trades
            WHERE trade_type = 'AI_VALIDATION'
            GROUP BY symbol
        """)
        
        symbol_stats = c.fetchall()
        
        conn.close()
        
        return jsonify({
            'total_statistics': {
                'total_trades': stats[0] or 0,
                'approved': stats[1] or 0,
                'rejected': stats[2] or 0,
                'modified': stats[3] or 0,
                'average_confidence': f"{(stats[4] or 0) * 100:.1f}%"
            },
            'symbol_statistics': [
                {
                    'symbol': row[0],
                    'trades': row[1],
                    'avg_confidence': f"{row[2] * 100:.1f}%",
                    'approved': row[3]
                } for row in symbol_stats
            ]
        }), 200
        
    except Exception as e:
        logging.error(f"AI 성과 조회 오류: {str(e)}")
        return jsonify({'error': str(e)}), 500

def initialize_bot():
    """봇 초기화"""
    logging.info(f"봇 초기화 중... (포트: {SERVER_PORT})")
    
    # 데이터베이스 초기화
    conn = init_db()
    conn.close()
    
    # AI 모니터링 자동 시작
    start_ai_monitoring()
    
    # 거래소 연결 테스트
    try:
        balance = exchange.fetch_balance()
        usdt_balance = balance['USDT']['free']
        logging.info(f"거래소 연결 성공. USDT 잔고: ${usdt_balance:,.2f}")
    except Exception as e:
        logging.error(f"거래소 연결 실패: {str(e)}")
    
    # OpenAI API 테스트
    try:
        client = OpenAI(api_key=os.getenv("DEEPSEEK_API_KEY"), base_url="https://api.deepseek.com")
        if client.api_key:
            logging.info("OpenAI API 연결 성공")
        else:
            logging.warning("OpenAI API 키가 설정되지 않았습니다. AI 기능이 제한됩니다.")
    except Exception as e:
        logging.error(f"OpenAI API 연결 실패: {str(e)}")
    
    # 활성화된 심볼 출력
    enabled_symbols = [s for s, c in SYMBOL_CONFIG.items() if c.get('enabled', True)]
    ai_symbols = [s for s, c in SYMBOL_CONFIG.items() if c.get('ai_validation', True)]
    ai_monitor_symbols = [s for s, c in SYMBOL_CONFIG.items() if c.get('ai_monitoring', True)]
    
    logging.info(f"활성화된 심볼: {len(enabled_symbols)}개")
    logging.info(f"AI 검증 활성 심볼: {len(ai_symbols)}개")
    logging.info(f"AI 모니터링 활성 심볼: {len(ai_monitor_symbols)}개")
    
    if ENABLE_TELEGRAM:
        startup_message = f"""
🚀 <b>통합 트레이딩 시스템 시작</b>

<b>서버 포트:</b> {SERVER_PORT}
<b>활성 심볼:</b> {len(enabled_symbols)}개
<b>AI 검증:</b> {len(ai_symbols)}개 심볼
<b>AI 모니터링:</b> {len(ai_monitor_symbols)}개 심볼
<b>모니터링 주기:</b> {AI_MONITOR_INTERVAL}분

✅ 시스템이 정상적으로 시작되었습니다.
🤖 AI 포지션 모니터링이 활성화되었습니다.
⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
        """.strip()
        send_telegram_notification(startup_message, 'success')

if __name__ == '__main__':
    initialize_bot()
    app.run(host='0.0.0.0', port=SERVER_PORT, debug=True)
