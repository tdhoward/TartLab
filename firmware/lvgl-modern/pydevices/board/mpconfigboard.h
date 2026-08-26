#define MICROPY_HW_BOARD_NAME               "TartLab T-Display-S3 Pro"
#define MICROPY_HW_MCU_NAME                 "ESP32S3"

// The board's USB connector is wired to the ESP32-S3 USB Serial/JTAG block.
#define MICROPY_HW_ENABLE_UART_REPL         (0)
#define MICROPY_HW_ENABLE_USBDEV            (0)
#define MICROPY_HW_USB_CDC                  (0)
#define MICROPY_HW_ESP_USB_SERIAL_JTAG      (1)

#define MICROPY_HW_I2C0_SCL                 (6)
#define MICROPY_HW_I2C0_SDA                 (5)
