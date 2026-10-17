# ICD-EOS-100: Command Interface Control Document

Satisfies SYS-042. Defines the command interface between the EOS-100 sensor and a host (the test station).

## Transport
- Line-based ASCII over serial (RS-422) or TCP (simulator default port 5025).
- Host to sensor: `<COMMAND>[ <argument>]\n`
- Sensor to host: `<payload>*<HH>\n`, where `HH` is the XOR of all payload bytes as two uppercase hex digits (SYS-041).
- Every command gets exactly one response. Set commands return `OK`. Errors return `ERR <code>` and push the error onto the error queue.

## Commands
| Command | Response | Notes |
|---|---|---|
| `*IDN?` | `MFR,MODEL,SNnnnnnn,x.y.z` | Always available |
| `*RST` | `OK` | Gimbal home, gain 1, exposure 10 ms, clears error queue |
| `*TST?` | integer bitmask | 0 = pass; bit1 gimbal, bit2 imager, bit3 power |
| `SYST:POW ON\|OFF` / `SYST:POW?` | `OK` / `ON\|OFF` | Always available |
| `SYST:STAT?` | `OFF\|BOOTING\|READY` | Always available |
| `SYST:ERR?` | `code,"message"` | FIFO, `0,"No error"` when empty (SYS-040) |
| `MEAS:VOLT?` / `MEAS:CURR?` | volts / amps | |
| `MEAS:TEMP?` / `COOL:STAT?` | °C / `COOLING\|READY` | |
| `GIMB:AZ <deg>` / `GIMB:EL <deg>` | `OK` | Az -170..+170, El -30..+90 |
| `GIMB:POS?` / `GIMB:STAT?` / `GIMB:HOME` | `az,el` / `IDLE\|MOVING` / `OK` | |
| `IMG:GAIN <1-16>` / `IMG:EXP <0.1-100 ms>` | `OK` | Also query forms `IMG:GAIN?`, `IMG:EXP?` |
| `IMG:CAPT?` | `id,mean,std,dead,CRC32` | CRC-32 over `id,mean,std,dead` (SYS-033) |
| `SIM:FAULT <name>` / `SIM:FAULT?` / `SIM:FAULT:CLR` | | Simulator only |

## Error codes
| Code | Meaning |
|---|---|
| -104 | Data type error |
| -109 | Missing parameter |
| -113 | Undefined header |
| -200 | Not powered (operational command while OFF) |
| -201 | Not ready (operational command while BOOTING) |
| -222 | Data out of range |
| -350 | Error queue overflow (queue depth 10) |
