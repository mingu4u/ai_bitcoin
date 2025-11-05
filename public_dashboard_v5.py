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
        
        # DB에만 있는 포지션 종료 처리
        for pos in comparison['db_only']:
            symbol = pos['symbol']
            
            # position_history에 종료 기록 (amount = 0)
            cursor.execute("""
                INSERT INTO position_history 
                (timestamp, symbol, side, amount, entry_price, current_price,
                 pnl_usdt, pnl_percent, position_value, required_margin, liquidation_price)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                datetime.now().isoformat(), symbol, 'closed', 0, 0, 0,
                0, 0, 0, 0, 0
            ))
            
            # trades 테이블 업데이트
            cursor.execute("""
                UPDATE trades 
                SET status = 'closed_by_sync'
                WHERE symbol = ? AND status = 'active'
            """, (symbol,))
        
        conn.commit()
        conn.close()
        
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
    auto_sync = st.sidebar.checkbox("Auto Sync DB (30s)", value=True, help="자동으로 DB와 거래소 불일치 포지션 정리")
    
    # 자동 동기화 실행
    if auto_sync:
        try:
            exchange_pos = get_exchange_positions()
            db_pos = get_db_positions()
            comparison = compare_positions(exchange_pos, db_pos)
            
            # DB에만 있는 포지션이 있으면 자동 삭제
            if comparison['db_only']:
                sync_positions_to_db(comparison)
                st.sidebar.success(f"✅ {len(comparison['db_only'])}개 포지션 정리됨")
        except Exception as e:
            st.sidebar.error(f"자동 동기화 오류: {e}")
    
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
        
        # 거래 통계는 DB에서만 가져옴
        try:
            conn = sqlite3.connect('integrated_trades.db')
            
            # 완료된 거래 통계
            stats_query = """
            SELECT 
                COUNT(*) as total_trades,
                SUM(CASE WHEN is_win = 1 THEN 1 ELSE 0 END) as wins,
                SUM(pnl_usdt) as total_pnl,
                AVG(pnl_percent) as avg_pnl_percent
            FROM completed_trades
            WHERE close_timestamp >= date('now', '-30 days')
            """
            
            stats_df = pd.read_sql_query(stats_query, conn)
            
            if not stats_df.empty:
                stats = stats_df.iloc[0]
                
                # None 값 처리
                total_trades = int(stats['total_trades']) if pd.notna(stats['total_trades']) else 0
                wins = int(stats['wins']) if pd.notna(stats['wins']) else 0
                total_pnl = float(stats['total_pnl']) if pd.notna(stats['total_pnl']) else 0.0
                avg_pnl_percent = float(stats['avg_pnl_percent']) if pd.notna(stats['avg_pnl_percent']) else 0.0
                
                col1, col2, col3, col4 = st.columns(4)
                
                with col1:
                    st.metric("Total Trades (30d)", total_trades)
                
                with col2:
                    win_rate = (wins / total_trades * 100) if total_trades > 0 else 0
                    st.metric("Win Rate", f"{win_rate:.1f}%")
                
                with col3:
                    st.metric("Total PnL (30d)", f"${total_pnl:.2f}")
                
                with col4:
                    st.metric("Avg PnL %", f"{avg_pnl_percent:.2f}%")
            else:
                st.info("최근 30일간 완료된 거래가 없습니다.")
            
            conn.close()
            
        except Exception as e:
            st.error(f"통계 조회 오류: {e}")
    
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
