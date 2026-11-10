# RESQNET X — Interactive Autopilot Simulator Starter

A laptop-first virtual prototype. It demonstrates the RESQNET concept before physical LoRa hardware is connected.

## Features
- Three virtual nodes: A (current relay), B (standby relay), C (gateway).
- Battery drain, battery adjustment and node disconnect controls.
- Live network topology and node status cards.
- Deterministic fallback mode for testing without AI.
- Optional Gemma 4 integration through Ollama's local HTTP API and tool calling.
- Allow-listed tools: `get_network_snapshot`, `request_relay_handover`, `request_alternate_route`.
- Event timeline with action, acceptance and simulated forwarding verification.

> All radio links and nodes in this starter are simulated. It does not control ESP32 boards or transmit LoRa packets.

## 1. Install Python
Install Python 3.10+ (Python 3.11 recommended). Open PowerShell in this folder:

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

If PowerShell blocks activation, use Command Prompt:

```bat
.venv\Scripts\activate.bat
pip install -r requirements.txt
```

## 2. Run without Gemma first

```powershell
streamlit run app.py
```

Open the local address shown in the terminal (usually `http://localhost:8501`). Then:
1. Click **Drain active relay to 8%**.
2. Click **Run rule-based fallback**.
3. Confirm the active relay changes from Node A to Node B.
4. Try **Disconnect active relay** and run fallback again.
5. Reset the simulation.

This proves the simulated network logic before adding model inference.

## 3. Add local Gemma 4 with Ollama
1. Install Ollama: https://ollama.com/download
2. In PowerShell run:

```powershell
ollama pull gemma4:e2b
ollama run gemma4:e2b
```

3. Keep Ollama available, then open another terminal and run the Streamlit app.
4. In the sidebar, use the model tag `gemma4:e2b`.
5. Drain the active relay to 8%, then click **Run Gemma 4 Autopilot**.
6. Expand **Inspect tool calls and execution results** to inspect the actual tool request and simulator result.

The first model download is several GB. Inference speed depends on RAM, CPU and available GPU memory. An 8 GB laptop may be constrained; a successful download does not guarantee smooth inference. Start with the small E2B variant and monitor Windows Task Manager.

Ollama serves a local API at `http://localhost:11434`. This app sends requests only to that local endpoint.

## 4. Handover validation
A target relay must be online, have at least 30% battery and link quality of at least 45%. Gateway Node C must be online. The simulator changes relay ownership only after the target accepts and the simulated forwarding check passes. These are demonstration thresholds, not field-validated operating limits.

## 5. Troubleshooting
- **Ollama not detected:** ensure it is installed and running; try `ollama list` and visit `http://localhost:11434/api/tags`.
- **Model missing:** run `ollama pull gemma4:e2b`; verify its exact tag with `ollama list`.
- **Gemma returns no tool call:** verify the exact installed tag and current Ollama/model tool-calling support. The deterministic fallback remains available.
- **Slow inference / memory pressure:** close unnecessary apps, use the smallest model variant and check Task Manager.

## 6. Path to physical hardware
Later replace the virtual state functions with real telemetry and operations:
- ESP32 nodes send telemetry over LoRa.
- Gateway ESP32 passes packets to Raspberry Pi Zero 2 W over USB serial/UART.
- Pi sends telemetry to the laptop over local Wi-Fi (HTTP/WebSocket).
- Laptop agent requests approved commands; Pi forwards commands to the gateway ESP32 and LoRa network.
- Real target nodes send task acceptance/ACK messages, and forwarding is verified before relay ownership changes.

Keep the action tools allow-listed. Do not let Gemma produce arbitrary GPIO values, shell commands, SPI transactions or raw radio instructions. Deterministic firmware and application code must validate commands.

## Safety boundary
This is a development simulator, not a certified disaster-response system. Do not use it to direct real rescue operations.
