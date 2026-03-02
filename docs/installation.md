# Installation Guide

## 1. Hardware Setup
- Flash firmware/gripper & firmware/gantry (PlatformIO)
- Connect cables (Pi → Gripper, Laptop → Gantry)
- Power on gantry (24V)
- Power on gripper (12V)

## 2. Pi Side
cd pi_vision
pip install -r requirements.txt
python main.py

## 3. Laptop Side
cd laptop_gui
pip install -r requirements.txt
python gui.py

## 4. Calibration
- Run homing on GUI
- Calibrate tactile sensor (see protocols/)