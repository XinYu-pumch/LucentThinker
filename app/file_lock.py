"""Process-owned shared/exclusive locks, released when the file handle closes."""
import os

if os.name == 'nt':
    import ctypes
    from ctypes import wintypes
    import msvcrt

    class Overlapped(ctypes.Structure):
        _fields_ = [('Internal', ctypes.c_size_t), ('InternalHigh', ctypes.c_size_t),
                    ('Offset', wintypes.DWORD), ('OffsetHigh', wintypes.DWORD),
                    ('hEvent', wintypes.HANDLE)]

    kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel32.LockFileEx.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD,
                                   wintypes.DWORD, wintypes.DWORD, ctypes.POINTER(Overlapped)]
    kernel32.LockFileEx.restype = wintypes.BOOL
else:
    import fcntl


def acquire(file, *, exclusive=False, blocking=True):
    """Lock byte zero, including empty files. Keep the file open while using it."""
    if os.name != 'nt':
        flags = fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH
        if not blocking:
            flags |= fcntl.LOCK_NB
        fcntl.flock(file, flags)
        return
    flags = (2 if exclusive else 0) | (0 if blocking else 1)
    overlap = Overlapped()
    handle = msvcrt.get_osfhandle(file.fileno())
    if not kernel32.LockFileEx(handle, flags, 0, 1, 0, ctypes.byref(overlap)):
        error = ctypes.get_last_error()
        if error == 33:  # ERROR_LOCK_VIOLATION
            raise BlockingIOError(error, 'File is locked by another process')
        raise ctypes.WinError(error)
