"""Pass/fail limits derived from the SRS (requirements/requirements.yaml).

Keeping limits in one place means a requirement change is a one-line edit
here, and the fault-detection tests check against the same numbers as the
acceptance tests.
"""

BOOT_TIME_MAX_S = 3.0                      # SYS-002
BUS_VOLTAGE_V = (27.0, 29.0)               # SYS-005
CURRENT_MAX_A = 4.0                        # SYS-006

COOLER_SETPOINT_C = -40.0                  # SYS-010
COOLER_TOLERANCE_C = 1.0                   # SYS-010, SYS-011
COOLDOWN_MAX_S = 15.0                      # SYS-010
STABILITY_WINDOW_S = 10.0                  # SYS-011

POINTING_TOLERANCE_DEG = 0.1               # SYS-020, SYS-021
SLEW_90_MAX_S = 2.0                        # SYS-022
AZ_LIMITS_DEG = (-170.0, 170.0)            # SYS-023
EL_LIMITS_DEG = (-30.0, 90.0)              # SYS-023

GAIN_LIMITS = (1, 16)                      # SYS-030
EXPOSURE_LIMITS_MS = (0.1, 100.0)          # SYS-030
DEAD_PIXELS_MAX = 5                        # SYS-031
LINEARITY_R2_MIN = 0.99                    # SYS-032

OUT_OF_RANGE = -222
NOT_POWERED = -200
NOT_READY = -201


def cooler_band() -> tuple[float, float]:
    return (COOLER_SETPOINT_C - COOLER_TOLERANCE_C, COOLER_SETPOINT_C + COOLER_TOLERANCE_C)
