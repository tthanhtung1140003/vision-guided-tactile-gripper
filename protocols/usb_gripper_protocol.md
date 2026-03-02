# USB Gripper Protocol (Pi → STM32)

Format: ASCII text, ended with \n

Examples:
- <G>          → Grip (velocity mode)
- <R>          → Release
- <F>          → Stop & PID hold
- <S:5>        → Squeeze +5°
- <L:3>        → Loosen -3°
- <T:45>       → Go to absolute angle 45°

Response from STM32:
<ANG:23.5,TAR:45>