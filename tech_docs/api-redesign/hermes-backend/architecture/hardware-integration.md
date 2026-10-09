# Hardware Integration Guide — sBitx v2

## Overview

The Hermes Backend communicates with the **sBitx v2** HF transceiver through a Hardware Abstraction Layer (HAL). All hardware commands go through the `IRadioDriver` interface, which has two implementations:

| Driver | Purpose | Requires Hardware |
|--------|---------|:---:|
| `SBitxCLIDriver` | Production driver for sBitx v2 | Yes |
| `SimulatedRadioDriver` | Development and testing | No |

The driver is selected at startup via the `RADIO_DRIVER` environment variable.

## IRadioDriver Interface

```typescript
// src/hal/driver.ts
interface IRadioDriver {
  /** Connect to the radio hardware */
  connect(): Promise<void>;
  /** Disconnect from the radio hardware */
  disconnect(): Promise<void>;
  /** Check if the radio is connected and responsive */
  isConnected(): boolean;

  /** Get current radio status snapshot */
  getStatus(): Promise<RadioStatus>;
  /** Set frequency in kHz */
  setFrequency(frequencyKhz: number): Promise<void>;
  /** Set operating mode (USB, LSB, AM, FM, CW) */
  setMode(mode: RadioMode): Promise<void>;
  /** Set TX power in watts */
  setPower(watts: number): Promise<void>;
  /** Push-to-talk: start transmitting */
  pttOn(): Promise<void>;
  /** Push-to-talk: stop transmitting */
  pttOff(): Promise<void>;
  /** Get SWR (Standing Wave Ratio) reading */
  getSwr(): Promise<number>;

  /** Event: telemetry snapshot (1 Hz) */
  on(event: "telemetry", listener: (data: TelemetrySnapshot) => void): void;
  /** Event: radio connected */
  on(event: "connected", listener: () => void): void;
  /** Event: radio disconnected */
  on(event: "disconnected", listener: (error?: Error) => void): void;
  /** Event: SWR protection triggered */
  on(event: "swr-protection", listener: (swr: number) => void): void;
}

interface RadioStatus {
  connected: boolean;
  frequency: number;      // kHz
  mode: RadioMode;
  power: number;           // watts
  swr: number;
  temperature: number;     // °C
  txActive: boolean;
}

interface TelemetrySnapshot {
  timestamp: string;       // ISO 8601
  frequency: number;
  mode: RadioMode;
  power: number;
  swr: number;
  temperature: number;
  voltage: number;         // V
  current: number;         // A
  txActive: boolean;
}

type RadioMode = "USB" | "LSB" | "AM" | "FM" | "CW";
```

## SBitxCLIDriver

The production driver communicates with the sBitx hardware via its CLI interface. All commands use `child_process.execFile` with **argument arrays** to prevent shell injection.

### CLI Commands

The sBitx CLI (`/usr/local/bin/sbitx`) provides these commands:

| CLI Command | Description | Example |
|-------------|-------------|---------|
| `sbitx status` | Get full radio status (JSON output) | `sbitx status` |
| `sbitx set-frequency <kHz>` | Set VFO frequency | `sbitx set-frequency 7100` |
| `sbitx set-mode <mode>` | Set operating mode | `sbitx set-mode USB` |
| `sbitx set-power <watts>` | Set TX power | `sbitx set-power 10` |
| `sbitx ptt on` | Start transmitting | `sbitx ptt on` |
| `sbitx ptt off` | Stop transmitting | `sbitx ptt off` |
| `sbitx swr` | Read SWR (JSON output) | `sbitx swr` |
| `sbitx telemetry` | Stream telemetry (JSON, 1 Hz) | `sbitx telemetry --interval 1` |

### Implementation

```typescript
// src/hal/sbitx-cli-driver.ts
import { execFile, ChildProcess } from "node:child_process";
import { EventEmitter } from "node:events";

export class SBitxCLIDriver extends EventEmitter implements IRadioDriver {
  private connected = false;
  private telemetryProcess: ChildProcess | null = null;
  private readonly cliPath: string;
  private readonly timeout: number;

  constructor(cliPath = "/usr/local/bin/sbitx", timeout = 5000) {
    super();
    this.cliPath = cliPath;
    this.timeout = timeout;
  }

  async connect(): Promise<void> {
    // Verify CLI is available
    await this.exec(["status"]);
    this.connected = true;
    this.emit("connected");

    // Start telemetry streaming
    this.startTelemetryStream();
  }

  async disconnect(): Promise<void> {
    this.stopTelemetryStream();
    this.connected = false;
    this.emit("disconnected");
  }

  isConnected(): boolean {
    return this.connected;
  }

  async getStatus(): Promise<RadioStatus> {
    const output = await this.exec(["status"]);
    const parsed = JSON.parse(output) as RawStatus;
    return {
      connected: this.connected,
      frequency: parsed.vfo_frequency,
      mode: parsed.mode as RadioMode,
      power: parsed.tx_power,
      swr: parsed.swr_reading,
      temperature: parsed.pa_temperature,
      txActive: parsed.ptt_active,
    };
  }

  async setFrequency(khz: number): Promise<void> {
    await this.exec(["set-frequency", String(khz)]);
  }

  async setMode(mode: RadioMode): Promise<void> {
    await this.exec(["set-mode", mode]);
  }

  async setPower(watts: number): Promise<void> {
    await this.exec(["set-power", String(watts)]);
  }

  async pttOn(): Promise<void> {
    await this.exec(["ptt", "on"]);
  }

  async pttOff(): Promise<void> {
    await this.exec(["ptt", "off"]);
  }

  async getSwr(): Promise<number> {
    const output = await this.exec(["swr"]);
    const parsed = JSON.parse(output) as { swr: number };
    return parsed.swr;
  }

  private exec(args: string[]): Promise<string> {
    return new Promise((resolve, reject) => {
      execFile(this.cliPath, args, { timeout: this.timeout }, (error, stdout, stderr) => {
        if (error) {
          reject(new Error(`sBitx CLI error: ${stderr || error.message}`));
          return;
        }
        resolve(stdout.trim());
      });
    });
  }

  private startTelemetryStream(): void {
    this.telemetryProcess = execFile(
      this.cliPath,
      ["telemetry", "--interval", "1"],
      { timeout: 0 } // No timeout for streaming
    );

    this.telemetryProcess.stdout?.on("data", (chunk: Buffer) => {
      const lines = chunk.toString().trim().split("\n");
      for (const line of lines) {
        try {
          const data = JSON.parse(line) as RawTelemetry;
          const snapshot: TelemetrySnapshot = {
            timestamp: new Date().toISOString(),
            frequency: data.vfo_frequency,
            mode: data.mode as RadioMode,
            power: data.tx_power,
            swr: data.swr_reading,
            temperature: data.pa_temperature,
            voltage: data.supply_voltage,
            current: data.current_draw,
            txActive: data.ptt_active,
          };
          this.emit("telemetry", snapshot);

          // SWR protection: if SWR > 3.0, cut TX
          if (data.swr_reading > 3.0 && data.ptt_active) {
            this.emit("swr-protection", data.swr_reading);
            void this.pttOff();
          }
        } catch {
          // Malformed JSON line — log and continue
        }
      }
    });

    this.telemetryProcess.stderr?.on("data", (chunk: Buffer) => {
      // Log stderr but don't crash
      console.warn("sBitx CLI stderr:", chunk.toString());
    });

    this.telemetryProcess.on("close", (code) => {
      if (code !== 0 && this.connected) {
        this.connected = false;
        this.emit("disconnected", new Error(`Telemetry stream exited with code ${code}`));
      }
    });
  }

  private stopTelemetryStream(): void {
    if (this.telemetryProcess) {
      this.telemetryProcess.kill("SIGTERM");
      this.telemetryProcess = null;
    }
  }
}
```

## SimulatedRadioDriver

The simulated driver responds to all commands with plausible fake data — no hardware required.

```typescript
// src/hal/simulated-driver.ts
export class SimulatedRadioDriver extends EventEmitter implements IRadioDriver {
  private connected = false;
  private telemetryInterval: NodeJS.Timeout | null = null;
  private state: RadioStatus;

  constructor(initialState?: Partial<RadioStatus>) {
    super();
    this.state = {
      connected: false,
      frequency: 7100,
      mode: "USB",
      power: 10,
      swr: 1.2,
      temperature: 35,
      txActive: false,
      ...initialState,
    };
  }

  async connect(): Promise<void> {
    this.connected = true;
    this.state.connected = true;
    this.emit("connected");
    this.startTelemetrySimulation();
  }

  async disconnect(): Promise<void> {
    this.stopTelemetrySimulation();
    this.connected = false;
    this.state.connected = false;
    this.emit("disconnected");
  }

  private startTelemetrySimulation(): void {
    this.telemetryInterval = setInterval(() => {
      // Generate plausible variations
      this.state.temperature += (Math.random() - 0.5) * 0.5;
      this.state.swr = 1.0 + Math.random() * 0.5;

      const snapshot: TelemetrySnapshot = {
        timestamp: new Date().toISOString(),
        frequency: this.state.frequency,
        mode: this.state.mode,
        power: this.state.power,
        swr: this.state.swr,
        temperature: Math.round(this.state.temperature * 10) / 10,
        voltage: 13.8 + (Math.random() - 0.5) * 0.4,
        current: this.state.txActive ? 15 + Math.random() * 3 : 0.5 + Math.random() * 0.2,
        txActive: this.state.txActive,
      };
      this.emit("telemetry", snapshot);
    }, 1000);
  }

  // ... other methods simply update this.state and return it
}
```

## SWR Protection

High SWR (> 3.0) indicates antenna mismatch and can damage the transmitter. The driver:

1. Monitors SWR from telemetry stream (every 1 second)
2. If SWR > 3.0 **and** PTT is active → immediately cuts TX (`pttOff`)
3. Emits `swr-protection` event
4. API responds to `GET /radio/status` with `swrProtection: true`
5. Operator must manually reset via `POST /radio/protection/reset`

## Error Handling & Degraded Modes

| Failure | Behavior |
|---------|----------|
| sBitx CLI not found | Driver fails `connect()`; API returns `radio.connected: false` |
| Telemetry stream dies | `disconnected` event emitted; API serves last-known state with `stale: true` |
| Single command times out | Error returned to caller; subsequent commands retry |
| SWR protection triggers | TX cut immediately; API indicates protection active |
| Process `SIGTERM` received | Graceful shutdown: stop telemetry, disconnect radio, flush DB, exit |

## Testing

See [docs/development/testing.md](testing.md) for how to use `SimulatedRadioDriver` in tests.