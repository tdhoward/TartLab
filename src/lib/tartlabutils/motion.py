"""Reusable time-based motion helpers."""


MILLISECONDS_PER_SECOND = 1000


class StagedMotion:
    """Accumulate quantized distance using distance-selected speed stages.

    Distances and speeds use caller-defined units. For example, the same
    helper can drive pixels, degrees, steps, or millimeters without knowing
    anything about the application that consumes each emitted delta.
    """

    def __init__(self, speed_stages, quantum=1):
        quantum = int(quantum)
        if quantum <= 0:
            raise ValueError("quantum must be positive")
        if not speed_stages or speed_stages[0][0] != 0:
            raise ValueError("speed stages must begin at distance zero")

        previous_threshold = -1
        checked_stages = []
        for threshold, speed in speed_stages:
            threshold = int(threshold)
            speed = int(speed)
            if threshold <= previous_threshold or speed <= 0:
                raise ValueError(
                    "speed thresholds must increase and speeds must be positive")
            checked_stages.append((threshold, speed))
            previous_threshold = threshold

        self.speed_stages = tuple(checked_stages)
        self.quantum = quantum
        self.distance_milliunits = 0
        self.stage = 0
        self._emitted_quanta = 0

    @property
    def distance(self):
        """Return the accumulated whole distance units."""
        return self.distance_milliunits // MILLISECONDS_PER_SECOND

    @property
    def speed_per_second(self):
        return self.speed_stages[self.stage][1]

    def _select_stage(self):
        distance = self.distance
        stages = self.speed_stages
        while (self.stage + 1 < len(stages) and
               distance >= stages[self.stage + 1][0]):
            self.stage += 1

    def advance(self, elapsed_ms):
        """Advance elapsed time and return newly available quantized units."""
        elapsed_ms = int(elapsed_ms)
        if elapsed_ms < 0:
            raise ValueError("elapsed time must not be negative")
        self._select_stage()
        self.distance_milliunits += self.speed_per_second * elapsed_ms
        self._select_stage()

        quantum_milliunits = self.quantum * MILLISECONDS_PER_SECOND
        total_quanta = self.distance_milliunits // quantum_milliunits
        available_quanta = total_quanta - self._emitted_quanta
        self._emitted_quanta = total_quanta
        return available_quanta * self.quantum
