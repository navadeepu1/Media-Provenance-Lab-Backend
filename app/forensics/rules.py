"""Deterministic suspicious-activity rules for normalized events."""

from __future__ import annotations

from collections import defaultdict
from datetime import timedelta
from statistics import median
from typing import Iterable
import uuid

from .models import Action, Finding, NormalizedEvent

SEVERITIES = ("low", "medium", "high", "critical")


def _finding(rule_id: str, title: str, severity: str, confidence: float,
             events: list[NormalizedEvent], explanation: str,
             limitations: list[str] | None = None) -> Finding:
    if not events:
        raise ValueError("A finding must cite at least one event.")
    return Finding(
        id=uuid.uuid4().hex, tenant_id=events[0].tenant_id, case_id=events[0].case_id,
        rule_id=rule_id, title=title, severity=severity, confidence=confidence,
        event_ids=[event.id for event in events], actor=events[0].actor, host=events[0].host,
        window_start=events[0].timestamp_utc, window_end=events[-1].timestamp_utc,
        explanation=explanation, limitations=limitations or [],
    )


def login_burst(events: Iterable[NormalizedEvent], failure_count: int = 5,
                failure_window_minutes: int = 10, success_window_minutes: int = 5) -> list[Finding]:
    grouped: dict[tuple[str | None, str | None], list[NormalizedEvent]] = defaultdict(list)
    for event in events:
        if event.action in {Action.logon_failure, Action.logon_success}:
            grouped[(event.actor, event.host)].append(event)
    findings = []
    for (actor, host), stream in grouped.items():
        stream.sort(key=lambda item: (item.timestamp_utc, item.id))
        for index, event in enumerate(stream):
            if event.action != Action.logon_success:
                continue
            start = event.timestamp_utc - timedelta(minutes=success_window_minutes)
            preceding = [item for item in stream[:index] if start <= item.timestamp_utc < event.timestamp_utc]
            failures = [item for item in preceding if item.action == Action.logon_failure]
            if len(failures) < failure_count:
                continue
            window_start = event.timestamp_utc - timedelta(minutes=failure_window_minutes + success_window_minutes)
            cited = [item for item in stream[:index + 1] if window_start <= item.timestamp_utc <= event.timestamp_utc]
            severity = "high" if len(failures) >= 20 else "medium"
            findings.append(_finding(
                "R-LOGIN-BURST", "Repeated failed logons followed by success", severity, 0.9,
                cited, f"{len(failures)} failed logons for {actor or 'unknown actor'} on {host or 'unknown host'} preceded a successful logon within {success_window_minutes} minutes.",
                ["Counts are based only on imported events for this case."],
            ))
    return findings


def offhours(events: Iterable[NormalizedEvent], start_hour: int = 8, end_hour: int = 19) -> list[Finding]:
    return [
        _finding("R-OFFHOURS", "Successful logon outside working hours", "low", 0.8, [event],
                 f"Successful logon occurred at local-equivalent hour {event.timestamp_utc.hour:02d}, outside {start_hour:02d}:00-{end_hour:02d}:00.",
                 ["The default case timezone is UTC unless configured otherwise."])
        for event in events
        if event.action == Action.logon_success and not start_hour <= event.timestamp_utc.hour < end_hour
    ]


def privilege_escalation(events: Iterable[NormalizedEvent]) -> list[Finding]:
    ordered = sorted(events, key=lambda item: (item.timestamp_utc, item.id))
    grants: dict[str | None, list[NormalizedEvent]] = defaultdict(list)
    findings = []
    for event in ordered:
        if event.action != Action.privilege_granted:
            continue
        earlier = grants[event.actor]
        severity = "medium"
        cited = [event]
        for prior in ordered:
            if prior.timestamp_utc >= event.timestamp_utc:
                break
            if prior.action == Action.account_created and prior.actor == event.actor and event.timestamp_utc - prior.timestamp_utc <= timedelta(minutes=30):
                severity, cited = "high", [prior, event]
        if not earlier:
            findings.append(_finding("R-PRIV-ESC", "First privilege grant for actor", severity, 0.85, cited,
                                     "A privilege grant was observed without an earlier privilege grant for this actor in the case."))
        grants[event.actor].append(event)
    return findings


def delete_burst(events: Iterable[NormalizedEvent], minimum: int = 10, window_minutes: int = 15) -> list[Finding]:
    grouped: dict[str | None, list[NormalizedEvent]] = defaultdict(list)
    for event in events:
        if event.action == Action.file_delete:
            grouped[event.actor].append(event)
    findings = []
    for actor, stream in grouped.items():
        stream.sort(key=lambda item: (item.timestamp_utc, item.id))
        for index, event in enumerate(stream):
            start = event.timestamp_utc - timedelta(minutes=window_minutes)
            window = [item for item in stream[:index + 1] if item.timestamp_utc >= start]
            if len(window) >= minimum:
                findings.append(_finding("R-DELETE-BURST", "Burst of file deletions", "high", 0.9, window,
                                         f"{len(window)} file deletions by {actor or 'unknown actor'} occurred within {window_minutes} minutes.",
                                         ["The rule does not determine whether the deletions were authorized."]))
                break
    return findings


def access_burst(events: Iterable[NormalizedEvent], minimum_reads: int = 50, k: float = 3.0) -> list[Finding]:
    by_actor: dict[str | None, list[NormalizedEvent]] = defaultdict(list)
    for event in events:
        if event.action == Action.file_read:
            by_actor[event.actor].append(event)
    findings = []
    for actor, stream in by_actor.items():
        stream.sort(key=lambda item: item.timestamp_utc)
        hourly = []
        cursor = 0
        for index, event in enumerate(stream):
            while stream[cursor].timestamp_utc < event.timestamp_utc - timedelta(hours=1):
                cursor += 1
            hourly.append(index - cursor + 1)
        if not hourly:
            continue
        baseline = median(hourly)
        mad = median([abs(value - baseline) for value in hourly]) or 1
        peak = max(hourly)
        if peak >= minimum_reads and peak > baseline + k * mad:
            index = hourly.index(peak)
            findings.append(_finding("R-ACCESS-BURST", "File-read activity exceeds actor baseline", "medium", 0.75,
                                     stream[max(0, index - peak + 1):index + 1],
                                     f"{peak} file reads in one hour exceeded the actor baseline of {baseline:g} plus {k:g} MAD.",
                                     ["Baseline is calculated only from this actor's imported file-read events."]))
    return findings


def run_all(events: Iterable[NormalizedEvent]) -> list[Finding]:
    ordered = sorted(events, key=lambda item: (item.timestamp_utc, item.id))
    findings = login_burst(ordered) + offhours(ordered) + privilege_escalation(ordered) + access_burst(ordered) + delete_burst(ordered)
    return sorted(findings, key=lambda item: (item.window_start, item.rule_id, item.id))
