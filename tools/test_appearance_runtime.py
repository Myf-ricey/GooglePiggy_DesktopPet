"""Frozen HWND/settings lifetime, preview, scaling and four-edge acceptance."""
import json
import subprocess
import sys
import time
import uuid
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from codex_bridge import atomic_json
import tools.test_windows_runtime as rt
from windows_pet import APP_VERSION


def main():
    rt.STATE = rt.ROOT/'qa/appearance-native'/uuid.uuid4().hex
    rt.STATE.mkdir(parents=True)
    exe = Path(sys.argv[1]).resolve()
    process = subprocess.Popen([str(exe),'--qa-window','--no-codex-observer','--status-file',str(rt.STATE/'status.json')])
    passed = []
    try:
        rt.wait_for(lambda h:h.get('version')==APP_VERSION and h.get('window_visible'))
        for i in range(3):
            rt.command('appearance-open')
            rt.wait_for(lambda h:h.get('appearance_window_open'))
            rt.command('appearance',values={'petScale':.5+i*.5,'dialogScale':1.25,'taskScale':1.4},dialog=True,task=True)
            rt.wait_for(lambda h:h.get('appearance_preview')=={'dialog':True,'task':True})
            rt.command('appearance-close')
            rt.wait_for(lambda h:not h.get('appearance_window_open') and h.get('appearance_preview')=={'dialog':False,'task':False})
        passed.append('Three native settings open/change/close cycles; no Tcl thread crash; previews close')
        for scale in (.5,1,2):
            rt.command('appearance',values={'petScale':scale,'dialogScale':scale,'taskScale':scale,'dialogGap':200,'taskGap':200},dialog=True,task=True)
            h=rt.wait_for(lambda h:h.get('appearance',{}).get('petScale')==scale and h.get('appearance_preview',{}).get('dialog'))
            assert not h['families'] and not h['permission_request_id']
            rt.command('capture')
            rt.command('appearance',dialog=False,task=False)
            rt.wait_for(lambda h:h.get('appearance_preview')=={'dialog':False,'task':False})
            for edge in ('left','right','top','bottom'):
                rt.command('edge',edge=edge)
                h=rt.wait_for(lambda h:h['presentation']=='hidden' and h['hidden_edge']==edge)
                rect=h['tail_rect']
                assert abs((rect[2]-rect[0])-round(68*scale*h['dpi_scale']))<=1
                rt.command('reveal')
                h=rt.wait_for(lambda h:h['presentation']=='visible')
                c,w=h['content_screen_rect'],h['monitor_work']
                assert c[0]>=w[0] and c[1]>=w[1] and c[2]<=w[2] and c[3]<=w[3],(scale,edge,c,w)
            passed.append(f'{scale:.0%}: native preview isolation and four-edge scaled tail hide/reveal')
        rt.command('exit')
        assert process.wait(timeout=5)==0
        settings=json.loads((rt.STATE/'appearance.json').read_text())
        assert settings['petScale']==2 and settings['dialogGap']==200
        assert not list((rt.STATE/'permission-requests').glob('*.response.json'))
        passed.append('Clean native exit, persisted appearance, no preview permission output')
        atomic_json(rt.ROOT/'qa/appearance-runtime-report.json',{'passed':True,'pass_items':passed,'state_dir':str(rt.STATE)})
        print(json.dumps(passed,ensure_ascii=False,indent=2))
    finally:
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=5)


if __name__=='__main__':
    main()
