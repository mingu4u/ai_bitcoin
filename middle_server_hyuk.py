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
SERVER_PORT = 5001  # 여기서 포트 변경 (5000, 5001, 5002)
ENABLE_TELEGRAM = True if SERVER_PORT == 5000 else False  # 5000번 포트만 텔레그램 활성화

app = Flask(__name__)
logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s - [Port:{port}] - %(levelname)s - %(message)s'.format(port=SERVER_PORT))

# Binance 설정
exchange = ccxt.binance({
    'apiKey': os.getenv('BINANCE_API_KEY_HYUK'),
    'secret': os.getenv('BINANCE_SECRET_KEY_HYUK'),
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
    }
}


# 기본 설정
DEFAULT_POSITION_SIZE_PERCENT = float(os.getenv('POSITION_SIZE_PERCENT', 10))
DEFAULT_MIN_POSITION_SIZE = float(os.getenv('MIN_POSITION_SIZE', 10))
DEFAULT_MAX_POSITION_SIZE = float(os.getenv('MAX_POSITION_SIZE', 100000))

# 포지션 추적
current_positions = {}

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

def format_position_entry_message(symbol, action, amount, entry_price, stop_loss, take_profit, pl_ratio, position_size, balance, trailing_stop_percent=None):
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
        trailing_text = f"\n📊 <b>트레일링 스탑:</b> {trailing_stop_percent}%"
    
    message = f"""
{direction_emoji} <b>새 포지션 진입 - {symbol}</b>

📊 <b>방향:</b> {direction_text}
💰 <b>수량:</b> {amount:.6f}
💵 <b>포지션 크기:</b> ${position_size:.2f}
🏦 <b>사용 증거금:</b> ${margin_used:.2f} ({margin_percent:.1f}%)
💵 <b>진입가:</b> ${entry_price:,.2f}
🛑 <b>손절가:</b> ${stop_loss:,.2f}
🎯 <b>익절가:</b> ${take_profit:,.2f}{trailing_text}
📈 <b>손익비:</b> {pl_ratio}:1
⚙️ <b>레버리지:</b> {leverage}x

💸 <b>최대 손실:</b> ${risk_amount:.2f}
💰 <b>예상 수익:</b> ${reward_amount:.2f}
💳 <b>현재 잔고:</b> ${balance:,.2f}

⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
    """.strip()
    
    return message

def place_order_with_stops(symbol, side, amount, entry_price, stop_loss_price, take_profit_price, pl_ratio, trailing_stop_percent=None):
    """트레일링 스탑과 백업 손절을 포함한 주문 실행"""
    try:
        config = get_symbol_config(symbol)
        
        # 심볼 정보 가져오기
        markets = exchange.load_markets()
        market = markets[symbol]
        
        # 수량 정밀도 적용
        amount_precision = market['precision']['amount']
        min_amount = market['limits']['amount']['min']
        
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
            
            # 2. 주문 옵션 설정
            stop_side = 'sell' if side == 'buy' else 'buy'
            orders_placed = {'main': main_order}
            
            # 3. 백업 손절 주문 (항상 설정)
            logging.info(f"백업 손절 설정: ${stop_loss_price:.2f}")
            try:
                sl_order = exchange.create_order(
                    symbol=symbol,
                    type='stop_market',
                    side=stop_side,
                    amount=adjusted_amount,
                    params={
                        'stopPrice': stop_loss_price,
                        'workingType': 'MARK_PRICE',
                        'reduceOnly': True
                    }
                )
                orders_placed['stop_loss'] = sl_order
                logging.info(f"백업 손절 설정 완료: ${stop_loss_price:.2f}")
            except Exception as sl_error:
                logging.error(f"백업 손절 설정 실패: {str(sl_error)}")
                # 손절 실패시에도 계속 진행 (익절은 설정)
            
            # 4. 트레일링 스탑 설정 (있는 경우)
            trailing_order_success = False
            if trailing_stop_percent and trailing_stop_percent > 0:
                try:
                    logging.info(f"트레일링 스탑 설정 시도: {trailing_stop_percent}%")
                    
                    # 트레일링 스탑 파라미터
                    trailing_params = {
                        'reduceOnly': True,
                        'workingType': 'MARK_PRICE',
                        'activationPrice': actual_entry,  # 활성화 가격
                        'callbackRate': trailing_stop_percent,  # 콜백 비율 (%)
                    }
                    
                    trailing_order = exchange.create_order(
                        symbol=symbol,
                        type='trailing_stop_market',
                        side=stop_side,
                        amount=adjusted_amount,
                        params=trailing_params
                    )
                    
                    orders_placed['trailing_stop'] = trailing_order
                    trailing_order_success = True
                    logging.info(f"트레일링 스탑 설정 성공: {trailing_stop_percent}%")
                    
                    # 트레일링 스탑이 성공하면 백업 손절을 더 낮은 위치로 조정 (선택적)
                    # 이렇게 하면 트레일링 스탑과 백업 손절이 충돌하지 않음
                    try:
                        if 'stop_loss' in orders_placed and orders_placed['stop_loss']:
                            # 기존 백업 손절 취소
                            exchange.cancel_order(orders_placed['stop_loss']['id'], symbol)
                            
                            # 더 낮은 백업 손절 재설정 (원래 손절의 1.5배 거리)
                            if side == 'buy':
                                emergency_stop = actual_entry - (actual_entry - stop_loss_price) * 1.5
                            else:
                                emergency_stop = actual_entry + (stop_loss_price - actual_entry) * 1.5
                            
                            emergency_sl_order = exchange.create_order(
                                symbol=symbol,
                                type='stop_market',
                                side=stop_side,
                                amount=adjusted_amount,
                                params={
                                    'stopPrice': emergency_stop,
                                    'workingType': 'MARK_PRICE',
                                    'reduceOnly': True
                                }
                            )
                            orders_placed['emergency_stop'] = emergency_sl_order
                            logging.info(f"비상 손절 재설정: ${emergency_stop:.2f}")
                    except:
                        pass  # 백업 손절 조정 실패시 원래 손절 유지
                    
                except Exception as ts_error:
                    trailing_order_success = False
                    logging.warning(f"트레일링 스탑 설정 실패, 백업 손절 유지: {str(ts_error)}")
                    
                    # 트레일링 스탑 실패시 수동 트레일링 스레드 시작
                    thread = threading.Thread(
                        target=monitor_trailing_stop,
                        args=(symbol, side, adjusted_amount, actual_entry, trailing_stop_percent, stop_loss_price)
                    )
                    thread.daemon = True
                    thread.start()
                    logging.info("수동 트레일링 스탑 모니터링 시작")
            
            # 5. 익절 주문 설정
            try:
                tp_order = exchange.create_order(
                    symbol=symbol,
                    type='take_profit_market',
                    side=stop_side,
                    amount=adjusted_amount,
                    params={
                        'stopPrice': take_profit_price,
                        'workingType': 'MARK_PRICE',
                        'reduceOnly': True
                    }
                )
                orders_placed['take_profit'] = tp_order
                logging.info(f"익절 설정 완료: ${take_profit_price:.2f}")
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
                'trailing_stop_active': trailing_order_success,
                'pl_ratio': pl_ratio,
                'sl_order_id': orders_placed.get('stop_loss', {}).get('id'),
                'emergency_sl_order_id': orders_placed.get('emergency_stop', {}).get('id'),
                'tp_order_id': orders_placed.get('take_profit', {}).get('id'),
                'trailing_order_id': orders_placed.get('trailing_stop', {}).get('id'),
                'timestamp': datetime.now().isoformat(),
                'manual_entry': False
            }
            
            logging.info(f"""
            ✅ 주문 완료 ({symbol}):
            - Entry: ${actual_entry:.2f}
            - Stop Loss: ${stop_loss_price:.2f} (백업)
            - Take Profit: ${take_profit_price:.2f}
            - Trailing Stop: {trailing_stop_percent}% ({'활성' if trailing_order_success else '수동모드'})
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

def monitor_trailing_stop(symbol, side, amount, entry_price, trailing_stop_percent, initial_stop_loss):
    """수동 트레일링 스탑 모니터링 (백그라운드)"""
    try:
        logging.info(f"수동 트레일링 스탑 모니터링 시작 ({symbol}): {trailing_stop_percent}%")
        
        highest_price = entry_price if side == 'buy' else 0
        lowest_price = entry_price if side == 'sell' else float('inf')
        current_stop = initial_stop_loss
        
        while symbol in current_positions:
            time.sleep(10)  # 10초마다 체크
            
            try:
                ticker = exchange.fetch_ticker(symbol)
                current_price = ticker['last']
                
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
    """특정 심볼의 포지션 종료"""
    try:
        positions = exchange.fetch_positions([symbol])
        
        for position in positions:
            if position['contracts'] > 0:
                # 포지션 청산
                side = 'sell' if position['side'] == 'long' else 'buy'
                amount = abs(position['contracts'])
                
                exchange.create_order(
                    symbol=symbol,
                    type='market',
                    side=side,
                    amount=amount,
                    params={'reduceOnly': True}
                )
        
        # 열린 주문 모두 취소
        open_orders = exchange.fetch_open_orders(symbol)
        for order in open_orders:
            exchange.cancel_order(order['id'], symbol)
        
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
            
            # 포지션이 없는데 current_positions에 있는 경우 정리
            if not any(p['contracts'] > 0 for p in positions) and symbol in current_positions:
                logging.info(f"포지션이 종료되었습니다: {symbol}")
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
🔄 <b>트레일링 스탑:</b> 활성화
📱 <b>텔레그램:</b> {'활성화' if ENABLE_TELEGRAM else '비활성화'}

⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
    """.strip()
    
    send_telegram_notification(start_message, 'normal')
    sync_positions_with_exchange()
    logging.info(f"봇 초기화 완료")

@app.route('/webhook', methods=['POST'])
def webhook():
    """TradingView 웹훅 수신 - 트레일링 스탑 지원"""
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
            'ETHFIUSDT.P': 'ETHFI/USDT'    
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
                    logging.info(f"트레일링 스탑 활성화: {trailing_stop_percent}%")
                except:
                    trailing_stop_percent = None
                    logging.warning("트레일링 스탑 값 파싱 실패, 일반 손절 사용")
            
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
            - P/L Ratio: {pl_ratio}:1
            =======================
            """)
            
            # 주문 실행 (트레일링 스탑 포함)
            orders = place_order_with_stops(
                symbol, action, amount, entry_price, 
                stop_loss_price, take_profit_price, pl_ratio,
                trailing_stop_percent  # 트레일링 스탑 추가
            )
            
            if orders:
                actual_amount = float(orders.get('adjusted_amount', amount))
                entry_message = format_position_entry_message(
                    symbol, action, actual_amount, orders['actual_entry'],
                    stop_loss_price, take_profit_price,
                    pl_ratio, position_size, balance, trailing_stop_percent
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

@app.route('/status', methods=['GET'])
def status():
    """봇 상태 확인"""
    sync_positions_with_exchange()
    
    return jsonify({
        'status': 'running',
        'server_port': SERVER_PORT,
        'current_positions': current_positions,
        'telegram_enabled': ENABLE_TELEGRAM,
        'timestamp': datetime.now().isoformat()
    }), 200

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
                    'trailing_stop_percent': pos.get('trailing_stop_percent')
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

if __name__ == '__main__':
    initialize_bot()
    app.run(host='0.0.0.0', port=SERVER_PORT, debug=True)