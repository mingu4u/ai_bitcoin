"""
╔═══════════════════════════════════════════════════════════════════════════════╗
║              INTEGRATED TRADING SYSTEM v7.3 RULE-BASED                       ║
║                   Multi-User Crypto Trading Bot                              ║
╠═══════════════════════════════════════════════════════════════════════════════╣
║  Version: 7.3.0                                                              ║
║  Last Updated: 2025-11-28                                                    ║
║  Base Version: v7.2 COMPREHENSIVE                                            ║
╠═══════════════════════════════════════════════════════════════════════════════╣
║                     v7.3 CHANGELOG (RULE-BASED MODE)                         ║
╠═══════════════════════════════════════════════════════════════════════════════╣
║  🎯 핵심 변경: AI 역할 분리 - Rule-Based 검증 + AI 파라미터 조정             ║
║                                                                              ║
║  📊 새로운 아키텍처:                                                         ║
║  ┌─────────────────────────────────────────────────────────────────────┐     ║
║  │  1. 웹훅 Alert 수신                                                 │     ║
║  │         ↓                                                           │     ║
║  │  2. Rule-Based Validation (Python 로직)                            │     ║
║  │     - calculate_risk_score(): 위험 점수 계산                       │     ║
║  │     - calculate_approval_score(): 승인 점수 계산                   │     ║
║  │     - 정확한 수학적 비교 수행                                       │     ║
║  │         ↓                                                           │     ║
║  │  3. AI Parameter Adjustment (DeepSeek)                             │     ║
║  │     - 레버리지: 5~20배 조정                                        │     ║
║  │     - 포지션 사이즈: 10~40% 조정                                   │     ║
║  │     - TP/SL 미세조정                                               │     ║
║  │         ↓                                                           │     ║
║  │  4. 거래 실행                                                       │     ║
║  └─────────────────────────────────────────────────────────────────────┘     ║
║                                                                              ║
║  ✅ 장점:                                                                    ║
║  - 수학적 비교 오류 제거 (Python이 정확히 계산)                              ║
║  - AI 부담 감소 (복잡한 지표 분석 → 간단한 파라미터 조정)                   ║
║  - 일관성 있는 결과                                                         ║
║  - 빠른 처리 속도                                                           ║
║                                                                              ║
║  📈 Risk Score (0-15+):                                                      ║
║  - 0-4: Low Risk → APPROVE 가능                                             ║
║  - 5-7: Medium Risk → MODIFY (축소 진입)                                    ║
║  - 8+: High Risk → REJECT                                                   ║
║                                                                              ║
║  📊 Approval Score (0-100):                                                  ║
║  - 70+: APPROVE 가능                                                        ║
║  - 60-69: MODIFY                                                            ║
║  - <60: REJECT                                                              ║
║                                                                              ║
║  🔧 AI 파라미터 조정 범위:                                                   ║
║  - 레버리지: 5x ~ 20x (Risk Score에 따라)                                   ║
║  - 포지션: 10% ~ 40% (Approval Score에 따라)                                ║
║  - TP/SL: ATR 기반 (1.5~2.5x ATR)                                          ║
║                                                                              ║
║  v7.2 기능 유지:                                                             ║
║  - 모든 바이낸스 포지션 AI 모니터링                                         ║
║  - Peak Profit Tracking 시스템                                               ║
║  - 지지부진 포지션 감지                                                     ║
║  - HTML 특수문자 이스케이프 (텔레그램)                                       ║
╚═══════════════════════════════════════════════════════════════════════════════╝
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
from pydantic import BaseModel, Field, ValidationError, model_validator
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

# ============ AI Decision Models ============
class TradingDecision(BaseModel):
    """트레이딩 시그널 검증용 모델"""
    decision: str = Field(..., pattern="^(approve|reject|modify|reverse)$")  # 'reverse' 추가
    modified_action: str = Field(..., pattern="^(buy|sell|hold)$")
    percentage: int = Field(..., ge=0, le=100)  # reject일 때 0 허용
    reason: str = Field(..., min_length=1)
    stop_loss_price: float = Field(..., ge=0)   # reject일 때 0 허용
    take_profit_price: float = Field(..., ge=0) # reject일 때 0 허용
    pl_ratio: float = Field(..., ge=0, le=10.0) # reject일 때 0 허용, 상한 확장
    confidence: float = Field(..., ge=0.0, le=1.0)
    
    @model_validator(mode='after')
    def validate_non_reject_fields(self):
        """reject가 아닌 경우에만 필수 필드 검증"""
        if self.decision != 'reject':
            if self.percentage < 1:
                raise ValueError(f"percentage must be >= 1 for {self.decision} decision")
            if self.stop_loss_price <= 0:
                raise ValueError(f"stop_loss_price must be > 0 for {self.decision} decision")
            if self.take_profit_price <= 0:
                raise ValueError(f"take_profit_price must be > 0 for {self.decision} decision")
            if self.pl_ratio < 1.0:
                raise ValueError(f"pl_ratio must be >= 1.0 for {self.decision} decision")
        return self

class ClosePositionDecision(BaseModel):
    """청산 시그널 검증용 모델 (SL/TP 불필요)"""
    decision: str = Field(..., pattern="^(approve|reject)$")
    reason: str = Field(..., min_length=1)
    confidence: float = Field(..., ge=0.0, le=1.0)
    urgency: str = Field(..., pattern="^(immediate|soon|normal|low)$")

class PositionExitDecision(BaseModel):
    """포지션 종료 결정용 모델 - v7.1 개선 버전"""
    decision: str = Field(..., pattern="^(hold|close|partial_close)$")
    percentage: int = Field(..., ge=0, le=100)
    reason: str = Field(..., min_length=1)
    exit_type: str = Field(
        ..., 
        pattern="^(take_profit|stop_loss|trend_reversal|risk_management|time_stop|profit_protection|stagnation|none)$"
    )
    confidence: float = Field(..., ge=0.0, le=1.0)
    urgency: str = Field(..., pattern="^(immediate|soon|watch|none)$")

# 🆕 JSON 파싱 오류 시 AI 복구용 모델
class EmergencyTradingDecision(BaseModel):
    """JSON 파싱 오류 시 AI가 자동으로 파라미터를 설정"""
    percentage: int = Field(..., ge=1, le=100)
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

# 🆕 v7.3: 심볼 정규화 함수
def normalize_symbol(symbol: str) -> str:
    """
    ccxt 선물 심볼을 표준 형식으로 정규화
    
    Examples:
        'BTC/USDT:USDT' → 'BTC/USDT'
        'OG/USDT:USDT' → 'OG/USDT'
        'ETH/USDT' → 'ETH/USDT' (이미 정규화됨)
    """
    if ':' in symbol:
        # 'BTC/USDT:USDT' → 'BTC/USDT'
        return symbol.split(':')[0]
    return symbol


def get_symbol_config(symbol: str) -> dict:
    """
    🆕 v7.3: 정규화된 심볼로 SYMBOL_CONFIG 조회
    
    Args:
        symbol: 원본 심볼 (예: 'BTC/USDT:USDT' 또는 'BTC/USDT')
    
    Returns:
        dict: 심볼 설정 또는 빈 딕셔너리
    """
    normalized = normalize_symbol(symbol)
    return SYMBOL_CONFIG.get(normalized, {})


def is_symbol_configured(symbol: str) -> bool:
    """
    🆕 v7.3: 심볼이 SYMBOL_CONFIG에 정의되어 있는지 확인
    """
    normalized = normalize_symbol(symbol)
    return normalized in SYMBOL_CONFIG


# 기본 설정
DEFAULT_POSITION_SIZE_PERCENT = float(os.getenv('POSITION_SIZE_PERCENT', 10))
DEFAULT_TRAILING_STOP_PERCENT = 3.0
DEFAULT_TRAILING_ACTIVATION_PERCENT = 1.5

# 현재 포지션 추적을 위한 딕셔너리
current_positions = {}

# 🆕 v7.1 Peak Profit Tracking
position_peak_profits = {}  # {symbol: {'peak_pnl': float, 'peak_time': datetime, 'peak_price': float}}

def update_peak_profit(symbol, current_pnl, current_price):
    """포지션의 최고 수익률 추적 - v7.1"""
    global position_peak_profits
    
    if symbol not in position_peak_profits:
        position_peak_profits[symbol] = {
            'peak_pnl': current_pnl,
            'peak_time': datetime.now(),
            'peak_price': current_price
        }
    elif current_pnl > position_peak_profits[symbol]['peak_pnl']:
        position_peak_profits[symbol] = {
            'peak_pnl': current_pnl,
            'peak_time': datetime.now(),
            'peak_price': current_price
        }
    return position_peak_profits[symbol]

def get_profit_drawdown(symbol, current_pnl):
    """최고 수익 대비 현재 수익 하락률 계산 - v7.1"""
    global position_peak_profits
    
    if symbol not in position_peak_profits:
        return 0
    
    peak_pnl = position_peak_profits[symbol]['peak_pnl']
    if peak_pnl <= 0:
        return 0
    
    # 최고점 대비 하락률 (%)
    drawdown = ((peak_pnl - current_pnl) / peak_pnl) * 100
    return max(0, drawdown)

def clear_peak_profit(symbol):
    """포지션 종료 시 peak profit 기록 삭제 - v7.1"""
    global position_peak_profits
    if symbol in position_peak_profits:
        del position_peak_profits[symbol]
        logger.info(f"🗑️ {symbol} peak profit 기록 삭제")

# 모니터링 스레드 관리
position_monitor_threads = {}
ai_monitor_thread = None
ai_monitor_running = False

# ============ Position Sync Functions ============
def sync_positions_from_exchange():
    """
    거래소의 실제 포지션을 current_positions와 동기화
    🆕 v7.2 개선: SYMBOL_CONFIG에 없는 심볼도 포함한 모든 포지션 동기화
    - 바이낸스의 모든 활성 포지션 조회
    - 수동 포지션 자동 감지 및 AI 모니터링 대상 추가
    """
    global current_positions
    
    try:
        logger.info("=== 거래소 포지션 동기화 시작 (모든 포지션 스캔) ===")
        
        synced_count = 0
        manual_count = 0
        new_positions = {}
        
        # 🆕 v7.2: 바이낸스에서 모든 포지션 조회 (SYMBOL_CONFIG 제한 없이)
        try:
            all_positions = exchange.fetch_positions()
            logger.info(f"📊 바이낸스에서 {len(all_positions)}개 심볼 포지션 정보 조회")
        except Exception as e:
            logger.error(f"전체 포지션 조회 실패: {e}")
            # 실패 시 기존 방식으로 폴백
            all_positions = []
            for symbol in SYMBOL_CONFIG.keys():
                if SYMBOL_CONFIG[symbol].get('enabled', True):
                    try:
                        positions = exchange.fetch_positions([symbol])
                        all_positions.extend(positions)
                    except:
                        continue
        
        # 모든 포지션 처리
        for position in all_positions:
            try:
                contracts = float(position.get('contracts', 0))
                
                if contracts == 0:  # 포지션 없음
                    continue
                    
                raw_symbol = position.get('symbol', '')
                if not raw_symbol:
                    continue
                
                # 🆕 v7.3: 심볼 정규화 (OG/USDT:USDT → OG/USDT)
                symbol = normalize_symbol(raw_symbol)
                
                entry_price = float(position.get('entryPrice', 0))
                side = 'buy' if position['side'] == 'long' else 'sell'
                
                # 🆕 v7.3: 정규화된 심볼로 SYMBOL_CONFIG 확인
                is_configured = is_symbol_configured(symbol)
                symbol_config = get_symbol_config(symbol)
                
                # 기존 포지션 정보가 있으면 유지, 없으면 새로 생성
                if symbol in current_positions:
                    # 기존 정보 유지 (SL/TP, position_type 등)
                    new_positions[symbol] = current_positions[symbol]
                    # 수량과 진입가는 거래소 기준으로 업데이트
                    new_positions[symbol]['amount'] = abs(contracts)
                    new_positions[symbol]['entry_price'] = entry_price
                    pos_type = new_positions[symbol].get('position_type', 'auto')
                    type_emoji = "🤖" if pos_type == 'auto' else "🔧"
                    logger.info(f"{type_emoji} {symbol} 포지션 업데이트: {side} {abs(contracts):.4f} @ ${entry_price:.2f} ({pos_type.upper()})")
                else:
                    # 🆕 새로운 포지션 발견 → 수동 포지션으로 간주
                    # SYMBOL_CONFIG에 없어도 기본 설정으로 모니터링
                    default_leverage = symbol_config.get('leverage', 10)
                    
                    new_positions[symbol] = {
                        'side': side,
                        'entry_price': entry_price,
                        'amount': abs(contracts),
                        'stop_loss': 0,
                        'take_profit': 0,
                        'trailing_stop_percent': DEFAULT_TRAILING_STOP_PERCENT,
                        'trailing_activation_percent': DEFAULT_TRAILING_ACTIVATION_PERCENT,
                        'entry_time': datetime.now(),
                        'position_type': 'manual',  # 수동 포지션
                        'leverage': default_leverage,
                        'is_configured': is_configured  # SYMBOL_CONFIG 존재 여부
                    }
                    
                    config_status = "✓ CONFIG" if is_configured else "⚠️ NO CONFIG"
                    logger.info(f"🆕🔧 {symbol} 수동 포지션 발견: {side} {abs(contracts):.4f} @ ${entry_price:.2f} [{config_status}]")
                    logger.info(f"   → AI 모니터링 대상에 자동 추가됨")
                    synced_count += 1
                    manual_count += 1
                    
                    # 🆕 v7.3: 정규화된 심볼로 SYMBOL_CONFIG에 동적 추가
                    if not is_configured:
                        logger.warning(f"⚠️ {symbol}이 SYMBOL_CONFIG에 없음 - 기본 설정으로 모니터링")
                        # 동적으로 기본 설정 추가 (정규화된 심볼 사용)
                        SYMBOL_CONFIG[symbol] = {
                            'enabled': True,
                            'leverage': default_leverage,
                            'position_size_percent': 30,
                            'take_profit_percent': 2.0,
                            'stop_loss_percent': 1.5,
                            'ai_monitoring': True,  # AI 모니터링 활성화
                            'dynamic_added': True   # 동적 추가 표시
                        }
                        logger.info(f"   → SYMBOL_CONFIG에 동적 추가 완료 (정규화: {raw_symbol} → {symbol})")
                    
                    # 텔레그램 알림
                    if ENABLE_TELEGRAM:
                        config_msg = "⚠️ SYMBOL_CONFIG에 없음 (기본 설정 적용)" if not is_configured else "✓ CONFIG 존재"
                        send_telegram_notification(
                            f"🔧 <b>수동 포지션 감지</b>\n\n"
                            f"<b>심볼:</b> {symbol}\n"
                            f"<b>방향:</b> {side.upper()}\n"
                            f"<b>진입가:</b> ${entry_price:,.2f}\n"
                            f"<b>수량:</b> {abs(contracts):.4f}\n"
                            f"<b>레버리지:</b> {default_leverage}x\n"
                            f"<b>설정:</b> {config_msg}\n\n"
                            f"✅ AI 모니터링이 자동으로 시작됩니다.\n"
                            f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                            'info'
                        )
                        
            except Exception as e:
                logger.error(f"포지션 처리 오류: {e}")
                continue
        
        # 동기화 완료 - 메모리에 없지만 거래소에 있는 포지션 추가
        for symbol, pos_info in new_positions.items():
            if symbol not in current_positions:
                current_positions[symbol] = pos_info
        
        # 메모리에는 있지만 거래소에 없는 포지션 제거 및 DB 기록
        removed_symbols = []
        for symbol in list(current_positions.keys()):
            if symbol not in new_positions:
                # 종료된 포지션을 completed_trades에 기록
                try:
                    ticker = exchange.fetch_ticker(symbol)
                    exit_price = ticker['last']
                    position_info = current_positions[symbol]
                    record_completed_trade(symbol, position_info, exit_price, 'sync_detected_close')
                    logger.info(f"✅ Closed position recorded for {symbol} (detected by sync)")
                except Exception as e:
                    logger.error(f"Failed to record closed position for {symbol}: {e}")
                
                removed_symbols.append(symbol)
                del current_positions[symbol]
                clear_peak_profit(symbol)
                logger.warning(f"⚠️ {symbol} 포지션이 거래소에 없어 메모리에서 제거 및 DB 기록")
        
        # 동기화 결과 로깅
        auto_count = sum(1 for pos in current_positions.values() if pos.get('position_type', 'auto') == 'auto')
        manual_total = sum(1 for pos in current_positions.values() if pos.get('position_type', 'auto') == 'manual')
        configured_count = sum(1 for pos in current_positions.values() if pos.get('is_configured', True))
        dynamic_count = len(current_positions) - configured_count
        
        logger.info(f"=== 동기화 완료 ===")
        logger.info(f"총 포지션: {len(current_positions)}개")
        logger.info(f"  - 자동(AI) 포지션: {auto_count}개")
        logger.info(f"  - 수동 포지션: {manual_total}개 (이번 사이클: {manual_count}개)")
        logger.info(f"  - CONFIG 있음: {configured_count}개")
        logger.info(f"  - 동적 추가: {dynamic_count}개")
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
        # 🆕 기존 테이블에 position_type 컬럼이 없으면 추가 (마이그레이션)
        try:
            c.execute("SELECT position_type FROM completed_trades LIMIT 1")
        except sqlite3.OperationalError:
            logger.info("🔧 completed_trades 테이블에 position_type 컬럼 추가 중...")
            c.execute("ALTER TABLE completed_trades ADD COLUMN position_type TEXT DEFAULT 'auto'")
            conn.commit()
            logger.info("✅ position_type 컬럼 추가 완료")
        
        # 🆕 v7.1 대시보드 호환: realized_pnl_binance 컬럼 추가
        try:
            c.execute("SELECT realized_pnl_binance FROM completed_trades LIMIT 1")
        except sqlite3.OperationalError:
            logger.info("🔧 completed_trades 테이블에 realized_pnl_binance 컬럼 추가 중...")
            c.execute("ALTER TABLE completed_trades ADD COLUMN realized_pnl_binance REAL DEFAULT NULL")
            conn.commit()
            logger.info("✅ realized_pnl_binance 컬럼 추가 완료 (대시보드 호환)")
        
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
    
    # 2. 완료된 거래 테이블 (대시보드용, 🆕 position_type 컬럼 추가)
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
                  realized_pnl_binance REAL DEFAULT NULL)''')
    
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

# ============ 🆕 v7.1 강화된 과매수/과매도 필터링 함수 ============
def check_overbought_oversold_multi_timeframe(df_15min, df_hourly, df_4h, action):
    """
    🆕 v7.1 강화된 멀티 타임프레임 과매수/과매도 체크
    
    주요 개선사항:
    - 더 엄격한 RSI 기준 (75/25)
    - 멀티 타임프레임 Stochastic 분석 추가
    - Williams %R 극단값 체크 추가
    - CMF 반대 신호 (매수인데 자금유출, 매도인데 자금유입) 체크
    - MACD/DI 크로스 실시간 감지
    - 볼린저 밴드 멀티 타임프레임 확인
    - 반대 진입 기준 완화 (2개 신호 또는 강도 5점 이상)
    
    Returns:
        dict: 과매수/과매도 분석 결과
    """
    warnings = []
    risk_scores = []
    reverse_signals = []
    reverse_strength_points = 0  # 🆕 반대 진입 강도 점수
    
    # ===== RSI 체크 (더 세분화된 기준) =====
    rsi_15m = df_15min['rsi'].iloc[-1]
    rsi_1h = df_hourly['rsi'].iloc[-1]
    rsi_4h = df_4h['rsi'].iloc[-1]
    
    # 15분봉 RSI
    if action == 'buy':
        if rsi_15m > 75:
            warnings.append(f"⚠️ 15분봉 RSI 과매수 ({rsi_15m:.1f})")
            risk_scores.append(3)
            reverse_signals.append("15m_RSI_overbought")
            reverse_strength_points += 1
            if rsi_15m > 80:
                reverse_signals.append("15m_RSI_extreme_overbought")
                reverse_strength_points += 2
        elif rsi_15m > 65:
            risk_scores.append(1)
    elif action == 'sell':
        if rsi_15m < 25:
            warnings.append(f"⚠️ 15분봉 RSI 과매도 ({rsi_15m:.1f})")
            risk_scores.append(3)
            reverse_signals.append("15m_RSI_oversold")
            reverse_strength_points += 1
            if rsi_15m < 20:
                reverse_signals.append("15m_RSI_extreme_oversold")
                reverse_strength_points += 2
        elif rsi_15m < 35:
            risk_scores.append(1)
    
    # 1시간봉 RSI (더 중요)
    if action == 'buy':
        if rsi_1h > 70:
            warnings.append(f"🔴 1시간봉 RSI 과매수 ({rsi_1h:.1f})")
            risk_scores.append(4)
            reverse_signals.append("1h_RSI_overbought")
            reverse_strength_points += 2
            if rsi_1h > 80:
                reverse_signals.append("1h_RSI_extreme_overbought")
                reverse_strength_points += 3
        elif rsi_1h > 60:
            risk_scores.append(2)
    elif action == 'sell':
        if rsi_1h < 30:
            warnings.append(f"🔴 1시간봉 RSI 과매도 ({rsi_1h:.1f})")
            risk_scores.append(4)
            reverse_signals.append("1h_RSI_oversold")
            reverse_strength_points += 2
            if rsi_1h < 20:
                reverse_signals.append("1h_RSI_extreme_oversold")
                reverse_strength_points += 3
        elif rsi_1h < 40:
            risk_scores.append(2)
    
    # 4시간봉 RSI (가장 중요)
    if action == 'buy':
        if rsi_4h > 70:
            warnings.append(f"🔴 4시간봉 RSI 과매수 ({rsi_4h:.1f})")
            risk_scores.append(5)
            reverse_signals.append("4h_RSI_overbought")
            reverse_strength_points += 3
            if rsi_4h > 80:
                reverse_signals.append("4h_RSI_extreme_overbought")
                reverse_strength_points += 4
        elif rsi_4h > 60:
            risk_scores.append(2)
    elif action == 'sell':
        if rsi_4h < 30:
            warnings.append(f"🔴 4시간봉 RSI 과매도 ({rsi_4h:.1f})")
            risk_scores.append(5)
            reverse_signals.append("4h_RSI_oversold")
            reverse_strength_points += 3
            if rsi_4h < 20:
                reverse_signals.append("4h_RSI_extreme_oversold")
                reverse_strength_points += 4
        elif rsi_4h < 40:
            risk_scores.append(2)
    
    # ===== Stochastic 체크 =====
    stoch_k_15m = df_15min['stoch_k'].iloc[-1] if 'stoch_k' in df_15min.columns else 50
    stoch_k_1h = df_hourly['stoch_k'].iloc[-1] if 'stoch_k' in df_hourly.columns else 50
    
    if action == 'buy':
        if stoch_k_15m > 85 and stoch_k_1h > 80:
            warnings.append(f"⚠️ Stochastic 멀티 타임프레임 과매수 (15m: {stoch_k_15m:.1f}, 1h: {stoch_k_1h:.1f})")
            risk_scores.append(3)
            reverse_signals.append("stoch_multi_overbought")
            reverse_strength_points += 2
        elif stoch_k_1h > 90:
            reverse_signals.append("stoch_1h_extreme_overbought")
            reverse_strength_points += 2
    elif action == 'sell':
        if stoch_k_15m < 15 and stoch_k_1h < 20:
            warnings.append(f"⚠️ Stochastic 멀티 타임프레임 과매도 (15m: {stoch_k_15m:.1f}, 1h: {stoch_k_1h:.1f})")
            risk_scores.append(3)
            reverse_signals.append("stoch_multi_oversold")
            reverse_strength_points += 2
        elif stoch_k_1h < 10:
            reverse_signals.append("stoch_1h_extreme_oversold")
            reverse_strength_points += 2
    
    # ===== Williams %R 체크 =====
    williams_15m = df_15min['williams_r'].iloc[-1] if 'williams_r' in df_15min.columns else -50
    williams_1h = df_hourly['williams_r'].iloc[-1] if 'williams_r' in df_hourly.columns else -50
    
    if action == 'buy':
        if williams_15m > -10 and williams_1h > -20:
            warnings.append(f"⚠️ Williams %R 극단적 과매수 (15m: {williams_15m:.1f}, 1h: {williams_1h:.1f})")
            reverse_signals.append("williams_extreme_overbought")
            reverse_strength_points += 2
            risk_scores.append(2)
    elif action == 'sell':
        if williams_15m < -90 and williams_1h < -80:
            warnings.append(f"⚠️ Williams %R 극단적 과매도 (15m: {williams_15m:.1f}, 1h: {williams_1h:.1f})")
            reverse_signals.append("williams_extreme_oversold")
            reverse_strength_points += 2
            risk_scores.append(2)
    
    # ===== 볼린저 밴드 체크 =====
    current_price = df_15min['close'].iloc[-1]
    bb_upper_15m = df_15min['bb_bbh'].iloc[-1]
    bb_lower_15m = df_15min['bb_bbl'].iloc[-1]
    bb_upper_1h = df_hourly['bb_bbh'].iloc[-1]
    bb_lower_1h = df_hourly['bb_bbl'].iloc[-1]
    
    if action == 'buy':
        if current_price > bb_upper_15m and current_price > bb_upper_1h:
            warnings.append(f"🔴 멀티 타임프레임 볼린저 상단 돌파 (가격 과열)")
            risk_scores.append(4)
            reverse_signals.append("bb_multi_overbought")
            reverse_strength_points += 3
        elif current_price > bb_upper_15m:
            warnings.append(f"⚠️ 15분봉 볼린저 상단 돌파")
            risk_scores.append(2)
            reverse_signals.append("bb_15m_overbought")
            reverse_strength_points += 1
    elif action == 'sell':
        if current_price < bb_lower_15m and current_price < bb_lower_1h:
            warnings.append(f"🔴 멀티 타임프레임 볼린저 하단 돌파 (가격 침체)")
            risk_scores.append(4)
            reverse_signals.append("bb_multi_oversold")
            reverse_strength_points += 3
        elif current_price < bb_lower_15m:
            warnings.append(f"⚠️ 15분봉 볼린저 하단 돌파")
            risk_scores.append(2)
            reverse_signals.append("bb_15m_oversold")
            reverse_strength_points += 1
    
    # ===== CMF (Money Flow) 반대 신호 체크 =====
    cmf_15m = df_15min['cmf'].iloc[-1] if 'cmf' in df_15min.columns else 0
    cmf_1h = df_hourly['cmf'].iloc[-1] if 'cmf' in df_hourly.columns else 0
    
    if action == 'buy':
        # 매수 신호인데 자금이 유출 중
        if cmf_15m < -0.1 and cmf_1h < -0.05:
            warnings.append(f"⚠️ CMF 음수 (자금 유출 중 - 매수에 불리)")
            reverse_signals.append("cmf_negative_divergence")
            reverse_strength_points += 2
            risk_scores.append(2)
    elif action == 'sell':
        # 매도 신호인데 자금이 유입 중
        if cmf_15m > 0.1 and cmf_1h > 0.05:
            warnings.append(f"⚠️ CMF 양수 (자금 유입 중 - 매도에 불리)")
            reverse_signals.append("cmf_positive_divergence")
            reverse_strength_points += 2
            risk_scores.append(2)
    
    # ===== MACD 다이버전스 체크 =====
    macd_1h = df_hourly['macd'].iloc[-1]
    macd_signal_1h = df_hourly['macd_signal'].iloc[-1]
    macd_prev_1h = df_hourly['macd'].iloc[-2]
    macd_signal_prev_1h = df_hourly['macd_signal'].iloc[-2]
    
    if action == 'buy':
        # 매수 신호인데 MACD가 데드크로스
        if macd_1h < macd_signal_1h and macd_prev_1h >= macd_signal_prev_1h:
            warnings.append(f"🔴 1H MACD 데드크로스 발생 (매수 위험!)")
            reverse_signals.append("macd_1h_death_cross")
            reverse_strength_points += 3
            risk_scores.append(4)
    elif action == 'sell':
        # 매도 신호인데 MACD가 골든크로스
        if macd_1h > macd_signal_1h and macd_prev_1h <= macd_signal_prev_1h:
            warnings.append(f"🔴 1H MACD 골든크로스 발생 (매도 위험!)")
            reverse_signals.append("macd_1h_golden_cross")
            reverse_strength_points += 3
            risk_scores.append(4)
    
    # ===== ADX/DI 추세 강도 체크 =====
    adx_1h = df_hourly['adx'].iloc[-1] if 'adx' in df_hourly.columns else 25
    di_plus_1h = df_hourly['di_plus'].iloc[-1] if 'di_plus' in df_hourly.columns else 25
    di_minus_1h = df_hourly['di_minus'].iloc[-1] if 'di_minus' in df_hourly.columns else 25
    
    if action == 'buy':
        # 매수인데 DI-가 DI+ 보다 크게 우세
        if di_minus_1h > di_plus_1h + 10 and adx_1h > 25:
            warnings.append(f"🔴 강한 하락 추세 중 (DI-: {di_minus_1h:.1f} > DI+: {di_plus_1h:.1f})")
            reverse_signals.append("di_strong_bearish")
            reverse_strength_points += 3
            risk_scores.append(4)
    elif action == 'sell':
        # 매도인데 DI+가 DI- 보다 크게 우세
        if di_plus_1h > di_minus_1h + 10 and adx_1h > 25:
            warnings.append(f"🔴 강한 상승 추세 중 (DI+: {di_plus_1h:.1f} > DI-: {di_minus_1h:.1f})")
            reverse_signals.append("di_strong_bullish")
            reverse_strength_points += 3
            risk_scores.append(4)
    
    # ===== 최종 계산 =====
    total_risk = sum(risk_scores)
    
    # 🆕 반대 진입 기회 판단 (기준 완화: 2개 신호 또는 강도 5점 이상)
    reverse_opportunity = False
    reverse_strength = min(reverse_strength_points / 15, 1.0)  # 0-1 정규화
    
    if len(reverse_signals) >= 2 or reverse_strength_points >= 5:
        reverse_opportunity = True
        warnings.append(f"🔄 **반대 진입 기회 감지!** (신호: {len(reverse_signals)}개, 강도: {reverse_strength:.1%})")
        logger.warning(f"🔄 반대 진입 기회 감지 - {action} 대신 {'sell' if action == 'buy' else 'buy'} 고려")
        logger.warning(f"   감지된 신호: {', '.join(reverse_signals)}")
    
    # 리스크 레벨 결정
    if reverse_opportunity and reverse_strength_points >= 8:
        risk_level = 'extreme'
        is_risky = True
    elif total_risk >= 10 or reverse_strength_points >= 6:
        risk_level = 'high'
        is_risky = True
    elif total_risk >= 6:
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
            'stoch_15m': stoch_k_15m,
            'stoch_1h': stoch_k_1h,
            'williams_15m': williams_15m,
            'cmf_15m': cmf_15m,
            'cmf_1h': cmf_1h
        },
        'reverse_opportunity': reverse_opportunity,
        'reverse_signals': reverse_signals,
        'reverse_strength': reverse_strength,
        'reverse_strength_points': reverse_strength_points
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

# 🆕 v7.1 강화된 detect_early_reversal_signals 함수
def detect_early_reversal_signals(df_15min, df_hourly, df_4h, position_side, current_price, entry_price, pnl_percent=0, holding_minutes=0):
    """
    🆕 v7.1 강화된 추세 역전 조기 감지
    
    주요 개선사항:
    - 지지부진 포지션 감지 (30분+ 보유, <1% 수익)
    - 수익 되돌림 감지
    - 더 민감한 역전 신호 감지 (임계값 완화)
    - RSI/MACD/ADX/CMF 종합 분석
    
    Args:
        pnl_percent: 현재 수익률 (레버리지 적용)
        holding_minutes: 보유 시간 (분)
    
    Returns:
        dict: 역전 신호 분석 결과
    """
    signals = []
    reversal_score = 0
    
    # ===== 1. 지지부진/시간 기반 판단 (🆕 핵심 추가) =====
    profit_risk = {
        'is_stagnant': False,
        'is_declining': False,
        'time_inefficiency': False
    }
    
    # 지지부진 포지션 감지 (30분 이상 보유, 수익률 1% 미만)
    if holding_minutes >= 30 and abs(pnl_percent) < 1.0:
        signals.append(f"⏰ 지지부진 포지션 ({holding_minutes:.0f}분 보유, {pnl_percent:+.2f}%)")
        reversal_score += 3
        profit_risk['is_stagnant'] = True
    
    # 오래 보유한데 수익이 미미한 경우 (60분 이상, 1.5% 미만)
    if holding_minutes >= 60 and abs(pnl_percent) < 1.5:
        signals.append(f"⚠️ 장시간 미미한 수익 ({holding_minutes:.0f}분, {pnl_percent:+.2f}%)")
        reversal_score += 2
        profit_risk['time_inefficiency'] = True
    
    # 2시간 이상 보유 시 더 엄격한 기준
    if holding_minutes >= 120 and pnl_percent < 2.0:
        signals.append(f"🔴 2시간+ 보유 저성과 ({pnl_percent:+.2f}%)")
        reversal_score += 3
    
    # ===== 2. RSI Divergence 감지 =====
    try:
        recent_prices_15m = df_15min['close'].tail(10).values
        recent_rsi_15m = df_15min['rsi'].tail(10).values
        recent_prices_1h = df_hourly['close'].tail(5).values
        recent_rsi_1h = df_hourly['rsi'].tail(5).values
        
        if position_side == 'buy':
            # 15분 Bearish Divergence
            if recent_prices_15m[-1] > recent_prices_15m[-5] and recent_rsi_15m[-1] < recent_rsi_15m[-5]:
                rsi_level = recent_rsi_15m[-1]
                if rsi_level > 65:
                    signals.append(f"🔴 15분 Bearish Divergence (과매수권 RSI: {rsi_level:.1f})")
                    reversal_score += 5
                else:
                    signals.append(f"⚠️ 15분 Bearish Divergence (RSI: {rsi_level:.1f})")
                    reversal_score += 3
            
            # 1시간 Bearish Divergence
            if len(recent_prices_1h) >= 3 and len(recent_rsi_1h) >= 3:
                if recent_prices_1h[-1] > recent_prices_1h[-3] and recent_rsi_1h[-1] < recent_rsi_1h[-3]:
                    signals.append(f"🔴 1시간 Bearish Divergence")
                    reversal_score += 4
                    
        else:  # sell
            if recent_prices_15m[-1] < recent_prices_15m[-5] and recent_rsi_15m[-1] > recent_rsi_15m[-5]:
                rsi_level = recent_rsi_15m[-1]
                if rsi_level < 35:
                    signals.append(f"🔴 15분 Bullish Divergence (과매도권 RSI: {rsi_level:.1f})")
                    reversal_score += 5
                else:
                    signals.append(f"⚠️ 15분 Bullish Divergence (RSI: {rsi_level:.1f})")
                    reversal_score += 3
            
            if len(recent_prices_1h) >= 3 and len(recent_rsi_1h) >= 3:
                if recent_prices_1h[-1] < recent_prices_1h[-3] and recent_rsi_1h[-1] > recent_rsi_1h[-3]:
                    signals.append(f"🔴 1시간 Bullish Divergence")
                    reversal_score += 4
                    
    except Exception as e:
        logger.debug(f"Divergence 감지 오류: {e}")
    
    # ===== 3. MACD 신호 =====
    try:
        macd_15m = df_15min['macd'].iloc[-1]
        macd_signal_15m = df_15min['macd_signal'].iloc[-1]
        macd_hist_15m = df_15min['macd_diff'].iloc[-1] if 'macd_diff' in df_15min.columns else macd_15m - macd_signal_15m
        macd_hist_prev = df_15min['macd_diff'].iloc[-2] if 'macd_diff' in df_15min.columns else df_15min['macd'].iloc[-2] - df_15min['macd_signal'].iloc[-2]
        
        macd_1h = df_hourly['macd'].iloc[-1]
        macd_signal_1h = df_hourly['macd_signal'].iloc[-1]
        
        if position_side == 'buy':
            # 모멘텀 급격히 약화 (히스토그램 30% 이상 감소)
            if macd_hist_15m > 0 and macd_hist_prev > 0 and macd_hist_15m < macd_hist_prev * 0.7:
                signals.append("⚠️ MACD 모멘텀 급격히 약화 (30%+ 감소)")
                reversal_score += 3
            elif macd_hist_15m > 0 and macd_hist_15m < macd_hist_prev:
                signals.append("📉 MACD 모멘텀 약화 중")
                reversal_score += 1
            
            # 15분 데드크로스 임박
            macd_gap = macd_15m - macd_signal_15m
            if macd_15m != 0 and 0 < macd_gap < abs(macd_15m) * 0.1:
                signals.append("🔴 15분 MACD 데드크로스 임박!")
                reversal_score += 4
            
            # 1시간 데드크로스
            if macd_1h < macd_signal_1h and df_hourly['macd'].iloc[-2] >= df_hourly['macd_signal'].iloc[-2]:
                signals.append("🔴🔴 1시간 MACD 데드크로스 발생!")
                reversal_score += 5
                
        else:  # sell
            if macd_hist_15m < 0 and macd_hist_prev < 0 and macd_hist_15m > macd_hist_prev * 0.7:
                signals.append("⚠️ MACD 모멘텀 급격히 약화 (30%+ 감소)")
                reversal_score += 3
            elif macd_hist_15m < 0 and macd_hist_15m > macd_hist_prev:
                signals.append("📉 MACD 모멘텀 약화 중")
                reversal_score += 1
            
            macd_gap = macd_signal_15m - macd_15m
            if macd_15m != 0 and 0 < macd_gap < abs(macd_15m) * 0.1:
                signals.append("🔴 15분 MACD 골든크로스 임박!")
                reversal_score += 4
            
            if macd_1h > macd_signal_1h and df_hourly['macd'].iloc[-2] <= df_hourly['macd_signal'].iloc[-2]:
                signals.append("🔴🔴 1시간 MACD 골든크로스 발생!")
                reversal_score += 5
                
    except Exception as e:
        logger.debug(f"MACD 분석 오류: {e}")
    
    # ===== 4. ADX 및 DI 크로스 =====
    try:
        adx_1h = df_hourly['adx'].iloc[-1]
        adx_prev = df_hourly['adx'].iloc[-2]
        di_plus_1h = df_hourly['di_plus'].iloc[-1]
        di_minus_1h = df_hourly['di_minus'].iloc[-1]
        di_plus_prev = df_hourly['di_plus'].iloc[-2]
        di_minus_prev = df_hourly['di_minus'].iloc[-2]
        
        # 추세 강도 약화 (ADX 25 하향 돌파)
        if adx_1h < adx_prev and adx_prev > 25 and adx_1h < 25:
            signals.append("⚠️ ADX 25 하향 돌파 (추세 약화)")
            reversal_score += 3
        elif adx_1h < adx_prev and adx_1h < 20:
            signals.append("📉 ADX 약화 중 (추세력 감소)")
            reversal_score += 1
        
        # DI 크로스오버
        if position_side == 'buy':
            if di_minus_1h > di_plus_1h and di_minus_prev <= di_plus_prev:
                signals.append("🔴🔴 DI 크로스오버! (매도 우세 전환)")
                reversal_score += 5
            elif di_minus_1h > di_plus_1h:
                signals.append("⚠️ DI- > DI+ (하락 압력)")
                reversal_score += 2
        else:
            if di_plus_1h > di_minus_1h and di_plus_prev <= di_minus_prev:
                signals.append("🔴🔴 DI 크로스오버! (매수 우세 전환)")
                reversal_score += 5
            elif di_plus_1h > di_minus_1h:
                signals.append("⚠️ DI+ > DI- (상승 압력)")
                reversal_score += 2
                
    except Exception as e:
        logger.debug(f"ADX 분석 오류: {e}")
    
    # ===== 5. CMF 자금 흐름 반전 =====
    try:
        cmf_1h = df_hourly['cmf'].iloc[-1]
        cmf_prev = df_hourly['cmf'].iloc[-2]
        cmf_15m = df_15min['cmf'].iloc[-1]
        
        if position_side == 'buy':
            # 자금 유출 전환
            if cmf_1h < 0 and cmf_prev >= 0:
                signals.append("🔴 CMF 음수 전환 (자금 유출 시작!)")
                reversal_score += 4
            elif cmf_1h < -0.1 and cmf_15m < -0.1:
                signals.append("⚠️ 멀티 타임프레임 자금 유출")
                reversal_score += 2
        else:
            if cmf_1h > 0 and cmf_prev <= 0:
                signals.append("🔴 CMF 양수 전환 (자금 유입 시작!)")
                reversal_score += 4
            elif cmf_1h > 0.1 and cmf_15m > 0.1:
                signals.append("⚠️ 멀티 타임프레임 자금 유입")
                reversal_score += 2
                
    except Exception as e:
        logger.debug(f"CMF 분석 오류: {e}")
    
    # ===== 6. 볼린저 밴드 이탈 후 복귀 =====
    try:
        current_price_15m = df_15min['close'].iloc[-1]
        prev_price_15m = df_15min['close'].iloc[-2]
        bb_upper = df_15min['bb_bbh'].iloc[-1]
        bb_lower = df_15min['bb_bbl'].iloc[-1]
        bb_middle = df_15min['bb_bbm'].iloc[-1]
        
        if position_side == 'buy':
            # 상단 밴드에서 복귀
            if prev_price_15m > bb_upper and current_price_15m < bb_upper:
                signals.append("⚠️ BB 상단 이탈 후 복귀 (과열 해소)")
                reversal_score += 2
            # 중간선 하향 돌파
            if prev_price_15m > bb_middle and current_price_15m < bb_middle:
                signals.append("📉 BB 중간선 하향 돌파")
                reversal_score += 1
        else:
            if prev_price_15m < bb_lower and current_price_15m > bb_lower:
                signals.append("⚠️ BB 하단 이탈 후 복귀 (침체 해소)")
                reversal_score += 2
            if prev_price_15m < bb_middle and current_price_15m > bb_middle:
                signals.append("📈 BB 중간선 상향 돌파")
                reversal_score += 1
                
    except Exception as e:
        logger.debug(f"볼린저 분석 오류: {e}")
    
    # ===== 7. RSI 과열권 탈출 =====
    try:
        rsi_15m = df_15min['rsi'].iloc[-1]
        rsi_prev_15m = df_15min['rsi'].iloc[-2]
        
        if position_side == 'buy':
            # 과매수권(70+)에서 탈출
            if rsi_prev_15m > 70 and rsi_15m < 70:
                signals.append("⚠️ RSI 과매수권 이탈 (70 하향)")
                reversal_score += 3
            # RSI 50 하향 돌파
            if rsi_prev_15m > 50 and rsi_15m < 50:
                signals.append("📉 RSI 50선 하향 돌파")
                reversal_score += 2
        else:
            if rsi_prev_15m < 30 and rsi_15m > 30:
                signals.append("⚠️ RSI 과매도권 이탈 (30 상향)")
                reversal_score += 3
            if rsi_prev_15m < 50 and rsi_15m > 50:
                signals.append("📈 RSI 50선 상향 돌파")
                reversal_score += 2
                
    except Exception as e:
        logger.debug(f"RSI 분석 오류: {e}")
    
    # ===== 최종 판단 (🆕 더 민감한 기준) =====
    should_exit = False
    urgency = 'none'
    confidence = 0.0
    
    if reversal_score >= 8:
        should_exit = True
        urgency = 'immediate'
        confidence = min(reversal_score / 12, 1.0)
    elif reversal_score >= 5:
        should_exit = True
        urgency = 'soon'
        confidence = reversal_score / 12
    elif reversal_score >= 3:
        urgency = 'watch'
        confidence = reversal_score / 12
    
    return {
        'should_exit': should_exit,
        'urgency': urgency,
        'confidence': confidence,
        'reversal_score': reversal_score,
        'signals': signals,
        'profit_risk': profit_risk,
        'threshold_immediate': 8,
        'threshold_soon': 5,
        'threshold_watch': 3
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


# ============ v7.3 Rule-Based Validation System ============
def calculate_risk_score(df_15min, df_hourly, df_4h, action: str) -> dict:
    """
    🆕 v7.3: Rule-Based Risk Score 계산
    수학적 비교를 Python으로 정확하게 수행
    
    ⚠️ 단기 극단값(15분봉)도 레버리지 특성상 즉각 손실 위험이 있으므로 
    높은 가중치 부여하여 REJECT/MODIFY 처리
    
    Returns:
        dict: {
            'total_score': int,
            'details': list of strings,
            'is_high_risk': bool
        }
    """
    risk_score = 0
    details = []
    
    # 안전한 값 추출 헬퍼
    def safe_get(df, col, default=50):
        try:
            val = df[col].iloc[-1]
            return float(val) if pd.notna(val) else default
        except:
            return default
    
    # 지표 추출
    rsi_15m = safe_get(df_15min, 'rsi', 50)
    rsi_1h = safe_get(df_hourly, 'rsi', 50)
    rsi_4h = safe_get(df_4h, 'rsi', 50)
    
    stoch_k_15m = safe_get(df_15min, 'stoch_k', 50)
    stoch_k_1h = safe_get(df_hourly, 'stoch_k', 50)
    stoch_k_4h = safe_get(df_4h, 'stoch_k', 50)
    
    adx_4h = safe_get(df_4h, 'adx', 25)
    di_plus_4h = safe_get(df_4h, 'di_plus', 25)
    di_minus_4h = safe_get(df_4h, 'di_minus', 25)
    
    cmf_15m = safe_get(df_15min, 'cmf', 0)
    cmf_1h = safe_get(df_hourly, 'cmf', 0)
    cmf_4h = safe_get(df_4h, 'cmf', 0)
    
    bb_upper_1h = safe_get(df_hourly, 'bb_bbh', 0)
    bb_lower_1h = safe_get(df_hourly, 'bb_bbl', 0)
    bb_upper_4h = safe_get(df_4h, 'bb_bbh', 0)
    bb_lower_4h = safe_get(df_4h, 'bb_bbl', 0)
    current_price = safe_get(df_15min, 'close', 0)
    
    if action.lower() == 'buy':
        # ========== BUY Signal Risk Factors ==========
        
        # 🚨 15m 타임프레임 (레버리지 즉각 위험 - 가중치 높음!)
        if rsi_15m > 85:
            risk_score += 5
            details.append(f"⚠️ 15m RSI {rsi_15m:.1f} > 85 → +5 (EXTREME overbought - immediate risk!)")
        elif rsi_15m > 80:
            risk_score += 4
            details.append(f"⚠️ 15m RSI {rsi_15m:.1f} > 80 → +4 (strong overbought - high risk)")
        elif rsi_15m > 75:
            risk_score += 2
            details.append(f"15m RSI {rsi_15m:.1f} > 75 → +2 (overbought)")
        
        if stoch_k_15m > 95:
            risk_score += 4
            details.append(f"⚠️ 15m Stoch %K {stoch_k_15m:.1f} > 95 → +4 (EXTREME - immediate pullback risk)")
        elif stoch_k_15m > 90:
            risk_score += 2
            details.append(f"15m Stoch %K {stoch_k_15m:.1f} > 90 → +2 (very high)")
        
        # 4h 타임프레임 (중장기 트렌드)
        if rsi_4h > 70:
            risk_score += 4
            details.append(f"4h RSI {rsi_4h:.1f} > 70 → +4 (strong overbought)")
        elif rsi_4h > 65:
            risk_score += 2
            details.append(f"4h RSI {rsi_4h:.1f} > 65 → +2 (overbought zone)")
        
        if stoch_k_4h > 90:
            risk_score += 2
            details.append(f"4h Stoch %K {stoch_k_4h:.1f} > 90 → +2 (overbought)")
        
        if adx_4h < 20:
            risk_score += 3
            details.append(f"4h ADX {adx_4h:.1f} < 20 → +3 (no clear trend)")
        
        if di_minus_4h > di_plus_4h:
            diff = di_minus_4h - di_plus_4h
            if diff > 10 and adx_4h > 25:
                risk_score += 4
                details.append(f"4h DI- {di_minus_4h:.1f} > DI+ {di_plus_4h:.1f} (diff {diff:.1f}) with strong ADX → +4 (strong downtrend)")
            else:
                risk_score += 2
                details.append(f"4h DI- {di_minus_4h:.1f} > DI+ {di_plus_4h:.1f} → +2 (against trend)")
        
        if cmf_4h < -0.1:
            risk_score += 2
            details.append(f"4h CMF {cmf_4h:.2f} < -0.1 → +2 (money outflow)")
        
        # 1h 타임프레임
        if rsi_1h > 75:
            risk_score += 3
            details.append(f"1h RSI {rsi_1h:.1f} > 75 → +3 (strong overbought)")
        elif rsi_1h > 70:
            risk_score += 2
            details.append(f"1h RSI {rsi_1h:.1f} > 70 → +2 (overbought)")
        
        if stoch_k_1h > 90:
            risk_score += 2
            details.append(f"1h Stoch %K {stoch_k_1h:.1f} > 90 → +2 (overbought)")
        
        if cmf_1h < -0.1:
            risk_score += 1
            details.append(f"1h CMF {cmf_1h:.2f} < -0.1 → +1 (money outflow)")
        
        # 복합 조건 - 다중 타임프레임 과열
        extreme_count = sum([rsi_15m > 75, rsi_1h > 70, rsi_4h > 65])
        if extreme_count >= 3:
            risk_score += 3
            details.append(f"⚠️ ALL timeframes overbought → +3 (triple confirmation risk)")
        elif extreme_count >= 2:
            risk_score += 1
            details.append(f"2 timeframes overbought → +1")
        
        # CMF 다중 음수
        cmf_negative_count = sum([cmf_15m < 0, cmf_1h < 0, cmf_4h < 0])
        if cmf_negative_count >= 2:
            risk_score += 2
            details.append(f"CMF negative on {cmf_negative_count} timeframes → +2")
        
        # BB 상단 근접
        if current_price > 0 and bb_upper_1h > 0 and bb_upper_4h > 0:
            if current_price > bb_upper_1h and current_price > bb_upper_4h:
                risk_score += 3
                details.append(f"Price above BB upper on both 1h and 4h → +3 (double extreme)")
                
    else:  # SELL signal
        # ========== SELL Signal Risk Factors ==========
        
        # 🚨 15m 타임프레임 (레버리지 즉각 위험 - 가중치 높음!)
        if rsi_15m < 15:
            risk_score += 5
            details.append(f"⚠️ 15m RSI {rsi_15m:.1f} < 15 → +5 (EXTREME oversold - immediate risk!)")
        elif rsi_15m < 20:
            risk_score += 4
            details.append(f"⚠️ 15m RSI {rsi_15m:.1f} < 20 → +4 (strong oversold - high risk)")
        elif rsi_15m < 25:
            risk_score += 2
            details.append(f"15m RSI {rsi_15m:.1f} < 25 → +2 (oversold)")
        
        if stoch_k_15m < 5:
            risk_score += 4
            details.append(f"⚠️ 15m Stoch %K {stoch_k_15m:.1f} < 5 → +4 (EXTREME - immediate bounce risk)")
        elif stoch_k_15m < 10:
            risk_score += 2
            details.append(f"15m Stoch %K {stoch_k_15m:.1f} < 10 → +2 (very low)")
        
        # 4h 타임프레임 (중장기 트렌드)
        if rsi_4h < 30:
            risk_score += 4
            details.append(f"4h RSI {rsi_4h:.1f} < 30 → +4 (strong oversold)")
        elif rsi_4h < 35:
            risk_score += 2
            details.append(f"4h RSI {rsi_4h:.1f} < 35 → +2 (oversold zone)")
        
        if stoch_k_4h < 10:
            risk_score += 2
            details.append(f"4h Stoch %K {stoch_k_4h:.1f} < 10 → +2 (oversold)")
        
        if adx_4h < 20:
            risk_score += 3
            details.append(f"4h ADX {adx_4h:.1f} < 20 → +3 (no clear trend)")
        
        if di_plus_4h > di_minus_4h:
            diff = di_plus_4h - di_minus_4h
            if diff > 10 and adx_4h > 25:
                risk_score += 4
                details.append(f"4h DI+ {di_plus_4h:.1f} > DI- {di_minus_4h:.1f} (diff {diff:.1f}) with strong ADX → +4 (strong uptrend)")
            else:
                risk_score += 2
                details.append(f"4h DI+ {di_plus_4h:.1f} > DI- {di_minus_4h:.1f} → +2 (against trend)")
        
        if cmf_4h > 0.1:
            risk_score += 2
            details.append(f"4h CMF {cmf_4h:.2f} > 0.1 → +2 (money inflow)")
        
        # 1h 타임프레임
        if rsi_1h < 25:
            risk_score += 3
            details.append(f"1h RSI {rsi_1h:.1f} < 25 → +3 (strong oversold)")
        elif rsi_1h < 30:
            risk_score += 2
            details.append(f"1h RSI {rsi_1h:.1f} < 30 → +2 (oversold)")
        
        if stoch_k_1h < 10:
            risk_score += 2
            details.append(f"1h Stoch %K {stoch_k_1h:.1f} < 10 → +2 (oversold)")
        
        if cmf_1h > 0.1:
            risk_score += 1
            details.append(f"1h CMF {cmf_1h:.2f} > 0.1 → +1 (money inflow)")
        
        # 복합 조건 - 다중 타임프레임 과매도
        extreme_count = sum([rsi_15m < 25, rsi_1h < 30, rsi_4h < 35])
        if extreme_count >= 3:
            risk_score += 3
            details.append(f"⚠️ ALL timeframes oversold → +3 (triple confirmation risk)")
        elif extreme_count >= 2:
            risk_score += 1
            details.append(f"2 timeframes oversold → +1")
        
        # CMF 다중 양수
        cmf_positive_count = sum([cmf_15m > 0, cmf_1h > 0, cmf_4h > 0])
        if cmf_positive_count >= 2:
            risk_score += 2
            details.append(f"CMF positive on {cmf_positive_count} timeframes → +2")
        
        # BB 하단 근접
        if current_price > 0 and bb_lower_1h > 0 and bb_lower_4h > 0:
            if current_price < bb_lower_1h and current_price < bb_lower_4h:
                risk_score += 3
                details.append(f"Price below BB lower on both 1h and 4h → +3 (double extreme)")
    
    if not details:
        details.append("No significant risk factors detected → +0")
    
    return {
        'total_score': risk_score,
        'details': details,
        'is_high_risk': risk_score >= 8
    }


def calculate_approval_score(df_15min, df_hourly, df_4h, action: str) -> dict:
    """
    🆕 v7.3: Rule-Based Approval Score 계산
    
    Returns:
        dict: {
            'total_score': int,
            'details': list of strings,
            'is_approved': bool
        }
    """
    approval_score = 0
    details = []
    
    # 안전한 값 추출 헬퍼
    def safe_get(df, col, default=50):
        try:
            val = df[col].iloc[-1]
            return float(val) if pd.notna(val) else default
        except:
            return default
    
    # 지표 추출
    rsi_15m = safe_get(df_15min, 'rsi', 50)
    rsi_1h = safe_get(df_hourly, 'rsi', 50)
    rsi_4h = safe_get(df_4h, 'rsi', 50)
    
    adx_4h = safe_get(df_4h, 'adx', 25)
    di_plus_4h = safe_get(df_4h, 'di_plus', 25)
    di_minus_4h = safe_get(df_4h, 'di_minus', 25)
    
    adx_1h = safe_get(df_hourly, 'adx', 25)
    di_plus_1h = safe_get(df_hourly, 'di_plus', 25)
    di_minus_1h = safe_get(df_hourly, 'di_minus', 25)
    
    cmf_15m = safe_get(df_15min, 'cmf', 0)
    cmf_1h = safe_get(df_hourly, 'cmf', 0)
    cmf_4h = safe_get(df_4h, 'cmf', 0)
    
    macd_4h = safe_get(df_4h, 'macd', 0)
    macd_signal_4h = safe_get(df_4h, 'macd_signal', 0)
    macd_diff_4h = safe_get(df_4h, 'macd_diff', 0)
    
    sma_1h = safe_get(df_hourly, 'sma_20', 0)
    current_price = safe_get(df_15min, 'close', 0)
    
    if action.lower() == 'buy':
        # ========== BUY Signal Approval Factors ==========
        
        # Primary Factors (max 50 points)
        # 4h 추세 확인
        if di_plus_4h > di_minus_4h and adx_4h > 20:
            if adx_4h > 25:
                approval_score += 25
                details.append(f"4h DI+ {di_plus_4h:.1f} > DI- {di_minus_4h:.1f} with ADX {adx_4h:.1f} > 25 → +25 (strong uptrend)")
            else:
                approval_score += 20
                details.append(f"4h DI+ {di_plus_4h:.1f} > DI- {di_minus_4h:.1f} with ADX {adx_4h:.1f} > 20 → +20 (uptrend confirmed)")
        
        # 1h RSI 최적 영역
        if 35 <= rsi_1h <= 55:
            approval_score += 15
            details.append(f"1h RSI {rsi_1h:.1f} in optimal zone (35-55) → +15")
        elif 30 <= rsi_1h <= 60:
            approval_score += 10
            details.append(f"1h RSI {rsi_1h:.1f} in acceptable zone (30-60) → +10")
        
        # 1h 추세 정렬
        if current_price > sma_1h and di_plus_1h > di_minus_1h:
            approval_score += 10
            details.append(f"Price above 1h SMA with bullish DI → +10 (trend aligned)")
        
        # Secondary Factors (max 30 points)
        # CMF 확인
        if cmf_1h > 0 and cmf_4h > 0:
            approval_score += 10
            details.append(f"CMF positive on 1h ({cmf_1h:.2f}) and 4h ({cmf_4h:.2f}) → +10 (money inflow)")
        elif cmf_4h > 0:
            approval_score += 5
            details.append(f"CMF positive on 4h ({cmf_4h:.2f}) → +5")
        
        # MACD 확인
        if macd_4h > macd_signal_4h:
            approval_score += 8
            details.append(f"4h MACD {macd_4h:.2f} > Signal {macd_signal_4h:.2f} → +8 (bullish)")
        
        # ADX 상승 중
        try:
            adx_prev = df_4h['adx'].iloc[-2] if len(df_4h) > 1 else adx_4h
            if adx_4h > adx_prev:
                approval_score += 5
                details.append(f"4h ADX rising ({adx_prev:.1f} → {adx_4h:.1f}) → +5 (trend strengthening)")
        except:
            pass
        
        # Bonus Factors (max 20 points)
        # 거래량 확인
        try:
            vol = df_hourly['volume'].iloc[-1]
            vol_ma = df_hourly['volume'].rolling(20).mean().iloc[-1]
            if vol > vol_ma:
                approval_score += 5
                details.append(f"Volume above 20-period average → +5")
        except:
            pass
        
        # 15m 진입 타이밍
        if 30 <= rsi_15m <= 65:
            approval_score += 5
            details.append(f"15m RSI {rsi_15m:.1f} good entry timing → +5")
            
    else:  # SELL signal
        # ========== SELL Signal Approval Factors ==========
        
        # Primary Factors (max 50 points)
        # 4h 추세 확인
        if di_minus_4h > di_plus_4h and adx_4h > 20:
            if adx_4h > 25:
                approval_score += 25
                details.append(f"4h DI- {di_minus_4h:.1f} > DI+ {di_plus_4h:.1f} with ADX {adx_4h:.1f} > 25 → +25 (strong downtrend)")
            else:
                approval_score += 20
                details.append(f"4h DI- {di_minus_4h:.1f} > DI+ {di_plus_4h:.1f} with ADX {adx_4h:.1f} > 20 → +20 (downtrend confirmed)")
        
        # 1h RSI 최적 영역
        if 45 <= rsi_1h <= 65:
            approval_score += 15
            details.append(f"1h RSI {rsi_1h:.1f} in optimal zone (45-65) → +15")
        elif 40 <= rsi_1h <= 70:
            approval_score += 10
            details.append(f"1h RSI {rsi_1h:.1f} in acceptable zone (40-70) → +10")
        
        # 1h 추세 정렬
        if current_price < sma_1h and di_minus_1h > di_plus_1h:
            approval_score += 10
            details.append(f"Price below 1h SMA with bearish DI → +10 (trend aligned)")
        
        # Secondary Factors (max 30 points)
        # CMF 확인
        if cmf_1h < 0 and cmf_4h < 0:
            approval_score += 10
            details.append(f"CMF negative on 1h ({cmf_1h:.2f}) and 4h ({cmf_4h:.2f}) → +10 (money outflow)")
        elif cmf_4h < 0:
            approval_score += 5
            details.append(f"CMF negative on 4h ({cmf_4h:.2f}) → +5")
        
        # MACD 확인
        if macd_4h < macd_signal_4h:
            approval_score += 8
            details.append(f"4h MACD {macd_4h:.2f} < Signal {macd_signal_4h:.2f} → +8 (bearish)")
        
        # ADX 상승 중
        try:
            adx_prev = df_4h['adx'].iloc[-2] if len(df_4h) > 1 else adx_4h
            if adx_4h > adx_prev:
                approval_score += 5
                details.append(f"4h ADX rising ({adx_prev:.1f} → {adx_4h:.1f}) → +5 (trend strengthening)")
        except:
            pass
        
        # Bonus Factors (max 20 points)
        # 거래량 확인
        try:
            vol = df_hourly['volume'].iloc[-1]
            vol_ma = df_hourly['volume'].rolling(20).mean().iloc[-1]
            if vol > vol_ma:
                approval_score += 5
                details.append(f"Volume above 20-period average → +5")
        except:
            pass
        
        # 15m 진입 타이밍
        if 35 <= rsi_15m <= 70:
            approval_score += 5
            details.append(f"15m RSI {rsi_15m:.1f} good entry timing → +5")
    
    if not details:
        details.append("No approval factors detected → +0")
    
    return {
        'total_score': approval_score,
        'details': details,
        'is_approved': approval_score >= 70
    }


def calculate_reverse_score(df_15min, df_hourly, df_4h, action: str) -> dict:
    """
    🆕 v7.3 개선: Rule-Based Reverse Score 계산
    극단적 과매수/과매도 시 신호 반전 여부 결정
    
    ⚠️ 중요: 4시간봉 트렌드가 원본 신호를 지지하면 REVERSE하지 않음!
    - 단기 과열은 일시적일 수 있음
    - 장기 트렌드가 더 중요함
    - 4시간봉에서 여력이 있으면 원본 방향 유지
    
    Returns:
        dict: {
            'total_score': int,
            'signal_count': int,
            'details': list of strings,
            'should_reverse': bool,
            'reverse_action': str ('buy' or 'sell'),
            'trend_supports_original': bool  # 4시간봉이 원본 신호 지지 여부
        }
    """
    reverse_score = 0
    signal_count = 0
    details = []
    
    # 안전한 값 추출 헬퍼
    def safe_get(df, col, default=50):
        try:
            val = df[col].iloc[-1]
            return float(val) if pd.notna(val) else default
        except:
            return default
    
    # 지표 추출 (4시간봉 우선)
    rsi_4h = safe_get(df_4h, 'rsi', 50)
    rsi_1h = safe_get(df_hourly, 'rsi', 50)
    rsi_15m = safe_get(df_15min, 'rsi', 50)
    
    stoch_k_4h = safe_get(df_4h, 'stoch_k', 50)
    stoch_k_1h = safe_get(df_hourly, 'stoch_k', 50)
    
    adx_4h = safe_get(df_4h, 'adx', 25)
    di_plus_4h = safe_get(df_4h, 'di_plus', 25)
    di_minus_4h = safe_get(df_4h, 'di_minus', 25)
    
    adx_1h = safe_get(df_hourly, 'adx', 25)
    di_plus_1h = safe_get(df_hourly, 'di_plus', 25)
    di_minus_1h = safe_get(df_hourly, 'di_minus', 25)
    
    macd_diff_4h = safe_get(df_4h, 'macd_diff', 0)
    macd_diff_1h = safe_get(df_hourly, 'macd_diff', 0)
    
    bb_upper_4h = safe_get(df_4h, 'bb_bbh', 0)
    bb_lower_4h = safe_get(df_4h, 'bb_bbl', 0)
    bb_middle_4h = safe_get(df_4h, 'bb_bbm', 0)
    current_price = safe_get(df_15min, 'close', 0)
    
    # ========== 4시간봉 트렌드 확인 (최우선) ==========
    trend_supports_original = False
    trend_details = []
    
    if action.lower() == 'buy':
        # BUY 신호 - 4시간봉이 상승 추세를 지지하는지 확인
        
        # 조건 1: 4시간봉 RSI가 아직 과열 아님 (65 미만이면 여력 있음)
        if rsi_4h < 65:
            trend_supports_original = True
            trend_details.append(f"✅ 4h RSI {rsi_4h:.1f} < 65 - Room for upside")
        
        # 조건 2: 4시간봉 DI+가 우세하면 상승 추세
        if di_plus_4h > di_minus_4h and adx_4h > 20:
            trend_supports_original = True
            trend_details.append(f"✅ 4h Uptrend: DI+ {di_plus_4h:.1f} > DI- {di_minus_4h:.1f}, ADX {adx_4h:.1f}")
        
        # 조건 3: 4시간봉 MACD가 양수면 상승 모멘텀
        if macd_diff_4h > 0:
            trend_supports_original = True
            trend_details.append(f"✅ 4h MACD Bullish: {macd_diff_4h:.4f}")
        
        # 조건 4: 가격이 4시간봉 BB 중심선 위에 있으면 상승 추세
        if current_price > bb_middle_4h and bb_middle_4h > 0:
            trend_supports_original = True
            trend_details.append(f"✅ Price ${current_price:.2f} above 4h BB middle ${bb_middle_4h:.2f}")
        
        reverse_action = 'sell'
        
        # ========== REVERSE 점수 계산 (4시간봉 기준 강화) ==========
        # 4시간봉이 원본을 지지하면 reverse 불가 → 점수를 계산하지 않음
        if trend_supports_original:
            details.append(f"🛡️ 4H TREND SUPPORTS BUY - Reverse blocked")
            for td in trend_details:
                details.append(f"   {td}")
        else:
            # 4시간봉이 지지하지 않을 때만 reverse 점수 계산
            
            # 🔴 4시간봉 극단적 과매수 (가장 중요!)
            if rsi_4h > 85:
                reverse_score += 5
                signal_count += 1
                details.append(f"🔴 4h RSI {rsi_4h:.1f} > 85 → +5 (EXTREME overbought on 4H!)")
            elif rsi_4h > 80:
                reverse_score += 3
                signal_count += 1
                details.append(f"🔴 4h RSI {rsi_4h:.1f} > 80 → +3 (Strong overbought on 4H)")
            elif rsi_4h >= 75:
                reverse_score += 1
                details.append(f"🟠 4h RSI {rsi_4h:.1f} >= 75 → +1 (Overbought zone)")
            
            # 🔴 4시간봉 Stochastic 극단값
            if stoch_k_4h > 95:
                reverse_score += 4
                signal_count += 1
                details.append(f"🔴 4h Stoch %K {stoch_k_4h:.1f} > 95 → +4 (EXTREME on 4H)")
            elif stoch_k_4h > 90:
                reverse_score += 2
                signal_count += 1
                details.append(f"🔴 4h Stoch %K {stoch_k_4h:.1f} > 90 → +2 (Very high)")
            
            # 🔴 4시간봉 강한 하락 추세에서 BUY (추세 역행)
            if di_minus_4h > di_plus_4h + 20 and adx_4h > 35:
                reverse_score += 5
                signal_count += 1
                details.append(f"🔴 4H STRONG DOWNTREND: DI- {di_minus_4h:.1f} >> DI+ {di_plus_4h:.1f}, ADX {adx_4h:.1f} → +5")
            elif di_minus_4h > di_plus_4h + 10 and adx_4h > 30:
                reverse_score += 3
                signal_count += 1
                details.append(f"🔴 4H Downtrend: DI- {di_minus_4h:.1f} > DI+ {di_plus_4h:.1f}, ADX {adx_4h:.1f} → +3")
            
            # 🔴 4시간봉 MACD 강한 약세
            if macd_diff_4h < 0 and macd_diff_1h < 0:
                reverse_score += 2
                details.append(f"🟠 MACD bearish on both 1h & 4h → +2")
            
            # 🔴 가격이 4시간봉 BB 상단 위로 크게 돌파
            if current_price > 0 and bb_upper_4h > 0:
                if current_price > bb_upper_4h * 1.02:  # 2% 이상 돌파
                    reverse_score += 3
                    signal_count += 1
                    details.append(f"🔴 Price {((current_price/bb_upper_4h)-1)*100:.1f}% above 4H BB upper → +3")
            
            # 1시간봉은 보조 지표로만 사용 (점수 낮음)
            if rsi_1h > 85 and stoch_k_1h > 95:
                reverse_score += 1
                details.append(f"🟠 1h also extreme: RSI {rsi_1h:.1f}, Stoch {stoch_k_1h:.1f} → +1")
        
    else:  # action == 'sell'
        # SELL 신호 - 4시간봉이 하락 추세를 지지하는지 확인
        
        # 조건 1: 4시간봉 RSI가 아직 과매도 아님 (35 초과면 여력 있음)
        if rsi_4h > 35:
            trend_supports_original = True
            trend_details.append(f"✅ 4h RSI {rsi_4h:.1f} > 35 - Room for downside")
        
        # 조건 2: 4시간봉 DI-가 우세하면 하락 추세
        if di_minus_4h > di_plus_4h and adx_4h > 20:
            trend_supports_original = True
            trend_details.append(f"✅ 4h Downtrend: DI- {di_minus_4h:.1f} > DI+ {di_plus_4h:.1f}, ADX {adx_4h:.1f}")
        
        # 조건 3: 4시간봉 MACD가 음수면 하락 모멘텀
        if macd_diff_4h < 0:
            trend_supports_original = True
            trend_details.append(f"✅ 4h MACD Bearish: {macd_diff_4h:.4f}")
        
        # 조건 4: 가격이 4시간봉 BB 중심선 아래에 있으면 하락 추세
        if current_price < bb_middle_4h and bb_middle_4h > 0:
            trend_supports_original = True
            trend_details.append(f"✅ Price ${current_price:.2f} below 4h BB middle ${bb_middle_4h:.2f}")
        
        reverse_action = 'buy'
        
        # ========== REVERSE 점수 계산 (4시간봉 기준 강화) ==========
        if trend_supports_original:
            details.append(f"🛡️ 4H TREND SUPPORTS SELL - Reverse blocked")
            for td in trend_details:
                details.append(f"   {td}")
        else:
            # 4시간봉이 지지하지 않을 때만 reverse 점수 계산
            
            # 🟢 4시간봉 극단적 과매도 (가장 중요!)
            if rsi_4h < 15:
                reverse_score += 5
                signal_count += 1
                details.append(f"🟢 4h RSI {rsi_4h:.1f} < 15 → +5 (EXTREME oversold on 4H!)")
            elif rsi_4h < 20:
                reverse_score += 3
                signal_count += 1
                details.append(f"🟢 4h RSI {rsi_4h:.1f} < 20 → +3 (Strong oversold on 4H)")
            elif rsi_4h <= 25:
                reverse_score += 1
                details.append(f"🟡 4h RSI {rsi_4h:.1f} <= 25 → +1 (Oversold zone)")
            
            # 🟢 4시간봉 Stochastic 극단값
            if stoch_k_4h < 5:
                reverse_score += 4
                signal_count += 1
                details.append(f"🟢 4h Stoch %K {stoch_k_4h:.1f} < 5 → +4 (EXTREME on 4H)")
            elif stoch_k_4h < 10:
                reverse_score += 2
                signal_count += 1
                details.append(f"🟢 4h Stoch %K {stoch_k_4h:.1f} < 10 → +2 (Very low)")
            
            # 🟢 4시간봉 강한 상승 추세에서 SELL (추세 역행)
            if di_plus_4h > di_minus_4h + 20 and adx_4h > 35:
                reverse_score += 5
                signal_count += 1
                details.append(f"🟢 4H STRONG UPTREND: DI+ {di_plus_4h:.1f} >> DI- {di_minus_4h:.1f}, ADX {adx_4h:.1f} → +5")
            elif di_plus_4h > di_minus_4h + 10 and adx_4h > 30:
                reverse_score += 3
                signal_count += 1
                details.append(f"🟢 4H Uptrend: DI+ {di_plus_4h:.1f} > DI- {di_minus_4h:.1f}, ADX {adx_4h:.1f} → +3")
            
            # 🟢 4시간봉 MACD 강한 강세
            if macd_diff_4h > 0 and macd_diff_1h > 0:
                reverse_score += 2
                details.append(f"🟡 MACD bullish on both 1h & 4h → +2")
            
            # 🟢 가격이 4시간봉 BB 하단 아래로 크게 돌파
            if current_price > 0 and bb_lower_4h > 0:
                if current_price < bb_lower_4h * 0.98:  # 2% 이상 돌파
                    reverse_score += 3
                    signal_count += 1
                    details.append(f"🟢 Price {(1-(current_price/bb_lower_4h))*100:.1f}% below 4H BB lower → +3")
            
            # 1시간봉은 보조 지표로만 사용 (점수 낮음)
            if rsi_1h < 15 and stoch_k_1h < 5:
                reverse_score += 1
                details.append(f"🟡 1h also extreme: RSI {rsi_1h:.1f}, Stoch {stoch_k_1h:.1f} → +1")
    
    if not details:
        details.append("No extreme signals detected → +0")
    
    # 🔒 반전 조건: 4시간봉이 원본 지지하면 절대 반전 안함
    # 반전하려면: 4시간봉 지지 없음 + (4개 이상의 극단 신호 또는 10점 이상)
    should_reverse = (not trend_supports_original) and (signal_count >= 4 or reverse_score >= 10)
    
    return {
        'total_score': reverse_score,
        'signal_count': signal_count,
        'details': details,
        'should_reverse': should_reverse,
        'reverse_action': reverse_action,
        'trend_supports_original': trend_supports_original
    }


def rule_based_validation(symbol: str, action: str, market_data: dict) -> dict:
    """
    🆕 v7.3: Rule-Based 종합 검증
    AI 대신 Python 로직으로 진입 여부 결정
    
    Returns:
        dict: {
            'decision': 'approve' | 'reject' | 'modify' | 'reverse',
            'modified_action': str,  # reverse일 경우 반전된 액션
            'risk_score': dict,
            'approval_score': dict,
            'reverse_score': dict,  # 반전 점수
            'reason': str,
            'recommended_params': dict  # AI가 조정할 기본값
        }
    """
    df_15min = market_data['df_15min']
    df_hourly = market_data['df_hourly']
    df_4h = market_data['df_4h']
    current_price = market_data['current_price']
    
    # 1. Reverse Score 계산 (먼저 체크 - 극단적 신호 감지)
    reverse_result = calculate_reverse_score(df_15min, df_hourly, df_4h, action)
    
    # 2. Risk Score 계산
    risk_result = calculate_risk_score(df_15min, df_hourly, df_4h, action)
    
    # 3. Approval Score 계산
    approval_result = calculate_approval_score(df_15min, df_hourly, df_4h, action)
    
    # 점수 추출
    reverse_score = reverse_result['total_score']
    reverse_signals = reverse_result['signal_count']
    risk_score = risk_result['total_score']
    approval_score = approval_result['total_score']
    
    # ATR 기반 TP/SL 계산
    try:
        atr_4h = df_4h['atr'].iloc[-1] if 'atr' in df_4h.columns else current_price * 0.02
        if pd.isna(atr_4h) or atr_4h <= 0:
            atr_4h = current_price * 0.02
    except:
        atr_4h = current_price * 0.02
    
    # ========== 결정 로직 ==========
    modified_action = action  # 기본값: 원래 액션 유지
    
    # 🔄 STEP 0: 반전 조건 체크 (최우선)
    # 조건: 3개 이상의 극단 신호 또는 8점 이상
    if reverse_result['should_reverse']:
        decision = 'reverse'
        modified_action = reverse_result['reverse_action']
        reason = f"🔄 REVERSE - Extreme signals detected! Score: {reverse_score}/8, Signals: {reverse_signals}/3. Original {action.upper()} → {modified_action.upper()}"
        
        # 반전된 방향으로 TP/SL 설정 (카운터 트레이드는 더 보수적)
        if modified_action == 'buy':
            default_sl = current_price - (atr_4h * 1.5)  # 더 타이트한 SL
            default_tp = current_price + (atr_4h * 2.5)
        else:
            default_sl = current_price + (atr_4h * 1.5)
            default_tp = current_price - (atr_4h * 2.5)
        
        base_leverage = 8   # 반전은 보수적으로
        base_position_pct = 20
        
    # STEP 1: 높은 리스크 → REJECT
    elif risk_score >= 8:
        decision = 'reject'
        reason = f"HIGH RISK - Risk Score {risk_score}/8 exceeds threshold"
        
        if action.lower() == 'buy':
            default_sl = current_price - (atr_4h * 2.0)
            default_tp = current_price + (atr_4h * 3.5)
        else:
            default_sl = current_price + (atr_4h * 2.0)
            default_tp = current_price - (atr_4h * 3.5)
        
        base_leverage = 5
        base_position_pct = 10
        
    # STEP 2: 중간 리스크 + 낮은 승인 → MODIFY
    elif risk_score >= 5 and approval_score < 75:
        decision = 'modify'
        reason = f"MODIFY - Risk Score {risk_score}, Approval Score {approval_score} (marginal)"
        
        if action.lower() == 'buy':
            default_sl = current_price - (atr_4h * 2.0)
            default_tp = current_price + (atr_4h * 3.5)
        else:
            default_sl = current_price + (atr_4h * 2.0)
            default_tp = current_price - (atr_4h * 3.5)
        
        base_leverage = 10
        base_position_pct = 20
        
    # STEP 3: 승인 점수 충분 → APPROVE 또는 MODIFY
    elif approval_score >= 70:
        if risk_score <= 4:
            decision = 'approve'
            reason = f"APPROVED - Low Risk ({risk_score}), High Approval ({approval_score})"
            base_leverage = 15
            base_position_pct = 30
        else:
            decision = 'modify'
            reason = f"MODIFY - Medium Risk ({risk_score}), Good Approval ({approval_score})"
            base_leverage = 10
            base_position_pct = 20
        
        if action.lower() == 'buy':
            default_sl = current_price - (atr_4h * 2.0)
            default_tp = current_price + (atr_4h * 3.5)
        else:
            default_sl = current_price + (atr_4h * 2.0)
            default_tp = current_price - (atr_4h * 3.5)
            
    # STEP 4: 낮은 승인 점수 → REJECT
    else:
        decision = 'reject'
        reason = f"REJECTED - Approval Score {approval_score} below threshold (70)"
        
        if action.lower() == 'buy':
            default_sl = current_price - (atr_4h * 2.0)
            default_tp = current_price + (atr_4h * 3.5)
        else:
            default_sl = current_price + (atr_4h * 2.0)
            default_tp = current_price - (atr_4h * 3.5)
        
        base_leverage = 5
        base_position_pct = 10
    
    # ========== 로깅 ==========
    logger.info(f"📊 Rule-Based Validation for {symbol} {action.upper()}")
    
    # 4시간봉 트렌드 지지 여부 로깅
    trend_supports = reverse_result.get('trend_supports_original', False)
    if trend_supports:
        logger.info(f"   🛡️ 4H Trend SUPPORTS original {action.upper()} signal - Reverse blocked")
    
    # 반전 점수 로깅
    if reverse_score > 0 or reverse_signals > 0 or not trend_supports:
        reverse_emoji = "🔄" if reverse_result['should_reverse'] else "⚪"
        trend_status = "🛡️BLOCKED" if trend_supports else "⚠️POSSIBLE"
        logger.info(f"   {reverse_emoji} Reverse Score: {reverse_score}/10, Signals: {reverse_signals}/4 [{trend_status}] {'→ REVERSE!' if reverse_result['should_reverse'] else ''}")
        for detail in reverse_result['details'][:7]:  # 상위 7개
            logger.info(f"      - {detail}")
    
    logger.info(f"   Risk Score: {risk_score}/8 {'⚠️ HIGH' if risk_score >= 8 else '✓ OK'}")
    for detail in risk_result['details'][:5]:
        logger.info(f"      - {detail}")
    logger.info(f"   Approval Score: {approval_score}/100 {'✓ PASS' if approval_score >= 70 else '✗ FAIL'}")
    for detail in approval_result['details'][:5]:
        logger.info(f"      - {detail}")
    
    decision_emoji = {"approve": "✅", "reject": "❌", "modify": "⚠️", "reverse": "🔄"}
    logger.info(f"   {decision_emoji.get(decision, '❓')} Decision: {decision.upper()} - {reason}")
    if decision == 'reverse':
        logger.info(f"   🔄 Action changed: {action.upper()} → {modified_action.upper()}")
    
    return {
        'decision': decision,
        'modified_action': modified_action,
        'risk_score': risk_result,
        'approval_score': approval_result,
        'reverse_score': reverse_result,
        'reason': reason,
        'recommended_params': {
            'leverage': base_leverage,
            'position_percent': base_position_pct,
            'stop_loss': default_sl,
            'take_profit': default_tp,
            'current_price': current_price,
            'atr': atr_4h
        }
    }


def ai_parameter_adjustment(symbol: str, action: str, rule_based_result: dict, market_data: dict) -> dict:
    """
    🆕 v7.3: AI 파라미터 조정
    Rule-Based 결정 후 AI가 레버리지, 포지션 사이즈, TP/SL만 미세조정
    
    Returns:
        dict: 최종 트레이딩 파라미터
    """
    from openai import OpenAI
    
    client = OpenAI(api_key=os.getenv("DEEPSEEK_API_KEY"), base_url="https://api.deepseek.com")
    if not client.api_key:
        logger.error("DeepSeek API key is missing")
        return rule_based_result['recommended_params']
    
    params = rule_based_result['recommended_params']
    decision = rule_based_result['decision']
    
    # reject인 경우 AI 호출 안함
    if decision == 'reject':
        return {
            'decision': 'reject',
            'leverage': 0,
            'position_percent': 0,
            'stop_loss': 0,
            'take_profit': 0,
            'pl_ratio': 0,
            'reason': rule_based_result['reason']
        }
    
    current_price = params['current_price']
    atr = params['atr']
    risk_score = rule_based_result['risk_score']['total_score']
    approval_score = rule_based_result['approval_score']['total_score']
    
    # 간단한 프롬프트
    prompt = f"""You are a risk management AI for crypto futures trading.

**TASK:** Adjust trading parameters based on the pre-validated signal.

**SIGNAL INFO:**
- Symbol: {symbol}
- Action: {action.upper()}
- Current Price: ${current_price:.2f}
- ATR (4h): ${atr:.4f}

**PRE-VALIDATION RESULT (Rule-Based):**
- Decision: {decision.upper()}
- Risk Score: {risk_score}/8
- Approval Score: {approval_score}/100
- Reason: {rule_based_result['reason']}

**DEFAULT PARAMETERS (adjust these):**
- Leverage: {params['leverage']}x (range: 5-20)
- Position Size: {params['position_percent']}% (range: 10-40)
- Stop Loss: ${params['stop_loss']:.2f}
- Take Profit: ${params['take_profit']:.2f}

**ADJUSTMENT RULES:**
1. Higher Risk Score → Lower Leverage & Position Size
2. Lower Approval Score → More Conservative Parameters
3. TP/SL should maintain R:R ratio >= 1.8
4. Stop Loss: 1.5-2.5x ATR from entry
5. Take Profit: At least 1.8x the SL distance

**OUTPUT FORMAT (JSON only):**
{{
    "leverage": <5-20>,
    "position_percent": <10-40>,
    "stop_loss": <price>,
    "take_profit": <price>,
    "pl_ratio": <1.8-5.0>,
    "reason": "<brief adjustment rationale>"
}}

Return ONLY the JSON object."""

    try:
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {
                    "role": "system",
                    "content": "You are a risk management AI. Return ONLY valid JSON with adjusted trading parameters. No explanations outside JSON."
                },
                {"role": "user", "content": prompt}
            ],
            response_format={'type': 'json_object'},
            temperature=0.1,
            max_tokens=500
        )
        
        ai_response = response.choices[0].message.content.strip()
        logger.info(f"AI Parameter Adjustment Response: {ai_response[:200]}")
        
        # JSON 파싱
        result = json.loads(ai_response)
        
        # 범위 검증 및 보정
        leverage = max(5, min(20, int(result.get('leverage', params['leverage']))))
        position_pct = max(10, min(40, int(result.get('position_percent', params['position_percent']))))
        stop_loss = float(result.get('stop_loss', params['stop_loss']))
        take_profit = float(result.get('take_profit', params['take_profit']))
        
        # PL ratio 계산
        if action.lower() == 'buy':
            sl_distance = abs(current_price - stop_loss)
            tp_distance = abs(take_profit - current_price)
        else:
            sl_distance = abs(stop_loss - current_price)
            tp_distance = abs(current_price - take_profit)
        
        pl_ratio = tp_distance / sl_distance if sl_distance > 0 else 2.0
        pl_ratio = max(1.8, min(5.0, pl_ratio))
        
        return {
            'decision': decision,
            'leverage': leverage,
            'position_percent': position_pct,
            'stop_loss': stop_loss,
            'take_profit': take_profit,
            'pl_ratio': round(pl_ratio, 2),
            'reason': result.get('reason', rule_based_result['reason']),
            'risk_score': risk_score,
            'approval_score': approval_score
        }
        
    except Exception as e:
        logger.error(f"AI parameter adjustment failed: {e}")
        # 실패 시 기본값 반환
        if action.lower() == 'buy':
            sl_dist = abs(current_price - params['stop_loss'])
            tp_dist = abs(params['take_profit'] - current_price)
        else:
            sl_dist = abs(params['stop_loss'] - current_price)
            tp_dist = abs(current_price - params['take_profit'])
        
        default_pl_ratio = tp_dist / sl_dist if sl_dist > 0 else 2.0
        
        return {
            'decision': decision,
            'leverage': params['leverage'],
            'position_percent': params['position_percent'],
            'stop_loss': params['stop_loss'],
            'take_profit': params['take_profit'],
            'pl_ratio': round(default_pl_ratio, 2),
            'reason': f"Default params (AI failed): {rule_based_result['reason']}",
            'risk_score': risk_score,
            'approval_score': approval_score
        }

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
        
        # 심볼 설정 정보 가져오기 (🆕 v7.3: 정규화된 심볼 사용)
        symbol_config = get_symbol_config(symbol)
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
        
        # 🆕 v7.1 Peak Profit 업데이트
        peak_profit_info = update_peak_profit(symbol, pnl_percent, current_price)
        drawdown_from_peak = get_profit_drawdown(symbol, pnl_percent)
        
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
        
        # 🆕 v7.1 조기 종료 신호 감지 (pnl_percent, holding_time 추가)
        early_exit_signals = detect_early_reversal_signals(
            df_15min, df_hourly, df_4h, side, current_price, entry_price,
            pnl_percent=pnl_percent, holding_minutes=holding_time
        )
        
        # 🆕 v7.1 수익 되돌림 경고 로깅
        if peak_profit_info['peak_pnl'] > 2.0 and drawdown_from_peak > 25:
            logger.warning(f"🚨 수익 되돌림 경고: Peak {peak_profit_info['peak_pnl']:+.2f}% → Current {pnl_percent:+.2f}% (Drawdown: {drawdown_from_peak:.1f}%)")
        
        # 🆕 v7.3 지지부진 포지션 경고 로깅 (60분 이후에만 - 보호 기간 지난 후)
        if holding_time >= 60 and abs(pnl_percent) < 1.0:
            logger.warning(f"⏰ 지지부진 포지션: {holding_time:.0f}분 보유, {pnl_percent:+.2f}% 수익")
        elif holding_time < 60:
            protection_phase = "STRICT" if holding_time < 20 else "CAUTION" if holding_time < 40 else "WATCH"
            logger.info(f"🛡️ 진입 보호 활성: {protection_phase} ({holding_time:.1f}분 보유)")
        
        # 조기 종료 신호 로깅
        if early_exit_signals['should_exit']:
            logger.warning(f"🚨 조기 종료 신호 감지!")
            logger.warning(f"   긴급도: {early_exit_signals['urgency']}")
            logger.warning(f"   신뢰도: {early_exit_signals['confidence']:.1%}")
            logger.warning(f"   역전 점수: {early_exit_signals['reversal_score']}/12")
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
    "urgency": "none"
}"""

        # 🆕 v7.1 경고 메시지 생성 (v7.3 수정: 60분 보호 기간 이후에만 stagnation 알림)
        v71_alerts = []
        if peak_profit_info['peak_pnl'] > 2.0 and drawdown_from_peak > 25:
            v71_alerts.append(f"🚨 PROFIT DRAWDOWN ALERT: Peak {peak_profit_info['peak_pnl']:+.2f}% → Current {pnl_percent:+.2f}% (Drawdown: {drawdown_from_peak:.1f}%)")
        if peak_profit_info['peak_pnl'] > 2.0 and drawdown_from_peak > 40:
            v71_alerts.append(f"⛔ CRITICAL DRAWDOWN: Lost more than 40% of peak profit! Consider IMMEDIATE EXIT")
        
        # Stagnation 알림은 60분 이후에만 (보호 기간 지난 후)
        if holding_time >= 60 and abs(pnl_percent) < 1.0:
            v71_alerts.append(f"⏰ STAGNATION ALERT: {holding_time:.0f}min holding, only {pnl_percent:+.2f}% profit")
        if holding_time >= 90 and abs(pnl_percent) < 1.5:
            v71_alerts.append(f"⚠️ TIME INEFFICIENCY: {holding_time:.0f}min for just {pnl_percent:+.2f}% - capital inefficiency!")
        if holding_time >= 120 and pnl_percent < 2.0:
            v71_alerts.append(f"🔴 EXTENDED HOLDING LOW PROFIT: 2+ hours with <2% profit - consider exit")
        if holding_time >= 180 and pnl_percent < 2.0:
            v71_alerts.append(f"⛔ VERY EXTENDED HOLDING: 3+ hours with <2% profit - strongly consider exit")
        
        # 보호 기간 중에는 보호 상태 알림
        if holding_time < 60:
            protection_phase = "STRICT (< 20min)" if holding_time < 20 else "CAUTION (20-40min)" if holding_time < 40 else "WATCH (40-60min)"
            v71_alerts.append(f"🛡️ EARLY PROTECTION ACTIVE: {protection_phase} - Position needs time to develop")
        
        v71_alerts_text = chr(10).join(['  ' + alert for alert in v71_alerts]) if v71_alerts else '  ✅ No v7.1 alerts'

        prompt = f"""
You are an elite AI position manager monitoring an active {side.upper()} position for {symbol}. Your mission is to protect profits, minimize losses, and identify optimal exit points using multi-timeframe analysis.

**CRITICAL CONTEXT:**
This is a LEVERAGED position ({leverage}x) - small price movements have AMPLIFIED impact on P&L.

🚨 **EARLY REVERSAL DETECTION SYSTEM:**
{'═' * 43}
→ Reversal Risk Score: {early_exit_signals['reversal_score']}/12
→ Should Exit: {'YES ⚠️' if early_exit_signals['should_exit'] else 'NO ✅'}
→ Urgency Level: {early_exit_signals['urgency'].upper()}
→ Confidence: {early_exit_signals['confidence']:.1%}

→ Detected Signals ({len(early_exit_signals['signals'])}):
{chr(10).join(['  • ' + sig for sig in early_exit_signals['signals']]) if early_exit_signals['signals'] else '  • No reversal signals detected'}

💡 **INTERPRETATION (v7.1 Enhanced):**
  • Score ≥ 8: IMMEDIATE exit recommended
  • Score 5-7: EXIT SOON (strong reversal signals)
  • Score 3-4: WATCH closely (early warning)
  • Score < 3: No significant reversal risk

{'⚠️ WARNING: Multiple reversal signals detected! Consider this heavily in your decision.' if early_exit_signals['should_exit'] else '✅ No major reversal concerns detected. Focus on other technical factors.'}
{'═' * 43}

🆕 **v7.1 PROFIT TRACKING & ALERTS:**
{'═' * 43}
→ Peak Profit Tracking:
  • Peak P&L: {peak_profit_info['peak_pnl']:+.2f}%
  • Current P&L: {pnl_percent:+.2f}%
  • Drawdown from Peak: {drawdown_from_peak:.1f}%
  • Time Since Peak: {(datetime.now() - peak_profit_info['peak_time']).total_seconds() / 60:.0f} minutes

→ v7.1 Alerts:
{v71_alerts_text}
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

🛡️ **EARLY POSITION PROTECTION (CRITICAL!):**
{'═' * 43}
→ Current Holding Time: {holding_time:.0f} minutes
→ Protection Phase: {'🔒 STRICT PROTECTION (< 20 min)' if holding_time < 20 else '⚠️ CAUTION ZONE (20-40 min)' if holding_time < 40 else '👀 WATCH ZONE (40-60 min)' if holding_time < 60 else '✅ NORMAL MONITORING'}

**MANDATORY RULES FOR EARLY POSITIONS:**
{'🔒 STRICT PROTECTION MODE (0-20 minutes):' if holding_time < 20 else '⚠️ CAUTION MODE (20-40 minutes):' if holding_time < 40 else '👀 WATCH MODE (40-60 minutes):' if holding_time < 60 else '✅ NORMAL MODE (60+ minutes):'}
{'''  • ONLY EXIT FOR: Severe loss (< -10%), catastrophic reversal (Score ≥ 12)
  • DO NOT EXIT FOR: Small/medium profits, minor-moderate reversal signals
  • REASON: Position needs significant time to develop. Early noise is NORMAL.
  • PATIENCE: Crypto is volatile - initial fluctuations don't indicate trend failure.
  • EXCEPTION: Only catastrophic scenarios warrant early exit.''' if holding_time < 20 else '''  • BE VERY CAUTIOUS about exit decisions
  • REQUIRE: Loss < -7% OR (Profit > +10% with exhaustion) OR Reversal Score ≥ 10
  • PREFER: Hold and let the trade thesis play out
  • Still early - most winning trades need 30+ minutes to develop''' if holding_time < 40 else '''  • MODERATE CAUTION still applies
  • REQUIRE: Loss < -5% OR strong reversal signals (Score ≥ 8)
  • Allow profit-taking only if Profit > +8% with clear exhaustion
  • Approaching normal monitoring phase''' if holding_time < 60 else '''  • Normal monitoring rules apply
  • Technical signals guide decisions
  • Time-based stagnation rules now active'''}

💡 **WHY EXTENDED PROTECTION (1 HOUR):**
  • Crypto markets are extremely noisy in short timeframes
  • AI validated this entry after thorough analysis - trust it
  • Most successful trades take 30-60+ minutes to reach targets
  • Premature exits are the #1 cause of missed profits
  • Let the trade thesis fully develop before abandoning it
{'═' * 43}

💰 **PROFIT/LOSS ASSESSMENT (Relative to Volatility):**
**For Loss Scenarios:**
- **Severe Loss (multiple ATR against position):** 
  Exit immediately unless extremely strong reversal signals on multiple timeframes
  
- **Significant Loss (1-2 ATR against position):** 
  Monitor very closely, exit if momentum doesn't reverse soon
  
- **Moderate Loss (less than 1 ATR):** 
  Acceptable if technical indicators support recovery
  Stop loss should be used if breakdown continues

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

🎯 **v7.3 PROFIT ZONE RULES (중장기 관점 우선!):**
{'═' * 43}
**WHEN IN PROFIT, USE LONGER TIMEFRAMES FOR EXIT DECISIONS:**

→ Current P&L: {pnl_percent:+.2f}%
→ Profit Zone: {'🟢 IN PROFIT' if pnl_percent > 0 else '🔴 IN LOSS'}

{'🟢 **PROFITABLE POSITION - MEDIUM/LONG-TERM FOCUS:**' if pnl_percent > 0 else '🔴 **LOSING POSITION - SHORT-TERM SIGNALS MATTER:**'}
{'''  • 📊 PRIORITIZE 4H and 1H charts for exit decisions
  • ⚠️ IGNORE 15m noise - short-term pullbacks are NORMAL in profitable trades
  • 🔒 DO NOT EXIT based solely on 15m RSI/Stochastic extremes
  • ✅ EXIT ONLY WHEN: 4H shows clear trend reversal (DI crossover, MACD cross)
  • ✅ EXIT ONLY WHEN: 1H confirms with multiple bearish/bullish signals
  • 💡 A 15m RSI of 80+ during profit is often just healthy consolidation
  • 💡 Wait for 1H or 4H confirmation before taking action
  • 🎯 Let profits run - don't cut winners short on minor signals''' if pnl_percent > 0 else '''  • 📊 All timeframes matter for loss mitigation
  • ⚠️ 15m signals CAN trigger exit in losing positions
  • 🔒 Cut losses when momentum confirms against position
  • ✅ Consider exit if 15m + 1H both show adverse signals'''}

**EXIT DECISION HIERARCHY (When in Profit):**
  1. 🥇 4H Trend Reversal → EXIT (highest priority)
  2. 🥈 1H Trend Reversal + 4H Weakening → EXIT
  3. 🥉 1H + 4H Both Showing Exhaustion → Partial Exit
  4. ❌ 15m Signals Alone → DO NOT EXIT (wait for confirmation)
{'═' * 43}

🆕 **v7.1 TIME-BASED STAGNATION RULES (applies after 60 min protection):**
- **60+ min holding with <1% profit:** Start considering exit - but not mandatory
- **90+ min holding with <1.5% profit:** Evaluate opportunity cost carefully
- **120+ min holding with <2% profit:** Strong exit consideration - capital inefficiency
- **180+ min holding with <2% profit:** Exit recommended - better opportunities elsewhere

⚠️ **NOTE:** These stagnation rules ONLY apply AFTER the 60-minute protection period.
During the first hour, focus on letting the trade develop, not on time-based exits.

🆕 **v7.1 PROFIT PROTECTION RULES:**
- **Peak Profit > 2% but Current < 1%:** EXIT 100% (lost more than half your gains!)
- **Peak Profit > 3% but Current < 2%:** EXIT at least 50% (protect remaining gains)
- **Drawdown from Peak > 40%:** IMMEDIATE EXIT (profit evaporating!)
- **Drawdown from Peak > 25%:** Strong exit consideration (trend may be reversing)

**Key Principle:** 
Don't exit profitable positions just because of arbitrary profit levels. 
Exit when TECHNICAL SIGNALS indicate momentum exhaustion or reversal,
not when hitting a percentage target. Let winners run until they show
weakness. Cut losers when technical breakdown is confirmed.
**BUT** also protect gains - if you had significant profit and it's evaporating, 
don't let a winner turn into a loser!

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
- decision: "hold", "close", or "partial_close"
- percentage: 0 for hold, 100 for full close, 25-75 for partial
- reason: **MUST be technical and specific, not based on arbitrary percentages**
- exit_type: "take_profit", "stop_loss", "trend_reversal", "risk_management", "time_stop", "profit_protection", "stagnation", or "none"
- confidence: 0.0 to 1.0 (lower if signals are mixed across timeframes)
- urgency: "immediate", "soon", "watch", or "none"

**Your reason MUST include:**
1. **Timeframe Analysis:** What each timeframe (5m/1h/4h) is telling you
2. **Trend Assessment:** Is trend intact, weakening, or reversing?
3. **Momentum Evaluation:** MACD, RSI, ADX readings and their direction
4. **Volume Confirmation:** CMF showing money flow direction
5. **Volatility Context:** How current move compares to ATR baseline
6. **Key Level Analysis:** Support/resistance, Bollinger band position
7. **Leveraged PnL Context:** Current profit/loss relative to volatility
8. **Divergence Check:** Any bearish/bullish divergences detected?
9. **v7.1 Alerts Check:** Any stagnation or profit drawdown concerns?

**DO NOT:**
- Make decisions based solely on reaching a percentage profit target
- Exit profitable positions just because "profit is high enough"
- Ignore strong technical momentum just to "secure profits"
- Use arbitrary rules like "always exit at X%"
- Let significant profits evaporate (check drawdown from peak!)
- **EXIT POSITIONS WITHIN FIRST 60 MINUTES** unless severe loss (< -10%) or catastrophic reversal (Score ≥ 12)
- **BE TRIGGER-HAPPY IN FIRST HOUR** - positions need time to develop!
- **EXIT PROFITABLE POSITIONS based on 15m signals alone** - wait for 1H/4H confirmation!
- **React to short-term noise when in profit** - 15m RSI extremes are normal during trends

**DO:**
- Exit when technical indicators show momentum exhaustion
- Hold strong trends even with large profits if momentum persists
- Cut losses quickly when breakdown is technically confirmed
- Let ATR guide what's "normal" vs "extended" movement
- Prioritize multi-timeframe confirmation over single signals
- **RESPECT 1-HOUR PROTECTION PERIOD** - give trades time to work
- **BE PATIENT** in first 60 minutes - early noise ≠ trend reversal
- **USE 4H/1H FOR PROFIT EXITS** - ignore 15m noise when profitable
- **CONFIRM EXIT SIGNALS on longer timeframes** before closing profitable trades

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
- Consider timeframe hierarchy: 4h trend > 1h momentum > 15m noise
- Volatility matters: 5% move in BTC ≠ 5% move in altcoin

🎯 CRITICAL - PROFIT ZONE RULES:
- When IN PROFIT: Use 4H and 1H for exit decisions, IGNORE 15m noise
- 15m signals alone should NEVER trigger exit of profitable positions
- Wait for 1H or 4H confirmation before closing winning trades
- Short-term pullbacks (15m) are NORMAL during profitable trends
- Only exit profits when LONGER TIMEFRAMES show clear reversal

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
            
            # 🆕 v7.3: 진입 초반 보호 로직 (1시간까지 확장, 완화된 기준)
            original_decision = result['decision']
            if result['decision'] in ['close', 'partial_close']:
                # 20분 이내: 엄격한 보호 (심각한 손실/극단적 역전만 허용)
                if holding_time < 20:
                    # 허용 조건: 심각한 손절(-10% 이상 손실) 또는 극단적 역전(점수 12 이상)
                    is_severe_loss = pnl_percent <= -10.0
                    is_catastrophic_reversal = early_exit_signals['reversal_score'] >= 12
                    
                    if not (is_severe_loss or is_catastrophic_reversal):
                        logger.warning(f"🛡️ 진입 초반 보호 발동 (< 20분): {result['decision']} → HOLD")
                        logger.warning(f"   보유 시간: {holding_time:.1f}분, PnL: {pnl_percent:+.2f}%, Reversal Score: {early_exit_signals['reversal_score']}")
                        logger.warning(f"   원래 이유: {result['reason'][:100]}...")
                        result['decision'] = 'hold'
                        result['percentage'] = 0
                        result['reason'] = f"🛡️ STRICT PROTECTION (< 20min): Original decision was {original_decision}, but position needs time to develop. Holding time: {holding_time:.1f}min. Original reason: {result['reason'][:150]}"
                        result['exit_type'] = 'none'
                        result['urgency'] = 'none'
                        
                        if ENABLE_TELEGRAM:
                            send_telegram_notification(
                                f"🛡️ <b>진입 초반 보호 발동</b>\n\n"
                                f"<b>심볼:</b> {symbol}\n"
                                f"<b>보유 시간:</b> {holding_time:.1f}분\n"
                                f"<b>현재 PnL:</b> {pnl_percent:+.2f}%\n"
                                f"<b>원래 결정:</b> {original_decision.upper()}\n"
                                f"<b>변경 결정:</b> HOLD\n\n"
                                f"💡 포지션이 발전할 시간이 필요합니다.\n"
                                f"1시간 이후 정상 모니터링 재개됩니다.",
                                'info'
                            )
                
                # 20-40분: 주의 구간 (여전히 관대하게)
                elif holding_time < 40:
                    # 허용 조건: 손실 -7% 이상, 수익 +10% 이상 + 피로 신호(≥7), 또는 역전 점수 10 이상
                    is_significant_loss = pnl_percent <= -7.0
                    is_great_profit_with_exhaustion = pnl_percent >= 10.0 and early_exit_signals['reversal_score'] >= 7
                    is_strong_reversal = early_exit_signals['reversal_score'] >= 10
                    
                    if not (is_significant_loss or is_great_profit_with_exhaustion or is_strong_reversal):
                        logger.warning(f"🛡️ 진입 주의 구간 (20-40분): {result['decision']} → HOLD")
                        logger.warning(f"   보유 시간: {holding_time:.1f}분, PnL: {pnl_percent:+.2f}%, Reversal Score: {early_exit_signals['reversal_score']}")
                        result['decision'] = 'hold'
                        result['percentage'] = 0
                        result['reason'] = f"🛡️ CAUTION ZONE (20-40min): Original decision was {original_decision}. Conditions not met for early exit. Holding time: {holding_time:.1f}min. Original reason: {result['reason'][:150]}"
                        result['exit_type'] = 'none'
                        result['urgency'] = 'watch'
                
                # 40-60분: 가벼운 주의 (좀 더 유연하게)
                elif holding_time < 60:
                    # 허용 조건: 손실 -5% 이상, 수익 +8% 이상 + 피로 신호(≥6), 또는 역전 점수 8 이상
                    is_moderate_loss = pnl_percent <= -5.0
                    is_good_profit_with_exhaustion = pnl_percent >= 8.0 and early_exit_signals['reversal_score'] >= 6
                    is_moderate_reversal = early_exit_signals['reversal_score'] >= 8
                    
                    if not (is_moderate_loss or is_good_profit_with_exhaustion or is_moderate_reversal):
                        logger.warning(f"🛡️ 진입 관찰 구간 (40-60분): {result['decision']} → HOLD")
                        logger.warning(f"   보유 시간: {holding_time:.1f}분, PnL: {pnl_percent:+.2f}%, Reversal Score: {early_exit_signals['reversal_score']}")
                        result['decision'] = 'hold'
                        result['percentage'] = 0
                        result['reason'] = f"👀 WATCH ZONE (40-60min): Original decision was {original_decision}. Approaching normal monitoring. Holding time: {holding_time:.1f}min. Original reason: {result['reason'][:150]}"
                        result['exit_type'] = 'none'
                        result['urgency'] = 'watch'
            
            logger.info(
                f"✅ 포지션 모니터 결정: {result['decision']} "
                f"({result['percentage']}% / 신뢰도: {result['confidence']:.2f} / "
                f"긴급도: {result['urgency']})"
                f"{' [보호 발동]' if original_decision != result['decision'] else ''}"
            )
            logger.info(f"결정 이유: {result['reason'][:200]}...")
            
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
                del current_positions[symbol]
                clear_peak_profit(symbol)  # 🆕 v7.1 peak profit 기록 삭제
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
                del current_positions[symbol]
                clear_peak_profit(symbol)  # 🆕 v7.1 peak profit 기록 삭제
            elif decision['decision'] == 'partial_close' and symbol in current_positions:
                current_positions[symbol]['amount'] -= position['amount'] * (decision['percentage'] / 100)
        
        # 텔레그램 알림
        if ENABLE_TELEGRAM:
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

def ai_monitoring_cycle(skip_sync=False):
    """
    AI 모니터링 주기 실행
    🆕 개선: 자동/수동 포지션 모두 모니터링
    
    Args:
        skip_sync: True면 동기화 건너뛰기 (이미 sync된 경우)
    """
    global current_positions
    
    logger.info("=== AI Position Monitoring Cycle Start ===")
    logger.info(f"⏰ Monitoring interval: {AI_MONITOR_INTERVAL} minutes")
    logger.info(f"📊 Current positions in memory: {len(current_positions)}")
    
    # 🔄 실제 거래소 포지션과 동기화 (skip_sync가 False일 때만)
    if not skip_sync:
        sync_count = sync_positions_from_exchange()
        logger.info(f"🔄 Synchronized positions: {sync_count}")
    else:
        logger.info("🔄 Sync skipped (already synced)")
    
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
    
    for symbol, position in current_positions.copy().items():
        # AI 모니터링이 활성화된 심볼인지 확인 (🆕 v7.3: 정규화된 심볼 사용)
        if not get_symbol_config(symbol).get('ai_monitoring', True):
            continue
        
        position_type = position.get('position_type', 'auto')
        type_indicator = "🤖" if position_type == 'auto' else "🔧"
        
        logger.info(f"{type_indicator} Monitoring position: {symbol} ({position_type.upper()})")
        
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
                # 🆕 v7.3 수정: 항상 거래소 동기화 먼저 수행 (수동 포지션 감지용)
                # 메모리에 포지션이 없어도 바이낸스에서 수동 포지션이 있을 수 있음
                logger.info("🔄 AI 모니터링: 거래소 포지션 동기화 중...")
                sync_count = sync_positions_from_exchange()
                
                # 동기화 후 포지션이 있으면 AI 모니터링 실행
                if current_positions:
                    logger.info(f"📊 {len(current_positions)}개 포지션 AI 모니터링 시작...")
                    ai_monitoring_cycle(skip_sync=True)  # 이미 sync 했으므로 건너뛰기
                else:
                    logger.debug("No positions to monitor after sync")
                
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
        logger.info(f"   🔄 매 사이클마다 바이낸스 포지션 동기화 수행")

def stop_ai_monitoring():
    """AI 모니터링 중지"""
    global ai_monitor_running
    ai_monitor_running = False
    logger.info("AI position monitoring stopped")

# ============ AI Decision Making (개선 버전) ============
def ai_validate_signal(symbol, action, market_data, recent_trades_df, message_data=None):
    """
    🆕 v7.3: Rule-Based Validation + AI Parameter Adjustment
    
    변경사항:
    1. 기술지표 종합 판단: Rule-Based 로직으로 수행 (정확한 수학적 비교)
    2. AI 역할: 극단적 리스크 필터링 + 파라미터 미세조정만 담당
       - 레버리지: 5~20배
       - 포지션 사이즈: 10~40%
       - TP/SL 조정
    """
    
    logger.info(f"🆕 v7.3 Rule-Based Validation 시작: {symbol} {action.upper()}")
    
    try:
        # ========== STEP 1: Rule-Based Validation ==========
        rule_result = rule_based_validation(symbol, action, market_data)
        
        decision = rule_result['decision']
        risk_score = rule_result['risk_score']['total_score']
        approval_score = rule_result['approval_score']['total_score']
        
        # REJECT인 경우 바로 반환
        if decision == 'reject':
            logger.info(f"❌ Rule-Based REJECT: {rule_result['reason']}")
            
            # DB에 기록
            try:
                conn = init_db()
                timestamp = datetime.now().isoformat()
                c = conn.cursor()
                
                if not is_duplicate_trade_record(conn, symbol, action, 'RULE_BASED', time_window_seconds=10):
                    c.execute("""INSERT INTO trades 
                              (timestamp, symbol, action, ai_decision, confidence, reason, 
                               current_price, trade_type, reflection, percentage, entry_price)
                              VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                              (timestamp, symbol, action, 'reject', 0.0, 
                               f"Rule-Based REJECT: Risk={risk_score}, Approval={approval_score}. {rule_result['reason']}", 
                               market_data['current_price'], 'RULE_BASED', 
                               f"Risk Details: {'; '.join(rule_result['risk_score']['details'])}", 
                               0, market_data['current_price']))
                    conn.commit()
                conn.close()
            except Exception as e:
                logger.error(f"DB 기록 오류: {e}")
            
            # 텔레그램 알림
            if ENABLE_TELEGRAM:
                send_telegram_notification(
                    f"❌ <b>Rule-Based REJECT</b>\n\n"
                    f"<b>심볼:</b> {symbol}\n"
                    f"<b>신호:</b> {action.upper()}\n"
                    f"<b>Risk Score:</b> {risk_score}/8\n"
                    f"<b>Approval Score:</b> {approval_score}/100\n"
                    f"<b>이유:</b> {rule_result['reason']}\n"
                    f"<b>리스크 요인:</b>\n" + 
                    '\n'.join([f"  • {d}" for d in rule_result['risk_score']['details'][:5]]),
                    'warning'
                )
            
            return {
                'decision': 'reject',
                'modified_action': 'hold',
                'percentage': 0,
                'reason': f"Rule-Based REJECT: Risk={risk_score}/8, Approval={approval_score}/100. {rule_result['reason']}",
                'stop_loss_price': 0,
                'take_profit_price': 0,
                'pl_ratio': 0,
                'confidence': 0.0
            }
        
        # 🔄 REVERSE인 경우 - 반전된 방향으로 진입
        if decision == 'reverse':
            modified_action = rule_result['modified_action']
            reverse_score = rule_result['reverse_score']['total_score']
            reverse_signals = rule_result['reverse_score']['signal_count']
            
            logger.info(f"🔄 Rule-Based REVERSE: {action.upper()} → {modified_action.upper()}")
            logger.info(f"   Reverse Score: {reverse_score}/10, Signals: {reverse_signals}/4")
            logger.info(f"   4H Trend did NOT support original signal")
            
            # AI 파라미터 조정 (반전된 액션으로)
            ai_params = ai_parameter_adjustment(symbol, modified_action, rule_result, market_data)
            
            leverage = ai_params['leverage']
            position_pct = ai_params['position_percent']
            stop_loss = ai_params['stop_loss']
            take_profit = ai_params['take_profit']
            pl_ratio = ai_params['pl_ratio']
            
            # 반전 트레이드는 더 낮은 신뢰도
            confidence = min(0.75, approval_score / 100 * 0.8)
            
            result = {
                'decision': 'reverse',
                'modified_action': modified_action,
                'percentage': position_pct,
                'reason': f"🔄 REVERSE: {action.upper()}→{modified_action.upper()}. 4H trend against original. Reverse Score={reverse_score}/10, Signals={reverse_signals}/4. {rule_result['reason']}",
                'stop_loss_price': stop_loss,
                'take_profit_price': take_profit,
                'pl_ratio': pl_ratio,
                'confidence': confidence,
                'leverage': leverage,
                'risk_score': risk_score,
                'approval_score': approval_score,
                'reverse_score': reverse_score
            }
            
            # DB 기록
            try:
                conn = init_db()
                timestamp = datetime.now().isoformat()
                c = conn.cursor()
                
                if not is_duplicate_trade_record(conn, symbol, modified_action, 'RULE_BASED_REVERSE', time_window_seconds=10):
                    c.execute("""INSERT INTO trades 
                              (timestamp, symbol, action, ai_decision, confidence, reason, 
                               current_price, trade_type, reflection, percentage, entry_price)
                              VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                              (timestamp, symbol, modified_action, 'reverse', confidence,
                               result['reason'], market_data['current_price'], 'RULE_BASED_REVERSE',
                               f"Original: {action.upper()} | Reverse Details: {'; '.join(rule_result['reverse_score']['details'][:3])}",
                               position_pct, market_data['current_price']))
                    conn.commit()
                conn.close()
            except Exception as e:
                logger.error(f"DB 기록 오류: {e}")
            
            # 텔레그램 알림
            if ENABLE_TELEGRAM:
                reverse_details = '\n'.join([f"  • {d}" for d in rule_result['reverse_score']['details'][:5]])
                send_telegram_notification(
                    f"🔄 <b>v7.3 REVERSE SIGNAL (4H Trend Against)</b>\n\n"
                    f"<b>심볼:</b> {symbol}\n"
                    f"<b>원래 신호:</b> {action.upper()} ❌\n"
                    f"<b>반전 신호:</b> {modified_action.upper()} ✅\n"
                    f"<b>Reverse Score:</b> {reverse_score}/10\n"
                    f"<b>Extreme Signals:</b> {reverse_signals}/4\n"
                    f"<b>레버리지:</b> {leverage}x\n"
                    f"<b>포지션:</b> {position_pct}%\n"
                    f"<b>SL:</b> ${stop_loss:,.2f}\n"
                    f"<b>TP:</b> ${take_profit:,.2f}\n"
                    f"<b>R:R:</b> {pl_ratio:.2f}\n\n"
                    f"<b>극단 신호 (4H 기준):</b>\n{reverse_details}",
                    'warning'
                )
            
            logger.info(f"🔄 v7.3 REVERSE 완료: {modified_action.upper()} - Lev={leverage}x, Size={position_pct}%, R:R={pl_ratio:.2f}")
            
            return result
        
        # ========== STEP 2: AI Parameter Adjustment ==========
        logger.info(f"✅ Rule-Based {decision.upper()}: 진행하여 AI 파라미터 조정")
        
        ai_params = ai_parameter_adjustment(symbol, action, rule_result, market_data)
        
        # 결과 구성
        final_decision = ai_params['decision']
        leverage = ai_params['leverage']
        position_pct = ai_params['position_percent']
        stop_loss = ai_params['stop_loss']
        take_profit = ai_params['take_profit']
        pl_ratio = ai_params['pl_ratio']
        
        # confidence 계산 (approval_score 기반)
        confidence = min(0.95, approval_score / 100)
        
        result = {
            'decision': 'approve' if final_decision == 'approve' else 'modify',
            'modified_action': action,
            'percentage': position_pct,
            'reason': f"Rule-Based {decision.upper()}: Risk={risk_score}/8, Approval={approval_score}/100. Leverage={leverage}x, Size={position_pct}%. {ai_params.get('reason', '')}",
            'stop_loss_price': stop_loss,
            'take_profit_price': take_profit,
            'pl_ratio': pl_ratio,
            'confidence': confidence,
            'leverage': leverage,  # 추가 필드
            'risk_score': risk_score,
            'approval_score': approval_score
        }
        
        # DB 기록
        try:
            conn = init_db()
            timestamp = datetime.now().isoformat()
            c = conn.cursor()
            
            if not is_duplicate_trade_record(conn, symbol, action, 'RULE_BASED', time_window_seconds=10):
                c.execute("""INSERT INTO trades 
                          (timestamp, symbol, action, ai_decision, confidence, reason, 
                           current_price, trade_type, reflection, percentage, entry_price)
                          VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                          (timestamp, symbol, action, result['decision'], confidence,
                           result['reason'], market_data['current_price'], 'RULE_BASED',
                           f"Risk: {'; '.join(rule_result['risk_score']['details'][:3])} | Approval: {'; '.join(rule_result['approval_score']['details'][:3])}",
                           position_pct, market_data['current_price']))
                conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"DB 기록 오류: {e}")
        
        # 텔레그램 알림
        if ENABLE_TELEGRAM:
            emoji = "✅" if final_decision == 'approve' else "⚠️"
            send_telegram_notification(
                f"{emoji} <b>v7.3 Rule-Based {final_decision.upper()}</b>\n\n"
                f"<b>심볼:</b> {symbol}\n"
                f"<b>신호:</b> {action.upper()}\n"
                f"<b>Risk Score:</b> {risk_score}/8\n"
                f"<b>Approval Score:</b> {approval_score}/100\n"
                f"<b>레버리지:</b> {leverage}x\n"
                f"<b>포지션:</b> {position_pct}%\n"
                f"<b>SL:</b> ${stop_loss:,.2f}\n"
                f"<b>TP:</b> ${take_profit:,.2f}\n"
                f"<b>R:R:</b> {pl_ratio:.2f}",
                'success' if final_decision == 'approve' else 'info'
            )
        
        logger.info(f"✅ v7.3 검증 완료: {result['decision'].upper()} - Lev={leverage}x, Size={position_pct}%, R:R={pl_ratio:.2f}")
        
        return result
        
    except Exception as e:
        logger.error(f"v7.3 검증 오류: {e}", exc_info=True)
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

def escape_html(text):
    """HTML 특수 문자 이스케이프"""
    if not isinstance(text, str):
        text = str(text)
    return text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

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
    
    # HTML 특수 문자 이스케이프 (단, 의도적인 HTML 태그는 유지)
    # <b>, </b>, <i>, </i>, <code>, </code> 등은 유지
    safe_message = message
    # 먼저 허용된 태그를 임시 치환
    allowed_tags = ['<b>', '</b>', '<i>', '</i>', '<code>', '</code>', '<pre>', '</pre>', '<u>', '</u>', '<s>', '</s>']
    placeholders = {}
    for i, tag in enumerate(allowed_tags):
        placeholder = f"__TAG_PLACEHOLDER_{i}__"
        placeholders[placeholder] = tag
        safe_message = safe_message.replace(tag, placeholder)
    
    # 나머지 < > & 이스케이프
    safe_message = safe_message.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
    
    # 허용된 태그 복원
    for placeholder, tag in placeholders.items():
        safe_message = safe_message.replace(placeholder, tag)
    
    formatted_message = f"{emoji} {safe_message}"
    
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
        config = get_symbol_config(symbol)  # 🆕 v7.3: 정규화된 심볼 사용
        
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
        config = get_symbol_config(symbol)  # 🆕 v7.3: 정규화된 심볼 사용
        position_size_percent = config.get('position_size_percent', DEFAULT_POSITION_SIZE_PERCENT)
        position_size = balance * (position_size_percent / 100)
        min_size = config.get('min_position_size', 10)
        max_size = config.get('max_position_size', 100000)
        position_size = max(min_size, min(position_size, max_size))
        return position_size, position_size_percent

def set_leverage(symbol):
    """심볼별 레버리지 설정"""
    try:
        config = get_symbol_config(symbol)  # 🆕 v7.3: 정규화된 심볼 사용
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
            
            # 레버리지 설정 (🆕 v7.3: 정규화된 심볼 사용)
            try:
                leverage = get_symbol_config(symbol).get('leverage', 10)
                user_exchange.set_leverage(leverage, symbol)
                logger.info(f"[{user_name}] 레버리지 설정: {leverage}x")
            except Exception as e:
                logger.warning(f"[{user_name}] 레버리지 설정 실패: {str(e)}")
            
            # 각 유저의 잔고에 맞게 수량 재계산
            balance_info = user_exchange.fetch_balance()
            usdt_balance = balance_info['USDT']['free']
            position_percent = get_symbol_config(symbol).get('position_size_percent', 30)
            position_size = usdt_balance * (position_percent / 100)
            
            ticker = user_exchange.fetch_ticker(symbol)
            current_price = ticker['last']
            leverage = get_symbol_config(symbol).get('leverage', 10)
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
    
    # Primary User의 주문 정보 반환 (기존 코드 호환성)
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
    
    return success_count


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
        config = get_symbol_config(symbol)  # 🆕 v7.3: 정규화된 심볼 사용
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
        
        # 심볼 설정 확인 (🆕 v7.3: 정규화된 심볼 사용)
        if not is_symbol_configured(symbol):
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
        
        if not get_symbol_config(symbol).get('enabled', True):
            error_msg = f'심볼 {symbol}이(가) 비활성화됨'
            logger.warning(f"⚠️ {error_msg}")
            return jsonify({'error': error_msg}), 400
        
        logger.info(f"✅ 심볼 검증 완료: {symbol}")
        
        # 심볼 설정 가져오기 (🆕 v7.3: 정규화된 심볼 사용)
        symbol_config = get_symbol_config(symbol)
        
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
                    success_count = close_position_for_all_users(symbol)
                    
                    if success_count > 0:
                        # Primary User로 포지션 정보 조회 (메시지 표시용)
                        try:
                            ticker = exchange.fetch_ticker(symbol)
                            current_price = ticker['last']
                            
                            message = f"""
✅ <b>포지션 청산 완료 (Multi-User)</b>

<b>심볼:</b> {symbol}
<b>청산 성공:</b> {success_count}/{len(exchanges)}명
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
                            del current_positions[symbol]
                            clear_peak_profit(symbol)  # 🆕 v7.1 peak profit 기록 삭제
                        
                        return jsonify({
                            'status': 'closed',
                            'symbol': symbol,
                            'success_count': success_count,
                            'total_users': len(exchanges),
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
            position_percent = get_symbol_config(symbol).get('position_size_percent', 10)  # 🆕 v7.3: 정규화된 심볼 사용
            
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
    """즉시 AI 모니터링 실행 (🆕 v7.3: 먼저 동기화 수행)"""
    # 🆕 먼저 거래소와 동기화 (수동 포지션 감지용)
    sync_count = sync_positions_from_exchange()
    
    if not current_positions:
        return jsonify({
            'status': 'info',
            'message': 'No positions to monitor (sync completed, no active positions)',
            'synced_count': sync_count
        }), 200
    
    monitored, exits = ai_monitoring_cycle(skip_sync=True)  # 이미 sync 했으므로 건너뛰기
    
    return jsonify({
        'status': 'success',
        'positions_monitored': monitored,
        'exit_decisions': exits,
        'synced_count': sync_count
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

def initialize_bot():
    """봇 초기화"""
    logger.info(f"봇 초기화 중... (포트: {SERVER_PORT})")
    
    # 데이터베이스 초기화 (프로그램 시작 시 1회)
    init_db_once()
    
    # 거래소 연결 테스트
    try:
        balance = exchange.fetch_balance()
        usdt_balance = balance['USDT']['free']
        logger.info(f"거래소 연결 성공. USDT 잔고: ${usdt_balance:,.2f}")
    except Exception as e:
        logger.error(f"거래소 연결 실패: {str(e)}")
    
    # 🔄 실제 포지션 동기화 (서버 재시작 시 복구)
    try:
        position_count = sync_positions_from_exchange()
        if position_count > 0:
            logger.info(f"✅ {position_count}개의 기존 포지션 복구 완료")
            position_summary = get_position_summary()
            logger.info(f"복구된 포지션:\n{position_summary}")
        else:
            logger.info("복구할 포지션 없음 (새로 시작)")
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
    
    if ENABLE_TELEGRAM:
        # 🆕 포지션 타입별 카운트
        auto_count = sum(1 for pos in current_positions.values() if pos.get('position_type', 'auto') == 'auto')
        manual_count = sum(1 for pos in current_positions.values() if pos.get('position_type', 'auto') == 'manual')
        
        position_info = ""
        if len(current_positions) > 0:
            position_info = f"\n\n<b>복구된 포지션:</b>\n{get_position_summary()}"
        
        startup_message = f"""
🚀 <b>통합 트레이딩 시스템 v7.0 시작 (Multi-User Edition)</b>

<b>🆕 v7.0 Multi-User 핵심 기능:</b>
👥 <b>다중 유저 동시 거래</b>
  → 하나의 서버에서 최대 3명의 계정 관리
  → Primary User: AI 검증 + DB + 텔레그램
  → Secondary Users: 바이낸스 주문만 실행
🗑️ <b>TP/SL 자동 삭제</b>
  → 포지션 종료 시 해당 심볼의 모든 주문 자동 취소
  → 수동/자동 청산 모두 적용
  → 모든 유저에 대해 동시 처리
🔄 <b>동기화된 거래 실행</b>
  → TradingView 시그널을 모든 유저에게 전파
  → 각 유저의 잔고에 맞게 수량 자동 조정
  → 레버리지 독립 관리

<b>📊 v6.1 기능 (모두 유지):</b>

<b>🔥 v6.1 적절한 리스크 관리 개선사항:</b>
💡 <b>균형잡힌 TP/SL 설정</b>
  → TP: 최대 7% (권장 3.0-4.0%)
  → SL: 최대 2% (권장 0.8-2.0%)
  → 리스크와 수익의 균형
🚨 <b>스마트한 포지션 종료 기준</b>
  → 1.5% 이상 수익 시 종료 신호 강화
  → 최고점 대비 30% 하락 시 수익 보호
  → 과열 구간 기준 RSI 70/30
🔧 <b>JSON 파싱 오류 자동 복구</b>
  → 최소 정보(심볼/액션)로 거래 가능
  → AI가 TP/SL 및 수량 자동 설정
  → 긴급 모드에서도 균형잡힌 파라미터 적용

<b>📊 v6.0 핵심 기능 (유지):</b>
🎯 과매수/과매도 멀티 타임프레임 필터링
  → 진입 조건 강화: 1시간/4시간봉 과열 구간 자동 차단
  → 리스크 점수 기반 진입 승인/거부
💡 매물대 기반 TP/SL 자동 조정
  → 거래량 프로파일 분석으로 현실적 목표가 설정
  → 지지/저항선 고려한 손절가 최적화
  → ATR 기반 최소/최대 거리 보장
🚨 추세 역전 조기 신호 감지 시스템
  → Divergence, MACD, ADX, CMF 종합 분석
  → 역전 점수 기반 긴급도 자동 판단
  → AI 모니터링에 실시간 통합

<b>📊 기존 v5.1 기능 (모두 유지):</b>
✨ 수동 포지션 자동 감지 및 AI 모니터링
✨ 포지션 타입 구분 (자동/수동)
✨ DB 기록 개선 (position_type)
✅ 마진 부족 100% 방지
✅ Free Balance 기반 자동 포지션 크기 조정
✅ 대시보드 완벽 호환

<b>⚙️ 서버 정보:</b>
<b>서버 포트:</b> {SERVER_PORT} (Multi-User)
<b>활성 유저:</b> {len(exchanges)}명
<b>활성 심볼:</b> {len(enabled_symbols)}개
<b>AI 검증:</b> {len(ai_symbols)}개 심볼
<b>AI 모니터링:</b> {len(ai_monitor_symbols)}개 심볼
<b>모니터링 주기:</b> {AI_MONITOR_INTERVAL}분
<b>현재 포지션:</b> {len(current_positions)}개
  - 🤖 자동: {auto_count}개
  - 🔧 수동: {manual_count}개{position_info}

✅ 시스템이 정상적으로 시작되었습니다.
🎯 과매수/과매도 필터 활성화
💡 TP/SL 자동 조정 활성화
🚨 조기 종료 신호 감지 활성화
🤖 AI 포지션 모니터링 활성화
🔧 수동 포지션 자동 감지 활성화
🔄 거래소 포지션 자동 동기화 활성화
📊 서버 재시작 시 포지션 자동 복구
💾 주기적 데이터 기록 활성화 (5분)

⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
        """.strip()
        send_telegram_notification(startup_message, 'success')

if __name__ == '__main__':
    initialize_bot()
    app.run(host='0.0.0.0', port=SERVER_PORT, debug=False, threaded=True)  # 명시적 멀티스레드 설정