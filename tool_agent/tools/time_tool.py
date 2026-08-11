from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from tool_agent.tools.base import ToolResult


CITY_TIMEZONES = {
    # 小型城市别名表：把自然语言里的城市映射成标准展示名 + IANA timezone。
    # 面试可以说：第一版用表驱动，后续可换成 geocoding/timezone API。
    "beijing": ("Beijing", "Asia/Shanghai"),
    "北京": ("Beijing", "Asia/Shanghai"),
    "shanghai": ("Shanghai", "Asia/Shanghai"),
    "上海": ("Shanghai", "Asia/Shanghai"),
    "new york": ("New York", "America/New_York"),
    "纽约": ("New York", "America/New_York"),
    "london": ("London", "Europe/London"),
    "伦敦": ("London", "Europe/London"),
    "tokyo": ("Tokyo", "Asia/Tokyo"),
    "东京": ("Tokyo", "Asia/Tokyo"),
    "san francisco": ("San Francisco", "America/Los_Angeles"),
    "los angeles": ("Los Angeles", "America/Los_Angeles"),
    "paris": ("Paris", "Europe/Paris"),
}


class TimeTool:
    """当前时间工具。

    不依赖外部 API，直接使用 Python 标准库 zoneinfo。
    """

    name = "get_time"

    def __init__(self, now_provider=None) -> None:
        # now_provider 是测试注入点，让单元测试不依赖真实当前时间。
        self._now_provider = now_provider

    def run(self, query: str) -> ToolResult:
        location = query.strip() or "local"
        display_location, timezone = self._resolve_location(location)
        try:
            current = self._format_now(timezone)
        except ZoneInfoNotFoundError:
            return ToolResult(ok=False, tool=self.name, error=f"unknown timezone: {timezone}")
        return ToolResult(
            ok=True,
            tool=self.name,
            data={"location": display_location, "timezone": timezone, "current_time": current},
        )

    def _resolve_location(self, location: str) -> tuple[str, str]:
        lowered = location.lower()
        for key, value in CITY_TIMEZONES.items():
            if key in lowered:
                return value
        if "/" in location:
            # 用户直接传 Asia/Shanghai 这种 IANA timezone 时，也支持。
            return location, location
        timezone = datetime.now().astimezone().tzinfo.key if hasattr(datetime.now().astimezone().tzinfo, "key") else "local"
        return location, timezone

    def _format_now(self, timezone: str) -> str:
        if self._now_provider:
            return self._now_provider(timezone)
        if timezone == "local":
            now = datetime.now().astimezone()
        else:
            now = datetime.now(ZoneInfo(timezone))
        return now.strftime("%Y-%m-%d %H:%M:%S %Z%z")
