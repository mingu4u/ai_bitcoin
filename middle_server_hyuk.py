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
# 포트 5000: 메인 서버 (텔레그램 활성화)
# 포트 5001, 5002: 복제 서버 (텔레그램 비활성화)
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
        'leverage': 20,
        'position_size_percent': 50,
        'min_position_size': 10,
        'max_position_size': 100000,
        'enabled': True
    },
    'SAHARA/USDT': {
        'leverage': 3,
        'position_size_percent': 25,
        'min_position_size': 10,
        'max_position_size': 100000,
        'enabled': True
    },
    'ETH/USDT': {
        'leverage': 5,
        'position_size_percent': 35,
        'min_position_size': 10,
        'max_position_size': 100000,
        'enabled': True
    }
}

# 기본 설정 (환경변수로 오버라이드 가능)
DEFAULT_POSITION_SIZE_PERCENT = float(os.getenv('POSITION_SIZE_PERCENT', 10))
DEFAULT_MIN_POSITION_SIZE = float(os.getenv('MIN_POSITION_SIZE', 10))
DEFAULT_MAX_POSITION_SIZE = float(os.getenv('MAX_POSITION_SIZE', 100000))

# 포지션 추적 (다중 종목)
current_positions = {}

def get_symbol_config(symbol):
    """종목별 설정 가져오기"""
    if symbol in SYMBOL_CONFIG:
        return SYMBOL_CONFIG[symbol]
    else:
        # 기본 설정 반환
        return {
            'leverage': 10,
            'position_size_percent': DEFAULT_POSITION_SIZE_PERCENT,
            'min_position_size': DEFAULT_MIN_POSITION_SIZE,
            'max_position_size': DEFAULT_MAX_POSITION_SIZE,
            'enabled': True
        }

def send_telegram_notification(message, priority='normal'):
    """텔레그램으로 알림 전송 (비활성화 가능)"""
    # 텔레그램이 비활성화되면 로그만 출력
    if not ENABLE_TELEGRAM:
        logging.info(f"[Port {SERVER_PORT} - Telegram Disabled] {message}")
        return
    
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_IDS:
        logging.warning(f"[Port {SERVER_PORT}] 텔레그램 설정이 없습니다. .env 파일을 확인하세요.")
        return
    
    for chat_id in TELEGRAM_CHAT_IDS:
        if not chat_id.strip():
            continue
            
        try:
            url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
            
            # 우선순위에 따라 메시지 설정
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

def format_position_entry_message(symbol, action, amount, entry_price, stop_loss, take_profit, pl_ratio, position_size, balance):
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
    
    message = f"""
{direction_emoji} <b>새 포지션 진입 - {symbol}</b>

📊 <b>방향:</b> {direction_text}
💰 <b>수량:</b> {amount:.6f}
💵 <b>포지션 크기:</b> ${position_size:.2f}
🏦 <b>사용 증거금:</b> ${margin_used:.2f} ({margin_percent:.1f}%)
💵 <b>진입가:</b> ${entry_price:,.2f}
🛑 <b>손절가:</b> ${stop_loss:,.2f}
🎯 <b>익절가:</b> ${take_profit:,.2f}
📈 <b>손익비:</b> {pl_ratio}:1
⚙️ <b>레버리지:</b> {leverage}x

💸 <b>최대 손실:</b> ${risk_amount:.2f}
💰 <b>예상 수익:</b> ${reward_amount:.2f}
💳 <b>현재 잔고:</b> ${balance:,.2f}

⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
    """.strip()
    
    return message

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

def sync_positions_with_exchange():
    """거래소의 실제 포지션과 봇의 추적 정보를 동기화"""
    try:
        # 모든 활성화된 심볼에 대해 체크
        for symbol, config in SYMBOL_CONFIG.items():
            if not config.get('enabled', True):
                continue
                
            # 현재 거래소 포지션 조회
            positions = exchange.fetch_positions([symbol])
            
            for position in positions:
                if position['contracts'] > 0:
                    # 활성 포지션 발견
                    logging.info(f"활성 포지션 발견 ({symbol}): {position['side']} {position['contracts']} @ ${position.get('entryPrice', 'N/A')}")
                    
                    # current_positions에 없으면 추가
                    if symbol not in current_positions:
                        logging.info(f"수동 진입 포지션을 봇에 등록합니다: {symbol}")
                        
                        # 텔레그램 알림
                        sync_message = f"""
🔍 <b>수동 포지션 감지 - {symbol}</b>

📊 <b>방향:</b> {position['side'].upper()}
💰 <b>수량:</b> {position['contracts']}
💵 <b>진입가:</b> ${position.get('entryPrice', 'N/A')}

<i>봇에 자동 등록되었습니다.</i>
⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
                        """.strip()
                        
                        send_telegram_notification(sync_message, 'normal')
                        
                        # 열린 주문 확인하여 SL/TP 찾기
                        open_orders = exchange.fetch_open_orders(symbol)
                        sl_order_id = None
                        tp_order_id = None
                        stop_loss_price = None
                        take_profit_price = None
                        
                        for order in open_orders:
                            if order['type'] == 'stop_market' and order['reduceOnly']:
                                sl_order_id = order['id']
                                stop_loss_price = order['stopPrice']
                            elif order['type'] in ['limit', 'take_profit_market'] and order['reduceOnly']:
                                tp_order_id = order['id']
                                take_profit_price = order.get('price', order.get('stopPrice'))
                        
                        # 손익비 계산
                        pl_ratio = 3.0  # 기본값
                        entry_price = position.get('entryPrice') or position['markPrice']
                        if stop_loss_price and take_profit_price and entry_price:
                            sl_distance = abs(entry_price - stop_loss_price)
                            tp_distance = abs(take_profit_price - entry_price)
                            if sl_distance > 0:
                                pl_ratio = tp_distance / sl_distance
                        
                        # current_positions에 등록
                        current_positions[symbol] = {
                            'side': 'buy' if position['side'] == 'long' else 'sell',
                            'amount': position['contracts'],
                            'entry_price': entry_price,
                            'stop_loss': stop_loss_price or 0,
                            'take_profit': take_profit_price or 0,
                            'pl_ratio': pl_ratio,
                            'sl_order_id': sl_order_id,
                            'tp_order_id': tp_order_id,
                            'timestamp': datetime.now().isoformat(),
                            'manual_entry': True
                        }
            
            # 포지션이 없는데 current_positions에 있는 경우 정리
            if not any(p['contracts'] > 0 for p in positions) and symbol in current_positions:
                logging.info(f"포지션이 종료되었습니다: {symbol}")
                close_message = format_position_close_message(symbol, "자동 감지됨")
                send_telegram_notification(close_message, 'normal')
                del current_positions[symbol]
        
        return True
        
    except Exception as e:
        logging.error(f"포지션 동기화 실패: {str(e)}")
        return False

def initialize_bot():
    """봇 초기화 - 기존 포지션 확인"""
    logging.info(f"봇 초기화 중... (포트: {SERVER_PORT})")
    
    # 활성화된 심볼 목록
    enabled_symbols = [s for s, c in SYMBOL_CONFIG.items() if c.get('enabled', True)]
    
    # 봇 시작 알림
    start_message = f"""
🤖 <b>트레이딩 봇 시작</b>

🌐 <b>서버 포트:</b> {SERVER_PORT}
📊 <b>활성 심볼:</b> {', '.join(enabled_symbols)}
⚙️ <b>설정:</b>
"""
    
    for symbol, config in SYMBOL_CONFIG.items():
        if config.get('enabled', True):
            start_message += f"\n• {symbol}: {config['leverage']}x, {config['position_size_percent']}%"
    
    telegram_status = "활성화" if ENABLE_TELEGRAM else "비활성화"
    start_message += f"\n📱 <b>텔레그램:</b> {telegram_status}\n\n⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    
    send_telegram_notification(start_message, 'normal')
    
    sync_positions_with_exchange()
    logging.info(f"봇 초기화 완료 (포트: {SERVER_PORT}, 텔레그램: {telegram_status})")

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
    
    logging.info(f"""
    포지션 크기 계산 ({symbol}):
    - 잔고: ${balance:.2f}
    - 증거금 비율: {config['position_size_percent']}%
    - 증거금: ${margin:.2f}
    - 레버리지: {leverage}x
    - 포지션 크기: ${position_size:.2f}
    """)
    
    return position_size

def place_order_with_stops(symbol, side, amount, entry_price, stop_loss_price, take_profit_price, pl_ratio):
    """손절/익절과 함께 주문 실행"""
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
            
            # 2. 손절 주문 설정
            stop_side = 'sell' if side == 'buy' else 'buy'
            
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
            
            # 3. 익절 주문 설정
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
            
            # 4. 포지션 정보 저장
            current_positions[symbol] = {
                'side': side,
                'amount': float(adjusted_amount),
                'entry_price': actual_entry,
                'stop_loss': stop_loss_price,
                'take_profit': take_profit_price,
                'pl_ratio': pl_ratio,
                'sl_order_id': sl_order['id'] if sl_order else None,
                'tp_order_id': tp_order['id'] if tp_order else None,
                'timestamp': datetime.now().isoformat(),
                'manual_entry': False
            }
            
            logging.info(f"주문 완료 ({symbol}): Entry ${actual_entry:.2f}, SL ${stop_loss_price:.2f}, TP ${take_profit_price:.2f}")
            
            return {
                'main_order': main_order,
                'sl_order': sl_order,
                'tp_order': tp_order,
                'actual_entry': actual_entry,
                'adjusted_amount': adjusted_amount
            }
            
    except Exception as e:
        logging.error(f"주문 실행 실패 ({symbol}): {str(e)}")
        return None

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

def get_account_balance():
    """Binance 계정 잔고 조회"""
    try:
        balance = exchange.fetch_balance()
        free_usdt = balance['USDT']['free']
        return free_usdt
    except Exception as e:
        logging.error(f"잔고 조회 실패: {str(e)}")
        return None

@app.route('/webhook', methods=['POST'])
def webhook():
    """TradingView 웹훅 수신 - Stochastic/투자심리도 전략 지원"""
    try:
        # 요청 데이터 디버깅
        content_type = request.headers.get('Content-Type', '')
        content_length = request.headers.get('Content-Length', 0)
        
        logging.info(f"웹훅 요청 수신:")
        logging.info(f"- Content-Type: {content_type}")
        logging.info(f"- Content-Length: {content_length}")
        logging.info(f"- Method: {request.method}")
        
        # 원시 데이터 먼저 확인
        raw_data = request.get_data(as_text=True)
        logging.info(f"- Raw Data: '{raw_data}'")
        logging.info(f"- Raw Data Length: {len(raw_data)}")
        
        # 빈 데이터 체크
        if not raw_data or raw_data.strip() == '':
            error_msg = "Empty request body received"
            logging.error(error_msg)
            return jsonify({'error': error_msg, 'received_data': raw_data}), 400
        
        # JSON 파싱 시도
        data = None
        
        # 방법 1: Content-Type이 JSON인 경우
        if 'application/json' in content_type.lower():
            try:
                data = request.get_json()
                if data is None:
                    # get_json()이 None을 반환하는 경우
                    logging.warning("request.get_json() returned None, trying manual parse")
                    data = json.loads(raw_data)
            except Exception as e:
                logging.error(f"JSON parsing failed with get_json(): {str(e)}")
                try:
                    data = json.loads(raw_data)
                except Exception as e2:
                    logging.error(f"Manual JSON parsing also failed: {str(e2)}")
                    return jsonify({
                        'error': 'JSON parsing failed',
                        'original_error': str(e),
                        'manual_parse_error': str(e2),
                        'raw_data': raw_data,
                        'content_type': content_type
                    }), 400
        
        # 방법 2: Content-Type이 JSON이 아닌 경우
        else:
            try:
                data = json.loads(raw_data)
            except json.JSONDecodeError as e:
                # JSON이 아닌 경우 form-data나 plain text일 수 있음
                logging.error(f"Non-JSON data received: {str(e)}")
                
                # form-data 시도
                try:
                    form_data = request.form.to_dict()
                    if form_data:
                        logging.info(f"Form data received: {form_data}")
                        # form data를 JSON 형태로 변환 시도
                        if 'json' in form_data:
                            data = json.loads(form_data['json'])
                        else:
                            data = form_data
                    else:
                        return jsonify({
                            'error': 'Invalid data format',
                            'details': 'Neither JSON nor form data',
                            'raw_data': raw_data,
                            'content_type': content_type,
                            'json_error': str(e)
                        }), 400
                except Exception as form_error:
                    return jsonify({
                        'error': 'All parsing methods failed',
                        'json_error': str(e),
                        'form_error': str(form_error),
                        'raw_data': raw_data,
                        'content_type': content_type
                    }), 400
        
        # 데이터가 여전히 None인 경우
        if data is None:
            return jsonify({
                'error': 'Failed to parse request data',
                'raw_data': raw_data,
                'content_type': content_type
            }), 400
        
        # 파싱된 데이터 로깅
        logging.info(f"성공적으로 파싱된 데이터: {json.dumps(data, indent=2)}")
        
        # 심볼 확인 및 매핑
        symbol = data.get('symbol', 'BTC/USDT')
        original_symbol = symbol  # 원본 심볼 보존
        
        # 심볼 매핑 (TradingView 심볼 -> Binance 심볼)
        symbol_mapping = {
            'BTCUSDT': 'BTC/USDT',
            'BTCUSDT.P': 'BTC/USDT',
            'SAHARAUSDT': 'SAHARA/USDT',
            'SAHARAUSDT.P': 'SAHARA/USDT',  # SAHARA 영구선물 매핑
            'ETHUSDT': 'ETH/USDT',
            'ETHUSDT.P': 'ETH/USDT'
        }
        
        if symbol in symbol_mapping:
            symbol = symbol_mapping[symbol]
            logging.info(f"심볼 매핑: {original_symbol} -> {symbol}")
        
        # 심볼이 설정에 없으면 추가
        if symbol not in SYMBOL_CONFIG:
            logging.warning(f"새로운 심볼 감지: {symbol}. 기본 설정 사용")
        
        # 동기화
        sync_positions_with_exchange()
        
        logging.info(f"처리할 액션: {data.get('action')}, 심볼: {symbol}")
        
        action = data.get('action')
        
        # Stochastic/투자심리도 업데이트 Alert
        if action in ['stochastic_update', 'psychological_update']:
            if action == 'stochastic_update':
                k_value = float(data.get('k_value', 0))
                d_value = float(data.get('d_value', 0))
                pl_ratio = float(data.get('pl_ratio', 3.0))
                
                update_message = f"""
📊 <b>Stochastic 업데이트 - {symbol}</b>

📈 <b>%K:</b> {k_value:.2f}
📉 <b>%D:</b> {d_value:.2f}
🎯 <b>손익비:</b> {pl_ratio}:1

⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
                """.strip()
            else:  # psychological_update
                pl_value = float(data.get('pl_value', 0))
                pl_ratio = float(data.get('pl_ratio', 3.0))
                
                update_message = f"""
📊 <b>투자심리도 업데이트 - {symbol}</b>

📈 <b>투자심리도:</b> {pl_value:.2f}%
🎯 <b>손익비:</b> {pl_ratio}:1

⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
                """.strip()
            
            send_telegram_notification(update_message, 'normal')
            
            return jsonify({
                'status': 'success',
                'action': action,
                'symbol': symbol,
                'original_symbol': original_symbol,
                'timestamp': datetime.now().isoformat()
            }), 200
        
        # 포지션 종료
        elif action == 'close_position':
            exit_reason = data.get('exit_reason', 'signal_cross')
            
            # PnL 계산 (가능한 경우)
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
                except Exception as pnl_error:
                    logging.warning(f"PnL 계산 실패: {str(pnl_error)}")
            
            success = close_position(symbol)
            
            if success:
                close_message = format_position_close_message(symbol, exit_reason, pnl)
                send_telegram_notification(close_message, 'high')
                
                return jsonify({
                    'status': 'success',
                    'action': 'position_closed',
                    'symbol': symbol,
                    'original_symbol': original_symbol,
                    'timestamp': datetime.now().isoformat()
                }), 200
            else:
                return jsonify({
                    'status': 'error',
                    'message': 'Failed to close position'
                }), 500
        
        # 신규 포지션 진입
        elif action in ['buy', 'sell']:
            # 필수 필드 검증
            required_fields = ['entry_price', 'stop_loss']
            missing_fields = [field for field in required_fields if field not in data or data[field] is None]
            
            if missing_fields:
                error_msg = f"필수 필드 누락: {', '.join(missing_fields)}"
                logging.error(f"{error_msg}. 전체 데이터: {data}")
                return jsonify({
                    'status': 'error',
                    'message': error_msg,
                    'received_data': data
                }), 400
            
            try:
                entry_price = float(data.get('entry_price'))
                stop_loss_price = float(data.get('stop_loss'))
                pl_ratio = float(data.get('pl_ratio', 3.0))
                position_type = data.get('position_type', 'normal')
                
                # take_profit 처리 - 없으면 pl_ratio로 자동 계산
                take_profit_data = data.get('take_profit')
                
                if take_profit_data is not None and take_profit_data != 'null' and take_profit_data != '':
                    try:
                        take_profit_price = float(take_profit_data)
                        logging.info(f"Take profit 전송됨: ${take_profit_price:.2f}")
                    except (ValueError, TypeError):
                        # take_profit이 잘못된 형식인 경우 자동 계산
                        sl_distance = abs(entry_price - stop_loss_price)
                        if action == 'buy':
                            take_profit_price = entry_price + (sl_distance * pl_ratio)
                        else:  # sell
                            take_profit_price = entry_price - (sl_distance * pl_ratio)
                        logging.info(f"Take profit 형식 오류, 자동 계산: ${take_profit_price:.2f}")
                else:
                    # take_profit이 없는 경우 pl_ratio로 자동 계산
                    sl_distance = abs(entry_price - stop_loss_price)
                    if action == 'buy':
                        take_profit_price = entry_price + (sl_distance * pl_ratio)
                    else:  # sell
                        take_profit_price = entry_price - (sl_distance * pl_ratio)
                    
                    logging.info(f"Take profit 자동 계산 ({symbol}): ${take_profit_price:.2f} (PL Ratio: {pl_ratio}:1)")
                
            except (ValueError, TypeError) as e:
                error_msg = f"숫자 변환 오류: {str(e)}"
                logging.error(f"{error_msg}. 데이터: {data}")
                return jsonify({
                    'status': 'error',
                    'message': error_msg,
                    'received_data': data
                }), 400
            
            # 손절가 확인
            if not stop_loss_price or stop_loss_price == 0:
                error_msg = f"손절가가 없거나 0입니다! ({symbol})"
                logging.error(error_msg)
                return jsonify({
                    'status': 'error',
                    'message': error_msg,
                    'received_data': data
                }), 400
            
            # 기존 포지션 체크
            if symbol in current_positions:
                existing_position = current_positions[symbol]
                
                if not existing_position.get('manual_entry', False):
                    if existing_position['side'] == action:
                        logging.info(f"이미 {action.upper()} 포지션이 존재합니다: {symbol}")
                        
                        skip_message = f"""
⚠️ <b>포지션 중복 방지 - {symbol}</b>

이미 {action.upper()} 포지션이 존재합니다.
추가 진입을 스킵합니다.

⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
                        """.strip()
                        
                        send_telegram_notification(skip_message, 'normal')
                        
                        return jsonify({
                            'status': 'skipped',
                            'reason': '같은 방향 포지션 이미 존재',
                            'symbol': symbol,
                            'original_symbol': original_symbol,
                            'timestamp': datetime.now().isoformat()
                        }), 200
                    else:
                        # 반대 방향 포지션 -> 청산 후 진입
                        logging.info(f"반대 방향 포지션 전환: {symbol}")
                        close_position(symbol)
            
            # 잔고 확인
            balance = get_account_balance()
            if balance is None:
                return jsonify({'error': '잔고 조회 실패'}), 500
            
            # 포지션 크기 계산
            position_size = calculate_position_size(symbol, balance)
            if position_size is None:
                return jsonify({'error': '포지션 크기 계산 실패'}), 500
            
            # 수량 계산
            amount = position_size / entry_price
            
            logging.info(f"""
            ===== 주문 요청 ({symbol}) =====
            - Original Symbol: {original_symbol}
            - Action: {action} ({position_type})
            - Amount: {amount:.6f} (${position_size:.2f})
            - Entry: ${entry_price:.2f}
            - Stop Loss: ${stop_loss_price:.2f}
            - Take Profit: ${take_profit_price:.2f} (자동계산 여부: {take_profit_data is None})
            - P/L Ratio: {pl_ratio}:1
            =======================
            """)
            
            # 주문 실행
            orders = place_order_with_stops(
                symbol, action, amount, entry_price, 
                stop_loss_price, take_profit_price, pl_ratio
            )
            
            if orders:
                # 포지션 진입 알림
                actual_amount = float(orders.get('adjusted_amount', amount))
                entry_message = format_position_entry_message(
                    symbol, action, actual_amount, orders['actual_entry'],
                    stop_loss_price, take_profit_price,
                    pl_ratio, position_size, balance
                )
                send_telegram_notification(entry_message, 'high')
                
                return jsonify({
                    'status': 'success',
                    'action': action,
                    'symbol': symbol,
                    'original_symbol': original_symbol,
                    'position_type': position_type,
                    'amount': actual_amount,
                    'entry_price': orders['actual_entry'],
                    'stop_loss': stop_loss_price,
                    'take_profit': take_profit_price,
                    'take_profit_auto_calculated': take_profit_data is None,
                    'pl_ratio': pl_ratio,
                    'timestamp': datetime.now().isoformat()
                }), 200
            else:
                return jsonify({
                    'error': '주문 실행 실패',
                    'symbol': symbol,
                    'original_symbol': original_symbol
                }), 500
        
        else:
            return jsonify({
                'error': f'알 수 없는 액션: {action}',
                'received_data': data,
                'symbol': symbol,
                'original_symbol': original_symbol
            }), 400
            
    except Exception as e:
        logging.error(f"웹훅 처리 오류: {str(e)}")
        
        # 에러 정보 수집
        error_details = {
            'error': str(e),
            'error_type': type(e).__name__,
            'content_type': request.headers.get('Content-Type', 'N/A'),
            'content_length': request.headers.get('Content-Length', 'N/A'),
            'raw_data': request.get_data(as_text=True) if hasattr(request, 'get_data') else 'N/A',
            'form_data': dict(request.form) if hasattr(request, 'form') else 'N/A',
            'timestamp': datetime.now().isoformat()
        }
        
        # data 변수가 정의되어 있으면 포함
        if 'data' in locals() and data is not None:
            error_details['parsed_data'] = data
        
        error_message = f"""
❌ <b>웹훅 처리 오류</b>

<b>오류:</b> {str(e)}
<b>오류 타입:</b> {type(e).__name__}
<b>Content-Type:</b> {request.headers.get('Content-Type', 'N/A')}
<b>Raw 데이터:</b> {request.get_data(as_text=True)[:200]}...

⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
        """.strip()
        
        send_telegram_notification(error_message, 'error')
        return jsonify(error_details), 500

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
            
            # 현재가 조회
            ticker = exchange.fetch_ticker(symbol)
            current_price = ticker['last']
            
            # PnL 계산
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
                    'current_price': current_price
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

@app.route('/status', methods=['GET'])
def status():
    """봇 상태 확인"""
    sync_positions_with_exchange()
    
    return jsonify({
        'status': 'running',
        'server_port': SERVER_PORT,
        'symbols': list(SYMBOL_CONFIG.keys()),
        'symbol_config': SYMBOL_CONFIG,
        'current_positions': current_positions,
        'telegram_enabled': ENABLE_TELEGRAM,
        'telegram_configured': bool(TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_IDS),
        'timestamp': datetime.now().isoformat()
    }), 200

@app.route('/config', methods=['GET', 'POST'])
def config():
    """심볼 설정 조회/수정"""
    global SYMBOL_CONFIG
    
    if request.method == 'GET':
        return jsonify(SYMBOL_CONFIG), 200
    
    elif request.method == 'POST':
        data = request.get_json()
        
        # 설정 업데이트
        for symbol, config in data.items():
            if symbol in SYMBOL_CONFIG:
                SYMBOL_CONFIG[symbol].update(config)
            else:
                SYMBOL_CONFIG[symbol] = config
        
        # 알림 전송
        config_message = f"""
⚙️ <b>설정 변경</b>

{json.dumps(SYMBOL_CONFIG, indent=2)}

⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
        """.strip()
        
        send_telegram_notification(config_message, 'normal')
        
        return jsonify({
            'status': 'success',
            'config': SYMBOL_CONFIG,
            'timestamp': datetime.now().isoformat()
        }), 200

@app.route('/sync', methods=['POST'])
def sync():
    """수동 동기화"""
    try:
        success = sync_positions_with_exchange()
        
        if success:
            return jsonify({
                'status': 'success',
                'message': '포지션 동기화 완료',
                'current_positions': current_positions,
                'timestamp': datetime.now().isoformat()
            }), 200
        else:
            return jsonify({
                'status': 'error',
                'message': '동기화 실패'
            }), 500
            
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@app.route('/test-telegram', methods=['POST'])
def test_telegram():
    """텔레그램 알림 테스트"""
    try:
        if not ENABLE_TELEGRAM:
            return jsonify({
                'status': 'disabled',
                'message': '텔레그램이 비활성화되어 있습니다',
                'timestamp': datetime.now().isoformat()
            }), 200
        
        test_message = f"""
🧪 <b>텔레그램 알림 테스트</b>

✅ 설정이 정상적으로 작동합니다!
🤖 Multi-Symbol 봇이 준비되었습니다.

활성 심볼: {', '.join([s for s, c in SYMBOL_CONFIG.items() if c.get('enabled', True)])}

⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
        """.strip()
        
        send_telegram_notification(test_message, 'normal')
        
        return jsonify({
            'status': 'success',
            'message': '텔레그램 알림 테스트 완료',
            'timestamp': datetime.now().isoformat()
        }), 200
        
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

if __name__ == '__main__':
    # 서버 시작 시 초기화
    initialize_bot()
    
    # Flask 앱 실행 (포트는 상단 SERVER_PORT에서 설정)
    logging.info(f"서버 시작: 포트 {SERVER_PORT}, 텔레그램 {'활성화' if ENABLE_TELEGRAM else '비활성화'}")
    app.run(host='0.0.0.0', port=SERVER_PORT, debug=True)