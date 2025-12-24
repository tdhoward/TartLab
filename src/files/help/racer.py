from hdwconfig import display_drv, broker
from touch_keypad import Keypad
from eventsys.keys import Keys
from graphics import Draw, Area
from palettes import get_palette
from displaybuf import DisplayBuffer
from time import ticks_ms, sleep_ms   # Helps us keep time to smooth out the movement

display_drv.rotation = 0

# Disable auto byte swap if supported
if display_drv.requires_byteswap:
    needs_swap = display_drv.disable_auto_byteswap(True)
else:
    needs_swap = False

# Define some colors
class pal:
    BLACK   = 0x0000
    WHITE   = 0xFFFF
    GREEN   = 0x07E0 if not needs_swap else 0xE007
    DKGREEN = 0x0600 if not needs_swap else 0x0006
    RED     = 0xF800 if not needs_swap else 0x00F8
    ORANGE  = 0xFD20 if not needs_swap else 0x20FD
    GREY    = 0x8410 if not needs_swap else 0x1084
    YELLOW  = 0xFFE0 if not needs_swap else 0xE0FF

canvas = DisplayBuffer(display_drv)

WIDTH = canvas.width
HEIGHT = canvas.height  # 480
UNIT = HEIGHT // 15     # 32
TFA = UNIT              # 32
LINE_HEIGHT = (HEIGHT - TFA) // 8  # 56
TICKS = 40  # how many milliseconds should we wait between frames?

CAR_WIDTH = 16
CAR_HEIGHT = 16
CAR_POS_Y = HEIGHT - (CAR_HEIGHT + 10)

# Button mapping
BT_ROWS = 5
BT_COLS = 2
BT_WIDTH = WIDTH // BT_COLS
BT_HEIGHT = HEIGHT // BT_ROWS
BT_WIDTH_HALF = BT_WIDTH // 2
BT_HEIGHT_HALF = BT_HEIGHT // 2
START = Keys.K_RETURN
PAUSE = Keys.K_ESCAPE
LEFT  = Keys.K_LEFT
RIGHT = Keys.K_RIGHT
UNUSED = 0
keypad = Keypad(broker.poll, 0, 0, WIDTH, HEIGHT, rows=BT_ROWS, cols=BT_COLS,
                keys=[START, PAUSE, 
					  UNUSED, UNUSED, 
					  LEFT, RIGHT,
					  LEFT, RIGHT,
					  LEFT, RIGHT])

keys = {
    "start": False,
    "pause": False,
    "left": False,
    "right": False
}

canvas.set_vscroll(TFA, 0)  # top fixed area (TFA), bottom fixed area (BFA)
#pal = get_palette()
draw = Draw(canvas)


# Simple little helper function for drawing centered text on the canvas
def canvas_text(msg, x, y, color=pal.WHITE, center = True):
    if center:
        y -= 4
        x -= len(msg) * 4
    draw.text(msg, x, y, color, scale=1, inverted=False, font_data=None, height=8)

def display_msg(msg, col = pal.WHITE, bgcol = pal.GREY, center = True):
    x = 4
    y = 2
    if center:
        x = WIDTH // 2
        y = TFA // 2
        y -= 7
        x -= len(msg) * 4
    draw.fill_rect(0, 0, WIDTH, TFA, bgcol)
    draw.text14(msg, x, y, col)

def display_score():
    global score
    display_msg(f'SCORE: {score}')


'''
MOUSEBUTTONDOWN
Button(type=1025, pos=(181, 417), button=1, touch=False, window=None)

MOUSEMOTION
Motion(type=1024, pos=(172, 337), rel=(0, 0), buttons=(1, 0, 0), touch=False, window=None)
Motion(type=1024, pos=(173, 339), rel=(1, 2), buttons=(1, 0, 0), touch=False, window=None)

MOUSEBUTTONUP
Button(type=1026, pos=(53, 410), button=1, touch=False, window=None)

'''

def get_key_from_pos(x, y):
    if y < BT_HEIGHT:
        if x < BT_WIDTH:
            return "start"
        else:
            return "pause"
    elif y > BT_HEIGHT * 2:
        if x < BT_WIDTH:
            return "left"
        else:
            return "right"
    return None


def update_keys():
    global keys
    if evt := broker.poll():
        x, y = evt.pos
        key = get_key_from_pos(x, y)
        if evt.type == broker.events.MOUSEBUTTONDOWN or evt.type == broker.events.MOUSEBUTTONUP:
            if key:
                keys[key] = (evt.type == broker.events.MOUSEBUTTONDOWN)
        elif evt.type == broker.events.MOUSEMOTION:
            rx = evt.rel[0]
            ry = evt.rel[1]
            start_key = get_key_from_pos(x - rx, y - ry)
            if (start_key == key):  # we're still on the same key
                return
            if start_key:
                keys[start_key] = False  # we aren't, so key up on old key
            if key:
                keys[key] = True  # and key down on new key
            

def erase_car(old_car_x, old_car_y):
    return draw.fill_rect(old_car_x - CAR_WIDTH // 2, old_car_y, CAR_WIDTH, CAR_HEIGHT, pal.BLACK)

def draw_car(car_x, car_y):
    return draw.fill_rect(car_x - CAR_WIDTH // 2, car_y, CAR_WIDTH, CAR_HEIGHT, pal.RED)


def merge_areas(areas):
    merged = []
    while areas:
        base = areas.pop()
        if base is None:
            continue
        changed = True
        while changed:
            changed = False
            remaining = []
            for other in areas:
                if other is None:
                    continue
                if base.touches_or_intersects(other):
                    base = base + other  # union of areas
                    changed = True
                else:
                    remaining.append(other)
            areas = remaining
        merged.append(base)
    return merged

def main():
    global score, keys, road_speed
    # Show touch-screen control locations
    draw.fill(pal.BLACK)
    draw.rect(0, 0, BT_WIDTH, BT_HEIGHT, pal.GREY)  # Start
    canvas_text("Start", BT_WIDTH_HALF, BT_HEIGHT_HALF, pal.ORANGE)
    
    draw.rect(BT_WIDTH, 0, BT_WIDTH, BT_HEIGHT, pal.GREY)  # Pause
    canvas_text("Pause", BT_WIDTH + BT_WIDTH_HALF, BT_HEIGHT_HALF, pal.ORANGE)
    
    draw.rect(0, BT_HEIGHT * 2, BT_WIDTH, BT_HEIGHT * 3, pal.GREY)  # Left
    canvas_text("Left", BT_WIDTH_HALF, BT_HEIGHT * 3, pal.ORANGE)
    
    draw.rect(BT_WIDTH, BT_HEIGHT * 2, BT_WIDTH, BT_HEIGHT * 3, pal.GREY)  # Right
    canvas_text("Right", BT_WIDTH + BT_WIDTH_HALF, BT_HEIGHT * 3, pal.ORANGE)
    canvas.show()

    # Wait for START
    while True:
        if keypad.read() == START:
            break
    
    road_speed = 1
    vscroll = 0

    steering_acceleration = 0.5   # How quickly the car reacts to input
    max_velocity_x = 5.0          # Max sideways speed
    friction = 0.1                # How quickly the car slows down when no input

    car_y = CAR_POS_Y
    car_x = WIDTH // 2
    car_velocity_x = 0.0
    steering_input = 0  # -1 for left, 1 for right, 0 for no input

    # Clear screen again
    draw.fill(pal.BLACK)
    
    # draw top fixed area (score)
    score = 0
    display_score()

    # draw the street
    for y in range(TFA, canvas.vsa + TFA, LINE_HEIGHT * 2):
        # Draw street lines on the scrollable area
        draw.fill_rect(WIDTH // 2 - 2, y, 4, LINE_HEIGHT, pal.YELLOW)
    canvas.show()

    last = ticks_ms()  # take a snapshot of the current time

    while True:
        update_keys()  # check for keypresses

        if keys["pause"]:
            display_msg("-- PAUSED --")
            paused_key = None
            while paused_key is None:
                paused_key = keypad.read()
            if paused_key == START:  # if they press Start once...
                paused_key = None
                while paused_key is None:   # check to see if they press it again
                    paused_key = keypad.read()
                if paused_key == START:
                    return False    # quit if they pressed start twice
            display_score()

        if keys["left"] and keys["right"]:
            steering_input = 0
        elif keys["left"]:
            steering_input = -1
        elif keys["right"]:
            steering_input = 1
        else:
            steering_input = 0

        # Edge damping: reduce horizontal velocity near the edges
        edge_margin = 100  # Distance from edge where damping starts
        center = WIDTH / 2
        distance_from_center = abs(car_x - center)
        edge_factor = max(0.0, 1.0 - (distance_from_center / (WIDTH / 2 - edge_margin)))
        edge_factor = min(edge_factor, 1.0)  # Clamp to 1.0

        car_velocity_x += steering_input * steering_acceleration * edge_factor

        # Clamp horizontal velocity
        if car_velocity_x > max_velocity_x:
            car_velocity_x = max_velocity_x
        elif car_velocity_x < -max_velocity_x:
            car_velocity_x = -max_velocity_x

        # Apply friction (decay velocity when no input)
        if steering_input == 0:
            if car_velocity_x > 0:
                car_velocity_x = max(0, car_velocity_x - friction)
            elif car_velocity_x < 0:
                car_velocity_x = min(0, car_velocity_x + friction)

        # Update position
        old_car_x = car_x
        car_x += car_velocity_x

        # Clamp position to screen bounds
        car_x = max(0, min(WIDTH, car_x))

        vscroll -= road_speed
        if vscroll < 0:
            vscroll += HEIGHT
        old_car_y = car_y
        car_y = CAR_POS_Y - vscroll

        # Erase the old car
        dirty_areas = []
        dirty_areas.append(erase_car(int(old_car_x), old_car_y))

        # Draw the car onto the screen
        dirty_areas.append(draw_car(int(car_x), car_y))

        # try to merge the areas
        dirty = merge_areas(dirty_areas)

        # figure out how long we need to wait before drawing the frame
        delta = ticks_ms() - last
        if delta < TICKS:
            sleep_ms(TICKS - delta)

        for a in dirty:
            canvas.show(a)  # okay, update the screen in the dirty areas!

        canvas.vscroll = vscroll
        
        last = ticks_ms()  # store the snapshot of current time

main()
