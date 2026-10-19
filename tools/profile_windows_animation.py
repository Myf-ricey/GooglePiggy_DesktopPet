"""Opt-in native HWND timing probe; logs stay in memory until the window closes.

Uses production timer, compose, DPI scaling and UpdateLayeredWindow paths.
Submission timestamps are not DWM/monitor presentation timestamps.
"""
import argparse
import bisect
import collections
import functools
import hashlib
import json
import os
from pathlib import Path
import platform
import sys
import time
import threading


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--code-root', type=Path, default=Path(__file__).resolve().parents[1])
    ap.add_argument('--assets', type=Path, default=Path(__file__).resolve().parents[1]/'dist/GifPigDesktopPet')
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--clips', nargs='+', default=['idle', 'carrot', 'reading'])
    ap.add_argument('--seconds', type=float, default=12)
    ap.add_argument('--observe', action='store_true')
    ap.add_argument('--assert-smooth', action='store_true')
    args = ap.parse_args(argv)
    args.out.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(args.code_root.resolve()))
    os.environ['GOOGLEPIGGY_QA_WINDOW'] = '1'
    import pig_pet as win
    import windows_pet as module
    import animation_clock as clock
    animations = clock.load_manifest(args.assets/'assets/macos-resources')
    durations = [args.seconds if args.seconds > 0 else max(4,animations[k].total_duration/1000+2) for k in args.clips]
    starts, ends, total = [],[],0
    for duration in durations:
        starts.append(total)
        total += duration
        ends.append(total)
    records, reads = [], []
    current = None
    epoch = None
    active_key = args.clips[0]
    ui_thread = threading.get_ident()
    worker_batches = []
    import codex_observer
    if hasattr(codex_observer,'ObserverReader'):
        old_read = codex_observer.ObserverReader._read
        def read_batch(*a, **kw):
            start = time.perf_counter()
            try:
                return old_read(*a, **kw)
            finally:
                worker_batches.append((time.perf_counter()-start)*1000)
        codex_observer.ObserverReader._read = read_batch

    def stamp():
        return time.perf_counter()

    def wrap(cls, name, field):
        old = getattr(cls, name)
        @functools.wraps(old)
        def timed(*a, **kw):
            start = stamp()
            try:
                return old(*a, **kw)
            finally:
                if current is not None and threading.get_ident() == ui_thread:
                    current[field] = current.get(field, 0)+(stamp()-start)*1000
        setattr(cls, name, timed)

    for cls, name, field in [
        (module.WindowsPet, '_poll_bridge', 'bridge_ms'),
        (module.WindowsPet, '_poll_update', 'update_ms'),
        (module.WindowsPet, '_write_heartbeat', 'heartbeat_ms'),
        (module.WindowsPet, '_update_hover', 'hover_ms'),
        (module.WindowsPet, 'compose', 'compose_ms'),
        (module.WindowsPet, '_render_current', 'render_ms'),
        (module.WindowsPet, '_frame_bytes', 'frame_bytes_ms'),
        (module.WindowsPet, '_render_layered_window', 'scaled_submit_ms'),
        (module.CodexObserver, 'poll', 'observer_ms'),
        (module.CodexObserver, 'refresh_metadata', 'metadata_ms'),
    ]:
        wrap(cls, name, field)
    old_get = clock.Frames.__getitem__
    def get(frames, index):
        start = stamp()
        hit = index in frames.cache
        result = old_get(frames, index)
        if current is not None and threading.get_ident() == ui_thread:
            current['image_access_ms'] = current.get('image_access_ms', 0)+(stamp()-start)*1000
            current['image_accesses'] = current.get('image_accesses', 0)+1
            current['image_misses'] = current.get('image_misses', 0)+int(not hit)
        return result
    clock.Frames.__getitem__ = get
    old_open = clock.Image.open
    def image_open(*a, **kw):
        start = stamp()
        try:
            return old_open(*a, **kw)
        finally:
            if current is not None and threading.get_ident() == ui_thread:
                current['image_opens'] = current.get('image_opens', 0)+1
                current['image_open_ms'] = current.get('image_open_ms',0)+(stamp()-start)*1000
    clock.Image.open = image_open
    from PIL import PngImagePlugin
    old_load = PngImagePlugin.PngImageFile.load
    def png_load(im,*a,**kw):
        decoding = bool(im.tile)
        start = stamp()
        try:
            return old_load(im,*a,**kw)
        finally:
            if decoding and current is not None and threading.get_ident() == ui_thread:
                current['png_decode_ms'] = current.get('png_decode_ms',0)+(stamp()-start)*1000
    PngImagePlugin.PngImageFile.load = png_load
    old_pixels = win.premultiplied_bgra
    def pixels(*a, **kw):
        start = stamp()
        result = old_pixels(*a, **kw)
        if current is not None and threading.get_ident() == ui_thread:
            current['premultiply_ms'] = current.get('premultiply_ms', 0)+(stamp()-start)*1000
        return result
    win.premultiplied_bgra = pixels

    def ordinal(key, elapsed):
        clip = animations[key]
        ms = max(0, elapsed*1000)
        n = len(clip.frames)
        if ms < clip.total_duration:
            return bisect.bisect_right(clip.ends, ms)
        intro = sum(clip.durations[:clip.loop_start])
        cycle = clip.total_duration-intro
        cycles = int((ms-intro)//cycle)
        within = intro+(ms-intro)%cycle
        return clip.loop_start+cycles*(n-clip.loop_start)+bisect.bisect_right(clip.ends, within)-clip.loop_start

    def displayed_ordinal(key, elapsed, frame):
        clip = animations[key]
        reference = ordinal(key,elapsed)
        expected_frame = clip.frame(elapsed)
        value = reference-expected_frame+frame
        count = len(clip.frames)-clip.loop_start
        # Unwrap the actual submitted frame around the independent time oracle.
        if frame >= clip.loop_start and elapsed*1000 >= clip.total_duration-100:
            value = min((value-count,value,value+count),key=lambda n:abs(n-reference))
        return value

    old_submit = win.PigPet._render_layered_window
    def submit(pet, hwnd, *a):
        start = stamp()
        result = old_submit(pet, hwnd, *a)
        if current is not None and hwnd == pet.hwnd:
            t = time.monotonic()
            current.update(submit_s=t-epoch, native_ms=(stamp()-start)*1000,
                actual_frame=pet.frame_index, target_at_submit=animations[active_key].frame(t-pet.visual_epoch),
                actual_ordinal=displayed_ordinal(active_key,t-pet.visual_epoch,pet.frame_index),
                submit_ordinal=ordinal(active_key,t-pet.visual_epoch), dpi=pet.scale)
        return result
    win.PigPet._render_layered_window = submit
    old_resolve = module.WindowsPet._resolve_visual
    def resolve(pet):
        pet.transient_key, pet.transient_once = active_key, False
        pet.visual_epoch = epoch+starts[args.clips.index(active_key)] if epoch else time.monotonic()
        if active_key == 'sleep_body':
            pet.leisure.sleep_epoch = pet.visual_epoch
        old_resolve(pet)
        if current is not None:
            current.update(target_at_resolve=pet.frame_index,
                sample_s=(getattr(pet,'animation_sample_time',None) or time.monotonic())-epoch,
                resolved_ordinal=ordinal(active_key,time.monotonic()-pet.visual_epoch))
    module.WindowsPet._resolve_visual = resolve
    old_advance = module.WindowsPet._advance
    def advance(pet):
        nonlocal current, epoch, active_key
        t = time.monotonic()
        if epoch is None:
            epoch = t
        phase = bisect.bisect_right(ends,t-epoch)
        if phase >= len(args.clips):
            win.user32.DestroyWindow(pet.hwnd)
            return
        active_key = args.clips[phase]
        current = dict(key=active_key, callback_s=t-epoch)
        start = stamp()
        old_advance(pet)
        current['callback_ms'] = (stamp()-start)*1000
        records.append(current)
        current = None
    module.WindowsPet._advance = advance
    pet = module.WindowsPet(animations, args.out/'manifest.json', args.assets,
        args.out/'codex-status.json', observe=args.observe)
    # No network/update side effects during a timing experiment.
    pet.update_startup_done = True
    pet.run()
    (args.out/'trace.json').write_text(json.dumps(records), encoding='utf-8')
    def stats(values):
        v = sorted(values)
        return dict(n=len(v), mean=sum(v)/len(v), p50=v[int((len(v)-1)*.5)],
            p95=v[int((len(v)-1)*.95)], p99=v[int((len(v)-1)*.99)], max=v[-1]) if v else {}
    summary = dict(platform=platform.platform(), python=sys.version, observe=args.observe,
        clip_seconds=dict(zip(args.clips,durations)),
        version=module.APP_VERSION, build=module.APP_BUILD,
        frozen=bool(getattr(sys,'frozen',False)),
        executable_sha256=hashlib.sha256(Path(sys.executable).read_bytes()).hexdigest(),
        worker_batch_ms=stats(worker_batches),
        timer_ms=20, source={n:hashlib.sha256((args.code_root/n).read_bytes()).hexdigest()
            for n in ['animation_clock.py','windows_pet.py','pig_pet.py','codex_observer.py','windows_animation_timer.py'] if (args.code_root/n).is_file()}, clips={})
    for key in args.clips:
        rows = [r for r in records if r['key']==key and 'actual_frame' in r]
        steps = [b['actual_ordinal']-a['actual_ordinal'] for a,b in zip(rows,rows[1:])]
        changed = [r for i,r in enumerate(rows) if not i or r['actual_ordinal']!=rows[i-1]['actual_ordinal']]
        summary['clips'][key] = dict(callback_interval_ms=stats([(b['callback_s']-a['callback_s'])*1000 for a,b in zip(rows,rows[1:])]),
            changed_frame_interval_ms=stats([(b['submit_s']-a['submit_s'])*1000 for a,b in zip(changed,changed[1:])]),
            skipped_frames=sum(max(0,s-1) for s in steps), expected_advances=sum(max(0,s) for s in steps),
            late_submissions=sum(r['actual_frame']!=r['target_at_submit'] for r in rows), submissions=len(rows),
            image_opens=sum(r.get('image_opens',0) for r in rows),
            warm_image_opens=sum(r.get('image_opens',0) for r in rows if r['callback_s']-starts[args.clips.index(key)] >= animations[key].total_duration/1000),
            stages={field:stats([r.get(field,0) for r in rows]) for field in ['callback_ms','bridge_ms','observer_ms','metadata_ms','image_access_ms','image_open_ms','png_decode_ms','compose_ms','premultiply_ms','render_ms','native_ms','heartbeat_ms']})
    (args.out/'summary.json').write_text(json.dumps(summary,indent=2), encoding='utf-8')
    print(json.dumps({k:{f:v[f] for f in ['callback_interval_ms','skipped_frames','expected_advances','image_opens']} for k,v in summary['clips'].items()},indent=2))
    if args.assert_smooth:
        assert all(v['callback_interval_ms']['p95']<35 and v['skipped_frames']/max(1,v['expected_advances'])<.10 for v in summary['clips'].values()), 'Animation stalls / dropped frames exceed budget'


if __name__ == '__main__':
    main()
