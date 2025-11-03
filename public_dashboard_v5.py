#!/usr/bin/env python3
"""
Public Dashboard v5 - Fixed Version
v5 봇의 DB 스키마와 호환되도록 수정된 버전

주요 변경사항:
1. entry_time → open_timestamp
2. exit_time → close_timestamp
3. pnl → pnl_usdt
4. total_equity → total_balance
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
    page_title="Trading Performance Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# CSS 스타일 (원본과 동일)
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
    
    /* 메트릭 카드 스타일들... (원본과 동일) */
</style>
""", unsafe_allow_html=True)

@st.cache_data(ttl=30)
def get_current_balance():
    """현재 잔고 조회 - 수정된 버전"""
    try:
        conn = sqlite3.connect('integrated_trades.db')
        
        # 가장 최근의 잔고 정보 가져오기
        query = """
        SELECT 
            timestamp,
            total_balance,  -- total_equity 대신 total_balance 사용
            free_balance,
            used_balance,
            active_positions,
            total_position_value,
            total_pnl
        FROM balance_history
        ORDER BY timestamp DESC
        LIMIT 1
        """
        
        result = pd.read_sql_query(query, conn)
        conn.close()
        
        if not result.empty:
            return result.iloc[0].to_dict()
        else:
            # 기본값 반환
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
    """거래 통계 조회 - 수정된 버전"""
    try:
        conn = sqlite3.connect('integrated_trades.db')
        
        query = "SELECT * FROM completed_trades WHERE 1=1"
        params = []
        
        if days:
            cutoff_date = (datetime.now() - timedelta(days=days)).isoformat()
            query += " AND open_timestamp >= ?"  # entry_time 대신 open_timestamp
            params.append(cutoff_date)
        
        if symbol:
            query += " AND symbol = ?"
            params.append(symbol)
        
        query += " ORDER BY close_timestamp DESC"  # exit_time 대신 close_timestamp
        
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
        
        # pnl_usdt 사용 (pnl 대신)
        total_pnl = df['pnl_usdt'].sum()
        avg_pnl = df['pnl_usdt'].mean()
        best_trade = df['pnl_usdt'].max()
        worst_trade = df['pnl_usdt'].min()
        
        # 승/패 평균
        wins_df = df[df['is_win'] == 1]
        losses_df = df[df['is_win'] == 0]
        
        avg_win = wins_df['pnl_usdt'].mean() if not wins_df.empty else 0
        avg_loss = losses_df['pnl_usdt'].mean() if not losses_df.empty else 0
        
        # Profit Factor
        total_wins = wins_df['pnl_usdt'].sum() if not wins_df.empty else 0
        total_losses = abs(losses_df['pnl_usdt'].sum()) if not losses_df.empty else 1
        profit_factor = total_wins / total_losses if total_losses != 0 else 0
        
        # 최대 승/패
        max_win = wins_df['pnl_usdt'].max() if not wins_df.empty else 0
        max_loss = losses_df['pnl_usdt'].min() if not losses_df.empty else 0
        
        # 평균 보유 시간
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

@st.cache_data(ttl=30)
def get_balance_history(days=30):
    """자산 히스토리 조회 - 수정된 버전"""
    try:
        conn = sqlite3.connect('integrated_trades.db')
        
        cutoff_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
        
        # v5 봇의 실제 컬럼 사용
        query = """
        SELECT 
            timestamp,
            total_balance as total_equity,  -- 별칭 사용
            total_pnl,
            free_balance,
            used_balance,
            active_positions,
            total_position_value
        FROM balance_history
        WHERE DATE(timestamp) >= ?
        ORDER BY timestamp ASC
        """
        
        df = pd.read_sql_query(query, conn, params=(cutoff_date,))
        
        # daily_pnl과 daily_pnl_percent 계산
        if not df.empty:
            df['daily_pnl'] = df['total_pnl'].diff()
            df['daily_pnl_percent'] = (df['daily_pnl'] / df['total_equity'].shift(1) * 100).fillna(0)
            df['unrealized_pnl'] = 0  # 실시간 계산 필요
        
        conn.close()
        
        return df
        
    except Exception as e:
        st.error(f"Error getting balance history: {e}")
        return pd.DataFrame()

@st.cache_data(ttl=30)
def get_daily_pnl(days=30):
    """일별 손익 조회 - 수정된 버전"""
    try:
        conn = sqlite3.connect('integrated_trades.db')
        
        cutoff_date = (datetime.now() - timedelta(days=days)).isoformat()
        
        # close_timestamp 사용
        query = """
        SELECT 
            DATE(close_timestamp) as date,
            COUNT(*) as trades,
            SUM(CASE WHEN is_win = 1 THEN 1 ELSE 0 END) as wins,
            ROUND(SUM(pnl_usdt), 2) as daily_pnl,
            ROUND(SUM(CASE WHEN is_win = 1 THEN pnl_usdt ELSE 0 END), 2) as win_pnl,
            ROUND(SUM(CASE WHEN is_win = 0 THEN pnl_usdt ELSE 0 END), 2) as loss_pnl
        FROM completed_trades
        WHERE close_timestamp >= ?
        GROUP BY DATE(close_timestamp)
        ORDER BY date DESC
        """
        
        df = pd.read_sql_query(query, conn, params=(cutoff_date,))
        conn.close()
        
        return df
        
    except Exception as e:
        st.error(f"Error getting daily PnL: {e}")
        return pd.DataFrame()

@st.cache_data(ttl=30)
def get_completed_trades(limit=100):
    """완료된 거래 조회 - 수정된 버전"""
    try:
        conn = sqlite3.connect('integrated_trades.db')
        
        # v5 봇 스키마에 맞춰 조회
        query = """
        SELECT 
            *,
            open_timestamp as entry_time,
            close_timestamp as exit_time,
            pnl_usdt as pnl
        FROM completed_trades
        ORDER BY close_timestamp DESC
        LIMIT ?
        """
        
        df = pd.read_sql_query(query, conn, params=(limit,))
        conn.close()
        
        # 타임스탬프 변환
        if not df.empty:
            df['exit_time'] = pd.to_datetime(df['exit_time'])
            df['entry_time'] = pd.to_datetime(df['entry_time'])
        
        return df
        
    except Exception as e:
        st.error(f"Error getting completed trades: {e}")
        return pd.DataFrame()

# ... 나머지 함수들도 동일한 방식으로 수정 ...

def main():
    """메인 대시보드"""
    
    # 헤더
    st.markdown('<div class="main-header">Trading Performance Dashboard v5</div>', 
                unsafe_allow_html=True)
    st.markdown('<div class="sub-header">v5 봇 호환 버전</div>', 
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
            st.metric("Active Positions", 
                     f"{balance.get('active_positions', 0)}")
    
    # 탭 생성
    tab1, tab2, tab3, tab4 = st.tabs(["📊 Overview", "📈 Charts", "📋 Trades", "⚙️ Settings"])
    
    with tab1:
        # 거래 통계
        stats = get_trading_statistics()
        
        if stats:
            # 주요 지표 카드
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                st.metric("Total Trades", stats['total_trades'])
            
            with col2:
                win_rate = stats['win_rate']
                color = "green" if win_rate >= 50 else "red"
                st.metric("Win Rate", f"{win_rate:.1f}%")
            
            with col3:
                st.metric("Total PnL", f"${stats['total_pnl']:,.2f}")
            
            with col4:
                st.metric("Profit Factor", f"{stats['profit_factor']:.2f}")
    
    # ... 나머지 UI 코드 ...
    
    st.markdown("---")
    st.caption("Dashboard Fixed for v5 Bot Compatibility")

if __name__ == "__main__":
    main()
