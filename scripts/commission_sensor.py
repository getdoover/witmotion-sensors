#!/usr/bin/env python3
"""Commissioning tool: set a WitMotion WTVB01-485 sensor's Modbus address + baud.

Out of the box every WTVB01-485 ships on slave id 80 (0x50) @ 9600 8N1. On a
bus with more than one sensor that's a collision, so during commissioning
each unit is given a unique address (and optionally a different baud) one at
a time — connect a single sensor, run this, move to the next.

    # give the connected sensor address 10, keep 9600 baud
    python scripts/commission_sensor.py --new-id 10

    # address 11 and bump it to 115200 baud
    python scripts/commission_sensor.py --new-id 11 --new-baud 115200

    # talk to a sensor that's NOT on the defaults (e.g. re-addressing)
    python scripts/commission_sensor.py --from-id 10 --from-baud 115200 --new-id 12

    # also set the output rate, and read everything back afterwards
    python scripts/commission_sensor.py --new-id 10 --sample-rate 50 --verify

    # blow it back to factory defaults (id 80 @ 9600)
    python scripts/commission_sensor.py --from-id 10 --factory-reset

    # just read back the registers without changing anything
    python scripts/commission_sensor.py --check

Unlike the ProSense family, WitMotion config writes are gated behind an
unlock key and persisted with an explicit save, so every change here runs
the full unlock -> write -> save sequence (write 0xB588 to reg 0x69, write
the value, then write 0x0000 to reg 0x00). WitMotion applies an address or
baud change *immediately* — observed on the register write itself, before
the save — so this tool re-discovers the sensor (possibly at a new address
and/or line speed) before sending the save, which is what makes the change
persist to flash. Without that, the change lives only in RAM and is lost on
the next power cycle. The save target is resolved automatically, and --check
is a read-only way to confirm comms.

Only dependency is pyserial (`pip install pyserial`); the Modbus RTU framing
is done here so there's no pymodbus version dance. The register map, keys and
the slave-id range are imported from the app's registers module so this tool
can never drift from what the running app expects.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

# Reuse the app's register map + keys rather than re-deriving them. We import
# the bare registers module file directly (adding its dir to the path) rather
# than `witmotion_sensors.registers` — the latter would run the package
# __init__, which pulls in pydoover and the whole app. registers.py only needs
# the stdlib, so a commissioning tool can use it with nothing else installed.
# Candidates: the in-repo package dir, and the script's own dir (the flat
# copy made by the remote-run wrapper).
_HERE = Path(__file__).resolve().parent
for _candidate in (_HERE.parent / "src" / "witmotion_sensors", _HERE):
    if _candidate.is_dir():
        sys.path.insert(0, str(_candidate))

from registers import (  # type: ignore  # noqa: E402
    BAUD_REG, FACTORY_RESET_KEY, RESTART_KEY, SAMPLE_RATE_REG,
    SAVE_KEY, SAVE_REG, SLAVE_ID_REG, UNLOCK_KEY, UNLOCK_REG,
)

FC_READ_HOLDING = 0x03
FC_WRITE_SINGLE = 0x06

# WitMotion baud register codes. Code 2 == 9600 is confirmed by the app's
# simulator seed (simulators/sample/main.py); the rest follow the WTVB01-485
# manual's table.
WIT_BAUD_CODES: dict[int, int] = {
    4800: 1,
    9600: 2,
    19200: 3,
    38400: 4,
    57600: 5,
    115200: 6,
    230400: 7,
}

SLAVE_ID_MIN, SLAVE_ID_MAX = 0x01, 0x7F   # app enforces [1, 127]
SAMPLE_RATE_MIN, SAMPLE_RATE_MAX = 1, 200


# ---- Modbus RTU framing ------------------------------------------------

def crc16(data: bytes) -> int:
    """Standard Modbus RTU CRC-16 (poly 0xA001), returned host-order."""
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
    return crc


def _frame(payload: bytes) -> bytes:
    crc = crc16(payload)
    return payload + bytes([crc & 0xFF, (crc >> 8) & 0xFF])


class ModbusError(RuntimeError):
    pass


class RtuClient:
    """Minimal Modbus RTU master over a serial line — FC03 read, FC06 write.

    ``transport`` is injectable for testing; when None a real pyserial port
    is opened. Re-opening at a new baud (after a WitMotion baud change) is
    done via :meth:`set_baud`.
    """

    def __init__(self, port, baud, parity, timeout, transport=None):
        self._port = port
        self._parity = parity
        self._timeout = timeout
        self._baud = baud
        self._injected = transport is not None
        self._ser = transport if transport is not None else self._open(baud)

    def _open(self, baud):
        try:
            import serial  # pyserial — imported lazily so --help works without it
        except ModuleNotFoundError:
            sys.exit("pyserial is required: `pip install pyserial` "
                     "(or `uv pip install pyserial`).")
        return serial.Serial(
            port=self._port, baudrate=baud,
            parity={"none": serial.PARITY_NONE, "even": serial.PARITY_EVEN,
                    "odd": serial.PARITY_ODD}[self._parity],
            stopbits=serial.STOPBITS_ONE, bytesize=serial.EIGHTBITS,
            timeout=self._timeout,
        )

    @property
    def baud(self):
        return self._baud

    def set_baud(self, baud):
        self._baud = baud
        if self._injected:
            return
        try:
            self._ser.baudrate = baud
        except Exception:
            self._ser.close()
            self._ser = self._open(baud)

    def close(self):
        if not self._injected:
            self._ser.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def _txn(self, slave, payload, expected_len):
        request = _frame(bytes([slave]) + payload)
        self._ser.reset_input_buffer()
        self._ser.write(request)
        self._ser.flush()
        resp = self._ser.read(expected_len)
        if len(resp) < 3:
            raise ModbusError(
                f"no/short response from slave {slave} "
                f"(got {len(resp)} bytes — wrong address, baud, or wiring?)"
            )
        if crc16(resp[:-2]) != (resp[-2] | (resp[-1] << 8)):
            raise ModbusError(f"bad CRC in response from slave {slave}: {resp.hex()}")
        if resp[1] & 0x80:
            code = resp[2] if len(resp) > 2 else -1
            raise ModbusError(f"slave {slave} returned Modbus exception 0x{code:02X}")
        return resp

    def read_holding(self, slave, start, count):
        payload = bytes([FC_READ_HOLDING,
                         (start >> 8) & 0xFF, start & 0xFF,
                         (count >> 8) & 0xFF, count & 0xFF])
        resp = self._txn(slave, payload, 5 + 2 * count)
        byte_count = resp[2]
        data = resp[3:3 + byte_count]
        if len(data) < 2 * count:
            raise ModbusError(f"short register payload from slave {slave}: {resp.hex()}")
        return [(data[i] << 8) | data[i + 1] for i in range(0, 2 * count, 2)]

    def write_single(self, slave, register, value):
        value &= 0xFFFF
        payload = bytes([FC_WRITE_SINGLE,
                         (register >> 8) & 0xFF, register & 0xFF,
                         (value >> 8) & 0xFF, value & 0xFF])
        resp = self._txn(slave, payload, 8)  # FC06 echoes the 8-byte request
        echoed_reg = (resp[2] << 8) | resp[3]
        echoed_val = (resp[4] << 8) | resp[5]
        if echoed_reg != register or echoed_val != value:
            raise ModbusError(
                f"slave {slave} echo mismatch on write to 0x{register:02X}: "
                f"sent 0x{value:04X}, echoed reg=0x{echoed_reg:02X} val=0x{echoed_val:04X}"
            )


# ---- WitMotion write sequences ----------------------------------------

def _write(client, addr, reg, val, label, *, tolerant=False):
    print(f"    · write 0x{val:04X} → reg 0x{reg:02X} ({label})")
    try:
        client.write_single(addr, reg, val)
        return True
    except ModbusError as exc:
        if tolerant:
            print(f"      (no echo: {exc})")
            return False
        raise


def resolve(client, addr_candidates, baud_candidates):
    """Find which (addr, baud) the sensor currently answers on.

    WitMotion applies an address/baud change the instant the register is
    written — *before* the trailing save — so after writing one we have to
    rediscover the sensor (possibly at a new address and/or line speed)
    before we can save. Leaves the client tuned to the baud that worked;
    returns (addr, baud) or (None, None) if nothing answered.
    """
    for baud in dict.fromkeys(baud_candidates):
        client.set_baud(baud)
        for addr in dict.fromkeys(addr_candidates):
            try:
                client.read_holding(addr, SLAVE_ID_REG, 1)
                return addr, baud
            except ModbusError:
                continue
    return None, None


def unlock_write_save(client, addr, reg, val, label, *,
                      addr_candidates, baud_candidates, value_tolerant=False):
    """Unlock → write → save, re-finding the sensor before the save.

    The unlock and value write go to the current address at the current
    baud. The value write may move the sensor to a new address/baud
    immediately, so we resolve where it is *now* and address the save there
    — that's what makes the change persist to flash. Returns the (addr,
    baud) the sensor ended up on.
    """
    print(f"  → {label}")
    write_baud = client.baud
    _write(client, addr, UNLOCK_REG, UNLOCK_KEY, "unlock")
    _write(client, addr, reg, val, label, tolerant=value_tolerant)

    # Where is the sensor now? The change may have applied on the write
    # (some firmware) so we resolve before saving and address the save there.
    sa, sb = _resolve_or(client, addr_candidates, baud_candidates, addr, write_baud)
    if sa != addr or sb != write_baud:
        print(f"    (sensor now at id {sa} @ {sb} baud — saving there)")
    _write(client, sa, SAVE_REG, SAVE_KEY, "save")

    # On other firmware the change applies on the save itself, so resolve
    # once more to report the true post-save address/baud to the caller.
    fa, fb = _resolve_or(client, addr_candidates, baud_candidates, sa, sb)
    return fa, fb


def _resolve_or(client, addr_candidates, baud_candidates, default_addr, default_baud):
    """resolve(), falling back to a default (and retuning to it) if nothing answers."""
    ra, rb = resolve(client, addr_candidates, baud_candidates)
    if ra is None:
        ra, rb = default_addr, default_baud
        client.set_baud(rb)
    return ra, rb


# ---- commissioning flow ------------------------------------------------

def commission(args):
    if not (SLAVE_ID_MIN <= args.new_id <= SLAVE_ID_MAX) and not args.factory_reset:
        raise ValueError(f"--new-id must be in [{SLAVE_ID_MIN}, {SLAVE_ID_MAX}], "
                         f"got {args.new_id}")
    new_baud_code = WIT_BAUD_CODES[args.new_baud] if args.new_baud else None
    if args.sample_rate is not None and not (SAMPLE_RATE_MIN <= args.sample_rate <= SAMPLE_RATE_MAX):
        raise ValueError(f"--sample-rate must be in [{SAMPLE_RATE_MIN}, {SAMPLE_RATE_MAX}]")

    print(f"Opening {args.port} @ {args.from_baud} {args.parity[0].upper()}81 "
          f"(reaching sensor at slave id {args.from_id})")

    with RtuClient(args.port, args.from_baud, args.parity, args.timeout) as client:
        # 1. Confirm comms before touching anything.
        try:
            regs = client.read_holding(args.from_id, BAUD_REG, 1)
            cur_id = client.read_holding(args.from_id, SLAVE_ID_REG, 1)[0]
        except ModbusError as exc:
            print(f"  ✗ can't reach sensor: {exc}", file=sys.stderr)
            return 2
        cur_baud_code = regs[0]
        print(f"  ✓ found sensor: slave id {cur_id}, baud code {cur_baud_code} "
              f"({_baud_from_code(cur_baud_code) or '?'} baud)")

        if args.check:
            print("  ✓ comms OK — read-only check, nothing written.")
            return 0

        if args.dry_run:
            print("  (dry run — no writes performed)")
            _print_plan(args, new_baud_code)
            return 0

        # 2. Factory reset is standalone — it returns the sensor to id 80 @ 9600.
        #    Same unlock → reset-key → save shape the app uses, but the reset
        #    may reboot the sensor, so a dropped reply on the trailing save is
        #    expected rather than an error.
        if args.factory_reset:
            print("  → factory reset")
            _write(client, args.from_id, UNLOCK_REG, UNLOCK_KEY, "unlock")
            _write(client, args.from_id, SAVE_REG, FACTORY_RESET_KEY, "factory reset")
            try:
                _write(client, args.from_id, SAVE_REG, SAVE_KEY, "save")
            except ModbusError:
                print("    (no ack on trailing save — sensor likely already reset)")
            print("\n  ✓ factory reset issued — sensor returns to id 80 @ 9600 baud.")
            return 0

        addr = args.from_id

        # 3. Sample rate (doesn't change addressing).
        if args.sample_rate is not None:
            addr, _ = unlock_write_save(
                client, addr, SAMPLE_RATE_REG, args.sample_rate,
                f"set output rate to {args.sample_rate} Hz",
                addr_candidates=[addr], baud_candidates=[client.baud])

        # 4. Slave id. WitMotion applies it the instant the register is
        #    written, so the save must follow to the *new* address — let
        #    unlock_write_save resolve that. We track the live address.
        if args.new_id != args.from_id:
            addr, _ = unlock_write_save(
                client, addr, SLAVE_ID_REG, args.new_id,
                f"set slave id to {args.new_id}",
                addr_candidates=[args.new_id, addr], baud_candidates=[client.baud])

        # 5. Baud LAST — changing it shifts the line speed out from under us,
        #    so nothing else may follow. The value write may flip the line to
        #    the new baud immediately (its echo can be lost in the switch, so
        #    it's tolerant), and the save follows at whichever baud answers.
        if new_baud_code is not None:
            addr, _ = unlock_write_save(
                client, addr, BAUD_REG, new_baud_code,
                f"set baud to {args.new_baud} (code {new_baud_code})",
                addr_candidates=[addr], baud_candidates=[args.new_baud, client.baud],
                value_tolerant=True)
            if args.restart:
                _write(client, addr, UNLOCK_REG, UNLOCK_KEY, "unlock")
                _write(client, addr, SAVE_REG, RESTART_KEY, "restart", tolerant=True)

        print("  ✓ writes accepted and saved")

        if args.verify:
            _verify(client, addr, args)

    return 0


def _verify(client, addr, args):
    verify_baud = args.new_baud or args.from_baud
    print(f"\nVerifying: looking for the sensor @ {verify_baud} baud ...")
    if args.verify_delay:
        time.sleep(args.verify_delay)
    # Try the resolved address/baud first, then fall back to the originals in
    # case this unit applies changes on restart rather than live.
    addr_cands = list(dict.fromkeys([addr, args.new_id, args.from_id]))
    baud_cands = list(dict.fromkeys([verify_baud, args.from_baud]))
    found, fbaud = resolve(client, addr_cands, baud_cands)
    if found is None:
        print("  · no answer at the new settings. If this unit applies changes "
              "only on restart, power-cycle it and re-run with --check "
              f"--from-id {args.new_id}"
              + (f" --from-baud {args.new_baud}" if args.new_baud else "")
              + " to confirm.")
        return
    sid = client.read_holding(found, SLAVE_ID_REG, 1)[0]
    bcode = client.read_holding(found, BAUD_REG, 1)[0]
    print(f"  ✓ sensor reports slave id {sid}, baud code {bcode} "
          f"({_baud_from_code(bcode) or '?'} baud) @ {fbaud} line baud")


def _baud_from_code(code):
    for baud, c in WIT_BAUD_CODES.items():
        if c == code:
            return baud
    return None


def _print_plan(args, new_baud_code):
    if args.factory_reset:
        print(f"  would factory-reset (unlock, write 0x{FACTORY_RESET_KEY:04X} "
              f"→ reg 0x{SAVE_REG:02X}, save)")
        return
    if args.sample_rate is not None:
        print(f"  would set output rate → {args.sample_rate} Hz (reg 0x{SAMPLE_RATE_REG:02X})")
    if args.new_id != args.from_id:
        print(f"  would set slave id → {args.new_id} (reg 0x{SLAVE_ID_REG:02X})")
    if new_baud_code is not None:
        print(f"  would set baud → {args.new_baud} / code {new_baud_code} (reg 0x{BAUD_REG:02X})")
    print(f"  each via unlock(0x{UNLOCK_REG:02X}=0x{UNLOCK_KEY:04X}) → write → "
          f"save(0x{SAVE_REG:02X}=0x{SAVE_KEY:04X})")


def build_parser():
    p = argparse.ArgumentParser(
        description="Set a WitMotion WTVB01-485 sensor's Modbus slave id and baud.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--port", default="/dev/ttyAMA0", help="serial device")
    p.add_argument("--check", action="store_true",
                   help="read-only: confirm comms and report id/baud, then exit")
    p.add_argument("--new-id", type=int, default=None,
                   help="new Modbus slave id to assign (1..127); omit with --factory-reset/--check")
    p.add_argument("--new-baud", type=int, default=None, choices=sorted(WIT_BAUD_CODES),
                   help="new baud rate (leave unset to keep the current baud)")
    p.add_argument("--sample-rate", type=int, default=None,
                   help="output rate in Hz (1..200), optional")
    p.add_argument("--from-id", type=int, default=80,
                   help="slave id the sensor currently answers on (factory default 80)")
    p.add_argument("--from-baud", type=int, default=9600, choices=sorted(WIT_BAUD_CODES),
                   help="baud the sensor currently uses")
    p.add_argument("--parity", default="none", choices=("none", "even", "odd"),
                   help="serial parity (sensors ship 8N1)")
    p.add_argument("--timeout", type=float, default=1.0, help="per-response timeout (s)")
    p.add_argument("--factory-reset", action="store_true",
                   help="reset the sensor to factory defaults (id 80 @ 9600) and exit")
    p.add_argument("--restart", action="store_true",
                   help="after a baud change, also issue the restart key")
    p.add_argument("--verify", action="store_true",
                   help="re-read the registers back after writing")
    p.add_argument("--verify-delay", type=float, default=0.0,
                   help="seconds to wait before --verify")
    p.add_argument("--dry-run", action="store_true",
                   help="connect and report, but write nothing")
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    if args.new_id is None and not (args.factory_reset or args.check):
        print("error: one of --new-id, --factory-reset or --check is required",
              file=sys.stderr)
        return 2
    if args.new_id is None:
        args.new_id = args.from_id  # check/factory-reset path; keeps comparisons sane
    try:
        return commission(args)
    except (ValueError, ModbusError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        # pyserial's SerialException subclasses OSError; also "no such port".
        print(f"serial error: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("\naborted", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
