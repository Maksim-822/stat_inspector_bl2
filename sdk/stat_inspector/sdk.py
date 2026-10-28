"""Thin wrapper around every SDK call the overlay makes (willow2-mod-manager v3.8: pyunrealsdk 1.10,
unrealsdk 3.2, mods_base 1.12).

reader / sources / overlay only talk to the engine through this module, so an SDK change is fixed
in one place, and tests only have to stub what is used here.
"""
from pathlib import Path
from typing import Any, Optional, Tuple

import unrealsdk
from unrealsdk import logging

LOG_PREFIX = "[StatInspector] "

Color = Tuple[int, int, int, int]  # (R, G, B, A)


# ---- objects ----------------------------------------------------------------

def find_object(cls: str, path: str) -> Optional[Any]:
    """`unrealsdk.find_object`, but None on a miss (the SDK raises ValueError). The class match is
    not exact (StaticFindObject with ExactClass=false), so "Object" finds anything."""
    try:
        return unrealsdk.find_object(cls, path)
    except ValueError:
        return None


class ObjectCache:
    """find_object results kept across frames as WeakPointers.

    A raw UObject wrapper must never outlive its object: attributes from level/character
    packages (GD_Shields.*, GD_Siren_Skills.*) are unloaded when the player changes character,
    and touching a stale cached wrapper crashed the game natively (pyunrealsdk access violation,
    2026-10-28, Siren -> Salvador). A WeakPointer reads as None once the object is gone, and the
    object is then looked up again. Misses are not cached: packages loaded later must be found.
    """

    def __init__(self) -> None:
        self._pointers: dict = {}

    def get(self, cls: str, path: str) -> Optional[Any]:
        pointer = self._pointers.get((cls, path))
        obj = pointer() if pointer is not None else None
        # Willow's WeakPointer is emulated and "may very rarely return a different (but valid,
        # near-identical) object" once the original's slot is reused (pyunrealsdk weak_pointer.cpp):
        # verify the path and look the object up again on a mismatch
        if obj is not None and path_name(obj) != path:
            obj = None
        if obj is None:
            obj = find_object(cls, path)
            if obj is None:
                self._pointers.pop((cls, path), None)
                return None
            from unrealsdk.unreal import WeakPointer
            self._pointers[(cls, path)] = WeakPointer(obj)
        return obj


def path_name(obj: Any) -> str:
    """Full path without the class, e.g. `GD_Weap_SniperRifles.Skills.Skill_Morningstar`."""
    try:
        return obj._path_name()
    except Exception:
        return str(obj)


def class_name(obj: Any) -> str:
    # repr() is now `Class'Path'`, so the class comes from the Class property
    try:
        return obj.Class.Name
    except Exception:
        return type(obj).__name__


def name_text(value: Any) -> Optional[str]:
    """FName / FString as str, None when empty. An unset FName reads as the string "None"."""
    if value is None:
        return None
    text = str(value)
    if not text or text == "None":
        return None
    return text


def enum_int(value: Any) -> int:
    """Byte enums (EModifierType) come back as IntFlag members; keys and formats want ints."""
    return int(value)


def get_property(obj: Any, name: str) -> Any:
    """Property read; raises AttributeError if the object's class has no such property."""
    return getattr(obj, name)


# ---- attributes -------------------------------------------------------------

# GetValue/GetBaseValue(ContextSource, out ResolvedContext, optional OptionalOverrideContextSource).
# Out params are only optional when flagged optional, so ResolvedContext is passed explicitly (None
# is just its initial value). The call returns a tuple (value, ResolvedContext). If the explicit
# form is ever rejected we fall back to the context-only call, once per session.
_attribute_call_full = True


def _call_attribute(func: Any, context: Any) -> Any:
    global _attribute_call_full
    if _attribute_call_full:
        try:
            return func(context, None, None)
        except TypeError as ex:
            _attribute_call_full = False
            log_warning("attribute call with explicit out param rejected (%s), retrying short form" % ex)
    return func(context)


def _split_return(ret: Any) -> Tuple[float, Any]:
    if isinstance(ret, (tuple, list)):
        return float(ret[0]), (ret[1] if len(ret) > 1 else None)
    return float(ret), None


def get_value(attr: Any, context: Any) -> Tuple[float, Any]:
    """Final value and the resolved context object (weapon, pool, pawn, ...)."""
    return _split_return(_call_attribute(attr.GetValue, context))


def get_base_value(attr: Any, context: Any) -> float:
    return _split_return(_call_attribute(attr.GetBaseValue, context))[0]


# ---- canvas -----------------------------------------------------------------

def text_size(canvas: Any, text: str) -> Tuple[float, float]:
    """(width, height) at scale 1. TextSize(String, out XL, out YL) returns (Ellipsis, XL, YL)."""
    ret = canvas.TextSize(text, 0, 0)
    return float(ret[-2]), float(ret[-1])


def set_font(canvas: Any, font: Any) -> None:
    canvas.Font = font


def set_pos(canvas: Any, x: float, y: float) -> None:
    canvas.SetPos(x, y)  # PosZ is optional


def set_color(canvas: Any, color: Color) -> None:
    # No tuple -> Color struct conversion in the new SDK; SetDrawColor takes R, G, B, A bytes
    r, g, b, a = color
    canvas.SetDrawColor(int(r), int(g), int(b), int(a))


_draw_text_render_info = False  # True once the 4-arg DrawText was rejected


def draw_text(canvas: Any, text: str, scale: float) -> None:
    """DrawText(Text, optional CR, optional XScale, optional YScale, optional out RenderInfo)."""
    global _draw_text_render_info
    if not _draw_text_render_info:
        try:
            canvas.DrawText(text, False, scale, scale)
            return
        except TypeError as ex:
            _draw_text_render_info = True
            log_warning("DrawText without RenderInfo rejected (%s), passing a default one" % ex)
    global _render_info
    if _render_info is None:
        _render_info = unrealsdk.make_struct("FontRenderInfo")  # plain data, no UObject refs: reusable
    canvas.DrawText(text, False, scale, scale, _render_info)


_render_info: Any = None


def draw_rect(canvas: Any, width: float, height: float, texture: Any) -> None:
    canvas.DrawRect(width, height, texture)


def canvas_size(canvas: Any) -> Tuple[float, float]:
    return float(canvas.SizeX), float(canvas.SizeY)


# ---- logging / files --------------------------------------------------------

def log(message: str) -> None:
    logging.info(LOG_PREFIX + message)


def log_warning(message: str) -> None:
    logging.warning(LOG_PREFIX + message)


def settings_dir() -> Path:
    """Writable folder for our files (the mod itself may be a read-only .sdkmod zip)."""
    from mods_base import SETTINGS_DIR
    return Path(SETTINGS_DIR)
