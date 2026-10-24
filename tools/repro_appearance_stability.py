"""Native presentation trace while a fixed idle frame changes scale/gap."""
import argparse
import json
import os
from pathlib import Path
import sys
import time


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--code-root',type=Path,default=Path(__file__).resolve().parents[1])
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--expect-jitter',action='store_true')
    args=parser.parse_args()
    args.out.mkdir(parents=True,exist_ok=True)
    sys.path.insert(0,str(args.code_root.resolve()))
    os.environ['GOOGLEPIGGY_QA_WINDOW']='1'
    import pig_pet as win
    from windows_pet import WindowsPet
    from animation_clock import load_manifest
    pet=WindowsPet(load_manifest(args.code_root/'assets/macos-resources'),args.out/'report.json',args.code_root,args.out/'status.json',False)
    pet.appearance.update({'petScale':1.12})
    pet.preview_dialog=True
    pet._poll_bridge=lambda **kwargs:None
    pet._poll_update=lambda:None
    def resolve():
        pet.position=('idle',0)
        pet.frame_index=0
    pet._resolve_visual=resolve
    native_render=pet._render_layered_window
    move=pet._set_window_origin
    advance=pet._advance
    samples=[]
    displayed=[0,0]
    tracking=False
    tick=0
    def record(kind):
        rect=pet._window_rect(pet.hwnd)
        samples.append({'kind':kind,'anchor':[rect[i]+displayed[i] for i in range(2)],'time':time.perf_counter()})
    def render(hwnd,*values):
        native_render(hwnd,*values)
        if hwnd==pet.hwnd:
            displayed[:]=[round((v+off)*pet.scale) for v,off in zip((410,570),pet.canvas_offset)]
            if tracking:record('bitmap-and-position')
    def reposition(hwnd,origin):
        move(hwnd,origin)
        if tracking and hwnd==pet.hwnd:record('old-bitmap-repositioned')
    def step():
        nonlocal tick,tracking
        if not tracking:
            move(pet.hwnd,(1280-displayed[0],1100-displayed[1]))
            tracking=True
            record('initial')
        changes={4:{'petScale':1.14},8:{'dialogGap':20},12:{'dialogGap':0},16:{'petScale':1.12}}
        if tick in changes:pet.appearance_events.put(('values',changes[tick]))
        if tick>=24:
            win.user32.DestroyWindow(pet.hwnd)
            return
        tick+=1
        advance()
    pet._render_layered_window=render
    pet._set_window_origin=reposition
    pet._advance=step
    pet.run()
    initial=samples[0]['anchor']
    excursion=max(abs(v-initial[i]) for row in samples for i,v in enumerate(row['anchor']))
    result={'max_anchor_excursion_px':excursion,'dpi_scale':pet.scale,'samples':samples,'code_root':str(args.code_root)}
    (args.out/'trace.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps({'max_anchor_excursion_px':excursion,'samples':len(samples),'dpi_scale':pet.scale}))
    assert excursion>1 if args.expect_jitter else excursion<=1,result


if __name__=='__main__':main()
