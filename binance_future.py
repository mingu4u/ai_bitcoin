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
        
        # BlackFlag FTS 업데이트 (새로운 신호가 있을 때만)
        blackflag = analysis_result.get("BlackFlag", {})
        if blackflag.get("flip_detected") != "none" and blackflag.get("flip_time"):
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
                    signal_direction = "Buy" if blackflag.get("flip_detected") == "long" else "Sell"
                    
                    # 기존 신호가 없거나 새로운 신호가 더 최근인 경우만 업데이트
                    if (self.signals["BlackFlag"]["timestamp"] is None or 
                        signal_time > datetime.fromisoformat(self.signals["BlackFlag"]["timestamp"])):
                        self.signals["BlackFlag"] = {
                            "signal": signal_direction,
                            "candles_ago": self._calculate_candles_ago(signal_time, current_time),
                            "timestamp": signal_time.isoformat(),
                            "stop_loss_price": blackflag.get("stop_loss_price")
                        }
                        print(f"BlackFlag 신호 업데이트: {signal_direction}, {signal_time_str}, SL: {blackflag.get('stop_loss_price')}")
            except Exception as e:
                print(f"BlackFlag 시간 파싱 오류: {e}, 원본 시간: {blackflag.get('flip_time')}")
        
        # UT Bot Alerts 업데이트 (새로운 신호가 있을 때만)
        utbot = analysis_result.get("UTBot", {})
        if utbot.get("alert_signal") != "None" and utbot.get("alert_time"):
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
                    
                    # 기존 신호가 없거나 새로운 신호가 더 최근인 경우만 업데이트
                    if (self.signals["UTBot"]["timestamp"] is None or 
                        signal_time > datetime.fromisoformat(self.signals["UTBot"]["timestamp"])):
                        self.signals["UTBot"] = {
                            "signal": utbot.get("alert_signal"),
                            "candles_ago": self._calculate_candles_ago(signal_time, current_time),
                            "timestamp": signal_time.isoformat()
                        }
                        print(f"UTBot 신호 업데이트: {utbot.get('alert_signal')}, {signal_time_str}")
            except Exception as e:
                print(f"UTBot 시간 파싱 오류: {e}, 원본 시간: {utbot.get('alert_time')}")
        
        # Volume Oscillator 업데이트 (항상 업데이트, FIFO 방식)
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
            
            # 10캔들 이상 지난 신호는 None 처리
            if self.signals["BlackFlag"]["candles_ago"] > 10:
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
            
            # 10캔들 이상 지난 신호는 None 처리
            if self.signals["UTBot"]["candles_ago"] > 10:
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
                            blackflag_cloud_roi=(0.0, 0.0, 0.9, 0.67),
                            blackflag_xaxis_yrange=(0.85, 0.90),
                            blackflag_chunk_size=10,
                            blackflag_needed_red_chunks=2,
                            blackflag_needed_green_chunks=2,
                            # UT Bot parameters
                            utbot_xaxis_yrange=(0.85, 0.90),
                            # Volume Oscillator parameters (normalized ROI)
                            volume_roi=(0.92, 0.65, 0.97, 0.84),
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
        x_margin = 50
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
        candidate_center_y = None
        if flip_x_local < roi_w:
            right_side_mask = mask_candidate[:, flip_x_local:]
            points = cv2.findNonZero(right_side_mask)
            if points is not None:
                points[:,:,0] += flip_x_local
                max_x = np.max(points[:,:,0])
                candidate_points = points[points[:,:,0] == max_x]
                candidate_points = candidate_points.reshape(-1,2)
                candidate_center_y = int(np.mean(candidate_points[:,1]))
        stop_loss_price = None
        if candidate_center_y is not None:
            global_center_y = cy1 + candidate_center_y
            band_half = 20
            new_s_y1 = max(0, global_center_y - band_half)
            new_s_y2 = min(h, global_center_y + band_half)
            s_x1 = int(w * 0.92)
            s_x2 = int(w * 0.97)
            roi_stoploss = img_bf[new_s_y1:new_s_y2, s_x1:s_x2]
            cv2.rectangle(debug_img, (s_x1, new_s_y1), (s_x2, new_s_y2), (0,255,0), 2)
        else:
            s_x1 = int(w * 0.92)
            s_y1 = int(h * 0.05)
            s_x2 = int(w * 0.97)
            s_y2 = int(h * 0.68)
            roi_stoploss = img_bf[s_y1:s_y2, s_x1:s_x2]
            cv2.rectangle(debug_img, (s_x1, s_y1), (s_x2, s_y2), (255,0,255), 2)
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
            if area < 1500:
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
            if area < 1500:
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

# def main():
#     """
#     메인 함수 - 트레이딩 신호 처리 및 AI 프롬프트 생성 예시
#     """
#     # 차트 신호 프로세서 초기화
#     processor = ChartSignalProcessor()
    
#     # 예시: 차트 이미지 처리
#     image_path = "chart_image.png"  # 실제 이미지 경로로 변경 필요
    
#     # 이미지가 존재하는지 확인
#     if os.path.exists(image_path):
#         # 이미지 분석 및 신호 업데이트
#         result = processor.process_chart_image(image_path, debug=True)
        
#         if result:
#             print("차트 분석 결과:", result)
            
#             # AI 프롬프트 데이터 생성
#             prompt_data = processor.generate_ai_prompt_data()
#             print("\nAI 프롬프트 데이터:", json.dumps(prompt_data, indent=2))
            
#             # AI 프롬프트 텍스트 생성
#             prompt_text = processor.create_prompt_text()
#             print("\nAI 프롬프트 텍스트:")
#             print(prompt_text)
#         else:
#             print("차트 분석 실패")
#     else:
#         print(f"이미지 파일을 찾을 수 없습니다: {image_path}")

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
# SQLite 데이터베이스 초기화 함수 - 거래 내역을 저장할 테이블을 생성 (수정됨)
def init_db():
    conn = sqlite3.connect('bitcoin_trades.db')
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
    return conn

# 거래 기록을 DB에 저장하는 함수

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
        blackflag_signal = signals_data.get("BlackFlag", {}).get("signal")
        blackflag_candles_ago = signals_data.get("BlackFlag", {}).get("candles_ago")
        utbot_signal = signals_data.get("UTBot", {}).get("signal")
        utbot_candles_ago = signals_data.get("UTBot", {}).get("candles_ago")
        volume_osc_current = signals_data.get("VolumeOsc", {}).get("current")
        stop_loss_price = signals_data.get("BlackFlag", {}).get("stop_loss_price")
    
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



# # 스크린샷 캡쳐 및 base64 이미지 인코딩        
# def capture_and_encode_screenshot(driver, type, save="no"):
#     try:
#         # 스크린샷 캡처
#         png = driver.get_screenshot_as_png()
        
#         # PIL Image로 변환
#         img = Image.open(io.BytesIO(png))
        
#         # 이미지 리사이즈 (OpenAI API 제한에 맞춤)
#         img.thumbnail((2000, 2000))
        
#         # 현재 시간을 파일명에 포함
#         current_time = datetime.now().strftime("%Y%m%d_%H%M%S")
#         filename = f"{type}_chart_{current_time}.png"
        
#         # 현재 스크립트의 경로를 가져옴
#         script_dir = os.path.dirname(os.path.abspath(__file__))
        
#         # 파일 저장 경로 설정
#         file_path = os.path.join(script_dir, filename)
        
#         # 이미지 파일로 저장
#         if save == "yes":
#             img.save(file_path)
#             logger.info(f"스크린샷이 저장되었습니다: {file_path}")
        
#         # 이미지를 바이트로 변환
#         buffered = io.BytesIO()
#         img.save(buffered, format="PNG")
        
#         # base64로 인코딩
#         base64_image = base64.b64encode(buffered.getvalue()).decode('utf-8')
        
#         return base64_image, file_path
#     except Exception as e:
#         logger.error(f"스크린샷 캡처 및 인코딩 중 오류 발생: {e}")
#         return None, None


# 새로 추가된 차트 캡처 및 분석 함수
def capture_and_analyze_chart(driver, chart_processor=None):
    """
    차트 이미지를 캡처하고 신호를 분석하는 함수
    
    Args:
        driver: Selenium 웹드라이버
        chart_processor: 차트 신호 프로세서 인스턴스
        
    Returns:
        tuple: (차트 이미지 base64, 신호 분석 결과, 이미지 파일 경로)
    """
    try:
        # 스크린샷 캡처
        png = driver.get_screenshot_as_png()
        
        # PIL Image로 변환
        img = Image.open(io.BytesIO(png))
        
        # 이미지 리사이즈 (필요시)
        img.thumbnail((2000, 2000))
        
        # 파일명에 현재 시간 포함
        current_time = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"chart_{current_time}.png"
        
        # 현재 스크립트의 경로를 가져옴
        script_dir = os.path.dirname(os.path.abspath(__file__))
        
        # 파일 저장 경로 설정
        file_path = os.path.join(script_dir, filename)
        
        # 이미지 파일로 저장
        # img.save(file_path)
        # logger.info(f"차트 스크린샷이 저장되었습니다: {file_path}")
        
        # base64로 인코딩
        buffered = io.BytesIO()
        img.save(buffered, format="PNG")
        base64_image = base64.b64encode(buffered.getvalue()).decode('utf-8')
        
        # 신호 분석 수행 (차트 프로세서가 제공된 경우)
        signal_analysis = None
        if chart_processor is not None:
            signal_analysis = chart_processor.process_chart_image(file_path, debug=True)
            if signal_analysis:
                logger.info("차트 신호 분석 완료")
            else:
                logger.warning("차트 신호 분석 실패")
        
        return base64_image, signal_analysis, file_path
        
    except Exception as e:
        logger.error(f"차트 캡처 및 분석 중 오류 발생: {e}")
        return None, None, None


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
    
    # 차트 신호 프로세서 초기화 (새로 추가)
    chart_processor = ChartSignalProcessor()
    ### 데이터 가져오기
    # 7. Selenium으로 차트 캡처
    driver = None
    chart_image = None
    try:
        # TradingView 차트 캡처
        driver = login_with_cookies()
        driver.get("https://kr.tradingview.com/chart/zcDfxQQ8/?symbol=BINANCE%3ABTCUSDT.P")
        logger.info("TradingView 페이지 로드 완료")
        time.sleep(3)
    
        # chart_image, saved_file_path2 = capture_and_encode_screenshot(driver, "tradingview", save="no")
        # logger.info(f"TradingView 스크린샷 캡처 완료.")
    
        # 이미지 캡처 및 신호 분석 (수정된 부분)
        chart_image, signals_analysis, saved_file_path = capture_and_analyze_chart(driver, chart_processor)    
        
        if chart_image:
            logger.info(f"TradingView 스크린샷 캡처 및 분석 완료.")
        else:
            logger.error("스크린샷 캡처 실패")
                    
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
            # 차트 신호 데이터를 AI 프롬프트에 포함 (새로 추가)
            trading_signals_text = chart_processor.create_prompt_text()
            
            # AI 모델에 프롬프트 제공 (수정된 부분)
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                    "role": "system",
                    "content": f"""
                        ───────────────────────────────────────────────────────────────
                        # Bitcoin Futures Trading Strategy

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

                        You must first check the Portfolio information before making any trading decision. If Current Position Side is "none", then no exit orders should be executed; if a close signal is generated, it must be treated as a new entry (reversal) rather than closing a non-existing position.

                        ───────────────────────────────────────────────────────────────
                        ## 3. Core Strategy Overview

                        ### A. Critical Timing

                        **For Long Entry:**  
                        - **BlackFlag FTS:** Must show a red-to-green transition (indicating a change from bearish to bullish) within the last 3 candles. Refer to the "BlackFlag FTS Signal" data in the trading signals section to confirm the signal and its freshness.
                        - **UT Bot Alerts:** Must display a BUY alert within the last 3 candles. Refer to the "UT Bot Alert" data in the trading signals section to confirm the signal and its freshness.
                        - **Volume Oscillator:** Must be positive on the current candle, confirming rising volume momentum supportive of a long move. Refer to the "Volume Oscillator" data in the trading signals section to check current value and recent history.

                        **For Short Entry:**  
                        - **BlackFlag FTS:** Must show a green-to-red transition (indicating a change from bullish to bearish) within the last 3 candles. Refer to the "BlackFlag FTS Signal" data in the trading signals section to confirm the signal and its freshness.
                        - **UT Bot Alerts:** Must display a SELL alert within the last 3 candles. Refer to the "UT Bot Alert" data in the trading signals section to confirm the signal and its freshness.
                        - **Volume Oscillator:** Must be positive on the current candle, confirming sufficient momentum for a short move. Refer to the "Volume Oscillator" data in the trading signals section to check current value and recent history.

                        Any stale signals or misalignment → "hold" (no entry).  
                        **This is mandatory: prioritize the "Trading Signals Data" section from the user input, which provides exact information about each indicator signal and its freshness (candles ago). If any core indicator signal is older than 3 candles, you must not enter. Always "hold" unless all three primary indicators are fresh (≤3 candles).**
                                                
                        ### B. Additional Indicators (RSI, MACD, ATR, CMF, ADX, DI+/DI-)
                        Use these solely for extra confirmation or for rejecting the primary signal.  
                        **Do not open a position based only on Additional Indicators if the primary indicators do not show a valid fresh entry signal.**  
                        While additional indicators may override or cancel a primary entry (resulting in a “hold”), they cannot independently generate an entry.  
                        Adjust stops and position size using ATR; monitor momentum (MACD, ADX) and money flow (CMF).

                        ### C. Signal Classification: Strong, Moderate, Weak

                        • **Strong Signal**  
                        - Primary indicators are in perfect alignment with very high volume (≥250% avg) and low, stable ATR.  
                        - Position Size: 100% of calculated size.  
                        - Stop Loss: ±0.7% from entry (refined with Cloud/ATR).  
                        - P/L Ratio: ~2.0.

                        • **Moderate Signal**  
                        - Adequate volume and volatility with clean and well-aligned primary indicators.  
                        - Position Size: ~60%.  
                        - Stop Loss: ±0.5% from entry or Cloud.  
                        - P/L Ratio: ~1.75 (within a range of 1.5 to 2.0).

                        • **Weak Signal**  
                        - Primary indicators appear borderline (possibly slightly delayed or with lower volume), or only partially supportive.  
                        - Position Size: ~30%.  
                        - Stop Loss: ±0.4% from entry (with Cloud + ATR checks).  
                        - P/L Ratio: ~1.5 (within a range of 1.5 to 2.0).

                        ### D. Price Action & Key Levels (Support/Resistance)
                        Identify notable swing highs and lows on the 5-minute, 1-hour, and 4-hour charts to locate potential support (previous lows) or resistance (previous highs).  
                        • A primary signal occurring just below a strong resistance should be treated with caution—consider waiting for confirmation (such as a breakout or a clear rejection).  
                        • Conversely, if a primary BUY signal coincides with a well-established support level on a higher timeframe, it further strengthens your entry case.  
                        • Use these levels only as confluence or rejection criteria; do not base your entry solely on price action if the primary indicators are not validating a fresh signal.  
                        • When prices approach or move beyond these key levels, watch for divergences or volume spikes for further confirmation or rejection.

                        ───────────────────────────────────────────────────────────────
                        ## 4. Stop Loss & Take Profit

                        1) **Stop Loss Price**
                        - **Use the provided Stop Loss Price:** When available in the "Trading Signals Data" section, use the "Stop Loss Price" value that was directly extracted from the chart.
                        - **Fallback method:** If Stop Loss Price is "None" in the Trading Signals Data, then use Cloud-Based Stop Loss:
                        - **LONG:** Place near the deepest green portion of the latest Green Cloud.
                        - **SHORT:** Place near the deepest red portion of the latest Red Cloud.
                        - If this level is unreasonably far, refer to ATR guidelines (±0.4-0.7% from entry).
                        
                        2) **P/L Ratio (1.5-2.0)**  
                        - Strong Signal: Approximately 2.0 baseline.  
                        - Moderate Signal: Approximately 1.75 baseline.  
                        - Weak Signal: Approximately 1.5 baseline.

                        Adjust within this range based on current market volatility.

                        ───────────────────────────────────────────────────────────────
                        ## 5. Exit & Risk Management

                        • Exit if any core signal reverses or becomes invalid.  
                        • If the Volume Oscillator falls below 0%, that is an immediate red flag.  
                        • If secondary indicators exhibit significant contradictions (e.g., strong RSI or MACD divergence), exit early.  
                        • Employ partial exits when appropriate (for example, scaling out in increments of +0.1% gains).  
                        **• If the 5-minute MACD shows a clear trend reversal for 2 consecutive candles in the opposite direction, execute an immediate “Full Exit” of the position.**

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

                        - **decision:** Determine whether to open or close a position. “buy” is used to close shorts or open a new long; “sell” is used to close longs or open a new short; “hold” means take no action. Additionally, make sure to check your current position: if the Current Position Side shows “none”, then no exit order should be issued.
                        - **stop_loss_price:** Set based on Cloud levels or ATR guidelines (±0.4-0.7% from entry).  
                        - **pl_ratio:** Choose a value between 1.5 and 2.0 according to the signal strength.  
                        - **reason:** Provide a detailed explanation that includes:
                        - A clear statement of the current portfolio status (e.g., whether you have an active position and its side—long, short, or none).
                        - An explanation of the state of the primary indicators:
                            - **BlackFlag FTS:** Describe whether it shows a red-to-green transition for a long entry or a green-to-red transition for a short entry, and comment on its freshness.
                            - **UT Bot Alerts:** Specify if a BUY or SELL alert has been issued within the last 3 candles.
                            - **Volume Oscillator:** Confirm that it is positive, indicating sufficient momentum.
                        - Mention any other relevant details regarding volume or volatility that affect the decision.
                        
                        **Position Sizing Rules:**  
                        - The "percentage" field is an integer between 0 and 100 representing the fraction of a full allocation.
                        - For entry orders, 100 indicates using 100% of the available balance for entry.
                        - For exit orders, 100 indicates closing 100% of the current position quantity.
                        - In practice, you may choose any value from 0 to 100 (except when the decision is “hold”) based on signal strength and risk considerations.
                        - Use the following full-allocation benchmarks as your baseline:
                        - For entries: If Current Position Side is "long" or "none" and the decision is "buy", or if Current Position Side is "short" or "none" and the decision is "sell", 100% represents the entirety of the available balance.
                        - For exits: If Current Position Side is "short" and the decision is "buy", or if Current Position Side is "long" and the decision is "sell", 100% represents closing the entire current position.

                        ───────────────────────────────────────────────────────────────
                        ### Final Notes

                        1) Always check the Portfolio information before deciding: if Current Position Side is "none", then only new entry orders should be considered; exit orders are valid only when an active position exists.
                        2) **Prioritize the extracted signal data in the "Trading Signals Data" section**, which provides accurate information about signal freshness. Only consider signals within 3 candles old for entry decisions.
                        3) Use the correct exit commands: "buy" to exit a short and "sell" to exit a long.
                        4) Incorporate dynamically updated values from the [Market Data], [Portfolio], and [Trading Signals Data] sections.
                        5) Preserve capital by exiting immediately on conflicting or invalid signals.
                        
                        ───────────────────────────────────────────────────────────────
                        This is the final integrated prompt. Use all provided data, ensure that the three primary indicators (BlackFlag FTS, UT Bot Alerts, Volume OSC) are fresh (≤3 candles old) for any entry—even though slight delays of 3–4 candles may be acceptable if the price remains within ±0.2% of the trigger level and volume momentum persists (otherwise, treat it as stale if more than 4 candles have passed or if the price moves more than 0.5% away). Additionally, always check the Portfolio first to determine if you already have an active position; only execute exit orders if a position exists. Additional Indicators can only confirm or reject a fresh (or slightly delayed) primary signal—never generate an entry on their own. For position sizing, apply the Position Sizing Rules above when computing the percentage (0–100) for entries and exits. Also, incorporate local highs/lows across the 5-minute, 1-hour, and 4-hour charts to identify potential support/resistance zones and further refine or reject your primary signals.
                        ───────────────────────────────────────────────────────────────
  
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
                                
                                {trading_signals_text}
                                """
                            }
                            # {
                            #     "type": "image_url",
                            #     "image_url": {
                            #         "url": f"data:image/png;base64,{chart_image}"
                            #     }
                            # }
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

        # 신호 데이터 추출
        signals_data = chart_processor.generate_ai_prompt_data()

        # 거래 기록을 DB에 저장하기
        if order_executed and order_info != None:
            order_id = order_info['entry']['id']
            tp_order_id = order_info['tp']['id'] if order_info.get('tp') else None
            sl_order_id = order_info['sl']['id'] if order_info.get('sl') else None
            
            log_trade(conn, 'AI', order_id, result.decision, result.percentage, result.reason, 
            used_usdt, free_usdt, total_usdt, btc_avg_buy_price, current_btc_price, 
            reflection, tp_order_id, sl_order_id, signals_data)
            
            # 트레일링 스탑로스 모니터링 추가
            if 'monitor_sl' in order_info:
                # 함수를 변수에 저장
                monitor_sl_func = order_info['monitor_sl']
                
                def periodic_sl_monitoring():
                    try:
                        new_sl_order = monitor_sl_func()
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
                    reflection, None, None, signals_data)
    
    
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
