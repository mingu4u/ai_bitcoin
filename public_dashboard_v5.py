#!/usr/bin/env python3
"""
Public Dashboard v5 - Fixed Enhanced Version
실시간 포지션과 AI 모니터링 기록을 표시하는 개선된 버전

주요 개선사항:
1. 실시간 활성 포지션 표시
2. AI 모니터링 기록 표시
3. position_history 테이블 조회 추가
4. trades 테이블 조회 추가
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

# 페이지 설정
st.set_page_config(
    page_title="Trading Performance Dashboard v5 Enhanced",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# CSS 스타일
st.markdown("""
<style>
    /* 메인 헤더 */
    .main-header {
        font-size: 3rem;
        font-weight: bold;
        background: linear-gradient(120deg, #1f77b4, #2ca02c);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        text-align: center;
        margin-bottom: 1rem;
        padding: 1rem 0;
    }
    
    .sub-header {
        font-size: 1.2rem;
        color: #6c757d;
        text-align: center;
        margin-bottom: 2rem;
    }
    
    /* 메트릭 카드 */
    .metric-card {
        background: #f8f9fa;
        border-radius: 10px;
        padding: 1rem;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }
    
    /* AI 모니터링 스타일 */
    .ai-monitor-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        border-radius: 10px;
        padding: 1rem;
        margin: 0.5rem 0;
    }
    
    /* 포지션 카드 */
    .position-card {
        background: white;
        border-left: 4px solid #1f77b4;
        border-radius: 5px;
        padding: 1rem;
        margin: 0.5rem 0;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }
</style>
""", unsafe_allow_html=True)

@st.cache_data(ttl=10)
def get_active_positions_realtime():
    """실시간 활성 포지션 조회 - 새로운 함수"""
    try:
        conn = sqlite3.connect('integrated_trades.db')
        
        # 방법 1: position_history에서 최신 포지션 가져오기
        query1 = """
        WITH latest_positions AS (
            SELECT 
                symbol,
                MAX(timestamp) as latest_time
            FROM position_history
            WHERE DATE(timestamp) >= date('now', '-1 day')
            GROUP BY symbol
        )
        SELECT 
            ph.symbol,
            ph.side,
            ph.amount,
            ph.entry_price,
            ph.current_price,
            ph.pnl_usdt,
            ph.pnl_percent,
            ph.position_value,
            ph.timestamp
        FROM position_history ph
        INNER JOIN latest_positions lp 
            ON ph.symbol = lp.symbol 
            AND ph.timestamp = lp.latest_time
        WHERE ph.amount > 0
        ORDER BY ph.pnl_percent DESC
        """
        
        positions_df = pd.read_sql_query(query1, conn)
        
        # 방법 2: trades 테이블에서 활성 포지션 확인 (백업)
        if positions_df.empty:
            query2 = """
            SELECT DISTINCT
                symbol,
                action as side,
                entry_price,
                current_price,
                position_size as amount,
                timestamp
            FROM trades
            WHERE status = 'active'
            AND trade_type IN ('entry', 'manual')
            ORDER BY timestamp DESC
            """
            positions_df = pd.read_sql_query(query2, conn)
        
        conn.close()
        return positions_df
        
    except Exception as e:
        st.error(f"Error getting active positions: {e}")
        return pd.DataFrame()

@st.cache_data(ttl=30)
def get_ai_monitoring_history(days=7):
    """AI 모니터링 기록 조회 - 새로운 함수"""
    try:
        conn = sqlite3.connect('integrated_trades.db')
        
        cutoff_date = (datetime.now() - timedelta(days=days)).isoformat()
        
        query = """
        SELECT 
            timestamp,
            symbol,
            ai_decision,
            action,
            percentage,
            reason,
            entry_price,
            current_price,
            confidence,
            exit_type,
            urgency,
            ROUND(((current_price - entry_price) / entry_price * 100), 2) as price_change_pct
        FROM trades
        WHERE trade_type = 'AI_MONITOR'
        AND timestamp >= ?
        ORDER BY timestamp DESC
        LIMIT 100
        """
        
        df = pd.read_sql_query(query, conn, params=(cutoff_date,))
        
        # 타임스탬프 변환
        if not df.empty:
            df['timestamp'] = pd.to_datetime(df['timestamp'])
        
        conn.close()
        return df
        
    except Exception as e:
        st.error(f"Error getting AI monitoring history: {e}")
        return pd.DataFrame()

@st.cache_data(ttl=30)
def get_current_balance():
    """현재 잔고 조회 - 개선된 버전"""
    try:
        conn = sqlite3.connect('integrated_trades.db')
        
        # 잔고 정보
        balance_query = """
        SELECT 
            timestamp,
            total_balance,
            free_balance,
            used_balance,
            active_positions,
            total_position_value,
            total_pnl
        FROM balance_history
        ORDER BY timestamp DESC
        LIMIT 1
        """
        
        balance_result = pd.read_sql_query(balance_query, conn)
        
        # 실제 활성 포지션 수 계산 (position_history 기반)
        active_pos_query = """
        WITH latest_positions AS (
            SELECT 
                symbol,
                MAX(timestamp) as latest_time
            FROM position_history
            WHERE DATE(timestamp) >= date('now', '-1 day')
            GROUP BY symbol
        )
        SELECT COUNT(DISTINCT ph.symbol) as real_active_positions
        FROM position_history ph
        INNER JOIN latest_positions lp 
            ON ph.symbol = lp.symbol 
            AND ph.timestamp = lp.latest_time
        WHERE ph.amount > 0
        """
        
        active_pos_result = pd.read_sql_query(active_pos_query, conn)
        
        conn.close()
        
        if not balance_result.empty:
            balance_dict = balance_result.iloc[0].to_dict()
            # 실제 활성 포지션 수로 업데이트
            if not active_pos_result.empty:
                balance_dict['active_positions'] = active_pos_result.iloc[0]['real_active_positions']
            return balance_dict
        else:
            return {
                'total_balance': 0,
                'free_balance': 0,
                'used_balance': 0,
                'active_positions': 0,
                'total_position_value': 0,
                'total_pnl': 0
            }
            
    except Exception as e:
        st.error(f"Error getting current balance: {e}")
        return None

@st.cache_data(ttl=60)
def get_trading_statistics(days=None, symbol=None):
    """거래 통계 조회"""
    try:
        conn = sqlite3.connect('integrated_trades.db')
        
        query = "SELECT * FROM completed_trades WHERE 1=1"
        params = []
        
        if days:
            cutoff_date = (datetime.now() - timedelta(days=days)).isoformat()
            query += " AND open_timestamp >= ?"
            params.append(cutoff_date)
        
        if symbol:
            query += " AND symbol = ?"
            params.append(symbol)
        
        query += " ORDER BY close_timestamp DESC"
        
        df = pd.read_sql_query(query, conn, params=params)
        conn.close()
        
        if df.empty:
            return {
                'total_trades': 0,
                'winning_trades': 0,
                'losing_trades': 0,
                'win_rate': 0,
                'total_pnl': 0,
                'avg_pnl': 0,
                'best_trade': 0,
                'worst_trade': 0,
                'avg_win': 0,
                'avg_loss': 0,
                'profit_factor': 0,
                'max_win': 0,
                'max_loss': 0,
                'avg_holding_time': 0
            }
        
        # 통계 계산
        total_trades = len(df)
        winning_trades = len(df[df['is_win'] == 1])
        losing_trades = len(df[df['is_win'] == 0])
        win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
        
        total_pnl = df['pnl_usdt'].sum()
        avg_pnl = df['pnl_usdt'].mean()
        best_trade = df['pnl_usdt'].max()
        worst_trade = df['pnl_usdt'].min()
        
        wins_df = df[df['is_win'] == 1]
        losses_df = df[df['is_win'] == 0]
        
        avg_win = wins_df['pnl_usdt'].mean() if not wins_df.empty else 0
        avg_loss = losses_df['pnl_usdt'].mean() if not losses_df.empty else 0
        
        total_wins = wins_df['pnl_usdt'].sum() if not wins_df.empty else 0
        total_losses = abs(losses_df['pnl_usdt'].sum()) if not losses_df.empty else 1
        profit_factor = total_wins / total_losses if total_losses != 0 else 0
        
        max_win = wins_df['pnl_usdt'].max() if not wins_df.empty else 0
        max_loss = losses_df['pnl_usdt'].min() if not losses_df.empty else 0
        
        avg_holding_time = df['holding_time_minutes'].mean() if 'holding_time_minutes' in df.columns else 0
        
        return {
            'total_trades': total_trades,
            'winning_trades': winning_trades,
            'losing_trades': losing_trades,
            'win_rate': win_rate,
            'total_pnl': total_pnl,
            'avg_pnl': avg_pnl,
            'best_trade': best_trade,
            'worst_trade': worst_trade,
            'avg_win': avg_win,
            'avg_loss': avg_loss,
            'profit_factor': profit_factor,
            'max_win': max_win,
            'max_loss': max_loss,
            'avg_holding_time': avg_holding_time
        }
        
    except Exception as e:
        st.error(f"Error getting trading statistics: {e}")
        return {}

def display_active_positions(positions_df):
    """활성 포지션 표시 - 새로운 함수"""
    if positions_df.empty:
        st.info("현재 활성 포지션이 없습니다.")
        return
    
    st.subheader("📍 Active Positions (Real-time)")
    
    for idx, pos in positions_df.iterrows():
        col1, col2, col3, col4, col5 = st.columns([2, 1, 1, 1, 1])
        
        with col1:
            side_emoji = "🟢" if pos.get('side', '').lower() in ['buy', 'long'] else "🔴"
            st.markdown(f"**{side_emoji} {pos['symbol']}**")
        
        with col2:
            st.metric("Entry", f"${pos.get('entry_price', 0):.2f}")
        
        with col3:
            current_price = pos.get('current_price', pos.get('entry_price', 0))
            st.metric("Current", f"${current_price:.2f}")
        
        with col4:
            pnl_usdt = pos.get('pnl_usdt', 0)
            pnl_percent = pos.get('pnl_percent', 0)
            color = "green" if pnl_usdt >= 0 else "red"
            st.markdown(f"<span style='color:{color}'>PnL: ${pnl_usdt:.2f} ({pnl_percent:.2f}%)</span>", unsafe_allow_html=True)
        
        with col5:
            amount = pos.get('amount', 0)
            st.metric("Size", f"{amount:.4f}")

def display_ai_monitoring(ai_df):
    """AI 모니터링 기록 표시 - 새로운 함수"""
    if ai_df.empty:
        st.info("AI 모니터링 기록이 없습니다.")
        return
    
    st.subheader("🤖 AI Monitoring History")
    
    # 요약 통계
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        total_monitors = len(ai_df)
        st.metric("Total Monitors", total_monitors)
    
    with col2:
        hold_count = len(ai_df[ai_df['ai_decision'] == 'hold'])
        st.metric("Hold Decisions", hold_count)
    
    with col3:
        close_count = len(ai_df[ai_df['ai_decision'] == 'close'])
        st.metric("Close Decisions", close_count)
    
    with col4:
        avg_confidence = ai_df['confidence'].mean() * 100 if 'confidence' in ai_df.columns else 0
        st.metric("Avg Confidence", f"{avg_confidence:.1f}%")
    
    # 최근 모니터링 기록
    st.markdown("### Recent AI Decisions")
    
    # 테이블로 표시
    display_df = ai_df[['timestamp', 'symbol', 'ai_decision', 'confidence', 'urgency', 'reason']].head(20)
    
    # 신뢰도를 퍼센트로 변환
    if 'confidence' in display_df.columns:
        display_df['confidence'] = display_df['confidence'].apply(lambda x: f"{x*100:.1f}%" if pd.notna(x) else "N/A")
    
    # 타임스탬프 포맷
    if 'timestamp' in display_df.columns:
        display_df['timestamp'] = display_df['timestamp'].dt.strftime('%Y-%m-%d %H:%M')
    
    # 스타일 적용
    def highlight_decisions(row):
        if row['ai_decision'] == 'close':
            return ['background-color: #ffebee'] * len(row)
        elif row['ai_decision'] == 'partial_close':
            return ['background-color: #fff3e0'] * len(row)
        else:
            return ['background-color: #e8f5e9'] * len(row)
    
    styled_df = display_df.style.apply(highlight_decisions, axis=1)
    st.dataframe(styled_df, use_container_width=True, hide_index=True)

def plot_ai_monitoring_chart(ai_df):
    """AI 모니터링 차트 - 새로운 함수"""
    if ai_df.empty:
        return
    
    # AI 결정 분포
    fig = make_subplots(
        rows=1, cols=2,
        subplot_titles=('AI Decision Distribution', 'Confidence by Decision'),
        specs=[[{'type': 'pie'}, {'type': 'box'}]]
    )
    
    # Pie chart
    decision_counts = ai_df['ai_decision'].value_counts()
    fig.add_trace(
        go.Pie(
            labels=decision_counts.index,
            values=decision_counts.values,
            hole=0.3,
            marker_colors=['#2ecc71', '#e74c3c', '#f39c12']
        ),
        row=1, col=1
    )
    
    # Box plot
    for decision in ai_df['ai_decision'].unique():
        data = ai_df[ai_df['ai_decision'] == decision]['confidence'] * 100
        fig.add_trace(
            go.Box(
                y=data,
                name=decision,
                boxmean=True
            ),
            row=1, col=2
        )
    
    fig.update_layout(height=400, showlegend=True)
    st.plotly_chart(fig, use_container_width=True)

def main():
    """메인 대시보드"""
    
    # 헤더
    st.markdown('<div class="main-header">Trading Performance Dashboard v5</div>', 
                unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Enhanced with Real-time Positions & AI Monitoring</div>', 
                unsafe_allow_html=True)
    
    # 현재 잔고 표시
    balance = get_current_balance()
    if balance:
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("Total Balance", 
                     f"${balance.get('total_balance', 0):,.2f}",
                     f"{balance.get('total_pnl', 0):+,.2f}")
        
        with col2:
            st.metric("Free Balance", 
                     f"${balance.get('free_balance', 0):,.2f}")
        
        with col3:
            st.metric("Used Balance", 
                     f"${balance.get('used_balance', 0):,.2f}")
        
        with col4:
            # 실시간 활성 포지션 수 표시
            st.metric("Active Positions", 
                     f"{balance.get('active_positions', 0)}",
                     "Real-time")
    
    # 탭 생성
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "📊 Overview", 
        "📍 Active Positions", 
        "🤖 AI Monitoring", 
        "📈 Charts", 
        "📋 Trades"
    ])
    
    with tab1:
        # 거래 통계
        stats = get_trading_statistics()
        
        if stats:
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                st.metric("Total Trades", stats['total_trades'])
            
            with col2:
                win_rate = stats['win_rate']
                st.metric("Win Rate", f"{win_rate:.1f}%", 
                         delta=f"{win_rate-50:.1f}%" if win_rate != 0 else None)
            
            with col3:
                st.metric("Total PnL", f"${stats['total_pnl']:,.2f}")
            
            with col4:
                st.metric("Profit Factor", f"{stats['profit_factor']:.2f}")
            
            # 추가 통계
            st.markdown("---")
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                st.metric("Best Trade", f"${stats['best_trade']:,.2f}")
            
            with col2:
                st.metric("Worst Trade", f"${stats['worst_trade']:,.2f}")
            
            with col3:
                st.metric("Avg Win", f"${stats['avg_win']:,.2f}")
            
            with col4:
                st.metric("Avg Loss", f"${stats['avg_loss']:,.2f}")
    
    with tab2:
        # 실시간 활성 포지션
        st.header("Active Positions")
        
        # 새로고침 버튼
        if st.button("🔄 Refresh Positions"):
            st.cache_data.clear()
        
        positions_df = get_active_positions_realtime()
        display_active_positions(positions_df)
        
        if not positions_df.empty:
            # 포지션 요약
            st.markdown("---")
            st.subheader("Position Summary")
            
            col1, col2, col3 = st.columns(3)
            
            with col1:
                total_value = positions_df['position_value'].sum() if 'position_value' in positions_df.columns else 0
                st.metric("Total Position Value", f"${total_value:,.2f}")
            
            with col2:
                total_pnl = positions_df['pnl_usdt'].sum() if 'pnl_usdt' in positions_df.columns else 0
                st.metric("Total Unrealized PnL", f"${total_pnl:,.2f}")
            
            with col3:
                avg_pnl_pct = positions_df['pnl_percent'].mean() if 'pnl_percent' in positions_df.columns else 0
                st.metric("Avg PnL %", f"{avg_pnl_pct:.2f}%")
    
    with tab3:
        # AI 모니터링 기록
        st.header("AI Monitoring Dashboard")
        
        # 기간 선택
        days = st.slider("Days to show", 1, 30, 7)
        
        ai_history = get_ai_monitoring_history(days)
        
        # AI 모니터링 표시
        display_ai_monitoring(ai_history)
        
        # AI 모니터링 차트
        if not ai_history.empty:
            st.markdown("---")
            plot_ai_monitoring_chart(ai_history)
    
    with tab4:
        # 차트 (기존 코드 활용)
        st.header("Performance Charts")
        # ... 기존 차트 코드 ...
    
    with tab5:
        # 거래 내역 (기존 코드 활용)
        st.header("Trade History")
        # ... 기존 거래 내역 코드 ...
    
    # Footer
    st.markdown("---")
    st.caption(f"Dashboard Enhanced v5 | Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # 자동 새로고침 (선택사항)
    if st.sidebar.checkbox("Auto-refresh (10s)", value=False):
        st.experimental_rerun()

if __name__ == "__main__":
    main()
