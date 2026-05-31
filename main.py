import asyncio
import sys
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from src.orchestrator import GameAssistOrchestrator
from src.api.server import run as run_api

logger = logging.getLogger(__name__)


async def interactive_cli():
    orch = GameAssistOrchestrator()

    print("=" * 60)
    print("  STREAMBUDDY v2.3 - AI Game Assistant")
    print("  Voice + Gameplay + Strategy Swarm + Multi-Platform")
    print("=" * 60)
    print()
    print("Commands:")
    print("  /voice [sec]    - Record voice (default 5 seconds)")
    print("  /query <text>   - Ask a text question")
    print("  /game <name>    - Set current game")
    print("  /boss <name>    - Get strategy swarm analysis for a boss")
    print("  /swarm <boss>   - Run full swarm intelligence on a boss")
    print("  /history        - Show session history")
    print("  /api            - Start API server")
    print("  /twitch <chan>  - Start Twitch chat monitor")
    print("  /youtube <boss> - Find YouTube guide for a boss")
    print("  /lang           - Detect language of last query")
    print("  /webhook <url>  - Register a notification webhook")
    print("  /quit           - Exit")
    print()

    while True:
        try:
            cmd = input("\n> ").strip()
            if not cmd:
                continue

            if cmd == "/quit":
                break
            elif cmd == "/api":
                print("\nStarting API server on http://localhost:8080\n")
                run_api()
                break
            elif cmd == "/history":
                for i, h in enumerate(orch.session_history[-10:], 1):
                    print(f"\n  [{i}] Q: {h.query}")
                    print(f"      Game: {h.game or 'unknown'}")
                    print(f"      Answer: {h.answer[:100]}...")
                continue
            elif cmd.startswith("/voice"):
                parts = cmd.split()
                duration = float(parts[1]) if len(parts) > 1 else 5.0
                print(f"\nRecording {duration}s...")
                result = await orch.process_voice_command(duration=duration)
                if result.voice_text:
                    print(f"\nHeard: \"{result.voice_text}\"")
                if result.answer:
                    print(f"\n{result.answer[:300]}")
            elif cmd.startswith("/boss"):
                boss_name = cmd[6:].strip()
                if boss_name:
                    print(f"\nAnalyzing {boss_name} with Strategy Swarm...")
                    swarm = orch.analyze_boss_strategy(boss_name)
                    if swarm:
                        print(f"\n  🧠 Swarm Analysis for {swarm.boss} ({swarm.game})")
                        print(f"  Agreement: {swarm.agreement_level * 100:.0f}%")
                        print(f"  Confidence: {swarm.swarm_confidence * 100:.0f}%")
                        print(f"\n  Approach: {swarm.recommended_approach}")
                        print(f"\n  Top Recommendations:")
                        for rec in swarm.top_recommendations[:3]:
                            print(f"    • {rec}")
                        if swarm.consensus_loadout:
                            print(f"\n  Consensus Loadout:")
                            for item in swarm.consensus_loadout[:5]:
                                print(f"    • {item}")
                    else:
                        print(f"\n  No strategy data for '{boss_name}'")
                else:
                    print("Usage: /boss <boss name>")
            elif cmd.startswith("/swarm"):
                boss_name = cmd[7:].strip()
                if boss_name:
                    print(f"\nRunning full swarm on {boss_name}...")
                    swarm = orch.analyze_boss_strategy(boss_name)
                    if swarm:
                        print(f"\n  🧠 Full Swarm Report for {swarm.boss}")
                        for v in swarm.votes:
                            print(f"\n  [{v.agent_name}] ({v.agent_focus})")
                            print(f"    Confidence: {v.confidence * 100:.0f}%")
                            print(f"    Advice: {v.key_advice}")
                            print(f"    Recommendation: {v.recommendation[:200]}")
                    else:
                        print(f"\n  No swarm data for '{boss_name}'")
                else:
                    print("Usage: /swarm <boss name>")
            elif cmd.startswith("/youtube"):
                boss_name = cmd[9:].strip()
                if boss_name:
                    print(f"\nSearching YouTube for {boss_name} guides...")
                    guide = await orch.find_youtube_guide(boss_name)
                    if guide:
                        print(f"\n  Found: {guide['title']}")
                        print(f"  Channel: {guide['channel']}")
                        print(f"  URL: {guide['url']}")
                    else:
                        print(f"\n  No YouTube guide found for '{boss_name}'")
                else:
                    print("Usage: /youtube <boss name>")
            elif cmd == "/lang":
                print(f"\n  Current language: {orch.current_language}")
            elif cmd.startswith("/webhook"):
                parts = cmd.split(maxsplit=1)
                if len(parts) > 1:
                    from src.notifications.webhook import WebhookNotifier
                    notifier = WebhookNotifier()
                    notifier.register_webhook("cli", parts[1])
                    result = await notifier.send_discord(parts[1], "STREAMBUDDY connected via CLI", "CLI Test")
                    print(f"\n  Webhook test: {'success' if result else 'failed'}")
                else:
                    print("Usage: /webhook <url>")
            elif cmd.startswith("/twitch"):
                channel = cmd[8:].strip()
                if channel:
                    from src.twitch import TwitchStreamIntegration
                    tw = TwitchStreamIntegration()
                    tw.orch = orch
                    asyncio.create_task(tw.monitor_chat(channel))
                    print(f"\nTwitch monitor started for #{channel}")
                else:
                    print("Usage: /twitch <channel>")
            elif cmd.startswith("/game"):
                game = cmd[6:].strip()
                if game:
                    orch.current_game = game
                    print(f"\nCurrent game: {game}")
                else:
                    print(f"\nCurrent game: {orch.current_game or 'not set'}")
            elif cmd.startswith("/query"):
                query = cmd[7:].strip()
                if query:
                    print(f"\nSearching...")
                    result = await orch.process_text_query(query)
                    print(f"\nGame: {result.game or 'unknown'}")
                    print(f"Answer:\n{result.answer[:500]}")
                else:
                    print("Usage: /query <question>")
            else:
                print(f"\nSearching...")
                result = await orch.process_text_query(cmd)
                print(f"\nGame: {result.game or 'unknown'}")
                print(f"Answer:\n{result.answer[:500]}")

        except KeyboardInterrupt:
            print("\nExiting...")
            break
        except Exception as e:
            logger.error(f"Error: {e}", exc_info=True)
            print(f"Error: {e}")


def main():
    if "--api" in sys.argv:
        run_api()
    else:
        asyncio.run(interactive_cli())


if __name__ == "__main__":
    main()
