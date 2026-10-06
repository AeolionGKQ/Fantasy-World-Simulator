import json
import io
import sqlite3
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock

API_DIR = Path(__file__).resolve().parents[1]
APPS_DIR = API_DIR.parent
if str(APPS_DIR) not in sys.path:
    sys.path.insert(0, str(APPS_DIR))

from api.database import SecretStore
from api.model_provider import (THINKING_CONFIG_VERSION, THINKING_STRATEGIES,
                                AnthropicCompatibleProvider, ModelProvider,
                                OpenAICompatibleProvider, OpenAIImageProvider, ProviderError, _request,
                                is_explicit_concurrency_rejection,
                                is_explicit_parameter_rejection, thinking_parameters,
                                thinking_capability_key, response_format_capability_key,
                                validate_candidate)
from api.server import AppContext, create_server


VALID_PROPOSAL = {
    "attributes": {
        "con": {"value": 61, "reason": "经常旅行且接受过训练。"},
        "int": {"value": 72, "reason": "学习能力和知识基础较好。"},
        "cha": {"value": 55, "reason": "待人平和但不擅长公开演说。"},
    },
    "resources": {
        "hp": {"max": 240, "reason": "体质与阶位共同决定。"},
        "mp": {"max": 310, "reason": "拥有稳定魔力基础。"},
        "sp": {"max": 180, "reason": "精神状态稳定。"},
        "st": {"max": 260, "reason": "具备持续活动能力。"},
    },
    "starting_currency": {"copper": 450, "reason": "边境家庭准备了基础旅费。"},
    "summary": "擅长学习与持续探索的均衡角色。",
    "strengths": ["学习迅速", "状态稳定"],
    "limitations": ["缺少高强度实战经验"],
}


class FakeProvider:
    def __init__(self):
        self.calls = 0
        self.block = False
        self.started = threading.Event()
        self.release = threading.Event()
        self.proposal = VALID_PROPOSAL
        self.test_config = None
        self.test_api_key = None
        self.test_calls = 0
        self.probe_calls = 0
        self.response_format_probe_calls = 0
        self.response_format_capability = "supported"
        self.capability_update = None

    def test_connection(self, config, api_key, cached_capability=None,
                        force_thinking_probe=False):
        self.test_calls += 1
        self.test_config = dict(config)
        self.test_api_key = api_key
        thinking = (cached_capability if not force_thinking_probe else {
                    "capability": "controlled", "strategy": "enable_thinking",
                    "confidence": "verified", "message": "已验证思考控制参数：enable_thinking。",
                })
        probed = thinking is not cached_capability
        if probed:
            self.probe_calls += 1
        return {"connected": True, "model_available": True,
                "structured_output": "unknown", "thinking": thinking,
                "thinking_probed": probed}

    def probe_response_format(self, config, api_key):
        self.response_format_probe_calls += 1
        capability = self.response_format_capability
        return {
            "capability": capability, "strategy": "json_object",
            "last_failure": "unsupported response_format" if capability == "unsupported" else None,
            "message": ("已验证当前服务支持 response_format。" if capability == "supported" else
                        "当前服务明确不支持 response_format，无法开启结构化输出。"),
        }

    def generate_character(self, config, api_key, draft, feedback="", on_thinking_capability=None):
        self.calls += 1
        self.started.set()
        if self.block:
            self.release.wait(3)
        if self.capability_update and on_thinking_capability:
            on_thinking_capability(dict(self.capability_update))
        return json.loads(json.dumps(self.proposal, ensure_ascii=False))


class ConcurrentRejectingProvider(FakeProvider):
    def __init__(self, rejection_message="Too many concurrent requests"):
        super().__init__()
        self.lock = threading.Lock()
        self.first_started = threading.Event()
        self.second_rejected = threading.Event()
        self.release_first = threading.Event()
        self.active = 0
        self.max_active = 0
        self.calls_by_name = {}
        self.rejection_message = rejection_message
        self.allow_second_rejection = None

    def generate_character(self, config, api_key, draft, feedback="", on_thinking_capability=None):
        name = draft["name"]
        with self.lock:
            self.active += 1
            self.max_active = max(self.max_active, self.active)
            self.calls_by_name[name] = self.calls_by_name.get(name, 0) + 1
            active = self.active
            attempt = self.calls_by_name[name]
        try:
            if active == 1 and not self.first_started.is_set():
                self.first_started.set()
                self.release_first.wait(3)
            elif active > 1 and attempt == 1:
                self.second_rejected.set()
                if self.allow_second_rejection is not None:
                    self.allow_second_rejection.wait(3)
                raise ProviderError(
                    "MODEL_RATE_LIMITED", "模型服务请求过于频繁", True, 429,
                    self.rejection_message)
            return json.loads(json.dumps(self.proposal, ensure_ascii=False))
        finally:
            with self.lock:
                self.active -= 1


class DrainingProvider(FakeProvider):
    def __init__(self):
        super().__init__()
        self.lock = threading.Lock()
        self.first_started = threading.Event()
        self.second_started = threading.Event()
        self.third_started = threading.Event()
        self.release_first = threading.Event()
        self.release_third = threading.Event()
        self.calls = []
        self.active = 0
        self.retry_active = None

    def generate_character(self, config, api_key, draft, feedback="", on_thinking_capability=None):
        name = draft["name"]
        with self.lock:
            self.active += 1
            self.calls.append(name)
            attempt = self.calls.count(name)
        try:
            if name == "first":
                self.first_started.set()
                self.release_first.wait(3)
            elif name == "second" and attempt == 1:
                self.second_started.set()
                raise ProviderError("MODEL_RATE_LIMITED", "并发拒绝", True, 429,
                                    "too many concurrent requests")
            elif name == "second":
                with self.lock:
                    self.retry_active = self.active
            else:
                self.third_started.set()
                self.release_third.wait(3)
            return json.loads(json.dumps(self.proposal, ensure_ascii=False))
        finally:
            with self.lock:
                self.active -= 1


class FakeHttpResponse:
    def __init__(self, payload):
        self.payload = json.dumps(payload).encode("utf-8")
        self.length = len(self.payload)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def read(self, _limit):
        return self.payload


class ProviderTestCase(unittest.TestCase):
    @staticmethod
    def config():
        return {"base_url": "https://model.example/v1", "model": "model-a",
                "timeout_seconds": 1, "structured_output": True}

    @staticmethod
    def http_error(status, payload, reason="rejected"):
        raw = (json.dumps(payload).encode("utf-8") if isinstance(payload, dict)
               else str(payload).encode("utf-8"))
        return urllib.error.HTTPError("https://model.example", status, reason, {}, io.BytesIO(raw))

    def test_request_reads_structured_and_text_http_error_without_secret(self):
        for payload, expected_message, expected_code, expected_param in (
                ({"error": {"message": "Unknown field enable_thinking Bearer fixture",
                             "code": "bad_field",
                             "param": "enable_thinking"}},
                 "Unknown field enable_thinking", "bad_field", "enable_thinking"),
                ("unsupported parameter reasoning_effort", "unsupported parameter reasoning_effort",
                 None, None)):
            error = self.http_error(400, payload)
            with self.subTest(payload=payload), mock.patch("urllib.request.urlopen", side_effect=error):
                with self.assertRaises(ProviderError) as raised:
                    _request("https://model.example", "fixture-secret", 1, max_retries=0)
            self.assertIn(expected_message, raised.exception.provider_message)
            self.assertNotIn("fixture-secret", raised.exception.message)
            self.assertEqual(expected_code, raised.exception.provider_code)
            self.assertEqual(expected_param, raised.exception.provider_param)

    def test_explicit_parameter_rejection_requires_status_semantics_and_named_field(self):
        fields = {"thinking", "enable_thinking", "reasoning_effort",
                  "chat_template_kwargs", "reasoning", "enabled", "effort",
                  "thinking_config", "thinking_budget", "response_format"}
        for field in fields:
            error = ProviderError("MODEL_REQUEST_REJECTED", "拒绝", http_status=400,
                                  provider_message=f"Unknown field: {field}")
            with self.subTest(field=field):
                self.assertTrue(is_explicit_parameter_rejection(error, {field}))
        for status, text in ((404, "unknown field thinking"),
                             (405, "unsupported parameter enable_thinking"),
                             (400, "model does not exist"),
                             (422, "invalid request"),
                             (400, "unknown field temperature")):
            error = ProviderError("MODEL_REQUEST_REJECTED", "拒绝", http_status=status,
                                  provider_message=text)
            with self.subTest(status=status, text=text):
                self.assertFalse(is_explicit_parameter_rejection(error, fields))

    def test_nested_control_field_names_are_explicit(self):
        for path, fields in (
                ("chat_template_kwargs.enable_thinking",
                 {"chat_template_kwargs", "enable_thinking"}),
                ("reasoning.enabled", {"reasoning", "enabled"}),
                ("reasoning.effort", {"reasoning", "effort"}),
                ("thinking_config.thinking_budget",
                 {"thinking_config", "thinking_budget"})):
            error = ProviderError(
                "MODEL_REQUEST_REJECTED", "拒绝", http_status=422,
                provider_message=f"Invalid field {path}",
            )
            with self.subTest(path=path):
                self.assertTrue(is_explicit_parameter_rejection(error, fields))

    def test_explicit_concurrency_rejection_is_conservative(self):
        for status, message, code in (
                (429, "Too many concurrent requests", None),
                (400, "Max concurrent requests exceeded", None),
                (409, "Simultaneous calls are not supported", "concurrency_limit"),
                (422, "供应商不支持并发，请勿同时请求", None)):
            error = ProviderError("MODEL_REQUEST_REJECTED", "拒绝", http_status=status,
                                  provider_message=message, provider_code=code)
            with self.subTest(status=status, message=message):
                self.assertTrue(is_explicit_concurrency_rejection(error))
        for status, message in (
                (429, "rate limit exceeded"), (429, "quota exceeded"),
                (429, "requests per minute exceeded"),
                (429, "tokens per minute exceeded"),
                (503, "too many concurrent requests"),
                (429, None)):
            error = ProviderError("MODEL_RATE_LIMITED", "请求过于频繁", http_status=status,
                                  provider_message=message)
            with self.subTest(status=status, message=message):
                self.assertFalse(is_explicit_concurrency_rejection(error))

    def test_generation_retries_without_rejected_response_format_and_keeps_context_small(self):
        proposal_response = {"choices": [{"message": {"content": json.dumps(VALID_PROPOSAL)}}]}
        requests = []

        def fake_urlopen(request, timeout):
            requests.append(json.loads(request.data.decode("utf-8")))
            if len(requests) == 1:
                raise self.http_error(400, {"error": {"message":
                                                       "Unknown field response_format"}})
            return FakeHttpResponse(proposal_response)

        with mock.patch("urllib.request.urlopen", side_effect=fake_urlopen):
            result = OpenAICompatibleProvider().generate_character(
                self.config(), "key", {
                    "race_id": "human", "name": "艾琳", "gender": "女", "age": 24,
                    "appearance": "黑发", "personality": "沉着", "rank": 3,
                    "talent": "魔力感知", "backstory": "旅行者",
                    "start_location_id": "grand_academy", "additional": "喜欢阅读",
                }, "更均衡")
        self.assertEqual(VALID_PROPOSAL, result)
        self.assertIn("response_format", requests[0])
        self.assertNotIn("response_format", requests[1])
        self.assertTrue(all("temperature" not in request for request in requests))
        context = json.loads(requests[1]["messages"][1]["content"])["generation_context"]
        self.assertEqual(320, context["base_power"])
        self.assertEqual("人类", context["race"]["name"])
        self.assertEqual("维尔瑟亚大联合学院", context["start_location"]["name"])
        self.assertTrue(any("1金币=100银币=10000铜币" in baseline
                            for baseline in context["world_baselines"]))
        system_prompt = requests[1]["messages"][0]["content"]
        self.assertIn("starting_currency", system_prompt)
        self.assertIn("身世与家世", system_prompt)
        self.assertIn("regeneration_feedback仅用于指导本次调整", system_prompt)
        self.assertIn("不要出现‘根据反馈’", system_prompt)
        self.assertEqual("旅行者", json.loads(requests[1]["messages"][1]["content"])["draft"]["backstory"])
        self.assertLess(len(json.dumps(context, ensure_ascii=False)), 3000)

    def test_starting_currency_is_required_positive_and_explained(self):
        valid = validate_candidate(json.loads(json.dumps(VALID_PROPOSAL, ensure_ascii=False)), 3)
        self.assertEqual({"copper": 450, "reason": "边境家庭准备了基础旅费。"},
                         valid["starting_currency"])
        self.assertEqual("character-candidate/2", valid["contract_version"])
        for value in (0, -1, 1.5, True, 1_000_000_001):
            proposal = json.loads(json.dumps(VALID_PROPOSAL, ensure_ascii=False))
            proposal["starting_currency"]["copper"] = value
            with self.subTest(value=value), self.assertRaises(ProviderError):
                validate_candidate(proposal, 3)
        for reason in ("", "   ", "x" * 2001):
            proposal = json.loads(json.dumps(VALID_PROPOSAL, ensure_ascii=False))
            proposal["starting_currency"]["reason"] = reason
            with self.subTest(reason_length=len(reason)), self.assertRaises(ProviderError):
                validate_candidate(proposal, 3)
        missing = json.loads(json.dumps(VALID_PROPOSAL, ensure_ascii=False))
        del missing["starting_currency"]
        with self.assertRaises(ProviderError):
            validate_candidate(missing, 3)
        self.assertNotIn("starting_currency",
                         validate_candidate(missing, 3, allow_legacy_missing_currency=True))

    def test_request_retries_429_retry_after_and_5xx(self):
        url = "https://model.example/v1/models"
        effects = [
            urllib.error.HTTPError(url, 429, "rate", {"Retry-After": "0"}, None),
            urllib.error.HTTPError(url, 503, "down", {}, None),
            FakeHttpResponse({"data": []}),
        ]
        with mock.patch("urllib.request.urlopen", side_effect=effects) as call, mock.patch("time.sleep"):
            self.assertEqual({"data": []}, _request(url, "key", 1))
            self.assertEqual(3, call.call_count)

    def test_narrative_generation_disables_hidden_transport_retries(self):
        provider = OpenAICompatibleProvider()
        config = self.config()
        messages = [{"role": "user", "content": "返回JSON"}]
        with mock.patch("api.model_provider._request", side_effect=ProviderError(
                "MODEL_TIMEOUT", "模型服务请求超时", True)) as request:
            with self.assertRaises(ProviderError):
                provider.generate_narrative(config, "key", messages)
        self.assertEqual(0, request.call_args.kwargs["max_retries"])

    def test_story_arc_forces_thinking_on_when_narrative_toggle_is_off(self):
        response = {"choices": [{"message": {"content": json.dumps({
            "schema_version": "story-arc/1", "title": "弧", "summary": "摘要",
            "key_events": [], "unresolved": []})}}]}
        requests = []

        def respond(request, timeout):
            requests.append(json.loads(request.data.decode("utf-8")))
            return FakeHttpResponse(response)

        config = {**self.config(), "structured_output": False,
                  "thinking_strategy": "enable_thinking", "thinking_confidence": "verified",
                  "thinking_enabled": False}
        with mock.patch("urllib.request.urlopen", side_effect=respond):
            OpenAICompatibleProvider().generate_story_arc(config, "key", [])
        self.assertTrue(requests[0]["enable_thinking"])

    def test_anthropic_messages_request_headers_system_and_text_blocks(self):
        requests = []
        response = {"content": [
            {"type": "thinking", "thinking": "hidden"},
            {"type": "text", "text": json.dumps(VALID_PROPOSAL, ensure_ascii=False)},
        ]}

        def respond(request, timeout):
            requests.append(request)
            return FakeHttpResponse(response)

        config = {**self.config(), "protocol": "anthropic", "structured_output": False}
        with mock.patch("urllib.request.urlopen", side_effect=respond):
            result = ModelProvider().generate_character(config, "secret-key", {"rank": 3})
        self.assertEqual(VALID_PROPOSAL, result)
        request = requests[0]
        payload = json.loads(request.data.decode("utf-8"))
        self.assertEqual("https://model.example/v1/messages", request.full_url)
        self.assertEqual("secret-key", request.headers["X-api-key"])
        self.assertEqual("2023-06-01", request.headers["Anthropic-version"])
        self.assertNotIn("Authorization", request.headers)
        self.assertIn("角色属性生成器", payload["system"])
        self.assertEqual(["user"], [message["role"] for message in payload["messages"]])
        self.assertGreaterEqual(payload["max_tokens"], 4096)
        self.assertNotIn("temperature", payload)

        requests.clear()
        config["base_url"] = "https://api.anthropic.com"
        with mock.patch("urllib.request.urlopen", side_effect=respond):
            ModelProvider().generate_character(config, "secret-key", {"rank": 3})
        self.assertEqual("https://api.anthropic.com/v1/messages", requests[0].full_url)

        requests.clear()
        config["base_url"] = "https://api.anthropic.com/v1/messages"
        with mock.patch("urllib.request.urlopen", side_effect=respond):
            ModelProvider().generate_character(config, "secret-key", {"rank": 3})
        self.assertEqual("https://api.anthropic.com/v1/messages", requests[0].full_url)

        requests.clear()
        config["base_url"] = "https://model.example/v1"
        config.update({"structured_output": True,
                       "structured_output_strategy": "anthropic_json_schema"})
        with mock.patch("urllib.request.urlopen", side_effect=respond):
            ModelProvider().generate_character(config, "secret-key", {"rank": 3})
        schema = json.loads(requests[0].data.decode("utf-8"))["output_config"]["format"]["schema"]
        self.assertEqual(["con", "int", "cha"], schema["properties"]["attributes"]["required"])

    def test_openai_image_provider_request_and_png_validation(self):
        png = b"\x89PNG\r\n\x1a\nfixture"
        requests = []
        response = {"id": "image-request", "data": [{"b64_json": __import__("base64").b64encode(png).decode()}],
                    "usage": {"output_tokens": 1}}
        def respond(request, timeout):
            requests.append((request, json.loads(request.data.decode("utf-8"))))
            return FakeHttpResponse(response)
        config = {"base_url": "https://api.openai.com", "model": "gpt-image-2.5-sunburst",
                  "timeout_seconds": 30}
        with mock.patch("urllib.request.urlopen", side_effect=respond):
            result = OpenAIImageProvider().generate(config, "image-key", "fantasy scene",
                                                    "1536x1024", "high")
        self.assertEqual(png, result["bytes"])
        request, payload = requests[0]
        self.assertEqual("https://api.openai.com/v1/images/generations", request.full_url)
        self.assertEqual("gpt-image-2.5-sunburst", payload["model"])
        self.assertEqual("1536x1024", payload["size"])
        self.assertEqual("high", payload["quality"])
        self.assertNotIn("temperature", payload)

    def test_anthropic_thinking_probe_and_story_arc_controls(self):
        requests = []

        def accept(request, timeout):
            requests.append(json.loads(request.data.decode("utf-8")))
            return FakeHttpResponse({"content": [{"type": "text", "text": json.dumps({
                "schema_version": "story-arc/1", "title": "弧", "summary": "摘要",
                "key_events": [], "unresolved": []})}]})

        config = {**self.config(), "protocol": "anthropic", "structured_output": False}
        provider = AnthropicCompatibleProvider()
        with mock.patch("urllib.request.urlopen", side_effect=accept):
            capability = provider._probe_thinking(config, "key", 1)
        self.assertEqual("anthropic_adaptive", capability["strategy"])
        self.assertEqual({"type": "disabled"}, requests[0]["thinking"])
        self.assertEqual({"type": "adaptive"}, requests[1]["thinking"])

        def sonnet_55(request, timeout):
            payload = json.loads(request.data.decode("utf-8"))
            requests.append(payload)
            if payload.get("thinking", {}).get("type") == "disabled":
                raise self.http_error(400, {"error": {"message": (
                    'To turn thinking off on this model, send "thinking": '
                    '{"type": "between_tools"} instead of {"type": "disabled"}.')}})
            return FakeHttpResponse({"content": [{"type": "text", "text": "OK"}]})

        requests.clear()
        with mock.patch("urllib.request.urlopen", side_effect=sonnet_55):
            capability = provider._probe_thinking(config, "key", 1)
        self.assertEqual("anthropic_adaptive_between_tools", capability["strategy"])
        self.assertEqual({"type": "between_tools"}, requests[1]["thinking"])
        self.assertEqual({"type": "adaptive"}, requests[2]["thinking"])

        requests.clear()
        config.update({"thinking_strategy": "anthropic_enabled",
                       "thinking_confidence": "verified", "thinking_enabled": False})
        with mock.patch("urllib.request.urlopen", side_effect=accept):
            provider.generate_story_arc(config, "key", [{"role": "system", "content": "规则"}])
        self.assertEqual({"type": "enabled", "budget_tokens": 2048}, requests[0]["thinking"])
        self.assertNotIn("temperature", requests[0])

    def test_anthropic_connection_and_structured_output_probe(self):
        requests = []

        def accept(request, timeout):
            requests.append(json.loads(request.data.decode("utf-8")))
            payload = requests[-1]
            text = '{"ok":true}' if "output_config" in payload else "OK"
            return FakeHttpResponse({"content": [{"type": "text", "text": text}]})

        config = {**self.config(), "protocol": "anthropic"}
        cached = {"capability": "controlled", "strategy": "anthropic_adaptive",
                  "confidence": "verified", "message": "ok"}
        with mock.patch("urllib.request.urlopen", side_effect=accept):
            connected = AnthropicCompatibleProvider().test_connection(config, "key", cached)
            structured = AnthropicCompatibleProvider().probe_response_format(config, "key")
        self.assertTrue(connected["connected"])
        self.assertEqual("supported", structured["capability"])
        self.assertEqual("anthropic_json_schema", structured["strategy"])
        self.assertNotIn("response_format", requests[-1])
        self.assertEqual("json_schema", requests[-1]["output_config"]["format"]["type"])

    def test_protocol_is_part_of_capability_identity(self):
        openai = {**self.config(), "protocol": "openai"}
        anthropic = {**self.config(), "protocol": "anthropic"}
        self.assertNotEqual(thinking_capability_key(openai), thinking_capability_key(anthropic))
        self.assertNotEqual(response_format_capability_key(openai),
                            response_format_capability_key(anthropic))

    def test_request_stops_retrying_explicit_concurrency_429(self):
        url = "https://model.example/v1/models"
        effects = [
            self.http_error(429, {"error": {
                "message": "Too many concurrent requests",
                "code": "concurrency_limit",
            }}),
            FakeHttpResponse({"data": []}),
        ]
        with mock.patch("urllib.request.urlopen", side_effect=effects) as call, \
                mock.patch("time.sleep") as sleep:
            with self.assertRaises(ProviderError) as raised:
                _request(url, "key", 1)
        self.assertEqual(1, call.call_count)
        sleep.assert_not_called()
        self.assertEqual("MODEL_RATE_LIMITED", raised.exception.code)
        self.assertEqual("Too many concurrent requests",
                         raised.exception.provider_message)

    def test_request_retries_ordinary_429_twice_then_succeeds(self):
        url = "https://model.example/v1/models"
        effects = [
            self.http_error(429, {"error": {"message": "quota exceeded"}}),
            self.http_error(429, {"error": {
                "message": "requests per minute exceeded",
            }}),
            FakeHttpResponse({"data": []}),
        ]
        with mock.patch("urllib.request.urlopen", side_effect=effects) as call, \
                mock.patch("time.sleep"):
            self.assertEqual({"data": []}, _request(url, "key", 1))
        self.assertEqual(3, call.call_count)

    def test_models_unsupported_falls_back_to_minimal_chat_and_marks_cost(self):
        chat = {"choices": [{"message": {"content": "{\"ok\":true}"}}]}
        effects = [urllib.error.HTTPError("https://model.example/v1/models", 404, "missing", {}, None),
                   FakeHttpResponse(chat), FakeHttpResponse({"choices": [{"message": {"content": "OK"}}]})]
        with mock.patch("urllib.request.urlopen", side_effect=effects) as call:
            result = OpenAICompatibleProvider().test_connection(self.config(), "key")
        self.assertTrue(result["connected"])
        self.assertTrue(result["may_have_cost"])
        self.assertEqual(2, call.call_count)

    def test_transient_network_error_is_retried(self):
        effects = [urllib.error.URLError("temporary"), FakeHttpResponse({"data": []})]
        with mock.patch("urllib.request.urlopen", side_effect=effects) as call, mock.patch("time.sleep"):
            self.assertEqual({"data": []}, _request("https://model.example/v1/models", "", 1))
        self.assertEqual(2, call.call_count)

    @staticmethod
    def chat_ok():
        return FakeHttpResponse({"choices": [{"message": {"content": "OK"}}]})

    def test_thinking_probe_accepts_bundle_without_parsing_output(self):
        requests = []

        def fake_urlopen(request, timeout):
            requests.append(json.loads(request.data.decode("utf-8")))
            return self.chat_ok()

        with mock.patch("urllib.request.urlopen", side_effect=fake_urlopen) as call:
            result = OpenAICompatibleProvider()._probe_thinking(self.config(), "key", 1)
        self.assertEqual("accepted_bundle", result["confidence"])
        self.assertEqual("bundle", result["strategy"])
        self.assertEqual(1, call.call_count)
        self.assertEqual(False, requests[0]["enable_thinking"])
        self.assertEqual({"type": "disabled"}, requests[0]["thinking"])
        self.assertEqual("none", requests[0]["reasoning_effort"])
        self.assertEqual({"enable_thinking": False}, requests[0]["chat_template_kwargs"])
        self.assertEqual({"enabled": False, "effort": "none"}, requests[0]["reasoning"])
        self.assertEqual({"thinking_budget": 0}, requests[0]["thinking_config"])

    def test_thinking_config_version_invalidates_v1_cache(self):
        self.assertEqual("thinking-control-v2", THINKING_CONFIG_VERSION)

    def test_thinking_probe_tries_each_strategy_in_order(self):
        rejected_fields = ["enable_thinking"] + [
            next(iter(thinking_parameters(strategy, False)))
            for strategy in THINKING_STRATEGIES[:-1]
        ]
        for successful_index, expected in enumerate(THINKING_STRATEGIES, 1):
            rejected = rejected_fields[:successful_index]
            effects = [self.http_error(400, {"error": {"message": f"Unknown field {field}"}})
                       for field in rejected] + [self.chat_ok()]
            with self.subTest(strategy=expected), mock.patch(
                    "urllib.request.urlopen", side_effect=effects) as call:
                result = OpenAICompatibleProvider()._probe_thinking(self.config(), "key", 1)
            self.assertEqual("verified", result["confidence"])
            self.assertEqual(expected, result["strategy"])
            self.assertEqual(successful_index + 1, call.call_count)
        self.assertEqual({"reasoning": {"enabled": False}},
                         thinking_parameters("reasoning_enabled", False))
        self.assertEqual({"reasoning": {"effort": "none"}},
                         thinking_parameters("reasoning_effort_nested", False))

    def test_thinking_probe_all_rejected_is_unsupported(self):
        rejected_fields = ["enable_thinking"] + [
            next(iter(thinking_parameters(strategy, False))) for strategy in THINKING_STRATEGIES
        ]
        effects = [self.http_error(422, {"error": {"message": f"Unsupported parameter {field}"}})
                   for field in rejected_fields]
        with mock.patch("urllib.request.urlopen", side_effect=effects) as call:
            result = OpenAICompatibleProvider()._probe_thinking(self.config(), "key", 1)
        self.assertEqual("unsupported", result["capability"])
        self.assertEqual(1 + len(THINKING_STRATEGIES), call.call_count)

    def test_thinking_probe_rate_limit_and_timeout_are_not_unsupported(self):
        errors = [
            ProviderError("MODEL_RATE_LIMITED", "限流", True, 429),
            ProviderError("MODEL_TIMEOUT", "超时", True),
        ]
        for error in errors:
            with self.subTest(code=error.code), mock.patch(
                    "api.model_provider._request", side_effect=error) as call:
                with self.assertRaises(ProviderError) as raised:
                    OpenAICompatibleProvider()._probe_thinking(self.config(), "key", 1)
            self.assertEqual(error.code, raised.exception.code)
            self.assertEqual(1, call.call_count)

    def test_response_format_probe_supported_and_minimal(self):
        requests = []

        def respond(request, timeout):
            requests.append(json.loads(request.data.decode("utf-8")))
            return self.chat_ok()

        with mock.patch("urllib.request.urlopen", side_effect=respond):
            result = OpenAICompatibleProvider().probe_response_format(self.config(), "key")
        self.assertEqual("supported", result["capability"])
        self.assertEqual({"type": "json_object"}, requests[0]["response_format"])
        self.assertEqual(8, requests[0]["max_tokens"])
        self.assertNotIn("temperature", requests[0])

    def test_response_format_probe_only_explicit_rejection_is_unsupported(self):
        provider = OpenAICompatibleProvider()
        with mock.patch("urllib.request.urlopen", side_effect=self.http_error(
                422, {"error": {"message": "response_format is not allowed"}})):
            result = provider.probe_response_format(self.config(), "key")
        self.assertEqual("unsupported", result["capability"])
        for error in (
                self.http_error(400, {"error": {"message": "invalid model identifier"}}),
                self.http_error(401, {"error": {"message": "bad credentials"}}),
                urllib.error.URLError("offline")):
            with self.subTest(error=error), mock.patch(
                    "urllib.request.urlopen", side_effect=error), self.assertRaises(ProviderError):
                provider.probe_response_format(self.config(), "key")

    def test_settings_model_checks_cap_timeout_and_disable_transport_retries(self):
        provider = OpenAICompatibleProvider()
        config = self.config()
        config["timeout_seconds"] = 600
        with mock.patch("api.model_provider._request", return_value={"data": [
                {"id": config["model"]}]}) as request:
            provider.test_connection(config, "key", {
                "confidence": "verified", "capability": "controlled",
                "strategy": "thinking", "message": "ok"})
        self.assertEqual(30.0, request.call_args.args[2])
        self.assertEqual(0, request.call_args.kwargs["max_retries"])
        with mock.patch("api.model_provider._request", return_value=None) as request:
            provider.probe_response_format(config, "key")
        self.assertEqual(30.0, request.call_args.args[2])
        self.assertEqual(0, request.call_args.kwargs["max_retries"])

    def test_generation_uses_control_values_and_falls_back_without_controls(self):
        proposal_response = {"choices": [{"message": {"content": json.dumps(VALID_PROPOSAL)}}]}
        for strategy, key, disabled, enabled in (
                ("enable_thinking", "enable_thinking", False, True),
                ("thinking", "thinking", {"type": "disabled"}, {"type": "enabled"}),
                ("reasoning_effort", "reasoning_effort", "none", "medium"),
                ("chat_template_kwargs", "chat_template_kwargs", {"enable_thinking": False}, {"enable_thinking": True}),
                ("reasoning_enabled", "reasoning", {"enabled": False}, {"enabled": True}),
                ("reasoning_effort_nested", "reasoning", {"effort": "none"}, {"effort": "medium"}),
                ("thinking_budget", "thinking_config", {"thinking_budget": 0}, {"thinking_budget": -1})):
            for is_enabled, expected in ((False, disabled), (True, enabled)):
                config = {**self.config(), "structured_output": False,
                          "thinking_strategy": strategy, "thinking_confidence": "verified",
                          "thinking_enabled": is_enabled}
                requests = []

                def fake_urlopen(request, timeout):
                    requests.append(json.loads(request.data.decode("utf-8")))
                    return FakeHttpResponse(proposal_response)

                with self.subTest(strategy=strategy, enabled=is_enabled), mock.patch(
                        "urllib.request.urlopen", side_effect=fake_urlopen):
                    OpenAICompatibleProvider().generate_character(config, "key", {"rank": 3})
                self.assertEqual(expected, requests[0][key])

        config = {**self.config(), "structured_output": False, "thinking_strategy": "thinking",
                  "thinking_confidence": "verified", "thinking_enabled": False}
        requests = []
        rejected = []

        def reject_once(request, timeout):
            requests.append(json.loads(request.data.decode("utf-8")))
            if len(requests) == 1:
                raise self.http_error(400, {"error": {"message": "Unknown field thinking"}})
            return FakeHttpResponse(proposal_response)

        with mock.patch("urllib.request.urlopen", side_effect=reject_once):
            OpenAICompatibleProvider().generate_character(
                config, "key", {"rank": 3}, on_thinking_capability=rejected.append)
        self.assertIn("thinking", requests[0])
        self.assertNotIn("thinking", requests[1])
        self.assertEqual(1, len(rejected))

    def test_bundle_generation_sends_all_reverse_values(self):
        proposal_response = {"choices": [{"message": {"content": json.dumps(VALID_PROPOSAL)}}]}
        requests = []

        def fake_urlopen(request, timeout):
            requests.append(json.loads(request.data.decode("utf-8")))
            return FakeHttpResponse(proposal_response)

        config = {**self.config(), "structured_output": False, "thinking_strategy": "bundle",
                  "thinking_confidence": "accepted_bundle", "thinking_enabled": True}
        with mock.patch("urllib.request.urlopen", side_effect=fake_urlopen):
            OpenAICompatibleProvider().generate_character(config, "key", {"rank": 3})
        payload = requests[0]
        self.assertTrue(payload["enable_thinking"])
        self.assertEqual({"type": "enabled"}, payload["thinking"])
        self.assertEqual("medium", payload["reasoning_effort"])
        self.assertEqual({"enable_thinking": True}, payload["chat_template_kwargs"])
        self.assertEqual({"enabled": True, "effort": "medium"}, payload["reasoning"])
        self.assertEqual({"thinking_budget": -1}, payload["thinking_config"])

    def test_response_format_and_thinking_rejection_has_bounded_retries(self):
        proposal_response = {"choices": [{"message": {"content": json.dumps(VALID_PROPOSAL)}}]}
        effects = [
            self.http_error(400, {"error": {"message": "Unknown field response_format"}}),
            self.http_error(422, {"error": {"message": "Unsupported parameter enable_thinking"}}),
            FakeHttpResponse(proposal_response),
        ]
        rejected = []
        config = {**self.config(), "thinking_strategy": "enable_thinking",
                  "thinking_confidence": "verified", "thinking_enabled": False}
        with mock.patch("urllib.request.urlopen", side_effect=effects) as call:
            OpenAICompatibleProvider().generate_character(
                config, "key", {"rank": 3}, on_thinking_capability=rejected.append)
        self.assertEqual(3, call.call_count)
        self.assertEqual(1, len(rejected))

    def test_generation_advances_single_strategies_and_caches_success(self):
        proposal = {"choices": [{"message": {"content": json.dumps(VALID_PROPOSAL)}}]}
        requests = []

        def respond(request, timeout):
            body = json.loads(request.data.decode("utf-8"))
            requests.append(body)
            if "thinking_config" in body:
                return FakeHttpResponse(proposal)
            for field in ("enable_thinking", "thinking", "reasoning_effort",
                          "chat_template_kwargs"):
                if field in body:
                    raise self.http_error(
                        400, {"error": {"message": f"Unknown field {field}"}})
            if body.get("reasoning", {}).get("enabled") is not None:
                raise self.http_error(
                    400, {"error": {"message": "Unknown field reasoning.enabled"}})
            if body.get("reasoning", {}).get("effort") is not None:
                raise self.http_error(
                    400, {"error": {"message": "Unknown field reasoning.effort"}})
            return FakeHttpResponse(proposal)

        config = {**self.config(), "structured_output": False, "thinking_strategy": "thinking",
                  "thinking_confidence": "verified", "thinking_enabled": False}
        updates = []
        with mock.patch("urllib.request.urlopen", side_effect=respond) as call:
            OpenAICompatibleProvider().generate_character(
                config, "key", {"rank": 3}, on_thinking_capability=updates.append)
        self.assertEqual(len(THINKING_STRATEGIES), call.call_count)
        self.assertEqual({"thinking_budget": 0}, requests[-1]["thinking_config"])
        self.assertEqual("controlled", updates[-1]["capability"])
        self.assertEqual("thinking_budget", updates[-1]["strategy"])
        self.assertEqual("verified", updates[-1]["confidence"])

    def test_generation_all_strategies_rejected_then_once_without_control(self):
        proposal = {"choices": [{"message": {"content": json.dumps(VALID_PROPOSAL)}}]}
        requests = []
        keys = [next(iter(thinking_parameters(strategy, False)))
                for strategy in THINKING_STRATEGIES]

        def respond(request, timeout):
            body = json.loads(request.data.decode("utf-8"))
            requests.append(body)
            field = next((key for key in keys if key in body), None)
            if field:
                raise self.http_error(422, {"error": {"message": f"Unsupported parameter {field}"}})
            return FakeHttpResponse(proposal)

        config = {**self.config(), "structured_output": False, "thinking_strategy": "bundle",
                  "thinking_confidence": "accepted_bundle", "thinking_enabled": True}
        updates = []
        with mock.patch("urllib.request.urlopen", side_effect=respond) as call:
            OpenAICompatibleProvider().generate_character(
                config, "key", {"rank": 3}, on_thinking_capability=updates.append)
        self.assertEqual(1 + len(THINKING_STRATEGIES) + 1, call.call_count)
        self.assertFalse(any(key in requests[-1] for key in keys))
        self.assertEqual("unsupported", updates[-1]["capability"])

    def test_generation_does_not_remove_unattributed_or_different_field(self):
        for text in ("invalid model", "Unknown field temperature"):
            config = {**self.config(), "thinking_strategy": "enable_thinking",
                      "thinking_confidence": "verified", "thinking_enabled": False}
            with self.subTest(text=text), mock.patch(
                    "urllib.request.urlopen",
                    side_effect=self.http_error(400, {"error": {"message": text}})) as call:
                with self.assertRaises(ProviderError):
                    OpenAICompatibleProvider().generate_character(config, "key", {"rank": 3})
            self.assertEqual(1, call.call_count)


class ApiTestCase(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        root = Path(self.temporary.name)
        static = root / "web"
        static.mkdir()
        (static / "index.html").write_text("<!doctype html><title>Fantasy Simulator</title>", encoding="utf-8")
        self.provider = FakeProvider()
        self.server = create_server("127.0.0.1", 0, str(root / ".data"), str(static), self.provider)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base_url = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.provider.release.set()
        self.server.app_context.wait_for_workers()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(2)
        self.temporary.cleanup()

    def request(self, method, path, body=None, expected=200):
        data = None
        headers = {}
        if body is not None:
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json; charset=utf-8"
        request = urllib.request.Request(self.base_url + path, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=3) as response:
                payload = json.loads(response.read().decode("utf-8"))
                status = response.status
        except urllib.error.HTTPError as error:
            status = error.code
            payload = json.loads(error.read().decode("utf-8"))
            error.close()
        self.assertEqual(expected, status, payload)
        return payload

    def configure_model(self, api_key="test-secret-key"):
        revision = self.request("GET", "/api/settings")["revision"]
        return self.request("PUT", "/api/settings/model", {
            "request_id": "settings-" + str(time.time_ns()),
            "expected_revision": revision,
            "base_url": "https://model.example/v1",
            "model": "test-model",
            "timeout_seconds": 30,
            "structured_output": False,
            "max_concurrency": 1,
            "thinking_enabled": True,
            "api_key": api_key,
        })

    def set_model(self, **changes):
        current = self.request("GET", "/api/settings")
        return self.request("PUT", "/api/settings/model", {
            "request_id": "settings-" + str(time.time_ns()),
            "expected_revision": current["revision"], **changes,
        })

    def create_save(self, name="测试存档"):
        return self.request("POST", "/api/saves", {
            "name": name, "request_id": "save-" + str(time.time_ns())
        }, 201)

    @staticmethod
    def draft(name="艾琳", rank=3):
        return {
            "race_id": "human", "name": name, "gender": "女", "age": 24,
            "appearance": "黑发，旅行装束", "personality": "沉着而好奇", "rank": rank,
            "talent": "魔力感知敏锐", "backstory": "曾在边境生活。",
            "start_location_id": "grand_academy", "additional": "喜欢阅读。",
        }

    def save_draft(self, save, data=None, draft_revision=0):
        wire = data or self.draft()
        return self.request("PUT", f"/api/saves/{save['id']}/character-draft", {
            "request_id": "draft-" + str(time.time_ns()),
            "draft_revision": draft_revision,
            "expected_save_revision": save["revision"],
            "current_step": 13,
            "race_id": wire.get("race_id", ""), "race_branch_id": wire.get("race_branch_id"),
            "name": wire.get("name", ""), "gender": wire.get("gender", ""),
            "age": wire.get("age"), "appearance": wire.get("appearance", ""),
            "personality": wire.get("personality", ""), "rank": wire.get("rank"),
            "talent": wire.get("talent", ""), "background": wire.get("backstory", ""),
            "location_id": wire.get("start_location_id", ""),
            "additional": wire.get("additional", ""),
        })

    def start_generation(self, save_id, draft_revision, save_revision, request_id="generation-1", expected=202, feedback=""):
        return self.request("POST", f"/api/saves/{save_id}/character-generations", {
            "request_id": request_id, "draft_revision": draft_revision,
            "expected_save_revision": save_revision, "feedback": feedback,
        }, expected)

    def wait_job(self, save_id, job_id, statuses=("succeeded", "failed", "stale", "cancelled")):
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            job = self.request("GET", f"/api/saves/{save_id}/character-generations/{job_id}")
            if job["status"] in statuses:
                return job
            time.sleep(0.02)
        self.fail("生成任务未在期限内结束")

    def ready_save(self, name="可导出存档"):
        self.configure_model()
        save = self.create_save(name)
        updated = self.save_draft(save)
        draft = updated
        save = self.request("GET", f"/api/saves/{save['id']}")
        job = self.start_generation(save["id"], draft["draft_revision"], save["revision"])
        self.assertEqual("succeeded", self.wait_job(save["id"], job["id"])["status"])
        candidate = self.request("GET", f"/api/saves/{save['id']}/character-candidate")
        current_save = self.request("GET", f"/api/saves/{save['id']}")
        bootstrap = self.request("POST", f"/api/saves/{save['id']}/character/confirm", {
            "request_id": "confirm-1", "candidate_id": candidate["id"],
            "expected_save_revision": current_save["revision"],
            "expected_draft_revision": draft["draft_revision"],
        })
        return save["id"], bootstrap

    def test_catalog_is_complete_and_factions_are_read_only(self):
        catalog = self.request("GET", "/api/world/catalog")
        self.assertEqual(8, len(catalog["races"]))
        self.assertEqual(11, len(catalog["locations"]))
        self.assertEqual(12, len(catalog["factions"]))
        self.assertEqual(["orc", "half_orc"], [x["id"] for x in catalog["races"][3]["branches"]])
        self.assertEqual(100000, catalog["ranks"][-1]["base_power"])
        self.assertIsNone(catalog["ranks"][-1]["next_exp"])
        self.assertIn("七阶及以上", catalog["ranks"][6]["warning"])
        self.assertEqual(["一阶", "二阶", "三阶", "四阶", "五阶", "六阶",
                          "七阶", "八阶", "九阶", "十阶"],
                         [rank["display_rank"] for rank in catalog["ranks"]])
        self.assertEqual("什么是等阶", catalog["rank_system"]["title"])
        self.assertIn("同阶只表示整体战斗层级", catalog["rank_system"]["description"])
        self.assertIn("十阶", catalog["rank_system"]["description"])
        self.assertIn("游戏性提示", catalog["rank_system"]["description"])
        self.assertGreaterEqual(len(catalog["rank_system"]["principles"]), 4)
        self.assertEqual({"pace": "dynamic", "tone": "balanced", "detail": "standard",
                          "player_address": "second_person"},
                         catalog["narration"]["defaults"])
        self.assertEqual([], catalog["presets"]["appearance"][0]["race_ids"])
        appearance = catalog["presets"]["appearance"]
        self.assertGreaterEqual(len(appearance), 30)
        self.assertEqual({"发色", "发型", "眼眸", "身形体态", "外观特征"},
                         {item["category"] for item in appearance})
        self.assertTrue({"黑发", "银发", "湛蓝眼眸", "琥珀色眼眸", "身形匀称", "体格魁梧"}
                        .issubset({item["label"] for item in appearance}))
        personality = catalog["presets"]["personality"]
        self.assertGreaterEqual(len(personality), 25)
        self.assertEqual({"处世基调", "社交方式", "驱动力", "弱点与棱角"},
                         {item["category"] for item in personality})
        self.assertTrue(all(item["race_ids"] == [] for item in personality))
        talent = catalog["presets"]["talent"]
        self.assertGreaterEqual(len(talent), 20)
        self.assertEqual({"魔力与施法", "身体与战斗", "认知与技艺", "社会与生存"},
                         {item["category"] for item in talent})
        self.assertTrue({"魔力感知敏锐", "施法控制细致", "耐力出众", "武器直觉",
                         "魔导回路理解力", "洞察情绪", "野外生存", "方向感良好"}
                        .issubset({item["label"] for item in talent}))
        races = {race["id"]: race for race in catalog["races"]}
        structured_fields = {"tagline", "description", "lifespan_text", "distribution",
                             "magic_affinity", "combat_style", "technology", "society",
                             "creation_notes", "facts", "ranks", "image_landscape_path",
                             "image_portrait_path"}
        for race_id, race in races.items():
            self.assertTrue(structured_fields.issubset(race), race_id)
            self.assertTrue(all(race[field] for field in structured_fields), race_id)
            self.assertEqual(f"/assets/world/races/{race_id}-landscape.webp",
                             race["image_landscape_path"])
            self.assertEqual(f"/assets/world/races/{race_id}-portrait.webp",
                             race["image_portrait_path"])
            self.assertTrue(all(set(fact) == {"label", "value"} and fact["value"]
                                for fact in race["facts"]))
            self.assertEqual(10, len(race["ranks"]))

        facts = lambda race_id: " ".join(
            fact["value"] for fact in races[race_id]["facts"])
        self.assertIn("30%", facts("human"))
        self.assertIn("几乎100%", facts("featherfolk"))
        self.assertIn("三阶", facts("featherfolk"))
        self.assertIn("60%", facts("sea_folk"))
        self.assertIn("一阶后", facts("sea_folk"))
        self.assertIn("三阶", facts("elf"))
        self.assertFalse(races["elf"]["ranks"][0]["disabled"])
        self.assertIn("理论分类", races["elf"]["ranks"][0]["warning"])
        self.assertFalse(races["elf"]["ranks"][2]["disabled"])
        self.assertIn("100%", facts("dragonkin"))
        self.assertIn("四至五阶", facts("dragonkin"))
        self.assertIn("独立于战斗阶", facts("dwarf"))
        self.assertIn("50%", facts("demonkin"))

        branches = {branch["id"]: branch for branch in races["therian"]["branches"]}
        for branch in branches.values():
            self.assertTrue({"description", "lifespan_text", "magic_affinity", "combat_style",
                             "technology", "society", "creation_notes", "facts", "ranks"}
                            .issubset(branch))
            self.assertNotIn("兽裔的", branch["description"])
            self.assertEqual(10, len(branch["ranks"]))
        self.assertIn("80%", " ".join(x["value"] for x in branches["orc"]["facts"]))
        self.assertIn("40%", " ".join(x["value"] for x in branches["half_orc"]["facts"]))
        self.assertIsNone(branches["orc"]["ranks"][0]["title"])
        self.assertEqual("初阶者", branches["half_orc"]["ranks"][0]["title"])
        self.assertEqual("天穹", races["featherfolk"]["ranks"][-1]["title"])
        self.assertEqual("瀚海", races["sea_folk"]["ranks"][-1]["title"])
        self.assertEqual("始源", races["elf"]["ranks"][-1]["title"])
        self.assertEqual("天龙", races["dragonkin"]["ranks"][-1]["title"])
        self.assertEqual("心界", races["demonkin"]["ranks"][-1]["title"])
        location_fields = {"tagline", "description", "region", "environment", "structure",
                           "highlights", "transport", "access_note", "arrival_point",
                           "safeguards", "image_landscape_path", "image_portrait_path"}
        locations = {location["id"]: location for location in catalog["locations"]}
        for location_id, location in locations.items():
            self.assertTrue(location_fields.issubset(location), location_id)
            self.assertTrue(all(location[field] for field in location_fields), location_id)
            self.assertEqual(f"/assets/world/locations/{location_id}-landscape.webp",
                             location["image_landscape_path"])
            self.assertEqual(f"/assets/world/locations/{location_id}-portrait.webp",
                             location["image_portrait_path"])
        self.assertIn("水下生存魔导器", locations["abyssal_tides"]["access_note"])
        self.assertNotIn("密闭", locations["abyssal_tides"]["arrival_point"])
        self.assertIn("隔热", locations["dragonvale"]["access_note"])
        self.assertIn("许可", locations["elf_forest"]["access_note"])
        self.assertIn("资质试炼", locations["grand_academy"]["access_note"])

        faction_fields = {"tagline", "description", "headquarters", "ideology",
                          "organization", "tasks", "services", "activities", "rewards",
                          "audience", "access_note", "image_landscape_path",
                          "image_portrait_path"}
        factions = {faction["id"]: faction for faction in catalog["factions"]}
        for faction_id, faction in factions.items():
            self.assertTrue(faction_fields.issubset(faction), faction_id)
            self.assertTrue(all(faction[field] for field in faction_fields), faction_id)
            self.assertEqual(f"/assets/world/factions/{faction_id}-landscape.webp",
                             faction["image_landscape_path"])
            self.assertEqual(f"/assets/world/factions/{faction_id}-portrait.webp",
                             faction["image_portrait_path"])
        forbidden = {"selected", "selectable", "choice", "join", "initial_membership"}
        for faction in factions.values():
            self.assertTrue(faction["tasks"])
            self.assertTrue(faction["services"])
            self.assertTrue(faction["activities"])
            self.assertFalse(forbidden.intersection(faction))
        self.assertIn("信仰", factions["sacred_radiance"]["ideology"])
        self.assertIn("十阶体系", factions["adventurers_guild"]["description"])
        self.assertIn("十二云区", factions["skycrown_conclave"]["tagline"])
        self.assertIn("两位十阶", factions["sacred_tree_court"]["tagline"])
        self.assertIn("不设官方任务", " ".join(factions["dragonvale_moot"]["tasks"]))

    def test_static_spa_fallback_and_utf8_json(self):
        with urllib.request.urlopen(self.base_url + "/saves/example/create/1") as response:
            html = response.read().decode("utf-8")
            self.assertIn("Fantasy Simulator", html)
            self.assertIn("text/html", response.headers["Content-Type"])
        save = self.create_save("中文存档")
        self.assertEqual("中文存档", save["name"])

    def test_save_crud_revision_and_isolation(self):
        first = self.create_save("甲")
        second = self.create_save("乙")
        changed = self.request("PATCH", f"/api/saves/{first['id']}", {
            "request_id": "rename-1", "expected_revision": 0, "name": "甲改名",
        })
        self.assertEqual(1, changed["revision"])
        self.assertEqual("乙", self.request("GET", f"/api/saves/{second['id']}")["name"])
        conflict = self.request("PATCH", f"/api/saves/{first['id']}", {
            "request_id": "rename-2", "expected_revision": 0, "name": "错误覆盖",
        }, 409)
        self.assertEqual("REVISION_CONFLICT", conflict["error"]["code"])
        first_draft = self.save_draft(changed, self.draft("甲角色"))
        second_draft = self.save_draft(second, self.draft("乙角色"))
        self.assertEqual("甲角色", first_draft["name"])
        self.assertEqual("乙角色", second_draft["name"])
        summaries = {item["id"]: item for item in self.request("GET", "/api/saves")["items"]}
        self.assertEqual(13, summaries[first["id"]]["current_step"])
        self.request("DELETE", f"/api/saves/{first['id']}", {
            "request_id": "delete-1", "confirm": True,
            "expected_revision": self.request("GET", f"/api/saves/{first['id']}")["revision"],
        })
        self.assertEqual("SAVE_NOT_FOUND", self.request("GET", f"/api/saves/{first['id']}", expected=404)["error"]["code"])

    def test_create_save_request_is_idempotent(self):
        body = {"name": "幂等存档", "request_id": "create-save-once"}
        first = self.request("POST", "/api/saves", body, 201)
        second = self.request("POST", "/api/saves", body, 201)
        self.assertEqual(first["id"], second["id"])
        conflict = self.request("POST", "/api/saves", {
            "name": "不同存档", "request_id": "create-save-once"
        }, 409)
        self.assertEqual("IDEMPOTENCY_CONFLICT", conflict["error"]["code"])
        self.assertEqual(1, len(self.request("GET", "/api/saves")["items"]))

    def test_settings_secret_is_separate_and_connection_test_uses_provider(self):
        initial = self.request("GET", "/api/settings")["model"]
        self.assertEqual(300, initial["timeout_seconds"])
        self.assertEqual(2, initial["max_concurrency"])
        self.assertFalse(initial["structured_output"])
        self.assertEqual("unknown", initial["structured_output_capability"])
        self.assertIsNone(initial["structured_output_probed_at"])
        settings = self.configure_model("super-secret-value")
        serialized = json.dumps(settings, ensure_ascii=False)
        self.assertNotIn("super-secret-value", serialized)
        self.assertNotIn("api_key", settings["model"])
        self.assertTrue(settings["model"]["api_key_configured"])
        self.assertEqual("••••••••", settings["model"]["api_key_mask"])
        original_revision = settings["revision"]
        result = self.request("POST", "/api/settings/model/test", {
            "base_url": "https://unsaved.example/v1", "model": "unsaved-model",
            "timeout_seconds": 17, "structured_output": False, "max_concurrency": 16,
            "thinking_enabled": False, "api_key": "unsaved-secret",
        })
        self.assertTrue(result["ok"])
        self.assertEqual("unknown", result["thinking_capability"])
        self.assertIsNone(result["thinking_strategy"])
        self.assertEqual("unknown", result["thinking_confidence"])
        self.assertEqual(0, self.provider.probe_calls)
        self.assertEqual("https://unsaved.example/v1", self.provider.test_config["base_url"])
        self.assertEqual("unsaved-model", self.provider.test_config["model"])
        self.assertEqual("unsaved-secret", self.provider.test_api_key)
        self.assertEqual(original_revision, self.request("GET", "/api/settings")["revision"])
        maximum = self.request("PUT", "/api/settings/model", {
            "request_id": "settings-max-concurrency", "expected_revision": original_revision,
            "max_concurrency": 16,
        })
        self.assertEqual(16, maximum["model"]["max_concurrency"])
        data_dir = Path(self.temporary.name) / ".data"
        self.assertIn(settings["model"]["api_key_persistence"], {"windows_dpapi", "memory_only"})
        for path in data_dir.rglob("*"):
            if path.is_file():
                self.assertNotIn(b"super-secret-value", path.read_bytes(), path.name)
        if settings["model"]["api_key_persistence"] == "windows_dpapi":
            self.assertTrue((data_dir / "secrets.dat").is_file())
        connection = sqlite3.connect(data_dir / "fantasy_simulator.sqlite3")
        try:
            self.assertEqual("wal", connection.execute("PRAGMA journal_mode").fetchone()[0].lower())
        finally:
            connection.close()

    def test_response_format_probe_cache_put_guard_and_endpoint_identity(self):
        probe = {
            "base_url": "https://response-format.example/v1", "model": "model-a",
            "timeout_seconds": 10, "structured_output": True,
            "max_concurrency": 1, "thinking_enabled": True,
            "probe_structured_output": True,
        }
        first = self.request("POST", "/api/settings/model/test", probe)
        self.assertEqual("supported", first["structured_output_capability"])
        self.assertEqual("json_object", first["structured_output_strategy"])
        self.assertIsNotNone(first["structured_output_probed_at"])
        self.assertIn("structured_output_probe_token", first)
        self.assertEqual(1, self.provider.response_format_probe_calls)
        self.assertEqual(0, self.provider.test_calls)
        self.assertEqual(0, self.provider.probe_calls)
        second = self.request("POST", "/api/settings/model/test", probe)
        self.assertEqual("supported", second["structured_output_capability"])
        self.assertEqual(2, self.provider.response_format_probe_calls)
        self.assertEqual(0, self.provider.test_calls)
        self.assertEqual(0, self.provider.probe_calls)
        forced = self.request("POST", "/api/settings/model/test", {
            **probe, "structured_output": False, "probe_structured_output": False,
            "force_response_format_probe": True,
        })
        self.assertEqual("supported", forced["structured_output_capability"])
        self.assertEqual(3, self.provider.response_format_probe_calls)
        self.assertEqual(0, self.provider.test_calls)
        self.assertEqual(0, self.provider.probe_calls)

        settings = self.request("GET", "/api/settings")
        unknown = self.request("PUT", "/api/settings/model", {
            "request_id": "unknown-response-format", "expected_revision": settings["revision"],
            "base_url": "https://response-format.example/v1", "model": "model-b",
            "structured_output": True,
        }, 400)
        self.assertIn("structured_output", unknown["error"]["fields"])
        saved = self.request("PUT", "/api/settings/model", {
            "request_id": "save-response-format", "expected_revision": settings["revision"],
            "base_url": probe["base_url"], "model": probe["model"],
            "structured_output": True,
            "structured_output_probe_token": first["structured_output_probe_token"],
        })
        self.assertTrue(saved["model"]["structured_output"])
        self.assertEqual("supported", saved["model"]["structured_output_capability"])
        changed = self.server.app_context.database.get_response_format_capability({
            "base_url": probe["base_url"] + "/other", "model": probe["model"]})
        self.assertEqual("unknown", changed["capability"])

    def test_response_format_probe_proof_binds_api_key_and_stays_in_memory(self):
        config = {
            "base_url": "https://proof.example/v1", "model": "proof-model",
            "timeout_seconds": 10, "structured_output": False,
            "max_concurrency": 1, "thinking_enabled": True,
        }
        probe = self.request("POST", "/api/settings/model/test", {
            **config, "api_key": "key-a", "probe_structured_output": True,
        })
        token = probe["structured_output_probe_token"]
        self.assertTrue(token)
        self.assertNotIn("structured_output_probe_token",
                         json.dumps(self.request("GET", "/api/settings")))

        before = self.request("GET", "/api/settings")
        saved = self.request("PUT", "/api/settings/model", {
            **config, "structured_output": True, "api_key": "key-a",
            "structured_output_probe_token": token,
            "request_id": "proof-key-a", "expected_revision": before["revision"],
        })
        self.assertTrue(saved["model"]["structured_output"])
        self.assertEqual("key-a", self.server.app_context.secrets.get_api_key())

        for request_id, changes in (
                ("proof-key-b", {"api_key": "key-b"}),
                ("proof-endpoint", {"api_key": "key-a", "base_url": "https://other.example/v1"}),
                ("proof-model", {"api_key": "key-a", "model": "other-model"})):
            unchanged = self.request("GET", "/api/settings")
            rejected = self.request("PUT", "/api/settings/model", {
                **config, **changes, "structured_output": True,
                "structured_output_probe_token": token,
                "request_id": request_id, "expected_revision": unchanged["revision"],
            }, 400)
            self.assertIn("structured_output", rejected["error"]["fields"])
            after = self.request("GET", "/api/settings")
            self.assertEqual(unchanged, after)
            self.assertEqual("key-a", self.server.app_context.secrets.get_api_key())

        continued = self.request("PUT", "/api/settings/model", {
            "structured_output": True, "max_concurrency": 2,
            "request_id": "proof-existing-key", "expected_revision": saved["revision"],
        })
        self.assertTrue(continued["model"]["structured_output"])

        data_dir = Path(self.temporary.name) / ".data"
        connection = sqlite3.connect(data_dir / "fantasy_simulator.sqlite3")
        try:
            self.assertNotIn(token, "\n".join(connection.iterdump()))
        finally:
            connection.close()
        fresh = AppContext(str(data_dir), self.server.app_context.static_dir, self.provider)
        self.assertFalse(fresh.validate_response_format_probe(token, config, "key-a"))

    def test_ordinary_connection_test_only_displays_cached_response_format_capability(self):
        db = self.server.app_context.database
        config = {"base_url": "https://ordinary.example/v1", "model": "model-a"}
        db.set_model_capability(config, {
            "capability": "controlled", "strategy": "thinking", "confidence": "verified",
        })
        db.set_response_format_capability(config, {
            "capability": "supported", "strategy": "json_object",
        })

        result = self.request("POST", "/api/settings/model/test", {
            **config, "structured_output": False,
        })

        self.assertEqual("supported", result["structured_output_capability"])
        self.assertEqual(1, self.provider.test_calls)
        self.assertEqual(0, self.provider.probe_calls)
        self.assertEqual(0, self.provider.response_format_probe_calls)

    def test_unsupported_response_format_probe_does_not_change_saved_settings(self):
        self.provider.response_format_capability = "unsupported"
        before = self.request("GET", "/api/settings")
        request = {
            "base_url": "https://unsupported.example/v1", "model": "model-a",
            "structured_output": True, "probe_structured_output": True,
        }
        result = self.request("POST", "/api/settings/model/test", request)
        self.assertEqual("unsupported", result["structured_output_capability"])
        self.assertIn("不支持", result["structured_output_message"])
        self.assertNotIn("structured_output_probe_token", result)
        repeated = self.request("POST", "/api/settings/model/test", request)
        self.assertEqual("unsupported", repeated["structured_output_capability"])
        self.assertEqual(2, self.provider.response_format_probe_calls)
        self.assertEqual(0, self.provider.test_calls)
        self.assertEqual(0, self.provider.probe_calls)
        after = self.request("GET", "/api/settings")
        self.assertEqual(before["revision"], after["revision"])
        self.assertFalse(after["model"]["structured_output"])
        rejected = self.request("PUT", "/api/settings/model", {
            "request_id": "unsupported-response-format",
            "expected_revision": after["revision"],
            "base_url": "https://unsupported.example/v1", "model": "model-a",
            "structured_output": True,
        }, 400)
        self.assertIn("structured_output", rejected["error"]["fields"])
        allowed = self.request("PUT", "/api/settings/model", {
            "request_id": "disable-response-format", "expected_revision": after["revision"],
            "base_url": "https://unsupported.example/v1", "model": "model-a",
            "structured_output": False,
        })
        self.assertFalse(allowed["model"]["structured_output"])

    def test_effective_structured_output_requires_supported_capability(self):
        db = self.server.app_context.database
        stored = {
            "base_url": "https://legacy.example/v1", "model": "legacy-model",
            "timeout_seconds": 30, "structured_output": True, "max_concurrency": 1,
        }
        with db.connect() as connection:
            connection.execute("UPDATE settings SET model_json=? WHERE id=1",
                               (json.dumps(stored),))

        unknown_settings = self.request("GET", "/api/settings")["model"]
        unknown_config = db.get_model_config()
        self.assertFalse(unknown_settings["structured_output"])
        self.assertFalse(unknown_config["structured_output"])
        requests = []

        def fake_urlopen(request, timeout):
            requests.append(json.loads(request.data.decode("utf-8")))
            return FakeHttpResponse({"choices": [{"message": {
                "content": json.dumps(VALID_PROPOSAL, ensure_ascii=False)}}]})

        with mock.patch("urllib.request.urlopen", side_effect=fake_urlopen):
            OpenAICompatibleProvider().generate_character(unknown_config, "key", {"rank": 3})
        self.assertNotIn("response_format", requests[0])

        db.set_response_format_capability(stored, {
            "capability": "unsupported", "strategy": "json_object",
        })
        self.assertFalse(self.request("GET", "/api/settings")["model"]["structured_output"])
        self.assertFalse(db.get_model_config()["structured_output"])

        db.set_response_format_capability(stored, {
            "capability": "supported", "strategy": "json_object",
        })
        supported_settings = self.request("GET", "/api/settings")["model"]
        supported_config = db.get_model_config()
        self.assertTrue(supported_settings["structured_output"])
        self.assertTrue(supported_config["structured_output"])
        requests.clear()
        with mock.patch("urllib.request.urlopen", side_effect=fake_urlopen):
            OpenAICompatibleProvider().generate_character(supported_config, "key", {"rank": 3})
        self.assertIn("response_format", requests[0])

    def test_response_format_migration_only_changes_blank_legacy_default(self):
        db = self.server.app_context.database

        def rerun_v4(model):
            with db.connect() as connection:
                connection.execute("UPDATE settings SET model_json=? WHERE id=1",
                                   (json.dumps(model),))
                connection.execute("DROP TABLE response_format_capabilities")
                connection.execute("DELETE FROM schema_migrations WHERE version=4")
            db._initialize()
            with db.connect() as connection:
                return json.loads(connection.execute(
                    "SELECT model_json FROM settings WHERE id=1").fetchone()[0])

        configured = rerun_v4({
            "base_url": "https://legacy.example/v1", "model": "legacy-model",
            "timeout_seconds": 60, "structured_output": True,
        })
        self.assertTrue(configured["structured_output"])
        blank = rerun_v4({
            "base_url": "", "model": "", "timeout_seconds": 300,
            "structured_output": True,
        })
        self.assertFalse(blank["structured_output"])

    def test_concurrency_migration_only_changes_unconfigured_legacy_default(self):
        db = self.server.app_context.database

        def rerun_v5(model, revision):
            with db.connect() as connection:
                connection.execute("UPDATE settings SET model_json=?,revision=? WHERE id=1",
                                   (json.dumps(model), revision))
                connection.execute("DELETE FROM schema_migrations WHERE version=5")
            db._initialize()
            with db.connect() as connection:
                return json.loads(connection.execute(
                    "SELECT model_json FROM settings WHERE id=1").fetchone()[0])

        blank = rerun_v5({"base_url": "", "model": "", "timeout_seconds": 300,
                          "max_concurrency": 1}, 0)
        self.assertEqual(2, blank["max_concurrency"])
        configured = rerun_v5({"base_url": "https://legacy.example/v1", "model": "legacy",
                               "max_concurrency": 1}, 0)
        self.assertEqual(1, configured["max_concurrency"])
        explicit = rerun_v5({"base_url": "", "model": "", "timeout_seconds": 300,
                             "max_concurrency": 1}, 7)
        self.assertEqual(1, explicit["max_concurrency"])
        missing = rerun_v5({"base_url": "https://legacy.example/v1", "model": "legacy"}, 0)
        self.assertNotIn("max_concurrency", missing)
        self.assertEqual(2, db.get_settings()["model"]["max_concurrency"])

    def test_memory_cleanup_migration_removes_legacy_inactive_rows(self):
        db = self.server.app_context.database
        with db.connect() as connection:
            connection.execute("PRAGMA foreign_keys=OFF")
            for status in ("resolved", "superseded"):
                connection.execute(
                    "INSERT INTO memories VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    ("legacy-" + status, "missing-save", status, "clue", "旧记忆", 1,
                     "[]", "[]", "[]", "[]", "[]", None,
                     "missing-turn", "missing-version", "2026-09-29T00:00:00+00:00"))
            connection.execute("DELETE FROM schema_migrations WHERE version=8")
        db._initialize()
        with db.connect() as connection:
            self.assertEqual(0, connection.execute(
                "SELECT COUNT(*) FROM memories WHERE status<>'active'").fetchone()[0])

    def test_thinking_capability_cache_hits_and_config_changes_invalidate(self):
        first = self.request("POST", "/api/settings/model/test", {
            "base_url": "https://cache.example/v1", "model": "model-a",
            "timeout_seconds": 10, "structured_output": True,
            "max_concurrency": 1, "thinking_enabled": True,
        })
        self.assertEqual("unknown", first["thinking_confidence"])
        second = self.request("POST", "/api/settings/model/test", {
            "base_url": "https://cache.example/v1", "model": "model-a",
            "timeout_seconds": 10, "structured_output": True,
            "max_concurrency": 1, "thinking_enabled": True,
        })
        self.assertEqual("unknown", second["thinking_confidence"])
        self.assertEqual(2, self.provider.test_calls)
        self.assertEqual(0, self.provider.probe_calls)
        forced = self.request("POST", "/api/settings/model/test", {
            "base_url": "https://cache.example/v1", "model": "model-a",
            "timeout_seconds": 10, "structured_output": True,
            "max_concurrency": 1, "thinking_enabled": True,
            "force_thinking_probe": True,
        })
        self.assertEqual("verified", forced["thinking_confidence"])
        self.assertEqual(3, self.provider.test_calls)
        self.assertEqual(1, self.provider.probe_calls)
        capability = self.server.app_context.database.get_model_capability({
            "base_url": "https://cache.example/v1", "model": "model-a"})
        self.assertEqual("controlled", capability["capability"])
        changed = self.server.app_context.database.get_model_capability({
            "base_url": "https://cache.example/v1", "model": "model-b"})
        self.assertEqual("unknown", changed["capability"])

    def test_unsaved_unsupported_probe_does_not_change_saved_preference(self):
        db = self.server.app_context.database
        saved = {"base_url": "https://saved.example/v1", "model": "saved-model"}
        db.set_model_capability(saved, {
            "capability": "controlled", "strategy": "thinking", "confidence": "verified"})
        current = self.request("GET", "/api/settings")
        configured = self.request("PUT", "/api/settings/model", {
            "request_id": "save-controlled", "expected_revision": current["revision"],
            **saved, "thinking_enabled": False,
        })
        self.assertFalse(configured["model"]["thinking_enabled"])
        db.set_model_capability({"base_url": "https://draft.example/v1", "model": "draft-model"}, {
            "capability": "unsupported", "strategy": None, "confidence": "unsupported"})
        self.assertFalse(self.request("GET", "/api/settings")["model"]["thinking_enabled"])

    def test_capability_cache_write_preserves_revision_and_saved_thinking_preference(self):
        db = self.server.app_context.database
        config = {"base_url": "https://revision.example/v1", "model": "revision-model"}
        db.set_model_capability(config, {
            "capability": "controlled", "strategy": "thinking", "confidence": "verified"})
        before = self.request("GET", "/api/settings")
        saved = self.request("PUT", "/api/settings/model", {
            "request_id": "cache-revision", "expected_revision": before["revision"],
            **config, "thinking_enabled": False,
        })
        revision = saved["revision"]
        db.set_model_capability(config, {
            "capability": "unsupported", "strategy": None, "confidence": "unsupported"})
        after = self.request("GET", "/api/settings")
        self.assertEqual(revision, after["revision"])
        self.assertTrue(after["model"]["thinking_enabled"])
        with db.connect() as connection:
            stored = connection.execute("SELECT thinking_enabled FROM settings WHERE id=1").fetchone()[0]
        self.assertEqual(0, stored)

    def test_generation_capability_callback_updates_cache(self):
        settings = self.configure_model()
        config = {"base_url": settings["model"]["base_url"],
                  "model": settings["model"]["model"]}
        self.server.app_context.database.set_model_capability(config, {
            "capability": "controlled", "strategy": "bundle",
            "confidence": "accepted_bundle"})
        self.provider.capability_update = {
            "capability": "controlled", "strategy": "reasoning_effort",
            "confidence": "verified", "last_failure": "bundle rejected",
        }
        save = self.create_save()
        draft = self.save_draft(save)
        current = self.request("GET", f"/api/saves/{save['id']}")
        job = self.start_generation(save["id"], draft["draft_revision"], current["revision"])
        self.assertEqual("succeeded", self.wait_job(save["id"], job["id"])["status"])
        capability = self.server.app_context.database.get_model_capability(config)
        self.assertEqual("controlled", capability["capability"])
        self.assertEqual("reasoning_effort", capability["strategy"])
        self.assertEqual("verified", capability["confidence"])

    def test_dpapi_secret_store_round_trip_or_memory_only(self):
        path = Path(self.temporary.name) / ".data" / "standalone-secrets.dat"
        store = SecretStore(path)
        self.assertEqual("", store.get_api_key())
        persisted = store.set_api_key("dpapi-plain-secret")
        self.assertEqual("dpapi-plain-secret", store.get_api_key())
        if persisted:
            self.assertNotIn(b"dpapi-plain-secret", path.read_bytes())
            self.assertEqual("dpapi-plain-secret", SecretStore(path).get_api_key())
        else:
            self.assertEqual("memory_only", store.persistence)
            self.assertFalse(path.exists())

    def test_legacy_plaintext_secret_is_removed_during_migration(self):
        data_dir = Path(self.temporary.name) / ".legacy"
        data_dir.mkdir()
        legacy = data_dir / "secrets.json"
        legacy.write_text(json.dumps({"model_api_key": "legacy-plain-secret"}), encoding="utf-8")
        store = SecretStore(data_dir / "secrets.dat")
        self.assertEqual("legacy-plain-secret", store.get_api_key())
        for path in data_dir.iterdir():
            self.assertNotIn(b"legacy-plain-secret", path.read_bytes())

    def test_health_identifies_application_and_api(self):
        health = self.request("GET", "/api/health")
        self.assertEqual({"status": "ok", "app_id": "fantasy-simulator", "api_version": "1"}, health)

    def test_thinking_cannot_be_disabled_before_probe(self):
        settings = self.request("GET", "/api/settings")
        rejected = self.request("PUT", "/api/settings/model", {
            "request_id": "thinking-disabled", "expected_revision": settings["revision"],
            "thinking_enabled": False,
        }, 400)
        self.assertIn("thinking_enabled", rejected["error"]["fields"])
        self.assertTrue(self.request("GET", "/api/settings")["model"]["thinking_enabled"])

    def test_narration_defaults_are_copied_into_new_saves(self):
        settings = self.request("GET", "/api/settings")
        updated = self.request("PUT", "/api/settings/narration", {
            "request_id": "narration-1", "expected_revision": settings["revision"],
            "pace": "slow", "tendency": "casual", "detail": "detailed",
            "player_address": "given_name",
        })
        self.assertEqual("slow", updated["narration"]["pace"])
        self.assertEqual("given_name", updated["narration"]["player_address"])
        save = self.create_save()
        self.assertEqual({"pace": "slow", "tone": "casual", "detail": "detailed",
                          "player_address": "given_name"},
                         save["narration"])
        per_save = self.request("PUT", f"/api/saves/{save['id']}/preferences", {
            "request_id": "save-narration-1", "expected_revision": save["revision"],
            "pace": "fast", "tone": "combat", "detail": "concise",
            "player_address": "full_name",
        })
        self.assertEqual("fast", per_save["narration"]["pace"])
        self.assertEqual("full_name", per_save["narration"]["player_address"])
        self.assertEqual("slow", self.request("GET", "/api/settings")["narration"]["pace"])

    def test_global_narration_settings_apply_to_existing_saves(self):
        save = self.create_save("已有存档")
        settings = self.request("GET", "/api/settings")
        updated = self.request("PUT", "/api/settings/narration", {
            "request_id": "global-address-existing", "expected_revision": settings["revision"],
            "pace": "dynamic", "tendency": "balanced", "detail": "standard",
            "player_address": "given_name",
        })
        existing = self.request("GET", f"/api/saves/{save['id']}")
        self.assertEqual("given_name", existing["narration"]["player_address"])
        self.assertEqual(save["revision"] + 1, existing["revision"])
        self.assertEqual("given_name", updated["narration"]["player_address"])

    def test_global_narration_settings_are_blocked_during_character_generation(self):
        self.configure_model()
        self.provider.block = True
        save = self.create_save("生成中的存档")
        draft = self.save_draft(save)
        save = self.request("GET", f"/api/saves/{save['id']}")
        job = self.start_generation(save["id"], draft["draft_revision"], save["revision"],
                                    "global-address-block")
        self.assertTrue(self.provider.started.wait(1))
        settings = self.request("GET", "/api/settings")
        blocked = self.request("PUT", "/api/settings/narration", {
            "request_id": "global-address-while-generating",
            "expected_revision": settings["revision"], "pace": "dynamic",
            "tendency": "balanced", "detail": "standard", "player_address": "given_name",
        }, 409)
        self.assertEqual("GENERATION_ACTIVE", blocked["error"]["code"])
        self.provider.release.set()
        self.assertEqual("succeeded", self.wait_job(save["id"], job["id"])["status"])

    def test_player_address_migration_backfills_existing_json(self):
        db = self.server.app_context.database
        save = self.create_save("旧称呼存档")
        with db.connect() as connection:
            connection.execute("UPDATE settings SET narration_json=? WHERE id=1", (
                json.dumps({"pace": "dynamic", "tone": "balanced", "detail": "standard"}),))
            connection.execute("UPDATE saves SET preferences_json=? WHERE id=?", (
                json.dumps({"pace": "slow", "tone": "casual", "detail": "detailed"}), save["id"]))
            connection.execute("DELETE FROM schema_migrations WHERE version=6")
        db._initialize()
        self.assertEqual("second_person", self.request("GET", "/api/settings")["narration"]["player_address"])
        self.assertEqual("second_person", self.request("GET", f"/api/saves/{save['id']}")["narration"]["player_address"])

    def test_model_not_configured_is_explicit(self):
        save = self.create_save()
        updated = self.save_draft(save)
        current_save = self.request("GET", f"/api/saves/{save['id']}")
        error = self.start_generation(save["id"], updated["draft_revision"],
                                      current_save["revision"], expected=409)
        self.assertEqual("MODEL_NOT_CONFIGURED", error["error"]["code"])

    def test_draft_revision_conflict_preserves_server_data(self):
        save = self.create_save()
        updated = self.save_draft(save, self.draft("服务器版本"))
        current_save = self.request("GET", f"/api/saves/{save['id']}")
        conflict = self.request("PUT", f"/api/saves/{save['id']}/character-draft", {
            "request_id": "stale-draft", "draft_revision": 0,
            "expected_save_revision": current_save["revision"], "current_step": 13,
            "race_id": "human", "name": "过期客户端版本", "gender": "女", "age": 24,
            "appearance": "黑发，旅行装束", "personality": "沉着而好奇", "rank": 3,
            "talent": "魔力感知敏锐", "background": "曾在边境生活。",
            "location_id": "grand_academy", "additional": "喜欢阅读。",
        }, 409)
        self.assertEqual("REVISION_CONFLICT", conflict["error"]["code"])
        current = self.request("GET", f"/api/saves/{save['id']}/character-draft")
        self.assertEqual("服务器版本", current["name"])

    def test_generation_idempotency_and_candidate_rules(self):
        self.configure_model()
        save = self.create_save()
        draft = self.save_draft(save)
        save = self.request("GET", f"/api/saves/{save['id']}")
        job = self.start_generation(save["id"], draft["draft_revision"], save["revision"], "same-request")
        repeated = self.start_generation(save["id"], draft["draft_revision"], save["revision"], "same-request", expected=200)
        self.assertEqual(job["id"], repeated["id"])
        self.assertEqual("succeeded", self.wait_job(save["id"], job["id"])["status"])
        self.assertEqual(1, self.provider.calls)
        candidate = self.request("GET", f"/api/saves/{save['id']}/character-candidate")
        self.assertEqual(320, candidate["power"]["base"])
        self.assertEqual(candidate["power"]["base"], candidate["power"]["effective"])
        self.assertEqual(0, candidate["exp"])
        self.assertEqual(240, candidate["resources"]["hp"]["current"])
        self.assertEqual(450, candidate["starting_currency"]["copper"])
        conflict = self.start_generation(save["id"], draft["draft_revision"], save["revision"],
                                         "same-request", expected=409, feedback="不同意见")
        self.assertEqual("IDEMPOTENCY_CONFLICT", conflict["error"]["code"])

    def test_only_one_active_generation_per_save(self):
        self.configure_model()
        self.provider.block = True
        save = self.create_save()
        updated = self.save_draft(save)
        save = self.request("GET", f"/api/saves/{save['id']}")
        job = self.start_generation(save["id"], updated["draft_revision"],
                                    save["revision"], "active-1")
        self.assertTrue(self.provider.started.wait(1))
        error = self.start_generation(save["id"], updated["draft_revision"],
                                      save["revision"], "active-2", expected=409)
        self.assertEqual("GENERATION_ACTIVE", error["error"]["code"])
        self.provider.release.set()
        self.assertEqual("succeeded", self.wait_job(save["id"], job["id"])["status"])

    def test_generation_is_isolated_between_saves(self):
        self.configure_model()
        first = self.create_save("生成甲")
        second = self.create_save("生成乙")
        first_state = self.save_draft(first, self.draft("甲候选"))
        second_state = self.save_draft(second, self.draft("乙候选"))
        first = self.request("GET", f"/api/saves/{first['id']}")
        second = self.request("GET", f"/api/saves/{second['id']}")
        first_job = self.start_generation(first["id"], first_state["draft_revision"],
                                          first["revision"], "first-generation")
        second_job = self.start_generation(second["id"], second_state["draft_revision"],
                                           second["revision"], "second-generation")
        self.assertEqual("succeeded", self.wait_job(first["id"], first_job["id"])["status"])
        self.assertEqual("succeeded", self.wait_job(second["id"], second_job["id"])["status"])
        first_candidate = self.request("GET", f"/api/saves/{first['id']}/character-candidate")
        second_candidate = self.request("GET", f"/api/saves/{second['id']}/character-candidate")
        self.assertEqual("甲候选", first_candidate["identity"]["name"])
        self.assertEqual("乙候选", second_candidate["identity"]["name"])
        self.assertNotEqual(first_candidate["id"], second_candidate["id"])

    def _start_two_generation_jobs(self):
        first = self.create_save("生成甲")
        second = self.create_save("生成乙")
        first_draft = self.save_draft(first, self.draft("甲候选"))
        second_draft = self.save_draft(second, self.draft("乙候选"))
        first = self.request("GET", f"/api/saves/{first['id']}")
        second = self.request("GET", f"/api/saves/{second['id']}")
        first_job = self.start_generation(first["id"], first_draft["draft_revision"],
                                          first["revision"], "concurrent-first")
        started = getattr(self.server.app_context.provider, "first_started", None)
        if started is not None:
            self.assertTrue(started.wait(1))
        second_job = self.start_generation(second["id"], second_draft["draft_revision"],
                                           second["revision"], "concurrent-second")
        return first, first_job, second, second_job

    def test_concurrent_rejection_downgrades_waits_and_retries_once(self):
        provider = ConcurrentRejectingProvider()
        self.server.app_context.provider = provider
        self.configure_model()
        configured = self.set_model(max_concurrency=2)
        first, first_job, second, second_job = self._start_two_generation_jobs()
        self.assertTrue(provider.first_started.wait(1))
        self.assertTrue(provider.second_rejected.wait(1))
        time.sleep(0.05)
        self.assertEqual(1, provider.active)
        self.assertEqual(1, provider.calls_by_name["乙候选"])
        provider.release_first.set()
        first_result = self.wait_job(first["id"], first_job["id"])
        second_result = self.wait_job(second["id"], second_job["id"])
        self.assertEqual("succeeded", first_result["status"], first_result)
        self.assertEqual("succeeded", second_result["status"], second_result)
        self.assertGreaterEqual(provider.max_active, 2)
        self.assertEqual(2, provider.calls_by_name["乙候选"])
        settings = self.request("GET", "/api/settings")
        self.assertEqual(1, settings["model"]["max_concurrency"])
        self.assertEqual(configured["revision"] + 1, settings["revision"])

    def test_ordinary_rate_limit_does_not_downgrade_or_retry(self):
        provider = ConcurrentRejectingProvider("quota exceeded")
        self.server.app_context.provider = provider
        self.configure_model()
        self.set_model(max_concurrency=2)
        first, first_job, second, second_job = self._start_two_generation_jobs()
        self.assertTrue(provider.first_started.wait(1))
        self.assertTrue(provider.second_rejected.wait(1))
        provider.release_first.set()
        self.assertEqual("succeeded", self.wait_job(first["id"], first_job["id"])["status"])
        failed = self.wait_job(second["id"], second_job["id"])
        self.assertEqual("failed", failed["status"])
        self.assertEqual(1, provider.calls_by_name["乙候选"])
        self.assertEqual(2, self.request("GET", "/api/settings")["model"]["max_concurrency"])

    def test_limit_one_never_uses_concurrency_fallback(self):
        calls = []
        config = {"base_url": "https://model.example/v1", "model": "model-a",
                  "max_concurrency": 1, "_settings_revision": 0}
        context = self.server.app_context
        entered = threading.Event()
        release = threading.Event()
        context._effective_provider_limit[(config["base_url"], config["model"])] = {
            "configured": 2, "effective": 2, "revision": 0,
        }

        def active_call():
            entered.set()
            release.wait(2)

        active = threading.Thread(target=lambda: context._call_provider_with_concurrency_fallback(
            {**config, "max_concurrency": 2}, active_call))
        active.start()
        self.assertTrue(entered.wait(1))

        def reject():
            calls.append(1)
            raise ProviderError("MODEL_RATE_LIMITED", "限流", True, 429,
                                "too many concurrent requests")

        try:
            with self.assertRaises(ProviderError):
                context._call_provider_with_concurrency_fallback(config, reject)
        finally:
            release.set()
        active.join(2)
        self.assertEqual(1, len(calls))
        self.assertEqual(2, self.request("GET", "/api/settings")["model"]["max_concurrency"])

    def test_non_overlapped_concurrency_word_does_not_downgrade(self):
        calls = []
        config = {"base_url": "https://model.example/v1", "model": "model-a",
                  "max_concurrency": 2, "_settings_revision": 0}

        def reject():
            calls.append(1)
            raise ProviderError("MODEL_RATE_LIMITED", "限流", True, 429,
                                "too many concurrent requests")

        with self.assertRaises(ProviderError):
            self.server.app_context._call_provider_with_concurrency_fallback(config, reject)
        self.assertEqual(1, len(calls))
        self.assertEqual(2, self.request("GET", "/api/settings")["model"]["max_concurrency"])

    def test_failed_serial_retry_reports_original_concurrency_error(self):
        context = self.server.app_context
        config = {"base_url": "https://model.example/v1", "model": "model-a",
                  "max_concurrency": 2, "_settings_revision": 0}
        active_entered = threading.Event()
        release_active = threading.Event()

        def active_call():
            active_entered.set()
            release_active.wait(2)

        active = threading.Thread(target=lambda: context._call_provider_with_concurrency_fallback(
            config, active_call))
        active.start()
        self.assertTrue(active_entered.wait(1))
        calls = []
        original = ProviderError("MODEL_RATE_LIMITED", "首次并发拒绝", True, 429,
                                 "too many concurrent requests")

        def reject_twice():
            calls.append(1)
            if len(calls) == 1:
                raise original
            raise ProviderError("MODEL_TIMEOUT", "串行重试超时", True)

        timer = threading.Timer(0.05, release_active.set)
        timer.start()
        try:
            with self.assertRaises(ProviderError) as raised:
                context._call_provider_with_concurrency_fallback(config, reject_twice)
        finally:
            timer.cancel()
            release_active.set()
        active.join(2)
        self.assertIs(original, raised.exception)
        self.assertEqual(2, len(calls))
        self.assertEqual(0, context._active_provider_calls)
        self.assertEqual(0, context._provider_fallback_retries)

    def test_serial_concurrency_fallback_preserves_output_format_error(self):
        context = self.server.app_context
        config = {"base_url": "https://model.example/v1", "model": "model-a",
                  "max_concurrency": 2, "_settings_revision": 0}
        active_entered = threading.Event()
        release_active = threading.Event()

        def active_call():
            active_entered.set()
            release_active.wait(2)

        active = threading.Thread(target=lambda: context._call_provider_with_concurrency_fallback(
            config, active_call))
        active.start()
        self.assertTrue(active_entered.wait(1))
        calls = []

        def reject_then_bad_output():
            calls.append(1)
            if len(calls) == 1:
                raise ProviderError("MODEL_RATE_LIMITED", "首次并发拒绝", True, 429,
                                    "too many concurrent requests")
            raise ProviderError("MODEL_OUTPUT_FORMAT", "JSON第2行无效")

        timer = threading.Timer(0.05, release_active.set)
        timer.start()
        try:
            with self.assertRaises(ProviderError) as raised:
                context._call_provider_with_concurrency_fallback(config, reject_then_bad_output)
        finally:
            timer.cancel()
            release_active.set()
        active.join(2)
        self.assertEqual("MODEL_OUTPUT_FORMAT", raised.exception.code)
        self.assertIn("第2行", raised.exception.message)

    def test_fallback_retry_runs_before_waiters_admitted_under_limit_one(self):
        context = self.server.app_context
        provider = DrainingProvider()
        context.provider = provider
        config = {"base_url": "https://model.example/v1", "model": "model-a",
                  "max_concurrency": 2, "_settings_revision": 0}
        results = []

        def run(name):
            results.append(context._call_provider_with_concurrency_fallback(
                config, lambda: provider.generate_character(config, "key", {"name": name})))

        first = threading.Thread(target=run, args=("first",))
        second = threading.Thread(target=run, args=("second",))
        third = threading.Thread(target=run, args=("third",))
        first.start()
        self.assertTrue(provider.first_started.wait(1))
        second.start()
        self.assertTrue(provider.second_started.wait(1))
        third.start()
        time.sleep(0.05)
        self.assertFalse(provider.third_started.is_set())
        provider.release_first.set()
        second.join(2)
        self.assertEqual(1, provider.retry_active)
        self.assertEqual(["first", "second", "second"], provider.calls[:3])
        self.assertTrue(provider.third_started.wait(1))
        provider.release_third.set()
        first.join(2)
        third.join(2)
        self.assertEqual(3, len(results))
        self.assertEqual(0, context._active_provider_calls)
        self.assertEqual(0, context._provider_fallback_retries)

    def test_late_concurrency_rejection_preserves_newer_same_provider_settings(self):
        context = self.server.app_context
        db = context.database
        provider = ConcurrentRejectingProvider()
        context.provider = provider
        self.configure_model()
        old = self.set_model(max_concurrency=3)
        provider.allow_second_rejection = threading.Event()
        try:
            first, first_job, second, second_job = self._start_two_generation_jobs()
            self.assertTrue(provider.second_rejected.wait(1))
            newer = self.set_model(max_concurrency=4)
            provider.allow_second_rejection.set()
            time.sleep(0.05)
            self.assertEqual(1, provider.active)
            self.assertEqual(1, provider.calls_by_name["乙候选"])
            provider.release_first.set()
            first_result = self.wait_job(first["id"], first_job["id"])
            second_result = self.wait_job(second["id"], second_job["id"])
        finally:
            provider.allow_second_rejection.set()
            provider.release_first.set()

        self.assertEqual("succeeded", first_result["status"], first_result)
        self.assertEqual("succeeded", second_result["status"], second_result)
        self.assertEqual(2, provider.calls_by_name["乙候选"])
        settings = self.request("GET", "/api/settings")
        self.assertEqual(4, settings["model"]["max_concurrency"])
        self.assertEqual(newer["revision"], settings["revision"])
        identity = (old["model"].get("protocol", "openai"),
                    old["model"]["base_url"], old["model"]["model"])
        self.assertEqual({"configured": 4, "effective": 4,
                          "revision": newer["revision"]},
                         context._effective_provider_limit[identity])
        self.assertEqual(0, context._provider_fallback_retries)

    def test_story_arc_provider_call_uses_shared_fallback_wrapper(self):
        context = self.server.app_context
        calls = []
        original = context._call_provider_with_concurrency_fallback

        def recording_wrapper(config, provider_call):
            calls.append((config["base_url"], config["model"]))
            return original(config, provider_call)

        context._call_provider_with_concurrency_fallback = recording_wrapper
        claimed = {
            "job": {"type": "turns_to_arc"}, "input": {}, "context_state": {},
            "early_summaries": [], "recent_full_turns": [], "memories": [],
            "arcs": [], "location_nodes": {}, "documents": [],
            "revision_manifest": {},
        }
        context.story.claim = lambda save_id, job_id: claimed
        context.story.claim_arc = lambda value: []
        context.story.set_context_manifest = lambda job_id, manifest: None
        context.story.get_job = lambda save_id, job_id: {"status": "running"}
        context.story.complete_arc = lambda value, proposal: calls.append("completed")
        context.database.get_model_config = lambda: {
            "base_url": "https://arc.example/v1", "model": "arc-model",
            "max_concurrency": 2, "_settings_revision": 1,
        }
        context.content_registry.build_messages = lambda *args: ([], {})
        context.provider.generate_story_arc = lambda *args: {
            "schema_version": "story-arc/1", "title": "弧", "summary": "摘要",
            "key_events": [], "unresolved": [],
        }
        with mock.patch("api.server.contract_from_documents", return_value={
                "schema": {}, "version": "story-arc/1"}), mock.patch(
                "api.server.validate_story_arc", side_effect=lambda proposal, contract: proposal):
            context._run_narrative("save", "arc-job")
        self.assertEqual(("https://arc.example/v1", "arc-model"), calls[0])
        self.assertEqual("completed", calls[1])

    def test_high_rank_is_allowed_with_warning(self):
        self.configure_model()
        save = self.create_save()
        updated = self.save_draft(save, self.draft(rank=10))
        save = self.request("GET", f"/api/saves/{save['id']}")
        job = self.start_generation(save["id"], updated["draft_revision"], save["revision"])
        self.assertEqual("succeeded", self.wait_job(save["id"], job["id"])["status"])
        candidate = self.request("GET", f"/api/saves/{save['id']}/character-candidate")
        self.assertEqual(100000, candidate["power"]["base"])
        self.assertIsNone(candidate["next_exp"])
        self.assertNotIn("warnings", candidate)

    def test_invalid_model_output_fails_without_candidate(self):
        self.configure_model()
        self.provider.proposal = {"attributes": {}}
        save = self.create_save()
        updated = self.save_draft(save)
        save = self.request("GET", f"/api/saves/{save['id']}")
        job = self.start_generation(save["id"], updated["draft_revision"], save["revision"])
        result = self.wait_job(save["id"], job["id"])
        self.assertEqual("failed", result["status"])
        self.assertEqual("MODEL_OUTPUT_FORMAT", result["error"]["code"])
        self.request("GET", f"/api/saves/{save['id']}/character-candidate", expected=404)

    def test_draft_change_makes_late_generation_stale(self):
        self.configure_model()
        self.provider.block = True
        save = self.create_save()
        draft = self.save_draft(save)
        save = self.request("GET", f"/api/saves/{save['id']}")
        job = self.start_generation(save["id"], draft["draft_revision"], save["revision"])
        self.assertTrue(self.provider.started.wait(1))
        changed_data = dict(draft)
        changed_data["name"] = "更新后的名字"
        changed_data.update({"request_id": "draft-late-change",
                             "expected_save_revision": save["revision"]})
        changed = self.request("PUT", f"/api/saves/{save['id']}/character-draft", changed_data)
        self.assertEqual("更新后的名字", changed["name"])
        self.provider.release.set()
        result = self.wait_job(save["id"], job["id"])
        self.assertEqual("stale", result["status"])
        missing = self.request("GET", f"/api/saves/{save['id']}/character-candidate", expected=404)
        self.assertEqual("CANDIDATE_NOT_FOUND", missing["error"]["code"])

    def test_cancel_discards_late_result(self):
        self.configure_model()
        self.provider.block = True
        save = self.create_save()
        updated = self.save_draft(save)
        save = self.request("GET", f"/api/saves/{save['id']}")
        job = self.start_generation(save["id"], updated["draft_revision"], save["revision"])
        self.assertTrue(self.provider.started.wait(1))
        cancelled = self.request("POST", f"/api/saves/{save['id']}/character-generations/{job['id']}/cancel", {
            "request_id": "cancel-1"
        })
        self.assertEqual("cancel_requested", cancelled["status"])
        self.provider.release.set()
        result = self.wait_job(save["id"], job["id"])
        self.assertEqual("cancelled", result["status"])
        self.request("GET", f"/api/saves/{save['id']}/character-candidate", expected=404)

    def test_atomic_confirmation_is_idempotent_and_bootstraps_game(self):
        save_id, bootstrap = self.ready_save()
        character = bootstrap["character"]
        self.assertEqual(0, character["exp"])
        self.assertEqual(320, character["power"]["base"])
        self.assertEqual(450, character["starting_currency"]["copper"])
        candidate_id = character["id"]
        # Reusing the same confirmation request is idempotent even after the save becomes ready.
        repeated = self.request("POST", f"/api/saves/{save_id}/character/confirm", {
            "request_id": "confirm-1", "candidate_id": candidate_id,
            "expected_save_revision": 999, "expected_draft_revision": 999,
        })
        self.assertEqual(character["id"], repeated["character"]["id"])
        different_request = self.request("POST", f"/api/saves/{save_id}/character/confirm", {
            "request_id": "confirm-2", "candidate_id": candidate_id,
            "expected_save_revision": 999, "expected_draft_revision": 999,
        }, 409)
        self.assertEqual("SAVE_ALREADY_READY", different_request["error"]["code"])
        bootstrap = self.request("GET", f"/api/saves/{save_id}/game-bootstrap")
        self.assertEqual("ready", bootstrap["phase"])
        self.assertEqual(save_id, bootstrap["save_id"])

    def test_export_validate_import_round_trip_excludes_secret_and_assigns_new_id(self):
        save_id, _ = self.ready_save()
        exported = self.request("GET", f"/api/saves/{save_id}/export")
        export_text = json.dumps(exported, ensure_ascii=False).lower()
        self.assertNotIn("test-secret-key", export_text)
        self.assertNotIn("api_key", export_text)
        preview = self.request("POST", "/api/saves/import/validate", exported)
        self.assertTrue(preview["valid"])
        self.assertEqual("可导出存档", preview["save_name"])
        imported = self.request("POST", "/api/saves/import", {
            "request_id": "import-1", "payload": exported,
        }, 201)
        imported_again = self.request("POST", "/api/saves/import", {
            "request_id": "import-1", "payload": exported,
        }, 201)
        self.assertEqual(imported["id"], imported_again["id"])
        self.assertNotEqual(save_id, imported["id"])
        self.assertEqual(save_id, imported["source_save_id"])
        imported_bootstrap = self.request("GET", f"/api/saves/{imported['id']}/game-bootstrap")
        self.assertEqual("艾琳", imported_bootstrap["character"]["identity"]["name"])
        self.assertEqual(450, imported_bootstrap["character"]["starting_currency"]["copper"])
        malicious = json.loads(json.dumps(exported, ensure_ascii=False))
        malicious["api_key"] = "must-not-import"
        rejected = self.request("POST", "/api/saves/import/validate", malicious, 400)
        self.assertEqual("IMPORT_CONTAINS_SECRET", rejected["error"]["code"])

    def test_import_accepts_character_reason_edit_without_matching_candidate(self):
        save_id, _ = self.ready_save("手工修改角色说明")
        exported = self.request("GET", f"/api/saves/{save_id}/export")
        original_candidate_reason = exported["candidate"]["attributes"]["cha"]["reason"]
        exported["character"]["attributes"]["cha"]["reason"] = "手工修改后的魅力说明。"
        preview = self.request("POST", "/api/saves/import/validate", exported)
        self.assertTrue(preview["valid"])
        imported = self.request("POST", "/api/saves/import", {
            "request_id": "edited-character-reason", "payload": exported,
        }, 201)
        bootstrap = self.request("GET", f"/api/saves/{imported['id']}/game-bootstrap")
        self.assertEqual("手工修改后的魅力说明。",
                         bootstrap["character"]["attributes"]["cha"]["reason"])
        self.assertNotEqual(original_candidate_reason,
                            bootstrap["character"]["attributes"]["cha"]["reason"])

    def test_legacy_save_without_starting_currency_keeps_zero_balance(self):
        save_id, _ = self.ready_save("旧版钱财存档")
        exported = self.request("GET", f"/api/saves/{save_id}/export")
        exported["candidate"].pop("starting_currency")
        exported["candidate"].pop("contract_version")
        exported["character"].pop("initial_currency_copper")
        exported["character"].pop("starting_currency_reason")
        exported["character"]["provenance"]["output_contract_version"] = "character-candidate/1"
        exported["character"]["provenance"]["prompt_version"] = "character-generator/1"
        self.assertTrue(self.request("POST", "/api/saves/import/validate", exported)["valid"])
        imported = self.request("POST", "/api/saves/import", {
            "request_id": "legacy-currency-import", "payload": exported,
        }, 201)
        bootstrap = self.request("GET", f"/api/saves/{imported['id']}/game-bootstrap")
        self.assertNotIn("starting_currency", bootstrap["character"])
        self.assertEqual(0, bootstrap["story"]["state"]["currency_copper"])

    def test_current_candidate_cannot_drop_starting_currency(self):
        save_id, _ = self.ready_save("钱财契约防篡改")
        exported = self.request("GET", f"/api/saves/{save_id}/export")
        exported["candidate"].pop("starting_currency")
        rejected = self.request("POST", "/api/saves/import/validate", exported, 400)
        self.assertIn("candidate", rejected["error"]["fields"])

    def test_import_rejects_malformed_nested_data_and_normalizes_storage(self):
        save_id, _ = self.ready_save("严格导入")
        exported = self.request("GET", f"/api/saves/{save_id}/export")
        cases = []
        unknown = json.loads(json.dumps(exported, ensure_ascii=False))
        unknown["draft"]["data"]["unexpected"] = "value"
        cases.append(unknown)
        wrong_location = json.loads(json.dumps(exported, ensure_ascii=False))
        wrong_location["character"]["current_location_id"] = "missing-place"
        cases.append(wrong_location)
        bad_resource = json.loads(json.dumps(exported, ensure_ascii=False))
        bad_resource["candidate"]["resources"]["hp"]["current"] = 1
        cases.append(bad_resource)
        modifier = json.loads(json.dumps(exported, ensure_ascii=False))
        modifier["character"]["power_modifiers"] = [{"label": "注入", "value": 999}]
        cases.append(modifier)
        identity = json.loads(json.dumps(exported, ensure_ascii=False))
        identity["character"]["identity"]["name"] = "伪造身份"
        cases.append(identity)
        wrong_phase = json.loads(json.dumps(exported, ensure_ascii=False))
        wrong_phase["save"]["phase"] = "review"
        cases.append(wrong_phase)
        for index, malformed in enumerate(cases):
            result = self.request("POST", "/api/saves/import/validate", malformed, 400)
            self.assertEqual("IMPORT_INVALID", result["error"]["code"], index)

        secret_alias = json.loads(json.dumps(exported, ensure_ascii=False))
        secret_alias["candidate"]["providerPasswordBackup"] = "forbidden"
        result = self.request("POST", "/api/saves/import/validate", secret_alias, 400)
        self.assertEqual("IMPORT_CONTAINS_SECRET", result["error"]["code"])

        clean = json.loads(json.dumps(exported, ensure_ascii=False))
        clean["save"]["name"] = "  规范化名称  "
        imported = self.request("POST", "/api/saves/import", {
            "request_id": "normalized-import", "payload": clean,
        }, 201)
        self.assertEqual("规范化名称", imported["name"])
        connection = sqlite3.connect(Path(self.temporary.name) / ".data" / "fantasy_simulator.sqlite3")
        try:
            stored = json.loads(connection.execute(
                "SELECT data_json FROM candidates WHERE save_id=?", (imported["id"],)).fetchone()[0])
            self.assertEqual([], stored["power_modifiers"])
            self.assertEqual(stored["resources"]["hp"]["max"], stored["resources"]["hp"]["current"])
        finally:
            connection.close()

    def test_error_shape_and_draft_rejects_faction(self):
        save = self.create_save()
        error = self.request("PUT", f"/api/saves/{save['id']}/character-draft", {
            "request_id": "bad-draft", "draft_revision": 0,
            "expected_save_revision": 0, "current_step": 12,
            "race_id": "human", "name": "艾琳", "gender": "女", "age": 24,
            "appearance": "黑发", "personality": "沉着", "rank": 3,
            "talent": "魔力感知敏锐", "background": "", "location_id": "grand_academy",
            "additional": "", "faction_id": "sacred_radiance",
        }, 400)
        self.assertEqual({"code", "message", "fields", "field_errors", "retryable", "trace_id"}, set(error["error"]))
        self.assertIn("faction_id", error["error"]["fields"])


if __name__ == "__main__":
    unittest.main()
