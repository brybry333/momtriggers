momtriggers bot tests (see ../README.md)

make_testmap.py [out.bsp]   momtrig_ceaseless.bsp from ~/Desktop/bhop_restricted/bhop_ceaseless.zip (or $CEASELESS)
mtt.sp                      bot driver: mtt_run <log> <ticks> x y z yaw fwd side "<tick:buttons;...>" [vx vy vz],
                            mtt_name <targetname>; logs T (per tick), O (trigger outputs), R (relays) rows
momtrig_tests.py [port] [logdir]   39 checks; changes map to momtrig_ceaseless first
ceaseless_tests.py          the original bhop_ceaseless boosters (before conversion), for comparison
bspents.py                  list/dump/replace a BSP entity lump (handles LZMA lumps)
pevt.py / mksig.py          Windows server.dll RTTI vtables / SourceMod byte signatures

Servers used (2026-10-25):
  Linux:   ~/msf-rig (test-harness/make-rig.sh), port 27115, 100 tick (TickrateEnabler)
  Windows: ~/cssds-win (steamcmd +@sSteamCmdForcePlatformType windows app 232330) + MM:S/SM 1.12 Windows,
           run with: WINEPREFIX=~/.wine-cssds DISPLAY= wine srcds.exe -console -game cstrike -insecure
                     -port 27116 +ip 127.0.0.1 +map momtrig_ceaseless +exec server.cfg      (66.7 tick)
Results: 39/39 on both.
