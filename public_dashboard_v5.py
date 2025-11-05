#!/usr/bin/env python3
"""
Public Dashboard v5 - Exchange Direct Version
거래소 직접 조회와 DB 동기화 기능이 있는 최종 버전
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
    page_title="Trading Dashboard v5 - Live Exchange",
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
</style>
""", unsafe_allow_html=True)

# 전역 변수로 거래소 객체
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
    
    # 거래소 포지션 심볼 목록
    exchange_symbols = set(exchange_df['symbol'].tolist()) if not exchange_df.empty else set()
    
    # DB 포지션 심볼 목록
    db_symbols = set(db_df['symbol'].tolist()) if not db_df.empty else set()
    
    # 매칭된 포지션
    matched_symbols = exchange_symbols & db_symbols
    for symbol in matched_symbols:
        ex_pos = exchange_df[exchange_df['symbol'] == symbol].iloc[0]
        db_pos = db_df[db_df['symbol'] == symbol].iloc[0]
        
        # 수량 비교
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
    
    # 거래소에만 있는 포지션
    for symbol in exchange_symbols - db_symbols:
        ex_pos = exchange_df[exchange_df['symbol'] == symbol].iloc[0]
        comparison['exchange_only'].append({
            'symbol': symbol,
            'amount': ex_pos['contracts'],
            'pnl': ex_pos['unrealized_pnl']
        })
    
    # DB에만 있는 포지션 (종료되었지만 DB에 남은 것)
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
        
        # DB에만 있는 포지션 종료 처리
        for pos in comparison['db_only']:
            symbol = pos['symbol']
            
            # position_history에 종료 기록 (amount = 0으로 포지션 종료 표시)
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
        
        # 동기화 버튼
        if st.button("🔄 DB 동기화 실행", type="primary"):
            if sync_positions_to_db(comparison):
                st.success("✅ DB 동기화 완료!")
                st.experimental_rerun()

def display_combined_positions(exchange_df, db_df):
    """통합 포지션 표시"""
    st.subheader("📍 Active Positions")
    
    if exchange_df.empty and db_df.empty:
        st.info("활성 포지션이 없습니다")
        return
    
    # 거래소 우선으로 통합
    all_symbols = set()
    if not exchange_df.empty:
        all_symbols.update(exchange_df['symbol'].tolist())
    if not db_df.empty:
        all_symbols.update(db_df['symbol'].tolist())
    
    for symbol in sorted(all_symbols):
        col1, col2, col3, col4, col5, col6 = st.columns([2, 1, 1, 1, 1, 1])
        
        # 거래소 데이터 우선
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

def main():
    # 헤더
    st.markdown('<div class="main-header">Trading Dashboard v5 - Live Exchange</div>', unsafe_allow_html=True)
    
    # 사이드바 - 데이터 소스 선택
    st.sidebar.header("⚙️ Settings")
    data_source = st.sidebar.radio(
        "Data Source",
        ["Exchange + DB", "Exchange Only", "DB Only"],
        index=0
    )
    
    auto_refresh = st.sidebar.checkbox("Auto Refresh (10s)", value=False)
    auto_sync = st.sidebar.checkbox("Auto Sync DB", value=True, help="자동으로 DB와 거래소 불일치 포지션 정리 (30초마다)")
    
    # 자동 동기화 실행 (session_state로 주기 관리)
    if auto_sync:
        if 'last_sync_time' not in st.session_state:
            st.session_state.last_sync_time = datetime.now() - timedelta(seconds=31)
        
        time_since_sync = (datetime.now() - st.session_state.last_sync_time).total_seconds()
        
        # 30초마다 한 번씩만 실행
        if time_since_sync > 30:
            try:
                exchange_pos = get_exchange_positions()
                db_pos = get_db_positions()
                comparison = compare_positions(exchange_pos, db_pos)
                
                # DB에만 있는 포지션이 있으면 자동 삭제
                if comparison['db_only']:
                    if sync_positions_to_db(comparison):
                        st.session_state.last_sync_time = datetime.now()
                else:
                    st.session_state.last_sync_time = datetime.now()
                    
            except Exception as e:
                st.sidebar.error(f"자동 동기화 오류: {e}")
        
        # 다음 동기화까지 남은 시간 표시
        next_sync = 30 - time_since_sync
        if next_sync > 0:
            st.sidebar.caption(f"다음 동기화: {int(next_sync)}초 후")
    
    # 데이터 로드
    exchange_positions = pd.DataFrame()
    db_positions = pd.DataFrame()
    
    if data_source in ["Exchange + DB", "Exchange Only"]:
        exchange_positions = get_exchange_positions()
    
    if data_source in ["Exchange + DB", "DB Only"]:
        db_positions = get_db_positions()
    
    # 메인 컨텐츠
    tab1, tab2, tab3, tab4 = st.tabs([
        "📊 Overview",
        "🔄 Sync Status", 
        "📈 Performance",
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
                color = "green" if total_pnl >= 0 else "red"
                st.metric("Total PnL", f"${total_pnl:.2f}", delta_color="normal")
            
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
        
        # 포지션 표시
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
                
                # 상세 비교 표시
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
        
        try:
            conn = sqlite3.connect('integrated_trades.db')
            
            # =========================
            # 0. 전체 자산 추이 그래프 (최상단)
            # =========================
            st.subheader("💎 Total Equity Over Time")
            
            # 현재 거래소 잔고 조회
            current_balance = get_account_balance()
            
            if current_balance is not None:
                col_balance1, col_balance2, col_balance3 = st.columns(3)
                
                with col_balance1:
                    st.metric("Current Balance", f"${current_balance:.2f}", 
                             help="거래소 현재 USDT 잔고")
                
                # 과거 자산 추이 계산 (현재 잔고 - 누적 PnL 역산)
                equity_history_query = """
                SELECT 
                    close_timestamp,
                    symbol,
                    pnl_usdt,
                    SUM(pnl_usdt) OVER (ORDER BY close_timestamp DESC) as reverse_cumulative_pnl
                FROM completed_trades
                WHERE close_timestamp >= date('now', '-30 days')
                ORDER BY close_timestamp ASC
                """
                
                equity_hist_df = pd.read_sql_query(equity_history_query, conn)
                
                if not equity_hist_df.empty:
                    equity_hist_df['close_timestamp'] = pd.to_datetime(equity_hist_df['close_timestamp'])
                    
                    # 각 시점의 추정 자산 = 현재 잔고 - (미래 거래들의 PnL 합)
                    equity_hist_df['estimated_balance'] = current_balance - equity_hist_df['reverse_cumulative_pnl']
                    
                    # 현재 시점 추가
                    current_row = pd.DataFrame({
                        'close_timestamp': [datetime.now()],
                        'estimated_balance': [current_balance]
                    })
                    
                    equity_hist_df = pd.concat([
                        equity_hist_df[['close_timestamp', 'estimated_balance']], 
                        current_row
                    ]).sort_values('close_timestamp')
                    
                    # 초기 자산과 현재 자산 비교
                    initial_balance = equity_hist_df['estimated_balance'].iloc[0]
                    total_gain = current_balance - initial_balance
                    total_gain_pct = (total_gain / initial_balance * 100) if initial_balance > 0 else 0
                    
                    with col_balance2:
                        st.metric("Starting Balance (30d)", f"${initial_balance:.2f}")
                    
                    with col_balance3:
                        st.metric("Total Gain (30d)", f"${total_gain:.2f}", 
                                 delta=f"{total_gain_pct:+.2f}%",
                                 delta_color="normal")
                    
                    # 자산 추이 그래프
                    fig_total_equity = go.Figure()
                    
                    # 자산 곡선
                    fig_total_equity.add_trace(go.Scatter(
                        x=equity_hist_df['close_timestamp'],
                        y=equity_hist_df['estimated_balance'],
                        mode='lines+markers',
                        name='Total Equity',
                        line=dict(color='#1f77b4', width=3),
                        fill='tozeroy',
                        fillcolor='rgba(31, 119, 180, 0.1)',
                        marker=dict(size=6)
                    ))
                    
                    # 초기 잔고 기준선
                    fig_total_equity.add_hline(
                        y=initial_balance, 
                        line_dash="dash", 
                        line_color="gray", 
                        opacity=0.5,
                        annotation_text=f"Start: ${initial_balance:.2f}",
                        annotation_position="right"
                    )
                    
                    fig_total_equity.update_layout(
                        title="Account Equity Growth",
                        xaxis_title="Date",
                        yaxis_title="Balance (USDT)",
                        hovermode='x unified',
                        height=450,
                        showlegend=False
                    )
                    
                    st.plotly_chart(fig_total_equity, use_container_width=True)
                else:
                    st.info("자산 추이를 계산할 거래 데이터가 없습니다.")
            else:
                st.warning("⚠️ 거래소 잔고를 조회할 수 없습니다. API 키를 확인해주세요.")
            
            st.markdown("---")
            
            # =========================
            # 1. 전체 통계 요약
            # =========================
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
                
                # None 값 처리
                total_trades = int(stats['total_trades']) if pd.notna(stats['total_trades']) else 0
                wins = int(stats['wins']) if pd.notna(stats['wins']) else 0
                losses = int(stats['losses']) if pd.notna(stats['losses']) else 0
                total_pnl = float(stats['total_pnl']) if pd.notna(stats['total_pnl']) else 0.0
                avg_pnl_percent = float(stats['avg_pnl_percent']) if pd.notna(stats['avg_pnl_percent']) else 0.0
                max_profit = float(stats['max_profit']) if pd.notna(stats['max_profit']) else 0.0
                max_loss = float(stats['max_loss']) if pd.notna(stats['max_loss']) else 0.0
                avg_win = float(stats['avg_win']) if pd.notna(stats['avg_win']) else 0.0
                avg_loss = float(stats['avg_loss']) if pd.notna(stats['avg_loss']) else 0.0
                
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
                
                # =========================
                # 2. 자산 증감 시계열 그래프
                # =========================
                st.subheader("💰 Cumulative PnL Over Time")
                
                equity_query = """
                SELECT 
                    date(close_timestamp) as date,
                    close_timestamp,
                    symbol,
                    pnl_usdt,
                    SUM(pnl_usdt) OVER (ORDER BY close_timestamp) as cumulative_pnl
                FROM completed_trades
                WHERE close_timestamp >= date('now', '-30 days')
                ORDER BY close_timestamp
                """
                
                equity_df = pd.read_sql_query(equity_query, conn)
                
                if not equity_df.empty:
                    equity_df['close_timestamp'] = pd.to_datetime(equity_df['close_timestamp'])
                    
                    fig_equity = go.Figure()
                    
                    # 누적 PnL 라인
                    fig_equity.add_trace(go.Scatter(
                        x=equity_df['close_timestamp'],
                        y=equity_df['cumulative_pnl'],
                        mode='lines+markers',
                        name='Cumulative PnL',
                        line=dict(color='#2ca02c', width=3),
                        fill='tozeroy',
                        fillcolor='rgba(44, 160, 44, 0.1)'
                    ))
                    
                    # 0 기준선
                    fig_equity.add_hline(y=0, line_dash="dash", line_color="gray", opacity=0.5)
                    
                    fig_equity.update_layout(
                        title="Cumulative Profit/Loss Timeline",
                        xaxis_title="Date",
                        yaxis_title="PnL (USDT)",
                        hovermode='x unified',
                        height=400
                    )
                    
                    st.plotly_chart(fig_equity, use_container_width=True)
                else:
                    st.info("충분한 거래 데이터가 없습니다.")
                
                # =========================
                # 3. 심볼별 성과 분석
                # =========================
                col_left, col_right = st.columns(2)
                
                with col_left:
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
                        # 컬러 매핑
                        symbol_df['color'] = symbol_df['total_pnl'].apply(
                            lambda x: '🟢' if x > 0 else '🔴'
                        )
                        
                        # 표시용 데이터프레임
                        display_df = symbol_df[['color', 'symbol', 'trades', 'win_rate', 'total_pnl', 'avg_pnl_pct']].copy()
                        display_df.columns = ['', 'Symbol', 'Trades', 'Win Rate %', 'Total PnL', 'Avg %']
                        
                        st.dataframe(
                            display_df,
                            use_container_width=True,
                            hide_index=True
                        )
                    else:
                        st.info("심볼별 데이터가 없습니다.")
                
                with col_right:
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
                        
                        fig_winrate.add_hline(y=50, line_dash="dash", line_color="gray", 
                                             annotation_text="50% Break-even")
                        
                        fig_winrate.update_layout(
                            title="Win Rate by Symbol",
                            xaxis_title="Symbol",
                            yaxis_title="Win Rate (%)",
                            showlegend=False,
                            height=300
                        )
                        
                        st.plotly_chart(fig_winrate, use_container_width=True)
                
                st.markdown("---")
                
                # =========================
                # 4. Best & Worst 거래 리더보드
                # =========================
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
                    else:
                        st.info("데이터 없음")
                
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
                    else:
                        st.info("데이터 없음")
                
                st.markdown("---")
                
                # =========================
                # 5. 추가 통계 분석
                # =========================
                col_stats1, col_stats2, col_stats3 = st.columns(3)
                
                with col_stats1:
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
                
                with col_stats2:
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
                    else:
                        st.info("보유 시간 데이터 없음")
                
                with col_stats3:
                    st.subheader("🎲 Risk/Reward")
                    
                    if avg_win != 0 and avg_loss != 0:
                        risk_reward_ratio = abs(avg_win / avg_loss)
                        
                        # 도넛 차트
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
                        st.info("Risk/Reward 비율 계산 불가")
            
            else:
                st.info("⚠️ 최근 30일간 완료된 거래가 없습니다.")
            
            conn.close()
            
        except Exception as e:
            st.error(f"통계 조회 오류: {e}")
            import traceback
            st.text(traceback.format_exc())
    
    with tab4:
        st.header("🤖 AI Monitoring Status")
        
        try:
            conn = sqlite3.connect('integrated_trades.db')
            
            # AI 모니터링 기록
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
            
            if not ai_df.empty:
                ai_df['timestamp'] = pd.to_datetime(ai_df['timestamp'])
                ai_df['confidence'] = ai_df['confidence'] * 100
                
                st.dataframe(
                    ai_df.style.format({'confidence': '{:.1f}%'}),
                    use_container_width=True
                )
            else:
                st.info("No AI monitoring records found")
            
            conn.close()
            
        except Exception as e:
            st.error(f"AI 모니터링 조회 오류: {e}")
    
    # 자동 새로고침
    if auto_refresh:
        import time
        time.sleep(10)
        st.experimental_rerun()
    
    # Footer
    st.markdown("---")
    st.caption(f"Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | Data: {data_source}")

if __name__ == "__main__":
    main()
