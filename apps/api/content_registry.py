"""Immutable source snapshots and stable prompt assembly."""

import hashlib
import json
import re
from pathlib import Path

try:
    from .canonical_npcs import canonical_npc_catalog
    from .contract_registry import contract_from_documents
    from .narrative_contract import (AGE_DELTA_LIMIT, ATTRIBUTE_DELTA_LIMIT, BOND_IMPACT_LIMITS,
                                     MEMORY_CURATION_CONTRACT, MODIFIER_SEVERITY_SHARE,
                                     ORDINARY_EQUIPMENT_SHARE, RANK_UP_RESOURCE_GROWTH,
                                     REPUTATION_IMPACT_LIMITS)
    from .location_graph import (LOCATION_GRAPH_VERSION, location_catalog,
                                 location_graph_manifest)
except ImportError:
    from canonical_npcs import canonical_npc_catalog
    from contract_registry import contract_from_documents
    from narrative_contract import (AGE_DELTA_LIMIT, ATTRIBUTE_DELTA_LIMIT, BOND_IMPACT_LIMITS,
                                    MEMORY_CURATION_CONTRACT, MODIFIER_SEVERITY_SHARE,
                                    ORDINARY_EQUIPMENT_SHARE, RANK_UP_RESOURCE_GROWTH,
                                    REPUTATION_IMPACT_LIMITS)
    from location_graph import (LOCATION_GRAPH_VERSION, location_catalog,
                                location_graph_manifest)


# The rule, canon and regional-quest documents and the GM writing guide live together in this
# folder at the project root. Their source_path stays the bare file name: it is recorded in every
# frozen content revision, and a stored revision must match what the program reads.
SOURCE_DIRECTORY = "canon"
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
        "location_graph": manifest.get("location_graph", []),
        "location_graph_version": manifest.get("location_graph_version"),
        "canonical_npcs": manifest.get("canonical_npcs", []),
    }, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    revision_id = "content-v2-" + _sha(digest_material)[:24]
    prompt_version = "gm-prompt-v2-" + _sha(
        (revision_id + ":gm-turn/2").encode("utf-8"))[:16]
    return revision_id, prompt_version


STORY_ARC_POLICY_VERSION = "story-arc-policy/1"


def story_arc_policy(action_type):
    """Runtime rules for story arc jobs. Not frozen in a save's content revision, so older saves
    (whose frozen contract is story-arc/1) follow them too."""
    rules = [
        "summary是来源内容的一段完整梗概，关键事件、转折、人物、因果与持续后果都写进summary，不再单独列出关键事件",
        "若契约中仍有key_events字段（旧版契约），一律返回[]",
        "unresolved逐条列出来源中仍未解决的事件、承诺、约定、线索、悬念与待办；每条一句话，写明涉及的人物、地点或物品，不同事项不要合并成一条",
        "来源范围内已经解决或已有明确结局的事项不得列入unresolved；没有未解决事项时返回[]",
        "只总结current_action.frozen_sources中的内容；recent_full_turns、其他story_arcs与long_term_memories仅供理解前因后果，不得写入本故事弧",
        "summary建议约800到1500字，篇幅随来源内容的分量调整",
    ]
    if action_type == "arcs_to_arc":
        rules += [
            "本次是把多个相邻故事弧合并为一个：summary把各来源故事弧的梗概按时间顺序融合为一段，不得遗漏关键事件",
            "逐条检查各来源故事弧的unresolved：结合全部来源内容判断，已被解决、已经失效或不再有意义的条目不得再返回",
            "仍然悬而未决的条目保留，可去重并改写得更准确；来源梗概中出现但尚未列出的未解决事项也要补上",
        ]
    policy = {"priority": "mandatory", "version": STORY_ARC_POLICY_VERSION, "rules": rules}
    encoded = json.dumps(policy, ensure_ascii=True, separators=(",", ":")).replace(
        "<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    return "\n<RUNTIME_STORY_ARC_POLICY_JSON>\n" + encoded + "\n</RUNTIME_STORY_ARC_POLICY_JSON>\n"


STATE_RULES_POLICY_VERSION = "state-rules/3"
MEMORY_CURATION_POLICY_VERSION = "memory-curation-policy/1"


def memory_curation_policy():
    """Rules for the player-started long-term memory curation job."""
    policy = {"priority": "mandatory", "version": MEMORY_CURATION_POLICY_VERSION, "rules": [
        "本次任务是整理长期记忆：逐条审阅long_term_memories中的全部记忆，结合story_arcs、early_summaries、recent_full_turns与authoritative_state判断哪些应当剔除，不写剧情",
        "resolved：记录的事项已经解决，承诺已兑现或已作废，冲突已结束且没有持续后果",
        "expired：信息已经过时，被后续剧情推翻或证伪，或已被另一条记忆、故事弧或权威状态完整取代；内容高度重复的多条记忆只保留信息最完整的一条，其余按expired剔除",
        "unimportant：琐碎的动作、场景细节或一次性信息，对后续剧情没有持续影响",
        "仍未解决的事项、尚未兑现的承诺、持续中的关系与冲突、对角色或世界有长期影响的发现与后果必须保留；拿不准时保留",
        "memory_number只能填写本次long_term_memories中出现的编号，每个编号最多出现一次；只能剔除，不能新建或改写记忆",
    ]}
    encoded = json.dumps(policy, ensure_ascii=True, separators=(",", ":")).replace(
        "<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    return "\n<RUNTIME_MEMORY_CURATION_POLICY_JSON>\n" + encoded + "\n</RUNTIME_MEMORY_CURATION_POLICY_JSON>\n"


def state_rules_policy(state, contract):
    """How each state proposal works, with the caps the adjudicator enforces and this character's
    current numbers. Runtime, so saves frozen on an older output contract follow it too; where a
    frozen contract says otherwise, this policy wins."""
    character = state.get("character", {})
    base_power = character.get("base_power") or 0
    inventory = state.get("inventory", {}).values()
    ordinary_cap = int(base_power * ORDINARY_EQUIPMENT_SHARE)
    ordinary_used = sum(item.get("power", 0) for item in inventory
                        if item.get("equipped") and item.get("power_class", "ordinary") == "ordinary")
    proposal_schema = contract.get("schema", {}).get("properties", {}).get("proposals", {})
    supports_age = "age" in proposal_schema.get("properties", {})
    current_age = character.get("age", character.get("identity", {}).get("age"))
    rules = [
        "本策略与冻结在存档中的输出契约原文冲突时，以本策略为准",
        "所有数值提案都是增量：delta为正表示增加或恢复，为负表示减少或消耗；结果由程序截断到允许范围",
        "短期资源resources（hp生命/mp魔力/sp精神/st精力）：current在0到max之间；HP归零即死亡，MP、SP、ST归零分别产生魔力枯竭、精神崩溃、力竭状态。"
        f"max不由模型修改：每升一阶，程序把四项max提高到原来的{RANK_UP_RESOURCE_GROWTH}倍，current同步补上增量",
        f"长期属性attributes（con体质/int智力/cha魅力）：取值1到100，单回合delta绝对值最多{ATTRIBUTE_DELTA_LIMIT}，且只有重大正向或负向事件才能接近这个上限；常规成长或损伤建议为1到3，并在long_term_basis中写明长期积累的依据",
        "天赋talents是先天或极少变化的特质，只在重大事件中获得；技能skills通过学习、训练获得或提升，可随角色成长更新。"
        "add时id填null；update或remove必须填写authoritative_state.character中已有的id。"
        "建卡时的初始天赋（id为talent.legacy）在剧情有充分依据（如诅咒、重伤、血脉觉醒）时允许修改或移除。"
        "当前天赋以talents列表为准，identity.talent只是建卡时的原始记录",
        "character.identity.additional是玩家可随时在角色面板改写或补充的角色设定，始终以当前内容为准，内容改变时以新内容取代旧印象。"
        "描写角色的背景、习惯、人际关系、偏好与言行时必须遵守；但它不是状态提案，不能据此直接增加数值、物品、货币、天赋、技能、等阶、羁绊、声望或任务，这些变化仍须在正文中发生并通过proposals提交",
        "EXP只增不减：experience.amount为非负整数，到达当前阶位阈值后不再累积。单次奖励参考当前阈值的3%到15%，重大挑战可更高；低挑战、无新颖、重复的行为单回合合计不超过10",
        "突破breakthrough：角色EXP满足阈值时breakthrough_eligible由程序计算。玩家本次输入明确表达突破意图时才可attempted=true，"
        "action_evidence逐字摘取玩家输入中表达该意图的那一小段（例如“闭关冲击六阶”），不要整段复制，也不要引用否定说法；没有意图时只描写准备或机缘。"
        "6阶及以上升阶需要完成突破任务：EXP刚满时若尚无对应任务，程序会自动创建一个状态为eligible、quest_kind=breakthrough、target_rank=当前阶位+1的突破任务，由你在剧情中展开并推进到offered或active；"
        "玩家拒绝或任务失败后程序不会重建，之后由玩家主动发起",
        "存活与死亡：scene.player_life_state必须与HP结果一致；角色死亡即本存档的结局，请写出完整的结局段落，之后玩家只能重塑最近一段剧情，任何手段都不能复活",
        f"战力：有效战力=基础战力+装备战力+战力修正，由程序计算。已装备的ordinary普通装备合计最多计入基础战力的{int(ORDINARY_EQUIPMENT_SHARE * 100)}%，超出部分不计入有效战力；"
        "high_rank与exceptional装备必须提供power_basis",
        "战力修正power_modifiers的value绝对值上限按severity计算（正典例外除外）："
        + "、".join(f"{key}为基础战力的{int(share * 100)}%" for key, share in MODIFIER_SEVERITY_SHARE.items())
        + "。伤势痊愈、离开对应环境、强化或增益结束时，必须用remove或expire移除对应的临时修正，程序不会自动过期；空数组表示既有修正保持不变",
        "背包items：add获得，remove消耗、出售、交出或遗失，equip/unequip穿脱。可堆叠物品追加时复用已有item_id（name必须一致）；新物品item_id填null。货币currency.copper_delta以铜币计，100铜=1银，100银=1金，余额不能为负",
        "任务quests：新建任务必须填写name与description，状态可为untriggered、eligible或offered；玩家本次输入明确表示接受时才能把任务创建为或转为active，"
        "action_evidence逐字摘取玩家输入中表达接受意图的那一小段（如“这个委托我接了”“我答应帮她”），不要整段复制，也不要引用否定说法；终局状态不可逆",
        "已提供（offered）但玩家尚未接取的任务，若剧情表明它已失效或过期——如截止时间已过、委托人已另找他人或不再需要、任务对象已死亡或消失、与玩家已选择的另一任务冲突而无法兼顾——"
        "就用status=failed、terminal_cause=external_failure把它结束，并在正文中交代原因。拿不准时保留；玩家只是暂未答复、或可以与其他任务并行推进的委托不要结束。地区任务仍按其专门规则处理。"
        "已结束的任务不会再出现在authoritative_state中，玩家也可能在任务栏中主动忽略任务",
        "羁绊bonds的delta绝对值上限由impact决定："
        + "、".join(f"{key}为{limit}" for key, limit in BOND_IMPACT_LIMITS.items())
        + "（可正可负）；普通互动只能用minor或moderate",
        "声望reputations的delta绝对值上限由impact决定："
        + "、".join(f"{key}为{limit}" for key, limit in REPUTATION_IMPACT_LIMITS.items())
        + "（可正可负）。continental_overall只用于跨势力、广泛传播的事件；主要发生在某一势力辖区或直接影响该势力的事件，使用对应势力的键；同一事件理由充分时可同时影响二者。visibility须为公开、被发现或已传播",
        "delta为0的提案不需要evidence；其余状态提案的evidence必须逐字存在于本次narrative.body",
    ]
    if supports_age:
        rules.append("年龄age：正常情况下只随剧情中流逝的时间增长，跨过生日或经过多年时用proposals.age提出years_delta（正数增长）；"
                     f"返老还童等特殊事件可为负数，绝对值最多{AGE_DELTA_LIMIT}，并需引用正文作为evidence；没有变化时age为null")
    else:
        rules.append("年龄：本存档的输出契约没有年龄字段，不要提交年龄变化")
    policy = {"priority": "mandatory", "version": STATE_RULES_POLICY_VERSION, "rules": rules,
              "current_numbers": {
                  "base_power": base_power,
                  "ordinary_equipment_power_cap": ordinary_cap,
                  "ordinary_equipment_power_equipped": ordinary_used,
                  "ordinary_equipment_power_remaining": max(0, ordinary_cap - ordinary_used),
                  "power_modifier_caps": {key: int(base_power * share)
                                          for key, share in MODIFIER_SEVERITY_SHARE.items()},
                  "current_age": current_age,
              }}
    encoded = json.dumps(policy, ensure_ascii=True, separators=(",", ":")).replace(
        "<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    return "\n<RUNTIME_STATE_RULES_POLICY_JSON>\n" + encoded + "\n</RUNTIME_STATE_RULES_POLICY_JSON>\n"


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
        writing_raw = (self.workspace / SOURCE_DIRECTORY / "GM写作规范.md").read_bytes()
        self._gm_writing_guidelines, _ = _decode(writing_raw)
        self._gm_writing_metadata = {
            "source_path": "GM写作规范.md", "raw_sha256": _sha(writing_raw),
            "character_count": len(self._gm_writing_guidelines),
        }
        self._documents = self._read_sources()
        quest_doc = next(item for item in self._documents
                         if item["document_id"] == "regional.source")
        self.quests = self._parse_quests(quest_doc["text_content"])
        provisional = {"documents": self._documents, "quests": [
            {"id": item["id"], "normal_context_card": item["normal_context_card"],
             "roots": list(item["roots"]), "rewards": item["rewards"]} for item in self.quests],
             "location_graph_version": LOCATION_GRAPH_VERSION,
             "canonical_npcs": canonical_npc_catalog(),
             "location_graph": location_graph_manifest()}
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
                        else self.workspace / SOURCE_DIRECTORY / relative)
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
            "location_graph_version": LOCATION_GRAPH_VERSION,
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
            "location_graph": location_graph_manifest(),
            "canonical_npcs": canonical_npc_catalog(),
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
                       revision_manifest=None, jailbreak_prompt=""):
        source_documents = list(documents or self._documents)
        frozen_manifest = revision_manifest or self.manifest
        graph_version = frozen_manifest.get("location_graph_version", LOCATION_GRAPH_VERSION)
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
        contract = (MEMORY_CURATION_CONTRACT if contract_kind == "memory_curation" else
                    contract_from_documents(contract_kind, source_documents))
        address_directive = player_address_directive(state)
        # The player's 破甲提示词 opens the system prompt exactly as typed; empty adds nothing.
        system_parts = [jailbreak_prompt] if jailbreak_prompt else []
        for item in by_category.get("protocol", [])[:2]:
            system_parts.append(self._protocol_container(item))
        if contract_kind == "story_arc":
            system_parts.append(story_arc_policy((action or {}).get("action_type")))
        if contract_kind == "memory_curation":
            system_parts.append(memory_curation_policy())
        if contract_kind == "gm_turn":
            location_policy = {
                "priority": "mandatory",
                "version": graph_version,
                "rules": [
                    "GM可在正典未定义的部分自由创建城市、村庄、街区、建筑、遗迹、海域、岛屿与其他地点",
                    "已有地点只能填入scene.location.location_id；location_ref只用于本响应new_locations中声明的location:new局部引用",
                    "stay时location_id与location_ref都必须为null；move时必须且只能填写其中一个",
                    "new_locations的parent必须且只能使用parent_id或parent_ref；parent_ref只能引用本数组中更早声明的新地点",
                    "scope=region可创建新的地理区域；scope=place表示可实际进入的地点，place必须拥有父级",
                    "新城市应挂在地理region而不是另一座城市下；南海自由联邦沿海新城可挂region.southern_coast，深海城市可挂region.southern_ocean",
                    "region_id由程序计算，不得输出；jurisdiction_id必须输出，父节点辖区适用时填相同固定键，否则可为新地点声明固定辖区键或null",
                    "同属地区或政治辖区不等于地区任务触发地点，地区任务仍只按指定地点的真实父子链匹配",
                ],
            }
            encoded_location_policy = json.dumps(
                location_policy, ensure_ascii=True, separators=(",", ":")
            ).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
            system_parts.append(
                "\n<RUNTIME_LOCATION_GRAPH_POLICY_JSON>\n" +
                encoded_location_policy +
                "\n</RUNTIME_LOCATION_GRAPH_POLICY_JSON>\n"
            )
            adjudication_policy = {
                "priority": "mandatory",
                "rules": [
                    "玩家可尝试任何行为；客观条件不足时叙述合理失败并继续故事，不要省略尝试本身",
                    "所有非零状态提案必须用evidence逐字引用正文；正文可以使用自然沉浸式措辞，不必迎合机制关键词",
                    "重塑只以reshape_guidance作为本次新授权，original_action仅是要被改写的历史上下文",
                    "普通任务可按世界进展创建为untriggered、eligible或offered；只有玩家本次输入明确表示接受时才能active，action_evidence逐字摘取玩家输入中表达接受意图的那一小段，不要整段复制",
                    "NPC死亡不等于玩家死亡；scene.player_life_state只描述玩家本人且必须与HP结果一致",
                    "普通行为只能产生minor或moderate关系影响；major、life_defining或world_shaping必须由正文中的重大长期事件支撑",
                    "既有正典人物必须使用canonical_npc_catalog稳定ID，不得伪造canon.npc前缀",
                    "authoritative_state.npcs中的既有动态NPC必须复用其稳定npc_id；scene.new_npcs只声明本响应首次创建的非正典NPC，不得重复创建既有人物",
                ],
            }
            encoded_adjudication_policy = json.dumps(
                adjudication_policy, ensure_ascii=True, separators=(",", ":")
            ).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
            system_parts.append(
                "\n<RUNTIME_ADJUDICATION_POLICY_JSON>\n" + encoded_adjudication_policy +
                "\n</RUNTIME_ADJUDICATION_POLICY_JSON>\n")
            system_parts.append(state_rules_policy(state, contract))
            memory_policy = {
                "priority": "mandatory",
                "rules": [
                    "长期记忆只保存确有跨回合价值的关键信息、线索、承诺、人物关系变化或事件结果，语言必须精炼",
                    "不要记录普通动作、场景装饰、重复信息、短期状态或可直接从权威状态读取的内容",
                    "普通询问若没有得到具体且后续仍有用的新线索，memory_candidates必须返回空数组；不要为了填字段强行创建记忆",
                    "memory evidence用于简要说明本回合记忆来源，可引用正文、概括正文信息，或引用玩家本次明确要求记住的内容；不要求逐字复制。facts与unresolved用精炼语言概括，不要求与evidence相同；输出契约原文中关于至少8个字符、完整分句或逐字相等的旧要求一律不再适用",
                    "people与locations填写canonical_npc_catalog、authoritative_state或本响应新建的NPC与地点ID；无法识别的条目会被程序忽略",
                    "keywords是程序召回记忆用的检索词，程序会拿它们与之后的剧情和玩家输入逐字比对。create时除核心名词外，同时写入涉及人物的全名、简称、称号与常用称呼，地点的全称与简称，关键物品、组织、事件的名称及其他常见说法，方便以后换一种说法提到时也能匹配；每项是至少2个字的简短词语，不写句子，一般5到15项",
                    "当一条已召回记忆已经使用完、事项已解决、信息过期、失效、被证伪或被新结论替代，使用resolve或supersede删除；supersede只删除旧记忆，要保留新结论，必须同时create一条新记忆",
                    "resolve或supersede时在memory_id填写本次long_term_memories中目标memory_number的十进制字符串，不得使用内部UUID",
                    "只能删除本次long_term_memories实际出现的编号，不得猜测未召回记忆；删除后编号由程序自动连续重排",
                ],
            }
            encoded_memory_policy = json.dumps(
                memory_policy, ensure_ascii=True, separators=(",", ":")
            ).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
            system_parts.append(
                "\n<RUNTIME_LONG_TERM_MEMORY_POLICY_JSON>\n" +
                encoded_memory_policy +
                "\n</RUNTIME_LONG_TERM_MEMORY_POLICY_JSON>\n"
            )
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
        if contract_kind == "gm_turn":
            system_parts.append("\n<GM_WRITING_GUIDELINES>\n" +
                                self._gm_writing_guidelines +
                                "\n</GM_WRITING_GUIDELINES>\n")
        system_parts.append("\n<完整规则原文>\n")
        system_parts.extend(self._document_container(item) for item in by_category.get("rule", []))
        system_parts.append("\n</完整规则原文>\n<完整世界正典>\n")
        system_parts.extend(self._document_container(item) for item in by_category.get("canon", []))
        system_parts.append("\n</完整世界正典>\n")
        system_parts.append("\n<OUTPUT_CONTRACT kind=\"" + contract_kind + "\" version=\"" +
                            contract["version"] + "\">\n" + contract["text"] + "\nJSON Schema:\n" +
                            json.dumps(contract["schema"], ensure_ascii=False, separators=(",", ":")) +
                            "\n</OUTPUT_CONTRACT>\n")
        frozen_locations = ({item["id"]: item for item in (revision_manifest or {}).get(
            "location_graph", [])} if revision_manifest else None)
        catalog_nodes = dict(location_nodes or {})
        if frozen_locations:
            catalog_nodes.update({key: {**value, "location_type": value.get("type")}
                                  for key, value in frozen_locations.items()})
        for location_id, status in state.get("location_statuses", {}).items():
            if location_id in catalog_nodes:
                catalog_nodes[location_id] = {**catalog_nodes[location_id], **status}
        # Only what the model reads or answers with; people, locations, keywords, kind and the
        # recall reason serve the program's recall scoring. The cleanup job also weighs importance.
        memory_fields = ("memory_number", "summary", "facts", "unresolved") + (
            ("importance",) if contract_kind == "memory_curation" else ())
        dynamic = {
            "active_narration": state.get("narration", {}), "regional_quests": quest_context,
            "player_address_directive": address_directive,
            "story_arcs": arcs, "early_summaries": early_summaries,
            "long_term_memories": [{key: memory.get(key) for key in memory_fields}
                                   for memory in memories],
            "recent_full_turns": recent_full_turns,
            "canonical_npc_catalog": frozen_manifest.get("canonical_npcs", []),
            "location_catalog": location_catalog(catalog_nodes),
            "authoritative_state": prompt_state, "current_action": action,
            "output_contract_reminder": {"kind": contract_kind, "version": contract["version"],
                                         "schema": contract["schema"]},
        }
        frozen = frozen_manifest
        manifest = {
            "content_revision_id": frozen["revision_id"],
            "prompt_version": frozen["prompt_version"], "contract_kind": contract_kind,
            "contract_version": contract["version"],
            "player_address_protocol_version": PLAYER_ADDRESS_PROTOCOL_VERSION,
            "location_graph_version": graph_version,
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
            "memory_numbers": [item.get("memory_number") for item in memories],
        }
        if contract_kind == "gm_turn":
            manifest["gm_writing_guidelines"] = dict(self._gm_writing_metadata)
            manifest["state_rules_policy_version"] = STATE_RULES_POLICY_VERSION
        elif contract_kind == "memory_curation":
            manifest["memory_curation_policy_version"] = MEMORY_CURATION_POLICY_VERSION
        else:
            manifest["story_arc_policy_version"] = STORY_ARC_POLICY_VERSION
        if jailbreak_prompt:
            manifest["jailbreak_prompt_characters"] = len(jailbreak_prompt)
        return ([{"role": "system", "content": "".join(system_parts)},
                 {"role": "user", "content": json.dumps(dynamic, ensure_ascii=False,
                                                           separators=(",", ":"))}],
                manifest)

    def build_image_prompt_messages(self, frozen, size):
        """Build a non-state-changing visual prompt request from frozen story context."""
        orientation = {"1536x1024": "横向画幅", "1024x1536": "竖向画幅",
                       "1024x1024": "方形画幅"}[size]
        documents = frozen["documents"]
        by_category = {}
        for item in documents:
            by_category.setdefault(item["category"], []).append(item)
        system = [
            "你负责为当前奇幻剧情场景编写一段可直接用于文生图的中文提示词。",
            "提示词正文必须全部使用简体中文，方便玩家阅读和修改；专有名词也优先使用设定中的中文名称。",
            "只返回一个JSON对象：{\"prompt\":\"...\"}。不得推进剧情、虚构行动，也不要要求图片出现文字、",
            "字幕、标志、界面元素或水印。保持角色种族、外貌、服饰、装备、地点、时间、天气、情绪和既有世界事实一致。",
            "按照", orientation, "组织构图。\n<完整规则原文>\n",
        ]
        system.extend(self._document_container(item) for item in by_category.get("rule", []))
        system.append("\n</完整规则原文>\n<完整世界正典>\n")
        system.extend(self._document_container(item) for item in by_category.get("canon", []))
        system.append("\n</完整世界正典>\n")
        payload = {key: frozen[key] for key in (
            "state", "turn", "early_summaries", "recent_full_turns", "memories", "arcs")}
        payload["requested_composition"] = orientation
        return [{"role": "system", "content": "".join(system)},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False,
                                                         separators=(",", ":"))}]


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
