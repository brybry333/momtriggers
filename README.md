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
| **`trigger_userinput`** with `OnKeyPressed`, `OnKeyHeld`, `OnKeyReleased` | a player inside presses, holds or releases a chosen key or combo of up to 3 keys (old name `trigger_momentum_userinput` also works). Optional `interval` (seconds) limits how often `OnKeyHeld` fires. |

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

**Download** the zip from [Releases](https://github.com/brybry333/momtriggers/releases/latest). It holds the
plugin, the gamedata, the Hammer FGD and the source.

- **Server owners:** drop the `.smx` and the gamedata file into SourceMod 1.12+ (details below), then
  change map.
- **Mappers:** add `fgd/momtriggers.fgd` to Hammer (below `cstrike.fgd`). `OnJump` / `OnLand` then show up
  in the output list of the triggers, and `trigger_userinput` becomes available.

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

**Platforms.** Windows and Linux, 32-bit and 64-bit. The full bot test suite (49 checks) passed on all four
at **100 tick**, using idk1703's [TickrateEnabler](https://github.com/idk1703/TickrateEnabler) (32/64-bit
builds). Linux 32-bit also passed at the default 66.7 tick.

| Server | 100 tick | 66.7 tick |
|---|---|---|
| Linux, 32-bit `srcds_linux` | 49/49 | 49/49 |
| Linux, 64-bit `srcds_linux64` | 49/49 | not run for 1.2.0 (1.1.0: 45/45) |
| Windows, 32-bit `srcds.exe` | 49/49 | not run for 1.2.0 (1.1.0: 45/45) |
| Windows, 64-bit `srcds_win64.exe` | 49/49 | not run for 1.2.0 (1.1.0: 45/45) |

64-bit CS:S servers use TF2's 64-bit launcher (`srcds_linux64` / `srcds_win64.exe`). The only gamedata entry
is one vtable offset, checked against all four `server` binaries.

## For mappers

**Hammer setup.** Add `fgd/momtriggers.fgd` to your CS:S game configuration, *below* `cstrike.fgd`
(Tools > Options > Game Configurations > Game Data files). It adds `trigger_userinput` and puts `OnJump` /
`OnLand` in the output list of these triggers: `trigger_multiple`, `trigger_once`, `trigger_push`,
`trigger_teleport`, `trigger_teleport_relative`, `trigger_gravity`, `trigger_hurt`, `trigger_look`,
`trigger_playermovement`, `trigger_proximity`, `trigger_soundscape`, `trigger_remove`, `trigger_apply_impulse`.
- Hammer can't add outputs to a class that's already defined, so the FGD redefines those triggers with
  full copies of the stock CS:S `base.fgd` definitions plus `OnJump` / `OnLand`. Their keys and outputs are
  unchanged. If you use a custom `cstrike.fgd` that changed one of these triggers, load it after this file.
- Without the FGD, type `OnJump` / `OnLand` into the "My output named" box. Hammer keeps them (they show in
  red) and VBSP compiles them normally.

**Using OnJump / OnLand.** Add an output named `OnJump` or `OnLand` to any trigger, exactly like
`OnStartTouch`.

**Converting an `OnEndTouch` jump booster.** Rename its outputs from `OnEndTouch` to `OnJump`. That's
exactly what Momentum's entity tools do ("Convert to OnJump trigger_multiple"):

```
"OnJump" "!activator,AddOutput,basevelocity 0 0 800,0,-1"
```

**Activator and caller.** These outputs use the same targets and options as any other output.
`!activator` is the player and `!self` / `!caller` is the trigger, and delays and fire-once counts
work as usual.

**"Don't land here" zones.** `OnLand` → `!activator AddOutput targetname <name>` plus a `trigger_teleport`
in the same box that only takes `<name>` (`filter_activator_name`) works like in Momentum: the player is
teleported on the tick after landing, even if they bhop off right away.
- Make the box at least ~16 units tall. A bhop's jump lifts the feet ~3 units before the teleport checks
  the player again, so a 4-unit pad lets them escape (in Momentum too).
- A jumpbug (unduck + jump just above the floor) never touches the floor, so it isn't a landing. To
  catch it too, give the same output to `OnJump` as well.

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
  - A jumpbug gives only OnJump. The jump happens with the feet ~8-9.5 units above the floor, so the
    player never lands, and OnJump only fires if the trigger reaches that high.
- **trigger_userinput:**
  - `lookedkey` (default Forward), `lookedkey2` and `lookedkey3` (default None) pick the keys.
  - `OnKeyPressed` fires when one of them is pressed and all of them are now held.
  - `OnKeyHeld` fires every tick all of them are held.
  - `OnKeyReleased` fires when any one of them is released.
  - All three only fire while the player is inside the trigger and passes its filters.
  - `interval` (**seconds**, default 0) is an addition that Momentum doesn't have. It limits `OnKeyHeld`
    to once per interval for each player. It fires right away when the keys are held, then each time the
    interval runs out while they stay held. Releasing the keys or leaving the trigger doesn't restart
    it, so tapping a key can't fire it faster. Example: `0.25` gives up to 4 fires a second, for a "boost
    while crouch is held" that doesn't stack a boost every tick. 0 is Momentum's every-tick behaviour.
    The interval is rounded up to whole ticks (0.25 s = 25 ticks at 100 tick) and counted per player
    command, like the rest of the plugin. `OnKeyPressed` and `OnKeyReleased` ignore it.
  - Key values: -1 None, 0 Forward, 1 Back, 2 Move Left, 3 Move Right, 4 Jump, 5 Duck, 6 Attack,
    7 Attack 2, 8 Reload, 9 Speed, 10 Walk. Momentum's website docs number these wrong; the FGD and
    the game use these values.
- **One fire per jump or landing.** Each jump or landing fires a given trigger at most once.
  Momentum compares "this tick", and always gets one movement command per tick, since it runs a
  single player on a local server. A CS:S server can run several commands of one player in one
  tick under lag, so here it's tracked per command. That gives the same result without
  double-firing.
- **Timing.** Their actions run at the end of the tick of the jump, landing or key press, like in
  Momentum, so an `AddOutput targetname` is already set when the player moves again on the next tick.
  - Other outputs fired by a player's movement (`OnStartTouch` etc.) normally run ~6 ticks (60 ms) later
    on a CS:S server. The player's commands run on their own clock, which the server keeps
    `sv_clockcorrection_msecs` (default 60 ms) ahead, and the event queue uses that clock. Momentum is
    single player, so it has no such delay. momtriggers fires its outputs at server time; stock outputs
    keep CS:S's timing.
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
- **Above 100 tick** the timer that fires the outputs (a `logic_timer`, minimum 0.01 s) can't run every
  tick, so on the ticks it skips the actions run one tick late instead of on the same tick.

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
5. **Timing:** an output that happens while a player's command runs (on the player's clock) waits.
   It's fired later in the same tick, when the game clock is the server's again: by a `logic_timer`
   the plugin creates, which thinks every tick after all players have moved, or at the start of the
   next player's command. If a player ends up after the timer in the engine's think order (e.g. someone
   joined later), the timer is created again at the end of the list.

## Tests

`test/` holds the bot test setup.

- `make_testmap.py` builds `momtrig_ceaseless.bsp` from bhop_ceaseless:
  - Ceaseless's real vertical and horizontal boosters, converted to OnJump
  - test triggers for OnLand, `trigger_userinput` (with and without `interval`), filters, OnUser slot
    conflicts, a tall volume (also used for a jumpbug) and a "don't land here" zone (OnLand rename +
    filtered teleport)
- `momtrig_tests.py` runs 49 checks against a server, including the timing: actions run on the
  landing tick, and the zone teleports a player who bhops off it.
- `mtt.sp` is the bot driver plugin.

All 49 checks passed on all four platforms at 100 tick.

Credits: Momentum Mod team (https://github.com/momentum-mod) for the original outputs and entity.
