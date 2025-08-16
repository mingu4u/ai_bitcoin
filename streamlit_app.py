import streamlit as st
import sqlite3
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import math
import requests
import json
from datetime import datetime, timedelta
import time
import asyncio

# Middle Server 설정
MIDDLE_SERVER_URL = "http://localhost:5000"

def check_middle_server_health():
    """Middle Server 상태 확인"""
    try:
        response = requests.get(f"{MIDDLE_SERVER_URL}/status", timeout=2)
        if response.status_code == 200:
            return True, response.json()
        return False, None
    except:
        return False, None

def get_all_positions():
    """모든 심볼의 포지션 정보 가져오기"""
    try:
        response = requests.get(f"{MIDDLE_SERVER_URL}/all-positions", timeout=5)
        if response.status_code == 200:
            return response.json()
        return None
    except:
        return None

def get_account_balance():
    """계정 전체 잔고 정보 가져오기"""
    try:
        response = requests.get(f"{MIDDLE_SERVER_URL}/balance", timeout=5)
        if response.status_code == 200:
            return response.json()
        return None
    except:
        return None

def get_current_positions():
    """현재 포지션 정보 가져오기"""
    try:
        response = requests.get(f"{MIDDLE_SERVER_URL}/positions", timeout=5)
        if response.status_code == 200:
            return response.json()
        return None
    except:
        return None

def get_symbol_price(symbol):
    """특정 심볼의 현재 가격 가져오기"""
    try:
        response = requests.get(f"{MIDDLE_SERVER_URL}/price/{symbol}", timeout=5)
        if response.status_code == 200:
            return response.json()
        return None
    except:
        return None

def get_portfolio_value():
    """포트폴리오 전체 가치 계산"""
    try:
        response = requests.get(f"{MIDDLE_SERVER_URL}/portfolio-value", timeout=5)
        if response.status_code == 200:
            return response.json()
        return None
    except:
        return None

def get_open_orders():
    """열린 주문 정보 가져오기"""
    try:
        response = requests.get(f"{MIDDLE_SERVER_URL}/check", timeout=5)
        if response.status_code == 200:
            return response.json()
        return None
    except:
        return None

def sync_positions():
    """포지션 동기화 실행"""
    try:
        response = requests.post(f"{MIDDLE_SERVER_URL}/sync", timeout=5)
        if response.status_code == 200:
            return True, response.json()
        return False, None
    except:
        return False, None

def test_telegram():
    """텔레그램 알림 테스트"""
    try:
        response = requests.post(f"{MIDDLE_SERVER_URL}/test-telegram", timeout=5)
        if response.status_code == 200:
            return True, response.json()
        return False, None
    except:
        return False, None

def close_position_manually(symbol=None):
    """수동으로 포지션 종료"""
    try:
        data = {
            "action": "close_position"
        }
        if symbol:
            data["symbol"] = symbol
            
        response = requests.post(
            f"{MIDDLE_SERVER_URL}/webhook",
            json=data,
            headers={'Content-Type': 'application/json'},
            timeout=5
        )
        if response.status_code == 200:
            return True, response.json()
        return False, None
    except:
        return False, None

def get_connection():
    return sqlite3.connect('bitcoin_trades.db')

def load_historical_data():
    """기존 거래 히스토리 데이터 로드"""
    try:
        conn = get_connection()
        query = """SELECT timestamp, trade_type, order_id, decision, percentage, reason, 
                  btc_balance, usdt_balance, total_assets, btc_avg_buy_price, 
                  btc_current_price, reflection, tp_order_id, sl_order_id,
                  blackflag_signal, blackflag_candles_ago, utbot_signal, 
                  utbot_candles_ago, volume_osc_current, stop_loss_price, 
                  cloud_gap_valid, position_type
                  FROM trades"""
        df = pd.read_sql_query(query, conn)
        conn.close()
        
        # 불리언 컬럼 변환
        if 'cloud_gap_valid' in df.columns:
            df['cloud_gap_valid'] = df['cloud_gap_valid'].astype(bool)
        
        # position_type 기본값 처리
        if 'position_type' in df.columns:
            df['position_type'] = df['position_type'].fillna('normal')
        
        return df
    except sqlite3.Error as e:
        st.error(f"Database error: {e}")
        return pd.DataFrame()

def paginate_dataframe(df, page_size=30):
    if df.empty:
        return 1
    return math.ceil(len(df) / page_size)

def calculate_performance_metrics(trades_df):
    if trades_df.empty:
        return {
            'total_trades': 0,
            'total_return': 0,
            'win_rate': 0,
            'avg_profit_per_trade': 0,
            'max_drawdown': 0,
            'risk_adjusted_return': 0
        }
    
    trades_df = trades_df.sort_values('timestamp')
    
    # 이 수익률
    total_return = ((trades_df['total_assets'].iloc[-1] - trades_df['total_assets'].iloc[0]) 
                   / trades_df['total_assets'].iloc[0]) * 100
    
    # 승률 계산
    trades_df['pnl'] = trades_df['total_assets'].diff()
    wins = (trades_df['pnl'] > 0).sum()
    win_rate = (wins / len(trades_df[trades_df['pnl'].notna()])) * 100
    
    # 평균 수익/거래
    avg_profit_per_trade = trades_df['pnl'].mean() / trades_df['total_assets'].shift(1) * 100
    
    # 최대 낙폭
    cummax = trades_df['total_assets'].cummax()
    drawdowns = (trades_df['total_assets'] - cummax) / cummax * 100
    max_drawdown = abs(drawdowns.min())
    
    # 리스크 조정 수익률 (Daily Sharpe Ratio)
    daily_returns = trades_df['total_assets'].pct_change()
    risk_adjusted_return = (daily_returns.mean() / daily_returns.std()) if daily_returns.std() != 0 else 0
    
    return {
        'total_trades': len(trades_df),
        'total_return': total_return,
        'win_rate': win_rate,
        'avg_profit_per_trade': avg_profit_per_trade,
        'max_drawdown': max_drawdown,
        'risk_adjusted_return': risk_adjusted_return
    }

def display_portfolio_overview():
    """포트폴리오 전체 개요 표시"""
    st.subheader("💰 Portfolio Overview")
    
    # 포트폴리오 전체 가치 가져오기
    portfolio_data = get_portfolio_value()
    balance_data = get_account_balance()
    
    if portfolio_data and balance_data:
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            total_value = portfolio_data.get('total_portfolio_value', 0)
            st.metric("Total Portfolio Value", f"${total_value:,.2f}")
        
        with col2:
            total_pnl = portfolio_data.get('total_unrealized_pnl', 0)
            pnl_color = "normal" if total_pnl >= 0 else "inverse"
            st.metric("Unrealized PnL", f"${total_pnl:,.2f}", delta=total_pnl, delta_color=pnl_color)
        
        with col3:
            usdt_balance = balance_data.get('USDT', {}).get('free', 0)
            st.metric("Available USDT", f"${float(usdt_balance):,.2f}")
        
        with col4:
            active_positions = len([pos for pos in portfolio_data.get('positions', []) if float(pos.get('size', 0)) != 0])
            st.metric("Active Positions", active_positions)
        
        # 주요 코인 보유량 표시
        if balance_data:
            st.subheader("🪙 Major Holdings")
            holdings_data = []
            
            for symbol, balance_info in balance_data.items():
                free_balance = float(balance_info.get('free', 0))
                locked_balance = float(balance_info.get('locked', 0))
                total_balance = free_balance + locked_balance
                
                if total_balance > 0 and symbol != 'USDT':
                    # 현재 가격 가져오기
                    price_data = get_symbol_price(f"{symbol}USDT")
                    current_price = float(price_data.get('price', 0)) if price_data else 0
                    value_usdt = total_balance * current_price
                    
                    holdings_data.append({
                        'Symbol': symbol,
                        'Free': free_balance,
                        'Locked': locked_balance,
                        'Total': total_balance,
                        'Price (USDT)': current_price,
                        'Value (USDT)': value_usdt
                    })
            
            if holdings_data:
                holdings_df = pd.DataFrame(holdings_data)
                holdings_df = holdings_df.sort_values('Value (USDT)', ascending=False)
                st.dataframe(holdings_df, use_container_width=True)

def display_realtime_positions():
    """실시간 포지션 정보 표시"""
    st.subheader("📊 Active Positions")
    
    # 모든 포지션 정보 가져오기
    all_positions = get_all_positions()
    
    if all_positions and all_positions.get('positions'):
        positions_data = []
        
        for position in all_positions['positions']:
            if float(position.get('positionAmt', 0)) != 0:  # 활성 포지션만
                symbol = position.get('symbol', '')
                side = 'LONG' if float(position.get('positionAmt', 0)) > 0 else 'SHORT'
                size = abs(float(position.get('positionAmt', 0)))
                entry_price = float(position.get('entryPrice', 0))
                mark_price = float(position.get('markPrice', 0))
                pnl = float(position.get('unRealizedProfit', 0))
                pnl_percent = (pnl / (size * entry_price)) * 100 if entry_price > 0 else 0
                
                positions_data.append({
                    'Symbol': symbol,
                    'Side': side,
                    'Size': size,
                    'Entry Price': entry_price,
                    'Mark Price': mark_price,
                    'PnL (USDT)': pnl,
                    'PnL (%)': pnl_percent
                })
        
        if positions_data:
            positions_df = pd.DataFrame(positions_data)
            
            # 각 포지션을 카드 형태로 표시
            for idx, row in positions_df.iterrows():
                col1, col2, col3, col4 = st.columns([2, 1, 1, 1])
                
                with col1:
                    side_color = "🟢" if row['Side'] == 'LONG' else "🔴"
                    st.write(f"{side_color} **{row['Symbol']}** ({row['Side']})")
                    st.write(f"Size: {row['Size']:.6f}")
                
                with col2:
                    st.write(f"Entry: ${row['Entry Price']:,.4f}")
                    st.write(f"Mark: ${row['Mark Price']:,.4f}")
                
                with col3:
                    pnl_color = "green" if row['PnL (USDT)'] >= 0 else "red"
                    st.markdown(f"<span style='color:{pnl_color}'>PnL: ${row['PnL (USDT)']:,.2f}</span>", 
                              unsafe_allow_html=True)
                    st.markdown(f"<span style='color:{pnl_color}'>({row['PnL (%)']:+.2f}%)</span>", 
                              unsafe_allow_html=True)
                
                with col4:
                    if st.button(f"Close {row['Symbol']}", key=f"close_{row['Symbol']}_{idx}"):
                        success, result = close_position_manually(row['Symbol'])
                        if success:
                            st.success(f"Position {row['Symbol']} closed!")
                            time.sleep(1)
                            st.rerun()
                        else:
                            st.error(f"Failed to close {row['Symbol']}")
                
                st.write("---")
        else:
            st.info("No active positions")
    else:
        st.warning("Unable to fetch position data")

def display_realtime_section():
    """실시간 거래 정보 섹션"""
    st.header('🔴 Real-time Trading Status')
    
    # Health Check 상태 표시
    col1, col2 = st.columns([1, 3])
    
    with col1:
        health_status, server_data = check_middle_server_health()
        if health_status:
            st.success("✅ Server Online")
            
            # 서버 상태 정보 표시
            if server_data:
                st.metric("Symbol", server_data.get('symbol', 'N/A'))
                st.metric("Position Size %", f"{server_data.get('position_size_percent', 0)}%")
                st.metric("Active Positions", server_data.get('current_positions', 0))
                
                # 텔레그램 상태
                if server_data.get('telegram_configured'):
                    st.success("📱 Telegram: Connected")
                else:
                    st.warning("📱 Telegram: Not configured")
                    
                # 컨트롤 버튼들
                st.subheader("⚙️ Controls")
                
                if st.button("🔄 Sync Positions", use_container_width=True):
                    success, data = sync_positions()
                    if success:
                        st.success("Synced successfully!")
                    else:
                        st.error("Sync failed")
                
                if st.button("📱 Test Telegram", use_container_width=True):
                    success, data = test_telegram()
                    if success:
                        st.success("Telegram test sent!")
                    else:
                        st.error("Telegram test failed")
        else:
            st.error("❌ Server Offline")
            st.info("Please check if middle_server.py is running on port 5000")
    
    with col2:
        if health_status:
            # 포트폴리오 개요
            display_portfolio_overview()
    
    # 실시간 포지션 정보
    if health_status:
        display_realtime_positions()
        
        # 열린 주문 정보
        st.subheader("📋 Open Orders")
        orders_data = get_open_orders()
        if orders_data and orders_data.get('orders'):
            orders_df = pd.DataFrame(orders_data['orders'])
            st.dataframe(orders_df, use_container_width=True)
        else:
            st.info("No open orders")

def display_historical_section(df):
    """기존 히스토리 섹션"""
    st.header('📈 Historical Trading Data')
    
    if df.empty:
        st.warning("No historical trading data available.")
        return
    
    # 시간 역순 정렬
    df = df.sort_values('timestamp', ascending=False).reset_index(drop=True)
    
    # 거래 유형 선택 필터
    trade_type = st.selectbox('Select Trade Type', ['ALL', 'AI', 'MANUAL'])
    
    filtered_df = df[df['trade_type'] == trade_type] if trade_type != 'ALL' else df
    
    # 기본 통계
    st.subheader('Basic Statistics')
    if not filtered_df.empty:
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.metric("Total Trades", len(filtered_df))
        with col2:
            st.metric("First Trade", filtered_df['timestamp'].min())
        with col3:
            st.metric("Last Trade", filtered_df['timestamp'].max())
        
        # 최근 거래 신호 상태
        latest_trade = df.iloc[0]
        
        with st.expander("Latest Trading Signals Status"):
            col1, col2 = st.columns(2)
            
            with col1:
                st.subheader("BlackFlag FTS")
                if 'blackflag_signal' in latest_trade and pd.notna(latest_trade['blackflag_signal']):
                    st.write(f"Signal: {latest_trade['blackflag_signal']}")
                    if 'blackflag_candles_ago' in latest_trade and pd.notna(latest_trade['blackflag_candles_ago']):
                        st.write(f"Candles Ago: {latest_trade['blackflag_candles_ago']}")
                    if 'cloud_gap_valid' in latest_trade and pd.notna(latest_trade['cloud_gap_valid']):
                        st.write(f"Cloud Gap: {latest_trade['cloud_gap_valid']}")
                
                st.subheader("UT Bot Alert")
                if 'utbot_signal' in latest_trade and pd.notna(latest_trade['utbot_signal']):
                    st.write(f"Signal: {latest_trade['utbot_signal']}")
                    if 'utbot_candles_ago' in latest_trade and pd.notna(latest_trade['utbot_candles_ago']):
                        st.write(f"Candles Ago: {latest_trade['utbot_candles_ago']}")
            
            with col2:
                st.subheader("Volume Oscillator")
                if 'volume_osc_current' in latest_trade and pd.notna(latest_trade['volume_osc_current']):
                    st.write(f"Current Value: {latest_trade['volume_osc_current']:.2f}")
                
                st.subheader("Stop Loss Price")
                if 'stop_loss_price' in latest_trade and pd.notna(latest_trade['stop_loss_price']):
                    st.write(f"Price: {latest_trade['stop_loss_price']:.2f} USDT")
    
    # 거래 내역 표시
    st.subheader('Trade History')
    if not filtered_df.empty:
        page_size = 30
        n_pages = paginate_dataframe(filtered_df, page_size)
        
        page_number = st.selectbox('Page', range(1, n_pages + 1), 
                                 format_func=lambda x: f'Page {x} of {n_pages}')
        
        start_idx = (page_number - 1) * page_size
        end_idx = min(start_idx + page_size, len(filtered_df))
        
        # 표시할 컬럼 선택
        display_columns = ['timestamp', 'trade_type', 'decision', 'percentage', 'reason', 
                         'btc_balance', 'usdt_balance', 'total_assets', 'btc_current_price',
                         'blackflag_signal', 'blackflag_candles_ago', 'utbot_signal', 
                         'utbot_candles_ago', 'volume_osc_current', 'stop_loss_price', 
                         'cloud_gap_valid', 'position_type']
        
        display_df = filtered_df.iloc[start_idx:end_idx][display_columns].copy()
        
        # 컬럼 이름 축약
        display_df = display_df.rename(columns={
            'blackflag_signal': 'BF_Signal',
            'blackflag_candles_ago': 'BF_Age',
            'utbot_signal': 'UTBot_Signal',
            'utbot_candles_ago': 'UTBot_Age',
            'volume_osc_current': 'Vol_Osc',
            'stop_loss_price': 'SL_Price',
            'cloud_gap_valid': 'Cloud_Gap',
            'position_type': 'Pos_Type'
        })
        
        st.dataframe(display_df, height=500, use_container_width=True)

def display_charts_section(df):
    """차트 및 분석 섹션"""
    st.header('📊 Performance Analysis')
    
    if df.empty:
        st.info("No data available for analysis")
        return
    
    # 거래 결정 분포
    col1, col2 = st.columns(2)
    
    with col1:
        if 'decision' in df.columns:
            st.subheader('Trade Decision Distribution')
            decision_counts = df['decision'].value_counts()
            if not decision_counts.empty:
                fig = px.pie(
                    values=decision_counts.values, 
                    names=decision_counts.index,
                    title='Trade Decisions',
                    color=decision_counts.index,
                    color_discrete_map={
                        'buy': '#FF0000',
                        'sell': '#000080',
                        'hold': '#87CEEB'
                    }
                )
                st.plotly_chart(fig, use_container_width=True)
    
    with col2:
        if 'total_assets' in df.columns:
            st.subheader('Total Assets Over Time')
            fig = px.line(df, x='timestamp', y='total_assets', 
                        title='Portfolio Value')
            st.plotly_chart(fig, use_container_width=True)
    
    # BTC 가격과 잔고 변화
    col3, col4 = st.columns(2)
    
    with col3:
        if 'btc_balance' in df.columns:
            st.subheader('BTC Balance Over Time')
            fig = px.line(df, x='timestamp', y='btc_balance', 
                        title='BTC Holdings')
            st.plotly_chart(fig, use_container_width=True)
    
    with col4:
        if 'btc_current_price' in df.columns:
            st.subheader('BTC Price Movement')
            fig = px.line(df, x='timestamp', y='btc_current_price', 
                        title='BTC/USDT Price')
            st.plotly_chart(fig, use_container_width=True)

def main():
    st.set_page_config(
        page_title="Multi-Coin Trading Bot Dashboard",
        page_icon="🤖",
        layout="wide",
        initial_sidebar_state="expanded"
    )
    
    st.title("🤖 Ming9's Multi-Coin Trading Bot Dashboard")
    
    # 자동 새로고침 설정
    auto_refresh = st.sidebar.checkbox("🔄 Auto Refresh (10 seconds)", value=False)
    
    if auto_refresh:
        refresh_placeholder = st.sidebar.empty()
        for seconds in range(10, 0, -1):
            refresh_placeholder.write(f"⏰ Refreshing in {seconds} seconds...")
            time.sleep(1)
        refresh_placeholder.write("🔄 Refreshing now...")
        st.rerun()
    
    # 탭 생성
    tab1, tab2, tab3 = st.tabs(["🔴 Live Trading", "📈 Historical Data", "📊 Analysis"])
    
    with tab1:
        display_realtime_section()
    
    with tab2:
        # 히스토리 데이터 로드
        df = load_historical_data()
        display_historical_section(df)
    
    with tab3:
        # 분석 차트
        df = load_historical_data()
        display_charts_section(df)
        
        # AI vs Manual 비교 (데이터가 있을 경우)
        if not df.empty and 'trade_type' in df.columns:
            st.header('🤖 AI vs Manual Trading Comparison')
            
            ai_trades = df[df['trade_type'] == 'AI']
            manual_trades = df[df['trade_type'] == 'MANUAL']
            
            if not ai_trades.empty or not manual_trades.empty:
                ai_metrics = calculate_performance_metrics(ai_trades)
                manual_metrics = calculate_performance_metrics(manual_trades)
                
                comparison_data = pd.DataFrame({
                    'Metric': [
                        'Total Trades',
                        'Total Return (%)',
                        'Win Rate (%)',
                        'Avg Profit/Trade (%)',
                        'Max Drawdown (%)',
                        'Risk-Adjusted Return'
                    ],
                    'AI Trading': [
                        ai_metrics['total_trades'],
                        round(ai_metrics['total_return'], 2),
                        round(ai_metrics['win_rate'], 2),
                        round(ai_metrics['avg_profit_per_trade'], 2),
                        round(ai_metrics['max_drawdown'], 2),
                        round(ai_metrics['risk_adjusted_return'], 2)
                    ],
                    'Manual Trading': [
                        manual_metrics['total_trades'],
                        round(manual_metrics['total_return'], 2),
                        round(manual_metrics['win_rate'], 2),
                        round(manual_metrics['avg_profit_per_trade'], 2),
                        round(manual_metrics['max_drawdown'], 2),
                        round(manual_metrics['risk_adjusted_return'], 2)
                    ]
                })
                
                st.dataframe(comparison_data, use_container_width=True)
                
                # 성과 비교 차트
                fig = go.Figure()
                
                x = comparison_data['Metric'][1:4]  # 주요 지표만 선택
                
                fig.add_trace(go.Bar(
                    name='AI Trading',
                    x=x,
                    y=comparison_data['AI Trading'][1:4],
                    marker_color='lightblue'
                ))
                
                fig.add_trace(go.Bar(
                    name='Manual Trading',
                    x=x,
                    y=comparison_data['Manual Trading'][1:4],
                    marker_color='lightgreen'
                ))
                
                fig.update_layout(
                    title='Trading Performance Comparison',
                    barmode='group',
                    xaxis_title='Metrics',
                    yaxis_title='Value (%)'
                )
                
                st.plotly_chart(fig, use_container_width=True)
    
    # 사이드바에 간단한 정보 표시
    with st.sidebar:
        st.header("ℹ️ System Info")
        
        # 서버 상태 확인
        health_status, server_data = check_middle_server_health()
        
        if health_status:
            st.success("✅ Middle Server: Online")
            
            if server_data:
                st.write(f"**Symbol:** {server_data.get('symbol', 'N/A')}")
                st.write(f"**Positions:** {server_data.get('current_positions', 0)}")
                
                # 마지막 업데이트 시간
                st.write(f"**Last Check:** {datetime.now().strftime('%H:%M:%S')}")
        else:
            st.error("❌ Middle Server: Offline")
            st.info("Start middle_server.py first")
        
        st.write("---")
        
        # 빠른 액션 버튼들
        st.header("⚡ Quick Actions")
        
        if st.button("🔄 Refresh Dashboard", use_container_width=True):
            st.rerun()
        
        if health_status:
            if st.button("📊 Check All Positions", use_container_width=True):
                positions = get_all_positions()
                if positions:
                    st.json(positions.get('positions', {}))
                else:
                    st.error("Failed to get positions")
            
            if st.button("💰 Check Portfolio Value", use_container_width=True):
                portfolio = get_portfolio_value()
                if portfolio:
                    st.json(portfolio)
                else:
                    st.error("Failed to get portfolio value")

if __name__ == "__main__":
    main()