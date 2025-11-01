# 📱 텔레그램 알림 시스템 사용 가이드

## 📋 목차
- [주요 기능](#주요-기능)
- [설치 방법](#설치-방법)
- [텔레그램 봇 설정](#텔레그램-봇-설정)
- [사용 방법](#사용-방법)
- [API 레퍼런스](#api-레퍼런스)
- [예제 코드](#예제-코드)

---

## 🎯 주요 기능

### ✨ 새로운 기능 (v2.1)
- ✅ **중요도별 메시지 분류** - 6가지 중요도 레벨 (high, normal, low, success, error, warning)
- ✅ **다중 Chat ID 지원** - 여러 사용자/그룹에 동시 전송
- ✅ **HTML 파싱 모드** - 굵게, 기울임, 코드 블록 등 서식 지원
- ✅ **서버 통합 지원** - middle_server.py와 연동 가능
- ✅ **개선된 에러 처리** - 타임아웃, 연결 오류 등 상세 에러 메시지

### 📊 기본 기능
- 텔레그램 봇 연결 확인
- 테스트 메시지 전송
- 커스텀 메시지 전송
- 거래 신호 알림
- 포지션 업데이트 알림
- 에러 알림
- 전송 이력 확인

---

## 🚀 설치 방법

### 1. 필요한 패키지 설치
```bash
pip install streamlit requests
```

### 2. 파일 구조
```
project/
├── integrated_trading_system_v2_complete.py  # 핵심 시스템
├── integrated_dashboard.py                    # Streamlit UI
└── README.md                                  # 이 파일
```

---

## 🤖 텔레그램 봇 설정

### Step 1: 봇 생성
1. 텔레그램에서 [@BotFather](https://t.me/botfather) 검색
2. `/newbot` 명령어 실행
3. 봇 이름 입력 (예: My Trading Bot)
4. 봇 사용자명 입력 (예: MyTradingBot_bot) - 반드시 `_bot`으로 끝나야 함
5. **Bot Token 저장** (예: `1234567890:ABCdefGHIjklMNOpqrsTUVwxyz`)

### Step 2: Chat ID 확인
1. 생성한 봇과 대화 시작
2. 아무 메시지나 전송 (예: "안녕")
3. [@userinfobot](https://t.me/userinfobot)에게 `/start` 전송
4. **Chat ID 저장** (예: `123456789`)

### Step 3: 그룹 Chat ID (선택사항)
그룹에서 알림을 받고 싶다면:
1. 봇을 그룹에 추가
2. 그룹에서 봇에게 `/start` 메시지 전송
3. 브라우저에서 다음 URL 접속:
   ```
   https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates
   ```
4. 응답에서 그룹의 Chat ID 확인 (음수로 시작)

---

## 💻 사용 방법

### 방법 1: Streamlit 대시보드 (권장)

```bash
streamlit run integrated_dashboard.py
```

#### 대시보드 기능
1. **⚙️ 설정 및 테스트 탭**
   - Bot Token과 Chat ID 입력
   - 연결 확인
   - 테스트 메시지 전송
   - 설정 저장

2. **✍️ 메시지 전송 탭**
   - 커스텀 메시지 작성
   - HTML/Markdown 파싱 모드 선택
   - 중요도 선택
   - 실시간 전송

3. **📋 템플릿 탭**
   - 거래 신호 (매수/매도)
   - 포지션 업데이트
   - 에러 알림
   - 일반/경고 알림

4. **📊 이력 탭**
   - 마지막 전송 결과 확인
   - JSON 응답 상세보기

### 방법 2: Python 코드에서 직접 사용

#### 2-1. 독립 함수 사용 (간단한 전송)

```python
from integrated_trading_system_v2_complete import (
    send_telegram_test_message,
    send_custom_telegram_message,
    verify_telegram_bot
)

# 테스트 메시지 전송
result = send_telegram_test_message(
    bot_token='YOUR_BOT_TOKEN',
    chat_id='YOUR_CHAT_ID'
)
print(result)

# 커스텀 메시지 전송
result = send_custom_telegram_message(
    bot_token='YOUR_BOT_TOKEN',
    chat_id='YOUR_CHAT_ID',
    message='<b>안녕하세요!</b> 테스트 메시지입니다.',
    parse_mode='HTML',
    importance='high'
)
print(result)

# 다중 Chat ID 지원
result = send_custom_telegram_message(
    bot_token='YOUR_BOT_TOKEN',
    chat_id=['123456', '789012'],  # 리스트로 전달
    message='여러 사람에게 전송',
    importance='normal'
)
print(result)
```

#### 2-2. 시스템 클래스 사용 (고급 기능)

```python
from integrated_trading_system_v2_complete import IntegratedTradingSystem

# 설정
config = {
    'telegram_bot_token': 'YOUR_BOT_TOKEN',
    'telegram_chat_ids': ['123456', '789012']  # 여러 ID 지원
}

# 시스템 초기화
system = IntegratedTradingSystem(config)

# 알림 전송
system.send_telegram_notification(
    message='시스템이 시작되었습니다.',
    importance='normal'
)

# 연결 확인
result = system.verify_telegram_connection()
print(result)
```

#### 2-3. TelegramNotifier 클래스 사용 (세밀한 제어)

```python
from integrated_trading_system_v2_complete import TelegramNotifier

# 초기화
notifier = TelegramNotifier(
    bot_token='YOUR_BOT_TOKEN',
    chat_ids=['123456', '789012']  # 단일 또는 리스트
)

# 거래 신호 전송
notifier.send_trading_signal(
    signal_type='BUY',
    symbol='BTC/USDT',
    price=45000.0,
    reason='상승 추세 돌파'
)

# 포지션 업데이트
notifier.send_position_update(
    symbol='BTC/USDT',
    position_type='LONG',
    entry_price=44000.0,
    current_price=45000.0,
    pnl=1000.0,
    pnl_percentage=2.27
)

# 에러 알림
notifier.send_error_alert(
    error_type='API 연결 오류',
    error_message='API 호출 실패'
)
```

---

## 📚 API 레퍼런스

### 중요도 (Importance) 레벨

| 레벨 | 이모지 | 용도 |
|------|--------|------|
| `high` | 🚨 | 중요한 거래 신호, 긴급 알림 |
| `normal` | 📊 | 일반적인 알림, 정보 |
| `low` | ℹ️ | 덜 중요한 정보성 메시지 |
| `success` | ✅ | 성공 메시지, 수익 달성 |
| `error` | ❌ | 에러, 시스템 장애 |
| `warning` | ⚠️ | 경고, 주의 필요 |

### 파싱 모드 (Parse Mode)

| 모드 | 설명 | 예제 |
|------|------|------|
| `HTML` | HTML 태그 지원 (기본) | `<b>굵게</b> <i>기울임</i> <code>코드</code>` |
| `Markdown` | Markdown 문법 지원 | `**굵게** _기울임_ \`코드\`` |
| `None` | 일반 텍스트 | `그냥 텍스트` |

### 주요 함수

#### `send_telegram_notification(message, importance, bot_token, chat_ids)`
간단한 알림 전송

**Parameters:**
- `message` (str): 전송할 메시지
- `importance` (str): 중요도 레벨
- `bot_token` (str, optional): 봇 토큰
- `chat_ids` (list, optional): 채팅 ID 리스트

**Returns:**
- `bool`: 전송 성공 여부

#### `test_telegram(server_url, bot_token, chat_ids)`
테스트 메시지 전송

**Parameters:**
- `server_url` (str, optional): 서버 URL (서버 통한 전송)
- `bot_token` (str, optional): 봇 토큰 (직접 전송)
- `chat_ids` (list, optional): 채팅 ID 리스트 (직접 전송)

**Returns:**
- `tuple`: (성공 여부, 응답/에러 메시지)

#### `TelegramNotifier.send_message(message, parse_mode, importance)`
세밀한 제어로 메시지 전송

**Parameters:**
- `message` (str): 전송할 메시지
- `parse_mode` (str): 파싱 모드 (HTML, Markdown, None)
- `importance` (str): 중요도 레벨

**Returns:**
- `dict`: 상세 응답 딕셔너리

---

## 🔧 예제 코드

### 예제 1: 기본 알림
```python
from integrated_trading_system_v2_complete import send_telegram_notification

# 글로벌 설정
from integrated_trading_system_v2_complete import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_IDS
TELEGRAM_BOT_TOKEN = 'YOUR_BOT_TOKEN'
TELEGRAM_CHAT_IDS = ['YOUR_CHAT_ID']

# 알림 전송
send_telegram_notification(
    message='트레이딩 봇이 시작되었습니다.',
    importance='normal'
)
```

### 예제 2: 거래 신호
```python
from integrated_trading_system_v2_complete import TelegramNotifier

notifier = TelegramNotifier(
    bot_token='YOUR_BOT_TOKEN',
    chat_ids=['YOUR_CHAT_ID']
)

# 매수 신호
notifier.send_trading_signal(
    signal_type='BUY',
    symbol='BTC/USDT',
    price=45000.0,
    reason='RSI 과매도 + 지지선 터치'
)
```

### 예제 3: HTML 서식 메시지
```python
from integrated_trading_system_v2_complete import send_custom_telegram_message

message = """
<b>📊 일일 트레이딩 리포트</b>

<b>총 거래:</b> 12건
<b>승률:</b> 75%
<b>수익:</b> +$1,250

<i>상세 내역은 대시보드를 확인하세요.</i>
"""

send_custom_telegram_message(
    bot_token='YOUR_BOT_TOKEN',
    chat_id='YOUR_CHAT_ID',
    message=message,
    parse_mode='HTML',
    importance='success'
)
```

### 예제 4: 다중 사용자에게 전송
```python
from integrated_trading_system_v2_complete import TelegramNotifier

# 여러 Chat ID에 동시 전송
notifier = TelegramNotifier(
    bot_token='YOUR_BOT_TOKEN',
    chat_ids=['123456', '789012', '345678']
)

result = notifier.send_message(
    message='<b>긴급!</b> 시장에 큰 변동이 감지되었습니다.',
    importance='high'
)

print(f"전송 결과: {result['success_count']}/{result['total']} 성공")
```

### 예제 5: 에러 처리
```python
from integrated_trading_system_v2_complete import test_telegram

# 서버를 통한 전송 (권장)
success, result = test_telegram(server_url='http://localhost:8000')

if success:
    print("✅ 테스트 성공:", result)
else:
    print("❌ 테스트 실패:", result)
    
    if "Cannot connect to server" in result:
        print("서버가 실행 중인지 확인하세요.")
    elif "timed out" in result:
        print("네트워크 연결을 확인하세요.")
```

### 예제 6: 트레이딩 봇 통합
```python
from integrated_trading_system_v2_complete import IntegratedTradingSystem

class TradingBot:
    def __init__(self):
        config = {
            'telegram_bot_token': 'YOUR_BOT_TOKEN',
            'telegram_chat_ids': ['YOUR_CHAT_ID']
        }
        self.system = IntegratedTradingSystem(config)
    
    def on_trade_signal(self, signal_type, symbol, price):
        """거래 신호 발생 시"""
        self.system.send_telegram_notification(
            f'<b>{signal_type}</b> 신호: {symbol} @ ${price}',
            importance='high'
        )
    
    def on_position_closed(self, pnl):
        """포지션 청산 시"""
        importance = 'success' if pnl > 0 else 'error'
        self.system.send_telegram_notification(
            f'포지션 청산: {"수익" if pnl > 0 else "손실"} ${abs(pnl):.2f}',
            importance=importance
        )
    
    def on_error(self, error_msg):
        """에러 발생 시"""
        self.system.send_telegram_notification(
            f'<b>⚠️ 에러 발생</b>\n{error_msg}',
            importance='error'
        )

# 사용
bot = TradingBot()
bot.on_trade_signal('BUY', 'BTC/USDT', 45000)
bot.on_position_closed(1250.50)
bot.on_error('API 연결 실패')
```

---

## 🔍 문제 해결

### 일반적인 오류

#### 1. "Cannot connect to server"
- `middle_server.py`가 실행 중인지 확인
- 서버 URL이 올바른지 확인

#### 2. "Request timed out"
- 네트워크 연결 확인
- 방화벽 설정 확인
- 텔레그램 API 접근 가능 여부 확인

#### 3. "Unauthorized"
- Bot Token이 정확한지 확인
- BotFather에서 봇이 비활성화되지 않았는지 확인

#### 4. "Chat not found"
- Chat ID가 정확한지 확인
- 봇과 대화를 시작했는지 확인
- 그룹의 경우 봇이 멤버인지 확인

### 디버깅 팁

```python
# 로깅 활성화
import logging
logging.basicConfig(level=logging.DEBUG)

# 연결 테스트
from integrated_trading_system_v2_complete import verify_telegram_bot

result = verify_telegram_bot('YOUR_BOT_TOKEN', 'YOUR_CHAT_ID')
print(result)
```

---

## 📝 라이선스

이 프로젝트는 MIT 라이선스 하에 배포됩니다.

---

## 🤝 기여

버그 리포트나 기능 제안은 언제든 환영합니다!

---

## 📞 지원

문제가 있으시면 다음을 확인해주세요:
1. 이 README의 [문제 해결](#문제-해결) 섹션
2. 텔레그램 봇 설정이 올바른지 확인
3. 예제 코드를 참고하여 사용법 확인

---

**버전:** 2.1
**최종 업데이트:** 2024-01-01
