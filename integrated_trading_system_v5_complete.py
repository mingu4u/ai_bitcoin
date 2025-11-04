#!/usr/bin/env python3
"""
v5 봇 패치 스크립트
포지션 종료 시 completed_trades 테이블에 자동 기록하도록 수정
"""

import os
import shutil
from datetime import datetime

def patch_v5_bot():
    """v5 봇 코드 패치"""
    
    print("=" * 60)
    print("🔧 v5 봇 패치 시작")
    print("=" * 60)
    
    # 파일 경로
    original_file = "integrated_trading_system_v5_complete.py"
    backup_file = f"integrated_trading_system_v5_complete_{datetime.now().strftime('%Y%m%d_%H%M%S')}.py.backup"
    
    if not os.path.exists(original_file):
        print(f"❌ {original_file} 파일을 찾을 수 없습니다.")
        return False
    
    # 백업 생성
    shutil.copy2(original_file, backup_file)
    print(f"💾 백업 생성: {backup_file}")
    
    # 파일 읽기
    with open(original_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    # 패치 적용
    patches_applied = 0
    
    # 1. execute_position_exit 함수 수정
    for i, line in enumerate(lines):
        if "def execute_position_exit(symbol, decision):" in line:
            print(f"📍 execute_position_exit 함수 발견 (줄 {i+1})")
            
            # 포지션 종료 후 DB 기록 추가 (del current_positions[symbol] 찾기)
            for j in range(i, min(i+100, len(lines))):
                if "del current_positions[symbol]" in lines[j]:
                    print(f"  → 포지션 삭제 코드 발견 (줄 {j+1})")
                    
                    # record_completed_trade 호출 추가
                    indent = "            "  # 적절한 들여쓰기
                    insert_code = f"""
{indent}# 완료된 거래 DB 기록
{indent}try:
{indent}    ticker = exchange.fetch_ticker(symbol)
{indent}    exit_price = ticker['last']
{indent}    record_completed_trade(symbol, position, exit_price, decision.get('exit_type', 'ai_exit'))
{indent}    logger.info(f"✅ Completed trade recorded for {{symbol}}")
{indent}except Exception as e:
{indent}    logger.error(f"Failed to record completed trade: {{e}}")

"""
                    lines[j] = lines[j] + insert_code
                    patches_applied += 1
                    break
            break
    
    # 2. webhook 함수의 청산 처리 수정
    for i, line in enumerate(lines):
        if "def webhook():" in line:
            print(f"📍 webhook 함수 발견 (줄 {i+1})")
            
            # 포지션 청산 완료 메시지 찾기
            for j in range(i, min(i+500, len(lines))):
                if "✅ <b>포지션 청산 완료" in lines[j]:
                    print(f"  → 청산 완료 메시지 발견 (줄 {j+1})")
                    
                    # record_completed_trade 호출 추가
                    for k in range(j, j-50, -1):  # 역방향 검색
                        if "close_order = exchange.create_market_order" in lines[k]:
                            indent = "                            "
                            insert_code = f"""
{indent}# 완료된 거래 DB 기록
{indent}try:
{indent}    position_info = {{
{indent}        'entry_price': float(position['entryPrice']),
{indent}        'amount': close_amount,
{indent}        'side': 'buy' if position['side'] == 'long' else 'sell',
{indent}        'leverage': SYMBOL_CONFIG.get(symbol, {{}}).get('leverage', 10),
{indent}        'entry_time': datetime.now() - timedelta(hours=1)  # 임시
{indent}    }}
{indent}    record_completed_trade(symbol, position_info, current_price, 'ai_close')
{indent}    logger.info(f"✅ Completed trade recorded for {{symbol}}")
{indent}except Exception as e:
{indent}    logger.error(f"Failed to record completed trade: {{e}}")

"""
                            lines[k] = lines[k] + insert_code
                            patches_applied += 1
                            break
                    break
            break
    
    # 3. 일반 포지션 종료 처리 추가
    for i, line in enumerate(lines):
        if "# 포지션 종료 주문" in line or "# Position close order" in line:
            print(f"📍 포지션 종료 주문 발견 (줄 {i+1})")
            
            # 다음 몇 줄 내에서 주문 실행 후 처리
            for j in range(i, min(i+20, len(lines))):
                if "exchange.create_market" in lines[j]:
                    indent = "                "
                    insert_code = f"""
{indent}# DB에 완료된 거래 기록
{indent}if symbol in current_positions:
{indent}    try:
{indent}        ticker = exchange.fetch_ticker(symbol)
{indent}        record_completed_trade(symbol, current_positions[symbol], ticker['last'], 'manual')
{indent}    except Exception as e:
{indent}        logger.error(f"DB 기록 실패: {{e}}")

"""
                    lines[j] = lines[j] + insert_code
                    patches_applied += 1
                    break
    
    # 패치된 코드 저장
    if patches_applied > 0:
        with open(original_file, 'w', encoding='utf-8') as f:
            f.writelines(lines)
        
        print(f"\n✅ 패치 완료! {patches_applied}개 위치 수정됨")
        print(f"📝 백업 파일: {backup_file}")
        return True
    else:
        print("\n⚠️ 패치할 위치를 찾지 못했습니다.")
        print("수동으로 수정이 필요할 수 있습니다.")
        return False

def create_patched_functions():
    """수정된 함수들만 별도 파일로 저장"""
    
    print("\n" + "=" * 60)
    print("📝 수정된 함수 생성")
    print("=" * 60)
    
    patched_code = '''# 수정된 execute_position_exit 함수
def execute_position_exit(symbol, decision):
    """포지션 종료 실행 - 수정 버전"""
    try:
        position = current_positions.get(symbol)
        if not position:
            logger.warning(f"No position found for {symbol}")
            return False
        
        # 현재 포지션 정보
        side = position['side']
        amount = position['amount']
        
        # 종료할 수량 계산
        if decision['decision'] == 'close':
            exit_amount = amount
        elif decision['decision'] == 'partial_close':
            exit_amount = amount * (decision['percentage'] / 100)
        else:
            return False
        
        # 시장가 주문으로 포지션 종료
        if side == 'buy':
            order = exchange.create_market_sell_order(symbol, exit_amount)
        else:  # sell
            order = exchange.create_market_buy_order(symbol, exit_amount)
        
        logger.info(f"Position exit executed for {symbol}: {decision['decision']}")
        
        # 🔥 추가된 코드: 완료된 거래 DB 기록
        try:
            ticker = exchange.fetch_ticker(symbol)
            exit_price = ticker['last']
            
            # 전체 종료인 경우
            if decision['decision'] == 'close':
                record_completed_trade(symbol, position, exit_price, decision.get('exit_type', 'ai_exit'))
                logger.info(f"✅ Completed trade recorded for {symbol}")
                del current_positions[symbol]
            else:
                # 부분 종료인 경우
                partial_position = position.copy()
                partial_position['amount'] = exit_amount
                record_completed_trade(symbol, partial_position, exit_price, 'partial_' + decision.get('exit_type', 'exit'))
                current_positions[symbol]['amount'] -= exit_amount
                
        except Exception as e:
            logger.error(f"Failed to record completed trade: {e}")
        
        # 텔레그램 알림 (기존 코드)
        if ENABLE_TELEGRAM:
            # ... (기존 알림 코드)
            pass
        
        return True
        
    except Exception as e:
        logger.error(f"Error executing position exit for {symbol}: {e}")
        return False
'''
    
    with open('patched_functions.py', 'w', encoding='utf-8') as f:
        f.write(patched_code)
    
    print("✅ patched_functions.py 파일 생성 완료")
    print("   필요시 이 코드를 v5 봇에 직접 복사하세요.")

def main():
    """메인 실행"""
    
    print("\n" + "=" * 80)
    print("🔧 v5 봇 자동 패치 도구")
    print("=" * 80)
    print("\n이 도구는 v5 봇이 completed_trades 테이블에 자동으로")
    print("거래를 기록하도록 코드를 수정합니다.")
    
    print("\n옵션을 선택하세요:")
    print("1. 자동 패치 (v5 봇 파일 직접 수정)")
    print("2. 수정된 함수만 별도 파일로 생성")
    print("3. 취소")
    
    choice = input("\n선택 (1-3): ").strip()
    
    if choice == '1':
        success = patch_v5_bot()
        if success:
            print("\n✅ 패치 성공! 봇을 재시작하세요.")
        else:
            print("\n⚠️ 자동 패치 실패. 수동 수정이 필요합니다.")
            create_patched_functions()
    
    elif choice == '2':
        create_patched_functions()
    
    else:
        print("취소되었습니다.")

if __name__ == "__main__":
    main()
