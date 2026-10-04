"""Phase-two narrative persistence and atomic turn commits."""

import copy
import hashlib
import json

try:
    from .catalog import EXP_THRESHOLDS, NARRATION, POWER_BY_RANK
    from .content_registry import (TERMINAL_QUEST_STATES, load_revision_documents,
                                   load_revision_manifest)
    from .database import DomainError, dumps, loads, new_id, normalize_narration, utc_now
    from .location_graph import canonical_location_map
    from .narrative_contract import (REPUTATION_KEYS, ContractError, adjudicate,
                                     bond_level, receipt_hash, reputation_level)
except ImportError:
    from catalog import EXP_THRESHOLDS, NARRATION, POWER_BY_RANK
    from content_registry import (TERMINAL_QUEST_STATES, load_revision_documents,
                                  load_revision_manifest)
    from database import DomainError, dumps, loads, new_id, normalize_narration, utc_now
    from location_graph import canonical_location_map
    from narrative_contract import (REPUTATION_KEYS, ContractError, adjudicate,
                                     bond_level, receipt_hash, reputation_level)


SAFE_PUBLIC_STARTS = ("san_velia", "vargard", "grand_academy", "noxvia",
                      "thousand_furnace", "selavia_port", "sahravia")


def initial_story_state(character, save, content_revision, quest_specs):
    source = character["data"]
    identity = copy.deepcopy(source["identity"])
    talent = identity.get("talent", "")
    current_location_id = source["current_location_id"]
    locations = canonical_location_map()
    location = locations[current_location_id]
    reputations = {key: {"key": key, "value": 0, "level": "中立"}
                   for key in REPUTATION_KEYS}
    regional = {quest["id"]: {"id": quest["id"], "name": quest["name"],
                                        "description": quest["description"],
                                        "status": "untriggered", "progress": "",
                                        "objectives": [], "regional": True}
                for quest in quest_specs}
    prerequisite = start_prerequisite(identity, current_location_id)
    return {
        "schema_version": "story-state/1", "state_version": 0,
        "content_revision_id": content_revision, "current_turn_id": None,
        "narration": copy.deepcopy(normalize_narration(save["narration"])),
        "time": {"label": "上午", "elapsed_minutes": 0},
        "location": {"id": current_location_id, "name": location["name"],
                     "safeguards": location["safeguards"],
                     "legacy_start_protection": False,
                     "prerequisite": prerequisite},
        "character": {
            "id": character["id"], "candidate_id": character["candidate_id"], "identity": identity,
            "attributes": copy.deepcopy(source["attributes"]),
            "resources": copy.deepcopy(source["resources"]),
            "rank": source["rank"], "exp": source["exp"],
            "exp_to_next": EXP_THRESHOLDS[source["rank"]],
            "breakthrough_eligible": False,
            "base_power": POWER_BY_RANK[source["rank"]],
            "equipment_power": 0, "effective_power": POWER_BY_RANK[source["rank"]],
            "power_modifiers": [], "conditions": {}, "profession": None, "growth_path": None,
            "talents": ([{"id": "talent.legacy", "name": "初始天赋",
                           "description": talent, "source": "第一阶段正式角色"}] if talent else []),
            "skills": [], "alive": True, "status": "normal",
        },
        "inventory": {}, "currency_copper": source.get("initial_currency_copper", 0),
        "quests": {}, "npcs": {},
        "regional_quests": regional, "bonds": {}, "reputations": reputations,
        "locations": {}, "location_statuses": {}, "world_flags": {},
    }


def start_prerequisite(identity, location_id):
    race = identity.get("race_id")
    requirements = []
    if location_id == "abyssal_tides" and race != "sea_folk":
        requirements = ["underwater_breathing", "pressure_protection"]
    elif location_id == "dragonvale" and race not in {"dragonkin", "dwarf"}:
        requirements = ["heat_protection", "environment_protection"]
    elif location_id == "elf_forest" and race != "elf":
        requirements = ["elf_forest_entry_permission"]
    return {"status": "required" if requirements else "satisfied",
            "requirements": requirements, "resolution": None,
            "options": ([{"kind": "relocate", "location_ids": list(SAFE_PUBLIC_STARTS)},
                         {"kind": "accept_legacy_protection", "grants": requirements}]
                        if requirements else [])}


def number_active_memories(memories):
    """Assign contiguous display numbers without changing stable memory IDs."""
    active = [copy.deepcopy(memory) for memory in memories
              if memory.get("status") == "active"]
    active.sort(key=lambda memory: (memory.get("updated_at", ""), memory.get("id", "")))
    for number, memory in enumerate(active, 1):
        memory["memory_number"] = number
    return active


class StoryRepository:
    def __init__(self, database, content_registry):
        self.database = database
        self.content_registry = content_registry
        self.canonical_locations = canonical_location_map()

    def initialize(self, save_id, connection=None):
        own = connection is None
        connection = connection or self.database.connect()
        try:
            if own:
                connection.execute("BEGIN IMMEDIATE")
            save = self.database.get_save(save_id, connection)
            if save["phase"] != "ready":
                raise DomainError("SAVE_NOT_READY", "存档尚未完成角色确认", 409)
            row = connection.execute("SELECT * FROM story_states WHERE save_id=?", (save_id,)).fetchone()
            if not row:
                character_row = connection.execute("SELECT * FROM characters WHERE save_id=?", (save_id,)).fetchone()
                character = self.database._character_dict(character_row)
                state = initial_story_state(character, save, self.content_registry.revision_id,
                                            self.content_registry.quests)
                now = utc_now()
                connection.execute("INSERT INTO story_states VALUES(?,?,?,?,?,?,?)",
                                   (save_id, 0, None, self.content_registry.revision_id,
                                    dumps(state), now, now))
                for item in self.canonical_locations.values():
                    connection.execute(
                        "INSERT OR IGNORE INTO location_nodes VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                        (save_id, item["id"], item["name"], item["type"], item["scope"],
                         item["parent_id"], item["region_id"], item["jurisdiction_id"],
                         item["description"], 1, None))
                row = connection.execute("SELECT * FROM story_states WHERE save_id=?", (save_id,)).fetchone()
            if own:
                connection.commit()
            return self._state_row(row)
        except Exception:
            if own:
                connection.rollback()
            raise
        finally:
            if own:
                connection.close()

    @staticmethod
    def _state_row(row):
        state = loads(row["state_json"], {})
        state.setdefault("npcs", {})
        state.setdefault("location_statuses", {})
        state.get("character", {}).setdefault("conditions", {})
        state["narration"] = (normalize_narration(state.get("narration", {})) or
                              copy.deepcopy(NARRATION["defaults"]))
        state["state_version"] = row["state_version"]
        state["current_turn_id"] = row["current_turn_id"]
        state["content_revision_id"] = row["content_revision_id"]
        return state

    @staticmethod
    def _job_row(row):
        return {"id": row["id"], "save_id": row["save_id"], "request_id": row["request_id"],
                "type": row["job_type"], "source_state_version": row["source_state_version"],
                "target_turn_id": row["target_turn_id"], "status": row["status"],
                "error": ({"code": row["error_code"], "message": row["error_message"],
                           "retryable": bool(row["retryable"])} if row["error_code"] else None),
                "result": loads(row["result_json"]),
                "context_manifest": loads(row["context_manifest_json"]),
                "created_at": row["created_at"], "updated_at": row["updated_at"]}

    def get_state(self, save_id):
        self.initialize(save_id)
        with self.database.connect() as connection:
            row = connection.execute("SELECT * FROM story_states WHERE save_id=?", (save_id,)).fetchone()
        return self._state_row(row)

    def _revision_quests(self, documents, manifest):
        return self.content_registry.revision_quests(documents, manifest)

    def _validate_write(self, body, allowed):
        unknown = set(body) - set(allowed)
        if unknown:
            raise DomainError("INVALID_INPUT", "存在未知叙事请求字段", 400,
                              fields={key: "未知字段" for key in unknown})
        self.database._validate_request_id(body)
        if type(body.get("expected_state_version")) is not int or body["expected_state_version"] < 0:
            raise DomainError("INVALID_INPUT", "expected_state_version无效", 400,
                              fields={"expected_state_version": "必须是非负整数"})

    def create_job(self, save_id, job_type, body, target_turn_id=None):
        allowed = {"request_id", "expected_state_version"}
        if job_type == "opening":
            allowed.add("guidance")
        elif job_type == "turn":
            allowed.update({"action", "option_id"})
        elif job_type == "intervene":
            allowed.add("guidance")
        elif job_type == "reshape":
            allowed.add("guidance")
        self._validate_write(body, allowed)
        text_key = "action" if job_type == "turn" else "guidance"
        text = body.get(text_key, "")
        if not isinstance(text, str) or len(text) > 12000 or (job_type != "opening" and not text.strip()):
            raise DomainError("INVALID_INPUT", f"{text_key}格式无效", 400,
                              fields={text_key: "必须是长度合规的文本"})
        if job_type == "turn" and body.get("option_id") is not None and (
                not isinstance(body["option_id"], str) or len(body["option_id"]) > 300):
            raise DomainError("INVALID_INPUT", "option_id格式无效", 400)
        fingerprint = dumps({key: body.get(key) for key in sorted(allowed) if key != "request_id"})
        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            state = self.initialize(save_id, connection)
            previous = connection.execute(
                "SELECT * FROM narrative_jobs WHERE save_id=? AND request_id=?",
                (save_id, body["request_id"])).fetchone()
            if previous:
                if previous["request_fingerprint"] != fingerprint:
                    raise DomainError("IDEMPOTENCY_CONFLICT", "request_id已用于不同叙事请求", 409)
                if previous["status"] == "interrupted":
                    connection.execute(
                        "UPDATE narrative_jobs SET status='queued',error_code=NULL,error_message=NULL,"
                        "retryable=0,updated_at=? WHERE id=?", (utc_now(), previous["id"]))
                    previous = connection.execute(
                        "SELECT * FROM narrative_jobs WHERE id=?", (previous["id"],)).fetchone()
                    connection.commit()
                    return self._job_row(previous), True
                connection.commit()
                return self._job_row(previous), False
            if state["state_version"] != body["expected_state_version"]:
                raise DomainError("STATE_VERSION_CONFLICT", "权威状态版本冲突", 409,
                                  fields={"state_version": state["state_version"]})
            if job_type == "opening" and state["current_turn_id"]:
                raise DomainError("OPENING_ALREADY_EXISTS", "开场已经生成", 409)
            if (job_type == "opening" and
                    state["location"].get("prerequisite", {}).get("status") == "required"):
                raise DomainError("START_LOCATION_PREREQUISITE_REQUIRED",
                                  "起始地点需要先处理生存防护或通行许可", 409,
                                  fields={"prerequisite": state["location"]["prerequisite"]})
            if job_type in {"turn", "intervene"} and not state["current_turn_id"]:
                raise DomainError("OPENING_REQUIRED", "必须先生成开场", 409)
            if job_type == "reshape":
                if not state["current_turn_id"] or target_turn_id != state["current_turn_id"]:
                    raise DomainError("RESHAPE_LATEST_ONLY", "只能重塑最新剧情节点", 409)
            active = connection.execute(
                "SELECT id FROM narrative_jobs WHERE save_id=? AND status IN ('queued','running','cancel_requested') "
                "AND job_type IN ('opening','turn','intervene','reshape')",
                (save_id,)).fetchone()
            if active:
                raise DomainError("NARRATIVE_JOB_ACTIVE", "该存档已有活动叙事任务", 409,
                                  fields={"job_id": active["id"]}, retryable=True)
            now, job_id = utc_now(), new_id()
            request_input = dict(body)
            request_input["action_type"] = job_type
            connection.execute(
                "INSERT INTO narrative_jobs VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (job_id, save_id, body["request_id"], fingerprint, job_type,
                 state["state_version"], target_turn_id, "queued", dumps(request_input),
                 None, None, None, None, 0, now, now))
            row = connection.execute("SELECT * FROM narrative_jobs WHERE id=?", (job_id,)).fetchone()
            connection.commit()
        return self._job_row(row), True

    def resolve_start_prerequisite(self, save_id, body):
        self._validate_write(body, {"request_id", "expected_state_version", "resolution", "location_id"})
        resolution = body.get("resolution")
        if resolution not in {"relocate", "accept_legacy_protection"}:
            raise DomainError("INVALID_INPUT", "起点处理方式无效", 400)
        fingerprint = dumps({"resolution": resolution, "location_id": body.get("location_id"),
                             "expected_state_version": body["expected_state_version"]})
        scope = "start-prerequisite:" + save_id
        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            previous = connection.execute(
                "SELECT response_json FROM mutation_requests WHERE scope=? AND request_id=?",
                (scope, body["request_id"])).fetchone()
            if previous:
                stored = loads(previous["response_json"])
                if stored["fingerprint"] != fingerprint:
                    raise DomainError("IDEMPOTENCY_CONFLICT", "request_id已用于不同起点处理", 409)
                connection.commit(); return stored["result"]
            state = self.initialize(save_id, connection)
            if state["state_version"] != body["expected_state_version"]:
                raise DomainError("STATE_VERSION_CONFLICT", "权威状态版本冲突", 409)
            prerequisite = state["location"].get("prerequisite", {})
            if prerequisite.get("status") != "required":
                raise DomainError("START_PREREQUISITE_ALREADY_RESOLVED", "起点前置条件已处理", 409)
            old_location = state["location"]["id"]
            if resolution == "relocate":
                location_id = body.get("location_id")
                if location_id not in SAFE_PUBLIC_STARTS:
                    raise DomainError("INVALID_INPUT", "必须选择合法公开起点", 400,
                                      fields={"location_id": "不在可选公开地点中"})
                location = self.canonical_locations[location_id]
                state["location"] = {"id": location_id, "name": location["name"],
                                     "safeguards": location["safeguards"],
                                     "legacy_start_protection": False,
                                     "prerequisite": {"status": "satisfied", "requirements": [],
                                                      "resolution": "relocate", "options": []}}
            else:
                grants = prerequisite["requirements"]
                state["world_flags"]["legacy_start_prerequisites"] = {
                    "location_id": old_location, "grants": grants,
                    "source": "explicit_pre_opening_resolution"}
                prerequisite.update({"status": "satisfied",
                                     "resolution": "accept_legacy_protection", "options": []})
                state["location"]["legacy_start_protection"] = True
            state["state_version"] += 1
            now = utc_now()
            connection.execute(
                "UPDATE story_states SET state_version=?,state_json=?,updated_at=? WHERE save_id=?",
                (state["state_version"], dumps(state), now, save_id))
            result = {"save_id": save_id, "state_version": state["state_version"],
                      "location": state["location"], "resolved": True}
            connection.execute("INSERT INTO mutation_requests VALUES(?,?,?,?)",
                               (scope, body["request_id"], dumps({"fingerprint": fingerprint,
                                                                  "result": result}), now))
            connection.commit()
        return result

    def get_job(self, save_id, job_id):
        with self.database.connect() as connection:
            self.database.get_save(save_id, connection)
            row = connection.execute("SELECT * FROM narrative_jobs WHERE id=? AND save_id=?",
                                     (job_id, save_id)).fetchone()
        if not row:
            raise DomainError("NARRATIVE_JOB_NOT_FOUND", "叙事任务不存在", 404)
        return self._job_row(row)

    def list_queued(self):
        with self.database.connect() as connection:
            return [(row["save_id"], row["id"]) for row in connection.execute(
                "SELECT save_id,id FROM narrative_jobs WHERE status='queued' ORDER BY created_at").fetchall()]

    def claim(self, save_id, job_id):
        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            changed = connection.execute(
                "UPDATE narrative_jobs SET status='running',updated_at=? WHERE id=? AND save_id=? AND status='queued'",
                (utc_now(), job_id, save_id)).rowcount
            if not changed:
                connection.rollback(); return None
            job = connection.execute("SELECT * FROM narrative_jobs WHERE id=?", (job_id,)).fetchone()
            state_row = connection.execute("SELECT * FROM story_states WHERE save_id=?", (save_id,)).fetchone()
            state = self._state_row(state_row)
            if job["job_type"] == "reshape":
                turn = connection.execute("SELECT * FROM turns WHERE id=? AND save_id=?",
                                          (job["target_turn_id"], save_id)).fetchone()
                snapshot = connection.execute("SELECT state_json FROM turn_snapshots WHERE turn_id=?",
                                              (turn["id"],)).fetchone()
                frozen = loads(snapshot["state_json"], {})
                base_state = frozen["state"]
                base_state.setdefault("npcs", {})
                # Narration preferences are user settings, not rollbackable story effects.
                base_state["narration"] = copy.deepcopy(state["narration"])
                snapshot_memories = frozen["memories"]
            else:
                turn = None; base_state = state; snapshot_memories = None
            history_rows = connection.execute(
                "SELECT id,sequence,title,body,summary,action_type,action_json FROM turns "
                "WHERE save_id=? AND (? IS NULL OR sequence < ?) ORDER BY sequence",
                (save_id, turn["sequence"] if turn else None,
                 turn["sequence"] if turn else None)).fetchall()
            memories = (number_active_memories(snapshot_memories or [])
                        if job["job_type"] == "reshape" else
                        number_active_memories([self._memory_row(row) for row in connection.execute(
                            "SELECT * FROM memories WHERE save_id=? AND status='active' "
                            "ORDER BY updated_at,id", (save_id,)).fetchall()]))
            arcs = [self._arc_row(row) for row in connection.execute(
                "SELECT * FROM story_arcs WHERE save_id=? AND status='current' ORDER BY start_sequence",
                (save_id,)).fetchall()]
            covered = {(item["start_sequence"], item["end_sequence"])
                       for item in arcs if item["status"] == "current"}
            uncompressed = [dict(row) for row in history_rows
                            if not any(start <= row["sequence"] <= end for start, end in covered)]
            recent_ids = {item["id"] for item in uncompressed[-10:]}
            history = []
            for item in uncompressed:
                item["action"] = loads(item.pop("action_json"), {})
                if item["id"] not in recent_ids:
                    item.pop("body", None)
                    item["projection"] = "summary"
                else:
                    item["projection"] = "full"
                history.append(item)
            context_state = copy.deepcopy(base_state)
            terminal_quests = {key for key, value in context_state.get("regional_quests", {}).items()
                               if value.get("status") in TERMINAL_QUEST_STATES}
            context_state["regional_quests"] = {
                key: value for key, value in context_state.get("regional_quests", {}).items()
                if key not in terminal_quests}
            for item in history:
                action_value = item.get("action")
                if isinstance(action_value, dict):
                    for key in ("regional_quests", "quests"):
                        if isinstance(action_value.get(key), dict):
                            action_value[key] = {quest_id: quest for quest_id, quest in action_value[key].items()
                                                 if quest_id not in terminal_quests}
                for key in ("title", "summary", "body"):
                    text = item.get(key)
                    if isinstance(text, str):
                        for quest_id in terminal_quests:
                            text = text.replace(quest_id, "[terminal-regional-quest]")
                        item[key] = text
            memories = self._recall_memories(context_state, history, memories)
            claimed_memory_numbers = {
                memory["memory_number"]: memory["id"] for memory in memories
            }
            nodes = {row["id"]: dict(row) for row in connection.execute(
                "SELECT * FROM location_nodes WHERE save_id=?", (save_id,)).fetchall()}
            if job["job_type"] == "reshape":
                allowed_dynamic = set(base_state.get("locations", {}))
                nodes = {key: value for key, value in nodes.items()
                         if value.get("canonical") or key in allowed_dynamic}
            documents = load_revision_documents(connection, state["content_revision_id"])
            revision_manifest = load_revision_manifest(connection, state["content_revision_id"])
            connection.commit()
        recent = [item for item in history if item["projection"] == "full"]
        early = [item for item in history if item["projection"] == "summary"]
        request_input = loads(job["input_json"], {})
        if job["job_type"] == "reshape" and turn:
            request_input = {"action_type": "reshape",
                             "original_action": loads(turn["action_json"], {}),
                             "old_result": {key: turn[key] for key in ("id", "sequence", "title", "body", "summary")},
                             "reshape_guidance": request_input.get("guidance", "")}
        return {"job": self._job_row(job), "input": request_input,
                "current_state": state, "base_state": base_state,
                "context_state": context_state,
                "early_summaries": early, "recent_full_turns": recent,
                "memories": memories, "arcs": arcs, "location_nodes": nodes,
                "documents": documents, "revision_manifest": revision_manifest,
                "snapshot_memories": snapshot_memories,
                "claimed_memory_numbers": claimed_memory_numbers,
                "old_turn": dict(turn) if turn else None}

    @staticmethod
    def _recall_memories(state, history, memories, limit=20):
        try:
            from .canonical_npcs import CANONICAL_NPCS
        except ImportError:
            from canonical_npcs import CANONICAL_NPCS
        location_id = state.get("location", {}).get("id", "")
        recent_text = " ".join(
            str(value) for item in history[-10:] for value in
            (item.get("title", ""), item.get("summary", ""), item.get("body", "")))
        recalled = []
        for memory in memories:
            reasons = []
            if location_id and (location_id in memory.get("locations", []) or
                                any(location_id.startswith(value + ".") for value in memory.get("locations", []))):
                reasons.append("当前位置相关")
            people = []
            for person in memory.get("people", []):
                dynamic = state.get("npcs", {}).get(person, {})
                bond = state.get("bonds", {}).get(person, {})
                name = dynamic.get("name") or bond.get("npc_name") or CANONICAL_NPCS.get(person)
                if person and (person in recent_text or (name and name in recent_text)):
                    people.append(name or person)
            if people:
                reasons.append("近期人物相关：" + "、".join(people[:3]))
            keywords = [word for word in memory.get("keywords", []) if word and word in recent_text]
            if keywords:
                reasons.append("近期关键词相关：" + "、".join(keywords[:3]))
            if memory.get("unresolved"):
                reasons.append("包含未解决事项")
            score = memory.get("importance", 0) + 40 * bool(reasons)
            if reasons or memory.get("importance", 0) >= 70:
                recalled.append((score, memory.get("updated_at", ""), {
                    **copy.deepcopy(memory),
                    "recall_reason": "；".join(reasons) if reasons else "高重要度长期记忆"}))
        recalled.sort(key=lambda item: (item[0], item[1]), reverse=True)
        return [item[2] for item in recalled[:limit]]

    def cancel(self, save_id, job_id, body):
        self.database._validate_request_id(body)
        if set(body) != {"request_id", "expected_state_version"}:
            raise DomainError("INVALID_INPUT", "取消请求字段无效", 400)
        if type(body["expected_state_version"]) is not int:
            raise DomainError("INVALID_INPUT", "expected_state_version无效", 400)
        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            state = self.initialize(save_id, connection)
            if state["state_version"] != body["expected_state_version"]:
                raise DomainError("STATE_VERSION_CONFLICT", "权威状态版本冲突", 409)
            row = connection.execute("SELECT * FROM narrative_jobs WHERE id=? AND save_id=?",
                                     (job_id, save_id)).fetchone()
            if not row:
                raise DomainError("NARRATIVE_JOB_NOT_FOUND", "叙事任务不存在", 404)
            status = "cancelled" if row["status"] == "queued" else (
                "cancel_requested" if row["status"] == "running" else row["status"])
            connection.execute("UPDATE narrative_jobs SET status=?,updated_at=? WHERE id=?",
                               (status, utc_now(), job_id))
            row = connection.execute("SELECT * FROM narrative_jobs WHERE id=?", (job_id,)).fetchone()
            connection.commit()
        return self._job_row(row)

    def set_context_manifest(self, job_id, manifest):
        with self.database.connect() as connection:
            connection.execute("UPDATE narrative_jobs SET context_manifest_json=?,updated_at=? WHERE id=?",
                               (dumps(manifest), utc_now(), job_id))

    def fail(self, save_id, job_id, code, message, retryable=False):
        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT status FROM narrative_jobs WHERE id=? AND save_id=?",
                                     (job_id, save_id)).fetchone()
            if not row or row["status"] not in {"running", "cancel_requested"}:
                connection.rollback(); return
            status = "cancelled" if row["status"] == "cancel_requested" else "failed"
            connection.execute(
                "UPDATE narrative_jobs SET status=?,error_code=?,error_message=?,retryable=?,updated_at=? WHERE id=?",
                (status, code, message[:2000], int(retryable), utc_now(), job_id))
            connection.commit()

    def complete_turn(self, claimed, response):
        save_id = claimed["job"]["save_id"]
        job_id = claimed["job"]["id"]
        job_type = claimed["job"]["type"]
        action = claimed["input"]
        base_state = claimed["base_state"]
        revision_quests = self._revision_quests(claimed["documents"], claimed["revision_manifest"])
        regional_ids = {item["id"] for item in revision_quests}
        try:
            selected = self.content_registry.select_quests(
                base_state, claimed["location_nodes"],
                revision_quests)
            quest_context = {item["id"]: item for item in selected}
            frozen_locations = {
                item["id"]: {**item, "safeguards": []}
                for item in claimed["revision_manifest"].get("location_graph", [])
            } or self.canonical_locations
            frozen_canonical_npcs = {
                item["id"]: item["name"]
                for item in claimed["revision_manifest"].get("canonical_npcs", [])
            }
            decision = adjudicate(base_state, response, frozen_locations, regional_ids,
                                  quest_context, claimed["input"],
                                  {item["id"]: item for item in revision_quests},
                                  canonical_npcs=frozen_canonical_npcs)
        except ContractError:
            raise
        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            job = connection.execute("SELECT * FROM narrative_jobs WHERE id=? AND save_id=?",
                                     (job_id, save_id)).fetchone()
            state_row = connection.execute("SELECT * FROM story_states WHERE save_id=?", (save_id,)).fetchone()
            current = self._state_row(state_row)
            if not job or job["status"] == "cancel_requested":
                if job:
                    connection.execute("UPDATE narrative_jobs SET status='cancelled',updated_at=? WHERE id=?",
                                       (utc_now(), job_id)); connection.commit()
                else: connection.rollback()
                return "cancelled"
            if job["status"] != "running":
                connection.rollback(); return job["status"]
            if current["state_version"] != job["source_state_version"]:
                connection.execute(
                    "UPDATE narrative_jobs SET status='stale',error_code='NARRATIVE_STALE',"
                    "error_message='权威状态已变化',updated_at=? WHERE id=?", (utc_now(), job_id))
                connection.commit(); return "stale"
            if job_type == "reshape" and current["current_turn_id"] != job["target_turn_id"]:
                connection.execute(
                    "UPDATE narrative_jobs SET status='stale',error_code='NARRATIVE_STALE',"
                    "error_message='最新节点已变化',updated_at=? WHERE id=?", (utc_now(), job_id))
                connection.commit(); return "stale"
            now = utc_now()
            new_state = decision["state"]
            new_state["state_version"] = current["state_version"] + 1
            if job_type == "reshape":
                turn = connection.execute("SELECT * FROM turns WHERE id=?", (job["target_turn_id"],)).fetchone()
                turn_id = turn["id"]
                version_number = connection.execute(
                    "SELECT COALESCE(MAX(version_number),0)+1 FROM turn_versions WHERE turn_id=?",
                    (turn_id,)).fetchone()[0]
                connection.execute(
                    "UPDATE effect_receipts SET status='revoked' WHERE turn_id=? AND status='active'", (turn_id,))
                connection.execute(
                    "DELETE FROM reputation_change_history WHERE turn_version_id IN "
                    "(SELECT id FROM turn_versions WHERE turn_id=?)", (turn_id,))
                connection.execute(
                    "DELETE FROM location_nodes WHERE save_id=? AND canonical=0 AND created_turn_version_id IN "
                    "(SELECT id FROM turn_versions WHERE turn_id=?)", (save_id, turn_id))
                self._restore_memories(connection, save_id, claimed["snapshot_memories"] or [])
                snapshot_locations = base_state.get("locations", {})
                current_dynamic = connection.execute(
                    "SELECT id FROM location_nodes WHERE save_id=? AND canonical=0", (save_id,)).fetchall()
                for row in current_dynamic:
                    if row["id"] not in snapshot_locations:
                        connection.execute("DELETE FROM location_nodes WHERE save_id=? AND id=?",
                                           (save_id, row["id"]))
                for location in snapshot_locations.values():
                    connection.execute(
                        "INSERT OR REPLACE INTO location_nodes VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                        (save_id, location["id"], location["name"], location["type"],
                         location["scope"], location["parent_id"], location["region_id"],
                         location.get("jurisdiction_id"), location["description"], 0,
                         location.get("created_turn_version_id")))
                sequence = turn["sequence"]
            else:
                turn_id, version_number = new_id(), 1
                sequence = connection.execute(
                    "SELECT COALESCE(MAX(sequence),0)+1 FROM turns WHERE save_id=?", (save_id,)).fetchone()[0]
                snapshot = {"state": base_state, "memories": [self._memory_row(row) for row in connection.execute(
                    "SELECT * FROM memories WHERE save_id=?", (save_id,)).fetchall()]}
            version_id = new_id()
            changes = decision["changes"]
            for warning in response["warnings"]:
                changes.append({"kind": "warning", "key": "gm_warning", "old": None,
                                "new": warning, "reason": "模型识别的规则警告"})
            changes_json = dumps(changes)
            proposals = response["proposals"]
            narrative = response["narrative"]
            fallback_used = 0
            if not narrative["chronicle_summary"].strip():
                first_paragraph = next((part.strip() for part in narrative["body"].split("\n")
                                        if part.strip()), "本节点已提交。")
                narrative["chronicle_summary"] = f"{narrative['title']}：{first_paragraph[:500]}"
                fallback_used = 1
            if job_type != "reshape":
                connection.execute(
                    "INSERT INTO turns VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (turn_id, save_id, sequence, None, job_type, dumps(action), "",
                     "", "", "[]", "[]", current["state_version"],
                     new_state["state_version"], now, now))
            connection.execute(
                "INSERT INTO turn_versions(id,turn_id,save_id,version_number,raw_response_json,"
                "proposals_json,authoritative_changes_json,prompt_version,content_revision_id,model,"
                "created_at,action_json,generated_ids_json) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (version_id, turn_id, save_id, version_number, dumps(response), dumps(proposals),
                 changes_json, claimed["revision_manifest"]["prompt_version"],
                 current["content_revision_id"], claimed.get("provider_model", ""), now,
                 dumps(action), dumps(decision["generated_ids"])))
            if job_type == "reshape":
                connection.execute(
                    "UPDATE turns SET current_version_id=?,title=?,body=?,summary=?,options_json=?,"
                    "changes_json=?,state_version_after=?,updated_at=? WHERE id=?",
                    (version_id, narrative["title"], narrative["body"], narrative["chronicle_summary"],
                     dumps(narrative["suggested_options"]), changes_json, new_state["state_version"],
                     now, turn_id))
            else:
                connection.execute(
                    "UPDATE turns SET current_version_id=?,title=?,body=?,summary=?,options_json=?,"
                    "changes_json=?,updated_at=? WHERE id=?",
                    (version_id, narrative["title"], narrative["body"], narrative["chronicle_summary"],
                     dumps(narrative["suggested_options"]), changes_json, now, turn_id))
                connection.execute("INSERT INTO turn_snapshots VALUES(?,?,?,?,?)",
                                   (turn_id, save_id, "turn-snapshot/1", dumps(snapshot), now))
            new_state["current_turn_id"] = turn_id
            for item in decision["new_locations"]:
                item["created_turn_version_id"] = version_id
                connection.execute("INSERT INTO location_nodes VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                                   (save_id, item["id"], item["name"], item["type"], item["scope"],
                                    item["parent_id"], item["region_id"], item.get("jurisdiction_id"),
                                    item["description"], 0, version_id))
            for item in decision["new_npcs"]:
                item["created_turn_version_id"] = version_id
                new_state["npcs"][item["id"]] = item
            for effect_key, kind, payload in decision["receipts"]:
                connection.execute("INSERT INTO effect_receipts VALUES(?,?,?,?,?,?,?,?,?)",
                                   (new_id(), save_id, turn_id, version_id, effect_key, kind,
                                    receipt_hash(payload), "active", now))
            connection.execute(
                "INSERT INTO journals VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(turn_id) DO UPDATE SET "
                "title=excluded.title,summary=excluded.summary,location_id=excluded.location_id,"
                "time_label=excluded.time_label,changes_json=excluded.changes_json,updated_at=excluded.updated_at",
                (turn_id, save_id, sequence, narrative["title"], narrative["chronicle_summary"],
                 new_state["location"]["id"], new_state["time"]["label"], changes_json,
                 fallback_used, now))
            for audit in decision["reputation_audit"]:
                connection.execute("INSERT INTO reputation_change_history VALUES(?,?,?,?,?,?,?,?,?)",
                                   (new_id(), save_id, version_id, audit["key"], audit["old"], audit["new"],
                                    audit["public_reason"], 1, now))
            self._apply_memories(connection, save_id, turn_id, version_id,
                                 decision["memory_operations"], now,
                                 claimed.get("claimed_memory_numbers", {}))
            connection.execute(
                "UPDATE story_states SET state_version=?,current_turn_id=?,state_json=?,updated_at=? WHERE save_id=?",
                (new_state["state_version"], turn_id, dumps(new_state), now, save_id))
            result = {"turn_id": turn_id, "sequence": sequence,
                      "state_version": new_state["state_version"]}
            connection.execute(
                "UPDATE narrative_jobs SET status='succeeded',result_json=?,updated_at=? WHERE id=?",
                (dumps(result), now, job_id))
            connection.commit()
        return "succeeded"

    @staticmethod
    def _memory_row(row):
        if isinstance(row, dict) and "people" in row:
            return copy.deepcopy(row)
        return {"id": row["id"], "save_id": row["save_id"], "status": row["status"],
                "kind": row["kind"], "summary": row["summary"], "importance": row["importance"],
                "people": loads(row["people_json"], []), "locations": loads(row["locations_json"], []),
                "keywords": loads(row["keywords_json"], []), "facts": loads(row["facts_json"], []),
                "unresolved": loads(row["unresolved_json"], []), "superseded_by": row["superseded_by"],
                "source_turn_id": row["source_turn_id"],
                "source_turn_version_id": row["source_turn_version_id"], "updated_at": row["updated_at"]}

    @staticmethod
    def _insert_memory(connection, memory):
        connection.execute("INSERT INTO memories VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                           (memory["id"], memory["save_id"], memory["status"], memory["kind"],
                            memory["summary"], memory["importance"], dumps(memory["people"]),
                            dumps(memory["locations"]), dumps(memory["keywords"]), dumps(memory["facts"]),
                            dumps(memory["unresolved"]), memory.get("superseded_by"),
                            memory["source_turn_id"], memory["source_turn_version_id"], memory["updated_at"]))
        connection.execute("INSERT INTO memory_sources VALUES(?,?)",
                           (memory["id"], memory["source_turn_version_id"]))

    def _restore_memories(self, connection, save_id, memories):
        connection.execute("DELETE FROM memories WHERE save_id=?", (save_id,))
        for memory in memories:
            restored = copy.deepcopy(memory)
            restored.pop("memory_number", None)
            restored["save_id"] = save_id
            self._insert_memory(connection, restored)

    def _apply_memories(self, connection, save_id, turn_id, version_id, operations, now,
                        claimed_memory_numbers=None):
        if claimed_memory_numbers is None:
            numbered = number_active_memories([
                self._memory_row(row) for row in connection.execute(
                    "SELECT * FROM memories WHERE save_id=? AND status='active' ORDER BY updated_at,id",
                    (save_id,)).fetchall()
            ])
            number_to_id = {memory["memory_number"]: memory["id"] for memory in numbered}
        else:
            number_to_id = dict(claimed_memory_numbers)
        delete_numbers = [int(item["memory_id"]) for item in operations
                          if item["operation"] != "create"]
        if len(delete_numbers) != len(set(delete_numbers)):
            raise ContractError("同一长期记忆编号每轮只能删除一次")
        if any(number not in number_to_id for number in delete_numbers):
            raise ContractError("删除编号不是本回合可见的活动长期记忆")
        created = 0
        for item in operations:
            if item["operation"] == "create":
                created += 1
                if created > 10:
                    raise ContractError("单回合长期记忆过多")
                duplicate = connection.execute(
                    "SELECT id FROM memories WHERE save_id=? AND status='active' AND summary=?",
                    (save_id, item["summary"])).fetchone()
                if duplicate:
                    continue
                memory = {"id": new_id(), "save_id": save_id, "status": "active",
                          "kind": item["kind"], "summary": item["summary"],
                          "importance": item["importance"], "people": item["people"],
                          "locations": item["locations"], "keywords": item["keywords"],
                          "facts": item["facts"], "unresolved": item["unresolved"],
                          "superseded_by": None, "source_turn_id": turn_id,
                          "source_turn_version_id": version_id, "updated_at": now}
                self._insert_memory(connection, memory)
            else:
                memory_id = number_to_id[int(item["memory_id"])]
                connection.execute("DELETE FROM memories WHERE id=? AND save_id=?",
                                   (memory_id, save_id))

    def list_turns(self, save_id, cursor=0, limit=50, enabled=False):
        self.initialize(save_id)
        with self.database.connect() as connection:
            if enabled:
                rows = connection.execute(
                    "SELECT * FROM turns WHERE save_id=? AND sequence>? ORDER BY sequence LIMIT ?",
                    (save_id, cursor, limit + 1)).fetchall()
            else:
                rows = connection.execute("SELECT * FROM turns WHERE save_id=? ORDER BY sequence", (save_id,)).fetchall()
        has_more = enabled and len(rows) > limit
        rows = rows[:limit] if enabled else rows
        return {"items": [self._turn_row(row) for row in rows],
                **({"next_cursor": rows[-1]["sequence"] if has_more and rows else None}
                   if enabled else {})}

    @staticmethod
    def _turn_row(row):
        return {"id": row["id"], "save_id": row["save_id"], "sequence": row["sequence"],
                "current_version_id": row["current_version_id"], "action_type": row["action_type"],
                "action": loads(row["action_json"], {}), "title": row["title"], "body": row["body"],
                "summary": row["summary"], "suggested_options": loads(row["options_json"], []),
                "authoritative_changes": loads(row["changes_json"], []),
                "state_version_before": row["state_version_before"],
                "state_version_after": row["state_version_after"],
                "created_at": row["created_at"], "updated_at": row["updated_at"]}

    def get_turn(self, save_id, turn_id):
        with self.database.connect() as connection:
            self.database.get_save(save_id, connection)
            row = connection.execute("SELECT * FROM turns WHERE id=? AND save_id=?", (turn_id, save_id)).fetchone()
            if not row:
                raise DomainError("TURN_NOT_FOUND", "剧情节点不存在", 404)
            versions = connection.execute(
                "SELECT id,version_number,prompt_version,content_revision_id,model,created_at FROM turn_versions "
                "WHERE turn_id=? ORDER BY version_number", (turn_id,)).fetchall()
        result = self._turn_row(row); result["versions"] = [dict(item) for item in versions]
        return result

    @staticmethod
    def _arc_row(row):
        return {"id": row["id"], "level": row["level"], "start_sequence": row["start_sequence"],
                "end_sequence": row["end_sequence"], "title": row["title"], "summary": row["summary"],
                "key_events": loads(row["key_events_json"], []),
                "unresolved": loads(row["unresolved_json"], []), "status": row["status"],
                "job_id": row["job_id"], "created_at": row["created_at"]}

    def projections(self, save_id, kind, cursor=0, limit=50, enabled=False):
        state = self.get_state(save_id)
        if kind == "character-state": return state["character"] | {"state_version": state["state_version"]}
        if kind == "inventory":
            copper = state["currency_copper"]
            return {"items": list(state["inventory"].values()), "currency_copper": copper,
                    "currency": {"gold": copper // 10000, "silver": (copper % 10000) // 100,
                                 "copper": copper % 100}, "state_version": state["state_version"]}
        if kind == "quests":
            all_quests = list(state["quests"].values()) + list(state["regional_quests"].values())
            return {"active": [item for item in all_quests if item["status"] == "active"],
                    "state_version": state["state_version"]}
        if kind == "bonds":
            return {"items": list(state["bonds"].values()), "state_version": state["state_version"]}
        if kind == "reputations":
            local = self.local_reputation(save_id, state)
            return {"items": [state["reputations"][key] for key in REPUTATION_KEYS],
                    "primary_key": "continental_overall", "local_modifier_key": local,
                    "state_version": state["state_version"]}
        with self.database.connect() as connection:
            if kind == "journals":
                rows = (connection.execute(
                    "SELECT * FROM journals WHERE save_id=? AND sequence>? ORDER BY sequence LIMIT ?",
                    (save_id, cursor, limit + 1)).fetchall() if enabled else
                    connection.execute("SELECT * FROM journals WHERE save_id=? ORDER BY sequence", (save_id,)).fetchall())
                has_more = enabled and len(rows) > limit
                rows = rows[:limit] if enabled else rows
                return {"items": [{"turn_id": r["turn_id"], "sequence": r["sequence"], "title": r["title"],
                                   "summary": r["summary"], "location_id": r["location_id"],
                                   "time_label": r["time_label"], "changes": loads(r["changes_json"], [])}
                                  for r in rows],
                        **({"next_cursor": rows[-1]["sequence"] if has_more and rows else None}
                           if enabled else {})}
            if kind == "memories":
                rows = [self._memory_row(r) for r in connection.execute(
                    "SELECT * FROM memories WHERE save_id=? ORDER BY updated_at,id",
                    (save_id,)).fetchall()]
                return {"items": number_active_memories(rows)}
            if kind == "memory":
                turns = [self._turn_row(r) for r in connection.execute(
                    "SELECT * FROM turns WHERE save_id=? ORDER BY sequence", (save_id,)).fetchall()]
                arcs = [self._arc_row(r) for r in connection.execute(
                    "SELECT * FROM story_arcs WHERE save_id=? ORDER BY start_sequence,level", (save_id,)).fetchall()]
                recent = turns[-10:]
                covered = {(a["start_sequence"], a["end_sequence"]) for a in arcs if a["status"] == "current"}
                summaries = [t for t in turns[:-10] if not any(start <= t["sequence"] <= end
                                                               for start, end in covered)]
                return {"recent_full_turns": recent, "summary_buffer": summaries,
                        "story_arcs": arcs, "policy": {"recent_full_count": 10,
                                                       "arc_turn_count": 25,
                                                       "original_history_preserved": True}}
        raise DomainError("NOT_FOUND", "投影不存在", 404)

    @staticmethod
    def _local_reputation(location_id):
        if location_id in REPUTATION_KEYS:
            return location_id if location_id != "continental_overall" else None
        mapping = {"noxvia": "court_of_veiled_night", "velansia": "skycrown_conclave",
                   "san_velia": "holy_see_sacred_radiance", "elf_forest": "court_of_sacred_tree",
                   "vargard": "valkeren_empire", "selavia_port": "southern_maritime_federation",
                   "abyssal_tides": "southern_maritime_federation"}
        root = location_id.split(".")[0]
        return mapping.get(root)

    def local_reputation(self, save_id, state):
        location_id = state["location"]["id"]
        direct = self._local_reputation(location_id)
        if direct:
            return direct
        with self.database.connect() as connection:
            rows = connection.execute(
                "SELECT id,parent_id,region_id,jurisdiction_id FROM location_nodes WHERE save_id=?",
                                      (save_id,)).fetchall()
        nodes = {row["id"]: dict(row) for row in rows}
        current, seen = location_id, set()
        while current and current not in seen:
            seen.add(current)
            node = nodes.get(current, {})
            for candidate in (node.get("jurisdiction_id"), node.get("region_id"),
                              node.get("parent_id")):
                key = self._local_reputation(candidate or "")
                if key:
                    return key
            current = node.get("parent_id")
        return None

    def story_view(self, save_id):
        state = self.get_state(save_id)
        latest = self.get_turn(save_id, state["current_turn_id"]) if state["current_turn_id"] else None
        with self.database.connect() as connection:
            active = connection.execute(
                "SELECT * FROM narrative_jobs WHERE save_id=? AND status IN ('queued','running','cancel_requested') "
                "AND job_type IN ('opening','turn','intervene','reshape') "
                "ORDER BY created_at LIMIT 1", (save_id,)).fetchone()
            active_arc = connection.execute(
                "SELECT * FROM narrative_jobs WHERE save_id=? AND status IN ('queued','running','cancel_requested') "
                "AND job_type IN ('turns_to_arc','arcs_to_arc') ORDER BY created_at LIMIT 1",
                (save_id,)).fetchone()
        return {"state": state, "latest_turn": latest, "active_job": self._job_row(active) if active else None,
                "active_arc_job": self._job_row(active_arc) if active_arc else None,
                "start_prerequisite": state["location"].get("prerequisite"),
                "can_open": latest is None, "can_act": latest is not None and active is None,
                "can_reshape": latest is not None and active is None}

    def create_arc_job(self, save_id, body, parent_arc_ids=None, automatic=False):
        if automatic:
            body = {"request_id": "pending-auto-arc",
                    "expected_state_version": self.get_state(save_id)["state_version"]}
        self._validate_write(body, {"request_id", "expected_state_version", "arc_ids"})
        arc_ids = parent_arc_ids if parent_arc_ids is not None else body.get("arc_ids")
        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            state = self.initialize(save_id, connection)
            if state["state_version"] != body["expected_state_version"]:
                raise DomainError("STATE_VERSION_CONFLICT", "权威状态版本冲突", 409)
            active = connection.execute(
                "SELECT id FROM narrative_jobs WHERE save_id=? AND status IN ('queued','running','cancel_requested') "
                "AND job_type IN ('turns_to_arc','arcs_to_arc')",
                (save_id,)).fetchone()
            if active:
                if automatic:
                    connection.rollback(); return None, False
                raise DomainError("NARRATIVE_JOB_ACTIVE", "该存档已有活动叙事任务", 409)
            if arc_ids:
                if not isinstance(arc_ids, list) or len(arc_ids) < 2 or any(not isinstance(x, str) for x in arc_ids):
                    raise DomainError("INVALID_INPUT", "arc_ids必须包含至少两个故事弧", 400)
                placeholders = ",".join("?" for _ in arc_ids)
                rows = connection.execute(
                    f"SELECT * FROM story_arcs WHERE save_id=? AND id IN ({placeholders}) AND status='current' "
                    "ORDER BY start_sequence", (save_id, *arc_ids)).fetchall()
                if len(rows) != len(arc_ids) or any(rows[i]["end_sequence"] + 1 != rows[i + 1]["start_sequence"]
                                                   for i in range(len(rows) - 1)):
                    raise DomainError("ARC_SOURCES_NOT_CONTIGUOUS", "故事弧来源必须连续且有效", 409)
                job_type = "arcs_to_arc"
                source = {"arc_ids": [r["id"] for r in rows], "start": rows[0]["start_sequence"],
                          "end": rows[-1]["end_sequence"]}
            else:
                current_ranges = [(r[0], r[1]) for r in connection.execute(
                    "SELECT start_sequence,end_sequence FROM story_arcs "
                    "WHERE save_id=? AND status='current'", (save_id,)).fetchall()]
                rows = connection.execute(
                    "SELECT * FROM turns WHERE save_id=? ORDER BY sequence", (save_id,)).fetchall()
                eligible = [r for r in rows[:-10] if not any(
                    start <= r["sequence"] <= end for start, end in current_ranges)]
                selected = None
                for index in range(max(0, len(eligible) - 24)):
                    batch = eligible[index:index + 25]
                    if len(batch) == 25 and all(batch[i]["sequence"] + 1 == batch[i + 1]["sequence"]
                                                for i in range(24)):
                        selected = batch; break
                if not selected:
                    if automatic:
                        connection.rollback(); return None, False
                    raise DomainError("ARC_SOURCE_NOT_READY", "没有连续25个未覆盖节点", 409)
                job_type = "turns_to_arc"
                source = {"turn_ids": [r["id"] for r in selected], "start": selected[0]["sequence"],
                          "end": selected[-1]["sequence"],
                          "version_ids": [r["current_version_id"] for r in selected]}
            fingerprint = dumps(source)
            if automatic:
                source_digest = hashlib.sha256(fingerprint.encode("utf-8")).hexdigest()[:24]
                body["request_id"] = "auto-arc:" + source_digest
                previous_source = connection.execute(
                    "SELECT * FROM narrative_jobs WHERE save_id=? AND job_type=? AND request_fingerprint=? "
                    "ORDER BY created_at DESC LIMIT 1", (save_id, job_type, fingerprint)).fetchone()
                if previous_source:
                    connection.commit()
                    return self._job_row(previous_source), False
            previous = connection.execute(
                "SELECT * FROM narrative_jobs WHERE save_id=? AND request_id=?",
                (save_id, body["request_id"])).fetchone()
            if previous:
                if previous["request_fingerprint"] != fingerprint:
                    raise DomainError("IDEMPOTENCY_CONFLICT", "request_id已用于不同故事弧请求", 409)
                connection.commit(); return self._job_row(previous), False
            now, job_id = utc_now(), new_id()
            connection.execute("INSERT INTO narrative_jobs VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                               (job_id, save_id, body["request_id"], fingerprint, job_type,
                                state["state_version"], None, "queued", dumps(source), None, None,
                                None, None, 0, now, now))
            row = connection.execute("SELECT * FROM narrative_jobs WHERE id=?", (job_id,)).fetchone()
            connection.commit()
        return self._job_row(row), True

    def claim_arc(self, claimed):
        source = claimed["input"]
        save_id = claimed["job"]["save_id"]
        with self.database.connect() as connection:
            if claimed["job"]["type"] == "turns_to_arc":
                rows = [connection.execute("SELECT * FROM turns WHERE id=? AND save_id=?",
                                           (turn_id, save_id)).fetchone() for turn_id in source["turn_ids"]]
                frozen = [self._turn_row(row) for row in rows]
            else:
                rows = [connection.execute("SELECT * FROM story_arcs WHERE id=? AND save_id=?",
                                           (arc_id, save_id)).fetchone() for arc_id in source["arc_ids"]]
                frozen = [self._arc_row(row) for row in rows]
        return frozen

    def complete_arc(self, claimed, response):
        save_id, job_id = claimed["job"]["save_id"], claimed["job"]["id"]
        source = claimed["input"]
        frozen = self.claim_arc(claimed)
        source_hash = hashlib.sha256(dumps(frozen).encode("utf-8")).hexdigest()
        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            job = connection.execute("SELECT * FROM narrative_jobs WHERE id=? AND save_id=?", (job_id, save_id)).fetchone()
            if job and job["status"] == "cancel_requested":
                connection.execute("UPDATE narrative_jobs SET status='cancelled',updated_at=? WHERE id=?",
                                   (utc_now(), job_id)); connection.commit(); return "cancelled"
            if not job or job["status"] != "running":
                connection.rollback(); return job["status"] if job else "missing"
            now, arc_id = utc_now(), new_id()
            level = 1
            if job["job_type"] == "arcs_to_arc":
                level = max(item["level"] for item in frozen) + 1
            connection.execute("INSERT INTO story_arcs VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                               (arc_id, save_id, level, source["start"], source["end"], response["title"],
                                response["summary"], dumps(response["key_events"]),
                                dumps(response["unresolved"]), source_hash, "current", job_id, now))
            if job["job_type"] == "turns_to_arc":
                for index, (turn_id, version_id) in enumerate(zip(source["turn_ids"], source["version_ids"]), 1):
                    connection.execute("INSERT INTO story_arc_sources VALUES(?,?,?,?)",
                                       (arc_id, turn_id, version_id, index))
            else:
                for index, parent in enumerate(source["arc_ids"], 1):
                    connection.execute("INSERT INTO story_arc_parent_sources VALUES(?,?,?)",
                                       (arc_id, parent, index))
                    connection.execute("UPDATE story_arcs SET status='superseded' WHERE id=?", (parent,))
            connection.execute("INSERT INTO context_policies VALUES(?,?,?,?,?,?)",
                               (new_id(), save_id, job["job_type"], dumps(source), arc_id, now))
            result = {"story_arc_id": arc_id, "start_sequence": source["start"],
                      "end_sequence": source["end"]}
            connection.execute("UPDATE narrative_jobs SET status='succeeded',result_json=?,updated_at=? WHERE id=?",
                               (dumps(result), now, job_id))
            connection.commit()
        return "succeeded"
