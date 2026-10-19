"""Strict GM response validation and deterministic state adjudication."""

import copy
import hashlib
import json
import re
import uuid

try:
    from .canonical_npcs import CANONICAL_NPCS, canonical_name_collision
    from .catalog import EXP_THRESHOLDS, POWER_BY_RANK
    from .contract_registry import validate_contract, validate_json_schema
    from .location_graph import JURISDICTION_IDS
except ImportError:
    from canonical_npcs import CANONICAL_NPCS, canonical_name_collision
    from catalog import EXP_THRESHOLDS, POWER_BY_RANK
    from contract_registry import validate_contract, validate_json_schema
    from location_graph import JURISDICTION_IDS


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
    "untriggered": {"eligible", "offered", "active", "declined", "failed"},
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
    "canon:sea_folk_deep_sea": 4,
    "canon:tenth_rank_discontinuity": 1,
    "canon:featherfolk_open_air": 1,
    "canon:elf_forest_affinity": 1,
    "canon:dragon_true_form": 2,
}
# Per-event caps the prompt states verbatim (runtime state-rules policy) and the adjudicator enforces.
BOND_IMPACT_LIMITS = {"minor": 5, "moderate": 15, "major": 25, "life_defining": 35}
REPUTATION_IMPACT_LIMITS = {"minor": 5, "moderate": 15, "major": 35, "world_shaping": 50}
ATTRIBUTE_DELTA_LIMIT = 20
# Power modifier caps as a share of base power, unless a verified canonical exception applies.
MODIFIER_SEVERITY_SHARE = {"minor": .10, "moderate": .25, "major": .50, "extreme": 1.0}
ORDINARY_EQUIPMENT_SHARE = .4
RANK_UP_RESOURCE_GROWTH = 1.3
AGE_DELTA_LIMIT = 200
AFFIRMATIVE_NEGATION_IDIOMS = {
    "毫不犹豫": "果断", "不得不": "必须", "不由得": "自然",
    "不禁": "自然", "不妨": "可以", "并非不": "确实",
    "并不是不": "确实", "不是不": "确实",
}
GENERIC_TASK_ACCEPT_TERMS = ("接受任务", "接取任务", "接受委托", "接取委托", "同意委托",
                             "接受护送", "担任护卫", "加入商队", "受雇", "签下契约")
BREAKTHROUGH_ACCEPT_TERMS = ("尝试突破", "进行突破", "开始突破", "升阶", "晋阶", "冲阶",
                             "冲关", "破境", "跨过力量关隘",
                             "breakthrough", "rank up", "advance rank")


class ContractError(Exception):
    def __init__(self, message, path=None):
        self.path = path
        super().__init__((path + "：" if path else "") + message)


def _path_error(path, message):
    raise ContractError(message, path)


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
        "conditions": lambda item: item.get("id"),
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
        for index, item in enumerate(proposals.get(group, [])):
            key = key_for(item) if isinstance(item, dict) else None
            if key is None:
                continue
            if key in seen:
                _path_error(f"$.proposals.{group}[{index}]",
                            f"{group}不能对同一键或ID提交多个提案")
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
    if exception not in CANONICAL_POWER_EXCEPTIONS or type(modifier_value) is not int:
        return False
    character = state.get("character", {})
    race = character.get("identity", {}).get("race_id")
    rank = character.get("rank")
    base_power = POWER_BY_RANK.get(rank)
    if base_power is None or abs(modifier_value) > base_power * CANONICAL_POWER_EXCEPTIONS[exception]:
        return False
    if exception == "canon:sea_folk_deep_sea":
        return race == "sea_folk" and rank >= 7 and _location_matches_region(state, "abyssal_tides")
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
    action_type = action.get("action_type")
    if action_type == "reshape":
        value = action.get("reshape_guidance", "")
    elif action_type == "turn":
        value = action.get("action", "")
    else:
        value = action.get("guidance", "") or action.get("action", "")
    return value.lower() if isinstance(value, str) else ""


def _text_clauses(text):
    return [value.strip() for value in re.split(r"[。！？!?；;，,\r\n]+", text) if value.strip()]


def _normalized_clause(text):
    return text.strip().strip("。！？!?；;，,：:\"'“”‘’「」『』").strip()


def _has_negated_action(text, terms):
    return any(_clause_negates_terms(clause, terms) for clause in _text_clauses(text))


def _explicit_affirmed_action(text, terms):
    clauses = [clause for clause in _text_clauses(text) if _contains_any(clause, terms)]
    return bool(clauses) and not any(_clause_negates_terms(clause, terms) for clause in clauses)


def _clause_negates_terms(clause, terms):
    normalized = clause.lower()
    for source, replacement in AFFIRMATIVE_NEGATION_IDIOMS.items():
        normalized = normalized.replace(source, replacement)
    has_target = (_contains_task_acceptance(normalized)
                  if terms is GENERIC_TASK_ACCEPT_TERMS else _contains_any(normalized, terms))
    if not has_target:
        return False
    if re.match(r"^(?:我|本人|角色)?(?:绝对|明确)?(?:不(?:想|愿|肯|会|能|再|要)?|别)", normalized):
        return True
    for term in terms:
        start = normalized.find(term)
        while start >= 0:
            prefix = normalized[max(0, start - 12):start]
            if re.search(r"(?:不(?:想|愿|肯|会|能|再|要|打算|准备|同意)?|别|拒绝|放弃|取消)"
                         r"[^。！？!?；;，,]{0,4}$", prefix):
                return True
            start = normalized.find(term, start + 1)
    return False


def _contains_task_acceptance(text):
    if _contains_any(text, GENERIC_TASK_ACCEPT_TERMS):
        return True
    return bool(re.search(r"(?:接受|接取|同意|承接|加入|受雇|签下)"
                          r"[^。！？!?；;，,]{0,12}(?:任务|委托|护送|护卫|商队|契约)", text))


def _evidence_matches_action(evidence, action_text):
    evidence = _normalized_clause(evidence).lower()
    return bool(evidence and evidence in action_text)


# Negation right before or inside a quoted intent ("我不接", "先不突破", "拒绝委托").
INTENT_NEGATION = re.compile(r"不|别|拒绝|放弃|取消|暂缓|没(?:有)?(?:打算|准备|想)")
CLAUSE_BOUNDARY = "。！？!?；;，,\r\n"


def _evidence_authorizes_action(evidence, action_text):
    """Whether the player really chose to do something (accept a quest, attempt a breakthrough).

    The model judges the intent and quotes the short span of this turn's player input that
    expresses it. The program only checks that the quote is verbatim from that input and that it
    is not negated inside the quote or in the few characters right before it.
    """
    quote = _normalized_clause(evidence).lower()
    if len(quote) < 2:
        return False
    start = action_text.find(quote)
    if start < 0:
        return False
    # Look back to the start of the clause, or to a turn such as "但/还是/不过" that overrides
    # an earlier negation ("我不太确定，但我接了").
    boundary = max(action_text.rfind(mark, 0, start) for mark in CLAUSE_BOUNDARY)
    scope = re.split(r"但是|但|可是|还是|不过|然而", action_text[boundary + 1:start] + quote)[-1]
    for source, replacement in AFFIRMATIVE_NEGATION_IDIOMS.items():
        scope = scope.replace(source, replacement)
    return not INTENT_NEGATION.search(scope)


def _evidence_authorizes_terms(evidence, action_text, terms):
    """Regional quests keep their trigger words from the source text on top of the intent check."""
    quote = _normalized_clause(evidence).lower()
    return _evidence_authorizes_action(evidence, action_text) and _contains_any(quote, terms)


def _validate_breakthrough_intent(response, action):
    breakthrough = response["proposals"].get("breakthrough")
    if breakthrough and (breakthrough.get("attempted") or breakthrough.get("success")):
        action_text = _player_action_text(action)
        if not _evidence_authorizes_action(breakthrough.get("action_evidence", ""), action_text):
            raise ContractError("突破尝试或成功时，action_evidence必须逐字摘取本次玩家输入中表达突破意图的短句，且不能是否定说法")


def validate_gm_response(value, response_type=None, contract=None):
    try:
        validate_contract(value, "gm_turn", contract)
    except ValueError as exc:
        raise ContractError(str(exc)) from None
    _exact(value, {"schema_version", "response_type", "narrative", "scene", "proposals",
                   "memory_candidates", "warnings"}, "响应")
    if value["schema_version"] != "gm-turn/2":
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
    option_ids, option_texts = set(), set()
    for option_index, option in enumerate(options):
        _exact(option, {"id", "text", "intent"}, "option")
        for key in option:
            _text(option[key], "option." + key, 1000)
        if option["id"] in option_ids or option["text"] in option_texts:
            _path_error(f"$.narrative.suggested_options[{option_index}]",
                        "suggested_options不能重复")
        option_ids.add(option["id"]); option_texts.add(option["text"])

    scene = value["scene"]
    _exact(scene, {"time_label", "elapsed_minutes", "player_life_state", "location",
                   "new_locations", "location_updates", "new_npcs", "npc_updates"}, "scene")
    if scene["time_label"] not in TIME_LABELS:
        raise ContractError("scene.time_label无效")
    _integer(scene["elapsed_minutes"], "scene.elapsed_minutes", 0, 5256000)
    if scene["player_life_state"] not in {"alive", "dead"}:
        raise ContractError("scene.player_life_state无效")
    location = scene["location"]
    _exact(location, {"operation", "location_id", "location_ref", "reason"}, "scene.location")
    if location["operation"] not in {"stay", "move"}:
        raise ContractError("地点操作无效")
    for key in ("location_id", "location_ref"):
        if location[key] is not None:
            _text(location[key], "scene.location." + key, 300)
    _text(location["reason"], "scene.location.reason", 2000, empty=True)
    if location["operation"] == "stay":
        if location["location_id"] is not None or location["location_ref"] is not None:
            raise ContractError("停留时不得填写地点引用")
    elif bool(location["location_id"]) == bool(location["location_ref"]):
        raise ContractError("移动必须且只能引用一个地点")
    new_refs = set()
    for item in _list(scene["new_locations"], "new_locations", 10):
        _exact(item, {"ref", "name", "type", "scope", "parent_id", "parent_ref",
                      "jurisdiction_id", "description", "reason"},
               "new_location")
        for key, maximum in (("ref", 300), ("name", 300), ("type", 100),
                             ("description", 4000), ("reason", 2000)):
            _text(item[key], "new_location." + key, maximum)
        for key in ("parent_id", "parent_ref", "jurisdiction_id"):
            if item[key] is not None:
                _text(item[key], "new_location." + key, 300)
        if not item["ref"].startswith("location:new:") or item["ref"] in new_refs:
            raise ContractError("新地点局部引用无效")
        if item["scope"] not in {"region", "place"}:
            raise ContractError("新地点scope无效")
        if bool(item["parent_id"]) == bool(item["parent_ref"]):
            raise ContractError("新地点必须且只能引用一个父节点")
        if item["parent_ref"] and item["parent_ref"] not in new_refs:
            raise ContractError("新地点parent_ref只能引用本数组中更早声明的地点")
        if item["jurisdiction_id"] is not None and item["jurisdiction_id"] not in JURISDICTION_IDS:
            raise ContractError("新地点政治辖区无效")
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
    for item in _list(scene["location_updates"], "location_updates", 20):
        _exact(item, {"location_id", "status", "accessible", "description", "reason", "evidence"},
               "location_update")
        for key in ("location_id", "status", "reason", "evidence"):
            _text(item[key], "location_update." + key, 4000)
        _text(item["description"], "location_update.description", 4000, empty=True)
        if type(item["accessible"]) is not bool:
            raise ContractError("location_update.accessible无效")
    for item in _list(scene["npc_updates"], "npc_updates", 30):
        _exact(item, {"npc_id", "status", "location_id", "availability", "current_goal",
                      "reason", "evidence"}, "npc_update")
        for key in ("npc_id", "status", "availability", "reason", "evidence"):
            _text(item[key], "npc_update." + key, 4000)
        if item["location_id"] is not None:
            _text(item["location_id"], "npc_update.location_id", 300)
        _text(item["current_goal"], "npc_update.current_goal", 2000, empty=True)

    proposals = value["proposals"]
    proposal_fields = {"resources", "attributes", "conditions", "experience", "breakthrough", "items",
                       "currency", "quests", "bonds", "reputations", "skills", "talents",
                       "world_flags", "power_modifiers"}
    # "age" exists only in newer contracts; saves frozen on an older one never send it.
    _exact(proposals, proposal_fields | ({"age"} if "age" in proposals else set()), "proposals")
    if proposals.get("age") is not None:
        age = proposals["age"]
        _proposal_reason(age, "age", ("years_delta",))
        if type(age["years_delta"]) is not int or age["years_delta"] == 0 or abs(age["years_delta"]) > AGE_DELTA_LIMIT:
            raise ContractError(f"age.years_delta必须是非零整数，绝对值不超过{AGE_DELTA_LIMIT}")
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
        if type(item["delta"]) is not int or abs(item["delta"]) > ATTRIBUTE_DELTA_LIMIT:
            raise ContractError(f"attribute.delta单回合最多±{ATTRIBUTE_DELTA_LIMIT}（只有重大事件才能接近上限，常规为1至3）")
        _text(item["long_term_basis"], "attribute.long_term_basis", 4000)
    for item in _list(proposals["conditions"], "conditions"):
        _proposal_reason(item, "condition", ("operation", "id", "name", "description",
                                               "temporary", "expires_at", "source"))
        if item["operation"] not in {"add", "update", "remove", "expire"}:
            raise ContractError("condition.operation无效")
        if item["id"] is not None:
            _text(item["id"], "condition.id", 300)
        if item["operation"] != "add" and item["id"] is None:
            raise ContractError("更新或移除状态必须提供稳定ID")
        for key in ("name", "description", "source"):
            _text(item[key], "condition." + key, 4000, empty=key == "description")
        if type(item["temporary"]) is not bool:
            raise ContractError("condition.temporary无效")
        if item["expires_at"] is not None:
            _text(item["expires_at"], "condition.expires_at", 300)
    low_value_exp = 0
    for item in _list(proposals["experience"], "experience", 20):
        _exact(item, {"amount", "growth_type", "challenge", "novelty", "repetition",
                      "reason", "evidence"}, "experience")
        _integer(item["amount"], "experience.amount", 0, 100000)
        for key in ("growth_type", "challenge", "novelty", "repetition", "reason", "evidence"):
            _text(item[key], "experience." + key, 4000)
        if (item["challenge"] == "low" and item["novelty"] == "none" and
                item["repetition"] == "repeated"):
            low_value_exp += item["amount"]
    if low_value_exp > 10:
        raise ContractError("同一回合低挑战、无新颖度且重复行为累计不能获得大额EXP")
    breakthrough = proposals["breakthrough"]
    if breakthrough is not None:
        _exact(breakthrough, {"attempted", "success", "action_evidence", "method", "preparation", "failure_reason", "improvement",
                              "task_completed_id", "reason", "evidence"}, "breakthrough")
        if type(breakthrough["attempted"]) is not bool or type(breakthrough["success"]) is not bool:
            raise ContractError("突破布尔字段无效")
        if breakthrough["success"] and not breakthrough["attempted"]:
            raise ContractError("突破成功必须同时标记attempted")
        for key in ("failure_reason", "improvement", "task_completed_id"):
            if breakthrough[key] is not None:
                _text(breakthrough[key], "breakthrough." + key, 2000)
        _text(breakthrough["action_evidence"], "breakthrough.action_evidence", 4000,
              empty=not breakthrough["attempted"])
        _text(breakthrough["method"], "breakthrough.method", 2000)
        _text(breakthrough["preparation"], "breakthrough.preparation", 2000)
        _text(breakthrough["reason"], "breakthrough.reason", 2000)
        _text(breakthrough["evidence"], "breakthrough.evidence", 4000)
    for item in _list(proposals["items"], "items"):
        _proposal_reason(item, "item", ("operation", "item_id", "name", "description",
                                         "quantity", "power", "power_class", "power_basis",
                                         "equipped", "source"))
        if item["operation"] not in {"add", "remove", "equip", "unequip"}:
            raise ContractError("物品操作无效")
        if item["item_id"] is not None:
            _text(item["item_id"], "item.item_id", 300)
        _text(item["name"], "item.name", 300)
        _text(item["description"], "item.description", 4000, empty=True)
        _integer(item["quantity"], "item.quantity", 1, 1000000)
        _integer(item["power"], "item.power", 0, 1000000)
        if item["power_class"] not in {"ordinary", "high_rank", "exceptional"}:
            raise ContractError("item.power_class无效")
        _text(item["power_basis"], "item.power_basis", 4000,
              empty=item["power_class"] == "ordinary")
        if type(item["equipped"]) is not bool:
            raise ContractError("item.equipped无效")
        _text(item["source"], "item.source", 1000)
    currency = proposals["currency"]
    _exact(currency, {"copper_delta", "reason", "evidence"}, "currency")
    _integer(currency["copper_delta"], "currency.copper_delta", -1000000000, 1000000000)
    _text(currency["reason"], "currency.reason", 2000, empty=True)
    _text(currency["evidence"], "currency.evidence", 4000, empty=True)
    for item in _list(proposals["quests"], "quests"):
        _proposal_reason(item, "quest", ("operation", "quest_id", "name", "description",
                                          "status", "progress", "objectives", "quest_kind",
                                          "target_rank", "action_evidence", "necessary_nodes",
                                          "terminal_cause"))
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
        if item["terminal_cause"] not in {"none", "refusal", "voluntary_departure",
                                          "missed_return", "objective_failure", "external_failure"}:
            raise ContractError("quest.terminal_cause无效")
        if item["status"] not in TERMINAL_QUEST_STATES and item["terminal_cause"] != "none":
            raise ContractError("非终局任务不能填写terminal_cause")
        if item["status"] in (TERMINAL_QUEST_STATES - {"completed"}) and item["terminal_cause"] == "none":
            raise ContractError("终局任务必须填写terminal_cause")
        if any(not isinstance(x, str) for x in _list(item["necessary_nodes"], "quest.necessary_nodes", 30)):
            raise ContractError("任务必要节点无效")
    for item in _list(proposals["bonds"], "bonds"):
        _proposal_reason(item, "bond", ("operation", "npc_id", "npc_ref", "npc_name", "delta",
                                         "impact", "relation_type", "admission"))
        if item["operation"] not in {"create_or_join", "adjust", "change_relation_type"}:
            raise ContractError("羁绊操作无效")
        if bool(item["npc_id"]) == bool(item["npc_ref"]):
            raise ContractError("羁绊必须且只能引用一个NPC")
        _text(item["npc_name"], "bond.npc_name", 300)
        _integer(item["delta"], "bond.delta", -35, 35)
        if item["impact"] not in {"minor", "moderate", "major", "life_defining"}:
            raise ContractError("bond.impact无效")
        _text(item["relation_type"], "bond.relation_type", 200)
        if item["operation"] == "create_or_join" and item["admission"] not in BOND_ADMISSIONS:
            raise ContractError("羁绊准入条件无效")
        if item["npc_ref"] and item["npc_ref"] not in npc_refs:
            raise ContractError("羁绊npc_ref未对应本响应新NPC")
    for item in _list(proposals["reputations"], "reputations"):
        _exact(item, {"key", "delta", "impact", "visibility", "public_reason", "evidence"},
               "reputation")
        if item["key"] not in REPUTATION_KEYS:
            raise ContractError("未知声望键")
        _integer(item["delta"], "reputation.delta", -50, 50)
        if item["impact"] not in {"minor", "moderate", "major", "world_shaping"}:
            raise ContractError("reputation.impact无效")
        if item["visibility"] not in {"public", "discovered", "propagated"}:
            raise ContractError("reputation.visibility无效")
        _text(item["public_reason"], "reputation.public_reason", 2000)
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
            if item["operation"] != "add" and item["id"] is None:
                raise ContractError(f"{group}的update或remove必须填写authoritative_state中已有的id")
    for item in _list(proposals["world_flags"], "world_flags"):
        _proposal_reason(item, "world_flag", ("key", "value"))
        _text(item["key"], "world_flag.key", 300)
        if item["key"].startswith(("canon:", "canon_exception.", "system.")):
            raise ContractError("world_flag使用了程序保留命名空间")
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
        if item["operation"] == "create":
            if item["memory_id"] is not None:
                raise ContractError("创建长期记忆时memory_id必须为null")
        elif (not isinstance(item["memory_id"], str) or not item["memory_id"].isdigit() or
              int(item["memory_id"]) < 1):
            raise ContractError("删除长期记忆时memory_id必须是有效记忆编号")
        for key in ("kind", "summary", "reason", "evidence"):
            _text(item[key], "memory." + key, 300 if key == "summary" else 4000)
        _integer(item["importance"], "memory.importance", 1, 100)
        for key in ("people", "locations", "keywords", "facts", "unresolved"):
            for entry in _list(item[key], "memory." + key, 30):
                _text(entry, "memory." + key, 4000)
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
    authorization_clause = next((clause for clause in _text_clauses(action_text)
                                 if _normalized_clause(clause).lower() ==
                                 _normalized_clause(proposal["action_evidence"]).lower()), "")
    negated_active = bool(authorization_clause) and _clause_negates_terms(
        authorization_clause, REGIONAL_NEGATED_ACTION_TERMS[quest_id])
    if target == "active" and negated_active:
        raise ContractError("玩家原始行动明确否定地区任务触发行为，不能转为active")
    if target == "active" and not _evidence_authorizes_terms(
            proposal["action_evidence"], action_text,
            REGIONAL_ACTIVE_ACTION_TERMS[quest_id] + tuple(rule["start_terms"])):
        raise ContractError("地区任务active必须引用本次玩家行动中的触发原文")
    if current["status"] in {"untriggered", "eligible"} and target in {
            "active", "offered", "declined", "failed"} and not _contains_any(evidence, rule["start_terms"]):
        raise ContractError("地区任务缺少玩家动作或触发证据")
    terminal_evidence = " ".join((action_text, current.get("progress", ""), body))
    if target in {"declined", "failed", "abandoned"}:
        if proposal["evidence"] not in body:
            raise ContractError("地区任务终局路径缺少正文证据")
        if target == "declined" and not negated_active and not _contains_any(
                terminal_evidence, ("拒绝", "不接受", "不接取", "不加入", "不参与")):
            raise ContractError("地区任务declined必须来自玩家明确拒绝")
        if proposal["terminal_cause"] == "voluntary_departure" and not _evidence_authorizes_terms(
                proposal["action_evidence"], action_text,
                ("主动离队", "提出离队", "申请离队", "告辞", "结束护卫", "离开商队")):
            raise ContractError("主动离队必须引用本次玩家行动中的离队原文")
        if proposal["terminal_cause"] == "refusal" and target != "declined":
            raise ContractError("refusal只能对应declined任务状态")
        if proposal["terminal_cause"] == "missed_return" and not _contains_any(
                " ".join((proposal["evidence"], body)), ("未按时", "错过归队", "没有归队", "未能归队")):
            raise ContractError("missed_return必须有未按时归队的正文证据")
    if target == "completed":
        if not all(term in body or term in current.get("necessary_nodes", [])
                   for term in rule["complete_nodes"]):
            raise ContractError("地区任务缺少必要完成节点")
    if quest_id == "regional_main.song_of_sandsea" and (
            target == "completed" or proposal.get("terminal_cause") == "voluntary_departure"):
        currency = (proposals or {}).get("currency", {})
        combined = " ".join((currency.get("reason", ""), currency.get("evidence", ""), body))
        if currency.get("copper_delta", 0) <= 0 or not _contains_any(
                combined, ("工资", "贡献", "路程", "护卫", "结算")):
            raise ContractError("沙海之歌完成或主动离队必须按实际贡献结算工资")
    if (quest_id == "regional_main.song_of_sandsea" and
            proposal.get("terminal_cause") == "missed_return" and
            (proposals or {}).get("currency", {}).get("copper_delta", 0) > 0):
        raise ContractError("沙海之歌未按时归队时不能结算护卫工资")
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
    for key in ("resources", "attributes", "conditions", "experience", "items", "quests", "bonds",
                "reputations", "skills", "talents", "world_flags", "power_modifiers"):
        evidence_items.extend((item, f"$.proposals.{key}[{index}].evidence")
                              for index, item in enumerate(proposals[key]))
    evidence_items.extend((item, f"$.scene.location_updates[{index}].evidence")
                          for index, item in enumerate(response["scene"]["location_updates"]))
    evidence_items.extend((item, f"$.scene.npc_updates[{index}].evidence")
                          for index, item in enumerate(response["scene"]["npc_updates"]))
    if proposals["breakthrough"]:
        evidence_items.append((proposals["breakthrough"], "$.proposals.breakthrough.evidence"))
    if proposals["currency"]["copper_delta"]:
        evidence_items.append((proposals["currency"], "$.proposals.currency.evidence"))
    if proposals.get("age"):
        evidence_items.append((proposals["age"], "$.proposals.age.evidence"))
    # A proposal that changes nothing (delta 0) needs no evidence, as the runtime policy says.
    evidence_items = [(item, path) for item, path in evidence_items
                      if not (item.get("delta") == 0 and item.get("operation") in (None, "adjust"))]
    for item, path in evidence_items:
        evidence = item.get("evidence", "")
        if evidence and evidence not in body:
            _path_error(path, "提案evidence必须逐字存在于叙事正文")
    hp_delta = sum(item["delta"] for item in proposals["resources"] if item["key"] == "hp")
    hp_after = max(0, min(state["character"]["resources"]["hp"]["max"],
                          state["character"]["resources"]["hp"]["current"] + hp_delta))
    player_dead = response["scene"]["player_life_state"] == "dead"
    if player_dead and hp_after != 0:
        raise ContractError("正文死亡叙述与HP提案不一致")
    if hp_after == 0 and not player_dead:
        raise ContractError("HP归零时player_life_state必须为dead")
    if (state["character"].get("alive") is False or
            state["character"].get("status") == "dead") and hp_after > 0:
        raise ContractError("角色死亡即本存档结局，任何手段都不能复活")


def adjudicate(state, response, canonical_locations, regional_quest_ids,
               quest_context=None, action=None, regional_definitions=None, id_factory=None,
               canonical_npcs=None):
    canonical_npcs = canonical_npcs or CANONICAL_NPCS
    generated_ids = []
    def generated_id(prefix):
        if id_factory is not None:
            value = id_factory(prefix)
            if not isinstance(value, str) or not value:
                raise ContractError("权威实体ID生成失败")
        else:
            value = prefix + "." + str(uuid.uuid4())
        generated_ids.append(value)
        return value

    def require_fresh_id(value, existing, label):
        if value in existing or generated_ids.count(value) > 1:
            raise ContractError(label + "稳定ID已存在")

    _reject_duplicate_keyed_proposals(response["proposals"])
    _validate_breakthrough_intent(response, action)
    _validate_narrative_consistency(state, response)
    result = copy.deepcopy(state)
    changes = []
    receipts = []
    reputation_audit = []
    notes = []  # program-side explanations shown with the turn's changes (e.g. capped equipment power)
    new_locations = []
    memory_operations = []
    local_locations = {}
    base_world_flags = copy.deepcopy(state.get("world_flags", {}))
    result.setdefault("npcs", {})
    local_npcs = {item["ref"]: generated_id("npc")
                  for item in response["scene"]["new_npcs"]}
    new_npcs = []
    for candidate in response["scene"]["new_npcs"]:
        if canonical_name_collision(
                candidate["name"], [{"id": key, "name": value}
                                    for key, value in canonical_npcs.items()]):
            raise ContractError("正典人物必须使用canonical_npc_catalog中的稳定ID")
        stable_id = local_npcs[candidate["ref"]]
        require_fresh_id(stable_id, result["npcs"], "NPC")
        npc = {"id": stable_id, "name": candidate["name"],
               "description": candidate["description"], "source": candidate["reason"]}
        result["npcs"][stable_id] = npc
        new_npcs.append(npc)
        receipts.append(("npc:" + stable_id, "npc", npc))
        changes.append(_change("npc", stable_id, None, npc, candidate["reason"]))
    all_locations = {**canonical_locations, **state.get("locations", {})}
    for candidate in response["scene"]["new_locations"]:
        parent_id = candidate["parent_id"] or local_locations.get(candidate["parent_ref"])
        parent = all_locations.get(parent_id)
        if not parent:
            raise ContractError("新地点父节点不存在")
        if parent.get("scope") == "place" and candidate["scope"] == "region":
            raise ContractError("地理区域不能建立在具体地点内部")
        if candidate["type"] == "city" and (
                candidate["scope"] != "place" or parent.get("scope") != "region"):
            raise ContractError("城市必须直接建立在地理区域下")
        stable_id = generated_id("dynamic")
        require_fresh_id(stable_id, all_locations, "地点")
        local_locations[candidate["ref"]] = stable_id
        region_id = stable_id if candidate["scope"] == "region" else parent["region_id"]
        jurisdiction_id = (candidate["jurisdiction_id"] if candidate["jurisdiction_id"] is not None
                           else parent.get("jurisdiction_id"))
        stored = {"id": stable_id, "name": candidate["name"], "type": candidate["type"],
                  "scope": candidate["scope"], "parent_id": parent_id, "region_id": region_id,
                  "jurisdiction_id": jurisdiction_id,
                  "description": candidate["description"], "canonical": False}
        new_locations.append(stored)
        result.setdefault("locations", {})[stable_id] = stored
        all_locations[stable_id] = stored
        receipts.append(("location:" + stable_id, "location", stored))
    for update_index, update in enumerate(response["scene"]["location_updates"]):
        if (update["location_id"] not in result.get("locations", {}) and
                update["location_id"] not in canonical_locations):
            _path_error(f"$.scene.location_updates[{update_index}].location_id", "只能更新已知地点")
        result.setdefault("location_statuses", {})[update["location_id"]] = {
            "status": update["status"], "accessible": update["accessible"],
            "description": update["description"], "reason": update["reason"]}
        changes.append(_change("location_status", update["location_id"], None,
                               update["status"], update["reason"]))
    move = response["scene"]["location"]
    if move["operation"] == "move":
        destination = move["location_id"] or local_locations.get(move["location_ref"])
        target = canonical_locations.get(destination) or result.get("locations", {}).get(destination)
        if not target:
            raise ContractError("目标地点不存在")
        if target.get("scope") != "place":
            raise ContractError("只能进入具体地点，不能进入抽象世界或地区节点")
        status_override = result.get("location_statuses", {}).get(destination, {})
        if target.get("accessible") is False or status_override.get("accessible") is False:
            raise ContractError("目标地点当前不可进入")
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
    conditions = result["character"].setdefault("conditions", {})
    for proposal in proposals["conditions"]:
        condition_id = proposal["id"] or generated_id("condition")
        existing = conditions.get(condition_id)
        if proposal["operation"] == "add":
            if existing:
                raise ContractError("持续状态已存在")
            conditions[condition_id] = {"id": condition_id, "name": proposal["name"],
                "description": proposal["description"], "temporary": proposal["temporary"],
                "expires_at": proposal["expires_at"], "source": proposal["source"]}
        elif not existing:
            raise ContractError("持续状态不存在")
        elif proposal["operation"] == "update":
            existing.update({"name": proposal["name"], "description": proposal["description"],
                             "temporary": proposal["temporary"], "expires_at": proposal["expires_at"],
                             "source": proposal["source"]})
        else:
            del conditions[condition_id]
        changes.append(_change("condition", condition_id,
                               existing if proposal["operation"] != "add" else None,
                               conditions.get(condition_id), proposal["reason"],
                               {"display_name": proposal["name"]}))
    for proposal in proposals["resources"]:
        resource = result["character"]["resources"][proposal["key"]]
        old = resource["current"]
        resource["current"] = max(0, min(resource["max"], old + proposal["delta"]))
        if resource["current"] != old:
            changes.append(_change("resource", proposal["key"], old, resource["current"], proposal["reason"]))
    result["character"]["alive"] = result["character"]["resources"]["hp"]["current"] > 0
    derived_effects = {"dead", "mana_depleted", "mental_collapse", "exhausted"}
    effects = [effect for effect in result["character"].get("status_effects", [])
               if effect not in derived_effects]
    if not result["character"]["alive"]:
        result["character"]["status"] = "dead"
        effects.append("dead")
    else:
        if result["character"].get("status") == "dead":
            result["character"]["status"] = "normal"
    zero_effects = {"mp": "mana_depleted", "sp": "mental_collapse", "st": "exhausted"}
    for key, effect in zero_effects.items():
        if result["character"]["resources"][key]["current"] == 0:
            effects.append(effect)
    result["character"]["status_effects"] = effects

    known_npcs = set(result["npcs"]) | set(canonical_npcs)
    known_locations = set(canonical_locations) | set(result.get("locations", {}))
    for update_index, update in enumerate(response["scene"]["npc_updates"]):
        if update["npc_id"] not in known_npcs:
            _path_error(f"$.scene.npc_updates[{update_index}].npc_id", "只能更新已知NPC")
        if update["location_id"] is not None and update["location_id"] not in known_locations:
            _path_error(f"$.scene.npc_updates[{update_index}].location_id", "NPC更新引用了未知地点")
        if update["npc_id"] in result["npcs"]:
            npc = result["npcs"][update["npc_id"]]
        else:
            npc = result["npcs"].setdefault(update["npc_id"], {
                "id": update["npc_id"], "name": canonical_npcs[update["npc_id"]],
                "description": "正典人物", "source": "世界人物志"})
        npc.update({"status": update["status"], "location_id": update["location_id"],
                    "availability": update["availability"], "current_goal": update["current_goal"]})
        changes.append(_change("npc_status", update["npc_id"], None, update["status"],
                               update["reason"]))

    for attribute_index, proposal in enumerate(proposals["attributes"]):
        if not proposal["long_term_basis"].strip() or len(proposal["long_term_basis"].strip()) < 4:
            _path_error(f"$.proposals.attributes[{attribute_index}].long_term_basis",
                        "长期属性变化缺少长期积累依据")
        attribute = result["character"]["attributes"][proposal["key"]]
        old = attribute["value"]
        new = old + proposal["delta"]
        if not 1 <= new <= 100:
            _path_error(f"$.proposals.attributes[{attribute_index}].delta",
                        "长期属性变化超出1至100")
        attribute["value"] = new
        if new != old:
            changes.append(_change("attribute", proposal["key"], old, new, proposal["reason"]))

    character = result["character"]
    if proposals.get("age"):
        old_age = character.get("age", character["identity"].get("age"))
        if type(old_age) is not int:
            _path_error("$.proposals.age", "角色缺少可修改的年龄")
        new_age = max(1, old_age + proposals["age"]["years_delta"])
        character["age"] = new_age
        if new_age != old_age:
            changes.append(_change("age", "age", old_age, new_age, proposals["age"]["reason"]))
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
        # 6+ ranks need a breakthrough quest. When EXP first fills up and no quest for the next rank
        # exists in any state, the program opens one as "eligible" for the GM to develop. A quest the
        # player declined or failed is not recreated: the player starts the breakthrough themselves.
        target_rank = character["rank"] + 1
        existing = next((q for q in result["quests"].values()
                         if q.get("quest_kind") == "breakthrough" and
                         q.get("target_rank") == target_rank and not q.get("consumed")), None)
        proposed = next((q for q in proposals["quests"]
                         if q["operation"] == "create" and q["quest_kind"] == "breakthrough" and
                         q["target_rank"] == target_rank), None)
        if not existing and not proposed:
            quest_id = generated_id("quest")
            quest = {"id": quest_id, "name": f"突破至{target_rank}阶",
                     "description": f"经验已满，需要完成一次突破考验才能晋升{target_rank}阶。",
                     "status": "eligible", "progress": "", "objectives": [], "regional": False,
                     "quest_kind": "breakthrough", "target_rank": target_rank, "consumed": False,
                     "necessary_nodes": [], "source": "program"}
            result["quests"][quest_id] = quest
            changes.append(_change("quest", quest_id, None, "eligible", "经验已满，开启突破任务",
                                   {"display_name": quest["name"]}))
    breakthrough = proposals["breakthrough"]
    consumed_breakthrough_task = None
    if breakthrough and breakthrough["attempted"]:
        if breakthrough["success"] and character["rank"] <= 6:
            resources = character["resources"]
            if (not character["alive"] or character["status"] != "normal" or
                    resources["hp"]["current"] <= 0 or resources["sp"]["current"] <= 0 or
                    resources["st"]["current"] <= 0):
                _path_error("$.proposals.breakthrough.success",
                            "1至6阶突破要求生命、精神、精力和角色状态正常")
            if len(breakthrough["method"].strip()) < 2 or len(breakthrough["preparation"].strip()) < 2:
                _path_error("$.proposals.breakthrough", "1至6阶突破必须说明方法和准备")
        if breakthrough["success"]:
            if not character["breakthrough_eligible"] or character["rank"] >= 10:
                _path_error("$.proposals.breakthrough.success", "角色不具备成功突破资格")
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
                    _path_error("$.proposals.breakthrough.task_completed_id",
                                "高阶突破缺少已完成突破任务")
                consumed_breakthrough_task = task_id
            old_rank = character["rank"]
            character["rank"] += 1
            character["exp"] = 0
            character["exp_to_next"] = EXP_THRESHOLDS[character["rank"]]
            character["base_power"] = POWER_BY_RANK[character["rank"]]
            character["breakthrough_eligible"] = False
            changes.append(_change("rank", "rank", old_rank, character["rank"], breakthrough["reason"]))
            # Each rank raises all four maxima by a fixed factor; current values gain the same amount.
            for key in RESOURCE_KEYS:
                resource = character["resources"][key]
                old_max = resource["max"]
                resource["max"] = max(old_max + 1, round(old_max * RANK_UP_RESOURCE_GROWTH))
                resource["current"] = min(resource["max"], resource["current"] + resource["max"] - old_max)
                changes.append(_change("resource_max", key, old_max, resource["max"], "升阶提升资源上限"))
        elif not breakthrough["failure_reason"] or not breakthrough["improvement"]:
            _path_error("$.proposals.breakthrough", "突破失败必须给出原因和改善方向")

    inventory = result["inventory"]
    for item_index, proposal in enumerate(proposals["items"]):
        operation = proposal["operation"]
        item_id = proposal["item_id"]
        if operation == "add":
            if item_id is None:
                item_id = next((key for key, value in inventory.items()
                                if value["name"] == proposal["name"] and
                                value.get("power", 0) == proposal["power"] and
                                value.get("power_class", "ordinary") == proposal["power_class"]), None)
            item_id = item_id or generated_id("item")
            if item_id in inventory:
                if inventory[item_id]["name"] != proposal["name"]:
                    _path_error(f"$.proposals.items[{item_index}].name",
                                "追加已有物品时name必须与该item_id的物品一致")
                old = inventory[item_id]["quantity"]
                inventory[item_id]["quantity"] += proposal["quantity"]
                if proposal["equipped"]:
                    inventory[item_id]["equipped"] = True
                new = inventory[item_id]["quantity"]
            else:
                old = None
                inventory[item_id] = {"id": item_id, "name": proposal["name"],
                                      "description": proposal["description"],
                                      "quantity": proposal["quantity"], "power": proposal["power"],
                                      "power_class": proposal["power_class"],
                                      "power_basis": proposal["power_basis"],
                                      "equipped": proposal["equipped"], "source": proposal["source"]}
                new = inventory[item_id]
            receipts.append(("item:" + item_id + ":" + operation, "item", inventory[item_id]))
            changes.append(_change("item", item_id, old, new, proposal["reason"],
                                   {"display_name": inventory[item_id]["name"]}))
        elif item_id not in inventory:
            _path_error(f"$.proposals.items[{item_index}].item_id", "物品不存在")
        elif operation == "remove":
            item_name = inventory[item_id]["name"]
            old = inventory[item_id]["quantity"]
            if old < proposal["quantity"]:
                _path_error(f"$.proposals.items[{item_index}].quantity", "物品数量不足")
            inventory[item_id]["quantity"] -= proposal["quantity"]
            if inventory[item_id]["quantity"] == 0:
                del inventory[item_id]
            changes.append(_change("item", item_id, old, old - proposal["quantity"], proposal["reason"],
                                   {"display_name": item_name}))
        else:
            old = inventory[item_id]["equipped"]
            inventory[item_id]["equipped"] = operation == "equip"
            changes.append(_change("item", item_id + ".equipped", old,
                                   inventory[item_id]["equipped"], proposal["reason"],
                                   {"display_name": inventory[item_id]["name"]}))
    old_currency = result["currency_copper"]
    new_currency = old_currency + proposals["currency"]["copper_delta"]
    if new_currency < 0:
        _path_error("$.proposals.currency.copper_delta", "货币余额不能为负")
    result["currency_copper"] = new_currency
    if new_currency != old_currency:
        changes.append(_change("currency", "copper", old_currency, new_currency,
                               proposals["currency"]["reason"]))
        receipts.append(("currency", "currency", {"delta": new_currency - old_currency}))

    for quest_index, proposal in enumerate(proposals["quests"]):
        quest_id = proposal["quest_id"]
        if proposal["operation"] == "create":
            quest_id = quest_id or generated_id("quest")
            if quest_id in result["quests"] or quest_id in regional_quest_ids:
                raise ContractError("任务ID已存在")
            if proposal["quest_kind"] == "regional":
                _path_error(f"$.proposals.quests[{quest_index}].quest_kind", "地区任务不能由模型创建")
            if proposal["status"] in TERMINAL_QUEST_STATES:
                raise ContractError("新任务不能直接创建为终局状态")
            if not (proposal["name"] or "").strip() or not (proposal["description"] or "").strip():
                _path_error(f"$.proposals.quests[{quest_index}]", "新建任务必须填写name和description")
            if proposal["quest_kind"] == "regular" and proposal["status"] == "active" and not (
                    _evidence_authorizes_action(proposal["action_evidence"], _player_action_text(action))):
                _path_error(f"$.proposals.quests[{quest_index}].action_evidence",
                            "普通任务直接创建为active时，action_evidence必须逐字摘取本次玩家输入中表达接受意图的短句")
            if proposal["quest_kind"] == "breakthrough":
                if (proposal["target_rank"] != character["rank"] + 1 or
                        proposal["status"] not in {"eligible", "offered", "active"}):
                    raise ContractError("突破任务target_rank必须为当前阶位+1，初始状态只能是eligible、offered或active")
            elif proposal["target_rank"] is not None:
                raise ContractError("普通任务不能设置突破目标阶位")
            result["quests"][quest_id] = {"id": quest_id, "name": proposal["name"],
                                          "description": proposal["description"],
                                          "status": proposal["status"], "progress": proposal["progress"],
                                          "objectives": proposal["objectives"], "regional": False,
                                          "quest_kind": proposal["quest_kind"],
                                          "target_rank": proposal["target_rank"], "consumed": False,
                                          "necessary_nodes": proposal["necessary_nodes"]}
            changes.append(_change("quest", quest_id, None, proposal["status"], proposal["reason"],
                                   {"display_name": proposal["name"]}))
        else:
            if quest_id in regional_quest_ids:
                current = result["regional_quests"][quest_id]
            else:
                current = result["quests"].get(quest_id)
            if not current:
                _path_error(f"$.proposals.quests[{quest_index}].quest_id", "任务不存在")
            old_status = current["status"]
            old_progress = current.get("progress", "")
            old_objectives = list(current.get("objectives", []))
            if old_status in TERMINAL_QUEST_STATES:
                raise ContractError("终局任务不能再次变化")
            if proposal["status"] != old_status and proposal["status"] not in QUEST_TRANSITIONS.get(old_status, set()):
                _path_error(f"$.proposals.quests[{quest_index}].status", "任务状态转移无效")
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
            if (quest_id not in regional_quest_ids and proposal["status"] == "active" and
                    old_status != "active" and not _evidence_authorizes_action(
                        proposal["action_evidence"], _player_action_text(action))):
                _path_error(f"$.proposals.quests[{quest_index}].action_evidence",
                            "任务转为active时，action_evidence必须逐字摘取本次玩家输入中表达接受意图的短句")
            current.update({key: proposal[key] for key in ("status", "progress", "objectives")
                            if proposal[key] is not None})
            if proposal["necessary_nodes"]:
                established_nodes = set(current.get("necessary_nodes", []))
                established_nodes.update(node for node in proposal["necessary_nodes"] if node in response["narrative"]["body"])
                current["necessary_nodes"] = sorted(established_nodes)
            status_changed = current["status"] != old_status
            progress_changed = (current.get("progress", "") != old_progress or
                                current.get("objectives", []) != old_objectives)
            if status_changed or progress_changed:
                changes.append(_change("quest", quest_id,
                                       old_status if status_changed else "progress_updated",
                                       current["status"] if status_changed else "progress_updated",
                                       proposal["reason"], {"display_name": current["name"],
                                                            "force_display": progress_changed}))
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
                                "power": 0, "power_class": "ordinary", "power_basis": "",
                                "equipped": False, "source": quest_id}
                        result["inventory"][reward["id"]] = item
                        receipts.append(("regional-reward:item:" + reward["id"], "item", item))
                        changes.append(_change("item", reward["id"], None, item, "地区任务固定奖励",
                                               {"display_name": reward["name"]}))
                    for reward in definition["rewards"]["bonds"]:
                        if reward["npc_id"] not in result["bonds"]:
                            bond = {"id": generated_id("bond"), "npc_id": reward["npc_id"],
                                    "npc_name": reward["npc_name"], "value": 21,
                                    "relation_type": reward["relation_type"], "listed": True,
                                    "level": bond_level(21)}
                            result["bonds"][reward["npc_id"]] = bond
                            receipts.append(("regional-reward:bond:" + reward["npc_id"], "bond", bond))
                            changes.append(_change("bond", reward["npc_id"], None, 21,
                                                   "地区任务固定结识关系",
                                                   {"display_name": reward["npc_name"]}))
                    for flag in definition["rewards"]["world_flags"]:
                        result["world_flags"][flag] = True
                        receipts.append(("regional-reward:flag:" + flag, "world_flag", {flag: True}))
                        changes.append(_change("world_flag", flag, None, True, "地区任务固定结果"))
    if consumed_breakthrough_task:
        result["quests"][consumed_breakthrough_task]["consumed"] = True

    for bond_index, proposal in enumerate(proposals["bonds"]):
        if proposal["npc_ref"]:
            npc_id = local_npcs[proposal["npc_ref"]]
        else:
            npc_id = proposal["npc_id"]
            if (npc_id not in result["bonds"] and npc_id not in result["npcs"] and
                    npc_id not in canonical_npcs):
                _path_error(f"$.proposals.bonds[{bond_index}].npc_id", "羁绊npc_id不是既有稳定NPC")
            if npc_id in canonical_npcs and proposal["npc_name"] != canonical_npcs[npc_id]:
                _path_error(f"$.proposals.bonds[{bond_index}].npc_name", "正典人物ID与姓名不一致")
        bond = result["bonds"].get(npc_id)
        if proposal["operation"] == "create_or_join":
            if bond:
                _path_error(f"$.proposals.bonds[{bond_index}]", "羁绊已存在")
            bond = {"id": generated_id("bond"), "npc_id": npc_id,
                    "npc_name": proposal["npc_name"], "value": 0,
                    "relation_type": proposal["relation_type"], "listed": True}
            result["bonds"][npc_id] = bond
        elif not bond:
            _path_error(f"$.proposals.bonds[{bond_index}].npc_id", "羁绊不存在")
        old = bond["value"]
        maximum_delta = BOND_IMPACT_LIMITS[proposal["impact"]]
        if abs(proposal["delta"]) > maximum_delta:
            _path_error(f"$.proposals.bonds[{bond_index}].delta",
                        f"羁绊impact={proposal['impact']}时delta绝对值最多{maximum_delta}")
        new = max(-100, min(100, old + proposal["delta"]))
        bond["value"] = new
        if proposal["operation"] == "change_relation_type":
            bond["relation_type"] = proposal["relation_type"]
        bond["level"] = bond_level(new)
        if new != old:
            changes.append(_change("bond", npc_id, old, new, proposal["reason"],
                                   {"display_name": bond["npc_name"],
                                    "old_level": bond_level(old), "new_level": bond["level"]}))
        receipts.append(("bond:" + npc_id, "bond", {"old": old, "new": new}))

    for reputation_index, proposal in enumerate(proposals["reputations"]):
        reputation = result["reputations"][proposal["key"]]
        old = reputation["value"]
        maximum_delta = REPUTATION_IMPACT_LIMITS[proposal["impact"]]
        if abs(proposal["delta"]) > maximum_delta:
            _path_error(f"$.proposals.reputations[{reputation_index}].delta",
                        f"声望impact={proposal['impact']}时delta绝对值最多{maximum_delta}")
        new = max(-100, min(100, old + proposal["delta"]))
        reputation.update({"value": new, "level": reputation_level(new)})
        if new != old:
            changes.append(_change("reputation", proposal["key"], old, new,
                                   proposal["public_reason"],
                                   {"old_level": reputation_level(old),
                                    "new_level": reputation["level"]}))
        reputation_audit.append({"key": proposal["key"], "old": old, "new": new,
                                 "public_reason": proposal["public_reason"]})
        receipts.append(("reputation:" + proposal["key"], "reputation", {"old": old, "new": new}))

    for group in ("skills", "talents"):
        collection = result["character"][group]
        for proposal in proposals[group]:
            item_id = proposal["id"] or generated_id(group[:-1])
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
            changes.append(_change(group[:-1], item_id, None, proposal["operation"], proposal["reason"],
                                   {"display_name": proposal["name"]}))
    for proposal in proposals["world_flags"]:
        old = result["world_flags"].get(proposal["key"])
        result["world_flags"][proposal["key"]] = proposal["value"]
        changes.append(_change("world_flag", proposal["key"], old, proposal["value"], proposal["reason"]))

    equipped_power = sum(item.get("power", 0) for item in inventory.values() if item.get("equipped"))
    ordinary_equipped_power = sum(item.get("power", 0) for item in inventory.values()
                                  if item.get("equipped") and
                                  item.get("power_class", "ordinary") == "ordinary")
    high_rank_equipped_power = sum(item.get("power", 0) for item in inventory.values()
                                   if item.get("equipped") and item.get("power_class") == "high_rank")
    exceptional_equipped_power = sum(item.get("power", 0) for item in inventory.values()
                                     if item.get("equipped") and item.get("power_class") == "exceptional")
    # Ordinary gear counts up to 40% of base power; anything above is simply not counted.
    ordinary_cap = int(character["base_power"] * ORDINARY_EQUIPMENT_SHARE)
    if ordinary_equipped_power > ordinary_cap:
        notes.append(f"已装备的普通装备战力合计{ordinary_equipped_power}，超过基础战力40%（{ordinary_cap}），"
                     f"超出的{ordinary_equipped_power - ordinary_cap}点不计入有效战力。")
        equipped_power -= ordinary_equipped_power - ordinary_cap
        ordinary_equipped_power = ordinary_cap
    if high_rank_equipped_power > character["base_power"]:
        raise ContractError("高阶装备的可发挥战力超过角色基础战力")
    if exceptional_equipped_power > character["base_power"] * 2:
        raise ContractError("特殊装备的可发挥战力超过角色承载上限")
    modifiers = copy.deepcopy(character.get("power_modifiers", []))
    old_effective_power = character.get("effective_power", character["base_power"])
    for modifier_index, item in enumerate(proposals["power_modifiers"]):
        existing = next((value for value in modifiers if value["id"] == item["id"]), None)
        if item["operation"] == "add":
            if existing:
                _path_error(f"$.proposals.power_modifiers[{modifier_index}].id", "战力修正已存在")
            modifiers.append({"id": item["id"], "value": item["value"], "reason": item["reason"],
                              "temporary": item["temporary"], "category": item["category"],
                              "severity": item["severity"],
                              "canonical_exception": item["canonical_exception"]})
        elif not existing:
            _path_error(f"$.proposals.power_modifiers[{modifier_index}].id", "战力修正不存在")
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
        exception_applies = canonical_power_exception_applies(
            item["canonical_exception"], exception_state, item["value"])
        if item["canonical_exception"] is not None and not exception_applies:
            index = next((offset for offset, proposed in enumerate(proposals["power_modifiers"])
                          if proposed["id"] == item["id"]), None)
            path = (f"$.proposals.power_modifiers[{index}].canonical_exception"
                    if index is not None else "$.proposals.power_modifiers")
            _path_error(path, "战力修正的正典例外无效、数值越界或不适用于当前状态")
        if item["value"] > 0 and item["severity"] in {"major", "extreme"} and not exception_applies:
            _path_error("$.proposals.power_modifiers",
                        "重大或极端战力修正的正典例外不适用于当前种族、地点、阶位或形态")
        # Only modifiers added or changed this turn are held to the caps; older ones stay as they were.
        severity_cap = int(character["base_power"] * MODIFIER_SEVERITY_SHARE[item["severity"]])
        proposed_now = any(proposed["id"] == item["id"] and proposed["operation"] in {"add", "update"}
                           for proposed in proposals["power_modifiers"])
        if proposed_now and not exception_applies and abs(item["value"]) > severity_cap:
            index = next((offset for offset, proposed in enumerate(proposals["power_modifiers"])
                          if proposed["id"] == item["id"]), None)
            _path_error(f"$.proposals.power_modifiers[{index}].value" if index is not None
                        else "$.proposals.power_modifiers",
                        f"severity={item['severity']}的战力修正绝对值最多{severity_cap}"
                        f"（基础战力的{int(MODIFIER_SEVERITY_SHARE[item['severity']] * 100)}%）")
    character["power_modifiers"] = modifiers
    character["equipment_power"] = equipped_power
    character["effective_power"] = max(0, character["base_power"] + equipped_power +
                                       sum(item["value"] for item in modifiers))
    non_exceptional = [item for item in modifiers if not canonical_power_exception_applies(
        item.get("canonical_exception"), exception_state, item.get("value", 0))]
    non_exceptional_power = character["base_power"] + ordinary_equipped_power + sum(
        item["value"] for item in non_exceptional)
    rank = character["rank"]
    next_power = POWER_BY_RANK.get(rank + 2)
    if next_power is not None and non_exceptional_power >= next_power:
        raise ContractError("普通场景战力修正不能覆盖两阶差距")
    if rank < 10 and character["effective_power"] >= POWER_BY_RANK[10]:
        raise ContractError("非十阶不能靠数值修正跨越十阶鸿沟")
    if character["effective_power"] != old_effective_power:
        changes.append(_change("power", "effective_power", old_effective_power,
                               character["effective_power"], "战力修正发生变化"))
    # Memory people/locations are only search aids: names are mapped to IDs where possible and
    # anything still unknown is dropped, rather than voiding the whole turn.
    known_canonical_npcs = dict(canonical_npcs) | {
        reward["npc_id"]: reward.get("npc_name", reward["npc_id"])
        for definition in (regional_definitions or {}).values()
        for reward in definition.get("rewards", {}).get("bonds", [])
    }
    people_by_name = {name: npc_id for npc_id, name in known_canonical_npcs.items()}
    people_by_name.update({npc.get("name"): npc_id for npc_id, npc in result["npcs"].items() if npc.get("name")})
    people_by_name.update({bond.get("npc_name"): npc_id for npc_id, bond in result["bonds"].items()
                           if bond.get("npc_name")})
    known_people = set(result["npcs"]) | set(result["bonds"]) | set(known_canonical_npcs)
    every_location = {**canonical_locations, **result.get("locations", {})}
    locations_by_name = {item.get("name"): location_id for location_id, item in every_location.items()
                         if item.get("name")}
    for memory in response["memory_candidates"]:
        rewritten = copy.deepcopy(memory)
        people = []
        for person in rewritten["people"]:
            person = local_npcs.get(person, people_by_name.get(person, person))
            if person in known_people and person not in people:
                people.append(person)
        locations = []
        for location in rewritten["locations"]:
            location = local_locations.get(location, locations_by_name.get(location, location))
            if location in every_location and location not in locations:
                locations.append(location)
        rewritten["people"], rewritten["locations"] = people, locations
        memory_operations.append(rewritten)
    result["state_version"] = state["state_version"] + 1
    return {"state": result, "changes": changes, "receipts": receipts,
            "reputation_audit": reputation_audit, "new_locations": new_locations,
            "memory_operations": memory_operations, "new_npcs": new_npcs,
            "generated_ids": generated_ids, "notes": notes}


def receipt_hash(payload):
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode("utf-8")).hexdigest()


STORY_ARC_FIELDS = {
    # story-arc/1 is still the frozen contract of older saves; its key_events are no longer kept.
    "story-arc/1": {"schema_version", "title", "summary", "key_events", "unresolved"},
    "story-arc/2": {"schema_version", "title", "summary", "unresolved"},
}


def validate_story_arc(value, contract=None):
    """Validate a story arc and return it in the story-arc/2 shape (no key_events)."""
    try:
        validate_contract(value, "story_arc", contract)
    except ValueError as exc:
        raise ContractError(str(exc)) from None
    fields = STORY_ARC_FIELDS.get(value.get("schema_version") if isinstance(value, dict) else None)
    if fields is None:
        raise ContractError("故事弧版本无效")
    _exact(value, fields, "故事弧")
    for key in ("title", "summary"):
        _text(value[key], "story_arc." + key, 20000)
    for key in fields & {"key_events", "unresolved"}:
        if any(not isinstance(item, str) for item in _list(value[key], "story_arc." + key, 100)):
            raise ContractError("故事弧数组字段无效")
    unresolved = [item.strip() for item in value["unresolved"] if item.strip()]
    return {"schema_version": "story-arc/2", "title": value["title"], "summary": value["summary"],
            "unresolved": unresolved}


# Long-term memory curation: the model reviews every active memory and names the ones to remove.
# A runtime contract, not frozen in a save's content revision, so every save can use it.
MEMORY_CURATION_CATEGORIES = ("resolved", "expired", "unimportant")
MEMORY_CURATION_CONTRACT = {
    "kind": "memory_curation", "version": "memory-curation/1",
    "text": ("只返回一个符合JSON Schema的JSON对象，不要输出解释、代码围栏或其他文字。"
             "schema_version固定为memory-curation/1。remove列出需要剔除的长期记忆，每项填写："
             "memory_number为本次long_term_memories中的编号；category为resolved（已解决）、"
             "expired（过期、被推翻或被取代）或unimportant（琐碎、重复、对后续剧情没有持续影响）；"
             "reason用一句话说明剔除依据。没有需要剔除的记忆时remove返回空数组。"),
    "schema": {
        "type": "object", "additionalProperties": False, "required": ["schema_version", "remove"],
        "properties": {
            "schema_version": {"type": "string", "const": "memory-curation/1"},
            "remove": {"type": "array", "items": {
                "type": "object", "additionalProperties": False,
                "required": ["memory_number", "category", "reason"],
                "properties": {
                    "memory_number": {"type": "integer", "minimum": 1},
                    "category": {"type": "string", "enum": list(MEMORY_CURATION_CATEGORIES)},
                    "reason": {"type": "string", "maxLength": 500},
                }}},
        },
    },
}


def validate_memory_curation(value, contract=None):
    try:
        validate_json_schema(value, (contract or MEMORY_CURATION_CONTRACT)["schema"])
    except ValueError as exc:
        raise ContractError(str(exc)) from None
    numbers = [item["memory_number"] for item in value["remove"]]
    if len(numbers) != len(set(numbers)):
        raise ContractError("同一长期记忆编号只能剔除一次")
    return {"remove": [{"memory_number": item["memory_number"], "category": item["category"],
                        "reason": item["reason"].strip()} for item in value["remove"]]}
