"""Windows presentation of the shared macOS 0.4 artwork and behavior."""
from __future__ import annotations
import ctypes
import json
import os
import time
import queue
import threading
import math
from pathlib import Path
from functools import lru_cache
from PIL import Image, ImageDraw, ImageFilter
import pig_pet as win
from animation_clock import AnimationClock
from family_store import FamilyStore
from codex_observer import CodexObserver
from leisure import Leisure
from codex_bridge import atomic_json
from windows_update import Checker, Installer, prepare_helper, Release, validate_tree
from update_notice import UpdateNotice
from windows_animation_timer import WindowAnimationTimer, ANIMATION_MESSAGE

SLOTS = [(310,575),(410,615),(510,575)]
APP_VERSION = '0.5.5-windows'
APP_BUILD = '20261019.5-input-release'


@lru_cache(maxsize=4)
def permission_surface(rect):
    left,top,right,bottom = rect
    height = bottom-top
    mask_large = Image.new('L',(1920,1920))
    shape = ImageDraw.Draw(mask_large)
    shape.rounded_rectangle(tuple(v*3 for v in rect),60,fill=255)
    shape.polygon([(402*3,(bottom-1)*3),(418*3,(bottom-1)*3),(410*3,(bottom+10)*3)],fill=255)
    mask = mask_large.resize((640,640),Image.Resampling.LANCZOS)
    inside = mask.filter(ImageFilter.MinFilter(5))
    gradient = Image.new('RGBA',(640,640))
    pixels = gradient.load()
    for y in range(max(0,top),bottom+14):
        for x in range(left,right+1):
            t = min(1,((x-left)*320+(y-top)*(height+10))/(320**2+(height+10)**2))
            pixels[x,y] = (round(253-2*t),round(249-19*t),round(246-11*t),255)
    shadow = Image.new('RGBA',(640,640),(0,0,0,0))
    shadow.putalpha(mask.filter(ImageFilter.GaussianBlur(8)).point(lambda v:round(v*.18)))
    canvas = Image.new('RGBA',(640,640))
    canvas.alpha_composite(shadow,(0,4))
    border = Image.new('RGBA',(640,640),(231,169,188,255))
    canvas.alpha_composite(Image.composite(border,Image.new('RGBA',(640,640)),mask))
    canvas.alpha_composite(Image.composite(gradient,Image.new('RGBA',(640,640)),inside))
    return canvas


def union(rects):
    return (min(r[0] for r in rects),min(r[1] for r in rects),max(r[2] for r in rects),max(r[3] for r in rects))


def resize_alpha(image, size):
    return image.convert('RGBa').resize(size,Image.Resampling.BILINEAR).convert('RGBA')


def scaled_frame_bytes(canvas, size):
    """Same bilinear pixels, without filtering the mostly transparent window.

    Align crop edges to the source/destination pixel grid and include the
    filter's transparent border, so crop resizing retains the full image phase.
    """
    bounds = canvas.getbbox()
    if bounds is None:
        return bytes(size[0]*size[1]*4)
    gx,gy = (n//math.gcd(n,d) for n,d in zip(canvas.size,size))
    if gx > 16 or gy > 16:
        return win.premultiplied_bgra(resize_alpha(canvas,size))
    left,top,right,bottom = bounds
    left,top = max(0,(left-2)//gx*gx),max(0,(top-2)//gy*gy)
    right = min(canvas.width,((right+2+gx-1)//gx)*gx)
    bottom = min(canvas.height,((bottom+2+gy-1)//gy)*gy)
    dest = (left*size[0]//canvas.width,top*size[1]//canvas.height,
        right*size[0]//canvas.width,bottom*size[1]//canvas.height)
    sprite = resize_alpha(canvas.crop((left,top,right,bottom)),(dest[2]-dest[0],dest[3]-dest[1]))
    result = Image.new('RGBa',size)
    result.paste(sprite.convert('RGBa'),dest[:2])
    return result.tobytes('raw','BGRa')


def family_tail_rects(edge, main, screen, count, scale=1):
    rects = [main]
    vertical = edge in ('left','right')
    side, gap = round(32*scale), round(4*scale)
    start = main[3]+gap if vertical else main[2]+gap
    low, high = (screen[1],screen[3]) if vertical else (screen[0],screen[2])
    # Shift the entire along-edge group to retain ordering at either corner.
    total = round(68*scale)+count*(side+gap)
    begin = max(low+4,min((main[1] if vertical else main[0]),high-total-4))
    shift = begin-(main[1] if vertical else main[0])
    rects[0] = (main[0],main[1]+shift,main[2],main[3]+shift) if vertical else (main[0]+shift,main[1],main[2]+shift,main[3])
    start += shift
    for i in range(count):
        along = start+i*(side+gap)
        if edge == 'left':
            rect = (screen[0]-round(18*scale),along,screen[0]+round(14*scale),along+side)
        elif edge == 'right':
            rect = (screen[2]-round(14*scale),along,screen[2]+round(18*scale),along+side)
        elif edge == 'top':
            rect = (along,screen[1]-round(18*scale),along+side,screen[1]+round(14*scale))
        else:
            rect = (along,screen[3]-round(14*scale),along+side,screen[3]+round(18*scale))
        rects.append(rect)
    return rects


class WindowsPet(win.PigPet):
    def __init__(self, animations, report_path, app_dir, status_path, observe=True):
        self.store = FamilyStore()
        self.observer = CodexObserver(self.store,status_path.parent,enabled=observe)
        if observe:
            self.observer.enable_background()
        self.clock = AnimationClock(animations)
        self.leisure = Leisure(time.monotonic())
        self.position = ('idle',0)
        self.visual_epoch = time.monotonic()
        self.idle_epoch = self.visual_epoch
        self.hidden_tokens = set()
        self.hidden_family = ''
        self.hidden_since = 0
        self.reveal_completion = ''
        self.celebration_family = ''
        self.celebration_started = 0
        self.known_work = set()
        self.drag_direction = -1
        self.drag_last_x = None
        self.drag_accum = 0
        self.child_positions, self.child_rects = {}, {}
        self.selector_visible, self.selector_last_hover = False, 0
        self.selector_rect, self.selector_rows = None, []
        self.selector_scroll, self.selector_down = 0, None
        self.focused_child = ''
        self.permission_page, self.permission_viewed = 0, set()
        self.permission_actors = set()
        self.permission_visual_epoch = time.monotonic()
        self.permission_lines_key, self.permission_lines = None, []
        self.last_canvas = None
        self.last_family_poll = 0
        self.scale = 1
        self.scaled_once = False
        self.animation_timer_started = False
        self.animation_timer = None
        self.animation_sample_time = None
        self.qa_commands = set()
        if os.environ.get('GOOGLEPIGGY_QA_WINDOW') == '1' and not observe:
            seen = win.read_json_file(status_path.parent/'qa-consumed.json')
            self.qa_commands = set(seen.get('ids',[])) if seen else set()
        self.update_checker = Checker(APP_VERSION.removesuffix('-windows'))
        self.update_installer = Installer(status_path.parent)
        self.update_notice = None
        self.update_down = None
        self.update_package = None
        self.update_helper_job = None
        self.update_helper_started = 0
        self.update_helper_events = queue.Queue()
        self.update_startup_done = False
        self.reduced_motion = False
        super().__init__(animations,report_path,app_dir,status_path)

    @property
    def current_key(self):
        return self.position[0]

    @property
    def can_hide_at_desktop_edge(self):
        return self.mode == 'responsive' and self.edge_placement is None and self.edge_transition is None and bool(self.edge_tail_assets)

    @property
    def activity_requires_visible_pet(self):
        if self.hidden_family:
            node = self.store.nodes.get(self.hidden_family)
            return bool(node and not node.active and node.status == 'success' and
                node.payload.get('event') in {'Stop','TaskCompleteFallback'} and
                node.completion is not None and node.completion > self.hidden_since and
                not any(n.active for n in self.store.nodes.values() if self._belongs_to_hidden_family(n)))
        return bool(self.permission_request or self.store.work_tokens()-self.hidden_tokens)

    def _belongs_to_hidden_family(self, node):
        seen = set()
        while node.parent and node.id not in seen:
            seen.add(node.id)
            if node.parent == self.hidden_family:
                return True
            node = self.store.nodes.get(node.parent)
            if node is None:
                break
        return False

    def _apply_bridge_payload(self,payload):
        # Legacy events have their own actor, never occupy another task's slot.
        if not payload.get('session_id') and payload.get('token'):
            p = dict(payload,session_id='legacy')
            return self.store.ingest(p,time.time())
        return False

    def _switch_visual(self,key,once=False):
        self.transient_key, self.transient_once = key, once
        self.visual_epoch = time.monotonic()
        self._resolve_visual()
        self._render_current()
        self._schedule_current()

    def _poll_bridge(self,force=False):
        now = time.monotonic()
        if not force and now-self.last_family_poll < .2:
            return False
        self.last_family_poll = now
        self.observer.poll()
        pinned = self.hidden_family or self.reveal_completion
        if self.celebration_family:
            node = self.store.nodes.get(self.celebration_family)
            if (now-self.celebration_started < self.animations['jump'].total_duration/1000
                    and node and not node.active):
                pinned = pinned or self.celebration_family
            else:
                self.celebration_family = ''
        if pinned:
            self.store.select(pinned)
        legacy = win.read_status(self.status_path)
        self._apply_bridge_payload(legacy)
        tokens = self.store.work_tokens()
        if tokens-self.known_work:
            self.leisure.reset(now)
            if not self.dragging and not self.edge_transition:
                self.transient_key = None
        self.known_work |= tokens
        self._sync_family_permission()
        if self.permission_request:
            self.leisure.cancel()
            if not self.dragging and not self.edge_transition:
                self.transient_key = None
        wall = time.time()
        for node in self.store.nodes.values():
            state = 'question' if node.id in self.permission_actors else self.store.visual(node,wall)
            parent = self.store.nodes.get(node.parent)
            changed = max(node.changed,parent.changed) if parent and self.store.paused(node) else node.changed
            self.clock.update(node.id,node.turn,state,now,max(0,wall-changed))
        self._reveal_for_activity_if_needed()
        return False

    def _sync_family_permission(self):
        now = time.time()
        node = self.store.nodes.get(self.focused_child) or self.store.nodes.get(self.store.selected)
        candidates = ([node] if node else []) + self.store.children(self.store.selected,now)
        if self.permission_request_id:
            actor = self.permission_request.get('agent_id') or self.permission_request.get('session_id')
            old = self.store.nodes.get(actor)
            if old in candidates:
                candidates = [old]+[n for n in candidates if n is not old]
        pending = {}
        for file in sorted(self.permission_dir.glob('*.request.json')):
            p = win.read_json_file(file)
            if not p:
                continue
            request_id = p.get('request_id','')
            actor = p.get('agent_id') or p.get('session_id')
            actor_node = self.store.nodes.get(actor)
            expired = self._permission_request_expired(p)
            stale = actor_node is not None and (actor_node.status == 'interrupted' or p.get('turn_id') and actor_node.turn and p['turn_id'] != actor_node.turn or actor_node.completion is not None)
            helper_pid = p.get('hook_pid')
            dead = False
            if helper_pid:
                open_process = win.kernel32.OpenProcess
                open_process.argtypes = [ctypes.c_uint,ctypes.c_bool,ctypes.c_uint]
                open_process.restype = win.wintypes.HANDLE
                handle = open_process(0x1000,False,int(helper_pid))
                dead = not bool(handle)
                if handle:
                    code = ctypes.c_uint()
                    get_exit = win.kernel32.GetExitCodeProcess
                    get_exit.argtypes = [win.wintypes.HANDLE,ctypes.POINTER(ctypes.c_uint)]
                    dead = bool(get_exit(handle,ctypes.byref(code))) and code.value != 259
                    win.kernel32.CloseHandle(handle)
            if expired or stale or dead:
                file.unlink(missing_ok=True)
                self._permission_response_path(request_id).unlink(missing_ok=True)
                if actor_node and actor_node.status=='permission' and not stale:
                    self.store.ingest(dict(actor_node.payload,status='idle',event='PermissionNoDecision',token='expired-'+request_id,permission_request_id=''),time.time())
                continue
            if not self._permission_response_path(request_id).exists():
                pending.setdefault(actor,[]).append(p)
        request = None
        self.permission_actors = set(pending)
        for actor in candidates:
            requests = pending.get(actor.id,[])
            if requests:
                request = min(requests,key=lambda p:p.get('created_at',''))
                break
        old_id = self.permission_request_id
        self.permission_request = request
        self.permission_request_id = request.get('request_id','') if request else ''
        if old_id != self.permission_request_id:
            self.permission_page = 0
            self.permission_button_down = None
            self.permission_visual_epoch = time.monotonic()
        self.bridge_status = node.status if node else 'idle'

    def _resolve_visual(self):
        now = self.animation_sample_time if self.animation_sample_time is not None else time.monotonic()
        wall = time.time()
        if self.dragging:
            self.position = ('left',self.animations['left'].frame(now-self.visual_epoch))
        elif self.transient_key:
            clip = self.animations[self.transient_key]
            elapsed = now-self.visual_epoch
            if self.transient_once and elapsed >= clip.total_duration/1000:
                self.transient_key = None
                return self._resolve_visual()
            self.position = (clip.key,clip.frame(elapsed,self.transient_once))
        elif self.permission_request:
            self.position = ('question',self.animations['question'].frame(now-self.permission_visual_epoch,True))
        else:
            selected = self.store.nodes.get(self.store.selected)
            state = self.store.visual(selected,wall) if selected else 'idle'
            active = bool(self.store.work_tokens())
            if active or selected and (selected.active or state == 'jump' and self.clock.position(selected.id,now)):
                self.leisure.cancel()
                self.position = self.clock.position(selected.id,now) if selected else None
            else:
                self.leisure.tick(now,not self.mouse_down and self.edge_placement is None and self.edge_transition is None)
                self.position = self.leisure.position(self.animations,now)
            self.position = self.position or ('idle',self.animations['idle'].frame(now-self.idle_epoch))
        self.frame_index = self.position[1]

    def _advance(self):
        self._qa_control()
        self._poll_bridge()
        self._poll_update()
        self._resolve_visual()
        self._update_hover()
        self._render_current()
        self._write_heartbeat()
        self._schedule_current()

    def _qa_control(self):
        # Explicit isolated developer mode; never reads commands in production.
        if os.environ.get('GOOGLEPIGGY_QA_WINDOW') != '1' or self.observer.enabled:
            return
        path = self.status_path.parent/'qa-command.json'
        command = win.read_json_file(path)
        if not command or command.get('id') in self.qa_commands:
            return
        self.qa_commands.add(command.get('id'))
        atomic_json(self.status_path.parent/'qa-consumed.json',{'ids':sorted(self.qa_commands)})
        action = command.get('action')
        if action == 'preview' and command.get('key') in self.animations:
            self._switch_visual(command['key'],once=bool(command.get('once')))
        elif action == 'rest' and not self.store.work_tokens():
            self.transient_key=None
            self.leisure.enter(time.monotonic())
        elif action == 'sleep-click':
            self.leisure.click(time.monotonic(),command.get('wake'))
        elif action == 'edge':
            edge = command.get('edge')
            monitor = win.enumerate_monitor_infos()[0]
            bounds = self._current_pet_local_bounds()
            rect = self._window_rect(self.hwnd)
            x,y = rect[:2]
            if edge=='left': x=monitor.frame[0]-bounds[0]-2
            elif edge=='right': x=monitor.frame[2]-bounds[2]+2
            elif edge=='top': y=monitor.frame[1]-bounds[1]-2
            elif edge=='bottom': y=monitor.frame[3]-bounds[3]+2
            else: return
            self._set_window_origin(self.hwnd,(x,y))
            self._begin_edge_hide_if_needed()
        elif action == 'reveal':
            self._begin_edge_reveal(True)
        elif action == 'select' and command.get('actor') in self.store.nodes:
            self.store.select(command['actor'])
            self.focused_child=''
        elif action == 'capture':
            target = self.status_path.parent/'captures'
            target.mkdir(exist_ok=True)
            self.compose().save(target/(str(len(self.qa_commands))+'.png'))
        elif action == 'update-preview':
            release = Release('0.5.2','• 更新体验更顺畅\n• 修复后台内部会话误触发','', '', 1, '')
            self.update_notice = UpdateNotice(release if command.get('kind','available')=='available' else None,
                'fixture' if command.get('kind')=='failed' else None)
            self._fit_update_notice()
        elif action == 'update-dismiss':
            self._update_action('dismiss')
        elif action == 'update-install':
            package = Path(command['package']).resolve()
            number = command['version']
            validate_tree(package,number)
            self.update_notice = UpdateNotice(Release(number,'离线更新验收','','',1,''))
            self.update_notice.phase = 'ready'
            self.update_package = package
        elif action == 'exit':
            win.user32.DestroyWindow(self.hwnd)

    def _schedule_current(self):
        if self.hwnd and not self.animation_timer_started:
            try:
                self.animation_timer = WindowAnimationTimer(self.hwnd)
            except OSError:
                # Older Windows builds retain a periodic fallback, never reset
                # after rendering (which would add render time to every period).
                win.user32.SetTimer(self.hwnd,self.timer_id,20,None)
            self.animation_timer_started = True

    def compose(self,key=None,index=None):
        now = self.animation_sample_time if self.animation_sample_time is not None else time.monotonic()
        key, index = (key,index) if key is not None else self.position
        canvas = self.animations[key].frames[index].copy()
        if key == 'left' and self.dragging and self.drag_direction > 0:
            # Mirror around body x=410, not around the transparent canvas centre.
            canvas = canvas.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
            shifted = Image.new('RGBA',(640,640))
            shifted.alpha_composite(canvas,(180,0))
            canvas = shifted
        if key == 'sleep_body':
            tail_elapsed = now-self.leisure.tail_epoch if self.leisure.tail_epoch is not None else 2
            tail_index = self.animations['sleep_tail'].frame(tail_elapsed,True) if tail_elapsed < 1.44 else 0
            canvas.alpha_composite(self.animations['sleep_tail'].frames[tail_index])
            canvas.alpha_composite(self.animations['sleep_z'].frames[self.animations['sleep_z'].frame(now-self.leisure.sleep_epoch)])
        if key == 'jump':
            node = self.store.nodes.get(self.store.selected)
            self.success_effect_started = (self.celebration_started if self.celebration_family == self.store.selected
                else now-max(0,time.time()-node.completion) if node and node.completion else self.visual_epoch)
            self._composite_success_effects(canvas)
        children = self.store.children(self.store.selected,time.time())
        self.child_rects = {}
        for i,node in enumerate(children[:3]):
            target = SLOTS[i]
            old = self.child_positions.get(node.id,target)
            point = tuple(a+.14*(b-a) for a,b in zip(old,target))
            self.child_positions[node.id] = point
            if self.dragging:
                child_key,child_index = 'left',self.animations['left'].frame(now-self.visual_epoch)
            elif self.edge_transition:
                child_key,child_index = 'edge_reveal',self.animations['edge_reveal'].frame(now-self.visual_epoch,True)
            else:
                pos = self.clock.position(node.id,now)
                if not pos:
                    continue
                child_key,child_index = pos
                if child_key == 'carrot':
                    child_index = self.animations['carrot'].frame(max(0,time.time()-node.changed)*1.25)
            sprite = self.animations[child_key].frames[child_index]
            # Keep the whole artwork coordinate system while resizing; no frame-by-frame centering.
            sprite = resize_alpha(sprite,(261,307))
            if self.dragging and (int((now-self.visual_epoch)/.6)+i)%2:
                sprite = sprite.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
                anchor_x = 261-410*.408
            else:
                anchor_x = 410*.408
            origin = (round(point[0]-anchor_x),round(point[1]-570*.48))
            canvas.alpha_composite(sprite,origin)
            bounds = sprite.getbbox()
            if bounds:
                self.child_rects[node.id] = tuple(bounds[j]+origin[j%2] for j in range(4))
        if len(children)>3:
            ImageDraw.Draw(canvas).text((540,570),'+'+str(len(children)-3),font=win.load_ui_font(16,True),fill=(96,84,88,255))
        if self.selector_visible:
            self._composite_selector(canvas)
        if self.permission_request:
            self._composite_permission_bubble(canvas)
        elif self.update_notice:
            self.update_notice.draw(canvas,APP_VERSION.removesuffix('-windows'),win.load_ui_font,permission_surface,win.wrap_text_by_width,self.reduced_motion)
        self.last_canvas = canvas
        return canvas

    def _frame_bytes(self,key,index):
        return win.premultiplied_bgra(self.compose(key,index))

    def _render_current(self):
        if self.hwnd is None:
            return
        self.compose(self.current_key,self.frame_index)
        # Convert only the final DPI-sized image. The old path converted the
        # 640px canvas and then discarded those bytes at non-100% DPI.
        self._render_layered_window(self.hwnd,None,640,640)

    def run(self):
        # Per-monitor awareness must precede the first HWND. Coordinates passed
        # to Win32 stay physical; rendering and hit testing use 640-point units.
        try:
            win.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
        except (AttributeError,OSError):
            pass
        super().run()

    def _render_layered_window(self,hwnd,pixels,width,height):
        if hwnd == self.hwnd:
            try:
                get_dpi = win.user32.GetDpiForWindow
                get_dpi.argtypes = [win.wintypes.HWND]
                get_dpi.restype = ctypes.c_uint
                self.scale = (get_dpi(hwnd) or 96)/96
            except AttributeError:
                self.scale = 1
            # compose() is straight-alpha; feed exactly one premultiplication.
            if self.scale != 1 and self.last_canvas is not None:
                width,height = round(width*self.scale),round(height*self.scale)
                pixels = scaled_frame_bytes(self.last_canvas,(width,height))
            elif pixels is None:
                pixels = win.premultiplied_bgra(self.last_canvas)
            if not self.scaled_once:
                rect = self._window_rect(hwnd)
                if rect:
                    self._set_window_origin(hwnd,(rect[0]+640-width,rect[1]+640-height))
                self.scaled_once = True
        super()._render_layered_window(hwnd,pixels,width,height)

    def _cursor_window_position(self):
        point = super()._cursor_window_position()
        return (round(point[0]/self.scale),round(point[1]/self.scale)) if point else None

    def _composite_selector(self,canvas):
        roots = self.store.roots(time.time())
        count = max(1,min(6,len(roots)))
        left,bottom,width,height = 270,425,280,count*34+12
        top = bottom-height
        self.selector_rect = (left,top,left+width,bottom)
        draw = ImageDraw.Draw(canvas)
        draw.rounded_rectangle(self.selector_rect,12,fill=(220,218,222,237),outline=(245,242,245,245),width=1)
        self.selector_scroll = min(self.selector_scroll,max(0,len(roots)-6))
        self.selector_rows = []
        font = win.load_ui_font(14)
        if not roots:
            draw.text((left+18,top+12),'当前好像没有任务唔～',font=font,fill=(95,89,96,255))
        for i,node in enumerate(roots[self.selector_scroll:self.selector_scroll+6]):
            rect = (left+6,top+6+i*34,left+width-6,top+40+i*34)
            if node.id == self.store.selected:
                draw.rounded_rectangle(rect,7,fill=(245,240,246,235))
            if node.unread:
                draw.ellipse((left+12,rect[1]+13,left+19,rect[1]+20),fill=(47,137,229,255))
            title = node.title
            while title and draw.textlength(title,font=font)>width-48:
                title = title[:-2]+'…' if not title.endswith('…') else title[:-2]+'…'
            draw.text((left+28,rect[1]+7),title,font=font,fill=(78,72,80,255))
            self.selector_rows.append((rect,node.id))

    def _update_hover(self):
        if self.update_notice or self.permission_request:
            self.selector_visible = False
            return
        point = self._cursor_window_position()
        if point and self.edge_placement is None and not self.dragging:
            hit = self._point_in_rect(point,self._logical_pet_bounds()) or self._point_in_rect(point,self.selector_rect if self.selector_visible else None)
            # The small corridor connects pig head and fixed panel without flicker.
            hit = hit or self.selector_visible and self._point_in_rect(point,(270,420,550,445))
            if hit:
                self.selector_visible,self.selector_last_hover = True,time.monotonic()
            elif time.monotonic()-self.selector_last_hover >= .4:
                self.selector_visible = False
        else:
            self.selector_visible = False

    def _composite_permission_bubble(self,canvas):
        draw = ImageDraw.Draw(canvas)
        font, title_font = win.load_ui_font(14),win.load_ui_font(11)
        request = self.permission_request
        detail = str(request.get('summary') or 'Codex 请求权限')
        if detail != self.permission_lines_key:
            self.permission_lines_key = detail
            self.permission_lines = win.wrap_text_by_width(draw,detail,font,280,10000)
        lines = self.permission_lines
        self.permission_page = min(self.permission_page,max(0,len(lines)-11))
        visible = lines[self.permission_page:self.permission_page+11]
        height = 104+max(1,len(visible))*20
        left,right,bottom,top = 250,570,348,348-height
        rect = (left,top,right,bottom)
        self.permission_bubble_rect = (left,top,right,bottom+10)
        canvas.alpha_composite(permission_surface(rect))
        draw = ImageDraw.Draw(canvas)
        rose = (176,124,129,255)
        draw.ellipse((left+20,top+21,left+26,top+27),fill=rose)
        draw.text((left+34,top+17),'CODEX · 需要你的确认',font=title_font,fill=rose)
        for i,line in enumerate(visible):
            draw.text((left+20,top+43+i*20),line,font=font,fill=(76,67,70,255))
        long = len(lines)>11
        if not long or self.permission_page+11 >= len(lines):
            self.permission_viewed.add(self.permission_request_id)
        button_y = bottom-48
        buttons = {'deny':(left+20,button_y,left+120,bottom-16),'allow':(right-136,button_y,right-20,bottom-16)}
        self.permission_buttons = buttons
        for action,button in buttons.items():
            disabled = action == 'allow' and self.permission_request_id not in self.permission_viewed
            fill = (223,207,214,255) if disabled else rose if action == 'allow' else (242,238,231,255)
            draw.rounded_rectangle(button,10,fill=fill)
            draw.text(((button[0]+button[2])/2,(button[1]+button[3])/2),{'allow':'允许一次','deny':'拒绝'}[action],font=win.load_ui_font(13),anchor='mm',fill=(255,255,255,255) if action=='allow' and not disabled else (82,76,76,255))

    def _write_permission_decision(self,decision):
        if decision == 'allow' and self.permission_request_id not in self.permission_viewed:
            return
        if decision in {'allow','deny'} and self.permission_request_id:
            atomic_json(self._permission_response_path(self.permission_request_id),{'request_id':self.permission_request_id,'decision':decision,'updated_at':win.utc_timestamp(),'source':'pig-pet','message':'用户从 GooglePiggy 拒绝本次请求。' if decision=='deny' else ''})
            self.permission_request = None
            self.permission_request_id = ''

    def _logical_pet_bounds(self):
        frame = self.animations[self.position[0]].frames[self.position[1]]
        rects = [frame.getbbox() or (334,436,486,570)]
        rects.extend(self.child_rects.values())
        return union(rects)

    def _current_pet_local_bounds(self):
        return tuple(round(v*self.scale) for v in self._logical_pet_bounds())

    def _current_content_local_bounds(self):
        # Always reserve three slots on reveal, including when no children exist yet.
        rects = [self._logical_pet_bounds(),(266,505,554,620)]
        if self.permission_request and self.permission_bubble_rect:
            rects.append(self.permission_bubble_rect)
        elif self.update_notice:
            rects.append(self.update_notice.bounds)
        return tuple(round(v*self.scale) for v in union(rects))

    def _edge_bottom_drop(self,edge,pet_bounds):
        return 0.0 # The reserved family must remain inside the work area.

    def _begin_edge_hide_if_needed(self):
        self.hidden_tokens = self.store.work_tokens().copy()
        node = self.store.nodes.get(self.store.selected)
        self.hidden_family = node.id if node and (node.active or any(n.active for n in self.store.children(node.id,time.time()))) else ''
        self.hidden_since = time.time()
        self.leisure.cancel()
        result = super()._begin_edge_hide_if_needed()
        if not result:
            self.hidden_family = ''
        return result

    def _begin_edge_reveal(self, play_reveal_animation):
        if self.hidden_family and self.activity_requires_visible_pet:
            self.reveal_completion = self.hidden_family
        result = super()._begin_edge_reveal(play_reveal_animation)
        if result:
            self.hidden_family = ''
        return result

    def _finish_edge_reveal(self):
        actor = self.reveal_completion
        self.reveal_completion = ''
        if actor and actor in self.store.nodes and not self.store.nodes[actor].active:
            self.celebration_family = actor
            self.celebration_started = time.monotonic()
            node = self.store.nodes[actor]
            self.clock.tracks.pop(actor,None)
            self.clock.update(actor,node.turn,'jump',self.celebration_started)
            self.store.select(actor)
            self.transient_key = None
            self._resolve_visual()
        super()._finish_edge_reveal()

    def _show_tail(self,placement):
        if not self.tail_hwnd:
            return
        count = min(3,len(self.store.children(self.store.selected,time.time())))
        main = placement.tail_rect
        scale = self.scale
        side, overlap = round(68*scale),round(30*scale)
        screen = placement.monitor.frame
        if placement.edge in ('left','right'):
            y = (main[1]+main[3]-side)//2
            x = screen[0]-(side-overlap) if placement.edge=='left' else screen[2]-overlap
        else:
            x = (main[0]+main[2]-side)//2
            y = screen[1]-(side-overlap) if placement.edge=='top' else screen[3]-overlap
        main = (x,y,x+side,y+side)
        rects = family_tail_rects(placement.edge,main,screen,count,scale)
        bounds = union(rects)
        image = Image.new('RGBA',(bounds[2]-bounds[0],bounds[3]-bounds[1]))
        for i,rect in enumerate(rects):
            source = self.edge_tail_assets[placement.edge]
            source = resize_alpha(source,(rect[2]-rect[0],rect[3]-rect[1]))
            image.alpha_composite(source,(rect[0]-bounds[0],rect[1]-bounds[1]))
        win.user32.SetWindowPos(self.tail_hwnd,win.HWND_TOPMOST,bounds[0],bounds[1],image.width,image.height,win.SWP_NOACTIVATE|win.SWP_SHOWWINDOW)
        self._render_layered_window(self.tail_hwnd,win.premultiplied_bgra(image),image.width,image.height)
        win.user32.ShowWindow(self.tail_hwnd,win.SW_SHOW)

    def _handle_left_button_down(self):
        point = self._cursor_window_position()
        if self.permission_request and point and self._point_in_rect(point,self.permission_bubble_rect):
            super()._handle_left_button_down()
            return
        if self.update_notice and not self.permission_request and point and self._point_in_rect(point,self.update_notice.bounds):
            self.update_down = next((a for a,r in self.update_notice.buttons.items() if self._point_in_rect(point,r)), 'surface')
            win.user32.SetCapture(self.hwnd)
            return
        if point:
            for rect,actor in self.selector_rows if self.selector_visible else []:
                if self._point_in_rect(point,rect):
                    self.selector_down = actor
                    win.user32.SetCapture(self.hwnd)
                    return
            for actor,rect in self.child_rects.items():
                if self._point_in_rect(point,rect) and self.store.nodes[actor].status=='permission':
                    self.focused_child = actor
                    self._sync_family_permission()
                    return
        self.drag_sleep_phase = self.leisure.phase
        self.drag_last_x = None
        self.drag_accum = 0
        super()._handle_left_button_down()
        self.drag_can_play_flat = not self.store.work_tokens() and not self.permission_request

    def _handle_mouse_move(self,wparam):
        was_dragging = self.dragging
        super()._handle_mouse_move(wparam)
        if self.dragging:
            cursor = win.POINT()
            win.user32.GetCursorPos(ctypes.byref(cursor))
            if self.drag_last_x is not None:
                self.drag_accum += cursor.x-self.drag_last_x
                if abs(self.drag_accum)>=2*self.scale:
                    self.drag_direction = 1 if self.drag_accum>0 else -1
                    self.drag_accum=0
            self.drag_last_x = cursor.x
            if not was_dragging:
                if self.drag_sleep_phase == 'sleeping':
                    self.leisure.reset(time.monotonic())
                else:
                    self.leisure.cancel()
            self._resolve_visual()

    def _restore_after_drag(self,previous):
        self.transient_key = None
        self._poll_bridge(force=True)
        self._resolve_visual()
        self._render_current()

    def _handle_left_button_up(self):
        if self.update_down:
            action,self.update_down = self.update_down,None
            win.user32.ReleaseCapture()
            point = self._cursor_window_position()
            if self.update_notice and not self.permission_request and point and self._point_in_rect(point,self.update_notice.buttons.get(action)):
                self._update_action(action)
            return
        if self.selector_down:
            actor,self.selector_down = self.selector_down,None
            point = self._cursor_window_position()
            win.user32.ReleaseCapture()
            if any(n==actor and self._point_in_rect(point,rect) for rect,n in self.selector_rows) if point else False:
                self.store.select(actor)
                self.focused_child = ''
                node = self.store.nodes[actor]
                if node.unread:
                    try:
                        # ShellExecute reports failure if the URL handler is absent.
                        result = win.ctypes.windll.shell32.ShellExecuteW(None,'open','codex://threads/'+actor,None,None,1)
                        if result <= 32:
                            raise OSError('Codex URL handler unavailable')
                        node.unread = False
                        self.observer.opened.add(actor)
                    except OSError:
                        win.user32.MessageBoxW(self.hwnd,'无法打开 Codex 线程，请复制线程 ID：\n'+actor,'GooglePiggy',0)
            return
        if self.mouse_down and not self.dragging and self.leisure.click(time.monotonic()):
            self.mouse_down=False
            win.user32.ReleaseCapture()
            self._resolve_visual()
            return
        if self.mouse_down and not self.dragging and self.leisure.phase=='snacking':
            self.leisure.cancel()
        super()._handle_left_button_up()

    def _show_menu(self,owner_hwnd=None):
        owner = owner_hwnd or self.hwnd or self.tail_hwnd
        if not owner:
            return
        menu = win.user32.CreatePopupMenu()
        for command,label in [(100,'状态互动（Codex）'),(101,'休息模式'),(170,'正在检查更新…' if self.update_checker.checking else '检查更新…'),(150,'关闭开机自启动' if win.is_autostart_enabled() else '开启开机自启动'),(160,'Codex Hook 首次授权说明'),(199,'退出猪猪桌宠')]:
            flags = win.MF_STRING | (1 if command==101 and self.store.work_tokens() else 0)
            win.user32.AppendMenuW(menu,flags,command,label)
        cursor = win.POINT()
        win.user32.GetCursorPos(ctypes.byref(cursor))
        win.user32.SetForegroundWindow(owner)
        command = win.user32.TrackPopupMenu(menu,win.TPM_RETURNCMD|win.TPM_NONOTIFY|win.TPM_RIGHTBUTTON,cursor.x,cursor.y,0,owner,None)
        win.user32.DestroyMenu(menu)
        if command == 199:
            win.user32.DestroyWindow(self.hwnd)
            return
        if command == 101 and not self.store.work_tokens():
            self.transient_key=None
            self.leisure.enter(time.monotonic())
        elif command == 150:
            win.set_autostart(not win.is_autostart_enabled(),self.app_dir)
        elif command == 160:
            win.user32.MessageBoxW(owner,'首次安装后，请在 Codex /hooks 中审核并信任 GooglePiggy 的 Hook。桌宠不会修改信任数据库。\n权限请求只响应当前请求的允许／拒绝。','GooglePiggy',0)
        elif command == 170:
            if self.update_notice and self.update_notice.phase in {'downloading','verifying','ready','installing'}:
                self._fit_update_notice()
            else:
                self.update_checker.check(manual=True)
        elif command == 100:
            self.mode='responsive'
        self._restore_after_menu_dismissal()

    def _write_heartbeat(self,force=False):
        now = time.monotonic()
        if not force and now-self.last_heartbeat < 1:
            return
        self.last_heartbeat = now
        p = dict(app=win.APP_NAME,pid=os.getpid(),updated_at=win.utc_timestamp(),status_path=str(self.status_path),current_key=self.current_key,
            version=APP_VERSION,build=APP_BUILD,frame_index=self.frame_index,selected_family=self.store.selected,
            families=[{'id':n.id,'parent':n.parent,'turn':n.turn,'status':n.status,'unread':n.unread} for n in self.store.nodes.values()],
            leisure_phase=self.leisure.phase,selector_visible=self.selector_visible,hidden_work_tokens=sorted(self.hidden_tokens),unread_sync=self.observer.unread_supported,dpi_scale=self.scale,
            presentation=(self.edge_transition or 'hidden') if self.edge_placement else 'visible',
            tail_visible=bool(self.tail_hwnd and win.user32.IsWindowVisible(self.tail_hwnd)))
        p['update_phase'] = self.update_notice.phase if self.update_notice else None
        p['update_visible'] = bool(self.update_notice and not self.permission_request)
        p['update_checking'] = self.update_checker.checking
        if os.environ.get('GOOGLEPIGGY_QA_WINDOW') == '1' and not self.observer.enabled:
            p['qa_commands'] = sorted(self.qa_commands)
            p['permission_request_id'] = self.permission_request_id
        if self.hwnd:
            p.update(hwnd=int(self.hwnd),window_rect=self._window_rect(self.hwnd),window_visible=bool(win.user32.IsWindowVisible(self.hwnd)))
            content = self._screen_bounds_for_local(self._current_content_local_bounds())
            if content:
                p['content_screen_rect'] = content
                monitors = win.enumerate_monitor_infos()
                monitor = self.edge_placement.monitor if self.edge_placement else (
                    max(monitors,key=lambda m:win.rect_intersection_area(content,m.frame)) if monitors else None)
                if monitor:
                    p['monitor_work'] = monitor.work
        if self.tail_hwnd:
            p.update(tail_hwnd=int(self.tail_hwnd),tail_rect=self._window_rect(self.tail_hwnd))
        if self.edge_placement:
            p['hidden_edge'] = self.edge_placement.edge
        try:
            atomic_json(self.heartbeat_path,p)
        except OSError:
            pass

    def _wndproc(self,hwnd,message,wparam,lparam):
        if hwnd == self.hwnd and message == ANIMATION_MESSAGE:
            if self.animation_timer:
                # Sample the fixed deadline rather than OS delivery jitter.
                # Otherwise 19.9/20.1ms arrivals alternately repeat and skip
                # frames of a 20ms clip even when the average cadence is right.
                self.animation_sample_time = self.animation_timer.sample()
            try:
                self._advance()
            finally:
                self.animation_sample_time = None
                # Keep the one-notification latch set throughout rendering.
                # Posted messages precede input/WM_TIMER in GetMessage; if a
                # heavy frame queues its successor, input can starve forever.
                if self.animation_timer:
                    self.animation_timer.acknowledge()
            return 0
        if hwnd == self.hwnd and message == win.WM_DESTROY:
            self.observer.close()
            if self.animation_timer:
                self.animation_timer.close()
                self.animation_timer = None
        if hwnd==self.hwnd and message==0x020A: # WM_MOUSEWHEEL
            delta = ctypes.c_short((wparam>>16)&0xffff).value
            point = self._cursor_window_position()
            if self.permission_request and point and self._point_in_rect(point,self.permission_bubble_rect):
                self.permission_page=max(0,self.permission_page+(-3 if delta>0 else 3))
            elif self.selector_visible:
                self.selector_scroll=max(0,self.selector_scroll+(-1 if delta>0 else 1))
            return 0
        return super()._wndproc(hwnd,message,wparam,lparam)

    def _fit_update_notice(self):
        if not self.hwnd or self.dragging or self.edge_transition or self.hidden_family:
            return
        if self.edge_placement:
            self._begin_edge_reveal(False)
            return
        content = self._screen_bounds_for_local(self._current_content_local_bounds())
        rect = self._window_rect(self.hwnd)
        monitors = win.enumerate_monitor_infos()
        if content and rect and monitors:
            work = max(monitors,key=lambda m:win.rect_intersection_area(content,m.frame)).work
            dx = max(work[0]-content[0], min(0,work[2]-content[2]))
            dy = max(work[1]-content[1], min(0,work[3]-content[3]))
            if dx or dy:
                self._set_window_origin(self.hwnd,(rect[0]+dx,rect[1]+dy))

    def _update_action(self, action):
        notice = self.update_notice
        if not notice or action not in notice.buttons:
            return
        if action == 'dismiss':
            self.update_notice = None
        elif action == 'cancel':
            self.update_installer.cancel.set()
        elif action == 'update' and notice.release:
            notice.error = None
            notice.phase,notice.progress = 'downloading',0
            self.update_installer.start(notice.release)

    def _poll_update(self):
        if not self.update_startup_done:
            self.update_startup_done = True
            # Isolated test instances never contact GitHub or real account data.
            if self.observer.enabled:
                self.update_checker.check()
            enabled = win.wintypes.BOOL(True)
            if win.user32.SystemParametersInfoW(0x1042,0,ctypes.byref(enabled),0):
                self.reduced_motion = not bool(enabled.value)
        result = self.update_checker.poll()
        if result:
            release,error,manual = result
            if (release or manual) and not (self.update_notice and self.update_notice.phase in {'downloading','verifying','ready','installing'}):
                self.update_notice = UpdateNotice(release,error)
        while True:
            try:
                phase,value = self.update_installer.events.get_nowait()
            except queue.Empty:
                break
            if not self.update_notice:
                continue
            self.update_notice.phase = phase
            if phase == 'downloading': self.update_notice.progress = value
            elif phase == 'ready': self.update_package = value
            elif phase == 'error': self.update_notice.error = value
            elif phase == 'cancelled':
                self.update_notice.phase,self.update_notice.progress = 'available',None
        if self.update_package and not self.dragging and not self.mouse_down and not self.permission_actors:
            package,self.update_package = self.update_package,None
            self.update_notice.phase = 'installing'
            self.update_helper_started = time.monotonic()
            def prepare():
                try:
                    job = prepare_helper(self.app_dir,package,self.update_notice.release.version,self.status_path,not self.observer.enabled)
                    self.update_helper_events.put((job,None))
                except Exception as error:
                    self.update_helper_events.put((None,str(error)))
            threading.Thread(target=prepare,daemon=True).start()
        try:
            job,error = self.update_helper_events.get_nowait()
            if error:
                self.update_notice.phase,self.update_notice.error = 'error',error
            else:
                self.update_helper_job = job
                self.update_helper_started = time.monotonic()
        except queue.Empty:
            pass
        if self.update_helper_job:
            result = win.read_json_file(self.update_helper_job.with_name('install-result.json'))
            if result and not result.get('success'):
                self.update_notice.phase,self.update_notice.error = 'error',result.get('error','更新未完成')
                self.update_helper_job = None
            elif time.monotonic()-self.update_helper_started > 50:
                atomic_json(self.update_helper_job.with_name('abort.json'),{'abort':True})
                self.update_notice.phase,self.update_notice.error = 'error','等待安装超时，请重试'
                self.update_helper_job = None
            elif self.update_helper_job.with_name('helper-ready.json').exists() and not self.dragging and not self.mouse_down and not self.permission_actors:
                win.user32.DestroyWindow(self.hwnd)
                return
        if self.update_notice and not self.permission_request:
            self._fit_update_notice()
