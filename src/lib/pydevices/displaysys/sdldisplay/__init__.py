# SPDX-FileCopyrightText: 2024 Brad Barnett
#
# SPDX-License-Identifier: MIT

"""
displaysys.sdldisplay
"""

from displaysys import DisplayDriver, color_rgb
from eventsys import events
from sys import implementation
from micropython import schedule
from ._sdl2_lib import (
    SDL_Init,
    SDL_Quit,
    SDL_GetError,
    SDL_CreateWindow,
    SDL_CreateRenderer,
    SDL_DestroyWindow,
    SDL_DestroyRenderer,
    SDL_DestroyTexture,
    SDL_SetRenderDrawColor,
    SDL_RenderPresent,
    SDL_RenderSetLogicalSize,
    SDL_SetWindowSize,
    SDL_RenderCopyEx,
    SDL_SetRenderTarget,
    SDL_SetTextureBlendMode,
    SDL_RenderFillRect,
    SDL_RenderCopy,
    SDL_UpdateTexture,
    SDL_CreateTexture,
    SDL_PIXELFORMAT_ARGB8888,
    SDL_PIXELFORMAT_RGB888,
    SDL_PIXELFORMAT_RGB565,
    SDL_TEXTUREACCESS_TARGET,
    SDL_BLENDMODE_NONE,
    SDL_RENDERER_ACCELERATED,
    SDL_RENDERER_PRESENTVSYNC,
    SDL_WINDOWPOS_CENTERED,
    SDL_WINDOW_SHOWN,
    SDL_INIT_EVERYTHING,
    SDL_Rect,
    SDL_PollEvent,
    SDL_GetKeyName,
    SDL_Event,
    SDL_QUIT,
    SDL_BUTTON_LMASK,
    SDL_BUTTON_MMASK,
    SDL_BUTTON_RMASK,
    SDL_MOUSEBUTTONDOWN,
    SDL_MOUSEBUTTONUP,
    SDL_MOUSEMOTION,
    SDL_MOUSEWHEEL,
    SDL_KEYDOWN,
    SDL_KEYUP,
)

try:
    from typing import Optional, Union, Sequence
except ImportError:
    pass

if implementation.name == "cpython":
    import ctypes

    is_cpython = True
else:
    is_cpython = False

try:
    from time import ticks_ms, ticks_add
except ImportError:
    from adafruit_ticks import ticks_ms, ticks_add


def scheduler(param):
    func, next_run, interval = param
    if (current_time := ticks_ms()) >= next_run:
        interval = func(interval)
        next_run = ticks_add(current_time, interval)
    if interval > 0:
        schedule(scheduler, (func, next_run, interval))


_event = SDL_Event()


def poll() -> Optional[events]:
    """
    Polls for an event and returns the event type and data.

    Returns:
        Optional[events]: The event type and data.
    """
    global _event
    if SDL_PollEvent(_event):
        if is_cpython:
            if _event.type in events.filter:
                return _convert(SDL_Event(_event))
        else:
            if int.from_bytes(_event[:4], "little") in events.filter:
                return _convert(SDL_Event(_event))
    return None

def _convert(e):
    # Convert an SDL event to a Pygame event
    if e.type == SDL_MOUSEMOTION:
        l = 1 if e.motion.state & SDL_BUTTON_LMASK else 0  # noqa: E741
        m = 1 if e.motion.state & SDL_BUTTON_MMASK else 0
        r = 1 if e.motion.state & SDL_BUTTON_RMASK else 0
        evt = events.Motion(
            e.type,
            (e.motion.x, e.motion.y),
            (e.motion.xrel, e.motion.yrel),
            (l, m, r),
            e.motion.which != 0,
            e.motion.windowID,
        )
    elif e.type in (SDL_MOUSEBUTTONDOWN, SDL_MOUSEBUTTONUP):
        evt = events.Button(
            e.type,
            (e.button.x, e.button.y),
            e.button.button,
            e.button.which != 0,
            e.button.windowID,
        )
    elif e.type == SDL_MOUSEWHEEL:
        evt = events.Wheel(
            e.type,
            e.wheel.direction != 0,
            e.wheel.x,
            e.wheel.y,
            e.wheel.preciseX,
            e.wheel.preciseY,
            e.wheel.which != 0,
            e.wheel.windowID,
        )
    elif e.type in (SDL_KEYDOWN, SDL_KEYUP):
        name = SDL_GetKeyName(e.key.keysym.sym)
        evt = events.Key(
            e.type,
            name,
            e.key.keysym.sym,
            e.key.keysym.mod,
            e.key.keysym.scancode,
            e.key.windowID,
        )
    elif e.type == SDL_QUIT:
        evt = events.Quit(e.type)
    else:
        evt = events.Unknown(e.type)
    return evt

def retcheck(retvalue):
    # Check the return value of an SDL function and raise an exception if it's not 0
    if retvalue:
        raise RuntimeError(SDL_GetError())


class SDLDisplay(DisplayDriver):
    """
    A class to emulate an LCD using SDL2.
    Provides scrolling and rotation functions similar to an LCD.  The .texture
    object functions as the LCD's internal memory.

    Args:
        width (int, optional): The width of the display. Defaults to 320.
        height (int, optional): The height of the display. Defaults to 240.
        rotation (int, optional): The rotation of the display. Defaults to 0.
        color_depth (int, optional): The color depth of the display. Defaults to 16.
        title (str, optional): The title of the display window. Defaults to "SDL2 Display".
        scale (float, optional): The scale of the display. Defaults to 1.0.
        window_flags (int, optional): The flags for creating the display window. Defaults to SDL_WINDOW_SHOWN.
        render_flags (int, optional): The flags for creating the renderer. Defaults to SDL_RENDERER_ACCELERATED | SDL_RENDERER_PRESENTVSYNC.
        x (int, optional): The x-coordinate of the display window's position. Defaults to SDL_WINDOWPOS_CENTERED.
        y (int, optional): The y-coordinate of the display window's position. Defaults to SDL_WINDOWPOS_CENTERED.
    """

    def __init__(
        self,
        width=320,
        height=240,
        rotation=0,
        color_depth=16,
        title="SDL2 Display",
        scale=1.0,
        window_flags=SDL_WINDOW_SHOWN,
        render_flags=SDL_RENDERER_ACCELERATED | SDL_RENDERER_PRESENTVSYNC,
        x=SDL_WINDOWPOS_CENTERED,
        y=SDL_WINDOWPOS_CENTERED,
    ):
        self._width = width
        self._height = height
        self._rotation = rotation
        self.color_depth = color_depth
        self._title = title
        self._window_flags = window_flags
        self._scale = scale
        self._buffer = None
        self._requires_byteswap = False

        # Determine the pixel format
        if color_depth == 32:
            self._px_format = SDL_PIXELFORMAT_ARGB8888
        elif color_depth == 24:
            self._px_format = SDL_PIXELFORMAT_RGB888
        elif color_depth == 16:
            self._px_format = SDL_PIXELFORMAT_RGB565
        else:
            raise ValueError("Unsupported color_depth")

        retcheck(SDL_Init(SDL_INIT_EVERYTHING))
        self._window = SDL_CreateWindow(
            self._title.encode(),
            x,
            y,
            int(self.width * self._scale),
            int(self.height * self._scale),
            self._window_flags,
        )
        if not self._window:
            raise RuntimeError(f"{SDL_GetError()}")
        self._renderer = SDL_CreateRenderer(self._window, -1, render_flags)
        if not self._renderer:
            raise RuntimeError(f"{SDL_GetError()}")

        self._buffer = SDL_CreateTexture(
            self._renderer,
            self._px_format,
            SDL_TEXTUREACCESS_TARGET,
            self.width,
            self.height,
        )
        if not self._buffer:
            raise RuntimeError(f"{SDL_GetError()}")
        retcheck(SDL_SetTextureBlendMode(self._buffer, SDL_BLENDMODE_NONE))

        super().__init__(auto_refresh=True)

    ############### Required API Methods ################

    def init(self) -> None:
        """
        Initializes the display instance.  Called by __init__ and rotation setter.
        """
        retcheck(
            SDL_SetWindowSize(
                self._window,
                int(self.width * self._scale),
                int(self.height * self._scale),
            )
        )
        retcheck(SDL_RenderSetLogicalSize(self._renderer, self.width, self.height))

        super().vscrdef(
            0, self.height, 0
        )  # Set the vertical scroll definition without calling .render()
        self.vscsad(False)  # Scroll offset; set to False to disable scrolling

    def blit_rect(self, buffer: memoryview, x: int, y: int, w: int, h: int):
        """
        Blits a buffer to the display.

        Args:
            buffer (memoryview): The buffer to blit.
            x (int): The x-coordinate of the buffer.
            y (int): The y-coordinate of the buffer.
            w (int): The width to blit.
            h (int): The height to blit.

        Returns:
            (tuple): A tuple containing the x, y, w, h values.
        """
        pitch = int(w * self.color_depth // 8)
        if len(buffer) != pitch * h:
            raise ValueError("Buffer size does not match dimensions")
        blitRect = SDL_Rect(x, y, w, h)
        if is_cpython:
            if isinstance(buffer, memoryview):
                buffer_array = (ctypes.c_ubyte * len(buffer.obj)).from_buffer(buffer.obj)
            elif type(buffer) is bytearray:
                buffer_array = (ctypes.c_ubyte * len(buffer)).from_buffer(buffer)
            else:
                raise ValueError(
                    f"Buffer is of type {type(buffer)} instead of memoryview or bytearray"
                )
            buffer_ptr = ctypes.c_void_p(ctypes.addressof(buffer_array))
            retcheck(SDL_UpdateTexture(self._buffer, blitRect, buffer_ptr, pitch))
        else:
            retcheck(SDL_UpdateTexture(self._buffer, blitRect, buffer, pitch))
        self.render(blitRect)
        return (x, y, w, h)

    def fill_rect(self, x: int, y: int, w: int, h: int, c: int):
        """
        Fill a rectangle with a color.

        Renders to the texture instead of directly to the window
        to facilitate scrolling and scaling.

        Args:
            x (int): The x-coordinate of the rectangle.
            y (int): The y-coordinate of the rectangle.
            w (int): The width of the rectangle.
            h (int): The height of the rectangle.
            c (int): The color of the rectangle.

        Returns:
            (tuple): A tuple containing the x, y, w, h values
        """
        fillRect = SDL_Rect(x, y, w, h)
        r, g, b = color_rgb(c)

        retcheck(
            SDL_SetRenderTarget(self._renderer, self._buffer)
        )  # Set the render target to the texture
        retcheck(
            SDL_SetRenderDrawColor(self._renderer, r, g, b, 255)
        )  # Set the color to fill the rectangle
        retcheck(SDL_RenderFillRect(self._renderer, fillRect))  # Fill the rectangle on the texture
        retcheck(
            SDL_SetRenderTarget(self._renderer, None)
        )  # Reset the render target back to the window
        self.render(fillRect)
        return (x, y, w, h)

    def pixel(self, x: int, y: int, c: int):
        """
        Set a pixel on the display.

        Args:
            x (int): The x-coordinate of the pixel.
            y (int): The y-coordinate of the pixel.
            c (int): The color of the pixel.

        Returns:
            (tuple): A tuple containing the x, y values.
        """
        return self.blit_rect(bytearray(c.to_bytes(2, "little")), x, y, 1, 1)

    ############### API Method Overrides ################

    def vscrdef(self, tfa: int, vsa: int, bfa: int) -> None:
        """
        Set the vertical scroll definition.

        Args:
            tfa (int): The top fixed area.
            vsa (int): The vertical scroll area.
            bfa (int): The bottom fixed area.
        """
        super().vscrdef(tfa, vsa, bfa)
        self.render()

    def vscsad(self, vssa: Optional[int] = None) -> int:
        """
        Set or get the vertical scroll start address.

        Args:
            vssa (int): The vertical scroll start address. Defaults to None.

        Returns:
            int: The vertical scroll start address.
        """
        if vssa is not None:
            super().vscsad(vssa)
            self.render()
        return self._vssa

    def _rotation_helper(self, value):
        """
        Creates a new texture to use as the buffer and copies the old one,
        applying rotation with SDL_RenderCopyEx.  Destroys the old buffer.

        Args:
            value (int): The new rotation value.
        """

        print("here")
        if (angle := (value % 360) - (self._rotation % 360)) != 0:
            if implementation.name == "cpython":
                tempBuffer = SDL_CreateTexture(
                    self._renderer,
                    self._px_format,
                    SDL_TEXTUREACCESS_TARGET,
                    self.height,
                    self.width,
                )
                if not tempBuffer:
                    raise RuntimeError(f"{SDL_GetError()}")

                retcheck(SDL_SetTextureBlendMode(tempBuffer, SDL_BLENDMODE_NONE))
                retcheck(SDL_SetRenderTarget(self._renderer, tempBuffer))
                if abs(angle) != 180:
                    dstrect = SDL_Rect(
                        (self.height - self.width) // 2,
                        (self.width - self.height) // 2,
                        self.width,
                        self.height,
                    )
                else:
                    dstrect = None
                retcheck(
                    SDL_RenderCopyEx(self._renderer, self._buffer, None, dstrect, angle, None, 0)
                )
                retcheck(SDL_SetRenderTarget(self._renderer, None))
                retcheck(SDL_DestroyTexture(self._buffer))
                self._buffer = tempBuffer
            else:
                retcheck(SDL_DestroyTexture(self._buffer))
                self._buffer = SDL_CreateTexture(
                    self._renderer,
                    self._px_format,
                    SDL_TEXTUREACCESS_TARGET,
                    self.height,
                    self.width,
                )
                if not self._buffer:
                    raise RuntimeError(f"{SDL_GetError()}")
                retcheck(SDL_SetTextureBlendMode(self._buffer, SDL_BLENDMODE_NONE))

    ############### Class Specific Methods ##############

    def render(self, renderRect: Optional[SDL_Rect] = None):
        """
        Render the display.  Automatically called after blitting or filling the display.

        Args:
            renderRect (Optional[SDL_Rect], optional): The rectangle to render. Defaults to None.
        """
        # if (y_start := self.vscsad()) == False:
        if False:
            # The following line is not working on Chromebooks, Ubuntu and Raspberry Pi OS
            retcheck(SDL_RenderCopy(self._renderer, self._buffer, renderRect, renderRect))
        else:
            # Ignore renderRect and render the entire texture to the window in four steps
            y_start = self.vscsad()
            if self._tfa > 0:
                tfaRect = SDL_Rect(0, 0, self.width, self._tfa)
                retcheck(SDL_RenderCopy(self._renderer, self._buffer, tfaRect, tfaRect))

            vsaTopHeight = self._vsa + self._tfa - y_start
            vsaTopSrcRect = SDL_Rect(0, y_start, self.width, vsaTopHeight)
            vsaTopDestRect = SDL_Rect(0, self._tfa, self.width, vsaTopHeight)
            retcheck(SDL_RenderCopy(self._renderer, self._buffer, vsaTopSrcRect, vsaTopDestRect))

            vsaBtmHeight = self._vsa - vsaTopHeight
            vsaBtmSrcRect = SDL_Rect(0, self._tfa, self.width, vsaBtmHeight)
            vsaBtmDestRect = SDL_Rect(0, self._tfa + vsaTopHeight, self.width, vsaBtmHeight)
            retcheck(SDL_RenderCopy(self._renderer, self._buffer, vsaBtmSrcRect, vsaBtmDestRect))

            if self._bfa > 0:
                bfaRect = SDL_Rect(0, self._tfa + self._vsa, self.width, self._bfa)
                retcheck(SDL_RenderCopy(self._renderer, self._buffer, bfaRect, bfaRect))

    def show(self) -> None:
        """
        Show the display.
        """
        SDL_RenderPresent(self._renderer)

    def deinit(self) -> None:
        """
        Deinitializes the sdl2lcd instance.
        """
        retcheck(SDL_DestroyTexture(self._buffer))
        retcheck(SDL_DestroyRenderer(self._renderer))
        retcheck(SDL_DestroyWindow(self._window))
        retcheck(SDL_Quit())
