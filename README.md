# TartLab
Lite web-based MicroPython IDE for embedded devices.

## Goals
The primary goal of this project is to enable embedded device programming in a classroom setting while allowing the students to bring their own laptops, tablets, etc.  Trying to install USB drivers and applications (such as the Arduino IDE) becomes impractical for larger class sizes, and introduces many unnecessary complications to what should otherwise be fairly simple.

Since many embedded devices have WiFi connectivity built in, why not serve a tiny web-based IDE directly from the device?  Once set up, the IDE can be used without the need for any particular drivers, applications, or operating systems.  It can be accessed from any browser, from desktop PCs and Macs to Chromebooks, tablets, or phones.  The files are loaded and saved directly on the embedded device.

Additionally, it would be great if a community of embedded Python developers would get their start on TartLab and then continue to improve it for others.

## Requirements
 * Embedded module: Must be able to run MicroPython and have WiFi  (See below for more details.)
 * Embedded storage: 2MB minimum, 4MB recommended
 * Client device (for development): Any device with a relatively modern browser

## Installation
 1. Install [MicroPython](https://micropython.org/) on the embedded device.  Sometimes there are special builds of MicroPython that are specific to your device, such as the [build for LilyGo T-Display-S3](https://github.com/russhughes/s3lcd).
 2. Use [mpsync](https://github.com/tdhoward/mpsync) to load the TartLab "dist" files onto the device.
 3. Enjoy!

## Usage
There are two different modes of operation:
 * Normal operation:  If the user applies power or presses the hard-reset button, the device will begin to execute the user's Python code.
 * Development mode:  If the user holds down the development button while powering up or resetting, the device will begin serving the TartLab IDE.

## Recommended embedded devices
Any device using an ESP32 or ESP8266 processor and providing WiFi support should work.  Devices with LCD screens are highly recommended, as that simplifies the connection process for the first time.
LilyGo devices (T-Display-S3) were used to test and develop TartLab, so those should work great.
