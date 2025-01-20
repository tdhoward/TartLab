from hdwconfig import display_drv
from displaybuf import DisplayBuffer as SSD
from bmp565 import BMP565
from graphics import FrameBuffer, RGB565
from time import sleep

canvas = SSD(display_drv, SSD.RGB565)

# Set the display orientation to vertical
display_drv.rotation = 0
display_drv.disable_auto_byteswap(False)

canvas.fill(0x0)
canvas.show()
bmp = BMP565("files/assets/warrior.bmp")
fb = FrameBuffer(bmp.buffer, bmp.width, bmp.height, RGB565)

canvas.blit(fb, 0, 0)
canvas.show()
