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
        self.leverage = 2  # 기본 레버리지 설정
        self.logger = logger
        self.exchange.load_markets()

    def setup_leverage_and_margin(self, leverage: int):
            try:
                self.exchange.set_leverage(leverage, self.symbol)
                self.exchange.set_margin_mode('isolated', self.symbol)
                self.leverage = leverage  # leverage 속성 업데이트
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

    # async def market_order_with_tp_sl(self, 
    #                       side: str,           # 'buy' or 'sell'
    #                       buy_amount: float,   # USDT 투자금액
    #                       pl_ratio: float,   # 손익비 
    #                       sl_price: float):  # SL 가격
   
    #     # 현재가 조회
    #     ticker = self.exchange.fetch_ticker(self.symbol)
    #     current_price = ticker['last']
        
    #     # 수량 계산 (USDT 금액 / 현재가)
    #     quantity = buy_amount / current_price
        
    #     # TP/SL 가격 계산
    #     if side == 'buy':
    #         tp_price = current_price + round(pl_ratio,2)*(current_price-sl_price)
    #         sl_price = sl_price
    #     else:
    #         tp_price = current_price - round(pl_ratio,2)*(sl_price-current_price) 
    #         sl_price = sl_price

    #     # 시장가 주문 실행
    #     order = self.exchange.create_market_order(
    #         symbol=self.symbol,
    #         side=side,
    #         amount=quantity
    #     )

    #     # TP/SL 주문
    #     tp_side = 'sell' if side == 'buy' else 'buy'
        
    #     tp_order = self.exchange.create_order(
    #         symbol=self.symbol,
    #         type='TAKE_PROFIT_MARKET',
    #         side=tp_side,
    #         amount=quantity,
    #         params={'stopPrice': tp_price}
    #     )

    #     sl_order = self.exchange.create_order(
    #         symbol=self.symbol,
    #         type='STOP_MARKET',
    #         side=tp_side,
    #         amount=quantity,
    #         params={'stopPrice': sl_price}
    #     )

    #     return {
    #         'entry': order,
    #         'tp': tp_order, 
    #         'sl': sl_order
    #     }
    def market_order_with_tp_sl(self, side: str, buy_amount: float, pl_ratio: float, sl_price: float):
        try:
            # 현재가 조회
            ticker = self.exchange.fetch_ticker(self.symbol)
            current_price = ticker['last']
            
            # 증거금 필요량 계산 (최소 필요 증거금 + 수수료)
            margin_needed = buy_amount / self.leverage + (buy_amount * 0.0004)  # 0.04% 수수료
            
            # 가용 자금 조회
            balance = self.exchange.fetch_balance()
            available_balance = float(balance['USDT']['free'])
            
            # 자금 부족 시 주문 실패 처리
            if available_balance < 10:  # USDT 최소 주문금액
                self.logger.error(f"Insufficient balance. Available: {available_balance} USDT")
                return None
                
            # 증거금 부족 시 거래 금액 조정
            if margin_needed > available_balance:
                adjusted_amount = (available_balance * self.leverage) * 0.9996
                self.logger.warning(f"Margin required ({margin_needed} USDT) exceeds available balance. Adjusting order amount from {buy_amount} to {adjusted_amount} USDT")
                buy_amount = adjusted_amount
                
            # 수량 계산
            quantity = buy_amount / current_price
            
            # 최소 주문 수량 확인
            market_limits = self.exchange.markets[self.symbol]['limits']
            min_amount = market_limits['amount']['min']
            if quantity < min_amount:
                self.logger.error(f"Order quantity ({quantity}) is below minimum ({min_amount})")
                return None
            
            # TP/SL 가격 계산
            if side == 'buy':
                tp_price = current_price + pl_ratio * (current_price - sl_price)
            else:
                tp_price = current_price - pl_ratio * (sl_price - current_price)
                
            # 주문 실행
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
trader.setup_leverage_and_margin(2)  # 2배 레버리지

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
def log_trade(conn, decision, percentage, reason, btc_balance, usdt_balance, total_assets, btc_avg_buy_price, btc_current_price, reflection=''):
    c = conn.cursor()
    timestamp = datetime.now().isoformat()
    c.execute("""INSERT INTO trades 
                 (timestamp, decision, percentage, reason, btc_balance, usdt_balance, total_assets, btc_avg_buy_price, btc_current_price, reflection) 
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
              (timestamp, decision, percentage, reason, btc_balance, usdt_balance, total_assets, btc_avg_buy_price, btc_current_price, reflection))
    conn.commit()


# 최근 투자 기록 조회
def get_recent_trades(conn, days=7):
    c = conn.cursor()
    seven_days_ago = (datetime.now() - timedelta(days=days)).isoformat()
    c.execute("SELECT * FROM trades WHERE timestamp > ? ORDER BY timestamp DESC", (seven_days_ago,))
    columns = [column[0] for column in c.description]
    return pd.DataFrame.from_records(data=c.fetchall(), columns=columns)


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
        model="gpt-4o-2024-08-06",
        messages=[
            {
                "role": "system",
                "content": "You are an AI trading assistant tasked with analyzing recent trading performance and current market conditions to generate insights and improvements for future trading decisions."
            },
            {
                "role": "user",
                "content": f"""
                Recent trading data:
                {trades_df.to_json(orient='records')}
                
                Current market data:
                {current_market_data}
                
                Overall performance in the last 7 days: {performance:.2f}%
                
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


# 공포 탐욕 지수 조회
def get_fear_and_greed_index():
    url = "https://api.alternative.me/fng/"
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        return data['data'][0]
    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching Fear and Greed Index: {e}")
        return None


# 뉴스 데이터 가져오기
def get_bitcoin_news():
    serpapi_key = os.getenv("SERPAPI_API_KEY")
    if not serpapi_key:
        logger.error("SERPAPI API key is missing.")
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
                "date": item.get("date", "")
            })
        
        return headlines[:5]
    except requests.RequestException as e:
        logger.error(f"Error fetching news: {e}")
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








### 메인 AI 트레이딩 로직
def ai_trading():
    # global upbit
    ### 데이터 가져오기
    # 1. 현재 투자 상태 조회
    # all_balances = upbit.get_balances()
    # filtered_balances = [balance for balance in all_balances if balance['currency'] in ['BTC', 'KRW']]
    # USDT 잔고 조회
    balance = trader.exchange.fetch_balance()
    usdt_balance = balance['USDT']
    free_usdt = usdt_balance['free']      # 사용 가능한 잔고
    used_usdt = usdt_balance['used']      # 주문에 묶인 잔고
    total_usdt = usdt_balance['total']    # 전체 잔고
    filtered_balances = [used_usdt, free_usdt]

    # 2. 오더북(호가 데이터) 조회
    # orderbook = pyupbit.get_orderbook("KRW-BTC")
    orderbook = trader.exchange.fetch_order_book('BTC/USDT')

    # 3. 차트 데이터 조회 및 보조지표 추가
    # df_daily = pyupbit.get_ohlcv("KRW-BTC", interval="day", count=30)
    # df_daily = dropna(df_daily)
    # df_daily = add_indicators(df_daily)
    
    # df_hourly = pyupbit.get_ohlcv("KRW-BTC", interval="minute60", count=24)
    # df_hourly = dropna(df_hourly)
    # df_hourly = add_indicators(df_hourly)
    # 바이낸스 일봉 데이터 
    df_daily = pd.DataFrame(
    trader.exchange.fetch_ohlcv(
        "BTC/USDT",
        timeframe='1d',
        limit=30
    ),
    columns=['timestamp', 'open', 'high', 'low', 'close', 'volume']
    )
    df_daily['timestamp'] = pd.to_datetime(df_daily['timestamp'], unit='ms')
    df_daily = df_daily.set_index('timestamp')
    df_daily = dropna(df_daily)
    df_daily = add_indicators(df_daily)

    # 바이낸스 60분봉 데이터
    df_hourly = pd.DataFrame(
    trader.exchange.fetch_ohlcv(
        "BTC/USDT", 
        timeframe='1h',
        limit=24
    ),
    columns=['timestamp', 'open', 'high', 'low', 'close', 'volume']
    )
    df_hourly['timestamp'] = pd.to_datetime(df_hourly['timestamp'], unit='ms')
    df_hourly = df_hourly.set_index('timestamp')
    df_hourly = dropna(df_hourly)
    df_hourly = add_indicators(df_hourly)



    # 4. 공포 탐욕 지수 가져오기
    fear_greed_index = get_fear_and_greed_index()

    # 5. 뉴스 헤드라인 가져오기
    # news_headlines = get_bitcoin_news()

    # 6. YouTube 자막 데이터 가져오기
    f2 = open("strategy2.txt", "r", encoding="utf-8")
    youtube_transcript2 = f2.read()
    f2.close()    

    # 7. Selenium으로 차트 캡처
    driver = None
    try:
        # TradingView 차트 캡처
        driver = login_with_cookies()
        driver.get("https://kr.tradingview.com/chart/QYZJBUKS/?symbol=BITHUMB%3ABTCKRW")
        logger.info("TradingView 페이지 로드 완료")
        time.sleep(5)
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
            cleanup_chrome_processes()

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
                # "news_headlines": news_headlines,
                "orderbook": orderbook,
                "daily_ohlcv": df_daily.to_dict(),
                "hourly_ohlcv": df_hourly.to_dict()
            }
    
            # 반성 및 개선 내용 생성
            reflection = generate_reflection(recent_trades, current_market_data)
    
            # AI 모델에 반성 내용 제공
            response = client.chat.completions.create(
                model="gpt-4o-2024-08-06",
                messages=[
                    {
                        "role": "system",
                        "content": f"""You are a Bitcoin futures day trader who specializes in short-term trading based on 5-minute candlestick charts. You are trading two-way positions based on coin futures trading and focus on analyzing 5-minute timeframes to identify quick market moves and opportunities while also considering the broader market conditions. You analyze the data provided to determine whether to take a buy, sell, or hold position at the current time. Consider the following when analyzing
                        
                        - Technical indicators and market data, with primary focus on 5-minute chart patterns and movements
                        - Short-term price action and momentum
                        - Volume analysis on 5-minute timeframes
                        - Quick trend reversals and continuation patterns
                        - Support and resistance levels visible on 5-minute charts
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
                        For optimal timing of entry, the occurrence of these three indicators should be recent on a 5-minute timeframe. Otherwise, don't enter position.
                        and "stop loss price" should be based on trading method above.
                        Also, because of the high fees associated with futures leverage, you shouldn't trade too often. Prioritize the entry signals from the three indicators.
                        
                        Based on this trading method, analyze the current market situation and make a judgment by synthesizing it with the provided data and recent performance reflection.

                        Response format:
                        1. Decision (buy, sell, or hold)
                        2. If the decision is 'buy', provide a percentage (1-100) of available USDT to use for buying. and show stop_loss_price, P&L ratio.
                        If the decision is 'sell', provide a percentage (1-100) of held BTC/USDT to sell. and show stop_loss_price, P&L ratio.
                        If the decision is 'hold', set the percentage to 0.
                        3. Reason for your decision (it should include not only market situation and chart status, but also recent status or change of BlackFlag FTS, UT Bot Alerts, Volume Oscillator)

                        Ensure that the percentage is an integer between 1 and 100 for buy/sell decisions, and exactly 0 for hold decisions.
                        Your percentage should reflect the strength of your conviction in the decision based on the analyzed data.
                        Depending on the strength of the buy signal, P&L ratio should between 1.3~2 value  (default 1.5) 
                        """
                    },
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": f"""Current investment status: {json.dumps(filtered_balances)}
                                Orderbook: {json.dumps(orderbook)}
                                Daily OHLCV with indicators (30 days): {df_daily.to_json()}
                                Hourly OHLCV with indicators (24 hours): {df_hourly.to_json()}
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
                            "required": ["decision", "percentage", "reason", "stop_loss_price", "pl_ratio"], # XXX : claer !! || (25-01-24) TP/SL 설정 마저 완료해야함. 추후, 업비트로 남아있는 코드 바이낸스 형식으로 바꿔야.
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
        # used_balance = next((float(balance['balance']) for balance in balances if balance['currency'] == 'BTC'), 0)
        # free_balance = next((float(balance['balance']) for balance in balances if balance['currency'] == 'KRW'), 0)
        # btc_avg_buy_price = next((float(balance['avg_buy_price']) for balance in balances if balance['currency'] == 'BTC'), 0)
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
        log_trade(conn, result.decision, result.percentage if order_executed else 0, result.reason, 
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


        # 중복 실행 방지를 위한 변수
        trading_in_progress = False
        
        # 트레이딩 작업을 수행하는 함수
        def job():
            global trading_in_progress
            if trading_in_progress:
                logger.warning("Trading job is already in progress, skipping this run ")
                return
            try:
                trading_in_progress = True
                ai_trading()
            except Exception as e:
                logger.error(f"An error occured: {e}")
            finally:
                trading_in_progress = False

        job()
        # 활발한 거래 시간대 (21:00-02:00): 15분 간격
        for hour in [21, 22, 23, 0, 1]:
            for minute in range(0, 60, 15):
                schedule.every().day.at(f"{hour:02d}:{minute:02d}").do(job)
        # 02:00에 마지막 실행
        schedule.every().day.at("02:00").do(job)

        # 활발한 거래 시간대 (04:00-07:00): 15분 간격
        for hour in [4, 5, 6, 7]:
            for minute in range(0, 60, 15):
                schedule.every().day.at(f"{hour:02d}:{minute:02d}").do(job)
        # 07:00에 마지막 실행
        schedule.every().day.at("07:00").do(job)

        # 새로 추가된 15:00-18:00 시간대: 15분 간격
        for hour in [15, 16, 17, 18]:
            for minute in range(0, 60, 15):
                schedule.every().day.at(f"{hour:02d}:{minute:02d}").do(job)
        # 18:00에 마지막 실행
        schedule.every().day.at("18:00").do(job)

        # 스케줄러 실행
        while True:
            schedule.run_pending()
            time.sleep(1)
            
    except Exception as e:
        logger.error(f"Critical error occurred: {e}")
        cleanup_chrome_processes()
    finally:
        cleanup_chrome_processes()