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

app = Flask(__name__)
logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s - %(levelname)s - %(message)s')

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

# 거래 설정
POSITION_SIZE_PERCENT = 90#float(os.getenv('POSITION_SIZE_PERCENT', 10))
MIN_POSITION_SIZE = 10#float(os.getenv('MIN_POSITION_SIZE', 10))
MAX_POSITION_SIZE = 100000000000000#float(os.getenv('MAX_POSITION_SIZE', 1000))
SYMBOL = 'BTC/USDT'

# 포지션 추적
current_positions = {}

def send_telegram_notification(message, priority='normal'):
    """텔레그램으로 알림 전송"""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_IDS:
        logging.warning("텔레그램 설정이 없습니다. .env 파일을 확인하세요.")
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

def format_position_entry_message(action, amount, entry_price, stop_loss, take_profit, pl_ratio, position_size, balance):
    """포지션 진입 메시지 포맷"""
    direction_emoji = "🚀" if action == "buy" else "📉"
    direction_text = "LONG" if action == "buy" else "SHORT"
    
    # 리스크/리워드 계산
    risk_amount = abs(entry_price - stop_loss) * amount
    reward_amount = abs(take_profit - entry_price) * amount
    
    message = f"""
{direction_emoji} <b>새 포지션 진입</b>

📊 <b>방향:</b> {direction_text}
💰 <b>수량:</b> {amount:.6f} BTC (${position_size:.2f})
💵 <b>진입가:</b> ${entry_price:,.2f}
🛑 <b>손절가:</b> ${stop_loss:,.2f}
🎯 <b>익절가:</b> ${take_profit:,.2f}
📈 <b>손익비:</b> {pl_ratio}:1

💸 <b>최대 손실:</b> ${risk_amount:.2f}
💰 <b>예상 수익:</b> ${reward_amount:.2f}
💳 <b>현재 잔고:</b> ${balance:,.2f}

⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
    """.strip()
    
    return message

def format_trail_update_message(new_sl, new_tp, pl_ratio, current_price=None):
    """트레일링 스톱 업데이트 메시지 포맷"""
    message = f"""
🔄 <b>트레일링 스톱 업데이트</b>

🛑 <b>새 손절가:</b> ${new_sl:,.2f}
🎯 <b>새 익절가:</b> ${new_tp:,.2f}
📈 <b>손익비:</b> {pl_ratio}:1 (유지)
    """
    
    if current_price:
        message += f"\n📊 <b>현재가:</b> ${current_price:,.2f}"
    
    message += f"\n\n⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    
    return message.strip()

def format_position_close_message(reason="수동 종료"):
    """포지션 종료 메시지 포맷"""
    message = f"""
❌ <b>포지션 종료</b>

📋 <b>종료 사유:</b> {reason}
⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
    """.strip()
    
    return message

def format_error_message(error_type, error_msg):
    """오류 메시지 포맷"""
    message = f"""
⚠️ <b>시스템 오류</b>

🔍 <b>오류 유형:</b> {error_type}
📝 <b>오류 내용:</b> {error_msg}
⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

<i>관리자에게 문의하세요.</i>
    """.strip()
    
    return message

def sync_positions_with_exchange():
    """거래소의 실제 포지션과 봇의 추적 정보를 동기화"""
    try:
        # 현재 거래소 포지션 조회
        positions = exchange.fetch_positions([SYMBOL])
        
        for position in positions:
            if position['contracts'] > 0:
                # 활성 포지션 발견
                logging.info(f"활성 포지션 발견: {position['side']} {position['contracts']} BTC @ ${position.get('entryPrice', 'N/A')}")
                
                # current_positions에 없으면 추가
                if SYMBOL not in current_positions:
                    logging.info("수동 진입 포지션을 봇에 등록합니다.")
                    
                    # 텔레그램 알림: 수동 포지션 감지
                    sync_message = f"""
🔍 <b>수동 포지션 감지</b>

📊 <b>방향:</b> {position['side'].upper()}
💰 <b>수량:</b> {position['contracts']} BTC
💵 <b>진입가:</b> ${position.get('entryPrice', 'N/A')}

<i>봇에 자동 등록되었습니다.</i>
⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
                    """.strip()
                    
                    send_telegram_notification(sync_message, 'normal')
                    
                    # 열린 주문 확인하여 SL/TP 찾기
                    open_orders = exchange.fetch_open_orders(SYMBOL)
                    sl_order_id = None
                    tp_order_id = None
                    stop_loss_price = None
                    take_profit_price = None
                    
                    for order in open_orders:
                        if order['type'] == 'stop_market' and order['reduceOnly']:
                            sl_order_id = order['id']
                            stop_loss_price = order['stopPrice']
                            logging.info(f"손절 주문 발견: ${stop_loss_price}")
                        elif order['type'] in ['limit', 'take_profit_market'] and order['reduceOnly']:
                            tp_order_id = order['id']
                            take_profit_price = order.get('price', order.get('stopPrice'))
                            logging.info(f"익절 주문 발견: ${take_profit_price}")
                    
                    # 손익비 계산 (SL/TP가 있는 경우)
                    pl_ratio = 3.0  # 기본값
                    entry_price = position.get('entryPrice') or position['markPrice']
                    if stop_loss_price and take_profit_price and entry_price:
                        sl_distance = abs(entry_price - stop_loss_price)
                        tp_distance = abs(take_profit_price - entry_price)
                        if sl_distance > 0:
                            pl_ratio = tp_distance / sl_distance
                    
                    # current_positions에 등록
                    current_positions[SYMBOL] = {
                        'side': 'buy' if position['side'] == 'long' else 'sell',
                        'amount': position['contracts'],
                        'entry_price': entry_price,
                        'stop_loss': stop_loss_price or 0,
                        'take_profit': take_profit_price or 0,
                        'pl_ratio': pl_ratio,
                        'sl_order_id': sl_order_id,
                        'tp_order_id': tp_order_id,
                        'timestamp': datetime.now().isoformat(),
                        'manual_entry': True  # 수동 진입 표시
                    }
                    
                    logging.info(f"포지션 등록 완료: {current_positions[SYMBOL]}")
                    return True
                    
        # 포지션이 없는데 current_positions에 있는 경우 정리
        if not any(p['contracts'] > 0 for p in positions) and SYMBOL in current_positions:
            logging.info("포지션이 종료되었습니다. 추적 정보를 제거합니다.")
            
            # 포지션 종료 알림
            close_message = format_position_close_message("자동 감지됨")
            send_telegram_notification(close_message, 'normal')
            
            del current_positions[SYMBOL]
            
        return True
        
    except Exception as e:
        logging.error(f"포지션 동기화 실패: {str(e)}")
        
        # 오류 알림
        error_message = format_error_message("포지션 동기화", str(e))
        send_telegram_notification(error_message, 'error')
        
        return False

def initialize_bot():
    """봇 초기화 - 기존 포지션 확인"""
    logging.info("봇 초기화 중...")
    
    # 봇 시작 알림
    start_message = f"""
🤖 <b>트레이딩 봇 시작</b>

📊 <b>심볼:</b> {SYMBOL}
⚙️ <b>포지션 크기:</b> {POSITION_SIZE_PERCENT}%
📱 <b>알림:</b> 활성화

⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
    """.strip()
    
    send_telegram_notification(start_message, 'normal')
    
    sync_positions_with_exchange()
    logging.info("봇 초기화 완료")

def calculate_tp_from_pl_ratio(entry_price, stop_loss_price, pl_ratio, side):
    """
    손익비를 기반으로 TP 계산
    
    Args:
        entry_price: 진입가
        stop_loss_price: 손절가 (BlackFlag trail)
        pl_ratio: 손익비 (예: 3.0은 3:1)
        side: 'buy' 또는 'sell'
    
    Returns:
        take_profit_price: 계산된 익절가
    """
    # 손절 거리 계산
    sl_distance = abs(entry_price - stop_loss_price)
    
    # 익절 거리 = 손절 거리 × 손익비
    tp_distance = sl_distance * pl_ratio
    
    # 포지션 방향에 따라 TP 계산
    if side == 'buy':
        take_profit_price = entry_price + tp_distance
    else:  # sell
        take_profit_price = entry_price - tp_distance
    
    logging.info(f"""
    TP 계산:
    - Entry: ${entry_price:.2f}
    - SL: ${stop_loss_price:.2f}
    - SL Distance: ${sl_distance:.2f}
    - P/L Ratio: {pl_ratio}:1
    - TP Distance: ${tp_distance:.2f}
    - TP: ${take_profit_price:.2f}
    """)
    
    return take_profit_price

def place_order_with_calculated_stops(side, amount, entry_price, stop_loss_price, pl_ratio):
    """손익비 기반으로 계산된 TP와 함께 주문 실행"""
    try:
        # 손익비 기반 TP 계산
        take_profit_price = calculate_tp_from_pl_ratio(
            entry_price, stop_loss_price, pl_ratio, side
        )
        
        # 레버리지 설정
        exchange.set_leverage(10, SYMBOL)
        
        # 1. 메인 주문 실행
        logging.info(f"메인 주문 실행: {side} {amount} BTC @ market")
        main_order = exchange.create_order(
            symbol=SYMBOL,
            type='market',
            side=side,
            amount=amount
        )
        
        if main_order:
            order_id = main_order['id']
            actual_entry = main_order.get('average', main_order.get('price', entry_price))
            
            logging.info(f"메인 주문 체결: Entry @ ${actual_entry:.2f}")
            
            # 실제 체결가로 TP 재계산
            if abs(actual_entry - entry_price) > entry_price * 0.001:  # 0.1% 이상 차이
                logging.info(f"체결가 차이 감지. TP 재계산: {entry_price} -> {actual_entry}")
                take_profit_price = calculate_tp_from_pl_ratio(
                    actual_entry, stop_loss_price, pl_ratio, side
                )
            
            # 2. 손절 주문 설정
            stop_side = 'sell' if side == 'buy' else 'buy'
            
            logging.info(f"손절 주문 설정: {stop_side} {amount} BTC @ stop ${stop_loss_price:.2f}")
            
            # Binance Futures의 경우 Stop Market 주문 사용
            sl_order = exchange.create_order(
                symbol=SYMBOL,
                type='stop_market',  # 'stop' 대신 'stop_market' 사용
                side=stop_side,
                amount=amount,
                stopPrice=stop_loss_price,
                params={
                    'stopPrice': stop_loss_price,
                    'workingType': 'MARK_PRICE',  # Mark Price 기준
                    'reduceOnly': True,
                    'postOnly': False
                }
            )
            
            logging.info(f"손절 주문 생성 완료: Order ID = {sl_order['id'] if sl_order else 'None'}")
            
            # 3. 익절 주문 설정
            logging.info(f"익절 주문 설정: {stop_side} {amount} BTC @ limit ${take_profit_price:.2f}")
            
            tp_order = exchange.create_order(
                symbol=SYMBOL,
                type='take_profit_market',  # 'limit' 대신 'take_profit_market' 사용
                side=stop_side,
                amount=amount,
                stopPrice=take_profit_price,
                params={
                    'stopPrice': take_profit_price,
                    'workingType': 'MARK_PRICE',
                    'reduceOnly': True,
                    'postOnly': False
                }
            )
            
            logging.info(f"익절 주문 생성 완료: Order ID = {tp_order['id'] if tp_order else 'None'}")
            
            # 4. 포지션 정보 저장
            current_positions[SYMBOL] = {
                'side': side,
                'amount': amount,
                'entry_price': actual_entry,
                'stop_loss': stop_loss_price,
                'take_profit': take_profit_price,
                'pl_ratio': pl_ratio,
                'sl_order_id': sl_order['id'] if sl_order else None,
                'tp_order_id': tp_order['id'] if tp_order else None,
                'timestamp': datetime.now().isoformat()
            }
            
            # 5. 주문 확인
            logging.info("=== 주문 완료 요약 ===")
            logging.info(f"포지션: {side.upper()}")
            logging.info(f"수량: {amount} BTC")
            logging.info(f"진입가: ${actual_entry:.2f}")
            logging.info(f"손절가: ${stop_loss_price:.2f} (리스크: ${abs(actual_entry - stop_loss_price):.2f})")
            logging.info(f"익절가: ${take_profit_price:.2f} (수익: ${abs(take_profit_price - actual_entry):.2f})")
            logging.info(f"손익비: {pl_ratio}:1")
            logging.info("====================")
            
            return {
                'main_order': main_order,
                'sl_order': sl_order,
                'tp_order': tp_order,
                'calculated_tp': take_profit_price,
                'actual_entry': actual_entry
            }
            
    except Exception as e:
        logging.error(f"주문 실행 실패: {str(e)}")
        logging.error(f"상세 오류: {type(e).__name__}")
        
        # 주문 실패 알림
        error_message = format_error_message("주문 실행", str(e))
        send_telegram_notification(error_message, 'error')
        
        # Binance 오류 메시지 상세 출력
        if hasattr(e, 'response'):
            logging.error(f"Binance 응답: {e.response}")
            
        return None

def check_open_orders():
    """현재 열린 주문 확인"""
    try:
        open_orders = exchange.fetch_open_orders(SYMBOL)
        
        if open_orders:
            logging.info(f"=== 열린 주문 {len(open_orders)}개 ===")
            for order in open_orders:
                logging.info(f"- {order['type']} {order['side']} @ ${order.get('stopPrice', order.get('price'))}")
        else:
            logging.info("열린 주문 없음")
            
        return open_orders
    except Exception as e:
        logging.error(f"주문 조회 실패: {str(e)}")
        return []

def check_position_status():
    """현재 포지션과 주문 상태 확인"""
    try:
        # 먼저 동기화 실행
        sync_positions_with_exchange()
        
        # 포지션 확인
        positions = exchange.fetch_positions([SYMBOL])
        active_position = None
        
        for pos in positions:
            if pos['contracts'] > 0:
                active_position = pos
                break
        
        if active_position:
            logging.info(f"=== 활성 포지션 ===")
            logging.info(f"방향: {active_position['side']}")
            logging.info(f"수량: {active_position['contracts']}")
            logging.info(f"진입가: ${active_position.get('entryPrice', 'N/A')}")
            logging.info(f"현재가: ${active_position['markPrice']}")
            logging.info(f"미실현 손익: ${active_position.get('unrealizedPnl', 0)}")
            
            # current_positions 정보도 출력
            if SYMBOL in current_positions:
                logging.info(f"봇 추적 정보: {current_positions[SYMBOL]}")
        
        # 열린 주문 확인
        check_open_orders()
        
        return active_position
    except Exception as e:
        logging.error(f"포지션 상태 확인 실패: {str(e)}")
        return None

def update_trailing_stop_with_pl_ratio(new_stop_loss_price, pl_ratio):
    """트레일링 스톱 업데이트 시 손익비 유지하며 TP도 재계산"""
    try:
        if SYMBOL not in current_positions:
            return None
            
        position = current_positions[SYMBOL]
        
        # 손절가가 유리한 방향으로만 이동
        if position['side'] == 'buy':
            if new_stop_loss_price <= position['stop_loss']:
                logging.info("롱 포지션: 새 손절가가 기존보다 낮음. 업데이트 생략")
                return None
        else:  # sell
            if new_stop_loss_price >= position['stop_loss']:
                logging.info("숏 포지션: 새 손절가가 기존보다 높음. 업데이트 생략")
                return None
        
        # 새로운 TP 계산 (손익비 유지)
        new_take_profit = calculate_tp_from_pl_ratio(
            position['entry_price'], 
            new_stop_loss_price, 
            pl_ratio,
            position['side']
        )
        
        # 기존 주문 취소
        if position.get('sl_order_id'):
            try:
                exchange.cancel_order(position['sl_order_id'], SYMBOL)
            except:
                pass
                
        if position.get('tp_order_id'):
            try:
                exchange.cancel_order(position['tp_order_id'], SYMBOL)
            except:
                pass
        
        # 새로운 손절/익절 주문 생성
        stop_side = 'sell' if position['side'] == 'buy' else 'buy'
        
        # 새 손절 주문
        new_sl_order = exchange.create_order(
            symbol=SYMBOL,
            type='stop_market',
            side=stop_side,
            amount=position['amount'],
            stopPrice=new_stop_loss_price,
            params={'reduceOnly': True}
        )
        
        # 새 익절 주문
        new_tp_order = exchange.create_order(
            symbol=SYMBOL,
            type='take_profit_market',
            side=stop_side,
            amount=position['amount'],
            stopPrice=new_take_profit,
            params={
                'reduceOnly': True,
                'postOnly': False
            }
        )
        
        # 포지션 정보 업데이트
        position['stop_loss'] = new_stop_loss_price
        position['take_profit'] = new_take_profit
        position['sl_order_id'] = new_sl_order['id'] if new_sl_order else None
        position['tp_order_id'] = new_tp_order['id'] if new_tp_order else None
        position['last_update'] = datetime.now().isoformat()
        
        logging.info(f"""
        트레일링 스톱 업데이트 완료:
        - 새 SL: ${new_stop_loss_price:.2f}
        - 새 TP: ${new_take_profit:.2f}
        - P/L Ratio: {pl_ratio}:1 (유지됨)
        """)
        
        return {
            'sl_order': new_sl_order,
            'tp_order': new_tp_order,
            'new_sl': new_stop_loss_price,
            'new_tp': new_take_profit
        }
        
    except Exception as e:
        logging.error(f"트레일링 스톱 업데이트 실패: {str(e)}")
        
        # 트레일링 스톱 업데이트 실패 알림
        error_message = format_error_message("트레일링 스톱 업데이트", str(e))
        send_telegram_notification(error_message, 'error')
        
        return None

@app.route('/webhook', methods=['POST'])
def webhook():
    """TradingView 웹훅 수신"""
    try:
        # 웹훅 처리 전 동기화
        sync_positions_with_exchange()
        
        # 웹훅 데이터 파싱
        data = request.get_json()
        logging.info(f"웹훅 수신: {json.dumps(data, indent=2)}")
        
        # JSON 문자열인 경우 파싱
        if isinstance(data, str):
            data = json.loads(data)
        
        action = data.get('action')
        
        # 트레일링 스톱 업데이트
        if action == 'update_trail':
            new_stop_loss = float(data.get('new_stop_loss'))
            pl_ratio = float(data.get('pl_ratio', 3.0))  # 기본값 3:1
            
            result = update_trailing_stop_with_pl_ratio(new_stop_loss, pl_ratio)
            
            if result:
                # 트레일링 스톱 업데이트 알림
                current_price = None
                try:
                    ticker = exchange.fetch_ticker(SYMBOL)
                    current_price = ticker['last']
                except:
                    pass
                
                trail_message = format_trail_update_message(
                    result['new_sl'], result['new_tp'], pl_ratio, current_price
                )
                send_telegram_notification(trail_message, 'normal')
                
                return jsonify({
                    'status': 'success',
                    'action': 'trail_updated',
                    'new_stop_loss': result['new_sl'],
                    'new_take_profit': result['new_tp'],
                    'pl_ratio': pl_ratio,
                    'timestamp': datetime.now().isoformat()
                }), 200
            else:
                return jsonify({
                    'status': 'skipped',
                    'reason': '손절가가 불리한 방향',
                    'timestamp': datetime.now().isoformat()
                }), 200
        
        # 포지션 종료
        elif action == 'close_position':
            close_all_positions()
            
            # 포지션 종료 알림
            close_message = format_position_close_message("TradingView 신호")
            send_telegram_notification(close_message, 'high')
            
            return jsonify({
                'status': 'success',
                'action': 'position_closed',
                'timestamp': datetime.now().isoformat()
            }), 200
        
        # 신규 포지션
        elif action in ['buy', 'sell']:
            entry_price = float(data.get('entry_price'))
            stop_loss_price = float(data.get('stop_loss'))
            pl_ratio = float(data.get('pl_ratio', 3.0))  # 기본값 3:1
            position_type = data.get('position_type', 'normal')
            
            # 중요: stop_loss 확인
            if not stop_loss_price or stop_loss_price == 0:
                error_msg = "손절가가 없습니다! TradingView 설정을 확인하세요."
                logging.error(f"❌ {error_msg}")
                
                # 오류 알림
                error_message = format_error_message("손절가 누락", error_msg)
                send_telegram_notification(error_message, 'error')
                
                return jsonify({
                    'status': 'error',
                    'message': error_msg
                }), 400
            
            # 잔고 확인
            balance = get_account_balance()
            if balance is None:
                error_msg = "잔고 조회 실패"
                error_message = format_error_message("잔고 조회", error_msg)
                send_telegram_notification(error_message, 'error')
                return jsonify({'error': error_msg}), 500
            
            logging.info(f"현재 USDT 잔고: ${balance:.2f}")
            
            # 리스크 체크
            if not check_risk_before_entry(balance):
                risk_msg = "리스크 한도 초과"
                risk_message = f"""
⚠️ <b>리스크 한도 초과</b>

현재 일일 손실이 한도를 초과하여 주문이 거부되었습니다.

⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
                """.strip()
                
                send_telegram_notification(risk_message, 'high')
                
                return jsonify({
                    'status': 'rejected',
                    'reason': risk_msg,
                    'timestamp': datetime.now().isoformat()
                }), 200
            
            # 포지션 크기 계산
            position_size = calculate_position_size(balance)
            if position_size is None:
                error_msg = "포지션 크기 계산 실패"
                error_message = format_error_message("포지션 크기 계산", error_msg)
                send_telegram_notification(error_message, 'error')
                return jsonify({'error': error_msg}), 500
            
            # BTC 수량 계산
            btc_amount = position_size / entry_price
            
            logging.info(f"""
            ===== 주문 요청 정보 =====
            - Action: {action}
            - Type: {position_type}
            - Amount: {btc_amount:.6f} BTC (${position_size:.2f})
            - Entry: ${entry_price:.2f}
            - Stop Loss: ${stop_loss_price:.2f} ✅
            - P/L Ratio: {pl_ratio}:1
            =======================
            """)
            
            # 기존 포지션 청산
            close_all_positions()
            
            # 새 주문 실행 (stop_loss 포함)
            orders = place_order_with_calculated_stops(
                action, btc_amount, entry_price, stop_loss_price, pl_ratio
            )
            
            if orders:
                # 주문 후 상태 확인
                time.sleep(1)  # API 제한 고려
                check_position_status()
                
                # 📱 포지션 진입 알림 전송
                entry_message = format_position_entry_message(
                    action, btc_amount, orders['actual_entry'], 
                    stop_loss_price, orders['calculated_tp'], 
                    pl_ratio, position_size, balance
                )
                send_telegram_notification(entry_message, 'high')
                
                response = {
                    'status': 'success',
                    'action': action,
                    'position_type': position_type,
                    'amount': btc_amount,
                    'value': position_size,
                    'entry_price': orders['actual_entry'],
                    'stop_loss': stop_loss_price,
                    'take_profit': orders['calculated_tp'],
                    'pl_ratio': pl_ratio,
                    'balance': balance,
                    'order_ids': {
                        'main': orders['main_order']['id'],
                        'sl': orders['sl_order']['id'] if orders['sl_order'] else None,
                        'tp': orders['tp_order']['id'] if orders['tp_order'] else None
                    },
                    'timestamp': datetime.now().isoformat()
                }
                
                # SL/TP 주문 확인
                if not orders['sl_order']:
                    logging.warning("⚠️ 손절 주문이 생성되지 않았습니다!")
                    warning_msg = "⚠️ 손절 주문 생성 실패"
                    send_telegram_notification(warning_msg, 'error')
                    
                if not orders['tp_order']:
                    logging.warning("⚠️ 익절 주문이 생성되지 않았습니다!")
                    warning_msg = "⚠️ 익절 주문 생성 실패"
                    send_telegram_notification(warning_msg, 'error')
                
                logging.info(f"주문 응답: {json.dumps(response, indent=2)}")
                return jsonify(response), 200
            else:
                error_msg = "주문 실행 실패"
                return jsonify({'error': error_msg}), 500
        
        else:
            error_msg = f"알 수 없는 액션: {action}"
            error_message = format_error_message("알 수 없는 액션", error_msg)
            send_telegram_notification(error_message, 'error')
            return jsonify({'error': error_msg}), 400
            
    except Exception as e:
        logging.error(f"웹훅 처리 오류: {str(e)}")
        
        # 웹훅 처리 오류 알림
        error_message = format_error_message("웹훅 처리", str(e))
        send_telegram_notification(error_message, 'error')
        
        return jsonify({'error': str(e)}), 500

def get_account_balance():
    """Binance 계정 잔고 조회"""
    try:
        balance = exchange.fetch_balance()
        free_usdt = balance['USDT']['free']
        return free_usdt
    except Exception as e:
        logging.error(f"잔고 조회 실패: {str(e)}")
        return None

def calculate_position_size(balance):
    """잔고 기반 포지션 크기 계산"""
    if balance is None:
        return None
    
    position_size = balance * POSITION_SIZE_PERCENT / 100
    position_size = max(MIN_POSITION_SIZE, min(position_size, MAX_POSITION_SIZE))
    
    return position_size

def check_risk_before_entry(balance):
    """포지션 진입 전 리스크 체크"""
    try:
        # 일일 손실 확인
        today_pnl = calculate_daily_pnl()
        max_daily_loss = balance * 0.05  # 5% 최대 손실
        
        if today_pnl < -max_daily_loss:
            logging.warning(f"일일 최대 손실 도달: ${today_pnl:.2f}")
            return False
            
        return True
    except:
        return True

def calculate_daily_pnl():
    """일일 손익 계산 (간단한 버전)"""
    # 실제 구현에서는 거래 내역을 조회하여 계산
    return 0

def close_all_positions():
    """모든 포지션 종료"""
    try:
        # 현재 포지션 확인
        positions = exchange.fetch_positions([SYMBOL])
        
        for position in positions:
            if position['contracts'] > 0:
                # 포지션 청산
                side = 'sell' if position['side'] == 'long' else 'buy'
                amount = abs(position['contracts'])
                
                exchange.create_order(
                    symbol=SYMBOL,
                    type='market',
                    side=side,
                    amount=amount,
                    params={'reduceOnly': True}
                )
        
        # 열린 주문 모두 취소
        open_orders = exchange.fetch_open_orders(SYMBOL)
        for order in open_orders:
            exchange.cancel_order(order['id'], SYMBOL)
        
        # 포지션 정보 초기화
        if SYMBOL in current_positions:
            del current_positions[SYMBOL]
            
    except Exception as e:
        logging.error(f"포지션 종료 실패: {str(e)}")

@app.route('/sync', methods=['POST'])
def sync_positions():
    """수동으로 포지션 동기화 실행"""
    try:
        success = sync_positions_with_exchange()
        
        if success:
            # 동기화 후 상태 반환
            positions = exchange.fetch_positions([SYMBOL])
            open_orders = exchange.fetch_open_orders(SYMBOL)
            
            return jsonify({
                'status': 'success',
                'message': '포지션 동기화 완료',
                'current_positions': current_positions,
                'exchange_positions': positions,
                'open_orders': open_orders,
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

@app.route('/positions', methods=['GET'])
def get_positions():
    """현재 포지션 상태 조회"""
    try:
        # 먼저 동기화
        sync_positions_with_exchange()
        
        positions = exchange.fetch_positions([SYMBOL])
        open_orders = exchange.fetch_open_orders(SYMBOL)
        
        # 현재가 조회
        ticker = exchange.fetch_ticker(SYMBOL)
        current_price = ticker['last']
        
        # PnL 계산
        position_info = {}
        if SYMBOL in current_positions:
            pos = current_positions[SYMBOL]
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
                'distance_to_sl': abs(current_price - pos['stop_loss']) if pos['stop_loss'] else None,
                'distance_to_tp': abs(pos['take_profit'] - current_price) if pos['take_profit'] else None
            }
        
        return jsonify({
            'positions': positions,
            'open_orders': open_orders,
            'tracked_positions': current_positions,
            'position_info': position_info,
            'timestamp': datetime.now().isoformat()
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/status', methods=['GET'])
def status():
    """봇 상태 확인"""
    # 동기화 실행
    sync_positions_with_exchange()
    
    return jsonify({
        'status': 'running',
        'symbol': SYMBOL,
        'position_size_percent': POSITION_SIZE_PERCENT,
        'current_positions': len(current_positions),
        'tracked_positions': current_positions,
        'telegram_configured': bool(TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_IDS),
        'timestamp': datetime.now().isoformat()
    }), 200

# 진단 엔드포인트 수정
@app.route('/check', methods=['GET'])
def check_orders():
    """현재 주문 상태 확인"""
    try:
        # 먼저 동기화
        sync_positions_with_exchange()
        
        position = check_position_status()
        orders = check_open_orders()
        
        # current_positions 정보 포함
        has_tracked_position = SYMBOL in current_positions
        
        return jsonify({
            'has_position': position is not None,
            'has_tracked_position': has_tracked_position,
            'tracked_position': current_positions.get(SYMBOL, None),
            'open_orders_count': len(orders),
            'orders': [
                {
                    'type': o['type'],
                    'side': o['side'],
                    'price': o.get('stopPrice', o.get('price'))
                } for o in orders
            ],
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# 텔레그램 테스트 엔드포인트 추가
@app.route('/test-telegram', methods=['POST'])
def test_telegram():
    """텔레그램 알림 테스트"""
    try:
        test_message = f"""
🧪 <b>텔레그램 알림 테스트</b>

✅ 설정이 정상적으로 작동합니다!
🤖 봇이 준비되었습니다.

⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
        """.strip()
        
        send_telegram_notification(test_message, 'normal')
        
        return jsonify({
            'status': 'success',
            'message': '텔레그램 알림 테스트 완료',
            'telegram_configured': bool(TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_IDS),
            'chat_ids_count': len([id for id in TELEGRAM_CHAT_IDS if id.strip()]),
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
    
    # Flask 앱 실행
    app.run(host='0.0.0.0', port=5000, debug=True)