from flask import Flask, request, jsonify
import ccxt
import json
import logging
from datetime import datetime
import os
from dotenv import load_dotenv
import threading
import time

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

# 거래 설정
POSITION_SIZE_PERCENT = 90#float(os.getenv('POSITION_SIZE_PERCENT', 10))
MIN_POSITION_SIZE = 10#float(os.getenv('MIN_POSITION_SIZE', 10))
MAX_POSITION_SIZE = 100000000000000#float(os.getenv('MAX_POSITION_SIZE', 1000))
SYMBOL = 'BTC/USDT'

# 포지션 추적
current_positions = {}

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
                'calculated_tp': take_profit_price
            }
            
    except Exception as e:
        logging.error(f"주문 실행 실패: {str(e)}")
        logging.error(f"상세 오류: {type(e).__name__}")
        
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
            logging.info(f"진입가: ${active_position['average']}")
            logging.info(f"현재가: ${active_position['markPrice']}")
            logging.info(f"미실현 손익: ${active_position['unrealizedPnl']}")
        
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
        return None

@app.route('/webhook', methods=['POST'])
def webhook():
    """TradingView 웹훅 수신"""
    try:
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
                logging.error("❌ 손절가가 없습니다! TradingView 설정을 확인하세요.")
                return jsonify({
                    'status': 'error',
                    'message': 'stop_loss price is missing'
                }), 400
            
            # 잔고 확인
            balance = get_account_balance()
            if balance is None:
                return jsonify({'error': '잔고 조회 실패'}), 500
            
            logging.info(f"현재 USDT 잔고: ${balance:.2f}")
            
            # 리스크 체크
            if not check_risk_before_entry(balance):
                return jsonify({
                    'status': 'rejected',
                    'reason': '리스크 한도 초과',
                    'timestamp': datetime.now().isoformat()
                }), 200
            
            # 포지션 크기 계산
            position_size = calculate_position_size(balance)
            if position_size is None:
                return jsonify({'error': '포지션 크기 계산 실패'}), 500
            
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
                
                response = {
                    'status': 'success',
                    'action': action,
                    'position_type': position_type,
                    'amount': btc_amount,
                    'value': position_size,
                    'entry_price': entry_price,
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
                if not orders['tp_order']:
                    logging.warning("⚠️ 익절 주문이 생성되지 않았습니다!")
                
                logging.info(f"주문 응답: {json.dumps(response, indent=2)}")
                return jsonify(response), 200
            else:
                return jsonify({'error': '주문 실행 실패'}), 500
        
        else:
            return jsonify({'error': '알 수 없는 액션'}), 400
            
    except Exception as e:
        logging.error(f"웹훅 처리 오류: {str(e)}")
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

@app.route('/positions', methods=['GET'])
def get_positions():
    """현재 포지션 상태 조회"""
    try:
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
                'distance_to_sl': abs(current_price - pos['stop_loss']),
                'distance_to_tp': abs(pos['take_profit'] - current_price)
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
    return jsonify({
        'status': 'running',
        'symbol': SYMBOL,
        'position_size_percent': POSITION_SIZE_PERCENT,
        'current_positions': len(current_positions),
        'timestamp': datetime.now().isoformat()
    }), 200

# 진단 엔드포인트 추가
@app.route('/check', methods=['GET'])
def check_orders():
    """현재 주문 상태 확인"""
    try:
        position = check_position_status()
        orders = check_open_orders()
        
        return jsonify({
            'has_position': position is not None,
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

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)