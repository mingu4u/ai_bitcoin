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
import cv2
import numpy as np
import pytesseract
import re
import gc
import psutil

# WebDriver 관리자 클래스 개선 (재시작 기능 추가)
class WebDriverManager:
    _instance = None
    _last_created = None
    _max_lifetime = 900  # 15분 (초 단위) - 드라이버 최대 수명
    
    @classmethod
    def get_driver(cls, force_new=False):
        """
        WebDriver 인스턴스 가져오기 - 필요시 새로 생성
        
        Args:
            force_new (bool): 강제로 새 드라이버 생성 여부
            
        Returns:
            WebDriver: 생성된 WebDriver 인스턴스
        """
        current_time = time.time()
        
        # 1. 강제 재생성 또는 인스턴스가 없는 경우
        if force_new or cls._instance is None:
            if cls._instance:
                cls.quit()  # 기존 드라이버 정리
            cls._instance = safe_create_driver()
            cls._last_created = current_time
            return cls._instance
            
        # 2. 드라이버 수명 초과 확인
        if cls._last_created and (current_time - cls._last_created) > cls._max_lifetime:
            logger.info(f"드라이버 최대 수명({cls._max_lifetime}초) 초과, 재생성")
            cls.quit()  # 기존 드라이버 정리
            cls._instance = safe_create_driver()
            cls._last_created = current_time
            return cls._instance
            
        # 3. 드라이버 건강상태 확인
        if not cls._is_alive(cls._instance):
            logger.warning("드라이버가 응답하지 않음, 재생성")
            cls.quit()  # 기존 드라이버 정리
            cls._instance = safe_create_driver()
            cls._last_created = current_time
        
        return cls._instance
    
    @classmethod
    def _is_alive(cls, driver):
        """
        드라이버 건강상태 확인
        
        Args:
            driver: WebDriver 인스턴스
            
        Returns:
            bool: 드라이버 정상 여부
        """
        try:
            # 간단한 JavaScript 실행으로 드라이버 상태 확인
            driver.execute_script("return 1")
            # 현재 URL 확인 (추가 검증)
            _ = driver.current_url
            return True
        except Exception as e:
            logger.warning(f"드라이버 상태 확인 실패: {str(e)}")
            return False
    
    @classmethod
    def quit(cls):
        """드라이버 안전하게 종료 - 완전히 개선된 버전"""
        if cls._instance:
            session_id = None
            driver_url = None
            
            try:
                # 세션 ID와 URL 저장 (디버깅 및 로깅용)
                try:
                    session_id = cls._instance.session_id
                    driver_url = cls._instance.command_executor._url
                    logger.debug(f"종료할 드라이버 세션: {session_id} @ {driver_url}")
                except:
                    pass
                    
                # 모든 진행 중인 스크립트 실행 중지 시도
                try:
                    cls._instance.execute_script("window.stop();")
                except:
                    pass
                    
                # 모든 요청 취소 및 핸들러 제거
                try:
                    cls._instance.execute_script("""
                        // 모든 진행 중인 Ajax 요청 중단
                        if (window.jQuery) {
                            jQuery.ajax({global: false});
                            jQuery(document).unbind('ajaxSend ajaxComplete ajaxError');
                        }
                        // 모든 이벤트 리스너 제거
                        window.onbeforeunload = null;
                        window.onunload = null;
                    """)
                except:
                    pass
                    
                # 현재 페이지 네비게이션 중단
                try:
                    cls._instance.execute_script("window.stop();")
                except:
                    pass
                
                # 드라이버 종료 전 타임아웃 설정 축소
                try:
                    cls._instance.set_page_load_timeout(2)  # 2초로 축소
                    cls._instance.set_script_timeout(2)
                except:
                    pass
                
                # 드라이버 종료 - 먼저 참조 저장
                temp_instance = cls._instance
                
                # 참조 즉시 해제하여 다른 코드가 재사용하지 못하도록 함
                cls._instance = None
                cls._last_created = None
                
                # 이제 저장된 임시 참조로 종료 시도
                try:
                    temp_instance.quit()
                    logger.info("드라이버 정상 종료됨")
                except Exception as e:
                    logger.warning(f"드라이버 종료 중 오류 (무시됨): {str(e)}")
                
                # 참조 명시적 해제
                del temp_instance
                
            except Exception as e:
                logger.warning(f"드라이버 종료 프로세스 중 오류: {str(e)}")
            finally:
                # 세션 ID를 포함하여 크롬 프로세스 정리
                if session_id:
                    cleanup_chrome_processes(session_id)
                else:
                    cleanup_chrome_processes()
                
                # 네트워크 핸들러 수동 정리 (소켓 누수 방지)
                clear_network_handlers()
                
                # 메모리 정리
                gc.collect()

def force_quit_webdriver(driver):
    """WebDriver 강제 종료 및 모든 리소스 해제"""
    try:
        # 페이지 로드 중지
        try:
            driver.execute_script("window.stop();")
        except:
            pass
            
        # 모든 자원 해제
        try:
            driver.execute_script("""
                window.onbeforeunload = null;
                window.onunload = null;
                if (window.jQuery) {
                    jQuery(document).unbind('ajaxSend ajaxComplete ajaxError');
                }
            """)
        except:
            pass
            
        # 명시적 종료
        driver.quit()
    except:
        pass
    finally:
        # 세션 참조 정리
        clear_webdriver_session_refs(driver)
        # 크롬 프로세스 강제 종료
        cleanup_chrome_processes()

def clear_network_handlers():
    """네트워크 및 소켓 관련 리소스 정리"""
    try:
        # 파이썬 내장 모듈 정리
        import urllib3
        try:
            # urllib3 커넥션 풀 비우기
            urllib3.disable_warnings()
            manager = urllib3.PoolManager()
            manager.clear()
            
            # 연결 풀에서 나오는 경고 메시지 수집 및 폐기
            import warnings
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                
            logger.debug("urllib3 연결 풀 정리 완료")
        except:
            pass
            
        # 소켓 관련 리소스 정리
        import socket
        socket.setdefaulttimeout(1)  # 짧은 타임아웃 설정
        
        # 가비지 컬렉션 수행
        gc.collect()
        
    except Exception as e:
        logger.error(f"네트워크 핸들러 정리 중 오류: {e}")

# 시스템 리소스 모니터링 및 자가 복구 함수
def check_resource_usage():
    """시스템 리소스 모니터링 및 자동 정리 - 개선된 버전"""
    # 메모리 사용량 모니터링 (더 낮은 임계값)
    memory_percent = psutil.virtual_memory().percent
    if memory_percent > 70:  # 70%로 낮춤
        logger.warning(f"높은 메모리 사용량 감지: {memory_percent}%")
        # 강화된 정리 작업 수행
        WebDriverManager.quit()
        cleanup_chrome_processes()
        
        # 가비지 컬렉션 여러 번 실행
        for _ in range(3):
            gc.collect()
        
        # 메모리 사용량 로깅
        process = psutil.Process(os.getpid())
        memory_info = process.memory_info()
        logger.info(f"정리 후 메모리 사용량: {memory_info.rss / 1024 / 1024:.2f} MB")
    
    # CPU 사용량 모니터링
    cpu_percent = psutil.cpu_percent(interval=1)
    if cpu_percent > 80:  # 80%로 낮춤
        logger.warning(f"높은 CPU 사용량 감지: {cpu_percent}%")
        # CPU 사용량 줄이기 위한 조치
        time.sleep(5)  # 잠시 대기
        
    # 디스크 사용량 모니터링
    disk_usage = psutil.disk_usage('/')
    if disk_usage.percent > 75:  # 디스크 정리 시작 임계값
        logger.warning(f"높은 디스크 사용량 감지: {disk_usage.percent}%")
        # 디스크 정리 함수 호출
        simple_disk_cleanup(logger)

# 크롬 프로세스 정리 함수 개선
def cleanup_chrome_processes(session_id=None):
    """
    크롬 및 크롬드라이버 프로세스 강제 종료
    
    Args:
        session_id (str, optional): 종료할 특정 WebDriver 세션 ID
    """
    try:
        if os.getenv("ENVIRONMENT") == "ec2":
            # 모든 프로세스 목록 가져오기
            processes = os.popen('ps aux | grep -E "chrome|chromedriver"').read()
            logger.debug(f"현재 실행 중인 크롬 관련 프로세스: {processes}")
            
            # 추가: session_id가 있으면 해당 프로세스만 찾아서 종료
            if session_id:
                os.system(f'sudo pkill -9 -f "{session_id}"')
                
            # 강제 종료 옵션과 함께 모든 크롬/크롬드라이버 프로세스 종료
            os.system('sudo pkill -9 -f "chrome|chromium|chromedriver"')
            
            # 확실한 정리를 위한 추가 명령
            os.system('sudo killall -9 chrome chromium-browser chromedriver 2>/dev/null || true')
            
            # 프로세스가 완전히 종료될 때까지 충분히 대기
            time.sleep(3)
            
            # 프로세스가 확실히 종료되었는지 확인
            chrome_processes = os.popen('ps aux | grep -E "chrome|chromedriver" | grep -v grep').read()
            if chrome_processes.strip():
                logger.warning(f"일부 크롬 프로세스가 아직 실행 중: {chrome_processes}")
                # 다시 시도 (특정 PID 찾아서 직접 종료)
                pid_pattern = r'\S+\s+(\d+)'
                pids = re.findall(pid_pattern, chrome_processes)
                for pid in pids:
                    os.system(f'sudo kill -9 {pid}')
        elif os.getenv("ENVIRONMENT") == "local":
            # Windows 환경에서는 taskkill 사용
            os.system('taskkill /f /im chrome.exe 2>nul')
            os.system('taskkill /f /im chromedriver.exe 2>nul')
        else:
            # 기본 환경 (Linux)
            os.system('pkill -9 -f "chrome|chromium|chromedriver" 2>/dev/null || true')
            
        # 소켓 파일 및 임시 파일 정리 (필요 시)
        tmp_dirs = ['/tmp', '/var/tmp']
        for tmp_dir in tmp_dirs:
            if os.path.exists(tmp_dir):
                for f in os.listdir(tmp_dir):
                    if ('chrome' in f.lower() or 'selenium' in f.lower()) and not os.path.isdir(os.path.join(tmp_dir, f)):
                        try:
                            os.remove(os.path.join(tmp_dir, f))
                        except:
                            pass
    except Exception as e:
        logger.error(f"크롬 프로세스 정리 실패: {e}")

class SignalTracker:
    def __init__(self, cache_file="trading_signals_cache.json"):
        """
        트레이딩 신호를 추적하고 저장하는 클래스
        
        Args:
            cache_file (str): 신호 캐시를 저장할 파일 경로
        """
        self.cache_file = cache_file
        self.signals = {
            "BlackFlag": {
                "signal": None,
                "candles_ago": None,
                "timestamp": None,
                "stop_loss_price": None
            },
            "UTBot": {
                "signal": None,
                "candles_ago": None,
                "timestamp": None
            },
            "VolumeOsc": {
                "values": [None] * 10,  # 최근 10개 캔들의 값을 저장
                "timestamps": [None] * 10
            }
        }
        
        # 캐시 파일이 존재하면 로드
        self.load_cache()
    
    def load_cache(self):
        """캐시 파일에서 신호 데이터 로드"""
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, 'r') as f:
                    cached_data = json.load(f)
                    self.signals = cached_data
                print(f"캐시 파일 '{self.cache_file}'에서 신호 데이터를 로드했습니다.")
            except Exception as e:
                print(f"캐시 파일 로드 중 오류 발생: {e}")
    
    def save_cache(self):
        """현재 신호 데이터를 캐시 파일에 저장"""
        try:
            with open(self.cache_file, 'w') as f:
                json.dump(self.signals, f, indent=4)
            print(f"신호 데이터를 캐시 파일 '{self.cache_file}'에 저장했습니다.")
        except Exception as e:
            print(f"캐시 파일 저장 중 오류 발생: {e}")
    
    def update_from_image_analysis(self, analysis_result, current_time=None):
        """
        이미지 분석 결과를 바탕으로 신호 정보 업데이트
        
        Args:
            analysis_result (dict): analyze_chart_signals 함수의 반환 결과
            current_time (datetime, optional): 현재 시간. 기본값은 현재 시간.
        """
        if current_time is None:
            current_time = datetime.now()
        
        # UTBot Alerts 업데이트 - 중요한 변경: 신호가 None인 경우에도 항상 업데이트
        utbot = analysis_result.get("UTBot", {})
        utbot_signal = utbot.get("alert_signal", "None")
        
        # 새로운 신호 여부와 관계없이 항상 최신 분석 결과로 업데이트
        if utbot_signal == "None":
            # 신호가 없는 경우, 현재 데이터를 None으로 설정
            self.signals["UTBot"] = {
                "signal": None,
                "candles_ago": None,
                "timestamp": None
            }
            print(f"UTBot 신호 업데이트: None (차트에서 신호 사라짐)")
        elif utbot.get("alert_time"):  # 유효한 신호가 있는 경우만 시간 처리
            try:
                # alert_time이 HH:MM 형식이라고 가정
                signal_time_str = utbot.get("alert_time", "").strip()
                if signal_time_str:
                    # 시간 파싱
                    hour, minute = map(int, signal_time_str.split(':'))
                    
                    # 현재 날짜에 시간 적용
                    signal_time = current_time.replace(hour=hour, minute=minute)
                    
                    # 만약 계산된 시간이 현재 시간보다 미래라면 어제 날짜로 조정
                    if signal_time > current_time:
                        signal_time = signal_time - timedelta(days=1)
                    
                    # 기존 로직과 동일하게 처리
                    self.signals["UTBot"] = {
                        "signal": utbot_signal,
                        "candles_ago": self._calculate_candles_ago(signal_time, current_time),
                        "timestamp": signal_time.isoformat()
                    }
                    print(f"UTBot 신호 업데이트: {utbot_signal}, {signal_time_str}")
            except Exception as e:
                print(f"UTBot 시간 파싱 오류: {e}, 원본 시간: {utbot.get('alert_time')}")
        
        # BlackFlag 업데이트도 동일한 방식으로 수정
        blackflag = analysis_result.get("BlackFlag", {})
        blackflag_flip = blackflag.get("flip_detected", "none")
        
        if blackflag_flip == "none":
            # 신호가 없는 경우, 현재 데이터를 None으로 설정
            self.signals["BlackFlag"] = {
                "signal": None,
                "candles_ago": None,
                "timestamp": None,
                "stop_loss_price": None
            }
            print(f"BlackFlag 신호 업데이트: None (차트에서 신호 사라짐)")
        elif blackflag.get("flip_time"):  # 유효한 신호가 있는 경우만 시간 처리
            try:
                # flip_time이 HH:MM 형식이라고 가정
                signal_time_str = blackflag.get("flip_time", "").strip()
                if signal_time_str:
                    # 시간 파싱
                    hour, minute = map(int, signal_time_str.split(':'))
                    
                    # 현재 날짜에 시간 적용
                    signal_time = current_time.replace(hour=hour, minute=minute)
                    
                    # 만약 계산된 시간이 현재 시간보다 미래라면 어제 날짜로 조정
                    if signal_time > current_time:
                        signal_time = signal_time - timedelta(days=1)
                    
                    # BlackFlag 신호 방향 매핑
                    signal_direction = "Buy" if blackflag_flip == "long" else "Sell"
                    
                    self.signals["BlackFlag"] = {
                        "signal": signal_direction,
                        "candles_ago": self._calculate_candles_ago(signal_time, current_time),
                        "timestamp": signal_time.isoformat(),
                        "stop_loss_price": blackflag.get("stop_loss_price")
                    }
                    print(f"BlackFlag 신호 업데이트: {signal_direction}, {signal_time_str}, SL: {blackflag.get('stop_loss_price')}")
            except Exception as e:
                print(f"BlackFlag 시간 파싱 오류: {e}, 원본 시간: {blackflag.get('flip_time')}")
        
        # Volume Oscillator 업데이트 (기존 로직과 동일)
        vol_osc_value = analysis_result.get("VolumeOsc")
        if vol_osc_value is not None:
            # 값을 왼쪽으로 시프트하고 새 값을 추가
            self.signals["VolumeOsc"]["values"].pop(0)
            self.signals["VolumeOsc"]["values"].append(vol_osc_value)
            
            # 타임스탬프도 같이 업데이트
            self.signals["VolumeOsc"]["timestamps"].pop(0)
            self.signals["VolumeOsc"]["timestamps"].append(current_time.isoformat())
            
            print(f"Volume Oscillator 업데이트: {vol_osc_value}")
        
        # 신호 캔들 수 업데이트
        self.update_candles_ago(current_time)
        
        # 캐시 저장
        self.save_cache() 
    
    def update_candles_ago(self, current_time=None):
        """현재 시간 기준으로 신호 발생 후 경과한 캔들 수 업데이트"""
        if current_time is None:
            current_time = datetime.now()
        
        # BlackFlag 캔들 수 업데이트
        if self.signals["BlackFlag"]["timestamp"]:
            signal_time = datetime.fromisoformat(self.signals["BlackFlag"]["timestamp"])
            self.signals["BlackFlag"]["candles_ago"] = self._calculate_candles_ago(signal_time, current_time)
            
            # 20캔들 이상 지난 신호는 None 처리 (15->20 변경)
            if self.signals["BlackFlag"]["candles_ago"] > 20:
                self.signals["BlackFlag"] = {
                    "signal": None,
                    "candles_ago": None,
                    "timestamp": None,
                    "stop_loss_price": None
                }
        
        # UTBot 캔들 수 업데이트
        if self.signals["UTBot"]["timestamp"]:
            signal_time = datetime.fromisoformat(self.signals["UTBot"]["timestamp"])
            self.signals["UTBot"]["candles_ago"] = self._calculate_candles_ago(signal_time, current_time)
            
            # 20캔들 이상 지난 신호는 None 처리 (15->20 변경)
            if self.signals["UTBot"]["candles_ago"] > 20:
                self.signals["UTBot"] = {
                    "signal": None,
                    "candles_ago": None,
                    "timestamp": None
                } 
    
    def _calculate_candles_ago(self, signal_time, current_time):
        """
        신호 발생 시간과 현재 시간 사이의 캔들 수 계산 (5분 캔들 기준)
        
        Args:
            signal_time (datetime): 신호 발생 시간
            current_time (datetime): 현재 시간
            
        Returns:
            int: 경과된 캔들 수
        """
        # 두 시간 사이의 차이를 분 단위로 계산
        time_diff = (current_time - signal_time).total_seconds() / 60
        
        # 5분 캔들 기준으로 몇 개의 캔들이 지났는지 계산
        candles_ago = int(time_diff // 5)
        
        return candles_ago
    
    def generate_prompt_data(self):
        """
        AI 프롬프트에 전달할 신호 데이터 생성
        
        Returns:
            dict: AI 프롬프트에 사용될 신호 데이터
        """
        return {
            "BlackFlag": {
                "signal": self.signals["BlackFlag"]["signal"],
                "candles_ago": self.signals["BlackFlag"]["candles_ago"],
                "stop_loss_price": self.signals["BlackFlag"]["stop_loss_price"]
            },
            "UTBot": {
                "signal": self.signals["UTBot"]["signal"],
                "candles_ago": self.signals["UTBot"]["candles_ago"]
            },
            "VolumeOsc": {
                "values": self.signals["VolumeOsc"]["values"],
                "current": self.signals["VolumeOsc"]["values"][-1]
            }
        }

def analyze_chart_signals(image_path,
                         # BlackFlag FTS parameters (normalized coordinates)
                         blackflag_cloud_roi=(0.0, 0.05, 0.92, 0.68),
                         blackflag_xaxis_yrange=(0.87, 0.91),
                         blackflag_chunk_size=10,
                         blackflag_needed_red_chunks=2,
                         blackflag_needed_green_chunks=2,
                         # UT Bot parameters
                         utbot_xaxis_yrange=(0.87, 0.91),
                         # Volume Oscillator parameters (normalized ROI)
                         volume_roi=(0.93, 0.68, 0.97, 0.88),
                         # Debug flag and prefix
                         debug=False,
                         debug_prefix="debug_"):
    """
    하나의 이미지에서 아래 3개 신호/값을 감지하여 반환합니다.

      1) BlackFlag FTS 신호 – Flip 신호, flip time, stop_loss_price를
         long, short 두 방향 모두 검출한 후, 프레임에서 오른쪽(큰 flip_x) 신호만 결과로 출력.
         (결과 예: {"flip_detected": "long", "flip_x": 123, "flip_time": "18:25", "stop_loss_price": 95295.4})
      2) UT Bot Alerts 신호 – Buy(하늘색) 또는 Sell(주황색) 박스 중 오른쪽(최신) 박스를 선택하고,
         그 박스 중심 아래 x축 영역 OCR로 신호 시간(alert_time)을 판독.
      3) Volume Oscillator 값 – volume_roi 영역 내 파란색 박스를 찾아 그 내부 숫자(예:-11.51%)를 OCR해
         '%'제거 후 float형으로 반환.
    
    모든 좌표는 정규화(0~1) 값이며, debug=True이면 debug_prefix를 이용해 debug 이미지(세 지표가 모두 표시된 한 개 이미지)를 저장합니다.
    반환 예시:
      {
        "BlackFlag": { "flip_detected": "long" or "short" or "none", "flip_x": ..., "flip_time": ..., "stop_loss_price": ... },
        "UTBot": { "alert_signal": "Buy"/"Sell"/"None", "alert_time": "hh:mm" },
        "VolumeOsc": -11.51
      }
    """

    # 이미지 로드
    img = cv2.imread(image_path)
    if img is None:
        print("이미지를 로드할 수 없습니다:", image_path)
        return None
    
    h, w = img.shape[:2]
    if h <= 0 or w <= 0:
        print(f"이미지 크기가 유효하지 않습니다: {w}x{h}")
        return None
        
    # 전역 debug 이미지: 원본 이미지의 복사본에 각 검출 결과를 덧그림
    debug_img = img.copy()
    
    # 디버그 이미지 저장 도우미 – 최종에 한 번만 저장
    def save_debug_final(image, suffix):
        if debug:
            path = f"{debug_prefix}{suffix}.png"
            cv2.imwrite(path, image)
            print("[Debug] Saved:", path)

    # 정규화 좌표 → 픽셀 좌표 변환 함수
    def to_px(norm_roi):
        x1n, y1n, x2n, y2n = norm_roi
        return (int(x1n * w), int(y1n * h), int(x2n * w), int(y2n * h))

    ############### BlackFlag FTS Detection ###############
    # run_blackflag_detection()는 주어진 방향("long" 또는 "short")에 대해 검출 결과를 반환함.
    # OCR 및 좌표 계산은 원본 이미지(img)를 사용하고, 결과 debug 오버레이는 debug_img에 그림.
    def run_blackflag_detection(direction):
        # OCR 계산용 복사본(원본 이미지 손상을 피하기 위해)
        img_bf = img.copy()
        cx1, cy1, cx2, cy2 = to_px(blackflag_cloud_roi)
        roi_cloud_bgr = img_bf[cy1:cy2, cx1:cx2]
        roi_cloud_hsv = cv2.cvtColor(roi_cloud_bgr, cv2.COLOR_BGR2HSV)
        roi_h, roi_w = roi_cloud_hsv.shape[:2]
        # 화면에 구름영역 박스 표시 (debug_img)
        cv2.rectangle(debug_img, (cx1, cy1), (cx2, cy2), (0,255,255), 2)

        # HSV 범위
        lower_red1 = np.array([0, 70, 70]);     upper_red1 = np.array([10, 255, 255])
        lower_red2 = np.array([170, 70, 70]);    upper_red2 = np.array([180, 255, 255])
        lower_green = np.array([35, 60, 70]);     upper_green = np.array([85, 255, 255])

        # Step B: chunk별 색상 판별
        chunk_colors = []
        n_chunks = roi_w // blackflag_chunk_size
        for i in range(n_chunks):
            x_start = i * blackflag_chunk_size
            x_end = x_start + blackflag_chunk_size
            col_slice = roi_cloud_hsv[:, x_start:x_end]
            mask_r1 = cv2.inRange(col_slice, lower_red1, upper_red1)
            mask_r2 = cv2.inRange(col_slice, lower_red2, upper_red2)
            mask_red = mask_r1 | mask_r2
            mask_green = cv2.inRange(col_slice, lower_green, upper_green)
            red_count = np.count_nonzero(mask_red)
            green_count = np.count_nonzero(mask_green)
            if direction == "long":
                chunk_colors.append("green" if green_count > red_count else "red")
            else:
                chunk_colors.append("red" if red_count > green_count else "green")
        # Step C: flip 신호 판별 (연속된 chunk 조건)
        if direction == "long":
            first_color = "red"
            second_color = "green"
            first_needed = blackflag_needed_red_chunks
            second_needed = blackflag_needed_green_chunks
        else:
            first_color = "green"
            second_color = "red"
            first_needed = blackflag_needed_green_chunks
            second_needed = blackflag_needed_red_chunks
        flip_x_local = None
        i_idx = 0
        while i_idx < n_chunks:
            valid_first = True
            for r in range(first_needed):
                if i_idx + r >= n_chunks or chunk_colors[i_idx + r] != first_color:
                    valid_first = False
                    break
            if not valid_first:
                i_idx += 1
                continue
            start_second_idx = i_idx + first_needed
            valid_second = True
            for g in range(second_needed):
                if start_second_idx + g >= n_chunks or chunk_colors[start_second_idx + g] != second_color:
                    valid_second = False
                    break
            if valid_second:
                flip_x_local = start_second_idx * blackflag_chunk_size
                break
            else:
                i_idx += 1

        if flip_x_local is None:
            return {"flip_detected": False, "flip_x": None, "flip_time": "", "stop_loss_price": None}

        # Step D: flip_x_global 및 flip time OCR
        flip_x_global = cx1 + flip_x_local
        cv2.line(debug_img, (flip_x_global, cy1), (flip_x_global, cy2), (0,255,255), 2)
        x_margin = 35
        x1px = max(0, flip_x_global - x_margin)
        x2px = min(w, flip_x_global + x_margin)
        y1p = int(blackflag_xaxis_yrange[0] * h)
        y2p = int(blackflag_xaxis_yrange[1] * h)
        roi_xaxis = img_bf[y1p:y2p, x1px:x2px]
        cv2.rectangle(debug_img, (x1px, y1p), (x2px, y2p), (255,0,255), 2)
        ocr_config = "--psm 7 --oem 3"
        time_text = pytesseract.image_to_string(roi_xaxis, config=ocr_config)
        time_label = time_text.strip().replace("\n","").replace(" ","")

        # Step E: stop_loss_price OCR
        if direction == "long":
            rgb_color = np.uint8([[[80,175,76]]])
            hsv_ref = cv2.cvtColor(rgb_color, cv2.COLOR_BGR2HSV)
            mask_candidate = cv2.inRange(roi_cloud_hsv, hsv_ref*0.9, hsv_ref*1.1)
        else:
            rgb_color = np.uint8([[[82,82,255]]])
            hsv_ref = cv2.cvtColor(rgb_color, cv2.COLOR_BGR2HSV)
            mask_candidate = cv2.inRange(roi_cloud_hsv, hsv_ref*0.9, hsv_ref*1.1)
        
        # 수정된 부분: 클라우드 영역 바운더리(상단/하단) 근처 후보만 고려
        candidate_center_y = None
        valid_candidates = []
        
        if flip_x_local < roi_w:
            right_side_mask = mask_candidate[:, flip_x_local:]
            points = cv2.findNonZero(right_side_mask)
            if points is not None:
                points[:,:,0] += flip_x_local
                max_x = np.max(points[:,:,0])
                candidate_points = points[points[:,:,0] == max_x]
                candidate_points = candidate_points.reshape(-1, 2)
                
                # 후보 포인트들을 y좌표 기준으로 정렬
                candidate_points = sorted(candidate_points, key=lambda p: p[1])
                
                # 여러 개의 후보점이 존재할 경우
                if len(candidate_points) > 0:
                    if direction == "long":
                        # long 방향(Green Cloud)인 경우 가장 아래쪽 점 사용 (Cloud의 경계) - 첫번째 점 무시
                        if len(candidate_points) > 1:
                            candidate_center_y = int(candidate_points[-1][1])
                        else:
                            candidate_center_y = int(candidate_points[0][1])
                    else:
                        # short 방향(Red Cloud)인 경우 가장 위쪽 점 사용 (Cloud의 경계) - 마지막 점 무시
                        if len(candidate_points) > 1:
                            candidate_center_y = int(candidate_points[0][1])
                        else:
                            candidate_center_y = int(candidate_points[0][1])
        
        stop_loss_price = None
        # 변수 초기화 위치 수정 - new_s_y1, new_s_y2 변수를 먼저 정의
        s_x1 = int(w * 0.92)
        s_x2 = int(w * 0.97)
        
        if candidate_center_y is not None:
            global_center_y = cy1 + candidate_center_y
            band_half = 20
            new_s_y1 = max(0, global_center_y - band_half)
            new_s_y2 = min(h, global_center_y + band_half)
            
            # 클라우드 영역 내부로 제한하는 추가 로직
            if direction == "long":
                # Long(Green Cloud)인 경우 하단 경계 근처로 제한
                new_s_y1 = max(new_s_y1, cy1)
                new_s_y2 = min(new_s_y2, cy2)
            else:
                # Short(Red Cloud)인 경우 상단 경계 근처로 제한
                new_s_y1 = max(new_s_y1, cy1)
                new_s_y2 = min(new_s_y2, cy2)
                
            roi_stoploss = img_bf[new_s_y1:new_s_y2, s_x1:s_x2]
            cv2.rectangle(debug_img, (s_x1, new_s_y1), (s_x2, new_s_y2), (0,255,0), 2)
        else:
            # 후보 포인트가 없는 경우 클라우드 영역으로 제한
            s_y1 = cy1
            s_y2 = cy2
            roi_stoploss = img_bf[s_y1:s_y2, s_x1:s_x2]
            cv2.rectangle(debug_img, (s_x1, s_y1), (s_x2, s_y2), (255,0,255), 2)
            # candidate_center_y가 None일 때의 new_s_y1, new_s_y2 설정
            new_s_y1 = s_y1
            new_s_y2 = s_y2
            
        roi_stoploss_hsv = cv2.cvtColor(roi_stoploss, cv2.COLOR_BGR2HSV)
        if direction == "long":
            mask_stoploss_sl = cv2.inRange(roi_stoploss_hsv, lower_green, upper_green)
        else:
            mask_stoploss_sl = cv2.inRange(roi_stoploss_hsv, lower_red1, upper_red1) | cv2.inRange(roi_stoploss_hsv, lower_red2, upper_red2)
        kernel = np.ones((3,3), np.uint8)
        mask_stoploss_sl = cv2.morphologyEx(mask_stoploss_sl, cv2.MORPH_OPEN, kernel)
        contours_sl, _ = cv2.findContours(mask_stoploss_sl, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if contours_sl:
            candidate_contours = [cnt for cnt in contours_sl if cv2.contourArea(cnt) > 500]
            if candidate_contours:
                candidate = max(candidate_contours, key=cv2.contourArea)
                x_box, y_box, w_box, h_box = cv2.boundingRect(candidate)
                cv2.rectangle(debug_img, (s_x1+x_box, new_s_y1+y_box), (s_x1+x_box+w_box, new_s_y1+y_box+h_box), (0,255,0), 2)
                candidate_roi = roi_stoploss[y_box:y_box+h_box, x_box:x_box+w_box]
                ocr_config_sl = "--psm 7 -c tessedit_char_whitelist=0123456789,."
                stop_loss_text = pytesseract.image_to_string(candidate_roi, config=ocr_config_sl)
                normalized_text = stop_loss_text.replace(',', '')
                normalized_text = normalized_text.strip().replace("\n","").replace(" ","")
                matches = re.findall(r"\d+\.\d+|\d+", normalized_text)
                if matches:
                    try:
                        stop_loss_price = float(matches[0])
                    except:
                        stop_loss_price = None
        if stop_loss_price is None:
            ocr_config_sl = "--psm 7 -c tessedit_char_whitelist=0123456789,."
            stop_loss_text = pytesseract.image_to_string(roi_stoploss, config=ocr_config_sl)
            normalized_text = stop_loss_text.replace(',', '')
            normalized_text = normalized_text.strip().replace("\n","").replace(" ","")
            matches = re.findall(r"\d+\.\d+|\d+", normalized_text)
            if matches:
                try:
                    stop_loss_price = float(matches[0])
                except:
                    stop_loss_price = None
        return {"flip_detected": True,
                "flip_x": flip_x_global,
                "flip_time": time_label,
                "stop_loss_price": stop_loss_price}  
        
    ############### UT Bot Alerts Detection ###############
    def detect_utbot():
            img_ut = img.copy()
            img_hsv = cv2.cvtColor(img_ut, cv2.COLOR_BGR2HSV)
            # HSV 범위: 하늘색 for Buy, 주황색 for Sell
            lower_cyan   = np.array([80, 100, 100])
            upper_cyan   = np.array([100, 255, 255])   # Buy
            lower_orange = np.array([10, 150, 100])
            upper_orange = np.array([25, 255, 255])    # Sell

            bounding_data = []
            # Buy 신호 탐색
            mask_buy = cv2.inRange(img_hsv, lower_cyan, upper_cyan)
            contours_buy, _ = cv2.findContours(mask_buy, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            for cnt in contours_buy:
                area = cv2.contourArea(cnt)
                if area < 750:
                    continue
                x, y, w_box, h_box = cv2.boundingRect(cnt)
                cx = x + w_box // 2
                bounding_data.append({
                    "signal": "Buy",
                    "cx": cx,
                    "box": (x, y, w_box, h_box)
                })
                cv2.rectangle(debug_img, (x,y), (x+w_box,y+h_box), (255,255,0), 2)
            # Sell 신호 탐색
            mask_sell = cv2.inRange(img_hsv, lower_orange, upper_orange)
            contours_sell, _ = cv2.findContours(mask_sell, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            for cnt in contours_sell:
                area = cv2.contourArea(cnt)
                if area < 750:
                    continue
                x, y, w_box, h_box = cv2.boundingRect(cnt)
                cx = x + w_box // 2
                bounding_data.append({
                    "signal": "Sell",
                    "cx": cx,
                    "box": (x, y, w_box, h_box)
                })
                cv2.rectangle(debug_img, (x,y), (x+w_box,y+h_box), (0,165,255), 2)
            alert_signal = "None"
            alert_time = ""
            center_x = None
            if len(bounding_data) > 0:
                best_box = max(bounding_data, key=lambda d: d["cx"])
                alert_signal = best_box["signal"]
                center_x = best_box["cx"]
                (bx, by, bw, bh) = best_box["box"]
                cv2.rectangle(debug_img, (bx,by), (bx+bw,by+bh), (0,255,255), 3)
            if alert_signal != "None" and center_x is not None:
                x_margin = 35
                x1px = max(0, center_x - x_margin)
                x2px = min(w, center_x + x_margin)
                y1p = int(utbot_xaxis_yrange[0] * h)
                y2p = int(utbot_xaxis_yrange[1] * h)
                roi_time = img_ut[y1p:y2p, x1px:x2px]
                cv2.rectangle(debug_img, (x1px,y1p), (x2px,y2p), (0,0,255), 2)
                ocr_config = "--psm 7 --oem 3"
                time_ocr_text = pytesseract.image_to_string(roi_time, config=ocr_config)
                alert_time = time_ocr_text.strip().replace("\n"," ").strip()
            return {"alert_signal": alert_signal, "alert_time": alert_time}
    ############ End UT Bot Detection ############
        
    ############## Volume Oscillator Detection ##############
    def read_volume_osc():
        img_vol = img.copy()
        x1 = int(volume_roi[0] * w)
        y1 = int(volume_roi[1] * h)
        x2 = int(volume_roi[2] * w)
        y2 = int(volume_roi[3] * h)
        cv2.rectangle(debug_img, (x1, y1), (x2, y2), (255,0,255), 2)
        roi_osc = img_vol[y1:y2, x1:x2]
        roi_hsv = cv2.cvtColor(roi_osc, cv2.COLOR_BGR2HSV)
        lower_blue = np.array([100, 100, 50])
        upper_blue = np.array([140, 255, 255])
        mask_blue = cv2.inRange(roi_hsv, lower_blue, upper_blue)
        kernel = np.ones((3,3), np.uint8)
        mask_blue = cv2.morphologyEx(mask_blue, cv2.MORPH_OPEN, kernel)
        contours, _ = cv2.findContours(mask_blue, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        sub_roi = roi_osc
        if contours:
            max_cnt = max(contours, key=cv2.contourArea)
            x_box, y_box, w_box, h_box = cv2.boundingRect(max_cnt)
            cv2.rectangle(debug_img, (x1+x_box, y1+y_box), (x1+x_box+w_box, y1+y_box+h_box), (255,255,0), 2)
            sub_roi = roi_osc[y_box:y_box+h_box, x_box:x_box+w_box]
        ocr_config = "--psm 7 --oem 3"
        ocr_text = pytesseract.image_to_string(sub_roi, config=ocr_config)
        ocr_text = ocr_text.strip().replace("\n", "").replace(" ", "")
        ocr_text = ocr_text.replace("%", "")
        matches = re.findall(r"[+-]?\d+\.\d+|[+-]?\d+", ocr_text)
        vol_value = None
        if matches:
            try:
                vol_value = float(matches[0])
            except ValueError:
                vol_value = None
        return vol_value
    ############ End Volume Oscillator Detection ############

    # 각 지표 검출 함수 호출
    result_long = run_blackflag_detection("long")
    result_short = run_blackflag_detection("short")
    
    # 통합된 BlackFlag 결과: 두 방향 모두 검출된 경우 오른쪽(최대 flip_x) 신호만 선택
    if result_long.get("flip_detected") and result_short.get("flip_detected"):
        if result_long["flip_x"] is not None and result_short["flip_x"] is not None:
            if result_long["flip_x"] >= result_short["flip_x"]:
                blackflag_final = {"flip_detected": "long",
                                "flip_x": result_long["flip_x"],
                                "flip_time": result_long["flip_time"],
                                "stop_loss_price": result_long["stop_loss_price"]}
            else:
                blackflag_final = {"flip_detected": "short",
                                "flip_x": result_short["flip_x"],
                                "flip_time": result_short["flip_time"],
                                "stop_loss_price": result_short["stop_loss_price"]}
        elif result_long["flip_x"] is not None:
            blackflag_final = {"flip_detected": "long",
                            "flip_x": result_long["flip_x"],
                            "flip_time": result_long["flip_time"],
                            "stop_loss_price": result_long["stop_loss_price"]}
        else:
            blackflag_final = {"flip_detected": "short",
                            "flip_x": result_short["flip_x"],
                            "flip_time": result_short["flip_time"],
                            "stop_loss_price": result_short["stop_loss_price"]}
    elif result_long.get("flip_detected"):
        blackflag_final = {"flip_detected": "long",
                        "flip_x": result_long["flip_x"],
                        "flip_time": result_long["flip_time"],
                        "stop_loss_price": result_long["stop_loss_price"]}
    elif result_short.get("flip_detected"):
        blackflag_final = {"flip_detected": "short",
                        "flip_x": result_short["flip_x"],
                        "flip_time": result_short["flip_time"],
                        "stop_loss_price": result_short["stop_loss_price"]}
    else:
        blackflag_final = {"flip_detected": "none", "flip_x": None, "flip_time": "", "stop_loss_price": None}

    # UT Bot 및 Volume Oscillator 검출 함수 호출
    utbot_result = detect_utbot()
    volume_result = read_volume_osc()

    # 최종 debug 이미지 저장(하나로 통합)
    save_debug_final(debug_img, "merged")

    # 큰 이미지 객체 명시적 해제
    del img
    del debug_img
    
    # GC 강제 수행
    gc.collect()

    return {"BlackFlag": blackflag_final,
            "UTBot": utbot_result,
            "VolumeOsc": volume_result}

class ChartSignalProcessor:
    """
    트레이딩 뷰 차트에서 신호를 처리하고 AI 프롬프트에 전달할 데이터를 생성하는 클래스
    """
    
    def __init__(self):
        """트레이딩 신호 트래커 초기화"""
        self.signal_tracker = SignalTracker()
    
    def process_chart_image(self, image_path, debug=False):
        """
        차트 이미지 처리 및 신호 업데이트
        
        Args:
            image_path (str): 처리할 이미지 파일 경로
            debug (bool): 디버그 이미지 저장 여부
            
        Returns:
            dict: 분석 결과 (성공 시) 또는 None (실패 시)
        """
        try:
            # 이미지 분석 수행
            analysis_result = analyze_chart_signals(
                image_path=image_path,
                debug=debug,
                debug_prefix=f"debug_{datetime.now().strftime('%Y%m%d_%H%M%S')}_"
            )
            
            if analysis_result:
                # 현재 시간으로 신호 트래커 업데이트
                current_time = datetime.now()
                self.signal_tracker.update_from_image_analysis(analysis_result, current_time)
                return analysis_result
            return None
        except Exception as e:
            print(f"차트 이미지 처리 중 오류 발생: {e}")
            return None
    
    def generate_ai_prompt_data(self):
        """
        AI 프롬프트에 전달할 데이터 생성
        
        Returns:
            dict: AI 프롬프트에 사용될 포맷팅된 신호 데이터
        """
        # 현재 시간 기준으로 캔들 경과 업데이트
        self.signal_tracker.update_candles_ago()
        
        # 프롬프트용 데이터 생성
        signal_data = self.signal_tracker.generate_prompt_data()
        
        # 프롬프트용 텍스트 포맷팅
        formatted_data = {
            "BlackFlag_Signal": signal_data["BlackFlag"]["signal"],
            "BlackFlag_CandlesAgo": signal_data["BlackFlag"]["candles_ago"],
            "UTBot_Signal": signal_data["UTBot"]["signal"],
            "UTBot_CandlesAgo": signal_data["UTBot"]["candles_ago"],
            "VolumeOsc_Current": signal_data["VolumeOsc"]["current"],
            "VolumeOsc_History": signal_data["VolumeOsc"]["values"],
            "StopLoss_Price": signal_data["BlackFlag"]["stop_loss_price"]
        }
        
        return formatted_data
    
    def create_prompt_text(self):
        """
        AI 프롬프트에 전달할 텍스트 생성
        
        Returns:
            str: AI 프롬프트에 사용될 포맷팅된 신호 텍스트
        """
        data = self.generate_ai_prompt_data()
        
        # BlackFlag 신호 정보
        blackflag_info = "None" if data["BlackFlag_Signal"] is None else \
                        f"{data['BlackFlag_Signal']} ({data['BlackFlag_CandlesAgo']} 캔들 전)"
        
        # UTBot 신호 정보
        utbot_info = "None" if data["UTBot_Signal"] is None else \
                    f"{data['UTBot_Signal']} ({data['UTBot_CandlesAgo']} 캔들 전)"
        
        # Volume Oscillator 정보
        vol_history = ", ".join([str(round(v, 2)) if v is not None else "None" 
                                for v in data["VolumeOsc_History"]])
        
        # Stop Loss 가격 정보
        sl_price = "None" if data["StopLoss_Price"] is None else str(data["StopLoss_Price"])
        
        # 프롬프트 텍스트 구성
        prompt_text = f"""
        ### Trading Signals Data

        **BlackFlag FTS Signal:** {blackflag_info}

        **UT Bot Alert:** {utbot_info}

        **Volume Oscillator:**
        - Current Value: {data["VolumeOsc_Current"]}
        - Last 10 candles: [{vol_history}] (oldest to newest)

        **Stop Loss Price:** {sl_price}
        """
        
        return prompt_text

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
        """현재 활성화된 AI 포지션 ID만 조회"""
        try:
            with sqlite3.connect('bitcoin_trades.db') as conn:
                c = conn.cursor()
                # 가장 최근의 진입 거래만 유효하게 고려하고, 이후 청산된 기록이 없는 것만 선택
                c.execute("""
                    WITH latest_entry AS (
                        SELECT order_id, decision, MAX(timestamp) as entry_time
                        FROM trades 
                        WHERE trade_type = 'AI' 
                        AND decision IN ('buy', 'sell')
                        GROUP BY decision
                    )
                    SELECT le.order_id, le.decision 
                    FROM latest_entry le
                    WHERE NOT EXISTS (
                        SELECT 1 FROM trades 
                        WHERE reason LIKE '%Close%' 
                        AND timestamp > le.entry_time
                    )
                    ORDER BY entry_time DESC
                    LIMIT 1
                """)
                return c.fetchall()
        except Exception as e:
            self.logger.error(f"Error fetching active AI positions: {e}")
            return []

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

            with sqlite3.connect('bitcoin_trades.db') as conn:
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
                                    btc_balance, usdt_balance, total_assets, btc_avg_buy_price, 
                                    btc_current_price, reflection, tp_order_id, sl_order_id,
                                    blackflag_signal, blackflag_candles_ago, utbot_signal, 
                                    utbot_candles_ago, volume_osc_current, stop_loss_price) 
                                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", 
                                (
                                order_timestamp, trade_type, order_id, decision,
                                int(trade_percentage), reason,
                                used_usdt, free_usdt, total_usdt,
                                btc_avg_buy_price, current_btc_price,
                                last_reflection,  # 기존 reflection을 유지
                                order_id if reason == 'AI TP Realized' else None,
                                order_id if reason == 'AI SL Realized' else None,
                                None,None,None,None,None,None
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
                            
                except Exception as e:
                    self.logger.error(f"Error processing orders: {e}")
                    
        except Exception as e:
            self.logger.error(f"Error monitoring trades: {e}")


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


    # market_order_with_tp_sl 함수 수정 - monitor_and_adjust_sl 함수에서 SL 업데이트 이슈 해결
    def market_order_with_tp_sl(self, side: str, buy_amount: float, pl_ratio: float, sl_price: float):
        """
        시장가 주문과 TP/SL 설정을 처리하는 함수 - 중복 SL 생성 버그 수정

        Args:
            side (str): 'buy' 또는 'sell'
            buy_amount (float): 주문 금액 (USDT)
            pl_ratio (float): 수익률 비율
            sl_price (float): 스탑로스 가격
        """
        # 상수 정의
        SAFETY_MARGIN = 0.002      # 안전 마진 (0.2%)
        TRAILING_THRESHOLD = 0.004 # 트레일링 시작 기준 수익률 (0.4%)
        TRAILING_STEP = 0.004      # 트레일링 스탑 업데이트 단계 (0.4%)
        TRAILING_BUFFER = 0.003    # 트레일링 버퍼 (0.3%)
        MINIMUM_ORDER_VALUE = 10   # 최소 주문 금액 (USDT)
        MIN_PRICE_DIFF = 0.001     # 최소 가격 차이 (0.1%)
        MAX_BALANCE_USE = 0.80     # 최대 사용 가능 잔고 비율 (80%)
        API_DELAY = 0.5            # API 호출 후 대기 시간

        def cancel_orders(orders_to_cancel):
            """TP/SL 주문 취소 헬퍼 함수"""
            for o in orders_to_cancel:
                try:
                    self.exchange.cancel_order(o['id'], self.symbol)
                    self.logger.info(f"Cancelled order: {o['id']} (ClientOrderId={o.get('clientOrderId','')}")
                except Exception as e:
                    self.logger.error(f"Error cancelling order {o['id']}: {e}")
                time.sleep(API_DELAY)

        # 1. 현재가 조회 및 TP/SL 가격 계산
        try:
            ticker = self.exchange.fetch_ticker(self.symbol)
            current_price = ticker['last']
            
            # TP/SL 가격 보정
            min_price_diff_val = current_price * MIN_PRICE_DIFF

            if side == 'buy':  # LONG 포지션
                # SL 가격 검증
                if sl_price >= current_price or (current_price - sl_price) < min_price_diff_val:
                    sl_price = current_price * (1 - SAFETY_MARGIN)
                    self.logger.warning(f"Invalid SL price for long position. Adjusted to {sl_price}")
                
                # 거리 계산 (현재가와 SL 사이의 거리)
                price_distance = current_price - sl_price
                
                # TP 가격 계산 (현재가에서 위쪽으로 [거리 × PL 비율]만큼 이동)
                tp_price = current_price + (price_distance * pl_ratio)
                
                self.logger.info(f"LONG position: Entry={current_price}, SL={sl_price}, TP={tp_price}, Distance={price_distance}, PL Ratio={pl_ratio}")
                
            else:  # side == 'sell' (SHORT 포지션)
                # SL 가격 검증
                if sl_price <= current_price or (sl_price - current_price) < min_price_diff_val:
                    sl_price = current_price * (1 + SAFETY_MARGIN)
                    self.logger.warning(f"Invalid SL price for short position. Adjusted to {sl_price}")
                
                # 거리 계산 (SL과 현재가 사이의 거리)
                price_distance = sl_price - current_price
                
                # TP 가격 계산 (현재가에서 아래쪽으로 [거리 × PL 비율]만큼 이동)
                tp_price = current_price - (price_distance * pl_ratio)
                
                self.logger.info(f"SHORT position: Entry={current_price}, SL={sl_price}, TP={tp_price}, Distance={price_distance}, PL Ratio={pl_ratio}")
        
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

        # 5. 트레일링 스탑로스 모니터링 함수 정의 - 개선된 버전 (수익률 조건 충족 시에만 SL 업데이트)
        def monitor_and_adjust_sl():
            """
            트레일링 스탑로스를 모니터링하고 필요시 업데이트하는 함수
            - 수정: 수익률이 TRAILING_THRESHOLD(0.4%) 이상일 때만 스탑로스 업데이트
            - 호출 즉시 SL 생성하지 않고 조건 충족 시에만 기존 SL 업데이트
            """
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

                # 최소 트레일링 단계 확인 (0.4%)
                if profit_percentage >= TRAILING_THRESHOLD:
                    # 이 함수에 상태를 저장하기 위한 비공개 속성이 없으므로 
                    # 현재 스탑로스 주문을 조회하여 마지막 업데이트 가격을 확인
                    try:
                        open_orders_ = self.exchange.fetch_open_orders(self.symbol)
                        existing_sl = [o for o in open_orders_ if o.get('clientOrderId','').startswith('sl_')]
                        
                        if not existing_sl:
                            self.logger.warning("No existing SL order found for trailing update")
                            return None
                            
                        # 기존 SL 가격 가져오기
                        current_sl_price = float(existing_sl[0]['info'].get('stopPrice', 0))
                        
                        # 새로운 SL 가격 계산
                        if pos_side == 'long':
                            # 진입가와 현재가의 차이에서 TRAILING_STEP(0.5%) 단위로 나누어 몇 번째 스텝인지 계산
                            step_count = int(profit_percentage / TRAILING_STEP)
                            # 새로운 SL은 진입가 + (스텝 수 - 1) * 스텝 크기 * 진입가
                            # 첫 번째 스텝(0.5%)에서는 SL을 진입가에 두고, 두 번째 스텝(1.0%)부터는 0.5% 간격으로 올림
                            min_sl_price = entry_price * (1 + (step_count - 1) * TRAILING_STEP) if step_count > 0 else entry_price
                            
                            # 현재 가격에서 버퍼만큼 내린 값
                            new_sl_price = current_market_price * (1 - TRAILING_BUFFER)
                            
                            # 기존 SL과 계산된 min_sl_price 중 높은 값만 사용 (SL은 항상 올리기만 함)
                            if min_sl_price <= current_sl_price:
                                # 이미 적절한 SL이 설정되어 있음
                                return None
                                
                        else:  # short position
                            # 진입가와 현재가의 차이에서 TRAILING_STEP(0.5%) 단위로 나누어 몇 번째 스텝인지 계산
                            step_count = int(profit_percentage / TRAILING_STEP)
                            # 새로운 SL은 진입가 - (스텝 수 - 1) * 스텝 크기 * 진입가
                            # 첫 번째 스텝(0.5%)에서는 SL을 진입가에 두고, 두 번째 스텝(1.0%)부터는 0.5% 간격으로 내림
                            max_sl_price = entry_price * (1 - (step_count - 1) * TRAILING_STEP) if step_count > 0 else entry_price
                            
                            # 현재 가격에서 버퍼만큼 올린 값
                            new_sl_price = current_market_price * (1 + TRAILING_BUFFER)
                            
                            # 기존 SL과 계산된 max_sl_price 중 낮은 값만 사용 (SL은 항상 내리기만 함)
                            if max_sl_price >= current_sl_price:
                                # 이미 적절한 SL이 설정되어 있음
                                return None
                        
                        # 현재 SL보다 유리한 가격으로 업데이트 가능한 경우만 실행
                        if (pos_side == 'long' and new_sl_price > current_sl_price) or \
                        (pos_side == 'short' and new_sl_price < current_sl_price):
                            
                            # 기존 SL 주문 취소
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
                            
                            # 로그 출력 - 현재 이익률과 업데이트된 SL 표시
                            self.logger.info(f"Trailing SL updated: Price={new_sl_price:.2f}, Current Profit={profit_percentage*100:.2f}%, Step={step_count}")
                            return new_sl_order

                    except Exception as e_:
                        self.logger.error(f"Error updating trailing SL: {e_}")
                        return None
                else:
                    # 수익률이 충분하지 않으면 SL 업데이트 하지 않음
                    self.logger.debug(f"Profit percentage ({profit_percentage*100:.2f}%) below threshold ({TRAILING_THRESHOLD*100}%) - no SL update")
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


# Selenium 관련 함수
def create_driver():
    env = os.getenv("ENVIRONMENT")
    logger.info("ChromeDriver 설정 중...")
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    
    # 성능 최적화 옵션 추가
    chrome_options.add_argument("--disable-extensions")
    chrome_options.add_argument("--disable-browser-side-navigation")
    chrome_options.add_argument("--disable-infobars")
    chrome_options.add_argument("--disable-browser-animations")
    chrome_options.add_argument("--js-flags=--expose-gc")
    chrome_options.add_argument("--disable-default-apps")
    chrome_options.add_argument("--disable-translate")
    chrome_options.add_argument("--disable-sync")
    chrome_options.add_argument("--disable-web-security")
    chrome_options.add_argument("--blink-settings=imagesEnabled=false")  # 이미지 로드 비활성화
    
    # 메모리 최적화 설정
    chrome_options.add_argument("--js-flags=--max-old-space-size=128")  # JS 힙 크기 제한
    chrome_options.add_argument("--memory-model=low")
    chrome_options.add_argument("--disable-site-isolation-trials")
    
    # WebGL 경고 메시지 제거를 위한 추가 옵션들
    chrome_options.add_argument("--enable-unsafe-webgl")
    chrome_options.add_argument("--enable-unsafe-swiftshader")
    chrome_options.add_argument('--disable-software-rasterizer')

    # 로깅 레벨 조정
    chrome_options.add_argument('--log-level=3')
    
    # 프록시 설정 제거 (잠재적 지연 요소)
    chrome_options.add_argument('--no-proxy-server')
    
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
        
        # 페이지 로드 전략 설정 (빠른 로드)
        driver.set_page_load_timeout(30)
        driver.set_script_timeout(30)
        
        driver.set_window_size(1920, 1028)
        
        return driver
    except Exception as e:
        logger.error(f"ChromeDriver 생성 중 오류 발생: {e}")
        raise
    
    
# 안전하게 WebDriver 생성 (싱글톤 패턴 활용)
def safe_create_driver():
    """안전하게 WebDriver 인스턴스 생성"""
    retries = 3
    for attempt in range(retries):
        try:
            driver = create_driver()
            return driver
        except WebDriverException as e:
            logger.error(f"WebDriver 생성 실패 (시도 {attempt + 1}/{retries}): {e}")
            time.sleep(2)  # 재시도 전 대기
    raise WebDriverException("WebDriver 생성 실패. 크롬 드라이버를 확인하세요.")

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
        driver = WebDriverManager.get_driver()
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
        # 드라이버 정리 - 메모리 누수 방지
        WebDriverManager.quit()
        return None

# 재시도 로직이 포함된 TradingView 차트 캡처 함수
def capture_tradingview_chart_with_retry(chart_processor=None, save_image=False, debug=False, 
                                        max_retries=3, page_load_timeout=30):
    """
    TradingView 차트를 캡처하고 분석하는 함수 (재시도 로직 포함)
    
    Args:
        chart_processor: 차트 신호 프로세서 인스턴스
        save_image: 이미지 저장 여부
        debug: 디버그 모드 활성화 여부
        max_retries: 최대 재시도 횟수
        page_load_timeout: 페이지 로드 타임아웃 (초)
        
    Returns:
        tuple: (차트 이미지 base64, 신호 분석 결과, 이미지 파일 경로 또는 None)
    """
    driver = None
    
    for attempt in range(max_retries):
        try:
            # 1. 드라이버 획득 (필요시 재생성)
            if attempt > 0:
                logger.info(f"차트 캡처 재시도 ({attempt+1}/{max_retries})")
                driver = WebDriverManager.get_driver(force_new=True)  # 강제 재생성
            else:
                driver = WebDriverManager.get_driver()
            
            if not driver:
                logger.error("유효한 WebDriver를 얻을 수 없음")
                time.sleep(2)
                continue
                
            # 2. 페이지 로드
            try:
                driver.set_page_load_timeout(page_load_timeout)
                # 첫 시도에만 페이지 로드, 재시도 시에는 새로고침
                if attempt == 0:
                    # 로그인 상태로 TradingView 차트 페이지 열기
                    driver.get("https://kr.tradingview.com/chart/zcDfxQQ8/?symbol=BINANCE%3ABTCUSDT.P")
                else:
                    driver.refresh()
                
                # 페이지 로드 대기
                WebDriverWait(driver, page_load_timeout).until(
                    EC.presence_of_element_located((By.XPATH, "/html/body/div[2]"))
                )
                logger.info("TradingView 페이지 로드 완료")
                # 차트 로딩을 위한 추가 대기
                time.sleep(3)
            except Exception as e:
                logger.error(f"페이지 로드 중 오류: {str(e)}")
                
                # 통신 에러 발생 시 즉시 세션 참조 정리
                clear_webdriver_session_refs(driver)
                
                time.sleep(2)
                continue
                
            # 3. 이미지 캡처 및 신호 분석
            result = capture_and_analyze_chart(driver, chart_processor, save_image, debug)
            
            # 결과가 유효하면 반환 전에 즉시 통신 종료
            if result[0]:  # base64 이미지가 있으면 성공
                # 세션 참조 정리
                clear_webdriver_session_refs(driver)
                
                # 성공적인 캡처 후 드라이버 즉시 종료
                try:
                    # 페이지 로드 및 자원 로드 중지
                    try:
                        driver.execute_script("window.stop();")
                    except:
                        pass
                    
                    # 실제 드라이버 종료 지연 (비동기적으로 처리)
                    def delayed_quit():
                        try:
                            if driver:
                                driver.quit()
                        except:
                            pass
                    
                    # 새 스레드에서 종료 실행 (현재 코드 블로킹 방지)
                    from threading import Thread
                    Thread(target=delayed_quit, daemon=True).start()
                    
                    logger.info("캡처 성공 후 WebDriver 종료 예약됨")
                except:
                    pass
                
                return result
            else:
                logger.warning(f"캡처 실패 또는 빈 응답 (시도 {attempt+1}/{max_retries})")
                
                # 통신 에러 발생 시 즉시 세션 참조 정리
                clear_webdriver_session_refs(driver)
                
                time.sleep(2)
        
        except Exception as e:
            logger.error(f"차트 캡처 중 오류 (시도 {attempt+1}/{max_retries}): {str(e)}")
            
            # 예외 발생 시 즉시 세션 참조 정리
            if driver:
                clear_webdriver_session_refs(driver)
                
            time.sleep(2)
        finally:
            # 무조건 드라이버 종료 시도 (성공 시에는 이미 지연 종료 예약됨)
            if driver:
                try:
                    # 종료 전 세션 참조 정리 한번 더
                    clear_webdriver_session_refs(driver)
                    
                    # 실제 종료
                    driver.quit()
                    logger.info("WebDriver 명시적으로 종료됨")
                except Exception as e:
                    logger.warning(f"WebDriver 종료 중 오류: {str(e)}")
                finally:
                    # 참조 명시적 삭제
                    driver = None
    
    logger.error(f"최대 재시도 횟수({max_retries}) 초과, 차트 캡처 실패")
    
    # 마지막 정리 작업
    WebDriverManager.quit()  # WebDriverManager에서 관리하는 드라이버 인스턴스 종료
    cleanup_chrome_processes()  # 크롬 프로세스 정리
    gc.collect()  # 가비지 컬렉션 명시적 호출
    
    return None, None, None

# 캡처 함수 타임아웃 및 에러 처리 개선
def capture_and_analyze_chart(driver, chart_processor=None, save_image=False, debug=False, timeout=60):
    """
    차트 이미지를 캡처하고 신호를 분석하는 함수 - 타임아웃 및 메모리 관리 개선
    
    Args:
        driver: Selenium 웹드라이버
        chart_processor: 차트 신호 프로세서 인스턴스
        save_image: 이미지 저장 여부 (기본값: False)
        debug: 디버그 모드 활성화 여부 (기본값: False)
        timeout: 캡처 타임아웃 (초) (기본값: 60)
        
    Returns:
        tuple: (차트 이미지 base64, 신호 분석 결과, 이미지 파일 경로 또는 None)
    """
    temp_path = None
    start_time = time.time()
    
    try:
        # 타임아웃 설정 개선
        try:
            driver.set_page_load_timeout(30)  # 30초 제한
            driver.set_script_timeout(30)     # 스크립트 실행 제한
        except:
            pass
        
        # 브라우저 창 크기 설정
        try:
            logger.info("브라우저 창 크기 설정 시작")
            driver.set_window_size(1920, 1028) # driver.set_window_size(1920, 1080)
            time.sleep(1)
        except Exception as e:
            logger.warning(f"브라우저 창 크기 설정 중 오류 (무시됨): {e}")
        
        # 스크린샷 캡처 시작
        logger.info("스크린샷 캡처 시작")
        capture_start = time.time()
        
        try:
            # 타임아웃 설정
            if time.time() - start_time > timeout:
                logger.error(f"캡처 타임아웃 초과: {timeout}초")
                force_quit_webdriver(driver)
                return None, None, None
                
            # 명시적인 명령 사용
            png = driver.get_screenshot_as_png()
            capture_time = time.time() - capture_start
            logger.info(f"전체 화면 스크린샷 캡처 완료 ({capture_time:.2f}초)")
            
            # 캡처 시간이 너무 길면 경고
            if capture_time > 10:
                logger.warning(f"스크린샷 캡처에 {capture_time:.2f}초 소요 - 성능 저하 가능성")
            
            # 이미지 캡처 후 스크립트 실행 중단
            try:
                driver.execute_script("window.stop();")
            except:
                pass
        except Exception as e:
            logger.error(f"스크린샷 캡처 실패: {e}")
            return None, None, None
        
        # PIL Image로 변환 - 명시적 메모리 관리
        img_buffer = io.BytesIO(png)
        img_pil = Image.open(img_buffer)
        img_pil.load()  # 이미지 데이터 즉시 로드
        
        # 원본 PNG 데이터 메모리 해제
        del png
        gc.collect()
        
        logger.info("PIL Image 변환 완료")
        
        # 이미지 크기 기록 
        original_width, original_height = img_pil.size
        logger.info(f"원본 캡처 이미지 크기: {original_width}x{original_height}")
        
        # 이미지 크기가 너무 작은 경우 유효하지 않음
        if original_width < 100 or original_height < 100:
            logger.error(f"이미지 크기가 너무 작음: {original_width}x{original_height}")
            # 명시적 메모리 해제
            img_pil.close()
            del img_pil
            img_buffer.close()
            del img_buffer
            gc.collect()
            return None, None, None
        
        # 파일 경로 설정
        current_time = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"chart_{current_time}.png"
        script_dir = os.path.dirname(os.path.abspath(__file__))
        file_path = os.path.join(script_dir, filename)
        
        # 저장 옵션이 활성화된 경우에만 파일로 저장
        if save_image:
            img_pil.save(file_path)
            logger.info(f"스크린샷 저장 완료: {file_path}")
        
        # Base64 인코딩 - 메모리 효율적 처리
        buffered = io.BytesIO()
        img_pil.save(buffered, format="PNG")
        base64_image = base64.b64encode(buffered.getvalue()).decode('utf-8')
        
        # 메모리 관리: buffered 객체 명시적 정리
        buffered.close()
        del buffered
        
        # 캡처 작업 완료 후 드라이버와의 통신 최소화
        try:
            # 페이지 로드 중지
            driver.execute_script("window.stop();")
            # 불필요한 자원 해제
            driver.execute_script("""
                // 메모리 누수 가능성 있는 자원 정리
                if (window.jQuery) { 
                    try { jQuery.clear && jQuery.clear(); } catch(e) {} 
                }
                // DOM에 연결된 이벤트 리스너 제거
                try {
                    var oldElem = document.documentElement.cloneNode(false);
                    document.replaceChild(oldElem, document.documentElement);
                } catch(e) {}
                // GC 힌트
                if (typeof CollectGarbage === 'function') CollectGarbage();
            """)
        except:
            pass
        
        # OpenCV 이미지로 변환 (중요: PIL 이미지 데이터 복사 후 변환)
        img_np = np.array(img_pil)
        
        # PIL 이미지 명시적 메모리 해제 (더 이상 필요 없음)
        img_pil.close()
        del img_pil
        img_buffer.close()
        del img_buffer
        gc.collect()
        
        img_cv = cv2.cvtColor(img_np, cv2.COLOR_RGB2BGR)
        logger.info("OpenCV 이미지 변환 완료")
        
        # 이미지가 유효한지 확인
        if img_cv is None or img_cv.size == 0:
            logger.error("OpenCV 이미지 변환 실패 또는 이미지가 비어 있습니다")
            del img_np
            gc.collect()
            return base64_image, None, file_path if save_image else None
        
        # 타임아웃 체크 (분석 시작 전)
        if time.time() - start_time > timeout * 0.8:  # 타임아웃의 80% 이상 소요됐으면 분석 건너뛰기
            logger.warning(f"이미지 처리에 너무 많은 시간 소요: {time.time() - start_time:.2f}초")
            return base64_image, None, file_path if save_image else None
        
        # 신호 분석 수행 (타임아웃 적용)
        signal_analysis = None
        if chart_processor is not None:
            # 임시 이미지 파일 생성
            temp_path = os.path.join(script_dir, f"temp_{current_time}.png")
            cv2.imwrite(temp_path, img_cv)
            
            try:
                # 시간 제한 설정 - 분석에 최대 30초만 허용
                analysis_start = time.time()
                logger.info(f"차트 신호 분석 시작 (debug={debug})")
                
                # 분석 시간 제한 구현
                MAX_ANALYSIS_TIME = 30  # 30초
                
                # 분석 실행
                signal_analysis = chart_processor.process_chart_image(
                    image_path=temp_path,
                    debug=debug
                )
                
                # 타임아웃 체크
                analysis_time = time.time() - analysis_start
                if analysis_time > MAX_ANALYSIS_TIME:
                    logger.warning(f"차트 신호 분석이 너무 오래 걸림: {analysis_time:.2f}초")
                
                if signal_analysis:
                    logger.info("차트 신호 분석 완료")
                    logger.info(f"신호 분석 결과: {signal_analysis}")
                else:
                    logger.warning("차트 신호 분석 결과 없음")
            except Exception as analysis_error:
                logger.error(f"신호 분석 중 오류: {analysis_error}")
                signal_analysis = None
            finally:
                # 임시 파일 삭제
                if temp_path and os.path.exists(temp_path) and not save_image:
                    try:
                        os.remove(temp_path)
                        logger.info(f"임시 파일 삭제: {temp_path}")
                    except Exception as del_error:
                        logger.warning(f"임시 파일 삭제 실패: {del_error}")
        
        # 메모리 정리
        del img_cv
        del img_np
        
        # 가비지 컬렉션 강제 수행
        gc.collect()
        
        # 세션 참조 정리
        clear_webdriver_session_refs(driver)
        
        # 타임아웃 체크 및 소요시간 로깅
        total_time = time.time() - start_time
        if total_time > timeout * 0.9:
            logger.warning(f"전체 처리 시간이 타임아웃에 근접: {total_time:.2f}초 / {timeout}초")
        else:
            logger.info(f"캡처 및 분석 완료 시간: {total_time:.2f}초")
            
        return base64_image, signal_analysis, file_path if save_image else None
        
    except Exception as e:
        logger.error(f"차트 캡처 및 분석 중 오류 발생: {e}", exc_info=True)
        
        # 임시 파일 정리
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except:
                pass
                
        # 강제 메모리 정리
        for var in ['img_cv', 'img_np', 'img_pil', 'png', 'buffered', 'img_buffer']:
            if var in locals() and locals()[var] is not None:
                try:
                    if var == 'img_pil' and locals()[var] is not None:
                        locals()[var].close()
                    del locals()[var]
                except:
                    pass
                
        gc.collect()
        gc.collect()  # 두 번 실행하여 순환 참조도 정리
        
        # 세션 참조 정리
        clear_webdriver_session_refs(driver)
        
        # 타임아웃 체크 후 드라이버 강제 종료
        if time.time() - start_time > timeout * 0.5:  # 절반 이상 소요됐으면 드라이버 재설정
            logger.warning("처리 시간 초과로 WebDriver 강제 종료")
            force_quit_webdriver(driver)
        
        return None, None, None

def clear_webdriver_session_refs(driver):
    """WebDriver 세션 관련 참조 정리"""
    try:
        # 연결 비활성화 시도
        try:
            if hasattr(driver, 'command_executor') and hasattr(driver.command_executor, '_conn'):
                driver.command_executor._conn = None
        except:
            pass
            
        # 세션 관련 속성 제거
        for attr in ['_unwrapped', '_url', '_conn', '_commands', 'session_id']:
            try:
                if hasattr(driver, attr):
                    setattr(driver, attr, None)
                    
                if hasattr(driver, 'command_executor') and hasattr(driver.command_executor, attr):
                    setattr(driver.command_executor, attr, None)
            except:
                pass
    except Exception as e:
        logger.debug(f"WebDriver 세션 참조 정리 중 오류: {e}")


def modify_orderbook(orderbook):
    """
    오더북 데이터의 타임스탬프를 KST로 변환
    
    Args:
        orderbook: 오더북 데이터
        
    Returns:
        dict: 수정된 오더북 데이터
    """
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


# 메인 코드의 리소스 모니터링 기능 강화
def check_resource_usage():
    """시스템 리소스 모니터링 및 자동 정리 - 개선된 버전"""
    # 메모리 사용량 모니터링 (더 낮은 임계값)
    memory_percent = psutil.virtual_memory().percent
    if memory_percent > 70:  # 70%로 낮춤
        logger.warning(f"높은 메모리 사용량 감지: {memory_percent}%")
        # 강화된 정리 작업 수행
        WebDriverManager.quit()
        cleanup_chrome_processes()
        
        # 파일 캐시 정리
        if os.getenv("ENVIRONMENT") == "ec2":
            try:
                os.system('sudo sh -c "sync; echo 3 > /proc/sys/vm/drop_caches"')
            except:
                pass
                
        # 가비지 컬렉션 여러 번 실행
        for _ in range(3):
            gc.collect()
        
        # 메모리 사용량 로깅
        process = psutil.Process(os.getpid())
        memory_info = process.memory_info()
        logger.info(f"정리 후 메모리 사용량: {memory_info.rss / 1024 / 1024:.2f} MB")
    
    # CPU 사용량 모니터링
    cpu_percent = psutil.cpu_percent(interval=1)
    if cpu_percent > 80:  # 80%로 낮춤
        logger.warning(f"높은 CPU 사용량 감지: {cpu_percent}%")
        # CPU 사용량 줄이기 위한 조치
        time.sleep(5)  # 잠시 대기
        
    # 디스크 사용량 모니터링
    disk_usage = psutil.disk_usage('/')
    if disk_usage.percent > 85:
        logger.warning(f"높은 디스크 사용량 감지: {disk_usage.percent}%")
        # 로그 및 임시 파일 정리
        cleanup_temp_files()
        
# 임시 파일 정리 함수 추가        
def cleanup_temp_files():
    """로그 및 임시 파일 정리"""
    try:
        # 임시 디렉토리 내 파일 정리
        temp_dirs = ['/tmp', os.path.join(os.getcwd(), 'temp')]
        for temp_dir in temp_dirs:
            if os.path.exists(temp_dir):
                for f in os.listdir(temp_dir):
                    if f.startswith(('temp_', 'chart_', 'debug_')) and f.endswith(('.png', '.jpg')):
                        file_path = os.path.join(temp_dir, f)
                        # 1일 이상 지난 파일만 삭제
                        if (time.time() - os.path.getctime(file_path)) > 86400:
                            try:
                                os.remove(file_path)
                                logger.debug(f"오래된 임시 파일 삭제: {file_path}")
                            except:
                                pass
        
        # 로그 파일 정리
        log_dir = "logs"
        if os.path.exists(log_dir):
            log_files = sorted([os.path.join(log_dir, f) for f in os.listdir(log_dir) if f.endswith('.log')])
            if len(log_files) > 10:  # 최근 10개만 보존
                for old_file in log_files[:-10]:
                    try:
                        os.remove(old_file)
                        logger.info(f"오래된 로그 파일 삭제: {old_file}")
                    except:
                        pass
    except Exception as e:
        logger.error(f"임시 파일 정리 중 오류: {e}")

# 로그 관리 설정 추가
def setup_logging():
    log_dir = "logs"
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
        
    # 로그 파일 이름에 날짜 포함
    log_file = os.path.join(log_dir, f"trading_bot_{datetime.now().strftime('%Y%m%d')}.log")
    
    # 로그 핸들러 설정
    file_handler = logging.FileHandler(log_file)
    console_handler = logging.StreamHandler()
    
    # 포맷터 설정
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)
    
    # 로거 설정
    logger = logging.getLogger()
    logger.handlers.clear()
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    logger.setLevel(logging.INFO)
    
    # 로그 로테이션 설정
    def cleanup_old_logs():
        # 30일 이상 된 로그 파일 삭제
        now = datetime.now()
        for f in os.listdir(log_dir):
            if f.startswith("trading_bot_") and f.endswith(".log"):
                file_path = os.path.join(log_dir, f)
                file_time = datetime.fromtimestamp(os.path.getctime(file_path))
                if (now - file_time).days > 30:
                    os.remove(file_path)
    
    # 매일 자정에 오래된 로그 정리
    schedule.every().day.at("00:00").do(cleanup_old_logs)
    
    return logger

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
    """데이터베이스 초기화 및 필요한 테이블 생성"""
    try:
        with sqlite3.connect('bitcoin_trades.db') as conn:
            c = conn.cursor()
            
            # 기존 테이블 구조 확인
            c.execute("PRAGMA table_info(trades)")
            columns = [column[1] for column in c.fetchall()]
            
            # 테이블이 존재하지 않으면 새로 생성
            if not columns:
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
                            sl_order_id TEXT,
                            blackflag_signal TEXT,
                            blackflag_candles_ago INTEGER,
                            utbot_signal TEXT,
                            utbot_candles_ago INTEGER,
                            volume_osc_current REAL,
                            stop_loss_price REAL)''')
            else:
                # 필요한 새 컬럼 추가
                new_columns = {
                    'blackflag_signal': 'TEXT',
                    'blackflag_candles_ago': 'INTEGER',
                    'utbot_signal': 'TEXT',
                    'utbot_candles_ago': 'INTEGER',
                    'volume_osc_current': 'REAL',
                    'stop_loss_price': 'REAL'
                }
                
                # 존재하지 않는 컬럼만 추가
                for col_name, col_type in new_columns.items():
                    if col_name not in columns:
                        c.execute(f"ALTER TABLE trades ADD COLUMN {col_name} {col_type}")
                        print(f"Added new column: {col_name}")
            
            conn.commit()
            return True
    except Exception as e:
        logger.error(f"데이터베이스 초기화 오류: {e}")
        return False

# 거래 기록 함수 수정 - 신호 데이터 포함
def log_trade(conn, trade_type, order_id, decision, percentage, reason, btc_balance, 
              usdt_balance, total_assets, btc_avg_buy_price, btc_current_price, 
              reflection='', tp_order_id=None, sl_order_id=None, signals_data=None):
    """
    거래 기록을 DB에 저장하는 함수
    
    Args:
        ... (기존 매개변수) ...
        signals_data (dict, optional): 트레이딩 신호 데이터. 기본값은 None.
    """
    try:
        with conn:  # context manager 사용하여 자동 커밋/롤백
            c = conn.cursor()
            timestamp = datetime.now().isoformat()
            
            # 신호 데이터가 있는 경우 이를 추출
            blackflag_signal = None
            blackflag_candles_ago = None
            utbot_signal = None
            utbot_candles_ago = None
            volume_osc_current = None
            stop_loss_price = None
            
            if signals_data:
                blackflag_signal = signals_data.get("BlackFlag_Signal")
                blackflag_candles_ago = signals_data.get("BlackFlag_CandlesAgo")
                utbot_signal = signals_data.get("UTBot_Signal")
                utbot_candles_ago = signals_data.get("UTBot_CandlesAgo")
                volume_osc_current = signals_data.get("VolumeOsc_Current")
                stop_loss_price = signals_data.get("StopLoss_Price")            
            
            c.execute("""INSERT INTO trades 
                        (timestamp, trade_type, order_id, decision, percentage, reason, 
                        btc_balance, usdt_balance, total_assets, btc_avg_buy_price, 
                        btc_current_price, reflection, tp_order_id, sl_order_id,
                        blackflag_signal, blackflag_candles_ago, utbot_signal, 
                        utbot_candles_ago, volume_osc_current, stop_loss_price) 
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (timestamp, trade_type, order_id, decision, percentage, reason, 
                    btc_balance, usdt_balance, total_assets, btc_avg_buy_price, 
                    btc_current_price, reflection, tp_order_id, sl_order_id,
                    blackflag_signal, blackflag_candles_ago, utbot_signal,
                    utbot_candles_ago, volume_osc_current, stop_loss_price))
            return True
    except Exception as e:
        logger.error(f"거래 기록 오류: {e}")
        return False
    

def get_recent_trades(conn, num_trades=20):
    """
    최근 n개의 거래 내역을 시간 역순으로 가져오는 함수
    
    Args:
        conn: SQLite 데이터베이스 연결 객체
        num_trades: 가져올 거래 내역의 수 (기본값: 20)
    
    Returns:
        DataFrame: 최근 거래 내역이 시간 역순으로 정렬된 데이터프레임
    """
    try:
        with conn:  # context manager 사용
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

def get_db_connection():
    """SQLite 데이터베이스 연결 객체 반환"""
    try:
        return sqlite3.connect('bitcoin_trades.db')
    except Exception as e:
        logger.error(f"데이터베이스 연결 오류: {e}")
        return None

def calculate_performance(trades_df):
    """최근 투자 기록을 기반으로 퍼포먼스 계산 (초기 잔고 대비 최종 잔고)"""
    if trades_df.empty or trades_df.iloc[-1]['usdt_balance'] == 0:
        return 0
    
    initial_balance = trades_df.iloc[-1]['usdt_balance'] + trades_df.iloc[-1]['btc_balance'] * trades_df.iloc[-1]['btc_current_price']
    final_balance = trades_df.iloc[0]['usdt_balance'] + trades_df.iloc[0]['btc_balance'] * trades_df.iloc[0]['btc_current_price']
    
    return (final_balance - initial_balance) / initial_balance * 100

def generate_reflection(trades_df, current_market_data):
    """
    AI 모델을 사용하여 최근 투자 기록과 시장 데이터를 기반으로 분석 및 반성을 생성하는 함수
    
    Args:
        trades_df: 최근 거래 내역 데이터프레임
        current_market_data: 현재 시장 데이터 (딕셔너리)
        
    Returns:
        str: 생성된 반성 텍스트
    """
    performance = calculate_performance(trades_df) # 투자 퍼포먼스 계산
    
    try:
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
    except Exception as e:
        logger.error(f"Error generating reflection: {e}")
        return None

def add_indicators(df):
    """
    데이터프레임에 보조 지표를 추가하는 함수
    
    Args:
        df: OHLCV 데이터가 포함된 데이터프레임
        
    Returns:
        DataFrame: 보조 지표가 추가된 데이터프레임
    """
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
    """
    UTC 시간을 한국 표준시(KST)로 변환
    
    Args:
        utc_date_str: UTC 시간 문자열
    
    Returns:
        str: KST 형식의 시간 문자열
    """
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
    """
    암호화폐 시장의 공포 탐욕 지수 조회
    
    Returns:
        dict: 공포 탐욕 지수 데이터
    """
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
    """
    비트코인 관련 뉴스 헤드라인 가져오기
    
    Returns:
        list: 뉴스 헤드라인 목록
    """
    serpapi_key = os.getenv("SERPAPI_API_KEY")
    if not serpapi_key:
        print("SERPAPI API key is missing.")
        return []  # 빈 목록 반환
        
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
    """
    YouTube 비디오의 자막 데이터 가져오기
    
    Args:
        video_id: YouTube 비디오 ID
        
    Returns:
        str: 결합된 자막 텍스트
    """
    try:
        transcript = YouTubeTranscriptApi.get_transcript(video_id, languages=['ko'])
        combined_text = ' '.join(entry['text'] for entry in transcript)
        return combined_text
    except Exception as e:
        logger.error(f"Error fetching YouTube transcript: {e}")
        return ""

# OpenAI를 이용한 TradingDecision 모델
class TradingDecision(BaseModel):
    decision: str
    percentage: int
    reason: str
    stop_loss_price: int
    pl_ratio: float

def assess_trend_strength(df_5min, df_hourly, current_price, df_4h=None):
    """
    비트코인의 특성에 맞게 개선된 트렌드 강도 평가 함수
    
    Args:
        df_5min: 5분 OHLCV 데이터프레임 (지표 포함)
        df_hourly: 1시간 OHLCV 데이터프레임 (지표 포함)
        current_price: 현재 BTC 가격
        df_4h: 4시간 OHLCV 데이터프레임 (지표 포함, 선택사항)
        
    Returns:
        dict: 롱/숏 트렌드 강도 평가 결과
    """
    # 최신 지표 값 가져오기
    latest_5min = df_5min.iloc[-1]
    latest_hourly = df_hourly.iloc[-1]
    latest_4h = df_4h.iloc[-1] if df_4h is not None else None
    
    # 평가 기준 결과 초기화
    long_criteria = []
    short_criteria = []
    
    # 트렌드 상태 초기화
    long_trend_disqualified = False
    short_trend_disqualified = False
    disqualification_reasons = []
    
    # 1. 극단적인 가격 레벨 확인 - 비트코인의 높은 변동성에 맞게 수정
    try:
        # 1시간 차트 극단 확인
        hourly_high = df_hourly['high'].max()
        hourly_low = df_hourly['low'].min()
        hourly_range = hourly_high - hourly_low
        
        # 상단 극단 확인 (신규: 볼린저 밴드와 연계)
        if ('bb_bbh' in latest_hourly and 
            current_price > latest_hourly['bb_bbh'] * 1.005 and 
            latest_hourly['rsi'] > 75):
            long_trend_disqualified = True
            disqualification_reasons.append(f"가격이 1시간 상단 밴드를 5% 이상 돌파 & RSI > 75")
        
        # 하단 극단 확인 (신규: 볼린저 밴드와 연계)
        if ('bb_bbl' in latest_hourly and 
            current_price < latest_hourly['bb_bbl'] * 0.995 and 
            latest_hourly['rsi'] < 25):
            short_trend_disqualified = True
            disqualification_reasons.append(f"가격이 1시간 하단 밴드를 5% 이상 하회 & RSI < 25")
        
        # 4시간 차트 극단 확인 - 비트코인의 상승 경향을 고려하여 비대칭 적용
        if df_4h is not None:
            four_hour_high = df_4h['high'].max()
            four_hour_low = df_4h['low'].min()
            four_hour_range = four_hour_high - four_hour_low
            
            # 상단 극단 확인 (상단 기준 7% - 비트코인의 상승 잠재력 감안)
            if ('bb_bbh' in latest_4h and 
                current_price > latest_4h['bb_bbh'] * 1.01 and
                latest_4h['rsi'] > 78):
                long_trend_disqualified = True
                disqualification_reasons.append(f"가격이 4시간 상단 밴드를 1% 이상 돌파 & RSI > 78")
            
            # 하단 극단 확인 (하단 기준 5% - 비트코인의 더 급격한 하락 특성 반영)
            if ('bb_bbl' in latest_4h and 
                current_price < latest_4h['bb_bbl'] * 0.99 and
                latest_4h['rsi'] < 22):
                short_trend_disqualified = True
                disqualification_reasons.append(f"가격이 4시간 하단 밴드를 1% 이상 하회 & RSI < 22")
    except Exception as e:
        logger.error(f"가격 극단치 확인 중 오류: {e}")
    
    # 2. RSI 과매수/과매도 확인 - 비트코인의 극단적 움직임을 허용하도록 수정
    try:
        # 1시간 RSI 확인 (컨텍스트 고려)
        hourly_rsi = latest_hourly['rsi']
        
        # 과매수 확인 (RSI > 78, 이전 70에서 상향)
        if hourly_rsi > 78:
            # 상승 모멘텀 확인 (제시된 데이터에서 강한 상승 경향 반영)
            if len(df_hourly) > 2:
                rsi_diff = hourly_rsi - df_hourly['rsi'].iloc[-2]
                # RSI가 약해질 때만 비적격으로 처리 (중요: 3으로 증가, 이전 1에서 상향)
                if rsi_diff < 3.0:
                    long_trend_disqualified = True
                    disqualification_reasons.append(f"1시간 RSI 과매수 및 약화 ({hourly_rsi:.2f}, 변화: {rsi_diff:.2f})")
        
        # 과매도 확인 (RSI < 22, 이전 25에서 하향)
        if hourly_rsi < 22:
            # 하락 모멘텀 확인
            if len(df_hourly) > 2:
                rsi_diff = hourly_rsi - df_hourly['rsi'].iloc[-2]
                # RSI가 강해질 때만 비적격으로 처리 (중요: -3으로 감소, 이전 -1에서 하향)
                if rsi_diff > -3.0:
                    short_trend_disqualified = True
                    disqualification_reasons.append(f"1시간 RSI 과매도 및 강화 ({hourly_rsi:.2f}, 변화: {rsi_diff:.2f})")
        
        # 4시간 RSI 확인 (비트코인의 변동성 고려하여 기준 조정)
        if df_4h is not None and 'rsi' in latest_4h:
            four_hour_rsi = latest_4h['rsi']
            
            # 4시간 RSI 과매수 임계값 증가 (비트코인의 강한 상승 고려)
            if four_hour_rsi > 80 and four_hour_rsi < df_4h['rsi'].iloc[-2]:
                long_trend_disqualified = True
                disqualification_reasons.append(f"4시간 RSI 강한 과매수 ({four_hour_rsi:.2f}) 및 하락 시작")
            
            # 4시간 RSI 과매도 임계값 감소 (급격한 하락 고려)
            if four_hour_rsi < 20 and four_hour_rsi > df_4h['rsi'].iloc[-2]:
                short_trend_disqualified = True
                disqualification_reasons.append(f"4시간 RSI 강한 과매도 ({four_hour_rsi:.2f}) 및 상승 시작")
    except Exception as e:
        logger.error(f"RSI 극단치 확인 중 오류: {e}")
    
    # 3. 연장된 트렌드 지속시간 확인 - 비트코인의 강한 트렌드 인정
    try:
        # 비트코인 시장의 특성에 맞게 마지막 15개 캔들 분석
        if 'ema_12' in df_5min.columns or 'sma_20' in df_5min.columns:
            last_15_candles = df_5min.iloc[-15:].copy()
            
            # 비율 계산
            bullish_count = sum(last_15_candles['close'] > last_15_candles['open'])
            bearish_count = sum(last_15_candles['close'] < last_15_candles['open'])
            
            # 비트코인의 강한 트렌드를 고려하여 기준 상향 (85% → 90%)
            if bullish_count / 15 >= 0.90:
                # 볼륨 프로필 확인 - 볼륨이 감소하고 MACD 약화될 때만 비적격으로
                if 'volume' in df_5min.columns and 'macd' in df_5min.columns:
                    recent_volume = df_5min['volume'].iloc[-3:].mean()
                    avg_volume = df_5min['volume'].iloc[-15:].mean()
                    macd_diff = df_5min['macd'].iloc[-1] - df_5min['macd'].iloc[-2]
                    
                    # 볼륨 감소 + MACD 약화 조합의 경우만 비적격
                    if recent_volume < avg_volume * 0.7 and macd_diff < 0:
                        long_trend_disqualified = True
                        disqualification_reasons.append(f"연장된 상승 트렌드 ({bullish_count}/15 상승 캔들), 볼륨 감소 및 MACD 약화")
            
            if bearish_count / 15 >= 0.90:
                # 볼륨 프로필 확인 - 볼륨이 감소하고 MACD 약화될 때만 비적격으로
                if 'volume' in df_5min.columns and 'macd' in df_5min.columns:
                    recent_volume = df_5min['volume'].iloc[-3:].mean()
                    avg_volume = df_5min['volume'].iloc[-15:].mean()
                    macd_diff = df_5min['macd'].iloc[-1] - df_5min['macd'].iloc[-2]
                    
                    # 볼륨 감소 + MACD 약화 조합의 경우만 비적격
                    if recent_volume < avg_volume * 0.7 and macd_diff > 0:
                        short_trend_disqualified = True
                        disqualification_reasons.append(f"연장된 하락 트렌드 ({bearish_count}/15 하락 캔들), 볼륨 감소 및 MACD 약화")
            
            # 연속 캔들 확인 - 비트코인의 보다 강한 트렌드를 허용
            consecutive_bullish = 0
            consecutive_bearish = 0
            max_consecutive_bullish = 0
            max_consecutive_bearish = 0
            
            for i in range(15):
                if i < len(last_15_candles):
                    if last_15_candles['close'].iloc[i] > last_15_candles['open'].iloc[i]:
                        consecutive_bullish += 1
                        consecutive_bearish = 0
                    else:
                        consecutive_bearish += 1
                        consecutive_bullish = 0
                        
                    max_consecutive_bullish = max(max_consecutive_bullish, consecutive_bullish)
                    max_consecutive_bearish = max(max_consecutive_bearish, consecutive_bearish)
            
            # 이례적으로 극단적인 연속 캔들만 고려 (12→15로 증가)
            if max_consecutive_bullish >= 15:
                long_trend_disqualified = True
                disqualification_reasons.append(f"15+ 연속 상승 캔들 감지 ({max_consecutive_bullish})")
                
            if max_consecutive_bearish >= 15:
                short_trend_disqualified = True
                disqualification_reasons.append(f"15+ 연속 하락 캔들 감지 ({max_consecutive_bearish})")
    except Exception as e:
        logger.error(f"트렌드 지속 시간 확인 중 오류: {e}")
    
    # 비적격 사유가 있으면 로깅
    if disqualification_reasons:
        logger.info(f"트렌드 비적격 사유: {disqualification_reasons}")
    
    # 비트코인 데이터에서 캔들 사이에 강한 이동을 더 잘 감지하기 위한 추가 확인
    # 캔들 폭 확인 (최근 3개 캔들)
    try:
        recent_candles = df_5min.tail(3)
        avg_candle_range = (recent_candles['high'] - recent_candles['low']).mean()
        latest_candle_range = recent_candles['high'].iloc[-1] - recent_candles['low'].iloc[-1]
        
        # 최근 가격 움직임의 속도 확인
        price_velocity = abs(recent_candles['close'].iloc[-1] - recent_candles['close'].iloc[-3]) / avg_candle_range
        
        # 강한 상승 모멘텀 (비트코인의 특성에 맞게 조정)
        if price_velocity > 1.8 and recent_candles['close'].iloc[-1] > recent_candles['close'].iloc[-3] and recent_candles['close'].iloc[-1] > recent_candles['open'].iloc[-1]:
            long_criteria.append(True)
            logger.info(f"강한 상승 모멘텀 감지: 가격 속도 = {price_velocity:.2f} (임계값 1.8)")
        
        # 강한 하락 모멘텀 (비트코인의 특성에 맞게 조정)
        if price_velocity > 1.8 and recent_candles['close'].iloc[-1] < recent_candles['close'].iloc[-3] and recent_candles['close'].iloc[-1] < recent_candles['open'].iloc[-1]:
            short_criteria.append(True)
            logger.info(f"강한 하락 모멘텀 감지: 가격 속도 = {price_velocity:.2f} (임계값 1.8)")

        if 'bb_bbh' in latest_5min and 'bb_bbl' in latest_5min and 'bb_bbm' in latest_5min:
            # 밴드 폭 및 기타 속성 계산
            band_width = latest_5min['bb_bbh'] - latest_5min['bb_bbl']
            
            # 최근 캔들 분석
            candle_analysis_window = min(20, len(df_5min) - 1)
            
            # ==== 개선된 브레이크아웃 감지 로직 ====
            
            # A. 브레이크아웃 분석용 데이터 수집
            candle_body_sizes = []       # 캔들 몸통 크기
            candle_ranges = []           # 고가-저가 범위
            candle_directions = []       # 캔들 방향 (1=상승, -1=하락)
            close_to_close_changes = []  # 종가-종가 변화
            
            for i in range(candle_analysis_window):
                idx = -(i + 1)  # 가장 최근 캔들부터
                
                # 몸통 크기 (절대값)
                body_size = abs(df_5min['close'].iloc[idx] - df_5min['open'].iloc[idx])
                candle_body_sizes.append(body_size)
                
                # 캔들 범위 (고가-저가)
                candle_range = df_5min['high'].iloc[idx] - df_5min['low'].iloc[idx]
                candle_ranges.append(candle_range)
                
                # 방향
                candle_dir = 1 if df_5min['close'].iloc[idx] >= df_5min['open'].iloc[idx] else -1
                candle_directions.append(candle_dir)
                
                # 종가-종가 변화 (첫 캔들 제외)
                if i > 0:
                    close_change = df_5min['close'].iloc[idx] - df_5min['close'].iloc[idx+1]
                    close_to_close_changes.append(close_change)
            
            # B. 통계 계산
            avg_body_size = sum(candle_body_sizes) / len(candle_body_sizes)
            avg_range = sum(candle_ranges) / len(candle_ranges)
            body_size_std = (sum((x - avg_body_size) ** 2 for x in candle_body_sizes) / len(candle_body_sizes)) ** 0.5
            range_std = (sum((x - avg_range) ** 2 for x in candle_ranges) / len(candle_ranges)) ** 0.5
            
            # 볼륨 분석
            has_volume_data = 'volume' in df_5min.columns
            if has_volume_data:
                candle_volumes = [df_5min['volume'].iloc[-i-1] for i in range(candle_analysis_window)]
                avg_volume = sum(candle_volumes) / len(candle_volumes)
                volume_std = (sum((x - avg_volume) ** 2 for x in candle_volumes) / len(candle_volumes)) ** 0.5
            
            # C. 최근 캔들 집중 분석
            recent_bodies = candle_body_sizes[:3]
            recent_ranges = candle_ranges[:3]
            recent_directions = candle_directions[:3]
            recent_volumes = candle_volumes[:3] if has_volume_data else []
            
            # D. 브레이크아웃 판단 로직 (개선된 컨텍스트)
            is_breakout = False
            breakout_direction = 0  # 0=없음, 1=상승, -1=하락
            breakout_reasons = []
            
            # 확인 1: 최근 캔들 크기 이상치
            # 비트코인의 빠른 가격 변화 고려 - 1.5 → 1.3으로 완화
            if recent_bodies[0] > avg_body_size + 1.3 * body_size_std:
                breakout_reasons.append(f"이례적으로 큰 최근 캔들 몸통 ({recent_bodies[0]:.2f} vs 평균 {avg_body_size:.2f})")
                
            # 확인 2: 방향 일관성
            recent_direction_sum = sum(recent_directions)
            if abs(recent_direction_sum) >= 2:  # 최소 3개 중 2개 캔들이 같은 방향
                direction_str = "상승" if recent_direction_sum > 0 else "하락"
                breakout_reasons.append(f"최근 캔들에서 일관된 {direction_str} 방향")
                breakout_direction = 1 if recent_direction_sum > 0 else -1
            
            # 확인 3: 최근 종가 변화 이상치
            if close_to_close_changes:
                avg_close_change = sum(abs(x) for x in close_to_close_changes) / len(close_to_close_changes)
                recent_close_change = abs(df_5min['close'].iloc[-1] - df_5min['close'].iloc[-2])
                
                # 비트코인의 급격한 가격 변화 고려 - 1.8 → 1.6으로 완화
                if recent_close_change > avg_close_change * 1.6:
                    breakout_reasons.append(f"큰 폭의 가격 이동 ({recent_close_change:.2f} vs 평균 {avg_close_change:.2f})")
            
            # 확인 4: 볼륨 급증 (데이터 있는 경우)
            if has_volume_data and recent_volumes:
                recent_volume = recent_volumes[0]
                # 비트코인의 빠른 거래량 변화 고려 - 1.2 → 1.1로 완화
                if recent_volume > avg_volume + 1.1 * volume_std:
                    breakout_reasons.append(f"볼륨 급증 ({recent_volume:.2f} vs 평균 {avg_volume:.2f})")
            
            # 확인 5: 볼린저 밴드 확장/수축
            recent_band_widths = []
            for i in range(min(10, len(df_5min))):
                idx = -i - 1
                if idx >= -len(df_5min) and 'bb_bbh' in df_5min.iloc[idx] and 'bb_bbl' in df_5min.iloc[idx]:
                    width = df_5min.iloc[idx]['bb_bbh'] - df_5min.iloc[idx]['bb_bbl']
                    recent_band_widths.append(width)
            
            if len(recent_band_widths) >= 5:
                # 밴드 폭 변화율 계산
                band_width_change_ratio = recent_band_widths[0] / recent_band_widths[4]
                
                # 비트코인의 빠른 밴드 확장 고려 - 1.15 → 1.12로 완화
                if band_width_change_ratio > 1.12:
                    breakout_reasons.append(f"볼린저 밴드 확장 ({(band_width_change_ratio-1)*100:.1f}% 증가)")
                # 비트코인의 빠른 밴드 수축 고려 - 0.9 → 0.92로 완화
                elif band_width_change_ratio < 0.92:
                    # 중앙선에서 가격 거리
                    middle_to_price_ratio = abs(current_price - latest_5min['bb_bbm']) / band_width
                    # 비트코인의 빠른 밴드 이탈 고려 - 0.35 → 0.32로 완화
                    if middle_to_price_ratio > 0.32:
                        breakout_reasons.append(f"잠재적 스퀴즈 브레이크아웃 (밴드 수축 중, 가격이 중앙에서 이탈)")
            
            # 통합 브레이크아웃 분석 결과
            # 비트코인의 빠른 브레이크아웃 고려 - 필요 이유 수 2→1로 완화
            if len(breakout_reasons) >= 1 and breakout_direction != 0:
                is_breakout = True
                logger.info(f"브레이크아웃 감지 ({breakout_direction > 0 and '상승' or '하락'}) - 이유: {', '.join(breakout_reasons)}")
            
            # ==== 컨텍스트를 고려한 볼린저 밴드 경계 분석 ====
            
            # 거리 임계값 계산 - 비트코인의 높은 변동성 고려
            threshold_distance = band_width * 0.2  # 0.18 → 0.2로 증가
            
            # 거리 계산
            distance_to_upper = latest_5min['bb_bbh'] - current_price
            distance_to_lower = current_price - latest_5min['bb_bbl']
            
            # 상단 밴드 분석
            if distance_to_upper <= threshold_distance or current_price > latest_5min['bb_bbh']:
                # 유효한 브레이크아웃이 감지된 경우, 상단 밴드 위에 있어도 비적격으로 처리하지 않음
                if is_breakout and breakout_direction > 0:  # 상승 브레이크아웃
                    if current_price > latest_5min['bb_bbh']:
                        logger.info("가격이 상단 볼린저 밴드 위지만 유효한 상승 브레이크아웃으로 간주")
                        # 극단적으로 확장된 경우만 비적격 처리
                        # 비트코인의 강한 돌파 허용 - 0.6 → 0.7로 증가
                        excessive_ratio = (current_price - latest_5min['bb_bbh']) / band_width
                        if excessive_ratio > 0.7:
                            long_trend_disqualified = True
                            disqualification_reasons.append(f"가격이 상단 BB를 과도하게 초과 ({excessive_ratio:.2f} 밴드 폭)")
                    else:
                        logger.info("가격이 상단 볼린저 밴드 부근에 있으며, 유효한 상승 브레이크아웃 신호 감지")
                else:
                    # 브레이크아웃 아님 - 모멘텀과 컨텍스트 확인
                    # 비트코인의 경우: 밴드 위에서 여러 캔들 동안 머물 수 있는지 확인
                    above_band_count = 0
                    for i in range(min(3, len(df_5min))):
                        if i < len(df_5min) and df_5min['close'].iloc[-i-1] > df_5min['bb_bbh'].iloc[-i-1]:
                            above_band_count += 1
                    
                    # 가격이 일관되게 밴드 위에 있고 여전히 상승 중인 경우
                    if above_band_count >= 2 and df_5min['close'].iloc[-1] > df_5min['close'].iloc[-2]:
                        # 볼륨이 여전히 강한지 확인
                        if has_volume_data and recent_volumes[0] > avg_volume:
                            # 비적격으로 처리하지 않음 - 비트코인의 강한 모멘텀일 수 있음
                            logger.info(f"가격이 {above_band_count}개 캔들 동안 밴드 위에 있고 가격 상승 및 강한 볼륨 - 유효한 추세 지속")
                        else:
                            long_trend_disqualified = True
                            disqualification_reasons.append(f"가격이 {above_band_count}개 캔들 동안 밴드 위에 있지만 강한 볼륨 없음")
                    else:
                        long_trend_disqualified = True
                        if current_price > latest_5min['bb_bbh']:
                            disqualification_reasons.append("가격이 상단 볼린저 밴드 위에 있지만 브레이크아웃 신호 없음")
                        else:
                            percent_to_upper = (distance_to_upper / band_width) * 100
                            disqualification_reasons.append(f"가격이 상단 BB 부근 (상단에서 {percent_to_upper:.2f}%) 이지만 브레이크아웃 신호 없음")
            
            # 하단 밴드 분석 (위와 동일한 로직 구조)
            if distance_to_lower <= threshold_distance or current_price < latest_5min['bb_bbl']:
                # 유효한 브레이크아웃이 감지된 경우, 하단 밴드 아래에 있어도 비적격으로 처리하지 않음
                if is_breakout and breakout_direction < 0:  # 하락 브레이크아웃
                    if current_price < latest_5min['bb_bbl']:
                        logger.info("가격이 하단 볼린저 밴드 아래지만 유효한 하락 브레이크아웃으로 간주")
                        # 극단적으로 확장된 경우만 비적격 처리
                        # 비트코인의 강한 하락 허용 - 0.6 → 0.7로 증가
                        excessive_ratio = (latest_5min['bb_bbl'] - current_price) / band_width
                        if excessive_ratio > 0.7:
                            short_trend_disqualified = True
                            disqualification_reasons.append(f"가격이 하단 BB 아래로 과도하게 이탈 ({excessive_ratio:.2f} 밴드 폭)")
                    else:
                        logger.info("가격이 하단 볼린저 밴드 부근에 있으며, 유효한 하락 브레이크아웃 신호 감지")
                else:
                    # 브레이크아웃 아님 - 모멘텀과 컨텍스트 확인
                    # 비트코인의 경우: 밴드 아래에서 여러 캔들 동안 머물 수 있는지 확인
                    below_band_count = 0
                    for i in range(min(3, len(df_5min))):
                        if i < len(df_5min) and df_5min['close'].iloc[-i-1] < df_5min['bb_bbl'].iloc[-i-1]:
                            below_band_count += 1
                    
                    # 가격이 일관되게 밴드 아래에 있고 여전히 하락 중인 경우
                    if below_band_count >= 2 and df_5min['close'].iloc[-1] < df_5min['close'].iloc[-2]:
                        # 볼륨이 여전히 강한지 확인
                        if has_volume_data and recent_volumes[0] > avg_volume:
                            # 비적격으로 처리하지 않음 - 비트코인의 강한 모멘텀일 수 있음
                            logger.info(f"가격이 {below_band_count}개 캔들 동안 밴드 아래에 있고 가격 하락 및 강한 볼륨 - 유효한 추세 지속")
                        else:
                            short_trend_disqualified = True
                            disqualification_reasons.append(f"가격이 {below_band_count}개 캔들 동안 밴드 아래에 있지만 강한 볼륨 없음")
                    else:
                        short_trend_disqualified = True
                        if current_price < latest_5min['bb_bbl']:
                            disqualification_reasons.append("가격이 하단 볼린저 밴드 아래에 있지만 브레이크아웃 신호 없음")
                        else:
                            percent_to_lower = (distance_to_lower / band_width) * 100
                            disqualification_reasons.append(f"가격이 하단 BB 부근 (하단에서 {percent_to_lower:.2f}%) 이지만 브레이크아웃 신호 없음")
    except Exception as e:
        logger.error(f"트렌드 지속 시간 확인 중 오류: {e}")
    
    # 긍정적 기준 확인 - 비적격이 아닌 경우만 실행
    if not long_trend_disqualified or not short_trend_disqualified:
        # 5분 차트에서 EMA 위치 확인 (기준 1)
        try:
            ema12 = latest_5min.get('ema_12', 0)
            sma20 = latest_5min.get('sma_20', 0)
            
            if ema12 > 0 and sma20 > 0:
                # 롱 기준 - 비트코인의 빠른 움직임을 고려해 완화된 임계값
                if current_price > ema12 and current_price > sma20 and ema12 > sma20:
                    # 0.001 → 0.0007로 완화
                    if (current_price - ema12) / ema12 > 0.0007:
                        long_criteria.append(True)
                
                # 숏 기준
                if current_price < ema12 and current_price < sma20 and ema12 < sma20:
                    # 0.001 → 0.0007로 완화
                    if (ema12 - current_price) / ema12 > 0.0007:
                        short_criteria.append(True)
        except Exception as e:
            logger.error(f"EMA 확인 중 오류: {e}")
        
        # 연속 캔들 방향 확인 (기준 2) - 비트코인의 빠른 움직임에 맞게 수정
        try:
            # 최근 4개 캔들 가져오기 (이전 4개에서 완화)
            recent_candles = df_5min.iloc[-3:].copy()
            
            # 롱: 3개 캔들 중 2개 이상 상승 캔들 (4/5→2/3로 완화)
            bullish_count = sum(recent_candles['close'] > recent_candles['open'])
            if bullish_count >= 2 and recent_candles['close'].iloc[-1] > recent_candles['close'].iloc[-2]:
                # 최근 캔들이 상승이고 최소 0.05% 상승 (0.08%→0.05%로 완화)
                if (recent_candles['close'].iloc[-1] > recent_candles['open'].iloc[-1] and
                    (recent_candles['close'].iloc[-1] - recent_candles['open'].iloc[-1]) / recent_candles['open'].iloc[-1] > 0.0005):
                    long_criteria.append(True)
            
            # 숏: 3개 캔들 중 2개 이상 하락 캔들 (4/5→2/3로 완화)
            bearish_count = sum(recent_candles['close'] < recent_candles['open'])
            if bearish_count >= 2 and recent_candles['close'].iloc[-1] < recent_candles['close'].iloc[-2]:
                # 최근 캔들이 하락이고 최소 0.05% 하락 (0.08%→0.05%로 완화)
                if (recent_candles['close'].iloc[-1] < recent_candles['open'].iloc[-1] and
                    (recent_candles['open'].iloc[-1] - recent_candles['close'].iloc[-1]) / recent_candles['open'].iloc[-1] > 0.0005):
                    short_criteria.append(True)
        except Exception as e:
            logger.error(f"연속 캔들 확인 중 오류: {e}")
        
        # MACD 히스토그램 방향 확인 (기준 3) - 비트코인의 빠른 움직임에 맞게 수정
        try:
            if 'macd_diff' in df_5min.columns:
                recent_macd = df_5min['macd_diff'].iloc[-3:].values
                
                # 롱: MACD 히스토그램 2+ 캔들 증가 (3→2로 완화)
                if (len(recent_macd) >= 3 and
                    recent_macd[-1] > 0 and 
                    recent_macd[-1] > recent_macd[-2] and
                    # 절대값 임계치 - 0.6 → 0.4로 완화 (비트코인의 빠른 신호 포착)
                    abs(recent_macd[-1]) > 0.4):
                    long_criteria.append(True)
                
                # 숏: MACD 히스토그램 2+ 캔들 감소 (3→2로 완화)
                if (len(recent_macd) >= 3 and
                    recent_macd[-1] < 0 and 
                    recent_macd[-1] < recent_macd[-2] and
                    # 절대값 임계치 - 0.6 → 0.4로 완화 (비트코인의 빠른 신호 포착)
                    abs(recent_macd[-1]) > 0.4):
                    short_criteria.append(True)
        except Exception as e:
            logger.error(f"MACD 확인 중 오류: {e}")
        
        # 고점과 저점 패턴 확인 (기준 4)
        try:
            # 15개 캔들 분석 (20→15로 단축, 비트코인의 빠른 움직임 고려)
            last_15_candles = df_5min.iloc[-15:].copy()
            
            # 스윙 고점과 저점 식별
            highs = []
            lows = []
            
            for i in range(1, len(last_15_candles) - 1):
                # 스윙 고점
                if last_15_candles['high'].iloc[i] > last_15_candles['high'].iloc[i-1] and \
                   last_15_candles['high'].iloc[i] > last_15_candles['high'].iloc[i+1]:
                    highs.append(last_15_candles['high'].iloc[i])
                
                # 스윙 저점
                if last_15_candles['low'].iloc[i] < last_15_candles['low'].iloc[i-1] and \
                   last_15_candles['low'].iloc[i] < last_15_candles['low'].iloc[i+1]:
                    lows.append(last_15_candles['low'].iloc[i])
            
            # 최소 3개 스윙 포인트 필요 (4→3으로 완화)
            if len(highs) >= 3 and len(lows) >= 3:
                # 롱 기준: 높아지는 고점과 저점 (0.08% → 0.06%로 완화)
                higher_highs = all(highs[-1] > h * 1.0006 for h in highs[:-1])
                higher_lows = all(lows[i] > lows[i-1] * 1.0006 for i in range(1, len(lows)))
                
                if higher_highs and higher_lows:
                    long_criteria.append(True)
            
                # 숏 기준: 낮아지는 고점과 저점 (0.08% → 0.06%로 완화)
                lower_highs = all(highs[i] < highs[i-1] * 0.9994 for i in range(1, len(highs)))
                lower_lows = all(lows[-1] < l * 0.9994 for l in lows[:-1])
                
                if lower_highs and lower_lows:
                    short_criteria.append(True)
        except Exception as e:
            logger.error(f"가격 구조 확인 중 오류: {e}")
        
        # 1시간 타임프레임 추세 확인 (기준 5) - ADX
        try:
            hourly_adx = latest_hourly['adx']
            hourly_di_plus = latest_hourly['di_plus']
            hourly_di_minus = latest_hourly['di_minus']
            
            # 롱: ADX > 21 (25→21로 완화) & DI+ > DI-
            if hourly_adx > 21 and hourly_di_plus > hourly_di_minus:
                # 차이 임계값 (8→5로 완화)
                if hourly_di_plus - hourly_di_minus > 5:
                    long_criteria.append(True)
            
            # 숏: ADX > 21 (25→21로 완화) & DI- > DI+
            if hourly_adx > 21 and hourly_di_minus > hourly_di_plus:
                # 차이 임계값 (8→5로 완화)
                if hourly_di_minus - hourly_di_plus > 5:
                    short_criteria.append(True)
        except Exception as e:
            logger.error(f"1시간 ADX 확인 중 오류: {e}")
        
        # 4시간 차트 MACD 방향 확인 (기준 6) - 비트코인의 빠른 진입을 위해 완화
        try:
            if df_4h is not None and 'macd' in df_4h.columns and 'macd_signal' in df_4h.columns:
                # 4시간 MACD 방향 확인
                four_hour_macd = df_4h['macd'].iloc[-3:].values
                four_hour_macd_signal = df_4h['macd_signal'].iloc[-3:].values
                
                # 롱: MACD 시그널선 위로 교차 또는 약세로부터 강세로 전환
                macd_cross_bullish = (len(four_hour_macd) >= 2 and 
                                     four_hour_macd[-2] < four_hour_macd_signal[-2] and 
                                     four_hour_macd[-1] > four_hour_macd_signal[-1])
                macd_bullish_conv = (len(four_hour_macd) >= 3 and 
                                    four_hour_macd[-1] < 0 and  # 여전히 음수이지만
                                    four_hour_macd[-1] > four_hour_macd[-2] and  # 2+ 캔들 상승
                                    four_hour_macd[-2] > four_hour_macd[-3])
                
                # 제로 크로싱 임계값 - 비트코인의 빠른 움직임 고려 -5 → -7로 완화
                if macd_cross_bullish or (macd_bullish_conv and four_hour_macd[-1] > -7):
                    long_criteria.append(True)
                
                # 숏: MACD 시그널선 아래로 교차 또는 강세로부터 약세로 전환
                macd_cross_bearish = (len(four_hour_macd) >= 2 and
                                     four_hour_macd[-2] > four_hour_macd_signal[-2] and 
                                     four_hour_macd[-1] < four_hour_macd_signal[-1])
                macd_bearish_conv = (len(four_hour_macd) >= 3 and
                                    four_hour_macd[-1] > 0 and  # 여전히 양수이지만
                                    four_hour_macd[-1] < four_hour_macd[-2] and  # 2+ 캔들 하락
                                    four_hour_macd[-2] < four_hour_macd[-3])
                
                # 제로 크로싱 임계값 - 비트코인의 빠른 움직임 고려 5 → 7로 완화
                if macd_cross_bearish or (macd_bearish_conv and four_hour_macd[-1] < 7):
                    short_criteria.append(True)
        except Exception as e:
            logger.error(f"4시간 MACD 확인 중 오류: {e}")
        
        # 새로 추가: 볼륨 프로필 확인 (기준 7) - 비트코인 시장에 맞게 조정
        try:
            if 'volume' in df_5min.columns:
                # 최근 볼륨 데이터
                recent_5_volume = df_5min['volume'].iloc[-5:].values
                recent_10_volume = df_5min['volume'].iloc[-10:].values
                
                # 볼륨 트렌드 계산
                avg_5_volume = sum(recent_5_volume) / 5
                avg_10_volume = sum(recent_10_volume) / 10
                
                # 최근 캔들 방향 확인
                recent_3_candles = df_5min.iloc[-3:].copy()
                bullish_candles = sum(1 for i in range(len(recent_3_candles)) if recent_3_candles['close'].iloc[i] > recent_3_candles['open'].iloc[i])
                bearish_candles = sum(1 for i in range(len(recent_3_candles)) if recent_3_candles['close'].iloc[i] < recent_3_candles['open'].iloc[i])
                
                # 롱: 볼륨 증가 + 상승 캔들
                # 비트코인의 빠른 볼륨 증가 고려 - 1.1 → 1.07로 완화
                if avg_5_volume > avg_10_volume * 1.07 and bullish_candles >= 2:
                    # 볼륨 가중 평균 상승 대 하락 볼륨
                    bullish_volume = sum(df_5min['volume'].iloc[-i-1] for i in range(5) 
                                        if df_5min['close'].iloc[-i-1] > df_5min['open'].iloc[-i-1])
                    bearish_volume = sum(df_5min['volume'].iloc[-i-1] for i in range(5) 
                                        if df_5min['close'].iloc[-i-1] < df_5min['open'].iloc[-i-1])
                    
                    if bullish_volume > bearish_volume:
                        long_criteria.append(True)
                
                # 숏: 볼륨 증가 + 하락 캔들
                if avg_5_volume > avg_10_volume * 1.07 and bearish_candles >= 2:
                    # 볼륨 가중 평균 상승 대 하락 볼륨
                    bullish_volume = sum(df_5min['volume'].iloc[-i-1] for i in range(5) 
                                        if df_5min['close'].iloc[-i-1] > df_5min['open'].iloc[-i-1])
                    bearish_volume = sum(df_5min['volume'].iloc[-i-1] for i in range(5) 
                                        if df_5min['close'].iloc[-i-1] < df_5min['open'].iloc[-i-1])
                    
                    if bearish_volume > bullish_volume:
                        short_criteria.append(True)
        except Exception as e:
            logger.error(f"볼륨 프로필 확인 중 오류: {e}")
        
        # 새로 추가: 멀티타임프레임 모멘텀 정렬 (기준 8) - 비트코인에 맞게
        try:
            # RSI로 타임프레임 간 모멘텀 정렬 확인
            if 'rsi' in latest_5min and 'rsi' in latest_hourly:
                # 롱 추세
                if latest_5min['rsi'] > 50 and latest_hourly['rsi'] > 50:
                    # 비트코인의 빠른 움직임 - 이전 캔들과 비교하지 않고, 1시간 RSI 기준 완화
                    if latest_hourly['rsi'] > 45:
                        long_criteria.append(True)
                
                # 숏 추세
                if latest_5min['rsi'] < 50 and latest_hourly['rsi'] < 50:
                    # 비트코인의 빠른 움직임 - 이전 캔들과 비교하지 않고, 1시간 RSI 기준 완화
                    if latest_hourly['rsi'] < 55:
                        short_criteria.append(True)
                
                # 4시간 모멘텀 확인
                if df_4h is not None and 'rsi' in latest_4h:
                    # 강한 상승 정렬 - 비트코인의 변동성 고려 50 → 48로 완화
                    if latest_5min['rsi'] > 50 and latest_hourly['rsi'] > 50 and latest_4h['rsi'] > 48:
                        long_criteria.append(True)  # 멀티타임프레임 정렬 점수 추가
                    
                    # 강한 하락 정렬 - 비트코인의 변동성 고려 50 → 52로 완화
                    if latest_5min['rsi'] < 50 and latest_hourly['rsi'] < 50 and latest_4h['rsi'] < 52:
                        short_criteria.append(True)  # 멀티타임프레임 정렬 점수 추가
        except Exception as e:
            logger.error(f"멀티타임프레임 정렬 확인 중 오류: {e}")
        
        # 새로 추가: 볼린저 밴드 폭 확인 (비트코인 특화)
        try:
            if 'bb_bbh' in latest_5min and 'bb_bbl' in latest_5min and 'bb_bbm' in latest_5min:
                # 현재 밴드 폭 계산
                current_band_width = latest_5min['bb_bbh'] - latest_5min['bb_bbl']
                
                # 최근 20개 캔들의 밴드 폭 평균
                if len(df_5min) >= 20:
                    band_widths = [(df_5min['bb_bbh'].iloc[-i] - df_5min['bb_bbl'].iloc[-i]) 
                                 for i in range(1, 21) if 'bb_bbh' in df_5min.iloc[-i] and 'bb_bbl' in df_5min.iloc[-i]]
                    if band_widths:
                        avg_band_width = sum(band_widths) / len(band_widths)
                        
                        # 밴드 폭이 좁아지고 있는지 확인 (스퀴즈 전)
                        if current_band_width < avg_band_width * 0.9:
                            # 가격이 중앙선에 가까워지고 있음 (잠재적 발사 준비)
                            price_to_mid = abs(current_price - latest_5min['bb_bbm'])
                            if price_to_mid < current_band_width * 0.2:
                                logger.info("볼린저 밴드 스퀴즈 상태 감지 - 브레이크아웃 가능성 높음")
                                # 최근 3캔들의 방향을 확인하여 방향 결정
                                recent_direction = sum(1 if df_5min['close'].iloc[-i] > df_5min['open'].iloc[-i] else -1 
                                                      for i in range(1, 4))
                                if recent_direction > 0:
                                    long_criteria.append(True)
                                elif recent_direction < 0:
                                    short_criteria.append(True)
        except Exception as e:
            logger.error(f"볼린저 밴드 폭 확인 중 오류: {e}")
        
        # 새로 추가: 비트코인 특성 반영한 ADX 확인
        try:
            # ADX 임계값 - 비트코인의 빠른 움직임에 맞게 감소 (20이상)
            if latest_5min['adx'] > 20:
                # +DI > -DI이고, 가격이 상승 중이면 상승 추세
                if latest_5min['di_plus'] > latest_5min['di_minus'] and latest_5min['close'] > latest_5min['open']:
                    long_criteria.append(True)
                
                # -DI > +DI이고, 가격이 하락 중이면 하락 추세
                if latest_5min['di_minus'] > latest_5min['di_plus'] and latest_5min['close'] < latest_5min['open']:
                    short_criteria.append(True)
        except Exception as e:
            logger.error(f"ADX 확인 중 오류: {e}")
    
    # 최종 평가: 비트코인에 대해 필요한 기준 개수 감소 (3 → 2)
    long_trend_is_strong = (not long_trend_disqualified) and (len(long_criteria) >= 2)
    short_trend_is_strong = (not short_trend_disqualified) and (len(short_criteria) >= 2)
    
    result = {
        "long_trend_strong": long_trend_is_strong,
        "short_trend_strong": short_trend_is_strong,
        "long_criteria_count": len(long_criteria),
        "short_criteria_count": len(short_criteria),
        "long_disqualified": long_trend_disqualified,
        "short_disqualified": short_trend_disqualified,
        "disqualification_reasons": disqualification_reasons
    }
    logger.info(f"트렌드 강도 평가 결과: {result}")
    return result

# 2. assess_exit_signals 함수 최적화

def assess_exit_signals(df_5min, signals_data, position_side):
    """
    강력한 규칙 기반 출구 신호 평가 - 비트코인 시장에 최적화
    
    Args:
        df_5min: 5분 OHLCV 데이터프레임 (지표 포함)
        signals_data: 차트 분석에서 얻은 신호 데이터 딕셔너리
        position_side: 현재 포지션 방향 ('long', 'short', 또는 None)
        
    Returns:
        dict: 출구 평가 결과를 담은 딕셔너리
    """
    # 시작 로깅
    logger.info(f"포지션 방향 {position_side}에 대한 출구 신호 평가 시작")
    
    # 포지션이 없으면 출구가 필요 없음
    if not position_side:
        logger.info("열린 포지션 없음 - 출구 필요 없음")
        return {"should_exit": False, "exit_signals": []}
        
    exit_signals = []
    exit_signal_weights = []  # 각 출구 신호에 가중치 부여
    
    # 1. 두 핵심 신호가 모두 반전되었는지 확인 (강화된 조건)
    try:
        # 비트코인의 빠른 움직임을 고려하여 캔들 기준 수정 (3→4)
        if position_side == 'long':
            bf_reversed = signals_data.get("BlackFlag_Signal") == "Sell" and signals_data.get("BlackFlag_CandlesAgo", 999) <= 4
            ut_reversed = signals_data.get("UTBot_Signal") == "Sell" and signals_data.get("UTBot_CandlesAgo", 999) <= 4
            
            if bf_reversed and ut_reversed:  # 두 신호 모두 반전되고 최근인 경우
                exit_signals.append("BlackFlag 및 UTBot 신호가 최근에 Sell로 반전됨 (4 캔들 이내)")
                exit_signal_weights.append(1.0)  # 높은 가중치
            elif bf_reversed and signals_data.get("BlackFlag_CandlesAgo", 999) <= 1:  # BlackFlag만 반전되었지만 매우 최근인 경우
                exit_signals.append("최근 BlackFlag FTS 신호가 Sell로 반전됨 (1 캔들 이내)")
                exit_signal_weights.append(0.75)  # 중간-높은 가중치 (0.7→0.75로 상향)
            elif ut_reversed and signals_data.get("UTBot_CandlesAgo", 999) <= 1:  # UTBot만 반전되었지만 매우 최근인 경우
                exit_signals.append("최근 UTBot 신호가 Sell로 반전됨 (1 캔들 이내)")
                exit_signal_weights.append(0.65)  # 중간 가중치 (0.6→0.65로 상향)
                
        elif position_side == 'short':
            bf_reversed = signals_data.get("BlackFlag_Signal") == "Buy" and signals_data.get("BlackFlag_CandlesAgo", 999) <= 4
            ut_reversed = signals_data.get("UTBot_Signal") == "Buy" and signals_data.get("UTBot_CandlesAgo", 999) <= 4
            
            if bf_reversed and ut_reversed:  # 두 신호 모두 반전되고 최근인 경우
                exit_signals.append("BlackFlag 및 UTBot 신호가 최근에 Buy로 반전됨 (4 캔들 이내)")
                exit_signal_weights.append(1.0)  # 높은 가중치
            elif bf_reversed and signals_data.get("BlackFlag_CandlesAgo", 999) <= 1:  # BlackFlag만 반전되었지만 매우 최근인 경우
                exit_signals.append("최근 BlackFlag FTS 신호가 Buy로 반전됨 (1 캔들 이내)")
                exit_signal_weights.append(0.75)  # 중간-높은 가중치 (0.7→0.75로 상향)
            elif ut_reversed and signals_data.get("UTBot_CandlesAgo", 999) <= 1:  # UTBot만 반전되었지만 매우 최근인 경우
                exit_signals.append("최근 UTBot 신호가 Buy로 반전됨 (1 캔들 이내)")
                exit_signal_weights.append(0.65)  # 중간 가중치 (0.6→0.65로 상향)
    except Exception as e:
        logger.error(f"핵심 신호 반전 확인 중 오류: {e}")
    
    # 2. Volume Oscillator가 0% 아래로 떨어지는지 확인 - 강화: 연속적인 음수 패턴 확인 (더 엄격한 기준으로)
    try:
        volume_osc_current = signals_data.get("VolumeOsc_Current")
        volume_osc_history = signals_data.get("VolumeOsc_History", [])
        
        # 최소 3개 이상의 연속된 음수 값이 있는지 확인 (현재 포함)
        consecutive_negative = 0
        
        # 비트코인의 빠른 움직임 고려해 기준 조정 (-20 → -18)
        if volume_osc_current is not None and isinstance(volume_osc_history, list) and len(volume_osc_history) >= 3:
            for i in range(min(5, len(volume_osc_history))):  # 최근 5개만 확인
                idx = len(volume_osc_history) - 1 - i
                if idx >= 0 and volume_osc_history[idx] is not None and float(volume_osc_history[idx]) < -18:
                    consecutive_negative += 1
                else:
                    break  # 연속성이 깨지면 중단
                    
        # 3개 이상 연속으로 상당히 음수 (-18 미만)인 경우에만 유효한 출구 신호로 간주
        if consecutive_negative >= 3:
            exit_signals.append(f"Volume Oscillator가 연속적으로 음수 (-18 미만): {consecutive_negative}개 연속 캔들")
            exit_signal_weights.append(0.75)  # 중간-높은 가중치 (0.7→0.75로 상향)
        # 현재 값이 매우 낮은 경우 (-30 → -28로 완화)
        elif volume_osc_current is not None and float(volume_osc_current) < -28:
            exit_signals.append(f"Volume Oscillator 심각한 음수 (-28 미만): {volume_osc_current}")
            exit_signal_weights.append(0.65)  # 중간 가중치 (0.6→0.65로 상향)
    except Exception as e:
        logger.error(f"Volume Oscillator 확인 중 오류: {e}")
    
    # 3. RSI 또는 MACD에서 강한 다이버전스 확인 - 강화: 더 명확한 다이버전스 패턴 식별
    try:
        # 다이버전스 체크를 위해 최근 8개 캔들 가져오기
        recent_df = df_5min.iloc[-8:].copy()
        
        # 롱 포지션에서의 베어리시 다이버전스 감지
        if position_side == 'long':
            # 더 정교한 다이버전스 패턴 - 최소 2개의 피크 포인트 필요
            # 가격 피크 찾기
            price_peaks = []
            for i in range(1, len(recent_df) - 1):
                if recent_df['close'].iloc[i] > recent_df['close'].iloc[i-1] and recent_df['close'].iloc[i] > recent_df['close'].iloc[i+1]:
                    price_peaks.append((i, recent_df['close'].iloc[i]))
            
            # RSI 피크 찾기
            rsi_peaks = []
            for i in range(1, len(recent_df) - 1):
                if recent_df['rsi'].iloc[i] > recent_df['rsi'].iloc[i-1] and recent_df['rsi'].iloc[i] > recent_df['rsi'].iloc[i+1]:
                    rsi_peaks.append((i, recent_df['rsi'].iloc[i]))
            
            # 유효한 피크가 최소 2개 있는지 확인
            if len(price_peaks) >= 2 and len(rsi_peaks) >= 2:
                # 최근 두 개의 가격 피크와 RSI 피크 비교
                price_peak1, price_peak2 = price_peaks[-2:]
                rsi_peak1, rsi_peak2 = rsi_peaks[-2:]
                
                # 비트코인 시장에 맞게 기준 조정 (1.003 → 1.002, 0.97 → 0.975)
                # 가격은 더 높은 고점을 만들고 RSI는 더 낮은 고점을 만드는지 확인 (명확한 다이버전스)
                if (price_peak2[1] > price_peak1[1] * 1.002) and (rsi_peak2[1] < rsi_peak1[1] * 0.975):
                    exit_signals.append("롱 포지션에서 명확한 RSI 베어리시 다이버전스 감지 (가격은 더 높은 고점, RSI는 더 낮은 고점)")
                    exit_signal_weights.append(0.85)  # 높은 가중치 (0.8→0.85로 상향)
            
            # MACD 다이버전스 - 더 강화된 조건
            if 'macd' in recent_df.columns:
                # MACD 피크 찾기
                macd_peaks = []
                for i in range(1, len(recent_df) - 1):
                    if recent_df['macd'].iloc[i] > recent_df['macd'].iloc[i-1] and recent_df['macd'].iloc[i] > recent_df['macd'].iloc[i+1]:
                        macd_peaks.append((i, recent_df['macd'].iloc[i]))
                
                # 유효한 피크가 최소 2개 있는지 확인
                if len(price_peaks) >= 2 and len(macd_peaks) >= 2:
                    # 최근 두 개의 가격 피크와 MACD 피크 비교
                    price_peak1, price_peak2 = price_peaks[-2:]
                    macd_peak1, macd_peak2 = macd_peaks[-2:]
                    
                    # 비트코인 시장에 맞게 기준 조정 (1.003 → 1.002, 0.97 → 0.975)
                    # 가격은 더 높은 고점을 만들고 MACD는 더 낮은 고점을 만드는지 확인 (명확한 다이버전스)
                    if (price_peak2[1] > price_peak1[1] * 1.002) and (macd_peak2[1] < macd_peak1[1] * 0.975):
                        exit_signals.append("롱 포지션에서 명확한 MACD 베어리시 다이버전스 감지 (가격은 더 높은 고점, MACD는 더 낮은 고점)")
                        exit_signal_weights.append(0.85)  # 높은 가중치 (0.8→0.85로 상향)
        
        # 숏 포지션에서의 불리시 다이버전스 감지
        elif position_side == 'short':
            # 더 정교한 다이버전스 패턴 - 최소 2개의 저점 포인트 필요
            # 가격 저점 찾기
            price_troughs = []
            for i in range(1, len(recent_df) - 1):
                if recent_df['close'].iloc[i] < recent_df['close'].iloc[i-1] and recent_df['close'].iloc[i] < recent_df['close'].iloc[i+1]:
                    price_troughs.append((i, recent_df['close'].iloc[i]))
            
            # RSI 저점 찾기
            rsi_troughs = []
            for i in range(1, len(recent_df) - 1):
                if recent_df['rsi'].iloc[i] < recent_df['rsi'].iloc[i-1] and recent_df['rsi'].iloc[i] < recent_df['rsi'].iloc[i+1]:
                    rsi_troughs.append((i, recent_df['rsi'].iloc[i]))
            
            # 유효한 저점이 최소 2개 있는지 확인
            if len(price_troughs) >= 2 and len(rsi_troughs) >= 2:
                # 최근 두 개의 가격 저점과 RSI 저점 비교
                price_trough1, price_trough2 = price_troughs[-2:]
                rsi_trough1, rsi_trough2 = rsi_troughs[-2:]
                
                # 비트코인 시장에 맞게 기준 조정 (0.997 → 0.998, 1.03 → 1.025)
                # 가격은 더 낮은 저점을 만들고 RSI는 더 높은 저점을 만드는지 확인 (명확한 다이버전스)
                if (price_trough2[1] < price_trough1[1] * 0.998) and (rsi_trough2[1] > rsi_trough1[1] * 1.025):
                    exit_signals.append("숏 포지션에서 명확한 RSI 불리시 다이버전스 감지 (가격은 더 낮은 저점, RSI는 더 높은 저점)")
                    exit_signal_weights.append(0.85)  # 높은 가중치 (0.8→0.85로 상향)
            
            # MACD 다이버전스 - 더 강화된 조건
            if 'macd' in recent_df.columns:
                # MACD 저점 찾기
                macd_troughs = []
                for i in range(1, len(recent_df) - 1):
                    if recent_df['macd'].iloc[i] < recent_df['macd'].iloc[i-1] and recent_df['macd'].iloc[i] < recent_df['macd'].iloc[i+1]:
                        macd_troughs.append((i, recent_df['macd'].iloc[i]))
                
                # 유효한 저점이 최소 2개 있는지 확인
                if len(price_troughs) >= 2 and len(macd_troughs) >= 2:
                    # 최근 두 개의 가격 저점과 MACD 저점 비교
                    price_trough1, price_trough2 = price_troughs[-2:]
                    macd_trough1, macd_trough2 = macd_troughs[-2:]
                    
                    # 비트코인 시장에 맞게 기준 조정 (0.997 → 0.998, 1.03 → 1.025)
                    # 가격은 더 낮은 저점을 만들고 MACD는 더 높은 저점을 만드는지 확인 (명확한 다이버전스)
                    if (price_trough2[1] < price_trough1[1] * 0.998) and (macd_trough2[1] > macd_trough1[1] * 1.025):
                        exit_signals.append("숏 포지션에서 명확한 MACD 불리시 다이버전스 감지 (가격은 더 낮은 저점, MACD는 더 높은 저점)")
                        exit_signal_weights.append(0.85)  # 높은 가중치 (0.8→0.85로 상향)
    except Exception as e:
        logger.error(f"다이버전스 확인 중 오류: {e}")
    
    # 4. 트렌드 전환 및 지지/저항 레벨 돌파 확인 (더 엄격한 기준)
    try:
        latest = df_5min.iloc[-1]
        previous = df_5min.iloc[-2]
        
        # A. 이동평균선 교차 확인 (강화: 단순 교차가 아닌 명확한 교차)
        if 'ema_12' in df_5min.columns and 'sma_20' in df_5min.columns:
            # Long position - EMA가 SMA 아래로 교차 (with confirmation)
            if position_side == 'long':
                # 최근 5개 캔들 체크 (5→4로 감소, 비트코인의 빠른 움직임 고려)
                cross_below_count = 0
                for i in range(min(4, len(df_5min))):
                    idx = len(df_5min) - 1 - i
                    if df_5min['ema_12'].iloc[idx] < df_5min['sma_20'].iloc[idx]:
                        cross_below_count += 1
                
                # 최소 3개 이상의 캔들에서 EMA가 SMA 아래에 있으면 명확한 교차로 간주 (3→2로 감소)
                if cross_below_count >= 2:
                    exit_signals.append(f"EMA12가 SMA20 아래로 교차 확인됨 ({cross_below_count} 캔들)")
                    exit_signal_weights.append(0.75)  # 중간-높은 가중치 (0.7→0.75로 상향)
            
            # Short position - EMA가 SMA 위로 교차 (with confirmation)
            elif position_side == 'short':
                # 최근 5개 캔들 체크 (5→4로 감소, 비트코인의 빠른 움직임 고려)
                cross_above_count = 0
                for i in range(min(4, len(df_5min))):
                    idx = len(df_5min) - 1 - i
                    if df_5min['ema_12'].iloc[idx] > df_5min['sma_20'].iloc[idx]:
                        cross_above_count += 1
                
                # 최소 3개 이상의 캔들에서 EMA가 SMA 위에 있으면 명확한 교차로 간주 (3→2로 감소)
                if cross_above_count >= 2:
                    exit_signals.append(f"EMA12가 SMA20 위로 교차 확인됨 ({cross_above_count} 캔들)")
                    exit_signal_weights.append(0.75)  # 중간-높은 가중치 (0.7→0.75로 상향)
        
        # B. 주요 지지/저항 레벨 돌파 확인 (볼린저 밴드 + 피보나치 레벨 등)
        # Long position - 주요 지지선 하향 돌파
        if position_side == 'long' and 'bb_bbl' in latest:
            # 비트코인의 빠른 움직임 고려 (0.998 → 0.999로 완화)
            if latest['close'] < latest['bb_bbl'] * 0.999:
                exit_signals.append("롱 포지션에서 가격이 하단 볼린저 밴드 아래로 크게 이탈")
                exit_signal_weights.append(0.95)  # 매우 높은 가중치 (0.9→0.95로 상향)
        
        # Short position - 주요 저항선 상향 돌파
        elif position_side == 'short' and 'bb_bbh' in latest:
            # 비트코인의 빠른 움직임 고려 (1.002 → 1.001로 완화)
            if latest['close'] > latest['bb_bbh'] * 1.001:
                exit_signals.append("숏 포지션에서 가격이 상단 볼린저 밴드 위로 크게 이탈")
                exit_signal_weights.append(0.95)  # 매우 높은 가중치 (0.9→0.95로 상향)
        
        # C. 캔들 패턴 분석 - 강력한 반전 캔들 형성
        # 최근 3개 캔들 분석
        last_3_candles = df_5min.iloc[-3:].copy()
        
        # Long position - 베어리시 반전 캔들
        if position_side == 'long':
            # 비트코인의 높은 변동성 고려 (0.7 → 0.65로 완화)
            # 강한 베어리시 캔들 확인 (몸통이 전체 범위의 65% 이상)
            latest_body_ratio = abs(latest['close'] - latest['open']) / (latest['high'] - latest['low'])
            latest_is_bearish = latest['close'] < latest['open']
            
            if latest_is_bearish and latest_body_ratio > 0.65:
                # 이전 캔들이 불리시였는지 확인 (추세 전환 확인)
                prev_is_bullish = previous['close'] > previous['open']
                
                if prev_is_bullish:
                    exit_signals.append("롱 포지션에서 불리시 캔들 이후 강한 베어리시 반전 캔들 형성")
                    exit_signal_weights.append(0.75)  # 중간-높은 가중치 (0.7→0.75로 상향)
        
        # Short position - 불리시 반전 캔들
        elif position_side == 'short':
            # 비트코인의 높은 변동성 고려 (0.7 → 0.65로 완화)
            # 강한 불리시 캔들 확인 (몸통이 전체 범위의 65% 이상)
            latest_body_ratio = abs(latest['close'] - latest['open']) / (latest['high'] - latest['low'])
            latest_is_bullish = latest['close'] > latest['open']
            
            if latest_is_bullish and latest_body_ratio > 0.65:
                # 이전 캔들이 베어리시였는지 확인 (추세 전환 확인)
                prev_is_bearish = previous['close'] < previous['open']
                
                if prev_is_bearish:
                    exit_signals.append("숏 포지션에서 베어리시 캔들 이후 강한 불리시 반전 캔들 형성")
                    exit_signal_weights.append(0.75)  # 중간-높은 가중치 (0.7→0.75로 상향)
    except Exception as e:
        logger.error(f"트렌드 반전 및 지지/저항 레벨 확인 중 오류: {e}")
    
    # 5. 볼륨 프로필 분석 - 볼륨 급증 확인
    try:
        if 'volume' in df_5min.columns:
            recent_volume = df_5min['volume'].iloc[-1]
            avg_volume = df_5min['volume'].iloc[-10:].mean()
            
            # 비트코인의 변동성 고려 (3배 → 2.8배로 완화)
            # 볼륨이 평균의 2.8배 이상이고 캔들 방향이 포지션과 반대인 경우
            if recent_volume > avg_volume * 2.8:
                if (position_side == 'long' and latest['close'] < latest['open']) or \
                   (position_side == 'short' and latest['close'] > latest['open']):
                    exit_signals.append(f"포지션 방향과 반대되는 매우 높은 볼륨 스파이크 ({recent_volume/avg_volume:.1f}배)")
                    exit_signal_weights.append(0.85)  # 높은 가중치 (0.8→0.85로 상향)
    except Exception as e:
        logger.error(f"볼륨 프로필 확인 중 오류: {e}")
    
    # 6. 변동성 확인 - ATR 급증
    try:
        if 'atr' in df_5min.columns:
            recent_atr = df_5min['atr'].iloc[-1]
            avg_atr = df_5min['atr'].iloc[-20:].mean()
            
            # 비트코인의 급격한 변동성 고려 (2.5배 → 2.2배로 완화)
            # ATR이 평균의 2.2배 이상인 경우 (변동성 급증)
            if recent_atr > avg_atr * 2.2:
                exit_signals.append(f"극단적인 변동성 스파이크 감지 (ATR {recent_atr/avg_atr:.1f}배)")
                exit_signal_weights.append(0.75)  # 중간-높은 가중치 (0.7→0.75로 상향)
    except Exception as e:
        logger.error(f"변동성 확인 중 오류: {e}")
    
    # 7. 극단적인 과매수/과매도 확인 (RSI)
    try:
        if 'rsi' in df_5min.columns:
            rsi_value = df_5min['rsi'].iloc[-1]
            
            # 비트코인의 극단적 움직임 고려 (조건 완화)
            # Long position - RSI 과매도 (20→22로 완화)
            if position_side == 'long' and rsi_value <= 22:
                # 추가 확인: 이전 캔들들도 낮은 RSI인지
                # 비트코인의 빠른 움직임 고려 (25→28로 완화)
                low_rsi_count = sum(1 for rsi in df_5min['rsi'].iloc[-5:] if rsi <= 28)
                
                # 비트코인의 빠른 움직임 고려 (3→2로 완화)
                if low_rsi_count >= 2:  # 최소 2개 캔들에서 낮은 RSI 확인
                    exit_signals.append(f"RSI 극단적 과매도 상태 ({rsi_value:.1f}), {low_rsi_count}개 캔들 지속")
                    exit_signal_weights.append(0.85)  # 높은 가중치 (0.8→0.85로 상향)
            
            # Short position - RSI 과매수 (80→78로 완화)
            elif position_side == 'short' and rsi_value >= 78:
                # 추가 확인: 이전 캔들들도 높은 RSI인지
                # 비트코인의 빠른 움직임 고려 (75→72로 완화)
                high_rsi_count = sum(1 for rsi in df_5min['rsi'].iloc[-5:] if rsi >= 72)
                
                # 비트코인의 빠른 움직임 고려 (3→2로 완화)
                if high_rsi_count >= 2:  # 최소 2개 캔들에서 높은 RSI 확인
                    exit_signals.append(f"RSI 극단적 과매수 상태 ({rsi_value:.1f}), {high_rsi_count}개 캔들 지속")
                    exit_signal_weights.append(0.85)  # 높은 가중치 (0.8→0.85로 상향)
    except Exception as e:
        logger.error(f"RSI 극단 확인 중 오류: {e}")
    
    # 8. 멀티타임프레임 분석 - 상위 타임프레임 반전 신호 확인 (고급 분석)
    try:
        if 'hourly_reversal' in signals_data:
            if position_side == 'long' and signals_data['hourly_reversal'] == 'bearish':
                # 추가: 1시간 차트에서 명확한 반전 패턴 확인
                hourly_confirmation = signals_data.get('hourly_confirmation', False)
                
                if hourly_confirmation:
                    exit_signals.append("1시간 차트에서 패턴 확인된 베어리시 반전")
                    exit_signal_weights.append(0.95)  # 매우 높은 가중치 (0.9→0.95로 상향)
                else:
                    exit_signals.append("1시간 차트에서 베어리시 반전 신호")
                    exit_signal_weights.append(0.85)  # 높은 가중치 (0.8→0.85로 상향)
            elif position_side == 'short' and signals_data['hourly_reversal'] == 'bullish':
                # 추가: 1시간 차트에서 명확한 반전 패턴 확인
                hourly_confirmation = signals_data.get('hourly_confirmation', False)
                
                if hourly_confirmation:
                    exit_signals.append("1시간 차트에서 패턴 확인된 불리시 반전")
                    exit_signal_weights.append(0.95)  # 매우 높은 가중치 (0.9→0.95로 상향)
                else:
                    exit_signals.append("1시간 차트에서 불리시 반전 신호")
                    exit_signal_weights.append(0.85)  # 높은 가중치 (0.8→0.85로 상향)
    except Exception as e:
        logger.error(f"1시간 반전 확인 중 오류: {e}")
    
    # 9. 새로 추가: 패턴 연속성 확인 - 여러 지표의 일관된 신호 분석
    try:
        # 신호의 일관성 수준 계산
        consistent_bearish_signals = 0
        consistent_bullish_signals = 0
        
        # A. RSI 방향
        if 'rsi' in df_5min.columns:
            # 비트코인의 급격한 움직임 고려 (-2→-1.8로 완화)
            rsi_direction = df_5min['rsi'].iloc[-1] - df_5min['rsi'].iloc[-2]
            if rsi_direction < -1.8:  # RSI가 명확하게 하락 중
                consistent_bearish_signals += 1
            # 비트코인의 급격한 움직임 고려 (2→1.8로 완화)
            elif rsi_direction > 1.8:  # RSI가 명확하게 상승 중
                consistent_bullish_signals += 1
        
        # B. MACD 방향
        if 'macd' in df_5min.columns and 'macd_signal' in df_5min.columns:
            # 비트코인의 급격한 움직임 고려 (-0.2→-0.18로 완화)
            macd_direction = df_5min['macd'].iloc[-1] - df_5min['macd'].iloc[-2]
            macd_signal_cross = (df_5min['macd'].iloc[-2] > df_5min['macd_signal'].iloc[-2] and 
                                df_5min['macd'].iloc[-1] < df_5min['macd_signal'].iloc[-1])  # 베어리시 크로스
            macd_signal_cross_bullish = (df_5min['macd'].iloc[-2] < df_5min['macd_signal'].iloc[-2] and 
                                        df_5min['macd'].iloc[-1] > df_5min['macd_signal'].iloc[-1])  # 불리시 크로스
            
            if macd_direction < -0.18 or macd_signal_cross:  # MACD가 명확하게 하락 중이거나 베어리시 크로스
                consistent_bearish_signals += 1
            # 비트코인의 급격한 움직임 고려 (0.2→0.18로 완화)
            elif macd_direction > 0.18 or macd_signal_cross_bullish:  # MACD가 명확하게 상승 중이거나 불리시 크로스
                consistent_bullish_signals += 1
        
        # C. 볼린저 밴드 위치
        if 'bb_bbm' in df_5min.columns:
            price_to_bbm = latest['close'] - latest['bb_bbm']
            # 비트코인의 빠른 움직임 고려 (0.3→0.27로 완화)
            if price_to_bbm < 0 and abs(price_to_bbm) > (latest['bb_bbh'] - latest['bb_bbl']) * 0.27:
                # 가격이 중앙선보다 밴드 폭의 27% 이상 아래
                consistent_bearish_signals += 1
            # 비트코인의 빠른 움직임 고려 (0.3→0.27로 완화)
            elif price_to_bbm > 0 and abs(price_to_bbm) > (latest['bb_bbh'] - latest['bb_bbl']) * 0.27:
                # 가격이 중앙선보다 밴드 폭의 27% 이상 위
                consistent_bullish_signals += 1
        
        # D. ADX & DI 방향 (비트코인 시장에 맞게 ADX 임계값 25→23으로 완화)
        if 'adx' in df_5min.columns and 'di_plus' in df_5min.columns and 'di_minus' in df_5min.columns:
            # ADX가 23 이상이고, -DI가 +DI보다 높은 경우 (강한 하락 트렌드)
            if df_5min['adx'].iloc[-1] > 23 and df_5min['di_minus'].iloc[-1] > df_5min['di_plus'].iloc[-1]:
                consistent_bearish_signals += 1
            # ADX가 23 이상이고, +DI가 -DI보다 높은 경우 (강한 상승 트렌드)
            elif df_5min['adx'].iloc[-1] > 23 and df_5min['di_plus'].iloc[-1] > df_5min['di_minus'].iloc[-1]:
                consistent_bullish_signals += 1
        
        # E. 볼륨 기반 지표
        if 'obv' in df_5min.columns:
            # 비트코인의 빠른 움직임 고려 (3→2로 완화)
            obv_direction = df_5min['obv'].iloc[-1] - df_5min['obv'].iloc[-2]
            if obv_direction < 0:  # OBV 하락 (매도 압력)
                consistent_bearish_signals += 1
            elif obv_direction > 0:  # OBV 상승 (매수 압력)
                consistent_bullish_signals += 1
        
        # 일관된 신호 분석 결과를 바탕으로 출구 신호 평가
        # 비트코인의 빠른 움직임 고려 (3→2로 완화)
        if position_side == 'long' and consistent_bearish_signals >= 2:
            exit_signals.append(f"여러 지표에서 {consistent_bearish_signals}개의 일관된 베어리시 신호 감지")
            # 신호 수에 따라 가중치 증가
            # 가중치 상향 (0.7→0.75 기본, 단계 0.05→0.07로 증가)
            exit_signal_weights.append(min(0.75 + (consistent_bearish_signals - 2) * 0.07, 0.95))
        elif position_side == 'short' and consistent_bullish_signals >= 2:
            exit_signals.append(f"여러 지표에서 {consistent_bullish_signals}개의 일관된 불리시 신호 감지")
            # 신호 수에 따라 가중치 증가
            # 가중치 상향 (0.7→0.75 기본, 단계 0.05→0.07로 증가)
            exit_signal_weights.append(min(0.75 + (consistent_bullish_signals - 2) * 0.07, 0.95))
    except Exception as e:
        logger.error(f"패턴 일관성 확인 중 오류: {e}")
    
    # 신호 가중치 합산하여 최종 결정
    exit_score = sum(exit_signal_weights)
    
    # 비트코인의 빠른 움직임을 고려하여 출구 임계값 조정 (1.7→1.5로 완화)
    should_exit = exit_score >= 1.5
    
    # 출구 신호가 있으면 로깅
    if exit_signals:
        logger.info(f"출구 신호 감지: {exit_signals} - 가중치: {exit_signal_weights}, 총점: {exit_score}")
    
    # 결과 반환
    result = {
        "should_exit": should_exit,
        "exit_signals": exit_signals,
        "exit_score": exit_score,
        "exit_signal_weights": exit_signal_weights
    }
    logger.info(f"출구 평가 결과: {result}")
    return result


### 메인 AI 트레이딩 로직
def ai_trading():
    """Main AI trading function with pre-calculated trend strength and exit signals"""
    
    # Chart signal processor initialization
    chart_processor = ChartSignalProcessor()
    
    ### Data Collection
    # 7. Capture trading view chart with Selenium
    chart_image = None
    signals_analysis = None
    try:
        # Try login with cookies first
        login_with_cookies()
        
        # Capture chart with retry logic
        chart_image, signals_analysis, saved_file_path = capture_tradingview_chart_with_retry(
            chart_processor=chart_processor, 
            save_image=False, 
            debug=False,
            max_retries=3,
            page_load_timeout=40
        )
        
        if chart_image:
            logger.info("TradingView screenshot capture and analysis completed")
        else:
            logger.error("Screenshot capture failed after maximum retries")
            
    except Exception as e:
        logger.error(f"Serious error during chart capture process: {e}", exc_info=True)
    finally:
        # Always clean up driver
        WebDriverManager.quit()

    # 1. Check current investment status
    # Query USDT balance
    balance = trader.exchange.fetch_balance()
    usdt_balance = balance['USDT']
    free_usdt = usdt_balance['free']      # Available balance
    used_usdt = usdt_balance['used']      # Balance in orders
    total_usdt = usdt_balance['total']    # Total balance
    filtered_balances = [used_usdt, free_usdt]

    # Query position information
    positions = trader.exchange.fetch_positions([trader.symbol])
    btc_avg_buy_price = 0  # Default value
    position_side = None
    position_size = 0
    unrealized_pnl = None

    for position in positions:
        if float(position.get('contracts', 0) or 0) != 0:
            btc_avg_buy_price = float(position['entryPrice'])
            position_side = position['side']  # 'long' or 'short'
            position_size = float(position['notional']) # contracts * entryPrice = In USDT
            unrealized_pnl = float(position.get('percentage', 0))  # Profit/loss (%)
            break

    # 2. Get orderbook data
    orderbook = trader.exchange.fetch_order_book('BTC/USDT')
    modified_orderbook = modify_orderbook(orderbook)

    # 3. Get chart data and add technical indicators
    # Binance exchange BTC/USDT Perpetual current price
    ticker = trader.exchange.fetch_ticker(trader.symbol)
    current_price = ticker['last']

    # Query Binance 5-minute candles
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
    
    # Select only the last 60 data points
    df_5min = df_5min.tail(60)

    # Query Binance 1-hour candles
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

    # Select only the last 24 data points
    df_hourly = df_hourly.tail(24)

    # Query Binance 4-hour candles
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

    # Select only the last 18 data points
    df_4h = df_4h.tail(18)

    # 4. Get Fear & Greed Index
    fear_greed_index = get_fear_and_greed_index()

    # 5. Get news headlines
    news_headlines = get_bitcoin_news()

    # 6. Get YouTube transcript data
    try:
        f2 = open("strategy2.txt", "r", encoding="utf-8")
        youtube_transcript2 = f2.read()
        f2.close()
    except Exception as e:
        logger.error(f"Failed to read strategy file: {e}")
        youtube_transcript2 = ""
        
    ### Get chart signal data and trading signals text
    trading_signals_text = chart_processor.create_prompt_text()
    signals_data = chart_processor.generate_ai_prompt_data()
        
    ### PRE-CALCULATE Key Decision Points
        
    # 1. Assess trend strength (TREND STRENGTH CHECK)
    try:
        trend_strength_result = assess_trend_strength(df_5min, df_hourly, current_price, df_4h)
        if isinstance(trend_strength_result, dict):
            long_trend_strong = trend_strength_result.get("long_trend_strong", False)
            short_trend_strong = trend_strength_result.get("short_trend_strong", False)
        else:
            logger.error("trend_strength_result is not a dictionary")
            long_trend_strong = False
            short_trend_strong = False
    except Exception as e:
        logger.error(f"Error during trend strength assessment: {e}")
        long_trend_strong = False
        short_trend_strong = False

    # 2. Assess exit signals
    try:
        exit_assessment = assess_exit_signals(df_5min, signals_data, position_side)
        if isinstance(exit_assessment, dict):
            should_exit = exit_assessment.get("should_exit", False)
            exit_signals_list = exit_assessment.get("exit_signals", [])
        else:
            logger.error("exit_assessment is not a dictionary")
            should_exit = False
            exit_signals_list = []
    except Exception as e:
        logger.error(f"Error during exit signals assessment: {e}")
        should_exit = False
        exit_signals_list = []
    
    
    # 3. Check market overheating conditions
    market_overheating = {
        "long_overheated": False,
        "short_overheated": False,
        "reasons": []
    }
    
    try:
        # Get latest candle data
        latest = df_5min.iloc[-1]
        
        # Long overheating checks
        if latest['close'] >= latest['bb_bbh']:
            market_overheating["long_overheated"] = True
            market_overheating["reasons"].append("Price at/above upper Bollinger Band")
            
        if latest['rsi'] > 70:
            market_overheating["long_overheated"] = True
            market_overheating["reasons"].append("RSI above 70")
        
        # Check if price moved more than 0.8% in last 5 candles without pullback
        recent_5 = df_5min.iloc[-5:]
        price_5_candles_ago = recent_5.iloc[0]['close']
        price_percent_change = (latest['close'] - price_5_candles_ago) / price_5_candles_ago * 100
        
        if price_percent_change > 0.8 and all(recent_5.iloc[i]['close'] > recent_5.iloc[i-1]['close'] for i in range(1, 5)):
            market_overheating["long_overheated"] = True
            market_overheating["reasons"].append(f"Price moved up {price_percent_change:.2f}% in last 5 candles without pullback")
            
        # Short overheating checks
        if latest['close'] <= latest['bb_bbl']:
            market_overheating["short_overheated"] = True
            market_overheating["reasons"].append("Price at/below lower Bollinger Band")
            
        if latest['rsi'] < 30:
            market_overheating["short_overheated"] = True
            market_overheating["reasons"].append("RSI below 30")
            
        if price_percent_change < -0.8 and all(recent_5.iloc[i]['close'] < recent_5.iloc[i-1]['close'] for i in range(1, 5)):
            market_overheating["short_overheated"] = True
            market_overheating["reasons"].append(f"Price moved down {abs(price_percent_change):.2f}% in last 5 candles without pullback")
    
    except Exception as e:
        logger.error(f"Error assessing market overheating: {e}")

    # 추가: 진입 조건 검증 함수
    # 수정: Volume Oscillator 조건 완화
    def verify_entry_conditions(signals_data, trend_strength_result, decision, current_position_side, df_5min, entry_price):
        """
        진입 조건 검증 함수 - 수정된 버전
        
        Args:
            signals_data: 트레이딩 신호 데이터
            trend_strength_result: 트렌드 강도 분석 결과
            decision: AI 결정 ('buy', 'sell', 'hold')
            current_position_side: 현재 포지션 방향 ('long', 'short', None)
            df_5min: 5분 캔들 데이터프레임
            entry_price: 현재 가격
        
        Returns:
            bool: 진입 조건 충족 여부
        """
        # 롱 포지션 진입 조건 검증
        if decision == "buy" and current_position_side is None:
            # 신호 유효성 확인 (캔들 수 20으로 확장)
            blackflag_valid = signals_data.get("BlackFlag_Signal") == "Buy" and signals_data.get("BlackFlag_CandlesAgo", 999) <= 20
            utbot_valid = signals_data.get("UTBot_Signal") == "Buy" and signals_data.get("UTBot_CandlesAgo", 999) <= 20
            
            # 가격 변화 확인 - 신호 시점 가격과 현재 가격 비교
            price_change_pct = 0
            signal_price = None
            
            # 첫 번째 신호 찾기
            first_signal_candles_ago = min(
                signals_data.get("BlackFlag_CandlesAgo", 999) if signals_data.get("BlackFlag_Signal") == "Buy" else 999,
                signals_data.get("UTBot_CandlesAgo", 999) if signals_data.get("UTBot_Signal") == "Buy" else 999
            )
            
            # 유효한 첫 신호가 있으면 가격 변화 계산
            if first_signal_candles_ago < 999 and first_signal_candles_ago < len(df_5min):
                idx = -1 - first_signal_candles_ago  # 신호가 발생한 캔들의 인덱스
                signal_price = df_5min['close'].iloc[idx]
                price_change_pct = (entry_price - signal_price) / signal_price * 100
            
            # 수정: Volume Oscillator 조건 완화 - 강한 신호가 있을 경우 음수도 허용
            strong_signals = blackflag_valid and utbot_valid and trend_strength_result.get("long_trend_strong", False)
            volume_valid = signals_data.get("VolumeOsc_Current", -999) > 0 or (
                strong_signals and signals_data.get("VolumeOsc_Current", -999) > -15
            )
            
            trend_valid = trend_strength_result.get("long_trend_strong", False)
            
            # 가격 변화 조건 (1% 이상 상승하면 진입하지 않음)
            price_valid = price_change_pct < 1.0
            
            # 추가 로깅
            logger.info(f"롱 진입 조건 검증: BlackFlag={blackflag_valid}, UTBot={utbot_valid}, Volume={volume_valid}, Trend={trend_valid}, PriceChange={price_change_pct:.2f}%, PriceValid={price_valid}")
            
            # 모든 조건이 충족되는지 확인
            all_conditions_met = blackflag_valid and utbot_valid and volume_valid and trend_valid and price_valid
            
            if not all_conditions_met:
                logger.warning(f"롱 진입 조건 검증 실패: BlackFlag={blackflag_valid}, UTBot={utbot_valid}, Volume={volume_valid}, Trend={trend_valid}, PriceChange={price_change_pct:.2f}%, PriceValid={price_valid}")
            
            return all_conditions_met
        
        # 숏 포지션 진입 조건 검증
        elif decision == "sell" and current_position_side is None:
            # 신호 유효성 확인 (캔들 수 20으로 확장)
            blackflag_valid = signals_data.get("BlackFlag_Signal") == "Sell" and signals_data.get("BlackFlag_CandlesAgo", 999) <= 20
            utbot_valid = signals_data.get("UTBot_Signal") == "Sell" and signals_data.get("UTBot_CandlesAgo", 999) <= 20
            
            # 가격 변화 확인 - 신호 시점 가격과 현재 가격 비교
            price_change_pct = 0
            signal_price = None
            
            # 첫 번째 신호 찾기
            first_signal_candles_ago = min(
                signals_data.get("BlackFlag_CandlesAgo", 999) if signals_data.get("BlackFlag_Signal") == "Sell" else 999,
                signals_data.get("UTBot_CandlesAgo", 999) if signals_data.get("UTBot_Signal") == "Sell" else 999
            )
            
            # 유효한 첫 신호가 있으면 가격 변화 계산
            if first_signal_candles_ago < 999 and first_signal_candles_ago < len(df_5min):
                idx = -1 - first_signal_candles_ago  # 신호가 발생한 캔들의 인덱스
                signal_price = df_5min['close'].iloc[idx]
                price_change_pct = (signal_price - entry_price) / signal_price * 100
            
            # 수정: Volume Oscillator 조건 완화 - 강한 신호가 있을 경우 음수도 허용
            strong_signals = blackflag_valid and utbot_valid and trend_strength_result.get("short_trend_strong", False)
            volume_valid = signals_data.get("VolumeOsc_Current", -999) > 0 or (
                strong_signals and signals_data.get("VolumeOsc_Current", -999) > -15
            )
            
            trend_valid = trend_strength_result.get("short_trend_strong", False)
            
            # 가격 변화 조건 (1% 이상 하락하면 진입하지 않음)
            price_valid = price_change_pct < 1.0
            
            # 추가 로깅
            logger.info(f"숏 진입 조건 검증: BlackFlag={blackflag_valid}, UTBot={utbot_valid}, Volume={volume_valid}, Trend={trend_valid}, PriceChange={price_change_pct:.2f}%, PriceValid={price_valid}")
            
            # 모든 조건이 충족되는지 확인
            all_conditions_met = blackflag_valid and utbot_valid and volume_valid and trend_valid and price_valid
            
            if not all_conditions_met:
                logger.warning(f"숏 진입 조건 검증 실패: BlackFlag={blackflag_valid}, UTBot={utbot_valid}, Volume={volume_valid}, Trend={trend_valid}, PriceChange={price_change_pct:.2f}%, PriceValid={price_valid}")
            
            return all_conditions_met
        
        # 포지션 청산(exit) 조건은 이미 should_exit 변수로 검증됨
        elif (decision == "sell" and current_position_side == "long") or (decision == "buy" and current_position_side == "short"):
            return True
        
        # 다른 모든 경우 (e.g., "hold")
        return True   
            
        

    ### AI Decision Making
    try:
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        if not client.api_key:
            logger.error("OpenAI API key is missing or invalid.")
            return None
            
        # Database connection
        conn = get_db_connection()
        if not conn:
            logger.error("Database connection failed.")
            return None
            
        try:
            # Get recent trades
            recent_trades = get_recent_trades(conn)
            
            # Collect current market data
            current_market_data = {
                "Current Price": current_price,
                "fear_greed_index": fear_greed_index,
                "news_headlines": news_headlines,
                "orderbook": modified_orderbook,
                "5min_ohlcv": df_5min.to_dict(),
                "hourly_ohlcv": df_hourly.to_dict(),
                "4hour_ohlcv": df_4h.to_dict()
            }
            
            # Generate reflection and improvement content
            reflection = generate_reflection(recent_trades, current_market_data)
            
            # Format pre-calculated data for the AI prompt
            blackflag_signal = signals_data.get("BlackFlag_Signal", "None") 
            blackflag_candles_ago = signals_data.get("BlackFlag_CandlesAgo", "None")
            utbot_signal = signals_data.get("UTBot_Signal", "None")
            utbot_candles_ago = signals_data.get("UTBot_CandlesAgo", "None")
            volume_osc_current = signals_data.get("VolumeOsc_Current", "None")
            stop_loss_price = signals_data.get("StopLoss_Price", "None")
            
            # Call OpenAI API with the updated prompt format
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                    "role": "system",
                    "content": f"""
# Bitcoin Futures Trading Strategy with Pre-calculated Indicators

You are a Bitcoin futures day trader on the 5-minute timeframe with leveraged positions. Your strategy uses pre-calculated core indicators and trend strength assessments. Capital preservation is paramount.

## 1. CRITICAL: POSITION MANAGEMENT RULES ⚠️

**POSITION MANAGEMENT RULES - READ FIRST**

Before making ANY trading decision:

1. **ALWAYS CHECK** current position in the Portfolio section:
   - "Current Position Side" will be "long", "short", or "none"

2. **For EXIT decisions:**
   - If current position is LONG → Must use **"sell"** command to exit
   - If current position is SHORT → Must use **"buy"** command to exit
   - If current position is NONE → No exit possible (consider entries only)

3. **For ENTRY decisions:**
   - To open LONG position → Use **"buy"** command
   - To open SHORT position → Use **"sell"** command

⚠️ Using the wrong command will INCREASE position risk instead of reducing it.

## 2. Market Data and Portfolio Information

The data below must be considered in your analysis.

**[Market Data]**
- Current Price: {current_price:.2f} USDT

**Technical Indicators (5-min, 1-hour, 4-hour timeframes)**

→ **5-Minute Chart Data:**
- RSI(14): {df_5min['rsi'].iloc[-1]:.2f}
- MACD: {df_5min['macd'].iloc[-1]:.2f}
- Bollinger Bands (20):
  * Middle: {df_5min['bb_bbm'].iloc[-1]:.2f}
  * Upper: {df_5min['bb_bbh'].iloc[-1]:.2f}
  * Lower: {df_5min['bb_bbl'].iloc[-1]:.2f}
- ATR: {df_5min['atr'].iloc[-1]:.2f}
- ADX: {df_5min['adx'].iloc[-1]:.2f}
- DI+: {df_5min['di_plus'].iloc[-1]:.2f}
- DI-: {df_5min['di_minus'].iloc[-1]:.2f}
- CMF: {df_5min['cmf'].iloc[-1]:.2f}

→ **1-Hour Chart Data:**
- RSI(14): {df_hourly['rsi'].iloc[-1]:.2f}
- MACD: {df_hourly['macd'].iloc[-1]:.2f}
- ADX: {df_hourly['adx'].iloc[-1]:.2f}
- DI+: {df_hourly['di_plus'].iloc[-1]:.2f}
- DI-: {df_hourly['di_minus'].iloc[-1]:.2f}
- CMF: {df_hourly['cmf'].iloc[-1]:.2f}

→ **4-Hour Chart Data:**
- RSI(14): {df_4h['rsi'].iloc[-1]:.2f}
- MACD: {df_4h['macd'].iloc[-1]:.2f}
- ADX: {df_4h['adx'].iloc[-1]:.2f}
- DI+: {df_4h['di_plus'].iloc[-1]:.2f}
- DI-: {df_4h['di_minus'].iloc[-1]:.2f}
- CMF: {df_4h['cmf'].iloc[-1]:.2f}

**[Portfolio]**
- Total USDT Assets: {total_usdt:.1f}
- Free USDT Balance: {free_usdt:.1f}
- Used USDT Holdings: {used_usdt:.1f}
- BTC Average Purchase Price: {btc_avg_buy_price:.1f} USDT
- Current Position Side: {position_side} ← "long", "short", or "none"
- Current Position PnL: {unrealized_pnl} % ← -100~100 or None(no position)

## 3. Pre-Calculated Indicators and Signals

**CORE INDICATORS STATUS (PRE-CALCULATED):**
- BlackFlag FTS Signal: {blackflag_signal} (Candles ago: {blackflag_candles_ago})
- UT Bot Signal: {utbot_signal} (Candles ago: {utbot_candles_ago})
- Volume Oscillator: {volume_osc_current}
- Stop Loss Price: {stop_loss_price}

**TREND STRENGTH ASSESSMENT (PRE-CALCULATED):**
- Long Trend Strength: {"STRONG" if long_trend_strong else "WEAK"}
- Short Trend Strength: {"STRONG" if short_trend_strong else "WEAK"}

**EXIT SIGNALS ASSESSMENT (PRE-CALCULATED):**
- Should Exit Current Position: {"YES" if should_exit else "NO"}
- Exit Signals Detected: {len(exit_signals_list)}

**MARKET OVERHEATING (PRE-CALCULATED):**
- Long Side Overheated: {"YES" if market_overheating["long_overheated"] else "NO"}
- Short Side Overheated: {"YES" if market_overheating["short_overheated"] else "NO"}

## 4. Decision Rules

For a valid PRIMARY entry, ALL of the following must be true:

**For Long Entry:**
1. **BlackFlag FTS:** Must show a BUY signal within the last 20 candles.
2. **UT Bot Alerts:** Must display a BUY alert within the last 20 candles.
3. **Volume Oscillator:** Should generally be POSITIVE, but can be moderately negative (-15 or higher) if other signals are strong and aligned.
4. **Trend Strength:** Must be STRONG (pre-calculated as {"STRONG" if long_trend_strong else "WEAK"}).

**For Short Entry:**
1. **BlackFlag FTS:** Must show a SELL signal within the last 20 candles.
2. **UT Bot Alerts:** Must display a SELL alert within the last 20 candles.
3. **Volume Oscillator:** Should generally be POSITIVE, but can be moderately negative (-15 or higher) if other signals are strong and aligned.
4. **Trend Strength:** Must be STRONG (pre-calculated as {"STRONG" if short_trend_strong else "WEAK"}).

**Exit Rules:**
1. If exit signals are detected (pre-calculated as {"YES" if should_exit else "NO"}), exit the current position immediately using the correct command (sell to exit long, buy to exit short).

**Position Sizing Rules:**
1. If the market is overheated in the direction of entry, reduce position size by 50%.
2. Standard position sizes based on signal strength:
   - **Strong Signal:** 100% of calculated size.
   - **Medium Signal:** 70% of calculated size. *(Increased from 60% to better capture movement.)*
   - **Weak Signal:** 40% of calculated size. *(Adjusted from 30% for improved exposure on less sure signals.)*

**Risk/Reward (PL Ratio) Guidelines (Bitcoin-Specific):**
- **Strong Signal & Low Volatility:** Use a PL ratio of **1.7**
- **Strong Signal & High Volatility:** Use a PL ratio of **1.3** (to secure quick profits at lower target prices)
- **Medium Signal:** Use a PL ratio of **1.5**
- **Weak Signal:** Use a PL ratio of **1.4**

**Additional Guidelines:**
- Always consider Bitcoin's rapid volatility alongside its long-term upward trend. This means while the market may be prone to swift moves, the overall bias can be bullish. Trade conservatively to preserve capital and adjust positions accordingly.

## 5. Response Format

Output a JSON object:

```json
{{
  "decision": "buy" or "sell" or "hold",
  "percentage": integer (0-100),
  "stop_loss_price": float,
  "pl_ratio": float (1.3-2.0),
  "reason": "Concise rationale referencing signals & data"
}}

decision: MUST FIRST CHECK CURRENT POSITION STATUS:

To exit a LONG position → Use "sell"
To exit a SHORT position → Use "buy"
To open a new LONG → Use "buy"
To open a new SHORT → Use "sell"
If there is no position and no valid entry signal → Use "hold"
percentage: Position size (0-100) based on the adjusted sizing rules.

stop_loss_price: As defined by the strategy (pre-calculated indicator).

pl_ratio: Based on the signal strength and market volatility, following the Bitcoin-specific guidelines above.

reason: Provide a clear explanation detailing which signals and data informed the decision.

## 6. Final Notes

When in doubt, preserve capital. Considering Bitcoin's rapid volatility paired with its long-term bullish trend, it is essential to balance aggressive entries with conservative management. "hold" is often the safest decision if the signals are not strongly aligned.

All key indicators have been pre-calculated for you. Focus on making a clear decision based on the provided data and always trade within your risk parameters.
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
                                Fear and Greed Index: {json.dumps(fear_greed_index)}
                                
                                Core indicators & Stop Loss Price: {trading_signals_text}
                                """
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

            # Validate AI's trading decision with Pydantic
            try:
                result = TradingDecision.model_validate_json(response.choices[0].message.content)
            except Exception as e:
                logger.error(f"Error parsing AI response: {e}")
                return

            # 여기에 추가: 진입 조건 검증
            # ai_trading 함수 내 verify_entry_conditions 호출 부분 변경
            if not verify_entry_conditions(signals_data, trend_strength_result, result.decision, position_side, df_5min, current_price):
                logger.warning(f"AI 결정 '{result.decision}'이 모든 진입 조건을 충족하지 않음. 'hold'로 변경됩니다.")
                original_decision = result.decision
                original_reason = result.reason
                result.decision = "hold"
                result.percentage = 0
                result.reason = f"Entry conditions not fully met for {original_decision} - HOLD for capital preservation. Original reason: {original_reason}"

            logger.info(f"### AI Decision: {result.decision.upper()} ###")
            logger.info(f"### Reason: {result.reason} ###")

            order_executed = False
            order_info = None  # Initialize variable

            try:
                # Get current price
                ticker = trader.exchange.fetch_ticker('BTC/USDT')
                current_btc_price = ticker['last']
                
                # Check account balance
                balance = trader.exchange.fetch_balance()
                total_balance = float(balance['USDT']['free'])
                
                # Calculate order amount (considering fees)
                # When position is active
                if position_side:
                    # If order direction is opposite to current position, calculate based on position size
                    if ((position_side == 'long' and result.decision == 'sell') or 
                        (position_side == 'short' and result.decision == 'buy')):
                            order_amount = position_size * (result.percentage / 100)
                    # If adding to existing position in same direction, calculate based on balance
                    else:
                        order_amount = total_balance * (result.percentage / 100) * 0.9996
                else:  # For new entries, calculate based on balance
                    order_amount = total_balance * (result.percentage / 100) * 0.9996
                
                if result.decision == "buy" and result.percentage > 0:
                    # Long position entry or short position exit
                    order_info = trader.market_order_with_tp_sl(
                        side='buy',
                        buy_amount=order_amount,
                        pl_ratio=result.pl_ratio,
                        sl_price=result.stop_loss_price
                    )
                    
                    if order_info != None:
                        logger.info(f"Buy order executed: Amount={order_amount}, P&L ratio={result.pl_ratio}, SL={result.stop_loss_price}")
                        order_executed = True
                        
                elif result.decision == "sell" and result.percentage > 0:
                    # Short position entry or long position exit
                    order_info = trader.market_order_with_tp_sl(
                        side='sell',
                        buy_amount=order_amount,
                        pl_ratio=result.pl_ratio,
                        sl_price=result.stop_loss_price
                    )
                    
                    if order_info != None:
                        logger.info(f"Sell order executed: Amount={order_amount}, P&L ratio={result.pl_ratio}, SL={result.stop_loss_price}")
                        order_executed = True
                        
            except Exception as e:
                logger.error(f"Error executing order: {str(e)}")
                
            # Update balance info after order (executed or not)
            time.sleep(1)  # Brief delay to allow API updates
            balance = trader.exchange.fetch_balance()
            usdt_balance = balance['USDT']
            free_usdt = usdt_balance['free']
            used_usdt = usdt_balance['used']
            total_usdt = usdt_balance['total']
            
            # Get current position info
            try:
                positions = trader.exchange.fetch_positions([trader.symbol])
                if positions and len(positions) > 0:
                    position = positions[0]
                    btc_avg_buy_price = float(position['entryPrice']) 
                    position_size = float(position['contracts'])
                else:
                    btc_avg_buy_price = 0
                    position_size = 0
            except Exception as e:
                logger.error(f"Error fetching position: {e}")
                btc_avg_buy_price = 0 
                position_size = 0
                
            # Get current BTC price
            ticker = trader.exchange.fetch_ticker('BTC/USDT')
            current_btc_price = ticker['last']

            # Record trade in database
            if order_executed and order_info != None:
                order_id = order_info['entry']['id']
                tp_order_id = order_info['tp']['id'] if order_info.get('tp') else None
                sl_order_id = order_info['sl']['id'] if order_info.get('sl') else None
                
                log_trade(conn, 'AI', order_id, result.decision, result.percentage, result.reason, 
                used_usdt, free_usdt, total_usdt, btc_avg_buy_price, current_btc_price, 
                reflection, tp_order_id, sl_order_id, signals_data)
                
                # Set up trailing stop loss monitoring if available
                if 'monitor_sl' in order_info:
                    # Clean up existing monitoring jobs
                    global sl_monitor_jobs
                    for job in sl_monitor_jobs[:]:
                        schedule.cancel_job(job)
                        sl_monitor_jobs.remove(job)
                        logger.info(f"Cancelled previous trailing SL monitoring job: {getattr(job, 'job_id', 'unknown')}")
                    
                    # Store monitor function
                    monitor_sl_func = order_info['monitor_sl']
                    
                    # Create unique job ID
                    job_id = f"sl_monitor_{order_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                    
                    def periodic_sl_monitoring(monitor_func, job_id=job_id):
                        try:
                            # Measure function execution time
                            start_time = time.time()
                            
                            new_sl_order = monitor_func()
                            
                            if new_sl_order:
                                logger.info(f"Trailing SL order updated: {new_sl_order}")
                            
                            # Log execution time
                            elapsed_time = time.time() - start_time
                            logger.debug(f"SL monitoring job completed in {elapsed_time:.2f} seconds")
                            
                            # Check resource usage
                            memory_percent = psutil.virtual_memory().percent
                            if memory_percent > 85:
                                logger.warning(f"High memory usage in SL monitoring: {memory_percent}%")
                                gc.collect()
                                
                        except Exception as e:
                            # Remove job if error occurs
                            logger.error(f"Error in SL monitoring: {e}")
                            for job in sl_monitor_jobs:
                                if job.job_id == job_id:
                                    schedule.cancel_job(job)
                                    sl_monitor_jobs.remove(job)
                                    break
                    
                    # Schedule monitoring job every minute
                    job = schedule.every(1).minutes.do(periodic_sl_monitoring, monitor_sl_func)
                    job.job_id = job_id
                    
                    # Add to global job list
                    sl_monitor_jobs.append(job)
                    logger.info(f"Created trailing SL monitoring job: {job_id}")          
                
            else:
                # If no trade was executed (hold or failed)
                log_trade(conn, 'AI', None, result.decision, 0, result.reason, 
                        used_usdt, free_usdt, total_usdt, btc_avg_buy_price, current_btc_price, 
                        reflection, None, None, signals_data)
        
        finally:
            if conn:
                conn.close()
    
    except Exception as e:
        logger.error(f"Error in AI trading function: {e}")
        # Clean up memory
        gc.collect()


def simple_disk_cleanup(logger=None):
    """
    EC2 환경에서 디스크 공간을 효과적으로 정리하는 간결한 함수
    """
    import os
    import glob
    import psutil
    import shutil
    from datetime import datetime, timedelta
    
    if logger is None:
        import logging
        logger = logging.getLogger()
    
    # 시작 전 디스크 사용량 확인
    initial_usage = psutil.disk_usage('/')
    logger.info(f"디스크 정리 시작 - 현재 사용량: {initial_usage.percent}%")
    
    deleted_count = 0
    deleted_size = 0
    
    # 1. 임시 이미지 파일 정리 (프로젝트 디렉토리)
    project_dir = os.getcwd()
    image_patterns = [
        os.path.join(project_dir, "temp_*.png"),
        os.path.join(project_dir, "chart_*.png"),
        os.path.join(project_dir, "debug_*.png")
    ]
    
    cutoff_time = datetime.now() - timedelta(hours=24)  # 24시간 이상 지난 파일
    
    for pattern in image_patterns:
        for file_path in glob.glob(pattern):
            try:
                if os.path.isfile(file_path) and datetime.fromtimestamp(os.path.getmtime(file_path)) < cutoff_time:
                    file_size = os.path.getsize(file_path)
                    os.remove(file_path)
                    deleted_count += 1
                    deleted_size += file_size
            except Exception as e:
                logger.error(f"파일 삭제 오류: {file_path}, {e}")
    
    # 2. 로그 파일 정리
    log_dir = os.path.join(project_dir, "logs")
    if os.path.exists(log_dir):
        log_files = sorted([
            os.path.join(log_dir, f) 
            for f in os.listdir(log_dir) 
            if f.endswith('.log')
        ])
        
        # 최신 5개 파일만 유지
        if len(log_files) > 5:
            for old_file in log_files[:-5]:
                try:
                    file_size = os.path.getsize(old_file)
                    os.remove(old_file)
                    deleted_count += 1
                    deleted_size += file_size
                except Exception as e:
                    logger.error(f"로그 파일 삭제 오류: {old_file}, {e}")
    
    # 3. /tmp 디렉토리 정리
    tmp_patterns = [
        "/tmp/chrome_*",
        "/tmp/selenium_*",
        "/tmp/*.png",
        "/tmp/*.log"
    ]
    
    for pattern in tmp_patterns:
        for file_path in glob.glob(pattern):
            try:
                if os.path.isfile(file_path) and datetime.fromtimestamp(os.path.getmtime(file_path)) < cutoff_time:
                    file_size = os.path.getsize(file_path)
                    os.remove(file_path)
                    deleted_count += 1
                    deleted_size += file_size
            except Exception as e:
                pass  # /tmp 파일은 삭제 권한 문제가 있을 수 있으므로 오류 무시
    
    # 4. __pycache__ 디렉토리 정리
    for root, dirs, files in os.walk(project_dir):
        if "__pycache__" in dirs:
            pycache_dir = os.path.join(root, "__pycache__")
            try:
                # 디렉토리 크기 계산
                dir_size = sum(os.path.getsize(os.path.join(pycache_dir, f)) 
                             for f in os.listdir(pycache_dir) 
                             if os.path.isfile(os.path.join(pycache_dir, f)))
                
                # 디렉토리 삭제
                shutil.rmtree(pycache_dir)
                deleted_count += 1
                deleted_size += dir_size
            except Exception as e:
                logger.error(f"캐시 삭제 오류: {pycache_dir}, {e}")
    
    # 5. 시스템 캐시 정리 시도 (EC2에서 권한이 있을 경우)
    try:
        import subprocess
        subprocess.run("sudo sh -c 'sync; echo 3 > /proc/sys/vm/drop_caches'", 
                      shell=True, timeout=5, capture_output=True)
    except:
        pass  # 권한 문제로 실패할 수 있으므로 무시
    
    # 정리 후 디스크 사용량 확인
    final_usage = psutil.disk_usage('/')
    space_freed = initial_usage.percent - final_usage.percent
    
    logger.info(f"디스크 정리 완료: {deleted_count}개 항목 제거, {deleted_size/1024/1024:.2f} MB 확보")
    logger.info(f"디스크 사용량 변화: {initial_usage.percent}% → {final_usage.percent}% (감소: {space_freed:.1f}%)")
    
    return final_usage.percent


if __name__ == "__main__":
    logger.info("Starting trading bot...")
    try:
        # 시작할 때 철저한 정리
        cleanup_chrome_processes()
        cleanup_temp_files()
        
        # 메모리 덤프 및 리소스 모니터링을 위한 함수
        def log_memory_usage():
            """메모리 사용량 모니터링 및 로깅 - 개선된 버전"""
            try:
                # 현재 프로세스 정보 수집
                process = psutil.Process(os.getpid())
                memory_info = process.memory_info()
                
                # 상세한 메모리 정보 로깅
                logger.info(f"메모리 사용량: {memory_info.rss / 1024 / 1024:.2f} MB")
                logger.info(f"가상 메모리: {memory_info.vms / 1024 / 1024:.2f} MB")
                
                # 시스템 전체 메모리 정보
                system_memory = psutil.virtual_memory()
                logger.info(f"시스템 메모리 사용률: {system_memory.percent}%")
                
                # CPU 정보 추가
                cpu_percent = psutil.cpu_percent(interval=1)
                logger.info(f"CPU 사용률: {cpu_percent}%")
                
                # 열린 파일 핸들 수 확인
                try:
                    open_files = process.open_files()
                    logger.info(f"열린 파일 핸들 수: {len(open_files)}")
                except:
                    logger.info("열린 파일 핸들 정보를 가져올 수 없음")
                
                # 스레드 정보 확인
                threads = process.num_threads()
                logger.info(f"활성 스레드 수: {threads}")
                
                # 상위 메모리 사용 프로세스 로깅 (크롬 관련)
                try:
                    chrome_processes = []
                    for proc in psutil.process_iter(['pid', 'name', 'memory_info']):
                        if 'chrome' in proc.info['name'].lower() or 'chromedriver' in proc.info['name'].lower():
                            chrome_processes.append({
                                'pid': proc.info['pid'],
                                'name': proc.info['name'],
                                'memory_mb': proc.info['memory_info'].rss / 1024 / 1024
                            })
                    
                    if chrome_processes:
                        # 메모리 사용량 기준 내림차순 정렬
                        chrome_processes = sorted(chrome_processes, key=lambda x: x['memory_mb'], reverse=True)
                        # 상위 5개만 로깅
                        for proc in chrome_processes[:5]:
                            logger.info(f"크롬 프로세스: PID={proc['pid']}, 이름={proc['name']}, 메모리={proc['memory_mb']:.2f} MB")
                except:
                    pass
                
                # 너무 많은 로그 파일 생성 방지 - 로그 파일 정리
                log_dir = "logs"
                if os.path.exists(log_dir):
                    log_files = sorted([os.path.join(log_dir, f) for f in os.listdir(log_dir) if f.endswith('.log')])
                    if len(log_files) > 30:
                        for old_file in log_files[:-30]:
                            try:
                                os.remove(old_file)
                                logger.info(f"오래된 로그 파일 삭제: {old_file}")
                            except Exception as e:
                                logger.warning(f"로그 파일 삭제 실패: {e}")
                
                # 메모리 사용량이 높으면 자동 정리 수행
                if system_memory.percent > 75:
                    logger.warning(f"높은 메모리 사용량 감지: {system_memory.percent}%, 자동 정리 수행")
                    WebDriverManager.quit()
                    cleanup_chrome_processes()
                    cleanup_temp_files()
                    gc.collect()
                    gc.collect()
                    
                    # 정리 후 메모리 사용량 다시 확인
                    process = psutil.Process(os.getpid())
                    memory_info = process.memory_info()
                    logger.info(f"정리 후 메모리 사용량: {memory_info.rss / 1024 / 1024:.2f} MB")
                    
            except Exception as e:
                logger.error(f"메모리 사용량 로깅 중 오류: {e}")
        
        # 핸들러 등록
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        atexit.register(cleanup_handler)
        
        # 데이터베이스 초기화
        init_db()
        
        # 리소스 모니터링
        schedule.every(5).minutes.do(check_resource_usage)
        
        # 메모리 모니터링 주기 단축 (30분→15분)
        schedule.every(15).minutes.do(log_memory_usage)
        
        # 디스크 정리 추가 (3시간마다 실행)
        schedule.every(3).hours.do(simple_disk_cleanup, logger)
        
        # 시스템 안정화 기능 강화 (24시간→12시간)
        def system_stabilization():
            try:
                process = psutil.Process(os.getpid())
                uptime_seconds = time.time() - process.create_time()
                
                # 12시간으로 단축 (24시간→12시간)
                if uptime_seconds > 43200:  # 12시간
                    logger.info("12시간 이상 실행 중, 안정화를 위한 정상 종료 준비...")
                    
                    # 모든 리소스 정리
                    WebDriverManager.quit()
                    cleanup_chrome_processes()
                    cleanup_temp_files()
                    
                    # 스케줄러 작업 정리
                    schedule.clear()
                    
                    # 프로그램 종료
                    logger.info("안정화 종료 프로세스 완료. 종료합니다...")
                    sys.exit(0)
            except Exception as e:
                logger.error(f"시스템 안정화 중 오류: {e}")
        
        # 시스템 안정화 스케줄 추가 (매 시간 체크)
        # NOTE : (25-03-05) system_stabilization 실행 시 파이썬 코드 재실행 불가 문제 발생. 따라서, 스케줄링에서 현재는 제외
        # schedule.every(1).hours.do(system_stabilization) 
        
        # 글로벌 변수 초기화
        sl_monitor_jobs = []
        trading_in_progress = False
        monitoring_in_progress = False
        
        # AI 트레이딩 작업 강화 - 실패 시 메모리 정리
        def trading_job():
            global trading_in_progress
            if trading_in_progress:
                logger.warning("Trading job is already in progress, skipping this run")
                return
            
            start_time = time.time()
            try:
                trading_in_progress = True
                
                # 작업 시작 전 리소스 확인
                memory_percent = psutil.virtual_memory().percent
                if memory_percent > 75:
                    logger.warning(f"트레이딩 작업 시작 전 높은 메모리 사용량 감지: {memory_percent}%")
                    WebDriverManager.quit()
                    cleanup_chrome_processes()
                    gc.collect()
                
                ai_trading()
            except Exception as e:
                logger.error(f"An error occurred in trading job: {e}")
                # 오류 발생 시 강제 정리
                WebDriverManager.quit()
                cleanup_chrome_processes()
            finally:
                trading_in_progress = False
                elapsed_time = time.time() - start_time
                logger.info(f"Trading job completed in {elapsed_time:.2f} seconds")
                
                # 완료 후 메모리 정리 강화
                gc.collect()
                gc.collect()  # 두 번 연속 호출
                
                process = psutil.Process(os.getpid())
                logger.info(f"트레이딩 작업 후 메모리 사용량: {process.memory_info().rss / 1024 / 1024:.2f} MB")
        
        # 수동 거래 모니터링 작업
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
                # 메모리 정리
                gc.collect()
        
        # 초기 실행
        trading_job()
        monitoring_job()
        
        # 스케줄 설정
        schedule.every(5).minutes.do(trading_job)
        schedule.every(1).minutes.do(monitoring_job)
        
        # 스케줄러 실행 - 예외 처리 강화
        while True:
            try:
                schedule.run_pending()
                time.sleep(1)
            except Exception as e:
                logger.error(f"스케줄러 실행 중 오류: {e}")
                time.sleep(5)  # 오류 발생 시 대기 시간 증가
            
    except Exception as e:
        logger.error(f"Critical error occurred: {e}")
        cleanup_chrome_processes()
        WebDriverManager.quit()
    finally:
        logger.info("Trading bot shutting down...")
        cleanup_chrome_processes()
        WebDriverManager.quit()