#!/usr/bin/env python3
"""Bot tests of bhop_ceaseless's boosters (rig on port 27115, mtt.smx loaded, map bhop_ceaseless).

Counts boosts per run from the velocity log (a +250/+500 x or +800 z step = one boost) and lists the
trigger touch events, so we can see what each anti-cboost design actually allows.
"""
import sys, os, time, csv
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from rcon import RCON

LOG = os.environ.get('MTT_LOGS', 'cstrike/addons/sourcemod/logs')
IN_JUMP, IN_DUCK = 2, 4

def park(r):
    # neutral floor spot (no triggers) so the previous run's touches end before the next run
    r.cmd('mtt_name ""', 0.1)
    r.cmd('mtt_run park 40 3300 704 14593 0 0 0 "0:0"', 0.2)
    time.sleep(0.9)

def run(r, name, ticks, pos, yaw, fwd, script, vel=None, startname=''):
    park(r)
    r.cmd('mtt_name "%s"' % startname, 0.1)
    v = ' %g %g %g' % tuple(vel) if vel else ''
    r.cmd('mtt_run %s %d %g %g %g %g %g 0 "%s"%s' % (name, ticks, pos[0], pos[1], pos[2], yaw, fwd, script, v), 0.2)
    time.sleep(ticks / 100 + 0.9)
    T, O = [], []
    for row in open('%s/mtt_%s.tsv' % (LOG, name)):
        p = row.rstrip('\n').split('\t')
        if p[0] == 'T':
            T.append(dict(tick=int(p[1]), g=int(p[2]), x=float(p[3]), y=float(p[4]), z=float(p[5]), vx=float(p[6]),
                          vy=float(p[7]), vz=float(p[8]), ground=int(p[9]), duck=int(p[10]), btn=int(p[11]), name=p[12] if len(p) > 12 else ''))
        elif p[0] == 'O':
            O.append((int(p[1]), p[2], p[3]))
    return T, O

def boosts(T, axis, size):
    out = []
    for a, b in zip(T, T[1:]):
        d = b[axis] - a[axis]
        if d > size * 0.6:
            out.append((b['tick'], round(d, 1), b['ground'], b['duck']))
    return out

def show(title, T, O, axis, size, hids):
    bs = boosts(T, axis, size)
    print('\n== %s: %d boost(s)' % (title, len(bs)))
    for b in bs:
        print('   boost at tick %d: %s +%.0f (on ground=%s ducked=%s)' % (b[0], axis, b[1], b[2] >= 0, b[3]))
    for g, out, caller in O:
        if any(h in caller for h in hids) and out in ('OnStartTouch', 'OnEndTouch'):
            print('   tick %3d %-12s %s' % (g, out, caller))
    names = []
    for t in T:
        if not names or names[-1][1] != t['name']:
            names.append((t['tick'], t['name']))
    print('   targetname: ' + ', '.join('%s@%d' % (n or '""', k) for k, n in names))
    jumps = [t['tick'] for a, t in zip(T, T[1:]) if (t['btn'] & IN_JUMP) and not (a['btn'] & IN_JUMP) and a['ground'] >= 0]
    print('   jump presses on ground at ticks: %s' % jumps)
    return len(bs)

def main():
    r = RCON()
    H = ['#813193', '#813482']           # horizontal booster pair *210 / *259 (filters boost1_filter / boost2_filter)
    V = ['#415117']                      # vertical booster *218 (plain OnEndTouch, basevelocity 0 0 800)
    S = ['#800931', '#964']              # start booster *549 (filter meow) / start zone *530
    res = {}

    # --- horizontal pair, floor z 14592, trigger 14592..14598, x 3376..5328 y 512..896 (platform 64u larger)
    T, O = run(r, 'h_jump', 120, (4352, 704, 14593), 90, 0, '0:0;20:%d;22:0' % IN_JUMP, startname='boost1_filter')
    res['h_jump'] = show('horizontal: stand, jump once', T, O, 'vx', 250, H)
    T, O = run(r, 'h_walkoff', 120, (4352, 850, 14593), 90, 250, '0:0', startname='boost1_filter')
    res['h_walkoff'] = show('horizontal: walk off the side, no jump', T, O, 'vx', 250, H)
    for dt in (31, 32, 33, 34):
        T, O = run(r, 'h_duckland%d' % dt, 70, (4352, 704, 14640), 90, 0, '0:0;%d:%d' % (dt, IN_DUCK), startname='boost1_filter')
        res['h_duckland%d' % dt] = show('horizontal: drop from 48u, crouch at tick %d (no jump)' % dt, T, O, 'vx', 250, H)
    spam = ';'.join('%d:%d' % (t, IN_DUCK if (t // 2) % 2 == 0 else 0) for t in range(0, 80, 2))
    T, O = run(r, 'h_spam', 100, (4352, 704, 14640), 90, 0, spam, startname='boost1_filter')
    res['h_spam'] = show('horizontal: crouch spam (2-tick toggles) while dropping onto it from 48u', T, O, 'vx', 250, H)

    # --- vertical booster, pad z 6496, trigger 6496..6500, x 14016..14528 y 384..1408 (pad edge = trigger edge)
    T, O = run(r, 'v_jump', 120, (14272, 896, 6497), 90, 0, '0:0;20:%d;22:0' % IN_JUMP)
    res['v_jump'] = show('vertical: stand, jump once', T, O, 'vz', 800, V)
    T, O = run(r, 'v_walkoff', 120, (14272, 1380, 6497), 90, 250, '0:0')
    res['v_walkoff'] = show('vertical: walk off the pad edge, no jump', T, O, 'vz', 800, V)
    for dt in (30, 31, 32, 33):
        T, O = run(r, 'v_duckland%d' % dt, 70, (14272, 896, 6540), 90, 0, '0:0;%d:%d' % (dt, IN_DUCK))
        res['v_duckland%d' % dt] = show('vertical: drop from 44u, crouch at tick %d (no jump)' % dt, T, O, 'vz', 800, V)

    # --- start booster *549 x -2224..-1872, z 14400..14656 (room ceiling 14656): OnStartTouch Boost(500) if named meow
    T, O = run(r, 's_meow', 30, (-2300, 0, 14500), 0, 0, '0:0', vel=(300, 0, 0), startname='meow')
    res['s_meow'] = show('start booster: fly into it named meow (left the start zone)', T, O, 'vx', 500, S)
    T, O = run(r, 's_reset', 30, (-2300, 0, 14500), 0, 0, '0:0', vel=(300, 0, 0), startname='reset')
    res['s_reset'] = show('start booster: fly into it named reset (already used this attempt)', T, O, 'vx', 500, S)
    T, O = run(r, 's_spam', 30, (-2300, 0, 14500), 0, 0, ';'.join('%d:%d' % (t, IN_DUCK if (t // 2) % 2 == 0 else 0) for t in range(0, 30, 2)), vel=(300, 0, 0), startname='meow')
    res['s_spam'] = show('start booster: fly into it named meow while crouch spamming', T, O, 'vx', 500, S)
    print('\nsummary', res)

if __name__ == '__main__':
    main()
