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
import platform




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
        """
        주문이 AI 거래인지 판별하는 함수
        
        Args:
            order: 바이낸스 주문 객체
            last_ai_entry: DB에서 조회한 가장 최근 AI 거래 정보 (order_id, timestamp)
        
        Returns:
            bool: AI 거래 여부
        """
        if not last_ai_entry:
            return False
        
        # 기본 주문 정보 확인
        order_id = str(order['id'])
        client_order_id = order['clientOrderId']
        
        # 1. AI가 생성한 주문 ID 패턴 확인 
        if client_order_id and (
            client_order_id.startswith('tp_') or 
            client_order_id.startswith('sl_') or 
            client_order_id == str(last_ai_entry[0])
        ):
            return True
        
        # 2. 최근 AI 엔트리 주문과 동일한 order_id 확인
        if order_id == str(last_ai_entry[0]):
            return True
        
        return False

    def _handle_position_reduction(self, current_position, side, buy_amount, current_price):
        """포지션 축소/청산을 위한 수량 계산"""
        position_size = float(current_position['contracts'])
        position_notional = float(current_position['notional'])
        
        # 주문 비율 계산
        reduction_ratio = buy_amount / position_notional
        quantity = position_size * reduction_ratio
        
        # 남은 포지션 크기 계산
        remaining_size = position_size - quantity
        
        # 최소 주문 수량 (0.001 BTC)
        MIN_ORDER_SIZE = 0.001
        
        # 남은 수량이 최소 주문 수량보다 작으면 전체 청산
        if remaining_size < MIN_ORDER_SIZE:
            self.logger.info(f"Remaining position ({remaining_size} BTC) would be below minimum size. Will close entire position.")
            quantity = position_size

        return quantity

    def _handle_position_increase(self, current_position, side, buy_amount, current_price,
                                    sl_price, tp_price, pl_ratio, min_order_value):
        """같은 방향 추가 진입 처리 - SL 가격만 업데이트"""
        # 레버리지 적용된 수량 계산
        leveraged_amount = buy_amount * self.leverage
        quantity = leveraged_amount / current_price

        # 최소 주문 금액 확인
        if quantity * current_price < min_order_value:
            self.logger.error(f"Order value too small: {quantity * current_price} USDT")
            return None

        # 기존 SL 주문 조회
        try:
            open_orders = self.exchange.fetch_open_orders(self.symbol)
            existing_sl_order = None
            existing_tp_order = None
            
            for order in open_orders:
                if order['info']['origType'] == 'STOP_MARKET' and order['type'] == 'market':
                    existing_sl_order = order
                elif order['info']['origType'] == 'TAKE_PROFIT_MARKET' and order['type'] == 'market':
                    existing_tp_order = order
                    
            if existing_sl_order:
                # 기존 SL 주문만 취소
                try:
                    self.exchange.cancel_order(existing_sl_order['id'], self.symbol)
                    self.logger.info(f"Cancelled existing SL order: {existing_sl_order['id']}")
                    time.sleep(0.5)  # API 제한 고려
                except Exception as e:
                    self.logger.error(f"Error cancelling existing SL order: {e}")
                    return None

        except Exception as e:
            self.logger.error(f"Error fetching existing orders: {e}")
            return None

        # 새로운 total position size 계산
        total_position_size = quantity + float(current_position['contracts'])

        # 기존 TP 가격 유지 (존재하는 경우)
        if existing_tp_order:
            tp_price = float(existing_tp_order['info'].get('stopPrice', existing_tp_order.get('price', 0)))
        
        # SL 가격만 업데이트
        if side == 'buy':
            if sl_price >= current_price:
                sl_price = current_price * 0.998  # 0.2% 아래로 설정
        else:  # sell
            if sl_price <= current_price:
                sl_price = current_price * 1.002  # 0.2% 위로 설정

        return tp_price, sl_price  


    def get_active_ai_positions(self):
        """현재 활성화된 모든 AI 포지션 ID 조회"""
        try:
            conn = sqlite3.connect('bitcoin_trades.db')
            c = conn.cursor()
            c.execute("""
                SELECT order_id, decision 
                FROM trades 
                WHERE trade_type = 'AI' 
                AND decision != 'hold'
                AND timestamp >= (
                    SELECT COALESCE(
                        (SELECT timestamp 
                        FROM trades 
                        WHERE reason LIKE '%Close%' 
                        ORDER BY timestamp DESC 
                        LIMIT 1),
                        '1970-01-01'  -- 청산 기록이 없는 경우 가장 오래된 날짜 사용
                    )
                )
                ORDER BY timestamp DESC
            """)
            return c.fetchall()
        except Exception as e:
            self.logger.error(f"Error fetching active AI positions: {e}")
            return []
        finally:
            if 'conn' in locals():
                conn.close()

        # 수동 거래 모니터링
    def monitor_manual_trades(self):
        try:
            since = int((datetime.now() - timedelta(minutes=5)).timestamp() * 1000)
            since_datetime = datetime.fromtimestamp(since/1000)
            self.logger.info(f"Monitoring trades since: {since_datetime}")

            # 활성화된 AI 포지션 조회
            active_ai_positions = self.get_active_ai_positions()
            self.logger.info(f"Active AI positions: {active_ai_positions}")

            # 초기 데이터 한 번만 조회
            try:
                balance = self.exchange.fetch_balance()
                positions = self.exchange.fetch_positions([self.symbol])
                ticker = self.exchange.fetch_ticker(self.symbol)
                
                usdt_balance = balance['USDT']
                free_usdt = usdt_balance['free']
                used_usdt = usdt_balance['used'] 
                total_usdt = usdt_balance['total']
                
                current_position = next((pos for pos in positions if float(pos.get('contracts', 0) or 0) != 0), None)
                btc_avg_buy_price = float(current_position['entryPrice']) if current_position else 0
                current_btc_price = ticker['last']
            except Exception as e:
                self.logger.error(f"Error fetching initial market data: {e}")
                return

            # 주문 가져오기
            orders = self.exchange.fetch_orders(self.symbol, since=since, limit=100)
            self.logger.info(f"Fetched {len(orders)} orders")
            
            # 디버깅용 로그
            for order in orders:
                self.logger.info(f"Order Details: ID={order['id']}, "
                            f"ClientID={order.get('clientOrderId', 'N/A')}, "
                            f"Type={order['info'].get('origType', 'N/A')}, "
                            f"Market={order['type']}, "
                            f"Status={order['status']}, "
                            f"Filled={order['filled']}")
                
            # TP/SL 실현 주문 필터링
            realized_tp_orders = [order for order in orders 
                        if ((order['info'].get('origType') == 'TAKE_PROFIT_MARKET' or 
                            (order.get('clientOrderId', '') or '').startswith('tp_')) 
                            and order['type'] == 'market'
                            and order['status'] == 'closed'
                            and order['filled'] > 0)]

            realized_sl_orders = [order for order in orders 
                        if ((order['info'].get('origType') == 'STOP_MARKET' or 
                            (order.get('clientOrderId', '') or '').startswith('sl_'))
                            and order['type'] == 'market'
                            and order['status'] == 'closed'
                            and order['filled'] > 0)]

            self.logger.info(f"Found {len(realized_tp_orders)} TP and {len(realized_sl_orders)} SL orders")

            # parent_id로 매핑
            tp_orders_by_parent = {}
            sl_orders_by_parent = {}
            
            for order in realized_tp_orders:
                client_order_id = order.get('clientOrderId', '')
                if client_order_id and client_order_id.startswith('tp_'):
                    parent_id = client_order_id.split('_')[-1]
                else:
                    parent_id = order['id']
                tp_orders_by_parent[parent_id] = order
                self.logger.info(f"Mapped TP order: {order['id']} for parent {parent_id}")

            for order in realized_sl_orders:
                client_order_id = order.get('clientOrderId', '')
                if client_order_id and client_order_id.startswith('sl_'):
                    parent_id = client_order_id.split('_')[-1]
                else:
                    parent_id = order['id']
                sl_orders_by_parent[parent_id] = order
                self.logger.info(f"Mapped SL order: {order['id']} for parent {parent_id}")

            # 처리된 주문 ID 추적을 위한 set
            processed_orders = set()

            conn = sqlite3.connect('bitcoin_trades.db')
            c = conn.cursor()
            
            def get_last_reflection(conn):
                """DB에서 가장 최근 reflection 값을 가져오는 함수"""
                try:
                    c = conn.cursor()
                    c.execute("""
                        SELECT reflection FROM trades
                        WHERE reflection IS NOT NULL AND reflection != ''
                        ORDER BY timestamp DESC
                        LIMIT 1
                    """)
                    result = c.fetchone()
                    return result[0] if result else None
                except Exception as e:
                    logger.error(f"Error fetching last reflection: {e}")
                    return None            
                        
            
            try:
                def process_tp_sl_order(order, is_tp=True):
                    """TP/SL 주문 처리 함수"""
                    try:
                        order_id = str(order['id'])
                        if order_id in processed_orders:
                            return
                            
                        # 중복 체크
                        c.execute("SELECT id FROM trades WHERE order_id = ?", (order_id,))
                        if c.fetchone():
                            self.logger.info(f"Skipping duplicate order: {order_id}")
                            return

                        self.logger.info(f"Processing {'TP' if is_tp else 'SL'} order: {order_id}")
                        
                        order_timestamp = datetime.fromtimestamp(order['lastUpdateTimestamp']/1000).isoformat()
                        
                        # AI 주문 여부 확인
                        client_order_id = order.get('clientOrderId', '')
                        is_ai_order = False
                        if client_order_id and client_order_id.startswith(('tp_', 'sl_')):
                            parent_id = client_order_id.split('_')[-1]
                            is_ai_order = any(str(pos_id) == parent_id for pos_id, _ in active_ai_positions)
                            self.logger.info(f"TP/SL order for parent {parent_id}: {'AI' if is_ai_order else 'Manual'} position")
                        
                        trade_type = 'AI' if is_ai_order else 'MANUAL'
                        reason = (f"AI {('TP' if is_tp else 'SL')} Realized" if is_ai_order 
                                else f"Manual {('TP' if is_tp else 'SL')} Realized")
                        
                        decision = 'sell' if order['side'] == 'sell' else 'buy'
                        
                        # 거래 비율 계산
                        actual_trade_amount = abs(order['cost']) / self.leverage
                        trade_percentage = (actual_trade_amount / total_usdt) * 100 if total_usdt > 0 else 0

                        # 마지막 reflection 유지
                        last_reflection = get_last_reflection(conn)

                        # DB 기록
                        c.execute("""
                            INSERT INTO trades 
                            (timestamp, trade_type, order_id, decision, percentage, reason, 
                            btc_balance, usdt_balance, total_assets, btc_avg_buy_price, btc_current_price,
                            reflection, tp_order_id, sl_order_id) 
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (
                            order_timestamp, trade_type, order_id, decision,
                            int(trade_percentage), reason,
                            used_usdt, free_usdt, total_usdt,
                            btc_avg_buy_price, current_btc_price,
                            last_reflection,  # 기존 reflection을 유지
                            order_id if reason == 'AI TP Realized' else None,
                            order_id if reason == 'AI SL Realized' else None
                        ))                        
                                                
                        conn.commit()
                        processed_orders.add(order_id)
                        self.logger.info(f"Recorded {trade_type} trade: {order_id}")
                    except Exception as e:
                        self.logger.error(f"Error processing TP/SL order {order.get('id')}: {e}")
                        self.logger.error(f"Order details: {json.dumps(order, indent=2)}")

                def process_market_order(order):
                    """일반 거래 처리 함수"""
                    try:
                        order_id = str(order['id'])
                        if order_id in processed_orders:
                            return
                            
                        # 중복 체크
                        c.execute("SELECT id FROM trades WHERE order_id = ?", (order_id,))
                        if c.fetchone():
                            return

                        order_timestamp = datetime.fromtimestamp(order['lastUpdateTimestamp']/1000).isoformat()
                        
                        # TP/SL 주문 확인
                        tp_order = tp_orders_by_parent.get(order_id)
                        sl_order = sl_orders_by_parent.get(order_id)
                        is_reduce_only = order.get('info', {}).get('reduceOnly', False)

                        # AI 포지션 체크
                        is_ai_entry = False
                        ai_position_decision = None
                        
                        # ClientOrderId로 AI 주문 여부 확인
                        client_order_id = order.get('clientOrderId', '')
                        parent_id = None
                        if client_order_id:
                            if client_order_id.startswith(('tp_', 'sl_')):
                                parent_id = client_order_id.split('_')[-1]
                        
                        if parent_id:
                            for pos_id, decision in active_ai_positions:
                                if str(pos_id) == parent_id:
                                    is_ai_entry = True
                                    ai_position_decision = decision
                                    break
                        else:
                            for pos_id, decision in active_ai_positions:
                                if str(pos_id) == order_id:
                                    is_ai_entry = True
                                    ai_position_decision = decision
                                    break

                        # 거래 유형 판별
                        if is_ai_entry:
                            if not is_reduce_only:
                                trade_type = 'AI'
                                reason = 'AI Entry'
                            else:
                                if tp_order:
                                    trade_type = 'AI'
                                    reason = 'AI TP Realized'
                                elif sl_order:
                                    trade_type = 'AI'
                                    reason = 'AI SL Realized'
                                else:
                                    return
                        else:
                            if is_reduce_only:
                                # 포지션 종료 케이스 분석
                                trade_type = 'MANUAL'
                                
                                # 1. TP/SL 주문인지 먼저 확인
                                client_order_id = order.get('clientOrderId', '')
                                if client_order_id and client_order_id.startswith(('tp_', 'sl_')):
                                    # 2. parent_id를 통해 AI 포지션과 연관되어 있는지 확인
                                    parent_id = client_order_id.split('_')[-1]
                                    is_ai_tp_sl = any(str(pos_id) == parent_id for pos_id, _ in active_ai_positions)
                                    reason = 'Manual Close of AI Position' if is_ai_tp_sl else 'Manual Close of AI Position'
                                    self.logger.info(f"TP/SL order for parent {parent_id}: {'AI' if is_ai_tp_sl else 'Manual'} position")
                                else:
                                    # 3. 일반 청산 주문인 경우
                                    for pos_id, ai_decision in active_ai_positions:
                                        is_closing_ai_position = (
                                            (ai_decision == 'buy' and order['side'] == 'sell') or 
                                            (ai_decision == 'sell' and order['side'] == 'buy')
                                        )
                                        if is_closing_ai_position:
                                            reason = 'Manual Close of AI Position'
                                            self.logger.info(f"Manual close of AI position: {pos_id}")
                                            break
                                    else:
                                        reason = 'Manual Close of AI Position'
                            else:
                                trade_type = 'MANUAL'
                                if tp_order:
                                    reason = 'Manual TP Realized'
                                elif sl_order:
                                    reason = 'Manual SL Realized'
                                else:
                                    reason = 'Manual Entry'

                        decision = 'buy' if order['side'] == 'buy' else 'sell'
                        
                        # 거래 비율 계산
                        actual_trade_amount = abs(order['cost']) / self.leverage
                        trade_percentage = (actual_trade_amount / total_usdt) * 100 if total_usdt > 0 else 0

                        # TP/SL 주문 ID
                        tp_order_id = tp_order['id'] if tp_order else None
                        sl_order_id = sl_order['id'] if sl_order else None

                        # 마지막 reflection 유지
                        last_reflection = get_last_reflection(conn)

                        # DB 기록
                        c.execute("""
                            INSERT INTO trades 
                            (timestamp, trade_type, order_id, decision, percentage, reason, 
                            btc_balance, usdt_balance, total_assets, btc_avg_buy_price, btc_current_price,
                            reflection, tp_order_id, sl_order_id) 
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (
                            order_timestamp, trade_type, order_id, decision,
                            int(trade_percentage), reason,
                            used_usdt, free_usdt, total_usdt,
                            btc_avg_buy_price, current_btc_price,
                            last_reflection,  # 기존 reflection을 유지
                            tp_order_id, sl_order_id
                        ))
                        conn.commit()
                        processed_orders.add(order_id)
                        self.logger.info(f"{trade_type} trade recorded: {decision.upper()} at {current_btc_price} (Reason: {reason})")
                        
                    except Exception as e:
                        self.logger.error(f"Error processing market order {order.get('id')}: {e}")
                        self.logger.error(f"Order details: {json.dumps(order, indent=2)}")

                # 메인 처리 로직 실행
                for tp_order in realized_tp_orders:
                    process_tp_sl_order(tp_order, True)
                for sl_order in realized_sl_orders:
                    process_tp_sl_order(sl_order, False)
                
                # 일반 거래 처리 (TP/SL 제외)
                for order in orders:
                    if order['type'] == 'market' and str(order['id']) not in processed_orders:
                        process_market_order(order)
                        
            finally:
                conn.close()
                self.logger.info("Database connection closed")
                            
        except Exception as e:
            self.logger.error(f"Error monitoring trades: {e}")
            if 'conn' in locals():
                conn.close()
                self.logger.info("Database connection closed after error")

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





    def _calculate_weighted_sl_price(self, position_size, position_sl_price, new_size, new_sl_price):
        """가중 평균 스탑로스 가격 계산"""
        total_size = position_size + new_size
        weighted_sl = ((position_size * position_sl_price) + (new_size * new_sl_price)) / total_size
        return weighted_sl

    def market_order_with_tp_sl(self, side: str, buy_amount: float, pl_ratio: float, sl_price: float):
        """
        시장가 주문과 TP/SL 설정을 처리하는 함수

        Args:
            side (str): 'buy' 또는 'sell'
            buy_amount (float): 주문 금액 (USDT)
            pl_ratio (float): 수익률 비율
            sl_price (float): 스탑로스 가격
        """
        # 상수 정의
        SAFETY_MARGIN = 0.002      # 안전 마진 (0.2%)
        TRAILING_THRESHOLD = 0.004 # 트레일링 시작 기준 수익률 (0.4%)
        TRAILING_BUFFER = 0.0012   # 트레일링 버퍼 (0.12%)
        MINIMUM_ORDER_VALUE = 10   # 최소 주문 금액 (USDT)
        MIN_PRICE_DIFF = 0.001     # 최소 가격 차이 (0.1%)
        MAX_BALANCE_USE = 0.80     # 최대 사용 가능 잔고 비율 (80%)
        API_DELAY = 0.5            # API 호출 후 대기 시간

        def cancel_orders(orders_to_cancel):
            """TP/SL 주문 취소 헬퍼 함수"""
            for o in orders_to_cancel:
                try:
                    self.exchange.cancel_order(o['id'], self.symbol)
                    self.logger.info(f"Cancelled order: {o['id']} (ClientOrderId={o.get('clientOrderId','')})")
                except Exception as e:
                    self.logger.error(f"Error cancelling order {o['id']}: {e}")
                time.sleep(API_DELAY)

        # 1. 현재가 조회 및 TP/SL 가격 계산
        try:
            ticker = self.exchange.fetch_ticker(self.symbol)
            current_price = ticker['last']

            # TP/SL 가격 보정
            min_price_diff_val = current_price * MIN_PRICE_DIFF

            if side == 'buy':
                if sl_price >= current_price or (current_price - sl_price) < min_price_diff_val:
                    sl_price = current_price * (1 - SAFETY_MARGIN)
                    self.logger.warning(f"Invalid SL price for long position. Adjusted to {sl_price}")

                tp_price = current_price + pl_ratio * (current_price - sl_price)
                if tp_price <= current_price or (tp_price - current_price) < pl_ratio * min_price_diff_val:
                    tp_price = current_price * (1 + SAFETY_MARGIN)
                    self.logger.warning(f"Invalid TP price for long position. Adjusted to {tp_price}")

            else:  # side == 'sell'
                if sl_price <= current_price or (sl_price - current_price) < min_price_diff_val:
                    sl_price = current_price * (1 + SAFETY_MARGIN)
                    self.logger.warning(f"Invalid SL price for short position. Adjusted to {sl_price}")

                tp_price = current_price - pl_ratio * (sl_price - current_price)
                if tp_price >= current_price or (current_price - tp_price) < pl_ratio * min_price_diff_val:
                    tp_price = current_price * (1 - SAFETY_MARGIN)
                    self.logger.warning(f"Invalid TP price for short position. Adjusted to {tp_price}")

        except Exception as e:
            self.logger.error(f"Error calculating prices: {e}")
            return None

        # 2. 현재 포지션 확인
        try:
            positions = self.exchange.fetch_positions([self.symbol])
            current_position = None
            position_side = None
            for pos in positions:
                if float(pos.get('contracts', 0) or 0) != 0:
                    current_position = pos
                    position_side = pos['side']
                    break
        except Exception as e:
            self.logger.error(f"Error fetching positions: {e}")
            return None

        # 3. 신규 포지션 진입을 위한 잔고 확인 및 주문 수량 계산
        try:
            is_reduction = False
            if current_position and ((position_side == 'long' and side == 'sell') or (position_side == 'short' and side == 'buy')):
                is_reduction = True

            if is_reduction:
                # 반대 방향 축소(reduction)일 경우
                quantity = (buy_amount * self.leverage) / current_price
                # 최소 주문 금액 체크
                if quantity * current_price < MINIMUM_ORDER_VALUE:
                    self.logger.error(f"Partial reduction order value too small: {quantity * current_price} USDT")
                    return None
            else:
                balance = self.exchange.fetch_balance()
                available_balance = float(balance['USDT']['free'])
                if available_balance < MINIMUM_ORDER_VALUE:
                    self.logger.error(f"Insufficient balance: {available_balance} USDT")
                    return None
                max_safe_amount = available_balance * MAX_BALANCE_USE
                if buy_amount > max_safe_amount:
                    buy_amount = max_safe_amount
                    self.logger.warning(f"Order amount adjusted to {buy_amount} USDT")

                quantity = (buy_amount * self.leverage) / current_price
                if quantity * current_price < MINIMUM_ORDER_VALUE:
                    self.logger.error(f"Order value too small: {quantity * current_price} USDT")
                    return None
                min_amount = self.exchange.markets[self.symbol]['limits']['amount']['min']
                if quantity < min_amount:
                    self.logger.error(f"Order quantity too small: {quantity}")
                    return None
        except Exception as e:
            self.logger.error(f"Error calculating order quantity: {e}")
            return None

        # 4. TP/SL 주문 관리 및 포지션 주문 실행
        order = None
        tp_order = None
        sl_order = None
        is_full_reduction = False

        try:
            # 현재 열린 주문 조회
            open_orders = self.exchange.fetch_open_orders(self.symbol)

            # clientOrderId가 'tp_'로 시작하면 TP 주문, 'sl_'로 시작하면 SL 주문으로 간주
            tp_orders = [o for o in open_orders if o.get('clientOrderId','').startswith('tp_')]
            sl_orders = [o for o in open_orders if o.get('clientOrderId','').startswith('sl_')]

            if current_position and position_side:
                # A. 같은 방향 추가 진입
                if side == position_side:
                    if sl_orders:
                        cancel_orders(sl_orders)

                # B. 반대 방향 축소
                elif ((position_side == 'long' and side == 'sell') or 
                    (position_side == 'short' and side == 'buy')):
                    is_full_reduction = quantity >= float(current_position['contracts'])
                    if is_full_reduction:
                        # 전량 청산 시에만 TP/SL 모두 취소
                        if tp_orders:
                            cancel_orders(tp_orders)
                        if sl_orders:
                            cancel_orders(sl_orders)
                        quantity = float(current_position['contracts'])
                    else:
                        # 부분 청산 시 기존 TP/SL 유지
                        tp_order = None
                        sl_order = None
            else:
                # C. 신규 진입
                # 기존 TP/SL 주문이 있다면 모두 취소
                if tp_orders:
                    cancel_orders(tp_orders)
                if sl_orders:
                    cancel_orders(sl_orders)

            # 포지션 주문 실행 (시장가)
            order = self.exchange.create_market_order(
                symbol=self.symbol,
                side=side,
                amount=quantity
            )
            entry_price = current_price

            # TP/SL 주문 생성 (신규 진입 또는 동일 방향 추가 진입)
            # 반대 방향 축소인 경우에는 이미 TP/SL 유지/폐기 결정 완료
            if not (current_position and position_side and 
                    ((position_side == 'long' and side == 'sell') or 
                    (position_side == 'short' and side == 'buy'))):
                tp_side = 'sell' if side == 'buy' else 'buy'
                
                # 신규 진입이면 TP 생성
                if not current_position:
                    tp_order = self.exchange.create_order(
                        symbol=self.symbol,
                        type='TAKE_PROFIT_MARKET',
                        side=tp_side,
                        amount=quantity,
                        params={
                            'stopPrice': tp_price,
                            'closePosition': True,
                            'clientOrderId': f"tp_{order['id']}"
                        }
                    )

                # SL은 무조건 새로 생성
                sl_order = self.exchange.create_order(
                    symbol=self.symbol,
                    type='STOP_MARKET',
                    side=tp_side,
                    amount=quantity,
                    params={
                        'stopPrice': sl_price,
                        'closePosition': True,
                        'clientOrderId': f"sl_{order['id']}"
                    }
                )

            # 주문 성공 여부 확인
            if not order:
                raise Exception("Main order creation failed")

        except Exception as e:
            self.logger.error(f"Error in order execution: {e}")
            # 롤백 처리
            if order:
                try:
                    self.exchange.cancel_order(order['id'], self.symbol)
                    self.logger.info("Cancelled main order during rollback")
                except Exception as cancel_error:
                    self.logger.error(f"Error cancelling main order during rollback: {cancel_error}")

            if tp_order:
                try:
                    self.exchange.cancel_order(tp_order['id'], self.symbol)
                    self.logger.info("Cancelled TP order during rollback")
                except Exception as cancel_error:
                    self.logger.error(f"Error cancelling TP order during rollback: {cancel_error}")

            if sl_order:
                try:
                    self.exchange.cancel_order(sl_order['id'], self.symbol)
                    self.logger.info("Cancelled SL order during rollback")
                except Exception as cancel_error:
                    self.logger.error(f"Error cancelling SL order during rollback: {cancel_error}")

            return None

        # 5. 트레일링 스탑로스 모니터링 함수 정의
        def monitor_and_adjust_sl():
            try:
                positions_ = self.exchange.fetch_positions([self.symbol])
                current_pos = next((p for p in positions_ if float(p.get('contracts', 0) or 0) != 0), None)

                if not current_pos:
                    return None

                current_market_price = self.exchange.fetch_ticker(self.symbol)['last']
                position_size = float(current_pos['contracts'])
                pos_side = current_pos['side']

                # 수익률 계산
                profit_percentage = (current_market_price - entry_price) / entry_price if pos_side == 'long' \
                                    else (entry_price - current_market_price) / entry_price

                if profit_percentage >= TRAILING_THRESHOLD:
                    # 새로운 SL 가격 계산
                    new_sl_price = current_market_price * (1 - TRAILING_BUFFER) if pos_side == 'long' \
                                else current_market_price * (1 + TRAILING_BUFFER)

                    # 기존 SL 주문 취소 (clientOrderId로 식별)
                    try:
                        open_orders_ = self.exchange.fetch_open_orders(self.symbol)
                        existing_sl = [o for o in open_orders_ if o.get('clientOrderId','').startswith('sl_')]
                        cancel_orders(existing_sl)

                        # 새 SL 주문 생성
                        t_side = 'sell' if pos_side == 'long' else 'buy'
                        new_sl_order = self.exchange.create_order(
                            symbol=self.symbol,
                            type='STOP_MARKET',
                            side=t_side,
                            amount=position_size,
                            params={
                                'stopPrice': new_sl_price,
                                'closePosition': True,
                                'clientOrderId': f"sl_{order['id']}"
                            }
                        )
                        self.logger.info(f"Trailing SL updated: {new_sl_price}")
                        return new_sl_order

                    except Exception as e_:
                        self.logger.error(f"Error updating trailing SL: {e_}")
                        return None

            except Exception as e_:
                self.logger.error(f"Error in SL monitoring: {e_}")
                return None

        self.logger.info(f"Position opened - Side: {side}, Amount: {buy_amount} USDT")
        return {
            'entry': order,
            'tp': tp_order,
            'sl': sl_order,
            'monitor_sl': monitor_and_adjust_sl,
            'entry_price': entry_price
        }

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
                  reflection TEXT,
                  tp_order_id TEXT,
                  sl_order_id TEXT)''')
    conn.commit()
    return conn

# 거래 기록을 DB에 저장하는 함수

# 거래 기록 함수 수정
def log_trade(conn, trade_type, order_id, decision, percentage, reason, btc_balance, 
              usdt_balance, total_assets, btc_avg_buy_price, btc_current_price, 
              reflection='', tp_order_id=None, sl_order_id=None):
    c = conn.cursor()
    timestamp = datetime.now().isoformat()
    c.execute("""INSERT INTO trades 
                 (timestamp, trade_type, order_id, decision, percentage, reason, 
                 btc_balance, usdt_balance, total_assets, btc_avg_buy_price, 
                 btc_current_price, reflection, tp_order_id, sl_order_id) 
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
              (timestamp, trade_type, order_id, decision, percentage, reason, 
               btc_balance, usdt_balance, total_assets, btc_avg_buy_price, 
               btc_current_price, reflection, tp_order_id, sl_order_id))
    conn.commit()
    
# 최근 투자 기록 조회
# def get_recent_trades(conn, days=1):
#     c = conn.cursor()
#     some_days_ago = (datetime.now() - timedelta(days=days)).isoformat()
#     c.execute("SELECT * FROM trades WHERE timestamp > ? ORDER BY timestamp DESC", (some_days_ago,))
#     columns = [column[0] for column in c.description]
#     return pd.DataFrame.from_records(data=c.fetchall(), columns=columns)

def get_recent_trades(conn, num_trades=20):
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
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": """
    You are an advanced AI trading analyst assistant. Your role is to analyze recent trading performance and current market conditions to generate specific, actionable insights and recommendations that can improve future trading decisions made by the Trading AI. Your analysis should focus on enhancing trading performance by providing clear feedback on past trades, identifying areas of improvement, and suggesting precise adjustments to the trading strategy, based solely on the data provided.
    """
            },
            {
                "role": "user",
                "content": f"""
                    Please analyze the following trading performance data and provide a structured analysis to improve future trading decisions.

                    **Input Data:**
                    - **Recent 20 Trades:**
                    {trades_df.to_json(orient='records')}
                    [Contains: Timestamp, Trade Type (AI/Manual), Decision (buy/sell/hold), Position Size %, Reason, Balance Information, Price Data]

                    - **Current Market Data:**
                    {current_market_data}
                    [Contains: Current Price, Fear/Greed Index, News Headlines, Orderbook Depth, Multi-timeframe OHLCV Data (5min/1h/4h)]

                    - **Overall Performance:** {performance:.2f}%

                    **Analysis Requirements:**

                    1. **Trade Performance Analysis:**
                    - Analyze AI trade decisions:
                        * Success rate by trade direction (buy/sell)
                        * Profit/loss distribution by position size
                        * Average duration of profitable vs unprofitable trades
                        * Market conditions during successful trades
                    - Position sizing effectiveness:
                        * Performance by position size category
                        * Correlation between size and outcome
                        * Risk-adjusted returns by size

                    2. **Market Condition Impact:**
                    - Analyze success rates during:
                        * Different Fear/Greed Index ranges
                        * Various volatility conditions
                        * News-heavy vs quiet periods
                    - Compare performance across timeframes
                    - Identify optimal trading conditions
                    - Analyze market structure during successful trades

                    3. **Strategy Execution Review:**
                    - Evaluate entry quality:
                        * Success rate by entry reason
                        * Market condition at entry
                        * Multi-timeframe alignment quality
                        * Entry price levels relative to key S/R
                    - Analyze trade management:
                        * Effectiveness of position scaling
                        * Market reversals impact
                        * Capital utilization efficiency

                    4. **Risk Management Effectiveness:**
                    - Calculate:
                        * Risk-Reward ratio achievement rate
                        * Capital preservation efficiency
                        * Maximum drawdown periods
                    - Identify:
                        * Most effective position sizing
                        * Best performing setup types
                        * Riskiest market conditions
                        * Optimal market volatility ranges

                    5. **Actionable Improvements:**
                    - Provide specific recommendations for:
                        * Entry timing optimization
                        * Position size adjustments
                        * Risk management refinements
                        * Market condition filters
                    - List top 3 most critical adjustments needed
                    - Suggest specific parameter adjustments
                    - Identify patterns to avoid

                    **Output Format:**
                    - Maximum 550 words
                    - Prioritize data-driven insights
                    - Include specific success patterns
                    - Provide quantifiable recommendations
                    - Address both success and failure patterns
                    - Focus on actionable strategy adjustments

                    Your analysis should provide comprehensive, data-driven insights that the trading AI can directly incorporate into its decision-making process, with emphasis on pattern recognition and risk management optimization based on historical performance data.
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
    
    # Stochastic Oscillator 추가
    stoch = ta.momentum.StochasticOscillator(
        high=df['high'], low=df['low'], close=df['close'], window=14, smooth_window=3)
    df['stoch_k'] = stoch.stoch()
    df['stoch_d'] = stoch.stoch_signal()

    # Average True Range (ATR) 추가
    df['atr'] = ta.volatility.AverageTrueRange(
        high=df['high'], low=df['low'], close=df['close'], window=14).average_true_range()

    # On-Balance Volume (OBV) 추가
    df['obv'] = ta.volume.OnBalanceVolumeIndicator(
        close=df['close'], volume=df['volume']).on_balance_volume()    
    
    # Momentum과 고점/저점 판단을 위한 새로운 지표들 추가
    
    # CMF (Chaikin Money Flow) - 자금 흐름 측정
    df['cmf'] = ta.volume.ChaikinMoneyFlowIndicator(
        high=df['high'], low=df['low'], close=df['close'], volume=df['volume'], window=20).chaikin_money_flow()
    
    # ADX (Average Directional Index) - 트렌드 강도 측정
    adx = ta.trend.ADXIndicator(high=df['high'], low=df['low'], close=df['close'])
    df['adx'] = adx.adx()
    df['di_plus'] = adx.adx_pos()
    df['di_minus'] = adx.adx_neg()
    
    # Williams %R - 과매수/과매도 판단
    df['williams_r'] = ta.momentum.WilliamsRIndicator(
        high=df['high'], low=df['low'], close=df['close'], lbp=14).williams_r()
    
    # PPO (Percentage Price Oscillator) - 모멘텀과 추세 전환 감지
    df['ppo'] = ta.momentum.PercentagePriceOscillator(close=df['close']).ppo()

    
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
        "q": "bitcoin OR btc",
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
                "date": convert_utc_to_kst(item.get("date", ""))
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


def safe_create_driver():
    retries = 3
    for attempt in range(retries):
        try:
            driver = create_driver()
            return driver
        except WebDriverException as e:
            logger.error(f"WebDriver 생성 실패 (시도 {attempt + 1}/{retries}): {e}")
            time.sleep(2)  # 재시도 전 대기
    raise WebDriverException("WebDriver 생성 실패. 크롬 드라이버를 확인하세요.")



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
        driver = safe_create_driver()
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
    # 7. Selenium으로 차트 캡처
    driver = None
    try:
        # TradingView 차트 캡처
        driver = login_with_cookies()
        driver.get("https://kr.tradingview.com/chart/zcDfxQQ8/?symbol=BINANCE%3ABTCUSDT.P")
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

    # 1. 현재 투자 상태 조회
    # USDT 잔고 조회
    balance = trader.exchange.fetch_balance()
    usdt_balance = balance['USDT']
    free_usdt = usdt_balance['free']      # 사용 가능한 잔고
    used_usdt = usdt_balance['used']      # 주문에 묶인 잔고
    total_usdt = usdt_balance['total']    # 전체 잔고
    filtered_balances = [used_usdt, free_usdt]

    # 포지션 정보 조회
    positions = trader.exchange.fetch_positions([trader.symbol])
    btc_avg_buy_price = 0  # 기본값 설정
    position_side = None
    position_size = 0
    unrealized_pnl = None

    for position in positions:
        if float(position.get('contracts', 0) or 0) != 0:
            btc_avg_buy_price = float(position['entryPrice'])
            position_side = position['side']  # 'long' 또는 'short'
            position_size = float(position['notional']) # contracts * entryPrice = USDT 단위
            unrealized_pnl = float(position.get('percentage', 0))  # 수익률(%)
            break


    # 2. 오더북(호가 데이터) 조회
    orderbook = trader.exchange.fetch_order_book('BTC/USDT')
    modified_orderbook = modify_orderbook(orderbook)

    # 3. 차트 데이터 조회 및 보조지표 추가   
    # Binance 거래소의 BTC/USDT Perpetual 현재가격
    ticker = trader.exchange.fetch_ticker(trader.symbol)
    current_price = ticker['last']

    # 바이낸스 5분봉 데이터 조회 (최근 2.5시간)
    df_5min = pd.DataFrame(
        trader.exchange.fetch_ohlcv(
            "BTC/USDT",
            timeframe='5m',
            limit=93 # 60 + 33
        ),
        columns=['timestamp', 'open', 'high', 'low', 'close', 'volume']
    )
    df_5min['timestamp'] = pd.to_datetime(df_5min['timestamp'], unit='ms').dt.tz_localize('UTC').dt.tz_convert('Asia/Seoul').dt.strftime('%Y/%m/%d %H:%M (KST)')
    df_5min = df_5min.set_index('timestamp')
    df_5min = dropna(df_5min)
    df_5min = add_indicators(df_5min)
    
    # 마지막 60개 데이터만 선택 (NaN 제거)
    df_5min = df_5min.tail(60)

    # 바이낸스 1시간봉 데이터 조회 (최근 24시간)
    df_hourly = pd.DataFrame(
        trader.exchange.fetch_ohlcv(
            "BTC/USDT", 
            timeframe='1h',
            limit=57 # 24 + 33
        ),
        columns=['timestamp', 'open', 'high', 'low', 'close', 'volume']
    )
    df_hourly['timestamp'] = pd.to_datetime(df_hourly['timestamp'], unit='ms').dt.tz_localize('UTC').dt.tz_convert('Asia/Seoul').dt.strftime('%Y/%m/%d %H:%M (KST)')
    df_hourly = df_hourly.set_index('timestamp')
    df_hourly = dropna(df_hourly)
    df_hourly = add_indicators(df_hourly)

    # 마지막 24개 데이터만 선택 (NaN 제거)
    df_hourly = df_hourly.tail(24)

    # 바이낸스 4시간봉 데이터 조회 (최근 3일)
    df_4h = pd.DataFrame(
        trader.exchange.fetch_ohlcv(
            "BTC/USDT",
            timeframe='4h',
            limit=51 # 18 + 33
        ),
        columns=['timestamp', 'open', 'high', 'low', 'close', 'volume']
    )
    df_4h['timestamp'] = pd.to_datetime(df_4h['timestamp'], unit='ms').dt.tz_localize('UTC').dt.tz_convert('Asia/Seoul').dt.strftime('%Y/%m/%d %H:%M (KST)')
    df_4h = df_4h.set_index('timestamp')
    df_4h = dropna(df_4h)
    df_4h = add_indicators(df_4h)    

    # 마지막 18개 데이터만 선택 (NaN 제거)
    df_4h = df_4h.tail(18)

    # 4. 공포 탐욕 지수 가져오기
    fear_greed_index = get_fear_and_greed_index()

    # 5. 뉴스 헤드라인 가져오기
    news_headlines = get_bitcoin_news()

    # 6. YouTube 자막 데이터 가져오기
    f2 = open("strategy2.txt", "r", encoding="utf-8")
    youtube_transcript2 = f2.read()
    f2.close()    

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
                "Current Price": current_price,
                "fear_greed_index": fear_greed_index,
                "news_headlines": news_headlines,
                "orderbook": modified_orderbook,
                "5min_ohlcv": df_5min.to_dict(),      # 5시간치 5분봉 데이터 추가
                "hourly_ohlcv": df_hourly.to_dict(),  # 24시간치 1시간봉 데이터 추가
                "4hour_ohlcv": df_4h.to_dict()        # 3일치 4시간봉 데이터 추가
            }
            # 반성 및 개선 내용 생성
            reflection = generate_reflection(recent_trades, current_market_data)
    
            # AI 모델에 반성 내용 제공
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                    "role": "system",
                    "content": f"""
                        ───────────────────────────────────────────────────────────────
                        # Bitcoin Futures Trading Strategy (Integrated Prompt)

                        You are a Bitcoin futures day trader on the 5-minute timeframe with {trader.leverage}x leverage. Your strategy centers on three primary indicators (BlackFlag FTS, UT Bot Alerts, Volume Oscillator) and includes additional confluence checks (RSI, MACD, ATR, CMF, ADX, DI+, DI−, etc.). Strict timing rules apply—no aged signals, immediate exits on signal deterioration, and precise position management. Capital preservation is paramount.

                        ───────────────────────────────────────────────────────────────
                        ## 1. ALWAYS Use Correct Exit Commands
                        • "buy" to exit shorts  
                        • "sell" to exit longs  

                        This ensures the correct order type is used when closing an existing position.

                        ───────────────────────────────────────────────────────────────
                        ## 2. Market Data and Portfolio Placeholders

                        Below are placeholders for real-time data. They MUST be considered as secondary in your analysis (the three primary indicators are main) and in your final decision.

                        **[Market Data]**  
                        • Current Price: {current_price:.2f} USDT  

                        **Technical Indicators (5-min, 1-hour, 4-hour timeframes)**

                        → 5-Minute Chart Data:  
                        - RSI(14): {df_5min['rsi'].iloc[-1]:.2f}  
                        - MACD: {df_5min['macd'].iloc[-1]:.2f}  
                        - Bollinger Bands (20):  
                        * Middle: {df_5min['bb_bbm'].iloc[-1]:.2f}  
                        * Upper: {df_5min['bb_bbh'].iloc[-1]:.2f}  
                        * Lower: {df_5min['bb_bbl'].iloc[-1]:.2f}  
                        - Stochastic Oscillator (14, 3):  
                        * %K: {df_5min['stoch_k'].iloc[-1]:.2f}  
                        * %D: {df_5min['stoch_d'].iloc[-1]:.2f}  
                        - ATR: {df_5min['atr'].iloc[-1]:.2f}  
                        - Williams %R: {df_5min['williams_r'].iloc[-1]:.2f}  
                        - CMF: {df_5min['cmf'].iloc[-1]:.2f}  
                        - ADX: {df_5min['adx'].iloc[-1]:.2f}  
                        - DI+: {df_5min['di_plus'].iloc[-1]:.2f}  
                        - DI-: {df_5min['di_minus'].iloc[-1]:.2f}  
                        - PPO: {df_5min['ppo'].iloc[-1]:.2f}

                        → 1-Hour Chart Data:  
                        - RSI(14): {df_hourly['rsi'].iloc[-1]:.2f}  
                        - MACD: {df_hourly['macd'].iloc[-1]:.2f}  
                        - Bollinger Bands:  
                        * Middle: {df_hourly['bb_bbm'].iloc[-1]:.2f}  
                        * Upper: {df_hourly['bb_bbh'].iloc[-1]:.2f}  
                        * Lower: {df_hourly['bb_bbl'].iloc[-1]:.2f}  
                        - ATR: {df_hourly['atr'].iloc[-1]:.2f}  
                        - Williams %R: {df_hourly['williams_r'].iloc[-1]:.2f}  
                        - CMF: {df_hourly['cmf'].iloc[-1]:.2f}  
                        - ADX: {df_hourly['adx'].iloc[-1]:.2f}  
                        - DI+: {df_hourly['di_plus'].iloc[-1]:.2f}  
                        - DI-: {df_hourly['di_minus'].iloc[-1]:.2f}  
                        - PPO: {df_hourly['ppo'].iloc[-1]:.2f}

                        → 4-Hour Chart Data:  
                        - RSI(14): {df_4h['rsi'].iloc[-1]:.2f}  
                        - MACD: {df_4h['macd'].iloc[-1]:.2f}  
                        - Bollinger Bands:  
                        * Middle: {df_4h['bb_bbm'].iloc[-1]:.2f}  
                        * Upper: {df_4h['bb_bbh'].iloc[-1]:.2f}  
                        * Lower: {df_4h['bb_bbl'].iloc[-1]:.2f}  
                        - ATR: {df_4h['atr'].iloc[-1]:.2f}  
                        - Williams %R: {df_4h['williams_r'].iloc[-1]:.2f}  
                        - CMF: {df_4h['cmf'].iloc[-1]:.2f}  
                        - ADX: {df_4h['adx'].iloc[-1]:.2f}  
                        - DI+: {df_4h['di_plus'].iloc[-1]:.2f}  
                        - DI-: {df_4h['di_minus'].iloc[-1]:.2f}  
                        - PPO: {df_4h['ppo'].iloc[-1]:.2f}

                        **[Portfolio]**  
                        • Total USDT Assets: {total_usdt:.1f}  
                        • Free USDT Balance: {free_usdt:.1f}  
                        • Used USDT Holdings: {used_usdt:.1f}  
                        • BTC Average Purchase Price: {btc_avg_buy_price:.1f} USDT  
                        • Current Position Side: {position_side}  ← “long”, “short”, or “none”  
                        • Current Position PnL: {unrealized_pnl} % ← -100~100 or None(no position)

                        You should factor in these data points before making a final trading decision (buy, sell, hold).

                        ───────────────────────────────────────────────────────────────
                        ## 3. Core Strategy Overview

                        ### A. Critical Timing
                        • BlackFlag FTS:  
                        - LONG if Red→Green transition is fresh (≤2 candles ago).  
                        - SHORT if Green→Red transition is fresh (≤2 candles ago).  
                        • UT Bot Alerts:  
                        - Must appear within the last 2 candles in the same direction.  
                        • Volume Oscillator:  
                        - Must be positive (>0) on the current candle, indicating rising volume momentum.

                        Any stale signals or misalignment → “hold” (no entry).  
                        **This is mandatory: if any core indicator signal is older than 2 candles, you must not enter. Always “hold” unless all three are fresh (≤2 candles).**

                        **However, if a signal is slightly beyond 2 candles (e.g., 3 or 4 candles) but price has not moved significantly (within ±0.2% from the original trigger level), and Volume or other Additional Indicators still align, you may consider entering with a reduced position size (e.g., treat it as a “Weak Signal”). This helps avoid missing valid trades due to minor delays. If more than 4 candles have passed or price has shifted over ±0.5% from the trigger, treat it as stale and remain in “hold.”**

                        ### B. Additional Indicators (RSI, MACD, ATR, CMF, ADX, DI+/DI-)
                        Use these for extra confirmation or rejection of the primary indicators only.  
                        **You may never open a position solely on Additional Indicators if the primary indicators do not show a valid fresh entry signal.**  
                        Major divergences or contradictory signals can override or cancel a primary entry (leading to a “hold”), but cannot create a new entry on their own.  
                        Adjust stops/position size using ATR. Watch momentum (MACD, ADX) and money flow (CMF).

                        ### C. Signal Classification: Strong, Moderate, Weak

                        • Strong Signal  
                        - Primary indicators in perfect alignment + High volume (≥250% avg) + Low/stable ATR.  
                        - Position Size: 100% of calculated size.  
                        - Stop Loss: ±0.5% from entry (refined with Cloud/ATR).  
                        - P/L Ratio: ~2.0.

                        • Moderate Signal  
                        - Decent volume and volatility, clean primary indicator alignment.  
                        - Position Size: ~60%.  
                        - Stop Loss: ±0.4% from entry or Cloud.  
                        - P/L Ratio: ~1.75 (1.5-2.0 range).

                        • Weak Signal  
                        - Indicators align but momentum/volume borderline, or partial confluence. Possibly higher volatility.  
                        - Position Size: ~30%.  
                        - Stop Loss: ±0.3% from entry (Cloud + ATR checks).  
                        - P/L Ratio: ~1.5 (1.5-2.0 range).

                        ### D. Price Action & Key Levels (Support/Resistance)
                        To further refine your entries/exits, identify notable swing highs and lows on the 5-minute, 1-hour, and 4-hour charts. These levels often serve as potential support (previous lows) or resistance (previous highs).  
                        • A fresh primary signal that appears right below a strong resistance may be risky—consider waiting for a breakout or rejection confirmation.  
                        • Conversely, if a primary buy signal aligns with a well-established support level on the higher timeframe, it can strengthen the case for entry.  
                        • Use such key levels only as confluence or rejection criteria; do not open new positions on price action alone if the three primary indicators are not providing a valid fresh signal.  
                        • When prices approach or break these S/R zones, watch for divergences or volume spikes to confirm or deny continuation.

                        ───────────────────────────────────────────────────────────────
                        ## 4. Stop Loss & Take Profit

                        1) Cloud-Based Stop Loss  
                        - LONG: near the deepest green portion of the latest Green Cloud.  
                        - SHORT: near the deepest red portion of the latest Red Cloud.  
                        - If that is unreasonably far, switch to ATR ±0.3-0.5% guidelines.

                        2) P/L Ratio (1.5-2.0)  
                        - Strong: ~2.0 baseline.  
                        - Moderate: ~1.75 baseline.  
                        - Weak: ~1.5 baseline.

                        Adjust within 1.5-2.0 based on real-time volatility.

                        ───────────────────────────────────────────────────────────────
                        ## 5. Exit & Risk Management

                        • Exit if any core signal reverses or invalidates.  
                        • Volume Oscillator < 0% → immediate red flag.  
                        • If secondary indicators reveal sharp contradiction (e.g., strong RSI or MACD divergence), exit early.  
                        • Use partial exits if needed (e.g., scale out every +0.1% gain).  
                        **• If the 5-minute MACD shows a clear trend reversal for 2 consecutive candles in the opposite direction, perform an immediate “Full Exit” of the position.**

                        ───────────────────────────────────────────────────────────────
                        ## 6. Response Format

                        Output a JSON object:

                        ```json
                        {{
                        "decision": "buy" or "sell" or "hold",
                        "percentage": integer (0-100),
                        "stop_loss_price": float,
                        "pl_ratio": float (1.5-2.0),
                        "reason": "Concise rationale referencing signals & data"
                        }}
                        ```

                        - “decision”: Open or close a position. “buy” closes shorts or opens a new long, “sell” closes longs or opens a new short, “hold” = no action.  
                        - “stop_loss_price”: Based on Cloud or ±0.3-0.5% + ATR.  
                        - “pl_ratio”: Choose between 1.5 and 2.0, guided by signal strength.  
                        - “reason”: A short summary referencing indicator alignment (must include BlackFlag FTS, UT Bot Alerts, Volume OSC), volume, volatility, etc.

                        **Position Sizing Rules:**  
                        - The "percentage" field is an integer between 0 and 100 representing the fraction of a full allocation.  
                        - For entry orders, a value of 100 means using 100% of the available balance for entry.  
                        - For exit orders, 100 means closing 100% of the current position quantity.  
                        - In practice, you may set "percentage" to any value between 0 and 100 (except when the decision is "hold") based on signal strength and risk considerations.  
                        - Use the following full-allocation benchmarks as your baseline:  
                        - For entries when Current Position Side is "long" or "none" and the decision is "buy", or when Current Position Side is "short" or "none" and the decision is "sell", 100% represents the entirety of the available balance.  
                        - For exits when Current Position Side is "short" and the decision is "buy", or when Current Position Side is "long" and the decision is "sell", 100% represents the entire current position.

                        ───────────────────────────────────────────────────────────────
                        ### Final Notes

                        1) Respect fresh signals only—if any signal is 2 or more candles old, do not enter and hold.  
                        2) Use correct exit commands: “buy” to exit a short, “sell” to exit a long.  
                        3) Incorporate the dynamically updated values from [Market Data] and [Portfolio] sections.  
                        4) Maintain capital preservation: exit immediately on conflicting or invalid signals.

                        ───────────────────────────────────────────────────────────────
                        This is the final integrated prompt. Use all provided data, ensure that the three primary indicators (BlackFlag FTS, UT Bot Alerts, Volume OSC) are fresh (≤2 candles old) for any entry—though slight delays (3–4 candles) may still qualify if price remains near the trigger (+/–0.2%) and volume momentum persists. If more than 4 candles pass or price moves >0.5% away, treat it as stale. Additional Indicators can only confirm or reject a fresh or slightly delayed primary signal—never enter on Additional Indicators alone. For position sizing, apply the updated Position Sizing Rules above when computing the percentage (0–100) for entries and exits, and factor in local highs/lows for possible support/resistance.  
                        """   
                    },
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": f"""Current investment status: {json.dumps(filtered_balances)}
                                Orderbook: {json.dumps(modified_orderbook)}
                                5-minute OHLCV with indicators (5 hours): {df_5min.to_json()}
                                Hourly OHLCV with indicators (24 hours): {df_hourly.to_json()}
                                4-hour OHLCV with indicators (3 days): {df_4h.to_json()}
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
            # 포지션 보유 중일 때
            if position_side:
                # 보유 포지션과 반대 방향 주문이면 포지션 크기 기준으로 계산
                if ((position_side == 'long' and result.decision == 'sell') or 
                    (position_side == 'short' and result.decision == 'buy')):
                        order_amount = position_size * (result.percentage / 100)
                # 같은 방향 추가 주문이면 잔고 기준으로 계산
                else:
                    order_amount = total_balance * (result.percentage / 100) * 0.9996
            else:  # 신규 진입일 때도 잔고 기준으로 계산
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
        time.sleep(1)  # API 호출 제한을 고려하여 잠시 대기
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
            tp_order_id = order_info['tp']['id'] if order_info.get('tp') else None
            sl_order_id = order_info['sl']['id'] if order_info.get('sl') else None
            
            log_trade(conn, 'AI', order_id, result.decision, result.percentage, result.reason, 
                    used_usdt, free_usdt, total_usdt, btc_avg_buy_price, current_btc_price, 
                    reflection, tp_order_id, sl_order_id)
            
            # 트레일링 스탑로스 모니터링 추가
            if 'monitor_sl' in order_info:
                # 함수를 변수에 저장
                monitor_sl_func = order_info['monitor_sl']
                
                def periodic_sl_monitoring():
                    try:
                        new_sl_order = monitor_sl_func(trader)
                        if new_sl_order:
                            logger.info(f"Trailing SL order updated: {new_sl_order}")
                    except Exception as e:
                        logger.error(f"Error in SL monitoring: {e}")
                        
                # 5분마다 SL 모니터링
                schedule.every(5).minutes.do(periodic_sl_monitoring)
                
        else:
            # 거래가 실행되지 않은 경우 (hold 또는 실패)
            log_trade(conn, 'AI', None, result.decision, 0, result.reason, 
                    used_usdt, free_usdt, total_usdt, btc_avg_buy_price, current_btc_price, 
                    reflection, None, None)
            
    
    
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
