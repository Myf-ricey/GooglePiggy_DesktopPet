"""Cold-start final EXE with saved sizes; check actual pig bounds on one display."""
import argparse
import ctypes
import json
from pathlib import Path
import subprocess
import sys
import uuid

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from animation_clock import load_manifest
from codex_bridge import atomic_json
import pig_pet as win
from windows_pet import WindowsPet
import tools.test_windows_runtime as rt

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--exe',type=Path,default=rt.TEST_EXE)
    args=parser.parse_args()
    win.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    clips=load_manifest(ROOT/'assets/macos-resources')
    results=[]
    for size in (.5,.8,1,2):
        rt.STATE=ROOT/'qa/startup-native'/f'native-{size}-{uuid.uuid4().hex}'
        rt.STATE.mkdir(parents=True)
        atomic_json(rt.STATE/'appearance.json',{'petScale':size})
        process=subprocess.Popen([str(args.exe),'--qa-window','--no-codex-observer','--status-file',str(rt.STATE/'status.json')])
        try:
            first=rt.wait_for(lambda h:h.get('pid')==process.pid and h.get('window_visible'))
            # Creation writes a heartbeat before submitting the first bitmap.
            # Wait for the next sample so DPI and cropped geometry are final.
            h=rt.wait_for(lambda h:h.get('pid')==process.pid and h.get('window_visible')
                          and h.get('updated_at')!=first.get('updated_at'))
            # Derive the unchanged sprite/canvas offsets from production compose;
            # the position under test comes from the actual frozen HWND heartbeat.
            model=WindowsPet(clips,rt.STATE/'report.json',ROOT,rt.STATE/'model-status.json',False)
            model.appearance.update({'petScale':size})
            model.scale=h['dpi_scale']
            model.position=(h['current_key'],h['frame_index'])
            model.compose(*model.position)
            local=model._current_pet_local_bounds()
            body=tuple(v+h['window_rect'][i%2] for i,v in enumerate(local))
            work=h['monitor_work']
            assert body[0]>=work[0] and body[1]>=work[1] and body[2]<=work[2] and body[3]<=work[3],(size,body,work,h)
            results.append(dict(size=size,dpi=h['dpi_scale'],window=h['window_rect'],body=body,work=work,build=h['build']))
            rt.command('exit')
            assert process.wait(timeout=5)==0
        finally:
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=5)
    report=dict(passed=True,cases=results,physical_environment='single physical display',dpi_scales=sorted({r['dpi'] for r in results}))
    atomic_json(ROOT/'qa/native-startup-report.json',report)
    print(json.dumps(report,indent=2))


if __name__=='__main__':
    main()
