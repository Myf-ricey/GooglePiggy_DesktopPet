"""Idle routines with injectable monotonic time and randomness."""
import math
import random


class Leisure:
    def __init__(self, now, rng=None):
        self.rng = rng or random.Random()
        self.reset(now)

    def interval(self):
        while True:
            u = max(1e-12, min(1-1e-12, self.rng.random()))
            minutes = 10 + 2.965 * math.sqrt(-2*math.log(u))*math.cos(2*math.pi*self.rng.random())
            if 3 <= minutes <= 30:
                return minutes*60

    def reset(self, now, interval=None, choice=None):
        duration = self.interval() if interval is None else interval
        choice = self.rng.random() if choice is None else choice
        fractions = [2/3] if choice < .4 else [1/3] if choice < .8 else [1/3,2/3] if choice < .9 else []
        self.phase, self.began, self.deadline = 'awake', now, now+duration
        self.snacks = [now+duration*f for f in fractions]
        self.sleep_epoch, self.tail_epoch, self.action_epoch = 0, None, now

    def tick(self, now, eligible):
        if self.phase != 'awake':
            return
        due = any(t <= now for t in self.snacks)
        self.snacks = [t for t in self.snacks if t > now]
        if eligible:
            if now >= self.deadline:
                self.enter(now)
            elif due:
                self.phase, self.action_epoch = 'snacking', now

    def enter(self, now):
        self.phase, self.action_epoch, self.tail_epoch, self.snacks = 'entering', now, None, []

    def cancel(self):
        self.phase, self.tail_epoch = 'awake', None

    def click(self, now, wake=None):
        if self.phase not in ('entering','sleeping'):
            return False
        if wake is None:
            wake = self.rng.random() < .5
        if wake:
            self.phase, self.action_epoch, self.tail_epoch = 'waking', now, None
        elif self.phase == 'sleeping' and (self.tail_epoch is None or now-self.tail_epoch >= 1.44):
            self.tail_epoch = now
        return True

    def position(self, clips, now):
        elapsed = now-self.action_epoch
        if self.phase == 'snacking':
            if elapsed >= clips['snack'].total_duration/1000:
                self.phase = 'awake'
            else:
                return 'snack', clips['snack'].frame(elapsed, True)
        if self.phase == 'entering':
            duration = clips['sleep_entry'].total_duration/1000
            if elapsed >= duration:
                self.phase, self.sleep_epoch = 'sleeping', self.action_epoch+duration
            else:
                return 'sleep_entry', clips['sleep_entry'].frame(elapsed, True)
        if self.phase == 'sleeping':
            return 'sleep_body', clips['sleep_body'].frame(now-self.sleep_epoch)
        if self.phase == 'waking':
            if elapsed >= 2*clips['left'].total_duration/1000:
                self.reset(now)
            else:
                return 'left', clips['left'].frame(elapsed)
        return None
