"""Native low-priority message canary while the update panel is rendering."""
import sys,time,json,ctypes
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import windows_pet as w
import pig_pet as win
from windows_update import Release
from update_notice import UpdateNotice
from tools.profile_windows_animation import main

ui_mode='--ui' in sys.argv
if ui_mode:
    sys.argv.remove('--ui')
    win.APP_NAME='GooglePiggy Input Regression'

original_init=w.WindowsPet.__init__
original_wndproc=w.WindowsPet._wndproc
original_schedule=w.WindowsPet._schedule_current
events=[]

def init(pet,*args,**kwargs):
    original_init(pet,*args,**kwargs)
    pet.update_notice=UpdateNotice(Release('0.5.4','Animation update','','',1,''))
    now=time.time()
    pet.store.ingest(dict(session_id='fixture',event='UserPromptSubmit',turn_id='t'),now)
    for i in range(3):
        pet.store.ingest(dict(session_id='fixture',agent_id='child'+str(i),event='SubagentStart',turn_id='c'),now)
    pet.canary_started=False
    if ui_mode:
        def received(release):
            pet.update_notice.phase='available'
            pet.update_notice.error='测试：更新按钮点击已收到（未联网）'
        pet.update_installer.start=received

def schedule(pet):
    original_schedule(pet)
    if pet.hwnd and not pet.canary_started:
        win.user32.SetTimer(pet.hwnd,77,50,None)
        pet.canary_started=True

def wndproc(pet,hwnd,msg,wp,lp):
    if msg==win.WM_TIMER and wp==77:
        events.append(time.monotonic())
        return 0
    return original_wndproc(pet,hwnd,msg,wp,lp)

w.WindowsPet.__init__=init
w.WindowsPet._schedule_current=schedule
w.WindowsPet._wndproc=wndproc
main()
out=Path(sys.argv[sys.argv.index('--out')+1])
result=dict(canary_callbacks=len(events),max_gap_ms=max([(b-a)*1000 for a,b in zip(events,events[1:])],default=None))
(out/'input-canary.json').write_text(json.dumps(result,indent=2))
print(result)
assert len(events)>30 and result['max_gap_ms']<500,'UI low-priority messages starved by animation posts'
