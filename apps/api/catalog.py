"""Versioned, read-only data used by the character creator."""

RULESET_VERSION = "world-rules/1"

POWER_BY_RANK = {1: 100, 2: 180, 3: 320, 4: 560, 5: 1000,
                 6: 1800, 7: 4000, 8: 9000, 9: 20000, 10: 100000}
EXP_THRESHOLDS = {0: 80, 1: 100, 2: 140, 3: 200, 4: 300,
                  5: 450, 6: 650, 7: 900, 8: 1300, 9: 2000, 10: None}

_GENERIC_TITLES = ["初阶者", "熟练者", "精锐者", "卓越者", "大师", "宗师",
                   "冠位", "尊位", "传奇", "至境"]
_CHINESE_RANKS = ["一", "二", "三", "四", "五", "六", "七", "八", "九", "十"]
_TITLES = {
    "human": _GENERIC_TITLES,
    "featherfolk": ["启翼", "驭风", "翔士", "凌空", "御风", "天巡", "云冠", "天翼", "穹翼", "天穹"],
    "sea_folk": ["潮启", "驭流", "逐浪", "御潮", "深澜", "海巡", "潮冠", "渊潮", "沧溟", "瀚海"],
    "therian": [None] * 10,
    "elf": ["芽生", "青枝", "林语", "森行", "翠冠", "古木", "圣枝", "森冠", "永青", "始源"],
    "dragonkin": ["初鳞", "炽血", "振翼", "龙牙", "龙威", "天吼", "苍翼", "古龙", "龙尊", "天龙"],
    "dwarf": [None] * 10,
    "demonkin": ["启念", "识影", "幽行", "心刃", "灵契", "魂域", "夜冠", "幽冕", "灵渊", "心界"],
}


def _rank_rows(titles, theoretical_below=1):
    rows = []
    for rank in range(1, 11):
        warning = None
        if rank < theoretical_below:
            warning = "精灵出生即具备三阶魔力基础；一阶与二阶仅作理论分类，选择时请在角色设定中解释其战斗能力尚未完整发挥。"
        elif rank >= 7:
            warning = "七阶及以上属于稀少高阶强者；推荐选择六阶及以下。"
        rows.append({"rank": rank, "display_rank": f"{_CHINESE_RANKS[rank - 1]}阶",
                     "name": f"{_CHINESE_RANKS[rank - 1]}阶", "title": titles[rank - 1],
                     "base_power": POWER_BY_RANK[rank], "disabled": False,
                     "warning": warning})
    return rows


_THERIAN_BRANCHES = [
    {
        "id": "orc",
        "name": "兽人",
        "tagline": "依靠本能身体强化的近战与生存者",
        "description": "兽人外形明显偏向兽类，常有大面积毛发、兽类面部、爪牙和发达肌肉，并继承原型动物的强化感官。他们以本能将魔力融入身体，形成与半兽人完全不同的发展道路。",
        "lifespan_text": "平均约60岁；高阶个体可略有延长",
        "distribution": "多生活于森林、荒野、山地与草原，以群落或部族组织生存。",
        "magic_affinity": "通常不系统学习法术，而将魔力本能地融入肌肉、骨骼、皮肤与感官。魔力控制偏弱，高阶成长困难。",
        "combat_style": "擅长肉体强化、冲撞、撕咬、爪牙和重型近战武器，正面近战与野外生存能力突出。",
        "technology": "几乎没有独立魔导技术体系，对复杂设备掌握较弱，多使用简单武器或其他种族的基础装备。",
        "society": "部族社会重视力量、生存、狩猎与族群安全，没有正式的十阶称号体系。",
        "creation_notes": "适合创建近战或生存型角色。约80%能入一阶，但多数长期停留在一阶，二阶已较困难，更高阶极为罕见。",
        "facts": [
            {"label": "超凡比例", "value": "约80%可入一阶"},
            {"label": "常见水平", "value": "多数长期停留一阶"},
            {"label": "身体特征", "value": "强壮、兽化程度高"},
            {"label": "阶位称号", "value": "无族内正式称号"},
        ],
        "ranks": _rank_rows([None] * 10),
    },
    {
        "id": "half_orc",
        "name": "半兽人",
        "tagline": "兼具动物原型特长与现代职业适应力",
        "description": "半兽人整体接近人形，通常仅保留兽耳、尾巴、特殊瞳孔、犬齿、爪或局部毛发。他们会继承原型动物的嗅觉、听觉、夜视、平衡或爆发力等少量特长。",
        "lifespan_text": "平均约100岁；高阶强者可进一步延长",
        "distribution": "分散生活于各族城市、港口、城镇和边境聚落，很少拥有大型独立聚居区。",
        "magic_affinity": "能够正常学习魔法、战技、魔导技术与各类超凡职业，整体泛用性仅次于人类。",
        "combat_style": "身体素质平均略高于人类，可按动物原型与个人训练走近战、施法、技术或混合路线。",
        "technology": "能正常操作现代魔导设备，多沿用人类或其他种族的技术标准，未形成统一的独立技术路线。",
        "society": "因缺乏统一政治力量且常被与野性兽人混同，整体社会地位偏低，但高阶强者、学者、军官和魔导师同样存在。",
        "creation_notes": "适合希望保留广泛职业选择、同时拥有动物原型特长的角色。约40%可入一阶，现存七至八阶强者数量较少。",
        "facts": [
            {"label": "超凡比例", "value": "约40%可入一阶"},
            {"label": "身体特征", "value": "近人形、少量兽征"},
            {"label": "职业路线", "value": "泛用性仅次于人类"},
            {"label": "阶位称号", "value": "沿用人类通行称号"},
        ],
        "ranks": _rank_rows(_GENERIC_TITLES),
    },
]


RACES = [
    {
        "id": "human",
        "name": "人类",
        "tagline": "适应、整合与自由发展的泛用型种族",
        "description": "人类是维尔瑟亚人口最多、分布最广的智慧种族，政治实体与文化差异也最丰富。人类缺少极端的单项先天优势，但以适应性、创造力和跨体系整合能力弥补。",
        "lifespan_text": "普通人平均约80岁；九至十阶可活数百年",
        "distribution": "遍布大陆各地，国家、地区与社会背景选择最广，没有统一的人类文化。",
        "magic_affinity": "对几乎所有已知魔法都有一定亲和，特点是广泛而非极端，适合跨流派学习、研究和组合。",
        "combat_style": "没有固定种族战法，可适应战士、法师、魔导师和多种混合职业；实际表现主要取决于训练与资源。",
        "technology": "综合魔导技术体系最完整，擅长模块化、标准化、工业化，以及将异族知识与蒸汽技术整合为可规模应用的系统。",
        "society": "主流社会性别地位总体平等，但贫富差距会显著影响超凡教育、装备、医疗与导师资源。",
        "creation_notes": "发展路线最自由，适合任何主要职业与多数地区背景；相对弱点是缺少其他种族的极端先天天赋。",
        "facts": [
            {"label": "超凡比例", "value": "约30%可踏入一阶"},
            {"label": "魔力倾向", "value": "泛魔力亲和"},
            {"label": "人口分布", "value": "人口最多、分布最广"},
            {"label": "高阶寿命", "value": "九至十阶可达数百年"},
        ],
        "ranks": _rank_rows(_TITLES["human"]),
    },
    {
        "id": "featherfolk",
        "name": "羽族",
        "tagline": "以天空为日常环境的高机动全民超凡种族",
        "description": "羽族是聚居云端天境的少数高空智慧种族，背生大型羽翼，成年翼展通常约3米。飞行不是额外技能，而是其生活、战斗与文明基础。",
        "lifespan_text": "普通羽族约150至200岁；高阶者更长寿",
        "distribution": "人口稀少且主要集中于云端天境；少数成员在大陆从事高空工程、运输、护航、狩猎与紧急传讯。",
        "magic_affinity": "风属性亲和显著，擅长气流控制、飞行强化、风压攻击与高空环境适应。羽毛可以承载魔力并自然再生。",
        "combat_style": "依靠高速空中机动和远程飞羽攻击；训练可强化羽毛的速度、硬度、穿透与轨迹，但短时过度消耗会影响飞行。",
        "technology": "在浮空岛稳定、空艇核心、云端列车、浮空港与高空气流工程领域处于领先地位。",
        "society": "社会稳定平和，基础教育、医疗、飞行训练与魔力训练免费开放，基础成长资源较少因贫富被完全剥夺。",
        "creation_notes": "适合空中机动、风系施法、飞羽远攻或高空工程路线。文化与主要社会网络集中于云端天境。",
        "facts": [
            {"label": "超凡比例", "value": "健康成年几乎100%至少一阶"},
            {"label": "常见水平", "value": "多数成年约三阶"},
            {"label": "成年翼展", "value": "通常约3米"},
            {"label": "核心领域", "value": "飞行、风系与浮空工程"},
        ],
        "ranks": _rank_rows(_TITLES["featherfolk"]),
    },
    {
        "id": "sea_folk",
        "name": "海族",
        "tagline": "在大型水域获得显著增幅的环境专精种族",
        "description": "海族主要生活于南部海洋与沿海。陆地形态近似人类并有鱼鳍状耳朵，入水后双腿会化为鱼尾，依靠身体、魔力推进与水流控制高速游动。",
        "lifespan_text": "普通海族平均约100至150岁；高阶者更长寿",
        "distribution": "绝大多数终生生活在南部海域；长期上岸者多在沿海城市从事引航、护航、海魔物狩猎、船舶工程与资源贸易。",
        "magic_affinity": "水属性亲和极高，擅长水流、高压水击、水体塑形、水幕、水下感知与水压适应；其他属性平均亲和较低。",
        "combat_style": "在海洋等大型自然水体中可直接借环境施法并获得明显增幅，擅长水下高速机动、海战和持续作战；离水后优势收窄。",
        "technology": "拥有领先的水体控制、远洋航行、船舶推进、深海压力防护、水下城市与海洋资源采集技术。",
        "society": "海洋资源充足，教育、医疗和基础公共服务免费；内部多采用分享、公共分配、赠予和以物易物，货币主要用于陆海贸易。",
        "creation_notes": "约60%可入一阶。只有一阶及以上才能稳定将鱼尾化为双腿，因此长期在陆地活动的海族角色至少是一阶。",
        "facts": [
            {"label": "超凡比例", "value": "约60%可踏入一阶"},
            {"label": "陆地形态", "value": "一阶后可稳定维持双腿"},
            {"label": "环境优势", "value": "大型自然水域显著增幅"},
            {"label": "顶级战力", "value": "无十阶，现有三名九阶"},
        ],
        "ranks": _rank_rows(_TITLES["sea_folk"]),
    },
    {
        "id": "therian",
        "name": "兽裔",
        "tagline": "共享兽类特征、却走上两条独立道路的族群",
        "description": "兽裔是人口仅次于人类的智慧种族统称，包含兽人和半兽人两个独立分支。两者并非混血关系，也不是同一种族的不同血统，只因都具有鲜明兽类特征而被共同归类。",
        "lifespan_text": "依分支而异：兽人约60岁，半兽人约100岁",
        "distribution": "广布全大陆。兽人多居野外部族，半兽人则分散融入城市、港口、城镇与边境聚落。",
        "magic_affinity": "兽人偏向本能身体强化且控制较弱；半兽人可正常学习魔法、战技与魔导技术。",
        "combat_style": "兽人专长身体强化、近战与生存；半兽人依动物原型特长发展，职业适应面更广。",
        "technology": "兽人缺乏独立魔导体系；半兽人能使用现代技术，但多采用其他种族的通行标准。",
        "society": "兽人以野外群落或部族为主；半兽人缺少统一政权与大型聚居区，整体社会地位偏低。",
        "creation_notes": "必须先选择兽人或半兽人。分支会改变寿命、超凡比例、职业方向与阶位称号，应按角色想走的道路决定。",
        "facts": [
            {"label": "人口规模", "value": "总量仅次于人类"},
            {"label": "分支关系", "value": "两个独立种族，并非混血"},
            {"label": "兽人入阶", "value": "约80%"},
            {"label": "半兽人入阶", "value": "约40%"},
        ],
        "branches": _THERIAN_BRANCHES,
        "ranks": _rank_rows(_TITLES["therian"]),
    },
    {
        "id": "elf",
        "name": "精灵",
        "tagline": "由古圣树孕育的高起点长寿施法种族",
        "description": "精灵是人口最少的主要智慧种族，几乎都居住在精灵之森。所有精灵由古圣树孕育，再由伴侣领养成家；极低的孕育速度使其人口长期稀少。",
        "lifespan_text": "普通精灵平均超过600岁；现存十阶均逾千岁",
        "distribution": "高度集中于精灵之森，社会封闭且对外交流有限；长期在外生活者多为使者、学者、任务执行者或少数冒险家。",
        "magic_affinity": "木属性亲和极高，擅长植物、根系、生命力、生态修复与环境控制；对其他多数属性也有较高亲和。",
        "combat_style": "以法杖、长弓和中远程施法为主，兼具元素攻击、魔力箭、治疗与辅助；森林环境可进一步放大优势。",
        "technology": "生命、医疗、农业、生态与环境魔导技术领先，可进行土壤改良、环境净化、天气调节和大型气候控制。",
        "society": "精灵之森高度自给自足，内部以共享、赠予和以物易物为主，货币几乎没有实际意义。家庭关系建立于领养、伴侣与情感而非血缘。",
        "creation_notes": "所有精灵出生即有三阶基础，但幼年仍需成长训练才能完整发挥，整体起点高、成长慢。一至二阶仅作理论分类。",
        "facts": [
            {"label": "出生基础", "value": "至少三阶魔力水平"},
            {"label": "成长节奏", "value": "起点极高、成长较慢"},
            {"label": "诞生方式", "value": "由古圣树孕育"},
            {"label": "人口规模", "value": "主要智慧种族中最少"},
        ],
        "ranks": _rank_rows(_TITLES["elf"], theoretical_below=3),
    },
    {
        "id": "dragonkin",
        "name": "龙族",
        "tagline": "以强大肉体与龙语魔法正面突破的全民超凡种族",
        "description": "龙族生来多以巨龙形态成长，完成化形后称为龙裔，可在人形与巨龙形态间切换。巨龙形态更强壮并适合大型龙语魔法，龙裔形态则利于精细战斗与社会活动。",
        "lifespan_text": "普通龙族平均超过500岁；高阶古龙可逾千岁",
        "distribution": "主要栖息龙谷和大陆各地大型山脉；化形龙裔也会进入各族社会。龙族个人主义强，较少形成庞大统一组织。",
        "magic_affinity": "独有龙语魔法，以身体、血脉、精神和声音引发共振，擅长龙息、火焰、爆炸、冲击、强化与威压，不长于精细治疗和复杂幻术。",
        "combat_style": "同阶正面近战、防御、耐力与持续作战优势明显，兼具飞行和大范围高破坏施法，偏好直接击破。",
        "technology": "专长魔导炮、高能武器、战舰主炮、聚焦系统、重型防御和高阶强者专用战斗设备。",
        "society": "人口较少，性格整体豪爽直接、好战，崇尚力量；成年龙裔常任将领、护卫、佣兵、冒险者、猎人与武器工程师。",
        "creation_notes": "全民超凡，成年平均四至五阶，前中期成长快但高阶后明显放缓。适合高基础战力、飞行、双形态与正面突破路线。",
        "facts": [
            {"label": "超凡比例", "value": "正常个体100%可入一阶"},
            {"label": "成年水平", "value": "平均四至五阶"},
            {"label": "成熟形态", "value": "巨龙与龙裔自由切换"},
            {"label": "核心优势", "value": "肉体、飞行与龙语魔法"},
        ],
        "ranks": _rank_rows(_TITLES["dragonkin"]),
    },
    {
        "id": "dwarf",
        "name": "矮人",
        "tagline": "将复杂设计铸成可靠实体的工匠与工程专家",
        "description": "矮人是人口总量第三的主要智慧种族，身材矮壮、骨骼与肌肉结实。直接战斗天赋一般，但在采矿、冶金、锻造、魔法回路和大型魔导工程方面极为突出。",
        "lifespan_text": "普通矮人平均约200岁；超凡提升可延寿",
        "distribution": "广泛融入大陆各国城市、矿区、工业区与工程组织，并不存在高度封闭的单一种族社会。",
        "magic_affinity": "魔法战斗并非核心优势，天赋主要体现为矿物鉴定、材料处理、魔晶加工、魔法回路与魔导核心制造。",
        "combat_style": "可拥有一至十阶战斗能力，但通常依靠重甲、战锤、魔导枪械、护盾和自制工程装置。",
        "technology": "擅长将设计制造为稳定耐用的设备，参与高级武器、建筑、魔导核心和文明级系统的施工与维护。",
        "society": "重视技艺、师承、契约、材料品质、工程可靠性与劳动价值，认为材料、时间和手艺都应获得合理报酬。",
        "creation_notes": "角色创建中的阶位表示战斗能力。矮人认可的工匠阶独立于战斗阶，从初炉到天工，两者没有直接换算关系。",
        "facts": [
            {"label": "人口规模", "value": "主要智慧种族中第三"},
            {"label": "核心专长", "value": "锻造、回路与大型工程"},
            {"label": "战斗称号", "value": "族内不设特殊称号"},
            {"label": "工匠阶", "value": "独立于战斗阶"},
        ],
        "ranks": _rank_rows(_TITLES["dwarf"]),
    },
    {
        "id": "demonkin",
        "name": "魔族",
        "tagline": "专精暗属性、意识与灵魂领域的控制型种族",
        "description": "魔族是维尔瑟亚原生智慧种族，通常具有恶魔角与细长尾巴，并非来自魔界或深渊，也不天然邪恶。不同分支会在角、尾、瞳色、魔法与战法上有所差异。",
        "lifespan_text": "普通魔族平均约100至150岁；高阶者更长寿",
        "distribution": "拥有主要聚居区域，也广泛生活在其他种族的城市中；社会形态近似人类，具备完整的家庭、教育、行政与职业体系。",
        "magic_affinity": "暗属性亲和较高，尤其擅长精神感知、意识干扰、精神防护、灵魂感知、保护、治疗与封存；无法恢复已彻底消散的灵魂。",
        "combat_style": "偏向精神冲击、暗属性攻击、感官干扰、灵魂震荡、屏障和战场控制，常任法师、辅助施术者与精神治疗师。",
        "technology": "精神与灵魂类魔导技术领先，包括稳定、增幅、屏障、意识监测、灵魂损伤诊断、治疗与高阶储存设备。",
        "society": "人口较多，职业路线多样，能正常融入大陆社会；暗属性和灵魂研究不等同于邪恶或蔑视生命。",
        "creation_notes": "约50%可入一阶。适合控制、削弱、暗系施法、精神防护或灵魂医疗路线，正面爆发与身体能力并非核心强项。",
        "facts": [
            {"label": "超凡比例", "value": "约50%可踏入一阶"},
            {"label": "种族来源", "value": "主世界原生智慧种族"},
            {"label": "专精领域", "value": "暗属性、精神与灵魂"},
            {"label": "战斗倾向", "value": "控制、削弱与防护"},
        ],
        "ranks": _rank_rows(_TITLES["demonkin"]),
    },
]

for race in RACES:
    race_id = race["id"]
    race["summary"] = race["tagline"]
    race["image_landscape_path"] = f"/assets/world/races/{race_id}-landscape.webp"
    race["image_portrait_path"] = f"/assets/world/races/{race_id}-portrait.webp"

LOCATIONS = [
    {
        "id": "san_velia", "name": "圣维利亚", "tagline": "依山而建、由圣辉大圣堂俯瞰的秩序之城",
        "description": "圣辉教廷首都，通称圣城。白色与浅色石材、严格统一的街道和建筑规范构成庄严肃穆的城市景观；大圣堂的钟声也是居民日常生活的时间标记。",
        "region": "中央平原东部·圣辉教廷", "environment": "管理严格、治安良好的阶梯式山城，各种族可合法进入。",
        "structure": "城市由低至高分为外部交通与商业区、居民区、教廷行政区、大圣堂与核心宗教区，以石阶、坡道和广场连接。",
        "highlights": ["圣辉大圣堂与每日钟声", "高度统一的白色城市景观", "教廷政治、宗教与医疗资源集中"],
        "transport": "可从外部交通区进入；城内主要沿阶梯、坡道和广场在不同高度间通行。",
        "access_note": "外来者须遵守公共秩序与城市法规；魔族可以合法进入，但可能受到额外检查与民间关注。",
        "arrival_point": "具体落脚点将在游戏开场时确定，不预设为教廷核心区。",
        "safeguards": ["无已知特殊生存装备前置", "进入宗教或行政核心区域仍须遵守当地许可与秩序"],
    },
    {
        "id": "vargard", "name": "瓦尔加德", "tagline": "武器、契约与军工塑造的帝国首都",
        "description": "瓦尔凯伦帝国首都，以赤铁皇宫为中心向外扩展。黑、深灰与暗红色的厚重建筑之间，军人、佣兵、冒险者、工匠和武器商人构成城市最鲜明的日常。",
        "region": "中央平原西部·瓦尔凯伦帝国", "environment": "宽阔街道与坚固建筑组成的大型军事和兵装都市。",
        "structure": "赤铁皇宫是最高行政与军事决策中心；外围分布兵装商业区、锻造与军工设施，以及适应龙族本体需求的大型服务场所。",
        "highlights": ["赤铁皇宫", "大陆重要军用装备交易与生产中心", "常见龙族军官、佣兵与工程师", "少见的龙族本体护理产业"],
        "transport": "位于中央平原通往西部山脉与荒原的方向，是帝国人员、商队与军用物资的重要集散地。",
        "access_note": "城市公开区域可供旅人活动；军事设施、皇宫及授权事务并非自由开放。",
        "arrival_point": "具体落脚点将在游戏开场时确定，不预设进入皇宫或军事禁区。",
        "safeguards": ["无已知特殊生存装备前置", "需遵守帝国城市与军事区域秩序"],
    },
    {
        "id": "velansia", "name": "维兰希亚", "tagline": "悬于云海之上、守望阿尔凯昂天衡的羽族首都",
        "description": "维兰希亚坐落于云端天境最大的天冠岛，是羽族政治、文化与居住核心，也是天穹议庭所在地。中央广场保存着维持整个浮空群岛系统的十阶古代设施阿尔凯昂天衡。",
        "region": "云端天境·天冠岛", "environment": "高空浮岛城市，长期受浮空系统与高空气流环境影响。",
        "structure": "城市由羽族皇宫、议庭议政厅、居民区、商业区和中央广场组成；天冠岛旁的天穹港承担主要对外交通。",
        "highlights": ["中央广场的阿尔凯昂天衡", "天穹议庭与羽族皇宫", "现代天穹港与古代浮空系统并立"],
        "transport": "多数外族旅客经天穹港搭乘空艇或云端列车抵达；羽族也可直接飞行往来浮空岛。",
        "access_note": "外族可进入开放区域；高空专业区域、议庭内部与古代设施维护区需要相应许可。",
        "arrival_point": "具体落脚点将在游戏开场时确定；外族通常应从公开航运可达区域展开。",
        "safeguards": ["非飞行种族需依靠可用的空中交通与开放通行区域", "不得将可进入开放区理解为获准进入议庭或设施核心"],
    },
    {
        "id": "elf_forest", "name": "精灵之森", "tagline": "古圣树孕育精灵、自然与文明彼此依存的森林核心",
        "description": "精灵之森位于翠幕雨林深处，经过精灵长期生态调节后比外围雨林更稳定。森林最深处的古圣树是精灵族起源与文明核心，周围分布圣树圣殿、王庭和核心聚居地。",
        "region": "大陆东部·翠幕雨林深处", "environment": "森林内部生态稳定，但外围雨林高温潮湿、地形复杂，存在毒物、拟态生物与迷路风险。",
        "structure": "越接近古圣树、圣树圣殿和核心聚居区，进入限制越严格；外围与获准开放区域承担有限对外交流。",
        "highlights": ["孕育所有精灵的古圣树", "圣树圣殿与圣树王庭", "依附根系、溪流和原有森林建造的聚居区"],
        "transport": "可徒步穿越翠幕雨林，或搭乘天穹航运联合会获王庭许可的专属线路进入开放区域。",
        "access_note": "外族必须获得精灵方面许可；专属航线乘客也须提前通过审核，不能自由进入核心区域。",
        "arrival_point": "具体落脚点将在游戏开场时依角色身份与许可确定，不默认置于古圣树或王庭核心区。",
        "safeguards": ["外族角色必须具备进入许可或符合已审核航线条件", "徒步路线需要应对外围雨林环境，不能假定自动获得精灵向导"],
    },
    {
        "id": "grand_academy", "name": "维尔瑟亚大联合学院", "tagline": "三大学院环绕中央广场的跨种族学术之城",
        "description": "大陆规模最大的建筑群与学术中心之一。战士、法师与魔导学院各自接近大型城市规模，从三个方向环绕中央广场；万象研究院则位于广场低空的人工浮空岛。",
        "region": "大陆中央·教廷与帝国之间", "environment": "永久中立、面向所有智慧种族的教学、研究与交流区域。",
        "structure": "战士学院以演武与实战设施为核心，法师学院拥有八座属性法师塔，魔导学院遍布实验和工程设施；万象中枢覆盖三大片区。",
        "highlights": ["战士、法师与魔导三大学院", "浮空岛上的万象研究院", "现代十阶综合魔导系统万象中枢", "记录文明贡献者的先贤大道"],
        "transport": "外部交通枢纽经先贤大道连接中央区域；学院内部各片区拥有完整公共与魔导设施。",
        "access_note": "进入学院开放区域不等于取得学籍；入学候选者必须通过资质试炼与心性试炼，且没有年龄限制。",
        "arrival_point": "具体落脚点将在游戏开场时确定，不默认角色已入学或进入万象研究院。",
        "safeguards": ["正式入学必须通过资质试炼与心性试炼", "研究设施、法师塔和万象中枢节点按学院权限开放"],
    },
    {
        "id": "noxvia", "name": "诺克维亚", "tagline": "以地热抵御北境寒意、由静魂之环温养精神的魔族首都",
        "description": "诺克维亚位于北境雪原与温带交界，背靠北方雪山。黑灰砖石令城市外观沉静冷峻，商业与公共设施却十分完善；地下十阶遗产静魂之环持续温养范围内生命的精神与灵魂。",
        "region": "大陆北部·雪原与温带交界", "environment": "外部气候寒冷，城市依靠天然地热建设温泉和供暖系统，整体宜居度较高。",
        "structure": "市中心是魔王城与幽夜王庭核心机构；静魂之环埋藏于地下并覆盖整座首都，高规格精神与灵魂医疗设施集中于城中。",
        "highlights": ["覆盖全城的阿尔凯昂静魂阵列", "大陆顶尖的精神与灵魂医疗", "天然地热、温泉与城市供暖", "魔王城与幽夜王庭"],
        "transport": "位于北境文明区域通往雪原和苍穹山脉的方向，可作为继续北行前的城市据点。",
        "access_note": "公开城区可正常活动；王庭和地下古代设施核心不因选择此地而自动开放。",
        "arrival_point": "具体落脚点将在游戏开场时确定，不预设进入静魂之环核心或王庭内部。",
        "safeguards": ["前往城外北境需准备防寒条件", "静魂之环可缓慢温养现存精神与灵魂损伤，但不能恢复已彻底消散的灵魂"],
    },
    {
        "id": "dragonvale", "name": "熔脊龙谷", "tagline": "火山、幼龙与高温锻炉共存的龙族祖地",
        "description": "熔脊龙谷位于西部山脉深处，是龙族最重要的祖地、育幼区和传统集会地点。尚未化形的幼龙、年长龙族与利用地热矿产的矮人工匠共同生活于此。",
        "region": "大陆西部山脉深处", "environment": "临近火山与地下岩浆带，常年高温；巨石、火山岩和耐热金属构成适合巨龙通行的巨大建筑与道路。",
        "structure": "谷内包含幼龙成长区域、龙族与矮人聚居和锻造区域，以及龙谷议盟的传统集会地点；地下是否存在古代设施尚无确证。",
        "highlights": ["龙族祖地与幼龙成长地", "高温锻造和特殊合金产业", "平等自愿的幼龙伙伴契约", "龙皇召集龙族议事的传统地点"],
        "transport": "位于西部山脉深处，需经山地路线抵达；谷内道路与广场主要按巨龙尺度建设。",
        "access_note": "非龙族、非矮人长期活动通常需要隔热与环境防护魔导器；伙伴契约必须双方自愿且地位平等。",
        "arrival_point": "具体落脚点将在游戏开场时确定，不默认进入幼龙区、议盟集会或地下未知区域。",
        "safeguards": ["非龙族、非矮人角色需具备隔热与环境防护条件", "不能假定自动获得防护魔导器或幼龙伙伴"],
    },
    {
        "id": "thousand_furnace", "name": "万炉矿渊", "tagline": "由数百年开采与工程塑成的阶梯巨坑和地下炉城",
        "description": "万炉矿渊是西部山脉已探明矿产最富集的区域之一，也是完全由现代文明创造的人造奇观。地表巨坑、地下矿道和正下方的炉心城组成完整的采矿、冶炼与制造体系。",
        "region": "大陆西部山脉", "environment": "大型露天阶梯矿坑与地下洞穴并存，包含作业矿区、废弃矿井和仍未探索的深层区域。",
        "structure": "平台、升降设施和运输轨道沿坑壁深入地下；炉心城是行政、工程、锻造与生活中心，也是大工程联合会总部所在地。",
        "highlights": ["近似大型城市规模的阶梯巨坑", "地下炉心城与联合会总部", "从开采到加工的完整工业链", "魔力晶体与稀有导魔材料矿脉"],
        "transport": "设有大型空艇货运港、云端列车货运站，以及覆盖矿坑内部的魔导运输设施。",
        "access_note": "公共城区与运输节点不等于生产矿井；作业区、废弃矿井及深层探索需要相应许可、装备和风险准备。",
        "arrival_point": "具体落脚点将在游戏开场时确定，不默认将角色置于作业深井或未探索矿道。",
        "safeguards": ["进入矿井作业或深层区域前需满足当地工程与安全要求", "不假定角色自动获得采矿权限或专用装备"],
    },
    {
        "id": "selavia_port", "name": "塞拉维亚港", "tagline": "街道从陆地延伸入海的联邦首都与综合港城",
        "description": "南海自由联邦首都，也是大陆最大的综合海运与贸易枢纽之一。人类与海族共同生活，陆上城区、人工半岛和向海底延伸的水下城区连接成一座跨越海面的城市。",
        "region": "大陆南部海岸·南海自由联邦", "environment": "大型沿海港城；沧澜天幕长期调节周边海流、波浪、气流与水汽，使主要港区保持稳定。",
        "structure": "陆上城区承担行政、外交和陆地居住；人工半岛连接庞大港区，其结构继续向下形成海族水下城区与交通枢纽。",
        "highlights": ["陆上与水下城区连为一体", "大型商船、护航舰与深海潜航船港区", "现代九阶海洋调衡系统沧澜天幕", "进入海族深海城市的重要门户"],
        "transport": "拥有远洋、客运、河海联运与潜航船线路；部分潜航船可直接前往海族深海城市。",
        "access_note": "其他种族进入水下城区必须佩戴海族制造的水下生存魔导器，以提供呼吸、压力与环境防护。",
        "arrival_point": "具体落脚点将在游戏开场时确定；选择塞拉维亚不表示默认进入水下城区。",
        "safeguards": ["进入水下城区前必须具备水下生存魔导器", "不假定系统自动配发水下装备或船票"],
    },
    {
        "id": "abyssal_tides", "name": "沧渊城", "tagline": "发光珊瑚照亮海床、破碎古环悬于城上的海族深海核心",
        "description": "沧渊城位于南部海洋深处，是海族规模最大的核心城市之一，约有海族总人口三成长居于此。城市中央的海神殿保存着严重损毁的十阶阿尔凯昂沧海之环控制核心。",
        "region": "南部海洋深处·海床", "environment": "深海高压水下环境；发光珊瑚、魔力矿石与魔导设施令城区近乎白昼。",
        "structure": "适应深海的建筑、交通和聚居区铺展于海床；破碎环体悬于城市上方或散落周围，海神殿兼具圣地与古代设施控制中心功能。",
        "highlights": ["破碎的阿尔凯昂沧海之环", "海神殿与无法开启的地下大门", "海族最大核心城市之一", "部分恢复的洋流、潮汐与灾害防护功能"],
        "transport": "通过海族水下交通和深海航路连接其他海域；塞拉维亚的部分潜航船可通往深海城市。",
        "access_note": "外族必须佩戴海族制造的水下生存魔导器；设定未定义无需装备即可停留的自动密闭访客站。",
        "arrival_point": "具体落脚点将在游戏开场时依交通方式与生存条件确定，不预设未定义的访客设施。",
        "safeguards": ["非水下适应种族必须具备水下呼吸、压力与环境防护魔导器", "不假定系统自动配发装备或开放海神殿地下设施"],
    },
    {
        "id": "sahravia", "name": "萨赫拉维亚", "tagline": "沙海边缘水渠纵横、公共交通在此折返的绿洲门户",
        "description": "萨赫拉维亚位于西部沙漠边缘，是多数旅人与冒险者进入西部的第一站。城市围绕天然大型绿洲发展，丰富地下水支撑水渠、花园、植被与农田。",
        "region": "大陆西部·沙漠边缘", "environment": "绿洲城内水源丰富，城外则迅速转为炎热、干燥、缺水且道路稀少的西部荒原。",
        "structure": "商业区、商队集散区、云端列车终点站与空艇港围绕绿洲展开；多个大陆级组织在此设有分部。",
        "highlights": ["与沙海形成强烈对比的大型绿洲", "西部公共交通主要终点", "大型官方商队与自由商业", "多家大陆级组织分部"],
        "transport": "可乘云端列车或空艇抵达；继续向西主要依靠商队、私人交通或冒险者自身能力。",
        "access_note": "城内是成熟补给与集散地，但离开城市深入荒原后必须自行应对水源、高温、迷路和补给问题。",
        "arrival_point": "具体落脚点将在游戏开场时确定，不默认角色已加入商队或直接置于无人沙漠。",
        "safeguards": ["深入西部前需准备水、补给和适合荒原的交通或生存能力", "不假定自动获得商队席位、向导或荒原装备"],
    },
]

for location in LOCATIONS:
    location_id = location["id"]
    location["summary"] = location["tagline"]
    location["image_landscape_path"] = f"/assets/world/locations/{location_id}-landscape.webp"
    location["image_portrait_path"] = f"/assets/world/locations/{location_id}-portrait.webp"


FACTIONS = [
    {
        "id": "sacred_radiance", "name": "圣辉教廷", "tagline": "以信仰维系秩序、慈悲、守护与正义的人类神权国家",
        "description": "教廷的圣辉术包含光属性、治疗、防护、净化与辅助魔法。其守护和慈善理念真实落实于骑士巡游与平民援助，但组织也存在教义保守、政治斗争及对魔族的传统偏见。",
        "headquarters": "首都圣维利亚，中央教廷与主要宗教机构集中于此。",
        "ideology": "以光明与慈悲之神信仰为核心，崇尚秩序、慈悲、守护与正义；信徒将由稳定精神结构调用魔力理解为神力。",
        "organization": "兼具宗教与世俗统治权，主要层级为教皇、红衣主教、紫衣主教、主教与基层神职人员，并拥有庞大骑士体系。",
        "tasks": ["魔物肃清", "护送与救援", "医疗物资运输", "危险区域调查"],
        "services": ["光属性、治疗、防护与净化相关援助", "巡游骑士对村镇、商路与灾难提供援助，原则上不向受助者收费"],
        "activities": ["接受公开委托", "在符合条件后以骑士、圣职者或其他身份正式加入"],
        "rewards": ["金钱与教廷声望", "光属性装备与治疗道具", "光属性、治疗类魔导物品"],
        "audience": "公开任务面向符合任务要求的各族参与者。",
        "access_note": "浏览公开任务或使用公开援助不等于成为教廷成员；正式加入另有身份与组织要求。",
    },
    {
        "id": "valkeren", "name": "瓦尔凯伦帝国", "tagline": "以实力、军功、契约和实际成果组织国家的军事化帝国",
        "description": "帝国位于中央平原西部，是大陆重要军事服务与军工输出国。它允许凭贡献上升，也长期存在军国文化、社会阶层差异及对兽裔尤其半兽人的明显偏见。",
        "headquarters": "首都瓦尔加德，赤铁皇宫是最高行政与军事决策中心。",
        "ideology": "重视实力、军功、忠诚、契约精神与实际贡献，倾向用武力处理无法谈判的问题。",
        "organization": "帝王集最高政治与军权于一身，下设大将军、帝国高层、军团、地方总督与行政机构，并运营官方军事服务体系。",
        "tasks": ["魔物讨伐", "商队护送", "边境作战与危险区域肃清", "军事护卫与高价值目标保护"],
        "services": ["有偿商队护卫、城市防卫与私人护卫", "军事顾问、魔导炮兵及高阶战力支援", "武器、重甲与军工装备供应"],
        "activities": ["承接帝国战斗和护卫任务", "符合条件后加入军队、官方佣兵体系或军事机构"],
        "rewards": ["金钱与帝国声望", "武器、重甲与魔导武器", "龙族或矮人工艺装备"],
        "audience": "大量公开战斗与护卫任务可由合适参与者承接。",
        "access_note": "公开委托和有偿服务不等于取得军籍或军事授权；正式加入及内部行动须遵循帝国体系。",
    },
    {
        "id": "grand_academy", "name": "维尔瑟亚大联合学院", "tagline": "永久中立、向所有智慧种族开放的战士、法师与魔导学术中心",
        "description": "学院位于大陆中央，不隶属于任何国家或宗教势力。三位十阶院长分别领导战士、法师和魔导学院，也是跨种族知识交流与大陆高阶研究的核心。",
        "headquarters": "学院本身即为总部，位于圣辉教廷与瓦尔凯伦帝国之间。",
        "ideology": "知识、力量与教育不应只属于某一个种族或国家。",
        "organization": "由战士、法师、魔导三大学院组成；三位院长负责重大事项，正副理事处理日常行政，法师学院另设八座属性塔。",
        "tasks": ["异常事件与魔导事故调查", "古代遗迹探索与魔物研究", "灾害支援、失踪人员搜寻和危险物品回收"],
        "services": ["学习技能、魔法与战技", "接触导师、知识库与研究设施", "进行魔导技术及跨种族学术研究"],
        "activities": ["学院课程与跨学院交流", "魔法竞技、战士比武和魔导技术展示", "每百年举行的大型庆典与学术交流"],
        "rewards": ["世界知识、训练与能力提升机会", "导师与研究资源", "具体任务报酬按学院委托确定"],
        "audience": "招生面向所有智慧种族；部分任务也向受认可的外部人员发布。",
        "access_note": "公开交流、外部任务与正式入学不同；入学必须通过资质试炼和心性试炼。",
    },
    {
        "id": "south_sea_federation", "name": "南海自由联邦", "tagline": "由港口、沿海自治领与海族聚居区组成的跨种族海洋联邦",
        "description": "联邦以贸易、航运、商业与多元文化为核心，奉行和平中立。人类与海族共同构成双执政官体系，成熟的船舶工业和海巡舰队支撑海上治安、物流与探索。",
        "headquarters": "首都塞拉维亚港，联邦行政、港运和陆海交通在此汇集。",
        "ideology": "避免意识形态冲突，优先维护契约、信用、自由贸易、运输与地区稳定。",
        "organization": "由港口城市、沿海自治领、河口城市、海族聚居区与商业城市组成，各地高度自治，中央采用人类与海族双执政官制。",
        "tasks": ["海魔物讨伐、海盗清剿与商船护航", "海上搜救、沉船和未知岛屿调查", "深海资源采集与贵重货物运输"],
        "services": ["海上与河流运输", "商船、客船、护航舰与潜航船制造维修", "港口贸易和海洋魔导技术服务"],
        "activities": ["发展商业、航海与海洋冒险路线", "参与海巡、探索、资源与运输事务"],
        "rewards": ["金钱与联邦声望", "航海装备和船舶部件", "海洋类魔导物品与特殊贸易资源"],
        "audience": "法律原则上不以种族、国籍、信仰或出身限制正常社会活动。",
        "access_note": "公开贸易与海事任务不等于联邦公职或舰队成员资格；深海事务还要求相应生存能力或交通工具。",
    },
    {
        "id": "adventurers_guild", "name": "维尔瑟亚冒险者联合公会", "tagline": "覆盖全大陆、连接委托人与自由冒险者的永久中立平台",
        "description": "公会不统治领土、不拥有正规军队，也不介入国家战争。它直接采用通行的十阶体系记录冒险者能力并评估任务风险，不另设青铜、白银等冒险者等级。",
        "headquarters": "设定集未说明总部所在城市；分会遍布首都、城邦、普通城镇乃至小型村庄。",
        "ideology": "保持跨国中立，为民间委托、救援、魔物处理与危险调查建立可信的发布和履约渠道。",
        "organization": "地方分会高度自主，由总部和总会长协调跨国事务、重大危机及中立原则；登记冒险者仍是自由人员。",
        "tasks": ["按地区承接魔物讨伐、护送、采集与调查", "处理危险遗迹、大型灾害和异常魔力事件", "参与搜救及其他民间委托"],
        "services": ["冒险者注册、任务发布与接取、难度评估", "报酬托管、队伍招募、身份与履历记录", "情报、素材鉴定，以及大型分会的地图、仓储、补给和临时住宿"],
        "activities": ["浏览与接取任务", "发布委托、招募队友或加入临时队伍", "查询当地魔物与危险区域、积累冒险履历"],
        "rewards": ["领取由公会托管的任务报酬", "具体金钱、物资或其他回报由委托内容决定"],
        "audience": "所有智慧种族均可正常注册，不以国籍、信仰或社会阶层限制。",
        "access_note": "公会会警告或拒绝明显超出承受能力的极端任务；注册与接取公开任务不构成对公会的军事从属。",
    },
    {
        "id": "skyreach_transit", "name": "天穹航运联合会", "tagline": "由羽族牵头、连接大陆主要城市的中立空中交通组织",
        "description": "联合会运营空艇、云端列车、商队和特殊运输，将羽族浮空技术、人类标准化运营与矮人工程制造整合为大陆级交通网络。",
        "headquarters": "云端天境的天穹航运总港，也是大陆最大的空中交通枢纽之一。",
        "ideology": "维持中立、安全和开放的民用空中交通，不将航运网络用于政治或军事扩张。",
        "organization": "名义上直属羽族与天穹议庭，日常运营高度独立；航务总长统筹航线、安全、对外协调与重大事故。",
        "tasks": ["空艇与云端列车护卫", "飞行魔物肃清和空盗讨伐", "失事空艇搜救、贵重货物运输和异常航线调查"],
        "services": ["空艇与云端列车客货运", "商队、高价值货物与旅游运输", "包机和特殊运输服务"],
        "activities": ["购买公开航线票务", "委托货运或特殊运输", "参加空中护航与救援事务"],
        "rewards": ["设定集未统一规定固定奖励，依具体运输、护航或搜救委托确定"],
        "audience": "购票和运输服务面向公众；护航队也招募多种族成员。",
        "access_note": "使用民用交通或承接公开任务不等于加入联合会；专业岗位与高风险航线要求相应能力。",
    },
    {
        "id": "grandworks_union", "name": "维尔瑟亚大工程联合会", "tagline": "由矮人牵头、承接大陆基础设施与魔导系统的中立工程组织",
        "description": "联合会分部遍布主要地区，负责大型建筑、魔导系统、环境改造和民用工程的设计、施工与维护，是跨种族工程技术协作平台。",
        "headquarters": "西部万炉矿渊正下方的炉心城。",
        "ideology": "以材料、图纸、预算、技术标准和工程可靠性完成各规模项目，并长期保持政治中立。",
        "organization": "矮人是核心技术力量，各族工程师负责自身专长；首席总匠统领技术方向，工程总长协调分部和大型项目。",
        "tasks": ["矿石与特殊材料采集、矿井探索", "工程区域魔物清理与工程队护送", "设施维修、事故调查、遗迹测绘与核心部件寻找"],
        "services": ["大型建筑、动力、水利、地下、浮空与环境工程", "城市魔力网络、魔导设施和民用设备维修", "工程验收与行业认证"],
        "activities": ["提出民间或国家级工程委托", "以锻造、魔导或工程能力参与项目", "参与施工、测绘、维护与材料运输"],
        "rewards": ["设定集未统一规定固定奖励，依工程任务、雇佣或合同确定"],
        "audience": "国家、组织与普通民间均可向分部提出工程委托；技术岗位面向具备相应能力者。",
        "access_note": "公开委托和服务不等于成为联合会工程师；专业岗位、施工区和高等级项目有技术与安全要求。",
    },
    {
        "id": "mind_soul_physicians", "name": "灵心医师联合会", "tagline": "面向全大陆提供精神、意识与灵魂诊疗的专业医疗组织",
        "description": "联合会由魔族建立，分部广布大型城市、军事城市和交通枢纽。它能诊断、保护和治疗尚未消散的灵魂与精神结构，但不能恢复已经彻底消散的灵魂。",
        "headquarters": "设定集未明确标注总部所在城市；各地设有广泛分部，魔族首都诺克维亚拥有最高规格的精神与灵魂医疗设施。",
        "ideology": "坚持医疗中立，通常不因种族、国籍、信仰或政治立场拒绝正常患者。",
        "organization": "名义上直属魔族王权但保持专业独立；总医监协调分部、医疗规范和技术标准，核心诊疗医师多为魔族。",
        "tasks": ["精神异常、灵魂魔法事故与污染源调查", "护送高级医师", "回收危险灵魂魔导器与寻找治疗材料"],
        "services": ["精神损伤、意识异常和灵魂损伤诊疗", "精神稳定训练与精神、灵魂防护", "提供相关监测、治疗、保护与合法强化魔导设备"],
        "activities": ["接受精神与灵魂医疗", "参与异常调查、医疗护送和材料任务", "以医疗、护理、工程、药剂、行政或安保身份参与组织工作"],
        "rewards": ["精神类装备与灵魂保护魔导器", "治疗服务与特殊强化"],
        "audience": "医疗服务面向全大陆各族患者；非魔族也可担任多类非核心诊疗岗位。",
        "access_note": "接受公开医疗或任务不等于正式加入；危险事务会按能力委派，医疗能力也不突破灵魂消散规则。",
    },
    {
        "id": "skycrown_conclave", "name": "天穹议庭", "tagline": "由女皇主持、共同管理云端天境十二云区的羽族核心政权",
        "description": "议庭政治风格稳定温和，由羽族女皇和十二位云区代表共同议政；独立长老体系承担高阶守护、技术与重大危机处理。",
        "headquarters": "云端天境天冠岛上的羽族首都维兰希亚。",
        "ideology": "和平、友好、低冲突外交；以议会讨论协调十二云区的治理、资源、外交与公共事务。",
        "organization": "女皇主持议庭，十二云区各有一名代表；长老直属女皇但原则上不参与正常政治决策。",
        "tasks": ["云区巡逻、飞行魔物肃清与人员救援", "浮空设施保护、高空异常调查", "重要运输、外交护送和魔导设施维护"],
        "services": ["对获许可者开放云端天境公开区域", "通过公共治理维持云区与浮空设施运行"],
        "activities": ["羽族成员可在符合条件后接受内部事务", "外族可在获得许可后访问开放区域"],
        "rewards": ["羽族专属装备与风属性魔导器", "高阶训练资源", "议庭任务通常比普通航运任务难度与奖励更高"],
        "audience": "只有羽族可以正式加入并接受内部任务；非羽族仅可访问获准开放区域。",
        "access_note": "公开区域访问不等于议庭成员资格；本页面展示内部任务，也不会在角色创建阶段完成加入。",
    },
    {
        "id": "sacred_tree_court", "name": "圣树王庭", "tagline": "由两位十阶精灵共同统治、守护古圣树与精灵之森的精简政权",
        "description": "王庭服务于人口稀少、社会稳定且高度隔绝的精灵族，不设复杂官僚机构。日常政务由九阶执政官处理，重大事务由精灵皇与精灵女皇共同决定。",
        "headquarters": "精灵之森最深处、古圣树周围的精灵核心聚居区域。",
        "ideology": "守护古圣树、族群、森林生态与长期稳定，较少主动参与大陆政治、战争和商业活动。",
        "organization": "两位十阶共同拥有最高决策权，九阶执政官处理日常政务；精灵没有庞大常备军，由族人和高阶守护者分级应对威胁。",
        "tasks": ["森林巡查、魔物肃清与族人支援", "失踪人员搜寻和生态异常调查", "特殊植物材料采集与古圣树事务"],
        "services": ["经许可进入部分外围与开放区域", "在学术、生态、环境或特殊事件中开展有限对外合作"],
        "activities": ["精灵成员参与王庭种族事务", "获许可外族参与研究、外交或特殊合作"],
        "rewards": ["木属性魔法与精灵法术", "魔法弓、特殊箭矢、精灵药剂和自然系魔导器", "古圣树材料与高阶精灵训练资源"],
        "audience": "只有精灵可以正式接受王庭种族任务；外族访问范围受许可限制。",
        "access_note": "进入森林开放区不等于可进入古圣树或核心聚居区，也不等于加入王庭。",
    },
    {
        "id": "dragonvale_moot", "name": "龙谷议盟", "tagline": "没有常设政府与常备军、只在重大事件中汇聚龙族的松散议盟",
        "description": "议盟是龙族名义上的共同政权。龙谷是祖地、幼龙成长地与年长龙族聚居地，而非行政首都；龙皇仅在全族重大事务中发布血脉召集令并作最终仲裁。",
        "headquarters": "没有常设总部；熔脊龙谷是传统集会地点和共同祖地。",
        "ideology": "尊重成年龙族的高度独立与个人选择，只在涉及全族的重大事件中形成共同决定。",
        "organization": "龙皇是最高领袖与最终仲裁者；议事没有严格程序，高阶龙族大多散居各地，议盟也没有常备军。",
        "tasks": ["议盟本身不设官方任务；龙族个人通常经冒险者公会发布委托", "常见委托包括高阶魔物、遗迹和稀有材料事务", "幼龙护送、失踪龙族搜寻与私人事务处理"],
        "services": ["议盟本身不提供统一常设公共服务", "个人龙族可通过公会建立公开委托与报酬关系"],
        "activities": ["参与龙族个人委托", "龙族在重大事件中响应血脉召集令返回龙谷议事"],
        "rewards": ["高品质武器与龙族魔导装备", "稀有材料、大额报酬或龙族个人的人情"],
        "audience": "龙族个人通过公会发布的委托通常不限制接受者种族。",
        "access_note": "公开个人委托不代表议盟官方任务或成员招募；龙谷也不是一套常设行政加入体系。",
    },
    {
        "id": "veiled_night", "name": "幽夜王庭", "tagline": "以诺克维亚为中心、规范运用暗属性与精神灵魂力量的魔族王权",
        "description": "王庭采用中央王权制度，设有内政、财政、外交、军事、魔导技术与公共事务部门。魔族军队擅长精神防御、隐蔽侦察、控制和暗属性魔法，相关力量受严格规范。",
        "headquarters": "魔族首都诺克维亚的魔王城与王庭核心机构。",
        "ideology": "维护魔族国家与公共秩序，奉行和平外交；精神与灵魂力量不得任意用于平民或非法控制。",
        "organization": "魔王拥有最高政治军事权，首席辅政官汇总各部门日常政务；王庭拥有正规军队与治安力量。",
        "tasks": ["魔物讨伐、国家安全事件与边境支援", "高危险调查、特殊人员保护", "危险魔导器回收与犯罪组织清剿"],
        "services": ["通过国家行政和治安体系处理公共事务", "灵心医师联合会另以高独立性提供专业医疗"],
        "activities": ["承接面向各族公开的王庭官方委托", "符合授权和组织条件后参与内部行政或军事事务"],
        "rewards": ["金钱与王庭声望", "暗属性装备、精神与灵魂类魔导器", "魔族特殊法术、高阶魔导装备与特殊强化机会"],
        "audience": "公开官方委托向所有种族开放。",
        "access_note": "承接公开委托不等于加入王庭；内部事务、行政与军事权限仍需正式授权。",
    },
]

for faction in FACTIONS:
    faction_id = faction["id"]
    faction["image_landscape_path"] = f"/assets/world/factions/{faction_id}-landscape.webp"
    faction["image_portrait_path"] = f"/assets/world/factions/{faction_id}-portrait.webp"

PRESETS = {
    "appearance": [
        {"id": "hair_black", "label": "黑发", "category": "发色", "race_ids": []},
        {"id": "hair_dark_brown", "label": "深棕发", "category": "发色", "race_ids": []},
        {"id": "hair_blonde", "label": "金发", "category": "发色", "race_ids": []},
        {"id": "hair_silver", "label": "银发", "category": "发色", "race_ids": []},
        {"id": "hair_white", "label": "白发", "category": "发色", "race_ids": []},
        {"id": "hair_red", "label": "赤红发", "category": "发色", "race_ids": []},
        {"id": "hair_blue_black", "label": "蓝黑发", "category": "发色", "race_ids": []},
        {"id": "hair_long", "label": "长发", "category": "发型", "race_ids": []},
        {"id": "hair_short", "label": "短发", "category": "发型", "race_ids": []},
        {"id": "hair_curly", "label": "卷发", "category": "发型", "race_ids": []},
        {"id": "hair_braided", "label": "编发", "category": "发型", "race_ids": []},
        {"id": "hair_ponytail", "label": "束成马尾", "category": "发型", "race_ids": []},
        {"id": "eyes_black", "label": "黑色眼眸", "category": "眼眸", "race_ids": []},
        {"id": "eyes_brown", "label": "棕色眼眸", "category": "眼眸", "race_ids": []},
        {"id": "eyes_blue", "label": "湛蓝眼眸", "category": "眼眸", "race_ids": []},
        {"id": "eyes_green", "label": "碧绿眼眸", "category": "眼眸", "race_ids": []},
        {"id": "eyes_amber", "label": "琥珀色眼眸", "category": "眼眸", "race_ids": []},
        {"id": "eyes_silver", "label": "银灰色眼眸", "category": "眼眸", "race_ids": []},
        {"id": "eyes_red", "label": "赤红色眼眸", "category": "眼眸", "race_ids": []},
        {"id": "build_slender", "label": "身形纤细", "category": "身形体态", "race_ids": []},
        {"id": "build_proportioned", "label": "身形匀称", "category": "身形体态", "race_ids": []},
        {"id": "build_tall", "label": "身材高挑", "category": "身形体态", "race_ids": []},
        {"id": "build_fit", "label": "身形健硕", "category": "身形体态", "race_ids": []},
        {"id": "build_powerful", "label": "体格魁梧", "category": "身形体态", "race_ids": []},
        {"id": "build_petite", "label": "身材娇小", "category": "身形体态", "race_ids": []},
        {"id": "posture_upright", "label": "姿态挺拔", "category": "身形体态", "race_ids": []},
        {"id": "feature_neat", "label": "衣着整洁", "category": "外观特征", "race_ids": []},
        {"id": "feature_weathered", "label": "饱经风霜", "category": "外观特征", "race_ids": []},
        {"id": "feature_soft", "label": "五官柔和", "category": "外观特征", "race_ids": []},
        {"id": "feature_sharp", "label": "轮廓硬朗", "category": "外观特征", "race_ids": []},
        {"id": "feature_scar", "label": "带有伤疤", "category": "外观特征", "race_ids": []},
        {"id": "feature_freckles", "label": "脸上有雀斑", "category": "外观特征", "race_ids": []},
    ],
    "personality": [
        {"id": "calm", "label": "沉着", "category": "处世基调", "race_ids": []},
        {"id": "optimistic", "label": "乐观", "category": "处世基调", "race_ids": []},
        {"id": "cautious", "label": "谨慎", "category": "处世基调", "race_ids": []},
        {"id": "decisive", "label": "果断", "category": "处世基调", "race_ids": []},
        {"id": "easygoing", "label": "随和", "category": "处世基调", "race_ids": []},
        {"id": "rigorous", "label": "严谨", "category": "处世基调", "race_ids": []},
        {"id": "pragmatic", "label": "务实", "category": "处世基调", "race_ids": []},
        {"id": "patient", "label": "耐心", "category": "处世基调", "race_ids": []},
        {"id": "forthright", "label": "直率", "category": "社交方式", "race_ids": []},
        {"id": "talkative", "label": "健谈", "category": "社交方式", "race_ids": []},
        {"id": "reserved", "label": "寡言", "category": "社交方式", "race_ids": []},
        {"id": "gentle", "label": "温和", "category": "社交方式", "race_ids": []},
        {"id": "aloof", "label": "疏离", "category": "社交方式", "race_ids": []},
        {"id": "courteous", "label": "礼貌", "category": "社交方式", "race_ids": []},
        {"id": "humorous", "label": "幽默", "category": "社交方式", "race_ids": []},
        {"id": "empathetic", "label": "善于共情", "category": "社交方式", "race_ids": []},
        {"id": "curious", "label": "好奇", "category": "驱动力", "race_ids": []},
        {"id": "knowledge_seeking", "label": "求知", "category": "驱动力", "race_ids": []},
        {"id": "honor_driven", "label": "重视荣誉", "category": "驱动力", "race_ids": []},
        {"id": "freedom_seeking", "label": "追求自由", "category": "驱动力", "race_ids": []},
        {"id": "responsible", "label": "富有责任感", "category": "驱动力", "race_ids": []},
        {"id": "protective", "label": "保护欲强", "category": "驱动力", "race_ids": []},
        {"id": "ambitious", "label": "渴望成就", "category": "驱动力", "race_ids": []},
        {"id": "loyal", "label": "重视承诺", "category": "驱动力", "race_ids": []},
        {"id": "stubborn", "label": "固执", "category": "弱点与棱角", "race_ids": []},
        {"id": "suspicious", "label": "多疑", "category": "弱点与棱角", "race_ids": []},
        {"id": "impulsive", "label": "冲动", "category": "弱点与棱角", "race_ids": []},
        {"id": "proud", "label": "骄傲", "category": "弱点与棱角", "race_ids": []},
        {"id": "softhearted", "label": "心软", "category": "弱点与棱角", "race_ids": []},
        {"id": "inexpressive", "label": "不善表达", "category": "弱点与棱角", "race_ids": []},
        {"id": "overcautious", "label": "顾虑过多", "category": "弱点与棱角", "race_ids": []},
        {"id": "competitive", "label": "好胜", "category": "弱点与棱角", "race_ids": []},
    ],
    "talent": [
        {"id": "magic_sense", "label": "魔力感知敏锐", "category": "魔力与施法", "race_ids": []},
        {"id": "elemental_affinity", "label": "元素亲和", "category": "魔力与施法", "race_ids": []},
        {"id": "spell_control", "label": "施法控制细致", "category": "魔力与施法", "race_ids": []},
        {"id": "magic_recovery", "label": "魔力恢复较快", "category": "魔力与施法", "race_ids": []},
        {"id": "spell_stability", "label": "施法稳定", "category": "魔力与施法", "race_ids": []},
        {"id": "magic_resonance", "label": "魔力共鸣敏锐", "category": "魔力与施法", "race_ids": []},
        {"id": "endurance", "label": "耐力出众", "category": "身体与战斗", "race_ids": []},
        {"id": "reflexes", "label": "反应敏捷", "category": "身体与战斗", "race_ids": []},
        {"id": "weapon_instinct", "label": "武器直觉", "category": "身体与战斗", "race_ids": []},
        {"id": "coordination", "label": "身体协调", "category": "身体与战斗", "race_ids": []},
        {"id": "balance", "label": "平衡感强", "category": "身体与战斗", "race_ids": []},
        {"id": "pain_tolerance", "label": "忍耐力强", "category": "身体与战斗", "race_ids": []},
        {"id": "fast_learner", "label": "学习迅速", "category": "认知与技艺", "race_ids": []},
        {"id": "memory", "label": "记忆清晰", "category": "认知与技艺", "race_ids": []},
        {"id": "analysis", "label": "善于分析", "category": "认知与技艺", "race_ids": []},
        {"id": "craft_sense", "label": "工艺直觉", "category": "认知与技艺", "race_ids": []},
        {"id": "circuit_understanding", "label": "魔导回路理解力", "category": "认知与技艺", "race_ids": []},
        {"id": "observation", "label": "观察细致", "category": "认知与技艺", "race_ids": []},
        {"id": "emotional_insight", "label": "洞察情绪", "category": "社会与生存", "race_ids": []},
        {"id": "negotiation", "label": "谈判意识", "category": "社会与生存", "race_ids": []},
        {"id": "wilderness_survival", "label": "野外生存", "category": "社会与生存", "race_ids": []},
        {"id": "direction", "label": "方向感良好", "category": "社会与生存", "race_ids": []},
        {"id": "danger_sense", "label": "危险感知敏锐", "category": "社会与生存", "race_ids": []},
        {"id": "adaptability", "label": "环境适应较快", "category": "社会与生存", "race_ids": []},
    ],
    "merge_rule": "按点击顺序追加到可编辑文本；相同稳定ID去重。",
}

NARRATION = {
    "pace": [{"id": "slow", "name": "慢"}, {"id": "fast", "name": "快"},
             {"id": "dynamic", "name": "动态"}],
    "tone": [{"id": "casual", "name": "休闲"}, {"id": "balanced", "name": "平衡"},
             {"id": "combat", "name": "战斗"}],
    "detail": [{"id": "concise", "name": "简洁"}, {"id": "standard", "name": "标准"},
               {"id": "detailed", "name": "细致"}],
    "player_address": [{"id": "full_name", "name": "全名"},
                       {"id": "given_name", "name": "名"},
                       {"id": "second_person", "name": "第二人称"}],
    "defaults": {"pace": "dynamic", "tone": "balanced", "detail": "standard",
                 "player_address": "second_person"},
}

CATALOG = {
    "ruleset_version": RULESET_VERSION,
    "races": RACES,
    "locations": LOCATIONS,
    "factions": FACTIONS,
    "faction_notice": "本步骤无需选择；符合条件的势力可在游戏过程中加入。",
    "rank_system": {
        "title": "什么是等阶",
        "description": "等阶是维尔瑟亚用于跨种族、跨职业衡量个体综合战斗能力的通用标准，共分一至十阶。同阶只表示整体战斗层级与威胁大致相当，并不表示攻击、防御、速度或能力结构相同；种族天赋、职业路线、装备、环境、数量、战术与克制都会改变实际胜负。高阶强者数量稀少，十阶更是现代文明个体战力的顶点，与其下层级存在明显断层。界面推荐选择六阶及以下，是为了保留更多成长与挑战空间的游戏性提示，并非世界规则对角色的硬性限制。",
        "principles": ["同阶不等于能力相同", "实际胜负受种族、职业、环境与克制等因素影响", "高阶稀少，十阶是文明个体战力顶点", "六阶以下仅为游戏体验建议"],
    },
    "ranks": [{"rank": rank, "display_rank": f"{_CHINESE_RANKS[rank - 1]}阶",
               "name": f"{_CHINESE_RANKS[rank - 1]}阶", "base_power": power,
               "next_exp": EXP_THRESHOLDS[rank],
               "warning": ("七阶及以上属于稀少高阶强者；推荐选择六阶及以下。"
                           if rank >= 7 else None)}
              for rank, power in POWER_BY_RANK.items()],
    "exp_thresholds": EXP_THRESHOLDS,
    "presets": PRESETS,
    "narration": NARRATION,
    "limits": {"long_attribute": [1, 100], "resource_max": [1, 9999]},
}

RACE_IDS = {item["id"] for item in RACES}
LOCATION_IDS = {item["id"] for item in LOCATIONS}


def validate_draft(data, complete=False):
    """Return field errors. The faction browsing step deliberately has no field."""
    errors = {}
    allowed = {"race_id", "race_branch_id", "name", "gender", "age", "appearance",
               "personality", "rank", "talent", "backstory", "start_location_id", "additional"}
    for field in set(data) - allowed:
        errors[field] = "未知角色草稿字段"
    forbidden = {"faction", "faction_id", "factions"}.intersection(data)
    for field in forbidden:
        errors[field] = "角色草稿不包含势力选择"
    race_id = data.get("race_id")
    if race_id is not None and race_id not in RACE_IDS:
        errors["race_id"] = "未知种族"
    if race_id == "therian" and data.get("race_branch_id") not in {"orc", "half_orc"}:
        errors["race_branch_id"] = "兽裔必须选择兽人或半兽人分支"
    if data.get("race_branch_id") and race_id != "therian":
        errors["race_branch_id"] = "只有兽裔可以选择分支"
    if "rank" in data and (type(data["rank"]) is not int or not 1 <= data["rank"] <= 10):
        errors["rank"] = "等阶必须为1至10"
    if "age" in data and (type(data["age"]) is not int or data["age"] <= 0):
        errors["age"] = "年龄必须为正整数"
    if "start_location_id" in data and data["start_location_id"] not in LOCATION_IDS:
        errors["start_location_id"] = "未知初始地点"
    for field, limit in {"name": 100, "gender": 100, "appearance": 4000,
                         "personality": 4000, "talent": 4000,
                         "backstory": 12000, "additional": 8000}.items():
        if field in data and (not isinstance(data[field], str) or len(data[field]) > limit):
            errors[field] = f"必须是长度不超过{limit}的文本"
    for field in ("name", "gender", "appearance", "personality", "talent"):
        if field in data and isinstance(data[field], str) and not data[field].strip():
            errors[field] = "不能为空白文本"
    if complete:
        for field in ("race_id", "name", "gender", "age", "appearance", "personality",
                      "rank", "talent", "start_location_id"):
            if data.get(field) in (None, ""):
                errors[field] = "生成角色前必须填写"
    return errors


def high_rank_warning(rank):
    if type(rank) is int and rank >= 7:
        return "七阶及以上属于稀少高阶强者，会显著改变游戏体验；推荐选择六阶及以下。"
    return None
