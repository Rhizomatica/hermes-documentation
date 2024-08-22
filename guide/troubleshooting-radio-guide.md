## HF Radio Step-by-Step Troubleshooting Guide

1. Connect the radio to the antenna by plugging in the coaxial cable that connects the radio to the antenna;

2. Transmit (use the HERMES "PTT" button in radio config)

3. After reading the SWR, turn off the "PTT"

4. If the SWR is lower than 2.0, the station is ready to be used!

5. If the SWR is higher than 2.0, follow the following checks


In order to transmit a test signal, go to “Radio configuration”:

|![Font](./pictures/figure01.png)|
|:---------------------------------------------------------------------------------------------:|


Then click to turn ON the “PTT” button. Check the “Power” level, which should be between 15W and 30W. Check the SWR, which should be less than 2.0. Check the “Protection”, which should be “OFF”. After the readings, click to turn OFF the “PTT” button. 

|![Font](./pictures/figure02.png)|
|:---------------------------------------------------------------------------------------------:|

If the protection stays “OFF” after the transmission test, and the Power and SWR readings are in the correct ranges, the HERMES system is ready for operation and you can stop here. If either Power and SWR are not in the correct ranges or if the protection is on follow the steps in this guide to resolve the issue.

For properly assessing the HF station problems, the following equipment is necessary:
   - Multimeter which can measure voltage
   - HF watt meter
   - 2x small 50 Ohm coaxial cables with UHF connector for connecting the radio to wattmeter, and wattmeter to dummy load. You might need a UHF-female to BNC-male adapter of use with the sBitx radio.
   - 50 Ohm dummy load 


Assure that the measurement equipment is working previously.

## Initial Equipment Checks

# Check the cable:
 - Test the continuity of the cable (both center pin and outside conductor) and if the outside and center conductors are not short-circuited with a multimeter 
 - Analyze the overall cable situation 
   - - check for visibly broken parts of the cable

# Check the radio:
 - Check that the radio has all the necessary cables for connection 
 - Check the voltage in the input of the radio (should be between 12 and 14V) 
 - Test the continuity of the power cable
 - Connect the power cable to the radio
 - Check that the radio turns on correctly 
 - Test the buttons and see if everything seems correct (volume, frequency) 
 - Check if the radio is too hot, and if it is, there can be a problem in the radio. Turn off the radio and contact support.
 - Check that it doesn't smell burnt, if yes, there is a problem in radio, turn it off immediately
# Check the antenna:
 - Check the radio to antenna connections
 - Check if the antenna is well installed and hanging properly in the poles
 - Check for any broken parts and avoid any elements touching the antenna
 If all the above checks are completed without identifying the problem, and when transmitting through an antenna, the SWR is still high, proceed to the following steps:
 
  - Connect the radio to the watt meter and dummy load
  - Check the SWR:
    - - if lower than 2.0 (typically it should be 1.0 or 1.1 in the dummy load), the radio is working fine, and if there is a problem when transmitting with the antenna, the problem is likely to be in the coaxial cable, or in the antenna itself;
    - - if higher than 2.0, then most likely there is a problem with the cables (or its connectors) or even the dummy load.



