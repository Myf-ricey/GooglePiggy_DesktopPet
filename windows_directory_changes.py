"""Nonblocking Windows file-name hints for one directory."""
import ctypes
from ctypes import wintypes
import struct


class Overlapped(ctypes.Structure):
    _fields_ = [
        ('internal', ctypes.c_size_t),
        ('internal_high', ctypes.c_size_t),
        ('offset', wintypes.DWORD),
        ('offset_high', wintypes.DWORD),
        ('event', wintypes.HANDLE),
    ]


FILE_LIST_DIRECTORY = 0x0001
FILE_SHARE_ALL = 0x0007  # Read, write, and delete.
OPEN_EXISTING = 3
DIRECTORY_OVERLAPPED = 0x42000000  # BACKUP_SEMANTICS | OVERLAPPED
CHANGE_FILTER = 0x0019  # File name, size, and last write.
ERROR_IO_INCOMPLETE = 996
ERROR_NOTIFY_ENUM_DIR = 1022
FILE_CONTENT_AVAILABLE = {1, 3, 5}  # Added, modified, renamed to this name.
NOTIFY_HEADER = struct.Struct('<III')


class WindowsDirectoryChanges:
    """The caller owns the handle and polls for completed reads on one thread."""

    def __init__(self, directory):
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        handle, dword = wintypes.HANDLE, wintypes.DWORD
        overlap = ctypes.POINTER(Overlapped)
        kernel.CreateFileW.argtypes = [
            wintypes.LPCWSTR, dword, dword, ctypes.c_void_p, dword, dword, handle,
        ]
        kernel.CreateFileW.restype = handle
        kernel.CreateEventW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.BOOL, wintypes.LPCWSTR]
        kernel.CreateEventW.restype = handle
        kernel.ReadDirectoryChangesW.argtypes = [
            handle, ctypes.c_void_p, dword, wintypes.BOOL, dword, ctypes.POINTER(dword),
            overlap, ctypes.c_void_p,
        ]
        kernel.GetOverlappedResult.argtypes = [handle, overlap, ctypes.POINTER(dword), wintypes.BOOL]
        kernel.ResetEvent.argtypes = [handle]
        kernel.CancelIoEx.argtypes = [handle, overlap]
        kernel.CloseHandle.argtypes = [handle]
        self.kernel = kernel
        # The DWORD array aligns the buffer and stays alive until cancellation completes.
        self.buffer = (dword * (64 * 1024 // ctypes.sizeof(dword)))()
        self.overlapped = Overlapped()
        self.pending = False
        self.directory = kernel.CreateFileW(
            str(directory), FILE_LIST_DIRECTORY, FILE_SHARE_ALL, None, OPEN_EXISTING,
            DIRECTORY_OVERLAPPED, None,
        )
        if self.directory == ctypes.c_void_p(-1).value:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            self.overlapped.event = kernel.CreateEventW(None, True, False, None)
            if not self.overlapped.event:
                raise ctypes.WinError(ctypes.get_last_error())
            self._arm()
        except OSError:
            self.close()
            raise

    def _arm(self):
        event = self.overlapped.event
        if not self.kernel.ResetEvent(event):
            raise ctypes.WinError(ctypes.get_last_error())
        self.overlapped = Overlapped(event=event)
        if not self.kernel.ReadDirectoryChangesW(
            self.directory, self.buffer, ctypes.sizeof(self.buffer), False, CHANGE_FILTER,
            None, ctypes.byref(self.overlapped), None,
        ):
            raise ctypes.WinError(ctypes.get_last_error())
        self.pending = True

    def read(self):
        """Return changed names, or None when the caller must enumerate the directory."""
        names = set()
        size = wintypes.DWORD()
        for _ in range(8):
            if not self.kernel.GetOverlappedResult(
                self.directory, ctypes.byref(self.overlapped), ctypes.byref(size), False,
            ):
                error = ctypes.get_last_error()
                if error == ERROR_IO_INCOMPLETE:
                    return names
                self.pending = False
                if error != ERROR_NOTIFY_ENUM_DIR:
                    raise ctypes.WinError(error)
                self._arm()
                return None
            self.pending = False
            data = ctypes.string_at(self.buffer, size.value)
            self._arm()
            if not data:
                return None  # Windows dropped notifications after buffer overflow.
            offset = 0
            while offset + NOTIFY_HEADER.size <= len(data):
                step, action, length = NOTIFY_HEADER.unpack_from(data, offset)
                start = offset + NOTIFY_HEADER.size
                if length % 2 or start + length > len(data):
                    return None
                if action in FILE_CONTENT_AVAILABLE:
                    names.add(data[start:start + length].decode('utf-16-le', errors='surrogatepass'))
                if not step:
                    break
                if step < NOTIFY_HEADER.size + length or offset + step >= len(data):
                    return None
                offset += step
        # An active burst should neither monopolize the reader nor delay a full scan.
        return None

    def close(self):
        if self.pending:
            overlap = ctypes.byref(self.overlapped)
            self.kernel.CancelIoEx(self.directory, overlap)
            # The cancellation request may finish asynchronously. Keep the buffer
            # and OVERLAPPED alive until the kernel completes the read.
            self.kernel.GetOverlappedResult(
                self.directory, overlap, ctypes.byref(wintypes.DWORD()), True,
            )
            self.pending = False
        if self.overlapped.event:
            self.kernel.CloseHandle(self.overlapped.event)
            self.overlapped.event = None
        if self.directory:
            self.kernel.CloseHandle(self.directory)
            self.directory = None
