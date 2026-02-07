# storage/seen_store.py
import os


class SeenStore:
    def __init__(self, filepath: str):
        self.filepath = filepath
        self._seen = self._load()

    def _load(self) -> set[str]:
        if not os.path.exists(self.filepath):
            return set()
        with open(self.filepath, "r", encoding="utf-8") as f:
            return {line.strip() for line in f if line.strip()}

    def has(self, pid: str) -> bool:
        return pid in self._seen

    def add(self, pid: str) -> None:
        if pid in self._seen:
            return
        self._seen.add(pid)
        with open(self.filepath, "a", encoding="utf-8") as f:
            f.write(pid + "\n")
