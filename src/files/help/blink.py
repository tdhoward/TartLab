# Blink an LED
import machine
import time

led = machine.Pin(1, machine.Pin.OUT)

def blink(delay):
	led.on()
	time.sleep(delay)
	led.off()
	time.sleep(delay)
	
for i in range(20):  # blink 20 times
	blink(0.1)  # Use a 0.1 second delay
