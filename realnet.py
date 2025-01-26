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
import logging
from datetime import datetime
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
import asyncio

class BinanceFuturesTrader:
    def __init__(self, api_key: str, api_secret: str):
        self.exchange = ccxt.binance({
            'apiKey': api_key,
            'secret': api_secret,
            'enableRateLimit': True,
            'options': {
                'defaultType': 'future'
            }
        })
        self.setup_logging()
        self.symbol = "BTC/USDT"
        self.exchange.load_markets()
        
    def setup_logging(self):
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging.INFO)
        handler = logging.StreamHandler()
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        self.logger.addHandler(handler)

    async def setup_leverage_and_margin(self, leverage: int):
        try:
            # Set leverage
            self.exchange.set_leverage(leverage, self.symbol)
            # Set margin mode to isolated
            self.exchange.set_margin_mode('isolated', self.symbol)
            self.logger.info(f"Leverage set to {leverage}x and margin mode set to isolated")
        except Exception as e:
            self.logger.error(f"Error setting up leverage and margin: {e}")
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
                params={'stopPrice': tp_price}
            )

            # Set stop loss order
            sl_order = await self.exchange.create_order(
                symbol=self.symbol,
                type='STOP_MARKET',
                side='sell' if side == 'buy' else 'buy',
                amount=position_size,
                params={'stopPrice': sl_price}
            )

            self.logger.info(f"{side.upper()} position opened: Size={position_size}, Entry={entry_price}, TP={tp_price}, SL={sl_price}")
            return {'entry': order, 'tp': tp_order, 'sl': sl_order}
        
        except Exception as e:
            self.logger.error(f"Error opening position: {e}")
            raise

    async def market_order_with_tp_sl(self, 
                          side: str,           # 'buy' or 'sell'
                          buy_amount: float,   # USDT 투자금액
                          pl_ratio: float,   # 손익비 
                          sl_price: float):  # SL 가격
   
        # 현재가 조회
        ticker = self.exchange.fetch_ticker(self.symbol)
        current_price = ticker['last']
        
        # 수량 계산 (USDT 금액 / 현재가)
        quantity = buy_amount / current_price
        
        # TP/SL 가격 계산
        if side == 'buy':
            tp_price = current_price + round(pl_ratio,2)*(current_price-sl_price)
            sl_price = sl_price
        else:
            tp_price = current_price - round(pl_ratio,2)*(sl_price-current_price) 
            sl_price = sl_price

        # 시장가 주문 실행
        order = self.exchange.create_market_order(
            symbol=self.symbol,
            side=side,
            amount=quantity
        )

        # TP/SL 주문
        tp_side = 'sell' if side == 'buy' else 'buy'
        
        tp_order = self.exchange.create_order(
            symbol=self.symbol,
            type='TAKE_PROFIT_MARKET',
            side=tp_side,
            amount=quantity,
            params={'stopPrice': tp_price}
        )

        sl_order = self.exchange.create_order(
            symbol=self.symbol,
            type='STOP_MARKET',
            side=tp_side,
            amount=quantity,
            params={'stopPrice': sl_price}
        )

        return {
            'entry': order,
            'tp': tp_order, 
            'sl': sl_order
        }

    async def close_position(self) -> Optional[Dict[str, Any]]:
        try:
            position = await self.exchange.fetch_position(self.symbol)
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
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)



async def main():
    # BINANCE 객체 생성
    api_key = os.getenv("BINANCE_API_KEY")
    secret_key = os.getenv("BINANCE_SECRET_KEY")
    if not api_key or not secret_key:
        logger.error("API keys not found. Please check your .env file.")
        raise ValueError("Missing API keys. Please check your .env file.")
    trader = BinanceFuturesTrader(api_key, secret_key)


    # 레버리지 설정 
    await trader.setup_leverage_and_margin(8)  # 5배 레버리지



if __name__ == "__main__":
    asyncio.run(main())
