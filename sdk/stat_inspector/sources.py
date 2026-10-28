"""Maps AttributeModifier objects to a human readable source (skill, item, Badass Rank).

A modifier's Outer tells where it came from:
- a Skill: named skill (class skills, Badass Rank) or an unnamed skill created by an item
  (class mod, shield, relic, some weapons like Morningstar). Items point at their runtime skill
  through `RuntimeAttributeSlotSkill`; otherwise the SkillDefinition's Outer may be the item;
- the PlayerController / Transient package: effects applied directly by items, found through
  the items' effect lists ({Context, Attribute, Modifier} entries).
"""
from typing import Any, Dict, List, Optional, Tuple

from . import sdk

ITEM_EFFECT_LISTS = (
    "ExternalAttributeModifiers",
    "PartExternalAttributeModifiers",
    "ItemAttributeModifiers",
    "WeaponAttributeModifiers",
    "AppliedAttributeSlotEffects",
    "ZoomExternalAttributeModifiers",
    "ZoomWeaponAttributeModifiers",
)

SKILL_RENAMES = {"Badassitutide": "Badass Rank"}
UNATTRIBUTED = "Unattributed"

# Step tracing hook. Developer tools (not shipped) can install a tracer that records every SDK
# step of a refresh, so after a native crash the last recorded step names the culprit
tracer: Optional[Any] = None  # object with begin() and write(message); None in normal play


def trace_begin() -> None:
    if tracer is not None:
        tracer.begin()


def trace(message: str) -> None:
    if tracer is not None:
        tracer.write(message)


def item_name(item: Any) -> str:
    try:
        name = item.GetShortHumanReadableName()
        if name:
            return name
    except Exception:
        pass
    return sdk.class_name(item)


def _inventory_items(pc: Any) -> List[Any]:
    """Equipped items plus every readied inventory item (all weapon slots, not only the one in
    hand), deduplicated. Inventory is a linked list through `Inventory.Inventory`."""
    pawn = pc.Pawn
    candidates = [pawn.Weapon] + list(pawn.EquippedItems)
    inv = pawn.InvManager
    if inv is not None:
        for start in (inv.InventoryChain, inv.ItemChain):
            cur = start
            while cur is not None and len(candidates) < 64:
                candidates.append(cur)
                cur = cur.Inventory
    items, seen = [], set()
    for item in candidates:
        if item is None:
            continue
        key = sdk.path_name(item)
        if key not in seen:
            seen.add(key)
            items.append(item)
    return items


# Playthrough-wide player effects. UVHM (playthrough index 2) gives every player a -30% weapon
# swap time Scale modifier from BalanceMod_PT3.BalanceModifiers[].AttributeEffectsForPlayers; the
# engine creates it in the Transient package (probe run 5)
PLAYTHROUGH_BALANCE = {2: ("UVHM", "GD_Playthrough3Tuning.Balance.BalanceMod_PT3")}
# playthrough -> {(attribute path, modifier type, rounded value)}; plain data only, read once
_playthrough_effects: Dict[int, set] = {}


def _effects_for_playthrough(playthrough: int) -> set:
    if playthrough in _playthrough_effects:
        return _playthrough_effects[playthrough]
    effects = set()
    entry = PLAYTHROUGH_BALANCE.get(playthrough)
    balance = sdk.find_object("Object", entry[1]) if entry else None
    if balance is None:
        return effects  # not loaded yet: don't cache the empty set, try again next refresh
    for modifier in balance.BalanceModifiers:
        for effect in modifier.AttributeEffectsForPlayers or ():
            base = effect.BaseModifierValue
            value = base.BaseValueConstant * base.BaseValueScaleConstant
            effects.add((sdk.path_name(effect.AttributeToModify), sdk.enum_int(effect.ModifierType),
                         round(value, 4)))
    _playthrough_effects[playthrough] = effects
    return effects


def equipment_signature(pc: Any) -> Tuple:
    """Cheap fingerprint of everything SourceIndex depends on: inventory items, the weapon in hand
    and the playthrough. Equal signatures mean a cached index is still valid."""
    items = tuple(sdk.path_name(item) for item in _inventory_items(pc))
    try:
        playthrough = int(pc.GetCurrentPlaythrough())
    except Exception:
        playthrough = None
    return items + (sdk.path_name(pc.Pawn.Weapon) if pc.Pawn.Weapon is not None else None, playthrough)


class SourceIndex:
    """Built once per refresh: modifier / runtime skill definition path name -> source label.

    Holds only strings, so it stays valid while a refresh is spread over several frames.
    `items=False` skips the inventory scan (~2.5 ms): enough to name skills (buff timers).
    """

    def __init__(self, pc: Any, items: bool = True) -> None:
        self._by_modifier: Dict[str, str] = {}
        self._by_skill_definition: Dict[str, str] = {}
        self._skill_labels: Dict[str, str] = {}  # modifier outer path -> label, filled lazily
        self._playthrough_label = None
        self._playthrough_effects: set = set()
        if not items:
            return
        try:
            playthrough = int(pc.GetCurrentPlaythrough())
            if playthrough in PLAYTHROUGH_BALANCE:
                self._playthrough_label = PLAYTHROUGH_BALANCE[playthrough][0]
                self._playthrough_effects = _effects_for_playthrough(playthrough)
        except Exception as ex:
            log_error_once("playthrough", "playthrough effects unavailable: %s" % ex)
        for item in _inventory_items(pc):
            trace("index item %s" % sdk.path_name(item))
            name = item_name(item)
            try:
                skill = item.RuntimeAttributeSlotSkill
            except Exception:
                skill = None
            if skill is not None:
                self._by_skill_definition[sdk.path_name(skill)] = name
            for list_name in ITEM_EFFECT_LISTS:
                trace("index list %s" % list_name)
                try:
                    entries = sdk.get_property(item, list_name)
                except Exception:
                    continue  # not every item class has every list
                if not entries:
                    continue
                for entry in entries:
                    if entry.Modifier is not None:
                        self._by_modifier[sdk.path_name(entry.Modifier)] = name

    def label(self, modifier: Any, attribute: str = "") -> str:
        mod_path = sdk.path_name(modifier)
        trace("    path %s" % mod_path)
        known = self._by_modifier.get(mod_path)
        if known is not None:
            return known
        outer = modifier.Outer
        trace("    outer read")
        if outer is None:
            return UNATTRIBUTED
        outer_class = sdk.class_name(outer)
        if outer_class == "Package":
            # Engine-created modifiers (Transient): match against playthrough-wide effects
            key = (attribute, sdk.enum_int(modifier.Type), round(modifier.Value, 4))
            if self._playthrough_label and key in self._playthrough_effects:
                return self._playthrough_label
            return UNATTRIBUTED
        outer_path = sdk.path_name(outer)
        trace("    outer %s" % outer_path)
        # Stacking effects put hundreds of modifiers on one skill: resolve each skill once
        if outer_path in self._skill_labels:
            return self._skill_labels[outer_path]
        label = self._skill_label(outer) if outer_class == "Skill" else UNATTRIBUTED
        self._skill_labels[outer_path] = label
        return label

    def skill_label(self, skill: Any) -> str:
        """Display name of an active Skill (class skill, item skill, weapon behavior skill)."""
        return self._skill_label(skill)

    def _skill_label(self, skill: Any) -> str:
        definition = skill.Definition
        trace("    definition read")
        if definition is None:
            return "Unknown skill"
        definition_path = sdk.path_name(definition)
        trace("    definition %s" % definition_path)
        # Each stack may be its own Skill instance sharing one definition
        known = self._by_skill_definition.get(definition_path)
        if known is None:
            known = self._label_definition(definition)
            self._by_skill_definition[definition_path] = known
        return known

    def _label_definition(self, definition: Any) -> str:
        """Walks up the definition's outers to the first thing with a usable name.

        Weapon effects create runtime skills inside a behavior of the weapon's own skill, e.g.
        GD_Weap_SniperRifles.Skills.Skill_Morningstar:BehaviorProviderDefinition_0
            .Behavior_AttributeEffect_0.SkillDefinition_0
        so the named ancestor (or its asset name minus "Skill_") identifies the source.
        """
        cur = definition
        for depth in range(8):
            cls = sdk.class_name(cur)
            trace("    walk %s" % cls)
            if cls.startswith("Willow"):
                return item_name(cur)  # unnamed item slot skill: class mod, shield, relic
            if cls == "SkillDefinition":
                name = sdk.name_text(cur.SkillName)
                asset = sdk.path_name(cur).rsplit(".", 1)[-1]
                asset_name = asset[len("Skill_"):] if asset.startswith("Skill_") else None
                # Weapon skills reached through a behavior carry internal names
                # ("Talking Gun Skill" for Skill_Morningstar): prefer the asset name there
                if depth > 0 and asset_name:
                    return asset_name
                if name:
                    return SKILL_RENAMES.get(name, name)
                if asset_name:
                    return asset_name
            if cls == "Package":
                break
            cur = cur.Outer
            if cur is None:
                break
        # Keep the path visible so unknown runtime skills can be tracked down
        return sdk.path_name(definition).rsplit(".", 1)[-1]


def log_error_once(key: str, message: str, _seen=set()) -> None:
    if key in _seen:
        return
    _seen.add(key)
    sdk.log_warning(message)
