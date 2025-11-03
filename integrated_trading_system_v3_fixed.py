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
from pydantic import BaseModel, Field, ValidationError
import sqlite3
import numpy as np
import re

# 환경 변수 로드
load_dotenv()

# ============ 서버별 하드코딩 설정 ============
SERVER_PORT = 5000  # 여기서 포트 변경 (5000, 5001, 5002)
ENABLE_TELEGRAM = True if SERVER_PORT == 5000 else False  # 5000번 포트만 텔레그램 활성화
AI_MONITOR_INTERVAL = 5 # AI 포지션 모니터링 간격 (분)

app = Flask(__name__)
logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s - [Port:{port}] - %(levelname)s - %(message)s'.format(port=SERVER_PORT))
logger = logging.getLogger(__name__)

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
    """트레이딩 시그널 검증용 모델"""
    decision: str = Field(..., pattern="^(approve|reject|modify)$")
    modified_action: str = Field(..., pattern="^(buy|sell|hold)$")
    percentage: int = Field(..., ge=10, le=100)
    reason: str = Field(..., min_length=1)
    stop_loss_price: float = Field(..., gt=0)
    take_profit_price: float = Field(..., gt=0)
    pl_ratio: float = Field(..., ge=1.0, le=5.0)
    confidence: float = Field(..., ge=0.0, le=1.0)

class ClosePositionDecision(BaseModel):
    """청산 시그널 검증용 모델 (SL/TP 불필요)"""
    decision: str = Field(..., pattern="^(approve|reject)$")
    reason: str = Field(..., min_length=1)
    confidence: float = Field(..., ge=0.0, le=1.0)
    urgency: str = Field(..., pattern="^(immediate|soon|normal|low)$")

class PositionExitDecision(BaseModel):
    """포지션 종료 결정용 모델 - 개선 버전"""
    decision: str = Field(..., pattern="^(hold|close|partial_close)$")
    percentage: int = Field(..., ge=0, le=100)
    reason: str = Field(..., min_length=1)
    exit_type: str = Field(
        ..., 
        pattern="^(take_profit|stop_loss|trend_reversal|risk_management|time_stop|none)$"
    )
    confidence: float = Field(..., ge=0.0, le=1.0)
    urgency: str = Field(..., pattern="^(immediate|soon|watch|none)$")

# ============ 다중 종목 설정 ============
SYMBOL_CONFIG = {
    'BTC/USDT': {
        'leverage': 10,
        'position_size_percent': 30,
        'min_position_size': 10,
        'max_position_size': 100000,
        'enabled': True,
        'ai_validation': True,
        'ai_monitoring': True
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
    },
    'ASTER/USDT': {
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

# ============ AI Response Helper ============
def extract_ai_response(response):
    """
    DeepSeek Reasoner 응답에서 content 추출
    reasoning_content와 content를 모두 확인
    """
    try:
        message = response.choices[0].message
        
        # 응답 구조 로깅
        logger.debug(f"응답 구조: {dir(message)}")
        
        # content 확인
        content = getattr(message, 'content', None)
        if content and content.strip():
            logger.info(f"Content 응답 길이: {len(content)} 문자")
            return content
        
        # reasoning_content 확인 (DeepSeek Reasoner 특수 필드)
        reasoning_content = getattr(message, 'reasoning_content', None)
        if reasoning_content and reasoning_content.strip():
            logger.info(f"Reasoning content 응답 길이: {len(reasoning_content)} 문자")
            logger.warning("Content가 비어있어 reasoning_content 사용")
            return reasoning_content
        
        # 둘 다 없으면 전체 응답 로깅
        logger.error(f"응답이 비어있음. Message 객체: {message}")
        logger.error(f"전체 response: {response}")
        return None
        
    except Exception as e:
        logger.error(f"AI 응답 추출 중 오류: {str(e)}")
        logger.error(f"전체 response: {response}")
        return None

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
        logger.error(f"Error collecting market data for {symbol}: {e}")
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
        logger.error(f"Error fetching Fear and Greed Index: {e}")
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
        logger.error(f"Error fetching recent trades: {e}")
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
        logger.error("OpenAI API key is missing or invalid.")
        return None
    
    try:
        response = client.chat.completions.create(
            model="deepseek-chat",  # Chat 모델 사용 - 자연어 응답에 더 효율적
            messages=[
                {
                    "role": "system",
                    "content": """
You are an advanced AI trading analyst assistant. Your role is to analyze recent trading performance including position monitoring decisions and current market conditions to generate specific, actionable insights.

Provide clear, concise analysis in natural language.
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
            temperature=0.3,
            max_tokens=1500  # Chat 모델은 더 효율적
        )
        
        # AI 응답 추출 - 개선된 버전
        ai_response_text = extract_ai_response(response)
        
        if not ai_response_text:
            logger.error("Reflection 생성 실패: AI 응답이 비어있음")
            return None
            
        return ai_response_text
        
    except Exception as e:
        logger.error(f"Error generating reflection: {e}")
        return None

# ============ JSON 추출 헬퍼 함수 ============
def extract_json_from_text(text: str) -> str:
    """
    텍스트에서 JSON 추출 (여러 방법 시도)
    """
    if not text or not text.strip():
        return None
    
    # 방법 1: 전체가 JSON인 경우
    try:
        json.loads(text.strip())
        logger.debug("전체가 유효한 JSON")
        return text.strip()
    except json.JSONDecodeError:
        pass
    
    # 방법 2: ```json ... ``` 블록 찾기
    json_block_match = re.search(r'```json\s*\n(.*?)\n```', text, re.DOTALL)
    if json_block_match:
        extracted = json_block_match.group(1).strip()
        try:
            json.loads(extracted)
            logger.debug("```json 블록에서 JSON 추출")
            return extracted
        except json.JSONDecodeError:
            pass
    
    # 방법 3: ``` ... ``` 블록 찾기
    code_block_match = re.search(r'```\s*\n(.*?)\n```', text, re.DOTALL)
    if code_block_match:
        extracted = code_block_match.group(1).strip()
        try:
            json.loads(extracted)
            logger.debug("``` 블록에서 JSON 추출")
            return extracted
        except json.JSONDecodeError:
            pass
    
    # 방법 4: 첫 { 부터 마지막 } 까지 추출 (공격적 방법)
    first_brace = text.find('{')
    last_brace = text.rfind('}')
    if first_brace != -1 and last_brace != -1 and first_brace < last_brace:
        extracted = text[first_brace:last_brace+1]
        try:
            json.loads(extracted)
            logger.debug(f"첫/마지막 중괄호 사이에서 JSON 추출 (길이: {len(extracted)})")
            return extracted
        except json.JSONDecodeError:
            pass
    
    # 방법 5: { ... } 패턴 찾기 (가장 긴 것 우선)
    brace_matches = re.findall(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', text, re.DOTALL)
    if brace_matches:
        # 길이순으로 정렬 (긴 것이 완전한 JSON일 가능성 높음)
        brace_matches.sort(key=len, reverse=True)
        for match in brace_matches:
            try:
                json.loads(match.strip())
                logger.debug(f"{{...}} 패턴에서 JSON 추출 (길이: {len(match)})")
                return match.strip()
            except json.JSONDecodeError:
                continue
    
    logger.error("모든 JSON 추출 방법 실패")
    logger.debug(f"추출 실패한 텍스트 샘플 (처음 500자): {text[:500]}")
    return None

def create_default_hold_decision(reason: str) -> dict:
    """기본 hold 결정 생성"""
    return {
        "decision": "hold",
        "percentage": 0,
        "reason": reason,
        "exit_type": "none",
        "confidence": 0.0,
        "urgency": "none"
    }

def create_default_reject_decision(reason: str) -> dict:
    """기본 reject 결정 생성"""
    return {
        "decision": "reject",
        "modified_action": "hold",
        "percentage": 0,
        "reason": reason,
        "stop_loss_price": 0.0,
        "take_profit_price": 0.0,
        "pl_ratio": 0.0,
        "confidence": 0.0
    }

# ============ AI Position Monitoring (개선 버전) ============
def ai_monitor_position(symbol, position_info):
    """
    AI가 포지션을 모니터링하고 종료 여부 결정 - 개선 버전
    Pydantic 검증 및 에러 처리 강화
    """
    
    client = OpenAI(api_key=os.getenv("DEEPSEEK_API_KEY"), base_url="https://api.deepseek.com")
    if not client.api_key:
        logger.error("OpenAI API key is missing or invalid.")
        return None
    
    try:
        # 시장 데이터 수집
        market_data = get_market_data(symbol)
        if not market_data:
            logger.error(f"Failed to get market data for {symbol}")
            return create_default_hold_decision("시장 데이터 조회 실패")
        
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
        
        json_template = """
{
    "decision": "hold",
    "percentage": 0,
    "reason": "Strong momentum continues",
    "exit_type": "none",
    "confidence": 0.85,
    "urgency": "none"
}"""

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

**CRITICAL INSTRUCTIONS:**
1. You MUST respond with ONLY a valid JSON object
2. Do NOT include any text before or after the JSON
3. Do NOT use markdown code blocks (no ```)
4. Follow this EXACT structure:

{json_template}

**Field Requirements:**
- decision: "hold", "close", or "partial_close"
- percentage: 0 for hold, 100 for close, 25-75 for partial
- reason: detailed explanation
- exit_type: "take_profit", "stop_loss", "trend_reversal", "risk_management", "time_stop", or "none"
- confidence: 0.0 to 1.0
- urgency: "immediate", "soon", "watch", or "none"

**EXAMPLES:**

Hold:
{{
    "decision": "hold",
    "percentage": 0,
    "reason": "Strong bullish momentum, no reversal signals",
    "exit_type": "none",
    "confidence": 0.82,
    "urgency": "none"
}}

Close:
{{
    "decision": "close",
    "percentage": 100,
    "reason": "Trend reversal with bearish MACD crossover",
    "exit_type": "trend_reversal",
    "confidence": 0.88,
    "urgency": "immediate"
}}

Partial:
{{
    "decision": "partial_close",
    "percentage": 50,
    "reason": "Approaching resistance, securing partial profits",
    "exit_type": "take_profit",
    "confidence": 0.75,
    "urgency": "soon"
}}

Return ONLY the JSON object.
"""

        # AI API 호출
        logger.info(f"포지션 모니터 시작 - {symbol} {side}")
        
        response = client.chat.completions.create(
            model="deepseek-chat",  # Reasoner 대신 Chat 사용
            messages=[
                {
                    "role": "system",
                    "content": """You are a professional position manager.

CRITICAL RULES:
1. ONLY return valid JSON - no explanations, no reasoning, no markdown
2. Start your response with { and end with }
3. Follow the exact JSON schema provided
4. Be decisive about position management

Your response must be a single JSON object."""
                },
                {"role": "user", "content": prompt}
            ],
            response_format={'type': 'json_object'},
            temperature=0.1,
            max_tokens=1500  # Chat 모델은 Reasoner보다 토큰 효율적
        )
        
        # 1. 응답 추출 - 개선된 버전
        ai_response_text = extract_ai_response(response)
        
        if not ai_response_text or not ai_response_text.strip():
            logger.error("AI 응답이 비어있음 (content와 reasoning_content 모두 확인)")
            return create_default_hold_decision("AI 응답 없음")

        
        logger.info(f"AI 응답 길이: {len(ai_response_text)} 문자")
        logger.debug(f"AI 응답 내용: {ai_response_text[:500]}")
        
        # 2. JSON 추출
        json_str = extract_json_from_text(ai_response_text)
        if not json_str:
            logger.error("JSON 추출 실패")
            logger.error(f"전체 AI 응답: {ai_response_text}")
            return create_default_hold_decision("JSON 파싱 실패")
        
        logger.debug(f"추출된 JSON: {json_str}")
        
        # 3. JSON 파싱
        try:
            parsed_json = json.loads(json_str)
            logger.debug(f"JSON 파싱 성공: {parsed_json}")
        except json.JSONDecodeError as e:
            logger.error(f"JSON decode 실패: {e}")
            logger.error(f"시도한 JSON: {json_str}")
            return create_default_hold_decision(f"JSON 형식 오류: {str(e)}")
        
        # 4. Pydantic 검증
        try:
            decision = PositionExitDecision.model_validate(parsed_json)
            result = decision.model_dump()
            
            logger.info(
                f"✅ 포지션 모니터 결정: {result['decision']} "
                f"({result['percentage']}% / 신뢰도: {result['confidence']:.2f} / "
                f"긴급도: {result['urgency']})"
            )
            logger.info(f"결정 이유: {result['reason']}")
            
            # DB에 모니터링 기록 저장
            conn = init_db()
            c = conn.cursor()
            timestamp = datetime.now().isoformat()
            c.execute("""INSERT INTO trades 
                         (timestamp, symbol, trade_type, ai_decision, action, percentage, reason, 
                          entry_price, current_price, confidence, exit_type, urgency) 
                         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                      (timestamp, symbol, 'AI_MONITOR', result['decision'], 'monitor', result['percentage'], 
                       result['reason'], entry_price, current_price, result['confidence'], 
                       result['exit_type'], result['urgency']))
            conn.commit()
            conn.close()
            
            return result
            
        except ValidationError as e:
            logger.error(f"Pydantic 검증 실패:")
            for error in e.errors():
                logger.error(f"  - 필드 {error['loc']}: {error['msg']}")
            logger.error(f"검증 실패한 데이터: {parsed_json}")
            return create_default_hold_decision(f"데이터 검증 실패: {str(e.errors()[0]['msg'])}")
    
    except Exception as e:
        logger.error(f"포지션 모니터 오류: {e}", exc_info=True)
        return create_default_hold_decision(f"시스템 오류: {str(e)}")

def execute_position_exit(symbol, decision):
    """포지션 종료 실행"""
    try:
        position = current_positions.get(symbol)
        if not position:
            logger.warning(f"No position found for {symbol}")
            return False
        
        # 현재 포지션 정보
        side = position['side']
        amount = position['amount']
        
        # 종료할 수량 계산
        if decision['decision'] == 'close':
            exit_amount = amount
        elif decision['decision'] == 'partial_close':
            exit_amount = amount * (decision['percentage'] / 100)
        else:
            return False
        
        # 시장가 주문으로 포지션 종료
        if side == 'buy':
            order = exchange.create_market_sell_order(symbol, exit_amount)
        else:  # sell
            order = exchange.create_market_buy_order(symbol, exit_amount)
        
        logger.info(f"Position exit executed for {symbol}: {decision['decision']}")
        
        # 전체 종료인 경우 포지션 추적에서 제거
        if decision['decision'] == 'close':
            del current_positions[symbol]
        else:
            # 부분 종료인 경우 수량 업데이트
            current_positions[symbol]['amount'] -= exit_amount
        
        # 텔레그램 알림
        if ENABLE_TELEGRAM:
            message = f"""
🤖 <b>AI Position Exit</b>

<b>Symbol:</b> {symbol}
<b>Decision:</b> {decision['decision'].upper()}
<b>Exit Type:</b> {decision['exit_type']}
<b>Amount:</b> {exit_amount:.6f}
<b>Reason:</b> {decision['reason']}
<b>Urgency:</b> {decision['urgency']}
<b>Confidence:</b> {decision['confidence']:.1%}

⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
            """.strip()
            send_telegram_notification(message, 'high' if decision['urgency'] == 'immediate' else 'normal')
        
        return True
        
    except Exception as e:
        logger.error(f"Error executing position exit for {symbol}: {e}")
        return False

def ai_monitoring_cycle():
    """AI 모니터링 주기 실행"""
    global current_positions
    
    logger.info("=== AI Position Monitoring Cycle Start ===")
    
    monitored_count = 0
    exit_decisions = []
    
    for symbol, position in current_positions.copy().items():
        # AI 모니터링이 활성화된 심볼인지 확인
        if not SYMBOL_CONFIG.get(symbol, {}).get('ai_monitoring', True):
            continue
        
        logger.info(f"Monitoring position: {symbol}")
        
        # AI 모니터링 실행
        decision = ai_monitor_position(symbol, position)
        
        if decision:
            monitored_count += 1
            
            # 종료 결정인 경우
            if decision['decision'] in ['close', 'partial_close']:
                # 신뢰도와 긴급도 확인
                if decision['confidence'] >= 0.6 or decision['urgency'] == 'immediate':
                    success = execute_position_exit(symbol, decision)
                    if success:
                        exit_decisions.append({
                            'symbol': symbol,
                            'decision': decision['decision'],
                            'reason': decision['reason']
                        })
                else:
                    logger.info(f"Exit decision for {symbol} not executed due to low confidence ({decision['confidence']:.1%})")
        
        # API 제한을 위한 짧은 대기
        time.sleep(2)
    
    # 모니터링 결과 요약
    if monitored_count > 0:
        logger.info(f"✅ AI monitoring cycle completed: {monitored_count} positions monitored")
        if exit_decisions:
            logger.info(f"Exit decisions executed: {exit_decisions}")
    else:
        logger.info("No positions to monitor")
    
    logger.info("=== AI Position Monitoring Cycle End ===")
    
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
                    logger.info("No positions to monitor")
                
                # 다음 모니터링까지 대기
                time.sleep(AI_MONITOR_INTERVAL * 60)
                
            except Exception as e:
                logger.error(f"Error in AI monitoring loop: {e}", exc_info=True)
                time.sleep(60)  # 오류 발생 시 1분 대기
    
    if not ai_monitor_running:
        ai_monitor_thread = threading.Thread(target=monitor_loop, daemon=True)
        ai_monitor_thread.start()
        logger.info(f"✅ AI position monitoring started ({AI_MONITOR_INTERVAL}-minute intervals)")

def stop_ai_monitoring():
    """AI 모니터링 중지"""
    global ai_monitor_running
    ai_monitor_running = False
    logger.info("AI position monitoring stopped")

# ============ AI Decision Making (개선 버전) ============
def ai_validate_signal(symbol, action, market_data, recent_trades_df):
    """
    AI를 사용하여 거래 신호를 검증 - 개선 버전
    Pydantic 검증 및 에러 처리 강화
    """
    
    client = OpenAI(api_key=os.getenv("DEEPSEEK_API_KEY"), base_url="https://api.deepseek.com")
    if not client.api_key:
        logger.error("OpenAI API key is missing or invalid.")
        return None
    
    try:
        # Reflection 생성
        reflection = generate_reflection(recent_trades_df, market_data)
        
        # Technical Indicators 준비
        df_5min = market_data['df_5min']
        df_hourly = market_data['df_hourly'] 
        df_4h = market_data['df_4h']

        # close_position 액션 처리 (별도 로직)
        if action in ['close', 'close_position']:
            json_template = """
{
    "decision": "approve",
    "reason": "Favorable exit conditions confirmed",
    "confidence": 0.75,
    "urgency": "immediate"
}"""

            prompt = f"""
You are an expert crypto trading AI validator. Analyze whether to approve closing the position for {symbol}.

**CURRENT MARKET CONDITIONS:**
- Symbol: {symbol}
- Current Price: {market_data['current_price']:.2f}
- Action: Close Position

**TECHNICAL INDICATORS:**

**5-Minute Chart (Latest):**
- RSI(14): {df_5min['rsi'].iloc[-1]:.2f}
- MACD: {df_5min['macd'].iloc[-1]:.2f}
- Bollinger: Middle={df_5min['bb_bbm'].iloc[-1]:.2f}, Upper={df_5min['bb_bbh'].iloc[-1]:.2f}, Lower={df_5min['bb_bbl'].iloc[-1]:.2f}
- ADX: {df_5min['adx'].iloc[-1]:.2f}
- CMF: {df_5min['cmf'].iloc[-1]:.2f}

**1-Hour Chart (Latest):**
- RSI(14): {df_hourly['rsi'].iloc[-1]:.2f}
- MACD: {df_hourly['macd'].iloc[-1]:.2f}
- ADX: {df_hourly['adx'].iloc[-1]:.2f}

**4-Hour Chart (Latest):**
- RSI(14): {df_4h['rsi'].iloc[-1]:.2f}
- ADX: {df_4h['adx'].iloc[-1]:.2f}

**RECENT PERFORMANCE REFLECTION:**
{reflection if reflection else 'No previous trading data available'}

**VALIDATION CRITERIA:**
Consider if this is a good time to close the position based on:
- Current market momentum
- Technical indicator signals
- Recent price action
- Risk management perspective

**CRITICAL INSTRUCTIONS:**
1. You MUST respond with ONLY a valid JSON object
2. Do NOT include any text before or after the JSON
3. Do NOT use markdown code blocks (no ```)
4. Follow this EXACT structure:

{json_template}

**Field Requirements:**
- decision: must be "approve" or "reject"
- reason: string explaining the decision
- confidence: number between 0.0 and 1.0
- urgency: "immediate", "soon", "normal", or "low"

Return ONLY the JSON object. Start with {{ and end with }}
"""
            
            # AI API 호출
            logger.info(f"AI 청산 시그널 검증 시작 - {symbol}")
            
            response = client.chat.completions.create(
                model="deepseek-chat",
                messages=[
                    {
                        "role": "system",
                        "content": """You are a professional crypto trading AI validator for position exits.

CRITICAL RULES:
1. ONLY return valid JSON - no explanations, no reasoning, no markdown
2. Start your response with { and end with }
3. Follow the exact JSON schema provided
4. Be decisive about exit decisions

Your response must be a single JSON object."""
                    },
                    {"role": "user", "content": prompt}
                ],
                response_format={'type': 'json_object'},
                temperature=0.1,
                max_tokens=1000
            )
            
            # 응답 추출
            ai_response_text = extract_ai_response(response)
            
            if not ai_response_text or not ai_response_text.strip():
                logger.error("AI 응답이 비어있음")
                return {
                    "decision": "reject",
                    "reason": "AI 응답 없음",
                    "confidence": 0.0,
                    "urgency": "low"
                }
            
            logger.info(f"AI 응답 길이: {len(ai_response_text)} 문자")
            
            # JSON 추출
            json_str = extract_json_from_text(ai_response_text)
            if not json_str:
                logger.error("JSON 추출 실패")
                return {
                    "decision": "reject",
                    "reason": "JSON 파싱 실패",
                    "confidence": 0.0,
                    "urgency": "low"
                }
            
            # JSON 파싱
            try:
                parsed_json = json.loads(json_str)
            except json.JSONDecodeError as e:
                logger.error(f"JSON decode 실패: {e}")
                return {
                    "decision": "reject",
                    "reason": f"JSON 형식 오류: {str(e)}",
                    "confidence": 0.0,
                    "urgency": "low"
                }
            
            # Pydantic 검증
            try:
                decision = ClosePositionDecision.model_validate(parsed_json)
                result = decision.model_dump()
                
                logger.info(
                    f"✅ AI 청산 시그널 검증 완료: {result['decision'].upper()} "
                    f"(신뢰도: {result['confidence']:.2%})"
                )
                logger.info(f"결정 이유: {result['reason']}")
                
                # 거래 기록 저장
                conn = init_db()
                c = conn.cursor()
                timestamp = datetime.now().isoformat()
                c.execute("""INSERT INTO trades 
                             (timestamp, symbol, trade_type, ai_decision, action, reason, 
                              current_price, confidence) 
                             VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                          (timestamp, symbol, 'AI_VALIDATION', result['decision'], 'close_position', 
                           result['reason'], market_data['current_price'], result['confidence']))
                conn.commit()
                conn.close()
                
                return result
                
            except ValidationError as e:
                logger.error(f"Pydantic 검증 실패:")
                for error in e.errors():
                    logger.error(f"  - 필드 {error['loc']}: {error['msg']}")
                return {
                    "decision": "reject",
                    "reason": f"데이터 검증 실패: {str(e.errors()[0]['msg'])}",
                    "confidence": 0.0,
                    "urgency": "low"
                }

        # 일반 buy/sell 액션 처리
        # JSON 템플릿을 프롬프트에 명시
        json_template = """
{
    "decision": "approve",
    "modified_action": "sell",
    "percentage": 30,
    "reason": "Strong bearish indicators",
    "stop_loss_price": 186.42,
    "take_profit_price": 166.11,
    "pl_ratio": 2.5,
    "confidence": 0.75
}"""

        # 프롬프트 구성
        prompt = f"""
You are an expert crypto trading AI validator. You need to validate trading signals using technical analysis and return ONLY valid JSON.

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
- RSI is not overbought (preferably < 80)
- MACD shows bullish momentum or crossover
- Price is near support levels or breaking resistance
- Volume and momentum indicators confirm

For SELL signals, validate if:  
- RSI is not oversold (preferably > 20)
- MACD shows bearish momentum or crossover
- Price is near resistance levels or breaking support
- Volume and momentum indicators confirm

**DECISION REQUIRED:**
Based on the technical indicators and market conditions, should this {action} signal be:
1. APPROVED - Execute the trade as proposed
2. REJECTED - Do not execute, conditions unfavorable
3. MODIFIED - Execute with adjusted parameters

**CRITICAL INSTRUCTIONS:**
1. You MUST respond with ONLY a valid JSON object
2. Do NOT include any text before or after the JSON
3. Do NOT use markdown code blocks (no ```)
4. Follow this EXACT structure:

{json_template}

**Field Requirements:**
- decision: must be "approve", "reject", or "modify"
- modified_action: must be "buy", "sell", or "hold"
- percentage: integer between 10 and 100
- reason: string explaining the decision
- stop_loss_price: number (price level)
- take_profit_price: number (price level)
- pl_ratio: number between 1.0 and 5.0
- confidence: number between 0.0 and 1.0

Return ONLY the JSON object. Start with {{ and end with }}

Provide specific reasoning based on the indicators and suggest optimal entry, stop loss, and take profit levels.
"""
        
        # AI API 호출
        logger.info(f"AI 시그널 검증 시작 - {symbol} {action}")
        
        response = client.chat.completions.create(
            model="deepseek-chat",  # Reasoner 대신 Chat 사용 - JSON 포맷을 더 잘 따름
            messages=[
                {
                    "role": "system",
                    "content": """You are a professional crypto trading AI validator.

CRITICAL RULES:
1. ONLY return valid JSON - no explanations, no reasoning, no markdown
2. Start your response with { and end with }
3. Follow the exact JSON schema provided
4. Be decisive and specific in your analysis

Your response must be a single JSON object."""
                },
                {"role": "user", "content": prompt}
            ],
            response_format={'type': 'json_object'},
            temperature=0.1,
            max_tokens=1500  # Chat 모델은 Reasoner보다 토큰 효율적
        )
        
        # 1. 응답 추출 - 개선된 버전
        ai_response_text = extract_ai_response(response)
        
        if not ai_response_text or not ai_response_text.strip():
            logger.error("AI 응답이 비어있음 (content와 reasoning_content 모두 확인)")
            return create_default_reject_decision("AI 응답 없음")
        
        logger.info(f"AI 응답 길이: {len(ai_response_text)} 문자")
        logger.debug(f"AI 응답 내용: {ai_response_text[:500]}")

        
        # 2. JSON 추출
        json_str = extract_json_from_text(ai_response_text)
        if not json_str:
            logger.error("JSON 추출 실패")
            logger.error(f"전체 AI 응답: {ai_response_text}")
            return create_default_reject_decision("JSON 파싱 실패")
        
        logger.debug(f"추출된 JSON: {json_str}")
        
        # 3. JSON 파싱
        try:
            parsed_json = json.loads(json_str)
            logger.debug(f"JSON 파싱 성공: {parsed_json}")
        except json.JSONDecodeError as e:
            logger.error(f"JSON decode 실패: {e}")
            logger.error(f"시도한 JSON: {json_str}")
            return create_default_reject_decision(f"JSON 형식 오류: {str(e)}")
        
        # 4. Pydantic 검증
        try:
            decision = TradingDecision.model_validate(parsed_json)
            result = decision.model_dump()
            
            logger.info(
                f"✅ AI 시그널 검증 완료: {result['decision'].upper()} "
                f"(신뢰도: {result['confidence']:.2%})"
            )
            logger.info(f"결정 이유: {result['reason']}")
            
            # 거래 기록 저장
            conn = init_db()
            c = conn.cursor()
            timestamp = datetime.now().isoformat()
            c.execute("""INSERT INTO trades 
                         (timestamp, symbol, trade_type, ai_decision, action, percentage, reason, 
                          current_price, stop_loss, take_profit, pl_ratio, confidence, reflection) 
                         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                      (timestamp, symbol, 'AI_VALIDATION', result['decision'], action, result['percentage'], 
                       result['reason'], market_data['current_price'], result['stop_loss_price'], 
                       result['take_profit_price'], result['pl_ratio'], result['confidence'], reflection))
            conn.commit()
            conn.close()
            
            return result
            
        except ValidationError as e:
            logger.error(f"Pydantic 검증 실패:")
            for error in e.errors():
                logger.error(f"  - 필드 {error['loc']}: {error['msg']}")
            logger.error(f"검증 실패한 데이터: {parsed_json}")
            return create_default_reject_decision(f"데이터 검증 실패: {str(e.errors()[0]['msg'])}")
    
    except Exception as e:
        logger.error(f"AI 시그널 검증 오류: {e}", exc_info=True)
        return create_default_reject_decision(f"시스템 오류: {str(e)}")

# ============ Trading Functions ============
def send_telegram_notification(message, importance='normal'):
    """텔레그램 알림 전송"""
    if not ENABLE_TELEGRAM:
        return
        
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_IDS:
        logger.warning("텔레그램 설정이 완료되지 않았습니다.")
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
                logger.error(f"텔레그램 알림 전송 실패 (chat_id: {chat_id}): {str(e)}")

def test_telegram():
    """텔레그램 알림 테스트 - 개선된 에러 처리"""
    if not ENABLE_TELEGRAM:
        return False, "Telegram is disabled on this server"
    
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_IDS:
        return False, "Telegram configuration is incomplete"
    
    test_message = """<b>텔레그램 봇 테스트</b>

✅ 봇이 정상적으로 작동하고 있습니다!

이 메시지를 받으셨다면 설정이 올바르게 되어 있습니다.
⏰ """ + datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    try:
        send_telegram_notification(test_message, 'normal')
        return True, {"status": "success", "message": "Test message sent successfully"}
    except Exception as e:
        return False, f"Error: {str(e)}"

def verify_telegram_bot():
    """텔레그램 봇 연결 확인"""
    if not TELEGRAM_BOT_TOKEN:
        return {
            "success": False,
            "message": "Bot token is not configured"
        }
    
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getMe"
        response = requests.get(url, timeout=10)
        
        if response.status_code == 200:
            bot_info = response.json().get('result', {})
            return {
                "success": True,
                "message": "Bot connection successful",
                "bot_info": bot_info
            }
        else:
            return {
                "success": False,
                "message": "Bot connection failed",
                "status_code": response.status_code
            }
    except Exception as e:
        return {
            "success": False,
            "message": f"Connection verification error: {str(e)}"
        }

def send_custom_telegram_message(message, parse_mode='HTML', importance='normal'):
    """커스텀 텔레그램 메시지 전송"""
    if not ENABLE_TELEGRAM:
        return {"success": False, "message": "Telegram is disabled"}
    
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_IDS:
        return {"success": False, "message": "Telegram configuration is incomplete"}
    
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
    
    success_count = 0
    results = []
    
    for chat_id in TELEGRAM_CHAT_IDS:
        if chat_id:
            try:
                payload = {
                    'chat_id': chat_id.strip(),
                    'text': formatted_message,
                    'parse_mode': parse_mode
                }
                response = requests.post(url, json=payload, timeout=10)
                response.raise_for_status()
                success_count += 1
                results.append({
                    "chat_id": chat_id,
                    "success": True,
                    "response": response.json()
                })
            except Exception as e:
                logger.error(f"텔레그램 메시지 전송 실패 (chat_id: {chat_id}): {str(e)}")
                results.append({
                    "chat_id": chat_id,
                    "success": False,
                    "error": str(e)
                })
    
    return {
        "success": success_count > 0,
        "message": f"{success_count}/{len(TELEGRAM_CHAT_IDS)}개 채팅방에 전송 성공",
        "total": len(TELEGRAM_CHAT_IDS),
        "success_count": success_count,
        "results": results
    }

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
        logger.info(f"{symbol} 레버리지 설정: {leverage}x")
        return leverage
    except Exception as e:
        logger.error(f"{symbol} 레버리지 설정 실패: {str(e)}")
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
        
        logger.info(f"포지션 진입 완료 - {symbol} {action} @ ${entry_price:.2f}, 수량: {amount}")
        
        # SL/TP 주문 설정
        time.sleep(1)
        
        # 스탑로스 주문
        sl_side = 'sell' if action == 'buy' else 'buy'
        sl_order = exchange.create_order(
            symbol=symbol,
            type='stop_market',
            side=sl_side,
            amount=amount,
            params={
                'stopPrice': stop_loss_price,
                'workingType': 'MARK_PRICE',
                'reduceOnly': True
            }
        )
        
        logger.info(f"스탑로스 주문 완료 - {symbol} @ ${stop_loss_price:.2f}")
        
        # 테이크프로핏 주문
        tp_side = 'sell' if action == 'buy' else 'buy'
        tp_order = exchange.create_order(
            symbol=symbol,
            type='take_profit_market',
            side=tp_side,
            amount=amount,
            params={
                'stopPrice': take_profit_price,
                'workingType': 'MARK_PRICE',
                'reduceOnly': True
            }
        )
        
        logger.info(f"테이크프로핏 주문 완료 - {symbol} @ ${take_profit_price:.2f}")
        
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
        logger.error(f"주문 실행 오류: {str(e)}", exc_info=True)
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
                        logger.info(f"{symbol} 트레일링 스탑 활성화: {current_price}")
                    
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
                        logger.info(f"{symbol} 트레일링 스탑 활성화: {current_price}")
                    
                    if activated:
                        if current_price < lowest_price:
                            lowest_price = current_price
                            new_sl = lowest_price * (1 + trailing_percent/100)
                            update_stop_loss(symbol, new_sl, amount)
                
                time.sleep(30)  # 30초마다 체크
                
            except Exception as e:
                logger.error(f"트레일링 스탑 모니터링 오류 ({symbol}): {str(e)}")
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
            if order['type'] == 'stop' or order['type'] == 'stop_market':
                exchange.cancel_order(order['id'], symbol)
                time.sleep(1)
        
        # 새로운 스탑로스 주문 생성
        position = current_positions.get(symbol)
        if position:
            sl_side = 'sell' if position['side'] == 'buy' else 'buy'
            new_order = exchange.create_order(
                symbol=symbol,
                type='stop_market',
                side=sl_side,
                amount=amount,
                params={
                    'stopPrice': new_sl_price,
                    'workingType': 'MARK_PRICE',
                    'reduceOnly': True
                }
            )

            logger.info(f"{symbol} 스탑로스 업데이트: {new_sl_price}")
            
    except Exception as e:
        logger.error(f"스탑로스 업데이트 오류 ({symbol}): {str(e)}")

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
    """TradingView 웹훅 수신 및 처리 - 개선 버전"""
    try:
        data = request.get_json()
        
        # 기본 검증
        if not data:
            return jsonify({'error': 'No data received'}), 400
        
        action = data.get('action')
        symbol = data.get('symbol', 'BTC/USDT')
        message = data if data else json.dumps(data, ensure_ascii=False)
        
        # 심볼 매핑 테이블 (정규화 전에 수행!)
        symbol_mapping = {
            'BTCUSDT': 'BTC/USDT',
            'BTCUSDT.P': 'BTC/USDT',
            'SAHARAUSDT': 'SAHARA/USDT',
            'SAHARAUSDT.P': 'SAHARA/USDT',
            'ETHUSDT': 'ETH/USDT',
            'ETHUSDT.P': 'ETH/USDT',
            'RESOLVUSDT': 'RESOLV/USDT',
            'RESOLVUSDT.P': 'RESOLV/USDT',
            'BIOUSDT': 'BIO/USDT',
            'BIOUSDT.P': 'BIO/USDT',
            'UNIUSDT': 'UNI/USDT',
            'UNIUSDT.P': 'UNI/USDT',
            'PENGUUSDT': 'PENGU/USDT',
            'PENGUUSDT.P': 'PENGU/USDT',
            'UMAUSDT': 'UMA/USDT',
            'UMAUSDT.P': 'UMA/USDT',
            'COMPUSDT': 'COMP/USDT',
            'COMPUSDT.P': 'COMP/USDT',
            'XLMUSDT': 'XLM/USDT',
            'XLMUSDT.P': 'XLM/USDT',
            'DOTUSDT': 'DOT/USDT',
            'DOTUSDT.P': 'DOT/USDT',
            'ENAUSDT': 'ENA/USDT',
            'ENAUSDT.P': 'ENA/USDT',
            'RLCUSDT': 'RLC/USDT',
            'RLCUSDT.P': 'RLC/USDT',
            'ETHFIUSDT': 'ETHFI/USDT',
            'ETHFIUSDT.P': 'ETHFI/USDT',
            'SOLUSDT': 'SOL/USDT',
            'SOLUSDT.P': 'SOL/USDT',
            'PYTHUSDT': 'PYTH/USDT',
            'PYTHUSDT.P': 'PYTH/USDT',
            'LINKUSDT': 'LINK/USDT',
            'LINKUSDT.P': 'LINK/USDT',
            'ADAUSDT': 'ADA/USDT',
            'ADAUSDT.P': 'ADA/USDT',
            'XRPUSDT': 'XRP/USDT',
            'XRPUSDT.P': 'XRP/USDT',
            'BNBUSDT': 'BNB/USDT',
            'BNBUSDT.P': 'BNB/USDT',
            'DOGEUSDT': 'DOGE/USDT',
            'DOGEUSDT.P': 'DOGE/USDT',
            'ACHUSDT': 'ACH/USDT',
            'ACHUSDT.P': 'ACH/USDT',
            'CRVUSDT': 'CRV/USDT',
            'CRVUSDT.P': 'CRV/USDT',
            'RONINUSDT': 'RONIN/USDT',
            'RONINUSDT.P': 'RONIN/USDT',
            'BCHUSDT': 'BCH/USDT',
            'BCHUSDT.P': 'BCH/USDT',
            'LSKUSDT': 'LSK/USDT',
            'LSKUSDT.P': 'LSK/USDT',
            'HBARUSDT': 'HBAR/USDT',
            'HBARUSDT.P': 'HBAR/USDT',
            'AGLDUSDT': 'AGLD/USDT',
            'AGLDUSDT.P': 'AGLD/USDT',
            'ONDOUSDT': 'ONDO/USDT',
            'ONDOUSDT.P': 'ONDO/USDT',
            'HOMEUSDT': 'HOME/USDT',
            'HOMEUSDT.P': 'HOME/USDT',
            'TRXUSDT': 'TRX/USDT',
            'TRXUSDT.P': 'TRX/USDT',
            'ASTERUSDT': 'ASTER/USDT',            
            'ASTERUSDT.P': 'ASTER/USDT'         
        }
        
        # 심볼 매핑 적용
        if symbol in symbol_mapping:
            symbol = symbol_mapping[symbol]
        # 매핑이 없는 경우만 정규화
        elif not symbol.endswith('/USDT'):
            # .P 제거 후 정규화
            clean_symbol = symbol.replace('.P', '').replace('.p', '')
            if 'USDT' in clean_symbol:
                base = clean_symbol.replace('USDT', '')
                symbol = f"{base}/USDT"
            else:
                symbol = f"{clean_symbol}/USDT"
        
        # 심볼 설정 확인
        if symbol not in SYMBOL_CONFIG:
            return jsonify({'error': f'Symbol {symbol} not configured'}), 400
        
        if not SYMBOL_CONFIG[symbol].get('enabled', True):
            return jsonify({'error': f'Symbol {symbol} is disabled'}), 400
        
        logger.info(f"웹훅 수신 - 심볼: {symbol}, 액션: {action}, 메시지: {message}")
        
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
            
            # AI 검증 (close_position 포함)
            ai_decision = ai_validate_signal(symbol, action, market_data, recent_trades)
            
            if not ai_decision:
                return jsonify({'error': 'AI validation failed'}), 500
            
            # close_position 액션 처리
            if action in ['close', 'close_position']:
                # AI 결정에 따른 처리
                if ai_decision['decision'] == 'reject':
                    message = f"""
⚠️ <b>AI 청산 신호 거부</b>

<b>심볼:</b> {symbol}
<b>원래 신호:</b> CLOSE POSITION
<b>AI 결정:</b> REJECT
<b>신뢰도:</b> {ai_decision['confidence']:.1%}
<b>긴급도:</b> {ai_decision.get('urgency', 'N/A')}
<b>이유:</b> {ai_decision['reason']}

⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
                    """.strip()
                    send_telegram_notification(message, 'warning')
                    return jsonify({
                        'status': 'rejected',
                        'reason': ai_decision['reason'],
                        'confidence': ai_decision['confidence']
                    }), 200
                
                # AI가 승인한 경우 포지션 청산 실행
                try:
                    positions = exchange.fetch_positions([symbol])
                    closed_positions = []
                    
                    for position in positions:
                        if float(position['contracts']) != 0:
                            close_side = 'sell' if position['side'] == 'long' else 'buy'
                            close_amount = abs(float(position['contracts']))
                            
                            close_order = exchange.create_market_order(symbol, close_side, close_amount)
                            closed_positions.append({
                                'side': position['side'],
                                'amount': close_amount,
                                'entry_price': float(position['entryPrice'])
                            })
                            
                            # 현재가 조회
                            ticker = exchange.fetch_ticker(symbol)
                            current_price = ticker['last']
                            
                            # PnL 계산
                            if position['side'] == 'long':
                                pnl_percent = ((current_price - float(position['entryPrice'])) / float(position['entryPrice'])) * 100
                            else:
                                pnl_percent = ((float(position['entryPrice']) - current_price) / float(position['entryPrice'])) * 100
                            
                            message = f"""
✅ <b>포지션 청산 완료 (AI 승인)</b>

<b>심볼:</b> {symbol}
<b>방향:</b> {'🟢 롱' if position['side'] == 'long' else '🔴 숏'}
<b>진입가:</b> ${float(position['entryPrice']):,.2f}
<b>청산가:</b> ${current_price:,.2f}
<b>청산 수량:</b> {close_amount:.4f}
<b>수익률:</b> {pnl_percent:+.2f}%
<b>청산 사유:</b> {data.get('exit_reason', 'Manual close')}

<b>AI 검증:</b>
• 신뢰도: {ai_decision['confidence']:.1%}
• 긴급도: {ai_decision.get('urgency', 'N/A')}
• 이유: {ai_decision['reason']}

⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
                            """.strip()
                            send_telegram_notification(message, 'success')
                            
                            # 포지션 추적에서 제거
                            if symbol in current_positions:
                                del current_positions[symbol]
                    
                    if closed_positions:
                        return jsonify({
                            'status': 'closed',
                            'symbol': symbol,
                            'closed_positions': closed_positions,
                            'ai_confidence': ai_decision['confidence']
                        }), 200
                    else:
                        return jsonify({
                            'status': 'no_position',
                            'message': f'No open position found for {symbol}'
                        }), 200
                        
                except Exception as e:
                    logger.error(f"포지션 청산 오류: {str(e)}", exc_info=True)
                    error_message = f"""
❌ <b>포지션 청산 오류</b>

<b>심볼:</b> {symbol}
<b>오류:</b> {str(e)}
⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
                    """.strip()
                    send_telegram_notification(error_message, 'error')
                    return jsonify({'error': str(e)}), 500
            
            # buy/sell 액션 처리
            # AI 결정에 따른 처리
            if ai_decision['decision'] == 'reject':
                message = f"""
⚠️ <b>AI 신호 거부</b>

<b>심볼:</b> {symbol}
<b>원래 신호:</b> {action.upper()}
<b>AI 결정:</b> REJECT
<b>신뢰도:</b> {ai_decision['confidence']:.1%}
<b>이유:</b> {ai_decision['reason']}

⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
                """.strip()
                send_telegram_notification(message, 'warning')
                return jsonify({
                    'status': 'rejected',
                    'reason': ai_decision['reason'],
                    'confidence': ai_decision['confidence']
                }), 200
            
            elif ai_decision['decision'] == 'modify':
                # AI가 수정한 매매 신호 사용
                action = ai_decision['modified_action']
                if action == 'hold':
                    return jsonify({'status': 'hold', 'reason': ai_decision['reason']}), 200
            
            # AI가 승인하거나 수정한 경우 거래 실행
            stop_loss_price = ai_decision['stop_loss_price']
            take_profit_price = ai_decision['take_profit_price']
            pl_ratio = ai_decision['pl_ratio']
            position_percent = ai_decision['percentage']
            
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
        
        # 거래 실행 (buy/sell만)
        if action in ['buy', 'sell']:
            # 잔고 확인
            balance_info = exchange.fetch_balance()
            usdt_balance = balance_info['USDT']['free']
            
            # 포지션 크기 계산
            position_size = usdt_balance * (position_percent / 100)
            
            # 레버리지 설정
            leverage = set_leverage(symbol)
            if not leverage:
                error_msg = f"""
❌ <b>레버리지 설정 실패</b>

<b>심볼:</b> {symbol}
⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
                """.strip()
                send_telegram_notification(error_msg, 'error')
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
                    entry_message += f"\n<b>AI 신뢰도:</b> {ai_decision['confidence']:.1%}"
                
                send_telegram_notification(entry_message, 'high')
                
                return jsonify({
                    'status': 'success',
                    'action': action,
                    'symbol': symbol,
                    'amount': orders['adjusted_amount'],
                    'entry_price': orders['actual_entry'],
                    'stop_loss': stop_loss_price,
                    'take_profit': take_profit_price,
                    'ai_confidence': ai_decision['confidence'] if use_ai else None
                }), 200
            else:
                error_msg = f"""
❌ <b>주문 실행 실패</b>

<b>심볼:</b> {symbol}
<b>액션:</b> {action.upper()}
⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
                """.strip()
                send_telegram_notification(error_msg, 'error')
                return jsonify({'error': 'Order execution failed'}), 500
        
        else:
            return jsonify({'error': f'Unknown action: {action}'}), 400
            
    except Exception as e:
        logger.error(f"웹훅 처리 오류: {str(e)}", exc_info=True)
        
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
            
            logger.info(f"설정 업데이트 완료: {list(new_config.keys())}")
            
            return jsonify({
                'status': 'success',
                'updated_symbols': list(new_config.keys()),
                'config': SYMBOL_CONFIG
            }), 200
            
        except Exception as e:
            logger.error(f"설정 업데이트 실패: {str(e)}")
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
        logger.error(f"AI 성과 조회 오류: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/test-telegram', methods=['POST'])
def test_telegram_endpoint():
    """텔레그램 테스트 메시지 전송 엔드포인트"""
    try:
        success, result = test_telegram()
        
        if success:
            return jsonify(result), 200
        else:
            return jsonify({'error': result}), 400
            
    except Exception as e:
        logger.error(f"텔레그램 테스트 오류: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/telegram/verify', methods=['GET'])
def verify_telegram_endpoint():
    """텔레그램 봇 연결 확인 엔드포인트"""
    try:
        result = verify_telegram_bot()
        
        if result['success']:
            return jsonify(result), 200
        else:
            return jsonify(result), 400
            
    except Exception as e:
        logger.error(f"텔레그램 봇 확인 오류: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/telegram/send', methods=['POST'])
def send_telegram_endpoint():
    """커스텀 텔레그램 메시지 전송 엔드포인트"""
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        message = data.get('message', '')
        parse_mode = data.get('parse_mode', 'HTML')
        importance = data.get('importance', 'normal')
        
        if not message:
            return jsonify({'error': 'Message is required'}), 400
        
        result = send_custom_telegram_message(message, parse_mode, importance)
        
        if result['success']:
            return jsonify(result), 200
        else:
            return jsonify(result), 400
            
    except Exception as e:
        logger.error(f"텔레그램 메시지 전송 오류: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/trades', methods=['GET'])
def get_trades():
    """거래 히스토리 조회 엔드포인트"""
    try:
        limit = request.args.get('limit', 100, type=int)
        symbol = request.args.get('symbol', None)
        trade_type = request.args.get('trade_type', None)
        
        conn = init_db()
        c = conn.cursor()
        
        query = "SELECT * FROM trades WHERE 1=1"
        params = []
        
        if symbol:
            query += " AND symbol = ?"
            params.append(symbol)
        
        if trade_type:
            query += " AND trade_type = ?"
            params.append(trade_type)
        
        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)
        
        c.execute(query, params)
        
        columns = [desc[0] for desc in c.description]
        trades = [dict(zip(columns, row)) for row in c.fetchall()]
        
        conn.close()
        
        return jsonify({
            'success': True,
            'count': len(trades),
            'trades': trades
        }), 200
        
    except Exception as e:
        logger.error(f"거래 조회 오류: {str(e)}")
        return jsonify({'error': str(e)}), 500

def initialize_bot():
    """봇 초기화"""
    logger.info(f"봇 초기화 중... (포트: {SERVER_PORT})")
    
    # 데이터베이스 초기화
    conn = init_db()
    conn.close()
    
    # AI 모니터링 자동 시작
    start_ai_monitoring()
    
    # 거래소 연결 테스트
    try:
        balance = exchange.fetch_balance()
        usdt_balance = balance['USDT']['free']
        logger.info(f"거래소 연결 성공. USDT 잔고: ${usdt_balance:,.2f}")
    except Exception as e:
        logger.error(f"거래소 연결 실패: {str(e)}")
    
    # OpenAI API 테스트
    try:
        client = OpenAI(api_key=os.getenv("DEEPSEEK_API_KEY"), base_url="https://api.deepseek.com")
        if client.api_key:
            logger.info("OpenAI API 연결 성공")
        else:
            logger.warning("OpenAI API 키가 설정되지 않았습니다. AI 기능이 제한됩니다.")
    except Exception as e:
        logger.error(f"OpenAI API 연결 실패: {str(e)}")
    
    # 활성화된 심볼 출력
    enabled_symbols = [s for s, c in SYMBOL_CONFIG.items() if c.get('enabled', True)]
    ai_symbols = [s for s, c in SYMBOL_CONFIG.items() if c.get('ai_validation', True)]
    ai_monitor_symbols = [s for s, c in SYMBOL_CONFIG.items() if c.get('ai_monitoring', True)]
    
    logger.info(f"활성화된 심볼: {len(enabled_symbols)}개")
    logger.info(f"AI 검증 활성 심볼: {len(ai_symbols)}개")
    logger.info(f"AI 모니터링 활성 심볼: {len(ai_monitor_symbols)}개")
    
    if ENABLE_TELEGRAM:
        startup_message = f"""
🚀 <b>통합 트레이딩 시스템 v3.2 시작</b>

<b>서버 포트:</b> {SERVER_PORT}
<b>활성 심볼:</b> {len(enabled_symbols)}개
<b>AI 검증:</b> {len(ai_symbols)}개 심볼
<b>AI 모니터링:</b> {len(ai_monitor_symbols)}개 심볼
<b>모니터링 주기:</b> {AI_MONITOR_INTERVAL}분

✅ 시스템이 정상적으로 시작되었습니다.
🤖 AI 포지션 모니터링이 활성화되었습니다.
🔧 close_position도 AI 검증을 거치도록 개선
📊 포지션 진입/청산 알림 강화

⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
        """.strip()
        send_telegram_notification(startup_message, 'success')

if __name__ == '__main__':
    initialize_bot()
    app.run(host='0.0.0.0', port=SERVER_PORT, debug=False)
