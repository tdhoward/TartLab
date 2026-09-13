"""Portable behavioral checks, shared by host tests and serial device checks.

Pass the actual engine's definitions as an object with named attributes.
No platform imports, copied movement rules, or rendering are needed.
"""


def make_state(g, cells, enclosed=False):
    rows = [[".."] * g.COLS for _ in range(g.ROWS)]
    if enclosed:
        for y in range(g.ROWS):
            for x in range(g.COLS):
                if x in (0, g.COLS - 1) or y in (0, g.ROWS - 1):
                    rows[y][x] = "#0"
    # Keep the idle player and exit away from all tested perimeter routes.
    rows[8][3], rows[9][3] = "P.", "E."
    for (x, y), token in cells.items():
        rows[y][x] = token
    return g.create_state(g.validate_level({
        "name": "Spider wall following", "map": [" ".join(row) for row in rows],
        "timers": {"spider_ms": 10},
    }))


def move(g, level):
    spider = level.spiders[0]
    before = (spider.cell, spider.heading, spider.next_due_ms,
              list(level.actor_at), level.occupancy_version)
    heading = g.next_spider_heading(level, spider)
    assert heading is not None, "unexpected trap"
    destination = g.spider_destination(level, spider, heading)
    assert before == (spider.cell, spider.heading, spider.next_due_ms,
                      list(level.actor_at), level.occupancy_version), "preview mutated state"
    g.step(level)
    assert level.status == g.PLAYING and spider.alive, "unexpected death"
    assert (spider.cell, spider.heading) == (destination, heading), "preview disagrees with move"
    assert spider.next_due_ms == before[2] + 10, "movement deadline drifted"
    return spider.cell % g.COLS, spider.cell // g.COLS


def assert_perimeter(g, level, inset=0):
    expected = {(x, y) for x in range(inset, g.COLS - inset)
                for y in range(inset, g.ROWS - inset)
                if x in (inset, g.COLS - 1 - inset) or y in (inset, g.ROWS - 1 - inset)}
    for _ in range(g.COLS + g.ROWS):
        if move(g, level) in expected:
            break
    else:
        raise AssertionError("did not reach the room perimeter")
    # The arrival heading points into the wall; start after joining its edge.
    assert move(g, level) in expected
    spider = level.spiders[0]
    start = (spider.cell, spider.heading)
    for _ in range(2):
        visited = [move(g, level) for _ in range(len(expected))]
        assert set(visited) == expected, "did not follow the complete perimeter"
        assert (spider.cell, spider.heading) == start, "perimeter circuit did not close"


def assert_circuit(g, level, route):
    spider = level.spiders[0]
    start = (spider.cell, spider.heading)
    for _ in range(2):
        assert [move(g, level) for _ in route] == route, "obstacle circuit differed"
        assert (spider.cell, spider.heading) == start, "obstacle circuit did not close"


def room_perimeters(g):
    for enclosed in (False, True):
        for heading in "neswNESW":
            level = make_state(g, {(6, 4): "X" + heading}, enclosed)
            assert_perimeter(g, level, int(enclosed))


def rectangular_obstacles(g):
    route = [(6, 3), (5, 3), (5, 4), (5, 5), (5, 6), (5, 7), (6, 7), (7, 7),
             (8, 7), (9, 7), (9, 6), (9, 5), (9, 4), (9, 3), (8, 3), (7, 3)]
    for token, path in (("Xw", route), ("XE", list(reversed(route[:-1])) + [route[-1]])):
        cells = {(x, y): "#0" for x in range(6, 9) for y in range(4, 7)}
        cells[(7, 3)] = token
        assert_circuit(g, make_state(g, cells), path)


def concave_obstacles(g):
    route = [(5, 3), (5, 4), (5, 5), (5, 6), (5, 7), (6, 7), (7, 7), (8, 7),
             (9, 7), (10, 7), (10, 6), (10, 5), (9, 5), (8, 5), (8, 4),
             (8, 3), (7, 3), (6, 3)]
    for token, path in (("Xw", route), ("XE", list(reversed(route[:-1])) + [route[-1]])):
        cells = {(x, y): "#0" for x in (6, 7) for y in (4, 5, 6)}
        cells.update({(8, 6): "#0", (9, 6): "#0", (6, 3): token})
        assert_circuit(g, make_state(g, cells), path)


def disappearing_obstacles(g):
    # Remove the obstacle at every position in a circuit, including corners.
    for token in ("Xw", "XE"):
        for moves in range(16):
            cells = {(x, y): "O." for x in range(6, 9) for y in range(3, 6)}
            cells[(7, 2)] = token
            level = make_state(g, cells)
            for _ in range(moves):
                move(g, level)
            for x in range(6, 9):
                for y in range(3, 6):
                    cell = g.cell_at(x, y)
                    level.objects[cell] = g.EMPTY
                    g.mark_changed(level, cell, g.OBJECT_CHANGED)
            assert_perimeter(g, level)


def teleport_reacquires_wall(g):
    for heading in "neswNESW":
        dx, dy = g.DIRECTIONS["nesw".index(heading.lower())]
        cells = {(3, 3): "X" + heading, (3 + dx, 3 + dy): "T0", (7, 5): "T0"}
        level = make_state(g, cells)
        assert move(g, level) == (7, 5), "spider did not teleport"
        assert_perimeter(g, level)


def corner_support_uses_all_blockers(g):
    for heading in "neswNESW":
        direction = "nesw".index(heading.lower())
        side = -1 if heading.islower() else 1
        dx, dy = g.DIRECTIONS[direction]
        sx, sy = g.DIRECTIONS[(direction + side) % 4]
        corner = (6 - dx + sx, 4 - dy + sy)
        for blocker in ("#0", "F0", "d0", "W0", "K.", "D.", "O.", "E.", "S.", "RE", "Xn"):
            cells = {(6, 4): "X" + heading, corner: blocker}
            if blocker == "E.":
                cells[(3, 9)] = ".."
            level = make_state(g, cells)
            spider = next(a for a in level.spiders if a.cell == g.cell_at(6, 4))
            assert g.next_spider_heading(level, spider) == (direction + side) % 4, blocker
        for trap_state in (g.EXTENDING, g.STOPPED):
            level = make_state(g, {(6, 4): "X" + heading, (2, 2): "RE"})
            emitter = next(a for a in level.actors if a.kind == g.EMITTER)
            emitter.trap_state = trap_state
            level.spear_at[g.cell_at(*corner)] = emitter.id
            assert g.next_spider_heading(level, level.spiders[0]) == (direction + side) % 4


def diagonal_senses_local_cell(g):
    for token, side_y, expected in (("Xe", 3, g.NORTH), ("XE", 5, g.SOUTH)):
        # A clear diagonal pad is floor, regardless of its blocked remote twin.
        level = make_state(g, {(6, 4): token, (5, side_y): "T0", (2, 2): "T0"})
        level.objects[g.cell_at(2, 2)] = g.BOULDER
        assert g.next_spider_heading(level, level.spiders[0]) == g.EAST
        # A corner-supported side move still performs the normal teleport hop.
        level = make_state(g, {(6, 4): token, (5, side_y): "#0",
                               (6, side_y): "T0", (7, 5): "T0"})
        assert move(g, level) == (7, 5)
        assert level.spiders[0].heading == expected


def edges_do_not_wrap(g):
    for token in ("Xe", "XE"):
        level = make_state(g, {(0, 4): token})
        assert g.next_spider_heading(level, level.spiders[0]) == (
            g.NORTH if token == "Xe" else g.SOUTH), "outside diagonal must be blocked"
    # A row-edge neighbor must not supply a fictitious diagonal corner.
    for token, direction in (("Xs", g.SOUTH), ("XN", g.NORTH)):
        level = make_state(g, {(15, 4): token, (0, 4): "#0"})
        assert g.next_spider_heading(level, level.spiders[0]) == direction


CHECKS = (
    room_perimeters, rectangular_obstacles, concave_obstacles,
    disappearing_obstacles, teleport_reacquires_wall,
    corner_support_uses_all_blockers, diagonal_senses_local_cell, edges_do_not_wrap,
)
