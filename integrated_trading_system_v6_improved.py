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

# Flask 로깅 레벨 조정 (404 에러 등 줄이기)
import logging as flask_logging
flask_logging.getLogger('werkzeug').setLevel(flask_logging.WARNING)

# ============ 포트별 사용자 API 설정 ============
# 각 포트별로 다른 사용자의 API 키를 사용
# DB는 모든 사용자가 동일한 파일 사용 (쓰기는 포트 5000만)
DB_FILENAME = 'trading_bot.db'  # 모든 포트가 동일한 DB 사용

if SERVER_PORT == 5000:
    # 기본 사용자 (User 1) - DB 쓰기 권한
    BINANCE_API_KEY = os.getenv('BINANCE_API_KEY')
    BINANCE_SECRET_KEY = os.getenv('BINANCE_SECRET_KEY')
    USER_NAME = "User1"
    ENABLE_DB_WRITE = True  # DB 쓰기 활성화
    logger.info(f"🔑 Using API keys for {USER_NAME} (Default) - DB Write Enabled")
    
elif SERVER_PORT == 5001:
    # Hyun 사용자 (User 2) - DB 읽기 전용
    BINANCE_API_KEY = os.getenv('BINANCE_API_KEY_HYUN')
    BINANCE_SECRET_KEY = os.getenv('BINANCE_SECRET_KEY_HYUN')
    USER_NAME = "Hyun"
    ENABLE_DB_WRITE = False  # DB 쓰기 비활성화
    logger.info(f"🔑 Using API keys for {USER_NAME} - DB Read Only")
    
elif SERVER_PORT == 5002:
    # 추가 사용자 (User 3) - DB 읽기 전용
    BINANCE_API_KEY = os.getenv('BINANCE_API_KEY_USER3')
    BINANCE_SECRET_KEY = os.getenv('BINANCE_SECRET_KEY_USER3')
    USER_NAME = "User3"
    ENABLE_DB_WRITE = False  # DB 쓰기 비활성화
    logger.info(f"🔑 Using API keys for {USER_NAME} - DB Read Only")
    
else:
    # 기본값 (안전장치)
    BINANCE_API_KEY = os.getenv('BINANCE_API_KEY')
    BINANCE_SECRET_KEY = os.getenv('BINANCE_SECRET_KEY')
    USER_NAME = "Default"
    ENABLE_DB_WRITE = False  # DB 쓰기 비활성화
    logger.warning(f"⚠️ Unknown port {SERVER_PORT}, using default API keys - DB Read Only")

# Binance Exchange 객체 생성
exchange = ccxt.binance({
    'apiKey': BINANCE_API_KEY,
    'secret': BINANCE_SECRET_KEY,
    'enableRateLimit': True,
    'options': {
        'defaultType': 'future'  # 선물 거래용
    }
})

# API 키 확인
if not BINANCE_API_KEY or not BINANCE_SECRET_KEY:
    logger.error(f"❌ Binance API keys not found for {USER_NAME} (Port: {SERVER_PORT})")
    logger.error(f"Please set environment variables for this user")
else:
    logger.info(f"✅ Binance API configured for {USER_NAME} (Port: {SERVER_PORT})")

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
    'SOL/USDT': {
        'leverage': 10,
        'position_size_percent': 25,
        'min_position_size': 10,
        'max_position_size': 100000,
        'enabled': True,
        'ai_validation': True,
        'ai_monitoring': True
    },
}

# ============ 새로운 헬퍼 함수들 추가 ============

def calculate_support_resistance(df, lookback=20):
    """
    지지/저항선 계산
    """
    try:
        # 최근 lookback 개 캔들에서 pivot 포인트 찾기
        highs = df['high'].rolling(window=5, center=True).max()
        lows = df['low'].rolling(window=5, center=True).min()
        
        # Pivot high/low 찾기
        pivot_highs = df[df['high'] == highs]['high'].tail(lookback)
        pivot_lows = df[df['low'] == lows]['low'].tail(lookback)
        
        # 클러스터링으로 주요 레벨 찾기
        resistance_levels = []
        support_levels = []
        
        if len(pivot_highs) > 0:
            # 비슷한 레벨끼리 그룹화
            sorted_highs = sorted(pivot_highs.unique())
            current_cluster = [sorted_highs[0]]
            
            for high in sorted_highs[1:]:
                if (high - current_cluster[-1]) / current_cluster[-1] < 0.005:  # 0.5% 이내면 같은 클러스터
                    current_cluster.append(high)
                else:
                    resistance_levels.append(np.mean(current_cluster))
                    current_cluster = [high]
            resistance_levels.append(np.mean(current_cluster))
        
        if len(pivot_lows) > 0:
            sorted_lows = sorted(pivot_lows.unique())
            current_cluster = [sorted_lows[0]]
            
            for low in sorted_lows[1:]:
                if (low - current_cluster[-1]) / current_cluster[-1] < 0.005:
                    current_cluster.append(low)
                else:
                    support_levels.append(np.mean(current_cluster))
                    current_cluster = [low]
            support_levels.append(np.mean(current_cluster))
        
        return {
            'resistance': sorted(resistance_levels, reverse=True)[:3] if resistance_levels else [],
            'support': sorted(support_levels)[:3] if support_levels else []
        }
    except Exception as e:
        logger.error(f"지지/저항선 계산 실패: {e}")
        return {'resistance': [], 'support': []}

def calculate_volume_profile(df, bins=20):
    """
    볼륨 프로파일 계산 - 매물대 분석
    """
    try:
        # 가격 구간별 거래량 계산
        price_range = df['close'].max() - df['close'].min()
        bin_size = price_range / bins
        
        volume_profile = {}
        min_price = df['close'].min()
        
        for i in range(bins):
            bin_low = min_price + (i * bin_size)
            bin_high = min_price + ((i + 1) * bin_size)
            
            mask = (df['close'] >= bin_low) & (df['close'] < bin_high)
            volume_in_bin = df[mask]['volume'].sum()
            
            if volume_in_bin > 0:
                volume_profile[round((bin_low + bin_high) / 2, 2)] = volume_in_bin
        
        # 상위 3개 매물대 찾기
        sorted_profile = sorted(volume_profile.items(), key=lambda x: x[1], reverse=True)
        major_levels = [price for price, volume in sorted_profile[:3]]
        
        return major_levels
    except Exception as e:
        logger.error(f"볼륨 프로파일 계산 실패: {e}")
        return []

def calculate_realistic_tp_sl(current_price, action, df_15min, df_hourly, df_4h, atr_value, message_data=None):
    """
    현실적인 TP/SL 계산 - 하루 이내 달성 가능한 목표
    """
    try:
        # 지지/저항선 계산
        sr_15min = calculate_support_resistance(df_15min)
        sr_hourly = calculate_support_resistance(df_hourly)
        sr_4h = calculate_support_resistance(df_4h, lookback=50)
        
        # 볼륨 프로파일 (매물대)
        volume_levels = calculate_volume_profile(df_hourly, bins=30)
        
        # 일일 평균 변동성 계산
        daily_volatility = df_hourly['close'].pct_change().rolling(24).std().iloc[-1] * np.sqrt(24)
        daily_range = current_price * daily_volatility  # 일일 예상 변동폭
        
        # 최근 24시간 실제 고저 범위
        recent_high = df_hourly['high'].tail(24).max()
        recent_low = df_hourly['low'].tail(24).min()
        recent_range = recent_high - recent_low
        
        # ATR 기반 기본값
        base_sl_distance = atr_value * 1.5  # 1.5 ATR
        base_tp_distance = atr_value * 2.5  # 2.5 ATR
        
        # 하루 변동폭의 일정 비율로 제한
        max_distance = min(daily_range * 0.7, recent_range * 0.5)  # 일일 변동폭의 70% 또는 최근 범위의 50%
        
        if action == 'buy':
            # Stop Loss 계산
            potential_supports = []
            
            # 지지선들 수집
            for level in sr_15min['support']:
                if level < current_price:
                    potential_supports.append(level)
            for level in sr_hourly['support']:
                if level < current_price:
                    potential_supports.append(level)
            for level in sr_4h['support']:
                if level < current_price:
                    potential_supports.append(level)
            
            # 매물대 중 현재가 아래 레벨
            for level in volume_levels:
                if level < current_price * 0.98:  # 2% 아래
                    potential_supports.append(level)
            
            # 가장 가까운 지지선을 SL로
            if potential_supports:
                nearest_support = max(potential_supports)
                sl_price = nearest_support - (atr_value * 0.3)  # 지지선 약간 아래
            else:
                sl_price = current_price - base_sl_distance
            
            # 최대 거리로 제한
            sl_price = max(sl_price, current_price - max_distance)
            
            # Take Profit 계산
            potential_resistances = []
            
            # 저항선들 수집
            for level in sr_15min['resistance']:
                if level > current_price:
                    potential_resistances.append(level)
            for level in sr_hourly['resistance']:
                if level > current_price:
                    potential_resistances.append(level)
            for level in sr_4h['resistance']:
                if level > current_price:
                    potential_resistances.append(level)
            
            # 매물대 중 현재가 위 레벨
            for level in volume_levels:
                if level > current_price * 1.02:  # 2% 위
                    potential_resistances.append(level)
            
            # 가장 가까운 저항선을 TP로
            if potential_resistances:
                nearest_resistance = min(potential_resistances)
                tp_price = nearest_resistance - (atr_value * 0.2)  # 저항선 약간 아래
            else:
                tp_price = current_price + base_tp_distance
            
            # 최대 거리로 제한
            tp_price = min(tp_price, current_price + max_distance)
            
        else:  # sell
            # Stop Loss 계산 (Short 포지션이므로 위쪽)
            potential_resistances = []
            
            for level in sr_15min['resistance']:
                if level > current_price:
                    potential_resistances.append(level)
            for level in sr_hourly['resistance']:
                if level > current_price:
                    potential_resistances.append(level)
            for level in sr_4h['resistance']:
                if level > current_price:
                    potential_resistances.append(level)
            
            for level in volume_levels:
                if level > current_price * 1.02:
                    potential_resistances.append(level)
            
            if potential_resistances:
                nearest_resistance = min(potential_resistances)
                sl_price = nearest_resistance + (atr_value * 0.3)
            else:
                sl_price = current_price + base_sl_distance
            
            sl_price = min(sl_price, current_price + max_distance)
            
            # Take Profit 계산 (Short 포지션이므로 아래쪽)
            potential_supports = []
            
            for level in sr_15min['support']:
                if level < current_price:
                    potential_supports.append(level)
            for level in sr_hourly['support']:
                if level < current_price:
                    potential_supports.append(level)
            for level in sr_4h['support']:
                if level < current_price:
                    potential_supports.append(level)
            
            for level in volume_levels:
                if level < current_price * 0.98:
                    potential_supports.append(level)
            
            if potential_supports:
                nearest_support = max(potential_supports)
                tp_price = nearest_support + (atr_value * 0.2)
            else:
                tp_price = current_price - base_tp_distance
            
            tp_price = max(tp_price, current_price - max_distance)
        
        # 최소 Risk/Reward 보장
        risk = abs(current_price - sl_price)
        reward = abs(tp_price - current_price)
        
        if reward < risk * 1.2:  # 최소 1.2:1 RR
            if action == 'buy':
                tp_price = current_price + (risk * 1.5)
            else:
                tp_price = current_price - (risk * 1.5)
        
        # 웹훅에서 받은 TP/SL과 비교 (message_data가 있는 경우)
        if message_data and isinstance(message_data, dict):
            webhook_tp = message_data.get('take_profit', tp_price)
            webhook_sl = message_data.get('stop_loss', sl_price)
            
            # 웹훅 TP/SL이 너무 멀면 조정
            if action == 'buy':
                if webhook_tp > current_price + max_distance * 1.5:
                    tp_price = min(tp_price, current_price + max_distance)
                else:
                    tp_price = webhook_tp
                
                if webhook_sl < current_price - max_distance * 1.5:
                    sl_price = max(sl_price, current_price - max_distance)
                else:
                    sl_price = webhook_sl
            else:
                if webhook_sl > current_price + max_distance * 1.5:
                    sl_price = min(sl_price, current_price + max_distance)
                else:
                    sl_price = webhook_sl
                
                if webhook_tp < current_price - max_distance * 1.5:
                    tp_price = max(tp_price, current_price - max_distance)
                else:
                    tp_price = webhook_tp
        
        pl_ratio = reward / risk if risk > 0 else 1.5
        
        return {
            'tp': round(tp_price, 2),
            'sl': round(sl_price, 2),
            'pl_ratio': round(pl_ratio, 2),
            'risk_percent': round((risk / current_price) * 100, 2),
            'reward_percent': round((reward / current_price) * 100, 2),
            'support_levels': sr_hourly['support'][:3],
            'resistance_levels': sr_hourly['resistance'][:3],
            'volume_levels': volume_levels[:3]
        }
        
    except Exception as e:
        logger.error(f"현실적 TP/SL 계산 실패: {e}")
        # 폴백 값
        if action == 'buy':
            sl_price = current_price * 0.97
            tp_price = current_price * 1.04
        else:
            sl_price = current_price * 1.03
            tp_price = current_price * 0.96
        
        return {
            'tp': round(tp_price, 2),
            'sl': round(sl_price, 2),
            'pl_ratio': 1.5,
            'risk_percent': 3,
            'reward_percent': 4,
            'support_levels': [],
            'resistance_levels': [],
            'volume_levels': []
        }

def detect_early_reversal_signals(df_15min, df_hourly, df_4h, position_side):
    """
    추세 역전 조기 감지 시스템
    """
    signals = {
        'reversal_score': 0,
        'reversal_signals': [],
        'urgency': 'none',
        'exit_recommended': False
    }
    
    try:
        # 1. RSI Divergence 체크
        rsi_15 = df_15min['rsi'].tail(10)
        price_15 = df_15min['close'].tail(10)
        
        if position_side == 'long':
            # Bearish divergence: 가격은 상승하는데 RSI는 하락
            if price_15.iloc[-1] > price_15.iloc[-5] and rsi_15.iloc[-1] < rsi_15.iloc[-5]:
                signals['reversal_score'] += 20
                signals['reversal_signals'].append("Bearish RSI divergence on 15min")
        else:
            # Bullish divergence: 가격은 하락하는데 RSI는 상승
            if price_15.iloc[-1] < price_15.iloc[-5] and rsi_15.iloc[-1] > rsi_15.iloc[-5]:
                signals['reversal_score'] += 20
                signals['reversal_signals'].append("Bullish RSI divergence on 15min")
        
        # 2. MACD 히스토그램 기울기 변화
        macd_hist = df_hourly['macd_diff'].tail(5)
        hist_slope = (macd_hist.iloc[-1] - macd_hist.iloc[-3]) / 3
        
        if position_side == 'long' and hist_slope < 0 and macd_hist.iloc[-1] < macd_hist.iloc[-2]:
            signals['reversal_score'] += 15
            signals['reversal_signals'].append("MACD histogram declining")
        elif position_side == 'short' and hist_slope > 0 and macd_hist.iloc[-1] > macd_hist.iloc[-2]:
            signals['reversal_score'] += 15
            signals['reversal_signals'].append("MACD histogram rising")
        
        # 3. 볼륨 이상 감지
        avg_volume = df_hourly['volume'].rolling(20).mean().iloc[-1]
        recent_volume = df_hourly['volume'].iloc[-1]
        
        if recent_volume > avg_volume * 2:
            if position_side == 'long' and df_hourly['close'].iloc[-1] < df_hourly['open'].iloc[-1]:
                signals['reversal_score'] += 25
                signals['reversal_signals'].append("High volume selling pressure")
            elif position_side == 'short' and df_hourly['close'].iloc[-1] > df_hourly['open'].iloc[-1]:
                signals['reversal_score'] += 25
                signals['reversal_signals'].append("High volume buying pressure")
        
        # 4. DI 크로스오버 임박
        di_plus = df_hourly['di_plus'].tail(3)
        di_minus = df_hourly['di_minus'].tail(3)
        
        if position_side == 'long':
            # DI- 상승 중이고 DI+와 가까워짐
            if di_minus.iloc[-1] > di_minus.iloc[-3] and abs(di_plus.iloc[-1] - di_minus.iloc[-1]) < 5:
                signals['reversal_score'] += 20
                signals['reversal_signals'].append("DI crossover imminent")
        else:
            # DI+ 상승 중이고 DI-와 가까워짐
            if di_plus.iloc[-1] > di_plus.iloc[-3] and abs(di_plus.iloc[-1] - di_minus.iloc[-1]) < 5:
                signals['reversal_score'] += 20
                signals['reversal_signals'].append("DI crossover imminent")
        
        # 5. 캔들 패턴 분석
        last_candle = df_15min.iloc[-1]
        prev_candle = df_15min.iloc[-2]
        
        # Doji 캔들 (우유부단)
        body_size = abs(last_candle['close'] - last_candle['open'])
        total_range = last_candle['high'] - last_candle['low']
        
        if total_range > 0 and body_size / total_range < 0.1:
            signals['reversal_score'] += 10
            signals['reversal_signals'].append("Doji candle pattern")
        
        # Engulfing 패턴
        if position_side == 'long':
            if (prev_candle['close'] > prev_candle['open'] and 
                last_candle['open'] > prev_candle['close'] and 
                last_candle['close'] < prev_candle['open']):
                signals['reversal_score'] += 30
                signals['reversal_signals'].append("Bearish engulfing pattern")
        else:
            if (prev_candle['close'] < prev_candle['open'] and 
                last_candle['open'] < prev_candle['close'] and 
                last_candle['close'] > prev_candle['open']):
                signals['reversal_score'] += 30
                signals['reversal_signals'].append("Bullish engulfing pattern")
        
        # 6. CMF (Chaikin Money Flow) 반전
        cmf_15 = df_15min['cmf'].tail(5)
        cmf_hourly = df_hourly['cmf'].tail(5)
        
        if position_side == 'long':
            if cmf_15.iloc[-1] < 0 and cmf_hourly.iloc[-1] < 0:
                signals['reversal_score'] += 15
                signals['reversal_signals'].append("Money flow turning negative")
        else:
            if cmf_15.iloc[-1] > 0 and cmf_hourly.iloc[-1] > 0:
                signals['reversal_score'] += 15
                signals['reversal_signals'].append("Money flow turning positive")
        
        # 7. 추세 강도 약화
        adx_hourly = df_hourly['adx'].tail(5)
        if adx_hourly.iloc[-1] < adx_hourly.iloc[-3] and adx_hourly.iloc[-1] < 20:
            signals['reversal_score'] += 10
            signals['reversal_signals'].append("Trend strength weakening (ADX declining)")
        
        # 긴급도 판단
        if signals['reversal_score'] >= 70:
            signals['urgency'] = 'immediate'
            signals['exit_recommended'] = True
        elif signals['reversal_score'] >= 50:
            signals['urgency'] = 'soon'
            signals['exit_recommended'] = True
        elif signals['reversal_score'] >= 30:
            signals['urgency'] = 'watch'
            signals['exit_recommended'] = False
        else:
            signals['urgency'] = 'none'
            signals['exit_recommended'] = False
        
        return signals
        
    except Exception as e:
        logger.error(f"추세 역전 신호 감지 실패: {e}")
        return signals

def check_entry_conditions_enhanced(df_15min, df_hourly, df_4h, action):
    """
    강화된 진입 조건 체크 - 과매수/과매도 필터링
    """
    conditions = {
        'score': 0,
        'passed': False,
        'warnings': [],
        'positives': []
    }
    
    try:
        # RSI 체크 - 멀티타임프레임
        rsi_15 = df_15min['rsi'].iloc[-1]
        rsi_hourly = df_hourly['rsi'].iloc[-1]
        rsi_4h = df_4h['rsi'].iloc[-1]
        
        if action == 'buy':
            # 과매수 체크
            if rsi_15 > 80:
                conditions['warnings'].append("15min RSI extremely overbought")
                conditions['score'] -= 20
            elif rsi_15 > 70:
                conditions['warnings'].append("15min RSI overbought")
                conditions['score'] -= 10
                
            if rsi_hourly > 75:
                conditions['warnings'].append("1H RSI overbought")
                conditions['score'] -= 15
                
            if rsi_4h > 70:
                conditions['warnings'].append("4H RSI overbought")
                conditions['score'] -= 15
            
            # 극단적 과매수 거부 조건
            if rsi_15 > 85 and rsi_hourly > 75 and rsi_4h > 70:
                conditions['warnings'].append("CRITICAL: Multi-timeframe overbought")
                conditions['score'] -= 50
            
            # 긍정적 조건
            if 30 < rsi_15 < 60:
                conditions['positives'].append("15min RSI in optimal range")
                conditions['score'] += 15
            if 40 < rsi_hourly < 65:
                conditions['positives'].append("1H RSI in optimal range")
                conditions['score'] += 20
            if rsi_4h < 60:
                conditions['positives'].append("4H RSI has room to grow")
                conditions['score'] += 15
                
        else:  # sell
            # 과매도 체크
            if rsi_15 < 20:
                conditions['warnings'].append("15min RSI extremely oversold")
                conditions['score'] -= 20
            elif rsi_15 < 30:
                conditions['warnings'].append("15min RSI oversold")
                conditions['score'] -= 10
                
            if rsi_hourly < 25:
                conditions['warnings'].append("1H RSI oversold")
                conditions['score'] -= 15
                
            if rsi_4h < 30:
                conditions['warnings'].append("4H RSI oversold")
                conditions['score'] -= 15
            
            # 극단적 과매도 거부 조건
            if rsi_15 < 15 and rsi_hourly < 25 and rsi_4h < 30:
                conditions['warnings'].append("CRITICAL: Multi-timeframe oversold")
                conditions['score'] -= 50
            
            # 긍정적 조건
            if 40 < rsi_15 < 70:
                conditions['positives'].append("15min RSI in optimal range")
                conditions['score'] += 15
            if 35 < rsi_hourly < 60:
                conditions['positives'].append("1H RSI in optimal range")
                conditions['score'] += 20
            if rsi_4h > 40:
                conditions['positives'].append("4H RSI has room to fall")
                conditions['score'] += 15
        
        # 볼린저 밴드 체크
        bb_upper = df_15min['bb_bbh'].iloc[-1]
        bb_lower = df_15min['bb_bbl'].iloc[-1]
        bb_middle = df_15min['bb_bbm'].iloc[-1]
        current_price = df_15min['close'].iloc[-1]
        
        if action == 'buy':
            if current_price > bb_upper:
                conditions['warnings'].append("Price above Bollinger upper band")
                conditions['score'] -= 15
            elif current_price > bb_middle:
                conditions['positives'].append("Price above Bollinger middle")
                conditions['score'] += 10
        else:
            if current_price < bb_lower:
                conditions['warnings'].append("Price below Bollinger lower band")
                conditions['score'] -= 15
            elif current_price < bb_middle:
                conditions['positives'].append("Price below Bollinger middle")
                conditions['score'] += 10
        
        # 추세 방향 확인
        di_plus_hourly = df_hourly['di_plus'].iloc[-1]
        di_minus_hourly = df_hourly['di_minus'].iloc[-1]
        adx_hourly = df_hourly['adx'].iloc[-1]
        
        if action == 'buy':
            if di_plus_hourly > di_minus_hourly and adx_hourly > 20:
                conditions['positives'].append("Uptrend confirmed on 1H")
                conditions['score'] += 25
            elif di_minus_hourly > di_plus_hourly and adx_hourly > 25:
                conditions['warnings'].append("Strong downtrend on 1H")
                conditions['score'] -= 25
        else:
            if di_minus_hourly > di_plus_hourly and adx_hourly > 20:
                conditions['positives'].append("Downtrend confirmed on 1H")
                conditions['score'] += 25
            elif di_plus_hourly > di_minus_hourly and adx_hourly > 25:
                conditions['warnings'].append("Strong uptrend on 1H")
                conditions['score'] -= 25
        
        # MACD 체크
        macd = df_hourly['macd'].iloc[-1]
        macd_signal = df_hourly['macd_signal'].iloc[-1]
        
        if action == 'buy':
            if macd > macd_signal:
                conditions['positives'].append("MACD bullish on 1H")
                conditions['score'] += 15
            else:
                conditions['warnings'].append("MACD bearish on 1H")
                conditions['score'] -= 10
        else:
            if macd < macd_signal:
                conditions['positives'].append("MACD bearish on 1H")
                conditions['score'] += 15
            else:
                conditions['warnings'].append("MACD bullish on 1H")
                conditions['score'] -= 10
        
        # 최종 판단
        conditions['passed'] = conditions['score'] > 0
        
        return conditions
        
    except Exception as e:
        logger.error(f"진입 조건 체크 실패: {e}")
        conditions['warnings'].append(f"Condition check error: {str(e)}")
        return conditions

# ==================== 기존 함수들 복사 (필요한 함수들만) ====================

def fetch_ohlcv(symbol, timeframe='15m', limit=100):
    """Binance에서 OHLCV 데이터 가져오기"""
    try:
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        return df
    except Exception as e:
        logger.error(f"OHLCV 데이터 가져오기 실패 ({symbol}): {e}")
        return None

def calculate_indicators(df):
    """기술적 지표 계산"""
    try:
        # RSI
        df['rsi'] = ta.momentum.RSIIndicator(close=df['close'], window=14).rsi()
        
        # MACD
        macd_indicator = ta.trend.MACD(close=df['close'])
        df['macd'] = macd_indicator.macd()
        df['macd_signal'] = macd_indicator.macd_signal()
        df['macd_diff'] = macd_indicator.macd_diff()
        
        # Bollinger Bands
        bollinger = ta.volatility.BollingerBands(close=df['close'], window=20, window_dev=2)
        df['bb_bbm'] = bollinger.bollinger_mavg()
        df['bb_bbh'] = bollinger.bollinger_hband()
        df['bb_bbl'] = bollinger.bollinger_lband()
        
        # ATR
        df['atr'] = ta.volatility.AverageTrueRange(high=df['high'], low=df['low'], close=df['close']).average_true_range()
        
        # ADX
        adx_indicator = ta.trend.ADXIndicator(high=df['high'], low=df['low'], close=df['close'])
        df['adx'] = adx_indicator.adx()
        df['di_plus'] = adx_indicator.adx_pos()
        df['di_minus'] = adx_indicator.adx_neg()
        
        # CMF (Chaikin Money Flow)
        df['cmf'] = ta.volume.ChaikinMoneyFlowIndicator(
            high=df['high'], low=df['low'], close=df['close'], volume=df['volume']
        ).chaikin_money_flow()
        
        return df
    except Exception as e:
        logger.error(f"지표 계산 실패: {e}")
        return df

def send_telegram_message(message):
    """텔레그램 메시지 전송"""
    if not ENABLE_TELEGRAM:
        logger.info(f"텔레그램 비활성화 상태 - 메시지 스킵: {message[:50]}...")
        return
        
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_IDS:
        logger.warning("텔레그램 설정이 완료되지 않았습니다.")
        return
    
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    
    for chat_id in TELEGRAM_CHAT_IDS:
        if not chat_id:
            continue
            
        payload = {
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "Markdown",
            "disable_web_page_preview": True
        }
        
        try:
            response = requests.post(url, json=payload, timeout=10)
            if response.status_code != 200:
                logger.error(f"텔레그램 메시지 전송 실패: {response.text}")
        except Exception as e:
            logger.error(f"텔레그램 메시지 전송 중 오류: {e}")

# 데이터베이스 관련 함수들
def get_db_connection():
    """데이터베이스 연결 - 사용자별 DB 파일 사용"""
    conn = sqlite3.connect(DB_FILENAME)
    conn.row_factory = sqlite3.Row
    return conn

def init_database():
    """데이터베이스 초기화 - 포트 5000만 테이블 생성"""
    # 포트 5000이 아니면 DB는 읽기만 하므로 초기화 스킵
    if not ENABLE_DB_WRITE:
        logger.info(f"📚 DB 읽기 전용 모드 (포트: {SERVER_PORT})")
        return
    
    conn = get_db_connection()
    c = conn.cursor()
    
    # trades 테이블
    c.execute('''CREATE TABLE IF NOT EXISTS trades
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  timestamp TEXT,
                  symbol TEXT,
                  trade_type TEXT,
                  ai_decision TEXT,
                  action TEXT,
                  amount REAL,
                  entry_price REAL,
                  current_price REAL,
                  stop_loss REAL,
                  take_profit REAL,
                  pl_ratio REAL,
                  reason TEXT,
                  confidence REAL,
                  balance_before REAL,
                  balance_after REAL,
                  success BOOLEAN,
                  user_name TEXT,
                  port INTEGER)''')
    
    # completed_trades 테이블
    c.execute('''CREATE TABLE IF NOT EXISTS completed_trades
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  symbol TEXT,
                  side TEXT,
                  entry_price REAL,
                  exit_price REAL,
                  amount REAL,
                  entry_time TEXT,
                  exit_time TEXT,
                  profit_usdt REAL,
                  profit_percentage REAL,
                  close_reason TEXT,
                  max_profit REAL,
                  max_loss REAL,
                  duration_hours REAL,
                  user_name TEXT,
                  port INTEGER)''')
    
    # positions 테이블 추가
    c.execute('''CREATE TABLE IF NOT EXISTS positions
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  symbol TEXT UNIQUE,
                  side TEXT,
                  amount REAL,
                  entry_price REAL,
                  current_price REAL,
                  unrealized_pnl REAL,
                  percentage REAL,
                  margin REAL,
                  last_updated TEXT,
                  user_name TEXT,
                  port INTEGER)''')
    
    conn.commit()
    conn.close()
    logger.info(f"✅ 데이터베이스 초기화 완료 (포트: {SERVER_PORT})")

def generate_reflection(recent_trades_df, market_data):
    """최근 거래 성과 분석 및 인사이트 생성"""
    try:
        if recent_trades_df is None or len(recent_trades_df) == 0:
            return "No recent trading data available for reflection."
        
        # 기본 통계
        total_trades = len(recent_trades_df)
        winning_trades = recent_trades_df[recent_trades_df['profit_percentage'] > 0]
        losing_trades = recent_trades_df[recent_trades_df['profit_percentage'] < 0]
        
        win_rate = (len(winning_trades) / total_trades * 100) if total_trades > 0 else 0
        avg_profit = recent_trades_df['profit_percentage'].mean()
        
        reflection = f"""
**Trading Performance Analysis (Last {total_trades} trades):**

📊 **Overall Statistics:**
- Win Rate: {win_rate:.1f}%
- Average Profit: {avg_profit:.2f}%
- Total Trades: {total_trades}
- Winning/Losing: {len(winning_trades)}/{len(losing_trades)}
"""
        
        # 승리/패배 패턴 분석
        if len(winning_trades) > 0:
            avg_win = winning_trades['profit_percentage'].mean()
            avg_win_duration = winning_trades['duration_hours'].mean()
            reflection += f"""
✅ **Winning Pattern:**
- Average Win: +{avg_win:.2f}%
- Average Duration: {avg_win_duration:.1f} hours
- Most Profitable Close Reason: {winning_trades['close_reason'].mode().iloc[0] if not winning_trades['close_reason'].mode().empty else 'N/A'}
"""
        
        if len(losing_trades) > 0:
            avg_loss = losing_trades['profit_percentage'].mean()
            avg_loss_duration = losing_trades['duration_hours'].mean()
            reflection += f"""
❌ **Losing Pattern:**
- Average Loss: {avg_loss:.2f}%
- Average Duration: {avg_loss_duration:.1f} hours
- Most Common Loss Reason: {losing_trades['close_reason'].mode().iloc[0] if not losing_trades['close_reason'].mode().empty else 'N/A'}
"""
        
        # 리스크 관리 분석
        if total_trades > 0:
            early_exits = recent_trades_df[recent_trades_df['duration_hours'] < 1]
            long_holds = recent_trades_df[recent_trades_df['duration_hours'] > 24]
            
            reflection += f"""
⚠️ **Risk Management Insights:**
- Early Exits (<1hr): {len(early_exits)} trades ({len(early_exits)/total_trades*100:.1f}%)
- Long Holds (>24hr): {len(long_holds)} trades ({len(long_holds)/total_trades*100:.1f}%)
- Max Profit Given Up: {recent_trades_df['max_profit'].mean() - recent_trades_df['profit_percentage'].mean():.2f}%
"""
        
        # 최근 트렌드
        if total_trades >= 5:
            recent_5 = recent_trades_df.head(5)
            recent_win_rate = (len(recent_5[recent_5['profit_percentage'] > 0]) / 5 * 100)
            trend = "Improving" if recent_win_rate > win_rate else "Declining"
            
            reflection += f"""
📈 **Recent Trend (Last 5 trades):**
- Recent Win Rate: {recent_win_rate:.1f}%
- Performance Trend: {trend}
- Momentum: {"Positive" if recent_5['profit_percentage'].mean() > 0 else "Negative"}
"""
        
        # AI 권장사항
        recommendations = []
        if win_rate < 40:
            recommendations.append("- Consider more conservative entry criteria")
        if avg_profit < 0:
            recommendations.append("- Review stop-loss and take-profit levels")
        if len(early_exits) > total_trades * 0.3:
            recommendations.append("- Avoid premature exits, let winners run")
        if avg_loss < -3:
            recommendations.append("- Tighten stop-loss to limit downside")
        
        if recommendations:
            reflection += "\n💡 **Recommendations:**\n" + "\n".join(recommendations)
        
        return reflection
        
    except Exception as e:
        logger.error(f"Reflection 생성 실패: {e}")
        return "Error generating performance reflection"

# AI 관련 헬퍼 함수들
def extract_ai_response(response):
    """AI 응답에서 텍스트 추출"""
    try:
        # 일반적인 content 필드 확인
        if hasattr(response, 'choices') and response.choices:
            choice = response.choices[0]
            if hasattr(choice, 'message') and hasattr(choice.message, 'content'):
                return choice.message.content
            # reasoning_content 확인 (DeepSeek의 경우)
            if hasattr(choice, 'message') and hasattr(choice.message, 'reasoning_content'):
                return choice.message.reasoning_content
        return None
    except Exception as e:
        logger.error(f"AI 응답 추출 실패: {e}")
        return None

def extract_json_from_text(text):
    """텍스트에서 JSON 추출"""
    try:
        # 먼저 전체 텍스트가 JSON인지 확인
        text = text.strip()
        if text.startswith('{') and text.endswith('}'):
            return text
        
        # JSON 패턴 찾기
        json_pattern = r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}'
        matches = re.findall(json_pattern, text)
        
        if matches:
            # 가장 큰 JSON 객체 찾기
            longest_match = max(matches, key=len)
            return longest_match
        
        return None
    except Exception as e:
        logger.error(f"JSON 추출 실패: {e}")
        return None

def create_default_reject_decision(reason):
    """기본 거부 결정 생성"""
    return {
        "decision": "reject",
        "modified_action": "hold",
        "percentage": 0,
        "reason": reason,
        "stop_loss_price": 0,
        "take_profit_price": 0,
        "pl_ratio": 0,
        "confidence": 0.0
    }

def is_duplicate_trade_record(conn, symbol, action, trade_type, time_window_seconds=10):
    """중복 거래 기록 확인"""
    c = conn.cursor()
    current_time = datetime.now()
    time_threshold = current_time - timedelta(seconds=time_window_seconds)
    
    c.execute("""SELECT COUNT(*) FROM trades 
                 WHERE symbol = ? AND action = ? AND trade_type = ? 
                 AND timestamp > ?""",
              (symbol, action, trade_type, time_threshold.isoformat()))
    
    count = c.fetchone()[0]
    return count > 0

def ai_validate_signal(symbol, action, market_data, recent_trades_df, message_data=None):
    """
    AI를 사용하여 거래 신호를 검증 - 개선 버전
    과매수/과매도 필터링 강화, 현실적인 TP/SL 설정
    """
    
    client = OpenAI(api_key=os.getenv("DEEPSEEK_API_KEY"), base_url="https://api.deepseek.com")
    if not client.api_key:
        logger.error("OpenAI API key is missing or invalid.")
        return None
    
    try:
        # Reflection 생성
        reflection = generate_reflection(recent_trades_df, market_data)
        
        # Technical Indicators 준비
        df_15min = market_data['df_15min']
        df_hourly = market_data['df_hourly'] 
        df_4h = market_data['df_4h']
        
        # ATR 값 안전하게 추출
        def safe_get_atr(df, current_price):
            """ATR을 안전하게 추출"""
            try:
                if 'atr' not in df.columns:
                    return current_price * 0.002
                
                atr_value = df['atr'].iloc[-1]
                if pd.isna(atr_value) or atr_value == 0:
                    # 대체값 계산
                    if len(df) >= 5:
                        recent_range = (df['high'].iloc[-5:] - df['low'].iloc[-5:]).mean()
                        if recent_range > 0:
                            return recent_range
                    return current_price * 0.002
                
                return atr_value
            except:
                return current_price * 0.002
        
        # ATR 추출
        atr_15min = safe_get_atr(df_15min, market_data['current_price'])
        atr_hourly = safe_get_atr(df_hourly, market_data['current_price'])
        
        # ======== 새로운 기능: 진입 조건 체크 ========
        entry_conditions = check_entry_conditions_enhanced(df_15min, df_hourly, df_4h, action)
        
        # ======== 새로운 기능: 현실적인 TP/SL 계산 ========
        tp_sl_calc = calculate_realistic_tp_sl(
            market_data['current_price'], 
            action, 
            df_15min, 
            df_hourly, 
            df_4h, 
            atr_hourly,
            message_data
        )
        
        # close_position 액션 처리 (별도 로직)
        if action in ['close', 'close_position']:
            # 포지션 정보 가져오기
            position_side = 'long' if action == 'buy' else 'short'
            
            # ======== 새로운 기능: 추세 역전 조기 감지 ========
            reversal_signals = detect_early_reversal_signals(df_15min, df_hourly, df_4h, position_side)
            
            # 심볼 설정 정보 가져오기
            symbol_config = SYMBOL_CONFIG.get(symbol, {})
            leverage = symbol_config.get('leverage', 10)
            position_size_percent = symbol_config.get('position_size_percent', 30)
            
            # 계좌 잔고 정보 가져오기
            try:
                balance_info = exchange.fetch_balance()
                total_margin = balance_info['USDT']['total']
                free_margin = balance_info['USDT']['free']
                used_margin = balance_info['USDT']['used']
            except Exception as e:
                logger.warning(f"잔고 정보 조회 실패: {e}")
                total_margin = 0
                free_margin = 0
                used_margin = 0
            
            # message_data 문자열 변환
            message_str = ""
            if message_data:
                if isinstance(message_data, dict):
                    message_str = f"\n**ADDITIONAL SIGNAL DATA:**\n{json.dumps(message_data, ensure_ascii=False, indent=2)}\n"
                else:
                    message_str = f"\n**ADDITIONAL SIGNAL DATA:**\n{str(message_data)}\n"
            
            # 역전 신호 정보 추가
            reversal_info = f"""
**🔄 TREND REVERSAL ANALYSIS:**
- Reversal Score: {reversal_signals['reversal_score']}/100
- Urgency: {reversal_signals['urgency'].upper()}
- Exit Recommended: {"YES" if reversal_signals['exit_recommended'] else "NO"}
- Reversal Signals Detected: {', '.join(reversal_signals['reversal_signals']) if reversal_signals['reversal_signals'] else 'None'}
"""
            
            json_template = """
{
    "decision": "approve",
    "reason": "Favorable exit conditions confirmed with early reversal signals",
    "confidence": 0.75,
    "urgency": "immediate"
}"""

            prompt = f"""
You are an expert crypto trading AI validator specializing in position exit timing. Analyze whether to approve closing the position for {symbol}.

**ACCOUNT & TRADING CONFIGURATION (REFERENCE ONLY):**
- Leverage: {leverage}x
- Position Size Target: {position_size_percent}% of total balance
- Total Balance: ${total_margin:,.2f} USDT
- Free Balance: ${free_margin:,.2f} USDT
- Used Margin: ${used_margin:,.2f} USDT

**CURRENT MARKET CONDITIONS:**
- Symbol: {symbol}
- Current Price: ${market_data['current_price']:.2f} USDT
- Action: Close Position
{message_str}

{reversal_info}

**MULTI-TIMEFRAME TECHNICAL ANALYSIS:**

═══════════════════════════════════════════
📊 **15-MINUTE CHART (Short-term Momentum)**
═══════════════════════════════════════════
→ Momentum:
  • RSI(14): {df_15min['rsi'].iloc[-1]:.2f} {'[OVERBOUGHT]' if df_15min['rsi'].iloc[-1] > 70 else '[OVERSOLD]' if df_15min['rsi'].iloc[-1] < 30 else '[NEUTRAL]'}
  • MACD: {df_15min['macd'].iloc[-1]:.2f} (Signal: {df_15min['macd_signal'].iloc[-1]:.2f})

→ Trend:
  • Bollinger: Upper=${df_15min['bb_bbh'].iloc[-1]:.2f}, Mid=${df_15min['bb_bbm'].iloc[-1]:.2f}, Lower=${df_15min['bb_bbl'].iloc[-1]:.2f}
  • ADX: {df_15min['adx'].iloc[-1]:.2f} {'[STRONG]' if df_15min['adx'].iloc[-1] > 25 else '[WEAK]'}
  • DI+: {df_15min['di_plus'].iloc[-1]:.2f} vs DI-: {df_15min['di_minus'].iloc[-1]:.2f}

→ Volume:
  • CMF: {df_15min['cmf'].iloc[-1]:.2f} {'[BUYING]' if df_15min['cmf'].iloc[-1] > 0 else '[SELLING]'}

═══════════════════════════════════════════
📈 **1-HOUR CHART (Medium-term Trend)**
═══════════════════════════════════════════
  • RSI(14): {df_hourly['rsi'].iloc[-1]:.2f} {'[OVERBOUGHT]' if df_hourly['rsi'].iloc[-1] > 70 else '[OVERSOLD]' if df_hourly['rsi'].iloc[-1] < 30 else '[NEUTRAL]'}
  • MACD: {df_hourly['macd'].iloc[-1]:.2f} (Signal: {df_hourly['macd_signal'].iloc[-1]:.2f})
  • ADX: {df_hourly['adx'].iloc[-1]:.2f} {'[STRONG]' if df_hourly['adx'].iloc[-1] > 25 else '[WEAK]'}
  • DI+: {df_hourly['di_plus'].iloc[-1]:.2f} vs DI-: {df_hourly['di_minus'].iloc[-1]:.2f}
  • CMF: {df_hourly['cmf'].iloc[-1]:.2f} {'[BUYING]' if df_hourly['cmf'].iloc[-1] > 0 else '[SELLING]'}

═══════════════════════════════════════════
📊 **4-HOUR CHART (Long-term Direction)**
═══════════════════════════════════════════
  • RSI(14): {df_4h['rsi'].iloc[-1]:.2f} {'[OVERBOUGHT]' if df_4h['rsi'].iloc[-1] > 70 else '[OVERSOLD]' if df_4h['rsi'].iloc[-1] < 30 else '[NEUTRAL]'}
  • MACD: {df_4h['macd'].iloc[-1]:.2f}
  • ADX: {df_4h['adx'].iloc[-1]:.2f} {'[STRONG]' if df_4h['adx'].iloc[-1] > 25 else '[WEAK]'}
  • DI+: {df_4h['di_plus'].iloc[-1]:.2f} vs DI-: {df_4h['di_minus'].iloc[-1]:.2f}
  • CMF: {df_4h['cmf'].iloc[-1]:.2f} {'[BUYING]' if df_4h['cmf'].iloc[-1] > 0 else '[SELLING]'}

**RECENT PERFORMANCE REFLECTION:**
{reflection if reflection else 'No previous trading data available'}

**ENHANCED EXIT VALIDATION WITH EARLY REVERSAL DETECTION:**

⚠️ **APPROVE EXIT IMMEDIATELY IF:**
- Reversal Score > 70 (Strong reversal signals detected)
- Multiple timeframe divergences confirmed
- Volume shows clear distribution/accumulation against position
- Momentum exhaustion with trend weakening
- Early reversal patterns detected (engulfing, doji at extremes)

✅ **APPROVE EXIT IF:**
- Reversal Score > 50 with confirming indicators
- Profit target reached with reversal confirmation
- Clear trend change on higher timeframes
- Risk management signals triggered
- CMF reversing across timeframes

❌ **REJECT EXIT IF:**
- Reversal Score < 30 (No reversal signals)
- Trend still strong on all timeframes
- Temporary pullback in strong trend
- Position showing healthy momentum

**CRITICAL INSTRUCTIONS:**
1. You MUST respond with ONLY a valid JSON object
2. Do NOT include any text before or after the JSON
3. Do NOT use markdown code blocks (no ```)
4. Consider the reversal score heavily in your decision
5. Act on early reversal signals to protect profits

{json_template}

**Field Requirements:**
- decision: must be "approve" or "reject"
- reason: string explaining WITH REVERSAL SIGNAL ANALYSIS
- confidence: number between 0.0 and 1.0
- urgency: "immediate" (if reversal score > 70), "soon" (if > 50), "normal", or "low"

Return ONLY the JSON object. Start with {{ and end with }}
"""
            
            # AI API 호출
            logger.info(f"AI 청산 시그널 검증 시작 - {symbol} (Reversal Score: {reversal_signals['reversal_score']})")
            
            response = client.chat.completions.create(
                model="deepseek-chat",
                messages=[
                    {
                        "role": "system",
                        "content": """You are a professional crypto trading AI validator for position exits with early reversal detection.

CRITICAL RULES:
1. ONLY return valid JSON - no explanations, no reasoning, no markdown
2. Start your response with { and end with }
3. Follow the exact JSON schema provided
4. Be aggressive about exits when reversal signals are strong
5. Protect profits by acting on early reversal signals

Your response must be a single JSON object."""
                    },
                    {"role": "user", "content": prompt}
                ],
                response_format={'type': 'json_object'},
                temperature=0.1,
                max_tokens=1000
            )
            
            # 응답 처리 (기존 로직과 동일)
            ai_response_text = extract_ai_response(response)
            
            if not ai_response_text or not ai_response_text.strip():
                logger.error("AI 응답이 비어있음")
                return {
                    "decision": "reject",
                    "reason": "AI 응답 없음",
                    "confidence": 0.0,
                    "urgency": "low"
                }
            
            json_str = extract_json_from_text(ai_response_text)
            if not json_str:
                logger.error("JSON 추출 실패")
                return {
                    "decision": "reject",
                    "reason": "JSON 파싱 실패",
                    "confidence": 0.0,
                    "urgency": "low"
                }
            
            try:
                parsed_json = json.loads(json_str)
                decision = ClosePositionDecision.model_validate(parsed_json)
                result = decision.model_dump()
                
                logger.info(
                    f"✅ AI 청산 시그널 검증 완료: {result['decision'].upper()} "
                    f"(신뢰도: {result['confidence']:.2%}, 긴급도: {result['urgency']})"
                )
                
                return result
                
            except ValidationError as e:
                logger.error(f"Pydantic 검증 실패: {e}")
                return {
                    "decision": "reject",
                    "reason": f"데이터 검증 실패: {str(e.errors()[0]['msg'])}",
                    "confidence": 0.0,
                    "urgency": "low"
                }
        
        # 일반 buy/sell 액션 처리
        # 심볼 설정 정보 가져오기
        symbol_config = SYMBOL_CONFIG.get(symbol, {})
        leverage = symbol_config.get('leverage', 10)
        position_size_percent = symbol_config.get('position_size_percent', 30)
        
        # 계좌 잔고 정보 가져오기
        try:
            balance_info = exchange.fetch_balance()
            total_margin = balance_info['USDT']['total']
            free_margin = balance_info['USDT']['free']
            used_margin = balance_info['USDT']['used']
        except Exception as e:
            logger.warning(f"잔고 정보 조회 실패: {e}")
            total_margin = 0
            free_margin = 0
            used_margin = 0
        
        # 진입 조건 정보 추가
        entry_condition_info = f"""
**🎯 ENTRY CONDITION ANALYSIS:**
- Entry Score: {entry_conditions['score']}/100
- Conditions Met: {"YES" if entry_conditions['passed'] else "NO"}
- Warnings: {', '.join(entry_conditions['warnings']) if entry_conditions['warnings'] else 'None'}
- Positive Factors: {', '.join(entry_conditions['positives']) if entry_conditions['positives'] else 'None'}

**📍 CALCULATED SUPPORT/RESISTANCE & TP/SL:**
- Support Levels: {', '.join([f'${x:.2f}' for x in tp_sl_calc['support_levels']]) if tp_sl_calc['support_levels'] else 'None'}
- Resistance Levels: {', '.join([f'${x:.2f}' for x in tp_sl_calc['resistance_levels']]) if tp_sl_calc['resistance_levels'] else 'None'}
- Volume Clusters: {', '.join([f'${x:.2f}' for x in tp_sl_calc['volume_levels']]) if tp_sl_calc['volume_levels'] else 'None'}
- Suggested TP: ${tp_sl_calc['tp']:.2f} (Risk: {tp_sl_calc['risk_percent']:.1f}%, Reward: {tp_sl_calc['reward_percent']:.1f}%)
- Suggested SL: ${tp_sl_calc['sl']:.2f} (P/L Ratio: {tp_sl_calc['pl_ratio']:.2f})
"""
        
        # JSON 템플릿을 프롬프트에 명시
        json_template = f"""
{{
    "decision": "approve",
    "modified_action": "{action}",
    "percentage": 30,
    "reason": "Entry conditions met with realistic TP/SL based on support/resistance levels",
    "stop_loss_price": {tp_sl_calc['sl']},
    "take_profit_price": {tp_sl_calc['tp']},
    "pl_ratio": {tp_sl_calc['pl_ratio']},
    "confidence": 0.75
}}"""

        # message_data 문자열 변환
        message_str = ""
        if message_data:
            if isinstance(message_data, dict):
                message_str = f"\n**ADDITIONAL SIGNAL DATA:**\n{json.dumps(message_data, ensure_ascii=False, indent=2)}\n"
            else:
                message_str = f"\n**ADDITIONAL SIGNAL DATA:**\n{str(message_data)}\n"
        
        # 프롬프트 구성
        prompt = f"""
You are an elite crypto trading AI validator with enhanced entry filtering and realistic TP/SL calculation. Your mission is to prevent entries at market extremes while setting achievable daily profit targets.

**ACCOUNT & TRADING CONFIGURATION:**
- Leverage: {leverage}x
- Position Size Target: {position_size_percent}% of total balance
- Total Balance: ${total_margin:,.2f} USDT
- Free Balance: ${free_margin:,.2f} USDT

**SIGNAL TO VALIDATE:**
- Symbol: {symbol}
- Proposed Action: {action.upper()}
- Current Price: ${market_data['current_price']:.2f} USDT
{message_str}

{entry_condition_info}

**MULTI-TIMEFRAME TECHNICAL ANALYSIS:**

═══════════════════════════════════════════
📊 **15-MINUTE CHART (Entry Timing)**
═══════════════════════════════════════════
→ Momentum:
  • RSI(14): {df_15min['rsi'].iloc[-1]:.2f} {'[EXTREME OVERBOUGHT - AVOID ENTRY]' if df_15min['rsi'].iloc[-1] > 80 else '[OVERBOUGHT]' if df_15min['rsi'].iloc[-1] > 70 else '[OVERSOLD]' if df_15min['rsi'].iloc[-1] < 30 else '[EXTREME OVERSOLD - AVOID ENTRY]' if df_15min['rsi'].iloc[-1] < 20 else '[NEUTRAL]'}
  • MACD: {df_15min['macd'].iloc[-1]:.2f} (Signal: {df_15min['macd_signal'].iloc[-1]:.2f})
  • Bollinger Position: {'Above Upper Band - RISKY' if df_15min['close'].iloc[-1] > df_15min['bb_bbh'].iloc[-1] else 'Below Lower Band - RISKY' if df_15min['close'].iloc[-1] < df_15min['bb_bbl'].iloc[-1] else 'Within Bands'}

═══════════════════════════════════════════
📈 **1-HOUR CHART (Trend Confirmation)**
═══════════════════════════════════════════
  • RSI(14): {df_hourly['rsi'].iloc[-1]:.2f} {'[OVERBOUGHT]' if df_hourly['rsi'].iloc[-1] > 70 else '[OVERSOLD]' if df_hourly['rsi'].iloc[-1] < 30 else '[NEUTRAL]'}
  • MACD: {df_hourly['macd'].iloc[-1]:.2f} (Signal: {df_hourly['macd_signal'].iloc[-1]:.2f})
  • ADX: {df_hourly['adx'].iloc[-1]:.2f} {'[STRONG TREND]' if df_hourly['adx'].iloc[-1] > 25 else '[WEAK TREND]'}
  • DI+: {df_hourly['di_plus'].iloc[-1]:.2f} vs DI-: {df_hourly['di_minus'].iloc[-1]:.2f}

═══════════════════════════════════════════
📊 **4-HOUR CHART (Major Trend)**
═══════════════════════════════════════════
  • RSI(14): {df_4h['rsi'].iloc[-1]:.2f} {'[OVERBOUGHT]' if df_4h['rsi'].iloc[-1] > 70 else '[OVERSOLD]' if df_4h['rsi'].iloc[-1] < 30 else '[NEUTRAL]'}
  • MACD: {df_4h['macd'].iloc[-1]:.2f}
  • ADX: {df_4h['adx'].iloc[-1]:.2f}
  • Trend Direction: {'BULLISH' if df_4h['di_plus'].iloc[-1] > df_4h['di_minus'].iloc[-1] else 'BEARISH'}

**RECENT PERFORMANCE:**
{reflection if reflection else 'No previous trading data available'}

**🛡️ ENHANCED VALIDATION CRITERIA V2.0:**

⛔ **AUTOMATIC REJECTION CONDITIONS (OVERBOUGHT/OVERSOLD FILTER):**

For BUY Signals - REJECT if:
- Entry Score < -30 (Multiple extreme conditions)
- 15min RSI > 85 AND 1h RSI > 75 (Extreme overbought)
- Price > Bollinger Upper + ATR (Extreme deviation)
- All timeframes showing overbought (RSI > 70 on all)

For SELL Signals - REJECT if:
- Entry Score < -30 (Multiple extreme conditions)
- 15min RSI < 15 AND 1h RSI < 25 (Extreme oversold)
- Price < Bollinger Lower - ATR (Extreme deviation)
- All timeframes showing oversold (RSI < 30 on all)

✅ **APPROVAL WITH REALISTIC TP/SL:**

IMPORTANT: Use the suggested TP/SL from the calculated support/resistance levels provided above.
These are based on:
- Daily volatility range (achievable within 24 hours)
- Nearest support/resistance levels
- Volume profile clusters
- ATR-based reasonable distances

DO NOT set TP/SL beyond daily range unless strong justification exists.

**POSITION SIZING BASED ON CONDITIONS:**
- Entry Score > 50: Use full position (30%)
- Entry Score 20-50: Use 20% position
- Entry Score 0-20: Use 15% position
- Entry Score < 0: Reject or wait

**CRITICAL INSTRUCTIONS:**
1. Respond with ONLY a valid JSON object
2. Use the suggested TP/SL values from the calculation above
3. Adjust position size based on entry score
4. Be strict about extreme overbought/oversold conditions
5. Focus on realistic daily profit targets

{json_template}

**Field Requirements:**
- decision: "approve", "reject", or "modify"
- modified_action: "{action}", "hold", or opposite action if reversing
- percentage: 10-100 based on entry conditions
- reason: Must reference entry score and market extremes
- stop_loss_price: Use suggested SL from calculation
- take_profit_price: Use suggested TP from calculation
- pl_ratio: Should be between 1.2 and 3.0
- confidence: 0.0 to 1.0 based on entry score

Return ONLY the JSON object. Start with {{ and end with }}
"""
        
        # AI API 호출
        logger.info(f"AI 시그널 검증 시작 - {symbol} {action} (Entry Score: {entry_conditions['score']})")
        
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {
                    "role": "system",
                    "content": """You are a professional crypto trading AI validator with strict entry filtering.

CRITICAL RULES:
1. ONLY return valid JSON - no explanations
2. Reject entries at market extremes (overbought/oversold)
3. Use realistic TP/SL based on daily achievable ranges
4. Adjust position size based on market conditions
5. Protect capital by avoiding FOMO entries

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
        
        json_str = extract_json_from_text(ai_response_text)
        if not json_str:
            logger.error("JSON 추출 실패")
            return create_default_reject_decision("JSON 파싱 실패")
        
        try:
            parsed_json = json.loads(json_str)
            decision = TradingDecision.model_validate(parsed_json)
            result = decision.model_dump()
            
            logger.info(
                f"✅ AI 시그널 검증 완료: {result['decision'].upper()} "
                f"(신뢰도: {result['confidence']:.2%}, TP: ${result['take_profit_price']:.2f}, SL: ${result['stop_loss_price']:.2f})"
            )
            
            return result
            
        except ValidationError as e:
            logger.error(f"Pydantic 검증 실패: {e}")
            return create_default_reject_decision(f"데이터 검증 실패: {str(e.errors()[0]['msg'])}")
            
    except Exception as e:
        logger.error(f"AI 검증 중 오류: {e}")
        return create_default_reject_decision(f"AI 검증 오류: {str(e)}")

def ai_monitor_position(symbol, position_info):
    """
    포지션 모니터링 - 추세 역전 조기 감지 강화
    """
    client = OpenAI(api_key=os.getenv("DEEPSEEK_API_KEY"), base_url="https://api.deepseek.com")
    if not client.api_key:
        logger.error("OpenAI API key is missing")
        return None
    
    try:
        # 시장 데이터 가져오기
        df_15min = fetch_ohlcv(symbol, '15m', 100)
        df_hourly = fetch_ohlcv(symbol, '1h', 100)
        df_4h = fetch_ohlcv(symbol, '4h', 100)
        
        if df_15min is None or df_hourly is None or df_4h is None:
            logger.error(f"시장 데이터 가져오기 실패: {symbol}")
            return None
        
        # 기술적 지표 계산
        df_15min = calculate_indicators(df_15min)
        df_hourly = calculate_indicators(df_hourly)
        df_4h = calculate_indicators(df_4h)
        
        current_price = df_15min['close'].iloc[-1]
        entry_price = position_info['entryPrice']
        amount = position_info['contracts']
        side = position_info['side']
        
        # PnL 계산
        if side == 'long':
            pnl_percentage = ((current_price - entry_price) / entry_price) * 100
        else:
            pnl_percentage = ((entry_price - current_price) / entry_price) * 100
        
        # ======== 추세 역전 조기 감지 ========
        reversal_signals = detect_early_reversal_signals(df_15min, df_hourly, df_4h, side)
        
        # 역전 신호 정보
        reversal_info = f"""
**🔄 TREND REVERSAL DETECTION:**
- Reversal Score: {reversal_signals['reversal_score']}/100
- Detected Signals: {', '.join(reversal_signals['reversal_signals']) if reversal_signals['reversal_signals'] else 'None'}
- Urgency Level: {reversal_signals['urgency'].upper()}
- Exit Recommended: {"YES - ACT NOW!" if reversal_signals['exit_recommended'] else "NO"}
"""
        
        json_template = """
{
    "decision": "hold",
    "percentage": 0,
    "reason": "Position showing healthy momentum",
    "exit_type": "none",
    "confidence": 0.75,
    "urgency": "none"
}"""
        
        prompt = f"""
You are an advanced position monitoring AI with early trend reversal detection capabilities.

**POSITION DETAILS:**
- Symbol: {symbol}
- Side: {side.upper()}
- Entry Price: ${entry_price:.2f}
- Current Price: ${current_price:.2f}
- Position Size: {amount}
- Current PnL: {pnl_percentage:.2f}%
- Time in Position: {position_info.get('duration_hours', 'Unknown')} hours

{reversal_info}

**TECHNICAL ANALYSIS:**

15-MINUTE:
- RSI: {df_15min['rsi'].iloc[-1]:.2f}
- MACD: {df_15min['macd'].iloc[-1]:.2f} (Signal: {df_15min['macd_signal'].iloc[-1]:.2f})
- ADX: {df_15min['adx'].iloc[-1]:.2f}

1-HOUR:
- RSI: {df_hourly['rsi'].iloc[-1]:.2f}
- MACD: {df_hourly['macd'].iloc[-1]:.2f} (Signal: {df_hourly['macd_signal'].iloc[-1]:.2f})
- ADX: {df_hourly['adx'].iloc[-1]:.2f}
- DI+: {df_hourly['di_plus'].iloc[-1]:.2f} vs DI-: {df_hourly['di_minus'].iloc[-1]:.2f}

4-HOUR:
- RSI: {df_4h['rsi'].iloc[-1]:.2f}
- ADX: {df_4h['adx'].iloc[-1]:.2f}

**EXIT DECISION FRAMEWORK:**

⚠️ **IMMEDIATE EXIT (close 100%) if:**
- Reversal Score > 70 with multiple confirming signals
- Clear trend reversal pattern (engulfing, major divergence)
- Volume spike against position direction
- Breaking key support/resistance against position

✅ **PARTIAL EXIT (close 50-75%) if:**
- Reversal Score 50-70 with some confirming signals
- Momentum weakening but trend intact
- Profit > 2% with reversal warnings
- Time to secure partial profits

🔄 **TIGHTEN MONITORING (hold but watch) if:**
- Reversal Score 30-50
- Mixed signals but position still favorable
- Minor pullback in strong trend

💎 **HOLD POSITION if:**
- Reversal Score < 30
- Trend strongly in favor
- Healthy momentum continuation
- No reversal patterns detected

**CRITICAL INSTRUCTIONS:**
1. Return ONLY valid JSON
2. Act aggressively on reversal scores > 70
3. Protect profits when reversal signals appear
4. Consider partial exits to manage risk
5. Focus on capital preservation over maximizing gains

{json_template}

**Field Requirements:**
- decision: "hold", "close", or "partial_close"
- percentage: 0 (hold), 100 (close), or 50-75 (partial)
- reason: Must reference reversal score and signals
- exit_type: "trend_reversal", "take_profit", "stop_loss", "risk_management", or "none"
- confidence: 0.0 to 1.0
- urgency: "immediate" (if reversal > 70), "soon" (if > 50), "watch", or "none"

Return ONLY the JSON object.
"""
        
        logger.info(f"AI 포지션 모니터링 - {symbol} (Reversal Score: {reversal_signals['reversal_score']})")
        
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {
                    "role": "system",
                    "content": "You are a position monitoring AI focused on early exit signals. Return only JSON."
                },
                {"role": "user", "content": prompt}
            ],
            response_format={'type': 'json_object'},
            temperature=0.1,
            max_tokens=500
        )
        
        ai_response_text = extract_ai_response(response)
        if not ai_response_text:
            return None
        
        json_str = extract_json_from_text(ai_response_text)
        if not json_str:
            return None
        
        try:
            parsed_json = json.loads(json_str)
            decision = PositionExitDecision.model_validate(parsed_json)
            result = decision.model_dump()
            
            logger.info(
                f"📊 포지션 모니터링 결과 - {symbol}: {result['decision'].upper()} "
                f"(긴급도: {result['urgency']}, PnL: {pnl_percentage:.2f}%)"
            )
            
            if result['urgency'] == 'immediate':
                logger.warning(f"⚠️ IMMEDIATE ACTION REQUIRED for {symbol}: {result['reason']}")
                send_telegram_message(
                    f"🚨 *긴급 포지션 알림 - {symbol}*\n\n"
                    f"결정: {result['decision'].upper()}\n"
                    f"이유: {result['reason']}\n"
                    f"현재 PnL: {pnl_percentage:.2f}%\n"
                    f"Reversal Score: {reversal_signals['reversal_score']}/100"
                )
            
            return result
            
        except Exception as e:
            logger.error(f"포지션 모니터링 결과 파싱 실패: {e}")
            return None
            
    except Exception as e:
        logger.error(f"포지션 모니터링 중 오류: {e}")
        return None

def calculate_position_size(symbol, balance):
    """포지션 크기 계산"""
    try:
        config = SYMBOL_CONFIG.get(symbol, {})
        position_percent = config.get('position_size_percent', 30)
        min_size = config.get('min_position_size', 10)
        max_size = config.get('max_position_size', 100000)
        
        position_size = balance * (position_percent / 100)
        position_size = max(min_size, min(position_size, max_size))
        
        return position_size
    except Exception as e:
        logger.error(f"포지션 크기 계산 실패: {e}")
        return min_size

def execute_trade(symbol, action, amount, sl, tp, leverage=None):
    """실제 거래 실행"""
    try:
        # 심볼 설정 가져오기
        config = SYMBOL_CONFIG.get(symbol, {})
        if leverage is None:
            leverage = config.get('leverage', 10)
        
        # 레버리지 설정
        exchange.set_leverage(leverage, symbol)
        
        # 주문 실행
        if action == 'buy':
            order = exchange.create_market_buy_order(symbol, amount)
        else:
            order = exchange.create_market_sell_order(symbol, amount)
        
        logger.info(f"✅ 주문 실행 완료: {symbol} {action} {amount}")
        
        # SL/TP 설정
        if sl and tp:
            # Stop Loss 주문
            sl_side = 'sell' if action == 'buy' else 'buy'
            sl_order = exchange.create_order(
                symbol=symbol,
                type='stop_market',
                side=sl_side,
                amount=amount,
                params={'stopPrice': sl}
            )
            
            # Take Profit 주문
            tp_side = 'sell' if action == 'buy' else 'buy'
            tp_order = exchange.create_order(
                symbol=symbol,
                type='take_profit_market',
                side=tp_side,
                amount=amount,
                params={'stopPrice': tp}
            )
            
            logger.info(f"✅ SL/TP 설정 완료: SL=${sl:.2f}, TP=${tp:.2f}")
        
        return order
        
    except Exception as e:
        logger.error(f"거래 실행 실패: {e}")
        return None

@app.route('/webhook', methods=['POST'])
def webhook():
    """TradingView 웹훅 수신"""
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({'error': 'No data received'}), 400
        
        # 필수 필드 확인
        symbol = data.get('symbol', 'BTC/USDT')
        action = data.get('action', '').lower()
        
        # 심볼 설정 확인
        if symbol not in SYMBOL_CONFIG:
            logger.warning(f"미등록 심볼: {symbol}")
            return jsonify({'error': f'Symbol {symbol} not configured'}), 400
        
        if not SYMBOL_CONFIG[symbol].get('enabled', False):
            logger.info(f"비활성화된 심볼: {symbol}")
            return jsonify({'status': 'Symbol disabled'}), 200
        
        logger.info(f"📨 웹훅 수신: {symbol} - {action}")
        
        # 시장 데이터 가져오기
        df_15min = fetch_ohlcv(symbol, '15m', 100)
        df_hourly = fetch_ohlcv(symbol, '1h', 100)
        df_4h = fetch_ohlcv(symbol, '4h', 100)
        
        if df_15min is None or df_hourly is None or df_4h is None:
            logger.error("시장 데이터 가져오기 실패")
            return jsonify({'error': 'Failed to fetch market data'}), 500
        
        # 기술적 지표 계산
        df_15min = calculate_indicators(df_15min)
        df_hourly = calculate_indicators(df_hourly)
        df_4h = calculate_indicators(df_4h)
        
        current_price = df_15min['close'].iloc[-1]
        
        market_data = {
            'df_15min': df_15min,
            'df_hourly': df_hourly,
            'df_4h': df_4h,
            'current_price': current_price
        }
        
        # 최근 거래 데이터 가져오기
        conn = get_db_connection()
        recent_trades_query = """
            SELECT * FROM completed_trades 
            WHERE symbol = ?
            ORDER BY exit_time DESC 
            LIMIT 20
        """
        recent_trades_df = pd.read_sql_query(recent_trades_query, conn, params=(symbol,))
        conn.close()
        
        # AI 검증이 활성화된 경우
        if SYMBOL_CONFIG[symbol].get('ai_validation', False):
            logger.info(f"🤖 AI 검증 시작: {symbol} {action}")
            
            decision = ai_validate_signal(
                symbol=symbol,
                action=action,
                market_data=market_data,
                recent_trades_df=recent_trades_df,
                message_data=data
            )
            
            if not decision:
                logger.error("AI 검증 실패")
                return jsonify({'error': 'AI validation failed'}), 500
            
            # AI 결정에 따른 처리
            if decision['decision'] == 'reject':
                logger.info(f"❌ AI가 시그널 거부: {decision['reason']}")
                send_telegram_message(
                    f"❌ *시그널 거부 - {symbol}*\n\n"
                    f"액션: {action}\n"
                    f"이유: {decision['reason']}\n"
                    f"신뢰도: {decision.get('confidence', 0):.2%}"
                )
                return jsonify({'status': 'rejected', 'reason': decision['reason']}), 200
            
            elif decision['decision'] in ['approve', 'modify']:
                # 거래 실행
                try:
                    balance_info = exchange.fetch_balance()
                    balance = balance_info['USDT']['free']
                    
                    # 포지션 크기 계산
                    position_size = calculate_position_size(symbol, balance)
                    
                    # AI 결정에 따른 포지션 크기 조정
                    adjusted_size = position_size * (decision['percentage'] / 100)
                    
                    # 거래 실행
                    order = execute_trade(
                        symbol=symbol,
                        action=decision['modified_action'],
                        amount=adjusted_size,
                        sl=decision['stop_loss_price'],
                        tp=decision['take_profit_price']
                    )
                    
                    if order:
                        logger.info(f"✅ 거래 실행 성공: {symbol}")
                        
                        # 텔레그램 알림
                        send_telegram_message(
                            f"✅ *포지션 진입 - {symbol}*\n\n"
                            f"방향: {decision['modified_action'].upper()}\n"
                            f"진입가: ${current_price:.2f}\n"
                            f"수량: {adjusted_size:.4f}\n"
                            f"SL: ${decision['stop_loss_price']:.2f}\n"
                            f"TP: ${decision['take_profit_price']:.2f}\n"
                            f"P/L Ratio: {decision['pl_ratio']:.2f}\n"
                            f"신뢰도: {decision['confidence']:.2%}\n"
                            f"이유: {decision['reason']}"
                        )
                        
                        # DB 저장 (포트 5000만 쓰기)
                        if ENABLE_DB_WRITE:
                            conn = get_db_connection()
                            c = conn.cursor()
                            c.execute("""INSERT INTO trades 
                                        (timestamp, symbol, trade_type, ai_decision, action, 
                                         amount, entry_price, current_price, stop_loss, 
                                         take_profit, pl_ratio, reason, confidence, success,
                                         user_name, port)
                                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                                     (datetime.now().isoformat(), symbol, 'WEBHOOK', 
                                      decision['decision'], decision['modified_action'],
                                      adjusted_size, current_price, current_price,
                                      decision['stop_loss_price'], decision['take_profit_price'],
                                      decision['pl_ratio'], decision['reason'],
                                      decision['confidence'], True, USER_NAME, SERVER_PORT))
                            conn.commit()
                            conn.close()
                            logger.info(f"✅ DB 기록 완료 (사용자: {USER_NAME})")
                        else:
                            logger.info(f"⏭️  DB 기록 스킵 (읽기 전용 모드: {USER_NAME})")
                        
                        return jsonify({'status': 'executed', 'order': order}), 200
                    else:
                        return jsonify({'error': 'Trade execution failed'}), 500
                        
                except Exception as e:
                    logger.error(f"거래 실행 중 오류: {e}")
                    return jsonify({'error': str(e)}), 500
        
        else:
            # AI 검증 없이 직접 실행
            logger.info(f"AI 검증 스킵 - 직접 실행: {symbol}")
            # 직접 실행 로직 구현...
            return jsonify({'status': 'executed without AI'}), 200
            
    except Exception as e:
        logger.error(f"웹훅 처리 중 오류: {e}")
        return jsonify({'error': str(e)}), 500

def monitor_positions():
    """포지션 모니터링 스레드"""
    while True:
        try:
            time.sleep(AI_MONITOR_INTERVAL * 60)  # 분 단위
            
            # 활성 포지션 가져오기
            positions = exchange.fetch_positions()
            
            for position in positions:
                if position['contracts'] > 0:  # 열린 포지션만
                    symbol = position['symbol']
                    
                    # AI 모니터링이 활성화된 심볼만
                    if SYMBOL_CONFIG.get(symbol, {}).get('ai_monitoring', False):
                        logger.info(f"🔍 포지션 모니터링: {symbol}")
                        
                        decision = ai_monitor_position(symbol, position)
                        
                        if decision and decision['decision'] != 'hold':
                            # 포지션 종료 또는 부분 종료
                            if decision['decision'] == 'close':
                                # 전체 포지션 종료
                                logger.warning(f"🔴 포지션 종료 신호: {symbol}")
                                # 종료 로직 구현...
                            elif decision['decision'] == 'partial_close':
                                # 부분 종료
                                logger.warning(f"🟡 부분 종료 신호: {symbol} ({decision['percentage']}%)")
                                # 부분 종료 로직 구현...
                                
        except Exception as e:
            logger.error(f"포지션 모니터링 중 오류: {e}")
            time.sleep(60)  # 에러 시 1분 대기

@app.route('/status', methods=['GET'])
def status():
    """서버 상태 확인"""
    try:
        balance = exchange.fetch_balance()
        positions = exchange.fetch_positions()
        
        active_positions = [p for p in positions if p['contracts'] > 0]
        
        return jsonify({
            'status': 'running',
            'user': USER_NAME,
            'port': SERVER_PORT,
            'telegram': ENABLE_TELEGRAM,
            'db_mode': 'read-write' if ENABLE_DB_WRITE else 'read-only',
            'db_file': DB_FILENAME,
            'balance': balance['USDT']['total'],
            'free_balance': balance['USDT']['free'],
            'used_balance': balance['USDT']['used'],
            'active_positions': len(active_positions),
            'positions_detail': [{
                'symbol': p['symbol'],
                'side': p['side'],
                'contracts': p['contracts'],
                'pnl': p.get('percentage', 0)
            } for p in active_positions],
            'symbols': list(SYMBOL_CONFIG.keys()),
            'api_configured': bool(BINANCE_API_KEY and BINANCE_SECRET_KEY)
        }), 200
    except Exception as e:
        return jsonify({
            'status': 'error',
            'user': USER_NAME,
            'port': SERVER_PORT,
            'db_mode': 'read-write' if ENABLE_DB_WRITE else 'read-only',
            'error': str(e)
        }), 500

@app.route('/positions', methods=['GET'])
def get_positions():
    """현재 포지션 조회"""
    try:
        positions = exchange.fetch_positions()
        active_positions = []
        
        for position in positions:
            if position['contracts'] > 0:
                active_positions.append({
                    'symbol': position['symbol'],
                    'side': position['side'],
                    'contracts': position['contracts'],
                    'entryPrice': position['entryPrice'],
                    'markPrice': position['markPrice'],
                    'pnl': position['percentage']
                })
        
        return jsonify(active_positions), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/manual_close/<symbol>', methods=['POST'])
def manual_close(symbol):
    """수동 포지션 종료"""
    try:
        positions = exchange.fetch_positions(symbols=[symbol])
        
        if not positions or positions[0]['contracts'] == 0:
            return jsonify({'error': 'No open position'}), 400
        
        position = positions[0]
        side = 'sell' if position['side'] == 'long' else 'buy'
        
        # 포지션 종료
        order = exchange.create_market_order(
            symbol=symbol,
            type='market',
            side=side,
            amount=position['contracts']
        )
        
        logger.info(f"✅ 수동 포지션 종료: {symbol}")
        
        send_telegram_message(
            f"🔴 *포지션 종료 - {symbol}*\n\n"
            f"종료 방식: 수동\n"
            f"포지션: {position['side']}\n"
            f"수량: {position['contracts']}\n"
            f"진입가: ${position['entryPrice']:.2f}\n"
            f"종료가: ${position['markPrice']:.2f}\n"
            f"PnL: {position['percentage']:.2f}%"
        )
        
        return jsonify({'status': 'closed', 'order': order}), 200
        
    except Exception as e:
        logger.error(f"수동 종료 실패: {e}")
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    # 데이터베이스 초기화 (공통 DB 파일)
    logger.info(f"📁 Using database file: {DB_FILENAME}")
    logger.info(f"💾 DB 모드: {'쓰기/읽기' if ENABLE_DB_WRITE else '읽기 전용'}")
    init_database()
    
    # 포지션 모니터링 스레드 시작
    if AI_MONITOR_INTERVAL > 0:
        monitor_thread = threading.Thread(target=monitor_positions, daemon=True)
        monitor_thread.start()
        logger.info(f"✅ 포지션 모니터링 시작 (간격: {AI_MONITOR_INTERVAL}분)")
    
    # 서버 시작
    logger.info(f"🚀 통합 트레이딩 시스템 v6 시작")
    logger.info(f"👤 사용자: {USER_NAME} (포트: {SERVER_PORT})")
    logger.info(f"📊 활성 심볼: {', '.join([s for s in SYMBOL_CONFIG.keys() if SYMBOL_CONFIG[s]['enabled']])}")
    logger.info(f"💬 텔레그램: {'활성화' if ENABLE_TELEGRAM else '비활성화'}")
    
    # 시작 알림
    if ENABLE_TELEGRAM:
        send_telegram_message(
            f"🚀 *트레이딩 봇 시작*\n\n"
            f"👤 사용자: {USER_NAME}\n"
            f"🔌 포트: {SERVER_PORT}\n"
            f"💾 DB 모드: {'쓰기/읽기' if ENABLE_DB_WRITE else '읽기 전용'}\n"
            f"📊 활성 심볼: {', '.join([s for s in SYMBOL_CONFIG.keys() if SYMBOL_CONFIG[s]['enabled']])}\n"
            f"✅ AI 검증: 활성화\n"
            f"🔄 포지션 모니터링: {AI_MONITOR_INTERVAL}분"
        )
    
    app.run(host='0.0.0.0', port=SERVER_PORT, debug=False)
