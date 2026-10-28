"""Stat Inspector: shows the player's final stat values as computed by the game, and the buffs
behind them. Native port for willow2-mod-manager v3.8 (mods_base 1.12).

Name, author, version and description come from pyproject.toml (read by build_mod).
"""
import time
from typing import Any, Dict, List, Optional, Set

from mods_base import BoolOption, HiddenOption, NestedOption, SliderOption, build_mod, get_pc, hook, keybind
from unrealsdk.unreal import BoundFunction, UObject, WrappedStruct

from . import overlay, reader, sources, stats

MODE_OFF, MODE_VALUES, MODE_SOURCES = 0, 1, 2
MODE_NAMES = {MODE_OFF: "off", MODE_VALUES: "values", MODE_SOURCES: "values + sources"}
TOAST_SECONDS = 2.0

_readings: List[reader.Reading] = []
_refresh: Optional[reader.Refresh] = None
_next_refresh = 0.0
_toast_text = ""
_toast_until = 0.0


def _force_refresh(*_: Any) -> None:
    """Option change callback (option, new value): restart reading on the next frame."""
    global _next_refresh, _refresh
    _next_refresh = 0.0
    _refresh = None


# ---- options ----------------------------------------------------------------

opt_mode = HiddenOption("Overlay Mode", MODE_OFF)
opt_x = SliderOption("Position X", 2, 0, 95, 1, description="Panel left edge, % of screen width.")
opt_y = SliderOption("Position Y", 20, 0, 95, 1, description="Panel top edge, % of screen height.")
opt_scale = SliderOption("Text Scale", 100, 50, 300, 10, description="Text size, %.")
opt_opacity = SliderOption("Background Opacity", 60, 0, 100, 5, description="Panel background opacity, %.")
opt_only_modified = BoolOption(
    "Only Modified Stats", True,
    description=(
        "Hide stats that are at their base value with no buffs right now. Stats switched on in the "
        "Stats menu still stay hidden while unmodified; turn this off to always see every enabled stat."
    ),
    on_change_anytime=_force_refresh,
)
opt_refresh = SliderOption(
    "Refresh Interval", 0.5, 0.2, 3.0, 0.1, is_integer=False,
    description="Seconds between stat updates. Timers count down every frame regardless.",
)
# Max time spent reading stats per frame: a full cycle (all stats + sources, ~10 ms) is spread
# over several frames instead of hitching one
opt_budget = SliderOption(
    "Frame Budget (ms)", 1.5, 0.2, 3.0, 0.1, is_integer=False,
    description="Max milliseconds per frame spent reading stats. Lower = smoother, slower updates.",
)
opt_timers = BoolOption(
    "Show Timers", True,
    description="Show a Timers group: action skill cooldown left and remaining time of timed buffs.",
    on_change_anytime=_force_refresh,
)
opt_toasts = BoolOption(
    "Show Notifications", True,
    description="Briefly show the overlay mode on screen when it changes.",
)


def _groups() -> List[str]:
    """Catalog groups in first-appearance order."""
    groups: List[str] = []
    for stat in stats.CATALOG:
        if stat.group not in groups:
            groups.append(stat.group)
    return groups


# Stats menu, generated from the catalog: one submenu per group with a group switch and a switch
# per stat. Identifiers only need to be unique among siblings: each NestedOption saves its children
# as its own JSON object (options.Stats.<group>.<label>).
group_opts: Dict[str, BoolOption] = {}
stat_opts: Dict[str, BoolOption] = {}


def _build_stats_menu() -> NestedOption:
    group_menus = []
    for group in _groups():
        group_opts[group] = BoolOption(
            "Show Group", True, description="Show the %s group at all." % group, on_change_anytime=_force_refresh
        )
        children = [group_opts[group]]
        for stat in stats.CATALOG:
            if stat.group != group:
                continue
            option = BoolOption(stat.label, stat.default_on, description=stat.attribute, on_change_anytime=_force_refresh)
            stat_opts[reader.stat_key(stat)] = option
            children.append(option)
        group_menus.append(NestedOption(group, children, description="Choose which %s stats to show." % group))
    return NestedOption("Stats", group_menus, description="Choose which stat groups and stats the panel shows.")


stats_menu = _build_stats_menu()


def _mode() -> int:
    try:
        return int(opt_mode.value or MODE_OFF) % 3
    except (TypeError, ValueError):
        return MODE_OFF


def _toast(text: str) -> None:
    global _toast_text, _toast_until
    if opt_toasts.value:
        _toast_text = text
        _toast_until = time.time() + TOAST_SECONDS


def _enabled_stats() -> Set[str]:
    enabled = set()
    for stat in stats.CATALOG:
        key = reader.stat_key(stat)
        group_opt = group_opts.get(stat.group)
        stat_opt = stat_opts.get(key)
        group_on = group_opt.value if group_opt is not None else True
        stat_on = stat_opt.value if stat_opt is not None else stat.default_on
        if group_on and stat_on:
            enabled.add(key)
    return enabled


def _settings() -> overlay.Settings:
    return overlay.Settings(
        x_percent=opt_x.value,
        y_percent=opt_y.value,
        scale_percent=opt_scale.value,
        background_opacity=opt_opacity.value,
        only_modified=opt_only_modified.value,
        with_sources=_mode() == MODE_SOURCES,
    )


# ---- keybinds (callbacks fire on press, no args) ------------------------------

@keybind("Cycle Overlay Mode", "F6", description="Cycle the overlay: off / values / values + sources.")
def cycle_mode() -> None:
    opt_mode.value = (_mode() + 1) % 3
    opt_mode.save()  # remember the mode between game sessions
    _force_refresh()
    _toast("Stat Inspector: " + MODE_NAMES[_mode()])


# ---- public hooks for companion tools -----------------------------------------

def refresh_now() -> None:
    """Drops the running refresh so the panel re-reads everything on the next frame."""
    _force_refresh()


def notify(text: str) -> None:
    """Shows a short on-screen notification (respects the "Show Notifications" option)."""
    _toast(text)


# ---- render hook ------------------------------------------------------------

@hook("WillowGame.WillowGameViewportClient:PostRender")
def post_render(obj: UObject, args: WrappedStruct, ret: Any, func: BoundFunction) -> None:
    global _readings, _next_refresh, _refresh
    canvas = args.Canvas
    if canvas is None:
        return None
    try:
        settings = _settings()
        now = time.time()
        if now < _toast_until:
            overlay.draw_toast(canvas, _toast_text, settings)
        if _mode() == MODE_OFF:
            return None
        pc = get_pc()
        if pc is None or pc.Pawn is None or pc.GetHUDMovie() is None:
            return None
        if _refresh is None and now >= _next_refresh:
            _refresh = reader.Refresh(settings.with_sources, _enabled_stats(), timers=opt_timers.value)
        if _refresh is not None and _refresh.step(pc, opt_budget.value / 1000.0):
            _readings = _refresh.readings
            _refresh = None
            _next_refresh = now + opt_refresh.value
        _readings = reader.update_timers(_readings, reader.world_time(pc))
        overlay.draw(canvas, overlay.build_rows(_readings, settings), settings)
    except Exception as ex:
        sources.log_error_once("render " + type(ex).__name__, "overlay error: %r" % ex)
    return None  # never block the engine's PostRender


def on_disable() -> None:
    global _readings, _toast_until, _refresh
    _readings = []
    _refresh = None
    _toast_until = 0.0
    reader._index = None  # drop the cached source index while the mod is off


mod = build_mod(
    options=[
        opt_mode, opt_x, opt_y, opt_scale, opt_opacity, opt_only_modified, opt_timers, opt_toasts,
        opt_refresh, opt_budget, stats_menu,
    ],
    keybinds=[cycle_mode],
    hooks=[post_render],
    on_disable=on_disable,
)
