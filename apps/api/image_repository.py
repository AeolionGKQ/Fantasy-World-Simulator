"""Persistent current-scene image sessions and generation attempts."""

import copy
import hashlib
import json

try:
    from .content_registry import load_revision_documents, load_revision_manifest
    from .database import DomainError, dumps, loads, new_id, utc_now
    from .story_repository import number_active_memories
except ImportError:
    from content_registry import load_revision_documents, load_revision_manifest
    from database import DomainError, dumps, loads, new_id, utc_now
    from story_repository import number_active_memories


IMAGE_SIZES = {"1024x1024", "1536x1024", "1024x1536"}
IMAGE_QUALITIES = {"low", "medium", "high", "xhigh", "max", "auto"}
ACTIVE_ATTEMPT_STATUSES = {"queued", "running", "cancel_requested"}


class ImageRepository:
    def __init__(self, database, content_registry):
        self.database = database
        self.content_registry = content_registry

    @staticmethod
    def _attempt(row):
        if not row:
            return None
        return {"id": row["id"], "status": row["status"],
                "requested_size": row["requested_size"],
                "requested_quality": row["requested_quality"],
                "image_available": bool(row["image_relative_path"]),
                "error": ({"code": row["error_code"], "message": row["error_message"],
                           "retryable": bool(row["retryable"])} if row["error_code"] else None),
                "created_at": row["created_at"], "updated_at": row["updated_at"]}

    @staticmethod
    def _prompt_attempt(row):
        if not row:
            return None
        return {"id": row["id"], "status": row["status"],
                "error": ({"code": row["error_code"], "message": row["error_message"],
                           "retryable": bool(row["retryable"])} if row["error_code"] else None),
                "created_at": row["created_at"], "updated_at": row["updated_at"]}

    def _view(self, connection, row):
        prompt = connection.execute(
            "SELECT * FROM image_prompt_attempts WHERE session_id=? ORDER BY created_at DESC LIMIT 1",
            (row["id"],)).fetchone()
        attempt = connection.execute(
            "SELECT * FROM image_attempts WHERE session_id=? ORDER BY created_at DESC LIMIT 1",
            (row["id"],)).fetchone()
        successful = connection.execute(
            "SELECT * FROM image_attempts WHERE session_id=? AND status='succeeded' "
            "ORDER BY created_at DESC LIMIT 1", (row["id"],)).fetchone()
        return {"id": row["id"], "save_id": row["save_id"],
                "source_turn_id": row["source_turn_id"], "status": row["status"],
                "prompt_draft": row["prompt_draft"], "prompt_revision": row["prompt_revision"],
                "selected_size": row["selected_size"],
                "selected_quality": row["selected_quality"],
                "prompt_attempt": self._prompt_attempt(prompt),
                "image_attempt": self._attempt(attempt),
                "latest_successful_image": self._attempt(successful),
                "created_at": row["created_at"], "updated_at": row["updated_at"]}

    def get_active(self, save_id):
        with self.database.connect() as connection:
            self.database.get_save(save_id, connection)
            row = connection.execute(
                "SELECT * FROM image_sessions WHERE save_id=? AND completed_at IS NULL",
                (save_id,)).fetchone()
            return self._view(connection, row) if row else None

    def create(self, save_id, body, narrative_config):
        self.database._validate_request_id(body)
        allowed = {"request_id", "source_turn_id", "expected_state_version"}
        if set(body) != allowed:
            raise DomainError("INVALID_INPUT", "图片会话请求字段无效")
        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            save = self.database.get_save(save_id, connection)
            if save["phase"] != "ready":
                raise DomainError("SAVE_NOT_READY", "存档尚未进入游戏", 409)
            existing = connection.execute(
                "SELECT * FROM image_sessions WHERE save_id=? AND completed_at IS NULL",
                (save_id,)).fetchone()
            if existing:
                connection.commit()
                return self._view(connection, existing), None
            state_row = connection.execute("SELECT * FROM story_states WHERE save_id=?", (save_id,)).fetchone()
            if not state_row:
                raise DomainError("STORY_NOT_STARTED", "请先生成剧情节点", 409)
            state = loads(state_row["state_json"], {})
            if (body["expected_state_version"] != state_row["state_version"] or
                    body["source_turn_id"] != state_row["current_turn_id"]):
                raise DomainError("STATE_VERSION_CONFLICT", "当前剧情节点已变化", 409)
            turn = connection.execute("SELECT * FROM turns WHERE id=? AND save_id=?",
                                      (body["source_turn_id"], save_id)).fetchone()
            if not turn:
                raise DomainError("TURN_NOT_FOUND", "当前剧情节点不存在", 404)
            version = connection.execute("SELECT * FROM turn_versions WHERE id=?",
                                         (turn["current_version_id"],)).fetchone()
            history = [dict(row) for row in connection.execute(
                "SELECT id,sequence,title,body,summary,action_type,action_json FROM turns "
                "WHERE save_id=? ORDER BY sequence", (save_id,)).fetchall()]
            recent_ids = {item["id"] for item in history[-10:]}
            for item in history:
                item["action"] = loads(item.pop("action_json"), {})
                item["projection"] = "full" if item["id"] in recent_ids else "summary"
                if item["projection"] == "summary": item.pop("body", None)
            memories = number_active_memories([dict(row) for row in connection.execute(
                "SELECT * FROM memories WHERE save_id=? AND status='active' ORDER BY updated_at,id",
                (save_id,)).fetchall()])
            for memory in memories:
                for key in ("people", "locations", "keywords", "facts", "unresolved"):
                    stored = key + "_json"
                    if stored in memory: memory[key] = loads(memory.pop(stored), [])
            arcs = []
            for row in connection.execute(
                    "SELECT * FROM story_arcs WHERE save_id=? AND status='current' ORDER BY start_sequence",
                    (save_id,)).fetchall():
                item = dict(row)
                item["key_events"] = loads(item.pop("key_events_json"), [])
                item["unresolved"] = loads(item.pop("unresolved_json"), [])
                arcs.append(item)
            nodes = {row["id"]: dict(row) for row in connection.execute(
                "SELECT * FROM location_nodes WHERE save_id=?", (save_id,)).fetchall()}
            documents = load_revision_documents(connection, state["content_revision_id"])
            manifest = load_revision_manifest(connection, state["content_revision_id"])
            prompt_documents = [{key: value for key, value in document.items() if key != "raw_bytes"}
                                for document in documents]
            frozen = {"state": state, "turn": dict(turn), "version": dict(version),
                      "early_summaries": [item for item in history if item["projection"] == "summary"],
                      "recent_full_turns": [item for item in history if item["projection"] == "full"],
                      "memories": memories, "arcs": arcs, "location_nodes": nodes,
                      "documents": prompt_documents, "revision_manifest": manifest}
            frozen_json = dumps(frozen)
            session_id, attempt_id, now = new_id(), new_id(), utc_now()
            connection.execute(
                "INSERT INTO image_sessions(id,save_id,source_turn_id,source_turn_version_id,"
                "source_state_version,status,prompt_draft,prompt_revision,selected_size,"
                "selected_quality,frozen_context_json,context_manifest_json,created_at,updated_at,"
                "completed_at) VALUES(?,?,?,?,?,'active',NULL,0,'1536x1024','high',?,?,?,?,NULL)",
                (session_id, save_id, turn["id"], version["id"], state_row["state_version"],
                 frozen_json, dumps({"sha256": hashlib.sha256(frozen_json.encode()).hexdigest()}), now, now))
            fingerprint = dumps({"source_turn_id": turn["id"], "state_version": state_row["state_version"]})
            connection.execute(
                "INSERT INTO image_prompt_attempts(id,session_id,request_id,request_fingerprint,status,"
                "provider_protocol,provider_endpoint,provider_model,error_code,error_message,retryable,"
                "created_at,updated_at) VALUES(?,?,?,?,'queued',?,?,?,?,?,0,?,?)",
                (attempt_id, session_id, body["request_id"], fingerprint,
                 narrative_config.get("protocol", "openai"), narrative_config.get("base_url", ""),
                 narrative_config.get("model", ""), None, None, now, now))
            row = connection.execute("SELECT * FROM image_sessions WHERE id=?", (session_id,)).fetchone()
            view = self._view(connection, row)
            connection.commit()
        return view, attempt_id

    def claim_prompt(self, attempt_id):
        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            changed = connection.execute(
                "UPDATE image_prompt_attempts SET status='running',updated_at=? WHERE id=? AND status='queued'",
                (utc_now(), attempt_id)).rowcount
            if not changed: connection.rollback(); return None
            attempt = connection.execute("SELECT * FROM image_prompt_attempts WHERE id=?", (attempt_id,)).fetchone()
            session = connection.execute("SELECT * FROM image_sessions WHERE id=?", (attempt["session_id"],)).fetchone()
            connection.commit()
        return {"attempt": dict(attempt), "session": dict(session),
                "frozen": loads(session["frozen_context_json"], {})}

    def complete_prompt(self, attempt_id, prompt):
        if not isinstance(prompt, str) or not 1 <= len(prompt.strip()) <= 8000:
            raise DomainError("MODEL_OUTPUT_FORMAT", "画面提示词必须是1至8000字符文本")
        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            attempt = connection.execute("SELECT * FROM image_prompt_attempts WHERE id=?", (attempt_id,)).fetchone()
            if not attempt or attempt["status"] not in {"running", "cancel_requested"}: connection.rollback(); return
            if attempt["status"] == "cancel_requested":
                connection.execute("UPDATE image_prompt_attempts SET status='cancelled',updated_at=? WHERE id=?",
                                   (utc_now(), attempt_id))
                connection.commit(); return
            session = connection.execute("SELECT * FROM image_sessions WHERE id=?", (attempt["session_id"],)).fetchone()
            if not session or session["status"] != "active": connection.rollback(); return
            now = utc_now()
            connection.execute("UPDATE image_sessions SET prompt_draft=?,prompt_revision=prompt_revision+1,updated_at=? WHERE id=?",
                               (prompt.strip(), now, session["id"]))
            connection.execute("UPDATE image_prompt_attempts SET status='succeeded',updated_at=? WHERE id=?", (now, attempt_id))
            connection.commit()

    def fail_prompt(self, attempt_id, code, message, retryable=False):
        with self.database.connect() as connection:
            connection.execute("UPDATE image_prompt_attempts SET status='failed',error_code=?,error_message=?,retryable=?,updated_at=? WHERE id=? AND status='running'",
                               (code, message[:2000], int(retryable), utc_now(), attempt_id))

    def update_prompt(self, save_id, session_id, body):
        allowed = {"prompt", "expected_prompt_revision", "size", "quality"}
        if set(body) != allowed or not isinstance(body.get("prompt"), str) or not 1 <= len(body["prompt"].strip()) <= 8000:
            raise DomainError("INVALID_INPUT", "提示词保存请求无效")
        if body["size"] not in IMAGE_SIZES or body["quality"] not in IMAGE_QUALITIES:
            raise DomainError("INVALID_INPUT", "图片画幅或质量无效")
        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT * FROM image_sessions WHERE id=? AND save_id=? AND completed_at IS NULL", (session_id, save_id)).fetchone()
            if not row: raise DomainError("IMAGE_SESSION_NOT_FOUND", "图片会话不存在", 404)
            if body["expected_prompt_revision"] != row["prompt_revision"]:
                raise DomainError("REVISION_CONFLICT", "提示词已在其他页面更新", 409)
            if connection.execute("SELECT 1 FROM image_attempts WHERE session_id=? AND status IN ('queued','running','cancel_requested')", (session_id,)).fetchone():
                raise DomainError("IMAGE_JOB_ACTIVE", "图片生成期间不能修改提示词", 409)
            connection.execute("UPDATE image_sessions SET prompt_draft=?,prompt_revision=prompt_revision+1,selected_size=?,selected_quality=?,updated_at=? WHERE id=?",
                               (body["prompt"].strip(), body["size"], body["quality"], utc_now(), session_id))
            row = connection.execute("SELECT * FROM image_sessions WHERE id=?", (session_id,)).fetchone()
            connection.commit()
            return self._view(connection, row)

    def create_image_attempt(self, save_id, session_id, body, model):
        self.database._validate_request_id(body)
        if set(body) != {"request_id", "expected_prompt_revision"}:
            raise DomainError("INVALID_INPUT", "生图请求字段无效")
        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            session = connection.execute("SELECT * FROM image_sessions WHERE id=? AND save_id=? AND completed_at IS NULL", (session_id, save_id)).fetchone()
            if not session: raise DomainError("IMAGE_SESSION_NOT_FOUND", "图片会话不存在", 404)
            if session["prompt_revision"] != body["expected_prompt_revision"]:
                raise DomainError("REVISION_CONFLICT", "提示词版本已变化", 409)
            if not session["prompt_draft"]: raise DomainError("INVALID_INPUT", "请先生成或填写提示词")
            existing = connection.execute("SELECT * FROM image_attempts WHERE session_id=? AND request_id=?", (session_id, body["request_id"])).fetchone()
            fingerprint = dumps({"prompt": session["prompt_draft"], "revision": session["prompt_revision"], "size": session["selected_size"], "quality": session["selected_quality"]})
            if existing:
                if existing["request_fingerprint"] != fingerprint:
                    raise DomainError("IDEMPOTENCY_CONFLICT", "request_id已用于不同生图请求", 409)
                connection.commit(); return self._attempt(existing), False
            active = connection.execute("SELECT 1 FROM image_attempts WHERE session_id=? AND status IN ('queued','running','cancel_requested')", (session_id,)).fetchone()
            if active: raise DomainError("IMAGE_JOB_ACTIVE", "已有图片正在生成", 409)
            attempt_id, now = new_id(), utc_now()
            connection.execute("INSERT INTO image_attempts(id,session_id,request_id,request_fingerprint,"
                "prompt_revision,status,provider_model,requested_size,requested_quality,prompt_snapshot,image_relative_path,"
                "mime_type,byte_count,sha256,provider_request_id,usage_json,error_code,error_message,retryable,"
                "created_at,updated_at) VALUES(?,?,?,?,?,'queued',?,?,?,?,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,0,?,?)",
                (attempt_id, session_id, body["request_id"], fingerprint, session["prompt_revision"], model,
                 session["selected_size"], session["selected_quality"], session["prompt_draft"], now, now))
            row = connection.execute("SELECT * FROM image_attempts WHERE id=?", (attempt_id,)).fetchone()
            connection.commit()
            return self._attempt(row), True

    def claim_image(self, attempt_id):
        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            changed = connection.execute("UPDATE image_attempts SET status='running',updated_at=? WHERE id=? AND status='queued'", (utc_now(), attempt_id)).rowcount
            if not changed: connection.rollback(); return None
            attempt = connection.execute("SELECT * FROM image_attempts WHERE id=?", (attempt_id,)).fetchone()
            session = connection.execute("SELECT * FROM image_sessions WHERE id=?", (attempt["session_id"],)).fetchone()
            connection.commit()
        return {"attempt": dict(attempt), "session": dict(session)}

    def complete_image(self, attempt_id, relative_path, byte_count, sha256, request_id=None, usage=None):
        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT status FROM image_attempts WHERE id=?", (attempt_id,)).fetchone()
            if not row or row["status"] not in {"running", "cancel_requested"}: connection.rollback(); return False
            if row["status"] == "cancel_requested":
                connection.execute("UPDATE image_attempts SET status='cancelled',updated_at=? WHERE id=?",
                                   (utc_now(), attempt_id))
                connection.commit(); return False
            connection.execute("UPDATE image_attempts SET status='succeeded',image_relative_path=?,mime_type='image/png',byte_count=?,sha256=?,provider_request_id=?,usage_json=?,updated_at=? WHERE id=?",
                               (relative_path, byte_count, sha256, request_id, dumps(usage or {}), utc_now(), attempt_id))
            connection.commit(); return True

    def fail_image(self, attempt_id, code, message, retryable=False, outcome_unknown=False):
        status = "outcome_unknown" if outcome_unknown else "failed"
        with self.database.connect() as connection:
            connection.execute("UPDATE image_attempts SET status=?,error_code=?,error_message=?,retryable=?,updated_at=? WHERE id=? AND status='running'",
                               (status, code, message[:2000], int(retryable), utc_now(), attempt_id))

    def cancel(self, save_id, session_id):
        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            session = connection.execute("SELECT 1 FROM image_sessions WHERE id=? AND save_id=? AND completed_at IS NULL",
                                         (session_id, save_id)).fetchone()
            if not session: raise DomainError("IMAGE_SESSION_NOT_FOUND", "图片会话不存在", 404)
            now = utc_now()
            connection.execute("UPDATE image_prompt_attempts SET status=CASE WHEN status='queued' THEN 'cancelled' ELSE 'cancel_requested' END,updated_at=? WHERE session_id=? AND status IN ('queued','running')",
                               (now, session_id))
            connection.execute("UPDATE image_attempts SET status=CASE WHEN status='queued' THEN 'cancelled' ELSE 'cancel_requested' END,updated_at=? WHERE session_id=? AND status IN ('queued','running')",
                               (now, session_id))
            row = connection.execute("SELECT * FROM image_sessions WHERE id=?", (session_id,)).fetchone()
            view = self._view(connection, row)
            connection.commit(); return view

    def complete_session(self, save_id, session_id, abandon=False):
        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT * FROM image_sessions WHERE id=? AND save_id=? AND completed_at IS NULL", (session_id, save_id)).fetchone()
            if not row: raise DomainError("IMAGE_SESSION_NOT_FOUND", "图片会话不存在", 404)
            active_prompt = connection.execute(
                "SELECT 1 FROM image_prompt_attempts WHERE session_id=? AND status IN ('queued','running','cancel_requested')",
                (session_id,)).fetchone()
            active_image = connection.execute(
                "SELECT 1 FROM image_attempts WHERE session_id=? AND status IN ('queued','running','cancel_requested')",
                (session_id,)).fetchone()
            if (active_prompt or active_image) and not abandon:
                raise DomainError("IMAGE_JOB_ACTIVE", "图片任务仍在运行，不能完成", 409)
            now = utc_now()
            if abandon:
                connection.execute("UPDATE image_prompt_attempts SET status=CASE WHEN status='queued' THEN 'cancelled' ELSE 'cancel_requested' END,updated_at=? WHERE session_id=? AND status IN ('queued','running')",
                                   (now, session_id))
                connection.execute("UPDATE image_attempts SET status=CASE WHEN status='queued' THEN 'cancelled' ELSE 'cancel_requested' END,updated_at=? WHERE session_id=? AND status IN ('queued','running')",
                                   (now, session_id))
            connection.execute("UPDATE image_sessions SET status='completed',prompt_draft=NULL,completed_at=?,updated_at=? WHERE id=?", (now, now, session_id))
            paths = [row[0] for row in connection.execute(
                "SELECT image_relative_path FROM image_attempts WHERE session_id=? AND image_relative_path IS NOT NULL",
                (session_id,)).fetchall()]
            connection.commit()
        return {"session": dict(row), "paths": paths}

    def retry_prompt(self, save_id, session_id, request_id, narrative_config):
        if not isinstance(request_id, str) or not request_id:
            raise DomainError("INVALID_INPUT", "request_id不能为空")
        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            session = connection.execute("SELECT * FROM image_sessions WHERE id=? AND save_id=? AND completed_at IS NULL", (session_id, save_id)).fetchone()
            if not session: raise DomainError("IMAGE_SESSION_NOT_FOUND", "图片会话不存在", 404)
            active = connection.execute("SELECT 1 FROM image_prompt_attempts WHERE session_id=? AND status IN ('queued','running','cancel_requested')", (session_id,)).fetchone()
            if active: raise DomainError("IMAGE_JOB_ACTIVE", "提示词正在生成", 409)
            attempt_id, now = new_id(), utc_now()
            fingerprint = dumps({"session_id": session_id, "retry": request_id})
            connection.execute("INSERT INTO image_prompt_attempts(id,session_id,request_id,request_fingerprint,status,provider_protocol,provider_endpoint,provider_model,error_code,error_message,retryable,created_at,updated_at) VALUES(?,?,?,?,'queued',?,?,?,?,?,0,?,?)",
                (attempt_id, session_id, request_id, fingerprint, narrative_config.get("protocol", "openai"), narrative_config.get("base_url", ""), narrative_config.get("model", ""), None, None, now, now))
            connection.commit(); return attempt_id

    def image_record(self, save_id, session_id, attempt_id=None):
        with self.database.connect() as connection:
            row = connection.execute("SELECT a.* FROM image_attempts a JOIN image_sessions s ON s.id=a.session_id WHERE s.save_id=? AND s.id=? AND a.status='succeeded' AND (? IS NULL OR a.id=?) ORDER BY a.created_at DESC LIMIT 1", (save_id, session_id, attempt_id, attempt_id)).fetchone()
        if not row: raise DomainError("IMAGE_NOT_FOUND", "图片尚未生成", 404)
        return dict(row)

    def queued(self):
        with self.database.connect() as connection:
            prompts = [(row["id"], "prompt") for row in connection.execute("SELECT id FROM image_prompt_attempts WHERE status='queued'")]
            images = [(row["id"], "image") for row in connection.execute("SELECT id FROM image_attempts WHERE status='queued'")]
        return prompts + images
