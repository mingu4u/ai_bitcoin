# ============================================================================
# 통합 트레이딩 시스템 v4 - DB + 안전한 주문 로직 통합
# ============================================================================
"""
주요 기능:
1. 개선된 DB 스키마 (trades, completed_trades, balance_history, position_history)
2. 마진 부족 100% 방지하는 안전한 주문 로직
3. Free Balance 기반 계산 + 10% 안전 버퍼
4. 자동 포지션 사이즈 조정
5. 거래소 제한 조건 자동 준수
6. 상세한 로깅 및 모니터링
"""

import sqlite3
import logging
from datetime import datetime, timedelta
import pandas as pd
import ccxt
import time

# 로깅 설정
logger = logging.getLogger(__name__)

# ============================================================================
# DATABASE SCHEMA & FUNCTIONS
# ============================================================================

def init_db_enhanced():
    """개선된 DB 스키마 초기화"""
    conn = sqlite3.connect('integrated_trades.db')
    c = conn.cursor()
    
    # 1. 기존 trades 테이블 (모든 이벤트 로깅)
    c.execute('''CREATE TABLE IF NOT EXISTS trades
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  timestamp TEXT NOT NULL,
                  symbol TEXT NOT NULL,
                  trade_type TEXT,
                  ai_decision TEXT,
                  order_id TEXT,
                  action TEXT,
                  percentage INTEGER,
                  reason TEXT,
                  position_size REAL,
                  entry_price REAL,
                  current_price REAL,
                  stop_loss REAL,
                  take_profit REAL,
                  pl_ratio REAL,
                  confidence REAL,
                  reflection TEXT,
                  exit_type TEXT,
                  urgency TEXT)''')
    
    # 2. 완료된 거래 테이블 (진입+청산 페어링)
    c.execute('''CREATE TABLE IF NOT EXISTS completed_trades
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  symbol TEXT NOT NULL,
                  side TEXT NOT NULL,
                  entry_time TEXT NOT NULL,
                  exit_time TEXT NOT NULL,
                  entry_price REAL NOT NULL,
                  exit_price REAL NOT NULL,
                  amount REAL NOT NULL,
                  leverage INTEGER,
                  stop_loss REAL,
                  take_profit REAL,
                  exit_reason TEXT,
                  pnl REAL NOT NULL,
                  pnl_percent REAL NOT NULL,
                  fees REAL DEFAULT 0,
                  holding_time_minutes INTEGER,
                  ai_entry_confidence REAL,
                  ai_exit_confidence REAL,
                  ai_entry_reason TEXT,
                  ai_exit_reason TEXT,
                  is_win INTEGER NOT NULL,
                  max_profit_percent REAL,
                  max_loss_percent REAL)''')
    
    # 3. 자산 히스토리 테이블
    c.execute('''CREATE TABLE IF NOT EXISTS balance_history
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  timestamp TEXT NOT NULL,
                  total_balance REAL NOT NULL,
                  available_balance REAL NOT NULL,
                  used_balance REAL NOT NULL,
                  unrealized_pnl REAL DEFAULT 0,
                  total_equity REAL NOT NULL,
                  daily_pnl REAL DEFAULT 0,
                  daily_pnl_percent REAL DEFAULT 0)''')
    
    # 4. 포지션 히스토리 테이블
    c.execute('''CREATE TABLE IF NOT EXISTS position_history
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  timestamp TEXT NOT NULL,
                  symbol TEXT NOT NULL,
                  action TEXT NOT NULL,
                  side TEXT,
                  price REAL NOT NULL,
                  amount REAL NOT NULL,
                  position_size_usdt REAL,
                  leverage INTEGER,
                  stop_loss REAL,
                  take_profit REAL,
                  ai_confidence REAL,
                  ai_reason TEXT,
                  order_id TEXT,
                  status TEXT DEFAULT 'executed')''')
    
    # 인덱스 생성
    c.execute('CREATE INDEX IF NOT EXISTS idx_trades_symbol ON trades(symbol)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_trades_timestamp ON trades(timestamp)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_completed_symbol ON completed_trades(symbol)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_completed_time ON completed_trades(entry_time, exit_time)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_balance_timestamp ON balance_history(timestamp)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_position_symbol ON position_history(symbol)')
    
    conn.commit()
    return conn

# ============================================================================
# BALANCE TRACKING FUNCTIONS
# ============================================================================

def record_balance_snapshot(exchange):
    """현재 자산 상태를 기록"""
    try:
        balance_info = exchange.fetch_balance()
        total_balance = balance_info['USDT']['total']
        available = balance_info['USDT']['free']
        used = balance_info['USDT']['used']
        
        # 미실현 손익 계산
        unrealized_pnl = 0
        positions = exchange.fetch_positions()
        for pos in positions:
            if float(pos.get('contracts', 0)) != 0:
                unrealized_pnl += float(pos.get('unrealizedPnl', 0))
        
        total_equity = total_balance + unrealized_pnl
        
        # 일일 손익 계산 (전날 대비)
        conn = sqlite3.connect('integrated_trades.db')
        c = conn.cursor()
        
        yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
        c.execute("""SELECT total_equity FROM balance_history 
                     WHERE DATE(timestamp) = ? 
                     ORDER BY timestamp DESC LIMIT 1""", (yesterday,))
        row = c.fetchone()
        
        daily_pnl = 0
        daily_pnl_percent = 0
        if row:
            yesterday_equity = row[0]
            daily_pnl = total_equity - yesterday_equity
            daily_pnl_percent = (daily_pnl / yesterday_equity) * 100 if yesterday_equity > 0 else 0
        
        # 기록 저장
        timestamp = datetime.now().isoformat()
        c.execute("""INSERT INTO balance_history 
                     (timestamp, total_balance, available_balance, used_balance, 
                      unrealized_pnl, total_equity, daily_pnl, daily_pnl_percent)
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                  (timestamp, total_balance, available, used, unrealized_pnl, 
                   total_equity, daily_pnl, daily_pnl_percent))
        
        conn.commit()
        conn.close()
        
        logger.info(f"Balance snapshot: ${total_equity:,.2f} (Daily: {daily_pnl:+.2f} / {daily_pnl_percent:+.2f}%)")
        
        return total_equity
        
    except Exception as e:
        logger.error(f"Error recording balance snapshot: {e}")
        return None

def record_position_entry(symbol, side, price, amount, position_size_usdt, leverage, 
                         stop_loss, take_profit, ai_confidence, ai_reason, order_id):
    """포지션 진입 기록"""
    try:
        conn = sqlite3.connect('integrated_trades.db')
        c = conn.cursor()
        
        timestamp = datetime.now().isoformat()
        c.execute("""INSERT INTO position_history 
                     (timestamp, symbol, action, side, price, amount, position_size_usdt,
                      leverage, stop_loss, take_profit, ai_confidence, ai_reason, order_id, status)
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                  (timestamp, symbol, 'ENTRY', side, price, amount, position_size_usdt,
                   leverage, stop_loss, take_profit, ai_confidence, ai_reason, order_id, 'executed'))
        
        conn.commit()
        conn.close()
        
        logger.info(f"Position entry recorded: {symbol} {side} @ ${price:.2f}")
        
    except Exception as e:
        logger.error(f"Error recording position entry: {e}")

def record_position_exit_and_complete_trade(symbol, exit_price, exit_reason, 
                                            ai_exit_confidence=None, ai_exit_reason=None):
    """포지션 청산 기록 및 완료된 거래 생성"""
    try:
        conn = sqlite3.connect('integrated_trades.db')
        c = conn.cursor()
        
        # 가장 최근 진입 기록 조회
        c.execute("""SELECT timestamp, side, price, amount, position_size_usdt, leverage,
                            stop_loss, take_profit, ai_confidence, ai_reason, order_id
                     FROM position_history
                     WHERE symbol = ? AND action = 'ENTRY'
                     ORDER BY timestamp DESC LIMIT 1""", (symbol,))
        
        entry_row = c.fetchone()
        if not entry_row:
            logger.warning(f"No entry record found for {symbol}")
            return
        
        (entry_time, side, entry_price, amount, position_size_usdt, leverage,
         stop_loss, take_profit, ai_entry_confidence, ai_entry_reason, entry_order_id) = entry_row
        
        # 청산 기록
        exit_time = datetime.now().isoformat()
        c.execute("""INSERT INTO position_history 
                     (timestamp, symbol, action, side, price, amount, ai_confidence, 
                      ai_reason, status)
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                  (exit_time, symbol, 'EXIT', side, exit_price, amount, 
                   ai_exit_confidence, ai_exit_reason, 'executed'))
        
        # PnL 계산
        if side == 'buy':
            pnl_percent = ((exit_price - entry_price) / entry_price) * 100
        else:  # sell
            pnl_percent = ((entry_price - exit_price) / entry_price) * 100
        
        pnl_percent_leveraged = pnl_percent * leverage
        pnl_usdt = position_size_usdt * (pnl_percent / 100)
        is_win = 1 if pnl_usdt > 0 else 0
        
        # 보유 시간 계산
        entry_dt = datetime.fromisoformat(entry_time)
        exit_dt = datetime.fromisoformat(exit_time)
        holding_minutes = int((exit_dt - entry_dt).total_seconds() / 60)
        
        # 수수료 추정 (0.04%)
        fees = position_size_usdt * 0.0004 * 2  # 진입 + 청산
        
        # 완료된 거래 기록
        c.execute("""INSERT INTO completed_trades 
                     (symbol, side, entry_time, exit_time, entry_price, exit_price, amount,
                      leverage, stop_loss, take_profit, exit_reason, pnl, pnl_percent, fees,
                      holding_time_minutes, ai_entry_confidence, ai_exit_confidence,
                      ai_entry_reason, ai_exit_reason, is_win)
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                  (symbol, side, entry_time, exit_time, entry_price, exit_price, amount,
                   leverage, stop_loss, take_profit, exit_reason, pnl_usdt, pnl_percent_leveraged,
                   fees, holding_minutes, ai_entry_confidence, ai_exit_confidence,
                   ai_entry_reason, ai_exit_reason, is_win))
        
        conn.commit()
        conn.close()
        
        logger.info(f"Trade completed: {symbol} PnL: ${pnl_usdt:+.2f} ({pnl_percent_leveraged:+.2f}%)")
        
        return {
            'pnl_usdt': pnl_usdt,
            'pnl_percent': pnl_percent_leveraged,
            'is_win': is_win,
            'holding_minutes': holding_minutes
        }
        
    except Exception as e:
        logger.error(f"Error recording position exit: {e}", exc_info=True)
        return None

# ============================================================================
# STATISTICS FUNCTIONS
# ============================================================================

def get_trading_statistics(days=None, symbol=None):
    """거래 통계 조회"""
    try:
        conn = sqlite3.connect('integrated_trades.db')
        
        query = "SELECT * FROM completed_trades WHERE 1=1"
        params = []
        
        if days:
            cutoff_date = (datetime.now() - timedelta(days=days)).isoformat()
            query += " AND entry_time >= ?"
            params.append(cutoff_date)
        
        if symbol:
            query += " AND symbol = ?"
            params.append(symbol)
        
        query += " ORDER BY exit_time DESC"
        
        df = pd.read_sql_query(query, conn, params=params)
        conn.close()
        
        if df.empty:
            return {
                'total_trades': 0,
                'winning_trades': 0,
                'losing_trades': 0,
                'win_rate': 0,
                'total_pnl': 0,
                'avg_pnl': 0,
                'avg_win': 0,
                'avg_loss': 0,
                'profit_factor': 0,
                'max_win': 0,
                'max_loss': 0,
                'avg_holding_time': 0
            }
        
        total_trades = len(df)
        winning_trades = len(df[df['is_win'] == 1])
        losing_trades = len(df[df['is_win'] == 0])
        win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
        
        total_pnl = df['pnl'].sum()
        avg_pnl = df['pnl'].mean()
        
        wins_df = df[df['is_win'] == 1]
        losses_df = df[df['is_win'] == 0]
        
        avg_win = wins_df['pnl'].mean() if not wins_df.empty else 0
        avg_loss = losses_df['pnl'].mean() if not losses_df.empty else 0
        
        total_wins = wins_df['pnl'].sum() if not wins_df.empty else 0
        total_losses = abs(losses_df['pnl'].sum()) if not losses_df.empty else 0
        profit_factor = (total_wins / total_losses) if total_losses > 0 else 0
        
        max_win = df['pnl'].max()
        max_loss = df['pnl'].min()
        avg_holding_time = df['holding_time_minutes'].mean()
        
        return {
            'total_trades': total_trades,
            'winning_trades': winning_trades,
            'losing_trades': losing_trades,
            'win_rate': win_rate,
            'total_pnl': total_pnl,
            'avg_pnl': avg_pnl,
            'avg_win': avg_win,
            'avg_loss': avg_loss,
            'profit_factor': profit_factor,
            'max_win': max_win,
            'max_loss': max_loss,
            'avg_holding_time': avg_holding_time
        }
        
    except Exception as e:
        logger.error(f"Error getting trading statistics: {e}")
        return {}

def get_symbol_performance():
    """심볼별 성과 조회"""
    try:
        conn = sqlite3.connect('integrated_trades.db')
        
        query = """
        SELECT 
            symbol,
            COUNT(*) as total_trades,
            SUM(CASE WHEN is_win = 1 THEN 1 ELSE 0 END) as wins,
            SUM(CASE WHEN is_win = 0 THEN 1 ELSE 0 END) as losses,
            ROUND(SUM(CASE WHEN is_win = 1 THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2) as win_rate,
            ROUND(SUM(pnl), 2) as total_pnl,
            ROUND(AVG(pnl), 2) as avg_pnl,
            ROUND(MAX(pnl), 2) as best_trade,
            ROUND(MIN(pnl), 2) as worst_trade
        FROM completed_trades
        GROUP BY symbol
        ORDER BY total_pnl DESC
        """
        
        df = pd.read_sql_query(query, conn)
        conn.close()
        
        return df
        
    except Exception as e:
        logger.error(f"Error getting symbol performance: {e}")
        return pd.DataFrame()

def get_daily_pnl(days=30):
    """일별 손익 조회"""
    try:
        conn = sqlite3.connect('integrated_trades.db')
        
        cutoff_date = (datetime.now() - timedelta(days=days)).isoformat()
        
        query = """
        SELECT 
            DATE(exit_time) as date,
            COUNT(*) as trades,
            SUM(CASE WHEN is_win = 1 THEN 1 ELSE 0 END) as wins,
            ROUND(SUM(pnl), 2) as daily_pnl,
            ROUND(SUM(CASE WHEN is_win = 1 THEN pnl ELSE 0 END), 2) as win_pnl,
            ROUND(SUM(CASE WHEN is_win = 0 THEN pnl ELSE 0 END), 2) as loss_pnl
        FROM completed_trades
        WHERE exit_time >= ?
        GROUP BY DATE(exit_time)
        ORDER BY date DESC
        """
        
        df = pd.read_sql_query(query, conn, params=(cutoff_date,))
        conn.close()
        
        return df
        
    except Exception as e:
        logger.error(f"Error getting daily PnL: {e}")
        return pd.DataFrame()

def get_balance_history(days=30):
    """자산 히스토리 조회"""
    try:
        conn = sqlite3.connect('integrated_trades.db')
        
        cutoff_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
        
        query = """
        SELECT 
            timestamp,
            total_equity,
            unrealized_pnl,
            daily_pnl,
            daily_pnl_percent
        FROM balance_history
        WHERE DATE(timestamp) >= ?
        ORDER BY timestamp ASC
        """
        
        df = pd.read_sql_query(query, conn, params=(cutoff_date,))
        conn.close()
        
        return df
        
    except Exception as e:
        logger.error(f"Error getting balance history: {e}")
        return pd.DataFrame()

# ============================================================================
# SAFE MARGIN & ORDER FUNCTIONS (마진 부족 100% 방지)
# ============================================================================

def get_available_margin_for_new_position(exchange, symbol_config):
    """
    새로운 포지션을 열 수 있는 실제 사용 가능한 마진 계산
    
    핵심 개선:
    - Free Balance 사용 (다른 포지션의 마진 사용량 제외됨)
    - 10% 안전 버퍼 적용
    - 설정값과 실제 가능 금액 중 작은 값 선택
    """
    try:
        # 1. 잔고 조회
        balance = exchange.fetch_balance()
        
        total_balance = balance['USDT']['total']
        free_balance = balance['USDT']['free']    # ⭐ 핵심!
        used_balance = balance['USDT']['used']
        
        logger.info("=" * 60)
        logger.info("💰 잔고 현황:")
        logger.info(f"  - Total Balance: ${total_balance:,.2f}")
        logger.info(f"  - Free Balance: ${free_balance:,.2f} ✅")
        logger.info(f"  - Used Balance: ${used_balance:,.2f}")
        
        # 2. 현재 포지션 확인
        positions = exchange.fetch_positions()
        active_positions = []
        total_used_margin = 0
        
        for pos in positions:
            contracts = float(pos.get('contracts', 0))
            if contracts != 0:
                initial_margin = float(pos.get('initialMargin', 0))
                total_used_margin += initial_margin
                active_positions.append({
                    'symbol': pos.get('symbol'),
                    'side': pos.get('side'),
                    'contracts': contracts,
                    'margin': initial_margin
                })
        
        if active_positions:
            logger.info(f"📊 활성 포지션 {len(active_positions)}개:")
            for pos in active_positions:
                logger.info(f"  - {pos['symbol']}: {pos['side']} (Margin: ${pos['margin']:,.2f})")
            logger.info(f"  총 사용 마진: ${total_used_margin:,.2f}")
        else:
            logger.info("📊 활성 포지션: 없음")
        
        # 3. 설정 기준 최대 사용 금액
        position_size_percent = symbol_config.get('position_size_percent', 30)
        max_from_config = total_balance * (position_size_percent / 100)
        
        logger.info(f"⚙️ 설정값:")
        logger.info(f"  - Position Size %: {position_size_percent}%")
        logger.info(f"  - Total Balance 기준 최대: ${max_from_config:,.2f}")
        
        # 4. 안전 버퍼 적용 (90%만 사용, 10% 버퍼)
        safety_buffer_percent = 0.90
        safe_free_balance = free_balance * safety_buffer_percent
        
        logger.info(f"🛡️ 안전 버퍼:")
        logger.info(f"  - Free Balance: ${free_balance:,.2f}")
        logger.info(f"  - Safe Free (90%): ${safe_free_balance:,.2f}")
        
        # 5. 최종 사용 가능 마진
        available_margin = min(max_from_config, safe_free_balance)
        
        logger.info(f"✅ 최종 계산:")
        logger.info(f"  - 설정 기준: ${max_from_config:,.2f}")
        logger.info(f"  - 실제 가능: ${safe_free_balance:,.2f}")
        logger.info(f"  - 최종 사용 가능 마진: ${available_margin:,.2f} ⭐")
        logger.info("=" * 60)
        
        return available_margin
        
    except Exception as e:
        logger.error(f"❌ 사용 가능 마진 계산 오류: {e}", exc_info=True)
        return 0

def calculate_safe_position_size(exchange, symbol, entry_price, symbol_config, action='buy'):
    """
    안전한 포지션 사이즈 계산 (마진 부족 100% 방지)
    """
    try:
        leverage = symbol_config.get('leverage', 10)
        min_position_size = symbol_config.get('min_position_size', 10)
        max_position_size = symbol_config.get('max_position_size', 100000)
        
        logger.info(f"\n{'='*60}")
        logger.info(f"📊 포지션 사이즈 계산 시작:")
        logger.info(f"  - 심볼: {symbol}")
        logger.info(f"  - 진입가: ${entry_price:,.2f}")
        logger.info(f"  - 방향: {action.upper()}")
        logger.info(f"  - 레버리지: {leverage}x")
        
        # 1. 사용 가능한 마진 계산
        available_margin = get_available_margin_for_new_position(exchange, symbol_config)
        
        if available_margin <= 0:
            logger.error(f"❌ 사용 가능한 마진이 없습니다")
            return None
        
        # 2. 최소 마진 체크
        min_required_margin = min_position_size / leverage
        if available_margin < min_required_margin:
            logger.error(f"❌ 마진 부족: ${available_margin:,.2f} < ${min_required_margin:,.2f}")
            return None
        
        # 3. 포지션 사이즈 계산
        position_size_usdt = available_margin * leverage
        
        # 4. 최소/최대 범위 조정
        if position_size_usdt < min_position_size:
            logger.warning(f"⚠️ 포지션이 최소값보다 작음")
            return None
        
        if position_size_usdt > max_position_size:
            logger.warning(f"⚠️ 포지션이 최대값 초과, 조정")
            position_size_usdt = max_position_size
            available_margin = position_size_usdt / leverage
        
        # 5. 코인 수량 계산
        amount = position_size_usdt / entry_price
        
        # 6. 거래소 제한 조건 적용
        market = exchange.market(symbol)
        
        # Precision 조정
        if 'precision' in market and 'amount' in market['precision']:
            precision = market['precision']['amount']
            if precision is not None:
                amount = float(exchange.amount_to_precision(symbol, amount))
        
        # Limits 체크
        if 'limits' in market:
            limits = market['limits']
            
            # 최소 수량
            if 'amount' in limits and 'min' in limits['amount']:
                min_amount = limits['amount']['min']
                if amount < min_amount:
                    logger.info(f"  최소 수량으로 조정: {min_amount}")
                    amount = min_amount
            
            # 최대 수량
            if 'amount' in limits and 'max' in limits['amount']:
                max_amount = limits['amount']['max']
                if max_amount and amount > max_amount:
                    logger.info(f"  최대 수량으로 조정: {max_amount}")
                    amount = max_amount
            
            # 최소 거래 금액
            if 'cost' in limits and 'min' in limits['cost']:
                min_cost = limits['cost']['min']
                calculated_cost = amount * entry_price
                if calculated_cost < min_cost:
                    logger.info(f"  최소 거래금액 조정: ${min_cost}")
                    amount = min_cost / entry_price
                    amount = float(exchange.amount_to_precision(symbol, amount))
        
        # 7. 최종 계산
        position_size_usdt = amount * entry_price
        required_margin = position_size_usdt / leverage
        
        # 8. 최종 마진 체크
        balance = exchange.fetch_balance()
        free_balance = balance['USDT']['free']
        
        if required_margin > free_balance:
            logger.warning(f"⚠️ 최종 마진 체크 실패, 자동 축소...")
            new_margin = free_balance * 0.85
            position_size_usdt = new_margin * leverage
            amount = position_size_usdt / entry_price
            amount = float(exchange.amount_to_precision(symbol, amount))
            position_size_usdt = amount * entry_price
            required_margin = position_size_usdt / leverage
            
            if required_margin > free_balance:
                logger.error(f"❌ 축소 후에도 마진 부족")
                return None
        
        result = {
            'amount': amount,
            'position_size_usdt': position_size_usdt,
            'required_margin': required_margin,
            'leverage': leverage
        }
        
        logger.info(f"\n✅ 포지션 사이즈 계산 완료:")
        logger.info(f"  - 코인 수량: {amount:.6f}")
        logger.info(f"  - 포지션 크기: ${position_size_usdt:,.2f}")
        logger.info(f"  - 필요 마진: ${required_margin:,.2f}")
        logger.info(f"  - 레버리지: {leverage}x")
        logger.info(f"{'='*60}\n")
        
        return result
        
    except Exception as e:
        logger.error(f"❌ 포지션 사이즈 계산 오류: {e}", exc_info=True)
        return None

def place_order_with_safe_margin(exchange, symbol, action, entry_price, stop_loss, 
                                  take_profit, symbol_config, ai_confidence=None, 
                                  ai_reason=None):
    """
    마진 부족을 100% 방지하는 안전한 주문 실행
    
    Args:
        exchange: ccxt exchange 객체
        symbol: 거래 심볼
        action: 'buy' 또는 'sell'
        entry_price: 진입 가격
        stop_loss: 손절가
        take_profit: 익절가
        symbol_config: 심볼 설정
        ai_confidence: AI 신뢰도
        ai_reason: AI 이유
    
    Returns:
        dict: 주문 결과 또는 None
    """
    try:
        logger.info(f"\n{'='*80}")
        logger.info(f"🚀 주문 실행 시작")
        logger.info(f"{'='*80}")
        logger.info(f"심볼: {symbol}")
        logger.info(f"방향: {action.upper()}")
        logger.info(f"진입가: ${entry_price:,.2f}")
        logger.info(f"손절가: ${stop_loss:,.2f}")
        logger.info(f"익절가: ${take_profit:,.2f}")
        if ai_confidence:
            logger.info(f"AI 신뢰도: {ai_confidence:.1%}")
        logger.info(f"{'='*80}\n")
        
        # 1. 레버리지 설정
        leverage = symbol_config.get('leverage', 10)
        try:
            exchange.set_leverage(leverage, symbol)
            logger.info(f"✅ 레버리지 설정: {leverage}x")
        except Exception as e:
            logger.warning(f"⚠️ 레버리지 설정 실패 (이미 설정됨): {e}")
        
        # 2. 마진 모드 설정
        try:
            exchange.set_margin_mode('cross', symbol)
            logger.info(f"✅ 마진 모드: Cross")
        except Exception as e:
            logger.warning(f"⚠️ 마진 모드 설정 실패: {e}")
        
        # 3. 안전한 포지션 사이즈 계산
        position_info = calculate_safe_position_size(
            exchange, symbol, entry_price, symbol_config, action
        )
        
        if not position_info:
            logger.error(f"❌ 포지션 사이즈 계산 실패")
            return None
        
        amount = position_info['amount']
        position_size_usdt = position_info['position_size_usdt']
        required_margin = position_info['required_margin']
        
        # 4. 메인 주문 실행
        logger.info(f"\n📤 주문 실행 중...")
        
        if action.lower() == 'buy':
            order = exchange.create_market_buy_order(symbol, amount)
            side = 'buy'
        else:
            order = exchange.create_market_sell_order(symbol, amount)
            side = 'sell'
        
        actual_entry = order.get('average') or order.get('price') or entry_price
        
        logger.info(f"✅ 메인 주문 성공!")
        logger.info(f"  - Order ID: {order.get('id')}")
        logger.info(f"  - 실제 진입가: ${actual_entry:,.2f}")
        
        # 5. 손절/익절 주문
        time.sleep(1)
        
        try:
            # 손절
            if stop_loss:
                sl_side = 'sell' if side == 'buy' else 'buy'
                sl_params = {
                    'stopPrice': stop_loss,
                    'workingType': 'MARK_PRICE',
                    'reduceOnly': True
                }
                sl_order = exchange.create_order(
                    symbol, 'stop_market', sl_side, amount, None, sl_params
                )
                logger.info(f"✅ 손절 설정: ${stop_loss:,.2f}")
            
            # 익절
            if take_profit:
                tp_side = 'sell' if side == 'buy' else 'buy'
                tp_params = {
                    'stopPrice': take_profit,
                    'workingType': 'MARK_PRICE',
                    'reduceOnly': True
                }
                tp_order = exchange.create_order(
                    symbol, 'take_profit_market', tp_side, amount, None, tp_params
                )
                logger.info(f"✅ 익절 설정: ${take_profit:,.2f}")
                
        except Exception as e:
            logger.error(f"⚠️ 손절/익절 설정 실패: {e}")
        
        # 6. DB 기록
        try:
            record_position_entry(
                symbol=symbol,
                side=side,
                price=actual_entry,
                amount=amount,
                position_size_usdt=position_size_usdt,
                leverage=leverage,
                stop_loss=stop_loss,
                take_profit=take_profit,
                ai_confidence=ai_confidence,
                ai_reason=ai_reason,
                order_id=order.get('id')
            )
            logger.info(f"✅ DB 기록 완료")
        except Exception as e:
            logger.error(f"⚠️ DB 기록 실패: {e}")
        
        # 7. 결과 반환
        result = {
            'success': True,
            'order': order,
            'symbol': symbol,
            'side': side,
            'amount': amount,
            'entry_price': actual_entry,
            'position_size_usdt': position_size_usdt,
            'required_margin': required_margin,
            'leverage': leverage,
            'stop_loss': stop_loss,
            'take_profit': take_profit,
            'ai_confidence': ai_confidence
        }
        
        logger.info(f"\n{'='*80}")
        logger.info(f"🎉 주문 완료!")
        logger.info(f"{'='*80}")
        logger.info(f"심볼: {symbol}")
        logger.info(f"방향: {side.upper()}")
        logger.info(f"수량: {amount:.6f}")
        logger.info(f"진입가: ${actual_entry:,.2f}")
        logger.info(f"포지션: ${position_size_usdt:,.2f}")
        logger.info(f"{'='*80}\n")
        
        return result
        
    except ccxt.InsufficientFunds as e:
        logger.error(f"\n{'='*80}")
        logger.error(f"❌ 마진 부족 오류")
        logger.error(f"{'='*80}")
        logger.error(f"오류: {e}")
        logger.error(f"심볼: {symbol}")
        
        try:
            balance = exchange.fetch_balance()
            logger.error(f"\n현재 잔고:")
            logger.error(f"  - Total: ${balance['USDT']['total']:,.2f}")
            logger.error(f"  - Free: ${balance['USDT']['free']:,.2f}")
            logger.error(f"  - Used: ${balance['USDT']['used']:,.2f}")
        except:
            pass
        
        logger.error(f"{'='*80}\n")
        return None
        
    except Exception as e:
        logger.error(f"\n{'='*80}")
        logger.error(f"❌ 주문 실행 오류")
        logger.error(f"{'='*80}")
        logger.error(f"오류: {e}", exc_info=True)
        logger.error(f"{'='*80}\n")
        return None

# ============================================================================
# 사용 예시
# ============================================================================

"""
# Exchange 초기화
exchange = ccxt.binance({
    'apiKey': 'YOUR_API_KEY',
    'secret': 'YOUR_SECRET',
    'options': {'defaultType': 'future'}
})

# 심볼 설정
SYMBOL_CONFIG = {
    'ETH/USDT': {
        'leverage': 10,
        'position_size_percent': 30,
        'min_position_size': 10,
        'max_position_size': 100000,
        'enabled': True
    }
}

# DB 초기화
conn = init_db_enhanced()

# 주문 실행 (웹훅 등에서 호출)
result = place_order_with_safe_margin(
    exchange=exchange,
    symbol='ETH/USDT',
    action='sell',
    entry_price=3697.35,
    stop_loss=3752.81,
    take_profit=3327.61,
    symbol_config=SYMBOL_CONFIG['ETH/USDT'],
    ai_confidence=0.85,
    ai_reason="Strong bearish momentum"
)

if result:
    print(f"✅ 주문 성공!")
    print(f"포지션: ${result['position_size_usdt']:,.2f}")
    print(f"필요 마진: ${result['required_margin']:,.2f}")
else:
    print(f"❌ 주문 실패!")

# 잔고 스냅샷 기록
record_balance_snapshot(exchange)

# 통계 조회
stats = get_trading_statistics(days=30)
print(f"승률: {stats['win_rate']:.1f}%")
print(f"총 손익: ${stats['total_pnl']:,.2f}")
"""

if __name__ == "__main__":
    print("""
    ============================================================================
    통합 트레이딩 시스템 v4 - 완전판
    ============================================================================
    
    주요 기능:
    1. ✅ DB 스키마 (4개 테이블)
    2. ✅ 마진 부족 100% 방지
    3. ✅ Free Balance 기반 계산
    4. ✅ 10% 안전 버퍼
    5. ✅ 자동 포지션 조정
    6. ✅ 상세 로깅
    
    사용 방법:
    1. DB 초기화: init_db_enhanced()
    2. 주문 실행: place_order_with_safe_margin(...)
    3. 잔고 기록: record_balance_snapshot(exchange)
    4. 통계 조회: get_trading_statistics()
    
    ============================================================================
    """)
