Bot tests for momtriggers (see ../README.md).

Files
  make_testmap.py [out.bsp]   builds momtrig_ceaseless.bsp from bhop_ceaseless.bsp (not included; set CEASELESS=path,
                              a .zip containing the .bsp also works). Converts Ceaseless's real OnEndTouch boosters to
                              OnJump and adds test triggers (OnLand, trigger_userinput, filter, OnUser slot conflicts,
                              tall volume) on a flat floor.
  mtt.sp                      SourceMod test driver: mtt_run <log> <ticks> x y z yaw fwd side "<tick:buttons;...>" [vx vy vz],
                              mtt_name <targetname>. Logs T (per tick), O (trigger outputs) and R (logic_relay) rows to
                              addons/sourcemod/logs/mtt_<log>.tsv
  momtrig_tests.py [port] [logdir]   the 39 checks; changes the map to momtrig_ceaseless first
  ceaseless_tests.py          the original (unconverted) bhop_ceaseless boosters, for comparison
  bspents.py                  list / dump / replace a BSP entity lump (handles LZMA lumps)
  pevt.py                     MSVC RTTI vtable dump for Windows server.dll (used to verify the gamedata offset)
  rcon.py                     minimal Source RCON client

Setup
  A CS:S server with SourceMod 1.12+, momtriggers.smx + gamedata, mtt.smx, momtrig_ceaseless.bsp (+ a .nav so bots
  can join), sv_cheats 1, rcon_password mtpass, one bot (bot_add_t).
  python3 momtrig_tests.py <rcon port> <server>/cstrike/addons/sourcemod/logs

Results (2026-10-25): 39/39 on Linux 32-bit (100 tick), Linux 64-bit, Windows 32-bit and Windows 64-bit (66.7 tick).
64-bit servers ran on TF2's srcds_linux64 / srcds_win64.exe launchers; the Windows servers ran under Wine.
