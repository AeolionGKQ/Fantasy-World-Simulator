"""Rules confirmed before the beta release (docs/测试版发布前GM功能检查报告.md, section 4)."""
import copy
import json
import time
import unittest

import test_phase_two as base
from api.content_registry import STATE_RULES_POLICY_VERSION, ContentRegistry, state_rules_policy
from api.contract_registry import load_contract
from api.model_provider import ProviderError
from api.narrative_contract import ContractError, adjudicate, validate_gm_response
from api.story_repository import (StoryRepository, canonical_location_map, initial_story_state,
                                  number_active_memories)

gm_response = base.gm_response


def story_state(rank=3, exp=0, race="human", age=24):
    registry = ContentRegistry(base.API_DIR)
    character = {"id": "character", "candidate_id": "candidate", "data": {
        "identity": {"talent": "", "race_id": race, "age": age}, "current_location_id": "grand_academy",
        "attributes": {key: {"value": 50, "reason": ""} for key in ("con", "int", "cha")},
        "resources": {key: {"current": 100, "max": 100, "reason": ""} for key in ("hp", "mp", "sp", "st")},
        "rank": rank, "exp": exp}}
    return initial_story_state(character, {"narration": {}}, registry.revision_id, registry.quests)


def decide(state, response, action=None):
    return adjudicate(state, validate_gm_response(response), canonical_location_map(), set(), {},
                      action or {"action": "继续前进"})


class StateRuleTest(unittest.TestCase):
    def test_age_follows_story_time_and_never_drops_below_one(self):
        state = story_state(age=24)
        response = gm_response("turn")
        response["narrative"]["body"] = "三年的学院生活转眼过去。"
        response["proposals"]["age"] = {"years_delta": 3, "reason": "学院三年", "evidence": "三年的学院生活转眼过去"}
        decided = decide(state, response)
        self.assertEqual(27, decided["state"]["character"]["age"])
        self.assertEqual(24, decided["state"]["character"]["identity"]["age"])  # creation record stays
        self.assertIn(("age", 24, 27), [(c["kind"], c["old"], c["new"]) for c in decided["changes"]])
        younger = copy.deepcopy(response)
        younger["narrative"]["body"] = "古老的泉水让旅人重回孩童模样。"
        younger["proposals"]["age"] = {"years_delta": -100, "reason": "返老还童", "evidence": "重回孩童模样"}
        self.assertEqual(1, decide(state, younger)["state"]["character"]["age"])
        zero = copy.deepcopy(response)
        zero["proposals"]["age"]["years_delta"] = 0
        with self.assertRaisesRegex(ContractError, "非零整数"):
            validate_gm_response(zero)

    def test_full_exp_at_rank_six_opens_a_breakthrough_quest_once(self):
        state = story_state(rank=6, exp=640)
        response = gm_response("turn")
        response["narrative"]["body"] = "一次艰难的护卫让旅人的力量趋于圆满。"
        response["proposals"]["experience"] = [{"amount": 20, "growth_type": "实战", "challenge": "high",
            "novelty": "new", "repetition": "none", "reason": "护卫", "evidence": "一次艰难的护卫"}]
        decided = decide(state, response)
        quests = [q for q in decided["state"]["quests"].values() if q["quest_kind"] == "breakthrough"]
        self.assertEqual(1, len(quests))
        self.assertEqual(("eligible", 7), (quests[0]["status"], quests[0]["target_rank"]))
        declined = copy.deepcopy(decided["state"])
        declined["quests"][quests[0]["id"]]["status"] = "declined"
        again = decide(declined, gm_response("turn"))
        self.assertEqual(1, len([q for q in again["state"]["quests"].values()
                                 if q["quest_kind"] == "breakthrough"]))

    def test_rank_up_raises_all_resource_maxima(self):
        state = story_state(rank=3, exp=200)
        state["character"]["breakthrough_eligible"] = True
        state["character"]["resources"]["hp"]["current"] = 80
        response = gm_response("turn")
        response["narrative"]["body"] = "旅人闭关冲击四阶，魔力顺利贯通。"
        response["proposals"]["breakthrough"] = {"attempted": True, "success": True,
            "action_evidence": "闭关冲击四阶", "method": "引导魔力", "preparation": "状态良好",
            "failure_reason": None, "improvement": None, "task_completed_id": None,
            "reason": "突破成功", "evidence": "魔力顺利贯通"}
        decided = decide(state, response, {"action": "我闭关冲击四阶"})
        resources = decided["state"]["character"]["resources"]
        self.assertEqual(4, decided["state"]["character"]["rank"])
        self.assertEqual({130}, {resources[key]["max"] for key in ("hp", "mp", "sp", "st")})
        self.assertEqual(110, resources["hp"]["current"])

    def test_ordinary_equipment_beyond_forty_percent_is_not_counted(self):
        state = story_state(rank=3)  # base power 320, cap 128
        response = gm_response("turn")
        response["narrative"]["body"] = "旅人买下一柄做工精良的长剑并立刻佩上。"
        response["proposals"]["items"] = [{"operation": "add", "item_id": None, "name": "精良长剑",
            "description": "", "quantity": 1, "power": 200, "power_class": "ordinary", "power_basis": "",
            "equipped": True, "source": "铁匠铺", "reason": "购买", "evidence": "买下一柄做工精良的长剑"}]
        decided = decide(state, response)
        character = decided["state"]["character"]
        self.assertEqual(320 + 128, character["effective_power"])
        self.assertTrue(any("不计入有效战力" in note for note in decided["notes"]))

    def test_power_modifier_caps_follow_severity_for_new_modifiers_only(self):
        state = story_state(rank=3)  # base power 320
        response = gm_response("turn")
        response["narrative"]["body"] = "旅人肩头中箭，动作明显迟缓。"
        response["proposals"]["power_modifiers"] = [{"operation": "add", "id": "wound", "value": -100,
            "temporary": True, "category": "status", "severity": "minor", "canonical_exception": None,
            "reason": "中箭", "evidence": "旅人肩头中箭"}]
        with self.assertRaisesRegex(ContractError, "最多32"):
            decide(state, response)
        response["proposals"]["power_modifiers"][0]["severity"] = "major"  # cap 160
        self.assertEqual(220, decide(state, response)["state"]["character"]["effective_power"])
        legacy = copy.deepcopy(state)
        legacy["character"]["power_modifiers"] = [{"id": "old", "value": -200, "reason": "旧伤", "temporary": True,
            "category": "status", "severity": "minor", "canonical_exception": None}]
        self.assertEqual(120, decide(legacy, gm_response("turn"))["state"]["character"]["effective_power"])

    def test_attribute_changes_are_capped_at_twenty(self):
        response = gm_response("turn")
        response["proposals"]["attributes"] = [{"key": "con", "delta": 21, "long_term_basis": "长期训练",
            "reason": "训练", "evidence": "晨光落在广场上"}]
        with self.assertRaisesRegex(ContractError, "attributes"):
            validate_gm_response(response)
        # Saves frozen on the older contract (schema allowed ±35) still get the ±20 cap.
        older = load_contract("gm_turn")
        older["schema"]["$defs"]["attribute"]["properties"]["delta"].update({"minimum": -35, "maximum": 35})
        with self.assertRaisesRegex(ContractError, "±20"):
            validate_gm_response(response, contract=older)

    def test_stackable_items_reuse_the_existing_entry(self):
        state = story_state()
        state["inventory"]["item.potion"] = {"id": "item.potion", "name": "治疗药水", "description": "",
            "quantity": 2, "power": 0, "power_class": "ordinary", "power_basis": "", "equipped": False,
            "source": "商店"}
        response = gm_response("turn")
        response["narrative"]["body"] = "旅人又买了三瓶治疗药水。"
        response["proposals"]["items"] = [{"operation": "add", "item_id": None, "name": "治疗药水",
            "description": "", "quantity": 3, "power": 0, "power_class": "ordinary", "power_basis": "",
            "equipped": False, "source": "商店", "reason": "购买", "evidence": "又买了三瓶治疗药水"}]
        inventory = decide(state, response)["state"]["inventory"]
        self.assertEqual(1, len(inventory))
        self.assertEqual(5, inventory["item.potion"]["quantity"])

    def test_new_quests_need_a_name_and_learnables_need_an_id_to_change(self):
        response = gm_response("turn")
        response["narrative"]["body"] = "公会贴出一张委托。"
        response["proposals"]["quests"] = [{"operation": "create", "quest_id": None, "name": None,
            "description": None, "status": "offered", "progress": None, "objectives": [],
            "quest_kind": "regular", "target_rank": None, "action_evidence": "", "necessary_nodes": [],
            "terminal_cause": "none", "reason": "委托", "evidence": "公会贴出一张委托"}]
        with self.assertRaisesRegex(ContractError, "name和description"):
            decide(story_state(), response)
        talents = gm_response("turn")
        talents["proposals"]["talents"] = [{"operation": "update", "id": None, "name": "天赋", "description": "改",
            "source": "剧情", "reason": "改", "evidence": "晨光落在广场上"}]
        with self.assertRaisesRegex(ContractError, "已有的id"):
            validate_gm_response(talents)

    def test_zero_change_needs_no_evidence(self):
        response = gm_response("turn")
        response["proposals"]["resources"] = [{"key": "mp", "delta": 0, "reason": "无消耗", "evidence": "不在正文里"}]
        decide(story_state(), response)

    def test_state_rules_policy_reaches_every_gm_turn(self):
        registry = ContentRegistry(base.API_DIR)
        state = story_state(rank=5)
        messages, manifest = registry.build_messages(
            {**state, "regional_quests": {}}, {"action_type": "turn"}, [], [], [], [], {},
            registry.documents, "gm_turn", registry.manifest)
        system = messages[0]["content"]
        start = system.index("<RUNTIME_STATE_RULES_POLICY_JSON>") + len("<RUNTIME_STATE_RULES_POLICY_JSON>")
        policy = json.loads(system[start:system.index("</RUNTIME_STATE_RULES_POLICY_JSON>")])
        self.assertEqual(STATE_RULES_POLICY_VERSION, manifest["state_rules_policy_version"])
        self.assertEqual(400, policy["current_numbers"]["ordinary_equipment_power_cap"])
        text = " ".join(policy["rules"])
        for expected in ("life_defining为35", "world_shaping为50", "talent.legacy", "proposals.age", "不能复活"):
            self.assertIn(expected, text)
        old_contract = load_contract("gm_turn")
        del old_contract["schema"]["properties"]["proposals"]["properties"]["age"]
        older = json.loads(state_rules_policy(state, old_contract).strip().split("\n")[1])
        self.assertIn("不要提交年龄变化", " ".join(older["rules"]))


class MemoryRecallTest(unittest.TestCase):
    def test_player_input_keywords_count_and_open_threads_score_less(self):
        def memory(key, importance, **fields):
            return {"id": key, "status": "active", "importance": importance, "locations": [], "people": [],
                    "keywords": [], "unresolved": [], "updated_at": key, **fields}
        memories = number_active_memories([
            memory("a-typed", 45, keywords=["黑塔"]),
            memory("b-open", 60, unresolved=["约定未履行"]),
            memory("c-here", 30, locations=["grand_academy"], unresolved=["钥匙下落"]),
            memory("d-quiet", 50, keywords=["灯塔"]),
        ])
        recalled = StoryRepository._recall_memories(
            {"location": {"id": "grand_academy"}}, [{"title": "", "summary": "", "body": "风很大。"}],
            memories, "我想去黑塔看看")
        self.assertEqual(["c-here", "a-typed", "b-open"], [item["id"] for item in recalled])  # 90, 85, 80
        reasons = {item["id"]: item["recall_reason"] for item in recalled}
        self.assertEqual("本轮输入关键词相关：黑塔", reasons["a-typed"])
        self.assertEqual("当前位置相关；包含未解决事项", reasons["c-here"])
        self.assertEqual([], StoryRepository._recall_memories(
            {"location": {"id": "grand_academy"}}, [], [memory("e", 45, keywords=["黑塔"])], "随便走走"))


class ReleaseApiTest(unittest.TestCase):
    setUp = base.PhaseTwoApiTest.setUp
    tearDown = base.PhaseTwoApiTest.tearDown
    request = base.PhaseTwoApiTest.request
    _ready_save = base.PhaseTwoApiTest._ready_save
    wait_job = base.PhaseTwoApiTest.wait_job

    def seed_turns(self, count):
        db = self.server.app_context.database
        state = self.server.app_context.story.get_state(self.save_id)
        now = "2026-10-18T00:00:00+00:00"
        with db.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            for sequence in range(1, count + 1):
                turn_id, version_id = f"seed-turn-{sequence}", f"seed-version-{sequence}"
                connection.execute("INSERT INTO turns VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (turn_id, self.save_id, sequence, version_id, "turn", "{}", f"标题{sequence}",
                     f"正文{sequence}", f"摘要{sequence}", "[]", "[]", 0, 1, now, now))
                connection.execute("INSERT INTO turn_snapshots VALUES(?,?,?,?,?)",
                    (turn_id, self.save_id, "turn-snapshot/1", json.dumps({"state": state, "memories": []}), now))
                connection.execute("INSERT INTO turn_versions VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (version_id, turn_id, self.save_id, 1, "{}", "{}", "[]",
                     self.server.app_context.content_registry.prompt_version,
                     state["content_revision_id"], "fake", now, "{}", "[]"))
            connection.execute("UPDATE story_states SET current_turn_id=?,state_version=1 WHERE save_id=?",
                               (f"seed-turn-{count}", self.save_id))
            connection.commit()

    def run_automatic_arc(self):
        story = self.server.app_context.story
        job, created = story.create_arc_job(self.save_id, {}, automatic=True)
        if created:
            self.server.app_context.schedule_narrative(self.save_id, job["id"])
            return self.wait_job(self.save_id, job["id"])
        return None

    def wait_for_arcs(self, current_count):
        deadline = time.time() + 20
        while time.time() < deadline:
            memory = self.request("GET", f"/api/saves/{self.save_id}/memory")
            view = self.request("GET", f"/api/saves/{self.save_id}/story")
            current = [arc for arc in memory["story_arcs"] if arc["status"] == "current"]
            if len(current) == current_count and not view["active_arc_job"]:
                return current
            time.sleep(.05)
        self.fail("story arcs did not settle")

    def test_dead_character_can_only_reshape(self):
        self.server.app_context.story.get_state(self.save_id)
        db = self.server.app_context.database
        with db.connect() as connection:
            row = connection.execute("SELECT state_json FROM story_states WHERE save_id=?", (self.save_id,)).fetchone()
            state = json.loads(row["state_json"])
            state["character"]["alive"] = False
            state["character"]["status"] = "dead"
            connection.execute("UPDATE story_states SET state_json=?,current_turn_id='dead-turn' WHERE save_id=?",
                               (json.dumps(state, ensure_ascii=False), self.save_id))
            connection.commit()
        error = self.request("POST", f"/api/saves/{self.save_id}/turns", {
            "request_id": "after-death", "expected_state_version": 0, "action": "站起来", "option_id": None}, 409)
        self.assertEqual("CHARACTER_DEAD", error["error"]["code"])

    def test_player_edits_to_additional_setting_reach_the_next_turn_and_survive_reshape(self):
        path = f"/api/saves/{self.save_id}/character-state/additional"
        edit = {"request_id": "notes-1", "expected_state_version": 0, "additional": "  左手有旧伤，惧怕深水。  "}
        result = self.request("PUT", path, edit)
        self.assertEqual((1, "左手有旧伤，惧怕深水。"), (result["state_version"], result["additional"]))
        self.assertEqual(result, self.request("PUT", path, edit))  # same request replays
        self.assertEqual("IDEMPOTENCY_CONFLICT", self.request("PUT", path, edit | {"additional": "别的"}, 409)["error"]["code"])
        self.assertEqual("STATE_VERSION_CONFLICT", self.request("PUT", path, edit | {"request_id": "notes-old"}, 409)["error"]["code"])
        self.assertEqual("INVALID_INPUT", self.request("PUT", path, {"request_id": "notes-long", "expected_state_version": 1,
                                                                     "additional": "长" * 8001}, 400)["error"]["code"])
        character = self.request("GET", f"/api/saves/{self.save_id}/character-state")
        self.assertEqual("左手有旧伤，惧怕深水。", character["identity"]["additional"])
        self.provider.responses.append(gm_response("opening"))
        job = self.request("POST", f"/api/saves/{self.save_id}/story/opening",
                           {"request_id": "notes-opening", "expected_state_version": 1, "guidance": ""}, 202)
        self.assertEqual("succeeded", self.wait_job(self.save_id, job["id"])["status"])
        context = json.loads(self.provider.messages[-1][1]["content"])
        self.assertEqual("左手有旧伤，惧怕深水。", context["authoritative_state"]["character"]["identity"]["additional"])
        self.assertIn("identity.additional", self.provider.messages[-1][0]["content"])
        self.request("PUT", path, {"request_id": "notes-2", "expected_state_version": 2, "additional": "已学会游泳。"})
        turn_id = self.request("GET", f"/api/saves/{self.save_id}/story")["latest_turn"]["id"]
        self.provider.responses.append(gm_response("reshape"))
        job = self.request("POST", f"/api/saves/{self.save_id}/turns/{turn_id}/reshape",
                           {"request_id": "notes-reshape", "expected_state_version": 3, "guidance": "换个开场"}, 202)
        self.assertEqual("succeeded", self.wait_job(self.save_id, job["id"])["status"])
        context = json.loads(self.provider.messages[-1][1]["content"])
        self.assertEqual("已学会游泳。", context["authoritative_state"]["character"]["identity"]["additional"])
        story = self.request("GET", f"/api/saves/{self.save_id}/story")
        self.assertEqual("已学会游泳。", story["state"]["character"]["identity"]["additional"])

    def test_turn_input_recalls_memory_by_keyword(self):
        opening = gm_response("opening")
        opening["narrative"]["body"] = "旅人听说城外有一座古塔。"
        opening["memory_candidates"] = [{"operation": "create", "memory_id": None, "kind": "clue",
            "summary": "城外古塔藏有旧王的遗物", "importance": 30, "people": [], "locations": [],
            "keywords": ["黑塔"], "facts": ["古塔里有遗物"], "unresolved": [], "reason": "线索",
            "evidence": "旅人听说城外有一座古塔"}]
        self.provider.responses.append(opening)
        job = self.request("POST", f"/api/saves/{self.save_id}/story/opening",
                           {"request_id": "recall-opening", "expected_state_version": 0, "guidance": ""}, 202)
        self.assertEqual("succeeded", self.wait_job(self.save_id, job["id"])["status"])
        self.provider.responses.append(gm_response("turn"))
        job = self.request("POST", f"/api/saves/{self.save_id}/turns", {"request_id": "recall-turn",
            "expected_state_version": 1, "action": "我去黑塔看看", "option_id": None}, 202)
        self.assertEqual("succeeded", self.wait_job(self.save_id, job["id"])["status"])
        context = json.loads(self.provider.messages[-1][1]["content"])
        self.assertEqual(["本轮输入关键词相关：黑塔"],
                         [item["recall_reason"] for item in context["long_term_memories"]])

    def memory_candidate(self, summary, evidence, importance=60):
        return {"operation": "create", "memory_id": None, "kind": "clue", "summary": summary,
                "importance": importance, "people": [], "locations": [], "keywords": [], "facts": [summary],
                "unresolved": [], "reason": "线索", "evidence": evidence}

    def play(self, kind, request_id, version, memories=(), **fields):
        response = gm_response(kind)
        response["narrative"]["body"] = "旅人在学院里打听到三条消息。"
        response["memory_candidates"] = list(memories)
        self.provider.responses.append(response)
        path = {"opening": "story/opening", "turn": "turns"}[kind]
        body = {"request_id": request_id, "expected_state_version": version} | fields
        job = self.request("POST", f"/api/saves/{self.save_id}/{path}", body, 202)
        self.assertEqual("succeeded", self.wait_job(self.save_id, job["id"])["status"])

    def memories(self):
        return self.request("GET", f"/api/saves/{self.save_id}/memories")["items"]

    def assert_round_trip(self):
        exported = self.request("GET", f"/api/saves/{self.save_id}/export")
        self.assertTrue(self.request("POST", "/api/saves/import/validate", exported)["valid"])
        self.request("POST", "/api/saves/import", {"request_id": "round-trip-" + str(len(self.provider.messages)),
                                                   "payload": exported}, 201)

    def test_player_removed_memory_stays_removed_after_reshape_and_export(self):
        self.play("opening", "removal-opening", 0, [self.memory_candidate("钟楼下埋着钥匙", "打听到三条消息")],
                  guidance="")
        self.play("turn", "removal-turn", 1, action="继续打听", option_id=None)
        memory = self.memories()[0]
        path = f"/api/saves/{self.save_id}/memories/{memory['id']}"
        self.assertEqual({"save_id": self.save_id, "memory_id": memory["id"], "removed": True},
                         self.request("DELETE", path))
        self.assertTrue(self.request("DELETE", path)["removed"])  # repeating is harmless
        self.assertEqual("MEMORY_NOT_FOUND", self.request(
            "DELETE", f"/api/saves/{self.save_id}/memories/missing", None, 404)["error"]["code"])
        self.assertEqual([], self.memories())
        self.request("PUT", f"/api/saves/{self.save_id}/character-state/additional",
                     {"request_id": "removal-notes", "expected_state_version": 2, "additional": "怕黑。"})
        self.assert_round_trip()  # removals and the edited setting do not break replay
        turn_id = self.request("GET", f"/api/saves/{self.save_id}/story")["latest_turn"]["id"]
        self.provider.responses.append(gm_response("reshape"))
        job = self.request("POST", f"/api/saves/{self.save_id}/turns/{turn_id}/reshape",
                           {"request_id": "removal-reshape", "expected_state_version": 3, "guidance": "换个说法"}, 202)
        self.assertEqual("succeeded", self.wait_job(self.save_id, job["id"])["status"])
        self.assertEqual([], json.loads(self.provider.messages[-1][1]["content"])["long_term_memories"])
        self.assertEqual([], self.memories())
        self.assert_round_trip()

    def test_memory_curation_removes_what_the_model_names(self):
        self.play("opening", "curation-opening", 0, [
            self.memory_candidate("钟楼下埋着钥匙", "打听到三条消息"),
            self.memory_candidate("面包店周三打折", "打听到三条消息", 10),
            self.memory_candidate("导师在等回信", "打听到三条消息")], guidance="")
        before = self.memories()
        self.assertEqual(3, len(before))
        path = f"/api/saves/{self.save_id}/memory-curations"
        # Two invalid answers fail the job with the reason, like any other model job.
        bad = {"schema_version": "memory-curation/1",
               "remove": [{"memory_number": 9, "category": "expired", "reason": "不存在"}]}
        self.provider.responses.extend([bad, bad])
        job = self.request("POST", path, {"request_id": "curation-bad", "expected_state_version": 1}, 202)
        failed = self.wait_job(self.save_id, job["id"])
        self.assertEqual(("failed", "MODEL_OUTPUT_FORMAT"), (failed["status"], failed["error"]["code"]))
        self.assertEqual(3, len(self.memories()))
        bakery = next(item["memory_number"] for item in before if item["summary"] == "面包店周三打折")
        self.provider.responses.append({"schema_version": "memory-curation/1", "remove": [
            {"memory_number": bakery, "category": "unimportant", "reason": "琐碎"}]})
        job = self.request("POST", path, {"request_id": "curation-ok", "expected_state_version": 1}, 202)
        done = self.wait_job(self.save_id, job["id"])
        self.assertEqual("succeeded", done["status"])
        self.assertEqual([{"memory_number": bakery, "summary": "面包店周三打折", "category": "unimportant",
                           "reason": "琐碎"}], done["result"]["removed"])
        system, dynamic = self.provider.messages[-1][0]["content"], json.loads(self.provider.messages[-1][1]["content"])
        self.assertIn("RUNTIME_MEMORY_CURATION_POLICY_JSON", system)
        self.assertIn("memory-curation/1", system)
        self.assertEqual(3, len(dynamic["long_term_memories"]))  # every memory, not only recalled ones
        self.assertEqual({"钟楼下埋着钥匙", "导师在等回信"}, {item["summary"] for item in self.memories()})
        self.assert_round_trip()

    def test_memory_curation_and_story_turns_wait_for_each_other(self):
        self.play("opening", "wait-opening", 0, [self.memory_candidate("钟楼下埋着钥匙", "打听到三条消息")],
                  guidance="")
        story = self.server.app_context.story
        job, created = story.create_memory_curation_job(self.save_id, {"request_id": "wait-curation",
                                                                       "expected_state_version": 1})
        self.assertTrue(created)  # left queued: nothing schedules it
        view = self.request("GET", f"/api/saves/{self.save_id}/story")
        self.assertEqual((job["id"], False), (view["active_memory_job"]["id"], view["can_act"]))
        blocked = self.request("POST", f"/api/saves/{self.save_id}/turns", {"request_id": "wait-turn",
            "expected_state_version": 1, "action": "继续", "option_id": None}, 409)
        self.assertEqual("MEMORY_CURATION_ACTIVE", blocked["error"]["code"])
        memory_id = self.memories()[0]["id"]
        self.assertEqual("MEMORY_CURATION_ACTIVE", self.request(
            "DELETE", f"/api/saves/{self.save_id}/memories/{memory_id}", None, 409)["error"]["code"])
        self.assertEqual("MEMORY_CURATION_ACTIVE", self.request(
            "POST", f"/api/saves/{self.save_id}/memory-curations",
            {"request_id": "wait-second", "expected_state_version": 1}, 409)["error"]["code"])

    def test_quest_panel_lists_offered_and_finished_quests(self):
        quests = self.request("GET", f"/api/saves/{self.save_id}/quests")
        self.assertEqual({"active", "offered", "finished", "state_version"}, set(quests))

    def test_failed_automatic_arc_is_retried_and_reported_after_three_failures(self):
        self.seed_turns(35)
        for attempt in range(3):
            self.server.app_context.provider.responses.append(
                ProviderError("MODEL_SERVICE_ERROR", f"服务暂时不可用{attempt}"))
            self.assertEqual("failed", self.run_automatic_arc()["status"])
        failures = self.request("GET", f"/api/saves/{self.save_id}/memory")["arc_failures"]
        self.assertEqual((3, 1, 25), (failures["count"], failures["start_sequence"], failures["end_sequence"]))
        self.assertIn("服务暂时不可用2", failures["message"])
        self.assertEqual("succeeded", self.run_automatic_arc()["status"])
        self.assertIsNone(self.request("GET", f"/api/saves/{self.save_id}/memory")["arc_failures"])

    def test_four_current_arcs_merge_the_earliest_three(self):
        self.seed_turns(110)
        self.assertEqual("succeeded", self.run_automatic_arc()["status"])
        current = self.wait_for_arcs(2)
        self.assertEqual([(1, 75, 2), (76, 100, 1)],
                         [(arc["start_sequence"], arc["end_sequence"], arc["level"]) for arc in current])


if __name__ == "__main__":
    unittest.main()
