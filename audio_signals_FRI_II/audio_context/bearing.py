# Goal: estimate which direction a voice comes from, with the 7 microphones
# of the Azure Kinect. Produces speech_bearing_deg.
#
#   bearing = Bearing(CONFIG)
#   bearing.activate(device_name, channels, rate)  # True only for the Kinect array
#   bearing.add(block)                              # a block with voice in it
#   bearing.latest(stamp)                           # degrees, or None
#
# It runs only when the capture device is the Kinect's 7-microphone array.
# With any other microphone, activate() returns False and the JSON has no
# speech_bearing_deg field.
#
# Method: SRP-PHAT. For each candidate direction, it adds up how well every
# microphone pair agrees with the time difference that the direction would
# cause, and takes the direction with the highest total. A study with the same
# method on an Azure Kinect measured about 12 to 14 degrees of average error
# for one speaker, and unreliable results for a second speaker at the same time.
#
# Microphone positions, in metres, from ssloc_ros (Universitat Hamburg,
# MIT/Apache-2.0), param/azure_kinect.yaml. Channel 0 is the centre. Channels
# 1 to 6 are a hexagon of 40 mm radius.

import threading
from collections import deque

import numpy as np

MICS = np.array([
    [0.0, 0.0],
    [0.04, 0.0],
    [0.02, -0.0346],
    [-0.02, -0.0346],
    [-0.04, 0.0],
    [-0.02, 0.0346],
    [0.02, 0.0346],
])
SPEED_OF_SOUND = 343.0
BAND_HZ = (300.0, 4000.0)   # most speech energy, and below strong aliasing
STEP_DEG = 5


class Bearing:

    def __init__(self, cfg):
        self.enabled = cfg.get("bearing_enabled", False)
        self.offset = cfg.get("bearing_offset_deg", 0.0)
        self.mirror = cfg.get("bearing_mirror", False)
        self.window = cfg.get("bearing_window_sec", 1.0)
        self.active = False
        self.rate = None
        self._steer = {}          # FFT length -> (band slice, steering array)
        self._lock = threading.Lock()
        self._recent = deque()    # (time, unit vector as complex, weight)

        i, j = np.triu_indices(len(MICS), k=1)
        self._pairs = (i, j)
        angles = np.deg2rad(np.arange(0, 360, STEP_DEG))
        self._angles = angles
        directions = np.stack([np.cos(angles), np.sin(angles)], axis=1)
        # A mic closer to the source hears it earlier, so the time difference
        # between mics i and j for direction u is -(p_i - p_j) . u / c.
        self._tdoa = -(directions @ (MICS[i] - MICS[j]).T) / SPEED_OF_SOUND

    def activate(self, device_name, channels, rate):
        """Turn on for the Kinect's 7-microphone array only."""
        name = (device_name or "").lower()
        self.active = bool(self.enabled and "azure kinect" in name and channels == len(MICS))
        self.rate = rate
        return self.active

    def _steering(self, n):
        if n not in self._steer:
            freqs = np.fft.rfftfreq(n, 1.0 / self.rate)
            band = (freqs >= BAND_HZ[0]) & (freqs <= BAND_HZ[1])
            f = freqs[band]
            steer = np.exp(2j * np.pi * self._tdoa[:, :, None] * f[None, None, :])
            self._steer[n] = (band, steer.astype(np.complex64))
        return self._steer[n]

    def estimate(self, samples):
        """Direction in the array's own frame, in radians, and a weight.

        samples has one column for each microphone, at self.rate.
        """
        n = samples.shape[0]
        band, steer = self._steering(n)
        spectrum = np.fft.rfft(samples * np.hanning(n)[:, None], axis=0)[band]
        i, j = self._pairs
        cross = spectrum[:, i] * np.conj(spectrum[:, j])
        cross /= np.abs(cross) + 1e-12             # phase transform
        power = np.real(np.einsum("fp,apf->a", cross, steer))
        best = int(np.argmax(power))
        # A sharp peak is a clearer estimate than a flat response.
        weight = float((power[best] - power.mean()) / (power.std() + 1e-12))
        return self._angles[best], max(weight, 0.0)

    def add(self, block):
        if not self.active or block.channels is None:
            return
        samples = np.asarray(block.channels, dtype=np.float64)
        if samples.ndim != 2 or samples.shape[1] != len(MICS):
            return
        angle, weight = self.estimate(samples)
        # Quiet blocks, such as the end of a word, carry more noise than voice.
        weight *= float(np.sqrt(np.mean(np.square(samples))))
        with self._lock:
            self._recent.append((block.t, np.exp(1j * angle), weight))
            cutoff = block.t - self.window
            while self._recent and self._recent[0][0] < cutoff:
                self._recent.popleft()

    def latest(self, now):
        """Degrees from straight ahead, or None when no voice in the window.

        After calibration, 0 is straight ahead of the camera, negative is
        left, and positive is right, as bearing_deg in the schema.
        """
        if not self.active or now is None:
            return None
        with self._lock:
            recent = [(v, w) for t, v, w in self._recent if t >= now - self.window]
        if not recent:
            return None
        total = sum(v * w for v, w in recent)
        if abs(total) < 1e-9:
            total = sum(v for v, _ in recent)
        degrees = float(np.degrees(np.angle(total)))
        if self.mirror:
            degrees = -degrees
        degrees += self.offset
        degrees = (degrees + 180.0) % 360.0 - 180.0
        return round(degrees)
