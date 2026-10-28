# Stat Inspector

A Borderlands 2 mod that shows your **real, final stats**, the numbers the game actually
calculated, and **every buff behind them**.

Borderlands 2 stacks a lot of invisible modifiers on your character: skills, class mods, relics,
shields, weapon effects, Badass Rank, Ultimate Vault Hunter Mode. The item cards don't tell you
how they add up. Stat Inspector reads the result straight from the game's attribute system, so
what you see is what the game uses.

```
Crit damage            x3.96  (+98%)
    Base                       x2.00
    Practicable Interfacer    +60.0%
    Mind's Eye                +25.0%
    Badass Rank               +12.8%
```

## Features
- **Final values** for 140+ stats in groups: Weapon, Offense, Elemental, Defense, Grenade, Ammo,
  Other and Badass Rank. Green means better than base, red means worse.
- **Sources mode** lists each stat's base and every live modifier with where it comes from: the
  skill, item, Badass Rank or UVHM. Stacking effects are merged into one row with a count
  (`Morningstar x68`).
- **Timers**: action skill cooldown left, plus every running timed buff (Phaselock, Gunzerking,
  Cloud Kill, shield boosts…) with a live countdown.
- **Derived stats** the game never shows: real action skill cooldown for every class, Badass
  Rank token bonuses, shield elemental resistance, status effect resistances.
- **Self-check**: if a value doesn't match the game's own formula, the panel says so
  (`unexplained`) instead of guessing.
- Choose exactly which groups and stats to show. Light on performance: reading is spread over
  frames within a per-frame time budget.

## Requirements
- Borderlands 2 (PC)
- [willow2-mod-manager](https://github.com/bl-sdk/willow2-mod-manager) **v3.8** or newer
  ([installation guide](https://bl-sdk.github.io/willow2-mod-db/))

## Installation
1. Download `stat_inspector.sdkmod` from the Releases page.
2. Put it in the `sdk_mods` folder in your game directory
   (e.g. `...\steamapps\common\Borderlands 2\sdk_mods\`).
3. Start the game and enable **Stat Inspector** in the **MODS** menu.

## Usage
- **F6** cycles the panel: off → values → values + sources. The mode is remembered between
  sessions. You can rebind the key in the mod's keybind menu.
- **Options** (MODS → Stat Inspector):
  - panel position, text scale, background opacity;
  - **Only Modified Stats**: hides stats with no buffs right now. Turn it off to always see every
    enabled stat;
  - Show Timers, Show Notifications;
  - Refresh Interval and Frame Budget (performance);
  - **Stats**: one submenu per group, with a switch for the whole group and one per stat. About
    50 core stats are on by default.

## Reading the panel
| Shown | Meaning |
|---|---|
| `+30.0%` | percentage bonus (Scale) |
| `+5.00s base` | added to the base value *before* the percentages, in the stat's unit |
| `+25 flat` | added to the final value *after* the percentages |
| `x68` | that many stacks of the same effect |
| `UVHM` | Ultimate Vault Hunter Mode's built-in bonus (e.g. −30% weapon swap time) |
| `Unattributed` | a real modifier the game doesn't link to any item or skill |
| `unexplained` | the game's value differs from the formula: something the mod can't see |

Formula: `(base + Σbase) × (1 + Σ%⁺) / (1 + |Σ%⁻|) + Σflat`. Integer stats such as magazine size
are rounded down by the game.

## Notes
- Info only: the mod reads values and never changes gameplay.
- Co-op: client side; it shows your own stats.
- English labels only. Item and skill names come from the game's current language.

## License
[MIT](LICENSE) © smarkls
