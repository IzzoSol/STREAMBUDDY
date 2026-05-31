from dataclasses import dataclass, field
from typing import Optional

BOSS_STRATEGIES = {
    "malenia": {
        "game": "Elden Ring",
        "phases": 2,
        "weaknesses": ["bleed", "frost", "poise break"],
        "resistances": ["holy", "fire"],
        "recommended_level": 120,
        "key_moves": [
            "Waterfowl Dance — sprint away first flurry, roll INTO second, roll away third",
            "Scarlet Aeonia — sprint left, punish from behind",
            "Grabs — punishable after recovery",
        ],
        "loadout_tips": [
            "Bloodhound's Step or Vow of the Indomitable for Waterfowl dodge",
            "Mimic Tear +10 or Tiche +10 spirit ash",
            "Rivers of Blood / RoB or Blasphemous Blade",
            "Dragoncrest Greatshield +2 talisman",
        ],
        "phase_1_strategy": "Stay mid-range. Let her come to you. Punish after her lunges and kick combo. Jump attack for stagger.",
        "phase_2_strategy": "She gains hyper armor. Wait for Scarlet Aeonia or big slam, punish then back off. Waterfowl is deadlier.",
    },
    "radahn": {
        "game": "Elden Ring",
        "phases": 2,
        "weaknesses": ["rot", "poison", "bleed", "frost"],
        "resistances": ["magic", "holy"],
        "recommended_level": 70,
        "key_moves": [
            "Gravity arrows — ride perpendicular to avoid",
            "Meteor phase transition — run away, summon all phantoms",
            "Spin2Win AoE — jump over shockwave",
        ],
        "loadout_tips": [
            "Rot breath / Swarm of Flies for status procs",
            "Resummon phantoms through the fight",
            "Light load for rolling his combos",
        ],
        "phase_1_strategy": "Summon all phantoms immediately. Rot breath twice, then ride around resummoning. Let phantoms tank.",
        "phase_2_strategy": "After meteor crash, keep gap. He's more aggressive. Rot breath when he's locked on phantom.",
    },
    "orphan of kos": {
        "game": "Bloodborne",
        "phases": 2,
        "weaknesses": ["visceral attacks", "bolt"],
        "resistances": ["arcane"],
        "recommended_level": 80,
        "key_moves": [
            "Leaping slam — roll toward and slightly left",
            "Placenta flail — back off, punish after final swing",
            "Phase 2 lightning — swim into water to dodge",
        ],
        "loadout_tips": [
            "Bolt paper for extra damage",
            "High rally potential weapon (Saw Cleaver / Whirligig Saw)",
            "Clawmark runes for visceral damage",
        ],
        "phase_1_strategy": "Punish after his combos. Parry his slow attacks for visceral. Stay close to bait melee combos.",
        "phase_2_strategy": "He gains AoE attacks. When he screams, back off. Swim through lightning AOE toward him.",
    },
    "isshin": {
        "game": "Sekiro",
        "phases": 3,
        "weaknesses": ["lightning reversal", "mikiri counter"],
        "resistances": ["none"],
        "recommended_level": 1,
        "key_moves": [
            "Ashina Cross — deflect both slashes, then attack",
            "Spear sweep — jump on his head",
            "Spear thrust — mikiri counter",
            "Phase 3 lightning — jump and reverse it",
        ],
        "loadout_tips": [
            "High posture damage combat art (Ichimonji Double / Mortal Draw)",
            "Loaded Umbrella for his wind slashes",
            "Rice / Divine Grass for healing",
        ],
        "phase_1_strategy": "Stay aggressive. Deflect his ichimonji. Punish his pause after long combos. Break his posture, don't rely on HP.",
        "phase_2_strategy": "Spear phase. Deflect his charge, mikiri the thrust. Jump sweep perilous. Lightening reversal in phase 3.",
    },
    "midir": {
        "game": "Dark Souls 3",
        "phases": 2,
        "weaknesses": ["lightning", "head"],
        "resistances": ["dark", "fire", "bleed", "poison", "frost"],
        "recommended_level": 100,
        "key_moves": [
            "Laser sweep — run toward him, roll under",
            "Fire breath — run left and behind",
            "Charge — roll right",
        ],
        "loadout_tips": [
            "Lightning buff on weapon (Lightning Blade / Gold Pine Resin)",
            "Pestilent Mist does %HP damage",
            "Only hit the head for double damage",
        ],
        "phase_1_strategy": "Stay in front. Wait for his head to drop after combos. 2-3 hits then back off. Never go under him.",
        "phase_2_strategy": "More lasers. When he does the dark AOE, run to the back wall. Punish head after charge.",
    },
    "nameless king": {
        "game": "Dark Souls 3",
        "phases": 2,
        "weaknesses": ["dark", "frost"],
        "resistances": ["lightning"],
        "recommended_level": 90,
        "key_moves": [
            "Phase 1 dragon fire — run left",
            "Phase 1 dragon charge — roll toward tail",
            "Phase 2 delayed thrust — dodge on movement, not wind-up",
        ],
        "loadout_tips": [
            "Dark weapon (Darksword / Onyx Blade / Dark-infused weapon)",
            "Lightning is BAD for phase 2 — switch to dark",
            "Dragon slayer armor set for lightning resist in phase 1",
        ],
        "phase_1_strategy": "Stay unlocked. Hit the dragon head. When it breathes fire, run left. Kill the dragon quickly to save estus.",
        "phase_2_strategy": "His attacks are DELAYED. Roll on his movement, not the wind-up. Single hits, don't get greedy. Punish after the thrust combo.",
    },
    "margit": {
        "game": "Elden Ring",
        "phases": 1,
        "weaknesses": ["strike", "poison", "bleed"],
        "resistances": ["holy", "slash"],
        "recommended_level": 30,
        "key_moves": [
            "Hammer slam — roll toward him",
            "Magic sword rain — sprint sideways",
            "Dagger swipe — parry opportunity",
        ],
        "loadout_tips": [
            "Margit's Shackle (from Patches) stuns him twice",
            "Jellyfish spirit ash for poison buildup",
            "Heavy weapon for stagger",
        ],
        "phase_1_strategy": "Use Shackle at 70% HP. Stay behind him. Jump attack for stagger. Summon sorcerer Rogier if needed.",
        "phase_2_strategy": "Same but faster. His cane sword extensions have longer reach. Roll INTO rather than away.",
    },
    "godrick": {
        "game": "Elden Ring",
        "phases": 2,
        "weaknesses": ["bleed", "frost", "poison"],
        "resistances": ["holy"],
        "recommended_level": 40,
        "key_moves": [
            "Wind cyclone — run away, punish when he stops",
            "Dragon head grab — roll left, huge punish window",
            "Phase 2 fire — roll through, not away",
        ],
        "loadout_tips": [
            "Nepheli Loux summon sign before fog gate",
            "Bleed weapon (Uchigatana / Flail)",
            "Rotten Stray spirit ash for rot",
        ],
        "phase_1_strategy": "Stay close. Bait the cyclone and punish. His axe combos have long recovery. Jump attacks break stance fast.",
        "phase_2_strategy": "Dodge the dragon head fire, stay behind him. When he does the AOE dragon attack, sprint away then punish.",
    },
}


GENERAL_STRATEGY_TIPS = {
    "soulslike": [
        "Level Vigor/VIT first — HP is your best stat",
        "Upgrade weapon before leveling damage stats",
        "Explore thoroughly before boss fights",
        "Read item descriptions for lore and hints",
        "Talk to NPCs until they repeat dialogue",
        "Check corners and behind waterfalls for secrets",
        "Use consumable buffs before boss fog gates",
    ],
    "openworld": [
        "Do side content before main story missions",
        "Fast travel often to avoid backtracking death runs",
        "Mark interesting locations on the map",
        "Check merchants for upgrades after each main quest",
        "Save manually before major decisions",
    ],
    "rpg": [
        "Save often and in different slots",
        "Talk to every NPC — many give quests",
        "Check quest logs for objective details",
        "Sell old gear, keep upgrade materials",
        "Spec your build around 1-2 damage stats",
    ],
    "fps": [
        "Check corners and sightlines before advancing",
        "Use cover, don't stand in the open to reload",
        "Ammo conservation — switch weapons instead of reloading in combat",
        "Learn the map layouts for flank routes",
        "Headphones give massive advantage for footsteps",
    ],
    "survival": [
        "Build a base before exploring dangerous areas",
        "Stockpile food, water, and medical supplies",
        "Upgrade tools before weapons",
        "Learn enemy patrol routes",
        "Sleep to save progress and restore buffs",
    ],
}


@dataclass
class GameStrategy:
    game: str
    boss: str = ""
    phases: int = 1
    weaknesses: list = field(default_factory=list)
    resistances: list = field(default_factory=list)
    recommended_level: int = 1
    key_moves: list = field(default_factory=list)
    loadout_tips: list = field(default_factory=list)
    phase_strategies: dict = field(default_factory=dict)
    general_tips: list = field(default_factory=list)


def get_boss_strategy(boss_name: str) -> Optional[GameStrategy]:
    key = boss_name.lower().strip()
    if key in BOSS_STRATEGIES:
        data = BOSS_STRATEGIES[key]
        return GameStrategy(
            game=data["game"],
            boss=boss_name,
            phases=data["phases"],
            weaknesses=data["weaknesses"],
            resistances=data["resistances"],
            recommended_level=data["recommended_level"],
            key_moves=data["key_moves"],
            loadout_tips=data["loadout_tips"],
            phase_strategies={
                "phase_1": data["phase_1_strategy"],
                "phase_2": data.get("phase_2_strategy", ""),
            },
        )
    return None


def get_game_tips(genre: str) -> list[str]:
    return GENERAL_STRATEGY_TIPS.get(genre, [])


STRATEGY_AGENTS = [
    {
        "name": "Aggressor",
        "focus": "offensive tactics",
        "bias": "aggressive play, high damage setups, speed kills",
        "description": "Recommends high-damage rushdown strategies and aggressive positioning",
    },
    {
        "name": "Defender",
        "focus": "defense and survival",
        "bias": "safe play, high survivability, patient approach",
        "description": "Prefers tanky builds, defensive tactics, and waiting for safe punish windows",
    },
    {
        "name": "Optimizer",
        "focus": "efficiency and speed",
        "bias": "speedrun strats, skip mechanics, sequence breaks",
        "description": "Finds the fastest path through content using glitches, skips, and optimized routing",
    },
    {
        "name": "Scholar",
        "focus": "mechanics and lore",
        "bias": "game mechanic explanations, lore-friendly strategies",
        "description": "Explains WHY strategies work through game mechanics and rewards understanding",
    },
    {
        "name": "Preparer",
        "focus": "loadout and preparation",
        "bias": "overpreparation, farming, crafting, gear checks",
        "description": "Focuses on what to bring and how to prepare before attempting content",
    },
    {
        "name": "Improviser",
        "focus": "adaptability",
        "bias": "flexible loadouts, multi-purpose tools, reactive play",
        "description": "Recommends versatile setups that work in many situations",
    },
    {
        "name": "Veteran",
        "focus": "experience and patterns",
        "bias": "pattern recognition, practiced techniques, consistency",
        "description": "Draws from deep experience with similar mechanics across multiple games",
    },
]
