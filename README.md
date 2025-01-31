
# 🤖 AI 기반 암호화폐 자동매매 봇

[![Python](https://img.shields.io/badge/Python-3.8%2B-blue)](https://www.python.org/)
[![OpenAI](https://img.shields.io/badge/OpenAI-GPT--4-brightgreen)](https://openai.com/)
[![Binance](https://img.shields.io/badge/Binance-Futures-yellow)](https://www.binance.com/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](https://opensource.org/licenses/MIT)

OpenAI의 GPT-4를 활용하여 Binance Futures에서 시장 분석과 자동 거래를 수행하는 고급 암호화폐 거래 봇입니다. 이 봇은 전통적인 기술적 분석과 인공지능을 결합하여 거래 결정을 내리며, 자체 성찰과 지속적인 개선 메커니즘을 포함하고 있습니다.

## 시스템 아키텍처
![시스템 아키텍처 다이어그램](https://github.com/user-attachments/assets/84f6f0cd-584e-48fd-85c1-2f04c61c4c8e)

## 🌟 주요 기능

### 🧠 지능형 거래 시스템
* **AI 기반 분석**: GPT-4를 활용하여 다양한 데이터 소스를 분석하고 거래 결정
* **자가 학습**: 지속적인 전략 개선을 위한 성찰 모델 구현
* **기술적 분석**: 다중 기술 지표와 차트 패턴 인식 통합
* **감성 분석**: 뉴스, 시장 심리, 공포&탐욕 지수 처리

### 📊 고급 리스크 관리
* 포지션 크기 최적화
* 자동 손절(Stop-loss)과 이익실현(Take-profit) 관리
* 트레일링 스탑로스 구현
* 레버리지 관리 (최대 20배)
* 계좌 잔액 보호 (최대 65% 노출)

### 🔄 실시간 처리
* 실시간 시장 데이터 모니터링
* 자동 거래 실행
* 수동 거래 추적
* 종합적인 로깅 시스템

### 📈 데이터 소스 통합
* Binance Futures API
* TradingView 차트
* 시장 뉴스 피드
* 공포&탐욕 지수
* 호가창 데이터
* 다중 시간프레임 분석 (5분, 1시간)

## 🛠️ 시스템 아키텍처

본 시스템은 다음과 같은 주요 구성 요소로 이루어져 있습니다:

### 주요 모듈
1. **INPUT**: 외부 데이터 수집
   * Binance API 데이터
   * 뉴스 API
   * TradingView 차트
   * Fear & Greed 지수

2. **AI BRAIN**: 핵심 분석 엔진
   * GPT-4 분석
   * 리스크 관리
   * 포지션 사이징
   * 기술적/감성 분석

3. **TRADING**: 거래 실행
   * 주문 관리
   * 포지션 추적
   * 손절/이익실현 관리

4. **IMPROVEMENT**: 자가 개선
   * 성과 분석
   * 전략 리플렉션
   * 지속적 개선

5. **STORAGE**: 데이터 저장소
   * SQLite 데이터베이스
   * 거래 이력
   * 성과 데이터

## 📋 필수 요구사항

```plaintext
- Python 3.8 이상
- Binance Futures 계정
- OpenAI API 키
- TradingView 계정 (차트 분석용)
```

## 🔧 설치 방법

1. 저장소 복제
   ```bash
   git clone https://github.com/yourusername/ai-crypto-trader.git
   cd ai-crypto-trader
   ```

2. 필요 패키지 설치
   ```bash
   pip install -r requirements.txt
   ```

3. 환경 변수 설정
   ```bash
   cp .env.example .env
   # .env 파일에 API 키와 설정을 입력하세요
   ```

## 💫 상세 기능

### 거래 전략
* 다중 시간프레임 분석 (5분, 1시간)
* BlackFlag FTS, UT Bot Alerts, Volume Oscillator 통합
* 동적 손익비율 조정 (1.3-2.0)
* 계좌 잔액 기반 자동 포지션 사이징

### 리스크 관리
* 지능형 손절가 설정
* 동적 이익실현 레벨
* 트레일링 스탑로스 구현
* 최대 포지션 크기 제한
* 레버리지 최적화

### 성과 분석
* 거래 이력 추적
* 성과 지표 계산
* 전략 효과성 평가
* 자체 성찰 및 개선

## 📊 거래 스케줄

봇은 최적의 거래 시간대에 운영됩니다:
* 21:00-02:00 (주 거래 세션)
* 04:00-07:00 (아시아 세션)
* 15:00-18:00 (유럽 세션)

각 세션에서 15분 간격으로 시장을 분석하고 거래를 실행합니다.

## ⚠️ 리스크 경고

```plaintext
암호화폐 선물 거래에는 상당한 위험이 따릅니다:
- 레버리지로 인한 큰 손실 가능성
- 높은 시장 변동성
- 청산 위험
이 봇은 교육 및 실험 목적으로 제작되었습니다.
본인의 책임 하에 거래하시기 바랍니다.
```

## 🤝 기여하기

기여는 언제나 환영합니다! Pull Request를 자유롭게 제출해 주세요.

## 📝 라이선스

이 프로젝트는 MIT 라이선스를 따릅니다 - 자세한 내용은 [LICENSE.md](LICENSE.md) 파일을 참조하세요.

## 📫 연락처

문의사항과 피드백:
* 이 저장소에 이슈를 생성해 주세요
* 이메일: mingu4u@naver.com

---
**참고**: 이 봇은 실험적인 프로젝트입니다. 항상 소액으로 시작하고 큰 자본을 투입하기 전에 철저히 테스트하시기 바랍니다.
