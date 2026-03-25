# -*- coding: utf-8 -*-
"""
data_pusher.py — SHE → Railway Push 모듈
위치: D:\\vom project(260317)\\SHE(260323)\\data_pusher.py

■ 역할
  - 보유종목(consign_stocks) 5분 간격 Push
  - 진입후보(signals) 17:00 Push
  - 조회종목 요청 폴링 → 분석 → 결과 Push

■ 연동
  - master.py에서 import하여 사용
  - 또는 단독 스케줄러로 실행 가능
"""

import os, sys, json, time, logging, requests
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# ════════════════════════════════════════
# ■ 설정
# ════════════════════════════════════════
RAILWAY_URL     = os.environ.get("RAILWAY_URL",     "https://your-app.railway.app")
PUSH_SECRET_KEY = os.environ.get("PUSH_SECRET_KEY", "SHE_SECRET_2026")
ADMIN_SECRET    = os.environ.get("ADMIN_SECRET",    "SHE_ADMIN_2026")
PUSH_INTERVAL   = 300   # 5분

BASE_DIR = Path(__file__).parent
LOG_DIR  = BASE_DIR / "logs" / "pusher"
LOG_DIR.mkdir(parents=True, exist_ok=True)

# ════════════════════════════════════════
# ■ 로거
# ════════════════════════════════════════
_log_path = LOG_DIR / f"pusher_{datetime.now().strftime('%y%m%d_%H%M')}.txt"
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [PUSHER] %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.FileHandler(_log_path, encoding="utf-8"),
        logging.StreamHandler(),
    ]
)
log = logging.getLogger("pusher")


# ════════════════════════════════════════
# ■ DataPusher
# ════════════════════════════════════════
class DataPusher:

    def __init__(self):
        self._push_headers  = {
            "Content-Type":  "application/json",
            "X-Secret-Key":  PUSH_SECRET_KEY,
        }
        self._admin_headers = {
            "Content-Type":  "application/json",
            "X-Admin-Key":   ADMIN_SECRET,
        }
        log.info(f"DataPusher 초기화 — 서버: {RAILWAY_URL}")

    # ──────────────────────────────────────
    # ■ 보유종목 Push (5분마다)
    # ──────────────────────────────────────
    def push_holdings(self):
        """consign_stocks DB → Railway"""
        try:
            from data.trade_db import get_consign
            from core.kiwoom_rest import kiwoom
            stocks = get_consign()
            holdings = []
            for s in stocks:
                code  = s.get("code","")
                ep    = int(s.get("entry_price", 0) or 0)
                qty   = int(s.get("qty", 0) or 0)
                # 현재가 조회 (장중=API, 장외=DB)
                cp = 0
                try:
                    from datetime import datetime as dt
                    h = dt.now().hour
                    if 9 <= h <= 15:
                        cp = kiwoom.get_current_price(code) or 0
                except: pass
                if not cp:
                    cp = int(s.get("cur_price", 0) or ep)

                eval_  = cp * qty
                profit = (cp - ep) * qty
                pct    = round((cp - ep) / ep * 100, 2) if ep > 0 else 0.0

                holdings.append({
                    "holder":      s.get("holder",""),
                    "code":        code,
                    "name":        s.get("name",""),
                    "qty":         qty,
                    "entry_price": ep,
                    "cur_price":   cp,
                    "eval_amt":    eval_,
                    "profit_amt":  profit,
                    "profit_pct":  pct,
                    "memo":        s.get("note",""),
                    "added_at":    s.get("created_at",""),
                })

            payload = {
                "timestamp": datetime.now().isoformat(),
                "holdings":  holdings,
            }
            self._post("/api/push/holdings", payload)
            log.info(f"보유종목 Push: {len(holdings)}건")
        except Exception as e:
            log.error(f"보유종목 Push 실패: {e}")

    # ──────────────────────────────────────
    # ■ 진입후보 Push (17:00 스케줄)
    # ──────────────────────────────────────
    def push_signals(self, signals: list = None):
        """
        SHE 진입후보 → Railway
        signals: signal_eng.get_today_signals().values() 형태
        """
        try:
            if signals is None:
                from strategy.signal_engine import signal_eng
                signals = list(signal_eng.get_today_signals().values())

            payload = {
                "timestamp": datetime.now().isoformat(),
                "date":      datetime.now().strftime("%Y%m%d"),
                "signals":   signals,
            }
            self._post("/api/push/signals", payload)
            log.info(f"진입후보 Push: {len(signals)}건")
        except Exception as e:
            log.error(f"진입후보 Push 실패: {e}")

    # ──────────────────────────────────────
    # ■ 조회요청 폴링 + 분석 + 결과 Push
    # ──────────────────────────────────────
    def process_lookup_queue(self):
        """Railway에서 조회요청 수신 → 분석 → 결과 Push"""
        try:
            url  = f"{RAILWAY_URL}/api/pull/lookup_queue"
            resp = requests.get(url, headers=self._push_headers, timeout=10)
            if resp.status_code != 200: return
            queue = resp.json().get("queue", [])
            if not queue: return

            log.info(f"조회요청 {len(queue)}건 수신")
            for item in queue:
                code = item.get("code","")
                name = item.get("name", code)
                try:
                    result = self._analyze_stock(code, name)
                    self._post("/api/push/lookup_result", {"code": code, "result": result})
                    log.info(f"분석 완료: {name}({code})")
                except Exception as e:
                    log.error(f"분석 실패 {code}: {e}")
        except Exception as e:
            log.error(f"조회큐 처리 실패: {e}")

    def _analyze_stock(self, code: str, name: str) -> dict:
        """단일 종목 분석 — 현재가 + 추세 + 지표"""
        from data.db_manager import get_daily as _gd
        from core.kiwoom_rest import kiwoom
        import pandas as pd

        # 현재가
        cur = 0
        try:
            h = datetime.now().hour
            if 9 <= h <= 15:
                cur = kiwoom.get_current_price(code) or 0
        except: pass

        # 일봉
        rows = _gd(code, limit=300)
        if not rows:
            return {"cur_price": cur, "error": "데이터 없음"}

        df = pd.DataFrame(rows)
        for c in ["open","high","low","close","volume"]:
            df[c] = pd.to_numeric(df[c], errors="coerce")
        df["date"] = pd.to_datetime(df["date"].astype(str), format="%Y%m%d")
        df = df[df["close"]>0].sort_values("date").reset_index(drop=True)

        if not cur:
            cur = int(df["close"].iloc[-1]) if len(df) else 0

        # 60일 종이격
        gap60 = 0.0
        if len(df) >= 60:
            ma60  = df["close"].rolling(60).mean().iloc[-1]
            gap60 = round((df["close"].iloc[-1] - ma60) / ma60 * 100, 2) if ma60 else 0.0

        # 추세 정보 (월/주/일봉)
        trend_info = {}
        try:
            from indicators.trend_classifier import build_trend
            tdf  = build_trend(df)
            last = tdf.iloc[-1]
            trend_info["일봉"] = {
                "ma":      str(last.get("up_ma",""))   or "-",
                "macd":    str(last.get("hist_up","")) or "-",
                "rsi":     str(last.get("up_rsi",""))  or "-",
                "adx":     str(last.get("up_adx",""))  or "-",
                "vol":     str(last.get("vol_up",""))  or "-",
                "overall": str(last.get("trend",""))   or "-",
            }
        except: pass

        # 개별 지표 (기본값)
        indicators = []
        try:
            close  = df["close"]
            ma5    = close.rolling(5).mean().iloc[-1]
            ma20   = close.rolling(20).mean().iloc[-1]
            ma60_v = close.rolling(60).mean().iloc[-1]
            cur_c  = close.iloc[-1]
            indicators = [
                {"name":"MA5",  "ok": cur_c > ma5,   "display": f"{ma5:,.0f}"},
                {"name":"MA20", "ok": cur_c > ma20,   "display": f"{ma20:,.0f}"},
                {"name":"MA60", "ok": cur_c > ma60_v, "display": f"{ma60_v:,.0f}"},
                {"name":"60일종이격", "ok": gap60 > 0, "display": f"{gap60:+.2f}%"},
            ]
        except: pass

        return {
            "cur_price":  cur,
            "gap_60d":    gap60,
            "trend_info": trend_info,
            "indicators": indicators,
            "updated_at": datetime.now().isoformat(),
        }

    # ──────────────────────────────────────
    # ■ 사용자 등록 (admin_mode.py에서 호출)
    # ──────────────────────────────────────
    def register_user(self, holder: str, phone: str) -> dict:
        """
        보유자 등록 → 토큰/링크 반환
        Returns: {"token": "...", "link": "...", "holder": "..."}
        """
        try:
            url  = f"{RAILWAY_URL}/api/admin/users"
            resp = requests.post(
                url,
                json={"holder": holder, "phone": phone},
                headers=self._admin_headers,
                timeout=10
            )
            if resp.status_code == 200:
                data = resp.json()
                log.info(f"사용자 등록: {holder} → {data.get('link','')}")
                return data
            else:
                log.error(f"사용자 등록 실패: {resp.status_code} {resp.text}")
                return {}
        except Exception as e:
            log.error(f"사용자 등록 오류: {e}")
            return {}

    def list_users(self) -> list:
        """전체 사용자 목록 조회"""
        try:
            url  = f"{RAILWAY_URL}/api/admin/users"
            resp = requests.get(url, headers=self._admin_headers, timeout=10)
            if resp.status_code == 200:
                return resp.json().get("users", [])
        except: pass
        return []

    def delete_user(self, token: str) -> bool:
        """사용자 삭제"""
        try:
            url  = f"{RAILWAY_URL}/api/admin/users/{token}"
            resp = requests.delete(url, headers=self._admin_headers, timeout=10)
            return resp.status_code == 200
        except: return False

    # ──────────────────────────────────────
    # ■ 통합 사이클 (5분마다)
    # ──────────────────────────────────────
    def run_cycle(self, signals=None):
        """master.py 스케줄러에서 5분마다 호출"""
        log.info("── Push 사이클 시작 ──")
        self.push_holdings()
        self.process_lookup_queue()
        log.info("── Push 사이클 완료 ──")

    def run_signal_push(self, signals=None):
        """17:00 신호 스캔 후 호출"""
        self.push_signals(signals)

    # ──────────────────────────────────────
    # ■ 내부: HTTP POST
    # ──────────────────────────────────────
    def _post(self, endpoint: str, payload: dict):
        url = f"{RAILWAY_URL}{endpoint}"
        try:
            resp = requests.post(url, json=payload,
                                 headers=self._push_headers, timeout=15)
            if resp.status_code == 200:
                log.info(f"✅ {endpoint}")
            else:
                log.warning(f"⚠️ {endpoint} → {resp.status_code}")
        except requests.exceptions.ConnectionError:
            log.error(f"❌ 서버 연결 실패: {url}")
        except Exception as e:
            log.error(f"❌ Push 오류 {endpoint}: {e}")


# 전역 인스턴스
pusher = DataPusher()


# ════════════════════════════════════════
# ■ 단독 실행 (테스트)
# ════════════════════════════════════════
if __name__ == "__main__":
    log.info("=== DataPusher 단독 실행 ===")
    import schedule

    schedule.every(5).minutes.do(pusher.run_cycle)
    schedule.every().day.at("17:00").do(pusher.run_signal_push)

    pusher.run_cycle()   # 즉시 1회 실행

    while True:
        schedule.run_pending()
        time.sleep(10)
