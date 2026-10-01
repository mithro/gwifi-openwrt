#!/usr/bin/python3
"""Run a command in a libvirt guest via the qemu guest agent (as root).

Run ON THE HYPERVISOR:  sudo python3 ga-exec.py wisp /bin/sh -c "id; uptime"
Prints the command's stdout, stderr, then "rc: N". The hypervisor-side way
into a wisp VM when ssh is unavailable (see install-guest-agent-offline.py).
"""
import base64, json, subprocess, sys, time
dom, argv = sys.argv[1], sys.argv[2:]
def qga(cmd):
    r = subprocess.run(["virsh", "qemu-agent-command", dom, json.dumps(cmd)], text=True, capture_output=True, check=True)
    return json.loads(r.stdout)["return"]
pid = qga({"execute": "guest-exec", "arguments": {"path": argv[0], "arg": argv[1:], "capture-output": True}})["pid"]
while True:
    st = qga({"execute": "guest-exec-status", "arguments": {"pid": pid}})
    if st["exited"]: break
    time.sleep(0.5)
for k in ("out-data", "err-data"):
    if k in st: sys.stdout.write(base64.b64decode(st[k]).decode(errors="replace"))
print("rc:", st.get("exitcode"))
