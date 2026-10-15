import ctypes, time, subprocess, threading, statistics
from ctypes import wintypes as w
import tkinter as tk
u=ctypes.windll.user32
try: ctypes.windll.shcore.SetProcessDpiAwareness(2)
except: pass
pet=subprocess.Popen(["O:/dev/target/release/hotbar-spike.exe"],env={**__import__("os").environ,"SPIKE_PORT":"19998"},stderr=subprocess.DEVNULL)
time.sleep(4)
h=u.FindWindowW(None,"pet"); r=w.RECT(); u.GetWindowRect(h,ctypes.byref(r)); sc=(r.right-r.left)/320
# a plain window under the pet, same rect, not topmost
clicks=[]
root=tk.Tk(); root.overrideredirect(True); root.geometry(f"{r.right-r.left}x{r.bottom-r.top}+{r.left}+{r.top}")
root.configure(bg="#335577"); root.bind("<Button-1>",lambda e:clicks.append((e.x,e.y)))
root.update(); u.SetWindowPos(h,-1,0,0,0,0,0x13)  # keep pet topmost
def pump(sec):
    t=time.time()
    while time.time()-t<sec: root.update(); time.sleep(0.01)
pump(0.5)
def move(x,y): u.SetCursorPos(int(r.left+x*sc),int(r.top+y*sc))
def click(x,y):
    move(x,y); pump(0.4); u.mouse_event(2,0,0,0,0); u.mouse_event(4,0,0,0,0); pump(0.4)
b=len(clicks); [click(10,300) for _ in range(3)]; print("transparent corner: sent 3, window below received",len(clicks)-b)
b=len(clicks); [click(160,160) for _ in range(3)]; print("on pet: sent 3, window below received",len(clicks)-b,"(expect 0)")
ex=lambda: u.GetWindowLongW(h,-20)&0x20
lat=[]
for i in range(40):
    move(10,300); pump(0.15)            # outside -> ignoring
    t=time.perf_counter(); move(160,160)
    while ex() and time.perf_counter()-t<0.5: pass
    lat.append((time.perf_counter()-t)*1000)
    move(10,300); pump(0.1)
lat.sort(); print("enter-pet latency ms: median %.1f p95 %.1f max %.1f (n=%d)"%(statistics.median(lat),lat[int(.95*len(lat))-1],lat[-1],len(lat)))
lat=[]
for i in range(40):
    move(160,160); pump(0.15)
    t=time.perf_counter(); move(10,300)
    while not ex() and time.perf_counter()-t<0.5: pass
    lat.append((time.perf_counter()-t)*1000)
lat.sort(); print("leave-pet latency ms: median %.1f p95 %.1f max %.1f"%(statistics.median(lat),lat[int(.95*len(lat))-1],lat[-1]))
pet.kill(); root.destroy()
