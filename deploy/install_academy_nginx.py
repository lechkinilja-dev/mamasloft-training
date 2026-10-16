#!/usr/bin/env python3
"""Replace only the final academy vhost while preserving bind-mount inode."""

from __future__ import annotations

import argparse
from pathlib import Path


MARKER = "# academy.analytics-mamasloft.ru — employee training platform"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--active", type=Path, required=True)
    parser.add_argument("--academy", type=Path, required=True)
    args = parser.parse_args()

    active = args.active.read_text(encoding="utf-8")
    academy = args.academy.read_text(encoding="utf-8").strip() + "\n"
    if active.count(MARKER) != 1:
        raise RuntimeError("expected exactly one academy marker in active config")
    if not academy.startswith(MARKER):
        raise RuntimeError("academy config does not start with the expected marker")

    prefix, _ = active.split(MARKER, 1)
    inode_before = args.active.stat().st_ino
    with args.active.open("w", encoding="utf-8") as handle:
        handle.write(prefix.rstrip() + "\n\n" + academy)
    inode_after = args.active.stat().st_ino
    if inode_before != inode_after:
        raise RuntimeError("active config inode changed")
    print(f"academy vhost updated; inode={inode_after}")


if __name__ == "__main__":
    main()
