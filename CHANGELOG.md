# 📋 변경사항 (CHANGELOG)

## Version 2.1 (2024-01-01)

### 🎉 주요 업데이트

기존 `streamlit_app.py`와 `integrated_trading_system_v2_complete.py`의 텔레그램 기능을 완전히 통합하고 개선했습니다.

---

## 🔄 integrated_trading_system_v2_complete.py

### ✨ 새로운 기능

1. **중요도 시스템 (Importance System)**
   ```python
   # 6가지 중요도 레벨 지원
   emoji_map = {
       'high': '🚨',      # 긴급/중요
       'normal': '📊',    # 일반
       'low': 'ℹ️',       # 정보
       'error': '❌',     # 에러
       'success': '✅',   # 성공
       'warning': '⚠️'    # 경고
   }
   ```

2. **다중 Chat ID 지원**
   ```python
   # 단일 Chat ID
   notifier = TelegramNotifier('token', '123456')
   
   # 여러 Chat ID (리스트)
   notifier = TelegramNotifier('token', ['123456', '789012'])
   ```

3. **HTML 파싱 모드 기본 사용**
   - 기존: Markdown 기본
   - 변경: HTML 기본 (streamlit_app.py와 일치)
   - 이유: `<b>`, `<i>`, `<code>` 태그가 더 안정적

4. **개선된 send_telegram_notification 함수**
   ```python
   def send_telegram_notification(message, importance='normal', 
                                  bot_token=None, chat_ids=None):
       """기존 streamlit_app.py의 함수와 완전히 호환"""
       # HTML 파싱
       # 중요도별 이모지 자동 추가
       # 다중 Chat ID 지원
       # 에러 처리 개선
   ```

5. **test_telegram 함수 추가**
   ```python
   def test_telegram(server_url=None, bot_token=None, chat_ids=None):
       """
       streamlit_app.py의 test_telegram 함수 완전 이식
       - 서버를 통한 테스트 (server_url 제공 시)
       - 직접 테스트 (bot_token, chat_ids 제공 시)
       - 개선된 에러 메시지
       """
   ```

### 🔧 수정된 기능

1. **TelegramNotifier 클래스**
   - `chat_id` → `chat_ids` (복수형, 리스트 지원)
   - `send_message()`에 `importance` 파라미터 추가
   - 다중 전송 결과 상세 정보 제공
   - 각 Chat ID별 성공/실패 상태 추적

2. **IntegratedTradingSystem 클래스**
   - `telegram_chat_id` + `telegram_chat_ids` 모두 지원
   - `send_telegram_notification()` 메서드 추가 (간단 사용)
   - `send_test_telegram()`에 서버 URL 옵션 추가

3. **에러 처리 개선**
   - 타임아웃: "Request timed out. The server might be busy."
   - 연결 오류: "Cannot connect to server. Please check if middle_server.py is running."
   - 기타 오류: 상세한 에러 메시지 제공

### 📝 코드 예제

#### Before (기존)
```python
# 단일 Chat ID만 지원
notifier = TelegramNotifier('token', '123456')
notifier.send_message('메시지')  # Markdown, 이모지 없음
```

#### After (개선)
```python
# 다중 Chat ID 지원
notifier = TelegramNotifier('token', ['123456', '789012'])
result = notifier.send_message(
    '메시지',
    parse_mode='HTML',
    importance='high'  # 🚨 이모지 자동 추가
)
# result: {'success': True, 'success_count': 2, 'total': 2, 'results': [...]}
```

---

## 🎨 integrated_dashboard.py

### ✨ 새로운 기능

1. **중요도 선택 UI**
   - 커스텀 메시지 전송 시 중요도 선택 가능
   - 선택한 이모지 미리보기
   - 6가지 레벨 지원

2. **다중 Chat ID 입력**
   - 쉼표 또는 공백으로 구분
   - 예: `123456,789012` 또는 `123456 789012`
   - 입력된 ID 개수 실시간 표시

3. **HTML 템플릿**
   - 모든 템플릿 HTML 형식으로 변경
   - `<b>`, `<i>`, `<code>` 태그 사용
   - 템플릿별 적절한 importance 자동 설정

4. **상세한 전송 결과**
   - 각 Chat ID별 성공/실패 상태
   - 전송 성공 비율 표시
   - 에러 메시지 상세 표시

5. **개선된 사이드바**
   - 중요도 시스템 설명 추가
   - HTML 파싱 모드 안내
   - 다중 Chat ID 지원 안내

### 🔧 수정된 기능

1. **텔레그램 설정 섹션**
   ```python
   # Before: 단일 Chat ID
   chat_id = st.text_input("Chat ID")
   
   # After: 다중 Chat ID
   chat_id_input = st.text_input("Chat ID(s)", 
                                  placeholder="123456 또는 123456,789012")
   chat_ids = parse_chat_ids(chat_id_input)  # 자동 파싱
   ```

2. **커스텀 메시지 섹션**
   - HTML 플레이스홀더로 변경
   - importance 선택 드롭다운 추가
   - 이모지 미리보기 표시
   - 다중 전송 결과 상세 표시

3. **템플릿 섹션**
   - 모든 템플릿 HTML로 변환
   - 템플릿별 중요도 설정
   - 중요도 표시 UI 추가

4. **시각적 개선**
   - 성공/실패 박스 색상 개선
   - 전송 결과 상세 펼침 메뉴
   - 푸터에 새 기능 안내

---

## 🔍 기존 코드와의 호환성

### ✅ 완벽히 호환되는 부분

1. **streamlit_app.py의 test_telegram 함수**
   ```python
   # 기존 코드 그대로 작동
   success, result = test_telegram(server_url='http://localhost:8000')
   if success:
       print("테스트 성공")
   ```

2. **send_telegram_notification 함수**
   ```python
   # 기존 함수 시그니처 유지
   send_telegram_notification(
       message='알림',
       importance='normal'  # 기존과 동일
   )
   ```

3. **글로벌 설정**
   ```python
   # 기존 방식 그대로 작동
   TELEGRAM_BOT_TOKEN = 'your_token'
   TELEGRAM_CHAT_IDS = ['123456']  # 리스트로 변경됨
   ```

### 🔄 마이그레이션 가이드

#### 단일 Chat ID → 다중 Chat ID
```python
# Before
TELEGRAM_CHAT_ID = '123456'

# After (자동 변환됨)
TELEGRAM_CHAT_IDS = ['123456']

# 또는 여러 ID
TELEGRAM_CHAT_IDS = ['123456', '789012']
```

#### Markdown → HTML
```python
# Before
message = "*굵게* _기울임_ `코드`"

# After
message = "<b>굵게</b> <i>기울임</i> <code>코드</code>"
```

---

## 📊 성능 개선

1. **동시 전송**
   - 여러 Chat ID에 순차 전송
   - 각 전송마다 타임아웃 10초
   - 실패한 ID만 에러 로그

2. **에러 처리**
   - 연결 오류 시 즉시 반환
   - 타임아웃 시 다음 ID로 진행
   - 모든 오류 상세 로깅

3. **응답 상세도**
   ```python
   {
       'success': True,
       'message': '2/3개 채팅방에 전송 성공',
       'total': 3,
       'success_count': 2,
       'results': [
           {'chat_id': '123', 'success': True, 'response': {...}},
           {'chat_id': '456', 'success': True, 'response': {...}},
           {'chat_id': '789', 'success': False, 'error': 'Chat not found'}
       ]
   }
   ```

---

## 🐛 버그 수정

1. **Chat ID 파싱 오류**
   - 문제: 공백이 포함된 Chat ID 처리 실패
   - 수정: strip() 및 split() 개선

2. **Parse Mode 기본값**
   - 문제: Markdown이 기본값이었으나 HTML이 더 안정적
   - 수정: HTML을 기본값으로 변경

3. **에러 메시지 불명확**
   - 문제: "알 수 없는 오류"만 표시
   - 수정: 상세한 에러 타입별 메시지

4. **다중 전송 시 부분 실패 처리**
   - 문제: 하나라도 실패하면 전체 실패로 처리
   - 수정: 성공 개수 카운트 및 부분 성공 지원

---

## 📚 새로운 문서

1. **README_TELEGRAM.md**
   - 완전한 사용 가이드
   - API 레퍼런스
   - 예제 코드 모음
   - 문제 해결 가이드

2. **코드 주석 개선**
   - 모든 함수에 상세한 docstring
   - 파라미터 타입 힌트 추가
   - 반환값 설명 추가

---

## 🚀 사용 예제

### 예제 1: 기본 사용
```python
from integrated_trading_system_v2_complete import send_telegram_notification

send_telegram_notification(
    message='트레이딩 봇 시작',
    importance='normal'
)
```

### 예제 2: 다중 전송
```python
from integrated_trading_system_v2_complete import TelegramNotifier

notifier = TelegramNotifier(
    bot_token='YOUR_TOKEN',
    chat_ids=['123456', '789012']
)

result = notifier.send_message(
    message='<b>긴급!</b> 가격 급등',
    importance='high'
)

print(f"전송 결과: {result['success_count']}/{result['total']} 성공")
```

### 예제 3: 서버 통한 테스트
```python
from integrated_trading_system_v2_complete import test_telegram

success, result = test_telegram(
    server_url='http://localhost:8000'
)

if not success:
    if "Cannot connect" in result:
        print("서버 실행 확인 필요")
```

---

## ⚠️ 주의사항

1. **Chat ID 형식**
   - 개인: 양수 (예: 123456789)
   - 그룹: 음수 (예: -987654321)
   - 슈퍼그룹: -100으로 시작 (예: -1001234567890)

2. **HTML vs Markdown**
   - HTML 권장 (더 안정적)
   - Markdown은 특수문자 이스케이프 필요

3. **Rate Limit**
   - 텔레그램 봇 API: 초당 30개 메시지
   - 같은 그룹: 분당 20개 메시지

4. **타임아웃**
   - 기본: 10초
   - 네트워크 불안정 시 조정 가능

---

## 🔜 향후 계획

- [ ] 비동기 전송 지원 (asyncio)
- [ ] 메시지 큐 시스템
- [ ] 이미지 첨부 지원
- [ ] 버튼/인라인 키보드 지원
- [ ] 메시지 편집/삭제 기능
- [ ] 전송 이력 데이터베이스 저장

---

## 📞 지원

문제 발생 시:
1. README_TELEGRAM.md의 문제 해결 섹션 확인
2. 로깅 활성화 (`logging.basicConfig(level=logging.DEBUG)`)
3. 텔레그램 API 상태 확인 (https://t.me/BotNews)

---

**버전:** 2.1  
**날짜:** 2024-01-01  
**작성자:** Trading System Team
