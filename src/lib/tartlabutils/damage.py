"""Allocation-conscious clipped damage-region tracking."""


class DamageTracker:
    """Collect, merge, and bound rectangular regions needing presentation.

    Storage is allocated during construction and reused by :meth:`clear`.
    Nearby rectangles merge only when the union adds no more than the
    configured pixel-equivalent transaction overhead.  When capacity is
    reached, the least-expensive union is selected instead of growing the
    list without bound.
    """

    __slots__ = (
        "left", "top", "right", "bottom", "capacity",
        "merge_overhead", "_regions", "count")

    def __init__(self, bounds, capacity=12, merge_overhead=48):
        left, top, width, height = bounds
        self.left = int(left)
        self.top = int(top)
        self.right = self.left + int(width)
        self.bottom = self.top + int(height)
        self.capacity = int(capacity)
        self.merge_overhead = int(merge_overhead)
        if self.right <= self.left or self.bottom <= self.top:
            raise ValueError("damage bounds must have positive size")
        if self.capacity <= 0:
            raise ValueError("damage capacity must be positive")
        if self.merge_overhead < 0:
            raise ValueError("merge overhead must not be negative")
        self._regions = [[0, 0, 0, 0] for unused in range(self.capacity)]
        self.count = 0

    def clear(self):
        """Forget active regions while retaining all allocated storage."""
        self.count = 0

    def area(self, index):
        """Return reusable ``[x, y, width, height]`` storage by index."""
        if index < 0 or index >= self.count:
            raise IndexError(index)
        return self._regions[index]

    @property
    def pixel_count(self):
        total = 0
        for index in range(self.count):
            region = self._regions[index]
            total += region[2] * region[3]
        return total

    def add(self, area):
        """Clip and add a four-item rectangle; return whether it was visible."""
        return self.mark(area[0], area[1], area[2], area[3])

    def mark(self, x, y, width, height):
        """Clip and add one rectangle without allocating steady-state storage."""
        x = int(x)
        y = int(y)
        width = int(width)
        height = int(height)
        if width <= 0 or height <= 0:
            return False

        right = min(self.right, x + width)
        bottom = min(self.bottom, y + height)
        x = max(self.left, x)
        y = max(self.top, y)
        if right <= x or bottom <= y:
            return False

        while True:
            width = right - x
            height = bottom - y
            area_pixels = width * height
            merge_index = -1

            for index in range(self.count):
                region = self._regions[index]
                union_left = min(x, region[0])
                union_top = min(y, region[1])
                union_right = max(right, region[0] + region[2])
                union_bottom = max(bottom, region[1] + region[3])
                union_pixels = ((union_right - union_left) *
                                (union_bottom - union_top))
                region_pixels = region[2] * region[3]
                if union_pixels <= (area_pixels + region_pixels +
                                    self.merge_overhead):
                    merge_index = index
                    x = union_left
                    y = union_top
                    right = union_right
                    bottom = union_bottom
                    break

            if merge_index >= 0:
                self.count -= 1
                if merge_index != self.count:
                    source = self._regions[self.count]
                    target = self._regions[merge_index]
                    target[0] = source[0]
                    target[1] = source[1]
                    target[2] = source[2]
                    target[3] = source[3]
                continue

            if self.count < self.capacity:
                region = self._regions[self.count]
                region[0] = x
                region[1] = y
                region[2] = width
                region[3] = height
                self.count += 1
                return True

            cheapest_index = 0
            cheapest_growth = None
            for index in range(self.count):
                region = self._regions[index]
                union_left = min(x, region[0])
                union_top = min(y, region[1])
                union_right = max(right, region[0] + region[2])
                union_bottom = max(bottom, region[1] + region[3])
                growth = ((union_right - union_left) *
                          (union_bottom - union_top) -
                          region[2] * region[3])
                if cheapest_growth is None or growth < cheapest_growth:
                    cheapest_growth = growth
                    cheapest_index = index

            region = self._regions[cheapest_index]
            x = min(x, region[0])
            y = min(y, region[1])
            right = max(right, region[0] + region[2])
            bottom = max(bottom, region[1] + region[3])
            self.count -= 1
            if cheapest_index != self.count:
                source = self._regions[self.count]
                target = self._regions[cheapest_index]
                target[0] = source[0]
                target[1] = source[1]
                target[2] = source[2]
                target[3] = source[3]
