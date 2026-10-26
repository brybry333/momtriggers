#!/usr/bin/env python3
"""Builds momtrig_ceaseless.bsp from bhop_ceaseless.bsp for the momtriggers bot tests.

Real boosters converted the way Momentum's entity tools do it (OnEndTouch -> OnJump):
  V  hammerid 415117  vertical booster *218 (basevelocity 0 0 800)          pad z 6496
  H  hammerid 813193 + 813482  horizontal booster pair *210/*259 (+250 x)   floor z 14592

Test triggers on the flat floor at z 2944 (clones of the map's 512x512x4 booster brushes, z 2944..2948;
the fail teleport 96u above that floor, hammerid 588855, starts disabled in the test map):
  T2 90002 OnLand                                   ( 800, -2700)
  T3 90003 trigger_userinput, keys speed + walk     (1500, -2700)
  T4 90004 own OnUser3/OnUser4 + OnStartTouch !self FireUser3 -> OnJump/OnLand get OnUser2/OnUser1
  T5 90005 OnJump behind filter_activator_name vip  (2900, -2700)
  T6 90006 OnJump/OnLand + fire-once relay          (3600, -2700)
  T7 90007 tall 352x352x256 box (*549 clone)        (4300, -2700)
  T8 90008 all four OnUser slots taken -> OnJump has no slot (error logged)   (5000, -2700)
Every output triggers a logic_relay r_* so the log shows the action really ran (and with which activator).
"""
import sys, os, struct
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bspents

SRC = os.environ.get('CEASELESS', 'bhop_ceaseless.bsp')   # the map is not included; a .zip containing it works too
Z = 2944

def ent(kv):
    return '{\n' + ''.join('"%s" "%s"\n' % (k, v) for k, v in kv) + '}\n'

def relay(name):
    return ent([('classname', 'logic_relay'), ('targetname', name), ('origin', '3000 -3200 3000')])

def pad(model, hid, x, y, extra, cls='trigger_multiple'):
    return ent([('model', model), ('wait', '1'), ('StartDisabled', '0'), ('spawnflags', '1'),
                ('origin', '%d %d %d' % (x, y, Z + 2)), ('classname', cls), ('hammerid', str(hid))] + extra)

def convert(t, hid):
    """OnEndTouch -> OnJump inside the entity block with this hammerid."""
    key = '"hammerid" "%d"' % hid
    i = t.index(key)
    s = t.rindex('{', 0, i)
    e = t.index('}', i)
    blk = t[s:e]
    assert '"OnEndTouch"' in blk, hid
    return t[:s] + blk.replace('"OnEndTouch"', '"OnJump"') + t[e:]

def main(out):
    if SRC.endswith('.zip'):
        import zipfile
        d = bytearray(zipfile.ZipFile(SRC).read('bhop_ceaseless.bsp'))
    else:
        d = bspents.read(SRC)
    t = bspents.ents_text(d)
    for hid in (415117, 813193, 813482):
        t = convert(t, hid)
    i = t.index('"hammerid" "588855"')
    s = t.rindex('{', 0, i)
    t = t[:s] + t[s:i].replace('"StartDisabled" "0"', '"StartDisabled" "1"') + t[i:]

    add = ''
    for r in ['r_l2', 'r_kp3', 'r_kh3', 'r_kr3', 'r_j4', 'r_l4', 'r_u3', 'r_u4', 'r_j5', 'r_j6', 'r_l6', 'r_once6',
              'r_j7', 'r_l7', 'r_j8']:
        add += relay(r)
    add += ent([('classname', 'filter_activator_name'), ('targetname', 'f_vip'), ('filtername', 'vip'), ('Negated', '0'), ('origin', '3000 -3200 3000')])
    add += pad('*243', 90002, 800, -2700, [('OnLand', 'r_l2,Trigger,,0,-1')])
    add += pad('*244', 90003, 1500, -2700, [('lookedkey', '9'), ('lookedkey2', '10'),
                                            ('OnKeyPressed', 'r_kp3,Trigger,,0,-1'), ('OnKeyHeld', 'r_kh3,Trigger,,0,-1'),
                                            ('OnKeyReleased', 'r_kr3,Trigger,,0,-1')], cls='trigger_userinput')
    add += pad('*365', 90004, 2200, -2700, [('OnUser4', 'r_u4,Trigger,,0,-1'), ('OnStartTouch', '!self,FireUser3,,0,-1'),
                                            ('OnUser3', 'r_u3,Trigger,,0,-1'), ('OnJump', 'r_j4,Trigger,,0,-1'), ('OnLand', 'r_l4,Trigger,,0,-1')])
    add += pad('*410', 90005, 2900, -2700, [('filtername', 'f_vip'), ('OnJump', 'r_j5,Trigger,,0,-1')])
    add += pad('*412', 90006, 3600, -2700, [('targetname', 't6'), ('OnJump', 'r_j6,Trigger,,0,-1'), ('OnLand', 'r_l6,Trigger,,0,-1'),
                                            ('OnJump', 'r_once6,Trigger,,0,1'), ('OnJump', '!activator,AddOutput,targetname jumper6,0,-1')])
    add += ent([('model', '*549'), ('wait', '1'), ('StartDisabled', '0'), ('spawnflags', '1'), ('origin', '4300 -2700 %d' % (Z + 128)),
                ('classname', 'trigger_multiple'), ('hammerid', '90007'), ('targetname', 't7'),
                ('OnJump', 'r_j7,Trigger,,0,-1'), ('OnLand', 'r_l7,Trigger,,0,-1')])
    add += pad('*501', 90008, 5000, -2700, [('OnUser1', 'r_u3,Trigger,,0,-1'), ('OnUser2', 'r_u3,Trigger,,0,-1'),
                                            ('OnUser3', 'r_u3,Trigger,,0,-1'), ('OnUser4', 'r_u3,Trigger,,0,-1'),
                                            ('OnJump', 'r_j8,Trigger,,0,-1')])

    t = t.rstrip('\0') + add
    new = (t + '\0').encode('latin1')
    while len(d) % 4:
        d += b'\0'
    off = len(d)
    d += new
    struct.pack_into('<iii4s', d, 8, off, len(new), 0, b'\0\0\0\0')
    open(out, 'wb').write(d)
    print('wrote', out)

if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else 'momtrig_ceaseless.bsp')
