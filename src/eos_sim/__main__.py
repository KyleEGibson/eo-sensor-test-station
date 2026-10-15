"""Run the EOS-100 simulator as a standalone process.

    python -m eos_sim --port 5025 --speed 1 --fault TEMP_DRIFT
"""

import argparse

from .device import MODEL, Device
from .faults import Fault
from .server import SimulatorServer


def main() -> None:
    parser = argparse.ArgumentParser(description=f"{MODEL} sensor simulator")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5025)
    parser.add_argument("--speed", type=float, default=1.0, help="simulated-time multiplier")
    parser.add_argument("--serial", default="000123")
    parser.add_argument("--fault", action="append", default=[], choices=[f.value for f in Fault])
    args = parser.parse_args()

    device = Device(serial=args.serial, speed=args.speed)
    device.faults.update(Fault(name) for name in args.fault)
    server = SimulatorServer(device, args.host, args.port)
    print(f"{MODEL} simulator listening on {server.url} (speed x{args.speed})")
    if device.faults:
        print("Injected faults:", ", ".join(sorted(f.value for f in device.faults)))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.stop()


if __name__ == "__main__":
    main()
