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
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 1.5rem;
        border-radius: 1rem;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
        text-align: center;
        color: white;
        transition: transform 0.2s;
    }
    
    .metric-card:hover {
        transform: translateY(-5px);
        box-shadow: 0 8px 12px rgba(0, 0, 0, 0.15);
    }
    
    .metric-card.green {
        background: linear-gradient(135deg, #11998e 0%, #38ef7d 100%);
    }
    
    .metric-card.red {
        background: linear-gradient(135deg, #eb3349 0%, #f45c43 100%);
    }
    
    .metric-card.blue {
        background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%);
    }
    
    .metric-card.orange {
        background: linear-gradient(135deg, #fa709a 0%, #fee140 100%);
    }
    
    .metric-value {
        font-size: 2.5rem;
        font-weight: bold;
        margin: 0.5rem 0;
    }
    
    .metric-label {
        font-size: 1rem;
        opacity: 0.9;
        text-transform: uppercase;
        letter-spacing: 1px;
    }
    
    /* 통계 카드 */
    .stat-card {
        background-color: #ffffff;
        padding: 1.2rem;
        border-radius: 0.8rem;
        border: 2px solid #e9ecef;
        text-align: center;
        box-shadow: 0 2px 4px rgba(0, 0, 0, 0.05);
    }
    
    .stat-value {
        font-size: 1.8rem;
        font-weight: bold;
        color: #212529;
        margin: 0.3rem 0;
    }
    
    .stat-label {
        font-size: 0.85rem;
        color: #6c757d;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }
    
    .positive {
        color: #28a745;
    }
    
    .negative {
        color: #dc3545;
    }
    
    /* 리더보드 */
    .leaderboard-item {
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 1rem;
        margin: 0.5rem 0;
        background-color: #f8f9fa;
        border-radius: 0.5rem;
        border-left: 4px solid #1f77b4;
        transition: all 0.2s;
    }
    
    .leaderboard-item:hover {
        background-color: #e9ecef;
        transform: translateX(5px);
    }
    
    .leaderboard-rank {
        font-size: 1.5rem;
        font-weight: bold;
        color: #1f77b4;
        min-width: 50px;
    }
    
    .leaderboard-symbol {
        font-size: 1.2rem;
        font-weight: 600;
        flex: 1;
    }
    
    .leaderboard-pnl {
        font-size: 1.2rem;
        font-weight: bold;
        min-width: 120px;
        text-align: right;
    }
    
    /* 탭 스타일 */
    .stTabs [data-baseweb="tab-list"] button [data-testid="stMarkdownContainer"] p {
        font-size: 1.1rem;
        font-weight: 600;
    }
    
    /* 데이터프레임 */
    .dataframe {
        font-size: 0.9rem;
    }
    
    /* 업데이트 시간 */
    .update-time {
        text-align: center;
        color: #6c757d;
        font-size: 0.85rem;
        margin-top: 2rem;
        padding: 1rem;
        background-color: #f8f9fa;
        border-radius: 0.5rem;
    }
</style>
""", unsafe_allow_html=True)

# ============ Database Functions ============
@st.cache_data(ttl=30)
def get_trading_statistics(days=None, symbol=None):
    """거래 통계 조회"""
    try:
        conn = sqlite3.connect('integrated_trades.db')
        
        query = "SELECT * FROM completed_trades WHERE 1=1"
        params = []
        
        if days:
            cutoff_date = (datetime.now() - timedelta(days=days)).isoformat()
            query += " AND entry_time >= ?"
            params.append(cutoff_date)
        
        if symbol:
            query += " AND symbol = ?"
            params.append(symbol)
        
        query += " ORDER BY exit_time DESC"
        
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
                'avg_win': 0,
                'avg_loss': 0,
                'profit_factor': 0,
                'max_win': 0,
                'max_loss': 0,
                'avg_holding_time': 0
            }
        
        total_trades = len(df)
        winning_trades = len(df[df['is_win'] == 1])
        losing_trades = len(df[df['is_win'] == 0])
        win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
        
        total_pnl = df['pnl'].sum()
        avg_pnl = df['pnl'].mean()
        
        wins_df = df[df['is_win'] == 1]
        losses_df = df[df['is_win'] == 0]
        
        avg_win = wins_df['pnl'].mean() if not wins_df.empty else 0
        avg_loss = losses_df['pnl'].mean() if not losses_df.empty else 0
        
        total_wins = wins_df['pnl'].sum() if not wins_df.empty else 0
        total_losses = abs(losses_df['pnl'].sum()) if not losses_df.empty else 0
        profit_factor = (total_wins / total_losses) if total_losses > 0 else 0
        
        max_win = df['pnl'].max()
        max_loss = df['pnl'].min()
        avg_holding_time = df['holding_time_minutes'].mean()
        
        return {
            'total_trades': total_trades,
            'winning_trades': winning_trades,
            'losing_trades': losing_trades,
            'win_rate': win_rate,
            'total_pnl': total_pnl,
            'avg_pnl': avg_pnl,
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
    """자산 히스토리 조회"""
    try:
        conn = sqlite3.connect('integrated_trades.db')
        
        cutoff_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
        
        query = """
        SELECT 
            timestamp,
            total_equity,
            unrealized_pnl,
            daily_pnl,
            daily_pnl_percent
        FROM balance_history
        WHERE DATE(timestamp) >= ?
        ORDER BY timestamp ASC
        """
        
        df = pd.read_sql_query(query, conn, params=(cutoff_date,))
        conn.close()
        
        return df
        
    except Exception as e:
        st.error(f"Error getting balance history: {e}")
        return pd.DataFrame()

@st.cache_data(ttl=30)
def get_symbol_performance():
    """심볼별 성과 조회"""
    try:
        conn = sqlite3.connect('integrated_trades.db')
        
        query = """
        SELECT 
            symbol,
            COUNT(*) as total_trades,
            SUM(CASE WHEN is_win = 1 THEN 1 ELSE 0 END) as wins,
            SUM(CASE WHEN is_win = 0 THEN 1 ELSE 0 END) as losses,
            ROUND(SUM(CASE WHEN is_win = 1 THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2) as win_rate,
            ROUND(SUM(pnl), 2) as total_pnl,
            ROUND(AVG(pnl), 2) as avg_pnl,
            ROUND(MAX(pnl), 2) as best_trade,
            ROUND(MIN(pnl), 2) as worst_trade
        FROM completed_trades
        GROUP BY symbol
        ORDER BY total_pnl DESC
        """
        
        df = pd.read_sql_query(query, conn)
        conn.close()
        
        return df
        
    except Exception as e:
        st.error(f"Error getting symbol performance: {e}")
        return pd.DataFrame()

@st.cache_data(ttl=30)
def get_daily_pnl(days=30):
    """일별 손익 조회"""
    try:
        conn = sqlite3.connect('integrated_trades.db')
        
        cutoff_date = (datetime.now() - timedelta(days=days)).isoformat()
        
        query = """
        SELECT 
            DATE(exit_time) as date,
            COUNT(*) as trades,
            SUM(CASE WHEN is_win = 1 THEN 1 ELSE 0 END) as wins,
            ROUND(SUM(pnl), 2) as daily_pnl,
            ROUND(SUM(CASE WHEN is_win = 1 THEN pnl ELSE 0 END), 2) as win_pnl,
            ROUND(SUM(CASE WHEN is_win = 0 THEN pnl ELSE 0 END), 2) as loss_pnl
        FROM completed_trades
        WHERE exit_time >= ?
        GROUP BY DATE(exit_time)
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
    """완료된 거래 조회"""
    try:
        conn = sqlite3.connect('integrated_trades.db')
        
        query = f"""
        SELECT * FROM completed_trades
        ORDER BY exit_time DESC
        LIMIT {limit}
        """
        
        df = pd.read_sql_query(query, conn)
        conn.close()
        
        return df
        
    except Exception as e:
        st.error(f"Error getting completed trades: {e}")
        return pd.DataFrame()

@st.cache_data(ttl=60)
def get_current_balance():
    """현재 자산 조회"""
    try:
        conn = sqlite3.connect('integrated_trades.db')
        c = conn.cursor()
        
        c.execute("""
            SELECT total_equity, unrealized_pnl, daily_pnl, daily_pnl_percent
            FROM balance_history
            ORDER BY timestamp DESC
            LIMIT 1
        """)
        
        row = c.fetchone()
        conn.close()
        
        if row:
            return {
                'total_equity': row[0],
                'unrealized_pnl': row[1],
                'daily_pnl': row[2],
                'daily_pnl_percent': row[3]
            }
        return None
        
    except Exception as e:
        st.error(f"Error getting current balance: {e}")
        return None

# ============ Visualization Functions ============
def plot_balance_history(df):
    """자산 변화 그래프"""
    if df.empty:
        st.info("📊 자산 히스토리 데이터가 없습니다.")
        return
    
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    
    fig = go.Figure()
    
    # 자산 변화 라인
    fig.add_trace(go.Scatter(
        x=df['timestamp'],
        y=df['total_equity'],
        mode='lines+markers',
        name='Total Equity',
        line=dict(color='#2196F3', width=3),
        marker=dict(size=6, color='#2196F3'),
        fill='tozeroy',
        fillcolor='rgba(33, 150, 243, 0.1)',
        hovertemplate='<b>%{x|%Y-%m-%d %H:%M}</b><br>Equity: $%{y:,.2f}<extra></extra>'
    ))
    
    # 시작 자산 라인
    if not df.empty:
        initial_equity = df['total_equity'].iloc[0]
        current_equity = df['total_equity'].iloc[-1]
        pnl_percent = ((current_equity - initial_equity) / initial_equity * 100) if initial_equity > 0 else 0
        
        fig.add_hline(
            y=initial_equity, 
            line_dash="dash", 
            line_color="gray",
            annotation_text=f"Initial: ${initial_equity:,.2f}",
            annotation_position="left"
        )
        
        # 수익률 표시
        fig.add_annotation(
            x=df['timestamp'].iloc[-1],
            y=current_equity,
            text=f"<b>{pnl_percent:+.2f}%</b>",
            showarrow=True,
            arrowhead=2,
            arrowsize=1,
            arrowwidth=2,
            arrowcolor="#2196F3",
            bgcolor="white",
            bordercolor="#2196F3",
            borderwidth=2,
            font=dict(size=14, color="#2196F3")
        )
    
    fig.update_layout(
        title={
            'text': '📈 Total Asset History',
            'font': {'size': 20, 'color': '#1f77b4'}
        },
        xaxis_title='Date',
        yaxis_title='Equity ($)',
        hovermode='x unified',
        height=450,
        showlegend=False,
        plot_bgcolor='white',
        paper_bgcolor='white',
        xaxis=dict(showgrid=True, gridcolor='#e9ecef'),
        yaxis=dict(showgrid=True, gridcolor='#e9ecef')
    )
    
    st.plotly_chart(fig, use_container_width=True)

def plot_daily_pnl(df):
    """일별 PnL 그래프"""
    if df.empty:
        st.info("📊 일별 PnL 데이터가 없습니다.")
        return
    
    df['date'] = pd.to_datetime(df['date'])
    
    colors = ['#28a745' if x >= 0 else '#dc3545' for x in df['daily_pnl']]
    
    fig = go.Figure()
    
    fig.add_trace(go.Bar(
        x=df['date'],
        y=df['daily_pnl'],
        marker_color=colors,
        name='Daily PnL',
        text=df['daily_pnl'].apply(lambda x: f'${x:,.0f}'),
        textposition='outside',
        hovertemplate='<b>%{x|%Y-%m-%d}</b><br>PnL: $%{y:,.2f}<br>Trades: %{customdata}<extra></extra>',
        customdata=df['trades']
    ))
    
    fig.update_layout(
        title={
            'text': '📊 Daily PnL',
            'font': {'size': 20, 'color': '#1f77b4'}
        },
        xaxis_title='Date',
        yaxis_title='PnL ($)',
        hovermode='x unified',
        height=450,
        showlegend=False,
        plot_bgcolor='white',
        paper_bgcolor='white',
        xaxis=dict(showgrid=True, gridcolor='#e9ecef'),
        yaxis=dict(showgrid=True, gridcolor='#e9ecef', zeroline=True, zerolinecolor='black', zerolinewidth=2)
    )
    
    st.plotly_chart(fig, use_container_width=True)

def plot_symbol_performance(df, top_n=10):
    """심볼별 성과 그래프"""
    if df.empty:
        st.info("📊 심볼별 성과 데이터가 없습니다.")
        return
    
    df_sorted = df.sort_values('total_pnl', ascending=False).head(top_n)
    
    colors = ['#28a745' if x >= 0 else '#dc3545' for x in df_sorted['total_pnl']]
    
    fig = go.Figure()
    
    fig.add_trace(go.Bar(
        x=df_sorted['symbol'],
        y=df_sorted['total_pnl'],
        marker_color=colors,
        name='Total PnL',
        text=df_sorted['total_pnl'].apply(lambda x: f'${x:,.0f}'),
        textposition='outside',
        hovertemplate='<b>%{x}</b><br>PnL: $%{y:,.2f}<br>Win Rate: %{customdata:.1f}%<br>Trades: %{text}<extra></extra>',
        customdata=df_sorted['win_rate'],
        texttemplate='',
    ))
    
    # 거래 수 추가 정보
    for i, row in df_sorted.iterrows():
        fig.add_annotation(
            x=row['symbol'],
            y=row['total_pnl'],
            text=f"{row['total_trades']} trades",
            showarrow=False,
            yshift=20 if row['total_pnl'] > 0 else -20,
            font=dict(size=10, color='gray')
        )
    
    fig.update_layout(
        title={
            'text': f'🏆 Top {top_n} Symbols by PnL',
            'font': {'size': 20, 'color': '#1f77b4'}
        },
        xaxis_title='Symbol',
        yaxis_title='Total PnL ($)',
        height=450,
        showlegend=False,
        plot_bgcolor='white',
        paper_bgcolor='white',
        xaxis=dict(showgrid=False),
        yaxis=dict(showgrid=True, gridcolor='#e9ecef', zeroline=True, zerolinecolor='black', zerolinewidth=2)
    )
    
    st.plotly_chart(fig, use_container_width=True)

def plot_winrate_distribution(df):
    """승률 분포 그래프"""
    if df.empty:
        st.info("📊 승률 데이터가 없습니다.")
        return
    
    # 승률 구간별로 그룹화
    bins = [0, 30, 40, 50, 60, 70, 100]
    labels = ['0-30%', '30-40%', '40-50%', '50-60%', '60-70%', '70-100%']
    df['win_rate_group'] = pd.cut(df['win_rate'], bins=bins, labels=labels, include_lowest=True)
    
    dist = df.groupby('win_rate_group', observed=True).size().reset_index(name='count')
    
    colors_map = {
        '0-30%': '#dc3545',
        '30-40%': '#fd7e14',
        '40-50%': '#ffc107',
        '50-60%': '#20c997',
        '60-70%': '#28a745',
        '70-100%': '#007bff'
    }
    
    colors = [colors_map.get(x, '#6c757d') for x in dist['win_rate_group']]
    
    fig = go.Figure()
    
    fig.add_trace(go.Bar(
        x=dist['win_rate_group'],
        y=dist['count'],
        marker_color=colors,
        name='Symbols',
        text=dist['count'],
        textposition='outside',
        hovertemplate='<b>%{x}</b><br>Symbols: %{y}<extra></extra>'
    ))
    
    fig.update_layout(
        title={
            'text': '📊 Win Rate Distribution',
            'font': {'size': 20, 'color': '#1f77b4'}
        },
        xaxis_title='Win Rate Range',
        yaxis_title='Number of Symbols',
        height=450,
        showlegend=False,
        plot_bgcolor='white',
        paper_bgcolor='white',
        xaxis=dict(showgrid=False),
        yaxis=dict(showgrid=True, gridcolor='#e9ecef')
    )
    
    st.plotly_chart(fig, use_container_width=True)

def plot_pnl_distribution(df):
    """PnL 분포 그래프"""
    if df.empty:
        st.info("📊 PnL 분포 데이터가 없습니다.")
        return
    
    wins = df[df['is_win'] == 1]['pnl']
    losses = df[df['is_win'] == 0]['pnl']
    
    fig = go.Figure()
    
    fig.add_trace(go.Histogram(
        x=wins,
        name='Wins',
        marker_color='#28a745',
        opacity=0.7,
        nbinsx=30,
        hovertemplate='PnL: $%{x:,.2f}<br>Count: %{y}<extra></extra>'
    ))
    
    fig.add_trace(go.Histogram(
        x=losses,
        name='Losses',
        marker_color='#dc3545',
        opacity=0.7,
        nbinsx=30,
        hovertemplate='PnL: $%{x:,.2f}<br>Count: %{y}<extra></extra>'
    ))
    
    fig.update_layout(
        title={
            'text': '📊 PnL Distribution',
            'font': {'size': 20, 'color': '#1f77b4'}
        },
        xaxis_title='PnL ($)',
        yaxis_title='Frequency',
        height=400,
        barmode='overlay',
        plot_bgcolor='white',
        paper_bgcolor='white',
        xaxis=dict(showgrid=True, gridcolor='#e9ecef', zeroline=True, zerolinecolor='black'),
        yaxis=dict(showgrid=True, gridcolor='#e9ecef'),
        legend=dict(x=0.02, y=0.98)
    )
    
    st.plotly_chart(fig, use_container_width=True)

def plot_cumulative_pnl(df):
    """누적 PnL 그래프"""
    if df.empty:
        st.info("📊 누적 PnL 데이터가 없습니다.")
        return
    
    df = df.sort_values('exit_time')
    df['exit_time'] = pd.to_datetime(df['exit_time'])
    df['cumulative_pnl'] = df['pnl'].cumsum()
    
    fig = go.Figure()
    
    # 누적 PnL 라인
    fig.add_trace(go.Scatter(
        x=df['exit_time'],
        y=df['cumulative_pnl'],
        mode='lines',
        name='Cumulative PnL',
        line=dict(color='#2196F3', width=3),
        fill='tozeroy',
        fillcolor='rgba(33, 150, 243, 0.1)',
        hovertemplate='<b>%{x|%Y-%m-%d %H:%M}</b><br>Cumulative: $%{y:,.2f}<extra></extra>'
    ))
    
    # 거래 포인트
    colors = ['#28a745' if x == 1 else '#dc3545' for x in df['is_win']]
    
    fig.add_trace(go.Scatter(
        x=df['exit_time'],
        y=df['cumulative_pnl'],
        mode='markers',
        name='Trades',
        marker=dict(size=8, color=colors, line=dict(width=1, color='white')),
        hovertemplate='<b>%{x|%Y-%m-%d %H:%M}</b><br>Trade PnL: $%{customdata:,.2f}<br>Cumulative: $%{y:,.2f}<extra></extra>',
        customdata=df['pnl']
    ))
    
    fig.update_layout(
        title={
            'text': '📈 Cumulative PnL Over Time',
            'font': {'size': 20, 'color': '#1f77b4'}
        },
        xaxis_title='Date',
        yaxis_title='Cumulative PnL ($)',
        hovermode='closest',
        height=450,
        showlegend=False,
        plot_bgcolor='white',
        paper_bgcolor='white',
        xaxis=dict(showgrid=True, gridcolor='#e9ecef'),
        yaxis=dict(showgrid=True, gridcolor='#e9ecef', zeroline=True, zerolinecolor='black', zerolinewidth=2)
    )
    
    st.plotly_chart(fig, use_container_width=True)

# ============ Main Application ============
def main():
    # 헤더
    st.markdown('<div class="main-header">🚀 Trading Performance Dashboard</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Real-time Trading Statistics & Analytics</div>', unsafe_allow_html=True)
    
    # 현재 자산 정보
    current_balance = get_current_balance()
    
    if current_balance:
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            equity = current_balance['total_equity']
            st.markdown(f"""
            <div class="metric-card blue">
                <div class="metric-label">Total Equity</div>
                <div class="metric-value">${equity:,.2f}</div>
            </div>
            """, unsafe_allow_html=True)
        
        with col2:
            unrealized = current_balance['unrealized_pnl']
            color_class = "green" if unrealized >= 0 else "red"
            st.markdown(f"""
            <div class="metric-card {color_class}">
                <div class="metric-label">Unrealized PnL</div>
                <div class="metric-value">${unrealized:+,.2f}</div>
            </div>
            """, unsafe_allow_html=True)
        
        with col3:
            daily_pnl = current_balance['daily_pnl']
            color_class = "green" if daily_pnl >= 0 else "red"
            st.markdown(f"""
            <div class="metric-card {color_class}">
                <div class="metric-label">Daily PnL</div>
                <div class="metric-value">${daily_pnl:+,.2f}</div>
            </div>
            """, unsafe_allow_html=True)
        
        with col4:
            daily_pnl_pct = current_balance['daily_pnl_percent']
            color_class = "green" if daily_pnl_pct >= 0 else "red"
            st.markdown(f"""
            <div class="metric-card {color_class}">
                <div class="metric-label">Daily Return</div>
                <div class="metric-value">{daily_pnl_pct:+.2f}%</div>
            </div>
            """, unsafe_allow_html=True)
        
        st.divider()
    
    # 기간 선택
    col1, col2, col3 = st.columns([2, 2, 6])
    
    with col1:
        time_range = st.selectbox(
            "📅 Time Range",
            options=[7, 14, 30, 60, 90],
            index=2,
            format_func=lambda x: f"Last {x} days"
        )
    
    with col2:
        if st.button("🔄 Refresh Data", use_container_width=True):
            st.cache_data.clear()
            st.rerun()
    
    st.divider()
    
    # 전체 통계
    stats = get_trading_statistics(days=time_range)
    
    if stats and stats.get('total_trades', 0) > 0:
        # 통계 카드
        col1, col2, col3, col4, col5, col6 = st.columns(6)
        
        with col1:
            st.markdown(f"""
            <div class="stat-card">
                <div class="stat-label">Total Trades</div>
                <div class="stat-value">{stats['total_trades']}</div>
            </div>
            """, unsafe_allow_html=True)
        
        with col2:
            win_rate = stats['win_rate']
            st.markdown(f"""
            <div class="stat-card">
                <div class="stat-label">Win Rate</div>
                <div class="stat-value {'positive' if win_rate >= 50 else 'negative'}">{win_rate:.1f}%</div>
            </div>
            """, unsafe_allow_html=True)
        
        with col3:
            total_pnl = stats['total_pnl']
            pnl_class = "positive" if total_pnl >= 0 else "negative"
            st.markdown(f"""
            <div class="stat-card">
                <div class="stat-label">Total PnL</div>
                <div class="stat-value {pnl_class}">${total_pnl:+,.2f}</div>
            </div>
            """, unsafe_allow_html=True)
        
        with col4:
            avg_pnl = stats['avg_pnl']
            pnl_class = "positive" if avg_pnl >= 0 else "negative"
            st.markdown(f"""
            <div class="stat-card">
                <div class="stat-label">Avg PnL</div>
                <div class="stat-value {pnl_class}">${avg_pnl:+,.2f}</div>
            </div>
            """, unsafe_allow_html=True)
        
        with col5:
            profit_factor = stats['profit_factor']
            st.markdown(f"""
            <div class="stat-card">
                <div class="stat-label">Profit Factor</div>
                <div class="stat-value {'positive' if profit_factor >= 1 else 'negative'}">{profit_factor:.2f}</div>
            </div>
            """, unsafe_allow_html=True)
        
        with col6:
            avg_time = stats['avg_holding_time']
            st.markdown(f"""
            <div class="stat-card">
                <div class="stat-label">Avg Hold Time</div>
                <div class="stat-value">{avg_time:.0f}m</div>
            </div>
            """, unsafe_allow_html=True)
        
        st.divider()
        
        # 차트 섹션
        col1, col2 = st.columns(2)
        
        with col1:
            balance_df = get_balance_history(time_range)
            plot_balance_history(balance_df)
        
        with col2:
            daily_df = get_daily_pnl(time_range)
            plot_daily_pnl(daily_df)
        
        st.divider()
        
        # 탭 메뉴
        tabs = st.tabs(["🏆 Leaderboard", "📊 Performance", "💰 Trade History", "📈 Analytics"])
        
        # ============ Tab 1: Leaderboard ============
        with tabs[0]:
            st.header("🏆 Symbol Leaderboard")
            
            symbol_df = get_symbol_performance()
            
            if not symbol_df.empty:
                col1, col2 = st.columns([2, 1])
                
                with col1:
                    plot_symbol_performance(symbol_df, top_n=15)
                
                with col2:
                    st.subheader("Top 10 Performers")
                    
                    top_symbols = symbol_df.head(10)
                    
                    for idx, row in enumerate(top_symbols.itertuples(), 1):
                        pnl_class = "positive" if row.total_pnl >= 0 else "negative"
                        
                        medal = "🥇" if idx == 1 else "🥈" if idx == 2 else "🥉" if idx == 3 else f"#{idx}"
                        
                        st.markdown(f"""
                        <div class="leaderboard-item">
                            <div class="leaderboard-rank">{medal}</div>
                            <div class="leaderboard-symbol">{row.symbol}</div>
                            <div class="leaderboard-pnl {pnl_class}">${row.total_pnl:+,.2f}</div>
                        </div>
                        """, unsafe_allow_html=True)
                        
                        st.caption(f"Win Rate: {row.win_rate:.1f}% | {row.total_trades} trades")
                
                st.divider()
                
                # 상세 테이블
                st.subheader("📋 Detailed Symbol Statistics")
                
                display_df = symbol_df.copy()
                display_df = display_df.rename(columns={
                    'symbol': 'Symbol',
                    'total_trades': 'Trades',
                    'wins': 'Wins',
                    'losses': 'Losses',
                    'win_rate': 'Win Rate (%)',
                    'total_pnl': 'Total PnL ($)',
                    'avg_pnl': 'Avg PnL ($)',
                    'best_trade': 'Best ($)',
                    'worst_trade': 'Worst ($)'
                })
                
                st.dataframe(
                    display_df.style.format({
                        'Total PnL ($)': '${:,.2f}',
                        'Avg PnL ($)': '${:,.2f}',
                        'Best ($)': '${:,.2f}',
                        'Worst ($)': '${:,.2f}',
                        'Win Rate (%)': '{:.1f}%'
                    }).background_gradient(
                        subset=['Total PnL ($)'], 
                        cmap='RdYlGn',
                        vmin=-symbol_df['total_pnl'].abs().max(),
                        vmax=symbol_df['total_pnl'].abs().max()
                    ),
                    use_container_width=True,
                    height=500
                )
            else:
                st.info("📊 심볼별 성과 데이터가 없습니다.")
        
        # ============ Tab 2: Performance ============
        with tabs[1]:
            st.header("📊 Performance Analysis")
            
            # 기간별 비교
            col1, col2, col3 = st.columns(3)
            
            stats_7d = get_trading_statistics(days=7)
            stats_30d = get_trading_statistics(days=30)
            stats_all = get_trading_statistics()
            
            with col1:
                st.subheader("📅 Last 7 Days")
                if stats_7d and stats_7d.get('total_trades', 0) > 0:
                    st.metric("Trades", stats_7d['total_trades'])
                    st.metric("Win Rate", f"{stats_7d['win_rate']:.1f}%")
                    st.metric("Total PnL", f"${stats_7d['total_pnl']:,.2f}",
                             delta=f"{stats_7d['total_pnl']:+.2f}")
                    st.metric("Avg PnL", f"${stats_7d['avg_pnl']:,.2f}")
                    st.metric("Profit Factor", f"{stats_7d['profit_factor']:.2f}")
                else:
                    st.info("No trades in last 7 days")
            
            with col2:
                st.subheader("📅 Last 30 Days")
                if stats_30d and stats_30d.get('total_trades', 0) > 0:
                    st.metric("Trades", stats_30d['total_trades'])
                    st.metric("Win Rate", f"{stats_30d['win_rate']:.1f}%")
                    st.metric("Total PnL", f"${stats_30d['total_pnl']:,.2f}",
                             delta=f"{stats_30d['total_pnl']:+.2f}")
                    st.metric("Avg PnL", f"${stats_30d['avg_pnl']:,.2f}")
                    st.metric("Profit Factor", f"{stats_30d['profit_factor']:.2f}")
                else:
                    st.info("No trades in last 30 days")
            
            with col3:
                st.subheader("📅 All Time")
                if stats_all and stats_all.get('total_trades', 0) > 0:
                    st.metric("Trades", stats_all['total_trades'])
                    st.metric("Win Rate", f"{stats_all['win_rate']:.1f}%")
                    st.metric("Total PnL", f"${stats_all['total_pnl']:,.2f}",
                             delta=f"{stats_all['total_pnl']:+.2f}")
                    st.metric("Avg PnL", f"${stats_all['avg_pnl']:,.2f}")
                    st.metric("Profit Factor", f"{stats_all['profit_factor']:.2f}")
                else:
                    st.info("No trades yet")
            
            st.divider()
            
            # 승률 분포
            symbol_df = get_symbol_performance()
            if not symbol_df.empty:
                plot_winrate_distribution(symbol_df)
            
            st.divider()
            
            # 상세 통계
            if stats and stats.get('total_trades', 0) > 0:
                st.subheader("📈 Detailed Statistics")
                
                col1, col2, col3 = st.columns(3)
                
                with col1:
                    st.metric("Winning Trades", stats['winning_trades'])
                    st.metric("Average Win", f"${stats['avg_win']:,.2f}")
                    st.metric("Max Win", f"${stats['max_win']:,.2f}")
                
                with col2:
                    st.metric("Losing Trades", stats['losing_trades'])
                    st.metric("Average Loss", f"${stats['avg_loss']:,.2f}")
                    st.metric("Max Loss", f"${stats['max_loss']:,.2f}")
                
                with col3:
                    risk_reward = abs(stats['avg_win'] / stats['avg_loss']) if stats['avg_loss'] != 0 else 0
                    st.metric("Risk/Reward Ratio", f"{risk_reward:.2f}")
                    st.metric("Average Holding Time", f"{stats['avg_holding_time']:.0f} minutes")
                    expectancy = (stats['win_rate']/100 * stats['avg_win']) + ((1-stats['win_rate']/100) * stats['avg_loss'])
                    st.metric("Expectancy", f"${expectancy:,.2f}")
        
        # ============ Tab 3: Trade History ============
        with tabs[2]:
            st.header("💰 Trade History")
            
            trades_df = get_completed_trades(200)
            
            if not trades_df.empty:
                col1, col2 = st.columns(2)
                
                with col1:
                    plot_pnl_distribution(trades_df)
                
                with col2:
                    plot_cumulative_pnl(trades_df)
                
                st.divider()
                
                # 거래 테이블
                st.subheader("📋 Recent Trades")
                
                # 필터
                col1, col2, col3 = st.columns(3)
                
                with col1:
                    filter_symbol = st.selectbox(
                        "Filter by Symbol",
                        options=['All'] + sorted(trades_df['symbol'].unique().tolist())
                    )
                
                with col2:
                    filter_side = st.selectbox(
                        "Filter by Side",
                        options=['All', 'Long', 'Short']
                    )
                
                with col3:
                    filter_result = st.selectbox(
                        "Filter by Result",
                        options=['All', 'Wins', 'Losses']
                    )
                
                # 필터 적용
                filtered_df = trades_df.copy()
                
                if filter_symbol != 'All':
                    filtered_df = filtered_df[filtered_df['symbol'] == filter_symbol]
                
                if filter_side == 'Long':
                    filtered_df = filtered_df[filtered_df['side'] == 'buy']
                elif filter_side == 'Short':
                    filtered_df = filtered_df[filtered_df['side'] == 'sell']
                
                if filter_result == 'Wins':
                    filtered_df = filtered_df[filtered_df['is_win'] == 1]
                elif filter_result == 'Losses':
                    filtered_df = filtered_df[filtered_df['is_win'] == 0]
                
                # 데이터 준비
                display_df = filtered_df[[
                    'exit_time', 'symbol', 'side', 'entry_price', 'exit_price',
                    'pnl', 'pnl_percent', 'holding_time_minutes', 'exit_reason'
                ]].copy()
                
                display_df['side'] = display_df['side'].map({'buy': '🟢 Long', 'sell': '🔴 Short'})
                
                display_df.columns = [
                    'Exit Time', 'Symbol', 'Side', 'Entry Price', 'Exit Price',
                    'PnL ($)', 'PnL (%)', 'Hold Time (min)', 'Exit Reason'
                ]
                
                # 시간 포맷
                display_df['Exit Time'] = pd.to_datetime(display_df['Exit Time']).dt.strftime('%Y-%m-%d %H:%M:%S')
                
                st.dataframe(
                    display_df.style.format({
                        'Entry Price': '${:,.2f}',
                        'Exit Price': '${:,.2f}',
                        'PnL ($)': '${:,.2f}',
                        'PnL (%)': '{:+.2f}%',
                        'Hold Time (min)': '{:.0f}'
                    }).applymap(
                        lambda x: 'color: #28a745; font-weight: bold' if isinstance(x, str) and x.startswith('+') or (isinstance(x, (int, float)) and x > 0) else 'color: #dc3545; font-weight: bold' if isinstance(x, (int, float)) and x < 0 else '',
                        subset=['PnL ($)', 'PnL (%)']
                    ),
                    use_container_width=True,
                    height=600
                )
                
                # 통계 요약
                st.divider()
                
                col1, col2, col3, col4 = st.columns(4)
                
                with col1:
                    st.metric("Filtered Trades", len(filtered_df))
                
                with col2:
                    win_count = len(filtered_df[filtered_df['is_win'] == 1])
                    win_rate_filtered = (win_count / len(filtered_df) * 100) if len(filtered_df) > 0 else 0
                    st.metric("Win Rate", f"{win_rate_filtered:.1f}%")
                
                with col3:
                    total_pnl_filtered = filtered_df['pnl'].sum()
                    st.metric("Total PnL", f"${total_pnl_filtered:+,.2f}")
                
                with col4:
                    avg_pnl_filtered = filtered_df['pnl'].mean()
                    st.metric("Avg PnL", f"${avg_pnl_filtered:+,.2f}")
            else:
                st.info("📊 거래 내역이 없습니다.")
        
        # ============ Tab 4: Analytics ============
        with tabs[3]:
            st.header("📈 Advanced Analytics")
            
            trades_df = get_completed_trades(1000)
            
            if not trades_df.empty:
                # 월별 성과
                st.subheader("📊 Monthly Performance")
                
                trades_df['exit_time'] = pd.to_datetime(trades_df['exit_time'])
                trades_df['month'] = trades_df['exit_time'].dt.to_period('M')
                
                monthly_stats = trades_df.groupby('month').agg({
                    'pnl': ['sum', 'count', 'mean'],
                    'is_win': 'sum'
                }).reset_index()
                
                monthly_stats.columns = ['Month', 'Total PnL', 'Trades', 'Avg PnL', 'Wins']
                monthly_stats['Losses'] = monthly_stats['Trades'] - monthly_stats['Wins']
                monthly_stats['Win Rate (%)'] = (monthly_stats['Wins'] / monthly_stats['Trades'] * 100).round(1)
                monthly_stats['Month'] = monthly_stats['Month'].astype(str)
                
                st.dataframe(
                    monthly_stats.style.format({
                        'Total PnL': '${:,.2f}',
                        'Avg PnL': '${:,.2f}',
                        'Win Rate (%)': '{:.1f}%'
                    }).background_gradient(
                        subset=['Total PnL'],
                        cmap='RdYlGn',
                        vmin=-monthly_stats['Total PnL'].abs().max(),
                        vmax=monthly_stats['Total PnL'].abs().max()
                    ),
                    use_container_width=True
                )
                
                st.divider()
                
                # 요일별 성과
                st.subheader("📅 Performance by Day of Week")
                
                trades_df['day_of_week'] = trades_df['exit_time'].dt.day_name()
                day_order = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
                
                day_stats = trades_df.groupby('day_of_week').agg({
                    'pnl': ['sum', 'count', 'mean'],
                    'is_win': 'sum'
                }).reset_index()
                
                day_stats.columns = ['Day', 'Total PnL', 'Trades', 'Avg PnL', 'Wins']
                day_stats['Win Rate (%)'] = (day_stats['Wins'] / day_stats['Trades'] * 100).round(1)
                
                # 요일 순서 정렬
                day_stats['Day'] = pd.Categorical(day_stats['Day'], categories=day_order, ordered=True)
                day_stats = day_stats.sort_values('Day')
                
                col1, col2 = st.columns(2)
                
                with col1:
                    fig = go.Figure()
                    colors = ['#28a745' if x >= 0 else '#dc3545' for x in day_stats['Total PnL']]
                    
                    fig.add_trace(go.Bar(
                        x=day_stats['Day'],
                        y=day_stats['Total PnL'],
                        marker_color=colors,
                        text=day_stats['Total PnL'].apply(lambda x: f'${x:,.0f}'),
                        textposition='outside',
                        hovertemplate='<b>%{x}</b><br>PnL: $%{y:,.2f}<br>Trades: %{customdata}<extra></extra>',
                        customdata=day_stats['Trades']
                    ))
                    
                    fig.update_layout(
                        title='PnL by Day of Week',
                        xaxis_title='Day',
                        yaxis_title='Total PnL ($)',
                        height=400,
                        showlegend=False,
                        plot_bgcolor='white',
                        yaxis=dict(zeroline=True, zerolinecolor='black', zerolinewidth=2)
                    )
                    
                    st.plotly_chart(fig, use_container_width=True)
                
                with col2:
                    st.dataframe(
                        day_stats.style.format({
                            'Total PnL': '${:,.2f}',
                            'Avg PnL': '${:,.2f}',
                            'Win Rate (%)': '{:.1f}%'
                        }),
                        use_container_width=True,
                        height=400
                    )
                
                st.divider()
                
                # 시간대별 성과
                st.subheader("🕐 Performance by Hour")
                
                trades_df['hour'] = trades_df['exit_time'].dt.hour
                
                hour_stats = trades_df.groupby('hour').agg({
                    'pnl': ['sum', 'count', 'mean'],
                    'is_win': 'sum'
                }).reset_index()
                
                hour_stats.columns = ['Hour', 'Total PnL', 'Trades', 'Avg PnL', 'Wins']
                hour_stats['Win Rate (%)'] = (hour_stats['Wins'] / hour_stats['Trades'] * 100).round(1)
                
                fig = go.Figure()
                
                colors = ['#28a745' if x >= 0 else '#dc3545' for x in hour_stats['Total PnL']]
                
                fig.add_trace(go.Bar(
                    x=hour_stats['Hour'],
                    y=hour_stats['Total PnL'],
                    marker_color=colors,
                    text=hour_stats['Trades'],
                    textposition='outside',
                    hovertemplate='<b>Hour %{x}</b><br>PnL: $%{y:,.2f}<br>Trades: %{text}<br>Win Rate: %{customdata:.1f}%<extra></extra>',
                    customdata=hour_stats['Win Rate (%)']
                ))
                
                fig.update_layout(
                    title='PnL by Hour of Day',
                    xaxis_title='Hour (24h format)',
                    yaxis_title='Total PnL ($)',
                    height=400,
                    showlegend=False,
                    plot_bgcolor='white',
                    xaxis=dict(tickmode='linear', tick0=0, dtick=2),
                    yaxis=dict(zeroline=True, zerolinecolor='black', zerolinewidth=2)
                )
                
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("📊 분석할 데이터가 없습니다.")
    
    else:
        st.info("📊 거래 데이터가 없습니다. 봇이 거래를 시작하면 여기에 통계가 표시됩니다.")
    
    # 업데이트 시간
    st.markdown(f"""
    <div class="update-time">
        ⏰ Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | 
        🔄 Data refreshes every 30 seconds
    </div>
    """, unsafe_allow_html=True)

if __name__ == "__main__":
    main()
