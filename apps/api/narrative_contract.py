"""Strict GM response validation and deterministic state adjudication."""

import copy
import hashlib
import json
import re
import uuid

try:
    from .catalog import EXP_THRESHOLDS, POWER_BY_RANK
    from .contract_registry import validate_contract
except ImportError:
    from catalog import EXP_THRESHOLDS, POWER_BY_RANK
    from contract_registry import validate_contract


REPUTATION_KEYS = (
    "continental_overall",
    "court_of_veiled_night",
    "skycrown_conclave",
    "holy_see_sacred_radiance",
    "court_of_sacred_tree",
    "valkeren_empire",
    "southern_maritime_federation",
)
RESOURCE_KEYS = ("hp", "mp", "sp", "st")
ATTRIBUTE_KEYS = ("con", "int", "cha")
TIME_LABELS = ("深夜", "凌晨", "早晨", "上午", "中午", "下午", "黄昏", "夜晚")
QUEST_STATES = {"untriggered", "eligible", "offered", "active", "completed",
                "declined", "failed", "abandoned"}
TERMINAL_QUEST_STATES = {"completed", "declined", "failed", "abandoned"}
BOND_ADMISSIONS = {"important_character", "persistent_interaction",
                   "long_term_relationship", "likely_recurring"}
QUEST_TRANSITIONS = {
    "untriggered": {"offered", "active", "declined", "failed"},
    "eligible": {"offered", "active", "declined", "failed"},
    "offered": {"active", "declined", "failed", "abandoned"},
    "active": {"active", "completed", "failed", "abandoned"},
}
REGIONAL_TRANSITION_RULES = {
    "regional_main.lost_tidevoice": {
        "start_terms": ("任务板", "匿名", "委托", "潮音珠"),
        "complete_nodes": ("潮音珠", "演出"),
        "terminal_terms": ("拒绝", "未接取", "演出取消", "未能在演出前找回", "放弃"),
    },
    "regional_main.walking_with_wind": {
        "start_terms": ("搭话", "伊蕾娅", "少女"),
        "complete_nodes": ("日落", "维兰希亚"),
        "terminal_terms": ("没有搭话", "中途离开", "未完成", "拒绝", "放弃"),
    },
    "regional_main.mia_day_out": {
        "start_terms": ("误导", "拒绝透露", "帮助", "士兵", "米娅"),
        "complete_nodes": ("星空", "维蕾莎", "护魂项链"),
        "terminal_terms": ("指出方向", "帮助士兵", "破坏出行", "强行带回", "中断"),
    },
    "regional_main.sacred_tree_encounter": {
        "start_terms": ("观看", "搭话", "协助", "莉瑟娅"),
        "complete_nodes": ("同行", "交流", "翠生护符"),
        "terminal_terms": ("忽略", "持续冒犯", "攻击", "伤害精灵之森", "离开"),
    },
    "regional_main.song_of_sandsea": {
        "start_terms": ("接受", "加入", "护卫", "商队", "娜希娅"),
        "complete_nodes": ("熔脊龙谷",),
        "terminal_terms": ("拒绝", "未按时归队", "主动离队", "放弃"),
    },
    "regional_main.grand_academy_first_day": {
        "start_terms": ("入学", "测试", "学院"),
        "complete_nodes": ("选择学院", "宿舍", "学生卡"),
        "terminal_terms": ("拒绝", "放弃入学", "测试失败", "中断", "离开"),
    },
}
REGIONAL_ACTIVE_ACTION_TERMS = {
    "regional_main.lost_tidevoice": ("接取", "接受委托", "帮助露米娅", "同行寻找"),
    "regional_main.walking_with_wind": ("搭话", "主动交谈", "陪伊蕾娅", "接受邀请"),
    "regional_main.mia_day_out": ("误导士兵", "拒绝透露", "帮助少女", "帮助米娅"),
    "regional_main.sacred_tree_encounter": ("搭话", "协助教学", "接受同行", "请求莉瑟娅"),
    "regional_main.song_of_sandsea": ("接受招募", "加入商队", "担任护卫"),
    "regional_main.grand_academy_first_day": ("入学", "参加测试", "选择学院"),
}
REGIONAL_NEGATED_ACTION_TERMS = {
    "regional_main.lost_tidevoice": ("接取", "接受委托", "帮助露米娅", "同行寻找", "委托"),
    "regional_main.walking_with_wind": ("搭话", "交谈", "陪伊蕾娅", "接受邀请"),
    "regional_main.mia_day_out": ("误导士兵", "帮助少女", "帮助米娅"),
    "regional_main.sacred_tree_encounter": ("搭话", "协助教学", "接受同行", "同行", "请求莉瑟娅"),
    "regional_main.song_of_sandsea": ("接受招募", "加入商队", "担任护卫", "加入", "护卫"),
    "regional_main.grand_academy_first_day": ("入学", "参加测试", "选择学院"),
}
ACADEMY_GUIDES = {"战士学院": "莱恩·哈维尔", "法师学院": "塞莉娅·维恩",
                  "魔导学院": "芙妮娅·莱克斯"}
CANONICAL_POWER_EXCEPTIONS = {
    "canon:sea_folk_deep_sea",
    "canon:tenth_rank_discontinuity",
    "canon:featherfolk_open_air",
    "canon:elf_forest_affinity",
    "canon:dragon_true_form",
}
BREAKTHROUGH_ACTION_TERMS = ("突破", "升阶", "晋阶", "冲阶", "breakthrough", "rank up", "advance rank")
ACTION_NEGATIONS = ("不想", "不要", "不愿", "不再", "不能", "不", "别", "拒绝", "放弃", "取消")


class ContractError(Exception):
    pass


def _exact(value, fields, label):
    if not isinstance(value, dict) or set(value) != set(fields):
        raise ContractError(f"{label}字段不完整或包含未知字段")


def _text(value, label, maximum=20000, empty=False):
    if not isinstance(value, str) or len(value) > maximum or (not empty and not value.strip()):
        raise ContractError(f"{label}必须是有效文本")
    return value


def _integer(value, label, minimum=None, maximum=None):
    if type(value) is not int or (minimum is not None and value < minimum) or (
            maximum is not None and value > maximum):
        raise ContractError(f"{label}必须是有效整数")
    return value


def _list(value, label, maximum=100):
    if not isinstance(value, list) or len(value) > maximum:
        raise ContractError(f"{label}必须是数组")
    return value


def _proposal_reason(item, label, extra=()):
    required = {"reason", "evidence", *extra}
    if not isinstance(item, dict) or set(item) != required:
        raise ContractError(f"{label}字段无效")
    _text(item["reason"], label + ".reason", 2000)
    _text(item["evidence"], label + ".evidence", 4000)


def _reject_duplicate_keyed_proposals(proposals):
    keyed_groups = {
        "resources": lambda item: item.get("key"),
        "attributes": lambda item: item.get("key"),
        "reputations": lambda item: item.get("key"),
        "world_flags": lambda item: item.get("key"),
        "power_modifiers": lambda item: item.get("id"),
        "items": lambda item: item.get("item_id"),
        "quests": lambda item: item.get("quest_id"),
        "bonds": lambda item: item.get("npc_id") or item.get("npc_ref"),
        "skills": lambda item: item.get("id"),
        "talents": lambda item: item.get("id"),
    }
    for group, key_for in keyed_groups.items():
        seen = set()
        for item in proposals.get(group, []):
            key = key_for(item) if isinstance(item, dict) else None
            if key is None:
                continue
            if key in seen:
                raise ContractError(f"{group}不能对同一键或ID提交多个提案")
            seen.add(key)


def _location_matches_region(state, region_id):
    location_id = state.get("location", {}).get("id", "")
    if location_id == region_id or location_id.startswith(region_id + "."):
        return True
    location = state.get("locations", {}).get(location_id, {})
    return location.get("region_id") == region_id


def canonical_power_exception_applies(exception, state, modifier_value=0):
    """Return whether a protected power exception applies to this exact state."""
    flags = state.get("world_flags", {})
    if exception not in CANONICAL_POWER_EXCEPTIONS:
        return (isinstance(exception, str) and exception.startswith("canon_exception.") and
                flags.get(exception) is True)
    character = state.get("character", {})
    race = character.get("identity", {}).get("race_id")
    rank = character.get("rank")
    if exception == "canon:sea_folk_deep_sea":
        return race == "sea_folk" and _location_matches_region(state, "abyssal_tides")
    if exception == "canon:featherfolk_open_air":
        location_id = state.get("location", {}).get("id", "")
        location = state.get("locations", {}).get(location_id, {})
        open_air = (location_id == "velansia.central_plaza" or
                    location_id.startswith("velansia.central_plaza.") or
                    location.get("type") in {"plaza", "street", "outdoor", "open_air"} or
                    flags.get("environment.open_high_altitude") is True)
        return race == "featherfolk" and _location_matches_region(state, "velansia") and open_air
    if exception == "canon:elf_forest_affinity":
        return race == "elf" and _location_matches_region(state, "elf_forest")
    if exception == "canon:dragon_true_form":
        true_form = (flags.get("dragon_true_form_active") is True or
                     flags.get("dragon_true_form") is True or
                     flags.get("current_form") == "dragon_true_form")
        return race == "dragonkin" and true_form
    if exception == "canon:tenth_rank_discontinuity":
        return rank == 10
    return False


def _player_action_text(action):
    if not isinstance(action, dict):
        return ""
    values = [action.get(key, "") for key in ("action", "guidance", "reshape_guidance")]
    values.append(_player_action_text(action.get("original_action")))
    return " ".join(value for value in values if isinstance(value, str)).lower()


def _text_clauses(text):
    return [value.strip() for value in re.split(r"[。！？!?；;，,\r\n]+", text) if value.strip()]


def _normalized_clause(text):
    return text.strip().strip("。！？!?；;，,").strip()


def _has_negated_action(text, terms):
    return any(_contains_any(clause, terms) and _contains_any(clause, ACTION_NEGATIONS)
               for clause in _text_clauses(text))


def _explicit_affirmed_action(text, terms):
    clauses = [clause for clause in _text_clauses(text) if _contains_any(clause, terms)]
    return bool(clauses) and not any(_contains_any(clause, ACTION_NEGATIONS) for clause in clauses)


def _validate_memory_evidence(item, body):
    evidence = _normalized_clause(item["evidence"])
    if len(evidence) < 8:
        raise ContractError("记忆evidence至少需要8个字符的完整正文证据")
    if evidence not in {_normalized_clause(clause) for clause in _text_clauses(body)}:
        raise ContractError("记忆evidence必须是叙事正文中的完整分句")
    for key in ("facts", "unresolved"):
        if any(_normalized_clause(entry) != evidence for entry in item[key]):
            raise ContractError("memory." + key + "每一项都必须与evidence完全相同")


def _validate_breakthrough_intent(response, action):
    breakthrough = response["proposals"].get("breakthrough")
    if breakthrough and (breakthrough.get("attempted") or breakthrough.get("success")):
        action_text = _player_action_text(action)
        if _has_negated_action(action_text, BREAKTHROUGH_ACTION_TERMS):
            raise ContractError("玩家原始行动明确否定突破，不能提议突破尝试或成功")
        if not _explicit_affirmed_action(action_text, BREAKTHROUGH_ACTION_TERMS):
            raise ContractError("突破尝试或成功必须由玩家原始行动明确请求")


def validate_gm_response(value, response_type=None, contract=None):
    try:
        validate_contract(value, "gm_turn", contract)
    except ValueError as exc:
        raise ContractError(str(exc)) from None
    _exact(value, {"schema_version", "response_type", "narrative", "scene", "proposals",
                   "memory_candidates", "warnings"}, "响应")
    if value["schema_version"] != "gm-turn/1":
        raise ContractError("schema_version无效")
    if value["response_type"] not in {"opening", "turn", "intervene", "reshape"}:
        raise ContractError("response_type无效")
    if response_type and value["response_type"] != response_type:
        raise ContractError("response_type与任务类型不符")

    narrative = value["narrative"]
    _exact(narrative, {"title", "body", "chronicle_summary", "suggested_options"}, "narrative")
    for key, limit in (("title", 300), ("body", 50000)):
        _text(narrative[key], "narrative." + key, limit)
    _text(narrative["chronicle_summary"], "narrative.chronicle_summary", 2000, empty=True)
    if re.search(r"<\s*/?\s*[A-Za-z][^>]*>", narrative["body"]):
        raise ContractError("叙事正文禁止原始HTML")
    options = _list(narrative["suggested_options"], "suggested_options", 3)
    if len(options) not in {2, 3}:
        raise ContractError("suggested_options必须有2至3项")
    option_ids, option_texts = set(), set()
    for option in options:
        _exact(option, {"id", "text", "intent"}, "option")
        for key in option:
            _text(option[key], "option." + key, 1000)
        if option["id"] in option_ids or option["text"] in option_texts:
            raise ContractError("suggested_options不能重复")
        option_ids.add(option["id"]); option_texts.add(option["text"])

    scene = value["scene"]
    _exact(scene, {"time_label", "elapsed_minutes", "location", "new_locations", "new_npcs"}, "scene")
    if scene["time_label"] not in TIME_LABELS:
        raise ContractError("scene.time_label无效")
    _integer(scene["elapsed_minutes"], "scene.elapsed_minutes", 0, 5256000)
    location = scene["location"]
    _exact(location, {"operation", "location_id", "location_ref", "reason"}, "scene.location")
    if location["operation"] not in {"stay", "move"}:
        raise ContractError("地点操作无效")
    for key in ("location_id", "location_ref"):
        if location[key] is not None:
            _text(location[key], "scene.location." + key, 300)
    _text(location["reason"], "scene.location.reason", 2000, empty=True)
    if location["operation"] == "move" and bool(location["location_id"]) == bool(location["location_ref"]):
        raise ContractError("移动必须且只能引用一个地点")
    new_refs = set()
    for item in _list(scene["new_locations"], "new_locations", 10):
        _exact(item, {"ref", "name", "type", "parent_id", "region_id", "description", "reason"},
               "new_location")
        for key, maximum in (("ref", 300), ("name", 300), ("type", 100), ("parent_id", 300),
                             ("region_id", 300), ("description", 4000), ("reason", 2000)):
            _text(item[key], "new_location." + key, maximum)
        if not item["ref"].startswith("location:new:") or item["ref"] in new_refs:
            raise ContractError("新地点局部引用无效")
        new_refs.add(item["ref"])
    if location["location_ref"] and location["location_ref"] not in new_refs:
        raise ContractError("移动引用了不存在的新地点")
    npc_refs = set()
    for item in _list(scene["new_npcs"], "new_npcs", 20):
        _exact(item, {"ref", "name", "description", "reason"}, "new_npc")
        if not item["ref"].startswith("npc:new:") or item["ref"] in npc_refs:
            raise ContractError("新NPC局部引用无效")
        npc_refs.add(item["ref"])
        for key in ("name", "description", "reason"):
            _text(item[key], "new_npc." + key, 4000)

    proposals = value["proposals"]
    proposal_fields = {"resources", "attributes", "experience", "breakthrough", "items",
                       "currency", "quests", "bonds", "reputations", "skills", "talents",
                       "world_flags", "power_modifiers"}
    _exact(proposals, proposal_fields, "proposals")
    _reject_duplicate_keyed_proposals(proposals)
    for item in _list(proposals["resources"], "resources"):
        _proposal_reason(item, "resource", ("key", "delta"))
        if item["key"] not in RESOURCE_KEYS:
            raise ContractError("未知资源键")
        _integer(item["delta"], "resource.delta", -9999, 9999)
    for item in _list(proposals["attributes"], "attributes"):
        _proposal_reason(item, "attribute", ("key", "delta", "long_term_basis"))
        if item["key"] not in ATTRIBUTE_KEYS:
            raise ContractError("未知属性键")
        _integer(item["delta"], "attribute.delta", -100, 100)
        _text(item["long_term_basis"], "attribute.long_term_basis", 4000)
    for item in _list(proposals["experience"], "experience"):
        _exact(item, {"amount", "growth_type", "challenge", "novelty", "repetition",
                      "reason", "evidence"}, "experience")
        _integer(item["amount"], "experience.amount", 0, 100000)
        for key in ("growth_type", "challenge", "novelty", "repetition", "reason", "evidence"):
            _text(item[key], "experience." + key, 4000)
        semantics = " ".join((item["challenge"], item["novelty"], item["repetition"])).lower()
        low = any(term in semantics for term in ("low", "none", "repeated", "trivial", "低", "无挑战", "重复", "熟练"))
        if low and item["amount"] > 10:
            raise ContractError("低挑战、低新颖度或重复行为不能获得大额EXP")
    breakthrough = proposals["breakthrough"]
    if breakthrough is not None:
        _exact(breakthrough, {"attempted", "success", "method", "preparation", "failure_reason", "improvement",
                              "task_completed_id", "reason", "evidence"}, "breakthrough")
        if type(breakthrough["attempted"]) is not bool or type(breakthrough["success"]) is not bool:
            raise ContractError("突破布尔字段无效")
        if breakthrough["success"] and not breakthrough["attempted"]:
            raise ContractError("突破成功必须同时标记attempted")
        for key in ("failure_reason", "improvement", "task_completed_id"):
            if breakthrough[key] is not None:
                _text(breakthrough[key], "breakthrough." + key, 2000)
        _text(breakthrough["method"], "breakthrough.method", 2000)
        _text(breakthrough["preparation"], "breakthrough.preparation", 2000)
        _text(breakthrough["reason"], "breakthrough.reason", 2000)
        _text(breakthrough["evidence"], "breakthrough.evidence", 4000)
    for item in _list(proposals["items"], "items"):
        _proposal_reason(item, "item", ("operation", "item_id", "name", "description",
                                         "quantity", "power", "source"))
        if item["operation"] not in {"add", "remove", "equip", "unequip"}:
            raise ContractError("物品操作无效")
        if item["item_id"] is not None:
            _text(item["item_id"], "item.item_id", 300)
        _text(item["name"], "item.name", 300)
        _text(item["description"], "item.description", 4000, empty=True)
        _integer(item["quantity"], "item.quantity", 1, 1000000)
        _integer(item["power"], "item.power", 0, 1000000)
        _text(item["source"], "item.source", 1000)
    currency = proposals["currency"]
    _exact(currency, {"copper_delta", "reason", "evidence"}, "currency")
    _integer(currency["copper_delta"], "currency.copper_delta", -1000000000, 1000000000)
    _text(currency["reason"], "currency.reason", 2000, empty=True)
    _text(currency["evidence"], "currency.evidence", 4000, empty=True)
    for item in _list(proposals["quests"], "quests"):
        _proposal_reason(item, "quest", ("operation", "quest_id", "name", "description",
                                          "status", "progress", "objectives", "quest_kind",
                                          "target_rank", "action_evidence", "necessary_nodes"))
        if item["operation"] not in {"create", "transition", "update"} or item["status"] not in QUEST_STATES:
            raise ContractError("任务操作或状态无效")
        for key in ("quest_id", "name", "description", "progress"):
            if item[key] is not None:
                _text(item[key], "quest." + key, 4000)
        if any(not isinstance(x, str) for x in _list(item["objectives"], "quest.objectives", 30)):
            raise ContractError("任务目标无效")
        if item["quest_kind"] not in {"regular", "regional", "breakthrough"}:
            raise ContractError("任务类型无效")
        if item["target_rank"] is not None:
            _integer(item["target_rank"], "quest.target_rank", 1, 10)
        _text(item["action_evidence"], "quest.action_evidence", 4000, empty=True)
        if any(not isinstance(x, str) for x in _list(item["necessary_nodes"], "quest.necessary_nodes", 30)):
            raise ContractError("任务必要节点无效")
    for item in _list(proposals["bonds"], "bonds"):
        _proposal_reason(item, "bond", ("operation", "npc_id", "npc_ref", "npc_name", "delta",
                                         "relation_type", "admission"))
        if item["operation"] not in {"create_or_join", "adjust", "change_relation_type"}:
            raise ContractError("羁绊操作无效")
        if bool(item["npc_id"]) == bool(item["npc_ref"]):
            raise ContractError("羁绊必须且只能引用一个NPC")
        _text(item["npc_name"], "bond.npc_name", 300)
        _integer(item["delta"], "bond.delta", -200, 200)
        _text(item["relation_type"], "bond.relation_type", 200)
        if item["operation"] == "create_or_join" and item["admission"] not in BOND_ADMISSIONS:
            raise ContractError("羁绊准入条件无效")
        if item["npc_ref"] and item["npc_ref"] not in npc_refs:
            raise ContractError("羁绊npc_ref未对应本响应新NPC")
    for item in _list(proposals["reputations"], "reputations"):
        _exact(item, {"key", "delta", "public_reason", "evidence"}, "reputation")
        if item["key"] not in REPUTATION_KEYS:
            raise ContractError("未知声望键")
        _integer(item["delta"], "reputation.delta", -200, 200)
        _text(item["public_reason"], "reputation.public_reason", 2000)
        if re.search(r"(?:没有|未|尚未|并未|不曾).{0,8}(?:公开|传播|知晓|发现)", item["public_reason"]):
            raise ContractError("声望变化理由明确表示尚未公开或传播")
        _text(item["evidence"], "reputation.evidence", 4000)
    for group in ("skills", "talents"):
        for item in _list(proposals[group], group):
            _proposal_reason(item, group[:-1], ("operation", "id", "name", "description", "source"))
            if item["operation"] not in {"add", "remove", "update"}:
                raise ContractError(group + "操作无效")
            for key in ("name", "description", "source"):
                _text(item[key], group + "." + key, 4000)
            if item["id"] is not None:
                _text(item["id"], group + ".id", 300)
    for item in _list(proposals["world_flags"], "world_flags"):
        _proposal_reason(item, "world_flag", ("key", "value"))
        _text(item["key"], "world_flag.key", 300)
        if not isinstance(item["value"], (str, int, bool)) and item["value"] is not None:
            raise ContractError("world_flag.value无效")
    for item in _list(proposals["power_modifiers"], "power_modifiers"):
        _proposal_reason(item, "power_modifier", ("operation", "id", "value", "temporary",
                                                    "category", "severity", "canonical_exception"))
        if item["operation"] not in {"add", "update", "remove", "expire"}:
            raise ContractError("power_modifier.operation无效")
        _text(item["id"], "power_modifier.id", 300)
        if item["value"] is not None:
            _integer(item["value"], "power_modifier.value", -1000000, 1000000)
        if item["operation"] in {"add", "update"} and item["value"] is None:
            raise ContractError("add/update战力修正必须提供value")
        if item["operation"] in {"remove", "expire"} and item["value"] is not None:
            raise ContractError("remove/expire战力修正的value必须为null")
        if type(item["temporary"]) is not bool:
            raise ContractError("power_modifier.temporary无效")
        if item["category"] not in {"environment", "status", "counter", "tactics", "equipment", "other"}:
            raise ContractError("power_modifier.category无效")
        if item["severity"] not in {"minor", "moderate", "major", "extreme"}:
            raise ContractError("power_modifier.severity无效")

    for item in _list(value["memory_candidates"], "memory_candidates", 10):
        _exact(item, {"operation", "memory_id", "kind", "summary", "importance", "people",
                      "locations", "keywords", "facts", "unresolved", "reason", "evidence"}, "memory")
        if item["operation"] not in {"create", "resolve", "supersede"}:
            raise ContractError("记忆操作无效")
        if item["memory_id"] is not None:
            _text(item["memory_id"], "memory.memory_id", 300)
        for key in ("kind", "summary", "reason", "evidence"):
            _text(item[key], "memory." + key, 4000)
        _integer(item["importance"], "memory.importance", 1, 100)
        for key in ("people", "locations", "keywords", "facts", "unresolved"):
            for entry in _list(item[key], "memory." + key, 30):
                _text(entry, "memory." + key, 4000)
        _validate_memory_evidence(item, narrative["body"])
    if any(not isinstance(item, str) for item in _list(value["warnings"], "warnings", 30)):
        raise ContractError("warnings无效")
    return copy.deepcopy(value)


def reputation_level(value):
    if value <= -81: return "公敌"
    if value <= -51: return "恶名昭著"
    if value <= -21: return "不受欢迎"
    if value <= 20: return "中立"
    if value <= 50: return "声名良好"
    if value <= 80: return "受人敬重"
    return "威望卓著"


def bond_level(value):
    if value <= -81: return "死敌"
    if value <= -51: return "仇恨"
    if value <= -21: return "厌恶"
    if value <= 20: return "普通/陌生"
    if value <= 50: return "友好"
    if value <= 80: return "亲近"
    return "深厚羁绊"


def _change(kind, key, old, new, reason, extra=None):
    result = {"kind": kind, "key": key, "old": old, "new": new, "reason": reason}
    if extra:
        result.update(extra)
    return result


def _contains_any(text, terms):
    return any(term in text for term in terms)


def _validate_regional_transition(quest_id, current, proposal, context_eligibility,
                                  action_text, body, proposals=None):
    target = proposal["status"]
    if current["status"] in {"untriggered", "eligible"} and context_eligibility != "location_matched":
        raise ContractError("地区任务不能在错误地点从未触发状态转移")
    rule = REGIONAL_TRANSITION_RULES[quest_id]
    evidence = " ".join((action_text, proposal["action_evidence"], proposal["evidence"], body))
    negated_active = _has_negated_action(action_text, REGIONAL_NEGATED_ACTION_TERMS[quest_id])
    if target == "active" and negated_active:
        raise ContractError("玩家原始行动明确否定地区任务触发行为，不能转为active")
    if target == "active" and not _explicit_affirmed_action(
            action_text, REGIONAL_ACTIVE_ACTION_TERMS[quest_id]):
        raise ContractError("地区任务active必须由玩家原始行动明确触发")
    if current["status"] in {"untriggered", "eligible"} and target in {
            "active", "offered", "declined", "failed"} and not _contains_any(evidence, rule["start_terms"]):
        raise ContractError("地区任务缺少玩家动作或触发证据")
    terminal_evidence = " ".join((action_text, current.get("progress", ""), body))
    if target in {"declined", "failed", "abandoned"} and not (
            target == "declined" and negated_active) and not _contains_any(
                terminal_evidence, rule["terminal_terms"]):
        raise ContractError("地区任务终局路径缺少任务专属拒绝、失败或中断证据")
    if target == "completed":
        markers = set(proposal["necessary_nodes"])
        if not all(term in body or term in markers for term in rule["complete_nodes"]):
            raise ContractError("地区任务缺少必要完成节点")
    if quest_id == "regional_main.song_of_sandsea" and target in {"completed", "abandoned"}:
        currency = (proposals or {}).get("currency", {})
        combined = " ".join((currency.get("reason", ""), currency.get("evidence", ""), body))
        if currency.get("copper_delta", 0) <= 0 or not _contains_any(
                combined, ("工资", "贡献", "路程", "护卫", "结算")):
            raise ContractError("沙海之歌完成或主动离队必须按实际贡献结算工资")
    if quest_id == "regional_main.grand_academy_first_day" and target == "completed":
        flags = {item["key"]: item["value"] for item in (proposals or {}).get("world_flags", [])}
        academy = flags.get("grand_academy_selected_school")
        guide = flags.get("grand_academy_guide")
        if academy not in ACADEMY_GUIDES or guide != ACADEMY_GUIDES[academy]:
            raise ContractError("学院任务完成必须记录所选学院和对应指引员")


def _validate_narrative_consistency(state, response):
    body = response["narrative"]["body"]
    proposals = response["proposals"]
    evidence_items = []
    for key in ("resources", "attributes", "experience", "items", "quests", "bonds",
                "reputations", "skills", "talents", "world_flags", "power_modifiers"):
        evidence_items.extend(proposals[key])
    if proposals["breakthrough"]:
        evidence_items.append(proposals["breakthrough"])
    if proposals["currency"]["copper_delta"]:
        evidence_items.append(proposals["currency"])
    for item in evidence_items:
        evidence = item.get("evidence", "")
        if evidence and evidence not in body:
            raise ContractError("提案evidence必须逐字存在于叙事正文")
    for memory in response["memory_candidates"]:
        _validate_memory_evidence(memory, body)
    hp_delta = sum(item["delta"] for item in proposals["resources"] if item["key"] == "hp")
    hp_after = max(0, min(state["character"]["resources"]["hp"]["max"],
                          state["character"]["resources"]["hp"]["current"] + hp_delta))
    says_death = any(term in body for term in ("死亡", "死去", "失去生命"))
    if says_death and hp_after != 0:
        raise ContractError("正文死亡叙述与HP提案不一致")
    if hp_after == 0 and not says_death and not any(term in body for term in ("致命", "没有呼吸", "心跳停止")):
        raise ContractError("HP归零但正文没有死亡或致命结果")
    checks = ((proposals["items"], ("获得", "得到", "拾取", "失去", "消耗", "装备"), "物品"),
              ([proposals["currency"]] if proposals["currency"]["copper_delta"] else [],
               ("金币", "银币", "铜币", "金钱", "报酬"), "货币"),
              ([x for x in proposals["quests"] if x["status"] in TERMINAL_QUEST_STATES],
               ("任务完成", "任务失败", "拒绝任务", "放弃任务", "委托完成"), "任务终局"),
              (proposals["reputations"], ("公开", "传播", "众人", "居民", "声名", "名望"), "声望公开"))
    for values, terms, label in checks:
        if values and not any(term in body for term in terms):
            raise ContractError(f"正文缺少{label}提案的关键叙述")
    move = response["scene"]["location"]
    if move["operation"] == "move" and not any(term in body for term in ("抵达", "来到", "进入", "前往", "离开")):
        raise ContractError("正文与移动提案不一致")
    breakthrough = proposals["breakthrough"]
    if breakthrough and breakthrough["attempted"] and not any(term in body for term in ("突破", "升阶", "瓶颈")):
        raise ContractError("正文与突破提案不一致")


def adjudicate(state, response, canonical_locations, regional_quest_ids,
               quest_context=None, action=None, regional_definitions=None):
    _reject_duplicate_keyed_proposals(response["proposals"])
    _validate_breakthrough_intent(response, action)
    _validate_narrative_consistency(state, response)
    result = copy.deepcopy(state)
    changes = []
    receipts = []
    reputation_audit = []
    new_locations = []
    memory_operations = []
    local_locations = {}
    base_world_flags = copy.deepcopy(state.get("world_flags", {}))
    result.setdefault("npcs", {})
    local_npcs = {item["ref"]: "npc." + str(uuid.uuid4())
                  for item in response["scene"]["new_npcs"]}
    new_npcs = []
    for candidate in response["scene"]["new_npcs"]:
        stable_id = local_npcs[candidate["ref"]]
        npc = {"id": stable_id, "name": candidate["name"],
               "description": candidate["description"], "source": candidate["reason"]}
        result["npcs"][stable_id] = npc
        new_npcs.append(npc)
        receipts.append(("npc:" + stable_id, "npc", npc))
        changes.append(_change("npc", stable_id, None, npc, candidate["reason"]))
    for candidate in response["scene"]["new_locations"]:
        parent = canonical_locations.get(candidate["parent_id"]) or state.get("locations", {}).get(candidate["parent_id"])
        if not parent:
            raise ContractError("新地点父节点不存在")
        inherited_region = parent["region_id"]
        if candidate["region_id"] != inherited_region:
            raise ContractError("新地点region_id必须与父地点区域一致")
        if candidate["ref"].replace("location:new:", "") in canonical_locations:
            raise ContractError("新地点不得伪造正典ID")
        stable_id = "dynamic." + str(uuid.uuid4())
        local_locations[candidate["ref"]] = stable_id
        stored = {"id": stable_id, "name": candidate["name"], "type": candidate["type"],
                  "parent_id": candidate["parent_id"], "region_id": inherited_region,
                  "description": candidate["description"], "canonical": False}
        new_locations.append(stored)
        result.setdefault("locations", {})[stable_id] = stored
        receipts.append(("location:" + stable_id, "location", stored))
    move = response["scene"]["location"]
    if move["operation"] == "move":
        destination = move["location_id"] or local_locations.get(move["location_ref"])
        if not destination or (destination not in canonical_locations and destination not in result.get("locations", {})):
            raise ContractError("目标地点不存在")
        old = result["location"]["id"]
        result["location"] = {"id": destination,
                              "name": (canonical_locations.get(destination) or
                                       result["locations"].get(destination, {})).get("name", destination)}
        changes.append(_change("location", "current_location_id", old, destination, move["reason"]))
    result["time"]["elapsed_minutes"] += response["scene"]["elapsed_minutes"]
    if response["scene"]["time_label"] != result["time"]["label"]:
        old = result["time"]["label"]
        result["time"]["label"] = response["scene"]["time_label"]
        changes.append(_change("time", "time_label", old, result["time"]["label"],
                               f"经过{response['scene']['elapsed_minutes']}分钟"))

    proposals = response["proposals"]
    for proposal in proposals["resources"]:
        resource = result["character"]["resources"][proposal["key"]]
        old = resource["current"]
        resource["current"] = max(0, min(resource["max"], old + proposal["delta"]))
        if resource["current"] != old:
            changes.append(_change("resource", proposal["key"], old, resource["current"], proposal["reason"]))
    result["character"]["alive"] = result["character"]["resources"]["hp"]["current"] > 0
    effects = []
    if not result["character"]["alive"]:
        result["character"]["status"] = "dead"
        effects.append("dead")
    else:
        result["character"]["status"] = "normal"
    zero_effects = {"mp": "mana_depleted", "sp": "mental_collapse", "st": "exhausted"}
    for key, effect in zero_effects.items():
        if result["character"]["resources"][key]["current"] == 0:
            effects.append(effect)
    result["character"]["status_effects"] = effects

    for proposal in proposals["attributes"]:
        if not proposal["long_term_basis"].strip() or len(proposal["long_term_basis"].strip()) < 4:
            raise ContractError("长期属性变化缺少长期积累依据")
        if abs(proposal["delta"]) > 10 and not _contains_any(
                proposal["long_term_basis"], ("长期", "多年", "数年", "数月", "累计", "系统训练", "重大")):
            raise ContractError("大幅长期属性结算缺少重大长期积累依据")
        attribute = result["character"]["attributes"][proposal["key"]]
        old = attribute["value"]
        new = old + proposal["delta"]
        if not 1 <= new <= 100:
            raise ContractError("长期属性变化超出1至100")
        attribute["value"] = new
        if new != old:
            changes.append(_change("attribute", proposal["key"], old, new, proposal["reason"]))

    character = result["character"]
    for proposal in proposals["experience"]:
        threshold = EXP_THRESHOLDS[character["rank"]]
        if threshold is None:
            continue
        old = character["exp"]
        character["exp"] = min(threshold, old + proposal["amount"])
        if character["exp"] != old:
            changes.append(_change("experience", "exp", old, character["exp"], proposal["reason"]))
    threshold = EXP_THRESHOLDS[character["rank"]]
    character["breakthrough_eligible"] = threshold is not None and character["exp"] >= threshold
    if character["breakthrough_eligible"] and character["rank"] >= 6:
        target_rank = character["rank"] + 1
        existing = next((q for q in result["quests"].values()
                         if q.get("quest_kind") == "breakthrough" and
                         q.get("target_rank") == target_rank and
                         q.get("status") in {"offered", "active", "completed"} and
                         not q.get("consumed")), None)
        proposed = next((q for q in proposals["quests"]
                         if q["operation"] == "create" and q["quest_kind"] == "breakthrough" and
                         q["target_rank"] == target_rank), None)
        if not existing and not proposed:
            raise ContractError("六升七及以上满EXP时必须创建对应突破任务")
    breakthrough = proposals["breakthrough"]
    consumed_breakthrough_task = None
    if breakthrough and breakthrough["attempted"]:
        if character["rank"] <= 6:
            resources = character["resources"]
            if (not character["alive"] or character["status"] != "normal" or
                    resources["hp"]["current"] <= 0 or resources["sp"]["current"] <= 0 or
                    resources["st"]["current"] <= 0):
                raise ContractError("1至6阶突破要求生命、精神、精力和角色状态正常")
            if len(breakthrough["method"].strip()) < 2 or len(breakthrough["preparation"].strip()) < 2:
                raise ContractError("1至6阶突破必须说明方法和准备")
        if breakthrough["success"]:
            if not character["breakthrough_eligible"] or character["rank"] >= 10:
                raise ContractError("角色不具备成功突破资格")
            if character["rank"] >= 6:
                task_id = breakthrough["task_completed_id"]
                task = result["quests"].get(task_id or "")
                completion = next((proposal for proposal in proposals["quests"]
                                   if proposal["quest_id"] == task_id and
                                   proposal["status"] == "completed"), None)
                if (not task or task.get("status") != "completed" or
                        task.get("quest_kind") != "breakthrough" or
                        task.get("target_rank") != character["rank"] + 1 or task.get("consumed")) and not (
                            task and completion and task.get("quest_kind") == "breakthrough" and
                            task.get("target_rank") == character["rank"] + 1 and not task.get("consumed")):
                    raise ContractError("高阶突破缺少已完成突破任务")
                consumed_breakthrough_task = task_id
            old_rank = character["rank"]
            character["rank"] += 1
            character["exp"] = 0
            character["exp_to_next"] = EXP_THRESHOLDS[character["rank"]]
            character["base_power"] = POWER_BY_RANK[character["rank"]]
            character["breakthrough_eligible"] = False
            changes.append(_change("rank", "rank", old_rank, character["rank"], breakthrough["reason"]))
        elif not breakthrough["failure_reason"] or not breakthrough["improvement"]:
            raise ContractError("突破失败必须给出原因和改善方向")

    inventory = result["inventory"]
    for proposal in proposals["items"]:
        operation = proposal["operation"]
        item_id = proposal["item_id"]
        if operation == "add":
            item_id = item_id or "item." + str(uuid.uuid4())
            if item_id in inventory:
                inventory[item_id]["quantity"] += proposal["quantity"]
            else:
                inventory[item_id] = {"id": item_id, "name": proposal["name"],
                                      "description": proposal["description"],
                                      "quantity": proposal["quantity"], "power": proposal["power"],
                                      "equipped": False, "source": proposal["source"]}
            receipts.append(("item:" + item_id + ":" + operation, "item", inventory[item_id]))
            changes.append(_change("item", item_id, None, inventory[item_id], proposal["reason"]))
        elif item_id not in inventory:
            raise ContractError("物品不存在")
        elif operation == "remove":
            old = inventory[item_id]["quantity"]
            if old < proposal["quantity"]:
                raise ContractError("物品数量不足")
            inventory[item_id]["quantity"] -= proposal["quantity"]
            if inventory[item_id]["quantity"] == 0:
                del inventory[item_id]
            changes.append(_change("item", item_id, old, old - proposal["quantity"], proposal["reason"]))
        else:
            old = inventory[item_id]["equipped"]
            inventory[item_id]["equipped"] = operation == "equip"
            changes.append(_change("item", item_id + ".equipped", old,
                                   inventory[item_id]["equipped"], proposal["reason"]))
    old_currency = result["currency_copper"]
    new_currency = old_currency + proposals["currency"]["copper_delta"]
    if new_currency < 0:
        raise ContractError("货币余额不能为负")
    result["currency_copper"] = new_currency
    if new_currency != old_currency:
        changes.append(_change("currency", "copper", old_currency, new_currency,
                               proposals["currency"]["reason"]))
        receipts.append(("currency", "currency", {"delta": new_currency - old_currency}))

    for proposal in proposals["quests"]:
        quest_id = proposal["quest_id"]
        if proposal["operation"] == "create":
            quest_id = quest_id or "quest." + str(uuid.uuid4())
            if quest_id in result["quests"] or quest_id in regional_quest_ids:
                raise ContractError("任务ID已存在")
            if proposal["quest_kind"] == "regional":
                raise ContractError("地区任务不能由模型创建")
            if proposal["quest_kind"] == "breakthrough":
                if (proposal["target_rank"] != character["rank"] + 1 or
                        proposal["status"] not in {"offered", "active"}):
                    raise ContractError("突破任务目标阶位或初始状态无效")
            elif proposal["target_rank"] is not None:
                raise ContractError("普通任务不能设置突破目标阶位")
            result["quests"][quest_id] = {"id": quest_id, "name": proposal["name"],
                                          "description": proposal["description"],
                                          "status": proposal["status"], "progress": proposal["progress"],
                                          "objectives": proposal["objectives"], "regional": False,
                                          "quest_kind": proposal["quest_kind"],
                                          "target_rank": proposal["target_rank"], "consumed": False,
                                          "necessary_nodes": proposal["necessary_nodes"]}
        else:
            if quest_id in regional_quest_ids:
                current = result["regional_quests"][quest_id]
            else:
                current = result["quests"].get(quest_id)
            if not current:
                raise ContractError("任务不存在")
            old_status = current["status"]
            if old_status in TERMINAL_QUEST_STATES:
                raise ContractError("终局任务不能再次变化")
            if proposal["status"] != old_status and proposal["status"] not in QUEST_TRANSITIONS.get(old_status, set()):
                raise ContractError("任务状态转移无效")
            if quest_id in regional_quest_ids:
                context_item = (quest_context or {}).get(quest_id, {})
                if proposal["quest_kind"] != "regional" or proposal["target_rank"] is not None:
                    raise ContractError("地区任务提案类型无效")
                _validate_regional_transition(
                    quest_id, current, proposal, context_item.get("context_eligibility"),
                    _player_action_text(action),
                    response["narrative"]["body"], proposals)
            elif (proposal["quest_kind"] != current.get("quest_kind", "regular") or
                  proposal["target_rank"] != current.get("target_rank")):
                raise ContractError("任务类型或目标阶位不能在状态转移中改变")
            current.update({key: proposal[key] for key in ("status", "progress", "objectives")
                            if proposal[key] is not None})
            changes.append(_change("quest", quest_id, old_status, current["status"], proposal["reason"]))
            if current["status"] in TERMINAL_QUEST_STATES:
                receipts.append(("quest-terminal:" + quest_id, "quest", {"status": current["status"]}))
                if current["status"] == "completed" and quest_id in regional_quest_ids:
                    definition = (regional_definitions or {}).get(quest_id)
                    if not definition:
                        raise ContractError("地区任务缺少冻结奖励定义")
                    for reward in definition["rewards"]["items"]:
                        condition = reward.get("condition", {})
                        if condition.get("race_not") == result["character"]["identity"].get("race_id"):
                            continue
                        if reward["id"] in result["inventory"]:
                            raise ContractError("地区任务固定奖励已存在")
                        item = {"id": reward["id"], "name": reward["name"],
                                "description": reward["description"], "quantity": 1,
                                "power": 0, "equipped": False, "source": quest_id}
                        result["inventory"][reward["id"]] = item
                        receipts.append(("regional-reward:item:" + reward["id"], "item", item))
                        changes.append(_change("item", reward["id"], None, item, "地区任务固定奖励"))
                    for reward in definition["rewards"]["bonds"]:
                        if reward["npc_id"] not in result["bonds"]:
                            bond = {"id": "bond." + str(uuid.uuid4()), "npc_id": reward["npc_id"],
                                    "npc_name": reward["npc_name"], "value": 21,
                                    "relation_type": reward["relation_type"], "listed": True,
                                    "level": bond_level(21)}
                            result["bonds"][reward["npc_id"]] = bond
                            receipts.append(("regional-reward:bond:" + reward["npc_id"], "bond", bond))
                            changes.append(_change("bond", reward["npc_id"], None, 21,
                                                   "地区任务固定结识关系"))
                    for flag in definition["rewards"]["world_flags"]:
                        result["world_flags"][flag] = True
                        receipts.append(("regional-reward:flag:" + flag, "world_flag", {flag: True}))
                        changes.append(_change("world_flag", flag, None, True, "地区任务固定结果"))
    if consumed_breakthrough_task:
        result["quests"][consumed_breakthrough_task]["consumed"] = True

    for proposal in proposals["bonds"]:
        if proposal["npc_ref"]:
            npc_id = local_npcs[proposal["npc_ref"]]
        else:
            npc_id = proposal["npc_id"]
            if (npc_id not in result["bonds"] and npc_id not in result["npcs"] and
                    not npc_id.startswith("canon.npc.")):
                raise ContractError("羁绊npc_id不是既有稳定NPC")
        bond = result["bonds"].get(npc_id)
        if proposal["operation"] == "create_or_join":
            if bond:
                raise ContractError("羁绊已存在")
            bond = {"id": "bond." + str(uuid.uuid4()), "npc_id": npc_id,
                    "npc_name": proposal["npc_name"], "value": 0,
                    "relation_type": proposal["relation_type"], "listed": True}
            result["bonds"][npc_id] = bond
        elif not bond:
            raise ContractError("羁绊不存在")
        old = bond["value"]
        new = max(-100, min(100, old + proposal["delta"]))
        bond["value"] = new
        if proposal["operation"] == "change_relation_type":
            bond["relation_type"] = proposal["relation_type"]
        bond["level"] = bond_level(new)
        changes.append(_change("bond", npc_id, old, new, proposal["reason"],
                               {"old_level": bond_level(old), "new_level": bond["level"]}))
        receipts.append(("bond:" + npc_id, "bond", {"old": old, "new": new}))

    for proposal in proposals["reputations"]:
        reputation = result["reputations"][proposal["key"]]
        old = reputation["value"]
        new = max(-100, min(100, old + proposal["delta"]))
        reputation.update({"value": new, "level": reputation_level(new)})
        changes.append(_change("reputation", proposal["key"], old, new,
                               proposal["public_reason"],
                               {"old_level": reputation_level(old), "new_level": reputation["level"]}))
        reputation_audit.append({"key": proposal["key"], "old": old, "new": new,
                                 "public_reason": proposal["public_reason"]})
        receipts.append(("reputation:" + proposal["key"], "reputation", {"old": old, "new": new}))

    for group in ("skills", "talents"):
        collection = result["character"][group]
        for proposal in proposals[group]:
            item_id = proposal["id"] or group[:-1] + "." + str(uuid.uuid4())
            if proposal["operation"] == "add":
                if any(item["id"] == item_id for item in collection):
                    raise ContractError(group + " ID已存在")
                collection.append({"id": item_id, "name": proposal["name"],
                                   "description": proposal["description"], "source": proposal["source"]})
            else:
                existing = next((item for item in collection if item["id"] == item_id), None)
                if not existing:
                    raise ContractError(group + " 不存在")
                if proposal["operation"] == "remove": collection.remove(existing)
                else: existing.update({"name": proposal["name"],
                                       "description": proposal["description"], "source": proposal["source"]})
            changes.append(_change(group[:-1], item_id, None, proposal["operation"], proposal["reason"]))
    for proposal in proposals["world_flags"]:
        old = result["world_flags"].get(proposal["key"])
        result["world_flags"][proposal["key"]] = proposal["value"]
        changes.append(_change("world_flag", proposal["key"], old, proposal["value"], proposal["reason"]))

    equipped_power = sum(item.get("power", 0) for item in inventory.values() if item.get("equipped"))
    if equipped_power > int(character["base_power"] * .4):
        raise ContractError("常规装备战力超过基础战力40%")
    modifiers = copy.deepcopy(character.get("power_modifiers", []))
    old_effective_power = character.get("effective_power", character["base_power"])
    for item in proposals["power_modifiers"]:
        existing = next((value for value in modifiers if value["id"] == item["id"]), None)
        if item["operation"] == "add":
            if existing:
                raise ContractError("战力修正已存在")
            modifiers.append({"id": item["id"], "value": item["value"], "reason": item["reason"],
                              "temporary": item["temporary"], "category": item["category"],
                              "severity": item["severity"],
                              "canonical_exception": item["canonical_exception"]})
        elif not existing:
            raise ContractError("战力修正不存在")
        elif item["operation"] == "update":
            existing.update({"value": item["value"], "reason": item["reason"],
                             "temporary": item["temporary"], "category": item["category"],
                             "severity": item["severity"],
                             "canonical_exception": item["canonical_exception"]})
        else:
            modifiers.remove(existing)
    exception_state = copy.deepcopy(result)
    exception_state["world_flags"] = base_world_flags
    for item in modifiers:
        if item["severity"] in {"major", "extreme"} and not canonical_power_exception_applies(
                item["canonical_exception"], exception_state, item["value"]):
            raise ContractError("重大或极端战力修正的正典例外不适用于当前种族、地点、阶位或形态")
    character["power_modifiers"] = modifiers
    character["equipment_power"] = equipped_power
    character["effective_power"] = max(0, character["base_power"] + equipped_power +
                                       sum(item["value"] for item in modifiers))
    non_exceptional = [item for item in modifiers if item.get("severity") != "extreme"]
    non_exceptional_power = character["base_power"] + equipped_power + sum(
        item["value"] for item in non_exceptional)
    rank = character["rank"]
    next_power = POWER_BY_RANK.get(rank + 2)
    if next_power is not None and non_exceptional_power >= next_power:
        raise ContractError("普通场景战力修正不能覆盖两阶差距")
    if rank < 10 and character["effective_power"] >= POWER_BY_RANK[10] and not any(
            item.get("severity") == "extreme" and item.get("canonical_exception") for item in modifiers):
        raise ContractError("非十阶不能靠普通修正跨越十阶鸿沟")
    if character["effective_power"] != old_effective_power:
        changes.append(_change("power", "effective_power", old_effective_power,
                               character["effective_power"], "战力修正发生变化"))
    for memory in response["memory_candidates"]:
        canonical_npcs = {
            reward["npc_id"]
            for definition in (regional_definitions or {}).values()
            for reward in definition.get("rewards", {}).get("bonds", [])
        }
        known_people = set(result["npcs"]) | set(result["bonds"]) | set(local_npcs) | canonical_npcs
        unknown_people = set(memory["people"]) - known_people
        if unknown_people:
            raise ContractError("记忆people必须引用已知或本回合新建NPC")
        known_locations = set(canonical_locations) | set(result.get("locations", {})) | set(local_locations)
        unknown_locations = set(memory["locations"]) - known_locations
        if unknown_locations:
            raise ContractError("记忆locations必须引用已知或本回合新建地点")
        rewritten = copy.deepcopy(memory)
        rewritten["people"] = [local_npcs.get(person, person) for person in rewritten["people"]]
        rewritten["locations"] = [local_locations.get(location, location)
                                  for location in rewritten["locations"]]
        memory_operations.append(rewritten)
    result["state_version"] = state["state_version"] + 1
    return {"state": result, "changes": changes, "receipts": receipts,
            "reputation_audit": reputation_audit, "new_locations": new_locations,
            "memory_operations": memory_operations, "new_npcs": new_npcs}


def receipt_hash(payload):
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode("utf-8")).hexdigest()


def validate_story_arc(value, contract=None):
    try:
        validate_contract(value, "story_arc", contract)
    except ValueError as exc:
        raise ContractError(str(exc)) from None
    _exact(value, {"schema_version", "title", "summary", "key_events", "unresolved"}, "故事弧")
    if value["schema_version"] != "story-arc/1":
        raise ContractError("故事弧版本无效")
    for key in ("title", "summary"):
        _text(value[key], "story_arc." + key, 20000)
    for key in ("key_events", "unresolved"):
        if any(not isinstance(item, str) for item in _list(value[key], "story_arc." + key, 100)):
            raise ContractError("故事弧数组字段无效")
    return copy.deepcopy(value)
