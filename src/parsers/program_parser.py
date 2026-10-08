import json
import re
from datetime import datetime
from pathlib import Path

PROGRAMS_FOLDER = Path("data/processed/programs")
OUTPUT_FOLDER = Path("data/structured/programs")

MONTHS = {
    "JANVIER": 1, "FEVRIER": 2, "FÉVRIER": 2, "MARS": 3,
    "AVRIL": 4, "MAI": 5, "JUIN": 6, "JUILLET": 7,
    "AOUT": 8, "AOÛT": 8, "SEPTEMBRE": 9, "OCTOBRE": 10, "NOVEMBRE": 11,
    "DECEMBRE": 12, "DÉCEMBRE": 12,
}


def clean_text(text):
    text = text.replace("\u202f", " ").replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def extract_date(text):
    """Extract the current race date from the newspaper header before old results."""
    header = text
    months = r"(JANVIER|FEVRIER|FÉVRIER|MARS|AVRIL|MAI|JUIN|JUILLET|AOUT|AOÛT|SEPTEMBRE|OCTOBRE|NOVEMBRE|DECEMBRE|DÉCEMBRE)"
    patterns = [
        r'(?:["“]?(?:4\+1|QUARTE|TIERCE)["”]?\s+DU\s+)(?:LUNDI|MARDI|MERCREDI|JEUDI|VENDREDI|SAMEDI|DIMANCHE)\s+(\d{1,2})\s+' + months + r'\s+(20\d{2})\b',
        r'(?:LUNDI|MARDI|MERCREDI|JEUDI|VENDREDI|SAMEDI|DIMANCHE)\s+(\d{1,2})\s+' + months + r'\s+(20\d{2})\b',
    ]
    for pattern in patterns:
        match = re.search(pattern, header, re.IGNORECASE)
        if match:
            try:
                day, month_name, year = int(match.group(1)), match.group(2).upper(), int(match.group(3))
                return datetime(year, MONTHS[month_name], day).date().isoformat()
            except (KeyError, ValueError):
                pass
    fallback = re.search(r'(\d{1,2})\s+' + months + r'\s+(20\d{2})\b', header, re.IGNORECASE)
    if fallback:
        try:
            day, month_name, year = int(fallback.group(1)), fallback.group(2).upper(), int(fallback.group(3))
            return datetime(year, MONTHS[month_name], day).date().isoformat()
        except (KeyError, ValueError):
            pass
    return None


def extract_race_info(text):
    race = {
        "race_name": None,
        "track": None,
        "race_number": None,
        "race_type": None,
        "runners_count": None,
        "distance": None,
        "prize_euros": None,
    }

    # LONAB/PMU-B uses more than one race-name convention, including
    # CRITERIUM DES 5 ANS and SUPER HANDICAP DE LA RENTREE. Anchor the match
    # to the runner-count line instead of requiring the literal word PRIX.
    header_match = re.search(
        r"(?m)^\s*(?P<track>[A-ZÀ-Ü][A-ZÀ-Ü0-9'’ .\-]{2,})\s+-\s+"
        r"(?P<race_name>[A-ZÀ-Ü0-9'’ .\-]{2,}?)\s*\n\s*"
        r"(?P<runners>\d+)\s+CONCURRENTS?\b",
        text,
        re.IGNORECASE,
    )
    if header_match:
        race["track"] = re.sub(r"\s+", " ", header_match.group("track")).strip().upper()
        race["race_name"] = re.sub(r"\s+", " ", header_match.group("race_name")).strip().upper()
        race["runners_count"] = int(header_match.group("runners"))
    else:
        match = re.search(
            r"([A-ZÀ-Ü][A-ZÀ-Ü0-9'’ .\-]{2,}?)\s*-\s*(PRIX\s+[A-ZÀ-Ü0-9'’ .\-]{2,})",
            text,
            re.IGNORECASE,
        )
        if match:
            race["track"] = re.sub(r"\s+", " ", match.group(1)).strip().upper()
            race["race_name"] = re.sub(r"\s+", " ", match.group(2)).strip().upper()

        match = re.search(r"(\d+)\s+CONCURRENTS?", text, re.IGNORECASE)
        if match:
            race["runners_count"] = int(match.group(1))

    for pattern in (
        r"(\d+)\s*(?:ère|ere|ème|eme|ER|E|EME|ÈME)\s+COURSE",
        r"(\d+)\s*COURSE",
    ):
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            race["race_number"] = int(match.group(1))
            break

    for race_type in ("STEEPLE-CHASE", "ATTELE", "MONTÉ", "MONTE", "PLAT", "OBSTACLE", "HAIES"):
        if re.search(rf"\b{re.escape(race_type)}\b", text, re.IGNORECASE):
            race["race_type"] = race_type
            break

    match = re.search(r"(\d[\d\s]*)\s+EUROS", text, re.IGNORECASE)
    if match:
        try:
            race["prize_euros"] = int(re.sub(r"\s+", "", match.group(1)))
        except ValueError:
            pass

    # Prefer the distance nearest the structured race header. Commentary can
    # contain unrelated "METRES" values, so never trust the first occurrence.
    header_end = header_match.end() if header_match else 0
    distance_matches = list(re.finditer(r"(\d[\d\s]*)\s+METRES?", text, re.IGNORECASE))
    candidates = []
    for match in distance_matches:
        try:
            value = int(re.sub(r"\s+", "", match.group(1)))
        except ValueError:
            continue
        if 800 <= value <= 7000:
            candidates.append((abs(match.start()-header_end), value))
    if candidates:
        candidates.sort(key=lambda item:item[0])
        race["distance"] = candidates[0][1]

    return race


def clean_horse_name(name):
    return re.sub(r"\s+", " ", name.strip())


def clean_description(description):
    return re.sub(r"\s+", " ", description).strip()


def extract_horses(text, expected_runners=None):
    """Extract horse descriptions from the complete program document."""
    horse_pattern = re.compile(
        r"(?m)^\s*(\d{1,2})\s*-\s*"
        r"([A-ZÀ-Ü0-9][A-ZÀ-Ü0-9'’\.\- ]+?)\s*:\s*"
    )
    matches = list(horse_pattern.finditer(text))
    horses_by_number = {}

    tail_markers = (
        "JOURNAL HIPPIQUE",
        "LES MEILLEURS DE LA SEMAINE",
        "PMU’B...",
        "PMU'B...",
        "RESULTATS DES COURSES",
        "RÉSULTATS DES COURSES",
        "ARRIVEE DU",
        "ARRIVÉE DU",
    )
    tail_positions = [text.upper().find(marker.upper()) for marker in tail_markers]
    tail_positions = [p for p in tail_positions if p != -1]
    tail_end = min(tail_positions) if tail_positions else len(text)

    for index, match in enumerate(matches):
        number = int(match.group(1))
        if expected_runners is not None and not (1 <= number <= expected_runners):
            continue

        name = clean_horse_name(match.group(2))
        description_start = match.end()
        next_start = matches[index + 1].start() if index + 1 < len(matches) else tail_end
        description_end = max(description_start, min(next_start, tail_end))
        description = clean_description(text[description_start:description_end])

        candidate = {
            "number": number,
            "horse": name,
            "description": description,
        }
        existing = horses_by_number.get(number)
        if existing is None or len(candidate["description"]) > len(existing["description"]):
            horses_by_number[number] = candidate

    horses = sorted(horses_by_number.values(), key=lambda item: item["number"])
    if expected_runners is not None and len(horses) != expected_runners:
        print(
            "WARNING: horse count mismatch: "
            f"expected {expected_runners}, extracted {len(horses)}"
        )
    return horses



def _clean_table_line(line):
    line = line.replace("\u202f", " ").replace("\xa0", " ")
    line = re.sub(r"\s+", " ", line).strip()
    return line


def _is_sex_age_block(lines, expected):
    return len(lines) == expected and all(
        re.fullmatch(r"[HFM]\.?\d{1,2}", line, re.IGNORECASE) for line in lines
    )


def _is_integer_block(lines, expected):
    if len(lines) != expected:
        return False
    values = []
    for line in lines:
        if not re.fullmatch(r"\d{1,3}", line):
            return False
        values.append(int(line))
    return all(1 <= value <= expected for value in values)


def _is_weight_block(lines, expected):
    if len(lines) != expected:
        return False
    return all(
        re.fullmatch(r"\d+(?:[.,]\d+)?\s*\.?\s*KG", line, re.IGNORECASE)
        for line in lines
    )


def _is_distance_block(lines, expected):
    if len(lines) != expected:
        return False
    return all(
        re.fullmatch(r"\d+(?:\s+\d+)*\.?[A-Z]?", line, re.IGNORECASE)
        and "." in line
        for line in lines
    )


def _is_chrono_block(lines, expected):
    if len(lines) != expected:
        return False
    return all(re.fullmatch(r"\d+(?:\.\d+){2,3}", line) for line in lines)


def _is_performance_block(lines, expected):
    if len(lines) != expected:
        return False
    return all(
        re.fullmatch(r"[0-9A-Z]+(?:\.[0-9A-Z]+){2,6}", line, re.IGNORECASE)
        for line in lines
    )


def _is_gains_block(lines, expected):
    if len(lines) != expected:
        return False
    return all(re.fullmatch(r"\d[\d ]*", line) for line in lines)


def _split_sex_age(value):
    match = re.fullmatch(r"([HFM])\.?([0-9]{1,2})", value or "", re.IGNORECASE)
    if not match:
        return None, None
    return match.group(1).upper(), int(match.group(2))


def _parse_weight(value):
    match = re.search(r"(\d+(?:[.,]\d+)?)", value or "")
    if not match:
        return None
    try:
        return float(match.group(1).replace(",", "."))
    except ValueError:
        return None


def _parse_numeric_gain(value):
    try:
        return int(re.sub(r"\s+", "", value))
    except (TypeError, ValueError):
        return None


def extract_program_table_fields(text, horses, expected_runners=None):
    """Extract pre-race runner fields from the LONAB table only.

    The PDF text extractor emits the table as aligned column blocks. We first
    anchor on the exact ordered horse-name block already recovered from the
    runner descriptions, then map surrounding fixed-width blocks. A field is
    promoted only when its full runner-length block matches the expected
    grammar.
    """
    expected = int(expected_runners or len(horses) or 0)
    if expected <= 0 or len(horses) != expected:
        return {"status": "unmapped", "fields": {}}

    names = [_clean_table_line(h.get("horse", "")) for h in horses]
    if any(not name for name in names):
        return {"status": "unmapped", "fields": {}}

    lines = [_clean_table_line(line) for line in text.splitlines()]
    lines = [line for line in lines if line]

    horse_start = None
    for idx in range(len(lines) - expected + 1):
        if lines[idx:idx + expected] == names:
            horse_start = idx
            break
    if horse_start is None:
        return {"status": "unmapped", "fields": {}}

    before = lines[:horse_start]
    after = lines[horse_start + expected:]

    def take_before(cursor, predicate):
        start = cursor - expected
        if start < 0:
            return None, cursor
        block = before[start:cursor]
        if predicate(block, expected):
            return block, start
        return None, cursor

    cursor = len(before)
    gains, cursor = take_before(cursor, _is_gains_block)
    if gains is None:
        return {"status": "unmapped", "fields": {}}

    performance, cursor = take_before(cursor, _is_performance_block)
    if performance is None:
        return {"status": "unmapped", "fields": {}}

    optional = {}
    for label, predicate in (
        ("weight", _is_weight_block),
        ("draw", _is_integer_block),
        ("chrono", _is_chrono_block),
        ("distance_listed", _is_distance_block),
    ):
        block, next_cursor = take_before(cursor, predicate)
        if block is not None:
            optional[label] = block
            cursor = next_cursor

    sex_age, next_cursor = take_before(cursor, _is_sex_age_block)
    if sex_age is None:
        return {"status": "unmapped", "fields": {}}
    cursor = next_cursor

    number_block = before[max(0, cursor - expected):cursor]
    if number_block != [str(n) for n in range(1, expected + 1)] and number_block != [f"{n:02d}" for n in range(1, expected + 1)]:
        return {"status": "unmapped", "fields": {}}

    if len(after) < expected * 3:
        return {"status": "unmapped", "fields": {}}
    trainer = after[:expected]
    driver = after[expected:expected * 2]
    owner = after[expected * 2:expected * 3]

    if any(not value or value in {"CHEVAUX", "DRIVERS", "ENTRAINEURS", "PROPRIETAIRES"} for value in trainer + driver + owner):
        return {"status": "unmapped", "fields": {}}

    fields = {}
    for idx, horse in enumerate(horses):
        number = int(horse["number"])
        sex, age = _split_sex_age(sex_age[idx])
        row = {
            "sex": sex,
            "age": age,
            "performance": performance[idx],
            "gains": _parse_numeric_gain(gains[idx]),
            "trainer": trainer[idx],
            "jockey": driver[idx],
            "driver": driver[idx],
            "owner": owner[idx],
        }
        if "weight" in optional:
            row["weight"] = _parse_weight(optional["weight"][idx])
        if "draw" in optional:
            row["draw"] = int(optional["draw"][idx])
        if "chrono" in optional:
            row["listed_chrono"] = optional["chrono"][idx]
        if "distance_listed" in optional:
            row["listed_distance"] = optional["distance_listed"][idx]
        fields[number] = row

    return {"status": "mapped", "fields": fields}

def extract_number_list(text, label):
    match = re.search(rf"{re.escape(label)}\s*:\s*([^\n\r]+)", text, re.IGNORECASE)
    if not match:
        return []
    return [int(value) for value in re.findall(r"\b\d{1,2}\b", match.group(1))]


FRACTIONAL_ODDS_RE = re.compile(r"\b(\d+(?:[.,]\d+)?)/(\d+(?:[.,]\d+)?)\b")


def _parse_fractional_odds(token: str):
    try:
        numerator, denominator = token.split("/", 1)
        value_num = float(numerator.replace(",", "."))
        value_den = float(denominator.replace(",", "."))
        # LONAB program tables observed in the source PDFs use whole-number
        # fractional prices in N/1 form. Other denominators can be produced by
        # PDF column concatenation (for example 5/116) and are rejected.
        if value_den != 1.0 or value_num < 1.0 or value_num > 200.0:
            return None
        decimal = 1.0 + value_num
        if decimal <= 1.0:
            return None
        return round(decimal, 6)
    except (TypeError, ValueError):
        return None


def _extract_press_odds_series(text, start_pattern, stop_pattern, expected_runners):
    """Extract explicit fractional press odds from a program table.

    These are published press prices (Paris Turf / Tierce Magazine), not
    operator/tote odds. They are retained separately so the economic gate
    cannot mistake them for independent market-price evidence.
    """
    if not expected_runners or expected_runners <= 0:
        return {}
    start = re.search(start_pattern, text, re.IGNORECASE)
    if not start:
        return {}
    tail = text[start.end():]
    stop = re.search(stop_pattern, tail, re.IGNORECASE)
    segment = tail[:stop.start()] if stop else tail

    values = []
    for match in FRACTIONAL_ODDS_RE.finditer(segment):
        token = match.group(0)
        decimal = _parse_fractional_odds(token)
        if decimal is None:
            continue
        values.append({"fractional": token, "decimal": decimal})
        if len(values) >= expected_runners:
            break

    if len(values) != expected_runners:
        return {}
    return {str(number): value for number, value in enumerate(values, start=1)}


def extract_press_odds(text, expected_runners=None):
    """Extract the two published press-odds columns when present."""
    expected = int(expected_runners or 0)
    if expected <= 0:
        return {}

    paris_turf = _extract_press_odds_series(
        text,
        r"\bPARIS\s*TURF\b",
        r"\bTIERCE\s*MAGAZINE\b",
        expected,
    )
    tierce_magazine = _extract_press_odds_series(
        text,
        r"\bTIERCE\s*MAGAZINE\b",
        r"\bTURF[- ]FR\.COM\b|\bAPTITUDES\b|\bCLASSEMENT\b",
        expected,
    )

    result = {}
    if paris_turf:
        result["paris_turf"] = paris_turf
    if tierce_magazine:
        result["tierce_magazine"] = tierce_magazine
    return result


def extract_rankings(text):
    return {
        "favorites": extract_number_list(text, "FAVORIS"),
        "form": extract_number_list(text, "FORME"),
        "class": extract_number_list(text, "CLASSE"),
        "progress": extract_number_list(text, "PROGRES"),
        "regularity": extract_number_list(text, "REGULARITE"),
    }


def extract_published_arrival(text):
    match = re.search(r"ARRIVEE\s+DU.*?:\s*([0-9\s\-–]+)(?:NPO|NP|$)", text, re.IGNORECASE)
    if not match:
        return []
    return [int(value) for value in re.findall(r"\d+", match.group(1))]


def parse_program_text(text, source_file="unknown.txt"):
    text = clean_text(text)
    race_info = extract_race_info(text)
    horses = extract_horses(text, expected_runners=race_info.get("runners_count"))
    table = extract_program_table_fields(
        text,
        horses,
        expected_runners=race_info.get("runners_count"),
    )
    for horse in horses:
        horse.update(table["fields"].get(int(horse["number"]), {}))
    return {
        "document_type": "program",
        "source_file": source_file,
        "parsed_at": datetime.utcnow().isoformat() + "Z",
        "date": extract_date(text),
        "race": race_info,
        "horses": horses,
        "program_table_mapping_status": table["status"],
        "rankings": extract_rankings(text),
        "press_odds": extract_press_odds(text, race_info.get("runners_count")),
        "press_odds_status": "observed_in_program" if extract_press_odds(text, race_info.get("runners_count")) else "unavailable",
        "published_arrival": extract_published_arrival(text),
    }


def parse_program_file(file_path):
    raw_text = file_path.read_text(encoding="utf-8")
    return parse_program_text(raw_text, file_path.name)


def process_all_programs():
    OUTPUT_FOLDER.mkdir(parents=True, exist_ok=True)
    files = sorted(PROGRAMS_FOLDER.glob("*.txt"))

    print("\n" + "=" * 60)
    print("PARSING PROGRAM FILES")
    print("=" * 60)
    print(f"Program files found: {len(files)}")

    success_count = 0
    failed_count = 0

    for file_path in files:
        try:
            data = parse_program_file(file_path)
            output_path = OUTPUT_FOLDER / f"{file_path.stem}.json"
            output_path.write_text(
                json.dumps(data, ensure_ascii=False, indent=4),
                encoding="utf-8",
            )
            print(f"Parsed successfully: {file_path.name}")
            print(f"Horses extracted: {len(data['horses'])}")
            success_count += 1
        except Exception as error:
            print(f"Failed: {file_path.name}")
            print(f"Error: {error}")
            failed_count += 1

    print("\n" + "=" * 60)
    print(f"Programs parsed: {success_count}")
    print(f"Failures: {failed_count}")
    print("=" * 60)


if __name__ == "__main__":
    process_all_programs()
