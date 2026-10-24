"""What every phone driver provides. The agent loop only talks to this interface, so the same box
software drives an Android phone (ADB), an iPhone (USB/Bluetooth HID + AirPlay) or a simulator."""

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class ScreenState:
    """Same shape as the NextStep backend's Screen model (and the Android app's ScreenReader)."""

    package: str
    width: int
    height: int
    nodes: list[dict[str, Any]] = field(default_factory=list)
    screenshot_b64: str | None = None
    screenshot_tried: bool = False
    has_secure_field: bool = False

    def to_json(self) -> dict[str, Any]:
        d: dict[str, Any] = {"package": self.package, "width": self.width, "height": self.height,
                             "nodes": self.nodes, "has_secure_field": self.has_secure_field,
                             "screenshot_tried": self.screenshot_tried}
        if self.screenshot_b64:
            d["screenshot_b64"] = self.screenshot_b64
        return d


class PhoneDriver(Protocol):
    name: str

    def capture(self, with_screenshot: bool) -> ScreenState:
        """The current screen: element list always, a JPEG screenshot only when asked."""
        ...

    def execute(self, name: str, args: dict[str, Any], screen: ScreenState) -> dict[str, Any]:
        """Runs one backend action (click, type, open_link, ...). Coordinates are 0-999."""
        ...

    def close(self) -> None: ...


def px(value: Any, size: int) -> int:
    """Backend coordinates are normalised to 0-999; map them to device pixels."""
    v = min(max(int(value), 0), 999)
    return int(v * size / 1000)
