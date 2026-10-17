# TP-EOS-100: Acceptance Test Plan

| | |
|---|---|
| Document | TP-EOS-100 Rev A |
| Item under test | EOS-100 electro-optical sensor, firmware 2.4.x |
| Requirements baseline | SRS-EOS-100 Rev B (`requirements/requirements.yaml`) |
| Test station | `test_station` v1.0.0 |

## 1. Scope
This plan covers acceptance testing of the EOS-100 sensor against SRS-EOS-100 at two levels:
- Component level: each subsystem (power, thermal, gimbal, imager, command interface) tested in isolation.
- System level: operational scenarios that exercise all subsystems together.

It also covers verifying the test station itself (TS-xxx requirements), since its results don't count for much until the station is shown to work.

Out of scope: environmental testing (vibration, thermal chamber, EMI) and optical performance (MTF, NETD), which need lab equipment.

## 2. Approach
| Level | Location | Technique |
|---|---|---|
| Unit (simulator model) | `tests/unit/` | Deterministic tests with a fake clock |
| Component | `tests/component/` | Functional tests against limits, boundary values, invalid inputs |
| System | `tests/system/` | End-to-end scenarios: cold start, scan-and-capture, power cycle |
| Station verification | `tests/station/` | Fault injection, protocol error injection, report and database checks |
| Test effectiveness | `scripts/fault_campaign.py` | Full suite rerun once per injected fault |

Techniques:
- Boundary value analysis: gimbal limits ±170.0 / -30.0..90.0 are tested both just inside (169.9) and just outside (170.1). Gain and exposure are tested at their minimum, a nominal value and their maximum.
- Equivalence partitioning: invalid commands are grouped into out-of-range, wrong type, missing parameter and unknown header.
- Statistical checks: linearity is a least-squares fit with R² ≥ 0.99. Voltage and dead pixels use worst case over repeated samples.
- Negative testing: commands in the wrong power state, corrupted frames and a silent device.

## 3. Pass/fail criteria
- A test passes when every recorded measurement is within its limits (`src/test_station/limits.py`, each traced to its SRS requirement) and every assertion holds.
- A requirement is VERIFIED when at least one linked test passed and none failed. Inspection, Analysis and Demonstration requirements also need their evidence file to exist.
- The release is accepted when `pytest --rtm-strict` exits 0: all tests pass and 100% of requirements are verified.
- The station is qualified when every hardware fault in the fault campaign is detected and every communication fault is tolerated.

## 4. Suspension and resumption
- Suspend timing tests whenever comm retries occur. Retry latency looks the same as device delay, so a timing failure with retries recorded must be rerun on a clean link before a hardware defect is written up. The report annotates these failures automatically.
- Suspend all testing if the DUT stops responding (CommError after 3 attempts). Resume after power cycling and checking the cables or link.

## 5. Test environment
| Item | Configuration |
|---|---|
| DUT | EOS-100 simulator (`python -m eos_sim`) or hardware on a COM port |
| Link | `socket://` (simulator) or RS-422 serial; 0.2 s read timeout, 2 retries |
| Host | Windows 11 or Ubuntu, Python 3.11+ |
| Time scale | x10 for the built-in simulator, x1 for hardware |
| CI | GitHub Actions, Windows and Linux, Python 3.11 / 3.12 |

## 6. Deliverables (produced on every run in `reports/`)
| Artifact | Purpose |
|---|---|
| `test_report.html` | Run summary, DUT identity, every measurement against limits |
| `rtm.html`, `rtm.xlsx`, `rtm.json`, `rtm.md` | Requirements traceability matrix |
| `results.db` | Append-only SQLite history for trend analysis |
| `comm_log.tsv` | Raw command/response transcript for troubleshooting |
| `junit.xml` | CI integration |

## 7. Procedures
Each test's docstring and steps are its procedure. Representative procedures:

**TP-PWR-01 Boot time (SYS-002)**
1. Power the DUT off and confirm `SYST:STAT?` returns `OFF`.
2. Send `SYST:POW ON` and start the timer.
3. Poll `SYST:STAT?` every 10 ms until it returns `READY`.
4. Record the elapsed time. Pass if it is ≤ 3.0 s.

**TP-THM-02 Temperature stability (SYS-011)**
1. Power cycle the DUT and wait for `READY`.
2. Poll `COOL:STAT?` until it returns `READY`.
3. Sample `MEAS:TEMP?` every 0.5 s for 10 s; at least 10 samples are required.
4. Pass if the minimum and maximum are both within -40.0 ± 1.0 °C.

**TP-SYS-01 Cold start to imaging mission (system)**
1. Cold start the DUT. Measure the boot time and run BIT; the result must be 0.
2. Wait for the cooler; cooldown must be ≤ 15 s from power-on.
3. Set gain 4 and exposure 20 ms.
4. At each of the 5 scan points: point the gimbal, wait for it to settle, check the position against ±0.1°, capture a frame, then check dead pixels (≤ 5) and the CRC.

## 8. Risks
| Risk | Mitigation |
|---|---|
| The simulator does not match real hardware | Driver implements the ICD independently of the simulator; `--dut-url` runs the same suite on hardware |
| Tests that can't actually fail | Fault campaign shows every hardware fault causes failures |
| Flaky timing on shared CI runners | Timing limits have margin over nominal (boot 2.0 s vs 3.0 s limit); comm-induced timing failures are annotated |
