import logging
import random
from dataclasses import dataclass, field
from typing import Optional

from src.strategy.strategies import STRATEGY_AGENTS, get_boss_strategy, GameStrategy

logger = logging.getLogger(__name__)


@dataclass
class AgentVote:
    agent_name: str
    agent_focus: str
    recommendation: str
    confidence: float
    loadout_suggestion: list = field(default_factory=list)
    key_advice: str = ""


@dataclass
class SwarmConsensus:
    boss: str
    game: str
    votes: list[AgentVote] = field(default_factory=list)
    top_recommendations: list[str] = field(default_factory=list)
    consensus_loadout: list[str] = field(default_factory=list)
    swarm_confidence: float = 0.0
    agreement_level: float = 0.0
    recommended_approach: str = ""


class StrategySwarm:
    def __init__(self):
        self.agents = STRATEGY_AGENTS
        self.vote_history: dict = {}

    def analyze_boss(self, boss_name: str, game: str = "") -> Optional[SwarmConsensus]:
        base = get_boss_strategy(boss_name)
        if not base:
            return None

        votes = []
        for agent in self.agents:
            vote = self._generate_agent_vote(agent, base)
            votes.append(vote)

        top_recs = self._extract_top_recommendations(votes)
        consensus_loadout = self._build_consensus_loadout(votes)
        agreement = self._calculate_agreement(votes)
        avg_confidence = sum(v.confidence for v in votes) / len(votes) if votes else 0
        swarm_conf = min(1.0, avg_confidence * (0.7 + 0.3 * agreement))

        approach = (
            f"Swarm recommends {top_recs[0].lower()}" if top_recs
            else f"Fight {boss_name} with a balanced approach focusing on {base.weaknesses[0] if base.weaknesses else 'consistent damage'}"
        )

        result = SwarmConsensus(
            boss=boss_name,
            game=base.game,
            votes=votes,
            top_recommendations=top_recs,
            consensus_loadout=consensus_loadout,
            swarm_confidence=round(swarm_conf, 2),
            agreement_level=round(agreement, 2),
            recommended_approach=approach,
        )

        key = f"{game}:{boss_name}".lower()
        self.vote_history[key] = result
        return result

    def _generate_agent_vote(self, agent: dict, base: GameStrategy) -> AgentVote:
        focus = agent["focus"]
        bias = agent["bias"]

        rec_parts = []
        loadout = []
        key_advice = ""
        confidence = random.uniform(0.65, 0.95)

        if focus == "offensive tactics":
            if base.weaknesses:
                rec_parts.append(f"Exploit {base.weaknesses[0]} weakness with corresponding gear/buffs")
                rec_parts.append(f"Use {base.weaknesses[0]}-inflicting weapons/items for massive damage")
            if base.key_moves:
                rec_parts.append(f"Punish these moves hard: {base.key_moves[0]}")
            rec_parts.append(f"Recommended level: {base.recommended_level}+")
            loadout = [f"Weapon with {base.weaknesses[0]}" for w in base.weaknesses[:2]] if base.weaknesses else []
            key_advice = "Stay aggressive but don't get greedy — 2-3 hits then reset"

        elif focus == "defense and survival":
            if base.resistances:
                rec_parts.append(f"Equip {base.resistances[0]} resistance gear — boss deals this damage type")
            rec_parts.append(f"Prioritize survivability: level HP to {base.recommended_level + 10}+")
            if base.key_moves:
                rec_parts.append(f"Learn to dodge: {base.key_moves[0]}")
            rec_parts.append("Keep distance and wait for safe punish windows")
            loadout = [f"{r} resistance talisman/ring" for r in base.resistances[:2]] if base.resistances else ["HP-boosting talisman"]
            key_advice = "Patience wins. One extra roll is better than one extra hit."

        elif focus == "efficiency and speed":
            rec_parts.append(f"Use {base.weaknesses[0] if base.weaknesses else 'highest DPS'} setup for fastest kill")
            if len(base.phases) > 1:
                rec_parts.append(f"Phase 2 skip strats: burst damage at 60% HP to skip transition")
            rec_parts.append("Optimize flask allocation — more damage flasks, less healing")
            loadout = ["Burst damage weapon", "Damage buff items", "Attack boosting talismans"]
            key_advice = "Kill them before they kill you. Max DPS."

        elif focus == "mechanics and lore":
            if base.key_moves:
                for i, move in enumerate(base.key_moves[:2]):
                    rec_parts.append(f"Move #{i+1}: {move}")
            if base.phase_strategies:
                for phase, strat in base.phase_strategies.items():
                    if strat:
                        rec_parts.append(f"{phase.replace('_', ' ').title()}: {strat}")
            rec_parts.append(f"Boss has {base.phases} phase(s) — adjust strategy at each transition")
            loadout = ["Mechanically-focused build", "Practice tool: summon sign for co-op learning"]
            key_advice = "Understanding the moveset is more important than stats."

        elif focus == "loadout and preparation":
            for tip in base.loadout_tips[:3]:
                rec_parts.append(tip)
            rec_parts.append(f"Recommended level: {base.recommended_level}")
            if base.weaknesses:
                rec_parts.append(f"Stock up on {base.weaknesses[0]} consumables")
            loadout = base.loadout_tips[:4]
            key_advice = "Proper preparation prevents poor performance."

        elif focus == "adaptability":
            if base.weaknesses and base.resistances:
                rec_parts.append(f"Hybrid setup: exploit {base.weaknesses[0]}, resist {base.resistances[0]}")
            rec_parts.append("Keep a ranged option for specific phases")
            rec_parts.append("Have a backup weapon with different damage type")
            loadout = ["Versatile weapon (quality build)", "Range option", "Healing items"]
            key_advice = "Adapt to the situation. If one approach fails, try another."

        elif focus == "experience and patterns":
            if base.key_moves:
                rec_parts.append(f"Pattern to learn: {base.key_moves[0]}")
            rec_parts.append(f"This boss type appears in other {base.game} fights — transfer your skills")
            rec_parts.append("Watch the boss's body language, not the weapon")
            loadout = ["Consistent damage weapon (no gimmicks)", "Stamina management items"]
            key_advice = "Pattern recognition > reaction time. Predict, don't react."

        return AgentVote(
            agent_name=agent["name"],
            agent_focus=agent["focus"],
            recommendation=". ".join(rec_parts) if rec_parts else "Standard approach recommended.",
            confidence=round(confidence, 2),
            loadout_suggestion=loadout,
            key_advice=key_advice,
        )

    def _extract_top_recommendations(self, votes: list[AgentVote]) -> list[str]:
        sorted_votes = sorted(votes, key=lambda v: v.confidence, reverse=True)
        recs = []
        for v in sorted_votes[:3]:
            short = v.recommendation[:120].rsplit(".", 1)[0] if "." in v.recommendation else v.recommendation[:120]
            recs.append(f"{v.agent_name}: {short}")
        return recs

    def _build_consensus_loadout(self, votes: list[AgentVote]) -> list[str]:
        all_items = []
        for v in votes:
            all_items.extend(v.loadout_suggestion)
        from collections import Counter
        item_counts = Counter(all_items)
        return [item for item, count in item_counts.most_common(6)]

    def _calculate_agreement(self, votes: list[AgentVote]) -> float:
        if len(votes) < 2:
            return 1.0
        confs = [v.confidence for v in votes]
        mean = sum(confs) / len(confs)
        variance = sum((c - mean) ** 2 for c in confs) / len(confs)
        agreement = 1.0 - min(1.0, variance * 2)
        return max(0.0, agreement)
