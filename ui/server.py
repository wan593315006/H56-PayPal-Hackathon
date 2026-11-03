#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""H56 支付版治理 · 只读证据台 —— 本地展示服务。

设计约束（不可放宽）：
  * 纯标准库，不引用交付包的应用层与内核层模块，不联网。
  * 纯只读：只做 open/read，从不写 runs/ 或 records/，从不触发新的评估。
  * 三道闸：Host 精确匹配、一次性 token、POST 空体。

读取边界的第四条约束（P2 审计整改后加入）：参数字符白名单只约束**名字**，不约束**位置**。
一个合规命名的 run 目录可以是目录联接（junction / symlink / 其它重解析点），
白名单校验通过而内容在 runs\ 之外。所以每次读盘前都要问两件事：
真实路径是否仍在根内，以及从根到目标的路径上有无重解析点。两者任一不成立即拒绝。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import secrets
import stat
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
RUNS_DIR = ROOT / "runs"
RECORDS_DIR = ROOT / "records"
INDEX_FILE = HERE / "index.html"

STAMP_RE = re.compile(r"^[0-9]{8}T[0-9]{6}Z\Z")
BUSINESS_RE = re.compile(r"^[A-Za-z0-9_-]{1,32}\Z")

MAX_POST_BODY = 65536
TOKEN_HEADER = "X-H56-Run-Token"

# 只读视图里允许暴露的 run 文件（白名单，不做目录拼接之外的探索）
RUN_FILES = ("request.json", "evidence.json", "result.json", "binding.json")

REPARSE_POINT = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)



# --------------------------------------------------------------------------
# 基础工具（全部只读）
# --------------------------------------------------------------------------

def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_bytes(obj) -> bytes:
    """canonical JSON：sort_keys + 紧凑分隔符 + 不转义非 ASCII。

    这是 UI 侧独立实现的字节级口径，用来复核 binding.json 自洽；
    语义链复核属于 app.main verify 的职责，这里不做。
    """
    return json.dumps(obj, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False).encode("utf-8")


def read_json(path: Path):
    """返回 (对象, 错误码)。文件缺失或不是合法 JSON 时对象为 None。"""
    if not path.is_file():
        return None, "MISSING"
    try:
        raw = path.read_bytes()
    except OSError:
        return None, "UNREADABLE"
    try:
        return json.loads(raw.decode("utf-8-sig")), None
    except (UnicodeDecodeError, ValueError):
        return None, "INVALID_JSON"


def file_sha256(path: Path):
    if not path.is_file():
        return None
    try:
        return sha256_bytes(path.read_bytes())
    except OSError:
        return None


def as_bool(value) -> bool:
    return value is True


# --------------------------------------------------------------------------
# 读取边界
# --------------------------------------------------------------------------

class BoundaryError(Exception):
    """一个路径没通过边界检查。`code` 直接进响应体，不吞掉原因。"""

    def __init__(self, code, detail=""):
        self.code = code
        self.detail = detail
        super().__init__(code + (": " + detail if detail else ""))


def is_reparse(path: Path) -> bool:
    """符号链接，或任何带重解析点的对象（目录联接、挂载点等）。

    `Path.is_symlink()` 只看符号链接；Windows 的目录联接（junction）不是符号链接，
    却是把目录指到别处去的同一类东西。`lstat()` 的 `st_file_attributes` 才看得见它。
    """
    try:
        info = os.lstat(str(path))
    except OSError:
        return False
    if stat.S_ISLNK(info.st_mode):
        return True
    return bool(getattr(info, "st_file_attributes", 0) & REPARSE_POINT)


def resolve_within(path: Path, root: Path):
    """路径在根内且路上没有重解析点时返回真实路径，否则返回 None。

    两道判据都要，因为它们挡的不是同一种事：
      * 重解析点检查 —— 名字在根内、内容在根外；
      * realpath 包含检查 —— 根内的联接指向根外，或经由任意形式的重定向离开根。
    只看其中一个都能被另一个绕过。
    """
    if is_reparse(root):
        return None
    current = Path(path)
    chain = []
    while True:
        chain.append(current)
        if current == root or current.parent == current:
            break
        current = current.parent
    if not chain or chain[-1] != root:
        return None
    if any(is_reparse(item) for item in chain):
        return None
    try:
        real = Path(os.path.realpath(str(path)))
        real_root = Path(os.path.realpath(str(root)))
    except OSError:
        return None
    if real != real_root and real_root not in real.parents:
        return None
    return real


# --------------------------------------------------------------------------
# 只读数据视图
# --------------------------------------------------------------------------

def scan_run_dirs():
    """枚举 runs/<stamp>_<business>/，返回 (合规条目, 被边界检查拒掉的条目)。

    被拒的条目要单独返回，不能只是静默跳过：看不见的东西无法被质疑，
    而"列表里没有"与"存在但被拒"对审计是两件完全不同的事。
    """
    found, refused = [], []
    if not RUNS_DIR.is_dir():
        return found, refused
    for entry in sorted(RUNS_DIR.iterdir(), key=lambda p: p.name):
        stamp, sep, business = entry.name.partition("_")
        if not sep or not STAMP_RE.match(stamp) or not BUSINESS_RE.match(business):
            continue
        if not entry.is_dir():
            continue
        if resolve_within(entry, RUNS_DIR) is None:
            refused.append({"entry": entry.name, "code": "PATH_OUTSIDE_ROOT",
                            "why": "目录联接或真实路径在 runs/ 之外"})
            continue
        found.append((stamp, business, entry))
    return found, refused


def list_run_dirs():
    return scan_run_dirs()[0]


def run_path(stamp: str, business: str) -> Path:
    """按名字取 run 目录，名字之外还要过边界检查。"""
    candidate = RUNS_DIR / ("%s_%s" % (stamp, business))
    if not candidate.is_dir():
        raise BoundaryError("RUN_NOT_FOUND")
    if resolve_within(candidate, RUNS_DIR) is None:
        raise BoundaryError("PATH_OUTSIDE_ROOT", candidate.name)
    return candidate


def run_file(run_dir: Path, name: str):
    """run 目录里的一个文件，同样不能被联接带到外面去。"""
    candidate = run_dir / name
    if not candidate.exists():
        return None
    if resolve_within(candidate, RUNS_DIR) is None:
        raise BoundaryError("PATH_OUTSIDE_ROOT", name)
    return candidate


def check_binding(run_dir: Path):
    """字节级自洽复核，不重算语义链。"""
    try:
        binding_path = run_file(run_dir, "binding.json")
        evidence_path = run_file(run_dir, "evidence.json")
    except BoundaryError as error:
        # A linked file inside an otherwise good directory is neither "absent" nor "clean".
        # Saying `present: False` here would let the page show a harmless-looking gap.
        return {
            "present": True,
            "ok": False,
            "binding_sha256_match": False,
            "evidence_sha256_match": False,
            "boundary_refused": error.code,
            "note": "读取被边界检查拒绝：%s" % error.detail,
        }
    if binding_path is None or not binding_path.is_file():
        return {
            "present": False,
            "ok": None,
            "binding_sha256_match": None,
            "evidence_sha256_match": None,
            "note": "该 run 无 binding.json（未进入绑定阶段）",
        }

    binding, err = read_json(binding_path)
    if not isinstance(binding, dict):
        return {
            "present": True,
            "ok": False,
            "binding_sha256_match": False,
            "evidence_sha256_match": False,
            "note": "binding.json 不可解析：%s" % err,
        }

    claimed = binding.get("binding_sha256")
    body = {k: v for k, v in binding.items() if k != "binding_sha256"}
    computed = sha256_bytes(canonical_bytes(body))
    binding_match = isinstance(claimed, str) and claimed == computed

    evidence_claimed = binding.get("evidence_sha256")
    evidence_actual = file_sha256(evidence_path) if evidence_path is not None else None
    if evidence_actual is None:
        evidence_match = False
        evidence_note = "evidence.json 缺失，无法复核"
    else:
        evidence_match = isinstance(evidence_claimed, str) and evidence_claimed == evidence_actual
        evidence_note = "evidence_sha256 与 evidence.json 字节一致" if evidence_match \
            else "evidence_sha256 与 evidence.json 字节不一致"

    ok = bool(binding_match and evidence_match)
    return {
        "present": True,
        "ok": ok,
        "binding_sha256_match": bool(binding_match),
        "evidence_sha256_match": bool(evidence_match),
        "binding_sha256_claimed": claimed,
        "binding_sha256_computed": computed,
        "evidence_sha256_claimed": evidence_claimed,
        "evidence_sha256_file": evidence_actual,
        "note": evidence_note,
    }


def summarize_run(stamp: str, business: str, run_dir: Path):
    try:
        result_path = run_file(run_dir, "result.json")
    except BoundaryError:
        result_path = None
    result, result_err = (read_json(result_path) if result_path is not None
                          else (None, "OUTSIDE_ROOT"))
    if not isinstance(result, dict):
        result = {}

    binding = check_binding(run_dir)

    files = []
    try:
        for child in sorted(run_dir.iterdir(), key=lambda p: p.name):
            if child.name not in RUN_FILES or not child.is_file():
                continue
            # 白名单只挡名字；被联接指到根外的同名文件仍然要挡。
            if resolve_within(child, RUNS_DIR) is None:
                continue
            files.append(child.name)
    except OSError:
        files = []

    business_action_calls = result.get("business_action_calls")
    try:
        business_action_observed = int(business_action_calls) > 0
    except (TypeError, ValueError):
        business_action_observed = False

    return {
        "stamp": stamp,
        "business": business,
        "decision": result.get("decision"),
        "stage": result.get("stage"),
        "native_calls": result.get("native_calls"),
        "boundary": {
            "authority_granted": as_bool(result.get("authority_granted")),
            "execution_permitted": as_bool(result.get("execution_permitted")),
            "business_action_observed": business_action_observed,
        },
        "has_binding": binding["present"],
        "files": files,
        "binding_ok": binding["ok"],
        "result_state": "OK" if result_err is None else result_err,
    }


def api_runs():
    return [summarize_run(stamp, business, run_dir)
            for stamp, business, run_dir in list_run_dirs()]


def api_refused():
    """被边界检查拒掉的条目。列出来，而不是让它们从列表里消失。"""
    _found, refused = scan_run_dirs()
    rows = [dict(row, root="runs") for row in refused]
    if RECORDS_DIR.is_dir():
        for entry in sorted(RECORDS_DIR.iterdir(), key=lambda p: p.name):
            if not entry.is_dir() or not entry.name.startswith("oq_"):
                continue
            if resolve_within(entry, RECORDS_DIR) is None:
                rows.append({"entry": entry.name, "code": "PATH_OUTSIDE_ROOT",
                             "why": "目录联接或真实路径在 records/ 之外",
                             "root": "records"})
    return rows


def api_run(stamp: str, business: str):
    try:
        run_dir = run_path(stamp, business)
    except BoundaryError as error:
        if error.code == "RUN_NOT_FOUND":
            return None
        raise

    view = {
        "stamp": stamp,
        "business": business,
        "order": None,
        "policy": None,
        "reference": None,
        "result": None,
        "request": None,
        "evidence": None,
        "binding": None,
        "binding_check": check_binding(run_dir),
        "unreadable": [],
    }
    for key, filename in (("result", "result.json"),
                          ("request", "request.json"),
                          ("evidence", "evidence.json"),
                          ("binding", "binding.json")):
        try:
            path = run_file(run_dir, filename)
        except BoundaryError as error:
            view[key] = None
            view["unreadable"].append({"file": filename, "state": error.code})
            continue
        obj, err = (read_json(path) if path is not None else (None, "MISSING"))
        view[key] = obj
        if err is not None:
            view["unreadable"].append({"file": filename, "state": err})

    view.update(summarize_run(stamp, business, run_dir))

    # 把 order / policy / reference 提到顶层，方便前端直接用；
    # reference 在业务策略拦下的 run 里只存在于 binding.json。
    result = view.get("result") if isinstance(view.get("result"), dict) else {}
    binding = view.get("binding") if isinstance(view.get("binding"), dict) else {}
    view["order"] = result.get("order") or binding.get("order")
    view["policy"] = result.get("policy") or binding.get("policy")
    view["reference"] = result.get("reference") or binding.get("reference")
    return view


def split_session(session: str):
    """oq_<business>_<stamp> -> (business, stamp)；不合规返回 (None, None)。"""
    head, sep, tail = session.rpartition("_")
    if not sep or not STAMP_RE.match(tail):
        return None, None
    _, _, business = head.partition("_")
    if not business or not BUSINESS_RE.match(business):
        return business or None, tail
    return business, tail


def parse_journal(path: Path):
    """逐行解析 events.jsonl。判据与 `app/recovery.journal_state` 逐字一致。

    两个条件都叫 TORN，因为内核拒绝这两个条件用的是同一条规则：末行没有换行符，
    或者某一整行不是 JSON。以前这里把"末行没换行"当成可读（先 pop 掉空段再逐行解析），
    于是内核拒绝、恢复模块报 TORN_JOURNAL、UI 却显示 OK —— 三处对同一份字节给出两种结论。
    一个显示层可以对内容保守，但不能对同一判据给出比内核更乐观的答案。
    """
    if not path.is_file():
        return {"journal_state": "MISSING", "events": 0, "damaged_line": None}

    try:
        raw = path.read_bytes()
    except OSError:
        return {"journal_state": "UNREADABLE", "events": 0, "damaged_line": None}

    if not raw:
        # An empty file and no file at all mean the same thing here, and `recovery` calls both
        # MISSING. Reporting one of them as OK would make the same bytes read two ways.
        return {"journal_state": "MISSING", "events": 0, "damaged_line": None}
    if not raw.endswith(b"\n"):
        return {"journal_state": "TORN", "events": 0, "damaged_line": None}

    lines = raw.split(b"\n")
    if lines and lines[-1] == b"":
        lines.pop()

    events = 0
    for index, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            json.loads(line.decode("utf-8-sig"))
        except (UnicodeDecodeError, ValueError):
            return {"journal_state": "TORN", "events": events, "damaged_line": index}
        events += 1

    return {"journal_state": "OK", "events": events, "damaged_line": None}


def decision_index():
    """assessment_id -> 该评估自己的判定来源，用于给 record 补判定，缺失则留空。

    索引键是 `assessment_id`，不是时间戳。按时间戳兜底曾经把另一条业务的结论借给了
    当前记录：两项业务同戳、一个可行一个不可行，删掉不可行那条的 result.json 后，
    UI 就把可行那条的 FEASIBLE 显示在了不可行记录上。**同戳不等于同一条评估**，
    评估之间唯一的对应关系是 assessment_id（以及产物里的 semantic_sha256）。
    找不到就返回空，显示"未知"比显示别人的结论更接近事实。
    """
    index = {}
    for stamp, business, run_dir in list_run_dirs():
        try:
            path = run_file(run_dir, "result.json")
        except BoundaryError:
            continue
        if path is None:
            continue
        result, _ = read_json(path)
        if not isinstance(result, dict):
            continue
        reference = result.get("reference") or {}
        assessment_id = reference.get("assessment_id") or result.get("assessment_id")
        if not isinstance(assessment_id, str) or not assessment_id.startswith("ASSESS:"):
            continue
        index[assessment_id] = {
            "decision": result.get("decision"),
            "stamp": stamp,
            "business": business,
        }
    return index


def api_records():
    decisions = decision_index()
    records = []
    if not RECORDS_DIR.is_dir():
        return records

    for entry in sorted(RECORDS_DIR.iterdir(), key=lambda p: p.name):
        if not entry.is_dir() or not entry.name.startswith("oq_"):
            continue
        # 记录库这一侧同样要过边界：会话目录本身可以是联接。
        if resolve_within(entry, RECORDS_DIR) is None:
            continue
        session = entry.name
        business, stamp = split_session(session)

        journal_path = entry / "events.jsonl"
        journal = (parse_journal(journal_path)
                   if resolve_within(journal_path, RECORDS_DIR) is not None
                   else {"journal_state": "OUTSIDE_ROOT", "events": 0, "damaged_line": None})

        artifacts_dir = entry / "artifacts"
        artifact_files = []
        if artifacts_dir.is_dir() and resolve_within(artifacts_dir, RECORDS_DIR) is not None:
            try:
                artifact_files = sorted(p for p in artifacts_dir.iterdir()
                                        if p.is_file()
                                        and resolve_within(p, RECORDS_DIR) is not None)
            except OSError:
                artifact_files = []
        artifact_bytes = 0
        for path in artifact_files:
            try:
                artifact_bytes += path.stat().st_size
            except OSError:
                pass

        assessment_id = None
        artifact_doc = None
        if artifact_files:
            artifact_doc, _ = read_json(artifact_files[0])
        if isinstance(artifact_doc, dict):
            assessment_id = artifact_doc.get("assessment_id")
        if not assessment_id and artifact_files:
            stem = artifact_files[0].stem
            if len(stem) == 64:
                assessment_id = "ASSESS:" + stem

        match = decisions.get(assessment_id) if assessment_id else None
        decision = match["decision"] if match else None
        stored = None
        if isinstance(artifact_doc, dict):
            stored = (artifact_doc.get("c2_projection") or {}).get("decision")

        records.append({
            "session": session,
            "assessment_id": assessment_id,
            "decision": decision,
            "decision_source": ("ASSESSMENT_MATCH" if match else "NO_MATCH"),
            "decision_run": (None if not match
                             else "%s_%s" % (match["stamp"], match["business"])),
            # 产物里自己的判定与它对应的 run 判定不一致，是漂移的直接证据；
            # 两者都可能"有值"，但只有一个能同时成立。
            "artifact_decision": stored,
            "decision_conflict": bool(match and stored and stored != decision),
            "artifact_bytes": artifact_bytes,
            "artifact_count": len(artifact_files),
            "events": journal["events"],
            "journal_state": journal["journal_state"],
            "journal_damaged_line": journal["damaged_line"],
        })

    return records


# --------------------------------------------------------------------------
# HTTP 层
# --------------------------------------------------------------------------

ERROR_TEXT = {
    "HOST_NOT_ALLOWED": "Host 头必须精确为 127.0.0.1:<port>，不接受 localhost 及其它别名。",
    "TOKEN_REQUIRED": "缺少或错误的 " + TOKEN_HEADER + " 头。token 在服务进程 stdout 里。",
    "METHOD_NOT_ALLOWED": "/api/* 只接受 GET 与 POST。",
    "BODY_NOT_EMPTY": "POST 体必须是空对象 {}。",
    "BAD_PARAM": "stamp/business 未通过白名单校验。",
    "RUN_NOT_FOUND": "该 run 目录不存在。",
    "PATH_OUTSIDE_ROOT": "该路径是目录联接/重解析点，或真实路径在 runs\\ / records\\ 之外，已拒绝读取。",
    "NOT_FOUND": "无此路由。",
    "INTERNAL_ERROR": "服务端读取失败，详情见服务进程 stderr。",
}


class Handler(BaseHTTPRequestHandler):
    server_version = "H56ReadOnlyUI/1.0"
    sys_version = ""
    protocol_version = "HTTP/1.1"

    # --- 统一日志：只到 stderr，不落盘 ---
    def log_message(self, fmt, *args):
        sys.stderr.write("[h56-ui] %s %s\n" % (self.log_date_time_string(), fmt % args))

    # --- 输出 ---
    def _send(self, status, payload, content_type, extra_headers=None):
        if isinstance(payload, (dict, list)):
            body = json.dumps(payload, ensure_ascii=False,
                              separators=(",", ":")).encode("utf-8")
        elif isinstance(payload, str):
            body = payload.encode("utf-8")
        else:
            body = payload

        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        for key, value in (extra_headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        if self.command != "HEAD":
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass

    def _error(self, status, code, extra_headers=None):
        self._send(status, {"error": code, "message": ERROR_TEXT.get(code, "")},
                   "application/json; charset=utf-8", extra_headers)

    # --- 闸门 ---
    def _host_ok(self):
        expected = "127.0.0.1:%d" % self.server.server_address[1]
        return (self.headers.get("Host") or "").strip() == expected

    def _token_ok(self):
        supplied = self.headers.get(TOKEN_HEADER)
        if not isinstance(supplied, str) or not supplied:
            return False
        return secrets.compare_digest(supplied, self.server.run_token)

    def _read_body(self):
        """返回 (bytes, 是否读取成功)。超长视为非法并断开连接。"""
        raw_length = self.headers.get("Content-Length")
        if raw_length is None:
            return b"", True
        try:
            length = int(raw_length)
        except (TypeError, ValueError):
            return b"", False
        if length < 0 or length > MAX_POST_BODY:
            return b"", False
        if length == 0:
            return b"", True
        try:
            return self.rfile.read(length), True
        except OSError:
            return b"", False

    def _body_is_empty_object(self):
        body, read_ok = self._read_body()
        if not read_ok:
            return False
        return body.strip() == b"{}"

    # --- 路由分发 ---
    def do_GET(self):
        self._dispatch("GET")

    def do_POST(self):
        self._dispatch("POST")

    def do_PUT(self):
        self._dispatch("PUT")

    def do_DELETE(self):
        self._dispatch("DELETE")

    def do_PATCH(self):
        self._dispatch("PATCH")

    def do_HEAD(self):
        self._dispatch("HEAD")

    def do_OPTIONS(self):
        self._dispatch("OPTIONS")

    def _dispatch(self, method):
        try:
            self._route(method)
        except Exception:  # 绝不把 traceback 写进响应体
            sys.stderr.write("[h56-ui] internal error on %s %s\n"
                             % (method, urlparse(self.path).path))
            try:
                self._send(500, {"error": "INTERNAL_ERROR",
                                 "message": ERROR_TEXT["INTERNAL_ERROR"]},
                           "application/json; charset=utf-8",
                           {"Connection": "close"})
            except Exception:
                pass

    def _route(self, method):
        # 闸一：Host 精确匹配（对所有请求生效，含 "/"）
        if not self._host_ok():
            self._error(403, "HOST_NOT_ALLOWED", {"Connection": "close"})
            return

        path = urlparse(self.path).path
        is_api = path == "/api" or path.startswith("/api/")

        if not is_api:
            if method != "GET":
                self._error(405, "METHOD_NOT_ALLOWED", {"Allow": "GET"})
                return
            if path not in ("/", "/index.html"):
                self._error(404, "NOT_FOUND")
                return
            try:
                html = INDEX_FILE.read_bytes()
            except OSError:
                self._error(500, "INTERNAL_ERROR")
                return
            self._send(200, html, "text/html; charset=utf-8")
            return

        # /api/*：只接受 GET / POST
        if method not in ("GET", "POST"):
            self._error(405, "METHOD_NOT_ALLOWED", {"Allow": "GET, POST"})
            return

        # 闸二：一次性 token
        if not self._token_ok():
            self._error(401, "TOKEN_REQUIRED")
            return

        # 闸三：POST 体必须是 {}
        if method == "POST" and not self._body_is_empty_object():
            self._error(400, "BODY_NOT_EMPTY", {"Connection": "close"})
            return

        if path == "/api/runs":
            self._send(200, api_runs(), "application/json; charset=utf-8")
            return

        if path == "/api/records":
            self._send(200, api_records(), "application/json; charset=utf-8")
            return

        if path == "/api/refused":
            self._send(200, api_refused(), "application/json; charset=utf-8")
            return

        if path == "/api/run":
            query = parse_qs(urlparse(self.path).query, keep_blank_values=True)
            stamp = (query.get("stamp") or [""])[0].strip()
            business = (query.get("business") or [""])[0].strip()
            if not STAMP_RE.match(stamp) or not BUSINESS_RE.match(business):
                self._error(400, "BAD_PARAM")
                return
            try:
                view = api_run(stamp, business)
            except BoundaryError as error:
                # 名字通过白名单、内容在根外：这不是 404，也不是 500。
                self._error(403, error.code)
                return
            if view is None:
                self._error(404, "RUN_NOT_FOUND")
                return
            self._send(200, view, "application/json; charset=utf-8")
            return

        self._error(404, "NOT_FOUND")


class Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False

    def __init__(self, address, handler, run_token):
        self.run_token = run_token
        super().__init__(address, handler)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="H56 支付版治理 · 只读证据台（不触发任何评估）")
    parser.add_argument("--port", type=int, default=8848,
                        help="监听端口，默认 8848")
    args = parser.parse_args(argv)

    if not (0 < args.port < 65536):
        parser.error("--port 必须在 1..65535 之间")

    token = secrets.token_hex(16)
    try:
        httpd = Server(("127.0.0.1", args.port), Handler, token)
    except OSError as exc:
        sys.stderr.write("[h56-ui] 端口 %d 不可用：%s\n" % (args.port, exc))
        return 2

    port = httpd.server_address[1]
    out = sys.stdout
    out.write("H56 只读证据台已启动\n")
    out.write("  URL   : http://127.0.0.1:%d/\n" % port)
    out.write("  TOKEN : %s\n" % token)
    out.write("  头名  : %s\n" % TOKEN_HEADER)
    out.write("  只读  : 不写 runs/ 与 records/，不触发评估；Ctrl+C 结束\n")
    out.flush()

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        out.write("\n[h56-ui] 收到中断，退出。\n")
        out.flush()
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
