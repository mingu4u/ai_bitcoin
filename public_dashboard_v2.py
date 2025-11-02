import streamlit as st
import requests
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime, timedelta
import time

# 페이지 설정
st.set_page_config(
    page_title="트레이딩 봇 성과 대시보드",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# CSS 스타일
st.markdown("""
<style>
    .main-header {
        font-size: 3rem;
        font-weight: bold;
        background: linear-gradient(120deg, #1f77b4, #2ca02c);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        text-align: center;
        margin-bottom: 1rem;
    }
    .metric-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 2rem;
        border-radius: 1rem;
        color: white;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
    }
    .metric-card-positive {
        background: linear-gradient(135deg, #11998e 0%, #38ef7d 100%);
        padding: 2rem;
        border-radius: 1rem;
        color: white;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
    }
    .metric-card-negative {
        background: linear-gradient(135deg, #ee0979 0%, #ff6a00 100%);
        padding: 2rem;
        border-radius: 1rem;
        color: white;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
    }
    .metric-card-neutral {
        background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%);
        padding: 2rem;
        border-radius: 1rem;
        color: white;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
    }
    .info-card {
        background-color: #f8f9fa;
        padding: 1.5rem;
        border-radius: 0.5rem;
        border-left: 4px solid #667eea;
        margin: 1rem 0;
    }
    .stMetric {
        background-color: rgba(255, 255, 255, 0.1);
        padding: 1rem;
        border-radius: 0.5rem;
    }
    div[data-testid="stMetricValue"] {
        font-size: 2rem;
        font-weight: bold;
    }
    .trade-row-profit {
        background-color: rgba(76, 175, 80, 0.1);
    }
    .trade-row-loss {
        background-color: rgba(244, 67, 54, 0.1);
    }
</style>
""", unsafe_allow_html=True)

# 서버 URL 설정
DEFAULT_SERVER_URL = "http://localhost:5000"

# Session state 초기화
def init_session_state():
    """세션 상태 초기화"""
    if 'server_url' not in st.session_state:
        st.session_state.server_url = DEFAULT_SERVER_URL

def get_server_url():
    """현재 서버 URL 반환"""
    return st.session_state.get('server_url', DEFAULT_SERVER_URL)

def get_status():
    """시스템 상태 조회"""
    try:
        response = requests.get(f"{get_server_url()}/status", timeout=5)
        if response.status_code == 200:
            return response.json()
        return None
    except requests.exceptions.RequestException as e:
        # 연결 오류, 타임아웃 등
        return None
    except Exception as e:
        # 기타 예외
        return None

def get_trades(limit=200, symbol=None):
    """거래 히스토리 조회"""
    try:
        params = {'limit': limit}
        if symbol:
            params['symbol'] = symbol
        
        response = requests.get(f"{get_server_url()}/trades", params=params, timeout=10)
        if response.status_code == 200:
            data = response.json()
            return data.get('trades', [])
        return []
    except requests.exceptions.RequestException as e:
        # 연결 오류, 타임아웃 등
        return []
    except Exception as e:
        # 기타 예외
        return []

def calculate_pnl(trades):
    """수익률 계산"""
    if not trades:
        return {
            'total_pnl': 0,
            'total_pnl_percent': 0,
            'win_rate': 0,
            'total_trades': 0,
            'profitable_trades': 0,
            'loss_trades': 0
        }
    
    df = pd.DataFrame(trades)
    
    # PnL 계산 (entry_price와 current_price가 있는 경우)
    if 'entry_price' in df.columns and 'current_price' in df.columns and 'position_size' in df.columns:
        df['pnl'] = 0
        
        for idx, row in df.iterrows():
            if pd.notna(row['entry_price']) and pd.notna(row['current_price']) and pd.notna(row['position_size']):
                # Zero division 체크
                if row['entry_price'] == 0:
                    continue
                    
                action = row.get('action', '')
                if action == 'buy':
                    # 매수 포지션: (현재가 - 진입가) / 진입가 * 포지션크기
                    pnl_percent = (row['current_price'] - row['entry_price']) / row['entry_price']
                elif action == 'sell':
                    # 매도 포지션: (진입가 - 현재가) / 진입가 * 포지션크기
                    pnl_percent = (row['entry_price'] - row['current_price']) / row['entry_price']
                else:
                    pnl_percent = 0
                
                df.at[idx, 'pnl'] = pnl_percent * row['position_size']
        
        total_pnl = df['pnl'].sum()
        total_position_size = df['position_size'].sum()
        total_pnl_percent = (total_pnl / total_position_size * 100) if total_position_size > 0 else 0
        
        profitable = len(df[df['pnl'] > 0])
        loss = len(df[df['pnl'] < 0])
        win_rate = (profitable / len(df) * 100) if len(df) > 0 else 0
        
        return {
            'total_pnl': total_pnl,
            'total_pnl_percent': total_pnl_percent,
            'win_rate': win_rate,
            'total_trades': len(df),
            'profitable_trades': profitable,
            'loss_trades': loss
        }
    
    return {
        'total_pnl': 0,
        'total_pnl_percent': 0,
        'win_rate': 0,
        'total_trades': len(df),
        'profitable_trades': 0,
        'loss_trades': 0
    }

def calculate_symbol_performance(trades):
    """심볼별 성과 계산"""
    if not trades:
        return pd.DataFrame()
    
    df = pd.DataFrame(trades)
    
    if 'symbol' not in df.columns:
        return pd.DataFrame()
    
    # 심볼별 그룹화
    symbol_stats = []
    
    for symbol in df['symbol'].unique():
        symbol_trades = df[df['symbol'] == symbol].copy()
        
        # PnL 계산
        symbol_pnl = 0
        symbol_trades['pnl'] = 0.0  # pnl 컬럼 초기화
        
        if 'entry_price' in symbol_trades.columns and 'current_price' in symbol_trades.columns:
            for idx, row in symbol_trades.iterrows():
                if pd.notna(row['entry_price']) and pd.notna(row['current_price']) and pd.notna(row.get('position_size', 0)):
                    # Zero division 체크
                    if row['entry_price'] == 0:
                        continue
                        
                    action = row.get('action', '')
                    if action == 'buy':
                        pnl_percent = (row['current_price'] - row['entry_price']) / row['entry_price']
                    elif action == 'sell':
                        pnl_percent = (row['entry_price'] - row['current_price']) / row['entry_price']
                    else:
                        pnl_percent = 0
                    
                    trade_pnl = pnl_percent * row.get('position_size', 0)
                    symbol_trades.at[idx, 'pnl'] = trade_pnl
                    symbol_pnl += trade_pnl
        
        # 승률 계산 (PnL이 양수인 거래 개수)
        profitable = 0
        if 'pnl' in symbol_trades.columns:
            profitable = len(symbol_trades[symbol_trades['pnl'] > 0])
        total = len(symbol_trades)
        win_rate = (profitable / total * 100) if total > 0 else 0
        
        symbol_stats.append({
            '심볼': symbol,
            '거래수': total,
            '수익 ($)': f"${symbol_pnl:,.2f}",
            '승률 (%)': f"{win_rate:.1f}%",
            'PnL': symbol_pnl
        })
    
    result_df = pd.DataFrame(symbol_stats)
    if not result_df.empty:
        result_df = result_df.sort_values('PnL', ascending=False)
    
    return result_df

def render_overview():
    """개요 페이지"""
    st.markdown('<div class="main-header">📈 트레이딩 봇 성과 대시보드</div>', unsafe_allow_html=True)
    
    # 서버 연결 상태 확인
    st.markdown("### 🔌 서버 연결 상태")
    status = get_status()
    
    col_status1, col_status2, col_status3 = st.columns(3)
    
    with col_status1:
        if status:
            st.success(f"✅ 서버 연결됨: {get_server_url()}")
        else:
            st.error(f"❌ 서버 연결 실패: {get_server_url()}")
            st.info("📌 서버가 실행 중인지 확인해주세요")
            
            # 연결 테스트 버튼
            if st.button("🔄 연결 재시도"):
                st.rerun()
            
            # 디버깅 정보
            with st.expander("🔍 디버깅 정보"):
                st.code(f"""
서버 URL: {get_server_url()}
확인할 사항:
1. 서버가 실행 중인가요?
   python integrated_trading_system_v3_complete.py

2. 포트가 맞나요? (기본: 5000)
   사이드바에서 서버 URL을 변경할 수 있습니다.

3. 방화벽이 차단하고 있나요?
   방화벽 설정을 확인해주세요.
                """)
            return
    
    with col_status2:
        if status:
            st.metric("활성 심볼", f"{status.get('total_symbols', 0)}개")
    
    with col_status3:
        if status:
            ai_active = status.get('ai_monitoring_active', False)
            st.metric("AI 모니터링", "✅ 활성" if ai_active else "⏸️ 비활성")
    
    st.markdown("---")
    
    # 자동 새로고침 옵션
    col_refresh1, col_refresh2, col_refresh3 = st.columns([2, 1, 3])
    with col_refresh1:
        auto_refresh = st.checkbox("자동 새로고침", value=False)
    with col_refresh2:
        refresh_interval = st.selectbox("간격 (초)", [10, 30, 60, 300], index=1)
    
    if auto_refresh:
        time.sleep(refresh_interval)
        st.rerun()
    
    # 수동 새로고침 버튼
    with col_refresh3:
        if st.button("🔄 새로고침", use_container_width=True):
            st.rerun()
    
    st.markdown("---")
    
    # 데이터 로드
    trades = get_trades(limit=500)
    
    if not trades:
        st.warning("⚠️ 거래 데이터가 없습니다.")
        st.info("💡 서버는 연결되었지만 아직 거래 기록이 없는 것 같아요. 거래가 발생하면 여기에 표시됩니다.")
        
        # 시스템 상태는 표시
        if status:
            st.markdown("### 🤖 시스템 상태")
            
            status_col1, status_col2, status_col3, status_col4 = st.columns(4)
            
            with status_col1:
                st.metric("서버 포트", status.get('server_port', 'N/A'))
            
            with status_col2:
                st.metric("활성 심볼", f"{status.get('total_symbols', 0)}개")
            
            with status_col3:
                ai_active = status.get('ai_monitoring_active', False)
                st.metric("AI 모니터링", "✅ 활성" if ai_active else "⏸️ 비활성")
            
            with status_col4:
                st.metric("모니터링 주기", f"{status.get('ai_monitor_interval', 0)}분")
            
            # 활성 심볼 목록
            symbols = status.get('symbols', [])
            if symbols:
                st.markdown("#### 📊 활성 거래 심볼")
                cols = st.columns(min(4, len(symbols)))
                for idx, symbol in enumerate(symbols):
                    with cols[idx % 4]:
                        st.info(f"**{symbol}**")
        
        return
    
    # 성과 계산
    performance = calculate_pnl(trades)
    
    # 주요 지표 카드
    st.markdown("### 💰 전체 성과")
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        pnl = performance['total_pnl']
        pnl_class = "metric-card-positive" if pnl > 0 else "metric-card-negative" if pnl < 0 else "metric-card-neutral"
        st.markdown(f'<div class="{pnl_class}">', unsafe_allow_html=True)
        st.metric(
            "총 수익",
            f"${pnl:,.2f}",
            f"{performance['total_pnl_percent']:.2f}%"
        )
        st.markdown('</div>', unsafe_allow_html=True)
    
    with col2:
        st.markdown('<div class="metric-card">', unsafe_allow_html=True)
        st.metric(
            "총 거래",
            performance['total_trades']
        )
        st.markdown('</div>', unsafe_allow_html=True)
    
    with col3:
        st.markdown('<div class="metric-card-positive">', unsafe_allow_html=True)
        st.metric(
            "수익 거래",
            performance['profitable_trades'],
            f"{performance['win_rate']:.1f}% 승률"
        )
        st.markdown('</div>', unsafe_allow_html=True)
    
    with col4:
        st.markdown('<div class="metric-card-negative">', unsafe_allow_html=True)
        st.metric(
            "손실 거래",
            performance['loss_trades']
        )
        st.markdown('</div>', unsafe_allow_html=True)
    
    st.markdown("---")
    
    # 시스템 상태
    if status:
        st.markdown("### 🤖 시스템 상태")
        
        status_col1, status_col2, status_col3, status_col4 = st.columns(4)
        
        with status_col1:
            st.metric("서버 상태", "🟢 온라인")
        
        with status_col2:
            st.metric("활성 심볼", f"{status.get('total_symbols', 0)}개")
        
        with status_col3:
            ai_active = status.get('ai_monitoring_active', False)
            st.metric("AI 모니터링", "✅ 활성" if ai_active else "⏸️ 비활성")
        
        with status_col4:
            st.metric("모니터링 주기", f"{status.get('ai_monitor_interval', 0)}분")
        
        # 현재 포지션
        current_positions = status.get('current_positions', {})
        if current_positions:
            st.markdown("---")
            st.markdown("### 📊 현재 포지션")
            
            positions_data = []
            for symbol, pos_info in current_positions.items():
                positions_data.append({
                    '심볼': symbol,
                    '방향': pos_info.get('side', 'N/A'),
                    '크기': pos_info.get('size', 0),
                    '진입가': f"${pos_info.get('entry_price', 0):,.2f}",
                    '현재가': f"${pos_info.get('current_price', 0):,.2f}",
                    'PnL': f"${pos_info.get('pnl', 0):,.2f}"
                })
            
            if positions_data:
                positions_df = pd.DataFrame(positions_data)
                st.dataframe(positions_df, use_container_width=True, hide_index=True)
            else:
                st.info("현재 오픈된 포지션이 없습니다.")

def render_symbol_performance():
    """심볼별 성과"""
    st.markdown("### 📊 심볼별 성과")
    
    # 서버 연결 확인
    status = get_status()
    if not status:
        st.error("❌ 서버에 연결할 수 없습니다.")
        st.info(f"서버 URL: {get_server_url()}")
        if st.button("🔄 연결 재시도"):
            st.rerun()
        return
    
    # 데이터 로드
    trades = get_trades(limit=500)
    
    if not trades:
        st.warning("거래 데이터가 없습니다.")
        st.info("거래가 발생하면 여기에 심볼별 성과가 표시됩니다.")
        return
    
    # 심볼별 성과 계산
    symbol_df = calculate_symbol_performance(trades)
    
    if symbol_df.empty:
        st.info("심볼별 성과 데이터가 없습니다.")
        return
    
    # 테이블 표시 (PnL 컬럼 제외)
    display_df = symbol_df.drop('PnL', axis=1)
    st.dataframe(display_df, use_container_width=True, hide_index=True, height=400)
    
    st.markdown("---")
    
    # 차트
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("#### 거래수 분포")
        fig1 = px.bar(
            symbol_df,
            x='심볼',
            y='거래수',
            color='PnL',
            color_continuous_scale=['red', 'yellow', 'green'],
            title="심볼별 거래 횟수"
        )
        fig1.update_layout(showlegend=False)
        st.plotly_chart(fig1, use_container_width=True)
    
    with col2:
        st.markdown("#### 수익 분포")
        fig2 = px.bar(
            symbol_df,
            x='심볼',
            y='PnL',
            color='PnL',
            color_continuous_scale=['red', 'yellow', 'green'],
            title="심볼별 수익"
        )
        fig2.update_layout(showlegend=False)
        st.plotly_chart(fig2, use_container_width=True)

def render_trade_history():
    """거래 히스토리"""
    st.markdown("### 💼 거래 히스토리")
    
    # 필터
    col1, col2, col3 = st.columns([2, 2, 1])
    
    with col1:
        limit = st.selectbox("조회 개수", [50, 100, 200, 500], index=1)
    
    with col2:
        trades_all = get_trades(limit=500)
        if trades_all:
            df_all = pd.DataFrame(trades_all)
            symbols = ['전체'] + list(df_all['symbol'].unique()) if 'symbol' in df_all.columns else ['전체']
        else:
            symbols = ['전체']
        
        selected_symbol = st.selectbox("심볼 필터", symbols)
    
    with col3:
        if st.button("🔍 조회", use_container_width=True):
            st.rerun()
    
    # 데이터 로드
    symbol_filter = None if selected_symbol == '전체' else selected_symbol
    trades = get_trades(limit=limit, symbol=symbol_filter)
    
    if not trades:
        st.info("조회된 거래가 없습니다.")
        return
    
    # 데이터프레임 생성
    df = pd.DataFrame(trades)
    
    # 주요 컬럼만 표시
    display_columns = []
    column_mapping = {
        'timestamp': '시간',
        'symbol': '심볼',
        'action': '액션',
        'trade_type': '타입',
        'ai_decision': 'AI 결정',
        'entry_price': '진입가',
        'current_price': '현재가',
        'position_size': '크기',
        'percentage': '비율(%)',
        'confidence': '신뢰도',
        'reason': '사유'
    }
    
    for col in column_mapping.keys():
        if col in df.columns:
            display_columns.append(col)
    
    df_display = df[display_columns].copy()
    
    # 컬럼명 한글화
    df_display.rename(columns=column_mapping, inplace=True)
    
    # 숫자 포맷팅
    if '진입가' in df_display.columns:
        df_display['진입가'] = df_display['진입가'].apply(lambda x: f"${x:,.2f}" if pd.notna(x) else "N/A")
    if '현재가' in df_display.columns:
        df_display['현재가'] = df_display['현재가'].apply(lambda x: f"${x:,.2f}" if pd.notna(x) else "N/A")
    if '크기' in df_display.columns:
        df_display['크기'] = df_display['크기'].apply(lambda x: f"${x:,.2f}" if pd.notna(x) else "N/A")
    if '신뢰도' in df_display.columns:
        df_display['신뢰도'] = df_display['신뢰도'].apply(lambda x: f"{x*100:.1f}%" if pd.notna(x) else "N/A")
    
    # 테이블 표시
    st.dataframe(df_display, use_container_width=True, hide_index=True, height=600)
    
    # 통계
    st.markdown("---")
    st.markdown("#### 📈 조회된 거래 통계")
    
    stat_col1, stat_col2, stat_col3, stat_col4 = st.columns(4)
    
    with stat_col1:
        st.metric("총 거래", len(df))
    
    with stat_col2:
        if 'action' in df.columns:
            buy_count = len(df[df['action'] == 'buy'])
            st.metric("매수", buy_count)
    
    with stat_col3:
        if 'action' in df.columns:
            sell_count = len(df[df['action'] == 'sell'])
            st.metric("매도", sell_count)
    
    with stat_col4:
        if 'confidence' in df.columns:
            avg_confidence = df['confidence'].mean()
            st.metric("평균 신뢰도", f"{avg_confidence*100:.1f}%")
    
    # CSV 다운로드
    csv = df_display.to_csv(index=False).encode('utf-8')
    st.download_button(
        label="📥 CSV 다운로드",
        data=csv,
        file_name=f"trades_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
        mime="text/csv",
        use_container_width=True
    )

def render_charts():
    """차트 및 통계"""
    st.markdown("### 📊 통계 차트")
    
    # 서버 연결 확인
    status = get_status()
    if not status:
        st.error("❌ 서버에 연결할 수 없습니다.")
        st.info(f"서버 URL: {get_server_url()}")
        if st.button("🔄 연결 재시도"):
            st.rerun()
        return
    
    # 데이터 로드
    trades = get_trades(limit=500)
    
    if not trades:
        st.warning("거래 데이터가 없습니다.")
        st.info("거래가 발생하면 여기에 통계 차트가 표시됩니다.")
        return
    
    df = pd.DataFrame(trades)
    
    # 시간별 거래 추이
    if 'timestamp' in df.columns:
        st.markdown("#### 📈 시간별 거래 추이")
        
        # timestamp를 datetime으로 변환
        df['date'] = pd.to_datetime(df['timestamp']).dt.date
        daily_trades = df.groupby('date').size().reset_index(name='거래수')
        
        fig = px.line(
            daily_trades,
            x='date',
            y='거래수',
            title="일별 거래 횟수",
            markers=True
        )
        fig.update_layout(
            xaxis_title="날짜",
            yaxis_title="거래수",
            hovermode='x unified'
        )
        st.plotly_chart(fig, use_container_width=True)
    
    st.markdown("---")
    
    # 액션별 분포
    col1, col2 = st.columns(2)
    
    with col1:
        if 'action' in df.columns:
            st.markdown("#### 📊 매수/매도 분포")
            action_counts = df['action'].value_counts()
            
            fig_action = px.pie(
                values=action_counts.values,
                names=action_counts.index,
                title="거래 액션 분포",
                color_discrete_sequence=['#2ca02c', '#d62728']
            )
            st.plotly_chart(fig_action, use_container_width=True)
    
    with col2:
        if 'ai_decision' in df.columns:
            st.markdown("#### 🤖 AI 결정 분포")
            ai_counts = df['ai_decision'].value_counts()
            
            fig_ai = px.pie(
                values=ai_counts.values,
                names=ai_counts.index,
                title="AI 의사결정 분포",
                color_discrete_sequence=['#1f77b4', '#ff7f0e', '#2ca02c']
            )
            st.plotly_chart(fig_ai, use_container_width=True)

def main():
    """메인 함수"""
    
    # Session state 초기화
    init_session_state()
    
    # 사이드바 (최소화)
    with st.sidebar:
        st.markdown("### ⚙️ 설정")
        
        # 서버 URL 프리셋
        preset_urls = {
            "로컬호스트 (5000)": "http://localhost:5000",
            "로컬호스트 (5001)": "http://localhost:5001",
            "로컬호스트 (5002)": "http://localhost:5002",
            "사용자 정의": ""
        }
        
        preset_choice = st.selectbox(
            "서버 선택",
            list(preset_urls.keys()),
            index=0
        )
        
        if preset_choice == "사용자 정의":
            server_url_input = st.text_input(
                "서버 URL",
                value=get_server_url(),
                help="트레이딩 시스템 서버 주소"
            )
        else:
            server_url_input = preset_urls[preset_choice]
            st.info(f"📡 {server_url_input}")
        
        if server_url_input and server_url_input != get_server_url():
            st.session_state.server_url = server_url_input
            st.rerun()
        
        # 연결 테스트
        if st.button("🔌 연결 테스트", use_container_width=True):
            with st.spinner("서버 연결 확인 중..."):
                status = get_status()
                if status:
                    st.success("✅ 연결 성공!")
                    st.json(status)
                else:
                    st.error("❌ 연결 실패")
                    st.warning(f"서버 URL: {get_server_url()}")
        
        st.markdown("---")
        st.markdown("""
        ### 📖 정보
        
        이 대시보드는 트레이딩 봇의 성과를 실시간으로 모니터링합니다.
        
        **기능:**
        - 📊 전체 수익률
        - 💰 심볼별 성과
        - 📈 거래 히스토리
        - 📉 통계 차트
        
        **연결 문제 해결:**
        1. 트레이딩 시스템이 실행 중인지 확인
        2. 올바른 포트 번호 확인 (기본: 5000)
        3. 방화벽 설정 확인
        """)
        
        st.markdown("---")
        st.markdown("""
        <div style="text-align: center; color: #7f8c8d;">
            <small>
                <strong>공개용 대시보드 v1.1</strong><br>
                읽기 전용 모드
            </small>
        </div>
        """, unsafe_allow_html=True)
    
    # 메인 탭
    tabs = st.tabs(["📊 개요", "💎 심볼별 성과", "💼 거래 히스토리", "📈 차트"])
    
    with tabs[0]:
        render_overview()
    
    with tabs[1]:
        render_symbol_performance()
    
    with tabs[2]:
        render_trade_history()
    
    with tabs[3]:
        render_charts()
    
    # 푸터
    st.markdown("---")
    st.markdown("""
    <div style="text-align: center; color: #7f8c8d; padding: 1rem 0;">
        <small>
            🤖 AI Trading Bot Performance Dashboard | 📊 Real-time Monitoring<br>
            <em>This is a read-only dashboard for public viewing</em>
        </small>
    </div>
    """, unsafe_allow_html=True)

if __name__ == "__main__":
    main()
