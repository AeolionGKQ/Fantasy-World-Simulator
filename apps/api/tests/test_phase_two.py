import copy
import json
import sqlite3
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

API_DIR = Path(__file__).resolve().parents[1]
APPS_DIR = API_DIR.parent
if str(APPS_DIR) not in sys.path:
    sys.path.insert(0, str(APPS_DIR))

from api.content_registry import CANON_DOCUMENTS, RULE_DOCUMENTS, ContentRegistry
from api.contract_registry import contract_from_documents, load_contract, validate_json_schema
from api.database import Database, DomainError
from api.model_provider import OpenAICompatibleProvider, ProviderError, is_context_length_error
from api.narrative_contract import (REPUTATION_KEYS, ContractError, adjudicate,
                                    validate_gm_response)
from api.story_repository import (StoryRepository, canonical_location_map, initial_story_state,
                                  start_prerequisite)
from api.server import create_server


def gm_response(response_type="opening"):
    return {
        "schema_version": "gm-turn/1", "response_type": response_type,
        "narrative": {"title": "旅程开始", "body": "晨光落在广场上。",
                      "chronicle_summary": "旅人在广场开始新的旅程。",
                      "suggested_options": [
                          {"id": "look", "text": "环顾四周", "intent": "观察环境"},
                          {"id": "walk", "text": "走向大道", "intent": "继续探索"}]},
        "scene": {"time_label": "上午", "elapsed_minutes": 5,
                  "location": {"operation": "stay", "location_id": None,
                               "location_ref": None, "reason": "仍在原地"},
                  "new_locations": [], "new_npcs": []},
        "proposals": {"resources": [], "attributes": [], "experience": [],
                      "breakthrough": None, "items": [],
                      "currency": {"copper_delta": 0, "reason": "", "evidence": ""},
                      "quests": [], "bonds": [], "reputations": [], "skills": [],
                      "talents": [], "world_flags": [], "power_modifiers": []},
        "memory_candidates": [], "warnings": [],
    }


class PhaseTwoProvider:
    def __init__(self):
        self.character = {
            "attributes": {key: {"value": 50, "reason": "初始"} for key in ("con", "int", "cha")},
            "resources": {key: {"max": 100, "reason": "初始"} for key in ("hp", "mp", "sp", "st")},
            "summary": "测试角色", "strengths": [], "limitations": [], "warnings": []}
        self.responses = []
        self.messages = []

    def test_connection(self, *args, **kwargs):
        return {"connected": True, "model_available": True, "thinking_probed": False,
                "thinking": {"capability": "controlled", "strategy": "enable_thinking",
                             "confidence": "verified", "message": "ok"}}

    def generate_character(self, *args, **kwargs):
        return copy.deepcopy(self.character)

    def generate_narrative(self, config, key, messages, callback=None):
        self.messages.append(messages)
        return copy.deepcopy(self.responses.pop(0))

    def generate_story_arc(self, config, key, messages, callback=None):
        self.messages.append(messages)
        return {"schema_version": "story-arc/1", "title": "第一故事弧",
                "summary": "一段连续旅程。", "key_events": ["旅程开始"], "unresolved": []}


class ContentTest(unittest.TestCase):
    def test_complete_documents_and_regional_selection(self):
        registry = ContentRegistry(API_DIR)
        self.assertEqual([x[1] for x in RULE_DOCUMENTS],
                         [x["source_path"] for x in registry.documents if x["category"] == "rule"])
        self.assertEqual([x[1] for x in CANON_DOCUMENTS],
                         [x["source_path"] for x in registry.documents if x["category"] == "canon"])
        for document in registry.documents:
            source = (API_DIR / document["source_path"] if document["source_path"].startswith("content/")
                      else API_DIR.parents[1] / document["source_path"])
            self.assertEqual(source.read_bytes(), document["raw_bytes"])
        state = {"state_version": 0, "location": {"id": "selavia_port"},
                 "regional_quests": {}, "narration": {}}
        selected = registry.select_quests(state)
        self.assertTrue(all(item["full_source_markdown"] is None for item in selected))
        state["location"]["id"] = "selavia_port.adventurers_guild"
        selected = registry.select_quests(state)
        full = [item for item in selected if item["full_source_markdown"]]
        self.assertEqual(["regional_main.lost_tidevoice"], [item["id"] for item in full])
        self.assertIn("# 南海自由联邦地区主线：遗失的潮音", full[0]["full_source_markdown"])
        self.assertNotIn("# 云端天境地区主线", full[0]["full_source_markdown"])

    def test_unknown_reputation_and_context_error(self):
        value = gm_response()
        value["proposals"]["reputations"] = [{"key": "unknown", "delta": 1,
                                               "public_reason": "公开", "evidence": "正文"}]
        with self.assertRaises(Exception):
            validate_gm_response(value)
        error = ProviderError("MODEL_REQUEST_REJECTED", "拒绝", False, 400,
                              "maximum context length exceeded", "context_length_exceeded")
        self.assertTrue(is_context_length_error(error))

    def test_schema_is_prompt_and_validation_single_source(self):
        registry = ContentRegistry(API_DIR)
        gm_contract = contract_from_documents("gm_turn", registry.documents)
        arc_contract = contract_from_documents("story_arc", registry.documents)
        validate_json_schema(gm_response("turn"), gm_contract["schema"])
        validate_json_schema({"schema_version": "story-arc/1", "title": "弧", "summary": "摘要",
                              "key_events": [], "unresolved": []}, arc_contract["schema"])
        messages, manifest = registry.build_messages(
            {"state_version": 0, "location": {"id": "grand_academy"}, "regional_quests": {},
             "narration": {}}, {"action_type": "turn"}, [], [], [], [], {}, registry.documents,
            "gm_turn", registry.manifest)
        system = messages[0]["content"]
        self.assertIn(json.dumps(gm_contract["schema"], ensure_ascii=False, separators=(",", ":")), system)
        self.assertNotIn("story-arc/1 JSON Schema", system)
        self.assertEqual("gm_turn", manifest["contract_kind"])

    def test_all_regional_roots_and_terminal_context(self):
        registry = ContentRegistry(API_DIR)
        roots = {quest["id"]: quest["roots"][0] for quest in registry.quests}
        self.assertEqual("velansia.central_plaza", roots["regional_main.walking_with_wind"])
        for quest in registry.quests:
            state = {"location": {"id": quest["roots"][0]}, "regional_quests": {}, "narration": {}}
            selected = {item["id"]: item for item in registry.select_quests(state)}
            self.assertEqual("location_matched", selected[quest["id"]]["context_eligibility"])
            self.assertIsNotNone(selected[quest["id"]]["full_source_markdown"])
            state["location"]["id"] = "san_velia"
            state["regional_quests"] = {quest["id"]: {"status": "active"}}
            selected = {item["id"]: item for item in registry.select_quests(state)}
            self.assertEqual("persistent_active", selected[quest["id"]]["context_eligibility"])
            state["regional_quests"][quest["id"]]["status"] = "completed"
            self.assertNotIn(quest["id"], {item["id"] for item in registry.select_quests(state)})

    def test_provider_json_schema_falls_back_to_json_object(self):
        contract = load_contract("gm_turn")
        requests = []
        from api.tests.test_api import FakeHttpResponse, ProviderTestCase
        def respond(request, timeout):
            payload = json.loads(request.data)
            requests.append(payload)
            if len(requests) == 1:
                raise ProviderTestCase.http_error(400, {"error": {"message": "Unsupported response_format json_schema"}})
            return FakeHttpResponse({"choices": [{"message": {"content": json.dumps(gm_response("turn"))}}]})
        config = {"base_url": "https://unused.example/v1", "model": "fake", "timeout_seconds": 1,
                  "structured_output": True, "_output_schema": contract["schema"],
                  "_output_schema_name": "gm_turn_1"}
        from unittest import mock
        with mock.patch("urllib.request.urlopen", side_effect=respond):
            OpenAICompatibleProvider().generate_narrative(config, "secret", [])
        self.assertEqual("json_schema", requests[0]["response_format"]["type"])
        self.assertEqual({"type": "json_object"}, requests[1]["response_format"])

    def test_unavailable_response_format_falls_back_schema_object_none(self):
        contract = load_contract("gm_turn")
        requests = []
        from api.tests.test_api import FakeHttpResponse, ProviderTestCase
        from unittest import mock

        def respond(request, timeout):
            payload = json.loads(request.data)
            requests.append(payload)
            if len(requests) <= 2:
                raise ProviderTestCase.http_error(400, {"error": {"message":
                    "This response_format type is unavailable now (...)"}})
            return FakeHttpResponse({"choices": [{"message": {
                "content": json.dumps(gm_response("turn"))}}]})

        config = {"base_url": "https://unused.example/v1", "model": "fake",
                  "timeout_seconds": 1, "structured_output": True,
                  "_output_schema": contract["schema"], "_output_schema_name": "gm_turn_1"}
        with mock.patch("urllib.request.urlopen", side_effect=respond) as call:
            result = OpenAICompatibleProvider().generate_narrative(config, "secret", [])
        self.assertEqual("gm-turn/1", result["schema_version"])
        self.assertEqual(3, call.call_count)
        self.assertEqual("json_schema", requests[0]["response_format"]["type"])
        self.assertEqual({"type": "json_object"}, requests[1]["response_format"])
        self.assertNotIn("response_format", requests[2])

    def test_contract_anyof_and_schema_keyword_fallback_only(self):
        contract = load_contract("gm_turn")
        self.assertIn("anyOf", contract["schema"]["properties"]["proposals"]["properties"]["breakthrough"])
        self.assertNotIn("oneOf", json.dumps(contract["schema"]))
        validate_json_schema(gm_response("turn"), contract["schema"])
        from api.tests.test_api import FakeHttpResponse, ProviderTestCase
        from unittest import mock
        for message in ("unsupported schema keyword anyOf", "invalid schema for response_format",
                        "oneOf not permitted in json_schema"):
            requests = []
            def respond(request, timeout, text=message):
                requests.append(json.loads(request.data))
                if len(requests) == 1:
                    raise ProviderTestCase.http_error(422, {"error": {"message": text}})
                return FakeHttpResponse({"choices": [{"message": {"content": json.dumps(gm_response("turn"))}}]})
            config = {"base_url": "https://unused.example/v1", "model": "fake", "timeout_seconds": 1,
                      "structured_output": True, "_output_schema": contract["schema"]}
            with self.subTest(message=message), mock.patch("urllib.request.urlopen", side_effect=respond):
                OpenAICompatibleProvider().generate_narrative(config, "secret", [])
            self.assertEqual({"type": "json_object"}, requests[1]["response_format"])
        with mock.patch("urllib.request.urlopen", side_effect=ProviderTestCase.http_error(
                400, {"error": {"message": "invalid model identifier"}})) as call:
            with self.assertRaises(ProviderError):
                OpenAICompatibleProvider().generate_narrative(config, "secret", [])
        self.assertEqual(1, call.call_count)

    def test_time_resource_exp_reputation_bond_and_warning_guards(self):
        bad_time = gm_response("turn"); bad_time["scene"]["time_label"] = "午夜后"
        with self.assertRaises(ContractError): validate_gm_response(bad_time)
        low_exp = gm_response("turn"); low_exp["narrative"]["body"] = "重复进行无挑战训练却获得大量成长经验。"
        low_exp["proposals"]["experience"] = [{"amount": 50, "growth_type": "训练",
            "challenge": "low", "novelty": "none", "repetition": "repeated",
            "reason": "重复训练", "evidence": "大量成长经验"}]
        with self.assertRaises(ContractError): validate_gm_response(low_exp)
        private_rep = gm_response("turn"); private_rep["narrative"]["body"] = "事件没有公开，也未传播。"
        private_rep["proposals"]["reputations"] = [{"key": "continental_overall", "delta": 5,
            "public_reason": "没有公开且未传播", "evidence": "没有公开"}]
        with self.assertRaises(ContractError): validate_gm_response(private_rep)
        dangling_bond = gm_response("turn"); dangling_bond["proposals"]["bonds"] = [{
            "operation": "create_or_join", "npc_id": None, "npc_ref": "npc:new:missing",
            "npc_name": "陌生人", "delta": 1, "relation_type": "friend",
            "admission": "likely_recurring", "reason": "相识", "evidence": "晨光"}]
        with self.assertRaises(ContractError): validate_gm_response(dangling_bond)
        valid_bond = gm_response("turn"); valid_bond["scene"]["new_npcs"] = [{
            "ref": "npc:new:1", "name": "旅伴", "description": "可能长期同行", "reason": "本轮相识"}]
        valid_bond["proposals"]["bonds"] = [{"operation": "create_or_join", "npc_id": None,
            "npc_ref": "npc:new:1", "npc_name": "旅伴", "delta": 1, "relation_type": "companion",
            "admission": "likely_recurring", "reason": "同行", "evidence": "晨光"}]
        validate_gm_response(valid_bond)
        registry = ContentRegistry(API_DIR)
        character = {"id": "character", "candidate_id": "candidate", "data": {
            "identity": {"talent": ""}, "current_location_id": "grand_academy",
            "attributes": {key: {"value": 50, "reason": ""} for key in ("con", "int", "cha")},
            "resources": {key: {"current": 100, "max": 100, "reason": ""} for key in ("hp", "mp", "sp", "st")},
            "rank": 3, "exp": 0}}
        state = initial_story_state(character, {"narration": {}}, registry.revision_id, registry.quests)
        exhausted = gm_response("turn"); exhausted["narrative"]["body"] = "魔力、精神和精力全部耗尽。"
        exhausted["proposals"]["resources"] = [
            {"key": key, "delta": -100, "reason": "耗尽", "evidence": label}
            for key, label in (("mp", "魔力"), ("sp", "精神"), ("st", "精力"))]
        result = adjudicate(state, validate_gm_response(exhausted), canonical_location_map(), set())
        self.assertEqual({"mana_depleted", "mental_collapse", "exhausted"},
                         set(result["state"]["character"]["status_effects"]))
        state["character"]["exp"] = 200; state["character"]["breakthrough_eligible"] = True
        state["character"]["resources"]["sp"]["current"] = 0
        attempt = gm_response("turn"); attempt["narrative"]["body"] = "角色尝试突破瓶颈。"
        attempt["proposals"]["breakthrough"] = {"attempted": True, "success": True,
            "method": "引导魔力", "preparation": "完成准备", "failure_reason": None,
            "improvement": None, "task_completed_id": None, "reason": "尝试", "evidence": "尝试突破"}
        with self.assertRaises(ContractError):
            adjudicate(state, validate_gm_response(attempt), canonical_location_map(), set())

    def test_breakthrough_modifier_and_consistency(self):
        registry = ContentRegistry(API_DIR)
        character = {"id": "character", "candidate_id": "candidate", "data": {
            "identity": {"talent": ""}, "current_location_id": "grand_academy",
            "attributes": {key: {"value": 50, "reason": ""} for key in ("con", "int", "cha")},
            "resources": {key: {"current": 100, "max": 100, "reason": ""} for key in ("hp", "mp", "sp", "st")},
            "rank": 6, "exp": 649}}
        state = initial_story_state(character, {"narration": {}}, registry.revision_id, registry.quests)
        state["character"]["rank"] = 6; state["character"]["exp"] = 649
        state["character"]["exp_to_next"] = 650; state["character"]["base_power"] = 1800
        state["character"]["effective_power"] = 1800
        response = gm_response("turn")
        response["narrative"]["body"] = "长期训练后获得成长经验，并收到七阶突破任务。"
        response["proposals"]["experience"] = [{"amount": 1, "growth_type": "训练", "challenge": "高",
            "novelty": "新", "repetition": "无", "reason": "长期训练", "evidence": "成长经验"}]
        response["proposals"]["quests"] = [{"operation": "create", "quest_id": "breakthrough.7",
            "name": "七阶突破", "description": "完成个性化试炼", "status": "active", "progress": "开始",
            "objectives": ["试炼"], "quest_kind": "breakthrough", "target_rank": 7,
            "action_evidence": "长期训练", "necessary_nodes": [], "reason": "达到门槛", "evidence": "七阶突破任务"}]
        decided = adjudicate(state, validate_gm_response(response), canonical_location_map(),
                             {q["id"] for q in registry.quests}, {}, {"action": "长期训练"})
        self.assertEqual("breakthrough", decided["state"]["quests"]["breakthrough.7"]["quest_kind"])
        breakthrough_state = decided["state"]
        breakthrough_state["quests"]["breakthrough.7"]["status"] = "completed"
        success = gm_response("turn")
        success["narrative"]["body"] = "角色完成突破任务并成功突破至七阶。"
        success["proposals"]["breakthrough"] = {"attempted": True, "success": True,
            "method": "稳定引导魔力完成突破", "preparation": "状态良好且已完成试炼",
            "failure_reason": None, "improvement": None, "task_completed_id": "breakthrough.7",
            "reason": "完成试炼", "evidence": "成功突破"}
        advanced = adjudicate(breakthrough_state, validate_gm_response(success),
                              canonical_location_map(), set(), {}, {"action": "尝试突破"})
        self.assertEqual(7, advanced["state"]["character"]["rank"])
        self.assertEqual(0, advanced["state"]["character"]["exp"])
        self.assertTrue(advanced["state"]["quests"]["breakthrough.7"]["consumed"])
        decided["state"]["character"]["power_modifiers"] = [{"id": "terrain", "value": 10,
            "reason": "地形", "temporary": True, "category": "environment", "severity": "minor",
            "canonical_exception": None}]
        neutral = gm_response("turn")
        kept = adjudicate(decided["state"], neutral, canonical_location_map(), set(), {}, {})
        self.assertEqual("terrain", kept["state"]["character"]["power_modifiers"][0]["id"])
        bad = gm_response("turn"); bad["narrative"]["body"] = "旅人死亡。"
        with self.assertRaises(ContractError):
            adjudicate(state, bad, canonical_location_map(), set(), {}, {})
        overpowered = gm_response("turn")
        overpowered["narrative"]["body"] = "普通地形令战力大幅提升。"
        overpowered["proposals"]["power_modifiers"] = [{"operation": "add", "id": "too-much",
            "value": 5000, "temporary": True, "category": "environment", "severity": "major",
            "canonical_exception": "玩家声称这是例外", "reason": "地形", "evidence": "战力大幅提升"}]
        with self.assertRaises(ContractError):
            adjudicate(state, validate_gm_response(overpowered), canonical_location_map(), set(), {}, {})

    def test_modifier_update_and_same_turn_flag_cannot_bypass(self):
        registry = ContentRegistry(API_DIR)
        character = {"id": "character", "candidate_id": "candidate", "data": {
            "identity": {"talent": ""}, "current_location_id": "grand_academy",
            "attributes": {key: {"value": 50, "reason": ""} for key in ("con", "int", "cha")},
            "resources": {key: {"current": 100, "max": 100, "reason": ""} for key in ("hp", "mp", "sp", "st")},
            "rank": 3, "exp": 0}}
        state = initial_story_state(character, {"narration": {}}, registry.revision_id, registry.quests)
        state["character"]["power_modifiers"] = [{"id": "existing", "value": 1, "reason": "旧",
            "temporary": True, "category": "environment", "severity": "minor", "canonical_exception": None}]
        response = gm_response("turn"); response["narrative"]["body"] = "本轮创造标记并宣称战力极端提升。"
        response["proposals"]["world_flags"] = [{"key": "canon_exception.fake", "value": True,
            "reason": "本轮创建", "evidence": "创造标记"}]
        response["proposals"]["power_modifiers"] = [{"operation": "update", "id": "existing",
            "value": 5000, "temporary": True, "category": "environment", "severity": "extreme",
            "canonical_exception": "canon_exception.fake", "reason": "伪造", "evidence": "战力极端提升"}]
        with self.assertRaises(ContractError):
            adjudicate(state, validate_gm_response(response), canonical_location_map(), set())

    def test_duplicate_keyed_proposals_are_rejected(self):
        duplicate_hp = gm_response("turn")
        duplicate_hp["narrative"]["body"] = "生命先恢复又受到伤害。"
        duplicate_hp["proposals"]["resources"] = [
            {"key": "hp", "delta": 100, "reason": "恢复", "evidence": "生命先恢复"},
            {"key": "hp", "delta": -100, "reason": "受伤", "evidence": "受到伤害"},
        ]
        with self.assertRaisesRegex(ContractError, "同一键"):
            validate_gm_response(duplicate_hp)
        for group, entries in (
                ("attributes", [
                    {"key": "con", "delta": 1, "long_term_basis": "长期训练", "reason": "成长", "evidence": "成长"},
                    {"key": "con", "delta": 1, "long_term_basis": "长期训练", "reason": "成长", "evidence": "成长"}]),
                ("reputations", [
                    {"key": "continental_overall", "delta": 1, "public_reason": "公开传播", "evidence": "公开"},
                    {"key": "continental_overall", "delta": 1, "public_reason": "公开传播", "evidence": "公开"}])):
            response = gm_response("turn")
            response["narrative"]["body"] = "长期成长被众人公开传播。"
            response["proposals"][group] = entries
            with self.subTest(group=group), self.assertRaisesRegex(ContractError, "同一键"):
                validate_gm_response(response)

    def test_canonical_power_exception_requires_applicable_state(self):
        registry = ContentRegistry(API_DIR)
        character = {"id": "character", "candidate_id": "candidate", "data": {
            "identity": {"talent": "", "race_id": "human"}, "current_location_id": "grand_academy",
            "attributes": {key: {"value": 50, "reason": ""} for key in ("con", "int", "cha")},
            "resources": {key: {"current": 100, "max": 100, "reason": ""} for key in ("hp", "mp", "sp", "st")},
            "rank": 3, "exp": 0}}
        state = initial_story_state(character, {"narration": {}}, registry.revision_id, registry.quests)
        response = gm_response("turn")
        response["narrative"]["body"] = "深海亲和令战力大幅提升。"
        response["proposals"]["power_modifiers"] = [{"operation": "add", "id": "false-sea-bonus",
            "value": 500, "temporary": True, "category": "environment", "severity": "major",
            "canonical_exception": "canon:sea_folk_deep_sea", "reason": "深海亲和",
            "evidence": "战力大幅提升"}]
        with self.assertRaisesRegex(ContractError, "不适用"):
            adjudicate(state, validate_gm_response(response), canonical_location_map(), set(), {}, {})

    def test_breakthrough_requires_explicit_player_action(self):
        registry = ContentRegistry(API_DIR)
        character = {"id": "character", "candidate_id": "candidate", "data": {
            "identity": {"talent": "", "race_id": "human"}, "current_location_id": "grand_academy",
            "attributes": {key: {"value": 50, "reason": ""} for key in ("con", "int", "cha")},
            "resources": {key: {"current": 100, "max": 100, "reason": ""} for key in ("hp", "mp", "sp", "st")},
            "rank": 3, "exp": 200}}
        state = initial_story_state(character, {"narration": {}}, registry.revision_id, registry.quests)
        state["character"]["exp"] = 200
        state["character"]["breakthrough_eligible"] = True
        response = gm_response("turn")
        response["narrative"]["body"] = "吃饭时角色忽然尝试突破并成功升阶。"
        response["proposals"]["breakthrough"] = {"attempted": True, "success": True,
            "method": "引导魔力", "preparation": "状态良好", "failure_reason": None,
            "improvement": None, "task_completed_id": None, "reason": "突破成功", "evidence": "尝试突破"}
        with self.assertRaisesRegex(ContractError, "玩家原始行动"):
            adjudicate(state, validate_gm_response(response), canonical_location_map(), set(), {},
                       {"action": "坐下来吃饭"})
        with self.assertRaisesRegex(ContractError, "明确否定突破"):
            adjudicate(state, validate_gm_response(response), canonical_location_map(), set(), {},
                       {"action": "我不想突破，也不要升阶"})
        with self.assertRaisesRegex(ContractError, "明确否定突破"):
            adjudicate(state, validate_gm_response(response), canonical_location_map(), set(), {},
                       {"action": "不要在任何情况下让角色尝试突破或升阶"})

    def test_memory_evidence_must_be_verbatim_in_narrative(self):
        response = gm_response("turn")
        response["narrative"]["body"] = "国王在宴会上向旅人致意，宴会随后平静结束。"
        response["memory_candidates"] = [{"operation": "create", "memory_id": None, "kind": "event",
            "summary": "国王已被杀死", "importance": 100, "people": [], "locations": [],
            "keywords": ["国王"], "facts": ["国王死亡"], "unresolved": [], "reason": "重大事件",
            "evidence": "国王"}]
        with self.assertRaisesRegex(ContractError, "evidence"):
            validate_gm_response(response)
        response["memory_candidates"][0]["evidence"] = "国王在宴会上向旅人致意"
        with self.assertRaisesRegex(ContractError, "memory.facts"):
            validate_gm_response(response)
        response["narrative"]["body"] = "关于国王退位的传言当场被证实为虚假，国王本人仍然在位。"
        response["memory_candidates"][0].update({
            "summary": "国王退位", "facts": ["国王退位"],
            "evidence": "关于国王退位的传言当场被证实为虚假"})
        with self.assertRaisesRegex(ContractError, "memory.facts"):
            validate_gm_response(response)

    def test_memory_people_and_locations_require_known_references(self):
        registry = ContentRegistry(API_DIR)
        character = {"id": "character", "candidate_id": "candidate", "data": {
            "identity": {"talent": "", "race_id": "human"}, "current_location_id": "grand_academy",
            "attributes": {key: {"value": 50, "reason": ""} for key in ("con", "int", "cha")},
            "resources": {key: {"current": 100, "max": 100, "reason": ""} for key in ("hp", "mp", "sp", "st")},
            "rank": 3, "exp": 0}}
        state = initial_story_state(character, {"narration": {}}, registry.revision_id, registry.quests)
        response = gm_response("turn")
        response["narrative"]["body"] = "旅人在广场记下一段完整而清晰的见闻。"
        response["memory_candidates"] = [{"operation": "create", "memory_id": None, "kind": "event",
            "summary": "广场见闻", "importance": 50, "people": ["npc.unknown"],
            "locations": ["location.unknown"], "keywords": ["见闻"],
            "facts": ["旅人在广场记下一段完整而清晰的见闻"], "unresolved": [], "reason": "值得记录",
            "evidence": "旅人在广场记下一段完整而清晰的见闻"}]
        validated = validate_gm_response(response)
        with self.assertRaisesRegex(ContractError, "people必须引用已知"):
            adjudicate(state, validated, canonical_location_map(), set(), {}, {})

    def test_new_location_region_must_inherit_parent(self):
        registry = ContentRegistry(API_DIR)
        character = {"id": "character", "candidate_id": "candidate", "data": {
            "identity": {"talent": ""}, "current_location_id": "grand_academy",
            "attributes": {key: {"value": 50, "reason": ""} for key in ("con", "int", "cha")},
            "resources": {key: {"current": 100, "max": 100, "reason": ""} for key in ("hp", "mp", "sp", "st")},
            "rank": 3, "exp": 0}}
        state = initial_story_state(character, {"narration": {}}, registry.revision_id, registry.quests)
        response = gm_response("turn"); response["narrative"]["body"] = "角色进入新教室。"
        response["scene"]["new_locations"] = [{"ref": "location:new:1", "name": "教室", "type": "room",
            "parent_id": "grand_academy", "region_id": "noxvia", "description": "学院教室", "reason": "进入"}]
        with self.assertRaises(ContractError):
            adjudicate(state, validate_gm_response(response), canonical_location_map(), set())

    def test_regional_active_requires_raw_player_action(self):
        registry = ContentRegistry(API_DIR)
        for quest_id in ("regional_main.walking_with_wind", "regional_main.mia_day_out",
                         "regional_main.song_of_sandsea", "regional_main.grand_academy_first_day"):
            quest = next(item for item in registry.quests if item["id"] == quest_id)
            character = {"id": "character", "candidate_id": "candidate", "data": {
                "identity": {"talent": "", "race_id": "human"}, "current_location_id": quest["roots"][0],
                "attributes": {key: {"value": 50, "reason": ""} for key in ("con", "int", "cha")},
                "resources": {key: {"current": 100, "max": 100, "reason": ""} for key in ("hp", "mp", "sp", "st")},
                "rank": 3, "exp": 0}}
            state = initial_story_state(character, {"narration": {}}, registry.revision_id, registry.quests)
            response = gm_response("turn"); response["narrative"]["body"] = "模型声称玩家已经接受并开始任务。"
            response["proposals"]["quests"] = [{"operation": "transition", "quest_id": quest_id,
                "name": quest["name"], "description": quest["description"], "status": "active", "progress": "开始",
                "objectives": [], "quest_kind": "regional", "target_rank": None,
                "action_evidence": "模型声称接受", "necessary_nodes": [], "reason": "开始", "evidence": "开始任务"}]
            with self.subTest(quest=quest_id), self.assertRaises(ContractError):
                adjudicate(state, validate_gm_response(response), canonical_location_map(), {quest_id},
                           {quest_id: {"context_eligibility": "location_matched"}},
                           {"action": "只是观察"}, {quest_id: quest})

    def test_regional_active_respects_explicit_player_negation(self):
        registry = ContentRegistry(API_DIR)
        quest_id = "regional_main.song_of_sandsea"
        quest = next(item for item in registry.quests if item["id"] == quest_id)
        character = {"id": "character", "candidate_id": "candidate", "data": {
            "identity": {"talent": "", "race_id": "human"}, "current_location_id": quest["roots"][0],
            "attributes": {key: {"value": 50, "reason": ""} for key in ("con", "int", "cha")},
            "resources": {key: {"current": 100, "max": 100, "reason": ""} for key in ("hp", "mp", "sp", "st")},
            "rank": 3, "exp": 0}}
        state = initial_story_state(character, {"narration": {}}, registry.revision_id, registry.quests)
        response = gm_response("turn")
        response["narrative"]["body"] = "娜希娅发布招募，但模型仍宣称玩家加入商队并开始任务。"
        response["proposals"]["quests"] = [{"operation": "transition", "quest_id": quest_id,
            "name": quest["name"], "description": quest["description"], "status": "active", "progress": "开始",
            "objectives": [], "quest_kind": "regional", "target_rank": None,
            "action_evidence": "加入商队", "necessary_nodes": [], "reason": "开始", "evidence": "开始任务"}]
        context = {quest_id: {"context_eligibility": "location_matched"}}
        action = {"action": "我不接受招募，不加入商队，也不担任护卫"}
        with self.assertRaisesRegex(ContractError, "明确否定地区任务"):
            adjudicate(state, validate_gm_response(response), canonical_location_map(), {quest_id},
                       context, action, {quest_id: quest})
        with self.assertRaisesRegex(ContractError, "明确否定地区任务"):
            adjudicate(state, validate_gm_response(response), canonical_location_map(), {quest_id},
                       context, {"action": "不要在任何情况下让他们把我登记为护卫或加入商队"},
                       {quest_id: quest})
        state["regional_quests"][quest_id]["status"] = "offered"
        declined = copy.deepcopy(response)
        declined["narrative"]["body"] = "玩家拒绝任务，商队尊重决定。"
        declined["proposals"]["quests"][0].update({"status": "declined", "progress": "已拒绝",
            "action_evidence": action["action"], "reason": "玩家拒绝", "evidence": "拒绝任务"})
        decided = adjudicate(state, validate_gm_response(declined), canonical_location_map(), {quest_id},
                             {quest_id: {"context_eligibility": "persistent_active"}}, action,
                             {quest_id: quest})
        self.assertEqual("declined", decided["state"]["regional_quests"][quest_id]["status"])

    def test_regional_completion_applies_frozen_rewards(self):
        registry = ContentRegistry(API_DIR)
        quest = registry.quests[0]
        character = {"id": "character", "candidate_id": "candidate", "data": {
            "identity": {"talent": "", "race_id": "human"},
            "current_location_id": "selavia_port.adventurers_guild",
            "attributes": {key: {"value": 50, "reason": ""} for key in ("con", "int", "cha")},
            "resources": {key: {"current": 100, "max": 100, "reason": ""} for key in ("hp", "mp", "sp", "st")},
            "rank": 3, "exp": 0}}
        state = initial_story_state(character, {"narration": {}}, registry.revision_id, registry.quests)
        state["regional_quests"][quest["id"]]["status"] = "active"
        response = gm_response("turn")
        response["narrative"]["body"] = "潮音珠及时找回，演出顺利举行，任务完成。"
        response["proposals"]["quests"] = [{"operation": "transition", "quest_id": quest["id"],
            "name": quest["name"], "description": quest["description"], "status": "completed",
            "progress": "完成", "objectives": [], "quest_kind": "regional", "target_rank": None,
            "action_evidence": "找回潮音珠", "necessary_nodes": ["潮音珠", "演出"],
            "reason": "任务完成", "evidence": "任务完成"}]
        result = adjudicate(state, validate_gm_response(response), canonical_location_map(),
                            {quest["id"]}, {quest["id"]: {"context_eligibility": "persistent_active"}},
                            {"action": "交还潮音珠"}, {quest["id"]: quest})
        self.assertIn("regional.reward.memory_bottle", result["state"]["inventory"])
        self.assertIn("canon.npc.lumia_seir", result["state"]["bonds"])
        self.assertTrue(result["state"]["world_flags"]["lumia_recognizes_player"])
        self.assertTrue(any(key.startswith("regional-reward:") for key, _, _ in result["receipts"]))

    def test_sandsea_wage_and_academy_completion_requirements(self):
        registry = ContentRegistry(API_DIR)
        for quest_id in ("regional_main.song_of_sandsea", "regional_main.grand_academy_first_day"):
            quest = next(item for item in registry.quests if item["id"] == quest_id)
            character = {"id": "character", "candidate_id": "candidate", "data": {
                "identity": {"talent": "", "race_id": "human"}, "current_location_id": quest["roots"][0],
                "attributes": {key: {"value": 50, "reason": ""} for key in ("con", "int", "cha")},
                "resources": {key: {"current": 100, "max": 100, "reason": ""} for key in ("hp", "mp", "sp", "st")},
                "rank": 3, "exp": 0}}
            state = initial_story_state(character, {"narration": {}}, registry.revision_id, registry.quests)
            state["regional_quests"][quest_id]["status"] = "active"
            response = gm_response("turn")
            if quest_id.endswith("song_of_sandsea"):
                response["narrative"]["body"] = "商队抵达熔脊龙谷，任务完成。"
                nodes = ["熔脊龙谷"]
            else:
                response["narrative"]["body"] = "选择学院后分配宿舍并取得学生卡，任务完成。"
                nodes = ["选择学院", "宿舍", "学生卡"]
            response["proposals"]["quests"] = [{"operation": "transition", "quest_id": quest_id,
                "name": quest["name"], "description": quest["description"], "status": "completed",
                "progress": "完成", "objectives": [], "quest_kind": "regional", "target_rank": None,
                "action_evidence": "完成", "necessary_nodes": nodes, "reason": "完成", "evidence": "任务完成"}]
            with self.subTest(quest=quest_id), self.assertRaises(ContractError):
                adjudicate(state, validate_gm_response(response), canonical_location_map(), {quest_id},
                           {quest_id: {"context_eligibility": "persistent_active"}}, {}, {quest_id: quest})

    def test_regional_terminal_paths_require_task_specific_evidence(self):
        registry = ContentRegistry(API_DIR)
        for quest in registry.quests:
            character = {"id": "character", "candidate_id": "candidate", "data": {
                "identity": {"talent": "", "race_id": "human"}, "current_location_id": quest["roots"][0],
                "attributes": {key: {"value": 50, "reason": ""} for key in ("con", "int", "cha")},
                "resources": {key: {"current": 100, "max": 100, "reason": ""} for key in ("hp", "mp", "sp", "st")},
                "rank": 3, "exp": 0}}
            state = initial_story_state(character, {"narration": {}}, registry.revision_id, registry.quests)
            state["regional_quests"][quest["id"]]["status"] = "active"
            response = gm_response("turn"); response["narrative"]["body"] = "任务失败。"
            response["proposals"]["quests"] = [{"operation": "transition", "quest_id": quest["id"],
                "name": quest["name"], "description": quest["description"], "status": "failed",
                "progress": "失败", "objectives": [], "quest_kind": "regional", "target_rank": None,
                "action_evidence": "不明原因", "necessary_nodes": [], "reason": "失败", "evidence": "任务失败"}]
            with self.subTest(quest=quest["id"]), self.assertRaises(ContractError):
                adjudicate(state, validate_gm_response(response), canonical_location_map(), {quest["id"]},
                           {quest["id"]: {"context_eligibility": "persistent_active"}}, {},
                           {quest["id"]: quest})

    def test_all_regional_rewards_and_conditional_flight_device_are_frozen(self):
        registry = ContentRegistry(API_DIR)
        self.assertEqual(6, len(registry.quests))
        self.assertTrue(all(quest["rewards"]["items"] or quest["rewards"]["world_flags"]
                            for quest in registry.quests))
        walking = next(quest for quest in registry.quests
                       if quest["id"] == "regional_main.walking_with_wind")
        flight = next(item for item in walking["rewards"]["items"]
                      if item["id"] == "regional.reward.basic_flight_device")
        self.assertEqual({"race_not": "featherfolk"}, flight["condition"])

    def test_all_dangerous_start_prerequisites(self):
        cases = (({"race_id": "human"}, "abyssal_tides", {"underwater_breathing", "pressure_protection"}),
                 ({"race_id": "human"}, "dragonvale", {"heat_protection", "environment_protection"}),
                 ({"race_id": "human"}, "elf_forest", {"elf_forest_entry_permission"}),
                 ({"race_id": "sea_folk"}, "abyssal_tides", set()),
                 ({"race_id": "dragonkin"}, "dragonvale", set()),
                 ({"race_id": "elf"}, "elf_forest", set()))
        for identity, location, expected in cases:
            with self.subTest(identity=identity, location=location):
                value = start_prerequisite(identity, location)
                self.assertEqual(expected, set(value["requirements"]))
                self.assertEqual("required" if expected else "satisfied", value["status"])

    def test_memory_recall_is_explainable_and_bounded(self):
        memories = [{"id": f"memory-{index}", "importance": 50 + index,
                     "locations": ["noxvia"] if index == 0 else [],
                     "people": ["莉莉娅"] if index == 1 else [],
                     "keywords": ["承诺"] if index == 2 else [],
                     "unresolved": ["待处理"] if index == 3 else [],
                     "updated_at": str(index)} for index in range(25)]
        recalled = StoryRepository._recall_memories(
            {"location": {"id": "noxvia.street"}},
            [{"title": "莉莉娅", "summary": "提到承诺", "body": ""}], memories)
        self.assertLessEqual(len(recalled), 20)
        self.assertTrue(all(item["recall_reason"] for item in recalled))

    def test_each_regional_quest_transition_requires_location_and_evidence(self):
        registry = ContentRegistry(API_DIR)
        for quest in registry.quests:
            character = {"id": "character", "candidate_id": "candidate", "data": {
                "identity": {"talent": ""}, "current_location_id": "san_velia",
                "attributes": {key: {"value": 50, "reason": ""} for key in ("con", "int", "cha")},
                "resources": {key: {"current": 100, "max": 100, "reason": ""} for key in ("hp", "mp", "sp", "st")},
                "rank": 3, "exp": 0}}
            state = initial_story_state(character, {"narration": {}}, registry.revision_id, registry.quests)
            response = gm_response("turn")
            response["narrative"]["body"] = "角色直接开始地区任务。"
            response["proposals"]["quests"] = [{"operation": "transition", "quest_id": quest["id"],
                "name": quest["name"], "description": quest["description"], "status": "active",
                "progress": "开始", "objectives": [], "quest_kind": "regional", "target_rank": None,
                "action_evidence": "直接开始", "necessary_nodes": [], "reason": "开始",
                "evidence": "开始地区任务"}]
            context = {quest["id"]: {"context_eligibility": "card_only"}}
            with self.subTest(quest=quest["id"]), self.assertRaises(ContractError):
                adjudicate(state, response, canonical_location_map(), {quest["id"]}, context,
                           {"action": "直接开始"})


class PhaseTwoApiTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        static = root / "web"; static.mkdir(); (static / "index.html").write_text("ok")
        self.provider = PhaseTwoProvider()
        self.server = create_server("127.0.0.1", 0, str(root / ".data"), str(static), self.provider)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True); self.thread.start()
        self.url = f"http://127.0.0.1:{self.server.server_port}"
        self.save_id = self._ready_save()

    def tearDown(self):
        self.server.app_context.wait_for_workers()
        self.server.shutdown(); self.server.server_close(); self.thread.join(2); self.tmp.cleanup()

    def request(self, method, path, body=None, expected=200):
        data = json.dumps(body, ensure_ascii=False).encode() if body is not None else None
        request = urllib.request.Request(self.url + path, data=data,
                                         headers={"Content-Type": "application/json"} if data else {}, method=method)
        try:
            with urllib.request.urlopen(request, timeout=4) as response:
                status = response.status; payload = json.loads(response.read())
        except urllib.error.HTTPError as error:
            status = error.code; payload = json.loads(error.read()); error.close()
        self.assertEqual(expected, status, payload); return payload

    def _ready_save(self):
        settings = self.request("GET", "/api/settings")
        self.request("PUT", "/api/settings/model", {"request_id": "settings", "expected_revision": settings["revision"],
                     "base_url": "https://unused.example/v1", "model": "fake", "api_key": "fake"})
        save = self.request("POST", "/api/saves", {"name": "阶段二", "request_id": "save"}, 201)
        draft = {"request_id": "draft", "draft_revision": 0, "expected_save_revision": 0,
                 "current_step": 13, "race_id": "human", "race_branch_id": None, "name": "艾琳",
                 "gender": "女", "age": 24, "appearance": "黑发", "personality": "沉着", "rank": 3,
                 "talent": "魔力感知", "background": "旅行者", "location_id": "grand_academy", "additional": ""}
        saved = self.request("PUT", f"/api/saves/{save['id']}/character-draft", draft)
        current = self.request("GET", f"/api/saves/{save['id']}")
        job = self.request("POST", f"/api/saves/{save['id']}/character-generations",
                           {"request_id": "gen", "draft_revision": saved["draft_revision"],
                            "expected_save_revision": current["revision"], "feedback": ""}, 202)
        self.wait_job(save["id"], job["id"], "character-generations")
        candidate = self.request("GET", f"/api/saves/{save['id']}/character-candidate")
        current = self.request("GET", f"/api/saves/{save['id']}")
        self.request("POST", f"/api/saves/{save['id']}/character/confirm",
                     {"request_id": "confirm", "candidate_id": candidate["id"],
                      "expected_save_revision": current["revision"],
                      "expected_draft_revision": saved["draft_revision"]})
        return save["id"]

    def wait_job(self, save_id, job_id, path="narrative-jobs"):
        for _ in range(200):
            job = self.request("GET", f"/api/saves/{save_id}/{path}/{job_id}")
            if job["status"] in {"succeeded", "failed", "stale", "cancelled"}: return job
            time.sleep(.01)
        self.fail("job timeout")

    def test_initialization_opening_turn_idempotency_and_projections(self):
        bootstrap = self.request("GET", f"/api/saves/{self.save_id}/game-bootstrap")
        state = bootstrap["story"]["state"]
        self.assertEqual({}, state["inventory"]); self.assertEqual(0, state["currency_copper"])
        self.assertEqual([], state["character"]["skills"])
        self.assertEqual(tuple(REPUTATION_KEYS), tuple(state["reputations"]))
        self.assertTrue(all(item["value"] == 0 for item in state["reputations"].values()))
        self.provider.responses.append(gm_response("opening"))
        body = {"request_id": "opening", "expected_state_version": 0, "guidance": ""}
        job = self.request("POST", f"/api/saves/{self.save_id}/story/opening", body, 202)
        repeated = self.request("POST", f"/api/saves/{self.save_id}/story/opening", body)
        self.assertEqual(job["id"], repeated["id"])
        self.assertEqual("succeeded", self.wait_job(self.save_id, job["id"])["status"])
        story = self.request("GET", f"/api/saves/{self.save_id}/story")
        self.assertEqual(1, story["state"]["state_version"])
        self.assertEqual(1, story["latest_turn"]["sequence"])
        reputations = self.request("GET", f"/api/saves/{self.save_id}/reputations")
        self.assertEqual(7, len(reputations["items"]))
        self.assertEqual("continental_overall", reputations["primary_key"])
        system = self.provider.messages[0][0]["content"]
        for doc in self.server.app_context.content_registry.documents:
            if doc["category"] in {"rule", "canon"}:
                self.assertEqual(1, system.count(doc["text_content"]))
        conflict = self.request("POST", f"/api/saves/{self.save_id}/turns",
                                {"request_id": "bad-version", "expected_state_version": 0,
                                 "action": "前进", "option_id": None}, 409)
        self.assertEqual("STATE_VERSION_CONFLICT", conflict["error"]["code"])

    def test_boundaries_completion_and_reshape_rollback(self):
        opening = gm_response("opening")
        opening["narrative"]["body"] = "旅人遭受致命重伤，失去生命。随后有人留下二十枚铜币，任务也随之开始。"
        opening["proposals"]["resources"] = [{"key": "hp", "delta": -500,
                                               "reason": "重伤", "evidence": "失去生命"}]
        opening["proposals"]["currency"] = {"copper_delta": 20, "reason": "拾得", "evidence": "二十枚铜币"}
        opening["proposals"]["quests"] = [{"operation": "create", "quest_id": "quest.test",
            "name": "测试任务", "description": "说明", "status": "active", "progress": "开始",
            "objectives": ["完成"], "quest_kind": "regular", "target_rank": None,
            "action_evidence": "接受任务", "necessary_nodes": [],
            "reason": "接受", "evidence": "任务也随之开始"}]
        self.provider.responses.append(opening)
        job = self.request("POST", f"/api/saves/{self.save_id}/story/opening",
                           {"request_id": "open-boundary", "expected_state_version": 0, "guidance": ""}, 202)
        opening_result = self.wait_job(self.save_id, job["id"])
        self.assertEqual("succeeded", opening_result["status"], opening_result)
        story = self.request("GET", f"/api/saves/{self.save_id}/story")
        self.assertEqual(0, story["state"]["character"]["resources"]["hp"]["current"])
        self.assertFalse(story["state"]["character"]["alive"])
        turn_id = story["latest_turn"]["id"]
        replacement = gm_response("reshape")
        replacement["narrative"]["body"] = "旅人安然无恙，并明确宣布任务完成。"
        replacement["proposals"]["quests"] = [{"operation": "create", "quest_id": "quest.done",
            "name": "已完成", "description": "说明", "status": "completed", "progress": "完成",
            "objectives": [], "quest_kind": "regular", "target_rank": None,
            "action_evidence": "完成任务", "necessary_nodes": [],
            "reason": "完成", "evidence": "任务完成"}]
        self.provider.responses.append(replacement)
        job = self.request("POST", f"/api/saves/{self.save_id}/turns/{turn_id}/reshape",
                           {"request_id": "reshape", "expected_state_version": 1, "guidance": "改写"}, 202)
        arc_result = self.wait_job(self.save_id, job["id"])
        self.assertEqual("succeeded", arc_result["status"], arc_result)
        story = self.request("GET", f"/api/saves/{self.save_id}/story")
        self.assertEqual(100, story["state"]["character"]["resources"]["hp"]["current"])
        self.assertEqual(0, story["state"]["currency_copper"])
        self.assertNotIn("quest.test", story["state"]["quests"])
        quests = self.request("GET", f"/api/saves/{self.save_id}/quests")
        self.assertEqual([], quests["active"]); self.assertNotIn("terminal", quests)
        self.assertEqual(1, len(self.request("GET", f"/api/saves/{self.save_id}/turns")["items"]))

    def test_arc_trigger_core_and_migrations(self):
        db = self.server.app_context.database
        state = self.server.app_context.story.get_state(self.save_id)
        with db.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            now = "2026-09-28T00:00:00+00:00"
            for sequence in range(1, 36):
                turn_id, version_id = f"turn-{sequence}", f"version-{sequence}"
                connection.execute("INSERT INTO turns VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (turn_id, self.save_id, sequence, version_id, "turn", "{}", "标题", "正文", "摘要", "[]", "[]", 0, 1, now, now))
                connection.execute("INSERT INTO turn_snapshots VALUES(?,?,?,?,?)",
                    (turn_id, self.save_id, "turn-snapshot/1", json.dumps({"state": state, "memories": []}), now))
                connection.execute("INSERT INTO turn_versions VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                    (version_id, turn_id, self.save_id, 1, "{}", "{}", "[]",
                     self.server.app_context.content_registry.prompt_version,
                     state["content_revision_id"], "fake", now))
            connection.execute("UPDATE story_states SET current_turn_id='turn-35',state_version=1 WHERE save_id=?",
                               (self.save_id,)); connection.commit()
        job = self.request("POST", f"/api/saves/{self.save_id}/story-arcs",
                           {"request_id": "arc", "expected_state_version": 1}, 202)
        result = self.wait_job(self.save_id, job["id"])
        self.assertEqual("succeeded", result["status"], result)
        memory = self.request("GET", f"/api/saves/{self.save_id}/memory")
        self.assertEqual(1, len(memory["story_arcs"])); self.assertEqual(25, memory["story_arcs"][0]["end_sequence"])
        with db.connect() as connection:
            self.assertEqual([1, 2, 3, 4], [row[0] for row in connection.execute(
                "SELECT version FROM schema_migrations ORDER BY version")])

    def test_v2_export_import_round_trip(self):
        self.provider.responses.append(gm_response("opening"))
        job = self.request("POST", f"/api/saves/{self.save_id}/story/opening",
                           {"request_id": "export-opening", "expected_state_version": 0,
                            "guidance": ""}, 202)
        self.assertEqual("succeeded", self.wait_job(self.save_id, job["id"])["status"])
        exported = self.request("GET", f"/api/saves/{self.save_id}/export")
        self.assertEqual(2, exported["schema_version"])
        self.assertIn("turn_versions", exported["narrative"])
        self.assertTrue(self.request("POST", "/api/saves/import/validate", exported)["valid"])
        imported = self.request("POST", "/api/saves/import",
                                {"request_id": "v2-import", "payload": exported}, 201)
        turns = self.request("GET", f"/api/saves/{imported['id']}/turns")["items"]
        self.assertEqual(1, len(turns)); self.assertEqual("旅程开始", turns[0]["title"])

    def test_empty_summary_fallback_and_warnings_are_committed(self):
        response = gm_response("opening")
        response["narrative"]["chronicle_summary"] = ""
        response["warnings"] = ["需要留意当前风险"]
        self.provider.responses.append(response)
        job = self.request("POST", f"/api/saves/{self.save_id}/story/opening",
                           {"request_id": "fallback-summary", "expected_state_version": 0,
                            "guidance": ""}, 202)
        self.assertEqual("succeeded", self.wait_job(self.save_id, job["id"])["status"])
        story = self.request("GET", f"/api/saves/{self.save_id}/story")
        self.assertTrue(story["latest_turn"]["summary"])
        self.assertTrue(any(change["kind"] == "warning"
                            for change in story["latest_turn"]["authoritative_changes"]))
        with self.server.app_context.database.connect() as connection:
            journal = connection.execute("SELECT fallback_used FROM journals WHERE save_id=?",
                                         (self.save_id,)).fetchone()
        self.assertEqual(1, journal[0])

    def test_five_world_calls_include_all_rules_and_canon(self):
        registry = self.server.app_context.content_registry
        documents = [item for item in registry.documents if item["category"] in {"rule", "canon"}]
        state = self.server.app_context.story.get_state(self.save_id)
        for kind in ("opening", "turn", "intervene", "reshape", "story_arc"):
            contract_kind = "story_arc" if kind == "story_arc" else "gm_turn"
            messages, _ = registry.build_messages(
                state, {"action_type": kind}, [], [], [], [], {}, registry.documents,
                contract_kind, registry.manifest)
            system = messages[0]["content"]
            for document in documents:
                self.assertEqual(1, system.count(document["text_content"]),
                                 f"{kind}: {document['document_id']}")

    def test_portable_import_into_clean_database_and_rejects_damage(self):
        self.provider.responses.append(gm_response("opening"))
        job = self.request("POST", f"/api/saves/{self.save_id}/story/opening",
                           {"request_id": "portable-opening", "expected_state_version": 0,
                            "guidance": ""}, 202)
        self.assertEqual("succeeded", self.wait_job(self.save_id, job["id"])["status"])
        exported = self.request("GET", f"/api/saves/{self.save_id}/export")
        clean_root = Path(self.tmp.name) / "clean"; clean_root.mkdir()
        clean = Database(clean_root / "clean.sqlite3", ContentRegistry(API_DIR))
        revision = exported["narrative"]["content_revision"]["id"]
        with clean.connect() as connection:
            connection.execute("DELETE FROM content_revision_documents WHERE revision_id=?", (revision,))
            connection.execute("DELETE FROM content_revisions WHERE id=?", (revision,))
        pending = clean.import_save({"request_id": "portable-clean", "payload": exported})
        self.assertEqual("pending", pending["status"])
        imported = clean.trust_and_import(pending["pending_import_id"], {
            "request_id": "trust-portable", "confirm_revision_id": revision, "confirm": True})
        with clean.connect() as connection:
            self.assertIsNotNone(connection.execute(
                "SELECT 1 FROM content_revisions WHERE id=?", (revision,)).fetchone())
        self.assertEqual("ready", imported["phase"])
        malformed = copy.deepcopy(exported)
        malformed["narrative"]["story_state"]["state_json"]["reputations"]["unknown"] = {
            "key": "unknown", "value": 0, "level": "中立"}
        with self.assertRaises(DomainError):
            clean.import_save({"request_id": "bad-reputation", "payload": malformed})
        broken = copy.deepcopy(exported)
        broken["narrative"]["turns"][0]["current_version_id"] = "missing-version"
        with self.assertRaises(DomainError):
            clean.import_save({"request_id": "bad-reference", "payload": broken})
        tampered_content = copy.deepcopy(exported)
        tampered_content["narrative"]["content_revision"]["documents"][0]["text_content"] += "篡改"
        with self.assertRaises(DomainError):
            clean.import_save({"request_id": "bad-content", "payload": tampered_content})
        power_tamper = copy.deepcopy(exported)
        power_tamper["narrative"]["story_state"]["state_json"]["character"]["effective_power"] = 999999
        power_tamper["narrative"]["story_state"]["state_json"]["character"]["alive"] = False
        power_tamper["narrative"]["story_state"]["state_json"]["reputations"]["continental_overall"]["level"] = "伪造"
        with clean.connect() as connection:
            connection.execute("DELETE FROM trusted_content_revisions WHERE revision_id=?", (revision,))
        pending_power = clean.import_save({"request_id": "derive-power", "payload": power_tamper})
        restored = clean.trust_and_import(pending_power["pending_import_id"], {
            "request_id": "trust-derived", "confirm_revision_id": revision, "confirm": True})
        with clean.connect() as connection:
            imported_state = json.loads(connection.execute(
                "SELECT state_json FROM story_states WHERE save_id=?", (restored["id"],)).fetchone()[0])
        self.assertNotEqual(999999, imported_state["character"]["effective_power"])
        self.assertTrue(imported_state["character"]["alive"])
        self.assertEqual("中立", imported_state["reputations"]["continental_overall"]["level"])
        for mutate in ("equipment", "modifier", "skills"):
            malicious = copy.deepcopy(exported)
            imported_story = malicious["narrative"]["story_state"]["state_json"]
            if mutate == "equipment":
                imported_story["inventory"]["item.million"] = {"id": "item.million", "name": "恶意装备",
                    "description": "", "quantity": 1, "power": 1000000, "equipped": True, "source": "attack"}
            elif mutate == "modifier":
                imported_story["character"]["power_modifiers"] = [{"id": "million", "value": 1000000,
                    "reason": "任意", "temporary": False, "category": "other", "severity": "minor",
                    "canonical_exception": None}]
            else:
                imported_story["character"]["skills"] = [{"id": 123, "name": "坏技能",
                                                            "description": "", "source": ""}]
            with self.subTest(mutate=mutate), self.assertRaises(DomainError):
                clean.import_save({"request_id": "malicious-" + mutate, "payload": malicious})

    def test_imported_dangerous_start_is_rederived_and_blocks_opening(self):
        self.request("GET", f"/api/saves/{self.save_id}/game-bootstrap")
        exported = self.request("GET", f"/api/saves/{self.save_id}/export")
        narrative = exported["narrative"]
        state = narrative["story_state"]["state_json"]
        state["character"]["identity"]["race_id"] = "human"
        state["location"] = {"id": "abyssal_tides", "name": "沧渊城", "safeguards": [],
                             "legacy_start_protection": False,
                             "prerequisite": {"status": "satisfied", "requirements": [],
                                              "resolution": None, "options": []}}
        narrative["location_nodes"] = [row for row in narrative["location_nodes"]
                                        if row["id"] != "abyssal_tides"] + [{
            "save_id": self.save_id, "id": "abyssal_tides", "name": "沧渊城",
            "location_type": "city", "parent_id": None, "region_id": "abyssal_tides",
            "description": "深海", "canonical": 1, "created_turn_version_id": None}]
        imported = self.server.app_context.database.import_save({
            "request_id": "danger-import", "payload": exported})
        story = self.request("GET", f"/api/saves/{imported['id']}/story")
        self.assertEqual("required", story["start_prerequisite"]["status"])
        blocked = self.request("POST", f"/api/saves/{imported['id']}/story/opening", {
            "request_id": "danger-import-opening", "expected_state_version": 0,
            "guidance": ""}, 409)
        self.assertEqual("START_LOCATION_PREREQUISITE_REQUIRED", blocked["error"]["code"])
        forged = copy.deepcopy(exported)
        forged_state = forged["narrative"]["story_state"]["state_json"]
        forged_state["character"]["identity"]["race_id"] = "human"
        forged_state["location"] = {"id": "abyssal_tides", "name": "沧渊城", "safeguards": [],
            "legacy_start_protection": True,
            "prerequisite": {"status": "satisfied", "requirements": [],
                             "resolution": "accept_legacy_protection", "options": []}}
        forged_state["world_flags"]["legacy_start_prerequisites"] = {
            "location_id": "abyssal_tides", "grants": ["underwater_breathing"], "source": "伪造"}
        forged["narrative"]["location_nodes"] = narrative["location_nodes"]
        with self.assertRaises(DomainError):
            self.server.app_context.database.import_save({"request_id": "forged-start", "payload": forged})

    def test_import_rejects_inapplicable_canonical_power_exception(self):
        self.request("GET", f"/api/saves/{self.save_id}/game-bootstrap")
        exported = self.request("GET", f"/api/saves/{self.save_id}/export")
        state = exported["narrative"]["story_state"]["state_json"]
        state["character"]["power_modifiers"] = [{"id": "false-sea-bonus", "value": 500,
            "reason": "伪造海族深海加成", "temporary": False, "category": "environment",
            "severity": "major", "canonical_exception": "canon:sea_folk_deep_sea"}]
        with self.assertRaisesRegex(DomainError, "不适用"):
            self.server.app_context.database.import_save({
                "request_id": "inapplicable-canon-import", "payload": exported})

    def test_portable_dynamic_entity_maps_round_trip(self):
        self.provider.responses.append(gm_response("opening"))
        opening = self.request("POST", f"/api/saves/{self.save_id}/story/opening",
                               {"request_id": "maps-opening", "expected_state_version": 0,
                                "guidance": ""}, 202)
        self.assertEqual("succeeded", self.wait_job(self.save_id, opening["id"])["status"])
        turn_id = self.request("GET", f"/api/saves/{self.save_id}/story")["latest_turn"]["id"]
        self.provider.responses.append(gm_response("reshape"))
        reshape = self.request("POST", f"/api/saves/{self.save_id}/turns/{turn_id}/reshape",
                               {"request_id": "maps-reshape", "expected_state_version": 1,
                                "guidance": "保留平静开场"}, 202)
        self.assertEqual("succeeded", self.wait_job(self.save_id, reshape["id"])["status"])
        story = self.server.app_context.story.get_state(self.save_id)
        dynamic_id, item_id, quest_id, npc_id = "dynamic.portable", "item.portable", "quest.portable", "npc.portable"
        story["locations"][dynamic_id] = {"id": dynamic_id, "name": "动态营地", "type": "camp",
            "parent_id": "grand_academy", "region_id": "grand_academy", "description": "营地",
            "canonical": False, "created_turn_version_id": None}
        story["inventory"][item_id] = {"id": item_id, "name": "旅行包", "description": "用品",
            "quantity": 1, "power": 5, "equipped": True, "source": "test"}
        story["quests"][quest_id] = {"id": quest_id, "name": "动态任务", "description": "测试",
            "status": "active", "progress": "开始", "objectives": [], "regional": False,
            "quest_kind": "regular", "target_rank": None, "consumed": False, "necessary_nodes": []}
        story["bonds"][npc_id] = {"id": "bond.portable", "npc_id": npc_id, "npc_name": "旅伴",
            "value": 35, "level": "伪造", "relation_type": "friend", "listed": True}
        with self.server.app_context.database.connect() as connection:
            connection.execute("UPDATE story_states SET state_json=? WHERE save_id=?",
                               (json.dumps(story, ensure_ascii=False), self.save_id))
            connection.execute("INSERT INTO location_nodes VALUES(?,?,?,?,?,?,?,?,?)",
                (self.save_id, dynamic_id, "动态营地", "camp", "grand_academy", "grand_academy",
                 "营地", 0, None))
        exported = self.request("GET", f"/api/saves/{self.save_id}/export")
        clean = Database(Path(self.tmp.name) / "portable-map.sqlite3", ContentRegistry(API_DIR))
        revision = exported["narrative"]["content_revision_id"]
        with clean.connect() as connection:
            connection.execute("DELETE FROM trusted_content_revisions WHERE revision_id=?", (revision,))
        pending = clean.import_save({"request_id": "maps", "payload": exported})
        imported = clean.trust_and_import(pending["pending_import_id"], {
            "request_id": "trust-maps", "confirm_revision_id": revision, "confirm": True})
        with clean.connect() as connection:
            restored = json.loads(connection.execute(
                "SELECT state_json FROM story_states WHERE save_id=?", (imported["id"],)).fetchone()[0])
        for map_name in ("locations", "inventory", "quests"):
            self.assertTrue(all(key == value["id"] for key, value in restored[map_name].items()))
        self.assertTrue(all(key == value["npc_id"] for key, value in restored["bonds"].items()))
        self.assertEqual("友好", next(iter(restored["bonds"].values()))["level"])
        self.assertEqual(5, restored["character"]["equipment_power"])
        with clean.connect() as connection:
            self.assertEqual(2, connection.execute(
                "SELECT COUNT(*) FROM turn_versions WHERE save_id=?", (imported["id"],)).fetchone()[0])

    def test_snapshot_import_rejects_tamper_and_remaps_dynamic_maps(self):
        self.provider.responses.append(gm_response("opening"))
        opening = self.request("POST", f"/api/saves/{self.save_id}/story/opening",
                               {"request_id": "snapshot-opening", "expected_state_version": 0,
                                "guidance": ""}, 202)
        self.assertEqual("succeeded", self.wait_job(self.save_id, opening["id"])["status"])
        exported = self.request("GET", f"/api/saves/{self.save_id}/export")
        snapshot = exported["narrative"]["turn_snapshots"][0]["state_json"]["state"]
        snapshot["npcs"]["npc.snapshot"] = {"id": "npc.snapshot", "name": "旧识",
            "description": "快照NPC", "source": "test"}
        snapshot["locations"]["dynamic.snapshot"] = {"id": "dynamic.snapshot", "name": "旧营地",
            "type": "camp", "parent_id": "grand_academy", "region_id": "grand_academy",
            "description": "快照地点", "canonical": False, "created_turn_version_id": None}
        snapshot["inventory"]["item.snapshot"] = {"id": "item.snapshot", "name": "旧物",
            "description": "快照物品", "quantity": 1, "power": 0, "equipped": False, "source": "test"}
        snapshot["quests"]["quest.snapshot"] = {"id": "quest.snapshot", "name": "旧任务",
            "description": "", "status": "active", "progress": "", "objectives": [], "regional": False,
            "quest_kind": "regular", "target_rank": None, "consumed": False, "necessary_nodes": []}
        snapshot["bonds"]["npc.snapshot"] = {"id": "bond.snapshot", "npc_id": "npc.snapshot",
            "npc_name": "旧识", "value": 25, "level": "友好", "relation_type": "friend", "listed": True}
        tampered = copy.deepcopy(exported)
        tampered["narrative"]["turn_snapshots"][0]["state_json"]["state"]["inventory"][
            "item.bad"] = {"id": "item.bad", "name": "恶意", "description": "", "quantity": 1,
                           "power": 1000000, "equipped": True, "source": "attack"}
        with self.assertRaises(DomainError):
            self.server.app_context.database.import_save({"request_id": "bad-snapshot", "payload": tampered})
        clean = Database(Path(self.tmp.name) / "snapshot.sqlite3", ContentRegistry(API_DIR))
        revision = exported["narrative"]["content_revision_id"]
        with clean.connect() as connection:
            connection.execute("DELETE FROM trusted_content_revisions WHERE revision_id=?", (revision,))
        pending = clean.import_save({"request_id": "good-snapshot", "payload": exported})
        imported = clean.trust_and_import(pending["pending_import_id"], {
            "request_id": "trust-snapshot", "confirm_revision_id": revision, "confirm": True})
        with clean.connect() as connection:
            stored = json.loads(connection.execute(
                "SELECT state_json FROM turn_snapshots WHERE save_id=?", (imported["id"],)).fetchone()[0])
        frozen = stored["state"]
        self.assertTrue(all(key == value["id"] for key, value in frozen["npcs"].items()))
        self.assertTrue(all(key == value["id"] for key, value in frozen["locations"].items()))
        self.assertTrue(all(key == value["npc_id"] for key, value in frozen["bonds"].items()))
        repository = StoryRepository(clean, ContentRegistry(API_DIR))
        imported_state = repository.get_state(imported["id"])
        reshape_job, _ = repository.create_job(imported["id"], "reshape", {
            "request_id": "imported-snapshot-reshape",
            "expected_state_version": imported_state["state_version"],
            "guidance": "从导入快照重塑"}, imported_state["current_turn_id"])
        claimed = repository.claim(imported["id"], reshape_job["id"])
        self.assertEqual("succeeded", repository.complete_turn(claimed, gm_response("reshape")))
        restored_state = repository.get_state(imported["id"])
        self.assertTrue(any(item["name"] == "旧营地" for item in restored_state["locations"].values()))
        self.assertTrue(any(item["name"] == "旧识" for item in restored_state["npcs"].values()))

    def test_unknown_revision_requires_explicit_trust_http(self):
        self.provider.responses.append(gm_response("opening"))
        job = self.request("POST", f"/api/saves/{self.save_id}/story/opening",
                           {"request_id": "pending-opening", "expected_state_version": 0,
                            "guidance": ""}, 202)
        self.assertEqual("succeeded", self.wait_job(self.save_id, job["id"])["status"])
        exported = self.request("GET", f"/api/saves/{self.save_id}/export")
        revision = exported["narrative"]["content_revision_id"]
        with self.server.app_context.database.connect() as connection:
            connection.execute("DELETE FROM trusted_content_revisions WHERE revision_id=?", (revision,))
        pending = self.request("POST", "/api/imports", {
            "request_id": "pending-http", "payload": exported}, 202)
        self.assertEqual("pending", pending["status"])
        self.assertTrue(pending["confirmation_required"])
        repeated = self.request("POST", "/api/imports", {
            "request_id": "pending-http", "payload": exported}, 202)
        self.assertEqual(pending["pending_import_id"], repeated["pending_import_id"])
        imported = self.request("POST", f"/api/imports/{pending['pending_import_id']}/trust-and-import", {
            "request_id": "trust-http", "confirm_revision_id": revision, "confirm": True}, 201)
        again = self.request("POST", f"/api/imports/{pending['pending_import_id']}/trust-and-import", {
            "request_id": "trust-http", "confirm_revision_id": revision, "confirm": True}, 201)
        self.assertEqual(imported["id"], again["id"])
        with self.server.app_context.database.connect() as connection:
            connection.execute("DELETE FROM trusted_content_revisions WHERE revision_id=?", (revision,))
        expiring = self.request("POST", "/api/imports", {
            "request_id": "expiring-http", "payload": exported}, 202)
        with self.server.app_context.database.connect() as connection:
            connection.execute("UPDATE pending_imports SET expires_at='2000-01-01T00:00:00+00:00' WHERE id=?",
                               (expiring["pending_import_id"],))
        expired = self.request("POST", f"/api/imports/{expiring['pending_import_id']}/trust-and-import", {
            "request_id": "trust-expired", "confirm_revision_id": revision, "confirm": True}, 409)
        self.assertEqual("PENDING_IMPORT_EXPIRED", expired["error"]["code"])

    def test_large_import_endpoint_and_validate(self):
        self.provider.responses.append(gm_response("opening"))
        job = self.request("POST", f"/api/saves/{self.save_id}/story/opening",
                           {"request_id": "large-opening", "expected_state_version": 0,
                            "guidance": ""}, 202)
        self.assertEqual("succeeded", self.wait_job(self.save_id, job["id"])["status"])
        exported = self.request("GET", f"/api/saves/{self.save_id}/export")
        preview = self.request("POST", "/api/imports/validate", exported)
        self.assertTrue(preview["valid"])
        request = urllib.request.Request(self.url + "/api/imports", data=json.dumps(exported).encode(),
            headers={"Content-Type": "application/json", "X-Request-Id": "large-direct"}, method="POST")
        with urllib.request.urlopen(request, timeout=4) as response:
            self.assertIn(response.status, {201, 202})
            result = json.loads(response.read())
        self.assertIn(result.get("status", "imported"), {"pending", "imported"})

    def test_reshape_context_and_rolls_back_memory_location_reputation(self):
        opening = gm_response("opening")
        opening["narrative"]["body"] = "旅人进入月灯小巷，公开救助居民并获得声望。旅人作出重要承诺，此事仍待履行。"
        opening["scene"]["new_locations"] = [{"ref": "location:new:1", "name": "月灯小巷",
            "type": "street", "parent_id": "grand_academy", "region_id": "grand_academy",
            "description": "安静的小巷", "reason": "进入小巷"}]
        opening["scene"]["location"] = {"operation": "move", "location_id": None,
                                           "location_ref": "location:new:1", "reason": "进入小巷"}
        opening["proposals"]["reputations"] = [{"key": "continental_overall", "delta": 5,
            "public_reason": "公开救助居民", "evidence": "公开救助居民"}]
        opening["memory_candidates"] = [{"operation": "create", "memory_id": None, "kind": "promise",
            "summary": "重要承诺", "importance": 80, "people": [], "locations": [],
            "keywords": ["承诺"], "facts": ["旅人作出重要承诺"], "unresolved": [], "reason": "重要",
            "evidence": "旅人作出重要承诺"}]
        self.provider.responses.append(opening)
        job = self.request("POST", f"/api/saves/{self.save_id}/story/opening",
                           {"request_id": "rollback-opening", "expected_state_version": 0,
                            "guidance": ""}, 202)
        self.assertEqual("succeeded", self.wait_job(self.save_id, job["id"])["status"])
        first_context = json.loads(self.provider.messages[-1][1]["content"])
        self.assertEqual(["active_narration", "regional_quests", "story_arcs", "early_summaries",
                          "long_term_memories", "recent_full_turns", "authoritative_state",
                          "current_action", "output_contract_reminder"], list(first_context))
        story = self.request("GET", f"/api/saves/{self.save_id}/story")
        turn_id = story["latest_turn"]["id"]
        replacement = gm_response("reshape")
        self.provider.responses.append(replacement)
        job = self.request("POST", f"/api/saves/{self.save_id}/turns/{turn_id}/reshape",
                           {"request_id": "rollback-reshape", "expected_state_version": 1,
                            "guidance": "不要进入小巷"}, 202)
        self.assertEqual("succeeded", self.wait_job(self.save_id, job["id"])["status"])
        context = json.loads(self.provider.messages[-1][1]["content"])
        self.assertIn("original_action", context["current_action"])
        self.assertIn("old_result", context["current_action"])
        self.assertEqual("不要进入小巷", context["current_action"]["reshape_guidance"])
        story = self.request("GET", f"/api/saves/{self.save_id}/story")
        self.assertEqual("grand_academy", story["state"]["location"]["id"])
        self.assertEqual(0, story["state"]["reputations"]["continental_overall"]["value"])
        self.assertEqual([], self.request("GET", f"/api/saves/{self.save_id}/memories")["items"])
        with self.server.app_context.database.connect() as connection:
            self.assertEqual(0, connection.execute(
                "SELECT COUNT(*) FROM location_nodes WHERE save_id=? AND canonical=0", (self.save_id,)).fetchone()[0])
            self.assertEqual(0, connection.execute(
                "SELECT COUNT(*) FROM reputation_change_history WHERE save_id=?", (self.save_id,)).fetchone()[0])

    def test_dynamic_npc_persists_then_bond_memory_and_reshape(self):
        opening = gm_response("opening")
        opening["narrative"]["body"] = "旅人初遇名为诺兰的旅者。"
        opening["scene"]["new_npcs"] = [{"ref": "npc:new:1", "name": "诺兰",
                                           "description": "旅行者", "reason": "初次相遇"}]
        self.provider.responses.append(opening)
        job = self.request("POST", f"/api/saves/{self.save_id}/story/opening",
                           {"request_id": "npc-opening", "expected_state_version": 0, "guidance": ""}, 202)
        self.assertEqual("succeeded", self.wait_job(self.save_id, job["id"])["status"])
        story = self.request("GET", f"/api/saves/{self.save_id}/story")
        npc_id = next(iter(story["state"]["npcs"]))
        self.assertEqual({}, story["state"]["bonds"])
        follow = gm_response("turn"); follow["narrative"]["body"] = "诺兰决定长期同行，双方建立羁绊。"
        follow["proposals"]["bonds"] = [{"operation": "create_or_join", "npc_id": npc_id,
            "npc_ref": None, "npc_name": "诺兰", "delta": 5, "relation_type": "companion",
            "admission": "likely_recurring", "reason": "长期同行", "evidence": "建立羁绊"}]
        follow["memory_candidates"] = [{"operation": "create", "memory_id": None, "kind": "person",
            "summary": "诺兰成为同行者", "importance": 70, "people": [npc_id], "locations": [],
            "keywords": ["诺兰"], "facts": ["诺兰决定长期同行"], "unresolved": [], "reason": "持续关系",
            "evidence": "诺兰决定长期同行"}]
        self.provider.responses.append(follow)
        turn = self.request("POST", f"/api/saves/{self.save_id}/turns", {
            "request_id": "npc-turn", "expected_state_version": 1, "action": "邀请诺兰同行",
            "option_id": None}, 202)
        self.assertEqual("succeeded", self.wait_job(self.save_id, turn["id"])["status"])
        current = self.request("GET", f"/api/saves/{self.save_id}/story")
        self.assertIn(npc_id, current["state"]["bonds"])
        self.assertEqual(npc_id, self.request("GET", f"/api/saves/{self.save_id}/memories")["items"][0]["people"][0])
        replacement = gm_response("reshape"); self.provider.responses.append(replacement)
        reshape = self.request("POST", f"/api/saves/{self.save_id}/turns/{current['latest_turn']['id']}/reshape", {
            "request_id": "npc-reshape", "expected_state_version": 2, "guidance": "不邀请同行"}, 202)
        self.assertEqual("succeeded", self.wait_job(self.save_id, reshape["id"])["status"])
        reshaped = self.request("GET", f"/api/saves/{self.save_id}/story")["state"]
        self.assertIn(npc_id, reshaped["npcs"])
        self.assertNotIn(npc_id, reshaped["bonds"])

    def test_new_npc_memory_ref_is_stabilized_and_opening_reshape_removes_npc(self):
        opening = gm_response("opening"); opening["narrative"]["body"] = "旅人初遇诺兰并记住此人。"
        opening["scene"]["new_npcs"] = [{"ref": "npc:new:1", "name": "诺兰",
                                           "description": "旅行者", "reason": "初遇"}]
        opening["memory_candidates"] = [{"operation": "create", "memory_id": None, "kind": "person",
            "summary": "初遇诺兰", "importance": 60, "people": ["npc:new:1"], "locations": [],
            "keywords": ["诺兰"], "facts": ["旅人初遇诺兰并记住此人"], "unresolved": [], "reason": "重要人物",
            "evidence": "旅人初遇诺兰并记住此人"}]
        self.provider.responses.append(opening)
        job = self.request("POST", f"/api/saves/{self.save_id}/story/opening", {
            "request_id": "npc-memory-opening", "expected_state_version": 0, "guidance": ""}, 202)
        self.assertEqual("succeeded", self.wait_job(self.save_id, job["id"])["status"])
        state = self.request("GET", f"/api/saves/{self.save_id}/story")
        npc_id = next(iter(state["state"]["npcs"]))
        self.assertEqual(npc_id, self.request("GET", f"/api/saves/{self.save_id}/memories")["items"][0]["people"][0])
        self.provider.responses.append(gm_response("reshape"))
        reshape = self.request("POST", f"/api/saves/{self.save_id}/turns/{state['latest_turn']['id']}/reshape", {
            "request_id": "npc-memory-reshape", "expected_state_version": 1, "guidance": "不遇见诺兰"}, 202)
        self.assertEqual("succeeded", self.wait_job(self.save_id, reshape["id"])["status"])
        self.assertEqual({}, self.request("GET", f"/api/saves/{self.save_id}/story")["state"]["npcs"])

    def test_arc_job_does_not_block_turn_and_cancel_finishes(self):
        db = self.server.app_context.database; story = self.server.app_context.story
        state = story.get_state(self.save_id)
        with db.connect() as connection:
            connection.execute("BEGIN IMMEDIATE"); now = "2026-09-28T00:00:00+00:00"
            for sequence in range(1, 36):
                turn_id, version_id = f"parallel-turn-{sequence}", f"parallel-version-{sequence}"
                connection.execute("INSERT INTO turns VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (turn_id, self.save_id, sequence, version_id, "turn", "{}", "标题", "正文", "摘要", "[]", "[]", 0, 1, now, now))
                connection.execute("INSERT INTO turn_snapshots VALUES(?,?,?,?,?)",
                    (turn_id, self.save_id, "turn-snapshot/1", json.dumps({"state": state, "memories": []}), now))
                connection.execute("INSERT INTO turn_versions VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                    (version_id, turn_id, self.save_id, 1, "{}", "{}", "[]",
                     self.server.app_context.content_registry.prompt_version, state["content_revision_id"], "fake", now))
            connection.execute("UPDATE story_states SET current_turn_id='parallel-turn-35',state_version=1 WHERE save_id=?",
                               (self.save_id,)); connection.commit()
        arc, _ = story.create_arc_job(self.save_id, {"request_id": "parallel-arc", "expected_state_version": 1})
        turn, created = story.create_job(self.save_id, "turn", {"request_id": "parallel-turn",
                                                                  "expected_state_version": 1,
                                                                  "action": "继续", "option_id": None})
        self.assertTrue(created); self.assertEqual("queued", turn["status"])
        claimed = story.claim(self.save_id, arc["id"])
        story.cancel(self.save_id, arc["id"], {"request_id": "cancel-arc", "expected_state_version": 1})
        result = story.complete_arc(claimed, {"schema_version": "story-arc/1", "title": "弧",
                                               "summary": "摘要", "key_events": [], "unresolved": []})
        self.assertEqual("cancelled", result)
        self.assertEqual("cancelled", story.get_job(self.save_id, arc["id"])["status"])

    def test_turn_version_uses_frozen_prompt_version(self):
        self.request("GET", f"/api/saves/{self.save_id}/game-bootstrap")
        frozen_version = "frozen-prompt-test"
        with self.server.app_context.database.connect() as connection:
            row = connection.execute("SELECT content_revision_id FROM story_states WHERE save_id=?",
                                     (self.save_id,)).fetchone()
            revision = row["content_revision_id"]
            manifest = json.loads(connection.execute(
                "SELECT manifest_json FROM content_revisions WHERE id=?", (revision,)).fetchone()[0])
            manifest["prompt_version"] = frozen_version
            connection.execute("UPDATE content_revisions SET manifest_json=? WHERE id=?",
                               (json.dumps(manifest, ensure_ascii=False, separators=(",", ":")), revision))
        self.provider.responses.append(gm_response("opening"))
        job = self.request("POST", f"/api/saves/{self.save_id}/story/opening",
                           {"request_id": "frozen-version", "expected_state_version": 0,
                            "guidance": ""}, 202)
        self.assertEqual("succeeded", self.wait_job(self.save_id, job["id"])["status"])
        with self.server.app_context.database.connect() as connection:
            stored = connection.execute(
                "SELECT prompt_version FROM turn_versions WHERE save_id=?", (self.save_id,)).fetchone()[0]
        self.assertEqual(frozen_version, stored)

    def test_dangerous_start_requires_explicit_resolution(self):
        db = self.server.app_context.database
        with db.connect() as connection:
            row = connection.execute("SELECT data_json FROM characters WHERE save_id=?",
                                     (self.save_id,)).fetchone()
            character = json.loads(row[0]); character["current_location_id"] = "abyssal_tides"
            character["start_location_id"] = "abyssal_tides"
            character["identity"]["start_location_id"] = "abyssal_tides"
            connection.execute("DELETE FROM story_states WHERE save_id=?", (self.save_id,))
            connection.execute("UPDATE characters SET data_json=? WHERE save_id=?",
                               (json.dumps(character, ensure_ascii=False), self.save_id))
        story = self.request("GET", f"/api/saves/{self.save_id}/story")
        self.assertEqual("required", story["start_prerequisite"]["status"])
        blocked = self.request("POST", f"/api/saves/{self.save_id}/story/opening",
                               {"request_id": "blocked", "expected_state_version": 0,
                                "guidance": ""}, 409)
        self.assertEqual("START_LOCATION_PREREQUISITE_REQUIRED", blocked["error"]["code"])
        resolved = self.request("POST", f"/api/saves/{self.save_id}/story/start-prerequisite", {
            "request_id": "resolve-start", "expected_state_version": 0,
            "resolution": "accept_legacy_protection", "location_id": None})
        self.assertTrue(resolved["location"]["legacy_start_protection"])
        self.provider.responses.append(gm_response("opening"))
        job = self.request("POST", f"/api/saves/{self.save_id}/story/opening",
                           {"request_id": "after-resolution", "expected_state_version": 1,
                            "guidance": ""}, 202)
        self.assertEqual("succeeded", self.wait_job(self.save_id, job["id"])["status"])

    def test_dynamic_location_inherits_local_reputation(self):
        state = self.server.app_context.story.get_state(self.save_id)
        dynamic_id = "dynamic.noxvia.test"
        with self.server.app_context.database.connect() as connection:
            connection.execute("INSERT INTO location_nodes VALUES(?,?,?,?,?,?,?,?,?)",
                (self.save_id, dynamic_id, "北街小店", "shop", "noxvia.street", "noxvia",
                 "动态地点", 0, None))
            state["location"] = {"id": dynamic_id, "name": "北街小店", "safeguards": [],
                                 "legacy_start_protection": False,
                                 "prerequisite": {"status": "satisfied", "requirements": [],
                                                  "resolution": None, "options": []}}
            connection.execute("UPDATE story_states SET state_json=? WHERE save_id=?",
                               (json.dumps(state, ensure_ascii=False), self.save_id))
        projection = self.request("GET", f"/api/saves/{self.save_id}/reputations")
        self.assertEqual("court_of_veiled_night", projection["local_modifier_key"])

    def test_pagination_and_query_whitelist(self):
        state = self.server.app_context.story.get_state(self.save_id)
        now = "2026-09-28T00:00:00+00:00"
        with self.server.app_context.database.connect() as connection:
            for sequence in range(1, 4):
                turn_id, version_id = f"page-turn-{sequence}", f"page-version-{sequence}"
                connection.execute("INSERT INTO turns VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (turn_id, self.save_id, sequence, version_id, "turn", "{}", "标题", "正文", "摘要",
                     "[]", "[]", 0, 1, now, now))
                connection.execute("INSERT INTO turn_versions VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                    (version_id, turn_id, self.save_id, 1, "{}", "{}", "[]",
                     self.server.app_context.content_registry.prompt_version,
                     state["content_revision_id"], "fake", now))
                connection.execute("INSERT INTO journals VALUES(?,?,?,?,?,?,?,?,?,?)",
                    (turn_id, self.save_id, sequence, "标题", "摘要", "grand_academy", "上午", "[]", 0, now))
        first = self.request("GET", f"/api/saves/{self.save_id}/turns?cursor=0&limit=2")
        self.assertEqual(2, len(first["items"])); self.assertEqual(2, first["next_cursor"])
        journals = self.request("GET", f"/api/saves/{self.save_id}/journals?cursor=2&limit=2")
        self.assertEqual([3], [item["sequence"] for item in journals["items"]])
        self.request("GET", f"/api/saves/{self.save_id}/turns?unknown=1", expected=400)


if __name__ == "__main__":
    unittest.main()
