# 🔧 sBitx V3 PA Bias Adjustment Guide

This guide outlines the step-by-step process for setting the **Power Amplifier (PA) bias** on the sBitx V3, ensuring optimal performance of the IRF510 MOSFETs in the PA stage. This procedure can be performed anytime, however it is **required** when the IRF510's are replaced.

---

## 📋 Prerequisites

### 🛡️ Safety Considerations

- Always connect the sBitx to a **50-ohm dummy load** and a **power meter** to prevent damage to the MOSFETs from transmitting into an open or mismatched load.

### 🛠️ Required Tools

- **Multimeter**: For measuring current draw.
- **Flat blade screwdriver or tuning tool**: For adjusting the bias potentiometer.
- **Stable 12.1-13.8 VDC power supply**: Current-limited, capable of delivering up to **2A max**.

---

## 📖 IRF510 MOSFET Overview

- The **IRF510** is an N-channel enhancement-mode MOSFET, not specifically designed for RF but sometimes used in amateur radio amplifiers.
- Requires **precise biasing** to operate in the linear region (Class AB for SSB/CW) to prevent thermal runaway.

### 🧠 sBitx V3 Notes

- The sBitx V3 uses **two IRF510 MOSFETs** in its PA stage, with bias adjusted via the **PA_BIAS1 potentiometer**.
- Proper bias setting ensures clean amplification with minimal heat and distortion while preserving the longevity of the MOSFETs.

---

## 📝 Step-by-Step Bias Adjustment Procedure

### 1️⃣ Setup Preparation

1. Connect the sBitx V3 to a **50-ohm dummy load** and a **power meter**.
2. Open the transceiver case and locate the **PA_BIAS1 potentiometer** on the sBitx V3 circuit board *(refer to the schematic in the documentation folder)*.
3. Turn the **PA_BIAS1 potentiometer** fully **counter-clockwise** (minimum bias, zero current).
4. Connect the multimeter or current meter **inline with the XT60 power connector** to monitor the current draw.
5. Power the sBitx with a **12-13.8 VDC supply** (current-limited to 2A max).
6. Ensure adequate cooling, as IRF510s dissipate ~1.38W at 100 mA bias with 13.8V (heat sink required).

---

### 2️⃣ Initial Configuration

| Setting | Value |
|---------|-------|
| **Frequency** | 7.035 MHz |
| **Mode** | USB |
| **Mic Gain** | 0 or 1 (minimum) |
| **Drive** | 0 or 1 (minimum) |

> ⚠️ **Important**: Ensure the **PA_BIAS1 potentiometer** is fully **counter-clockwise** (minimum bias, zero current) before proceeding.

---

### 3️⃣ Measure TX Idle Current

1. Activate **TX mode** by pressing the **TX software button** or **PTT** on the external microphone.
   > 🚫 **Do not speak into the microphone** during this process.
2. Write down the **DC current draw** using a DC current multimeter in series with the power supply.

---

### 4️⃣ Adjust Bias Current

> ⚡ **WARNING**: **SLOWLY** adjust the potentiometer. **DO NOT INCREASE ABOVE 250 mA!**

1. While in **TX mode**, slowly turn the **PA_BIAS1 potentiometer** **clockwise** to increase the bias voltage to the IRF510 gates.
2. Monitor the **total current draw** on the multimeter and **SLOWLY** adjust the **PA_BIAS1 potentiometer** until it increases by **150-250 mA** above the idle current recorded in step 3.

---

### 5️⃣ Verify and Fine-Tune

1. Switch to **RX mode** (via software or unkey the microphone) and let the MOSFETs stabilize for a few seconds.
2. Re-engage **TX mode** and verify the current increase remains stable at **150-250 mA** above idle current.

| Condition | Action |
|-----------|--------|
| **Too high** (>250 mA increase) | Reduce bias slightly to prevent overheating or thermal runaway. |
| **Too low** (<150 mA) | Increase bias slightly to ensure proper linearity. |

3. Check the IRF510 heat sink temperature. It should be **warm but not excessively hot**. Reduce bias or improve cooling if overheating occurs.

---

### 6️⃣ Test RF Performance

1. Gradually increase the **Drive** setting (e.g., to 10-20) and transmit into the dummy load while monitoring output power.
2. The sBitx V3 should produce **~25W output** at full drive, depending on the band and supply voltage (12.1-13.8V).
3. Verify clean SSB modulation or CW output. If distortion occurs, reduce bias slightly or ensure input drive does not exceed 2W to protect the IRF510s.
4. Confirm stable power supply voltage (**12-13.8V**).

---

### 7️⃣ Calibration

> 📌 **Tip**: If power output varies across bands, use the **V3 Powercal utility** to calibrate drive settings for each band, compensating for gain variations.

---

## 📊 Summary Table

| Step | Action | Target |
|------|--------|--------|
| 1 | Setup Preparation | Connect dummy load, power meter, locate PA_BIAS1 |
| 2 | Initial Configuration | Frequency: 7.035 MHz, Mode: USB, Min Drive/Mic Gain |
| 3 | Measure TX Idle Current | Record baseline current draw |
| 4 | Adjust Bias Current | Increase by **150-250 mA** above idle |
| 5 | Verify and Fine-Tune | Stable bias, check heat sink temperature |
| 6 | Test RF Performance | ~**25W** output, clean modulation |
| 7 | Calibration | Use V3 Powercal utility for band-specific adjustments |

---

## ⚠️ Safety & Best Practices

- ✅ Always use a **50-ohm dummy load** during adjustment.
- ✅ Keep the **power supply current-limited** to 2A max.
- ✅ Make bias adjustments **slowly**.
- ✅ Monitor **heat sink temperature** constantly.
- ❌ **Never** transmit without a proper load.
- ❌ **Never** exceed 250 mA increase above idle current.

---

## 📚 References

- [sBitx V3 Schematic](../documentation/sbitx-v3-schematic.pdf)
- [IRF510 Datasheet](https://www.infineon.com/dgdl/irf510.pdf)
- [sBitx V3 User Manual](../documentation/sbitx-v3-manual.pdf)

---

## 📝 Revision History

| Date | Version | Author | Description |
|------|---------|--------|-------------|
| 2026-07-20 | 1.0 | [Nilson Rocha ] | Initial creation |
| | | | |

---

## 📬 Questions / Support

For questions or support, please open an issue in the repository or contact the maintainer.

---

**Happy HAM Radio!** 🎙️📻