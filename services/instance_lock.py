from __future__ import annotations

from pathlib import Path


class InstanceLockError(RuntimeError):
    pass


class InstanceLock:
    def __init__(self, lock_path: Path) -> None:
        self.lock_path = lock_path
        self._file = None
        self._locked = False

    def acquire(self) -> None:
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        self._file = self.lock_path.open("a+b")

        try:
            try:
                import msvcrt  # type: ignore

                msvcrt.locking(self._file.fileno(), msvcrt.LK_NBLCK, 1)
            except ImportError:
                import fcntl  # type: ignore

                fcntl.flock(self._file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            self._file.close()
            self._file = None
            raise InstanceLockError("이미 또봇이 실행 중입니다.") from error

        self._locked = True
        self._file.seek(0)
        self._file.truncate()
        self._file.write(str(self.lock_path).encode("utf-8", errors="ignore"))
        self._file.flush()

    def release(self) -> None:
        if self._file is None:
            return

        try:
            if self._locked:
                try:
                    import msvcrt  # type: ignore

                    self._file.seek(0)
                    msvcrt.locking(self._file.fileno(), msvcrt.LK_UNLCK, 1)
                except ImportError:
                    import fcntl  # type: ignore

                    fcntl.flock(self._file.fileno(), fcntl.LOCK_UN)
                except OSError:
                    pass
        finally:
            self._file.close()
            self._file = None
            self._locked = False
