from flask import Flask, request, jsonify
import ccxt
import json
import logging
from datetime import datetime
import os
from dotenv import load_dotenv
import threading
import time
import requests

# 환경 변수 로드
load_dotenv()

# ============ 서버별 하드코딩 설정 ============
SERVER_PORT = 5000  # 여기서 포트 변경 (5000, 5001, 5002)
ENABLE_TELEGRAM = True if SERVER_PORT == 5000 else False  # 5000번 포트만 텔레그램 활성화

app = Flask(__name__)
logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s - [Port:{port}] - %(levelname)s - %(message)s'.format(port=SERVER_PORT))

# Binance 설정
exchange = ccxt.binance({
    'apiKey': os.getenv('BINANCE_API_KEY'),
    'secret': os.getenv('BINANCE_SECRET_KEY'),
    'enableRateLimit': True,
    'options': {
        'defaultType': 'future'  # 선물 거래용
    }
})

# 텔레그램 설정
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_IDS = os.getenv('TELEGRAM_CHAT_IDS', '').split(',')

# ============ 다중 종목 설정 ============
SYMBOL_CONFIG = {
    'BTC/USDT': {
        'leverage': 5,
        'position_size_percent': 20,
        'min_position_size': 10,
        'max_position_size': 100000,
        'enabled': True
    },
    'SAHARA/USDT': {
        'leverage': 10,
        'position_size_percent': 40,
        'min_position_size': 10,
        'max_position_size': 100000,
        'enabled': True
    },
    'ETH/USDT': {
        'leverage': 10,
        'position_size_percent': 30,
        'min_position_size': 10,
        'max_position_size': 100000,
        'enabled': True
    },
    'RESOLV/USDT': {
        'leverage': 10,
        'position_size_percent': 30,
        'min_position_size': 10,
        'max_position_size': 100000,
        'enabled': True
    },
    'BIO/USDT': {
        'leverage': 10,
        'position_size_percent': 30,
        'min_position_size': 10,
        'max_position_size': 100000,
        'enabled': True
    },
    'UNI/USDT': {
        'leverage': 10,
        'position_size_percent': 30,
        'min_position_size': 10,
        'max_position_size': 100000,
        'enabled': True
    },
    'PENGU/USDT': {
        'leverage': 10,
        'position_size_percent': 30,
        'min_position_size': 10,
        'max_position_size': 100000,
        'enabled': True
    },
    'UMA/USDT': {
        'leverage': 10,
        'position_size_percent': 30,
        'min_position_size': 10,
        'max_position_size': 100000,
        'enabled': True
    },  
    'COMP/USDT': {
        'leverage': 10,
        'position_size_percent': 30,
        'min_position_size': 10,
        'max_position_size': 100000,
        'enabled': True
    },  
    'XLM/USDT': {
        'leverage': 10,
        'position_size_percent': 30,
        'min_position_size': 10,
        'max_position_size': 100000,
        'enabled': True
    },
    'DOT/USDT': {
        'leverage': 10,
        'position_size_percent': 30,
        'min_position_size': 10,
        'max_position_size': 100000,
        'enabled': True
    },   
    'ENA/USDT': {
        'leverage': 10,
        'position_size_percent': 30,
        'min_position_size': 10,
        'max_position_size': 100000,
        'enabled': True
    },
    'RLC/USDT': {
        'leverage': 10,
        'position_size_percent': 30,
        'min_position_size': 10,
        'max_position_size': 100000,
        'enabled': True
    },
    'ETHFI/USDT': {
        'leverage': 10,
        'position_size_percent': 30,
        'min_position_size': 10,
        'max_position_size': 100000,
        'enabled': True
    },
    'SOL/USDT': {
        'leverage': 10,
        'position_size_percent': 30,
        'min_position_size': 10,
        'max_position_size': 100000,
        'enabled': True
    },
    'PYTH/USDT': {
        'leverage': 10,
        'position_size_percent': 30,
        'min_position_size': 10,
        'max_position_size': 100000,
        'enabled': True
    },
    'LINK/USDT': {
        'leverage': 10,
        'position_size_percent': 30,
        'min_position_size': 10,
        'max_position_size': 100000,
        'enabled': True
    },
    'ADA/USDT': {
        'leverage': 10,
        'position_size_percent': 30,
        'min_position_size': 10,
        'max_position_size': 100000,
        'enabled': True
    } 
}

# 기본 설정
DEFAULT_POSITION_SIZE_PERCENT = float(os.getenv('POSITION_SIZE_PERCENT', 10))
DEFAULT_MIN_POSITION_SIZE = float(os.getenv('MIN_POSITION_SIZE', 10))
DEFAULT_MAX_POSITION_SIZE = float(os.getenv('MAX_POSITION_SIZE', 100000))

# 포지션 추적
current_positions = {}
position_monitor_threads = {}

def get_symbol_config(symbol):
    """종목별 설정 가져오기"""
    if symbol in SYMBOL_CONFIG:
        return SYMBOL_CONFIG[symbol]
    else:
        return {
            'leverage': 10,
            'position_size_percent': DEFAULT_POSITION_SIZE_PERCENT,
            'min_position_size': DEFAULT_MIN_POSITION_SIZE,
            'max_position_size': DEFAULT_MAX_POSITION_SIZE,
            'enabled': True
        }

def send_telegram_notification(message, priority='normal'):
    """텔레그램으로 알림 전송"""
    if not ENABLE_TELEGRAM:
        logging.info(f"[Port {SERVER_PORT} - Telegram Disabled] {message}")
        return
    
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_IDS:
        logging.warning(f"[Port {SERVER_PORT}] 텔레그램 설정이 없습니다.")
        return
    
    for chat_id in TELEGRAM_CHAT_IDS:
        if not chat_id.strip():
            continue
            
        try:
            url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
            
            if priority == 'high':
                message = f"🚨 <b>중요 알림</b> 🚨\n\n{message}"
            elif priority == 'error':
                message = f"❌ <b>오류 발생</b> ❌\n\n{message}"
            
            payload = {
                'chat_id': chat_id.strip(),
                'text': message,
                'parse_mode': 'HTML',
                'disable_web_page_preview': True
            }
            
            response = requests.post(url, data=payload, timeout=5)
            
            if response.status_code == 200:
                logging.info(f"✅ 텔레그램 알림 전송 성공: {chat_id}")
            else:
                logging.error(f"❌ 텔레그램 전송 실패: {response.text}")
                
        except Exception as e:
            logging.error(f"텔레그램 전송 오류: {e}")

def cleanup_open_orders(symbol):
    """특정 심볼의 모든 열린 주문 취소"""
    try:
        open_orders = exchange.fetch_open_orders(symbol)
        canceled_orders = []
        
        for order in open_orders:
            try:
                exchange.cancel_order(order['id'], symbol)
                canceled_orders.append(order['id'])
                logging.info(f"주문 취소 완료 ({symbol}): {order['id']} - {order['type']}")
            except Exception as cancel_error:
                logging.warning(f"주문 취소 실패 ({symbol}): {order['id']} - {str(cancel_error)}")
        
        if canceled_orders:
            logging.info(f"총 {len(canceled_orders)}개 주문 취소 완료 ({symbol})")
        
        return canceled_orders
        
    except Exception as e:
        logging.error(f"열린 주문 정리 실패 ({symbol}): {str(e)}")
        return []

def monitor_position_status(symbol):
    """포지션 상태를 모니터링하고 종료 시 자동으로 관련 주문 정리"""
    try:
        logging.info(f"포지션 상태 모니터링 시작 ({symbol})")
        check_interval = 5  # 5초마다 체크
        
        while symbol in current_positions:
            time.sleep(check_interval)
            
            try:
                # 실제 포지션 확인
                positions = exchange.fetch_positions([symbol])
                has_position = any(p['contracts'] > 0 for p in positions)
                
                # 포지션이 종료된 경우
                if not has_position:
                    logging.info(f"포지션 종료 감지 ({symbol})")
                    
                    # 남은 주문 모두 취소
                    cleanup_open_orders(symbol)
                    
                    # 포지션 정보 정리
                    if symbol in current_positions:
                        exit_reason = "trailing_stop" if current_positions[symbol].get('trailing_stop_active') else "unknown"
                        
                        # PnL 계산 시도
                        try:
                            closed_positions = exchange.fetch_closed_orders(symbol, limit=1)
                            if closed_positions:
                                last_order = closed_positions[0]
                                pnl = last_order.get('info', {}).get('realizedPnl', 0)
                            else:
                                pnl = None
                        except:
                            pnl = None
                        
                        # 종료 메시지 전송
                        close_message = format_position_close_message(symbol, exit_reason, pnl)
                        send_telegram_notification(close_message, 'high')
                        
                        # 포지션 정보 삭제
                        del current_positions[symbol]
                    
                    # 모니터링 종료
                    break
                    
            except Exception as check_error:
                logging.error(f"포지션 체크 오류 ({symbol}): {str(check_error)}")
                time.sleep(check_interval * 2)  # 오류 시 더 긴 대기
        
    except Exception as e:
        logging.error(f"포지션 모니터링 오류 ({symbol}): {str(e)}")
    finally:
        logging.info(f"포지션 상태 모니터링 종료 ({symbol})")
        if symbol in position_monitor_threads:
            del position_monitor_threads[symbol]

def start_position_monitor(symbol):
    """포지션 모니터링 스레드 시작"""
    if symbol in position_monitor_threads:
        return  # 이미 모니터링 중
    
    thread = threading.Thread(
        target=monitor_position_status,
        args=(symbol,)
    )
    thread.daemon = True
    thread.start()
    position_monitor_threads[symbol] = thread
    logging.info(f"포지션 모니터링 스레드 시작 ({symbol})")

def format_position_entry_message(symbol, action, amount, entry_price, stop_loss, take_profit, pl_ratio, position_size, balance, trailing_stop_percent=None, trailing_activation_percent=None):
    """포지션 진입 메시지 포맷"""
    direction_emoji = "🚀" if action == "buy" else "📉"
    direction_text = "LONG" if action == "buy" else "SHORT"
    
    # 리스크/리워드 계산
    risk_amount = abs(entry_price - stop_loss) * amount
    reward_amount = abs(take_profit - entry_price) * amount
    
    # 증거금 계산
    config = get_symbol_config(symbol)
    leverage = config['leverage']
    margin_used = position_size / leverage
    margin_percent = (margin_used / balance) * 100
    
    # 트레일링 스탑 정보 추가
    trailing_text = ""
    if trailing_stop_percent:
        trailing_text = f"\n📊 <b>트레일링 스탑:</b> {trailing_stop_percent:.1f}%"
        if trailing_activation_percent and trailing_activation_percent > 0:
            trailing_text += f" (활성화: +{trailing_activation_percent:.1f}%)"
    
    # 가격 포맷팅 (큰 숫자와 작은 숫자 모두 처리)
    def format_price(price):
        if price >= 100:
            return f"{price:,.2f}"
        elif price >= 1:
            return f"{price:.4f}"
        else:
            return f"{price:.8f}"
    
    message = f"""
{direction_emoji} <b>새 포지션 진입 - {symbol}</b>

📊 <b>방향:</b> {direction_text}
💰 <b>수량:</b> {amount:.6f}
💵 <b>포지션 크기:</b> ${position_size:.2f}
🏦 <b>사용 증거금:</b> ${margin_used:.2f} ({margin_percent:.1f}%)
💵 <b>진입가:</b> ${format_price(entry_price)}
🛑 <b>손절가:</b> ${format_price(stop_loss)}
🎯 <b>익절가:</b> ${format_price(take_profit)}{trailing_text}
📈 <b>손익비:</b> {pl_ratio:.1f}:1
⚙️ <b>레버리지:</b> {leverage}x

💸 <b>최대 손실:</b> ${risk_amount:.2f}
💰 <b>예상 수익:</b> ${reward_amount:.2f}
💳 <b>현재 잔고:</b> ${balance:,.2f}

⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
    """.strip()
    
    return message

def place_order_with_stops(symbol, side, amount, entry_price, stop_loss_price, take_profit_price, pl_ratio, trailing_stop_percent=None, trailing_activation_percent=None):
    """트레일링 스탑과 백업 손절을 포함한 주문 실행 - 활성화 가격 지원"""
    try:
        config = get_symbol_config(symbol)
        
        # 심볼 정보 가져오기
        markets = exchange.load_markets()
        market = markets[symbol]
        
        # 수량 정밀도 적용
        amount_precision = market['precision']['amount']
        min_amount = market['limits']['amount']['min']
        
        # 가격 정밀도 가져오기
        price_precision = market['precision']['price']
        
        # 수량 조정
        adjusted_amount = exchange.amount_to_precision(symbol, amount)
        
        if float(adjusted_amount) < min_amount:
            adjusted_amount = min_amount
        
        # 레버리지 설정
        exchange.set_leverage(config['leverage'], symbol)
        
        # 1. 메인 주문 실행
        logging.info(f"메인 주문 실행 ({symbol}): {side} {adjusted_amount} @ market")
        main_order = exchange.create_order(
            symbol=symbol,
            type='market',
            side=side,
            amount=adjusted_amount
        )
        
        if main_order:
            actual_entry = main_order.get('average', main_order.get('price', entry_price))
            
            # 현재 가격 가져오기 (활성화 가격 계산용)
            ticker = exchange.fetch_ticker(symbol)
            current_price = ticker['last']
            
            # 2. 주문 옵션 설정
            stop_side = 'sell' if side == 'buy' else 'buy'
            orders_placed = {'main': main_order}
            
            # 3. 백업 손절 주문 (항상 설정)
            logging.info(f"백업 손절 설정: ${stop_loss_price:.2f}")
            try:
                # 손절 가격도 정밀도 적용
                formatted_stop_loss = float(exchange.price_to_precision(symbol, stop_loss_price))
                
                sl_order = exchange.create_order(
                    symbol=symbol,
                    type='stop_market',
                    side=stop_side,
                    amount=adjusted_amount,
                    params={
                        'stopPrice': formatted_stop_loss,
                        'workingType': 'MARK_PRICE',
                        'reduceOnly': True
                    }
                )
                orders_placed['stop_loss'] = sl_order
                logging.info(f"백업 손절 설정 완료: ${formatted_stop_loss}")
            except Exception as sl_error:
                logging.error(f"백업 손절 설정 실패: {str(sl_error)}")
            
            # 4. 트레일링 스탑 설정 (있는 경우)
            trailing_order_success = False
            activation_price = None
            
            if trailing_stop_percent and trailing_stop_percent > 0:
                # 활성화 가격 계산
                if trailing_activation_percent and trailing_activation_percent > 0:
                    # 수익률 도달시 트레일링 활성화
                    if side == 'buy':
                        raw_activation_price = current_price * (1 + trailing_activation_percent / 100)
                    else:
                        raw_activation_price = current_price * (1 - trailing_activation_percent / 100)
                else:
                    # 즉시 활성화
                    raw_activation_price = current_price
                
                # 정밀도 레벨 설정 (높은 정밀도부터 시작)
                def get_precision_levels(price):
                    """가격대별 정밀도 레벨 리스트 반환 (높은 정밀도부터 낮은 정밀도 순)"""
                    if price >= 10000:
                        return [2, 1, 0]  # BTC 같은 큰 가격
                    elif price >= 1000:
                        return [3, 2, 1, 0]
                    elif price >= 100:
                        return [4, 3, 2, 1]
                    elif price >= 10:
                        return [4, 3, 2, 1]
                    elif price >= 1:
                        return [6, 5, 4, 3, 2]  # ETHFI 같은 작은 가격 (최소 4자리 시작)
                    else:
                        return [8, 7, 6, 5, 4, 3, 2]  # 아주 작은 가격
                
                precision_levels = get_precision_levels(raw_activation_price)
                
                # 정밀도를 낮춰가며 주문 시도
                for precision in precision_levels:
                    try:
                        # 현재 정밀도로 활성화 가격 포맷팅
                        formatted_activation_price = round(raw_activation_price, precision)
                        
                        # ccxt의 price_to_precision도 적용해보기
                        try:
                            ccxt_formatted = float(exchange.price_to_precision(symbol, formatted_activation_price))
                            if ccxt_formatted != formatted_activation_price:
                                logging.info(f"CCXT 정밀도 조정: {formatted_activation_price} -> {ccxt_formatted}")
                                formatted_activation_price = ccxt_formatted
                        except:
                            pass  # ccxt 정밀도 실패시 그대로 사용
                        
                        activation_price = formatted_activation_price
                        
                        logging.info(f"트레일링 활성화 가격 시도 (정밀도 {precision}): 원본=${raw_activation_price:.8f}, 포맷=${formatted_activation_price}")
                        
                        # 트레일링 스탑 파라미터
                        trailing_params = {
                            'reduceOnly': True,
                            'workingType': 'MARK_PRICE',
                            'activationPrice': formatted_activation_price,
                            'callbackRate': float(trailing_stop_percent),
                        }
                        
                        # 디버깅용 로그
                        logging.info(f"트레일링 파라미터 (시도 {precision_levels.index(precision)+1}/{len(precision_levels)}): {trailing_params}")
                        
                        trailing_order = exchange.create_order(
                            symbol=symbol,
                            type='trailing_stop_market',
                            side=stop_side,
                            amount=adjusted_amount,
                            params=trailing_params
                        )
                        
                        orders_placed['trailing_stop'] = trailing_order
                        trailing_order_success = True
                        logging.info(f"✅ 트레일링 스탑 설정 성공: {trailing_stop_percent}% (활성화: ${formatted_activation_price}, 정밀도: {precision})")
                        
                        # 트레일링 스탑이 성공하면 백업 손절을 더 낮은 위치로 조정
                        try:
                            if 'stop_loss' in orders_placed and orders_placed['stop_loss']:
                                # 기존 백업 손절 취소
                                exchange.cancel_order(orders_placed['stop_loss']['id'], symbol)
                                
                                # 더 낮은 백업 손절 재설정 (원래 손절의 1.5배 거리)
                                if side == 'buy':
                                    emergency_stop = actual_entry - (actual_entry - stop_loss_price) * 1.5
                                else:
                                    emergency_stop = actual_entry + (stop_loss_price - actual_entry) * 1.5
                                
                                # 비상 손절도 정밀도 적용
                                formatted_emergency_stop = float(exchange.price_to_precision(symbol, emergency_stop))
                                
                                emergency_sl_order = exchange.create_order(
                                    symbol=symbol,
                                    type='stop_market',
                                    side=stop_side,
                                    amount=adjusted_amount,
                                    params={
                                        'stopPrice': formatted_emergency_stop,
                                        'workingType': 'MARK_PRICE',
                                        'reduceOnly': True
                                    }
                                )
                                orders_placed['emergency_stop'] = emergency_sl_order
                                logging.info(f"비상 손절 재설정: ${formatted_emergency_stop}")
                        except Exception as e:
                            logging.warning(f"백업 손절 조정 실패: {str(e)}")
                        
                        # 성공했으므로 루프 종료
                        break
                        
                    except Exception as ts_error:
                        error_msg = str(ts_error)
                        logging.warning(f"트레일링 스탑 실패 (정밀도 {precision}): {error_msg}")
                        
                        # 마지막 시도였다면 수동 모드로 전환
                        if precision == precision_levels[-1]:
                            trailing_order_success = False
                            logging.error(f"모든 정밀도 시도 실패. 수동 모드로 전환")
                            
                            # 트레일링 스탑 실패시 수동 트레일링 스레드 시작
                            thread = threading.Thread(
                                target=monitor_trailing_stop,
                                args=(symbol, side, adjusted_amount, actual_entry, trailing_stop_percent, stop_loss_price, trailing_activation_percent)
                            )
                            thread.daemon = True
                            thread.start()
                            logging.info("수동 트레일링 스탑 모니터링 시작")
                        else:
                            # 다음 정밀도로 재시도
                            logging.info(f"낮은 정밀도로 재시도...")
                            continue
            
            # 5. 익절 주문 설정
            try:
                # 익절 가격도 정밀도 적용
                formatted_take_profit = float(exchange.price_to_precision(symbol, take_profit_price))
                
                tp_order = exchange.create_order(
                    symbol=symbol,
                    type='take_profit_market',
                    side=stop_side,
                    amount=adjusted_amount,
                    params={
                        'stopPrice': formatted_take_profit,
                        'workingType': 'MARK_PRICE',
                        'reduceOnly': True
                    }
                )
                orders_placed['take_profit'] = tp_order
                logging.info(f"익절 설정 완료: ${formatted_take_profit}")
            except Exception as tp_error:
                logging.warning(f"익절 설정 실패: {str(tp_error)}")
            
            # 6. 포지션 정보 저장
            current_positions[symbol] = {
                'side': side,
                'amount': float(adjusted_amount),
                'entry_price': actual_entry,
                'stop_loss': stop_loss_price,
                'take_profit': take_profit_price,
                'trailing_stop_percent': trailing_stop_percent,
                'trailing_activation_percent': trailing_activation_percent,
                'trailing_activation_price': activation_price,
                'trailing_stop_active': trailing_order_success,
                'pl_ratio': pl_ratio,
                'sl_order_id': orders_placed.get('stop_loss', {}).get('id'),
                'emergency_sl_order_id': orders_placed.get('emergency_stop', {}).get('id'),
                'tp_order_id': orders_placed.get('take_profit', {}).get('id'),
                'trailing_order_id': orders_placed.get('trailing_stop', {}).get('id'),
                'timestamp': datetime.now().isoformat(),
                'manual_entry': False
            }
            
            # 7. 포지션 모니터링 시작 (트레일링 스탑이 있는 경우)
            if trailing_stop_percent and trailing_stop_percent > 0:
                start_position_monitor(symbol)
            
            logging.info(f"""
            ✅ 주문 완료 ({symbol}):
            - Entry: ${actual_entry:.8f}
            - Stop Loss: ${stop_loss_price:.8f} (백업)
            - Take Profit: ${take_profit_price:.8f}
            - Trailing Stop: {trailing_stop_percent}% ({'활성' if trailing_order_success else '수동모드'})
            - Activation Price: ${activation_price:.8f if activation_price else 'N/A'}
            - 설정된 주문: {list(orders_placed.keys())}
            """)
            
            return {
                'main_order': main_order,
                'orders_placed': orders_placed,
                'actual_entry': actual_entry,
                'adjusted_amount': adjusted_amount,
                'trailing_success': trailing_order_success
            }
            
    except Exception as e:
        logging.error(f"주문 실행 실패 ({symbol}): {str(e)}")
        return None

def monitor_trailing_stop(symbol, side, amount, entry_price, trailing_stop_percent, initial_stop_loss, trailing_activation_percent=None):
    """수동 트레일링 스탑 모니터링 (백그라운드) - 활성화 가격 지원"""
    try:
        logging.info(f"수동 트레일링 스탑 모니터링 시작 ({symbol}): {trailing_stop_percent}% (활성화: {trailing_activation_percent}%)")
        
        highest_price = entry_price if side == 'buy' else 0
        lowest_price = entry_price if side == 'sell' else float('inf')
        current_stop = initial_stop_loss
        trailing_activated = False
        
        # 활성화 가격 계산
        activation_price = None
        if trailing_activation_percent and trailing_activation_percent > 0:
            if side == 'buy':
                activation_price = entry_price * (1 + trailing_activation_percent / 100)
            else:
                activation_price = entry_price * (1 - trailing_activation_percent / 100)
            logging.info(f"트레일링 활성화 대기: ${activation_price:.2f}")
        else:
            trailing_activated = True  # 즉시 활성화
            logging.info("트레일링 즉시 활성화")
        
        while symbol in current_positions:
            time.sleep(10)  # 10초마다 체크
            
            try:
                # 포지션 상태 확인
                positions = exchange.fetch_positions([symbol])
                has_position = any(p['contracts'] > 0 for p in positions)
                
                if not has_position:
                    # 포지션이 종료된 경우 남은 주문 정리
                    logging.info(f"수동 트레일링: 포지션 종료 감지 ({symbol})")
                    cleanup_open_orders(symbol)
                    break
                
                ticker = exchange.fetch_ticker(symbol)
                current_price = ticker['last']
                
                # 활성화 체크
                if not trailing_activated and activation_price:
                    if side == 'buy' and current_price >= activation_price:
                        trailing_activated = True
                        logging.info(f"트레일링 활성화! ({symbol}): 현재가 ${current_price:.2f} >= 활성화가 ${activation_price:.2f}")
                    elif side == 'sell' and current_price <= activation_price:
                        trailing_activated = True
                        logging.info(f"트레일링 활성화! ({symbol}): 현재가 ${current_price:.2f} <= 활성화가 ${activation_price:.2f}")
                
                # 트레일링 스탑 업데이트 (활성화된 경우만)
                if trailing_activated:
                    if side == 'buy':
                        # 롱 포지션: 최고가 업데이트
                        if current_price > highest_price:
                            highest_price = current_price
                            new_stop = highest_price * (1 - trailing_stop_percent / 100)
                            
                            # 새로운 손절가가 기존보다 높은 경우만 업데이트
                            if new_stop > current_stop:
                                update_stop_loss(symbol, new_stop, amount, side)
                                current_stop = new_stop
                                logging.info(f"트레일링 스탑 업데이트 ({symbol}): ${new_stop:.2f}")
                    else:  # sell
                        # 숏 포지션: 최저가 업데이트
                        if current_price < lowest_price:
                            lowest_price = current_price
                            new_stop = lowest_price * (1 + trailing_stop_percent / 100)
                            
                            # 새로운 손절가가 기존보다 낮은 경우만 업데이트
                            if new_stop < current_stop:
                                update_stop_loss(symbol, new_stop, amount, side)
                                current_stop = new_stop
                                logging.info(f"트레일링 스탑 업데이트 ({symbol}): ${new_stop:.2f}")
                            
            except Exception as tick_error:
                logging.error(f"가격 체크 오류 ({symbol}): {str(tick_error)}")
                time.sleep(30)  # 오류 시 30초 대기
            
    except Exception as e:
        logging.error(f"트레일링 스탑 모니터링 오류 ({symbol}): {str(e)}")
    finally:
        logging.info(f"트레일링 스탑 모니터링 종료 ({symbol})")

def update_stop_loss(symbol, new_stop_price, amount, side):
    """손절 주문 업데이트"""
    try:
        pos = current_positions.get(symbol)
        if not pos:
            return
        
        # 기존 손절 주문 취소
        if pos.get('sl_order_id'):
            try:
                exchange.cancel_order(pos['sl_order_id'], symbol)
                logging.info(f"기존 손절 주문 취소: {pos['sl_order_id']}")
            except:
                pass  # 이미 취소된 경우 무시
        
        # 새 손절 주문 생성
        stop_side = 'sell' if side == 'buy' else 'buy'
        new_order = exchange.create_order(
            symbol=symbol,
            type='stop_market',
            side=stop_side,
            amount=amount,
            params={
                'stopPrice': new_stop_price,
                'workingType': 'MARK_PRICE',
                'reduceOnly': True
            }
        )
        
        # 포지션 정보 업데이트
        current_positions[symbol]['sl_order_id'] = new_order['id']
        current_positions[symbol]['stop_loss'] = new_stop_price
        
        logging.info(f"손절 주문 업데이트 완료 ({symbol}): ${new_stop_price:.2f}")
        
    except Exception as e:
        logging.error(f"손절 업데이트 실패 ({symbol}): {str(e)}")

def close_position(symbol):
    """특정 심볼의 포지션 종료 및 모든 관련 주문 정리"""
    try:
        positions = exchange.fetch_positions([symbol])
        
        # 포지션 청산
        for position in positions:
            if position['contracts'] > 0:
                side = 'sell' if position['side'] == 'long' else 'buy'
                amount = abs(position['contracts'])
                
                exchange.create_order(
                    symbol=symbol,
                    type='market',
                    side=side,
                    amount=amount,
                    params={'reduceOnly': True}
                )
        
        # 모든 열린 주문 취소
        cleanup_open_orders(symbol)
        
        # 포지션 정보 초기화
        if symbol in current_positions:
            del current_positions[symbol]
        
        return True
            
    except Exception as e:
        logging.error(f"포지션 종료 실패 ({symbol}): {str(e)}")
        return False

def sync_positions_with_exchange():
    """거래소의 실제 포지션과 봇의 추적 정보를 동기화"""
    try:
        for symbol, config in SYMBOL_CONFIG.items():
            if not config.get('enabled', True):
                continue
                
            positions = exchange.fetch_positions([symbol])
            
            for position in positions:
                if position['contracts'] > 0:
                    logging.info(f"활성 포지션 발견 ({symbol}): {position['side']} {position['contracts']}")
                    
                    if symbol not in current_positions:
                        logging.info(f"수동 진입 포지션을 봇에 등록합니다: {symbol}")
                        
                        current_positions[symbol] = {
                            'side': 'buy' if position['side'] == 'long' else 'sell',
                            'amount': position['contracts'],
                            'entry_price': position.get('entryPrice', position['markPrice']),
                            'timestamp': datetime.now().isoformat(),
                            'manual_entry': True
                        }
                        
                        # 수동 진입 포지션도 모니터링 시작
                        start_position_monitor(symbol)
            
            # 포지션이 없는데 current_positions에 있는 경우 정리
            if not any(p['contracts'] > 0 for p in positions) and symbol in current_positions:
                logging.info(f"포지션이 종료되었습니다: {symbol}")
                # 남은 주문 정리
                cleanup_open_orders(symbol)
                del current_positions[symbol]
        
        return True
        
    except Exception as e:
        logging.error(f"포지션 동기화 실패: {str(e)}")
        return False

def format_position_close_message(symbol, reason="수동 종료", pnl=None):
    """포지션 종료 메시지 포맷"""
    pnl_text = ""
    if pnl is not None:
        pnl_emoji = "💰" if pnl >= 0 else "💸"
        pnl_text = f"\n{pnl_emoji} <b>손익:</b> ${pnl:.2f}"
    
    message = f"""
❌ <b>포지션 종료 - {symbol}</b>

📋 <b>종료 사유:</b> {reason}{pnl_text}
⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
    """.strip()
    
    return message

def calculate_position_size(symbol, balance):
    """잔고 기반 포지션 크기 계산"""
    if balance is None:
        return None
    
    config = get_symbol_config(symbol)
    
    # 증거금 = 잔고의 X%
    margin = balance * config['position_size_percent'] / 100
    
    # 레버리지 설정
    leverage = config['leverage']
    
    # 포지션 크기 = 증거금 × 레버리지
    position_size = margin * leverage
    
    # 최소/최대 제한 적용
    position_size = max(config['min_position_size'], 
                       min(position_size, config['max_position_size']))
    
    logging.info(f"포지션 크기 계산 ({symbol}): ${position_size:.2f}")
    
    return position_size

def get_account_balance():
    """Binance 계정 잔고 조회"""
    try:
        balance = exchange.fetch_balance()
        free_usdt = balance['USDT']['free']
        return free_usdt
    except Exception as e:
        logging.error(f"잔고 조회 실패: {str(e)}")
        return None

def initialize_bot():
    """봇 초기화"""
    logging.info(f"봇 초기화 중... (포트: {SERVER_PORT})")
    
    enabled_symbols = [s for s, c in SYMBOL_CONFIG.items() if c.get('enabled', True)]
    
    start_message = f"""
🤖 <b>트레이딩 봇 시작</b>

🌐 <b>서버 포트:</b> {SERVER_PORT}
📊 <b>활성 심볼:</b> {', '.join(enabled_symbols)}
🔄 <b>트레일링 스탑:</b> 활성화 (자동 정리)
📱 <b>텔레그램:</b> {'활성화' if ENABLE_TELEGRAM else '비활성화'}

⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
    """.strip()
    
    send_telegram_notification(start_message, 'normal')
    sync_positions_with_exchange()
    logging.info(f"봇 초기화 완료")

@app.route('/webhook', methods=['POST'])
def webhook():
    """TradingView 웹훅 수신 - 트레일링 스탑 활성화 가격 지원"""
    try:
        # 데이터 파싱
        raw_data = request.get_data(as_text=True)
        logging.info(f"웹훅 데이터 수신: {raw_data[:200]}")
        
        try:
            data = json.loads(raw_data)
        except:
            data = request.get_json()
        
        if not data:
            return jsonify({'error': 'No data received'}), 400
        
        # 심볼 매핑
        symbol = data.get('symbol', 'BTC/USDT')
        symbol_mapping = {
            'BTCUSDT': 'BTC/USDT',
            'BTCUSDT.P': 'BTC/USDT',
            'SAHARAUSDT': 'SAHARA/USDT',
            'SAHARAUSDT.P': 'SAHARA/USDT',
            'ETHUSDT': 'ETH/USDT',
            'ETHUSDT.P': 'ETH/USDT',
            'RESOLVUSDT': 'RESOLV/USDT',
            'RESOLVUSDT.P': 'RESOLV/USDT',
            'BIOUSDT': 'BIO/USDT',
            'BIOUSDT.P': 'BIO/USDT',
            'UNIUSDT': 'UNI/USDT',
            'UNIUSDT.P': 'UNI/USDT',
            'PENGUUSDT': 'PENGU/USDT',
            'PENGUUSDT.P': 'PENGU/USDT',
            'UMAUSDT': 'UMA/USDT',
            'UMAUSDT.P': 'UMA/USDT',    
            'COMPUSDT': 'COMP/USDT',
            'COMPUSDT.P': 'COMP/USDT',
            'XLMUSDT': 'XLM/USDT',
            'XLMUSDT.P': 'XLM/USDT',
            'DOTUSDT': 'DOT/USDT',
            'DOTUSDT.P': 'DOT/USDT',
            'ENAUSDT': 'ENA/USDT',
            'ENAUSDT.P': 'ENA/USDT',
            'RLCUSDT': 'RLC/USDT',
            'RLCUSDT.P': 'RLC/USDT',
            'ETHFIUSDT': 'ETHFI/USDT',
            'ETHFIUSDT.P': 'ETHFI/USDT',
            'SOLUSDT': 'SOL/USDT',
            'SOLUSDT.P': 'SOL/USDT',
            'PYTHUSDT': 'PYTH/USDT',
            'PYTHUSDT.P': 'PYTH/USDT',
            'LINKUSDT': 'LINK/USDT',
            'LINKUSDT.P': 'LINK/USDT',
            'ADAUSDT': 'ADA/USDT',
            'ADAUSDT.P': 'ADA/USDT'         
        }
        
        if symbol in symbol_mapping:
            symbol = symbol_mapping[symbol]
        
        action = data.get('action')
        
        # 포지션 종료
        if action == 'close_position':
            exit_reason = data.get('exit_reason', 'signal_cross')
            
            pnl = None
            if symbol in current_positions:
                try:
                    ticker = exchange.fetch_ticker(symbol)
                    current_price = ticker['last']
                    pos = current_positions[symbol]
                    
                    if pos['side'] == 'buy':
                        pnl = (current_price - pos['entry_price']) * pos['amount']
                    else:
                        pnl = (pos['entry_price'] - current_price) * pos['amount']
                except:
                    pass
            
            success = close_position(symbol)
            
            if success:
                close_message = format_position_close_message(symbol, exit_reason, pnl)
                send_telegram_notification(close_message, 'high')
                
                return jsonify({
                    'status': 'success',
                    'action': 'position_closed',
                    'symbol': symbol
                }), 200
        
        # 신규 포지션 진입
        elif action in ['buy', 'sell']:
            # 트레일링 스탑 비율 파싱
            trailing_stop_data = data.get('trailing_stop_percent')
            trailing_stop_percent = None
            
            if trailing_stop_data and trailing_stop_data != 'null':
                try:
                    trailing_stop_percent = float(trailing_stop_data)
                    logging.info(f"트레일링 스탑 비율: {trailing_stop_percent}%")
                except:
                    trailing_stop_percent = None
                    logging.warning("트레일링 스탑 값 파싱 실패")
            
            # 트레일링 활성화 비율 파싱
            trailing_activation_data = data.get('trailing_activation_percent')
            trailing_activation_percent = None
            
            if trailing_activation_data and trailing_activation_data != 'null' and trailing_activation_data != '0':
                try:
                    trailing_activation_percent = float(trailing_activation_data)
                    logging.info(f"트레일링 활성화 비율: {trailing_activation_percent}%")
                except:
                    trailing_activation_percent = None
                    logging.warning("트레일링 활성화 값 파싱 실패")
            
            # 필수 필드 확인
            entry_price = float(data.get('entry_price'))
            stop_loss_price = float(data.get('stop_loss'))
            pl_ratio = float(data.get('pl_ratio', 3.0))
            
            # take_profit 처리
            take_profit_data = data.get('take_profit')
            if take_profit_data and take_profit_data != 'null':
                try:
                    take_profit_price = float(take_profit_data)
                except:
                    sl_distance = abs(entry_price - stop_loss_price)
                    take_profit_price = entry_price + (sl_distance * pl_ratio) if action == 'buy' else entry_price - (sl_distance * pl_ratio)
            else:
                sl_distance = abs(entry_price - stop_loss_price)
                take_profit_price = entry_price + (sl_distance * pl_ratio) if action == 'buy' else entry_price - (sl_distance * pl_ratio)
            
            # 기존 포지션 체크
            if symbol in current_positions:
                if current_positions[symbol]['side'] == action:
                    return jsonify({
                        'status': 'skipped',
                        'reason': '같은 방향 포지션 이미 존재'
                    }), 200
                else:
                    close_position(symbol)
            
            # 잔고 확인 및 포지션 크기 계산
            balance = get_account_balance()
            if balance is None:
                return jsonify({'error': '잔고 조회 실패'}), 500
            
            position_size = calculate_position_size(symbol, balance)
            if position_size is None:
                return jsonify({'error': '포지션 크기 계산 실패'}), 500
            
            amount = position_size / entry_price
            
            logging.info(f"""
            ===== 주문 요청 ({symbol}) =====
            - Action: {action}
            - Amount: {amount:.6f}
            - Entry: ${entry_price:.2f}
            - Stop Loss: ${stop_loss_price:.2f}
            - Take Profit: ${take_profit_price:.2f}
            - Trailing Stop: {trailing_stop_percent}%
            - Trailing Activation: {trailing_activation_percent}%
            - P/L Ratio: {pl_ratio}:1
            =======================
            """)
            
            # 주문 실행 (트레일링 스탑 및 활성화 가격 포함)
            orders = place_order_with_stops(
                symbol, action, amount, entry_price, 
                stop_loss_price, take_profit_price, pl_ratio,
                trailing_stop_percent,  # 트레일링 스탑 비율
                trailing_activation_percent  # 트레일링 활성화 비율
            )
            
            if orders:
                actual_amount = float(orders.get('adjusted_amount', amount))
                entry_message = format_position_entry_message(
                    symbol, action, actual_amount, orders['actual_entry'],
                    stop_loss_price, take_profit_price,
                    pl_ratio, position_size, balance, 
                    trailing_stop_percent, trailing_activation_percent
                )
                send_telegram_notification(entry_message, 'high')
                
                return jsonify({
                    'status': 'success',
                    'action': action,
                    'symbol': symbol,
                    'amount': actual_amount,
                    'entry_price': orders['actual_entry'],
                    'stop_loss': stop_loss_price,
                    'take_profit': take_profit_price,
                    'trailing_stop_percent': trailing_stop_percent,
                    'trailing_activation_percent': trailing_activation_percent,
                    'pl_ratio': pl_ratio
                }), 200
            else:
                return jsonify({'error': '주문 실행 실패'}), 500
        
        else:
            return jsonify({'error': f'알 수 없는 액션: {action}'}), 400
            
    except Exception as e:
        logging.error(f"웹훅 처리 오류: {str(e)}")
        
        error_message = f"""
❌ <b>웹훅 처리 오류</b>

<b>오류:</b> {str(e)}
⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
        """.strip()
        
        send_telegram_notification(error_message, 'error')
        return jsonify({'error': str(e)}), 500

@app.route('/positions', methods=['GET'])
def get_positions():
    """모든 포지션 상태 조회"""
    try:
        sync_positions_with_exchange()
        
        all_positions = {}
        
        for symbol in SYMBOL_CONFIG.keys():
            if not SYMBOL_CONFIG[symbol].get('enabled', True):
                continue
                
            positions = exchange.fetch_positions([symbol])
            open_orders = exchange.fetch_open_orders(symbol)
            
            ticker = exchange.fetch_ticker(symbol)
            current_price = ticker['last']
            
            position_info = {}
            if symbol in current_positions:
                pos = current_positions[symbol]
                if pos['side'] == 'buy':
                    unrealized_pnl = (current_price - pos['entry_price']) * pos['amount']
                    pnl_percent = ((current_price - pos['entry_price']) / pos['entry_price']) * 100
                else:
                    unrealized_pnl = (pos['entry_price'] - current_price) * pos['amount']
                    pnl_percent = ((pos['entry_price'] - current_price) / pos['entry_price']) * 100
                
                position_info = {
                    'unrealized_pnl': unrealized_pnl,
                    'pnl_percent': pnl_percent,
                    'current_price': current_price,
                    'trailing_stop_percent': pos.get('trailing_stop_percent'),
                    'trailing_activation_percent': pos.get('trailing_activation_percent'),
                    'trailing_activation_price': pos.get('trailing_activation_price'),
                    'monitoring_active': symbol in position_monitor_threads
                }
            
            all_positions[symbol] = {
                'exchange_positions': positions,
                'open_orders': open_orders,
                'tracked_position': current_positions.get(symbol),
                'position_info': position_info
            }
        
        return jsonify({
            'positions': all_positions,
            'timestamp': datetime.now().isoformat()
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/config', methods=['GET', 'POST'])
def config():
    """심볼 설정 관리"""
    global SYMBOL_CONFIG
    
    if request.method == 'GET':
        # 현재 설정 반환
        return jsonify(SYMBOL_CONFIG), 200
    
    elif request.method == 'POST':
        # 설정 업데이트
        try:
            new_config = request.get_json()
            if not new_config:
                return jsonify({'error': 'No configuration data provided'}), 400
            
            # 기존 설정과 병합 (부분 업데이트 지원)
            for symbol, settings in new_config.items():
                if symbol in SYMBOL_CONFIG:
                    # 기존 심볼 업데이트
                    SYMBOL_CONFIG[symbol].update(settings)
                else:
                    # 새 심볼 추가
                    SYMBOL_CONFIG[symbol] = settings
            
            logging.info(f"설정 업데이트 완료: {list(new_config.keys())}")
            
            # 업데이트된 설정 반환
            return jsonify({
                'status': 'success',
                'updated_symbols': list(new_config.keys()),
                'config': SYMBOL_CONFIG
            }), 200
            
        except Exception as e:
            logging.error(f"설정 업데이트 실패: {str(e)}")
            return jsonify({'error': str(e)}), 500

@app.route('/test-telegram', methods=['POST'])
def test_telegram():
    """텔레그램 알림 테스트"""
    try:
        if not ENABLE_TELEGRAM:
            return jsonify({
                'status': 'disabled',
                'message': f'Telegram is disabled on port {SERVER_PORT}'
            }), 200
        
        test_message = f"""
🔔 <b>텔레그램 테스트 메시지</b>

✅ 알림이 정상적으로 작동합니다!
🌐 서버 포트: {SERVER_PORT}
📊 활성 심볼: {len([s for s, c in SYMBOL_CONFIG.items() if c.get('enabled', True)])}개
💼 현재 포지션: {len(current_positions)}개

⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
        """.strip()
        
        send_telegram_notification(test_message, 'normal')
        
        return jsonify({
            'status': 'success',
            'message': 'Test message sent',
            'telegram_enabled': ENABLE_TELEGRAM,
            'chat_ids': len(TELEGRAM_CHAT_IDS)
        }), 200
        
    except Exception as e:
        logging.error(f"텔레그램 테스트 실패: {str(e)}")
        return jsonify({
            'status': 'error',
            'error': str(e)
        }), 500

@app.route('/sync', methods=['POST'])
def sync():
    """포지션 동기화"""
    try:
        # 거래소와 포지션 동기화
        success = sync_positions_with_exchange()
        
        if success:
            # 동기화 결과 메시지
            sync_message = f"""
🔄 <b>포지션 동기화 완료</b>

📊 추적 중인 포지션: {len(current_positions)}개
{chr(10).join([f"• {symbol}: {pos['side'].upper()}" for symbol, pos in current_positions.items()])}

⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
            """.strip()
            
            if ENABLE_TELEGRAM and current_positions:
                send_telegram_notification(sync_message, 'normal')
            
            return jsonify({
                'status': 'success',
                'positions_count': len(current_positions),
                'positions': current_positions
            }), 200
        else:
            return jsonify({
                'status': 'error',
                'message': 'Synchronization failed'
            }), 500
            
    except Exception as e:
        logging.error(f"동기화 실패: {str(e)}")
        return jsonify({
            'status': 'error',
            'error': str(e)
        }), 500

@app.route('/webhook-all', methods=['POST'])
def webhook_all():
    """모든 서버에 웹훅 전파 (메인 서버용)"""
    try:
        if SERVER_PORT != 5000:
            # 메인 서버가 아니면 일반 웹훅으로 처리
            return webhook()
        
        # 메인 서버인 경우, 다른 서버들에도 전파
        data = request.get_json()
        
        # 먼저 자신이 처리
        response = webhook()
        
        # 다른 서버들에 전파
        other_ports = [5001, 5002]
        for port in other_ports:
            try:
                url = f"http://localhost:{port}/webhook"
                requests.post(url, json=data, timeout=5)
                logging.info(f"웹훅 전파 성공: 포트 {port}")
            except Exception as e:
                logging.error(f"웹훅 전파 실패 (포트 {port}): {str(e)}")
        
        return response
        
    except Exception as e:
        logging.error(f"웹훅 전파 오류: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/status', methods=['GET'])
def status():
    """봇 상태 확인 - 확장된 정보"""
    sync_positions_with_exchange()
    
    # 활성화된 심볼 목록
    enabled_symbols = [s for s, c in SYMBOL_CONFIG.items() if c.get('enabled', True)]
    
    return jsonify({
        'status': 'running',
        'server_port': SERVER_PORT,
        'current_positions': current_positions,
        'telegram_enabled': ENABLE_TELEGRAM,
        'symbols': enabled_symbols,
        'symbol_config': SYMBOL_CONFIG,  # 설정 정보도 포함
        'timestamp': datetime.now().isoformat()
    }), 200

if __name__ == '__main__':
    initialize_bot()
    app.run(host='0.0.0.0', port=SERVER_PORT, debug=True)