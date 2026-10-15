import os, subprocess, time, json, ctypes, sys
from ctypes import wintypes as w
home="O:/dev/T3w/home"; os.makedirs(home+"/.clawd-tank",exist_ok=True)
env=dict(os.environ,HOME=home,USERPROFILE=home,SPIKE_PORT="19999",SPIKE_WRONG="1",PYTHONPATH="O:/Proyectos/Clawdy-hotbar/host")
PY="O:/Proyectos/Clawdy/host/.venv/Scripts/python.exe"
pet=subprocess.Popen(["O:/dev/target/release/hotbar-spike.exe"],env=env,stderr=open("O:/dev/T3w/pet.log","w"))
time.sleep(4)
dm=subprocess.Popen([PY,"-m","clawd_tank_daemon.daemon","--sim-only","--sim-port","19999","--no-install-hooks"],env=env,cwd="O:/Proyectos/Clawdy-hotbar/host",stdout=open("O:/dev/T3w/d.log","w"),stderr=subprocess.STDOUT)
for _ in range(60):
    if os.path.exists(home+"/.clawd-tank/endpoint.json") and "DAEMON connected" in open("O:/dev/T3w/pet.log").read(): break
    time.sleep(0.5)
payload={"hook_event_name":"PermissionRequest","session_id":"t3-sess","cwd":"O:/x","tool_name":"Bash","tool_input":{"command":"echo hi"}}
def hook():
    return subprocess.Popen([PY,"O:/Proyectos/Clawdy-hotbar/host/clawd-tank-notify"],env=env,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
u=ctypes.windll.user32
try: ctypes.windll.shcore.SetProcessDpiAwareness(2)
except: pass
h=u.FindWindowW(None,"pet"); r=w.RECT(); u.GetWindowRect(h,ctypes.byref(r)); sc=(r.right-r.left)/320
def click(x,y):
    u.SetCursorPos(int(r.left+x*sc),int(r.top+y*sc)); time.sleep(0.5); u.mouse_event(2,0,0,0,0); time.sleep(0.05); u.mouse_event(4,0,0,0,0)
res={}
for name,(x,y) in [("allow-wrongnonce",(126,165))]:
    p=hook(); p.stdin.write(json.dumps(payload)); p.stdin.close()
    for _ in range(40):
        if open("O:/dev/T3w/pet.log").read().count("REQUEST received")>=len(res)+1: break
        time.sleep(0.25)
    time.sleep(1); click(x,y)
    try: out,err=p.communicate(timeout=10)
    except subprocess.TimeoutExpired: p.kill(); out,err=p.communicate()
    res[name]=(out.strip()[:200],err.strip()[:120])
print(json.dumps(res,indent=1))
print(open("O:/dev/T3w/pet.log").read())
pet.kill(); dm.kill()
print("--- daemon log tail"); print(open("O:/dev/T3w/d.log").read()[-700:])
