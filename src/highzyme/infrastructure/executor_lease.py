"""One cooperating executor per local SQLite database, released by the OS on exit."""
from pathlib import Path
import os


class ExecutorLease:
    def __init__(self, database):
        self.path = Path(str(Path(database).resolve()) + '.executor.lock')
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._file = self.path.open('a+b')
        self._file.seek(0, os.SEEK_END)
        if self._file.tell() == 0:
            self._file.write(b'0'); self._file.flush()
        self._file.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(self._file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self._file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self._file.close(); self._file = None
            raise RuntimeError('Another Highzyme executor already owns this task database') from None

    def close(self):
        if self._file is None: return
        try:
            self._file.seek(0)
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(self._file.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(self._file.fileno(), fcntl.LOCK_UN)
        finally:
            self._file.close(); self._file = None
