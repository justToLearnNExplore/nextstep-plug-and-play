"""What every phone driver provides. The agent loop only talks to this interface, so the same box
software drives an Android phone (ADB), an iPhone (USB/Bluetooth HID + AirPlay) or a simulator."""

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class ScreenState:
    """One look at the phone: the element list (pixel bounds) and, sometimes, a JPEG screenshot."""

    package: str
    width: int
    height: int
    nodes: list[dict[str, Any]] = field(default_factory=list)
    screenshot_b64: str | None = None
    screenshot_tried: bool = False
    has_secure_field: bool = False
    hint: str = ""  # what the brain should know about this kind of phone, shown with the element list

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

    def execute(self, name: str, args: dict[str, Any], screen: ScreenState | None) -> dict[str, Any]:
        """Runs one action (click, type, open_link, ...). Coordinates are 0-999."""
        ...

    def close(self) -> None: ...


def px(value: Any, size: int) -> int:
    """The brain works in 0-999 coordinates; map them to device pixels."""
    v = min(max(int(value), 0), 999)
    return int(v * size / 1000)


def center(node: dict[str, Any], screen: ScreenState) -> tuple[int, int]:
    """An element's centre in the brain's 0-999 coordinates."""
    b = node["b"]
    return (int((b[0] + b[2]) / 2 * 1000 / max(screen.width, 1)), int((b[1] + b[3]) / 2 * 1000 / max(screen.height, 1)))
