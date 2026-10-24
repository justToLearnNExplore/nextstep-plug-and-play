"""The box's button and light (HARDWARE.md: a push button on GPIO23, an LED on GPIO24).

Light: off = waiting for a phone; on = listening; fast blink = thinking or working; slow blink = asking
the person something. Button: "listen now" while the box waits, "yes" / "done" while it asks.
On a Mac (no gpiozero) there is neither: the Enter key and the terminal stand in.
"""

import os


class Face:
    def __init__(self):
        self.button = self.led = None
        try:
            from gpiozero import LED, Button  # Raspberry Pi only
            self.button = Button(int(os.getenv("NEXTSTEP_BOX_BUTTON_PIN", "23")))
            self.led = LED(int(os.getenv("NEXTSTEP_BOX_LED_PIN", "24")))
        except Exception:  # not a Pi, or no gpiozero: no button or light
            pass

    def pressed(self) -> bool:
        return bool(self.button is not None and self.button.is_pressed)

    def idle(self) -> None:
        if self.led is not None:
            self.led.off()

    def listening(self) -> None:
        if self.led is not None:
            self.led.on()

    def thinking(self) -> None:
        if self.led is not None:
            self.led.blink(on_time=0.15, off_time=0.15)

    def asking(self) -> None:
        if self.led is not None:
            self.led.blink(on_time=0.6, off_time=0.6)
