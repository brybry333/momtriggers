# Momentum Trigger Outputs (momtriggers)

A SourceMod plugin that adds Momentum Mod's trigger outputs to Counter-Strike: Source, so CS:S maps can
use them the same way Momentum maps do.

## What it is

[Momentum Mod](https://github.com/momentum-mod) gave every trigger two new outputs, and added a key-press
trigger. This plugin brings them to CS:S:

| Output / entity | Fires when |
|---|---|
| **`OnJump`** (any `trigger_*`) | a player jumps while inside the trigger |
| **`OnLand`** (any `trigger_*`) | a player lands while inside the trigger |
| **`trigger_userinput`** with `OnKeyPressed`, `OnKeyHeld`, `OnKeyReleased` | a player inside presses, holds or releases a chosen key or combo of up to 3 keys (old name `trigger_momentum_userinput` also works) |

Mappers use these like any other output in Hammer. The server runs this plugin, and the outputs behave
like Momentum's: same timing, same filter rules, same edge cases. That behaviour was taken from Momentum's
current game code; see *Exact behaviour* below.

## Why

**The problem: `OnEndTouch` boosters fire without a jump.** CS:S bhop and surf maps usually build jump
boosters as a thin floor trigger with an `OnEndTouch` output (e.g. `!activator AddOutput basevelocity 0 0 800`).
`OnEndTouch` can't tell *why* you left the trigger, so the boost also fires when you:

- walk or slide off the booster,
- get pushed off it, or
- crouch on the exact tick you land on it. Crouching in the air lifts your feet out of the trigger.
  This is "crouch boosting", and with crouch spam you can sometimes trigger it again.

**The fix: `OnJump`.** It fires only on a real jump made inside the trigger: a normal jump, bhop, crouch
jump or jumpbug. Convert a booster by renaming its outputs from `OnEndTouch` to `OnJump`, which is exactly
what Momentum's own map-porting tools do.

**Entity-only tricks don't solve it.** Renaming the player with `AddOutput targetname` and blocking that
name with a filter works well for boosters used **once per attempt**, such as start boosters. It can't make
a boost need a jump: in bot tests, targetname-gated floor boosters still fired from walking off and
crouch-landing. `OnJump` covers boosters that should only fire on a jump.

**Plugin only.** A map that relies on these outputs needs this plugin on the server. Vanilla CS:S ignores
`OnJump` / `OnLand`, and doesn't spawn `trigger_userinput` at all.

## Quick start

- **Server owners:** drop the `.smx` and the gamedata file into SourceMod 1.12+ (details below), then
  change map.
- **Mappers:** add `OnJump` / `OnLand` outputs to your triggers. In Hammer, type the name into the output
  box. Add `fgd/momtriggers.fgd` if you want `trigger_userinput`.

## Install (server)

Requirements: SourceMod **1.12 or newer** (the plugin uses its EntityLump API; SDKHooks and SDKTools ship
with SourceMod, and no DHooks is needed).

Copy these files into your server:

- `addons/sourcemod/plugins/momtriggers.smx`
- `addons/sourcemod/gamedata/momtriggers.games.txt`

Then change map. The outputs are prepared while the map loads, so loading the plugin mid-map only
takes effect on the next map.

| | |
|---|---|
| `sm_momtriggers` | (admin) lists the triggers on the current map that use these outputs |
| `momtriggers_debug 1` | prints every OnJump / OnLand / OnKey* the plugin fires |

**Platforms.** Windows and Linux, 32-bit and 64-bit. The full bot test suite (39 checks) passed on all four
at **100 tick**, using idk1703's [TickrateEnabler](https://github.com/idk1703/TickrateEnabler) (32/64-bit
builds). The 64-bit and Windows servers also passed at the default 66.7 tick.

| Server | 100 tick | 66.7 tick |
|---|---|---|
| Linux, 32-bit `srcds_linux` | 39/39 | (not run) |
| Linux, 64-bit `srcds_linux64` | 39/39 | 39/39 |
| Windows, 32-bit `srcds.exe` | 39/39 | 39/39 |
| Windows, 64-bit `srcds_win64.exe` | 39/39 | 39/39 |

64-bit CS:S servers use TF2's 64-bit launcher (`srcds_linux64` / `srcds_win64.exe`). The only gamedata entry
is one vtable offset, checked against all four `server` binaries.

## For mappers

**Using OnJump / OnLand.** Add an output named `OnJump` or `OnLand` to any trigger, exactly like
`OnStartTouch`. Hammer's CS:S FGD doesn't list these names, so type them into the "My output named"
box yourself. Hammer keeps them (they show in red) and VBSP compiles them normally.

`fgd/momtriggers.fgd` adds `trigger_userinput`. Add it in Hammer below `cstrike.fgd`.

**Converting an `OnEndTouch` jump booster.** Rename its outputs from `OnEndTouch` to `OnJump`. That's
exactly what Momentum's entity tools do ("Convert to OnJump trigger_multiple"):

```
"OnJump" "!activator,AddOutput,basevelocity 0 0 800,0,-1"
```

**Activator and caller.** These outputs use the same targets and options as any other output.
`!activator` is the player and `!self` / `!caller` is the trigger, and delays and fire-once counts
work as usual.

### Exact behaviour

All of this follows Momentum's own server code. The public Momentum source predates these outputs,
so it was decompiled from the current Playtest build.

- **OnJump** fires when a player jumps (a successful jump, including bhops and crouch jumps) while
  touching the trigger after that tick's movement, and passing its filters.
  - It also fires if that same jump carries the player out of the trigger, just before
    `OnEndTouch`.
  - Walking off, being pushed off, crouching out, or jumping after you've already left: no OnJump.
- **OnLand** fires when the player ends a tick's movement on the ground after not being on the
  ground at the end of the previous one, while inside the trigger and passing its filters.
  - Fall speed doesn't matter.
  - A bhop gives OnLand on one tick and OnJump on the next.
  - A jumpbug gives only OnJump.
- **trigger_userinput:**
  - `lookedkey` (default Forward), `lookedkey2` and `lookedkey3` (default None) pick the keys.
  - `OnKeyPressed` fires when one of them is pressed and all of them are now held.
  - `OnKeyHeld` fires every tick all of them are held.
  - `OnKeyReleased` fires when any one of them is released.
  - All three only fire while the player is inside the trigger and passes its filters.
  - Key values: -1 None, 0 Forward, 1 Back, 2 Move Left, 3 Move Right, 4 Jump, 5 Duck, 6 Attack,
    7 Attack 2, 8 Reload, 9 Speed, 10 Walk. Momentum's website docs number these wrong; the FGD and
    the game use these values.
- **One fire per jump or landing.** Each jump or landing fires a given trigger at most once.
  Momentum compares "this tick", and always gets one movement command per tick, since it runs a
  single player on a local server. A CS:S server can run several commands of one player in one
  tick under lag, so here it's tracked per command. That gives the same result without
  double-firing.
- **Who fires them.** Every player fires them, bots included, the same as all other trigger
  outputs in CS:S. Whether shavit replay bots fire them depends on how they're played back.

### Limits

- **OnUser slots.** The plugin carries each output in an `OnUser1-4` slot that the trigger doesn't
  use, and that nothing in the map fires (`FireUserN`) or adds (`AddOutput OnUserN`).
  - A trigger that already uses all four slots can't get OnJump. The server logs an error naming it.
  - Avoid `FireUser` with `!activator` as the target: the plugin then treats that slot as taken on
    every trigger.
- **No runtime adds.** Adding `OnJump` / `OnLand` at runtime with `AddOutput` isn't supported. Put
  them in the map.
- **Trigger types.** OnJump and OnLand work on `trigger_*` entities, the same ones Momentum supports
  (everything built on CBaseTrigger).

## How it works

1. **At map load (`OnMapInit`):** each trigger's `OnJump` / `OnLand` / `OnKey*` keyvalues are renamed
   to a free `OnUserN` slot, and `trigger_userinput` becomes a `trigger_multiple`. CS:S then parses
   these outputs like any other.
2. **Jumps** come from the `player_jump` event, which CS:S fires inside `CheckJumpButton`.
3. **Landings** use the same rule Momentum checks at the end of `CGameMovement::FullWalkMove`. Nothing
   can change the ground state between the end of movement and the first trigger touch of that command
   (or `PostThink` if no trigger is touched), so the plugin reads the end-of-movement state there. Every
   `trigger_*` is watched so a teleport or push can't run first. This needs no DHooks, which SourceMod
   doesn't have on 64-bit Linux.
4. **On the trigger:** SDKHooks StartTouch / Touch / EndTouch hooks replay Momentum's trigger logic,
   using `CBaseTrigger::PassesTriggerFilters` (a vtable call). They fire the output with
   `FireUserN` on the trigger, with the player as activator.

## Tests

`test/` holds the bot test setup.

- `make_testmap.py` builds `momtrig_ceaseless.bsp` from bhop_ceaseless:
  - Ceaseless's real vertical and horizontal boosters, converted to OnJump
  - test triggers for OnLand, `trigger_userinput`, filters, OnUser slot conflicts and a tall volume
- `momtrig_tests.py` runs 39 checks against a server.
- `mtt.sp` is the bot driver plugin.

All 39 checks passed on both platforms.

Credits: Momentum Mod team (https://github.com/momentum-mod) for the original outputs and entity.
