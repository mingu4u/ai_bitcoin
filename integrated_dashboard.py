import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import requests
import json
from datetime import datetime, timedelta
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
import sqlite3
import numpy as np

# Middle Server 설정 - 다중 포트 지원
MIDDLE_SERVER_PORTS = [5000, 5001, 5002]
MIDDLE_SERVER_BASE_URL = "http://localhost"

# 메인 서버는 5000번 포트
MAIN_SERVER_URL = f"{MIDDLE_SERVER_BASE_URL}:5000"

# 페이지 설정
st.set_page_config(
    page_title="AI Trading System Dashboard",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ============ 캐싱 메커니즘 ============
class DataCache:
    def __init__(self, ttl=30):
        self.cache = {}
        self.ttl = ttl
        self.lock = threading.Lock()
    
    def get(self, key):
        with self.lock:
            if key in self.cache:
                data, timestamp = self.cache[key]
                if time.time() - timestamp < self.ttl:
                    return data
                else:
                    del self.cache[key]
            return None
    
    def set(self, key, value):
        with self.lock:
            self.cache[key] = (value, time.time())
    
    def clear(self, key=None):
        with self.lock:
            if key:
                self.cache.pop(key, None)
            else:
                self.cache.clear()

# 전역 캐시 인스턴스
data_cache = DataCache(ttl=30)

# ============ Database Functions ============
def get_trades_from_db(symbol=None, limit=100):
    """데이터베이스에서 거래 기록 조회"""
    try:
        conn = sqlite3.connect('integrated_trades.db')
        
        if symbol:
            query = """
                SELECT * FROM trades 
                WHERE symbol = ? 
                ORDER BY timestamp DESC 
                LIMIT ?
            """
            df = pd.read_sql_query(query, conn, params=(symbol, limit))
        else:
            query = """
                SELECT * FROM trades 
                ORDER BY timestamp DESC 
                LIMIT ?
            """
            df = pd.read_sql_query(query, conn, params=(limit,))
        
        conn.close()
        return df
    except Exception as e:
        st.error(f"Database error: {str(e)}")
        return pd.DataFrame()

def get_ai_decisions_from_db(limit=50):
    """AI 의사결정 기록 조회"""
    try:
        conn = sqlite3.connect('integrated_trades.db')
        
        query = """
            SELECT 
                timestamp,
                symbol,
                ai_decision,
                action,
                percentage,
                reason,
                stop_loss,
                take_profit,
                pl_ratio,
                confidence,
                reflection
            FROM trades 
            WHERE trade_type = 'AI_VALIDATION'
            ORDER BY timestamp DESC 
            LIMIT ?
        """
        
        df = pd.read_sql_query(query, conn, params=(limit,))
        conn.close()
        
        # timestamp를 datetime으로 변환
        if not df.empty:
            df['timestamp'] = pd.to_datetime(df['timestamp'])
        
        return df
    except Exception as e:
        st.error(f"Database error: {str(e)}")
        return pd.DataFrame()

def get_reflection_history(symbol=None, limit=10):
    """Reflection 내역 조회"""
    try:
        conn = sqlite3.connect('integrated_trades.db')
        
        if symbol:
            query = """
                SELECT DISTINCT
                    timestamp,
                    symbol,
                    reflection
                FROM trades 
                WHERE reflection IS NOT NULL 
                AND reflection != ''
                AND symbol = ?
                ORDER BY timestamp DESC 
                LIMIT ?
            """
            df = pd.read_sql_query(query, conn, params=(symbol, limit))
        else:
            query = """
                SELECT DISTINCT
                    timestamp,
                    symbol,
                    reflection
                FROM trades 
                WHERE reflection IS NOT NULL 
                AND reflection != ''
                ORDER BY timestamp DESC 
                LIMIT ?
            """
            df = pd.read_sql_query(query, conn, params=(limit,))
        
        conn.close()
        return df
    except Exception as e:
        st.error(f"Database error: {str(e)}")
        return pd.DataFrame()

# ============ API Functions ============
def check_middle_server_health(force_refresh=False):
    """Middle Server 상태 확인"""
    cache_key = "server_health"
    
    if not force_refresh:
        cached = data_cache.get(cache_key)
        if cached:
            return cached
    
    try:
        response = requests.get(f"{MAIN_SERVER_URL}/status", timeout=5)
        if response.status_code == 200:
            result = (True, response.json())
            data_cache.set(cache_key, result)
            return result
        return False, None
    except:
        return False, None

def get_ai_performance(force_refresh=False):
    """AI 성과 통계 가져오기"""
    cache_key = "ai_performance"
    
    if not force_refresh:
        cached = data_cache.get(cache_key)
        if cached:
            return cached
    
    try:
        response = requests.get(f"{MAIN_SERVER_URL}/ai-performance", timeout=10)
        if response.status_code == 200:
            result = response.json()
            data_cache.set(cache_key, result)
            return result
        return None
    except Exception as e:
        st.error(f"Error fetching AI performance: {str(e)}")
        return None

def get_symbol_config(force_refresh=False):
    """심볼 설정 가져오기"""
    cache_key = "symbol_config"
    
    if not force_refresh:
        cached = data_cache.get(cache_key)
        if cached:
            return cached
    
    try:
        response = requests.get(f"{MAIN_SERVER_URL}/config", timeout=10)
        if response.status_code == 200:
            result = response.json()
            data_cache.set(cache_key, result)
            return result
        return {}
    except:
        return {}

def send_webhook_signal(action, symbol, message="Manual signal from dashboard"):
    """수동으로 웹훅 신호 전송"""
    try:
        data = {
            "action": action,
            "symbol": symbol,
            "message": message
        }
        response = requests.post(
            f"{MAIN_SERVER_URL}/webhook",
            json=data,
            headers={'Content-Type': 'application/json'},
            timeout=10
        )
        return response.status_code == 200, response.json() if response.status_code == 200 else response.text
    except Exception as e:
        return False, str(e)

# ============ Display Functions ============
def display_ai_trading_history():
    """AI 트레이딩 히스토리 표시"""
    st.header("🤖 AI Trading History")
    
    # 새로고침 버튼
    col1, col2, col3 = st.columns([1, 1, 4])
    with col1:
        if st.button("🔄 Refresh History", use_container_width=True):
            data_cache.clear("ai_decisions")
            st.rerun()
    
    with col2:
        limit = st.selectbox("Records", [50, 100, 200, 500], index=0)
    
    with col3:
        symbol_filter = st.text_input("Filter by Symbol (e.g., BTC/USDT)")
    
    # AI 의사결정 기록 가져오기
    df = get_ai_decisions_from_db(limit)
    
    if symbol_filter:
        df = df[df['symbol'].str.contains(symbol_filter, case=False)]
    
    if not df.empty:
        # 통계 표시
        col1, col2, col3, col4, col5 = st.columns(5)
        
        with col1:
            total_decisions = len(df)
            st.metric("Total Decisions", total_decisions)
        
        with col2:
            approved = len(df[df['ai_decision'] == 'approve'])
            st.metric("Approved", approved)
        
        with col3:
            rejected = len(df[df['ai_decision'] == 'reject'])
            st.metric("Rejected", rejected)
        
        with col4:
            modified = len(df[df['ai_decision'] == 'modify'])
            st.metric("Modified", modified)
        
        with col5:
            avg_confidence = df['confidence'].mean() * 100 if 'confidence' in df.columns else 0
            st.metric("Avg Confidence", f"{avg_confidence:.1f}%")
        
        st.divider()
        
        # 최근 결정 표시
        st.subheader("📋 Recent AI Decisions")
        
        for idx, row in df.head(10).iterrows():
            with st.expander(f"{row['timestamp']} - {row['symbol']} - {row['ai_decision'].upper()}", expanded=False):
                col1, col2 = st.columns(2)
                
                with col1:
                    st.write(f"**Decision:** {row['ai_decision']}")
                    st.write(f"**Action:** {row['action']}")
                    st.write(f"**Position Size:** {row['percentage']}%")
                    st.write(f"**Confidence:** {row['confidence']*100:.1f}%")
                
                with col2:
                    st.write(f"**Stop Loss:** ${row['stop_loss']:,.2f}")
                    st.write(f"**Take Profit:** ${row['take_profit']:,.2f}")
                    st.write(f"**P/L Ratio:** {row['pl_ratio']:.2f}")
                
                st.write("**Reason:**")
                st.info(row['reason'])
                
                if pd.notna(row['reflection']) and row['reflection']:
                    st.write("**Reflection Applied:**")
                    st.text_area("", row['reflection'], height=100, disabled=True, key=f"refl_{idx}")
        
        # 전체 데이터 테이블
        st.subheader("📊 Full Decision History")
        
        # 표시할 컬럼 선택
        display_columns = ['timestamp', 'symbol', 'ai_decision', 'action', 'confidence', 'percentage', 'pl_ratio']
        display_df = df[display_columns].copy()
        display_df['confidence'] = (display_df['confidence'] * 100).round(1).astype(str) + '%'
        
        st.dataframe(display_df, use_container_width=True, height=400)
        
    else:
        st.info("No AI trading history available")

def display_reflection_analysis():
    """Reflection 분석 표시"""
    st.header("📖 AI Reflection & Learning")
    
    col1, col2 = st.columns([3, 1])
    with col1:
        selected_symbol = st.selectbox(
            "Select Symbol (or All)",
            ["All"] + list(get_symbol_config().keys()),
            index=0
        )
    with col2:
        limit = st.selectbox("Reflections to show", [5, 10, 20, 50], index=1)
    
    # Reflection 데이터 가져오기
    symbol_filter = None if selected_symbol == "All" else selected_symbol
    df = get_reflection_history(symbol_filter, limit)
    
    if not df.empty:
        st.subheader(f"🔍 Reflection History for {selected_symbol}")
        
        for idx, row in df.iterrows():
            timestamp = pd.to_datetime(row['timestamp']).strftime('%Y-%m-%d %H:%M:%S')
            
            with st.expander(f"📝 {timestamp} - {row['symbol']}", expanded=idx==0):
                # Reflection 내용을 구조화하여 표시
                reflection_text = row['reflection']
                
                # Reflection이 구조화된 형식인지 확인
                if "Performance Summary" in reflection_text:
                    # 구조화된 Reflection 파싱
                    sections = reflection_text.split('\n\n')
                    
                    for section in sections:
                        if section.strip():
                            if section.startswith("**"):
                                st.markdown(section)
                            elif section.startswith("1.") or section.startswith("2.") or section.startswith("3.") or section.startswith("4."):
                                st.markdown(section)
                            else:
                                st.text(section)
                else:
                    # 일반 텍스트 Reflection
                    st.text_area("", reflection_text, height=200, disabled=True, key=f"reflection_{idx}")
                
                st.divider()
                
                # 해당 시점의 거래 통계 표시
                trades_around = get_trades_from_db(row['symbol'], 20)
                if not trades_around.empty:
                    trades_around['timestamp'] = pd.to_datetime(trades_around['timestamp'])
                    recent_trades = trades_around[trades_around['timestamp'] <= pd.to_datetime(row['timestamp'])]
                    
                    if not recent_trades.empty:
                        col1, col2, col3 = st.columns(3)
                        with col1:
                            approved_count = len(recent_trades[recent_trades['ai_decision'] == 'approve'])
                            st.metric("Recent Approvals", approved_count)
                        with col2:
                            rejected_count = len(recent_trades[recent_trades['ai_decision'] == 'reject'])
                            st.metric("Recent Rejections", rejected_count)
                        with col3:
                            if 'confidence' in recent_trades.columns:
                                avg_conf = recent_trades['confidence'].mean() * 100
                                st.metric("Avg Confidence", f"{avg_conf:.1f}%")
    else:
        st.info("No reflection history available")

def display_ai_performance_metrics():
    """AI 성과 메트릭 표시"""
    st.header("📊 AI Performance Metrics")
    
    # AI 성과 데이터 가져오기
    performance = get_ai_performance()
    
    if performance:
        # 전체 통계
        st.subheader("Overall Statistics")
        
        total_stats = performance.get('total_statistics', {})
        
        col1, col2, col3, col4, col5 = st.columns(5)
        
        with col1:
            st.metric("Total Trades", total_stats.get('total_trades', 0))
        
        with col2:
            st.metric("Approved", total_stats.get('approved', 0))
        
        with col3:
            st.metric("Rejected", total_stats.get('rejected', 0))
        
        with col4:
            st.metric("Modified", total_stats.get('modified', 0))
        
        with col5:
            st.metric("Avg Confidence", total_stats.get('average_confidence', '0%'))
        
        st.divider()
        
        # 심볼별 통계
        symbol_stats = performance.get('symbol_statistics', [])
        
        if symbol_stats:
            st.subheader("Performance by Symbol")
            
            # 데이터프레임 생성
            df = pd.DataFrame(symbol_stats)
            
            # 차트 생성
            col1, col2 = st.columns(2)
            
            with col1:
                fig = px.bar(df, x='symbol', y='trades', 
                            title='Trades by Symbol',
                            color='trades',
                            color_continuous_scale='viridis')
                st.plotly_chart(fig, use_container_width=True)
            
            with col2:
                # 승인율 계산
                if 'approved' in df.columns and 'trades' in df.columns:
                    df['approval_rate'] = (df['approved'] / df['trades'] * 100).round(1)
                    
                    fig = px.bar(df, x='symbol', y='approval_rate',
                                title='Approval Rate by Symbol (%)',
                                color='approval_rate',
                                color_continuous_scale=['red', 'yellow', 'green'])
                    st.plotly_chart(fig, use_container_width=True)
            
            # 테이블
            st.dataframe(df, use_container_width=True)
        
        # 시간별 분석
        st.divider()
        st.subheader("📈 Time-based Analysis")
        
        # 최근 거래 데이터로 시간별 분석
        df_trades = get_ai_decisions_from_db(200)
        
        if not df_trades.empty:
            df_trades['timestamp'] = pd.to_datetime(df_trades['timestamp'])
            df_trades['hour'] = df_trades['timestamp'].dt.hour
            df_trades['date'] = df_trades['timestamp'].dt.date
            
            col1, col2 = st.columns(2)
            
            with col1:
                # 시간대별 거래 분포
                hourly_counts = df_trades.groupby('hour').size().reset_index(name='count')
                fig = px.line(hourly_counts, x='hour', y='count',
                            title='Trades by Hour of Day',
                            markers=True)
                fig.update_xaxes(dtick=1)
                st.plotly_chart(fig, use_container_width=True)
            
            with col2:
                # 일별 거래 추이
                daily_counts = df_trades.groupby('date').size().reset_index(name='count')
                daily_counts = daily_counts.tail(30)  # 최근 30일
                fig = px.line(daily_counts, x='date', y='count',
                            title='Daily Trading Activity (Last 30 days)',
                            markers=True)
                st.plotly_chart(fig, use_container_width=True)
            
            # 결정별 신뢰도 분포
            st.subheader("🎯 Confidence Distribution by Decision")
            
            if 'confidence' in df_trades.columns:
                fig = px.box(df_trades, x='ai_decision', y='confidence',
                            title='Confidence Distribution by AI Decision',
                            color='ai_decision',
                            color_discrete_map={
                                'approve': 'green',
                                'reject': 'red',
                                'modify': 'yellow'
                            })
                fig.update_yaxis(tickformat='.0%')
                st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No AI performance data available")

def display_ai_decision_simulator():
    """AI 의사결정 시뮬레이터"""
    st.header("🎮 AI Decision Simulator")
    
    st.info("Test how the AI would respond to different market signals")
    
    col1, col2 = st.columns(2)
    
    with col1:
        symbol = st.selectbox("Symbol", list(get_symbol_config().keys()))
        action = st.selectbox("Proposed Action", ["buy", "sell", "close"])
    
    with col2:
        confidence_threshold = st.slider("Min Confidence for Approval", 0.0, 1.0, 0.6, 0.1)
        st.write(f"Threshold: {confidence_threshold*100:.0f}%")
    
    if st.button("🔮 Simulate AI Decision", type="primary"):
        with st.spinner("Simulating AI decision..."):
            # 실제 웹훅 신호 전송
            success, result = send_webhook_signal(action, symbol, "Simulated signal from dashboard")
            
            if success:
                st.success("AI Decision Simulation Complete!")
                
                # 결과 표시
                col1, col2 = st.columns(2)
                
                with col1:
                    st.write("**Response:**")
                    st.json(result)
                
                with col2:
                    if 'ai_confidence' in result:
                        confidence = result['ai_confidence']
                        
                        # 게이지 차트
                        fig = go.Figure(go.Indicator(
                            mode = "gauge+number",
                            value = confidence * 100,
                            title = {'text': "AI Confidence"},
                            domain = {'x': [0, 1], 'y': [0, 1]},
                            gauge = {
                                'axis': {'range': [None, 100]},
                                'bar': {'color': "green" if confidence >= confidence_threshold else "red"},
                                'steps': [
                                    {'range': [0, 50], 'color': "lightgray"},
                                    {'range': [50, 80], 'color': "gray"}],
                                'threshold': {
                                    'line': {'color': "red", 'width': 4},
                                    'thickness': 0.75,
                                    'value': confidence_threshold * 100}}))
                        
                        fig.update_layout(height=200)
                        st.plotly_chart(fig, use_container_width=True)
            else:
                st.error(f"Simulation failed: {result}")

def display_ai_insights():
    """AI 인사이트 대시보드"""
    st.header("💡 AI Trading Insights")
    
    # 탭 생성
    tab1, tab2, tab3, tab4 = st.tabs([
        "📊 Performance Metrics",
        "📖 Reflection Analysis",
        "📜 Decision History",
        "🎮 Simulator"
    ])
    
    with tab1:
        display_ai_performance_metrics()
    
    with tab2:
        display_reflection_analysis()
    
    with tab3:
        display_ai_trading_history()
    
    with tab4:
        display_ai_decision_simulator()

def display_realtime_ai_status():
    """실시간 AI 상태 표시"""
    st.subheader("🤖 AI System Status")
    
    col1, col2, col3, col4 = st.columns(4)
    
    # 최근 AI 결정 통계
    recent_decisions = get_ai_decisions_from_db(20)
    
    if not recent_decisions.empty:
        with col1:
            last_decision = recent_decisions.iloc[0]
            time_diff = (datetime.now() - pd.to_datetime(last_decision['timestamp'])).total_seconds() / 60
            st.metric("Last AI Decision", f"{time_diff:.0f} min ago")
        
        with col2:
            recent_approvals = len(recent_decisions[recent_decisions['ai_decision'] == 'approve'])
            recent_total = len(recent_decisions)
            approval_rate = (recent_approvals / recent_total * 100) if recent_total > 0 else 0
            st.metric("Recent Approval Rate", f"{approval_rate:.1f}%")
        
        with col3:
            avg_confidence = recent_decisions['confidence'].mean() * 100
            st.metric("Recent Avg Confidence", f"{avg_confidence:.1f}%")
        
        with col4:
            unique_symbols = recent_decisions['symbol'].nunique()
            st.metric("Active Symbols", unique_symbols)
    else:
        st.info("No recent AI decisions")

def main():
    st.title("🤖 AI-Powered Trading System Dashboard")
    
    # 자동 새로고침 설정
    auto_refresh = st.sidebar.checkbox("🔄 Auto Refresh (30 seconds)", value=False)
    
    if auto_refresh:
        refresh_placeholder = st.sidebar.empty()
        for seconds in range(30, 0, -1):
            refresh_placeholder.write(f"⏰ Refreshing in {seconds} seconds...")
            time.sleep(1)
        refresh_placeholder.write("🔄 Refreshing now...")
        data_cache.clear()
        st.rerun()
    
    # 서버 상태 확인
    health_status, server_data = check_middle_server_health()
    
    if not health_status:
        st.error("❌ Trading System Offline")
        st.info("Please check if integrated_trading_system.py is running on port 5000")
        st.stop()
    
    # 메인 탭
    tab1, tab2, tab3 = st.tabs([
        "🎯 AI Insights",
        "📊 Trading Overview", 
        "⚙️ System Config"
    ])
    
    with tab1:
        # 실시간 AI 상태
        display_realtime_ai_status()
        st.divider()
        # AI 인사이트
        display_ai_insights()
    
    with tab2:
        st.header("📊 Trading Overview")
        
        # 서버 정보
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("System Status", "🟢 Online" if health_status else "🔴 Offline")
        
        with col2:
            positions = len(server_data.get('current_positions', {})) if server_data else 0
            st.metric("Active Positions", positions)
        
        with col3:
            enabled_symbols = len([s for s, c in server_data.get('symbols', {}).items()])
            st.metric("Active Symbols", enabled_symbols)
        
        with col4:
            st.metric("Server Time", datetime.now().strftime('%H:%M:%S'))
        
        st.divider()
        
        # 현재 포지션 표시
        if server_data and server_data.get('current_positions'):
            st.subheader("📈 Current Positions")
            
            positions_df = []
            for symbol, pos in server_data['current_positions'].items():
                positions_df.append({
                    'Symbol': symbol,
                    'Side': pos.get('side', 'N/A'),
                    'Entry Price': pos.get('entry_price', 0),
                    'Amount': pos.get('amount', 0),
                    'Stop Loss': pos.get('stop_loss', 0),
                    'Take Profit': pos.get('take_profit', 0)
                })
            
            if positions_df:
                df = pd.DataFrame(positions_df)
                st.dataframe(df, use_container_width=True)
        else:
            st.info("No active positions")
    
    with tab3:
        st.header("⚙️ System Configuration")
        
        # 심볼 설정
        config = get_symbol_config()
        
        if config:
            st.subheader("Symbol Configuration")
            
            config_df = []
            for symbol, settings in config.items():
                config_df.append({
                    'Symbol': symbol,
                    'Enabled': '✅' if settings.get('enabled', True) else '❌',
                    'AI Validation': '✅' if settings.get('ai_validation', True) else '❌',
                    'Leverage': settings.get('leverage', 10),
                    'Position Size %': settings.get('position_size_percent', 10)
                })
            
            if config_df:
                df = pd.DataFrame(config_df)
                st.dataframe(df, use_container_width=True, height=400)
        else:
            st.info("No configuration available")
        
        # AI 성과 요약
        st.divider()
        performance = get_ai_performance()
        if performance:
            st.subheader("AI Performance Summary")
            st.json(performance.get('total_statistics', {}))
    
    # 사이드바 정보
    with st.sidebar:
        st.header("ℹ️ System Info")
        
        # 캐시 관리
        st.write(f"**Cache TTL:** 30 seconds")
        if st.button("🗑️ Clear Cache", use_container_width=True):
            data_cache.clear()
            st.success("Cache cleared!")
            time.sleep(0.5)
            st.rerun()
        
        st.divider()
        
        # 서버 상태
        if health_status and server_data:
            st.write("**Server Status:** 🟢 Online")
            st.write(f"**Port:** 5000")
            st.write(f"**Telegram:** {'🔔 On' if server_data.get('telegram_enabled') else '🔕 Off'}")
            
            st.divider()
            
            # 빠른 통계
            st.write("**Quick Stats:**")
            
            # 최근 AI 결정
            recent = get_ai_decisions_from_db(10)
            if not recent.empty:
                approved = len(recent[recent['ai_decision'] == 'approve'])
                rejected = len(recent[recent['ai_decision'] == 'reject'])
                
                st.write(f"Last 10 decisions:")
                st.write(f"• ✅ Approved: {approved}")
                st.write(f"• ❌ Rejected: {rejected}")
                
                avg_conf = recent['confidence'].mean() * 100
                st.write(f"• 🎯 Avg Confidence: {avg_conf:.1f}%")
        
        st.divider()
        
        # 사용 가이드
        st.markdown("""
        ### 📖 Dashboard Guide
        
        **AI Insights:**
        - Performance metrics
        - Reflection analysis
        - Decision history
        - Simulator
        
        **Trading Overview:**
        - Current positions
        - Real-time status
        
        **System Config:**
        - Symbol settings
        - AI validation status
        
        ---
        
        **Key Features:**
        - 🤖 AI decision validation
        - 📖 Learning from reflections
        - 📊 Performance tracking
        - 🎮 Decision simulation
        """)

if __name__ == "__main__":
    main()
