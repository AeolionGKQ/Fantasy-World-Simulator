"""SQLite persistence and atomic domain operations."""

import json
import os
import sqlite3
import subprocess
import threading
import uuid
from datetime import datetime, timedelta, timezone

try:
    from .catalog import EXP_THRESHOLDS, NARRATION, POWER_BY_RANK, RULESET_VERSION, validate_draft
    from .content_registry import ContentRegistry
    from .migrations import apply_migrations
    from .model_provider import (ProviderError, response_format_capability_key,
                                 thinking_capability_key, validate_candidate)
except ImportError:  # Direct execution: python server.py
    from catalog import EXP_THRESHOLDS, NARRATION, POWER_BY_RANK, RULESET_VERSION, validate_draft
    from content_registry import ContentRegistry
    from migrations import apply_migrations
    from model_provider import (ProviderError, response_format_capability_key,
                                thinking_capability_key, validate_candidate)


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def utc_after(seconds):
    return (datetime.now(timezone.utc) + timedelta(seconds=seconds)).isoformat()


def new_id():
    return str(uuid.uuid4())


def dumps(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def loads(value, default=None):
    return default if value is None else json.loads(value)


class DomainError(Exception):
    def __init__(self, code, message, status=400, fields=None, retryable=False):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
        self.fields = fields or {}
        self.retryable = retryable


class SecretStore:
    """Keep credentials in Windows DPAPI storage, or in process memory only."""

    def __init__(self, path):
        self.path = os.path.abspath(path)
        self._lock = threading.Lock()
        self._value = None
        self._persistence = "windows_dpapi" if os.name == "nt" else "memory_only"
        self._migrate_legacy_plaintext()

    def _migrate_legacy_plaintext(self):
        legacy = os.path.join(os.path.dirname(self.path), "secrets.json")
        if not os.path.isfile(legacy):
            return
        value = ""
        try:
            with open(legacy, "r", encoding="utf-8") as handle:
                candidate = json.load(handle).get("model_api_key", "")
            value = candidate if isinstance(candidate, str) else ""
            self._value = value
            if os.name == "nt" and value:
                cipher = self._protect(value)
                temporary = self.path + ".tmp"
                with open(temporary, "w", encoding="utf-8", newline="") as handle:
                    handle.write(cipher)
                os.replace(temporary, self.path)
            elif os.name == "nt":
                self._persistence = "windows_dpapi"
            else:
                self._persistence = "memory_only"
        except (OSError, ValueError, UnicodeError, subprocess.SubprocessError):
            self._persistence = "memory_only"
        finally:
            try:
                os.remove(legacy)
            except OSError:
                try:
                    with open(legacy, "w", encoding="utf-8") as handle:
                        handle.write("{}")
                except OSError:
                    pass

    @property
    def persistence(self):
        return self._persistence

    @staticmethod
    def _powershell(script, value):
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        completed = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
             "-Command", script],
            input=value, capture_output=True, text=True, encoding="utf-8", errors="strict",
            timeout=10, check=True, creationflags=flags,
        )
        return completed.stdout

    @classmethod
    def _protect(cls, value):
        script = (
            "$ErrorActionPreference='Stop';"
            "[Console]::InputEncoding=[Text.Encoding]::UTF8;"
            "[Console]::OutputEncoding=New-Object Text.UTF8Encoding($false);"
            "$plain=[Console]::In.ReadToEnd();"
            "$secure=ConvertTo-SecureString -String $plain -AsPlainText -Force;"
            "$cipher=ConvertFrom-SecureString -SecureString $secure;"
            "[Console]::Out.Write($cipher)"
        )
        cipher = cls._powershell(script, value).strip()
        if not cipher or value.encode("utf-8") in cipher.encode("utf-8"):
            raise ValueError("DPAPI encryption returned invalid data")
        return cipher

    @classmethod
    def _unprotect(cls, cipher):
        script = (
            "$ErrorActionPreference='Stop';"
            "[Console]::InputEncoding=[Text.Encoding]::UTF8;"
            "[Console]::OutputEncoding=New-Object Text.UTF8Encoding($false);"
            "$cipher=[Console]::In.ReadToEnd();"
            "$secure=ConvertTo-SecureString -String $cipher;"
            "$ptr=[Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure);"
            "try {[Console]::Out.Write([Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr))}"
            "finally {[Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr)}"
        )
        return cls._powershell(script, cipher)

    def get_api_key(self):
        with self._lock:
            if self._value is not None:
                return self._value
            if os.name != "nt":
                self._value = ""
                self._persistence = "memory_only"
                return self._value
            try:
                with open(self.path, "r", encoding="utf-8") as handle:
                    cipher = handle.read().strip()
                self._value = self._unprotect(cipher) if cipher else ""
            except FileNotFoundError:
                self._value = ""
            except (OSError, ValueError, UnicodeError, subprocess.SubprocessError):
                self._value = ""
                self._persistence = "memory_only"
            return self._value

    def set_api_key(self, value):
        if not isinstance(value, str) or len(value) > 10000:
            raise DomainError("INVALID_INPUT", "API Key 格式无效", fields={"api_key": "必须是长度不超过10000的文本"})
        with self._lock:
            self._value = value
            if os.name != "nt":
                self._persistence = "memory_only"
                return False
            try:
                if not value:
                    try:
                        os.remove(self.path)
                    except FileNotFoundError:
                        pass
                    self._persistence = "windows_dpapi"
                    return True
                cipher = self._protect(value)
                os.makedirs(os.path.dirname(self.path), exist_ok=True)
                temporary = self.path + ".tmp"
                with open(temporary, "w", encoding="utf-8", newline="") as handle:
                    handle.write(cipher)
                os.replace(temporary, self.path)
                self._persistence = "windows_dpapi"
                return True
            except (OSError, ValueError, UnicodeError, subprocess.SubprocessError):
                self._persistence = "memory_only"
                try:
                    os.remove(self.path + ".tmp")
                except FileNotFoundError:
                    pass
                return False

    def prepare_api_key(self, value):
        """Encrypt before DB mutation so plaintext never reaches disk on failure."""
        if not isinstance(value, str) or len(value) > 10000:
            raise DomainError("INVALID_INPUT", "API Key 格式无效", fields={"api_key": "必须是长度不超过10000的文本"})
        if os.name != "nt" or not value:
            return value, None
        try:
            return value, self._protect(value)
        except (OSError, ValueError, UnicodeError, subprocess.SubprocessError):
            return value, None

    def commit_api_key(self, prepared):
        value, cipher = prepared
        with self._lock:
            self._value = value
            if cipher is None:
                self._persistence = "memory_only" if value else (
                    "windows_dpapi" if os.name == "nt" else "memory_only")
                if not value and os.name == "nt":
                    try:
                        os.remove(self.path)
                    except FileNotFoundError:
                        pass
                return False
            try:
                os.makedirs(os.path.dirname(self.path), exist_ok=True)
                temporary = self.path + ".tmp"
                with open(temporary, "w", encoding="utf-8", newline="") as handle:
                    handle.write(cipher)
                os.replace(temporary, self.path)
                self._persistence = "windows_dpapi"
                return True
            except OSError:
                self._persistence = "memory_only"
                try:
                    os.remove(self.path + ".tmp")
                except FileNotFoundError:
                    pass
                return False


SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    model_json TEXT NOT NULL,
    narration_json TEXT NOT NULL,
    thinking_enabled INTEGER NOT NULL DEFAULT 1,
    revision INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS model_capabilities (
    endpoint TEXT NOT NULL,
    model TEXT NOT NULL,
    config_version TEXT NOT NULL,
    capability TEXT NOT NULL CHECK (capability IN ('controlled','unsupported','unknown')),
    strategy TEXT,
    confidence TEXT NOT NULL CHECK (confidence IN ('verified','accepted_bundle','unsupported','unknown')),
    last_failure TEXT,
    probed_at TEXT NOT NULL,
    PRIMARY KEY(endpoint, model, config_version)
);
CREATE TABLE IF NOT EXISTS saves (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    phase TEXT NOT NULL CHECK (phase IN ('draft','review','ready')),
    revision INTEGER NOT NULL,
    ruleset_version TEXT NOT NULL,
    preferences_json TEXT NOT NULL,
    source_save_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS drafts (
    save_id TEXT PRIMARY KEY REFERENCES saves(id) ON DELETE CASCADE,
    data_json TEXT NOT NULL,
    current_step INTEGER NOT NULL,
    revision INTEGER NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS generation_jobs (
    id TEXT PRIMARY KEY,
    save_id TEXT NOT NULL REFERENCES saves(id) ON DELETE CASCADE,
    request_id TEXT NOT NULL,
    draft_revision INTEGER NOT NULL,
    save_revision INTEGER NOT NULL,
    attempt INTEGER NOT NULL,
    status TEXT NOT NULL,
    feedback TEXT NOT NULL,
    error_code TEXT,
    error_message TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(save_id, request_id)
);
CREATE UNIQUE INDEX IF NOT EXISTS one_active_generation_per_save
ON generation_jobs(save_id)
WHERE status IN ('queued','running','cancel_requested');
CREATE TABLE IF NOT EXISTS candidates (
    id TEXT PRIMARY KEY,
    save_id TEXT NOT NULL UNIQUE REFERENCES saves(id) ON DELETE CASCADE,
    job_id TEXT NOT NULL UNIQUE REFERENCES generation_jobs(id) ON DELETE CASCADE,
    draft_revision INTEGER NOT NULL,
    data_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS characters (
    id TEXT PRIMARY KEY,
    save_id TEXT NOT NULL UNIQUE REFERENCES saves(id) ON DELETE CASCADE,
    candidate_id TEXT NOT NULL UNIQUE,
    data_json TEXT NOT NULL,
    confirmed_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS confirmation_requests (
    save_id TEXT NOT NULL REFERENCES saves(id) ON DELETE CASCADE,
    request_id TEXT NOT NULL,
    character_id TEXT NOT NULL,
    request_fingerprint TEXT NOT NULL,
    PRIMARY KEY(save_id, request_id)
);
CREATE TABLE IF NOT EXISTS mutation_requests (
    scope TEXT NOT NULL,
    request_id TEXT NOT NULL,
    response_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY(scope, request_id)
);
"""


class ClosingConnection(sqlite3.Connection):
    def __exit__(self, exc_type, exc_value, traceback_value):
        try:
            return super().__exit__(exc_type, exc_value, traceback_value)
        finally:
            self.close()


class Database:
    def __init__(self, path, content_registry=None):
        self.path = os.path.abspath(path)
        self.content_registry = content_registry or ContentRegistry()
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        self._initialize()

    def connect(self):
        connection = sqlite3.connect(self.path, timeout=5, isolation_level=None,
                                     factory=ClosingConnection)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=5000")
        return connection

    def _initialize(self):
        connection = self.connect()
        try:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.executescript(SCHEMA)
            now = utc_now()
            apply_migrations(connection, now)
            connection.execute("BEGIN IMMEDIATE")
            try:
                self.content_registry.publish(connection, now)
                connection.commit()
            except Exception:
                connection.rollback()
                raise
            connection.execute(
                "INSERT OR IGNORE INTO settings VALUES(1,?,?,?,?,?)",
                (dumps({"base_url": "", "model": "", "timeout_seconds": 300,
                        "structured_output": False, "max_concurrency": 1}),
                 dumps(NARRATION["defaults"]), 1, 0, now),
            )
            settings_row = connection.execute(
                "SELECT model_json FROM settings WHERE id=1"
            ).fetchone()
            existing_model = loads(settings_row["model_json"], {})
            if (not existing_model.get("base_url") and not existing_model.get("model") and
                    existing_model.get("timeout_seconds") == 60):
                existing_model["timeout_seconds"] = 300
                connection.execute(
                    "UPDATE settings SET model_json=?,updated_at=? WHERE id=1",
                    (dumps(existing_model), now),
                )
            connection.execute(
                "UPDATE generation_jobs SET status='interrupted', error_code='SERVER_RESTARTED', "
                "error_message='服务重启中断了生成', updated_at=? WHERE status IN ('running','cancel_requested')",
                (now,),
            )
            connection.execute(
                "UPDATE narrative_jobs SET status='interrupted', error_code='SERVER_RESTARTED', "
                "error_message='服务重启中断了叙事生成', retryable=1, updated_at=? "
                "WHERE status IN ('running','cancel_requested')", (now,))
        finally:
            connection.close()

    @staticmethod
    def _save_dict(row):
        current_step = row["current_step"] if "current_step" in row.keys() else 1
        return {
            "id": row["id"], "name": row["name"], "phase": row["phase"],
            "revision": row["revision"], "ruleset_version": row["ruleset_version"],
            "current_step": current_step,
            "narration": loads(row["preferences_json"], {}),
            "source_save_id": row["source_save_id"], "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    @staticmethod
    def _job_dict(row):
        return {
            "id": row["id"], "save_id": row["save_id"], "request_id": row["request_id"],
            "draft_revision": row["draft_revision"], "save_revision": row["save_revision"],
            "attempt": row["attempt"], "status": row["status"],
            "error": ({"code": row["error_code"], "message": row["error_message"]}
                      if row["error_code"] else None),
            "created_at": row["created_at"], "updated_at": row["updated_at"],
        }

    def get_settings(self, secret_configured=False, secret_persistence="memory_only"):
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM settings WHERE id=1").fetchone()
        model = loads(row["model_json"], {})
        capability = self.get_model_capability(model)
        response_format = self.get_response_format_capability(model)
        model["structured_output"] = bool(
            model.get("structured_output", False) and
            response_format["capability"] == "supported"
        )
        thinking_enabled = bool(row["thinking_enabled"])
        if capability["capability"] != "controlled":
            thinking_enabled = True
        model.update({"api_key_configured": bool(secret_configured),
                      "api_key_mask": "••••••••" if secret_configured else None,
                      "api_key_persistence": secret_persistence,
                      "thinking_enabled": thinking_enabled,
                      "thinking_capability": capability["capability"],
                      "thinking_strategy": capability["strategy"],
                      "thinking_confidence": capability["confidence"],
                      "thinking_message": capability["message"],
                      "thinking_probed_at": capability.get("probed_at"),
                      "structured_output_capability": response_format["capability"],
                      "structured_output_message": response_format["message"],
                      "structured_output_probed_at": response_format.get("probed_at")})
        narration = loads(row["narration_json"], {})
        return {"model": model,
                "narration": {"pace": narration.get("pace"),
                              "tendency": narration.get("tone"),
                              "detail": narration.get("detail")},
                "revision": row["revision"]}

    def get_model_config(self):
        with self.connect() as connection:
            row = connection.execute("SELECT model_json,thinking_enabled FROM settings WHERE id=1").fetchone()
        config = loads(row["model_json"], {})
        capability = self.get_model_capability(config)
        response_format = self.get_response_format_capability(config)
        config["structured_output"] = bool(
            config.get("structured_output", False) and
            response_format["capability"] == "supported"
        )
        config["thinking_enabled"] = (bool(row["thinking_enabled"])
                                        if capability["capability"] == "controlled" else True)
        config["thinking_strategy"] = capability["strategy"]
        config["thinking_confidence"] = capability["confidence"]
        return config

    @staticmethod
    def _capability_message(capability, confidence, strategy):
        if capability == "unsupported":
            return "当前服务不支持关闭思考；模型将保持默认思考或不受应用控制。"
        if confidence == "accepted_bundle":
            return "服务接受兼容参数组合，无法逐项证明。"
        if confidence == "verified":
            return f"已验证思考控制参数：{strategy}。"
        return "思考控制能力未测试，请先测试连接。"

    def get_model_capability(self, config):
        endpoint, model, version = thinking_capability_key(config)
        if not endpoint or not model:
            return {"capability": "unknown", "strategy": None, "confidence": "unknown",
                    "last_failure": None, "probed_at": None,
                    "message": self._capability_message("unknown", "unknown", None)}
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM model_capabilities WHERE endpoint=? AND model=? AND config_version=?",
                (endpoint, model, version)).fetchone()
        if row is None:
            return {"capability": "unknown", "strategy": None, "confidence": "unknown",
                    "last_failure": None, "probed_at": None,
                    "message": self._capability_message("unknown", "unknown", None)}
        result = dict(row)
        result["message"] = self._capability_message(
            result["capability"], result["confidence"], result["strategy"])
        return result

    def set_model_capability(self, config, result):
        endpoint, model, version = thinking_capability_key(config)
        now = utc_now()
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO model_capabilities(endpoint,model,config_version,capability,strategy,"
                "confidence,last_failure,probed_at) VALUES(?,?,?,?,?,?,?,?) "
                "ON CONFLICT(endpoint,model,config_version) DO UPDATE SET capability=excluded.capability,"
                "strategy=excluded.strategy,confidence=excluded.confidence,last_failure=excluded.last_failure,"
                "probed_at=excluded.probed_at",
                (endpoint, model, version, result.get("capability", "unknown"),
                 result.get("strategy"), result.get("confidence", "unknown"),
                 result.get("last_failure"), now))
        stored = self.get_model_capability(config)
        stored["message"] = result.get("message") or stored["message"]
        return stored

    def invalidate_model_capability(self, config, failure=None):
        return self.set_model_capability(config, {
            "capability": "unknown", "strategy": None, "confidence": "unknown",
            "last_failure": failure or "运行时明确拒绝已缓存的思考参数",
            "message": "已缓存的思考控制参数被服务拒绝，请重新测试连接。",
        })

    @staticmethod
    def _response_format_capability_message(capability):
        if capability == "supported":
            return "已验证当前服务支持 response_format。"
        if capability == "unsupported":
            return "当前服务明确不支持 response_format，无法开启结构化输出。"
        return "response_format 能力未知，请先测试后再开启结构化输出。"

    def get_response_format_capability(self, config):
        endpoint, model, version = response_format_capability_key(config)
        unknown = {
            "capability": "unknown", "strategy": None, "last_failure": None,
            "probed_at": None,
            "message": self._response_format_capability_message("unknown"),
        }
        if not endpoint or not model:
            return unknown
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM response_format_capabilities "
                "WHERE endpoint=? AND model=? AND config_version=?",
                (endpoint, model, version)).fetchone()
        if row is None:
            return unknown
        result = dict(row)
        result["message"] = self._response_format_capability_message(result["capability"])
        return result

    def set_response_format_capability(self, config, result):
        endpoint, model, version = response_format_capability_key(config)
        if not endpoint or not model:
            raise DomainError("INVALID_INPUT", "response_format 能力缓存缺少服务地址或模型")
        now = utc_now()
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO response_format_capabilities(endpoint,model,config_version,"
                "capability,strategy,last_failure,probed_at) VALUES(?,?,?,?,?,?,?) "
                "ON CONFLICT(endpoint,model,config_version) DO UPDATE SET "
                "capability=excluded.capability,strategy=excluded.strategy,"
                "last_failure=excluded.last_failure,probed_at=excluded.probed_at",
                (endpoint, model, version, result.get("capability", "unknown"),
                 result.get("strategy"), result.get("last_failure"), now))
        stored = self.get_response_format_capability(config)
        stored["message"] = result.get("message") or stored["message"]
        return stored

    def update_model_settings(self, data):
        self._validate_request_id(data)
        allowed = {"base_url", "model", "timeout_seconds", "structured_output", "max_concurrency", "thinking_enabled"}
        transient = {"api_key", "expected_revision", "request_id",
                     "structured_output_probe_token"}
        unknown = set(data) - allowed - transient
        if unknown:
            raise DomainError("INVALID_INPUT", "存在未知设置字段", fields={key: "未知字段" for key in unknown})
        if "expected_revision" not in data:
            raise DomainError("INVALID_INPUT", "模型设置缺少expected_revision",
                              fields={"expected_revision": "缺少字段"})
        if "api_key" in data and (not isinstance(data["api_key"], str) or len(data["api_key"]) > 10000):
            raise DomainError("INVALID_INPUT", "API Key 格式无效",
                              fields={"api_key": "必须是长度不超过10000的文本"})
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT * FROM settings WHERE id=1").fetchone()
            expected = data.get("expected_revision")
            if expected != row["revision"]:
                connection.rollback()
                raise DomainError("REVISION_CONFLICT", "设置已被其他请求修改", 409)
            config = loads(row["model_json"], {})
            config.update({key: data[key] for key in allowed - {"thinking_enabled"} if key in data})
            fields = {}
            if config.get("base_url"):
                from urllib.parse import urlparse
                parsed = urlparse(config["base_url"])
                if (parsed.scheme not in {"http", "https"} or not parsed.netloc or
                        parsed.username is not None or parsed.password is not None or
                        parsed.query or parsed.fragment):
                    fields["base_url"] = "必须是有效的HTTP/HTTPS地址"
            if not isinstance(config.get("model", ""), str) or len(config.get("model", "")) > 300:
                fields["model"] = "模型标识格式无效"
            timeout = config.get("timeout_seconds", 300)
            if type(timeout) not in (int, float) or not 1 <= timeout <= 600:
                fields["timeout_seconds"] = "必须在1至600秒之间"
            concurrency = config.get("max_concurrency", 1)
            if type(concurrency) is not int or not 1 <= concurrency <= 16:
                fields["max_concurrency"] = "必须是1至16的整数"
            if type(config.get("structured_output", False)) is not bool:
                fields["structured_output"] = "必须是布尔值"
            if "thinking_enabled" in data and type(data["thinking_enabled"]) is not bool:
                fields["thinking_enabled"] = "必须是布尔值"
            capability = self.get_model_capability(config)
            response_format = self.get_response_format_capability(config)
            if (config.get("structured_output", False) and
                    response_format["capability"] != "supported"):
                fields["structured_output"] = (
                    "当前服务不支持 response_format" if
                    response_format["capability"] == "unsupported" else
                    "response_format 能力未知，请先测试后再开启")
            requested_thinking = data.get("thinking_enabled", bool(row["thinking_enabled"]))
            if capability["capability"] != "controlled":
                if data.get("thinking_enabled") is False:
                    fields["thinking_enabled"] = ("当前服务不支持关闭思考" if
                                                   capability["capability"] == "unsupported" else
                                                   "思考控制能力未知，请先测试连接")
                requested_thinking = True
            if fields:
                connection.rollback()
                raise DomainError("INVALID_INPUT", "模型设置无效", fields=fields)
            revision = row["revision"] + 1
            connection.execute(
                "UPDATE settings SET model_json=?, thinking_enabled=?, revision=?, updated_at=? WHERE id=1",
                (dumps(config), 1 if capability["capability"] != "controlled" else
                 int(requested_thinking), revision, utc_now()),
            )
            connection.commit()
        return revision

    def write_model_settings_with_secret(self, data, secret_store):
        """Encrypt the credential first, then update settings and secret storage."""
        prepared = secret_store.prepare_api_key(data["api_key"]) if "api_key" in data else None
        revision = self.update_model_settings(data)
        if prepared is not None:
            secret_store.commit_api_key(prepared)
        return revision

    def update_narration_settings(self, data):
        self._validate_request_id(data)
        unknown = set(data) - {"request_id", "expected_revision", "pace", "tendency", "detail"}
        if unknown:
            raise DomainError("INVALID_INPUT", "存在未知叙事设置字段",
                              fields={key: "未知字段" for key in unknown})
        if "expected_revision" not in data:
            raise DomainError("INVALID_INPUT", "叙事设置缺少expected_revision",
                              fields={"expected_revision": "缺少字段"})
        narration = {"pace": data.get("pace"), "tone": data.get("tendency"),
                     "detail": data.get("detail")}
        valid = {"pace": {"slow", "fast", "dynamic"}, "tone": {"casual", "balanced", "combat"},
                 "detail": {"concise", "standard", "detailed"}}
        fields = {key: "无效枚举值" for key in valid if narration[key] not in valid[key]}
        if fields:
            raise DomainError("INVALID_INPUT", "叙事设置无效", fields=fields)
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT revision FROM settings WHERE id=1").fetchone()
            expected = data.get("expected_revision")
            if expected != row["revision"]:
                connection.rollback()
                raise DomainError("REVISION_CONFLICT", "设置已被其他请求修改", 409)
            revision = row["revision"] + 1
            connection.execute("UPDATE settings SET narration_json=?, revision=?, updated_at=? WHERE id=1",
                               (dumps(narration), revision, utc_now()))
            connection.commit()
        return revision

    def create_save(self, name="新存档", request_id=None):
        if not isinstance(request_id, str) or not request_id or len(request_id) > 200:
            raise DomainError("INVALID_INPUT", "request_id不能为空", fields={"request_id": "格式无效"})
        if not isinstance(name, str) or not name.strip() or len(name.strip()) > 100:
            raise DomainError("INVALID_INPUT", "存档名称必须是1至100个字符", fields={"name": "格式无效"})
        save_id, now = new_id(), utc_now()
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            previous = connection.execute("SELECT response_json FROM mutation_requests WHERE scope='create-save' AND request_id=?",
                                          (request_id,)).fetchone()
            if previous:
                response = loads(previous["response_json"])
                if response.get("request_fingerprint") != dumps({"name": name.strip()}):
                    connection.rollback()
                    raise DomainError("IDEMPOTENCY_CONFLICT", "request_id已用于不同的新建存档请求", 409)
                connection.commit()
                return response["result"]
            narration = loads(connection.execute("SELECT narration_json FROM settings WHERE id=1").fetchone()[0], {})
            connection.execute("INSERT INTO saves VALUES(?,?,?,?,?,?,?,?,?)",
                               (save_id, name.strip(), "draft", 0, RULESET_VERSION, dumps(narration), None, now, now))
            connection.execute("INSERT INTO drafts VALUES(?,?,?,?,?)", (save_id, "{}", 1, 0, now))
            response = self._save_dict(connection.execute("SELECT * FROM saves WHERE id=?", (save_id,)).fetchone())
            record = {"request_fingerprint": dumps({"name": name.strip()}), "result": response}
            connection.execute("INSERT INTO mutation_requests VALUES('create-save',?,?,?)",
                               (request_id, dumps(record), now))
            connection.commit()
        return response

    def create_save_from_request(self, data):
        unknown = set(data) - {"request_id", "name"}
        if unknown:
            raise DomainError("INVALID_INPUT", "存在未知新建存档字段",
                              fields={key: "未知字段" for key in unknown})
        return self.create_save(data.get("name", "新存档"), data.get("request_id"))

    def list_saves(self):
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT s.*, (SELECT id FROM generation_jobs j WHERE j.save_id=s.id ORDER BY j.created_at DESC LIMIT 1) generation_id, "
                "(SELECT status FROM generation_jobs j WHERE j.save_id=s.id ORDER BY j.created_at DESC LIMIT 1) generation_status, "
                "(SELECT updated_at FROM generation_jobs j WHERE j.save_id=s.id ORDER BY j.created_at DESC LIMIT 1) generation_updated_at, "
                "(SELECT data_json FROM characters c WHERE c.save_id=s.id) character_json, "
                "(SELECT current_step FROM drafts d WHERE d.save_id=s.id) current_step "
                "FROM saves s ORDER BY s.updated_at DESC"
            ).fetchall()
        result = []
        for row in rows:
            item = self._save_dict(row)
            character = loads(row["character_json"], {})
            generation = None
            if row["generation_id"]:
                generation = {"job_id": row["generation_id"],
                              "status": row["generation_status"],
                              "updated_at": row["generation_updated_at"]}
            item.update({"generation": generation,
                         "character_name": character.get("identity", {}).get("name")})
            result.append(item)
        return result

    def get_save(self, save_id, connection=None):
        own = connection is None
        connection = connection or self.connect()
        try:
            row = connection.execute("SELECT * FROM saves WHERE id=?", (save_id,)).fetchone()
            if not row:
                raise DomainError("SAVE_NOT_FOUND", "存档不存在", 404)
            result = self._save_dict(row)
            draft_row = connection.execute("SELECT current_step FROM drafts WHERE save_id=?", (save_id,)).fetchone()
            result["current_step"] = draft_row["current_step"] if draft_row else 1
            job = connection.execute(
                "SELECT id,status,updated_at FROM generation_jobs WHERE save_id=? "
                "ORDER BY created_at DESC LIMIT 1", (save_id,)
            ).fetchone()
            result["generation"] = ({"job_id": job["id"], "status": job["status"],
                                     "updated_at": job["updated_at"]} if job else None)
            return result
        finally:
            if own:
                connection.close()

    def patch_save(self, save_id, data):
        self._validate_request_id(data)
        unknown = set(data) - {"request_id", "expected_revision", "name"}
        if unknown:
            raise DomainError("INVALID_INPUT", "存在未知存档字段",
                              fields={key: "未知字段" for key in unknown})
        name = data.get("name")
        if not isinstance(name, str) or not name.strip() or len(name.strip()) > 100:
            raise DomainError("INVALID_INPUT", "存档名称必须是1至100个字符", fields={"name": "格式无效"})
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            save = self.get_save(save_id, connection)
            if data.get("expected_revision") != save["revision"]:
                connection.rollback()
                raise DomainError("REVISION_CONFLICT", "存档版本冲突", 409)
            connection.execute("UPDATE saves SET name=?,revision=revision+1,updated_at=? WHERE id=?",
                               (name.strip(), utc_now(), save_id))
            connection.commit()
        return self.get_save(save_id)

    def delete_save(self, save_id, data):
        self._validate_request_id(data)
        unknown = set(data) - {"request_id", "expected_revision", "confirm"}
        if unknown:
            raise DomainError("INVALID_INPUT", "存在未知删除字段",
                              fields={key: "未知字段" for key in unknown})
        if data.get("confirm") is not True:
            raise DomainError("CONFIRMATION_REQUIRED", "删除存档需要明确确认", 400)
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            save = self.get_save(save_id, connection)
            expected = data.get("expected_revision")
            if expected is None:
                connection.rollback()
                raise DomainError("INVALID_INPUT", "删除请求缺少expected_revision",
                                  fields={"expected_revision": "缺少字段"})
            if expected != save["revision"]:
                connection.rollback()
                raise DomainError("REVISION_CONFLICT", "存档版本冲突", 409)
            connection.execute("UPDATE generation_jobs SET status='cancelled', updated_at=? WHERE save_id=? AND status IN ('queued','running','cancel_requested')",
                               (utc_now(), save_id))
            connection.execute("DELETE FROM saves WHERE id=?", (save_id,))
            connection.commit()

    def update_save_preferences(self, save_id, data):
        self._validate_request_id(data)
        unknown = set(data) - {"request_id", "expected_revision", "pace", "tone", "detail"}
        if unknown:
            raise DomainError("INVALID_INPUT", "存在未知存档偏好字段",
                              fields={key: "未知字段" for key in unknown})
        if "expected_revision" not in data:
            raise DomainError("INVALID_INPUT", "存档偏好缺少expected_revision",
                              fields={"expected_revision": "缺少字段"})
        narration = {key: data.get(key) for key in ("pace", "tone", "detail")}
        valid = {"pace": {"slow", "fast", "dynamic"}, "tone": {"casual", "balanced", "combat"},
                 "detail": {"concise", "standard", "detailed"}}
        fields = {key: "无效枚举值" for key in valid if narration[key] not in valid[key]}
        if fields:
            raise DomainError("INVALID_INPUT", "存档叙事偏好无效", fields=fields)
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            save = self.get_save(save_id, connection)
            if data.get("expected_revision") != save["revision"]:
                connection.rollback()
                raise DomainError("REVISION_CONFLICT", "存档版本冲突", 409)
            connection.execute("UPDATE saves SET preferences_json=?,revision=revision+1,updated_at=? WHERE id=?",
                               (dumps(narration), utc_now(), save_id))
            connection.commit()
        return self.get_save(save_id)

    def get_draft(self, save_id, connection=None):
        own = connection is None
        connection = connection or self.connect()
        try:
            self.get_save(save_id, connection)
            row = connection.execute("SELECT * FROM drafts WHERE save_id=?", (save_id,)).fetchone()
            return {"save_id": save_id, "data": loads(row["data_json"], {}),
                    "current_step": row["current_step"], "draft_revision": row["revision"],
                    "updated_at": row["updated_at"]}
        finally:
            if own:
                connection.close()

    def put_draft(self, save_id, body):
        self._validate_request_id(body)
        unknown = set(body) - {"request_id", "expected_revision", "expected_save_revision",
                               "current_step", "data"}
        if unknown:
            raise DomainError("INVALID_INPUT", "存在未知草稿请求字段",
                              fields={key: "未知字段" for key in unknown})
        missing = [field for field in ("expected_revision", "expected_save_revision", "data")
                   if field not in body]
        if missing:
            raise DomainError("INVALID_INPUT", "草稿请求缺少必要字段",
                              fields={field: "缺少字段" for field in missing})
        if not isinstance(body.get("data"), dict):
            raise DomainError("INVALID_INPUT", "data必须是对象", fields={"data": "类型无效"})
        errors = validate_draft(body["data"])
        current_step = body.get("current_step", 1)
        if type(current_step) is not int or not 1 <= current_step <= 13:
            errors["current_step"] = "必须是1至13的整数"
        if errors:
            raise DomainError("INVALID_INPUT", "角色草稿无效", fields=errors)
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            save = self.get_save(save_id, connection)
            if save["phase"] == "ready":
                connection.rollback()
                raise DomainError("SAVE_ALREADY_READY", "已确认角色的存档不能修改草稿", 409)
            draft = self.get_draft(save_id, connection)
            if body.get("expected_revision") != draft["draft_revision"]:
                connection.rollback()
                raise DomainError("REVISION_CONFLICT", "角色草稿版本冲突", 409,
                                  fields={"draft_revision": draft["draft_revision"]})
            expected_save = body.get("expected_save_revision")
            if expected_save != save["revision"]:
                connection.rollback()
                raise DomainError("REVISION_CONFLICT", "存档版本冲突", 409)
            now = utc_now()
            connection.execute("UPDATE drafts SET data_json=?,current_step=?,revision=revision+1,updated_at=? WHERE save_id=?",
                               (dumps(body["data"]), current_step, now, save_id))
            connection.execute("DELETE FROM candidates WHERE save_id=?", (save_id,))
            connection.execute("UPDATE saves SET phase='draft',revision=revision+1,updated_at=? WHERE id=?", (now, save_id))
            connection.commit()
        return {"save": self.get_save(save_id), "draft": self.get_draft(save_id)}

    def create_generation(self, save_id, body, model_configured):
        request_id = body.get("request_id")
        if not isinstance(request_id, str) or not request_id or len(request_id) > 200:
            raise DomainError("INVALID_INPUT", "request_id不能为空", fields={"request_id": "格式无效"})
        feedback = body.get("feedback", "")
        unknown = set(body) - {"request_id", "draft_revision", "expected_save_revision", "feedback"}
        if unknown:
            raise DomainError("INVALID_INPUT", "存在未知生成请求字段",
                              fields={key: "未知字段" for key in unknown})
        missing = [field for field in ("draft_revision", "expected_save_revision") if field not in body]
        if missing:
            raise DomainError("INVALID_INPUT", "生成请求缺少必要字段",
                              fields={field: "缺少字段" for field in missing})
        if not isinstance(feedback, str) or len(feedback) > 4000:
            raise DomainError("INVALID_INPUT", "重新生成意见格式无效", fields={"feedback": "长度不能超过4000"})
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute("SELECT * FROM generation_jobs WHERE save_id=? AND request_id=?",
                                          (save_id, request_id)).fetchone()
            if existing:
                expected_save = body.get("expected_save_revision")
                same_request = (body.get("draft_revision") == existing["draft_revision"] and
                                expected_save == existing["save_revision"] and
                                feedback == existing["feedback"])
                if not same_request:
                    connection.rollback()
                    raise DomainError("IDEMPOTENCY_CONFLICT", "request_id已用于不同的生成请求", 409)
                connection.commit()
                return self._job_dict(existing), False
            save = self.get_save(save_id, connection)
            draft = self.get_draft(save_id, connection)
            if save["phase"] == "ready":
                connection.rollback()
                raise DomainError("SAVE_ALREADY_READY", "角色已经确认", 409)
            if not model_configured:
                connection.rollback()
                raise DomainError("MODEL_NOT_CONFIGURED", "模型未配置，无法生成角色", 409)
            if body.get("draft_revision") != draft["draft_revision"]:
                connection.rollback()
                raise DomainError("REVISION_CONFLICT", "角色草稿版本冲突", 409)
            expected_save = body.get("expected_save_revision")
            if expected_save != save["revision"]:
                connection.rollback()
                raise DomainError("REVISION_CONFLICT", "存档版本冲突", 409)
            errors = validate_draft(draft["data"], complete=True)
            if errors:
                connection.rollback()
                raise DomainError("INVALID_INPUT", "角色草稿尚未完成", fields=errors)
            active = connection.execute(
                "SELECT id FROM generation_jobs WHERE save_id=? AND status IN ('queued','running','cancel_requested')", (save_id,)
            ).fetchone()
            if active:
                connection.rollback()
                raise DomainError("GENERATION_ACTIVE", "该存档已有活动生成任务", 409,
                                  fields={"job_id": active["id"]}, retryable=True)
            attempt = connection.execute("SELECT COALESCE(MAX(attempt),0)+1 FROM generation_jobs WHERE save_id=?", (save_id,)).fetchone()[0]
            job_id, now = new_id(), utc_now()
            connection.execute("INSERT INTO generation_jobs VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                               (job_id, save_id, request_id, draft["draft_revision"], save["revision"],
                                attempt, "queued", feedback, None, None, now, now))
            connection.commit()
        return self.get_job(save_id, job_id), True

    @staticmethod
    def _validate_request_id(body):
        request_id = body.get("request_id")
        if not isinstance(request_id, str) or not request_id or len(request_id) > 200:
            raise DomainError("INVALID_INPUT", "request_id不能为空", fields={"request_id": "格式无效"})

    def get_job(self, save_id, job_id):
        with self.connect() as connection:
            self.get_save(save_id, connection)
            row = connection.execute("SELECT * FROM generation_jobs WHERE id=? AND save_id=?", (job_id, save_id)).fetchone()
        if not row:
            raise DomainError("JOB_NOT_FOUND", "生成任务不存在", 404)
        return self._job_dict(row)

    def list_queued_jobs(self):
        with self.connect() as connection:
            return [(row["save_id"], row["id"]) for row in connection.execute(
                "SELECT save_id,id FROM generation_jobs WHERE status='queued' ORDER BY created_at"
            ).fetchall()]

    def claim_job(self, save_id, job_id):
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            changed = connection.execute("UPDATE generation_jobs SET status='running',updated_at=? "
                                         "WHERE id=? AND save_id=? AND status='queued'",
                                         (utc_now(), job_id, save_id)).rowcount
            if not changed:
                connection.rollback()
                return None
            row = connection.execute(
                "SELECT j.*,d.data_json FROM generation_jobs j JOIN drafts d ON d.save_id=j.save_id WHERE j.id=?", (job_id,)
            ).fetchone()
            connection.commit()
        return {"job": self._job_dict(row), "draft": loads(row["data_json"], {}), "feedback": row["feedback"]}

    def complete_job(self, save_id, job_id, candidate_data):
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT * FROM generation_jobs WHERE id=? AND save_id=?", (job_id, save_id)).fetchone()
            if not row:
                connection.rollback()
                return "missing"
            save_row = connection.execute("SELECT * FROM saves WHERE id=?", (save_id,)).fetchone()
            draft_row = connection.execute("SELECT revision FROM drafts WHERE save_id=?", (save_id,)).fetchone()
            if row["status"] == "cancel_requested":
                connection.execute("UPDATE generation_jobs SET status='cancelled',updated_at=? WHERE id=?",
                                   (utc_now(), job_id))
                connection.commit()
                return "cancelled"
            if row["status"] != "running":
                connection.rollback()
                return row["status"]
            stale = (not save_row or not draft_row or save_row["phase"] == "ready" or
                     save_row["revision"] != row["save_revision"] or
                     draft_row["revision"] != row["draft_revision"])
            now = utc_now()
            if stale:
                connection.execute("UPDATE generation_jobs SET status='stale',error_code='GENERATION_STALE',"
                                   "error_message='草稿或存档版本已变化',updated_at=? WHERE id=?", (now, job_id))
                connection.commit()
                return "stale"
            candidate_id = new_id()
            connection.execute("DELETE FROM candidates WHERE save_id=?", (save_id,))
            connection.execute("INSERT INTO candidates VALUES(?,?,?,?,?,?)",
                               (candidate_id, save_id, job_id, row["draft_revision"], dumps(candidate_data), now))
            connection.execute("UPDATE generation_jobs SET status='succeeded',updated_at=? WHERE id=?", (now, job_id))
            connection.execute("UPDATE saves SET phase='review',revision=revision+1,updated_at=? WHERE id=?", (now, save_id))
            connection.commit()
        return "succeeded"

    def fail_job(self, save_id, job_id, code, message):
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT status FROM generation_jobs WHERE id=? AND save_id=?", (job_id, save_id)).fetchone()
            if not row:
                connection.rollback()
                return
            if row["status"] == "cancel_requested":
                connection.execute("UPDATE generation_jobs SET status='cancelled',updated_at=? WHERE id=?", (utc_now(), job_id))
            elif row["status"] == "running":
                connection.execute("UPDATE generation_jobs SET status='failed',error_code=?,error_message=?,updated_at=? WHERE id=?",
                                   (code, message[:1000], utc_now(), job_id))
            connection.commit()

    def cancel_job(self, save_id, job_id):
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            self.get_save(save_id, connection)
            row = connection.execute("SELECT * FROM generation_jobs WHERE id=? AND save_id=?", (job_id, save_id)).fetchone()
            if not row:
                connection.rollback()
                raise DomainError("JOB_NOT_FOUND", "生成任务不存在", 404)
            if row["status"] == "queued":
                status = "cancelled"
            elif row["status"] == "running":
                status = "cancel_requested"
            else:
                connection.commit()
                return self._job_dict(row)
            connection.execute("UPDATE generation_jobs SET status=?,updated_at=? WHERE id=?", (status, utc_now(), job_id))
            connection.commit()
        return self.get_job(save_id, job_id)

    def get_candidate(self, save_id):
        with self.connect() as connection:
            self.get_save(save_id, connection)
            row = connection.execute("SELECT * FROM candidates WHERE save_id=?", (save_id,)).fetchone()
        if not row:
            raise DomainError("CANDIDATE_NOT_FOUND", "当前没有可确认的角色候选", 404)
        return {"id": row["id"], "save_id": row["save_id"], "job_id": row["job_id"],
                "draft_revision": row["draft_revision"], "data": loads(row["data_json"], {}),
                "created_at": row["created_at"]}

    def confirm_character(self, save_id, body):
        request_id = body.get("request_id")
        if not isinstance(request_id, str) or not request_id or len(request_id) > 200:
            raise DomainError("INVALID_INPUT", "request_id不能为空", fields={"request_id": "格式无效"})
        unknown = set(body) - {"request_id", "candidate_id", "expected_save_revision",
                               "expected_draft_revision"}
        if unknown:
            raise DomainError("INVALID_INPUT", "存在未知确认请求字段",
                              fields={key: "未知字段" for key in unknown})
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            previous = connection.execute("SELECT character_id,request_fingerprint FROM confirmation_requests WHERE save_id=? AND request_id=?",
                                          (save_id, request_id)).fetchone()
            if previous:
                row = connection.execute("SELECT * FROM characters WHERE id=?", (previous["character_id"],)).fetchone()
                fingerprint = dumps({"candidate_id": body.get("candidate_id")})
                if previous["request_fingerprint"] != fingerprint:
                    connection.rollback()
                    raise DomainError("IDEMPOTENCY_CONFLICT", "request_id已用于不同的确认请求", 409)
                connection.commit()
                return self._character_dict(row)
            missing = [field for field in ("candidate_id", "expected_save_revision", "expected_draft_revision")
                       if field not in body]
            if missing:
                connection.rollback()
                raise DomainError("INVALID_INPUT", "确认请求缺少必要字段",
                                  fields={field: "缺少字段" for field in missing})
            save = self.get_save(save_id, connection)
            if save["phase"] == "ready":
                connection.rollback()
                raise DomainError("SAVE_ALREADY_READY", "该存档已有正式角色", 409)
            candidate = connection.execute("SELECT * FROM candidates WHERE id=? AND save_id=?",
                                           (body.get("candidate_id"), save_id)).fetchone()
            if not candidate:
                connection.rollback()
                raise DomainError("CANDIDATE_NOT_FOUND", "候选不存在或已被替换", 404)
            job = connection.execute("SELECT status FROM generation_jobs WHERE id=?", (candidate["job_id"],)).fetchone()
            draft = self.get_draft(save_id, connection)
            if not job or job["status"] != "succeeded":
                connection.rollback()
                raise DomainError("GENERATION_STALE", "候选来源任务不可确认", 409)
            if body.get("expected_save_revision") != save["revision"] or body.get("expected_draft_revision") != draft["draft_revision"]:
                connection.rollback()
                raise DomainError("REVISION_CONFLICT", "存档或草稿版本冲突", 409)
            if candidate["draft_revision"] != draft["draft_revision"]:
                connection.rollback()
                raise DomainError("GENERATION_STALE", "候选已过期", 409)
            candidate_data = loads(candidate["data_json"], {})
            source = dict(draft["data"])
            for key in ("faction", "faction_id", "factions"):
                source.pop(key, None)
            location_id = source["start_location_id"]
            try:
                expected_power = POWER_BY_RANK[source["rank"]]
                if (candidate_data["rank"] != source["rank"] or
                        candidate_data["base_power"] != expected_power or
                        candidate_data["effective_power"] != expected_power or
                        candidate_data["exp"] != 0 or
                        candidate_data["exp_to_next"] != EXP_THRESHOLDS[source["rank"]]):
                    raise ValueError("derived fields")
                proposal_shape = {
                    "attributes": candidate_data["attributes"],
                    "resources": {
                        key: {"max": value["max"], "reason": value["reason"]}
                        for key, value in candidate_data["resources"].items()
                    },
                    "summary": candidate_data["summary"],
                    "strengths": candidate_data["strengths"],
                    "limitations": candidate_data["limitations"],
                    "warnings": candidate_data["warnings"],
                }
                validate_candidate(proposal_shape, source["rank"])
            except (KeyError, TypeError, ValueError):
                connection.rollback()
                raise DomainError("GENERATION_STALE", "候选权威字段无效，无法确认", 409) from None
            except ProviderError:
                connection.rollback()
                raise DomainError("GENERATION_STALE", "候选权威字段无效，无法确认", 409) from None
            now, character_id = utc_now(), new_id()
            character_data = {
                "identity": source,
                "attributes": candidate_data["attributes"],
                "resources": candidate_data["resources"],
                "rank": candidate_data["rank"], "base_power": candidate_data["base_power"],
                "effective_power": candidate_data["effective_power"],
                "power_modifiers": candidate_data.get("power_modifiers", []),
                "exp": 0, "exp_to_next": candidate_data["exp_to_next"],
                "summary": candidate_data["summary"], "strengths": candidate_data.get("strengths", []),
                "limitations": candidate_data.get("limitations", []), "warnings": candidate_data.get("warnings", []),
                "start_location_id": location_id, "current_location_id": location_id,
                "provenance": {"ruleset_version": RULESET_VERSION, "output_contract_version": "character-candidate/1",
                               "prompt_version": "character-generator/1", "candidate_id": candidate["id"],
                               "confirmed_at": now},
            }
            connection.execute("INSERT INTO characters VALUES(?,?,?,?,?)",
                               (character_id, save_id, candidate["id"], dumps(character_data), now))
            connection.execute("INSERT INTO confirmation_requests VALUES(?,?,?,?)",
                               (save_id, request_id, character_id,
                                dumps({"candidate_id": body.get("candidate_id")})))
            connection.execute("UPDATE generation_jobs SET status=CASE WHEN status='running' THEN 'cancel_requested' ELSE 'stale' END,updated_at=? "
                               "WHERE save_id=? AND id<>? AND status IN ('queued','running')",
                               (now, save_id, candidate["job_id"]))
            connection.execute("UPDATE saves SET phase='ready',revision=revision+1,updated_at=? WHERE id=?", (now, save_id))
            connection.commit()
        return self.get_character(save_id)

    @staticmethod
    def _character_dict(row):
        return {"id": row["id"], "save_id": row["save_id"], "candidate_id": row["candidate_id"],
                "data": loads(row["data_json"], {}), "confirmed_at": row["confirmed_at"]}

    def get_character(self, save_id):
        with self.connect() as connection:
            self.get_save(save_id, connection)
            row = connection.execute("SELECT * FROM characters WHERE save_id=?", (save_id,)).fetchone()
        if not row:
            raise DomainError("CHARACTER_NOT_FOUND", "正式角色尚未确认", 404)
        return self._character_dict(row)

    def game_bootstrap(self, save_id):
        save = self.get_save(save_id)
        if save["phase"] != "ready":
            raise DomainError("SAVE_NOT_READY", "存档尚未完成角色确认", 409)
        return {"save": save, "character": self.get_character(save_id),
                "stage": "phase-one-complete", "gm_turns_available": False}

    def export_save(self, save_id):
        with self.connect() as connection:
            connection.execute("BEGIN")
            save = self.get_save(save_id, connection)
            draft = self.get_draft(save_id, connection)
            candidate_row = connection.execute("SELECT * FROM candidates WHERE save_id=?", (save_id,)).fetchone()
            character_row = connection.execute("SELECT * FROM characters WHERE save_id=?", (save_id,)).fetchone()
            state_row = connection.execute("SELECT * FROM story_states WHERE save_id=?", (save_id,)).fetchone()
            payload = {
                "format": "fantasy-simulator-save", "schema_version": 2 if state_row else 1,
                "exported_at": utc_now(), "application_version": "phase-2" if state_row else "phase-1",
                "ruleset_version": save["ruleset_version"], "source_save_id": save["id"],
                "save": {"name": save["name"], "phase": save["phase"], "revision": save["revision"]},
                "narration": save["narration"],
                "draft": {"data": draft["data"], "current_step": draft["current_step"],
                          "draft_revision": draft["draft_revision"]},
                "candidate": (loads(candidate_row["data_json"], {}) if candidate_row else None),
                "character": (loads(character_row["data_json"], {}) if character_row else None),
                "extensions": {},
            }
            if state_row:
                tables = ("narrative_jobs", "turns", "turn_versions", "turn_snapshots", "effect_receipts", "journals",
                          "memories", "memory_sources", "story_arcs", "story_arc_sources",
                          "story_arc_parent_sources", "context_policies", "location_nodes",
                          "reputation_change_history")
                narrative = {"story_state": dict(state_row), "content_revision_id": state_row["content_revision_id"]}
                narrative["story_state"]["state_json"] = loads(state_row["state_json"], {})
                narrative["story_state"]["state_json"].setdefault("npcs", {})
                revision_row = connection.execute(
                    "SELECT * FROM content_revisions WHERE id=?",
                    (state_row["content_revision_id"],)).fetchone()
                revision_documents = connection.execute(
                    "SELECT * FROM content_revision_documents WHERE revision_id=? ORDER BY category,ordinal",
                    (state_row["content_revision_id"],)).fetchall()
                narrative["content_revision"] = {
                    "id": revision_row["id"], "manifest": loads(revision_row["manifest_json"], {}),
                    "documents": [{key: (row[key].hex() if key == "raw_bytes" else row[key])
                                   for key in row.keys()} for row in revision_documents]}
                for table in tables:
                    rows = connection.execute(f"SELECT * FROM {table} WHERE save_id=?", (save_id,)).fetchall() \
                        if "save_id" in {r[1] for r in connection.execute(f"PRAGMA table_info({table})").fetchall()} \
                        else connection.execute(
                            f"SELECT t.* FROM {table} t WHERE EXISTS (SELECT 1 FROM memories m WHERE m.id=t.memory_id AND m.save_id=?)"
                            if table == "memory_sources" else
                            f"SELECT t.* FROM {table} t WHERE EXISTS (SELECT 1 FROM story_arcs a WHERE a.id=t.arc_id AND a.save_id=?)",
                            (save_id,)).fetchall()
                    narrative[table] = [dict(row) for row in rows]
                for table, fields in {"turns": ("action_json", "options_json", "changes_json"),
                                      "narrative_jobs": ("input_json", "context_manifest_json", "result_json"),
                                      "turn_versions": ("raw_response_json", "proposals_json", "authoritative_changes_json"),
                                      "turn_snapshots": ("state_json",), "journals": ("changes_json",),
                                      "memories": ("people_json", "locations_json", "keywords_json", "facts_json", "unresolved_json"),
                                      "story_arcs": ("key_events_json", "unresolved_json"),
                                      "context_policies": ("source_json",)}.items():
                    for row in narrative[table]:
                        for field in fields:
                            row[field] = loads(row[field], {} if field.endswith("state_json") else [])
                            if table == "turn_snapshots" and field == "state_json":
                                row[field].get("state", {}).setdefault("npcs", {})
                payload["narrative"] = narrative
            connection.commit()
        return payload

    def validate_import(self, payload):
        if not isinstance(payload, dict):
            raise DomainError("IMPORT_INVALID", "导入内容必须是JSON对象", fields={"file": "格式无效"})
        sensitive_fragments = ("secret", "password", "token", "authorization", "credential",
                               "api_key", "apikey", "access_key", "private_key")

        def walk(value, path="$"):
            if isinstance(value, dict):
                for key, child in value.items():
                    normalized_key = str(key).lower().replace("-", "_").replace(" ", "_")
                    if any(fragment in normalized_key for fragment in sensitive_fragments):
                        raise DomainError("IMPORT_CONTAINS_SECRET", "导入文件包含禁止的密钥字段",
                                          fields={path + "." + str(key): "敏感字段禁止导入"})
                    walk(child, path + "." + str(key))
            elif isinstance(value, list):
                for index, child in enumerate(value):
                    walk(child, f"{path}[{index}]")
        walk(payload)
        fields = {}
        if payload.get("format") != "fantasy-simulator-save":
            fields["format"] = "不支持的文件格式"
        if payload.get("schema_version") not in {1, 2}:
            fields["schema_version"] = "不支持的存档主版本"
        if not isinstance(payload.get("save"), dict):
            fields["save"] = "缺少存档元数据"
        if not isinstance(payload.get("draft"), dict) or not isinstance(payload.get("draft", {}).get("data"), dict):
            fields["draft"] = "缺少角色草稿"
        for optional_object in ("candidate", "character", "extensions"):
            if payload.get(optional_object) is not None and not isinstance(payload.get(optional_object), dict):
                fields[optional_object] = "必须是对象或null"
        if fields:
            raise DomainError("IMPORT_INCOMPATIBLE", "存档格式不兼容", fields=fields)
        allowed_top = {"format", "schema_version", "exported_at", "application_version",
                       "ruleset_version", "source_save_id", "save", "narration", "draft",
                       "candidate", "character", "extensions", "narrative"}
        unknown_top = set(payload) - allowed_top
        if unknown_top:
            fields.update({key: "未知顶层字段" for key in unknown_top})
        if isinstance(payload.get("extensions"), dict) and set(payload["extensions"]):
            fields["extensions"] = "当前版本不接受扩展字段"
        if payload.get("schema_version") == 2:
            narrative = payload.get("narrative")
            if not isinstance(narrative, dict):
                fields["narrative"] = "v2存档缺少叙事数据"
            else:
                allowed_narrative = {"story_state", "content_revision_id", "narrative_jobs",
                                     "turns", "turn_versions",
                                     "turn_snapshots", "effect_receipts", "journals", "memories",
                                     "memory_sources", "story_arcs", "story_arc_sources",
                                     "story_arc_parent_sources", "context_policies", "location_nodes",
                                     "reputation_change_history", "content_revision"}
                if set(narrative) != allowed_narrative:
                    fields["narrative"] = "叙事容器字段不完整或包含未知字段"
                revision = narrative.get("content_revision_id")
                if not isinstance(revision, str):
                    fields["narrative.content_revision_id"] = "内容版本无效"
                content_revision = narrative.get("content_revision")
                if not isinstance(content_revision, dict) or set(content_revision) != {"id", "manifest", "documents"}:
                    fields["narrative.content_revision"] = "内容版本快照无效"
                elif content_revision.get("id") != revision:
                    fields["narrative.content_revision.id"] = "内容版本ID不一致"
        for optional_text in ("exported_at", "application_version", "ruleset_version", "source_save_id"):
            value = payload.get(optional_text)
            if value is not None and (not isinstance(value, str) or len(value) > 200):
                fields[optional_text] = "必须是长度不超过200的文本"
        if payload.get("ruleset_version") != RULESET_VERSION:
            fields["ruleset_version"] = "不支持的世界规则版本"
        allowed_save = {"name", "phase", "revision"}
        unknown_save = set(payload["save"]) - allowed_save
        if unknown_save:
            fields.update({"save." + key: "未知存档字段" for key in unknown_save})
        allowed_draft = {"data", "current_step", "draft_revision"}
        unknown_draft = set(payload["draft"]) - allowed_draft
        if unknown_draft:
            fields.update({"draft." + key: "未知草稿容器字段" for key in unknown_draft})
        name = payload["save"].get("name")
        phase = payload["save"].get("phase")
        if not isinstance(name, str) or not name.strip() or len(name.strip()) > 100:
            fields["save.name"] = "存档名称无效"
        if type(payload["save"].get("revision")) is not int or payload["save"].get("revision", -1) < 0:
            fields["save.revision"] = "存档修订必须是非负整数"
        if phase not in {"draft", "review", "ready"}:
            fields["save.phase"] = "存档阶段无效"
        draft_data = payload["draft"]["data"]
        fields.update({"draft." + key: value for key, value in validate_draft(draft_data).items()})
        current_step = payload["draft"].get("current_step", 1)
        if type(current_step) is not int or not 1 <= current_step <= 13:
            fields["draft.current_step"] = "必须是1至13的整数"
        if phase in {"review", "ready"} and current_step != 13:
            fields["draft.current_step"] = "review/ready存档必须停留在生成步骤"
        draft_revision = payload["draft"].get("draft_revision", 0)
        if type(draft_revision) is not int or draft_revision < 0:
            fields["draft.draft_revision"] = "草稿修订必须是非负整数"
        candidate = payload.get("candidate")
        normalized_candidate = None
        if isinstance(candidate, dict):
            self_rank = draft_data.get("rank")
            proposal = dict(candidate)
            candidate_keys = set(candidate)
            allowed_candidate_keys = {"attributes", "resources", "summary", "strengths", "limitations",
                                      "warnings", "rank", "base_power", "effective_power",
                                      "power_modifiers", "exp", "exp_to_next"}
            if candidate_keys - allowed_candidate_keys:
                fields["candidate"] = "角色候选包含未知字段"
            for derived in ("rank", "base_power", "effective_power", "power_modifiers", "exp", "exp_to_next"):
                proposal.pop(derived, None)
            if isinstance(proposal.get("resources"), dict):
                for key, item in proposal["resources"].items():
                    if isinstance(item, dict) and set(item) - {"current", "max", "reason"}:
                        fields[f"candidate.resources.{key}"] = "资源包含未知字段"
                    if isinstance(item, dict) and item.get("current") != item.get("max"):
                        fields[f"candidate.resources.{key}.current"] = "开局当前资源必须等于最大值"
                proposal["resources"] = {
                    key: ({"max": item.get("max"), "reason": item.get("reason")}
                          if isinstance(item, dict) else item)
                    for key, item in proposal["resources"].items()
                }
            try:
                normalized_candidate = validate_candidate(proposal, self_rank)
                for derived in ("rank", "base_power", "effective_power", "power_modifiers", "exp", "exp_to_next"):
                    if candidate.get(derived) != normalized_candidate[derived]:
                        raise ValueError(derived)
            except (ProviderError, KeyError, TypeError, ValueError):
                fields["candidate"] = "角色候选不符合输出契约"
        narration = payload.get("narration")
        if (not isinstance(narration, dict) or set(narration) != {"pace", "tone", "detail"} or
                narration.get("pace") not in {"slow", "fast", "dynamic"} or
                narration.get("tone") not in {"casual", "balanced", "combat"} or
                narration.get("detail") not in {"concise", "standard", "detailed"}):
            fields["narration"] = "叙事偏好无效"
        if phase == "draft" and (candidate is not None or payload.get("character") is not None):
            fields["save.phase"] = "draft存档不能包含候选或正式角色"
        if phase == "review" and not isinstance(payload.get("candidate"), dict):
            fields["candidate"] = "review存档必须包含候选"
        if phase == "review" and payload.get("character") is not None:
            fields["character"] = "review存档不能包含正式角色"
        if phase == "ready" and not isinstance(payload.get("character"), dict):
            fields["character"] = "ready存档必须包含正式角色"
        if phase == "ready" and not isinstance(candidate, dict):
            fields["candidate"] = "ready存档必须包含来源候选"
        character = payload.get("character")
        if isinstance(character, dict):
            allowed_character = {"identity", "attributes", "resources", "rank", "base_power",
                                 "effective_power", "power_modifiers", "exp", "exp_to_next",
                                 "summary", "strengths", "limitations", "warnings",
                                 "start_location_id", "current_location_id", "provenance"}
            unknown_character = set(character) - allowed_character
            if unknown_character:
                fields.update({"character." + key: "未知正式角色字段" for key in unknown_character})
            identity = character.get("identity")
            if not isinstance(identity, dict):
                fields["character.identity"] = "正式角色缺少身份信息"
            else:
                fields.update({"character.identity." + key: value
                               for key, value in validate_draft(identity, complete=True).items()})
                if identity != draft_data:
                    fields["character.identity"] = "正式角色身份必须与草稿一致"
            provenance = character.get("provenance")
            allowed_provenance = {"ruleset_version", "output_contract_version", "prompt_version",
                                  "candidate_id", "confirmed_at"}
            if (not isinstance(provenance, dict) or set(provenance) != allowed_provenance or
                    any(not isinstance(provenance.get(key), str) or not provenance[key] or
                        len(provenance[key]) > 200 for key in allowed_provenance) or
                    provenance.get("ruleset_version") != RULESET_VERSION or
                    provenance.get("output_contract_version") != "character-candidate/1"):
                fields["character.provenance"] = "正式角色来源信息无效"
            attributes = character.get("attributes")
            if not isinstance(attributes, dict) or set(attributes) != {"con", "int", "cha"}:
                fields["character.attributes"] = "正式角色缺少长期属性"
            else:
                for key in ("con", "int", "cha"):
                    item = attributes.get(key)
                    if (not isinstance(item, dict) or set(item) != {"value", "reason"} or
                            type(item.get("value")) is not int or not 1 <= item["value"] <= 100 or
                            not isinstance(item.get("reason"), str)):
                        fields[f"character.attributes.{key}"] = "属性值必须为1至100整数"
            resources = character.get("resources")
            if not isinstance(resources, dict) or set(resources) != {"hp", "mp", "sp", "st"}:
                fields["character.resources"] = "正式角色缺少短期资源"
            else:
                for key in ("hp", "mp", "sp", "st"):
                    item = resources.get(key)
                    if (not isinstance(item, dict) or set(item) != {"current", "max", "reason"} or
                            type(item.get("current")) is not int or type(item.get("max")) is not int or
                            not 1 <= item["current"] <= item["max"] <= 9999 or
                            item["current"] != item["max"] or not isinstance(item.get("reason"), str)):
                        fields[f"character.resources.{key}"] = "开局资源必须为1至9999且当前值等于最大值"
            rank = character.get("rank")
            if type(rank) is not int or rank not in POWER_BY_RANK:
                fields["character.rank"] = "等阶必须为1至10"
            else:
                if character.get("base_power") != POWER_BY_RANK[rank]:
                    fields["character.base_power"] = "基础战力与等阶不符"
                if character.get("effective_power") != POWER_BY_RANK[rank]:
                    fields["character.effective_power"] = "首版有效战力必须等于基础战力"
                if character.get("power_modifiers") != []:
                    fields["character.power_modifiers"] = "首版战力修正必须为空"
                if character.get("exp_to_next") != EXP_THRESHOLDS[rank]:
                    fields["character.exp_to_next"] = "经验阈值与等阶不符"
            if character.get("exp") != 0:
                fields["character.exp"] = "首版角色EXP必须为0"
            for location_field in ("start_location_id", "current_location_id"):
                if character.get(location_field) != draft_data.get("start_location_id"):
                    fields["character." + location_field] = "正式角色地点必须与草稿起点一致"
            for key in ("summary",):
                if not isinstance(character.get(key), str):
                    fields["character." + key] = "必须是文本"
            for key in ("strengths", "limitations", "warnings"):
                value = character.get(key)
                if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
                    fields["character." + key] = "必须是文本数组"
            if normalized_candidate is not None:
                comparable = {key: character.get(key) for key in
                              ("attributes", "resources", "rank", "base_power", "effective_power",
                               "power_modifiers", "exp", "exp_to_next", "summary", "strengths",
                               "limitations", "warnings")}
                expected = {key: normalized_candidate.get(key) for key in comparable}
                if comparable != expected:
                    fields["character"] = "正式角色必须与候选一致"
        if fields:
            raise DomainError("IMPORT_INVALID", "导入存档校验失败", fields=fields)
        character_name = None
        if isinstance(payload.get("character"), dict):
            character_name = payload["character"].get("identity", {}).get("name")
        normalized_character = None
        if isinstance(character, dict) and normalized_candidate is not None:
            normalized_character = {
                "identity": {key: draft_data[key] for key in draft_data},
                "attributes": normalized_candidate["attributes"],
                "resources": normalized_candidate["resources"],
                "rank": normalized_candidate["rank"],
                "base_power": normalized_candidate["base_power"],
                "effective_power": normalized_candidate["effective_power"],
                "power_modifiers": normalized_candidate["power_modifiers"],
                "exp": normalized_candidate["exp"],
                "exp_to_next": normalized_candidate["exp_to_next"],
                "summary": normalized_candidate["summary"],
                "strengths": normalized_candidate["strengths"],
                "limitations": normalized_candidate["limitations"],
                "warnings": normalized_candidate["warnings"],
                "start_location_id": draft_data["start_location_id"],
                "current_location_id": draft_data["start_location_id"],
                "provenance": ({key: character["provenance"][key] for key in allowed_provenance}
                               if isinstance(character.get("provenance"), dict) and
                               allowed_provenance.issubset(character["provenance"]) else {}),
            }
        pending = self._pending_requirement(payload)
        return {"valid": True, "schema_version": payload.get("schema_version"), "ruleset_version": payload.get("ruleset_version"),
                "source_save_id": payload.get("source_save_id"),
                "name": name.strip(), "phase": phase, "character_name": character_name,
                "warnings": ["导入时将分配新的本地存档ID"],
                "confirmation_required": bool(pending), "content_revision": pending,
                "normalized": {"name": name.strip(), "phase": phase,
                               "narration": {key: narration[key] for key in ("pace", "tone", "detail")},
                               "draft_data": {key: draft_data[key] for key in draft_data},
                               "current_step": current_step,
                               "candidate": normalized_candidate,
                               "character": normalized_character,
                               "narrative": loads(dumps(payload.get("narrative")))}}

    def import_save(self, request, allow_pending=True):
        if "payload" not in request:
            raise DomainError("INVALID_INPUT", "导入请求必须包含request_id和payload",
                              fields={"payload": "缺少字段"})
        self._validate_request_id(request)
        request_id = request["request_id"]
        payload = request["payload"]
        if not isinstance(payload, dict):
            raise DomainError("IMPORT_INVALID", "导入内容必须是JSON对象",
                              fields={"payload": "类型无效"})
        preview = self.validate_import(payload)
        pending = self._pending_requirement(payload)
        if pending and allow_pending:
            self._verify_content_revision_bundle(payload["narrative"]["content_revision"])
            return self._create_pending_import(request_id, payload, pending)
        if pending:
            raise DomainError("CONTENT_REVISION_TRUST_REQUIRED", "内容版本尚未显式信任", 409)
        normalized = preview["normalized"]
        save_id, now = new_id(), utc_now()
        source_id = payload.get("source_save_id")
        if source_id is not None and (not isinstance(source_id, str) or len(source_id) > 200):
            raise DomainError("IMPORT_INVALID", "来源存档ID无效",
                              fields={"source_save_id": "格式无效"})
        phase = normalized["phase"]
        imported_ruleset = payload.get("ruleset_version", RULESET_VERSION)
        if not isinstance(imported_ruleset, str) or not imported_ruleset or len(imported_ruleset) > 100:
            raise DomainError("IMPORT_INVALID", "世界规则版本无效",
                              fields={"ruleset_version": "格式无效"})
        draft_revision = payload["draft"].get("draft_revision", 0)
        with self.connect() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                response = self._import_save_in_connection(
                    connection, request_id, payload, normalized, save_id, source_id,
                    imported_ruleset, draft_revision, now, install_content=True)
                connection.commit()
            except DomainError:
                raise
            except (sqlite3.Error, KeyError, TypeError, ValueError):
                connection.rollback()
                raise DomainError("IMPORT_INVALID", "导入存档无法写入", fields={"payload": "结构无效"}) from None
        return response

    def _import_save_in_connection(self, connection, request_id, payload, normalized,
                                   save_id, source_id, imported_ruleset, draft_revision,
                                   now, install_content):
        previous = connection.execute(
            "SELECT response_json FROM mutation_requests WHERE scope='import-save' AND request_id=?",
            (request_id,)).fetchone()
        if previous:
            response = loads(previous["response_json"])
            if response.get("request_fingerprint") != dumps(payload):
                raise DomainError("IDEMPOTENCY_CONFLICT", "request_id已用于不同的导入请求", 409)
            return response["result"]
        connection.execute("INSERT INTO saves VALUES(?,?,?,?,?,?,?,?,?)",
                           (save_id, normalized["name"], normalized["phase"], 0,
                            imported_ruleset, dumps(normalized["narration"]), source_id,
                            now, now))
        connection.execute("INSERT INTO drafts VALUES(?,?,?,?,?)",
                           (save_id, dumps(normalized["draft_data"]), normalized["current_step"],
                            draft_revision, now))
        candidate_id = character_id = None
        if normalized["candidate"] is not None:
            job_id, candidate_id = new_id(), new_id()
            connection.execute("INSERT INTO generation_jobs VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                               (job_id, save_id, "import:" + new_id(), draft_revision, 0, 1,
                                "succeeded", "", None, None, now, now))
            connection.execute("INSERT INTO candidates VALUES(?,?,?,?,?,?)",
                               (candidate_id, save_id, job_id, draft_revision,
                                dumps(normalized["candidate"]), now))
        if normalized["character"] is not None:
            candidate_id = candidate_id or new_id()
            character_id = new_id()
            character = json.loads(dumps(normalized["character"]))
            character.setdefault("provenance", {})["candidate_id"] = candidate_id
            connection.execute("INSERT INTO characters VALUES(?,?,?,?,?)",
                               (character_id, save_id, candidate_id, dumps(character), now))
        if normalized.get("narrative") is not None:
            if install_content:
                self._install_content_revision(
                    connection, normalized["narrative"]["content_revision"], now)
            self._import_narrative(connection, save_id, normalized["narrative"], now,
                                   character_id, candidate_id)
        response = self._save_dict(connection.execute(
            "SELECT * FROM saves WHERE id=?", (save_id,)).fetchone())
        response["generation"] = None
        record = {"request_fingerprint": dumps(payload), "result": response}
        connection.execute("INSERT INTO mutation_requests VALUES('import-save',?,?,?)",
                           (request_id, dumps(record), now))
        return response

    def _pending_requirement(self, payload):
        narrative = payload.get("narrative") if isinstance(payload, dict) else None
        if not isinstance(narrative, dict):
            return None
        revision_id = narrative.get("content_revision_id")
        with self.connect() as connection:
            trusted = connection.execute(
                "SELECT trust_kind FROM trusted_content_revisions WHERE revision_id=?",
                (revision_id,)).fetchone()
        if trusted:
            return None
        bundle = narrative["content_revision"]
        self._verify_content_revision_bundle(bundle)
        return {"revision_id": revision_id,
                "documents": [{"document_id": item["document_id"],
                               "source_path": item["source_path"],
                               "raw_sha256": item["raw_sha256"],
                               "text_sha256": item["text_sha256"],
                               "byte_count": item["byte_count"]}
                              for item in bundle["documents"]],
                "prompt_version": bundle["manifest"].get("prompt_version")}

    def _create_pending_import(self, request_id, payload, requirement):
        payload_json = dumps(payload).encode("utf-8")
        import hashlib
        payload_hash = hashlib.sha256(payload_json).hexdigest()
        now, pending_id = utc_now(), new_id()
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "UPDATE pending_imports SET status='expired',payload_json=X'' "
                "WHERE status='pending' AND expires_at<=?", (now,))
            previous = connection.execute(
                "SELECT * FROM pending_imports WHERE request_id=?", (request_id,)).fetchone()
            if previous:
                if previous["payload_hash"] != payload_hash:
                    raise DomainError("IDEMPOTENCY_CONFLICT", "request_id已用于不同导入内容", 409)
                if previous["status"] == "expired":
                    raise DomainError("PENDING_IMPORT_EXPIRED", "待确认导入已失效", 409)
                connection.commit()
                return self._pending_view(previous, requirement)
            connection.execute(
                "INSERT INTO pending_imports VALUES(?,?,?,?,?,'pending',NULL,NULL,?,?)",
                (pending_id, request_id, requirement["revision_id"], payload_hash, payload_json,
                 now, utc_after(3600)))
            row = connection.execute("SELECT * FROM pending_imports WHERE id=?", (pending_id,)).fetchone()
            connection.commit()
        return self._pending_view(row, requirement)

    @staticmethod
    def _pending_view(row, requirement):
        return {"status": row["status"], "pending_import_id": row["id"],
                "revision_id": row["revision_id"], "expires_at": row["expires_at"],
                "confirmation_required": True, "content_revision": requirement,
                "result": loads(row["result_json"])}

    def trust_and_import(self, pending_id, request):
        self._validate_request_id(request)
        if set(request) != {"request_id", "confirm_revision_id", "confirm"} or request.get("confirm") is not True:
            raise DomainError("CONFIRMATION_REQUIRED", "必须显式确认内容版本", 400)
        now = utc_now()
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT * FROM pending_imports WHERE id=?", (pending_id,)).fetchone()
            if not row:
                raise DomainError("PENDING_IMPORT_NOT_FOUND", "待确认导入不存在", 404)
            if row["status"] == "imported":
                if row["trust_request_id"] != request["request_id"]:
                    raise DomainError("IDEMPOTENCY_CONFLICT", "待确认导入已由其他请求完成", 409)
                result = loads(row["result_json"]); connection.commit(); return result
            if row["status"] != "pending" or row["expires_at"] <= now:
                connection.execute("UPDATE pending_imports SET status='expired',payload_json=X'' WHERE id=?",
                                   (pending_id,))
                connection.commit()
                raise DomainError("PENDING_IMPORT_EXPIRED", "待确认导入已失效", 409)
            if request["confirm_revision_id"] != row["revision_id"]:
                raise DomainError("CONFIRMATION_MISMATCH", "确认的内容版本不匹配", 409)
            payload = loads(bytes(row["payload_json"]).decode("utf-8"))
            preview = self.validate_import(payload)
            normalized = preview["normalized"]
            bundle = payload["narrative"]["content_revision"]
            self._install_content_revision(connection, bundle, now)
            connection.execute(
                "INSERT INTO trusted_content_revisions VALUES(?,?,?) ON CONFLICT(revision_id) DO NOTHING",
                (row["revision_id"], "user", now))
            source_id = payload.get("source_save_id")
            result = self._import_save_in_connection(
                connection, "trusted:" + request["request_id"], payload, normalized,
                new_id(), source_id, payload.get("ruleset_version", RULESET_VERSION),
                payload["draft"].get("draft_revision", 0), now, install_content=False)
            connection.execute(
                "UPDATE pending_imports SET status='imported',trust_request_id=?,result_json=?,payload_json=X'' "
                "WHERE id=?", (request["request_id"], dumps(result), pending_id))
            connection.commit()
        return result

    @staticmethod
    def _verify_content_revision_bundle(bundle):
        revision_id = bundle["id"]
        manifest = bundle["manifest"]
        documents = bundle["documents"]
        if not isinstance(manifest, dict) or manifest.get("revision_id") != revision_id:
            raise DomainError("IMPORT_INVALID", "内容版本manifest无效",
                              fields={"narrative.content_revision.manifest": "版本不一致"})
        try:
            from .content_registry import revision_identity
        except ImportError:
            from content_registry import revision_identity
        calculated_revision, calculated_prompt = revision_identity(manifest)
        if calculated_revision != revision_id or calculated_prompt != manifest.get("prompt_version"):
            raise DomainError("IMPORT_INVALID", "内容版本身份哈希无效")
        if not isinstance(documents, list) or len(documents) != len(manifest.get("documents", [])):
            raise DomainError("IMPORT_INVALID", "内容版本文档数量无效")
        expected_columns = ["revision_id", "document_id", "category", "ordinal", "source_path",
                            "raw_bytes", "text_content", "raw_sha256", "text_sha256", "encoding",
                            "has_bom", "newline_style", "byte_count", "character_count", "line_count"]
        indexed_manifest = {item.get("document_id"): item for item in manifest.get("documents", [])
                            if isinstance(item, dict)}
        normalized = []
        for document in documents:
            if not isinstance(document, dict) or set(document) != set(expected_columns):
                raise DomainError("IMPORT_INVALID", "内容版本文档字段无效")
            if document["revision_id"] != revision_id or document["document_id"] not in indexed_manifest:
                raise DomainError("IMPORT_INVALID", "内容版本文档引用无效")
            try:
                raw = bytes.fromhex(document["raw_bytes"])
                text = raw.decode("utf-8-sig")
            except (ValueError, UnicodeError):
                raise DomainError("IMPORT_INVALID", "内容版本原始字节无效") from None
            import hashlib
            raw_hash = hashlib.sha256(raw).hexdigest()
            text_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
            manifest_document = indexed_manifest[document["document_id"]]
            if (raw_hash != document["raw_sha256"] or text_hash != document["text_sha256"] or
                    text != document["text_content"] or raw_hash != manifest_document.get("raw_sha256") or
                    text_hash != manifest_document.get("text_sha256") or len(raw) != document["byte_count"] or
                    len(text) != document["character_count"]):
                raise DomainError("IMPORT_INVALID", "内容版本哈希校验失败")
            normalized.append({**document, "raw_bytes": raw})
        return revision_id, manifest, normalized, expected_columns

    @staticmethod
    def _install_content_revision(connection, bundle, now):
        revision_id, manifest, normalized, expected_columns = Database._verify_content_revision_bundle(bundle)
        stored = connection.execute("SELECT manifest_json FROM content_revisions WHERE id=?",
                                    (revision_id,)).fetchone()
        manifest_json = dumps(manifest)
        if stored:
            if stored["manifest_json"] != manifest_json:
                raise DomainError("IMPORT_INVALID", "本地内容版本与导入快照冲突")
            return
        connection.execute("INSERT INTO content_revisions VALUES(?,?,?)",
                           (revision_id, manifest_json, now))
        for document in normalized:
            connection.execute(
                "INSERT INTO content_revision_documents VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                tuple(document[column] for column in expected_columns))

    def _import_narrative(self, connection, save_id, narrative, now,
                          character_id, candidate_id):
        revision_id = narrative.get("content_revision_id")
        if not connection.execute("SELECT 1 FROM content_revisions WHERE id=?", (revision_id,)).fetchone():
            raise DomainError("CONTENT_REVISION_NOT_FOUND", "导入所需内容版本不存在", 409,
                              fields={"content_revision_id": revision_id})
        tables = ("narrative_jobs", "turns", "turn_versions", "turn_snapshots",
                  "effect_receipts", "journals", "memories", "memory_sources", "story_arcs",
                  "story_arc_sources", "story_arc_parent_sources", "context_policies",
                  "location_nodes", "reputation_change_history")
        if any(not isinstance(narrative.get(table), list) for table in tables):
            raise DomainError("IMPORT_INVALID", "叙事对象图不完整", fields={"narrative": "缺少数组"})
        state_row = narrative.get("story_state")
        if not isinstance(state_row, dict) or not isinstance(state_row.get("state_json"), dict):
            raise DomainError("IMPORT_INVALID", "叙事权威状态无效", fields={"narrative.story_state": "无效"})
        expected_state_columns = [row[1] for row in connection.execute(
            "PRAGMA table_info(story_states)").fetchall()]
        if set(state_row) != set(expected_state_columns):
            raise DomainError("IMPORT_INVALID", "叙事权威状态字段无效")
        state = state_row["state_json"]
        self._validate_imported_story_state(state)
        maps = {key: {} for key in ("job", "turn", "version", "receipt", "memory", "arc", "policy",
                                    "location", "npc", "reputation_history", "character", "candidate")}
        old_candidate = state.get("character", {}).get("candidate_id")
        old_character = state.get("character", {}).get("id")
        if isinstance(old_candidate, str): maps["candidate"][old_candidate] = candidate_id
        if isinstance(old_character, str): maps["character"][old_character] = character_id
        for row in narrative["narrative_jobs"]: maps["job"][row["id"]] = new_id()
        for row in narrative["turns"]: maps["turn"][row["id"]] = new_id()
        for row in narrative["turn_versions"]: maps["version"][row["id"]] = new_id()
        for row in narrative["effect_receipts"]: maps["receipt"][row["id"]] = new_id()
        for row in narrative["memories"]: maps["memory"][row["id"]] = new_id()
        for row in narrative["story_arcs"]: maps["arc"][row["id"]] = new_id()
        for row in narrative["context_policies"]: maps["policy"][row["id"]] = new_id()
        for row in narrative["reputation_change_history"]: maps["reputation_history"][row["id"]] = new_id()
        for row in narrative["location_nodes"]:
            if not row.get("canonical"):
                maps["location"][row["id"]] = "dynamic." + new_id()
        for npc_id in state.get("npcs", {}):
            if not npc_id.startswith("canon.npc."):
                maps["npc"][npc_id] = "npc." + new_id()
        flat_map = {}
        for mapping in maps.values(): flat_map.update(mapping)

        def remap(value):
            if isinstance(value, str): return flat_map.get(value, value)
            if isinstance(value, list): return [remap(item) for item in value]
            if isinstance(value, dict): return {key: remap(item) for key, item in value.items()}
            return value

        expected_columns = {}
        for table in tables:
            expected_columns[table] = [row[1] for row in connection.execute(
                f"PRAGMA table_info({table})").fetchall()]
            for row in narrative[table]:
                if not isinstance(row, dict) or set(row) != set(expected_columns[table]):
                    raise DomainError("IMPORT_INVALID", "叙事表字段无效",
                                      fields={"narrative." + table: "字段不匹配"})
        turn_ids = {row["id"] for row in narrative["turns"]}
        version_ids = {row["id"] for row in narrative["turn_versions"]}
        job_ids = {row["id"] for row in narrative["narrative_jobs"]}
        memory_ids = {row["id"] for row in narrative["memories"]}
        arc_ids = {row["id"] for row in narrative["story_arcs"]}
        version_turns = {row["id"]: row["turn_id"] for row in narrative["turn_versions"]}
        if len(turn_ids) != len(narrative["turns"]) or len(version_ids) != len(narrative["turn_versions"]):
            raise DomainError("IMPORT_INVALID", "剧情节点或版本ID重复")
        for turn in narrative["turns"]:
            if turn["current_version_id"] not in version_ids or version_turns.get(turn["current_version_id"]) != turn["id"]:
                raise DomainError("IMPORT_INVALID", "当前剧情版本引用不闭合")
        if state_row.get("current_turn_id") is not None and state_row["current_turn_id"] not in turn_ids:
            raise DomainError("IMPORT_INVALID", "当前剧情节点引用不闭合")
        if state.get("current_turn_id") != state_row.get("current_turn_id"):
            raise DomainError("IMPORT_INVALID", "权威状态当前节点不一致")
        if state.get("state_version") != state_row.get("state_version"):
            raise DomainError("IMPORT_INVALID", "权威状态版本不一致")
        if state.get("content_revision_id") != revision_id:
            raise DomainError("IMPORT_INVALID", "权威状态内容版本不一致")
        for version in narrative["turn_versions"]:
            if version["turn_id"] not in turn_ids:
                raise DomainError("IMPORT_INVALID", "剧情版本引用不存在节点")
        for receipt in narrative["effect_receipts"]:
            if receipt["turn_id"] not in turn_ids or receipt["turn_version_id"] not in version_ids:
                raise DomainError("IMPORT_INVALID", "效果收据引用不闭合")
        for snapshot in narrative["turn_snapshots"]:
            if snapshot["turn_id"] not in turn_ids:
                raise DomainError("IMPORT_INVALID", "节点快照引用不闭合")
            if snapshot["snapshot_schema_version"] != "turn-snapshot/1" or not isinstance(snapshot["state_json"], dict):
                raise DomainError("IMPORT_INVALID", "节点快照schema无效")
            frozen = snapshot["state_json"]
            if set(frozen) != {"state", "memories"} or not isinstance(frozen["memories"], list):
                raise DomainError("IMPORT_INVALID", "节点快照结构无效")
            self._validate_imported_story_state(frozen["state"])
        for journal in narrative["journals"]:
            if journal["turn_id"] not in turn_ids:
                raise DomainError("IMPORT_INVALID", "纪事引用不闭合")
        for memory in narrative["memories"]:
            if (memory["source_turn_id"] not in turn_ids or
                    memory["source_turn_version_id"] not in version_ids or
                    version_turns[memory["source_turn_version_id"]] != memory["source_turn_id"] or
                    (memory["superseded_by"] is not None and memory["superseded_by"] not in memory_ids)):
                raise DomainError("IMPORT_INVALID", "长期记忆引用不闭合")
        for source in narrative["memory_sources"]:
            if source["memory_id"] not in memory_ids or source["turn_version_id"] not in version_ids:
                raise DomainError("IMPORT_INVALID", "长期记忆来源不闭合")
        for arc in narrative["story_arcs"]:
            if arc["job_id"] not in job_ids or arc["start_sequence"] > arc["end_sequence"]:
                raise DomainError("IMPORT_INVALID", "故事弧引用或范围无效")
        for source in narrative["story_arc_sources"]:
            if (source["arc_id"] not in arc_ids or source["turn_id"] not in turn_ids or
                    source["turn_version_id"] not in version_ids or
                    version_turns[source["turn_version_id"]] != source["turn_id"]):
                raise DomainError("IMPORT_INVALID", "故事弧节点来源不闭合")
        for source in narrative["story_arc_parent_sources"]:
            if source["arc_id"] not in arc_ids or source["parent_arc_id"] not in arc_ids:
                raise DomainError("IMPORT_INVALID", "故事弧父来源不闭合")
        for policy in narrative["context_policies"]:
            if policy["replacement_arc_id"] not in arc_ids:
                raise DomainError("IMPORT_INVALID", "上下文策略引用不闭合")
        location_ids = {row["id"] for row in narrative["location_nodes"]}
        if state.get("location", {}).get("id") not in location_ids:
            raise DomainError("IMPORT_INVALID", "当前地点引用不闭合")
        ordered = ("narrative_jobs", "turns", "turn_versions", "turn_snapshots",
                   "effect_receipts", "journals", "memories", "memory_sources", "story_arcs",
                   "story_arc_sources", "story_arc_parent_sources", "context_policies",
                   "location_nodes", "reputation_change_history")
        json_fields = {"narrative_jobs": {"input_json", "context_manifest_json", "result_json"},
                       "turns": {"action_json", "options_json", "changes_json"},
                       "turn_versions": {"raw_response_json", "proposals_json", "authoritative_changes_json"},
                       "turn_snapshots": {"state_json"}, "journals": {"changes_json"},
                       "memories": {"people_json", "locations_json", "keywords_json", "facts_json", "unresolved_json"},
                       "story_arcs": {"key_events_json", "unresolved_json"},
                       "context_policies": {"source_json"}}
        for table in ordered:
            columns = expected_columns[table]
            for raw_row in narrative[table]:
                row = remap(raw_row)
                if "save_id" in row: row["save_id"] = save_id
                if table == "narrative_jobs":
                    row["request_id"] = "import:" + new_id()
                    if row["status"] in {"queued", "running", "cancel_requested"}:
                        row.update({"status": "interrupted", "error_code": "IMPORT_RETRY_REQUIRED",
                                    "error_message": "导入后需要显式重试", "retryable": 1})
                for field in json_fields.get(table, set()):
                    if row[field] is not None and not isinstance(row[field], str):
                        if table == "turn_snapshots" and field == "state_json":
                            frozen = row[field]
                            original_frozen = raw_row[field]
                            frozen_state = frozen["state"]
                            original_snapshot_state = original_frozen["state"]
                            frozen_state["inventory"] = self._remap_id_map(original_snapshot_state["inventory"], remap)
                            frozen_state["quests"] = self._remap_id_map(original_snapshot_state["quests"], remap)
                            frozen_state["regional_quests"] = self._remap_id_map(
                                original_snapshot_state["regional_quests"], remap)
                            frozen_state["locations"] = self._remap_id_map(original_snapshot_state["locations"], remap)
                            frozen_state["npcs"] = self._remap_id_map(original_snapshot_state["npcs"], remap)
                            frozen_state["bonds"] = self._remap_bond_map(original_snapshot_state["bonds"], remap)
                            self._derive_imported_story_state(frozen_state)
                            for memory in frozen["memories"]:
                                if not isinstance(memory, dict):
                                    raise DomainError("IMPORT_INVALID", "节点快照记忆无效")
                        row[field] = dumps(row[field])
                placeholders = ",".join("?" for _ in columns)
                connection.execute(f"INSERT INTO {table}({','.join(columns)}) VALUES({placeholders})",
                                   tuple(row[column] for column in columns))
        original_state = state_row["state_json"]
        state = remap(original_state)
        state["inventory"] = self._remap_id_map(original_state["inventory"], remap)
        state["quests"] = self._remap_id_map(original_state["quests"], remap)
        state["regional_quests"] = self._remap_id_map(original_state["regional_quests"], remap)
        state["locations"] = self._remap_id_map(original_state["locations"], remap)
        state["npcs"] = self._remap_id_map(original_state["npcs"], remap)
        state["bonds"] = self._remap_bond_map(original_state["bonds"], remap)
        self._derive_imported_story_state(state)
        state["state_version"] = state_row["state_version"]
        state["current_turn_id"] = remap(state_row.get("current_turn_id"))
        connection.execute("INSERT INTO story_states VALUES(?,?,?,?,?,?,?)",
                           (save_id, state_row["state_version"], state["current_turn_id"], revision_id,
                            dumps(state), now, now))

    @staticmethod
    def _remap_id_map(value, remap):
        result = {}
        for old_key, item in value.items():
            mapped = remap(item)
            new_key = remap(old_key)
            if not isinstance(mapped, dict) or mapped.get("id") != new_key:
                raise DomainError("IMPORT_INVALID", "ID映射键值不一致")
            result[new_key] = mapped
        return result

    @staticmethod
    def _remap_bond_map(value, remap):
        result = {}
        for old_key, item in value.items():
            mapped = remap(item)
            new_key = remap(old_key)
            if not isinstance(mapped, dict) or mapped.get("npc_id") != new_key:
                raise DomainError("IMPORT_INVALID", "羁绊映射键值不一致")
            result[new_key] = mapped
        return result

    @staticmethod
    def _derive_imported_story_state(state):
        try:
            from .narrative_contract import bond_level, reputation_level
        except ImportError:
            from narrative_contract import bond_level, reputation_level
        character = state["character"]
        character["alive"] = character["resources"]["hp"]["current"] > 0
        character["status"] = "normal" if character["alive"] else "dead"
        effects = [] if character["alive"] else ["dead"]
        for key, effect in {"mp": "mana_depleted", "sp": "mental_collapse", "st": "exhausted"}.items():
            if character["resources"][key]["current"] == 0:
                effects.append(effect)
        character["status_effects"] = effects
        threshold = EXP_THRESHOLDS[character["rank"]]
        character["breakthrough_eligible"] = threshold is not None and character["exp"] >= threshold
        equipment_power = sum(item.get("power", 0) for item in state["inventory"].values()
                              if item.get("equipped"))
        if equipment_power > int(POWER_BY_RANK[character["rank"]] * .4):
            raise DomainError("IMPORT_INVALID", "装备战力超过基础战力40%")
        Database._validate_import_power_modifiers(state, equipment_power)
        character["equipment_power"] = equipment_power
        character["base_power"] = POWER_BY_RANK[character["rank"]]
        character["exp_to_next"] = EXP_THRESHOLDS[character["rank"]]
        character["effective_power"] = max(
            0, POWER_BY_RANK[character["rank"]] + equipment_power +
            sum(item.get("value", 0) for item in character.get("power_modifiers", [])))
        for reputation in state["reputations"].values():
            reputation["level"] = reputation_level(reputation["value"])
        for bond in state["bonds"].values():
            bond["level"] = bond_level(bond["value"])
        try:
            from .story_repository import SAFE_PUBLIC_STARTS, start_prerequisite
        except ImportError:
            from story_repository import SAFE_PUBLIC_STARTS, start_prerequisite
        location_id = state["location"]["id"]
        expected = start_prerequisite(character["identity"], location_id)
        stored = state["location"].get("prerequisite")
        resolution = stored.get("resolution") if isinstance(stored, dict) else None
        audit = state.get("world_flags", {}).get("legacy_start_prerequisites")
        if expected["status"] == "required":
            valid_legacy = (resolution == "accept_legacy_protection" and
                            state["location"].get("legacy_start_protection") is True and
                            isinstance(audit, dict) and audit.get("location_id") == location_id and
                            set(audit.get("grants", [])) == set(expected["requirements"]) and
                            audit.get("source") == "explicit_pre_opening_resolution")
            if valid_legacy:
                expected.update({"status": "satisfied", "resolution": resolution, "options": []})
            else:
                state["location"]["legacy_start_protection"] = False
        elif resolution == "relocate" and location_id not in SAFE_PUBLIC_STARTS:
            raise DomainError("IMPORT_INVALID", "relocate起点不是合法公开地点")
        state["location"]["prerequisite"] = expected

    @staticmethod
    def _validate_import_start_prerequisite(state):
        try:
            from .story_repository import SAFE_PUBLIC_STARTS, start_prerequisite
        except ImportError:
            from story_repository import SAFE_PUBLIC_STARTS, start_prerequisite
        character = state["character"]
        location_id = state["location"]["id"]
        expected = start_prerequisite(character["identity"], location_id)
        stored = state["location"].get("prerequisite")
        resolution = stored.get("resolution") if isinstance(stored, dict) else None
        if resolution == "relocate" and location_id not in SAFE_PUBLIC_STARTS:
            raise DomainError("IMPORT_INVALID", "relocate起点不是合法公开地点")
        if expected["status"] == "required" and resolution == "accept_legacy_protection":
            audit = state.get("world_flags", {}).get("legacy_start_prerequisites")
            if not (state["location"].get("legacy_start_protection") is True and
                    isinstance(audit, dict) and audit.get("location_id") == location_id and
                    set(audit.get("grants", [])) == set(expected["requirements"]) and
                    audit.get("source") == "explicit_pre_opening_resolution"):
                raise DomainError("IMPORT_INVALID", "危险起点legacy防护审计无效")

    @staticmethod
    def _validate_import_power_modifiers(state, equipment_power):
        try:
            from .narrative_contract import canonical_power_exception_applies
        except ImportError:
            from narrative_contract import canonical_power_exception_applies
        character = state["character"]
        modifiers = character.get("power_modifiers")
        if not isinstance(modifiers, list) or len(modifiers) > 100:
            raise DomainError("IMPORT_INVALID", "战力修正结构无效")
        seen = set()
        for item in modifiers:
            if (not isinstance(item, dict) or set(item) != {"id", "value", "reason", "temporary",
                    "category", "severity", "canonical_exception"} or
                    not isinstance(item["id"], str) or not item["id"] or item["id"] in seen or
                    type(item["value"]) is not int or not -1000000 <= item["value"] <= 1000000 or
                    not isinstance(item["reason"], str) or type(item["temporary"]) is not bool or
                    item["category"] not in {"environment", "status", "counter", "tactics", "equipment", "other"} or
                    item["severity"] not in {"minor", "moderate", "major", "extreme"} or
                    (item["canonical_exception"] is not None and not isinstance(item["canonical_exception"], str))):
                raise DomainError("IMPORT_INVALID", "战力修正字段无效")
            seen.add(item["id"])
            if item["severity"] in {"major", "extreme"}:
                if not canonical_power_exception_applies(
                        item["canonical_exception"], state, item["value"]):
                    raise DomainError("IMPORT_INVALID", "重大战力修正的正典例外不适用于当前状态")
        rank = character["rank"]
        total = POWER_BY_RANK[rank] + equipment_power + sum(item["value"] for item in modifiers)
        next_two = POWER_BY_RANK.get(rank + 2)
        ordinary = POWER_BY_RANK[rank] + equipment_power + sum(
            item["value"] for item in modifiers if item["severity"] != "extreme")
        if next_two is not None and ordinary >= next_two:
            raise DomainError("IMPORT_INVALID", "普通战力修正覆盖两阶差距")
        if rank < 10 and total >= POWER_BY_RANK[10] and not any(
                item["severity"] == "extreme" and item["canonical_exception"] for item in modifiers):
            raise DomainError("IMPORT_INVALID", "普通战力修正跨越十阶鸿沟")

    @staticmethod
    def _validate_imported_story_state(state):
        required = {"schema_version", "state_version", "content_revision_id", "current_turn_id",
                    "narration", "time", "location", "character", "inventory", "currency_copper",
                    "quests", "regional_quests", "bonds", "reputations", "locations", "npcs", "world_flags"}
        if not isinstance(state, dict) or set(state) != required or state.get("schema_version") != "story-state/1":
            raise DomainError("IMPORT_INVALID", "story state schema无效")
        if type(state.get("state_version")) is not int or state["state_version"] < 0:
            raise DomainError("IMPORT_INVALID", "story state版本无效")
        character = state.get("character")
        if (not isinstance(character, dict) or not isinstance(character.get("id"), str) or
                not isinstance(character.get("candidate_id"), str) or
                type(character.get("rank")) is not int or character["rank"] not in POWER_BY_RANK):
            raise DomainError("IMPORT_INVALID", "story state角色等阶无效")
        rank = character["rank"]
        if character.get("base_power") != POWER_BY_RANK[rank] or character.get("exp_to_next") != EXP_THRESHOLDS[rank]:
            raise DomainError("IMPORT_INVALID", "story state角色派生值无效")
        if type(character.get("exp")) is not int or character["exp"] < 0 or (
                EXP_THRESHOLDS[rank] is not None and character["exp"] > EXP_THRESHOLDS[rank]):
            raise DomainError("IMPORT_INVALID", "story state经验无效")
        resources = character.get("resources")
        if not isinstance(resources, dict) or set(resources) != {"hp", "mp", "sp", "st"}:
            raise DomainError("IMPORT_INVALID", "story state资源无效")
        for resource in resources.values():
            if (not isinstance(resource, dict) or type(resource.get("current")) is not int or
                    type(resource.get("max")) is not int or not 0 <= resource["current"] <= resource["max"] <= 9999):
                raise DomainError("IMPORT_INVALID", "story state资源范围无效")
        attributes = character.get("attributes")
        if not isinstance(attributes, dict) or set(attributes) != {"con", "int", "cha"}:
            raise DomainError("IMPORT_INVALID", "story state属性无效")
        if any(not isinstance(item, dict) or type(item.get("value")) is not int or
               not 1 <= item["value"] <= 100 for item in attributes.values()):
            raise DomainError("IMPORT_INVALID", "story state属性范围无效")
        reputations = state.get("reputations")
        try:
            from .narrative_contract import REPUTATION_KEYS, QUEST_STATES, reputation_level
        except ImportError:
            from narrative_contract import REPUTATION_KEYS, QUEST_STATES, reputation_level
        if not isinstance(reputations, dict) or tuple(reputations) != REPUTATION_KEYS:
            raise DomainError("IMPORT_INVALID", "story state固定声望无效")
        for key, reputation in reputations.items():
            if (not isinstance(reputation, dict) or reputation.get("key") != key or
                    type(reputation.get("value")) is not int or not -100 <= reputation["value"] <= 100):
                raise DomainError("IMPORT_INVALID", "story state声望值无效")
        for collection in (state.get("quests"), state.get("regional_quests")):
            if not isinstance(collection, dict) or any(
                    not isinstance(item, dict) or item.get("id") != key or item.get("status") not in QUEST_STATES
                    for key, item in collection.items()):
                raise DomainError("IMPORT_INVALID", "story state任务无效")
        for map_name in ("inventory", "quests", "regional_quests", "locations", "npcs"):
            collection = state.get(map_name)
            if not isinstance(collection, dict) or any(
                    not isinstance(item, dict) or item.get("id") != key
                    for key, item in collection.items()):
                raise DomainError("IMPORT_INVALID", f"story state {map_name}键值不一致")
        for npc in state["npcs"].values():
            allowed = {"id", "name", "description", "source", "created_turn_version_id"}
            if (set(npc) - allowed or not isinstance(npc.get("name"), str) or
                    not isinstance(npc.get("description"), str) or not isinstance(npc.get("source"), str)):
                raise DomainError("IMPORT_INVALID", "story state动态NPC无效")
        inventory = state["inventory"]
        for key, item in inventory.items():
            if (set(item) != {"id", "name", "description", "quantity", "power", "equipped", "source"} or
                    not isinstance(item["name"], str) or not isinstance(item["description"], str) or
                    type(item["quantity"]) is not int or not 1 <= item["quantity"] <= 1000000 or
                    type(item["power"]) is not int or not 0 <= item["power"] <= 1000000 or
                    type(item["equipped"]) is not bool or not isinstance(item["source"], str)):
                raise DomainError("IMPORT_INVALID", "story state物品结构无效")
        for group in ("skills", "talents"):
            values = character.get(group)
            if not isinstance(values, list) or len(values) > 100:
                raise DomainError("IMPORT_INVALID", f"story state {group}结构无效")
            ids = set()
            for item in values:
                if (not isinstance(item, dict) or set(item) != {"id", "name", "description", "source"} or
                        not isinstance(item["id"], str) or not item["id"] or item["id"] in ids or
                        not all(isinstance(item[field], str) for field in ("name", "description", "source"))):
                    raise DomainError("IMPORT_INVALID", f"story state {group}条目无效")
                ids.add(item["id"])
        bonds = state.get("bonds")
        if not isinstance(bonds, dict) or any(
                not isinstance(item, dict) or item.get("npc_id") != key or
                type(item.get("value")) is not int or not -100 <= item["value"] <= 100
                for key, item in bonds.items()):
            raise DomainError("IMPORT_INVALID", "story state羁绊无效")
        if type(state.get("currency_copper")) is not int or state["currency_copper"] < 0:
            raise DomainError("IMPORT_INVALID", "story state货币无效")
        Database._validate_import_start_prerequisite(state)
