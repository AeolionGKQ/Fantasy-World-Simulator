"""Optional embedding service and vector recall of long-term memories (docs: 长期记忆向量召回方案)."""
import json
import unittest

import test_phase_two as base
from api.model_provider import ProviderError
from api.story_repository import StoryRepository, number_active_memories, semantic_bonuses

gm_response = base.gm_response

VOCABULARY = ("塔", "面包", "钥匙")


class FakeEmbeddings:
    """One dimension per vocabulary word plus a small constant, so related texts point the same way."""

    def __init__(self):
        self.fail = None
        self.calls = []

    def embed(self, config, api_key, texts):
        self.calls.append(list(texts))
        if self.fail:
            raise ProviderError(self.fail, "嵌入服务请求超时", True)
        return [[float(text.count(word)) for word in VOCABULARY] + [0.1] for text in texts]

    def test_connection(self, config, api_key):
        return {"ok": True, "model": config["model"], "dimensions": len(self.embed(config, api_key, ["测试"])[0]),
                "latency_ms": 1}


class SemanticScoringTest(unittest.TestCase):
    def test_bonus_scales_from_twenty_to_sixty_within_the_turns_range(self):
        bonuses = semantic_bonuses({"a": 0.80, "b": 0.72, "c": 0.64, "d": 0.50})
        self.assertEqual({"a": 60, "b": 40, "c": 20}, bonuses)  # threshold max(0.2, 0.8 * 0.8) = 0.64
        self.assertEqual({}, semantic_bonuses({"a": 0.15, "b": 0.1}))  # below the absolute floor
        ten = semantic_bonuses({f"m{index}": 0.9 for index in range(12)})
        self.assertEqual(10, len(ten))
        self.assertEqual({60}, set(ten.values()))  # one shared similarity: no range to scale

    def test_semantic_match_replaces_the_keyword_rule_only(self):
        memories = number_active_memories([
            {"id": "typed", "status": "active", "importance": 30, "keywords": ["黑塔"], "locations": [],
             "people": [], "unresolved": [], "updated_at": "1"},
            {"id": "here", "status": "active", "importance": 30, "keywords": [], "locations": ["grand_academy"],
             "people": [], "unresolved": [], "updated_at": "2"},
            {"id": "similar", "status": "active", "importance": 30, "keywords": [], "locations": [],
             "people": [], "unresolved": [], "updated_at": "3"}])
        state = {"location": {"id": "grand_academy"}}
        code = StoryRepository._recall_memories(state, [], memories, "去黑塔")
        self.assertEqual({"typed", "here"}, {item["id"] for item in code})
        vector = StoryRepository._recall_memories(state, [], memories, "去黑塔", semantic={"similar": 45})
        self.assertEqual(["similar", "here"], [item["id"] for item in vector])  # 75 beats 70
        self.assertEqual("语义相关（+45）", vector[0]["recall_reason"])


class EmbeddingRecallApiTest(unittest.TestCase):
    setUp = base.PhaseTwoApiTest.setUp
    tearDown = base.PhaseTwoApiTest.tearDown
    request = base.PhaseTwoApiTest.request
    _ready_save = base.PhaseTwoApiTest._ready_save
    wait_job = base.PhaseTwoApiTest.wait_job

    def embeddings(self):
        fake = FakeEmbeddings()
        self.server.app_context.embedding_provider = fake
        return fake

    def configure(self, test=True):
        revision = self.request("GET", "/api/settings")["revision"]
        settings = self.request("PUT", "/api/settings/embedding-model", {
            "base_url": "https://embeddings.example/v1/embeddings", "model": "bge-m3", "api_key": "sk-embed",
            "expected_revision": revision, "request_id": f"embedding-{revision}"})
        if test:
            self.request("POST", "/api/settings/embedding-model/test", {})
        return settings

    def play(self, kind, request_id, version, memories=(), **fields):
        response = gm_response(kind)
        response["narrative"]["body"] = "旅人在学院里打听到两条消息。"
        response["memory_candidates"] = list(memories)
        self.provider.responses.append(response)
        path = {"opening": "story/opening", "turn": "turns"}[kind]
        job = self.request("POST", f"/api/saves/{self.save_id}/{path}",
                           {"request_id": request_id, "expected_state_version": version} | fields, 202)
        done = self.wait_job(self.save_id, job["id"])
        self.assertEqual("succeeded", done["status"])
        return done

    def memory(self, summary, keywords):
        return {"operation": "create", "memory_id": None, "kind": "clue", "summary": summary, "importance": 30,
                "people": [], "locations": [], "keywords": keywords, "facts": [], "unresolved": [],
                "reason": "线索", "evidence": "打听到两条消息"}

    def open_with_memories(self):
        self.play("opening", "embedding-opening", 0, [self.memory("城外古塔藏有旧王的遗物", ["古塔"]),
                                                     self.memory("面包店周三打折", ["面包店"])], guidance="")

    def test_settings_test_and_status(self):
        fake = self.embeddings()
        status = self.request("GET", "/api/status/services")["embedding_model"]
        self.assertEqual("not_configured", status["state"])
        invalid = self.request("PUT", "/api/settings/embedding-model", {
            "base_url": "embeddings.example", "model": "bge-m3",
            "expected_revision": self.request("GET", "/api/settings")["revision"], "request_id": "bad-url"}, 400)
        self.assertIn("base_url", invalid["error"]["fields"])
        settings = self.configure(test=False)
        self.assertEqual({"base_url": "https://embeddings.example/v1/embeddings", "model": "bge-m3",
                          "configured": True, "api_key_configured": True},
                         {key: settings["embedding_model"][key]
                          for key in ("base_url", "model", "configured", "api_key_configured")})
        self.assertEqual("unverified", self.request("GET", "/api/status/services")["embedding_model"]["state"])
        result = self.request("POST", "/api/settings/embedding-model/test", {})
        self.assertEqual((True, 4), (result["ok"], result["dimensions"]))
        self.assertEqual("connected", self.request("GET", "/api/status/services")["embedding_model"]["state"])
        fake.fail = "MODEL_AUTH_FAILED"
        self.request("POST", "/api/settings/embedding-model/test", {}, 401)
        self.assertEqual("failed", self.request("GET", "/api/status/services")["embedding_model"]["state"])

    def test_vector_recall_finds_a_memory_worded_differently(self):
        fake = self.embeddings()
        self.open_with_memories()
        self.configure()
        done = self.play("turn", "embedding-turn", 1, action="我想去那座黑色的塔看看", option_id=None)
        context = json.loads(self.provider.messages[-1][1]["content"])
        self.assertEqual(["城外古塔藏有旧王的遗物"], [item["summary"] for item in context["long_term_memories"]])
        recall = done["context_manifest"]["memory_recall"]
        self.assertEqual(("vector", "bge-m3"), (recall["mode"], recall["model"]))
        self.assertEqual(60, next(iter(recall["semantic"].values()))["bonus"])
        with self.server.app_context.database.connect() as connection:
            self.assertEqual(2, connection.execute("SELECT COUNT(*) FROM memory_embeddings").fetchone()[0])
        # Stored vectors are reused: the next turn only embeds the query.
        self.play("turn", "embedding-turn-2", 2, action="继续看看", option_id=None)
        self.assertEqual(1, len(fake.calls[-1]))

    def test_failures_fall_back_and_three_in_a_row_are_reported(self):
        fake = self.embeddings()
        self.open_with_memories()
        self.configure()
        fake.fail = "MODEL_TIMEOUT"
        for index in range(3):
            done = self.play("turn", f"fallback-{index}", index + 1, action="去面包店", option_id=None)
            recall = done["context_manifest"]["memory_recall"]
            self.assertEqual(("code", "failed"), (recall["mode"], recall["reason"]))
            # The keyword rule still recalls the bakery memory; the turn is not affected.
            context = json.loads(self.provider.messages[-1][1]["content"])
            self.assertEqual(["面包店周三打折"], [item["summary"] for item in context["long_term_memories"]])
            failures = self.request("GET", f"/api/saves/{self.save_id}/memory")["embedding_failures"]
            self.assertEqual(None if index < 2 else {"count": 3, "message": "嵌入服务请求超时"}, failures)
        self.assertEqual("failed", self.request("GET", "/api/status/services")["embedding_model"]["state"])
        fake.fail = None  # a failed call keeps vector recall on, so the next turn recovers
        done = self.play("turn", "recovered", 4, action="继续", option_id=None)
        self.assertEqual("vector", done["context_manifest"]["memory_recall"]["mode"])
        self.assertIsNone(self.request("GET", f"/api/saves/{self.save_id}/memory")["embedding_failures"])

    def switch(self, enabled):
        revision = self.request("GET", "/api/settings")["revision"]
        return self.request("PUT", "/api/settings/embedding-model", {
            "enabled": enabled, "expected_revision": revision, "request_id": f"switch-{revision}"})

    def test_the_players_switch_turns_vector_recall_off_and_on(self):
        fake = self.embeddings()
        self.open_with_memories()
        self.configure()
        self.assertTrue(self.request("GET", "/api/settings")["embedding_model"]["enabled"])
        self.assertFalse(self.switch(False)["embedding_model"]["enabled"])
        self.assertEqual("disabled", self.request("GET", "/api/status/services")["embedding_model"]["state"])
        calls = len(fake.calls)
        done = self.play("turn", "switched-off", 1, action="去面包店", option_id=None)
        self.assertEqual({"mode": "code", "reason": "disabled"}, done["context_manifest"]["memory_recall"])
        self.assertEqual(calls, len(fake.calls))  # nothing is sent to the embedding service
        context = json.loads(self.provider.messages[-1][1]["content"])
        self.assertEqual(["面包店周三打折"], [item["summary"] for item in context["long_term_memories"]])
        # Switching back on needs no new connection test.
        self.switch(True)
        self.assertEqual("connected", self.request("GET", "/api/status/services")["embedding_model"]["state"])
        recall = self.play("turn", "switched-on", 2, action="继续", option_id=None)["context_manifest"]["memory_recall"]
        self.assertEqual("vector", recall["mode"])
        self.assertIsInstance(recall["duration_ms"], int)
        revision = self.request("GET", "/api/settings")["revision"]
        bad = self.request("PUT", "/api/settings/embedding-model", {
            "enabled": "no", "expected_revision": revision, "request_id": "switch-bad"}, 400)
        self.assertIn("enabled", bad["error"]["fields"])

    def test_a_failed_connection_test_turns_vector_recall_off(self):
        fake = self.embeddings()
        self.open_with_memories()
        self.configure()
        fake.fail = "MODEL_AUTH_FAILED"
        self.request("POST", "/api/settings/embedding-model/test", {}, 401)
        calls = len(fake.calls)
        done = self.play("turn", "untested", 1, action="继续", option_id=None)
        self.assertEqual({"mode": "code", "reason": "not_ready"}, done["context_manifest"]["memory_recall"])
        self.assertEqual(calls, len(fake.calls))
        self.assertIsNone(self.request("GET", f"/api/saves/{self.save_id}/memory")["embedding_failures"])


if __name__ == "__main__":
    unittest.main()
