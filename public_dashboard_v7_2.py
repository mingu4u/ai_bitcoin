#!/usr/bin/env python3
"""
Public Dashboard v7.3 Complete - 모든 기능 복원 버전
=======================================================
v7.2의 수정사항 + v6의 모든 Performance Analysis 기능 통합

주요 기능:
1. 🔥 Exchange 연결 문제 해결 (v7.2)
2. 📊 다중 기간 성과 분석 (v6)
3. 📈 심볼별 수익 분석 (v6)
4. 🎯 상세한 그래프와 통계 (v6)
5. ⚡ 실시간 업데이트 (v7)

작성일: 2025-11-22
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
    page_title="Trading Dashboard v7.3 Complete",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ============ 실시간 설정 ============
REALTIME_ENABLED = True
EVENT_POLL_INTERVAL = 2
AUTO_REFRESH_INTERVAL = 3
TRADING_BOT_URL = "http://localhost:5000"

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
</style>
""", unsafe_allow_html=True)

# ==========================================
# Helper Functions
# ==========================================

def get_binance_exchange():
    """바이낸스 거래소 객체 생성 (v7.3: 캐시 제거)"""
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

def fetch_balance_from_binance(exchange):
    """바이낸스에서 실시간 잔고 가져오기"""
    try:
        if exchange is None:
            return {'total': 0, 'free': 0, 'used': 0}
        
        balance = exchange.fetch_balance()
        
        if 'USDT' in balance:
            return {
                'total': balance['USDT']['total'],
                'free': balance['USDT']['free'],
                'used': balance['USDT']['used']
            }
        else:
            return {'total': 0, 'free': 0, 'used': 0}
        
    except Exception as e:
        st.error(f"잔고 조회 오류: {e}")
        return {'total': 0, 'free': 0, 'used': 0}

def fetch_positions_from_binance(exchange):
    """바이낸스에서 실시간 포지션 가져오기"""
    try:
        if exchange is None:
            return []
        
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
            leverage = int(pos['info'].get('leverage', 10))
            
            result.append({
                'symbol': symbol,
                'side': side,
                'amount': amount,
                'entry_price': entry_price,
                'mark_price': mark_price,
                'liquidation_price': liquidation_price,
                'unrealized_pnl': unrealized_pnl,
                'leverage': leverage,
                'pnl_percent': ((mark_price - entry_price) / entry_price * 100 * leverage) if side == 'long' 
                              else ((entry_price - mark_price) / entry_price * 100 * leverage)
            })
        
        return result
        
    except Exception as e:
        st.error(f"포지션 조회 오류: {e}")
        return []

def get_or_set_initial_balance():
    """초기 잔고 가져오기 또는 설정"""
    try:
        conn = sqlite3.connect('integrated_trades.db')
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
        conn = sqlite3.connect('integrated_trades.db')
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
        conn = sqlite3.connect('integrated_trades.db')
        
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
        conn = sqlite3.connect('integrated_trades.db')
        
        query = f"""
        SELECT 
            COUNT(*) as trades,
            SUM(CASE WHEN is_win = 1 THEN 1 ELSE 0 END) as wins,
            SUM(pnl_usdt) as total_pnl
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
        conn = sqlite3.connect('integrated_trades.db')
        
        if days:
            query = f"""
            SELECT 
                close_timestamp,
                SUM(pnl_usdt) OVER (ORDER BY close_timestamp) as cumulative_pnl
            FROM completed_trades
            WHERE close_timestamp >= date('now', '-{days} days')
            ORDER BY close_timestamp
            """
        else:
            query = """
            SELECT 
                close_timestamp,
                SUM(pnl_usdt) OVER (ORDER BY close_timestamp) as cumulative_pnl
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
    st.markdown('<h1 class="main-header">⚡ Automated Trading Dashboard v7.3 Complete</h1>', unsafe_allow_html=True)
    
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
    tab1, tab2, tab3, tab4 = st.tabs([
        "📊 Trading Overview", 
        "📈 Performance Analysis", 
        "📜 Trade History",
        "🎯 Symbol Analytics"
    ])
    
    # ==========================================
    # Tab 1: Trading Overview
    # ==========================================
    with tab1:
        st.header("📊 Real-time Trading Status")
        
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
            
            # 포지션 테이블
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
                    
                    # ===================================
                    # 누적 PnL 그래프
                    # ===================================
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
                    
                    # ===================================
                    # Best & Worst 거래
                    # ===================================
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
                    
                    # ===================================
                    # 추가 통계 차트
                    # ===================================
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
        else:
            st.error("⚠️ 잔고 정보를 가져올 수 없습니다.")
    
    # ==========================================
    # Tab 3: Trade History
    # ==========================================
    with tab3:
        st.header("📜 Trade History")
        
        try:
            conn = sqlite3.connect('integrated_trades.db')
            
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
                pnl_usdt,
                pnl_percent,
                holding_time_minutes,
                close_reason,
                position_type,
                realized_pnl_binance
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
                
                # 컬럼 선택 및 표시
                display_columns = ['close_timestamp', 'symbol', 'side', 'entry_price', 
                                 'exit_price', 'pnl_usdt', 'pnl_percent', 'holding_time', 
                                 'close_reason', 'verified']
                
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
            conn = sqlite3.connect('integrated_trades.db')
            
            # 심볼별 상세 분석
            st.subheader("📊 Symbol Performance Matrix")
            
            symbol_analysis_query = """
            SELECT 
                symbol,
                COUNT(*) as total_trades,
                SUM(CASE WHEN is_win = 1 THEN 1 ELSE 0 END) as wins,
                ROUND(AVG(CASE WHEN is_win = 1 THEN 1.0 ELSE 0.0 END) * 100, 1) as win_rate,
                ROUND(SUM(pnl_usdt), 2) as total_pnl,
                ROUND(AVG(pnl_usdt), 2) as avg_pnl,
                ROUND(MAX(pnl_usdt), 2) as max_win,
                ROUND(MIN(pnl_usdt), 2) as max_loss,
                ROUND(AVG(holding_time_minutes), 1) as avg_holding_time,
                ROUND(SUM(amount * entry_price), 2) as total_volume
            FROM completed_trades
            WHERE close_timestamp >= date('now', '-30 days')
            GROUP BY symbol
            HAVING COUNT(*) >= 3
            ORDER BY total_pnl DESC
            """
            
            symbol_analysis_df = pd.read_sql_query(symbol_analysis_query, conn)
            
            if not symbol_analysis_df.empty:
                # Profit Factor 계산
                symbol_analysis_df['profit_factor'] = symbol_analysis_df.apply(
                    lambda row: abs(row['max_win'] / row['max_loss']) if row['max_loss'] != 0 else 0,
                    axis=1
                )
                
                # 컬러 코딩
                symbol_analysis_df['status'] = symbol_analysis_df['total_pnl'].apply(
                    lambda x: '🟢' if x > 0 else '🔴'
                )
                
                # 표시
                display_df = symbol_analysis_df[[
                    'status', 'symbol', 'total_trades', 'win_rate', 
                    'total_pnl', 'avg_pnl', 'max_win', 'max_loss', 
                    'profit_factor', 'total_volume'
                ]]
                
                display_df.columns = [
                    '', 'Symbol', 'Trades', 'Win %', 'Total PnL', 
                    'Avg PnL', 'Best', 'Worst', 'PF', 'Volume'
                ]
                
                st.dataframe(display_df, use_container_width=True, hide_index=True)
                
                # 차트들
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
                
                # 시간대별 분석
                st.subheader("⏰ Trading Activity by Hour")
                
                hourly_query = """
                SELECT 
                    strftime('%H', close_timestamp) as hour,
                    COUNT(*) as trades,
                    SUM(pnl_usdt) as total_pnl
                FROM completed_trades
                WHERE close_timestamp >= date('now', '-30 days')
                GROUP BY hour
                ORDER BY hour
                """
                
                hourly_df = pd.read_sql_query(hourly_query, conn)
                
                if not hourly_df.empty:
                    fig_hourly = make_subplots(
                        rows=1, cols=2,
                        subplot_titles=('Trades by Hour', 'PnL by Hour')
                    )
                    
                    fig_hourly.add_trace(
                        go.Bar(x=hourly_df['hour'], y=hourly_df['trades'], name='Trades'),
                        row=1, col=1
                    )
                    
                    fig_hourly.add_trace(
                        go.Bar(
                            x=hourly_df['hour'], 
                            y=hourly_df['total_pnl'], 
                            name='PnL',
                            marker_color=hourly_df['total_pnl'].apply(
                                lambda x: '#2ca02c' if x > 0 else '#d62728'
                            )
                        ),
                        row=1, col=2
                    )
                    
                    fig_hourly.update_layout(height=350, showlegend=False)
                    st.plotly_chart(fig_hourly, use_container_width=True)
            
            conn.close()
            
        except Exception as e:
            st.error(f"심볼 분석 오류: {e}")
    
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
        
        # 봇 상태 확인
        try:
            response = requests.get(f"{TRADING_BOT_URL}/status", timeout=2)
            if response.status_code == 200:
                st.success("🤖 Trading Bot: Online")
            else:
                st.warning("🤖 Trading Bot: Error")
        except:
            st.error("🤖 Trading Bot: Offline")
        
        st.markdown("---")
        
        # 정보
        st.caption("Trading Dashboard v7.3 Complete")
        st.caption("© 2025 Automated Trading System")

if __name__ == "__main__":
    main()
