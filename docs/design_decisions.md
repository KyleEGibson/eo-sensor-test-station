# Design decisions

### Why simulate the hardware?
I don't have an IR sensor, and writing procedures, automating them and tracing them to requirements doesn't need one. The model boots, cools down, slews and fails when I tell it to. The driver connects through pyserial, so `--dut-url COM3` would point the same suite at a real unit.

### Why does every response carry a checksum?
Serial links pick up noise, and a flipped byte in `28.01` can turn into a reading that looks fine but is wrong. The XOR checksum is cheap and catches any single-byte error. Frames get a stronger CRC-32 because they carry more data. `driver.py` has its own checksum code separate from the simulator's, so a bug on either side shows up as a mismatch.

### Why retry exactly twice?
One retry recovers from a single lost or corrupted message. A second covers back-to-back errors. After three failures the link is down and continuing just piles up failures that mean nothing. Error responses (`ERR -222`) aren't retried, because the device got the command and rejected it, and retrying could hide a real defect. All commands are idempotent (absolute positions, absolute settings), so retrying a set command is safe.

### Why separate "timing" tests under comm faults?
The fault campaign turned this up: with dropped responses, three timing tests failed on a healthy sensor, since each retry adds a read timeout that looks exactly like device delay. Widening the limits would have hidden real slow-boot defects, so instead the timing tests are marked, the campaign ignores timing results over a bad link, and the report flags any timing failure that had retries during it.

### Why do limits live in one module?
Every constant in `limits.py` has the requirement ID it comes from, so a requirement change is one edit. The fault-detection tests use the same limits, which means they're checking the real acceptance check and not a copy of it.

### Why record measurements and not just pass/fail?
A pass at 28.98 V against a 29.0 V limit is worth noticing and a pass at 28.01 V isn't. The `measure` fixture saves the value, limits and units for every check in an append-only database so you can look at trends later. It records the value before checking it, so failing values get saved too.

### Why a separate traceability plugin?
Nothing about traceability is specific to this sensor, so `pytest_rtm` doesn't import the station and works on any pytest project with a YAML requirements file. It rejects links to requirement IDs that don't exist, since a typo would otherwise quietly leave a requirement unverified. `--rtm-strict` makes "every requirement has passing evidence" a CI gate.

### Why IADT verification methods?
Some requirements aren't verified by a test. "The interface shall be documented" is verified by Inspection, so the RTM takes an evidence file for those and still flags them if the file is missing.

### Why does the simulator run faster than real time?
Cooldown takes about 10 s and the stability window is 10 s. At real time the suite takes minutes, at x10 it takes 15 s, which is fine for every commit. Durations get converted back to device seconds before they're compared to limits, so the speed-up doesn't change any result.

### Why does BIT miss the temperature drift?
That's deliberate, since real BIT only watches some failure modes. In the fault campaign the sensor's BIT reports 0 while the cooler drifts out of regulation, and only the external stability test catches it.
