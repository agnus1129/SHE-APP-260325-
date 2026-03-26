# -*- coding: utf-8 -*-
"""
admin/admin_mode.py — ATSRS 관리자 모드
────────────────────────────────────────────────────────────
탭 구성:
  1. 직접관리종목  - 손익절/자동매매 배제, 보유자 관리
  2. 의뢰관리종목  - 외부 보유자 종목 기록
  3. 신저가종목    - 52주 신저가 자동 수집
  4. 관심종목      - 직접 입력 관리

공통 기능:
  - 종목별 분석 버튼 (74개 지표 + 추세 + 신호)
  - 탭 전체 분석 버튼
  - CRUD (추가/수정/삭제)
  - 컬럼 클릭 정렬
  - 현재가/평가금액/수익률 실시간 표시
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QTabWidget, QWidget, QVBoxLayout,
    QHBoxLayout, QPushButton, QTableWidget, QTableWidgetItem,
    QHeaderView, QLabel, QLineEdit, QComboBox, QDialog,
    QFormLayout, QDialogButtonBox, QMessageBox, QSpinBox,
    QFrame, QSplitter, QTextEdit, QProgressBar, QMenu,
    QAction
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt5.QtGui import QColor, QFont
from datetime import datetime
import threading

# DB 함수
from data.trade_db import (
    get_direct, add_direct, upd_direct, del_direct,
    get_consign, add_consign, upd_consign, del_consign,
    get_newlow, add_newlow, upd_newlow, del_newlow,
    get_watchlist, add_watchlist, upd_watchlist, del_watchlist,
)

# ── 색상 상수 ─────────────────────────────────────────────
C_BG       = "#1e1e2e"
C_PANEL    = "#2a2a3e"
C_BTN      = "#4f6bed"
C_BTN_RED  = "#e84040"
C_BTN_GRN  = "#40b040"
C_BTN_YLW  = "#e0a020"
C_TEXT     = "#e0e0f0"
C_HEADER   = "#3a3a5e"
C_SEL      = "#5050a0"
C_PROFIT   = "#40e040"
C_LOSS     = "#e04040"

STYLE_MAIN = f"""
QMainWindow, QWidget {{ background: {C_BG}; color: {C_TEXT};
                        font-size: 16px; font-weight: bold; }}
QTabWidget::pane {{ border: 1px solid #444; }}
QTabBar::tab {{ background: {C_PANEL}; color: {C_TEXT};
                padding: 10px 24px; font-size: 16px; font-weight: bold; }}
QTabBar::tab:selected {{ background: {C_BTN}; color: white; font-weight: bold; }}
QTableWidget {{ background: {C_PANEL}; gridline-color: #444;
                color: {C_TEXT}; font-size: 16px; font-weight: bold; }}
QTableWidget::item {{ padding: 6px; }}
QTableWidget::item:selected {{ background: {C_SEL}; }}
QHeaderView::section {{ background: {C_HEADER}; color: {C_TEXT};
                         padding: 8px; border: 1px solid #555;
                         font-size: 16px; font-weight: bold; }}
QPushButton {{ background: {C_BTN}; color: white; border: none;
               padding: 8px 16px; border-radius: 4px;
               font-size: 16px; font-weight: bold; }}
QPushButton:hover {{ background: #6070ff; }}
QPushButton.red {{ background: {C_BTN_RED}; }}
QPushButton.green {{ background: {C_BTN_GRN}; }}
QPushButton.yellow {{ background: {C_BTN_YLW}; color: black; }}
QLineEdit, QSpinBox, QComboBox {{
    background: #333355; color: {C_TEXT}; border: 1px solid #555;
    padding: 6px; border-radius: 3px;
    font-size: 16px; font-weight: bold; }}
QLabel {{ color: {C_TEXT}; font-size: 16px; font-weight: bold; }}
QTextEdit {{ background: {C_PANEL}; color: {C_TEXT}; border: 1px solid #444;
             font-size: 16px; font-weight: bold; }}
QMessageBox {{ font-size: 16px; font-weight: bold; }}
QMessageBox QLabel {{ font-size: 16px; font-weight: bold; }}
QDialog {{ font-size: 16px; font-weight: bold; }}
"""

# ══════════════════════════════════════════════════════════
# 현재가 전용 워커 — premium_data.db에서 일괄 조회
class PriceWorker(QThread):
    done = pyqtSignal(dict)  # {code: price}

    def __init__(self, codes: list):
        super().__init__()
        self.codes = codes

    def run(self):
        import sqlite3, os, sys
        result = {}
        try:
            _base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            # premium_data.db 조회
            for _dbname in ["premium_data.db", "candle_cache.db"]:
                _pdb = os.path.join(_base, "data", _dbname)
                if not os.path.exists(_pdb):
                    # IDSRS candle_cache.db도 시도
                    _idsrs = r"D:\vom project(260317)\IDSRS-자동매매시그널 우선 적용(260305)\data"
                    _pdb = os.path.join(_idsrs, _dbname)
                if os.path.exists(_pdb):
                    c = sqlite3.connect(_pdb, timeout=10)
                    for code in self.codes:
                        if code in result: continue
                        row = c.execute(
                            "SELECT close FROM daily_candles WHERE code=? ORDER BY date DESC LIMIT 1",
                            (code,)).fetchone()
                        if row and row[0]:
                            result[code] = abs(int(row[0]))
                    c.close()
        except Exception as e:
            pass
        # 장중 REST 보완
        try:
            from core.kiwoom_rest import kiwoom
            import datetime
            h = datetime.datetime.now().hour
            if 9 <= h <= 15:
                for code in self.codes:
                    try:
                        p = kiwoom.get_current_price(code)
                        if p: result[code] = p
                    except: pass
        except: pass
        self.done.emit(result)

# 분석 워커 스레드
class AnalysisWorker(QThread):
    done    = pyqtSignal(str, dict)   # (code, result)
    progress= pyqtSignal(int, int)    # (done, total)

    def __init__(self, codes: list):
        super().__init__()
        self.codes = codes

    def run(self):
        import os, sys
        from core.kiwoom_rest import kiwoom
        from data.db_manager import get_daily

        # IndicatorEngine 초기화
        _ind_dir  = os.path.join(os.path.dirname(os.path.dirname(__file__)), "indicators")
        _map_path = os.path.join(_ind_dir, "indicators_map.json")
        _engine   = None
        _engine_err = ""
        try:
            if _ind_dir not in sys.path:
                sys.path.insert(0, _ind_dir)
            from engine import IndicatorEngine
            if os.path.exists(_map_path):
                _engine = IndicatorEngine(config_path=_map_path)
            else:
                raise FileNotFoundError(f"indicators_map.json 없음: {_map_path}")
        except Exception as _init_err:
            _engine_err = str(_init_err)

        results = {}
        for i, code in enumerate(self.codes):
            try:
                # 현재가 — REST → premium_data.db → trade.db 순서로 fallback
                price = kiwoom.get_current_price(code) or 0
                if not price:
                    try:
                        import sqlite3 as _sq, os as _os
                        _pdb = _os.path.join(_os.path.dirname(_os.path.dirname(__file__)), "data", "premium_data.db")
                        if _os.path.exists(_pdb):
                            _c = _sq.connect(_pdb, timeout=5)
                            _row = _c.execute(
                                "SELECT close FROM daily_candles WHERE code=? ORDER BY date DESC LIMIT 1",
                                (code,)).fetchone()
                            _c.close()
                            if _row and _row[0]:
                                price = abs(int(_row[0]))
                    except:
                        pass
                if not price:
                    try:
                        rows_tmp = get_daily(code, limit=1)
                        price = abs(int(rows_tmp[0].get("close", 0))) if rows_tmp else 0
                    except:
                        price = 0

                # 일봉 캔들 로드 (premium_data.db, REST 기반)
                rows = get_daily(code, limit=300)
                candles = list(reversed([{
                    "open":   r["open"],  "high": r["high"],
                    "low":    r["low"],   "close": r["close"],
                    "volume": r["volume"],
                } for r in rows if r.get("close", 0) > 0]))

                # 장마감 후 현재가 0이면 최근 종가 사용
                if (not price or price == 0) and candles:
                    price = candles[-1]["close"]

                # 74개 지표 분석
                indian_result = None
                if _engine and len(candles) >= 60:
                    try:
                        indian_result = _engine.analyze_stock(code, candles)
                    except Exception as _e2:
                        indian_result = {"error": str(_e2)}

                from strategy.signal_engine import signal_eng
                sig = signal_eng.scan_general(code)

                date_from = rows[-1].get("date","") if rows else ""
                date_to   = rows[0].get("date","") if rows else ""
                def _fmt(d):
                    d = str(d)
                    return f"{d[:4]}-{d[4:6]}-{d[6:8]}" if len(d)==8 else d
                results[code] = {
                    "cur_price":    price,
                    "signal":       sig,
                    "indian":       indian_result,
                    "candle_count": len(candles),
                    "candle_range": f"{_fmt(date_from)}~{_fmt(date_to)}",
                    "engine_err":   _engine_err,
                }
                self.done.emit(code, results[code])
            except Exception as e:
                self.done.emit(code, {"error": str(e)})
            self.progress.emit(i+1, len(self.codes))

# ══════════════════════════════════════════════════════════
# 종목 입력 다이얼로그
class StockDialog(QDialog):
    def __init__(self, parent=None, data=None, tab_type="direct"):
        super().__init__(parent)
        self.tab_type = tab_type
        self.setWindowTitle("종목 입력" if not data else "종목 수정")
        self.setMinimumWidth(400)
        self.setStyleSheet(f"background:{C_BG}; color:{C_TEXT};")

        layout = QFormLayout(self)

        self.f_code  = QLineEdit(data.get("code","") if data else "")
        self.f_name  = QLineEdit(data.get("name","") if data else "")
        self.f_holder= QLineEdit(data.get("holder","") if data else "")
        self.f_qty   = QSpinBox(); self.f_qty.setRange(0,9999999)
        self.f_qty.setValue(data.get("qty",0) if data else 0)
        self.f_price = QSpinBox(); self.f_price.setRange(0,9999999)
        self.f_price.setValue(data.get("entry_price",0) if data else 0)
        self.f_note  = QLineEdit(data.get("note","") if data else "")

        layout.addRow("종목코드*:", self.f_code)
        layout.addRow("종목명:",    self.f_name)
        if tab_type in ("direct", "consign"):
            layout.addRow("보유자:",    self.f_holder)
            layout.addRow("수량:",      self.f_qty)
            layout.addRow("진입가(원):", self.f_price)
        layout.addRow("메모:",      self.f_note)

        btns = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addRow(btns)

    def get_data(self) -> dict:
        d = {
            "code":        self.f_code.text().strip().zfill(6),
            "name":        self.f_name.text().strip(),
            "holder":      self.f_holder.text().strip(),
            "qty":         self.f_qty.value(),
            "entry_price": self.f_price.value(),
            "note":        self.f_note.text().strip(),
        }
        # tab_type에 따라 필드 필터
        if self.tab_type in ("newlow","watchlist"):
            d.pop("holder",""); d.pop("qty",""); d.pop("entry_price","")
        return d

# ══════════════════════════════════════════════════════════
# 분석 결과 표시 창
class AnalysisDialog(QDialog):
    def __init__(self, code: str, name: str, result: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"분석: {name}({code})")
        self.setMinimumSize(700, 500)
        self.setStyleSheet(f"background:{C_BG}; color:{C_TEXT};")

        layout = QVBoxLayout(self)
        text = QTextEdit()
        text.setReadOnly(True)

        # SHE 공통 헤더
        _she_hdr = ""
        try:
            import sys as _sys, os as _os
            _base = _os.path.dirname(_os.path.dirname(__file__))
            if _base not in _sys.path: _sys.path.insert(0, _base)
            from data.db_manager import get_daily as _gd
            import pandas as _pd
            _rows = _gd(code, limit=300)
            if _rows:
                _dc = _pd.DataFrame(_rows)
                for _c in ["open","high","low","close","volume"]:
                    _dc[_c] = _pd.to_numeric(_dc[_c], errors="coerce")
                _dc = _dc[_dc["close"]>0].sort_values("date").reset_index(drop=True)
                from indicators.trend_classifier import get_stock_header
                _h = get_stock_header(_dc, code=code, name=name)
                _she_hdr = _h.get("header_text","") + "\n" + _h.get("header_sep","─"*38) + "\n"
        except:
            pass
        content = _she_hdr
        content += f"═══════════════════════════════════════\n"
        content += f"  {name} ({code}) 분석 결과\n"
        content += f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        content += f"═══════════════════════════════════════\n\n"

        if "error" in result:
            content += f"❌ 오류: {result['error']}\n"
        else:
            cur = result.get("cur_price", 0)
            sig = result.get("signal")
            indian = result.get("indian")
            candle_range = result.get("candle_range", "")
            candle_cnt   = result.get("candle_count", 0)
            content += f"현재가: {cur:,}원  |  캔들: {candle_cnt}일 ({candle_range})\n\n"

            # ── SHE 진입신호 ──
            content += "【SHE 진입신호】\n"
            if sig:
                content += f"  추세:  {sig.get('trend','')} / 전환: {sig.get('trend_c','')}\n"
                content += f"  CCW:   {sig.get('ccw','')}\n"
                content += f"  히스트: {'✅' if sig.get('hist_up') else '❌'}\n"
                content += f"  등급:  [{sig.get('grade','')}]  신호: {sig.get('signal_type','')}\n"
            else:
                content += "  신호 없음\n"

            content += "\n"

            # ── IndiAn 74개 지표 분석 ──
            if indian and "error" not in indian:
                try:
                    import os as _os, sys as _sys
                    _ind_dir  = _os.path.join(_os.path.dirname(_os.path.dirname(__file__)), "indicators")
                    _map_path = _os.path.join(_ind_dir, "indicators_map.json")
                    if _ind_dir not in _sys.path:
                        _sys.path.insert(0, _ind_dir)
                    from engine import IndicatorEngine as _IE
                    _eng = _IE(config_path=_map_path)
                    content += _eng.format_result(indian)
                except Exception as _fe:
                    content += f"【IndiAn 분석 포맷 오류】\n  {_fe}\n"
            elif indian and "error" in indian:
                content += f"【IndiAn 분석 오류】\n  {indian['error']}\n"
            else:
                content += "【IndiAn 분석】\n  데이터 부족 또는 모듈 미연동\n"

        text.setPlainText(content)
        layout.addWidget(text)

        close_btn = QPushButton("닫기")
        close_btn.clicked.connect(self.close)
        layout.addWidget(close_btn)

# ══════════════════════════════════════════════════════════
# 공통 종목 탭 위젯
class StockTab(QWidget):
    """4개 탭에서 공통으로 사용하는 베이스 위젯"""

    def __init__(self, tab_type: str, columns: list,
                 get_fn, add_fn, upd_fn, del_fn,
                 parent=None):
        super().__init__(parent)
        self.tab_type = tab_type
        self.columns  = columns
        self.get_fn   = get_fn
        self.add_fn   = add_fn
        self.upd_fn   = upd_fn
        self.del_fn   = del_fn
        self._sort_col = 0
        self._sort_asc = True
        self._data     = []

        self._build_ui()
        self.refresh()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5,5,5,5)
        layout.setSpacing(5)

        # ── 상단 버튼 바 ──
        top = QHBoxLayout()

        btn_add   = QPushButton("➕ 추가")
        btn_edit  = QPushButton("✏️ 수정")
        btn_del   = QPushButton("🗑️ 삭제")
        btn_anal  = QPushButton("📊 전체 분석")
        btn_ref   = QPushButton("🔄 새로고침")

        btn_del.setProperty("class","red")
        btn_anal.setProperty("class","green")

        btn_add.clicked.connect(self._add_row)
        btn_edit.clicked.connect(self._edit_row)
        btn_del.clicked.connect(self._del_row)
        btn_anal.clicked.connect(self._analyze_all)
        btn_ref.clicked.connect(self.refresh)

        for b in [btn_add, btn_edit, btn_del, btn_anal, btn_ref]:
            top.addWidget(b)
        top.addStretch()

        # 진행바
        self.progress = QProgressBar()
        self.progress.setVisible(False)
        self.progress.setMaximumHeight(16)
        top.addWidget(self.progress)

        self._top_layout = top          # 서브클래스에서 버튼 추가 가능하도록 저장
        layout.addLayout(top)

        # ── 검색 바 ──
        search_bar = QHBoxLayout()
        search_bar.addWidget(QLabel("🔍 검색:"))
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("종목명 또는 코드 검색...")
        self.search_edit.textChanged.connect(self.refresh)
        search_bar.addWidget(self.search_edit)
        layout.addLayout(search_bar)

        # ── 테이블 ──
        col_labels = [c["label"] for c in self.columns] + ["현재가","평가금액","수익률","분석"]
        self.table = QTableWidget(0, len(col_labels))
        self.table.setHorizontalHeaderLabels(col_labels)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.table.horizontalHeader().setStretchLastSection(False)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(False)
        self.table.setSortingEnabled(False)  # 수동 정렬
        self.table.horizontalHeader().sectionClicked.connect(self._sort_by_col)
        self.table.doubleClicked.connect(self._edit_row)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._context_menu)

        # Delete 키 단축키
        self.table.keyPressEvent = self._key_press

        layout.addWidget(self.table)

        # ── 하단 상태바 ──
        self.status_label = QLabel("총 0종목")
        layout.addWidget(self.status_label)

    def _key_press(self, event):
        if event.key() == Qt.Key_Delete:
            self._del_row()
        else:
            QTableWidget.keyPressEvent(self.table, event)

    def _context_menu(self, pos):
        menu = QMenu(self)
        act_edit = QAction("✏️ 수정", self)
        act_del  = QAction("🗑️ 삭제", self)
        act_anal = QAction("📊 분석", self)
        act_edit.triggered.connect(self._edit_row)
        act_del.triggered.connect(self._del_row)
        act_anal.triggered.connect(self._analyze_selected)
        menu.addAction(act_edit)
        menu.addAction(act_del)
        menu.addSeparator()
        menu.addAction(act_anal)
        menu.exec_(self.table.viewport().mapToGlobal(pos))

    def refresh(self):
        self._data = self.get_fn()
        q = self.search_edit.text().strip().lower()
        if q:
            self._data = [r for r in self._data
                          if q in str(r.get("name","")).lower()
                          or q in str(r.get("code","")).lower()]
        self._render()
        # 렌더 후 현재가 자동 업데이트
        if self._data:
            self.refresh_prices()

    def _render(self):
        self.table.setRowCount(0)
        for row_data in self._data:
            r = self.table.rowCount()
            self.table.insertRow(r)
            # 데이터 컬럼
            for c_idx, col in enumerate(self.columns):
                val = row_data.get(col["key"], "")
                item = QTableWidgetItem(str(val) if val is not None else "")
                item.setData(Qt.UserRole, row_data.get("id"))
                if col.get("align") == "right":
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.table.setItem(r, c_idx, item)

            n = len(self.columns)
            # 현재가 (빈칸 — 새로고침 시 채움)
            self.table.setItem(r, n,   QTableWidgetItem(""))
            self.table.setItem(r, n+1, QTableWidgetItem(""))
            self.table.setItem(r, n+2, QTableWidgetItem(""))

            # 분석 버튼
            btn = QPushButton("분석")
            btn.setMaximumHeight(24)
            code = row_data.get("code","")
            name = row_data.get("name","")
            btn.clicked.connect(lambda _, c=code, n=name: self._analyze_one(c, n))
            self.table.setCellWidget(r, n+3, btn)

        self.table.verticalHeader().setDefaultSectionSize(36)
        self.status_label.setText(f"총 {len(self._data)}종목")

    def _sort_by_col(self, col_idx: int):
        if self._sort_col == col_idx:
            self._sort_asc = not self._sort_asc
        else:
            self._sort_col = col_idx
            self._sort_asc = True
        if col_idx < len(self.columns):
            key = self.columns[col_idx]["key"]
            self._data.sort(
                key=lambda x: str(x.get(key,"")),
                reverse=not self._sort_asc)
            self._render()

    def _get_selected_id(self):
        row = self.table.currentRow()
        if row < 0: return None, None
        item = self.table.item(row, 0)
        if not item: return None, None
        return item.data(Qt.UserRole), row

    def _add_row(self):
        dlg = StockDialog(self, tab_type=self.tab_type)
        if dlg.exec_() == QDialog.Accepted:
            d = dlg.get_data()
            if not d.get("code"):
                QMessageBox.warning(self, "오류", "종목코드를 입력하세요.")
                return
            try:
                self.add_fn(d)
                self.refresh()
            except Exception as e:
                QMessageBox.warning(self, "오류", f"저장 실패: {e}")

    def _edit_row(self):
        row_id, row = self._get_selected_id()
        if row_id is None:
            QMessageBox.information(self, "알림", "수정할 항목을 선택하세요.")
            return
        # 현재 데이터 찾기
        cur_data = next((r for r in self._data
                         if r.get("id") == row_id), None)
        dlg = StockDialog(self, data=cur_data, tab_type=self.tab_type)
        if dlg.exec_() == QDialog.Accepted:
            self.upd_fn(row_id, dlg.get_data())
            self.refresh()

    def _del_row(self):
        row_id, _ = self._get_selected_id()
        if row_id is None:
            QMessageBox.information(self, "알림", "삭제할 항목을 선택하세요.")
            return
        ans = QMessageBox.question(self, "삭제 확인",
                                   "선택한 항목을 삭제하시겠습니까?",
                                   QMessageBox.Yes | QMessageBox.No)
        if ans == QMessageBox.Yes:
            self.del_fn(row_id)
            self.refresh()

    def refresh_prices(self):
        """현재가만 빠르게 업데이트 (중복 실행 방지)"""
        if hasattr(self, "_price_worker") and self._price_worker.isRunning():
            return
        codes = [r.get("code","") for r in self._data if r.get("code")]
        if not codes: return
        self._price_worker = PriceWorker(codes)
        self._price_worker.done.connect(self._apply_prices)
        self._price_worker.start()

    def _apply_prices(self, price_map: dict):
        """현재가 일괄 적용 — DB cur_price 우선, 없으면 price_map 사용"""
        for r in range(self.table.rowCount()):
            item = self.table.item(r, 0)
            if not item: continue
            row_id = item.data(Qt.UserRole)
            row_data = next((d for d in self._data if d.get("id") == row_id), None)
            if not row_data: continue
            code  = row_data.get("code","")
            # DB cur_price 우선, 없으면 PriceWorker 결과 사용
            db_cur = row_data.get("cur_price", 0) or 0
            cur    = db_cur if db_cur > 0 else price_map.get(code, 0)
            qty    = row_data.get("qty", 0) or 0
            entry  = row_data.get("entry_price", 0) or 0
            n = len(self.columns)
            if cur:
                cur_item = QTableWidgetItem(f"{cur:,}")
                cur_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.table.setItem(r, n, cur_item)
                if qty:
                    evlt = cur * qty
                    evlt_item = QTableWidgetItem(f"{evlt:,}")
                    evlt_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                    self.table.setItem(r, n+1, evlt_item)
                if entry > 0:
                    pct = (cur - entry) / entry * 100
                    pct_item = QTableWidgetItem(f"{pct:+.2f}%")
                    pct_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                    pct_item.setForeground(QColor(C_PROFIT) if pct >= 0 else QColor(C_LOSS))
                    self.table.setItem(r, n+2, pct_item)

    def _analyze_one(self, code: str, name: str):
        """단일 종목 분석"""
        self.progress.setVisible(True)
        self.progress.setRange(0, 1)
        self.progress.setValue(0)

        self._worker = AnalysisWorker([code])
        self._worker.done.connect(
            lambda c, r: self._show_analysis(c, name, r))
        self._worker.progress.connect(
            lambda d, t: self.progress.setValue(d))
        self._worker.finished.connect(
            lambda: self.progress.setVisible(False))
        self._worker.start()

    def _analyze_selected(self):
        row_id, row = self._get_selected_id()
        if row_id is None: return
        cur = next((r for r in self._data if r.get("id") == row_id), None)
        if cur:
            self._analyze_one(cur.get("code",""), cur.get("name",""))

    def _analyze_all(self):
        """탭 전체 종목 분석"""
        if not self._data:
            QMessageBox.information(self, "알림", "분석할 종목이 없습니다.")
            return
        codes = [r.get("code","") for r in self._data if r.get("code")]
        self.progress.setVisible(True)
        self.progress.setRange(0, len(codes))
        self.progress.setValue(0)

        self._all_results = {}
        self._worker = AnalysisWorker(codes)
        self._worker.done.connect(self._on_analysis_done)
        self._worker.progress.connect(self.progress.setValue)
        self._worker.finished.connect(self._show_all_analysis)
        self._worker.start()

    def _on_analysis_done(self, code: str, result: dict):
        self._all_results[code] = result
        # 현재가 업데이트
        for r in range(self.table.rowCount()):
            item = self.table.item(r, 0)
            if item and item.data(Qt.UserRole):
                row_data = next(
                    (d for d in self._data if d.get("id") == item.data(Qt.UserRole)), None)
                if row_data and row_data.get("code") == code:
                    cur = result.get("cur_price", 0)
                    # 장마감 후 현재가 0이면 DB 최근 종가 사용
                    if not cur:
                        try:
                            from data.db_manager import get_daily
                            rows_d = get_daily(code, limit=1)
                            if rows_d:
                                cur = rows_d[0].get("close", 0) or 0
                        except:
                            pass
                    qty   = row_data.get("qty", 0) or 0
                    entry = row_data.get("entry_price", 0) or 0
                    n = len(self.columns)
                    self.table.setItem(r, n,
                        QTableWidgetItem(f"{cur:,}" if cur else ""))
                    evlt = cur * qty if cur and qty else 0
                    self.table.setItem(r, n+1,
                        QTableWidgetItem(f"{evlt:,}" if evlt else ""))
                    if entry > 0 and cur > 0:
                        pct = (cur - entry) / entry * 100
                        pct_item = QTableWidgetItem(f"{pct:+.2f}%")
                        pct_item.setForeground(
                            QColor(C_PROFIT) if pct >= 0 else QColor(C_LOSS))
                        self.table.setItem(r, n+2, pct_item)
                    break

    def _show_analysis(self, code: str, name: str, result: dict):
        dlg = AnalysisDialog(code, name, result, self)
        dlg.exec_()

    def _show_all_analysis(self):
        self.progress.setVisible(False)
        # 요약 다이얼로그
        summary = f"전체 분석 완료 ({len(self._all_results)}종목)\n\n"
        signal_codes = []
        for code, res in self._all_results.items():
            if res.get("signal"):
                signal_codes.append(code)
        if signal_codes:
            summary += f"✅ 신호 감지 종목 ({len(signal_codes)}개):\n"
            for c in signal_codes:
                row = next((r for r in self._data if r.get("code")==c), {})
                summary += f"  {row.get('name',c)}({c})\n"
        else:
            summary += "신호 감지 종목 없음\n"
        QMessageBox.information(self, "분석 완료", summary)


# ══════════════════════════════════════════════════════════
# 직접관리종목 탭
class DirectTab(StockTab):
    COLS = [
        {"key":"code",        "label":"종목코드"},
        {"key":"name",        "label":"종목명"},
        {"key":"qty",         "label":"수량",   "align":"right"},
        {"key":"entry_price", "label":"매입가", "align":"right"},
        {"key":"note",        "label":"메모"},
    ]
    def __init__(self, parent=None):
        super().__init__("direct", self.COLS,
                         get_direct, add_direct, upd_direct, del_direct,
                         parent)

# 의뢰관리종목 탭
class ConsignTab(StockTab):
    COLS = [
        {"key":"code",        "label":"종목코드"},
        {"key":"name",        "label":"종목명"},
        {"key":"holder",      "label":"보유자"},
        {"key":"qty",         "label":"수량",      "align":"right"},
        {"key":"entry_price", "label":"매입가",    "align":"right"},
        {"key":"note",        "label":"메모"},
        {"key":"updated_at",  "label":"갱신일"},
    ]
    def __init__(self, parent=None):
        super().__init__("consign", self.COLS,
                         get_consign, add_consign, upd_consign, del_consign,
                         parent)
        # PC1 동기화 버튼 + 텔레그램 출력 버튼 추가
        from PyQt5.QtWidgets import QPushButton
        btn_sync = QPushButton("🔁 PC1 동기화")
        btn_sync.setProperty("class", "yellow")
        btn_sync.clicked.connect(self._sync_pc1)
        btn_send = QPushButton("📤 텔레그램 출력")
        btn_send.setProperty("class", "green")
        btn_send.clicked.connect(self._send_report)
        # 상단 버튼바에 추가 (progress 위젯 바로 앞에 삽입)
        self._top_layout.insertWidget(self._top_layout.count()-1, btn_sync)
        self._top_layout.insertWidget(self._top_layout.count()-1, btn_send)

    def _sync_pc1(self):
        try:
            from data.trade_db import sync_from_pc1
            count = sync_from_pc1()
            self.refresh()
            QMessageBox.information(self, "동기화 완료", f"PC1→DB 동기화 완료: {count}종목")
        except Exception as e:
            QMessageBox.warning(self, "오류", f"동기화 실패: {e}")

    def _send_report(self):
        try:
            from data.trade_db import get_consign
            from report.telegram import send_holder_report
            stocks = get_consign()
            holders = {}
            for s in stocks:
                h = s.get("holder","") or "미지정"
                holders.setdefault(h, []).append(s)
            if not holders:
                QMessageBox.information(self, "알림", "의뢰관리 종목이 없습니다.")
                return
            send_holder_report("의뢰관리", holders)
            QMessageBox.information(self, "전송 완료", f"텔레그램 보고 완료: {len(holders)}명")
        except Exception as e:
            QMessageBox.warning(self, "오류", f"전송 실패: {e}")

# 신저가종목 탭
class NewLowTab(StockTab):
    COLS = [
        {"key":"code",      "label":"종목코드"},
        {"key":"name",      "label":"종목명"},
        {"key":"cur_price", "label":"현재가",   "align":"right"},
        {"key":"low_52w",   "label":"52주저가", "align":"right"},
        {"key":"drop_pct",  "label":"하락률",   "align":"right"},
        {"key":"scan_date", "label":"검색일"},
        {"key":"note",      "label":"메모"},
    ]
    def __init__(self, parent=None):
        super().__init__("newlow", self.COLS,
                         get_newlow, add_newlow, upd_newlow, del_newlow,
                         parent)

# 관심종목 탭
class WatchlistTab(StockTab):
    COLS = [
        {"key":"code",       "label":"종목코드"},
        {"key":"name",       "label":"종목명"},
        {"key":"note",       "label":"메모"},
        {"key":"created_at", "label":"등록일"},
        {"key":"updated_at", "label":"갱신일"},
    ]
    def __init__(self, parent=None):
        super().__init__("watchlist", self.COLS,
                         get_watchlist, add_watchlist, upd_watchlist, del_watchlist,
                         parent)

# ══════════════════════════════════════════════════════════
# 사용자 관리 탭
class UserTab(QWidget):
    """보유자 전화번호 등록 + Railway 링크 생성"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._users = []
        self._build_ui()
        self.refresh()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5,5,5,5)
        layout.setSpacing(8)

        # ── 등록 폼 ──
        form_card = QFrame()
        form_card.setStyleSheet(f"background:{C_PANEL}; border:1px solid #444; border-radius:6px;")
        form_layout = QVBoxLayout(form_card)
        form_layout.setContentsMargins(12,10,12,10)

        title_lbl = QLabel("📱 사용자 등록")
        title_lbl.setFont(QFont("맑은 고딕", 14, QFont.Bold))
        form_layout.addWidget(title_lbl)

        row = QHBoxLayout()
        self.f_holder = QLineEdit(); self.f_holder.setPlaceholderText("보유자명 (예: 김은경)")
        self.f_phone  = QLineEdit(); self.f_phone.setPlaceholderText("전화번호 (예: 01012345678)")
        btn_add = QPushButton("➕ 등록")
        btn_add.setFixedWidth(80)
        btn_add.clicked.connect(self._register_user)
        row.addWidget(self.f_holder)
        row.addWidget(self.f_phone)
        row.addWidget(btn_add)
        form_layout.addLayout(row)
        layout.addWidget(form_card)

        # ── 사용자 목록 테이블 (5컬럼) ──
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["보유자명", "전화번호", "접속 링크", "링크복사", "수정/삭제"])
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(2, QHeaderView.Stretch)
        hh.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.table.setAlternatingRowColors(False)
        layout.addWidget(self.table)

        # ── 하단 ──
        bot = QHBoxLayout()
        btn_ref = QPushButton("🔄 새로고침")
        btn_ref.clicked.connect(self.refresh)
        self.status_lbl = QLabel("총 0명")
        bot.addWidget(btn_ref)
        bot.addStretch()
        bot.addWidget(self.status_lbl)
        layout.addLayout(bot)

    def refresh(self):
        """Railway에서 사용자 목록 로드"""
        try:
            from data_pusher import pusher
            self._users = pusher.list_users()
            self._render()
        except Exception as e:
            self.status_lbl.setText(f"로드 실패: {e}")

    def _render(self):
        self.table.setRowCount(0)
        for u in self._users:
            r = self.table.rowCount()
            self.table.insertRow(r)

            # 보유자명
            self.table.setItem(r, 0, QTableWidgetItem(u.get("holder","")))
            # 전화번호
            self.table.setItem(r, 1, QTableWidgetItem(u.get("phone","")))
            # 접속 링크 (파란색 텍스트로 표시)
            link = u.get("link","")
            link_item = QTableWidgetItem(link)
            link_item.setForeground(QColor("#58a6ff"))
            link_item.setToolTip(link)
            self.table.setItem(r, 2, link_item)

            # 링크복사 버튼 (노란색)
            btn_copy = QPushButton("📋 링크복사")
            btn_copy.setMaximumHeight(28)
            btn_copy.setStyleSheet(f"background:{C_BTN_YLW}; color:black; font-size:13px; font-weight:bold;")
            btn_copy.clicked.connect(lambda _, l=link: self._copy_link(l))
            self.table.setCellWidget(r, 3, btn_copy)

            # 수정 + 삭제 버튼
            btn_frame = QWidget()
            btn_layout = QHBoxLayout(btn_frame)
            btn_layout.setContentsMargins(2,2,2,2); btn_layout.setSpacing(4)

            btn_edit = QPushButton("✏️ 수정")
            btn_edit.setMaximumHeight(28)
            btn_edit.setStyleSheet(f"background:{C_BTN}; font-size:13px; font-weight:bold;")
            btn_edit.clicked.connect(lambda _, uu=u: self._edit_user(uu))

            btn_del = QPushButton("🗑️ 삭제")
            btn_del.setMaximumHeight(28)
            btn_del.setStyleSheet(f"background:{C_BTN_RED}; font-size:13px; font-weight:bold;")
            btn_del.clicked.connect(lambda _, t=u.get("token",""): self._delete_user(t))

            btn_layout.addWidget(btn_edit)
            btn_layout.addWidget(btn_del)
            self.table.setCellWidget(r, 4, btn_frame)

        self.table.verticalHeader().setDefaultSectionSize(36)
        self.status_lbl.setText(f"총 {len(self._users)}명")


    def _edit_user(self, user: dict):
        """전화번호 수정 다이얼로그"""
        from PyQt5.QtWidgets import QInputDialog
        holder = user.get("holder","")
        old_phone = user.get("phone","")
        token = user.get("token","")
        new_phone, ok = QInputDialog.getText(
            self, "전화번호 수정",
            f"{holder}의 전화번호를 수정하세요:",
            text=old_phone
        )
        if not ok or not new_phone.strip():
            return
        try:
            from data_pusher import pusher
            # 기존 삭제 후 재등록
            pusher.delete_user(token)
            result = pusher.register_user(holder, new_phone.strip().replace("-",""))
            if result:
                QMessageBox.information(self, "수정 완료", f"{holder} 전화번호가 수정됐습니다.")
                self.refresh()
            else:
                QMessageBox.warning(self, "오류", "수정에 실패했습니다.")
        except Exception as e:
            QMessageBox.warning(self, "오류", f"수정 실패: {e}")

    def _register_user(self):
        holder = self.f_holder.text().strip()
        phone  = self.f_phone.text().strip().replace("-","")
        if not holder or not phone:
            QMessageBox.warning(self, "입력 오류", "보유자명과 전화번호를 모두 입력하세요.")
            return
        try:
            from data_pusher import pusher
            result = pusher.register_user(holder, phone)
            if not result:
                QMessageBox.warning(self, "오류", "사용자 등록에 실패했습니다.\nRAILWAY_URL 설정을 확인하세요.")
                return
            link = result.get("link","")
            already = result.get("already_exists", False)
            msg = f"{'이미 등록된 사용자입니다.' if already else '등록 완료!'}\n\n보유자: {holder}\n링크: {link}"
            QMessageBox.information(self, "등록 결과", msg)
            # 클립보드 복사
            from PyQt5.QtWidgets import QApplication
            QApplication.clipboard().setText(link)
            self.f_holder.clear(); self.f_phone.clear()
            self.refresh()
        except Exception as e:
            QMessageBox.warning(self, "오류", f"등록 실패: {e}")

    def _copy_link(self, link):
        from PyQt5.QtWidgets import QApplication
        QApplication.clipboard().setText(link)
        QMessageBox.information(self, "복사 완료", f"링크가 클립보드에 복사됐습니다.\n{link}")

    def _delete_user(self, token):
        ans = QMessageBox.question(self, "삭제 확인", "이 사용자를 삭제하시겠습니까?",
                                   QMessageBox.Yes | QMessageBox.No)
        if ans == QMessageBox.Yes:
            try:
                from data_pusher import pusher
                ok = pusher.delete_user(token)
                if ok:
                    self.refresh()
                else:
                    QMessageBox.warning(self, "오류", "삭제에 실패했습니다.")
            except Exception as e:
                QMessageBox.warning(self, "오류", f"삭제 실패: {e}")


# ══════════════════════════════════════════════════════════
# 메인 관리자 윈도우
class AdminWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("SHE 관리자 모드 v1.0")
        self.setMinimumSize(1200, 700)
        self.setStyleSheet(STYLE_MAIN)

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        # ── 헤더 ──
        header = QHBoxLayout()
        title  = QLabel("⚡ SHE 관리자 모드")
        title.setFont(QFont("맑은 고딕", 18, QFont.Bold))
        self.clock = QLabel("")
        self.clock.setFont(QFont("맑은 고딕", 15))

        btn_refresh_all = QPushButton("🔄 전체 새로고침")
        btn_refresh_all.setFixedWidth(150)
        btn_refresh_all.clicked.connect(self._refresh_all)

        header.addWidget(title)
        header.addStretch()
        header.addWidget(btn_refresh_all)
        header.addWidget(self.clock)
        layout.addLayout(header)

        # ── 탭 ──
        self.tabs = QTabWidget()
        self.tab_direct  = DirectTab()
        self.tab_consign = ConsignTab()
        self.tab_newlow  = NewLowTab()
        self.tab_watch   = WatchlistTab()
        self.tab_users   = UserTab()

        self.tabs.addTab(self.tab_direct,  "📌 직접관리종목")
        self.tabs.addTab(self.tab_consign, "📋 의뢰관리종목")
        self.tabs.addTab(self.tab_newlow,  "📉 신저가종목")
        self.tabs.addTab(self.tab_watch,   "👀 관심종목")
        self.tabs.addTab(self.tab_users,   "👤 사용자관리")
        layout.addWidget(self.tabs)

        # ── 시계 타이머 ──
        self.timer = QTimer()
        self.timer.timeout.connect(self._update_clock)
        self.timer.start(1000)
        self._update_clock()

        # ── 시작 시 현재가 자동 로드 (2초 후 실행 — UI 완전 렌더링 후)
        self._init_timer = QTimer()
        self._init_timer.setSingleShot(True)
        self._init_timer.timeout.connect(self._refresh_all)
        self._init_timer.start(2000)

    def _refresh_all(self):
        """전체 탭 새로고침 + 현재가 조회"""
        self.tab_direct.refresh()
        self.tab_consign.refresh()
        self.tab_newlow.refresh()
        self.tab_watch.refresh()
        self.tab_users.refresh()
        # 현재가 전용 워커로 빠르게 업데이트
        for tab in [self.tab_direct, self.tab_consign, self.tab_watch]:
            if tab._data:
                tab.refresh_prices()

    def _update_clock(self):
        self.clock.setText(
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"))


# ── 실행 ──────────────────────────────────────────────────
if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    win = AdminWindow()
    win.show()
    sys.exit(app.exec_())
