import streamlit as st
import sys
import os
from datetime import datetime
import json
import requests
import pandas as pd

# 서버 URL 설정
MAIN_SERVER_URL = "http://localhost:5000"  # 기본 서버 URL

# CSS 스타일
st.set_page_config(
    page_title="통합 트레이딩 대시보드 v2",
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
    .sub-header {
        font-size: 1.5rem;
        font-weight: bold;
        color: #2c3e50;
        margin-top: 2rem;
        margin-bottom: 1rem;
    }
    .info-box {
        background-color: #e3f2fd;
        padding: 1rem;
        border-radius: 0.5rem;
        border-left: 4px solid #2196f3;
        margin: 1rem 0;
    }
    .success-box {
        background-color: #e8f5e9;
        padding: 1rem;
        border-radius: 0.5rem;
        border-left: 4px solid #4caf50;
        margin: 1rem 0;
    }
    .error-box {
        background-color: #ffebee;
        padding: 1rem;
        border-radius: 0.5rem;
        border-left: 4px solid #f44336;
        margin: 1rem 0;
    }
    .warning-box {
        background-color: #fff3e0;
        padding: 1rem;
        border-radius: 0.5rem;
        border-left: 4px solid #ff9800;
        margin: 1rem 0;
    }
    .stButton>button {
        width: 100%;
        margin-top: 0.5rem;
    }
    .metric-card {
        background-color: #f8f9fa;
        padding: 1rem;
        border-radius: 0.5rem;
        border: 1px solid #dee2e6;
    }
</style>
""", unsafe_allow_html=True)


def test_telegram_via_server(server_url):
    """서버를 통한 텔레그램 테스트"""
    try:
        response = requests.post(f"{server_url}/test-telegram", timeout=10)
        if response.status_code == 200:
            return True, response.json()
        else:
            error_msg = f"Server returned status code: {response.status_code}"
            if response.text:
                try:
                    error_data = response.json()
                    error_msg = error_data.get('error', error_msg)
                except:
                    error_msg = response.text[:200]
            return False, error_msg
    except requests.exceptions.ConnectionError:
        return False, "Cannot connect to server. Please check if the server is running."
    except requests.exceptions.Timeout:
        return False, "Request timed out. The server might be busy."
    except Exception as e:
        return False, f"Error: {str(e)}"

def verify_telegram_via_server(server_url):
    """서버를 통한 텔레그램 봇 확인"""
    try:
        response = requests.get(f"{server_url}/telegram/verify", timeout=10)
        if response.status_code == 200:
            return response.json()
        else:
            return {"success": False, "message": f"Server error: {response.status_code}"}
    except Exception as e:
        return {"success": False, "message": f"Connection error: {str(e)}"}

def send_telegram_via_server(server_url, message, parse_mode='HTML', importance='normal'):
    """서버를 통한 텔레그램 메시지 전송"""
    try:
        payload = {
            'message': message,
            'parse_mode': parse_mode,
            'importance': importance
        }
        response = requests.post(f"{server_url}/telegram/send", json=payload, timeout=10)
        if response.status_code == 200:
            return response.json()
        else:
            return {"success": False, "message": f"Server error: {response.status_code}"}
    except Exception as e:
        return {"success": False, "message": f"Connection error: {str(e)}"}


def init_session_state():
    """세션 상태 초기화"""
    if 'telegram_test_result' not in st.session_state:
        st.session_state.telegram_test_result = None
    if 'telegram_verified' not in st.session_state:
        st.session_state.telegram_verified = False
    if 'use_server' not in st.session_state:
        st.session_state.use_server = True
    if 'server_url' not in st.session_state:
        st.session_state.server_url = MAIN_SERVER_URL


def render_telegram_settings(key_prefix=""):
    """텔레그램 설정 섹션 렌더링"""
    st.markdown('<div class="sub-header">📱 텔레그램 설정</div>', unsafe_allow_html=True)
    
    # 서버 모드 선택
    use_server = st.checkbox(
        "🔌 서버를 통해 전송 (권장)",
        value=st.session_state.use_server,
        key=f"{key_prefix}_use_server_checkbox",
        help="integrated_trading_system_v3_complete.py 서버가 실행 중일 때 사용"
    )
    st.session_state.use_server = use_server
    
    if use_server:
        server_url = st.text_input(
            "🌐 서버 URL",
            value=st.session_state.server_url,
            key=f"{key_prefix}_server_url_input",
            placeholder="http://localhost:5000",
            help="트레이딩 시스템 서버의 URL을 입력하세요"
        )
        st.session_state.server_url = server_url
        
        st.info("💡 서버 모드: 서버의 텔레그램 설정을 사용합니다. Bot Token과 Chat ID는 서버의 .env 파일에서 설정되어 있어야 합니다.")
        
        return None, None, True, server_url
    
    else:
        st.warning("⚠️ 직접 모드는 현재 지원되지 않습니다. '서버를 통해 전송' 옵션을 활성화해주세요.")
        return None, None, False, None


def render_telegram_test_section(bot_token, chat_id, use_server, server_url):
    """텔레그램 테스트 섹션 렌더링"""
    col1, col2, col3 = st.columns(3)
    
    # 연결 확인 버튼
    with col1:
        if st.button("🔗 연결 확인", use_container_width=True):
            if not server_url:
                st.error("❌ 서버 URL을 입력해주세요.")
            else:
                with st.spinner("서버에 연결 확인 중..."):
                    result = verify_telegram_via_server(server_url)
                    
                    if result.get('success'):
                        st.session_state.telegram_verified = True
                        bot_info = result.get('bot_info', {})
                        st.markdown(f"""
                        <div class="success-box">
                            <strong>✅ 연결 성공!</strong><br>
                            봇 이름: {bot_info.get('first_name', 'N/A')}<br>
                            사용자명: @{bot_info.get('username', 'N/A')}
                        </div>
                        """, unsafe_allow_html=True)
                    else:
                        st.session_state.telegram_verified = False
                        st.markdown(f"""
                        <div class="error-box">
                            <strong>❌ 연결 실패</strong><br>
                            {result.get('message', '알 수 없는 오류')}
                        </div>
                        """, unsafe_allow_html=True)
    
    # 테스트 메시지 전송
    with col2:
        if st.button("📤 테스트 메시지 전송", use_container_width=True):
            if not server_url:
                st.error("❌ 서버 URL을 입력해주세요.")
            else:
                with st.spinner("테스트 메시지 전송 중..."):
                    success, result = test_telegram_via_server(server_url)
                    
                    if success:
                        st.success("✅ 텔레그램 메시지가 전송되었습니다!")
                        st.session_state.telegram_test_result = {
                            'success': True,
                            'message': '메시지 전송 성공',
                            'response': result
                        }
                    else:
                        st.error(f"❌ 메시지 전송 실패: {result}")
                        st.session_state.telegram_test_result = {
                            'success': False,
                            'message': result
                        }


def render_custom_message_section(bot_token, chat_id, use_server, server_url):
    """커스텀 메시지 섹션 렌더링"""
    st.markdown('<div class="sub-header">✍️ 커스텀 메시지 전송</div>', unsafe_allow_html=True)
    
    col1, col2 = st.columns([3, 1])
    
    with col1:
        message = st.text_area(
            "메시지 입력",
            height=150,
            placeholder="전송할 메시지를 입력하세요...",
            help="HTML 태그를 사용할 수 있습니다 (예: <b>굵게</b>, <i>기울임</i>)"
        )
    
    with col2:
        importance = st.selectbox(
            "중요도",
            options=['high', 'normal', 'low', 'success', 'error', 'warning'],
            index=1,
            help="메시지 중요도를 선택하세요"
        )
        
        parse_mode = st.selectbox(
            "파싱 모드",
            options=['HTML', 'Markdown', 'None'],
            index=0,
            help="메시지 형식을 선택하세요"
        )
    
    if st.button("📤 메시지 전송", use_container_width=True):
        if not message:
            st.warning("⚠️ 메시지를 입력해주세요.")
        elif not server_url:
            st.error("❌ 서버 URL을 입력해주세요.")
        else:
            with st.spinner("메시지 전송 중..."):
                result = send_telegram_via_server(
                    server_url,
                    message,
                    parse_mode=parse_mode if parse_mode != 'None' else None,
                    importance=importance
                )
                
                if result.get('success'):
                    st.success(f"✅ 메시지가 전송되었습니다! ({result.get('message', '')})")
                    
                    if result.get('results'):
                        with st.expander("전송 결과 상세", expanded=False):
                            for res in result['results']:
                                if res.get('success'):
                                    st.success(f"Chat ID {res['chat_id']}: 전송 성공")
                                else:
                                    st.error(f"Chat ID {res['chat_id']}: {res.get('error', '전송 실패')}")
                else:
                    st.error(f"❌ 메시지 전송 실패: {result.get('message', '알 수 없는 오류')}")


def render_message_templates(bot_token, chat_id, use_server, server_url):
    """메시지 템플릿 섹션"""
    st.markdown('<div class="sub-header">📋 메시지 템플릿</div>', unsafe_allow_html=True)
    
    templates = {
        "거래 신호 - 매수": {
            "message": """<b>거래 신호</b>

<b>타입:</b> 매수 (BUY)
<b>심볼:</b> BTC/USDT
<b>가격:</b> $45,000
<b>사유:</b> 상승 추세 돌파""",
            "importance": "high"
        },
        "거래 신호 - 매도": {
            "message": """<b>거래 신호</b>

<b>타입:</b> 매도 (SELL)
<b>심볼:</b> BTC/USDT
<b>가격:</b> $45,000
<b>사유:</b> 저항선 도달""",
            "importance": "high"
        },
        "포지션 업데이트": {
            "message": """<b>포지션 업데이트</b>

<b>심볼:</b> BTC/USDT
<b>타입:</b> LONG
<b>진입가:</b> $44,000
<b>현재가:</b> $45,000

<b>손익:</b> $1,000 (+2.27%)""",
            "importance": "success"
        },
        "에러 알림": {
            "message": """<b>에러 알림</b>

<b>타입:</b> API 연결 오류
<b>메시지:</b> API 호출 실패
<b>시간:</b> 2024-01-01 12:00:00""",
            "importance": "error"
        },
        "일반 알림": {
            "message": """<b>시스템 알림</b>

트레이딩 시스템이 정상적으로 작동하고 있습니다.

다음 체크 시간: 10분 후""",
            "importance": "normal"
        },
        "경고 알림": {
            "message": """<b>경고</b>

포지션 위험도가 높습니다.
손절가를 확인해주세요.

현재 손실: -5%""",
            "importance": "warning"
        }
    }
    
    template_name = st.selectbox(
        "템플릿 선택",
        options=list(templates.keys()),
        help="미리 정의된 메시지 템플릿을 선택하세요"
    )
    
    if template_name:
        template_data = templates[template_name]
        template_message = template_data["message"]
        importance = template_data["importance"]
        
        # 중요도 표시
        importance_colors = {
            'high': '🚨 높음',
            'normal': '📊 보통',
            'low': 'ℹ️ 낮음',
            'error': '❌ 에러',
            'success': '✅ 성공',
            'warning': '⚠️ 경고'
        }
        
        col1, col2 = st.columns([3, 1])
        with col2:
            st.metric("중요도", importance_colors.get(importance, importance))
        
        st.code(template_message, language="html")
        
        if st.button(f"📤 '{template_name}' 전송", use_container_width=True):
            if not server_url:
                st.error("❌ 서버 URL을 입력해주세요.")
            else:
                with st.spinner("메시지 전송 중..."):
                    result = send_telegram_via_server(
                        server_url,
                        template_message,
                        parse_mode="HTML",
                        importance=importance
                    )
                    
                    if result.get('success'):
                        st.success(f"✅ 템플릿 메시지가 전송되었습니다! ({result.get('message', '')})")
                        
                        if result.get('results'):
                            with st.expander("전송 결과 상세", expanded=False):
                                for res in result['results']:
                                    if res.get('success'):
                                        st.success(f"Chat ID {res['chat_id']}: 전송 성공")
                                    else:
                                        st.error(f"Chat ID {res['chat_id']}: {res.get('error', '전송 실패')}")
                    else:
                        st.error(f"❌ 메시지 전송 실패: {result.get('message', '알 수 없는 오류')}")


def render_telegram_history():
    """텔레그램 전송 이력 섹션"""
    st.markdown('<div class="sub-header">📜 전송 이력</div>', unsafe_allow_html=True)
    
    if st.session_state.telegram_test_result:
        result = st.session_state.telegram_test_result
        
        with st.expander("마지막 전송 결과 상세", expanded=False):
            col1, col2 = st.columns(2)
            
            with col1:
                st.metric("상태", "성공" if result['success'] else "실패")
                if result.get('status_code'):
                    st.metric("상태 코드", result['status_code'])
            
            with col2:
                st.text_area(
                    "응답 메시지",
                    value=result['message'],
                    height=100,
                    disabled=True
                )
            
            if result.get('response'):
                st.json(result['response'])
    else:
        st.info("아직 전송 이력이 없습니다.")


def render_config_management(server_url):
    """Config 설정 관리 섹션"""
    st.markdown('<div class="sub-header">⚙️ 심볼별 설정 관리</div>', unsafe_allow_html=True)
    
    if not server_url:
        st.warning("⚠️ 서버 URL을 입력해주세요.")
        return
    
    try:
        # 현재 설정 가져오기
        response = requests.get(f"{server_url}/config", timeout=10)
        
        if response.status_code == 200:
            config = response.json()
            
            # 심볼 선택
            symbol = st.selectbox(
                "심볼 선택",
                options=list(config.keys()),
                help="설정을 변경할 심볼을 선택하세요"
            )
            
            if symbol:
                symbol_config = config[symbol]
                
                st.markdown("---")
                
                # 설정 편집 UI
                col1, col2, col3 = st.columns(3)
                
                with col1:
                    enabled = st.checkbox(
                        "활성화",
                        value=symbol_config.get('enabled', True),
                        help="이 심볼의 거래를 활성화합니다"
                    )
                    
                    leverage = st.number_input(
                        "레버리지",
                        value=symbol_config.get('leverage', 10),
                        min_value=1,
                        max_value=125,
                        help="레버리지 배수 (1~125)"
                    )
                    
                    position_size = st.number_input(
                        "포지션 크기 (%)",
                        value=symbol_config.get('position_size_percent', 30),
                        min_value=1,
                        max_value=100,
                        help="잔고의 몇 %를 사용할지 설정"
                    )
                
                with col2:
                    ai_validation = st.checkbox(
                        "AI 검증",
                        value=symbol_config.get('ai_validation', True),
                        help="AI가 거래 신호를 검증합니다"
                    )
                    
                    ai_monitoring = st.checkbox(
                        "AI 모니터링",
                        value=symbol_config.get('ai_monitoring', True),
                        help="AI가 포지션을 자동 모니터링합니다"
                    )
                
                with col3:
                    min_size = st.number_input(
                        "최소 포지션 ($)",
                        value=symbol_config.get('min_position_size', 10),
                        min_value=1,
                        help="최소 주문 금액"
                    )
                    
                    max_size = st.number_input(
                        "최대 포지션 ($)",
                        value=symbol_config.get('max_position_size', 100000),
                        min_value=100,
                        help="최대 주문 금액"
                    )
                
                st.markdown("---")
                
                # 저장 버튼
                col_btn1, col_btn2, col_btn3 = st.columns([1, 1, 2])
                
                with col_btn1:
                    if st.button("💾 설정 저장", use_container_width=True):
                        new_config = {
                            symbol: {
                                "enabled": enabled,
                                "leverage": leverage,
                                "position_size_percent": position_size,
                                "ai_validation": ai_validation,
                                "ai_monitoring": ai_monitoring,
                                "min_position_size": min_size,
                                "max_position_size": max_size
                            }
                        }
                        
                        response = requests.post(
                            f"{server_url}/config",
                            json=new_config,
                            timeout=10
                        )
                        
                        if response.status_code == 200:
                            st.success(f"✅ {symbol} 설정이 저장되었습니다!")
                            st.rerun()
                        else:
                            st.error("❌ 설정 저장 실패")
                
                with col_btn2:
                    if st.button("🔄 새로고침", use_container_width=True):
                        st.rerun()
                
                # 현재 설정 표시
                st.markdown("### 현재 설정 정보")
                
                config_df = pd.DataFrame([symbol_config]).T
                config_df.columns = ['값']
                st.dataframe(config_df, use_container_width=True)
        
        else:
            st.error(f"❌ 설정을 가져올 수 없습니다. (상태 코드: {response.status_code})")
    
    except requests.exceptions.ConnectionError:
        st.error("❌ 서버에 연결할 수 없습니다. 서버가 실행 중인지 확인해주세요.")
    except Exception as e:
        st.error(f"❌ 오류 발생: {str(e)}")


def render_ai_performance(server_url):
    """AI 성과 대시보드"""
    st.markdown('<div class="sub-header">🤖 AI 거래 성과</div>', unsafe_allow_html=True)
    
    if not server_url:
        st.warning("⚠️ 서버 URL을 입력해주세요.")
        return
    
    try:
        response = requests.get(f"{server_url}/ai-performance", timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            total_stats = data.get('total_statistics', {})
            symbol_stats = data.get('symbol_statistics', [])
            
            # 전체 통계 카드
            st.markdown("### 📊 전체 통계")
            
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                st.markdown('<div class="metric-card">', unsafe_allow_html=True)
                st.metric("총 거래", total_stats.get('total_trades', 0))
                st.markdown('</div>', unsafe_allow_html=True)
            
            with col2:
                st.markdown('<div class="metric-card">', unsafe_allow_html=True)
                st.metric("승인", total_stats.get('approved', 0))
                st.markdown('</div>', unsafe_allow_html=True)
            
            with col3:
                st.markdown('<div class="metric-card">', unsafe_allow_html=True)
                st.metric("거부", total_stats.get('rejected', 0))
                st.markdown('</div>', unsafe_allow_html=True)
            
            with col4:
                st.markdown('<div class="metric-card">', unsafe_allow_html=True)
                st.metric("수정", total_stats.get('modified', 0))
                st.markdown('</div>', unsafe_allow_html=True)
            
            st.markdown("---")
            
            # 평균 신뢰도
            confidence = total_stats.get('average_confidence', '0%')
            st.metric("평균 신뢰도", confidence)
            
            st.markdown("---")
            
            # 심볼별 통계
            st.markdown("### 📈 심볼별 성과")
            
            if symbol_stats:
                df = pd.DataFrame(symbol_stats)
                
                # 컬럼 한글화
                df.columns = ['심볼', '거래수', '평균 신뢰도', '승인수']
                
                st.dataframe(
                    df,
                    use_container_width=True,
                    hide_index=True
                )
                
                # 차트
                st.markdown("### 📊 시각화")
                
                chart_col1, chart_col2 = st.columns(2)
                
                with chart_col1:
                    st.bar_chart(df.set_index('심볼')['거래수'])
                
                with chart_col2:
                    st.bar_chart(df.set_index('심볼')['승인수'])
            else:
                st.info("AI 거래 기록이 없습니다.")
        
        else:
            st.error(f"❌ AI 성과를 가져올 수 없습니다. (상태 코드: {response.status_code})")
    
    except requests.exceptions.ConnectionError:
        st.error("❌ 서버에 연결할 수 없습니다. 서버가 실행 중인지 확인해주세요.")
    except Exception as e:
        st.error(f"❌ 오류 발생: {str(e)}")


def render_position_history(server_url):
    """포지션 히스토리"""
    st.markdown('<div class="sub-header">💼 포지션 히스토리</div>', unsafe_allow_html=True)
    
    if not server_url:
        st.warning("⚠️ 서버 URL을 입력해주세요.")
        return
    
    # 필터 옵션
    col1, col2, col3 = st.columns(3)
    
    with col1:
        limit = st.selectbox(
            "조회 개수",
            options=[50, 100, 200, 500],
            index=1,
            help="최근 몇 개의 거래를 조회할지 선택하세요"
        )
    
    with col2:
        # 심볼 목록 가져오기
        try:
            config_response = requests.get(f"{server_url}/config", timeout=5)
            if config_response.status_code == 200:
                symbols = ['전체'] + list(config_response.json().keys())
            else:
                symbols = ['전체']
        except:
            symbols = ['전체']
        
        selected_symbol = st.selectbox(
            "심볼 필터",
            options=symbols,
            help="특정 심볼만 조회하려면 선택하세요"
        )
    
    with col3:
        trade_type = st.selectbox(
            "거래 타입",
            options=['전체', 'AI_VALIDATION', 'AI_MONITOR', 'MANUAL'],
            help="거래 타입으로 필터링"
        )
    
    # 조회 버튼
    if st.button("🔍 조회", use_container_width=True):
        try:
            params = {'limit': limit}
            
            if selected_symbol != '전체':
                params['symbol'] = selected_symbol
            
            if trade_type != '전체':
                params['trade_type'] = trade_type
            
            response = requests.get(
                f"{server_url}/trades",
                params=params,
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                trades = data.get('trades', [])
                
                if trades:
                    st.success(f"✅ {len(trades)}개의 거래를 조회했습니다.")
                    
                    df = pd.DataFrame(trades)
                    
                    # 컬럼 순서 조정 (주요 정보 먼저)
                    display_columns = ['timestamp', 'symbol', 'trade_type', 'action', 'ai_decision', 
                                     'entry_price', 'current_price', 'position_size', 'percentage', 
                                     'stop_loss', 'take_profit', 'confidence', 'reason']
                    
                    # 존재하는 컬럼만 선택
                    available_columns = [col for col in display_columns if col in df.columns]
                    df_display = df[available_columns]
                    
                    # 데이터 테이블 표시
                    st.dataframe(
                        df_display,
                        use_container_width=True,
                        hide_index=True,
                        height=600
                    )
                    
                    # 통계 정보
                    st.markdown("---")
                    st.markdown("### 📊 통계 요약")
                    
                    stat_col1, stat_col2, stat_col3, stat_col4 = st.columns(4)
                    
                    with stat_col1:
                        st.metric("총 거래 수", len(trades))
                    
                    with stat_col2:
                        buy_count = len([t for t in trades if t.get('action') == 'buy'])
                        st.metric("매수", buy_count)
                    
                    with stat_col3:
                        sell_count = len([t for t in trades if t.get('action') == 'sell'])
                        st.metric("매도", sell_count)
                    
                    with stat_col4:
                        if 'confidence' in df.columns:
                            avg_confidence = df['confidence'].mean()
                            st.metric("평균 신뢰도", f"{avg_confidence:.2%}")
                    
                    # CSV 다운로드 버튼
                    csv = df.to_csv(index=False).encode('utf-8')
                    st.download_button(
                        label="📥 CSV 다운로드",
                        data=csv,
                        file_name=f"trades_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                        mime="text/csv"
                    )
                else:
                    st.info("조회된 거래 기록이 없습니다.")
            
            else:
                st.error(f"❌ 거래 기록을 가져올 수 없습니다. (상태 코드: {response.status_code})")
        
        except requests.exceptions.ConnectionError:
            st.error("❌ 서버에 연결할 수 없습니다. 서버가 실행 중인지 확인해주세요.")
        except Exception as e:
            st.error(f"❌ 오류 발생: {str(e)}")


def main():
    """메인 대시보드 함수"""
    init_session_state()
    
    # 헤더
    st.markdown('<div class="main-header">📊 통합 트레이딩 대시보드 v2</div>', unsafe_allow_html=True)
    
    # 텔레그램 설정 (탭 외부에서 한 번만 렌더링)
    bot_token, chat_id, use_server, server_url = render_telegram_settings("main")
    
    st.markdown("---")
    
    # 사이드바
    with st.sidebar:
        st.image("https://img.icons8.com/color/96/000000/telegram-app.png", width=100)
        st.title("📱 통합 대시보드")
        st.markdown("---")
        
        st.markdown("""
        ### 기능 소개
        
        #### 텔레그램
        - 🔗 텔레그램 봇 연결 확인
        - ✉️ 테스트 메시지 전송
        - ✍️ 커스텀 메시지 전송
        - 📋 메시지 템플릿 사용
        
        #### 시스템 관리
        - ⚙️ 심볼별 설정 관리
        - 🤖 AI 성과 모니터링
        - 💼 포지션 히스토리 조회
        """)
        
        st.markdown("---")
        
        # 시스템 상태
        if server_url:
            try:
                status_response = requests.get(f"{server_url}/status", timeout=5)
                if status_response.status_code == 200:
                    status = status_response.json()
                    st.markdown("### 🟢 시스템 상태")
                    st.markdown(f"""
                    - 포트: {status.get('server_port', 'N/A')}
                    - 활성 심볼: {status.get('total_symbols', 'N/A')}개
                    - AI 모니터링: {'🟢' if status.get('ai_monitoring_active') else '🔴'}
                    """)
            except:
                st.markdown("### 🔴 시스템 연결 안됨")
        
        st.markdown("---")
        st.markdown("""
        <div class="info-box">
            <small>
            <strong>💡 Tip:</strong><br>
            서버 실행 후 대시보드를<br>
            새로고침하세요!
            </small>
        </div>
        """, unsafe_allow_html=True)
    
    # 메인 콘텐츠 - 탭
    tabs = st.tabs([
        "⚙️ 텔레그램 테스트", 
        "✍️ 메시지 전송", 
        "📋 템플릿", 
        "📊 전송 이력",
        "🎛️ 설정 관리",
        "🤖 AI 성과",
        "💼 포지션 히스토리"
    ])
    
    # 탭 1: 텔레그램 테스트
    with tabs[0]:
        if use_server and server_url:
            render_telegram_test_section(bot_token, chat_id, use_server, server_url)
            
            # 연결 상태 표시
            if st.session_state.telegram_verified:
                st.markdown("""
                <div class="success-box">
                    <strong>✅ 텔레그램 연결 상태: 정상</strong>
                </div>
                """, unsafe_allow_html=True)
        else:
            st.warning("⚠️ 서버 URL을 입력하고 '서버를 통해 전송'을 활성화해주세요.")
    
    # 탭 2: 메시지 전송
    with tabs[1]:
        if use_server and server_url:
            render_custom_message_section(bot_token, chat_id, use_server, server_url)
        else:
            st.warning("⚠️ 서버 URL을 입력하고 '서버를 통해 전송'을 활성화해주세요.")
    
    # 탭 3: 템플릿
    with tabs[2]:
        if use_server and server_url:
            render_message_templates(bot_token, chat_id, use_server, server_url)
        else:
            st.warning("⚠️ 서버 URL을 입력하고 '서버를 통해 전송'을 활성화해주세요.")
    
    # 탭 4: 전송 이력
    with tabs[3]:
        render_telegram_history()
    
    # 탭 5: 설정 관리
    with tabs[4]:
        if use_server and server_url:
            render_config_management(server_url)
        else:
            st.warning("⚠️ 서버 URL을 입력해주세요.")
    
    # 탭 6: AI 성과
    with tabs[5]:
        if use_server and server_url:
            render_ai_performance(server_url)
        else:
            st.warning("⚠️ 서버 URL을 입력해주세요.")
    
    # 탭 7: 포지션 히스토리
    with tabs[6]:
        if use_server and server_url:
            render_position_history(server_url)
        else:
            st.warning("⚠️ 서버 URL을 입력해주세요.")
    
    # 푸터
    st.markdown("---")
    st.markdown("""
    <div style="text-align: center; color: #7f8c8d; padding: 2rem 0;">
        <small>
            Integrated Trading Dashboard v2.0 | Made with ❤️ using Streamlit<br>
            <strong>✨ New:</strong> 설정 관리, AI 성과, 포지션 히스토리
        </small>
    </div>
    """, unsafe_allow_html=True)


if __name__ == "__main__":
    main()
