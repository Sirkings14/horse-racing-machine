# Market odds evidence capture

## Source review

The official LONAB PMU'B program pages provide race programs and results/dividends. We have not verified an official public, per-runner, timestamped pre-race win-odds feed from LONAB. Press estimates are not observed market prices and must never be relabelled as odds.

### Free source investigated: Open PMU API

The public Open PMU API is accessible without an API key and provides historical race results. Its documented response includes a `cotes` array and derived statistics such as minimum, maximum, average, median, and favourite rank. In the documented example, the detailed horse records are nested under `arrivee_details` and cover the official finishers, rather than a complete pre-race field. The API schema does not clearly establish the meaning and timestamp of each price in the array. Therefore this is **not sufficient for complete-field, pre-race odds evidence or a reliable strategy ROI calculation**.

We added an isolated audit tool to inspect the actual response shape for a selected date. It reports the number of detailed runner rows, whether `cotes` arrays exist, their lengths, and whether explicit timestamp fields are present. It never writes to the market-evidence ledger or interprets these values as pre-race prices.

Run from the repository root:

    python scripts/audit_open_pmu_cotes.py --date 09/29/2026

The tool needs network access to the public endpoint. A successful response only describes the API data returned for that date; it does not upgrade the data to verified pre-race evidence. The endpoint does not document a rate limit or service-level guarantee, so avoid broad repeated queries.

Documentation: https://github.com/open-pmu-api/open-pmu-api and https://open-pmu-api.vercel.app/api/arrivees

The PMU France public racecard pages display runner prices for some races, but no documented free API/feed with reliable price timestamps was verified. A browser page or scraped number alone is not sufficient proof that a price was available at the claimed pre-race time. Before automating any collection, verify applicable access terms, the odds type, update timestamp, and stable runner/course mapping.

### Paid fallback

A documented third-party option is the Turf.bzh API, which exposes PMU odds and documents an API key requirement and a lifetime licence priced at €49.90 as of 1 October 2026. This repository does not include or purchase that key. Do not enable paid collection without explicit approval. PMU France prices are a market benchmark, but they are not necessarily identical to payouts from the Burkina Faso LONAB pool.

## Snapshot schema and manual import

All timestamps must include a timezone. `price_timestamp` is when the provider says the prices were valid; `captured_at` is when the machine obtained the snapshot; both must be at or before `race_off_at`. `source_url` must point to the raw provider reference.

Example:

    {
      "race_key": "2026-10-12|AUTEUIL|1",
      "source": "provider-name",
      "source_type": "bookmaker_win",
      "market_type": "winner",
      "source_url": "https://provider.example/race/1",
      "captured_at": "2026-10-12T10:00:00Z",
      "price_timestamp": "2026-10-12T09:59:30Z",
      "race_off_at": "2026-10-12T10:15:00Z",
      "odds": {"1": 4.5, "2": 5.0}
    }

Allowed source_type values are `bookmaker_win`, `tote_win`, and `exchange_win`. Press estimates are intentionally rejected. Decimal prices must be greater than 1.0.

## Optional Turf.bzh adapter

Set `TURFBZH_API_KEY` as an environment variable or GitHub Actions secret. Never commit the key to the repository. The adapter deliberately requires an explicit provider course code, scheduled off time, and exact expected active runner-number set:

    python -m src.model.turf_bzh_odds --date 2026-10-12 --course-code R1C1 --race-key '2026-10-12|AUTEUIL|1' --race-off-at '2026-10-12T10:15:00+02:00' --runner-numbers 1,2,3

Use the real course code, real off time, and complete active runner list; the example values above are illustrative only. The adapter rejects missing keys, stale or post-off prices, wrong source/date, invalid odds, and runner-roster mismatches. It does not guess the mapping from LONAB race number to provider course code.

## Import from another verified source

From the repository root, run:

    python -m src.model.market_odds_capture path/to/snapshot.json

The importer validates provenance, timestamps, source type, race key, and decimal prices, then appends accepted snapshots to `data/evaluation/market_evidence.json`. Duplicate snapshots are not appended again.

The profitability report only counts races where every recommended runner has a valid price in a strict, verified pre-race snapshot. Legacy odds fields in prediction files, post-race historical price arrays without documented timestamps, and press estimates are not treated as adequate ROI evidence.

## Still required before profitability can be assessed

1. Verify the odds source, odds semantics, course-code mapping, and active runner-number mapping for each race.
2. Capture snapshots automatically before the race starts, preserving raw source references and reliable timestamps.
3. Capture many races, including races where prices are unavailable.
4. Match the odds market and bet type to the intended stake and the correct official payout/dividend.
5. Evaluate only chronological out-of-sample predictions. A few snapshots or a green workflow do not establish an edge.
