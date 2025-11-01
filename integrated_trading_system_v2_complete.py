import requests
import json
from typing import Optional, Dict, Any, List, Union
import logging

# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ============ Configuration ============
ENABLE_TELEGRAM = True
TELEGRAM_BOT_TOKEN = ""
TELEGRAM_CHAT_IDS = []
MAIN_SERVER_URL = "http://localhost:8000"  # 기본 서버 URL


# ============ Telegram Functions ============
def send_telegram_notification(message: str, importance: str = 'normal', 
                               bot_token: Optional[str] = None, 
                               chat_ids: Optional[List[str]] = None) -> bool:
    """
    텔레그램 알림 전송
    
    Args:
        message: 전송할 메시지
        importance: 중요도 ('high', 'normal', 'low', 'error', 'success', 'warning')
        bot_token: 봇 토큰 (None이면 글로벌 설정 사용)
        chat_ids: 채팅 ID 리스트 (None이면 글로벌 설정 사용)
        
    Returns:
        전송 성공 여부
    """
    if not ENABLE_TELEGRAM:
        return False
    
    # 토큰과 채팅 ID 설정
    token = bot_token or TELEGRAM_BOT_TOKEN
    ids = chat_ids or TELEGRAM_CHAT_IDS
    
    if not token or not ids:
        logging.warning("텔레그램 설정이 완료되지 않았습니다.")
        return False
    
    # HTML 파싱 모드 사용
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    
    # 중요도에 따른 이모지 추가
    emoji_map = {
        'high': '🚨',
        'normal': '📊',
        'low': 'ℹ️',
        'error': '❌',
        'success': '✅',
        'warning': '⚠️'
    }
    
    emoji = emoji_map.get(importance, '📊')
    formatted_message = f"{emoji} {message}"
    
    success_count = 0
    for chat_id in ids:
        if chat_id:
            try:
                payload = {
                    'chat_id': chat_id.strip(),
                    'text': formatted_message,
                    'parse_mode': 'HTML'
                }
                response = requests.post(url, json=payload, timeout=10)
                response.raise_for_status()
                success_count += 1
            except Exception as e:
                logging.error(f"텔레그램 알림 전송 실패 (chat_id: {chat_id}): {str(e)}")
    
    return success_count > 0


def test_telegram(server_url: Optional[str] = None, 
                 bot_token: Optional[str] = None,
                 chat_ids: Optional[List[str]] = None) -> tuple:
    """
    텔레그램 알림 테스트 - 개선된 에러 처리
    
    Args:
        server_url: 서버 URL (None이면 직접 전송)
        bot_token: 봇 토큰 (서버 사용 안할 때)
        chat_ids: 채팅 ID 리스트 (서버 사용 안할 때)
        
    Returns:
        (성공 여부, 응답/에러 메시지)
    """
    # 서버를 통한 테스트
    if server_url:
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
                        error_msg = response.text[:200]  # 처음 200자만 표시
                return False, error_msg
        except requests.exceptions.ConnectionError:
            return False, "Cannot connect to server. Please check if middle_server.py is running."
        except requests.exceptions.Timeout:
            return False, "Request timed out. The server might be busy."
        except Exception as e:
            return False, f"Error: {str(e)}"
    
    # 직접 전송 테스트
    else:
        token = bot_token or TELEGRAM_BOT_TOKEN
        ids = chat_ids or TELEGRAM_CHAT_IDS
        
        if not token or not ids:
            return False, "텔레그램 설정이 완료되지 않았습니다."
        
        test_message = "🤖 텔레그램 봇 테스트\n\n✅ 봇이 정상적으로 작동하고 있습니다!"
        
        try:
            success = send_telegram_notification(
                test_message, 
                importance='normal',
                bot_token=token,
                chat_ids=ids
            )
            
            if success:
                return True, {"status": "success", "message": "테스트 메시지가 전송되었습니다."}
            else:
                return False, "메시지 전송 실패"
                
        except Exception as e:
            return False, f"Error: {str(e)}"


class TelegramNotifier:
    """텔레그램 알림을 관리하는 클래스"""
    
    def __init__(self, bot_token: str, chat_ids: Union[str, List[str]]):
        """
        Args:
            bot_token: 텔레그램 봇 토큰
            chat_ids: 텔레그램 채팅 ID (단일 또는 리스트)
        """
        self.bot_token = bot_token
        
        # chat_ids를 리스트로 변환
        if isinstance(chat_ids, str):
            self.chat_ids = [chat_ids]
        else:
            self.chat_ids = chat_ids
            
        self.base_url = f"https://api.telegram.org/bot{bot_token}"
    
    def send_message(self, message: str, parse_mode: str = "HTML", 
                    importance: str = 'normal') -> Dict[str, Any]:
        """
        텔레그램으로 메시지를 전송합니다.
        
        Args:
            message: 전송할 메시지
            parse_mode: 메시지 파싱 모드 (Markdown, HTML, None)
            importance: 중요도
            
        Returns:
            응답 딕셔너리 (성공 여부, 메시지, 상태 코드 등)
        """
        # 중요도에 따른 이모지 추가
        emoji_map = {
            'high': '🚨',
            'normal': '📊',
            'low': 'ℹ️',
            'error': '❌',
            'success': '✅',
            'warning': '⚠️'
        }
        
        emoji = emoji_map.get(importance, '📊')
        formatted_message = f"{emoji} {message}"
        
        results = []
        success_count = 0
        
        for chat_id in self.chat_ids:
            if not chat_id:
                continue
                
            try:
                url = f"{self.base_url}/sendMessage"
                payload = {
                    "chat_id": chat_id.strip(),
                    "text": formatted_message,
                    "parse_mode": parse_mode
                }
                
                response = requests.post(url, json=payload, timeout=10)
                
                if response.status_code == 200:
                    success_count += 1
                    logger.info(f"텔레그램 메시지 전송 성공 (chat_id: {chat_id})")
                    results.append({
                        "chat_id": chat_id,
                        "success": True,
                        "response": response.json()
                    })
                else:
                    error_msg = response.json().get('description', '알 수 없는 오류')
                    logger.error(f"텔레그램 메시지 전송 실패 (chat_id: {chat_id}): {error_msg}")
                    results.append({
                        "chat_id": chat_id,
                        "success": False,
                        "error": error_msg
                    })
                    
            except requests.exceptions.Timeout:
                logger.error(f"텔레그램 API 타임아웃 (chat_id: {chat_id})")
                results.append({
                    "chat_id": chat_id,
                    "success": False,
                    "error": "요청 시간 초과 (타임아웃)"
                })
            except requests.exceptions.ConnectionError:
                logger.error(f"텔레그램 API 연결 오류 (chat_id: {chat_id})")
                results.append({
                    "chat_id": chat_id,
                    "success": False,
                    "error": "네트워크 연결 오류"
                })
            except Exception as e:
                logger.error(f"텔레그램 메시지 전송 중 오류 발생 (chat_id: {chat_id}): {str(e)}")
                results.append({
                    "chat_id": chat_id,
                    "success": False,
                    "error": str(e)
                })
        
        return {
            "success": success_count > 0,
            "message": f"{success_count}/{len(self.chat_ids)}개 채팅방에 전송 성공",
            "total": len(self.chat_ids),
            "success_count": success_count,
            "results": results
        }
    
    def send_test_message(self) -> Dict[str, Any]:
        """
        테스트 메시지를 전송합니다.
        
        Returns:
            응답 딕셔너리
        """
        test_message = "텔레그램 봇 테스트\n\n✅ 봇이 정상적으로 작동하고 있습니다!"
        return self.send_message(test_message, importance='normal')
    
    def send_trading_signal(self, signal_type: str, symbol: str, 
                          price: float, reason: str = "") -> Dict[str, Any]:
        """
        거래 신호를 텔레그램으로 전송합니다.
        
        Args:
            signal_type: 신호 타입 (BUY, SELL)
            symbol: 심볼
            price: 가격
            reason: 거래 사유
            
        Returns:
            응답 딕셔너리
        """
        emoji = "🟢" if signal_type == "BUY" else "🔴"
        message = f"""<b>거래 신호</b>

<b>타입:</b> {signal_type}
<b>심볼:</b> {symbol}
<b>가격:</b> ${price:,.2f}
<b>사유:</b> {reason}"""
        
        importance = 'high' if signal_type in ['BUY', 'SELL'] else 'normal'
        return self.send_message(message, importance=importance)
    
    def send_position_update(self, symbol: str, position_type: str,
                           entry_price: float, current_price: float,
                           pnl: float, pnl_percentage: float) -> Dict[str, Any]:
        """
        포지션 업데이트를 텔레그램으로 전송합니다.
        
        Args:
            symbol: 심볼
            position_type: 포지션 타입 (LONG, SHORT)
            entry_price: 진입 가격
            current_price: 현재 가격
            pnl: 손익
            pnl_percentage: 손익 퍼센트
            
        Returns:
            응답 딕셔너리
        """
        emoji = "📈" if position_type == "LONG" else "📉"
        
        message = f"""<b>포지션 업데이트</b>

<b>심볼:</b> {symbol}
<b>타입:</b> {position_type}
<b>진입가:</b> ${entry_price:,.2f}
<b>현재가:</b> ${current_price:,.2f}

<b>손익:</b> ${pnl:,.2f} ({pnl_percentage:+.2f}%)"""
        
        importance = 'success' if pnl > 0 else 'warning'
        return self.send_message(message, importance=importance)
    
    def send_error_alert(self, error_type: str, error_message: str) -> Dict[str, Any]:
        """
        에러 알림을 텔레그램으로 전송합니다.
        
        Args:
            error_type: 에러 타입
            error_message: 에러 메시지
            
        Returns:
            응답 딕셔너리
        """
        message = f"""<b>에러 알림</b>

<b>타입:</b> {error_type}
<b>메시지:</b> {error_message}"""
        
        return self.send_message(message, importance='error')
    
    def verify_connection(self) -> Dict[str, Any]:
        """
        봇 연결을 확인합니다.
        
        Returns:
            응답 딕셔너리 (봇 정보 포함)
        """
        try:
            url = f"{self.base_url}/getMe"
            response = requests.get(url, timeout=10)
            
            if response.status_code == 200:
                bot_info = response.json().get('result', {})
                return {
                    "success": True,
                    "message": "봇 연결 성공",
                    "bot_info": bot_info
                }
            else:
                return {
                    "success": False,
                    "message": "봇 연결 실패",
                    "status_code": response.status_code
                }
        except Exception as e:
            return {
                "success": False,
                "message": f"연결 확인 중 오류: {str(e)}"
            }


class IntegratedTradingSystem:
    """통합 트레이딩 시스템 메인 클래스"""
    
    def __init__(self, config: Optional[Dict] = None):
        """
        Args:
            config: 시스템 설정 딕셔너리
        """
        self.config = config or {}
        self.telegram_notifier = None
        
        # 텔레그램 설정이 있으면 초기화
        bot_token = self.config.get('telegram_bot_token')
        chat_ids = self.config.get('telegram_chat_ids') or self.config.get('telegram_chat_id')
        
        if bot_token and chat_ids:
            self.initialize_telegram(bot_token, chat_ids)
    
    def initialize_telegram(self, bot_token: str, chat_ids: Union[str, List[str]]) -> bool:
        """
        텔레그램 알림을 초기화합니다.
        
        Args:
            bot_token: 봇 토큰
            chat_ids: 채팅 ID (단일 또는 리스트)
            
        Returns:
            초기화 성공 여부
        """
        try:
            self.telegram_notifier = TelegramNotifier(bot_token, chat_ids)
            logger.info("텔레그램 알림 초기화 완료")
            return True
        except Exception as e:
            logger.error(f"텔레그램 알림 초기화 실패: {str(e)}")
            return False
    
    def send_telegram_message(self, message: str, parse_mode: str = "HTML", 
                            importance: str = 'normal') -> Dict[str, Any]:
        """
        텔레그램 메시지를 전송합니다.
        
        Args:
            message: 전송할 메시지
            parse_mode: 파싱 모드
            importance: 중요도
            
        Returns:
            응답 딕셔너리
        """
        if not self.telegram_notifier:
            return {
                "success": False,
                "message": "텔레그램이 초기화되지 않았습니다."
            }
        
        return self.telegram_notifier.send_message(message, parse_mode, importance)
    
    def send_telegram_notification(self, message: str, importance: str = 'normal') -> bool:
        """
        텔레그램 알림을 전송합니다 (간단 버전)
        
        Args:
            message: 전송할 메시지
            importance: 중요도
            
        Returns:
            전송 성공 여부
        """
        if not self.telegram_notifier:
            return False
        
        result = self.telegram_notifier.send_message(message, "HTML", importance)
        return result.get('success', False)
    
    def send_test_telegram(self, server_url: Optional[str] = None) -> tuple:
        """
        텔레그램 테스트 메시지를 전송합니다.
        
        Args:
            server_url: 서버 URL (None이면 직접 전송)
            
        Returns:
            (성공 여부, 응답/에러 메시지)
        """
        if server_url:
            return test_telegram(server_url=server_url)
        
        if not self.telegram_notifier:
            return False, "텔레그램이 초기화되지 않았습니다."
        
        result = self.telegram_notifier.send_test_message()
        return result['success'], result
    
    def verify_telegram_connection(self) -> Dict[str, Any]:
        """
        텔레그램 연결을 확인합니다.
        
        Returns:
            응답 딕셔너리
        """
        if not self.telegram_notifier:
            return {
                "success": False,
                "message": "텔레그램이 초기화되지 않았습니다."
            }
        
        return self.telegram_notifier.verify_connection()


# ============ 편의 함수들 ============
def send_telegram_test_message(bot_token: str, chat_id: Union[str, List[str]], 
                               server_url: Optional[str] = None) -> Dict[str, Any]:
    """
    텔레그램 테스트 메시지를 전송하는 독립 함수
    
    Args:
        bot_token: 봇 토큰
        chat_id: 채팅 ID (단일 또는 리스트)
        server_url: 서버 URL (있으면 서버 통해 전송)
        
    Returns:
        응답 딕셔너리
    """
    if server_url:
        success, result = test_telegram(server_url=server_url)
        if success:
            return {"success": True, "data": result}
        else:
            return {"success": False, "message": result}
    
    # chat_id를 리스트로 변환
    chat_ids = [chat_id] if isinstance(chat_id, str) else chat_id
    
    notifier = TelegramNotifier(bot_token, chat_ids)
    return notifier.send_test_message()


def verify_telegram_bot(bot_token: str, chat_id: Union[str, List[str]]) -> Dict[str, Any]:
    """
    텔레그램 봇 설정을 확인하는 독립 함수
    
    Args:
        bot_token: 봇 토큰
        chat_id: 채팅 ID (단일 또는 리스트)
        
    Returns:
        응답 딕셔너리
    """
    # chat_id를 리스트로 변환
    chat_ids = [chat_id] if isinstance(chat_id, str) else chat_id
    
    notifier = TelegramNotifier(bot_token, chat_ids)
    return notifier.verify_connection()


def send_custom_telegram_message(bot_token: str, chat_id: Union[str, List[str]], 
                                 message: str, parse_mode: str = "HTML",
                                 importance: str = 'normal') -> Dict[str, Any]:
    """
    커스텀 텔레그램 메시지를 전송하는 독립 함수
    
    Args:
        bot_token: 봇 토큰
        chat_id: 채팅 ID (단일 또는 리스트)
        message: 전송할 메시지
        parse_mode: 파싱 모드
        importance: 중요도
        
    Returns:
        응답 딕셔너리
    """
    # chat_id를 리스트로 변환
    chat_ids = [chat_id] if isinstance(chat_id, str) else chat_id
    
    notifier = TelegramNotifier(bot_token, chat_ids)
    return notifier.send_message(message, parse_mode, importance)


if __name__ == "__main__":
    # 테스트 코드
    print("=" * 60)
    print("Integrated Trading System v2 Complete - 텔레그램 기능")
    print("=" * 60)
    
    print("\n📱 텔레그램 알림 기능:")
    print("-" * 60)
    
    # 예제 사용법
    print("\n🔹 1. 독립 함수 사용 (직접 전송):")
    print("   result = send_telegram_test_message('YOUR_BOT_TOKEN', 'YOUR_CHAT_ID')")
    print("   result = send_telegram_test_message('YOUR_BOT_TOKEN', ['ID1', 'ID2'])")
    
    print("\n🔹 2. 서버를 통한 전송:")
    print("   success, result = test_telegram(server_url='http://localhost:8000')")
    
    print("\n🔹 3. 텔레그램 연결 확인:")
    print("   result = verify_telegram_bot('YOUR_BOT_TOKEN', 'YOUR_CHAT_ID')")
    
    print("\n🔹 4. 커스텀 메시지 전송:")
    print("   result = send_custom_telegram_message(")
    print("       'YOUR_BOT_TOKEN', 'YOUR_CHAT_ID', '메시지',")
    print("       importance='high'  # high, normal, low, error, success, warning")
    print("   )")
    
    print("\n🔹 5. 시스템 클래스 사용:")
    print("   config = {")
    print("       'telegram_bot_token': 'YOUR_TOKEN',")
    print("       'telegram_chat_ids': ['ID1', 'ID2']")
    print("   }")
    print("   system = IntegratedTradingSystem(config)")
    print("   system.send_telegram_notification('메시지', importance='normal')")
    
    print("\n🔹 6. 중요도별 이모지:")
    print("   - high: 🚨")
    print("   - normal: 📊")
    print("   - low: ℹ️")
    print("   - error: ❌")
    print("   - success: ✅")
    print("   - warning: ⚠️")
    
    print("\n" + "=" * 60)
    print("💡 Tip: HTML 파싱 모드가 기본으로 사용됩니다.")
    print("    <b>굵게</b>, <i>기울임</i>, <code>코드</code> 사용 가능")
    print("=" * 60)

