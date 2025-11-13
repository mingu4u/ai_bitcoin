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
    🆕 개선: 수동 포지션 감지 및 position_type 필드 추가
    """
    global current_positions
    
    try:
        logger.info("=== 거래소 포지션 동기화 시작 (수동 포지션 감지 포함) ===")
        
        # 모든 활성 심볼에 대해 포지션 조회
        synced_count = 0
        manual_count = 0  # 🆕 수동 포지션 카운트
        new_positions = {}
        
        for symbol in SYMBOL_CONFIG.keys():
            if not SYMBOL_CONFIG[symbol].get('enabled', True):
                continue
            
            try:
                # 거래소에서 실제 포지션 조회
                positions = exchange.fetch_positions([symbol])
                
                for position in positions:
                    contracts = float(position.get('contracts', 0))
                    
                    if contracts != 0:  # 포지션이 있는 경우
                        entry_price = float(position.get('entryPrice', 0))
                        side = 'buy' if position['side'] == 'long' else 'sell'
                        
                        # 기존 포지션 정보가 있으면 유지, 없으면 새로 생성
                        if symbol in current_positions:
                            # 기존 정보 유지 (SL/TP, position_type 등)
                            new_positions[symbol] = current_positions[symbol]
                            # 수량과 진입가는 거래소 기준으로 업데이트
                            new_positions[symbol]['amount'] = abs(contracts)
                            new_positions[symbol]['entry_price'] = entry_price
                            logger.info(f"✓ {symbol} 포지션 업데이트: {side} {abs(contracts):.4f} @ ${entry_price:.2f} (타입: {new_positions[symbol].get('position_type', 'auto')})")
                        else:
                            # 🆕 새로운 포지션 발견 → 수동 포지션으로 간주
                            new_positions[symbol] = {
                                'side': side,
                                'entry_price': entry_price,
                                'amount': abs(contracts),
                                'stop_loss': 0,  # 실제 SL/TP는 거래소에서 조회 가능하지만 간단히 0으로
                                'take_profit': 0,
                                'trailing_stop_percent': DEFAULT_TRAILING_STOP_PERCENT,
                                'trailing_activation_percent': DEFAULT_TRAILING_ACTIVATION_PERCENT,
                                'entry_time': datetime.now(),  # 동기화 시점을 진입 시간으로
                                'position_type': 'manual',  # 🆕 수동 포지션으로 표시
                                'leverage': SYMBOL_CONFIG[symbol].get('leverage', 10)
                            }
                            logger.info(f"🆕🔧 {symbol} 수동 포지션 발견: {side} {abs(contracts):.4f} @ ${entry_price:.2f}")
                            logger.info(f"   → AI 모니터링 대상에 자동 추가됨")
                            synced_count += 1
                            manual_count += 1
                            
                            # 🆕 텔레그램 알림 (수동 포지션 감지)
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
                        
            except Exception as e:
                logger.error(f"{symbol} 포지션 조회 오류: {str(e)}")
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
                logger.warning(f"⚠️ {symbol} 포지션이 거래소에 없어 메모리에서 제거 및 DB 기록")
        
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
                  position_type TEXT DEFAULT 'auto')''')
    
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
        
        json_template = """
{
    "decision": "hold",
    "percentage": 0,
    "reason": "Strong momentum continues, no reversal signals detected",
    "exit_type": "none",
    "confidence": 0.85,
    "urgency": "none"
}"""

        prompt = f"""
You are an elite AI position manager monitoring an active {side.upper()} position for {symbol}. Your mission is to protect profits, minimize losses, and identify optimal exit points using multi-timeframe analysis.

**CRITICAL CONTEXT:**
This is a LEVERAGED position ({leverage}x) - small price movements have AMPLIFIED impact on P&L.

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
- decision: "hold", "close", or "partial_close"
- percentage: 0 for hold, 100 for full close, 25-75 for partial
- reason: **MUST be technical and specific, not based on arbitrary percentages**
- exit_type: "take_profit", "stop_loss", "trend_reversal", "risk_management", "time_stop", or "none"
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
    🆕 자동/수동 포지션 모두 지원
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
        
        logger.info(f"{type_indicator} Position exit executed for {symbol} ({position_type.upper()}): {decision['decision']}")
        
        # 완료된 거래 DB 기록
        try:
            ticker = exchange.fetch_ticker(symbol)
            exit_price = ticker['last']
            
            if decision['decision'] == 'close':
                # 전체 종료인 경우
                record_completed_trade(symbol, position, exit_price, decision.get('exit_type', 'ai_exit'))
                logger.info(f"✅ Completed trade recorded for {symbol} ({position_type.upper()})")
                del current_positions[symbol]
            else:
                # 부분 종료인 경우
                partial_position = position.copy()
                partial_position['amount'] = exit_amount
                record_completed_trade(symbol, partial_position, exit_price, 'partial_' + decision.get('exit_type', 'exit'))
                logger.info(f"✅ Partial trade recorded for {symbol} ({position_type.upper()})")
                current_positions[symbol]['amount'] -= exit_amount
                
        except Exception as e:
            logger.error(f"Failed to record completed trade: {e}")
            # 오류가 나도 포지션은 정리
            if decision['decision'] == 'close' and symbol in current_positions:
                del current_positions[symbol]
            elif decision['decision'] == 'partial_close' and symbol in current_positions:
                current_positions[symbol]['amount'] -= exit_amount
        
        # 텔레그램 알림
        if ENABLE_TELEGRAM:
            message = f"""
{type_indicator} <b>AI Position Exit</b>

<b>Type:</b> {position_type.upper()} 포지션
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
    """
    AI 모니터링 주기 실행
    🆕 개선: 자동/수동 포지션 모두 모니터링
    """
    global current_positions
    
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
    
    for symbol, position in current_positions.copy().items():
        # AI 모니터링이 활성화된 심볼인지 확인
        if not SYMBOL_CONFIG.get(symbol, {}).get('ai_monitoring', True):
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
        
        try:
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
                    # 'reduceOnly': True,
                    'closePosition': True  # 모든 포지션 정리
                }
            )
            
            logger.info(f"✅ 스탑로스 주문 완료 - {symbol} @ ${stop_loss_price:.2f} (closePosition=True)")
        except Exception as sl_error:
            logger.error(f"⚠️ 스탑로스 설정 실패: {str(sl_error)}")
            sl_order = None
        
        try:
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
                    # 'reduceOnly': True,
                    'closePosition': True  # 모든 포지션 정리
                }
            )
            
            logger.info(f"✅ 테이크프로핏 주문 완료 - {symbol} @ ${take_profit_price:.2f} (closePosition=True)")
        except Exception as tp_error:
            logger.error(f"⚠️ 테이크프로핏 설정 실패: {str(tp_error)}")
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
                amount=amount,
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
                            
                            # 🔥 추가: 완료된 거래 DB 기록
                            try:
                                position_info = {
                                    'entry_price': float(position['entryPrice']),
                                    'amount': close_amount,
                                    'side': 'buy' if position['side'] == 'long' else 'sell',
                                    'leverage': symbol_config.get('leverage', 10),
                                    'entry_time': datetime.now() - timedelta(hours=1)  # 실제 진입 시간을 모르므로 임시
                                }
                                ticker = exchange.fetch_ticker(symbol)
                                current_price = ticker['last']
                                record_completed_trade(symbol, position_info, current_price, 'webhook_close')
                                logger.info(f"✅ Completed trade recorded for {symbol} (webhook close)")
                            except Exception as e:
                                logger.error(f"Failed to record completed trade in webhook: {e}")
                            
                            closed_positions.append({
                                'side': position['side'],
                                'amount': close_amount,
                                'entry_price': float(position['entryPrice'])
                            })
                            
                            # 현재가 조회
                            ticker = exchange.fetch_ticker(symbol)
                            current_price = ticker['last']
                            
                            # PnL 계산 (레버리지 반영)
                            leverage = symbol_config.get('leverage', 10)
                            if position['side'] == 'long':
                                price_change_percent = ((current_price - float(position['entryPrice'])) / float(position['entryPrice'])) * 100
                            else:
                                price_change_percent = ((float(position['entryPrice']) - current_price) / float(position['entryPrice'])) * 100
                            
                            # 레버리지 적용 - 실제 수익률
                            pnl_percent = price_change_percent * leverage
                            
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
            orders = place_orders_with_sl_tp(
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
🚀 <b>통합 트레이딩 시스템 v5.1 시작</b>

<b>🆕 신규 기능:</b>
✨ 수동 포지션 자동 감지
✨ 수동 포지션 AI 모니터링
✨ 포지션 타입 구분 (자동/수동)
✨ DB 기록 개선 (position_type)

<b>주요 개선사항:</b>
✅ 마진 부족 100% 방지
✅ Free Balance 기반 계산
✅ 자동 포지션 크기 조정
✅ 대시보드 완벽 호환

<b>서버 포트:</b> {SERVER_PORT}
<b>활성 심볼:</b> {len(enabled_symbols)}개
<b>AI 검증:</b> {len(ai_symbols)}개 심볼
<b>AI 모니터링:</b> {len(ai_monitor_symbols)}개 심볼
<b>모니터링 주기:</b> {AI_MONITOR_INTERVAL}분
<b>현재 포지션:</b> {len(current_positions)}개
  - 🤖 자동: {auto_count}개
  - 🔧 수동: {manual_count}개{position_info}

✅ 시스템이 정상적으로 시작되었습니다.
🤖 AI 포지션 모니터링이 활성화되었습니다.
🔧 수동 포지션 자동 감지가 활성화되었습니다.
🔄 거래소 포지션 자동 동기화 활성화
📊 서버 재시작 시 포지션 자동 복구
💾 주기적 데이터 기록 활성화 (5분)

⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
        """.strip()
        send_telegram_notification(startup_message, 'success')

if __name__ == '__main__':
    initialize_bot()
    app.run(host='0.0.0.0', port=SERVER_PORT, debug=False, threaded=True)  # 명시적 멀티스레드 설정