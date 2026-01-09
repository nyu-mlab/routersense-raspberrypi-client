import os
import signal


def get_mem_percent():
    """
    Returns the memory usage percentage.

    Auto-kills this current process if memory usage is above 80%.

    """
    with open("/proc/meminfo") as f:
        meminfo = f.readlines()

    mem_total = int([x for x in meminfo if x.startswith("MemTotal:")][0].split()[1])
    mem_free = int([x for x in meminfo if x.startswith("MemAvailable:")][0].split()[1])
    mem_used = mem_total - mem_free
    mem_percent = (mem_used / mem_total) * 100 if mem_total else 0

    if mem_percent > 80:
        os.kill(os.getpid(), signal.SIGTERM)

    return mem_percent