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
    print("  STREAMBUDDY - AI Game Assistant")
    print("  Voice + Gameplay + Internet Walkthrough Scanner")
    print("=" * 60)
    print()
    print("Commands:")
    print("  /voice [sec]    - Record voice (default 5 seconds)")
    print("  /query <text>   - Ask a text question")
    print("  /game <name>    - Set current game")
    print("  /history        - Show session history")
    print("  /api            - Start API server")
    print("  /twitch <chan>  - Start Twitch chat monitor")
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
