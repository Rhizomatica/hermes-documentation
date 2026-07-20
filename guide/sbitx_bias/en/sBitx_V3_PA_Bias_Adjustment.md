
##sBitx V3 PA Bias Adjustment Guide
This guide outlines the step-by-step process for setting the Power Amplifier (PA) bias on the sBitx V3, ensuring optimal performance of the IRF510 MOSFETs in the PA stage. This procedure can be performed anytime, however it is required when the IRF510's are replaced.

##Prerequisites
#Safety Considerations

Always connect the sBitx to a 50-ohm dummy load and a power meter to prevent damage to the MOSFETs from transmitting into an open or mismatched load.

#Required Tools
Multimeter: For measuring current draw.
Flat blade screwdriver or tuning tool: For adjusting the bias potentiometer.
Stable 12.1-13.8 VDC power supply: Current-limited, capable of delivering up to 2A max.
##IRF510 MOSFET Overview
The IRF510 is an N-channel enhancement-mode MOSFET, not specifically designed for RF but sometimes used in amateur radio amplifiers.
Requires precise biasing to operate in the linear region (Class AB for SSB/CW) to prevent thermal runaway.
sBitx V3 Notes
The sBitx V3 uses two IRF510 MOSFETs in its PA stage, with bias adjusted via the PA_BIAS1 potentiometer.
Proper bias setting ensures clean amplification with minimal heat and distortion while preserving the longevity of the MOSFETs.
Step-by-Step Bias Adjustment Procedure
1. Setup Preparation
Connect the sBitx V3 to a 50-ohm dummy load and a power meter.
Open the transceiver case and locate the PA_BIAS1 potentiometer on the sBitx V3 circuit board (refer to the schematic in the documentation folder).
Turn the PA_BIAS1 potentiometer fully counter-clockwise (minimum bias, zero current).
Connect the multimeter or current meter inline with the XT60 power connector to monitor the current draw.
Power the sBitx with a 12-13.8 VDC supply (current-limited to 2A max).
Ensure adequate cooling, as IRF510s dissipate ~1.38W at 100 mA bias with 13.8V (heat sink required).
2. Initial Configuration
Launch the sBitx application.
Set Frequency to 7.035 MHz.
Set Mode to USB.
Set Mic Gain to 0 or 1 (minimum) to prevent PA drive during adjustment.
Set Drive to 0 or 1 (minimum) to avoid excessive RF input.
Ensure the PA_BIAS1 potentiometer is fully counter-clockwise (minimum bias, zero current).
3. Measure TX Idle Current
Activate TX mode by pressing the TX software button or PTT on the external microphone. Do not speak into the microphone during this process
Write down the DC current draw using a DC current multimeter in series with the power supply.
4. Adjust Bias Current
While in TX mode, slowly turn the PA_BIAS1 potentiometer clockwise to increase the bias voltage to the IRF510 gates.
Monitor the total current draw on the multimeter and SLOWLY adjust the PA_BIAS1 potentiometer until it increases by 150-250 mA above the idle current recorded in step 3. DO NOT INCREASE ABOVE 250 mA
5. Verify and Fine-Tune
Switch to RX mode (via software or unkey the microphone) and let the MOSFETs stabilize for a few seconds.
Re-engage TX mode and verify the current increase remains stable at 150-250 mA above idle current.
If too high (>250 mA increase): Reduce bias slightly to prevent overheating or thermal runaway.
If too low (<150 mA): Increase bias slightly to ensure proper linearity.
Check the IRF510 heat sink temperature. It should be warm but not excessively hot. Reduce bias or improve cooling if overheating occurs.
6. Test RF Performance
Gradually increase the Drive setting (e.g., to 10-20) and transmit into the dummy load while monitoring output power.
The sBitx V3 should produce ~25W output at full drive, depending on the band and supply voltage (12.1-13.8V).
Verify clean SSB modulation or CW output. If distortion occurs, reduce bias slightly or ensure input drive does not exceed 2W to protect the IRF510s.
Confirm stable power supply voltage (12-13.8V).
7. Calibration
If power output varies across bands, use the V3 Powercal utility to calibrate drive settings for each band, compensating for gain variations.