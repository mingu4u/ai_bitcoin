#!/usr/bin/env python3
"""
Public Dashboard v6 - Enhanced Performance Analysis
고정 초기 잔고, 다중 기간 분석(7d/30d/90d/365d/lifetime), 수동 거래 감지 기능

주요 개선사항:
1. 고정 초기 잔고 관리 (DB 저장)
2. 7d, 30d, 90d, 365d, lifetime 기간별 gain 분석
3. 수동 포지션 진입/종료 자동 감지
4. 향상된 성과 그래프 및 통계

사용 방법:
    streamlit run public_dashboard_v6.py

작성일: 2025-11-07
버전: v6.0 Enhanced
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

load_dotenv()

# 페이지 설정
st.set_page_config(
    page_title="Trading Dashboard v6 - Enhanced Analytics",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# CSS 스타일
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
# 데이터베이스 초기화 및 관리 함수
# ==========================================

def init_database():
    """데이터베이스 초기화 - 새 테이블 추가"""
    try:
        conn = sqlite3.connect('integrated_trades.db')
        cursor = conn.cursor()
        
        # 계정 설정 테이블 (초기 잔고 저장)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS account_config (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                config_key TEXT UNIQUE NOT NULL,
                config_value TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        
        # 포지션 스냅샷 테이블 (수동 거래 감지용)
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
        
        # 감지된 수동 거래 테이블
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
    """초기 잔고 가져오기 또는 설정"""
    try:
        conn = sqlite3.connect('integrated_trades.db')
        cursor = conn.cursor()
        
        # 기존 초기 잔고 조회
        cursor.execute("""
            SELECT config_value FROM account_config 
            WHERE config_key = 'initial_balance'
        """)
        
        result = cursor.fetchone()
        
        if result:
            # 이미 설정된 초기 잔고가 있으면 반환
            conn.close()
            return float(result[0])
        elif balance is not None:
            # 새로 설정
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
    """Lifetime 시작 잔고 가져오기 또는 설정"""
    try:
        conn = sqlite3.connect('integrated_trades.db')
        cursor = conn.cursor()
        
        # 기존 lifetime 시작 잔고 조회
        cursor.execute("""
            SELECT config_value FROM account_config 
            WHERE config_key = 'lifetime_start_balance'
        """)
        
        result = cursor.fetchone()
        
        if result:
            conn.close()
            return float(result[0])
        elif balance is not None:
            # 새로 설정
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

def reset_lifetime_start_balance(new_balance):
    """Lifetime 시작 잔고 리셋"""
    try:
        conn = sqlite3.connect('integrated_trades.db')
        cursor = conn.cursor()
        
        cursor.execute("""
            UPDATE account_config 
            SET config_value = ?, updated_at = ?
            WHERE config_key = 'lifetime_start_balance'
        """, (str(new_balance), datetime.now().isoformat()))
        
        if cursor.rowcount == 0:
            # 없으면 새로 삽입
            cursor.execute("""
                INSERT INTO account_config (config_key, config_value, updated_at)
                VALUES ('lifetime_start_balance', ?, ?)
            """, (str(new_balance), datetime.now().isoformat()))
        
        conn.commit()
        conn.close()
        return True
        
    except Exception as e:
        st.error(f"Lifetime 시작 잔고 리셋 오류: {e}")
        return False

def reset_initial_balance(new_balance):
    """초기 잔고 리셋"""
    try:
        conn = sqlite3.connect('integrated_trades.db')
        cursor = conn.cursor()
        
        cursor.execute("""
            UPDATE account_config 
            SET config_value = ?, updated_at = ?
            WHERE config_key = 'initial_balance'
        """, (str(new_balance), datetime.now().isoformat()))
        
        if cursor.rowcount == 0:
            # 없으면 새로 삽입
            cursor.execute("""
                INSERT INTO account_config (config_key, config_value, updated_at)
                VALUES ('initial_balance', ?, ?)
            """, (str(new_balance), datetime.now().isoformat()))
        
        conn.commit()
        conn.close()
        return True
        
    except Exception as e:
        st.error(f"초기 잔고 리셋 오류: {e}")
        return False

def save_position_snapshot(positions_df):
    """현재 포지션 스냅샷 저장 (수동 거래 감지용)"""
    try:
        if positions_df.empty:
            return True
            
        conn = sqlite3.connect('integrated_trades.db')
        cursor = conn.cursor()
        
        timestamp = datetime.now().isoformat()
        
        for _, pos in positions_df.iterrows():
            # 스냅샷 해시 생성 (중복 체크용)
            snapshot_hash = f"{pos['symbol']}_{pos['side']}_{pos['contracts']:.4f}_{pos['entry_price']:.2f}"
            
            cursor.execute("""
                INSERT OR REPLACE INTO position_snapshots
                (timestamp, symbol, side, amount, entry_price, mark_price, 
                 unrealized_pnl, snapshot_hash)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                timestamp,
                pos['symbol'],
                pos['side'],
                pos['contracts'],
                pos['entry_price'],
                pos['mark_price'],
                pos['unrealized_pnl'],
                snapshot_hash
            ))
        
        conn.commit()
        conn.close()
        return True
        
    except Exception as e:
        st.error(f"포지션 스냅샷 저장 오류: {e}")
        return False

def detect_manual_trades():
    """수동 거래 감지 (포지션 변화 분석)"""
    try:
        conn = sqlite3.connect('integrated_trades.db')
        
        # 최근 2개 스냅샷 비교
        query = """
        WITH ranked_snapshots AS (
            SELECT 
                timestamp,
                symbol,
                side,
                amount,
                entry_price,
                ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY timestamp DESC) as rn
            FROM position_snapshots
            WHERE timestamp >= datetime('now', '-1 hour')
        )
        SELECT * FROM ranked_snapshots WHERE rn <= 2
        ORDER BY symbol, timestamp DESC
        """
        
        df = pd.read_sql_query(query, conn)
        
        detected_trades = []
        
        if not df.empty:
            symbols = df['symbol'].unique()
            
            for symbol in symbols:
                symbol_data = df[df['symbol'] == symbol].sort_values('timestamp')
                
                if len(symbol_data) == 2:
                    old_pos = symbol_data.iloc[0]
                    new_pos = symbol_data.iloc[1]
                    
                    amount_diff = new_pos['amount'] - old_pos['amount']
                    
                    # 신규 진입 감지
                    if old_pos['amount'] == 0 and new_pos['amount'] > 0:
                        detected_trades.append({
                            'symbol': symbol,
                            'type': 'MANUAL_ENTRY',
                            'side': new_pos['side'],
                            'amount': new_pos['amount'],
                            'price': new_pos['entry_price']
                        })
                    
                    # 완전 종료 감지
                    elif old_pos['amount'] > 0 and new_pos['amount'] == 0:
                        detected_trades.append({
                            'symbol': symbol,
                            'type': 'MANUAL_EXIT',
                            'side': old_pos['side'],
                            'amount': old_pos['amount'],
                            'price': old_pos['entry_price']
                        })
                    
                    # 수량 변경 감지 (부분 청산 or 추가 진입)
                    elif abs(amount_diff) > 0.0001:
                        trade_type = 'MANUAL_ADD' if amount_diff > 0 else 'MANUAL_REDUCE'
                        detected_trades.append({
                            'symbol': symbol,
                            'type': trade_type,
                            'side': new_pos['side'],
                            'amount': abs(amount_diff),
                            'price': new_pos['entry_price']
                        })
        
        # 감지된 거래 저장
        if detected_trades:
            cursor = conn.cursor()
            for trade in detected_trades:
                cursor.execute("""
                    INSERT INTO manual_trades 
                    (detected_at, symbol, trade_type, side, amount, price, note)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    datetime.now().isoformat(),
                    trade['symbol'],
                    trade['type'],
                    trade.get('side'),
                    trade.get('amount'),
                    trade.get('price'),
                    'Auto-detected manual trade'
                ))
            
            conn.commit()
        
        conn.close()
        return detected_trades
        
    except Exception as e:
        st.error(f"수동 거래 감지 오류: {e}")
        return []

# ==========================================
# 거래소 연결 및 데이터 조회
# ==========================================

@st.cache_resource
def get_exchange():
    """바이낸스 거래소 연결"""
    try:
        exchange = ccxt.binance({
            'apiKey': os.getenv('BINANCE_API_KEY'),
            'secret': os.getenv('BINANCE_SECRET_KEY'),
            'enableRateLimit': True,
            'options': {
                'defaultType': 'future'
            }
        })
        return exchange
    except Exception as e:
        st.error(f"거래소 연결 실패: {e}")
        return None

@st.cache_data(ttl=10)
def get_exchange_positions():
    """거래소에서 직접 포지션 조회"""
    exchange = get_exchange()
    if not exchange:
        return pd.DataFrame()
    
    try:
        positions = exchange.fetch_positions()
        active_positions = []
        
        for pos in positions:
            if pos['contracts'] > 0:
                symbol = pos['symbol']
                if symbol.endswith(':USDT'):
                    symbol = symbol.replace(':USDT', '/USDT')
                
                active_positions.append({
                    'symbol': symbol,
                    'side': pos['side'],
                    'contracts': abs(pos['contracts']),
                    'entry_price': pos['entryPrice'] or pos['markPrice'],
                    'mark_price': pos['markPrice'],
                    'unrealized_pnl': pos['unrealizedPnl'],
                    'pnl_percent': pos['percentage'],
                    'margin': pos['initialMargin'],
                    'source': 'EXCHANGE'
                })
        
        return pd.DataFrame(active_positions)
        
    except Exception as e:
        st.error(f"거래소 조회 오류: {e}")
        return pd.DataFrame()

@st.cache_data(ttl=30)
def get_db_positions():
    """DB에서 활성 포지션 조회"""
    try:
        conn = sqlite3.connect('integrated_trades.db')
        
        query = """
        WITH latest_positions AS (
            SELECT symbol, MAX(timestamp) as latest_time
            FROM position_history
            WHERE DATE(timestamp) >= date('now', '-1 day')
            GROUP BY symbol
        )
        SELECT 
            ph.symbol,
            ph.side,
            ph.amount as contracts,
            ph.entry_price,
            ph.current_price as mark_price,
            ph.pnl_usdt as unrealized_pnl,
            ph.pnl_percent,
            ph.position_value / ph.amount as margin,
            'DB' as source,
            ph.timestamp
        FROM position_history ph
        INNER JOIN latest_positions lp 
            ON ph.symbol = lp.symbol 
            AND ph.timestamp = lp.latest_time
        WHERE ph.amount > 0
        """
        
        df = pd.read_sql_query(query, conn)
        conn.close()
        
        return df
        
    except Exception as e:
        st.error(f"DB 조회 오류: {e}")
        return pd.DataFrame()

@st.cache_data(ttl=60)
def get_account_balance():
    """거래소에서 현재 USDT 잔고 조회"""
    exchange = get_exchange()
    if not exchange:
        return None
    
    try:
        balance = exchange.fetch_balance()
        usdt_balance = balance['USDT']['total'] if 'USDT' in balance else 0
        return usdt_balance
    except Exception as e:
        st.error(f"잔고 조회 오류: {e}")
        return None

# ==========================================
# 포지션 비교 및 동기화 (기존 유지)
# ==========================================

def compare_positions(exchange_df, db_df):
    """거래소와 DB 포지션 비교"""
    comparison = {
        'matched': [],
        'exchange_only': [],
        'db_only': [],
        'mismatched': []
    }
    
    if exchange_df.empty and db_df.empty:
        return comparison
    
    exchange_symbols = set(exchange_df['symbol'].tolist()) if not exchange_df.empty else set()
    db_symbols = set(db_df['symbol'].tolist()) if not db_df.empty else set()
    
    matched_symbols = exchange_symbols & db_symbols
    for symbol in matched_symbols:
        ex_pos = exchange_df[exchange_df['symbol'] == symbol].iloc[0]
        db_pos = db_df[db_df['symbol'] == symbol].iloc[0]
        
        amount_match = abs(ex_pos['contracts'] - db_pos['contracts']) < 0.0001
        
        comparison['matched'].append({
            'symbol': symbol,
            'exchange_amount': ex_pos['contracts'],
            'db_amount': db_pos['contracts'],
            'amount_match': amount_match,
            'exchange_pnl': ex_pos['unrealized_pnl'],
            'db_pnl': db_pos['unrealized_pnl']
        })
        
        if not amount_match:
            comparison['mismatched'].append(symbol)
    
    for symbol in exchange_symbols - db_symbols:
        ex_pos = exchange_df[exchange_df['symbol'] == symbol].iloc[0]
        comparison['exchange_only'].append({
            'symbol': symbol,
            'amount': ex_pos['contracts'],
            'pnl': ex_pos['unrealized_pnl']
        })
    
    for symbol in db_symbols - exchange_symbols:
        db_pos = db_df[db_df['symbol'] == symbol].iloc[0]
        comparison['db_only'].append({
            'symbol': symbol,
            'amount': db_pos['contracts'],
            'last_update': db_pos.get('timestamp', 'Unknown')
        })
    
    return comparison

def sync_positions_to_db(comparison):
    """불일치 포지션 DB 동기화"""
    try:
        conn = sqlite3.connect('integrated_trades.db')
        cursor = conn.cursor()
        
        synced_count = 0
        
        for pos in comparison['db_only']:
            symbol = pos['symbol']
            
            cursor.execute("""
                INSERT INTO position_history 
                (timestamp, symbol, side, amount, entry_price, current_price,
                 pnl_usdt, pnl_percent, position_value, required_margin, liquidation_price)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                datetime.now().isoformat(), symbol, 'closed', 0, 0, 0,
                0, 0, 0, 0, 0
            ))
            
            synced_count += 1
        
        conn.commit()
        conn.close()
        
        if synced_count > 0:
            st.sidebar.info(f"🔄 {synced_count}개 포지션 동기화됨")
        
        return True
        
    except Exception as e:
        st.error(f"동기화 오류: {e}")
        return False

def display_sync_status(comparison):
    """동기화 상태 표시"""
    total_issues = len(comparison['exchange_only']) + len(comparison['db_only']) + len(comparison['mismatched'])
    
    if total_issues == 0:
        st.markdown("""
        <div class="sync-status sync-ok">
            ✅ 거래소와 DB가 완벽히 동기화되어 있습니다
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown(f"""
        <div class="sync-status sync-warning">
            ⚠️ 동기화 필요: {total_issues}개 불일치 발견
        </div>
        """, unsafe_allow_html=True)
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            if comparison['exchange_only']:
                st.warning(f"거래소에만: {len(comparison['exchange_only'])}개")
                for pos in comparison['exchange_only']:
                    st.text(f"  • {pos['symbol']}")
        
        with col2:
            if comparison['db_only']:
                st.error(f"DB에만 (종료됨): {len(comparison['db_only'])}개")
                for pos in comparison['db_only']:
                    st.text(f"  • {pos['symbol']}")
        
        with col3:
            if comparison['mismatched']:
                st.warning(f"수량 불일치: {len(comparison['mismatched'])}개")
                for symbol in comparison['mismatched']:
                    st.text(f"  • {symbol}")
        
        if st.button("🔄 DB 동기화 실행", type="primary"):
            if sync_positions_to_db(comparison):
                st.success("✅ DB 동기화 완료!")
                st.rerun()

def display_combined_positions(exchange_df, db_df):
    """통합 포지션 표시"""
    st.subheader("📍 Active Positions")
    
    if exchange_df.empty and db_df.empty:
        st.info("활성 포지션이 없습니다")
        return
    
    all_symbols = set()
    if not exchange_df.empty:
        all_symbols.update(exchange_df['symbol'].tolist())
    if not db_df.empty:
        all_symbols.update(db_df['symbol'].tolist())
    
    for symbol in sorted(all_symbols):
        col1, col2, col3, col4, col5, col6 = st.columns([2, 1, 1, 1, 1, 1])
        
        if not exchange_df.empty and symbol in exchange_df['symbol'].values:
            pos = exchange_df[exchange_df['symbol'] == symbol].iloc[0]
            source_badge = '<span class="exchange-badge">LIVE</span>'
        elif not db_df.empty and symbol in db_df['symbol'].values:
            pos = db_df[db_df['symbol'] == symbol].iloc[0]
            source_badge = '<span class="db-badge">DB</span>'
        else:
            continue
        
        with col1:
            side_emoji = "🟢" if pos['side'] in ['buy', 'long'] else "🔴"
            st.markdown(f"{side_emoji} **{symbol}** {source_badge}", unsafe_allow_html=True)
        
        with col2:
            st.metric("Entry", f"${pos['entry_price']:.2f}", label_visibility="collapsed")
        
        with col3:
            st.metric("Current", f"${pos['mark_price']:.2f}", label_visibility="collapsed")
        
        with col4:
            pnl = pos['unrealized_pnl']
            pnl_pct = pos['pnl_percent']
            color = "green" if pnl >= 0 else "red"
            st.markdown(f'<span style="color:{color}">${pnl:.2f} ({pnl_pct:.2f}%)</span>', unsafe_allow_html=True)
        
        with col5:
            st.metric("Size", f"{pos['contracts']:.4f}", label_visibility="collapsed")
        
        with col6:
            if 'margin' in pos:
                st.metric("Margin", f"${pos['margin']:.2f}", label_visibility="collapsed")

# ==========================================
# 다중 기간 성과 분석 함수
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

def get_equity_history(current_balance, days=None):
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
            return pd.DataFrame()
        
        df['close_timestamp'] = pd.to_datetime(df['close_timestamp'])
        df['balance'] = current_balance - df['reverse_cumulative_pnl']
        
        # 현재 시점 추가
        current_row = pd.DataFrame({
            'close_timestamp': [datetime.now()],
            'balance': [current_balance]
        })
        
        result_df = pd.concat([
            df[['close_timestamp', 'balance']], 
            current_row
        ]).sort_values('close_timestamp')
        
        return result_df
        
    except Exception as e:
        st.error(f"자산 추이 조회 오류: {e}")
        return pd.DataFrame()

# ==========================================
# 메인 함수
# ==========================================

def main():
    # DB 초기화
    init_database()
    
    # 헤더
    st.markdown('<div class="main-header">Trading Dashboard v6 - Enhanced Performance</div>', unsafe_allow_html=True)
    
    # 사이드바 - 설정
    st.sidebar.header("⚙️ Settings")
    
    # 초기 잔고 설정
    st.sidebar.subheader("💰 Account Balance")
    
    current_balance = get_account_balance()
    initial_balance = get_or_set_initial_balance()
    lifetime_start_balance = get_or_set_lifetime_start_balance()
    
    if initial_balance is None and current_balance is not None:
        # 처음 실행 시 현재 잔고를 초기 잔고로 설정
        initial_balance = get_or_set_initial_balance(current_balance)
        st.sidebar.success(f"초기 잔고 설정: ${initial_balance:.2f}")
    
    if lifetime_start_balance is None and current_balance is not None:
        # Lifetime 시작 잔고도 처음에는 현재 잔고로 설정
        lifetime_start_balance = get_or_set_lifetime_start_balance(current_balance)
        st.sidebar.success(f"Lifetime 시작 잔고 설정: ${lifetime_start_balance:.2f}")
    
    if initial_balance:
        st.sidebar.info(f"💎 초기 잔고: ${initial_balance:.2f}")
    
    if lifetime_start_balance:
        st.sidebar.info(f"🌟 Lifetime 시작 잔고: ${lifetime_start_balance:.2f}")
        
        # 잔고 설정 옵션
        with st.sidebar.expander("🔧 잔고 재설정"):
            st.markdown("**초기 잔고 (기본 기준)**")
            new_initial = st.number_input(
                "새 초기 잔고",
                min_value=0.0,
                value=float(initial_balance),
                step=100.0,
                key="new_initial"
            )
            
            if st.button("💾 초기 잔고 저장", key="save_initial"):
                if reset_initial_balance(new_initial):
                    st.success("✅ 초기 잔고가 업데이트되었습니다!")
                    st.rerun()
            
            st.markdown("---")
            st.markdown("**Lifetime 시작 잔고** (전체 수익률 계산용)")
            new_lifetime = st.number_input(
                "Lifetime 시작 잔고",
                min_value=0.0,
                value=float(lifetime_start_balance),
                step=100.0,
                key="new_lifetime",
                help="트레이딩을 시작했을 때의 잔고를 입력하세요"
            )
            
            if st.button("💾 Lifetime 시작 잔고 저장", key="save_lifetime"):
                if reset_lifetime_start_balance(new_lifetime):
                    st.success("✅ Lifetime 시작 잔고가 업데이트되었습니다!")
                    st.rerun()
    
    st.sidebar.markdown("---")
    
    data_source = st.sidebar.radio(
        "Data Source",
        ["Exchange + DB", "Exchange Only", "DB Only"],
        index=0
    )
    
    auto_refresh = st.sidebar.checkbox("Auto Refresh (10s)", value=False)
    auto_sync = st.sidebar.checkbox("Auto Sync DB", value=True)
    
    # 포지션 스냅샷 자동 저장 (수동 거래 감지용)
    enable_manual_detection = st.sidebar.checkbox("Manual Trade Detection", value=True, 
                                                   help="수동 포지션 진입/종료 자동 감지")
    
    # 자동 동기화
    if auto_sync:
        if 'last_sync_time' not in st.session_state:
            st.session_state.last_sync_time = datetime.now() - timedelta(seconds=31)
        
        time_since_sync = (datetime.now() - st.session_state.last_sync_time).total_seconds()
        
        if time_since_sync > 30:
            try:
                exchange_pos = get_exchange_positions()
                db_pos = get_db_positions()
                comparison = compare_positions(exchange_pos, db_pos)
                
                if comparison['db_only']:
                    if sync_positions_to_db(comparison):
                        st.session_state.last_sync_time = datetime.now()
                else:
                    st.session_state.last_sync_time = datetime.now()
                    
            except Exception as e:
                st.sidebar.error(f"자동 동기화 오류: {e}")
        
        next_sync = 30 - time_since_sync
        if next_sync > 0:
            st.sidebar.caption(f"다음 동기화: {int(next_sync)}초 후")
    
    # 수동 거래 감지
    if enable_manual_detection:
        if 'last_detection_time' not in st.session_state:
            st.session_state.last_detection_time = datetime.now() - timedelta(seconds=61)
        
        time_since_detection = (datetime.now() - st.session_state.last_detection_time).total_seconds()
        
        if time_since_detection > 60:
            exchange_pos = get_exchange_positions()
            if not exchange_pos.empty:
                save_position_snapshot(exchange_pos)
                detected = detect_manual_trades()
                if detected:
                    st.sidebar.success(f"🔍 {len(detected)}개 수동 거래 감지!")
                
                st.session_state.last_detection_time = datetime.now()
    
    # 데이터 로드
    exchange_positions = pd.DataFrame()
    db_positions = pd.DataFrame()
    
    if data_source in ["Exchange + DB", "Exchange Only"]:
        exchange_positions = get_exchange_positions()
    
    if data_source in ["Exchange + DB", "DB Only"]:
        db_positions = get_db_positions()
    
    # 탭 구성
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "📊 Overview",
        "🔄 Sync Status", 
        "📈 Performance Analysis",
        "🎯 Manual Trades",
        "🤖 AI Monitor"
    ])
    
    with tab1:
        # 잔고 정보
        if not exchange_positions.empty or not db_positions.empty:
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                total_positions = len(exchange_positions) if not exchange_positions.empty else len(db_positions)
                st.metric("Active Positions", total_positions)
            
            with col2:
                if not exchange_positions.empty:
                    total_pnl = exchange_positions['unrealized_pnl'].sum()
                elif not db_positions.empty:
                    total_pnl = db_positions['unrealized_pnl'].sum()
                else:
                    total_pnl = 0
                st.metric("Total PnL", f"${total_pnl:.2f}")
            
            with col3:
                if not exchange_positions.empty:
                    total_margin = exchange_positions['margin'].sum()
                elif not db_positions.empty:
                    total_margin = db_positions['margin'].sum()
                else:
                    total_margin = 0
                st.metric("Total Margin", f"${total_margin:.2f}")
            
            with col4:
                source_text = data_source.upper()
                st.metric("Data Source", source_text)
        
        st.markdown("---")
        display_combined_positions(exchange_positions, db_positions)
    
    with tab2:
        st.header("🔄 Exchange-DB Synchronization")
        
        if st.button("🔍 Check Sync Status"):
            with st.spinner("Comparing positions..."):
                exchange_pos = get_exchange_positions()
                db_pos = get_db_positions()
                comparison = compare_positions(exchange_pos, db_pos)
                
                display_sync_status(comparison)
                
                if comparison['matched']:
                    st.subheader("✅ Matched Positions")
                    matched_df = pd.DataFrame(comparison['matched'])
                    st.dataframe(matched_df, use_container_width=True)
                
                if comparison['exchange_only']:
                    st.subheader("🆕 Exchange Only (Need DB Update)")
                    ex_only_df = pd.DataFrame(comparison['exchange_only'])
                    st.dataframe(ex_only_df, use_container_width=True)
                
                if comparison['db_only']:
                    st.subheader("❌ DB Only (Already Closed)")
                    db_only_df = pd.DataFrame(comparison['db_only'])
                    st.dataframe(db_only_df, use_container_width=True)
    
    with tab3:
        st.header("📈 Performance Analysis")
        
        if current_balance is None or initial_balance is None or lifetime_start_balance is None:
            st.error("⚠️ 잔고 정보를 가져올 수 없습니다. API 키를 확인해주세요.")
            return
        
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
                
                # 초기 잔고 기준선
                fig_equity.add_hline(
                    y=initial_balance,
                    line_dash="dash",
                    line_color="purple",
                    opacity=0.7,
                    annotation_text=f"Initial: ${initial_balance:.2f}",
                    annotation_position="right"
                )
                
                # 기간 시작 기준선
                if start_balance != initial_balance:
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
                
                equity_df = pd.read_sql_query(equity_query, conn)
                
                if not equity_df.empty:
                    equity_df['close_timestamp'] = pd.to_datetime(equity_df['close_timestamp'])
                    
                    fig_cumulative = go.Figure()
                    
                    fig_cumulative.add_trace(go.Scatter(
                        x=equity_df['close_timestamp'],
                        y=equity_df['cumulative_pnl'],
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
    
    with tab4:
        st.header("🎯 Manual Trade Detection")
        
        st.info("""
        📌 **수동 거래 감지 시스템**
        - 거래소 포지션을 주기적으로 모니터링
        - 수동 진입/종료/수량 변경 자동 감지
        - 거래 기록에 자동 반영
        """)
        
        try:
            conn = sqlite3.connect('integrated_trades.db')
            
            # 최근 감지된 수동 거래
            manual_query = """
            SELECT 
                detected_at,
                symbol,
                trade_type,
                side,
                amount,
                price,
                note
            FROM manual_trades
            ORDER BY detected_at DESC
            LIMIT 50
            """
            
            manual_df = pd.read_sql_query(manual_query, conn)
            conn.close()
            
            if not manual_df.empty:
                manual_df['detected_at'] = pd.to_datetime(manual_df['detected_at']).dt.strftime('%Y-%m-%d %H:%M:%S')
                
                # 거래 타입별 이모지 매핑
                type_emoji = {
                    'MANUAL_ENTRY': '🆕',
                    'MANUAL_EXIT': '✅',
                    'MANUAL_ADD': '➕',
                    'MANUAL_REDUCE': '➖'
                }
                
                manual_df['🎯'] = manual_df['trade_type'].map(type_emoji)
                
                st.subheader(f"📋 감지된 수동 거래 ({len(manual_df)}건)")
                
                display_cols = ['🎯', 'detected_at', 'symbol', 'trade_type', 'side', 'amount', 'price']
                st.dataframe(
                    manual_df[display_cols],
                    use_container_width=True,
                    hide_index=True
                )
                
                # 통계
                st.markdown("---")
                col1, col2, col3, col4 = st.columns(4)
                
                with col1:
                    entries = len(manual_df[manual_df['trade_type'] == 'MANUAL_ENTRY'])
                    st.metric("🆕 신규 진입", entries)
                
                with col2:
                    exits = len(manual_df[manual_df['trade_type'] == 'MANUAL_EXIT'])
                    st.metric("✅ 완전 청산", exits)
                
                with col3:
                    adds = len(manual_df[manual_df['trade_type'] == 'MANUAL_ADD'])
                    st.metric("➕ 추가 진입", adds)
                
                with col4:
                    reduces = len(manual_df[manual_df['trade_type'] == 'MANUAL_REDUCE'])
                    st.metric("➖ 부분 청산", reduces)
                
            else:
                st.warning("⚠️ 아직 감지된 수동 거래가 없습니다.")
                st.info("포지션 변화가 감지되면 자동으로 기록됩니다. (1분마다 체크)")
            
        except Exception as e:
            st.error(f"수동 거래 조회 오류: {e}")
    
    with tab5:
        st.header("🤖 AI Monitoring Status")
        
        # AI 모니터링 즉시 실행
        col_btn1, col_btn2 = st.columns([1, 3])
        
        with col_btn1:
            if st.button("🚀 즉시 AI 모니터링 실행", type="primary"):
                try:
                    import requests
                    response = requests.post('http://localhost:5000/ai-monitor/force', timeout=30)
                    
                    if response.status_code == 200:
                        result = response.json()
                        st.success(f"✅ AI 모니터링 완료: {result.get('positions_monitored', 0)}개 포지션 분석")
                        if result.get('exit_decisions'):
                            st.warning(f"⚠️ {len(result['exit_decisions'])}개 청산 결정 발생")
                        st.rerun()
                    else:
                        result = response.json()
                        st.error(f"❌ {result.get('message', 'Unknown error')}")
                        
                except requests.exceptions.ConnectionError:
                    st.error("❌ 봇 서버에 연결할 수 없습니다.")
                except Exception as e:
                    st.error(f"❌ 에러: {str(e)}")
        
        st.markdown("---")
        
        try:
            conn = sqlite3.connect('integrated_trades.db')
            
            ai_query = """
            SELECT 
                timestamp,
                symbol,
                ai_decision,
                confidence,
                urgency,
                reason
            FROM trades
            WHERE trade_type = 'AI_MONITOR'
            ORDER BY timestamp DESC
            LIMIT 20
            """
            
            ai_df = pd.read_sql_query(ai_query, conn)
            conn.close()
            
            if not ai_df.empty:
                ai_df['timestamp'] = pd.to_datetime(ai_df['timestamp'])
                ai_df['confidence'] = ai_df['confidence'] * 100
                
                latest_time = ai_df['timestamp'].max()
                st.info(f"📊 최근 AI 모니터링: {latest_time.strftime('%Y-%m-%d %H:%M:%S')}")
                
                st.dataframe(
                    ai_df.style.format({'confidence': '{:.1f}%'}),
                    use_container_width=True
                )
            else:
                st.warning("⚠️ AI 모니터링 기록이 없습니다.")
            
        except Exception as e:
            st.error(f"AI 모니터링 조회 오류: {e}")
    
    # 자동 새로고침
    if auto_refresh:
        import time
        time.sleep(10)
        st.rerun()
    
    # Footer
    st.markdown("---")
    st.caption(f"Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | v6.0 Enhanced")

if __name__ == "__main__":
    main()
