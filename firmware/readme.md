# Firmware

This folder contains the low-level firmware for the two STM32-based controllers in the vision-guided tactile gripper system:

- **gantry/**: Firmware for the 3-axis gantry CNC controller (STM32F103C8Tx).
- **gripper/**: Firmware for the parallel gripper controller.

Both are responsible for real-time motion control, communication, and safety features.

## Overview

| Controller | MCU          | Communication       | Main Functions                              | Project Type       |
|------------|--------------|---------------------|---------------------------------------------|--------------------|
| Gantry     | STM32F103C8Tx | USB Serial (from Laptop GUI) | Homing, jogging, motion planning, limits, error handling | STM32CubeIDE (.ioc) |
| Gripper    | (STM32 blackpill) | USB Serial  (from Raspberry Pi) | Grip/release, PID position/force, encoder reading | Arduino (.ino)     |

## Folder Structure

### gantry/
STM32CubeIDE project for the gantry controller.
gantry/
├── App/                      # Application layer (custom logic)
│   ├── comm/                 # Serial communication protocol
│   ├── driver/               # Hardware drivers
│   ├── error/                # Error management
│   ├── homing/               # Homing sequence
│   ├── jog/                  # Jogging mode
│   ├── limit/                # Limit switch handling
│   ├── motion/               # Motion control core
│   ├── protocol/             # Command parser
│   ├── system/               # System init & tick
│   ├── serial_rx.c/h         # Serial receive handler
│   └── tick_1ms.c/h          # 1ms system tick
├── Core/                     # STM32Cube generated code
│   ├── Inc/                  # HAL headers
│   ├── Src/                  # HAL implementation
│   └── Startup/              # Startup assembly
├── Drivers/                  # CMSIS & STM32 HAL
├── Gantry Controller v10.ioc # CubeMX project file
├── STM32F103C8TX_FLASH.ld    # Linker script
└── Test.launch               # Debug configuration (optional)
text### gripper/
Simple Arduino-style firmware (likely ported to STM32 via Arduino STM32 core).
gripper/
└── gripper.ino               # Main sketch: USB Serial, motor control, PID, encoder
text## Communication Protocols

- **Gantry** → Receives G-code-like commands via USB Serial from Laptop GUI.  
  See: [protocols/serial_gantry_protocol.md](../protocols/serial_gantry_protocol.md)

- **Gripper** → Receives ASCII commands via USB Serial from Raspberry Pi.  
  See: [protocols/usb_gripper_protocol.md](../protocols/usb_gripper_protocol.md)

## Build & Flash Instructions

### For gantry/ (STM32CubeIDE)
1. Open `Gantry Controller v10.ioc` in STM32CubeIDE.
2. Generate code (if needed).
3. Build project (Ctrl+B).
4. Connect ST-Link → Debug/Run (F11) or Flash (hammer icon).

### For gripper/ (.ino)
1. Open `gripper.ino` in Arduino IDE (with STM32 core installed).
2. Select board (Generic STM32F1/F4 series).
3. Select USB port → Upload.

**Note**: If using PlatformIO instead, create `platformio.ini` in each subfolder.

## Dependencies
- STM32Cube HAL (F1 series)
- CMSIS Core
- USB Device Library (for Serial on gripper, if implemented)
- Arduino STM32 core (for gripper.ino)

## Notes
- Gantry uses 1ms tick for precise timing (tick_1ms.c).
- All safety features (limits, error recovery, homing) are implemented in App/ layer.
- Firmware is tightly coupled with hardware (pinout in gpio.h / main.h).

For detailed command format, error codes, and baudrate → refer to `protocols/` folder.

Firmware version: v1.0 (March 2026)  
Questions? Contact: tung.ntt215887@sis.hust.edu.vn