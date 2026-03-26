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

DATA_DIR = Path(os.environ.get("RAILWAY_VOLUME_MOUNT_PATH", "")) / "data" \
           if os.environ.get("RAILWAY_VOLUME_MOUNT_PATH") \
           else Path("data")
DATA_DIR.mkdir(exist_ok=True, parents=True)

# 데이터 파일
F_USERS     = DATA_DIR / "users.json"         # 사용자 목록 {token: {holder, phone, ...}}
F_HOLDINGS  = DATA_DIR / "holdings.json"      # SHE → Push (holder별 보유종목)
F_SIGNALS   = DATA_DIR / "signals.json"       # SHE → Push (17:00 진입후보)
F_LOOKUP_Q  = DATA_DIR / "lookup_queue.json"  # 사용자 → 조회요청
F_LOOKUP_R  = DATA_DIR / "lookup_results.json"# SHE → 조회결과

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
    """진입후보(추천종목) 조회 — 인증 필요"""
    token = request.args.get("token","")
    phone = request.args.get("phone","")
    if not _verify_user(token, phone):
        return jsonify({"error": "인증 실패"}), 401

    data = _load(F_SIGNALS, default={"signals": [], "date": "", "timestamp": ""})
    return jsonify(data)


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
# ■ 헬스체크 + index.html 서빙
# ════════════════════════════════════════════════════════

@app.route("/health")
def health():
    return jsonify({"status": "ok", "time": datetime.now().isoformat(), "version": "SHE-1.0"})

@app.route("/")
def index():
    return send_from_directory(".", "index.html")

@app.route("/<path:path>")
def static_files(path):
    return send_from_directory(".", path)


if __name__ == "__main__":
    print(f"SHE 보유자 앱 서버 시작 — 포트: {PORT}")
    app.run(host="0.0.0.0", port=PORT, debug=False)
