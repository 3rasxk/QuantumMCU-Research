# bridge_ctl.py -- keep ONE dashboard alive across sweeps. A sweep owns TCP :5055 and its own dashboard while it runs; before
# it starts, pc/run.py stops the stand-alone bridge (if we started one); after it ends, pc/run.py starts the bridge again, detached,
# so http://localhost:8080/ and the counter link keep working between runs. The pid file is the only state.
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

PIDFILE = Path(__file__).with_name(".bridge.pid")
BRIDGE = Path(__file__).with_name("bridge.py")


def _alive(pid):
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _is_bridge(pid):
    try:
        out = subprocess.run(["ps", "-p", str(pid), "-o", "command="], capture_output=True, text=True, timeout=5).stdout
    except Exception:  # noqa: BLE001
        return False
    return "bridge.py" in out


def stop(pidfile=PIDFILE):
    """Stop the bridge we started earlier (never any other process). -> True if one was stopped."""
    try:
        pid = int(Path(pidfile).read_text().strip())
    except (OSError, ValueError):
        return False
    stopped = False
    if _alive(pid) and _is_bridge(pid):
        os.kill(pid, signal.SIGTERM)
        for _ in range(50):
            if not _alive(pid):
                break
            time.sleep(0.1)
        stopped = True
    try:
        Path(pidfile).unlink()
    except OSError:
        pass
    return stopped


def start(tcp_port, http_port=8080, log=None, pidfile=PIDFILE, python=None, script=BRIDGE):
    """Start bridge.py detached (survives this process). -> pid."""
    stop(pidfile)
    out = open(log, "ab") if log else subprocess.DEVNULL
    p = subprocess.Popen([python or sys.executable, str(script), "--tcp-port", str(tcp_port), "--http-port", str(http_port)],
                         stdout=out, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, start_new_session=True)
    Path(pidfile).write_text(str(p.pid))
    return p.pid
