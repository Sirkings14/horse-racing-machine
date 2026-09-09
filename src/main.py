from datetime import datetime, timezone

from src.notification.telegram_bot import telegram_bot


def run_machine():
    """
    Main autopilot entry point.

    The later modules will be connected here in this order:

    1. Find upcoming races
    2. Collect race programs
    3. Load historical backbone
    4. Normalize race data
    5. Build performance features
    6. Find similar historical races
    7. Run strategies
    8. Backtest / score strategies
    9. Generate predictions
    10. Send report to Telegram
    """

    started_at = datetime.now(timezone.utc)

    print("=" * 60)
    print("RACE MACHINE STARTED")
    print(f"UTC TIME: {started_at.isoformat()}")
    print("=" * 60)

    message = (
        "🏇 <b>RACE MACHINE AUTOPILOT</b>\n\n"
        "Status: Running\n"
        f"Time: {started_at.strftime('%Y-%m-%d %H:%M UTC')}\n\n"
        "Machine backbone initialized successfully.\n"
        "Next stage: automatic race discovery and data collection."
    )

    telegram_bot.send_message(message)

    print("Race machine run completed.")


if __name__ == "__main__":
    run_machine()
