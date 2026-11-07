"""进程内 TTL 缓存：热点问题不重复检索，文档变更后由调用方清空。"""

import time


class TTLCache:
    def __init__(self, ttl=300, maxsize=256):
        self.ttl = ttl
        self.maxsize = maxsize
        self._data = {}

    def get(self, key):
        item = self._data.get(key)
        if not item:
            return None
        value, expire = item
        if expire < time.time():
            self._data.pop(key, None)
            return None
        return value

    def set(self, key, value):
        if len(self._data) >= self.maxsize:
            # 简单淘汰：清掉过期项，仍然满就丢最早插入的一个
            now = time.time()
            self._data = {k: v for k, v in self._data.items() if v[1] >= now}
            if len(self._data) >= self.maxsize:
                self._data.pop(next(iter(self._data)))
        self._data[key] = (value, time.time() + self.ttl)

    def clear(self):
        self._data.clear()
