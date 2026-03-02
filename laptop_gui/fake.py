import socket
import threading
import time
import sys

HOST = "0.0.0.0"
PORT = 9999

HELP = """
Commands you can type:
  help
  grasp_done
  grasp_fail
  handover_done
  stop                  -> sends "Stop" (matches test spec)
  stop_allcaps           -> sends "STOP" (legacy)
  move x+ | move x- | move y+ | move y- | move z+ | move z-
  raw <text>            -> sends exactly <text> as one line
  spam <cmd> <ms> <n>   -> send cmd repeatedly every <ms> milliseconds, n times
  quit
"""

def safe_send(conn: socket.socket, line: str):
    data = (line.rstrip("\r\n") + "\n").encode("utf-8", errors="replace")
    conn.sendall(data)

def rx_thread(conn: socket.socket, addr):
    buf = b""
    print(f"[RX] client connected from {addr}")
    try:
        while True:
            chunk = conn.recv(4096)
            if not chunk:
                print("[RX] client closed")
                break
            buf += chunk
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                try:
                    s = line.decode("utf-8", errors="replace").strip()
                except Exception:
                    s = str(line)
                if s:
                    print(f"[GUI -> PI] {s}")
    except Exception as e:
        print(f"[RX] error: {e}")
    finally:
        try:
            conn.close()
        except Exception:
            pass

def accept_one(server: socket.socket):
    conn, addr = server.accept()
    conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    t = threading.Thread(target=rx_thread, args=(conn, addr), daemon=True)
    t.start()
    return conn

def main():
    print("[FakePi] starting...")
    print(HELP)

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((HOST, PORT))
    server.listen(1)
    print(f"[FakePi] listening on {HOST}:{PORT}")

    conn = None

    while True:
        if conn is None:
            print("[FakePi] waiting for GUI to connect...")
            conn = accept_one(server)
            print("[FakePi] GUI connected. Type 'help' to see commands.")
            continue

        try:
            cmd = input("fakepi> ").strip()
        except (EOFError, KeyboardInterrupt):
            cmd = "quit"

        if not cmd:
            continue

        lc = cmd.lower()

        try:
            if lc in ("help", "?"):
                print(HELP)

            elif lc == "quit":
                print("[FakePi] quitting...")
                try:
                    conn.close()
                except Exception:
                    pass
                break

            elif lc == "grasp_done":
                safe_send(conn, "Grasp_done")
                print("[PI -> GUI] Grasp_done")

            elif lc == "grasp_fail":
                safe_send(conn, "Grasp_fail")
                print("[PI -> GUI] Grasp_fail")

            elif lc == "handover_done":
                safe_send(conn, "Handover_done")
                print("[PI -> GUI] Handover_done")

            elif lc == "stop":
                # Match the provided test harness which uses "Stop" (capital S, rest lowercase)
                safe_send(conn, "Stop")
                print("[PI -> GUI] Stop")

            elif lc in ("stop_allcaps", "stop_caps", "stop_legacy"):
                # Legacy variant some older builds expect
                safe_send(conn, "STOP")
                print("[PI -> GUI] STOP")

            elif lc.startswith("move "):
                # move x+ / move y- ...
                parts = cmd.split()
                if len(parts) != 2:
                    print("Usage: move x+ | move x- | move y+ | move y- | move z+ | move z-")
                    continue
                axis = parts[1].strip()
                axis = axis.upper()
                if axis not in ("X+", "X-", "Y+", "Y-", "Z+", "Z-"):
                    print("Invalid axis. Use x+/x-/y+/y-/z+/z-")
                    continue
                out = f"Move {axis[0]}{axis[1]}"
                safe_send(conn, out)
                print(f"[PI -> GUI] {out}")

            elif lc.startswith("raw "):
                out = cmd[4:]
                safe_send(conn, out)
                print(f"[PI -> GUI] {out}")

            elif lc.startswith("spam "):
                # spam <cmd> <ms> <n>
                parts = cmd.split()
                if len(parts) < 4:
                    print("Usage: spam <cmd> <ms> <n>  (example: spam 'Move X+' 50 60)")
                    continue
                # reconstruct <cmd> possibly quoted without relying on shlex
                # assume last two tokens are ms and n
                ms = int(parts[-2])
                n = int(parts[-1])
                body = " ".join(parts[1:-2]).strip()
                body = body.strip("'\"")
                for i in range(n):
                    safe_send(conn, body)
                    time.sleep(ms / 1000.0)
                print(f"[FakePi] spammed {n} times: {body}")

            else:
                print("Unknown. Type 'help'.")
        except (BrokenPipeError, ConnectionResetError):
            print("[FakePi] GUI disconnected. Waiting for reconnect...")
            conn = None
        except Exception as e:
            print(f"[FakePi] error: {e}")

    try:
        server.close()
    except Exception:
        pass

if __name__ == "__main__":
    main()