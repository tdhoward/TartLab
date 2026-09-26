"""Bounded touch-bus inspection; no controller writes or SD mount changes."""


def touch_bus_probe(config):
    import machine
    import time

    pins = {pin["type"]: pin["number"] for pin in config["pins"]}
    touch = config["touch"]
    sda = machine.Pin(pins["TOUCH_SDA"], machine.Pin.OPEN_DRAIN,
                      machine.Pin.PULL_UP, value=1)
    scl = machine.Pin(pins["TOUCH_SCL"], machine.Pin.OPEN_DRAIN,
                      machine.Pin.PULL_UP, value=1)
    time.sleep_ms(10)
    report = {"board_id": config["id"], "released_sda": sda.value(),
              "released_scl": scl.value(), "frequency_hz": touch["i2c"]["frequency"],
              "transport": "SoftI2C", "controller_valid": False}
    # A low data line can falsely acknowledge every address, including the
    # reset expander. Never issue register transactions on that evidence.
    if not report["released_sda"] or not report["released_scl"]:
        report["error"] = "touch bus is not idle; controller transactions skipped"
        return report
    bus = machine.SoftI2C(sda=sda, scl=scl, freq=touch["i2c"]["frequency"])
    addresses = bus.scan()
    report["addresses"] = addresses
    report["after_scan_sda"] = sda.value()
    report["after_scan_scl"] = scl.value()
    if not report["after_scan_sda"] or not report["after_scan_scl"]:
        report["error"] = "touch bus is not idle after scan; controller transactions skipped"
        return report
    if set(addresses) == set(range(0x08, 0x78)):
        report["error"] = "all scanned I2C addresses acknowledge; invalid bus"
        return report
    if touch["driver"] != "gt911.GT911":
        report["error"] = "controller identity inspection unsupported"
        return report
    report["controllers"] = []
    for address in touch["addresses"]:
        if address not in addresses:
            continue
        current = {"address": address}
        try:
            product = bus.readfrom_mem(address, 0x8140, 4, addrsize=16)
            geometry = bus.readfrom_mem(address, 0x8146, 4, addrsize=16)
            current["product"] = list(product)
            current["geometry"] = list(geometry)
            width = geometry[0] | geometry[1] << 8
            height = geometry[2] | geometry[3] << 8
            current["valid"] = product == b"911\x00" and width > 0 and height > 0
            report["controller_valid"] |= current["valid"]
        except OSError as error:
            current["error"] = repr(error)
        report["controllers"].append(current)
    if not report["controller_valid"]:
        report["error"] = "no valid GT911 identity and geometry"
    return report
