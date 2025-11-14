from flask import Flask, request, jsonify
import ccxt
import json
import logging
from datetime import datetime, timedelta, timezone
import os
from dotenv import load_dotenv
import threading
import time
import requests
import pandas as pd
import ta
from ta.utils import dropna
from openai import OpenAI
from pydantic import BaseModel, Field, ValidationError
import sqlite3
import numpy as np
import re
from multiprocessing import Process
import signal
import sys

# 환경 변수 로드
load_dotenv()

# ============ 멀티 유저 설정 ============
USERS_CONFIG = {
    5000: {
        'name': 'User1',
        'api_key_env': 'BINANCE_API_KEY',
        'secret_key_env': 'BINANCE_SECRET_KEY',
        'enable_telegram': True,
        'enable_db_write': True,
        'leverage': 10,
        'position_size_percent': 30,
        'ai_monitor_interval': 5
    },
    5001: {
        'name': 'Hyun',
        'api_key_env': 'BINANCE_API_KEY_HYUN',
        'secret_key_env': 'BINANCE_SECRET_KEY_HYUN',
        'enable_telegram': False,
        'enable_db_write': False,
        'leverage': 10,
        'position_size_percent': 30,
        'ai_monitor_interval': 5
    },
    5002: {
        'name': 'User3',
        'api_key_env': 'BINANCE_API_KEY_USER3',
        'secret_key_env': 'BINANCE_SECRET_KEY_USER3',
        'enable_telegram': False,
        'enable_db_write': False,
        'leverage': 10,
        'position_size_percent': 25,
        'ai_monitor_interval': 5
    }
}

# 공통 DB 파일
DB_FILENAME = 'trading_bot.db'

# ============ AI Decision Models ============
class TradingDecision(BaseModel):
    """트레이딩 시그널 검증용 모델"""
    decision: str = Field(..., pattern="^(approve|reject|modify)$")
    modified_action: str = Field(..., pattern="^(buy|sell|hold)$")
    percentage: int = Field(..., ge=10, le=100)
    reason: str = Field(..., min_length=1)
    stop_loss_price: float = Field(..., gt=0)
    take_profit_price: float = Field(..., gt=0)
    pl_ratio: float = Field(..., ge=1.0, le=5.0)
    confidence: float = Field(..., ge=0.0, le=1.0)

class ClosePositionDecision(BaseModel):
    """청산 시그널 검증용 모델 (SL/TP 불필요)"""
    decision: str = Field(..., pattern="^(approve|reject)$")
    reason: str = Field(..., min_length=1)
    confidence: float = Field(..., ge=0.0, le=1.0)
    urgency: str = Field(..., pattern="^(immediate|soon|normal|low)$")

class PositionExitDecision(BaseModel):
    """포지션 종료 결정용 모델 - 개선 버전"""
    decision: str = Field(..., pattern="^(hold|close|partial_close)$")
    percentage: int = Field(..., ge=0, le=100)
    reason: str = Field(..., min_length=1)
    exit_type: str = Field(
        ..., 
        pattern="^(take_profit|stop_loss|trend_reversal|risk_management|time_stop|none)$"
    )
    confidence: float = Field(..., ge=0.0, le=1.0)
    urgency: str = Field(..., pattern="^(immediate|soon|watch|none)$")

# ============ 다중 종목 설정 ============
SYMBOL_CONFIG = {
    'BTC/USDT': {
        'leverage': 10,
        'position_size_percent': 30,
        'min_position_size': 10,
        'max_position_size': 100000,
        'enabled': True,
        'ai_validation': True,
        'ai_monitoring': True
    },
    'ETH/USDT': {
        'leverage': 10,
        'position_size_percent': 30,
        'min_position_size': 10,
        'max_position_size': 100000,
        'enabled': True,
        'ai_validation': True,
        'ai_monitoring': True
    },
    'SOL/USDT': {
        'leverage': 10,
        'position_size_percent': 25,
        'min_position_size': 10,
        'max_position_size': 100000,
        'enabled': True,
        'ai_validation': True,
        'ai_monitoring': True
    },
}

def init_database():
    """데이터베이스 초기화 - 한 번만 실행"""
    conn = sqlite3.connect(DB_FILENAME)
    c = conn.cursor()
    
    # trades 테이블
    c.execute('''CREATE TABLE IF NOT EXISTS trades
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  timestamp TEXT,
                  symbol TEXT,
                  trade_type TEXT,
                  ai_decision TEXT,
                  action TEXT,
                  amount REAL,
                  entry_price REAL,
                  current_price REAL,
                  stop_loss REAL,
                  take_profit REAL,
                  pl_ratio REAL,
                  reason TEXT,
                  confidence REAL,
                  balance_before REAL,
                  balance_after REAL,
                  success BOOLEAN,
                  user_name TEXT,
                  port INTEGER)''')
    
    # completed_trades 테이블
    c.execute('''CREATE TABLE IF NOT EXISTS completed_trades
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  symbol TEXT,
                  side TEXT,
                  entry_price REAL,
                  exit_price REAL,
                  amount REAL,
                  entry_time TEXT,
                  exit_time TEXT,
                  profit_usdt REAL,
                  profit_percentage REAL,
                  close_reason TEXT,
                  max_profit REAL,
                  max_loss REAL,
                  duration_hours REAL,
                  user_name TEXT,
                  port INTEGER)''')
    
    # positions 테이블
    c.execute('''CREATE TABLE IF NOT EXISTS positions
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  symbol TEXT,
                  side TEXT,
                  amount REAL,
                  entry_price REAL,
                  current_price REAL,
                  unrealized_pnl REAL,
                  percentage REAL,
                  margin REAL,
                  last_updated TEXT,
                  user_name TEXT,
                  port INTEGER,
                  UNIQUE(symbol, user_name))''')
    
    conn.commit()
    conn.close()
    print(f"✅ 데이터베이스 초기화 완료: {DB_FILENAME}")

class TradingServer:
    """각 포트별 독립 트레이딩 서버"""
    
    def __init__(self, port, config):
        self.port = port
        self.config = config
        self.user_name = config['name']
        self.enable_telegram = config['enable_telegram']
        self.enable_db_write = config['enable_db_write']
        self.ai_monitor_interval = config['ai_monitor_interval']
        
        # Flask 앱 생성
        self.app = Flask(f"trading_server_{port}")
        
        # 로깅 설정
        self.logger = self.setup_logger()
        
        # Binance 설정
        self.exchange = self.setup_exchange()
        
        # 텔레그램 설정
        self.telegram_bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
        self.telegram_chat_ids = os.getenv('TELEGRAM_CHAT_IDS', '').split(',')
        
        # 라우트 설정
        self.setup_routes()
        
    def setup_logger(self):
        """로거 설정"""
        logger = logging.getLogger(f'trading_{self.port}')
        logger.setLevel(logging.INFO)
        
        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            f'%(asctime)s - [Port:{self.port}|{self.user_name}] - %(levelname)s - %(message)s'
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        
        return logger
    
    def setup_exchange(self):
        """Binance Exchange 설정"""
        api_key = os.getenv(self.config['api_key_env'])
        secret_key = os.getenv(self.config['secret_key_env'])
        
        if not api_key or not secret_key:
            self.logger.error(f"❌ API 키를 찾을 수 없습니다: {self.user_name}")
            return None
        
        exchange = ccxt.binance({
            'apiKey': api_key,
            'secret': secret_key,
            'enableRateLimit': True,
            'options': {
                'defaultType': 'future'
            }
        })
        
        self.logger.info(f"✅ Binance API 설정 완료: {self.user_name}")
        return exchange
    
    def get_db_connection(self):
        """데이터베이스 연결"""
        conn = sqlite3.connect(DB_FILENAME)
        conn.row_factory = sqlite3.Row
        return conn
    
    def send_telegram_message(self, message):
        """텔레그램 메시지 전송"""
        if not self.enable_telegram:
            self.logger.info(f"텔레그램 비활성화 - 메시지 스킵")
            return
            
        if not self.telegram_bot_token or not self.telegram_chat_ids:
            return
        
        url = f"https://api.telegram.org/bot{self.telegram_bot_token}/sendMessage"
        
        for chat_id in self.telegram_chat_ids:
            if not chat_id:
                continue
                
            payload = {
                "chat_id": chat_id,
                "text": f"[{self.user_name}:{self.port}]\n{message}",
                "parse_mode": "Markdown",
                "disable_web_page_preview": True
            }
            
            try:
                response = requests.post(url, json=payload, timeout=10)
                if response.status_code != 200:
                    self.logger.error(f"텔레그램 메시지 전송 실패: {response.text}")
            except Exception as e:
                self.logger.error(f"텔레그램 메시지 전송 중 오류: {e}")
    
    def setup_routes(self):
        """Flask 라우트 설정"""
        
        @self.app.route('/status', methods=['GET'])
        def status():
            """서버 상태 확인"""
            try:
                if not self.exchange:
                    return jsonify({
                        'status': 'error',
                        'user': self.user_name,
                        'port': self.port,
                        'error': 'Exchange not configured'
                    }), 500
                
                balance = self.exchange.fetch_balance()
                positions = self.exchange.fetch_positions()
                
                active_positions = [p for p in positions if p['contracts'] > 0]
                
                return jsonify({
                    'status': 'running',
                    'user': self.user_name,
                    'port': self.port,
                    'telegram': self.enable_telegram,
                    'db_mode': 'read-write' if self.enable_db_write else 'read-only',
                    'db_file': DB_FILENAME,
                    'balance': balance['USDT']['total'],
                    'free_balance': balance['USDT']['free'],
                    'used_balance': balance['USDT']['used'],
                    'active_positions': len(active_positions),
                    'positions_detail': [{
                        'symbol': p['symbol'],
                        'side': p['side'],
                        'contracts': p['contracts'],
                        'pnl': p.get('percentage', 0)
                    } for p in active_positions],
                    'symbols': list(SYMBOL_CONFIG.keys()),
                    'api_configured': True
                }), 200
            except Exception as e:
                return jsonify({
                    'status': 'error',
                    'user': self.user_name,
                    'port': self.port,
                    'db_mode': 'read-write' if self.enable_db_write else 'read-only',
                    'error': str(e)
                }), 500
        
        @self.app.route('/webhook', methods=['POST'])
        def webhook():
            """TradingView 웹훅 수신"""
            try:
                data = request.get_json()
                
                if not data:
                    return jsonify({'error': 'No data received'}), 400
                
                symbol = data.get('symbol', 'BTC/USDT')
                action = data.get('action', '').lower()
                
                if symbol not in SYMBOL_CONFIG:
                    self.logger.warning(f"미등록 심볼: {symbol}")
                    return jsonify({'error': f'Symbol {symbol} not configured'}), 400
                
                if not SYMBOL_CONFIG[symbol].get('enabled', False):
                    self.logger.info(f"비활성화된 심볼: {symbol}")
                    return jsonify({'status': 'Symbol disabled'}), 200
                
                self.logger.info(f"📨 웹훅 수신: {symbol} - {action}")
                
                # 여기에 실제 거래 로직 구현
                # (기존 코드의 거래 로직을 여기에 추가)
                
                # DB 저장 예시
                if self.enable_db_write:
                    conn = self.get_db_connection()
                    c = conn.cursor()
                    c.execute("""INSERT INTO trades 
                                (timestamp, symbol, trade_type, action, user_name, port)
                                VALUES (?, ?, ?, ?, ?, ?)""",
                             (datetime.now().isoformat(), symbol, 'WEBHOOK', 
                              action, self.user_name, self.port))
                    conn.commit()
                    conn.close()
                    self.logger.info(f"✅ DB 기록 완료")
                else:
                    self.logger.info(f"⏭️  DB 기록 스킵 (읽기 전용)")
                
                return jsonify({'status': 'processed'}), 200
                
            except Exception as e:
                self.logger.error(f"웹훅 처리 중 오류: {e}")
                return jsonify({'error': str(e)}), 500
        
        @self.app.route('/positions', methods=['GET'])
        def get_positions():
            """현재 포지션 조회"""
            try:
                if not self.exchange:
                    return jsonify({'error': 'Exchange not configured'}), 500
                    
                positions = self.exchange.fetch_positions()
                active_positions = []
                
                for position in positions:
                    if position['contracts'] > 0:
                        active_positions.append({
                            'symbol': position['symbol'],
                            'side': position['side'],
                            'contracts': position['contracts'],
                            'entryPrice': position['entryPrice'],
                            'markPrice': position['markPrice'],
                            'pnl': position.get('percentage', 0),
                            'user': self.user_name
                        })
                
                return jsonify(active_positions), 200
            except Exception as e:
                return jsonify({'error': str(e)}), 500
        
        @self.app.route('/health', methods=['GET'])
        def health():
            """헬스체크"""
            return jsonify({
                'status': 'healthy',
                'user': self.user_name,
                'port': self.port,
                'timestamp': datetime.now().isoformat()
            }), 200
    
    def monitor_positions(self):
        """포지션 모니터링 스레드"""
        while True:
            try:
                time.sleep(self.ai_monitor_interval * 60)
                
                if not self.exchange:
                    continue
                
                positions = self.exchange.fetch_positions()
                
                for position in positions:
                    if position['contracts'] > 0:
                        symbol = position['symbol']
                        
                        if SYMBOL_CONFIG.get(symbol, {}).get('ai_monitoring', False):
                            self.logger.info(f"🔍 포지션 모니터링: {symbol}")
                            # AI 모니터링 로직 구현
                            
            except Exception as e:
                self.logger.error(f"포지션 모니터링 중 오류: {e}")
                time.sleep(60)
    
    def run(self):
        """서버 실행"""
        # 모니터링 스레드 시작
        if self.ai_monitor_interval > 0:
            monitor_thread = threading.Thread(target=self.monitor_positions, daemon=True)
            monitor_thread.start()
            self.logger.info(f"✅ 포지션 모니터링 시작 (간격: {self.ai_monitor_interval}분)")
        
        # 시작 알림
        self.logger.info(f"🚀 트레이딩 서버 시작 - {self.user_name} (포트: {self.port})")
        self.logger.info(f"💾 DB 모드: {'쓰기/읽기' if self.enable_db_write else '읽기 전용'}")
        
        if self.enable_telegram:
            self.send_telegram_message(
                f"🚀 *트레이딩 봇 시작*\n\n"
                f"👤 사용자: {self.user_name}\n"
                f"🔌 포트: {self.port}\n"
                f"💾 DB 모드: {'쓰기/읽기' if self.enable_db_write else '읽기 전용'}\n"
                f"📊 활성 심볼: {', '.join([s for s in SYMBOL_CONFIG.keys() if SYMBOL_CONFIG[s]['enabled']])}"
            )
        
        # Flask 서버 실행
        self.app.run(host='0.0.0.0', port=self.port, debug=False, use_reloader=False)

def run_server(port, config):
    """각 서버 프로세스 실행 함수"""
    server = TradingServer(port, config)
    server.run()

def signal_handler(signum, frame):
    """종료 시그널 처리"""
    print("\n🛑 모든 서버 종료 중...")
    for process in processes:
        if process.is_alive():
            process.terminate()
    sys.exit(0)

if __name__ == '__main__':
    # DB 초기화 (한 번만)
    init_database()
    
    # 프로세스 리스트
    processes = []
    
    # 종료 시그널 처리
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    print("="*60)
    print("   통합 트레이딩 시스템 v6 - 멀티 유저 동시 실행")
    print("="*60)
    print()
    
    # 각 포트별로 프로세스 시작
    for port, config in USERS_CONFIG.items():
        print(f"🚀 시작 중: {config['name']} (포트 {port})")
        process = Process(target=run_server, args=(port, config))
        process.start()
        processes.append(process)
        time.sleep(1)  # 서버 시작 간격
    
    print()
    print("✅ 모든 서버가 시작되었습니다!")
    print()
    print("📊 상태 확인:")
    for port, config in USERS_CONFIG.items():
        print(f"  - {config['name']}: http://localhost:{port}/status")
    print()
    print("📝 웹훅 URL:")
    for port, config in USERS_CONFIG.items():
        print(f"  - {config['name']}: http://your-server-ip:{port}/webhook")
    print()
    print("🛑 종료: Ctrl+C")
    print()
    
    # 메인 프로세스는 대기
    try:
        for process in processes:
            process.join()
    except KeyboardInterrupt:
        print("\n종료 중...")
        for process in processes:
            if process.is_alive():
                process.terminate()
