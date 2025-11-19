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

# ============ 다중 유저 설정 ============
USER_CONFIGS = {
    'USER1': {
        'name': 'Mingu (Primary)',
        'api_key_env': 'BINANCE_API_KEY',
        'secret_key_env': 'BINANCE_SECRET_KEY',
        'is_primary': True,  # AI 검증, DB, 텔레그램
    },
    'USER2': {
        'name': 'Hyun',
        'api_key_env': 'BINANCE_API_KEY_HYUN',
        'secret_key_env': 'BINANCE_SECRET_KEY_HYUN',
        'is_primary': False,  # 주문만 실행
    }
    # 'USER3': {
    #     'name': 'User 3',
    #     'api_key_env': 'BINANCE_API_KEY_USER3',
    #     'secret_key_env': 'BINANCE_SECRET_KEY_USER3',
    #     'is_primary': False,  # 주문만 실행
    # }
}

SERVER_PORT = 5000  # 하나의 서버에서 모든 유저 관리
ENABLE_TELEGRAM = True  # Primary User가 텔레그램 관리
AI_MONITOR_INTERVAL = 5  # AI 포지션 모니터링 간격 (분)

app = Flask(__name__)
logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s - [Multi-User Server] - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Flask 로깅 레벨 조정
import logging as flask_logging
flask_logging.getLogger('werkzeug').setLevel(flask_logging.WARNING)

# ============ 다중 Exchange 객체 생성 ============
exchanges = {}
for user_id, config in USER_CONFIGS.items():
    api_key = os.getenv(config['api_key_env'])
    secret_key = os.getenv(config['secret_key_env'])
    
    if api_key and secret_key:
        exchanges[user_id] = ccxt.binance({
            'apiKey': api_key,
            'secret': secret_key,
            'enableRateLimit': True,
            'options': {
                'defaultType': 'future'
            }
        })
        logger.info(f"✅ {config['name']} Exchange 객체 생성 완료")
    else:
        logger.warning(f"⚠️ {config['name']} API 키가 설정되지 않았습니다.")

# Primary User의 exchange 객체 (하위 호환성)
exchange = exchanges.get('USER1')

# 텔레그램 설정
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_IDS = os.getenv('TELEGRAM_CHAT_IDS', '').split(',')

# ============ AI Decision Models ============
class TradingDecision(BaseModel):
    """트레이딩 시그널 검증용 모델"""
    decision: str = Field(..., pattern="^(approve|reject|modify|reverse)$")  # 'reverse' 추가
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

class MonitorPositionDecision(BaseModel):
    """포지션 모니터링용 모델"""
    decision: str = Field(..., pattern="^(hold|close|partial_close)$")
    percentage: int = Field(..., ge=0, le=100)
    reason: str = Field(..., min_length=1)
    exit_type: str = Field(..., pattern="^(take_profit|stop_loss|trend_reversal|risk_management|time_stop|none)$")
    confidence: float = Field(..., ge=0.0, le=1.0)
    urgency: str = Field(..., pattern="^(immediate|soon|watch|none)$")

class EmergencyTradingDecision(BaseModel):
    """긴급 거래 파라미터 모델"""
    percentage: int = Field(..., ge=10, le=50)
    stop_loss_price: float = Field(..., gt=0)
    take_profit_price: float = Field(..., gt=0)
    leverage: int = Field(..., ge=1, le=20)
    reason: str = Field(..., min_length=1)
    confidence: float = Field(..., ge=0.0, le=1.0)

# ============ Trading State 관리 ============
ACTIVE_POSITIONS = {}  # {symbol: {'side': 'buy/sell', 'entry_price': float, ...}}
IS_MONITORING = False
MONITOR_THREAD = None
TRADE_LOCK = threading.Lock()  # 멀티스레드 안전성
LAST_ALERT_TIME = {}  # 중복 알림 방지
TRADE_HISTORY = {}  # 거래 이력 저장

# ============ Helper Functions ============
def send_telegram_message(message, chat_ids=None):
    """텔레그램으로 메시지 전송 (알림 빈도 제한)"""
    if not ENABLE_TELEGRAM or not TELEGRAM_BOT_TOKEN:
        return False
    
    if chat_ids is None:
        chat_ids = TELEGRAM_CHAT_IDS
    
    # 메시지 길이 제한
    max_length = 4096
    if len(message) > max_length:
        message = message[:max_length-10] + "...[생략]"
    
    success = False
    for chat_id in chat_ids:
        if not chat_id:
            continue
        
        try:
            url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
            data = {
                "chat_id": chat_id,
                "text": message,
                "parse_mode": "Markdown"
            }
            response = requests.post(url, json=data)
            response.raise_for_status()
            success = True
        except Exception as e:
            logger.error(f"Telegram 전송 실패 (chat_id: {chat_id}): {e}")
    
    return success

def format_number(value):
    """숫자 포맷팅 - 큰 수는 K/M으로 표시"""
    if value >= 1_000_000:
        return f"{value/1_000_000:.1f}M"
    elif value >= 1_000:
        return f"{value/1_000:.1f}K"
    elif value < 1:
        return f"{value:.4f}"
    else:
        return f"{value:.2f}"

def extract_json_from_text(text):
    """AI 응답에서 JSON 추출"""
    # JSON 블록 찾기 (```json ... ``` 또는 { ... } 직접)
    json_pattern = r'```json\s*(\{.*?\})\s*```'
    match = re.search(json_pattern, text, re.DOTALL)
    if match:
        return match.group(1)
    
    # 직접 JSON 찾기
    json_direct_pattern = r'(\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\})'
    match = re.search(json_direct_pattern, text, re.DOTALL)
    if match:
        return match.group(1)
    
    return None

def create_default_reject_decision(reason="AI 처리 오류"):
    """기본 거부 결정 생성"""
    return {
        'decision': 'reject',
        'modified_action': 'hold',
        'percentage': 0,
        'reason': reason,
        'stop_loss_price': 0.0,
        'take_profit_price': 0.0,
        'pl_ratio': 0.0,
        'confidence': 0.0
    }

# ============ DB Functions ============
def init_db():
    """DB 초기화 및 테이블 생성"""
    conn = sqlite3.connect('trading_system.db')
    c = conn.cursor()
    
    # trades 테이블 - position_type 컬럼 추가
    c.execute('''CREATE TABLE IF NOT EXISTS trades
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  timestamp TEXT,
                  symbol TEXT,
                  trade_type TEXT,
                  ai_decision TEXT,
                  action TEXT,
                  percentage INTEGER,
                  reason TEXT,
                  current_price REAL,
                  stop_loss REAL,
                  take_profit REAL,
                  pl_ratio REAL,
                  confidence REAL,
                  reflection TEXT,
                  position_type TEXT)''')
    
    # 기존 테이블에 position_type 컬럼 추가 (이미 있으면 무시)
    try:
        c.execute("ALTER TABLE trades ADD COLUMN position_type TEXT")
    except sqlite3.OperationalError:
        pass  # 컬럼이 이미 존재함
    
    # completed_trades 테이블 - position_type 추가
    c.execute('''CREATE TABLE IF NOT EXISTS completed_trades
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  open_timestamp TEXT,
                  close_timestamp TEXT,
                  symbol TEXT,
                  position_type TEXT,
                  side TEXT,
                  entry_price REAL,
                  exit_price REAL,
                  quantity REAL,
                  realized_pnl REAL,
                  pnl_percentage REAL,
                  max_profit REAL,
                  max_loss REAL,
                  holding_time_minutes REAL,
                  exit_reason TEXT,
                  total_commission REAL,
                  reflection_summary TEXT)''')
    
    # balance_history 테이블
    c.execute('''CREATE TABLE IF NOT EXISTS balance_history
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  timestamp TEXT,
                  total_balance REAL,
                  available_balance REAL,
                  in_position_balance REAL,
                  btc_price REAL,
                  total_positions INTEGER,
                  pnl_24h REAL,
                  pnl_7d REAL,
                  pnl_30d REAL)''')
    
    # 인덱스 생성 (성능 향상)
    c.execute('''CREATE INDEX IF NOT EXISTS idx_trades_timestamp 
                 ON trades(timestamp DESC)''')
    c.execute('''CREATE INDEX IF NOT EXISTS idx_completed_trades_timestamp 
                 ON completed_trades(close_timestamp DESC)''')
    c.execute('''CREATE INDEX IF NOT EXISTS idx_balance_history_timestamp 
                 ON balance_history(timestamp DESC)''')
    
    conn.commit()
    logger.info("✅ DB 초기화 완료 (프로그램 시작, position_type 지원)")
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

# ============ 🆕 추가 기능 1: 과매수/과매도 필터링 함수 ============
def check_overbought_oversold_multi_timeframe(df_15min, df_hourly, df_4h, action):
    """
    멀티 타임프레임에서 과매수/과매도 상태 체크
    
    Returns:
        dict: {
            'is_risky': bool,
            'risk_level': str ('low', 'medium', 'high', 'extreme'),  # extreme 추가
            'warnings': list,
            'scores': dict,
            'reverse_opportunity': bool  # 🆕 반대 진입 기회
        }
    """
    warnings = []
    risk_scores = []
    reverse_signals = []  # 🆕 반대 진입 신호 수집
    
    # 15분봉 체크
    rsi_15m = df_15min['rsi'].iloc[-1]
    if action == 'buy' and rsi_15m > 70:
        warnings.append(f"15분봉 RSI 과매수 ({rsi_15m:.1f})")
        risk_scores.append(2)
        if rsi_15m > 80:  # 🆕 극단적 과매수
            reverse_signals.append("15m_extreme_overbought")
    elif action == 'sell' and rsi_15m < 30:
        warnings.append(f"15분봉 RSI 과매도 ({rsi_15m:.1f})")
        risk_scores.append(2)
        if rsi_15m < 20:  # 🆕 극단적 과매도
            reverse_signals.append("15m_extreme_oversold")
    elif action == 'buy' and rsi_15m > 60:
        risk_scores.append(1)
    elif action == 'sell' and rsi_15m < 40:
        risk_scores.append(1)
    
    # 1시간봉 체크 (더 중요)
    rsi_1h = df_hourly['rsi'].iloc[-1]
    if action == 'buy' and rsi_1h > 70:
        warnings.append(f"1시간봉 RSI 과매수 ({rsi_1h:.1f})")
        risk_scores.append(3)
        if rsi_1h > 85:  # 🆕 극단적 과매수
            reverse_signals.append("1h_extreme_overbought")
    elif action == 'sell' and rsi_1h < 30:
        warnings.append(f"1시간봉 RSI 과매도 ({rsi_1h:.1f})")
        risk_scores.append(3)
        if rsi_1h < 15:  # 🆕 극단적 과매도
            reverse_signals.append("1h_extreme_oversold")
    elif action == 'buy' and rsi_1h > 65:
        risk_scores.append(2)
    elif action == 'sell' and rsi_1h < 35:
        risk_scores.append(2)
    
    # 4시간봉 체크 (가장 중요)
    rsi_4h = df_4h['rsi'].iloc[-1]
    if action == 'buy' and rsi_4h > 70:
        warnings.append(f"4시간봉 RSI 과매수 ({rsi_4h:.1f})")
        risk_scores.append(5)
        if rsi_4h > 85:  # 🆕 극단적 과매수
            reverse_signals.append("4h_extreme_overbought")
    elif action == 'sell' and rsi_4h < 30:
        warnings.append(f"4시간봉 RSI 과매도 ({rsi_4h:.1f})")
        risk_scores.append(5)
        if rsi_4h < 15:  # 🆕 극단적 과매도
            reverse_signals.append("4h_extreme_oversold")
    elif action == 'buy' and rsi_4h > 65:
        risk_scores.append(3)
    elif action == 'sell' and rsi_4h < 35:
        risk_scores.append(3)
    
    # 볼린저 밴드 체크
    current_price_15m = df_15min['close'].iloc[-1]
    bb_upper_15m = df_15min['bb_bbh'].iloc[-1]
    bb_lower_15m = df_15min['bb_bbl'].iloc[-1]
    
    if action == 'buy' and current_price_15m > bb_upper_15m:
        warnings.append(f"15분봉 가격이 볼린저 상단 돌파 (과열)")
        risk_scores.append(2)
        # 🆕 볼린저 밴드 돌파율 체크
        bb_breakout_rate = (current_price_15m - bb_upper_15m) / bb_upper_15m * 100
        if bb_breakout_rate > 2:  # 2% 이상 돌파
            reverse_signals.append("bb_extreme_overbought")
    elif action == 'sell' and current_price_15m < bb_lower_15m:
        warnings.append(f"15분봉 가격이 볼린저 하단 돌파 (과냉)")
        risk_scores.append(2)
        # 🆕 볼린저 밴드 돌파율 체크
        bb_breakout_rate = (bb_lower_15m - current_price_15m) / bb_lower_15m * 100
        if bb_breakout_rate > 2:  # 2% 이상 돌파
            reverse_signals.append("bb_extreme_oversold")
    
    # 스토캐스틱 체크
    stoch_k_1h = df_hourly['stoch_k'].iloc[-1] if 'stoch_k' in df_hourly.columns else 50
    if action == 'buy' and stoch_k_1h > 80:
        warnings.append(f"1시간봉 스토캐스틱 과매수 ({stoch_k_1h:.1f})")
        risk_scores.append(2)
        if stoch_k_1h > 95:  # 🆕 극단적 과매수
            reverse_signals.append("stoch_extreme_overbought")
    elif action == 'sell' and stoch_k_1h < 20:
        warnings.append(f"1시간봉 스토캐스틱 과매도 ({stoch_k_1h:.1f})")
        risk_scores.append(2)
        if stoch_k_1h < 5:  # 🆕 극단적 과매도
            reverse_signals.append("stoch_extreme_oversold")
    
    # 🆕 다이버전스 체크 (추가 반전 신호)
    # MACD 다이버전스
    macd_1h = df_hourly['macd'].iloc[-1]
    macd_signal_1h = df_hourly['macd_signal'].iloc[-1]
    if action == 'buy' and macd_1h < macd_signal_1h and df_hourly['macd'].iloc[-2] > df_hourly['macd_signal'].iloc[-2]:
        reverse_signals.append("macd_bearish_crossover")
    elif action == 'sell' and macd_1h > macd_signal_1h and df_hourly['macd'].iloc[-2] < df_hourly['macd_signal'].iloc[-2]:
        reverse_signals.append("macd_bullish_crossover")
    
    # 총 리스크 점수 계산
    total_risk = sum(risk_scores)
    
    # 🆕 반대 진입 기회 판단
    reverse_opportunity = False
    if len(reverse_signals) >= 3:  # 3개 이상의 극단 신호
        reverse_opportunity = True
        warnings.append(f"⚠️ 극단적 {('과매수' if action == 'buy' else '과매도')} - 반대 진입 고려")
    
    # 리스크 레벨 결정
    if reverse_opportunity:
        risk_level = 'extreme'
        is_risky = True
    elif total_risk >= 8:
        risk_level = 'high'
        is_risky = True
    elif total_risk >= 5:
        risk_level = 'medium'
        is_risky = True
    elif total_risk >= 3:
        risk_level = 'low'
        is_risky = False
    else:
        risk_level = 'none'
        is_risky = False
    
    return {
        'is_risky': is_risky,
        'risk_level': risk_level,
        'total_risk_score': total_risk,
        'warnings': warnings,
        'scores': {
            'rsi_15m': rsi_15m,
            'rsi_1h': rsi_1h,
            'rsi_4h': rsi_4h,
            'stoch_1h': stoch_k_1h
        },
        'reverse_opportunity': reverse_opportunity,  # 🆕
        'reverse_signals': reverse_signals  # 🆕
    }

# ============ 🆕 추가 기능 2: 매물대 기반 TP/SL 조정 함수 ============
def calculate_volume_profile_levels(df, num_levels=5):
    """
    거래량 기반 매물대 계산
    
    Returns:
        dict: {
            'support_levels': [prices],
            'resistance_levels': [prices],
            'high_volume_zones': [(price_low, price_high)]
        }
    """
    try:
        # 가격 범위를 bins으로 나누기
        price_range = df['high'].max() - df['low'].min()
        num_bins = 50
        bin_size = price_range / num_bins
        
        # 각 bin의 거래량 합계 계산
        volume_profile = []
        min_price = df['low'].min()
        
        for i in range(num_bins):
            bin_low = min_price + (i * bin_size)
            bin_high = bin_low + bin_size
            bin_mid = (bin_low + bin_high) / 2
            
            # 해당 가격대의 거래량 합계
            mask = (df['low'] <= bin_high) & (df['high'] >= bin_low)
            bin_volume = df.loc[mask, 'volume'].sum()
            
            volume_profile.append({
                'price': bin_mid,
                'volume': bin_volume,
                'range': (bin_low, bin_high)
            })
        
        # 거래량이 많은 구간 찾기 (상위 20%)
        sorted_profile = sorted(volume_profile, key=lambda x: x['volume'], reverse=True)
        high_volume_zones = sorted_profile[:int(num_bins * 0.2)]
        
        # 현재가 기준으로 지지/저항 분류
        current_price = df['close'].iloc[-1]
        
        support_levels = []
        resistance_levels = []
        
        for zone in high_volume_zones:
            if zone['price'] < current_price:
                support_levels.append(zone['price'])
            elif zone['price'] > current_price:
                resistance_levels.append(zone['price'])
        
        # 가격순 정렬
        support_levels = sorted(support_levels, reverse=True)[:num_levels]
        resistance_levels = sorted(resistance_levels)[:num_levels]
        
        return {
            'support_levels': support_levels,
            'resistance_levels': resistance_levels,
            'high_volume_zones': [z['range'] for z in high_volume_zones[:10]]
        }
        
    except Exception as e:
        logger.error(f"매물대 계산 오류: {e}")
        return {
            'support_levels': [],
            'resistance_levels': [],
            'high_volume_zones': []
        }

def adjust_tp_sl_based_on_levels(symbol, action, current_price, original_sl, original_tp, market_data):
    """
    🔄 수정됨: 매물대 및 지지/저항선 기반으로 TP를 더 단기적으로 조정
    
    Returns:
        dict: {
            'adjusted_sl': float,
            'adjusted_tp': float,
            'sl_reason': str,
            'tp_reason': str,
            'is_adjusted': bool
        }
    """
    try:
        df_hourly = market_data['df_hourly']
        df_4h = market_data['df_4h']
        df_15min = market_data['df_15min']  # 🆕 15분봉 추가
        
        # ATR 계산 (변동성 기준)
        atr_15min = df_15min['atr'].iloc[-1]  # 🆕 15분 ATR
        atr_hourly = df_hourly['atr'].iloc[-1]
        atr_4h = df_4h['atr'].iloc[-1]
        
        # 매물대 계산
        volume_profile_15m = calculate_volume_profile_levels(df_15min)  # 🆕 15분 매물대
        volume_profile_1h = calculate_volume_profile_levels(df_hourly)
        volume_profile_4h = calculate_volume_profile_levels(df_4h)
        
        adjusted_sl = original_sl
        adjusted_tp = original_tp
        sl_reason = "원본 유지"
        tp_reason = "원본 유지"
        is_adjusted = False
        
        # === SL 조정 로직 ===
        sl_distance_percent = abs((original_sl - current_price) / current_price) * 100
        
        if action == 'buy':
            # 롱 포지션 SL 조정
            
            # 1. SL이 너무 멀 경우 (5% 이상)
            if sl_distance_percent > 5:
                # 가장 가까운 지지선 찾기
                nearest_support = None
                min_distance = float('inf')
                
                # 1시간봉 지지선 체크
                for support in volume_profile_1h['support_levels']:
                    if support < current_price:
                        distance = current_price - support
                        if distance < min_distance:
                            min_distance = distance
                            nearest_support = support
                
                # ATR 기반 최소 거리 (2 ATR)
                min_sl_distance = current_price - (atr_hourly * 2)
                
                if nearest_support and nearest_support > min_sl_distance:
                    adjusted_sl = nearest_support * 0.995  # 지지선 약간 아래
                    sl_reason = f"가까운 지지선 ({nearest_support:.2f}) 기준 조정"
                    is_adjusted = True
                else:
                    adjusted_sl = min_sl_distance
                    sl_reason = f"2xATR 기준 조정 (과도한 SL 방지)"
                    is_adjusted = True
            
            # 2. SL이 너무 가까운 경우 (<1% 또는 1 ATR 미만)
            elif sl_distance_percent < 1 or (current_price - original_sl) < atr_hourly:
                # 최소 1.5 ATR은 확보
                adjusted_sl = current_price - (atr_hourly * 1.5)
                sl_reason = "1.5xATR 최소 거리 확보"
                is_adjusted = True
                
        else:  # sell 포지션
            # 숏 포지션 SL 조정
            
            # 1. SL이 너무 멀 경우
            if sl_distance_percent > 5:
                # 가장 가까운 저항선 찾기
                nearest_resistance = None
                min_distance = float('inf')
                
                for resistance in volume_profile_1h['resistance_levels']:
                    if resistance > current_price:
                        distance = resistance - current_price
                        if distance < min_distance:
                            min_distance = distance
                            nearest_resistance = resistance
                
                max_sl_distance = current_price + (atr_hourly * 2)
                
                if nearest_resistance and nearest_resistance < max_sl_distance:
                    adjusted_sl = nearest_resistance * 1.005  # 저항선 약간 위
                    sl_reason = f"가까운 저항선 ({nearest_resistance:.2f}) 기준 조정"
                    is_adjusted = True
                else:
                    adjusted_sl = max_sl_distance
                    sl_reason = f"2xATR 기준 조정 (과도한 SL 방지)"
                    is_adjusted = True
            
            elif sl_distance_percent < 1 or (original_sl - current_price) < atr_hourly:
                adjusted_sl = current_price + (atr_hourly * 1.5)
                sl_reason = "1.5xATR 최소 거리 확보"
                is_adjusted = True
        
        # === 🔄 TP 조정 로직 (더 단기적으로 수정) ===
        tp_distance_percent = abs((original_tp - current_price) / current_price) * 100
        
        if action == 'buy':
            # 롱 포지션 TP 조정
            
            # 🆕 1. 단기 저항선 우선 체크 (15분봉)
            immediate_resistance = None
            for resistance in volume_profile_15m['resistance_levels']:
                if resistance > current_price:
                    resistance_distance = (resistance - current_price) / current_price * 100
                    if 0.5 <= resistance_distance <= 3:  # 0.5~3% 범위의 저항선
                        immediate_resistance = resistance
                        break
            
            # 2. TP가 너무 멀 경우 (수정: 10% → 6%)
            if tp_distance_percent > 6:  # 🔄 10% → 6%로 낮춤
                if immediate_resistance:
                    adjusted_tp = immediate_resistance * 0.998  # 🔄 저항선 더 가까이
                    tp_reason = f"단기 저항선 ({immediate_resistance:.2f}) 직전으로 조정"
                    is_adjusted = True
                else:
                    # 다음 1시간 저항선 찾기
                    next_resistance = None
                    for resistance in volume_profile_1h['resistance_levels']:
                        if resistance > current_price:
                            if (resistance - current_price) / current_price * 100 <= 4:  # 🔄 6% → 4%
                                next_resistance = resistance
                                break
                    
                    if next_resistance:
                        adjusted_tp = next_resistance * 0.997  # 🔄 저항선 더 가까이
                        tp_reason = f"1시간 저항선 ({next_resistance:.2f}) 직전으로 조정"
                        is_adjusted = True
                    else:
                        # ATR 기반 (수정: 3.5 → 2.5 ATR)
                        adjusted_tp = current_price + (atr_15min * 2.5)  # 🔄 15분 ATR 사용, 2.5배로 낮춤
                        tp_reason = "2.5x15분ATR 목표가로 조정 (단기 수익)"
                        is_adjusted = True
            
            # 🆕 3. TP가 3~6% 범위일 때도 체크
            elif 3 < tp_distance_percent <= 6:
                if immediate_resistance and immediate_resistance < original_tp:
                    adjusted_tp = immediate_resistance * 0.998
                    tp_reason = f"단기 매물대 ({immediate_resistance:.2f}) 고려"
                    is_adjusted = True
            
            # 4. TP가 너무 가까운 경우 (수정: 1.5% → 1%)
            elif tp_distance_percent < 1:  # 🔄 1.5% → 1%
                # 최소 1.5 ATR은 확보
                adjusted_tp = current_price + (atr_15min * 1.5)  # 🔄 15분 ATR 사용
                tp_reason = "1.5x15분ATR 최소 목표 확보"
                is_adjusted = True
                
        else:  # sell 포지션
            # 숏 포지션 TP 조정
            
            # 🆕 1. 단기 지지선 우선 체크 (15분봉)
            immediate_support = None
            for support in volume_profile_15m['support_levels']:
                if support < current_price:
                    support_distance = (current_price - support) / current_price * 100
                    if 0.5 <= support_distance <= 3:  # 0.5~3% 범위의 지지선
                        immediate_support = support
                        break
            
            # 2. TP가 너무 멀 경우 (수정: 10% → 6%)
            if tp_distance_percent > 6:  # 🔄 10% → 6%
                if immediate_support:
                    adjusted_tp = immediate_support * 1.002  # 🔄 지지선 더 가까이
                    tp_reason = f"단기 지지선 ({immediate_support:.2f}) 직후로 조정"
                    is_adjusted = True
                else:
                    next_support = None
                    for support in volume_profile_1h['support_levels']:
                        if support < current_price:
                            if (current_price - support) / current_price * 100 <= 4:  # 🔄 6% → 4%
                                next_support = support
                                break
                    
                    if next_support:
                        adjusted_tp = next_support * 1.003  # 🔄 지지선 더 가까이
                        tp_reason = f"1시간 지지선 ({next_support:.2f}) 직후로 조정"
                        is_adjusted = True
                    else:
                        adjusted_tp = current_price - (atr_15min * 2.5)  # 🔄 15분 ATR, 2.5배
                        tp_reason = "2.5x15분ATR 목표가로 조정 (단기 수익)"
                        is_adjusted = True
            
            # 🆕 3. TP가 3~6% 범위일 때도 체크
            elif 3 < tp_distance_percent <= 6:
                if immediate_support and immediate_support > original_tp:
                    adjusted_tp = immediate_support * 1.002
                    tp_reason = f"단기 매물대 ({immediate_support:.2f}) 고려"
                    is_adjusted = True
            
            # 4. TP가 너무 가까운 경우
            elif tp_distance_percent < 1:  # 🔄 1.5% → 1%
                adjusted_tp = current_price - (atr_15min * 1.5)  # 🔄 15분 ATR 사용
                tp_reason = "1.5x15분ATR 최소 목표 확보"
                is_adjusted = True
        
        # PL 비율 재계산
        sl_distance = abs(current_price - adjusted_sl)
        tp_distance = abs(adjusted_tp - current_price)
        adjusted_pl_ratio = tp_distance / sl_distance if sl_distance > 0 else 1.5
        
        # 🆕 로깅 개선
        if is_adjusted:
            logger.info(f"📊 TP/SL 조정 - {symbol} {action.upper()}")
            logger.info(f"  SL: {original_sl:.2f} → {adjusted_sl:.2f} ({sl_reason})")
            logger.info(f"  TP: {original_tp:.2f} → {adjusted_tp:.2f} ({tp_reason})")
            logger.info(f"  PL Ratio: {adjusted_pl_ratio:.2f}")
        
        return {
            'adjusted_sl': adjusted_sl,
            'adjusted_tp': adjusted_tp,
            'sl_reason': sl_reason,
            'tp_reason': tp_reason,
            'is_adjusted': is_adjusted,
            'pl_ratio': adjusted_pl_ratio
        }
        
    except Exception as e:
        logger.error(f"TP/SL 조정 오류: {e}")
        return {
            'adjusted_sl': original_sl,
            'adjusted_tp': original_tp,
            'sl_reason': "조정 실패 - 원본 유지",
            'tp_reason': "조정 실패 - 원본 유지",
            'is_adjusted': False,
            'pl_ratio': 1.5
        }

# ============ 🆕 추가 기능 3: 추세 역전 신호 감지 함수 ============
def detect_trend_reversal_signals(df_15min, df_hourly, df_4h, side):
    """
    🔄 수정됨: 추세 역전 신호를 약간 더 빨리 감지 (임계값 조정)
    
    Args:
        side: 'buy' (long) or 'sell' (short) - 현재 포지션 방향
    
    Returns:
        dict: {
            'should_exit': bool,
            'urgency': str ('immediate', 'soon', 'watch', 'none'),
            'confidence': float,
            'reversal_score': int,
            'signals': list
        }
    """
    reversal_score = 0
    signals = []
    
    # 🔄 임계값 수정 (더 민감하게)
    threshold_immediate = 8  # 10 → 8
    threshold_soon = 6       # 7 → 6
    threshold_watch = 3      # 4 → 3
    
    # === 15분봉 신호 (단기) ===
    # MACD 크로스오버
    if side == 'buy':
        if df_15min['macd'].iloc[-1] < df_15min['macd_signal'].iloc[-1] and \
           df_15min['macd'].iloc[-2] >= df_15min['macd_signal'].iloc[-2]:  # 🔄 >= 조건 추가
            reversal_score += 2.5  # 🔄 2 → 2.5
            signals.append("15m MACD bearish crossover")
    else:
        if df_15min['macd'].iloc[-1] > df_15min['macd_signal'].iloc[-1] and \
           df_15min['macd'].iloc[-2] <= df_15min['macd_signal'].iloc[-2]:  # 🔄 <= 조건 추가
            reversal_score += 2.5  # 🔄 2 → 2.5
            signals.append("15m MACD bullish crossover")
    
    # RSI 극단 반전
    rsi_15m = df_15min['rsi'].iloc[-1]
    rsi_15m_prev = df_15min['rsi'].iloc[-2]
    if side == 'buy':
        if rsi_15m < 65 and rsi_15m_prev > 70:  # 🔄 70 → 65 (더 빨리 감지)
            reversal_score += 1.5
            signals.append("15m RSI overbought reversal")
    else:
        if rsi_15m > 35 and rsi_15m_prev < 30:  # 🔄 30 → 35 (더 빨리 감지)
            reversal_score += 1.5
            signals.append("15m RSI oversold reversal")
    
    # 🆕 볼륨 이상 감지 (15분)
    volume_15m = df_15min['volume'].iloc[-1]
    volume_avg_15m = df_15min['volume'].rolling(20).mean().iloc[-1]
    if volume_15m > volume_avg_15m * 2:  # 평균의 2배 이상
        reversal_score += 1
        signals.append("15m abnormal volume spike")
    
    # === 1시간봉 신호 (중기) ===
    # DI 크로스오버
    if side == 'buy':
        if df_hourly['di_minus'].iloc[-1] > df_hourly['di_plus'].iloc[-1] and \
           df_hourly['di_minus'].iloc[-2] <= df_hourly['di_plus'].iloc[-2]:  # 🔄 조건 완화
            reversal_score += 3.5  # 🔄 3 → 3.5
            signals.append("1h DI- crosses above DI+")
    else:
        if df_hourly['di_plus'].iloc[-1] > df_hourly['di_minus'].iloc[-1] and \
           df_hourly['di_plus'].iloc[-2] <= df_hourly['di_minus'].iloc[-2]:  # 🔄 조건 완화
            reversal_score += 3.5  # 🔄 3 → 3.5
            signals.append("1h DI+ crosses above DI-")
    
    # ADX 트렌드 약화
    adx_1h = df_hourly['adx'].iloc[-1]
    adx_1h_prev = df_hourly['adx'].iloc[-3]  # 3개 전 캔들과 비교
    if adx_1h < 22 and adx_1h_prev > 25:  # 🔄 25 → 22 (더 빨리 감지)
        reversal_score += 2
        signals.append("1h ADX trend weakening")
    
    # CMF 자금 흐름 반전
    cmf_1h = df_hourly['cmf'].iloc[-1]
    if side == 'buy' and cmf_1h < -0.05:  # 🔄 -0.1 → -0.05
        reversal_score += 2
        signals.append("1h CMF negative (money outflow)")
    elif side == 'sell' and cmf_1h > 0.05:  # 🔄 0.1 → 0.05
        reversal_score += 2
        signals.append("1h CMF positive (money inflow)")
    
    # 🆕 MACD 히스토그램 감소 (1시간)
    macd_hist = df_hourly['macd_diff'].iloc[-1]
    macd_hist_prev = df_hourly['macd_diff'].iloc[-2]
    if side == 'buy' and macd_hist < macd_hist_prev * 0.7:  # 30% 이상 감소
        reversal_score += 1.5
        signals.append("1h MACD histogram shrinking")
    elif side == 'sell' and macd_hist > macd_hist_prev * 0.7:
        reversal_score += 1.5
        signals.append("1h MACD histogram shrinking")
    
    # === 4시간봉 신호 (장기) ===
    # 트렌드 라인 브레이크
    if side == 'buy':
        # 하락 추세 시작 감지
        if df_4h['close'].iloc[-1] < df_4h['sma_20'].iloc[-1] and \
           df_4h['close'].iloc[-2] >= df_4h['sma_20'].iloc[-2]:  # 🔄 조건 완화
            reversal_score += 3  # 🔄 2.5 → 3
            signals.append("4h price breaks below SMA20")
    else:
        # 상승 추세 시작 감지
        if df_4h['close'].iloc[-1] > df_4h['sma_20'].iloc[-1] and \
           df_4h['close'].iloc[-2] <= df_4h['sma_20'].iloc[-2]:  # 🔄 조건 완화
            reversal_score += 3  # 🔄 2.5 → 3
            signals.append("4h price breaks above SMA20")
    
    # 🆕 RSI 다이버전스 (4시간)
    rsi_4h = df_4h['rsi'].iloc[-1]
    rsi_4h_prev = df_4h['rsi'].iloc[-3]
    price_4h = df_4h['close'].iloc[-1]
    price_4h_prev = df_4h['close'].iloc[-3]
    
    if side == 'buy':
        # Bearish divergence: 가격 상승, RSI 하락
        if price_4h > price_4h_prev and rsi_4h < rsi_4h_prev:
            reversal_score += 2.5
            signals.append("4h bearish RSI divergence")
    else:
        # Bullish divergence: 가격 하락, RSI 상승
        if price_4h < price_4h_prev and rsi_4h > rsi_4h_prev:
            reversal_score += 2.5
            signals.append("4h bullish RSI divergence")
    
    # 🆕 볼린저 밴드 수축/확장 (4시간)
    bb_width = df_4h['bb_bbh'].iloc[-1] - df_4h['bb_bbl'].iloc[-1]
    bb_width_avg = (df_4h['bb_bbh'] - df_4h['bb_bbl']).rolling(20).mean().iloc[-1]
    if bb_width < bb_width_avg * 0.7:  # 볼린저 밴드 수축
        reversal_score += 1
        signals.append("4h Bollinger Bands squeeze")
    
    # === 종합 판단 ===
    should_exit = False
    urgency = 'none'
    confidence = 0
    
    if reversal_score >= threshold_immediate:
        should_exit = True
        urgency = 'immediate'
        confidence = min(reversal_score / 12, 1.0)  # 🔄 15 → 12
    elif reversal_score >= threshold_soon:
        should_exit = False  # soon은 아직 홀드
        urgency = 'soon'
        confidence = reversal_score / 12  # 🔄 15 → 12
    elif reversal_score >= threshold_watch:
        should_exit = False
        urgency = 'watch'
        confidence = reversal_score / 12  # 🔄 15 → 12
    
    return {
        'should_exit': should_exit,
        'urgency': urgency,
        'confidence': confidence,
        'reversal_score': reversal_score,
        'signals': signals,
        'threshold_immediate': threshold_immediate,
        'threshold_soon': threshold_soon,
        'threshold_watch': threshold_watch
    }

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
        
        # 5분봉 데이터 (더 많이 가져오기 - ATR 계산 위해)
        df_15min = pd.DataFrame(
            exchange.fetch_ohlcv(symbol, timeframe='15m', limit=150),  # 15분봉으로 변경
            columns=['timestamp', 'open', 'high', 'low', 'close', 'volume']
        )
        df_15min['timestamp'] = pd.to_datetime(df_15min['timestamp'], unit='ms').dt.tz_localize('UTC').dt.tz_convert('Asia/Seoul')
        df_15min = df_15min.set_index('timestamp')
        df_15min = df_15min.dropna()  # dropna(df) → df.dropna() 수정
        df_15min = add_indicators(df_15min)
        
        # ATR NaN 처리 (tail 전에 수행)
        if 'atr' in df_15min.columns:
            df_15min['atr'] = df_15min['atr'].fillna(method='bfill')
            if df_15min['atr'].isna().any():
                # 대체값: high-low 평균
                default_atr = (df_15min['high'] - df_15min['low']).rolling(14).mean().iloc[-1]
                if pd.isna(default_atr) or default_atr == 0:
                    default_atr = current_price * 0.002  # 가격의 0.2%
                df_15min['atr'] = df_15min['atr'].fillna(default_atr)
            # ATR이 0인 경우 처리
            df_15min.loc[df_15min['atr'] == 0, 'atr'] = current_price * 0.002
        
        df_15min = df_15min.tail(60)
        
        # 1시간봉 데이터 (더 많이 가져오기)
        df_hourly = pd.DataFrame(
            exchange.fetch_ohlcv(symbol, timeframe='1h', limit=100),  # 57 → 100
            columns=['timestamp', 'open', 'high', 'low', 'close', 'volume']
        )
        df_hourly['timestamp'] = pd.to_datetime(df_hourly['timestamp'], unit='ms').dt.tz_localize('UTC').dt.tz_convert('Asia/Seoul')
        df_hourly = df_hourly.set_index('timestamp')
        df_hourly = df_hourly.dropna()  # dropna(df) → df.dropna()
        df_hourly = add_indicators(df_hourly)
        
        # ATR NaN 처리
        if 'atr' in df_hourly.columns:
            df_hourly['atr'] = df_hourly['atr'].fillna(method='bfill')
            if df_hourly['atr'].isna().any():
                default_atr = (df_hourly['high'] - df_hourly['low']).rolling(14).mean().iloc[-1]
                if pd.isna(default_atr) or default_atr == 0:
                    default_atr = current_price * 0.003
                df_hourly['atr'] = df_hourly['atr'].fillna(default_atr)
            df_hourly.loc[df_hourly['atr'] == 0, 'atr'] = current_price * 0.003
        
        df_hourly = df_hourly.tail(24)
        
        # 4시간봉 데이터 (더 많이 가져오기)
        df_4h = pd.DataFrame(
            exchange.fetch_ohlcv(symbol, timeframe='4h', limit=100),  # 51 → 100
            columns=['timestamp', 'open', 'high', 'low', 'close', 'volume']
        )
        df_4h['timestamp'] = pd.to_datetime(df_4h['timestamp'], unit='ms').dt.tz_localize('UTC').dt.tz_convert('Asia/Seoul')
        df_4h = df_4h.set_index('timestamp')
        df_4h = df_4h.dropna()  # dropna(df) → df.dropna()
        df_4h = add_indicators(df_4h)
        
        # ATR NaN 처리
        if 'atr' in df_4h.columns:
            df_4h['atr'] = df_4h['atr'].fillna(method='bfill')
            if df_4h['atr'].isna().any():
                default_atr = (df_4h['high'] - df_4h['low']).rolling(14).mean().iloc[-1]
                if pd.isna(default_atr) or default_atr == 0:
                    default_atr = current_price * 0.005
                df_4h['atr'] = df_4h['atr'].fillna(default_atr)
            df_4h.loc[df_4h['atr'] == 0, 'atr'] = current_price * 0.005
        
        df_4h = df_4h.tail(18)
        
        # 공포 탐욕 지수 (BTC만 해당)
        fear_greed_index = None
        if 'BTC' in symbol:
            fear_greed_index = get_fear_and_greed_index()
        
        # ATR 값 로깅 (디버깅용)
        try:
            atr_15m = df_15min['atr'].iloc[-1] if 'atr' in df_15min.columns else 0
            atr_1h = df_hourly['atr'].iloc[-1] if 'atr' in df_hourly.columns else 0
            atr_4h = df_4h['atr'].iloc[-1] if 'atr' in df_4h.columns else 0
            logger.debug(f"{symbol} ATR values - 15m: {atr_15m:.4f}, 1h: {atr_1h:.4f}, 4h: {atr_4h:.4f}")
        except Exception as e:
            logger.warning(f"Error logging ATR values: {e}")
        
        return {
            'current_price': current_price,
            'orderbook': orderbook,
            'df_15min': df_15min,
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
def is_duplicate_trade_record(conn, symbol, action, trade_type, time_window_seconds=10):
    """
    중복 거래 기록 체크
    최근 N초 이내에 동일한 symbol, action, trade_type 조합이 있는지 확인
    
    Args:
        conn: DB 연결
        symbol: 심볼 (예: 'BTC/USDT')
        action: 액션 (예: 'buy', 'sell', 'close_position', 'monitor')
        trade_type: 거래 타입 (예: 'AI_VALIDATION', 'AI_MONITOR')
        time_window_seconds: 중복 체크 시간 범위 (초)
    
    Returns:
        bool: 중복이면 True, 아니면 False
    """
    try:
        c = conn.cursor()
        
        # 현재 시간에서 time_window_seconds 이전 시간 계산
        cutoff_time = (datetime.now() - timedelta(seconds=time_window_seconds)).isoformat()
        
        # 최근 기록 조회
        c.execute("""
            SELECT COUNT(*) FROM trades 
            WHERE symbol = ? 
            AND action = ? 
            AND trade_type = ?
            AND timestamp > ?
        """, (symbol, action, trade_type, cutoff_time))
        
        count = c.fetchone()[0]
        return count > 0
        
    except Exception as e:
        logger.error(f"중복 체크 오류: {e}")
        return False  # 오류 시 중복 아님으로 처리

def get_db_connection():
    """DB 연결 반환 (없으면 생성)"""
    return init_db()

def generate_trade_reflection(conn, symbol, action, decision, market_conditions):
    """
    최근 유사 거래 분석하여 Reflection 생성
    
    Returns:
        str: AI가 참고할 과거 거래 패턴 분석
    """
    try:
        c = conn.cursor()
        
        # 최근 30일 내 동일 심볼의 완료된 거래 조회
        cutoff_date = (datetime.now() - timedelta(days=30)).isoformat()
        
        c.execute("""
            SELECT side, pnl_percentage, holding_time_minutes, exit_reason,
                   entry_price, exit_price, max_profit, max_loss
            FROM completed_trades
            WHERE symbol = ?
            AND close_timestamp > ?
            ORDER BY close_timestamp DESC
            LIMIT 20
        """, (symbol, cutoff_date))
        
        recent_trades = c.fetchall()
        
        if not recent_trades:
            return "No recent trade history for this symbol."
        
        # 통계 계산
        win_trades = [t for t in recent_trades if t[1] > 0]  # pnl_percentage > 0
        loss_trades = [t for t in recent_trades if t[1] <= 0]
        
        win_rate = len(win_trades) / len(recent_trades) * 100 if recent_trades else 0
        
        avg_win = sum(t[1] for t in win_trades) / len(win_trades) if win_trades else 0
        avg_loss = sum(abs(t[1]) for t in loss_trades) / len(loss_trades) if loss_trades else 0
        
        avg_holding_time = sum(t[2] for t in recent_trades) / len(recent_trades) if recent_trades else 0
        
        # 조기 청산 패턴 분석
        early_exits = [t for t in recent_trades if t[2] < 60 and t[3] != 'stop_loss']  # 1시간 이내 청산
        
        # Reflection 생성
        reflection = f"""
=== TRADE HISTORY ANALYSIS for {symbol} ===
Total Recent Trades: {len(recent_trades)}
Win Rate: {win_rate:.1f}%
Average Win: +{avg_win:.2f}%
Average Loss: -{avg_loss:.2f}%
Average Holding Time: {avg_holding_time:.0f} minutes

KEY PATTERNS:
"""
        
        if win_rate < 40:
            reflection += "- Low win rate detected. Consider more conservative entry criteria.\n"
        elif win_rate > 70:
            reflection += "- High win rate. Current strategy working well for this symbol.\n"
        
        if avg_loss > avg_win * 1.5:
            reflection += "- Losses are significantly larger than wins. Tighten stop losses.\n"
        
        if len(early_exits) > len(recent_trades) * 0.3:
            reflection += f"- {len(early_exits)} trades exited within 1 hour. May be entering on noise.\n"
        
        # 최근 3개 거래 트렌드
        if len(recent_trades) >= 3:
            recent_3_pnl = [t[1] for t in recent_trades[:3]]
            if all(pnl < 0 for pnl in recent_3_pnl):
                reflection += "- Last 3 trades were losses. Extra caution needed.\n"
            elif all(pnl > 0 for pnl in recent_3_pnl):
                reflection += "- Last 3 trades were wins. Momentum is positive.\n"
        
        # 현재 시장 조건과 비교
        if market_conditions:
            current_rsi = market_conditions.get('df_hourly', pd.DataFrame()).get('rsi', pd.Series()).iloc[-1] if not market_conditions.get('df_hourly', pd.DataFrame()).empty else 50
            
            # RSI 기반 과거 성과 분석
            c.execute("""
                SELECT AVG(pnl_percentage)
                FROM completed_trades ct
                JOIN trades t ON ct.symbol = t.symbol 
                    AND ABS(julianday(ct.open_timestamp) - julianday(t.timestamp)) < 1
                WHERE ct.symbol = ?
                AND t.reason LIKE ?
                AND ct.close_timestamp > ?
            """, (symbol, f'%RSI%{int(current_rsi/10)*10}%', cutoff_date))
            
            similar_condition_avg = c.fetchone()[0]
            
            if similar_condition_avg is not None:
                reflection += f"- Historical performance in similar RSI conditions ({int(current_rsi)}): {similar_condition_avg:+.2f}%\n"
        
        reflection += f"\nRECOMMENDATION FOR {action.upper()}:\n"
        
        if action == 'buy':
            if win_rate < 40:
                reflection += "- Be extra selective. Wait for strong confirmation signals.\n"
            if avg_holding_time < 30:
                reflection += "- Recent trades are very short. Consider larger timeframe signals.\n"
        else:  # sell
            if win_rate < 40:
                reflection += "- Short positions have been challenging. Ensure strong bearish signals.\n"
        
        return reflection
        
    except Exception as e:
        logger.error(f"Reflection 생성 오류: {e}")
        return "Error generating trade reflection."

# ============ Multi-Timeframe Analysis ============
def get_multi_timeframe_analysis(symbol):
    """멀티 타임프레임 기술적 분석"""
    try:
        # 현재가
        ticker = exchange.fetch_ticker(symbol)
        current_price = ticker['last']
        
        # 15분봉
        df_15m = pd.DataFrame(
            exchange.fetch_ohlcv(symbol, timeframe='15m', limit=100),
            columns=['timestamp', 'open', 'high', 'low', 'close', 'volume']
        )
        df_15m = add_indicators(df_15m)
        
        # 1시간봉
        df_1h = pd.DataFrame(
            exchange.fetch_ohlcv(symbol, timeframe='1h', limit=100),
            columns=['timestamp', 'open', 'high', 'low', 'close', 'volume']
        )
        df_1h = add_indicators(df_1h)
        
        # 4시간봉
        df_4h = pd.DataFrame(
            exchange.fetch_ohlcv(symbol, timeframe='4h', limit=50),
            columns=['timestamp', 'open', 'high', 'low', 'close', 'volume']
        )
        df_4h = add_indicators(df_4h)
        
        return {
            'current_price': current_price,
            'rsi_15m': df_15m['rsi'].iloc[-1] if 'rsi' in df_15m.columns else 50,
            'rsi_1h': df_1h['rsi'].iloc[-1] if 'rsi' in df_1h.columns else 50,
            'rsi_4h': df_4h['rsi'].iloc[-1] if 'rsi' in df_4h.columns else 50,
            'atr_15m': df_15m['atr'].iloc[-1] if 'atr' in df_15m.columns else current_price * 0.002,
            'atr_1h': df_1h['atr'].iloc[-1] if 'atr' in df_1h.columns else current_price * 0.003,
            'atr_4h': df_4h['atr'].iloc[-1] if 'atr' in df_4h.columns else current_price * 0.005,
            'macd_15m': df_15m['macd'].iloc[-1] if 'macd' in df_15m.columns else 0,
            'macd_1h': df_1h['macd'].iloc[-1] if 'macd' in df_1h.columns else 0,
            'adx_1h': df_1h['adx'].iloc[-1] if 'adx' in df_1h.columns else 20,
            'adx_4h': df_4h['adx'].iloc[-1] if 'adx' in df_4h.columns else 20
        }
        
    except Exception as e:
        logger.error(f"멀티타임프레임 분석 오류: {e}")
        return {}

# ============ Emergency Parameters ============
def ai_emergency_parameters(symbol, action):
    """JSON 파싱 실패 시 AI가 자동으로 거래 파라미터 설정"""
    try:
        client = OpenAI(api_key=os.getenv("DEEPSEEK_API_KEY"), base_url="https://api.deepseek.com")
        if not client.api_key:
            return None
            
        # 현재 시장 데이터 수집
        ticker = exchange.fetch_ticker(symbol)
        current_price = ticker['last']
        
        # 기술적 분석
        analysis = get_multi_timeframe_analysis(symbol)
        
        # 잔고 확인
        balance = exchange.fetch_balance()
        free_usdt = balance['USDT']['free']
        
        prompt = f"""Emergency trading parameter generation required due to webhook parsing error.

MARKET DATA:
Symbol: {symbol}
Action: {action.upper()}
Current Price: ${current_price:.4f}
Free Balance: ${free_usdt:.2f}
24h Change: {ticker['percentage']:.2f}%

TECHNICAL INDICATORS:
RSI (15m): {analysis.get('rsi_15m', 50):.1f}
RSI (1h): {analysis.get('rsi_1h', 50):.1f}
ATR (15m): {analysis.get('atr_15m', current_price * 0.01):.4f}

REQUIREMENTS (MODERATE CONSERVATIVE):
1. Position size: 15-30% of free balance
2. Take Profit: 2.0-3.0% from entry (SHORT-TERM)
3. Stop Loss: 1.0-1.5% from entry  
4. Leverage: 5-10x maximum
5. Balance risk management with profit potential

Generate emergency trading parameters. Respond with JSON only:
{{
  "percentage": 20,
  "stop_loss_price": 0.0,
  "take_profit_price": 0.0,
  "leverage": 10,
  "reason": "Emergency parameters with short-term profit target",
  "confidence": 0.0-1.0
}}"""

        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": "You are an emergency risk management AI. Generate moderate conservative trading parameters with short-term profit targets."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=300,
            response_format={"type": "json_object"}
        )
        
        result_text = response.choices[0].message.content
        result_json = json.loads(result_text)
        
        # Pydantic 검증
        emergency_params = EmergencyTradingDecision(**result_json)
        
        logger.info(f"🚨 AI 긴급 파라미터 생성:")
        logger.info(f"   크기: {emergency_params.percentage}%")
        logger.info(f"   TP: ${emergency_params.take_profit_price:.4f}")
        logger.info(f"   SL: ${emergency_params.stop_loss_price:.4f}")
        logger.info(f"   레버리지: {emergency_params.leverage}x")
        
        return emergency_params
        
    except Exception as e:
        logger.error(f"AI 긴급 파라미터 생성 실패: {str(e)}")
        return None

# ============ Close Position Validation ============
def ai_validate_close_signal(symbol, market_data):
    """AI를 통한 청산 시그널 검증"""
    try:
        client = OpenAI(api_key=os.getenv("DEEPSEEK_API_KEY"), base_url="https://api.deepseek.com")
        
        if not client.api_key:
            logger.error("DeepSeek API 키가 설정되지 않았습니다")
            return {'decision': 'reject', 'reason': 'API 키 없음', 'confidence': 0.0}
        
        # 시장 데이터 추출
        current_price = market_data['current_price']
        df_15min = market_data['df_15min']
        df_hourly = market_data['df_hourly']
        
        prompt = f"""
CLOSE POSITION SIGNAL VALIDATION

Symbol: {symbol}
Current Price: ${current_price:.2f}

TECHNICAL DATA:
- RSI 15m: {df_15min['rsi'].iloc[-1]:.2f}
- RSI 1h: {df_hourly['rsi'].iloc[-1]:.2f}
- MACD 1h: {df_hourly['macd'].iloc[-1]:.4f}

Validate if this close signal should be executed.

Respond with JSON only:
{{
  "decision": "approve/reject",
  "reason": "explanation",
  "confidence": 0.0-1.0
}}
"""
        
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": "You are a position close validator. Be conservative."},
                {"role": "user", "content": prompt}
            ],
            response_format={'type': 'json_object'},
            temperature=0.1,
            max_tokens=500
        )
        
        result_text = extract_ai_response(response)
        parsed_json = json.loads(result_text)
        
        decision = ClosePositionDecision.model_validate(parsed_json)
        return decision.model_dump()
        
    except Exception as e:
        logger.error(f"청산 신호 검증 오류: {e}")
        return {'decision': 'reject', 'reason': f'검증 오류: {str(e)}', 'confidence': 0.0}
def is_duplicate_trade_record(conn, symbol, action, trade_type, time_window_seconds=10):
    """
    중복 거래 기록 체크
    최근 N초 이내에 동일한 symbol, action, trade_type 조합이 있는지 확인
    
    Args:
        conn: DB 연결
        symbol: 심볼 (예: 'BTC/USDT')
        action: 액션 (예: 'buy', 'sell', 'close_position', 'monitor')
        trade_type: 거래 타입 (예: 'AI_VALIDATION', 'AI_MONITOR')
        time_window_seconds: 중복 체크 시간 범위 (초)
    
    Returns:
        bool: 중복이면 True, 아니면 False
    """
    try:
        c = conn.cursor()
        
        # 현재 시간에서 time_window_seconds 이전 시간 계산
        cutoff_time = (datetime.now() - timedelta(seconds=time_window_seconds)).isoformat()
        
        # 최근 기록 조회
        c.execute("""
            SELECT COUNT(*) FROM trades 
            WHERE symbol = ? 
            AND action = ? 
            AND trade_type = ?
            AND timestamp > ?
        """, (symbol, action, trade_type, cutoff_time))
        
        count = c.fetchone()[0]
        return count > 0
        
    except Exception as e:
        logger.error(f"중복 체크 오류: {e}")
        return False  # 오류 시 중복 아님으로 처리

def get_db_connection():
    """DB 연결 반환 (없으면 생성)"""
    return init_db()

def generate_trade_reflection(conn, symbol, action, decision, market_conditions):
    """
    최근 유사 거래 분석하여 Reflection 생성
    
    Returns:
        str: AI가 참고할 과거 거래 패턴 분석
    """
    try:
        c = conn.cursor()
        
        # 최근 30일 내 동일 심볼의 완료된 거래 조회
        cutoff_date = (datetime.now() - timedelta(days=30)).isoformat()
        
        c.execute("""
            SELECT side, pnl_percentage, holding_time_minutes, exit_reason,
                   entry_price, exit_price, max_profit, max_loss
            FROM completed_trades
            WHERE symbol = ?
            AND close_timestamp > ?
            ORDER BY close_timestamp DESC
            LIMIT 20
        """, (symbol, cutoff_date))
        
        recent_trades = c.fetchall()
        
        if not recent_trades:
            return "No recent trade history for this symbol."
        
        # 통계 계산
        win_trades = [t for t in recent_trades if t[1] > 0]  # pnl_percentage > 0
        loss_trades = [t for t in recent_trades if t[1] <= 0]
        
        win_rate = len(win_trades) / len(recent_trades) * 100 if recent_trades else 0
        
        avg_win = sum(t[1] for t in win_trades) / len(win_trades) if win_trades else 0
        avg_loss = sum(abs(t[1]) for t in loss_trades) / len(loss_trades) if loss_trades else 0
        
        avg_holding_time = sum(t[2] for t in recent_trades) / len(recent_trades) if recent_trades else 0
        
        # 조기 청산 패턴 분석
        early_exits = [t for t in recent_trades if t[2] < 60 and t[3] != 'stop_loss']  # 1시간 이내 청산
        
        # Reflection 생성
        reflection = f"""
=== TRADE HISTORY ANALYSIS for {symbol} ===
Total Recent Trades: {len(recent_trades)}
Win Rate: {win_rate:.1f}%
Average Win: +{avg_win:.2f}%
Average Loss: -{avg_loss:.2f}%
Average Holding Time: {avg_holding_time:.0f} minutes

KEY PATTERNS:
"""
        
        if win_rate < 40:
            reflection += "- Low win rate detected. Consider more conservative entry criteria.\n"
        elif win_rate > 70:
            reflection += "- High win rate. Current strategy working well for this symbol.\n"
        
        if avg_loss > avg_win * 1.5:
            reflection += "- Losses are significantly larger than wins. Tighten stop losses.\n"
        
        if len(early_exits) > len(recent_trades) * 0.3:
            reflection += f"- {len(early_exits)} trades exited within 1 hour. May be entering on noise.\n"
        
        # 최근 3개 거래 트렌드
        if len(recent_trades) >= 3:
            recent_3_pnl = [t[1] for t in recent_trades[:3]]
            if all(pnl < 0 for pnl in recent_3_pnl):
                reflection += "- Last 3 trades were losses. Extra caution needed.\n"
            elif all(pnl > 0 for pnl in recent_3_pnl):
                reflection += "- Last 3 trades were wins. Momentum is positive.\n"
        
        # 현재 시장 조건과 비교
        if market_conditions:
            current_rsi = market_conditions.get('df_hourly', pd.DataFrame()).get('rsi', pd.Series()).iloc[-1] if not market_conditions.get('df_hourly', pd.DataFrame()).empty else 50
            
            # RSI 기반 과거 성과 분석
            c.execute("""
                SELECT AVG(pnl_percentage)
                FROM completed_trades ct
                JOIN trades t ON ct.symbol = t.symbol 
                    AND ABS(julianday(ct.open_timestamp) - julianday(t.timestamp)) < 1
                WHERE ct.symbol = ?
                AND t.reason LIKE ?
                AND ct.close_timestamp > ?
            """, (symbol, f'%RSI%{int(current_rsi/10)*10}%', cutoff_date))
            
            similar_condition_avg = c.fetchone()[0]
            
            if similar_condition_avg is not None:
                reflection += f"- Historical performance in similar RSI conditions ({int(current_rsi)}): {similar_condition_avg:+.2f}%\n"
        
        reflection += f"\nRECOMMENDATION FOR {action.upper()}:\n"
        
        if action == 'buy':
            if win_rate < 40:
                reflection += "- Be extra selective. Wait for strong confirmation signals.\n"
            if avg_holding_time < 30:
                reflection += "- Recent trades are very short. Consider larger timeframe signals.\n"
        else:  # sell
            if win_rate < 40:
                reflection += "- Short positions have been challenging. Ensure strong bearish signals.\n"
        
        return reflection
        
    except Exception as e:
        logger.error(f"Reflection 생성 오류: {e}")
        return "Error generating trade reflection."

# ======= 기존 코드 계속 (나머지 함수들) =======

# 나머지 함수들은 원본 코드와 동일하게 유지...
# (파일이 너무 길어서 여기서는 수정된 부분만 표시했습니다)

# ============ AI Signal Validation with Reverse Entry ============
def ai_validate_trading_signal(symbol, action, market_data, reflection=""):
    """
    🔄 수정됨: AI를 통한 트레이딩 시그널 검증 - 반대 진입 기능 추가
    
    Returns:
        dict: TradingDecision 모델 형식의 결정
    """
    try:
        client = OpenAI(api_key=os.getenv("DEEPSEEK_API_KEY"), base_url="https://api.deepseek.com")
        
        if not client.api_key:
            logger.error("DeepSeek API 키가 설정되지 않았습니다")
            return create_default_reject_decision("API 키 없음")
        
        # 시장 데이터 추출
        current_price = market_data['current_price']
        df_15min = market_data['df_15min']
        df_hourly = market_data['df_hourly']
        df_4h = market_data['df_4h']
        fear_greed_index = market_data.get('fear_greed_index')
        
        # 🆕 과매수/과매도 체크 (반대 진입 판단 포함)
        overbought_oversold = check_overbought_oversold_multi_timeframe(df_15min, df_hourly, df_4h, action)
        
        # ATR 계산
        atr_15min = df_15min['atr'].iloc[-1] if 'atr' in df_15min.columns else current_price * 0.002
        atr_hourly = df_hourly['atr'].iloc[-1] if 'atr' in df_hourly.columns else current_price * 0.003
        atr_4h = df_4h['atr'].iloc[-1] if 'atr' in df_4h.columns else current_price * 0.005
        
        # 초기 SL/TP 계산 (ATR 기반)
        if action == 'buy':
            initial_sl = current_price - (atr_hourly * 2)
            initial_tp = current_price + (atr_hourly * 3)
        else:
            initial_sl = current_price + (atr_hourly * 2)
            initial_tp = current_price - (atr_hourly * 3)
        
        # 매물대 기반 조정
        adjusted = adjust_tp_sl_based_on_levels(
            symbol, action, current_price, initial_sl, initial_tp, market_data
        )
        
        # JSON 템플릿
        json_template = """{
    "decision": "approve/reject/modify/reverse",
    "modified_action": "buy/sell/hold",
    "percentage": 10-100,
    "reason": "detailed explanation with score calculation",
    "stop_loss_price": number,
    "take_profit_price": number,
    "pl_ratio": 1.0-5.0,
    "confidence": 0.0-1.0
}"""

        # 🆕 반대 진입 조건 설명 추가
        reverse_entry_condition = ""
        if overbought_oversold['reverse_opportunity']:
            reverse_entry_condition = f"""
🔄 **REVERSE ENTRY OPPORTUNITY DETECTED:**
- Current signal: {action.upper()}
- Market condition: EXTREME {'OVERBOUGHT' if action == 'buy' else 'OVERSOLD'}
- Reverse signals detected: {', '.join(overbought_oversold['reverse_signals'])}
- Risk level: {overbought_oversold['risk_level'].upper()}

**REVERSE ENTRY CRITERIA (Must meet ALL):**
1. At least 3 extreme signals present: {'✅' if len(overbought_oversold['reverse_signals']) >= 3 else '❌'} ({len(overbought_oversold['reverse_signals'])}/3)
2. Multiple timeframe confirmation of extreme conditions
3. Clear divergence or reversal patterns forming
4. Volume supporting potential reversal

**If conditions met, you should:**
- Set decision to "reverse"
- Set modified_action to opposite of original signal ({'sell' if action == 'buy' else 'buy'})
- Use conservative position size (30-50%)
- Set tight stop loss due to counter-trend nature
"""

        prompt = f"""
═══════════════════════════════════════════
📊 CRYPTO FUTURES SIGNAL VALIDATION REQUEST
═══════════════════════════════════════════

**POSITION DETAILS:**
• Symbol: {symbol}
• Requested Action: {action.upper()}
• Current Price: ${current_price:.2f}
• Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} KST

{reverse_entry_condition}

**MARKET CONDITIONS:**
{f"• Fear & Greed Index: {fear_greed_index['value']} ({fear_greed_index['value_classification']})" if fear_greed_index else "• Fear & Greed: N/A"}
• Market Volatility (ATR): 15m={atr_15min:.4f}, 1h={atr_hourly:.4f}, 4h={atr_4h:.4f}

**RISK ANALYSIS:**
• Risk Level: {overbought_oversold['risk_level'].upper()}
• Total Risk Score: {overbought_oversold['total_risk_score']}
• Warnings: {', '.join(overbought_oversold['warnings']) if overbought_oversold['warnings'] else 'None'}

**PROPOSED RISK MANAGEMENT:**
• Initial Stop Loss: ${adjusted['adjusted_sl']:.2f} ({adjusted['sl_reason']})
• Initial Take Profit: ${adjusted['adjusted_tp']:.2f} ({adjusted['tp_reason']})
• Risk/Reward Ratio: {adjusted['pl_ratio']:.2f}

═══════════════════════════════════════════
📈 TECHNICAL ANALYSIS SUMMARY
═══════════════════════════════════════════

→ **15-MINUTE CHART**
  • RSI: {df_15min['rsi'].iloc[-1]:.2f} {'[OB]' if df_15min['rsi'].iloc[-1] > 70 else '[OS]' if df_15min['rsi'].iloc[-1] < 30 else ''}
  • MACD: {df_15min['macd'].iloc[-1]:.4f} vs Signal: {df_15min['macd_signal'].iloc[-1]:.4f}
  • Stoch %K: {df_15min['stoch_k'].iloc[-1]:.2f}
  • Price vs BB: ${current_price:.2f} (Upper: ${df_15min['bb_bbh'].iloc[-1]:.2f}, Lower: ${df_15min['bb_bbl'].iloc[-1]:.2f})

→ **1-HOUR CHART**
  • RSI: {df_hourly['rsi'].iloc[-1]:.2f} {'[OB]' if df_hourly['rsi'].iloc[-1] > 70 else '[OS]' if df_hourly['rsi'].iloc[-1] < 30 else ''}
  • MACD: {df_hourly['macd'].iloc[-1]:.4f} vs Signal: {df_hourly['macd_signal'].iloc[-1]:.4f}
  • ADX: {df_hourly['adx'].iloc[-1]:.2f} (Trend: {'Strong' if df_hourly['adx'].iloc[-1] > 25 else 'Weak'})
  • DI+: {df_hourly['di_plus'].iloc[-1]:.2f} vs DI-: {df_hourly['di_minus'].iloc[-1]:.2f}
  • CMF: {df_hourly['cmf'].iloc[-1]:.3f} (Money Flow: {'Positive' if df_hourly['cmf'].iloc[-1] > 0 else 'Negative'})

→ **4-HOUR CHART**
  • RSI: {df_4h['rsi'].iloc[-1]:.2f} {'[OB]' if df_4h['rsi'].iloc[-1] > 70 else '[OS]' if df_4h['rsi'].iloc[-1] < 30 else ''}
  • MACD: {df_4h['macd'].iloc[-1]:.4f} vs Signal: {df_4h['macd_signal'].iloc[-1]:.4f}
  • ADX: {df_4h['adx'].iloc[-1]:.2f} (Trend: {'Strong' if df_4h['adx'].iloc[-1] > 25 else 'Weak'})
  • DI+: {df_4h['di_plus'].iloc[-1]:.2f} vs DI-: {df_4h['di_minus'].iloc[-1]:.2f}

{reflection}

═══════════════════════════════════════════
🎯 DECISION CRITERIA WITH REVERSE ENTRY
═══════════════════════════════════════════

**STANDARD ENTRY SCORING (60+ points to approve):**

For BUY Signals:
- 4h DI+ > DI-: +25 points
- 1h RSI 25-80: +25 points
- Price action favorable: +15 points
- Good entry timing: +10 points
- CMF positive 2+ timeframes: +10 points
- ADX > 18: +10-12 points
- No divergences: +10 points

For SELL Signals:
- 4h DI- > DI+: +25 points
- 1h RSI 20-75: +25 points
- Price action favorable: +15 points
- Good entry timing: +10 points
- CMF negative 2+ timeframes: +10 points
- ADX > 18: +10-12 points
- No divergences: +10 points

**🆕 REVERSE ENTRY CRITERIA (Override standard scoring):**
If extreme overbought/oversold conditions detected:
1. Check for 3+ extreme signals across timeframes
2. Verify clear divergence patterns
3. Confirm volume anomalies supporting reversal
4. If ALL conditions met → decision: "reverse"
5. Set modified_action to opposite direction
6. Use 30-50% position size for safety
7. Set tighter stop loss (1-1.5 ATR)

**DECISION FRAMEWORK:**
1. **APPROVE**: Score ≥ 60%, acceptable risk/reward
2. **REJECT**: High risk conditions OR score < 50%
3. **MODIFY**: Score 50-59%, reduce position or wait
4. **🆕 REVERSE**: Extreme conditions favor opposite direction

{json_template}

Return ONLY the JSON object. Start with {{ and end with }}
"""
        
        # AI API 호출
        logger.info(f"AI 시그널 검증 시작 - {symbol} {action}")
        
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {
                    "role": "system",
                    "content": """You are a professional crypto trading AI validator specialized in identifying reversal opportunities.

CRITICAL RULES:
1. ONLY return valid JSON - no explanations, no reasoning, no markdown
2. Start your response with { and end with }
3. Follow the exact JSON schema provided
4. Be especially alert for extreme overbought/oversold conditions that favor reversal
5. When extreme conditions are detected, consider "reverse" decision

REVERSE ENTRY PHILOSOPHY:
- Extreme overbought in uptrend = potential short opportunity
- Extreme oversold in downtrend = potential long opportunity
- But only with multiple confirmations across timeframes
- Risk management is crucial for counter-trend trades

Your response must be a single JSON object."""
                },
                {"role": "user", "content": prompt}
            ],
            response_format={'type': 'json_object'},
            temperature=0.1,
            max_tokens=1500
        )
        
        # 응답 처리
        ai_response_text = extract_ai_response(response)
        
        if not ai_response_text or not ai_response_text.strip():
            logger.error("AI 응답이 비어있음")
            return create_default_reject_decision("AI 응답 없음")
        
        # JSON 추출 및 파싱
        json_str = extract_json_from_text(ai_response_text)
        if not json_str:
            logger.error("JSON 추출 실패")
            return create_default_reject_decision("JSON 파싱 실패")
        
        try:
            parsed_json = json.loads(json_str)
            
            # 🆕 'reverse' 결정 처리
            if parsed_json.get('decision') == 'reverse':
                logger.warning(f"🔄 REVERSE ENTRY: {action} → {parsed_json.get('modified_action')}")
                logger.info(f"Reason: {parsed_json.get('reason')}")
                
                # 텔레그램 알림
                send_telegram_message(
                    f"🔄 *REVERSE ENTRY SIGNAL*\n"
                    f"Symbol: {symbol}\n"
                    f"Original: {action.upper()}\n"
                    f"Reversed to: {parsed_json.get('modified_action', '').upper()}\n"
                    f"Reason: Extreme market conditions favor reversal\n"
                    f"Confidence: {parsed_json.get('confidence', 0):.1%}"
                )
            
            # Pydantic 검증
            decision = TradingDecision.model_validate(parsed_json)
            result = decision.model_dump()
            
            logger.info(
                f"✅ AI 시그널 검증 완료: {result['decision'].upper()} "
                f"(신뢰도: {result['confidence']:.2%})"
            )
            
            # DB 저장
            conn = get_db_connection()
            c = conn.cursor()
            timestamp = datetime.now().isoformat()
            
            if not is_duplicate_trade_record(conn, symbol, action, 'AI_VALIDATION', time_window_seconds=10):
                c.execute("""INSERT INTO trades 
                             (timestamp, symbol, trade_type, ai_decision, action, percentage, reason, 
                              current_price, stop_loss, take_profit, pl_ratio, confidence, reflection) 
                             VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                          (timestamp, symbol, 'AI_VALIDATION', result['decision'], 
                           result['modified_action'] if result['decision'] == 'reverse' else action, 
                           result['percentage'], result['reason'], current_price, 
                           result['stop_loss_price'], result['take_profit_price'], 
                           result['pl_ratio'], result['confidence'], reflection))
                conn.commit()
            
            conn.close()
            
            return result
            
        except (json.JSONDecodeError, ValidationError) as e:
            logger.error(f"검증 실패: {e}")
            return create_default_reject_decision(f"검증 실패: {str(e)}")
    
    except Exception as e:
        logger.error(f"AI 시그널 검증 오류: {e}", exc_info=True)
        return create_default_reject_decision(f"시스템 오류: {str(e)}")

# ============ Position Monitoring with Enhanced Reversal Detection ============
def ai_monitor_position(symbol, side, entry_price, current_price, holding_time_minutes, pnl_percent, 
                        market_data, max_profit, max_loss, leverage=20):
    """
    🔄 수정됨: AI를 통한 포지션 모니터링 - 추세 역전 더 빨리 감지
    """
    try:
        client = OpenAI(api_key=os.getenv("DEEPSEEK_API_KEY"), base_url="https://api.deepseek.com")
        
        if not client.api_key:
            logger.error("DeepSeek API 키가 설정되지 않았습니다")
            return None
        
        # 시장 데이터 추출
        df_15min = market_data['df_15min']
        df_hourly = market_data['df_hourly'] 
        df_4h = market_data['df_4h']
        
        # 🔄 추세 역전 신호 감지 (수정된 함수 사용)
        reversal_signals = detect_trend_reversal_signals(df_15min, df_hourly, df_4h, side)
        
        # ATR 계산
        atr_15min = df_15min['atr'].iloc[-1] if 'atr' in df_15min.columns else current_price * 0.002
        atr_hourly = df_hourly['atr'].iloc[-1] if 'atr' in df_hourly.columns else current_price * 0.003
        
        # 보유 시간 계산
        holding_hours = holding_time_minutes / 60
        
        # JSON 템플릿
        json_template = """{
    "decision": "hold/close/partial_close",
    "percentage": 0-100,
    "reason": "detailed technical explanation",
    "exit_type": "take_profit/stop_loss/trend_reversal/risk_management/time_stop/none",
    "confidence": 0.0-1.0,
    "urgency": "immediate/soon/watch/none"
}"""

        # 🆕 추세 역전 경고 추가
        reversal_warning = ""
        if reversal_signals['urgency'] in ['immediate', 'soon']:
            reversal_warning = f"""
⚠️ **TREND REVERSAL WARNING:**
- Reversal Score: {reversal_signals['reversal_score']}/{reversal_signals['threshold_immediate']}
- Urgency Level: {reversal_signals['urgency'].upper()}
- Detected Signals: {', '.join(reversal_signals['signals'][:5])}
- Confidence: {reversal_signals['confidence']:.1%}

{'🚨 IMMEDIATE EXIT RECOMMENDED' if reversal_signals['urgency'] == 'immediate' else '⚡ PREPARE FOR EXIT SOON'}
"""

        prompt = f"""
═══════════════════════════════════════════
📊 POSITION MONITORING REQUEST
═══════════════════════════════════════════

**POSITION DETAILS:**
• Symbol: {symbol}
• Side: {'LONG' if side == 'buy' else 'SHORT'}
• Entry Price: ${entry_price:.2f}
• Current Price: ${current_price:.2f}
• Holding Time: {holding_hours:.1f} hours ({holding_time_minutes:.0f} minutes)

**PERFORMANCE METRICS:**
• Unrealized PnL: {pnl_percent:+.2f}% (Leveraged: {pnl_percent*leverage:+.2f}%)
• Max Profit Reached: {max_profit:+.2f}%
• Max Drawdown: {max_loss:.2f}%
• Price Movement: {((current_price - entry_price) / entry_price * 100):+.2f}%
• ATR-Normalized Move: {abs(current_price - entry_price) / atr_hourly:.1f} ATRs

{reversal_warning}

**TECHNICAL INDICATORS:**

→ **15-MINUTE** (Entry/Exit Timing)
  • RSI: {df_15min['rsi'].iloc[-1]:.2f}
  • MACD: {df_15min['macd'].iloc[-1]:.4f} vs Signal: {df_15min['macd_signal'].iloc[-1]:.4f}
  • Price vs BB: Current at {((current_price - df_15min['bb_bbm'].iloc[-1]) / (df_15min['bb_bbh'].iloc[-1] - df_15min['bb_bbl'].iloc[-1]) * 100):+.1f}% of band width

→ **1-HOUR** (Momentum)  
  • RSI: {df_hourly['rsi'].iloc[-1]:.2f}
  • ADX: {df_hourly['adx'].iloc[-1]:.2f}
  • DI+: {df_hourly['di_plus'].iloc[-1]:.2f} vs DI-: {df_hourly['di_minus'].iloc[-1]:.2f}
  • CMF: {df_hourly['cmf'].iloc[-1]:.3f}

→ **4-HOUR** (Trend)
  • RSI: {df_4h['rsi'].iloc[-1]:.2f}
  • ADX: {df_4h['adx'].iloc[-1]:.2f}
  • MACD Histogram: {df_4h['macd_diff'].iloc[-1]:.4f}

═══════════════════════════════════════════
🎯 EXIT DECISION FRAMEWORK (ENHANCED)
═══════════════════════════════════════════

**🔄 MODIFIED EXIT SIGNALS (More Sensitive):**

⚠️ **IMMEDIATE EXIT (Close 100%):**
- Reversal score ≥ {reversal_signals['threshold_immediate']} (Currently: {reversal_signals['reversal_score']})
- Multiple timeframe reversal confirmation
- Significant profit + reversal signals
- Stop loss approaching with adverse momentum

🔴 **STRONG EXIT (Close 75-100%):**
- Reversal score ≥ {reversal_signals['threshold_soon']} (Currently: {reversal_signals['reversal_score']})
- Momentum exhaustion on 2+ timeframes
- Profit > 2 ATR with weakening trend
- Extended time with diminishing returns

🟡 **PARTIAL EXIT (Close 25-50%):**
- Reversal score ≥ {reversal_signals['threshold_watch']} (Currently: {reversal_signals['reversal_score']})
- Mixed signals across timeframes
- Profit > 1 ATR with uncertainty
- Key resistance/support approaching

✅ **HOLD SIGNALS:**
- Reversal score < {reversal_signals['threshold_watch']}
- Strong trend continuation
- Momentum intact across timeframes
- No divergences detected

**PROFIT/LOSS CONTEXT:**
- Current: {pnl_percent:+.2f}% ({abs(current_price - entry_price) / atr_hourly:.1f} ATRs)
- Retracement from peak: {(max_profit - pnl_percent):.2f}%
{"- ⚠️ Significant retracement detected" if (max_profit - pnl_percent) > max_profit * 0.3 else ""}

{json_template}

**Your reason MUST include:**
1. Reversal signal assessment
2. Multi-timeframe trend analysis
3. Momentum evaluation
4. Risk/reward at current level
5. Time decay consideration

Return ONLY the JSON object.
"""
        
        # AI API 호출
        logger.info(f"포지션 모니터 - {symbol} {side} (PnL: {pnl_percent:+.2f}%, Reversal: {reversal_signals['urgency']})")
        
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {
                    "role": "system",
                    "content": """You are an elite crypto position manager with enhanced reversal detection.

CRITICAL RULES:
1. ONLY return valid JSON
2. Be more sensitive to reversal signals
3. Prioritize capital preservation
4. Act decisively on clear reversal patterns

ENHANCED EXIT PHILOSOPHY:
- Exit earlier on reversal signals (better safe than sorry)
- Don't wait for perfect confirmation if multiple warnings present
- Small losses are acceptable to avoid large ones
- Let winners run ONLY if momentum remains strong

Your response must be a single JSON object."""
                },
                {"role": "user", "content": prompt}
            ],
            response_format={'type': 'json_object'},
            temperature=0.1,
            max_tokens=1000
        )
        
        # 응답 처리
        ai_response_text = extract_ai_response(response)
        
        if not ai_response_text:
            logger.error("AI 응답 없음")
            return None
        
        json_str = extract_json_from_text(ai_response_text)
        if not json_str:
            logger.error("JSON 추출 실패")
            return None
        
        try:
            parsed_json = json.loads(json_str)
            decision = MonitorPositionDecision.model_validate(parsed_json)
            result = decision.model_dump()
            
            logger.info(f"✅ 모니터링 결정: {result['decision'].upper()} ({result['urgency']})")
            
            # DB 저장
            conn = get_db_connection()
            c = conn.cursor()
            timestamp = datetime.now().isoformat()
            
            if not is_duplicate_trade_record(conn, symbol, 'monitor', 'AI_MONITOR', time_window_seconds=60):
                c.execute("""INSERT INTO trades 
                             (timestamp, symbol, trade_type, ai_decision, action, percentage, reason, 
                              current_price, confidence) 
                             VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                          (timestamp, symbol, 'AI_MONITOR', result['decision'], 'monitor',
                           result['percentage'], result['reason'], current_price, result['confidence']))
                conn.commit()
            
            conn.close()
            
            return result
            
        except (json.JSONDecodeError, ValidationError) as e:
            logger.error(f"모니터링 검증 실패: {e}")
            return None
    
    except Exception as e:
        logger.error(f"포지션 모니터링 오류: {e}", exc_info=True)
        return None

# 나머지 함수들 추가...
# (execute_trade, close_position, monitor_positions_loop, webhook handler 등)

# ============ Trading Execution Functions ============
def execute_trade(user_id, symbol, action, percentage, stop_loss_price, take_profit_price, reason="Manual"):
    """특정 유저의 거래 실행"""
    try:
        user_exchange = exchanges.get(user_id)
        if not user_exchange:
            logger.error(f"Exchange not found for {user_id}")
            return None
            
        user_config = USER_CONFIGS[user_id]
        
        # 잔액 조회
        balance = user_exchange.fetch_balance()
        free_usdt = balance['USDT']['free']
        
        # 거래 금액 계산
        trade_amount_usdt = free_usdt * (percentage / 100) * 0.95  # 5% 여유
        
        # 현재가 조회
        ticker = user_exchange.fetch_ticker(symbol)
        current_price = ticker['last']
        
        # 수량 계산
        quantity = trade_amount_usdt / current_price
        
        # 최소 거래 단위 확인
        markets = user_exchange.load_markets()
        market = markets[symbol]
        min_qty = market['limits']['amount']['min']
        
        if quantity < min_qty:
            logger.warning(f"{user_config['name']}: 거래 수량이 최소값 미만 ({quantity:.4f} < {min_qty})")
            return None
        
        # 수량 정밀도 조정
        precision = market['precision']['amount']
        quantity = user_exchange.amount_to_precision(symbol, quantity)
        
        # 포지션 오픈
        order = user_exchange.create_market_order(
            symbol=symbol,
            type='market',
            side=action,
            amount=quantity
        )
        
        logger.info(f"✅ {user_config['name']} - {action.upper()} 주문 실행: {symbol} {quantity} @ ${current_price:.2f}")
        
        # SL/TP 설정 (Binance Futures)
        if stop_loss_price and take_profit_price:
            try:
                # Stop Loss 주문
                sl_side = 'sell' if action == 'buy' else 'buy'
                user_exchange.create_order(
                    symbol=symbol,
                    type='stop_market',
                    side=sl_side,
                    amount=quantity,
                    stopPrice=stop_loss_price,
                    params={'closePosition': True}
                )
                
                # Take Profit 주문
                tp_side = 'sell' if action == 'buy' else 'buy'
                user_exchange.create_order(
                    symbol=symbol,
                    type='take_profit_market',
                    side=tp_side,
                    amount=quantity,
                    stopPrice=take_profit_price,
                    params={'closePosition': True}
                )
                
                logger.info(f"✅ {user_config['name']} - SL: ${stop_loss_price:.2f}, TP: ${take_profit_price:.2f} 설정 완료")
            except Exception as e:
                logger.error(f"{user_config['name']} - SL/TP 설정 실패: {e}")
        
        return order
        
    except Exception as e:
        logger.error(f"{USER_CONFIGS[user_id]['name']} - 거래 실행 오류: {e}")
        return None

def close_position(user_id, symbol, percentage=100):
    """특정 유저의 포지션 청산"""
    try:
        user_exchange = exchanges.get(user_id)
        if not user_exchange:
            return None
            
        # 현재 포지션 조회
        positions = user_exchange.fetch_positions([symbol])
        
        if not positions:
            logger.warning(f"{USER_CONFIGS[user_id]['name']}: {symbol} 포지션 없음")
            return None
        
        position = positions[0]
        contracts = abs(position['contracts'])
        side = 'sell' if position['side'] == 'long' else 'buy'
        
        # 부분 청산 계산
        close_contracts = contracts * (percentage / 100)
        close_contracts = user_exchange.amount_to_precision(symbol, close_contracts)
        
        # 청산 주문
        order = user_exchange.create_market_order(
            symbol=symbol,
            type='market',
            side=side,
            amount=close_contracts,
            params={'reduceOnly': True}
        )
        
        logger.info(f"✅ {USER_CONFIGS[user_id]['name']} - 포지션 청산 ({percentage}%): {symbol}")
        
        return order
        
    except Exception as e:
        logger.error(f"{USER_CONFIGS[user_id]['name']} - 포지션 청산 오류: {e}")
        return None

# ============ Position Monitoring Loop ============
def monitor_positions_loop():
    """백그라운드에서 포지션 모니터링"""
    global IS_MONITORING, ACTIVE_POSITIONS
    
    while IS_MONITORING:
        try:
            time.sleep(AI_MONITOR_INTERVAL * 60)  # 분 단위를 초로 변환
            
            if not ACTIVE_POSITIONS:
                continue
            
            # Primary User만 AI 모니터링 수행
            primary_exchange = exchanges.get('USER1')
            if not primary_exchange:
                continue
            
            for symbol, position_info in list(ACTIVE_POSITIONS.items()):
                try:
                    # 시장 데이터 수집
                    market_data = get_market_data(symbol)
                    if not market_data:
                        continue
                    
                    current_price = market_data['current_price']
                    entry_price = position_info['entry_price']
                    side = position_info['side']
                    entry_time = position_info['entry_time']
                    
                    # 보유 시간 계산
                    holding_time = datetime.now() - entry_time
                    holding_minutes = holding_time.total_seconds() / 60
                    
                    # PnL 계산
                    if side == 'buy':
                        pnl_percent = ((current_price - entry_price) / entry_price) * 100
                    else:
                        pnl_percent = ((entry_price - current_price) / entry_price) * 100
                    
                    # 최대 이익/손실 업데이트
                    if 'max_profit' not in position_info:
                        position_info['max_profit'] = pnl_percent
                        position_info['max_loss'] = pnl_percent
                    else:
                        position_info['max_profit'] = max(position_info['max_profit'], pnl_percent)
                        position_info['max_loss'] = min(position_info['max_loss'], pnl_percent)
                    
                    # AI 모니터링
                    decision = ai_monitor_position(
                        symbol=symbol,
                        side=side,
                        entry_price=entry_price,
                        current_price=current_price,
                        holding_time_minutes=holding_minutes,
                        pnl_percent=pnl_percent,
                        market_data=market_data,
                        max_profit=position_info['max_profit'],
                        max_loss=abs(position_info['max_loss'])
                    )
                    
                    if decision and decision['decision'] != 'hold':
                        logger.warning(f"🔔 AI 청산 신호: {symbol} - {decision['decision']} ({decision['percentage']}%)")
                        
                        # 모든 유저 포지션 청산
                        for user_id in exchanges.keys():
                            close_position(user_id, symbol, decision['percentage'])
                        
                        # 포지션 정보 업데이트
                        if decision['percentage'] >= 100:
                            del ACTIVE_POSITIONS[symbol]
                        
                        # 텔레그램 알림
                        send_telegram_message(
                            f"🔔 *AI 포지션 청산*\n"
                            f"Symbol: {symbol}\n"
                            f"결정: {decision['decision']} ({decision['percentage']}%)\n"
                            f"이유: {decision['reason']}\n"
                            f"PnL: {pnl_percent:+.2f}%"
                        )
                        
                except Exception as e:
                    logger.error(f"포지션 모니터링 오류 ({symbol}): {e}")
                    
        except Exception as e:
            logger.error(f"모니터링 루프 오류: {e}")

# ============ Webhook Handler ============
@app.route('/webhook', methods=['POST'])
def webhook():
    """🔄 수정됨: TradingView 웹훅 처리 - 반대 진입 기능 포함"""
    try:
        data = request.json
        logger.info(f"웹훅 수신: {data}")
        
        # 필수 필드 검증
        required_fields = ['symbol', 'action']
        for field in required_fields:
            if field not in data:
                return jsonify({'error': f'Missing {field}'}), 400
        
        symbol = data['symbol']
        action = data['action'].lower()
        
        # 포지션 청산 처리
        if action in ['close', 'close_long', 'close_short']:
            for user_id in exchanges.keys():
                close_position(user_id, symbol, 100)
            
            if symbol in ACTIVE_POSITIONS:
                del ACTIVE_POSITIONS[symbol]
            
            send_telegram_message(f"📤 포지션 청산 완료: {symbol}")
            return jsonify({'status': 'closed'}), 200
        
        # buy/sell 신호 처리
        if action not in ['buy', 'sell']:
            return jsonify({'error': 'Invalid action'}), 400
        
        # 시장 데이터 수집
        market_data = get_market_data(symbol)
        if not market_data:
            return jsonify({'error': 'Failed to get market data'}), 500
        
        # Reflection 생성
        conn = get_db_connection()
        reflection = generate_trade_reflection(conn, symbol, action, None, market_data)
        conn.close()
        
        # AI 검증 (Primary User만)
        ai_decision = ai_validate_trading_signal(symbol, action, market_data, reflection)
        
        # 🆕 반대 진입 처리
        if ai_decision['decision'] == 'reverse':
            logger.warning(f"🔄 REVERSE ENTRY: {action} → {ai_decision['modified_action']}")
            action = ai_decision['modified_action']  # 액션 반전
            
            # 텔레그램 알림
            send_telegram_message(
                f"🔄 *반대 진입 실행*\n"
                f"원본 신호: {data['action'].upper()}\n"
                f"변경된 방향: {action.upper()}\n"
                f"이유: 극단적 과매수/과매도 상태\n"
                f"포지션 크기: {ai_decision['percentage']}%"
            )
        
        # AI 승인된 경우만 거래 실행
        if ai_decision['decision'] in ['approve', 'reverse']:
            # 모든 유저에게 거래 실행
            success_count = 0
            for user_id in exchanges.keys():
                order = execute_trade(
                    user_id=user_id,
                    symbol=symbol,
                    action=action,
                    percentage=ai_decision['percentage'],
                    stop_loss_price=ai_decision['stop_loss_price'],
                    take_profit_price=ai_decision['take_profit_price'],
                    reason=ai_decision['reason']
                )
                if order:
                    success_count += 1
            
            # 포지션 정보 저장
            if success_count > 0:
                ACTIVE_POSITIONS[symbol] = {
                    'side': action,
                    'entry_price': market_data['current_price'],
                    'entry_time': datetime.now(),
                    'sl_price': ai_decision['stop_loss_price'],
                    'tp_price': ai_decision['take_profit_price']
                }
            
            # 텔레그램 알림
            send_telegram_message(
                f"✅ *거래 실행 완료*\n"
                f"Symbol: {symbol}\n"
                f"방향: {action.upper()}\n"
                f"진입가: ${market_data['current_price']:.2f}\n"
                f"SL: ${ai_decision['stop_loss_price']:.2f}\n"
                f"TP: ${ai_decision['take_profit_price']:.2f}\n"
                f"신뢰도: {ai_decision['confidence']:.1%}\n"
                f"{'🔄 반대 진입' if ai_decision['decision'] == 'reverse' else ''}"
            )
            
            return jsonify({
                'status': 'executed',
                'decision': ai_decision['decision'],
                'users_executed': success_count
            }), 200
        
        else:
            # AI 거부
            send_telegram_message(
                f"❌ *거래 거부됨*\n"
                f"Symbol: {symbol}\n"
                f"요청: {action.upper()}\n"
                f"이유: {ai_decision['reason']}"
            )
            
            return jsonify({
                'status': 'rejected',
                'reason': ai_decision['reason']
            }), 200
    
    except Exception as e:
        logger.error(f"웹훅 처리 오류: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

# ============ Status Endpoints ============
@app.route('/status', methods=['GET'])
def status():
    """시스템 상태 확인"""
    try:
        status_info = {
            'server': 'running',
            'monitoring': IS_MONITORING,
            'active_positions': len(ACTIVE_POSITIONS),
            'users': {}
        }
        
        for user_id, user_exchange in exchanges.items():
            try:
                balance = user_exchange.fetch_balance()
                positions = user_exchange.fetch_positions()
                
                status_info['users'][user_id] = {
                    'name': USER_CONFIGS[user_id]['name'],
                    'balance': balance['USDT']['free'],
                    'positions': len(positions)
                }
            except Exception as e:
                status_info['users'][user_id] = {
                    'name': USER_CONFIGS[user_id]['name'],
                    'error': str(e)
                }
        
        return jsonify(status_info), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/positions', methods=['GET'])
def get_positions():
    """현재 포지션 조회"""
    try:
        all_positions = {}
        
        for user_id, user_exchange in exchanges.items():
            try:
                positions = user_exchange.fetch_positions()
                all_positions[USER_CONFIGS[user_id]['name']] = [
                    {
                        'symbol': pos['symbol'],
                        'side': pos['side'],
                        'contracts': pos['contracts'],
                        'pnl': pos['percentage'],
                        'unrealized_pnl': pos['unrealizedPnl']
                    }
                    for pos in positions if pos['contracts'] > 0
                ]
            except Exception as e:
                all_positions[USER_CONFIGS[user_id]['name']] = f"Error: {e}"
        
        return jsonify(all_positions), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ============ Main Execution ============
if __name__ == '__main__':
    # DB 초기화
    conn = init_db()
    conn.close()
    
    # 모니터링 시작
    IS_MONITORING = True
    MONITOR_THREAD = threading.Thread(target=monitor_positions_loop, daemon=True)
    MONITOR_THREAD.start()
    logger.info("✅ 포지션 모니터링 시작")
    
    # 시작 메시지
    send_telegram_message(
        f"🚀 *트레이딩 시스템 v7 ENHANCED 시작*\n"
        f"서버 포트: {SERVER_PORT}\n"
        f"활성 유저: {len(exchanges)}명\n"
        f"AI 모니터링: {AI_MONITOR_INTERVAL}분 간격\n"
        f"🔄 신규 기능:\n"
        f"- 단기 TP 설정\n"
        f"- 빠른 추세 역전 감지\n"
        f"- 극단 상황 반대 진입"
    )
    
    # Flask 서버 시작
    app.run(host='0.0.0.0', port=SERVER_PORT, debug=False)
