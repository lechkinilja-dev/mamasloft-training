#!/usr/bin/env python3
"""Safely replace the employee-training topic matrix in Google Sheets.

The command is a dry run unless ``--apply`` is supplied. Before changing the
two live worksheets it creates timestamped copies, so the previous progress
matrix and summary remain recoverable.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

import gspread


SPREADSHEET_ID = "1Mj8AQqTAcwOERolWsoq0nT2usSfZ8AEOBGAiUKkmQkA"
STATUS_TITLE = "Статус обучения"
SUMMARY_TITLE = "Свод "
STAGES = ("Лекция", "Карта знаний", "Тест")
DEFAULT_CREDENTIALS = Path.home() / ".config/gcloud/mamas-loft-service-account.json"
DEFAULT_CONTENT = Path(__file__).resolve().parents[1] / "docs/content.json"


def load_topics(path: Path) -> list[str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    modules = payload.get("modules") if isinstance(payload, dict) else payload
    if not isinstance(modules, list) or not modules:
        raise ValueError("content.json does not contain a non-empty module list")

    topics: list[str] = []
    for index, module in enumerate(modules, start=1):
        if not isinstance(module, dict):
            raise ValueError(f"module {index} is not an object")
        topic = str(module.get("topic", "")).strip()
        quiz = module.get("quiz")
        if not topic:
            raise ValueError(f"module {index} has no topic")
        if not isinstance(quiz, list) or not 10 <= len(quiz) <= 15:
            raise ValueError(f"{topic}: expected 10-15 quiz questions")
        topics.append(topic)

    if len(topics) != len(set(topics)):
        raise ValueError("duplicate topic names in content.json")
    return topics


def topic_rows(topics: list[str], width: int) -> list[list[str]]:
    return [[topic, stage, *([""] * (width - 2))] for topic in topics for stage in STAGES]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--content", type=Path, default=DEFAULT_CONTENT)
    parser.add_argument("--credentials", type=Path, default=DEFAULT_CREDENTIALS)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    topics = load_topics(args.content)
    if not args.credentials.is_file():
        raise FileNotFoundError("Google service-account credentials are unavailable")

    client = gspread.service_account(filename=str(args.credentials))
    spreadsheet = client.open_by_key(SPREADSHEET_ID)
    status = spreadsheet.worksheet(STATUS_TITLE)
    summary = spreadsheet.worksheet(SUMMARY_TITLE)

    header = status.row_values(1)
    if len(header) < 3 or header[:2] != ["Тема", "Этап"]:
        raise ValueError("unexpected header on the live training-status sheet")

    current = status.get_all_values()
    old_topic_count = len({row[0].strip() for row in current[1:] if row and row[0].strip()})
    print(
        json.dumps(
            {
                "mode": "apply" if args.apply else "dry-run",
                "old_topics": old_topic_count,
                "new_topics": len(topics),
                "new_stage_rows": len(topics) * len(STAGES),
                "topics": topics,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    if not args.apply:
        return

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    status_archive = f"Архив статуса {stamp}"
    summary_archive = f"Архив свода {stamp}"
    status.duplicate(new_sheet_name=status_archive)
    summary.duplicate(new_sheet_name=summary_archive)

    last_col = gspread.utils.rowcol_to_a1(1, status.col_count).rstrip("1")
    status.batch_clear([f"A2:{last_col}{status.row_count}"])
    rows = topic_rows(topics, len(header))
    status.update(rows, range_name=f"A2:{gspread.utils.rowcol_to_a1(len(rows) + 1, len(header))}")

    summary_values = summary.get_all_values()
    reset_ranges = []
    for row_number, row in enumerate(summary_values, start=1):
        pin = row[2].strip() if len(row) > 2 else ""
        if pin.isdigit():
            reset_ranges.extend(
                [
                    {"range": f"D{row_number}", "values": [["0%"]]},
                    {"range": f"E{row_number}", "values": [["0%"]]},
                ]
            )
    if reset_ranges:
        summary.batch_update(reset_ranges)

    fresh = status.get_all_values()
    expected_pairs = [(topic, stage) for topic in topics for stage in STAGES]
    actual_pairs = [(row[0].strip(), row[1].strip()) for row in fresh[1:] if row and row[0].strip()]
    if actual_pairs != expected_pairs:
        raise RuntimeError("post-write verification failed: topic/stage rows differ")
    if any(any(cell.strip() for cell in row[2:]) for row in fresh[1:] if row and row[0].strip()):
        raise RuntimeError("post-write verification failed: new progress cells are not blank")

    print(
        json.dumps(
            {
                "ok": True,
                "status_archive": status_archive,
                "summary_archive": summary_archive,
                "active_topics": len(topics),
                "active_stage_rows": len(expected_pairs),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
