import time
from machine import Pin, I2C

"""
Usage:

from i2c_test import TouchClassCST226
from machine import I2C, Pin
i2c = I2C(0, sda=Pin(5), scl=Pin(6), freq=100000)
DEVICE_ADDRESS = 90
touchpad = TouchClassCST226(i2c, DEVICE_ADDRESS, rst_pin=13, irq_pin=21)
touchpad.initImpl()

"""

# Constants (you might need to define these based on your setup)
SENSOR_PIN_NONE = None
OUTPUT = Pin.OUT
INPUT = Pin.IN

class TouchClassCST226:
    def __init__(self, i2c, device_address, rst_pin=None, irq_pin=None):
        self.i2c = i2c
        self.device_address = device_address
        self.__rst = rst_pin
        self.__irq = irq_pin
        self.__rst_pin = None
        self.__irq_pin = None
        self.__resX = 0
        self.__resY = 0
        self.__chipID = 0

    def setGpioMode(self, pin_num, mode):
        pin = Pin(pin_num, mode)
        if mode == OUTPUT:
            self.__rst_pin = pin
        elif mode == INPUT:
            self.__irq_pin = pin

    def reset(self):
        if self.__rst_pin:
            self.__rst_pin.value(0)
            time.sleep_ms(10)
            self.__rst_pin.value(1)
            time.sleep_ms(50)
        else:
            pass  # No reset pin defined

    def writeRegister(self, addr, value):
        data = bytearray([addr, value])
        self.i2c.writeto(self.device_address, data)

    def writeThenRead(self, write_buffer, read_buffer, read_length):
        self.i2c.writeto(self.device_address, write_buffer)
        read_data = self.i2c.readfrom(self.device_address, read_length)
        for i in range(read_length):
            read_buffer[i] = read_data[i]

    def initImpl(self):
        if self.__rst != SENSOR_PIN_NONE:
            self.setGpioMode(self.__rst, OUTPUT)

        if self.__irq != SENSOR_PIN_NONE:
            self.setGpioMode(self.__irq, INPUT)

        self.reset()

        buffer = bytearray(8)
        # Enter Command mode
        self.writeRegister(0xD1, 0x01)
        time.sleep_ms(10)
        write_buffer = bytearray([0xD1, 0xFC])
        self.writeThenRead(write_buffer, buffer, 4)
        checkcode = (buffer[3] << 24) | (buffer[2] << 16) | (buffer[1] << 8) | buffer[0]

        print("Chip checkcode:0x%08X.\r\n" % checkcode)

        write_buffer[0] = 0xD1
        write_buffer[1] = 0xF8
        self.writeThenRead(write_buffer, buffer, 4)
        self.__resX = (buffer[1] << 8) | buffer[0]
        self.__resY = (buffer[3] << 8) | buffer[2]
        print("Chip resolution X:%u Y:%u\r\n" % (self.__resX, self.__resY))

        write_buffer[0] = 0xD2
        write_buffer[1] = 0x04
        self.writeThenRead(write_buffer, buffer, 4)
        chipType = (buffer[3] << 8) | buffer[2]
        ProjectID = (buffer[1] << 8) | buffer[0]
        print("Chip type :0x%04X, ProjectID:0X%04X\r\n" % (chipType, ProjectID))

        write_buffer[0] = 0xD2
        write_buffer[1] = 0x08
        self.writeThenRead(write_buffer, buffer, 8)

        fwVersion = (buffer[3] << 24) | (buffer[2] << 16) | (buffer[1] << 8) | buffer[0]
        checksum = (buffer[7] << 24) | (buffer[6] << 16) | (buffer[5] << 8) | buffer[4]

        print("Chip ic version:0x%08X, checksum:0x%08X\n" % (fwVersion, checksum))

        if fwVersion == 0xA5A5A5A5:
            print("Chip ic doesn't have firmware.\n")
            return False
        if (checkcode & 0xFFFF0000) != 0xCACA0000:
            print("Firmware info read error.\n")
            return False

        self.__chipID = chipType

        # Exit Command mode
        self.writeRegister(0xD1, 0x09)
        return True
