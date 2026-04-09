"""
server.py — SHE 보유자 앱 API 서버
위치: D:\\vom project(260317)\\SHE(260323)\\Railway(260325)\\server.py

■ 배포 (Railway)
    GitHub 연결 → Railway(260325) 폴더 → 자동 배포

■ 환경변수 (Railway 콘솔)
    PUSH_SECRET_KEY : data_pusher.py 와 동일하게
    ADMIN_SECRET    : admin_mode.py 에서 사용자 등록 시 사용
"""

import os, json, hashlib, secrets
from datetime import datetime
from pathlib import Path
from functools import wraps
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS

# ════════════════════════════════════════════════════════
# ■ 설정
# ════════════════════════════════════════════════════════
PUSH_SECRET_KEY = os.environ.get("PUSH_SECRET_KEY", "SHE_SECRET_2026")
ADMIN_SECRET    = os.environ.get("ADMIN_SECRET",    "SHE_ADMIN_2026")
PORT            = int(os.environ.get("PORT", 8080))

DATA_DIR = Path(os.environ.get("RAILWAY_VOLUME_MOUNT_PATH", "data"))
DATA_DIR.mkdir(exist_ok=True, parents=True)

# 데이터 파일
F_USERS     = DATA_DIR / "users.json"
F_HOLDINGS  = DATA_DIR / "holdings.json"
F_SIGNALS   = DATA_DIR / "signals.json"
F_LOOKUP_Q  = DATA_DIR / "lookup_queue.json"
F_LOOKUP_R  = DATA_DIR / "lookup_results.json"
F_VIRTUAL   = DATA_DIR / "virtual_portfolio.json"
F_PNL       = DATA_DIR / "pnl_ledger.json"

# ── 시그널 한글명 ─────────────────────────────────────────
SIG_KR = {
    '60일_종이격_상승_추세_1':'60일선위','60일_종이격_하락_추세_2':'60일선아래',
    '60일_종이격_상승_추세_3':'60일선눌림','200점_전환선_전환선_상승_4':'전환선200점',
    '100점_전환선_전환선_상승_5':'전환선100점','고점주의_전환선_전환선_상승_6':'전환선고점주의',
    '반달형_전환선_전환선_상승_7':'반달형전환선','200점_기준선_기준선_상승_8':'기준선200점',
    '100점_기준선_기준선_상승_9':'기준선100점','고점주의_기준선_기준선_상승_10':'기준선고점주의',
    '저점_기준선_기준선_하락_11':'기준선저점','반달형_기준선_기준선_상승_12':'반달형기준선',
    '전기선_GC_전기선__13':'전기선GC','전기선_DC_전기선__14':'전기선DC',
    '구름_앞구름_15':'양운전환','구름_앞구름_16':'음운전환',
    '캔들과_구름_내구름_17':'캔들구름위양운','캔들과_구름_내구름_18':'캔들구름안양운',
    '캔들과_구름_내구름_19':'캔들구름아래양운','캔들과_구름_내구름_20':'캔들구름위음운',
    '캔들과_구름_내구름_21':'캔들구름안음운','캔들과_구름_내구름_22':'캔들구름아래음운',
    '캔들과_전환선_전환선_하락_23':'캔들전환선눌림','캔들과_전기선_전기선__24':'캔들기준선터치',
    '후행스팬과_전기선_후행스팬과_전기선_25':'후행스팬기준선터치',
    '전기선과_신고가_전기선과_신고가_26':'전기선신고가','전기선과_VO_전기선과_VO_27':'전기선VO',
    '기준선과_선행스팬2_기준선과_선행스팬2_28':'기준선스팬2상승',
    '기준선과_선행스팬2_기준선과_선행스팬2_29':'기준선스팬2정지',
    '캔들과_후행스팬과_60일_이평_캔들과_후행스팬과_60일_이평_30':'캔들후행스팬60',
    '캔들과_이평선_5일_이평선_31':'5일선위','캔들과_이평선_5일_이평선_32':'5일선아래',
    '전환선과_이평선_전환선과_10일_이평선_33':'전환선10일선위',
    '전환선과_이평선_전환선과_10일_이평선_34':'전환선스토캐스틱',
    '10일_신고가_10일_신고가_35':'10일신고가','20일_신고가_20일_신고가_36':'20일신고가',
    '60일_신고가_60일_신고가_37':'60일신고가','이평산_배열_정배열_38':'5-10정배열',
    '이평산_배열_역배열_39':'5-10역배열','이평산_배열_이평선_골든크로스_40':'5-10GC',
    '이평산_배열_이평선_데드크로스_41':'5-10DC','이평산_배열_정배열_42':'10-60정배열',
    '이평산_배열_역배열_43':'10-60역배열','이평산_배열_이평선_골든크로스_44':'10-60GC',
    '이평산_배열_이평선_데드크로스_45':'10-60DC','이평산_배열_이평선_신고가_46':'GC신고가',
    'MACD_MACD_47':'MACD0선돌파','MACD_MACD_48':'MACD골든크로스',
    'MACD_MACD_49':'MACD데드크로스','MACD_MACD_50':'MACD전고점돌파',
    'MACD_MACD_51':'MACD전저점돌파','RSI_과열진입':'RSI과열진입','RSI_과열이탈':'RSI과열이탈',
    'ADX_ADX_53':'ADX과열진입','ADX_ADX_54':'ADX과열이탈','ADX_ADX_55':'ADX침체진입',
    'ADX_ADX_56':'ADX침체이탈','ADX_ADX_57':'ADX전고점돌파','ADX_ADX_58':'ADX전저점돌파',
    'ADX_ADX_59':'ADX최저값','ADX_ADX_60':'ADX매수세상승','ADX_ADX_61':'ADX매도세상승',
    'VO_VO_62':'VO양수','VO_VO_64':'VO최저점상승',
    'Pivot_Pivot_66':'피벗중심터치','Pivot_Pivot_67':'PivotR1터치','Pivot_Pivot_68':'PivotS1터치',
    'Pivot과_BII_Pivot과_BII_69':'Pivot+BII','BWI_BWI_70':'BWI확장',
    '이격도와_투자심리도_이격도와_투자심리도_71':'이격도투자심리',
    '캔들과_구름_내구름_17':'캔들구름위(양운)',
    '캔들과_구름_내구름_18':'캔들구름안(양운)',
    '캔들과_구름_내구름_19':'캔들구름아래(양운)',
    '캔들과_구름_내구름_20':'캔들구름위(음운)',
    '캔들과_구름_내구름_21':'캔들구름안(음운)',
    '캔들과_구름_내구름_22':'캔들구름아래(음운)',
    '캔들과_전환선_전환선_하락_23':'캔들전환선눌림',
    '캔들과_후행스팬과_60일_이평_캔들과_후행스팬과_60일_이평_30':'캔들후행스팬60이평',
    'ADX_ADX_52':'ADX상승',
    'VO_VO_63':'VO음수',
    'VO_VO_65':'VO최고점하락',
    '후행스팬_60이평선_터치_72':'후행스팬60이평선터치',
    '기준선하락_BII상승_73':'기준선하락BII상승','정배열_저가매수_74':'정배열저가매수',
    'TRANS_UP_히스트':'⚡추세전환+MACD증가','TRANS_UP_단독':'⚡추세전환(A등급)',
    'TRANS_UP_기관D20':'⚡추세전환+기관매수','UP_히스트중기':'📊상승추세+MACD증가',
    'UP_히스트_S8강화':'📊상승추세+S8매집','TRANS_UP_CCW_S2':'⚡추세전환+S2상승',
    'UP_대차감소':'📊상승추세+대차감소','UP_기관D20':'📊상승추세+기관매수',
}

def _sig_kr(key):
    return SIG_KR.get(key, key)

app = Flask(__name__, static_folder=".", static_url_path="")
CORS(app)


# ════════════════════════════════════════════════════════
# ■ 헬퍼
# ════════════════════════════════════════════════════════
def _save(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def _load(path, default=None):
    if not path.exists():
        return default if default is not None else {}
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except:
        return default if default is not None else {}

def require_push_key(f):
    @wraps(f)
    def deco(*a, **kw):
        if request.headers.get("X-Secret-Key","") != PUSH_SECRET_KEY:
            return jsonify({"error": "Unauthorized"}), 401
        return f(*a, **kw)
    return deco

def require_admin_key(f):
    @wraps(f)
    def deco(*a, **kw):
        if request.headers.get("X-Admin-Key","") != ADMIN_SECRET:
            return jsonify({"error": "Unauthorized"}), 401
        return f(*a, **kw)
    return deco

def _get_user(token):
    """토큰으로 사용자 조회"""
    users = _load(F_USERS, default={})
    return users.get(token)

def _verify_user(token, phone):
    """토큰 + 전화번호 검증"""
    user = _get_user(token)
    if not user:
        return None
    # 전화번호 마지막 4자리 또는 전체 매칭
    stored = user.get("phone","").replace("-","")
    given  = phone.replace("-","")
    if stored == given or stored.endswith(given):
        return user
    return None


# ════════════════════════════════════════════════════════
# ■ [ADMIN] 사용자 관리 (admin_mode.py → server)
# ════════════════════════════════════════════════════════

@app.route("/api/admin/users", methods=["GET"])
@require_admin_key
def admin_list_users():
    """전체 사용자 목록 조회"""
    users = _load(F_USERS, default={})
    base_url = ("https://" + request.host).rstrip("/")
    result = []
    for t, u in users.items():
        link = u.get("link") or f"{base_url}/?token={t}"
        result.append({"token": t, "link": link, **u})
    return jsonify({"users": result})

@app.route("/api/admin/users", methods=["POST"])
@require_admin_key
def admin_create_user():
    """
    사용자 등록 (관리자)
    Body: {"holder": "김은경", "phone": "01012345678"}
    Returns: {"token": "...", "link": "https://.../?token=..."}
    """
    body = request.get_json() or {}
    holder = body.get("holder","").strip()
    phone  = body.get("phone","").replace("-","").strip()
    if not holder or not phone:
        return jsonify({"error": "보유자명과 전화번호 필요"}), 400

    users = _load(F_USERS, default={})

    # 이미 존재하면 기존 토큰 반환
    for token, u in users.items():
        if u.get("holder") == holder:
            base_url = ("https://" + request.host).rstrip("/")
            link = f"{base_url}/?token={token}"
            return jsonify({
                "token": token,
                "link": link,
                "already_exists": True
            })

    # 새 토큰 생성
    token = secrets.token_urlsafe(16)
    base_url = ("https://" + request.host).rstrip("/")
    link = f"{base_url}/?token={token}"
    users[token] = {
        "holder":     holder,
        "phone":      phone,
        "link":       link,          # link 저장
        "created_at": datetime.now().isoformat(),
    }
    _save(F_USERS, users)
    return jsonify({
        "token": token,
        "link":  link,
        "holder": holder
    })

@app.route("/api/admin/users/<token>", methods=["DELETE"])
@require_admin_key
def admin_delete_user(token):
    """사용자 삭제"""
    users = _load(F_USERS, default={})
    # URL 디코딩된 토큰으로도 시도
    from urllib.parse import unquote
    token_decoded = unquote(token)
    # 정확히 일치하는 토큰 찾기
    matched = None
    for k in list(users.keys()):
        if k == token or k == token_decoded:
            matched = k
            break
    if not matched:
        return jsonify({"error": "사용자 없음"}), 404
    holder = users.pop(matched, {}).get("holder","")
    _save(F_USERS, users)
    return jsonify({"status": "ok", "deleted": holder})


@app.route("/api/auth/holder", methods=["GET"])
def get_holder_by_token():
    """토큰으로 보유자명 조회 (로그인 화면에서 이름 표시용)"""
    token = request.args.get("token","")
    user  = _get_user(token)
    if not user:
        return jsonify({"error": "없음"}), 404
    return jsonify({"holder": user.get("holder",""), "token": token})


# ════════════════════════════════════════════════════════
# ■ [PUSH] SHE → 서버
# ════════════════════════════════════════════════════════

@app.route("/api/push/holdings", methods=["POST"])
@require_push_key
def push_holdings():
    """
    SHE가 보유종목 현황 전송
    Body: {"timestamp": "...", "holdings": [{"holder":"김은경","code":"...","name":"...","qty":1,"entry_price":1000,"cur_price":1100,...}]}
    """
    data = request.get_json() or {}
    _save(F_HOLDINGS, data)
    return jsonify({"status": "ok", "count": len(data.get("holdings", []))})

@app.route("/api/push/signals", methods=["POST"])
@require_push_key
def push_signals():
    """
    SHE가 진입후보(추천종목) 전송 (17:00)
    Body: {"timestamp": "...", "date": "20260325", "signals": [...]}
    """
    data = request.get_json() or {}
    _save(F_SIGNALS, data)
    return jsonify({"status": "ok", "count": len(data.get("signals", []))})

@app.route("/api/push/lookup_result", methods=["POST"])
@require_push_key
def push_lookup_result():
    """
    SHE가 조회종목 분석결과 전송
    Body: {"code": "005930", "result": {...분석데이터...}}
    """
    data = request.get_json() or {}
    results = _load(F_LOOKUP_R, default={})
    code = data.get("code","")
    if code:
        results[code] = {
            "result":      data.get("result", {}),
            "updated_at":  datetime.now().isoformat(),
        }
        _save(F_LOOKUP_R, results)
    return jsonify({"status": "ok"})


# ════════════════════════════════════════════════════════
# ■ [PULL] 서버 → SHE (조회요청 수신)
# ════════════════════════════════════════════════════════

@app.route("/api/pull/lookup_queue", methods=["GET"])
@require_push_key
def pull_lookup_queue():
    """SHE가 조회요청 목록 가져감 (처리 후 삭제)"""
    queue = _load(F_LOOKUP_Q, default={"queue": []})
    items = queue.get("queue", [])
    _save(F_LOOKUP_Q, {"queue": []})
    return jsonify({"queue": items})


# ════════════════════════════════════════════════════════
# ■ [CLIENT] 사용자 인증
# ════════════════════════════════════════════════════════

@app.route("/api/auth/verify", methods=["POST"])
def auth_verify():
    """
    전화번호로 본인 확인
    Body: {"token": "...", "phone": "01012345678"}
    """
    body  = request.get_json() or {}
    token = body.get("token","")
    phone = body.get("phone","")
    user  = _verify_user(token, phone)
    if not user:
        return jsonify({"error": "인증 실패"}), 401
    return jsonify({
        "status": "ok",
        "holder": user["holder"],
        "token":  token
    })


# ════════════════════════════════════════════════════════
# ■ [CLIENT] 보유종목 조회
# ════════════════════════════════════════════════════════

@app.route("/api/holdings", methods=["GET"])
def get_holdings():
    """
    본인 보유종목 조회
    Query: token=xxx&phone=01012345678
    """
    token = request.args.get("token","")
    phone = request.args.get("phone","")
    user  = _verify_user(token, phone)
    if not user:
        return jsonify({"error": "인증 실패"}), 401

    holder = user["holder"]
    data   = _load(F_HOLDINGS, default={"holdings": [], "timestamp": ""})
    all_h  = data.get("holdings", [])

    # 본인 것만 필터
    mine = [h for h in all_h if h.get("holder","") == holder]

    # 합계 계산
    total_entry  = sum(h.get("entry_price",0) * h.get("qty",0) for h in mine)
    total_eval   = sum(h.get("cur_price",0)   * h.get("qty",0) for h in mine)
    total_profit = total_eval - total_entry
    total_pct    = round(total_profit / total_entry * 100, 2) if total_entry > 0 else 0.0

    return jsonify({
        "holder":       holder,
        "holdings":     mine,
        "summary": {
            "total_entry":  total_entry,
            "total_eval":   total_eval,
            "total_profit": total_profit,
            "total_pct":    total_pct,
            "count":        len(mine),
        },
        "timestamp": data.get("timestamp",""),
    })


# ════════════════════════════════════════════════════════
# ■ [CLIENT] 추천종목 조회
# ════════════════════════════════════════════════════════

@app.route("/api/signals", methods=["GET"])
def get_signals():
    """진입후보(추천종목) 조회 — TOP10, 순번/칼마/한글지표명 포함"""
    token = request.args.get("token","")
    phone = request.args.get("phone","")
    if not _verify_user(token, phone):
        return jsonify({"error": "인증 실패"}), 401

    data    = _load(F_SIGNALS, default={"signals": [], "date": "", "timestamp": ""})
    sigs    = data.get("signals", [])

    # 칼마 순 정렬 → TOP10
    sigs.sort(key=lambda x: x.get("rank", 999))
    top10 = sigs[:10]

    # 한글 지표명 변환
    result = []
    for s in top10:
        fired    = s.get("all_signals", s.get("signals_raw", []))
        fired_kr = [_sig_kr(sg) for sg in fired]
        result.append({
            **s,
            "rank":       s.get("rank", ""),
            "name":       s.get("name", s.get("code","")),
            "calmar":     round(float(s.get("calmar_rank", s.get("calmar", 0))), 0),
            "signal_type_kr": _sig_kr(s.get("signal_type","")),
            "signals_kr": fired_kr,
            "signals_raw": fired,
        })

    return jsonify({
        "date":      data.get("date",""),
        "timestamp": data.get("timestamp",""),
        "count":     len(result),
        "signals":   result,
    })


# ════════════════════════════════════════════════════════
# ■ [CLIENT] 조회종목 요청 / 결과 조회
# ════════════════════════════════════════════════════════

@app.route("/api/lookup/request", methods=["POST"])
def lookup_request():
    """
    조회종목 분석 요청
    Body: {"token":"...","phone":"...","code":"005930","name":"삼성전자"}
    """
    body  = request.get_json() or {}
    token = body.get("token","")
    phone = body.get("phone","")
    if not _verify_user(token, phone):
        return jsonify({"error": "인증 실패"}), 401

    code = body.get("code","").strip().zfill(6)
    name = body.get("name","").strip()
    if not code or code == "000000":
        return jsonify({"error": "종목코드 필요"}), 400

    # 큐에 추가 (중복 제거)
    queue = _load(F_LOOKUP_Q, default={"queue": []})
    items = queue.get("queue", [])
    codes = [q["code"] for q in items]
    if code not in codes:
        items.append({
            "code": code, "name": name,
            "requested_at": datetime.now().isoformat(),
            "token": token,
        })
        _save(F_LOOKUP_Q, {"queue": items})

    return jsonify({"status": "ok", "message": f"{name}({code}) 분석 요청됨 (잠시 후 결과 확인)"})

@app.route("/api/lookup/result", methods=["GET"])
def lookup_result():
    """
    조회종목 분석결과 조회
    Query: token=xxx&phone=xxx&code=005930
    """
    token = request.args.get("token","")
    phone = request.args.get("phone","")
    if not _verify_user(token, phone):
        return jsonify({"error": "인증 실패"}), 401

    code    = request.args.get("code","").strip().zfill(6)
    results = _load(F_LOOKUP_R, default={})
    item    = results.get(code)
    if not item:
        return jsonify({"status": "pending", "message": "분석 대기 중..."})

    return jsonify({"status": "ready", "code": code, **item})


# ════════════════════════════════════════════════════════
# ■ [PNL] 손익 장부 (관리자 전용)
# ════════════════════════════════════════════════════════

@app.route("/api/push/pnl", methods=["POST"])
@require_push_key
def push_pnl():
    """
    SHE가 손익 장부 레코드 전송 (청산 발생 시 또는 자본 변동 시)
    Body: {
      "date": "2026-04-02",
      "투자원금": 0, "입금": 0, "출금": 0,
      "매입": 267100, "청산": 264150,
      "수수료": 80, "세금": 475,
      "메모": "씨에스윈드TRAIL/HDC SL",
      "transactions": []
    }
    id = date + 수신시각 밀리초로 자동 부여 (같은 날 복수 청산 지원)
    """
    data = request.get_json() or {}
    pnl  = _load(F_PNL, default={"records": []})
    recs = pnl.get("records", [])

    # id 자동 부여 (날짜+타임스탬프 밀리초)
    ts   = datetime.now()
    rid  = f"r_{ts.strftime('%Y%m%d%H%M%S%f')[:17]}"
    rec  = {
        "id":       rid,
        "date":     data.get("date", ts.strftime("%Y-%m-%d")),
        "투자원금": int(data.get("투자원금", 0) or 0),
        "입금":     int(data.get("입금", 0) or 0),
        "출금":     int(data.get("출금", 0) or 0),
        "매입":     int(data.get("매입", 0) or 0),
        "청산":     int(data.get("청산", 0) or 0),
        "수수료":   int(data.get("수수료", 0) or 0),
        "세금":     int(data.get("세금", 0) or 0),
        "메모":     data.get("메모", ""),
        "transactions": data.get("transactions", []),
        "created_at":   ts.isoformat(),
    }
    # 같은 id 중복 방지 (재전송 등)
    recs = [r for r in recs if r.get("id") != rid]
    recs.append(rec)
    # 날짜 오름차순 정렬
    recs.sort(key=lambda r: (r.get("date",""), r.get("created_at","")))
    _save(F_PNL, {"records": recs, "updated_at": ts.isoformat()})
    return jsonify({"status": "ok", "id": rid})


@app.route("/api/pnl/ledger", methods=["GET"])
def pnl_ledger():
    """
    손익 장부 조회 (관리자 인증 필요)
    Query: token=xxx&phone=xxx
    """
    token = request.args.get("token", "")
    phone = request.args.get("phone", "")
    user  = _verify_user(token, phone)
    if not user:
        return jsonify({"error": "인증 실패"}), 401
    # 관리자 여부 확인
    holder = user.get("holder", "")
    if not any(n in holder for n in ["관리자", "박상규", "상규"]):
        return jsonify({"error": "관리자 전용"}), 403
    pnl = _load(F_PNL, default={"records": []})
    return jsonify(pnl)


# ════════════════════════════════════════════════════════
# ■ [VIRTUAL] 가상 포트폴리오 (관리자 전용)
# ════════════════════════════════════════════════════════

@app.route("/api/push/virtual", methods=["POST"])
@require_push_key
def push_virtual():
    """
    SHE가 가상포트폴리오 데이터 전송 (17:00 신호스캔 후)
    Body: {"date": "20260402", "entries": [...]}
    entries 는 전체를 덮어쓰지 않고 id 기준 upsert
    """
    data    = request.get_json() or {}
    entries = data.get("entries", [])
    vdata   = _load(F_VIRTUAL, default={"entries": {}})
    tbl     = vdata.get("entries", {})
    for e in entries:
        eid = e.get("id", "")
        if eid:
            tbl[eid] = e
    vdata["entries"]    = tbl
    vdata["updated_at"] = datetime.now().isoformat()
    _save(F_VIRTUAL, vdata)
    return jsonify({"status": "ok", "count": len(entries)})


@app.route("/api/virtual/query", methods=["GET"])
@require_admin_key
def virtual_query():
    """
    가상포트폴리오 조회 (관리자 전용)
    Query params:
      date=YYYYMMDD  → 해당 날짜 진입 종목 + 해당 날짜 보유 중인 종목 모두
      code=XXXXXX    → 해당 종목의 모든 가상진입 이력
    응답: D+3 최고 수익률 종목이 맨 앞
    """
    vdata   = _load(F_VIRTUAL, default={"entries": {}})
    tbl     = vdata.get("entries", {})
    all_e   = list(tbl.values())

    date_q  = request.args.get("date", "").strip()
    code_q  = request.args.get("code", "").strip().zfill(6)

    if date_q:
        result = []
        for e in all_e:
            edate = e.get("entry_date", "")
            # 진입일 일치
            if edate == date_q:
                result.append({**e, "_match": "진입일"})
                continue
            # 해당일이 D+1~D+9 보유기간 내인지 확인
            dr = e.get("d_results", {})
            for dk, dv in dr.items():
                if dv.get("date", "") == date_q:
                    result.append({**e, "_match": f"{dk} 보유중"})
                    break
    elif code_q and code_q != "000000":
        result = [e for e in all_e if e.get("code", "") == code_q]
    else:
        result = all_e

    # D+3~D+9 중 최고 수익률 기준 내림차순 정렬
    def _best_pct(e):
        dr = e.get("d_results", {})
        if not dr: return -9999
        return max((v.get("pnl_pct", -9999) for v in dr.values()), default=-9999)

    result.sort(key=_best_pct, reverse=True)
    return jsonify({"count": len(result), "entries": result,
                    "updated_at": vdata.get("updated_at", "")})


# ════════════════════════════════════════════════════════
# ■ 헬스체크 + index.html 서빙
# ════════════════════════════════════════════════════════

@app.route("/api/name", methods=["GET"])
def get_stock_name():
    """종목코드 → 종목명 조회 (signals → holdings → virtual → pnl 순 탐색)"""
    code = request.args.get("code", "").strip().zfill(6)
    if not code or code == "000000":
        return jsonify({"code": code, "name": ""})
    name = ""
    # 1. signals
    try:
        for s in _load(F_SIGNALS, default={}).get("signals", []):
            if s.get("code") == code:
                name = s.get("name", ""); break
    except Exception: pass
    # 2. holdings
    if not name:
        try:
            for h in _load(F_HOLDINGS, default={}).get("holdings", []):
                if h.get("code") == code:
                    name = h.get("name", ""); break
        except Exception: pass
    # 3. virtual_portfolio
    if not name:
        try:
            for entries in _load(F_VIRTUAL, default={}).values():
                if isinstance(entries, list):
                    for e in entries:
                        if e.get("code") == code:
                            name = e.get("name", ""); break
                if name: break
        except Exception: pass
    # 4. pnl_ledger
    if not name:
        try:
            for e in _load(F_PNL, default={}).get("entries", []):
                if e.get("code") == code:
                    name = e.get("name", ""); break
        except Exception: pass
    return jsonify({"code": code, "name": name})


@app.route("/health")
def health():
    users = _load(F_USERS, default={})
    return jsonify({
        "status": "ok",
        "time": datetime.now().isoformat(),
        "version": "SHE-1.0",
        "data_dir": str(DATA_DIR),
        "users_count": len(users),
        "users_file_exists": F_USERS.exists(),
    })

@app.route("/")
def index():
    return send_from_directory(".", "index.html")

@app.route("/<path:path>")
def static_files(path):
    return send_from_directory(".", path)


if __name__ == "__main__":
    print(f"SHE 보유자 앱 서버 시작 — 포트: {PORT}")
    app.run(host="0.0.0.0", port=PORT, debug=False)
