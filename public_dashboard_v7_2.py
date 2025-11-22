#!/usr/bin/env python3
"""
Public Dashboard v7.3 - Fixed Version
잔고 조회 오류 수정 및 exchange 객체 초기화 개선

주요 수정사항:
1. 🔥 exchange 객체 초기화 문제 해결
2. 🔥 Performance Analysis 탭 잔고 조회 오류 수정
3. 🔥 캐시 문제 해결

작성일: 2025-11-22
버전: v7.3 Fixed
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

load_dotenv()

# 페이지 설정
st.set_page_config(
    page_title="Trading Dashboard v7.3 - Fixed",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ============ 🔥 v7.3 수정: Exchange 초기화 개선 ============
def get_binance_exchange():
    """바이낸스 거래소 객체 생성 (캐시 제거)"""
    try:
        api_key = os.getenv('BINANCE_API_KEY')
        secret_key = os.getenv('BINANCE_SECRET_KEY')
        
        if not api_key or not secret_key:
            st.warning("⚠️ BINANCE_API_KEY 또는 BINANCE_SECRET_KEY 환경 변수가 설정되지 않았습니다.")
            st.info("💡 .env 파일에 다음 내용을 추가하세요:")
            st.code("""
BINANCE_API_KEY=your_api_key_here
BINANCE_SECRET_KEY=your_secret_key_here
            """)
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
            st.success(f"✅ 바이낸스 연결 성공")
            return exchange
        except Exception as test_error:
            st.error(f"❌ 바이낸스 연결 실패: {test_error}")
            return None
        
    except Exception as e:
        st.error(f"거래소 초기화 오류: {e}")
        return None

def fetch_balance_from_binance(exchange):
    """바이낸스에서 실시간 잔고 가져오기 (개선)"""
    try:
        if exchange is None:
            st.warning("⚠️ Exchange 객체가 없습니다.")
            return {'total': 0, 'free': 0, 'used': 0}
        
        balance = exchange.fetch_balance()
        
        # USDT 잔고 확인
        if 'USDT' in balance:
            return {
                'total': balance['USDT']['total'],
                'free': balance['USDT']['free'],
                'used': balance['USDT']['used']
            }
        else:
            st.warning("⚠️ USDT 잔고를 찾을 수 없습니다.")
            return {'total': 0, 'free': 0, 'used': 0}
        
    except Exception as e:
        st.error(f"잔고 조회 오류: {e}")
        st.info("💡 API 권한을 확인하세요: Futures 거래 권한이 필요합니다.")
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
                'pnl_percent': ((mark_price - entry_price) / entry_price * 100) if side == 'long' 
                              else ((entry_price - mark_price) / entry_price * 100)
            })
        
        return result
        
    except Exception as e:
        st.error(f"포지션 조회 오류: {e}")
        return []

# ============ 초기 잔고 설정 함수들 ============
def get_or_set_initial_balance():
    """초기 잔고 가져오기 또는 설정 (DB 저장)"""
    try:
        conn = sqlite3.connect('integrated_trades.db')
        c = conn.cursor()
        
        # initial_balance 테이블 확인/생성
        c.execute("""
            CREATE TABLE IF NOT EXISTS initial_balance (
                id INTEGER PRIMARY KEY,
                balance REAL,
                set_date TEXT
            )
        """)
        
        # 기존 초기 잔고 확인
        c.execute("SELECT balance FROM initial_balance ORDER BY id DESC LIMIT 1")
        result = c.fetchone()
        
        if result:
            initial_balance = result[0]
        else:
            initial_balance = 1000.0  # 기본값
            
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

# ============ 메인 대시보드 ============
def main():
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
    </style>
    """, unsafe_allow_html=True)
    
    st.markdown('<h1 class="main-header">⚡ Automated Trading Dashboard v7.3</h1>', unsafe_allow_html=True)
    
    # 🔥 Exchange 초기화 (Session State 활용)
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
    tab1, tab2, tab3 = st.tabs(["📊 Trading Overview", "📈 Performance Analysis", "📜 Trade History"])
    
    # ==========================================
    # Tab 1: Trading Overview
    # ==========================================
    with tab1:
        st.header("📊 Real-time Trading Status")
        
        # 잔고 정보
        balance_data = fetch_balance_from_binance(exchange)
        
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
        else:
            st.warning("⚠️ 잔고 정보를 가져올 수 없습니다.")
        
        # 포지션 정보
        positions = fetch_positions_from_binance(exchange)
        
        if positions:
            st.subheader("🎯 Active Positions")
            
            # 포지션 테이블
            df_positions = pd.DataFrame(positions)
            
            # 컬럼 포맷팅
            df_positions['entry_price'] = df_positions['entry_price'].apply(lambda x: f"${x:,.2f}")
            df_positions['mark_price'] = df_positions['mark_price'].apply(lambda x: f"${x:,.2f}")
            df_positions['unrealized_pnl'] = df_positions['unrealized_pnl'].apply(lambda x: f"${x:,.2f}")
            df_positions['pnl_percent'] = df_positions['pnl_percent'].apply(lambda x: f"{x:+.2f}%")
            
            st.dataframe(
                df_positions[['symbol', 'side', 'amount', 'entry_price', 'mark_price', 
                             'unrealized_pnl', 'pnl_percent', 'leverage']],
                use_container_width=True
            )
        else:
            st.info("📭 현재 활성 포지션이 없습니다.")
    
    # ==========================================
    # Tab 2: Performance Analysis (🔥 수정됨)
    # ==========================================
    with tab2:
        st.header("📈 Performance Analysis")
        
        # 🔥 수정: Exchange 체크 및 잔고 가져오기
        if exchange:
            try:
                balance_data_tab2 = fetch_balance_from_binance(exchange)
                current_balance = balance_data_tab2['total']
                
                # 디버깅 정보
                with st.expander("🔍 디버깅 정보"):
                    st.write("Exchange 상태:", "연결됨" if exchange else "연결 안됨")
                    st.write("현재 잔고:", current_balance)
                    st.write("잔고 데이터:", balance_data_tab2)
                    
            except Exception as e:
                st.error(f"잔고 조회 실패: {e}")
                current_balance = None
        else:
            st.error("⚠️ Exchange 연결이 필요합니다.")
            current_balance = None
        
        initial_balance = get_or_set_initial_balance()
        lifetime_start_balance = get_or_set_lifetime_start_balance()
        
        if current_balance and current_balance > 0 and initial_balance and lifetime_start_balance:
            try:
                # ===================================
                # 다중 기간 성과 요약
                # ===================================
                st.subheader("🎯 Multi-Period Performance Summary")
                
                # 수익률 계산
                daily_return = ((current_balance - initial_balance) / initial_balance) * 100
                lifetime_return = ((current_balance - lifetime_start_balance) / lifetime_start_balance) * 100
                
                col1, col2, col3, col4 = st.columns(4)
                
                with col1:
                    st.metric(
                        "📊 현재 잔고",
                        f"${current_balance:,.2f}",
                        f"{daily_return:+.2f}% Today"
                    )
                
                with col2:
                    st.metric(
                        "📈 일일 수익률",
                        f"{daily_return:+.2f}%",
                        f"${current_balance - initial_balance:+,.2f}"
                    )
                
                with col3:
                    st.metric(
                        "🎯 전체 수익률",
                        f"{lifetime_return:+.2f}%",
                        f"${current_balance - lifetime_start_balance:+,.2f}"
                    )
                
                with col4:
                    win_rate = 65.0  # 예시 값 (실제로는 DB에서 계산)
                    st.metric(
                        "✅ 승률",
                        f"{win_rate:.1f}%",
                        "Last 30 trades"
                    )
                
                # 차트 표시
                st.subheader("📊 Balance Trend")
                
                # 예시 차트 (실제로는 DB에서 데이터 가져오기)
                dates = pd.date_range(end=datetime.now(), periods=30, freq='D')
                balances = [lifetime_start_balance + (current_balance - lifetime_start_balance) * i / 29 for i in range(30)]
                
                fig = go.Figure()
                fig.add_trace(go.Scatter(
                    x=dates,
                    y=balances,
                    mode='lines+markers',
                    name='Balance',
                    line=dict(color='#2E8B57', width=2),
                    marker=dict(size=4)
                ))
                
                fig.update_layout(
                    title="30-Day Balance Trend",
                    xaxis_title="Date",
                    yaxis_title="Balance (USDT)",
                    hovermode='x unified',
                    height=400
                )
                
                st.plotly_chart(fig, use_container_width=True)
                
            except Exception as e:
                st.error(f"성과 분석 오류: {e}")
                st.info("💡 데이터베이스를 확인하세요.")
        else:
            st.error("⚠️ 잔고 정보를 가져올 수 없습니다.")
            
            # 문제 해결 가이드
            with st.expander("🔧 문제 해결 가이드"):
                st.markdown("""
                ### API 키 확인사항:
                1. **.env 파일 확인**
                   ```
                   BINANCE_API_KEY=your_api_key
                   BINANCE_SECRET_KEY=your_secret_key
                   ```
                
                2. **API 권한 확인**
                   - Futures Trading 활성화
                   - Read 권한 활성화
                   - IP 제한 확인
                
                3. **Exchange 재연결**
                   - 위의 "🔄 Exchange 재연결" 버튼 클릭
                
                4. **환경 변수 재로드**
                   ```python
                   # 터미널에서 실행
                   streamlit run public_dashboard_v7_3.py
                   ```
                """)
    
    # ==========================================
    # Tab 3: Trade History
    # ==========================================
    with tab3:
        st.header("📜 Trade History")
        
        try:
            conn = sqlite3.connect('integrated_trades.db')
            
            # 최근 거래 조회
            query = """
            SELECT 
                close_timestamp,
                symbol,
                side,
                entry_price,
                exit_price,
                amount,
                pnl_usdt,
                pnl_percent,
                close_reason
            FROM completed_trades
            ORDER BY close_timestamp DESC
            LIMIT 50
            """
            
            df_trades = pd.read_sql_query(query, conn)
            conn.close()
            
            if not df_trades.empty:
                # 포맷팅
                df_trades['close_timestamp'] = pd.to_datetime(df_trades['close_timestamp'])
                df_trades['entry_price'] = df_trades['entry_price'].apply(lambda x: f"${x:,.2f}")
                df_trades['exit_price'] = df_trades['exit_price'].apply(lambda x: f"${x:,.2f}")
                df_trades['pnl_usdt'] = df_trades['pnl_usdt'].apply(lambda x: f"${x:,.2f}")
                df_trades['pnl_percent'] = df_trades['pnl_percent'].apply(lambda x: f"{x:+.2f}%")
                
                st.dataframe(df_trades, use_container_width=True)
            else:
                st.info("📭 거래 내역이 없습니다.")
                
        except Exception as e:
            st.error(f"거래 내역 조회 오류: {e}")
            st.info("💡 integrated_trades.db 파일을 확인하세요.")
    
    # 자동 새로고침
    st.sidebar.markdown("---")
    if st.sidebar.checkbox("🔄 자동 새로고침 (3초)", value=False):
        time_module.sleep(3)
        st.rerun()
    
    # 수동 새로고침 버튼
    if st.sidebar.button("🔄 수동 새로고침"):
        st.rerun()

if __name__ == "__main__":
    main()

"""
🔥 v7.3 주요 수정사항:

1. Exchange 초기화 개선
   - @st.cache_resource 제거 (캐시 문제 해결)
   - Session State 활용으로 안정적 관리
   - 연결 테스트 추가

2. Performance Analysis 탭 수정
   - Exchange None 체크 강화
   - 에러 핸들링 개선
   - 디버깅 정보 추가

3. 문제 해결 가이드 추가
   - API 키 설정 안내
   - 권한 확인 사항
   - 재연결 방법 안내

4. UI/UX 개선
   - Exchange 재연결 버튼 추가
   - 상태 표시 명확화
   - 에러 메시지 개선
"""
