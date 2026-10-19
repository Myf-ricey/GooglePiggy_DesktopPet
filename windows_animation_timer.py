"""Fixed-deadline 20ms UI notifications; no global timer-resolution changes."""
import ctypes
from ctypes import wintypes
import threading
import time

ANIMATION_MESSAGE = 0x8000 + 73


class WindowAnimationTimer:
    def __init__(self, hwnd, period=.020):
        self.hwnd, self.period = hwnd, period
        self.pending = False
        self.sample_time = None
        self.lock = threading.Lock()
        self.kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        self.user = ctypes.WinDLL('user32', use_last_error=True)
        self.kernel.CreateWaitableTimerExW.argtypes = [ctypes.c_void_p,wintypes.LPCWSTR,wintypes.DWORD,wintypes.DWORD]
        self.kernel.CreateWaitableTimerExW.restype = wintypes.HANDLE
        self.kernel.CreateEventW.argtypes = [ctypes.c_void_p,wintypes.BOOL,wintypes.BOOL,wintypes.LPCWSTR]
        self.kernel.CreateEventW.restype = wintypes.HANDLE
        self.kernel.SetWaitableTimer.argtypes = [wintypes.HANDLE,ctypes.POINTER(ctypes.c_longlong),wintypes.LONG,ctypes.c_void_p,ctypes.c_void_p,wintypes.BOOL]
        self.kernel.WaitForMultipleObjects.argtypes = [wintypes.DWORD,ctypes.POINTER(wintypes.HANDLE),wintypes.BOOL,wintypes.DWORD]
        self.kernel.SetEvent.argtypes = [wintypes.HANDLE]
        self.kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        self.kernel.CancelWaitableTimer.argtypes = [wintypes.HANDLE]
        self.user.PostMessageW.argtypes = [wintypes.HWND,wintypes.UINT,wintypes.WPARAM,wintypes.LPARAM]
        # CREATE_WAITABLE_TIMER_HIGH_RESOLUTION (Windows 10 1803+).
        self.timer = self.kernel.CreateWaitableTimerExW(None,None,2,0x1F0003)
        self.stop = self.kernel.CreateEventW(None,True,False,None)
        if not self.timer or not self.stop:
            if self.timer: self.kernel.CloseHandle(self.timer)
            if self.stop: self.kernel.CloseHandle(self.stop)
            raise ctypes.WinError(ctypes.get_last_error())
        self.thread = threading.Thread(target=self._run,name='pig-animation-clock',daemon=True)
        self.thread.start()

    def acknowledge(self):
        with self.lock:
            self.pending = False
            return self.sample_time

    def sample(self):
        with self.lock:
            return self.sample_time

    def _run(self):
        handles = (wintypes.HANDLE*2)(self.stop,self.timer)
        origin, tick = time.monotonic(),1
        try:
            while True:
                deadline = origin+tick*self.period
                due = ctypes.c_longlong(-max(1,round((deadline-time.monotonic())*10_000_000)))
                if not self.kernel.SetWaitableTimer(self.timer,ctypes.byref(due),0,None,None,False):
                    return
                if self.kernel.WaitForMultipleObjects(2,handles,False,0xFFFFFFFF) != 1:
                    return
                with self.lock:
                    self.sample_time = deadline
                    if not self.pending:
                        self.pending = bool(self.user.PostMessageW(self.hwnd,ANIMATION_MESSAGE,0,0))
                now = time.monotonic()
                # Skip expired deadlines instead of enqueuing catch-up frames.
                tick = max(tick+1,int((now-origin)//self.period)+1)
        finally:
            self.kernel.CancelWaitableTimer(self.timer)

    def close(self):
        if self.stop:
            self.kernel.SetEvent(self.stop)
            self.thread.join()
            self.kernel.CloseHandle(self.stop)
            self.kernel.CloseHandle(self.timer)
            self.stop = self.timer = None
