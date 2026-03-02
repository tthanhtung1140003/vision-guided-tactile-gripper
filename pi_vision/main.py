# main.py
import time
import cv2
from multiprocessing import Process, Queue, set_start_method

from tactile.tactile_camera import tactile_cam_loop

from command.laptop_link import LaptopLink
from command.command_router import CommandRouter
from command.gripper import Gripper

def cam_process(cam_id: int, q: Queue):
    cam_gen = tactile_cam_loop(cam_id=cam_id, show=False)

    for frame, state in cam_gen:
        if q.full():
            try:
                q.get_nowait()
            except:
                pass
        q.put((frame, state))

def main():

    print(" Starting Full Tactile + Command System")

    set_start_method("spawn", force=True)

    q0 = Queue(maxsize=1)
    q1 = Queue(maxsize=1)

    p0 = Process(target=cam_process, args=(0, q0), daemon=True)
    p1 = Process(target=cam_process, args=(1, q1), daemon=True)

    p0.start()
    p1.start()

    laptop = LaptopLink(role="server", host="0.0.0.0", port=9999)
    gripper = Gripper(port="/dev/ttyACM0")

    router = CommandRouter(gripper, laptop)

    try:
        while True:

            slip_score = None
            contact0 = contact1 = None
            meanx0 = meany0 = mean0 = None
            meanx1 = meany1 = mean1 = None

            gripper.update()
            if not q0.empty() and not q1.empty():
                frame0, black_window0, state0 = q0.get()
                frame1, black_window1, state1 = q1.get()

                slip0 = state0.get("slip_score", 0.0)
                slip1 = state1.get("slip_score", 0.0)

                slip_score = max(slip0,slip1)

                contact0,contact1 = state0.get("contact", 0), state1.get("contact", 0)
                

                fz0,fz1 = state0.get("fz", 0.0) , state1.get("fz", 0.0)
                fx0,fx1 = state0.get("fx", 0.0) , state1.get("fx", 0.0)
                fy0,fy1 = state0.get("fy", 0.0) , state1.get("fy", 0.0)

                meanx0,meany0,mean0 = state0.get("mean_dx", 0.0), state0.get("mean_dy", 0.0), state0.get("mean_disp", 0.0)
                meanx1,meany1,mean1 = state1.get("mean_dx", 0.0), state1.get("mean_dy", 0.0), state1.get("mean_disp", 0.0)

                cv2.imshow("Tactile Cam 0", frame0)
                cv2.imshow("Tactile Cam 1", frame1)
                cv2.imshow("Contact Field 0", black_window0)
                cv2.imshow("Contact Field 1", black_window1)
                cv2.waitKey(1)

            router.update(slip_score=slip_score, 
                          contact_state0=contact0,
                          contact_state1=contact1,
                          tar_value = gripper.last_tar,
                          meanx0=meanx0, meany0=meany0, mean0=mean0,
                          meanx1=meanx1, meany1=meany1, mean1=mean1,
                        )

            time.sleep(0.005)

    except KeyboardInterrupt:
        print("\n Stopping system...")

    finally:
        p0.terminate()
        p1.terminate()
        p0.join()
        p1.join()
        cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
