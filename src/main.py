from datetime import datetime, timezone

from src.ingestion.provider_factory import get_race_provider
from src.ingestion.race_discovery import RaceDiscovery
from src.notification.telegram_bot import telegram_bot


def run_machine():

    started_at = datetime.now(timezone.utc)

    print("=" * 60)
    print("RACE MACHINE AUTOPILOT STARTED")
    print(f"UTC TIME: {started_at.isoformat()}")
    print("=" * 60)

    try:

        provider = get_race_provider()

        discovery = RaceDiscovery(provider)

        next_race = discovery.get_next_race()

        if next_race is None:

            message = (
                "🏇 <b>RACE MACHINE AUTOPILOT</b>\n\n"
                "Status: No race data available.\n\n"
                "The machine is running correctly, but no race-data "
                "provider has been connected yet."
            )

            telegram_bot.send_message(message)

            return

        print("Next race found:")
        print(next_race)

        message = (
            "🏇 <b>RACE MACHINE AUTOPILOT</b>\n\n"
            "Next race discovered.\n\n"
            f"<b>Track:</b> {next_race.get('track', 'Unknown')}\n"
            f"<b>Race:</b> {next_race.get('race_name', 'Unknown')}\n"
            f"<b>Time:</b> {next_race.get('race_time', 'Unknown')}\n\n"
            "Analysis engine connection comes next."
        )

        telegram_bot.send_message(message)

    except Exception as error:

        print(f"Machine error: {error}")

        telegram_bot.send_message(
            "⚠️ <b>RACE MACHINE ERROR</b>\n\n"
            f"{str(error)}"
        )


if __name__ == "__main__":
    run_machine()
