"""Temporary normal-startup GT911 diagnostics; never installed in releases.

No bus retries, scans after failure, pin initialization or callback SD writes.
Rows: sequence, ticks_us, operation, address, register, length, errno,
duration_us, poll, phase, heartbeat, first six data bytes (or -1).
"""
import time
import json
import machine
import gt911
import lvgl as lv

history = [[0] * 17 for _ in range(32)]
initial = []
sequence = 0
polls = 0
beats = 0
phase = 'touch_init'
failed = False
failure = None
pressed_polls = 0
last_point = None
coordinate_reads = 0
last_raw_point = None
status_reads = 0
ready_statuses = 0
config = None
timer = None
last_report = 0


def mark(value):
    global phase
    phase = value


def call(value, function, *args, **kwargs):
    mark(value)
    return function(*args, **kwargs)


def registers():
    result = {}
    for name, address in config['snapshot_registers'].items():
        try:
            result[name] = machine.mem32[address]
        except Exception as error:
            result[name] = repr(error)
    return result


def emit(kind, value):
    print('TOUCH_REC=' + json.dumps({'kind': kind, 'value': value}))


def report(unused=None):
    global beats, last_report
    beats += 1
    now = time.ticks_ms()
    if time.ticks_diff(now, last_report) >= 10000:
        last_report = now
        emit('heartbeat', {'ms': now, 'beats': beats, 'polls': polls,
                          'transactions': sequence, 'phase': phase,
                          'failed': failed, 'pressed_polls': pressed_polls,
                          'last_point': last_point,
                          'coordinate_reads': coordinate_reads,
                          'last_raw_point': last_raw_point,
                          'status_reads': status_reads,
                          'ready_statuses': ready_statuses})


def install(options):
    global config
    config = options
    read = gt911.GT911._read_reg
    write = gt911.GT911._write_reg
    coords = gt911.GT911._get_coords
    init = gt911.GT911.__init__

    def transact(self, operation, reg, length, call, args, data=None):
        global sequence, failed, failure, coordinate_reads, last_raw_point
        global status_reads, ready_statuses
        if failed:
            raise RuntimeError('Touch recorder has frozen after first failure')
        row = history[sequence % len(history)]
        sequence += 1
        start = time.ticks_us()
        row[0:11] = (sequence, start, operation, self._device.dev_id,
                     reg, length, 0, 0, polls, phase, beats)
        for index in range(11, 17):
            row[index] = -1
        if operation == 'write':
            for index in range(min(length, 6)):
                row[11 + index] = data[index]
        try:
            result = call(self, *args)
        except OSError as error:
            row[6] = error.args[0] if error.args else -1
            row[7] = time.ticks_diff(time.ticks_us(), start)
            failed = True
            # Snapshot before emitting UART output or touching LVGL state.
            try:
                failure = {'row': list(row), 'registers': registers(),
                           'reset_cause': machine.reset_cause(),
                           'history': [list(history[(sequence + n) % len(history)])
                                       for n in range(len(history))]}
                emit('failure', failure)
            except Exception:
                pass
            raise
        row[7] = time.ticks_diff(time.ticks_us(), start)
        if operation == 'read':
            buffer = args[2] if args[2] is not None else self._rx_buf
            for index in range(min(length, 6)):
                row[11 + index] = buffer[index]
            if reg == 0x814E:
                status_reads += 1
                if buffer[0] & 0x80:
                    ready_statuses += 1
            if reg == 0x8150:
                coordinate_reads += 1
                last_raw_point = (buffer[0] | (buffer[1] << 8),
                                  buffer[2] | (buffer[3] << 8))
        if polls == 0 and len(initial) < 32:
            initial.append(list(row))
        return result

    def read_reg(self, reg, num_bytes=None, buf=None):
        return transact(self, 'read', reg,
                        num_bytes if num_bytes is not None else len(buf),
                        read, (reg, num_bytes, buf))

    def write_reg(self, reg, value=None, buf=None):
        if 'command' in config and reg in (0x8040, 0x8046):
            if value != 1 or buf is not None:
                raise ValueError('Unexpected GT911 command write; comparison aborted')
            value = config['command']
        data = (value,) if value is not None else buf
        return transact(self, 'write', reg, len(data), write,
                        (reg, value, buf), data)

    def get_coords(self):
        global polls, pressed_polls, last_point
        if failed:
            return None
        polls += 1
        result = coords(self)
        if result and result[0] == self.PRESSED:
            pressed_polls += 1
            last_point = result[1:]
        return result

    def initialize(self, *args, **kwargs):
        global timer
        init(self, *args, **kwargs)
        emit('init', {'transactions': initial, 'config': config,
                      'reset_cause': machine.reset_cause(),
                      'registers': registers()})
        timer = lv.timer_create(report, 100, None)

    gt911.GT911._read_reg = read_reg
    gt911.GT911._write_reg = write_reg
    gt911.GT911._get_coords = get_coords
    gt911.GT911.__init__ = initialize

    if 'reset' in config:
        install_reset_probe()


def audited_reset(bus, options, perform):
    """PCA9557 RESET/INT audit; pin assignments come from BOARD_CONFIG."""
    global failed, failure
    if options['driver'] != 'PCA9557':
        raise ValueError('Unsupported reset expander')
    address = options['address']
    reset = 1 << options['reset_bit']
    interrupt = 1 << options['interrupt_bit']
    mask = reset | interrupt
    log = []
    pending = None

    def read(reg):
        nonlocal pending
        pending = ('read', address, reg, time.ticks_us())
        value = bus.readfrom_mem(address, reg, 1)[0]
        log.append([time.ticks_ms(), 'read', reg, value])
        return value

    def write(reg, value):
        nonlocal pending
        pending = ('write', address, reg, time.ticks_us())
        bus.writeto_mem(address, reg, bytes((value,)))
        log.append([time.ticks_ms(), 'write', reg, value])
        if read(reg) != value:
            raise ValueError('Expander write readback mismatch')

    try:
        before = [read(reg) for reg in range(4)]
        if perform:
            output, polarity, direction = before[1:]
            write(1, output & ~mask)
            write(3, direction & ~mask)
            time.sleep_ms(options['assert_ms'])
            if (read(0) ^ polarity) & mask:
                raise ValueError('RESET/INT did not both read low')
            write(1, (output & ~mask) | reset)
            time.sleep_ms(options['release_ms'])
            if (read(0) ^ polarity) & mask != reset:
                raise ValueError('Released RESET/selected INT levels mismatch')
            write(3, (direction & ~reset) | interrupt)
            # Goodix requires settling after INT becomes a floating input.
            time.sleep_ms(config['reset_settle_ms'])
        after = [read(reg) for reg in range(4)]
        emit('reset_audit', {'performed': perform, 'before': before,
                            'after': after, 'io': log,
                            'settle_ms': config['reset_settle_ms'] if perform else 0})
    except OSError as error:
        failed = True
        try:
            failure = {'reset_io': log, 'pending': pending, 'errno': error.args[0],
                       'phase': phase, 'registers': registers()}
            emit('failure', failure)
        except Exception:
            pass
        raise
    except Exception:
        emit('reset_validation_failure', {'io': log, 'pending': pending})
        raise


def install_reset_probe():
    import i2c
    from tartlabutils import factory
    original_touch = factory._touch
    original_scan = i2c.I2C.Bus.scan
    pending_board = None

    def scan(bus):
        nonlocal pending_board
        if pending_board is not None:
            board = pending_board
            pending_board = None
            mark('expander_reset' if config['reset'] else 'expander_observe')
            audited_reset(bus, board['touch']['reset_expander'], config['reset'])
        result = original_scan(bus)
        emit('scan', result)
        mark('touch_init')
        return result

    def touch(board, lvgl):
        nonlocal pending_board
        pending_board = board
        try:
            return original_touch(board, lvgl)
        finally:
            pending_board = None

    factory._touch = touch
    i2c.I2C.Bus.scan = scan
