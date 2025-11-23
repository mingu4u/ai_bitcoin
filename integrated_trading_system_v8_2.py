"""
Integrated Trading System v8.6 Enhanced
========================================
자동매매봇 - 다중 유저 지원, AI 검증/모니터링 통합 버전
🔥 포지션 청산 감지 완벽 해결 + 물타기 기능 추가!

v8.6 Enhanced 주요 신규 기능 (2025-11-23):
- 🎯 AI 물타기 기능 추가 (손실 구간에서 추가 진입)
- 🎯 물타기 수량: 잔여 마진의 5~30% (확신도/승률 기반)
- 🎯 물타기 조건: 강력한 반전 신호 + 충분한 잔여 마진
- 🎯 AI 판단: 포지션 유지/부분청산/전체청산/물타기 (4가지)
- ✅ 봇 시작 시 기존 포지션 감지 개선 및 AI 모니터링 확실히 적용
- ✅ 기존 포지션도 AI가 물타기 판단 가능

v8.5 Fixed 주요 수정사항 (2025-11-23):
- 🔥 포지션 진입 시간 추적 시스템 추가 (position_entry_times)
- 🔥 신규 포지션 30초 보호 기간 설정 (POSITION_CHECK_DELAY)
- 🔥 바이낸스 API 재시도 로직 추가 (3회)
- 🔥 포지션 청산 시 진입 시간 정보도 함께 제거
- 🔥 포지션 진입 직후 잘못된 청산 감지 문제 완벽 해결

v8.3 Enhanced 주요 개선사항 (2025-11-22):
- ✨ 봇 시작시 기존 포지션도 AI 모니터링 대상에 포함
- ✨ existing_positions를 current_positions로 정상 동기화  
- ✨ AI 모니터링이 모든 포지션(기존/신규) 대상으로 작동
- 🔥 봇 시작시 기존 포지션 잘못된 청산 감지 문제 해결
- 🔥 existing_positions_at_start 변수 추가하여 기존 포지션 추적
- 🔥 PnL 조회 실패시에도 계산값으로 정상 처리
- 🔥 청산 알림 조건 개선 (기존/신규 포지션 구분)

v8.2 기능:
- 다중 유저 동시 지원
- AI 시그널 검증 및 포지션 모니터링
- 실시간 TP/SL 감지
- 바이낸스 실제 PnL 조회
"""

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
    },
    'USER3': {
        'name': 'Hyuk',
        'api_key_env': 'BINANCE_API_KEY_HYUK',
        'secret_key_env': 'BINANCE_SECRET_KEY_HYUK',
        'is_primary': False,  # 주문만 실행
    }
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

# 🆕 봇 시작 시간 추적 (초기 청산 감지 알림 억제용)
bot_start_time = None
initial_sync_completed = False
existing_positions_at_start = set()  # 🔥 v8.3: 봇 시작시 이미 있던 포지션 추적
positions_already_notified = set()  # 🔥 v8.4: 이미 알림 보낸 청산 추적
last_position_check = {}  # 🔥 v8.4: 마지막 포지션 확인 시간
position_entry_times = {}  # 🔥 v8.5 Fixed: 포지션 진입 시간 추적 (청산 감지 보호용)
POSITION_CHECK_DELAY = 30  # 🔥 v8.5 Fixed: 신규 포지션 체크 대기시간 (30초)

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
    urgency: str = Field(..., pattern="^(immediate|soon|normal|low)$")

class PositionExitDecision(BaseModel):
    """포지션 종료/추가 진입 결정용 모델 - 물타기 기능 추가"""
    decision: str = Field(..., pattern="^(hold|close|partial_close|add_position)$")
    percentage: int = Field(..., ge=0, le=100)
    reason: str = Field(..., min_length=1)
    exit_type: str = Field(
        ..., 
        pattern="^(take_profit|stop_loss|trend_reversal|risk_management|time_stop|averaging_down|none)$"
    )
    confidence: float = Field(..., ge=0.0, le=1.0)
    urgency: str = Field(..., pattern="^(immediate|soon|watch|none)$")
    # 🆕 물타기 관련 필드
    add_position_margin_percent: int = Field(default=0, ge=0, le=30)  # 잔여 마진의 5~30%
    expected_win_rate: float = Field(default=0.0, ge=0.0, le=1.0)  # 예상 승률

# 🆕 JSON 파싱 오류 시 AI 복구용 모델
class EmergencyTradingDecision(BaseModel):
    """JSON 파싱 오류 시 AI가 자동으로 파라미터를 설정"""
    percentage: int = Field(..., ge=10, le=100)
    stop_loss_price: float = Field(..., gt=0)
    take_profit_price: float = Field(..., gt=0)
    leverage: int = Field(..., ge=1, le=20)
    reason: str = Field(..., min_length=1)
    confidence: float = Field(..., ge=0.0, le=1.0)

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
    },
    'DASH/USDT': {
        'leverage': 10,
        'position_size_percent': 30,
        'min_position_size': 10,
        'max_position_size': 100000,
        'enabled': True,
        'ai_validation': True,
        'ai_monitoring': True
    },
    'TRUMP/USDT': {
        'leverage': 10,
        'position_size_percent': 30,
        'min_position_size': 10,
        'max_position_size': 100000,
        'enabled': True,
        'ai_validation': True,
        'ai_monitoring': True
    },
    'SUI/USDT': {
        'leverage': 10,
        'position_size_percent': 30,
        'min_position_size': 10,
        'max_position_size': 100000,
        'enabled': True,
        'ai_validation': True,
        'ai_monitoring': True
    },
    'WLD/USDT': {
        'leverage': 10,
        'position_size_percent': 30,
        'min_position_size': 10,
        'max_position_size': 100000,
        'enabled': True,
        'ai_validation': True,
        'ai_monitoring': True
    },
    'GIGGLE/USDT': {
        'leverage': 10,
        'position_size_percent': 30,
        'min_position_size': 10,
        'max_position_size': 100000,
        'enabled': True,
        'ai_validation': True,
        'ai_monitoring': True
    },
    'LTC/USDT': {
        'leverage': 10,
        'position_size_percent': 30,
        'min_position_size': 10,
        'max_position_size': 100000,
        'enabled': True,
        'ai_validation': True,
        'ai_monitoring': True
    },
    'DUSK/USDT': {
        'leverage': 10,
        'position_size_percent': 30,
        'min_position_size': 10,
        'max_position_size': 100000,
        'enabled': True,
        'ai_validation': True,
        'ai_monitoring': True
    },
    'FET/USDT': {
        'leverage': 10,
        'position_size_percent': 30,
        'min_position_size': 10,
        'max_position_size': 100000,
        'enabled': True,
        'ai_validation': True,
        'ai_monitoring': True
    },
    'PENDLE/USDT': {
        'leverage': 10,
        'position_size_percent': 30,
        'min_position_size': 10,
        'max_position_size': 100000,
        'enabled': True,
        'ai_validation': True,
        'ai_monitoring': True
    },
    'FIL/USDT': {
        'leverage': 10,
        'position_size_percent': 30,
        'min_position_size': 10,
        'max_position_size': 100000,
        'enabled': True,
        'ai_validation': True,
        'ai_monitoring': True
    },
    'AR/USDT': {
        'leverage': 10,
        'position_size_percent': 30,
        'min_position_size': 10,
        'max_position_size': 100000,
        'enabled': True,
        'ai_validation': True,
        'ai_monitoring': True
    },
    'OG/USDT': {
        'leverage': 10,
        'position_size_percent': 30,
        'min_position_size': 10,
        'max_position_size': 100000,
        'enabled': True,
        'ai_validation': True,
        'ai_monitoring': True
    },
    'F/USDT': {
        'leverage': 10,
        'position_size_percent': 30,
        'min_position_size': 10,
        'max_position_size': 100000,
        'enabled': True,
        'ai_validation': True,
        'ai_monitoring': True
    },
    'TAO/USDT': {
        'leverage': 10,
        'position_size_percent': 30,
        'min_position_size': 10,
        'max_position_size': 100000,
        'enabled': True,
        'ai_validation': True,
        'ai_monitoring': True
    },
    'COTI/USDT': {
        'leverage': 10,
        'position_size_percent': 30,
        'min_position_size': 10,
        'max_position_size': 100000,
        'enabled': True,
        'ai_validation': True,
        'ai_monitoring': True
    },
    'RAYSOL/USDT': {
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

# ============ Position Sync Functions ============
def sync_positions_from_exchange():
    """
    거래소의 실제 포지션을 current_positions와 동기화
    🔥 v8.5 Fixed: 포지션 진입 시간 추적으로 잘못된 청산 감지 완벽 방지
    """
    global current_positions, existing_positions_at_start, positions_already_notified, position_entry_times
    
    try:
        logger.info("=== 거래소 포지션 동기화 시작 ===")
        
        synced_count = 0
        manual_count = 0
        new_positions = {}
        
        # 🔥 v8.4: 모든 포지션을 한번에 조회 (개별 심볼 조회보다 안정적)
        all_positions = exchange.fetch_positions()
        
        for position in all_positions:
            symbol = position['symbol']
            contracts = float(position.get('contracts', 0))
            
            # SYMBOL_CONFIG에 있는 심볼만 처리
            if symbol not in SYMBOL_CONFIG:
                continue
            
            if not SYMBOL_CONFIG[symbol].get('enabled', True):
                continue
            
            if contracts != 0:  # 포지션이 있는 경우
                entry_price = float(position.get('entryPrice', 0))
                side = 'buy' if position['side'] == 'long' else 'sell'
                
                # 기존 포지션 정보가 있으면 유지, 없으면 새로 생성
                if symbol in current_positions:
                    # 기존 정보 유지
                    new_positions[symbol] = current_positions[symbol]
                    new_positions[symbol]['amount'] = abs(contracts)
                    new_positions[symbol]['entry_price'] = entry_price
                    logger.info(f"✓ {symbol} 포지션 업데이트: {side} {abs(contracts):.4f} @ ${entry_price:.2f}")
                else:
                    # 새로운 포지션 발견
                    new_positions[symbol] = {
                        'side': side,
                        'entry_price': entry_price,
                        'amount': abs(contracts),
                        'stop_loss': 0,
                        'take_profit': 0,
                        'trailing_stop_percent': DEFAULT_TRAILING_STOP_PERCENT,
                        'trailing_activation_percent': DEFAULT_TRAILING_ACTIVATION_PERCENT,
                        'entry_time': datetime.now(),
                        'position_type': 'manual',
                        'leverage': SYMBOL_CONFIG[symbol].get('leverage', 10),
                        'ai_monitoring': SYMBOL_CONFIG[symbol].get('ai_monitoring', True)  # ✨ AI 모니터링 플래그
                    }
                    
                    # 🔥 v8.5 Fixed: 포지션 진입 시간 기록 (청산 감지 보호용)
                    if symbol not in position_entry_times:
                        position_entry_times[symbol] = datetime.now()
                        logger.info(f"📝 새 포지션 진입 시간 기록: {symbol} at {position_entry_times[symbol]}")
                    
                    # 🔥 v8.4: 봇 시작 직후인지 확인
                    is_bot_just_started = False
                    if bot_start_time:
                        time_since_start = (datetime.now() - bot_start_time).total_seconds()
                        if time_since_start < 60:  # 봇 시작 후 1분 이내
                            is_bot_just_started = True
                            existing_positions_at_start.add(symbol)
                            logger.info(f"📌 봇 시작시 기존 포지션 발견 - AI 모니터링 대상: {symbol}")
                            logger.info(f"   → Side: {side}, Amount: {abs(contracts):.4f}, Entry: ${entry_price:.2f}")
                            logger.info(f"   → AI 모니터링: {'활성화' if SYMBOL_CONFIG[symbol].get('ai_monitoring', True) else '비활성화'}")
                    
                    if not is_bot_just_started:
                        logger.info(f"🆕🔧 {symbol} 수동 포지션 발견: {side} {abs(contracts):.4f} @ ${entry_price:.2f}")
                        synced_count += 1
                        manual_count += 1
                        
                        # 텔레그램 알림 (진짜 신규 수동 포지션만)
                        if ENABLE_TELEGRAM:
                            send_telegram_notification(
                                f"🔧 <b>수동 포지션 감지</b>\n\n"
                                f"<b>심볼:</b> {symbol}\n"
                                f"<b>방향:</b> {side.upper()}\n"
                                f"<b>진입가:</b> ${entry_price:,.2f}\n"
                                f"<b>수량:</b> {abs(contracts):.4f}\n"
                                f"<b>타입:</b> MANUAL\n\n"
                                f"✅ AI 모니터링이 자동으로 시작됩니다.\n"
                                f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                                'info'
                            )
        
        # 동기화 완료 - 메모리에 없지만 거래소에 있는 포지션 추가
        for symbol, pos_info in new_positions.items():
            if symbol not in current_positions:
                current_positions[symbol] = pos_info
        
        # 🔥 v8.4: 메모리에는 있지만 거래소에 없는 포지션 처리 개선
        removed_symbols = []
        for symbol in list(current_positions.keys()):
            if symbol not in new_positions:
                # 🔥 봇 시작시 있던 포지션인지 확인
                is_existing = symbol in existing_positions_at_start
                
                # 🔥 이미 알림 보낸 청산인지 확인
                already_notified = symbol in positions_already_notified
                
                # 🔥 최근에 체크한 포지션인지 확인 (5초 이내)
                recently_checked = False
                if symbol in last_position_check:
                    time_since_check = (datetime.now() - last_position_check[symbol]).total_seconds()
                    if time_since_check < 5:
                        recently_checked = True
                
                # 정말로 청산된 경우만 처리
                if not is_existing and not already_notified and not recently_checked:
                    try:
                        ticker = exchange.fetch_ticker(symbol)
                        exit_price = ticker['last']
                        position_info = current_positions[symbol]
                        record_completed_trade(symbol, position_info, exit_price, 'sync_detected_close')
                        logger.info(f"✅ {symbol} 청산 확인 및 DB 기록")
                        positions_already_notified.add(symbol)
                    except Exception as e:
                        logger.error(f"청산 기록 실패 ({symbol}): {e}")
                
                removed_symbols.append(symbol)
                
                # 🔥 v8.5 Fixed: 포지션 진입 시간도 제거
                if symbol in position_entry_times:
                    del position_entry_times[symbol]
                    logger.info(f"🗑️ 포지션 진입 시간 제거: {symbol}")
                
                del current_positions[symbol]
                
                if is_existing:
                    logger.info(f"⏭️ {symbol} 봇 시작시 포지션 - 메모리에서만 제거")
                else:
                    logger.warning(f"⚠️ {symbol} 포지션 청산됨 - 메모리에서 제거")
        
        # 🆕 수동 포지션 감지 결과 로깅
        auto_count = sum(1 for pos in current_positions.values() if pos.get('position_type', 'auto') == 'auto')
        manual_total = sum(1 for pos in current_positions.values() if pos.get('position_type', 'auto') == 'manual')
        
        logger.info(f"=== 동기화 완료 ===")
        logger.info(f"총 포지션: {len(current_positions)}개")
        logger.info(f"  - 자동(AI) 포지션: {auto_count}개")
        logger.info(f"  - 수동 포지션: {manual_total}개 (이번 사이클: {manual_count}개)")
        logger.info(f"  - 새로 발견: {synced_count}개")
        logger.info(f"  - 제거: {len(removed_symbols)}개")
        
        return len(current_positions)
        
    except Exception as e:
        logger.error(f"포지션 동기화 오류: {str(e)}", exc_info=True)
        return 0


def cancel_symbol_orders(user_exchange, symbol, user_name="User"):
    """🆕 특정 심볼의 모든 열린 주문 취소 (TP/SL 포함)"""
    try:
        open_orders = user_exchange.fetch_open_orders(symbol)
        
        if not open_orders:
            logger.info(f"[{user_name}] {symbol}: 취소할 주문 없음")
            return 0
        
        cancelled_count = 0
        for order in open_orders:
            try:
                user_exchange.cancel_order(order['id'], symbol)
                order_type = order.get('type', 'UNKNOWN')
                order_side = order.get('side', 'UNKNOWN')
                order_price = order.get('price', 'N/A')
                logger.info(f"[{user_name}] ✅ 주문 취소: {symbol} {order_type} {order_side} @ ${order_price}")
                cancelled_count += 1
            except Exception as e:
                logger.error(f"[{user_name}] 주문 취소 실패 ({order['id']}): {str(e)}")
        
        return cancelled_count
        
    except Exception as e:
        logger.error(f"[{user_name}] {symbol} 주문 취소 중 오류: {str(e)}")
        return 0


def get_position_summary():
    """현재 포지션 요약 정보 (position_type 포함)"""
    if not current_positions:
        return "현재 보유 포지션 없음"
    
    summary = []
    for symbol, pos in current_positions.items():
        pos_type = pos.get('position_type', 'auto')
        type_emoji = "🤖" if pos_type == 'auto' else "🔧"
        summary.append(f"{type_emoji} {symbol}: {pos['side'].upper()} {pos['amount']:.4f} @ ${pos['entry_price']:.2f} ({pos_type.upper()})")
    
    return "\n".join(summary)

# ============ SQLite 데이터베이스 초기화 ============
def record_completed_trade(symbol, position_info, exit_price, close_reason='manual'):
    """완료된 거래를 DB에 기록 (🆕 position_type 포함)"""
    try:
        conn = get_db_connection()
        c = conn.cursor()
        
        # PnL 계산 (레버리지 반영)
        entry_price = position_info.get('entry_price', 0)
        amount = position_info.get('amount', 0)
        side = position_info.get('side', 'buy')
        leverage = position_info.get('leverage', 10)
        position_type = position_info.get('position_type', 'auto')  # 🆕
        
        # 가격 변화율 계산
        if side == 'buy':
            price_change_percent = ((exit_price - entry_price) / entry_price) * 100
        else:  # sell
            price_change_percent = ((entry_price - exit_price) / entry_price) * 100
        
        # 레버리지 적용 - 실제 수익률
        pnl_percent = price_change_percent * leverage
        
        position_size_usdt = amount * entry_price
        pnl_usdt = (position_size_usdt * pnl_percent / 100)
        
        # 보유 시간 계산
        entry_time = position_info.get('entry_time', datetime.now())
        if isinstance(entry_time, str):
            entry_time = datetime.fromisoformat(entry_time)
        holding_time_minutes = (datetime.now() - entry_time).total_seconds() / 60
        
        # is_win 판단
        is_win = 1 if pnl_percent > 0 else 0
        
        # 🔒 중복 기록 방지: 동일한 entry_time과 최근 5초 내 종료 기록 확인
        exit_time = datetime.now()
        if not is_duplicate_completed_trade(conn, symbol, entry_time, exit_time, time_window_seconds=5):
            c.execute("""INSERT INTO completed_trades 
                        (open_timestamp, close_timestamp, symbol, side, entry_price, exit_price,
                         amount, pnl_usdt, pnl_percent, position_size_usdt, holding_time_minutes,
                         close_reason, leverage, is_win, position_type)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                      (entry_time.isoformat(), exit_time.isoformat(), symbol, side, 
                       entry_price, exit_price, amount, pnl_usdt, pnl_percent, position_size_usdt,
                       holding_time_minutes, close_reason, leverage, is_win, position_type))
            
            conn.commit()
            logger.info(f"✅ 완료된 거래 기록: {symbol} ({position_type.upper()}) - PnL: ${pnl_usdt:,.2f} ({pnl_percent:.2f}%)")
        else:
            logger.info(f"⏭️  중복 완료 거래 기록 스킵: {symbol}")
        
        conn.close()
        
        return True
        
    except Exception as e:
        logger.error(f"❌ 완료된 거래 기록 실패: {str(e)}")
        return False

def record_balance_snapshot(exchange):
    """잔고 스냅샷 기록"""
    try:
        conn = get_db_connection()
        c = conn.cursor()
        
        # 잔고 정보 가져오기
        balance = exchange.fetch_balance()
        total_balance = balance['USDT']['total']
        free_balance = balance['USDT']['free']
        used_balance = balance['USDT']['used']
        
        # 활성 포지션 수
        active_positions = len(current_positions)
        
        # 총 포지션 가치
        total_position_value = 0
        for symbol, pos in current_positions.items():
            position_value = pos.get('position_size_usdt', 0)
            if position_value == 0:
                # position_size_usdt가 없으면 계산
                amount = pos.get('amount', 0)
                entry_price = pos.get('entry_price', 0)
                position_value = amount * entry_price
            total_position_value += position_value
        
        # 총 PnL 계산 (완료된 거래들의 합)
        c.execute("SELECT SUM(pnl_usdt) FROM completed_trades")
        result = c.fetchone()
        total_pnl = result[0] if result[0] else 0
        
        # DB에 저장
        c.execute("""INSERT INTO balance_history 
                    (timestamp, total_balance, free_balance, used_balance,
                     active_positions, total_position_value, total_pnl)
                    VALUES (?, ?, ?, ?, ?, ?, ?)""",
                  (datetime.now().isoformat(), total_balance, free_balance, used_balance,
                   active_positions, total_position_value, total_pnl))
        
        conn.commit()
        conn.close()
        
        logger.debug(f"📊 잔고 스냅샷 기록: Total ${total_balance:,.2f}, Free ${free_balance:,.2f}")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ 잔고 스냅샷 기록 실패: {str(e)}")
        return False

def record_position_history(exchange):
    """현재 포지션 히스토리 기록"""
    try:
        conn = get_db_connection()
        c = conn.cursor()
        
        for symbol, pos in current_positions.items():
            # 현재가 조회
            ticker = exchange.fetch_ticker(symbol)
            current_price = ticker['last']
            
            # PnL 계산 (레버리지 반영)
            entry_price = pos.get('entry_price', 0)
            amount = pos.get('amount', 0)
            side = pos.get('side', 'buy')
            leverage = pos.get('leverage', 10)
            
            # 가격 변화율 계산
            if side == 'buy':
                price_change_percent = ((current_price - entry_price) / entry_price) * 100
            else:
                price_change_percent = ((entry_price - current_price) / entry_price) * 100
            
            # 레버리지 적용 - 실제 수익률
            pnl_percent = price_change_percent * leverage
            
            position_size_usdt = amount * entry_price  # 진입 시점 포지션 크기
            position_value = amount * current_price  # 현재 포지션 가치
            pnl_usdt = (position_size_usdt * pnl_percent / 100)
            required_margin = position_value / leverage
            
            # 청산가격 계산 (대략적)
            if side == 'buy':
                liquidation_price = entry_price * (1 - (0.8 / leverage))
            else:
                liquidation_price = entry_price * (1 + (0.8 / leverage))
            
            # DB에 저장
            c.execute("""INSERT INTO position_history 
                        (timestamp, symbol, side, amount, entry_price, current_price,
                         pnl_usdt, pnl_percent, position_value, required_margin, liquidation_price)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                      (datetime.now().isoformat(), symbol, side, amount, entry_price, current_price,
                       pnl_usdt, pnl_percent, position_value, required_margin, liquidation_price))
        
        conn.commit()
        conn.close()
        
        logger.debug(f"📈 포지션 히스토리 기록 완료: {len(current_positions)}개")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ 포지션 히스토리 기록 실패: {str(e)}")
        return False

def get_db_connection():
    """DB 연결 반환 (초기화 메시지 없음)"""
    return sqlite3.connect('integrated_trades.db')

def init_db_once():
    """DB 초기화 - 프로그램 시작 시 1회만 실행 (🆕 position_type 지원)"""
    conn = sqlite3.connect('integrated_trades.db')
    c = conn.cursor()
    
    # 테이블 존재 여부 확인
    c.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table'")
    table_count = c.fetchone()[0]
    
    if table_count >= 4:  # 이미 초기화됨
        # 🆕 v8.1: DB 마이그레이션 (기존 DB 호환성)
        logger.info("🔧 DB 마이그레이션 체크 중...")
        migration_done = False
        
        # 1. completed_trades 테이블에 position_type 컬럼 추가
        try:
            c.execute("SELECT position_type FROM completed_trades LIMIT 1")
        except sqlite3.OperationalError:
            logger.info("🔧 completed_trades 테이블에 position_type 컬럼 추가 중...")
            c.execute("ALTER TABLE completed_trades ADD COLUMN position_type TEXT DEFAULT 'auto'")
            conn.commit()
            logger.info("✅ position_type 컬럼 추가 완료")
            migration_done = True
        
        # 2. completed_trades 테이블에 realized_pnl_binance 컬럼 추가
        try:
            c.execute("SELECT realized_pnl_binance FROM completed_trades LIMIT 1")
        except sqlite3.OperationalError:
            logger.info("🔧 completed_trades 테이블에 realized_pnl_binance 컬럼 추가 중...")
            c.execute("ALTER TABLE completed_trades ADD COLUMN realized_pnl_binance REAL")
            conn.commit()
            logger.info("✅ realized_pnl_binance 컬럼 추가 완료")
            migration_done = True
        
        # 3. realtime_events 테이블 생성 (없으면)
        c.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='realtime_events'")
        if c.fetchone()[0] == 0:
            logger.info("🔧 realtime_events 테이블 생성 중...")
            c.execute('''CREATE TABLE realtime_events
                         (id INTEGER PRIMARY KEY AUTOINCREMENT,
                          event_type TEXT NOT NULL,
                          symbol TEXT NOT NULL,
                          timestamp TEXT NOT NULL,
                          data TEXT,
                          is_processed INTEGER DEFAULT 0,
                          processed_at TEXT)''')
            
            c.execute('''CREATE INDEX idx_realtime_events_processed 
                         ON realtime_events(is_processed, timestamp DESC)''')
            
            conn.commit()
            logger.info("✅ realtime_events 테이블 생성 완료")
            migration_done = True
        
        if migration_done:
            logger.info("✅ DB 마이그레이션 완료 (v8.1 호환)")
        else:
            logger.info("✅ DB 이미 최신 상태 (v8.1)")
        
        conn.close()
        return
    
    # 1. 실시간 거래 테이블 (기존)
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
                  urgency TEXT,
                  status TEXT DEFAULT 'active',
                  position_size_usdt REAL,
                  required_margin REAL,
                  leverage INTEGER)''')
    
    # 2. 완료된 거래 테이블 (대시보드용, 🆕 position_type 컬럼 추가, 🆕 v8.1 realized_pnl_binance 추가)
    c.execute('''CREATE TABLE IF NOT EXISTS completed_trades
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  open_timestamp TEXT NOT NULL,
                  close_timestamp TEXT NOT NULL,
                  symbol TEXT NOT NULL,
                  side TEXT NOT NULL,
                  entry_price REAL,
                  exit_price REAL,
                  amount REAL,
                  pnl_usdt REAL,
                  pnl_percent REAL,
                  position_size_usdt REAL,
                  holding_time_minutes REAL,
                  close_reason TEXT,
                  max_profit_percent REAL,
                  max_loss_percent REAL,
                  leverage INTEGER,
                  is_win INTEGER DEFAULT 0,
                  commission REAL DEFAULT 0,
                  position_type TEXT DEFAULT 'auto',
                  realized_pnl_binance REAL)''')
    
    # 3. 잔고 히스토리 (대시보드용)
    c.execute('''CREATE TABLE IF NOT EXISTS balance_history
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  timestamp TEXT NOT NULL,
                  total_balance REAL,
                  free_balance REAL,
                  used_balance REAL,
                  active_positions INTEGER,
                  total_position_value REAL,
                  total_pnl REAL)''')
    
    # 4. 포지션 히스토리
    c.execute('''CREATE TABLE IF NOT EXISTS position_history
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  timestamp TEXT NOT NULL,
                  symbol TEXT NOT NULL,
                  side TEXT NOT NULL,
                  amount REAL,
                  entry_price REAL,
                  current_price REAL,
                  pnl_usdt REAL,
                  pnl_percent REAL,
                  position_value REAL,
                  required_margin REAL,
                  liquidation_price REAL)''')
    
    # 🆕 v8.1: 5. 실시간 이벤트 테이블 (대시보드 실시간 업데이트용)
    c.execute('''CREATE TABLE IF NOT EXISTS realtime_events
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  event_type TEXT NOT NULL,
                  symbol TEXT NOT NULL,
                  timestamp TEXT NOT NULL,
                  data TEXT,
                  is_processed INTEGER DEFAULT 0,
                  processed_at TEXT)''')
    
    # 인덱스 생성 (성능 향상)
    c.execute('''CREATE INDEX IF NOT EXISTS idx_trades_timestamp 
                 ON trades(timestamp DESC)''')
    c.execute('''CREATE INDEX IF NOT EXISTS idx_completed_trades_timestamp 
                 ON completed_trades(close_timestamp DESC)''')
    c.execute('''CREATE INDEX IF NOT EXISTS idx_balance_history_timestamp 
                 ON balance_history(timestamp DESC)''')
    # 🆕 v8.1: 실시간 이벤트 인덱스
    c.execute('''CREATE INDEX IF NOT EXISTS idx_realtime_events_processed 
                 ON realtime_events(is_processed, timestamp DESC)''')
    
    conn.commit()
    logger.info("✅ DB 초기화 완료 (v8.1 실시간 이벤트 시스템)")
    return conn

# ============ 🆕 v8.1 실시간 이벤트 시스템 ============
def trigger_dashboard_event(event_type, symbol, data=None):
    """
    대시보드로 실시간 이벤트를 전송하는 함수
    
    event_type: 'position_closed', 'position_opened', 'pnl_update', etc.
    symbol: 거래 심볼
    data: 추가 데이터 (딕셔너리)
    """
    try:
        conn = sqlite3.connect('integrated_trades.db')
        c = conn.cursor()
        
        event_data = {
            'event_type': event_type,
            'symbol': symbol,
            'timestamp': datetime.now().isoformat(),
            'data': json.dumps(data) if data else '{}'
        }
        
        c.execute("""
            INSERT INTO realtime_events (event_type, symbol, timestamp, data, is_processed)
            VALUES (?, ?, ?, ?, 0)
        """, (event_type, symbol, event_data['timestamp'], event_data['data']))
        
        conn.commit()
        conn.close()
        
        logger.info(f"🔔 실시간 이벤트 발생: {event_type} - {symbol}")
        
    except Exception as e:
        logger.error(f"이벤트 트리거 오류: {str(e)}")

def fetch_binance_position_pnl(user_exchange, symbol):
    """
    🆕 v8.1: 바이낸스 포지션 히스토리에서 실제 수익률 가져오기
    """
    try:
        # 심볼 형식 변환 (BTC/USDT -> BTCUSDT)
        binance_symbol = symbol.replace('/', '')
        
        # 최근 종료된 포지션 조회
        income_history = user_exchange.fapiPrivateGetIncome({
            'symbol': binance_symbol,
            'incomeType': 'REALIZED_PNL',  # 실현 손익만 조회
            'limit': 10  # 최근 10개
        })
        
        if not income_history:
            return None
        
        # 가장 최근 포지션의 실제 PnL
        latest_pnl = float(income_history[0]['income'])
        timestamp = int(income_history[0]['time'])
        
        return {
            'realized_pnl': latest_pnl,
            'timestamp': datetime.fromtimestamp(timestamp / 1000).isoformat(),
            'symbol': symbol
        }
        
    except Exception as e:
        logger.error(f"바이낸스 PnL 조회 오류 ({symbol}): {str(e)}")
        return None

def record_position_closure_with_real_pnl(symbol, position_data, close_type='manual'):
    """
    🆕 v8.3: 포지션 종료 시 바이낸스 실제 수익률을 기록하고 이벤트 발생
    - 실제 PnL 가져오기 실패시 종료로 판단하지 않음
    
    close_type: 'manual', 'auto', 'sl', 'tp', 'auto_tpsl', 'liquidation', 'auto_close_detected'
    """
    try:
        # 1. 바이낸스에서 실제 PnL 가져오기 시도
        real_pnl_data = fetch_binance_position_pnl(exchange, symbol)
        
        # 🔥 v8.3 수정: 실제 PnL이 없어도 정상 처리
        if real_pnl_data:
            realized_pnl = real_pnl_data['realized_pnl']
            logger.info(f"✅ {symbol} 실제 수익: ${realized_pnl:.2f} (바이낸스 확인)")
            is_binance_confirmed = True
        else:
            # 바이낸스 데이터 없으면 계산된 값 사용
            entry_price = position_data.get('entry_price', 0)
            exit_price = position_data.get('mark_price', entry_price)
            amount = position_data.get('amount', 0)
            side = position_data.get('side', 'unknown')
            leverage = position_data.get('leverage', 10)  # 기본 레버리지 10
            
            # 수익 계산
            if entry_price > 0 and amount > 0:
                if side == 'long':
                    price_change = ((exit_price - entry_price) / entry_price)
                else:  # short
                    price_change = ((entry_price - exit_price) / entry_price)
                
                # 레버리지 적용한 실제 PnL 계산
                realized_pnl = (amount * entry_price * price_change) * leverage
            else:
                realized_pnl = position_data.get('unrealized_pnl', 0)
            
            logger.info(f"📊 {symbol} 계산된 수익: ${realized_pnl:.2f} (레버리지 {leverage}x 적용)")
            is_binance_confirmed = False
        
        # 2. completed_trades 테이블에 기록
        conn = sqlite3.connect('integrated_trades.db')
        c = conn.cursor()
        
        entry_price = position_data.get('entry_price', 0)
        exit_price = position_data.get('mark_price', entry_price)
        amount = position_data.get('amount', 0)
        side = position_data.get('side', 'unknown')
        position_type = position_data.get('position_type', 'auto')
        leverage = position_data.get('leverage', 10)
        
        # 수익률 계산 (레버리지 포함)
        if entry_price > 0:
            if side == 'long':
                pnl_percent = ((exit_price - entry_price) / entry_price) * 100 * leverage
            else:  # short
                pnl_percent = ((entry_price - exit_price) / entry_price) * 100 * leverage
        else:
            pnl_percent = 0
        
        # 보유 시간 계산
        entry_time = position_data.get('entry_time', datetime.now().isoformat())
        exit_dt = datetime.now()
        
        try:
            entry_dt = datetime.fromisoformat(entry_time)
            holding_minutes = (exit_dt - entry_dt).total_seconds() / 60
        except:
            holding_minutes = 0
        
        c.execute("""
            INSERT INTO completed_trades 
            (open_timestamp, close_timestamp, symbol, side, entry_price, exit_price, amount, 
             pnl_usdt, pnl_percent, holding_time_minutes, close_reason, is_win, position_type, realized_pnl_binance)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            entry_time, exit_dt.isoformat(), symbol, side, entry_price, exit_price, amount,
            realized_pnl, pnl_percent, holding_minutes, close_type, 1 if realized_pnl > 0 else 0,
            position_type, realized_pnl if is_binance_confirmed else None
        ))
        
        conn.commit()
        conn.close()
        
        # 3. 실시간 이벤트 발생
        event_data = {
            'symbol': symbol,
            'pnl_usdt': realized_pnl,
            'pnl_percent': pnl_percent,
            'close_type': close_type,
            'side': side,
            'is_binance_confirmed': is_binance_confirmed
        }
        
        trigger_dashboard_event('position_closed', symbol, event_data)
        
        logger.info(f"📊 {symbol} 포지션 종료 기록 완료 (PnL: ${realized_pnl:.2f}, 확인: {is_binance_confirmed})")
        
        return realized_pnl
        
    except Exception as e:
        logger.error(f"포지션 종료 기록 오류 ({symbol}): {str(e)}")
        return None

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
            'risk_level': str ('low', 'medium', 'high', 'extreme'),
            'warnings': list,
            'scores': dict,
            'reverse_opportunity': bool,  # 🆕 반대 진입 기회
            'reverse_signals': list  # 🆕 반대 진입 신호
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
            'is_adjusted': bool,
            'pl_ratio': float
        }
    """
    try:
        df_15min = market_data['df_15min']  # 🆕 15분봉 추가
        df_hourly = market_data['df_hourly']
        df_4h = market_data['df_4h']
        
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
        
        # 최종 검증: Risk/Reward 비율 체크
        sl_distance = abs(adjusted_sl - current_price)
        tp_distance = abs(adjusted_tp - current_price)
        
        if sl_distance > 0:
            rr_ratio = tp_distance / sl_distance
            
            # R:R이 1:1.5 미만이면 TP 늘리기
            if rr_ratio < 1.5:
                if action == 'buy':
                    adjusted_tp = current_price + (sl_distance * 2)
                else:
                    adjusted_tp = current_price - (sl_distance * 2)
                tp_reason += " (R:R 1:2 확보)"
                is_adjusted = True
        
        logger.info(f"💡 TP/SL 조정 결과:")
        logger.info(f"   SL: ${original_sl:.4f} → ${adjusted_sl:.4f} ({sl_reason})")
        logger.info(f"   TP: ${original_tp:.4f} → ${adjusted_tp:.4f} ({tp_reason})")
        
        return {
            'adjusted_sl': adjusted_sl,
            'adjusted_tp': adjusted_tp,
            'sl_reason': sl_reason,
            'tp_reason': tp_reason,
            'is_adjusted': is_adjusted,
            'volume_profile': {
                'support_levels': volume_profile_1h['support_levels'][:3],
                'resistance_levels': volume_profile_1h['resistance_levels'][:3]
            }
        }
        
    except Exception as e:
        logger.error(f"TP/SL 조정 오류: {e}")
        return {
            'adjusted_sl': original_sl,
            'adjusted_tp': original_tp,
            'sl_reason': "조정 실패 - 원본 유지",
            'tp_reason': "조정 실패 - 원본 유지",
            'is_adjusted': False
        }

# ============ 🆕 추가 기능 3: 추세 역전 신호 감지 함수 (개선됨) ============
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
            'signals': list,
            'threshold_immediate': int,
            'threshold_soon': int,
            'threshold_watch': int
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

# 기존 detect_early_reversal_signals 함수는 유지 (하위 호환성)
def detect_early_reversal_signals(df_15min, df_hourly, df_4h, position_side, current_price, entry_price):
    """
    추세 역전 직전 신호 조기 감지
    
    Returns:
        dict: {
            'should_exit': bool,
            'urgency': str ('immediate', 'soon', 'watch'),
            'confidence': float,
            'signals': list,
            'score': int
        }
    """
    signals = []
    reversal_score = 0
    
    # === 1. Divergence 감지 (가장 강력한 신호) ===
    try:
        # RSI Divergence
        recent_prices_15m = df_15min['close'].tail(10).values
        recent_rsi_15m = df_15min['rsi'].tail(10).values
        
        if position_side == 'buy':
            # Bearish Divergence: 가격은 상승하지만 RSI는 하락
            if recent_prices_15m[-1] > recent_prices_15m[-5] and recent_rsi_15m[-1] < recent_rsi_15m[-5]:
                if recent_rsi_15m[-1] > 60:  # 과매수 영역에서 발생
                    signals.append("🔴 15분봉 Bearish Divergence (과매수 영역)")
                    reversal_score += 4
                else:
                    signals.append("🟡 15분봉 Bearish Divergence")
                    reversal_score += 2
        else:  # sell
            # Bullish Divergence: 가격은 하락하지만 RSI는 상승
            if recent_prices_15m[-1] < recent_prices_15m[-5] and recent_rsi_15m[-1] > recent_rsi_15m[-5]:
                if recent_rsi_15m[-1] < 40:  # 과매도 영역에서 발생
                    signals.append("🔴 15분봉 Bullish Divergence (과매도 영역)")
                    reversal_score += 4
                else:
                    signals.append("🟡 15분봉 Bullish Divergence")
                    reversal_score += 2
                    
    except Exception as e:
        logger.debug(f"Divergence 감지 오류: {e}")
    
    # === 2. MACD 크로스오버 직전 신호 ===
    try:
        macd_15m = df_15min['macd'].iloc[-1]
        macd_signal_15m = df_15min['macd_signal'].iloc[-1]
        macd_hist_15m = df_15min['macd_diff'].iloc[-1] if 'macd_diff' in df_15min.columns else 0
        macd_hist_prev_15m = df_15min['macd_diff'].iloc[-2] if 'macd_diff' in df_15min.columns else 0
        
        macd_1h = df_hourly['macd'].iloc[-1]
        macd_signal_1h = df_hourly['macd_signal'].iloc[-1]
        
        if position_side == 'buy':
            # MACD 히스토그램이 줄어드는 중 (모멘텀 약화)
            if macd_hist_15m < macd_hist_prev_15m and macd_hist_15m > 0:
                signals.append("⚠️ 15분봉 MACD 모멘텀 약화")
                reversal_score += 2
            
            # MACD가 시그널에 근접 (크로스오버 임박)
            if 0 < (macd_15m - macd_signal_15m) < 0.5:
                signals.append("🔴 15분봉 MACD 크로스오버 임박")
                reversal_score += 3
            
            # 1시간봉에서도 Bearish 크로스
            if macd_1h < macd_signal_1h and df_hourly['macd'].iloc[-2] >= df_hourly['macd_signal'].iloc[-2]:
                signals.append("🔴 1시간봉 MACD Bearish 크로스")
                reversal_score += 4
                
        else:  # sell
            if macd_hist_15m > macd_hist_prev_15m and macd_hist_15m < 0:
                signals.append("⚠️ 15분봉 MACD 모멘텀 약화")
                reversal_score += 2
            
            if -0.5 < (macd_15m - macd_signal_15m) < 0:
                signals.append("🔴 15분봉 MACD 크로스오버 임박")
                reversal_score += 3
            
            if macd_1h > macd_signal_1h and df_hourly['macd'].iloc[-2] <= df_hourly['macd_signal'].iloc[-2]:
                signals.append("🔴 1시간봉 MACD Bullish 크로스")
                reversal_score += 4
                
    except Exception as e:
        logger.debug(f"MACD 신호 감지 오류: {e}")
    
    # === 3. ADX 트렌드 강도 약화 ===
    try:
        adx_1h = df_hourly['adx'].iloc[-1]
        adx_prev_1h = df_hourly['adx'].iloc[-2]
        
        # ADX가 하락 중 (트렌드 약화)
        if adx_1h < adx_prev_1h and adx_1h < 25:
            signals.append("⚠️ ADX 하락 (트렌드 약화)")
            reversal_score += 2
        
        # DI 크로스오버
        di_plus_1h = df_hourly['di_plus'].iloc[-1]
        di_minus_1h = df_hourly['di_minus'].iloc[-1]
        di_plus_prev = df_hourly['di_plus'].iloc[-2]
        di_minus_prev = df_hourly['di_minus'].iloc[-2]
        
        if position_side == 'buy':
            # DI- 가 DI+ 위로 크로스
            if di_minus_1h > di_plus_1h and di_minus_prev <= di_plus_prev:
                signals.append("🔴 DI 크로스오버 (매도 우세)")
                reversal_score += 4
        else:
            if di_plus_1h > di_minus_1h and di_plus_prev <= di_minus_prev:
                signals.append("🔴 DI 크로스오버 (매수 우세)")
                reversal_score += 4
                
    except Exception as e:
        logger.debug(f"ADX 분석 오류: {e}")
    
    # === 4. CMF (Chaikin Money Flow) 반전 ===
    try:
        cmf_1h = df_hourly['cmf'].iloc[-1]
        cmf_prev_1h = df_hourly['cmf'].iloc[-2]
        
        if position_side == 'buy':
            # CMF가 양수에서 음수로 (자금 유출)
            if cmf_1h < 0 and cmf_prev_1h >= 0:
                signals.append("🔴 CMF 반전 (자금 유출)")
                reversal_score += 3
            elif cmf_1h < -0.1:
                signals.append("⚠️ CMF 음수 (약한 자금 흐름)")
                reversal_score += 1
        else:
            if cmf_1h > 0 and cmf_prev_1h <= 0:
                signals.append("🔴 CMF 반전 (자금 유입)")
                reversal_score += 3
            elif cmf_1h > 0.1:
                signals.append("⚠️ CMF 양수 (강한 자금 흐름)")
                reversal_score += 1
                
    except Exception as e:
        logger.debug(f"CMF 분석 오류: {e}")
    
    # === 최종 판단 ===
    should_exit = False
    urgency = 'none'
    confidence = 0.0
    
    if reversal_score >= 10:
        should_exit = True
        urgency = 'immediate'
        confidence = min(reversal_score / 15, 1.0)
    elif reversal_score >= 7:
        should_exit = True
        urgency = 'soon'
        confidence = reversal_score / 15
    elif reversal_score >= 4:
        urgency = 'watch'
        confidence = reversal_score / 15
    
    return {
        'should_exit': should_exit,
        'urgency': urgency,
        'confidence': confidence,
        'reversal_score': reversal_score,
        'signals': signals,
        'threshold_immediate': 10,
        'threshold_soon': 7,
        'threshold_watch': 4
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
            AND timestamp >= ?
        """, (symbol, action, trade_type, cutoff_time))
        
        count = c.fetchone()[0]
        
        if count > 0:
            logger.warning(
                f"⚠️ 중복 거래 기록 감지: {symbol} {action} {trade_type} "
                f"(최근 {time_window_seconds}초 내 {count}건 존재)"
            )
            return True
        
        return False
        
    except Exception as e:
        logger.error(f"중복 체크 오류: {e}")
        # 오류 발생 시 안전하게 False 반환 (기록 허용)
        return False

def is_duplicate_completed_trade(conn, symbol, entry_time, exit_time, time_window_seconds=5):
    """
    완료된 거래 중복 체크
    최근 N초 이내에 동일한 symbol, entry_price로 종료된 거래가 있는지 확인
    
    Args:
        conn: DB 연결
        symbol: 심볼
        entry_time: 진입 시간
        exit_time: 청산 시간
        time_window_seconds: 중복 체크 시간 범위 (초)
    
    Returns:
        bool: 중복이면 True, 아니면 False
    """
    try:
        c = conn.cursor()
        
        # entry_time과 exit_time을 문자열로 변환
        if isinstance(entry_time, datetime):
            entry_time_str = entry_time.isoformat()
        else:
            entry_time_str = entry_time
            
        if isinstance(exit_time, datetime):
            exit_time_str = exit_time.isoformat()
        else:
            exit_time_str = exit_time
        
        # 동일한 symbol, entry_time으로 최근 종료된 거래 확인
        c.execute("""
            SELECT COUNT(*) FROM completed_trades 
            WHERE symbol = ? 
            AND open_timestamp = ?
            AND close_timestamp >= datetime(?, '-' || ? || ' seconds')
        """, (symbol, entry_time_str, exit_time_str, time_window_seconds))
        
        count = c.fetchone()[0]
        
        if count > 0:
            logger.warning(
                f"⚠️ 중복 완료 거래 감지: {symbol} "
                f"(최근 {time_window_seconds}초 내 {count}건 존재)"
            )
            return True
        
        return False
        
    except Exception as e:
        logger.error(f"완료 거래 중복 체크 오류: {e}")
        # 오류 발생 시 안전하게 False 반환 (기록 허용)
        return False

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
    """투자 성과 계산 - 개선 버전 (풍부한 통계 데이터 제공)"""
    if trades_df.empty:
        return {
            'total_trades': 0,
            'win_rate': 0,
            'avg_pnl_percent': 0,
            'total_pnl': 0,
            'best_trade': 0,
            'worst_trade': 0,
            'avg_holding_time': 0,
            'recent_trend': 'neutral',
            'risk_reward_ratio': 0
        }
    
    # completed_trades에서 실제 거래 성과 데이터 조회
    try:
        conn = get_db_connection()
        c = conn.cursor()
        
        # 최근 완료된 거래 조회 (최대 50건)
        c.execute("""
            SELECT 
                pnl_usdt,
                pnl_percent,
                is_win,
                holding_time_minutes,
                entry_price,
                exit_price,
                close_timestamp
            FROM completed_trades 
            WHERE symbol IN (SELECT DISTINCT symbol FROM trades WHERE timestamp >= datetime('now', '-7 days'))
            ORDER BY close_timestamp DESC
            LIMIT 50
        """)
        
        completed_trades = c.fetchall()
        conn.close()
        
        if not completed_trades:
            return {
                'total_trades': len(trades_df),
                'win_rate': 0,
                'avg_pnl_percent': 0,
                'total_pnl': 0,
                'best_trade': 0,
                'worst_trade': 0,
                'avg_holding_time': 0,
                'recent_trend': 'no_data',
                'risk_reward_ratio': 0
            }
        
        # 통계 계산
        total_completed = len(completed_trades)
        winning_trades = sum(1 for t in completed_trades if t[2] == 1)
        win_rate = (winning_trades / total_completed * 100) if total_completed > 0 else 0
        
        pnl_values = [t[0] for t in completed_trades if t[0] is not None]
        pnl_percents = [t[1] for t in completed_trades if t[1] is not None]
        
        total_pnl = sum(pnl_values) if pnl_values else 0
        avg_pnl_percent = sum(pnl_percents) / len(pnl_percents) if pnl_percents else 0
        best_trade = max(pnl_values) if pnl_values else 0
        worst_trade = min(pnl_values) if pnl_values else 0
        
        holding_times = [t[3] for t in completed_trades if t[3] is not None]
        avg_holding_time = sum(holding_times) / len(holding_times) if holding_times else 0
        
        # 최근 추세 분석 (최근 10거래)
        recent_10 = completed_trades[:10] if len(completed_trades) >= 10 else completed_trades
        recent_wins = sum(1 for t in recent_10 if t[2] == 1)
        recent_win_rate = (recent_wins / len(recent_10) * 100) if recent_10 else 0
        
        if recent_win_rate >= 60:
            recent_trend = 'improving'
        elif recent_win_rate <= 40:
            recent_trend = 'declining'
        else:
            recent_trend = 'stable'
        
        # Risk/Reward Ratio 계산
        winning_pnl = [t[0] for t in completed_trades if t[2] == 1 and t[0] is not None]
        losing_pnl = [abs(t[0]) for t in completed_trades if t[2] == 0 and t[0] is not None]
        
        avg_win = sum(winning_pnl) / len(winning_pnl) if winning_pnl else 0
        avg_loss = sum(losing_pnl) / len(losing_pnl) if losing_pnl else 1
        risk_reward_ratio = avg_win / avg_loss if avg_loss > 0 else 0
        
        return {
            'total_trades': total_completed,
            'win_rate': win_rate,
            'avg_pnl_percent': avg_pnl_percent,
            'total_pnl': total_pnl,
            'best_trade': best_trade,
            'worst_trade': worst_trade,
            'avg_holding_time': avg_holding_time,
            'recent_trend': recent_trend,
            'risk_reward_ratio': risk_reward_ratio,
            'recent_win_rate': recent_win_rate
        }
        
    except Exception as e:
        logger.error(f"Error calculating performance: {e}")
        return {
            'total_trades': 0,
            'win_rate': 0,
            'avg_pnl_percent': 0,
            'total_pnl': 0,
            'best_trade': 0,
            'worst_trade': 0,
            'avg_holding_time': 0,
            'recent_trend': 'error',
            'risk_reward_ratio': 0
        }

def generate_reflection(trades_df, current_market_data):
    """AI를 사용한 심층 반성 및 개선 사항 생성 - 개선 버전"""
    performance = calculate_performance(trades_df)
    
    client = OpenAI(api_key=os.getenv("DEEPSEEK_API_KEY"), base_url="https://api.deepseek.com")
    if not client.api_key:
        logger.error("OpenAI API key is missing or invalid.")
        return None
    
    # 최근 거래 데이터를 더 구조화해서 준비
    recent_trades_summary = "No recent trades"
    if not trades_df.empty and len(trades_df) > 0:
        try:
            # 최근 거래 요약 정보 추출
            recent_trades_list = []
            for idx, trade in trades_df.head(10).iterrows():
                trade_info = {
                    'symbol': trade.get('symbol', 'N/A'),
                    'action': trade.get('action', 'N/A'),
                    'timestamp': trade.get('timestamp', 'N/A'),
                    'ai_decision': trade.get('ai_decision', 'N/A')
                }
                recent_trades_list.append(trade_info)
            recent_trades_summary = json.dumps(recent_trades_list, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning(f"Error formatting recent trades: {e}")
            recent_trades_summary = "Error formatting trades data"
    
    # 계좌 잔고 변화 추세 분석
    try:
        conn = get_db_connection()
        c = conn.cursor()
        
        # 최근 24시간 잔고 변화
        c.execute("""
            SELECT total_balance, timestamp 
            FROM balance_history 
            WHERE timestamp >= datetime('now', '-1 day')
            ORDER BY timestamp ASC
        """)
        balance_history = c.fetchall()
        
        if len(balance_history) >= 2:
            initial_balance = balance_history[0][0]
            current_balance = balance_history[-1][0]
            balance_change = ((current_balance - initial_balance) / initial_balance * 100) if initial_balance > 0 else 0
            balance_trend = f"24h Balance Change: {balance_change:+.2f}% (${initial_balance:.2f} → ${current_balance:.2f})"
        else:
            balance_trend = "Insufficient balance history"
        
        conn.close()
    except Exception as e:
        logger.warning(f"Error fetching balance trend: {e}")
        balance_trend = "Balance trend unavailable"
    
    try:
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {
                    "role": "system",
                    "content": """You are an elite crypto trading analyst AI with deep expertise in technical analysis, risk management, and pattern recognition.

Your role is to provide ACTIONABLE, SPECIFIC, and INSIGHTFUL analysis that will help validate future trading signals. This reflection will be used as critical context for making real trading decisions.

CRITICAL: Your analysis must be:
1. SPECIFIC - Use exact numbers, percentages, and concrete observations
2. ACTIONABLE - Provide clear guidance that can be applied to signal validation
3. PATTERN-FOCUSED - Identify recurring mistakes or winning strategies
4. RISK-AWARE - Highlight risk management issues and improvements
5. MARKET-CONTEXTUAL - Consider current market conditions in your assessment"""
                },
                {
                    "role": "user",
                    "content": f"""Analyze the recent trading performance and provide a comprehensive reflection for improving future trading decisions.

**PERFORMANCE STATISTICS:**
- Total Completed Trades: {performance['total_trades']}
- Overall Win Rate: {performance['win_rate']:.1f}%
- Recent Win Rate (Last 10): {performance.get('recent_win_rate', 0):.1f}%
- Performance Trend: {performance['recent_trend'].upper()}
- Average PnL per Trade: {performance['avg_pnl_percent']:.2f}%
- Total PnL: ${performance['total_pnl']:.2f}
- Best Trade: ${performance['best_trade']:.2f}
- Worst Trade: ${performance['worst_trade']:.2f}
- Risk/Reward Ratio: {performance['risk_reward_ratio']:.2f}
- Average Holding Time: {performance['avg_holding_time']:.1f} minutes

**BALANCE TREND:**
{balance_trend}

**RECENT TRADES DETAIL:**
{recent_trades_summary}

**CURRENT MARKET SNAPSHOT:**
- Symbol: {current_market_data.get('symbol', 'N/A')}
- Current Price: ${current_market_data.get('current_price', 0):.2f}

Based on this data, provide a structured reflection with the following sections:

1. **PERFORMANCE ASSESSMENT** (2-3 sentences):
   - Is the win rate acceptable? Is there improvement or decline?
   - Is the risk/reward ratio healthy (should be >1.5)?
   - What does the PnL trend indicate?

2. **KEY STRENGTHS** (2-3 bullet points):
   - What trading patterns or strategies are working well?
   - Which market conditions lead to successful trades?

3. **CRITICAL WEAKNESSES** (2-3 bullet points):
   - What mistakes are being repeated?
   - Where is risk management failing?
   - What entry/exit timing issues exist?

4. **ACTIONABLE RECOMMENDATIONS** (3-4 specific points):
   - For ENTRY signals: What should AI look for or avoid?
   - For EXIT signals: When should positions be closed?
   - Risk management: How should stop-loss and take-profit be adjusted?
   - Market conditions: What conditions favor trading vs. holding?

5. **SIGNAL VALIDATION GUIDANCE** (2-3 points):
   - What technical indicators are most reliable in current conditions?
   - What are red flags that should trigger rejection?
   - What confluence of factors should increase confidence?

Keep your response concise but packed with specific, actionable insights. Use data from the statistics to support your points."""
                }
            ],
            temperature=0.3,
            max_tokens=2000
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
    🆕 자동/수동 포지션 모두 모니터링
    Pydantic 검증 및 에러 처리 강화
    """
    
    # 🆕 포지션 타입 확인
    position_type = position_info.get('position_type', 'auto')
    type_indicator = "🤖" if position_type == 'auto' else "🔧"
    
    logger.info(f"{type_indicator} AI 모니터링 시작: {symbol} ({position_type.upper()} 포지션)")
    
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
        
        # 포지션 정보
        entry_price = position_info['entry_price']
        current_price = market_data['current_price']
        side = position_info['side']
        amount = position_info['amount']
        stop_loss = position_info.get('stop_loss', 0)
        take_profit = position_info.get('take_profit', 0)
        
        # PnL 계산 (레버리지 반영)
        if side == 'buy':
            price_change_percent = ((current_price - entry_price) / entry_price) * 100
            distance_to_sl = ((current_price - stop_loss) / current_price) * 100 if stop_loss else 100
            distance_to_tp = ((take_profit - current_price) / current_price) * 100 if take_profit else 100
        else:  # sell
            price_change_percent = ((entry_price - current_price) / entry_price) * 100
            distance_to_sl = ((stop_loss - current_price) / current_price) * 100 if stop_loss else 100
            distance_to_tp = ((current_price - take_profit) / current_price) * 100 if take_profit else 100
        
        # 레버리지 적용 - 실제 수익률
        pnl_percent = price_change_percent * leverage
        
        # 포지션 크기 (USDT)
        position_size_usdt = amount * entry_price
        pnl_usdt = position_size_usdt * pnl_percent / 100
        
        # 포지션 보유 시간
        entry_time = position_info.get('entry_time', datetime.now())
        holding_time = (datetime.now() - entry_time).total_seconds() / 60  # 분 단위
        holding_hours = holding_time / 60
        
        # Technical Indicators
        df_15min = market_data['df_15min']
        df_hourly = market_data['df_hourly']
        df_4h = market_data['df_4h']
        
        # ATR 값 안전하게 추출 (NaN, 0, undefined 체크)
        def safe_get_atr(df, timeframe_name, current_price):
            """ATR을 안전하게 추출하는 헬퍼 함수"""
            try:
                if 'atr' not in df.columns:
                    logger.warning(f"⚠️ ATR column missing in {timeframe_name}")
                    return current_price * 0.002
                
                atr_value = df['atr'].iloc[-1]
                
                # NaN, None, 0 체크
                if pd.isna(atr_value) or atr_value is None or atr_value == 0:
                    logger.warning(f"⚠️ {symbol} ATR({timeframe_name}) is invalid: {atr_value}")
                    # 대체값: 최근 5개 캔들의 평균 범위
                    if len(df) >= 5:
                        recent_range = (df['high'].iloc[-5:] - df['low'].iloc[-5:]).mean()
                        if recent_range > 0:
                            logger.info(f"   → Using recent range as ATR: {recent_range:.4f}")
                            return recent_range
                    # 최종 대체값: 가격의 일정 비율
                    default_atr = current_price * 0.002  # 0.2%
                    logger.info(f"   → Using default ATR: {default_atr:.4f}")
                    return default_atr
                
                return atr_value
            except Exception as e:
                logger.error(f"Error getting ATR for {timeframe_name}: {e}")
                return current_price * 0.002
        
        # 각 타임프레임별 ATR 추출
        atr_15min = safe_get_atr(df_15min, '5m', current_price)
        atr_hourly = safe_get_atr(df_hourly, '1h', current_price)
        atr_4h = safe_get_atr(df_4h, '4h', current_price)
        
        # ATR 로깅 (디버깅용)
        logger.debug(f"{symbol} ATR values - 15m: {atr_15min:.4f}, 1h: {atr_hourly:.4f}, 4h: {atr_4h:.4f}")
        
        # 🆕 조기 종료 신호 감지
        early_exit_signals = detect_early_reversal_signals(
            df_15min, df_hourly, df_4h, side, current_price, entry_price
        )
        
        # 조기 종료 신호 로깅
        if early_exit_signals['should_exit']:
            logger.warning(f"🚨 조기 종료 신호 감지!")
            logger.warning(f"   긴급도: {early_exit_signals['urgency']}")
            logger.warning(f"   신뢰도: {early_exit_signals['confidence']:.1%}")
            logger.warning(f"   역전 점수: {early_exit_signals['reversal_score']}/15")
            for signal in early_exit_signals['signals']:
                logger.warning(f"   - {signal}")
            
            # 텔레그램 알림
            if ENABLE_TELEGRAM:
                urgency_emoji = "🔴" if early_exit_signals['urgency'] == 'immediate' else "🟡"
                signal_msg = f"""
{urgency_emoji} <b>추세 역전 조기 신호 감지</b>

<b>심볼:</b> {symbol}
<b>포지션:</b> {side.upper()}
<b>진입가:</b> ${entry_price:,.2f}
<b>현재가:</b> ${current_price:,.2f}
<b>수익률:</b> {pnl_percent:+.2f}%

<b>⚠️ 감지된 신호:</b>
"""
                for signal in early_exit_signals['signals'][:4]:  # 상위 4개만
                    signal_msg += f"• {signal}\n"
                
                signal_msg += f"""
<b>긴급도:</b> {early_exit_signals['urgency'].upper()}
<b>신뢰도:</b> {early_exit_signals['confidence']:.1%}
<b>역전 점수:</b> {early_exit_signals['reversal_score']}/15

💡 AI가 포지션 종료를 검토 중입니다...

⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
                """.strip()
                send_telegram_notification(signal_msg, 'warning' if early_exit_signals['urgency'] == 'immediate' else 'info')
        elif early_exit_signals['urgency'] == 'watch':
            logger.info(f"👀 약한 역전 신호 감지 (점수: {early_exit_signals['reversal_score']}/15)")
            for signal in early_exit_signals['signals']:
                logger.info(f"   - {signal}")
        
        json_template = """
{
    "decision": "hold",
    "percentage": 0,
    "reason": "Strong momentum continues, no reversal signals detected",
    "exit_type": "none",
    "confidence": 0.85,
    "urgency": "none",
    "add_position_margin_percent": 0,
    "expected_win_rate": 0.0
}"""

        prompt = f"""
You are an elite AI position manager monitoring an active {side.upper()} position for {symbol}. Your mission is to protect profits, minimize losses, and identify optimal exit points using multi-timeframe analysis.

**CRITICAL CONTEXT:**
This is a LEVERAGED position ({leverage}x) - small price movements have AMPLIFIED impact on P&L.

🚨 **EARLY REVERSAL DETECTION SYSTEM:**
{'═' * 43}
→ Reversal Risk Score: {early_exit_signals['reversal_score']}/15
→ Should Exit: {'YES ⚠️' if early_exit_signals['should_exit'] else 'NO ✅'}
→ Urgency Level: {early_exit_signals['urgency'].upper()}
→ Confidence: {early_exit_signals['confidence']:.1%}

→ Detected Signals ({len(early_exit_signals['signals'])}):
{chr(10).join(['  • ' + sig for sig in early_exit_signals['signals']]) if early_exit_signals['signals'] else '  • No reversal signals detected'}

💡 **INTERPRETATION:**
  • Score ≥ 10: IMMEDIATE exit recommended
  • Score 7-9: EXIT SOON (strong reversal signals)
  • Score 4-6: WATCH closely (early warning)
  • Score < 4: No significant reversal risk

{'⚠️ WARNING: Multiple reversal signals detected! Consider this heavily in your decision.' if early_exit_signals['should_exit'] else '✅ No major reversal concerns detected. Focus on other technical factors.'}
{'═' * 43}

═══════════════════════════════════════════
💼 **POSITION STATUS**
═══════════════════════════════════════════
→ Position Details:
  • Type: {position_type.upper()} ({type_indicator})
  • Direction: {side.upper()}
  • Entry Price: ${entry_price:,.2f}
  • Current Price: ${current_price:,.2f}
  • Position Size: {amount:.4f} ({position_size_usdt:,.2f} USDT)
  • Leverage: {leverage}x

→ Performance Metrics:
  • Price Change: {price_change_percent:+.2f}%
  • **LEVERAGED P&L: {pnl_percent:+.2f}%** ({pnl_usdt:+,.2f} USDT)
  • Holding Time: {holding_time:.0f} minutes ({holding_hours:.1f} hours)

→ Risk Management:
  • Stop Loss: {'$' + f'{stop_loss:,.2f}' if stop_loss else 'Not Set'} {'(' + f'{distance_to_sl:.2f}%' + ' away)' if stop_loss else ''}
  • Take Profit: {'$' + f'{take_profit:,.2f}' if take_profit else 'Not Set'} {'(' + f'{distance_to_tp:.2f}%' + ' away)' if take_profit else ''}

→ Account Context:
  • Total Balance: ${total_margin:,.2f} USDT
  • Free Balance: ${free_margin:,.2f} USDT
  • Position Impact on Account: {(pnl_usdt / total_margin * 100) if total_margin > 0 else 0:+.2f}%

═══════════════════════════════════════════
📊 **MULTI-TIMEFRAME TECHNICAL ANALYSIS**
═══════════════════════════════════════════

→ **15-MINUTE CHART (Immediate Momentum)**
═══════════════════════════════════════════
  Momentum Indicators:
  • RSI(14): {df_15min['rsi'].iloc[-1]:.2f} {'[OVERBOUGHT]' if df_15min['rsi'].iloc[-1] > 70 else '[OVERSOLD]' if df_15min['rsi'].iloc[-1] < 30 else '[NEUTRAL]'}
  • Stochastic %K: {df_15min['stoch_k'].iloc[-1]:.2f}, %D: {df_15min['stoch_d'].iloc[-1]:.2f}
  • Williams %R: {df_15min['williams_r'].iloc[-1]:.2f}
  • PPO: {df_15min['ppo'].iloc[-1]:.2f}

  Trend Analysis:
  • MACD: {df_15min['macd'].iloc[-1]:.2f}
  • MACD Signal: {df_15min['macd_signal'].iloc[-1]:.2f}
  • MACD Diff: {df_15min['macd_diff'].iloc[-1]:.2f} {'[BULLISH]' if df_15min['macd_diff'].iloc[-1] > 0 else '[BEARISH]'}
  • ADX: {df_15min['adx'].iloc[-1]:.2f} {'[STRONG TREND]' if df_15min['adx'].iloc[-1] > 25 else '[WEAK TREND]'}
  • DI+: {df_15min['di_plus'].iloc[-1]:.2f} vs DI-: {df_15min['di_minus'].iloc[-1]:.2f}

  Price Position:
  • Bollinger Upper: ${df_15min['bb_bbh'].iloc[-1]:.2f}
  • Bollinger Middle: ${df_15min['bb_bbm'].iloc[-1]:.2f}
  • Bollinger Lower: ${df_15min['bb_bbl'].iloc[-1]:.2f}
  • Current Position: {((current_price - df_15min['bb_bbl'].iloc[-1]) / (df_15min['bb_bbh'].iloc[-1] - df_15min['bb_bbl'].iloc[-1]) * 100):.0f}% of band
  • ATR(14): {atr_15min:.4f} (volatility indicator)

  Volume & Flow:
  • CMF(20): {df_15min['cmf'].iloc[-1]:.2f} {'[BUYING PRESSURE]' if df_15min['cmf'].iloc[-1] > 0 else '[SELLING PRESSURE]'}

→ **1-HOUR CHART (Medium-term Trend)**
═══════════════════════════════════════════
  Momentum:
  • RSI(14): {df_hourly['rsi'].iloc[-1]:.2f} {'[OVERBOUGHT]' if df_hourly['rsi'].iloc[-1] > 70 else '[OVERSOLD]' if df_hourly['rsi'].iloc[-1] < 30 else '[NEUTRAL]'}

  Trend:
  • MACD: {df_hourly['macd'].iloc[-1]:.2f}
  • MACD Signal: {df_hourly['macd_signal'].iloc[-1]:.2f}
  • ADX: {df_hourly['adx'].iloc[-1]:.2f} {'[STRONG]' if df_hourly['adx'].iloc[-1] > 25 else '[WEAK]'}
  • DI+: {df_hourly['di_plus'].iloc[-1]:.2f} vs DI-: {df_hourly['di_minus'].iloc[-1]:.2f}

  Price:
  • Bollinger Middle: ${df_hourly['bb_bbm'].iloc[-1]:.2f}
  • ATR: {atr_hourly:.4f}

  Volume:
  • CMF: {df_hourly['cmf'].iloc[-1]:.2f} {'[BUYING]' if df_hourly['cmf'].iloc[-1] > 0 else '[SELLING]'}

→ **4-HOUR CHART (Primary Trend)**
═══════════════════════════════════════════
  Momentum:
  • RSI(14): {df_4h['rsi'].iloc[-1]:.2f} {'[OVERBOUGHT]' if df_4h['rsi'].iloc[-1] > 70 else '[OVERSOLD]' if df_4h['rsi'].iloc[-1] < 30 else '[NEUTRAL]'}

  Trend:
  • MACD: {df_4h['macd'].iloc[-1]:.2f}
  • MACD Signal: {df_4h['macd_signal'].iloc[-1]:.2f}
  • ADX: {df_4h['adx'].iloc[-1]:.2f} {'[STRONG]' if df_4h['adx'].iloc[-1] > 25 else '[WEAK]'}
  • DI+: {df_4h['di_plus'].iloc[-1]:.2f} vs DI-: {df_4h['di_minus'].iloc[-1]:.2f}

  Volume:
  • CMF: {df_4h['cmf'].iloc[-1]:.2f} {'[BUYING]' if df_4h['cmf'].iloc[-1] > 0 else '[SELLING]'}

═══════════════════════════════════════════
🎯 **EXIT DECISION FRAMEWORK**
═══════════════════════════════════════════

**For {'LONG' if side == 'buy' else 'SHORT'} Position:**

**Context for Decision Making:**
- Current ATR (5m): {atr_15min:.4f} - Use this as volatility baseline
- Price volatility is relative to this asset's normal movement
- Consider timeframe alignment more than absolute profit percentages

⚠️ **IMMEDIATE EXIT SIGNALS (Close 100%):**
{'- 15m MACD bearish crossover + RSI declining from overbought zone' if side == 'buy' else '- 15m MACD bullish crossover + RSI rising from oversold zone'}
{'- 1h DI- crosses above DI+ (definitive trend reversal)' if side == 'buy' else '- 1h DI+ crosses above DI- (definitive trend reversal)'}
{'- CMF turning negative across 2+ timeframes (money flowing out)' if side == 'buy' else '- CMF turning positive across 2+ timeframes (money flowing in)'}
{'- Price breaks below 1h Bollinger lower band with volume' if side == 'buy' else '- Price breaks above 1h Bollinger upper band with volume'}
- Significant profit + multiple reversal confirmations across timeframes
- Stop loss being approached with momentum clearly against position
- Strong bearish/bullish divergence on multiple timeframes

🔴 **STRONG EXIT SIGNALS (Close 75-100%):**
{'- 15m RSI dropping sharply from overbought (>70) back below 50' if side == 'buy' else '- 15m RSI rising sharply from oversold (<30) back above 50'}
- 4h trend weakening (ADX declining, was strong but now <25)
- MACD histogram consistently shrinking for multiple bars
- Substantial profit achieved + momentum showing fatigue
- Extended holding time with diminishing momentum
{'- Price struggling to break resistance despite multiple attempts' if side == 'buy' else '- Price struggling to break support despite multiple attempts'}

🟡 **PARTIAL EXIT SIGNALS (Close 25-50%):**
- Approaching take profit zone with early reversal indicators
- Price consolidating at key resistance/support levels
- Mixed signals: some timeframes bullish, others neutral/bearish
- Reasonable profit secured + uncertain near-term direction
- Risk management: preserve gains while maintaining exposure
- Time decay: long holding period without meaningful progress

✅ **HOLD SIGNALS:**
- All timeframes showing alignment with position direction
- Strong trend indicators: ADX >25 and rising
{'- DI+ clearly dominating DI- and expanding' if side == 'buy' else '- DI- clearly dominating DI+ and expanding'}
- MACD histogram expanding with strong momentum
- No reversal divergences detected on any timeframe
- CMF positive and strengthening (money flow supporting direction)
- Price respecting trend structure (higher lows for longs, lower highs for shorts)
- Profit target still has room with momentum intact

⏰ **TIME-BASED CONTEXT:**
- Short-term (<1 hour): Prioritize technical signals over time
- Medium-term (1-4 hours): Normal assessment window
- Extended (4-8 hours): Evaluate if momentum justifies continued holding
- Long-term (>8 hours): Question opportunity cost if minimal progress
- Very long (>24 hours): Seriously reconsider unless strong structural trend

💰 **PROFIT/LOSS ASSESSMENT (Relative to Volatility):**
**For Loss Scenarios:**
- **Severe Loss (multiple ATR against position):** 
  Exit immediately unless extremely strong reversal signals on multiple timeframes
  
- **Significant Loss (1-2 ATR against position):** 
  Monitor very closely, exit if momentum doesn't reverse soon
  
- **Moderate Loss (less than 1 ATR):** 
  Acceptable if technical indicators support recovery
  Stop loss should be used if breakdown continues
  
  🎯 **물타기(ADD_POSITION) 고려 상황:**
  - **현재 손실 중이지만** 다음 조건을 **모두** 만족할 때만 물타기 고려:
    ✓ 손실이 -5% ~ -15% 범위 (너무 적거나 많으면 안됨)
    ✓ **강력한 반전 신호**: 4h/1h/15m 최소 2개 타임프레임에서 반전 확인
    ✓ **추세 재개 신호**: ADX 상승, MACD 골든크로스, RSI 과매도 탈출
    ✓ **볼륨 확인**: CMF 양전환, 거래량 급증
    ✓ **핵심 지지선 테스트**: 강력한 지지선 근처에서 반등 시도
    ✓ **잔여 마진 충분**: 최소 50% 이상 잔여 마진 보유
    ✓ **포지션 확신도 높음**: confidence ≥ 0.75
  
  📊 **물타기 수량 결정 기준:**
  - **매우 높은 확신 (confidence ≥ 0.85, 승률 ≥ 75%)**: 25-30% 잔여 마진
  - **높은 확신 (confidence ≥ 0.75, 승률 ≥ 65%)**: 15-20% 잔여 마진  
  - **중간 확신 (confidence ≥ 0.65, 승률 ≥ 55%)**: 10-15% 잔여 마진
  - **낮은 확신 (그 외)**: 5-10% 잔여 마진 또는 물타기 안함
  
  ⚠️ **물타기 금지 조건:**
  - 손실이 -20% 초과 (너무 깊은 손실)
  - 손실이 -3% 미만 (너무 얕은 손실, 의미 없음)
  - 잔여 마진 50% 미만
  - 반전 신호가 1개 타임프레임에만 있는 경우
  - 추세가 여전히 반대 방향으로 강한 경우
  - ADX 하락 중이거나 25 미만
  - 이미 물타기를 2회 이상 한 포지션

**For Profit Scenarios:**
- **Minimal Profit (less than 1 ATR movement):**
  Hold unless clear reversal signals - still early in potential move
  
- **Moderate Profit (1-2 ATR movement):**
  Consider partial exit if reversal hints appear
  Full hold if momentum remains strong
  
- **Substantial Profit (2-3 ATR movement):**
  Strong candidate for partial profit-taking
  Watch for exhaustion signals
  
- **Exceptional Profit (>3 ATR movement):**
  Secure significant portion unless momentum extraordinarily strong
  Use trailing stops to protect gains

**Key Principle:** 
Don't exit profitable positions just because of arbitrary profit levels. 
Exit when TECHNICAL SIGNALS indicate momentum exhaustion or reversal,
not when hitting a percentage target. Let winners run until they show
weakness. Cut losers when technical breakdown is confirmed.

═══════════════════════════════════════════
📋 **RESPONSE REQUIREMENTS**
═══════════════════════════════════════════

**CRITICAL INSTRUCTIONS:**
1. You MUST respond with ONLY a valid JSON object
2. Do NOT include any text before or after the JSON
3. Do NOT use markdown code blocks (no ```)
4. Follow this EXACT structure:

{json_template}

**Field Requirements:**
- decision: "hold", "close", "partial_close", or "add_position" (물타기)
- percentage: 0 for hold, 100 for full close, 25-75 for partial, 5-30 for add_position (잔여 마진 %)
- reason: **MUST be technical and specific, not based on arbitrary percentages**
- exit_type: "take_profit", "stop_loss", "trend_reversal", "risk_management", "time_stop", "averaging_down", or "none"
- confidence: 0.0 to 1.0 (lower if signals are mixed across timeframes)
- urgency: "immediate", "soon", "watch", or "none"
- add_position_margin_percent: 5-30 (물타기 시 잔여 마진의 몇 % 사용할지)
- expected_win_rate: 0.0-1.0 (물타기 시 예상 승률)

**Your reason MUST include:**
1. **Timeframe Analysis:** What each timeframe (5m/1h/4h) is telling you
2. **Trend Assessment:** Is trend intact, weakening, or reversing?
3. **Momentum Evaluation:** MACD, RSI, ADX readings and their direction
4. **Volume Confirmation:** CMF showing money flow direction
5. **Volatility Context:** How current move compares to ATR baseline
6. **Key Level Analysis:** Support/resistance, Bollinger band position
7. **Leveraged PnL Context:** Current profit/loss relative to volatility
8. **Divergence Check:** Any bearish/bullish divergences detected?

**DO NOT:**
- Make decisions based solely on reaching a percentage profit target
- Exit profitable positions just because "profit is high enough"
- Ignore strong technical momentum just to "secure profits"
- Use arbitrary rules like "always exit at X%"

**DO:**
- Exit when technical indicators show momentum exhaustion
- Hold strong trends even with large profits if momentum persists
- Cut losses quickly when breakdown is technically confirmed
- Let ATR guide what's "normal" vs "extended" movement
- Prioritize multi-timeframe confirmation over single signals

Return ONLY the JSON object. Start with {{ and end with }}
"""

        # AI API 호출
        logger.info(f"포지션 모니터 시작 - {symbol} {side} (보유: {holding_hours:.1f}시간, PnL: {pnl_percent:+.2f}%)")
        
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {
                    "role": "system",
                    "content": """You are an elite crypto position manager specializing in leveraged futures trading with adaptive risk management.

CRITICAL RULES:
1. ONLY return valid JSON - no explanations, no reasoning, no markdown
2. Start your response with { and end with }
3. Follow the exact JSON schema provided
4. Be decisive but prudent - leveraged positions require careful management
5. Consider multi-timeframe analysis before making exit decisions
6. Account for leverage amplification in all profit/loss calculations

ADAPTIVE DECISION FRAMEWORK:
- Each asset has unique volatility - use ATR as baseline, not fixed percentages
- Exits should be driven by TECHNICAL SIGNALS, not arbitrary profit targets
- Let winning trades run until momentum shows exhaustion
- Cut losing trades when technical breakdown is confirmed
- Consider timeframe hierarchy: 4h trend > 1h momentum > 5m noise
- Volatility matters: 5% move in BTC ≠ 5% move in altcoin

PRIORITY OBJECTIVES:
1. Protect Capital: Exit when multiple timeframes show reversal
2. Maximize Profits: Hold while momentum and trend remain strong
3. Manage Risk: Balance profit preservation vs. opportunity cost
4. Respect Market Structure: Support/resistance, trendlines, key levels
5. Adapt to Volatility: High ATR assets need wider tolerance

DECISION PHILOSOPHY:
"Don't exit because you hit a profit target. Exit because the market 
tells you the move is over. Don't hold a loser hoping. Exit when 
technical breakdown is clear. Be patient with winners, ruthless with losers."

Your response must be a single JSON object."""
                },
                {"role": "user", "content": prompt}
            ],
            response_format={'type': 'json_object'},
            temperature=0.1,
            max_tokens=1500
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
            
            # DB에 모니터링 기록 저장 (중복 체크 추가)
            conn = get_db_connection()
            c = conn.cursor()
            timestamp = datetime.now().isoformat()
            
            # 🔒 중복 기록 방지: 최근 10초 내 동일 기록 확인
            if not is_duplicate_trade_record(conn, symbol, 'monitor', 'AI_MONITOR', time_window_seconds=10):
                c.execute("""INSERT INTO trades 
                             (timestamp, symbol, trade_type, ai_decision, action, percentage, reason, 
                              entry_price, current_price, confidence, exit_type, urgency) 
                             VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                          (timestamp, symbol, 'AI_MONITOR', result['decision'], 'monitor', result['percentage'], 
                           result['reason'], entry_price, current_price, result['confidence'], 
                           result['exit_type'], result['urgency']))
                conn.commit()
                logger.info(f"✅ AI 모니터링 기록 저장 완료: {symbol}")
            else:
                logger.info(f"⏭️  중복 기록 스킵: {symbol} AI_MONITOR")
            
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
    """
    포지션 종료 실행
    🆕 개선: 모든 유저의 포지션 종료 + TP/SL 자동 취소
    """
    try:
        position = current_positions.get(symbol)
        if not position:
            logger.warning(f"No position found for {symbol}")
            return False
        
        # 🆕 포지션 타입 확인
        position_type = position.get('position_type', 'auto')
        type_indicator = "🤖" if position_type == 'auto' else "🔧"
        
        logger.info(f"{type_indicator} {symbol} 포지션 종료 실행 중... ({position_type.upper()})")
        
        # 🆕 모든 유저에 대해 포지션 종료 실행
        success_count = 0
        failed_users = []
        
        for user_id, user_exchange in exchanges.items():
            user_name = USER_CONFIGS[user_id]['name']
            
            try:
                # 해당 유저의 포지션 확인
                positions = user_exchange.fetch_positions([symbol])
                active_position = None
                
                for pos in positions:
                    if float(pos.get('contracts', 0)) != 0:
                        active_position = pos
                        break
                
                if not active_position:
                    logger.info(f"[{user_name}] {symbol} 포지션 없음 (AI 모니터링)")
                    continue
                
                # 포지션 정보
                contracts = float(active_position['contracts'])
                side = active_position['side']
                
                # 종료할 수량 계산
                if decision['decision'] == 'close':
                    exit_amount = abs(contracts)
                elif decision['decision'] == 'partial_close':
                    exit_amount = abs(contracts) * (decision['percentage'] / 100)
                elif decision['decision'] == 'add_position':
                    # 🆕 물타기 로직: 추가 진입
                    logger.info(f"[{user_name}] 🎯 물타기 신호 감지: {symbol}")
                    
                    # 잔여 마진 확인
                    balance = user_exchange.fetch_balance()
                    free_margin = balance['USDT']['free']
                    
                    # 물타기 수량 계산
                    margin_percent = decision.get('add_position_margin_percent', 10)
                    add_position_size = free_margin * (margin_percent / 100)
                    
                    # 최소 수량 체크
                    if add_position_size < 10:
                        logger.warning(f"[{user_name}] 물타기 수량 너무 작음 (${add_position_size:.2f}) - 스킵")
                        continue
                    
                    # 현재가 조회
                    ticker = user_exchange.fetch_ticker(symbol)
                    current_price = ticker['last']
                    
                    # 추가 진입 수량 계산
                    add_amount = add_position_size / current_price
                    
                    # 시장가 주문 실행
                    add_side = 'buy' if side == 'long' else 'sell'
                    add_order = user_exchange.create_market_order(symbol, add_side, add_amount)
                    
                    logger.info(f"[{user_name}] 🎯 물타기 실행: {symbol} {add_side} {add_amount:.6f} @ ${current_price:.2f}")
                    logger.info(f"[{user_name}] 💰 투입 마진: ${add_position_size:.2f} ({margin_percent}% of free margin)")
                    
                    # Primary User의 경우 current_positions 업데이트
                    if USER_CONFIGS[user_id].get('is_primary', False):
                        # 평균 진입가 재계산
                        old_entry_price = position['entry_price']
                        old_amount = position['amount']
                        new_entry_price = (old_entry_price * old_amount + current_price * add_amount) / (old_amount + add_amount)
                        
                        current_positions[symbol]['entry_price'] = new_entry_price
                        current_positions[symbol]['amount'] += add_amount
                        
                        logger.info(f"✅ 평균 진입가 업데이트: ${old_entry_price:.2f} → ${new_entry_price:.2f}")
                        logger.info(f"✅ 총 포지션 수량: {old_amount:.6f} → {old_amount + add_amount:.6f}")
                    
                    success_count += 1
                    continue
                else:
                    continue
                
                # 포지션 청산
                close_side = 'sell' if side == 'long' else 'buy'
                close_order = user_exchange.create_market_order(symbol, close_side, exit_amount)
                
                logger.info(f"[{user_name}] {type_indicator} AI 포지션 청산: {symbol} {close_side} {exit_amount:.6f}")
                
                # 🆕 전체 종료 시 TP/SL 자동 취소
                if decision['decision'] == 'close':
                    cancelled = cancel_symbol_orders(user_exchange, symbol, user_name)
                    if cancelled > 0:
                        logger.info(f"[{user_name}] 🗑️ AI 청산으로 TP/SL 주문 {cancelled}개 자동 취소")
                
                success_count += 1
                
            except Exception as e:
                logger.error(f"[{user_name}] AI 포지션 청산 실패: {str(e)}")
                failed_users.append(user_name)
        
        # 결과 로깅
        total_users = len(exchanges)
        logger.info(f"{type_indicator} AI 청산 완료: {success_count}/{total_users}명 성공")
        if failed_users:
            logger.warning(f"⚠️ 실패한 유저: {', '.join(failed_users)}")
        
        # Primary User로 완료된 거래 DB 기록
        try:
            ticker = exchange.fetch_ticker(symbol)
            exit_price = ticker['last']
            
            if decision['decision'] == 'close':
                # 전체 종료인 경우
                record_completed_trade(symbol, position, exit_price, decision.get('exit_type', 'ai_exit'))
                logger.info(f"✅ Completed trade recorded for {symbol} ({position_type.upper()})")
                
                # 🔥 v8.5 Fixed: 포지션 진입 시간도 제거
                if symbol in position_entry_times:
                    del position_entry_times[symbol]
                    logger.info(f"🗑️ AI 청산 후 진입 시간 제거: {symbol}")
                
                del current_positions[symbol]
            else:
                # 부분 종료인 경우
                partial_position = position.copy()
                partial_position['amount'] = position['amount'] * (decision['percentage'] / 100)
                record_completed_trade(symbol, partial_position, exit_price, 'partial_' + decision.get('exit_type', 'exit'))
                logger.info(f"✅ Partial trade recorded for {symbol} ({position_type.upper()})")
                current_positions[symbol]['amount'] -= partial_position['amount']
                
        except Exception as e:
            logger.error(f"Failed to record completed trade: {e}")
            # 오류가 나도 포지션은 정리
            if decision['decision'] == 'close' and symbol in current_positions:
                # 🔥 v8.5 Fixed: 포지션 진입 시간도 제거
                if symbol in position_entry_times:
                    del position_entry_times[symbol]
                    logger.info(f"🗑️ 오류 처리 청산 후 진입 시간 제거: {symbol}")
                
                del current_positions[symbol]
            elif decision['decision'] == 'partial_close' and symbol in current_positions:
                current_positions[symbol]['amount'] -= position['amount'] * (decision['percentage'] / 100)
        
        # 텔레그램 알림
        if ENABLE_TELEGRAM:
            if decision['decision'] == 'add_position':
                # 물타기 알림
                margin_percent = decision.get('add_position_margin_percent', 10)
                expected_win_rate = decision.get('expected_win_rate', 0.0)
                
                message = f"""
🎯 <b>AI 물타기 실행 (Multi-User)</b>

<b>Type:</b> {position_type.upper()} 포지션
<b>Symbol:</b> {symbol}
<b>Decision:</b> ADD_POSITION (물타기)
<b>투입 마진:</b> {margin_percent}% of free margin
<b>예상 승률:</b> {expected_win_rate:.1%}
<b>성공:</b> {success_count}/{total_users}명
<b>Reason:</b> {decision['reason']}
<b>Confidence:</b> {decision['confidence']:.1%}

💡 손실 구간에서 강력한 반전 신호 포착
⚡ 평균 진입가가 개선되었습니다

⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
            """.strip()
                send_telegram_notification(message, 'high')
            else:
                # 기존 청산 알림
                message = f"""
{type_indicator} <b>AI Position Exit (Multi-User)</b>

<b>Type:</b> {position_type.upper()} 포지션
<b>Symbol:</b> {symbol}
<b>Decision:</b> {decision['decision'].upper()}
<b>Exit Type:</b> {decision['exit_type']}
<b>성공:</b> {success_count}/{total_users}명
<b>Reason:</b> {decision['reason']}
<b>Urgency:</b> {decision['urgency']}
<b>Confidence:</b> {decision['confidence']:.1%}

⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
            """.strip()
                send_telegram_notification(message, 'high' if decision['urgency'] == 'immediate' else 'normal')
        
        return success_count > 0
        
    except Exception as e:
        logger.error(f"Error executing position exit for {symbol}: {e}")
        return False

def ai_monitoring_cycle():
    """
    AI 모니터링 주기 실행
    🆕 개선: 자동/수동 포지션 모두 모니터링
    🔥 v8.5 Fixed: 포지션 진입 시간 추적 추가
    """
    global current_positions, initial_sync_completed, bot_start_time, existing_positions_at_start, positions_already_notified, last_position_check, position_entry_times
    
    logger.info("=== AI Position Monitoring Cycle Start ===")
    logger.info(f"⏰ Monitoring interval: {AI_MONITOR_INTERVAL} minutes")
    logger.info(f"📊 Current positions in memory: {len(current_positions)}")
    
    # 🔄 실제 거래소 포지션과 동기화 (중요!)
    sync_count = sync_positions_from_exchange()
    logger.info(f"🔄 Synchronized positions: {sync_count}")
    
    if not current_positions:
        logger.info("No positions to monitor after sync")
        return 0, []
    
    # 🆕 포지션 타입별 카운트
    auto_positions = {k: v for k, v in current_positions.items() if v.get('position_type', 'auto') == 'auto'}
    manual_positions = {k: v for k, v in current_positions.items() if v.get('position_type', 'auto') == 'manual'}
    
    logger.info(f"  - 자동(AI) 포지션: {len(auto_positions)}개")
    logger.info(f"  - 수동 포지션: {len(manual_positions)}개")
    
    monitored_count = 0
    exit_decisions = []
    
    # 🔥 v8.4: 전체 포지션을 한번에 조회 (더 안정적)
    try:
        all_positions = exchange.fetch_positions()
        active_symbols = {pos['symbol']: pos for pos in all_positions if abs(float(pos.get('contracts', 0))) > 0}
    except Exception as e:
        logger.error(f"전체 포지션 조회 오류: {e}")
        active_symbols = {}
    
    for symbol, position in current_positions.copy().items():
        # AI 모니터링이 활성화된 심볼인지 확인
        if not SYMBOL_CONFIG.get(symbol, {}).get('ai_monitoring', True):
            continue
        
        position_type = position.get('position_type', 'auto')
        type_indicator = "🤖" if position_type == 'auto' else "🔧"
        
        # 🔥 v8.4: 포지션 체크 시간 기록
        last_position_check[symbol] = datetime.now()
        
        # 🔥 v8.4: 개선된 포지션 존재 확인
        position_exists = symbol in active_symbols
        
        if not position_exists:
            # 🔥 이미 처리한 청산인지 확인
            if symbol in positions_already_notified:
                logger.info(f"⏭️ {symbol} 이미 처리된 청산 - 스킵")
                if symbol in current_positions:
                    # 🔥 v8.5 Fixed: 포지션 진입 시간도 제거
                    if symbol in position_entry_times:
                        del position_entry_times[symbol]
                        logger.info(f"🗑️ 이미 처리된 청산의 진입 시간 제거: {symbol}")
                    
                    del current_positions[symbol]
                continue
            
            # 🔥 봇 시작시 있던 포지션인지 확인
            is_existing = symbol in existing_positions_at_start
            
            # 🔥 봇 시작 후 충분한 시간이 지났는지 확인
            can_notify = False
            if bot_start_time:
                time_since_start = (datetime.now() - bot_start_time).total_seconds() / 60
                # 봇 시작 후 5분이 지났고, 기존 포지션이 아닌 경우만
                if time_since_start >= 5 and not is_existing:
                    can_notify = True
            
            logger.info(f"{type_indicator} {symbol} 포지션 청산 감지 (기존: {is_existing}, 알림: {can_notify})")
            
            # 포지션이 이미 청산됨 (TP/SL 등으로) - DB 기록 및 메모리에서 제거
            try:
                ticker = exchange.fetch_ticker(symbol)
                exit_price = ticker['last']
                
                # 포지션 종료 기록
                position_data = position.copy()
                position_data['mark_price'] = exit_price
                
                # DB 기록 및 PnL 계산
                pnl_result = record_position_closure_with_real_pnl(
                    symbol,
                    position_data,
                    close_type='auto_close_detected'
                )
                
                logger.info(f"✅ {symbol} 청산 DB 기록 완료")
                positions_already_notified.add(symbol)
                
                # 텔레그램 알림 (조건부)
                if ENABLE_TELEGRAM and can_notify and pnl_result is not None:
                    send_telegram_notification(
                        f"📊 <b>🔔 자동 청산 감지</b>\n\n"
                        f"<b>심볼:</b> {symbol}\n"
                        f"<b>종료 방식:</b> TP/SL 자동 체결\n"
                        f"<b>실현 손익:</b> ${pnl_result:,.2f} USD\n"
                        f"<b>타입:</b> {position_type.upper()}\n\n"
                        f"<b>감지 시간:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                        f"💡 바이낸스에서 자동으로 청산되었습니다.",
                        'info'
                    )
                elif not can_notify:
                    logger.info(f"⏭️ {symbol} 청산 알림 억제 (봇 시작시 기존 포지션: {is_existing})")
                    
            except Exception as record_error:
                logger.error(f"청산 기록 실패 ({symbol}): {record_error}")
            
            # 메모리에서 제거
            if symbol in current_positions:
                # 🔥 v8.5 Fixed: 포지션 진입 시간도 제거
                if symbol in position_entry_times:
                    del position_entry_times[symbol]
                    logger.info(f"🗑️ AI 청산 감지 후 진입 시간 제거: {symbol}")
                
                del current_positions[symbol]
            
            # existing_positions_at_start에서도 제거
            if symbol in existing_positions_at_start:
                existing_positions_at_start.discard(symbol)
            
            continue  # 다음 포지션으로
        
        # 포지션이 실제로 존재하는 경우에만 AI 모니터링 진행
        logger.info(f"{type_indicator} Monitoring position: {symbol} ({position_type.upper()})")
        
        try:
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
                                'position_type': position_type,  # 🆕
                                'decision': decision['decision'],
                                'reason': decision['reason']
                            })
                    else:
                        logger.info(f"{type_indicator} Exit decision for {symbol} ({position_type.upper()}) not executed due to low confidence ({decision['confidence']:.1%})")
        
        except Exception as monitor_error:
            logger.error(f"AI 모니터링 오류 ({symbol}): {monitor_error}")
            continue
        
        # API 제한을 위한 짧은 대기
        time.sleep(2)
    
    # 모니터링 결과 요약
    if monitored_count > 0:
        logger.info(f"✅ AI monitoring cycle completed: {monitored_count} positions monitored")
        if exit_decisions:
            logger.info(f"Exit decisions executed:")
            for exit_dec in exit_decisions:
                pos_type = exit_dec['position_type']
                type_emoji = "🤖" if pos_type == 'auto' else "🔧"
                logger.info(f"  {type_emoji} {exit_dec['symbol']} ({pos_type.upper()}): {exit_dec['decision']} - {exit_dec['reason']}")
    else:
        logger.info("No positions monitored (all disabled or no active positions)")
    
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
                    logger.debug("No positions to monitor")
                
                # 다음 모니터링까지 대기
                time.sleep(AI_MONITOR_INTERVAL * 60)
                
            except Exception as e:
                logger.error(f"Error in AI monitoring loop: {e}", exc_info=True)
                time.sleep(60)  # 오류 발생 시 1분 대기
    
    if not ai_monitor_running:
        ai_monitor_thread = threading.Thread(target=monitor_loop, daemon=True)
        ai_monitor_thread.start()
        logger.info(f"✅ AI position monitoring started ({AI_MONITOR_INTERVAL}-minute intervals)")
        logger.info(f"   🤖 자동 포지션 및 🔧 수동 포지션 모두 모니터링됩니다")

def stop_ai_monitoring():
    """AI 모니터링 중지"""
    global ai_monitor_running
    ai_monitor_running = False
    logger.info("AI position monitoring stopped")

# ============ AI Decision Making (개선 버전) ============
def ai_validate_signal(symbol, action, market_data, recent_trades_df, message_data=None):
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
        df_15min = market_data['df_15min']
        df_hourly = market_data['df_hourly'] 
        df_4h = market_data['df_4h']
        
        # ATR 값 안전하게 추출 (동일한 헬퍼 함수 사용)
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

        # 🆕 과매수/과매도 체크 (buy/sell 액션일 때만)
        overbought_oversold_risk = None
        reverse_entry_condition = ""  # 🆕 반대 진입 조건 설명
        if action in ['buy', 'sell']:
            overbought_oversold_risk = check_overbought_oversold_multi_timeframe(
                df_15min, df_hourly, df_4h, action
            )
            
            # 🆕 반대 진입 기회 감지
            if overbought_oversold_risk.get('reverse_opportunity', False):
                reverse_entry_condition = f"""
🔄 **REVERSE ENTRY OPPORTUNITY DETECTED:**
- Current signal: {action.upper()}
- Market condition: EXTREME {'OVERBOUGHT' if action == 'buy' else 'OVERSOLD'}
- Reverse signals detected: {', '.join(overbought_oversold_risk.get('reverse_signals', []))}
- Risk level: {overbought_oversold_risk['risk_level'].upper()}

**REVERSE ENTRY CRITERIA (Must meet ALL):**
1. At least 3 extreme signals present: {'✅' if len(overbought_oversold_risk.get('reverse_signals', [])) >= 3 else '❌'} ({len(overbought_oversold_risk.get('reverse_signals', []))}/3)
2. Multiple timeframe confirmation of extreme conditions
3. Clear divergence or reversal patterns forming
4. Volume supporting potential reversal

**If conditions met, you should:**
- Set decision to "reverse"
- Set modified_action to opposite of original signal ({'sell' if action == 'buy' else 'buy'})
- Use conservative position size (30-50%)
- Set tight stop loss due to counter-trend nature
"""
                logger.warning(f"🔄 반대 진입 기회 감지 - {symbol} {action}")
                logger.warning(f"   극단 신호: {', '.join(overbought_oversold_risk.get('reverse_signals', []))}")
            
            # 리스크가 high이면서 반대 진입 기회가 없으면 거부
            elif overbought_oversold_risk['is_risky'] and overbought_oversold_risk['risk_level'] == 'high' and not overbought_oversold_risk.get('reverse_opportunity', False):
                logger.warning(f"❌ 과매수/과매도 리스크 HIGH - 진입 거부")
                logger.warning(f"   경고: {', '.join(overbought_oversold_risk['warnings'])}")
                
                return create_default_reject_decision(
                    f"과매수/과매도 리스크 HIGH (점수: {overbought_oversold_risk['total_risk_score']}). "
                    f"경고: {', '.join(overbought_oversold_risk['warnings'][:2])}"
                )
            
            # 리스크가 medium이면 경고 로그
            elif overbought_oversold_risk['is_risky']:
                logger.warning(f"⚠️ 과매수/과매도 리스크 MEDIUM 감지 (점수: {overbought_oversold_risk['total_risk_score']})")
                for warning in overbought_oversold_risk['warnings']:
                    logger.warning(f"   - {warning}")

        # close_position 액션 처리 (별도 로직)
        if action in ['close', 'close_position']:
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
            
            json_template = """
{
    "decision": "approve",
    "reason": "Favorable exit conditions confirmed",
    "confidence": 0.75,
    "urgency": "immediate"
}"""

            prompt = f"""
You are an expert crypto trading AI validator. Analyze whether to approve closing the position for {symbol}.

**ACCOUNT & TRADING CONFIGURATION (REFERENCE ONLY - DO NOT VALIDATE):**
- Leverage: {leverage}x
- Position Size Target: {position_size_percent}% of total balance
- Total Balance: ${total_margin:,.2f} USDT
- Free Balance: ${free_margin:,.2f} USDT
- Used Margin: ${used_margin:,.2f} USDT
- Available for New Positions: ${free_margin:,.2f} USDT

Note: These are fixed trading parameters for your reference. Your job is to validate the exit signal, not these settings.

**CURRENT MARKET CONDITIONS:**
- Symbol: {symbol}
- Current Price: ${market_data['current_price']:.2f} USDT
- Action: Close Position
{message_str}

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

**CRITICAL: USE THE REFLECTION ABOVE**
The reflection contains insights from recent trading performance including:
- Win rate trends and patterns
- Successful strategies and common mistakes
- Risk management issues
- Entry/exit timing effectiveness

Apply these insights when validating this exit signal. If the reflection indicates problems with premature exits or timing issues, factor that into your decision.

**ENHANCED EXIT VALIDATION:**

⚠️ **APPROVE EXIT IF:**
- Strong reversal signals across multiple timeframes
- Momentum exhaustion (RSI extremes + divergence)
- Trend weakening (ADX declining, DI crossover)
- Volume flow reversing (CMF changing direction)
- Profit target reached with reversal confirmation

❌ **REJECT EXIT IF:**
- Trend still strong on higher timeframes
- No reversal confirmation
- Premature exit (small profit, trend intact)
- Temporary pullback in strong trend

**VALIDATION CRITERIA:**
Consider if this is a good time to close the position based on:
- Multi-timeframe trend alignment or divergence
- Momentum exhaustion vs healthy correction
- Volume flow changes across timeframes
- Risk management vs opportunity cost

**CRITICAL INSTRUCTIONS:**
1. You MUST respond with ONLY a valid JSON object
2. Do NOT include any text before or after the JSON
3. Do NOT use markdown code blocks (no ```)
4. Follow this EXACT structure:

{json_template}

**Field Requirements:**
- decision: must be "approve" or "reject"
- reason: string explaining WITH SPECIFIC TIMEFRAME ANALYSIS
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
                
                # 거래 기록 저장 (중복 체크 추가)
                conn = get_db_connection()
                c = conn.cursor()
                timestamp = datetime.now().isoformat()
                
                # 🔒 중복 기록 방지: 최근 10초 내 동일 기록 확인
                if not is_duplicate_trade_record(conn, symbol, 'close_position', 'AI_VALIDATION', time_window_seconds=10):
                    c.execute("""INSERT INTO trades 
                                 (timestamp, symbol, trade_type, ai_decision, action, reason, 
                                  current_price, confidence) 
                                 VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                              (timestamp, symbol, 'AI_VALIDATION', result['decision'], 'close_position', 
                               result['reason'], market_data['current_price'], result['confidence']))
                    conn.commit()
                    logger.info(f"✅ 청산 검증 기록 저장 완료: {symbol}")
                else:
                    logger.info(f"⏭️  중복 기록 스킵: {symbol} close_position AI_VALIDATION")
                
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

        # message_data 문자열 변환
        message_str = ""
        if message_data:
            if isinstance(message_data, dict):
                message_str = f"\n**ADDITIONAL SIGNAL DATA:**\n{json.dumps(message_data, ensure_ascii=False, indent=2)}\n"
            else:
                message_str = f"\n**ADDITIONAL SIGNAL DATA:**\n{str(message_data)}\n"
        
        # 프롬프트 구성
        prompt = f"""
You are an elite crypto trading AI validator specializing in multi-timeframe technical analysis. Your mission is to identify profitable trading opportunities while managing risk through appropriate position sizing, leverage, and stop-loss/take-profit levels.

**ACCOUNT & TRADING CONFIGURATION (REFERENCE ONLY):**
- Leverage: {leverage}x
- Position Size Target: {position_size_percent}% of total balance per trade
- Total Balance: ${total_margin:,.2f} USDT
- Free Balance: ${free_margin:,.2f} USDT
- Used Margin: ${used_margin:,.2f} USDT
- Available for New Positions: ${free_margin:,.2f} USDT
- Max Position Size (based on config): ${total_margin * (position_size_percent / 100):,.2f} USDT

Note: Risk is managed through position size ({position_size_percent}%), leverage ({leverage}x), and SL/TP settings. These parameters provide safety even in moderate market conditions.

**SIGNAL TO VALIDATE:**
- Symbol: {symbol}
- Proposed Action: {action.upper()}
- Current Price: ${market_data['current_price']:.2f} USDT
{message_str}

**MULTI-TIMEFRAME TECHNICAL ANALYSIS:**

═══════════════════════════════════════════
📊 **15-MINUTE CHART (Short-term Momentum)**
═══════════════════════════════════════════
→ Momentum Indicators:
  • RSI(14): {df_15min['rsi'].iloc[-1]:.2f} {'[OVERBOUGHT]' if df_15min['rsi'].iloc[-1] > 70 else '[OVERSOLD]' if df_15min['rsi'].iloc[-1] < 30 else '[NEUTRAL]'}
  • Stochastic %K: {df_15min['stoch_k'].iloc[-1]:.2f}, %D: {df_15min['stoch_d'].iloc[-1]:.2f}
  • Williams %R: {df_15min['williams_r'].iloc[-1]:.2f}
  • PPO: {df_15min['ppo'].iloc[-1]:.2f}

→ Trend Indicators:
  • MACD: {df_15min['macd'].iloc[-1]:.2f} (Signal: {df_15min['macd_signal'].iloc[-1]:.2f}, Diff: {df_15min['macd_diff'].iloc[-1]:.2f})
  • ADX: {df_15min['adx'].iloc[-1]:.2f} {'[STRONG TREND]' if df_15min['adx'].iloc[-1] > 25 else '[WEAK TREND]'}
  • DI+: {df_15min['di_plus'].iloc[-1]:.2f} vs DI-: {df_15min['di_minus'].iloc[-1]:.2f}

→ Volatility & Support/Resistance:
  • Bollinger Bands:
    * Upper: ${df_15min['bb_bbh'].iloc[-1]:.2f}
    * Middle: ${df_15min['bb_bbm'].iloc[-1]:.2f}
    * Lower: ${df_15min['bb_bbl'].iloc[-1]:.2f}
    * Current Position: {'Near Upper' if market_data['current_price'] > df_15min['bb_bbm'].iloc[-1] else 'Near Lower'}
  • ATR(14): {atr_15min:.4f}

→ Volume Flow:
  • CMF(20): {df_15min['cmf'].iloc[-1]:.2f} {'[BUYING PRESSURE]' if df_15min['cmf'].iloc[-1] > 0 else '[SELLING PRESSURE]'}

═══════════════════════════════════════════
📈 **1-HOUR CHART (Medium-term Trend)**
═══════════════════════════════════════════
→ Momentum Indicators:
  • RSI(14): {df_hourly['rsi'].iloc[-1]:.2f} {'[OVERBOUGHT]' if df_hourly['rsi'].iloc[-1] > 70 else '[OVERSOLD]' if df_hourly['rsi'].iloc[-1] < 30 else '[NEUTRAL]'}

→ Trend Indicators:
  • MACD: {df_hourly['macd'].iloc[-1]:.2f} (Signal: {df_hourly['macd_signal'].iloc[-1]:.2f})
  • ADX: {df_hourly['adx'].iloc[-1]:.2f} {'[STRONG TREND]' if df_hourly['adx'].iloc[-1] > 25 else '[WEAK TREND]'}
  • DI+: {df_hourly['di_plus'].iloc[-1]:.2f} vs DI-: {df_hourly['di_minus'].iloc[-1]:.2f}

→ Volatility:
  • Bollinger Middle: ${df_hourly['bb_bbm'].iloc[-1]:.2f}
  • ATR(14): {atr_hourly:.4f}

→ Volume Flow:
  • CMF(20): {df_hourly['cmf'].iloc[-1]:.2f} {'[BUYING PRESSURE]' if df_hourly['cmf'].iloc[-1] > 0 else '[SELLING PRESSURE]'}

═══════════════════════════════════════════
📊 **4-HOUR CHART (Long-term Direction)**
═══════════════════════════════════════════
→ Momentum Indicators:
  • RSI(14): {df_4h['rsi'].iloc[-1]:.2f} {'[OVERBOUGHT]' if df_4h['rsi'].iloc[-1] > 70 else '[OVERSOLD]' if df_4h['rsi'].iloc[-1] < 30 else '[NEUTRAL]'}

→ Trend Indicators:
  • MACD: {df_4h['macd'].iloc[-1]:.2f} (Signal: {df_4h['macd_signal'].iloc[-1]:.2f})
  • ADX: {df_4h['adx'].iloc[-1]:.2f} {'[STRONG TREND]' if df_4h['adx'].iloc[-1] > 25 else '[WEAK TREND]'}
  • DI+: {df_4h['di_plus'].iloc[-1]:.2f} vs DI-: {df_4h['di_minus'].iloc[-1]:.2f}

→ Volume Flow:
  • CMF(20): {df_4h['cmf'].iloc[-1]:.2f} {'[BUYING PRESSURE]' if df_4h['cmf'].iloc[-1] > 0 else '[SELLING PRESSURE]'}

═══════════════════════════════════════════
{('🎭 **MARKET SENTIMENT:** Fear & Greed Index = ' + str(market_data["fear_greed_index"]["value"]) + ' (' + market_data["fear_greed_index"]["value_classification"] + ')') if market_data.get("fear_greed_index") else ''}

**RECENT PERFORMANCE REFLECTION:**
{reflection if reflection else 'No previous trading data available'}

**CRITICAL: APPLY INSIGHTS FROM REFLECTION**
The reflection above provides:
- Historical win rate and performance trends
- Identified strengths and weaknesses in trading strategy
- Specific patterns that lead to success or failure
- Risk management insights from past trades
- Actionable recommendations for entry/exit timing

Use these insights to validate the current signal. If the reflection indicates that similar signals have failed, be more conservative. If certain patterns have succeeded, increase confidence accordingly.

**🔄 BALANCED VALIDATION FRAMEWORK (v2.0):**

⚠️ **HIGH RISK - STRONG REJECTION CONDITIONS:**

For BUY Signals (Reject only if MULTIPLE conditions are true):
1. **Extreme Overbought Combination:**
   - 15m RSI > 85 AND 1h RSI > 75 AND 4h RSI > 70 → Severely overextended
   - Price > 1h Bollinger Upper + 2*ATR → Extreme deviation

2. **Clear Reversal Signals:**
   - Strong bearish divergence on multiple timeframes
   - DI- strongly crossing above DI+ on BOTH 1h and 4h
   - CMF strongly negative on ALL timeframes with increasing magnitude

3. **No Trend Support:**
   - 4h ADX < 15 AND declining → Very weak/no trend
   - All timeframes showing opposite signals → Complete misalignment

For SELL Signals (Reject only if MULTIPLE conditions are true):
1. **Extreme Oversold Combination:**
   - 15m RSI < 15 AND 1h RSI < 25 AND 4h RSI < 30 → Severely oversold
   - Price < 1h Bollinger Lower - 2*ATR → Extreme deviation

2. **Clear Reversal Signals:**
   - Strong bullish divergence on multiple timeframes
   - DI+ strongly crossing above DI- on BOTH 1h and 4h
   - CMF strongly positive on ALL timeframes with increasing magnitude

3. **No Trend Support:**
   - 4h ADX < 15 AND declining → Very weak/no trend
   - All timeframes showing opposite signals → Complete misalignment

✅ **FLEXIBLE APPROVAL CRITERIA - WEIGHTED SCORING:**

For BUY Signals (Approve if score ≥ 60%):
**Primary Factors (Higher Timeframe Focus):**
- 4h trend direction: DI+ > DI- → Uptrend confirmed (+25 points) [중장기 가중치 상향]
- 1h momentum not extreme: RSI 25-80 → Room to move (+25 points) [중기 가중치 상향]
- Price action favorable: Above key MA or bounce from support (+15 points)

**Secondary Factors (10 points each):**
- 115m entry timing good: Not at immediate resistance (+10)
- CMF positive on 2+ timeframes → Money flowing in (+10)
- ADX > 18 on 1h or 4h timeframe → Trend strength (+12 if 4h, +10 if 1h) [중장기 보너스]
- No strong divergences visible (+10)

**Bonus Factors (5 points each):**
- 4h MACD bullish alignment (+7) [중장기 보너스]
- 1h volume increasing (+6) [중기 보너스]
- Market sentiment supportive (+5)
- Breaking key level with conviction (+5)
- Retesting previous resistance as support (+5)

For SELL Signals (Approve if score ≥ 60%):
**Primary Factors (Higher Timeframe Focus):**
- 4h trend direction: DI- > DI+ → Downtrend confirmed (+25 points) [중장기 가중치 상향]
- 1h momentum not extreme: RSI 20-75 → Room to move (+25 points) [중기 가중치 상향]
- Price action favorable: Below key MA or rejection from resistance (+15 points)

**Secondary Factors (10 points each):**
- 115m entry timing good: Not at immediate support (+10)
- CMF negative on 2+ timeframes → Money flowing out (+10)
- ADX > 18 on 1h or 4h timeframe → Trend strength (+12 if 4h, +10 if 1h) [중장기 보너스]
- No strong divergences visible (+10)

**Bonus Factors (5 points each):**
- 4h MACD bearish alignment (+7) [중장기 보너스]
- 1h volume increasing (+6) [중기 보너스]
- Market sentiment supportive (+5)
- Breaking key level with conviction (+5)
- Retesting previous support as resistance (+5)

🎯 **RISK-ADJUSTED DECISION MAKING:**

**Position Size Recommendations Based on Confidence:**
- High Confidence (80-100 points): Use full position size
- Good Confidence (70-79 points): Use 75% position size
- Moderate Confidence (60-69 points): Use 50% position size
- Low Confidence (below 60): Reject or suggest waiting

**Dynamic Stop Loss & Take Profit:**
- Use ATR-based stops: 1.5-2.5x ATR from entry
- Risk-reward ratio flexible: 1.0-3.0 based on market structure
- Consider support/resistance levels over fixed percentages
- Tighter stops for lower confidence trades

**DECISION FRAMEWORK:**
1. **APPROVE:** Score ≥ 60%, acceptable risk/reward
2. **REJECT:** High risk conditions met OR score < 50%
3. **MODIFY:** Score 50-59%, suggest reduced position or wait

**IMPORTANT MINDSET SHIFT:**
- We're not looking for perfect setups, but favorable risk/reward opportunities
- Risk is managed through position sizing, stops, and leverage - not just entry selection
- A 60% win rate with proper risk management is profitable
- Focus on catching moves early rather than waiting for perfect confirmation
- Accept that some trades will lose - that's why we use risk management

**CRITICAL INSTRUCTIONS:**
1. You MUST respond with ONLY a valid JSON object
2. Do NOT include any text before or after the JSON
3. Do NOT use markdown code blocks (no ```)
4. Calculate your confidence score based on the criteria above
5. Be more open to opportunities while respecting clear danger signals

{json_template}

**Field Requirements:**
- decision: must be "approve", "reject", or "modify"
- modified_action: must be "buy", "sell", or "hold"
- percentage: integer between 10 and 100 (adjust based on confidence score)
- reason: string explaining the decision with SCORE CALCULATION
- stop_loss_price: number (use ATR-based calculation)
- take_profit_price: number (aim for 1.5-2.5 risk/reward)
- pl_ratio: number between 1.0 and 5.0
- confidence: number between 0.0 and 1.0 (score/100)

Your reason MUST include:
- Calculated score breakdown (which factors earned points)
- Key supporting and opposing factors
- Why risk/reward is acceptable given position sizing
- Specific entry quality assessment

Return ONLY the JSON object. Start with {{ and end with }}
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
            
            # 거래 기록 저장 (중복 체크 추가)
            conn = get_db_connection()
            c = conn.cursor()
            timestamp = datetime.now().isoformat()
            
            # 🔒 중복 기록 방지: 최근 10초 내 동일 기록 확인
            if not is_duplicate_trade_record(conn, symbol, action, 'AI_VALIDATION', time_window_seconds=10):
                c.execute("""INSERT INTO trades 
                             (timestamp, symbol, trade_type, ai_decision, action, percentage, reason, 
                              current_price, stop_loss, take_profit, pl_ratio, confidence, reflection) 
                             VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                          (timestamp, symbol, 'AI_VALIDATION', result['decision'], action, result['percentage'], 
                           result['reason'], market_data['current_price'], result['stop_loss_price'], 
                           result['take_profit_price'], result['pl_ratio'], result['confidence'], reflection))
                conn.commit()
                logger.info(f"✅ {action.upper()} 신호 검증 기록 저장 완료: {symbol} (Reflection 포함)")
            else:
                logger.info(f"⏭️  중복 기록 스킵: {symbol} {action} AI_VALIDATION")
            
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
2. Take Profit: 3.0-4.0% from entry
3. Stop Loss: 0.8-2.0% from entry  
4. Leverage: 5-10x maximum
5. Balance risk management with profit potential

Generate emergency trading parameters. Respond with JSON only:
{{
  "percentage": 20,
  "stop_loss_price": 0.0,
  "take_profit_price": 0.0,
  "leverage": 10,
  "reason": "Emergency parameters with moderate risk management",
  "confidence": 0.0-1.0
}}"""

        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": "You are an emergency risk management AI. Generate moderate conservative trading parameters."},
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
    """포지션 크기 계산 - 개선된 버전 (마진 부족 방지)"""
    try:
        config = SYMBOL_CONFIG.get(symbol, {})
        
        # 전체 잔고 정보 가져오기 
        balance_info = exchange.fetch_balance()
        total_balance = balance_info['USDT']['total']
        free_balance = balance_info['USDT']['free']
        used_balance = balance_info['USDT']['used']
        
        logger.info(f"💰 잔고 상태 확인:")
        logger.info(f"  - Total Balance: ${total_balance:,.2f}")
        logger.info(f"  - Free Balance: ${free_balance:,.2f}")
        logger.info(f"  - Used Balance: ${used_balance:,.2f}")
        
        # 안전 마진 버퍼 적용 (Free Balance의 90%만 사용)
        SAFETY_BUFFER = 0.90
        safe_free_balance = free_balance * SAFETY_BUFFER
        
        # 심볼별 포지션 크기 비율 설정
        position_size_percent = config.get('position_size_percent', DEFAULT_POSITION_SIZE_PERCENT)
        
        # 설정 비율에 따른 최대 포지션 크기 (Total Balance 기준)
        max_position_from_config = total_balance * (position_size_percent / 100)
        
        # 실제 사용 가능한 포지션 크기 (Free Balance 기준)
        available_position_size = safe_free_balance
        
        # 둘 중 작은 값 선택
        position_size = min(max_position_from_config, available_position_size)
        
        # 최소/최대 포지션 크기 제한 적용
        min_size = config.get('min_position_size', 10)
        max_size = config.get('max_position_size', 100000)
        
        if position_size < min_size:
            logger.warning(f"⚠️ 계산된 포지션 크기 ${position_size:,.2f}가 최소값 ${min_size}보다 작음")
            position_size = min_size if safe_free_balance >= min_size else 0
            
        if position_size > max_size:
            logger.info(f"📊 포지션 크기를 최대값 ${max_size:,.2f}로 제한")
            position_size = max_size
        
        # 레버리지 고려
        leverage = config.get('leverage', 10)
        required_margin = position_size / leverage
        
        # 마진 충분성 최종 확인
        if required_margin > safe_free_balance:
            logger.warning(f"⚠️ 마진 부족 - 필요: ${required_margin:,.2f}, 사용가능: ${safe_free_balance:,.2f}")
            # 사용 가능한 마진에 맞춰 포지션 크기 자동 조정
            position_size = safe_free_balance * leverage
            required_margin = safe_free_balance
            logger.info(f"✅ 포지션 크기를 ${position_size:,.2f}로 자동 조정")
        
        logger.info(f"📊 포지션 크기 계산 완료:")
        logger.info(f"  - 포지션 크기: ${position_size:,.2f}")
        logger.info(f"  - 필요 마진: ${required_margin:,.2f}")
        logger.info(f"  - 레버리지: {leverage}x")
        logger.info(f"  - 사용 비율: {position_size_percent}%")
        
        return position_size, position_size_percent
        
    except Exception as e:
        logger.error(f"❌ 포지션 크기 계산 오류: {str(e)}")
        # 오류 시 기존 방식으로 fallback
        config = SYMBOL_CONFIG.get(symbol, {})
        position_size_percent = config.get('position_size_percent', DEFAULT_POSITION_SIZE_PERCENT)
        position_size = balance * (position_size_percent / 100)
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



def validate_and_adjust_prices(user_exchange, symbol, current_price, stop_loss_price, take_profit_price, action):
    """
    TP/SL 가격 검증 및 조정
    - 심볼별 tickSize 확인
    - 현재가와의 최소 거리 확인
    - 가격 정밀도 조정
    """
    try:
        # 마켓 정보 가져오기
        market = user_exchange.market(symbol)
        
        # 가격 정밀도(precision)
        price_precision = market.get('precision', {}).get('price', 8)
        
        # tickSize (최소 가격 변동폭)
        tick_size = None
        if 'filters' in market.get('info', {}):
            for filter_item in market['info']['filters']:
                if filter_item.get('filterType') == 'PRICE_FILTER':
                    tick_size = float(filter_item.get('tickSize', 0.01))
                    break
        
        if not tick_size:
            tick_size = 10 ** (-price_precision)
        
        # 가격을 tickSize에 맞게 조정
        def round_to_tick(price, tick):
            return round(price / tick) * tick
        
        # SL/TP 조정
        adjusted_sl = round_to_tick(stop_loss_price, tick_size)
        adjusted_tp = round_to_tick(take_profit_price, tick_size)
        
        # 최소 거리 검증 (0.1% 이상)
        min_distance_percent = 0.001  # 0.1%
        
        if action == 'buy':
            # 롱 포지션: SL < 현재가 < TP
            min_sl = current_price * (1 - min_distance_percent)
            min_tp = current_price * (1 + min_distance_percent)
            
            if adjusted_sl > min_sl:
                adjusted_sl = round_to_tick(min_sl, tick_size)
                logger.warning(f"⚠️ SL이 현재가와 너무 가까워 조정: ${stop_loss_price:.4f} -> ${adjusted_sl:.4f}")
            
            if adjusted_tp < min_tp:
                adjusted_tp = round_to_tick(min_tp, tick_size)
                logger.warning(f"⚠️ TP가 현재가와 너무 가까워 조정: ${take_profit_price:.4f} -> ${adjusted_tp:.4f}")
        else:
            # 숏 포지션: TP < 현재가 < SL
            max_sl = current_price * (1 + min_distance_percent)
            max_tp = current_price * (1 - min_distance_percent)
            
            if adjusted_sl < max_sl:
                adjusted_sl = round_to_tick(max_sl, tick_size)
                logger.warning(f"⚠️ SL이 현재가와 너무 가까워 조정: ${stop_loss_price:.4f} -> ${adjusted_sl:.4f}")
            
            if adjusted_tp > max_tp:
                adjusted_tp = round_to_tick(max_tp, tick_size)
                logger.warning(f"⚠️ TP가 현재가와 너무 가까워 조정: ${take_profit_price:.4f} -> ${adjusted_tp:.4f}")
        
        return {
            'sl': adjusted_sl,
            'tp': adjusted_tp,
            'tick_size': tick_size,
            'price_precision': price_precision
        }
        
    except Exception as e:
        logger.error(f"가격 검증 오류: {str(e)}")
        return {
            'sl': stop_loss_price,
            'tp': take_profit_price,
            'tick_size': 0.01,
            'price_precision': 2
        }


def execute_trade_for_all_users(symbol, action, amount_primary, stop_loss_price, take_profit_price, 
                                trailing_stop, trailing_activation):
    """모든 활성 유저에 대해 거래 실행"""
    success_count = 0
    failed_users = []
    primary_orders = None
    
    for user_id, user_exchange in exchanges.items():
        user_name = USER_CONFIGS[user_id]['name']
        is_primary = USER_CONFIGS[user_id]['is_primary']
        
        try:
            logger.info(f"[{user_name}] 거래 실행 시작: {symbol} {action}")
            
            # 레버리지 설정
            try:
                leverage = SYMBOL_CONFIG[symbol].get('leverage', 10)
                user_exchange.set_leverage(leverage, symbol)
                logger.info(f"[{user_name}] 레버리지 설정: {leverage}x")
            except Exception as e:
                logger.warning(f"[{user_name}] 레버리지 설정 실패: {str(e)}")
            
            # 각 유저의 잔고에 맞게 수량 재계산
            balance_info = user_exchange.fetch_balance()
            usdt_balance = balance_info['USDT']['free']
            position_percent = SYMBOL_CONFIG[symbol].get('position_size_percent', 30)
            position_size = usdt_balance * (position_percent / 100)
            
            ticker = user_exchange.fetch_ticker(symbol)
            current_price = ticker['last']
            leverage = SYMBOL_CONFIG[symbol].get('leverage', 10)
            amount = (position_size * leverage) / current_price
            
            logger.info(f"[{user_name}] 포지션 크기: ${position_size:.2f} (잔고: ${usdt_balance:.2f})")
            logger.info(f"[{user_name}] 수량: {amount:.6f}")
            
            # 주문 실행 (원본 함수 활용 - exchange를 user_exchange로 치환)
            # 메인 주문
            order_side = action
            main_order = user_exchange.create_market_order(symbol, order_side, amount)
            actual_entry = float(main_order['average']) if main_order.get('average') else current_price
            logger.info(f"[{user_name}] ✅ 메인 주문 체결: {symbol} {order_side} {amount:.6f} @ ${actual_entry:.4f}")

            # 🆕 가격 검증 및 조정
            price_check = validate_and_adjust_prices(
                user_exchange, symbol, current_price, 
                stop_loss_price, take_profit_price, action
            )
            adjusted_sl = price_check['sl']
            adjusted_tp = price_check['tp']
            
            # 🔄 현재 포지션의 전체 크기 조회 (여러 번 진입한 경우 대비)
            try:
                positions = user_exchange.fetch_positions([symbol])
                total_position_amount = 0
                for pos in positions:
                    if float(pos.get('contracts', 0)) != 0:
                        total_position_amount = abs(float(pos.get('contracts', 0)))
                        break
                
                # 포지션이 없으면 진입 예정 수량 사용
                if total_position_amount == 0:
                    total_position_amount = amount
                    
                logger.info(f"[{user_name}] 현재 포지션 크기: {total_position_amount:.6f} (TP/SL에 사용)")
            except Exception as e:
                logger.warning(f"[{user_name}] 포지션 조회 실패, 진입 수량 사용: {str(e)}")
                total_position_amount = amount
            
            # Stop Loss 주문 (closePosition=True로 전체 청산)
            sl_order = None
            try:
                sl_side = 'sell' if action == 'buy' else 'buy'
                sl_params = {
                    'stopPrice': adjusted_sl,
                    'workingType': 'MARK_PRICE',
                    'closePosition': True,  # 🆕 전체 포지션 청산
                }
                sl_order = user_exchange.create_order(
                    symbol=symbol,
                    type='STOP_MARKET',
                    side=sl_side,
                    amount=total_position_amount,  # 🆕 전체 포지션 크기 사용
                    params=sl_params
                )
                logger.info(f"[{user_name}] 🛡️ Stop Loss 설정 완료: ${adjusted_sl:.4f} (전체 포지션 청산: {total_position_amount:.6f})")
            except Exception as e:
                logger.error(f"[{user_name}] Stop Loss 설정 실패: {str(e)}")
                logger.error(f"[{user_name}] 실패 상세 - SL가격: ${adjusted_sl:.4f}, 현재가: ${current_price:.4f}, 수량: {total_position_amount:.6f}")
            
            # Take Profit 주문 (closePosition=True로 전체 청산)
            tp_order = None
            try:
                tp_side = 'sell' if action == 'buy' else 'buy'
                tp_params = {
                    'stopPrice': adjusted_tp,
                    'workingType': 'MARK_PRICE',
                    'closePosition': True,  # 🆕 전체 포지션 청산
                }
                tp_order = user_exchange.create_order(
                    symbol=symbol,
                    type='TAKE_PROFIT_MARKET',
                    side=tp_side,
                    amount=total_position_amount,  # 🆕 전체 포지션 크기 사용
                    params=tp_params
                )
                logger.info(f"[{user_name}] 🎯 Take Profit 설정 완료: ${adjusted_tp:.4f} (전체 포지션 청산: {total_position_amount:.6f})")
            except Exception as e:
                logger.error(f"[{user_name}] Take Profit 설정 실패: {str(e)}")
                logger.error(f"[{user_name}] 실패 상세 - TP가격: ${adjusted_tp:.4f}, 현재가: ${current_price:.4f}, 수량: {total_position_amount:.6f}")
            
            success_count += 1
            
            # Primary User의 주문 정보 저장 (반환용)
            if is_primary:
                primary_orders = {
                    'main': main_order,
                    'actual_entry': actual_entry,
                    'adjusted_amount': amount,
                    'sl': sl_order if 'sl_order' in locals() else None,
                    'tp': tp_order if 'tp_order' in locals() else None
                }
            
        except Exception as e:
            logger.error(f"[{user_name}] 거래 실행 실패: {str(e)}")
            failed_users.append(user_name)
    
    # 결과 로깅
    total_users = len(exchanges)
    logger.info(f"✅ 거래 실행 완료: {success_count}/{total_users}명 성공")
    if failed_users:
        logger.warning(f"⚠️ 실패한 유저: {', '.join(failed_users)}")
    
    # Primary User의 주문 정보와 멀티유저 통계 반환
    if primary_orders:
        primary_orders['success_count'] = success_count
        primary_orders['total_users'] = total_users
    
    return primary_orders

def close_position_for_all_users(symbol):
    """모든 활성 유저의 포지션 청산 및 TP/SL 자동 취소"""
    success_count = 0
    failed_users = []
    
    for user_id, user_exchange in exchanges.items():
        user_name = USER_CONFIGS[user_id]['name']
        
        try:
            # 포지션 확인
            positions = user_exchange.fetch_positions([symbol])
            active_position = None
            
            for pos in positions:
                if float(pos.get('contracts', 0)) != 0:
                    active_position = pos
                    break
            
            if not active_position:
                logger.info(f"[{user_name}] {symbol} 포지션 없음")
                continue
            
            # 포지션 청산
            contracts = float(active_position['contracts'])
            side = 'sell' if active_position['side'] == 'long' else 'buy'
            
            close_order = user_exchange.create_market_order(symbol, side, abs(contracts))
            logger.info(f"[{user_name}] ✅ 포지션 청산: {symbol} {side} {abs(contracts):.6f}")
            
            # 🆕 TP/SL 자동 취소
            cancelled = cancel_symbol_orders(user_exchange, symbol, user_name)
            if cancelled > 0:
                logger.info(f"[{user_name}] 🗑️ TP/SL 주문 {cancelled}개 자동 취소")
            
            success_count += 1
            
        except Exception as e:
            logger.error(f"[{user_name}] 포지션 청산 실패: {str(e)}")
            failed_users.append(user_name)
    
    # 결과 로깅
    total_users = len(exchanges)
    logger.info(f"✅ 청산 완료: {success_count}/{total_users}명 성공")
    if failed_users:
        logger.warning(f"⚠️ 실패한 유저: {', '.join(failed_users)}")
    
    return success_count, total_users


def place_orders_with_sl_tp(symbol, action, amount, stop_loss_price, take_profit_price, 
                            trailing_stop_percent=None, trailing_activation_percent=None):
    """스탑로스와 테이크프로핏이 포함된 주문 실행 - 마진 부족 방지 버전"""
    try:
        # 마진 충분성 사전 확인
        balance_info = exchange.fetch_balance()
        free_balance = balance_info['USDT']['free']
        
        # 현재 시장가 조회
        ticker = exchange.fetch_ticker(symbol)
        current_price = ticker['last']
        
        # 필요한 마진 계산
        config = SYMBOL_CONFIG.get(symbol, {})
        leverage = config.get('leverage', 10)
        position_value_usdt = amount * current_price
        required_margin = position_value_usdt / leverage
        
        # 안전 버퍼 적용
        SAFETY_BUFFER = 0.90
        safe_free_balance = free_balance * SAFETY_BUFFER
        
        logger.info(f"📊 주문 전 마진 체크:")
        logger.info(f"  - 필요 마진: ${required_margin:,.2f}")
        logger.info(f"  - 사용가능 마진: ${safe_free_balance:,.2f}")
        logger.info(f"  - 포지션 가치: ${position_value_usdt:,.2f}")
        
        # 마진 부족 시 수량 자동 조정
        if required_margin > safe_free_balance:
            logger.warning(f"⚠️ 마진 부족 감지 - 수량 자동 조정 시작")
            
            # 사용 가능한 마진으로 수량 재계산
            max_position_value = safe_free_balance * leverage
            adjusted_amount = max_position_value / current_price
            
            # 거래소 최소 수량 체크
            market = exchange.market(symbol)
            min_amount = market['limits']['amount']['min'] if 'limits' in market and 'amount' in market['limits'] else 0.001
            
            if adjusted_amount < min_amount:
                logger.error(f"❌ 조정된 수량 {adjusted_amount}이 최소 수량 {min_amount}보다 작음")
                return None
            
            logger.info(f"✅ 수량 조정: {amount} -> {adjusted_amount}")
            amount = adjusted_amount
            position_value_usdt = amount * current_price
            required_margin = position_value_usdt / leverage
        
        # 시장가 주문 실행 (재시도 로직 포함)
        max_retries = 3
        retry_count = 0
        order = None
        
        while retry_count < max_retries and order is None:
            try:
                if action == 'buy':
                    order = exchange.create_market_buy_order(symbol, amount)
                elif action == 'sell':
                    order = exchange.create_market_sell_order(symbol, amount)
                else:
                    return None
                    
            except Exception as order_error:
                if "Margin is insufficient" in str(order_error):
                    retry_count += 1
                    logger.warning(f"⚠️ 마진 부족 오류 발생 (시도 {retry_count}/{max_retries})")
                    
                    if retry_count < max_retries:
                        # 수량을 10% 줄여서 재시도
                        amount = amount * 0.9
                        logger.info(f"📉 수량 10% 감소 후 재시도: {amount}")
                        time.sleep(1)  # 1초 대기
                    else:
                        logger.error(f"❌ 최대 재시도 횟수 초과 - 주문 실패")
                        raise
                else:
                    # 다른 오류는 즉시 raise
                    raise
        
        if order is None:
            logger.error("❌ 주문 실행 실패")
            return None
        
        entry_price = order['average'] if order['average'] else order['price']
        
        logger.info(f"✅ 포지션 진입 완료 - {symbol} {action} @ ${entry_price:.2f}, 수량: {amount}")
        
        # SL/TP 주문 설정
        time.sleep(1)
        
        # 🆕 가격 검증 및 조정
        price_check = validate_and_adjust_prices(
            exchange, symbol, current_price, 
            stop_loss_price, take_profit_price, action
        )
        adjusted_sl = price_check['sl']
        adjusted_tp = price_check['tp']
        
        sl_order = None
        try:
            # 스탑로스 주문
            sl_side = 'sell' if action == 'buy' else 'buy'
            sl_order = exchange.create_order(
                symbol=symbol,
                type='STOP_MARKET',  # 🆕 대문자로 통일
                side=sl_side,
                amount=amount,  # 🆕 활성화
                params={
                    'stopPrice': adjusted_sl,  # 🆕 검증된 가격
                    'workingType': 'MARK_PRICE',
                    'reduceOnly': True,  # 🆕 활성화
                }
            )
            
            logger.info(f"✅ 스탑로스 주문 완료 - {symbol} @ ${adjusted_sl:.4f} (reduceOnly, 수량: {amount:.6f})")
        except Exception as sl_error:
            logger.error(f"❌ 스탑로스 설정 실패: {str(sl_error)}")
            logger.error(f"실패 상세 - SL가격: ${adjusted_sl:.4f}, 현재가: ${current_price:.4f}, 수량: {amount:.6f}")
            # 🆕 재시도 (closePosition 방식)
            try:
                logger.info(f"closePosition 방식으로 재시도...")
                sl_order = exchange.create_order(
                    symbol=symbol,
                    type='STOP_MARKET',
                    side=sl_side,
                    params={
                        'stopPrice': adjusted_sl,
                        'workingType': 'MARK_PRICE',
                        'closePosition': True,
                    }
                )
                logger.info(f"✅ 스탑로스 재시도 성공 - {symbol} @ ${adjusted_sl:.4f} (closePosition)")
            except Exception as retry_e:
                logger.error(f"❌ 스탑로스 재시도도 실패: {str(retry_e)}")
                sl_order = None
        
        tp_order = None
        try:
            # 테이크프로핏 주문
            tp_side = 'sell' if action == 'buy' else 'buy'
            tp_order = exchange.create_order(
                symbol=symbol,
                type='TAKE_PROFIT_MARKET',  # 🆕 대문자로 통일
                side=tp_side,
                amount=amount,  # 🆕 활성화
                params={
                    'stopPrice': adjusted_tp,  # 🆕 검증된 가격
                    'workingType': 'MARK_PRICE',
                    'reduceOnly': True,  # 🆕 활성화
                }
            )
            
            logger.info(f"✅ 테이크프로핏 주문 완료 - {symbol} @ ${adjusted_tp:.4f} (reduceOnly, 수량: {amount:.6f})")
        except Exception as tp_error:
            logger.error(f"❌ 테이크프로핏 설정 실패: {str(tp_error)}")
            logger.error(f"실패 상세 - TP가격: ${adjusted_tp:.4f}, 현재가: ${current_price:.4f}, 수량: {amount:.6f}")
            # 🆕 재시도 (closePosition 방식)
            try:
                logger.info(f"closePosition 방식으로 재시도...")
                tp_order = exchange.create_order(
                    symbol=symbol,
                    type='TAKE_PROFIT_MARKET',
                    side=tp_side,
                    params={
                        'stopPrice': adjusted_tp,
                        'workingType': 'MARK_PRICE',
                        'closePosition': True,
                    }
                )
                logger.info(f"✅ 테이크프로핏 재시도 성공 - {symbol} @ ${adjusted_tp:.4f} (closePosition)")
            except Exception as retry_e:
                logger.error(f"❌ 테이크프로핏 재시도도 실패: {str(retry_e)}")
                tp_order = None
        
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
        logger.error(f"❌ 주문 실행 오류: {str(e)}", exc_info=True)
        
        # 마진 부족 오류를 명확히 로깅
        if "Margin is insufficient" in str(e):
            logger.error("💡 해결 방법: position_size_percent를 낮추거나 잔고를 늘려주세요")
            
            # 텔레그램 알림
            if ENABLE_TELEGRAM:
                send_telegram_notification(
                    f"❌ 마진 부족으로 주문 실패\n"
                    f"심볼: {symbol}\n"
                    f"필요 마진: ${required_margin:,.2f}\n"
                    f"사용가능: ${safe_free_balance:,.2f}\n"
                    f"해결: position_size_percent 조정 필요",
                    'error'
                )
        
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
                # amount=amount,
                params={
                    'stopPrice': new_sl_price,
                    'workingType': 'MARK_PRICE',
                    # 'reduceOnly': True,
                    'closePosition': True  # 모든 포지션 정리
                }
            )

            logger.info(f"{symbol} 스탑로스 업데이트: {new_sl_price} (closePosition=True)")
            
    except Exception as e:
        logger.error(f"스탑로스 업데이트 오류 ({symbol}): {str(e)}")

def format_position_entry_message(symbol, action, amount, entry_price, sl, tp, pl_ratio, 
                                 position_size, balance, trailing_stop=None, trailing_activation=None,
                                 success_count=None, total_users=None):
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
"""
    
    # 멀티유저 통계 추가
    if success_count is not None and total_users is not None:
        message += f"<b>주문 전달:</b> ✅ {success_count}/{total_users}명\n"
    
    message += f"""
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
    """TradingView 웹훅 수신 및 처리 - 개선 버전 (강력한 파싱)"""
    try:
        # JSON 데이터 파싱 (개선된 에러 처리)
        data = None
        raw_data = ""
        
        # Content-Type 확인
        content_type = request.headers.get('Content-Type', '')
        
        # JSON 파싱 시도
        if 'application/json' in content_type:
            try:
                data = request.get_json(force=True)
                logger.info(f"✅ JSON 데이터 성공적으로 파싱됨")
            except Exception as e:
                logger.warning(f"⚠️ JSON 파싱 실패, raw 데이터로 재시도: {e}")
        
        # JSON 파싱 실패 시 raw 데이터로 처리
        if data is None:
            raw_data = request.get_data(as_text=True)
            logger.info(f"📥 Raw webhook data (first 500 chars): {raw_data[:500]}")
            
            # === 1단계: JSON 정리 및 파싱 ===
            try:
                # TradingView Pine Script에서 생성된 잘못된 JSON 수정
                # 예: "value":-0.2294" → "value":-0.2294
                cleaned_data = re.sub(r'":(-?\d+\.?\d*)"', r'":\1', raw_data)
                # 숫자 뒤의 불필요한 따옴표 제거
                cleaned_data = re.sub(r'(\d)"([,}])', r'\1\2', cleaned_data)
                
                data = json.loads(cleaned_data)
                logger.info(f"✅ 정리된 데이터에서 JSON 파싱 성공")
            except json.JSONDecodeError as e:
                logger.warning(f"⚠️ 정리 후에도 JSON 파싱 실패: {e}")
                
                # === 2단계: 정규식으로 필수 필드 추출 ===
                try:
                    logger.info(f"🔍 정규식 기반 필수 필드 추출 시도...")
                    parsed_data = {}
                    
                    # 필수 필드 패턴 정의 (기술적 지표 포함)
                    patterns = {
                        'action': r'"action"\s*:\s*"([^"]+)"',
                        'symbol': r'"symbol"\s*:\s*"([^"]+)"',
                        'entry_price': r'"entry_price"\s*:\s*(-?\d+\.?\d*)',
                        'stop_loss': r'"stop_loss"\s*:\s*(-?\d+\.?\d*)',
                        'take_profit': r'"take_profit"\s*:\s*(-?\d+\.?\d*)',
                        'position_type': r'"position_type"\s*:\s*"([^"]+)"',
                        'exit_price': r'"exit_price"\s*:\s*(-?\d+\.?\d*)',
                        'profit_percent': r'"profit_percent"\s*:\s*(-?\d+\.?\d*)',
                        'exit_reason': r'"exit_reason"\s*:\s*"([^"]+)"',
                        'trailing_stop_percent': r'"trailing_stop_percent"\s*:\s*(null|"null"|-?\d+\.?\d*)',
                        'trailing_activation_percent': r'"trailing_activation_percent"\s*:\s*(null|"null"|-?\d+\.?\d*)',
                        # 기술적 지표 추가
                        'timeframe': r'"timeframe"\s*:\s*"([^"]+)"',
                        'cmf_value': r'"cmf_value"\s*:\s*(-?\d+\.?\d*)',
                        'cmf_momentum': r'"cmf_momentum"\s*:\s*(-?\d+\.?\d*)',
                        'adx': r'"adx"\s*:\s*(-?\d+\.?\d*)',
                        'rsi': r'"rsi"\s*:\s*(-?\d+\.?\d*)',
                        'volume_ratio': r'"volume_ratio"\s*:\s*(-?\d+\.?\d*)'
                    }
                    
                    # 각 필드 추출
                    for key, pattern in patterns.items():
                        match = re.search(pattern, raw_data, re.IGNORECASE)
                        if match:
                            value = match.group(1)
                            # 숫자 필드 변환
                            if key in ['entry_price', 'stop_loss', 'take_profit', 'exit_price', 
                                      'profit_percent', 'cmf_value', 'cmf_momentum', 
                                      'adx', 'rsi', 'volume_ratio']:
                                try:
                                    parsed_data[key] = float(value)
                                except:
                                    parsed_data[key] = None
                            elif key in ['trailing_stop_percent', 'trailing_activation_percent']:
                                if value in ['null', '"null"']:
                                    parsed_data[key] = None
                                else:
                                    try:
                                        parsed_data[key] = float(value)
                                    except:
                                        parsed_data[key] = None
                            else:
                                parsed_data[key] = value
                    
                    # 필수 필드 검증
                    required_fields = ['action', 'symbol']
                    if all(field in parsed_data for field in required_fields):
                        data = parsed_data
                        logger.info(f"✅ 정규식 파싱 성공! 추출된 필드: {list(data.keys())}")
                    else:
                        missing = [f for f in required_fields if f not in parsed_data]
                        logger.error(f"❌ 필수 필드 누락: {missing}")
                        
                        # === 3단계: Pine Script 형식(key=value) 파싱 시도 ===
                        try:
                            logger.info(f"🔍 Pine Script format 파싱 시도...")
                            parsed_data = {}
                            lines = raw_data.strip().split('\n')
                            
                            for line in lines:
                                line = line.strip()
                                if '=' in line:
                                    key, value = line.split('=', 1)
                                    key = key.strip()
                                    value = value.strip()
                                    
                                    # 값 타입 변환
                                    if value.lower() in ['true', 'false']:
                                        parsed_data[key] = value.lower() == 'true'
                                    elif value.lower() in ['null', 'none', '']:
                                        parsed_data[key] = None
                                    else:
                                        try:
                                            # 숫자 변환 시도
                                            if '.' in value:
                                                parsed_data[key] = float(value)
                                            else:
                                                parsed_data[key] = int(value)
                                        except ValueError:
                                            # 문자열로 저장
                                            parsed_data[key] = value.strip('"').strip("'")
                            
                            if parsed_data and all(field in parsed_data for field in required_fields):
                                data = parsed_data
                                logger.info(f"✅ Pine Script format 파싱 성공: {list(data.keys())}")
                            else:
                                logger.error(f"❌ Pine Script 파싱 실패 - 필수 필드 없음")
                                
                                # 🆕 AI 긴급 파라미터 생성 시도
                                if 'symbol' in parsed_data and 'action' in parsed_data:
                                    logger.info(f"🚨 AI 긴급 파라미터 생성 시도...")
                                    emergency_params = ai_emergency_parameters(parsed_data['symbol'], parsed_data['action'])
                                    
                                    if emergency_params:
                                        # AI가 생성한 파라미터로 data 구성
                                        data = {
                                            'symbol': parsed_data['symbol'],
                                            'action': parsed_data['action'],
                                            'position_percent': emergency_params.percentage,
                                            'stop_loss_price': emergency_params.stop_loss_price,
                                            'take_profit_price': emergency_params.take_profit_price,
                                            'source': 'ai_emergency'
                                        }
                                        logger.info(f"✅ AI 긴급 파라미터로 복구 성공")
                                    else:
                                        return jsonify({'error': 'Failed to parse webhook data and AI recovery failed'}), 400
                                else:
                                    return jsonify({'error': 'Failed to parse webhook data - missing required fields'}), 400
                                
                        except Exception as pe:
                            logger.error(f"❌ Pine Script 파싱 오류: {pe}")
                            return jsonify({'error': 'Invalid data format'}), 400
                        
                except Exception as regex_error:
                    logger.error(f"❌ 정규식 파싱 오류: {regex_error}")
                    return jsonify({'error': 'Failed to extract required fields'}), 400
        
        # 기본 검증
        if not data:
            logger.error("❌ No data received in webhook")
            return jsonify({'error': 'No data received'}), 400
        
        logger.info(f"📋 최종 파싱된 데이터 키: {list(data.keys())}")
        
        # null 안전 파싱 - 모든 필드에 대해 null/None 처리
        def safe_get_float(data, key, default=None):
            """null, 'null', '', None을 안전하게 처리"""
            value = data.get(key)
            if value is None or value == 'null' or value == '':
                return default
            try:
                return float(value)
            except (ValueError, TypeError):
                logger.warning(f"⚠️ {key} 변환 실패: {value} → {default} 사용")
                return default
        
        action = data.get('action')
        original_action = action  # 원래 액션 저장 (modify 케이스를 위해)
        symbol = data.get('symbol', 'BTC/USDT')
        
        # 숫자 필드 안전 파싱 (null 허용)
        entry_price = safe_get_float(data, 'entry_price')
        stop_loss = safe_get_float(data, 'stop_loss')
        take_profit = safe_get_float(data, 'take_profit')
        exit_price = safe_get_float(data, 'exit_price')
        profit_percent = safe_get_float(data, 'profit_percent', 0)
        trailing_stop_percent = safe_get_float(data, 'trailing_stop_percent')
        trailing_activation_percent = safe_get_float(data, 'trailing_activation_percent')
        
        # 문자열 필드 안전 파싱
        position_type = data.get('position_type', 'normal')
        exit_reason = data.get('exit_reason', 'manual')
        
        message = json.dumps(data, ensure_ascii=False) if isinstance(data, dict) else str(data)
        
        logger.info(f"📊 웹훅 수신 - 심볼: {symbol}, 액션: {action}")
        logger.info(f"💰 파싱된 가격 정보:")
        logger.info(f"   - Entry: {entry_price}")
        logger.info(f"   - Stop Loss: {stop_loss}")
        logger.info(f"   - Take Profit: {take_profit}")
        logger.info(f"   - Exit: {exit_price}")
        
        # 필수 필드 검증 (action과 symbol은 필수)
        if not action or not symbol:
            error_msg = f"필수 필드 누락 - action: {action}, symbol: {symbol}"
            logger.error(f"❌ {error_msg}")
            return jsonify({'error': error_msg}), 400
        
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
            'ASTERUSDT.P': 'ASTER/USDT',
            'DASHUSDT': 'DASH/USDT',
            'DASHUSDT.P': 'DASH/USDT',
            'TRUMPUSDT': 'TRUMP/USDT',
            'TRUMPUSDT.P': 'TRUMP/USDT',
            'SUIUSDT': 'SUI/USDT',
            'SUIUSDT.P': 'SUI/USDT',
            'WLDUSDT': 'WLD/USDT',
            'WLDUSDT.P': 'WLD/USDT',
            'GIGGLEUSDT': 'GIGGLE/USDT',
            'GIGGLEUSDT.P': 'GIGGLE/USDT',
            'LTCUSDT': 'LTC/USDT',
            'LTCUSDT.P': 'LTC/USDT',
            'DUSKUSDT': 'DUSK/USDT',
            'DUSKUSDT.P': 'DUSK/USDT',
            'FETUSDT': 'FET/USDT',
            'FETUSDT.P': 'FET/USDT',
            'PENDLEUSDT': 'PENDLE/USDT',
            'PENDLEUSDT.P': 'PENDLE/USDT',
            'FILUSDT': 'FIL/USDT',
            'FILUSDT.P': 'FIL/USDT',
            'ARUSDT': 'AR/USDT',
            'ARUSDT.P': 'AR/USDT',
            'OGUSDT': 'OG/USDT',
            'OGUSDT.P': 'OG/USDT',
            'FUSDT': 'F/USDT',
            'FUSDT.P': 'F/USDT',
            'TAOUSDT': 'TAO/USDT',
            'TAOUSDT.P': 'TAO/USDT',
            'RAYSOLUSDT': 'RAYSOL/USDT',
            'RAYSOLUSDT.P': 'RAYSOL/USDT',
            'COTIUSDT': 'COTI/USDT',
            'COTIUSDT.P': 'COTI/USDT'
        }
        
        original_symbol = symbol
        # 심볼 매핑 적용
        if symbol in symbol_mapping:
            symbol = symbol_mapping[symbol]
            logger.info(f"🔄 심볼 매핑: {original_symbol} → {symbol}")
        # 매핑이 없는 경우만 정규화
        elif not symbol.endswith('/USDT'):
            # .P 제거 후 정규화
            clean_symbol = symbol.replace('.P', '').replace('.p', '')
            if 'USDT' in clean_symbol:
                base = clean_symbol.replace('USDT', '')
                symbol = f"{base}/USDT"
                logger.info(f"🔄 심볼 정규화: {original_symbol} → {symbol}")
            else:
                symbol = f"{clean_symbol}/USDT"
                logger.info(f"🔄 심볼 정규화: {original_symbol} → {symbol}")
        
        # 심볼 설정 확인
        if symbol not in SYMBOL_CONFIG:
            error_msg = f'심볼 {symbol}이(가) 설정되지 않음 (원본: {original_symbol})'
            logger.error(f"❌ {error_msg}")
            
            # 텔레그램 알림
            if ENABLE_TELEGRAM:
                notify_msg = f"""
❌ <b>미등록 심볼 감지</b>

<b>원본 심볼:</b> {original_symbol}
<b>변환 심볼:</b> {symbol}
<b>액션:</b> {action}

⚠️ SYMBOL_CONFIG에 해당 심볼을 추가해주세요.

⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
                """.strip()
                send_telegram_notification(notify_msg, 'error')
            
            return jsonify({'error': error_msg}), 400
        
        if not SYMBOL_CONFIG[symbol].get('enabled', True):
            error_msg = f'심볼 {symbol}이(가) 비활성화됨'
            logger.warning(f"⚠️ {error_msg}")
            return jsonify({'error': error_msg}), 400
        
        logger.info(f"✅ 심볼 검증 완료: {symbol}")
        
        # 심볼 설정 가져오기 (symbol_config 에러 방지)
        symbol_config = SYMBOL_CONFIG.get(symbol, {})
        
        # AI 검증이 활성화되어 있는지 확인
        use_ai = symbol_config.get('ai_validation', True)
        
        if use_ai:
            # 시장 데이터 수집
            market_data = get_market_data(symbol)
            if not market_data:
                return jsonify({'error': 'Failed to collect market data'}), 500
            
            # 최근 거래 내역 조회
            conn = get_db_connection()
            recent_trades = get_recent_trades(conn, symbol)
            conn.close()
            
            # AI 검증 (close_position 포함)
            ai_decision = ai_validate_signal(symbol, action, market_data, recent_trades, message_data=data)
            
            if not ai_decision:
                return jsonify({'error': 'AI validation failed'}), 500
            
            # 🆕 반대 진입 처리
            if ai_decision.get('decision') == 'reverse':
                original_action = action
                action = ai_decision.get('modified_action', 'sell' if original_action == 'buy' else 'buy')
                
                logger.warning(f"🔄 REVERSE ENTRY: {original_action} → {action}")
                
                # 텔레그램 알림
                reverse_message = f"""
🔄 <b>반대 진입 실행</b>

<b>심볼:</b> {symbol}
<b>원본 신호:</b> {original_action.upper()}
<b>변경된 방향:</b> {action.upper()}
<b>이유:</b> 극단적 과매수/과매도 상태
<b>포지션 크기:</b> {ai_decision.get('percentage', 30)}%
<b>신뢰도:</b> {ai_decision.get('confidence', 0.5):.1%}

⚠️ 반대 진입은 리스크가 높으니 주의하세요.

⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
                """.strip()
                send_telegram_notification(reverse_message, 'warning')
                
                # decision을 approve로 변경하여 거래 실행
                ai_decision['decision'] = 'approve'
                
                # 포지션 크기 조정 (보수적)
                if ai_decision.get('percentage', 30) > 50:
                    ai_decision['percentage'] = 30
            
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
                    # 🆕 모든 유저의 포지션 청산 및 TP/SL 자동 취소
                    success_count, total_users = close_position_for_all_users(symbol)
                    
                    if success_count > 0:
                        # Primary User로 포지션 정보 조회 (메시지 표시용)
                        try:
                            ticker = exchange.fetch_ticker(symbol)
                            current_price = ticker['last']
                            
                            message = f"""
✅ <b>포지션 청산 완료 (Multi-User)</b>

<b>심볼:</b> {symbol}
<b>청산 성공:</b> {success_count}/{total_users}명
<b>청산가:</b> ${current_price:,.2f}
<b>청산 사유:</b> {data.get('exit_reason', 'Manual close')}

<b>AI 검증:</b>
• 신뢰도: {ai_decision['confidence']:.1%}
• 긴급도: {ai_decision.get('urgency', 'N/A')}
• 이유: {ai_decision['reason']}

⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
                            """.strip()
                            send_telegram_notification(message, 'success')
                        except Exception as msg_error:
                            logger.error(f"메시지 전송 오류: {msg_error}")
                        
                        # 포지션 추적에서 제거
                        if symbol in current_positions:
                            # 🆕 v8.1: 포지션 종료 기록 및 이벤트 발생
                            position_data = current_positions[symbol].copy()
                            position_data['mark_price'] = current_price
                            
                            record_position_closure_with_real_pnl(
                                symbol,
                                position_data,
                                close_type=data.get('exit_reason', 'manual')
                            )
                            
                            # 🔥 v8.5 Fixed: 포지션 진입 시간도 제거
                            if symbol in position_entry_times:
                                del position_entry_times[symbol]
                                logger.info(f"🗑️ 웹훅 청산 후 진입 시간 제거: {symbol}")
                            
                            del current_positions[symbol]
                        
                        return jsonify({
                            'status': 'closed',
                            'symbol': symbol,
                            'success_count': success_count,
                            'total_users': total_users,
                            'ai_confidence': ai_decision['confidence']
                        }), 200
                    else:
                        return jsonify({
                            'status': 'no_position',
                            'message': f'No open position found for {symbol}'
                        }), 200
                    logger.error(f"포지션 청산 오류: {str(e)}", exc_info=True)
                    error_message = f"""
❌ <b>포지션 청산 오류</b>

<b>심볼:</b> {symbol}
<b>오류:</b> {str(e)}
⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
                    """.strip()
                    send_telegram_notification(error_message, 'error')
                    return jsonify({'error': str(e)}), 500
                        
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
                
                # 텔레그램 알림 전송 (modify 케이스 추가)
                message = f"""
🔄 <b>AI 신호 수정</b>

<b>심볼:</b> {symbol}
<b>원래 신호:</b> {original_action.upper()}
<b>수정된 신호:</b> {action.upper()}
<b>AI 결정:</b> MODIFY
<b>신뢰도:</b> {ai_decision['confidence']:.1%}
<b>포지션 크기:</b> {ai_decision['percentage']}%
<b>이유:</b> {ai_decision['reason']}

<b>수정된 가격:</b>
• 손절가: ${ai_decision['stop_loss_price']:.4f}
• 목표가: ${ai_decision['take_profit_price']:.4f}
• P/L 비율: {ai_decision['pl_ratio']:.1f}

⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
                """.strip()
                send_telegram_notification(message, 'info')
                
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
            
            # 웹훅 데이터 우선 사용, null이면 기본값 적용
            if action == 'buy':
                stop_loss_price = stop_loss if stop_loss is not None else (current_price * 0.98)  # -2%
                take_profit_price = take_profit if take_profit is not None else (current_price * 1.04)  # +4%
            else:
                stop_loss_price = stop_loss if stop_loss is not None else (current_price * 1.02)  # +2%
                take_profit_price = take_profit if take_profit is not None else (current_price * 0.96)  # -4%
            
            pl_ratio = 2.0
            position_percent = SYMBOL_CONFIG[symbol].get('position_size_percent', 10)
            
            logger.info(f"기본값 사용 - SL: {stop_loss_price:.4f}, TP: {take_profit_price:.4f}")
        
        # 🆕 TP/SL 현실적 조정 (매물대 및 지지/저항선 기반)
        # AI 검증 여부와 관계없이 항상 실행
        if action in ['buy', 'sell']:
            try:
                # 현재가 가져오기
                ticker = exchange.fetch_ticker(symbol)
                current_price_for_adjust = ticker['last']
                
                # 시장 데이터 수집 (아직 없는 경우)
                if 'market_data' not in locals() or not market_data:
                    market_data = get_market_data(symbol)
                
                if market_data:
                    # TP/SL 조정 실행
                    adjustment_result = adjust_tp_sl_based_on_levels(
                        symbol, action, current_price_for_adjust,
                        stop_loss_price, take_profit_price, market_data
                    )
                    
                    if adjustment_result['is_adjusted']:
                        logger.info(f"🎯 TP/SL 조정 완료:")
                        logger.info(f"   {adjustment_result['sl_reason']}")
                        logger.info(f"   {adjustment_result['tp_reason']}")
                        
                        # 조정된 가격 적용
                        stop_loss_price = adjustment_result['adjusted_sl']
                        take_profit_price = adjustment_result['adjusted_tp']
                        
                        # 텔레그램 알림 (조정된 경우에만)
                        if ENABLE_TELEGRAM:
                            adjust_msg = f"""
💡 <b>TP/SL 자동 조정</b>

<b>심볼:</b> {symbol}
<b>방향:</b> {action.upper()}

<b>조정 전:</b>
• SL: ${adjustment_result.get('adjusted_sl', stop_loss_price) / (1 + 0.005 if action == 'buy' else 1 - 0.005):.4f}
• TP: ${adjustment_result.get('adjusted_tp', take_profit_price) / (1 - 0.005 if action == 'buy' else 1 + 0.005):.4f}

<b>조정 후:</b>
• SL: ${stop_loss_price:.4f}
• TP: ${take_profit_price:.4f}

<b>조정 사유:</b>
• SL: {adjustment_result['sl_reason']}
• TP: {adjustment_result['tp_reason']}

<b>주요 지지/저항선:</b>
"""
                            # 지지/저항선 정보 추가
                            if adjustment_result.get('volume_profile'):
                                vp = adjustment_result['volume_profile']
                                if vp.get('support_levels'):
                                    supports = ", ".join([f"${s:.2f}" for s in vp['support_levels'][:2]])
                                    adjust_msg += f"• 지지: {supports}\n"
                                if vp.get('resistance_levels'):
                                    resistances = ", ".join([f"${r:.2f}" for r in vp['resistance_levels'][:2]])
                                    adjust_msg += f"• 저항: {resistances}\n"
                            
                            adjust_msg += f"\n⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                            send_telegram_notification(adjust_msg.strip(), 'info')
                    else:
                        logger.info(f"✅ TP/SL 조정 불필요 (현실적 범위 내)")
                else:
                    logger.warning(f"⚠️ 시장 데이터 수집 실패 - TP/SL 조정 스킵")
                    
            except Exception as adjust_error:
                logger.error(f"❌ TP/SL 조정 오류: {adjust_error}")
                logger.error(f"   원본 TP/SL 사용")
        
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
            
            # 트레일링 스탑 설정 (null 안전 처리)
            trailing_stop = trailing_stop_percent if trailing_stop_percent is not None else DEFAULT_TRAILING_STOP_PERCENT
            trailing_activation = trailing_activation_percent if trailing_activation_percent is not None else DEFAULT_TRAILING_ACTIVATION_PERCENT
            
            # 주문 실행
            # 🆕 모든 유저에 대해 거래 실행
            orders = execute_trade_for_all_users(
                symbol, action, amount, 
                stop_loss_price, take_profit_price,
                trailing_stop, trailing_activation
            )
            
            if orders:
                # 포지션 추적 (entry_time, leverage, position_type 추가)
                current_positions[symbol] = {
                    'side': action,
                    'entry_price': orders['actual_entry'],
                    'amount': orders['adjusted_amount'],
                    'stop_loss': stop_loss_price,
                    'take_profit': take_profit_price,
                    'trailing_stop_percent': trailing_stop,
                    'trailing_activation_percent': trailing_activation,
                    'entry_time': datetime.now(),  # 진입 시간 추가
                    'leverage': symbol_config.get('leverage', 10),  # 레버리지 추가
                    'position_size_usdt': position_size,  # 포지션 크기 추가
                    'position_type': 'auto'  # 자동 거래 표시
                }
                
                # 🔥 v8.5 Fixed: 포지션 진입 시간 기록 (청산 감지 보호용)
                position_entry_times[symbol] = datetime.now()
                logger.info(f"📝 새 포지션 진입 시간 기록: {symbol} at {position_entry_times[symbol]}")
                
                # 🔥 포지션 진입 즉시 DB 기록 (대시보드 표시용)
                try:
                    conn = get_db_connection()
                    c = conn.cursor()
                    
                    # position_history에 진입 기록
                    c.execute("""INSERT INTO position_history 
                                (timestamp, symbol, side, amount, entry_price, current_price,
                                 pnl_usdt, pnl_percent, position_value, required_margin, liquidation_price)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                              (datetime.now().isoformat(), symbol, action, orders['adjusted_amount'], 
                               orders['actual_entry'], orders['actual_entry'],
                               0, 0,  # 진입 시점 PnL은 0
                               position_size, position_size / symbol_config.get('leverage', 10),
                               stop_loss_price))  # 청산가 대신 스탑로스 사용
                    
                    conn.commit()
                    conn.close()
                    logger.info(f"✅ Position entry recorded to DB: {symbol} {action}")
                except Exception as db_error:
                    logger.error(f"❌ DB 기록 실패 (포지션은 정상 진입됨): {db_error}")
                    # DB 실패해도 포지션 추적은 계속
                
                # 알림 전송
                entry_message = format_position_entry_message(
                    symbol, action, orders['adjusted_amount'], orders['actual_entry'],
                    stop_loss_price, take_profit_price,
                    pl_ratio, position_size, usdt_balance,
                    trailing_stop, trailing_activation,
                    orders.get('success_count'), orders.get('total_users')
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
    """시스템 상태 확인 (🆕 자동/수동 포지션 구분)"""
    enabled_symbols = [s for s, c in SYMBOL_CONFIG.items() if c.get('enabled', True)]
    ai_enabled_symbols = [s for s, c in SYMBOL_CONFIG.items() if c.get('ai_validation', True)]
    ai_monitored_symbols = [s for s, c in SYMBOL_CONFIG.items() if c.get('ai_monitoring', True)]
    
    # 🆕 포지션 타입별 카운트
    auto_count = sum(1 for pos in current_positions.values() if pos.get('position_type', 'auto') == 'auto')
    manual_count = sum(1 for pos in current_positions.values() if pos.get('position_type', 'auto') == 'manual')
    
    # 포지션 상세 정보 (🆕 position_type 포함)
    positions_detail = {}
    for symbol, pos in current_positions.items():
        positions_detail[symbol] = {
            'side': pos['side'],
            'entry_price': pos['entry_price'],
            'amount': pos['amount'],
            'position_type': pos.get('position_type', 'auto'),  # 🆕
            'entry_time': pos.get('entry_time', datetime.now()).isoformat() if isinstance(pos.get('entry_time'), datetime) else str(pos.get('entry_time', 'N/A'))
        }
    
    return jsonify({
        'status': 'running',
        'server_port': SERVER_PORT,
        'current_positions': positions_detail,
        'position_count': len(current_positions),
        'auto_position_count': auto_count,  # 🆕
        'manual_position_count': manual_count,  # 🆕
        'telegram_enabled': ENABLE_TELEGRAM,
        'total_symbols': len(enabled_symbols),
        'ai_enabled_symbols': len(ai_enabled_symbols),
        'ai_monitored_symbols': len(ai_monitored_symbols),
        'ai_monitoring_active': ai_monitor_running,
        'ai_monitor_interval': AI_MONITOR_INTERVAL,
        'symbols': enabled_symbols,
        'timestamp': datetime.now().isoformat()
    }), 200

@app.route('/positions/sync', methods=['POST'])
def sync_positions():
    """거래소 포지션 수동 동기화"""
    try:
        position_count = sync_positions_from_exchange()
        
        return jsonify({
            'status': 'success',
            'message': f'{position_count}개 포지션 동기화 완료',
            'positions': {
                symbol: {
                    'side': pos['side'],
                    'entry_price': pos['entry_price'],
                    'amount': pos['amount']
                } for symbol, pos in current_positions.items()
            }
        }), 200
        
    except Exception as e:
        logger.error(f"포지션 동기화 오류: {str(e)}")
        return jsonify({'error': str(e)}), 500

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
        conn = get_db_connection()
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

@app.route('/trades/completed', methods=['GET'])
def get_completed_trades():
    """완료된 거래 조회 (대시보드용)"""
    try:
        conn = get_db_connection()
        c = conn.cursor()
        
        limit = request.args.get('limit', 100, type=int)
        symbol = request.args.get('symbol', None)
        
        query = "SELECT * FROM completed_trades WHERE 1=1"
        params = []
        
        if symbol:
            query += " AND symbol = ?"
            params.append(symbol)
            
        query += " ORDER BY close_timestamp DESC LIMIT ?"
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
        logger.error(f"완료된 거래 조회 오류: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/balance/history', methods=['GET'])
def get_balance_history():
    """잔고 히스토리 조회 (대시보드용)"""
    try:
        conn = get_db_connection()
        c = conn.cursor()
        
        days = request.args.get('days', 30, type=int)
        cutoff_date = (datetime.now() - timedelta(days=days)).isoformat()
        
        c.execute("""SELECT * FROM balance_history 
                    WHERE timestamp >= ? 
                    ORDER BY timestamp DESC""", (cutoff_date,))
        
        columns = [desc[0] for desc in c.description]
        history = [dict(zip(columns, row)) for row in c.fetchall()]
        
        conn.close()
        
        return jsonify({
            'success': True,
            'count': len(history),
            'history': history
        }), 200
        
    except Exception as e:
        logger.error(f"잔고 히스토리 조회 오류: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/positions/history', methods=['GET'])
def get_position_history():
    """포지션 히스토리 조회"""
    try:
        conn = get_db_connection()
        c = conn.cursor()
        
        hours = request.args.get('hours', 24, type=int)
        cutoff_date = (datetime.now() - timedelta(hours=hours)).isoformat()
        
        c.execute("""SELECT * FROM position_history 
                    WHERE timestamp >= ? 
                    ORDER BY timestamp DESC""", (cutoff_date,))
        
        columns = [desc[0] for desc in c.description]
        history = [dict(zip(columns, row)) for row in c.fetchall()]
        
        conn.close()
        
        return jsonify({
            'success': True,
            'count': len(history),
            'history': history
        }), 200
        
    except Exception as e:
        logger.error(f"포지션 히스토리 조회 오류: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/stats/overview', methods=['GET'])
def get_stats_overview():
    """통계 개요 조회 (대시보드용)"""
    try:
        conn = get_db_connection()
        c = conn.cursor()
        
        # 전체 통계
        c.execute("""SELECT 
                        COUNT(*) as total_trades,
                        SUM(CASE WHEN is_win = 1 THEN 1 ELSE 0 END) as winning_trades,
                        SUM(CASE WHEN is_win = 0 THEN 1 ELSE 0 END) as losing_trades,
                        AVG(pnl_percent) as avg_pnl_percent,
                        SUM(pnl_usdt) as total_pnl,
                        MAX(pnl_usdt) as best_trade,
                        MIN(pnl_usdt) as worst_trade,
                        AVG(holding_time_minutes) as avg_holding_time
                    FROM completed_trades""")
        
        stats = c.fetchone()
        
        # 최근 잔고
        c.execute("""SELECT * FROM balance_history 
                    ORDER BY timestamp DESC LIMIT 1""")
        latest_balance = c.fetchone()
        
        conn.close()
        
        # 승률 계산
        total_trades = stats[0] or 0
        winning_trades = stats[1] or 0
        win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
        
        return jsonify({
            'success': True,
            'stats': {
                'total_trades': total_trades,
                'winning_trades': winning_trades,
                'losing_trades': stats[2] or 0,
                'win_rate': win_rate,
                'avg_pnl_percent': stats[3] or 0,
                'total_pnl': stats[4] or 0,
                'best_trade': stats[5] or 0,
                'worst_trade': stats[6] or 0,
                'avg_holding_time': stats[7] or 0
            },
            'balance': {
                'total': latest_balance[2] if latest_balance else 0,
                'free': latest_balance[3] if latest_balance else 0,
                'used': latest_balance[4] if latest_balance else 0
            }
        }), 200
        
    except Exception as e:
        logger.error(f"통계 개요 조회 오류: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/trades', methods=['GET'])
def get_trades():
    """거래 히스토리 조회 엔드포인트"""
    try:
        limit = request.args.get('limit', 100, type=int)
        symbol = request.args.get('symbol', None)
        trade_type = request.args.get('trade_type', None)
        
        conn = get_db_connection()
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

# 🆕 v8.1: 실시간 이벤트 API
@app.route('/events/unread', methods=['GET'])
def get_unread_events():
    """
    미처리 이벤트 조회 (대시보드용)
    """
    try:
        conn = sqlite3.connect('integrated_trades.db')
        c = conn.cursor()
        
        c.execute("""
            SELECT id, event_type, symbol, timestamp, data
            FROM realtime_events
            WHERE is_processed = 0
            ORDER BY timestamp DESC
            LIMIT 50
        """)
        
        events = []
        for row in c.fetchall():
            events.append({
                'id': row[0],
                'event_type': row[1],
                'symbol': row[2],
                'timestamp': row[3],
                'data': json.loads(row[4]) if row[4] else {}
            })
        
        conn.close()
        
        return jsonify({
            'success': True,
            'count': len(events),
            'events': events
        }), 200
        
    except Exception as e:
        logger.error(f"이벤트 조회 오류: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/events/mark_processed', methods=['POST'])
def mark_events_processed():
    """
    이벤트를 처리됨으로 표시
    """
    try:
        data = request.get_json()
        event_ids = data.get('event_ids', [])
        
        if not event_ids:
            return jsonify({'error': 'event_ids 필수'}), 400
        
        conn = sqlite3.connect('integrated_trades.db')
        c = conn.cursor()
        
        placeholders = ','.join(['?' for _ in event_ids])
        c.execute(f"""
            UPDATE realtime_events
            SET is_processed = 1, processed_at = ?
            WHERE id IN ({placeholders})
        """, [datetime.now().isoformat()] + event_ids)
        
        conn.commit()
        conn.close()
        
        return jsonify({
            'success': True,
            'processed_count': len(event_ids)
        }), 200
        
    except Exception as e:
        logger.error(f"이벤트 처리 표시 오류: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/system/status', methods=['GET'])
def get_system_status():
    """
    시스템 상태 조회 (대시보드용)
    """
    try:
        return jsonify({
            'success': True,
            'status': {
                'active_positions': len(current_positions),
                'websocket_enabled': True,
                'polling_enabled': True,
                'ai_monitoring_interval': AI_MONITOR_INTERVAL,
                'active_users': len(exchanges),
                'server_port': SERVER_PORT,
            },
            'positions': [
                {
                    'symbol': symbol,
                    'type': pos.get('position_type', 'manual'),
                    'side': pos.get('side', 'unknown')
                }
                for symbol, pos in current_positions.items()
            ]
        }), 200
        
    except Exception as e:
        logger.error(f"시스템 상태 조회 오류: {str(e)}")
        return jsonify({'error': str(e)}), 500

# 🆕 v8.1: WebSocket 및 포지션 모니터링 함수
def start_binance_websocket_listener():
    """
    바이낸스 WebSocket User Data Stream
    TP/SL 체결을 실시간으로 감지 (0.1초 이내)
    """
    def websocket_loop():
        try:
            # websockets 모듈 체크
            try:
                import asyncio
                import websockets
            except ImportError:
                logger.warning("⚠️ websockets 라이브러리가 설치되지 않았습니다")
                logger.warning("💡 설치 방법: pip install websockets")
                logger.info("🔄 10초 폴링 모드로만 동작합니다")
                return
            
            logger.info("🌐 바이낸스 WebSocket 연결 시작...")
            
            # Listen Key 발급
            listen_key_response = exchange.fapiPrivatePostListenKey()
            listen_key = listen_key_response['listenKey']
            
            logger.info(f"✅ Listen Key 발급 완료: {listen_key[:10]}...")
            
            async def listen_to_websocket():
                ws_url = f"wss://fstream.binance.com/ws/{listen_key}"
                
                async with websockets.connect(ws_url) as websocket:
                    logger.info("✅ WebSocket 연결 성공 - 실시간 TP/SL 감지 활성화")
                    
                    while True:
                        try:
                            message = await websocket.recv()
                            data = json.loads(message)
                            
                            # ORDER_TRADE_UPDATE 이벤트 처리
                            if data.get('e') == 'ORDER_TRADE_UPDATE':
                                order_data = data['o']
                                symbol = order_data['s']  # BTCUSDT
                                order_status = order_data['X']  # FILLED, CANCELED, etc.
                                order_type = order_data['o']  # TAKE_PROFIT_MARKET, STOP_MARKET
                                
                                # TP/SL 체결 감지
                                if order_status == 'FILLED' and order_type in ['TAKE_PROFIT_MARKET', 'STOP_MARKET']:
                                    symbol_formatted = symbol.replace('USDT', '/USDT')
                                    
                                    logger.info(f"🔔 WebSocket: {symbol_formatted} {order_type} 체결 감지!")
                                    
                                    # 메모리에 포지션이 있는 경우만 처리
                                    if symbol_formatted in current_positions:
                                        position_data = current_positions[symbol_formatted].copy()
                                        
                                        # 체결 가격
                                        avg_price = float(order_data['ap'])
                                        position_data['mark_price'] = avg_price
                                        
                                        # 종료 타입 결정
                                        close_type = 'tp' if order_type == 'TAKE_PROFIT_MARKET' else 'sl'
                                        
                                        # 실제 PnL 기록 및 이벤트 발생
                                        realized_pnl = record_position_closure_with_real_pnl(
                                            symbol_formatted, 
                                            position_data, 
                                            close_type=close_type
                                        )
                                        
                                        # 메모리에서 제거
                                        del current_positions[symbol_formatted]
                                        
                                        # 텔레그램 알림
                                        if ENABLE_TELEGRAM and realized_pnl is not None:
                                            pnl_sign = "+" if realized_pnl > 0 else ""
                                            close_type_emoji = "✅" if close_type == 'tp' else "🛑"
                                            close_type_text = "익절" if close_type == 'tp' else "손절"
                                            
                                            message = f"""
{close_type_emoji} <b>{close_type_text} 체결 (WebSocket)</b>

<b>심볼:</b> {symbol_formatted}
<b>체결 가격:</b> ${avg_price:.4f}
<b>실현 손익:</b> {pnl_sign}${realized_pnl:.2f} USD
<b>체결 시간:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

⚡ 실시간 감지
                                            """.strip()
                                            send_telegram_notification(message, 'success' if close_type == 'tp' else 'warning')
                            
                            # ACCOUNT_UPDATE 이벤트 (포지션 변경)
                            elif data.get('e') == 'ACCOUNT_UPDATE':
                                positions = data.get('a', {}).get('P', [])
                                
                                for pos in positions:
                                    symbol = pos['s']
                                    position_amt = float(pos['pa'])
                                    
                                    symbol_formatted = symbol.replace('USDT', '/USDT')
                                    
                                    # 포지션이 0이 되었는데 메모리에는 있는 경우
                                    if position_amt == 0 and symbol_formatted in current_positions:
                                        logger.info(f"🔔 WebSocket: {symbol_formatted} 포지션 완전 청산 감지")
                                        
                                        position_data = current_positions[symbol_formatted].copy()
                                        
                                        # 실제 PnL 기록
                                        realized_pnl = record_position_closure_with_real_pnl(
                                            symbol_formatted, 
                                            position_data, 
                                            close_type='manual'
                                        )
                                        
                                        # 메모리에서 제거
                                        del current_positions[symbol_formatted]
                        
                        except websockets.exceptions.ConnectionClosed:
                            logger.warning("⚠️ WebSocket 연결 끊김 - 재연결 시도...")
                            break
                        except Exception as e:
                            logger.error(f"WebSocket 메시지 처리 오류: {str(e)}")
                            continue
            
            # Listen Key 갱신 (30분마다)
            async def keep_alive():
                while True:
                    await asyncio.sleep(1800)  # 30분
                    try:
                        exchange.fapiPrivatePutListenKey()
                        logger.info("🔄 Listen Key 갱신 완료")
                    except Exception as e:
                        logger.error(f"Listen Key 갱신 오류: {str(e)}")
            
            # 이벤트 루프 실행
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            # 두 태스크 동시 실행
            loop.run_until_complete(
                asyncio.gather(
                    listen_to_websocket(),
                    keep_alive()
                )
            )
            
        except Exception as e:
            logger.error(f"WebSocket 연결 오류: {str(e)}")
            logger.info("⚠️ WebSocket 없이 10초 폴링 모드로 동작합니다")
    
    # 백그라운드 스레드로 실행
    ws_thread = threading.Thread(target=websocket_loop, daemon=True)
    ws_thread.start()

def start_position_closure_monitor():
    """
    포지션 종료 감지 스레드 - v8.5 Fixed
    🔥 신규 포지션 30초 보호 + API 재시도 로직
    """
    def monitor_loop():
        global current_positions, position_entry_times, existing_positions_at_start
        
        logger.info("🔍 포지션 종료 감지 시작 (10초 간격, 신규 포지션 30초 보호)")
        
        while True:
            try:
                time.sleep(10)  # 10초마다 체크
                
                if not current_positions:
                    continue
                
                # 🔥 v8.5 Fixed: 바이낸스 API 재시도 로직 (3회)
                actual_positions = None
                for attempt in range(3):
                    try:
                        actual_positions = exchange.fetch_positions()
                        break
                    except Exception as e:
                        if attempt < 2:
                            logger.warning(f"포지션 조회 재시도 {attempt+1}/3: {str(e)}")
                            time.sleep(2)
                        else:
                            raise e
                
                if not actual_positions:
                    continue
                
                # 실제 포지션 목록
                actual_symbols = {
                    p['symbol'] for p in actual_positions 
                    if float(p['info'].get('positionAmt', 0)) != 0
                }
                
                # 메모리에는 있지만 바이낸스에는 없는 포지션 확인
                for symbol in list(current_positions.keys()):
                    # 🔥 v8.5 Fixed: 신규 포지션 보호 - 진입 후 30초간 체크 안함
                    if symbol in position_entry_times:
                        entry_time = position_entry_times[symbol]
                        elapsed_seconds = (datetime.now() - entry_time).total_seconds()
                        
                        if elapsed_seconds < POSITION_CHECK_DELAY:
                            logger.debug(f"⏳ {symbol} 신규 포지션 보호 중 ({elapsed_seconds:.0f}/{POSITION_CHECK_DELAY}초)")
                            continue
                    
                    # 포지션이 실제로 없어진 경우만 처리
                    if symbol not in actual_symbols:
                        logger.info(f"🔔 {symbol} 포지션 종료 감지 (TP/SL 또는 수동 청산)")
                        
                        # 포지션 데이터 가져오기
                        position_data = current_positions[symbol].copy()
                        
                        # 최종 가격 조회 (현재가)
                        try:
                            ticker = exchange.fetch_ticker(symbol)
                            position_data['mark_price'] = ticker['last']
                        except:
                            position_data['mark_price'] = position_data.get('entry_price', 0)
                        
                        # 실제 PnL 기록 및 이벤트 발생
                        realized_pnl = record_position_closure_with_real_pnl(
                            symbol, 
                            position_data, 
                            close_type='auto_tpsl'  # TP/SL 자동 체결
                        )
                        
                        # 메모리에서 제거
                        del current_positions[symbol]
                        
                        # 🔥 v8.5 Fixed: 포지션 진입 시간도 제거
                        if symbol in position_entry_times:
                            del position_entry_times[symbol]
                            logger.info(f"🗑️ 청산 후 진입 시간 제거: {symbol}")
                        
                        # 텔레그램 알림
                        if ENABLE_TELEGRAM and realized_pnl is not None:
                            pnl_sign = "+" if realized_pnl > 0 else ""
                            message = f"""
🔔 <b>자동 청산 감지</b>

<b>심볼:</b> {symbol}
<b>종료 방식:</b> TP/SL 자동 체결
<b>실현 손익:</b> {pnl_sign}${realized_pnl:.2f} USD
<b>감지 시간:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

💡 바이낸스에서 자동으로 청산되었습니다.
                        """.strip()
                            send_telegram_notification(message, 'info')
                    
            except Exception as e:
                logger.error(f"포지션 종료 감지 오류: {str(e)}")
                time.sleep(5)  # 오류 시 5초 후 재시도
    
    # 백그라운드 스레드로 실행
    monitor_thread = threading.Thread(target=monitor_loop, daemon=True)
    monitor_thread.start()
    logger.info("✅ 포지션 종료 감지 스레드 시작 (10초 간격, 신규 포지션 30초 보호)")

def initialize_bot():
    """봇 초기화 - v8.5 Fixed: 포지션 진입 시간 추적으로 청산 감지 안정성 향상"""
    global bot_start_time, initial_sync_completed, existing_positions_at_start, positions_already_notified, last_position_check, position_entry_times
    
    # 🆕 봇 시작 시간 기록
    bot_start_time = datetime.now()
    initial_sync_completed = False
    existing_positions_at_start = set()  # 🔥 v8.4: 기존 포지션 추적
    positions_already_notified = set()  # 🔥 v8.4: 알림 추적 초기화
    last_position_check = {}  # 🔥 v8.4: 체크 시간 초기화
    position_entry_times = {}  # 🔥 v8.5 Fixed: 포지션 진입 시간 추적 초기화
    
    logger.info(f"봇 초기화 중... (포트: {SERVER_PORT})")
    logger.info(f"🕐 봇 시작 시간: {bot_start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    
    # 데이터베이스 초기화 (프로그램 시작 시 1회)
    init_db_once()
    
    # 거래소 연결 테스트
    try:
        balance = exchange.fetch_balance()
        usdt_balance = balance['USDT']['free']
        logger.info(f"거래소 연결 성공. USDT 잔고: ${usdt_balance:,.2f}")
    except Exception as e:
        logger.error(f"거래소 연결 실패: {str(e)}")
    
    # 🔥 v8.4: 봇 시작시 기존 포지션을 확실하게 추적
    try:
        logger.info("📌 봇 시작시 기존 포지션 확인 중...")
        all_positions = exchange.fetch_positions()
        
        for pos in all_positions:
            symbol = pos['symbol']
            contracts = float(pos.get('contracts', 0))
            
            if contracts != 0 and symbol in SYMBOL_CONFIG:
                existing_positions_at_start.add(symbol)
                side = 'long' if contracts > 0 else 'short'
                entry_price = float(pos.get('entryPrice', 0))
                logger.info(f"📌 기존 포지션 발견: {symbol} ({side} {abs(contracts):.4f} @ ${entry_price:.2f})")
        
        logger.info(f"📌 봇 시작시 기존 포지션: {len(existing_positions_at_start)}개")
        if existing_positions_at_start:
            logger.info(f"📌 기존 포지션 목록: {list(existing_positions_at_start)}")
    except Exception as e:
        logger.error(f"기존 포지션 확인 실패: {str(e)}")
    
    # 🔄 실제 포지션 동기화 (서버 재시작 시 복구)
    try:
        position_count = sync_positions_from_exchange()
        if position_count > 0:
            logger.info(f"✅ {position_count}개의 기존 포지션 복구 완료")
            position_summary = get_position_summary()
            logger.info(f"복구된 포지션:\n{position_summary}")
        else:
            logger.info("복구할 포지션 없음 (새로 시작)")
        
        # 🆕 초기 동기화 완료 표시 (5분 대기 없이 바로 알림 가능)
        initial_sync_completed = True
        logger.info("✅ 초기 포지션 동기화 완료 - 이후 청산 감지 알림 활성화")
        
    except Exception as e:
        logger.error(f"포지션 동기화 실패: {str(e)}")
    
    # AI 모니터링 자동 시작
    start_ai_monitoring()
    
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
    
    # 주기적 데이터 기록 스레드 시작
    def periodic_data_recording():
        """주기적으로 잔고와 포지션 데이터를 기록"""
        while True:
            try:
                # 잔고 스냅샷 (5분마다)
                record_balance_snapshot(exchange)
                
                # 포지션이 있을 때만 히스토리 기록
                if len(current_positions) > 0:
                    record_position_history(exchange)
                
                # 5분 대기
                time.sleep(300)
                
            except Exception as e:
                logger.error(f"주기적 데이터 기록 오류: {str(e)}")
                time.sleep(60)  # 오류 시 1분 후 재시도
    
    # 백그라운드 스레드로 실행
    recording_thread = threading.Thread(target=periodic_data_recording, daemon=True)
    recording_thread.start()
    logger.info("📊 주기적 데이터 기록 스레드 시작 (5분 간격)")
    
    # 🆕 v8.1: 바이낸스 WebSocket 리스너 시작 (실시간 TP/SL 감지)
    try:
        start_binance_websocket_listener()
    except Exception as e:
        logger.warning(f"WebSocket 시작 실패 (폴링 모드로 계속 동작): {str(e)}")
    
    # 🆕 v8.1: 포지션 종료 감지 스레드 시작 (백업)
    start_position_closure_monitor()
    
    if ENABLE_TELEGRAM:
        # 🆕 포지션 타입별 카운트
        auto_count = sum(1 for pos in current_positions.values() if pos.get('position_type', 'auto') == 'auto')
        manual_count = sum(1 for pos in current_positions.values() if pos.get('position_type', 'auto') == 'manual')
        
        position_info = ""
        if len(current_positions) > 0:
            position_info = f"\n\n<b>복구된 포지션:</b>\n{get_position_summary()}"
        
        startup_message = f"""
🚀 <b>통합 트레이딩 시스템 v8.6 Enhanced 시작</b>

<b>🎯 v8.6 Enhanced 신규 기능:</b>
💪 <b>AI 물타기 시스템</b>
  → 손실 구간에서 강력한 반전 신호 포착 시 추가 진입
  → 잔여 마진의 5~30% 투입 (확신도/승률 기반)
  → 평균 진입가 개선으로 수익 전환 가능성 향상
  → AI 판단: 유지/부분청산/전체청산/물타기 (4가지)

<b>✅ v8.5 Fixed - 청산 감지 완벽 해결:</b>
🔥 <b>신규 포지션 30초 보호</b>
  → 포지션 진입 시간 추적 시스템
  → API 지연으로 인한 오감지 완벽 차단
  → 바이낸스 API 3회 재시도 로직

<b>✨ v8.3 Enhanced - 기존 포지션 모니터링:</b>
🤖 <b>봇 시작 전 포지션도 AI 모니터링</b>
  → 기존 포지션 자동 감지 및 추적
  → 모든 포지션에 대해 종료/물타기 시점 분석
  → Manual/Auto 포지션 구분 관리

<b>📊 v7.0 Multi-User 기능 (유지):</b>
👥 다중 유저 동시 거래
🗑️ TP/SL 자동 삭제
🔄 동기화된 거래 실행

<b>📊 v6.0 핵심 기능 (유지):</b>
🎯 과매수/과매도 멀티 타임프레임 필터링
💡 매물대 기반 TP/SL 자동 조정
🚨 추세 역전 조기 신호 감지

<b>⚙️ 서버 정보:</b>
<b>서버 포트:</b> {SERVER_PORT}
<b>활성 유저:</b> {len(exchanges)}명
<b>활성 심볼:</b> {len(enabled_symbols)}개
<b>AI 검증:</b> {len(ai_symbols)}개 심볼
<b>AI 모니터링:</b> {len(ai_monitor_symbols)}개 심볼
<b>현재 포지션:</b> {len(current_positions)}개
  - 🤖 자동: {auto_count}개
  - 🔧 수동: {manual_count}개{position_info}

✅ 시스템이 정상적으로 시작되었습니다.
⚡ WebSocket 실시간 감지 활성화
🔍 백업 폴링 시스템 활성화 (10초, 30초 신규 보호)
💰 바이낸스 실제 PnL 동기화 활성화
📊 실시간 대시보드 연동 준비 완료
🔄 거래소 포지션 자동 동기화 활성화
📊 서버 재시작 시 포지션 자동 복구
💾 주기적 데이터 기록 활성화 (5분)
🎯 AI 물타기 시스템 활성화
🎯 모든 기존 기능 100% 유지

⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
        """.strip()
        send_telegram_notification(startup_message, 'success')

if __name__ == '__main__':
    initialize_bot()
    app.run(host='0.0.0.0', port=SERVER_PORT, debug=False, threaded=True)  # 명시적 멀티스레드 설정