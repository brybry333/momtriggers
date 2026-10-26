#!/usr/bin/env python3
"""momtriggers bot test suite on momtrig_ceaseless (see make_testmap.py).

usage: momtrig_tests.py [port] [logdir]     (defaults: 27115, $MTT_LOGS or cstrike/addons/sourcemod/logs)
Needs mtt.smx + momtriggers.smx loaded and the map momtrig_ceaseless running.
Expected results follow Momentum's trigger code (decompiled): OnJump/OnLand fire from the trigger's
Touch on the jump/land command, OnJump also from EndTouch when the jump takes you out that tick.
"""
import sys, os, time, re, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from rcon import RCON

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 27115
LOG = sys.argv[2] if len(sys.argv) > 2 else os.environ.get('MTT_LOGS', 'cstrike/addons/sourcemod/logs')
IN_JUMP, IN_DUCK, IN_SPEED, IN_WALK = 2, 4, 1 << 17, 1 << 18
Z = 2944
r = RCON(port=PORT)
results = []
# fresh map: fire-once outputs (times=1) stay used up until the map reloads
r.cmd('changelevel momtrig_ceaseless', 1.0)
for _ in range(60):
    time.sleep(1)
    try:
        r = RCON(port=PORT)
        if 'momtrig_ceaseless' in r.cmd('status', 0.5) and 'registered' in r.cmd('sm_momtriggers', 0.5):
            break
    except OSError:
        pass
time.sleep(2)

def check(name, ok, detail=''):
    results.append((name, ok))
    print('  %s  %s%s' % ('PASS' if ok else 'FAIL', name, ('   [' + detail + ']') if detail else ''))

def park():
    r.cmd('mtt_name ""', 0.1)
    r.cmd('mtt_run park 40 5900 -3200 %d 0 0 0 "0:0"' % (Z + 1), 0.2)
    time.sleep(0.9)

def run(name, ticks, pos, yaw, fwd, script, vel=None, startname=''):
    park()
    r.cmd('mtt_name "%s"' % startname, 0.1)
    v = ' %g %g %g' % tuple(vel) if vel else ''
    r.cmd('mtt_run %s %d %g %g %g %g %g 0 "%s"%s' % (name, ticks, pos[0], pos[1], pos[2], yaw, fwd, script, v), 0.2)
    time.sleep(ticks / 100 + 0.5)
    path = '%s/mtt_%s.tsv' % (LOG, name)
    for _ in range(100):                      # wait for mtt to close the log (any tickrate)
        try:
            if open(path).read().rstrip().endswith('E\tdone'):
                break
        except OSError:
            pass
        time.sleep(0.2)
    T, O, R = [], [], []
    for row in open(path):
        p = row.rstrip('\r\n').split('\t')
        if p[0] == 'T':
            T.append(dict(tick=int(p[1]), g=int(p[2]), x=float(p[3]), y=float(p[4]), z=float(p[5]), vx=float(p[6]),
                          vy=float(p[7]), vz=float(p[8]), ground=int(p[9]) != -1, duck=int(p[10]), btn=int(p[11]),
                          name=p[12] if len(p) > 12 else ''))
        elif p[0] == 'O':
            O.append((int(p[1]), p[2], p[3], p[4]))
        elif p[0] == 'R':
            R.append((int(p[1]), p[2].split('#')[0], p[3]))
    return T, O, R

def jumps(T):
    return [b['g'] for a, b in zip(T, T[1:]) if a['ground'] and not b['ground'] and b['vz'] > 200]

def lands(T):
    return [b['g'] for a, b in zip(T, T[1:]) if not a['ground'] and b['ground']]

def fires(O, hid, slot):
    return [g for g, out, caller, act in O if caller.endswith('#%d' % hid) and out == 'OnUser%d' % slot]

def touches(O, hid, out):
    return [g for g, o, caller, act in O if caller.endswith('#%d' % hid) and o == out]

def relays(R, name):
    return [g for g, n, act in R if n == name]

def boosts(T, axis, size):
    # a booster kick: velocity jumps up by most of the boost AND ends up moving that way (not a landing)
    return [b['g'] for a, b in zip(T, T[1:]) if b[axis] - a[axis] > size * 0.6 and b[axis] > size * 0.6]

# ---------------------------------------------------------------------------------------------
listing = r.cmd('sm_momtriggers', 0.8)
slots = {}
for m in re.finditer(r'hammerid (\d+): OnJump=OnUser(\d) OnLand=OnUser(\d) Pressed=OnUser(\d) Held=OnUser(\d) Released=OnUser(\d)', listing):
    slots[int(m.group(1))] = dict(jump=int(m.group(2)), land=int(m.group(3)), pressed=int(m.group(4)),
                                  held=int(m.group(5)), released=int(m.group(6)))
intervals = {int(m.group(1)): float(m.group(2)) for m in re.finditer(r'hammerid (\d+):.* interval=([\d.]+)', listing)}
ti = float(re.search(r'mtt_tickinterval ([\d.]+)', r.cmd('mtt_tickinterval', 0.3)).group(1))
print(listing.strip())
print('tick interval %g' % ti)
print('\n== registration')
check('all 11 test triggers registered', all(h in slots for h in (415117, 813193, 813482, 90002, 90003, 90004, 90005, 90006, 90007, 90008, 90009)), str(sorted(slots)))
check('T4 slots avoid its own OnUser3/OnUser4 (OnJump=2, OnLand=1)', slots.get(90004, {}).get('jump') == 2 and slots.get(90004, {}).get('land') == 1, str(slots.get(90004)))
check('T8 (all OnUser slots used) gets no OnJump slot', slots.get(90008, {}).get('jump') == 0, str(slots.get(90008)))
check('trigger_userinput converted with 3 key outputs', all(slots.get(90003, {}).get(k) for k in ('pressed', 'held', 'released')), str(slots.get(90003)))
check('trigger_userinput interval read (T3 none = 0, T9 = 0.25)', intervals.get(90003) == 0 and intervals.get(90009) == 0.25, str(intervals))

# --- real Ceaseless boosters converted to OnJump --------------------------------------------
print('\n== vertical booster (Ceaseless *218, OnEndTouch -> OnJump)')
V = 415117; sj = slots[V]['jump']
T, O, R = run('v_jump', 100, (14272, 896, 6497), 90, 0, '0:0;20:%d;22:0' % IN_JUMP)
j = jumps(T)
check('jump: OnJump fires once, on the jump tick', fires(O, V, sj) == j and len(j) == 1, 'jumps %s fires %s' % (j, fires(O, V, sj)))
check('jump: booster launches (+800 z)', len(boosts(T, 'vz', 800)) == 1, str(boosts(T, 'vz', 800)))
T, O, R = run('v_walkoff', 100, (14272, 1380, 6497), 90, 250, '0:0')
check('walk off the pad: no OnJump, no boost', not fires(O, V, sj) and not boosts(T, 'vz', 800) and touches(O, V, 'OnEndTouch'),
      'fires %s endtouch %s' % (fires(O, V, sj), touches(O, V, 'OnEndTouch')))
exits, bad = [], []
for dt in range(0, 14):                       # start 1u above the trigger, sink through it, crouch at tick dt
    T, O, R = run('v_duck%d' % dt, 60, (14272, 896, 6501), 90, 0, '0:0;%d:%d' % (dt, IN_DUCK))
    if touches(O, V, 'OnEndTouch'):
        exits.append(dt)
    if fires(O, V, sj) or boosts(T, 'vz', 800):
        bad.append(dt)
check('crouch while landing on it (sweep): crouch lifts you out but no OnJump, no boost', exits and not bad,
      'crouch ticks that exited the trigger %s, boosted %s' % (exits, bad))

print('\n== horizontal booster pair (Ceaseless *210/*259, OnEndTouch -> OnJump)')
H1, H2 = 813193, 813482
T, O, R = run('h_jump', 100, (4352, 704, 14593), 90, 0, '0:0;20:%d;22:0' % IN_JUMP, startname='boost1_filter')
j = jumps(T)
check('jump: first booster fires once on the jump tick, second does not', fires(O, H1, slots[H1]['jump']) == j and len(j) == 1 and not fires(O, H2, slots[H2]['jump']),
      'jumps %s fires %s / %s' % (j, fires(O, H1, slots[H1]['jump']), fires(O, H2, slots[H2]['jump'])))
check('jump: one +250 boost', len(boosts(T, 'vx', 250)) == 1, str(boosts(T, 'vx', 250)))
T, O, R = run('h_walkoff', 100, (4352, 850, 14593), 90, 250, '0:0', startname='boost1_filter')
check('walk off: no boost', not boosts(T, 'vx', 250), str(boosts(T, 'vx', 250)))
exits, bad = [], []
for dt in range(0, 14):
    T, O, R = run('h_duck%d' % dt, 60, (4352, 704, 14599), 90, 0, '0:0;%d:%d' % (dt, IN_DUCK), startname='boost1_filter')
    if touches(O, H1, 'OnEndTouch'):
        exits.append(dt)
    if fires(O, H1, slots[H1]['jump']) or boosts(T, 'vx', 250):
        bad.append(dt)
check('crouch while landing on it (sweep): crouch lifts you out but no OnJump, no boost', exits and not bad,
      'crouch ticks that exited the trigger %s, boosted %s' % (exits, bad))
spam = ';'.join('%d:%d' % (t, IN_DUCK if t % 2 == 0 else 0) for t in range(0, 80))
T, O, R = run('h_spam', 100, (4352, 704, 14640), 90, 0, spam, startname='boost1_filter')
check('crouch spam (every tick) onto it: no boost', not boosts(T, 'vx', 250), 'endtouches %s' % touches(O, H1, 'OnEndTouch'))

# --- test pads -----------------------------------------------------------------------------
print('\n== T6 plain OnJump/OnLand pad')
P = 90006; sj, sl = slots[P]['jump'], slots[P]['land']
T, O, R = run('t6_jumps', 200, (3600, -2700, Z + 1), 90, 0, '0:0;10:%d;12:0;100:%d;102:0' % (IN_JUMP, IN_JUMP))
j, l = jumps(T), [g for g in lands(T) if g > 5]
check('two jumps inside: OnJump on both jump ticks', fires(O, P, sj) == j and len(j) == 2, 'jumps %s fires %s' % (j, fires(O, P, sj)))
check('landing back inside: OnLand on the landing tick', [g for g in fires(O, P, sl) if g > 5] == l and len(l) >= 1, 'lands %s fires %s' % (l, fires(O, P, sl)))
check('actions ran with the player as activator (r_j6 x2)', len(relays(R, 'r_j6')) == 2 and all(a.startswith('player') for g, n, a in R if n == 'r_j6'), str([x for x in R if x[1] == 'r_j6']))
check('fire-once action (times=1) ran once', len(relays(R, 'r_once6')) == 1, str(relays(R, 'r_once6')))
check('!activator AddOutput renamed the jumper', T[-1]['name'] == 'jumper6', T[-1]['name'])

T, O, R = run('t6_drop', 60, (3600, -2700, Z + 48), 90, 0, '0:0')
l = lands(T)
check('drop onto it: OnLand on the landing tick, no OnJump', fires(O, P, sl) == l and len(l) == 1 and not fires(O, P, sj), 'lands %s fires %s' % (l, fires(O, P, sl)))
land_g = l[0] if l else 30
T, O, R = run('t6_bhop', 120, (3600, -2700, Z + 48), 90, 0, '0:0;%d:%d;%d:0' % (land_g + 1, IN_JUMP, land_g + 3))
j, l = jumps(T), lands(T)
check('bhop: OnLand on landing tick, OnJump on the next tick', l[:1] == fires(O, P, sl)[:1] and j[:1] == fires(O, P, sj)[:1] and j and l and j[0] == l[0] + 1,
      'lands %s jumps %s land-fires %s jump-fires %s' % (l, j, fires(O, P, sl), fires(O, P, sj)))

T, O, R = run('t6_walkout', 80, (3800, -2700, Z + 1), 0, 250, '0:0', vel=(250, 0, 0))
e = touches(O, P, 'OnEndTouch')
check('walk out without jumping: OnEndTouch, no OnJump', e and not fires(O, P, sj), 'endtouch %s fires %s' % (e, fires(O, P, sj)))
exit_g = e[0] if e else 10
found_endtouch_path = False
for jt in (exit_g - 1, exit_g, exit_g + 1):
    T, O, R = run('t6_jumpout%d' % jt, 80, (3800, -2700, Z + 1), 0, 250, '0:0;%d:%d;%d:0' % (jt, IN_JUMP, jt + 2), vel=(250, 0, 0))
    j, f, e = jumps(T), fires(O, P, sj), touches(O, P, 'OnEndTouch')
    order = [o for g, o, c, a in O if c.endswith('#%d' % P) and o in ('OnUser%d' % sj, 'OnEndTouch')]
    print('    jump at %d: jumps %s OnJump %s OnEndTouch %s order %s' % (jt, j, f, e, order))
    if j and f and e and f[0] == e[0] == j[0]:
        found_endtouch_path = order[:2] == ['OnUser%d' % sj, 'OnEndTouch']
        check('jump that carries you out: OnJump from EndTouch, before OnEndTouch, same tick', found_endtouch_path, str(order))
    elif j and e and j[0] > e[0]:
        check('jump after leaving (tick %d): no OnJump' % jt, not f, str(f))
    elif j:
        check('jump while still inside (tick %d): exactly one OnJump' % jt, len(f) == 1 and f[0] == j[0], 'jumps %s fires %s' % (j, f))
if not found_endtouch_path:
    check('jump that carries you out: OnJump from EndTouch (timing found)', False, 'no run hit the exit tick')

print('\n== T7 tall box')
P = 90007
T, O, R = run('t7', 130, (4300, -2700, Z + 1), 90, 0, '0:0;10:%d;12:0' % IN_JUMP)
j, l = jumps(T), [g for g in lands(T) if g > 5]
check('jump inside: OnJump on jump tick', fires(O, P, slots[P]['jump']) == j and len(j) == 1, 'jumps %s fires %s' % (j, fires(O, P, slots[P]['jump'])))
check('land inside: OnLand on landing tick', [g for g in fires(O, P, slots[P]['land']) if g > 5] == l and len(l) == 1, 'lands %s fires %s' % (l, fires(O, P, slots[P]['land'])))

print('\n== T2 OnLand pad')
P = 90002
T, O, R = run('t2_drop', 60, (800, -2700, Z + 48), 90, 0, '0:0')
check('drop onto it: OnLand on landing tick', fires(O, P, slots[P]['land']) == lands(T) and len(lands(T)) == 1, 'lands %s fires %s' % (lands(T), fires(O, P, slots[P]['land'])))
T, O, R = run('t2_walkin', 80, (500, -2700, Z + 1), 0, 250, '0:0', vel=(250, 0, 0))
check('walk onto it (no landing): no OnLand', touches(O, P, 'OnStartTouch') and not fires(O, P, slots[P]['land']), 'starttouch %s fires %s' % (touches(O, P, 'OnStartTouch'), fires(O, P, slots[P]['land'])))

print('\n== T3 trigger_userinput (speed + walk)')
P = 90003; s = slots[P]
B = IN_SPEED | IN_WALK
T, O, R = run('t3_keys', 45, (1500, -2700, Z + 1), 90, 0, '0:0;5:%d;10:%d;15:%d;20:0;25:%d;40:0' % (IN_SPEED, B, IN_WALK, B))
check('OnKeyPressed when the combo completes (ticks 10, 25)', fires(O, P, s['pressed']) == [10, 25], str(fires(O, P, s['pressed'])))
held = fires(O, P, s['held'])
check('OnKeyHeld every tick both are held (10-14, 25-39)', held == list(range(10, 15)) + list(range(25, 40)), str(held))
check('OnKeyReleased whenever one of the keys is released (15, 20, 40)', fires(O, P, s['released']) == [15, 20, 40], str(fires(O, P, s['released'])))
T, O, R = run('t3_outside', 40, (1500, -2300, Z + 1), 90, 0, '0:0;5:%d;10:0' % B)
check('keys pressed outside the trigger: nothing', not any(fires(O, P, s[k]) for k in ('pressed', 'held', 'released')))

print('\n== T4 slot avoidance (own OnUser3/OnUser4, OnStartTouch -> !self FireUser3)')
P = 90004
T, O, R = run('t4_walkin', 80, (1900, -2700, Z + 1), 0, 250, '0:0', vel=(250, 0, 0))
check('walking in runs the map\'s own OnUser3 (r_u3), not OnJump/OnLand', relays(R, 'r_u3') and not relays(R, 'r_j4') and not relays(R, 'r_l4'),
      'r_u3 %s r_j4 %s r_l4 %s' % (relays(R, 'r_u3'), relays(R, 'r_j4'), relays(R, 'r_l4')))
T, O, R = run('t4_jump', 120, (2200, -2700, Z + 1), 90, 0, '0:0;10:%d;12:0' % IN_JUMP)
st = touches(O, P, 'OnStartTouch')
check('jump inside: r_j4 once, r_l4 once on landing; map\'s OnUser3 only from its own OnStartTouch, OnUser4 never',
      len(relays(R, 'r_j4')) == 1 and len(relays(R, 'r_l4')) == 1 and not relays(R, 'r_u4') and len(relays(R, 'r_u3')) == len(st),
      'r_j4 %s r_l4 %s r_u3 %s (starttouches %s) r_u4 %s' % (relays(R, 'r_j4'), relays(R, 'r_l4'), relays(R, 'r_u3'), st, relays(R, 'r_u4')))

print('\n== T5 filter (targetname vip)')
P = 90005
T, O, R = run('t5_noname', 100, (2900, -2700, Z + 1), 90, 0, '0:0;10:%d;12:0' % IN_JUMP)
check('jump without the name: no OnJump', jumps(T) and not fires(O, P, slots[P]['jump']), str(fires(O, P, slots[P]['jump'])))
T, O, R = run('t5_vip', 100, (2900, -2700, Z + 1), 90, 0, '0:0;10:%d;12:0' % IN_JUMP, startname='vip')
check('jump with the name: OnJump fires (r_j5)', fires(O, P, slots[P]['jump']) == jumps(T) and relays(R, 'r_j5'), str(fires(O, P, slots[P]['jump'])))

print('\n== T8 no free slot')
P = 90008
T, O, R = run('t8', 100, (5000, -2700, Z + 1), 90, 0, '0:0;10:%d;12:0' % IN_JUMP)
check('jump inside: no OnUser fires on it, r_j8 never runs', not any(o.startswith('OnUser') for g, o, c, a in O if c.endswith('#%d' % P)) and not relays(R, 'r_j8'))

print('\n== T9 trigger_userinput (speed), interval 0.25 s')
P = 90009; s = slots[P]
N = math.ceil(0.25 / ti - 0.001)                 # 0.25 s in ticks, rounded up (25 at 100 tick, 17 at 66.7)
t_re = 5 + 3 * N + 2                              # re-press after the interval has run out
T, O, R = run('t9_keys', 3 * N + 20, (5700, -2700, Z + 1), 90, 0,
              '0:0;5:%d;10:0;15:%d;%d:0;%d:%d;%d:0' % (IN_SPEED, IN_SPEED, 5 + 2 * N + 3, t_re, IN_SPEED, t_re + 3))
held = fires(O, P, s['held'])
check('on the ground inside the trigger', all(t['ground'] for t in T[2:]) and touches(O, P, 'OnStartTouch'))
check('OnKeyHeld: first tick held, then every %d ticks while held; re-press inside the interval waits (5, %d, %d, %d)' % (N, 5 + N, 5 + 2 * N, t_re),
      held == [5, 5 + N, 5 + 2 * N, t_re], str(held))
check('OnKeyPressed is not limited by the interval (5, 15, %d)' % t_re, fires(O, P, s['pressed']) == [5, 15, t_re], str(fires(O, P, s['pressed'])))
check('OnKeyHeld actions ran with the player as activator (r_kh9 x4)', len(relays(R, 'r_kh9')) == 4 and all(a.startswith('player') for g, n, a in R if n == 'r_kh9'),
      str([x for x in R if x[1] == 'r_kh9']))
T, O, R = run('t3_still_every_tick', 30, (1500, -2700, Z + 1), 90, 0, '0:0;5:%d;20:0' % (IN_SPEED | IN_WALK))
check('T3 (no interval) still fires OnKeyHeld every tick', fires(O, 90003, slots[90003]['held']) == list(range(5, 20)), str(fires(O, 90003, slots[90003]['held'])))

print('\n== plugin reload mid-map')
out = r.cmd('sm plugins reload momtriggers', 1.0)
again = r.cmd('sm_momtriggers', 0.8)
check('reload keeps the registrations', again.count('hammerid') == listing.count('hammerid'), out.strip()[:80])
P = 90006
T, O, R = run('t6_after_reload', 100, (3600, -2700, Z + 1), 90, 0, '0:0;10:%d;12:0' % IN_JUMP)
check('after reload: OnJump still fires once', fires(O, P, slots[P]['jump']) == jumps(T) and len(jumps(T)) == 1, str(fires(O, P, slots[P]['jump'])))

n = sum(1 for _, ok in results if ok)
print('\n%d/%d checks passed' % (n, len(results)))
sys.exit(0 if n == len(results) else 1)
