# ════════════════════════════════════════════════════════════════════════════
#  integrated_trading_system_v7_7.py 봇 패치
#  목적: TradingView Pine v4.5의 partial_close(부분익절) alert 지원 추가
#
#  현재 봇은 webhook으로 'partial_close' action을 받지 못합니다
#  (partial_close는 내부 AI 모니터링에서만 사용됨).
#  Pine의 TP1 50% 익절이 작동하려면 아래 2가지를 봇에 추가해야 합니다.
# ════════════════════════════════════════════════════════════════════════════


# ─────────────────────────────────────────────────────────────────────────────
# [추가 1/2] 부분청산 함수
#
#   위치: close_position_for_all_users 함수 바로 아래에 추가
#         (원본 파일 약 10417번째 줄, close_position_for_all_users 함수 끝 직후)
# ─────────────────────────────────────────────────────────────────────────────

def partial_close_for_all_users(symbol, close_percent):
    """
    모든 활성 유저의 포지션을 close_percent%만큼 부분 청산.
    - reduceOnly 시장가로 일부만 청산 (포지션 방향 유지)
    - TP/SL 주문은 취소하지 않음 (남은 포지션에 계속 적용)
    - Pine v4.5의 TP1(50% 익절) 신호 처리용

    Args:
        symbol: 'BTC/USDT' 형식 (정규화된 심볼)
        close_percent: 청산할 비율 (예: 50 = 50%)
    Returns:
        성공한 유저 수
    """
    success_count = 0
    failed_users = []

    # 비율 안전 범위 클램프 (1~100)
    try:
        close_percent = float(close_percent)
    except (TypeError, ValueError):
        close_percent = 50.0
    close_percent = max(1.0, min(100.0, close_percent))

    for user_id, user_exchange in exchanges.items():
        user_name = USER_CONFIGS[user_id]['name']

        try:
            # 포지션 확인
            positions = user_exchange.fetch_positions([symbol])
            active_position = None
            for pos in positions:
                if float(pos.get('contracts') or 0) != 0:
                    active_position = pos
                    break

            if not active_position:
                logger.info(f"[{user_name}] {symbol} 부분청산할 포지션 없음")
                continue

            contracts = float(active_position['contracts'])
            close_amount = abs(contracts) * (close_percent / 100.0)

            # 최소 주문 수량 체크 (거래소별 최소 단위 미만이면 전량 청산으로 폴백)
            try:
                market = user_exchange.market(symbol)
                min_amount = market.get('limits', {}).get('amount', {}).get('min') or 0
            except Exception:
                min_amount = 0

            if min_amount and close_amount < min_amount:
                logger.warning(
                    f"[{user_name}] 부분청산 수량({close_amount:.8f})이 최소단위({min_amount}) 미만 "
                    f"→ 남은 수량이 너무 작아 전량 청산으로 대체"
                )
                close_amount = abs(contracts)

            # 청산 방향 (롱이면 매도, 숏이면 매수)
            close_side = 'sell' if active_position['side'] == 'long' else 'buy'

            # reduceOnly 시장가 부분 청산 (TP/SL 주문은 유지)
            user_exchange.create_market_order(
                symbol, close_side, close_amount,
                params={'reduceOnly': True}
            )
            logger.info(
                f"[{user_name}] ✅ 부분청산 {close_percent:.0f}%: "
                f"{symbol} {close_side} {close_amount:.6f} (전체 {abs(contracts):.6f})"
            )

            # current_positions 수량 갱신 (전역 상태 동기화)
            if symbol in current_positions:
                old_amt = current_positions[symbol].get('amount', abs(contracts))
                current_positions[symbol]['amount'] = max(0.0, old_amt - close_amount)

            success_count += 1

        except Exception as e:
            logger.error(f"[{user_name}] 부분청산 실패: {str(e)}")
            failed_users.append(user_name)

    total_users = len(exchanges)
    logger.info(f"✅ 부분청산({close_percent:.0f}%) 완료: {success_count}/{total_users}명 성공")
    if failed_users:
        logger.warning(f"⚠️ 실패한 유저: {', '.join(failed_users)}")

    return success_count


# ─────────────────────────────────────────────────────────────────────────────
# [추가 2/2] webhook 라우터에 partial_close 분기 추가
#
#   위치: def webhook(): 내부, 심볼 매핑/검증이 끝난 직후.
#         구체적으로는 "use_ai = symbol_config.get('ai_validation', True)" 줄
#         바로 위(원본 약 11197번째 줄)에 아래 블록을 삽입.
#
#   이유: 부분익절은 AI 검증/진입차단(Market Shield) 대상이 아니므로,
#         AI 분기 이전에 먼저 처리하고 즉시 return 합니다.
# ─────────────────────────────────────────────────────────────────────────────

"""
        # ─── 삽입 시작 ───
        # 🆕 Pine v4.5: 부분 청산 (TP1 50% 익절) 처리
        #     AI 검증/Market Shield보다 먼저 처리하고 즉시 반환
        if action == 'partial_close':
            close_percent = safe_get_float(data, 'close_percent', 50)
            exit_reason_pc = data.get('exit_reason', 'tp1_partial')
            logger.info(f"💰 부분청산 신호 수신: {symbol} {close_percent}% (사유: {exit_reason_pc})")

            try:
                pc_success = partial_close_for_all_users(symbol, close_percent)

                if pc_success > 0:
                    # 부분청산 거래 기록 (선택)
                    try:
                        if symbol in current_positions:
                            partial_pos = current_positions[symbol].copy()
                            # 청산된 비율만큼만 기록
                            orig_amt = partial_pos.get('amount', 0)
                            record_completed_trade_with_binance(
                                symbol, partial_pos,
                                close_reason=f"partial_{exit_reason_pc}"
                            )
                    except Exception as rec_err:
                        logger.warning(f"부분청산 기록 실패 (무시): {rec_err}")

                    if ENABLE_TELEGRAM:
                        send_telegram_notification(
                            f"💰 <b>부분 익절 완료 (Multi-User)</b>\\n\\n"
                            f"<b>심볼:</b> {symbol}\\n"
                            f"<b>청산 비율:</b> {close_percent:.0f}%\\n"
                            f"<b>성공:</b> {pc_success}/{len(exchanges)}명\\n"
                            f"<b>사유:</b> {exit_reason_pc}\\n"
                            f"<b>수익률:</b> {safe_get_float(data, 'profit_percent', 0):.2f}%\\n\\n"
                            f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                            'success'
                        )

                    return jsonify({
                        'status': 'success',
                        'action': 'partial_close',
                        'symbol': symbol,
                        'close_percent': close_percent,
                        'closed_users': pc_success
                    }), 200
                else:
                    logger.warning(f"⚠️ {symbol} 부분청산할 포지션 없음")
                    return jsonify({'status': 'no_position', 'symbol': symbol}), 200

            except Exception as e:
                logger.error(f"부분청산 오류: {str(e)}", exc_info=True)
                return jsonify({'error': str(e)}), 500
        # ─── 삽입 끝 ───
"""

# ════════════════════════════════════════════════════════════════════════════
#  봇 설정 권장값 (config 또는 SYMBOL_CONFIG)
# ════════════════════════════════════════════════════════════════════════════
#
#  AUTO_TP_SL_GENERATION = False
#    → Pine이 보낸 stop_loss를 그대로 거래소 SL 주문으로 사용.
#      take_profit는 null이므로 거래소 TP 주문은 안 걸림 (TP는 Pine이 제어).
#      True로 두면 봇이 임의로 +4% TP를 거래소에 걸어버려 부분익절과 충돌함.
#
#  BTC/USDT 심볼 ai_validation:
#    → 추세추종 전략은 AI 재검증이 오히려 진입을 막을 수 있으니
#      처음엔 False로 두고 Pine 신호를 그대로 따르는 것을 권장.
#      (원하면 True로 두고 AI 필터를 추가 적용)
#
# ════════════════════════════════════════════════════════════════════════════
