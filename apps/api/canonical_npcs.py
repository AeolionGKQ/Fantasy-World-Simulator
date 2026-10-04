"""Stable references for people defined by the frozen world canon."""

import unicodedata

CANONICAL_NPCS = {
    "canon.npc.lilia_noxveil": "莉莉娅·诺克维尔",
    "canon.npc.velessa_morvien": "维蕾莎·莫尔维恩",
    "canon.npc.alevia_veylanth": "艾蕾维娅·维兰瑟",
    "canon.npc.fileia_veyslan": "菲蕾娅·维斯兰",
    "canon.npc.ileia_veylanth": "伊蕾娅·维兰瑟",
    "canon.npc.kavien_moris": "卡维恩·莫里斯",
    "canon.npc.taren_vissar": "塔伦·维萨尔",
    "canon.npc.neria_salen": "涅瑞娅·萨蓝",
    "canon.npc.lumia_seir": "露米娅·塞伊尔",
    "canon.npc.aelsian_selvien": "艾尔希安·塞尔维恩",
    "canon.npc.itheria_aevilan": "伊瑟莉娅·艾维兰",
    "canon.npc.lysia_aevilan": "莉瑟娅·艾维兰",
    "canon.npc.selavien_loshir": "塞拉维恩·洛希尔",
    "canon.npc.filia_laisen": "菲莉娅·莱森",
    "canon.npc.durgan_blackanvil": "杜格兰·黑砧",
    "canon.npc.baren_ironridge": "巴伦·铁脊",
    "canon.npc.mireia_karn": "米蕾娅·卡恩",
    "canon.npc.savia_nash": "萨维娅·纳什",
    "canon.npc.karegus_valdran": "卡雷古斯·瓦尔德兰",
    "canon.npc.olgan_herec": "奥尔甘·赫雷克",
    "canon.npc.virna_kadra": "薇尔娜·卡德拉",
    "canon.npc.adlan_vist": "阿德兰·维斯特",
    "canon.npc.ilaine_soviel": "伊莱恩·索维尔",
    "canon.npc.selena_melvian": "塞蕾娜·梅尔维安",
    "canon.npc.reynard_horn": "雷纳德·霍尔恩",
    "canon.npc.sevier_armand": "塞维尔·阿尔芒",
    "canon.npc.kedric_volan": "凯德里克·沃兰",
    "canon.npc.loren_sevia": "洛伦·塞维亚",
    "canon.npc.nashia_safar": "娜希娅·萨法尔",
    "canon.npc.rian_havel": "莱恩·哈维尔",
    "canon.npc.celia_veyn": "塞莉娅·维恩",
    "canon.npc.funia_lex": "芙妮娅·莱克斯",
}


def canonical_npc_catalog():
    return [{"id": npc_id, "name": name} for npc_id, name in CANONICAL_NPCS.items()]


def canonical_name_key(name):
    """Normalize only for identity collision checks; never alter displayed names."""
    if not isinstance(name, str):
        return ""
    normalized = unicodedata.normalize("NFKC", name).casefold()
    return "".join(character for character in normalized if character.isalnum())


def canonical_npc_map(catalog=None):
    if catalog is None:
        return dict(CANONICAL_NPCS)
    if not isinstance(catalog, list):
        raise ValueError("canonical NPC catalog must be a list")
    result = {}
    for item in catalog:
        if (not isinstance(item, dict) or set(item) != {"id", "name"} or
                not isinstance(item["id"], str) or not item["id"].startswith("canon.npc.") or
                not isinstance(item["name"], str) or not item["name"].strip() or
                item["id"] in result):
            raise ValueError("invalid canonical NPC catalog")
        result[item["id"]] = item["name"]
    keys = [canonical_name_key(name) for name in result.values()]
    if any(not key for key in keys) or len(keys) != len(set(keys)):
        raise ValueError("canonical NPC names must be unique")
    return result


def canonical_name_collision(name, catalog=None):
    key = canonical_name_key(name)
    if not key:
        return False
    for value in canonical_npc_map(catalog).values():
        canonical_key = canonical_name_key(value)
        if key == canonical_key:
            return True
        if len(key) >= 5 and len(key) == len(canonical_key):
            if sum(left != right for left, right in zip(key, canonical_key)) <= 1:
                return True
    return False
