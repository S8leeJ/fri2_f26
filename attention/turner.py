"""When to turn the robot toward the person it talks to. No ROS here, so it can be tested.

    turner = Turner()
    omega, note = turner.update(now, engaged, bearing_deg, yaw_deg)

bearing_deg: where the person is in the camera image. 0 is the center, positive is to
the right, None means nobody to look at. yaw_deg: the robot heading from /odom.
omega: the turn speed to command in rad/s (ROS: positive turns left). note: a short text
when something changes, else None.

Rules:
- Turn only while engaged. At the first conversation, remember the heading as the rest
  heading, and use it for the whole run, so small errors do not add up.
- Start a turn only when the person stays more than deadband_deg off center for hold_s,
  then stop within stop_within_deg. So small movements do not turn the robot.
- Turn faster when the person is far off center and slower near the center, so the turn
  is smooth: gain times the angle, between min_speed and speed.
- Never turn more than max_turn_deg away from the remembered heading.
- When the conversation ends, turn back to the remembered heading.
- Stop when the person is lost, when the heading is unknown, or when a turn takes too long.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional, Tuple


def wrap(deg: float) -> float:
    """An angle in the range -180 to 180."""
    return (deg + 180.0) % 360.0 - 180.0


def compensate(bearing: float, yaw_now: float, yaw_then: float) -> float:
    """Where the person is now, from a camera frame taken at heading yaw_then.

    The image is a little old. A right turn since then (yaw goes down) moves the person
    toward the left of the image by the same angle.
    """
    return bearing + wrap(yaw_now - yaw_then)


@dataclass
class Turner:
    # The base turned about twice as fast as commanded on flexo (October 12, 2026), so
    # 0.25 rad/s gives about 29 degrees each second.
    speed: float = 0.25                 # fastest commanded turn, rad/s
    min_speed: float = 0.05             # slowest commanded turn, so the base still moves
    gain: float = 1.0                   # commanded rad/s for each radian off center
    deadband_deg: float = 8.0
    hold_s: float = 0.3
    stop_within_deg: float = 3.0
    max_turn_deg: float = 40.0
    home_within_deg: float = 2.0
    move_timeout_s: float = 6.0
    return_timeout_s: float = 15.0

    home: Optional[float] = None        # rest heading while a turn is not undone yet
    rest: Optional[float] = None        # heading at the first conversation of this run
    state: str = "idle"                 # idle, watching, turning, returning
    _off_since: Optional[float] = None
    _since: float = 0.0                 # when the current turn or return started
    _last_note: Optional[str] = field(default=None, repr=False)

    def turned(self, yaw: float) -> float:
        return 0.0 if self.home is None else wrap(yaw - self.home)

    def _rate(self, off_deg: float) -> float:
        return min(self.speed, max(self.min_speed, self.gain * math.radians(abs(off_deg))))

    def update(self, now: float, engaged: bool, bearing: Optional[float],
               yaw: Optional[float]) -> Tuple[float, Optional[str]]:
        if yaw is None:
            return self._stop("no odometry, so no turns")
        if engaged:
            return self._engaged(now, bearing, yaw)
        return self._not_engaged(now, yaw)

    def _engaged(self, now, bearing, yaw):
        if self.state == "returning":
            self.state = "watching"
        if self.home is None:
            if self.rest is None:
                self.rest = yaw
            self.home = self.rest
        if bearing is None:
            self._off_since = None
            return self._stop("nobody to face")
        direction = -1.0 if bearing > 0 else 1.0   # a person on the right needs a right turn
        turned = self.turned(yaw)
        at_limit = abs(turned) >= self.max_turn_deg and math.copysign(1.0, turned) == direction

        if self.state == "turning":
            if abs(bearing) <= self.stop_within_deg:
                return self._stop("centered, %.0f deg from the start" % turned)
            if at_limit:
                return self._stop("stopped at the %.0f deg limit" % self.max_turn_deg)
            if now - self._since > self.move_timeout_s:
                return self._stop("turn took too long, stopped")
            return direction * self._rate(bearing), None

        self.state = "watching"
        if abs(bearing) <= self.deadband_deg or at_limit:
            self._off_since = None
            return 0.0, None
        if self._off_since is None:
            self._off_since = now
        if now - self._off_since < self.hold_s:
            return 0.0, None
        self.state, self._since, self._off_since = "turning", now, None
        side = "right" if bearing > 0 else "left"
        return direction * self._rate(bearing), self._note("turning %s, person %.0f deg off center" % (side, abs(bearing)))

    def _not_engaged(self, now, yaw):
        if self.home is None:
            self.state = "idle"
            return 0.0, None
        turned = self.turned(yaw)
        if abs(turned) <= self.home_within_deg:
            self.home = None
            return self._stop("back at the start heading", state="idle")
        if self.state != "returning":
            self.state, self._since = "returning", now
            return (-1.0 if turned > 0 else 1.0) * self._rate(turned), self._note("conversation over, turning back %.0f deg" % turned)
        if now - self._since > self.return_timeout_s:
            self.home = None
            return self._stop("could not get back to the start heading, stopped", state="idle")
        return (-1.0 if turned > 0 else 1.0) * self._rate(turned), None

    def _stop(self, why: str, state: Optional[str] = None) -> Tuple[float, Optional[str]]:
        moving = self.state in ("turning", "returning")
        self.state = state or ("watching" if self.home is not None else "idle")
        self._off_since = None
        return 0.0, (self._note(why) if moving or why != self._last_note else None)

    def _note(self, text: str) -> str:
        self._last_note = text
        return text
