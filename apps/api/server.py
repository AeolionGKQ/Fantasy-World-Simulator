"""Fantasy Simulator phase-one standard-library HTTP server."""

import argparse
import hashlib
import hmac
import json
import mimetypes
import os
import posixpath
import secrets
import sys
import tempfile
import threading
import time
import urllib.parse
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

try:
    from .catalog import CATALOG, LOCATIONS, RACES
    from .content_registry import ContentRegistry
    from .contract_registry import contract_from_documents
    from .database import Database, DomainError, SecretStore
    from .model_provider import (ModelProvider, ProviderError,
                                 is_explicit_concurrency_rejection, validate_candidate)
    from .narrative_contract import ContractError, validate_gm_response, validate_story_arc
    from .story_repository import StoryRepository
except ImportError:  # Direct execution with the isolated embedded runtime.
    api_directory = str(Path(__file__).resolve().parent)
    if api_directory not in sys.path:
        sys.path.insert(0, api_directory)
    from catalog import CATALOG, LOCATIONS, RACES
    from content_registry import ContentRegistry
    from contract_registry import contract_from_documents
    from database import Database, DomainError, SecretStore
    from model_provider import (ModelProvider, ProviderError,
                                is_explicit_concurrency_rejection, validate_candidate)
    from narrative_contract import ContractError, validate_gm_response, validate_story_arc
    from story_repository import StoryRepository

MAX_REQUEST_BYTES = 2_000_000
MAX_IMPORT_BYTES = 64 * 1024 * 1024
APP_ID = "fantasy-simulator"
API_VERSION = "1"


def draft_to_view(draft):
    data = draft["data"]
    return {"race_id": data.get("race_id", ""),
            "race_branch_id": data.get("race_branch_id"),
            "name": data.get("name", ""), "gender": data.get("gender", ""),
            "age": data.get("age"), "appearance": data.get("appearance", ""),
            "personality": data.get("personality", ""), "rank": data.get("rank"),
            "talent": data.get("talent", ""), "background": data.get("backstory", ""),
            "location_id": data.get("start_location_id", ""),
            "additional": data.get("additional", ""),
            "current_step": draft["current_step"],
            "draft_revision": draft["draft_revision"]}


def draft_from_view(body):
    fields = {"race_id", "race_branch_id", "name", "gender", "age", "appearance",
              "personality", "rank", "talent", "background", "location_id",
              "additional", "current_step", "draft_revision", "expected_save_revision",
              "request_id"}
    unknown = set(body) - fields
    if unknown:
        raise DomainError("INVALID_INPUT", "存在未知草稿请求字段", 400,
                          fields={key: "未知字段" for key in unknown})
    draft = {"race_id": body.get("race_id"),
             "race_branch_id": body.get("race_branch_id"),
             "name": body.get("name"), "gender": body.get("gender"),
             "age": body.get("age"), "appearance": body.get("appearance"),
             "personality": body.get("personality"), "rank": body.get("rank"),
             "talent": body.get("talent"), "backstory": body.get("background"),
             "start_location_id": body.get("location_id"),
             "additional": body.get("additional")}
    draft = {key: value for key, value in draft.items() if value not in (None, "")}
    return {"request_id": body.get("request_id"),
            "expected_revision": body.get("draft_revision"),
            "expected_save_revision": body.get("expected_save_revision"),
            "current_step": body.get("current_step", 1), "data": draft}


def _named_item(items, item_id):
    return next((item for item in items if item["id"] == item_id), None)


def candidate_to_view(candidate, draft, confirmed_at=None):
    data = candidate["data"]
    race = _named_item(RACES, draft.get("race_id"))
    branch = _named_item(race.get("branches", []), draft.get("race_branch_id")) if race else None
    location = _named_item(LOCATIONS, draft.get("start_location_id"))
    rank = data.get("rank")
    view = {"id": candidate["id"], "save_id": candidate["save_id"],
            "job_id": candidate.get("job_id"),
            "draft_revision": candidate.get("draft_revision", 0),
            "identity": {"name": draft.get("name"), "gender": draft.get("gender"),
                         "age": draft.get("age"),
                         "race_name": race.get("name") if race else None,
                         "race_branch_name": branch.get("name") if branch else None,
                         "location_name": location.get("name") if location else None,
                         "rank_name": f"{rank} 阶" if rank else None},
            "description": {"appearance": draft.get("appearance"),
                            "personality": draft.get("personality"),
                            "talent": draft.get("talent"),
                            "background": draft.get("backstory"),
                            "additional": draft.get("additional")},
            "attributes": data["attributes"], "resources": data.get("resources"),
            "power": {"base": data["base_power"],
                      "effective": data["effective_power"],
                      "modifiers": data.get("power_modifiers", [])},
            "exp": data["exp"], "next_exp": data.get("exp_to_next"),
            "summary": data.get("summary"), "strengths": data.get("strengths", []),
            "limitations": data.get("limitations", []),
            "valid": True}
    if isinstance(data.get("starting_currency"), dict):
        view["starting_currency"] = data["starting_currency"]
    if confirmed_at is not None:
        view["confirmed_at"] = confirmed_at
    return view


def bootstrap_to_view(bootstrap):
    save = bootstrap["save"]
    stored = bootstrap["character"]
    data = stored["data"]
    candidate = {"id": stored["candidate_id"], "save_id": stored["save_id"],
                 "draft_revision": 0,
                 "data": {"attributes": data["attributes"], "resources": data["resources"],
                          "rank": data["rank"], "base_power": data["base_power"],
                          "effective_power": data["effective_power"],
                          "power_modifiers": data.get("power_modifiers", []),
                          "exp": data["exp"], "exp_to_next": data.get("exp_to_next"),
                          "summary": data.get("summary"), "strengths": data.get("strengths", []),
                          "limitations": data.get("limitations", [])}}
    if "initial_currency_copper" in data and "starting_currency_reason" in data:
        candidate["data"]["starting_currency"] = {
            "copper": data["initial_currency_copper"],
            "reason": data["starting_currency_reason"],
        }
    character = candidate_to_view(candidate, data["identity"], stored["confirmed_at"])
    location = _named_item(LOCATIONS, data["current_location_id"])
    return {"save_id": save["id"], "save_revision": save["revision"],
            "character": character, "location": location,
            "phase": "ready", "ruleset_version": save["ruleset_version"]}


def model_test_to_view(result):
    connected = bool(result.get("connected"))
    thinking = result.get("thinking") or {}
    if not isinstance(thinking, dict):
        thinking = {"capability": thinking, "strategy": None,
                    "confidence": "unknown", "message": result.get("message", "")}
    structured_output = result.get("structured_output") or {}
    if not isinstance(structured_output, dict):
        structured_output = {"capability": structured_output, "strategy": None,
                             "message": ""}
    return {"ok": connected, "message": result.get("message", "连接测试通过" if connected else "连接测试未通过"),
            "latency_ms": result.get("latency_ms"),
            "model_available": result.get("model_available"),
            "thinking_capability": thinking.get("capability", "unknown"),
            "thinking_strategy": thinking.get("strategy"),
            "thinking_confidence": thinking.get("confidence", "unknown"),
            "thinking_message": thinking.get("message", result.get("message", "")),
            "thinking_probed_at": thinking.get("probed_at"),
            "structured_output_capability": structured_output.get("capability", "unknown"),
            "structured_output_strategy": structured_output.get("strategy"),
            "structured_output_message": structured_output.get("message", ""),
            "structured_output_probed_at": structured_output.get("probed_at"),
            "may_have_cost": bool(result.get("may_have_cost", True))}


class AppContext:
    RESPONSE_FORMAT_PROBE_TTL_SECONDS = 10 * 60

    def __init__(self, data_dir, static_dir, provider=None):
        data_dir = os.path.abspath(data_dir)
        self.content_registry = ContentRegistry(Path(__file__).resolve().parent)
        self.database = Database(os.path.join(data_dir, "fantasy_simulator.sqlite3"),
                                 self.content_registry)
        self.story = StoryRepository(self.database, self.content_registry)
        self.secrets = SecretStore(os.path.join(data_dir, "secrets.dat"))
        self.static_dir = os.path.abspath(static_dir)
        self.provider = provider or ModelProvider()
        self._worker_lock = threading.Lock()
        self._workers = set()
        self._provider_condition = threading.Condition()
        self._active_provider_calls = 0
        self._provider_fallback_retries = 0
        self._effective_provider_limit = {}
        self._response_format_probe_lock = threading.Lock()
        self._response_format_probe_proofs = {}

    @staticmethod
    def _response_format_probe_identity(config):
        protocol = str(config.get("protocol", "openai"))
        endpoint = str(config.get("base_url", "")).strip().rstrip("/")
        model = str(config.get("model", "")).strip()
        return protocol, endpoint, model

    @staticmethod
    def _api_key_digest(api_key):
        return hashlib.sha256(str(api_key or "").encode("utf-8")).hexdigest()

    def create_response_format_probe(self, config, api_key, capability):
        token = secrets.token_urlsafe(32)
        now = time.monotonic()
        protocol, endpoint, model = self._response_format_probe_identity(config)
        proof = {
            "protocol": protocol,
            "endpoint": endpoint,
            "model": model,
            "api_key_digest": self._api_key_digest(api_key),
            "capability": capability,
            "expires_at": now + self.RESPONSE_FORMAT_PROBE_TTL_SECONDS,
        }
        with self._response_format_probe_lock:
            self._response_format_probe_proofs = {
                key: value for key, value in self._response_format_probe_proofs.items()
                if value["expires_at"] > now
            }
            self._response_format_probe_proofs[token] = proof
        return token

    def validate_response_format_probe(self, token, config, api_key):
        if not isinstance(token, str) or not token:
            return False
        now = time.monotonic()
        protocol, endpoint, model = self._response_format_probe_identity(config)
        digest = self._api_key_digest(api_key)
        with self._response_format_probe_lock:
            proof = self._response_format_probe_proofs.get(token)
            if proof is None:
                return False
            if proof["expires_at"] <= now:
                self._response_format_probe_proofs.pop(token, None)
                return False
            return (proof["capability"] == "supported" and
                    proof["protocol"] == protocol and
                    proof["endpoint"] == endpoint and proof["model"] == model and
                    hmac.compare_digest(proof["api_key_digest"], digest))

    def validate_response_format_update(self, body):
        current = self.database.get_model_config()
        candidate = dict(current)
        candidate.update({key: body[key] for key in (
            "protocol", "base_url", "model", "timeout_seconds", "structured_output", "max_concurrency"
        ) if key in body})
        if not candidate.get("structured_output", False):
            return
        current_identity = self._response_format_probe_identity(current)
        candidate_identity = self._response_format_probe_identity(candidate)
        current_capability = self.database.get_response_format_capability(current)
        can_reuse_current = (
            "api_key" not in body and current_identity == candidate_identity and
            current.get("structured_output", False) and
            current_capability["capability"] == "supported"
        )
        if can_reuse_current:
            return
        api_key = body.get("api_key", self.secrets.get_api_key())
        if not self.validate_response_format_probe(
                body.get("structured_output_probe_token"), candidate, api_key):
            raise DomainError(
                "INVALID_INPUT", "结构化输出探测凭证无效或已过期", 400,
                fields={"structured_output": "请使用当前 API Key 重新探测 response_format 支持情况"})

    def schedule(self, save_id, job_id):
        worker = threading.Thread(target=self._run_generation, args=(save_id, job_id),
                                  name=f"generation-{job_id}", daemon=True)
        with self._worker_lock:
            self._workers.add(worker)
        worker.start()

    def schedule_narrative(self, save_id, job_id):
        worker = threading.Thread(target=self._run_narrative, args=(save_id, job_id),
                                  name=f"narrative-{job_id}", daemon=True)
        with self._worker_lock:
            self._workers.add(worker)
        worker.start()

    def resume_queued(self):
        for save_id, job_id in self.database.list_queued_jobs():
            self.schedule(save_id, job_id)
        for save_id, job_id in self.story.list_queued():
            self.schedule_narrative(save_id, job_id)

    @staticmethod
    def _provider_identity(config):
        return (str(config.get("protocol", "openai")),
                str(config.get("base_url", "")).strip().rstrip("/"),
                str(config.get("model", "")).strip())

    @staticmethod
    def _configured_provider_limit(config):
        return max(1, min(16, int(config.get("max_concurrency", 2))))

    def _provider_limit_locked(self, config, identity):
        configured = self._configured_provider_limit(config)
        revision = int(config.get("_settings_revision", -1))
        state = self._effective_provider_limit.get(identity)
        if state is None or revision > state["revision"]:
            state = {"configured": configured, "effective": configured,
                     "revision": revision}
            self._effective_provider_limit[identity] = state
        return state

    def sync_provider_limit(self, config):
        identity = self._provider_identity(config)
        with self._provider_condition:
            configured = self._configured_provider_limit(config)
            self._effective_provider_limit[identity] = {
                "configured": configured, "effective": configured,
                "revision": int(config.get("_settings_revision", -1)),
            }
            self._provider_condition.notify_all()

    def _apply_persisted_downgrade_locked(self, identity, expected_revision, revision):
        state = self._effective_provider_limit.get(identity)
        if state is not None and state["revision"] == expected_revision:
            state.update({"configured": 1, "effective": 1, "revision": revision})

    def _provider_enter(self, config, fallback_retry=False):
        identity = self._provider_identity(config)
        with self._provider_condition:
            while True:
                state = self._provider_limit_locked(config, identity)
                if (self._provider_fallback_retries > 0 and fallback_retry and
                        self._active_provider_calls == 0):
                    break
                if (self._provider_fallback_retries == 0 and
                        self._active_provider_calls < state["effective"]):
                    break
                self._provider_condition.wait()
            overlapped = self._active_provider_calls > 0
            self._active_provider_calls += 1
            return {"identity": identity, "overlapped": overlapped,
                    "limit": state["effective"], "revision": state["revision"]}

    def _provider_exit(self):
        with self._provider_condition:
            self._release_provider_locked()
            self._provider_condition.notify_all()

    def _release_provider_locked(self):
        if self._active_provider_calls <= 0:
            raise RuntimeError("provider call counter underflow")
        self._active_provider_calls -= 1

    def _downgrade_provider_and_exit(self, ticket):
        with self._provider_condition:
            self._release_provider_locked()
            self._provider_fallback_retries += 1
            self._provider_condition.notify_all()

    def _call_provider_with_concurrency_fallback(self, config, provider_call):
        ticket = self._provider_enter(config)
        released = False
        try:
            try:
                return provider_call()
            except ProviderError as original_error:
                if (self._configured_provider_limit(config) <= 1 or ticket["limit"] <= 1 or
                        not ticket["overlapped"] or
                        not is_explicit_concurrency_rejection(original_error)):
                    raise
                frozen_call = provider_call
                failed_config_revision = int(config.get("_settings_revision", -1))
                self._downgrade_provider_and_exit(ticket)
                released = True
                protocol, endpoint, model = ticket["identity"]
                try:
                    revision = self.database.downgrade_max_concurrency(
                        protocol, endpoint, model, failed_config_revision)
                    if revision is not None:
                        with self._provider_condition:
                            self._apply_persisted_downgrade_locked(
                                ticket["identity"], failed_config_revision, revision)
                except Exception:
                    print("provider concurrency fallback could not be persisted")
                self._provider_enter(config, fallback_retry=True)
                try:
                    try:
                        return frozen_call()
                    except ProviderError as retry_error:
                        if retry_error.code == "MODEL_OUTPUT_FORMAT":
                            raise
                        raise original_error from None
                finally:
                    with self._provider_condition:
                        if self._provider_fallback_retries <= 0:
                            raise RuntimeError("provider fallback counter underflow")
                        self._provider_fallback_retries -= 1
                        self._release_provider_locked()
                        self._provider_condition.notify_all()
        finally:
            if not released:
                self._provider_exit()

    def _run_generation(self, save_id, job_id):
        try:
            claimed = self.database.claim_job(save_id, job_id)
            if claimed is None:
                return
            config = self.database.get_model_config()
            api_key = self.secrets.get_api_key()
            def generate():
                if self.database.get_job(save_id, job_id)["status"] == "running":
                    return self.provider.generate_character(
                        config, api_key, claimed["draft"], claimed["feedback"],
                        lambda result: self.database.set_model_capability(config, result)
                    )
                return None
            proposal = self._call_provider_with_concurrency_fallback(config, generate)
            if proposal is None:
                self.database.fail_job(save_id, job_id, "GENERATION_CANCELLED", "生成已取消")
                return
            candidate = validate_candidate(proposal, claimed["draft"]["rank"])
            self.database.complete_job(save_id, job_id, candidate)
        except ProviderError as exc:
            self.database.fail_job(save_id, job_id, exc.code, exc.message)
        except Exception:
            self.database.fail_job(save_id, job_id, "INTERNAL_ERROR", "生成任务发生内部错误")
        finally:
            current = threading.current_thread()
            with self._worker_lock:
                self._workers.discard(current)

    def _run_narrative(self, save_id, job_id):
        claimed = None
        try:
            claimed = self.story.claim(save_id, job_id)
            if claimed is None:
                return
            config = self.database.get_model_config()
            if not config.get("base_url") or not config.get("model"):
                raise ProviderError("MODEL_NOT_CONFIGURED", "模型未配置，无法生成叙事")
            job_type = claimed["job"]["type"]
            if job_type in {"turns_to_arc", "arcs_to_arc"}:
                frozen = self.story.claim_arc(claimed)
                action = {"action_type": job_type, "frozen_sources": frozen}
                contract_kind = "story_arc"
            else:
                action = dict(claimed["input"])
                contract_kind = "gm_turn"
            messages, manifest = self.content_registry.build_messages(
                claimed["context_state"], action, claimed["early_summaries"],
                claimed["recent_full_turns"], claimed["memories"], claimed["arcs"],
                claimed["location_nodes"], claimed["documents"], contract_kind,
                claimed["revision_manifest"])
            contract = contract_from_documents(contract_kind, claimed["documents"])
            request_config = dict(config)
            request_config["_output_schema"] = contract["schema"]
            request_config["_output_schema_name"] = contract["version"].replace("-", "_").replace("/", "_")
            claimed["provider_model"] = config["model"]
            self.story.set_context_manifest(job_id, manifest)
            api_key = self.secrets.get_api_key()
            def generate(request_messages):
                if self.story.get_job(save_id, job_id)["status"] != "running":
                    return None
                if job_type in {"turns_to_arc", "arcs_to_arc"}:
                    return self.provider.generate_story_arc(
                        request_config, api_key, request_messages,
                        lambda result: self.database.set_model_capability(config, result))
                return self.provider.generate_narrative(
                    request_config, api_key, request_messages,
                    lambda result: self.database.set_model_capability(config, result))
            first_error = None
            for attempt in range(2):
                request_messages = list(messages)
                if first_error is not None:
                    request_messages.append({"role": "system", "content": (
                        "上一份回复未通过程序校验。不要讨论错误，不要添加解释或代码围栏；请重新返回一个完整JSON对象。\n"
                        "校验失败位置：" + first_error)})
                try:
                    proposal = self._call_provider_with_concurrency_fallback(
                        config, lambda: generate(request_messages))
                    if proposal is None:
                        self.story.fail(save_id, job_id, "GENERATION_CANCELLED", "生成已取消")
                        return
                    if job_type in {"turns_to_arc", "arcs_to_arc"}:
                        self.story.complete_arc(claimed, validate_story_arc(proposal, contract))
                        return
                    outcome = self.story.complete_turn(
                        claimed, validate_gm_response(proposal, job_type, contract))
                    if outcome == "succeeded":
                        arc_job, created = self.story.create_arc_job(save_id, {}, automatic=True)
                        if created:
                            self.schedule_narrative(save_id, arc_job["id"])
                    return
                except ProviderError as exc:
                    if exc.code != "MODEL_OUTPUT_FORMAT":
                        raise
                    detail = "JSON解析：" + exc.message
                except (ContractError, ValueError) as exc:
                    detail = "回复契约或权威规则：" + str(exc)
                if attempt == 0:
                    first_error = detail[:1600]
                    continue
                raise ContractError(
                    "自动修正重试后回复仍不合法。第一次错误：" + first_error +
                    "；第二次错误：" + detail[:1600])
        except ProviderError as exc:
            if exc.code == "MODEL_TIMEOUT":
                if claimed and claimed["job"]["type"] in {"turns_to_arc", "arcs_to_arc"}:
                    message = ("故事弧整理请求已超时，系统不会自动重试。故事弧任务固定开启模型思考；"
                               "你可以在设置中提高请求超时时长，或更换响应更快的模型后重试。")
                else:
                    message = ("剧情生成请求已超时，系统不会自动重试。你可以在设置中提高请求超时时长，"
                               "或关闭模型思考后重新提交。")
            else:
                message = exc.message
            self.story.fail(save_id, job_id, exc.code, message, exc.retryable)
        except ContractError as exc:
            self.story.fail(save_id, job_id, "MODEL_OUTPUT_FORMAT", str(exc), False)
        except Exception:
            self.story.fail(save_id, job_id, "INTERNAL_ERROR", "叙事任务发生内部错误", True)
        finally:
            current = threading.current_thread()
            with self._worker_lock:
                self._workers.discard(current)

    def wait_for_workers(self, timeout=2):
        with self._worker_lock:
            workers = list(self._workers)
        for worker in workers:
            worker.join(timeout)


class FantasySimulatorHandler(BaseHTTPRequestHandler):
    server_version = "FantasySimulator/phase-2"

    def log_message(self, format_string, *args):
        # log_request emits a sanitized line; never log headers, bodies or queries.
        return

    def log_request(self, code="-", size="-"):
        path = urllib.parse.urlsplit(self.path).path
        print(f'{self.client_address[0]} "{self.command} {path}" {code} {size}')

    @property
    def app(self):
        return self.server.app_context

    def do_GET(self):
        self._dispatch("GET")

    def do_POST(self):
        self._dispatch("POST")

    def do_PUT(self):
        self._dispatch("PUT")

    def do_PATCH(self):
        self._dispatch("PATCH")

    def do_DELETE(self):
        self._dispatch("DELETE")

    def _dispatch(self, method):
        trace_id = str(uuid.uuid4())
        try:
            split = urllib.parse.urlsplit(self.path)
            self._api_query = {}
            if split.query and (split.path == "/api" or split.path.startswith("/api/")):
                if not (method == "GET" and (split.path.endswith("/turns") or
                                              split.path.endswith("/journals"))):
                    raise DomainError("INVALID_INPUT", "API不接受查询参数", 400)
                parsed_query = urllib.parse.parse_qs(split.query, keep_blank_values=True)
                if set(parsed_query) - {"cursor", "limit"} or any(len(values) != 1 for values in parsed_query.values()):
                    raise DomainError("INVALID_INPUT", "分页查询参数无效", 400)
                try:
                    cursor = int(parsed_query.get("cursor", ["0"])[0])
                    limit = int(parsed_query.get("limit", ["50"])[0])
                except ValueError:
                    raise DomainError("INVALID_INPUT", "cursor和limit必须是整数", 400) from None
                if cursor < 0 or not 1 <= limit <= 100:
                    raise DomainError("INVALID_INPUT", "分页范围无效", 400)
                self._api_query = {"cursor": cursor, "limit": limit, "enabled": True}
            path = split.path
            if path == "/api" or path.startswith("/api/"):
                status, payload, headers = self._route_api(method, path)
                headers = dict(headers)
                headers.setdefault("X-Trace-Id", trace_id)
                self._send_json(status, payload, headers)
            elif method == "GET":
                self._serve_static(path)
            else:
                raise DomainError("NOT_FOUND", "接口不存在", 404)
        except DomainError as exc:
            self._send_error_json(exc.status, exc.code, exc.message, exc.fields, exc.retryable, trace_id)
        except ProviderError as exc:
            status = 502
            if exc.code in {"MODEL_NOT_CONFIGURED", "INVALID_INPUT"}:
                status = 409 if exc.code == "MODEL_NOT_CONFIGURED" else 400
            elif exc.code == "MODEL_AUTH_FAILED":
                status = 401
            elif exc.code == "MODEL_TIMEOUT":
                status = 504
            elif exc.code == "MODEL_RATE_LIMITED":
                status = 429
            self._send_error_json(status, exc.code, exc.message, {}, exc.retryable, trace_id)
        except (BrokenPipeError, ConnectionResetError):
            return
        except Exception:
            print(f"[{trace_id}] unhandled server error")
            self._send_error_json(500, "INTERNAL_ERROR", "服务器发生内部错误", {}, True, trace_id)

    def _route_api(self, method, path):
        db = self.app.database
        parts = [urllib.parse.unquote(part) for part in path.strip("/").split("/")]
        if method == "GET" and path == "/api/health":
            return 200, {"status": "ok", "app_id": APP_ID, "api_version": API_VERSION}, {}
        if method == "GET" and path == "/api/world/catalog":
            return 200, CATALOG, {}
        if method == "GET" and path == "/api/settings":
            return 200, db.get_settings(bool(self.app.secrets.get_api_key()),
                                        self.app.secrets.persistence), {}
        if method == "PUT" and path == "/api/settings/model":
            body = self._read_json()
            self.app.validate_response_format_update(body)
            body.pop("structured_output_probe_token", None)
            revision = db.write_model_settings_with_secret(body, self.app.secrets)
            self.app.sync_provider_limit(db.get_model_config())
            return 200, db.get_settings(bool(self.app.secrets.get_api_key()),
                                        self.app.secrets.persistence), {"X-Revision": str(revision)}
        if method == "POST" and path == "/api/settings/model/test":
            body = self._read_json(optional=True)
            allowed = {"protocol", "base_url", "model", "timeout_seconds", "structured_output",
                       "max_concurrency", "thinking_enabled", "api_key",
                       "force_thinking_probe", "probe_structured_output",
                       "force_response_format_probe"}
            unknown = set(body) - allowed
            if unknown:
                raise DomainError("INVALID_INPUT", "存在未知连接测试字段", 400,
                                  fields={key: "未知字段" for key in unknown})
            config = db.get_model_config()
            force_thinking_probe = body.get("force_thinking_probe", False)
            if type(force_thinking_probe) is not bool:
                raise DomainError("INVALID_INPUT", "force_thinking_probe必须是布尔值", 400,
                                  fields={"force_thinking_probe": "必须是布尔值"})
            for field in ("probe_structured_output", "force_response_format_probe"):
                if field in body and type(body[field]) is not bool:
                    raise DomainError("INVALID_INPUT", f"{field}必须是布尔值", 400,
                                      fields={field: "必须是布尔值"})
            if "structured_output" in body and type(body["structured_output"]) is not bool:
                raise DomainError("INVALID_INPUT", "structured_output必须是布尔值", 400,
                                  fields={"structured_output": "必须是布尔值"})
            protocol = body.get("protocol", config.get("protocol", "openai"))
            if not isinstance(protocol, str) or protocol not in {"openai", "anthropic"}:
                raise DomainError("INVALID_INPUT", "protocol必须是openai或anthropic", 400,
                                  fields={"protocol": "必须是openai或anthropic"})
            for field in ("base_url", "model"):
                if field in body and not isinstance(body[field], str):
                    raise DomainError("INVALID_INPUT", f"{field}必须是文本", 400,
                                      fields={field: "必须是文本"})
            if "api_key" in body and not isinstance(body["api_key"], str):
                raise DomainError("INVALID_INPUT", "api_key必须是文本", 400,
                                  fields={"api_key": "必须是文本"})
            timeout = body.get("timeout_seconds", config.get("timeout_seconds", 300))
            if type(timeout) not in (int, float) or not 1 <= timeout <= 600:
                raise DomainError("INVALID_INPUT", "timeout_seconds必须在1至600秒之间", 400,
                                  fields={"timeout_seconds": "必须在1至600秒之间"})
            concurrency = body.get("max_concurrency", config.get("max_concurrency", 2))
            if type(concurrency) is not int or not 1 <= concurrency <= 16:
                raise DomainError("INVALID_INPUT", "max_concurrency必须是1至16的整数", 400,
                                  fields={"max_concurrency": "必须是1至16的整数"})
            config.update({key: value for key, value in body.items()
                           if key not in {"api_key", "force_thinking_probe",
                                          "probe_structured_output",
                                          "force_response_format_probe"}})
            api_key = body.get("api_key", self.app.secrets.get_api_key())
            if (body.get("probe_structured_output", False) or
                    body.get("force_response_format_probe", False)):
                response_format = self.app._call_provider_with_concurrency_fallback(
                    config, lambda: self.app.provider.probe_response_format(config, api_key))
                response_format = db.set_response_format_capability(config, response_format)
                thinking = db.get_model_capability(config)
                result = {
                    "connected": True,
                    "model_available": True,
                    "thinking": thinking,
                    "structured_output": response_format,
                    "message": response_format["message"],
                    "may_have_cost": True,
                }
                view = model_test_to_view(result)
                if response_format["capability"] == "supported":
                    view["structured_output_probe_token"] = (
                        self.app.create_response_format_probe(config, api_key, "supported"))
                return 200, view, {}
            cached = db.get_model_capability(config)
            result = self.app._call_provider_with_concurrency_fallback(
                config, lambda: self.app.provider.test_connection(
                    config, api_key, cached,
                    force_thinking_probe=force_thinking_probe))
            thinking = result.get("thinking")
            if isinstance(thinking, dict) and result.get("thinking_probed", True):
                result["thinking"] = db.set_model_capability(config, thinking)
            response_format = db.get_response_format_capability(config)
            result["structured_output"] = response_format
            return 200, model_test_to_view(result), {}
        if method == "PUT" and path == "/api/settings/narration":
            revision = db.update_narration_settings(self._read_json())
            return 200, db.get_settings(bool(self.app.secrets.get_api_key()),
                                        self.app.secrets.persistence), {"X-Revision": str(revision)}
        if path == "/api/saves":
            if method == "GET":
                return 200, {"items": db.list_saves()}, {}
            if method == "POST":
                body = self._read_json(optional=True)
                return 201, db.create_save_from_request(body), {}
        if path == "/api/saves/import/validate" and method == "POST":
            preview = db.validate_import(self._read_json())
            preview.pop("normalized", None)
            preview["save_name"] = preview.pop("name")
            return 200, preview, {}
        if path == "/api/saves/import" and method == "POST":
            result = db.import_save(self._read_json())
            return (202 if result.get("status") == "pending" else 201), result, {}
        if path == "/api/imports/validate" and method == "POST":
            preview = db.validate_import(self._read_json(max_bytes=MAX_IMPORT_BYTES))
            preview.pop("normalized", None); preview["save_name"] = preview.pop("name")
            return 200, preview, {}
        if path == "/api/imports" and method == "POST":
            body = self._read_json(max_bytes=MAX_IMPORT_BYTES)
            if "payload" in body:
                request = body
            else:
                request_id = self.headers.get("X-Request-Id")
                request = {"request_id": request_id, "payload": body}
            result = db.import_save(request)
            return (202 if result.get("status") == "pending" else 201), result, {}
        if len(parts) == 4 and parts[:2] == ["api", "imports"] and parts[3] == "trust-and-import" and method == "POST":
            return 201, db.trust_and_import(parts[2], self._read_json()), {}

        if len(parts) >= 3 and parts[:2] == ["api", "saves"]:
            save_id = parts[2]
            if len(parts) == 3:
                if method == "GET":
                    return 200, db.get_save(save_id), {}
                if method == "PATCH":
                    return 200, db.patch_save(save_id, self._read_json()), {}
                if method == "DELETE":
                    db.delete_save(save_id, self._read_json())
                    return 200, {"deleted": True, "save_id": save_id}, {}
            if len(parts) == 4 and parts[3] == "preferences" and method == "PUT":
                return 200, db.update_save_preferences(save_id, self._read_json()), {}
            if len(parts) == 4 and parts[3] == "export" and method == "GET":
                payload = db.export_save(save_id)
                filename = f"fantasy-simulator-{save_id}.json"
                return 200, payload, {"Content-Disposition": f'attachment; filename="{filename}"'}
            if len(parts) == 4 and parts[3] == "character-draft":
                if method == "GET":
                    return 200, draft_to_view(db.get_draft(save_id)), {}
                if method == "PUT":
                    result = db.put_draft(save_id, draft_from_view(self._read_json()))
                    return 200, draft_to_view(result["draft"]), {"X-Save-Revision": str(result["save"]["revision"])}
            if len(parts) == 4 and parts[3] == "character-generations" and method == "POST":
                config = db.get_model_config()
                job, created = db.create_generation(save_id, self._read_json(),
                                                    bool(config.get("base_url") and config.get("model")))
                if created:
                    self.app.schedule(save_id, job["id"])
                return (202 if created else 200), job, {}
            if len(parts) == 5 and parts[3] == "character-generations" and method == "GET":
                return 200, db.get_job(save_id, parts[4]), {}
            if len(parts) == 6 and parts[3] == "character-generations" and parts[5] == "cancel" and method == "POST":
                body = self._read_json(optional=True)
                if set(body) - {"request_id"}:
                    raise DomainError("INVALID_INPUT", "存在未知取消请求字段", 400)
                if not isinstance(body.get("request_id"), str) or not body["request_id"]:
                    raise DomainError("INVALID_INPUT", "request_id不能为空", 400,
                                      fields={"request_id": "格式无效"})
                return 200, db.cancel_job(save_id, parts[4]), {}
            if len(parts) == 4 and parts[3] == "character-candidate" and method == "GET":
                candidate = db.get_candidate(save_id)
                return 200, candidate_to_view(candidate, db.get_draft(save_id)["data"]), {}
            if len(parts) == 5 and parts[3:5] == ["character", "confirm"] and method == "POST":
                db.confirm_character(save_id, self._read_json())
                return 200, bootstrap_to_view(db.game_bootstrap(save_id)), {}
            if len(parts) == 4 and parts[3] == "game-bootstrap" and method == "GET":
                result = bootstrap_to_view(db.game_bootstrap(save_id))
                result["story"] = self.app.story.story_view(save_id)
                result["gm_turns_available"] = True
                return 200, result, {}
            if len(parts) == 4 and parts[3] == "story" and method == "GET":
                return 200, self.app.story.story_view(save_id), {}
            if len(parts) == 5 and parts[3:5] == ["story", "opening"] and method == "POST":
                job, created = self.app.story.create_job(save_id, "opening", self._read_json())
                if created: self.app.schedule_narrative(save_id, job["id"])
                return (202 if created else 200), job, {}
            if len(parts) == 5 and parts[3:5] == ["story", "start-prerequisite"] and method == "POST":
                return 200, self.app.story.resolve_start_prerequisite(save_id, self._read_json()), {}
            if len(parts) == 4 and parts[3] == "turns":
                if method == "GET": return 200, self.app.story.list_turns(save_id, **self._api_query), {}
                if method == "POST":
                    job, created = self.app.story.create_job(save_id, "turn", self._read_json())
                    if created: self.app.schedule_narrative(save_id, job["id"])
                    return (202 if created else 200), job, {}
            if len(parts) == 5 and parts[3:5] == ["turns", "intervene"] and method == "POST":
                job, created = self.app.story.create_job(save_id, "intervene", self._read_json())
                if created: self.app.schedule_narrative(save_id, job["id"])
                return (202 if created else 200), job, {}
            if len(parts) == 5 and parts[3] == "turns" and method == "GET":
                return 200, self.app.story.get_turn(save_id, parts[4]), {}
            if len(parts) == 6 and parts[3] == "turns" and parts[5] == "reshape" and method == "POST":
                job, created = self.app.story.create_job(save_id, "reshape", self._read_json(), parts[4])
                if created: self.app.schedule_narrative(save_id, job["id"])
                return (202 if created else 200), job, {}
            if len(parts) == 5 and parts[3] == "narrative-jobs" and method == "GET":
                return 200, self.app.story.get_job(save_id, parts[4]), {}
            if len(parts) == 6 and parts[3] == "narrative-jobs" and parts[5] == "cancel" and method == "POST":
                return 200, self.app.story.cancel(save_id, parts[4], self._read_json()), {}
            if len(parts) == 4 and parts[3] in {"character-state", "inventory", "quests", "journals",
                                                            "memory", "memories", "bonds", "reputations"} and method == "GET":
                return 200, self.app.story.projections(save_id, parts[3], **self._api_query), {}
            if len(parts) == 4 and parts[3] == "story-arcs" and method == "POST":
                body = self._read_json(); job, created = self.app.story.create_arc_job(save_id, body)
                if created: self.app.schedule_narrative(save_id, job["id"])
                return (202 if created else 200), job, {}
            if len(parts) == 5 and parts[3:5] == ["story-arcs", "merge"] and method == "POST":
                body = self._read_json(); job, created = self.app.story.create_arc_job(
                    save_id, body, body.get("arc_ids"))
                if created: self.app.schedule_narrative(save_id, job["id"])
                return (202 if created else 200), job, {}
        raise DomainError("NOT_FOUND", "接口不存在", 404)

    def _read_json(self, optional=False, max_bytes=MAX_REQUEST_BYTES):
        content_type = self.headers.get("Content-Type", "")
        length_text = self.headers.get("Content-Length")
        if not length_text:
            if optional:
                return {}
            raise DomainError("INVALID_JSON", "请求体不能为空", 400)
        try:
            length = int(length_text)
        except ValueError:
            raise DomainError("INVALID_JSON", "Content-Length无效", 400) from None
        if length < 0 or length > max_bytes:
            raise DomainError("REQUEST_TOO_LARGE", f"请求体超过{max_bytes // (1024 * 1024)}MB限制", 413)
        if "application/json" not in content_type.lower():
            raise DomainError("UNSUPPORTED_MEDIA_TYPE", "请求必须使用application/json", 415)
        try:
            if max_bytes > MAX_REQUEST_BYTES:
                with tempfile.SpooledTemporaryFile(max_size=2_000_000, mode="w+b") as temporary:
                    remaining = length
                    while remaining:
                        chunk = self.rfile.read(min(1_048_576, remaining))
                        if not chunk:
                            raise ValueError("truncated body")
                        temporary.write(chunk); remaining -= len(chunk)
                    temporary.seek(0)
                    value = json.load(temporary, parse_constant=lambda item: (_ for _ in ()).throw(ValueError(item)))
            else:
                value = json.loads(self.rfile.read(length).decode("utf-8"),
                                   parse_constant=lambda item: (_ for _ in ()).throw(ValueError(item)))
        except (UnicodeError, ValueError):
            raise DomainError("INVALID_JSON", "请求体不是有效的UTF-8 JSON", 400) from None
        if not isinstance(value, dict):
            raise DomainError("INVALID_JSON", "请求JSON顶层必须是对象", 400)
        return value

    def _send_json(self, status, payload, extra_headers=None):
        body = b"" if status == 204 else json.dumps(
            payload, ensure_ascii=False, separators=(",", ":")
        ).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for key, value in (extra_headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def _send_error_json(self, status, code, message, fields, retryable, trace_id):
        self._send_json(status, {"error": {"code": code, "message": message,
                                           "fields": fields, "field_errors": fields,
                                           "retryable": bool(retryable),
                                           "trace_id": trace_id}}, {"X-Trace-Id": trace_id})

    def _serve_static(self, request_path):
        static_root = Path(self.app.static_dir).resolve()
        decoded = urllib.parse.unquote(request_path)
        relative = posixpath.normpath(decoded.lstrip("/"))
        if any(part == ".." for part in decoded.replace("\\", "/").split("/")):
            self.send_error(404)
            return
        if relative in {"", "."}:
            relative = "index.html"
        requested = (static_root / relative).resolve()
        try:
            requested.relative_to(static_root)
        except ValueError:
            self.send_error(404)
            return
        if not requested.is_file():
            requested = static_root / "index.html"
        if not requested.is_file():
            message = b"Web build not found"
            self.send_response(404)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(message)))
            self.end_headers()
            self.wfile.write(message)
            return
        body = requested.read_bytes()
        content_type = mimetypes.guess_type(str(requested))[0] or "application/octet-stream"
        if content_type.startswith("text/") or content_type in {"application/javascript", "application/json"}:
            content_type += "; charset=utf-8"
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        if requested.name == "index.html":
            self.send_header("Cache-Control", "no-cache")
        else:
            self.send_header("Cache-Control", "public, max-age=3600")
        self.end_headers()
        self.wfile.write(body)


def create_server(host="127.0.0.1", port=8000, data_dir=None, static_dir=None, provider=None):
    api_dir = Path(__file__).resolve().parent
    workspace = api_dir.parents[1]
    data_dir = data_dir or str(api_dir / ".data")
    static_dir = static_dir or str(workspace / "apps" / "web" / "dist")
    server = ThreadingHTTPServer((host, port), FantasySimulatorHandler)
    server.daemon_threads = True
    server.app_context = AppContext(data_dir, static_dir, provider)
    server.app_context.resume_queued()
    return server


def main():
    parser = argparse.ArgumentParser(description="Fantasy Simulator phase-one server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--data-dir")
    parser.add_argument("--static-dir")
    args = parser.parse_args()
    server = create_server(args.host, args.port, args.data_dir, args.static_dir)
    print(f"Fantasy Simulator listening on http://{args.host}:{server.server_port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
