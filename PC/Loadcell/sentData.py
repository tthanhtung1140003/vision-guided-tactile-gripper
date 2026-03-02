import PyDAQmx
from PyDAQmx import Task
import numpy as np
import keyboard
import time
import socket
import struct

# UDP CONFIG 
PI_IP = "10.0.0.23 "
PORT = 5005
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
EMA_ALPHA = 0.25 #Lọc nhiễu cao tần

# ---- ATI Calibration Matrix ----
CALIB = np.array([
    [-0.01204,  0.04072, -0.00491, -3.17693, -0.09011,  3.20056],
    [ 0.04877,  4.16255, -0.02547, -1.81391,  0.10208, -1.88871],
    [ 3.76907, -0.08275,  3.80119,  0.08022,  3.79020,  0.15491],
    [ 0.09941, 25.58867, 21.46188, -10.72741, -20.55362, -12.46830],
    [-23.96291,  0.38248, 12.34451, 19.63954, 12.85597, -19.10214],
    [ 0.48486, 17.25499, -0.09982, 15.21282, -0.55950, 15.49801]
])

# ---------------- ATI CLASS ----------------
class ATINano17Terminal:
    def __init__(self):
        self.channels = 6

        # ---- zero offset ----
        self.offset = np.zeros(3)
        self.first_10_fx = []
        self.first_10_fy = []
        self.first_10_fz = []

        # ---- EMA state ----
        self.ema_force = None

        self.task = Task()
        self.task.CreateAIVoltageChan(
            "Dev1/ai0:5",
            "",
            PyDAQmx.DAQmx_Val_Diff,
            -10.0,
            10.0,
            PyDAQmx.DAQmx_Val_Volts,
            None
        )
        self.task.StartTask()

    def zero(self):
        """Re-zero force offset using next 10 samples"""
        self.first_10_fx.clear()
        self.first_10_fy.clear()
        self.first_10_fz.clear()
        self.offset[:] = 0.0
        self.ema_force = None
        print("\n[ZERO] Reset offset & EMA baseline")

    def read_force(self):
        raw = np.zeros(self.channels, dtype=np.float64)
        read = PyDAQmx.int32()

        self.task.ReadAnalogF64(
            1,
            10.0,
            PyDAQmx.DAQmx_Val_GroupByChannel,
            raw,
            len(raw),
            PyDAQmx.byref(read),
            None
        )

        Fx, Fy, Fz = (CALIB @ raw)[:3]

        # ---- offset estimation ----
        if len(self.first_10_fx) < 10:
            self.first_10_fx.append(Fx)
            self.first_10_fy.append(Fy)
            self.first_10_fz.append(Fz)

            if len(self.first_10_fx) == 10:
                self.offset[:] = [
                    np.mean(self.first_10_fx),
                    np.mean(self.first_10_fy),
                    np.mean(self.first_10_fz)
                ]
            return None  # chưa valid
        else:
            Fx -= self.offset[0]
            Fy -= self.offset[1]
            Fz -= self.offset[2]

        # ---- EMA filtering ----
        current = np.array([Fx, Fy, Fz], dtype=np.float32)

        if self.ema_force is None:
            self.ema_force = current
        else:
            self.ema_force = (
                EMA_ALPHA * current
                + (1.0 - EMA_ALPHA) * self.ema_force
            )

        return tuple(self.ema_force)

    def close(self):
        self.task.StopTask()
        self.task.ClearTask()

# ---------------- MAIN LOOP ----------------
def main():
    reader = ATINano17Terminal()

    try:
        while True:
            result = reader.read_force()
            if result is None:
                continue

            Fx, Fy, Fz = result
            print(
                f"\rFx={Fx:8.3f}  Fy={Fy:8.3f}  Fz={Fz:8.3f}",
                end="",
                flush=True
            )
            sock.sendto(
                struct.pack('<fff', Fx, Fy, Fz),
                (PI_IP, PORT)
            )

            if keyboard.is_pressed("space") and abs(Fz) < 1.0:
                reader.zero()
                time.sleep(0.3)

    except KeyboardInterrupt:
        print("\nStopped.")

    finally:
        reader.close()
        sock.close()

if __name__ == "__main__":
    main()
