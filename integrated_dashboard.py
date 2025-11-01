import streamlit as st
import sys
import os
from datetime import datetime
import json

# 트레이딩 시스템 임포트
sys.path.append(os.path.dirname(__file__))
from integrated_trading_system_v2_complete import (
    IntegratedTradingSystem,
    send_telegram_test_message,
    verify_telegram_bot,
    send_custom_telegram_message
)

# 페이지 설정
st.set_page_config(
    page_title="통합 트레이딩 대시보드",
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
</style>
""", unsafe_allow_html=True)


def init_session_state():
    """세션 상태 초기화"""
    if 'trading_system' not in st.session_state:
        st.session_state.trading_system = None
    if 'telegram_test_result' not in st.session_state:
        st.session_state.telegram_test_result = None
    if 'telegram_verified' not in st.session_state:
        st.session_state.telegram_verified = False


def render_telegram_settings():
    """텔레그램 설정 섹션 렌더링"""
    st.markdown('<div class="sub-header">📱 텔레그램 설정</div>', unsafe_allow_html=True)
    
    with st.expander("ℹ️ 텔레그램 봇 설정 방법", expanded=False):
        st.markdown("""
        ### 텔레그램 봇 설정 가이드
        
        1. **봇 생성**
           - 텔레그램에서 [@BotFather](https://t.me/botfather) 검색
           - `/newbot` 명령어로 새 봇 생성
           - 봇 이름과 사용자명 설정
           - 받은 **Bot Token** 저장
        
        2. **Chat ID 확인**
           - 생성한 봇과 대화 시작 (아무 메시지나 전송)
           - [@userinfobot](https://t.me/userinfobot)에게 `/start` 전송
           - 받은 **Chat ID** 저장
           
        3. **설정 입력**
           - 아래 입력란에 Bot Token과 Chat ID 입력
           - 여러 Chat ID는 쉼표로 구분 (예: 123456,789012)
           - "연결 확인" 버튼으로 설정 검증
           - "테스트 메시지 전송" 버튼으로 메시지 수신 확인
        
        4. **중요도 시스템**
           - 🚨 high: 중요한 거래 신호
           - 📊 normal: 일반 알림
           - ℹ️ low: 정보성 메시지
           - ✅ success: 성공 메시지
           - ❌ error: 에러 알림
           - ⚠️ warning: 경고 메시지
        """)
    
    col1, col2 = st.columns(2)
    
    with col1:
        bot_token = st.text_input(
            "🤖 Bot Token",
            type="password",
            placeholder="1234567890:ABCdefGHIjklMNOpqrsTUVwxyz",
            help="BotFather에게서 받은 봇 토큰을 입력하세요"
        )
    
    with col2:
        chat_id_input = st.text_input(
            "💬 Chat ID(s)",
            placeholder="123456789 또는 123456,789012",
            help="본인의 텔레그램 Chat ID를 입력하세요 (여러 개는 쉼표로 구분)"
        )
    
    # Chat ID 파싱 (쉼표로 구분된 여러 ID 지원)
    chat_id = None
    if chat_id_input:
        # 쉼표 또는 공백으로 구분
        chat_ids = [id.strip() for id in chat_id_input.replace(',', ' ').split() if id.strip()]
        if len(chat_ids) == 1:
            chat_id = chat_ids[0]
        elif len(chat_ids) > 1:
            chat_id = chat_ids
            st.info(f"📢 {len(chat_ids)}개의 Chat ID가 입력되었습니다: {', '.join(chat_ids)}")
    
    return bot_token, chat_id


def render_telegram_test_section(bot_token, chat_id):
    """텔레그램 테스트 섹션 렌더링"""
    st.markdown('<div class="sub-header">🧪 텔레그램 테스트</div>', unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns(3)
    
    # 연결 확인 버튼
    with col1:
        if st.button("🔗 연결 확인", use_container_width=True):
            if not bot_token or not chat_id:
                st.error("❌ Bot Token과 Chat ID를 모두 입력해주세요.")
            else:
                with st.spinner("연결 확인 중..."):
                    result = verify_telegram_bot(bot_token, chat_id)
                    
                    if result['success']:
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
                            {result['message']}
                        </div>
                        """, unsafe_allow_html=True)
    
    # 테스트 메시지 전송 버튼
    with col2:
        if st.button("✉️ 테스트 메시지 전송", use_container_width=True):
            if not bot_token or not chat_id:
                st.error("❌ Bot Token과 Chat ID를 모두 입력해주세요.")
            else:
                with st.spinner("메시지 전송 중..."):
                    result = send_telegram_test_message(bot_token, chat_id)
                    st.session_state.telegram_test_result = result
                    
                    if result['success']:
                        st.markdown("""
                        <div class="success-box">
                            <strong>✅ 메시지 전송 성공!</strong><br>
                            텔레그램을 확인해보세요.
                        </div>
                        """, unsafe_allow_html=True)
                    else:
                        st.markdown(f"""
                        <div class="error-box">
                            <strong>❌ 메시지 전송 실패</strong><br>
                            {result['message']}
                        </div>
                        """, unsafe_allow_html=True)
    
    # 설정 저장 버튼
    with col3:
        if st.button("💾 설정 저장", use_container_width=True):
            if not bot_token or not chat_id:
                st.error("❌ Bot Token과 Chat ID를 모두 입력해주세요.")
            else:
                # 트레이딩 시스템 초기화
                config = {
                    'telegram_bot_token': bot_token,
                    'telegram_chat_id': chat_id
                }
                st.session_state.trading_system = IntegratedTradingSystem(config)
                st.success("✅ 설정이 저장되었습니다!")


def render_custom_message_section(bot_token, chat_id):
    """커스텀 메시지 전송 섹션"""
    st.markdown('<div class="sub-header">✍️ 커스텀 메시지 전송</div>', unsafe_allow_html=True)
    
    with st.form("custom_message_form"):
        message = st.text_area(
            "메시지 내용",
            height=150,
            placeholder="전송할 메시지를 입력하세요...\n\n<b>굵게</b> <i>기울임</i> <code>코드</code> 형식을 사용할 수 있습니다.",
            help="HTML 형식을 지원합니다"
        )
        
        col1, col2 = st.columns(2)
        
        with col1:
            parse_mode = st.selectbox(
                "파싱 모드",
                options=["HTML", "Markdown", "None"],
                index=0,
                help="메시지 형식 파싱 방식"
            )
        
        with col2:
            importance = st.selectbox(
                "중요도",
                options=["normal", "high", "low", "success", "error", "warning"],
                index=0,
                help="메시지 중요도 (이모지 자동 추가)"
            )
        
        # 중요도별 이모지 미리보기
        emoji_map = {
            'high': '🚨',
            'normal': '📊',
            'low': 'ℹ️',
            'error': '❌',
            'success': '✅',
            'warning': '⚠️'
        }
        st.info(f"💡 선택한 중요도의 이모지: {emoji_map[importance]} (메시지 앞에 자동으로 추가됩니다)")
        
        col1, col2 = st.columns([3, 1])
        with col2:
            submit_button = st.form_submit_button("📤 전송", use_container_width=True)
        
        if submit_button:
            if not bot_token or not chat_id:
                st.error("❌ Bot Token과 Chat ID를 먼저 입력해주세요.")
            elif not message.strip():
                st.error("❌ 메시지 내용을 입력해주세요.")
            else:
                with st.spinner("메시지 전송 중..."):
                    result = send_custom_telegram_message(
                        bot_token, 
                        chat_id, 
                        message,
                        parse_mode if parse_mode != "None" else None,
                        importance
                    )
                    
                    if result['success']:
                        st.success(f"✅ 메시지가 성공적으로 전송되었습니다! ({result.get('message', '')})")
                        
                        # 결과 상세 표시
                        if result.get('results'):
                            with st.expander("전송 결과 상세", expanded=False):
                                for res in result['results']:
                                    if res['success']:
                                        st.success(f"Chat ID {res['chat_id']}: 전송 성공")
                                    else:
                                        st.error(f"Chat ID {res['chat_id']}: {res.get('error', '전송 실패')}")
                    else:
                        st.error(f"❌ 메시지 전송 실패: {result.get('message', '알 수 없는 오류')}")



def render_message_templates(bot_token, chat_id):
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
            if not bot_token or not chat_id:
                st.error("❌ Bot Token과 Chat ID를 먼저 입력해주세요.")
            else:
                with st.spinner("메시지 전송 중..."):
                    result = send_custom_telegram_message(
                        bot_token, 
                        chat_id, 
                        template_message,
                        parse_mode="HTML",
                        importance=importance
                    )
                    
                    if result['success']:
                        st.success(f"✅ 템플릿 메시지가 전송되었습니다! ({result.get('message', '')})")
                        
                        # 결과 상세 표시
                        if result.get('results'):
                            with st.expander("전송 결과 상세", expanded=False):
                                for res in result['results']:
                                    if res['success']:
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


def main():
    """메인 대시보드 함수"""
    init_session_state()
    
    # 헤더
    st.markdown('<div class="main-header">📊 통합 트레이딩 대시보드</div>', unsafe_allow_html=True)
    
    # 사이드바
    with st.sidebar:
        st.image("https://img.icons8.com/color/96/000000/telegram-app.png", width=100)
        st.title("📱 텔레그램 알림")
        st.markdown("---")
        
        st.markdown("""
        ### 기능 소개
        - 🔗 텔레그램 봇 연결 확인
        - ✉️ 테스트 메시지 전송
        - ✍️ 커스텀 메시지 전송
        - 📋 메시지 템플릿 사용
        - 📜 전송 이력 확인
        - 🎯 중요도별 메시지 분류
        - 👥 다중 Chat ID 지원
        """)
        
        st.markdown("---")
        
        st.markdown("""
        ### 📊 중요도 시스템
        - 🚨 **높음**: 중요 거래 신호
        - 📊 **보통**: 일반 알림
        - ℹ️ **낮음**: 정보성 메시지
        - ✅ **성공**: 성공 메시지
        - ❌ **에러**: 에러 알림
        - ⚠️ **경고**: 경고 메시지
        """)
        
        st.markdown("---")
        st.markdown("""
        <div class="info-box">
            <small>
            <strong>💡 Tip:</strong><br>
            HTML 파싱 모드를 사용하여<br>
            <b>굵게</b>, <i>기울임</i>, <code>코드</code><br>
            형식의 메시지를 보낼 수 있습니다!
            </small>
        </div>
        """, unsafe_allow_html=True)
    
    # 메인 콘텐츠
    tabs = st.tabs(["⚙️ 설정 및 테스트", "✍️ 메시지 전송", "📋 템플릿", "📊 이력"])
    
    # 탭 1: 설정 및 테스트
    with tabs[0]:
        bot_token, chat_id = render_telegram_settings()
        
        if bot_token and chat_id:
            st.markdown("---")
            render_telegram_test_section(bot_token, chat_id)
            
            # 연결 상태 표시
            if st.session_state.telegram_verified:
                st.markdown("""
                <div class="success-box">
                    <strong>✅ 텔레그램 연결 상태: 정상</strong>
                </div>
                """, unsafe_allow_html=True)
    
    # 탭 2: 메시지 전송
    with tabs[1]:
        bot_token, chat_id = render_telegram_settings()
        
        if bot_token and chat_id:
            st.markdown("---")
            render_custom_message_section(bot_token, chat_id)
        else:
            st.warning("⚠️ 먼저 '설정 및 테스트' 탭에서 Bot Token과 Chat ID를 입력해주세요.")
    
    # 탭 3: 템플릿
    with tabs[2]:
        bot_token, chat_id = render_telegram_settings()
        
        if bot_token and chat_id:
            st.markdown("---")
            render_message_templates(bot_token, chat_id)
        else:
            st.warning("⚠️ 먼저 '설정 및 테스트' 탭에서 Bot Token과 Chat ID를 입력해주세요.")
    
    # 탭 4: 이력
    with tabs[3]:
        render_telegram_history()
    
    # 푸터
    st.markdown("---")
    st.markdown("""
    <div style="text-align: center; color: #7f8c8d; padding: 2rem 0;">
        <small>
            Integrated Trading Dashboard v2.1 | Made with ❤️ using Streamlit<br>
            <strong>✨ New:</strong> 중요도별 메시지, 다중 Chat ID 지원, HTML 파싱 모드
        </small>
    </div>
    """, unsafe_allow_html=True)


if __name__ == "__main__":
    main()
