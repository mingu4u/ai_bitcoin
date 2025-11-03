import streamlit as st
import sys
import os
from datetime import datetime, timedelta
import json
import requests
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
import sqlite3

# 서버 URL 설정
MAIN_SERVER_URL = "http://localhost:5000"

# 페이지 설정
st.set_page_config(
    page_title="통합 트레이딩 대시보드 v4",
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
        color: #1f77b4;
        text-align: center;
        margin-bottom: 2rem;
    }
    .metric-card {
        background-color: #f8f9fa;
        padding: 1.5rem;
        border-radius: 0.5rem;
        border: 1px solid #dee2e6;
        text-align: center;
    }
    .metric-value {
        font-size: 2rem;
        font-weight: bold;
        margin: 0.5rem 0;
    }
    .metric-label {
        font-size: 0.9rem;
        color: #6c757d;
    }
    .positive {
        color: #28a745;
    }
    .negative {
        color: #dc3545;
    }
    .stTabs [data-baseweb="tab-list"] button [data-testid="stMarkdownContainer"] p {
        font-size: 1.1rem;
    }
</style>
""", unsafe_allow_html=True)

# ============ Helper Functions ============
@st.cache_data(ttl=60)
def get_server_status():
    """서버 상태 조회"""
    try:
        response = requests.get(f"{MAIN_SERVER_URL}/status", timeout=5)
        if response.status_code == 200:
            return True, response.json()
        return False, None
    except:
        return False, None

@st.cache_data(ttl=30)
def get_trading_statistics(days=None, symbol=None):
    """거래 통계 조회"""
    try:
        params = {}
        if days:
            params['days'] = days
        if symbol:
            params['symbol'] = symbol
        
        response = requests.get(f"{MAIN_SERVER_URL}/statistics", params=params, timeout=10)
        if response.status_code == 200:
            return response.json()
        return {}
    except:
        return {}

@st.cache_data(ttl=30)
def get_balance_history(days=30):
    """자산 히스토리 조회"""
    try:
        response = requests.get(f"{MAIN_SERVER_URL}/balance/history", 
                              params={'days': days}, timeout=10)
        if response.status_code == 200:
            data = response.json()
            return pd.DataFrame(data)
        return pd.DataFrame()
    except:
        return pd.DataFrame()

@st.cache_data(ttl=30)
def get_symbol_performance():
    """심볼별 성과 조회"""
    try:
        response = requests.get(f"{MAIN_SERVER_URL}/statistics/symbols", timeout=10)
        if response.status_code == 200:
            data = response.json()
            return pd.DataFrame(data)
        return pd.DataFrame()
    except:
        return pd.DataFrame()

@st.cache_data(ttl=30)
def get_daily_pnl(days=30):
    """일별 PnL 조회"""
    try:
        response = requests.get(f"{MAIN_SERVER_URL}/statistics/daily", 
                              params={'days': days}, timeout=10)
        if response.status_code == 200:
            data = response.json()
            return pd.DataFrame(data)
        return pd.DataFrame()
    except:
        return pd.DataFrame()

@st.cache_data(ttl=30)
def get_completed_trades(limit=100):
    """완료된 거래 조회"""
    try:
        response = requests.get(f"{MAIN_SERVER_URL}/trades/completed", 
                              params={'limit': limit}, timeout=10)
        if response.status_code == 200:
            data = response.json()
            return pd.DataFrame(data)
        return pd.DataFrame()
    except:
        return pd.DataFrame()

# ============ Visualization Functions ============
def plot_balance_history(df):
    """자산 변화 그래프"""
    if df.empty:
        st.info("자산 히스토리 데이터가 없습니다.")
        return
    
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    
    fig = go.Figure()
    
    fig.add_trace(go.Scatter(
        x=df['timestamp'],
        y=df['total_equity'],
        mode='lines+markers',
        name='Total Equity',
        line=dict(color='#2196F3', width=3),
        marker=dict(size=6),
        hovertemplate='%{x}<br>Equity: $%{y:,.2f}<extra></extra>'
    ))
    
    # 시작 자산 라인 추가
    if not df.empty:
        initial_equity = df['total_equity'].iloc[0]
        fig.add_hline(y=initial_equity, line_dash="dash", line_color="gray",
                     annotation_text=f"Initial: ${initial_equity:,.2f}",
                     annotation_position="right")
    
    fig.update_layout(
        title='📈 Total Asset History',
        xaxis_title='Date',
        yaxis_title='Equity ($)',
        hovermode='x unified',
        height=400,
        showlegend=False
    )
    
    st.plotly_chart(fig, use_container_width=True)

def plot_daily_pnl(df):
    """일별 PnL 그래프"""
    if df.empty:
        st.info("일별 PnL 데이터가 없습니다.")
        return
    
    df['date'] = pd.to_datetime(df['date'])
    
    colors = ['#28a745' if x >= 0 else '#dc3545' for x in df['daily_pnl']]
    
    fig = go.Figure()
    
    fig.add_trace(go.Bar(
        x=df['date'],
        y=df['daily_pnl'],
        marker_color=colors,
        name='Daily PnL',
        hovertemplate='%{x}<br>PnL: $%{y:,.2f}<extra></extra>'
    ))
    
    fig.update_layout(
        title='📊 Daily PnL',
        xaxis_title='Date',
        yaxis_title='PnL ($)',
        hovermode='x unified',
        height=400,
        showlegend=False
    )
    
    st.plotly_chart(fig, use_container_width=True)

def plot_symbol_performance(df):
    """심볼별 성과 그래프"""
    if df.empty:
        st.info("심볼별 성과 데이터가 없습니다.")
        return
    
    # Top 10 by PnL
    df_sorted = df.sort_values('total_pnl', ascending=False).head(10)
    
    colors = ['#28a745' if x >= 0 else '#dc3545' for x in df_sorted['total_pnl']]
    
    fig = go.Figure()
    
    fig.add_trace(go.Bar(
        x=df_sorted['symbol'],
        y=df_sorted['total_pnl'],
        marker_color=colors,
        name='Total PnL',
        text=df_sorted['total_pnl'].apply(lambda x: f'${x:,.2f}'),
        textposition='outside',
        hovertemplate='%{x}<br>PnL: $%{y:,.2f}<br>Win Rate: %{customdata:.1f}%<extra></extra>',
        customdata=df_sorted['win_rate']
    ))
    
    fig.update_layout(
        title='🏆 Top 10 Symbols by PnL',
        xaxis_title='Symbol',
        yaxis_title='Total PnL ($)',
        height=400,
        showlegend=False
    )
    
    st.plotly_chart(fig, use_container_width=True)

def plot_winrate_distribution(df):
    """승률 분포 그래프"""
    if df.empty:
        st.info("승률 데이터가 없습니다.")
        return
    
    fig = go.Figure()
    
    fig.add_trace(go.Bar(
        x=df['symbol'],
        y=df['win_rate'],
        marker_color='#2196F3',
        name='Win Rate',
        text=df['win_rate'].apply(lambda x: f'{x:.1f}%'),
        textposition='outside',
        hovertemplate='%{x}<br>Win Rate: %{y:.1f}%<br>Trades: %{customdata}<extra></extra>',
        customdata=df['total_trades']
    ))
    
    # 50% 기준선
    fig.add_hline(y=50, line_dash="dash", line_color="red",
                 annotation_text="50%", annotation_position="right")
    
    fig.update_layout(
        title='📊 Win Rate by Symbol',
        xaxis_title='Symbol',
        yaxis_title='Win Rate (%)',
        height=400,
        showlegend=False
    )
    
    st.plotly_chart(fig, use_container_width=True)

def plot_pnl_distribution(df_trades):
    """PnL 분포 히스토그램"""
    if df_trades.empty:
        st.info("거래 데이터가 없습니다.")
        return
    
    fig = go.Figure()
    
    fig.add_trace(go.Histogram(
        x=df_trades['pnl_percent'],
        nbinsx=30,
        marker_color='#2196F3',
        name='PnL Distribution',
        hovertemplate='Return: %{x:.2f}%<br>Count: %{y}<extra></extra>'
    ))
    
    fig.update_layout(
        title='📉 PnL Distribution (% Returns)',
        xaxis_title='Return (%)',
        yaxis_title='Number of Trades',
        height=400,
        showlegend=False
    )
    
    st.plotly_chart(fig, use_container_width=True)

def plot_trade_timeline(df_trades):
    """거래 타임라인"""
    if df_trades.empty:
        st.info("거래 데이터가 없습니다.")
        return
    
    df_trades['exit_time'] = pd.to_datetime(df_trades['exit_time'])
    
    colors = ['#28a745' if x == 1 else '#dc3545' for x in df_trades['is_win']]
    
    fig = go.Figure()
    
    fig.add_trace(go.Scatter(
        x=df_trades['exit_time'],
        y=df_trades['pnl'],
        mode='markers',
        marker=dict(
            size=10,
            color=colors,
            line=dict(width=1, color='white')
        ),
        name='Trades',
        text=df_trades['symbol'],
        hovertemplate='%{text}<br>%{x}<br>PnL: $%{y:,.2f}<extra></extra>'
    ))
    
    fig.update_layout(
        title='📍 Trade Timeline',
        xaxis_title='Date',
        yaxis_title='PnL ($)',
        height=400,
        hovermode='closest'
    )
    
    st.plotly_chart(fig, use_container_width=True)

# ============ Main Dashboard ============
def main():
    st.markdown('<h1 class="main-header">📊 통합 트레이딩 대시보드 v4</h1>', 
                unsafe_allow_html=True)
    
    # 서버 상태 확인
    status_ok, server_data = get_server_status()
    
    if not status_ok:
        st.error("⚠️ 서버에 연결할 수 없습니다. 서버가 실행 중인지 확인하세요.")
        return
    
    # 사이드바
    with st.sidebar:
        st.header("⚙️ Settings")
        
        # 시간 범위 선택
        time_range = st.selectbox(
            "Time Range",
            options=[7, 14, 30, 60, 90],
            index=2,
            format_func=lambda x: f"Last {x} days"
        )
        
        # 새로고침 버튼
        if st.button("🔄 Refresh Data", use_container_width=True):
            st.cache_data.clear()
            st.rerun()
        
        st.divider()
        
        # 서버 정보
        st.subheader("🖥️ Server Status")
        if server_data:
            st.success("✅ Connected")
            st.metric("Port", server_data.get('server_port', 'N/A'))
            st.metric("Active Positions", server_data.get('position_count', 0))
            st.metric("AI Monitoring", 
                     "🟢 Active" if server_data.get('ai_monitoring_active') else "🔴 Inactive")
    
    # 메인 컨텐츠
    tabs = st.tabs(["📈 Overview", "📊 Statistics", "💰 Trades", "🎯 Performance"])
    
    # ============ Tab 1: Overview ============
    with tabs[0]:
        # 전체 통계
        stats = get_trading_statistics()
        
        if stats:
            # 메트릭 카드
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                total_pnl = stats.get('total_pnl', 0)
                pnl_class = "positive" if total_pnl >= 0 else "negative"
                st.markdown(f"""
                <div class="metric-card">
                    <div class="metric-label">Total PnL</div>
                    <div class="metric-value {pnl_class}">${total_pnl:,.2f}</div>
                </div>
                """, unsafe_allow_html=True)
            
            with col2:
                win_rate = stats.get('win_rate', 0)
                st.markdown(f"""
                <div class="metric-card">
                    <div class="metric-label">Win Rate</div>
                    <div class="metric-value">{win_rate:.1f}%</div>
                </div>
                """, unsafe_allow_html=True)
            
            with col3:
                total_trades = stats.get('total_trades', 0)
                st.markdown(f"""
                <div class="metric-card">
                    <div class="metric-label">Total Trades</div>
                    <div class="metric-value">{total_trades}</div>
                </div>
                """, unsafe_allow_html=True)
            
            with col4:
                profit_factor = stats.get('profit_factor', 0)
                st.markdown(f"""
                <div class="metric-card">
                    <div class="metric-label">Profit Factor</div>
                    <div class="metric-value">{profit_factor:.2f}</div>
                </div>
                """, unsafe_allow_html=True)
            
            st.divider()
            
            # 그래프
            col1, col2 = st.columns(2)
            
            with col1:
                # 자산 변화
                balance_df = get_balance_history(time_range)
                plot_balance_history(balance_df)
            
            with col2:
                # 일별 PnL
                daily_df = get_daily_pnl(time_range)
                plot_daily_pnl(daily_df)
        else:
            st.info("거래 통계 데이터가 없습니다.")
    
    # ============ Tab 2: Statistics ============
    with tabs[1]:
        st.header("📊 Detailed Statistics")
        
        # 심볼별 성과
        symbol_df = get_symbol_performance()
        
        if not symbol_df.empty:
            col1, col2 = st.columns(2)
            
            with col1:
                plot_symbol_performance(symbol_df)
            
            with col2:
                plot_winrate_distribution(symbol_df)
            
            st.divider()
            
            # 상세 테이블
            st.subheader("📋 Symbol Performance Table")
            
            # 스타일링
            styled_df = symbol_df.style.format({
                'total_pnl': '${:,.2f}',
                'avg_pnl': '${:,.2f}',
                'best_trade': '${:,.2f}',
                'worst_trade': '${:,.2f}',
                'win_rate': '{:.1f}%'
            }).background_gradient(
                subset=['total_pnl'], 
                cmap='RdYlGn', 
                vmin=-symbol_df['total_pnl'].abs().max(), 
                vmax=symbol_df['total_pnl'].abs().max()
            )
            
            st.dataframe(styled_df, use_container_width=True)
        else:
            st.info("심볼별 성과 데이터가 없습니다.")
        
        st.divider()
        
        # 통계 상세
        stats = get_trading_statistics(time_range)
        
        if stats and stats.get('total_trades', 0) > 0:
            col1, col2, col3 = st.columns(3)
            
            with col1:
                st.metric("Average PnL", f"${stats.get('avg_pnl', 0):,.2f}")
                st.metric("Average Win", f"${stats.get('avg_win', 0):,.2f}")
                st.metric("Average Loss", f"${stats.get('avg_loss', 0):,.2f}")
            
            with col2:
                st.metric("Max Win", f"${stats.get('max_win', 0):,.2f}")
                st.metric("Max Loss", f"${stats.get('max_loss', 0):,.2f}")
                st.metric("Profit Factor", f"{stats.get('profit_factor', 0):.2f}")
            
            with col3:
                st.metric("Winning Trades", stats.get('winning_trades', 0))
                st.metric("Losing Trades", stats.get('losing_trades', 0))
                st.metric("Avg Holding Time", f"{stats.get('avg_holding_time', 0):.0f} min")
    
    # ============ Tab 3: Trades ============
    with tabs[2]:
        st.header("💰 Trade History")
        
        trades_df = get_completed_trades(100)
        
        if not trades_df.empty:
            # PnL 분포
            col1, col2 = st.columns(2)
            
            with col1:
                plot_pnl_distribution(trades_df)
            
            with col2:
                plot_trade_timeline(trades_df)
            
            st.divider()
            
            # 거래 테이블
            st.subheader("📋 Recent Trades")
            
            # 데이터 준비
            display_df = trades_df[[
                'exit_time', 'symbol', 'side', 'entry_price', 'exit_price',
                'pnl', 'pnl_percent', 'holding_time_minutes', 'exit_reason'
            ]].copy()
            
            display_df.columns = [
                'Exit Time', 'Symbol', 'Side', 'Entry', 'Exit',
                'PnL ($)', 'PnL (%)', 'Time (min)', 'Exit Reason'
            ]
            
            # 스타일링
            def color_pnl(val):
                color = '#28a745' if val > 0 else '#dc3545'
                return f'color: {color}; font-weight: bold'
            
            styled_trades = display_df.style.format({
                'Entry': '${:,.2f}',
                'Exit': '${:,.2f}',
                'PnL ($)': '${:,.2f}',
                'PnL (%)': '{:+.2f}%',
                'Time (min)': '{:.0f}'
            }).applymap(color_pnl, subset=['PnL ($)', 'PnL (%)'])
            
            st.dataframe(styled_trades, use_container_width=True, height=400)
        else:
            st.info("거래 내역이 없습니다.")
    
    # ============ Tab 4: Performance ============
    with tabs[3]:
        st.header("🎯 Performance Analysis")
        
        stats_7d = get_trading_statistics(days=7)
        stats_30d = get_trading_statistics(days=30)
        stats_all = get_trading_statistics()
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.subheader("📅 Last 7 Days")
            if stats_7d and stats_7d.get('total_trades', 0) > 0:
                st.metric("Trades", stats_7d['total_trades'])
                st.metric("Win Rate", f"{stats_7d['win_rate']:.1f}%")
                pnl_7d = stats_7d['total_pnl']
                st.metric("PnL", f"${pnl_7d:,.2f}",
                         delta=f"{pnl_7d:+.2f}")
            else:
                st.info("No trades in last 7 days")
        
        with col2:
            st.subheader("📅 Last 30 Days")
            if stats_30d and stats_30d.get('total_trades', 0) > 0:
                st.metric("Trades", stats_30d['total_trades'])
                st.metric("Win Rate", f"{stats_30d['win_rate']:.1f}%")
                pnl_30d = stats_30d['total_pnl']
                st.metric("PnL", f"${pnl_30d:,.2f}",
                         delta=f"{pnl_30d:+.2f}")
            else:
                st.info("No trades in last 30 days")
        
        with col3:
            st.subheader("📅 All Time")
            if stats_all and stats_all.get('total_trades', 0) > 0:
                st.metric("Trades", stats_all['total_trades'])
                st.metric("Win Rate", f"{stats_all['win_rate']:.1f}%")
                pnl_all = stats_all['total_pnl']
                st.metric("PnL", f"${pnl_all:,.2f}",
                         delta=f"{pnl_all:+.2f}")
            else:
                st.info("No trades yet")
        
        st.divider()
        
        # 월별 성과
        st.subheader("📊 Monthly Performance")
        
        trades_df = get_completed_trades(1000)
        if not trades_df.empty:
            trades_df['exit_time'] = pd.to_datetime(trades_df['exit_time'])
            trades_df['month'] = trades_df['exit_time'].dt.to_period('M')
            
            monthly_stats = trades_df.groupby('month').agg({
                'pnl': ['sum', 'count', 'mean'],
                'is_win': 'sum'
            }).reset_index()
            
            monthly_stats.columns = ['Month', 'Total PnL', 'Trades', 'Avg PnL', 'Wins']
            monthly_stats['Win Rate'] = (monthly_stats['Wins'] / monthly_stats['Trades'] * 100).round(1)
            monthly_stats['Month'] = monthly_stats['Month'].astype(str)
            
            st.dataframe(
                monthly_stats.style.format({
                    'Total PnL': '${:,.2f}',
                    'Avg PnL': '${:,.2f}',
                    'Win Rate': '{:.1f}%'
                }),
                use_container_width=True
            )

if __name__ == "__main__":
    main()
