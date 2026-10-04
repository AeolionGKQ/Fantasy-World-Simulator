"""Canonical geography and helpers for the extensible location graph."""

try:
    from .catalog import LOCATIONS
except ImportError:
    from catalog import LOCATIONS


LOCATION_GRAPH_VERSION = "location-graph/2"
JURISDICTION_IDS = {
    "court_of_veiled_night", "skycrown_conclave", "holy_see_sacred_radiance",
    "court_of_sacred_tree", "valkeren_empire", "southern_maritime_federation",
}

REGION_NODES = (
    ("world.velseria", "维尔瑟亚世界", "world", None),
    ("region.central_plains", "中央平原", "region", "world.velseria"),
    ("region.cloud_realm", "云端天境", "region", "world.velseria"),
    ("region.elf_forest", "精灵之森地区", "region", "world.velseria"),
    ("region.veiled_night", "幽夜王庭辖域", "region", "world.velseria"),
    ("region.western_desert", "西部沙漠", "region", "world.velseria"),
    ("region.western_mountains", "西部山脉", "region", "world.velseria"),
    ("region.southern_coast", "南部沿海", "region", "world.velseria"),
    ("region.southern_ocean", "南部海洋", "region", "world.velseria"),
)

PLACE_PARENTS = {
    "san_velia": "region.central_plains", "vargard": "region.central_plains",
    "velansia": "region.cloud_realm", "elf_forest": "region.elf_forest",
    "grand_academy": "region.central_plains", "noxvia": "region.veiled_night",
    "dragonvale": "region.western_mountains", "thousand_furnace": "region.western_mountains",
    "selavia_port": "region.southern_coast",
    "abyssal_tides": "region.southern_ocean",
    "sahravia": "region.western_desert",
}

PLACE_JURISDICTIONS = {
    "san_velia": "holy_see_sacred_radiance", "vargard": "valkeren_empire",
    "velansia": "skycrown_conclave", "elf_forest": "court_of_sacred_tree",
    "noxvia": "court_of_veiled_night", "selavia_port": "southern_maritime_federation",
    "abyssal_tides": "southern_maritime_federation",
}

CANONICAL_CHILDREN = (
    ("selavia_port.adventurers_guild", "塞拉维亚港·冒险者公会", "building", "selavia_port"),
    ("velansia.central_plaza", "维兰希亚·中央广场", "plaza", "velansia"),
    ("velansia.central_plaza.celestial_balance_area", "阿尔凯昂天衡附近", "area", "velansia.central_plaza"),
    ("noxvia.street", "诺克维亚街道", "street", "noxvia"),
    ("elf_forest.main_settlement", "精灵之森主要聚居地", "settlement", "elf_forest"),
    ("elf_forest.main_settlement.street", "精灵之森主要聚居地街道", "street", "elf_forest.main_settlement"),
    ("grand_academy.central_plaza", "大联合学院中央广场", "plaza", "grand_academy"),
)


def canonical_location_map():
    result = {}
    for location_id, name, scope, parent_id in REGION_NODES:
        result[location_id] = {
            "id": location_id, "name": name, "type": scope, "scope": scope,
            "parent_id": parent_id, "region_id": location_id, "jurisdiction_id": None,
            "description": name, "canonical": True, "safeguards": [],
        }
    for item in LOCATIONS:
        parent_id = PLACE_PARENTS[item["id"]]
        result[item["id"]] = {
            "id": item["id"], "name": item["name"], "type": "city", "scope": "place",
            "parent_id": parent_id, "region_id": result[parent_id]["region_id"],
            "jurisdiction_id": PLACE_JURISDICTIONS.get(item["id"]),
            "description": item["description"], "canonical": True,
            "safeguards": list(item["safeguards"]),
        }
    for location_id, name, kind, parent_id in CANONICAL_CHILDREN:
        parent = result[parent_id]
        result[location_id] = {
            "id": location_id, "name": name, "type": kind, "scope": "place",
            "parent_id": parent_id, "region_id": parent["region_id"],
            "jurisdiction_id": parent["jurisdiction_id"],
            "description": name, "canonical": True, "safeguards": [],
        }
    return result


def location_graph_manifest():
    return [{key: value for key, value in node.items() if key != "safeguards"}
            for node in canonical_location_map().values()]


def normalize_location_node(node):
    result = dict(node)
    if "location_type" in result:
        result["type"] = result.pop("location_type")
    result.setdefault("scope", "place")
    result.setdefault("jurisdiction_id", None)
    return result


def location_catalog(location_nodes):
    values = [normalize_location_node(node) for node in (location_nodes or {}).values()]
    values.sort(key=lambda item: (item.get("scope") != "world",
                                  item.get("scope") != "region",
                                  not bool(item.get("canonical")), item.get("name", "")))
    return [{key: item.get(key) for key in (
        "id", "name", "type", "scope", "parent_id", "region_id",
        "jurisdiction_id", "description", "canonical", "status", "accessible")}
            for item in values]
