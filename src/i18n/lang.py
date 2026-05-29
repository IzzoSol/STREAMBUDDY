GAME_NAMES = {
    "en": "Game",
    "es": "Juego",
    "fr": "Jeu",
    "de": "Spiel",
    "ja": "ゲーム",
    "zh": "游戏",
    "ko": "게임",
    "pt": "Jogo",
    "ru": "Игра",
}

HELP_KEYWORDS = {
    "en": [
        "how do i", "how to", "where is", "help", "stuck",
        "walkthrough", "guide", "tips", "what do i do",
        "how do i beat", "strategy",
    ],
    "es": [
        "cómo", "como hago", "dónde está", "ayuda", "atascado",
        "guía", "consejos", "tutorial", "cómo vencer",
    ],
    "fr": [
        "comment", "où est", "aide", "bloqué", "guide",
        "astuces", "tutoriel", "comment battre",
    ],
    "de": [
        "wie mache ich", "wo ist", "hilfe", "feststecken",
        "komplettlösung", "leitfaden", "tipps", "wie besiege ich",
    ],
    "ja": [
        "方法", "どこ", "助けて", "詰まった", "攻略",
        "ガイド", "ヒント", "倒し方",
    ],
    "zh": [
        "怎么", "如何", "在哪里", "帮助", "卡住了",
        "攻略", "指南", "技巧", "怎么打败",
    ],
    "pt": [
        "como faço", "onde está", "ajuda", "preso",
        "guia", "dicas", "tutorial", "como vencer",
    ],
    "ru": [
        "как", "где", "помогите", "застрял",
        "прохождение", "гайд", "советы", "как победить",
    ],
}

CONTEXT_CATEGORIES = {
    "en": {
        "combat": ["boss", "enemy", "fight", "attack", "damage", "kill", "defeat", "battle"],
        "exploration": ["where", "find", "location", "area", "map", "hidden", "secret"],
        "quest": ["quest", "mission", "objective", "task"],
        "crafting": ["craft", "crafting", "build", "create", "make", "recipe"],
        "puzzle": ["puzzle", "riddle", "solve", "solution", "code", "lock"],
        "navigation": ["path", "door", "entrance", "exit", "stuck", "blocked"],
    },
    "es": {
        "combat": ["jefe", "enemigo", "pelea", "ataque", "daño", "matar", "derrotar"],
        "exploracion": ["donde", "encontrar", "ubicacion", "area", "mapa", "secreto"],
        "mision": ["mision", "objetivo", "tarea"],
        "artesania": ["crear", "construir", "fabricar", "receta"],
        "rompecabezas": ["rompecabezas", "acertijo", "resolver", "codigo"],
    },
    "fr": {
        "combat": ["boss", "ennemi", "combat", "attaque", "dégâts", "tuer", "vaincre"],
        "exploration": ["où", "trouver", "emplacement", "zone", "carte", "secret"],
        "quete": ["quête", "mission", "objectif"],
        "artisanat": ["fabriquer", "construire", "créer", "recette"],
        "enigme": ["énigme", "puzzle", "résoudre", "code"],
    },
}


def detect_language(text: str) -> str:
    from collections import Counter

    lang_scores = Counter()
    text_lower = text.lower()

    for lang, keywords in HELP_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in text_lower)
        if score > 0:
            lang_scores[lang] = score

    return lang_scores.most_common(1)[0][0] if lang_scores else "en"
