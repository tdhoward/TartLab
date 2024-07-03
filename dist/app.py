# This file gets overwritten by TartLab IDE when you select an app as the startup app.
# For now, this is just a test app that blinks an LED hooked to GPIO1.
import machine
import time

led = machine.Pin(1, machine.Pin.OUT)

def blink(n):
	led.on()
	time.sleep(n)
	led.off()
	time.sleep(n)
	
for i in range(20):
	blink(0.05)
