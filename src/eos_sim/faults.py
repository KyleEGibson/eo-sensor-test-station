"""Hardware and communication faults the simulator can inject on demand."""

from enum import Enum


class Fault(str, Enum):
    TEMP_DRIFT = "TEMP_DRIFT"
    GIMBAL_STALL = "GIMBAL_STALL"
    VOLT_SAG = "VOLT_SAG"
    DEAD_PIXELS = "DEAD_PIXELS"
    COMM_DROP = "COMM_DROP"
    COMM_CORRUPT = "COMM_CORRUPT"

    @property
    def description(self) -> str:
        return _DESCRIPTIONS[self]

    @property
    def is_comm_fault(self) -> bool:
        return self in (Fault.COMM_DROP, Fault.COMM_CORRUPT)


_DESCRIPTIONS = {
    Fault.TEMP_DRIFT: "Cooler loses regulation after reaching setpoint; detector warms slowly",
    Fault.GIMBAL_STALL: "Azimuth motor stalls partway through every move",
    Fault.VOLT_SAG: "Input bus voltage sags below its lower limit",
    Fault.DEAD_PIXELS: "Detector develops a cluster of dead pixels",
    Fault.COMM_DROP: "Every third response is lost on the wire",
    Fault.COMM_CORRUPT: "Every third response has a corrupted byte",
}

# Built-in self test (*TST?) bit assigned to each fault. Faults missing here
# are not caught by the sensor's own BIT; only external testing finds them.
BIT_FLAGS = {
    Fault.GIMBAL_STALL: 0b0010,
    Fault.DEAD_PIXELS: 0b0100,
    Fault.VOLT_SAG: 0b1000,
}
