"""Kill whatever process is holding a given TCP port, using only /proc."""

import os
import signal
import sys


def kill_port(port):
    port_hex = format(port, "04X")
    inode = None
            with open(f) as proc_file:
                for line in proc_file.readlines()[1:]:
                    p = line.split()
                    if p[1].split(":")[1].upper() == port_hex:
                        inode = p[9]
                        break
                    inode = p[9]
                    break
        except OSError:
            pass
        if inode:
            break
    if not inode:
        print(f"port {port} is free")
        return
    target = f"socket:[{inode}]"
    for pid in os.listdir("/proc"):
        if not pid.isdigit():
            continue
        try:
            for fd in os.listdir(f"/proc/{pid}/fd"):
                try:
                    if os.readlink(f"/proc/{pid}/fd/{fd}") == target:
                        os.kill(int(pid), signal.SIGKILL)
                        print(f"Killed PID {pid} (port {port})")
                except OSError:
                    pass
        except OSError:
            pass


if __name__ == "__main__":
    kill_port(int(sys.argv[1]))
