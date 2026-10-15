# Design Decisions

Why the station is built the way it is, written as answers to the questions a reviewer is likely to ask.

### Why simulate the hardware?
Test engineering skills (writing procedures, automating them, tracing them to requirements, finding failures) don't depend on owning the hardware. A behavioral model gives a DUT that boots, cools down, slews and fails in controlled ways. The driver connects through pyserial, so `--dut-url COM3` would point the same suite at a real unit.

### Why does every response carry a checksum?
Serial links pick up noise. Without integrity checks, a flipped byte in `28.01` can become a plausible but wrong reading, and the station would record a false measurement. The XOR checksum is cheap and catches any single-byte error. Frames get a stronger CRC-32 because they carry more data. The station verifies checksums independently of the simulator code (`driver.py` has its own implementation), so a bug in one side shows up as a mismatch.

### Why retry exactly twice?
One retry recovers from a single lost or corrupted message. A second covers back-to-back errors. After three failed attempts the link is really down, and continuing would only produce a cascade of meaningless failures. Error responses (`ERR -222`) are never retried: the device received and rejected the command, and retrying would hide a real defect. All commands are idempotent (absolute positions, absolute settings), so retrying a set command is safe.

### Why separate "timing" tests under comm faults?
The fault campaign showed the problem. With dropped responses, three timing tests failed on a healthy sensor, because each retry adds a read timeout the station cannot tell apart from device delay. Widening the limits would have hidden real slow-boot defects. Instead, timing tests are marked, the campaign treats timing evidence over a degraded link as invalid, and the report annotates any timing failure that coincided with retries. That way the engineer checks the cable before writing up the hardware.

### Why do limits live in one module?
`limits.py` is the single source of truth, and every constant carries the requirement ID it comes from. When a requirement changes, there is one edit. The fault-detection tests reuse the same limits, so "the check would catch this fault" is proven against the real check, not a copy of it.

### Why record measurements and not just pass/fail?
A pass at 28.98 V against a 29.0 V limit is a warning sign; a pass at 28.01 V is not. The `measure` fixture stores value, limits and units for every check in an append-only database, so trends across runs and units can be analyzed (failure and trend analysis). It records before judging, so a failing value is never lost.

### Why a separate traceability plugin?
Traceability is not specific to this sensor. `pytest_rtm` has no dependency on the station and works on any pytest project with a YAML requirements file. It rejects links to requirement IDs that don't exist (a typo would otherwise silently leave a requirement unverified). `--rtm-strict` turns "every requirement has passing evidence" into a CI gate.

### Why IADT verification methods?
Not every requirement is verified by a test. "The interface shall be documented" is verified by Inspection, so the RTM accepts an evidence file for those requirements and still flags them when the evidence is missing.

### Why does the simulator run faster than real time?
Cooldown takes about 10 s and the stability window is 10 s. At real time the suite would take minutes; at ×10 it takes 15 s, fast enough to run on every commit. Durations are always converted back to device seconds before comparison with limits, so the speed-up never changes a verdict.

### Why does BIT miss the temperature drift?
On purpose. Real built-in test monitors only some failure modes. The fault campaign shows the sensor's own BIT reports 0 while the cooler drifts out of regulation, and only the external stability test catches it. That is the argument for external acceptance testing in the first place.
