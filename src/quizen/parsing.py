"""Filename parsing helpers for Drive SRT inputs."""
from __future__ import annotations

import re
from pathlib import Path
from typing import List, Tuple

from .models import Lecture

FILENAME_PATTERN = re.compile(r"^(?P<order>\d{3})\s+(?P<id>\w+)\s+(?P<title>.+)\.srt$")


def parse_filename(path: Path) -> Tuple[Lecture, List[str]]:
    """Parse a single SRT filename into Lecture; returns lecture and warnings."""
    warnings: List[str] = []
    match = FILENAME_PATTERN.match(path.name)
    if not match:
        warnings.append(f"Filename does not match expected pattern: {path.name}")
        # Fallback using stem as title when parsing fails
        lecture = Lecture(order="", id=path.stem, title=path.stem, file_path=str(path))
        return lecture, warnings

    lecture = Lecture(
        order=match.group("order"),
        id=match.group("id"),
        title=match.group("title"),
        file_path=str(path),
    )
    return lecture, warnings


def parse_course_folder(folder: Path) -> Tuple[List[Lecture], List[str]]:
    """Scan folder for SRT files and parse metadata with ordering."""
    lectures: List[Lecture] = []
    warnings: List[str] = []

    srt_files = sorted(folder.glob("*.srt"))
    for srt_file in srt_files:
        lecture, lecture_warnings = parse_filename(srt_file)
        lectures.append(lecture)
        warnings.extend(lecture_warnings)

    lectures.sort(key=lambda lec: (lec.order or "", lec.title))
    return lectures, warnings
