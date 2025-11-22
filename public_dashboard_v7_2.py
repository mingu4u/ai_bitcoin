#!/usr/bin/env python3
"""
Public Dashboard v7.0 - Realtime Streaming Edition
실시간 이벤트 기반 업데이트, 빠른 새로고침, 바이낸스 실제 PnL 표시

주요 개선사항:
1. 🆕 실시간 이벤트 폴링 시스템
2. 🆕 2초 간격 빠른 자동 새로고침
3. 🆕 이벤트 감지 시 즉시 업데이트
4. 🆕 바이낸스 실제 PnL 표시 (계산값과 구분)
5. 기존 v6.1 모든 기능 유지

사용 방법:
    streamlit run public_dashboard_v7_REALTIME.py

작성일: 2025-11-22
버전: v7.0 Realtime
"""

import streamlit as st
import sys
import os
from datetime import datetime, timedelta
import json
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
import sqlite3
import ccxt
from dotenv import load_dotenv
import requests
import time as time_module

load_dotenv()

# 페이지 설정
st.set_page_config(
    page_title="Trading Dashboard v7.0 - Realtime Streaming",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ============ 🆕 v7.0 실시간 설정 ============
REALTIME_ENABLED = True  # 실시간 업데이트 활성화
EVENT_POLL_INTERVAL = 2  # 이벤트 폴링 간격 (초)
AUTO_REFRESH_INTERVAL = 3  # 자동 새로고침 간격 (초)
TRADING_BOT_URL = "http://localhost:5000"  # 자동매매 봇 URL

# CSS 스타일 (기존 유지 + 신규 추가)
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        background: linear-gradient(120deg, #1f77b4, #2ca02c);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        text-align: center;
        margin-bottom: 1rem;
    }
    
    .realtime-badge {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        padding: 0.5rem 1rem;
        border-radius: 20px;
        font-size: 0.9rem;
        font-weight: bold;
        display: inline-block;
        animation: pulse 2s infinite;
    }
    
    @keyframes pulse {
        0%, 100% { opacity: 1; }
        50% { opacity: 0.7; }
    }
    
    .event-notification {
        background: #fff3cd;
        border-left: 4px solid #ffc107;
        padding: 1rem;
        margin: 1rem 0;
        border-radius: 5px;
        animation: slideIn 0.3s ease-out;
    }
    
    @keyframes slideIn {
        from {
            transform: translateX(-20px);
            opacity: 0;
        }
        to {
            transform: translateX(0);
            opacity: 1;
        }
    }
    
    .sync-status {
        padding: 0.5rem 1rem;
        border-radius: 5px;
        margin: 1rem 0;
    }
    
    .sync-ok {
        background: #d4edda;
        color: #155724;
        border: 1px solid #c3e6cb;
    }
    
    .sync-warning {
        background: #fff3cd;
        color: #856404;
        border: 1px solid #ffeeba;
    }
    
    .sync-error {
        background: #f8d7da;
        color: #721c24;
        border: 1px solid #f5c6cb;
    }
    
    .position-card {
        background: white;
        border-radius: 10px;
        padding: 1rem;
        margin: 0.5rem 0;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }
    
    .exchange-badge {
        background: #007bff;
        color: white;
        padding: 0.25rem 0.5rem;
        border-radius: 3px;
        font-size: 0.8rem;
    }
    
    .db-badge {
        background: #6c757d;
        color: white;
        padding: 0.25rem 0.5rem;
        border-radius: 3px;
        font-size: 0.8rem;
    }
    
    .binance-verified {
        background: #28a745;
        color: white;
        padding: 0.25rem 0.5rem;
        border-radius: 3px;
        font-size: 0.8rem;
    }
    
    .period-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        padding: 1rem;
        border-radius: 10px;
        text-align: center;
    }
</style>
""", unsafe_allow_html=True)

# ==========================================
# 🆕 v7.0 실시간 이벤트 함수
# ==========================================

def fetch_unread_events():
    """
    자동매매 봇에서 미처리 이벤트 가져오기
    """
    try:
        response = requests.get(f"{TRADING_BOT_URL}/events/unread", timeout=5)
        
        if response.status_code == 200:
            data = response.json()
            return data.get('events', [])
        else:
            # 봇이 구버전이거나 엔드포인트가 없을 수 있음
            return []
            
    except requests.exceptions.ConnectionError:
        # 봇이 실행 중이 아님
        return []
    except requests.exceptions.Timeout:
        # 봇 응답 없음
        return []
    except Exception as e:
        # 기타 오류는 조용히 처리
        return []

def fetch_system_status():
    """
    🆕 자동매매 봇의 시스템 상태 조회
    """
    try:
        response = requests.get(f"{TRADING_BOT_URL}/system/status", timeout=5)
        
        if response.status_code == 200:
            data = response.json()
            return data.get('status', {})
        else:
            return None
            
    except Exception as e:
        return None

def mark_events_as_processed(event_ids):
    """
    이벤트를 처리됨으로 표시
    """
    try:
        response = requests.post(
            f"{TRADING_BOT_URL}/events/mark_processed",
            json={'event_ids': event_ids},
            timeout=5
        )
        
        if response.status_code == 200:
            return True
        else:
            return False
            
    except Exception as e:
        return False

def display_realtime_events():
    """
    실시간 이벤트 표시 (최상단 알림)
    """
    if not REALTIME_ENABLED:
        return
    
    events = fetch_unread_events()
    
    if not events:
        return
    
    # 이벤트를 최신순으로 표시
    for event in events[:5]:  # 최대 5개만 표시
        event_type = event.get('event_type', 'unknown')
        symbol = event.get('symbol', 'N/A')
        timestamp = event.get('timestamp', '')
        data = event.get('data', {})
        
        if event_type == 'position_closed':
            pnl = data.get('pnl_usdt', 0)
            pnl_percent = data.get('pnl_percent', 0)
            close_type = data.get('close_type', 'manual')
            is_binance_confirmed = data.get('is_binance_confirmed', False)
            
            pnl_emoji = "🟢" if pnl > 0 else "🔴"
            verified_badge = "✅ 바이낸스 확인" if is_binance_confirmed else "📊 계산값"
            
            st.markdown(f"""
            <div class="event-notification">
                <strong>{pnl_emoji} 포지션 종료 알림</strong><br>
                <strong>심볼:</strong> {symbol} | 
                <strong>수익:</strong> ${pnl:.2f} ({pnl_percent:+.2f}%) | 
                <strong>종료 방식:</strong> {close_type} | 
                <strong>{verified_badge}</strong><br>
                <small>{timestamp}</small>
            </div>
            """, unsafe_allow_html=True)
            
        elif event_type == 'position_opened':
            side = data.get('side', 'unknown')
            price = data.get('price', 0)
            
            st.markdown(f"""
            <div class="event-notification">
                <strong>🟢 포지션 진입 알림</strong><br>
                <strong>심볼:</strong> {symbol} | 
                <strong>방향:</strong> {side.upper()} | 
                <strong>가격:</strong> ${price:.2f}<br>
                <small>{timestamp}</small>
            </div>
            """, unsafe_allow_html=True)
    
    # 표시한 이벤트 처리됨으로 표시
    event_ids = [e['id'] for e in events[:5]]
    mark_events_as_processed(event_ids)

# ==========================================
# 데이터베이스 초기화 및 관리 함수 (기존 유지)
# ==========================================

def init_database():
    """데이터베이스 초기화"""
    try:
        conn = sqlite3.connect('integrated_trades.db')
        cursor = conn.cursor()
        
        # 기존 테이블들 (모두 유지)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS account_config (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                config_key TEXT UNIQUE NOT NULL,
                config_value TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS position_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                symbol TEXT NOT NULL,
                side TEXT NOT NULL,
                amount REAL NOT NULL,
                entry_price REAL NOT NULL,
                mark_price REAL NOT NULL,
                unrealized_pnl REAL NOT NULL,
                snapshot_hash TEXT,
                UNIQUE(timestamp, symbol)
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS manual_trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                detected_at TEXT NOT NULL,
                symbol TEXT NOT NULL,
                trade_type TEXT NOT NULL,
                side TEXT,
                amount REAL,
                price REAL,
                note TEXT
            )
        """)
        
        conn.commit()
        conn.close()
        
        return True
        
    except Exception as e:
        st.error(f"DB 초기화 오류: {e}")
        return False

def get_or_set_initial_balance(balance=None):
    """초기 잔고 가져오기 또는 설정 (기존 유지)"""
    try:
        conn = sqlite3.connect('integrated_trades.db')
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT config_value FROM account_config 
            WHERE config_key = 'initial_balance'
        """)
        
        result = cursor.fetchone()
        
        if result:
            conn.close()
            return float(result[0])
        elif balance is not None:
            cursor.execute("""
                INSERT INTO account_config (config_key, config_value, updated_at)
                VALUES ('initial_balance', ?, ?)
            """, (str(balance), datetime.now().isoformat()))
            
            conn.commit()
            conn.close()
            return balance
        else:
            conn.close()
            return None
            
    except Exception as e:
        st.error(f"초기 잔고 조회/설정 오류: {e}")
        return None

def get_or_set_lifetime_start_balance(balance=None):
    """Lifetime 시작 잔고 가져오기 또는 설정 (기존 유지)"""
    try:
        conn = sqlite3.connect('integrated_trades.db')
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT config_value FROM account_config 
            WHERE config_key = 'lifetime_start_balance'
        """)
        
        result = cursor.fetchone()
        
        if result:
            conn.close()
            return float(result[0])
        elif balance is not None:
            cursor.execute("""
                INSERT INTO account_config (config_key, config_value, updated_at)
                VALUES ('lifetime_start_balance', ?, ?)
            """, (str(balance), datetime.now().isoformat()))
            
            conn.commit()
            conn.close()
            return balance
        else:
            conn.close()
            return None
            
    except Exception as e:
        st.error(f"Lifetime 시작 잔고 조회/설정 오류: {e}")
        return None

# ==========================================
# Binance API 연결 함수 (기존 유지)
# ==========================================

@st.cache_resource
def get_binance_exchange():
    """바이낸스 거래소 객체 생성 (캐시)"""
    try:
        api_key = os.getenv('BINANCE_API_KEY')
        secret_key = os.getenv('BINANCE_SECRET_KEY')
        
        if not api_key or not secret_key:
            return None
        
        exchange = ccxt.binance({
            'apiKey': api_key,
            'secret': secret_key,
            'enableRateLimit': True,
            'options': {
                'defaultType': 'future'
            }
        })
        
        return exchange
        
    except Exception as e:
        st.error(f"거래소 연결 오류: {e}")
        return None

def fetch_positions_from_binance(exchange):
    """바이낸스에서 실시간 포지션 가져오기 (기존 유지)"""
    try:
        positions = exchange.fetch_positions()
        active_positions = [p for p in positions if float(p['info'].get('positionAmt', 0)) != 0]
        
        result = []
        for pos in active_positions:
            symbol = pos['symbol']
            side = 'long' if float(pos['info']['positionAmt']) > 0 else 'short'
            amount = abs(float(pos['info']['positionAmt']))
            entry_price = float(pos['info']['entryPrice'])
            mark_price = float(pos['info']['markPrice'])
            liquidation_price = float(pos['info'].get('liquidationPrice', 0))
            unrealized_pnl = float(pos['info']['unRealizedProfit'])
            leverage = int(pos['info'].get('leverage', 10))  # 기본값 10
            
            result.append({
                'symbol': symbol,
                'side': side,
                'amount': amount,
                'entry_price': entry_price,
                'mark_price': mark_price,
                'liquidation_price': liquidation_price,
                'unrealized_pnl': unrealized_pnl,
                'leverage': leverage,
                'pnl_percent': ((mark_price - entry_price) / entry_price * 100) if side == 'long' 
                              else ((entry_price - mark_price) / entry_price * 100)
            })
        
        return result
        
    except Exception as e:
        st.error(f"포지션 조회 오류: {e}")
        return []

def fetch_balance_from_binance(exchange):
    """바이낸스에서 실시간 잔고 가져오기 (기존 유지)"""
    try:
        balance = exchange.fetch_balance()
        
        return {
            'total': balance['USDT']['total'],
            'free': balance['USDT']['free'],
            'used': balance['USDT']['used']
        }
        
    except Exception as e:
        st.error(f"잔고 조회 오류: {e}")
        return {'total': 0, 'free': 0, 'used': 0}

# ==========================================
# 데이터베이스 조회 함수들 (기존 유지)
# ==========================================

def get_db_positions():
    """DB에서 포지션 히스토리 조회"""
    try:
        conn = sqlite3.connect('integrated_trades.db')
        
        query = """
        SELECT DISTINCT symbol, side, position_type
        FROM position_history
        WHERE timestamp >= datetime('now', '-1 hour')
        ORDER BY timestamp DESC
        """
        
        df = pd.read_sql_query(query, conn)
        conn.close()
        
        return df.to_dict('records')
        
    except Exception as e:
        return []

def get_completed_trades(days=30):
    """완료된 거래 조회 (🆕 바이낸스 실제 PnL 포함)"""
    try:
        conn = sqlite3.connect('integrated_trades.db')
        cursor = conn.cursor()
        
        # 🆕 v8.1: realized_pnl_binance 컬럼 존재 여부 확인
        cursor.execute("PRAGMA table_info(completed_trades)")
        columns = [col[1] for col in cursor.fetchall()]
        has_binance_pnl = 'realized_pnl_binance' in columns
        
        # 쿼리 동적 생성
        if has_binance_pnl:
            query = f"""
            SELECT 
                symbol, side, entry_price, exit_price, amount,
                pnl_usdt, pnl_percent, is_win, 
                open_timestamp, close_timestamp, holding_time_minutes, close_reason,
                realized_pnl_binance,
                CASE 
                    WHEN realized_pnl_binance IS NOT NULL THEN 1
                    ELSE 0
                END as is_binance_verified
            FROM completed_trades
            WHERE close_timestamp >= datetime('now', '-{days} days')
            ORDER BY close_timestamp DESC
            """
        else:
            # 구버전 DB 호환 (realized_pnl_binance 없음)
            query = f"""
            SELECT 
                symbol, side, entry_price, exit_price, amount,
                pnl_usdt, pnl_percent, is_win, 
                open_timestamp, close_timestamp, holding_time_minutes, close_reason,
                NULL as realized_pnl_binance,
                0 as is_binance_verified
            FROM completed_trades
            WHERE close_timestamp >= datetime('now', '-{days} days')
            ORDER BY close_timestamp DESC
            """
        
        df = pd.read_sql_query(query, conn)
        conn.close()
        
        if not df.empty:
            # 컬럼명을 exit_time, entry_time으로 변경 (하위 호환성)
            df['exit_time'] = pd.to_datetime(df['close_timestamp'])
            df['entry_time'] = pd.to_datetime(df['open_timestamp'])
            df = df.drop(['close_timestamp', 'open_timestamp'], axis=1)
        
        return df
        
    except Exception as e:
        st.error(f"거래 히스토리 조회 오류: {e}")
        import traceback
        st.error(traceback.format_exc())
        return pd.DataFrame()

def calculate_period_stats(df, period_days):
    """기간별 통계 계산 (기존 유지)"""
    if df.empty:
        return None
    
    cutoff_date = datetime.now() - timedelta(days=period_days)
    period_df = df[df['exit_time'] >= cutoff_date]
    
    if period_df.empty:
        return None
    
    total_trades = len(period_df)
    winning_trades = len(period_df[period_df['is_win'] == 1])
    win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
    total_pnl = period_df['pnl_usdt'].sum()
    
    # 🆕 바이낸스 확인된 거래 비율
    binance_verified_count = len(period_df[period_df['is_binance_verified'] == 1])
    binance_verified_rate = (binance_verified_count / total_trades * 100) if total_trades > 0 else 0
    
    return {
        'total_trades': total_trades,
        'winning_trades': winning_trades,
        'win_rate': win_rate,
        'total_pnl': total_pnl,
        'avg_pnl': total_pnl / total_trades if total_trades > 0 else 0,
        'binance_verified_count': binance_verified_count,
        'binance_verified_rate': binance_verified_rate
    }

# ==========================================
# 🆕 v7.2: 고급 성과 분석 함수 (from v6)
# ==========================================

def calculate_period_performance(current_balance, initial_balance, days):
    """특정 기간의 성과 계산"""
    try:
        conn = sqlite3.connect('integrated_trades.db')
        
        query = f"""
        SELECT 
            SUM(pnl_usdt) as period_pnl,
            COUNT(*) as trades,
            SUM(CASE WHEN is_win = 1 THEN 1 ELSE 0 END) as wins
        FROM completed_trades
        WHERE close_timestamp >= date('now', '-{days} days')
        """
        
        df = pd.read_sql_query(query, conn)
        conn.close()
        
        if df.empty or df.iloc[0]['period_pnl'] is None:
            return {
                'period_pnl': 0.0,
                'period_pct': 0.0,
                'trades': 0,
                'win_rate': 0.0
            }
        
        period_pnl = float(df.iloc[0]['period_pnl'])
        trades = int(df.iloc[0]['trades'])
        wins = int(df.iloc[0]['wins'])
        
        # 시작 잔고 = 현재 잔고 - 기간 PnL
        period_start_balance = current_balance - period_pnl
        period_pct = (period_pnl / period_start_balance * 100) if period_start_balance > 0 else 0.0
        win_rate = (wins / trades * 100) if trades > 0 else 0.0
        
        return {
            'period_pnl': period_pnl,
            'period_pct': period_pct,
            'trades': trades,
            'win_rate': win_rate
        }
        
    except Exception as e:
        st.error(f"기간 성과 계산 오류: {e}")
        return {
            'period_pnl': 0.0,
            'period_pct': 0.0,
            'trades': 0,
            'win_rate': 0.0
        }

def calculate_lifetime_performance(current_balance, lifetime_start_balance):
    """전체 기간 성과 계산"""
    try:
        conn = sqlite3.connect('integrated_trades.db')
        
        query = """
        SELECT 
            SUM(pnl_usdt) as total_pnl,
            COUNT(*) as trades,
            SUM(CASE WHEN is_win = 1 THEN 1 ELSE 0 END) as wins
        FROM completed_trades
        """
        
        df = pd.read_sql_query(query, conn)
        conn.close()
        
        if df.empty or df.iloc[0]['total_pnl'] is None:
            # DB에 거래 기록이 없으면 current_balance - lifetime_start_balance로 계산
            total_pnl = current_balance - lifetime_start_balance
            lifetime_pct = (total_pnl / lifetime_start_balance * 100) if lifetime_start_balance > 0 else 0.0
            return {
                'lifetime_pnl': total_pnl,
                'lifetime_pct': lifetime_pct,
                'trades': 0,
                'win_rate': 0.0
            }
        
        total_pnl = float(df.iloc[0]['total_pnl'])
        trades = int(df.iloc[0]['trades'])
        wins = int(df.iloc[0]['wins'])
        
        # Lifetime 수익률 = (현재 잔고 - Lifetime 시작 잔고) / Lifetime 시작 잔고 * 100
        lifetime_gain = current_balance - lifetime_start_balance
        lifetime_pct = (lifetime_gain / lifetime_start_balance * 100) if lifetime_start_balance > 0 else 0.0
        win_rate = (wins / trades * 100) if trades > 0 else 0.0
        
        return {
            'lifetime_pnl': lifetime_gain,  # 실제 총 수익 (현재 잔고 - 시작 잔고)
            'lifetime_pct': lifetime_pct,
            'trades': trades,
            'win_rate': win_rate
        }
        
    except Exception as e:
        st.error(f"전체 성과 계산 오류: {e}")
        return {
            'lifetime_pnl': 0.0,
            'lifetime_pct': 0.0,
            'trades': 0,
            'win_rate': 0.0
        }

def get_equity_history(current_balance, days=None, lifetime_start_balance=None):
    """자산 추이 데이터 생성"""
    try:
        conn = sqlite3.connect('integrated_trades.db')
        
        date_filter = f"WHERE close_timestamp >= date('now', '-{days} days')" if days else ""
        
        query = f"""
        SELECT 
            close_timestamp,
            pnl_usdt,
            SUM(pnl_usdt) OVER (ORDER BY close_timestamp DESC) as reverse_cumulative_pnl
        FROM completed_trades
        {date_filter}
        ORDER BY close_timestamp ASC
        """
        
        df = pd.read_sql_query(query, conn)
        conn.close()
        
        if df.empty:
            # 거래 데이터가 없는 경우
            if days is None and lifetime_start_balance is not None:
                # 전체 기간인데 거래가 없으면 lifetime_start_balance부터 시작
                return pd.DataFrame({
                    'close_timestamp': [datetime.now()],
                    'balance': [current_balance]
                })
            return pd.DataFrame()
        
        df['close_timestamp'] = pd.to_datetime(df['close_timestamp'])
        
        # 전체 기간이고 lifetime_start_balance가 제공된 경우
        if days is None and lifetime_start_balance is not None:
            # 모든 거래의 PnL 합계
            total_pnl_from_trades = df['pnl_usdt'].sum()
            # 시작 잔고 = lifetime_start_balance
            df['balance'] = lifetime_start_balance + df['pnl_usdt'].cumsum()
            
            # 시작점 추가 (첫 거래 이전)
            first_trade_time = df['close_timestamp'].min()
            start_row = pd.DataFrame({
                'close_timestamp': [first_trade_time - timedelta(minutes=1)],
                'balance': [lifetime_start_balance]
            })
            
            # 현재 시점 추가
            current_row = pd.DataFrame({
                'close_timestamp': [datetime.now()],
                'balance': [current_balance]
            })
            
            result_df = pd.concat([
                start_row,
                df[['close_timestamp', 'balance']], 
                current_row
            ]).sort_values('close_timestamp').reset_index(drop=True)
            
        else:
            # 특정 기간인 경우 (기존 로직)
            df['balance'] = current_balance - df['reverse_cumulative_pnl']
            
            # 현재 시점 추가
            current_row = pd.DataFrame({
                'close_timestamp': [datetime.now()],
                'balance': [current_balance]
            })
            
            result_df = pd.concat([
                df[['close_timestamp', 'balance']], 
                current_row
            ]).sort_values('close_timestamp').reset_index(drop=True)
        
        return result_df
        
    except Exception as e:
        st.error(f"자산 추이 조회 오류: {e}")
        return pd.DataFrame()


# ==========================================
# 메인 대시보드
# ==========================================

def main():
    """메인 대시보드"""
    
    # 🆕 실시간 이벤트 표시 (최상단)
    display_realtime_events()
    
    # 헤더
    st.markdown('<h1 class="main-header">⚡ Real-time Trading Dashboard v7.0</h1>', 
                unsafe_allow_html=True)
    
    # 🆕 실시간 상태 배지
    if REALTIME_ENABLED:
        st.markdown("""
        <div style="text-align: center; margin-bottom: 1rem;">
            <span class="realtime-badge">🔴 LIVE - 실시간 업데이트 중</span>
        </div>
        """, unsafe_allow_html=True)
    
    # DB 초기화
    init_database()
    
    # 사이드바 설정 (기존 유지)
    with st.sidebar:
        st.header("⚙️ 설정")
        
        # 🆕 시스템 상태 표시
        st.subheader("🔧 봇 상태")
        system_status = fetch_system_status()
        
        if system_status:
            st.success("✅ 자동매매 봇 연결됨")
            
            col_s1, col_s2 = st.columns(2)
            with col_s1:
                st.metric("활성 포지션", system_status.get('active_positions', 0))
            with col_s2:
                st.metric("활성 유저", system_status.get('active_users', 0))
            
            # WebSocket 상태
            if system_status.get('websocket_enabled'):
                st.info("⚡ WebSocket 실시간 감지")
            if system_status.get('polling_enabled'):
                st.info("🔍 폴링 백업 활성화")
        else:
            st.error("❌ 봇 연결 안됨")
            st.warning("💡 자동매매 봇을 먼저 실행하세요")
        
        st.markdown("---")
        
        # 🆕 실시간 업데이트 설정
        st.subheader("🔴 실시간 업데이트")
        auto_refresh = st.checkbox("자동 새로고침", value=REALTIME_ENABLED, 
                                   help=f"{AUTO_REFRESH_INTERVAL}초마다 자동으로 데이터를 갱신합니다")
        
        if auto_refresh:
            st.info(f"⚡ {AUTO_REFRESH_INTERVAL}초마다 업데이트")
        
        st.markdown("---")
        
        # 데이터 소스 선택 (기존 유지)
        st.subheader("📊 데이터 소스")
        data_source = st.radio(
            "포지션 데이터 소스",
            ["🔴 실시간 (Binance API)", "💾 데이터베이스"],
            help="실시간: 바이낸스에서 직접 조회 (정확)\n데이터베이스: 봇이 기록한 히스토리"
        )
        
        # 바이낸스 연결 (기존 유지)
        exchange = None
        if "실시간" in data_source:
            exchange = get_binance_exchange()
            
            if exchange:
                st.success("✅ Binance 연결됨")
            else:
                st.error("❌ API 키 미설정")
                st.info("💡 .env 파일에 API 키를 설정하세요")
        
        st.markdown("---")
        
        # 초기 잔고 설정 (기존 유지)
        st.subheader("💰 초기 잔고 설정")
        
        current_initial = get_or_set_initial_balance()
        
        if current_initial:
            st.info(f"현재 설정: ${current_initial:,.2f}")
        
        new_initial = st.number_input(
            "새 초기 잔고 (USD)",
            min_value=0.0,
            value=float(current_initial) if current_initial else 1000.0,
            step=100.0
        )
        
        if st.button("💾 초기 잔고 저장"):
            get_or_set_initial_balance(new_initial)
            st.success(f"✅ ${new_initial:,.2f}로 설정됨")
            st.rerun()
    
    # 탭 구성 (기존 유지)
    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
        "📊 Overview",
        "📈 성과 분석",
        "💼 포지션",
        "📝 거래 히스토리",
        "🤖 AI 모니터링",
        "🧠 AI Reflection"
    ])
    
    # ==========================================
    # Tab 1: Overview (기존 유지 + 실시간 개선)
    # ==========================================
    with tab1:
        st.header("📊 실시간 대시보드")
        
        # 현재 잔고 조회
        if exchange:
            balance_data = fetch_balance_from_binance(exchange)
        else:
            balance_data = {'total': 0, 'free': 0, 'used': 0}
        
        # 초기 잔고
        initial_balance = get_or_set_initial_balance() or balance_data['total']
        
        # 수익 계산
        current_total = balance_data['total']
        total_gain = current_total - initial_balance
        total_gain_percent = (total_gain / initial_balance * 100) if initial_balance > 0 else 0
        
        # 메트릭 표시
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric(
                "💰 현재 잔고",
                f"${current_total:,.2f}",
                f"{total_gain_percent:+.2f}%",
                delta_color="normal"
            )
        
        with col2:
            st.metric(
                "💵 가용 잔고",
                f"${balance_data['free']:,.2f}"
            )
        
        with col3:
            st.metric(
                "🔒 사용 중",
                f"${balance_data['used']:,.2f}"
            )
        
        with col4:
            st.metric(
                "📈 총 수익",
                f"${total_gain:+,.2f}",
                f"{total_gain_percent:+.2f}%",
                delta_color="normal"
            )
        
        st.markdown("---")
        
        # 완료된 거래 통계
        completed_df = get_completed_trades(days=365)
        
        if not completed_df.empty:
            total_trades = len(completed_df)
            winning_trades = len(completed_df[completed_df['is_win'] == 1])
            win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
            
            # 🆕 바이낸스 확인 통계
            binance_verified = len(completed_df[completed_df['is_binance_verified'] == 1])
            binance_verified_rate = (binance_verified / total_trades * 100) if total_trades > 0 else 0
            
            st.subheader("📊 거래 통계 (전체)")
            
            stat_col1, stat_col2, stat_col3, stat_col4 = st.columns(4)
            
            with stat_col1:
                st.metric("총 거래", total_trades)
            
            with stat_col2:
                st.metric("승률", f"{win_rate:.1f}%")
            
            with stat_col3:
                st.metric("승리", winning_trades)
            
            with stat_col4:
                # 🆕 바이낸스 검증 비율
                st.metric("✅ 바이낸스 확인", f"{binance_verified_rate:.1f}%",
                         help=f"{binance_verified}/{total_trades} 거래가 바이낸스에서 실제 PnL 확인됨")
    
    # ==========================================
    # Tab 2: 성과 분석 (기존 유지)
    # ==========================================
    # ==========================================
    # Tab 2: 성과 분석 (🆕 v7.2 Enhanced - from v6)
    # ==========================================
    with tab2:
        st.header("📈 Performance Analysis")
        
        if current_balance is None or initial_balance is None or lifetime_start_balance is None:
            st.error("⚠️ 잔고 정보를 가져올 수 없습니다. API 키를 확인해주세요.")
        else:
            try:
                # ===================================
                # 다중 기간 성과 요약 카드
                # ===================================
                st.subheader("🎯 Multi-Period Performance Summary")
                
                periods = {
                    '7D': 7,
                    '30D': 30,
                    '90D': 90,
                    '365D': 365
                }
                
                cols = st.columns(5)
                
                # Lifetime 성과
                with cols[0]:
                    lifetime_perf = calculate_lifetime_performance(current_balance, lifetime_start_balance)
                    
                    st.markdown(f"""
                    <div class="period-card" style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);">
                        <h4>📊 LIFETIME</h4>
                        <h2>${lifetime_perf['lifetime_pnl']:+.2f}</h2>
                        <p style="font-size:1.2rem; font-weight:bold;">{lifetime_perf['lifetime_pct']:+.2f}%</p>
                        <small>{lifetime_perf['trades']} trades | WR: {lifetime_perf['win_rate']:.1f}%</small>
                    </div>
                    """, unsafe_allow_html=True)
                
                # 각 기간별 성과
                for idx, (period_name, days) in enumerate(periods.items(), start=1):
                    with cols[idx]:
                        perf = calculate_period_performance(current_balance, initial_balance, days)
                        
                        # 색상 선택
                        if perf['period_pct'] > 0:
                            gradient = "linear-gradient(135deg, #11998e 0%, #38ef7d 100%)"
                        else:
                            gradient = "linear-gradient(135deg, #eb3349 0%, #f45c43 100%)"
                        
                        st.markdown(f"""
                        <div class="period-card" style="background: {gradient};">
                            <h4>📈 {period_name}</h4>
                            <h2>${perf['period_pnl']:+.2f}</h2>
                            <p style="font-size:1.2rem; font-weight:bold;">{perf['period_pct']:+.2f}%</p>
                            <small>{perf['trades']} trades | WR: {perf['win_rate']:.1f}%</small>
                        </div>
                        """, unsafe_allow_html=True)
                
                st.markdown("---")
                
                # ===================================
                # 자산 추이 그래프 (다중 기간)
                # ===================================
                st.subheader("💎 Total Equity Over Time")
                
                # 기간 선택
                period_selector = st.radio(
                    "기간 선택",
                    ["7일", "30일", "90일", "365일", "전체"],
                    horizontal=True,
                    index=1
                )
                
                period_days_map = {
                    "7일": 7,
                    "30일": 30,
                    "90일": 90,
                    "365일": 365,
                    "전체": None
                }
                
                selected_days = period_days_map[period_selector]
                
                # 전체 기간 선택 시 lifetime_start_balance 전달
                if selected_days is None:
                    equity_df = get_equity_history(current_balance, selected_days, lifetime_start_balance)
                else:
                    equity_df = get_equity_history(current_balance, selected_days)
                
                if not equity_df.empty:
                    # 메트릭 표시
                    start_balance = equity_df['balance'].iloc[0]
                    total_gain = current_balance - start_balance
                    total_gain_pct = (total_gain / start_balance * 100) if start_balance > 0 else 0
                    
                    col_m1, col_m2, col_m3, col_m4 = st.columns(4)
                    
                    with col_m1:
                        st.metric("💰 Current Balance", f"${current_balance:.2f}")
                    
                    with col_m2:
                        # 전체 기간일 때는 Lifetime 시작 잔고 표시, 아니면 초기 잔고
                        if selected_days is None:
                            st.metric("🎯 Lifetime Start Balance", f"${lifetime_start_balance:.2f}")
                        else:
                            st.metric("🎯 Initial Balance", f"${initial_balance:.2f}")
                    
                    with col_m3:
                        st.metric("📅 Period Start", f"${start_balance:.2f}")
                    
                    with col_m4:
                        st.metric(
                            "📊 Period Gain",
                            f"${total_gain:.2f}",
                            delta=f"{total_gain_pct:+.2f}%"
                        )
                    
                    # 그래프 생성
                    fig_equity = go.Figure()
                    
                    fig_equity.add_trace(go.Scatter(
                        x=equity_df['close_timestamp'],
                        y=equity_df['balance'],
                        mode='lines+markers',
                        name='Total Equity',
                        line=dict(color='#1f77b4', width=3),
                        fill='tozeroy',
                        fillcolor='rgba(31, 119, 180, 0.1)',
                        marker=dict(size=6)
                    ))
                    
                    # 전체 기간일 때는 Lifetime 시작 잔고 기준선 표시
                    if selected_days is None:
                        fig_equity.add_hline(
                            y=lifetime_start_balance,
                            line_dash="dash",
                            line_color="purple",
                            opacity=0.7,
                            annotation_text=f"Lifetime Start: ${lifetime_start_balance:.2f}",
                            annotation_position="right"
                        )
                    else:
                        # 특정 기간일 때는 초기 잔고 기준선 표시
                        fig_equity.add_hline(
                            y=initial_balance,
                            line_dash="dash",
                            line_color="purple",
                            opacity=0.7,
                            annotation_text=f"Initial: ${initial_balance:.2f}",
                            annotation_position="right"
                        )
                        
                        # 기간 시작 기준선 (초기 잔고와 다른 경우만)
                        if abs(start_balance - initial_balance) > 1:
                            fig_equity.add_hline(
                                y=start_balance,
                                line_dash="dot",
                                line_color="gray",
                                opacity=0.5,
                                annotation_text=f"Period Start: ${start_balance:.2f}",
                                annotation_position="left"
                            )
                    
                    fig_equity.update_layout(
                        title=f"Account Equity Growth - {period_selector}",
                        xaxis_title="Date",
                        yaxis_title="Balance (USDT)",
                        hovermode='x unified',
                        height=500,
                        showlegend=False
                    )
                    
                    st.plotly_chart(fig_equity, use_container_width=True)
                else:
                    st.info("선택한 기간에 거래 데이터가 없습니다.")
                
                st.markdown("---")
                
                # ===================================
                # 기존 통계 (30일 기준 유지)
                # ===================================
                conn = sqlite3.connect('integrated_trades.db')
                
                stats_query = """
                SELECT 
                    COUNT(*) as total_trades,
                    SUM(CASE WHEN is_win = 1 THEN 1 ELSE 0 END) as wins,
                    SUM(CASE WHEN is_win = 0 THEN 1 ELSE 0 END) as losses,
                    SUM(pnl_usdt) as total_pnl,
                    AVG(pnl_percent) as avg_pnl_percent,
                    MAX(pnl_usdt) as max_profit,
                    MIN(pnl_usdt) as max_loss,
                    AVG(CASE WHEN is_win = 1 THEN pnl_usdt END) as avg_win,
                    AVG(CASE WHEN is_win = 0 THEN pnl_usdt END) as avg_loss
                FROM completed_trades
                WHERE close_timestamp >= date('now', '-30 days')
                """
                
                stats_df = pd.read_sql_query(stats_query, conn)
                
                if not stats_df.empty and stats_df.iloc[0]['total_trades'] > 0:
                    stats = stats_df.iloc[0]
                    
                    total_trades = int(stats['total_trades']) if pd.notna(stats['total_trades']) else 0
                    wins = int(stats['wins']) if pd.notna(stats['wins']) else 0
                    losses = int(stats['losses']) if pd.notna(stats['losses']) else 0
                    total_pnl = float(stats['total_pnl']) if pd.notna(stats['total_pnl']) else 0.0
                    avg_pnl_percent = float(stats['avg_pnl_percent']) if pd.notna(stats['avg_pnl_percent']) else 0.0
                    max_profit = float(stats['max_profit']) if pd.notna(stats['max_profit']) else 0.0
                    max_loss = float(stats['max_loss']) if pd.notna(stats['max_loss']) else 0.0
                    avg_win = float(stats['avg_win']) if pd.notna(stats['avg_win']) else 0.0
                    avg_loss = float(stats['avg_loss']) if pd.notna(stats['avg_loss']) else 0.0
                    
                    st.subheader("📊 30-Day Trading Statistics")
                    
                    col1, col2, col3, col4, col5 = st.columns(5)
                    
                    with col1:
                        st.metric("Total Trades", total_trades)
                    
                    with col2:
                        win_rate = (wins / total_trades * 100) if total_trades > 0 else 0
                        st.metric("Win Rate", f"{win_rate:.1f}%", 
                                 delta=f"{wins}W / {losses}L")
                    
                    with col3:
                        st.metric("Total PnL", f"${total_pnl:.2f}",
                                 delta=f"{avg_pnl_percent:.2f}%")
                    
                    with col4:
                        st.metric("Best Trade", f"${max_profit:.2f}")
                    
                    with col5:
                        st.metric("Worst Trade", f"${max_loss:.2f}")
                    
                    st.markdown("---")
                    
                    # 누적 PnL 그래프
                    st.subheader("💰 Cumulative PnL Over Time (30D)")
                    
                    equity_query = """
                    SELECT 
                        close_timestamp,
                        pnl_usdt,
                        SUM(pnl_usdt) OVER (ORDER BY close_timestamp) as cumulative_pnl
                    FROM completed_trades
                    WHERE close_timestamp >= date('now', '-30 days')
                    ORDER BY close_timestamp
                    """
                    
                    equity_df_30d = pd.read_sql_query(equity_query, conn)
                    
                    if not equity_df_30d.empty:
                        equity_df_30d['close_timestamp'] = pd.to_datetime(equity_df_30d['close_timestamp'])
                        
                        fig_cumulative = go.Figure()
                        
                        fig_cumulative.add_trace(go.Scatter(
                            x=equity_df_30d['close_timestamp'],
                            y=equity_df_30d['cumulative_pnl'],
                            mode='lines+markers',
                            name='Cumulative PnL',
                            line=dict(color='#2ca02c', width=3),
                            fill='tozeroy',
                            fillcolor='rgba(44, 160, 44, 0.1)'
                        ))
                        
                        fig_cumulative.add_hline(y=0, line_dash="dash", line_color="gray", opacity=0.5)
                        
                        fig_cumulative.update_layout(
                            title="Cumulative Profit/Loss Timeline",
                            xaxis_title="Date",
                            yaxis_title="PnL (USDT)",
                            hovermode='x unified',
                            height=400
                        )
                        
                        st.plotly_chart(fig_cumulative, use_container_width=True)
                    
                    # 심볼별 성과
                    col_sym, col_wr = st.columns(2)
                    
                    with col_sym:
                        st.subheader("🎯 Symbol Performance")
                        
                        symbol_query = """
                        SELECT 
                            symbol,
                            COUNT(*) as trades,
                            SUM(CASE WHEN is_win = 1 THEN 1 ELSE 0 END) as wins,
                            ROUND(AVG(CASE WHEN is_win = 1 THEN 1.0 ELSE 0.0 END) * 100, 1) as win_rate,
                            ROUND(SUM(pnl_usdt), 2) as total_pnl,
                            ROUND(AVG(pnl_percent), 2) as avg_pnl_pct
                        FROM completed_trades
                        WHERE close_timestamp >= date('now', '-30 days')
                        GROUP BY symbol
                        ORDER BY total_pnl DESC
                        """
                        
                        symbol_df = pd.read_sql_query(symbol_query, conn)
                        
                        if not symbol_df.empty:
                            symbol_df['color'] = symbol_df['total_pnl'].apply(
                                lambda x: '🟢' if x > 0 else '🔴'
                            )
                            
                            display_df = symbol_df[['color', 'symbol', 'trades', 'win_rate', 'total_pnl', 'avg_pnl_pct']].copy()
                            display_df.columns = ['', 'Symbol', 'Trades', 'Win Rate %', 'Total PnL', 'Avg %']
                            
                            st.dataframe(display_df, use_container_width=True, hide_index=True)
                    
                    with col_wr:
                        st.subheader("📊 Win Rate Distribution")
                        
                        if not symbol_df.empty:
                            fig_winrate = go.Figure(data=[
                                go.Bar(
                                    x=symbol_df['symbol'],
                                    y=symbol_df['win_rate'],
                                    marker_color=symbol_df['win_rate'].apply(
                                        lambda x: '#2ca02c' if x >= 50 else '#d62728'
                                    ),
                                    text=symbol_df['win_rate'].apply(lambda x: f"{x:.1f}%"),
                                    textposition='outside'
                                )
                            ])
                            
                            fig_winrate.add_hline(y=50, line_dash="dash", line_color="gray")
                            
                            fig_winrate.update_layout(
                                title="Win Rate by Symbol",
                                xaxis_title="Symbol",
                                yaxis_title="Win Rate (%)",
                                showlegend=False,
                                height=300
                            )
                            
                            st.plotly_chart(fig_winrate, use_container_width=True)
                    
                    st.markdown("---")
                    
                    # Best & Worst 거래
                    col_best, col_worst = st.columns(2)
                    
                    with col_best:
                        st.subheader("🏆 Top 5 Best Trades")
                        
                        best_query = """
                        SELECT 
                            symbol,
                            ROUND(pnl_usdt, 2) as pnl,
                            ROUND(pnl_percent, 2) as pnl_pct,
                            close_timestamp
                        FROM completed_trades
                        WHERE close_timestamp >= date('now', '-30 days')
                        ORDER BY pnl_usdt DESC
                        LIMIT 5
                        """
                        
                        best_df = pd.read_sql_query(best_query, conn)
                        
                        if not best_df.empty:
                            best_df['close_timestamp'] = pd.to_datetime(best_df['close_timestamp']).dt.strftime('%m-%d %H:%M')
                            best_df.insert(0, '', ['🥇', '🥈', '🥉', '4️⃣', '5️⃣'][:len(best_df)])
                            st.dataframe(best_df, use_container_width=True, hide_index=True)
                    
                    with col_worst:
                        st.subheader("💔 Top 5 Worst Trades")
                        
                        worst_query = """
                        SELECT 
                            symbol,
                            ROUND(pnl_usdt, 2) as pnl,
                            ROUND(pnl_percent, 2) as pnl_pct,
                            close_timestamp
                        FROM completed_trades
                        WHERE close_timestamp >= date('now', '-30 days')
                        ORDER BY pnl_usdt ASC
                        LIMIT 5
                        """
                        
                        worst_df = pd.read_sql_query(worst_query, conn)
                        
                        if not worst_df.empty:
                            worst_df['close_timestamp'] = pd.to_datetime(worst_df['close_timestamp']).dt.strftime('%m-%d %H:%M')
                            worst_df.insert(0, '', ['💀', '😱', '😢', '😕', '😐'][:len(worst_df)])
                            st.dataframe(worst_df, use_container_width=True, hide_index=True)
                    
                    st.markdown("---")
                    
                    # 추가 통계
                    col_dist, col_dur, col_rr = st.columns(3)
                    
                    with col_dist:
                        st.subheader("📉 PnL Distribution")
                        
                        pnl_query = """
                        SELECT pnl_usdt
                        FROM completed_trades
                        WHERE close_timestamp >= date('now', '-30 days')
                        """
                        
                        pnl_dist_df = pd.read_sql_query(pnl_query, conn)
                        
                        if not pnl_dist_df.empty:
                            fig_dist = go.Figure(data=[
                                go.Histogram(
                                    x=pnl_dist_df['pnl_usdt'],
                                    nbinsx=20,
                                    marker_color='lightblue',
                                    marker_line_color='darkblue',
                                    marker_line_width=1
                                )
                            ])
                            
                            fig_dist.update_layout(
                                title="Profit/Loss Distribution",
                                xaxis_title="PnL (USDT)",
                                yaxis_title="Frequency",
                                showlegend=False,
                                height=250
                            )
                            
                            st.plotly_chart(fig_dist, use_container_width=True)
                    
                    with col_dur:
                        st.subheader("⏱️ Trade Duration")
                        
                        duration_query = """
                        SELECT 
                            ROUND((julianday(close_timestamp) - julianday(open_timestamp)) * 24, 1) as hours,
                            pnl_usdt
                        FROM completed_trades
                        WHERE close_timestamp >= date('now', '-30 days')
                            AND open_timestamp IS NOT NULL
                        """
                        
                        duration_df = pd.read_sql_query(duration_query, conn)
                        
                        if not duration_df.empty:
                            fig_duration = go.Figure(data=[
                                go.Scatter(
                                    x=duration_df['hours'],
                                    y=duration_df['pnl_usdt'],
                                    mode='markers',
                                    marker=dict(
                                        size=8,
                                        color=duration_df['pnl_usdt'],
                                        colorscale='RdYlGn',
                                        showscale=True,
                                        colorbar=dict(title="PnL")
                                    )
                                )
                            ])
                            
                            fig_duration.update_layout(
                                title="Duration vs PnL",
                                xaxis_title="Duration (hours)",
                                yaxis_title="PnL (USDT)",
                                showlegend=False,
                                height=250
                            )
                            
                            st.plotly_chart(fig_duration, use_container_width=True)
                    
                    with col_rr:
                        st.subheader("🎲 Risk/Reward")
                        
                        if avg_win != 0 and avg_loss != 0:
                            risk_reward_ratio = abs(avg_win / avg_loss)
                            
                            fig_rr = go.Figure(data=[
                                go.Pie(
                                    labels=['Avg Win', 'Avg Loss'],
                                    values=[abs(avg_win), abs(avg_loss)],
                                    hole=0.5,
                                    marker_colors=['#2ca02c', '#d62728']
                                )
                            ])
                            
                            fig_rr.update_layout(
                                title=f"Risk/Reward: {risk_reward_ratio:.2f}",
                                showlegend=True,
                                height=250
                            )
                            
                            st.plotly_chart(fig_rr, use_container_width=True)
                            
                            st.metric("Avg Win", f"${avg_win:.2f}")
                            st.metric("Avg Loss", f"${avg_loss:.2f}")
                
                else:
                    st.info("⚠️ 최근 30일간 완료된 거래가 없습니다.")
                
                conn.close()
                
            except Exception as e:
                st.error(f"성과 분석 오류: {e}")
                import traceback
                st.text(traceback.format_exc())
    # Tab 3: 포지션 (🆕 실시간 개선)
    # ==========================================
    with tab3:
        st.header("💼 활성 포지션")
        
        if exchange and "실시간" in data_source:
            # 🆕 실시간 바이낸스 포지션
            positions = fetch_positions_from_binance(exchange)
            
            if positions:
                st.success(f"✅ {len(positions)}개의 활성 포지션 (실시간)")
                
                for pos in positions:
                    pnl_color = "🟢" if pos['unrealized_pnl'] > 0 else "🔴"
                    side_emoji = "📈" if pos['side'] == 'long' else "📉"
                    
                    with st.expander(f"{pnl_color} {pos['symbol']} | {side_emoji} {pos['side'].upper()} | "
                                    f"PnL: ${pos['unrealized_pnl']:+.2f}"):
                        
                        col1, col2, col3, col4 = st.columns(4)
                        
                        with col1:
                            st.metric("진입 가격", f"${pos['entry_price']:.4f}")
                        
                        with col2:
                            st.metric("현재 가격", f"${pos['mark_price']:.4f}")
                        
                        with col3:
                            st.metric("미실현 손익", f"${pos['unrealized_pnl']:+.2f}",
                                     f"{pos['pnl_percent']:+.2f}%")
                        
                        with col4:
                            st.metric("레버리지", f"{pos['leverage']}x")
                        
                        # 청산가
                        if pos['liquidation_price'] > 0:
                            st.warning(f"⚠️ 청산 가격: ${pos['liquidation_price']:.4f}")
            else:
                st.info("현재 활성 포지션이 없습니다.")
        
        else:
            # DB에서 포지션 조회
            db_positions = get_db_positions()
            
            if db_positions:
                st.info(f"💾 {len(db_positions)}개의 포지션 (DB 기록)")
                
                for pos in db_positions:
                    position_type_icon = "🤖" if pos.get('position_type') == 'auto' else "🔧"
                    side_emoji = "📈" if pos['side'] == 'long' else "📉"
                    
                    st.markdown(f"{position_type_icon} {pos['symbol']} | {side_emoji} {pos['side'].upper()}")
            else:
                st.info("DB에 포지션 기록이 없습니다.")
    
    # ==========================================
    # Tab 4: 거래 히스토리 (🆕 바이낸스 확인 표시)
    # ==========================================
    with tab4:
        st.header("📝 거래 히스토리")
        
        period_days = st.selectbox(
            "조회 기간",
            [7, 30, 90, 365],
            format_func=lambda x: f"최근 {x}일"
        )
        
        completed_df = get_completed_trades(days=period_days)
        
        if not completed_df.empty:
            st.info(f"📊 총 {len(completed_df)}건의 완료된 거래")
            
            # 🆕 바이낸스 확인 여부 추가
            display_df = completed_df[[
                'exit_time', 'symbol', 'side', 'entry_price', 'exit_price',
                'pnl_usdt', 'pnl_percent', 'holding_time_minutes', 'close_reason',
                'is_binance_verified'
            ]].copy()
            
            # 열 이름 변경
            display_df.columns = [
                '종료 시간', '심볼', '방향', '진입가', '종료가',
                '손익 (USD)', '손익 (%)', '보유 시간 (분)', '종료 방식',
                '바이낸스 확인'
            ]
            
            # 바이낸스 확인 여부를 텍스트로 변환
            display_df['바이낸스 확인'] = display_df['바이낸스 확인'].apply(
                lambda x: '✅' if x == 1 else '📊'
            )
            
            st.dataframe(
                display_df.style.format({
                    '진입가': '${:.4f}',
                    '종료가': '${:.4f}',
                    '손익 (USD)': '${:+.2f}',
                    '손익 (%)': '{:+.2f}%',
                    '보유 시간 (분)': '{:.1f}'
                }),
                use_container_width=True
            )
        else:
            st.info("선택한 기간에 완료된 거래가 없습니다.")
    
    # ==========================================
    # Tab 5: AI 모니터링 (기존 유지)
    # ==========================================
    with tab5:
        st.header("🤖 AI 모니터링 히스토리")
        
        try:
            conn = sqlite3.connect('integrated_trades.db')
            
            ai_query = """
            SELECT 
                timestamp,
                symbol,
                ai_decision,
                confidence,
                urgency,
                reason,
                CASE 
                    WHEN reason LIKE '%Manual position%' THEN '🔧 Manual'
                    WHEN reason LIKE '%manual%' THEN '🔧 Manual'
                    ELSE '🤖 Auto'
                END as position_type
            FROM trades
            WHERE trade_type IN ('AI_MONITOR', 'MANUAL_ENTRY')
               OR (ai_decision = 'detected' AND action = 'manual_position')
            ORDER BY timestamp DESC
            LIMIT 30
            """
            
            ai_df = pd.read_sql_query(ai_query, conn)
            conn.close()
            
            if not ai_df.empty:
                ai_df['timestamp'] = pd.to_datetime(ai_df['timestamp'])
                ai_df['confidence'] = ai_df['confidence'] * 100
                
                latest_time = ai_df['timestamp'].max()
                st.info(f"📊 최근 AI 모니터링: {latest_time.strftime('%Y-%m-%d %H:%M:%S')}")
                
                display_columns = ['position_type', 'timestamp', 'symbol', 'ai_decision', 
                                 'confidence', 'urgency', 'reason']
                
                st.dataframe(
                    ai_df[display_columns].style.format({'confidence': '{:.1f}%'}),
                    use_container_width=True
                )
            else:
                st.warning("⚠️ AI 모니터링 기록이 없습니다.")
            
        except Exception as e:
            st.error(f"AI 모니터링 조회 오류: {e}")
    
    # ==========================================
    # Tab 6: AI Reflection (기존 유지)
    # ==========================================
    with tab6:
        st.header("🧠 AI Reflection History")
        
        st.info("""
        📌 **Reflection이란?**
        - AI가 최근 거래 성과를 분석하여 생성한 인사이트
        - 승률, 손익, 리스크 관리 등을 평가
        - 향후 거래 신호 검증에 활용되는 중요한 피드백
        """)
        
        try:
            conn = sqlite3.connect('integrated_trades.db')
            
            # 필터 옵션
            col_filter1, col_filter2 = st.columns(2)
            
            with col_filter1:
                symbol_query = "SELECT DISTINCT symbol FROM trades WHERE reflection IS NOT NULL ORDER BY symbol"
                symbols_df = pd.read_sql_query(symbol_query, conn)
                
                if not symbols_df.empty:
                    all_symbols = ['전체'] + symbols_df['symbol'].tolist()
                    selected_symbol = st.selectbox("🎯 심볼 선택", all_symbols)
                else:
                    selected_symbol = '전체'
            
            with col_filter2:
                period_options = {
                    '최근 24시간': 1,
                    '최근 3일': 3,
                    '최근 7일': 7,
                    '최근 30일': 30,
                    '전체': 999999
                }
                selected_period = st.selectbox("📅 조회 기간", list(period_options.keys()))
                days = period_options[selected_period]
            
            # Reflection 조회
            base_query = """
            SELECT 
                timestamp,
                symbol,
                action,
                ai_decision,
                confidence,
                reflection
            FROM trades
            WHERE reflection IS NOT NULL
                AND reflection != ''
                AND timestamp >= datetime('now', '-{days} days')
            """
            
            if selected_symbol != '전체':
                base_query += f" AND symbol = '{selected_symbol}'"
            
            base_query += " ORDER BY timestamp DESC LIMIT 50"
            
            reflection_query = base_query.format(days=days)
            reflection_df = pd.read_sql_query(reflection_query, conn)
            conn.close()
            
            if not reflection_df.empty:
                reflection_df['timestamp'] = pd.to_datetime(reflection_df['timestamp'])
                
                # 통계 표시
                st.markdown("### 📊 Reflection 통계")
                col_stat1, col_stat2, col_stat3, col_stat4 = st.columns(4)
                
                with col_stat1:
                    st.metric("📝 총 Reflection", len(reflection_df))
                
                with col_stat2:
                    approved = len(reflection_df[reflection_df['ai_decision'] == 'approve'])
                    st.metric("✅ Approved", approved)
                
                with col_stat3:
                    rejected = len(reflection_df[reflection_df['ai_decision'] == 'reject'])
                    st.metric("❌ Rejected", rejected)
                
                with col_stat4:
                    avg_confidence = reflection_df['confidence'].mean() * 100
                    st.metric("🎯 평균 신뢰도", f"{avg_confidence:.1f}%")
                
                st.markdown("---")
                
                # Reflection 카드 형식으로 표시
                st.markdown("### 📋 Reflection 상세 내역")
                
                for idx, row in reflection_df.iterrows():
                    if row['ai_decision'] == 'approve':
                        decision_color = "🟢"
                        bg_color = "#d4edda"
                    elif row['ai_decision'] == 'reject':
                        decision_color = "🔴"
                        bg_color = "#f8d7da"
                    else:
                        decision_color = "🟡"
                        bg_color = "#fff3cd"
                    
                    with st.expander(
                        f"{decision_color} {row['timestamp'].strftime('%Y-%m-%d %H:%M:%S')} | "
                        f"{row['symbol']} | {row['action'].upper()} | "
                        f"Confidence: {row['confidence']*100:.1f}%"
                    ):
                        col_meta1, col_meta2, col_meta3, col_meta4 = st.columns(4)
                        
                        with col_meta1:
                            st.markdown(f"**심볼:** `{row['symbol']}`")
                        
                        with col_meta2:
                            st.markdown(f"**액션:** `{row['action'].upper()}`")
                        
                        with col_meta3:
                            st.markdown(f"**결정:** `{row['ai_decision'].upper()}`")
                        
                        with col_meta4:
                            st.markdown(f"**신뢰도:** `{row['confidence']*100:.1f}%`")
                        
                        st.markdown("---")
                        
                        st.markdown("**🧠 AI Reflection:**")
                        
                        reflection_text = row['reflection']
                        
                        sections = {
                            'PERFORMANCE ASSESSMENT': '📊',
                            'KEY STRENGTHS': '💪',
                            'CRITICAL WEAKNESSES': '⚠️',
                            'ACTIONABLE RECOMMENDATIONS': '🎯',
                            'SIGNAL VALIDATION GUIDANCE': '✅'
                        }
                        
                        formatted_reflection = reflection_text
                        for section, emoji in sections.items():
                            if section in formatted_reflection:
                                formatted_reflection = formatted_reflection.replace(
                                    section, 
                                    f"\n\n**{emoji} {section}**"
                                )
                        
                        st.markdown(formatted_reflection)
                        
                        st.markdown("---")
                        st.caption(f"생성 시간: {row['timestamp'].strftime('%Y-%m-%d %H:%M:%S')}")
            
            else:
                st.warning("⚠️ 선택한 기간에 Reflection 기록이 없습니다.")
                st.info("💡 거래 신호가 발생하면 AI가 자동으로 Reflection을 생성합니다.")
            
        except Exception as e:
            st.error(f"Reflection 조회 오류: {e}")
            import traceback
            st.text(traceback.format_exc())
    
    # 🆕 실시간 자동 새로고침
    if auto_refresh:
        time_module.sleep(AUTO_REFRESH_INTERVAL)
        st.rerun()
    
    # Footer
    st.markdown("---")
    st.caption(f"Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | "
               f"v7.0 Realtime | Next update in {AUTO_REFRESH_INTERVAL}s")

if __name__ == "__main__":
    main()
