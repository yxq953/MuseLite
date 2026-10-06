"""Argument normalization for the Android system-calendar Agent tool."""

from __future__ import annotations

from datetime import datetime, time, timedelta
import re
from typing import Any

_DAY_WORDS = {"今天": 0, "今日": 0, "明天": 1, "后天": 2, "昨天": -1}
_TIME_RE = re.compile(r"^\s*(上午|下午|早上|晚上|凌晨)?\s*(\d{1,2})(?::(\d{1,2}))?(?:点|时)?\s*$")


def _tz():
    return datetime.now().astimezone().tzinfo


def _epoch(value: datetime) -> int:
    if value.tzinfo is None:
        value = value.replace(tzinfo=_tz())
    return int(value.timestamp() * 1000)


def _parse_time(value: Any, *, end: bool = False) -> datetime:
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(float(value) / 1000, _tz())
    text = str(value or "").strip()
    if not text:
        raise ValueError("时间不能为空")
    iso = text[:-1] + "+00:00" if text.endswith(("Z", "z")) else text
    try:
        parsed = datetime.fromisoformat(iso)
        return (parsed if parsed.tzinfo else parsed.replace(tzinfo=_tz())).astimezone(_tz())
    except ValueError:
        pass
    now = datetime.now(_tz())
    day_offset, rest = None, text
    for word, offset in _DAY_WORDS.items():
        if rest.startswith(word):
            day_offset, rest = offset, rest[len(word):]
            break
    if day_offset is None:
        lowered = rest.lower()
        for word, offset in (("today", 0), ("tomorrow", 1), ("day after tomorrow", 2), ("yesterday", -1)):
            if lowered.startswith(word):
                day_offset, rest = offset, rest[len(word):]
                break
    if day_offset is None:
        raise ValueError(f"无法解析时间：{text}")
    match = _TIME_RE.match(rest.strip())
    if not match:
        if not rest.strip():
            return datetime.combine((now + timedelta(days=day_offset)).date(), time.max if end else time.min, tzinfo=_tz())
        raise ValueError(f"无法解析时间：{text}")
    meridiem, hour_text, minute_text = match.groups()
    hour, minute = int(hour_text), int(minute_text or 0)
    if hour > 23 or minute > 59:
        raise ValueError(f"时间超出范围：{text}")
    if meridiem in {"下午", "晚上"} and hour < 12:
        hour += 12
    elif meridiem in {"凌晨", "早上"} and hour == 12:
        hour = 0
    return datetime.combine((now + timedelta(days=day_offset)).date(), time(hour, minute), tzinfo=_tz())


def _calendar_rows(bridge) -> list[dict[str, Any]]:
    result = bridge.calendar_call("calendars", {})
    if isinstance(result, dict):
        result = result.get("calendars", result.get("result", []))
    return [row for row in (result or []) if isinstance(row, dict) and row.get("writable", True)]


def _resolve_calendar(args: dict[str, Any], bridge, *, required: bool = False) -> None:
    if args.get("calendar_id") is not None:
        args["calendar_id"] = int(args["calendar_id"])
        args.pop("calendar", None)
        return
    name = str(args.get("calendar", "")).strip()
    if name:
        rows = _calendar_rows(bridge)
        match = next((r for r in rows if str(r.get("name", "")).casefold() == name.casefold()), None)
        if match is None:
            raise ValueError(f"找不到可写日历：{name}")
        args["calendar_id"] = int(match["id"])
    elif required:
        rows = _calendar_rows(bridge)
        if not rows:
            raise ValueError("手机上没有可写日历")
        args["calendar_id"] = int(rows[0]["id"])
    args.pop("calendar", None)


def normalize_calendar_args(action: str, raw: dict[str, Any], bridge) -> dict[str, Any]:
    args = {k: v for k, v in raw.items() if v is not None}
    args.pop("action", None)
    if action == "calendars":
        return {"writable": True, "calendars": _calendar_rows(bridge)}
    if action in {"create", "update"}:
        if action == "create" and not str(args.get("title", "")).strip():
            raise ValueError("title 为必填项")
        if action == "create" and "start" not in args:
            raise ValueError("start 为必填项")
        if "start" in args:
            start_dt = _parse_time(args["start"])
            if args.get("all_day"):
                start_dt = datetime.combine(start_dt.date(), time.min, tzinfo=_tz())
            args["start"] = _epoch(start_dt)
        if "end" in args:
            end_dt = _parse_time(args["end"], end=bool(args.get("all_day")))
            if args.get("all_day"):
                end_dt = datetime.combine(end_dt.date(), time.min, tzinfo=_tz())
            args["end"] = _epoch(end_dt)
        elif action == "create" and "start" in args:
            args["end"] = args["start"] + (86400000 if args.get("all_day") else 3600000)
        _resolve_calendar(args, bridge, required=action == "create")
    elif action in {"list", "freebusy"}:
        now = datetime.now(_tz())
        if args.pop("today", False):
            start = datetime.combine(now.date(), time.min, tzinfo=_tz())
            args["start"], args["end"] = _epoch(start), _epoch(start + timedelta(days=1))
        elif args.get("days") is not None:
            start = _parse_time(args.get("start", now))
            args["start"], args["end"] = _epoch(start), _epoch(start + timedelta(days=int(args["days"])))
        else:
            if action == "freebusy" and ("start" not in args or "end" not in args):
                raise ValueError("freebusy 需要同时提供 start 和 end")
            if "start" in args: args["start"] = _epoch(_parse_time(args["start"]))
            if "end" in args: args["end"] = _epoch(_parse_time(args["end"], end=True))
        _resolve_calendar(args, bridge)
    elif action == "delete":
        if "id" not in args:
            raise ValueError("id 为必填项")
        args["id"] = int(args["id"])
    else:
        raise ValueError(f"未知日历操作：{action}")
    return args
