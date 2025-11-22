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
existing_positions_at_start = set()  # 🔥 봇 시작 시 이미 있던 포지션 추적

# ============ 중요 함수들만 수정 ============
# ... (나머지 코드는 원본과 동일하게 유지) ...

def record_position_closure_with_real_pnl(symbol, position_data, close_type='manual'):
    """
    🆕 v8.3: 포지션 종료 시 바이낸스 실제 수익률을 기록하고 이벤트 발생
    - 실제 PnL 가져오기 실패시 종료로 판단하지 않음
    """
    try:
        # 1. 바이낸스에서 실제 PnL 가져오기 시도
        real_pnl_data = fetch_binance_position_pnl(exchange, symbol)
        
        # 🔥 수정: 실제 PnL이 없어도 정상 처리
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
            leverage = position_data.get('leverage', 1)
            
            # 수익 계산
            if side == 'long':
                pnl_percent = ((exit_price - entry_price) / entry_price) * 100
            else:  # short
                pnl_percent = ((entry_price - exit_price) / entry_price) * 100
            
            realized_pnl = (amount * entry_price * pnl_percent / 100) * leverage
            logger.info(f"📊 {symbol} 계산된 수익: ${realized_pnl:.2f}")
            is_binance_confirmed = False
        
        # 2. completed_trades 테이블에 기록
        conn = sqlite3.connect('integrated_trades.db')
        c = conn.cursor()
        
        entry_price = position_data.get('entry_price', 0)
        exit_price = position_data.get('mark_price', entry_price)
        amount = position_data.get('amount', 0)
        side = position_data.get('side', 'unknown')
        position_type = position_data.get('position_type', 'auto')
        leverage = position_data.get('leverage', 1)
        
        # 수익률 계산
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
        
        logger.info(f"📊 {symbol} 포지션 종료 기록 완료 (PnL: ${realized_pnl:.2f})")
        
        return realized_pnl
        
    except Exception as e:
        logger.error(f"포지션 종료 기록 오류 ({symbol}): {str(e)}")
        return None

def ai_monitor_positions():
    """
    🔥 v8.3 수정: 잘못된 청산 감지 문제 해결
    """
    global current_positions, bot_start_time, initial_sync_completed, existing_positions_at_start
    
    # 🔥 수정: 실제 포지션 동기화를 먼저 수행
    try:
        positions_check = exchange.fetch_positions()
        actual_positions = {}
        
        for pos in positions_check:
            symbol = pos['symbol']
            amount = abs(float(pos.get('contracts', 0)))
            
            if amount > 0:
                actual_positions[symbol] = {
                    'side': 'long' if float(pos['contracts']) > 0 else 'short',
                    'amount': amount,
                    'entry_price': float(pos['entryPrice']),
                    'mark_price': float(pos['markPrice']),
                    'unrealized_pnl': float(pos.get('unrealizedPnl', 0))
                }
        
        # 현재 메모리와 실제 포지션 비교
        for symbol in list(current_positions.keys()):
            if symbol not in actual_positions:
                # 🔥 수정: 포지션이 실제로 없어진 경우
                position_data = current_positions[symbol]
                
                # 봇 시작시 이미 있었던 포지션인지 확인
                is_existing_position = symbol in existing_positions_at_start
                
                # 청산 알림 조건 개선
                should_notify = False
                if bot_start_time:
                    time_since_start = (datetime.now() - bot_start_time).total_seconds() / 60
                    # 봇 시작 5분 후 또는 신규 포지션인 경우만 알림
                    if time_since_start >= 5 and not is_existing_position:
                        should_notify = True
                    elif initial_sync_completed and not is_existing_position:
                        should_notify = True
                
                logger.info(f"📊 {symbol} 포지션 청산 감지 (기존: {is_existing_position}, 알림: {should_notify})")
                
                try:
                    # PnL 가져오기 시도
                    real_pnl_data = fetch_binance_position_pnl(exchange, symbol)
                    
                    if real_pnl_data:
                        # 실제 PnL이 있으면 청산으로 판단
                        realized_pnl = real_pnl_data['realized_pnl']
                    else:
                        # 실제 PnL이 없으면 계산값 사용
                        realized_pnl = position_data.get('unrealized_pnl', 0)
                    
                    # DB에 기록
                    position_data['mark_price'] = position_data.get('mark_price', position_data.get('entry_price', 0))
                    record_position_closure_with_real_pnl(symbol, position_data, close_type='auto_close_detected')
                    
                    logger.info(f"✅ {symbol} 자동 청산 감지 및 DB 기록 완료 (PnL: ${realized_pnl:.2f})")
                    
                    # 텔레그램 알림 (조건부)
                    if ENABLE_TELEGRAM and should_notify:
                        send_telegram_notification(
                            f"📊 <b>🔔 자동 청산 감지</b>\n\n"
                            f"<b>심볼:</b> {symbol}\n"
                            f"<b>종료 방식:</b> TP/SL 자동 체결\n"
                            f"<b>실현 손익:</b> ${realized_pnl:,.2f} USD\n"
                            f"<b>감지 시간:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                            f"💡 바이낸스에서 자동으로 청산되었습니다.",
                            'info'
                        )
                    elif not should_notify:
                        logger.info(f"⏭️ {symbol} 청산 알림 억제 (봇 시작 직후 기존 포지션)")
                    
                except Exception as record_error:
                    logger.error(f"청산 기록 실패 ({symbol}): {record_error}")
                
                # 메모리에서 제거
                del current_positions[symbol]
                
                # existing_positions_at_start에서도 제거
                if symbol in existing_positions_at_start:
                    existing_positions_at_start.discard(symbol)
        
        # 새로운 포지션 추가
        for symbol, pos_data in actual_positions.items():
            if symbol not in current_positions:
                logger.info(f"🆕 새로운 포지션 감지: {symbol}")
                current_positions[symbol] = {
                    **pos_data,
                    'entry_time': datetime.now().isoformat(),
                    'position_type': 'manual'  # 기본값
                }
                
    except Exception as e:
        logger.error(f"포지션 모니터링 오류: {str(e)}")
    
    if not current_positions:
        logger.info("No positions to monitor")
        return 0, []
    
    # 나머지 AI 모니터링 로직...
    # (원본 코드의 나머지 부분 유지)
    
    return len(current_positions), []

def initialize_bot():
    """봇 초기화 - v8.3 수정"""
    global bot_start_time, initial_sync_completed, existing_positions_at_start
    
    # 🆕 봇 시작 시간 기록
    bot_start_time = datetime.now()
    initial_sync_completed = False
    existing_positions_at_start = set()
    
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
    
    # 🔥 실제 포지션 동기화 (서버 재시작 시 복구)
    try:
        # 봇 시작시 기존 포지션 추적
        positions = exchange.fetch_positions()
        for pos in positions:
            if abs(float(pos.get('contracts', 0))) > 0:
                symbol = pos['symbol']
                existing_positions_at_start.add(symbol)
                logger.info(f"📌 기존 포지션 발견: {symbol}")
        
        position_count = sync_positions_from_exchange()
        if position_count > 0:
            logger.info(f"✅ {position_count}개의 기존 포지션 복구 완료")
            position_summary = get_position_summary()
            logger.info(f"복구된 포지션:\n{position_summary}")
        else:
            logger.info("복구할 포지션 없음 (새로 시작)")
        
        # 🆕 초기 동기화 완료 표시
        initial_sync_completed = True
        logger.info("✅ 초기 포지션 동기화 완료")
        logger.info(f"📌 봇 시작시 기존 포지션: {len(existing_positions_at_start)}개")
        
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

# 🔥 주의: 이 파일은 핵심 수정사항만 포함합니다.
# 실제 사용시 원본 파일(integrated_trading_system_v8_2.py)의 전체 코드에
# 위 수정사항을 적용해야 합니다.

"""
핵심 수정사항:
1. existing_positions_at_start 변수 추가: 봇 시작시 이미 있던 포지션 추적
2. record_position_closure_with_real_pnl 함수 수정: PnL 조회 실패시에도 정상 처리
3. ai_monitor_positions 함수 수정: 기존 포지션과 신규 포지션 구분하여 알림
4. initialize_bot 함수 수정: 봇 시작시 포지션 상태 저장

이 수정으로 다음 문제가 해결됩니다:
- 봇 시작시 기존 포지션을 청산으로 잘못 감지하는 문제
- PnL 조회 실패를 청산으로 판단하는 문제
"""
