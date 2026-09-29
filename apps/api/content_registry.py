"""Immutable source snapshots and stable prompt assembly."""

import hashlib
import json
import re
from pathlib import Path

try:
    from .contract_registry import contract_from_documents
except ImportError:
    from contract_registry import contract_from_documents


RULE_DOCUMENTS = (
    ("rule.gm_core", "GM模型核心行为规则.md"),
    ("rule.attributes", "短期与长期属性设计.md"),
    ("rule.experience", "经验值功能设定.md"),
    ("rule.power", "战力值功能设定.md"),
    ("rule.narration", "叙述设置项.md"),
    ("rule.reputation_bonds", "声望与羁绊系统.md"),
)
CANON_DOCUMENTS = (
    ("canon.foundation", "世界基础设定集.md"),
    ("canon.geography", "世界地理设定.md"),
    ("canon.races", "可玩种族设定集.md"),
    ("canon.factions", "世界势力设定集.md"),
    ("canon.people", "世界人物志.md"),
    ("canon.wonders", "世界奇观设定集.md"),
    ("canon.misc", "世界杂项设定.md"),
    ("canon.currency", "货币系统设定.md"),
)
PROTOCOL_DOCUMENTS = (
    ("protocol.boundary", "content/system_boundary.txt"),
    ("protocol.regional_quests", "content/regional_quest_protocol.txt"),
)
CONTRACT_DOCUMENTS = (
    ("contract.gm_turn.text", "content/output_contract.txt"),
    ("contract.gm_turn.schema", "content/gm_turn.schema.json"),
    ("contract.story_arc.text", "content/story_arc_contract.txt"),
    ("contract.story_arc.schema", "content/story_arc.schema.json"),
)
TERMINAL_QUEST_STATES = {"completed", "declined", "failed", "abandoned"}
PLAYER_ADDRESS_PROTOCOL_VERSION = "player-address/1"
PLAYER_ADDRESS_MODES = {"full_name", "given_name", "second_person"}

QUEST_SPECS = (
    {
        "id": "regional_main.lost_tidevoice", "name": "遗失的潮音",
        "heading": "# 南海自由联邦地区主线：遗失的潮音",
        "next_heading": "# 云端天境地区主线：与风同行",
        "trigger": "玩家首次进入南海自由联邦地区后，可在任务板发现带特殊标记的匿名寻物委托。任务非强制。",
        "description": "帮助海族歌者露米娅沿运输路线寻找演出所需的潮音珠。",
        "roots": ("selavia_port.adventurers_guild",),
        "rewards": {"items": [{"id": "regional.reward.lumia_front_row_seat", "name": "露米娅演出最前排特别席位",
                                  "description": "露米娅正常演出的最前排特别席位。"},
                                 {"id": "regional.reward.memory_bottle", "name": "记忆瓶",
                                  "description": "保存此次共同冒险的一段记忆。"}],
                    "bonds": [{"npc_id": "canon.npc.lumia_seir", "npc_name": "露米娅·塞伊尔",
                               "relation_type": "friend", "required": True}],
                    "world_flags": ["met_lumia_seir", "lumia_recognizes_player"]},
    },
    {
        "id": "regional_main.walking_with_wind", "name": "与风同行",
        "heading": "# 云端天境地区主线：与风同行",
        "next_heading": "下面整理成适合玩家进入诺克维亚时临时注入模型上下文的压缩故事线。",
        "trigger": "玩家在阿尔凯昂天衡附近发现一名独自坐在长椅上叹气的羽族少女，并主动上前搭话。任务非强制。",
        "description": "与羽族公主伊蕾娅游览浮空群岛，在旅途中认识云端天境。",
        "roots": ("velansia.central_plaza",),
        "rewards": {"items": [{"id": "regional.reward.basic_flight_device", "name": "基础飞行魔导器",
                                  "description": "适用于普通飞行，不适合极端天气和高危险空域。",
                                  "condition": {"race_not": "featherfolk"}},
                                 {"id": "regional.reward.wind_accessory", "name": "风属性魔导饰品",
                                  "description": "轻微提升对风属性魔力的感知。"}],
                    "bonds": [{"npc_id": "canon.npc.ileia_veylanth", "npc_name": "伊蕾娅·维兰瑟",
                               "relation_type": "friend", "required": True}],
                    "world_flags": ["met_ileia_veylanth", "completed_walking_with_wind"]},
    },
    {
        "id": "regional_main.mia_day_out", "name": "“米娅”的一日出行",
        "heading": "# 魔族地区主线：“米娅”的一日出行",
        "next_heading": "# 精灵地区主线：圣树下的相遇",
        "trigger": "玩家在街上遇见一名披着黑色斗篷、匆忙逃跑的魔族少女。任务非强制。",
        "description": "帮助自称“米娅”的少女摆脱追踪，并陪她体验诺克维亚的一日生活。",
        "roots": ("noxvia.street",),
        "rewards": {"items": [{"id": "regional.reward.lilia_soul_necklace", "name": "莉莉娅的护魂项链",
                                  "description": "可抵挡一次强力精神或灵魂攻击，随后失效。"}],
                    "bonds": [{"npc_id": "canon.npc.lilia_noxveil", "npc_name": "莉莉娅·诺克维尔",
                               "relation_type": "friend", "required": True}],
                    "world_flags": ["met_lilia_noxveil", "lilia_treats_player_as_friend"]},
    },
    {
        "id": "regional_main.sacred_tree_encounter", "name": "圣树下的相遇",
        "heading": "# 精灵地区主线：圣树下的相遇",
        "next_heading": "# 西部地区主线：沙海之歌",
        "trigger": "玩家遇见正在教一群精灵孩童射箭的圣树圣女莉瑟娅，并通过观看、搭话、协助教学等方式引起她的注意。任务非强制。",
        "description": "与圣树圣女莉瑟娅交流或同行，按自己的兴趣了解精灵之森。",
        "roots": ("elf_forest.main_settlement.street",),
        "rewards": {"items": [{"id": "regional.reward.verdant_charm", "name": "翠生护符",
                                  "description": "可释放生命魔力恢复一定身体伤势。"}],
                    "bonds": [{"npc_id": "canon.npc.lysia_aevilan", "npc_name": "莉瑟娅·艾维兰",
                               "relation_type": "acquaintance", "required": True}],
                    "world_flags": ["met_lysia_aevilan"]},
    },
    {
        "id": "regional_main.song_of_sandsea", "name": "沙海之歌",
        "heading": "# 西部地区主线：沙海之歌",
        "next_heading": "# 学院地区主线：学院入学日",
        "trigger": "玩家抵达西部沙漠边缘城市萨赫拉维亚，并遇见正在招募护卫的大型官方商队。任务非强制。",
        "description": "加入娜希娅率领的官方商队，沿西部商路前往熔脊龙谷。",
        "roots": ("sahravia",),
        "rewards": {"items": [{"id": "regional.reward.sahravia_badge", "name": "萨赫拉维亚徽章",
                                  "description": "完成整段西行旅程的纪念。"}],
                    "bonds": [{"npc_id": "canon.npc.nashia_safar", "npc_name": "娜希娅·萨法尔",
                               "relation_type": "former_companion", "required": True}],
                    "world_flags": ["met_nashia_safar", "completed_sandsea_caravan"]},
    },
    {
        "id": "regional_main.grand_academy_first_day", "name": "学院入学日",
        "heading": "# 学院地区主线：学院入学日",
        "next_heading": None,
        "trigger": "玩家明确以入学为目的前往学院。",
        "description": "完成心性与天赋测试、选择学院，并在指引员带领下度过入学第一日。",
        "roots": ("grand_academy.central_plaza",),
        "rewards": {"items": [{"id": "regional.reward.academy_student_card", "name": "学院学生卡",
                                  "description": "用于学院通行、身份认证和学生权限。"}],
                    "bonds": [],
                    "world_flags": ["grand_academy_student", "completed_academy_first_day"]},
    },
)


def _sha(value):
    return hashlib.sha256(value).hexdigest()


def _decode(raw):
    has_bom = raw.startswith(b"\xef\xbb\xbf")
    return raw.decode("utf-8-sig"), has_bom


def _newline_style(raw):
    if b"\r\n" in raw:
        return "crlf"
    if b"\r" in raw:
        return "cr"
    return "lf"


def revision_identity(manifest):
    digest_material = json.dumps({
        "documents": [(item["document_id"], item["raw_sha256"])
                      for item in manifest["documents"]],
        "quest_cards": [(item["id"], item["normal_context_card"], tuple(item["roots"]),
                         item.get("rewards", {}))
                        for item in manifest["quests"]],
    }, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    revision_id = "content-v1-" + _sha(digest_material)[:24]
    prompt_version = "gm-prompt-v1-" + _sha(
        (revision_id + ":gm-turn/1").encode("utf-8"))[:16]
    return revision_id, prompt_version


def player_address_directive(state):
    """Resolve explicit name forms while preserving unsegmented names verbatim."""
    identity = state.get("character", {}).get("identity", {})
    raw_name = identity.get("name", "")
    full_name = raw_name.strip() if isinstance(raw_name, str) else ""
    parts = [part.strip() for part in re.split(r"[·・\s\-‐‑‒–—]+", full_name)
             if part.strip()]
    given_name = parts[0] if parts else full_name
    surname = parts[-1] if len(parts) >= 2 else None
    gender = identity.get("gender", "")
    normalized_gender = gender.strip().lower() if isinstance(gender, str) else ""
    title = None
    if normalized_gender in {"女", "女性", "female", "woman"}:
        title = "小姐"
    elif normalized_gender in {"男", "男性", "male", "man"}:
        title = "先生"
    formal_address = ((surname if surname else full_name) + title
                      if full_name and title else None)
    mode = (state.get("narration") or {}).get("player_address", "second_person")
    if mode not in PLAYER_ADDRESS_MODES:
        mode = "second_person"
    resolved = (full_name if mode == "full_name" else given_name
                if mode == "given_name" else "你")
    return {
        "protocol_version": PLAYER_ADDRESS_PROTOCOL_VERSION,
        "mode": mode,
        "gm_narration_address": resolved or "玩家角色",
        "name_forms": {"full_name": full_name or None, "given_name": given_name or None,
                       "surname": surname,
                       "structure": "given_surname_separated" if surname else "unsegmented"},
        "npc_address_examples": {
            "formal_or_stranger": formal_address,
            "friend_or_familiar": given_name or None,
            "written": full_name or None,
        },
        "instructions": [
            "GM叙述者称呼玩家角色时稳定使用gm_narration_address，不把其他姓名形式当作常规称呼",
            "本设置仅约束GM叙述者，不得据此改写NPC台词中的称呼",
            "NPC称呼由关系、场合与其确实知道的身份独立决定：尊称或陌生关系用姓+先生/小姐，朋友或熟悉关系用名，书面场合用全名",
            "姓名使用“·”“・”、空格或连字符等明确分隔符时按“名+姓”结构拆分，例如菲亚·维洛拉、菲亚 维洛拉、菲亚-维洛拉均识别为名“菲亚”、姓“维洛拉”",
            "不可拆分或只有名时由NPC结合语境自然调整，尊称可直接使用原始姓名+先生/小姐",
            "中文名及其他无间隔符姓名必须始终保持玩家输入的原始文字与顺序；不得擅自拆成姓和名、反转顺序或添加“·”，例如王子轩不得改成子轩·王",
            "性别称谓不适用或NPC不知道姓名时不得臆造性别、姓名或身份信息",
        ],
    }


class ContentRegistry:
    def __init__(self, api_directory=None):
        self.api_directory = Path(api_directory or Path(__file__).resolve().parent)
        self.workspace = self.api_directory.parents[1]
        self._documents = self._read_sources()
        quest_doc = next(item for item in self._documents
                         if item["document_id"] == "regional.source")
        self.quests = self._parse_quests(quest_doc["text_content"])
        provisional = {"documents": self._documents, "quests": [
            {"id": item["id"], "normal_context_card": item["normal_context_card"],
             "roots": list(item["roots"]), "rewards": item["rewards"]} for item in self.quests]}
        self.revision_id, self.prompt_version = revision_identity(provisional)

    def _read_sources(self):
        documents = []
        groups = (("protocol", PROTOCOL_DOCUMENTS), ("rule", RULE_DOCUMENTS),
                  ("contract", CONTRACT_DOCUMENTS),
                  ("canon", CANON_DOCUMENTS),
                  ("regional", (("regional.source", "地区引导主线.md"),)))
        for category, entries in groups:
            for ordinal, (document_id, relative) in enumerate(entries, 1):
                path = (self.api_directory / relative if relative.startswith("content/")
                        else self.workspace / relative)
                before = path.stat()
                raw = path.read_bytes()
                after = path.stat()
                if (before.st_mtime_ns, before.st_size) != (after.st_mtime_ns, after.st_size):
                    raise RuntimeError(f"content source changed during read: {path}")
                text, has_bom = _decode(raw)
                documents.append({
                    "document_id": document_id, "category": category,
                    "ordinal": ordinal, "source_path": relative.replace("\\", "/"),
                    "raw_bytes": raw, "text_content": text,
                    "raw_sha256": _sha(raw), "text_sha256": _sha(text.encode("utf-8")),
                    "encoding": "utf-8", "has_bom": has_bom,
                    "newline_style": _newline_style(raw), "byte_count": len(raw),
                    "character_count": len(text), "line_count": len(text.splitlines()),
                })
        return documents

    @staticmethod
    def _parse_quests(source):
        quests = []
        for spec in QUEST_SPECS:
            start = source.index(spec["heading"])
            end = source.index(spec["next_heading"], start) if spec["next_heading"] else len(source)
            full = source[start:end].rstrip() + "\n"
            quest = dict(spec)
            quest["full_source_markdown"] = full
            quest["start_character"] = start
            quest["end_character"] = end
            quest["text_sha256"] = _sha(full.encode("utf-8"))
            quest["normal_context_card"] = {
                "任务名": spec["name"], "简介": spec["description"],
                "触发条件": spec["trigger"],
            }
            quests.append(quest)
        return tuple(quests)

    @property
    def manifest(self):
        return {
            "revision_id": self.revision_id,
            "protocol_version": "content-container/1",
            "prompt_version": self.prompt_version,
            "documents": [{key: value for key, value in item.items()
                           if key not in {"raw_bytes", "text_content"}}
                          for item in self._documents],
            "quests": [{"id": q["id"], "name": q["name"],
                        "normal_context_card": q["normal_context_card"],
                        "rewards": q["rewards"],
                        "text_sha256": q["text_sha256"], "roots": list(q["roots"]),
                        "boundary": {"heading": q["heading"], "next_heading": q["next_heading"],
                                     "start_character": q["start_character"],
                                     "end_character": q["end_character"]}}
                       for q in self.quests],
        }

    @property
    def documents(self):
        return tuple(dict(item) for item in self._documents)

    def publish(self, connection, now):
        expected_manifest = json.dumps(self.manifest, ensure_ascii=False, separators=(",", ":"))
        existing = connection.execute(
            "SELECT manifest_json FROM content_revisions WHERE id=?", (self.revision_id,)).fetchone()
        if existing:
            if existing["manifest_json"] != expected_manifest:
                raise RuntimeError("content revision manifest mismatch")
        else:
            connection.execute("INSERT INTO content_revisions(id,manifest_json,created_at) VALUES(?,?,?)",
                               (self.revision_id, expected_manifest, now))
            for item in self._documents:
                connection.execute(
                    "INSERT INTO content_revision_documents VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (self.revision_id, item["document_id"], item["category"], item["ordinal"],
                     item["source_path"], item["raw_bytes"], item["text_content"],
                     item["raw_sha256"], item["text_sha256"], item["encoding"],
                     int(item["has_bom"]), item["newline_style"], item["byte_count"],
                     item["character_count"], item["line_count"]))
        rows = connection.execute(
            "SELECT * FROM content_revision_documents WHERE revision_id=? ORDER BY category,ordinal",
            (self.revision_id,)).fetchall()
        if len(rows) != len(self._documents):
            raise RuntimeError("content revision document count mismatch")
        actual = {row["document_id"]: row for row in rows}
        for item in self._documents:
            row = actual.get(item["document_id"])
            if not row or row["raw_sha256"] != item["raw_sha256"] or row["text_sha256"] != item["text_sha256"]:
                raise RuntimeError(f"content revision document mismatch: {item['document_id']}")
        connection.execute(
            "INSERT INTO trusted_content_revisions(revision_id,trust_kind,trusted_at) VALUES(?,?,?) "
            "ON CONFLICT(revision_id) DO UPDATE SET trust_kind='builtin'",
            (self.revision_id, "builtin", now))

    @staticmethod
    def location_matches(location_id, root, location_nodes=None):
        if location_id == root:
            return True
        nodes = location_nodes or {}
        seen = set()
        current = location_id
        while current and current not in seen:
            if current == root:
                return True
            seen.add(current)
            current = (nodes.get(current) or {}).get("parent_id")
        return False

    def select_quests(self, state, location_nodes=None, quests=None):
        selected = []
        statuses = state.get("regional_quests", {})
        location_id = state.get("location", {}).get("id", "")
        for quest in (quests or self.quests):
            status = statuses.get(quest["id"], {}).get("status", "untriggered")
            if status in TERMINAL_QUEST_STATES:
                continue
            matched = any(self.location_matches(location_id, root, location_nodes)
                          for root in quest["roots"])
            if not matched and status not in {"offered", "active"}:
                continue
            selected.append({
                "id": quest["id"], "stored_status": status,
                "context_eligibility": "location_matched" if matched else (
                    "persistent_active" if status in {"offered", "active"} else "card_only"),
                "card": dict(quest["normal_context_card"]),
                "full_source_markdown": (quest["full_source_markdown"]
                                         if matched or status in {"offered", "active"} else None),
                "text_sha256": quest["text_sha256"] if matched or status in {"offered", "active"} else None,
            })
        return selected

    def revision_quests(self, documents, manifest):
        regional_source = next(item["text_content"] for item in documents
                               if item["document_id"] == "regional.source")
        parsed = {item["id"]: item for item in self._parse_quests(regional_source)}
        result = []
        for definition in manifest["quests"]:
            quest = dict(parsed[definition["id"]])
            quest["normal_context_card"] = definition["normal_context_card"]
            quest["rewards"] = definition["rewards"]
            quest["roots"] = tuple(definition["roots"])
            quest["text_sha256"] = definition["text_sha256"]
            result.append(quest)
        return tuple(result)

    @staticmethod
    def _document_container(document):
        meta = {key: document[key] for key in (
            "document_id", "category", "ordinal", "source_path", "raw_sha256",
            "text_sha256", "encoding", "has_bom", "newline_style", "byte_count",
            "character_count", "line_count")}
        return ("\n<DOCUMENT " + json.dumps(meta, ensure_ascii=False, separators=(",", ":")) + ">\n" +
                document["text_content"] + "\n</DOCUMENT>\n")

    @staticmethod
    def _protocol_container(document):
        meta = {key: document[key] for key in (
            "document_id", "category", "ordinal", "source_path", "raw_sha256",
            "text_sha256", "character_count")}
        return ("\n<PROTOCOL " + json.dumps(meta, ensure_ascii=False,
                                             separators=(",", ":")) + ">\n" +
                document["text_content"] + "\n</PROTOCOL>\n")

    def build_messages(self, state, action, early_summaries, recent_full_turns, memories, arcs,
                       location_nodes=None, documents=None, contract_kind="gm_turn",
                       revision_manifest=None):
        source_documents = list(documents or self._documents)
        by_category = {}
        for item in source_documents:
            by_category.setdefault(item["category"], []).append(item)
        for values in by_category.values():
            values.sort(key=lambda item: item["ordinal"])
        revision_quests = (self.revision_quests(source_documents, revision_manifest)
                           if revision_manifest else self.quests)
        quest_context = self.select_quests(state, location_nodes, revision_quests)
        visible_quest_ids = {item["id"] for item in quest_context}
        prompt_state = json.loads(json.dumps(state, ensure_ascii=False))
        prompt_state["regional_quests"] = {
            quest_id: quest for quest_id, quest in prompt_state.get("regional_quests", {}).items()
            if quest_id in visible_quest_ids
        }
        contract = contract_from_documents(contract_kind, source_documents)
        address_directive = player_address_directive(state)
        system_parts = []
        for item in by_category.get("protocol", [])[:2]:
            system_parts.append(self._protocol_container(item))
        if contract_kind == "gm_turn":
            regional_policy = {
                "priority": "mandatory",
                "current_location_id": state.get("location", {}).get("id"),
                "visible_regional_quests": [{
                    "id": item["id"],
                    "context_eligibility": item["context_eligibility"],
                    "designated_trigger_locations": list(next(
                        quest["roots"] for quest in revision_quests if quest["id"] == item["id"])),
                } for item in quest_context],
                "rules": [
                    "只有visible_regional_quests列出的任务可用于本次叙事",
                    "location_matched任务才可首次出现线索、预告、推荐、引导、offered或触发事件，并且仍须满足任务原文触发条件",
                    "persistent_active仅表示任务此前已offered或active，允许离开指定地点后继续推进",
                    "同属一个地区、国家、势力或旅行路线不构成触发地点匹配",
                    "历史节点、故事弧、长期记忆、世界正典或玩家输入若提及未列出的地区任务，必须将其视为当前不可用信息，不得据此提及、暗示、推荐、引导或触发",
                ],
            }
            encoded_regional_policy = json.dumps(
                regional_policy, ensure_ascii=True, separators=(",", ":")
            ).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
            system_parts.append(
                "\n<RUNTIME_REGIONAL_QUEST_POLICY_JSON>\n" +
                encoded_regional_policy +
                "\n</RUNTIME_REGIONAL_QUEST_POLICY_JSON>\n"
            )
            address_policy = {
                "priority": "mandatory",
                "version": PLAYER_ADDRESS_PROTOCOL_VERSION,
                "mode": address_directive["mode"],
                "required_gm_narration_address": address_directive["gm_narration_address"],
                "forbidden_gm_second_person_pronouns": (
                    ["你", "您", "你们"] if address_directive["mode"] != "second_person" else []),
                "scope": "只约束GM叙述者；NPC台词不受此项限制",
            }
            encoded_address_policy = json.dumps(
                address_policy, ensure_ascii=True, separators=(",", ":")
            ).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
            system_parts.append(
                "\n<RUNTIME_PLAYER_ADDRESS_JSON>\n" +
                encoded_address_policy +
                "\n</RUNTIME_PLAYER_ADDRESS_JSON>\n"
            )
        system_parts.append("\n<完整规则原文>\n")
        system_parts.extend(self._document_container(item) for item in by_category.get("rule", []))
        system_parts.append("\n</完整规则原文>\n<完整世界正典>\n")
        system_parts.extend(self._document_container(item) for item in by_category.get("canon", []))
        system_parts.append("\n</完整世界正典>\n")
        system_parts.append("\n<OUTPUT_CONTRACT kind=\"" + contract_kind + "\" version=\"" +
                            contract["version"] + "\">\n" + contract["text"] + "\nJSON Schema:\n" +
                            json.dumps(contract["schema"], ensure_ascii=False, separators=(",", ":")) +
                            "\n</OUTPUT_CONTRACT>\n")
        dynamic = {
            "active_narration": state.get("narration", {}), "regional_quests": quest_context,
            "player_address_directive": address_directive,
            "story_arcs": arcs, "early_summaries": early_summaries,
            "long_term_memories": memories, "recent_full_turns": recent_full_turns,
            "authoritative_state": prompt_state, "current_action": action,
            "output_contract_reminder": {"kind": contract_kind, "version": contract["version"],
                                         "schema": contract["schema"]},
        }
        frozen = revision_manifest or self.manifest
        manifest = {
            "content_revision_id": frozen["revision_id"],
            "prompt_version": frozen["prompt_version"], "contract_kind": contract_kind,
            "contract_version": contract["version"],
            "player_address_protocol_version": PLAYER_ADDRESS_PROTOCOL_VERSION,
            "state_version": state.get("state_version", 0),
            "documents": [{"document_id": item["document_id"], "category": item["category"],
                           "ordinal": item["ordinal"], "raw_sha256": item["raw_sha256"],
                           "text_sha256": item["text_sha256"], "byte_count": item["byte_count"],
                           "character_count": item["character_count"]}
                          for item in source_documents],
            "regional_quest_ids": [item["id"] for item in quest_context],
            "full_regional_quest_ids": [item["id"] for item in quest_context
                                        if item["full_source_markdown"] is not None],
            "early_summary_sequences": [item.get("sequence") for item in early_summaries],
            "recent_full_sequences": [item.get("sequence") for item in recent_full_turns],
            "story_arc_ids": [item.get("id") for item in arcs],
            "memory_ids": [item.get("id") for item in memories],
        }
        return ([{"role": "system", "content": "".join(system_parts)},
                 {"role": "user", "content": json.dumps(dynamic, ensure_ascii=False,
                                                           separators=(",", ":"))}],
                manifest)


def load_revision_documents(connection, revision_id):
    rows = connection.execute(
        "SELECT * FROM content_revision_documents WHERE revision_id=? ORDER BY "
        "CASE category WHEN 'protocol' THEN 1 WHEN 'rule' THEN 2 WHEN 'contract' THEN 3 "
        "WHEN 'canon' THEN 4 ELSE 5 END,ordinal",
        (revision_id,)).fetchall()
    return [dict(row) for row in rows]


def load_revision_manifest(connection, revision_id):
    row = connection.execute("SELECT manifest_json FROM content_revisions WHERE id=?",
                             (revision_id,)).fetchone()
    if not row:
        raise ValueError("content revision does not exist")
    return json.loads(row["manifest_json"])
