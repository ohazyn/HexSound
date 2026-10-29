import random

class PlayQueue:
    """fila de reprodução; o shuffle é uma permutação"""
    def __init__(self, rng=None):
        self.items, self.order, self.pos = [], [], -1
        self.shuffle, self.repeat = False, "off"  # off | one | all
        self.history, self.rng = [], rng or random.Random()

    @property
    def current(self):
        return self.items[self.order[self.pos]] if 0 <= self.pos < len(self.order) else None

    def _build_order(self, cur_idx):
        n = len(self.items)
        if self.shuffle:
            rest = [i for i in range(n) if i != cur_idx]
            self.rng.shuffle(rest)
            self.order = ([cur_idx] if cur_idx is not None else []) + rest
            self.pos = 0 if n else -1
        else:
            self.order = list(range(n))
            self.pos = cur_idx if cur_idx is not None else (0 if n else -1)

    def set_tracks(self, ids, start=0):
        self.items = list(ids)
        self._build_order(start if ids else None)

    def set_shuffle(self, on):
        cur = self.order[self.pos] if self.pos >= 0 else None
        self.shuffle = on
        self._build_order(cur)

    def next(self, auto=False):
        if not self.items:
            return None
        if auto and self.repeat == "one":
            return self.current
        if self.pos + 1 < len(self.order):
            self.pos += 1
        elif self.repeat == "all":
            self._build_order(None)
            self.pos = 0
        else:
            return None
        self.history.append(self.current)
        return self.current

    def previous(self):
        if not self.items:
            return None
        if self.pos > 0:
            self.pos -= 1
        elif self.repeat == "all":
            self.pos = len(self.order) - 1
        return self.current

    def play_next(self, tid):
        ins = (self.order[self.pos] + 1) if self.pos >= 0 else 0
        self.items.insert(ins, tid)
        self.order = [i + 1 if i >= ins else i for i in self.order]
        self.order.insert(self.pos + 1, ins)

    def add_end(self, tid):
        self.items.append(tid)
        idx = len(self.items) - 1
        at = self.rng.randint(self.pos + 1, len(self.order)) if self.shuffle else len(self.order)
        self.order.insert(at, idx)

    def remove(self, qpos):
        idx = self.order.pop(qpos)
        self.items.pop(idx)
        self.order = [i - 1 if i > idx else i for i in self.order]
        if qpos < self.pos:
            self.pos -= 1
        elif qpos == self.pos:
            self.pos = min(self.pos, len(self.order) - 1)

    def jump(self, qpos):
        if 0 <= qpos < len(self.order):
            self.pos = qpos
            self.history.append(self.current)
        return self.current

    def upcoming(self):
        return [self.items[i] for i in self.order[self.pos + 1:]]
