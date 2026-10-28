"""Catalog of displayed stats and how to format them.

Every attribute is read with the PlayerController as context; the game resolves it to the right
object (current weapon, grenade mod, health/shield pool, pawn).

Only attribute names that exist in the game are used (exact spelling, game typos kept).
Entries marked "# unverified" have semantics (unit, base, direction) not yet confirmed in game.
"""
from dataclasses import dataclass
from typing import Optional

# Value kinds
CRIT = "crit"    # crit multiplier, base 2.0 (x2)
MULT = "mult"    # multiplier around 1.0, shown as +X%
NUM = "num"      # plain number, compacted (12.3K)
INT = "int"      # whole number
RATE = "rate"    # interval in seconds, shown as shots per second
TIME = "time"    # seconds
PCT = "pct"      # fraction 0..1 (chance, share), shown as X%
BAR = "bar"      # Badass Rank tokens, shown with the bonus they give: tokens ** BAR_EXPONENT %
TIMER = "timer"  # seconds left on a running effect (Timers group, not from the catalog)

TIMERS_GROUP = "Timers"

# Verified in game: 30 tokens -> +12.82% (crit/health), 31 tokens -> +13.14% (melee)
BAR_EXPONENT = 0.75

# Derived stat: the class's base action skill cooldown divided by the rate it counts down at. The
# generic SkillAttributes.ActionSkillCooldownTime is unused by players (always 0, no stack).
# The cooldown pool's CurrentValue counts down from the base at the rate; while the action skill
# is active the rate is 0 (cooldown paused)
ACTION_SKILL_COOLDOWN = "@action_skill_cooldown"
COOLDOWN_RATE = "D_Attributes.ActiveSkillCooldownResource.ActiveSkillCooldownConsumptionRate"
# Player class path keyword -> (base: attribute path or constant, rate attribute). All verified in
# game 2026-10-28. Krieg's pool holds 100 points refilled at Att_PsychoCooldownRegenRate per second
# (0.833 -> 120 s; damage dealt/taken adds bursts on top); his ConsumptionRate is 0
CLASS_COOLDOWNS = (
    ("Siren", "GD_Siren_Skills.Misc.Cooldown_Phaselock", COOLDOWN_RATE),  # 13 s
    ("Mercenary", "GD_Mercenary_Skills.Misc.Cooldown_Gunzerking", COOLDOWN_RATE),  # 42 s
    ("Soldier", "GD_Soldier_Skills.Misc.Cooldown_Turret", COOLDOWN_RATE),  # 42 s
    ("Assassin", "GD_Assassin_Skills.Misc.Cooldown_Deception", COOLDOWN_RATE),  # 15 s
    ("Mechromancer", "GD_Tulip_Mechromancer_Skills.Action.Cooldown_DeathTrap", COOLDOWN_RATE),  # 60 s
    ("Lilac", 100.0, "GD_Lilac_SkillsBase.ActionSkill.Att_PsychoCooldownRegenRate"),  # Krieg, 120 s
)


# Action skills (SkillDefinition.SkillType 1): the Skill's Duration is the real one for every class
# (Gunzerking 20, Turret 24 + skills, Decepti0n 6.5, Buzz Axe 15, Deathtrap 60) except Phaselock,
# whose Skill lives 120 s while the lift lasts Att_Phaselock_Duration (5 s, 7.5 with Suspension)
ACTION_SKILL_TYPE = 1
CLASS_ACTION_SKILL_DURATIONS = (
    ("Siren", "GD_Siren_Skills.Misc.Att_Phaselock_Duration"),
)


@dataclass(frozen=True)
class StatDef:
    group: str
    label: str
    attribute: str
    kind: str
    lower_better: bool = False
    default_on: bool = True
    # Derived stats: value = attribute / divisor (both read from the game), sources come from the
    # divisor's modifier stack
    divisor: Optional[str] = None


_W = "D_Attributes.Weapon."
_DS = "D_Attributes.DamageSourceModifiers."
_DT = "D_Attributes.DamageTypeModifers."  # sic, game spelling
_SE = "D_Attributes.StatusEffectModifiers."
_GP = "D_Attributes.GameplayAttributes."
_HP = "D_Attributes.HealthResourcePool."
_SH = "D_Attributes.ShieldResourcePool."
_SHI = "D_Attributes.Shield."
_GM = "D_Attributes.GrenadeMod."
_BR = "D_Attributes.BulletReflection."
_INJ = "D_Attributes.injured."
_BAR = "GD_Challenges.BadassRewardsAttributes.Att_BAR_"
_AM = "D_Attributes.AmmoResource_"


def _ammo(label: str, pool: str) -> tuple:
    """Max ammo and regen rate of one ammo pool (default off)."""
    prefix = _AM + pool + ".Ammo_" + pool
    return (
        # unverified: pool resolution from the PC context not yet tested in game
        StatDef("Ammo", label + " max", prefix + "_MaxValue", INT, default_on=False),
        # unverified: assumed ammo per second (Vladof/Bandit/Torgue-style regen, Ammo Regen COMs)
        StatDef("Ammo", label + " regen", prefix + "_RegenerationRate", NUM, default_on=False),
    )


CATALOG = (
    # ---- Weapon (current weapon) ----
    StatDef("Weapon", "Damage", _W + "WeaponDamage", NUM),
    StatDef("Weapon", "Fire rate", _W + "WeaponFireInterval", RATE),
    StatDef("Weapon", "Reload time", _W + "WeaponReloadSpeed", TIME, lower_better=True),
    StatDef("Weapon", "Magazine", _W + "WeaponClipSize", INT),
    StatDef("Weapon", "Pellets", _W + "WeaponProjectilesPerShot", INT),
    StatDef("Weapon", "Spread", _W + "WeaponSpread", NUM, lower_better=True),
    StatDef("Weapon", "Recoil", _W + "WeaponPerShotAccuracyImpulse", NUM, lower_better=True),
    StatDef("Weapon", "Elemental chance", _W + "WeaponStatusEffectChanceModifier", MULT),
    StatDef("Weapon", "Elemental DoT", _W + "WeaponStatusEffectDamage", NUM),
    StatDef("Weapon", "Melee (weapon)", _W + "WeaponMeleeDamage", NUM),
    StatDef("Weapon", "Swap time", _W + "WeaponSwapTimeMultiplier", MULT, lower_better=True),
    StatDef("Weapon", "Ammo per shot", _W + "WeaponShotCost", INT, lower_better=True, default_on=False),
    StatDef("Weapon", "Burst count", _W + "WeaponAutomaticBurstCount", INT, default_on=False),
    StatDef("Weapon", "Burst interval", _W + "WeaponBurstInterval", NUM, lower_better=True, default_on=False),  # unverified: bl2.parts calls it a scale on fire interval, may be seconds
    StatDef("Weapon", "Extra shot chance", _W + "WeaponExtraShotChance", PCT, default_on=False),  # unverified: 0..1 chance assumed
    StatDef("Weapon", "Projectile speed", _W + "WeaponProjectileSpeedMultiplier", MULT, default_on=False),
    StatDef("Weapon", "Ricochets", _W + "WeaponAdditionalRicochets", INT, default_on=False),
    StatDef("Weapon", "Zoom FOV", _W + "WeaponZoomEndFOV", NUM, lower_better=True, default_on=False),  # lower FOV = more zoom
    StatDef("Weapon", "Equip time", _W + "WeaponEquipTime", TIME, lower_better=True, default_on=False),
    StatDef("Weapon", "Put-down time", _W + "WeaponPutDownTime", TIME, lower_better=True, default_on=False),
    StatDef("Weapon", "Spin-up time", _W + "WeaponBarrelSpinUpDuration", TIME, lower_better=True, default_on=False),  # Vladof rotating barrels
    StatDef("Weapon", "Base elem. chance", _W + "WeaponBaseStatusEffectChanceModifier", NUM, default_on=False),  # unverified: additive base, scale unknown
    StatDef("Weapon", "Combined elem. chance", _W + "WeaponCombinedStatusEffectChanceModifier", NUM, default_on=False),  # unverified: base x modifier?
    StatDef("Weapon", "Knockback", _W + "WeaponKnockback", NUM, default_on=False),
    StatDef("Weapon", "Bullet speed", "D_Attributes.WeaponBullet.WeaponBulletSpeed", NUM, default_on=False),  # unverified: may not resolve from PC
    StatDef("Weapon", "Weapon level", _W + "WeaponLevel", INT, default_on=False),

    # ---- Offense ----
    StatDef("Offense", "Crit damage", _GP + "PlayerCriticalHitBonus", CRIT),
    StatDef("Offense", "Gun damage", _DS + "InstigatedBulletDamageModifier", MULT),
    StatDef("Offense", "Grenade damage", _DS + "InstigatedGrenadeDamageModifier", MULT),
    StatDef("Offense", "Rocket damage", _DS + "InstigatedRocketDamageModifier", MULT),
    StatDef("Offense", "Melee damage", _DS + "InstigatedMeleeDamageModifier", MULT),
    StatDef("Offense", "Elemental DoT damage", _DS + "InstigatedStatusEffectDamageModifier", MULT),
    StatDef("Offense", "Fire damage", _DT + "InstigatedIncindiaryDamageModifier", MULT),
    StatDef("Offense", "Shock damage", _DT + "InstigatedShockDamageModifier", MULT),
    StatDef("Offense", "Corrosive damage", _DT + "InstigatedCorrosiveDamageModifier", MULT),
    StatDef("Offense", "Explosive damage", _DT + "InstigatedExplosiveDamageModifier", MULT),
    StatDef("Offense", "Slag damage", _DT + "InstigatedAmpDamageModifier", MULT),
    StatDef("Offense", "Fire chance", _SE + "InstigatedIncendiaryStatusChanceModifier", MULT),
    StatDef("Offense", "Shock chance", _SE + "InstigatedShockStatusChanceModifier", MULT),
    StatDef("Offense", "Corrosive chance", _SE + "InstigatedCorrosiveStatusChanceModifier", MULT),
    StatDef("Offense", "Melee added damage", _DS + "InstigatedMeleeDamageAddedBuff", NUM, default_on=False),  # unverified: flat bonus assumed
    StatDef("Offense", "Shield bypass chance", "D_Attributes.DamageSourceShieldPenetration.PercentChanceInstigatedBulletDmgIgnoresShields", NUM, default_on=False),  # unverified: bl2.parts says 0..100 scale
    StatDef("Offense", "Low-health target bonus", _GP + "PlayerTargetMinHealthDamageBoostPercent", NUM, default_on=False),  # unverified: name-based guess
    StatDef("Offense", "Healthy target gun dmg", _GP + "PlayerTargetOverMinHealthGunDamageMultiplier", MULT, default_on=False),  # unverified: name-based guess
    StatDef("Offense", "Life steal", "D_Attributes.DamageEnhancementModifiers.PlayerConvertDamageToHealingPercent", PCT, default_on=False),  # share of damage dealt returned as health
    StatDef("Offense", "Gun healing", "D_Attributes.DamageSourceHealingModifiers.InstigatedBulletHealingModifier", PCT, default_on=False),  # unverified: Grog/Rubi-style heal share
    StatDef("Offense", "Rocket healing", "D_Attributes.DamageSourceHealingModifiers.InstigatedRocketHealingModifier", PCT, default_on=False),  # unverified: like Gun healing
    StatDef("Offense", "Reflect off enemy", _BR + "BulletReflectionOffEnemyChance", PCT, default_on=False),  # unverified: 0..1 chance assumed

    # ---- Elemental (per-element impact / DoT multipliers) ----
    StatDef("Elemental", "Fire DoT damage", _DT + "InstigatedIncendiaryStatusDamageModifier", MULT, default_on=False),
    StatDef("Elemental", "Shock DoT damage", _DT + "InstigatedShockStatusDamageModifier", MULT, default_on=False),
    StatDef("Elemental", "Corrosive DoT damage", _DT + "InstigatedCorrosiveStatusDamageModifier", MULT, default_on=False),
    # unverified: the *Impact/*StatusEffect modifiers below are weapon/projectile-side per bl2.parts;
    # context resolution from the PC (weapon in hand?) not yet tested
    # Per-element damage the player takes (they resolve to the pawn; outgoing damage resolves to the
    # controller). Modified by shield skills: Chimera_Shield_<Element>Resistance_Skill (The Evolution,
    # active only while hit by that element, strength = Att_ChimeraShield_Resistance), Blockade, Candy
    # Rock (-1.5 Scale to all), Drunk (-10% normal). Probe 2026-10-28
    StatDef("Elemental", "Normal dmg taken", _DT + "NormalImpactDamageModifier", MULT, lower_better=True, default_on=False),
    StatDef("Elemental", "Fire dmg taken", _DT + "IncendiaryImpactDamageModifier", MULT, lower_better=True, default_on=False),
    StatDef("Elemental", "Shock dmg taken", _DT + "ShockImpactDamageModifier", MULT, lower_better=True, default_on=False),
    StatDef("Elemental", "Corrosive dmg taken", _DT + "CorrosiveImpactDamageModifier", MULT, lower_better=True, default_on=False),
    StatDef("Elemental", "Explosive dmg taken", _DT + "ExplosiveImpactDamageModifier", MULT, lower_better=True, default_on=False),
    StatDef("Elemental", "Slag dmg taken", _DT + "AmpImpactDamageModifier", MULT, lower_better=True, default_on=False),
    StatDef("Elemental", "Normal DoT taken", _DT + "NormalStatusEffectDamageModifier", MULT, lower_better=True, default_on=False),
    StatDef("Elemental", "Fire DoT taken", _DT + "IncendiaryStatusEffectDamageModifier", MULT, lower_better=True, default_on=False),
    StatDef("Elemental", "Shock DoT taken", _DT + "ShockStatusEffectDamageModifier", MULT, lower_better=True, default_on=False),
    StatDef("Elemental", "Corrosive DoT taken", _DT + "CorrosiveStatusEffectDamageModifier", MULT, lower_better=True, default_on=False),
    StatDef("Elemental", "Slag DoT taken", _DT + "AmpStatusEffectDamageModifier", MULT, lower_better=True, default_on=False),

    # ---- Defense ----
    StatDef("Defense", "Max health", _HP + "HealthMaxValue_Player", NUM),
    StatDef("Defense", "Health regen", _HP + "HealthPassiveRegenerationRate", NUM),
    StatDef("Defense", "Shield capacity", _SH + "ShieldMaxValue", NUM),
    StatDef("Defense", "Shield recharge rate", _SH + "ShieldOnIdleRegenerationRate", NUM),
    StatDef("Defense", "Shield recharge delay", _SH + "ShieldOnIdleRegenerationDelay", TIME, lower_better=True),
    StatDef("Defense", "Armor", _GP + "BaseArmor", NUM),
    # Shield-type elemental resistance kept in a designer attribute on the pawn, not in any player
    # stat: The Evolution sets PostAdd -0.861 (base 0); read by the game's damage calculation
    StatDef("Defense", "Shield elem. resist", "GD_Shields.Misc.Att_ChimeraShield_Resistance", PCT, lower_better=True),
    StatDef("Defense", "Bullet damage taken", _DS + "ReceivedBulletDamageModifier", MULT, lower_better=True),
    StatDef("Defense", "Melee damage taken", _DS + "ReceivedMeleeDamageModifier", MULT, lower_better=True),
    StatDef("Defense", "Explosive damage taken", _DS + "ReceivedRocketDamageModifier", MULT, lower_better=True),
    StatDef("Defense", "Elemental damage taken", _DS + "ReceivedStatusEffectDamageModifier", MULT, lower_better=True),
    StatDef("Defense", "Grenade damage taken", _DS + "ReceivedGrenadeDamageModifier", MULT, lower_better=True, default_on=False),
    StatDef("Defense", "Slag damage taken", _DS + "ReceivedAmplifyDamageModifier", MULT, lower_better=True, default_on=False),  # unverified: "Amplify" assumed = slag
    StatDef("Defense", "Health regen (active)", _HP + "HealthActiveRegenerationRate", NUM, default_on=False),
    StatDef("Defense", "Health regen (idle)", _HP + "HealthOnIdleRegenerationRate", NUM, default_on=False),
    StatDef("Defense", "Shield regen (active)", _SH + "ShieldActiveRegenerationRate", NUM, default_on=False),
    StatDef("Defense", "Shield regen (passive)", _SH + "ShieldPassiveRegenerationRate", NUM, default_on=False),
    StatDef("Defense", "Roid melee damage", _SHI + "RoidMeleeDamage", NUM, default_on=False),
    StatDef("Defense", "Amp shot damage", _SHI + "ImpactShield_DamageBonus", NUM, default_on=False),
    StatDef("Defense", "Amp shot drain", _SHI + "ImpactShield_ConsumptionOnEmpower", NUM, lower_better=True, default_on=False),  # unverified: shield drained per amp shot
    StatDef("Defense", "Ammo absorb chance", _SHI + "PercentChanceToAbsorbAmmo", PCT, default_on=False),  # unverified: 0..1 assumed
    StatDef("Defense", "Absorb dmg negated", _SHI + "PercentDamageToNegateWhenAmmoAbsorbed", PCT, default_on=False),  # unverified: 0..1 assumed
    StatDef("Defense", "Reflect off self", _BR + "BulletReflectionOffSelfChance", PCT, default_on=False),  # unverified: 0..1 assumed
    StatDef("Defense", "Self-reflect dmg", _BR + "BulletReflectedOffSelfDamageScale", MULT, default_on=False),  # unverified
    StatDef("Defense", "Self-reflect dmg taken", _BR + "BulletReflectedOffSelfDamageTakenScale", MULT, lower_better=True, default_on=False),  # unverified
    # unverified: status resistances; assumed a multiplier on incoming status chance/duration
    # (lower = more resistant); could instead be a resistance where higher is better
    # Status chance/duration multipliers on the StatusEffectsComponent: Grounded The Bee (shock immunity)
    # puts PreAdd -1.0 on ShockChanceResistanceModifier -> 0 = never shocked (verified 2026-10-28)
    StatDef("Defense", "Burn chance taken", _SE + "IgniteChanceResistanceModifier", MULT, lower_better=True),
    StatDef("Defense", "Burn duration taken", _SE + "IgniteDurationResistanceModifier", MULT, lower_better=True),
    StatDef("Defense", "Shock chance taken", _SE + "ShockChanceResistanceModifier", MULT, lower_better=True),
    StatDef("Defense", "Shock duration taken", _SE + "ShockDurationResistanceModifier", MULT, lower_better=True),
    StatDef("Defense", "Corrode chance taken", _SE + "CorrosiveChanceResistanceModifier", MULT, lower_better=True),
    StatDef("Defense", "Corrode duration taken", _SE + "CorrosiveDurationResistanceModifier", MULT, lower_better=True),
    StatDef("Defense", "Slag chance taken", _SE + "AmpChanceResistanceModifier", MULT, lower_better=True),
    StatDef("Defense", "Slag duration taken", _SE + "AmpDurationResistanceModifier", MULT, lower_better=True),

    # ---- Grenade (equipped grenade mod) ----
    StatDef("Grenade", "Grenade damage", _GM + "GrenadeDamage", NUM),
    StatDef("Grenade", "Blast radius", _GM + "BlastRadius", NUM),
    StatDef("Grenade", "Fuse time", _GM + "FuseTime", TIME),
    # The grenade's own chance value (Chain Lightning: 5.0 = base), not a multiplier around 1
    StatDef("Grenade", "Elemental chance", _GM + "GrenadeModStatusEffectChanceModifier", NUM, default_on=False),
    StatDef("Grenade", "Elemental DoT", _GM + "GrenadeModStatusEffectDamage", NUM, default_on=False),
    StatDef("Grenade", "Base elem. chance", _GM + "GrenadeModBaseStatusEffectChanceModifier", NUM, default_on=False),  # unverified: scale unknown
    StatDef("Grenade", "Combined elem. chance", _GM + "GrenadeModCombinedStatusEffectChanceModifier", NUM, default_on=False),  # unverified: scale unknown
    StatDef("Grenade", "Child grenades", _GM + "NumberOfChildProjectiles", INT, default_on=False),  # MIRV / rubberized child count
    StatDef("Grenade", "Grenade level", _GM + "GrenadeModItemLevel", INT, default_on=False),

    # ---- Ammo (per-type pools) ----
    ) + _ammo("Pistol", "Repeater_Pistol") + _ammo("SMG", "Patrol_SMG") + _ammo("AR", "Combat_Rifle") \
    + _ammo("Shotgun", "Combat_Shotgun") + _ammo("Sniper", "Sniper_Rifle") + _ammo("Launcher", "Rocket_Launcher") + (
    StatDef("Ammo", "Grenades max", "D_Attributes.Ammo_Grenade_Protean.Ammo_Grenade_ProteanMaxValue", INT, default_on=False),  # unverified: PC resolution
    StatDef("Ammo", "Grenade regen", "D_Attributes.Ammo_Grenade_Protean.Ammo_Grenade_ProteanActiveRegenerationRate", NUM, default_on=False),  # unverified: units
    StatDef("Ammo", "Weapon ammo regen", _GP + "PlayerCurrentWeaponAmmoRegenerationMultiplier", NUM, default_on=False),  # base 0 in game

    # ---- Other ----
    StatDef("Other", "Move speed", _GP + "FootSpeed", NUM),
    StatDef("Other", "Action skill cooldown", ACTION_SKILL_COOLDOWN, TIME, lower_better=True),  # see CLASS_COOLDOWNS
    StatDef("Other", "Cooldown rate", COOLDOWN_RATE, MULT),  # Quicken +30% + Bone of the Ancients +37% = +67%, verified
    StatDef("Other", "Jump height", _GP + "JumpHeight", NUM, default_on=False),
    StatDef("Other", "Acceleration", "D_Attributes.Movement.AccelRate", NUM, default_on=False),
    StatDef("Other", "Weapon slots", "D_Attributes.Inventory.InventoryWeaponEquipMax", INT, default_on=False),
    StatDef("Other", "Revive health", "D_Attributes.SkillAttributes.RevivalHealthMultiplier", MULT, default_on=False),  # unverified: health when reviving others/being revived
    StatDef("Other", "Time to be revived", _INJ + "TimeToBeRevivedMultiplier", MULT, lower_better=True, default_on=False),  # unverified
    StatDef("Other", "Health after revive", _INJ + "RevivedHealthAmount", NUM, default_on=False),  # unverified: absolute or fraction?
    StatDef("Other", "XP gain", "D_Attributes.ExperienceResourcePool.ExperiencePointsFromCombatScale", MULT, default_on=False),  # unverified
    StatDef("Other", "Player level", "D_Attributes.ExperienceResourcePool.PlayerExperienceLevel", INT, default_on=False),

    # ---- Badass Rank ----
    # Token counts per Badass Rank reward; the bonus they give is tokens ** BAR_EXPONENT % (verified)
    StatDef("Badass Rank", "Gun damage", _BAR + "Gun_Damage", BAR, default_on=False),
    StatDef("Badass Rank", "Fire rate", _BAR + "Gun_FireRate", BAR, default_on=False),
    StatDef("Badass Rank", "Reload speed", _BAR + "Gun_ReloadSpeed", BAR, default_on=False),
    StatDef("Badass Rank", "Gun accuracy", _BAR + "Gun_Accuracy", BAR, default_on=False),
    StatDef("Badass Rank", "Recoil reduction", _BAR + "Gun_RecoilReduction", BAR, default_on=False),
    StatDef("Badass Rank", "Crit damage", _BAR + "CriticalHitDamage", BAR, default_on=False),
    StatDef("Badass Rank", "Grenade damage", _BAR + "Grenade_Damage", BAR, default_on=False),
    StatDef("Badass Rank", "Melee damage", _BAR + "Melee_Damage", BAR, default_on=False),
    StatDef("Badass Rank", "Elemental chance", _BAR + "StatusEffect_ProcChance", BAR, default_on=False),
    StatDef("Badass Rank", "Elemental damage", _BAR + "StatusEffect_Damage", BAR, default_on=False),
    StatDef("Badass Rank", "Max health", _BAR + "Health_Max", BAR, default_on=False),
    StatDef("Badass Rank", "Shield capacity", _BAR + "Shield_Max", BAR, default_on=False),
    StatDef("Badass Rank", "Recharge rate", _BAR + "Shield_RechargeRate", BAR, default_on=False),
    StatDef("Badass Rank", "Recharge delay", _BAR + "Shield_RechargeDelay", BAR, default_on=False),
)


def compact(value: float) -> str:
    magnitude = abs(value)
    if magnitude >= 1e6:
        return "%.2fM" % (value / 1e6)
    if magnitude >= 1e4:
        return "%.1fK" % (value / 1e3)
    if magnitude >= 100:
        return "%.0f" % value
    if magnitude >= 10:
        return "%.1f" % value
    return "%.2f" % value


def format_value(stat: StatDef, value: float) -> str:
    if stat.kind == CRIT:
        return "x%.2f" % value
    if stat.kind == MULT:
        return "%+.1f%%" % ((value - 1.0) * 100)
    if stat.kind == PCT:
        return "%.1f%%" % (value * 100)
    if stat.kind == BAR:
        return "%d (+%.1f%%)" % (round(value), max(value, 0.0) ** BAR_EXPONENT)
    if stat.kind == INT:
        return "%d" % round(value)
    if stat.kind == RATE:
        return "%.2f/s" % (1.0 / value) if value > 0 else "-"
    if stat.kind == TIME:
        return "%.2fs" % value
    if stat.kind == TIMER:
        return "%.1fs" % max(value, 0.0)
    return compact(value)


def change_ratio(stat: StatDef, value: float, base: float) -> Optional[float]:
    """Relative change vs base in the stat's natural direction (fire rate uses 1/interval).
    None when there is nothing meaningful to compare."""
    if base == 0 or value == base:
        return None
    if stat.kind == RATE and value > 0:
        return base / value - 1.0
    return value / base - 1.0


def format_modifier(stat: StatDef, mod_type: int, value: float) -> str:
    """Scale: "+30.0%". Additive modifiers in the stat's own unit: PreAdd joins the base before
    the percentages ("+5.00s base"), PostAdd is added to the final value ("+25 flat")."""
    if mod_type == 0:
        return "%+.1f%%" % (value * 100)
    sign = "+" if value >= 0 else "-"
    if stat.kind == PCT:
        amount = "%.1f%%" % (abs(value) * 100)  # additive on a 0..1 fraction = percentage points
    elif stat.kind in (CRIT, MULT):
        amount = "%.2f" % abs(value)
    elif stat.kind in (TIME, TIMER):
        amount = "%.2fs" % abs(value)
    else:
        amount = compact(abs(value))
    return "%s%s %s" % (sign, amount, "base" if mod_type == 1 else "flat")
