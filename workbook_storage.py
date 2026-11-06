"""Serialized workbook updates, validated atomic replacement and rolling backups."""
from contextlib import contextmanager
from functools import wraps
from datetime import datetime, timezone
from pathlib import Path
import os
import shutil
import tempfile
import threading
from openpyxl import load_workbook

_locks = {}
_guard = threading.Lock()

@contextmanager
def workbook_lock(path):
    path = Path(path).resolve()
    with _guard:
        lock = _locks.setdefault(path, threading.RLock())
    with lock:
        with open(str(path) + '.lock', 'a+b') as handle:
            if os.name == 'nt':
                import msvcrt
                handle.seek(0)
                if not handle.read(1):
                    handle.write(b'0'); handle.flush()
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
            else:
                import fcntl
                fcntl.flock(handle, fcntl.LOCK_EX)
            try:
                yield
            finally:
                if os.name == 'nt':
                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(handle, fcntl.LOCK_UN)

def serialized_update(function):
    @wraps(function)
    def update(path, *args, **kwargs):
        with workbook_lock(path):
            return function(path, *args, **kwargs)
    return update

def atomic_save(workbook, path):
    path = Path(path)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, suffix='.xlsx', delete=False) as file:
            temporary = Path(file.name)
        workbook.save(temporary)
        check = load_workbook(temporary, read_only=True)
        check.close()
        backup_dir = path.parent / 'backups'
        backup_dir.mkdir(exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S_%f')
        if path.exists():
            shutil.copy2(path, backup_dir / f'{path.stem}_{stamp}.xlsx')
        os.replace(temporary, path)
        for old in sorted(backup_dir.glob(f'{path.stem}_*.xlsx'), reverse=True)[30:]:
            old.unlink(missing_ok=True)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
