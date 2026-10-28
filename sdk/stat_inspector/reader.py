"""Reads final values, base values and the live modifier stack for catalog stats.

Value/base come from the game (`AttributeDefinition.GetValue/GetBaseValue`, which return
`(value, resolved_context)`). The modifier stack is the `<PropertyName>ModifierStack` array on the
resolved context, where PropertyName comes from the attribute's ObjectPropertyAttributeValueResolver.
"""
import math
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from . import sdk, sources, stats

MOD_SCALE, MOD_PREADD, MOD_POSTADD = 0, 1, 2

_attributes = sdk.ObjectCache()       # path -> AttributeDefinition, safe across character changes
_stack_props: Dict[str, Optional[str]] = {}  # path -> "<Property>ModifierStack" (None if unknown)


@dataclass
class Contribution:
    source: str
    mod_type: int
    value: float
    count: int = 1  # stacked effects add one modifier per stack; they are merged into one row


@dataclass
class Reading:
    stat: stats.StatDef
    value: float
    base: float
    contributions: List[Contribution] = field(default_factory=list)
    # Value predicted from base + contributions; differs from `value` if something is unexplained
    predicted: Optional[float] = None
    # Timers only: world time (WorldInfo.TimeSeconds) the effect ends at; value is recomputed per frame
    ends_at: Optional[float] = None


def _attribute(path: str) -> Any:
    attr = _attributes.get("Object", path)
    if attr is None:
        sources.log_error_once(path, "attribute not found: " + path)
    return attr


def _stack_property(path: str, attr: Any) -> Optional[str]:
    if path not in _stack_props:
        prop = None
        try:
            for resolver in attr.ValueResolverChain:
                name = sdk.name_text(getattr(resolver, "PropertyName", None))
                if name:
                    prop = name + "ModifierStack"
                    break
        except Exception as ex:
            sources.log_error_once("resolver " + path, "no value resolver for %s: %s" % (path, ex))
        _stack_props[path] = prop
    return _stack_props[path]


def predict(base: float, contributions: List[Contribution]) -> float:
    pre = sum(c.value for c in contributions if c.mod_type == MOD_PREADD)
    post = sum(c.value for c in contributions if c.mod_type == MOD_POSTADD)
    pos = sum(c.value for c in contributions if c.mod_type == MOD_SCALE and c.value > 0)
    neg = sum(-c.value for c in contributions if c.mod_type == MOD_SCALE and c.value < 0)
    return (base + pre) * (1 + pos) / (1 + neg) + post


def class_cooldown(pc: Any) -> Optional[Tuple[Union[str, float], str]]:
    """(base cooldown attribute or constant, rate attribute) for the player's class."""
    try:
        class_path = sdk.path_name(pc.PlayerClass)
    except Exception:
        return None
    for keyword, base, rate in stats.CLASS_COOLDOWNS:
        if keyword in class_path:
            return base, rate
    return None


def attribute_path(pc: Any, stat: stats.StatDef) -> Optional[str]:
    """The attribute to read for a stat; the action skill cooldown depends on the player class
    (None when its base is a constant, as for Krieg)."""
    if stat.attribute != stats.ACTION_SKILL_COOLDOWN:
        return stat.attribute
    cooldown = class_cooldown(pc)
    return cooldown[0] if cooldown is not None and isinstance(cooldown[0], str) else None


def _read(pc: Any, path: str) -> Optional[Tuple[Any, float, Any, float]]:
    """(attribute, value, resolved context, base) or None when unavailable."""
    attr = _attribute(path)
    if attr is None:
        return None
    try:
        value, context = sdk.get_value(attr, pc)
        base = sdk.get_base_value(attr, pc)
    except Exception as ex:
        sources.log_error_once("value " + path, "GetValue failed for %s: %s" % (path, ex))
        return None
    if context is None:
        return None  # e.g. no grenade mod equipped
    return attr, value, context, base


def _divided(pc: Any, stat: stats.StatDef, value: float, base: float, divisor_path: str,
             index: Optional[sources.SourceIndex]) -> Optional[Reading]:
    """Derived stat value / divisor attribute, e.g. base cooldown 13 s / cooldown rate 1.67 = 7.8 s.
    The sources are the divisor's modifiers; no formula check (not a single attribute)."""
    divisor = _read(pc, divisor_path)
    if divisor is None or divisor[1] <= 0:
        return None  # e.g. the cooldown rate is 0 while the action skill runs
    div_attr, div_value, div_context, div_base = divisor
    reading = Reading(stat, value / div_value, base / div_base if div_base > 0 else base)
    if index is not None:
        reading.contributions = _contributions(divisor_path, div_attr, div_context, index) or []
    return reading


def read_stat(pc: Any, stat: stats.StatDef, index: Optional[sources.SourceIndex]) -> Optional[Reading]:
    if stat.attribute == stats.ACTION_SKILL_COOLDOWN:
        cooldown = class_cooldown(pc)
        if cooldown is None:
            return None
        base_source, rate_path = cooldown
        if isinstance(base_source, str):
            read = _read(pc, base_source)
            if read is None:
                return None
            value, base = read[1], read[3]
        else:
            value = base = float(base_source)
        return _divided(pc, stat, value, base, rate_path, index)

    path = stat.attribute
    sources.trace("stat %s" % path)
    read = _read(pc, path)
    if read is None:
        return None
    attr, value, context, base = read
    if stat.divisor:
        return _divided(pc, stat, value, base, stat.divisor, index)

    reading = Reading(stat, value, base)
    if index is None:
        return reading
    contributions = _contributions(path, attr, context, index)
    if contributions is None:
        return reading
    reading.contributions = contributions
    reading.predicted = predict(base, reading.contributions)
    if stat.kind == stats.INT:
        # Integer attributes are truncated by the game (14 x 1.2 = 16.8 -> 16, probe run 4)
        reading.predicted = math.floor(reading.predicted + 1e-4)
    return reading


def _contributions(path: str, attr: Any, context: Any, index: sources.SourceIndex) -> Optional[List[Contribution]]:
    """Merged live modifiers of an attribute, or None when its stack can't be read."""
    prop = _stack_property(path, attr)
    if prop is None:
        return None
    try:
        sources.trace("  stack %s.%s" % (sdk.path_name(context), prop))
        try:
            stack = sdk.get_property(context, prop)
        except AttributeError:
            # The resolved context has no such stack: its sources are invisible to us, so skip
            # the formula check instead of reporting everything as unexplained
            sources.log_error_once("noprop " + path, "no %s on %s (%s)" % (
                prop, sdk.class_name(context), path))
            return None
        sources.trace("  stack size %d" % len(stack or ()))
        # Sign is part of the key: positive and negative Scale modifiers combine differently
        merged: Dict[Tuple[str, int, bool], Contribution] = {}
        for i, modifier in enumerate(stack or ()):
            sources.trace("  mod %d" % i)
            if modifier is None:
                continue
            mod_value = modifier.Value
            mod_type = sdk.enum_int(modifier.Type)
            sources.trace("    value %r type %d" % (mod_value, mod_type))
            if mod_value == 0:
                continue
            key = (index.label(modifier, path), mod_type, mod_value > 0)
            if key in merged:
                merged[key].value += mod_value
                merged[key].count += 1
            else:
                merged[key] = Contribution(key[0], key[1], mod_value)
        return list(merged.values())
    except Exception as ex:
        sources.log_error_once("stack " + path, "stack read failed for %s: %s" % (path, ex))
        return None


def stat_key(stat: stats.StatDef) -> str:
    """Settings key of a stat; group + label is unique even if an attribute appears twice."""
    return stat.group + "/" + stat.label


# The source index (2.5 ms to build) only changes with the equipment, so it is reused across
# refreshes until the equipment signature changes; rebuilt anyway after INDEX_MAX_AGE seconds so
# lazily cached skill labels can't go stale for long
INDEX_MAX_AGE = 10.0
_index: Optional[sources.SourceIndex] = None
_index_signature: Optional[Tuple] = None
_index_built = 0.0


def source_index(pc: Any) -> sources.SourceIndex:
    global _index, _index_signature, _index_built
    signature = sources.equipment_signature(pc)
    now = time.monotonic()
    if _index is None or signature != _index_signature or now - _index_built > INDEX_MAX_AGE:
        _index = sources.SourceIndex(pc)
        _index_signature = signature
        _index_built = now
    return _index


class Refresh:
    """One refresh cycle, spread over frames by a per-frame time budget.

    Reading every stat with sources in one frame took 10-12 ms (all 145 stats) - a visible hitch
    every refresh. `step()` reads stats until the budget is spent and resumes on the next frame;
    nothing engine-side is kept between frames (SourceIndex holds only strings, stats are
    re-resolved through the live PC each time).
    """

    def __init__(self, with_sources: bool, enabled: Optional[Set[str]] = None, timers: bool = False) -> None:
        self.with_sources = with_sources
        self.timers = timers
        self.stats = [s for s in stats.CATALOG if enabled is None or stat_key(s) in enabled]
        self.position = 0
        self.index: Optional[sources.SourceIndex] = None
        self.readings: List[Reading] = []
        self.started = False

    def step(self, pc: Any, budget: Optional[float] = None) -> bool:
        """Advances the cycle; True once every stat was read (results in `readings`)."""
        start = time.perf_counter()
        if not self.started:
            self.started = True
            sources.trace_begin()
            sources.trace("refresh with_sources=%s" % self.with_sources)
            if self.with_sources:
                try:
                    self.index = source_index(pc)
                except Exception as ex:
                    sources.log_error_once("index", "source index failed: %s" % ex)
            if budget is not None and time.perf_counter() - start >= budget:
                return False
        while self.position < len(self.stats):
            stat = self.stats[self.position]
            self.position += 1  # advance first: a stat that raises is skipped, never retried forever
            try:
                reading = read_stat(pc, stat, self.index)
            except Exception as ex:
                sources.log_error_once("read " + stat.attribute, "reading %s failed: %r" % (stat.label, ex))
                reading = None
            if reading is not None:
                self.readings.append(reading)
            if budget is not None and time.perf_counter() - start >= budget:
                return self.position >= len(self.stats) and self._finish(pc)
        return self._finish(pc)

    def _finish(self, pc: Any) -> bool:
        if self.timers:
            try:
                self.readings = self.readings + read_timers(pc, self.index)  # Timers go last
            except Exception as ex:
                sources.log_error_once("timers", "timers failed: %s" % ex)
        sources.trace("refresh done")
        return True


def read_all(pc: Any, with_sources: bool, enabled: Optional[Set[str]] = None) -> List[Reading]:
    """Reads catalog stats in one go; `enabled` (stat keys) skips stats switched off in settings."""
    refresh = Refresh(with_sources, enabled)
    refresh.step(pc)
    return refresh.readings


# ---- timers -----------------------------------------------------------------

COOLDOWN_LEFT = "D_Attributes.ActiveSkillCooldownResource.ActiveSkillCooldownCurrentValue"
DURATION_TYPE_TIMED = 1  # SkillDefinition.DurationType for skills that run out (Phaselock, Cloud Kill, ...)


def world_time(pc: Any) -> float:
    return float(pc.WorldInfo.TimeSeconds)


def _timer(label: str, total: float, ends_at: float, now: float) -> Reading:
    stat = stats.StatDef(stats.TIMERS_GROUP, label, "", stats.TIMER)
    return Reading(stat, ends_at - now, total, ends_at=ends_at)


def read_timers(pc: Any, index: Optional[sources.SourceIndex]) -> List[Reading]:
    """Running action skill cooldown and every active timed skill, as end times.

    Skills: remaining = StartTime + Duration - WorldInfo.TimeSeconds (Duration is the live
    attribute value, so duration buffs count). Cooldown: the pool's CurrentValue counts down in
    base seconds at the cooldown rate, so real seconds left = CurrentValue / rate.
    """
    now = world_time(pc)
    timers: List[Reading] = []
    left = _read(pc, COOLDOWN_LEFT)
    cooldown = class_cooldown(pc)
    rate = _read(pc, cooldown[1] if cooldown is not None else stats.COOLDOWN_RATE)
    if left is not None and left[1] > 0.05 and rate is not None and rate[1] > 0:
        seconds = left[1] / rate[1]
        timers.append(_timer("Action skill cooldown", seconds, now + seconds, now))
    labels = index if index is not None else sources.SourceIndex(pc, items=False)
    action_duration = _action_skill_duration(pc)
    for skill in pc.GetSkillManager().ActiveSkills:
        definition = skill.Definition if skill is not None else None
        if definition is None or sdk.enum_int(definition.DurationType) != DURATION_TYPE_TIMED:
            continue
        duration = float(skill.Duration)
        if action_duration is not None and sdk.enum_int(definition.SkillType) == stats.ACTION_SKILL_TYPE:
            # Phaselock's Skill outlives the lift (120 s); its class attribute holds the real time
            duration = min(duration, action_duration)
        ends_at = float(skill.StartTime) + duration
        if duration > 0 and ends_at > now:
            timers.append(_timer(labels.skill_label(skill), duration, ends_at, now))
    return timers


def _action_skill_duration(pc: Any) -> Optional[float]:
    """Real action skill duration when the class needs an override (Att_Phaselock_Duration, which
    Suspension extends); None means the Skill's own Duration is right (all other classes)."""
    try:
        class_path = sdk.path_name(pc.PlayerClass)
    except Exception:
        return None
    for keyword, path in stats.CLASS_ACTION_SKILL_DURATIONS:
        if keyword in class_path:
            read = _read(pc, path)
            return read[1] if read is not None and read[1] > 0 else None
    return None


def update_timers(readings: List[Reading], now: float) -> List[Reading]:
    """Per-frame countdown: recomputes timer values and drops the ones that ran out."""
    result = []
    for reading in readings:
        if reading.ends_at is None:
            result.append(reading)
        elif reading.ends_at > now:
            reading.value = reading.ends_at - now
            result.append(reading)
    return result
