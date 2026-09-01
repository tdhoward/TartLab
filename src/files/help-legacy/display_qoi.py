from hdwconfig import display_drv
from displaybuf import DisplayBuffer as SSD
from qoi_reader import QOIImage
from graphics import FrameBuffer, RGB565
from time import sleep

display_drv.rotation = 0  # Set the display orientation to vertical
canvas = SSD(display_drv, SSD.RGB565)
display_drv.disable_auto_byteswap(False)

canvas.fill(0x0)
canvas.show()
img = QOIImage.open("files/assets/test.qoi")
display_drv.blit(img.pixels, 0, 0, img.width, img.height)
'''
fb = FrameBuffer(img.pixels, img.width, img.height, RGB565)

canvas.blit(fb, 0, 0)
canvas.show()
'''
