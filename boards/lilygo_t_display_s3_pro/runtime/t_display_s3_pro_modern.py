"""TartLab board payload for the LilyGO T-Display-S3 Pro.

Board pins, native bus configuration, panel geometry, touch-controller quirks,
and rotation choices live in this board-owned payload so the reusable modern
rendering adapter stays board-agnostic.
"""

from tartlabutils.modern import ModernDisplayController, ModernPlatform


IDE_BUTTON_PIN = 12


def create_t_display_s3_pro_platform():
    """Construct the pinned T-Display-S3 Pro native LVGL platform."""
    import cst226
    import i2c
    import lcd_bus
    import lvgl as lv
    import machine
    import st7796
    import task_handler

    spi = machine.SPI.Bus(host=1, mosi=17, miso=8, sck=18)
    bus = lcd_bus.SPIBus(spi_bus=spi, freq=60_000_000, dc=9, cs=39)
    flags = lcd_bus.MEMORY_INTERNAL | lcd_bus.MEMORY_DMA
    buffer_size = 480 * 24 * 2
    frame_buffer1 = bus.allocate_framebuffer(buffer_size, flags)
    frame_buffer2 = bus.allocate_framebuffer(buffer_size, flags)
    if frame_buffer1 is None or frame_buffer2 is None:
        raise MemoryError("unable to allocate dual DMA display buffers")

    panel = st7796.ST7796(
        data_bus=bus,
        display_width=222,
        display_height=480,
        frame_buffer1=frame_buffer1,
        frame_buffer2=frame_buffer2,
        reset_pin=47,
        reset_state=st7796.STATE_LOW,
        backlight_pin=48,
        backlight_on_state=st7796.STATE_PWM,
        offset_x=0,
        offset_y=49,
        color_space=lv.COLOR_FORMAT.RGB565_SWAPPED,
        color_byte_order=st7796.BYTE_ORDER_BGR,
        rgb565_byte_swap=False,
    )
    panel.reset()
    panel.init()
    panel.set_color_inversion(True)

    i2c_bus = i2c.I2C.Bus(
        host=0, scl=6, sda=5, freq=100000, use_locks=False)
    touch_device = i2c.I2C.Device(
        bus=i2c_bus, dev_id=cst226.I2C_ADDR, reg_bits=cst226.BITS)
    pointer = cst226.CST226(
        touch_device, reset_pin=13, interrupt_pin=21,
        # LVGL rotates pointer coordinates with the display. Keep the
        # controller's raw portrait coordinates unrotated here.
        startup_rotation=lv.DISPLAY_ROTATION._0)

    panel.set_rotation(lv.DISPLAY_ROTATION._270)
    panel.set_backlight(100)
    handler = task_handler.TaskHandler()
    lv_display = lv.display_get_default()
    controller = ModernDisplayController(
        bus, panel, lv_display, lv, handler, pointer,
        width=480, height=222, offset_x=0, offset_y=49,
        allocation_flags=flags,
        buffer_allocator=lcd_bus.allocate_buffer,
        buffer_free=lcd_bus.free_buffer)
    platform = ModernPlatform(
        controller, panel, pointer, ide_button_pin=12, lvgl=lv,
        # This CST226SE fixture forgets its no-autosleep setting after a long
        # idle. Reassert it while IDE mode owns the touch input.
        touch_keep_awake=lambda: pointer._write_reg(0xFE, 0x01))
    # Keep native bus wrappers alive for the lifetime of the platform.
    platform._spi_bus = spi
    platform._i2c_bus = i2c_bus
    platform._touch_device = touch_device
    return platform


def create_platform():
    return create_t_display_s3_pro_platform()
