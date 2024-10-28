'''
Adapted from https://github.com/waveshareteam/RP2040-Touch-LCD-1.28/blob/main/python/RP2040-LCD-1.28.py
and https://github.com/koendv/cst816t/blob/master/src/cst816t.cpp
by Brad Barnett, 2024
Reference:  https://files.waveshare.com/upload/c/c2/CST816S_register_declaration.pdf
'''
from machine import Pin
from time import sleep_ms
from micropython import const


_CST816S_ID = const(0xB4)
_CST816T_ID = const(0xB5)
_CST816D_ID = const(0xB6)
_CST820_ID = const(0xB7)
_CST826_ID = const(0x11)

_REG_GESTURE_ID = const(0x01)
_REG_FINGER_NUM = const(0x02)  # Number of fingers currently touching the screen
_REG_TOUCHDATA = const(0x03)  # 4 bytes:  X[11:8], X[7:0], Y[11:8], Y[7:0]
_REG_CHIP_ID = const(0xA7)
# _REG_PROJ_ID = const(0xA8)
# _REG_FW_VERSION = const(0xA9)
# _REG_FACTORY_ID = const(0xAA)
_REG_SLEEP_MODE = const(0xE5)
_REG_LONG_PRESS_TICK = const(0xEB)
_REG_MOTION_MASK = const(0xEC)
_REG_IRQ_CTL = const(0xFA)
_REG_DIS_AUTOSLEEP = const(0xFE)

MOTION_MASK_CONTINUOUS_LEFT_RIGHT = const(0b100)
MOTION_MASK_CONTINUOUS_UP_DOWN = const(0b010)
MOTION_MASK_DOUBLE_CLICK = const(0b001)

IRQ_EN_TOUCH = const(0x40)
IRQ_EN_CHANGE = const(0x20)
IRQ_EN_MOTION = const(0x10)
IRQ_EN_LONGPRESS = const(0x01)

class CST8XX():
    def __init__(self, bus, address=0x15, rst_pin=None,
                 irq_pin=None, irq_handler=lambda pin: None, irq_en=0x00, motion_mask=0b000):

        self._bus = bus
        self._address = address
        if self._read(_REG_CHIP_ID)[0] not in (_CST816S_ID, _CST816T_ID, _CST816D_ID, _CST820_ID, _CST826_ID):
            raise ValueError("Error:  CST8xx not detected.")
        self.rst = Pin(rst_pin, Pin.OUT) if isinstance(rst_pin, int) else rst_pin
        self.reset()
        self.disable_autosleep()

        self.irq = Pin(irq_pin, Pin.IN, Pin.PULL_UP) if isinstance(irq_pin, int) else irq_pin
        if self.irq:
            self.irq.irq(trigger=Pin.IRQ_FALLING, handler=irq_handler)
            self.set_irq_ctl(irq_en, motion_mask)

    def touched(self):
        return self._read(_REG_FINGER_NUM)[0]

    def get_point(self):
        if self.touched() != 1:
            return None
        xy_data = self._read(_REG_TOUCHDATA, 4)
        x = ((xy_data[0] & 0x0f) << 8) + xy_data[1]
        y = ((xy_data[2] & 0x0f) << 8) + xy_data[3]
        return (x, y)

    def get_gestures(self):
        if not self.touched():
            return None
        return self._read(_REG_GESTURE_ID)[0]
    
    def get_points(self):
        raise NotImplementedError("get_points() not implemented (yet)")

    def reset(self):
        if self.rst:
            self.rst(0)
            sleep_ms(1)
            self.rst(1)
            sleep_ms(50)

    def disable_autosleep(self, val=0x01):
        self._write(_REG_DIS_AUTOSLEEP, val)

    def set_irq_ctl(self, irq_en, motion_mask=0b000): 
        self._write(_REG_IRQ_CTL, irq_en)
        self._write(_REG_MOTION_MASK, motion_mask)

    def set_long_press_tick(self, val):
        self._write(_REG_LONG_PRESS_TICK, val)

    def set_sleep_mode(self, val):
        self._write(_REG_SLEEP_MODE, val)

    def _read(self, reg, length=1):
        return self._bus.readfrom_mem(self._address, int(reg), length)
    
    def _write(self, reg, val):
        self._bus.writeto_mem(self._address, int(reg), bytes([int(val)]))
