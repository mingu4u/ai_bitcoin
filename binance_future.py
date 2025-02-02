import sys
import os
from dotenv import load_dotenv
import pandas as pd
import json
from openai import OpenAI
import ta
from ta.utils import dropna
import time
import requests
import base64
from PIL import Image
import io
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from selenium.common.exceptions import TimeoutException, ElementClickInterceptedException, WebDriverException, NoSuchElementException
import logging
from datetime import datetime, timezone, timedelta
from youtube_transcript_api import YouTubeTranscriptApi
from pydantic import BaseModel
from openai import OpenAI
import sqlite3
from datetime import datetime, timedelta
import pickle
import schedule
import signal
import atexit
import ccxt.binance
import time
import logging
from typing import Optional, Dict, Any





class BinanceFuturesTrader:
    def __init__(self, api_key: str, api_secret: str, logger):
        self.exchange = ccxt.binance({
            'apiKey': api_key,
            'secret': api_secret,
            'enableRateLimit': True,
            'options': {
                'defaultType': 'future'
            }
        })
        # self.setup_logging()
        self.symbol = "BTC/USDT"
        self.leverage = 20  # 기본 레버리지 설정
        self.logger = logger
        self.exchange.load_markets()


    def is_ai_trade(self, order, last_ai_entry):
        if not last_ai_entry:
            return False
            
        # 주문 ID 직접 비교
        if str(order['id']) == str(last_ai_entry[0]):
            return True
            
        # AI 거래의 TP/SL 주문인지 확인
        client_order_id = order['info'].get('origClientOrderId', '')
        parent_order_id = order['info'].get('parentOrderId', '')
        
        return (client_order_id.startswith(str(last_ai_entry[0])) or 
                str(parent_order_id) == str(last_ai_entry[0]))

    def cancel_existing_tp_sl_orders(self):
        try:
            open_orders = self.exchange.fetch_open_orders(self.symbol)
            cancelled_orders = []
            
            for order in open_orders:
                if order['type'] in ['TAKE_PROFIT_MARKET', 'STOP_MARKET']:
                    try:
                        self.exchange.cancel_order(order['id'], self.symbol)
                        cancelled_orders.append(order['id'])
                        self.logger.info(f"Cancelled TP/SL order: {order['id']}")
                    except Exception as e:
                        self.logger.error(f"Error cancelling order {order['id']}: {e}")
                        
            # 취소 확인
            time.sleep(1)  # API 제한 고려
            remaining_orders = self.exchange.fetch_open_orders(self.symbol)
            for order in remaining_orders:
                if order['id'] in cancelled_orders:
                    self.logger.warning(f"Order {order['id']} was not properly cancelled")
                    
        except Exception as e:
            self.logger.error(f"Error in cancel_existing_tp_sl_orders: {e}")
            raise



    # 수동 거래 모니터링
    def monitor_manual_trades(self):
        try:
            # 최근 주문 내역 직접 조회 (최근 5분)
            since = int((datetime.now() - timedelta(minutes=5)).timestamp() * 1000)
            since_datetime = datetime.fromtimestamp(since/1000)
            orders = self.exchange.fetch_orders(self.symbol, since)
            
            # DB 연결
            conn = sqlite3.connect('bitcoin_trades.db')
            c = conn.cursor()
            
            try:
                # 최근 거래 내역 조회
                c.execute("""
                    SELECT timestamp, order_id 
                    FROM trades 
                    WHERE timestamp >= ? 
                """, (since_datetime.isoformat(),))
                recent_trades = c.fetchall()
                recorded_trades = set((ts, oid) for ts, oid in recent_trades)
                
                # 가장 최근의 reflection 조회
                c.execute("""
                    SELECT reflection 
                    FROM trades 
                    WHERE reflection IS NOT NULL 
                    ORDER BY timestamp DESC 
                    LIMIT 1
                """)
                last_reflection = c.fetchone()
                last_reflection = last_reflection[0] if last_reflection else None

                # AI Entry 주문 조회
                c.execute("""
                    SELECT t.order_id, t.timestamp
                    FROM trades t 
                    WHERE t.trade_type = 'AI'
                    ORDER BY t.timestamp DESC 
                    LIMIT 1
                """)
                last_ai_entry = c.fetchone()

                for order in orders:
                    # 완료된 주문만 처리
                    if order['status'] != 'closed':
                        continue
                    
                    order_id = str(order['id'])
                    order_timestamp = datetime.fromtimestamp(order['timestamp']/1000).isoformat()
                    
                    # 중복 기록 방지
                    if (order_timestamp, order_id) in recorded_trades:
                        continue
                    
                    # 거래 방향 결정
                    decision = 'buy' if order['side'] == 'buy' else 'sell'
                    
                    # 잔고 정보 조회
                    balance = self.exchange.fetch_balance()
                    usdt_balance = balance['USDT']
                    free_usdt = usdt_balance['free']
                    used_usdt = usdt_balance['used']
                    total_usdt = usdt_balance['total']
                    
                    # 레버리지를 고려한 실제 거래 비율 계산
                    actual_trade_amount = abs(order['cost']) / self.leverage
                    trade_percentage = (actual_trade_amount / total_usdt) * 100 if total_usdt > 0 else 0
                    
                    # 기본값으로 MANUAL 설정
                    trade_type = 'MANUAL'
                    reason = 'Manual Trade'
                    
                    # AI 거래 여부 확인
                    if self.is_ai_trade(order, last_ai_entry):
                        trade_type = 'AI'
                        order_type = order['info'].get('type', '').upper()
                        if order_type == 'TAKE_PROFIT_MARKET':
                            reason = 'Take Profit'
                        elif order_type == 'STOP_MARKET':
                            reason = 'Stop Loss'
                        
                        # AI 트레이딩 타임스탬프 고려
                        order_timestamp = max(
                            order_timestamp, 
                            last_ai_entry[1] if last_ai_entry and last_ai_entry[1] else order_timestamp
                        )
                    
                    # 포지션 정보 조회
                    positions = self.exchange.fetch_positions([self.symbol])
                    current_position = next((pos for pos in positions if float(pos.get('contracts', 0) or 0) != 0), None)
                    btc_avg_buy_price = float(current_position['entryPrice']) if current_position else 0
                    
                    # BTC 현재가 조회
                    ticker = self.exchange.fetch_ticker(self.symbol)
                    current_btc_price = ticker['last']

                    # DB에 거래 기록
                    c.execute("""
                        INSERT INTO trades 
                        (timestamp, trade_type, order_id, decision, percentage, reason, 
                        btc_balance, usdt_balance, total_assets, btc_avg_buy_price, btc_current_price, reflection) 
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        order_timestamp,
                        trade_type,
                        order_id,
                        decision,
                        int(trade_percentage),
                        reason,
                        used_usdt,
                        free_usdt,
                        total_usdt,
                        btc_avg_buy_price,
                        current_btc_price,
                        last_reflection
                    ))
                    conn.commit()
                    
                    self.logger.info(f"{trade_type} trade recorded: {decision.upper()} at {current_btc_price} (Reason: {reason})")
                
            finally:
                conn.close()
                
        except Exception as e:
            self.logger.error(f"Error monitoring trades: {e}")
            if 'conn' in locals():
                conn.close()

    def setup_leverage_and_margin(self, leverage: int):
        try:
            # 현재 포지션 확인
            positions = self.exchange.fetch_positions([self.symbol])
            has_open_position = False
            
            # 포지션이 있는지 확인
            if positions:
                for position in positions:
                    position_size = float(position.get('contracts', 0) or 0)
                    if position_size != 0:
                        has_open_position = True
                        # leverage 값이 None인 경우 기본값 사용
                        try:
                            current_leverage = int(position.get('leverage', leverage))
                        except (TypeError, ValueError):
                            current_leverage = leverage
                            
                        self.leverage = current_leverage  # 현재 레버리지 유지
                        self.logger.warning(f"Open position detected. Keeping current leverage at {current_leverage}x")
                        break
            
            # 열린 포지션이 없을 때만 레버리지 설정
            if not has_open_position:
                self.exchange.set_leverage(leverage, self.symbol)
                self.exchange.set_margin_mode('isolated', self.symbol)
                self.leverage = leverage
                self.logger.info(f"Leverage set to {leverage}x and margin mode set to isolated")
                
        except Exception as e:
            self.logger.error(f"Error setting up leverage and margin: {e}")
            # 에러 발생 시 기본 레버리지 설정
            self.leverage = leverage
            raise    

    async def get_position_size(self, usdt_amount: float) -> float:
        try:
            ticker = await self.exchange.fetch_ticker(self.symbol)
            btc_price = ticker['last']
            position_size = (usdt_amount * self.leverage) / btc_price
            return position_size
        except Exception as e:
            self.logger.error(f"Error calculating position size: {e}")
            raise

    async def open_position(self, 
                          side: str, 
                          usdt_amount: float,
                          tp_percentage: float,
                          sl_percentage: float) -> Optional[Dict[str, Any]]:
        try:
            position_size = await self.get_position_size(usdt_amount)
            entry_price = (await self.exchange.fetch_ticker(self.symbol))['last']
            
            # Calculate TP/SL prices
            if side == 'buy':
                tp_price = entry_price * (1 + tp_percentage/100)
                sl_price = entry_price * (1 - sl_percentage/100)
            else:
                tp_price = entry_price * (1 - tp_percentage/100)
                sl_price = entry_price * (1 + sl_percentage/100)

            # Open main position
            order = await self.exchange.create_order(
                symbol=self.symbol,
                type='MARKET',
                side=side,
                amount=position_size
            )

            # Set take profit order
            tp_order = await self.exchange.create_order(
                symbol=self.symbol,
                type='TAKE_PROFIT_MARKET',
                side='sell' if side == 'buy' else 'buy',
                amount=position_size,
                params={'stopPrice': tp_price,
                        'reduceOnly': True}
            )

            # Set stop loss order
            sl_order = await self.exchange.create_order(
                symbol=self.symbol,
                type='STOP_MARKET',
                side='sell' if side == 'buy' else 'buy',
                amount=position_size,
                params={'stopPrice': sl_price,
                        'reduceOnly': True}
            )

            self.logger.info(f"{side.upper()} position opened: Size={position_size}, Entry={entry_price}, TP={tp_price}, SL={sl_price}")
            return {'entry': order, 'tp': tp_order, 'sl': sl_order}
        
        except Exception as e:
            self.logger.error(f"Error opening position: {e}")
            raise

    def market_order_with_tp_sl(self, side: str, buy_amount: float, pl_ratio: float, sl_price: float):
        try:
            # 시작하기 전에 불필요한 주문만 취소 (같은 방향 추가 진입을 위한 TP/SL은 아직 유지)
            try:
                open_orders = self.exchange.fetch_open_orders(self.symbol)
                for order in open_orders:
                    # TP/SL 주문이 아닌 경우에만 취소
                    if order['type'] not in ['TAKE_PROFIT_MARKET', 'STOP_MARKET']:
                        self.exchange.cancel_order(order['id'], self.symbol)
                        self.logger.info(f"Cancelled non-TP/SL order: {order['id']}")
            except Exception as e:
                self.logger.error(f"Error cancelling non-TP/SL orders: {e}")

            # 현재가 조회
            ticker = self.exchange.fetch_ticker(self.symbol)
            current_price = ticker['last']

            # TP/SL 가격 검증
            min_price_diff = current_price * 0.001  # 최소 0.1% 차이 필요
            
            # 안전 마진 상수 (0.2%)
            SAFETY_MARGIN = 0.002

            # 트레일링 스탑로스를 위한 추가 파라미터
            trailing_threshold = 0.01  # 1% 수익 달성 시 트레일링 시작
            trailing_buffer = 0.004     # 0.4% 안전 마진

            if side == 'buy':
                # SL 가격 보정
                if sl_price >= current_price or (current_price - sl_price) < min_price_diff:
                    adjusted_sl_price = current_price * (1 - SAFETY_MARGIN)
                    self.logger.warning(f"Invalid SL price for long position. Adjusting SL from {sl_price} to {adjusted_sl_price}")
                    sl_price = adjusted_sl_price

                # TP 가격 재계산
                tp_price = current_price + pl_ratio * (current_price - sl_price)

                # TP 가격 보정
                if tp_price <= current_price or (tp_price - current_price) < pl_ratio * min_price_diff:
                    adjusted_tp_price = current_price * (1 + SAFETY_MARGIN)
                    self.logger.warning(f"Invalid TP price for long position. Adjusting TP from {tp_price} to {adjusted_tp_price}")
                    tp_price = adjusted_tp_price

            else:  # sell
                # SL 가격 보정
                if sl_price <= current_price or (sl_price - current_price) < min_price_diff:
                    adjusted_sl_price = current_price * (1 + SAFETY_MARGIN)
                    self.logger.warning(f"Invalid SL price for short position. Adjusting SL from {sl_price} to {adjusted_sl_price}")
                    sl_price = adjusted_sl_price

                # TP 가격 재계산
                tp_price = current_price - pl_ratio * (sl_price - current_price)

                # TP 가격 보정
                if tp_price >= current_price or (current_price - tp_price) < pl_ratio * min_price_diff:
                    adjusted_tp_price = current_price * (1 - SAFETY_MARGIN)
                    self.logger.warning(f"Invalid TP price for short position. Adjusting TP from {tp_price} to {adjusted_tp_price}")
                    tp_price = adjusted_tp_price

            # 현재 포지션 확인
            positions = self.exchange.fetch_positions([self.symbol])
            current_position = None
            position_side = None  # position_side 명시적 초기화

            for pos in positions:
                if float(pos.get('contracts', 0) or 0) != 0:
                    current_position = pos
                    position_side = pos['side']  # binance futures에서는 'long' 또는 'short' 반환
                    break

            # 반대 방향 주문이 들어온 경우 포지션 축소/청산
            if current_position and position_side:  # position_side가 있는 경우에만 실행
                if (position_side == 'long' and side == 'sell') or (position_side == 'short' and side == 'buy'):
                    position_size = float(current_position['contracts'])
                    position_notional = float(current_position['notional'])
                    self.logger.info(f"Reducing/Closing {position_side} position of {position_size} contracts")
                    
                    # 레버리지를 고려한 실제 주문 수량 계산
                    leveraged_amount = buy_amount * self.leverage
                    calculated_quantity = leveraged_amount / current_price
                    
                    # 청산하려는 금액이 현재 포지션보다 큰 경우 전량 청산
                    if leveraged_amount >= abs(position_notional):
                        quantity = abs(position_size)
                        self.logger.info(f"Closing entire position of {quantity} contracts")
                        
                        # 기존 열려있는 모든 주문 취소
                        try:
                            open_orders = self.exchange.fetch_open_orders(self.symbol)
                            for order in open_orders:
                                self.exchange.cancel_order(order['id'], self.symbol)
                                self.logger.info(f"Cancelled order {order['id']}")
                        except Exception as e:
                            self.logger.error(f"Error cancelling orders: {e}")
                    else:
                        # 부분 청산
                        quantity = calculated_quantity
                        self.logger.info(f"Partially reducing position by {quantity} contracts")
                    
                    # 포지션 축소/청산 주문
                    order = self.exchange.create_market_order(
                        symbol=self.symbol,
                        side=side,
                        amount=quantity,
                        params={'reduceOnly': True}
                    )
                    
                    self.logger.info(f"Position {position_side} closed/reduced at price: {current_price}")
                    return {
                        'entry': order,
                        'tp': None,
                        'sl': None
                    }

            # 같은 방향 추가 진입인 경우
            elif current_position and side == position_side:
                # 1. 기존 TP/SL 주문 정보 읽기
                try:
                    open_orders = self.exchange.fetch_open_orders(self.symbol)
                    existing_sl_price = None
                    for order in open_orders:
                        if order['type'] == 'STOP_MARKET':
                            existing_sl_price = float(order['info'].get('stopPrice', order.get('price', 0)))
                            break
                except Exception as e:
                    self.logger.error(f"Error fetching existing SL price: {e}")
                    existing_sl_price = None

                # 2. 새로운 TP/SL 가격 계산
                # 총 포지션 크기와 평균 진입 가격 계산
                total_position_size = quantity + float(current_position['contracts'])
                total_position_value = (quantity * current_price) + (float(current_position['contracts']) * float(current_position['entryPrice']))
                new_avg_entry_price = total_position_value / total_position_size

                # 기존 TP/SL 주문 취소
                try:
                    for order in open_orders:
                        if order['type'] in ['TAKE_PROFIT_MARKET', 'STOP_MARKET']:
                            self.exchange.cancel_order(order['id'], self.symbol)
                            self.logger.info(f"Cancelled existing TP/SL order: {order['id']}")
                except Exception as e:
                    self.logger.error(f"Error cancelling existing TP/SL orders: {e}")
                    return None

                # SL 가격 가중평균 계산
                if existing_sl_price:
                    total_sl_value = (quantity * sl_price) + (float(current_position['contracts']) * existing_sl_price)
                    new_sl_price = total_sl_value / total_position_size
                else:
                    new_sl_price = sl_price

                # TP 가격 계산
                if side == 'buy':
                    new_tp_price = new_avg_entry_price + (new_avg_entry_price - new_sl_price) * pl_ratio
                else:  # sell
                    new_tp_price = new_avg_entry_price - (new_sl_price - new_avg_entry_price) * pl_ratio

                # 계산된 새 가격으로 업데이트
                tp_price = new_tp_price
                sl_price = new_sl_price

            # 새로운 포지션 진입 또는 같은 방향 추가 진입을 위한 잔고 확인
            # 가용 자금 조회
            balance = self.exchange.fetch_balance()
            available_balance = float(balance['USDT']['free'])
            
            if available_balance < 10:  # USDT 최소 주문금액
                self.logger.error(f"Insufficient balance. Available: {available_balance} USDT")
                return None
                
            # 안전 마진을 고려한 최대 사용 가능 금액 계산 (가용 자금의 65%까지만 사용)
            max_safe_amount = available_balance * 0.65
            
            # 요청된 주문 금액이 최대 안전 금액을 초과하는 경우 조정
            if buy_amount > max_safe_amount:
                original_amount = buy_amount
                buy_amount = max_safe_amount
                self.logger.warning(
                    f"Requested order amount ({original_amount} USDT) exceeds safe limit. "
                    f"Adjusted to {buy_amount} USDT (65% of available balance)"
                )
            
            # 레버리지를 고려한 실제 주문 수량 계산
            leveraged_amount = buy_amount * self.leverage
            quantity = leveraged_amount / current_price
            
            # 최소 주문 수량 확인
            market_limits = self.exchange.markets[self.symbol]['limits']
            min_amount = market_limits['amount']['min']
            if quantity < min_amount:
                self.logger.error(f"Order quantity ({quantity}) is below minimum ({min_amount})")
                return None
            
            # 주문 실행
            order = self.exchange.create_market_order(
                symbol=self.symbol,
                side=side,
                amount=quantity
            )

            # 포지션 진입 가격 저장 (트레일링 SL을 위해)
            entry_price = current_price

            # 트레일링 스탑로스 모니터링 함수
            def monitor_and_adjust_sl():
                try:
                    positions = self.exchange.fetch_positions([self.symbol])
                    current_position = None
                    for pos in positions:
                        if float(pos.get('contracts', 0) or 0) != 0:
                            current_position = pos
                            break

                    if not current_position:
                        return None

                    current_ticker = self.exchange.fetch_ticker(self.symbol)
                    current_market_price = current_ticker['last']
                    position_size = float(current_position['contracts'])
                    position_side = current_position['side']

                    # 수익률 계산
                    if position_side == 'long':
                        profit_percentage = (current_market_price - entry_price) / entry_price
                    else:  # short
                        profit_percentage = (entry_price - current_market_price) / entry_price

                    # 트레일링 스탑로스 로직
                    if profit_percentage >= trailing_threshold:
                        # 새로운 SL 가격 계산
                        if position_side == 'long':
                            new_sl_price = current_market_price * (1 - trailing_buffer)
                        else:  # short
                            new_sl_price = current_market_price * (1 + trailing_buffer)

                        # 기존 SL 주문 취소
                        try:
                            open_orders = self.exchange.fetch_open_orders(self.symbol)
                            for order in open_orders:
                                if order['type'] == 'STOP_MARKET':
                                    self.exchange.cancel_order(order['id'], self.symbol)
                                    self.logger.info("기존 SL 주문 취소")
                        except Exception as cancel_error:
                            self.logger.error(f"SL 주문 취소 중 오류: {cancel_error}")

                        # 새로운 SL 주문 생성
                        tp_side = 'sell' if position_side == 'long' else 'buy'
                        new_sl_order = self.exchange.create_order(
                            symbol=self.symbol,
                            type='STOP_MARKET',
                            side=tp_side,
                            amount=position_size,
                            params={
                                'stopPrice': new_sl_price,
                                'reduceOnly': True
                            }
                        )

                        self.logger.info(f"트레일링 SL 재설정: {new_sl_price}")
                        return new_sl_order

                except Exception as e:
                    self.logger.error(f"SL 모니터링 중 오류: {e}")
                    return None

            # 총 포지션 크기 계산
            total_position_size = quantity
            if current_position and side == position_side:
                total_position_size += float(current_position['contracts'])

            # TP/SL 주문 전에 기존 대기 중인 주문 취소
            self.cancel_existing_tp_sl_orders()

            # TP/SL 주문
            tp_side = 'sell' if side == 'buy' else 'buy'
            try:            
                # Take Profit 주문
                tp_order = self.exchange.create_order(
                    symbol=self.symbol,
                    type='TAKE_PROFIT_MARKET',
                    side=tp_side,
                    amount=quantity,
                    params={
                        'stopPrice': tp_price,
                        'reduceOnly': True,
                        'clientOrderId': f"tp_{order['id']}"
                    }
                )            

                # Stop Loss 주문
                sl_order = self.exchange.create_order(
                    symbol=self.symbol,
                    type='STOP_MARKET',
                    side=tp_side,
                    amount=quantity,
                    params={
                        'stopPrice': sl_price,
                        'reduceOnly': True,
                        'clientOrderId': f"sl_{order['id']}"
                    }
                )

            except Exception as e:
                # TP/SL 주문 실패 시 기존 포지션 취소
                self.logger.error(f"TP/SL 주문 실패: {e}")
                try:
                    # 기존 포지션 취소
                    self.exchange.create_market_order(
                        symbol=self.symbol,
                        side=tp_side,
                        amount=quantity,
                        params={'reduceOnly': True}
                    )
                except Exception as cancel_error:
                    self.logger.error(f"포지션 취소 실패: {cancel_error}")

                raise

            action_type = "Position increased" if current_position and side == position_side else "New position opened"
            self.logger.info(f"{action_type} - Side: {side}, Amount: {buy_amount} USDT, Leverage: {self.leverage}x")
            self.logger.info(f"Quantity: {quantity} BTC, Entry: {current_price}, TP: {tp_price}, SL: {sl_price}")
            self.logger.info(f"Available balance after order: {available_balance - buy_amount} USDT")

            return {
                'entry': order,
                'tp': tp_order,
                'sl': sl_order,
                'monitor_sl': monitor_and_adjust_sl,
                'entry_price': entry_price
            }
        
        except Exception as e:
            self.logger.error(f"Order execution error: {str(e)}")
            raise
    

    async def close_position(self) -> Optional[Dict[str, Any]]:
        try:
            position = await self.exchange.fetch_positions(self.symbol)
            if float(position['contracts']) == 0:
                return None

            side = 'sell' if position['side'] == 'long' else 'buy'
            order = await self.exchange.create_order(
                symbol=self.symbol,
                type='MARKET',
                side=side,
                amount=abs(float(position['contracts']))
            )

            self.logger.info(f"Position closed: {order}")
            return order

        except Exception as e:
            self.logger.error(f"Error closing position: {e}")
            raise

    async def get_account_balance(self) -> float:
        try:
            balance = await self.exchange.fetch_balance()
            return float(balance['USDT']['free'])
        except Exception as e:
            self.logger.error(f"Error fetching balance: {e}")
            raise




# .env 파일에 저장된 환경 변수를 불러오기 (API 키 등)
load_dotenv()

# 로깅 설정 - 로그 레벨을 INFO로 설정하여 중요 정보 출력
logging.getLogger().handlers.clear()
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)


# BINANCE 객체 생성
api_key = os.getenv("BINANCE_API_KEY")
secret_key = os.getenv("BINANCE_SECRET_KEY")
env = os.getenv("ENVIRONMENT")
if not api_key or not secret_key:
    logger.error("API keys not found. Please check your .env file.")
    raise ValueError("Missing API keys. Please check your .env file.")
trader = BinanceFuturesTrader(api_key, secret_key, logger)

# 레버리지 설정 
trader.setup_leverage_and_margin(20)  # 20배 레버리지

# OpenAI 구조화된 출력 체크용 클래스
class TradingDecision(BaseModel):
    decision: str
    percentage: int
    reason: str
    stop_loss_price: int
    pl_ratio: float



# 모든 크롬 프로세스 종료 후 정리
def cleanup_chrome_processes():
    try:
        if env=="ec2":
            os.system('sudo pkill -f "chrome|chromium|chromedriver"')
        elif env=="local":
            os.system('taskkill /f /im chrome.exe')
            os.system('taskkill /f /im chromedriver.exe')
            time.sleep(2)  # 프로세스들이 완전히 종료되기를 기다림
    except Exception as e:
        logger.error(f"Chrome processes cleanup failed: {e}")

# 종료 시 정리 작업을 수행하는 함수
def cleanup_handler():
    logger.info("Cleaning up chrome processes before exit...")
    cleanup_chrome_processes()

# 시그널 핸들러 함수
def signal_handler(signum, frame):
    logger.info(f"Signal {signum} received. Performing cleanup...")
    cleanup_handler()
    sys.exit(0)


# SQLite 데이터베이스 초기화 함수 - 거래 내역을 저장할 테이블을 생성
def init_db():
    conn = sqlite3.connect('bitcoin_trades.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS trades
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  timestamp TEXT,
                  trade_type TEXT,
                  order_id TEXT,
                  decision TEXT,
                  percentage INTEGER,
                  reason TEXT,
                  btc_balance REAL,
                  usdt_balance REAL,
                  total_assets REAL,
                  btc_avg_buy_price REAL,
                  btc_current_price REAL,
                  reflection TEXT)''')
    conn.commit()
    return conn


# 거래 기록을 DB에 저장하는 함수

# 거래 기록 함수 수정
def log_trade(conn, trade_type, order_id, decision, percentage, reason, btc_balance, usdt_balance, total_assets, btc_avg_buy_price, btc_current_price, reflection=''):
    c = conn.cursor()
    timestamp = datetime.now().isoformat()
    c.execute("""INSERT INTO trades 
                 (timestamp, trade_type, order_id, decision, percentage, reason, btc_balance, usdt_balance, total_assets, btc_avg_buy_price, btc_current_price, reflection) 
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
              (timestamp, trade_type, order_id, decision, percentage, reason, btc_balance, usdt_balance, total_assets, btc_avg_buy_price, btc_current_price, reflection))
    conn.commit()

# 최근 투자 기록 조회
# def get_recent_trades(conn, days=1):
#     c = conn.cursor()
#     some_days_ago = (datetime.now() - timedelta(days=days)).isoformat()
#     c.execute("SELECT * FROM trades WHERE timestamp > ? ORDER BY timestamp DESC", (some_days_ago,))
#     columns = [column[0] for column in c.description]
#     return pd.DataFrame.from_records(data=c.fetchall(), columns=columns)

def get_recent_trades(conn, num_trades=40):
    f"""
    최근 n개의 거래 내역을 시간 역순으로 가져오는 함수
    
    Args:
        conn: SQLite 데이터베이스 연결 객체
        num_trades: 가져올 거래 내역의 수 (기본값: 20)
    
    Returns:
        DataFrame: 최근 {num_trades}개의 거래 내역이 시간 역순으로 정렬된 데이터프레임
    """
    try:
        c = conn.cursor()
        c.execute("""
            SELECT * FROM trades 
            ORDER BY timestamp DESC
            LIMIT ?
        """, (num_trades,))
        
        columns = [column[0] for column in c.description]
        return pd.DataFrame.from_records(data=c.fetchall(), columns=columns)
    
    except Exception as e:
        logging.error(f"Error fetching recent trades: {e}")
        return pd.DataFrame()
    finally:
        if 'c' in locals():
            c.close()


# 최근 투자 기록을 기반으로 퍼포먼스 계산 (초기 잔고 대비 최종 잔고)
def calculate_performance(trades_df):
    if trades_df.empty or trades_df.iloc[-1]['usdt_balance'] == 0:
        return 0
    
    initial_balance = trades_df.iloc[-1]['usdt_balance'] + trades_df.iloc[-1]['btc_balance'] * trades_df.iloc[-1]['btc_current_price']
    final_balance = trades_df.iloc[0]['usdt_balance'] + trades_df.iloc[0]['btc_balance'] * trades_df.iloc[0]['btc_current_price']
    
    return (final_balance - initial_balance) / initial_balance * 100



# AI 모델을 사용하여 최근 투자 기록과 시장 데이터를 기반으로 분석 및 반성을 생성하는 함수
def generate_reflection(trades_df, current_market_data):
    performance = calculate_performance(trades_df) # 투자 퍼포먼스 계산
    
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    if not client.api_key:
        logger.error("OpenAI API key is missing or invalid.")
        return None        
    
    # OpenAI API 호출로 AI의 반성 일기 및 개선 사항 생성 요청    
    response = client.chat.completions.create(
        model="gpt-4o-mini", #gpt-4o-2024-11-20
        messages=[
            {
                "role": "system",
                "content": "You are an AI trading assistant tasked with analyzing recent trading performance and current market conditions to generate insights and improvements for future trading decisions."
            },
            {
                "role": "user",
                "content": f"""
                Recent 20 trading data:
                {trades_df.to_json(orient='records')}
                
                Current market data:
                {current_market_data}
                
                Overall performance over the last 20 trades : {performance:.2f}%
                
                Please analyze this data and provide:
                1. A brief reflection on the recent trading decisions
                2. Insights on what worked well and what didn't
                3. Suggestions for improvement in future trading decisions
                4. Any patterns or trends you notice in the market data
                
                Limit your response to 250 words or less.
                """
            }
        ]
    )
    
    try:
        response_content = response.choices[0].message.content
        return response_content
    except (IndexError, AttributeError) as e:
        logger.error(f"Error extracting response content: {e}")
        return None

def get_db_connection():
    return sqlite3.connect('bitcoin_trades.db')



# 데이터프레임에 보조 지표를 추가하는 함수
def add_indicators(df):
    # 볼린저 밴드 추가
    indicator_bb = ta.volatility.BollingerBands(close=df['close'], window=20, window_dev=2)
    df['bb_bbm'] = indicator_bb.bollinger_mavg()
    df['bb_bbh'] = indicator_bb.bollinger_hband()
    df['bb_bbl'] = indicator_bb.bollinger_lband()
    
    # RSI (Relative Strength Index) 추가
    df['rsi'] = ta.momentum.RSIIndicator(close=df['close'], window=14).rsi()
    
    # MACD (Moving Average Convergence Divergence) 추가
    macd = ta.trend.MACD(close=df['close'])
    df['macd'] = macd.macd()
    df['macd_signal'] = macd.macd_signal()
    df['macd_diff'] = macd.macd_diff()
    
    # 이동평균선 (단기, 장기)
    df['sma_20'] = ta.trend.SMAIndicator(close=df['close'], window=20).sma_indicator()
    df['ema_12'] = ta.trend.EMAIndicator(close=df['close'], window=12).ema_indicator()
    
    return df

# UTC에서 한국 표준시 (KST) 로 변환
def convert_utc_to_kst(utc_date_str):
    if not utc_date_str:
        return ''
    
    try:
        # Parse the UTC date string
        utc_datetime = datetime.strptime(utc_date_str, '%m/%d/%Y, %I:%M %p, %z')
        
        # Convert to KST (UTC+9)
        kst_datetime = utc_datetime + timedelta(hours=9)
        
        # Format the date in the desired KST format
        return kst_datetime.strftime('%Y/%m/%d/%H:%M (KST)')
    except ValueError:
        return ''

# 공포 탐욕 지수 조회
def get_fear_and_greed_index():
    url = "https://api.alternative.me/fng/"
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        result = data['data'][0]
        
        # timestamp를 초 단위에서 KST datetime 문자열로 변환
        timestamp = pd.to_datetime(int(result['timestamp']), unit='s')
        kst_time = timestamp.tz_localize('UTC').tz_convert('Asia/Seoul')
        result['timestamp'] = kst_time.strftime('%Y/%m/%d %H:%M (KST)')
        
        return result
    except requests.exceptions.RequestException as e:
        print(f"Error fetching Fear and Greed Index: {e}")
        return None

# 뉴스 데이터 가져오기
def get_bitcoin_news():
    serpapi_key = os.getenv("SERPAPI_API_KEY")
    if not serpapi_key:
        print("SERPAPI API key is missing.")
        return None  # 또는 함수 종료
    url = "https://serpapi.com/search.json"
    params = {
        "engine": "google_news",
        "q": "btc",
        "api_key": serpapi_key
    }
    
    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        data = response.json()
        
        news_results = data.get("news_results", [])
        headlines = []
        for item in news_results:
            headlines.append({
                "title": item.get("title", ""),
                "timestamp": convert_utc_to_kst(item.get("date", ""))
            })
        
        return headlines[:5]
    except requests.RequestException as e:
        print(f"Error fetching news: {e}")
        return []


# 유튜브 자막 데이터 가져오기
def get_combined_transcript(video_id):
    try:
        transcript = YouTubeTranscriptApi.get_transcript(video_id, languages=['ko'])
        combined_text = ' '.join(entry['text'] for entry in transcript)
        return combined_text
    except Exception as e:
        logger.error(f"Error fetching YouTube transcript: {e}")
        return ""


#### Selenium 관련 함수
def create_driver():
    env = os.getenv("ENVIRONMENT")
    logger.info("ChromeDriver 설정 중...")
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    # WebGL 경고 메시지 제거를 위한 추가 옵션들
    chrome_options.add_argument("--enable-unsafe-webgl")
    chrome_options.add_argument("--enable-unsafe-swiftshader")
    chrome_options.add_argument('--disable-web-security')
    chrome_options.add_argument('--allow-running-insecure-content')
    chrome_options.add_argument('--disable-software-rasterizer')

    # 로깅 레벨 조정
    chrome_options.add_argument('--log-level=3')
    try:
        if env == "local":
            chrome_options.add_experimental_option('excludeSwitches', ['enable-logging'])
            from webdriver_manager.chrome import ChromeDriverManager
            service = Service(ChromeDriverManager().install())
        elif env == "ec2":
            service = Service('/usr/bin/chromedriver')
        else:
            raise ValueError(f"Unsupported environment. Only local or ec2: {env}")
        driver = webdriver.Chrome(service=service, options=chrome_options)
        return driver
    except Exception as e:
        logger.error(f"ChromeDriver 생성 중 오류 발생: {e}")
        raise


# XPath로 Element 찾기
def click_element_by_xpath(driver, xpath, element_name, wait_time=10):
    try:
        element = WebDriverWait(driver, wait_time).until(
            EC.presence_of_element_located((By.XPATH, xpath))
        )
        # 요소가 뷰포트에 보일 때까지 스크롤
        driver.execute_script("arguments[0].scrollIntoView(true);", element)
        # 요소가 클릭 가능할 때까지 대기
        element = WebDriverWait(driver, wait_time).until(
            EC.element_to_be_clickable((By.XPATH, xpath))
        )
        element.click()
        logger.info(f"{element_name} 클릭 완료")
        time.sleep(2)  # 클릭 후 잠시 대기
    except TimeoutException:
        logger.error(f"{element_name} 요소를 찾는 데 시간이 초과되었습니다.")
    except ElementClickInterceptedException:
        logger.error(f"{element_name} 요소를 클릭할 수 없습니다. 다른 요소에 가려져 있을 수 있습니다.")
    except NoSuchElementException:
        logger.error(f"{element_name} 요소를 찾을 수 없습니다.")
    except Exception as e:
        logger.error(f"{element_name} 클릭 중 오류 발생: {e}")




def check_login_status(driver):
    """로그인 상태 확인"""
    try:
        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.CLASS_NAME, "logged-in-user-menu-button")))
        return True
    except:
        return False

def load_cookies(driver, filename="tradingview_cookies.pkl"):
   """쿠키 로드"""
   # 현재 작업 디렉토리에서 파일 로드
   current_dir = os.getcwd()
   file_path = os.path.join(current_dir, filename)
   
   if os.path.exists(file_path):
       with open(file_path, 'rb') as cookiesfile:
           cookies = pickle.load(cookiesfile)
           for cookie in cookies:
               driver.add_cookie(cookie)
       print(f"쿠키를 로드했습니다: {file_path}")
       return True
   print(f"쿠키 파일을 찾을 수 없습니다: {file_path}")
   return False

def login_with_cookies():
    try:
        driver = create_driver()
        cookies_path = "my_cookies.pkl"
        
        # 먼저 도메인에 접속 (쿠키 설정을 위해 필요)
        driver.get("https://www.tradingview.com/accounts/signin/")
        time.sleep(2)
        
        # 저장된 쿠키가 있다면 로드
        if load_cookies(driver, cookies_path):
            driver.refresh()  # 쿠키 적용을 위한 새로고침
            time.sleep(3)
            
            # 로그인 상태 확인
            if check_login_status(driver):
                logger.info("쿠키를 통한 로그인 성공")
                return driver
        return driver
        
    except Exception as e:
        logger.info(f"로그인 중 예외 발생: {e}")
        return None



# 스크린샷 캡쳐 및 base64 이미지 인코딩        
def capture_and_encode_screenshot(driver, type, save="no"):
    try:
        # 스크린샷 캡처
        png = driver.get_screenshot_as_png()
        
        # PIL Image로 변환
        img = Image.open(io.BytesIO(png))
        
        # 이미지 리사이즈 (OpenAI API 제한에 맞춤)
        img.thumbnail((2000, 2000))
        
        # 현재 시간을 파일명에 포함
        current_time = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{type}_chart_{current_time}.png"
        
        # 현재 스크립트의 경로를 가져옴
        script_dir = os.path.dirname(os.path.abspath(__file__))
        
        # 파일 저장 경로 설정
        file_path = os.path.join(script_dir, filename)
        
        # 이미지 파일로 저장
        if save == "yes":
            img.save(file_path)
            logger.info(f"스크린샷이 저장되었습니다: {file_path}")
        
        # 이미지를 바이트로 변환
        buffered = io.BytesIO()
        img.save(buffered, format="PNG")
        
        # base64로 인코딩
        base64_image = base64.b64encode(buffered.getvalue()).decode('utf-8')
        
        return base64_image, file_path
    except Exception as e:
        logger.error(f"스크린샷 캡처 및 인코딩 중 오류 발생: {e}")
        return None, None


def modify_orderbook(orderbook):
    # Convert timestamp to KST using timezone-aware method
    timestamp_ms = orderbook['timestamp']
    original_datetime = datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc)
    kst_datetime = original_datetime.astimezone(timezone(timedelta(hours=9)))
    
    # Modify the orderbook dictionary
    modified_orderbook = {
        'symbol': orderbook['symbol'],
        'bids': orderbook['bids'],
        'asks': orderbook['asks'],
        'timestamp': kst_datetime.strftime('%Y/%m/%d/%H:%M (KST)'),
        'nonce': orderbook['nonce']
    }
    
    return modified_orderbook





### 메인 AI 트레이딩 로직
def ai_trading():
    ### 데이터 가져오기
    # 1. 현재 투자 상태 조회
    # USDT 잔고 조회
    balance = trader.exchange.fetch_balance()
    usdt_balance = balance['USDT']
    free_usdt = usdt_balance['free']      # 사용 가능한 잔고
    used_usdt = usdt_balance['used']      # 주문에 묶인 잔고
    total_usdt = usdt_balance['total']    # 전체 잔고
    filtered_balances = [used_usdt, free_usdt]

    # 2. 오더북(호가 데이터) 조회
    orderbook = trader.exchange.fetch_order_book('BTC/USDT')
    modified_orderbook = modify_orderbook(orderbook)

    # 3. 차트 데이터 조회 및 보조지표 추가
    # df_daily = pyupbit.get_ohlcv("KRW-BTC", interval="day", count=30)
    # df_daily = dropna(df_daily)
    # df_daily = add_indicators(df_daily)
    

    # 바이낸스 5분봉 데이터 조회 (최근 2.5시간)
    df_5min = pd.DataFrame(
        trader.exchange.fetch_ohlcv(
            "BTC/USDT",
            timeframe='5m',
            limit=30
        ),
        columns=['timestamp', 'open', 'high', 'low', 'close', 'volume']
    )
    df_5min['timestamp'] = pd.to_datetime(df_5min['timestamp'], unit='ms').dt.tz_localize('UTC').dt.tz_convert('Asia/Seoul').dt.strftime('%Y/%m/%d %H:%M (KST)')
    df_5min = df_5min.set_index('timestamp')
    df_5min = dropna(df_5min)
    df_5min = add_indicators(df_5min)
    
    # 바이낸스 60분봉 데이터 조회 (최근 12시간)
    df_hourly = pd.DataFrame(
        trader.exchange.fetch_ohlcv(
            "BTC/USDT", 
            timeframe='1h',
            limit=12
        ),
        columns=['timestamp', 'open', 'high', 'low', 'close', 'volume']
    )
    df_hourly['timestamp'] = pd.to_datetime(df_hourly['timestamp'], unit='ms').dt.tz_localize('UTC').dt.tz_convert('Asia/Seoul').dt.strftime('%Y/%m/%d %H:%M (KST)')
    df_hourly = df_hourly.set_index('timestamp')
    df_hourly = dropna(df_hourly)
    df_hourly = add_indicators(df_hourly)



    # 4. 공포 탐욕 지수 가져오기
    fear_greed_index = get_fear_and_greed_index()

    # 5. 뉴스 헤드라인 가져오기
    news_headlines = get_bitcoin_news()

    # 6. YouTube 자막 데이터 가져오기
    f2 = open("strategy2.txt", "r", encoding="utf-8")
    youtube_transcript2 = f2.read()
    f2.close()    

    # 7. Selenium으로 차트 캡처
    driver = None
    try:
        # TradingView 차트 캡처
        driver = login_with_cookies()
        driver.get("https://kr.tradingview.com/chart/QYZJBUKS/?symbol=BINANCE%3ABTCUSDT.P")
        logger.info("TradingView 페이지 로드 완료")
        time.sleep(3)
        chart_image, saved_file_path2 = capture_and_encode_screenshot(driver, "tradingview", save="no")
        logger.info(f"TradingView 스크린샷 캡처 완료.")
    except WebDriverException as e:
        logger.error(f"캡쳐시 WebDriver 오류 발생: {e}")
        chart_image = None
    except Exception as e:
        logger.error(f"차트 캡처 중 오류 발생: {e}")
        chart_image = None        
    finally:
        if driver:
            driver.quit()
            # cleanup_chrome_processes()

    ### AI에게 데이터 제공하고 판단 받기
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    if not client.api_key:
        logger.error("OpenAI API key is missing or invalid.")
        return None
    try:
        # 데이터베이스 연결
        with sqlite3.connect('bitcoin_trades.db') as conn:
            # 최근 거래 내역 가져오기
            recent_trades = get_recent_trades(conn)
            
            # 현재 시장 데이터 수집 (기존 코드에서 가져온 데이터 사용)
            current_market_data = {
                "fear_greed_index": fear_greed_index,
                "news_headlines": news_headlines,
                "orderbook": modified_orderbook,
                "5min_ohlcv": df_5min.to_dict(),     # 2.5시간치 5분봉 데이터 추가
                "hourly_ohlcv": df_hourly.to_dict()  # 12시간치 60분봉 데이터 추가
            }
            # 반성 및 개선 내용 생성
            reflection = generate_reflection(recent_trades, current_market_data)
    
            # AI 모델에 반성 내용 제공
            response = client.chat.completions.create(
                model="gpt-4o-mini", #gpt-4o-2024-11-20
                messages=[
                    {
                        "role": "system",
                        "content": f"""You are a Bitcoin futures day trader who specializes in short-term trading based on 5-minute candlestick charts. You are trading two-way positions (buy or sell) and focus on analyzing 5-minute timeframes to identify quick market moves and opportunities while also considering the broader market conditions. You analyze the data provided to determine whether to take a buy(long), sell(short), or hold position at the current time. Consider the following when analyzing
                        
                        - Manage risk by only investing up to 65 percent of your assets in a single order
                        - Technical indicators and market data
                        - Focus on 5-minute chart patterns and movements for primary analysis, but use 60-minute data for medium-term trends
                        - Short-term price action and momentum
                        - Volume analysis on 5-minute timeframes
                        - Quick trend reversals and continuation patterns
                        - Support and resistance levels visible on 5-minute charts
                        - Recent news headlines and their immediate impact on Bitcoin price
                        - The Fear and Greed Index and its implications
                        - Overall market sentiment
                        - Patterns and trends visible in the chart image
                        - Recent trading performance and reflection

                        Recent trading reflection:
                        {reflection}

                        Particularly important is to always refer to the trading method below to help you assess your current situation and make trading decisions.

                        {youtube_transcript2}

                        You can find the BlackFlag FTS, UT Bot Alerts indicators, Volume Oscillator from the TradingView chart screenshot provided in the image of the user message. 
                        These technical indicators are essential for following the trading strategy outlined above.
                        "stop loss price" should be based on trading method above.
                        For optimal timing of entry, the occurrence of these three indicators should be recent on a 5-minute timeframe. otherwise, don't enter.
                        However, if other factors are sufficient reasons to enter a long(buy) or short(sell) position, you may trade.
                        because of the high fees associated with futures leverage, you shouldn't trade too often. Prioritize the entry signals from the three indicators.

                        Based on this trading method, analyze the current market situation and make a judgment by synthesizing it with the provided data and recent performance reflection.

                        Response format:
                        1. Decision (buy, sell, or hold)
                        2. If the decision is 'buy', provide a percentage (1-100) of available USDT to use for buying. and show stop_loss_price, P&L ratio.
                        If the decision is 'sell', provide a percentage (1-100) of held BTC/USDT to sell. and show stop_loss_price, P&L ratio.
                        If the decision is 'hold', set the percentage to 0.
                        3. Reason for your decision (it should include not only market situation and chart status, but also recent status or change of BlackFlag FTS, UT Bot Alerts, Volume Oscillator)

                        Ensure that the percentage is an integer between 1 and 100 for buy/sell decisions, and exactly 0 for hold decisions.
                        Your percentage should reflect the strength of your conviction in the decision based on the analyzed data.
                        Depending on the strength of the entry signal, P&L ratio should between 1.3~2 value  (default 1.5) 
                        """
                    },
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": f"""Current investment status: {json.dumps(filtered_balances)}
                                Orderbook: {json.dumps(modified_orderbook)}
                                5-minute OHLCV with indicators (30 days): {df_5min.to_json()}
                                Hourly OHLCV with indicators (24 hours): {df_hourly.to_json()}
                                Recent news headlines: {json.dumps(news_headlines)}
                                Fear and Greed Index: {json.dumps(fear_greed_index)}"""
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/png;base64,{chart_image}"
                                }
                            }
                        ]
                    }
                ],
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "trading_decision",
                        "strict": True,
                        "schema": {
                            "type": "object",
                            "properties": {
                                "decision": {"type": "string", "enum": ["buy", "sell", "hold"]},
                                "percentage": {"type": "integer"},
                                "reason": {"type": "string"},
                                "stop_loss_price": {"type": "integer"},
                                "pl_ratio": {"type": "number"}
                            },
                            "required": ["decision", "percentage", "reason", "stop_loss_price", "pl_ratio"],
                            "additionalProperties": False
                        }
                    }
                },
                max_tokens=4095
            )

            # Pydantic을 사용하여 AI의 트레이딩 결정 구조를 정의
            try:
                result = TradingDecision.model_validate_json(response.choices[0].message.content)
            except Exception as e:
                logger.error(f"Error parsing AI response: {e}")
                return

            logger.info(f"### AI Decision: {result.decision.upper()} ###")
            logger.info(f"### Reason: {result.reason} ###")

            order_executed = False
            order_info = None  # 변수 초기화 추가
        try:
            # 현재가 조회
            ticker = trader.exchange.fetch_ticker('BTC/USDT')
            current_btc_price = ticker['last']
            
            # 계좌 잔고 조회
            balance = trader.exchange.fetch_balance()
            total_balance = float(balance['USDT']['free'])
            
            # 주문 금액 계산 (수수료 고려)
            order_amount = total_balance * (result.percentage / 100) * 0.9996
            if result.decision == "buy":
                # 롱 포지션 진입
                order_info = trader.market_order_with_tp_sl(
                    side='buy',
                    buy_amount=order_amount,
                    pl_ratio=result.pl_ratio,
                    sl_price=result.stop_loss_price
                )
                
                if order_info != None:
                    logger.info(f"롱 포지션 진입: 금액={order_amount}, P&L ratio={result.pl_ratio}, SL={result.stop_loss_price}")
                    order_executed = True
                    
            elif result.decision == "sell":
                # 숏 포지션 진입
                order_info = trader.market_order_with_tp_sl(
                    side='sell',
                    buy_amount=order_amount,
                    pl_ratio=result.pl_ratio,
                    sl_price=result.stop_loss_price
                )
                
                if order_info != None:
                    logger.info(f"숏 포지션 진입: 금액={order_amount}, P&L ratio={result.pl_ratio}, SL={result.stop_loss_price}")
                    order_executed = True
                    
        except Exception as e:
            logger.error(f"주문 실행 중 오류 발생: {str(e)}")
            raise
            
        # 거래 실행 여부와 관계없이 현재 잔고 조회
        time.sleep(2)  # API 호출 제한을 고려하여 잠시 대기
        balance = trader.exchange.fetch_balance()
        usdt_balance = balance['USDT']
        free_usdt = usdt_balance['free']    # 사용 가능한 잔고
        used_usdt = usdt_balance['used']    # 주문에 묶인 잔고
        total_usdt = usdt_balance['total']  # 전체 잔고
        # 현재 포지션 정보 조회
        try:
            positions = trader.exchange.fetch_positions([trader.symbol])
            if positions and len(positions) > 0:
                position = positions[0]  # BTC/USDT 포지션
                btc_avg_buy_price = float(position['entryPrice']) 
                position_size = float(position['contracts'])
            else:
                btc_avg_buy_price = 0
                position_size = 0
        except Exception as e:
            logger.error(f"Error fetching position: {e}")
            btc_avg_buy_price = 0 
            position_size = 0
        # BTC/USDT 현재가 조회
        ticker = trader.exchange.fetch_ticker('BTC/USDT')
        current_btc_price = ticker['last']

        # 거래 기록을 DB에 저장하기
        if order_executed and order_info != None:
            order_id = order_info['entry']['id']
            log_trade(conn, 'AI', order_id, result.decision, result.percentage, result.reason, 
                used_usdt, free_usdt, total_usdt, btc_avg_buy_price, current_btc_price, reflection)
        
            # 트레일링 스탑로스 모니터링 추가
            if 'monitor_sl' in order_info:
                def periodic_sl_monitoring():
                    new_sl_order = order_info['monitor_sl']()
                    if new_sl_order:
                        # 필요하다면 추가 로직 구현
                        logger.info(f"Trailing SL order updated: {new_sl_order}")
                        
                # 5분마다 SL 모니터링
                schedule.every(5).minutes.do(periodic_sl_monitoring)
                
        else:
            # 거래가 실행되지 않은 경우 (hold 또는 실패)
            log_trade(conn, 'AI', None, result.decision, 0, result.reason, 
                    used_usdt, free_usdt, total_usdt, btc_avg_buy_price, current_btc_price, reflection)
    
    
    
    
    except sqlite3.Error as e:
        logger.error(f"Database connection error: {e}")
        return























if __name__ == "__main__":
    logger.info("Hello, Mingu !!")
    logger.info("Starting trading bot ...")
    try:
        # 시작할 때도 크롬 프로세스 한번 정리
        cleanup_chrome_processes()

        # 프로그램 시작 시 핸들러 등록
        signal.signal(signal.SIGINT, signal_handler)   # Ctrl+C
        signal.signal(signal.SIGTERM, signal_handler)  # 종료 시그널
        atexit.register(cleanup_handler)              # 정상 종료 시

        # 데이터베이스 초기화
        init_db()

        # 중복 실행 방지를 위한 변수들
        trading_in_progress = False
        monitoring_in_progress = False
        
        # AI 트레이딩 작업을 수행하는 함수
        def trading_job():
            global trading_in_progress
            if trading_in_progress:
                logger.warning("Trading job is already in progress, skipping this run")
                return
            try:
                trading_in_progress = True
                ai_trading()
            except Exception as e:
                logger.error(f"An error occurred in trading job: {e}")
            finally:
                trading_in_progress = False

        # 수동 거래 모니터링 작업을 수행하는 함수
        def monitoring_job():
            global monitoring_in_progress
            if monitoring_in_progress:
                logger.warning("Monitoring job is already in progress, skipping this run")
                return
            try:
                monitoring_in_progress = True
                trader.monitor_manual_trades()
            except Exception as e:
                logger.error(f"An error occurred in monitoring job: {e}")
            finally:
                monitoring_in_progress = False

        # 초기 실행
        trading_job()
        monitoring_job()

        # AI 트레이딩 스케줄 설정
        # for hour in [21, 22, 23, 0, 1]:
        #     for minute in range(0, 60, 15):
        #         schedule.every().day.at(f"{hour:02d}:{minute:02d}").do(trading_job)
        # schedule.every().day.at("02:00").do(trading_job)

        # for hour in [4, 5, 6]:
        #     for minute in range(0, 60, 15):
        #         schedule.every().day.at(f"{hour:02d}:{minute:02d}").do(trading_job)
        # schedule.every().day.at("07:00").do(trading_job)

        # for hour in [15, 16, 17]:
        #     for minute in range(0, 60, 15):
        #         schedule.every().day.at(f"{hour:02d}:{minute:02d}").do(trading_job)
        # schedule.every().day.at("18:00").do(trading_job)
        
        # AI 트레이딩 스케줄 설정 (5분마다 실행)
        schedule.every(5).minutes.do(trading_job) # GPT-4o-mini를 사용하여 비용 절감, 더 자주 트레이딩 수행


        # 수동 거래 모니터링 스케줄 설정 (1분마다 실행)
        schedule.every(1).minutes.do(monitoring_job)

        # 스케줄러 실행
        while True:
            schedule.run_pending()
            time.sleep(1)
            
    except Exception as e:
        logger.error(f"Critical error occurred: {e}")
        cleanup_chrome_processes()
    finally:
        cleanup_chrome_processes()
