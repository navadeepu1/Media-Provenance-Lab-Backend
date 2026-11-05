"""Deterministic incident grouping and sequence matching."""

from __future__ import annotations

import json
import uuid
from datetime import timedelta
from pathlib import Path

from .models import Finding, NormalizedEvent

SEQUENCES = json.loads((Path(__file__).parent / "sequences.json").read_text(encoding="utf-8"))


def group_incidents(events: list[NormalizedEvent], findings: list[Finding]) -> list[dict]:
    ordered = sorted(events, key=lambda event: (event.timestamp_utc, event.id))
    groups: list[list[NormalizedEvent]] = []
    for event in ordered:
        matching = next(
            (group for group in groups if event.timestamp_utc - group[-1].timestamp_utc <= timedelta(minutes=30)
             and ({event.actor, event.host} & {item.actor for item in group} | {item.host for item in group})),
            None,
        )
        if matching:
            matching.append(event)
        else:
            groups.append([event])
    return [{
        "id": f"incident-{uuid.uuid4().hex}",
        "start": group[0].timestamp_utc.isoformat(),
        "end": group[-1].timestamp_utc.isoformat(),
        "actors": sorted({item.actor for item in group if item.actor}),
        "hosts": sorted({item.host for item in group if item.host}),
        "sources": sorted({item.source_type for item in group}),
        "finding_ids": sorted({finding.id for finding in findings if set(finding.event_ids) & {item.id for item in group}}),
        "event_ids": [item.id for item in group],
    } for group in groups]


def match_sequences(events: list[NormalizedEvent]) -> list[Finding]:
    ordered = sorted(events, key=lambda event: (event.timestamp_utc, event.id))
    findings: list[Finding] = []
    for sequence in SEQUENCES:
        steps = sequence["steps"]
        for start_index, first in enumerate(ordered):
            if first.action.value != steps[0]["action"]:
                continue
            matched = [first]
            gaps = []
            cursor = start_index
            for step in steps[1:]:
                candidate = next((
                    event for event in ordered[cursor + 1:]
                    if (event.actor == first.actor or event.host == first.host)
                    and event.action.value in ([step["action"]] if isinstance(step["action"], str) else step["action"])
                ), None)
                if not candidate or candidate.timestamp_utc - matched[-1].timestamp_utc > timedelta(minutes=step["max_gap_minutes"]):
                    matched = []
                    break
                gaps.append(round((candidate.timestamp_utc - matched[-1].timestamp_utc).total_seconds() / 60, 2))
                matched.append(candidate)
                cursor = ordered.index(candidate)
            if not matched:
                continue
            findings.append(Finding(
                id=f"SEQ-{uuid.uuid4().hex}", tenant_id=first.tenant_id, case_id=first.case_id,
                rule_id=sequence["id"], title=sequence["title"], severity="high", confidence=0.8,
                event_ids=[event.id for event in matched], actor=first.actor, host=first.host,
                window_start=matched[0].timestamp_utc, window_end=matched[-1].timestamp_utc,
                explanation=f"Possible sequence matched with gaps of {gaps} minutes.",
                limitations=["This is deterministic time-window grouping, not statistical clustering."],
            ))
    return findings
