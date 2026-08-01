#!/usr/bin/env python3
"""
Public Dashboard v7.6 Complete - 모든 기능 완벽 통합 + 수동 종료
=======================================================
v7.5의 모든 기능 + 수동 포지션 종료 기능 추가

주요 기능:
1. 🔥 Exchange 연결 문제 해결 (v7.2)
2. 📊 다중 기간 성과 분석 (v6)
3. 📈 심볼별 수익 분석 (v6)
4. 🎯 상세한 그래프와 통계 (v6)
5. ⚡ 실시간 업데이트 (v7)
6. 🤖 AI 모니터링 탭 재구현 (v7.4)
7. 📊 Symbol Analytics 완전 구현 (v7.4)
8. 🧠 AI Reflection 복원 및 개선 (v7.5)
9. 🔴 수동 포지션 종료 기능 (v7.6) - 모든 유저 대상

작성일: 2025-12-14
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
import numpy as np

load_dotenv()

# 페이지 설정
st.set_page_config(
    page_title="Trading Dashboard v7.6 Complete",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ============ 실시간 설정 ============
REALTIME_ENABLED = True
EVENT_POLL_INTERVAL = 2
AUTO_REFRESH_INTERVAL = 3
TRADING_BOT_URL = "http://localhost:5000"

# 🆕 v8.0: DB 경로 통일 — 봇과 반드시 같은 파일을 보게 함
#   기존엔 'integrated_trades.db' 상대경로라 대시보드를 다른 폴더에서 실행하면
#   빈 DB를 새로 만들어 "no such table: completed_trades" 오류가 났음.
#   봇과 동일하게 DB_PATH 환경변수를 우선 사용한다.
DB_PATH = os.getenv('DB_PATH') or os.path.join(
    os.path.dirname(os.path.abspath(__file__)), 'integrated_trades.db')

# ============================================================================
# 🆕 v8.0: 반응성 개선 인프라 (캐싱 + 프래그먼트)
# ============================================================================
# 문제: v7.x는 캐시가 전혀 없어 상호작용마다 바이낸스 API·DB를 전부 재조회 →
#       클릭 한 번에 수 초 지연. 아래 캐시 계층으로 재조회를 제거한다.
#   • TTL 캐시: 같은 데이터를 TTL 동안 재사용 (rerun 되어도 즉시 반환)
#   • 프래그먼트: 특정 영역만 부분 갱신 (전체 페이지 리로드 제거)
#   • 낙관적 UI: 버튼 클릭 시 즉시 반영 → 백그라운드 확인

CACHE_TTL_FAST   = 3    # 포지션·가격 등 실시간성 높은 데이터
CACHE_TTL_NORMAL = 10   # 잔고·봇 상태
CACHE_TTL_SLOW   = 60   # DB 집계·바이낸스 손익 이력

# Streamlit 버전 호환 프래그먼트 데코레이터
def st_fragment(func=None, **kwargs):
    """st.fragment(1.33+) 사용, 미지원 버전에서는 통과"""
    def _wrap(f):
        frag = getattr(st, 'fragment', None) or getattr(st, 'experimental_fragment', None)
        if frag is None:
            return f
        try:
            return frag(**kwargs)(f) if kwargs else frag(f)
        except Exception:
            return f
    return _wrap(func) if func else _wrap


@st.cache_data(ttl=CACHE_TTL_NORMAL, show_spinner=False)
def bot_api_get(path, params=None, timeout=4):
    """봇 REST API GET (TTL 캐시) — 반복 호출로 인한 지연 제거"""
    try:
        r = requests.get(f"{TRADING_BOT_URL}{path}", params=params or {}, timeout=timeout)
        if r.status_code == 200:
            return r.json()
        return {'status': 'error', 'http': r.status_code}
    except Exception as e:
        return {'status': 'error', 'error': str(e)}


def bot_api_post(path, payload=None, timeout=8):
    """봇 REST API POST (캐시 없음 — 상태 변경용). 성공 시 캐시 무효화"""
    try:
        r = requests.post(f"{TRADING_BOT_URL}{path}", json=payload or {}, timeout=timeout)
        ok = r.status_code == 200
        if ok:
            invalidate_caches()
        try:
            return ok, r.json()
        except Exception:
            return ok, {'raw': r.text}
    except Exception as e:
        return False, {'error': str(e)}


@st.cache_data(ttl=CACHE_TTL_SLOW, show_spinner=False)
def cached_db_query(query, db_path=None):
    """DB 조회 결과 캐시 (집계 쿼리 재실행 제거)"""
    try:
        conn = sqlite3.connect(db_path or DB_PATH)
        df = pd.read_sql_query(query, conn)
        conn.close()
        return df
    except Exception:
        return pd.DataFrame()


def invalidate_caches():
    """상태 변경 후 캐시 비우기 (다음 렌더에서 최신값 반영)"""
    try:
        st.cache_data.clear()
    except Exception:
        pass


def fetch_anomalies(limit=100, hours=None):
    """🆕 v8.0: 봇에서 이상 현상(리페인팅) 로그 조회"""
    params = {'limit': limit}
    if hours:
        params['hours'] = hours
    return bot_api_get('/anomalies', params=params, timeout=5)


@st.cache_data(ttl=CACHE_TTL_SLOW, show_spinner=False)
def fetch_binance_realized_pnl(days=30):
    """
    🆕 v8.0: 바이낸스 실제 실현손익 (심볼별)
    내부 DB 집계 대신 거래소 income history를 사용해 바이낸스 화면과 일치시킴.
    """
    return bot_api_get('/binance/realized-pnl', params={'days': days}, timeout=20)

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
    
    .period-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        padding: 1.5rem;
        border-radius: 15px;
        margin-bottom: 1rem;
        text-align: center;
        box-shadow: 0 4px 15px rgba(0, 0, 0, 0.1);
    }
    
    .period-card h2 {
        margin: 0;
        font-size: 2rem;
        font-weight: bold;
    }
    
    .period-card h4 {
        margin: 0 0 0.5rem 0;
        opacity: 0.9;
    }
    
    .period-card p {
        margin: 0.5rem 0;
    }
    
    .period-card small {
        opacity: 0.8;
    }
    
    .metric-card {
        background: white;
        border-radius: 10px;
        padding: 1rem;
        box-shadow: 0 2px 10px rgba(0, 0, 0, 0.05);
        border-left: 4px solid #1f77b4;
    }
    
    .positive-value { color: #2ca02c; }
    .negative-value { color: #d62728; }
    
    /* v7.6: 포지션 종료 버튼 스타일 */
    .close-btn {
        background: linear-gradient(135deg, #eb3349 0%, #f45c43 100%);
        color: white;
        border: none;
        padding: 0.3rem 0.8rem;
        border-radius: 5px;
        cursor: pointer;
        font-size: 0.8rem;
        font-weight: bold;
    }
    
    .close-btn:hover {
        opacity: 0.8;
    }
    
    .position-card {
        background: #f8f9fa;
        border-radius: 10px;
        padding: 1rem;
        margin-bottom: 0.5rem;
        border-left: 4px solid #1f77b4;
    }
    
    .position-card.long {
        border-left-color: #2ca02c;
    }
    
    .position-card.short {
        border-left-color: #d62728;
    }
</style>
""", unsafe_allow_html=True)

# ==========================================
# Helper Functions
# ==========================================

@st.cache_resource(show_spinner=False)
def get_binance_exchange():
    """바이낸스 거래소 객체 (🆕 v8.0: cache_resource로 재연결 비용 제거)"""
    try:
        api_key = os.getenv('BINANCE_API_KEY')
        secret_key = os.getenv('BINANCE_SECRET_KEY')
        
        if not api_key or not secret_key:
            st.warning("⚠️ API 키가 설정되지 않았습니다.")
            return None
        
        exchange = ccxt.binance({
            'apiKey': api_key,
            'secret': secret_key,
            'enableRateLimit': True,
            'options': {
                'defaultType': 'future'
            }
        })
        
        # 연결 테스트
        try:
            balance = exchange.fetch_balance()
            return exchange
        except:
            return None
            
    except Exception as e:
        st.error(f"거래소 연결 오류: {e}")
        return None

@st.cache_data(ttl=CACHE_TTL_NORMAL, show_spinner=False)
def fetch_balance_from_binance(_exchange):
    """바이낸스 실시간 잔고 (🆕 v8.0: TTL 캐시)"""
    try:
        if _exchange is None:
            return {'total': 0, 'free': 0, 'used': 0}
        
        balance = _exchange.fetch_balance()
        
        if 'USDT' in balance:
            return {
                'total': balance['USDT']['total'],
                'free': balance['USDT']['free'],
                'used': balance['USDT']['used']
            }
        else:
            return {'total': 0, 'free': 0, 'used': 0}
        
    except Exception as e:
        return {'total': 0, 'free': 0, 'used': 0, 'error': str(e)}

@st.cache_data(ttl=CACHE_TTL_FAST, show_spinner=False)
def fetch_positions_from_binance(_exchange):
    """
    바이낸스 실시간 포지션 (🆕 v8.0)
      • TTL 캐시로 반복 조회 제거
      • ⭐ ROE% 계산 수정: 바이낸스 UI와 동일하게 (미실현손익 / 초기증거금)
        기존 v7.x는 '가격변동% × 레버리지'로 계산해 실제 값과 어긋났음
        (교차마진·부분청산·수수료 반영분이 빠짐)
    """
    try:
        if _exchange is None:
            return []
        
        positions = _exchange.fetch_positions()
        active_positions = [p for p in positions if float(p['info'].get('positionAmt', 0)) != 0]
        
        result = []
        for pos in active_positions:
            info = pos['info']
            symbol = pos['symbol']
            amt = float(info.get('positionAmt', 0))
            side = 'long' if amt > 0 else 'short'
            amount = abs(amt)
            entry_price = float(info.get('entryPrice', 0) or 0)
            mark_price = float(info.get('markPrice', 0) or 0)
            liquidation_price = float(info.get('liquidationPrice', 0) or 0)
            unrealized_pnl = float(info.get('unRealizedProfit', 0) or 0)
            leverage = float(info.get('leverage', 10) or 10)

            # ⭐ 초기증거금 우선순위: 거래소 제공값 → notional/leverage → 추정
            notional = abs(float(info.get('notional', 0) or 0)) or (amount * mark_price)
            init_margin = 0.0
            for key in ('initialMargin', 'positionInitialMargin', 'isolatedWallet', 'isolatedMargin'):
                try:
                    v = float(info.get(key, 0) or 0)
                    if v > 0:
                        init_margin = v
                        break
                except Exception:
                    continue
            if init_margin <= 0 and leverage > 0:
                init_margin = notional / leverage

            roe_pct = (unrealized_pnl / init_margin * 100) if init_margin > 0 else 0.0
            price_change_pct = ((mark_price - entry_price) / entry_price * 100) if entry_price > 0 else 0.0
            if side == 'short':
                price_change_pct = -price_change_pct

            result.append({
                'symbol': symbol,
                'side': side,
                'amount': amount,
                'entry_price': entry_price,
                'mark_price': mark_price,
                'liquidation_price': liquidation_price,
                'unrealized_pnl': unrealized_pnl,
                'leverage': leverage,
                'notional': notional,
                'init_margin': init_margin,
                'price_change_pct': price_change_pct,   # 순수 가격 변동
                'pnl_percent': roe_pct                   # 바이낸스 ROE와 일치
            })
        
        return result
        
    except Exception as e:
        return []


def close_position_api(symbol, reason="Manual close from dashboard"):
    """
    🆕 v7.6: 포지션 종료 API 호출
    트레이딩 봇의 /positions/close 엔드포인트 호출
    """
    try:
        response = requests.post(
            f"{TRADING_BOT_URL}/positions/close",
            json={
                "symbol": symbol,
                "reason": reason
            },
            timeout=30
        )
        
        if response.status_code == 200:
            return response.json()
        else:
            return {"error": f"API 오류: {response.status_code} - {response.text}"}
            
    except requests.exceptions.Timeout:
        return {"error": "요청 시간 초과 (30초)"}
    except requests.exceptions.ConnectionError:
        return {"error": "트레이딩 봇에 연결할 수 없습니다"}
    except Exception as e:
        return {"error": str(e)}

def get_or_set_initial_balance():
    """초기 잔고 가져오기 또는 설정"""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        c.execute("""
            CREATE TABLE IF NOT EXISTS initial_balance (
                id INTEGER PRIMARY KEY,
                balance REAL,
                set_date TEXT
            )
        """)
        
        c.execute("SELECT balance FROM initial_balance ORDER BY id DESC LIMIT 1")
        result = c.fetchone()
        
        if result:
            initial_balance = result[0]
        else:
            initial_balance = 1000.0
            
        conn.close()
        return initial_balance
        
    except Exception as e:
        st.error(f"초기 잔고 조회 오류: {e}")
        return 1000.0

def get_or_set_lifetime_start_balance():
    """전체 기간 시작 잔고"""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        c.execute("""
            CREATE TABLE IF NOT EXISTS lifetime_balance (
                id INTEGER PRIMARY KEY,
                balance REAL,
                set_date TEXT
            )
        """)
        
        c.execute("SELECT balance FROM lifetime_balance ORDER BY id DESC LIMIT 1")
        result = c.fetchone()
        
        if result:
            lifetime_balance = result[0]
        else:
            lifetime_balance = 1000.0
            
        conn.close()
        return lifetime_balance
        
    except Exception as e:
        st.error(f"Lifetime 잔고 조회 오류: {e}")
        return 1000.0

# ==========================================
# Performance Analysis Helper Functions (v6)
# ==========================================

def calculate_lifetime_performance(current_balance, lifetime_start_balance):
    """Lifetime 성과 계산"""
    try:
        conn = sqlite3.connect(DB_PATH)
        
        query = """
        SELECT 
            COUNT(*) as trades,
            SUM(CASE WHEN is_win = 1 THEN 1 ELSE 0 END) as wins,
            COUNT(*) as total
        FROM completed_trades
        """
        
        df = pd.read_sql_query(query, conn)
        conn.close()
        
        if not df.empty and df.iloc[0]['total'] > 0:
            trades = int(df.iloc[0]['trades'])
            wins = int(df.iloc[0]['wins'])
            win_rate = (wins / trades * 100) if trades > 0 else 0
        else:
            trades = 0
            win_rate = 0
        
        lifetime_pnl = current_balance - lifetime_start_balance
        lifetime_pct = (lifetime_pnl / lifetime_start_balance * 100) if lifetime_start_balance > 0 else 0
        
        return {
            'lifetime_pnl': lifetime_pnl,
            'lifetime_pct': lifetime_pct,
            'trades': trades,
            'win_rate': win_rate
        }
        
    except Exception:
        return {
            'lifetime_pnl': 0,
            'lifetime_pct': 0,
            'trades': 0,
            'win_rate': 0
        }

def calculate_period_performance(current_balance, initial_balance, days):
    """특정 기간 성과 계산"""
    try:
        conn = sqlite3.connect(DB_PATH)
        
        query = f"""
        SELECT 
            COUNT(*) as trades,
            SUM(CASE WHEN is_win = 1 THEN 1 ELSE 0 END) as wins,
            SUM(pnl_usdt - COALESCE(commission, 0)) as total_pnl
        FROM completed_trades
        WHERE close_timestamp >= date('now', '-{days} days')
        """
        
        df = pd.read_sql_query(query, conn)
        conn.close()
        
        if not df.empty:
            trades = int(df.iloc[0]['trades']) if pd.notna(df.iloc[0]['trades']) else 0
            wins = int(df.iloc[0]['wins']) if pd.notna(df.iloc[0]['wins']) else 0
            period_pnl = float(df.iloc[0]['total_pnl']) if pd.notna(df.iloc[0]['total_pnl']) else 0
            win_rate = (wins / trades * 100) if trades > 0 else 0
        else:
            trades = 0
            period_pnl = 0
            win_rate = 0
        
        period_pct = (period_pnl / initial_balance * 100) if initial_balance > 0 else 0
        
        return {
            'period_pnl': period_pnl,
            'period_pct': period_pct,
            'trades': trades,
            'win_rate': win_rate
        }
        
    except Exception:
        return {
            'period_pnl': 0,
            'period_pct': 0,
            'trades': 0,
            'win_rate': 0
        }

def get_equity_history(current_balance, days=None, lifetime_start_balance=None):
    """자산 추이 데이터 가져오기"""
    try:
        conn = sqlite3.connect(DB_PATH)
        
        if days:
            query = f"""
            SELECT 
                close_timestamp,
                SUM(pnl_usdt - COALESCE(commission, 0)) OVER (ORDER BY close_timestamp) as cumulative_pnl
            FROM completed_trades
            WHERE close_timestamp >= date('now', '-{days} days')
            ORDER BY close_timestamp
            """
        else:
            query = """
            SELECT 
                close_timestamp,
                SUM(pnl_usdt - COALESCE(commission, 0)) OVER (ORDER BY close_timestamp) as cumulative_pnl
            FROM completed_trades
            ORDER BY close_timestamp
            """
        
        df = pd.read_sql_query(query, conn)
        conn.close()
        
        if not df.empty:
            df['close_timestamp'] = pd.to_datetime(df['close_timestamp'])
            
            # 시작 잔고 설정
            if lifetime_start_balance:
                start_balance = lifetime_start_balance
            else:
                start_balance = current_balance - df['cumulative_pnl'].iloc[-1] if not df.empty else current_balance
            
            df['balance'] = start_balance + df['cumulative_pnl']
            return df
        else:
            return pd.DataFrame()
            
    except Exception:
        return pd.DataFrame()

# ==========================================
# Main Dashboard
# ==========================================

def main():
    st.markdown('<h1 class="main-header">⚡ Automated Trading Dashboard v7.6 Complete</h1>', unsafe_allow_html=True)
    
    # Realtime Badge
    col1, col2, col3 = st.columns([2, 1, 2])
    with col2:
        st.markdown('<div class="realtime-badge">🔴 LIVE TRADING</div>', unsafe_allow_html=True)
    
    # Exchange 초기화 (Session State 활용)
    if 'exchange' not in st.session_state:
        with st.spinner("바이낸스 연결 중..."):
            st.session_state.exchange = get_binance_exchange()
    
    exchange = st.session_state.exchange
    
    # Exchange 재연결 버튼
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        if st.button("🔄 Exchange 재연결", use_container_width=True):
            st.session_state.exchange = get_binance_exchange()
            exchange = st.session_state.exchange
            st.rerun()
    
    # Exchange 상태 표시
    if exchange:
        st.success("✅ 바이낸스 연결됨")
    else:
        st.error("❌ 바이낸스 연결 실패 - API 키를 확인하세요")
        st.stop()
    
    # 탭 생성
    tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8 = st.tabs([
        "📊 Trading Overview", 
        "📈 Performance Analysis", 
        "📜 Trade History",
        "🎯 Symbol Analytics",
        "🤖 AI Monitoring",
        "🧠 AI Reflection",
        "⚙️ Position Control",
        "⚠️ 이상 감지"
    ])
    
    # ==========================================
    # Tab 1: Trading Overview
    # ==========================================
    with tab1:
        st.header("📊 Real-time Trading Status")

        # 🆕 v8.0: 실시간 요약을 프래그먼트로 분리 → 이 영역만 3초마다 부분 갱신
        #          (전체 페이지 리로드 없이 잔고·포지션 수치가 살아있는 것처럼 반응)
        @st_fragment(run_every=3)
        def render_live_summary():
            bd = fetch_balance_from_binance(exchange)
            ps = fetch_positions_from_binance(exchange)
            up = sum(p['unrealized_pnl'] for p in ps) if ps else 0.0
            k1, k2, k3, k4, k5 = st.columns(5)
            with k1:
                st.metric("💰 총 잔고", f"${bd.get('total', 0):,.2f}")
            with k2:
                st.metric("✅ 사용 가능", f"${bd.get('free', 0):,.2f}")
            with k3:
                st.metric("🎯 포지션", f"{len(ps)}개")
            with k4:
                st.metric("📈 미실현 손익", f"${up:,.2f}", delta=f"{up:,.2f}")
            with k5:
                st.caption("🔄 실시간")
                st.caption(datetime.now().strftime("%H:%M:%S"))

        render_live_summary()
        st.markdown("---")

        # 잔고 정보
        balance_data = fetch_balance_from_binance(exchange)
        current_balance = balance_data['total']
        
        if balance_data['total'] > 0:
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("💰 총 잔고", f"${balance_data['total']:,.2f}")
            with col2:
                st.metric("✅ 사용 가능", f"${balance_data['free']:,.2f}")
            with col3:
                st.metric("🔒 사용 중", f"${balance_data['used']:,.2f}")
            with col4:
                usage_rate = (balance_data['used'] / balance_data['total'] * 100) if balance_data['total'] > 0 else 0
                st.metric("📊 사용률", f"{usage_rate:.1f}%")
        
        # 포지션 정보
        positions = fetch_positions_from_binance(exchange)
        
        if positions:
            st.subheader("🎯 Active Positions")
            
            # 포지션 요약
            total_unrealized_pnl = sum(p['unrealized_pnl'] for p in positions)
            total_position_value = sum(p['amount'] * p['mark_price'] for p in positions)
            
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("포지션 수", len(positions))
            with col2:
                color = "green" if total_unrealized_pnl >= 0 else "red"
                st.metric("미실현 손익", f"${total_unrealized_pnl:,.2f}")
            with col3:
                st.metric("포지션 가치", f"${total_position_value:,.2f}")
            
            # 🆕 v7.6: 수동 종료 섹션
            st.markdown("---")
            st.markdown("### 🔴 Position Control (All Users)")
            st.warning("⚠️ 아래 버튼을 클릭하면 **모든 유저**의 해당 포지션이 시장가로 즉시 종료됩니다.")
            
            # 각 포지션에 대해 종료 버튼 표시
            for i, pos in enumerate(positions):
                symbol = pos['symbol']
                side = pos['side']
                pnl = pos['unrealized_pnl']
                pnl_pct = pos['pnl_percent']
                
                # 색상 설정
                side_color = "🟢" if side == 'long' else "🔴"
                pnl_color = "green" if pnl >= 0 else "red"
                
                col_info, col_pnl, col_btn = st.columns([3, 2, 1])
                
                with col_info:
                    st.markdown(f"""
                    **{side_color} {symbol}** ({side.upper()})  
                    Entry: ${pos['entry_price']:,.4f} → Current: ${pos['mark_price']:,.4f}  
                    Amount: {pos['amount']:.4f} | Leverage: {pos['leverage']}x
                    """)
                
                with col_pnl:
                    pnl_display = f"${pnl:+,.2f}" if pnl >= 0 else f"-${abs(pnl):,.2f}"
                    st.markdown(f"""
                    <div style="padding: 10px; text-align: center;">
                        <span style="font-size: 1.5rem; font-weight: bold; color: {pnl_color};">
                            {pnl_display}
                        </span><br>
                        <span style="color: {pnl_color};">({pnl_pct:+.2f}%)</span>
                    </div>
                    """, unsafe_allow_html=True)
                
                with col_btn:
                    # 고유한 키 생성
                    btn_key = f"close_{symbol.replace('/', '_')}_{i}"
                    
                    if st.button(f"🔴 종료", key=btn_key, type="primary"):
                        # 확인 메시지를 위한 세션 상태 설정
                        st.session_state[f'confirm_{btn_key}'] = True
                
                # 확인 다이얼로그
                if st.session_state.get(f'confirm_{btn_key}', False):
                    st.warning(f"⚠️ **{symbol}** 포지션을 정말 종료하시겠습니까?")
                    st.info(f"현재 PnL: {pnl_display} ({pnl_pct:+.2f}%)")
                    
                    confirm_col1, confirm_col2 = st.columns(2)
                    
                    with confirm_col1:
                        if st.button(f"✅ 확인 - 종료 실행", key=f"confirm_yes_{btn_key}", type="primary"):
                            with st.spinner(f"{symbol} 포지션 종료 중..."):
                                result = close_position_api(symbol, "Manual close from dashboard")
                                
                                if 'error' in result:
                                    st.error(f"❌ 종료 실패: {result['error']}")
                                else:
                                    st.success(f"✅ {symbol} 포지션 종료 완료!")
                                    st.json(result)
                                    # 상태 초기화 및 페이지 새로고침
                                    st.session_state[f'confirm_{btn_key}'] = False
                                    time_module.sleep(1)
                                    st.rerun()
                    
                    with confirm_col2:
                        if st.button(f"❌ 취소", key=f"confirm_no_{btn_key}"):
                            st.session_state[f'confirm_{btn_key}'] = False
                            st.rerun()
                
                st.markdown("---")
            
            # 🆕 v7.6: 전체 포지션 종료 버튼
            st.markdown("### ⚠️ Emergency: Close All Positions")
            
            if st.button("🚨 모든 포지션 즉시 종료", type="secondary"):
                st.session_state['confirm_close_all'] = True
            
            if st.session_state.get('confirm_close_all', False):
                st.error("⚠️ **경고**: 모든 포지션을 종료하시겠습니까? 이 작업은 되돌릴 수 없습니다!")
                
                col_all1, col_all2 = st.columns(2)
                
                with col_all1:
                    if st.button("✅ 예, 모두 종료", type="primary", key="confirm_all_yes"):
                        with st.spinner("모든 포지션 종료 중..."):
                            all_success = True
                            for pos in positions:
                                result = close_position_api(pos['symbol'], "Emergency close all from dashboard")
                                if 'error' in result:
                                    st.error(f"❌ {pos['symbol']} 종료 실패: {result['error']}")
                                    all_success = False
                                else:
                                    st.success(f"✅ {pos['symbol']} 종료 완료")
                            
                            if all_success:
                                st.balloons()
                                st.success("🎉 모든 포지션 종료 완료!")
                            
                            st.session_state['confirm_close_all'] = False
                            time_module.sleep(2)
                            st.rerun()
                
                with col_all2:
                    if st.button("❌ 취소", key="confirm_all_no"):
                        st.session_state['confirm_close_all'] = False
                        st.rerun()
            
            st.markdown("---")
            
            # 포지션 테이블 (기존)
            st.subheader("📋 Position Details")
            df_positions = pd.DataFrame(positions)
            
            # 컬럼 포맷팅
            for col in ['entry_price', 'mark_price', 'liquidation_price']:
                if col in df_positions.columns:
                    df_positions[col] = df_positions[col].apply(lambda x: f"${x:,.2f}")
            
            if 'unrealized_pnl' in df_positions.columns:
                df_positions['unrealized_pnl'] = df_positions['unrealized_pnl'].apply(
                    lambda x: f"${x:,.2f}" if x >= 0 else f"-${abs(x):,.2f}"
                )
            
            if 'pnl_percent' in df_positions.columns:
                df_positions['pnl_percent'] = df_positions['pnl_percent'].apply(lambda x: f"{x:+.2f}%")
            
            st.dataframe(
                df_positions[['symbol', 'side', 'amount', 'entry_price', 'mark_price', 
                             'unrealized_pnl', 'pnl_percent', 'leverage']],
                use_container_width=True
            )
        else:
            st.info("📭 현재 활성 포지션이 없습니다.")
    
    # ==========================================
    # Tab 2: Performance Analysis (v6 기능 복원)
    # ==========================================
    with tab2:
        st.header("📈 Performance Analysis")
        
        # 잔고 정보 가져오기
        initial_balance = get_or_set_initial_balance()
        lifetime_start_balance = get_or_set_lifetime_start_balance()
        
        if current_balance and initial_balance and lifetime_start_balance:
            try:
                # ===================================
                # 다중 기간 성과 요약 카드 (v6)
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
                    
                    # 기준선 표시
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
                        fig_equity.add_hline(
                            y=initial_balance,
                            line_dash="dash",
                            line_color="purple",
                            opacity=0.7,
                            annotation_text=f"Initial: ${initial_balance:.2f}",
                            annotation_position="right"
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
                # 30일 통계 (v6)
                # ===================================
                conn = sqlite3.connect(DB_PATH)
                
                stats_query = """
                SELECT 
                    COUNT(*) as total_trades,
                    SUM(CASE WHEN is_win = 1 THEN 1 ELSE 0 END) as wins,
                    SUM(CASE WHEN is_win = 0 THEN 1 ELSE 0 END) as losses,
                    SUM(pnl_usdt - COALESCE(commission, 0)) as total_pnl,
                    AVG(pnl_percent) as avg_pnl_percent,
                    MAX(pnl_usdt - COALESCE(commission, 0)) as max_profit,
                    MIN(pnl_usdt - COALESCE(commission, 0)) as max_loss,
                    AVG(CASE WHEN is_win = 1 THEN (pnl_usdt - COALESCE(commission, 0)) END) as avg_win,
                    AVG(CASE WHEN is_win = 0 THEN (pnl_usdt - COALESCE(commission, 0)) END) as avg_loss
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
                    
                    # ===================================
                    # 누적 PnL 그래프
                    # ===================================
                    st.subheader("💰 Cumulative PnL Over Time (30D)")
                    
                    equity_query = """
                    SELECT 
                        close_timestamp,
                        (pnl_usdt - COALESCE(commission, 0)) as pnl_usdt,
                        SUM(pnl_usdt - COALESCE(commission, 0)) OVER (ORDER BY close_timestamp) as cumulative_pnl
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
                    
                    st.markdown("---")
                    
                    # ===================================
                    # 심볼별 성과 및 Win Rate 분포
                    # ===================================
                    col_sym, col_wr = st.columns(2)
                    
                    with col_sym:
                        st.subheader("🎯 Symbol Performance")
                        
                        symbol_query = """
                        SELECT 
                            symbol,
                            COUNT(*) as trades,
                            SUM(CASE WHEN is_win = 1 THEN 1 ELSE 0 END) as wins,
                            ROUND(AVG(CASE WHEN is_win = 1 THEN 1.0 ELSE 0.0 END) * 100, 1) as win_rate,
                            ROUND(SUM(pnl_usdt - COALESCE(commission, 0)), 2) as total_pnl,
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
                    
                    # ===================================
                    # Best & Worst 거래
                    # ===================================
                    col_best, col_worst = st.columns(2)
                    
                    with col_best:
                        st.subheader("🏆 Top 5 Best Trades")
                        
                        best_query = """
                        SELECT 
                            symbol,
                            ROUND(pnl_usdt - COALESCE(commission, 0), 2) as pnl,
                            ROUND(pnl_percent, 2) as pnl_pct,
                            close_timestamp
                        FROM completed_trades
                        WHERE close_timestamp >= date('now', '-30 days')
                        ORDER BY (pnl_usdt - COALESCE(commission, 0)) DESC
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
                            ROUND(pnl_usdt - COALESCE(commission, 0), 2) as pnl,
                            ROUND(pnl_percent, 2) as pnl_pct,
                            close_timestamp
                        FROM completed_trades
                        WHERE close_timestamp >= date('now', '-30 days')
                        ORDER BY (pnl_usdt - COALESCE(commission, 0)) ASC
                        LIMIT 5
                        """
                        
                        worst_df = pd.read_sql_query(worst_query, conn)
                        
                        if not worst_df.empty:
                            worst_df['close_timestamp'] = pd.to_datetime(worst_df['close_timestamp']).dt.strftime('%m-%d %H:%M')
                            worst_df.insert(0, '', ['💀', '😱', '😢', '😕', '😐'][:len(worst_df)])
                            st.dataframe(worst_df, use_container_width=True, hide_index=True)
                    
                    st.markdown("---")
                    
                    # ===================================
                    # 추가 통계 차트
                    # ===================================
                    col_dist, col_dur, col_rr = st.columns(3)
                    
                    with col_dist:
                        st.subheader("📉 PnL Distribution")
                        
                        pnl_query = """
                        SELECT (pnl_usdt - COALESCE(commission, 0)) as pnl_usdt
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
                            (pnl_usdt - COALESCE(commission, 0)) as pnl_usdt
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
        else:
            st.error("⚠️ 잔고 정보를 가져올 수 없습니다.")
    
    # ==========================================
    # Tab 3: Trade History
    # ==========================================
    with tab3:
        st.header("📜 Trade History")
        
        try:
            conn = sqlite3.connect(DB_PATH)
            
            # 기간 필터
            col1, col2 = st.columns([1, 3])
            with col1:
                period_filter = st.selectbox(
                    "기간 선택",
                    ["최근 24시간", "최근 7일", "최근 30일", "전체"],
                    index=1
                )
            
            # 쿼리 생성
            period_conditions = {
                "최근 24시간": "WHERE close_timestamp >= datetime('now', '-1 day')",
                "최근 7일": "WHERE close_timestamp >= datetime('now', '-7 days')",
                "최근 30일": "WHERE close_timestamp >= datetime('now', '-30 days')",
                "전체": ""
            }
            
            where_clause = period_conditions[period_filter]
            
            query = f"""
            SELECT 
                close_timestamp,
                symbol,
                side,
                entry_price,
                exit_price,
                amount,
                (pnl_usdt - COALESCE(commission, 0)) as pnl_usdt,
                pnl_percent,
                holding_time_minutes,
                close_reason,
                position_type,
                realized_pnl_binance,
                COALESCE(commission, 0) as commission
            FROM completed_trades
            {where_clause}
            ORDER BY close_timestamp DESC
            LIMIT 100
            """
            
            df_trades = pd.read_sql_query(query, conn)
            
            if not df_trades.empty:
                # 통계 표시
                total_trades = len(df_trades)
                total_pnl = df_trades['pnl_usdt'].sum()
                wins = len(df_trades[df_trades['pnl_usdt'] > 0])
                win_rate = (wins / total_trades * 100) if total_trades > 0 else 0
                
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric("거래 수", total_trades)
                with col2:
                    st.metric("총 손익", f"${total_pnl:,.2f}")
                with col3:
                    st.metric("승률", f"{win_rate:.1f}%")
                with col4:
                    st.metric("평균 손익", f"${total_pnl/total_trades:,.2f}")
                
                st.markdown("---")
                
                # 포맷팅
                df_trades['close_timestamp'] = pd.to_datetime(df_trades['close_timestamp'])
                df_trades['entry_price'] = df_trades['entry_price'].apply(lambda x: f"${x:,.2f}")
                df_trades['exit_price'] = df_trades['exit_price'].apply(lambda x: f"${x:,.2f}")
                df_trades['pnl_usdt'] = df_trades['pnl_usdt'].apply(
                    lambda x: f"${x:,.2f}" if x >= 0 else f"-${abs(x):,.2f}"
                )
                df_trades['pnl_percent'] = df_trades['pnl_percent'].apply(lambda x: f"{x:+.2f}%")
                df_trades['holding_time'] = df_trades['holding_time_minutes'].apply(
                    lambda x: f"{int(x/60)}h {int(x%60)}m" if x >= 60 else f"{int(x)}m"
                )
                
                # Binance 확인 표시
                df_trades['verified'] = df_trades['realized_pnl_binance'].apply(
                    lambda x: '✅' if pd.notna(x) else '📊'
                )
                
                # 🆕 수수료 표시
                if 'commission' in df_trades.columns:
                    df_trades['fee'] = df_trades['commission'].apply(
                        lambda x: f"${x:,.2f}" if pd.notna(x) and x > 0 else "-"
                    )
                
                # 컬럼 선택 및 표시
                display_columns = ['close_timestamp', 'symbol', 'side', 'entry_price', 
                                 'exit_price', 'pnl_usdt', 'fee', 'pnl_percent', 'holding_time', 
                                 'close_reason', 'verified']
                # fee 컬럼이 없으면 제외
                display_columns = [c for c in display_columns if c in df_trades.columns]
                
                st.dataframe(
                    df_trades[display_columns],
                    use_container_width=True,
                    hide_index=True
                )
            else:
                st.info("📭 거래 내역이 없습니다.")
            
            conn.close()
            
        except Exception as e:
            st.error(f"거래 내역 조회 오류: {e}")
    
    # ==========================================
    # Tab 4: Symbol Analytics
    # ==========================================
    with tab4:
        st.header("🎯 Symbol Analytics")
        
        try:
            conn = sqlite3.connect(DB_PATH)
            
            # 기간 선택
            col1, col2 = st.columns([1, 3])
            with col1:
                period_filter = st.selectbox(
                    "분석 기간",
                    options=[7, 30, 90, 365, -1],
                    format_func=lambda x: "전체" if x == -1 else f"최근 {x}일",
                    key="symbol_period"
                )
            
            # 심볼별 상세 분석
            # ================================================================
            # 🆕 v8.0: 바이낸스 실제 실현손익 (내부 DB 집계와 불일치 문제 해결)
            # ================================================================
            st.subheader("💰 바이낸스 실제 실현손익 (거래소 기준)")
            st.caption(
                "거래소 income history(REALIZED_PNL + COMMISSION + FUNDING_FEE)를 직접 집계합니다. "
                "아래 Performance Matrix는 봇 내부 DB 기준이라 수수료·펀딩비·거래소측 체결(SL/TP)이 "
                "누락될 수 있어 값이 다를 수 있습니다."
            )

            bcol1, bcol2 = st.columns([1, 3])
            with bcol1:
                bn_days = st.selectbox("조회 기간", [7, 30, 90, 180],
                                       format_func=lambda d: f"최근 {d}일",
                                       index=1, key="bn_pnl_days")
            with bcol2:
                st.write("")
                if st.button("🔄 바이낸스에서 재조회", key="bn_pnl_refresh"):
                    invalidate_caches()

            bn = fetch_binance_realized_pnl(days=bn_days)

            if bn.get('status') == 'success':
                tot = bn.get('totals', {})
                m1, m2, m3, m4 = st.columns(4)
                with m1:
                    st.metric("순 실현손익", f"${tot.get('net_pnl', 0):,.2f}")
                with m2:
                    st.metric("실현손익(총)", f"${tot.get('realized_pnl', 0):,.2f}")
                with m3:
                    st.metric("수수료", f"${tot.get('commission', 0):,.2f}")
                with m4:
                    st.metric("펀딩비", f"${tot.get('funding_fee', 0):,.2f}")

                bn_syms = bn.get('symbols', [])
                if bn_syms:
                    bn_df = pd.DataFrame(bn_syms)

                    fig_bn = px.bar(
                        bn_df.head(20), x='symbol', y='net_pnl',
                        color='net_pnl', color_continuous_scale=['#d62728', '#cccccc', '#2ca02c'],
                        labels={'net_pnl': '순 실현손익 (USDT)', 'symbol': '심볼'}
                    )
                    fig_bn.update_layout(height=320, margin=dict(l=10, r=10, t=10, b=10),
                                         coloraxis_showscale=False)
                    st.plotly_chart(fig_bn, use_container_width=True, key="bn_pnl_chart")

                    # 내부 DB와 대조 (불일치 진단)
                    try:
                        db_cmp = cached_db_query("""
                            SELECT symbol, ROUND(SUM(pnl_usdt - COALESCE(commission,0)), 2) AS db_pnl
                            FROM completed_trades
                            GROUP BY symbol
                        """)
                        if not db_cmp.empty:
                            merged = bn_df.merge(db_cmp, on='symbol', how='outer').fillna(0)
                            merged['차이'] = (merged['net_pnl'] - merged['db_pnl']).round(2)
                            merged = merged.reindex(
                                merged['차이'].abs().sort_values(ascending=False).index
                            )
                            show_cmp = merged[['symbol', 'net_pnl', 'db_pnl', '차이',
                                               'realized_pnl', 'commission', 'funding_fee']].copy()
                            show_cmp.columns = ['심볼', '바이낸스 실제', '봇 DB 집계', '차이',
                                                '실현손익', '수수료', '펀딩비']
                            st.markdown("**🔍 바이낸스 vs 봇 DB 대조** — 차이가 큰 심볼은 거래소측 체결(SL/TP)이나 펀딩비 누락 가능성")
                            st.dataframe(show_cmp, use_container_width=True, hide_index=True, height=320)
                    except Exception as e:
                        st.caption(f"내부 DB 대조 생략: {e}")
                else:
                    st.info("해당 기간 실현손익 내역이 없습니다.")

                st.caption(f"조회 시각: {bn.get('updated_at', '-')} · 출처: {bn.get('source', '-')}")
            else:
                st.warning(
                    f"바이낸스 손익을 가져올 수 없습니다: {bn.get('error', bn.get('http', '봇 연결 실패'))}  \n"
                    "봇이 실행 중인지, /binance/realized-pnl 엔드포인트가 있는 v8.0인지 확인하세요."
                )

            st.markdown("---")

            st.subheader("📊 Symbol Performance Matrix (봇 내부 DB 기준)")
            
            if period_filter == -1:
                date_condition = ""
            else:
                date_condition = f"AND close_timestamp >= date('now', '-{period_filter} days')"
            
            symbol_analysis_query = f"""
            SELECT 
                symbol,
                COUNT(*) as total_trades,
                SUM(CASE WHEN is_win = 1 THEN 1 ELSE 0 END) as wins,
                ROUND(AVG(CASE WHEN is_win = 1 THEN 1.0 ELSE 0.0 END) * 100, 1) as win_rate,
                ROUND(SUM(pnl_usdt - COALESCE(commission, 0)), 2) as total_pnl,
                ROUND(AVG(pnl_usdt - COALESCE(commission, 0)), 2) as avg_pnl,
                ROUND(MAX(pnl_usdt - COALESCE(commission, 0)), 2) as max_win,
                ROUND(MIN(pnl_usdt - COALESCE(commission, 0)), 2) as max_loss,
                ROUND(AVG(holding_time_minutes), 1) as avg_holding_time,
                ROUND(SUM(amount * entry_price), 2) as total_volume,
                ROUND(AVG(pnl_percent), 2) as avg_pnl_percent
            FROM completed_trades
            WHERE 1=1 {date_condition}
            GROUP BY symbol
            HAVING COUNT(*) >= 1
            ORDER BY total_pnl DESC
            """
            
            symbol_analysis_df = pd.read_sql_query(symbol_analysis_query, conn)
            
            if not symbol_analysis_df.empty:
                # Profit Factor 계산
                symbol_analysis_df['profit_factor'] = symbol_analysis_df.apply(
                    lambda row: abs(row['max_win'] / row['max_loss']) if row['max_loss'] != 0 and row['max_loss'] < 0 else 0,
                    axis=1
                )
                
                # Sharpe Ratio 간단 계산 (일별 수익률 기준)
                symbol_analysis_df['efficiency'] = symbol_analysis_df.apply(
                    lambda row: row['avg_pnl'] / abs(row['max_loss']) if row['max_loss'] != 0 else 0,
                    axis=1
                )
                
                # 컬러 코딩
                symbol_analysis_df['status'] = symbol_analysis_df['total_pnl'].apply(
                    lambda x: '🟢' if x > 0 else '🔴'
                )
                
                # 메트릭 카드로 상위 3개 심볼 표시
                st.markdown("### 🏆 Top Performers")
                top_symbols = symbol_analysis_df.nlargest(3, 'total_pnl')
                
                if len(top_symbols) > 0:
                    cols = st.columns(min(3, len(top_symbols)))
                    for idx, (col, (_, row)) in enumerate(zip(cols, top_symbols.iterrows())):
                        with col:
                            st.markdown(f"""
                            <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); 
                                        color: white; padding: 1.5rem; border-radius: 10px; text-align: center;">
                                <h3>{row['status']} {row['symbol']}</h3>
                                <h2>${row['total_pnl']:,.2f}</h2>
                                <p>Win Rate: {row['win_rate']:.1f}%</p>
                                <p>Trades: {row['total_trades']}</p>
                                <p>PF: {row['profit_factor']:.2f}</p>
                            </div>
                            """, unsafe_allow_html=True)
                
                st.markdown("---")
                
                # 전체 심볼 테이블
                st.markdown("### 📋 All Symbols Performance")
                
                # 표시용 데이터프레임
                display_df = symbol_analysis_df[[
                    'status', 'symbol', 'total_trades', 'win_rate', 
                    'total_pnl', 'avg_pnl', 'avg_pnl_percent', 'max_win', 'max_loss', 
                    'profit_factor', 'efficiency', 'total_volume'
                ]].copy()
                
                display_df.columns = [
                    '', 'Symbol', 'Trades', 'Win %', 'Total PnL', 
                    'Avg PnL', 'Avg %', 'Best', 'Worst', 'PF', 'Eff', 'Volume'
                ]
                
                # 포맷팅
                for col in ['Total PnL', 'Avg PnL', 'Best', 'Worst', 'Volume']:
                    display_df[col] = display_df[col].apply(lambda x: f"${x:,.2f}")
                display_df['Win %'] = display_df['Win %'].apply(lambda x: f"{x:.1f}%")
                display_df['Avg %'] = display_df['Avg %'].apply(lambda x: f"{x:.2f}%")
                display_df['PF'] = display_df['PF'].apply(lambda x: f"{x:.2f}")
                display_df['Eff'] = display_df['Eff'].apply(lambda x: f"{x:.2f}")
                
                st.dataframe(display_df, use_container_width=True, hide_index=True)
                
                # 차트들
                st.markdown("### 📈 Visual Analytics")
                col1, col2 = st.columns(2)
                
                with col1:
                    # Total PnL by Symbol
                    fig_pnl = go.Figure(data=[
                        go.Bar(
                            x=symbol_analysis_df['symbol'],
                            y=symbol_analysis_df['total_pnl'],
                            marker_color=symbol_analysis_df['total_pnl'].apply(
                                lambda x: '#2ca02c' if x > 0 else '#d62728'
                            ),
                            text=symbol_analysis_df['total_pnl'].apply(lambda x: f"${x:.2f}"),
                            textposition='outside'
                        )
                    ])
                    
                    fig_pnl.update_layout(
                        title="Total PnL by Symbol",
                        xaxis_title="Symbol",
                        yaxis_title="PnL (USDT)",
                        showlegend=False,
                        height=350
                    )
                    
                    st.plotly_chart(fig_pnl, use_container_width=True)
                
                with col2:
                    # Win Rate vs Profit Factor
                    fig_scatter = go.Figure(data=[
                        go.Scatter(
                            x=symbol_analysis_df['win_rate'],
                            y=symbol_analysis_df['profit_factor'],
                            mode='markers+text',
                            text=symbol_analysis_df['symbol'],
                            textposition="top center",
                            marker=dict(
                                size=symbol_analysis_df['total_trades'] * 2,
                                color=symbol_analysis_df['total_pnl'],
                                colorscale='RdYlGn',
                                showscale=True,
                                colorbar=dict(title="Total PnL")
                            )
                        )
                    ])
                    
                    fig_scatter.update_layout(
                        title="Win Rate vs Profit Factor",
                        xaxis_title="Win Rate (%)",
                        yaxis_title="Profit Factor",
                        height=350
                    )
                    
                    st.plotly_chart(fig_scatter, use_container_width=True)
                
                # 트레이드 분포 히트맵
                st.markdown("### 🗓️ Trading Activity Heatmap")
                
                # 시간대별/요일별 분석
                heatmap_query = f"""
                SELECT 
                    strftime('%H', close_timestamp) as hour,
                    strftime('%w', close_timestamp) as day_of_week,
                    COUNT(*) as trades,
                    SUM(pnl_usdt - COALESCE(commission, 0)) as total_pnl
                FROM completed_trades
                WHERE 1=1 {date_condition}
                GROUP BY hour, day_of_week
                """
                
                heatmap_df = pd.read_sql_query(heatmap_query, conn)
                
                if not heatmap_df.empty:
                    # 피벗 테이블 생성
                    pivot_trades = heatmap_df.pivot_table(
                        values='trades', 
                        index='hour', 
                        columns='day_of_week', 
                        fill_value=0
                    )
                    
                    pivot_pnl = heatmap_df.pivot_table(
                        values='total_pnl', 
                        index='hour', 
                        columns='day_of_week', 
                        fill_value=0
                    )
                    
                    # 요일 이름 매핑
                    day_names = {
                        '0': 'Sun', '1': 'Mon', '2': 'Tue', 
                        '3': 'Wed', '4': 'Thu', '5': 'Fri', '6': 'Sat'
                    }
                    pivot_trades.columns = [day_names.get(col, col) for col in pivot_trades.columns]
                    pivot_pnl.columns = [day_names.get(col, col) for col in pivot_pnl.columns]
                    
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        fig_heat_trades = go.Figure(data=go.Heatmap(
                            z=pivot_trades.values,
                            x=pivot_trades.columns,
                            y=pivot_trades.index,
                            colorscale='Blues',
                            text=pivot_trades.values,
                            texttemplate='%{text}',
                            textfont={"size": 10},
                            colorbar=dict(title="Trades")
                        ))
                        
                        fig_heat_trades.update_layout(
                            title="Trade Count by Hour/Day",
                            xaxis_title="Day of Week",
                            yaxis_title="Hour",
                            height=400
                        )
                        
                        st.plotly_chart(fig_heat_trades, use_container_width=True)
                    
                    with col2:
                        fig_heat_pnl = go.Figure(data=go.Heatmap(
                            z=pivot_pnl.values,
                            x=pivot_pnl.columns,
                            y=pivot_pnl.index,
                            colorscale='RdYlGn',
                            text=pivot_pnl.values.round(2),
                            texttemplate='$%{text}',
                            textfont={"size": 10},
                            colorbar=dict(title="PnL")
                        ))
                        
                        fig_heat_pnl.update_layout(
                            title="PnL by Hour/Day",
                            xaxis_title="Day of Week",
                            yaxis_title="Hour",
                            height=400
                        )
                        
                        st.plotly_chart(fig_heat_pnl, use_container_width=True)
                
                # 보유 시간 분석
                st.markdown("### ⏱️ Holding Time Analysis")
                
                holding_query = f"""
                SELECT 
                    symbol,
                    AVG(holding_time_minutes) as avg_holding,
                    AVG(CASE WHEN is_win = 1 THEN holding_time_minutes END) as avg_win_holding,
                    AVG(CASE WHEN is_win = 0 THEN holding_time_minutes END) as avg_loss_holding
                FROM completed_trades
                WHERE 1=1 {date_condition}
                GROUP BY symbol
                HAVING COUNT(*) >= 3
                """
                
                holding_df = pd.read_sql_query(holding_query, conn)
                
                if not holding_df.empty:
                    fig_holding = go.Figure()
                    
                    fig_holding.add_trace(go.Bar(
                        name='Win Trades',
                        x=holding_df['symbol'],
                        y=holding_df['avg_win_holding'] / 60,  # 시간으로 변환
                        marker_color='#2ca02c'
                    ))
                    
                    fig_holding.add_trace(go.Bar(
                        name='Loss Trades',
                        x=holding_df['symbol'],
                        y=holding_df['avg_loss_holding'] / 60,
                        marker_color='#d62728'
                    ))
                    
                    fig_holding.update_layout(
                        title="Average Holding Time by Symbol (Hours)",
                        xaxis_title="Symbol",
                        yaxis_title="Hours",
                        barmode='group',
                        height=350
                    )
                    
                    st.plotly_chart(fig_holding, use_container_width=True)
            
            else:
                st.info("분석할 거래 데이터가 없습니다.")
            
            conn.close()
            
        except Exception as e:
            st.error(f"심볼 분석 오류: {e}")
    
    # ==========================================
    # Tab 5: AI Monitoring (v7.4 신규)
    # ==========================================
    with tab5:
        st.header("🤖 AI Monitoring Status")
        
        # AI 모니터링 즉시 실행
        col_btn1, col_btn2, col_btn3 = st.columns([1, 1, 2])
        
        with col_btn1:
            if st.button("🚀 즉시 AI 모니터링 실행", type="primary"):
                try:
                    response = requests.post(f'{TRADING_BOT_URL}/ai-monitor/force', timeout=30)
                    
                    if response.status_code == 200:
                        result = response.json()
                        st.success(f"✅ AI 모니터링 완료: {result.get('positions_monitored', 0)}개 포지션 분석")
                        if result.get('exit_decisions'):
                            st.warning(f"⚠️ {len(result['exit_decisions'])}개 청산 결정 발생")
                            
                            # 청산 결정 상세 표시
                            for decision in result['exit_decisions']:
                                symbol = decision.get('symbol', 'N/A')
                                dec = decision.get('decision', {})
                                st.info(f"📊 {symbol}: {dec.get('decision', 'N/A')} - {dec.get('reason', 'N/A')}")
                        st.rerun()
                    else:
                        st.error(f"❌ 오류: {response.text}")
                        
                except requests.exceptions.ConnectionError:
                    st.error("❌ 봇 서버에 연결할 수 없습니다.")
                except Exception as e:
                    st.error(f"❌ 에러: {str(e)}")
        
        with col_btn2:
            if st.button("🔄 새로고침"):
                st.rerun()
        
        st.markdown("---")
        
        # AI 모니터링 현황
        col1, col2 = st.columns([2, 1])
        
        with col1:
            st.subheader("📊 최근 AI 모니터링 기록")
            
            try:
                conn = sqlite3.connect(DB_PATH)
                
                ai_query = """
                SELECT 
                    timestamp,
                    symbol,
                    action as ai_decision,
                    confidence,
                    reason,
                    current_price as price,
                    CASE 
                        WHEN trade_type = 'MANUAL_ENTRY' THEN '🔧 Manual'
                        WHEN reason LIKE '%Manual position%' THEN '🔧 Manual'
                        WHEN reason LIKE '%manual%' THEN '🔧 Manual'
                        ELSE '🤖 Auto'
                    END as position_type,
                    CASE 
                        WHEN action = 'close' THEN '🔴 Close'
                        WHEN action = 'partial_close' THEN '🟠 Partial'
                        WHEN action = 'hold' THEN '🟢 Hold'
                        ELSE action
                    END as decision_icon
                FROM trades
                WHERE trade_type IN ('AI_MONITOR', 'MANUAL_ENTRY')
                   OR (ai_decision IS NOT NULL AND ai_decision != '')
                ORDER BY timestamp DESC
                LIMIT 50
                """
                
                ai_df = pd.read_sql_query(ai_query, conn)
                
                if not ai_df.empty:
                    ai_df['timestamp'] = pd.to_datetime(ai_df['timestamp'])
                    ai_df['confidence'] = ai_df['confidence'] * 100
                    
                    latest_time = ai_df['timestamp'].max()
                    st.info(f"📊 최근 AI 모니터링: {latest_time.strftime('%Y-%m-%d %H:%M:%S')}")
                    
                    # 포맷팅
                    ai_df['timestamp'] = ai_df['timestamp'].dt.strftime('%Y-%m-%d %H:%M')
                    ai_df['confidence'] = ai_df['confidence'].apply(lambda x: f"{x:.1f}%")
                    ai_df['price'] = ai_df['price'].apply(lambda x: f"${x:,.2f}" if pd.notna(x) else "")
                    
                    # 컬럼 순서 조정
                    display_columns = ['timestamp', 'position_type', 'symbol', 'decision_icon', 
                                     'confidence', 'price', 'reason']
                    
                    st.dataframe(
                        ai_df[display_columns],
                        use_container_width=True,
                        hide_index=True
                    )
                else:
                    st.warning("⚠️ AI 모니터링 기록이 없습니다.")
                
                conn.close()
                
            except Exception as e:
                st.error(f"AI 모니터링 조회 오류: {e}")
        
        with col2:
            st.subheader("📈 AI 통계")
            
            try:
                conn = sqlite3.connect(DB_PATH)
                
                # AI 통계 조회
                stats_query = """
                SELECT 
                    COUNT(*) as total_monitors,
                    SUM(CASE WHEN action = 'close' THEN 1 ELSE 0 END) as close_decisions,
                    SUM(CASE WHEN action = 'hold' THEN 1 ELSE 0 END) as hold_decisions,
                    AVG(confidence) * 100 as avg_confidence
                FROM trades
                WHERE trade_type = 'AI_MONITOR'
                  AND timestamp >= datetime('now', '-24 hours')
                """
                
                stats = conn.execute(stats_query).fetchone()
                
                if stats and stats[0] > 0:
                    st.metric("📊 24h 모니터링", stats[0])
                    st.metric("🔴 청산 권고", stats[1] or 0)
                    st.metric("🟢 보유 권고", stats[2] or 0)
                    st.metric("🎯 평균 신뢰도", f"{stats[3]:.1f}%" if stats[3] else "N/A")
                else:
                    st.info("24시간 내 모니터링 기록 없음")
                
                conn.close()
                
            except Exception as e:
                st.error(f"통계 조회 오류: {e}")
        
        # AI 모니터링 설정 정보
        st.markdown("---")
        st.subheader("ℹ️ AI 모니터링 정보")
        
        info_col1, info_col2 = st.columns(2)
        
        with info_col1:
            st.info("""
            **AI 모니터링 기능:**
            - 5분마다 자동 실행
            - 모든 포지션 분석 (기존/신규)
            - 기술적 지표 기반 판단
            - 위험 관리 자동화
            """)
        
        with info_col2:
            st.warning("""
            **결정 타입:**
            - 🟢 Hold: 포지션 유지
            - 🟠 Partial: 부분 청산
            - 🔴 Close: 전체 청산
            - 긴급도에 따라 자동/수동 처리
            """)
    
    # ==========================================
    # Tab 6: AI Reflection (v7.4 Enhanced)
    # ==========================================
    with tab6:
        st.header("🧠 AI Reflection History")
        
        # Reflection 설명
        with st.expander("ℹ️ Reflection이란?", expanded=False):
            st.info("""
            📌 **AI Reflection System**
            - AI가 최근 거래 성과를 심층 분석하여 생성한 인사이트
            - 승률, 손익, 리스크 관리, 시장 조건을 종합적으로 평가
            - 향후 거래 신호 검증에 활용되는 중요한 피드백 루프
            - 거래 전략의 지속적인 개선을 위한 학습 메커니즘
            """)
        
        try:
            conn = sqlite3.connect(DB_PATH)
            
            # ==========================================
            # 🆕 v7.7: 종합 분석 섹션 (reflection_history 테이블)
            # ==========================================
            st.markdown("### 📊 종합 성과 분석 (AI Generated)")
            st.caption("AI가 완료된 거래들을 분석하여 생성한 종합적인 성과 평가입니다.")
            
            try:
                # reflection_history 테이블 존재 확인
                check_table = pd.read_sql_query(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='reflection_history'", 
                    conn
                )
                
                if not check_table.empty:
                    # 최근 종합 분석 조회
                    comprehensive_query = """
                    SELECT 
                        timestamp,
                        reflection_text,
                        total_trades,
                        win_rate,
                        recent_win_rate,
                        total_pnl,
                        risk_reward_ratio,
                        performance_trend,
                        symbols_analyzed
                    FROM reflection_history
                    ORDER BY timestamp DESC
                    LIMIT 10
                    """
                    comprehensive_df = pd.read_sql_query(comprehensive_query, conn)
                    
                    if not comprehensive_df.empty:
                        comprehensive_df['timestamp'] = pd.to_datetime(comprehensive_df['timestamp'])
                        
                        # 최신 종합 분석 통계
                        latest = comprehensive_df.iloc[0]
                        
                        col_comp1, col_comp2, col_comp3, col_comp4 = st.columns(4)
                        with col_comp1:
                            st.metric("📈 최근 승률", f"{latest['win_rate']:.1f}%")
                        with col_comp2:
                            st.metric("💰 총 PnL", f"${latest['total_pnl']:.2f}")
                        with col_comp3:
                            st.metric("⚖️ R:R Ratio", f"{latest['risk_reward_ratio']:.2f}")
                        with col_comp4:
                            trend_emoji = "📈" if latest['performance_trend'] == 'improving' else "📉" if latest['performance_trend'] == 'declining' else "➡️"
                            st.metric("📊 추세", f"{trend_emoji} {latest['performance_trend'].upper()}")
                        
                        # 종합 분석 카드들
                        st.markdown("---")
                        for idx, row in comprehensive_df.iterrows():
                            with st.expander(
                                f"📋 {row['timestamp'].strftime('%Y-%m-%d %H:%M')} | "
                                f"WR: {row['win_rate']:.1f}% | "
                                f"PnL: ${row['total_pnl']:.2f} | "
                                f"Symbols: {row['symbols_analyzed']}",
                                expanded=(idx == 0)  # 최신 것만 펼침
                            ):
                                # 성과 지표
                                st.markdown("**📊 Performance Metrics:**")
                                col_m1, col_m2, col_m3, col_m4 = st.columns(4)
                                with col_m1:
                                    st.markdown(f"**총 거래:** `{row['total_trades']}`")
                                with col_m2:
                                    st.markdown(f"**승률:** `{row['win_rate']:.1f}%`")
                                with col_m3:
                                    st.markdown(f"**최근 승률:** `{row['recent_win_rate']:.1f}%`")
                                with col_m4:
                                    st.markdown(f"**R:R:** `{row['risk_reward_ratio']:.2f}`")
                                
                                st.markdown("---")
                                st.markdown("**🧠 AI Analysis:**")
                                
                                # Reflection 텍스트 포맷팅
                                reflection_text = row['reflection_text']
                                sections = {
                                    'PERFORMANCE ASSESSMENT': '📊',
                                    'KEY STRENGTHS': '💪',
                                    'CRITICAL WEAKNESSES': '⚠️',
                                    'ACTIONABLE RECOMMENDATIONS': '🎯',
                                    'SIGNAL VALIDATION GUIDANCE': '✅',
                                }
                                
                                formatted_text = reflection_text
                                for section, emoji in sections.items():
                                    if section in formatted_text:
                                        formatted_text = formatted_text.replace(
                                            section, 
                                            f"\n\n**{emoji} {section}**"
                                        )
                                
                                st.markdown(
                                    f"<div style='background-color: rgba(76, 175, 80, 0.1); "
                                    f"border-left: 3px solid #4CAF50; "
                                    f"padding: 15px; border-radius: 5px; white-space: pre-wrap;'>"
                                    f"{formatted_text}"
                                    f"</div>",
                                    unsafe_allow_html=True
                                )
                                
                                st.caption(f"⏰ Generated: {row['timestamp'].strftime('%Y-%m-%d %H:%M:%S')}")
                    else:
                        st.info("📭 아직 생성된 종합 분석이 없습니다. 거래가 완료되면 자동으로 생성됩니다.")
                else:
                    # 🆕 v7.7: 테이블이 없으면 자동 생성
                    st.info("🔧 reflection_history 테이블을 생성 중...")
                    try:
                        cursor = conn.cursor()
                        cursor.execute('''CREATE TABLE IF NOT EXISTS reflection_history
                             (id INTEGER PRIMARY KEY AUTOINCREMENT,
                              timestamp TEXT NOT NULL,
                              reflection_text TEXT NOT NULL,
                              total_trades INTEGER,
                              win_rate REAL,
                              recent_win_rate REAL,
                              total_pnl REAL,
                              risk_reward_ratio REAL,
                              performance_trend TEXT,
                              symbols_analyzed TEXT)''')
                        conn.commit()
                        st.success("✅ reflection_history 테이블이 생성되었습니다! 페이지를 새로고침 해주세요.")
                    except Exception as create_err:
                        st.error(f"❌ 테이블 생성 실패: {create_err}")
            except Exception as comp_err:
                st.warning(f"종합 분석 조회 실패: {comp_err}")
            
            st.markdown("---")
            st.markdown("### 📝 거래별 신호 분석 (Rule-Based)")
            st.caption("각 거래 신호에 대한 Rule-Based 검증 결과입니다.")
            
            # 필터 옵션
            col_filter1, col_filter2, col_filter3 = st.columns([1, 1, 1])
            
            with col_filter1:
                # 심볼 필터
                symbol_query = "SELECT DISTINCT symbol FROM trades WHERE reflection IS NOT NULL AND reflection != '' ORDER BY symbol"
                symbols_df = pd.read_sql_query(symbol_query, conn)
                
                if not symbols_df.empty:
                    all_symbols = ['전체'] + symbols_df['symbol'].tolist()
                    selected_symbol = st.selectbox("🎯 심볼 선택", all_symbols, key="refl_symbol")
                else:
                    selected_symbol = '전체'
            
            with col_filter2:
                # 기간 필터
                period_options = {
                    '최근 24시간': 1,
                    '최근 3일': 3,
                    '최근 7일': 7,
                    '최근 30일': 30,
                    '최근 90일': 90,
                    '전체': 999999
                }
                selected_period = st.selectbox("📅 조회 기간", list(period_options.keys()), index=2, key="refl_period")
                days = period_options[selected_period]
            
            with col_filter3:
                # 결정 필터
                decision_filter = st.selectbox(
                    "🎭 결정 필터",
                    ['전체', 'Approve', 'Reject', 'Modify'],
                    key="refl_decision"
                )
            
            # Reflection 조회 쿼리
            base_query = """
            SELECT 
                timestamp,
                symbol,
                action,
                ai_decision,
                confidence,
                reflection,
                percentage,
                reason,
                trade_type,
                current_price,
                entry_price
            FROM trades
            WHERE reflection IS NOT NULL
                AND reflection != ''
                AND timestamp >= datetime('now', '-{days} days')
            """
            
            if selected_symbol != '전체':
                base_query += f" AND symbol = '{selected_symbol}'"
            
            if decision_filter != '전체':
                base_query += f" AND ai_decision = '{decision_filter.lower()}'"
            
            base_query += " ORDER BY timestamp DESC LIMIT 100"
            
            reflection_query = base_query.format(days=days)
            reflection_df = pd.read_sql_query(reflection_query, conn)
            
            if not reflection_df.empty:
                reflection_df['timestamp'] = pd.to_datetime(reflection_df['timestamp'])
                
                # ==========================================
                # 통계 대시보드
                # ==========================================
                st.markdown("### 📊 Reflection Analytics Dashboard")
                
                # 메인 메트릭
                col_stat1, col_stat2, col_stat3, col_stat4, col_stat5 = st.columns(5)
                
                with col_stat1:
                    st.metric("📝 총 Reflection", len(reflection_df))
                
                with col_stat2:
                    approved = len(reflection_df[reflection_df['ai_decision'] == 'approve'])
                    approve_rate = (approved / len(reflection_df) * 100) if len(reflection_df) > 0 else 0
                    st.metric("✅ Approved", approved, f"{approve_rate:.1f}%")
                
                with col_stat3:
                    rejected = len(reflection_df[reflection_df['ai_decision'] == 'reject'])
                    reject_rate = (rejected / len(reflection_df) * 100) if len(reflection_df) > 0 else 0
                    st.metric("❌ Rejected", rejected, f"{reject_rate:.1f}%")
                
                with col_stat4:
                    modified = len(reflection_df[reflection_df['ai_decision'] == 'modify'])
                    st.metric("🔄 Modified", modified)
                
                with col_stat5:
                    avg_confidence = reflection_df['confidence'].mean() * 100
                    st.metric("🎯 평균 신뢰도", f"{avg_confidence:.1f}%")
                
                # ==========================================
                # 시각화
                # ==========================================
                st.markdown("---")
                st.markdown("### 📈 Reflection Insights")
                
                col_chart1, col_chart2 = st.columns(2)
                
                with col_chart1:
                    # 시간별 결정 분포
                    time_grouped = reflection_df.groupby([
                        reflection_df['timestamp'].dt.date,
                        'ai_decision'
                    ]).size().reset_index(name='count')
                    
                    if not time_grouped.empty:
                        fig_timeline = go.Figure()
                        
                        for decision in reflection_df['ai_decision'].unique():
                            decision_data = time_grouped[time_grouped['ai_decision'] == decision]
                            color = '#2ca02c' if decision == 'approve' else '#d62728' if decision == 'reject' else '#ff7f0e'
                            
                            fig_timeline.add_trace(go.Scatter(
                                x=decision_data['timestamp'],
                                y=decision_data['count'],
                                mode='lines+markers',
                                name=decision.capitalize(),
                                line=dict(color=color, width=2),
                                marker=dict(size=8)
                            ))
                        
                        fig_timeline.update_layout(
                            title="AI Decision Timeline",
                            xaxis_title="Date",
                            yaxis_title="Count",
                            height=350,
                            hovermode='x unified'
                        )
                        
                        st.plotly_chart(fig_timeline, use_container_width=True)
                    else:
                        st.info("시간별 데이터가 충분하지 않습니다.")
                
                with col_chart2:
                    # 심볼별 신뢰도 분포
                    symbol_confidence = reflection_df.groupby('symbol').agg({
                        'confidence': 'mean',
                        'ai_decision': 'count'
                    }).reset_index()
                    symbol_confidence.columns = ['symbol', 'avg_confidence', 'count']
                    symbol_confidence['avg_confidence'] *= 100
                    
                    if not symbol_confidence.empty:
                        fig_confidence = go.Figure(data=[
                            go.Bar(
                                x=symbol_confidence['symbol'],
                                y=symbol_confidence['avg_confidence'],
                                text=symbol_confidence['avg_confidence'].apply(lambda x: f"{x:.1f}%"),
                                textposition='outside',
                                marker_color=symbol_confidence['avg_confidence'].apply(
                                    lambda x: '#2ca02c' if x >= 70 else '#ff7f0e' if x >= 50 else '#d62728'
                                )
                            )
                        ])
                        
                        fig_confidence.update_layout(
                            title="Average Confidence by Symbol",
                            xaxis_title="Symbol",
                            yaxis_title="Confidence (%)",
                            height=350,
                            showlegend=False
                        )
                        
                        st.plotly_chart(fig_confidence, use_container_width=True)
                    else:
                        st.info("심볼별 데이터가 충분하지 않습니다.")
                
                # ==========================================
                # Reflection 카드 (개선된 버전)
                # ==========================================
                st.markdown("---")
                st.markdown("### 📋 Reflection Details")
                
                # 정렬 옵션
                col_sort1, col_sort2, col_sort3 = st.columns([1, 1, 2])
                with col_sort1:
                    sort_by = st.selectbox(
                        "정렬 기준",
                        ['최신순', '신뢰도 높은순', '신뢰도 낮은순'],
                        key="refl_sort"
                    )
                
                # 정렬 적용
                if sort_by == '신뢰도 높은순':
                    reflection_df = reflection_df.sort_values('confidence', ascending=False)
                elif sort_by == '신뢰도 낮은순':
                    reflection_df = reflection_df.sort_values('confidence', ascending=True)
                else:
                    reflection_df = reflection_df.sort_values('timestamp', ascending=False)
                
                # 페이지네이션
                items_per_page = 10
                total_items = len(reflection_df)
                total_pages = (total_items - 1) // items_per_page + 1 if total_items > 0 else 1
                
                with col_sort2:
                    current_page = st.number_input(
                        "페이지",
                        min_value=1,
                        max_value=total_pages,
                        value=1,
                        key="refl_page"
                    )
                
                with col_sort3:
                    st.info(f"총 {total_items}개 중 {(current_page-1)*items_per_page+1}-{min(current_page*items_per_page, total_items)}번째")
                
                # 현재 페이지 데이터
                start_idx = (current_page - 1) * items_per_page
                end_idx = start_idx + items_per_page
                page_df = reflection_df.iloc[start_idx:end_idx]
                
                # Reflection 카드 표시
                for idx, row in page_df.iterrows():
                    # 결정에 따른 색상과 아이콘
                    if row['ai_decision'] == 'approve':
                        decision_icon = "✅"
                        card_color = "rgba(40, 167, 69, 0.1)"
                        border_color = "#28a745"
                    elif row['ai_decision'] == 'reject':
                        decision_icon = "❌"
                        card_color = "rgba(220, 53, 69, 0.1)"
                        border_color = "#dc3545"
                    elif row['ai_decision'] == 'modify':
                        decision_icon = "🔄"
                        card_color = "rgba(255, 193, 7, 0.1)"
                        border_color = "#ffc107"
                    else:
                        decision_icon = "❓"
                        card_color = "rgba(108, 117, 125, 0.1)"
                        border_color = "#6c757d"
                    
                    with st.expander(
                        f"{decision_icon} {row['timestamp'].strftime('%Y-%m-%d %H:%M')} | "
                        f"{row['symbol']} | {row['action'].upper() if pd.notna(row['action']) else 'N/A'} | "
                        f"Confidence: {row['confidence']*100:.1f}%",
                        expanded=False
                    ):
                        # 상세 정보
                        col_info1, col_info2, col_info3, col_info4 = st.columns(4)
                        
                        with col_info1:
                            st.markdown(f"**심볼:** `{row['symbol']}`")
                            if pd.notna(row['trade_type']):
                                st.markdown(f"**타입:** `{row['trade_type']}`")
                        
                        with col_info2:
                            if pd.notna(row['action']):
                                st.markdown(f"**액션:** `{row['action'].upper()}`")
                            if pd.notna(row['percentage']):
                                st.markdown(f"**비율:** `{row['percentage']}%`")
                        
                        with col_info3:
                            st.markdown(f"**결정:** `{row['ai_decision'].upper()}`")
                            st.markdown(f"**신뢰도:** `{row['confidence']*100:.1f}%`")
                        
                        with col_info4:
                            if pd.notna(row['entry_price']):
                                st.markdown(f"**진입가:** `${row['entry_price']:,.2f}`")
                            if pd.notna(row['current_price']):
                                st.markdown(f"**현재가:** `${row['current_price']:,.2f}`")
                        
                        # Reason 표시
                        if pd.notna(row['reason']):
                            st.markdown("---")
                            st.markdown("**📌 Decision Reason:**")
                            st.info(row['reason'])
                        
                        # Reflection 내용 (포맷팅 개선)
                        st.markdown("---")
                        st.markdown("**🧠 AI Reflection:**")
                        
                        reflection_text = row['reflection']
                        
                        # 섹션별로 하이라이팅 (더 많은 섹션 추가)
                        sections = {
                            'PERFORMANCE ASSESSMENT': '📊',
                            'KEY STRENGTHS': '💪',
                            'CRITICAL WEAKNESSES': '⚠️',
                            'ACTIONABLE RECOMMENDATIONS': '🎯',
                            'SIGNAL VALIDATION GUIDANCE': '✅',
                            'MARKET CONTEXT': '🌍',
                            'RISK ASSESSMENT': '⚡',
                            'POSITION MANAGEMENT': '📈',
                            'TECHNICAL ANALYSIS': '📉',
                            'STRATEGY ADJUSTMENT': '🔧'
                        }
                        
                        formatted_reflection = reflection_text
                        for section, emoji in sections.items():
                            if section in formatted_reflection:
                                formatted_reflection = formatted_reflection.replace(
                                    section, 
                                    f"\n\n**{emoji} {section}**"
                                )
                        
                        # 코드 블록으로 표시 (더 나은 가독성)
                        st.markdown(
                            f"<div style='background-color: {card_color}; "
                            f"border-left: 3px solid {border_color}; "
                            f"padding: 15px; border-radius: 5px;'>"
                            f"{formatted_reflection}"
                            f"</div>",
                            unsafe_allow_html=True
                        )
                        
                        st.caption(f"⏰ Generated: {row['timestamp'].strftime('%Y-%m-%d %H:%M:%S')}")
                
                # ==========================================
                # 워드 클라우드 분석 (신규)
                # ==========================================
                if len(reflection_df) >= 5:  # 최소 5개 이상일 때만 표시
                    st.markdown("---")
                    st.markdown("### 🔍 Reflection Keywords Analysis")
                    
                    # 전체 reflection 텍스트 결합
                    all_reflections = ' '.join(reflection_df['reflection'].dropna())
                    all_reasons = ' '.join(reflection_df['reason'].dropna())
                    
                    # 주요 키워드 추출 (간단한 빈도 분석)
                    import re
                    from collections import Counter
                    
                    # 키워드 추출 함수
                    def extract_keywords(text):
                        # 불용어 제거
                        stopwords = {'the', 'is', 'at', 'which', 'on', 'and', 'a', 'an', 'as', 
                                    'are', 'was', 'were', 'be', 'have', 'has', 'had', 'do', 
                                    'does', 'did', 'will', 'would', 'could', 'should', 'may',
                                    'might', 'must', 'can', 'this', 'that', 'these', 'those',
                                    'with', 'for', 'to', 'from', 'of', 'in', 'by', 'but'}
                        
                        words = re.findall(r'\b[a-z]+\b', text.lower())
                        words = [w for w in words if len(w) > 3 and w not in stopwords]
                        return Counter(words)
                    
                    keyword_counter = extract_keywords(all_reflections + ' ' + all_reasons)
                    top_keywords = keyword_counter.most_common(20)
                    
                    if top_keywords:
                        col_kw1, col_kw2 = st.columns(2)
                        
                        with col_kw1:
                            st.markdown("**📌 Top Keywords:**")
                            keywords_df = pd.DataFrame(top_keywords[:10], columns=['Keyword', 'Frequency'])
                            st.dataframe(keywords_df, use_container_width=True, hide_index=True)
                        
                        with col_kw2:
                            # 간단한 바 차트
                            fig_keywords = go.Figure(data=[
                                go.Bar(
                                    x=[k[1] for k in top_keywords[:10]],
                                    y=[k[0] for k in top_keywords[:10]],
                                    orientation='h',
                                    marker_color='#667eea'
                                )
                            ])
                            
                            fig_keywords.update_layout(
                                title="Keyword Frequency",
                                xaxis_title="Count",
                                yaxis_title="Keyword",
                                height=300,
                                showlegend=False
                            )
                            
                            st.plotly_chart(fig_keywords, use_container_width=True)
                
                # ==========================================
                # 최신 Reflection 하이라이트 (개선)
                # ==========================================
                if len(reflection_df) > 0:
                    st.markdown("---")
                    st.markdown("### ⭐ Latest Reflection Highlight")
                    
                    latest = reflection_df.iloc[0]
                    
                    # 결정에 따른 메시지 박스 색상
                    if latest['ai_decision'] == 'approve':
                        msg_type = st.success
                    elif latest['ai_decision'] == 'reject':
                        msg_type = st.error
                    else:
                        msg_type = st.warning
                    
                    msg_type(f"""
                    **🕐 Time:** {latest['timestamp'].strftime('%Y-%m-%d %H:%M:%S')}
                    
                    **📊 Symbol:** {latest['symbol']} | **Action:** {latest['action'].upper() if pd.notna(latest['action']) else 'N/A'}
                    
                    **🎯 AI Decision:** {latest['ai_decision'].upper()} (Confidence: {latest['confidence']*100:.1f}%)
                    
                    **📝 Reason:** {latest['reason'] if pd.notna(latest['reason']) else 'No specific reason provided'}
                    """)
                    
                    # Reflection 내용을 접을 수 있는 형태로
                    with st.expander("📖 View Full Reflection", expanded=True):
                        st.text_area(
                            "Latest Analysis",
                            latest['reflection'],
                            height=400,
                            disabled=True,
                            label_visibility="collapsed"
                        )
            
            else:
                st.warning("⚠️ 선택한 기간에 Reflection 기록이 없습니다.")
                st.info("""
                💡 **Reflection이 생성되는 경우:**
                - 거래 신호 발생시 AI가 자동으로 분석
                - 포지션 종료 후 성과 평가
                - 주기적인 전략 리뷰
                """)
                
                # 빈 상태일 때 도움말
                with st.expander("🔍 Reflection이 없다면?"):
                    st.markdown("""
                    **가능한 원인:**
                    1. 최근에 거래 활동이 없었을 수 있습니다
                    2. AI 검증이 비활성화되어 있을 수 있습니다
                    3. 데이터베이스가 초기화되었을 수 있습니다
                    
                    **해결 방법:**
                    - 거래 봇이 정상 작동중인지 확인하세요
                    - AI 검증이 활성화되어 있는지 확인하세요
                    - 더 긴 기간으로 조회해보세요
                    """)
            
            conn.close()
            
        except Exception as e:
            st.error(f"Reflection 조회 오류: {e}")
            import traceback
            st.text(traceback.format_exc())
    
    # ==========================================
    # Tab 7: Position Control (레버리지 / 진입 비중 조절)
    # ==========================================
    with tab7:
        st.header("⚙️ Position Control")
        st.caption("심볼별 또는 통합으로 레버리지와 진입 비중(자본 대비 %)을 조절합니다. 변경 즉시 봇에 반영되며, 레버리지는 거래소에도 적용됩니다.")

        # 봇에서 현재 설정 로드
        bot_config = {}
        bot_online = False
        try:
            cfg_resp = requests.get(f"{TRADING_BOT_URL}/config", timeout=4)
            if cfg_resp.status_code == 200:
                bot_config = cfg_resp.json()
                bot_online = True
        except Exception:
            bot_online = False

        if not bot_online:
            st.error("🔴 봇이 오프라인이거나 /config 응답이 없습니다. 봇 실행 상태를 확인하세요.")
        elif not bot_config:
            st.warning("심볼 설정이 비어 있습니다.")
        else:
            enabled_symbols = [s for s, c in bot_config.items() if c.get('enabled', False)]
            st.success(f"🟢 봇 연결됨 · 전체 {len(bot_config)}개 심볼 (거래 활성 {len(enabled_symbols)}개)")

            # ---------- (A) 통합 일괄 조절 ----------
            st.markdown("---")
            st.subheader("🌐 통합 일괄 조절")
            st.caption("모든 심볼에 동일한 값을 한 번에 적용합니다.")

            col_bulk1, col_bulk2, col_bulk3 = st.columns([1, 1, 1])
            with col_bulk1:
                bulk_scope = st.radio(
                    "적용 대상",
                    ["거래 활성 심볼만", "전체 심볼"],
                    key="bulk_scope",
                    help="거래 활성 심볼만: enabled=True인 심볼에만 적용"
                )
            with col_bulk2:
                bulk_leverage = st.slider("레버리지 (배)", min_value=1, max_value=50, value=5, step=1, key="bulk_leverage")
            with col_bulk3:
                bulk_position = st.slider("진입 비중 (%)", min_value=1, max_value=100, value=40, step=1, key="bulk_position",
                                          help="자본 대비 1회 진입에 사용할 비율")

            col_bulk_apply1, col_bulk_apply2 = st.columns(2)
            with col_bulk_apply1:
                apply_lev = st.checkbox("레버리지 적용", value=True, key="bulk_apply_lev")
            with col_bulk_apply2:
                apply_pos = st.checkbox("진입 비중 적용", value=True, key="bulk_apply_pos")

            if st.button("🚀 통합 적용", key="bulk_apply_btn", use_container_width=True, type="primary"):
                if not apply_lev and not apply_pos:
                    st.warning("적용할 항목을 최소 하나 선택하세요.")
                else:
                    target_symbols = enabled_symbols if bulk_scope == "거래 활성 심볼만" else list(bot_config.keys())
                    payload = {}
                    for sym in target_symbols:
                        s_settings = {}
                        if apply_lev:
                            s_settings['leverage'] = int(bulk_leverage)
                        if apply_pos:
                            s_settings['position_size_percent'] = int(bulk_position)
                        if s_settings:
                            payload[sym] = s_settings
                    try:
                        resp = requests.post(f"{TRADING_BOT_URL}/config", json=payload, timeout=15)
                        if resp.status_code == 200:
                            data = resp.json()
                            st.success(f"✅ {len(payload)}개 심볼에 적용 완료!")
                            lev_applied = data.get('leverage_applied', {})
                            failed = [s for s, v in lev_applied.items() if v is None]
                            if failed:
                                st.warning(f"⚠️ 레버리지 거래소 반영 실패: {', '.join(failed[:10])}{' 외' if len(failed) > 10 else ''}")
                            time_module.sleep(1)
                            st.rerun()
                        else:
                            st.error(f"❌ 적용 실패 (HTTP {resp.status_code}): {resp.text[:200]}")
                    except Exception as e:
                        st.error(f"❌ 적용 오류: {e}")

            # ---------- (B) 심볼별 개별 조절 ----------
            st.markdown("---")
            st.subheader("🎯 심볼별 개별 조절")

            only_enabled = st.checkbox("거래 활성 심볼만 표시", value=True, key="indiv_only_enabled")
            display_symbols = enabled_symbols if only_enabled else list(bot_config.keys())

            search_q = st.text_input("🔍 심볼 검색", value="", key="indiv_search", placeholder="예: BTC").upper().strip()
            if search_q:
                display_symbols = [s for s in display_symbols if search_q in s.upper()]

            if not display_symbols:
                st.info("표시할 심볼이 없습니다.")
            else:
                st.caption(f"{len(display_symbols)}개 심볼 · 각 행에서 값을 조절하고 '저장'을 누르세요.")

                # 헤더
                h1, h2, h3, h4 = st.columns([2, 2, 2, 1])
                h1.markdown("**심볼**")
                h2.markdown("**레버리지 (배)**")
                h3.markdown("**진입 비중 (%)**")
                h4.markdown("**저장**")

                for sym in display_symbols:
                    cfg = bot_config.get(sym, {})
                    cur_lev = int(cfg.get('leverage', 5))
                    cur_pos = int(cfg.get('position_size_percent', 40))
                    is_enabled = cfg.get('enabled', False)

                    c1, c2, c3, c4 = st.columns([2, 2, 2, 1])
                    with c1:
                        badge = "🟢" if is_enabled else "⚪"
                        st.markdown(f"{badge} `{sym}`")
                    with c2:
                        new_lev = st.number_input(
                            "lev", min_value=1, max_value=50, value=cur_lev, step=1,
                            key=f"lev_{sym}", label_visibility="collapsed"
                        )
                    with c3:
                        new_pos = st.number_input(
                            "pos", min_value=1, max_value=100, value=cur_pos, step=1,
                            key=f"pos_{sym}", label_visibility="collapsed"
                        )
                    with c4:
                        if st.button("💾", key=f"save_{sym}", use_container_width=True,
                                     help=f"{sym} 설정 저장"):
                            payload = {sym: {'leverage': int(new_lev), 'position_size_percent': int(new_pos)}}
                            try:
                                resp = requests.post(f"{TRADING_BOT_URL}/config", json=payload, timeout=10)
                                if resp.status_code == 200:
                                    data = resp.json()
                                    lev_ok = data.get('leverage_applied', {}).get(sym, None)
                                    if lev_ok is None:
                                        st.warning(f"⚠️ {sym} 저장됨 (레버리지 거래소 반영은 실패 — 포지션 보유 중일 수 있음)")
                                    else:
                                        st.success(f"✅ {sym} 저장 완료 (레버리지 {lev_ok}x)")
                                    time_module.sleep(1)
                                    st.rerun()
                                else:
                                    st.error(f"❌ 실패 (HTTP {resp.status_code})")
                            except Exception as e:
                                st.error(f"❌ 오류: {e}")

            st.markdown("---")
            st.info(
                "ℹ️ **참고**\n"
                "- 레버리지 변경은 **해당 심볼에 포지션이 없을 때** 거래소에 정상 반영됩니다. "
                "포지션 보유 중에는 봇 설정값만 갱신되고 다음 진입부터 적용됩니다.\n"
                "- 진입 비중은 다음 신호부터 적용되며, 이미 열린 포지션에는 영향을 주지 않습니다.\n"
                "- 변경 값은 봇 메모리에 저장됩니다. 봇 재시작 시 코드의 기본값으로 돌아가니, 영구 적용은 `SYMBOL_CONFIG`도 함께 수정하세요."
            )

    # 사이드바 - 설정 및 정보
    with st.sidebar:
        st.header("⚙️ Dashboard Settings")
        
        # 자동 새로고침
        auto_refresh = st.checkbox("🔄 자동 새로고침 (3초)", value=False)
        if auto_refresh:
            time_module.sleep(3)
            st.rerun()
        
        # 새로고침 버튼
        if st.button("🔄 수동 새로고침", use_container_width=True):
            st.rerun()
        
        st.markdown("---")
        
        # 시스템 상태
        st.header("📊 System Status")
        
        # 현재 시간
        st.info(f"🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        # 봇 상태 확인 (🆕 v8.0: /health 우선 — 내부 상태와 무관하게 생존 판정)
        bot_online = False
        try:
            hresp = requests.get(f"{TRADING_BOT_URL}/health", timeout=3)
            if hresp.status_code == 200:
                hdata = hresp.json()
                bot_online = True
                if hdata.get('degraded'):
                    st.warning("🟡 Trading Bot: Online (초기화 일부 실패)")
                    st.error(f"초기화 오류: {hdata.get('startup_error')}")
                    st.caption("서버의 bot.log 파일에서 전체 스택트레이스를 확인하세요.")
                else:
                    st.success(f"🤖 Trading Bot: Online  ·  {hdata.get('version', '')}")
                st.caption(f"봇 서버 시각: {hdata.get('server_time', '-')}")
            else:
                st.warning(f"🤖 Trading Bot: Error (HTTP {hresp.status_code})")
        except requests.exceptions.ConnectionError:
            st.error("🤖 Trading Bot: Offline — 연결할 수 없습니다")
            with st.expander("🔍 문제 해결 가이드", expanded=True):
                st.markdown(f"""
**확인 순서**

1. **봇 프로세스 생존 확인**
   ```
   ps aux | grep integrated_trading_system
   ```
2. **시작 로그에서 원인 확인** (v8.0은 `bot.log`에 기록)
   ```
   tail -100 bot.log
   ```
3. **포트 점유 확인** — 이전 프로세스가 남아 있으면 새 프로세스가 바인딩 실패
   ```
   lsof -i :5000
   kill -9 <PID>   # 남아있는 구 프로세스 종료 후 재실행
   ```
4. **직접 호출 테스트**
   ```
   curl {TRADING_BOT_URL}/health
   ```
5. **주소 확인** — 현재 대시보드가 보는 주소: `{TRADING_BOT_URL}`
   봇이 다른 호스트/포트면 `TRADING_BOT_URL`을 수정하세요.

> v8.0부터는 초기화가 실패해도 서버는 기동되어 `/health`가 응답합니다.
> 그래도 Offline이면 **프로세스가 아예 뜨지 않은 것**이므로 `bot.log` 마지막 줄을 확인하세요.
                """)
        except Exception as e:
            st.error(f"🤖 Trading Bot: Offline — {type(e).__name__}: {e}")

        # 상세 상태(/status)는 온라인일 때만 조회
        if bot_online:
            try:
                sresp = requests.get(f"{TRADING_BOT_URL}/status", timeout=4)
                if sresp.status_code == 200:
                    sdata = sresp.json()
                    rg = sdata.get('repaint_guard', {})
                    if rg:
                        rc1, rc2, rc3 = st.columns(3)
                        with rc1:
                            st.metric("🛡️ 리페인팅 방어", "ON" if rg.get('enabled') else "OFF")
                        with rc2:
                            st.metric("차단 중", f"{rg.get('blocked_now', 0)}개")
                        with rc3:
                            st.metric("누적 감지", f"{rg.get('anomaly_count', 0)}건")
                else:
                    st.caption(f"⚠️ /status 응답 이상 (HTTP {sresp.status_code}) — 봇은 살아있음")
            except Exception as e:
                st.caption(f"⚠️ /status 조회 실패: {e} (봇은 살아있음)")
        
        st.markdown("---")
        
        # ============ 🆕 텔레그램 테스트 ============
        st.header("📨 Telegram")
        
        if bot_online:
            if st.button("📨 텔레그램 테스트 메시지 전송", use_container_width=True):
                try:
                    resp = requests.post(f"{TRADING_BOT_URL}/test-telegram", timeout=5)
                    if resp.status_code == 200:
                        st.success("✅ 텔레그램 테스트 메시지 전송 완료!")
                    else:
                        error_msg = resp.json().get('error', 'Unknown error')
                        st.error(f"❌ 전송 실패: {error_msg}")
                except Exception as e:
                    st.error(f"❌ 요청 실패: {e}")
        else:
            st.warning("봇이 오프라인입니다")
        
        st.markdown("---")
        
        # ============ 🆕 AI 모니터링 ON/OFF ============
        st.header("🤖 AI Monitoring")
        
        if bot_online:
            # 현재 AI 모니터링 상태 조회
            ai_status = None
            try:
                resp = requests.get(f"{TRADING_BOT_URL}/ai-monitor/status", timeout=3)
                if resp.status_code == 200:
                    ai_status = resp.json()
            except:
                pass
            
            if ai_status:
                is_active = ai_status.get('monitoring_active', False)
                monitored_count = ai_status.get('total_positions', 0)
                interval = ai_status.get('interval_minutes', 5)
                
                if is_active:
                    st.success(f"🟢 AI 모니터링 활성 ({interval}분 간격)")
                    st.caption(f"모니터링 중인 포지션: {monitored_count}개")
                else:
                    st.warning("🔴 AI 모니터링 비활성")
                
                # ON/OFF 토글 버튼
                col_on, col_off = st.columns(2)
                
                with col_on:
                    if st.button("▶️ ON", use_container_width=True, disabled=is_active):
                        try:
                            resp = requests.post(f"{TRADING_BOT_URL}/ai-monitor/start", timeout=5)
                            if resp.status_code == 200:
                                st.success("✅ AI 모니터링 시작!")
                                time_module.sleep(1)
                                st.rerun()
                        except Exception as e:
                            st.error(f"❌ 시작 실패: {e}")
                
                with col_off:
                    if st.button("⏹️ OFF", use_container_width=True, disabled=not is_active):
                        try:
                            resp = requests.post(f"{TRADING_BOT_URL}/ai-monitor/stop", timeout=5)
                            if resp.status_code == 200:
                                st.warning("⏹️ AI 모니터링 중지됨")
                                time_module.sleep(1)
                                st.rerun()
                        except Exception as e:
                            st.error(f"❌ 중지 실패: {e}")
                
                # 강제 실행 버튼
                if st.button("⚡ 즉시 모니터링 실행", use_container_width=True):
                    try:
                        with st.spinner("AI 모니터링 실행 중..."):
                            resp = requests.post(f"{TRADING_BOT_URL}/ai-monitor/force", timeout=60)
                        if resp.status_code == 200:
                            result = resp.json()
                            monitored = result.get('positions_monitored', 0)
                            exits = result.get('exit_decisions', 0)
                            st.success(f"✅ 완료! 모니터링: {monitored}개, Exit 결정: {exits}개")
                        else:
                            st.info(resp.json().get('message', 'No positions'))
                    except Exception as e:
                        st.error(f"❌ 실행 실패: {e}")
            else:
                st.error("AI 모니터링 상태를 가져올 수 없습니다")
        else:
            st.warning("봇이 오프라인입니다")
        
        st.markdown("---")
        
        # ============ 🆕 AI Validation ON/OFF ============
        st.header("🧠 AI Validation")
        
        if bot_online:
            av_status = None
            try:
                resp = requests.get(f"{TRADING_BOT_URL}/ai-validation/status", timeout=3)
                if resp.status_code == 200:
                    av_status = resp.json()
            except:
                pass
            
            if av_status:
                total = av_status.get('total_symbols', 0)
                enabled = av_status.get('ai_validation_enabled', 0)
                all_enabled = av_status.get('all_enabled', False)
                all_disabled = av_status.get('all_disabled', False)
                
                if all_enabled:
                    st.success(f"🟢 AI 검증 활성 ({enabled}/{total})")
                elif all_disabled:
                    st.error(f"🔴 AI 검증 비활성 (전체 {total}개)")
                else:
                    st.warning(f"🟡 혼합 ({enabled}/{total} 활성)")
                
                st.caption("ON: 진입 신호를 AI가 검증/거부/수정")
                st.caption("OFF: 웹훅 신호가 바로 거래 실행")
                
                col_av_on, col_av_off = st.columns(2)
                with col_av_on:
                    if st.button("🧠 ON", key="av_on", use_container_width=True, disabled=all_enabled):
                        try:
                            resp = requests.post(f"{TRADING_BOT_URL}/ai-validation/toggle", json={'enabled': True}, timeout=5)
                            if resp.status_code == 200:
                                st.success("✅ AI 검증 활성화!")
                                time_module.sleep(1)
                                st.rerun()
                        except Exception as e:
                            st.error(f"❌ 실패: {e}")
                with col_av_off:
                    if st.button("⛔ OFF", key="av_off", use_container_width=True, disabled=all_disabled):
                        try:
                            resp = requests.post(f"{TRADING_BOT_URL}/ai-validation/toggle", json={'enabled': False}, timeout=5)
                            if resp.status_code == 200:
                                st.warning("⛔ AI 검증 비활성화!")
                                time_module.sleep(1)
                                st.rerun()
                        except Exception as e:
                            st.error(f"❌ 실패: {e}")
            else:
                st.error("상태를 가져올 수 없습니다")
        else:
            st.warning("봇이 오프라인입니다")
        
        st.markdown("---")
        
        # ============ 🆕 TP/SL 자동생성 ON/OFF ============
        st.header("🎯 TP/SL 자동생성")
        
        if bot_online:
            tpsl_status = None
            try:
                resp = requests.get(f"{TRADING_BOT_URL}/auto-tp-sl/status", timeout=3)
                if resp.status_code == 200:
                    tpsl_status = resp.json()
            except:
                pass
            
            if tpsl_status is not None:
                tpsl_enabled = tpsl_status.get('auto_tp_sl_enabled', True)
                
                if tpsl_enabled:
                    st.success("🟢 TP/SL 자동생성 ON")
                    st.caption("웹훅 TP/SL이 null이면 봇이 자동 생성")
                else:
                    st.warning("📡 TP/SL 자동생성 OFF")
                    st.caption("TradingView close_position 신호에 의존")
                
                col_tp_on, col_tp_off = st.columns(2)
                with col_tp_on:
                    if st.button("🎯 ON", key="tpsl_on", use_container_width=True, disabled=tpsl_enabled):
                        try:
                            resp = requests.post(f"{TRADING_BOT_URL}/auto-tp-sl/toggle", json={'enabled': True}, timeout=5)
                            if resp.status_code == 200:
                                st.success("✅ TP/SL 자동생성 ON!")
                                time_module.sleep(1)
                                st.rerun()
                        except Exception as e:
                            st.error(f"❌ 실패: {e}")
                with col_tp_off:
                    if st.button("📡 OFF", key="tpsl_off", use_container_width=True, disabled=not tpsl_enabled):
                        try:
                            resp = requests.post(f"{TRADING_BOT_URL}/auto-tp-sl/toggle", json={'enabled': False}, timeout=5)
                            if resp.status_code == 200:
                                st.warning("📡 TP/SL 자동생성 OFF!")
                                time_module.sleep(1)
                                st.rerun()
                        except Exception as e:
                            st.error(f"❌ 실패: {e}")
            else:
                st.error("상태를 가져올 수 없습니다")
        else:
            st.warning("봇이 오프라인입니다")
        
        st.markdown("---")
        
        # ============ 🆕 v7.8: Emergency Drawdown Protection ============
        st.header("🛡️ 긴급 낙폭 보호")
        
        if bot_online:
            edp_status = None
            try:
                resp = requests.get(f"{TRADING_BOT_URL}/emergency-drawdown/status", timeout=3)
                if resp.status_code == 200:
                    edp_status = resp.json()
            except:
                pass
            
            if edp_status is not None:
                edp_enabled = edp_status.get('enabled', False)
                edp_running = edp_status.get('running', False)
                warn_thresh = edp_status.get('warning_threshold', -25.0)
                force_thresh = edp_status.get('force_exit_threshold', -50.0)
                mon_interval = edp_status.get('monitor_interval', 15)
                warned_syms = edp_status.get('warned_symbols', [])
                
                if edp_enabled:
                    st.success(f"🟢 낙폭 보호 활성 {'(실행중)' if edp_running else ''}")
                else:
                    st.error("🔴 낙폭 보호 비활성")
                
                st.caption(f"⚠️ ROI ≤ {warn_thresh}% → AI 집중 모니터링 ({mon_interval}분)")
                st.caption(f"🚨 ROI ≤ {force_thresh}% → 즉시 강제 청산")
                
                if warned_syms:
                    st.warning(f"⚠️ 경고 중: {', '.join(warned_syms)}")
                
                col_edp_on, col_edp_off = st.columns(2)
                with col_edp_on:
                    if st.button("🛡️ ON", key="edp_on", use_container_width=True, disabled=edp_enabled):
                        try:
                            resp = requests.post(f"{TRADING_BOT_URL}/emergency-drawdown/toggle", json={'enabled': True}, timeout=5)
                            if resp.status_code == 200:
                                st.success("✅ 낙폭 보호 활성화!")
                                time_module.sleep(1)
                                st.rerun()
                        except Exception as e:
                            st.error(f"❌ 실패: {e}")
                with col_edp_off:
                    if st.button("⛔ OFF", key="edp_off", use_container_width=True, disabled=not edp_enabled):
                        try:
                            resp = requests.post(f"{TRADING_BOT_URL}/emergency-drawdown/toggle", json={'enabled': False}, timeout=5)
                            if resp.status_code == 200:
                                st.warning("⛔ 낙폭 보호 비활성화!")
                                time_module.sleep(1)
                                st.rerun()
                        except Exception as e:
                            st.error(f"❌ 실패: {e}")
                
                with st.expander("⚙️ 파라미터 설정"):
                    new_warn = st.number_input(
                        "경고 임계값 (%)", min_value=-80.0, max_value=-5.0,
                        value=float(warn_thresh), step=5.0, key="edp_warn"
                    )
                    new_force = st.number_input(
                        "강제청산 임계값 (%)", min_value=-95.0, max_value=-10.0,
                        value=float(force_thresh), step=5.0, key="edp_force"
                    )
                    new_interval = st.number_input(
                        "모니터링 간격 (분)", min_value=1, max_value=60,
                        value=int(mon_interval), step=5, key="edp_interval"
                    )
                    
                    if st.button("💾 설정 저장", key="edp_save", use_container_width=True):
                        try:
                            resp = requests.post(
                                f"{TRADING_BOT_URL}/emergency-drawdown/config",
                                json={
                                    'warning_threshold': new_warn,
                                    'force_exit_threshold': new_force,
                                    'monitor_interval': new_interval
                                }, timeout=5
                            )
                            if resp.status_code == 200:
                                st.success(f"✅ 저장! 경고:{new_warn}% / 강제:{new_force}% / 간격:{new_interval}분")
                                time_module.sleep(1)
                                st.rerun()
                        except Exception as e:
                            st.error(f"❌ 실패: {e}")
            else:
                st.error("상태를 가져올 수 없습니다")
        else:
            st.warning("봇이 오프라인입니다")
        
        st.markdown("---")
        
        # ============ 🆕 v7.9: Market Shield ============
        st.header("🛡️ Market Shield (멀티소스 방어)")
        
        try:
            resp = requests.get(f"{TRADING_BOT_URL}/market-shield/status", timeout=3)
            if resp.status_code == 200:
                shield = resp.json()
                
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    status = "🟢 활성" if shield.get('enabled') else "🔴 비활성"
                    st.metric("상태", status)
                with col2:
                    running = "✅ 실행중" if shield.get('running') else "⏸️ 대기"
                    st.metric("스레드", running)
                with col3:
                    st.metric("경제 이벤트", f"{shield.get('calendar_events', 0)}건")
                with col4:
                    anomalies = shield.get('active_anomalies', {})
                    blocked = shield.get('blocked_entries', {})
                    st.metric("이상 감지 / 차단", f"{len(anomalies)} / {len(blocked)}")
                
                # ON/OFF 토글
                col_on, col_off = st.columns(2)
                with col_on:
                    if st.button("🛡️ Shield 활성화", key="shield_on", use_container_width=True):
                        try:
                            resp = requests.post(f"{TRADING_BOT_URL}/market-shield/toggle", json={'enabled': True}, timeout=5)
                            if resp.status_code == 200:
                                st.success("✅ Market Shield 활성화!")
                                st.rerun()
                        except Exception as e:
                            st.error(f"❌ 실패: {e}")
                with col_off:
                    if st.button("⛔ Shield 비활성화", key="shield_off", use_container_width=True):
                        try:
                            resp = requests.post(f"{TRADING_BOT_URL}/market-shield/toggle", json={'enabled': False}, timeout=5)
                            if resp.status_code == 200:
                                st.warning("⛔ Market Shield 비활성화")
                                st.rerun()
                        except Exception as e:
                            st.error(f"❌ 실패: {e}")
                
                # 파라미터 설정
                with st.expander("⚙️ Market Shield 설정"):
                    ms_col1, ms_col2 = st.columns(2)
                    with ms_col1:
                        block_before = st.number_input("이벤트 전 차단 (분)", 
                                                       value=shield.get('block_before_min', 120),
                                                       min_value=30, max_value=360, step=30, key="ms_before")
                        zscore = st.number_input("Z-Score 임계값 (σ)", 
                                                 value=float(shield.get('zscore_threshold', 3.0)),
                                                 min_value=2.0, max_value=5.0, step=0.5, key="ms_zscore")
                    with ms_col2:
                        block_after = st.number_input("이벤트 후 차단 (분)", 
                                                      value=shield.get('block_after_min', 60),
                                                      min_value=15, max_value=180, step=15, key="ms_after")
                        cooldown = st.number_input("이상 감지 후 차단 (초)", 
                                                   value=shield.get('anomaly_cooldown_sec', 600),
                                                   min_value=60, max_value=3600, step=60, key="ms_cooldown")
                    
                    if st.button("💾 Shield 설정 저장", key="ms_save", use_container_width=True):
                        try:
                            resp = requests.post(f"{TRADING_BOT_URL}/market-shield/config", json={
                                'block_before': block_before,
                                'block_after': block_after,
                                'zscore_threshold': zscore,
                                'anomaly_cooldown': cooldown
                            }, timeout=5)
                            if resp.status_code == 200:
                                st.success("✅ 설정 저장 완료!")
                        except Exception as e:
                            st.error(f"❌ 저장 실패: {e}")
                
                # 실시간 상태 표시
                if anomalies:
                    st.subheader("⚡ 활성 이상 감지")
                    for sym, info in anomalies.items():
                        direction = "📈 급등" if info['direction'] == 'surge' else "📉 급락"
                        st.warning(f"{direction} **{sym}** — 가격 Z={info['z_price']}σ, 거래량 Z={info['z_volume']}σ")
                
                if blocked:
                    st.subheader("⛔ 진입 차단 중")
                    for sym, info in blocked.items():
                        st.error(f"**{sym}** — {info['reason']} (해제: {info['until'][:19]})")
                
            else:
                st.error("Market Shield 상태를 가져올 수 없습니다")
        except requests.exceptions.ConnectionError:
            st.warning("봇이 오프라인입니다")
        except Exception as e:
            st.error(f"Market Shield 오류: {e}")
        
        st.markdown("---")
        

    # ==========================================
    # 🆕 v8.0 Tab 8: 이상 감지 (리페인팅 등)
    # ==========================================
    with tab8:
        st.header("⚠️ 이상 현상 감지 로그")
        st.caption("Pine 실시간 종료의 리페인팅으로 진입↔종료가 반복되며 수수료가 소진되는 현상을 봇이 자동 차단하고 여기에 기록합니다.")

        @st_fragment(run_every=5)
        def render_anomaly_panel():
            colf1, colf2, colf3 = st.columns([1, 1, 2])
            with colf1:
                hours = st.selectbox("조회 기간", [1, 6, 24, 72, 168],
                                     format_func=lambda h: f"최근 {h}시간" if h < 168 else "최근 7일",
                                     index=2, key="anom_hours")
            with colf2:
                limit = st.selectbox("최대 건수", [50, 100, 300], index=1, key="anom_limit")
            with colf3:
                st.write("")
                if st.button("🔄 새로고침", key="anom_refresh", use_container_width=True):
                    invalidate_caches()

            data = fetch_anomalies(limit=limit, hours=hours)

            if data.get('status') != 'success':
                st.warning(f"봇에서 이상 감지 로그를 가져올 수 없습니다: {data.get('error', data.get('http', '연결 실패'))}")
                return

            # 요약 지표
            c1, c2, c3, c4 = st.columns(4)
            with c1:
                st.metric("리페인팅 방어", "ON" if data.get('guard_enabled') else "OFF")
            with c2:
                st.metric("감지 건수", f"{data.get('total', 0)}건")
            with c3:
                st.metric("차단 중 심볼", f"{data.get('blocked_count', 0)}개")
            with c4:
                st.metric("최소 보유", f"{data.get('min_hold_seconds', 0)}초")

            st.markdown("---")

            # 차단 중인 심볼
            suspects = data.get('suspects', [])
            blocked_now = [s for s in suspects if s.get('blocked')]
            if blocked_now:
                st.subheader("⛔ 현재 차단 중인 심볼")
                for s in blocked_now:
                    cc1, cc2 = st.columns([4, 1])
                    with cc1:
                        st.error(
                            f"**{s['symbol']}** — 누적 {s['strikes']}회 감지 · "
                            f"잔여 {s['remain_minutes']:.0f}분 (해제 {s['until']})"
                        )
                    with cc2:
                        if st.button("해제", key=f"unblock_{s['symbol']}", use_container_width=True):
                            ok, resp = bot_api_post('/anomalies/unblock', {'symbol': s['symbol']})
                            if ok:
                                st.success(f"{s['symbol']} 차단 해제됨")
                            else:
                                st.error(f"해제 실패: {resp}")
                if st.button("🧹 전체 차단 해제", key="unblock_all"):
                    ok, resp = bot_api_post('/anomalies/unblock', {'all': True})
                    st.success(f"{resp.get('cleared', 0)}개 해제") if ok else st.error("해제 실패")
                st.markdown("---")
            else:
                st.success("✅ 현재 차단 중인 심볼이 없습니다")
                st.markdown("---")

            # 이상 로그 테이블
            rows = data.get('anomalies', [])
            if not rows:
                st.info("기록된 이상 현상이 없습니다.")
                return

            df = pd.DataFrame(rows)
            type_label = {
                'repaint_close_ignored': '🔁 종료신호 무시',
                'repaint_entry_blocked': '⛔ 진입 차단',
                'repaint_confirmed': '❗ 리페인팅 확정'
            }
            df['유형'] = df['anomaly_type'].map(lambda t: type_label.get(t, t))
            df['심각도'] = df['severity'].map({'warning': '⚠️', 'error': '🔴', 'info': 'ℹ️'}).fillna('⚠️')

            # 심볼별 발생 빈도
            st.subheader("📊 심볼별 발생 빈도")
            freq = df.groupby('symbol').size().reset_index(name='건수').sort_values('건수', ascending=False)
            if not freq.empty:
                fig = px.bar(freq.head(15), x='symbol', y='건수',
                             color='건수', color_continuous_scale='Reds')
                fig.update_layout(height=280, margin=dict(l=10, r=10, t=10, b=10),
                                  showlegend=False, coloraxis_showscale=False)
                st.plotly_chart(fig, use_container_width=True, key="anom_freq_chart")

            st.subheader("📋 상세 로그")
            show = df[['timestamp', '심각도', 'symbol', '유형', 'detail', 'action_taken', 'held_seconds', 'strikes']].copy()
            show.columns = ['시각', '', '심볼', '유형', '내용', '조치', '보유(초)', '누적']
            st.dataframe(show, use_container_width=True, hide_index=True, height=420)

            csv = show.to_csv(index=False).encode('utf-8-sig')
            st.download_button("📥 CSV 다운로드", csv,
                               f"anomalies_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                               "text/csv", key="anom_csv")

        render_anomaly_panel()

        with st.expander("ℹ️ 리페인팅 방어 동작 방식"):
            st.markdown("""
**1단 — 종료 신호 무시**
진입 후 `MIN_HOLD_SECONDS`(기본 90초) 이내에 도착한 `close_position`/`partial_close` 신호는
정상 청산이 아니라 리페인팅으로 판단해 무시합니다.

**2단 — 재진입 차단**
1단이 발동한 심볼은 `REPAINT_BLOCK_MINUTES`(기본 60분) 동안 신규 진입(`buy`/`sell`)도 차단합니다.
되살아난 진입 신호를 그대로 실행하면 진입↔종료 루프가 반복되어 수수료만 소진되기 때문입니다.

**누적 감지**
같은 심볼에서 반복되면 차단 시간이 자동으로 연장됩니다.
차트를 점검해 리페인팅 원인을 제거한 뒤 위에서 수동 해제하세요.

**환경변수**
`REPAINT_GUARD_ENABLED` / `MIN_HOLD_SECONDS` / `REPAINT_BLOCK_MINUTES` / `REPAINT_STRIKE_LIMIT`
            """)

        st.markdown("---")

    # 페이지 하단 정보 (탭 밖)
    st.markdown("---")
    st.caption("Trading Dashboard v8.0 Complete — 캐싱/프래그먼트 반응성 개선 · 리페인팅 방어 · 바이낸스 손익 동기화")
    st.caption("© 2025 Automated Trading System")

if __name__ == "__main__":
    main()
