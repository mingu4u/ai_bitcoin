import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import requests
import json
from datetime import datetime, timedelta
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

# Middle Server 설정 - 다중 포트 지원
MIDDLE_SERVER_PORTS = [5000, 5001, 5002]
MIDDLE_SERVER_BASE_URL = "http://localhost"

# 메인 서버는 5000번 포트
MAIN_SERVER_URL = f"{MIDDLE_SERVER_BASE_URL}:5000"

# 페이지 설정
st.set_page_config(
    page_title="Multi-Symbol Trading Bot Dashboard",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded"
)

def check_middle_server_health():
    """Middle Server 상태 확인"""
    try:
        response = requests.get(f"{MAIN_SERVER_URL}/status", timeout=2)
        if response.status_code == 200:
            return True, response.json()
        return False, None
    except:
        return False, None

def check_all_servers_health():
    """모든 서버 상태 확인"""
    server_status = {}
    
    for port in MIDDLE_SERVER_PORTS:
        try:
            response = requests.get(f"{MIDDLE_SERVER_BASE_URL}:{port}/status", timeout=2)
            if response.status_code == 200:
                server_status[port] = {
                    'status': 'online',
                    'data': response.json()
                }
            else:
                server_status[port] = {'status': 'error', 'data': None}
        except:
            server_status[port] = {'status': 'offline', 'data': None}
    
    return server_status

def get_all_positions():
    """모든 심볼의 포지션 정보 가져오기"""
    try:
        response = requests.get(f"{MAIN_SERVER_URL}/positions", timeout=5)
        if response.status_code == 200:
            return response.json()
        return None
    except:
        return None

def get_symbol_config():
    """심볼 설정 가져오기 (메인 서버에서만)"""
    try:
        response = requests.get(f"{MAIN_SERVER_URL}/config", timeout=5)
        if response.status_code == 200:
            return response.json()
        return None
    except:
        return None

def get_all_servers_config():
    """모든 서버의 심볼 설정 가져오기"""
    configs = {}
    
    for port in MIDDLE_SERVER_PORTS:
        try:
            response = requests.get(f"{MIDDLE_SERVER_BASE_URL}:{port}/config", timeout=5)
            if response.status_code == 200:
                configs[port] = response.json()
            else:
                configs[port] = None
        except:
            configs[port] = None
    
    return configs

def update_symbol_config_all_servers(config):
    """모든 서버에 심볼 설정 업데이트"""
    results = {}
    
    def update_single_server(port):
        try:
            response = requests.post(
                f"{MIDDLE_SERVER_BASE_URL}:{port}/config",
                json=config,
                headers={'Content-Type': 'application/json'},
                timeout=5
            )
            if response.status_code == 200:
                return port, True, response.json()
            return port, False, None
        except Exception as e:
            return port, False, str(e)
    
    # 병렬로 모든 서버에 업데이트
    with ThreadPoolExecutor(max_workers=len(MIDDLE_SERVER_PORTS)) as executor:
        futures = [executor.submit(update_single_server, port) for port in MIDDLE_SERVER_PORTS]
        
        for future in as_completed(futures):
            port, success, result = future.result()
            results[port] = {'success': success, 'result': result}
    
    return results

def sync_positions():
    """포지션 동기화 실행"""
    try:
        response = requests.post(f"{MAIN_SERVER_URL}/sync", timeout=5)
        if response.status_code == 200:
            return True, response.json()
        return False, None
    except:
        return False, None

def test_telegram():
    """텔레그램 알림 테스트"""
    try:
        response = requests.post(f"{MAIN_SERVER_URL}/test-telegram", timeout=5)
        if response.status_code == 200:
            return True, response.json()
        return False, None
    except:
        return False, None

def close_position_manually(symbol):
    """수동으로 포지션 종료"""
    try:
        data = {
            "action": "close_position",
            "symbol": symbol
        }
        response = requests.post(
            f"{MAIN_SERVER_URL}/webhook",
            json=data,
            headers={'Content-Type': 'application/json'},
            timeout=5
        )
        if response.status_code == 200:
            return True, response.json()
        return False, None
    except:
        return False, None

def display_server_status():
    """모든 서버 상태 표시"""
    st.subheader("🖥️ Server Status")
    
    server_status = check_all_servers_health()
    
    cols = st.columns(len(MIDDLE_SERVER_PORTS))
    
    for idx, port in enumerate(MIDDLE_SERVER_PORTS):
        with cols[idx]:
            status = server_status.get(port, {})
            
            if status.get('status') == 'online':
                st.success(f"✅ Port {port}")
                data = status.get('data', {})
                telegram_status = "🔔" if data.get('telegram_enabled') else "🔕"
                st.write(f"{telegram_status} Telegram: {'On' if data.get('telegram_enabled') else 'Off'}")
                st.write(f"📊 Positions: {len(data.get('current_positions', {}))}")
            elif status.get('status') == 'error':
                st.error(f"⚠️ Port {port}")
                st.write("Server error")
            else:
                st.error(f"❌ Port {port}")
                st.write("Offline")

def display_symbol_config():
    """심볼 설정 관리 UI (다중 서버 지원)"""
    st.header("⚙️ Symbol Configuration (All Servers)")
    
    # 서버 상태 표시
    display_server_status()
    
    st.divider()
    
    # 모든 서버의 설정 가져오기
    all_configs = get_all_servers_config()
    
    # 메인 서버(5000)의 설정을 기준으로 사용
    main_config = all_configs.get(5000)
    
    if not main_config:
        st.error("Failed to load configuration from main server (port 5000)")
        return
    
    # 설정 동기화 상태 체크
    config_synced = True
    for port, config in all_configs.items():
        if config != main_config:
            config_synced = False
            break
    
    if config_synced:
        st.success("✅ All servers have synchronized configurations")
    else:
        st.warning("⚠️ Server configurations are not synchronized")
        
        if st.button("🔄 Sync All Servers with Main Config"):
            results = update_symbol_config_all_servers(main_config)
            
            success_count = sum(1 for r in results.values() if r['success'])
            total_count = len(results)
            
            if success_count == total_count:
                st.success(f"✅ Successfully synchronized all {total_count} servers!")
            else:
                st.warning(f"⚠️ Synchronized {success_count}/{total_count} servers")
                
                for port, result in results.items():
                    if not result['success']:
                        st.error(f"Failed to update port {port}: {result['result']}")
            
            time.sleep(2)
            st.rerun()
    
    st.divider()
    
    # 기존 심볼 설정
    st.subheader("📊 Existing Symbols")
    
    for symbol, settings in main_config.items():
        with st.expander(f"{symbol} Settings"):
            col1, col2, col3 = st.columns(3)
            
            with col1:
                leverage = st.number_input(
                    "Leverage",
                    min_value=1,
                    max_value=125,
                    value=settings.get('leverage', 10),
                    key=f"leverage_{symbol}"
                )
                enabled = st.checkbox(
                    "Enabled",
                    value=settings.get('enabled', True),
                    key=f"enabled_{symbol}"
                )
            
            with col2:
                position_size = st.number_input(
                    "Position Size %",
                    min_value=1.0,
                    max_value=100.0,
                    value=float(settings.get('position_size_percent', 10)),
                    step=1.0,
                    key=f"pos_size_{symbol}"
                )
                min_size = st.number_input(
                    "Min Position Size ($)",
                    min_value=1.0,
                    value=float(settings.get('min_position_size', 10)),
                    key=f"min_size_{symbol}"
                )
            
            with col3:
                max_size = st.number_input(
                    "Max Position Size ($)",
                    min_value=1.0,
                    value=float(settings.get('max_position_size', 100000)),
                    key=f"max_size_{symbol}"
                )
                
                if st.button(f"Update {symbol} (All Servers)", key=f"update_{symbol}"):
                    new_config = {
                        symbol: {
                            'leverage': leverage,
                            'position_size_percent': position_size,
                            'min_position_size': min_size,
                            'max_position_size': max_size,
                            'enabled': enabled
                        }
                    }
                    
                    # 모든 서버에 업데이트
                    results = update_symbol_config_all_servers(new_config)
                    
                    success_count = sum(1 for r in results.values() if r['success'])
                    total_count = len(results)
                    
                    if success_count == total_count:
                        st.success(f"✅ {symbol} updated on all {total_count} servers!")
                    else:
                        st.warning(f"⚠️ {symbol} updated on {success_count}/{total_count} servers")
                        
                        # 실패한 서버들 표시
                        for port, result in results.items():
                            if result['success']:
                                st.success(f"✅ Port {port}: Success")
                            else:
                                st.error(f"❌ Port {port}: Failed - {result['result']}")
                    
                    time.sleep(2)
                    st.rerun()
    
    # 새 심볼 추가
    st.subheader("➕ Add New Symbol (All Servers)")
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        new_symbol = st.text_input("Symbol (e.g., ETH/USDT)")
    
    with col2:
        new_leverage = st.number_input("Leverage", min_value=1, max_value=125, value=10)
    
    with col3:
        new_pos_size = st.number_input("Position Size %", min_value=1.0, max_value=100.0, value=10.0)
    
    with col4:
        if st.button("Add Symbol to All Servers", disabled=not new_symbol):
            if new_symbol:
                new_config = {
                    new_symbol: {
                        'leverage': new_leverage,
                        'position_size_percent': new_pos_size,
                        'min_position_size': 10,
                        'max_position_size': 100000,
                        'enabled': True
                    }
                }
                
                # 모든 서버에 추가
                results = update_symbol_config_all_servers(new_config)
                
                success_count = sum(1 for r in results.values() if r['success'])
                total_count = len(results)
                
                if success_count == total_count:
                    st.success(f"✅ {new_symbol} added to all {total_count} servers!")
                else:
                    st.warning(f"⚠️ {new_symbol} added to {success_count}/{total_count} servers")
                    
                    for port, result in results.items():
                        if result['success']:
                            st.success(f"✅ Port {port}: Added successfully")
                        else:
                            st.error(f"❌ Port {port}: Failed - {result['result']}")
                
                time.sleep(2)
                st.rerun()
    
    # 설정 상세 정보 (접힘 메뉴)
    with st.expander("🔍 Configuration Details by Server"):
        for port in MIDDLE_SERVER_PORTS:
            config = all_configs.get(port)
            st.subheader(f"Server Port {port}")
            
            if config:
                st.json(config)
            else:
                st.error(f"Failed to load configuration from port {port}")

def display_portfolio_overview():
    """포트폴리오 전체 개요 표시"""
    st.subheader("💰 Portfolio Overview")
    
    positions_data = get_all_positions()
    
    if not positions_data:
        st.warning("No position data available")
        return
    
    # 전체 통계 계산
    total_pnl = 0
    active_positions = 0
    total_margin_used = 0
    
    for symbol, data in positions_data.get('positions', {}).items():
        if data.get('tracked_position'):
            active_positions += 1
            if data.get('position_info'):
                total_pnl += data['position_info'].get('unrealized_pnl', 0)
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Active Positions", active_positions)
    
    with col2:
        pnl_color = "normal" if total_pnl >= 0 else "inverse"
        st.metric("Total Unrealized PnL", f"${total_pnl:,.2f}", delta=total_pnl, delta_color=pnl_color)
    
    with col3:
        st.metric("Active Symbols", len([s for s in positions_data.get('positions', {}) if positions_data['positions'][s].get('tracked_position')]))
    
    with col4:
        st.metric("Last Update", datetime.now().strftime('%H:%M:%S'))

def display_symbol_positions(symbol, position_data):
    """특정 심볼의 포지션 정보 표시"""
    if not position_data.get('tracked_position'):
        return
    
    pos_info = position_data['tracked_position']
    market_info = position_data.get('position_info', {})
    
    with st.container():
        col1, col2, col3, col4, col5 = st.columns([2, 2, 2, 2, 1])
        
        with col1:
            side = pos_info.get('side', 'N/A').upper()
            side_emoji = "🟢" if side == 'BUY' else "🔴"
            st.write(f"{side_emoji} **{symbol}**")
            st.write(f"Side: {side}")
            st.write(f"Amount: {pos_info.get('amount', 0):.6f}")
        
        with col2:
            st.write(f"Entry: ${pos_info.get('entry_price', 0):,.2f}")
            st.write(f"Current: ${market_info.get('current_price', 0):,.2f}")
        
        with col3:
            st.write(f"SL: ${pos_info.get('stop_loss', 0):,.2f}")
            st.write(f"TP: ${pos_info.get('take_profit', 0):,.2f}")
            st.write(f"P/L Ratio: {pos_info.get('pl_ratio', 0):.1f}:1")
        
        with col4:
            pnl = market_info.get('unrealized_pnl', 0)
            pnl_pct = market_info.get('pnl_percent', 0)
            
            pnl_color = "green" if pnl >= 0 else "red"
            st.markdown(f"**PnL:** <span style='color:{pnl_color}'>${pnl:,.2f}</span>", unsafe_allow_html=True)
            st.markdown(f"**PnL %:** <span style='color:{pnl_color}'>{pnl_pct:.2f}%</span>", unsafe_allow_html=True)
            
            if pos_info.get('manual_entry'):
                st.info("🔧 Manual")
        
        with col5:
            if st.button("Close", key=f"close_{symbol}"):
                success, result = close_position_manually(symbol)
                if success:
                    st.success(f"✅ {symbol} closed!")
                    time.sleep(1)
                    st.rerun()
                else:
                    st.error(f"Failed to close {symbol}")

def display_realtime_positions():
    """실시간 포지션 정보 표시"""
    st.subheader("📊 Active Positions by Symbol")
    
    positions_data = get_all_positions()
    
    if not positions_data or not positions_data.get('positions'):
        st.info("No active positions")
        return
    
    # 활성 포지션이 있는 심볼만 필터링
    active_symbols = []
    for symbol, data in positions_data['positions'].items():
        if data.get('tracked_position'):
            active_symbols.append((symbol, data))
    
    if not active_symbols:
        st.info("No active positions")
        return
    
    # 각 심볼별로 포지션 표시
    for symbol, position_data in active_symbols:
        display_symbol_positions(symbol, position_data)
        st.divider()

def display_open_orders():
    """열린 주문 표시"""
    st.subheader("📋 Open Orders")
    
    positions_data = get_all_positions()
    
    if not positions_data:
        st.info("No data available")
        return
    
    all_orders = []
    
    for symbol, data in positions_data.get('positions', {}).items():
        if data.get('open_orders'):
            for order in data['open_orders']:
                order['symbol'] = symbol
                all_orders.append({
                    'Symbol': symbol,
                    'Type': order.get('type', 'N/A'),
                    'Side': order.get('side', 'N/A'),
                    'Amount': order.get('amount', 0),
                    'Price': order.get('price') or order.get('stopPrice', 0),
                    'Status': order.get('status', 'N/A')
                })
    
    if all_orders:
        df = pd.DataFrame(all_orders)
        st.dataframe(df, use_container_width=True)
    else:
        st.info("No open orders")

def display_realtime_section():
    """실시간 거래 정보 섹션"""
    st.header('🔴 Real-time Multi-Symbol Trading')
    
    # Health Check 상태 표시
    health_status, server_data = check_middle_server_health()
    
    if not health_status:
        st.error("❌ Server Offline")
        st.info("Please check if middle_server.py is running on port 5000")
        return
    
    col1, col2, col3 = st.columns([1, 1, 1])
    
    with col1:
        st.success("✅ Server Online")
        
        if server_data:
            symbols = server_data.get('symbols', [])
            st.metric("Active Symbols", len(symbols))
            
            # 텔레그램 상태
            if server_data.get('telegram_configured'):
                st.success("📱 Telegram: Connected")
            else:
                st.warning("📱 Telegram: Not configured")
    
    with col2:
        if st.button("🔄 Sync All Positions", use_container_width=True):
            success, data = sync_positions()
            if success:
                st.success("Synced successfully!")
                time.sleep(1)
                st.rerun()
            else:
                st.error("Sync failed")
    
    with col3:
        if st.button("📱 Test Telegram", use_container_width=True):
            success, data = test_telegram()
            if success:
                st.success("Telegram test sent!")
            else:
                st.error("Telegram test failed")
    
    # 포트폴리오 개요
    display_portfolio_overview()
    
    # 실시간 포지션 정보
    display_realtime_positions()
    
    # 열린 주문 정보
    display_open_orders()

def display_performance_by_symbol():
    """심볼별 성과 분석"""
    st.header("📈 Performance by Symbol")
    
    positions_data = get_all_positions()
    
    if not positions_data:
        st.info("No data available")
        return
    
    performance_data = []
    
    for symbol, data in positions_data.get('positions', {}).items():
        if data.get('position_info'):
            info = data['position_info']
            performance_data.append({
                'Symbol': symbol,
                'PnL ($)': info.get('unrealized_pnl', 0),
                'PnL (%)': info.get('pnl_percent', 0),
                'Current Price': info.get('current_price', 0)
            })
    
    if performance_data:
        df = pd.DataFrame(performance_data)
        
        # PnL 차트
        col1, col2 = st.columns(2)
        
        with col1:
            fig = px.bar(df, x='Symbol', y='PnL ($)', 
                        title='Unrealized PnL by Symbol',
                        color='PnL ($)',
                        color_continuous_scale=['red', 'yellow', 'green'])
            st.plotly_chart(fig, use_container_width=True)
        
        with col2:
            fig = px.bar(df, x='Symbol', y='PnL (%)', 
                        title='PnL % by Symbol',
                        color='PnL (%)',
                        color_continuous_scale=['red', 'yellow', 'green'])
            st.plotly_chart(fig, use_container_width=True)
        
        # 테이블
        st.dataframe(df, use_container_width=True)
    else:
        st.info("No active positions to analyze")

def main():
    st.title("🤖 Multi-Symbol Trading Bot Dashboard")
    
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
    tab1, tab2, tab3, tab4 = st.tabs([
        "🔴 Live Trading", 
        "⚙️ Symbol Config (Multi-Server)", 
        "📊 Performance Analysis",
        "📚 Strategy Info"
    ])
    
    with tab1:
        display_realtime_section()
    
    with tab2:
        display_symbol_config()
    
    with tab3:
        display_performance_by_symbol()
    
    with tab4:
        st.header("📚 Stochastic Fast Strategy Information")
        
        st.markdown("""
        ### 전략 개요
        
        **Stochastic Fast 교차 매매전략**은 %K와 %D 라인의 교차를 이용한 모멘텀 기반 전략입니다.
        
        #### 매매 신호
        - **매수 (Long)**: %K가 %D를 상향 돌파 (골든 크로스)
        - **매도 (Short)**: %K가 %D를 하향 돌파 (데드 크로스)
        - **포지션 종료**: 반대 신호 발생 시
        
        #### 강화 신호
        - **강매수**: 과매도 구간(20 이하)에서 상향 돌파
        - **강매도**: 과매수 구간(80 이상)에서 하향 돌파
        
        #### 리스크 관리
        - 손절매 (Stop Loss) 자동 설정
        - 익절매 (Take Profit) 자동 설정
        - 손익비 (P/L Ratio) 관리
        
        #### 지원 심볼
        - BTC/USDT (레버리지 20x)
        - SAHARA/USDT (레버리지 3x)
        - 추가 심볼 설정 가능
        
        ### 다중 서버 구조
        
        - **Port 5000**: 메인 서버 (텔레그램 알림 활성화)
        - **Port 5001**: 복제 서버 1 (텔레그램 알림 비활성화)
        - **Port 5002**: 복제 서버 2 (텔레그램 알림 비활성화)
        
        모든 서버는 동일한 설정을 공유하며, Symbol Config 탭에서 일괄 관리할 수 있습니다.
        
        ### Alert 메시지 포맷
        
        ```json
        {
            "action": "buy/sell/close_position",
            "symbol": "SAHARAUSDT.P",
            "entry_price": 50000,
            "stop_loss": 49000,
            "take_profit": 52000,
            "pl_ratio": 3.0,
            "position_type": "strong_long/long/strong_short/short"
        }
        ```
        
        ### 사용 방법
        
        1. TradingView에서 Stochastic Fast 전략 스크립트 적용
        2. Alert 설정 (Webhook URL: http://your-server/webhook-all)
        3. Symbol Config 탭에서 심볼별 레버리지 및 포지션 크기 설정 (모든 서버 동시 적용)
        4. Live Trading 탭에서 실시간 모니터링
        """)
    
    # 사이드바에 간단한 정보 표시
    with st.sidebar:
        st.header("ℹ️ System Info")
        
        # 서버 상태 확인
        server_status = check_all_servers_health()
        
        st.write("**Server Status:**")
        for port in MIDDLE_SERVER_PORTS:
            status = server_status.get(port, {})
            
            if status.get('status') == 'online':
                telegram_icon = "🔔" if status.get('data', {}).get('telegram_enabled') else "🔕"
                st.success(f"✅ Port {port} {telegram_icon}")
            elif status.get('status') == 'error':
                st.error(f"⚠️ Port {port}")
            else:
                st.error(f"❌ Port {port}")
        
        st.write("---")
        
        # 메인 서버 정보
        health_status, server_data = check_middle_server_health()
        
        if health_status and server_data:
            st.write("**Active Symbols (Main):**")
            for symbol in server_data.get('symbols', []):
                config = server_data.get('symbol_config', {}).get(symbol, {})
                if config.get('enabled', True):
                    st.write(f"• {symbol} ({config.get('leverage', 'N/A')}x)")
            
            st.write("---")
            
            # 현재 포지션 수
            current_positions = server_data.get('current_positions', {})
            st.write(f"**Active Positions:** {len(current_positions)}")
            
            for symbol, pos in current_positions.items():
                side = pos.get('side', 'N/A').upper()
                st.write(f"• {symbol}: {side}")
        
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
        
        st.write("---")
        
        # 설명
        st.markdown("""
        ### 📖 Dashboard Guide
        
        **Live Trading**: 실시간 포지션 모니터링
        
        **Symbol Config (Multi-Server)**: 
        - 모든 서버에 심볼 설정 동시 적용
        - 레버리지 조정
        - 포지션 크기 설정
        - 심볼 활성화/비활성화
        
        **Performance**: 심볼별 성과 분석
        
        **Strategy Info**: 전략 설명 및 사용법
        """)

if __name__ == "__main__":
    main()