from datetime import (
    datetime,
    timezone,
)

from src.ingestion.lonab_collector import (
    LonabCollector,
)

from src.notification.telegram_bot import (
    telegram_bot,
)


def run_machine():

    started_at = datetime.now(
        timezone.utc
    )

    print("=" * 60)
    print(
        "RACE MACHINE AUTOPILOT STARTED"
    )
    print(
        f"UTC TIME: "
        f"{started_at.isoformat()}"
    )
    print("=" * 60)

    try:

        collector = LonabCollector()

        collected = (
            collector.collect(
                pages=2
            )
        )

        print(
            f"Documents collected: "
            f"{len(collected)}"
        )

        programs = [
            item
            for item in collected
            if item["post_type"]
            == "program"
        ]

        results = [
            item
            for item in collected
            if item["post_type"]
            == "result"
        ]

        message = (
            "🏇 <b>RACE MACHINE REPORT</b>\n\n"
            "Status: LONAB DATA COLLECTION COMPLETE\n\n"
            f"📄 Programs collected: "
            f"{len(programs)}\n"
            f"🏁 Results collected: "
            f"{len(results)}\n"
            f"📦 Total documents: "
            f"{len(collected)}\n\n"
            "Next stage: converting race "
            "programs and results into the "
            "machine's historical memory."
        )

        telegram_bot.send_message(
            message
        )

        print(
            "Collection completed."
        )

    except Exception as error:

        error_message = (
            f"Machine error: {error}"
        )

        print(
            error_message
        )

        telegram_bot.send_message(
            "⚠️ <b>RACE MACHINE ERROR</b>\n\n"
            f"{error_message}"
        )


if __name__ == "__main__":
    run_machine()
