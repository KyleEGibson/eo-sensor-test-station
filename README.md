# EO Sensor Test Station

An automated integration and test station for a simulated electro-optical sensor (the EOS-100), with built-in **requirements traceability**.

The sensor is a pure-software model of a cooled IR camera with a two-axis gimbal. The test station talks to it over a serial-style protocol, runs component-level and system-level functional tests against requirement limits, injects hardware faults, and produces a test report, a results database and a requirements traceability matrix (RTM) on every run.

## What this demonstrates
| Integration/test engineering task | Where |
|---|---|
| Test plans, procedures, test cases | `tests/component`, `tests/system` |
| Requirements traceability | `requirements/requirements.yaml` + `src/pytest_rtm` (RTM in HTML/Excel/JSON/Markdown) |
| Functional tests at component and system level | `tests/component/*`, `tests/system/*` |
| Scripting and test automation | `src/test_station` (pyserial driver + pytest test executive) |
| Troubleshooting and root cause analysis | `reports/comm_log.tsv` raw transcript; bugs found and fixed are recorded in the commit history |
| Fault injection and failure detection | `src/eos_sim/faults.py`, `tests/station/test_fault_detection.py` |
| Test reports and documentation | `reports/test_report.html`, `docs/interface_control_document.md` |

## Architecture
```mermaid
flowchart LR
  SRS[requirements.yaml] --> RTM[pytest-rtm plugin]
  T[pytest tests] -->|@pytest.mark.req| RTM
  T --> D[EOSensor driver<br/>pyserial]
  D <-->|ASCII + XOR checksum| S[EOS-100 simulator<br/>fault injection]
  T --> DB[(results.db)]
  T --> R[test_report.html]
  RTM --> M[rtm.html / .xlsx / .json / .md]
```

## Quick start
```bash
python -m venv .venv
.venv\Scripts\activate            # Windows  (source .venv/bin/activate on Linux/macOS)
pip install -e ".[dev]"
pytest --rtm-strict               # 80 tests, about 15 s; outputs go to reports/
```
Run against a separately launched simulator (or real hardware on a COM port):
```bash
python -m eos_sim --port 5025 --fault TEMP_DRIFT
pytest --dut-url socket://127.0.0.1:5025 --time-scale 1
```
Inject a fault for a whole run to see which tests catch it:
```bash
pytest tests/component tests/system --inject-fault GIMBAL_STALL
```

## Layout
```
requirements/   SRS with IADT verification methods (28 requirements)
src/eos_sim/    device simulator (the DUT) + TCP server
src/test_station/  driver, spec limits, results DB, HTML report, pytest plugin
src/pytest_rtm/ reusable traceability plugin
tests/unit/       simulator model tests (fake clock)
tests/component/  per-subsystem acceptance tests
tests/system/     end-to-end operational scenarios
tests/station/    verification of the station itself (TS-xxx requirements)
docs/           interface control document
```

## Defects found during development
Real issues the tests surfaced (see the commit messages):
1. The ADC never saturated: the maximum signal (4064) fell below the 12-bit limit (4095).
2. The cooler tests polled `COOL:STAT?` while the sensor was still booting, which is rejected with −201.
3. The RTM plugin crashed at session end after rejecting an unknown requirement ID.
4. The thermal-drift fault started the instant the cooler reached its band, so it never reported READY.
