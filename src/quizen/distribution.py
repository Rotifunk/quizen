"""Utilities to distribute questions across PARTs."""
from __future__ import annotations

from typing import Dict, List

from .models import Part, Question


def minimum_distribution(total_questions: int, parts: List[Part]) -> Dict[str, int]:
    """Distribute minimum counts using floor division and remainder round-robin."""
    if total_questions <= 0 or not parts:
        return {}
    base = total_questions // len(parts)
    remainder = total_questions % len(parts)
    allocation = {part.part_name: base for part in parts}
    for idx in range(remainder):
        allocation[parts[idx].part_name] += 1
    return allocation


def rebalance_questions(questions: List[Question], parts: List[Part]) -> List[Question]:
    """Re-assign part_name to satisfy minimum distribution order when needed."""
    if not questions or not parts:
        return questions

    target = minimum_distribution(len(questions), parts)
    per_part: Dict[str, List[Question]] = {part.part_name: [] for part in parts}
    overflow: List[Question] = []

    for q in questions:
        if q.part_name in per_part and len(per_part[q.part_name]) < target[q.part_name]:
            per_part[q.part_name].append(q)
        else:
            overflow.append(q)

    # Fill shortfalls with overflow questions
    for part in parts:
        needed = target[part.part_name] - len(per_part[part.part_name])
        if needed > 0:
            per_part[part.part_name].extend(overflow[:needed])
            overflow = overflow[needed:]

    balanced: List[Question] = []
    for part in parts:
        balanced.extend(per_part[part.part_name])
    balanced.extend(overflow)
    return balanced
