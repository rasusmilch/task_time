"""Process-lifetime local dataset ownership, not lock-file existence."""

import os
from pathlib import Path


class DatasetLock:
    def __init__(self, directory: Path):
        self.path = directory / ".chronicle.lock"
        self.file = None

    def acquire(self) -> None:
        self.file = self.path.open("a+b")
        try:
            if os.name == "nt":
                import msvcrt
                self.file.seek(0)
                if not self.file.read(1):
                    self.file.write(b"\0")
                    self.file.flush()
                self.file.seek(0)
                msvcrt.locking(self.file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BaseException:
            self.file.close()
            self.file = None
            raise

    def close(self) -> None:
        if self.file is not None:
            self.file.close()  # OS releases the lock, including after process death.
            self.file = None
