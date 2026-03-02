"""
╔═══════════════════════════════════════════════════════════════════════════════╗
║              INTEGRATED TRADING SYSTEM v7.8 CONSERVATIVE EXIT                ║
║                   Multi-User Crypto Trading Bot                              ║
╠═══════════════════════════════════════════════════════════════════════════════╣
║  Version: 7.8                                                                ║
║  Last Updated: 2026-01-12                                                    ║
║  Base Version: v7.7 → v7.8 CONSERVATIVE EXIT                                 ║
╠═══════════════════════════════════════════════════════════════════════════════╣
║                     v7.8 CHANGELOG (CONSERVATIVE EXIT)                       ║
╠═══════════════════════════════════════════════════════════════════════════════╣
║  🔴 핵심 문제: 포지션 너무 성급히 종료하여 수익 기회 상실                     ║
║  - PYTH -1.52% @ 0분, COTI -1.80% @ 18분, LTC -3.54% @ 27분                  ║
║  - 경미한 손실에서 trend_reversal로 조기 청산                                 ║
║                                                                              ║
║  🆕 핵심 개선 1: TP/SL 간격 더 타이트하게                                    ║
║  - SL: 0.4x → 0.3x ATR (리스크 감소)                                        ║
║  - TP: 0.6x → 0.5x ATR (수익 보존 확률 증가)                                ║
║  - 손익비 1.5 유지                                                           ║
║                                                                              ║
║  🆕 핵심 개선 2: 초반 보호 기간 대폭 확대                                    ║
║  - 초반 보호: 45분 → 60분                                                   ║
║  - 중간 보호: 60분 → 90분                                                   ║
║  - 경미 손실(-5% 이상)에서도 강한 보호                                       ║
║                                                                              ║
║  🆕 핵심 개선 3: 임계값 대폭 상향 (보수적 종료)                              ║
║  - 초반 수익: 즉시=20, 곧=16, 관찰=12                                        ║
║  - 초반 경미손실: 즉시=18, 곧=14, 관찰=10                                    ║
║  - 중간 손실: 즉시=15, 곧=12, 관찰=8                                         ║
║                                                                              ║
║  🆕 핵심 개선 4: 점수 차감 강화                                              ║
║  - 초반 수익: -6점 (기존 -4점)                                               ║
║  - 초반 경미손실: -4점 (신규)                                                ║
║  - 중간 수익: -3점, 경미손실: -2점                                           ║
║                                                                              ║
║  🆕 핵심 개선 5: 손실 가속 조건 완화                                         ║
║  - 60분 미만: 손실 가속 미적용 (인내심 유지)                                 ║
║  - 60분 이상 & -8% 이하: 손실 가속 적용                                      ║
║  - -15% 이하: 시간 무관 강제 청산                                            ║
║                                                                              ║
║  🆕 핵심 개선 6: RSI 인내심 경미손실 적용                                    ║
║  - 수익 중: 100% 인내심 적용                                                 ║
║  - 경미손실(-5% 이상): 50% 인내심 적용 (반등 기대)                           ║
║  - 심각손실(-5% 미만): 인내심 미적용                                         ║
║                                                                              ║
║  📊 v7.8 예상 효과:                                                          ║
║  ┌─────────────────────────────────────────────────────────────────────┐     ║
║  │  PYTH @ 0분 -1.52% → 보호 기간으로 청산 방지, 반등 대기             │     ║
║  │  LTC @ 27분 -3.54% → 경미손실 보호로 추가 기회 부여                 │     ║
║  │  TP/SL 타이트 → 손실 리스크 감소, 수익 확정 빈도 증가               │     ║
║  └─────────────────────────────────────────────────────────────────────┘     ║
║                                                                              ║
╠═══════════════════════════════════════════════════════════════════════════════╣
║                     v7.7 CHANGELOG (LOSS DISCIPLINE)                         ║
╠═══════════════════════════════════════════════════════════════════════════════╣
║  🔴 핵심 문제: UMA -47%, PENDLE -52%, ACH -42% 대형 손실                     ║
║  - 추세 역전 감지 후에도 너무 오래 버팀 → 손익비 파괴                        ║
║                                                                              ║
╠═══════════════════════════════════════════════════════════════════════════════╣
║                     v7.5.1 CHANGELOG (EARLY PROTECTION BALANCE)              ║
╠═══════════════════════════════════════════════════════════════════════════════╣
║  🆕 핵심 개선: 초반 보호 기간 인내심 강화                                    ║
║  - 문제: HOME +1.49% @ 31분에서 너무 성급하게 종료                          ║
║  - 해결: 초반 보호 기간에 임계값 대폭 상향                                   ║
║    • < 45분 + 손실 < -10%: 임계값 18/15/10 (기존 12/9/6)                    ║
║    • 45-60분: 임계값 15/12/8                                                 ║
║    • 60분+: 기존 임계값 12/9/6 유지                                          ║
║                                                                              ║
║  🆕 초반 수익 보호 점수 차감:                                                ║
║    • < 45분 + 수익 중: -4점 차감 (인내심 강화)                               ║
║    • 45-60분 + 수익 중: -2점 차감                                            ║
║                                                                              ║
║  🆕 Trailing Protection 초반 보류:                                           ║
║    • < 45분에서는 peak >= 20%일 때만 적용                                    ║
║    • 초반에 작은 수익에서 성급한 종료 방지                                   ║
║                                                                              ║
╠═══════════════════════════════════════════════════════════════════════════════╣
║  🆕 핵심 개선 1: Trailing Profit Protection                                  ║
║  - 문제: Peak +70% → -25% 손실 전환 (PENDLE, DOT 실제 사례)                  ║
║  - 해결: Peak profit에 비례한 동적 drawdown 임계값                           ║
║    • Peak >= 50%: 15-20% drawdown에서 강제 종료                              ║
║    • Peak >= 30%: 20-25% drawdown에서 EXIT_SOON                              ║
║    • Peak >= 15%: 25-30% drawdown에서 경고                                   ║
║    • 수익→손실 전환 시 즉시 종료 (95% 신뢰도)                               ║
║                                                                              ║
║  🆕 핵심 개선 2: 1H 신호 가중치 증가                                         ║
║  - 문제: 고수익 구간에서 1H 추세 반전 신호 무시                              ║
║  - 해결: Peak profit 비례 가중치                                             ║
║    • Peak >= 30%: 1H 신호 1.5x 가중치                                        ║
║    • Peak >= 15%: 1H 신호 1.3x 가중치                                        ║
║                                                                              ║
║  🆕 핵심 개선 3: 4H Trend Support 차감 제한 강화                             ║
║  - 문제: 강한 4H 추세에서 점수 50% 차감으로 exit 억제                        ║
║  - 해결: Peak profit 높을수록 차감 상한 더 낮춤                              ║
║    • Peak >= 50%: 최대 1점 차감                                              ║
║    • Peak >= 30%: 최대 2점 차감                                              ║
║    • Peak >= 15%: 최대 3점 차감                                              ║
║                                                                              ║
║  📊 v7.5 예상 효과:                                                          ║
║  ┌─────────────────────────────────────────────────────────────────────┐     ║
║  │  PENDLE +70.65% → 20% drawdown에서 경고, 25%에서 강제 종료 준비     │     ║
║  │  DOT +34.22% → 25% drawdown에서 경고, 30%에서 종료 권고             │     ║
║  │  손실 전환 전 조기 대응으로 수익 보호                               │     ║
║  └─────────────────────────────────────────────────────────────────────┘     ║
║                                                                              ║
╠═══════════════════════════════════════════════════════════════════════════════╣
║                     v7.4 CHANGELOG (MEAN REVERSION + DYNAMIC FILTER)         ║
╠═══════════════════════════════════════════════════════════════════════════════╣
║  🆕 핵심 개선 1: ATR 기반 적응형 손실 제한                                   ║
║  - 문제: 고정 손실 제한이 알트코인 변동성에 맞지 않음 (노이즈에 민감)         ║
║  - 해결: ATR의 2.5배 기준 동적 손실 제한 (-25% ~ -40%)                       ║
║  - 효과: 단기 노이즈에 덜 민감, 정상 변동성 내에서 포지션 유지               ║
║                                                                              ║
║  🆕 핵심 개선 2: DB 기반 동적 심볼 필터                                      ║
║  - 문제: 정적 블랙리스트는 시장 상황 반영 못함                                ║
║  - 해결: 최근 30일 성과 기반 자동 필터링                                     ║
║    • 3회+ 거래 & 0% 승률 → BLACKLIST (거래 금지)                            ║
║    • 승률 <35% & 누적손실 >$500 → REDUCED (사이즈 30%)                       ║
║    • 거래 없음 → NEUTRAL (정상 거래 허용)                                    ║
║    • 승률 >60% & 수익 → PREFERRED (사이즈 120%)                              ║
║                                                                              ║
║  🆕 핵심 개선 3: Mean Reversion 기회 포착                                    ║
║  - 문제: 극단적 과매도/과매수에서 신호 방향 진입 기회 놓침                    ║
║  - 해결: 저점 매수(BUY)/고점 매도(SELL) 신호 Approve 로직 추가               ║
║    • 4H RSI <25 + BB 하단 이탈 + Stoch 과매도 → BUY 신호 Approve             ║
║    • 4H RSI >75 + BB 상단 이탈 + Stoch 과매수 → SELL 신호 Approve            ║
║    • 점수 6점 이상 시 Mean Reversion 진입 허용                               ║
║                                                                              ║
║  🆕 핵심 개선 4: Contrarian 진입 조건 강화                                   ║
║  - 문제: 기존 반대매매 조건이 너무 느슨해서 손실 발생                         ║
║  - 해결: 더 극단적 조건에서만 반대매매 허용                                   ║
║    • 필수: 3개 타임프레임 모두 극단값 (4H+1H+15m 동시)                       ║
║    • 점수 8점 이상 필요 (기존 6점에서 상향)                                  ║
║    • MACD 다이버전스 + 볼륨 클라이맥스 추가 확인                             ║
║                                                                              ║
║  📊 v7.4 요약:                                                               ║
║  ┌─────────────────────────────────────────────────────────────────────┐     ║
║  │  1. 손실 제한: 고정값 → ATR 기반 적응형 (-25%~-40%)                 │     ║
║  │  2. 심볼 필터: 정적 → DB 기반 동적 (30일 성과)                      │     ║
║  │  3. Mean Reversion: 극단적 과매도/과매수에서 신호방향 Approve        │     ║
║  │  4. Contrarian: 3TF 극단 + 8점 이상에서만 반대매매                  │     ║
║  │  5. 4H 가중치: 감소 (30%), 1H 가중치 증가 (35%)                     │     ║
║  └─────────────────────────────────────────────────────────────────────┘     ║
║                                                                              ║
╠═══════════════════════════════════════════════════════════════════════════════╣
║                     v7.6 CHANGELOG (BALANCED EXIT LOGIC)                     ║
╠═══════════════════════════════════════════════════════════════════════════════╣
║  🔴 긴급 수정 1: TP/SL 주문 API 오류 해결                                   ║
║  - 문제: ccxt의 fapiPrivatePostAlgoorder 미지원으로 TP/SL 설정 실패         ║
║  - 해결: HTTP 직접 요청 방식으로 변경 (hmac 서명 포함)                       ║
║  - 추가: 기존 방식 fallback 지원 (Algo API 실패 시)                         ║
║                                                                              ║
║  🔄 핵심 수정 2: 장기 보유 포지션 수익 보호 강화                            ║
║  - 문제: peak 수익에서 많이 하락해도 4H 추세 강하면 종료 안함               ║
║  - 해결: 시간 기반 수익 보호 로직 추가                                      ║
║    • 60분+ 보유 + peak > 5% + 현재 < peak의 40% → 강제 종료 권장            ║
║    • 90분+ 보유 + peak > 3% + drawdown > 60% → 즉시 종료                    ║
║    • 4H 추세 지지 점수 차감에 상한선 추가 (수익 보호 우선)                  ║
║                                                                              ║
║  🛡️ 핵심 수정 3: 초반 drawdown 왜곡 문제 해결                               ║
║  - 문제: peak profit이 작을 때 (예: 0.5%) drawdown %가 비정상적으로 큼      ║
║  - 해결: 최소 peak threshold 추가 (peak < 1.5% 이면 drawdown 무시)          ║
║  - 추가: 절대값 기반 drawdown 조건 추가 (peak - current > 3% 체크)          ║
║                                                                              ║
║  📊 v7.6 주요 개선사항:                                                      ║
║  ┌─────────────────────────────────────────────────────────────────────┐     ║
║  │  1. TP/SL: HTTP 직접 요청으로 Algo Order API 완벽 지원              │     ║
║  │  2. 수익 보호: 시간 + peak drawdown 조합 조건 추가                  │     ║
║  │  3. 초반 보호: peak < 1.5%일 때 drawdown % 경고 무시                │     ║
║  │  4. 균형 잡힌 판단: 4H 추세 차감에 수익 보호 상한선 추가            │     ║
║  │  5. AI 프롬프트: 시간+수익 조합 규칙 명확화                         │     ║
║  └─────────────────────────────────────────────────────────────────────┘     ║
║                                                                              ║
║  📈 개선된 Exit 판단 기준:                                                   ║
║  - 초반 (< 60분): 기존 v7.5 보호 로직 유지 + drawdown 왜곡 방지            ║
║  - 중반 (60-120분): 수익 보호 조건 활성화 (peak > 3%, drawdown > 50%)      ║
║  - 장기 (120분+): 적극적 수익 보호 (peak > 2%, drawdown > 40%)             ║
║                                                                              ║
╠═══════════════════════════════════════════════════════════════════════════════╣
║                     v7.5 CHANGELOG (AI EXIT ANTI-NOISE)                      ║
╠═══════════════════════════════════════════════════════════════════════════════╣
║  🔄 핵심 변경: AI Exit 판단 - 중장기 타임프레임 중심으로 트랩 신호 필터링    ║
║                                                                              ║
║  📊 v7.5 주요 개선사항:                                                      ║
║  ┌─────────────────────────────────────────────────────────────────────┐     ║
║  │  1. 임계값 대폭 상향: immediate 8→12, soon 5→9, watch 3→6          │     ║
║  │  2. 15분봉 점수 대폭 감소: 단기 노이즈 무시 (1~2점으로 하향)        │     ║
║  │  3. 4시간봉 점수 대폭 증가: 중장기 추세 중시 (4~8점)                │     ║
║  │  4. 멀티타임프레임 확인 필수: 15분봉 단독 exit 불가                 │     ║
║  │  5. 연속 캔들 조건 추가: 2-3개 캔들 연속 확인                       │     ║
║  │  6. 트랩 필터 추가: 4시간봉 추세 방향과 일치하지 않으면 점수 감소   │     ║
║  │  7. 추세 지지 보너스: 큰 추세가 유효하면 점수 차감                  │     ║
║  └─────────────────────────────────────────────────────────────────────┘     ║
║                                                                              ║
╠═══════════════════════════════════════════════════════════════════════════════╣
║                     v7.4 CHANGELOG (2025-12-12)                              ║
╠═══════════════════════════════════════════════════════════════════════════════╣
║  🔴 긴급 수정: 바이낸스 API 변경 대응 (2025-12-09)                          ║
║  🧘 인내심 로직 추가 (조기 종료 방지)                                        ║
╚═══════════════════════════════════════════════════════════════════════════════╝
║                                                                              ║
║  📊 새로운 아키텍처:                                                         ║
║  ┌─────────────────────────────────────────────────────────────────────┐     ║
║  │  1. 웹훅 Alert 수신                                                 │     ║
║  │         ↓                                                           │     ║
║  │  2. Rule-Based Validation (Python 로직)                            │     ║
║  │     - calculate_risk_score(): 위험 점수 계산                       │     ║
║  │     - calculate_approval_score(): 승인 점수 계산                   │     ║
║  │     - 정확한 수학적 비교 수행                                       │     ║
║  │         ↓                                                           │     ║
║  │  3. AI Parameter Adjustment (DeepSeek)                             │     ║
║  │     - 레버리지: 5~20배 조정                                        │     ║
║  │     - 포지션 사이즈: 10~40% 조정                                   │     ║
║  │     - TP/SL 미세조정                                               │     ║
║  │         ↓                                                           │     ║
║  │  4. 거래 실행                                                       │     ║
║  └─────────────────────────────────────────────────────────────────────┘     ║
║                                                                              ║
║  ✅ 장점:                                                                    ║
║  - 수학적 비교 오류 제거 (Python이 정확히 계산)                              ║
║  - AI 부담 감소 (복잡한 지표 분석 → 간단한 파라미터 조정)                   ║
║  - 일관성 있는 결과                                                         ║
║  - 빠른 처리 속도                                                           ║
║                                                                              ║
║  📈 Risk Score (0-15+):                                                      ║
║  - 0-4: Low Risk → APPROVE 가능                                             ║
║  - 5-7: Medium Risk → MODIFY (축소 진입)                                    ║
║  - 8+: High Risk → REJECT                                                   ║
║                                                                              ║
║  📊 Approval Score (0-100):                                                  ║
║  - 70+: APPROVE 가능                                                        ║
║  - 60-69: MODIFY                                                            ║
║  - <60: REJECT                                                              ║
║                                                                              ║
║  🔧 AI 파라미터 조정 범위:                                                   ║
║  - 레버리지: 5x ~ 20x (Risk Score에 따라)                                   ║
║  - 포지션: 10% ~ 40% (Approval Score에 따라)                                ║
║  - TP/SL: ATR 기반 (1.5~2.5x ATR)                                          ║
║                                                                              ║
║  v7.2 기능 유지:                                                             ║
║  - 모든 바이낸스 포지션 AI 모니터링                                         ║
║  - Peak Profit Tracking 시스템                                               ║
║  - 지지부진 포지션 감지                                                     ║
║  - HTML 특수문자 이스케이프 (텔레그램)                                       ║
╚═══════════════════════════════════════════════════════════════════════════════╝
"""

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
from pydantic import BaseModel, Field, ValidationError, model_validator
import sqlite3
import numpy as np
import re
import hmac
import hashlib
import urllib.parse

# 환경 변수 로드
load_dotenv()

# ============ 다중 유저 설정 ============
USER_CONFIGS = {
    'USER1': {
        'name': 'Mingu (Primary)',
        'api_key_env': 'BINANCE_API_KEY',
        'secret_key_env': 'BINANCE_SECRET_KEY',
        'is_primary': True,  # AI 검증, DB, 텔레그램
    },
    'USER2': {
        'name': 'Hyun',
        'api_key_env': 'BINANCE_API_KEY_HYUN',
        'secret_key_env': 'BINANCE_SECRET_KEY_HYUN',
        'is_primary': False,  # 주문만 실행
    },
    'USER3': {
        'name': 'Hyuk',
        'api_key_env': 'BINANCE_API_KEY_HYUK',
        'secret_key_env': 'BINANCE_SECRET_KEY_HYUK',
        'is_primary': False,  # 주문만 실행
    }
}

SERVER_PORT = 5000  # 하나의 서버에서 모든 유저 관리
ENABLE_TELEGRAM = True  # Primary User가 텔레그램 관리
AI_MONITOR_INTERVAL = 5  # AI 포지션 모니터링 간격 (분)

# 🆕 TP/SL 자동생성 옵션
# True: 웹훅 TP/SL이 null이면 봇이 자동 생성 (기존 동작)
# False: 웹훅 TP/SL이 null이면 TP/SL 없이 진입 (TradingView 종료 신호에 의존)
AUTO_TP_SL_GENERATION = True

# ============ 🆕 v7.8: Emergency Drawdown Protection (긴급 낙폭 보호) ============
# TradingView 전략에서 손절가를 끈 경우의 안전장치
EMERGENCY_DRAWDOWN_ENABLED = True        # ON/OFF (대시보드에서 변경 가능)
EMERGENCY_DRAWDOWN_WARNING = -25.0       # 경고 임계값 (%) - AI 집중 모니터링 시작
EMERGENCY_DRAWDOWN_FORCE_EXIT = -50.0    # 강제 청산 임계값 (%) - 즉시 종료
EMERGENCY_DRAWDOWN_MONITOR_INTERVAL = 15 # 경고 구간 모니터링 간격 (분)

# ============ 🆕 v7.4 새로운 상수 ============
# 적응형 손실 제한 설정 (v7.7: 더 타이트하게 조정)
V74_ADAPTIVE_LOSS_MIN = -10  # 최소 손실 제한 (기존 -15 → -10)
V74_ADAPTIVE_LOSS_MAX = -18  # 최대 손실 제한 (기존 -25 → -18)
V74_ATR_MULTIPLIER = 2.0     # ATR 기반 손실 제한 배수

# ============ 🆕 v7.7 손실 진행 시 조기 청산 상수 ============
# 추세 역전 확인 후 손실이 지속되면 빠르게 청산
V77_LOSS_ACCELERATION_THRESHOLD = -8.0   # 이 손실부터 가속 청산 모드
V77_LOSS_CRITICAL_THRESHOLD = -15.0      # 이 손실 넘으면 무조건 청산 고려
V77_LOSS_CATASTROPHIC_THRESHOLD = -25.0  # 절대 손실 한도 (기존 -30 → -25)
V77_REVERSAL_LOSS_MULTIPLIER = 1.5       # 추세 역전 시 exit 점수 배율
V77_CONSECUTIVE_LOSS_CANDLES = 3         # 연속 손실 캔들 수 (청산 트리거)

# Mean Reversion 설정
V74_MEAN_REVERSION_THRESHOLD = 6  # Mean Reversion 진입 최소 점수
V74_CONTRARIAN_THRESHOLD = 8      # Contrarian 진입 최소 점수 (더 엄격)

# 동적 심볼 필터 설정
V74_SYMBOL_FILTER_LOOKBACK_DAYS = 30  # 심볼 성과 조회 기간
V74_BLACKLIST_MIN_TRADES = 3          # 블랙리스트 최소 거래 수
V74_BLACKLIST_WIN_RATE = 0            # 블랙리스트 승률 기준
V74_REDUCED_WIN_RATE = 35             # 축소 사이즈 승률 기준
V74_REDUCED_MIN_LOSS = -500           # 축소 사이즈 누적손실 기준

# ============ 🆕 v7.5 새로운 상수 ============
# TP/SL 설정 (v7.8: 더 타이트한 간격으로 리스크 감소)
V75_SL_ATR_MULTIPLIER = 0.3   # SL: 15분봉 ATR의 0.3배 (기존 0.4 → 0.3)
V75_TP_ATR_MULTIPLIER = 0.5   # TP: 15분봉 ATR의 0.5배 (기존 0.6 → 0.5)
V75_MIN_RR_RATIO = 1.5        # 최소 R:R 비율 유지

# 수익 보호 설정 (v7.8: 더 보수적으로)
V75_PROFIT_PROTECTION_THRESHOLD = 2.0   # 수익 보호 시작 임계값 (3% → 2%)
V75_PROFIT_LOCK_RATIO = 0.5             # 수익의 50% 확보 목표
V75_EARLY_PROFIT_EXIT = 4.0             # 조기 익절 임계값 (5% → 4%)
V75_QUICK_PROFIT_TIME = 40              # 빠른 수익 청산 기준 시간 (30분 → 40분)

# ============ 🆕 v7.8 보수적 종료 상수 ============
V78_EARLY_PROTECTION_MINUTES = 60       # 초반 보호 기간 확대 (45분 → 60분)
V78_MID_PROTECTION_MINUTES = 90         # 중간 보호 기간 확대 (60분 → 90분)
V78_MIN_LOSS_FOR_EXIT = -5.0            # 이 손실 이상이어야 exit 고려 시작
V78_STRICT_THRESHOLD_IMMEDIATE = 20     # 초반 즉시 exit 임계값 (매우 높음)
V78_STRICT_THRESHOLD_SOON = 16          # 초반 곧 exit 임계값
V78_STRICT_THRESHOLD_WATCH = 12         # 초반 관찰 임계값

# 양방향 포지션 관리
V75_HEDGE_PROFIT_THRESHOLD_MULTIPLIER = 2.0  # 수수료 x 2 x 레버리지 = 청산 기준
V75_BASE_FEE_RATE = 0.05  # 기본 수수료율 0.05%

# ============ 🆕 v7.6 RSI 과열 인내심 상수 ============
# RSI가 과열 상태(과매수/과매도)일 때 반등/반락 가능성이 높으므로 
# exit 점수를 차감하여 인내심을 갖도록 함
V76_RSI_EXTREME_OVERBOUGHT = 80  # 극단적 과매수
V76_RSI_OVERBOUGHT = 70          # 과매수
V76_RSI_EXTREME_OVERSOLD = 20    # 극단적 과매도
V76_RSI_OVERSOLD = 30            # 과매도
V76_STOCH_EXTREME_OVERBOUGHT = 85  # Stochastic 극단적 과매수
V76_STOCH_EXTREME_OVERSOLD = 15    # Stochastic 극단적 과매도
V76_EXTREME_PATIENCE_DEDUCTION = 6  # 극단적 과열 시 점수 차감 (높음)
V76_MODERATE_PATIENCE_DEDUCTION = 3  # 보통 과열 시 점수 차감


# ============ 🆕 v7.4 적응형 손실 제한 함수 ============
def get_adaptive_loss_limit(symbol: str, atr_percent: float, leverage: int) -> float:
    """
    🆕 v7.4: ATR 기반 적응형 손실 제한 (보수적 버전)
    - 알트코인 변동성을 고려한 동적 임계값
    - 레버리지 반영
    - 노이즈에 덜 민감하면서도 안전한 설계
    
    Args:
        symbol: 심볼명 (예: 'BTC/USDT')
        atr_percent: ATR을 가격 대비 퍼센트로 변환한 값
        leverage: 레버리지 배수
        
    Returns:
        float: 적응형 손실 제한 (음수 퍼센트)
        
    손실 제한 범위:
    - BTC/ETH: -15% ~ -20% (실제 가격 -0.75% ~ -1%)
    - 알트코인: -18% ~ -25% (실제 가격 -0.9% ~ -1.25%)
    """
    # 기본 손실 제한: ATR의 2배 (노이즈 필터링, 하지만 너무 넓지 않게)
    base_limit = atr_percent * V74_ATR_MULTIPLIER
    
    # 심볼 카테고리별 조정
    if 'BTC' in symbol or 'ETH' in symbol:
        # 메이저: 변동성 낮음, 더 타이트한 제한 (-15% ~ -20%)
        adjusted_limit = max(V74_ADAPTIVE_LOSS_MIN, -base_limit * leverage * 0.7)
        max_limit = -20  # 메이저는 최대 -20%
    else:
        # 알트코인: 변동성 높음, 약간 더 넓은 제한 (-18% ~ -25%)
        adjusted_limit = max(V74_ADAPTIVE_LOSS_MIN * 1.2, -base_limit * leverage * 0.9)
        max_limit = V74_ADAPTIVE_LOSS_MAX  # 알트는 최대 -25%
    
    # 최대 제한 적용 (절대 max_limit 이하로는 안감)
    return max(adjusted_limit, max_limit)


def should_emergency_exit_v74(current_pnl: float, holding_minutes: int, 
                               atr_percent: float, leverage: int, symbol: str) -> tuple:
    """
    🆕 v7.4: 긴급 탈출 조건 - 보수적 버전
    기존 고정 손실 제한 대신 ATR 기반 적응형 제한 사용
    
    Args:
        current_pnl: 현재 손익 (%)
        holding_minutes: 보유 시간 (분)
        atr_percent: ATR 퍼센트
        leverage: 레버리지
        symbol: 심볼명
        
    Returns:
        tuple: (should_exit: bool, reason: str or None)
    """
    adaptive_limit = get_adaptive_loss_limit(symbol, atr_percent, leverage)
    
    # 🆕 v7.7: 시간 기반 손실 제한 강화 (더 빠른 손절)
    time_based_limits = {
        10: adaptive_limit * 0.4,   # 10분: 적응형 제한의 40% (매우 빠른 손절)
        20: adaptive_limit * 0.5,   # 20분: 적응형 제한의 50%
        30: adaptive_limit * 0.6,   # 30분: 적응형 제한의 60%
        60: adaptive_limit * 0.75,  # 60분: 적응형 제한의 75%
        120: adaptive_limit * 0.9,  # 2시간: 적응형 제한의 90%
    }
    
    for minutes, limit in sorted(time_based_limits.items()):
        if holding_minutes <= minutes:
            if current_pnl <= limit:
                return True, f"v7.7 Time-adaptive limit: {current_pnl:.1f}% at {holding_minutes}min (limit: {limit:.1f}%)"
            break
    
    # 🆕 v7.7: 절대 손실 제한 강화 (-25%로 낮춤)
    if current_pnl <= V77_LOSS_CATASTROPHIC_THRESHOLD:
        return True, f"v7.7 CATASTROPHIC: Absolute loss {current_pnl:.1f}% exceeds {V77_LOSS_CATASTROPHIC_THRESHOLD}% limit"
    
    return False, None


# ============ 🆕 v7.5 양방향 포지션 관리 함수 ============
def check_hedge_position_conflict(symbol: str, new_side: str) -> dict:
    """
    🆕 v7.5: 양방향 포지션 충돌 체크
    롱/숏 동시 보유 시 수익 포지션 먼저 청산 권장
    
    Args:
        symbol: 심볼명
        new_side: 새로 진입하려는 방향 ('buy' or 'sell')
        
    Returns:
        dict: {
            'has_conflict': bool,
            'existing_side': str,
            'existing_pnl': float,
            'should_close_existing': bool,
            'reason': str
        }
    """
    try:
        # 현재 포지션 확인
        positions = exchange.fetch_positions([symbol])
        
        for pos in positions:
            if pos['symbol'] == symbol and pos['contracts'] > 0:
                existing_side = 'buy' if pos['side'] == 'long' else 'sell'
                
                # 같은 방향이면 충돌 없음
                if existing_side == new_side:
                    return {'has_conflict': False, 'reason': 'Same direction'}
                
                # 반대 방향 포지션 존재
                pnl_percent = float(pos.get('percentage', 0))
                leverage = int(pos.get('leverage', 20))
                
                # 수수료 기준 계산: 0.05% * 2 * leverage
                fee_threshold = V75_BASE_FEE_RATE * V75_HEDGE_PROFIT_THRESHOLD_MULTIPLIER * leverage
                
                # 수익이 수수료 기준 이상이면 기존 포지션 청산 권장
                if pnl_percent >= fee_threshold:
                    return {
                        'has_conflict': True,
                        'existing_side': existing_side,
                        'existing_pnl': pnl_percent,
                        'should_close_existing': True,
                        'reason': f"🔄 v7.5 HEDGE CONFLICT: Existing {existing_side.upper()} position has +{pnl_percent:.2f}% profit (>= {fee_threshold:.2f}% threshold). Close existing first!"
                    }
                else:
                    return {
                        'has_conflict': True,
                        'existing_side': existing_side,
                        'existing_pnl': pnl_percent,
                        'should_close_existing': False,
                        'reason': f"⚠️ v7.5 HEDGE WARNING: Existing {existing_side.upper()} position at {pnl_percent:+.2f}%. Consider waiting."
                    }
        
        return {'has_conflict': False, 'reason': 'No existing position'}
        
    except Exception as e:
        logger.error(f"Hedge conflict check error: {e}")
        return {'has_conflict': False, 'reason': f'Error: {e}'}


def manage_hedge_positions(symbol: str, leverage: int = 20) -> dict:
    """
    🆕 v7.5: 양방향 포지션 자동 관리
    수익 포지션이 임계값 이상이면 자동 청산
    
    Returns:
        dict: {'closed': bool, 'side': str, 'pnl': float, 'reason': str}
    """
    try:
        positions = exchange.fetch_positions([symbol])
        
        profitable_positions = []
        for pos in positions:
            if pos['symbol'] == symbol and pos['contracts'] > 0:
                pnl_percent = float(pos.get('percentage', 0))
                side = 'buy' if pos['side'] == 'long' else 'sell'
                
                fee_threshold = V75_BASE_FEE_RATE * V75_HEDGE_PROFIT_THRESHOLD_MULTIPLIER * leverage
                
                if pnl_percent >= fee_threshold:
                    profitable_positions.append({
                        'side': side,
                        'pnl': pnl_percent,
                        'contracts': pos['contracts'],
                        'threshold': fee_threshold
                    })
        
        # 수익 포지션이 있으면 청산
        if profitable_positions:
            # 가장 수익이 높은 포지션 먼저 청산
            best = max(profitable_positions, key=lambda x: x['pnl'])
            
            logger.info(f"🔄 v7.5 Auto-closing profitable hedge position: {best['side'].upper()} at +{best['pnl']:.2f}%")
            
            # 청산 실행
            close_side = 'sell' if best['side'] == 'buy' else 'buy'
            try:
                order = exchange.create_market_order(
                    symbol=symbol,
                    side=close_side,
                    amount=best['contracts'],
                    params={'reduceOnly': True}
                )
                return {
                    'closed': True,
                    'side': best['side'],
                    'pnl': best['pnl'],
                    'reason': f"v7.5 Hedge auto-close: {best['side'].upper()} at +{best['pnl']:.2f}%"
                }
            except Exception as e:
                logger.error(f"Failed to close hedge position: {e}")
                return {'closed': False, 'reason': f'Close failed: {e}'}
        
        return {'closed': False, 'reason': 'No profitable hedge positions'}
        
    except Exception as e:
        logger.error(f"Hedge management error: {e}")
        return {'closed': False, 'reason': f'Error: {e}'}


def calculate_tight_tp_sl(current_price: float, action: str, atr_15m: float, atr_1h: float, symbol: str) -> dict:
    """
    🆕 v7.8: 타이트한 TP/SL 계산 (15분봉 ATR 기반)
    리스크 감소 + 수익 보존 확률 증가
    
    Args:
        current_price: 현재 가격
        action: 'buy' or 'sell'
        atr_15m: 15분봉 ATR
        atr_1h: 1시간봉 ATR (백업용)
        symbol: 심볼명
        
    Returns:
        dict: {'stop_loss': float, 'take_profit': float, 'sl_percent': float, 'tp_percent': float}
    """
    # 15분봉 ATR 사용 (없으면 1시간봉의 1/4)
    base_atr = atr_15m if atr_15m > 0 else (atr_1h / 4 if atr_1h > 0 else current_price * 0.005)
    
    # BTC/ETH는 더 타이트하게 (v7.8: 0.3 * 0.9 = 0.27x, 0.5 * 0.9 = 0.45x)
    if 'BTC' in symbol or 'ETH' in symbol:
        sl_multiplier = V75_SL_ATR_MULTIPLIER * 0.9  # 0.27x ATR
        tp_multiplier = V75_TP_ATR_MULTIPLIER * 0.9  # 0.45x ATR
    else:
        sl_multiplier = V75_SL_ATR_MULTIPLIER  # 0.3x ATR
        tp_multiplier = V75_TP_ATR_MULTIPLIER  # 0.5x ATR
    
    sl_distance = base_atr * sl_multiplier
    tp_distance = base_atr * tp_multiplier
    
    # 최소 R:R 보장 (1.5)
    if tp_distance / sl_distance < V75_MIN_RR_RATIO:
        tp_distance = sl_distance * V75_MIN_RR_RATIO
    
    if action.lower() == 'buy':
        stop_loss = current_price - sl_distance
        take_profit = current_price + tp_distance
    else:
        stop_loss = current_price + sl_distance
        take_profit = current_price - tp_distance
    
    # 퍼센트 계산
    sl_percent = (sl_distance / current_price) * 100
    tp_percent = (tp_distance / current_price) * 100
    
    return {
        'stop_loss': stop_loss,
        'take_profit': take_profit,
        'sl_percent': sl_percent,
        'tp_percent': tp_percent,
        'sl_distance': sl_distance,
        'tp_distance': tp_distance,
        'rr_ratio': tp_distance / sl_distance if sl_distance > 0 else 0
    }


# ============ 🆕 v7.4 DB 기반 동적 심볼 필터 함수 ============
def get_symbol_performance_filter(symbol: str, lookback_days: int = 30) -> dict:
    """
    🆕 v7.4: 최근 N일간 심볼 성과 기반 동적 필터링
    - 거래 없으면 중립 (블랙리스트 아님!)
    - 성과에 따라 포지션 사이즈 조절
    
    Args:
        symbol: 심볼명 (예: 'BTC/USDT')
        lookback_days: 조회 기간 (일)
        
    Returns:
        dict: {
            'status': 'BLACKLIST' | 'REDUCED' | 'CAUTION' | 'NORMAL' | 'PREFERRED' | 'NEUTRAL',
            'size_multiplier': float (0.0 ~ 1.2),
            'reason': str
        }
    """
    try:
        conn = get_db_connection()
        c = conn.cursor()
        
        cutoff_date = datetime.now() - timedelta(days=lookback_days)
        
        # 최근 30일 해당 심볼 거래 조회
        c.execute("""
            SELECT 
                COUNT(*) as total_trades,
                SUM(CASE WHEN pnl_usdt > 0 THEN 1 ELSE 0 END) as wins,
                SUM(pnl_usdt) as total_pnl,
                AVG(pnl_usdt) as avg_pnl,
                MIN(pnl_usdt) as worst_trade
            FROM trades 
            WHERE symbol = ? 
            AND close_timestamp >= ?
            AND close_timestamp IS NOT NULL
        """, (symbol, cutoff_date.isoformat()))
        
        row = c.fetchone()
        conn.close()
        
        total_trades = row[0] or 0
        wins = row[1] or 0
        total_pnl = row[2] or 0
        avg_pnl = row[3] or 0
        worst_trade = row[4] or 0
        
        # 거래 없으면 중립 반환 (블랙리스트 아님!)
        if total_trades == 0:
            return {
                'status': 'NEUTRAL',
                'size_multiplier': 1.0,
                'reason': f'No trades in last {lookback_days} days - allowing normal trading'
            }
        
        win_rate = (wins / total_trades) * 100 if total_trades > 0 else 0
        
        # 동적 필터링 규칙
        if total_trades >= V74_BLACKLIST_MIN_TRADES and win_rate == V74_BLACKLIST_WIN_RATE:
            # 3회 이상 거래 & 0% 승률 → 블랙리스트
            return {
                'status': 'BLACKLIST',
                'size_multiplier': 0,
                'reason': f'{total_trades} trades, 0% win rate, total PnL: ${total_pnl:.2f}'
            }
        
        elif total_trades >= 2 and win_rate < V74_REDUCED_WIN_RATE and total_pnl < V74_REDUCED_MIN_LOSS:
            # 2회 이상 & 승률 35% 미만 & 누적손실 $500 이상 → 축소
            return {
                'status': 'REDUCED',
                'size_multiplier': 0.3,
                'reason': f'{win_rate:.0f}% win rate, ${total_pnl:.2f} total PnL'
            }
        
        elif win_rate < 50 and avg_pnl < 0:
            # 승률 50% 미만 & 평균 손실 → 소폭 축소
            return {
                'status': 'CAUTION',
                'size_multiplier': 0.6,
                'reason': f'{win_rate:.0f}% win rate, avg PnL: ${avg_pnl:.2f}'
            }
        
        elif win_rate >= 60 and total_pnl > 0:
            # 우수 성과 → 사이즈 증가 허용
            return {
                'status': 'PREFERRED',
                'size_multiplier': 1.2,
                'reason': f'{win_rate:.0f}% win rate, ${total_pnl:.2f} profit'
            }
        
        return {
            'status': 'NORMAL',
            'size_multiplier': 1.0,
            'reason': f'{win_rate:.0f}% win rate over {total_trades} trades'
        }
        
    except Exception as e:
        logger.warning(f"v7.4 Symbol filter error for {symbol}: {e}")
        return {
            'status': 'NEUTRAL',
            'size_multiplier': 1.0,
            'reason': f'Filter error, allowing normal trading'
        }


def calculate_position_size_v74(base_size: float, symbol: str) -> float:
    """
    🆕 v7.4: 동적 포지션 사이즈 계산
    DB 기반 심볼 성과를 반영하여 사이즈 조정
    
    Args:
        base_size: 기본 포지션 사이즈 (%)
        symbol: 심볼명
        
    Returns:
        float: 조정된 포지션 사이즈 (%)
    """
    filter_result = get_symbol_performance_filter(symbol)
    
    if filter_result['status'] == 'BLACKLIST':
        logger.warning(f"🚫 v7.4 {symbol} BLACKLISTED: {filter_result['reason']}")
        return 0
    
    adjusted_size = base_size * filter_result['size_multiplier']
    
    if filter_result['size_multiplier'] != 1.0:
        logger.info(f"📊 v7.4 {symbol} size adjusted: {base_size}% → {adjusted_size:.1f}% ({filter_result['status']})")
    
    return adjusted_size


# ============ 🆕 v7.4 Mean Reversion 기회 포착 함수 ============
def check_mean_reversion_opportunity(signal_action: str, df_15min, df_hourly, df_4h) -> dict:
    """
    🆕 v7.4: 극단적 과매도/과매수에서 신호 방향 Approve
    - 추세 역행이 아닌, 반등/반락 기회 포착
    - 신호 방향을 그대로 Approve하는 기준
    
    Args:
        signal_action: 웹훅 신호 방향 ('buy' or 'sell')
        df_15min, df_hourly, df_4h: 각 타임프레임 데이터프레임
        
    Returns:
        dict: {
            'is_mean_reversion': bool,
            'confidence_boost': int (0~30),
            'reason': str
        }
    """
    # 안전한 값 추출 헬퍼
    def safe_get(df, col, default=50):
        try:
            val = df[col].iloc[-1]
            return float(val) if pd.notna(val) else default
        except:
            return default
    
    # 지표 추출
    rsi_4h = safe_get(df_4h, 'rsi', 50)
    rsi_1h = safe_get(df_hourly, 'rsi', 50)
    rsi_15m = safe_get(df_15min, 'rsi', 50)
    
    stoch_k_4h = safe_get(df_4h, 'stoch_k', 50)
    stoch_d_4h = safe_get(df_4h, 'stoch_d', 50)
    stoch_k_1h = safe_get(df_hourly, 'stoch_k', 50)
    
    cmf_4h = safe_get(df_4h, 'cmf', 0)
    cmf_1h = safe_get(df_hourly, 'cmf', 0)
    
    # 볼린저 밴드 위치 계산
    bb_upper_4h = safe_get(df_4h, 'bb_bbh', 0)
    bb_lower_4h = safe_get(df_4h, 'bb_bbl', 0)
    bb_middle_4h = safe_get(df_4h, 'bb_bbm', 0)
    current_price = safe_get(df_15min, 'close', 0)
    
    bb_percent_4h = 50  # 기본값
    if bb_upper_4h > bb_lower_4h:
        bb_range = bb_upper_4h - bb_lower_4h
        bb_percent_4h = ((current_price - bb_lower_4h) / bb_range) * 100
    
    result = {
        'is_mean_reversion': False,
        'confidence_boost': 0,
        'reason': ''
    }
    
    # ========== BUY 신호 + 극단적 과매도 ==========
    if signal_action.lower() == 'buy':
        oversold_score = 0
        reasons = []
        
        # RSI 과매도 체크 (다중 타임프레임)
        if rsi_4h < 25:
            oversold_score += 3
            reasons.append(f'4H RSI {rsi_4h:.1f} (extreme oversold)')
        elif rsi_4h < 30:
            oversold_score += 1.5
            reasons.append(f'4H RSI {rsi_4h:.1f} (oversold)')
            
        if rsi_1h < 25:
            oversold_score += 2
            reasons.append(f'1H RSI {rsi_1h:.1f}')
        elif rsi_1h < 30:
            oversold_score += 1
            
        # 볼린저 밴드 하단 이탈/근접
        if bb_percent_4h < 5:  # 하단 밴드 아래
            oversold_score += 2.5
            reasons.append(f'4H BB {bb_percent_4h:.0f}% (below lower band)')
        elif bb_percent_4h < 15:
            oversold_score += 1.5
            reasons.append(f'4H BB {bb_percent_4h:.0f}%')
            
        # 스토캐스틱 과매도
        if stoch_k_4h < 15 and stoch_d_4h < 20:
            oversold_score += 2
            reasons.append(f'4H Stoch K:{stoch_k_4h:.0f}/D:{stoch_d_4h:.0f}')
        elif stoch_k_1h < 10:
            oversold_score += 1.5
            reasons.append(f'1H Stoch K:{stoch_k_1h:.0f}')
        
        # CMF 반등 조짐 (매도세 약화 또는 매수세 유입 시작)
        if cmf_4h < -0.15 and cmf_1h > cmf_4h:  # 4H 강한 매도세지만 1H에서 개선
            oversold_score += 1.5
            reasons.append('CMF divergence (selling exhaustion)')
        
        # Mean Reversion BUY 조건: 점수 6점 이상
        if oversold_score >= V74_MEAN_REVERSION_THRESHOLD:
            result['is_mean_reversion'] = True
            result['confidence_boost'] = min(30, int(oversold_score * 4))  # 최대 30% 부스트
            result['reason'] = f"v7.4 MEAN REVERSION BUY: {', '.join(reasons[:3])}"
    
    # ========== SELL 신호 + 극단적 과매수 ==========
    elif signal_action.lower() == 'sell':
        overbought_score = 0
        reasons = []
        
        # RSI 과매수 체크
        if rsi_4h > 75:
            overbought_score += 3
            reasons.append(f'4H RSI {rsi_4h:.1f} (extreme overbought)')
        elif rsi_4h > 70:
            overbought_score += 1.5
            reasons.append(f'4H RSI {rsi_4h:.1f} (overbought)')
            
        if rsi_1h > 75:
            overbought_score += 2
            reasons.append(f'1H RSI {rsi_1h:.1f}')
        elif rsi_1h > 70:
            overbought_score += 1
            
        # 볼린저 밴드 상단 이탈/근접
        if bb_percent_4h > 95:  # 상단 밴드 위
            overbought_score += 2.5
            reasons.append(f'4H BB {bb_percent_4h:.0f}% (above upper band)')
        elif bb_percent_4h > 85:
            overbought_score += 1.5
            reasons.append(f'4H BB {bb_percent_4h:.0f}%')
            
        # 스토캐스틱 과매수
        if stoch_k_4h > 85 and stoch_d_4h > 80:
            overbought_score += 2
            reasons.append(f'4H Stoch K:{stoch_k_4h:.0f}/D:{stoch_d_4h:.0f}')
        elif stoch_k_1h > 90:
            overbought_score += 1.5
            reasons.append(f'1H Stoch K:{stoch_k_1h:.0f}')
        
        # CMF 반락 조짐
        if cmf_4h > 0.15 and cmf_1h < cmf_4h:  # 4H 강한 매수세지만 1H에서 약화
            overbought_score += 1.5
            reasons.append('CMF divergence (buying exhaustion)')
        
        # Mean Reversion SELL 조건: 점수 6점 이상
        if overbought_score >= V74_MEAN_REVERSION_THRESHOLD:
            result['is_mean_reversion'] = True
            result['confidence_boost'] = min(30, int(overbought_score * 4))
            result['reason'] = f"v7.4 MEAN REVERSION SELL: {', '.join(reasons[:3])}"
    
    return result


# ============ 🆕 v7.4 Contrarian 진입 조건 강화 함수 ============
def check_contrarian_entry_v74(signal_action: str, df_15min, df_hourly, df_4h) -> dict:
    """
    🆕 v7.4: 반대매매 진입 조건 - 매우 극단적 상황에서만
    - 신호가 BUY인데 극단적 과매수 → SELL 반대매매
    - 신호가 SELL인데 극단적 과매도 → BUY 반대매매
    
    ⚠️ 기존보다 훨씬 엄격한 조건!
    - 필수: 3개 타임프레임 모두 극단값
    - 점수: 8점 이상 (기존 6점에서 상향)
    
    Args:
        signal_action: 웹훅 신호 방향
        df_15min, df_hourly, df_4h: 각 타임프레임 데이터프레임
        
    Returns:
        dict: {
            'should_contrarian': bool,
            'contrarian_action': str or None,
            'confidence': int,
            'reason': str
        }
    """
    # 안전한 값 추출 헬퍼
    def safe_get(df, col, default=50):
        try:
            val = df[col].iloc[-1]
            return float(val) if pd.notna(val) else default
        except:
            return default
    
    # 지표 추출
    rsi_4h = safe_get(df_4h, 'rsi', 50)
    rsi_1h = safe_get(df_hourly, 'rsi', 50)
    rsi_15m = safe_get(df_15min, 'rsi', 50)
    
    adx_4h = safe_get(df_4h, 'adx', 25)
    
    macd_diff_4h = safe_get(df_4h, 'macd_diff', 0)
    macd_diff_1h = safe_get(df_hourly, 'macd_diff', 0)
    
    # 볼린저 밴드 위치 계산
    bb_upper_4h = safe_get(df_4h, 'bb_bbh', 0)
    bb_lower_4h = safe_get(df_4h, 'bb_bbl', 0)
    current_price = safe_get(df_15min, 'close', 0)
    
    bb_percent_4h = 50
    if bb_upper_4h > bb_lower_4h:
        bb_range = bb_upper_4h - bb_lower_4h
        bb_percent_4h = ((current_price - bb_lower_4h) / bb_range) * 100
    
    result = {
        'should_contrarian': False,
        'contrarian_action': None,
        'confidence': 0,
        'reason': ''
    }
    
    # ========== BUY 신호 → SELL 반대매매 (매우 엄격) ==========
    if signal_action.lower() == 'buy':
        contrarian_score = 0
        reasons = []
        
        # 필수 조건 1: 3개 타임프레임 모두 과매수
        if rsi_4h > 80 and rsi_1h > 75 and rsi_15m > 70:
            contrarian_score += 4
            reasons.append(f'All TF overbought (4H:{rsi_4h:.0f}/1H:{rsi_1h:.0f}/15m:{rsi_15m:.0f})')
        else:
            # 필수 조건 미충족 → 반대매매 불가
            return result
        
        # 추가 조건: BB 극단적 상단 이탈
        if bb_percent_4h > 98:
            contrarian_score += 3
            reasons.append(f'4H BB {bb_percent_4h:.0f}% (extreme)')
        elif bb_percent_4h > 92:
            contrarian_score += 1.5
        
        # 추가 조건: MACD 다이버전스 (가격 상승 but 모멘텀 약화)
        if macd_diff_4h < macd_diff_1h < 0:  # 히스토그램 음수 전환
            contrarian_score += 2
            reasons.append('MACD bearish divergence')
        
        # 추가 조건: ADX 약화 (추세 소진)
        if adx_4h < 20:
            contrarian_score += 1
            reasons.append(f'ADX weak ({adx_4h:.0f})')
        
        # 반대매매 조건: 점수 8점 이상 (매우 엄격)
        if contrarian_score >= V74_CONTRARIAN_THRESHOLD:
            result['should_contrarian'] = True
            result['contrarian_action'] = 'sell'
            result['confidence'] = min(50, int(contrarian_score * 5))  # 최대 50%
            result['reason'] = f"v7.4 CONTRARIAN SELL: {', '.join(reasons[:2])}"
    
    # ========== SELL 신호 → BUY 반대매매 (매우 엄격) ==========
    elif signal_action.lower() == 'sell':
        contrarian_score = 0
        reasons = []
        
        # 필수 조건 1: 3개 타임프레임 모두 과매도
        if rsi_4h < 20 and rsi_1h < 25 and rsi_15m < 30:
            contrarian_score += 4
            reasons.append(f'All TF oversold (4H:{rsi_4h:.0f}/1H:{rsi_1h:.0f}/15m:{rsi_15m:.0f})')
        else:
            return result
        
        # BB 극단적 하단 이탈
        if bb_percent_4h < 2:
            contrarian_score += 3
            reasons.append(f'4H BB {bb_percent_4h:.0f}% (extreme)')
        elif bb_percent_4h < 8:
            contrarian_score += 1.5
        
        # MACD 다이버전스 (가격 하락 but 모멘텀 반등)
        if macd_diff_4h > macd_diff_1h > 0:
            contrarian_score += 2
            reasons.append('MACD bullish divergence')
        
        # ADX 약화
        if adx_4h < 20:
            contrarian_score += 1
            reasons.append(f'ADX weak ({adx_4h:.0f})')
        
        if contrarian_score >= V74_CONTRARIAN_THRESHOLD:
            result['should_contrarian'] = True
            result['contrarian_action'] = 'buy'
            result['confidence'] = min(50, int(contrarian_score * 5))
            result['reason'] = f"v7.4 CONTRARIAN BUY: {', '.join(reasons[:2])}"
    
    return result

app = Flask(__name__)
logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s - [Multi-User Server] - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Flask 로깅 레벨 조정
import logging as flask_logging
flask_logging.getLogger('werkzeug').setLevel(flask_logging.WARNING)

# ============ 다중 Exchange 객체 생성 ============
exchanges = {}
for user_id, config in USER_CONFIGS.items():
    api_key = os.getenv(config['api_key_env'])
    secret_key = os.getenv(config['secret_key_env'])
    
    if api_key and secret_key:
        exchanges[user_id] = ccxt.binance({
            'apiKey': api_key,
            'secret': secret_key,
            'enableRateLimit': True,
            'options': {
                'defaultType': 'future'
            }
        })
        logger.info(f"✅ {config['name']} Exchange 객체 생성 완료")
    else:
        logger.warning(f"⚠️ {config['name']} API 키가 설정되지 않았습니다.")

# Primary User의 exchange 객체 (하위 호환성)
exchange = exchanges.get('USER1')

# 텔레그램 설정
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_IDS = os.getenv('TELEGRAM_CHAT_IDS', '').split(',')

# ============ AI Decision Models ============
class TradingDecision(BaseModel):
    """트레이딩 시그널 검증용 모델"""
    decision: str = Field(..., pattern="^(approve|reject|modify|reverse)$")  # 'reverse' 추가
    modified_action: str = Field(..., pattern="^(buy|sell|hold)$")
    percentage: int = Field(..., ge=0, le=100)  # reject일 때 0 허용
    reason: str = Field(..., min_length=1)
    stop_loss_price: float = Field(..., ge=0)   # reject일 때 0 허용
    take_profit_price: float = Field(..., ge=0) # reject일 때 0 허용
    pl_ratio: float = Field(..., ge=0, le=10.0) # reject일 때 0 허용, 상한 확장
    confidence: float = Field(..., ge=0.0, le=1.0)
    
    @model_validator(mode='after')
    def validate_non_reject_fields(self):
        """reject가 아닌 경우에만 필수 필드 검증"""
        if self.decision != 'reject':
            if self.percentage < 1:
                raise ValueError(f"percentage must be >= 1 for {self.decision} decision")
            if self.stop_loss_price <= 0:
                raise ValueError(f"stop_loss_price must be > 0 for {self.decision} decision")
            if self.take_profit_price <= 0:
                raise ValueError(f"take_profit_price must be > 0 for {self.decision} decision")
            if self.pl_ratio < 1.0:
                raise ValueError(f"pl_ratio must be >= 1.0 for {self.decision} decision")
        return self

class ClosePositionDecision(BaseModel):
    """청산 시그널 검증용 모델 (SL/TP 불필요)"""
    decision: str = Field(..., pattern="^(approve|reject)$")
    reason: str = Field(..., min_length=1)
    confidence: float = Field(..., ge=0.0, le=1.0)
    urgency: str = Field(..., pattern="^(immediate|soon|normal|low)$")

class PositionExitDecision(BaseModel):
    """포지션 종료 결정용 모델 - v7.1 개선 버전"""
    decision: str = Field(..., pattern="^(hold|close|partial_close)$")
    percentage: int = Field(..., ge=0, le=100)
    reason: str = Field(..., min_length=1)
    exit_type: str = Field(
        ..., 
        pattern="^(take_profit|stop_loss|trend_reversal|risk_management|time_stop|profit_protection|stagnation|none)$"
    )
    confidence: float = Field(..., ge=0.0, le=1.0)
    urgency: str = Field(..., pattern="^(immediate|soon|watch|none)$")

# 🆕 JSON 파싱 오류 시 AI 복구용 모델
class EmergencyTradingDecision(BaseModel):
    """JSON 파싱 오류 시 AI가 자동으로 파라미터를 설정"""
    percentage: int = Field(..., ge=1, le=100)
    stop_loss_price: float = Field(..., gt=0)
    take_profit_price: float = Field(..., gt=0)
    leverage: int = Field(..., ge=1, le=20)
    reason: str = Field(..., min_length=1)
    confidence: float = Field(..., ge=0.0, le=1.0)

# ============ 다중 종목 설정 ============
SYMBOL_CONFIG = {
    'BTC/USDT': {
        'leverage': 10,
        'position_size_percent': 40,
        'min_position_size': 10,
        'max_position_size': 100000,
        'enabled': True,
        'ai_validation': True,
        'ai_monitoring': True
    },
    'SAHARA/USDT': {
        'leverage': 5,
        'position_size_percent': 40,
        'min_position_size': 10,
        'max_position_size': 100000,
        'enabled': True,
        'ai_validation': True,
        'ai_monitoring': True
    },
    'ETH/USDT': {
        'leverage': 5,
        'position_size_percent': 40,
        'min_position_size': 10,
        'max_position_size': 100000,
        'enabled': True,
        'ai_validation': True,
        'ai_monitoring': True
    },
    'RESOLV/USDT': {
        'leverage': 5,
        'position_size_percent': 40,
        'min_position_size': 10,
        'max_position_size': 100000,
        'enabled': True,
        'ai_validation': True,
        'ai_monitoring': True
    },
    'BIO/USDT': {
        'leverage': 5,
        'position_size_percent': 40,
        'min_position_size': 10,
        'max_position_size': 100000,
        'enabled': True,
        'ai_validation': True,
        'ai_monitoring': True
    },
    'UNI/USDT': {
        'leverage': 5,
        'position_size_percent': 40,
        'min_position_size': 10,
        'max_position_size': 100000,
        'enabled': True,
        'ai_validation': True,
        'ai_monitoring': True
    },
    'PENGU/USDT': {
        'leverage': 5,
        'position_size_percent': 40,
        'min_position_size': 10,
        'max_position_size': 100000,
        'enabled': True,
        'ai_validation': True,
        'ai_monitoring': True
    },
    'UMA/USDT': {
        'leverage': 5,
        'position_size_percent': 40,
        'min_position_size': 10,
        'max_position_size': 100000,
        'enabled': True,
        'ai_validation': True,
        'ai_monitoring': True
    },
    'COMP/USDT': {
        'leverage': 5,
        'position_size_percent': 40,
        'min_position_size': 10,
        'max_position_size': 100000,
        'enabled': True,
        'ai_validation': True,
        'ai_monitoring': True
    },
    'XLM/USDT': {
        'leverage': 5,
        'position_size_percent': 40,
        'min_position_size': 10,
        'max_position_size': 100000,
        'enabled': True,
        'ai_validation': True,
        'ai_monitoring': True
    },
    'DOT/USDT': {
        'leverage': 5,
        'position_size_percent': 40,
        'min_position_size': 10,
        'max_position_size': 100000,
        'enabled': True,
        'ai_validation': True,
        'ai_monitoring': True
    },
    'ENA/USDT': {
        'leverage': 5,
        'position_size_percent': 40,
        'min_position_size': 10,
        'max_position_size': 100000,
        'enabled': True,
        'ai_validation': True,
        'ai_monitoring': True
    },
    'RLC/USDT': {
        'leverage': 5,
        'position_size_percent': 40,
        'min_position_size': 10,
        'max_position_size': 100000,
        'enabled': True,
        'ai_validation': True,
        'ai_monitoring': True
    },
    'ETHFI/USDT': {
        'leverage': 5,
        'position_size_percent': 40,
        'min_position_size': 10,
        'max_position_size': 100000,
        'enabled': True,
        'ai_validation': True,
        'ai_monitoring': True
    },
    'SOL/USDT': {
        'leverage': 5,
        'position_size_percent': 40,
        'min_position_size': 10,
        'max_position_size': 100000,
        'enabled': True,
        'ai_validation': True,
        'ai_monitoring': True
    },
    'PYTH/USDT': {
        'leverage': 5,
        'position_size_percent': 40,
        'min_position_size': 10,
        'max_position_size': 100000,
        'enabled': True,
        'ai_validation': True,
        'ai_monitoring': True
    },
    'LINK/USDT': {
        'leverage': 5,
        'position_size_percent': 40,
        'min_position_size': 10,
        'max_position_size': 100000,
        'enabled': True,
        'ai_validation': True,
        'ai_monitoring': True
    },
    'ADA/USDT': {
        'leverage': 5,
        'position_size_percent': 40,
        'min_position_size': 10,
        'max_position_size': 100000,
        'enabled': True,
        'ai_validation': True,
        'ai_monitoring': True
    },
    'XRP/USDT': {
        'leverage': 5,
        'position_size_percent': 40,
        'min_position_size': 10,
        'max_position_size': 100000,
        'enabled': True,
        'ai_validation': True,
        'ai_monitoring': True
    },
    'BNB/USDT': {
        'leverage': 5,
        'position_size_percent': 40,
        'min_position_size': 10,
        'max_position_size': 100000,
        'enabled': True,
        'ai_validation': True,
        'ai_monitoring': True
    },
    'DOGE/USDT': {
        'leverage': 5,
        'position_size_percent': 40,
        'min_position_size': 10,
        'max_position_size': 100000,
        'enabled': True,
        'ai_validation': True,
        'ai_monitoring': True
    },
    'ACH/USDT': {
        'leverage': 5,
        'position_size_percent': 40,
        'min_position_size': 10,
        'max_position_size': 100000,
        'enabled': True,
        'ai_validation': True,
        'ai_monitoring': True
    },
    'CRV/USDT': {
        'leverage': 5,
        'position_size_percent': 40,
        'min_position_size': 10,
        'max_position_size': 100000,
        'enabled': True,
        'ai_validation': True,
        'ai_monitoring': True
    },
    'RONIN/USDT': {
        'leverage': 5,
        'position_size_percent': 40,
        'min_position_size': 10,
        'max_position_size': 100000,
        'enabled': True,
        'ai_validation': True,
        'ai_monitoring': True
    },
    'BCH/USDT': {
        'leverage': 5,
        'position_size_percent': 40,
        'min_position_size': 10,
        'max_position_size': 100000,
        'enabled': True,
        'ai_validation': True,
        'ai_monitoring': True
    },
    'LSK/USDT': {
        'leverage': 5,
        'position_size_percent': 40,
        'min_position_size': 10,
        'max_position_size': 100000,
        'enabled': True,
        'ai_validation': True,
        'ai_monitoring': True
    },
    'HBAR/USDT': {
        'leverage': 5,
        'position_size_percent': 40,
        'min_position_size': 10,
        'max_position_size': 100000,
        'enabled': True,
        'ai_validation': True,
        'ai_monitoring': True
    },
    'AGLD/USDT': {
        'leverage': 5,
        'position_size_percent': 40,
        'min_position_size': 10,
        'max_position_size': 100000,
        'enabled': True,
        'ai_validation': True,
        'ai_monitoring': True
    },
    'ONDO/USDT': {
        'leverage': 5,
        'position_size_percent': 40,
        'min_position_size': 10,
        'max_position_size': 100000,
        'enabled': True,
        'ai_validation': True,
        'ai_monitoring': True
    },
    'HOME/USDT': {
        'leverage': 5,
        'position_size_percent': 40,
        'min_position_size': 10,
        'max_position_size': 100000,
        'enabled': True,
        'ai_validation': True,
        'ai_monitoring': True
    },
    'TRX/USDT': {
        'leverage': 5,
        'position_size_percent': 40,
        'min_position_size': 10,
        'max_position_size': 100000,
        'enabled': True,
        'ai_validation': True,
        'ai_monitoring': True
    },
    'ASTER/USDT': {
        'leverage': 5,
        'position_size_percent': 40,
        'min_position_size': 10,
        'max_position_size': 100000,
        'enabled': True,
        'ai_validation': True,
        'ai_monitoring': True
    },
    'DASH/USDT': {
        'leverage': 5,
        'position_size_percent': 40,
        'min_position_size': 10,
        'max_position_size': 100000,
        'enabled': True,
        'ai_validation': True,
        'ai_monitoring': True
    },
    'TRUMP/USDT': {
        'leverage': 5,
        'position_size_percent': 40,
        'min_position_size': 10,
        'max_position_size': 100000,
        'enabled': True,
        'ai_validation': True,
        'ai_monitoring': True
    },
    'SUI/USDT': {
        'leverage': 5,
        'position_size_percent': 40,
        'min_position_size': 10,
        'max_position_size': 100000,
        'enabled': True,
        'ai_validation': True,
        'ai_monitoring': True
    },
    'WLD/USDT': {
        'leverage': 5,
        'position_size_percent': 40,
        'min_position_size': 10,
        'max_position_size': 100000,
        'enabled': True,
        'ai_validation': True,
        'ai_monitoring': True
    },
    'GIGGLE/USDT': {
        'leverage': 5,
        'position_size_percent': 40,
        'min_position_size': 10,
        'max_position_size': 100000,
        'enabled': True,
        'ai_validation': True,
        'ai_monitoring': True
    },
    'LTC/USDT': {
        'leverage': 5,
        'position_size_percent': 40,
        'min_position_size': 10,
        'max_position_size': 100000,
        'enabled': True,
        'ai_validation': True,
        'ai_monitoring': True
    },
    'DUSK/USDT': {
        'leverage': 5,
        'position_size_percent': 40,
        'min_position_size': 10,
        'max_position_size': 100000,
        'enabled': True,
        'ai_validation': True,
        'ai_monitoring': True
    },
    'FET/USDT': {
        'leverage': 5,
        'position_size_percent': 40,
        'min_position_size': 10,
        'max_position_size': 100000,
        'enabled': True,
        'ai_validation': True,
        'ai_monitoring': True
    },
    'PENDLE/USDT': {
        'leverage': 5,
        'position_size_percent': 40,
        'min_position_size': 10,
        'max_position_size': 100000,
        'enabled': True,
        'ai_validation': True,
        'ai_monitoring': True
    },
    'FIL/USDT': {
        'leverage': 5,
        'position_size_percent': 40,
        'min_position_size': 10,
        'max_position_size': 100000,
        'enabled': True,
        'ai_validation': True,
        'ai_monitoring': True
    },
    'AR/USDT': {
        'leverage': 5,
        'position_size_percent': 40,
        'min_position_size': 10,
        'max_position_size': 100000,
        'enabled': True,
        'ai_validation': True,
        'ai_monitoring': True
    },
    'OG/USDT': {
        'leverage': 5,
        'position_size_percent': 40,
        'min_position_size': 10,
        'max_position_size': 100000,
        'enabled': True,
        'ai_validation': True,
        'ai_monitoring': True
    },
    'F/USDT': {
        'leverage': 5,
        'position_size_percent': 40,
        'min_position_size': 10,
        'max_position_size': 100000,
        'enabled': True,
        'ai_validation': True,
        'ai_monitoring': True
    },
    'TAO/USDT': {
        'leverage': 5,
        'position_size_percent': 40,
        'min_position_size': 10,
        'max_position_size': 100000,
        'enabled': True,
        'ai_validation': True,
        'ai_monitoring': True
    },
    'RAYSOL/USDT': {
        'leverage': 5,
        'position_size_percent': 40,
        'min_position_size': 10,
        'max_position_size': 100000,
        'enabled': True,
        'ai_validation': True,
        'ai_monitoring': True
    },
    'COTI/USDT': {
        'leverage': 5,
        'position_size_percent': 40,
        'min_position_size': 10,
        'max_position_size': 100000,
        'enabled': True,
        'ai_validation': True,
        'ai_monitoring': True
    },
    'SOON/USDT': {
        'leverage': 5,
        'position_size_percent': 40,
        'min_position_size': 10,
        'max_position_size': 100000,
        'enabled': True,
        'ai_validation': True,
        'ai_monitoring': True
    },
    'KERNEL/USDT': {
        'leverage': 5,
        'position_size_percent': 40,
        'min_position_size': 10,
        'max_position_size': 100000,
        'enabled': True,
        'ai_validation': True,
        'ai_monitoring': True
    },
    'SYN/USDT': {
        'leverage': 5,
        'position_size_percent': 40,
        'min_position_size': 10,
        'max_position_size': 100000,
        'enabled': True,
        'ai_validation': True,
        'ai_monitoring': True
    },
    'HYPE/USDT': {
        'leverage': 5,
        'position_size_percent': 40,
        'min_position_size': 10,
        'max_position_size': 100000,
        'enabled': True,
        'ai_validation': True,
        'ai_monitoring': True
    },
    'API3/USDT': {
        'leverage': 5,
        'position_size_percent': 40,
        'min_position_size': 10,
        'max_position_size': 100000,
        'enabled': True,
        'ai_validation': True,
        'ai_monitoring': True
    },
    'KAITO/USDT': {
        'leverage': 5,
        'position_size_percent': 40,
        'min_position_size': 10,
        'max_position_size': 100000,
        'enabled': True,
        'ai_validation': True,
        'ai_monitoring': True
    },
    'AERO/USDT': {
        'leverage': 5,
        'position_size_percent': 40,
        'min_position_size': 10,
        'max_position_size': 100000,
        'enabled': True,
        'ai_validation': True,
        'ai_monitoring': True
    },
    'APT/USDT': {
        'leverage': 5,
        'position_size_percent': 40,
        'min_position_size': 10,
        'max_position_size': 100000,
        'enabled': True,
        'ai_validation': True,
        'ai_monitoring': True
    },
    'PIPPIN/USDT': {
        'leverage': 5,
        'position_size_percent': 40,
        'min_position_size': 10,
        'max_position_size': 100000,
        'enabled': True,
        'ai_validation': True,
        'ai_monitoring': True
    },
    'NEAR/USDT': {
        'leverage': 5,
        'position_size_percent': 40,
        'min_position_size': 10,
        'max_position_size': 100000,
        'enabled': True,
        'ai_validation': True,
        'ai_monitoring': True
    },
    'MANA/USDT': {
        'leverage': 5,
        'position_size_percent': 40,
        'min_position_size': 10,
        'max_position_size': 100000,
        'enabled': True,
        'ai_validation': True,
        'ai_monitoring': True
    },
    'ZEC/USDT': {
        'leverage': 5,
        'position_size_percent': 40,
        'min_position_size': 10,
        'max_position_size': 100000,
        'enabled': True,
        'ai_validation': True,
        'ai_monitoring': True
    },
    'POL/USDT': {
        'leverage': 5,
        'position_size_percent': 40,
        'min_position_size': 10,
        'max_position_size': 100000,
        'enabled': True,
        'ai_validation': True,
        'ai_monitoring': True
    },
    'SAND/USDT': {
        'leverage': 5,
        'position_size_percent': 40,
        'min_position_size': 10,
        'max_position_size': 100000,
        'enabled': True,
        'ai_validation': True,
        'ai_monitoring': True
    },
    'GOAT/USDT': {
        'leverage': 5,
        'position_size_percent': 40,
        'min_position_size': 10,
        'max_position_size': 100000,
        'enabled': True,
        'ai_validation': True,
        'ai_monitoring': True
    },
    'PARTI/USDT': {
        'leverage': 5,
        'position_size_percent': 40,
        'min_position_size': 10,
        'max_position_size': 100000,
        'enabled': True,
        'ai_validation': True,
        'ai_monitoring': True
    },
    'FLOW/USDT': {
        'leverage': 5,
        'position_size_percent': 40,
        'min_position_size': 10,
        'max_position_size': 100000,
        'enabled': True,
        'ai_validation': True,
        'ai_monitoring': True
    },
    'AAVE/USDT': {
        'leverage': 5,
        'position_size_percent': 40,
        'min_position_size': 10,
        'max_position_size': 100000,
        'enabled': True,
        'ai_validation': True,
        'ai_monitoring': True
    },   
    'PUMP/USDT': {
        'leverage': 5,
        'position_size_percent': 40,
        'min_position_size': 10,
        'max_position_size': 100000,
        'enabled': True,
        'ai_validation': True,
        'ai_monitoring': True
    },
    'XPL/USDT': {
        'leverage': 5,
        'position_size_percent': 40,
        'min_position_size': 10,
        'max_position_size': 100000,
        'enabled': True,
        'ai_validation': True,
        'ai_monitoring': True
    }, 
    'TON/USDT': {
        'leverage': 5,
        'position_size_percent': 40,
        'min_position_size': 10,
        'max_position_size': 100000,
        'enabled': True,
        'ai_validation': True,
        'ai_monitoring': True
    }, 
    'ICP/USDT': {
        'leverage': 5,
        'position_size_percent': 40,
        'min_position_size': 10,
        'max_position_size': 100000,
        'enabled': True,
        'ai_validation': True,
        'ai_monitoring': True
    }, 
    'HBAR/USDT': {
        'leverage': 5,
        'position_size_percent': 40,
        'min_position_size': 10,
        'max_position_size': 100000,
        'enabled': True,
        'ai_validation': True,
        'ai_monitoring': True
    }, 
    'ATOM/USDT': {
        'leverage': 5,
        'position_size_percent': 40,
        'min_position_size': 10,
        'max_position_size': 100000,
        'enabled': True,
        'ai_validation': True,
        'ai_monitoring': True
    }, 
    'OM/USDT': {
        'leverage': 5,
        'position_size_percent': 40,
        'min_position_size': 10,
        'max_position_size': 100000,
        'enabled': True,
        'ai_validation': True,
        'ai_monitoring': True
    }, 
    'SENTI/USDT': {
        'leverage': 5,
        'position_size_percent': 40,
        'min_position_size': 10,
        'max_position_size': 100000,
        'enabled': True,
        'ai_validation': True,
        'ai_monitoring': True
    }, 
    'ALLO/USDT': {
        'leverage': 5,
        'position_size_percent': 40,
        'min_position_size': 10,
        'max_position_size': 100000,
        'enabled': True,
        'ai_validation': True,
        'ai_monitoring': True
    }, 
    'AX/USDT': {
        'leverage': 5,
        'position_size_percent': 40,
        'min_position_size': 10,
        'max_position_size': 100000,
        'enabled': True,
        'ai_validation': True,
        'ai_monitoring': True
    }, 
    'MIRA/USDT': {
        'leverage': 5,
        'position_size_percent': 40,
        'min_position_size': 10,
        'max_position_size': 100000,
        'enabled': True,
        'ai_validation': True,
        'ai_monitoring': True
    }, 
    'RED/USDT': {
        'leverage': 5,
        'position_size_percent': 40,
        'min_position_size': 10,
        'max_position_size': 100000,
        'enabled': True,
        'ai_validation': True,
        'ai_monitoring': True
    }, 
    'FOGO/USDT': {
        'leverage': 5,
        'position_size_percent': 40,
        'min_position_size': 10,
        'max_position_size': 100000,
        'enabled': True,
        'ai_validation': True,
        'ai_monitoring': True
    }, 
    'YB/USDT': {
        'leverage': 5,
        'position_size_percent': 40,
        'min_position_size': 10,
        'max_position_size': 100000,
        'enabled': True,
        'ai_validation': True,
        'ai_monitoring': True
    }, 
    'ROSE/USDT': {
        'leverage': 5,
        'position_size_percent': 40,
        'min_position_size': 10,
        'max_position_size': 100000,
        'enabled': True,
        'ai_validation': True,
        'ai_monitoring': True
    }, 
    'SYRUP/USDT': {
        'leverage': 5,
        'position_size_percent': 40,
        'min_position_size': 10,
        'max_position_size': 100000,
        'enabled': True,
        'ai_validation': True,
        'ai_monitoring': True
    }, 
}

# 🆕 v7.3: 심볼 정규화 함수
def normalize_symbol(symbol: str) -> str:
    """
    ccxt 선물 심볼을 표준 형식으로 정규화
    
    Examples:
        'BTC/USDT:USDT' → 'BTC/USDT'
        'OG/USDT:USDT' → 'OG/USDT'
        'ETH/USDT' → 'ETH/USDT' (이미 정규화됨)
    """
    if ':' in symbol:
        # 'BTC/USDT:USDT' → 'BTC/USDT'
        return symbol.split(':')[0]
    return symbol


def get_symbol_config(symbol: str) -> dict:
    """
    🆕 v7.3: 정규화된 심볼로 SYMBOL_CONFIG 조회
    
    Args:
        symbol: 원본 심볼 (예: 'BTC/USDT:USDT' 또는 'BTC/USDT')
    
    Returns:
        dict: 심볼 설정 또는 빈 딕셔너리
    """
    normalized = normalize_symbol(symbol)
    return SYMBOL_CONFIG.get(normalized, {})


def is_symbol_configured(symbol: str) -> bool:
    """
    🆕 v7.3: 심볼이 SYMBOL_CONFIG에 정의되어 있는지 확인
    """
    normalized = normalize_symbol(symbol)
    return normalized in SYMBOL_CONFIG


# 기본 설정
DEFAULT_POSITION_SIZE_PERCENT = float(os.getenv('POSITION_SIZE_PERCENT', 10))
DEFAULT_TRAILING_STOP_PERCENT = 3.0
DEFAULT_TRAILING_ACTIVATION_PERCENT = 1.5

# 현재 포지션 추적을 위한 딕셔너리
current_positions = {}

# 🆕 v7.1 Peak Profit Tracking
position_peak_profits = {}  # {symbol: {'peak_pnl': float, 'peak_time': datetime, 'peak_price': float}}

def update_peak_profit(symbol, current_pnl, current_price):
    """포지션의 최고 수익률 추적 - v7.1"""
    global position_peak_profits
    
    if symbol not in position_peak_profits:
        position_peak_profits[symbol] = {
            'peak_pnl': current_pnl,
            'peak_time': datetime.now(),
            'peak_price': current_price
        }
    elif current_pnl > position_peak_profits[symbol]['peak_pnl']:
        position_peak_profits[symbol] = {
            'peak_pnl': current_pnl,
            'peak_time': datetime.now(),
            'peak_price': current_price
        }
    return position_peak_profits[symbol]

def get_profit_drawdown(symbol, current_pnl):
    """
    최고 수익 대비 현재 수익 하락률 계산 - v7.6 개선
    
    v7.6 개선사항:
    - 최소 peak threshold 추가 (peak < 1.5%이면 drawdown % 무시)
    - 절대값 기반 drawdown도 함께 반환
    - 초반 변동성에 의한 왜곡 방지
    """
    global position_peak_profits
    
    if symbol not in position_peak_profits:
        return 0
    
    peak_pnl = position_peak_profits[symbol]['peak_pnl']
    if peak_pnl <= 0:
        return 0
    
    # 🆕 v7.6: 최소 peak threshold - peak가 너무 작으면 drawdown % 계산이 왜곡됨
    # 예: peak 0.5%, current -1.2% → drawdown = 340% (비정상적)
    MIN_PEAK_THRESHOLD = 1.5  # 최소 1.5% 이상의 peak에서만 drawdown % 경고 적용
    
    if peak_pnl < MIN_PEAK_THRESHOLD:
        # peak가 작으면 0 반환 (왜곡 방지)
        return 0
    
    # 최고점 대비 하락률 (%)
    drawdown = ((peak_pnl - current_pnl) / peak_pnl) * 100
    return max(0, drawdown)


def get_profit_drawdown_absolute(symbol, current_pnl):
    """
    🆕 v7.6: 절대값 기반 drawdown 계산
    peak에서 현재까지 절대적으로 얼마나 떨어졌는지 (%)
    
    예: peak 5%, current 2% → absolute_drawdown = 3%
    """
    global position_peak_profits
    
    if symbol not in position_peak_profits:
        return 0
    
    peak_pnl = position_peak_profits[symbol]['peak_pnl']
    if peak_pnl <= 0:
        return 0
    
    # 절대적 하락폭 (%)
    absolute_drawdown = peak_pnl - current_pnl
    return max(0, absolute_drawdown)


def calculate_trailing_profit_threshold(peak_pnl: float, holding_minutes: float) -> dict:
    """
    🆕 v7.5: Trailing Profit Protection 임계값 계산
    
    Peak profit이 높을수록 더 타이트한 drawdown 임계값 적용
    - 수익이 클수록 빨리 보호
    - 보유 시간이 길수록 더 보수적
    """
    result = {
        'drawdown_threshold': 50.0,
        'absolute_threshold': 5.0,
        'urgency_level': 'normal',
        'action': 'hold'
    }
    
    if peak_pnl < 5.0:
        return result
    
    # Tier 1: 초고수익 구간 (Peak >= 50%)
    if peak_pnl >= 50.0:
        result['drawdown_threshold'] = 20.0
        result['absolute_threshold'] = peak_pnl * 0.3
        if holding_minutes >= 60:
            result['drawdown_threshold'] = 15.0
            result['urgency_level'] = 'critical'
            result['action'] = 'exit_immediately'
        else:
            result['urgency_level'] = 'warning'
            result['action'] = 'prepare_exit'
    
    # Tier 2: 고수익 구간 (Peak >= 30%)
    elif peak_pnl >= 30.0:
        result['drawdown_threshold'] = 25.0
        result['absolute_threshold'] = peak_pnl * 0.35
        if holding_minutes >= 90:
            result['drawdown_threshold'] = 20.0
            result['urgency_level'] = 'critical'
            result['action'] = 'exit_soon'
        elif holding_minutes >= 45:
            result['urgency_level'] = 'warning'
            result['action'] = 'prepare_exit'
        else:
            result['urgency_level'] = 'watch'
            result['action'] = 'monitor_closely'
    
    # Tier 3: 중간수익 구간 (Peak >= 15%)
    elif peak_pnl >= 15.0:
        result['drawdown_threshold'] = 30.0
        result['absolute_threshold'] = peak_pnl * 0.40
        if holding_minutes >= 120:
            result['drawdown_threshold'] = 25.0
            result['urgency_level'] = 'warning'
            result['action'] = 'prepare_exit'
        else:
            result['urgency_level'] = 'watch'
            result['action'] = 'monitor'
    
    # Tier 4: 소수익 구간 (Peak >= 5%)
    elif peak_pnl >= 5.0:
        result['drawdown_threshold'] = 40.0
        result['absolute_threshold'] = peak_pnl * 0.50
        if holding_minutes >= 180:
            result['drawdown_threshold'] = 35.0
            result['urgency_level'] = 'watch'
            result['action'] = 'consider_exit'
        else:
            result['urgency_level'] = 'normal'
            result['action'] = 'hold'
    
    return result


def should_force_exit_by_trailing_protection(
    peak_pnl: float, 
    current_pnl: float, 
    holding_minutes: float,
    trend_support_4h: int = 0
) -> dict:
    """
    🆕 v7.5: Trailing Protection에 의한 강제 종료 판단
    """
    result = {
        'should_exit': False,
        'reason': '',
        'confidence': 0.0
    }
    
    if peak_pnl < 5.0:
        return result
    
    if peak_pnl > 0:
        drawdown_percent = ((peak_pnl - current_pnl) / peak_pnl) * 100
    else:
        drawdown_percent = 0
    
    absolute_loss = peak_pnl - current_pnl
    thresholds = calculate_trailing_profit_threshold(peak_pnl, holding_minutes)
    
    # 조건 1: 수익 → 손실 전환 (가장 심각)
    if peak_pnl >= 10.0 and current_pnl < 0:
        result['should_exit'] = True
        result['reason'] = f"🚨 CRITICAL: Peak {peak_pnl:+.2f}% → Loss {current_pnl:+.2f}% (Profit turned to loss!)"
        result['confidence'] = 0.95
        return result
    
    # 조건 2: Drawdown이 임계값 초과
    if drawdown_percent >= thresholds['drawdown_threshold']:
        if peak_pnl >= 30.0 or trend_support_4h < 5:
            result['should_exit'] = True
            result['reason'] = f"⛔ Trailing Protection: {drawdown_percent:.1f}% drawdown (threshold: {thresholds['drawdown_threshold']}%)"
            result['confidence'] = min(0.7 + (drawdown_percent - thresholds['drawdown_threshold']) / 50, 0.95)
        elif drawdown_percent >= thresholds['drawdown_threshold'] + 15:
            result['should_exit'] = True
            result['reason'] = f"⛔ Override: {drawdown_percent:.1f}% drawdown exceeds safe limit"
            result['confidence'] = 0.85
    
    # 조건 3: 절대적 손실이 임계값 초과
    if absolute_loss >= thresholds['absolute_threshold']:
        if not result['should_exit']:
            result['should_exit'] = True
            result['reason'] = f"⚠️ Absolute loss {absolute_loss:.2f}% from peak (threshold: {thresholds['absolute_threshold']:.2f}%)"
            result['confidence'] = 0.75
    
    # 조건 4: 시간 + 수익 조합
    if holding_minutes >= 180 and peak_pnl >= 20.0:
        if current_pnl < peak_pnl * 0.5:
            if not result['should_exit']:
                result['should_exit'] = True
                result['reason'] = f"⏰ Time-based protection: 3h+ holding, profit dropped to {current_pnl/peak_pnl*100:.0f}% of peak"
                result['confidence'] = 0.80
    
    return result


def generate_v75_profit_alerts(
    peak_pnl: float,
    current_pnl: float,
    holding_minutes: float,
    trend_support_4h: int
) -> list:
    """
    🆕 v7.5: 강화된 수익 보호 경고 생성
    """
    alerts = []
    
    if peak_pnl < 2.0:
        if holding_minutes < 60:
            protection_phase = "STRICT (< 20min)" if holding_minutes < 20 else \
                             "CAUTION (20-40min)" if holding_minutes < 40 else "WATCH (40-60min)"
            alerts.append(f"🛡️ EARLY PROTECTION ACTIVE: {protection_phase}")
        return alerts
    
    if peak_pnl > 0:
        drawdown_percent = ((peak_pnl - current_pnl) / peak_pnl) * 100
    else:
        drawdown_percent = 0
    
    thresholds = calculate_trailing_profit_threshold(peak_pnl, holding_minutes)
    
    # 🚨 CRITICAL: 수익 → 손실 전환
    if peak_pnl >= 5.0 and current_pnl < 0:
        alerts.append(f"🚨🚨🚨 CRITICAL: Peak {peak_pnl:+.2f}% → LOSS {current_pnl:+.2f}%! IMMEDIATE EXIT!")
    
    # ⛔ Trailing Protection 발동
    elif drawdown_percent >= thresholds['drawdown_threshold']:
        alerts.append(f"⛔ TRAILING PROTECTION: {drawdown_percent:.1f}% drawdown (limit: {thresholds['drawdown_threshold']}%)")
        alerts.append(f"   → Action: {thresholds['action'].upper()}")
    
    # 🔴 고수익 대폭 하락
    elif peak_pnl >= 30.0 and drawdown_percent >= 20.0:
        alerts.append(f"🔴 HIGH PROFIT EROSION: Peak {peak_pnl:+.2f}% → Current {current_pnl:+.2f}%")
    
    # 🟠 중수익 하락
    elif peak_pnl >= 15.0 and drawdown_percent >= 25.0:
        alerts.append(f"🟠 PROFIT DRAWDOWN: Peak {peak_pnl:+.2f}% → Current {current_pnl:+.2f}%")
    
    # 🟡 기본 하락 경고
    elif peak_pnl >= 5.0 and drawdown_percent >= 30.0:
        alerts.append(f"🟡 PROFIT WARNING: {drawdown_percent:.1f}% loss from peak")
    
    # 시간 기반 경고
    if holding_minutes >= 180 and peak_pnl >= 20.0 and current_pnl < peak_pnl * 0.5:
        alerts.append(f"⏰ TIME-BASED EXIT: 3h+ holding, profit at {current_pnl/peak_pnl*100:.0f}% of peak")
    
    if holding_minutes >= 120 and current_pnl < 2.0:
        alerts.append(f"⚠️ EXTENDED LOW PROFIT: {holding_minutes:.0f}min with only {current_pnl:+.2f}%")
    
    if holding_minutes >= 90 and abs(current_pnl) < 1.0:
        alerts.append(f"⏰ STAGNATION: {holding_minutes:.0f}min holding, only {current_pnl:+.2f}%")
    
    if holding_minutes < 60:
        protection_phase = "STRICT (< 20min)" if holding_minutes < 20 else \
                         "CAUTION (20-40min)" if holding_minutes < 40 else "WATCH (40-60min)"
        alerts.append(f"🛡️ EARLY PROTECTION: {protection_phase}")
    
    return alerts


def clear_peak_profit(symbol):
    """포지션 종료 시 peak profit 기록 삭제 - v7.1"""
    global position_peak_profits
    if symbol in position_peak_profits:
        del position_peak_profits[symbol]
        logger.info(f"🗑️ {symbol} peak profit 기록 삭제")

# 모니터링 스레드 관리
position_monitor_threads = {}
ai_monitor_thread = None
ai_monitor_running = False

# ============ Position Sync Functions ============
def sync_positions_from_exchange():
    """
    거래소의 실제 포지션을 current_positions와 동기화
    🆕 v7.2 개선: SYMBOL_CONFIG에 없는 심볼도 포함한 모든 포지션 동기화
    - 바이낸스의 모든 활성 포지션 조회
    - 수동 포지션 자동 감지 및 AI 모니터링 대상 추가
    """
    global current_positions
    
    try:
        logger.info("=== 거래소 포지션 동기화 시작 (모든 포지션 스캔) ===")
        
        synced_count = 0
        manual_count = 0
        new_positions = {}
        
        # 🆕 v7.2: 바이낸스에서 모든 포지션 조회 (SYMBOL_CONFIG 제한 없이)
        try:
            all_positions = exchange.fetch_positions()
            logger.info(f"📊 바이낸스에서 {len(all_positions)}개 심볼 포지션 정보 조회")
        except Exception as e:
            logger.error(f"전체 포지션 조회 실패: {e}")
            # 실패 시 기존 방식으로 폴백
            all_positions = []
            for symbol in SYMBOL_CONFIG.keys():
                if SYMBOL_CONFIG[symbol].get('enabled', True):
                    try:
                        positions = exchange.fetch_positions([symbol])
                        all_positions.extend(positions)
                    except:
                        continue
        
        # 모든 포지션 처리
        for position in all_positions:
            try:
                contracts = float(position.get('contracts', 0))
                
                if contracts == 0:  # 포지션 없음
                    continue
                    
                raw_symbol = position.get('symbol', '')
                if not raw_symbol:
                    continue
                
                # 🆕 v7.3: 심볼 정규화 (OG/USDT:USDT → OG/USDT)
                symbol = normalize_symbol(raw_symbol)
                
                entry_price = float(position.get('entryPrice', 0))
                side = 'buy' if position['side'] == 'long' else 'sell'
                
                # 🆕 v7.3: 정규화된 심볼로 SYMBOL_CONFIG 확인
                is_configured = is_symbol_configured(symbol)
                symbol_config = get_symbol_config(symbol)
                
                # 기존 포지션 정보가 있으면 유지, 없으면 새로 생성
                if symbol in current_positions:
                    # 기존 정보 유지 (SL/TP, position_type 등)
                    new_positions[symbol] = current_positions[symbol]
                    # 수량과 진입가는 거래소 기준으로 업데이트
                    new_positions[symbol]['amount'] = abs(contracts)
                    new_positions[symbol]['entry_price'] = entry_price
                    pos_type = new_positions[symbol].get('position_type', 'auto')
                    type_emoji = "🤖" if pos_type == 'auto' else "🔧"
                    logger.info(f"{type_emoji} {symbol} 포지션 업데이트: {side} {abs(contracts):.4f} @ ${entry_price:.2f} ({pos_type.upper()})")
                else:
                    # 🆕 새로운 포지션 발견 → 수동 포지션으로 간주
                    # SYMBOL_CONFIG에 없어도 기본 설정으로 모니터링
                    default_leverage = symbol_config.get('leverage', 10)
                    
                    new_positions[symbol] = {
                        'side': side,
                        'entry_price': entry_price,
                        'amount': abs(contracts),
                        'stop_loss': 0,
                        'take_profit': 0,
                        'trailing_stop_percent': DEFAULT_TRAILING_STOP_PERCENT,
                        'trailing_activation_percent': DEFAULT_TRAILING_ACTIVATION_PERCENT,
                        'entry_time': datetime.now(),
                        'position_type': 'manual',  # 수동 포지션
                        'leverage': default_leverage,
                        'is_configured': is_configured  # SYMBOL_CONFIG 존재 여부
                    }
                    
                    config_status = "✓ CONFIG" if is_configured else "⚠️ NO CONFIG"
                    logger.info(f"🆕🔧 {symbol} 수동 포지션 발견: {side} {abs(contracts):.4f} @ ${entry_price:.2f} [{config_status}]")
                    logger.info(f"   → AI 모니터링 대상에 자동 추가됨")
                    synced_count += 1
                    manual_count += 1
                    
                    # 🆕 v7.3: 정규화된 심볼로 SYMBOL_CONFIG에 동적 추가
                    if not is_configured:
                        logger.warning(f"⚠️ {symbol}이 SYMBOL_CONFIG에 없음 - 기본 설정으로 모니터링")
                        # 동적으로 기본 설정 추가 (정규화된 심볼 사용)
                        SYMBOL_CONFIG[symbol] = {
                            'enabled': True,
                            'leverage': default_leverage,
                            'position_size_percent': 30,
                            'take_profit_percent': 2.0,
                            'stop_loss_percent': 1.5,
                            'ai_monitoring': True,  # AI 모니터링 활성화
                            'dynamic_added': True   # 동적 추가 표시
                        }
                        logger.info(f"   → SYMBOL_CONFIG에 동적 추가 완료 (정규화: {raw_symbol} → {symbol})")
                    
                    # 텔레그램 알림
                    if ENABLE_TELEGRAM:
                        config_msg = "⚠️ SYMBOL_CONFIG에 없음 (기본 설정 적용)" if not is_configured else "✓ CONFIG 존재"
                        send_telegram_notification(
                            f"🔧 <b>수동 포지션 감지</b>\n\n"
                            f"<b>심볼:</b> {symbol}\n"
                            f"<b>방향:</b> {side.upper()}\n"
                            f"<b>진입가:</b> ${entry_price:,.2f}\n"
                            f"<b>수량:</b> {abs(contracts):.4f}\n"
                            f"<b>레버리지:</b> {default_leverage}x\n"
                            f"<b>설정:</b> {config_msg}\n\n"
                            f"✅ AI 모니터링이 자동으로 시작됩니다.\n"
                            f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                            'info'
                        )
                        
            except Exception as e:
                logger.error(f"포지션 처리 오류: {e}")
                continue
        
        # 동기화 완료 - 메모리에 없지만 거래소에 있는 포지션 추가
        for symbol, pos_info in new_positions.items():
            if symbol not in current_positions:
                current_positions[symbol] = pos_info
        
        # 메모리에는 있지만 거래소에 없는 포지션 제거 및 DB 기록
        removed_symbols = []
        for symbol in list(current_positions.keys()):
            if symbol not in new_positions:
                # 종료된 포지션을 completed_trades에 기록 (🆕 v7.8: 바이낸스 실제 데이터)
                try:
                    position_info = current_positions[symbol]
                    record_completed_trade_with_binance(symbol, position_info, 
                                                        close_reason='sync_detected_close')
                    logger.info(f"✅ Closed position recorded for {symbol} (detected by sync)")
                except Exception as e:
                    logger.error(f"Failed to record closed position for {symbol}: {e}")
                
                removed_symbols.append(symbol)
                del current_positions[symbol]
                clear_peak_profit(symbol)
                logger.warning(f"⚠️ {symbol} 포지션이 거래소에 없어 메모리에서 제거 및 DB 기록")
                
                # 🆕 v7.8: 포지션 종료 감지 시 모든 사용자의 TP/SL 주문 취소
                try:
                    total_cancelled = 0
                    for user_id, user_exchange in exchanges.items():
                        user_name = USER_CONFIGS[user_id]['name']
                        cancelled = cancel_symbol_orders(user_exchange, symbol, user_name)
                        if cancelled > 0:
                            total_cancelled += cancelled
                            logger.info(f"[{user_name}] 🗑️ 종료된 포지션 TP/SL {cancelled}개 취소")
                    
                    if total_cancelled > 0:
                        logger.info(f"✅ {symbol} 종료 감지 → 총 {total_cancelled}개 TP/SL 주문 취소 완료")
                        
                        if ENABLE_TELEGRAM:
                            send_telegram_notification(
                                f"🗑️ <b>TP/SL 자동 정리</b>\n\n"
                                f"<b>심볼:</b> {symbol}\n"
                                f"<b>취소된 주문:</b> {total_cancelled}개\n"
                                f"<b>사유:</b> 포지션 종료 감지\n"
                                f"⏰ {datetime.now().strftime('%H:%M:%S')}",
                                'info'
                            )
                except Exception as cancel_err:
                    logger.error(f"❌ {symbol} TP/SL 취소 실패: {cancel_err}")
        
        # 동기화 결과 로깅
        auto_count = sum(1 for pos in current_positions.values() if pos.get('position_type', 'auto') == 'auto')
        manual_total = sum(1 for pos in current_positions.values() if pos.get('position_type', 'auto') == 'manual')
        configured_count = sum(1 for pos in current_positions.values() if pos.get('is_configured', True))
        dynamic_count = len(current_positions) - configured_count
        
        logger.info(f"=== 동기화 완료 ===")
        logger.info(f"총 포지션: {len(current_positions)}개")
        logger.info(f"  - 자동(AI) 포지션: {auto_count}개")
        logger.info(f"  - 수동 포지션: {manual_total}개 (이번 사이클: {manual_count}개)")
        logger.info(f"  - CONFIG 있음: {configured_count}개")
        logger.info(f"  - 동적 추가: {dynamic_count}개")
        logger.info(f"  - 새로 발견: {synced_count}개")
        logger.info(f"  - 제거: {len(removed_symbols)}개")
        
        return len(current_positions)
        
    except Exception as e:
        logger.error(f"포지션 동기화 오류: {str(e)}", exc_info=True)
        return 0


def cancel_symbol_orders(user_exchange, symbol, user_name="User"):
    """🆕 특정 심볼의 모든 열린 주문 취소 (TP/SL 포함)"""
    try:
        open_orders = user_exchange.fetch_open_orders(symbol)
        
        if not open_orders:
            logger.info(f"[{user_name}] {symbol}: 취소할 주문 없음")
            return 0
        
        cancelled_count = 0
        for order in open_orders:
            try:
                user_exchange.cancel_order(order['id'], symbol)
                order_type = order.get('type', 'UNKNOWN')
                order_side = order.get('side', 'UNKNOWN')
                order_price = order.get('price', 'N/A')
                logger.info(f"[{user_name}] ✅ 주문 취소: {symbol} {order_type} {order_side} @ ${order_price}")
                cancelled_count += 1
            except Exception as e:
                logger.error(f"[{user_name}] 주문 취소 실패 ({order['id']}): {str(e)}")
        
        return cancelled_count
        
    except Exception as e:
        logger.error(f"[{user_name}] {symbol} 주문 취소 중 오류: {str(e)}")
        return 0


def cleanup_orphan_orders():
    """
    🆕 v7.8: 고아 주문 정리 - 포지션 없는 심볼의 열린 주문 모두 취소
    
    주기적으로 호출하여 포지션 종료 후 남은 TP/SL 주문을 정리합니다.
    """
    total_cancelled = 0
    orphan_symbols = set()
    
    try:
        logger.info("=== 고아 주문 정리 시작 ===")
        
        for user_id, user_exchange in exchanges.items():
            user_name = USER_CONFIGS[user_id]['name']
            
            try:
                # 1. 추적 중인 심볼 + 설정된 심볼에서만 주문 조회 (rate limit 회피)
                symbols_to_check = set()
                for sym in current_positions:
                    symbols_to_check.add(sym)
                for sym_key in SYMBOL_CONFIG:
                    normalized = normalize_symbol(sym_key)
                    symbols_to_check.add(normalized)
                
                all_open_orders = []
                for sym in symbols_to_check:
                    try:
                        orders = user_exchange.fetch_open_orders(sym)
                        all_open_orders.extend(orders)
                    except Exception:
                        pass  # 심볼별 조회 실패는 무시
                
                if not all_open_orders:
                    continue
                
                # 2. 열린 주문이 있는 심볼 목록
                order_symbols = set()
                for order in all_open_orders:
                    order_symbol = order.get('symbol', '')
                    if order_symbol:
                        # 심볼 정규화
                        normalized = normalize_symbol(order_symbol)
                        order_symbols.add(normalized)
                
                # 3. 각 심볼에 대해 포지션 확인
                for symbol in order_symbols:
                    # 메모리에 포지션이 있으면 스킵
                    if symbol in current_positions:
                        continue
                    
                    # 거래소에서 실제 포지션 확인
                    try:
                        positions = user_exchange.fetch_positions([symbol])
                        has_position = False
                        
                        for pos in positions:
                            if float(pos.get('contracts', 0)) != 0:
                                has_position = True
                                break
                        
                        if not has_position:
                            # 포지션 없는데 주문 있음 → 취소
                            cancelled = cancel_symbol_orders(user_exchange, symbol, user_name)
                            if cancelled > 0:
                                total_cancelled += cancelled
                                orphan_symbols.add(symbol)
                                logger.warning(f"[{user_name}] 🧹 고아 주문 정리: {symbol} - {cancelled}개 취소")
                                
                    except Exception as pos_err:
                        logger.debug(f"[{user_name}] {symbol} 포지션 확인 실패: {pos_err}")
                        continue
                        
            except Exception as user_err:
                logger.error(f"[{user_name}] 고아 주문 정리 중 오류: {user_err}")
                continue
        
        # 결과 로깅
        if total_cancelled > 0:
            logger.info(f"=== 고아 주문 정리 완료: {total_cancelled}개 취소 (심볼: {', '.join(orphan_symbols)}) ===")
            
            if ENABLE_TELEGRAM:
                send_telegram_notification(
                    f"🧹 <b>고아 주문 자동 정리</b>\n\n"
                    f"<b>취소된 주문:</b> {total_cancelled}개\n"
                    f"<b>정리된 심볼:</b> {', '.join(orphan_symbols)}\n"
                    f"<b>사유:</b> 포지션 없는 TP/SL 주문\n"
                    f"⏰ {datetime.now().strftime('%H:%M:%S')}",
                    'info'
                )
        else:
            logger.info("=== 고아 주문 정리 완료: 정리할 주문 없음 ===")
        
        return total_cancelled
        
    except Exception as e:
        logger.error(f"고아 주문 정리 오류: {e}")
        return 0


def get_position_summary():
    """현재 포지션 요약 정보 (position_type 포함)"""
    if not current_positions:
        return "현재 보유 포지션 없음"
    
    summary = []
    for symbol, pos in current_positions.items():
        pos_type = pos.get('position_type', 'auto')
        type_emoji = "🤖" if pos_type == 'auto' else "🔧"
        summary.append(f"{type_emoji} {symbol}: {pos['side'].upper()} {pos['amount']:.4f} @ ${pos['entry_price']:.2f} ({pos_type.upper()})")
    
    return "\n".join(summary)

# ============ SQLite 데이터베이스 초기화 ============
def fetch_realized_pnl_from_binance(user_exchange, symbol, since_ms=None):
    """
    🆕 v7.8: 바이낸스에서 실제 실현 손익(Realized PnL) 조회
    
    Args:
        user_exchange: CCXT exchange 인스턴스
        symbol: 거래 심볼 (예: 'BTC/USDT')
        since_ms: 조회 시작 시간 (밀리초 타임스탬프, None이면 최근 24시간)
    
    Returns:
        dict: {
            'realized_pnl': float,      # 바이낸스 실현 PnL (USDT)
            'commission': float,         # 총 수수료
            'entry_price_avg': float,    # 평균 진입가
            'exit_price_avg': float,     # 평균 종료가
            'total_qty': float,          # 총 수량
            'trades': list               # 원본 거래 내역
        }
    """
    try:
        if since_ms is None:
            since_ms = int((datetime.now() - timedelta(hours=24)).timestamp() * 1000)
        
        # 바이낸스 선물 거래 내역 조회
        trades = user_exchange.fetch_my_trades(symbol, since=since_ms, limit=100)
        
        if not trades:
            logger.warning(f"바이낸스 거래 내역 없음: {symbol}")
            return None
        
        total_pnl = 0.0
        total_commission = 0.0
        buy_cost = 0.0
        buy_qty = 0.0
        sell_cost = 0.0
        sell_qty = 0.0
        
        for t in trades:
            info = t.get('info', {})
            
            # realizedPnl (바이낸스 선물 전용)
            rpnl = float(info.get('realizedPnl', 0))
            total_pnl += rpnl
            
            # 수수료
            commission = float(t.get('fee', {}).get('cost', 0) or 0)
            total_commission += abs(commission)
            
            # 평균 가격 계산용
            price = float(t.get('price', 0))
            qty = float(t.get('amount', 0))
            
            if t.get('side') == 'buy':
                buy_cost += price * qty
                buy_qty += qty
            else:
                sell_cost += price * qty
                sell_qty += qty
        
        entry_avg = (buy_cost / buy_qty) if buy_qty > 0 else 0
        exit_avg = (sell_cost / sell_qty) if sell_qty > 0 else 0
        
        result = {
            'realized_pnl': total_pnl,
            'commission': total_commission,
            'entry_price_avg': entry_avg,
            'exit_price_avg': exit_avg,
            'total_qty': max(buy_qty, sell_qty),
            'trade_count': len(trades)
        }
        
        logger.info(f"📊 바이낸스 실제 PnL: {symbol} = ${total_pnl:+.4f} (수수료: ${total_commission:.4f}, 거래 {len(trades)}건)")
        return result
        
    except Exception as e:
        logger.error(f"바이낸스 PnL 조회 실패 ({symbol}): {e}")
        return None


def record_completed_trade_with_binance(symbol, position_info, close_reason='manual'):
    """
    🆕 v7.8: 포지션 종료 시 바이낸스 실제 데이터로 DB 기록
    AI ON/OFF, 자동/수동 모두 동일하게 기록
    
    Args:
        symbol: 거래 심볼
        position_info: current_positions에서 가져온 포지션 정보
        close_reason: 종료 사유
    """
    try:
        entry_time = position_info.get('entry_time', datetime.now())
        if isinstance(entry_time, str):
            entry_time = datetime.fromisoformat(entry_time)
        
        since_ms = int(entry_time.timestamp() * 1000)
        
        # 바이낸스에서 실제 거래 데이터 조회
        binance_data = fetch_realized_pnl_from_binance(exchange, symbol, since_ms=since_ms)
        
        conn = get_db_connection()
        c = conn.cursor()
        
        entry_price = position_info.get('entry_price', 0)
        amount = position_info.get('amount', 0)
        side = position_info.get('side', 'long')
        leverage = position_info.get('leverage', 10)
        position_type = position_info.get('position_type', 'auto')
        
        exit_time = datetime.now()
        holding_time_minutes = (exit_time - entry_time).total_seconds() / 60
        
        if binance_data and binance_data['realized_pnl'] != 0:
            # ✅ 바이낸스 실제 데이터 사용
            pnl_usdt = binance_data['realized_pnl']
            commission = binance_data['commission']
            
            # 바이낸스 평균 가격 사용 (더 정확)
            if binance_data['entry_price_avg'] > 0:
                entry_price = binance_data['entry_price_avg']
            
            exit_price = binance_data['exit_price_avg'] if binance_data['exit_price_avg'] > 0 else entry_price
            
            position_size_usdt = amount * entry_price
            pnl_percent = (pnl_usdt / position_size_usdt * 100) if position_size_usdt > 0 else 0
            
            logger.info(f"✅ 바이낸스 실제 데이터 사용: {symbol} PnL=${pnl_usdt:+.4f} ({pnl_percent:+.2f}%)")
        else:
            # ⚠️ 바이낸스 조회 실패 시 자체 계산 (fallback)
            try:
                ticker = exchange.fetch_ticker(symbol)
                exit_price = ticker['last']
            except:
                exit_price = entry_price
            
            if side in ['long', 'buy']:
                price_change_pct = ((exit_price - entry_price) / entry_price * 100) if entry_price > 0 else 0
            else:
                price_change_pct = ((entry_price - exit_price) / entry_price * 100) if entry_price > 0 else 0
            
            pnl_percent = price_change_pct * leverage
            position_size_usdt = amount * entry_price
            pnl_usdt = position_size_usdt * pnl_percent / 100
            commission = 0
            pnl_usdt = pnl_usdt  # 바이낸스 데이터 없음 표시용
            
            logger.warning(f"⚠️ 자체 계산 사용 (바이낸스 조회 실패): {symbol} PnL≈${pnl_usdt:+.4f}")
        
        is_win = 1 if pnl_usdt > 0 else 0
        realized_pnl_binance = binance_data['realized_pnl'] if binance_data else None
        
        # 중복 방지
        if not is_duplicate_completed_trade(conn, symbol, entry_time, exit_time, time_window_seconds=5):
            c.execute("""INSERT INTO completed_trades 
                        (open_timestamp, close_timestamp, symbol, side, entry_price, exit_price,
                         amount, pnl_usdt, pnl_percent, position_size_usdt, holding_time_minutes,
                         close_reason, leverage, is_win, position_type, commission, realized_pnl_binance)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                      (entry_time.isoformat(), exit_time.isoformat(), symbol, side,
                       entry_price, exit_price, amount, pnl_usdt, pnl_percent, position_size_usdt,
                       holding_time_minutes, close_reason, leverage, is_win, position_type,
                       commission, realized_pnl_binance))
            
            conn.commit()
            src = "바이낸스" if binance_data else "자체계산"
            logger.info(f"✅ 거래 기록 완료 [{src}]: {symbol} ({position_type}) PnL=${pnl_usdt:+.2f} ({pnl_percent:+.2f}%) 사유={close_reason}")
            
            # Reflection 트리거
            try:
                c.execute("SELECT COUNT(*) FROM completed_trades WHERE close_timestamp >= datetime('now', '-1 hour')")
                recent_count = c.fetchone()[0]
                if recent_count > 0 and recent_count % 5 == 0:
                    trigger_reflection_generation()
            except Exception as refl_err:
                logger.warning(f"Reflection trigger check failed: {refl_err}")
        else:
            logger.info(f"⏭️ 중복 거래 기록 스킵: {symbol}")
        
        conn.close()
        return True
        
    except Exception as e:
        logger.error(f"❌ 거래 기록 실패: {str(e)}", exc_info=True)
        return False


def record_completed_trade(symbol, position_info, exit_price, close_reason='manual'):
    """완료된 거래를 DB에 기록 (🆕 position_type 포함)"""
    try:
        conn = get_db_connection()
        c = conn.cursor()
        
        # PnL 계산 (레버리지 반영)
        entry_price = position_info.get('entry_price', 0)
        amount = position_info.get('amount', 0)
        side = position_info.get('side', 'buy')
        leverage = position_info.get('leverage', 10)
        position_type = position_info.get('position_type', 'auto')  # 🆕
        
        # 가격 변화율 계산
        if side == 'buy':
            price_change_percent = ((exit_price - entry_price) / entry_price) * 100
        else:  # sell
            price_change_percent = ((entry_price - exit_price) / entry_price) * 100
        
        # 레버리지 적용 - 실제 수익률
        pnl_percent = price_change_percent * leverage
        
        position_size_usdt = amount * entry_price
        pnl_usdt = (position_size_usdt * pnl_percent / 100)
        
        # 보유 시간 계산
        entry_time = position_info.get('entry_time', datetime.now())
        if isinstance(entry_time, str):
            entry_time = datetime.fromisoformat(entry_time)
        holding_time_minutes = (datetime.now() - entry_time).total_seconds() / 60
        
        # is_win 판단
        is_win = 1 if pnl_percent > 0 else 0
        
        # 🔒 중복 기록 방지: 동일한 entry_time과 최근 5초 내 종료 기록 확인
        exit_time = datetime.now()
        if not is_duplicate_completed_trade(conn, symbol, entry_time, exit_time, time_window_seconds=5):
            c.execute("""INSERT INTO completed_trades 
                        (open_timestamp, close_timestamp, symbol, side, entry_price, exit_price,
                         amount, pnl_usdt, pnl_percent, position_size_usdt, holding_time_minutes,
                         close_reason, leverage, is_win, position_type)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                      (entry_time.isoformat(), exit_time.isoformat(), symbol, side, 
                       entry_price, exit_price, amount, pnl_usdt, pnl_percent, position_size_usdt,
                       holding_time_minutes, close_reason, leverage, is_win, position_type))
            
            conn.commit()
            logger.info(f"✅ 완료된 거래 기록: {symbol} ({position_type.upper()}) - PnL: ${pnl_usdt:,.2f} ({pnl_percent:.2f}%)")
            
            # 🆕 v7.7: 완료된 거래 5건마다 Reflection 생성 트리거
            try:
                c.execute("SELECT COUNT(*) FROM completed_trades WHERE close_timestamp >= datetime('now', '-1 hour')")
                recent_count = c.fetchone()[0]
                
                # 최근 1시간 내 5건 이상 완료 시 Reflection 생성
                if recent_count > 0 and recent_count % 5 == 0:
                    logger.info(f"🔄 Triggering reflection after {recent_count} recent trades")
                    # 비동기적으로 실행하지 않고 직접 호출
                    trigger_reflection_generation()
            except Exception as refl_err:
                logger.warning(f"Reflection trigger check failed: {refl_err}")
        else:
            logger.info(f"⏭️  중복 완료 거래 기록 스킵: {symbol}")
        
        conn.close()
        
        return True
        
    except Exception as e:
        logger.error(f"❌ 완료된 거래 기록 실패: {str(e)}")
        return False

def record_balance_snapshot(exchange):
    """잔고 스냅샷 기록"""
    try:
        conn = get_db_connection()
        c = conn.cursor()
        
        # 잔고 정보 가져오기
        balance = exchange.fetch_balance()
        total_balance = balance['USDT']['total']
        free_balance = balance['USDT']['free']
        used_balance = balance['USDT']['used']
        
        # 활성 포지션 수
        active_positions = len(current_positions)
        
        # 총 포지션 가치
        total_position_value = 0
        for symbol, pos in current_positions.items():
            position_value = pos.get('position_size_usdt', 0)
            if position_value == 0:
                # position_size_usdt가 없으면 계산
                amount = pos.get('amount', 0)
                entry_price = pos.get('entry_price', 0)
                position_value = amount * entry_price
            total_position_value += position_value
        
        # 총 PnL 계산 (완료된 거래들의 합)
        c.execute("SELECT SUM(pnl_usdt) FROM completed_trades")
        result = c.fetchone()
        total_pnl = result[0] if result[0] else 0
        
        # DB에 저장
        c.execute("""INSERT INTO balance_history 
                    (timestamp, total_balance, free_balance, used_balance,
                     active_positions, total_position_value, total_pnl)
                    VALUES (?, ?, ?, ?, ?, ?, ?)""",
                  (datetime.now().isoformat(), total_balance, free_balance, used_balance,
                   active_positions, total_position_value, total_pnl))
        
        conn.commit()
        conn.close()
        
        logger.debug(f"📊 잔고 스냅샷 기록: Total ${total_balance:,.2f}, Free ${free_balance:,.2f}")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ 잔고 스냅샷 기록 실패: {str(e)}")
        return False

def record_position_history(exchange):
    """현재 포지션 히스토리 기록"""
    try:
        conn = get_db_connection()
        c = conn.cursor()
        
        for symbol, pos in current_positions.items():
            # 현재가 조회
            ticker = exchange.fetch_ticker(symbol)
            current_price = ticker['last']
            
            # PnL 계산 (레버리지 반영)
            entry_price = pos.get('entry_price', 0)
            amount = pos.get('amount', 0)
            side = pos.get('side', 'buy')
            leverage = pos.get('leverage', 10)
            
            # 가격 변화율 계산
            if side == 'buy':
                price_change_percent = ((current_price - entry_price) / entry_price) * 100
            else:
                price_change_percent = ((entry_price - current_price) / entry_price) * 100
            
            # 레버리지 적용 - 실제 수익률
            pnl_percent = price_change_percent * leverage
            
            position_size_usdt = amount * entry_price  # 진입 시점 포지션 크기
            position_value = amount * current_price  # 현재 포지션 가치
            pnl_usdt = (position_size_usdt * pnl_percent / 100)
            required_margin = position_value / leverage
            
            # 청산가격 계산 (대략적)
            if side == 'buy':
                liquidation_price = entry_price * (1 - (0.8 / leverage))
            else:
                liquidation_price = entry_price * (1 + (0.8 / leverage))
            
            # DB에 저장
            c.execute("""INSERT INTO position_history 
                        (timestamp, symbol, side, amount, entry_price, current_price,
                         pnl_usdt, pnl_percent, position_value, required_margin, liquidation_price)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                      (datetime.now().isoformat(), symbol, side, amount, entry_price, current_price,
                       pnl_usdt, pnl_percent, position_value, required_margin, liquidation_price))
        
        conn.commit()
        conn.close()
        
        logger.debug(f"📈 포지션 히스토리 기록 완료: {len(current_positions)}개")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ 포지션 히스토리 기록 실패: {str(e)}")
        return False

def get_db_connection():
    """DB 연결 반환 (초기화 메시지 없음)"""
    return sqlite3.connect('integrated_trades.db')

# init_db 별칭 (호환성 유지)
init_db = get_db_connection

def init_db_once():
    """DB 초기화 - 프로그램 시작 시 1회만 실행 (🆕 position_type 지원)"""
    conn = sqlite3.connect('integrated_trades.db')
    c = conn.cursor()
    
    # 테이블 존재 여부 확인
    c.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table'")
    table_count = c.fetchone()[0]
    
    if table_count >= 4:  # 이미 초기화됨
        # 🆕 기존 테이블에 position_type 컬럼이 없으면 추가 (마이그레이션)
        try:
            c.execute("SELECT position_type FROM completed_trades LIMIT 1")
        except sqlite3.OperationalError:
            logger.info("🔧 completed_trades 테이블에 position_type 컬럼 추가 중...")
            c.execute("ALTER TABLE completed_trades ADD COLUMN position_type TEXT DEFAULT 'auto'")
            conn.commit()
            logger.info("✅ position_type 컬럼 추가 완료")
        
        # 🆕 v7.1 대시보드 호환: realized_pnl_binance 컬럼 추가
        try:
            c.execute("SELECT realized_pnl_binance FROM completed_trades LIMIT 1")
        except sqlite3.OperationalError:
            logger.info("🔧 completed_trades 테이블에 realized_pnl_binance 컬럼 추가 중...")
            c.execute("ALTER TABLE completed_trades ADD COLUMN realized_pnl_binance REAL DEFAULT NULL")
            conn.commit()
            logger.info("✅ realized_pnl_binance 컬럼 추가 완료 (대시보드 호환)")
        
        conn.close()
        return
    
    # 1. 실시간 거래 테이블 (기존)
    c.execute('''CREATE TABLE IF NOT EXISTS trades
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  timestamp TEXT,
                  symbol TEXT,
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
                  urgency TEXT,
                  status TEXT DEFAULT 'active',
                  position_size_usdt REAL,
                  required_margin REAL,
                  leverage INTEGER)''')
    
    # 2. 완료된 거래 테이블 (대시보드용, 🆕 position_type 컬럼 추가)
    c.execute('''CREATE TABLE IF NOT EXISTS completed_trades
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  open_timestamp TEXT NOT NULL,
                  close_timestamp TEXT NOT NULL,
                  symbol TEXT NOT NULL,
                  side TEXT NOT NULL,
                  entry_price REAL,
                  exit_price REAL,
                  amount REAL,
                  pnl_usdt REAL,
                  pnl_percent REAL,
                  position_size_usdt REAL,
                  holding_time_minutes REAL,
                  close_reason TEXT,
                  max_profit_percent REAL,
                  max_loss_percent REAL,
                  leverage INTEGER,
                  is_win INTEGER DEFAULT 0,
                  commission REAL DEFAULT 0,
                  position_type TEXT DEFAULT 'auto',
                  realized_pnl_binance REAL DEFAULT NULL)''')
    
    # 3. 잔고 히스토리 (대시보드용)
    c.execute('''CREATE TABLE IF NOT EXISTS balance_history
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  timestamp TEXT NOT NULL,
                  total_balance REAL,
                  free_balance REAL,
                  used_balance REAL,
                  active_positions INTEGER,
                  total_position_value REAL,
                  total_pnl REAL)''')
    
    # 4. 포지션 히스토리
    c.execute('''CREATE TABLE IF NOT EXISTS position_history
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  timestamp TEXT NOT NULL,
                  symbol TEXT NOT NULL,
                  side TEXT NOT NULL,
                  amount REAL,
                  entry_price REAL,
                  current_price REAL,
                  pnl_usdt REAL,
                  pnl_percent REAL,
                  position_value REAL,
                  required_margin REAL,
                  liquidation_price REAL)''')
    
    # 5. 🆕 v7.7: Reflection History 테이블 (AI 종합 분석 저장)
    c.execute('''CREATE TABLE IF NOT EXISTS reflection_history
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  timestamp TEXT NOT NULL,
                  reflection_text TEXT NOT NULL,
                  total_trades INTEGER,
                  win_rate REAL,
                  recent_win_rate REAL,
                  total_pnl REAL,
                  risk_reward_ratio REAL,
                  performance_trend TEXT,
                  symbols_analyzed TEXT)''')
    
    # 인덱스 생성 (성능 향상)
    c.execute('''CREATE INDEX IF NOT EXISTS idx_trades_timestamp 
                 ON trades(timestamp DESC)''')
    c.execute('''CREATE INDEX IF NOT EXISTS idx_completed_trades_timestamp 
                 ON completed_trades(close_timestamp DESC)''')
    c.execute('''CREATE INDEX IF NOT EXISTS idx_balance_history_timestamp 
                 ON balance_history(timestamp DESC)''')
    
    conn.commit()
    logger.info("✅ DB 초기화 완료 (프로그램 시작, position_type 지원)")
    return conn

# ============ Technical Indicators 추가 ============
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

# ============ 🆕 v7.1 강화된 과매수/과매도 필터링 함수 ============
def check_overbought_oversold_multi_timeframe(df_15min, df_hourly, df_4h, action):
    """
    🆕 v7.1 강화된 멀티 타임프레임 과매수/과매도 체크
    
    주요 개선사항:
    - 더 엄격한 RSI 기준 (75/25)
    - 멀티 타임프레임 Stochastic 분석 추가
    - Williams %R 극단값 체크 추가
    - CMF 반대 신호 (매수인데 자금유출, 매도인데 자금유입) 체크
    - MACD/DI 크로스 실시간 감지
    - 볼린저 밴드 멀티 타임프레임 확인
    - 반대 진입 기준 완화 (2개 신호 또는 강도 5점 이상)
    
    Returns:
        dict: 과매수/과매도 분석 결과
    """
    warnings = []
    risk_scores = []
    reverse_signals = []
    reverse_strength_points = 0  # 🆕 반대 진입 강도 점수
    
    # ===== RSI 체크 (더 세분화된 기준) =====
    rsi_15m = df_15min['rsi'].iloc[-1]
    rsi_1h = df_hourly['rsi'].iloc[-1]
    rsi_4h = df_4h['rsi'].iloc[-1]
    
    # 15분봉 RSI
    if action == 'buy':
        if rsi_15m > 75:
            warnings.append(f"⚠️ 15분봉 RSI 과매수 ({rsi_15m:.1f})")
            risk_scores.append(3)
            reverse_signals.append("15m_RSI_overbought")
            reverse_strength_points += 1
            if rsi_15m > 80:
                reverse_signals.append("15m_RSI_extreme_overbought")
                reverse_strength_points += 2
        elif rsi_15m > 65:
            risk_scores.append(1)
    elif action == 'sell':
        if rsi_15m < 25:
            warnings.append(f"⚠️ 15분봉 RSI 과매도 ({rsi_15m:.1f})")
            risk_scores.append(3)
            reverse_signals.append("15m_RSI_oversold")
            reverse_strength_points += 1
            if rsi_15m < 20:
                reverse_signals.append("15m_RSI_extreme_oversold")
                reverse_strength_points += 2
        elif rsi_15m < 35:
            risk_scores.append(1)
    
    # 1시간봉 RSI (더 중요)
    if action == 'buy':
        if rsi_1h > 70:
            warnings.append(f"🔴 1시간봉 RSI 과매수 ({rsi_1h:.1f})")
            risk_scores.append(4)
            reverse_signals.append("1h_RSI_overbought")
            reverse_strength_points += 2
            if rsi_1h > 80:
                reverse_signals.append("1h_RSI_extreme_overbought")
                reverse_strength_points += 3
        elif rsi_1h > 60:
            risk_scores.append(2)
    elif action == 'sell':
        if rsi_1h < 30:
            warnings.append(f"🔴 1시간봉 RSI 과매도 ({rsi_1h:.1f})")
            risk_scores.append(4)
            reverse_signals.append("1h_RSI_oversold")
            reverse_strength_points += 2
            if rsi_1h < 20:
                reverse_signals.append("1h_RSI_extreme_oversold")
                reverse_strength_points += 3
        elif rsi_1h < 40:
            risk_scores.append(2)
    
    # 4시간봉 RSI (가장 중요)
    if action == 'buy':
        if rsi_4h > 70:
            warnings.append(f"🔴 4시간봉 RSI 과매수 ({rsi_4h:.1f})")
            risk_scores.append(5)
            reverse_signals.append("4h_RSI_overbought")
            reverse_strength_points += 3
            if rsi_4h > 80:
                reverse_signals.append("4h_RSI_extreme_overbought")
                reverse_strength_points += 4
        elif rsi_4h > 60:
            risk_scores.append(2)
    elif action == 'sell':
        if rsi_4h < 30:
            warnings.append(f"🔴 4시간봉 RSI 과매도 ({rsi_4h:.1f})")
            risk_scores.append(5)
            reverse_signals.append("4h_RSI_oversold")
            reverse_strength_points += 3
            if rsi_4h < 20:
                reverse_signals.append("4h_RSI_extreme_oversold")
                reverse_strength_points += 4
        elif rsi_4h < 40:
            risk_scores.append(2)
    
    # ===== Stochastic 체크 =====
    stoch_k_15m = df_15min['stoch_k'].iloc[-1] if 'stoch_k' in df_15min.columns else 50
    stoch_k_1h = df_hourly['stoch_k'].iloc[-1] if 'stoch_k' in df_hourly.columns else 50
    
    if action == 'buy':
        if stoch_k_15m > 85 and stoch_k_1h > 80:
            warnings.append(f"⚠️ Stochastic 멀티 타임프레임 과매수 (15m: {stoch_k_15m:.1f}, 1h: {stoch_k_1h:.1f})")
            risk_scores.append(3)
            reverse_signals.append("stoch_multi_overbought")
            reverse_strength_points += 2
        elif stoch_k_1h > 90:
            reverse_signals.append("stoch_1h_extreme_overbought")
            reverse_strength_points += 2
    elif action == 'sell':
        if stoch_k_15m < 15 and stoch_k_1h < 20:
            warnings.append(f"⚠️ Stochastic 멀티 타임프레임 과매도 (15m: {stoch_k_15m:.1f}, 1h: {stoch_k_1h:.1f})")
            risk_scores.append(3)
            reverse_signals.append("stoch_multi_oversold")
            reverse_strength_points += 2
        elif stoch_k_1h < 10:
            reverse_signals.append("stoch_1h_extreme_oversold")
            reverse_strength_points += 2
    
    # ===== Williams %R 체크 =====
    williams_15m = df_15min['williams_r'].iloc[-1] if 'williams_r' in df_15min.columns else -50
    williams_1h = df_hourly['williams_r'].iloc[-1] if 'williams_r' in df_hourly.columns else -50
    
    if action == 'buy':
        if williams_15m > -10 and williams_1h > -20:
            warnings.append(f"⚠️ Williams %R 극단적 과매수 (15m: {williams_15m:.1f}, 1h: {williams_1h:.1f})")
            reverse_signals.append("williams_extreme_overbought")
            reverse_strength_points += 2
            risk_scores.append(2)
    elif action == 'sell':
        if williams_15m < -90 and williams_1h < -80:
            warnings.append(f"⚠️ Williams %R 극단적 과매도 (15m: {williams_15m:.1f}, 1h: {williams_1h:.1f})")
            reverse_signals.append("williams_extreme_oversold")
            reverse_strength_points += 2
            risk_scores.append(2)
    
    # ===== 볼린저 밴드 체크 =====
    current_price = df_15min['close'].iloc[-1]
    bb_upper_15m = df_15min['bb_bbh'].iloc[-1]
    bb_lower_15m = df_15min['bb_bbl'].iloc[-1]
    bb_upper_1h = df_hourly['bb_bbh'].iloc[-1]
    bb_lower_1h = df_hourly['bb_bbl'].iloc[-1]
    
    if action == 'buy':
        if current_price > bb_upper_15m and current_price > bb_upper_1h:
            warnings.append(f"🔴 멀티 타임프레임 볼린저 상단 돌파 (가격 과열)")
            risk_scores.append(4)
            reverse_signals.append("bb_multi_overbought")
            reverse_strength_points += 3
        elif current_price > bb_upper_15m:
            warnings.append(f"⚠️ 15분봉 볼린저 상단 돌파")
            risk_scores.append(2)
            reverse_signals.append("bb_15m_overbought")
            reverse_strength_points += 1
    elif action == 'sell':
        if current_price < bb_lower_15m and current_price < bb_lower_1h:
            warnings.append(f"🔴 멀티 타임프레임 볼린저 하단 돌파 (가격 침체)")
            risk_scores.append(4)
            reverse_signals.append("bb_multi_oversold")
            reverse_strength_points += 3
        elif current_price < bb_lower_15m:
            warnings.append(f"⚠️ 15분봉 볼린저 하단 돌파")
            risk_scores.append(2)
            reverse_signals.append("bb_15m_oversold")
            reverse_strength_points += 1
    
    # ===== CMF (Money Flow) 반대 신호 체크 =====
    cmf_15m = df_15min['cmf'].iloc[-1] if 'cmf' in df_15min.columns else 0
    cmf_1h = df_hourly['cmf'].iloc[-1] if 'cmf' in df_hourly.columns else 0
    
    if action == 'buy':
        # 매수 신호인데 자금이 유출 중
        if cmf_15m < -0.1 and cmf_1h < -0.05:
            warnings.append(f"⚠️ CMF 음수 (자금 유출 중 - 매수에 불리)")
            reverse_signals.append("cmf_negative_divergence")
            reverse_strength_points += 2
            risk_scores.append(2)
    elif action == 'sell':
        # 매도 신호인데 자금이 유입 중
        if cmf_15m > 0.1 and cmf_1h > 0.05:
            warnings.append(f"⚠️ CMF 양수 (자금 유입 중 - 매도에 불리)")
            reverse_signals.append("cmf_positive_divergence")
            reverse_strength_points += 2
            risk_scores.append(2)
    
    # ===== MACD 다이버전스 체크 =====
    macd_1h = df_hourly['macd'].iloc[-1]
    macd_signal_1h = df_hourly['macd_signal'].iloc[-1]
    macd_prev_1h = df_hourly['macd'].iloc[-2]
    macd_signal_prev_1h = df_hourly['macd_signal'].iloc[-2]
    
    if action == 'buy':
        # 매수 신호인데 MACD가 데드크로스
        if macd_1h < macd_signal_1h and macd_prev_1h >= macd_signal_prev_1h:
            warnings.append(f"🔴 1H MACD 데드크로스 발생 (매수 위험!)")
            reverse_signals.append("macd_1h_death_cross")
            reverse_strength_points += 3
            risk_scores.append(4)
    elif action == 'sell':
        # 매도 신호인데 MACD가 골든크로스
        if macd_1h > macd_signal_1h and macd_prev_1h <= macd_signal_prev_1h:
            warnings.append(f"🔴 1H MACD 골든크로스 발생 (매도 위험!)")
            reverse_signals.append("macd_1h_golden_cross")
            reverse_strength_points += 3
            risk_scores.append(4)
    
    # ===== ADX/DI 추세 강도 체크 =====
    adx_1h = df_hourly['adx'].iloc[-1] if 'adx' in df_hourly.columns else 25
    di_plus_1h = df_hourly['di_plus'].iloc[-1] if 'di_plus' in df_hourly.columns else 25
    di_minus_1h = df_hourly['di_minus'].iloc[-1] if 'di_minus' in df_hourly.columns else 25
    
    if action == 'buy':
        # 매수인데 DI-가 DI+ 보다 크게 우세
        if di_minus_1h > di_plus_1h + 10 and adx_1h > 25:
            warnings.append(f"🔴 강한 하락 추세 중 (DI-: {di_minus_1h:.1f} > DI+: {di_plus_1h:.1f})")
            reverse_signals.append("di_strong_bearish")
            reverse_strength_points += 3
            risk_scores.append(4)
    elif action == 'sell':
        # 매도인데 DI+가 DI- 보다 크게 우세
        if di_plus_1h > di_minus_1h + 10 and adx_1h > 25:
            warnings.append(f"🔴 강한 상승 추세 중 (DI+: {di_plus_1h:.1f} > DI-: {di_minus_1h:.1f})")
            reverse_signals.append("di_strong_bullish")
            reverse_strength_points += 3
            risk_scores.append(4)
    
    # ===== 최종 계산 =====
    total_risk = sum(risk_scores)
    
    # 🆕 반대 진입 기회 판단 (기준 완화: 2개 신호 또는 강도 5점 이상)
    reverse_opportunity = False
    reverse_strength = min(reverse_strength_points / 15, 1.0)  # 0-1 정규화
    
    if len(reverse_signals) >= 2 or reverse_strength_points >= 5:
        reverse_opportunity = True
        warnings.append(f"🔄 **반대 진입 기회 감지!** (신호: {len(reverse_signals)}개, 강도: {reverse_strength:.1%})")
        logger.warning(f"🔄 반대 진입 기회 감지 - {action} 대신 {'sell' if action == 'buy' else 'buy'} 고려")
        logger.warning(f"   감지된 신호: {', '.join(reverse_signals)}")
    
    # 리스크 레벨 결정
    if reverse_opportunity and reverse_strength_points >= 8:
        risk_level = 'extreme'
        is_risky = True
    elif total_risk >= 10 or reverse_strength_points >= 6:
        risk_level = 'high'
        is_risky = True
    elif total_risk >= 6:
        risk_level = 'medium'
        is_risky = True
    elif total_risk >= 3:
        risk_level = 'low'
        is_risky = False
    else:
        risk_level = 'none'
        is_risky = False
    
    return {
        'is_risky': is_risky,
        'risk_level': risk_level,
        'total_risk_score': total_risk,
        'warnings': warnings,
        'scores': {
            'rsi_15m': rsi_15m,
            'rsi_1h': rsi_1h,
            'rsi_4h': rsi_4h,
            'stoch_15m': stoch_k_15m,
            'stoch_1h': stoch_k_1h,
            'williams_15m': williams_15m,
            'cmf_15m': cmf_15m,
            'cmf_1h': cmf_1h
        },
        'reverse_opportunity': reverse_opportunity,
        'reverse_signals': reverse_signals,
        'reverse_strength': reverse_strength,
        'reverse_strength_points': reverse_strength_points
    }

# ============ 🆕 추가 기능 2: 매물대 기반 TP/SL 조정 함수 ============
def calculate_volume_profile_levels(df, num_levels=5):
    """
    거래량 기반 매물대 계산
    
    Returns:
        dict: {
            'support_levels': [prices],
            'resistance_levels': [prices],
            'high_volume_zones': [(price_low, price_high)]
        }
    """
    try:
        # 가격 범위를 bins으로 나누기
        price_range = df['high'].max() - df['low'].min()
        num_bins = 50
        bin_size = price_range / num_bins
        
        # 각 bin의 거래량 합계 계산
        volume_profile = []
        min_price = df['low'].min()
        
        for i in range(num_bins):
            bin_low = min_price + (i * bin_size)
            bin_high = bin_low + bin_size
            bin_mid = (bin_low + bin_high) / 2
            
            # 해당 가격대의 거래량 합계
            mask = (df['low'] <= bin_high) & (df['high'] >= bin_low)
            bin_volume = df.loc[mask, 'volume'].sum()
            
            volume_profile.append({
                'price': bin_mid,
                'volume': bin_volume,
                'range': (bin_low, bin_high)
            })
        
        # 거래량이 많은 구간 찾기 (상위 20%)
        sorted_profile = sorted(volume_profile, key=lambda x: x['volume'], reverse=True)
        high_volume_zones = sorted_profile[:int(num_bins * 0.2)]
        
        # 현재가 기준으로 지지/저항 분류
        current_price = df['close'].iloc[-1]
        
        support_levels = []
        resistance_levels = []
        
        for zone in high_volume_zones:
            if zone['price'] < current_price:
                support_levels.append(zone['price'])
            elif zone['price'] > current_price:
                resistance_levels.append(zone['price'])
        
        # 가격순 정렬
        support_levels = sorted(support_levels, reverse=True)[:num_levels]
        resistance_levels = sorted(resistance_levels)[:num_levels]
        
        return {
            'support_levels': support_levels,
            'resistance_levels': resistance_levels,
            'high_volume_zones': [z['range'] for z in high_volume_zones[:10]]
        }
        
    except Exception as e:
        logger.error(f"매물대 계산 오류: {e}")
        return {
            'support_levels': [],
            'resistance_levels': [],
            'high_volume_zones': []
        }

def adjust_tp_sl_based_on_levels(symbol, action, current_price, original_sl, original_tp, market_data):
    """
    🔄 수정됨: 매물대 및 지지/저항선 기반으로 TP를 더 단기적으로 조정
    
    Returns:
        dict: {
            'adjusted_sl': float,
            'adjusted_tp': float,
            'sl_reason': str,
            'tp_reason': str,
            'is_adjusted': bool,
            'pl_ratio': float
        }
    """
    try:
        df_15min = market_data['df_15min']  # 🆕 15분봉 추가
        df_hourly = market_data['df_hourly']
        df_4h = market_data['df_4h']
        
        # ATR 계산 (변동성 기준)
        atr_15min = df_15min['atr'].iloc[-1]  # 🆕 15분 ATR
        atr_hourly = df_hourly['atr'].iloc[-1]
        atr_4h = df_4h['atr'].iloc[-1]
        
        # 매물대 계산
        volume_profile_15m = calculate_volume_profile_levels(df_15min)  # 🆕 15분 매물대
        volume_profile_1h = calculate_volume_profile_levels(df_hourly)
        volume_profile_4h = calculate_volume_profile_levels(df_4h)
        
        adjusted_sl = original_sl
        adjusted_tp = original_tp
        sl_reason = "원본 유지"
        tp_reason = "원본 유지"
        is_adjusted = False
        
        # === SL 조정 로직 ===
        sl_distance_percent = abs((original_sl - current_price) / current_price) * 100
        
        if action == 'buy':
            # 롱 포지션 SL 조정
            
            # 1. SL이 너무 멀 경우 (5% 이상)
            if sl_distance_percent > 5:
                # 가장 가까운 지지선 찾기
                nearest_support = None
                min_distance = float('inf')
                
                # 1시간봉 지지선 체크
                for support in volume_profile_1h['support_levels']:
                    if support < current_price:
                        distance = current_price - support
                        if distance < min_distance:
                            min_distance = distance
                            nearest_support = support
                
                # ATR 기반 최소 거리 (2 ATR)
                min_sl_distance = current_price - (atr_hourly * 2)
                
                if nearest_support and nearest_support > min_sl_distance:
                    adjusted_sl = nearest_support * 0.995  # 지지선 약간 아래
                    sl_reason = f"가까운 지지선 ({nearest_support:.2f}) 기준 조정"
                    is_adjusted = True
                else:
                    adjusted_sl = min_sl_distance
                    sl_reason = f"2xATR 기준 조정 (과도한 SL 방지)"
                    is_adjusted = True
            
            # 2. SL이 너무 가까운 경우 (<1% 또는 1 ATR 미만)
            elif sl_distance_percent < 1 or (current_price - original_sl) < atr_hourly:
                # 최소 1.5 ATR은 확보
                adjusted_sl = current_price - (atr_hourly * 1.5)
                sl_reason = "1.5xATR 최소 거리 확보"
                is_adjusted = True
                
        else:  # sell 포지션
            # 숏 포지션 SL 조정
            
            # 1. SL이 너무 멀 경우
            if sl_distance_percent > 5:
                # 가장 가까운 저항선 찾기
                nearest_resistance = None
                min_distance = float('inf')
                
                for resistance in volume_profile_1h['resistance_levels']:
                    if resistance > current_price:
                        distance = resistance - current_price
                        if distance < min_distance:
                            min_distance = distance
                            nearest_resistance = resistance
                
                max_sl_distance = current_price + (atr_hourly * 2)
                
                if nearest_resistance and nearest_resistance < max_sl_distance:
                    adjusted_sl = nearest_resistance * 1.005  # 저항선 약간 위
                    sl_reason = f"가까운 저항선 ({nearest_resistance:.2f}) 기준 조정"
                    is_adjusted = True
                else:
                    adjusted_sl = max_sl_distance
                    sl_reason = f"2xATR 기준 조정 (과도한 SL 방지)"
                    is_adjusted = True
            
            elif sl_distance_percent < 1 or (original_sl - current_price) < atr_hourly:
                adjusted_sl = current_price + (atr_hourly * 1.5)
                sl_reason = "1.5xATR 최소 거리 확보"
                is_adjusted = True
        
        # === 🔄 TP 조정 로직 (더 단기적으로 수정) ===
        tp_distance_percent = abs((original_tp - current_price) / current_price) * 100
        
        if action == 'buy':
            # 롱 포지션 TP 조정
            
            # 🆕 1. 단기 저항선 우선 체크 (15분봉)
            immediate_resistance = None
            for resistance in volume_profile_15m['resistance_levels']:
                if resistance > current_price:
                    resistance_distance = (resistance - current_price) / current_price * 100
                    if 0.5 <= resistance_distance <= 3:  # 0.5~3% 범위의 저항선
                        immediate_resistance = resistance
                        break
            
            # 2. TP가 너무 멀 경우 (수정: 10% → 6%)
            if tp_distance_percent > 6:  # 🔄 10% → 6%로 낮춤
                if immediate_resistance:
                    adjusted_tp = immediate_resistance * 0.998  # 🔄 저항선 더 가까이
                    tp_reason = f"단기 저항선 ({immediate_resistance:.2f}) 직전으로 조정"
                    is_adjusted = True
                else:
                    # 다음 1시간 저항선 찾기
                    next_resistance = None
                    for resistance in volume_profile_1h['resistance_levels']:
                        if resistance > current_price:
                            if (resistance - current_price) / current_price * 100 <= 4:  # 🔄 6% → 4%
                                next_resistance = resistance
                                break
                    
                    if next_resistance:
                        adjusted_tp = next_resistance * 0.997  # 🔄 저항선 더 가까이
                        tp_reason = f"1시간 저항선 ({next_resistance:.2f}) 직전으로 조정"
                        is_adjusted = True
                    else:
                        # ATR 기반 (수정: 3.5 → 2.5 ATR)
                        adjusted_tp = current_price + (atr_15min * 2.5)  # 🔄 15분 ATR 사용, 2.5배로 낮춤
                        tp_reason = "2.5x15분ATR 목표가로 조정 (단기 수익)"
                        is_adjusted = True
            
            # 🆕 3. TP가 3~6% 범위일 때도 체크
            elif 3 < tp_distance_percent <= 6:
                if immediate_resistance and immediate_resistance < original_tp:
                    adjusted_tp = immediate_resistance * 0.998
                    tp_reason = f"단기 매물대 ({immediate_resistance:.2f}) 고려"
                    is_adjusted = True
            
            # 4. TP가 너무 가까운 경우 (수정: 1.5% → 1%)
            elif tp_distance_percent < 1:  # 🔄 1.5% → 1%
                # 최소 1.5 ATR은 확보
                adjusted_tp = current_price + (atr_15min * 1.5)  # 🔄 15분 ATR 사용
                tp_reason = "1.5x15분ATR 최소 목표 확보"
                is_adjusted = True
                
        else:  # sell 포지션
            # 숏 포지션 TP 조정
            
            # 🆕 1. 단기 지지선 우선 체크 (15분봉)
            immediate_support = None
            for support in volume_profile_15m['support_levels']:
                if support < current_price:
                    support_distance = (current_price - support) / current_price * 100
                    if 0.5 <= support_distance <= 3:  # 0.5~3% 범위의 지지선
                        immediate_support = support
                        break
            
            # 2. TP가 너무 멀 경우 (수정: 10% → 6%)
            if tp_distance_percent > 6:  # 🔄 10% → 6%
                if immediate_support:
                    adjusted_tp = immediate_support * 1.002  # 🔄 지지선 더 가까이
                    tp_reason = f"단기 지지선 ({immediate_support:.2f}) 직후로 조정"
                    is_adjusted = True
                else:
                    next_support = None
                    for support in volume_profile_1h['support_levels']:
                        if support < current_price:
                            if (current_price - support) / current_price * 100 <= 4:  # 🔄 6% → 4%
                                next_support = support
                                break
                    
                    if next_support:
                        adjusted_tp = next_support * 1.003  # 🔄 지지선 더 가까이
                        tp_reason = f"1시간 지지선 ({next_support:.2f}) 직후로 조정"
                        is_adjusted = True
                    else:
                        adjusted_tp = current_price - (atr_15min * 2.5)  # 🔄 15분 ATR, 2.5배
                        tp_reason = "2.5x15분ATR 목표가로 조정 (단기 수익)"
                        is_adjusted = True
            
            # 🆕 3. TP가 3~6% 범위일 때도 체크
            elif 3 < tp_distance_percent <= 6:
                if immediate_support and immediate_support > original_tp:
                    adjusted_tp = immediate_support * 1.002
                    tp_reason = f"단기 매물대 ({immediate_support:.2f}) 고려"
                    is_adjusted = True
            
            # 4. TP가 너무 가까운 경우
            elif tp_distance_percent < 1:  # 🔄 1.5% → 1%
                adjusted_tp = current_price - (atr_15min * 1.5)  # 🔄 15분 ATR 사용
                tp_reason = "1.5x15분ATR 최소 목표 확보"
                is_adjusted = True
        
        # 최종 검증: Risk/Reward 비율 체크
        sl_distance = abs(adjusted_sl - current_price)
        tp_distance = abs(adjusted_tp - current_price)
        
        if sl_distance > 0:
            rr_ratio = tp_distance / sl_distance
            
            # R:R이 1:1.5 미만이면 TP 늘리기
            if rr_ratio < 1.5:
                if action == 'buy':
                    adjusted_tp = current_price + (sl_distance * 2)
                else:
                    adjusted_tp = current_price - (sl_distance * 2)
                tp_reason += " (R:R 1:2 확보)"
                is_adjusted = True
        
        logger.info(f"💡 TP/SL 조정 결과:")
        logger.info(f"   SL: ${original_sl:.4f} → ${adjusted_sl:.4f} ({sl_reason})")
        logger.info(f"   TP: ${original_tp:.4f} → ${adjusted_tp:.4f} ({tp_reason})")
        
        return {
            'adjusted_sl': adjusted_sl,
            'adjusted_tp': adjusted_tp,
            'sl_reason': sl_reason,
            'tp_reason': tp_reason,
            'is_adjusted': is_adjusted,
            'volume_profile': {
                'support_levels': volume_profile_1h['support_levels'][:3],
                'resistance_levels': volume_profile_1h['resistance_levels'][:3]
            }
        }
        
    except Exception as e:
        logger.error(f"TP/SL 조정 오류: {e}")
        return {
            'adjusted_sl': original_sl,
            'adjusted_tp': original_tp,
            'sl_reason': "조정 실패 - 원본 유지",
            'tp_reason': "조정 실패 - 원본 유지",
            'is_adjusted': False
        }

# ============ 🆕 추가 기능 3: 추세 역전 신호 감지 함수 (개선됨) ============
def detect_trend_reversal_signals(df_15min, df_hourly, df_4h, side):
    """
    🔄 v7.5: 중장기 타임프레임 중심 추세 역전 감지 (트랩 필터 강화)
    
    핵심 원칙:
    - 15분봉 신호는 참고용, 단독으로 exit 결정 불가
    - 1시간봉/4시간봉 확인 필수
    - 연속 캔들 조건으로 노이즈 제거
    - 4시간봉 추세가 유효하면 점수 대폭 차감
    
    Args:
        side: 'buy' (long) or 'sell' (short) - 현재 포지션 방향
    
    Returns:
        dict: reversal analysis result
    """
    reversal_score = 0
    signals = []
    
    # 🔄 v7.5: 임계값 대폭 상향 (트랩 필터)
    threshold_immediate = 12  # 8 → 12 (4h+1h 동시 역전 확인 필요)
    threshold_soon = 9        # 6 → 9
    threshold_watch = 6       # 3 → 6
    
    # ========================================
    # === 4시간봉 추세 지지 확인 (먼저 체크) ===
    # ========================================
    trend_support_4h = 0
    
    # 4시간봉 추세 방향 확인
    di_plus_4h = df_4h['di_plus'].iloc[-1]
    di_minus_4h = df_4h['di_minus'].iloc[-1]
    adx_4h = df_4h['adx'].iloc[-1]
    macd_4h = df_4h['macd'].iloc[-1]
    macd_signal_4h = df_4h['macd_signal'].iloc[-1]
    
    # 추세가 여전히 포지션 방향을 지지하는지 확인
    if side == 'buy':
        if di_plus_4h > di_minus_4h:
            trend_support_4h += 2  # DI+ 우세
        if macd_4h > macd_signal_4h:
            trend_support_4h += 2  # MACD 상승 중
        if adx_4h > 20:
            trend_support_4h += 1  # 추세 강도 유지
        if df_4h['close'].iloc[-1] > df_4h['sma_20'].iloc[-1]:
            trend_support_4h += 2  # 가격이 SMA20 위
    else:  # sell
        if di_minus_4h > di_plus_4h:
            trend_support_4h += 2
        if macd_4h < macd_signal_4h:
            trend_support_4h += 2
        if adx_4h > 20:
            trend_support_4h += 1
        if df_4h['close'].iloc[-1] < df_4h['sma_20'].iloc[-1]:
            trend_support_4h += 2
    
    # ========================================
    # === 15분봉 신호 (참고용, 낮은 점수) ===
    # ========================================
    
    # 15분봉 MACD 크로스오버 (단독 의미 없음, 확인용)
    macd_cross_15m = False
    if side == 'buy':
        if df_15min['macd'].iloc[-1] < df_15min['macd_signal'].iloc[-1] and \
           df_15min['macd'].iloc[-2] >= df_15min['macd_signal'].iloc[-2]:
            macd_cross_15m = True
            reversal_score += 1  # 🔄 2.5 → 1 (대폭 감소)
            signals.append("📉 15m MACD bearish crossover (참고)")
    else:
        if df_15min['macd'].iloc[-1] > df_15min['macd_signal'].iloc[-1] and \
           df_15min['macd'].iloc[-2] <= df_15min['macd_signal'].iloc[-2]:
            macd_cross_15m = True
            reversal_score += 1
            signals.append("📈 15m MACD bullish crossover (참고)")
    
    # 15분봉 RSI 반전 (낮은 점수)
    rsi_15m = df_15min['rsi'].iloc[-1]
    rsi_15m_prev = df_15min['rsi'].iloc[-3]  # 3개 전과 비교 (연속성 확인)
    if side == 'buy':
        if rsi_15m < 60 and rsi_15m_prev > 70:
            reversal_score += 1  # 🔄 1.5 → 1
            signals.append("📉 15m RSI overbought reversal (참고)")
    else:
        if rsi_15m > 40 and rsi_15m_prev < 30:
            reversal_score += 1
            signals.append("📈 15m RSI oversold reversal (참고)")
    
    # ========================================
    # === 1시간봉 신호 (중요, 중간 점수) ===
    # ========================================
    
    # 1시간봉 DI 크로스오버 (중요 신호, 연속 2개 캔들 확인)
    di_cross_1h = False
    if side == 'buy':
        # 연속 2개 캔들에서 DI- > DI+ 확인
        if df_hourly['di_minus'].iloc[-1] > df_hourly['di_plus'].iloc[-1] and \
           df_hourly['di_minus'].iloc[-2] > df_hourly['di_plus'].iloc[-2] and \
           df_hourly['di_minus'].iloc[-3] <= df_hourly['di_plus'].iloc[-3]:
            di_cross_1h = True
            reversal_score += 5  # 🔄 3.5 → 5 (확인된 신호는 상향)
            signals.append("🔴 1h DI- crosses above DI+ (2캔들 확인)")
        elif df_hourly['di_minus'].iloc[-1] > df_hourly['di_plus'].iloc[-1] and \
             df_hourly['di_minus'].iloc[-2] <= df_hourly['di_plus'].iloc[-2]:
            reversal_score += 2  # 단일 캔들은 낮은 점수
            signals.append("⚠️ 1h DI crossover (확인 필요)")
    else:
        if df_hourly['di_plus'].iloc[-1] > df_hourly['di_minus'].iloc[-1] and \
           df_hourly['di_plus'].iloc[-2] > df_hourly['di_minus'].iloc[-2] and \
           df_hourly['di_plus'].iloc[-3] <= df_hourly['di_minus'].iloc[-3]:
            di_cross_1h = True
            reversal_score += 5
            signals.append("🔴 1h DI+ crosses above DI- (2캔들 확인)")
        elif df_hourly['di_plus'].iloc[-1] > df_hourly['di_minus'].iloc[-1] and \
             df_hourly['di_plus'].iloc[-2] <= df_hourly['di_minus'].iloc[-2]:
            reversal_score += 2
            signals.append("⚠️ 1h DI crossover (확인 필요)")
    
    # 1시간봉 ADX 트렌드 약화 (연속 감소 확인)
    adx_1h = df_hourly['adx'].iloc[-1]
    adx_1h_prev = df_hourly['adx'].iloc[-2]
    adx_1h_prev2 = df_hourly['adx'].iloc[-3]
    if adx_1h < adx_1h_prev < adx_1h_prev2 and adx_1h < 22:  # 연속 하락
        reversal_score += 3  # 🔄 2 → 3
        signals.append("📉 1h ADX 연속 하락 (추세 약화)")
    elif adx_1h < 20 and adx_1h_prev > 25:
        reversal_score += 2
        signals.append("⚠️ 1h ADX 급락")
    
    # 1시간봉 CMF 자금 흐름 반전 (연속 확인)
    cmf_1h = df_hourly['cmf'].iloc[-1]
    cmf_1h_prev = df_hourly['cmf'].iloc[-2]
    if side == 'buy':
        if cmf_1h < -0.1 and cmf_1h_prev < -0.05:  # 연속 음수
            reversal_score += 3  # 🔄 2 → 3
            signals.append("🔴 1h CMF 연속 자금유출 확인")
        elif cmf_1h < -0.15:  # 강한 유출
            reversal_score += 2
            signals.append("⚠️ 1h CMF 강한 자금유출")
    else:
        if cmf_1h > 0.1 and cmf_1h_prev > 0.05:
            reversal_score += 3
            signals.append("🔴 1h CMF 연속 자금유입 확인")
        elif cmf_1h > 0.15:
            reversal_score += 2
            signals.append("⚠️ 1h CMF 강한 자금유입")
    
    # 1시간봉 MACD 크로스오버 (중요)
    macd_1h = df_hourly['macd'].iloc[-1]
    macd_signal_1h = df_hourly['macd_signal'].iloc[-1]
    macd_1h_prev = df_hourly['macd'].iloc[-2]
    macd_signal_1h_prev = df_hourly['macd_signal'].iloc[-2]
    
    macd_cross_1h = False
    if side == 'buy':
        if macd_1h < macd_signal_1h and macd_1h_prev >= macd_signal_1h_prev:
            macd_cross_1h = True
            reversal_score += 4  # 🔄 1.5 → 4
            signals.append("🔴 1h MACD 데드크로스 발생")
    else:
        if macd_1h > macd_signal_1h and macd_1h_prev <= macd_signal_1h_prev:
            macd_cross_1h = True
            reversal_score += 4
            signals.append("🔴 1h MACD 골든크로스 발생")
    
    # ========================================
    # === 4시간봉 신호 (가장 중요, 높은 점수) ===
    # ========================================
    
    # 4시간봉 SMA20 이탈 (확정적 신호)
    sma20_break_4h = False
    if side == 'buy':
        # 2캔들 연속 SMA20 아래
        if df_4h['close'].iloc[-1] < df_4h['sma_20'].iloc[-1] and \
           df_4h['close'].iloc[-2] < df_4h['sma_20'].iloc[-2] and \
           df_4h['close'].iloc[-3] >= df_4h['sma_20'].iloc[-3]:
            sma20_break_4h = True
            reversal_score += 6  # 🔄 3 → 6 (확인된 신호)
            signals.append("🔴🔴 4h SMA20 하향 이탈 확인 (2캔들)")
        elif df_4h['close'].iloc[-1] < df_4h['sma_20'].iloc[-1] and \
             df_4h['close'].iloc[-2] >= df_4h['sma_20'].iloc[-2]:
            reversal_score += 3
            signals.append("⚠️ 4h SMA20 하향 이탈 (확인 필요)")
    else:
        if df_4h['close'].iloc[-1] > df_4h['sma_20'].iloc[-1] and \
           df_4h['close'].iloc[-2] > df_4h['sma_20'].iloc[-2] and \
           df_4h['close'].iloc[-3] <= df_4h['sma_20'].iloc[-3]:
            sma20_break_4h = True
            reversal_score += 6
            signals.append("🔴🔴 4h SMA20 상향 돌파 확인 (2캔들)")
        elif df_4h['close'].iloc[-1] > df_4h['sma_20'].iloc[-1] and \
             df_4h['close'].iloc[-2] <= df_4h['sma_20'].iloc[-2]:
            reversal_score += 3
            signals.append("⚠️ 4h SMA20 상향 돌파 (확인 필요)")
    
    # 4시간봉 MACD 크로스오버 (가장 강력한 신호)
    macd_cross_4h = False
    if side == 'buy':
        if macd_4h < macd_signal_4h and df_4h['macd'].iloc[-2] >= df_4h['macd_signal'].iloc[-2]:
            macd_cross_4h = True
            reversal_score += 8  # 🔄 매우 높은 점수
            signals.append("🔴🔴🔴 4h MACD 데드크로스! (중대 역전)")
    else:
        if macd_4h > macd_signal_4h and df_4h['macd'].iloc[-2] <= df_4h['macd_signal'].iloc[-2]:
            macd_cross_4h = True
            reversal_score += 8
            signals.append("🔴🔴🔴 4h MACD 골든크로스! (중대 역전)")
    
    # 4시간봉 DI 크로스오버
    di_cross_4h = False
    if side == 'buy':
        if di_minus_4h > di_plus_4h and df_4h['di_minus'].iloc[-2] <= df_4h['di_plus'].iloc[-2]:
            di_cross_4h = True
            reversal_score += 6
            signals.append("🔴🔴 4h DI- > DI+ 크로스오버")
    else:
        if di_plus_4h > di_minus_4h and df_4h['di_plus'].iloc[-2] <= df_4h['di_minus'].iloc[-2]:
            di_cross_4h = True
            reversal_score += 6
            signals.append("🔴🔴 4h DI+ > DI- 크로스오버")
    
    # 4시간봉 RSI 다이버전스 (연속 5캔들 비교)
    rsi_4h = df_4h['rsi'].iloc[-1]
    rsi_4h_prev = df_4h['rsi'].iloc[-5]  # 5개 전과 비교
    price_4h = df_4h['close'].iloc[-1]
    price_4h_prev = df_4h['close'].iloc[-5]
    
    if side == 'buy':
        if price_4h > price_4h_prev * 1.01 and rsi_4h < rsi_4h_prev - 5:  # 가격 1%+ 상승, RSI 5+ 하락
            reversal_score += 4  # 🔄 2.5 → 4
            signals.append("🔴 4h Bearish RSI Divergence (확실)")
    else:
        if price_4h < price_4h_prev * 0.99 and rsi_4h > rsi_4h_prev + 5:
            reversal_score += 4
            signals.append("🔴 4h Bullish RSI Divergence (확실)")
    
    # ========================================
    # === 트랩 필터: 4시간봉 추세 지지 시 점수 차감 ===
    # ========================================
    trend_support_deduction = 0
    if trend_support_4h >= 5:  # 강한 추세 지지
        trend_support_deduction = min(reversal_score * 0.4, 6)  # 최대 40% 또는 6점 차감
        signals.append(f"🛡️ 4h 추세 지지 강함 (-{trend_support_deduction:.1f}점)")
    elif trend_support_4h >= 3:  # 중간 추세 지지
        trend_support_deduction = min(reversal_score * 0.25, 4)  # 최대 25% 또는 4점 차감
        signals.append(f"🛡️ 4h 추세 지지 중 (-{trend_support_deduction:.1f}점)")
    
    reversal_score = max(0, reversal_score - trend_support_deduction)
    
    # ========================================
    # === 🆕 v7.6: RSI 과열 상태 인내심 로직 ===
    # ========================================
    try:
        rsi_4h = df_4h['rsi'].iloc[-1]
        rsi_1h = df_hourly['rsi'].iloc[-1]
        stoch_k_4h = df_4h.get('stoch_k', pd.Series([50])).iloc[-1] if 'stoch_k' in df_4h.columns else 50
        
        rsi_patience_deduction = 0
        rsi_patience_reasons = []
        
        if side == 'buy':
            # LONG 포지션: 과매도 상태이면 반등 기대 → exit 차감
            if rsi_4h < V76_RSI_EXTREME_OVERSOLD:
                rsi_patience_deduction += V76_EXTREME_PATIENCE_DEDUCTION
                rsi_patience_reasons.append(f"4H RSI={rsi_4h:.1f} 극단적 과매도")
            elif rsi_4h < V76_RSI_OVERSOLD:
                rsi_patience_deduction += V76_MODERATE_PATIENCE_DEDUCTION
                rsi_patience_reasons.append(f"4H RSI={rsi_4h:.1f} 과매도")
            
            if rsi_1h < V76_RSI_EXTREME_OVERSOLD:
                rsi_patience_deduction += 3
                rsi_patience_reasons.append(f"1H RSI={rsi_1h:.1f}")
            elif rsi_1h < V76_RSI_OVERSOLD:
                rsi_patience_deduction += 2
            
            if stoch_k_4h < V76_STOCH_EXTREME_OVERSOLD:
                rsi_patience_deduction += 2
                
        else:  # SHORT 포지션
            # SHORT 포지션: 과매수 상태이면 반락 기대 → exit 차감
            if rsi_4h > V76_RSI_EXTREME_OVERBOUGHT:
                rsi_patience_deduction += V76_EXTREME_PATIENCE_DEDUCTION
                rsi_patience_reasons.append(f"4H RSI={rsi_4h:.1f} 극단적 과매수")
            elif rsi_4h > V76_RSI_OVERBOUGHT:
                rsi_patience_deduction += V76_MODERATE_PATIENCE_DEDUCTION
                rsi_patience_reasons.append(f"4H RSI={rsi_4h:.1f} 과매수")
            
            if rsi_1h > V76_RSI_EXTREME_OVERBOUGHT:
                rsi_patience_deduction += 3
                rsi_patience_reasons.append(f"1H RSI={rsi_1h:.1f}")
            elif rsi_1h > V76_RSI_OVERBOUGHT:
                rsi_patience_deduction += 2
            
            if stoch_k_4h > V76_STOCH_EXTREME_OVERBOUGHT:
                rsi_patience_deduction += 2
        
        # RSI 과열 인내심 적용 (최대 10점 차감)
        if rsi_patience_deduction > 0:
            rsi_patience_deduction = min(rsi_patience_deduction, 10)
            reversal_score = max(0, reversal_score - rsi_patience_deduction)
            signals.append(f"🧘 v7.6 RSI 과열 인내심: -{rsi_patience_deduction}점 ({', '.join(rsi_patience_reasons[:2]) if rsi_patience_reasons else '과열'})")
            
    except Exception as e:
        pass  # RSI 과열 인내심은 선택적 기능
    
    # ========================================
    # === 멀티타임프레임 확인 보너스/페널티 ===
    # ========================================
    
    # 4시간봉 + 1시간봉 동시 역전 시 보너스
    if (macd_cross_4h or di_cross_4h) and (macd_cross_1h or di_cross_1h):
        reversal_score += 3
        signals.append("⚡ 4h+1h 멀티타임프레임 역전 확인!")
    
    # 15분봉만 역전이고 상위 타임프레임 지지 시 페널티
    if macd_cross_15m and not macd_cross_1h and not macd_cross_4h and trend_support_4h >= 3:
        reversal_score = max(0, reversal_score - 2)
        signals.append("🛡️ 15m 신호만 발생 - 상위 TF 미확인 (-2점)")
    
    # === 종합 판단 ===
    should_exit = False
    urgency = 'none'
    confidence = 0
    
    if reversal_score >= threshold_immediate:
        should_exit = True
        urgency = 'immediate'
        confidence = min(reversal_score / 18, 1.0)  # 🔄 12 → 18
    elif reversal_score >= threshold_soon:
        should_exit = False  # soon은 아직 홀드
        urgency = 'soon'
        confidence = reversal_score / 18
    elif reversal_score >= threshold_watch:
        should_exit = False
        urgency = 'watch'
        confidence = reversal_score / 18
    
    return {
        'should_exit': should_exit,
        'urgency': urgency,
        'confidence': confidence,
        'reversal_score': reversal_score,
        'signals': signals,
        'threshold_immediate': threshold_immediate,
        'threshold_soon': threshold_soon,
        'threshold_watch': threshold_watch,
        'trend_support_4h': trend_support_4h
    }

# 🆕 v7.5 강화된 detect_early_reversal_signals 함수 (트랩 필터)
def detect_early_reversal_signals(df_15min, df_hourly, df_4h, position_side, current_price, entry_price, pnl_percent=0, holding_minutes=0, peak_pnl=0):
    """
    🆕 v7.5 ENHANCED: 중장기 타임프레임 중심 추세 역전 감지 + Aggressive Profit Protection
    
    핵심 변경사항 (v7.5 ENHANCED):
    - Trailing profit protection 통합 (고수익 구간 보호)
    - 1H 신호 가중치 증가 (peak profit 비례)
    - 4H trend support 차감 상한 강화
    - Peak profit 기반 동적 임계값
    
    Args:
        pnl_percent: 현재 수익률 (레버리지 적용)
        holding_minutes: 보유 시간 (분)
        peak_pnl: 최고 수익률 (🆕 추가)
    
    Returns:
        dict: 역전 신호 분석 결과
    """
    signals = []
    reversal_score = 0
    trailing_exit = {'should_exit': False, 'reason': '', 'confidence': 0.0}
    
    # ========================================
    # === 0. 4시간봉 추세 지지 확인 (선행 체크) ===
    # ========================================
    trend_support_4h = 0
    di_plus_4h = df_4h['di_plus'].iloc[-1]
    di_minus_4h = df_4h['di_minus'].iloc[-1]
    adx_4h = df_4h['adx'].iloc[-1]
    macd_4h = df_4h['macd'].iloc[-1]
    macd_signal_4h = df_4h['macd_signal'].iloc[-1]
    
    if position_side == 'buy':
        if di_plus_4h > di_minus_4h:
            trend_support_4h += 2
        if macd_4h > macd_signal_4h:
            trend_support_4h += 2
        if adx_4h > 20:
            trend_support_4h += 1
        if df_4h['close'].iloc[-1] > df_4h['sma_20'].iloc[-1]:
            trend_support_4h += 2
        if df_4h['rsi'].iloc[-1] > 45 and df_4h['rsi'].iloc[-1] < 70:
            trend_support_4h += 1  # RSI 건강한 구간
    else:
        if di_minus_4h > di_plus_4h:
            trend_support_4h += 2
        if macd_4h < macd_signal_4h:
            trend_support_4h += 2
        if adx_4h > 20:
            trend_support_4h += 1
        if df_4h['close'].iloc[-1] < df_4h['sma_20'].iloc[-1]:
            trend_support_4h += 2
        if df_4h['rsi'].iloc[-1] < 55 and df_4h['rsi'].iloc[-1] > 30:
            trend_support_4h += 1
    
    # ========================================
    # === 🆕 v7.5: Trailing Profit Protection 체크 ===
    # ========================================
    if peak_pnl >= 5.0:
        trailing_exit = should_force_exit_by_trailing_protection(
            peak_pnl, pnl_percent, holding_minutes, trend_support_4h
        )
        if trailing_exit['should_exit']:
            signals.append(trailing_exit['reason'])
            reversal_score += 10  # 높은 점수로 exit 유도
    
    # 🆕 v7.5: 1H 신호 가중치 계산 (peak profit 비례)
    hourly_weight_multiplier = 1.0
    if peak_pnl >= 30.0:
        hourly_weight_multiplier = 1.5
        signals.append("📈 High profit mode: 1H signals weighted 1.5x")
    elif peak_pnl >= 15.0:
        hourly_weight_multiplier = 1.3
    
    # ===== 1. 지지부진/시간 기반 판단 (60분 보호 이후에만 적용) =====
    profit_risk = {
        'is_stagnant': False,
        'is_declining': False,
        'time_inefficiency': False
    }
    
    # v7.5: 시간 기반 점수는 60분 이후에만 적용
    if holding_minutes >= 60:
        # 지지부진 포지션 감지 (수익률 기준 완화)
        if holding_minutes >= 90 and abs(pnl_percent) < 0.8:
            signals.append(f"⏰ 지지부진 포지션 ({holding_minutes:.0f}분 보유, {pnl_percent:+.2f}%)")
            reversal_score += 2  # 🔄 3 → 2 (점수 감소)
            profit_risk['is_stagnant'] = True
        
        # 오래 보유한데 수익이 미미한 경우 (기준 완화)
        if holding_minutes >= 120 and abs(pnl_percent) < 1.2:
            signals.append(f"⚠️ 장시간 미미한 수익 ({holding_minutes:.0f}분, {pnl_percent:+.2f}%)")
            reversal_score += 2  # 🔄 2 유지
            profit_risk['time_inefficiency'] = True
        
        # 3시간 이상 보유 시 더 엄격한 기준
        if holding_minutes >= 180 and pnl_percent < 1.5:
            signals.append(f"🔴 3시간+ 보유 저성과 ({pnl_percent:+.2f}%)")
            reversal_score += 3
    
    # ========================================
    # === 2. 4시간봉 신호 (가장 중요, 높은 점수) ===
    # ========================================
    
    try:
        # 4시간봉 MACD 크로스오버 (가장 강력한 역전 신호)
        macd_cross_4h = False
        if position_side == 'buy':
            if macd_4h < macd_signal_4h and df_4h['macd'].iloc[-2] >= df_4h['macd_signal'].iloc[-2]:
                macd_cross_4h = True
                signals.append("🔴🔴🔴 4h MACD 데드크로스! (중대 역전)")
                reversal_score += 8
        else:
            if macd_4h > macd_signal_4h and df_4h['macd'].iloc[-2] <= df_4h['macd_signal'].iloc[-2]:
                macd_cross_4h = True
                signals.append("🔴🔴🔴 4h MACD 골든크로스! (중대 역전)")
                reversal_score += 8
        
        # 4시간봉 DI 크로스오버
        di_cross_4h = False
        if position_side == 'buy':
            if di_minus_4h > di_plus_4h and df_4h['di_minus'].iloc[-2] <= df_4h['di_plus'].iloc[-2]:
                di_cross_4h = True
                signals.append("🔴🔴 4h DI- > DI+ 크로스오버")
                reversal_score += 6
        else:
            if di_plus_4h > di_minus_4h and df_4h['di_plus'].iloc[-2] <= df_4h['di_minus'].iloc[-2]:
                di_cross_4h = True
                signals.append("🔴🔴 4h DI+ > DI- 크로스오버")
                reversal_score += 6
        
        # 4시간봉 SMA20 이탈 (연속 2캔들)
        sma20_break_4h = False
        if position_side == 'buy':
            if df_4h['close'].iloc[-1] < df_4h['sma_20'].iloc[-1] and \
               df_4h['close'].iloc[-2] < df_4h['sma_20'].iloc[-2]:
                sma20_break_4h = True
                signals.append("🔴🔴 4h SMA20 하향 이탈 확인 (2캔들)")
                reversal_score += 5
        else:
            if df_4h['close'].iloc[-1] > df_4h['sma_20'].iloc[-1] and \
               df_4h['close'].iloc[-2] > df_4h['sma_20'].iloc[-2]:
                sma20_break_4h = True
                signals.append("🔴🔴 4h SMA20 상향 돌파 확인 (2캔들)")
                reversal_score += 5
        
        # 4시간봉 RSI 다이버전스 (연속 5캔들 비교)
        rsi_4h_curr = df_4h['rsi'].iloc[-1]
        rsi_4h_prev = df_4h['rsi'].iloc[-5]
        price_4h_curr = df_4h['close'].iloc[-1]
        price_4h_prev = df_4h['close'].iloc[-5]
        
        if position_side == 'buy':
            if price_4h_curr > price_4h_prev * 1.01 and rsi_4h_curr < rsi_4h_prev - 5:
                signals.append("🔴 4h Bearish RSI Divergence (확실)")
                reversal_score += 4
        else:
            if price_4h_curr < price_4h_prev * 0.99 and rsi_4h_curr > rsi_4h_prev + 5:
                signals.append("🔴 4h Bullish RSI Divergence (확실)")
                reversal_score += 4
                
    except Exception as e:
        logger.debug(f"4h 분석 오류: {e}")
    
    # ========================================
    # === 3. 1시간봉 신호 (중요, 중간 점수) ===
    # ========================================
    
    try:
        macd_1h = df_hourly['macd'].iloc[-1]
        macd_signal_1h = df_hourly['macd_signal'].iloc[-1]
        
        # 1시간봉 MACD 크로스오버 (🆕 v7.5: 가중치 적용)
        macd_cross_1h = False
        base_score_1h_macd = 4
        if position_side == 'buy':
            if macd_1h < macd_signal_1h and df_hourly['macd'].iloc[-2] >= df_hourly['macd_signal'].iloc[-2]:
                macd_cross_1h = True
                signals.append("🔴 1h MACD 데드크로스")
                reversal_score += int(base_score_1h_macd * hourly_weight_multiplier)
        else:
            if macd_1h > macd_signal_1h and df_hourly['macd'].iloc[-2] <= df_hourly['macd_signal'].iloc[-2]:
                macd_cross_1h = True
                signals.append("🔴 1h MACD 골든크로스")
                reversal_score += int(base_score_1h_macd * hourly_weight_multiplier)
        
        # 1시간봉 DI 크로스오버 (연속 2캔들 확인) (🆕 v7.5: 가중치 적용)
        di_cross_1h = False
        di_plus_1h = df_hourly['di_plus'].iloc[-1]
        di_minus_1h = df_hourly['di_minus'].iloc[-1]
        base_score_1h_di = 5
        
        if position_side == 'buy':
            if di_minus_1h > di_plus_1h and \
               df_hourly['di_minus'].iloc[-2] > df_hourly['di_plus'].iloc[-2] and \
               df_hourly['di_minus'].iloc[-3] <= df_hourly['di_plus'].iloc[-3]:
                di_cross_1h = True
                signals.append("🔴 1h DI- > DI+ (2캔들 확인)")
                reversal_score += int(base_score_1h_di * hourly_weight_multiplier)
            elif di_minus_1h > di_plus_1h and df_hourly['di_minus'].iloc[-2] <= df_hourly['di_plus'].iloc[-2]:
                signals.append("⚠️ 1h DI crossover (확인 필요)")
                reversal_score += 2
        else:
            if di_plus_1h > di_minus_1h and \
               df_hourly['di_plus'].iloc[-2] > df_hourly['di_minus'].iloc[-2] and \
               df_hourly['di_plus'].iloc[-3] <= df_hourly['di_minus'].iloc[-3]:
                di_cross_1h = True
                signals.append("🔴 1h DI+ > DI- (2캔들 확인)")
                reversal_score += int(base_score_1h_di * hourly_weight_multiplier)
            elif di_plus_1h > di_minus_1h and df_hourly['di_plus'].iloc[-2] <= df_hourly['di_minus'].iloc[-2]:
                signals.append("⚠️ 1h DI crossover (확인 필요)")
                reversal_score += 2
        
        # 1시간봉 ADX 연속 하락
        adx_1h = df_hourly['adx'].iloc[-1]
        adx_1h_prev = df_hourly['adx'].iloc[-2]
        adx_1h_prev2 = df_hourly['adx'].iloc[-3]
        
        if adx_1h < adx_1h_prev < adx_1h_prev2 and adx_1h < 20:
            signals.append("📉 1h ADX 연속 하락 (추세 약화)")
            reversal_score += 3
        
        # 1시간봉 CMF 연속 음수/양수
        cmf_1h = df_hourly['cmf'].iloc[-1]
        cmf_1h_prev = df_hourly['cmf'].iloc[-2]
        
        if position_side == 'buy':
            if cmf_1h < -0.1 and cmf_1h_prev < -0.05:
                signals.append("🔴 1h CMF 연속 자금유출")
                reversal_score += 3
        else:
            if cmf_1h > 0.1 and cmf_1h_prev > 0.05:
                signals.append("🔴 1h CMF 연속 자금유입")
                reversal_score += 3
                
    except Exception as e:
        logger.debug(f"1h 분석 오류: {e}")
    
    # ========================================
    # === 4. 15분봉 신호 (참고용, 낮은 점수) ===
    # ========================================
    
    try:
        # 15분봉 MACD (참고용)
        macd_cross_15m = False
        if position_side == 'buy':
            if df_15min['macd'].iloc[-1] < df_15min['macd_signal'].iloc[-1] and \
               df_15min['macd'].iloc[-2] >= df_15min['macd_signal'].iloc[-2]:
                macd_cross_15m = True
                reversal_score += 1  # 🔄 4 → 1 (대폭 감소)
                signals.append("📉 15m MACD crossover (참고)")
        else:
            if df_15min['macd'].iloc[-1] > df_15min['macd_signal'].iloc[-1] and \
               df_15min['macd'].iloc[-2] <= df_15min['macd_signal'].iloc[-2]:
                macd_cross_15m = True
                reversal_score += 1
                signals.append("📈 15m MACD crossover (참고)")
        
        # 15분봉 RSI 과열권 탈출 (참고용)
        rsi_15m = df_15min['rsi'].iloc[-1]
        rsi_15m_prev = df_15min['rsi'].iloc[-3]  # 3개 전과 비교
        
        if position_side == 'buy':
            if rsi_15m < 60 and rsi_15m_prev > 70:
                reversal_score += 1  # 🔄 3 → 1
                signals.append("📉 15m RSI 과매수권 탈출 (참고)")
        else:
            if rsi_15m > 40 and rsi_15m_prev < 30:
                reversal_score += 1
                signals.append("📈 15m RSI 과매도권 탈출 (참고)")
        
        # 15분봉 다이버전스는 점수 부여하지 않음 (참고만)
        recent_prices_15m = df_15min['close'].tail(10).values
        recent_rsi_15m = df_15min['rsi'].tail(10).values
        
        if position_side == 'buy':
            if recent_prices_15m[-1] > recent_prices_15m[-5] and recent_rsi_15m[-1] < recent_rsi_15m[-5]:
                signals.append("📉 15m Divergence 감지 (참고, 점수 없음)")
        else:
            if recent_prices_15m[-1] < recent_prices_15m[-5] and recent_rsi_15m[-1] > recent_rsi_15m[-5]:
                signals.append("📈 15m Divergence 감지 (참고, 점수 없음)")
                
    except Exception as e:
        logger.debug(f"15m 분석 오류: {e}")
    
    # ========================================
    # === 5. 트랩 필터: 추세 지지 시 점수 차감 (🆕 v7.5 ENHANCED) ===
    # ========================================
    
    trend_support_deduction = 0
    
    # 🆕 v7.5 ENHANCED: peak_pnl 기반 차감 상한 (더 공격적)
    max_deduction_allowed = 8  # 기본 최대 차감
    
    if peak_pnl >= 50.0:
        max_deduction_allowed = 1  # 초고수익: 거의 차감 안함
        signals.append(f"🛡️ 초고수익 보호(Peak {peak_pnl:.0f}%): 최대 차감 {max_deduction_allowed}점")
    elif peak_pnl >= 30.0:
        max_deduction_allowed = 2
        signals.append(f"🛡️ 고수익 보호(Peak {peak_pnl:.0f}%): 최대 차감 {max_deduction_allowed}점")
    elif peak_pnl >= 15.0:
        max_deduction_allowed = 3
        signals.append(f"🛡️ 중수익 보호(Peak {peak_pnl:.0f}%): 최대 차감 {max_deduction_allowed}점")
    elif peak_pnl >= 5.0:
        max_deduction_allowed = 4
    elif pnl_percent > 5.0:  # 현재 수익도 고려 (기존 로직 유지)
        max_deduction_allowed = 4
    elif pnl_percent > 3.0:
        max_deduction_allowed = 6
    
    # 4시간봉 추세가 강하게 지지하면 점수 차감 (상한 적용)
    if trend_support_4h >= 6:
        trend_support_deduction = min(reversal_score * 0.5, max_deduction_allowed)
        signals.append(f"🛡️ 4h 추세 매우 강함 (-{trend_support_deduction:.1f}점)")
    elif trend_support_4h >= 4:
        trend_support_deduction = min(reversal_score * 0.35, max_deduction_allowed)
        signals.append(f"🛡️ 4h 추세 강함 (-{trend_support_deduction:.1f}점)")
    elif trend_support_4h >= 3:
        trend_support_deduction = min(reversal_score * 0.2, max_deduction_allowed)
        signals.append(f"🛡️ 4h 추세 지지 중 (-{trend_support_deduction:.1f}점)")
    
    # 🆕 v7.5: 고수익 + 장기보유 시 차감 더 제한
    if holding_minutes >= 90 and peak_pnl >= 20.0:
        max_time_deduction = 2
        if trend_support_deduction > max_time_deduction:
            reduction = trend_support_deduction - max_time_deduction
            trend_support_deduction = max_time_deduction
            signals.append(f"⏰ 장기 고수익 보호: 차감 {reduction:.1f}점 추가 감소")
    elif holding_minutes >= 120 and pnl_percent > 2.0:
        max_deduction_for_time = 3
        if trend_support_deduction > max_deduction_for_time:
            reduction = trend_support_deduction - max_deduction_for_time
            trend_support_deduction = max_deduction_for_time
            signals.append(f"⏰ 장기 보유 수익 보호: 차감 {reduction:.1f}점 감소")
    
    # 수익 구간 추가 차감은 peak이 낮을 때만
    if pnl_percent > 2.0 and peak_pnl < 10.0 and trend_support_4h >= 3 and holding_minutes < 90:
        extra_deduction = 2
        trend_support_deduction += extra_deduction
        signals.append(f"🛡️ 저수익 구간 + 추세 지지 (-{extra_deduction}점)")
    
    reversal_score = max(0, reversal_score - trend_support_deduction)
    
    # ========================================
    # === 6. 멀티타임프레임 확인 보너스/페널티 ===
    # ========================================
    
    # 4시간봉 + 1시간봉 동시 역전 시 보너스
    has_4h_signal = any('4h' in sig for sig in signals if '🔴🔴' in sig)
    has_1h_signal = any('1h' in sig and '🔴' in sig for sig in signals)
    
    if has_4h_signal and has_1h_signal:
        reversal_score += 4
        signals.append("⚡ 4h+1h 멀티타임프레임 역전 확인! (+4점)")
    
    # 15분봉만 있고 상위 TF 미확인 시 페널티
    has_15m_signal = any('15m' in sig for sig in signals)
    if has_15m_signal and not has_1h_signal and not has_4h_signal and trend_support_4h >= 3:
        reversal_score = max(0, reversal_score - 3)
        signals.append("🛡️ 15m 신호만 발생 - 상위 TF 미확인 (-3점)")
    
    # ========================================
    # === 🆕 7. v7.6 참고: 시간+수익 기반 조건 ===
    # ========================================
    # NOTE: peak_pnl 정보는 이 함수 외부에서 관리됨
    # 실제 시간+수익 조합 조건은 메인 모니터링 함수에서 처리
    # 여기서는 holding_minutes + pnl_percent만으로 간단한 보조 판단
    
    time_profit_exit = False
    time_profit_urgency = 'none'
    
    # 🆕 v7.4: 장기 보유 + 손실 전환 감지 (조건 완화)
    # 조건: 150분+ 보유 + 손실 -5% 이상 + 4H 추세 약화
    if holding_minutes >= 150 and pnl_percent < -5.0 and trend_support_4h < 5:
        time_profit_exit = True
        time_profit_urgency = 'soon'
        reversal_score = max(reversal_score, 9)
        signals.append(f"⚠️ v7.4 장기 보유 손실: {holding_minutes:.0f}분 보유, {pnl_percent:+.2f}%, 4H 추세 약화")
    
    # 조건: 240분+ 보유 + 수익 미미 (2% 미만) + 4H 추세 약화
    if holding_minutes >= 240 and pnl_percent < 2.0 and trend_support_4h < 5:
        time_profit_urgency = 'watch'
        reversal_score = max(reversal_score, 6)
        signals.append(f"⏰ v7.4 장기 보유 저성과: {holding_minutes:.0f}분 보유, {pnl_percent:+.2f}%")
    
    # ===== 최종 판단 (v7.5 임계값 상향) =====
    should_exit = False
    urgency = 'none'
    confidence = 0.0
    
    # 🆕 v7.8: 보수적 초반 보호 - 성급한 종료 방지
    # 경미한 손실(-5% 이상)에서는 강한 보호 유지
    if holding_minutes < V78_EARLY_PROTECTION_MINUTES:  # 60분 미만
        # 초반 보호 기간 - 매우 보수적
        if pnl_percent >= 0:  # 수익 중이면 최강 보호
            threshold_immediate = V78_STRICT_THRESHOLD_IMMEDIATE  # 20
            threshold_soon = V78_STRICT_THRESHOLD_SOON            # 16
            threshold_watch = V78_STRICT_THRESHOLD_WATCH          # 12
            signals.append(f"🛡️ v7.8 초반 수익 보호 (<60분): 임계값 최대 상향")
        elif pnl_percent >= V78_MIN_LOSS_FOR_EXIT:  # -5% 이상이면 강한 보호
            threshold_immediate = 18
            threshold_soon = 14
            threshold_watch = 10
            signals.append(f"🛡️ v7.8 초반 경미손실 보호 (<60분, {pnl_percent:.1f}%): 강한 보호")
        elif pnl_percent >= -10.0:  # -5% ~ -10% 중간 보호
            threshold_immediate = 15
            threshold_soon = 12
            threshold_watch = 8
            signals.append(f"⚠️ v7.8 초반 중간손실 (<60분, {pnl_percent:.1f}%): 중간 보호")
        else:  # -10% 이하 심각 손실
            threshold_immediate = 12
            threshold_soon = 9
            threshold_watch = 6
            signals.append(f"🚨 초반 심각손실 (<60분, {pnl_percent:.1f}%): 보호 해제")
    elif holding_minutes < V78_MID_PROTECTION_MINUTES:  # 60-90분
        # 중간 보호 기간
        if pnl_percent >= 0:
            threshold_immediate = 16
            threshold_soon = 13
            threshold_watch = 9
            signals.append(f"🛡️ v7.8 중간 수익 보호 (60-90분)")
        elif pnl_percent >= V78_MIN_LOSS_FOR_EXIT:  # -5% 이상
            threshold_immediate = 14
            threshold_soon = 11
            threshold_watch = 8
            signals.append(f"🛡️ v7.8 중간 경미손실 보호 (60-90분, {pnl_percent:.1f}%)")
        else:
            threshold_immediate = 12
            threshold_soon = 9
            threshold_watch = 6
    else:
        # 정상 모니터링 (90분+)
        threshold_immediate = 12
        threshold_soon = 9
        threshold_watch = 6
    
    # 🆕 v7.8: 초반에 수익/경미손실이면 추가 점수 차감 (더 보수적)
    early_protection_deduction = 0
    if holding_minutes < V78_EARLY_PROTECTION_MINUTES:  # 60분 미만
        if pnl_percent > 0:
            # 초반 + 수익 중 = 최대 인내심
            early_protection_deduction = 6  # 기존 4 → 6
            reversal_score = max(0, reversal_score - early_protection_deduction)
            signals.append(f"🛡️ v7.8 초반 수익 보호: -{early_protection_deduction}점 (강한 인내심)")
        elif pnl_percent >= V78_MIN_LOSS_FOR_EXIT:  # -5% 이상
            # 경미한 손실도 인내심 부여
            early_protection_deduction = 4
            reversal_score = max(0, reversal_score - early_protection_deduction)
            signals.append(f"🛡️ v7.8 초반 경미손실 인내: -{early_protection_deduction}점")
    elif holding_minutes < V78_MID_PROTECTION_MINUTES:  # 60-90분
        if pnl_percent > 0:
            early_protection_deduction = 3
            reversal_score = max(0, reversal_score - early_protection_deduction)
            signals.append(f"🛡️ v7.8 중간 수익 보호: -{early_protection_deduction}점")
        elif pnl_percent >= V78_MIN_LOSS_FOR_EXIT:
            early_protection_deduction = 2
            reversal_score = max(0, reversal_score - early_protection_deduction)
            signals.append(f"🛡️ v7.8 중간 경미손실 인내: -{early_protection_deduction}점")
    
    # ========================================
    # === 🆕 v7.6: RSI 과열 상태 인내심 로직 ===
    # ========================================
    # RSI가 극단적 과매수/과매도 상태이면 곧 반등/반락할 가능성이 높음
    # 이 상태에서 성급하게 exit하면 수익 기회를 놓침
    try:
        rsi_4h = df_4h['rsi'].iloc[-1]
        rsi_1h = df_hourly['rsi'].iloc[-1]
        rsi_15m = df_15min['rsi'].iloc[-1]
        stoch_k_4h = df_4h.get('stoch_k', pd.Series([50])).iloc[-1] if 'stoch_k' in df_4h.columns else 50
        stoch_k_1h = df_hourly.get('stoch_k', pd.Series([50])).iloc[-1] if 'stoch_k' in df_hourly.columns else 50
        
        rsi_patience_deduction = 0
        rsi_patience_reasons = []
        
        if position_side == 'buy':
            # LONG 포지션: 과매도 상태이면 반등 기대 → exit 차감
            # (현재 손실 중이더라도 반등 가능성 고려)
            
            # 극단적 과매도 (RSI < 20) - 강한 반등 기대
            if rsi_4h < V76_RSI_EXTREME_OVERSOLD:
                rsi_patience_deduction += V76_EXTREME_PATIENCE_DEDUCTION
                rsi_patience_reasons.append(f"4H RSI={rsi_4h:.1f} 극단적 과매도")
            elif rsi_4h < V76_RSI_OVERSOLD:
                rsi_patience_deduction += V76_MODERATE_PATIENCE_DEDUCTION
                rsi_patience_reasons.append(f"4H RSI={rsi_4h:.1f} 과매도")
            
            if rsi_1h < V76_RSI_EXTREME_OVERSOLD:
                rsi_patience_deduction += 3
                rsi_patience_reasons.append(f"1H RSI={rsi_1h:.1f} 극단적 과매도")
            elif rsi_1h < V76_RSI_OVERSOLD:
                rsi_patience_deduction += 2
                rsi_patience_reasons.append(f"1H RSI={rsi_1h:.1f} 과매도")
            
            # Stochastic 과매도 확인
            if stoch_k_4h < V76_STOCH_EXTREME_OVERSOLD:
                rsi_patience_deduction += 2
                rsi_patience_reasons.append(f"4H Stoch={stoch_k_4h:.1f} 극단적 과매도")
                
        else:  # SHORT 포지션
            # SHORT 포지션: 과매수 상태이면 반락 기대 → exit 차감
            
            # 극단적 과매수 (RSI > 80) - 강한 반락 기대
            if rsi_4h > V76_RSI_EXTREME_OVERBOUGHT:
                rsi_patience_deduction += V76_EXTREME_PATIENCE_DEDUCTION
                rsi_patience_reasons.append(f"4H RSI={rsi_4h:.1f} 극단적 과매수")
            elif rsi_4h > V76_RSI_OVERBOUGHT:
                rsi_patience_deduction += V76_MODERATE_PATIENCE_DEDUCTION
                rsi_patience_reasons.append(f"4H RSI={rsi_4h:.1f} 과매수")
            
            if rsi_1h > V76_RSI_EXTREME_OVERBOUGHT:
                rsi_patience_deduction += 3
                rsi_patience_reasons.append(f"1H RSI={rsi_1h:.1f} 극단적 과매수")
            elif rsi_1h > V76_RSI_OVERBOUGHT:
                rsi_patience_deduction += 2
                rsi_patience_reasons.append(f"1H RSI={rsi_1h:.1f} 과매수")
            
            # Stochastic 과매수 확인
            if stoch_k_4h > V76_STOCH_EXTREME_OVERBOUGHT:
                rsi_patience_deduction += 2
                rsi_patience_reasons.append(f"4H Stoch={stoch_k_4h:.1f} 극단적 과매수")
        
        # RSI 과열 인내심 적용 (최대 10점 차감으로 제한)
        # 🆕 v7.8: 경미한 손실(-5% 이상)에서도 인내심 적용
        if rsi_patience_deduction > 0:
            if pnl_percent > 0:  # 수익 중
                rsi_patience_deduction = min(rsi_patience_deduction, 10)
                reversal_score = max(0, reversal_score - rsi_patience_deduction)
                signals.append(f"🧘 v7.6 RSI 과열 인내심: -{rsi_patience_deduction}점 ({', '.join(rsi_patience_reasons[:2])})")
            elif pnl_percent >= V78_MIN_LOSS_FOR_EXIT:  # -5% 이상 경미한 손실
                # v7.8: 경미한 손실에서도 50% 인내심 적용
                reduced_deduction = rsi_patience_deduction // 2
                if reduced_deduction > 0:
                    reversal_score = max(0, reversal_score - reduced_deduction)
                    signals.append(f"🧘 v7.8 경미손실 RSI 인내심: -{reduced_deduction}점 (반등 기대)")
            else:
                signals.append(f"⚠️ RSI 과열 but 심각 손실 → 인내심 미적용")
            
    except Exception as e:
        logger.debug(f"RSI 과열 인내심 계산 오류: {e}")
    
    # ========================================
    # === 🆕 v7.7 → v7.8: 손실 가속 청산 로직 (보수적 조정) ===
    # ========================================
    # v7.8: 초반 보호 기간에는 손실 가속 미적용
    loss_acceleration_bonus = 0
    
    # 초반 보호 기간이면 손실 가속 미적용
    if holding_minutes >= V78_EARLY_PROTECTION_MINUTES:  # 60분 이상일 때만
        if pnl_percent <= V77_LOSS_ACCELERATION_THRESHOLD:  # -8% 이하
            # 손실 가속 모드 진입
            loss_severity = abs(pnl_percent) / abs(V77_LOSS_ACCELERATION_THRESHOLD)  # 1.0 ~ 3.0+
            loss_acceleration_bonus = int(min(loss_severity * 3, 8))  # 최대 +8점
            reversal_score += loss_acceleration_bonus
            signals.append(f"🚨 v7.7 손실 가속: +{loss_acceleration_bonus}점 (PnL: {pnl_percent:.1f}%)")
            
            # 임계값도 낮춤 (더 쉽게 exit)
            threshold_immediate = max(8, threshold_immediate - 4)
            threshold_soon = max(6, threshold_soon - 3)
            signals.append(f"⚡ 임계값 하향: 즉시={threshold_immediate}, 곧={threshold_soon}")
    else:
        if pnl_percent <= V77_LOSS_ACCELERATION_THRESHOLD:
            signals.append(f"🛡️ v7.8 초반 보호: 손실 가속 미적용 ({holding_minutes:.0f}분, {pnl_percent:.1f}%)")
    
    # 심각/재앙적 손실은 시간과 무관하게 적용
    if pnl_percent <= V77_LOSS_CRITICAL_THRESHOLD:  # -15% 이하
        # 심각한 손실 - 강제 청산 모드
        reversal_score = max(reversal_score, 15)  # 최소 15점으로 상향
        threshold_immediate = 10  # 임계값 대폭 하향
        signals.append(f"🔴 v7.7 CRITICAL LOSS: 강제 청산 모드 ({pnl_percent:.1f}%)")
    
    if pnl_percent <= V77_LOSS_CATASTROPHIC_THRESHOLD:  # -25% 이하
        # 재앙적 손실 - 무조건 청산
        reversal_score = 20  # 최대 점수
        threshold_immediate = 5
        signals.append(f"💀 v7.7 CATASTROPHIC: 즉시 청산 필요! ({pnl_percent:.1f}%)")
    
    # 🆕 v7.5: Trailing Protection이 강제 종료를 요청하면 점수 강제 상향
    # 단, 초반 보호 기간에는 peak_pnl이 매우 높을 때만 적용
    if trailing_exit['should_exit']:
        if holding_minutes >= 45 or peak_pnl >= 20.0:  # 45분 이상 또는 peak 20%+
            reversal_score = max(reversal_score, 12)
            signals.append(f"🚨 Trailing Protection 강제: 점수 {reversal_score}점으로 상향")
        else:
            signals.append(f"🛡️ Trailing Protection 보류: 초반 보호 기간 (<45분)")
    
    if reversal_score >= threshold_immediate:
        should_exit = True
        urgency = 'immediate'
        confidence = min(reversal_score / 20, 1.0)
    elif reversal_score >= threshold_soon:
        should_exit = True
        urgency = 'soon'
        confidence = reversal_score / 20
    elif reversal_score >= threshold_watch:
        urgency = 'watch'
        confidence = reversal_score / 20
    
    return {
        'should_exit': should_exit,
        'urgency': urgency,
        'confidence': confidence,
        'reversal_score': reversal_score,
        'signals': signals,
        'profit_risk': profit_risk,
        'threshold_immediate': threshold_immediate,
        'threshold_soon': threshold_soon,
        'threshold_watch': threshold_watch,
        'trend_support_4h': trend_support_4h,
        'trailing_exit': trailing_exit  # 🆕 추가
    }

# ============ AI Response Helper ============
def extract_ai_response(response):
    """
    DeepSeek Reasoner 응답에서 content 추출
    reasoning_content와 content를 모두 확인
    """
    try:
        message = response.choices[0].message
        
        # 응답 구조 로깅
        logger.debug(f"응답 구조: {dir(message)}")
        
        # content 확인
        content = getattr(message, 'content', None)
        if content and content.strip():
            logger.info(f"Content 응답 길이: {len(content)} 문자")
            return content
        
        # reasoning_content 확인 (DeepSeek Reasoner 특수 필드)
        reasoning_content = getattr(message, 'reasoning_content', None)
        if reasoning_content and reasoning_content.strip():
            logger.info(f"Reasoning content 응답 길이: {len(reasoning_content)} 문자")
            logger.warning("Content가 비어있어 reasoning_content 사용")
            return reasoning_content
        
        # 둘 다 없으면 전체 응답 로깅
        logger.error(f"응답이 비어있음. Message 객체: {message}")
        logger.error(f"전체 response: {response}")
        return None
        
    except Exception as e:
        logger.error(f"AI 응답 추출 중 오류: {str(e)}")
        logger.error(f"전체 response: {response}")
        return None

# ============ Market Data Collection ============
def get_market_data(symbol):
    """특정 심볼의 시장 데이터를 수집"""
    try:
        # 현재가격
        ticker = exchange.fetch_ticker(symbol)
        current_price = ticker['last']
        
        # 오더북 데이터
        orderbook = exchange.fetch_order_book(symbol, limit=10)
        
        # 5분봉 데이터 (더 많이 가져오기 - ATR 계산 위해)
        df_15min = pd.DataFrame(
            exchange.fetch_ohlcv(symbol, timeframe='15m', limit=150),  # 15분봉으로 변경
            columns=['timestamp', 'open', 'high', 'low', 'close', 'volume']
        )
        df_15min['timestamp'] = pd.to_datetime(df_15min['timestamp'], unit='ms').dt.tz_localize('UTC').dt.tz_convert('Asia/Seoul')
        df_15min = df_15min.set_index('timestamp')
        df_15min = df_15min.dropna()  # dropna(df) → df.dropna() 수정
        df_15min = add_indicators(df_15min)
        
        # ATR NaN 처리 (tail 전에 수행)
        if 'atr' in df_15min.columns:
            df_15min['atr'] = df_15min['atr'].fillna(method='bfill')
            if df_15min['atr'].isna().any():
                # 대체값: high-low 평균
                default_atr = (df_15min['high'] - df_15min['low']).rolling(14).mean().iloc[-1]
                if pd.isna(default_atr) or default_atr == 0:
                    default_atr = current_price * 0.002  # 가격의 0.2%
                df_15min['atr'] = df_15min['atr'].fillna(default_atr)
            # ATR이 0인 경우 처리
            df_15min.loc[df_15min['atr'] == 0, 'atr'] = current_price * 0.002
        
        df_15min = df_15min.tail(60)
        
        # 1시간봉 데이터 (더 많이 가져오기)
        df_hourly = pd.DataFrame(
            exchange.fetch_ohlcv(symbol, timeframe='1h', limit=100),  # 57 → 100
            columns=['timestamp', 'open', 'high', 'low', 'close', 'volume']
        )
        df_hourly['timestamp'] = pd.to_datetime(df_hourly['timestamp'], unit='ms').dt.tz_localize('UTC').dt.tz_convert('Asia/Seoul')
        df_hourly = df_hourly.set_index('timestamp')
        df_hourly = df_hourly.dropna()  # dropna(df) → df.dropna()
        df_hourly = add_indicators(df_hourly)
        
        # ATR NaN 처리
        if 'atr' in df_hourly.columns:
            df_hourly['atr'] = df_hourly['atr'].fillna(method='bfill')
            if df_hourly['atr'].isna().any():
                default_atr = (df_hourly['high'] - df_hourly['low']).rolling(14).mean().iloc[-1]
                if pd.isna(default_atr) or default_atr == 0:
                    default_atr = current_price * 0.003
                df_hourly['atr'] = df_hourly['atr'].fillna(default_atr)
            df_hourly.loc[df_hourly['atr'] == 0, 'atr'] = current_price * 0.003
        
        df_hourly = df_hourly.tail(24)
        
        # 4시간봉 데이터 (더 많이 가져오기)
        df_4h = pd.DataFrame(
            exchange.fetch_ohlcv(symbol, timeframe='4h', limit=100),  # 51 → 100
            columns=['timestamp', 'open', 'high', 'low', 'close', 'volume']
        )
        df_4h['timestamp'] = pd.to_datetime(df_4h['timestamp'], unit='ms').dt.tz_localize('UTC').dt.tz_convert('Asia/Seoul')
        df_4h = df_4h.set_index('timestamp')
        df_4h = df_4h.dropna()  # dropna(df) → df.dropna()
        df_4h = add_indicators(df_4h)
        
        # ATR NaN 처리
        if 'atr' in df_4h.columns:
            df_4h['atr'] = df_4h['atr'].fillna(method='bfill')
            if df_4h['atr'].isna().any():
                default_atr = (df_4h['high'] - df_4h['low']).rolling(14).mean().iloc[-1]
                if pd.isna(default_atr) or default_atr == 0:
                    default_atr = current_price * 0.005
                df_4h['atr'] = df_4h['atr'].fillna(default_atr)
            df_4h.loc[df_4h['atr'] == 0, 'atr'] = current_price * 0.005
        
        df_4h = df_4h.tail(18)
        
        # 공포 탐욕 지수 (BTC만 해당)
        fear_greed_index = None
        if 'BTC' in symbol:
            fear_greed_index = get_fear_and_greed_index()
        
        # ATR 값 로깅 (디버깅용)
        try:
            atr_15m = df_15min['atr'].iloc[-1] if 'atr' in df_15min.columns else 0
            atr_1h = df_hourly['atr'].iloc[-1] if 'atr' in df_hourly.columns else 0
            atr_4h = df_4h['atr'].iloc[-1] if 'atr' in df_4h.columns else 0
            logger.debug(f"{symbol} ATR values - 15m: {atr_15m:.4f}, 1h: {atr_1h:.4f}, 4h: {atr_4h:.4f}")
        except Exception as e:
            logger.warning(f"Error logging ATR values: {e}")
        
        return {
            'current_price': current_price,
            'orderbook': orderbook,
            'df_15min': df_15min,
            'df_hourly': df_hourly,
            'df_4h': df_4h,
            'fear_greed_index': fear_greed_index
        }
    except Exception as e:
        logger.error(f"Error collecting market data for {symbol}: {e}")
        return None

def get_fear_and_greed_index():
    """공포 탐욕 지수 조회"""
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
        logger.error(f"Error fetching Fear and Greed Index: {e}")
        return None


# ============ v7.4 장기 추세 여력 판단 (Patience Logic) ============
def check_trend_remaining_room(df_hourly, df_4h, position_side: str, pnl_percent: float) -> dict:
    """
    🆕 v7.4: 1H/4H 기준 추세 여력 판단
    수익 포지션이 조기 종료되지 않도록 인내심 점수 계산
    
    Args:
        df_hourly: 1시간봉 데이터
        df_4h: 4시간봉 데이터
        position_side: 'long' or 'short'
        pnl_percent: 현재 수익률
    
    Returns:
        dict: {
            'has_room': bool,  # 추세 여력 있음
            'patience_score': int,  # 인내심 점수 (높을수록 더 기다려야 함)
            'block_exit': bool,  # True면 종료 차단
            'reason': str,
            'details': list
        }
    """
    result = {
        'has_room': False,
        'patience_score': 0,
        'block_exit': False,
        'reason': '',
        'details': []
    }
    
    # 손실 중이면 인내심 로직 적용 안함
    if pnl_percent <= 0:
        result['reason'] = '손실 중 - 인내심 로직 미적용'
        return result
    
    try:
        # 최신 데이터 가져오기
        h1_latest = df_hourly.iloc[-1] if len(df_hourly) > 0 else None
        h4_latest = df_4h.iloc[-1] if len(df_4h) > 0 else None
        
        if h1_latest is None or h4_latest is None:
            return result
        
        # 지표 추출
        rsi_1h = h1_latest.get('RSI', 50)
        rsi_4h = h4_latest.get('RSI', 50)
        adx_1h = h1_latest.get('ADX', 20)
        adx_4h = h4_latest.get('ADX', 20)
        di_plus_4h = h4_latest.get('DI+', 20)
        di_minus_4h = h4_latest.get('DI-', 20)
        macd_hist_1h = h1_latest.get('MACD_hist', 0)
        stoch_k_1h = h1_latest.get('Stoch_K', 50)
        stoch_k_4h = h4_latest.get('Stoch_K', 50)
        
        patience_score = 0
        details = []
        
        if position_side == 'long':
            # ===== LONG 포지션 추세 여력 판단 =====
            
            # 4H RSI 여력
            if rsi_4h < 55:
                patience_score += 3
                details.append(f"📈 4H RSI {rsi_4h:.1f} < 55 → 상승 여력 매우 충분 (+3)")
            elif rsi_4h < 65:
                patience_score += 2
                details.append(f"📈 4H RSI {rsi_4h:.1f} < 65 → 상승 여력 충분 (+2)")
            elif rsi_4h < 75:
                patience_score += 1
                details.append(f"⚠️ 4H RSI {rsi_4h:.1f} < 75 → 상승 여력 일부 (+1)")
            else:
                details.append(f"🔴 4H RSI {rsi_4h:.1f} >= 75 → 과매수 진입")
            
            # 4H Stochastic 여력
            if stoch_k_4h < 70:
                patience_score += 2
                details.append(f"📈 4H Stoch {stoch_k_4h:.1f} < 70 → 상승 여력 (+2)")
            elif stoch_k_4h < 85:
                patience_score += 1
                details.append(f"⚠️ 4H Stoch {stoch_k_4h:.1f} < 85 → 약간의 여력 (+1)")
            
            # 4H ADX + DI 트렌드 강도
            if adx_4h > 25 and di_plus_4h > di_minus_4h:
                patience_score += 2
                details.append(f"💪 4H ADX {adx_4h:.1f} + DI+ > DI- → 상승 트렌드 강함 (+2)")
            
            # 1H MACD 모멘텀
            if macd_hist_1h > 0:
                patience_score += 1
                details.append(f"📊 1H MACD 히스토그램 양수 → 모멘텀 유지 (+1)")
            
            # 1H RSI 여력
            if rsi_1h < 70:
                patience_score += 1
                details.append(f"📈 1H RSI {rsi_1h:.1f} < 70 → 1H 여력 (+1)")
        
        else:  # SHORT 포지션
            # ===== SHORT 포지션 추세 여력 판단 =====
            
            # 4H RSI 여력
            if rsi_4h > 45:
                patience_score += 3
                details.append(f"📉 4H RSI {rsi_4h:.1f} > 45 → 하락 여력 매우 충분 (+3)")
            elif rsi_4h > 35:
                patience_score += 2
                details.append(f"📉 4H RSI {rsi_4h:.1f} > 35 → 하락 여력 충분 (+2)")
            elif rsi_4h > 25:
                patience_score += 1
                details.append(f"⚠️ 4H RSI {rsi_4h:.1f} > 25 → 하락 여력 일부 (+1)")
            else:
                details.append(f"🔴 4H RSI {rsi_4h:.1f} <= 25 → 과매도 진입")
            
            # 4H Stochastic 여력
            if stoch_k_4h > 30:
                patience_score += 2
                details.append(f"📉 4H Stoch {stoch_k_4h:.1f} > 30 → 하락 여력 (+2)")
            elif stoch_k_4h > 15:
                patience_score += 1
                details.append(f"⚠️ 4H Stoch {stoch_k_4h:.1f} > 15 → 약간의 여력 (+1)")
            
            # 4H ADX + DI 트렌드 강도
            if adx_4h > 25 and di_minus_4h > di_plus_4h:
                patience_score += 2
                details.append(f"💪 4H ADX {adx_4h:.1f} + DI- > DI+ → 하락 트렌드 강함 (+2)")
            
            # 1H MACD 모멘텀
            if macd_hist_1h < 0:
                patience_score += 1
                details.append(f"📊 1H MACD 히스토그램 음수 → 모멘텀 유지 (+1)")
            
            # 1H RSI 여력
            if rsi_1h > 30:
                patience_score += 1
                details.append(f"📉 1H RSI {rsi_1h:.1f} > 30 → 1H 여력 (+1)")
        
        # ========================================
        # === 🆕 v7.6: RSI 과열 상태 인내심 보너스 ===
        # ========================================
        # RSI가 극단적 과열 상태이면 곧 반등/반락 가능성 높음
        # 손실 중이더라도 인내심 점수를 추가로 부여
        
        if position_side == 'long':
            # LONG 포지션: 과매도 상태이면 반등 기대
            if rsi_4h < V76_RSI_EXTREME_OVERSOLD:
                patience_score += 4
                details.append(f"🧘 4H RSI {rsi_4h:.1f} 극단적 과매도 → 반등 기대 (+4)")
            elif rsi_4h < V76_RSI_OVERSOLD:
                patience_score += 2
                details.append(f"🧘 4H RSI {rsi_4h:.1f} 과매도 → 반등 기대 (+2)")
            
            if stoch_k_4h < V76_STOCH_EXTREME_OVERSOLD:
                patience_score += 2
                details.append(f"🧘 4H Stoch {stoch_k_4h:.1f} 극단적 과매도 → 반등 기대 (+2)")
        else:  # SHORT 포지션
            # SHORT 포지션: 과매수 상태이면 반락 기대
            if rsi_4h > V76_RSI_EXTREME_OVERBOUGHT:
                patience_score += 4
                details.append(f"🧘 4H RSI {rsi_4h:.1f} 극단적 과매수 → 반락 기대 (+4)")
            elif rsi_4h > V76_RSI_OVERBOUGHT:
                patience_score += 2
                details.append(f"🧘 4H RSI {rsi_4h:.1f} 과매수 → 반락 기대 (+2)")
            
            if stoch_k_4h > V76_STOCH_EXTREME_OVERBOUGHT:
                patience_score += 2
                details.append(f"🧘 4H Stoch {stoch_k_4h:.1f} 극단적 과매수 → 반락 기대 (+2)")
        
        # 결과 판정
        result['patience_score'] = patience_score
        result['details'] = details
        
        if patience_score >= 5:
            result['has_room'] = True
            result['block_exit'] = True
            result['reason'] = f"🔒 추세 여력 충분 (점수: {patience_score}/10) - EXIT 차단!"
        elif patience_score >= 3:
            result['has_room'] = True
            result['block_exit'] = False  # 경고만
            result['reason'] = f"⚠️ 추세 여력 있음 (점수: {patience_score}/10) - 신중히 결정"
        else:
            result['has_room'] = False
            result['block_exit'] = False
            result['reason'] = f"✅ 추세 여력 부족 (점수: {patience_score}/10) - EXIT 허용"
        
    except Exception as e:
        logger.error(f"추세 여력 판단 오류: {e}")
        result['reason'] = f"판단 오류: {e}"
    
    return result


# ============ v7.3 Rule-Based Validation System ============
def calculate_risk_score(df_15min, df_hourly, df_4h, action: str) -> dict:
    """
    🆕 v7.3: Rule-Based Risk Score 계산
    수학적 비교를 Python으로 정확하게 수행
    
    ⚠️ 단기 극단값(15분봉)도 레버리지 특성상 즉각 손실 위험이 있으므로 
    높은 가중치 부여하여 REJECT/MODIFY 처리
    
    Returns:
        dict: {
            'total_score': int,
            'details': list of strings,
            'is_high_risk': bool
        }
    """
    risk_score = 0
    details = []
    
    # 안전한 값 추출 헬퍼
    def safe_get(df, col, default=50):
        try:
            val = df[col].iloc[-1]
            return float(val) if pd.notna(val) else default
        except:
            return default
    
    # 지표 추출
    rsi_15m = safe_get(df_15min, 'rsi', 50)
    rsi_1h = safe_get(df_hourly, 'rsi', 50)
    rsi_4h = safe_get(df_4h, 'rsi', 50)
    
    stoch_k_15m = safe_get(df_15min, 'stoch_k', 50)
    stoch_k_1h = safe_get(df_hourly, 'stoch_k', 50)
    stoch_k_4h = safe_get(df_4h, 'stoch_k', 50)
    
    adx_4h = safe_get(df_4h, 'adx', 25)
    di_plus_4h = safe_get(df_4h, 'di_plus', 25)
    di_minus_4h = safe_get(df_4h, 'di_minus', 25)
    
    cmf_15m = safe_get(df_15min, 'cmf', 0)
    cmf_1h = safe_get(df_hourly, 'cmf', 0)
    cmf_4h = safe_get(df_4h, 'cmf', 0)
    
    bb_upper_1h = safe_get(df_hourly, 'bb_bbh', 0)
    bb_lower_1h = safe_get(df_hourly, 'bb_bbl', 0)
    bb_upper_4h = safe_get(df_4h, 'bb_bbh', 0)
    bb_lower_4h = safe_get(df_4h, 'bb_bbl', 0)
    current_price = safe_get(df_15min, 'close', 0)
    
    if action.lower() == 'buy':
        # ========== BUY Signal Risk Factors ==========
        
        # 🚨 15m 타임프레임 (레버리지 즉각 위험 - 가중치 높음!)
        if rsi_15m > 85:
            risk_score += 5
            details.append(f"⚠️ 15m RSI {rsi_15m:.1f} > 85 → +5 (EXTREME overbought - immediate risk!)")
        elif rsi_15m > 80:
            risk_score += 4
            details.append(f"⚠️ 15m RSI {rsi_15m:.1f} > 80 → +4 (strong overbought - high risk)")
        elif rsi_15m > 75:
            risk_score += 2
            details.append(f"15m RSI {rsi_15m:.1f} > 75 → +2 (overbought)")
        
        if stoch_k_15m > 95:
            risk_score += 4
            details.append(f"⚠️ 15m Stoch %K {stoch_k_15m:.1f} > 95 → +4 (EXTREME - immediate pullback risk)")
        elif stoch_k_15m > 90:
            risk_score += 2
            details.append(f"15m Stoch %K {stoch_k_15m:.1f} > 90 → +2 (very high)")
        
        # 4h 타임프레임 (중장기 트렌드)
        if rsi_4h > 70:
            risk_score += 4
            details.append(f"4h RSI {rsi_4h:.1f} > 70 → +4 (strong overbought)")
        elif rsi_4h > 65:
            risk_score += 2
            details.append(f"4h RSI {rsi_4h:.1f} > 65 → +2 (overbought zone)")
        
        if stoch_k_4h > 90:
            risk_score += 2
            details.append(f"4h Stoch %K {stoch_k_4h:.1f} > 90 → +2 (overbought)")
        
        if adx_4h < 20:
            risk_score += 3
            details.append(f"4h ADX {adx_4h:.1f} < 20 → +3 (no clear trend)")
        
        if di_minus_4h > di_plus_4h:
            diff = di_minus_4h - di_plus_4h
            if diff > 10 and adx_4h > 25:
                risk_score += 4
                details.append(f"4h DI- {di_minus_4h:.1f} > DI+ {di_plus_4h:.1f} (diff {diff:.1f}) with strong ADX → +4 (strong downtrend)")
            else:
                risk_score += 2
                details.append(f"4h DI- {di_minus_4h:.1f} > DI+ {di_plus_4h:.1f} → +2 (against trend)")
        
        if cmf_4h < -0.1:
            risk_score += 2
            details.append(f"4h CMF {cmf_4h:.2f} < -0.1 → +2 (money outflow)")
        
        # 1h 타임프레임
        if rsi_1h > 75:
            risk_score += 3
            details.append(f"1h RSI {rsi_1h:.1f} > 75 → +3 (strong overbought)")
        elif rsi_1h > 70:
            risk_score += 2
            details.append(f"1h RSI {rsi_1h:.1f} > 70 → +2 (overbought)")
        
        if stoch_k_1h > 90:
            risk_score += 2
            details.append(f"1h Stoch %K {stoch_k_1h:.1f} > 90 → +2 (overbought)")
        
        if cmf_1h < -0.1:
            risk_score += 1
            details.append(f"1h CMF {cmf_1h:.2f} < -0.1 → +1 (money outflow)")
        
        # 복합 조건 - 다중 타임프레임 과열
        extreme_count = sum([rsi_15m > 75, rsi_1h > 70, rsi_4h > 65])
        if extreme_count >= 3:
            risk_score += 3
            details.append(f"⚠️ ALL timeframes overbought → +3 (triple confirmation risk)")
        elif extreme_count >= 2:
            risk_score += 1
            details.append(f"2 timeframes overbought → +1")
        
        # CMF 다중 음수
        cmf_negative_count = sum([cmf_15m < 0, cmf_1h < 0, cmf_4h < 0])
        if cmf_negative_count >= 2:
            risk_score += 2
            details.append(f"CMF negative on {cmf_negative_count} timeframes → +2")
        
        # BB 상단 근접
        if current_price > 0 and bb_upper_1h > 0 and bb_upper_4h > 0:
            if current_price > bb_upper_1h and current_price > bb_upper_4h:
                risk_score += 3
                details.append(f"Price above BB upper on both 1h and 4h → +3 (double extreme)")
                
    else:  # SELL signal
        # ========== SELL Signal Risk Factors ==========
        
        # 🚨 15m 타임프레임 (레버리지 즉각 위험 - 가중치 높음!)
        if rsi_15m < 15:
            risk_score += 5
            details.append(f"⚠️ 15m RSI {rsi_15m:.1f} < 15 → +5 (EXTREME oversold - immediate risk!)")
        elif rsi_15m < 20:
            risk_score += 4
            details.append(f"⚠️ 15m RSI {rsi_15m:.1f} < 20 → +4 (strong oversold - high risk)")
        elif rsi_15m < 25:
            risk_score += 2
            details.append(f"15m RSI {rsi_15m:.1f} < 25 → +2 (oversold)")
        
        if stoch_k_15m < 5:
            risk_score += 4
            details.append(f"⚠️ 15m Stoch %K {stoch_k_15m:.1f} < 5 → +4 (EXTREME - immediate bounce risk)")
        elif stoch_k_15m < 10:
            risk_score += 2
            details.append(f"15m Stoch %K {stoch_k_15m:.1f} < 10 → +2 (very low)")
        
        # 4h 타임프레임 (중장기 트렌드)
        if rsi_4h < 30:
            risk_score += 4
            details.append(f"4h RSI {rsi_4h:.1f} < 30 → +4 (strong oversold)")
        elif rsi_4h < 35:
            risk_score += 2
            details.append(f"4h RSI {rsi_4h:.1f} < 35 → +2 (oversold zone)")
        
        if stoch_k_4h < 10:
            risk_score += 2
            details.append(f"4h Stoch %K {stoch_k_4h:.1f} < 10 → +2 (oversold)")
        
        if adx_4h < 20:
            risk_score += 3
            details.append(f"4h ADX {adx_4h:.1f} < 20 → +3 (no clear trend)")
        
        if di_plus_4h > di_minus_4h:
            diff = di_plus_4h - di_minus_4h
            if diff > 10 and adx_4h > 25:
                risk_score += 4
                details.append(f"4h DI+ {di_plus_4h:.1f} > DI- {di_minus_4h:.1f} (diff {diff:.1f}) with strong ADX → +4 (strong uptrend)")
            else:
                risk_score += 2
                details.append(f"4h DI+ {di_plus_4h:.1f} > DI- {di_minus_4h:.1f} → +2 (against trend)")
        
        if cmf_4h > 0.1:
            risk_score += 2
            details.append(f"4h CMF {cmf_4h:.2f} > 0.1 → +2 (money inflow)")
        
        # 1h 타임프레임
        if rsi_1h < 25:
            risk_score += 3
            details.append(f"1h RSI {rsi_1h:.1f} < 25 → +3 (strong oversold)")
        elif rsi_1h < 30:
            risk_score += 2
            details.append(f"1h RSI {rsi_1h:.1f} < 30 → +2 (oversold)")
        
        if stoch_k_1h < 10:
            risk_score += 2
            details.append(f"1h Stoch %K {stoch_k_1h:.1f} < 10 → +2 (oversold)")
        
        if cmf_1h > 0.1:
            risk_score += 1
            details.append(f"1h CMF {cmf_1h:.2f} > 0.1 → +1 (money inflow)")
        
        # 복합 조건 - 다중 타임프레임 과매도
        extreme_count = sum([rsi_15m < 25, rsi_1h < 30, rsi_4h < 35])
        if extreme_count >= 3:
            risk_score += 3
            details.append(f"⚠️ ALL timeframes oversold → +3 (triple confirmation risk)")
        elif extreme_count >= 2:
            risk_score += 1
            details.append(f"2 timeframes oversold → +1")
        
        # CMF 다중 양수
        cmf_positive_count = sum([cmf_15m > 0, cmf_1h > 0, cmf_4h > 0])
        if cmf_positive_count >= 2:
            risk_score += 2
            details.append(f"CMF positive on {cmf_positive_count} timeframes → +2")
        
        # BB 하단 근접
        if current_price > 0 and bb_lower_1h > 0 and bb_lower_4h > 0:
            if current_price < bb_lower_1h and current_price < bb_lower_4h:
                risk_score += 3
                details.append(f"Price below BB lower on both 1h and 4h → +3 (double extreme)")
    
    if not details:
        details.append("No significant risk factors detected → +0")
    
    return {
        'total_score': risk_score,
        'details': details,
        'is_high_risk': risk_score >= 8
    }


def calculate_approval_score(df_15min, df_hourly, df_4h, action: str) -> dict:
    """
    🆕 v7.6: Rule-Based Approval Score 계산 (단기 신호 강화)
    
    v7.6 변경사항:
    - 4H 추세 의존도 감소 (25점 → 20점)
    - 15분/1H 모멘텀 신호 점수 증가
    - 멀티타임프레임 정렬 보너스 추가
    - 단기 급등/급락 신호 반영
    
    Returns:
        dict: {
            'total_score': int,
            'details': list of strings,
            'is_approved': bool
        }
    """
    approval_score = 0
    details = []
    
    # 안전한 값 추출 헬퍼
    def safe_get(df, col, default=50):
        try:
            val = df[col].iloc[-1]
            return float(val) if pd.notna(val) else default
        except:
            return default
    
    # 지표 추출
    rsi_15m = safe_get(df_15min, 'rsi', 50)
    rsi_1h = safe_get(df_hourly, 'rsi', 50)
    rsi_4h = safe_get(df_4h, 'rsi', 50)
    
    adx_4h = safe_get(df_4h, 'adx', 25)
    di_plus_4h = safe_get(df_4h, 'di_plus', 25)
    di_minus_4h = safe_get(df_4h, 'di_minus', 25)
    
    adx_1h = safe_get(df_hourly, 'adx', 25)
    di_plus_1h = safe_get(df_hourly, 'di_plus', 25)
    di_minus_1h = safe_get(df_hourly, 'di_minus', 25)
    
    adx_15m = safe_get(df_15min, 'adx', 25)
    di_plus_15m = safe_get(df_15min, 'di_plus', 25)
    di_minus_15m = safe_get(df_15min, 'di_minus', 25)
    
    cmf_15m = safe_get(df_15min, 'cmf', 0)
    cmf_1h = safe_get(df_hourly, 'cmf', 0)
    cmf_4h = safe_get(df_4h, 'cmf', 0)
    
    macd_4h = safe_get(df_4h, 'macd', 0)
    macd_signal_4h = safe_get(df_4h, 'macd_signal', 0)
    macd_diff_4h = safe_get(df_4h, 'macd_diff', 0)
    
    macd_1h = safe_get(df_hourly, 'macd', 0)
    macd_signal_1h = safe_get(df_hourly, 'macd_signal', 0)
    
    macd_15m = safe_get(df_15min, 'macd', 0)
    macd_signal_15m = safe_get(df_15min, 'macd_signal', 0)
    
    sma_1h = safe_get(df_hourly, 'sma_20', 0)
    sma_15m = safe_get(df_15min, 'sma_20', 0)
    current_price = safe_get(df_15min, 'close', 0)
    
    # Stochastic 추출
    stoch_k_15m = safe_get(df_15min, 'stoch_k', 50)
    stoch_k_1h = safe_get(df_hourly, 'stoch_k', 50)
    
    if action.lower() == 'buy':
        # ========== BUY Signal Approval Factors ==========
        
        # === 1. 4H 추세 (max 20점 - 감소됨) ===
        if di_plus_4h > di_minus_4h and adx_4h > 20:
            if adx_4h > 25:
                approval_score += 20
                details.append(f"4h DI+ {di_plus_4h:.1f} > DI- {di_minus_4h:.1f} with ADX {adx_4h:.1f} > 25 → +20 (strong uptrend)")
            else:
                approval_score += 15
                details.append(f"4h DI+ {di_plus_4h:.1f} > DI- {di_minus_4h:.1f} with ADX {adx_4h:.1f} > 20 → +15 (uptrend)")
        elif adx_4h < 20:
            # 4H 추세 약함 - 단기 신호에 더 의존
            approval_score += 5
            details.append(f"4h ADX {adx_4h:.1f} < 20 (no clear trend) - relying on short-term signals → +5")
        
        # === 2. 1H 모멘텀 (max 20점 - 증가됨) ===
        if di_plus_1h > di_minus_1h:
            if adx_1h > 25:
                approval_score += 15
                details.append(f"1h DI+ {di_plus_1h:.1f} > DI- {di_minus_1h:.1f} with ADX {adx_1h:.1f} → +15 (1h bullish)")
            elif adx_1h > 20:
                approval_score += 10
                details.append(f"1h DI+ {di_plus_1h:.1f} > DI- {di_minus_1h:.1f} → +10 (1h bullish)")
        
        if macd_1h > macd_signal_1h:
            approval_score += 5
            details.append(f"1h MACD bullish → +5")
        
        # === 3. 15분 모멘텀 (max 20점 - 신규) ===
        if di_plus_15m > di_minus_15m and adx_15m > 20:
            approval_score += 10
            details.append(f"15m DI+ {di_plus_15m:.1f} > DI- with ADX {adx_15m:.1f} → +10 (15m momentum)")
        
        if macd_15m > macd_signal_15m:
            approval_score += 5
            details.append(f"15m MACD bullish → +5")
        
        # Stochastic 상승 신호
        if stoch_k_15m > 20 and stoch_k_15m < 80:
            approval_score += 5
            details.append(f"15m Stoch %K {stoch_k_15m:.1f} in good zone → +5")
        
        # === 4. RSI 조건 (max 15점) ===
        # 과매도 아닌 상태에서 진입 가능
        if 30 <= rsi_1h <= 65:
            approval_score += 10
            details.append(f"1h RSI {rsi_1h:.1f} in acceptable zone (30-65) → +10")
        elif 25 <= rsi_1h <= 70:
            approval_score += 5
            details.append(f"1h RSI {rsi_1h:.1f} marginally acceptable → +5")
        
        if 30 <= rsi_15m <= 70:
            approval_score += 5
            details.append(f"15m RSI {rsi_15m:.1f} not overbought → +5")
        
        # === 5. CMF/자금흐름 (max 10점) ===
        if cmf_1h > 0:
            approval_score += 5
            details.append(f"1h CMF {cmf_1h:.2f} positive → +5 (money inflow)")
        if cmf_15m > 0:
            approval_score += 5
            details.append(f"15m CMF {cmf_15m:.2f} positive → +5")
        
        # === 6. 멀티타임프레임 정렬 보너스 (max 15점 - 신규) ===
        bullish_count = 0
        if di_plus_15m > di_minus_15m:
            bullish_count += 1
        if di_plus_1h > di_minus_1h:
            bullish_count += 1
        if di_plus_4h > di_minus_4h:
            bullish_count += 1
        
        if bullish_count == 3:
            approval_score += 15
            details.append(f"All 3 timeframes aligned bullish → +15 (strong alignment)")
        elif bullish_count == 2:
            approval_score += 10
            details.append(f"2/3 timeframes aligned bullish → +10")
        elif bullish_count == 1:
            approval_score += 5
            details.append(f"1/3 timeframes bullish → +5 (weak but valid)")
            
    else:  # SELL signal
        # ========== SELL Signal Approval Factors ==========
        
        # === 1. 4H 추세 (max 20점 - 감소됨) ===
        if di_minus_4h > di_plus_4h and adx_4h > 20:
            if adx_4h > 25:
                approval_score += 20
                details.append(f"4h DI- {di_minus_4h:.1f} > DI+ {di_plus_4h:.1f} with ADX {adx_4h:.1f} > 25 → +20 (strong downtrend)")
            else:
                approval_score += 15
                details.append(f"4h DI- {di_minus_4h:.1f} > DI+ {di_plus_4h:.1f} with ADX {adx_4h:.1f} > 20 → +15 (downtrend)")
        elif adx_4h < 20:
            approval_score += 5
            details.append(f"4h ADX {adx_4h:.1f} < 20 (no clear trend) - relying on short-term signals → +5")
        
        # === 2. 1H 모멘텀 (max 20점 - 증가됨) ===
        if di_minus_1h > di_plus_1h:
            if adx_1h > 25:
                approval_score += 15
                details.append(f"1h DI- {di_minus_1h:.1f} > DI+ {di_plus_1h:.1f} with ADX {adx_1h:.1f} → +15 (1h bearish)")
            elif adx_1h > 20:
                approval_score += 10
                details.append(f"1h DI- {di_minus_1h:.1f} > DI+ {di_plus_1h:.1f} → +10 (1h bearish)")
        
        if macd_1h < macd_signal_1h:
            approval_score += 5
            details.append(f"1h MACD bearish → +5")
        
        # === 3. 15분 모멘텀 (max 20점 - 신규) ===
        if di_minus_15m > di_plus_15m and adx_15m > 20:
            approval_score += 10
            details.append(f"15m DI- {di_minus_15m:.1f} > DI+ with ADX {adx_15m:.1f} → +10 (15m momentum)")
        
        if macd_15m < macd_signal_15m:
            approval_score += 5
            details.append(f"15m MACD bearish → +5")
        
        # Stochastic 하락 신호
        if stoch_k_15m > 20 and stoch_k_15m < 80:
            approval_score += 5
            details.append(f"15m Stoch %K {stoch_k_15m:.1f} in good zone → +5")
        
        # === 4. RSI 조건 (max 15점) ===
        if 35 <= rsi_1h <= 70:
            approval_score += 10
            details.append(f"1h RSI {rsi_1h:.1f} in acceptable zone (35-70) → +10")
        elif 30 <= rsi_1h <= 75:
            approval_score += 5
            details.append(f"1h RSI {rsi_1h:.1f} marginally acceptable → +5")
        
        if 30 <= rsi_15m <= 70:
            approval_score += 5
            details.append(f"15m RSI {rsi_15m:.1f} not oversold → +5")
        
        # === 5. CMF/자금흐름 (max 10점) ===
        if cmf_1h < 0:
            approval_score += 5
            details.append(f"1h CMF {cmf_1h:.2f} negative → +5 (money outflow)")
        if cmf_15m < 0:
            approval_score += 5
            details.append(f"15m CMF {cmf_15m:.2f} negative → +5")
        
        # === 6. 멀티타임프레임 정렬 보너스 (max 15점 - 신규) ===
        bearish_count = 0
        if di_minus_15m > di_plus_15m:
            bearish_count += 1
        if di_minus_1h > di_plus_1h:
            bearish_count += 1
        if di_minus_4h > di_plus_4h:
            bearish_count += 1
        
        if bearish_count == 3:
            approval_score += 15
            details.append(f"All 3 timeframes aligned bearish → +15 (strong alignment)")
        elif bearish_count == 2:
            approval_score += 10
            details.append(f"2/3 timeframes aligned bearish → +10")
        elif bearish_count == 1:
            approval_score += 5
            details.append(f"1/3 timeframes bearish → +5 (weak but valid)")
    
    if not details:
        details.append("No approval factors detected → +0")
    
    # 🆕 v7.6: 최소 기본 점수 보장 (단기 신호만으로도 진입 가능)
    # 과매수/과매도가 아니면 최소 30점 보장
    if action.lower() == 'buy':
        if rsi_15m < 75 and rsi_1h < 70 and rsi_4h < 70:
            if approval_score < 30:
                approval_score = 30
                details.append(f"Base score guaranteed (not overbought) → min 30")
    else:
        if rsi_15m > 25 and rsi_1h > 30 and rsi_4h > 30:
            if approval_score < 30:
                approval_score = 30
                details.append(f"Base score guaranteed (not oversold) → min 30")
    
    return {
        'total_score': approval_score,
        'details': details,
        'is_approved': approval_score >= 60  # 🆕 v7.6: 임계값 70 → 60으로 낮춤
    }


def calculate_reverse_score(df_15min, df_hourly, df_4h, action: str) -> dict:
    """
    🆕 v7.4 개선: Rule-Based Reverse Score 계산 (기준 완화)
    극단적 과매수/과매도 시 신호 반전 여부 결정
    
    ⚠️ v7.4 변경사항:
    - trend_supports_original: 4개 조건 중 2개 이상 충족 시에만 차단
    - 반전 기준 완화: 10점/4신호 → 6점/2신호
    - RSI 기준 완화: 70~75 구간도 점수 부여
    - 1시간봉 가중치 상향
    - HOLD 판단 추가: 애매할 때는 Hold가 최선
    
    Returns:
        dict: {
            'total_score': int,
            'signal_count': int,
            'details': list of strings,
            'should_reverse': bool,
            'should_hold': bool,  # 🆕 v7.4: 애매한 상황
            'reverse_action': str ('buy' or 'sell'),
            'trend_supports_original': bool,
            'trend_support_count': int  # 🆕 v7.4: 트렌드 지지 조건 충족 수
        }
    """
    reverse_score = 0
    signal_count = 0
    details = []
    
    # 안전한 값 추출 헬퍼
    def safe_get(df, col, default=50):
        try:
            val = df[col].iloc[-1]
            return float(val) if pd.notna(val) else default
        except:
            return default
    
    # 지표 추출 (4시간봉 우선)
    rsi_4h = safe_get(df_4h, 'rsi', 50)
    rsi_1h = safe_get(df_hourly, 'rsi', 50)
    rsi_15m = safe_get(df_15min, 'rsi', 50)
    
    stoch_k_4h = safe_get(df_4h, 'stoch_k', 50)
    stoch_k_1h = safe_get(df_hourly, 'stoch_k', 50)
    stoch_k_15m = safe_get(df_15min, 'stoch_k', 50)
    
    adx_4h = safe_get(df_4h, 'adx', 25)
    di_plus_4h = safe_get(df_4h, 'di_plus', 25)
    di_minus_4h = safe_get(df_4h, 'di_minus', 25)
    
    adx_1h = safe_get(df_hourly, 'adx', 25)
    di_plus_1h = safe_get(df_hourly, 'di_plus', 25)
    di_minus_1h = safe_get(df_hourly, 'di_minus', 25)
    
    macd_diff_4h = safe_get(df_4h, 'macd_diff', 0)
    macd_diff_1h = safe_get(df_hourly, 'macd_diff', 0)
    
    bb_upper_4h = safe_get(df_4h, 'bb_bbh', 0)
    bb_lower_4h = safe_get(df_4h, 'bb_bbl', 0)
    bb_middle_4h = safe_get(df_4h, 'bb_bbm', 0)
    bb_upper_1h = safe_get(df_hourly, 'bb_bbh', 0)
    bb_lower_1h = safe_get(df_hourly, 'bb_bbl', 0)
    current_price = safe_get(df_15min, 'close', 0)
    
    # ========== 4시간봉 트렌드 확인 (v7.4: 2개 이상 충족 시에만 차단) ==========
    trend_support_count = 0  # 🆕 v7.4: 충족된 조건 수 카운트
    trend_details = []
    
    if action.lower() == 'buy':
        # BUY 신호 - 4시간봉이 상승 추세를 지지하는지 확인
        
        # 조건 1: 4시간봉 RSI가 아직 과열 아님 (60 미만이면 여력 있음) - 기준 강화
        if rsi_4h < 60:
            trend_support_count += 1
            trend_details.append(f"✅ 4h RSI {rsi_4h:.1f} < 60 - Room for upside")
        
        # 조건 2: 4시간봉 DI+가 우세하면 상승 추세
        if di_plus_4h > di_minus_4h + 5 and adx_4h > 20:  # 차이 5 이상으로 강화
            trend_support_count += 1
            trend_details.append(f"✅ 4h Uptrend: DI+ {di_plus_4h:.1f} > DI- {di_minus_4h:.1f}, ADX {adx_4h:.1f}")
        
        # 조건 3: 4시간봉 MACD가 양수이고 상승 중이면 상승 모멘텀
        macd_prev_4h = safe_get(df_4h.iloc[:-1] if len(df_4h) > 1 else df_4h, 'macd_diff', 0)
        if macd_diff_4h > 0 and macd_diff_4h > macd_prev_4h:  # 양수 + 상승 중
            trend_support_count += 1
            trend_details.append(f"✅ 4h MACD Bullish & Rising: {macd_diff_4h:.4f}")
        
        # 조건 4: 가격이 4시간봉 BB 중심선 위에 있으면 상승 추세
        if current_price > bb_middle_4h and bb_middle_4h > 0:
            trend_support_count += 1
            trend_details.append(f"✅ Price ${current_price:.2f} above 4h BB middle ${bb_middle_4h:.2f}")
        
        # 🆕 v7.4: 2개 이상 충족 시에만 트렌드 지지 인정
        trend_supports_original = trend_support_count >= 2
        reverse_action = 'sell'
        
        # ========== REVERSE 점수 계산 ==========
        if trend_supports_original:
            details.append(f"🛡️ 4H TREND SUPPORTS BUY ({trend_support_count}/4 conditions met) - Reverse blocked")
            for td in trend_details:
                details.append(f"   {td}")
        else:
            # 4시간봉이 강하게 지지하지 않을 때 reverse 점수 계산
            if trend_support_count == 1:
                details.append(f"⚠️ Weak 4H trend support ({trend_support_count}/4 conditions) - Reverse possible")
            else:
                details.append(f"❌ No 4H trend support ({trend_support_count}/4 conditions) - Reverse likely")
            
            # 🔴 4시간봉 RSI 과매수 (v7.4: 기준 완화)
            if rsi_4h > 85:
                reverse_score += 5
                signal_count += 1
                details.append(f"🔴 4h RSI {rsi_4h:.1f} > 85 → +5 (EXTREME overbought on 4H!)")
            elif rsi_4h > 80:
                reverse_score += 3
                signal_count += 1
                details.append(f"🔴 4h RSI {rsi_4h:.1f} > 80 → +3 (Strong overbought on 4H)")
            elif rsi_4h > 75:
                reverse_score += 2
                signal_count += 1
                details.append(f"🟠 4h RSI {rsi_4h:.1f} > 75 → +2 (Overbought zone)")
            elif rsi_4h >= 70:
                reverse_score += 1
                details.append(f"🟡 4h RSI {rsi_4h:.1f} >= 70 → +1 (Entering overbought)")
            
            # 🔴 4시간봉 Stochastic 과매수 (v7.4: 기준 완화)
            if stoch_k_4h > 95:
                reverse_score += 4
                signal_count += 1
                details.append(f"🔴 4h Stoch %K {stoch_k_4h:.1f} > 95 → +4 (EXTREME on 4H)")
            elif stoch_k_4h > 90:
                reverse_score += 2
                signal_count += 1
                details.append(f"🔴 4h Stoch %K {stoch_k_4h:.1f} > 90 → +2 (Very high)")
            elif stoch_k_4h > 85:
                reverse_score += 1
                details.append(f"🟠 4h Stoch %K {stoch_k_4h:.1f} > 85 → +1 (High)")
            
            # 🔴 4시간봉 강한 하락 추세에서 BUY (추세 역행)
            if di_minus_4h > di_plus_4h + 20 and adx_4h > 35:
                reverse_score += 5
                signal_count += 1
                details.append(f"🔴 4H STRONG DOWNTREND: DI- {di_minus_4h:.1f} >> DI+ {di_plus_4h:.1f}, ADX {adx_4h:.1f} → +5")
            elif di_minus_4h > di_plus_4h + 10 and adx_4h > 25:  # 기준 완화
                reverse_score += 3
                signal_count += 1
                details.append(f"🔴 4H Downtrend: DI- {di_minus_4h:.1f} > DI+ {di_plus_4h:.1f}, ADX {adx_4h:.1f} → +3")
            elif di_minus_4h > di_plus_4h + 5 and adx_4h > 20:
                reverse_score += 1
                details.append(f"🟠 4H Mild bearish: DI- {di_minus_4h:.1f} > DI+ {di_plus_4h:.1f} → +1")
            
            # 🔴 MACD 약세
            if macd_diff_4h < 0 and macd_diff_1h < 0:
                reverse_score += 2
                details.append(f"🟠 MACD bearish on both 1h & 4h → +2")
            elif macd_diff_4h < 0:
                reverse_score += 1
                details.append(f"🟡 4H MACD bearish → +1")
            
            # 🔴 가격이 4시간봉 BB 상단 위로 돌파
            if current_price > 0 and bb_upper_4h > 0:
                if current_price > bb_upper_4h * 1.02:  # 2% 이상 돌파
                    reverse_score += 3
                    signal_count += 1
                    details.append(f"🔴 Price {((current_price/bb_upper_4h)-1)*100:.1f}% above 4H BB upper → +3")
                elif current_price > bb_upper_4h:  # BB 상단 돌파
                    reverse_score += 1
                    details.append(f"🟠 Price above 4H BB upper → +1")
            
            # 🆕 v7.4: 1시간봉 신호도 더 중요하게 반영
            if rsi_1h > 80:
                reverse_score += 2
                signal_count += 1
                details.append(f"🔴 1h RSI {rsi_1h:.1f} > 80 → +2 (Strong overbought)")
            elif rsi_1h > 75:
                reverse_score += 1
                details.append(f"🟠 1h RSI {rsi_1h:.1f} > 75 → +1 (Overbought)")
            
            if stoch_k_1h > 90:
                reverse_score += 2
                signal_count += 1
                details.append(f"🔴 1h Stoch {stoch_k_1h:.1f} > 90 → +2 (Very high)")
            elif stoch_k_1h > 85:
                reverse_score += 1
                details.append(f"🟠 1h Stoch {stoch_k_1h:.1f} > 85 → +1 (High)")
            
            # 🆕 v7.4: 1시간봉 DI 역행
            if di_minus_1h > di_plus_1h + 10 and adx_1h > 25:
                reverse_score += 2
                signal_count += 1
                details.append(f"🔴 1H Downtrend: DI- {di_minus_1h:.1f} > DI+ {di_plus_1h:.1f} → +2")
        
    else:  # action == 'sell'
        # SELL 신호 - 4시간봉이 하락 추세를 지지하는지 확인
        
        # 조건 1: 4시간봉 RSI가 아직 과매도 아님 (40 초과면 여력 있음) - 기준 강화
        if rsi_4h > 40:
            trend_support_count += 1
            trend_details.append(f"✅ 4h RSI {rsi_4h:.1f} > 40 - Room for downside")
        
        # 조건 2: 4시간봉 DI-가 우세하면 하락 추세
        if di_minus_4h > di_plus_4h + 5 and adx_4h > 20:  # 차이 5 이상으로 강화
            trend_support_count += 1
            trend_details.append(f"✅ 4h Downtrend: DI- {di_minus_4h:.1f} > DI+ {di_plus_4h:.1f}, ADX {adx_4h:.1f}")
        
        # 조건 3: 4시간봉 MACD가 음수이고 하락 중이면 하락 모멘텀
        macd_prev_4h = safe_get(df_4h.iloc[:-1] if len(df_4h) > 1 else df_4h, 'macd_diff', 0)
        if macd_diff_4h < 0 and macd_diff_4h < macd_prev_4h:  # 음수 + 하락 중
            trend_support_count += 1
            trend_details.append(f"✅ 4h MACD Bearish & Falling: {macd_diff_4h:.4f}")
        
        # 조건 4: 가격이 4시간봉 BB 중심선 아래에 있으면 하락 추세
        if current_price < bb_middle_4h and bb_middle_4h > 0:
            trend_support_count += 1
            trend_details.append(f"✅ Price ${current_price:.2f} below 4h BB middle ${bb_middle_4h:.2f}")
        
        # 🆕 v7.4: 2개 이상 충족 시에만 트렌드 지지 인정
        trend_supports_original = trend_support_count >= 2
        reverse_action = 'buy'
        
        # ========== REVERSE 점수 계산 ==========
        if trend_supports_original:
            details.append(f"🛡️ 4H TREND SUPPORTS SELL ({trend_support_count}/4 conditions met) - Reverse blocked")
            for td in trend_details:
                details.append(f"   {td}")
        else:
            # 4시간봉이 강하게 지지하지 않을 때 reverse 점수 계산
            if trend_support_count == 1:
                details.append(f"⚠️ Weak 4H trend support ({trend_support_count}/4 conditions) - Reverse possible")
            else:
                details.append(f"❌ No 4H trend support ({trend_support_count}/4 conditions) - Reverse likely")
            
            # 🟢 4시간봉 RSI 과매도 (v7.4: 기준 완화)
            if rsi_4h < 15:
                reverse_score += 5
                signal_count += 1
                details.append(f"🟢 4h RSI {rsi_4h:.1f} < 15 → +5 (EXTREME oversold on 4H!)")
            elif rsi_4h < 20:
                reverse_score += 3
                signal_count += 1
                details.append(f"🟢 4h RSI {rsi_4h:.1f} < 20 → +3 (Strong oversold on 4H)")
            elif rsi_4h < 25:
                reverse_score += 2
                signal_count += 1
                details.append(f"🟡 4h RSI {rsi_4h:.1f} < 25 → +2 (Oversold zone)")
            elif rsi_4h <= 30:
                reverse_score += 1
                details.append(f"🟡 4h RSI {rsi_4h:.1f} <= 30 → +1 (Entering oversold)")
            
            # 🟢 4시간봉 Stochastic 과매도 (v7.4: 기준 완화)
            if stoch_k_4h < 5:
                reverse_score += 4
                signal_count += 1
                details.append(f"🟢 4h Stoch %K {stoch_k_4h:.1f} < 5 → +4 (EXTREME on 4H)")
            elif stoch_k_4h < 10:
                reverse_score += 2
                signal_count += 1
                details.append(f"🟢 4h Stoch %K {stoch_k_4h:.1f} < 10 → +2 (Very low)")
            elif stoch_k_4h < 15:
                reverse_score += 1
                details.append(f"🟡 4h Stoch %K {stoch_k_4h:.1f} < 15 → +1 (Low)")
            
            # 🟢 4시간봉 강한 상승 추세에서 SELL (추세 역행)
            if di_plus_4h > di_minus_4h + 20 and adx_4h > 35:
                reverse_score += 5
                signal_count += 1
                details.append(f"🟢 4H STRONG UPTREND: DI+ {di_plus_4h:.1f} >> DI- {di_minus_4h:.1f}, ADX {adx_4h:.1f} → +5")
            elif di_plus_4h > di_minus_4h + 10 and adx_4h > 25:  # 기준 완화
                reverse_score += 3
                signal_count += 1
                details.append(f"🟢 4H Uptrend: DI+ {di_plus_4h:.1f} > DI- {di_minus_4h:.1f}, ADX {adx_4h:.1f} → +3")
            elif di_plus_4h > di_minus_4h + 5 and adx_4h > 20:
                reverse_score += 1
                details.append(f"🟡 4H Mild bullish: DI+ {di_plus_4h:.1f} > DI- {di_minus_4h:.1f} → +1")
            
            # 🟢 MACD 강세
            if macd_diff_4h > 0 and macd_diff_1h > 0:
                reverse_score += 2
                details.append(f"🟡 MACD bullish on both 1h & 4h → +2")
            elif macd_diff_4h > 0:
                reverse_score += 1
                details.append(f"🟡 4H MACD bullish → +1")
            
            # 🟢 가격이 4시간봉 BB 하단 아래로 돌파
            if current_price > 0 and bb_lower_4h > 0:
                if current_price < bb_lower_4h * 0.98:  # 2% 이상 돌파
                    reverse_score += 3
                    signal_count += 1
                    details.append(f"🟢 Price {(1-(current_price/bb_lower_4h))*100:.1f}% below 4H BB lower → +3")
                elif current_price < bb_lower_4h:  # BB 하단 돌파
                    reverse_score += 1
                    details.append(f"🟡 Price below 4H BB lower → +1")
            
            # 🆕 v7.4: 1시간봉 신호도 더 중요하게 반영
            if rsi_1h < 20:
                reverse_score += 2
                signal_count += 1
                details.append(f"🟢 1h RSI {rsi_1h:.1f} < 20 → +2 (Strong oversold)")
            elif rsi_1h < 25:
                reverse_score += 1
                details.append(f"🟡 1h RSI {rsi_1h:.1f} < 25 → +1 (Oversold)")
            
            if stoch_k_1h < 10:
                reverse_score += 2
                signal_count += 1
                details.append(f"🟢 1h Stoch {stoch_k_1h:.1f} < 10 → +2 (Very low)")
            elif stoch_k_1h < 15:
                reverse_score += 1
                details.append(f"🟡 1h Stoch {stoch_k_1h:.1f} < 15 → +1 (Low)")
            
            # 🆕 v7.4: 1시간봉 DI 역행
            if di_plus_1h > di_minus_1h + 10 and adx_1h > 25:
                reverse_score += 2
                signal_count += 1
                details.append(f"🟢 1H Uptrend: DI+ {di_plus_1h:.1f} > DI- {di_minus_1h:.1f} → +2")
    
    if not details:
        details.append("No extreme signals detected → +0")
    
    # 🆕 v7.4: 반전 조건 대폭 완화
    # 반전하려면: 4시간봉 지지 없음(2개 미만 충족) + (2개 이상의 신호 또는 6점 이상)
    # 애매하면: HOLD 권장 (4-5점 또는 1개 신호)
    should_reverse = (not trend_supports_original) and (signal_count >= 2 or reverse_score >= 6)
    should_hold = (not trend_supports_original) and (not should_reverse) and (signal_count == 1 or (reverse_score >= 4 and reverse_score < 6))
    
    return {
        'total_score': reverse_score,
        'signal_count': signal_count,
        'details': details,
        'should_reverse': should_reverse,
        'should_hold': should_hold,  # 🆕 v7.4
        'reverse_action': reverse_action,
        'trend_supports_original': trend_supports_original,
        'trend_support_count': trend_support_count  # 🆕 v7.4
    }
    


def rule_based_validation(symbol: str, action: str, market_data: dict) -> dict:
    """
    🆕 v7.3: Rule-Based 종합 검증
    AI 대신 Python 로직으로 진입 여부 결정
    
    🆕 v7.6: Leverage, Position Size는 CONFIG 고정값 사용
    
    🆕 v7.4 Enhanced:
    - 동적 심볼 필터 (DB 기반 30일 성과)
    - Mean Reversion 기회 포착 (신호 방향 Approve)
    - Contrarian 진입 조건 강화 (8점 이상)
    
    Returns:
        dict: {
            'decision': 'approve' | 'reject' | 'modify' | 'reverse' | 'mean_reversion',
            'modified_action': str,  # reverse일 경우 반전된 액션
            'risk_score': dict,
            'approval_score': dict,
            'reverse_score': dict,  # 반전 점수
            'reason': str,
            'recommended_params': dict  # AI가 조정할 기본값
        }
    """
    df_15min = market_data['df_15min']
    df_hourly = market_data['df_hourly']
    df_4h = market_data['df_4h']
    current_price = market_data['current_price']
    
    # 🆕 v7.6: CONFIG에서 고정값 가져오기
    config = get_symbol_config(symbol)
    base_leverage = config.get('leverage', 10)
    base_position_pct = config.get('position_size_percent', 30)
    
    logger.info(f"📌 CONFIG 기반 고정값: Leverage={base_leverage}x, Position={base_position_pct}%")
    
    # ========== 🆕 v7.4 STEP 0: 동적 심볼 필터 체크 ==========
    symbol_filter = get_symbol_performance_filter(symbol, V74_SYMBOL_FILTER_LOOKBACK_DAYS)
    
    if symbol_filter['status'] == 'BLACKLIST':
        logger.warning(f"🚫 v7.4 {symbol} BLACKLISTED by dynamic filter: {symbol_filter['reason']}")
        
        # ATR 계산
        try:
            atr_4h = df_4h['atr'].iloc[-1] if 'atr' in df_4h.columns else current_price * 0.02
        except:
            atr_4h = current_price * 0.02
            
        return {
            'decision': 'reject',
            'modified_action': action,
            'risk_score': {'total_score': 10, 'details': [f'v7.4 BLACKLIST: {symbol_filter["reason"]}'], 'is_high_risk': True},
            'approval_score': {'total_score': 0, 'details': ['Blocked by dynamic symbol filter'], 'is_approved': False},
            'reverse_score': {'total_score': 0, 'signal_count': 0, 'details': [], 'should_reverse': False, 'should_hold': False},
            'reason': f"v7.4 BLACKLIST: {symbol_filter['reason']}",
            'recommended_params': {
                'leverage': 0,
                'position_percent': 0,
                'stop_loss': 0,
                'take_profit': 0,
                'current_price': current_price,
                'atr': atr_4h
            },
            'v74_symbol_filter': symbol_filter
        }
    
    # 동적 포지션 사이즈 조정
    adjusted_position_pct = calculate_position_size_v74(base_position_pct, symbol)
    if symbol_filter['status'] != 'NORMAL' and symbol_filter['status'] != 'NEUTRAL':
        logger.info(f"📊 v7.4 Symbol filter: {symbol_filter['status']} - Size multiplier: {symbol_filter['size_multiplier']}")
    
    
    # 1. Reverse Score 계산 (먼저 체크 - 극단적 신호 감지)
    reverse_result = calculate_reverse_score(df_15min, df_hourly, df_4h, action)
    
    # 2. Risk Score 계산
    risk_result = calculate_risk_score(df_15min, df_hourly, df_4h, action)
    
    # 3. Approval Score 계산
    approval_result = calculate_approval_score(df_15min, df_hourly, df_4h, action)
    
    # 점수 추출
    reverse_score = reverse_result['total_score']
    reverse_signals = reverse_result['signal_count']
    risk_score = risk_result['total_score']
    approval_score = approval_result['total_score']
    
    # ATR 기반 TP/SL 계산
    try:
        atr_4h = df_4h['atr'].iloc[-1] if 'atr' in df_4h.columns else current_price * 0.02
        if pd.isna(atr_4h) or atr_4h <= 0:
            atr_4h = current_price * 0.02
    except:
        atr_4h = current_price * 0.02
    
    # 🆕 v7.5: 15분봉 및 1시간봉 ATR도 가져오기 (타이트한 TP/SL용)
    try:
        atr_15m = df_15min['atr'].iloc[-1] if 'atr' in df_15min.columns else current_price * 0.005
        if pd.isna(atr_15m) or atr_15m <= 0:
            atr_15m = current_price * 0.005
    except:
        atr_15m = current_price * 0.005
    
    try:
        atr_1h = df_hourly['atr'].iloc[-1] if 'atr' in df_hourly.columns else current_price * 0.01
        if pd.isna(atr_1h) or atr_1h <= 0:
            atr_1h = current_price * 0.01
    except:
        atr_1h = current_price * 0.01
    
    # 🆕 v7.5: 타이트한 TP/SL 계산 (15분봉 ATR 기반)
    tight_tp_sl = calculate_tight_tp_sl(current_price, action, atr_15m, atr_1h, symbol)
    logger.info(f"📊 v7.5 Tight TP/SL: SL={tight_tp_sl['sl_percent']:.2f}%, TP={tight_tp_sl['tp_percent']:.2f}%, R:R={tight_tp_sl['rr_ratio']:.2f}")
    
    # ========== 🆕 v7.4 Mean Reversion 체크 (최우선) ==========
    mean_reversion = check_mean_reversion_opportunity(action, df_15min, df_hourly, df_4h)
    
    # ========== 🆕 v7.4 Contrarian 체크 (강화된 조건) ==========
    contrarian = check_contrarian_entry_v74(action, df_15min, df_hourly, df_4h)
    
    # ========== 결정 로직 ==========
    modified_action = action  # 기본값: 원래 액션 유지
    
    # 🆕 v7.4 STEP -1: Mean Reversion 기회 포착 (신호 방향 Approve)
    # 극단적 과매도에서 BUY 신호 또는 극단적 과매수에서 SELL 신호 → Approve
    if mean_reversion['is_mean_reversion']:
        decision = 'mean_reversion'
        modified_action = action  # 원래 신호 방향 유지!
        
        # Approval Score에 부스트 적용
        boosted_approval = approval_score + mean_reversion['confidence_boost']
        
        reason = f"🎯 v7.4 {mean_reversion['reason']} | Boosted Approval: {approval_score}+{mean_reversion['confidence_boost']}={boosted_approval}"
        
        # 🆕 v7.5: 타이트한 TP/SL 사용
        default_sl = tight_tp_sl['stop_loss']
        default_tp = tight_tp_sl['take_profit']
        
        logger.info(f"🎯 v7.4 Mean Reversion APPROVED: {symbol} {action.upper()}")
        logger.info(f"   {mean_reversion['reason']}")
    
    # 🆕 v7.4 STEP 0: Contrarian 체크 (더 엄격한 조건)
    # 기존 reverse 로직 대체 - 8점 이상 + 3TF 동시 극단에서만 반대매매
    elif contrarian['should_contrarian']:
        decision = 'reverse'
        modified_action = contrarian['contrarian_action']
        reason = f"🔄 v7.4 CONTRARIAN: {contrarian['reason']} | Original {action.upper()} → {modified_action.upper()}"
        
        # 🆕 v7.5: 반전된 방향으로 타이트한 TP/SL 재계산
        contrarian_tp_sl = calculate_tight_tp_sl(current_price, modified_action, atr_15m, atr_1h, symbol)
        default_sl = contrarian_tp_sl['stop_loss']
        default_tp = contrarian_tp_sl['take_profit']
        
        # Contrarian은 사이즈 50% 축소
        adjusted_position_pct = adjusted_position_pct * 0.5
        logger.info(f"🔄 v7.4 Contrarian entry: Position size reduced to {adjusted_position_pct:.1f}%")
    
    # 🔄 기존 STEP 0: 반전 조건 체크 (v7.4에서는 Contrarian으로 대체, 하지만 fallback으로 유지)
    # v7.4: Contrarian 조건 미충족 시에도 기존 reverse 로직 활용 가능 (더 느슨한 조건)
    elif reverse_result['should_reverse'] and not contrarian['should_contrarian']:
        # 기존 reverse는 이제 "weak contrarian"으로 취급 - HOLD 권장
        decision = 'reject'
        modified_action = 'hold'
        reason = f"⏸️ v7.4 HOLD - Weak contrarian signals (Score: {reverse_score}/8, Signals: {reverse_signals}). v7.4 requires 8+ for contrarian."
        
        # 🆕 v7.5: 타이트한 TP/SL 사용
        default_sl = tight_tp_sl['stop_loss']
        default_tp = tight_tp_sl['take_profit']
    
    # 🆕 v7.4 STEP 0.5: HOLD 판단 (애매한 상황)
    elif reverse_result.get('should_hold', False):
        decision = 'reject'  # Hold는 기본적으로 reject로 처리
        modified_action = 'hold'
        reason = f"⏸️ HOLD - Ambiguous signals (Score: {reverse_score}, Signals: {reverse_signals}). Better to wait."
        
        # 🆕 v7.5: 타이트한 TP/SL 사용
        default_sl = tight_tp_sl['stop_loss']
        default_tp = tight_tp_sl['take_profit']
        
        # 🆕 v7.6: CONFIG 고정값 유지
        
    # STEP 1: 높은 리스크 → REJECT
    elif risk_score >= 8:
        decision = 'reject'
        reason = f"HIGH RISK - Risk Score {risk_score}/8 exceeds threshold"
        
        # 🆕 v7.5: 타이트한 TP/SL 사용
        default_sl = tight_tp_sl['stop_loss']
        default_tp = tight_tp_sl['take_profit']
        
        # 🆕 v7.6: CONFIG 고정값 유지
        
    # STEP 2: 중간 리스크 + 낮은 승인 → MODIFY
    elif risk_score >= 5 and approval_score < 75:
        decision = 'modify'
        reason = f"MODIFY - Risk Score {risk_score}, Approval Score {approval_score} (marginal)"
        
        # 🆕 v7.5: 타이트한 TP/SL 사용
        default_sl = tight_tp_sl['stop_loss']
        default_tp = tight_tp_sl['take_profit']
        
        # 🆕 v7.6: CONFIG 고정값 유지
        
    # STEP 3: 승인 점수 충분 → APPROVE 또는 MODIFY
    elif approval_score >= 60:  # 🆕 v7.6: 70 → 60으로 낮춤
        if risk_score <= 4 and approval_score >= 75:
            decision = 'approve'
            reason = f"APPROVED - Low Risk ({risk_score}), High Approval ({approval_score})"
        else:
            decision = 'modify'
            reason = f"MODIFY - Risk ({risk_score}), Approval ({approval_score})"
        
        # 🆕 v7.5: 타이트한 TP/SL 사용
        default_sl = tight_tp_sl['stop_loss']
        default_tp = tight_tp_sl['take_profit']
        
        # 🆕 v7.6: CONFIG 고정값 유지
    
    # 🆕 v7.6: 50~60점 범위도 MODIFY로 진행
    elif approval_score >= 50:
        decision = 'modify'
        reason = f"MODIFY (Conservative) - Approval Score {approval_score} in marginal zone (50-60)"
        
        # 🆕 v7.5: 타이트한 TP/SL 사용
        default_sl = tight_tp_sl['stop_loss']
        default_tp = tight_tp_sl['take_profit']
        
        # 🆕 v7.6: CONFIG 고정값 유지
            
    # STEP 4: 낮은 승인 점수 → REJECT
    else:
        decision = 'reject'
        reason = f"REJECTED - Approval Score {approval_score} below threshold (50)"
        
        # 🆕 v7.5: 타이트한 TP/SL 사용
        default_sl = tight_tp_sl['stop_loss']
        default_tp = tight_tp_sl['take_profit']
        
        # 🆕 v7.6: CONFIG 고정값 유지
    
    # ========== 로깅 ==========
    logger.info(f"📊 Rule-Based Validation for {symbol} {action.upper()}")
    
    # 🆕 v7.4: 트렌드 지지 조건 수 로깅
    trend_support_count = reverse_result.get('trend_support_count', 0)
    trend_supports = reverse_result.get('trend_supports_original', False)
    if trend_supports:
        logger.info(f"   🛡️ 4H Trend SUPPORTS original {action.upper()} signal ({trend_support_count}/4 conditions) - Reverse blocked")
    else:
        logger.info(f"   ⚠️ 4H Trend does NOT strongly support {action.upper()} ({trend_support_count}/4 conditions)")
    
    # 🆕 v7.4: Mean Reversion 및 Contrarian 로깅
    if mean_reversion['is_mean_reversion']:
        logger.info(f"   🎯 v7.4 Mean Reversion: {mean_reversion['reason']}")
        logger.info(f"      Confidence Boost: +{mean_reversion['confidence_boost']}%")
    
    if contrarian['should_contrarian']:
        logger.info(f"   🔄 v7.4 Contrarian: {contrarian['reason']}")
        logger.info(f"      Confidence: {contrarian['confidence']}%")
    
    # 🆕 v7.4: Symbol Filter 로깅
    if symbol_filter['status'] != 'NORMAL' and symbol_filter['status'] != 'NEUTRAL':
        logger.info(f"   📊 v7.4 Symbol Filter: {symbol_filter['status']} ({symbol_filter['reason']})")
        logger.info(f"      Size Multiplier: {symbol_filter['size_multiplier']}")
    
    # 반전 점수 로깅
    if reverse_score > 0 or reverse_signals > 0 or not trend_supports:
        reverse_emoji = "🔄" if reverse_result['should_reverse'] else ("⏸️" if reverse_result.get('should_hold', False) else "⚪")
        trend_status = "🛡️BLOCKED" if trend_supports else "⚠️POSSIBLE"
        logger.info(f"   {reverse_emoji} Reverse Score: {reverse_score}/8 (v7.4), Signals: {reverse_signals}/2 [{trend_status}]")
        for detail in reverse_result['details'][:5]:  # 상위 5개
            logger.info(f"      - {detail}")
    
    logger.info(f"   Risk Score: {risk_score}/8 {'⚠️ HIGH' if risk_score >= 8 else '✓ OK'}")
    for detail in risk_result['details'][:5]:
        logger.info(f"      - {detail}")
    logger.info(f"   Approval Score: {approval_score}/100 {'✓ PASS' if approval_score >= 50 else '✗ FAIL'}")  # 🆕 v7.6
    for detail in approval_result['details'][:5]:
        logger.info(f"      - {detail}")
    
    decision_emoji = {"approve": "✅", "reject": "❌", "modify": "⚠️", "reverse": "🔄", "hold": "⏸️", "mean_reversion": "🎯"}
    logger.info(f"   {decision_emoji.get(decision, '❓')} Decision: {decision.upper()} - {reason}")
    if decision == 'reverse':
        logger.info(f"   🔄 Action changed: {action.upper()} → {modified_action.upper()}")
    elif decision == 'mean_reversion':
        logger.info(f"   🎯 Mean Reversion entry: {action.upper()} (signal direction maintained)")
    elif modified_action == 'hold':
        logger.info(f"   ⏸️ Recommending HOLD due to ambiguous market conditions")
    
    return {
        'decision': decision,
        'modified_action': modified_action,
        'risk_score': risk_result,
        'approval_score': approval_result,
        'reverse_score': reverse_result,
        'reason': reason,
        'recommended_params': {
            'leverage': base_leverage,
            'position_percent': adjusted_position_pct,  # 🆕 v7.4: 동적 조정된 사이즈 사용
            'stop_loss': default_sl,
            'take_profit': default_tp,
            'current_price': current_price,
            'atr': atr_4h
        },
        # 🆕 v7.4 추가 정보
        'v74_mean_reversion': mean_reversion,
        'v74_contrarian': contrarian,
        'v74_symbol_filter': symbol_filter
    }


def ai_parameter_adjustment(symbol: str, action: str, rule_based_result: dict, market_data: dict) -> dict:
    """
    🆕 v7.3: AI 파라미터 조정
    🆕 v7.6: Leverage, Position Size는 CONFIG 고정값 사용, AI는 TP/SL만 조정
    🆕 v7.4: mean_reversion 결정 처리 추가
    
    Returns:
        dict: 최종 트레이딩 파라미터
    """
    from openai import OpenAI
    
    client = OpenAI(api_key=os.getenv("DEEPSEEK_API_KEY"), base_url="https://api.deepseek.com")
    if not client.api_key:
        logger.error("DeepSeek API key is missing")
        return rule_based_result['recommended_params']
    
    params = rule_based_result['recommended_params']
    decision = rule_based_result['decision']
    
    # 🆕 v7.6: CONFIG에서 고정값 가져오기
    config = get_symbol_config(symbol)
    fixed_leverage = config.get('leverage', 10)
    fixed_position_pct = config.get('position_size_percent', 30)
    
    # 🆕 v7.4: 동적 조정된 포지션 사이즈 사용
    adjusted_position_pct = params.get('position_percent', fixed_position_pct)
    
    # reject인 경우 AI 호출 안함
    if decision == 'reject':
        return {
            'decision': 'reject',
            'leverage': 0,
            'position_percent': 0,
            'stop_loss': 0,
            'take_profit': 0,
            'pl_ratio': 0,
            'reason': rule_based_result['reason']
        }
    
    # 🆕 v7.4: mean_reversion도 approve/modify처럼 처리
    if decision == 'mean_reversion':
        decision = 'approve'  # AI 호출을 위해 approve로 변경
    
    
    current_price = params['current_price']
    atr = params['atr']
    risk_score = rule_based_result['risk_score']['total_score']
    approval_score = rule_based_result['approval_score']['total_score']
    
    # 🆕 v7.7: 최신 Reflection 조회
    latest_reflection = get_latest_reflection(max_age_hours=24)
    reflection_context = ""
    if latest_reflection:
        # Reflection 텍스트를 요약하여 포함 (너무 길면 잘라냄)
        reflection_summary = latest_reflection[:1500] if len(latest_reflection) > 1500 else latest_reflection
        reflection_context = f"""
**RECENT PERFORMANCE REFLECTION (AI Analysis):**
{reflection_summary}

Use this reflection to inform your TP/SL adjustments. Consider the identified weaknesses and recommendations.
"""
    else:
        reflection_context = "**No recent reflection available.**"
    
    # 🆕 v7.7: Reflection을 포함한 프롬프트
    prompt = f"""You are a risk management AI for crypto futures trading.

**TASK:** Adjust ONLY Stop Loss and Take Profit prices based on the market conditions.

**SIGNAL INFO:**
- Symbol: {symbol}
- Action: {action.upper()}
- Current Price: ${current_price:.2f}
- ATR (4h): ${atr:.4f}

**PRE-VALIDATION RESULT (Rule-Based):**
- Decision: {decision.upper()}
- Risk Score: {risk_score}/8
- Approval Score: {approval_score}/100
- Reason: {rule_based_result['reason']}

{reflection_context}

**FIXED PARAMETERS (DO NOT CHANGE):**
- Leverage: {fixed_leverage}x (FIXED)
- Position Size: {fixed_position_pct}% (FIXED)

**DEFAULT TP/SL (adjust these):**
- Stop Loss: ${params['stop_loss']:.2f}
- Take Profit: ${params['take_profit']:.2f}

**ADJUSTMENT RULES:**
1. TP/SL should maintain R:R ratio >= 1.8
2. Stop Loss: 1.5-2.5x ATR from entry
3. Take Profit: At least 1.8x the SL distance
4. Consider nearby support/resistance levels
5. Apply lessons from the performance reflection if available

**OUTPUT FORMAT (JSON only):**
{{
    "stop_loss": <price>,
    "take_profit": <price>,
    "pl_ratio": <1.8-5.0>,
    "reason": "<brief adjustment rationale including reflection insights>"
}}

Return ONLY the JSON object."""

    try:
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {
                    "role": "system",
                    "content": "You are a risk management AI. Return ONLY valid JSON with adjusted TP/SL prices. Leverage and Position Size are FIXED - do not include them in your response."
                },
                {"role": "user", "content": prompt}
            ],
            response_format={'type': 'json_object'},
            temperature=0.1,
            max_tokens=500
        )
        
        ai_response = response.choices[0].message.content.strip()
        logger.info(f"AI Parameter Adjustment Response: {ai_response[:200]}")
        
        # JSON 파싱
        result = json.loads(ai_response)
        
        # 🆕 v7.6: Leverage, Position Size는 CONFIG 고정값 사용 (AI 응답 무시)
        leverage = fixed_leverage
        position_pct = fixed_position_pct
        
        # TP/SL만 AI에서 가져옴
        stop_loss = float(result.get('stop_loss', params['stop_loss']))
        take_profit = float(result.get('take_profit', params['take_profit']))
        
        # PL ratio 계산
        if action.lower() == 'buy':
            sl_distance = abs(current_price - stop_loss)
            tp_distance = abs(take_profit - current_price)
        else:
            sl_distance = abs(stop_loss - current_price)
            tp_distance = abs(current_price - take_profit)
        
        pl_ratio = tp_distance / sl_distance if sl_distance > 0 else 2.0
        pl_ratio = max(1.8, min(5.0, pl_ratio))
        
        return {
            'decision': decision,
            'leverage': leverage,
            'position_percent': position_pct,
            'stop_loss': stop_loss,
            'take_profit': take_profit,
            'pl_ratio': round(pl_ratio, 2),
            'reason': result.get('reason', rule_based_result['reason']),
            'risk_score': risk_score,
            'approval_score': approval_score
        }
        
    except Exception as e:
        logger.error(f"AI parameter adjustment failed: {e}")
        # 🆕 v7.6: 실패 시에도 CONFIG 고정값 사용
        if action.lower() == 'buy':
            sl_dist = abs(current_price - params['stop_loss'])
            tp_dist = abs(params['take_profit'] - current_price)
        else:
            sl_dist = abs(params['stop_loss'] - current_price)
            tp_dist = abs(current_price - params['take_profit'])
        
        default_pl_ratio = tp_dist / sl_dist if sl_dist > 0 else 2.0
        
        return {
            'decision': decision,
            'leverage': fixed_leverage,  # 🆕 v7.6: CONFIG 고정값
            'position_percent': fixed_position_pct,  # 🆕 v7.6: CONFIG 고정값
            'stop_loss': params['stop_loss'],
            'take_profit': params['take_profit'],
            'pl_ratio': round(default_pl_ratio, 2),
            'reason': f"Default params (AI failed): {rule_based_result['reason']}",
            'risk_score': risk_score,
            'approval_score': approval_score
        }

# ============ Reflection 기능 ============
def is_duplicate_trade_record(conn, symbol, action, trade_type, time_window_seconds=10):
    """
    중복 거래 기록 체크
    최근 N초 이내에 동일한 symbol, action, trade_type 조합이 있는지 확인
    
    Args:
        conn: DB 연결
        symbol: 심볼 (예: 'BTC/USDT')
        action: 액션 (예: 'buy', 'sell', 'close_position', 'monitor')
        trade_type: 거래 타입 (예: 'AI_VALIDATION', 'AI_MONITOR')
        time_window_seconds: 중복 체크 시간 범위 (초)
    
    Returns:
        bool: 중복이면 True, 아니면 False
    """
    try:
        c = conn.cursor()
        
        # 현재 시간에서 time_window_seconds 이전 시간 계산
        cutoff_time = (datetime.now() - timedelta(seconds=time_window_seconds)).isoformat()
        
        # 최근 기록 조회
        c.execute("""
            SELECT COUNT(*) FROM trades 
            WHERE symbol = ? 
            AND action = ? 
            AND trade_type = ?
            AND timestamp >= ?
        """, (symbol, action, trade_type, cutoff_time))
        
        count = c.fetchone()[0]
        
        if count > 0:
            logger.warning(
                f"⚠️ 중복 거래 기록 감지: {symbol} {action} {trade_type} "
                f"(최근 {time_window_seconds}초 내 {count}건 존재)"
            )
            return True
        
        return False
        
    except Exception as e:
        logger.error(f"중복 체크 오류: {e}")
        # 오류 발생 시 안전하게 False 반환 (기록 허용)
        return False

def is_duplicate_completed_trade(conn, symbol, entry_time, exit_time, time_window_seconds=5):
    """
    완료된 거래 중복 체크
    최근 N초 이내에 동일한 symbol, entry_price로 종료된 거래가 있는지 확인
    
    Args:
        conn: DB 연결
        symbol: 심볼
        entry_time: 진입 시간
        exit_time: 청산 시간
        time_window_seconds: 중복 체크 시간 범위 (초)
    
    Returns:
        bool: 중복이면 True, 아니면 False
    """
    try:
        c = conn.cursor()
        
        # entry_time과 exit_time을 문자열로 변환
        if isinstance(entry_time, datetime):
            entry_time_str = entry_time.isoformat()
        else:
            entry_time_str = entry_time
            
        if isinstance(exit_time, datetime):
            exit_time_str = exit_time.isoformat()
        else:
            exit_time_str = exit_time
        
        # 동일한 symbol, entry_time으로 최근 종료된 거래 확인
        c.execute("""
            SELECT COUNT(*) FROM completed_trades 
            WHERE symbol = ? 
            AND open_timestamp = ?
            AND close_timestamp >= datetime(?, '-' || ? || ' seconds')
        """, (symbol, entry_time_str, exit_time_str, time_window_seconds))
        
        count = c.fetchone()[0]
        
        if count > 0:
            logger.warning(
                f"⚠️ 중복 완료 거래 감지: {symbol} "
                f"(최근 {time_window_seconds}초 내 {count}건 존재)"
            )
            return True
        
        return False
        
    except Exception as e:
        logger.error(f"완료 거래 중복 체크 오류: {e}")
        # 오류 발생 시 안전하게 False 반환 (기록 허용)
        return False

def get_recent_trades(conn, symbol, num_trades=20):
    """특정 심볼의 최근 거래 내역 조회"""
    try:
        c = conn.cursor()
        c.execute("""
            SELECT * FROM trades 
            WHERE symbol = ?
            ORDER BY timestamp DESC
            LIMIT ?
        """, (symbol, num_trades))
        
        columns = [column[0] for column in c.description]
        return pd.DataFrame.from_records(data=c.fetchall(), columns=columns)
    
    except Exception as e:
        logger.error(f"Error fetching recent trades: {e}")
        return pd.DataFrame()

def calculate_performance(trades_df):
    """투자 성과 계산 - 개선 버전 (풍부한 통계 데이터 제공)"""
    if trades_df.empty:
        return {
            'total_trades': 0,
            'win_rate': 0,
            'avg_pnl_percent': 0,
            'total_pnl': 0,
            'best_trade': 0,
            'worst_trade': 0,
            'avg_holding_time': 0,
            'recent_trend': 'neutral',
            'risk_reward_ratio': 0
        }
    
    # completed_trades에서 실제 거래 성과 데이터 조회
    try:
        conn = get_db_connection()
        c = conn.cursor()
        
        # 최근 완료된 거래 조회 (최대 50건)
        c.execute("""
            SELECT 
                pnl_usdt,
                pnl_percent,
                is_win,
                holding_time_minutes,
                entry_price,
                exit_price,
                close_timestamp
            FROM completed_trades 
            WHERE symbol IN (SELECT DISTINCT symbol FROM trades WHERE timestamp >= datetime('now', '-7 days'))
            ORDER BY close_timestamp DESC
            LIMIT 50
        """)
        
        completed_trades = c.fetchall()
        conn.close()
        
        if not completed_trades:
            return {
                'total_trades': len(trades_df),
                'win_rate': 0,
                'avg_pnl_percent': 0,
                'total_pnl': 0,
                'best_trade': 0,
                'worst_trade': 0,
                'avg_holding_time': 0,
                'recent_trend': 'no_data',
                'risk_reward_ratio': 0
            }
        
        # 통계 계산
        total_completed = len(completed_trades)
        winning_trades = sum(1 for t in completed_trades if t[2] == 1)
        win_rate = (winning_trades / total_completed * 100) if total_completed > 0 else 0
        
        pnl_values = [t[0] for t in completed_trades if t[0] is not None]
        pnl_percents = [t[1] for t in completed_trades if t[1] is not None]
        
        total_pnl = sum(pnl_values) if pnl_values else 0
        avg_pnl_percent = sum(pnl_percents) / len(pnl_percents) if pnl_percents else 0
        best_trade = max(pnl_values) if pnl_values else 0
        worst_trade = min(pnl_values) if pnl_values else 0
        
        holding_times = [t[3] for t in completed_trades if t[3] is not None]
        avg_holding_time = sum(holding_times) / len(holding_times) if holding_times else 0
        
        # 최근 추세 분석 (최근 10거래)
        recent_10 = completed_trades[:10] if len(completed_trades) >= 10 else completed_trades
        recent_wins = sum(1 for t in recent_10 if t[2] == 1)
        recent_win_rate = (recent_wins / len(recent_10) * 100) if recent_10 else 0
        
        if recent_win_rate >= 60:
            recent_trend = 'improving'
        elif recent_win_rate <= 40:
            recent_trend = 'declining'
        else:
            recent_trend = 'stable'
        
        # Risk/Reward Ratio 계산
        winning_pnl = [t[0] for t in completed_trades if t[2] == 1 and t[0] is not None]
        losing_pnl = [abs(t[0]) for t in completed_trades if t[2] == 0 and t[0] is not None]
        
        avg_win = sum(winning_pnl) / len(winning_pnl) if winning_pnl else 0
        avg_loss = sum(losing_pnl) / len(losing_pnl) if losing_pnl else 1
        risk_reward_ratio = avg_win / avg_loss if avg_loss > 0 else 0
        
        return {
            'total_trades': total_completed,
            'win_rate': win_rate,
            'avg_pnl_percent': avg_pnl_percent,
            'total_pnl': total_pnl,
            'best_trade': best_trade,
            'worst_trade': worst_trade,
            'avg_holding_time': avg_holding_time,
            'recent_trend': recent_trend,
            'risk_reward_ratio': risk_reward_ratio,
            'recent_win_rate': recent_win_rate
        }
        
    except Exception as e:
        logger.error(f"Error calculating performance: {e}")
        return {
            'total_trades': 0,
            'win_rate': 0,
            'avg_pnl_percent': 0,
            'total_pnl': 0,
            'best_trade': 0,
            'worst_trade': 0,
            'avg_holding_time': 0,
            'recent_trend': 'error',
            'risk_reward_ratio': 0
        }

def generate_reflection(trades_df, current_market_data):
    """AI를 사용한 심층 반성 및 개선 사항 생성 - 개선 버전"""
    performance = calculate_performance(trades_df)
    
    client = OpenAI(api_key=os.getenv("DEEPSEEK_API_KEY"), base_url="https://api.deepseek.com")
    if not client.api_key:
        logger.error("OpenAI API key is missing or invalid.")
        return None
    
    # 최근 거래 데이터를 더 구조화해서 준비
    recent_trades_summary = "No recent trades"
    if not trades_df.empty and len(trades_df) > 0:
        try:
            # 최근 거래 요약 정보 추출
            recent_trades_list = []
            for idx, trade in trades_df.head(10).iterrows():
                trade_info = {
                    'symbol': trade.get('symbol', 'N/A'),
                    'action': trade.get('action', 'N/A'),
                    'timestamp': trade.get('timestamp', 'N/A'),
                    'ai_decision': trade.get('ai_decision', 'N/A')
                }
                recent_trades_list.append(trade_info)
            recent_trades_summary = json.dumps(recent_trades_list, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning(f"Error formatting recent trades: {e}")
            recent_trades_summary = "Error formatting trades data"
    
    # 계좌 잔고 변화 추세 분석
    try:
        conn = get_db_connection()
        c = conn.cursor()
        
        # 최근 24시간 잔고 변화
        c.execute("""
            SELECT total_balance, timestamp 
            FROM balance_history 
            WHERE timestamp >= datetime('now', '-1 day')
            ORDER BY timestamp ASC
        """)
        balance_history = c.fetchall()
        
        if len(balance_history) >= 2:
            initial_balance = balance_history[0][0]
            current_balance = balance_history[-1][0]
            balance_change = ((current_balance - initial_balance) / initial_balance * 100) if initial_balance > 0 else 0
            balance_trend = f"24h Balance Change: {balance_change:+.2f}% (${initial_balance:.2f} → ${current_balance:.2f})"
        else:
            balance_trend = "Insufficient balance history"
        
        conn.close()
    except Exception as e:
        logger.warning(f"Error fetching balance trend: {e}")
        balance_trend = "Balance trend unavailable"
    
    try:
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {
                    "role": "system",
                    "content": """You are an elite crypto trading analyst AI with deep expertise in technical analysis, risk management, and pattern recognition.

Your role is to provide ACTIONABLE, SPECIFIC, and INSIGHTFUL analysis that will help validate future trading signals. This reflection will be used as critical context for making real trading decisions.

CRITICAL: Your analysis must be:
1. SPECIFIC - Use exact numbers, percentages, and concrete observations
2. ACTIONABLE - Provide clear guidance that can be applied to signal validation
3. PATTERN-FOCUSED - Identify recurring mistakes or winning strategies
4. RISK-AWARE - Highlight risk management issues and improvements
5. MARKET-CONTEXTUAL - Consider current market conditions in your assessment"""
                },
                {
                    "role": "user",
                    "content": f"""Analyze the recent trading performance and provide a comprehensive reflection for improving future trading decisions.

**PERFORMANCE STATISTICS:**
- Total Completed Trades: {performance['total_trades']}
- Overall Win Rate: {performance['win_rate']:.1f}%
- Recent Win Rate (Last 10): {performance.get('recent_win_rate', 0):.1f}%
- Performance Trend: {performance['recent_trend'].upper()}
- Average PnL per Trade: {performance['avg_pnl_percent']:.2f}%
- Total PnL: ${performance['total_pnl']:.2f}
- Best Trade: ${performance['best_trade']:.2f}
- Worst Trade: ${performance['worst_trade']:.2f}
- Risk/Reward Ratio: {performance['risk_reward_ratio']:.2f}
- Average Holding Time: {performance['avg_holding_time']:.1f} minutes

**BALANCE TREND:**
{balance_trend}

**RECENT TRADES DETAIL:**
{recent_trades_summary}

**CURRENT MARKET SNAPSHOT:**
- Symbol: {current_market_data.get('symbol', 'N/A')}
- Current Price: ${current_market_data.get('current_price', 0):.2f}

Based on this data, provide a structured reflection with the following sections:

1. **PERFORMANCE ASSESSMENT** (2-3 sentences):
   - Is the win rate acceptable? Is there improvement or decline?
   - Is the risk/reward ratio healthy (should be >1.5)?
   - What does the PnL trend indicate?

2. **KEY STRENGTHS** (2-3 bullet points):
   - What trading patterns or strategies are working well?
   - Which market conditions lead to successful trades?

3. **CRITICAL WEAKNESSES** (2-3 bullet points):
   - What mistakes are being repeated?
   - Where is risk management failing?
   - What entry/exit timing issues exist?

4. **ACTIONABLE RECOMMENDATIONS** (3-4 specific points):
   - For ENTRY signals: What should AI look for or avoid?
   - For EXIT signals: When should positions be closed?
   - Risk management: How should stop-loss and take-profit be adjusted?
   - Market conditions: What conditions favor trading vs. holding?

5. **SIGNAL VALIDATION GUIDANCE** (2-3 points):
   - What technical indicators are most reliable in current conditions?
   - What are red flags that should trigger rejection?
   - What confluence of factors should increase confidence?

Keep your response concise but packed with specific, actionable insights. Use data from the statistics to support your points."""
                }
            ],
            temperature=0.3,
            max_tokens=2000
        )
        
        # AI 응답 추출 - 개선된 버전
        ai_response_text = extract_ai_response(response)
        
        if not ai_response_text:
            logger.error("Reflection 생성 실패: AI 응답이 비어있음")
            return None
            
        return ai_response_text
        
    except Exception as e:
        logger.error(f"Error generating reflection: {e}")
        return None


def save_reflection(reflection_text: str, performance: dict, symbols: list = None):
    """
    🆕 v7.7: 생성된 AI Reflection을 reflection_history 테이블에 저장
    
    Args:
        reflection_text: generate_reflection에서 생성된 종합 분석 텍스트
        performance: calculate_performance에서 반환된 성과 데이터
        symbols: 분석에 포함된 심볼 목록
    """
    try:
        conn = get_db_connection()
        c = conn.cursor()
        
        timestamp = datetime.now().isoformat()
        symbols_str = ','.join(symbols) if symbols else 'ALL'
        
        c.execute("""
            INSERT INTO reflection_history 
            (timestamp, reflection_text, total_trades, win_rate, recent_win_rate, 
             total_pnl, risk_reward_ratio, performance_trend, symbols_analyzed)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            timestamp,
            reflection_text,
            performance.get('total_trades', 0),
            performance.get('win_rate', 0),
            performance.get('recent_win_rate', 0),
            performance.get('total_pnl', 0),
            performance.get('risk_reward_ratio', 0),
            performance.get('recent_trend', 'unknown'),
            symbols_str
        ))
        
        conn.commit()
        conn.close()
        logger.info(f"✅ Reflection saved to history: {len(reflection_text)} chars")
        return True
        
    except Exception as e:
        logger.error(f"Error saving reflection: {e}")
        return False


def get_latest_reflection(max_age_hours: int = 24) -> str:
    """
    🆕 v7.7: 최신 AI Reflection 조회 (AI Validation에서 사용)
    
    Args:
        max_age_hours: 최대 조회 시간 범위 (시간)
        
    Returns:
        str: 최신 reflection 텍스트 또는 None
    """
    try:
        conn = get_db_connection()
        c = conn.cursor()
        
        c.execute("""
            SELECT reflection_text, timestamp, win_rate, total_pnl, performance_trend
            FROM reflection_history 
            WHERE timestamp >= datetime('now', '-' || ? || ' hours')
            ORDER BY timestamp DESC
            LIMIT 1
        """, (max_age_hours,))
        
        result = c.fetchone()
        conn.close()
        
        if result:
            reflection_text, timestamp, win_rate, total_pnl, trend = result
            logger.info(f"📖 Retrieved reflection from {timestamp}: WR={win_rate:.1f}%, PnL=${total_pnl:.2f}")
            return reflection_text
        else:
            logger.info("📭 No recent reflection found")
            return None
            
    except Exception as e:
        logger.error(f"Error getting latest reflection: {e}")
        return None


def trigger_reflection_generation(symbol: str = None):
    """
    🆕 v7.7: Reflection 생성을 트리거하는 함수
    완료된 거래 발생 시 또는 주기적으로 호출
    
    Args:
        symbol: 특정 심볼 (None이면 전체)
    """
    try:
        conn = get_db_connection()
        
        # 최근 거래 데이터 조회 (completed_trades에서)
        c = conn.cursor()
        c.execute("""
            SELECT symbol, side, entry_price, exit_price, pnl_usdt, pnl_percent, 
                   close_timestamp, is_win
            FROM completed_trades 
            ORDER BY close_timestamp DESC
            LIMIT 50
        """)
        
        trades_data = c.fetchall()
        
        if not trades_data or len(trades_data) < 3:
            logger.info("⏭️ Not enough completed trades for reflection generation")
            conn.close()
            return None
        
        # DataFrame 생성
        columns = ['symbol', 'action', 'entry_price', 'exit_price', 'pnl_usdt', 
                   'pnl_percent', 'timestamp', 'is_win']
        trades_df = pd.DataFrame(trades_data, columns=columns)
        
        # 현재 시장 데이터 (마지막 거래 심볼 기준)
        last_symbol = trades_df.iloc[0]['symbol'] if not trades_df.empty else 'BTC/USDT'
        market_data = {
            'symbol': last_symbol,
            'current_price': trades_df.iloc[0].get('exit_price', 0) if not trades_df.empty else 0
        }
        
        conn.close()
        
        # Reflection 생성
        reflection = generate_reflection(trades_df, market_data)
        
        if reflection:
            # 성과 데이터 계산
            performance = calculate_performance(trades_df)
            
            # Reflection 저장
            symbols = trades_df['symbol'].unique().tolist() if 'symbol' in trades_df.columns else []
            save_reflection(reflection, performance, symbols)
            
            logger.info(f"✅ Reflection generated and saved successfully")
            return reflection
        else:
            logger.warning("⚠️ Reflection generation returned empty")
            return None
            
    except Exception as e:
        logger.error(f"Error triggering reflection: {e}")
        return None


# ============ JSON 추출 헬퍼 함수 ============
def extract_json_from_text(text: str) -> str:
    """
    텍스트에서 JSON 추출 (여러 방법 시도)
    """
    if not text or not text.strip():
        return None
    
    # 방법 1: 전체가 JSON인 경우
    try:
        json.loads(text.strip())
        logger.debug("전체가 유효한 JSON")
        return text.strip()
    except json.JSONDecodeError:
        pass
    
    # 방법 2: ```json ... ``` 블록 찾기
    json_block_match = re.search(r'```json\s*\n(.*?)\n```', text, re.DOTALL)
    if json_block_match:
        extracted = json_block_match.group(1).strip()
        try:
            json.loads(extracted)
            logger.debug("```json 블록에서 JSON 추출")
            return extracted
        except json.JSONDecodeError:
            pass
    
    # 방법 3: ``` ... ``` 블록 찾기
    code_block_match = re.search(r'```\s*\n(.*?)\n```', text, re.DOTALL)
    if code_block_match:
        extracted = code_block_match.group(1).strip()
        try:
            json.loads(extracted)
            logger.debug("``` 블록에서 JSON 추출")
            return extracted
        except json.JSONDecodeError:
            pass
    
    # 방법 4: 첫 { 부터 마지막 } 까지 추출 (공격적 방법)
    first_brace = text.find('{')
    last_brace = text.rfind('}')
    if first_brace != -1 and last_brace != -1 and first_brace < last_brace:
        extracted = text[first_brace:last_brace+1]
        try:
            json.loads(extracted)
            logger.debug(f"첫/마지막 중괄호 사이에서 JSON 추출 (길이: {len(extracted)})")
            return extracted
        except json.JSONDecodeError:
            pass
    
    # 방법 5: { ... } 패턴 찾기 (가장 긴 것 우선)
    brace_matches = re.findall(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', text, re.DOTALL)
    if brace_matches:
        # 길이순으로 정렬 (긴 것이 완전한 JSON일 가능성 높음)
        brace_matches.sort(key=len, reverse=True)
        for match in brace_matches:
            try:
                json.loads(match.strip())
                logger.debug(f"{{...}} 패턴에서 JSON 추출 (길이: {len(match)})")
                return match.strip()
            except json.JSONDecodeError:
                continue
    
    logger.error("모든 JSON 추출 방법 실패")
    logger.debug(f"추출 실패한 텍스트 샘플 (처음 500자): {text[:500]}")
    return None

def create_default_hold_decision(reason: str) -> dict:
    """기본 hold 결정 생성"""
    return {
        "decision": "hold",
        "percentage": 0,
        "reason": reason,
        "exit_type": "none",
        "confidence": 0.0,
        "urgency": "none"
    }

def create_default_reject_decision(reason: str) -> dict:
    """기본 reject 결정 생성"""
    return {
        "decision": "reject",
        "modified_action": "hold",
        "percentage": 0,
        "reason": reason,
        "stop_loss_price": 0.0,
        "take_profit_price": 0.0,
        "pl_ratio": 0.0,
        "confidence": 0.0
    }

# ============ AI Position Monitoring (개선 버전) ============
def ai_monitor_position(symbol, position_info):
    """
    AI가 포지션을 모니터링하고 종료 여부 결정 - 개선 버전
    🆕 자동/수동 포지션 모두 모니터링
    Pydantic 검증 및 에러 처리 강화
    """
    
    # 🆕 포지션 타입 확인
    position_type = position_info.get('position_type', 'auto')
    type_indicator = "🤖" if position_type == 'auto' else "🔧"
    
    logger.info(f"{type_indicator} AI 모니터링 시작: {symbol} ({position_type.upper()} 포지션)")
    
    client = OpenAI(api_key=os.getenv("DEEPSEEK_API_KEY"), base_url="https://api.deepseek.com")
    if not client.api_key:
        logger.error("OpenAI API key is missing or invalid.")
        return None
    
    try:
        # 시장 데이터 수집
        market_data = get_market_data(symbol)
        if not market_data:
            logger.error(f"Failed to get market data for {symbol}")
            return create_default_hold_decision("시장 데이터 조회 실패")
        
        # 심볼 설정 정보 가져오기 (🆕 v7.3: 정규화된 심볼 사용)
        symbol_config = get_symbol_config(symbol)
        leverage = symbol_config.get('leverage', 10)
        position_size_percent = symbol_config.get('position_size_percent', 30)
        
        # 계좌 잔고 정보 가져오기
        try:
            balance_info = exchange.fetch_balance()
            total_margin = balance_info['USDT']['total']
            free_margin = balance_info['USDT']['free']
            used_margin = balance_info['USDT']['used']
        except Exception as e:
            logger.warning(f"잔고 정보 조회 실패: {e}")
            total_margin = 0
            free_margin = 0
            used_margin = 0
        
        # 포지션 정보
        entry_price = position_info['entry_price']
        current_price = market_data['current_price']
        side = position_info['side']
        amount = position_info['amount']
        stop_loss = position_info.get('stop_loss', 0)
        take_profit = position_info.get('take_profit', 0)
        
        # PnL 계산 (레버리지 반영)
        if side == 'buy':
            price_change_percent = ((current_price - entry_price) / entry_price) * 100
            distance_to_sl = ((current_price - stop_loss) / current_price) * 100 if stop_loss else 100
            distance_to_tp = ((take_profit - current_price) / current_price) * 100 if take_profit else 100
        else:  # sell
            price_change_percent = ((entry_price - current_price) / entry_price) * 100
            distance_to_sl = ((stop_loss - current_price) / current_price) * 100 if stop_loss else 100
            distance_to_tp = ((current_price - take_profit) / current_price) * 100 if take_profit else 100
        
        # 레버리지 적용 - 실제 수익률
        pnl_percent = price_change_percent * leverage
        
        # 🆕 v7.1 Peak Profit 업데이트
        peak_profit_info = update_peak_profit(symbol, pnl_percent, current_price)
        drawdown_from_peak = get_profit_drawdown(symbol, pnl_percent)
        
        # 포지션 크기 (USDT)
        position_size_usdt = amount * entry_price
        pnl_usdt = position_size_usdt * pnl_percent / 100
        
        # 포지션 보유 시간
        entry_time = position_info.get('entry_time', datetime.now())
        holding_time = (datetime.now() - entry_time).total_seconds() / 60  # 분 단위
        holding_hours = holding_time / 60
        
        # Technical Indicators
        df_15min = market_data['df_15min']
        df_hourly = market_data['df_hourly']
        df_4h = market_data['df_4h']
        
        # ATR 값 안전하게 추출 (NaN, 0, undefined 체크)
        def safe_get_atr(df, timeframe_name, current_price):
            """ATR을 안전하게 추출하는 헬퍼 함수"""
            try:
                if 'atr' not in df.columns:
                    logger.warning(f"⚠️ ATR column missing in {timeframe_name}")
                    return current_price * 0.002
                
                atr_value = df['atr'].iloc[-1]
                
                # NaN, None, 0 체크
                if pd.isna(atr_value) or atr_value is None or atr_value == 0:
                    logger.warning(f"⚠️ {symbol} ATR({timeframe_name}) is invalid: {atr_value}")
                    # 대체값: 최근 5개 캔들의 평균 범위
                    if len(df) >= 5:
                        recent_range = (df['high'].iloc[-5:] - df['low'].iloc[-5:]).mean()
                        if recent_range > 0:
                            logger.info(f"   → Using recent range as ATR: {recent_range:.4f}")
                            return recent_range
                    # 최종 대체값: 가격의 일정 비율
                    default_atr = current_price * 0.002  # 0.2%
                    logger.info(f"   → Using default ATR: {default_atr:.4f}")
                    return default_atr
                
                return atr_value
            except Exception as e:
                logger.error(f"Error getting ATR for {timeframe_name}: {e}")
                return current_price * 0.002
        
        # 각 타임프레임별 ATR 추출
        atr_15min = safe_get_atr(df_15min, '5m', current_price)
        atr_hourly = safe_get_atr(df_hourly, '1h', current_price)
        atr_4h = safe_get_atr(df_4h, '4h', current_price)
        
        # ATR 로깅 (디버깅용)
        logger.debug(f"{symbol} ATR values - 15m: {atr_15min:.4f}, 1h: {atr_hourly:.4f}, 4h: {atr_4h:.4f}")
        
        # 🆕 v7.5 ENHANCED: 조기 종료 신호 감지 (peak_pnl 추가)
        early_exit_signals = detect_early_reversal_signals(
            df_15min, df_hourly, df_4h, side, current_price, entry_price,
            pnl_percent=pnl_percent, holding_minutes=holding_time,
            peak_pnl=peak_profit_info['peak_pnl']  # 🆕 추가
        )
        
        # 🆕 v7.1 수익 되돌림 경고 로깅
        if peak_profit_info['peak_pnl'] > 2.0 and drawdown_from_peak > 25:
            logger.warning(f"🚨 수익 되돌림 경고: Peak {peak_profit_info['peak_pnl']:+.2f}% → Current {pnl_percent:+.2f}% (Drawdown: {drawdown_from_peak:.1f}%)")
        
        # 🆕 v7.3 지지부진 포지션 경고 로깅 (60분 이후에만 - 보호 기간 지난 후)
        if holding_time >= 60 and abs(pnl_percent) < 1.0:
            logger.warning(f"⏰ 지지부진 포지션: {holding_time:.0f}분 보유, {pnl_percent:+.2f}% 수익")
        elif holding_time < 60:
            protection_phase = "STRICT" if holding_time < 20 else "CAUTION" if holding_time < 40 else "WATCH"
            logger.info(f"🛡️ 진입 보호 활성: {protection_phase} ({holding_time:.1f}분 보유)")
        
        # 조기 종료 신호 로깅
        if early_exit_signals['should_exit']:
            logger.warning(f"🚨 조기 종료 신호 감지!")
            logger.warning(f"   긴급도: {early_exit_signals['urgency']}")
            logger.warning(f"   신뢰도: {early_exit_signals['confidence']:.1%}")
            logger.warning(f"   역전 점수: {early_exit_signals['reversal_score']}/12")
            for signal in early_exit_signals['signals']:
                logger.warning(f"   - {signal}")
            
            # 텔레그램 알림
            if ENABLE_TELEGRAM:
                urgency_emoji = "🔴" if early_exit_signals['urgency'] == 'immediate' else "🟡"
                signal_msg = f"""
{urgency_emoji} <b>추세 역전 조기 신호 감지</b>

<b>심볼:</b> {symbol}
<b>포지션:</b> {side.upper()}
<b>진입가:</b> ${entry_price:,.2f}
<b>현재가:</b> ${current_price:,.2f}
<b>수익률:</b> {pnl_percent:+.2f}%

<b>⚠️ 감지된 신호:</b>
"""
                for signal in early_exit_signals['signals'][:4]:  # 상위 4개만
                    signal_msg += f"• {signal}\n"
                
                signal_msg += f"""
<b>긴급도:</b> {early_exit_signals['urgency'].upper()}
<b>신뢰도:</b> {early_exit_signals['confidence']:.1%}
<b>역전 점수:</b> {early_exit_signals['reversal_score']}/20
<b>4H 추세지지:</b> {early_exit_signals.get('trend_support_4h', 0)}/8

💡 AI가 포지션 종료를 검토 중입니다...

⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
                """.strip()
                send_telegram_notification(signal_msg, 'warning' if early_exit_signals['urgency'] == 'immediate' else 'info')
        elif early_exit_signals['urgency'] == 'watch':
            logger.info(f"👀 약한 역전 신호 감지 (점수: {early_exit_signals['reversal_score']}/20)")
            for signal in early_exit_signals['signals']:
                logger.info(f"   - {signal}")
        
        json_template = """
{
    "decision": "hold",
    "percentage": 0,
    "reason": "Strong momentum continues, no reversal signals detected",
    "exit_type": "none",
    "confidence": 0.85,
    "urgency": "none"
}"""

        # 🆕 v7.5 ENHANCED: 강화된 수익 보호 경고 생성
        v71_alerts = generate_v75_profit_alerts(
            peak_profit_info['peak_pnl'],
            pnl_percent,
            holding_time,
            early_exit_signals.get('trend_support_4h', 0)
        )
        
        # 🆕 v7.5: Trailing Exit 정보 추가
        trailing_exit_info = early_exit_signals.get('trailing_exit', {})
        if trailing_exit_info.get('should_exit', False):
            v71_alerts.insert(0, f"🚨🚨 TRAILING PROTECTION TRIGGERED: {trailing_exit_info.get('reason', 'Exit recommended')}")
        
        # 절대적 drawdown 계산 (기존 로직 유지)
        absolute_drawdown = get_profit_drawdown_absolute(symbol, pnl_percent)
        
        # 추가 경고 (기존 로직 유지 - 중복 방지를 위해 조건 추가)
        if absolute_drawdown > 3.0 and holding_time >= 30 and not any('ABSOLUTE' in a for a in v71_alerts):
            v71_alerts.append(f"⚠️ v7.6 ABSOLUTE DROP: Lost {absolute_drawdown:.2f}% from peak")
        
        v71_alerts_text = chr(10).join(['  ' + alert for alert in v71_alerts]) if v71_alerts else '  ✅ No v7.5 alerts'

        prompt = f"""
You are an elite AI position manager monitoring an active {side.upper()} position for {symbol}. Your mission is to protect profits, minimize losses, and identify optimal exit points using multi-timeframe analysis.

**CRITICAL CONTEXT:**
This is a LEVERAGED position ({leverage}x) - small price movements have AMPLIFIED impact on P&L.

🚨 **EARLY REVERSAL DETECTION SYSTEM (v7.5 Anti-Noise):**
{'═' * 43}
→ Reversal Risk Score: {early_exit_signals['reversal_score']}/20
→ 4H Trend Support: {early_exit_signals.get('trend_support_4h', 0)}/8 {'🟢 STRONG' if early_exit_signals.get('trend_support_4h', 0) >= 5 else '🟡 MODERATE' if early_exit_signals.get('trend_support_4h', 0) >= 3 else '🔴 WEAK'}
→ Should Exit: {'YES ⚠️' if early_exit_signals['should_exit'] else 'NO ✅'}
→ Urgency Level: {early_exit_signals['urgency'].upper()}
→ Confidence: {early_exit_signals['confidence']:.1%}

→ Detected Signals ({len(early_exit_signals['signals'])}):
{chr(10).join(['  • ' + sig for sig in early_exit_signals['signals']]) if early_exit_signals['signals'] else '  • No reversal signals detected'}

💡 **INTERPRETATION (v7.5 Anti-Noise Filter):**
  • Score ≥ 12: IMMEDIATE exit (4h+1h 동시 역전 확인)
  • Score 9-11: EXIT SOON (1h 역전 + 4h 약화)
  • Score 6-8: WATCH closely (경고, 아직 홀드)
  • Score < 6: No significant reversal risk (노이즈 무시)

{'⚠️ WARNING: Multiple reversal signals detected! Consider this heavily in your decision.' if early_exit_signals['should_exit'] else '✅ No major reversal concerns detected. Focus on other technical factors.'}
{'═' * 43}

🆕 **v7.1 PROFIT TRACKING & ALERTS:**
{'═' * 43}
→ Peak Profit Tracking:
  • Peak P&L: {peak_profit_info['peak_pnl']:+.2f}%
  • Current P&L: {pnl_percent:+.2f}%
  • Drawdown from Peak: {drawdown_from_peak:.1f}%
  • Time Since Peak: {(datetime.now() - peak_profit_info['peak_time']).total_seconds() / 60:.0f} minutes

→ v7.1 Alerts:
{v71_alerts_text}
{'═' * 43}

═══════════════════════════════════════════
💼 **POSITION STATUS**
═══════════════════════════════════════════
→ Position Details:
  • Type: {position_type.upper()} ({type_indicator})
  • Direction: {side.upper()}
  • Entry Price: ${entry_price:,.2f}
  • Current Price: ${current_price:,.2f}
  • Position Size: {amount:.4f} ({position_size_usdt:,.2f} USDT)
  • Leverage: {leverage}x

→ Performance Metrics:
  • Price Change: {price_change_percent:+.2f}%
  • **LEVERAGED P&L: {pnl_percent:+.2f}%** ({pnl_usdt:+,.2f} USDT)
  • Holding Time: {holding_time:.0f} minutes ({holding_hours:.1f} hours)

→ Risk Management:
  • Stop Loss: {'$' + f'{stop_loss:,.2f}' if stop_loss else 'Not Set'} {'(' + f'{distance_to_sl:.2f}%' + ' away)' if stop_loss else ''}
  • Take Profit: {'$' + f'{take_profit:,.2f}' if take_profit else 'Not Set'} {'(' + f'{distance_to_tp:.2f}%' + ' away)' if take_profit else ''}

→ Account Context:
  • Total Balance: ${total_margin:,.2f} USDT
  • Free Balance: ${free_margin:,.2f} USDT
  • Position Impact on Account: {(pnl_usdt / total_margin * 100) if total_margin > 0 else 0:+.2f}%

═══════════════════════════════════════════
📊 **MULTI-TIMEFRAME TECHNICAL ANALYSIS**
═══════════════════════════════════════════

→ **15-MINUTE CHART (Immediate Momentum)**
═══════════════════════════════════════════
  Momentum Indicators:
  • RSI(14): {df_15min['rsi'].iloc[-1]:.2f} {'[OVERBOUGHT]' if df_15min['rsi'].iloc[-1] > 70 else '[OVERSOLD]' if df_15min['rsi'].iloc[-1] < 30 else '[NEUTRAL]'}
  • Stochastic %K: {df_15min['stoch_k'].iloc[-1]:.2f}, %D: {df_15min['stoch_d'].iloc[-1]:.2f}
  • Williams %R: {df_15min['williams_r'].iloc[-1]:.2f}
  • PPO: {df_15min['ppo'].iloc[-1]:.2f}

  Trend Analysis:
  • MACD: {df_15min['macd'].iloc[-1]:.2f}
  • MACD Signal: {df_15min['macd_signal'].iloc[-1]:.2f}
  • MACD Diff: {df_15min['macd_diff'].iloc[-1]:.2f} {'[BULLISH]' if df_15min['macd_diff'].iloc[-1] > 0 else '[BEARISH]'}
  • ADX: {df_15min['adx'].iloc[-1]:.2f} {'[STRONG TREND]' if df_15min['adx'].iloc[-1] > 25 else '[WEAK TREND]'}
  • DI+: {df_15min['di_plus'].iloc[-1]:.2f} vs DI-: {df_15min['di_minus'].iloc[-1]:.2f}

  Price Position:
  • Bollinger Upper: ${df_15min['bb_bbh'].iloc[-1]:.2f}
  • Bollinger Middle: ${df_15min['bb_bbm'].iloc[-1]:.2f}
  • Bollinger Lower: ${df_15min['bb_bbl'].iloc[-1]:.2f}
  • Current Position: {((current_price - df_15min['bb_bbl'].iloc[-1]) / (df_15min['bb_bbh'].iloc[-1] - df_15min['bb_bbl'].iloc[-1]) * 100):.0f}% of band
  • ATR(14): {atr_15min:.4f} (volatility indicator)

  Volume & Flow:
  • CMF(20): {df_15min['cmf'].iloc[-1]:.2f} {'[BUYING PRESSURE]' if df_15min['cmf'].iloc[-1] > 0 else '[SELLING PRESSURE]'}

→ **1-HOUR CHART (Medium-term Trend)**
═══════════════════════════════════════════
  Momentum:
  • RSI(14): {df_hourly['rsi'].iloc[-1]:.2f} {'[OVERBOUGHT]' if df_hourly['rsi'].iloc[-1] > 70 else '[OVERSOLD]' if df_hourly['rsi'].iloc[-1] < 30 else '[NEUTRAL]'}

  Trend:
  • MACD: {df_hourly['macd'].iloc[-1]:.2f}
  • MACD Signal: {df_hourly['macd_signal'].iloc[-1]:.2f}
  • ADX: {df_hourly['adx'].iloc[-1]:.2f} {'[STRONG]' if df_hourly['adx'].iloc[-1] > 25 else '[WEAK]'}
  • DI+: {df_hourly['di_plus'].iloc[-1]:.2f} vs DI-: {df_hourly['di_minus'].iloc[-1]:.2f}

  Price:
  • Bollinger Middle: ${df_hourly['bb_bbm'].iloc[-1]:.2f}
  • ATR: {atr_hourly:.4f}

  Volume:
  • CMF: {df_hourly['cmf'].iloc[-1]:.2f} {'[BUYING]' if df_hourly['cmf'].iloc[-1] > 0 else '[SELLING]'}

→ **4-HOUR CHART (Primary Trend)**
═══════════════════════════════════════════
  Momentum:
  • RSI(14): {df_4h['rsi'].iloc[-1]:.2f} {'[OVERBOUGHT]' if df_4h['rsi'].iloc[-1] > 70 else '[OVERSOLD]' if df_4h['rsi'].iloc[-1] < 30 else '[NEUTRAL]'}

  Trend:
  • MACD: {df_4h['macd'].iloc[-1]:.2f}
  • MACD Signal: {df_4h['macd_signal'].iloc[-1]:.2f}
  • ADX: {df_4h['adx'].iloc[-1]:.2f} {'[STRONG]' if df_4h['adx'].iloc[-1] > 25 else '[WEAK]'}
  • DI+: {df_4h['di_plus'].iloc[-1]:.2f} vs DI-: {df_4h['di_minus'].iloc[-1]:.2f}

  Volume:
  • CMF: {df_4h['cmf'].iloc[-1]:.2f} {'[BUYING]' if df_4h['cmf'].iloc[-1] > 0 else '[SELLING]'}

═══════════════════════════════════════════
🎯 **EXIT DECISION FRAMEWORK (v7.5 Anti-Noise)**
═══════════════════════════════════════════

**For {'LONG' if side == 'buy' else 'SHORT'} Position:**

🛡️ **v7.5 CRITICAL RULE: MULTI-TIMEFRAME CONFIRMATION REQUIRED**
- ❌ 15분봉 신호만으로 EXIT 금지 (단기 노이즈)
- ✅ 1시간봉 + 4시간봉 확인 필수
- ✅ 연속 2-3개 캔들 확인 필요 (단일 캔들 무시)
- ✅ 4시간봉 추세 지지 시 단기 역전 신호 무시

**Context for Decision Making:**
- Current ATR (5m): {atr_15min:.4f} - Use this as volatility baseline
- 4H Trend Support: {early_exit_signals.get('trend_support_4h', 0)}/8
- If 4H trend strong (≥5), ignore 15m/1h noise

⚠️ **IMMEDIATE EXIT SIGNALS (Close 100%) - REQUIRES 4H+1H CONFIRMATION:**
{'- 4h MACD deadcross + 1h DI- crosses above DI+' if side == 'buy' else '- 4h MACD golden cross + 1h DI+ crosses above DI-'}
{'- 4h price breaks below SMA20 (2+ candles) + 1h MACD confirmation' if side == 'buy' else '- 4h price breaks above SMA20 (2+ candles) + 1h MACD confirmation'}
{'- CMF negative on BOTH 4h AND 1h (confirmed money outflow)' if side == 'buy' else '- CMF positive on BOTH 4h AND 1h (confirmed money inflow)'}
- Reversal Score ≥ 12 with 4h trend weakening
- Stop loss being approached with 4h momentum against position

🔴 **STRONG EXIT SIGNALS (Close 75-100%) - REQUIRES 1H CONFIRMATION:**
- 4h trend weakening (ADX declining, was strong but now <20)
- 1h MACD crossover + DI crossover (both confirmed)
- Extended holding time (3h+) with 1h momentum fading
{'- 1h price below SMA20 for 2+ candles' if side == 'buy' else '- 1h price above SMA20 for 2+ candles'}

🟡 **PARTIAL EXIT SIGNALS (Close 25-50%):**
- 1h showing reversal hints, but 4h still supportive
- Price consolidating at key resistance/support on 4h chart
- Good profit achieved + 1h momentum fading (4h still okay)

✅ **HOLD SIGNALS (IGNORE SHORT-TERM NOISE):**
- 4H trend strongly intact (DI favorable, MACD aligned)
- 4H ADX >20 and stable/rising
- Price above/below 4H SMA20 (aligned with position)
- 15m/1h fluctuations are NORMAL - wait for 4h confirmation
- CMF positive on 4h (money flow supporting)
- Recent 15m RSI extremes without 1h/4h breakdown = NOISE

⏰ **TIME-BASED CONTEXT:**
- Short-term (<1 hour): Prioritize technical signals over time
- Medium-term (1-4 hours): Normal assessment window
- Extended (4-8 hours): Evaluate if momentum justifies continued holding
- Long-term (>8 hours): Question opportunity cost if minimal progress
- Very long (>24 hours): Seriously reconsider unless strong structural trend

🛡️ **EARLY POSITION PROTECTION (v7.5 - 수익 보호 중심!):**
{'═' * 43}
→ Current Holding Time: {holding_time:.0f} minutes
→ Protection Phase: {'🔒 STRICT PROTECTION (< 20 min)' if holding_time < 20 else '⚠️ CAUTION ZONE (20-40 min)' if holding_time < 40 else '👀 WATCH ZONE (40-60 min)' if holding_time < 60 else '✅ NORMAL MONITORING'}

**🆕 v7.5 핵심 원칙: 수익 보호 > 인내심!**
- 수익 3% 이상: 적극적으로 50% 확보 고려
- 수익 5% 이상: 전량 청산 적극 고려 (특히 30분 이상 보유 시)
- 손실 -5% 이상 + 4H 추세 약화: 빠른 손절

**MANDATORY RULES FOR EARLY POSITIONS:**
{'🔒 STRICT PROTECTION MODE (0-20 minutes):' if holding_time < 20 else '⚠️ CAUTION MODE (20-40 minutes):' if holding_time < 40 else '👀 WATCH MODE (40-60 minutes):' if holding_time < 60 else '✅ NORMAL MODE (60+ minutes):'}
{'''  • ONLY EXIT FOR: Severe loss (< -10%), catastrophic reversal (Score ≥ 12)
  • BUT 수익 5%+ 달성 시: 적극 청산 고려 (빠른 수익 확보!)
  • REASON: Position needs some time to develop, but don't miss quick profits.
  • v7.5 UPDATE: 고승률 > 고수익, 작은 수익도 챙기기!''' if holding_time < 20 else '''  • EXIT FOR: Loss < -8% OR Profit > +5% with any exhaustion OR Reversal Score ≥ 10
  • 수익 3%+: 50% 청산으로 수익 확보 고려
  • 수익 5%+: 전량 청산 적극 고려
  • v7.5 원칙: 수익이 손실로 전환되지 않도록!''' if holding_time < 40 else '''  • EXIT FOR: Loss < -5% OR Profit > +3% with exhaustion OR Score ≥ 8
  • 수익 권: 더 적극적인 청산 고려
  • 4H 추세가 약해지면 빠른 청산
  • v7.5 원칙: 60분 보유했으면 결과를 챙겨라!''' if holding_time < 60 else '''  • Normal monitoring + 적극적 수익 보호
  • 수익 2%+ 이면서 모멘텀 약화: 청산
  • 손실 -3% + 4H 추세 반전: 즉시 청산
  • v7.5 원칙: 기회비용 고려, 빠른 판단!'''}

💡 **v7.5 고승률 전략:**
  • 수익 5% 달성 = 목표 달성! (TP 도달 기다리지 마라)
  • 30분 이상 보유 + 수익 3%+ = 청산 고려
  • 손실 포지션은 4H 확인 후 빠른 손절
  • "더 벌 수 있을텐데"보다 "이만큼 벌었다" 우선!
{'═' * 43}
  • Short-term drawdowns during strong 4H trends often recover
{'═' * 43}

💰 **PROFIT/LOSS ASSESSMENT (Relative to Volatility):**
**For Loss Scenarios:**
- **Severe Loss (multiple ATR against position):** 
  Exit immediately unless extremely strong reversal signals on multiple timeframes
  
- **Significant Loss (1-2 ATR against position):** 
  Monitor very closely, exit if momentum doesn't reverse soon
  
- **Moderate Loss (less than 1 ATR):** 
  Acceptable if technical indicators support recovery
  Stop loss should be used if breakdown continues

**For Profit Scenarios:**
- **Minimal Profit (less than 1 ATR movement):**
  Hold unless clear reversal signals - still early in potential move
  
- **Moderate Profit (1-2 ATR movement):**
  Consider partial exit if reversal hints appear
  Full hold if momentum remains strong
  
- **Substantial Profit (2-3 ATR movement):**
  Strong candidate for partial profit-taking
  Watch for exhaustion signals
  
- **Exceptional Profit (>3 ATR movement):**
  Secure significant portion unless momentum extraordinarily strong
  Use trailing stops to protect gains

🎯 **v7.3 PROFIT ZONE RULES (중장기 관점 우선!):**
{'═' * 43}
**WHEN IN PROFIT, USE LONGER TIMEFRAMES FOR EXIT DECISIONS:**

→ Current P&L: {pnl_percent:+.2f}%
→ Profit Zone: {'🟢 IN PROFIT' if pnl_percent > 0 else '🔴 IN LOSS'}

{'🟢 **PROFITABLE POSITION - MEDIUM/LONG-TERM FOCUS:**' if pnl_percent > 0 else '🔴 **LOSING POSITION - SHORT-TERM SIGNALS MATTER:**'}
{'''  • 📊 PRIORITIZE 4H and 1H charts for exit decisions
  • ⚠️ IGNORE 15m noise - short-term pullbacks are NORMAL in profitable trades
  • 🔒 DO NOT EXIT based solely on 15m RSI/Stochastic extremes
  • ✅ EXIT ONLY WHEN: 4H shows clear trend reversal (DI crossover, MACD cross)
  • ✅ EXIT ONLY WHEN: 1H confirms with multiple bearish/bullish signals
  • 💡 A 15m RSI of 80+ during profit is often just healthy consolidation
  • 💡 Wait for 1H or 4H confirmation before taking action
  • 🎯 Let profits run - don't cut winners short on minor signals''' if pnl_percent > 0 else '''  • 📊 All timeframes matter for loss mitigation
  • ⚠️ 15m signals CAN trigger exit in losing positions
  • 🔒 Cut losses when momentum confirms against position
  • ✅ Consider exit if 15m + 1H both show adverse signals'''}

🆕 **v7.4 PATIENCE RULES - 장기 추세 여력 확인:**
{'''━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🔍 **BEFORE ANY EXIT, CHECK THESE FIRST:**

1. **4H 추세 여력 (Trend Remaining Room):**
   • BUY position: 4H RSI < 65 → 상승 여력 충분, HOLD
   • BUY position: 4H RSI 65-75 → 주의, 1H 확인 필요
   • BUY position: 4H RSI > 75 → 과매수 진입, EXIT 고려
   • SELL position: 4H RSI > 35 → 하락 여력 충분, HOLD
   • SELL position: 4H RSI 25-35 → 주의, 1H 확인 필요
   • SELL position: 4H RSI < 25 → 과매도 진입, EXIT 고려

2. **1H 모멘텀 확인:**
   • MACD 히스토그램이 포지션 방향과 일치 → HOLD
   • ADX > 25 + DI가 포지션 방향 지지 → HOLD (강한 트렌드)
   • Stochastic이 중립권 (30-70) → HOLD (조정 구간)

3. **15분봉 노이즈 vs 실제 반전 구분:**
   • 15m RSI 극단 + 1H/4H 트렌드 유지 → NOISE (무시!)
   • 15m RSI 극단 + 1H RSI도 극단 → 주의 (부분 청산 고려)
   • 15m + 1H + 4H 모두 극단 → EXIT (확정 반전)

⚠️ **핵심 원칙 (v7.5 고승률 중심):**
   • 수익 3%+ 달성하면 수익 확보 우선 고려!
   • 수익 5%+ 이면 "더 벌까" 보다 "확보하자" 우선!
   • 작은 수익이라도 손실보다 낫다!
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━''' if pnl_percent > 0 else '''• 손실 포지션은 모든 TF 고려하여 빠른 손절
• 손실 -5% + 4H 약화: 즉시 손절'''}

**🆕 v7.5 EXIT DECISION HIERARCHY (고승률 중심):**
  1. 🥇 수익 5%+ 달성 + 30분+ 보유 → EXIT 적극 고려!
  2. 🥈 수익 3%+ + 모멘텀 약화 → EXIT 50% 이상
  3. 🥉 4H Trend Reversal → EXIT (기존 규칙)
  4. ⚠️ 손실 -5% + 4H 약화 → 즉시 EXIT
{'═' * 43}

🆕 **v7.5 TIME-BASED RULES (60분 이후):**
- **60+ min holding with <1% profit:** 시장 기회비용 고려, 청산 우선
- **90+ min holding with any profit:** 적극 청산 권장
- **60+ min holding with loss:** 4H 확인 후 빠른 손절

⚠️ **NOTE:** v7.5는 60분 보호 기간 적용. 고승률을 위해 작은 수익도 확보!

🆕 **v7.5 PROFIT PROTECTION RULES (적극적 수익 보호!):**
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
**v7.5 핵심: 수익이 있을 때 지켜라!**

- **Current Profit ≥ 5%:** 전량 청산 적극 고려 (특히 30분+ 보유 시)
- **Current Profit ≥ 3%:** 50% 부분 청산 고려 (수익 확보)
- **Peak > 3% and Current < 1%:** EXIT 100% (수익 증발!)
- **Peak > 5% and Current < 2%:** EXIT 100% (큰 수익 손실!)
- **Drawdown from Peak > 40%:** EXIT 즉시 (아직 수익 중이라도)

✅ **v7.5 적극 청산 조건:**
- 수익 5%+ 달성 (목표 달성!)
- 30분+ 보유 + 수익 3%+ (충분히 벌었다!)
- 모멘텀 약화 시작 + 수익 권 (지금 나가라!)

❌ **청산 보류 조건:**
- 20분 미만 + 수익 <5% (아직 초반)
- 4H Trend Support ≥ 7 + 강한 모멘텀 (추세 진행 중)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

💡 **v7.5 KEY INSIGHT:** 
- 고승률 = 작은 수익 자주 챙기기!
- "더 벌 수 있을텐데" 생각하다 손실로 전환되면 최악!
- 수익 5% = 성공적인 트레이드! TP 기다리지 마라!
- 승률 42%를 60%로 올리려면 빠른 익절이 핵심!

═══════════════════════════════════════════
📋 **RESPONSE REQUIREMENTS**
═══════════════════════════════════════════

**CRITICAL INSTRUCTIONS:**
1. You MUST respond with ONLY a valid JSON object
2. Do NOT include any text before or after the JSON
3. Do NOT use markdown code blocks (no ```)
4. Follow this EXACT structure:

{json_template}

**Field Requirements:**
- decision: "hold", "close", or "partial_close"
- percentage: 0 for hold, 100 for full close, 25-75 for partial
- reason: **MUST be technical and specific, not based on arbitrary percentages**
- exit_type: "take_profit", "stop_loss", "trend_reversal", "risk_management", "time_stop", "profit_protection", "stagnation", or "none"
- confidence: 0.0 to 1.0 (lower if signals are mixed across timeframes)
- urgency: "immediate", "soon", "watch", or "none"

**Your reason MUST include:**
1. **Timeframe Analysis:** What each timeframe (5m/1h/4h) is telling you
2. **Trend Assessment:** Is trend intact, weakening, or reversing?
3. **Momentum Evaluation:** MACD, RSI, ADX readings and their direction
4. **Volume Confirmation:** CMF showing money flow direction
5. **Volatility Context:** How current move compares to ATR baseline
6. **Key Level Analysis:** Support/resistance, Bollinger band position
7. **Leveraged PnL Context:** Current profit/loss relative to volatility
8. **Divergence Check:** Any bearish/bullish divergences detected?
9. **v7.1/v7.6 Alerts Check:** Any stagnation, profit drawdown, or TIME+PROFIT concerns?

**DO NOT:**
- Make decisions based solely on reaching a percentage profit target
- Exit profitable positions just because "profit is high enough"
- Ignore strong technical momentum just to "secure profits"
- Use arbitrary rules like "always exit at X%"
- Let significant profits evaporate (check drawdown from peak!)
- **EXIT POSITIONS WITHIN FIRST 90 MINUTES** unless severe loss (< -15%) or catastrophic reversal (Score ≥ 15)
- **BE TRIGGER-HAPPY IN FIRST 90 MINUTES** - positions need time to develop!
- **EXIT based on 15m signals ALONE** - ALWAYS wait for 1H/4H confirmation!
- **React to short-term noise** - 15m RSI/MACD extremes are NOISE during strong 4H trends
- **CONFUSE loss management with profit protection** - if now in LOSS, it's loss mgmt!
- **Exit on time-based rules when 4H Trend Support ≥ 6** - strong trends deserve patience!

**DO:**
- Exit when **4H timeframe** shows clear reversal signals (MACD cross, DI cross)
- Hold strong 4H trends even with 15m/1h fluctuations
- Cut losses when **4H breakdown** is technically confirmed
- Let ATR guide what's "normal" vs "extended" movement
- **PRIORITIZE 4H > 1H > 15m** for exit decisions
- **REQUIRE multi-timeframe confirmation** (4H+1H) before exiting
- **CHECK 4H Trend Support score** - if ≥6, be very reluctant to exit
- **WAIT for 2-3 candle confirmation** before acting on reversal signals
- **RESPECT 90-MINUTE PROTECTION PERIOD** - give trades time to work
- **BE PATIENT** - most winning trades need 60-120+ minutes to reach targets
- **TRUST THE 4H TREND** - short-term noise does not invalidate medium-term thesis
- **DISTINGUISH profit protection vs loss management** - different rules apply!
- **GIVE EXTRA PATIENCE when 4H Trend Support ≥ 6** - even with drawdown!

Return ONLY the JSON object. Start with {{ and end with }}
"""

        # AI API 호출
        logger.info(f"포지션 모니터 시작 - {symbol} {side} (보유: {holding_hours:.1f}시간, PnL: {pnl_percent:+.2f}%)")
        
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {
                    "role": "system",
                    "content": """You are an elite crypto position manager specializing in leveraged futures trading with adaptive risk management.

CRITICAL RULES:
1. ONLY return valid JSON - no explanations, no reasoning, no markdown
2. Start your response with { and end with }
3. Follow the exact JSON schema provided
4. Be decisive but prudent - leveraged positions require careful management
5. Consider multi-timeframe analysis before making exit decisions
6. Account for leverage amplification in all profit/loss calculations

ADAPTIVE DECISION FRAMEWORK:
- Each asset has unique volatility - use ATR as baseline, not fixed percentages
- Exits should be driven by TECHNICAL SIGNALS, not arbitrary profit targets
- Let winning trades run until momentum shows exhaustion
- Cut losing trades when technical breakdown is confirmed
- Consider timeframe hierarchy: 4h trend > 1h momentum > 15m noise
- Volatility matters: 5% move in BTC ≠ 5% move in altcoin

🎯 CRITICAL - PROFIT ZONE RULES:
  4890	- When IN PROFIT: Use 4H and 1H for exit decisions, IGNORE 15m noise
- 15m signals alone should NEVER trigger exit of profitable positions
- Wait for 1H or 4H confirmation before closing winning trades
- Short-term pullbacks (15m) are NORMAL during profitable trends
- Only exit profits when LONGER TIMEFRAMES show clear reversal

🆕 v7.4 PATIENCE RULES (수익 포지션 인내심):
- BUY + 4H RSI < 65 → 상승 여력 충분, 절대 종료하지 마라!
- SELL + 4H RSI > 35 → 하락 여력 충분, 절대 종료하지 마라!
- 15m RSI 극단값은 1H/4H 확인 없이 EXIT 금지
- "조금 더 기다렸으면" 후회를 최소화하라!
- 수익 중 4H 트렌드가 살아있으면 HOLD!

PRIORITY OBJECTIVES:
1. Protect Capital: Exit when multiple timeframes show reversal
2. Maximize Profits: Hold while momentum and trend remain strong
3. Manage Risk: Balance profit preservation vs. opportunity cost
4. Respect Market Structure: Support/resistance, trendlines, key levels
5. Adapt to Volatility: High ATR assets need wider tolerance

DECISION PHILOSOPHY:
"Don't exit because you hit a profit target. Exit because the market 
tells you the move is over. Don't hold a loser hoping. Exit when 
technical breakdown is clear. Be patient with winners, ruthless with losers."

Your response must be a single JSON object."""
                },
                {"role": "user", "content": prompt}
            ],
            response_format={'type': 'json_object'},
            temperature=0.1,
            max_tokens=1500
        )
        
        # 1. 응답 추출 - 개선된 버전
        ai_response_text = extract_ai_response(response)
        
        if not ai_response_text or not ai_response_text.strip():
            logger.error("AI 응답이 비어있음 (content와 reasoning_content 모두 확인)")
            return create_default_hold_decision("AI 응답 없음")

        
        logger.info(f"AI 응답 길이: {len(ai_response_text)} 문자")
        logger.debug(f"AI 응답 내용: {ai_response_text[:500]}")
        
        # 2. JSON 추출
        json_str = extract_json_from_text(ai_response_text)
        if not json_str:
            logger.error("JSON 추출 실패")
            logger.error(f"전체 AI 응답: {ai_response_text}")
            return create_default_hold_decision("JSON 파싱 실패")
        
        logger.debug(f"추출된 JSON: {json_str}")
        
        # 3. JSON 파싱
        try:
            parsed_json = json.loads(json_str)
            logger.debug(f"JSON 파싱 성공: {parsed_json}")
        except json.JSONDecodeError as e:
            logger.error(f"JSON decode 실패: {e}")
            logger.error(f"시도한 JSON: {json_str}")
            return create_default_hold_decision(f"JSON 형식 오류: {str(e)}")
        
        # 4. Pydantic 검증
        try:
            decision = PositionExitDecision.model_validate(parsed_json)
            result = decision.model_dump()
            
            # 🆕 v7.4: 진입 초반 보호 로직 (90분까지 확장, 4H Trend Support 고려)
            original_decision = result['decision']
            
            # 4H Trend Support 점수 가져오기
            trend_support_4h = early_exit_signals.get('trend_support_4h', 0)
            
            if result['decision'] in ['close', 'partial_close']:
                # 🆕 v7.5: 수익 보호 최우선! 수익 5%+ 이면 청산 허용
                is_quick_profit = pnl_percent >= V75_EARLY_PROFIT_EXIT  # 5%+
                is_good_profit_quick = pnl_percent >= V75_PROFIT_PROTECTION_THRESHOLD and holding_time >= V75_QUICK_PROFIT_TIME  # 3%+ and 30분+
                
                if is_quick_profit or is_good_profit_quick:
                    logger.info(f"💰 v7.5 수익 보호: {pnl_percent:+.2f}% 수익 확보 허용!")
                    # 청산 결정 유지 (보호 무시)
                    result['exit_type'] = 'profit_protection'
                
                # 🆕 v7.5: 20분 이내: 엄격한 보호 (수익 5%+ 제외)
                elif holding_time < 20:
                    # 허용 조건: 심각한 손절(-10% 이상 손실) 또는 극단적 역전(점수 12 이상) 또는 수익 5%+
                    loss_threshold = -10.0 if trend_support_4h < 6 else -15.0
                    reversal_threshold = 12 if trend_support_4h < 6 else 15
                    
                    is_severe_loss = pnl_percent <= loss_threshold
                    is_catastrophic_reversal = early_exit_signals['reversal_score'] >= reversal_threshold
                    
                    if not (is_severe_loss or is_catastrophic_reversal):
                        logger.warning(f"🛡️ v7.5 초반 보호 (< 20분): {result['decision']} → HOLD")
                        logger.warning(f"   보유: {holding_time:.1f}분, PnL: {pnl_percent:+.2f}%, Reversal: {early_exit_signals['reversal_score']}")
                        result['decision'] = 'hold'
                        result['percentage'] = 0
                        result['reason'] = f"🛡️ v7.5 STRICT (< 20min): {original_decision} blocked. PnL: {pnl_percent:+.2f}%"
                        result['exit_type'] = 'none'
                        result['urgency'] = 'none'
                
                # 🆕 v7.5: 20-40분: 주의 구간 (수익 3%+ or 손실 -8% 허용)
                elif holding_time < 40:
                    loss_threshold = -8.0 if trend_support_4h < 6 else -10.0
                    reversal_threshold = 10 if trend_support_4h < 6 else 12
                    
                    is_significant_loss = pnl_percent <= loss_threshold
                    is_good_profit = pnl_percent >= 3.0  # v7.5: 3%+ 수익 허용
                    is_strong_reversal = early_exit_signals['reversal_score'] >= reversal_threshold
                    
                    if not (is_significant_loss or is_good_profit or is_strong_reversal):
                        logger.warning(f"🛡️ v7.5 주의 구간 (20-40분): {result['decision']} → HOLD")
                        result['decision'] = 'hold'
                        result['percentage'] = 0
                        result['reason'] = f"🛡️ v7.5 CAUTION (20-40min): {original_decision} blocked. PnL: {pnl_percent:+.2f}%"
                        result['exit_type'] = 'none'
                        result['urgency'] = 'watch'
                
                # 🆕 v7.5: 40-60분: 가벼운 주의 (수익 2%+ or 손실 -5% 허용)
                elif holding_time < 60:
                    loss_threshold = -5.0 if trend_support_4h < 6 else -8.0
                    reversal_threshold = 8 if trend_support_4h < 6 else 10
                    
                    is_moderate_loss = pnl_percent <= loss_threshold
                    is_any_profit = pnl_percent >= 2.0  # v7.5: 2%+ 수익 허용
                    is_moderate_reversal = early_exit_signals['reversal_score'] >= reversal_threshold
                    
                    if not (is_moderate_loss or is_any_profit or is_moderate_reversal):
                        logger.warning(f"🛡️ v7.5 관찰 구간 (40-60분): {result['decision']} → HOLD")
                        result['decision'] = 'hold'
                        result['percentage'] = 0
                        result['reason'] = f"👀 v7.5 WATCH (40-60min): {original_decision} blocked. PnL: {pnl_percent:+.2f}%"
                        result['exit_type'] = 'none'
                        result['urgency'] = 'watch'
                
                # 🆕 v7.5: 60분 이후 - 정상 모니터링 (적극적 수익 보호)
                elif holding_time >= 60 and pnl_percent > 0 and result['decision'] in ['close', 'partial_close']:
                    try:
                        # v7.5: 더 적극적인 수익 보호
                        skip_patience = False
                        skip_reason = ""
                        
                        # 조건 1: 수익 2%+ 이면서 모멘텀 약화
                        if pnl_percent >= 2.0 and early_exit_signals['reversal_score'] >= 6:
                            skip_patience = True
                            skip_reason = f"v7.5 수익 보호: {pnl_percent:+.2f}% + 모멘텀 약화"
                        
                        # 조건 2: peak > 3% + 현재 < 1% (기존 5%/2% → 3%/1%로 낮춤)
                        elif peak_profit_info['peak_pnl'] > 3.0 and pnl_percent < 1.0:
                            skip_patience = True
                            skip_reason = f"v7.5 수익 보호: Peak {peak_profit_info['peak_pnl']:+.2f}% → 현재 {pnl_percent:+.2f}%"
                        
                        # 조건 3: drawdown > 40% (기존 60% → 40%로 낮춤)
                        elif drawdown_from_peak > 40 and peak_profit_info['peak_pnl'] > 2.0:
                            skip_patience = True
                            skip_reason = f"v7.5 수익 보호: Peak에서 {drawdown_from_peak:.1f}% drawdown"
                        
                        if skip_patience:
                            logger.info(f"💰 v7.5 수익 보호 발동: {skip_reason}")
                            result['reason'] = f"💰 {skip_reason}. " + result['reason'][:150]
                            result['exit_type'] = 'profit_protection'
                        
                        # 조건 3: holding 120분+ + peak > 5% + drawdown > 50% (기존 90분/3%/40% → 완화)
                        elif holding_time >= 120 and peak_profit_info['peak_pnl'] > 5.0 and drawdown_from_peak > 50:
                            skip_patience = True
                            skip_reason = f"v7.6 장기 보유 수익 보호: {holding_time:.0f}분 보유, 50%+ drawdown"
                        
                        # 조건 4: 절대적 drawdown > 5% (기존 3% → 5%로 상향)
                        absolute_dd = get_profit_drawdown_absolute(symbol, pnl_percent)
                        if absolute_dd > 5.0 and holding_time >= 90:
                            skip_patience = True
                            skip_reason = f"v7.6 절대적 drawdown 보호: {absolute_dd:.2f}% 하락"
                        
                        if skip_patience:
                            logger.warning(f"🚨 v7.6 수익 보호 발동 - 인내심 로직 무시")
                            logger.warning(f"   이유: {skip_reason}")
                            logger.warning(f"   Peak: {peak_profit_info['peak_pnl']:+.2f}%, Current: {pnl_percent:+.2f}%")
                            
                            # 종료 결정 유지 + 이유 추가
                            result['reason'] = f"🚨 {skip_reason}. 4H 추세 여력과 무관하게 수익 보호 우선. " + result['reason'][:200]
                            result['exit_type'] = 'profit_protection'
                            result['urgency'] = 'immediate' if skip_patience else 'soon'
                            
                            if ENABLE_TELEGRAM:
                                send_telegram_notification(
                                    f"🚨 <b>v7.6 수익 보호 발동</b>\n\n"
                                    f"<b>심볼:</b> {symbol}\n"
                                    f"<b>포지션:</b> {side.upper()}\n"
                                    f"<b>Peak 수익:</b> {peak_profit_info['peak_pnl']:+.2f}%\n"
                                    f"<b>현재 수익:</b> {pnl_percent:+.2f}%\n"
                                    f"<b>Drawdown:</b> {drawdown_from_peak:.1f}%\n"
                                    f"<b>보유 시간:</b> {holding_time:.0f}분\n\n"
                                    f"💡 {skip_reason}\n"
                                    f"4H 추세 지지와 무관하게 수익 보호!",
                                    'warning'
                                )
                        else:
                            # 기존 인내심 로직 실행
                            # 시장 데이터 가져오기
                            market_data = get_market_data(symbol)
                            if market_data and 'df_hourly' in market_data and 'df_4h' in market_data:
                                position_side = side  # 'long' or 'short'
                                
                                # 추세 여력 판단
                                patience_result = check_trend_remaining_room(
                                    market_data['df_hourly'],
                                    market_data['df_4h'],
                                    position_side,
                                    pnl_percent
                                )
                                
                                # 로깅
                                logger.info(f"🔍 v7.4 인내심 점검: {patience_result['reason']}")
                                for detail in patience_result['details'][:5]:
                                    logger.info(f"   {detail}")
                                
                                # 추세 여력이 충분하면 종료 차단
                                if patience_result['block_exit']:
                                    logger.warning(f"🔒 인내심 로직 발동: {result['decision']} → HOLD")
                                    logger.warning(f"   인내심 점수: {patience_result['patience_score']}/10")
                                    logger.warning(f"   수익률: {pnl_percent:+.2f}% | 4H/1H 추세 여력 충분")
                                    
                                    result['decision'] = 'hold'
                                    result['percentage'] = 0
                                    result['reason'] = f"🔒 PATIENCE OVERRIDE: 4H/1H 추세 여력 충분 (점수: {patience_result['patience_score']}/10). 원래 결정: {original_decision}. {patience_result['reason']}"
                                    result['exit_type'] = 'none'
                                    result['urgency'] = 'watch'
                                    
                                    if ENABLE_TELEGRAM:
                                        send_telegram_notification(
                                            f"🔒 <b>인내심 로직 발동</b>\n\n"
                                            f"<b>심볼:</b> {symbol}\n"
                                            f"<b>포지션:</b> {side.upper()}\n"
                                            f"<b>수익률:</b> {pnl_percent:+.2f}%\n"
                                            f"<b>인내심 점수:</b> {patience_result['patience_score']}/10\n\n"
                                            f"<b>원래 결정:</b> {original_decision.upper()}\n"
                                            f"<b>변경 결정:</b> HOLD\n\n"
                                            f"💡 4H/1H 추세 여력이 남아있습니다.\n"
                                            f"더 큰 수익을 위해 기다립니다!",
                                            'info'
                                        )
                                elif patience_result['has_room'] and result['decision'] == 'close':
                                    # 여력이 있지만 완전 차단은 아님 → partial_close로 변경
                                    logger.warning(f"⚠️ 인내심 로직: close → partial_close (여력 일부 남음)")
                                    result['decision'] = 'partial_close'
                                    result['percentage'] = 50
                                    result['reason'] = f"⚠️ PATIENCE ADJUSTMENT: 일부 추세 여력 남음 (점수: {patience_result['patience_score']}/10). 50% 부분 청산. {result['reason'][:100]}"
                    except Exception as patience_error:
                        logger.error(f"인내심 로직 오류: {patience_error}")
            
            logger.info(
                f"✅ 포지션 모니터 결정: {result['decision']} "
                f"({result['percentage']}% / 신뢰도: {result['confidence']:.2f} / "
                f"긴급도: {result['urgency']})"
                f"{' [보호 발동]' if original_decision != result['decision'] else ''}"
            )
            logger.info(f"결정 이유: {result['reason'][:200]}...")
            
            # DB에 모니터링 기록 저장 (중복 체크 추가)
            conn = get_db_connection()
            c = conn.cursor()
            timestamp = datetime.now().isoformat()
            
            # 🔒 중복 기록 방지: 최근 10초 내 동일 기록 확인
            if not is_duplicate_trade_record(conn, symbol, 'monitor', 'AI_MONITOR', time_window_seconds=10):
                c.execute("""INSERT INTO trades 
                             (timestamp, symbol, trade_type, ai_decision, action, percentage, reason, 
                              entry_price, current_price, confidence, exit_type, urgency) 
                             VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                          (timestamp, symbol, 'AI_MONITOR', result['decision'], 'monitor', result['percentage'], 
                           result['reason'], entry_price, current_price, result['confidence'], 
                           result['exit_type'], result['urgency']))
                conn.commit()
                logger.info(f"✅ AI 모니터링 기록 저장 완료: {symbol}")
            else:
                logger.info(f"⏭️  중복 기록 스킵: {symbol} AI_MONITOR")
            
            conn.close()
            
            return result
            
        except ValidationError as e:
            logger.error(f"Pydantic 검증 실패:")
            for error in e.errors():
                logger.error(f"  - 필드 {error['loc']}: {error['msg']}")
            logger.error(f"검증 실패한 데이터: {parsed_json}")
            return create_default_hold_decision(f"데이터 검증 실패: {str(e.errors()[0]['msg'])}")
    
    except Exception as e:
        logger.error(f"포지션 모니터 오류: {e}", exc_info=True)
        return create_default_hold_decision(f"시스템 오류: {str(e)}")

def execute_position_exit(symbol, decision):
    """
    포지션 종료 실행
    🆕 개선: 모든 유저의 포지션 종료 + TP/SL 자동 취소
    """
    try:
        position = current_positions.get(symbol)
        if not position:
            logger.warning(f"No position found for {symbol}")
            return False
        
        # 🆕 포지션 타입 확인
        position_type = position.get('position_type', 'auto')
        type_indicator = "🤖" if position_type == 'auto' else "🔧"
        
        logger.info(f"{type_indicator} {symbol} 포지션 종료 실행 중... ({position_type.upper()})")
        
        # 🆕 모든 유저에 대해 포지션 종료 실행
        success_count = 0
        failed_users = []
        
        for user_id, user_exchange in exchanges.items():
            user_name = USER_CONFIGS[user_id]['name']
            
            try:
                # 해당 유저의 포지션 확인
                positions = user_exchange.fetch_positions([symbol])
                active_position = None
                
                for pos in positions:
                    if float(pos.get('contracts', 0)) != 0:
                        active_position = pos
                        break
                
                if not active_position:
                    logger.info(f"[{user_name}] {symbol} 포지션 없음 (AI 모니터링)")
                    continue
                
                # 포지션 정보
                contracts = float(active_position['contracts'])
                side = active_position['side']
                
                # 종료할 수량 계산
                if decision['decision'] == 'close':
                    exit_amount = abs(contracts)
                elif decision['decision'] == 'partial_close':
                    exit_amount = abs(contracts) * (decision['percentage'] / 100)
                else:
                    continue
                
                # 포지션 청산
                close_side = 'sell' if side == 'long' else 'buy'
                close_order = user_exchange.create_market_order(symbol, close_side, exit_amount)
                
                logger.info(f"[{user_name}] {type_indicator} AI 포지션 청산: {symbol} {close_side} {exit_amount:.6f}")
                
                # 🆕 전체 종료 시 TP/SL 자동 취소
                if decision['decision'] == 'close':
                    cancelled = cancel_symbol_orders(user_exchange, symbol, user_name)
                    if cancelled > 0:
                        logger.info(f"[{user_name}] 🗑️ AI 청산으로 TP/SL 주문 {cancelled}개 자동 취소")
                
                success_count += 1
                
            except Exception as e:
                logger.error(f"[{user_name}] AI 포지션 청산 실패: {str(e)}")
                failed_users.append(user_name)
        
        # 결과 로깅
        total_users = len(exchanges)
        logger.info(f"{type_indicator} AI 청산 완료: {success_count}/{total_users}명 성공")
        if failed_users:
            logger.warning(f"⚠️ 실패한 유저: {', '.join(failed_users)}")
        
        # Primary User로 완료된 거래 DB 기록 (🆕 v7.8: 바이낸스 실제 데이터)
        try:
            if decision['decision'] == 'close':
                # 전체 종료인 경우
                record_completed_trade_with_binance(symbol, position, 
                                                    close_reason=decision.get('exit_type', 'ai_exit'))
                logger.info(f"✅ Completed trade recorded for {symbol} ({position_type.upper()})")
                del current_positions[symbol]
                clear_peak_profit(symbol)
            else:
                # 부분 종료인 경우
                partial_position = position.copy()
                partial_position['amount'] = position['amount'] * (decision['percentage'] / 100)
                record_completed_trade_with_binance(symbol, partial_position,
                                                    close_reason='partial_' + decision.get('exit_type', 'exit'))
                logger.info(f"✅ Partial trade recorded for {symbol} ({position_type.upper()})")
                current_positions[symbol]['amount'] -= partial_position['amount']
                
        except Exception as e:
            logger.error(f"Failed to record completed trade: {e}")
            # 오류가 나도 포지션은 정리
            if decision['decision'] == 'close' and symbol in current_positions:
                del current_positions[symbol]
                clear_peak_profit(symbol)  # 🆕 v7.1 peak profit 기록 삭제
            elif decision['decision'] == 'partial_close' and symbol in current_positions:
                current_positions[symbol]['amount'] -= position['amount'] * (decision['percentage'] / 100)
        
        # 텔레그램 알림
        if ENABLE_TELEGRAM:
            message = f"""
{type_indicator} <b>AI Position Exit (Multi-User)</b>

<b>Type:</b> {position_type.upper()} 포지션
<b>Symbol:</b> {symbol}
<b>Decision:</b> {decision['decision'].upper()}
<b>Exit Type:</b> {decision['exit_type']}
<b>성공:</b> {success_count}/{total_users}명
<b>Reason:</b> {decision['reason']}
<b>Urgency:</b> {decision['urgency']}
<b>Confidence:</b> {decision['confidence']:.1%}

⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
            """.strip()
            send_telegram_notification(message, 'high' if decision['urgency'] == 'immediate' else 'normal')
        
        return success_count > 0
        
    except Exception as e:
        logger.error(f"Error executing position exit for {symbol}: {e}")
        return False

def ai_monitoring_cycle(skip_sync=False):
    """
    AI 모니터링 주기 실행
    🆕 개선: 자동/수동 포지션 모두 모니터링
    
    Args:
        skip_sync: True면 동기화 건너뛰기 (이미 sync된 경우)
    """
    global current_positions
    
    logger.info("=== AI Position Monitoring Cycle Start ===")
    logger.info(f"⏰ Monitoring interval: {AI_MONITOR_INTERVAL} minutes")
    logger.info(f"📊 Current positions in memory: {len(current_positions)}")
    
    # 🔄 실제 거래소 포지션과 동기화 (skip_sync가 False일 때만)
    if not skip_sync:
        sync_count = sync_positions_from_exchange()
        logger.info(f"🔄 Synchronized positions: {sync_count}")
    else:
        logger.info("🔄 Sync skipped (already synced)")
    
    if not current_positions:
        logger.info("No positions to monitor after sync")
        return 0, []
    
    # 🆕 포지션 타입별 카운트
    auto_positions = {k: v for k, v in current_positions.items() if v.get('position_type', 'auto') == 'auto'}
    manual_positions = {k: v for k, v in current_positions.items() if v.get('position_type', 'auto') == 'manual'}
    
    logger.info(f"  - 자동(AI) 포지션: {len(auto_positions)}개")
    logger.info(f"  - 수동 포지션: {len(manual_positions)}개")
    
    monitored_count = 0
    exit_decisions = []
    
    for symbol, position in current_positions.copy().items():
        # AI 모니터링이 활성화된 심볼인지 확인 (🆕 v7.3: 정규화된 심볼 사용)
        if not get_symbol_config(symbol).get('ai_monitoring', True):
            continue
        
        position_type = position.get('position_type', 'auto')
        type_indicator = "🤖" if position_type == 'auto' else "🔧"
        
        logger.info(f"{type_indicator} Monitoring position: {symbol} ({position_type.upper()})")
        
        # AI 모니터링 실행
        decision = ai_monitor_position(symbol, position)
        
        if decision:
            monitored_count += 1
            
            # 종료 결정인 경우
            if decision['decision'] in ['close', 'partial_close']:
                # 신뢰도와 긴급도 확인
                if decision['confidence'] >= 0.6 or decision['urgency'] == 'immediate':
                    success = execute_position_exit(symbol, decision)
                    if success:
                        exit_decisions.append({
                            'symbol': symbol,
                            'position_type': position_type,  # 🆕
                            'decision': decision['decision'],
                            'reason': decision['reason']
                        })
                else:
                    logger.info(f"{type_indicator} Exit decision for {symbol} ({position_type.upper()}) not executed due to low confidence ({decision['confidence']:.1%})")
        
        # API 제한을 위한 짧은 대기
        time.sleep(2)
    
    # 모니터링 결과 요약
    if monitored_count > 0:
        logger.info(f"✅ AI monitoring cycle completed: {monitored_count} positions monitored")
        if exit_decisions:
            logger.info(f"Exit decisions executed:")
            for exit_dec in exit_decisions:
                pos_type = exit_dec['position_type']
                type_emoji = "🤖" if pos_type == 'auto' else "🔧"
                logger.info(f"  {type_emoji} {exit_dec['symbol']} ({pos_type.upper()}): {exit_dec['decision']} - {exit_dec['reason']}")
    else:
        logger.info("No positions monitored (all disabled or no active positions)")
    
    logger.info("=== AI Position Monitoring Cycle End ===")
    
    return monitored_count, exit_decisions

def start_ai_monitoring():
    """AI 모니터링 스레드 시작"""
    global ai_monitor_thread, ai_monitor_running
    
    def monitor_loop():
        global ai_monitor_running
        ai_monitor_running = True
        
        while ai_monitor_running:
            try:
                # 🆕 v7.3 수정: 항상 거래소 동기화 먼저 수행 (수동 포지션 감지용)
                # 메모리에 포지션이 없어도 바이낸스에서 수동 포지션이 있을 수 있음
                logger.info("🔄 AI 모니터링: 거래소 포지션 동기화 중...")
                sync_count = sync_positions_from_exchange()
                
                # 동기화 후 포지션이 있으면 AI 모니터링 실행
                if current_positions:
                    logger.info(f"📊 {len(current_positions)}개 포지션 AI 모니터링 시작...")
                    ai_monitoring_cycle(skip_sync=True)  # 이미 sync 했으므로 건너뛰기
                else:
                    logger.debug("No positions to monitor after sync")
                
                # 다음 모니터링까지 대기
                time.sleep(AI_MONITOR_INTERVAL * 60)
                
            except Exception as e:
                logger.error(f"Error in AI monitoring loop: {e}", exc_info=True)
                time.sleep(60)  # 오류 발생 시 1분 대기
    
    if not ai_monitor_running:
        ai_monitor_thread = threading.Thread(target=monitor_loop, daemon=True)
        ai_monitor_thread.start()
        logger.info(f"✅ AI position monitoring started ({AI_MONITOR_INTERVAL}-minute intervals)")
        logger.info(f"   🤖 자동 포지션 및 🔧 수동 포지션 모두 모니터링됩니다")
        logger.info(f"   🔄 매 사이클마다 바이낸스 포지션 동기화 수행")

def stop_ai_monitoring():
    """AI 모니터링 중지"""
    global ai_monitor_running
    ai_monitor_running = False
    logger.info("AI position monitoring stopped")


# ============ 🆕 v7.8: Emergency Drawdown Protection ============
emergency_drawdown_running = False
emergency_drawdown_thread = None
emergency_drawdown_warned = set()  # 경고 발송된 심볼 추적


def emergency_drawdown_check_force_exit():
    """
    🆕 v7.8: 2단계 강제 청산 전용 - 고빈도 체크 (1분 간격)
    ROI <= FORCE_EXIT 시 즉시 강제 청산
    """
    global current_positions, emergency_drawdown_warned
    
    if not EMERGENCY_DRAWDOWN_ENABLED or not current_positions:
        return
    
    for symbol, position in current_positions.copy().items():
        try:
            ticker = exchange.fetch_ticker(symbol)
            current_price = ticker['last']
            entry_price = position.get('entry_price', 0)
            side = position.get('side', 'long')
            
            if not entry_price or entry_price <= 0:
                continue
            
            if side == 'long':
                roi = (current_price - entry_price) / entry_price * 100
            else:
                roi = (entry_price - current_price) / entry_price * 100
            
            # 🚨 강제 청산 임계값 체크
            if roi <= EMERGENCY_DRAWDOWN_FORCE_EXIT:
                logger.critical(f"🚨 FORCE EXIT: {symbol} ROI={roi:.2f}% <= {EMERGENCY_DRAWDOWN_FORCE_EXIT}%")
                
                if ENABLE_TELEGRAM:
                    send_telegram_notification(
                        f"🚨🚨🚨 <b>긴급 강제 청산</b> 🚨🚨🚨\n\n"
                        f"<b>심볼:</b> {symbol}\n"
                        f"<b>방향:</b> {side.upper()}\n"
                        f"<b>진입가:</b> ${entry_price:,.4f}\n"
                        f"<b>현재가:</b> ${current_price:,.4f}\n"
                        f"<b>ROI:</b> <b>{roi:+.2f}%</b>\n"
                        f"<b>임계값:</b> {EMERGENCY_DRAWDOWN_FORCE_EXIT}%\n\n"
                        f"⚠️ 긴급 낙폭 보호에 의해 즉시 청산!\n\n"
                        f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                        'error'
                    )
                
                try:
                    success_count = close_position_for_all_users(symbol)
                    if success_count > 0:
                        logger.info(f"🚨 {symbol} 강제 청산 완료: {success_count}명")
                        if symbol in current_positions:
                            record_completed_trade_with_binance(symbol, current_positions[symbol],
                                                               close_reason='edp_force_exit')
                            del current_positions[symbol]
                        emergency_drawdown_warned.discard(symbol)
                        
                        if ENABLE_TELEGRAM:
                            send_telegram_notification(
                                f"✅ <b>{symbol} 강제 청산 완료</b>\n"
                                f"청산: {success_count}/{len(exchanges)}명\n"
                                f"최종 ROI: {roi:+.2f}%",
                                'success'
                            )
                except Exception as e:
                    logger.error(f"🚨 {symbol} 강제 청산 실패: {e}")
                    if ENABLE_TELEGRAM:
                        send_telegram_notification(
                            f"❌ <b>{symbol} 강제 청산 실패!</b>\n오류: {str(e)}\n⚠️ 수동 확인 필요!",
                            'error'
                        )
            
            time.sleep(0.5)
            
        except Exception as e:
            logger.error(f"EDP force-exit 체크 오류 ({symbol}): {e}")


def emergency_drawdown_check_warning():
    """
    🆕 v7.8: 1단계 경고 + AI 집중 모니터링 (설정 간격)
    ROI <= WARNING 시 텔레그램 경고 + AI 모니터링
    """
    global current_positions, emergency_drawdown_warned
    
    if not EMERGENCY_DRAWDOWN_ENABLED or not current_positions:
        return
    
    logger.info(f"🛡️ EDP 경고 체크: {len(current_positions)}개 포지션 스캔")
    
    for symbol, position in current_positions.copy().items():
        try:
            ticker = exchange.fetch_ticker(symbol)
            current_price = ticker['last']
            entry_price = position.get('entry_price', 0)
            side = position.get('side', 'long')
            
            if not entry_price or entry_price <= 0:
                continue
            
            if side == 'long':
                roi = (current_price - entry_price) / entry_price * 100
            else:
                roi = (entry_price - current_price) / entry_price * 100
            
            # ⚠️ 경고 구간 (강제청산 구간은 force_exit 스레드가 처리)
            if roi <= EMERGENCY_DRAWDOWN_WARNING and roi > EMERGENCY_DRAWDOWN_FORCE_EXIT:
                # 최초 경고 시 텔레그램 알림
                if symbol not in emergency_drawdown_warned:
                    emergency_drawdown_warned.add(symbol)
                    logger.warning(f"⚠️ EDP WARNING: {symbol} ROI={roi:.2f}%")
                    
                    if ENABLE_TELEGRAM:
                        send_telegram_notification(
                            f"⚠️ <b>낙폭 경고 - 긴급 모니터링 돌입</b>\n\n"
                            f"<b>심볼:</b> {symbol}\n"
                            f"<b>방향:</b> {side.upper()}\n"
                            f"<b>진입가:</b> ${entry_price:,.4f}\n"
                            f"<b>현재가:</b> ${current_price:,.4f}\n"
                            f"<b>ROI:</b> <b>{roi:+.2f}%</b>\n\n"
                            f"🔍 AI 집중 모니터링 활성화 ({EMERGENCY_DRAWDOWN_MONITOR_INTERVAL}분 간격)\n"
                            f"🚨 {EMERGENCY_DRAWDOWN_FORCE_EXIT}% 도달 시 강제 청산 (1분 이내)\n\n"
                            f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                            'warning'
                        )
                
                # AI 모니터링 실행
                logger.info(f"🔍 {symbol} AI 집중 모니터링 (ROI: {roi:+.2f}%)")
                try:
                    decision = ai_monitor_position(symbol, position)
                    if decision and decision.get('decision') in ['close', 'partial_close']:
                        if decision.get('confidence', 0) >= 0.5 or decision.get('urgency') == 'immediate':
                            logger.warning(f"🤖 AI 청산 권장: {symbol} (신뢰도: {decision['confidence']:.1%})")
                            success = execute_position_exit(symbol, decision)
                            if success:
                                if symbol in current_positions:
                                    del current_positions[symbol]
                                emergency_drawdown_warned.discard(symbol)
                                if ENABLE_TELEGRAM:
                                    send_telegram_notification(
                                        f"🤖 <b>AI 판단 청산: {symbol}</b>\n"
                                        f"ROI: {roi:+.2f}% | 신뢰도: {decision['confidence']:.1%}\n"
                                        f"사유: {decision.get('reason', 'AI decision')}",
                                        'info'
                                    )
                except Exception as e:
                    logger.error(f"EDP AI 모니터링 오류 ({symbol}): {e}")
            
            elif roi > EMERGENCY_DRAWDOWN_WARNING:
                # 경고 구간에서 회복
                if symbol in emergency_drawdown_warned:
                    emergency_drawdown_warned.discard(symbol)
                    logger.info(f"✅ {symbol} 낙폭 경고 해제 (ROI: {roi:+.2f}%)")
                    if ENABLE_TELEGRAM:
                        send_telegram_notification(
                            f"✅ <b>{symbol} 낙폭 경고 해제</b>\n"
                            f"현재 ROI: {roi:+.2f}% (임계값: {EMERGENCY_DRAWDOWN_WARNING}% 초과)",
                            'success'
                        )
            
            time.sleep(1)
            
        except Exception as e:
            logger.error(f"EDP 경고 체크 오류 ({symbol}): {e}")


def start_emergency_drawdown_protection():
    """EDP 스레드 시작 - 2단계(강제청산)는 1분, 1단계(경고)는 설정 간격"""
    global emergency_drawdown_thread, emergency_drawdown_running
    
    def edp_force_exit_loop():
        """2단계: 강제 청산 감시 (1분 간격)"""
        logger.info(f"🚨 EDP 강제청산 감시 시작 (1분 간격, 임계값: {EMERGENCY_DRAWDOWN_FORCE_EXIT}%)")
        while emergency_drawdown_running:
            try:
                if EMERGENCY_DRAWDOWN_ENABLED and current_positions:
                    emergency_drawdown_check_force_exit()
                time.sleep(60)  # 1분 간격
            except Exception as e:
                logger.error(f"EDP force-exit 루프 오류: {e}", exc_info=True)
                time.sleep(30)
    
    def edp_warning_loop():
        """1단계: 경고 + AI 모니터링 (설정 간격)"""
        logger.info(f"⚠️ EDP 경고 모니터링 시작 ({EMERGENCY_DRAWDOWN_MONITOR_INTERVAL}분 간격, 임계값: {EMERGENCY_DRAWDOWN_WARNING}%)")
        while emergency_drawdown_running:
            try:
                if EMERGENCY_DRAWDOWN_ENABLED and current_positions:
                    emergency_drawdown_check_warning()
                time.sleep(EMERGENCY_DRAWDOWN_MONITOR_INTERVAL * 60)
            except Exception as e:
                logger.error(f"EDP warning 루프 오류: {e}", exc_info=True)
                time.sleep(60)
    
    if not emergency_drawdown_running:
        emergency_drawdown_running = True
        
        # 2단계: 강제 청산 전용 스레드 (1분 간격)
        force_thread = threading.Thread(target=edp_force_exit_loop, daemon=True)
        force_thread.start()
        
        # 1단계: 경고 + AI 모니터링 스레드 (설정 간격)
        warning_thread = threading.Thread(target=edp_warning_loop, daemon=True)
        warning_thread.start()
        
        emergency_drawdown_thread = (force_thread, warning_thread)
        logger.info(f"🛡️ Emergency Drawdown Protection 시작")
        logger.info(f"   🚨 강제청산: {EMERGENCY_DRAWDOWN_FORCE_EXIT}% (1분 간격 감시)")
        logger.info(f"   ⚠️ 경고: {EMERGENCY_DRAWDOWN_WARNING}% ({EMERGENCY_DRAWDOWN_MONITOR_INTERVAL}분 간격)")


def stop_emergency_drawdown_protection():
    """EDP 중지"""
    global emergency_drawdown_running
    emergency_drawdown_running = False
    logger.info("🛡️ Emergency Drawdown Protection 중지")

# ============ AI Decision Making (개선 버전) ============
def ai_validate_signal(symbol, action, market_data, recent_trades_df, message_data=None):
    """
    🆕 v7.3: Rule-Based Validation + AI Parameter Adjustment
    
    변경사항:
    1. 기술지표 종합 판단: Rule-Based 로직으로 수행 (정확한 수학적 비교)
    2. AI 역할: 극단적 리스크 필터링 + 파라미터 미세조정만 담당
       - 레버리지: 5~20배
       - 포지션 사이즈: 10~40%
       - TP/SL 조정
    """
    
    logger.info(f"🆕 v7.3 Rule-Based Validation 시작: {symbol} {action.upper()}")
    
    try:
        # ========== STEP 1: Rule-Based Validation ==========
        rule_result = rule_based_validation(symbol, action, market_data)
        
        decision = rule_result['decision']
        risk_score = rule_result['risk_score']['total_score']
        approval_score = rule_result['approval_score']['total_score']
        
        # REJECT인 경우 바로 반환
        if decision == 'reject':
            logger.info(f"❌ Rule-Based REJECT: {rule_result['reason']}")
            
            # DB에 기록
            try:
                conn = init_db()
                timestamp = datetime.now().isoformat()
                c = conn.cursor()
                
                if not is_duplicate_trade_record(conn, symbol, action, 'RULE_BASED', time_window_seconds=10):
                    c.execute("""INSERT INTO trades 
                              (timestamp, symbol, action, ai_decision, confidence, reason, 
                               current_price, trade_type, reflection, percentage, entry_price)
                              VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                              (timestamp, symbol, action, 'reject', 0.0, 
                               f"Rule-Based REJECT: Risk={risk_score}, Approval={approval_score}. {rule_result['reason']}", 
                               market_data['current_price'], 'RULE_BASED', 
                               f"Risk Details: {'; '.join(rule_result['risk_score']['details'])}", 
                               0, market_data['current_price']))
                    conn.commit()
                conn.close()
            except Exception as e:
                logger.error(f"DB 기록 오류: {e}")
            
            # 텔레그램 알림
            if ENABLE_TELEGRAM:
                send_telegram_notification(
                    f"❌ <b>Rule-Based REJECT</b>\n\n"
                    f"<b>심볼:</b> {symbol}\n"
                    f"<b>신호:</b> {action.upper()}\n"
                    f"<b>Risk Score:</b> {risk_score}/8\n"
                    f"<b>Approval Score:</b> {approval_score}/100\n"
                    f"<b>이유:</b> {rule_result['reason']}\n"
                    f"<b>리스크 요인:</b>\n" + 
                    '\n'.join([f"  • {d}" for d in rule_result['risk_score']['details'][:5]]),
                    'warning'
                )
            
            return {
                'decision': 'reject',
                'modified_action': 'hold',
                'percentage': 0,
                'reason': f"Rule-Based REJECT: Risk={risk_score}/8, Approval={approval_score}/100. {rule_result['reason']}",
                'stop_loss_price': 0,
                'take_profit_price': 0,
                'pl_ratio': 0,
                'confidence': 0.0
            }
        
        # 🔄 REVERSE인 경우 - 반전된 방향으로 진입
        if decision == 'reverse':
            modified_action = rule_result['modified_action']
            reverse_score = rule_result['reverse_score']['total_score']
            reverse_signals = rule_result['reverse_score']['signal_count']
            
            logger.info(f"🔄 Rule-Based REVERSE: {action.upper()} → {modified_action.upper()}")
            logger.info(f"   Reverse Score: {reverse_score}/10, Signals: {reverse_signals}/4")
            logger.info(f"   4H Trend did NOT support original signal")
            
            # AI 파라미터 조정 (반전된 액션으로)
            ai_params = ai_parameter_adjustment(symbol, modified_action, rule_result, market_data)
            
            leverage = ai_params['leverage']
            position_pct = ai_params['position_percent']
            stop_loss = ai_params['stop_loss']
            take_profit = ai_params['take_profit']
            pl_ratio = ai_params['pl_ratio']
            
            # 반전 트레이드는 더 낮은 신뢰도
            confidence = min(0.75, approval_score / 100 * 0.8)
            
            result = {
                'decision': 'reverse',
                'modified_action': modified_action,
                'percentage': position_pct,
                'reason': f"🔄 REVERSE: {action.upper()}→{modified_action.upper()}. 4H trend against original. Reverse Score={reverse_score}/10, Signals={reverse_signals}/4. {rule_result['reason']}",
                'stop_loss_price': stop_loss,
                'take_profit_price': take_profit,
                'pl_ratio': pl_ratio,
                'confidence': confidence,
                'leverage': leverage,
                'risk_score': risk_score,
                'approval_score': approval_score,
                'reverse_score': reverse_score
            }
            
            # DB 기록
            try:
                conn = init_db()
                timestamp = datetime.now().isoformat()
                c = conn.cursor()
                
                if not is_duplicate_trade_record(conn, symbol, modified_action, 'RULE_BASED_REVERSE', time_window_seconds=10):
                    c.execute("""INSERT INTO trades 
                              (timestamp, symbol, action, ai_decision, confidence, reason, 
                               current_price, trade_type, reflection, percentage, entry_price)
                              VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                              (timestamp, symbol, modified_action, 'reverse', confidence,
                               result['reason'], market_data['current_price'], 'RULE_BASED_REVERSE',
                               f"Original: {action.upper()} | Reverse Details: {'; '.join(rule_result['reverse_score']['details'][:3])}",
                               position_pct, market_data['current_price']))
                    conn.commit()
                conn.close()
            except Exception as e:
                logger.error(f"DB 기록 오류: {e}")
            
            # 텔레그램 알림
            if ENABLE_TELEGRAM:
                reverse_details = '\n'.join([f"  • {d}" for d in rule_result['reverse_score']['details'][:5]])
                send_telegram_notification(
                    f"🔄 <b>v7.3 REVERSE SIGNAL (4H Trend Against)</b>\n\n"
                    f"<b>심볼:</b> {symbol}\n"
                    f"<b>원래 신호:</b> {action.upper()} ❌\n"
                    f"<b>반전 신호:</b> {modified_action.upper()} ✅\n"
                    f"<b>Reverse Score:</b> {reverse_score}/10\n"
                    f"<b>Extreme Signals:</b> {reverse_signals}/4\n"
                    f"<b>레버리지:</b> {leverage}x\n"
                    f"<b>포지션:</b> {position_pct}%\n"
                    f"<b>SL:</b> ${stop_loss:,.2f}\n"
                    f"<b>TP:</b> ${take_profit:,.2f}\n"
                    f"<b>R:R:</b> {pl_ratio:.2f}\n\n"
                    f"<b>극단 신호 (4H 기준):</b>\n{reverse_details}",
                    'warning'
                )
            
            logger.info(f"🔄 v7.3 REVERSE 완료: {modified_action.upper()} - Lev={leverage}x, Size={position_pct}%, R:R={pl_ratio:.2f}")
            
            return result
        
        # ========== STEP 2: AI Parameter Adjustment ==========
        logger.info(f"✅ Rule-Based {decision.upper()}: 진행하여 AI 파라미터 조정")
        
        ai_params = ai_parameter_adjustment(symbol, action, rule_result, market_data)
        
        # 결과 구성
        final_decision = ai_params['decision']
        leverage = ai_params['leverage']
        position_pct = ai_params['position_percent']
        stop_loss = ai_params['stop_loss']
        take_profit = ai_params['take_profit']
        pl_ratio = ai_params['pl_ratio']
        
        # confidence 계산 (approval_score 기반)
        confidence = min(0.95, approval_score / 100)
        
        result = {
            'decision': 'approve' if final_decision == 'approve' else 'modify',
            'modified_action': action,
            'percentage': position_pct,
            'reason': f"Rule-Based {decision.upper()}: Risk={risk_score}/8, Approval={approval_score}/100. Leverage={leverage}x, Size={position_pct}%. {ai_params.get('reason', '')}",
            'stop_loss_price': stop_loss,
            'take_profit_price': take_profit,
            'pl_ratio': pl_ratio,
            'confidence': confidence,
            'leverage': leverage,  # 추가 필드
            'risk_score': risk_score,
            'approval_score': approval_score
        }
        
        # DB 기록
        try:
            conn = init_db()
            timestamp = datetime.now().isoformat()
            c = conn.cursor()
            
            if not is_duplicate_trade_record(conn, symbol, action, 'RULE_BASED', time_window_seconds=10):
                c.execute("""INSERT INTO trades 
                          (timestamp, symbol, action, ai_decision, confidence, reason, 
                           current_price, trade_type, reflection, percentage, entry_price)
                          VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                          (timestamp, symbol, action, result['decision'], confidence,
                           result['reason'], market_data['current_price'], 'RULE_BASED',
                           f"Risk: {'; '.join(rule_result['risk_score']['details'][:3])} | Approval: {'; '.join(rule_result['approval_score']['details'][:3])}",
                           position_pct, market_data['current_price']))
                conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"DB 기록 오류: {e}")
        
        # 텔레그램 알림
        if ENABLE_TELEGRAM:
            emoji = "✅" if final_decision == 'approve' else "⚠️"
            send_telegram_notification(
                f"{emoji} <b>v7.3 Rule-Based {final_decision.upper()}</b>\n\n"
                f"<b>심볼:</b> {symbol}\n"
                f"<b>신호:</b> {action.upper()}\n"
                f"<b>Risk Score:</b> {risk_score}/8\n"
                f"<b>Approval Score:</b> {approval_score}/100\n"
                f"<b>레버리지:</b> {leverage}x\n"
                f"<b>포지션:</b> {position_pct}%\n"
                f"<b>SL:</b> ${stop_loss:,.2f}\n"
                f"<b>TP:</b> ${take_profit:,.2f}\n"
                f"<b>R:R:</b> {pl_ratio:.2f}",
                'success' if final_decision == 'approve' else 'info'
            )
        
        logger.info(f"✅ v7.3 검증 완료: {result['decision'].upper()} - Lev={leverage}x, Size={position_pct}%, R:R={pl_ratio:.2f}")
        
        return result
        
    except Exception as e:
        logger.error(f"v7.3 검증 오류: {e}", exc_info=True)
        return create_default_reject_decision(f"시스템 오류: {str(e)}")
    
# ============ Trading Functions ============
def ai_emergency_parameters(symbol, action):
    """JSON 파싱 실패 시 AI가 자동으로 거래 파라미터 설정"""
    try:
        client = OpenAI(api_key=os.getenv("DEEPSEEK_API_KEY"), base_url="https://api.deepseek.com")
        if not client.api_key:
            return None
            
        # 현재 시장 데이터 수집
        ticker = exchange.fetch_ticker(symbol)
        current_price = ticker['last']
        
        # 기술적 분석
        analysis = get_multi_timeframe_analysis(symbol)
        
        # 잔고 확인
        balance = exchange.fetch_balance()
        free_usdt = balance['USDT']['free']
        
        prompt = f"""Emergency trading parameter generation required due to webhook parsing error.

MARKET DATA:
Symbol: {symbol}
Action: {action.upper()}
Current Price: ${current_price:.4f}
Free Balance: ${free_usdt:.2f}
24h Change: {ticker['percentage']:.2f}%

TECHNICAL INDICATORS:
RSI (15m): {analysis.get('rsi_15m', 50):.1f}
RSI (1h): {analysis.get('rsi_1h', 50):.1f}
ATR (15m): {analysis.get('atr_15m', current_price * 0.01):.4f}

REQUIREMENTS (MODERATE CONSERVATIVE):
1. Position size: 15-30% of free balance
2. Take Profit: 3.0-4.0% from entry
3. Stop Loss: 0.8-2.0% from entry  
4. Leverage: 5-10x maximum
5. Balance risk management with profit potential

Generate emergency trading parameters. Respond with JSON only:
{{
  "percentage": 20,
  "stop_loss_price": 0.0,
  "take_profit_price": 0.0,
  "leverage": 10,
  "reason": "Emergency parameters with moderate risk management",
  "confidence": 0.0-1.0
}}"""

        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": "You are an emergency risk management AI. Generate moderate conservative trading parameters."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=300,
            response_format={"type": "json_object"}
        )
        
        result_text = response.choices[0].message.content
        result_json = json.loads(result_text)
        
        # Pydantic 검증
        emergency_params = EmergencyTradingDecision(**result_json)
        
        logger.info(f"🚨 AI 긴급 파라미터 생성:")
        logger.info(f"   크기: {emergency_params.percentage}%")
        logger.info(f"   TP: ${emergency_params.take_profit_price:.4f}")
        logger.info(f"   SL: ${emergency_params.stop_loss_price:.4f}")
        logger.info(f"   레버리지: {emergency_params.leverage}x")
        
        return emergency_params
        
    except Exception as e:
        logger.error(f"AI 긴급 파라미터 생성 실패: {str(e)}")
        return None

def escape_html(text):
    """HTML 특수 문자 이스케이프"""
    if not isinstance(text, str):
        text = str(text)
    return text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

def send_telegram_notification(message, importance='normal'):
    """텔레그램 알림 전송"""
    if not ENABLE_TELEGRAM:
        return
        
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_IDS:
        logger.warning("텔레그램 설정이 완료되지 않았습니다.")
        return
    
    # HTML 파싱 모드 사용
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    
    # 중요도에 따른 이모지 추가
    emoji_map = {
        'high': '🚨',
        'normal': '📊',
        'low': 'ℹ️',
        'error': '❌',
        'success': '✅',
        'warning': '⚠️'
    }
    
    emoji = emoji_map.get(importance, '📊')
    
    # HTML 특수 문자 이스케이프 (단, 의도적인 HTML 태그는 유지)
    # <b>, </b>, <i>, </i>, <code>, </code> 등은 유지
    safe_message = message
    # 먼저 허용된 태그를 임시 치환
    allowed_tags = ['<b>', '</b>', '<i>', '</i>', '<code>', '</code>', '<pre>', '</pre>', '<u>', '</u>', '<s>', '</s>']
    placeholders = {}
    for i, tag in enumerate(allowed_tags):
        placeholder = f"__TAG_PLACEHOLDER_{i}__"
        placeholders[placeholder] = tag
        safe_message = safe_message.replace(tag, placeholder)
    
    # 나머지 < > & 이스케이프
    safe_message = safe_message.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
    
    # 허용된 태그 복원
    for placeholder, tag in placeholders.items():
        safe_message = safe_message.replace(placeholder, tag)
    
    formatted_message = f"{emoji} {safe_message}"
    
    for chat_id in TELEGRAM_CHAT_IDS:
        if chat_id:
            try:
                payload = {
                    'chat_id': chat_id.strip(),
                    'text': formatted_message,
                    'parse_mode': 'HTML'
                }
                response = requests.post(url, json=payload)
                response.raise_for_status()
            except Exception as e:
                logger.error(f"텔레그램 알림 전송 실패 (chat_id: {chat_id}): {str(e)}")

def test_telegram():
    """텔레그램 알림 테스트 - 개선된 에러 처리"""
    if not ENABLE_TELEGRAM:
        return False, "Telegram is disabled on this server"
    
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_IDS:
        return False, "Telegram configuration is incomplete"
    
    test_message = """<b>텔레그램 봇 테스트</b>

✅ 봇이 정상적으로 작동하고 있습니다!

이 메시지를 받으셨다면 설정이 올바르게 되어 있습니다.
⏰ """ + datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    try:
        send_telegram_notification(test_message, 'normal')
        return True, {"status": "success", "message": "Test message sent successfully"}
    except Exception as e:
        return False, f"Error: {str(e)}"

def verify_telegram_bot():
    """텔레그램 봇 연결 확인"""
    if not TELEGRAM_BOT_TOKEN:
        return {
            "success": False,
            "message": "Bot token is not configured"
        }
    
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getMe"
        response = requests.get(url, timeout=10)
        
        if response.status_code == 200:
            bot_info = response.json().get('result', {})
            return {
                "success": True,
                "message": "Bot connection successful",
                "bot_info": bot_info
            }
        else:
            return {
                "success": False,
                "message": "Bot connection failed",
                "status_code": response.status_code
            }
    except Exception as e:
        return {
            "success": False,
            "message": f"Connection verification error: {str(e)}"
        }

def send_custom_telegram_message(message, parse_mode='HTML', importance='normal'):
    """커스텀 텔레그램 메시지 전송"""
    if not ENABLE_TELEGRAM:
        return {"success": False, "message": "Telegram is disabled"}
    
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_IDS:
        return {"success": False, "message": "Telegram configuration is incomplete"}
    
    # HTML 파싱 모드 사용
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    
    # 중요도에 따른 이모지 추가
    emoji_map = {
        'high': '🚨',
        'normal': '📊',
        'low': 'ℹ️',
        'error': '❌',
        'success': '✅',
        'warning': '⚠️'
    }
    
    emoji = emoji_map.get(importance, '📊')
    formatted_message = f"{emoji} {message}"
    
    success_count = 0
    results = []
    
    for chat_id in TELEGRAM_CHAT_IDS:
        if chat_id:
            try:
                payload = {
                    'chat_id': chat_id.strip(),
                    'text': formatted_message,
                    'parse_mode': parse_mode
                }
                response = requests.post(url, json=payload, timeout=10)
                response.raise_for_status()
                success_count += 1
                results.append({
                    "chat_id": chat_id,
                    "success": True,
                    "response": response.json()
                })
            except Exception as e:
                logger.error(f"텔레그램 메시지 전송 실패 (chat_id: {chat_id}): {str(e)}")
                results.append({
                    "chat_id": chat_id,
                    "success": False,
                    "error": str(e)
                })
    
    return {
        "success": success_count > 0,
        "message": f"{success_count}/{len(TELEGRAM_CHAT_IDS)}개 채팅방에 전송 성공",
        "total": len(TELEGRAM_CHAT_IDS),
        "success_count": success_count,
        "results": results
    }

def calculate_position_size(symbol, balance):
    """포지션 크기 계산 - 개선된 버전 (마진 부족 방지)"""
    try:
        config = get_symbol_config(symbol)  # 🆕 v7.3: 정규화된 심볼 사용
        
        # 전체 잔고 정보 가져오기 
        balance_info = exchange.fetch_balance()
        total_balance = balance_info['USDT']['total']
        free_balance = balance_info['USDT']['free']
        used_balance = balance_info['USDT']['used']
        
        logger.info(f"💰 잔고 상태 확인:")
        logger.info(f"  - Total Balance: ${total_balance:,.2f}")
        logger.info(f"  - Free Balance: ${free_balance:,.2f}")
        logger.info(f"  - Used Balance: ${used_balance:,.2f}")
        
        # 안전 마진 버퍼 적용 (Free Balance의 90%만 사용)
        SAFETY_BUFFER = 0.90
        safe_free_balance = free_balance * SAFETY_BUFFER
        
        # 심볼별 포지션 크기 비율 설정
        position_size_percent = config.get('position_size_percent', DEFAULT_POSITION_SIZE_PERCENT)
        
        # 설정 비율에 따른 최대 포지션 크기 (Total Balance 기준)
        max_position_from_config = total_balance * (position_size_percent / 100)
        
        # 실제 사용 가능한 포지션 크기 (Free Balance 기준)
        available_position_size = safe_free_balance
        
        # 둘 중 작은 값 선택
        position_size = min(max_position_from_config, available_position_size)
        
        # 최소/최대 포지션 크기 제한 적용
        min_size = config.get('min_position_size', 10)
        max_size = config.get('max_position_size', 100000)
        
        if position_size < min_size:
            logger.warning(f"⚠️ 계산된 포지션 크기 ${position_size:,.2f}가 최소값 ${min_size}보다 작음")
            position_size = min_size if safe_free_balance >= min_size else 0
            
        if position_size > max_size:
            logger.info(f"📊 포지션 크기를 최대값 ${max_size:,.2f}로 제한")
            position_size = max_size
        
        # 레버리지 고려
        leverage = config.get('leverage', 10)
        required_margin = position_size / leverage
        
        # 마진 충분성 최종 확인
        if required_margin > safe_free_balance:
            logger.warning(f"⚠️ 마진 부족 - 필요: ${required_margin:,.2f}, 사용가능: ${safe_free_balance:,.2f}")
            # 사용 가능한 마진에 맞춰 포지션 크기 자동 조정
            position_size = safe_free_balance * leverage
            required_margin = safe_free_balance
            logger.info(f"✅ 포지션 크기를 ${position_size:,.2f}로 자동 조정")
        
        logger.info(f"📊 포지션 크기 계산 완료:")
        logger.info(f"  - 포지션 크기: ${position_size:,.2f}")
        logger.info(f"  - 필요 마진: ${required_margin:,.2f}")
        logger.info(f"  - 레버리지: {leverage}x")
        logger.info(f"  - 사용 비율: {position_size_percent}%")
        
        return position_size, position_size_percent
        
    except Exception as e:
        logger.error(f"❌ 포지션 크기 계산 오류: {str(e)}")
        # 오류 시 기존 방식으로 fallback
        config = get_symbol_config(symbol)  # 🆕 v7.3: 정규화된 심볼 사용
        position_size_percent = config.get('position_size_percent', DEFAULT_POSITION_SIZE_PERCENT)
        position_size = balance * (position_size_percent / 100)
        min_size = config.get('min_position_size', 10)
        max_size = config.get('max_position_size', 100000)
        position_size = max(min_size, min(position_size, max_size))
        return position_size, position_size_percent

def set_leverage(symbol):
    """심볼별 레버리지 설정"""
    try:
        config = get_symbol_config(symbol)  # 🆕 v7.3: 정규화된 심볼 사용
        leverage = config.get('leverage', 10)
        
        # 레버리지 설정
        exchange.set_leverage(leverage, symbol)
        logger.info(f"{symbol} 레버리지 설정: {leverage}x")
        return leverage
    except Exception as e:
        logger.error(f"{symbol} 레버리지 설정 실패: {str(e)}")
        return None


# ============ v7.6 바이낸스 SL/TP API (2025-12-09 이후 새 방식) ============
def get_price_precision(user_exchange, symbol):
    """
    🆕 v7.6: 심볼의 가격 정밀도(소수점 자릿수) 가져오기
    """
    import math
    
    try:
        # 마켓 정보 로드 시도
        try:
            if not user_exchange.markets:
                user_exchange.load_markets()
            market = user_exchange.market(symbol)
        except Exception as load_err:
            logger.warning(f"마켓 정보 로드 실패 ({symbol}): {load_err}")
            # 가격 기반 기본 정밀도 추정
            return 5
        
        price_precision = 5  # 기본값
        
        # 방법 1: info.filters에서 PRICE_FILTER의 tickSize 확인 (가장 정확)
        if 'info' in market and 'filters' in market['info']:
            for filter_item in market['info']['filters']:
                if filter_item.get('filterType') == 'PRICE_FILTER':
                    tick_size = float(filter_item.get('tickSize', 0.00001))
                    if tick_size > 0:
                        price_precision = max(0, int(round(-math.log10(tick_size))))
                        logger.debug(f"[{symbol}] tickSize={tick_size} → precision={price_precision}")
                    break
        # 방법 2: precision.price 사용 (fallback)
        elif 'precision' in market and 'price' in market['precision']:
            price_precision = int(market['precision']['price'])
        
        return price_precision
    except Exception as e:
        logger.warning(f"가격 정밀도 조회 실패 ({symbol}): {e}, 기본값 5 사용")
        return 5


def format_price(price, precision):
    """
    🆕 v7.6: 가격을 지정된 정밀도로 포맷팅 (부동소수점 오류 방지)
    
    예: format_price(0.020749999999999998, 5) → "0.02075"
    """
    from decimal import Decimal, ROUND_HALF_UP
    
    if precision <= 0:
        return str(int(round(price)))
    
    try:
        # Decimal 사용으로 부동소수점 오류 완전 방지
        decimal_price = Decimal(str(price))
        quantize_str = '0.' + '0' * precision
        rounded = decimal_price.quantize(Decimal(quantize_str), rounding=ROUND_HALF_UP)
        return str(rounded)
    except Exception:
        # fallback: 기존 방식
        rounded = round(price, precision)
        return f"{rounded:.{precision}f}"


def place_conditional_order(user_exchange, symbol, side, order_type, stop_price=None, limit_price=None,
                           quantity=None, close_position=False, reduce_only=False, 
                           working_type='MARK_PRICE',
                           activate_price=None, callback_rate=None):
    """
    🆕 v7.6: 바이낸스 Algo Order API (2025-12-09 이후)
    
    바이낸스 변경사항:
    - 엔드포인트: /fapi/v1/algoOrder
    - 필수 파라미터: algoType = "CONDITIONAL"
    - stopPrice → triggerPrice
    - 응답: orderId → algoId
    
    TRAILING_STOP_MARKET 지원:
    - activatePrice: 트레일링 활성화 가격 (선택)
    - callbackRate: 콜백 비율 (필수, 0.1~5.0 범위, 1.0 = 1%)
    - BUY: activatePrice < 현재가, 최저가에서 callbackRate만큼 반등 시 체결
    - SELL: activatePrice > 현재가, 최고가에서 callbackRate만큼 하락 시 체결
    """
    try:
        binance_symbol = symbol.replace('/', '')
        api_key = user_exchange.apiKey
        api_secret = user_exchange.secret
        
        timestamp = int(time.time() * 1000)
        
        # 🆕 v7.6: 새로운 Algo Order API 파라미터
        params = {
            'algoType': 'CONDITIONAL',
            'symbol': binance_symbol,
            'side': side.upper(),
            'type': order_type.upper(),
            'workingType': working_type,
            'timestamp': str(timestamp),
        }
        
        # TRAILING_STOP_MARKET: callbackRate 필수, triggerPrice 불필요
        if order_type.upper() == 'TRAILING_STOP_MARKET':
            if callback_rate is None:
                logger.error("❌ TRAILING_STOP_MARKET에는 callbackRate가 필수입니다")
                return None
            # callbackRate 범위 검증 (0.1 ~ 5.0)
            callback_rate = max(0.1, min(5.0, float(callback_rate)))
            params['callbackRate'] = str(callback_rate)
            
            if activate_price is not None:
                price_precision = get_price_precision(user_exchange, symbol)
                params['activatePrice'] = format_price(activate_price, price_precision)
                logger.info(f"📐 Trailing Stop activatePrice: {params['activatePrice']}")
        else:
            # 일반 조건부 주문: triggerPrice 필수
            if stop_price is None:
                logger.error(f"❌ {order_type}에는 triggerPrice(stop_price)가 필수입니다")
                return None
            price_precision = get_price_precision(user_exchange, symbol)
            formatted_stop_price = format_price(stop_price, price_precision)
            params['triggerPrice'] = formatted_stop_price
            logger.info(f"📐 가격 정밀도 적용: {symbol} precision={price_precision}, {stop_price} → {formatted_stop_price}")
        
        # STOP, TAKE_PROFIT (지정가)인 경우 price 추가
        if order_type.upper() in ['STOP', 'TAKE_PROFIT'] and limit_price:
            price_precision = get_price_precision(user_exchange, symbol)
            formatted_limit_price = format_price(limit_price, price_precision)
            params['price'] = formatted_limit_price
            params['timeInForce'] = 'GTC'
        
        # closePosition 또는 quantity
        if close_position:
            params['closePosition'] = 'true'
        elif quantity:
            params['quantity'] = str(quantity)
            if reduce_only:
                params['reduceOnly'] = 'true'
        
        # 서명 생성
        query_string = urllib.parse.urlencode(params)
        signature = hmac.new(
            api_secret.encode('utf-8'),
            query_string.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        params['signature'] = signature
        
        headers = {
            'X-MBX-APIKEY': api_key,
            'Content-Type': 'application/x-www-form-urlencoded'
        }
        
        url = 'https://fapi.binance.com/fapi/v1/algoOrder'
        
        logger.info(f"🆕 Algo Order API 호출: {order_type} {side} {binance_symbol} | params={params}")
        
        response = requests.post(url, headers=headers, data=params, timeout=10)
        
        if response.status_code == 200:
            result = response.json()
            algo_id = result.get('algoId', 'N/A')
            logger.info(f"✅ Algo Order 성공: algoId={algo_id}, status={result.get('algoStatus', 'N/A')}")
            return result
        else:
            try:
                error_data = response.json()
                error_code = error_data.get('code', 'N/A')
                error_msg = error_data.get('msg', 'Unknown error')
                logger.error(f"❌ Algo Order 실패: {error_code} - {error_msg}")
            except:
                logger.error(f"❌ API 응답 파싱 실패: {response.text}")
            return None
            
    except Exception as e:
        logger.error(f"❌ place_conditional_order 오류: {str(e)}")
        return None


def place_sl_tp_orders(user_exchange, symbol, action, sl_price, tp_price, 
                       quantity, user_name="Unknown",
                       trailing_callback_rate=None, trailing_activate_price=None):
    """
    🆕 v7.6: TP/SL + Trailing Stop 주문 설정 (2025-12-09 이후 Algo Order API)
    
    Args:
        user_exchange: CCXT exchange 인스턴스
        symbol: 거래 심볼
        action: 'buy' 또는 'sell' (원래 포지션 방향)
        sl_price: Stop Loss 트리거 가격
        tp_price: Take Profit 트리거 가격
        quantity: 포지션 수량
        user_name: 사용자 이름 (로깅용)
        trailing_callback_rate: 트레일링 스탑 콜백 비율 (%, 예: 2.0 = 2%)
        trailing_activate_price: 트레일링 스탑 활성화 가격 (선택)
    
    Returns:
        tuple: (sl_order, tp_order, trailing_order)
    """
    sl_order = None
    tp_order = None
    trailing_order = None
    
    # SL/TP 방향 결정 (포지션 반대 방향)
    sl_tp_side = 'SELL' if action.lower() == 'buy' else 'BUY'
    
    # ============ Stop Loss 주문 ============
    if sl_price is not None:
        try:
            logger.info(f"[{user_name}] 🛡️ SL 주문 시도: STOP_MARKET {sl_tp_side} @ triggerPrice={sl_price:.5f}")
            
            sl_order = place_conditional_order(
                user_exchange=user_exchange,
                symbol=symbol,
                side=sl_tp_side,
                order_type='STOP_MARKET',
                stop_price=sl_price,
                close_position=True,
                working_type='MARK_PRICE'
            )
            
            if sl_order:
                logger.info(f"[{user_name}] ✅ Stop Loss 설정 완료: ${sl_price:.5f} (algoId={sl_order.get('algoId', 'N/A')})")
            else:
                logger.warning(f"[{user_name}] closePosition 실패, reduceOnly 방식 재시도...")
                sl_order = place_conditional_order(
                    user_exchange=user_exchange,
                    symbol=symbol,
                    side=sl_tp_side,
                    order_type='STOP_MARKET',
                    stop_price=sl_price,
                    quantity=quantity,
                    reduce_only=True,
                    working_type='MARK_PRICE'
                )
                if sl_order:
                    logger.info(f"[{user_name}] ✅ Stop Loss 설정 완료 (reduceOnly): ${sl_price:.5f}")
                    
        except Exception as e:
            logger.error(f"[{user_name}] ❌ Stop Loss 설정 실패: {str(e)}")
    else:
        logger.info(f"[{user_name}] ℹ️ SL 가격 없음 - SL 주문 스킵")
    
    # ============ Take Profit 주문 ============
    if tp_price is not None:
        try:
            logger.info(f"[{user_name}] 🎯 TP 주문 시도: TAKE_PROFIT_MARKET {sl_tp_side} @ triggerPrice={tp_price:.5f}")
            
            tp_order = place_conditional_order(
                user_exchange=user_exchange,
                symbol=symbol,
                side=sl_tp_side,
                order_type='TAKE_PROFIT_MARKET',
                stop_price=tp_price,
                close_position=True,
                working_type='MARK_PRICE'
            )
            
            if tp_order:
                logger.info(f"[{user_name}] ✅ Take Profit 설정 완료: ${tp_price:.5f} (algoId={tp_order.get('algoId', 'N/A')})")
            else:
                logger.warning(f"[{user_name}] closePosition 실패, reduceOnly 방식 재시도...")
                tp_order = place_conditional_order(
                    user_exchange=user_exchange,
                    symbol=symbol,
                    side=sl_tp_side,
                    order_type='TAKE_PROFIT_MARKET',
                    stop_price=tp_price,
                    quantity=quantity,
                    reduce_only=True,
                    working_type='MARK_PRICE'
                )
                if tp_order:
                    logger.info(f"[{user_name}] ✅ Take Profit 설정 완료 (reduceOnly): ${tp_price:.5f}")
                    
        except Exception as e:
            logger.error(f"[{user_name}] ❌ Take Profit 설정 실패: {str(e)}")
    else:
        logger.info(f"[{user_name}] ℹ️ TP 가격 없음 - TP 주문 스킵")
    
    # ============ 🆕 Trailing Stop 주문 ============
    if trailing_callback_rate is not None and trailing_callback_rate > 0:
        try:
            logger.info(f"[{user_name}] 🔄 Trailing Stop 주문 시도: TRAILING_STOP_MARKET {sl_tp_side} callbackRate={trailing_callback_rate}%")
            
            trailing_order = place_conditional_order(
                user_exchange=user_exchange,
                symbol=symbol,
                side=sl_tp_side,
                order_type='TRAILING_STOP_MARKET',
                close_position=True,
                working_type='CONTRACT_PRICE',
                callback_rate=trailing_callback_rate,
                activate_price=trailing_activate_price
            )
            
            if trailing_order:
                logger.info(f"[{user_name}] ✅ Trailing Stop 설정 완료: callbackRate={trailing_callback_rate}% "
                           f"(algoId={trailing_order.get('algoId', 'N/A')})")
                if trailing_activate_price:
                    logger.info(f"[{user_name}]    activatePrice=${trailing_activate_price:.5f}")
            else:
                # closePosition 실패 시 reduceOnly 재시도
                logger.warning(f"[{user_name}] closePosition 실패, reduceOnly 방식 재시도...")
                trailing_order = place_conditional_order(
                    user_exchange=user_exchange,
                    symbol=symbol,
                    side=sl_tp_side,
                    order_type='TRAILING_STOP_MARKET',
                    quantity=quantity,
                    reduce_only=True,
                    working_type='CONTRACT_PRICE',
                    callback_rate=trailing_callback_rate,
                    activate_price=trailing_activate_price
                )
                if trailing_order:
                    logger.info(f"[{user_name}] ✅ Trailing Stop 설정 완료 (reduceOnly): callbackRate={trailing_callback_rate}%")
                    
        except Exception as e:
            logger.error(f"[{user_name}] ❌ Trailing Stop 설정 실패: {str(e)}")
    
    # 결과 요약
    results = []
    if sl_order: results.append("SL✅")
    else: results.append("SL❌")
    if tp_order: results.append("TP✅")
    else: results.append("TP❌")
    if trailing_callback_rate and trailing_order: results.append("TS✅")
    elif trailing_callback_rate: results.append("TS❌")
    
    logger.info(f"[{user_name}] 주문 결과: {' '.join(results)}")
    
    return sl_order, tp_order, trailing_order


# 기존 함수를 새 함수로 연결 (호환성 유지)
def place_algo_order(user_exchange, symbol, side, order_type, trigger_price, quantity=None, 
                     close_position=False, reduce_only=False, working_type='MARK_PRICE'):
    """
    🆕 v7.6: 호환성 래퍼 - 새로운 place_conditional_order로 연결
    """
    return place_conditional_order(
        user_exchange=user_exchange,
        symbol=symbol,
        side=side,
        order_type=order_type,
        stop_price=trigger_price,
        limit_price=None,
        quantity=quantity,
        close_position=close_position,
        reduce_only=reduce_only,
        working_type=working_type
    )


def place_algo_order_v2(user_exchange, symbol, side, order_type, trigger_price, 
                        quantity=None, close_position=False, reduce_only=False, 
                        working_type='MARK_PRICE'):
    """
    🆕 v7.6: 호환성 래퍼 - place_algo_order와 동일
    """
    return place_algo_order(user_exchange, symbol, side, order_type, trigger_price,
                           quantity, close_position, reduce_only, working_type)


def place_stop_order_fallback(user_exchange, symbol, side, order_type, trigger_price,
                              quantity=None, reduce_only=False):
    """
    🆕 v7.6: Fallback은 더 이상 사용하지 않음 (Algo API로 통합)
    """
    logger.warning("⚠️ Fallback 함수 호출됨 - Algo API로 재시도")
    return place_algo_order(user_exchange, symbol, side, order_type, trigger_price,
                           quantity, False, reduce_only)


def place_sl_tp_with_algo_api(user_exchange, symbol, action, sl_price, tp_price, 
                              quantity, user_name="Unknown",
                              trailing_callback_rate=None, trailing_activate_price=None):
    """
    🆕 v7.6: 호환성 래퍼 - 새로운 place_sl_tp_orders로 연결
    """
    return place_sl_tp_orders(user_exchange, symbol, action, sl_price, tp_price, 
                              quantity, user_name,
                              trailing_callback_rate, trailing_activate_price)


def validate_and_adjust_prices(user_exchange, symbol, action, current_price, stop_loss_price, take_profit_price):
    """
    🆕 v7.6: TP/SL 가격 검증 및 조정
    - 심볼별 tickSize 확인
    - 현재가와의 최소 거리 확인
    - 가격 정밀도 조정
    
    Args:
        user_exchange: CCXT exchange 인스턴스
        symbol: 거래 심볼
        action: 'buy' 또는 'sell'
        current_price: 현재가
        stop_loss_price: 손절가
        take_profit_price: 익절가
    
    Returns:
        dict: {
            'sl': 조정된 손절가,
            'tp': 조정된 익절가,
            'tick_size': 최소 가격 변동폭,
            'price_precision': 가격 정밀도
        }
    """
    try:
        # 마켓 정보 가져오기
        market = user_exchange.market(symbol)
        
        # 가격 정밀도(precision)
        price_precision = market.get('precision', {}).get('price', 8)
        
        # tickSize (최소 가격 변동폭)
        tick_size = None
        if 'filters' in market.get('info', {}):
            for filter_item in market['info']['filters']:
                if filter_item.get('filterType') == 'PRICE_FILTER':
                    tick_size = float(filter_item.get('tickSize', 0.01))
                    break
        
        if not tick_size:
            tick_size = 10 ** (-price_precision)
        
        # 가격을 tickSize에 맞게 조정
        def round_to_tick(price, tick):
            return round(price / tick) * tick
        
        # SL/TP 조정
        adjusted_sl = round_to_tick(stop_loss_price, tick_size)
        adjusted_tp = round_to_tick(take_profit_price, tick_size)
        
        # 최소 거리 검증 (0.1% 이상)
        min_distance_percent = 0.001  # 0.1%
        
        if action.lower() == 'buy':
            # 롱 포지션: SL < 현재가 < TP
            min_sl = current_price * (1 - min_distance_percent)
            min_tp = current_price * (1 + min_distance_percent)
            
            if adjusted_sl > min_sl:
                adjusted_sl = round_to_tick(min_sl, tick_size)
                logger.warning(f"⚠️ SL이 현재가와 너무 가까워 조정: ${stop_loss_price:.4f} -> ${adjusted_sl:.4f}")
            
            if adjusted_tp < min_tp:
                adjusted_tp = round_to_tick(min_tp, tick_size)
                logger.warning(f"⚠️ TP가 현재가와 너무 가까워 조정: ${take_profit_price:.4f} -> ${adjusted_tp:.4f}")
        else:
            # 숏 포지션: TP < 현재가 < SL
            max_sl = current_price * (1 + min_distance_percent)
            max_tp = current_price * (1 - min_distance_percent)
            
            if adjusted_sl < max_sl:
                adjusted_sl = round_to_tick(max_sl, tick_size)
                logger.warning(f"⚠️ SL이 현재가와 너무 가까워 조정: ${stop_loss_price:.4f} -> ${adjusted_sl:.4f}")
            
            if adjusted_tp > max_tp:
                adjusted_tp = round_to_tick(max_tp, tick_size)
                logger.warning(f"⚠️ TP가 현재가와 너무 가까워 조정: ${take_profit_price:.4f} -> ${adjusted_tp:.4f}")
        
        return {
            'sl': adjusted_sl,
            'tp': adjusted_tp,
            'tick_size': tick_size,
            'price_precision': price_precision
        }
        
    except Exception as e:
        logger.error(f"가격 검증 오류: {str(e)}")
        return {
            'sl': stop_loss_price,
            'tp': take_profit_price,
            'tick_size': 0.01,
            'price_precision': 2
        }


def execute_trade_for_all_users(symbol, action, amount_primary, stop_loss_price, take_profit_price, 
                                trailing_stop, trailing_activation):
    """모든 활성 유저에 대해 거래 실행"""
    success_count = 0
    failed_users = []
    primary_orders = None
    
    for user_id, user_exchange in exchanges.items():
        user_name = USER_CONFIGS[user_id]['name']
        is_primary = USER_CONFIGS[user_id]['is_primary']
        
        try:
            logger.info(f"[{user_name}] 거래 실행 시작: {symbol} {action}")
            
            # 🆕 v7.5: 양방향 포지션 충돌 체크
            try:
                hedge_check = check_hedge_position_conflict(symbol, action)
                if hedge_check['has_conflict']:
                    if hedge_check['should_close_existing']:
                        logger.warning(f"🔄 v7.5 HEDGE CONFLICT: {hedge_check['reason']}")
                        
                        # 수익 포지션 자동 청산
                        leverage = get_symbol_config(symbol).get('leverage', 20)
                        hedge_result = manage_hedge_positions(symbol, leverage)
                        
                        if hedge_result['closed']:
                            logger.info(f"✅ v7.5 Hedge position closed: {hedge_result['side']} at +{hedge_result['pnl']:.2f}%")
                            if ENABLE_TELEGRAM:
                                send_telegram_notification(
                                    f"🔄 <b>v7.5 양방향 포지션 정리</b>\n\n"
                                    f"<b>심볼:</b> {symbol}\n"
                                    f"<b>청산 방향:</b> {hedge_result['side'].upper()}\n"
                                    f"<b>수익:</b> +{hedge_result['pnl']:.2f}%\n"
                                    f"<b>새 진입:</b> {action.upper()}\n\n"
                                    f"💡 수익 포지션 청산 후 새 방향 진입",
                                    'info'
                                )
                    else:
                        logger.warning(f"⚠️ v7.5 HEDGE WARNING: {hedge_check['reason']}")
            except Exception as e:
                logger.warning(f"Hedge check failed: {e}")
            
            # 레버리지 설정 (🆕 v7.3: 정규화된 심볼 사용)
            try:
                leverage = get_symbol_config(symbol).get('leverage', 10)
                user_exchange.set_leverage(leverage, symbol)
                logger.info(f"[{user_name}] 레버리지 설정: {leverage}x")
            except Exception as e:
                logger.warning(f"[{user_name}] 레버리지 설정 실패: {str(e)}")
            
            # 각 유저의 잔고에 맞게 수량 재계산
            balance_info = user_exchange.fetch_balance()
            usdt_balance = balance_info['USDT']['free']
            position_percent = get_symbol_config(symbol).get('position_size_percent', 30)
            position_size = usdt_balance * (position_percent / 100)
            
            ticker = user_exchange.fetch_ticker(symbol)
            current_price = ticker['last']
            leverage = get_symbol_config(symbol).get('leverage', 10)
            amount = (position_size * leverage) / current_price
            
            logger.info(f"[{user_name}] 포지션 크기: ${position_size:.2f} (잔고: ${usdt_balance:.2f})")
            logger.info(f"[{user_name}] 수량: {amount:.6f}")
            
            # 주문 실행 (원본 함수 활용 - exchange를 user_exchange로 치환)
            # 메인 주문
            order_side = action
            main_order = user_exchange.create_market_order(symbol, order_side, amount)
            actual_entry = float(main_order['average']) if main_order.get('average') else current_price
            logger.info(f"[{user_name}] ✅ 메인 주문 체결: {symbol} {order_side} {amount:.6f} @ ${actual_entry:.4f}")

            # 🆕 v7.6: 가격 검증 및 조정 (TP/SL 각각 독립 처리)
            adjusted_sl = stop_loss_price    # None일 수 있음
            adjusted_tp = take_profit_price  # None일 수 있음
            
            if stop_loss_price is not None and take_profit_price is not None:
                # 둘 다 있으면 기존 검증 로직
                price_check = validate_and_adjust_prices(
                    user_exchange, symbol, action, current_price, 
                    stop_loss_price, take_profit_price
                )
                adjusted_sl = price_check['sl']
                adjusted_tp = price_check['tp']
            elif stop_loss_price is not None:
                adjusted_sl = stop_loss_price
                logger.info(f"[{user_name}] SL만 설정: ${adjusted_sl:.5f} (TP 없음)")
            elif take_profit_price is not None:
                adjusted_tp = take_profit_price
                logger.info(f"[{user_name}] TP만 설정: ${adjusted_tp:.5f} (SL 없음)")
            
            # 🔄 현재 포지션의 전체 크기 조회 (여러 번 진입한 경우 대비)
            try:
                positions = user_exchange.fetch_positions([symbol])
                total_position_amount = 0
                for pos in positions:
                    if float(pos.get('contracts', 0)) != 0:
                        total_position_amount = abs(float(pos.get('contracts', 0)))
                        break
                
                # 포지션이 없으면 진입 예정 수량 사용
                if total_position_amount == 0:
                    total_position_amount = amount
                    
                logger.info(f"[{user_name}] 현재 포지션 크기: {total_position_amount:.6f} (TP/SL에 사용)")
            except Exception as e:
                logger.warning(f"[{user_name}] 포지션 조회 실패, 진입 수량 사용: {str(e)}")
                total_position_amount = amount
            
            # 🆕 v7.8: Algo Order API - TP/SL/Trailing 각각 독립 주문
            sl_order = None
            tp_order = None
            trailing_order = None
            
            # 🆕 Trailing Stop: activatePrice 계산
            # SELL(롱청산): activatePrice > 현재가 (수익 구간 진입 후 활성화)
            # BUY(숏청산): activatePrice < 현재가 (수익 구간 진입 후 활성화)
            ts_activate_price = None
            ts_callback_rate = None
            if trailing_stop is not None and trailing_stop > 0:
                ts_callback_rate = trailing_stop  # trailing_stop_percent → callbackRate
                if trailing_activation and trailing_activation > 0:
                    # activation > 0: 수익 구간 진입 후 활성화
                    if action.lower() == 'buy':
                        ts_activate_price = actual_entry * (1 + trailing_activation / 100)
                    else:
                        ts_activate_price = actual_entry * (1 - trailing_activation / 100)
                    logger.info(f"[{user_name}] 🔄 Trailing Stop: callbackRate={ts_callback_rate}%, activatePrice=${ts_activate_price:.5f}")
                else:
                    # activation = 0 또는 None: activatePrice 미설정 → 바이낸스가 즉시 추적 시작
                    ts_activate_price = None
                    logger.info(f"[{user_name}] 🔄 Trailing Stop: callbackRate={ts_callback_rate}%, activatePrice=즉시(미설정)")
            
            # 🆕 v7.8: TP/SL/Trailing 중 하나라도 있으면 Algo Order 설정
            has_sl = adjusted_sl is not None
            has_tp = adjusted_tp is not None
            has_trailing = ts_callback_rate is not None and ts_callback_rate > 0
            
            if has_sl or has_tp or has_trailing:
                sl_order, tp_order, trailing_order = place_sl_tp_with_algo_api(
                    user_exchange=user_exchange,
                    symbol=symbol,
                    action=action,
                    sl_price=adjusted_sl,
                    tp_price=adjusted_tp,
                    quantity=total_position_amount,
                    user_name=user_name,
                    trailing_callback_rate=ts_callback_rate,
                    trailing_activate_price=ts_activate_price
                )
                
                # 결과 로깅
                if has_sl and not sl_order:
                    logger.warning(f"[{user_name}] ⚠️ SL 주문 실패 - SL가격: ${adjusted_sl:.4f}, 현재가: ${current_price:.4f}")
                if has_tp and not tp_order:
                    logger.warning(f"[{user_name}] ⚠️ TP 주문 실패 - TP가격: ${adjusted_tp:.4f}, 현재가: ${current_price:.4f}")
            elif ts_callback_rate:
                # TP/SL 없어도 Trailing Stop만 단독 설정 가능
                sl_tp_side = 'SELL' if action.lower() == 'buy' else 'BUY'
                trailing_order = place_conditional_order(
                    user_exchange=user_exchange,
                    symbol=symbol,
                    side=sl_tp_side,
                    order_type='TRAILING_STOP_MARKET',
                    close_position=True,
                    working_type='CONTRACT_PRICE',
                    callback_rate=ts_callback_rate,
                    activate_price=ts_activate_price
                )
                if trailing_order:
                    logger.info(f"[{user_name}] ✅ Trailing Stop 단독 설정 완료 (TP/SL 미설정)")
                else:
                    logger.error(f"[{user_name}] ❌ Trailing Stop 단독 설정 실패")
            else:
                logger.info(f"[{user_name}] TP/SL 미설정 (자동생성 OFF) - TradingView 종료 신호에 의존")
            
            success_count += 1
            
            # Primary User의 주문 정보 저장 (반환용)
            if is_primary:
                primary_orders = {
                    'main': main_order,
                    'actual_entry': actual_entry,
                    'adjusted_amount': amount,
                    'sl': sl_order,
                    'tp': tp_order,
                    'trailing': trailing_order
                }
            
        except Exception as e:
            logger.error(f"[{user_name}] 거래 실행 실패: {str(e)}")
            failed_users.append(user_name)
    
    # 결과 로깅
    total_users = len(exchanges)
    logger.info(f"✅ 거래 실행 완료: {success_count}/{total_users}명 성공")
    if failed_users:
        logger.warning(f"⚠️ 실패한 유저: {', '.join(failed_users)}")
    
    # Primary User의 주문 정보 반환 (기존 코드 호환성)
    return primary_orders

def close_position_for_all_users(symbol):
    """모든 활성 유저의 포지션 청산 및 TP/SL 자동 취소"""
    success_count = 0
    failed_users = []
    
    for user_id, user_exchange in exchanges.items():
        user_name = USER_CONFIGS[user_id]['name']
        
        try:
            # 포지션 확인
            positions = user_exchange.fetch_positions([symbol])
            active_position = None
            
            for pos in positions:
                if float(pos.get('contracts', 0)) != 0:
                    active_position = pos
                    break
            
            if not active_position:
                logger.info(f"[{user_name}] {symbol} 포지션 없음")
                continue
            
            # 포지션 청산
            contracts = float(active_position['contracts'])
            side = 'sell' if active_position['side'] == 'long' else 'buy'
            
            close_order = user_exchange.create_market_order(symbol, side, abs(contracts))
            logger.info(f"[{user_name}] ✅ 포지션 청산: {symbol} {side} {abs(contracts):.6f}")
            
            # 🆕 TP/SL 자동 취소
            cancelled = cancel_symbol_orders(user_exchange, symbol, user_name)
            if cancelled > 0:
                logger.info(f"[{user_name}] 🗑️ TP/SL 주문 {cancelled}개 자동 취소")
            
            success_count += 1
            
        except Exception as e:
            logger.error(f"[{user_name}] 포지션 청산 실패: {str(e)}")
            failed_users.append(user_name)
    
    # 결과 로깅
    total_users = len(exchanges)
    logger.info(f"✅ 청산 완료: {success_count}/{total_users}명 성공")
    if failed_users:
        logger.warning(f"⚠️ 실패한 유저: {', '.join(failed_users)}")
    
    return success_count


def place_orders_with_sl_tp(symbol, action, amount, stop_loss_price, take_profit_price, 
                            trailing_stop_percent=None, trailing_activation_percent=None):
    """스탑로스와 테이크프로핏이 포함된 주문 실행 - 마진 부족 방지 버전"""
    try:
        # 마진 충분성 사전 확인
        balance_info = exchange.fetch_balance()
        free_balance = balance_info['USDT']['free']
        
        # 현재 시장가 조회
        ticker = exchange.fetch_ticker(symbol)
        current_price = ticker['last']
        
        # 필요한 마진 계산
        config = get_symbol_config(symbol)  # 🆕 v7.3: 정규화된 심볼 사용
        leverage = config.get('leverage', 10)
        position_value_usdt = amount * current_price
        required_margin = position_value_usdt / leverage
        
        # 안전 버퍼 적용
        SAFETY_BUFFER = 0.90
        safe_free_balance = free_balance * SAFETY_BUFFER
        
        logger.info(f"📊 주문 전 마진 체크:")
        logger.info(f"  - 필요 마진: ${required_margin:,.2f}")
        logger.info(f"  - 사용가능 마진: ${safe_free_balance:,.2f}")
        logger.info(f"  - 포지션 가치: ${position_value_usdt:,.2f}")
        
        # 마진 부족 시 수량 자동 조정
        if required_margin > safe_free_balance:
            logger.warning(f"⚠️ 마진 부족 감지 - 수량 자동 조정 시작")
            
            # 사용 가능한 마진으로 수량 재계산
            max_position_value = safe_free_balance * leverage
            adjusted_amount = max_position_value / current_price
            
            # 거래소 최소 수량 체크
            market = exchange.market(symbol)
            min_amount = market['limits']['amount']['min'] if 'limits' in market and 'amount' in market['limits'] else 0.001
            
            if adjusted_amount < min_amount:
                logger.error(f"❌ 조정된 수량 {adjusted_amount}이 최소 수량 {min_amount}보다 작음")
                return None
            
            logger.info(f"✅ 수량 조정: {amount} -> {adjusted_amount}")
            amount = adjusted_amount
            position_value_usdt = amount * current_price
            required_margin = position_value_usdt / leverage
        
        # 시장가 주문 실행 (재시도 로직 포함)
        max_retries = 3
        retry_count = 0
        order = None
        
        while retry_count < max_retries and order is None:
            try:
                if action == 'buy':
                    order = exchange.create_market_buy_order(symbol, amount)
                elif action == 'sell':
                    order = exchange.create_market_sell_order(symbol, amount)
                else:
                    return None
                    
            except Exception as order_error:
                if "Margin is insufficient" in str(order_error):
                    retry_count += 1
                    logger.warning(f"⚠️ 마진 부족 오류 발생 (시도 {retry_count}/{max_retries})")
                    
                    if retry_count < max_retries:
                        # 수량을 10% 줄여서 재시도
                        amount = amount * 0.9
                        logger.info(f"📉 수량 10% 감소 후 재시도: {amount}")
                        time.sleep(1)  # 1초 대기
                    else:
                        logger.error(f"❌ 최대 재시도 횟수 초과 - 주문 실패")
                        raise
                else:
                    # 다른 오류는 즉시 raise
                    raise
        
        if order is None:
            logger.error("❌ 주문 실행 실패")
            return None
        
        entry_price = order['average'] if order['average'] else order['price']
        
        logger.info(f"✅ 포지션 진입 완료 - {symbol} {action} @ ${entry_price:.2f}, 수량: {amount}")
        
        # SL/TP 주문 설정
        time.sleep(1)
        
        # 🆕 v7.6: 가격 검증 및 조정
        price_check = validate_and_adjust_prices(
            exchange, symbol, action, current_price, 
            stop_loss_price, take_profit_price
        )
        adjusted_sl = price_check['sl']
        adjusted_tp = price_check['tp']
        
        # 🆕 v7.4: 새로운 Algo Order API 사용 (2025-12-09 바이낸스 API 변경 대응)
        sl_order, tp_order, _trailing = place_sl_tp_with_algo_api(
            user_exchange=exchange,
            symbol=symbol,
            action=action,
            sl_price=adjusted_sl,
            tp_price=adjusted_tp,
            quantity=amount,
            user_name="Primary"
        )
        
        # 결과 로깅
        if not sl_order:
            logger.error(f"실패 상세 - SL가격: ${adjusted_sl:.4f}, 현재가: ${current_price:.4f}, 수량: {amount:.6f}")
        if not tp_order:
            logger.error(f"실패 상세 - TP가격: ${adjusted_tp:.4f}, 현재가: ${current_price:.4f}, 수량: {amount:.6f}")
        
        # 🆕 트레일링 스탑: 바이낸스 TRAILING_STOP_MARKET으로 대체 (구 모니터 스레드 제거)
        # 이 구 함수(place_orders_with_sl_tp)는 현재 사용되지 않으나, 호출될 경우 대비
        trailing_order_result = None
        if trailing_stop_percent and trailing_activation_percent:
            sl_tp_side = 'SELL' if action == 'buy' else 'BUY'
            ts_activate = entry_price * (1 + trailing_activation_percent/100) if action == 'buy' else entry_price * (1 - trailing_activation_percent/100)
            trailing_order_result = place_conditional_order(
                user_exchange=exchange, symbol=symbol, side=sl_tp_side,
                order_type='TRAILING_STOP_MARKET', close_position=True,
                working_type='CONTRACT_PRICE',
                callback_rate=trailing_stop_percent, activate_price=ts_activate
            )
            if trailing_order_result:
                logger.info(f"✅ Trailing Stop 설정: callbackRate={trailing_stop_percent}%, activatePrice=${ts_activate:.5f}")
        
        return {
            'entry': order,
            'sl': sl_order,
            'tp': tp_order,
            'actual_entry': entry_price,
            'adjusted_amount': amount
        }
        
    except Exception as e:
        logger.error(f"❌ 주문 실행 오류: {str(e)}", exc_info=True)
        
        # 마진 부족 오류를 명확히 로깅
        if "Margin is insufficient" in str(e):
            logger.error("💡 해결 방법: position_size_percent를 낮추거나 잔고를 늘려주세요")
            
            # 텔레그램 알림
            if ENABLE_TELEGRAM:
                send_telegram_notification(
                    f"❌ 마진 부족으로 주문 실패\n"
                    f"심볼: {symbol}\n"
                    f"필요 마진: ${required_margin:,.2f}\n"
                    f"사용가능: ${safe_free_balance:,.2f}\n"
                    f"해결: position_size_percent 조정 필요",
                    'error'
                )
        
        return None

def start_trailing_stop_monitor(symbol, side, entry_price, amount, trailing_percent, activation_percent):
    """트레일링 스탑 모니터링 스레드 시작"""
    def monitor():
        activation_price = entry_price * (1 + activation_percent/100) if side == 'buy' else entry_price * (1 - activation_percent/100)
        highest_price = entry_price
        lowest_price = entry_price
        activated = False
        
        while symbol in current_positions:
            try:
                ticker = exchange.fetch_ticker(symbol)
                current_price = ticker['last']
                
                if side == 'buy':
                    if not activated and current_price >= activation_price:
                        activated = True
                        logger.info(f"{symbol} 트레일링 스탑 활성화: {current_price}")
                    
                    if activated:
                        if current_price > highest_price:
                            highest_price = current_price
                            # 새로운 스탑로스 가격 계산
                            new_sl = highest_price * (1 - trailing_percent/100)
                            # 스탑로스 주문 업데이트 로직
                            update_stop_loss(symbol, new_sl, amount)
                            
                else:  # sell
                    if not activated and current_price <= activation_price:
                        activated = True
                        logger.info(f"{symbol} 트레일링 스탑 활성화: {current_price}")
                    
                    if activated:
                        if current_price < lowest_price:
                            lowest_price = current_price
                            new_sl = lowest_price * (1 + trailing_percent/100)
                            update_stop_loss(symbol, new_sl, amount)
                
                time.sleep(30)  # 30초마다 체크
                
            except Exception as e:
                logger.error(f"트레일링 스탑 모니터링 오류 ({symbol}): {str(e)}")
                time.sleep(60)
    
    thread = threading.Thread(target=monitor, daemon=True)
    thread.start()
    position_monitor_threads[symbol] = thread

def update_stop_loss(symbol, new_sl_price, amount):
    """스탑로스 주문 업데이트"""
    try:
        # 기존 스탑로스 주문 취소
        open_orders = exchange.fetch_open_orders(symbol)
        for order in open_orders:
            if order['type'] == 'stop' or order['type'] == 'stop_market':
                exchange.cancel_order(order['id'], symbol)
                time.sleep(1)
        
        # 새로운 스탑로스 주문 생성
        position = current_positions.get(symbol)
        if position:
            sl_side = 'sell' if position['side'] == 'buy' else 'buy'
            new_order = exchange.create_order(
                symbol=symbol,
                type='stop_market',
                side=sl_side,
                # amount=amount,
                params={
                    'stopPrice': new_sl_price,
                    'workingType': 'MARK_PRICE',
                    # 'reduceOnly': True,
                    'closePosition': True  # 모든 포지션 정리
                }
            )

            logger.info(f"{symbol} 스탑로스 업데이트: {new_sl_price} (closePosition=True)")
            
    except Exception as e:
        logger.error(f"스탑로스 업데이트 오류 ({symbol}): {str(e)}")

def format_position_entry_message(symbol, action, amount, entry_price, sl, tp, pl_ratio, 
                                 position_size, balance, trailing_stop=None, trailing_activation=None):
    """포지션 진입 메시지 포맷팅"""
    direction = "🟢 롱" if action == 'buy' else "🔴 숏"
    
    # P&L 계산 (TP/SL이 None일 수 있음)
    if sl is not None and tp is not None:
        if action == 'buy':
            potential_loss = (entry_price - sl) * amount
            potential_profit = (tp - entry_price) * amount
        else:
            potential_loss = (sl - entry_price) * amount
            potential_profit = (entry_price - tp) * amount
        
        risk_info = f"""<b>리스크 관리:</b>
• 스탑로스: ${sl:,.4f} (예상 손실: ${potential_loss:,.2f})
• 테이크프로핏: ${tp:,.4f} (예상 이익: ${potential_profit:,.2f})
• P/L 비율: {pl_ratio:.2f}"""
    else:
        risk_info = """<b>리스크 관리:</b>
• TP/SL: 미설정 (TradingView 종료 신호에 의존)"""
    
    message = f"""
<b>📈 포지션 진입 알림</b>

<b>심볼:</b> {symbol}
<b>방향:</b> {direction}
<b>진입가:</b> ${entry_price:,.4f}
<b>수량:</b> {amount:.4f}
<b>포지션 크기:</b> ${position_size:,.2f}

{risk_info}
"""
    
    if trailing_stop and trailing_activation:
        message += f"""• 🔄 트레일링 스탑: {trailing_stop}% (바이낸스 TRAILING_STOP_MARKET)
• 활성화 기준: +{trailing_activation}%
"""
    
    message += f"""
<b>계좌 정보:</b>
• 잔고: ${balance:,.2f}
• 사용 비율: {(position_size/balance)*100:.1f}%

⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
    """.strip()
    
    return message

# ============ Flask Routes ============
@app.route('/webhook', methods=['POST'])
def webhook():
    """TradingView 웹훅 수신 및 처리 - 개선 버전 (강력한 파싱)"""
    try:
        # JSON 데이터 파싱 (개선된 에러 처리)
        data = None
        raw_data = ""
        
        # Content-Type 확인
        content_type = request.headers.get('Content-Type', '')
        
        # JSON 파싱 시도
        if 'application/json' in content_type:
            try:
                data = request.get_json(force=True)
                logger.info(f"✅ JSON 데이터 성공적으로 파싱됨")
            except Exception as e:
                logger.warning(f"⚠️ JSON 파싱 실패, raw 데이터로 재시도: {e}")
        
        # JSON 파싱 실패 시 raw 데이터로 처리
        if data is None:
            raw_data = request.get_data(as_text=True)
            logger.info(f"📥 Raw webhook data (first 500 chars): {raw_data[:500]}")
            
            # === 1단계: JSON 정리 및 파싱 ===
            try:
                # TradingView Pine Script에서 생성된 잘못된 JSON 수정
                # 예: "value":-0.2294" → "value":-0.2294
                cleaned_data = re.sub(r'":(-?\d+\.?\d*)"', r'":\1', raw_data)
                # 숫자 뒤의 불필요한 따옴표 제거
                cleaned_data = re.sub(r'(\d)"([,}])', r'\1\2', cleaned_data)
                
                data = json.loads(cleaned_data)
                logger.info(f"✅ 정리된 데이터에서 JSON 파싱 성공")
            except json.JSONDecodeError as e:
                logger.warning(f"⚠️ 정리 후에도 JSON 파싱 실패: {e}")
                
                # === 2단계: 정규식으로 필수 필드 추출 ===
                try:
                    logger.info(f"🔍 정규식 기반 필수 필드 추출 시도...")
                    parsed_data = {}
                    
                    # 필수 필드 패턴 정의 (기술적 지표 포함)
                    patterns = {
                        'action': r'"action"\s*:\s*"([^"]+)"',
                        'symbol': r'"symbol"\s*:\s*"([^"]+)"',
                        'entry_price': r'"entry_price"\s*:\s*(-?\d+\.?\d*)',
                        'stop_loss': r'"stop_loss"\s*:\s*(-?\d+\.?\d*)',
                        'take_profit': r'"take_profit"\s*:\s*(-?\d+\.?\d*)',
                        'position_type': r'"position_type"\s*:\s*"([^"]+)"',
                        'exit_price': r'"exit_price"\s*:\s*(-?\d+\.?\d*)',
                        'profit_percent': r'"profit_percent"\s*:\s*(-?\d+\.?\d*)',
                        'exit_reason': r'"exit_reason"\s*:\s*"([^"]+)"',
                        'trailing_stop_percent': r'"trailing_stop_percent"\s*:\s*(null|"null"|-?\d+\.?\d*)',
                        'trailing_activation_percent': r'"trailing_activation_percent"\s*:\s*(null|"null"|-?\d+\.?\d*)',
                        # 기술적 지표 추가
                        'timeframe': r'"timeframe"\s*:\s*"([^"]+)"',
                        'cmf_value': r'"cmf_value"\s*:\s*(-?\d+\.?\d*)',
                        'cmf_momentum': r'"cmf_momentum"\s*:\s*(-?\d+\.?\d*)',
                        'adx': r'"adx"\s*:\s*(-?\d+\.?\d*)',
                        'rsi': r'"rsi"\s*:\s*(-?\d+\.?\d*)',
                        'volume_ratio': r'"volume_ratio"\s*:\s*(-?\d+\.?\d*)'
                    }
                    
                    # 각 필드 추출
                    for key, pattern in patterns.items():
                        match = re.search(pattern, raw_data, re.IGNORECASE)
                        if match:
                            value = match.group(1)
                            # 숫자 필드 변환
                            if key in ['entry_price', 'stop_loss', 'take_profit', 'exit_price', 
                                      'profit_percent', 'cmf_value', 'cmf_momentum', 
                                      'adx', 'rsi', 'volume_ratio']:
                                try:
                                    parsed_data[key] = float(value)
                                except:
                                    parsed_data[key] = None
                            elif key in ['trailing_stop_percent', 'trailing_activation_percent']:
                                if value in ['null', '"null"']:
                                    parsed_data[key] = None
                                else:
                                    try:
                                        parsed_data[key] = float(value)
                                    except:
                                        parsed_data[key] = None
                            else:
                                parsed_data[key] = value
                    
                    # 필수 필드 검증
                    required_fields = ['action', 'symbol']
                    if all(field in parsed_data for field in required_fields):
                        data = parsed_data
                        logger.info(f"✅ 정규식 파싱 성공! 추출된 필드: {list(data.keys())}")
                    else:
                        missing = [f for f in required_fields if f not in parsed_data]
                        logger.error(f"❌ 필수 필드 누락: {missing}")
                        
                        # === 3단계: Pine Script 형식(key=value) 파싱 시도 ===
                        try:
                            logger.info(f"🔍 Pine Script format 파싱 시도...")
                            parsed_data = {}
                            lines = raw_data.strip().split('\n')
                            
                            for line in lines:
                                line = line.strip()
                                if '=' in line:
                                    key, value = line.split('=', 1)
                                    key = key.strip()
                                    value = value.strip()
                                    
                                    # 값 타입 변환
                                    if value.lower() in ['true', 'false']:
                                        parsed_data[key] = value.lower() == 'true'
                                    elif value.lower() in ['null', 'none', '']:
                                        parsed_data[key] = None
                                    else:
                                        try:
                                            # 숫자 변환 시도
                                            if '.' in value:
                                                parsed_data[key] = float(value)
                                            else:
                                                parsed_data[key] = int(value)
                                        except ValueError:
                                            # 문자열로 저장
                                            parsed_data[key] = value.strip('"').strip("'")
                            
                            if parsed_data and all(field in parsed_data for field in required_fields):
                                data = parsed_data
                                logger.info(f"✅ Pine Script format 파싱 성공: {list(data.keys())}")
                            else:
                                logger.error(f"❌ Pine Script 파싱 실패 - 필수 필드 없음")
                                
                                # 🆕 AI 긴급 파라미터 생성 시도
                                if 'symbol' in parsed_data and 'action' in parsed_data:
                                    logger.info(f"🚨 AI 긴급 파라미터 생성 시도...")
                                    emergency_params = ai_emergency_parameters(parsed_data['symbol'], parsed_data['action'])
                                    
                                    if emergency_params:
                                        # AI가 생성한 파라미터로 data 구성
                                        data = {
                                            'symbol': parsed_data['symbol'],
                                            'action': parsed_data['action'],
                                            'position_percent': emergency_params.percentage,
                                            'stop_loss_price': emergency_params.stop_loss_price,
                                            'take_profit_price': emergency_params.take_profit_price,
                                            'source': 'ai_emergency'
                                        }
                                        logger.info(f"✅ AI 긴급 파라미터로 복구 성공")
                                    else:
                                        return jsonify({'error': 'Failed to parse webhook data and AI recovery failed'}), 400
                                else:
                                    return jsonify({'error': 'Failed to parse webhook data - missing required fields'}), 400
                                
                        except Exception as pe:
                            logger.error(f"❌ Pine Script 파싱 오류: {pe}")
                            return jsonify({'error': 'Invalid data format'}), 400
                        
                except Exception as regex_error:
                    logger.error(f"❌ 정규식 파싱 오류: {regex_error}")
                    return jsonify({'error': 'Failed to extract required fields'}), 400
        
        # 기본 검증
        if not data:
            logger.error("❌ No data received in webhook")
            return jsonify({'error': 'No data received'}), 400
        
        logger.info(f"📋 최종 파싱된 데이터 키: {list(data.keys())}")
        
        # null 안전 파싱 - 모든 필드에 대해 null/None 처리
        def safe_get_float(data, key, default=None):
            """null, 'null', '', None을 안전하게 처리"""
            value = data.get(key)
            if value is None or value == 'null' or value == '':
                return default
            try:
                return float(value)
            except (ValueError, TypeError):
                logger.warning(f"⚠️ {key} 변환 실패: {value} → {default} 사용")
                return default
        
        action = data.get('action')
        original_action = action  # 원래 액션 저장 (modify 케이스를 위해)
        symbol = data.get('symbol', 'BTC/USDT')
        
        # 숫자 필드 안전 파싱 (null 허용)
        entry_price = safe_get_float(data, 'entry_price')
        stop_loss = safe_get_float(data, 'stop_loss')
        take_profit = safe_get_float(data, 'take_profit')
        exit_price = safe_get_float(data, 'exit_price')
        profit_percent = safe_get_float(data, 'profit_percent', 0)
        trailing_stop_percent = safe_get_float(data, 'trailing_stop_percent')
        trailing_activation_percent = safe_get_float(data, 'trailing_activation_percent')
        
        # 문자열 필드 안전 파싱
        position_type = data.get('position_type', 'normal')
        exit_reason = data.get('exit_reason', 'manual')
        
        message = json.dumps(data, ensure_ascii=False) if isinstance(data, dict) else str(data)
        
        logger.info(f"📊 웹훅 수신 - 심볼: {symbol}, 액션: {action}")
        logger.info(f"💰 파싱된 가격 정보:")
        logger.info(f"   - Entry: {entry_price}")
        logger.info(f"   - Stop Loss: {stop_loss}")
        logger.info(f"   - Take Profit: {take_profit}")
        logger.info(f"   - Exit: {exit_price}")
        
        # 필수 필드 검증 (action과 symbol은 필수)
        if not action or not symbol:
            error_msg = f"필수 필드 누락 - action: {action}, symbol: {symbol}"
            logger.error(f"❌ {error_msg}")
            return jsonify({'error': error_msg}), 400
        
        # 심볼 매핑 테이블 (정규화 전에 수행!)
        symbol_mapping = {
            'BTCUSDT': 'BTC/USDT',
            'BTCUSDT.P': 'BTC/USDT',
            'SAHARAUSDT': 'SAHARA/USDT',
            'SAHARAUSDT.P': 'SAHARA/USDT',
            'ETHUSDT': 'ETH/USDT',
            'ETHUSDT.P': 'ETH/USDT',
            'RESOLVUSDT': 'RESOLV/USDT',
            'RESOLVUSDT.P': 'RESOLV/USDT',
            'BIOUSDT': 'BIO/USDT',
            'BIOUSDT.P': 'BIO/USDT',
            'UNIUSDT': 'UNI/USDT',
            'UNIUSDT.P': 'UNI/USDT',
            'PENGUUSDT': 'PENGU/USDT',
            'PENGUUSDT.P': 'PENGU/USDT',
            'UMAUSDT': 'UMA/USDT',
            'UMAUSDT.P': 'UMA/USDT',
            'COMPUSDT': 'COMP/USDT',
            'COMPUSDT.P': 'COMP/USDT',
            'XLMUSDT': 'XLM/USDT',
            'XLMUSDT.P': 'XLM/USDT',
            'DOTUSDT': 'DOT/USDT',
            'DOTUSDT.P': 'DOT/USDT',
            'ENAUSDT': 'ENA/USDT',
            'ENAUSDT.P': 'ENA/USDT',
            'RLCUSDT': 'RLC/USDT',
            'RLCUSDT.P': 'RLC/USDT',
            'ETHFIUSDT': 'ETHFI/USDT',
            'ETHFIUSDT.P': 'ETHFI/USDT',
            'SOLUSDT': 'SOL/USDT',
            'SOLUSDT.P': 'SOL/USDT',
            'PYTHUSDT': 'PYTH/USDT',
            'PYTHUSDT.P': 'PYTH/USDT',
            'LINKUSDT': 'LINK/USDT',
            'LINKUSDT.P': 'LINK/USDT',
            'ADAUSDT': 'ADA/USDT',
            'ADAUSDT.P': 'ADA/USDT',
            'XRPUSDT': 'XRP/USDT',
            'XRPUSDT.P': 'XRP/USDT',
            'BNBUSDT': 'BNB/USDT',
            'BNBUSDT.P': 'BNB/USDT',
            'DOGEUSDT': 'DOGE/USDT',
            'DOGEUSDT.P': 'DOGE/USDT',
            'ACHUSDT': 'ACH/USDT',
            'ACHUSDT.P': 'ACH/USDT',
            'CRVUSDT': 'CRV/USDT',
            'CRVUSDT.P': 'CRV/USDT',
            'RONINUSDT': 'RONIN/USDT',
            'RONINUSDT.P': 'RONIN/USDT',
            'BCHUSDT': 'BCH/USDT',
            'BCHUSDT.P': 'BCH/USDT',
            'LSKUSDT': 'LSK/USDT',
            'LSKUSDT.P': 'LSK/USDT',
            'HBARUSDT': 'HBAR/USDT',
            'HBARUSDT.P': 'HBAR/USDT',
            'AGLDUSDT': 'AGLD/USDT',
            'AGLDUSDT.P': 'AGLD/USDT',
            'ONDOUSDT': 'ONDO/USDT',
            'ONDOUSDT.P': 'ONDO/USDT',
            'HOMEUSDT': 'HOME/USDT',
            'HOMEUSDT.P': 'HOME/USDT',
            'TRXUSDT': 'TRX/USDT',
            'TRXUSDT.P': 'TRX/USDT',
            'ASTERUSDT': 'ASTER/USDT',            
            'ASTERUSDT.P': 'ASTER/USDT',
            'DASHUSDT': 'DASH/USDT',
            'DASHUSDT.P': 'DASH/USDT',
            'TRUMPUSDT': 'TRUMP/USDT',
            'TRUMPUSDT.P': 'TRUMP/USDT',
            'SUIUSDT': 'SUI/USDT',
            'SUIUSDT.P': 'SUI/USDT',
            'WLDUSDT': 'WLD/USDT',
            'WLDUSDT.P': 'WLD/USDT',
            'GIGGLEUSDT': 'GIGGLE/USDT',
            'GIGGLEUSDT.P': 'GIGGLE/USDT',
            'LTCUSDT': 'LTC/USDT',
            'LTCUSDT.P': 'LTC/USDT',
            'DUSKUSDT': 'DUSK/USDT',
            'DUSKUSDT.P': 'DUSK/USDT',
            'FETUSDT': 'FET/USDT',
            'FETUSDT.P': 'FET/USDT',
            'PENDLEUSDT': 'PENDLE/USDT',
            'PENDLEUSDT.P': 'PENDLE/USDT',
            'FILUSDT': 'FIL/USDT',
            'FILUSDT.P': 'FIL/USDT',
            'ARUSDT': 'AR/USDT',
            'ARUSDT.P': 'AR/USDT',
            'OGUSDT': 'OG/USDT',
            'OGUSDT.P': 'OG/USDT',
            'FUSDT': 'F/USDT',
            'FUSDT.P': 'F/USDT',
            'TAOUSDT': 'TAO/USDT',
            'TAOUSDT.P': 'TAO/USDT',
            'RAYSOLUSDT': 'RAYSOL/USDT',
            'RAYSOLUSDT.P': 'RAYSOL/USDT',
            'COTIUSDT': 'COTI/USDT',
            'COTIUSDT.P': 'COTI/USDT',
            'SOONUSDT': 'SOON/USDT',
            'SOONUSDT.P': 'SOON/USDT',
            'KERNELUSDT': 'KERNEL/USDT',
            'KERNELUSDT.P': 'KERNEL/USDT',
            'SYNUSDT': 'SYN/USDT',
            'SYNUSDT.P': 'SYN/USDT',
            'HYPEUSDT': 'HYPE/USDT',
            'HYPEUSDT.P': 'HYPE/USDT',
            'API3USDT': 'API3/USDT',
            'API3USDT.P': 'API3/USDT',
            'KAITOUSDT': 'KAITO/USDT',
            'KAITOUSDT.P': 'KAITO/USDT',
            'AEROUSDT': 'AERO/USDT',
            'AEROUSDT.P': 'AERO/USDT',
            'APTUSDT': 'APT/USDT',
            'APTUSDT.P': 'APT/USDT',
            'PIPPINUSDT': 'PIPPIN/USDT',
            'PIPPINUSDT.P': 'PIPPIN/USDT',
            'NEARUSDT': 'NEAR/USDT',
            'NEARUSDT.P': 'NEAR/USDT',
            'MANAUSDT': 'MANA/USDT',
            'MANAUSDT.P': 'MANA/USDT',           
            'ZECUSDT': 'ZEC/USDT',
            'ZECUSDT.P': 'ZEC/USDT',
            'POLUSDT': 'POL/USDT',
            'POLUSDT.P': 'POL/USDT',
            'SANDUSDT': 'SAND/USDT',
            'SANDUSDT.P': 'SAND/USDT',            
            'GOATUSDT': 'GOAT/USDT',
            'GOATUSDT.P': 'GOAT/USDT',
            'PARTIUSDT': 'PARTI/USDT',
            'PARTIUSDT.P': 'PARTI/USDT',
            'FLOWUSDT': 'FLOW/USDT',
            'FLOWUSDT.P': 'FLOW/USDT',
            'AAVEUSDT': 'AAVE/USDT',
            'AAVEUSDT.P': 'AAVE/USDT',      
            'PUMPUSDT': 'PUMP/USDT',
            'PUMPUSDT.P': 'PUMP/USDT',  
            'XPLUSDT': 'XPL/USDT',
            'XPLUSDT.P': 'XPL/USDT',    
            'TONUSDT': 'TON/USDT',
            'TONUSDT.P': 'TON/USDT',
            'ICPUSDT': 'ICP/USDT',
            'ICPUSDT.P': 'ICP/USDT', 
            'HBARUSDT': 'HBAR/USDT',
            'HBARUSDT.P': 'HBAR/USDT',    
            'ATOMUSDT': 'ATOM/USDT',
            'ATOMUSDT.P': 'ATOM/USDT', 
            'OMUSDT': 'OM/USDT',
            'OMUSDT.P': 'OM/USDT', 
            'SENTIUSDT': 'SENTI/USDT',
            'SENTIUSDT.P': 'SENTI/USDT', 
            'ALLOUSDT': 'ALLO/USDT',
            'ALLOUSDT.P': 'ALLO/USDT', 
            'AXUSDT': 'AX/USDT',
            'AXUSDT.P': 'AX/USDT', 
            'MIRAUSDT': 'MIRA/USDT',
            'MIRAUSDT.P': 'MIRA/USDT', 
            'REDUSDT': 'RED/USDT',
            'REDUSDT.P': 'RED/USDT', 
            'FOGOUSDT': 'FOGO/USDT',
            'FOGOUSDT.P': 'FOGO/USDT', 
            'YBUSDT': 'YB/USDT',
            'YBUSDT.P': 'YB/USDT',
            'ROSEUSDT': 'ROSE/USDT',
            'ROSEUSDT.P': 'ROSE/USDT', 
            'SYRUPUSDT': 'SYRUP/USDT',
            'SYRUPUSDT.P': 'SYRUP/USDT', 
        }
        
        original_symbol = symbol
        # 심볼 매핑 적용
        if symbol in symbol_mapping:
            symbol = symbol_mapping[symbol]
            logger.info(f"🔄 심볼 매핑: {original_symbol} → {symbol}")
        # 매핑이 없는 경우만 정규화
        elif not symbol.endswith('/USDT'):
            # .P 제거 후 정규화
            clean_symbol = symbol.replace('.P', '').replace('.p', '')
            if 'USDT' in clean_symbol:
                base = clean_symbol.replace('USDT', '')
                symbol = f"{base}/USDT"
                logger.info(f"🔄 심볼 정규화: {original_symbol} → {symbol}")
            else:
                symbol = f"{clean_symbol}/USDT"
                logger.info(f"🔄 심볼 정규화: {original_symbol} → {symbol}")
        
        # 심볼 설정 확인 (🆕 v7.3: 정규화된 심볼 사용)
        if not is_symbol_configured(symbol):
            error_msg = f'심볼 {symbol}이(가) 설정되지 않음 (원본: {original_symbol})'
            logger.error(f"❌ {error_msg}")
            
            # 텔레그램 알림
            if ENABLE_TELEGRAM:
                notify_msg = f"""
❌ <b>미등록 심볼 감지</b>

<b>원본 심볼:</b> {original_symbol}
<b>변환 심볼:</b> {symbol}
<b>액션:</b> {action}

⚠️ SYMBOL_CONFIG에 해당 심볼을 추가해주세요.

⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
                """.strip()
                send_telegram_notification(notify_msg, 'error')
            
            return jsonify({'error': error_msg}), 400
        
        if not get_symbol_config(symbol).get('enabled', True):
            error_msg = f'심볼 {symbol}이(가) 비활성화됨'
            logger.warning(f"⚠️ {error_msg}")
            return jsonify({'error': error_msg}), 400
        
        logger.info(f"✅ 심볼 검증 완료: {symbol}")
        
        # 심볼 설정 가져오기 (🆕 v7.3: 정규화된 심볼 사용)
        symbol_config = get_symbol_config(symbol)
        
        # AI 검증이 활성화되어 있는지 확인
        use_ai = symbol_config.get('ai_validation', True)
        
        if use_ai:
            # 시장 데이터 수집
            market_data = get_market_data(symbol)
            if not market_data:
                return jsonify({'error': 'Failed to collect market data'}), 500
            
            # 최근 거래 내역 조회
            conn = get_db_connection()
            recent_trades = get_recent_trades(conn, symbol)
            conn.close()
            
            # AI 검증 (close_position 포함)
            ai_decision = ai_validate_signal(symbol, action, market_data, recent_trades, message_data=data)
            
            if not ai_decision:
                return jsonify({'error': 'AI validation failed'}), 500
            
            # 🆕 반대 진입 처리
            if ai_decision.get('decision') == 'reverse':
                original_action = action
                action = ai_decision.get('modified_action', 'sell' if original_action == 'buy' else 'buy')
                
                logger.warning(f"🔄 REVERSE ENTRY: {original_action} → {action}")
                
                # 텔레그램 알림
                reverse_message = f"""
🔄 <b>반대 진입 실행</b>

<b>심볼:</b> {symbol}
<b>원본 신호:</b> {original_action.upper()}
<b>변경된 방향:</b> {action.upper()}
<b>이유:</b> 극단적 과매수/과매도 상태
<b>포지션 크기:</b> {ai_decision.get('percentage', 30)}%
<b>신뢰도:</b> {ai_decision.get('confidence', 0.5):.1%}

⚠️ 반대 진입은 리스크가 높으니 주의하세요.

⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
                """.strip()
                send_telegram_notification(reverse_message, 'warning')
                
                # decision을 approve로 변경하여 거래 실행
                ai_decision['decision'] = 'approve'
                
                # 포지션 크기 조정 (보수적)
                if ai_decision.get('percentage', 30) > 50:
                    ai_decision['percentage'] = 30
            
            # close_position 액션 처리
            if action in ['close', 'close_position']:
                # AI 결정에 따른 처리
                if ai_decision['decision'] == 'reject':
                    message = f"""
⚠️ <b>AI 청산 신호 거부</b>

<b>심볼:</b> {symbol}
<b>원래 신호:</b> CLOSE POSITION
<b>AI 결정:</b> REJECT
<b>신뢰도:</b> {ai_decision['confidence']:.1%}
<b>긴급도:</b> {ai_decision.get('urgency', 'N/A')}
<b>이유:</b> {ai_decision['reason']}

⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
                    """.strip()
                    send_telegram_notification(message, 'warning')
                    return jsonify({
                        'status': 'rejected',
                        'reason': ai_decision['reason'],
                        'confidence': ai_decision['confidence']
                    }), 200
                
                # AI가 승인한 경우 포지션 청산 실행
                try:
                    # 🆕 모든 유저의 포지션 청산 및 TP/SL 자동 취소
                    success_count = close_position_for_all_users(symbol)
                    
                    if success_count > 0:
                        # Primary User로 포지션 정보 조회 (메시지 표시용)
                        try:
                            ticker = exchange.fetch_ticker(symbol)
                            current_price = ticker['last']
                            
                            message = f"""
✅ <b>포지션 청산 완료 (Multi-User)</b>

<b>심볼:</b> {symbol}
<b>청산 성공:</b> {success_count}/{len(exchanges)}명
<b>청산가:</b> ${current_price:,.2f}
<b>청산 사유:</b> {data.get('exit_reason', 'Manual close')}

<b>AI 검증:</b>
• 신뢰도: {ai_decision['confidence']:.1%}
• 긴급도: {ai_decision.get('urgency', 'N/A')}
• 이유: {ai_decision['reason']}

⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
                            """.strip()
                            send_telegram_notification(message, 'success')
                        except Exception as msg_error:
                            logger.error(f"메시지 전송 오류: {msg_error}")
                        
                        # 포지션 추적에서 제거 + 🆕 v7.8: DB 기록
                        if symbol in current_positions:
                            record_completed_trade_with_binance(symbol, current_positions[symbol], 
                                                               close_reason=data.get('exit_reason', 'webhook_close'))
                            
                            # 🆕 v7.8: trades 테이블에도 종료 기록
                            try:
                                conn = get_db_connection()
                                c = conn.cursor()
                                c.execute("""INSERT INTO trades 
                                          (timestamp, symbol, action, ai_decision, confidence, reason, 
                                           current_price, trade_type, reflection, percentage, entry_price)
                                          VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                                          (datetime.now().isoformat(), symbol, 'close',
                                           'approve', ai_decision['confidence'],
                                           f"Close: {data.get('exit_reason', 'webhook')} | AI_VALIDATED",
                                           current_price, 'CLOSE_AI',
                                           None, 0, current_positions[symbol].get('entry_price', 0)))
                                conn.commit()
                                conn.close()
                            except Exception as db_err:
                                logger.warning(f"trades 기록 실패 (무시): {db_err}")
                            
                            del current_positions[symbol]
                            clear_peak_profit(symbol)
                        
                        return jsonify({
                            'status': 'closed',
                            'symbol': symbol,
                            'success_count': success_count,
                            'total_users': len(exchanges),
                            'ai_confidence': ai_decision['confidence']
                        }), 200
                    else:
                        return jsonify({
                            'status': 'no_position',
                            'message': f'No open position found for {symbol}'
                        }), 200
                    logger.error(f"포지션 청산 오류: {str(e)}", exc_info=True)
                    error_message = f"""
❌ <b>포지션 청산 오류</b>

<b>심볼:</b> {symbol}
<b>오류:</b> {str(e)}
⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
                    """.strip()
                    send_telegram_notification(error_message, 'error')
                    return jsonify({'error': str(e)}), 500
                        
                except Exception as e:
                    logger.error(f"포지션 청산 오류: {str(e)}", exc_info=True)
                    error_message = f"""
❌ <b>포지션 청산 오류</b>

<b>심볼:</b> {symbol}
<b>오류:</b> {str(e)}
⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
                    """.strip()
                    send_telegram_notification(error_message, 'error')
                    return jsonify({'error': str(e)}), 500
            
            # buy/sell 액션 처리
            # AI 결정에 따른 처리
            if ai_decision['decision'] == 'reject':
                message = f"""
⚠️ <b>AI 신호 거부</b>

<b>심볼:</b> {symbol}
<b>원래 신호:</b> {action.upper()}
<b>AI 결정:</b> REJECT
<b>신뢰도:</b> {ai_decision['confidence']:.1%}
<b>이유:</b> {ai_decision['reason']}

⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
                """.strip()
                send_telegram_notification(message, 'warning')
                return jsonify({
                    'status': 'rejected',
                    'reason': ai_decision['reason'],
                    'confidence': ai_decision['confidence']
                }), 200
            
            elif ai_decision['decision'] == 'modify':
                # AI가 수정한 매매 신호 사용
                action = ai_decision['modified_action']
                
                # 텔레그램 알림 전송 (modify 케이스 추가)
                message = f"""
🔄 <b>AI 신호 수정</b>

<b>심볼:</b> {symbol}
<b>원래 신호:</b> {original_action.upper()}
<b>수정된 신호:</b> {action.upper()}
<b>AI 결정:</b> MODIFY
<b>신뢰도:</b> {ai_decision['confidence']:.1%}
<b>포지션 크기:</b> {ai_decision['percentage']}%
<b>이유:</b> {ai_decision['reason']}

<b>수정된 가격:</b>
• 손절가: ${ai_decision['stop_loss_price']:.4f}
• 목표가: ${ai_decision['take_profit_price']:.4f}
• P/L 비율: {ai_decision['pl_ratio']:.1f}

⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
                """.strip()
                send_telegram_notification(message, 'info')
                
                if action == 'hold':
                    return jsonify({'status': 'hold', 'reason': ai_decision['reason']}), 200
            
            # AI가 승인하거나 수정한 경우 거래 실행
            stop_loss_price = ai_decision['stop_loss_price']
            take_profit_price = ai_decision['take_profit_price']
            pl_ratio = ai_decision['pl_ratio']
            position_percent = ai_decision['percentage']
            
        else:
            # AI 검증 없이 처리
            
            # 🆕 v7.7: close_position 처리 (AI 비활성 시에도 동작)
            if action in ['close', 'close_position']:
                try:
                    success_count = close_position_for_all_users(symbol)
                    
                    if success_count > 0:
                        try:
                            ticker = exchange.fetch_ticker(symbol)
                            current_price = ticker['last']
                            
                            message = f"""
✅ <b>포지션 청산 완료 (Multi-User)</b>

<b>심볼:</b> {symbol}
<b>청산 성공:</b> {success_count}/{len(exchanges)}명
<b>청산가:</b> ${current_price:,.2f}
<b>청산 사유:</b> {data.get('exit_reason', 'TradingView signal')}

<b>AI 검증:</b> OFF

⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
                            """.strip()
                            send_telegram_notification(message, 'success')
                        except Exception as msg_error:
                            logger.error(f"메시지 전송 오류: {msg_error}")
                        
                        # current_positions 업데이트 + 🆕 v7.8: DB 기록
                        if symbol in current_positions:
                            record_completed_trade_with_binance(symbol, current_positions[symbol],
                                                               close_reason=data.get('exit_reason', 'webhook_close_no_ai'))
                            
                            # 🆕 v7.8: trades 테이블에도 종료 기록 (AI OFF)
                            try:
                                conn = get_db_connection()
                                c = conn.cursor()
                                c.execute("""INSERT INTO trades 
                                          (timestamp, symbol, action, ai_decision, confidence, reason, 
                                           current_price, trade_type, reflection, percentage, entry_price)
                                          VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                                          (datetime.now().isoformat(), symbol, 'close',
                                           'approve', 1.0,
                                           f"Close: {data.get('exit_reason', 'webhook')} | NO_AI",
                                           current_price, 'CLOSE_NO_AI',
                                           None, 0, current_positions[symbol].get('entry_price', 0)))
                                conn.commit()
                                conn.close()
                            except Exception as db_err:
                                logger.warning(f"trades 기록 실패 (무시): {db_err}")
                            
                            del current_positions[symbol]
                        
                        return jsonify({
                            'status': 'success',
                            'action': 'close_position',
                            'symbol': symbol,
                            'closed_users': success_count
                        }), 200
                    else:
                        logger.warning(f"⚠️ {symbol} 청산할 포지션 없음")
                        return jsonify({
                            'status': 'no_position',
                            'symbol': symbol
                        }), 200
                        
                except Exception as e:
                    logger.error(f"포지션 청산 오류: {str(e)}", exc_info=True)
                    error_message = f"""
❌ <b>포지션 청산 오류</b>

<b>심볼:</b> {symbol}
<b>오류:</b> {str(e)}
⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
                    """.strip()
                    send_telegram_notification(error_message, 'error')
                    return jsonify({'error': str(e)}), 500
            
            # buy/sell 처리를 위한 기본값 설정
            ticker = exchange.fetch_ticker(symbol)
            current_price = ticker['last']
            
            # 🆕 AUTO_TP_SL_GENERATION 옵션에 따라 분기
            if AUTO_TP_SL_GENERATION:
                # 웹훅 데이터 우선 사용, null이면 기본값 적용
                if action == 'buy':
                    stop_loss_price = stop_loss if stop_loss is not None else (current_price * 0.98)  # -2%
                    take_profit_price = take_profit if take_profit is not None else (current_price * 1.04)  # +4%
                else:
                    stop_loss_price = stop_loss if stop_loss is not None else (current_price * 1.02)  # +2%
                    take_profit_price = take_profit if take_profit is not None else (current_price * 0.96)  # -4%
                logger.info(f"기본값 사용 (자동생성 ON) - SL: {stop_loss_price:.4f}, TP: {take_profit_price:.4f}")
            else:
                # 웹훅 TP/SL이 있으면 사용, null이면 None 유지 (TP/SL 주문 안 걸림)
                stop_loss_price = stop_loss  # None일 수 있음
                take_profit_price = take_profit  # None일 수 있음
                logger.info(f"TP/SL 자동생성 OFF - SL: {stop_loss_price}, TP: {take_profit_price} (None이면 TP/SL 미설정)")
            
            pl_ratio = 2.0
            position_percent = get_symbol_config(symbol).get('position_size_percent', 10)  # 🆕 v7.3: 정규화된 심볼 사용
        
        # 🆕 TP/SL 현실적 조정 (매물대 및 지지/저항선 기반)
        # AI 검증 여부와 관계없이 항상 실행 — 단, TP/SL이 None이면 스킵
        if action in ['buy', 'sell'] and stop_loss_price is not None and take_profit_price is not None:
            try:
                # 현재가 가져오기
                ticker = exchange.fetch_ticker(symbol)
                current_price_for_adjust = ticker['last']
                
                # 시장 데이터 수집 (아직 없는 경우)
                if 'market_data' not in locals() or not market_data:
                    market_data = get_market_data(symbol)
                
                if market_data:
                    # TP/SL 조정 실행
                    adjustment_result = adjust_tp_sl_based_on_levels(
                        symbol, action, current_price_for_adjust,
                        stop_loss_price, take_profit_price, market_data
                    )
                    
                    if adjustment_result['is_adjusted']:
                        logger.info(f"🎯 TP/SL 조정 완료:")
                        logger.info(f"   {adjustment_result['sl_reason']}")
                        logger.info(f"   {adjustment_result['tp_reason']}")
                        
                        # 조정된 가격 적용
                        stop_loss_price = adjustment_result['adjusted_sl']
                        take_profit_price = adjustment_result['adjusted_tp']
                        
                        # 텔레그램 알림 (조정된 경우에만)
                        if ENABLE_TELEGRAM:
                            adjust_msg = f"""
💡 <b>TP/SL 자동 조정</b>

<b>심볼:</b> {symbol}
<b>방향:</b> {action.upper()}

<b>조정 전:</b>
• SL: ${adjustment_result.get('adjusted_sl', stop_loss_price) / (1 + 0.005 if action == 'buy' else 1 - 0.005):.4f}
• TP: ${adjustment_result.get('adjusted_tp', take_profit_price) / (1 - 0.005 if action == 'buy' else 1 + 0.005):.4f}

<b>조정 후:</b>
• SL: ${stop_loss_price:.4f}
• TP: ${take_profit_price:.4f}

<b>조정 사유:</b>
• SL: {adjustment_result['sl_reason']}
• TP: {adjustment_result['tp_reason']}

<b>주요 지지/저항선:</b>
"""
                            # 지지/저항선 정보 추가
                            if adjustment_result.get('volume_profile'):
                                vp = adjustment_result['volume_profile']
                                if vp.get('support_levels'):
                                    supports = ", ".join([f"${s:.2f}" for s in vp['support_levels'][:2]])
                                    adjust_msg += f"• 지지: {supports}\n"
                                if vp.get('resistance_levels'):
                                    resistances = ", ".join([f"${r:.2f}" for r in vp['resistance_levels'][:2]])
                                    adjust_msg += f"• 저항: {resistances}\n"
                            
                            adjust_msg += f"\n⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                            send_telegram_notification(adjust_msg.strip(), 'info')
                    else:
                        logger.info(f"✅ TP/SL 조정 불필요 (현실적 범위 내)")
                else:
                    logger.warning(f"⚠️ 시장 데이터 수집 실패 - TP/SL 조정 스킵")
                    
            except Exception as adjust_error:
                logger.error(f"❌ TP/SL 조정 오류: {adjust_error}")
                logger.error(f"   원본 TP/SL 사용")
        
        # 거래 실행 (buy/sell만)
        if action in ['buy', 'sell']:
            # 잔고 확인
            balance_info = exchange.fetch_balance()
            usdt_balance = balance_info['USDT']['free']
            
            # 포지션 크기 계산
            position_size = usdt_balance * (position_percent / 100)
            
            # 레버리지 설정
            leverage = set_leverage(symbol)
            if not leverage:
                error_msg = f"""
❌ <b>레버리지 설정 실패</b>

<b>심볼:</b> {symbol}
⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
                """.strip()
                send_telegram_notification(error_msg, 'error')
                return jsonify({'error': 'Failed to set leverage'}), 500
            
            # 레버리지 적용한 실제 수량 계산
            ticker = exchange.fetch_ticker(symbol)
            current_price = ticker['last']
            amount = (position_size * leverage) / current_price
            
            # 트레일링 스탑 설정
            # trailing_stop_percent가 유효하면 trailing 주문 발생
            # trailing_activation_percent가 null이면 0 (즉시 활성화 = activatePrice 미설정)
            trailing_stop = trailing_stop_percent  # None일 수 있음
            trailing_activation = trailing_activation_percent if trailing_activation_percent is not None else (0 if trailing_stop is not None else None)
            
            # 주문 실행
            # 🆕 모든 유저에 대해 거래 실행
            orders = execute_trade_for_all_users(
                symbol, action, amount, 
                stop_loss_price, take_profit_price,
                trailing_stop, trailing_activation
            )
            
            if orders:
                # 포지션 추적 (entry_time, leverage, position_type 추가)
                current_positions[symbol] = {
                    'side': action,
                    'entry_price': orders['actual_entry'],
                    'amount': orders['adjusted_amount'],
                    'stop_loss': stop_loss_price,
                    'take_profit': take_profit_price,
                    'trailing_stop_percent': trailing_stop,
                    'trailing_activation_percent': trailing_activation,
                    'entry_time': datetime.now(),  # 진입 시간 추가
                    'leverage': symbol_config.get('leverage', 10),  # 레버리지 추가
                    'position_size_usdt': position_size,  # 포지션 크기 추가
                    'position_type': 'auto'  # 자동 거래 표시
                }
                
                # 🔥 포지션 진입 즉시 DB 기록 (대시보드 표시용)
                try:
                    conn = get_db_connection()
                    c = conn.cursor()
                    
                    # position_history에 진입 기록
                    c.execute("""INSERT INTO position_history 
                                (timestamp, symbol, side, amount, entry_price, current_price,
                                 pnl_usdt, pnl_percent, position_value, required_margin, liquidation_price)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                              (datetime.now().isoformat(), symbol, action, orders['adjusted_amount'], 
                               orders['actual_entry'], orders['actual_entry'],
                               0, 0,  # 진입 시점 PnL은 0
                               position_size, position_size / symbol_config.get('leverage', 10),
                               stop_loss_price if stop_loss_price is not None else 0))
                    
                    # 🆕 v7.8: trades 테이블에도 진입 기록 (AI ON/OFF 무관)
                    ai_mode = "AI_VALIDATED" if use_ai else "NO_AI"
                    c.execute("""INSERT INTO trades 
                              (timestamp, symbol, action, ai_decision, confidence, reason, 
                               current_price, trade_type, reflection, percentage, entry_price)
                              VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                              (datetime.now().isoformat(), symbol, action, 
                               'approve', ai_decision.get('confidence', 0) if use_ai else 1.0,
                               f"Entry: {action} @ ${orders['actual_entry']:.4f} | AI={ai_mode}",
                               orders['actual_entry'], ai_mode,
                               None, position_percent, orders['actual_entry']))
                    
                    conn.commit()
                    conn.close()
                    logger.info(f"✅ Position entry recorded to DB: {symbol} {action} (mode={ai_mode})")
                except Exception as db_error:
                    logger.error(f"❌ DB 기록 실패 (포지션은 정상 진입됨): {db_error}")
                    # DB 실패해도 포지션 추적은 계속
                
                # 알림 전송
                entry_message = format_position_entry_message(
                    symbol, action, orders['adjusted_amount'], orders['actual_entry'],
                    stop_loss_price, take_profit_price,
                    pl_ratio, position_size, usdt_balance,
                    trailing_stop, trailing_activation
                )
                
                if use_ai:
                    entry_message += f"\n<b>AI 신뢰도:</b> {ai_decision['confidence']:.1%}"
                
                send_telegram_notification(entry_message, 'high')
                
                return jsonify({
                    'status': 'success',
                    'action': action,
                    'symbol': symbol,
                    'amount': orders['adjusted_amount'],
                    'entry_price': orders['actual_entry'],
                    'stop_loss': stop_loss_price,
                    'take_profit': take_profit_price,
                    'ai_confidence': ai_decision['confidence'] if use_ai else None
                }), 200
            else:
                error_msg = f"""
❌ <b>주문 실행 실패</b>

<b>심볼:</b> {symbol}
<b>액션:</b> {action.upper()}
⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
                """.strip()
                send_telegram_notification(error_msg, 'error')
                return jsonify({'error': 'Order execution failed'}), 500
        
        else:
            return jsonify({'error': f'Unknown action: {action}'}), 400
            
    except Exception as e:
        logger.error(f"웹훅 처리 오류: {str(e)}", exc_info=True)
        
        error_message = f"""
❌ <b>웹훅 처리 오류</b>

<b>오류:</b> {str(e)}
⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
        """.strip()
        
        send_telegram_notification(error_message, 'error')
        return jsonify({'error': str(e)}), 500

@app.route('/ai-monitor/start', methods=['POST'])
def start_monitoring():
    """AI 모니터링 시작"""
    start_ai_monitoring()
    return jsonify({
        'status': 'success',
        'message': f'AI monitoring started with {AI_MONITOR_INTERVAL} minute intervals'
    }), 200

@app.route('/ai-monitor/stop', methods=['POST'])
def stop_monitoring():
    """AI 모니터링 중지"""
    stop_ai_monitoring()
    return jsonify({
        'status': 'success',
        'message': 'AI monitoring stopped'
    }), 200

@app.route('/ai-monitor/status', methods=['GET'])
def monitor_status():
    """AI 모니터링 상태 확인"""
    return jsonify({
        'monitoring_active': ai_monitor_running,
        'interval_minutes': AI_MONITOR_INTERVAL,
        'positions_monitored': list(current_positions.keys()),
        'total_positions': len(current_positions)
    }), 200

@app.route('/ai-monitor/force', methods=['POST'])
def force_monitor():
    """즉시 AI 모니터링 실행 (🆕 v7.3: 먼저 동기화 수행)"""
    # 🆕 먼저 거래소와 동기화 (수동 포지션 감지용)
    sync_count = sync_positions_from_exchange()
    
    if not current_positions:
        return jsonify({
            'status': 'info',
            'message': 'No positions to monitor (sync completed, no active positions)',
            'synced_count': sync_count
        }), 200
    
    monitored, exits = ai_monitoring_cycle(skip_sync=True)  # 이미 sync 했으므로 건너뛰기
    
    return jsonify({
        'status': 'success',
        'positions_monitored': monitored,
        'exit_decisions': exits,
        'synced_count': sync_count
    }), 200

@app.route('/status', methods=['GET'])
def status():
    """시스템 상태 확인 (🆕 자동/수동 포지션 구분)"""
    enabled_symbols = [s for s, c in SYMBOL_CONFIG.items() if c.get('enabled', True)]
    ai_enabled_symbols = [s for s, c in SYMBOL_CONFIG.items() if c.get('ai_validation', True)]
    ai_monitored_symbols = [s for s, c in SYMBOL_CONFIG.items() if c.get('ai_monitoring', True)]
    
    # 🆕 포지션 타입별 카운트
    auto_count = sum(1 for pos in current_positions.values() if pos.get('position_type', 'auto') == 'auto')
    manual_count = sum(1 for pos in current_positions.values() if pos.get('position_type', 'auto') == 'manual')
    
    # 포지션 상세 정보 (🆕 position_type 포함)
    positions_detail = {}
    for symbol, pos in current_positions.items():
        positions_detail[symbol] = {
            'side': pos['side'],
            'entry_price': pos['entry_price'],
            'amount': pos['amount'],
            'position_type': pos.get('position_type', 'auto'),  # 🆕
            'entry_time': pos.get('entry_time', datetime.now()).isoformat() if isinstance(pos.get('entry_time'), datetime) else str(pos.get('entry_time', 'N/A'))
        }
    
    return jsonify({
        'status': 'running',
        'server_port': SERVER_PORT,
        'current_positions': positions_detail,
        'position_count': len(current_positions),
        'auto_position_count': auto_count,  # 🆕
        'manual_position_count': manual_count,  # 🆕
        'telegram_enabled': ENABLE_TELEGRAM,
        'total_symbols': len(enabled_symbols),
        'ai_enabled_symbols': len(ai_enabled_symbols),
        'ai_monitored_symbols': len(ai_monitored_symbols),
        'ai_monitoring_active': ai_monitor_running,
        'ai_monitor_interval': AI_MONITOR_INTERVAL,
        'emergency_drawdown_enabled': EMERGENCY_DRAWDOWN_ENABLED,
        'emergency_drawdown_running': emergency_drawdown_running,
        'symbols': enabled_symbols,
        'timestamp': datetime.now().isoformat()
    }), 200

@app.route('/positions/sync', methods=['POST'])
def sync_positions():
    """거래소 포지션 수동 동기화"""
    try:
        position_count = sync_positions_from_exchange()
        
        return jsonify({
            'status': 'success',
            'message': f'{position_count}개 포지션 동기화 완료',
            'positions': {
                symbol: {
                    'side': pos['side'],
                    'entry_price': pos['entry_price'],
                    'amount': pos['amount']
                } for symbol, pos in current_positions.items()
            }
        }), 200
        
    except Exception as e:
        logger.error(f"포지션 동기화 오류: {str(e)}")
        return jsonify({'error': str(e)}), 500


@app.route('/positions/close', methods=['POST'])
def close_position_api():
    """
    🆕 v7.6: 포지션 수동 종료 API
    모든 유저의 해당 심볼 포지션을 종료합니다.
    
    Request Body:
        {
            "symbol": "BTC/USDT",
            "reason": "Manual close from dashboard"  (optional)
        }
    
    Response:
        {
            "status": "success",
            "symbol": "BTC/USDT",
            "closed_users": 3,
            "total_users": 3,
            "message": "..."
        }
    """
    try:
        data = request.get_json()
        
        if not data or 'symbol' not in data:
            return jsonify({'error': 'symbol is required'}), 400
        
        symbol = data['symbol']
        reason = data.get('reason', 'Manual close from dashboard')
        
        logger.info(f"🔴 수동 포지션 종료 요청: {symbol}")
        logger.info(f"   이유: {reason}")
        
        # 심볼 형식 정규화 (BTCUSDT -> BTC/USDT)
        if '/' not in symbol:
            symbol = symbol[:-4] + '/' + symbol[-4:]  # BTCUSDT -> BTC/USDT
        
        # 모든 유저 포지션 종료
        success_count = 0
        failed_users = []
        closed_details = []
        
        for user_id, user_exchange in exchanges.items():
            user_name = USER_CONFIGS[user_id]['name']
            
            try:
                # 포지션 확인
                positions = user_exchange.fetch_positions([symbol])
                active_position = None
                
                for pos in positions:
                    if float(pos.get('contracts', 0)) != 0:
                        active_position = pos
                        break
                
                if not active_position:
                    logger.info(f"[{user_name}] {symbol} 포지션 없음")
                    continue
                
                # 포지션 정보 저장
                contracts = float(active_position['contracts'])
                side = 'sell' if active_position['side'] == 'long' else 'buy'
                entry_price = float(active_position.get('entryPrice', 0))
                mark_price = float(active_position.get('markPrice', 0))
                unrealized_pnl = float(active_position.get('unrealizedPnl', 0))
                
                # 포지션 청산
                close_order = user_exchange.create_market_order(symbol, side, abs(contracts))
                logger.info(f"[{user_name}] ✅ 포지션 청산: {symbol} {side} {abs(contracts):.6f}")
                
                # TP/SL 자동 취소
                try:
                    cancelled = cancel_symbol_orders(user_exchange, symbol, user_name)
                    if cancelled > 0:
                        logger.info(f"[{user_name}] 🗑️ TP/SL 주문 {cancelled}개 자동 취소")
                except Exception as cancel_err:
                    logger.warning(f"[{user_name}] TP/SL 취소 오류 (무시): {cancel_err}")
                
                closed_details.append({
                    'user': user_name,
                    'contracts': abs(contracts),
                    'side': active_position['side'],
                    'entry_price': entry_price,
                    'close_price': mark_price,
                    'pnl': unrealized_pnl
                })
                
                success_count += 1
                
            except Exception as e:
                logger.error(f"[{user_name}] 포지션 청산 실패: {str(e)}")
                failed_users.append({'user': user_name, 'error': str(e)})
        
        # 내부 포지션 추적에서도 제거 + 🆕 v7.8: DB 기록
        if symbol in current_positions:
            record_completed_trade_with_binance(symbol, current_positions[symbol],
                                               close_reason=reason)
            del current_positions[symbol]
            logger.info(f"🗑️ {symbol} 내부 추적에서 제거 (DB 기록 완료)")
        
        # Peak profit 기록 삭제
        clear_peak_profit(symbol)
        
        # 텔레그램 알림
        if ENABLE_TELEGRAM and success_count > 0:
            total_pnl = sum(d['pnl'] for d in closed_details)
            send_telegram_notification(
                f"🔴 <b>수동 포지션 종료</b>\n\n"
                f"<b>심볼:</b> {symbol}\n"
                f"<b>이유:</b> {reason}\n"
                f"<b>종료된 유저:</b> {success_count}명\n"
                f"<b>총 PnL:</b> ${total_pnl:+.2f}\n\n"
                f"{'⚠️ 실패: ' + ', '.join([f['user'] for f in failed_users]) if failed_users else '✅ 모든 유저 성공'}",
                'warning' if total_pnl < 0 else 'success'
            )
        
        # DB에 기록 (Primary User만)
        if success_count > 0:
            try:
                # 첫 번째 성공한 거래 정보로 기록
                first_close = closed_details[0] if closed_details else {}
                record_trade(
                    symbol=symbol,
                    trade_type='close',
                    side=first_close.get('side', 'unknown'),
                    entry_price=first_close.get('entry_price', 0),
                    exit_price=first_close.get('close_price', 0),
                    amount=first_close.get('contracts', 0),
                    pnl_usdt=sum(d['pnl'] for d in closed_details),
                    pnl_percent=0,  # 계산 복잡하므로 생략
                    position_size_usdt=0,
                    holding_time_minutes=0,
                    close_reason=f"Manual: {reason}",
                    leverage=10,
                    is_win=sum(d['pnl'] for d in closed_details) > 0,
                    position_type='manual'
                )
            except Exception as db_err:
                logger.warning(f"DB 기록 실패 (무시): {db_err}")
        
        return jsonify({
            'status': 'success',
            'symbol': symbol,
            'closed_users': success_count,
            'total_users': len(exchanges),
            'closed_details': closed_details,
            'failed_users': failed_users,
            'message': f'{symbol} 포지션 {success_count}명 종료 완료'
        }), 200
        
    except Exception as e:
        logger.error(f"포지션 종료 API 오류: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return jsonify({'error': str(e)}), 500


@app.route('/positions/list', methods=['GET'])
def list_positions_api():
    """
    🆕 v7.6: 모든 유저의 현재 포지션 조회 API
    
    Response:
        {
            "status": "success",
            "positions": [
                {
                    "symbol": "BTC/USDT",
                    "users": [...]
                }
            ]
        }
    """
    try:
        all_positions = {}
        
        for user_id, user_exchange in exchanges.items():
            user_name = USER_CONFIGS[user_id]['name']
            
            try:
                positions = user_exchange.fetch_positions()
                
                for pos in positions:
                    if float(pos.get('contracts', 0)) != 0:
                        symbol = pos['symbol']
                        
                        if symbol not in all_positions:
                            all_positions[symbol] = {
                                'symbol': symbol,
                                'users': []
                            }
                        
                        all_positions[symbol]['users'].append({
                            'user': user_name,
                            'side': pos['side'],
                            'contracts': float(pos['contracts']),
                            'entry_price': float(pos.get('entryPrice', 0)),
                            'mark_price': float(pos.get('markPrice', 0)),
                            'unrealized_pnl': float(pos.get('unrealizedPnl', 0)),
                            'leverage': int(pos.get('leverage', 10))
                        })
                        
            except Exception as e:
                logger.warning(f"[{user_name}] 포지션 조회 실패: {e}")
        
        return jsonify({
            'status': 'success',
            'positions': list(all_positions.values()),
            'total_symbols': len(all_positions)
        }), 200
        
    except Exception as e:
        logger.error(f"포지션 목록 조회 오류: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/config', methods=['GET', 'POST'])
def config():
    """심볼 설정 관리"""
    global SYMBOL_CONFIG
    
    if request.method == 'GET':
        return jsonify(SYMBOL_CONFIG), 200
    
    elif request.method == 'POST':
        try:
            new_config = request.get_json()
            if not new_config:
                return jsonify({'error': 'No configuration data provided'}), 400
            
            for symbol, settings in new_config.items():
                if symbol in SYMBOL_CONFIG:
                    SYMBOL_CONFIG[symbol].update(settings)
                else:
                    SYMBOL_CONFIG[symbol] = settings
            
            logger.info(f"설정 업데이트 완료: {list(new_config.keys())}")
            
            return jsonify({
                'status': 'success',
                'updated_symbols': list(new_config.keys()),
                'config': SYMBOL_CONFIG
            }), 200
            
        except Exception as e:
            logger.error(f"설정 업데이트 실패: {str(e)}")
            return jsonify({'error': str(e)}), 500

@app.route('/ai-validation/toggle', methods=['POST'])
def toggle_ai_validation():
    """🆕 AI Validation 일괄 ON/OFF"""
    global SYMBOL_CONFIG
    try:
        data = request.get_json()
        if not data or 'enabled' not in data:
            return jsonify({'error': 'Missing "enabled" field (true/false)'}), 400
        
        enabled = bool(data['enabled'])
        updated_count = 0
        
        for symbol in SYMBOL_CONFIG:
            SYMBOL_CONFIG[symbol]['ai_validation'] = enabled
            updated_count += 1
        
        status_text = "활성화" if enabled else "비활성화"
        logger.info(f"🤖 AI Validation 일괄 {status_text}: {updated_count}개 심볼")
        
        if ENABLE_TELEGRAM:
            emoji = "✅" if enabled else "⛔"
            send_telegram_notification(
                f"{emoji} <b>AI Validation 일괄 {status_text}</b>\n\n"
                f"<b>적용 심볼:</b> {updated_count}개\n"
                f"<b>상태:</b> {'ON' if enabled else 'OFF'}\n\n"
                f"{'⚠️ AI 검증 없이 웹훅 신호가 직접 실행됩니다!' if not enabled else '🤖 모든 신호가 AI 검증을 거칩니다.'}\n\n"
                f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                'success' if enabled else 'warning'
            )
        
        return jsonify({
            'status': 'success',
            'ai_validation_enabled': enabled,
            'updated_symbols': updated_count
        }), 200
        
    except Exception as e:
        logger.error(f"AI Validation 토글 오류: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/ai-validation/status', methods=['GET'])
def ai_validation_status():
    """🆕 AI Validation 상태 조회"""
    try:
        enabled_count = sum(1 for c in SYMBOL_CONFIG.values() if c.get('ai_validation', True))
        disabled_count = sum(1 for c in SYMBOL_CONFIG.values() if not c.get('ai_validation', True))
        total = len(SYMBOL_CONFIG)
        
        return jsonify({
            'total_symbols': total,
            'ai_validation_enabled': enabled_count,
            'ai_validation_disabled': disabled_count,
            'all_enabled': enabled_count == total,
            'all_disabled': disabled_count == total
        }), 200
        
    except Exception as e:
        logger.error(f"AI Validation 상태 조회 오류: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/auto-tp-sl/toggle', methods=['POST'])
def toggle_auto_tp_sl():
    """🆕 TP/SL 자동생성 ON/OFF"""
    global AUTO_TP_SL_GENERATION
    try:
        data = request.get_json()
        if not data or 'enabled' not in data:
            return jsonify({'error': 'Missing "enabled" field (true/false)'}), 400
        
        AUTO_TP_SL_GENERATION = bool(data['enabled'])
        status_text = "활성화" if AUTO_TP_SL_GENERATION else "비활성화"
        logger.info(f"🎯 TP/SL 자동생성 {status_text}")
        
        if ENABLE_TELEGRAM:
            emoji = "🎯" if AUTO_TP_SL_GENERATION else "📡"
            send_telegram_notification(
                f"{emoji} <b>TP/SL 자동생성 {status_text}</b>\n\n"
                f"<b>상태:</b> {'ON' if AUTO_TP_SL_GENERATION else 'OFF'}\n\n"
                f"{'🎯 웹훅 TP/SL이 null이면 봇이 자동 생성합니다.' if AUTO_TP_SL_GENERATION else '📡 웹훅 TP/SL이 null이면 TP/SL 없이 진입합니다. (TradingView close_position 신호에 의존)'}\n\n"
                f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                'success' if AUTO_TP_SL_GENERATION else 'warning'
            )
        
        return jsonify({
            'status': 'success',
            'auto_tp_sl_enabled': AUTO_TP_SL_GENERATION
        }), 200
        
    except Exception as e:
        logger.error(f"TP/SL 자동생성 토글 오류: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/auto-tp-sl/status', methods=['GET'])
def auto_tp_sl_status():
    """🆕 TP/SL 자동생성 상태 조회"""
    return jsonify({
        'auto_tp_sl_enabled': AUTO_TP_SL_GENERATION
    }), 200


# ============ 🆕 v7.8: Emergency Drawdown Protection API ============
@app.route('/emergency-drawdown/toggle', methods=['POST'])
def toggle_emergency_drawdown():
    """EDP ON/OFF 토글"""
    global EMERGENCY_DRAWDOWN_ENABLED
    try:
        data = request.get_json()
        if not data or 'enabled' not in data:
            return jsonify({'error': 'Missing "enabled" field'}), 400
        
        EMERGENCY_DRAWDOWN_ENABLED = bool(data['enabled'])
        status_text = "활성화" if EMERGENCY_DRAWDOWN_ENABLED else "비활성화"
        logger.info(f"🛡️ EDP {status_text}")
        
        if EMERGENCY_DRAWDOWN_ENABLED and not emergency_drawdown_running:
            start_emergency_drawdown_protection()
        elif not EMERGENCY_DRAWDOWN_ENABLED and emergency_drawdown_running:
            stop_emergency_drawdown_protection()
        
        if ENABLE_TELEGRAM:
            emoji = "🛡️" if EMERGENCY_DRAWDOWN_ENABLED else "⛔"
            send_telegram_notification(
                f"{emoji} <b>긴급 낙폭 보호 {status_text}</b>\n\n"
                f"경고: {EMERGENCY_DRAWDOWN_WARNING}% | 강제청산: {EMERGENCY_DRAWDOWN_FORCE_EXIT}%\n"
                f"간격: {EMERGENCY_DRAWDOWN_MONITOR_INTERVAL}분\n\n"
                f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                'success' if EMERGENCY_DRAWDOWN_ENABLED else 'warning'
            )
        
        return jsonify({'status': 'success', 'enabled': EMERGENCY_DRAWDOWN_ENABLED}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/emergency-drawdown/config', methods=['POST'])
def config_emergency_drawdown():
    """EDP 파라미터 변경"""
    global EMERGENCY_DRAWDOWN_WARNING, EMERGENCY_DRAWDOWN_FORCE_EXIT, EMERGENCY_DRAWDOWN_MONITOR_INTERVAL
    try:
        data = request.get_json()
        changed = []
        
        if 'warning_threshold' in data:
            EMERGENCY_DRAWDOWN_WARNING = float(data['warning_threshold'])
            changed.append(f"경고={EMERGENCY_DRAWDOWN_WARNING}%")
        if 'force_exit_threshold' in data:
            EMERGENCY_DRAWDOWN_FORCE_EXIT = float(data['force_exit_threshold'])
            changed.append(f"강제청산={EMERGENCY_DRAWDOWN_FORCE_EXIT}%")
        if 'monitor_interval' in data:
            EMERGENCY_DRAWDOWN_MONITOR_INTERVAL = int(data['monitor_interval'])
            changed.append(f"간격={EMERGENCY_DRAWDOWN_MONITOR_INTERVAL}분")
        
        logger.info(f"🛡️ EDP 설정 변경: {', '.join(changed)}")
        
        return jsonify({
            'status': 'success',
            'warning_threshold': EMERGENCY_DRAWDOWN_WARNING,
            'force_exit_threshold': EMERGENCY_DRAWDOWN_FORCE_EXIT,
            'monitor_interval': EMERGENCY_DRAWDOWN_MONITOR_INTERVAL
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/emergency-drawdown/status', methods=['GET'])
def emergency_drawdown_status():
    """EDP 상태 조회"""
    return jsonify({
        'enabled': EMERGENCY_DRAWDOWN_ENABLED,
        'running': emergency_drawdown_running,
        'warning_threshold': EMERGENCY_DRAWDOWN_WARNING,
        'force_exit_threshold': EMERGENCY_DRAWDOWN_FORCE_EXIT,
        'monitor_interval': EMERGENCY_DRAWDOWN_MONITOR_INTERVAL,
        'warned_symbols': list(emergency_drawdown_warned)
    }), 200

@app.route('/ai-performance', methods=['GET'])
def ai_performance():
    """AI 거래 성과 조회"""
    try:
        conn = get_db_connection()
        c = conn.cursor()
        
        # 전체 AI 거래 통계
        c.execute("""
            SELECT 
                COUNT(*) as total_trades,
                SUM(CASE WHEN ai_decision = 'approve' THEN 1 ELSE 0 END) as approved,
                SUM(CASE WHEN ai_decision = 'reject' THEN 1 ELSE 0 END) as rejected,
                SUM(CASE WHEN ai_decision = 'modify' THEN 1 ELSE 0 END) as modified,
                AVG(confidence) as avg_confidence
            FROM trades
            WHERE trade_type = 'AI_VALIDATION'
        """)
        
        stats = c.fetchone()
        
        # 심볼별 통계
        c.execute("""
            SELECT 
                symbol,
                COUNT(*) as trades,
                AVG(confidence) as avg_confidence,
                SUM(CASE WHEN ai_decision = 'approve' THEN 1 ELSE 0 END) as approved
            FROM trades
            WHERE trade_type = 'AI_VALIDATION'
            GROUP BY symbol
        """)
        
        symbol_stats = c.fetchall()
        
        conn.close()
        
        return jsonify({
            'total_statistics': {
                'total_trades': stats[0] or 0,
                'approved': stats[1] or 0,
                'rejected': stats[2] or 0,
                'modified': stats[3] or 0,
                'average_confidence': f"{(stats[4] or 0) * 100:.1f}%"
            },
            'symbol_statistics': [
                {
                    'symbol': row[0],
                    'trades': row[1],
                    'avg_confidence': f"{row[2] * 100:.1f}%",
                    'approved': row[3]
                } for row in symbol_stats
            ]
        }), 200
        
    except Exception as e:
        logger.error(f"AI 성과 조회 오류: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/test-telegram', methods=['POST'])
def test_telegram_endpoint():
    """텔레그램 테스트 메시지 전송 엔드포인트"""
    try:
        success, result = test_telegram()
        
        if success:
            return jsonify(result), 200
        else:
            return jsonify({'error': result}), 400
            
    except Exception as e:
        logger.error(f"텔레그램 테스트 오류: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/telegram/verify', methods=['GET'])
def verify_telegram_endpoint():
    """텔레그램 봇 연결 확인 엔드포인트"""
    try:
        result = verify_telegram_bot()
        
        if result['success']:
            return jsonify(result), 200
        else:
            return jsonify(result), 400
            
    except Exception as e:
        logger.error(f"텔레그램 봇 확인 오류: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/telegram/send', methods=['POST'])
def send_telegram_endpoint():
    """커스텀 텔레그램 메시지 전송 엔드포인트"""
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        message = data.get('message', '')
        parse_mode = data.get('parse_mode', 'HTML')
        importance = data.get('importance', 'normal')
        
        if not message:
            return jsonify({'error': 'Message is required'}), 400
        
        result = send_custom_telegram_message(message, parse_mode, importance)
        
        if result['success']:
            return jsonify(result), 200
        else:
            return jsonify(result), 400
            
    except Exception as e:
        logger.error(f"텔레그램 메시지 전송 오류: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/trades/completed', methods=['GET'])
def get_completed_trades():
    """완료된 거래 조회 (대시보드용)"""
    try:
        conn = get_db_connection()
        c = conn.cursor()
        
        limit = request.args.get('limit', 100, type=int)
        symbol = request.args.get('symbol', None)
        
        query = "SELECT * FROM completed_trades WHERE 1=1"
        params = []
        
        if symbol:
            query += " AND symbol = ?"
            params.append(symbol)
            
        query += " ORDER BY close_timestamp DESC LIMIT ?"
        params.append(limit)
        
        c.execute(query, params)
        
        columns = [desc[0] for desc in c.description]
        trades = [dict(zip(columns, row)) for row in c.fetchall()]
        
        conn.close()
        
        return jsonify({
            'success': True,
            'count': len(trades),
            'trades': trades
        }), 200
        
    except Exception as e:
        logger.error(f"완료된 거래 조회 오류: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/balance/history', methods=['GET'])
def get_balance_history():
    """잔고 히스토리 조회 (대시보드용)"""
    try:
        conn = get_db_connection()
        c = conn.cursor()
        
        days = request.args.get('days', 30, type=int)
        cutoff_date = (datetime.now() - timedelta(days=days)).isoformat()
        
        c.execute("""SELECT * FROM balance_history 
                    WHERE timestamp >= ? 
                    ORDER BY timestamp DESC""", (cutoff_date,))
        
        columns = [desc[0] for desc in c.description]
        history = [dict(zip(columns, row)) for row in c.fetchall()]
        
        conn.close()
        
        return jsonify({
            'success': True,
            'count': len(history),
            'history': history
        }), 200
        
    except Exception as e:
        logger.error(f"잔고 히스토리 조회 오류: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/positions/history', methods=['GET'])
def get_position_history():
    """포지션 히스토리 조회"""
    try:
        conn = get_db_connection()
        c = conn.cursor()
        
        hours = request.args.get('hours', 24, type=int)
        cutoff_date = (datetime.now() - timedelta(hours=hours)).isoformat()
        
        c.execute("""SELECT * FROM position_history 
                    WHERE timestamp >= ? 
                    ORDER BY timestamp DESC""", (cutoff_date,))
        
        columns = [desc[0] for desc in c.description]
        history = [dict(zip(columns, row)) for row in c.fetchall()]
        
        conn.close()
        
        return jsonify({
            'success': True,
            'count': len(history),
            'history': history
        }), 200
        
    except Exception as e:
        logger.error(f"포지션 히스토리 조회 오류: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/stats/overview', methods=['GET'])
def get_stats_overview():
    """통계 개요 조회 (대시보드용)"""
    try:
        conn = get_db_connection()
        c = conn.cursor()
        
        # 전체 통계
        c.execute("""SELECT 
                        COUNT(*) as total_trades,
                        SUM(CASE WHEN is_win = 1 THEN 1 ELSE 0 END) as winning_trades,
                        SUM(CASE WHEN is_win = 0 THEN 1 ELSE 0 END) as losing_trades,
                        AVG(pnl_percent) as avg_pnl_percent,
                        SUM(pnl_usdt) as total_pnl,
                        MAX(pnl_usdt) as best_trade,
                        MIN(pnl_usdt) as worst_trade,
                        AVG(holding_time_minutes) as avg_holding_time
                    FROM completed_trades""")
        
        stats = c.fetchone()
        
        # 최근 잔고
        c.execute("""SELECT * FROM balance_history 
                    ORDER BY timestamp DESC LIMIT 1""")
        latest_balance = c.fetchone()
        
        conn.close()
        
        # 승률 계산
        total_trades = stats[0] or 0
        winning_trades = stats[1] or 0
        win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
        
        return jsonify({
            'success': True,
            'stats': {
                'total_trades': total_trades,
                'winning_trades': winning_trades,
                'losing_trades': stats[2] or 0,
                'win_rate': win_rate,
                'avg_pnl_percent': stats[3] or 0,
                'total_pnl': stats[4] or 0,
                'best_trade': stats[5] or 0,
                'worst_trade': stats[6] or 0,
                'avg_holding_time': stats[7] or 0
            },
            'balance': {
                'total': latest_balance[2] if latest_balance else 0,
                'free': latest_balance[3] if latest_balance else 0,
                'used': latest_balance[4] if latest_balance else 0
            }
        }), 200
        
    except Exception as e:
        logger.error(f"통계 개요 조회 오류: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/trades', methods=['GET'])
def get_trades():
    """거래 히스토리 조회 엔드포인트"""
    try:
        limit = request.args.get('limit', 100, type=int)
        symbol = request.args.get('symbol', None)
        trade_type = request.args.get('trade_type', None)
        
        conn = get_db_connection()
        c = conn.cursor()
        
        query = "SELECT * FROM trades WHERE 1=1"
        params = []
        
        if symbol:
            query += " AND symbol = ?"
            params.append(symbol)
        
        if trade_type:
            query += " AND trade_type = ?"
            params.append(trade_type)
        
        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)
        
        c.execute(query, params)
        
        columns = [desc[0] for desc in c.description]
        trades = [dict(zip(columns, row)) for row in c.fetchall()]
        
        conn.close()
        
        return jsonify({
            'success': True,
            'count': len(trades),
            'trades': trades
        }), 200
        
    except Exception as e:
        logger.error(f"거래 조회 오류: {str(e)}")
        return jsonify({'error': str(e)}), 500

def initialize_bot():
    """봇 초기화"""
    logger.info(f"봇 초기화 중... (포트: {SERVER_PORT})")
    
    # 데이터베이스 초기화 (프로그램 시작 시 1회)
    init_db_once()
    
    # 거래소 연결 테스트
    try:
        balance = exchange.fetch_balance()
        usdt_balance = balance['USDT']['free']
        logger.info(f"거래소 연결 성공. USDT 잔고: ${usdt_balance:,.2f}")
    except Exception as e:
        logger.error(f"거래소 연결 실패: {str(e)}")
    
    # 🔄 실제 포지션 동기화 (서버 재시작 시 복구)
    try:
        position_count = sync_positions_from_exchange()
        if position_count > 0:
            logger.info(f"✅ {position_count}개의 기존 포지션 복구 완료")
            position_summary = get_position_summary()
            logger.info(f"복구된 포지션:\n{position_summary}")
        else:
            logger.info("복구할 포지션 없음 (새로 시작)")
    except Exception as e:
        logger.error(f"포지션 동기화 실패: {str(e)}")
    
    # AI 모니터링 자동 시작
    start_ai_monitoring()
    
    # 🆕 v7.8: Emergency Drawdown Protection 자동 시작
    if EMERGENCY_DRAWDOWN_ENABLED:
        start_emergency_drawdown_protection()
    
    # OpenAI API 테스트
    try:
        client = OpenAI(api_key=os.getenv("DEEPSEEK_API_KEY"), base_url="https://api.deepseek.com")
        if client.api_key:
            logger.info("OpenAI API 연결 성공")
        else:
            logger.warning("OpenAI API 키가 설정되지 않았습니다. AI 기능이 제한됩니다.")
    except Exception as e:
        logger.error(f"OpenAI API 연결 실패: {str(e)}")
    
    # 활성화된 심볼 출력
    enabled_symbols = [s for s, c in SYMBOL_CONFIG.items() if c.get('enabled', True)]
    ai_symbols = [s for s, c in SYMBOL_CONFIG.items() if c.get('ai_validation', True)]
    ai_monitor_symbols = [s for s, c in SYMBOL_CONFIG.items() if c.get('ai_monitoring', True)]
    
    logger.info(f"활성화된 심볼: {len(enabled_symbols)}개")
    logger.info(f"AI 검증 활성 심볼: {len(ai_symbols)}개")
    logger.info(f"AI 모니터링 활성 심볼: {len(ai_monitor_symbols)}개")
    
    # 주기적 데이터 기록 스레드 시작
    def periodic_data_recording():
        """주기적으로 잔고와 포지션 데이터를 기록"""
        cleanup_counter = 0  # 🆕 v7.8: 고아 주문 정리 주기 카운터
        
        while True:
            try:
                # 잔고 스냅샷 (5분마다)
                record_balance_snapshot(exchange)
                
                # 포지션이 있을 때만 히스토리 기록
                if len(current_positions) > 0:
                    record_position_history(exchange)
                
                # 🆕 v7.8: 고아 주문 정리 (15분마다 = 5분 * 3)
                cleanup_counter += 1
                if cleanup_counter >= 3:
                    cleanup_counter = 0
                    logger.info("🧹 주기적 고아 주문 정리 실행...")
                    cleanup_orphan_orders()
                
                # 5분 대기
                time.sleep(300)
                
            except Exception as e:
                logger.error(f"주기적 데이터 기록 오류: {str(e)}")
                time.sleep(60)  # 오류 시 1분 후 재시도
    
    # 백그라운드 스레드로 실행
    recording_thread = threading.Thread(target=periodic_data_recording, daemon=True)
    recording_thread.start()
    logger.info("📊 주기적 데이터 기록 스레드 시작 (5분 간격)")
    
    if ENABLE_TELEGRAM:
        # 🆕 포지션 타입별 카운트
        auto_count = sum(1 for pos in current_positions.values() if pos.get('position_type', 'auto') == 'auto')
        manual_count = sum(1 for pos in current_positions.values() if pos.get('position_type', 'auto') == 'manual')
        
        position_info = ""
        if len(current_positions) > 0:
            position_info = f"\n\n<b>복구된 포지션:</b>\n{get_position_summary()}"
        
        startup_message = f"""
🚀 <b>통합 트레이딩 시스템 v7.5 고승률</b>

<b>🆕 v7.5 핵심 개선:</b>
💰 <b>고승률 수익 보호</b>
  → 수익 5%+ 적극 청산 권장
  → 수익 3%+ (30분+) 청산 허용
  → 작은 수익도 확실히 챙기기!

📊 <b>타이트한 TP/SL (15분봉 ATR 기반)</b>
  → SL: 0.8x ATR (기존 2.0x)
  → TP: 1.2x ATR (기존 3.5x)
  → 현실적인 목표, 높은 도달률

🔄 <b>양방향 포지션 관리</b>
  → 롱/숏 동시 보유 감지
  → 수익 포지션 자동 청산
  → 양쪽 손실 방지

⏰ <b>단축된 보호 기간</b>
  → 20분: 엄격 보호 (수익 5%+ 제외)
  → 40분: 수익 3%+ 허용
  → 60분: 정상 모니터링

<b>📊 기존 기능 (모두 유지):</b>
👥 다중 유저 동시 거래 (최대 3명)
🗑️ TP/SL 자동 삭제
🔄 동기화된 거래 실행
🎯 멀티 타임프레임 필터링
🚨 추세 역전 조기 신호 감지

<b>⚙️ 서버 정보:</b>
<b>서버 포트:</b> {SERVER_PORT} (Multi-User)
<b>활성 유저:</b> {len(exchanges)}명
<b>활성 심볼:</b> {len(enabled_symbols)}개
<b>AI 검증:</b> {len(ai_symbols)}개 심볼
<b>AI 모니터링:</b> {len(ai_monitor_symbols)}개 심볼
<b>모니터링 주기:</b> {AI_MONITOR_INTERVAL}분
<b>현재 포지션:</b> {len(current_positions)}개
  - 🤖 자동: {auto_count}개
  - 🔧 수동: {manual_count}개{position_info}

✅ v7.5 고승률 시스템 정상 시작!
💰 수익 보호 최우선 모드 활성화
📊 타이트한 TP/SL 적용
🔄 양방향 포지션 관리 활성화
🤖 AI 포지션 모니터링 활성화
📈 목표: 승률 60%+ 달성!

⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
        """.strip()
        send_telegram_notification(startup_message, 'success')

if __name__ == '__main__':
    initialize_bot()
    app.run(host='0.0.0.0', port=SERVER_PORT, debug=False, threaded=True)  # 명시적 멀티스레드 설정