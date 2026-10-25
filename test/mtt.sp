// Test driver for momtriggers: scripted bot input + tick-exact log of trigger outputs.
//
// mtt_run <log> <ticks> x y z yaw fwd side "<tick:buttons;tick:buttons;...>" [vx vy vz]
//   teleports the bot (zero velocity unless given), then feeds it the button script
//   (buttons set at a tick stay until the next entry). Log: addons/sourcemod/logs/mtt_<log>.tsv
//   rows:  T  tick gtick x y z vx vy vz ground ducked buttons targetname
//          O  gtick output caller(name/hammerid) activator      (trigger OnUser*/OnStartTouch/OnEndTouch/OnTrigger)
//          R  gtick relayname activator                          (logic_relay OnTrigger = action executed)

#include <sourcemod>
#include <sdktools>
#include <cstrike>

#pragma semicolon 1
#pragma newdecls required

public Plugin myinfo = { name = "mtt", author = "test", description = "momtriggers test driver", version = "1.0", url = "" };

int gBot = -1;
bool gRunning;
int gTick, gMaxTicks, gFirstG;
float gAng[3], gFwd, gSide;
int gScriptTick[256], gScriptBtn[256], gScriptN;
File gLog;
char gStartName[64];

static const char gTrigOutputs[][] = { "OnUser1", "OnUser2", "OnUser3", "OnUser4", "OnStartTouch", "OnEndTouch", "OnTrigger" };
static const char gTrigClasses[][] = { "trigger_multiple", "trigger_once", "trigger_push", "trigger_teleport" };

public void OnPluginStart()
{
	RegServerCmd("mtt_run", Cmd_Run);
	RegServerCmd("mtt_ent", Cmd_Ent);
	RegServerCmd("mtt_name", Cmd_Name);
	for (int c = 0; c < sizeof(gTrigClasses); c++)
		for (int o = 0; o < sizeof(gTrigOutputs); o++)
			HookEntityOutput(gTrigClasses[c], gTrigOutputs[o], OnTrigOutput);
	HookEntityOutput("logic_relay", "OnTrigger", OnRelay);
}

public void OnMapStart()
{
	if (FindEntityByClassname(-1, "info_player_terrorist") != -1)
		return;
	int start = FindEntityByClassname(-1, "info_player_start");
	if (start == -1)
		return;
	float o[3];
	GetEntPropVector(start, Prop_Data, "m_vecOrigin", o);
	for (int i = 0; i < 4; i++)
	{
		int e = CreateEntityByName("info_player_terrorist");
		DispatchSpawn(e);
		TeleportEntity(e, o, NULL_VECTOR, NULL_VECTOR);
	}
}

int FindBot()
{
	for (int i = 1; i <= MaxClients; i++)
		if (IsClientInGame(i) && IsFakeClient(i) && !IsClientSourceTV(i) && GetClientTeam(i) > 1)
		{
			if (!IsPlayerAlive(i))
				CS_RespawnPlayer(i);
			SetEntProp(i, Prop_Data, "m_takedamage", 0);
			return i;
		}
	return -1;
}

void Describe(int ent, char[] buf, int len)
{
	if (ent == -1 || ent == 0 || !IsValidEntity(ent)) { strcopy(buf, len, "-"); return; }
	if (ent > 0 && ent <= MaxClients) { FormatEx(buf, len, "player%d", ent); return; }
	char name[64];
	GetEntPropString(ent, Prop_Data, "m_iName", name, sizeof(name));
	FormatEx(buf, len, "%s#%d", name[0] ? name : "?", GetEntProp(ent, Prop_Data, "m_iHammerID"));
}

public void OnTrigOutput(const char[] output, int caller, int activator, float delay)
{
	if (!gLog) return;
	char c[96], a[96];
	Describe(caller, c, sizeof(c)); Describe(activator, a, sizeof(a));
	gLog.WriteLine("O\t%d\t%s\t%s\t%s", GetGameTickCount() - gFirstG, output, c, a);
}

public void OnRelay(const char[] output, int caller, int activator, float delay)
{
	if (!gLog) return;
	char c[96], a[96];
	Describe(caller, c, sizeof(c)); Describe(activator, a, sizeof(a));
	gLog.WriteLine("R\t%d\t%s\t%s", GetGameTickCount() - gFirstG, c, a);
}

public Action Cmd_Run(int args)
{
	if (args < 9) { PrintToServer("usage: mtt_run log ticks x y z yaw fwd side script [vx vy vz]"); return Plugin_Handled; }
	char buf[1024], name[128];
	float pos[3], vel[3];
	GetCmdArg(1, name, sizeof(name));
	GetCmdArg(2, buf, sizeof(buf)); gMaxTicks = StringToInt(buf);
	for (int i = 0; i < 3; i++) { GetCmdArg(3 + i, buf, sizeof(buf)); pos[i] = StringToFloat(buf); }
	GetCmdArg(6, buf, sizeof(buf)); gAng[1] = StringToFloat(buf); gAng[0] = 0.0; gAng[2] = 0.0;
	GetCmdArg(7, buf, sizeof(buf)); gFwd = StringToFloat(buf);
	GetCmdArg(8, buf, sizeof(buf)); gSide = StringToFloat(buf);
	GetCmdArg(9, buf, sizeof(buf));
	char parts[256][16], tb[2][8];
	gScriptN = ExplodeString(buf, ";", parts, sizeof(parts), sizeof(parts[]));
	for (int i = 0; i < gScriptN; i++)
	{
		ExplodeString(parts[i], ":", tb, 2, 8);
		gScriptTick[i] = StringToInt(tb[0]);
		gScriptBtn[i] = StringToInt(tb[1]);
	}
	if (args >= 12)
		for (int i = 0; i < 3; i++) { GetCmdArg(10 + i, buf, sizeof(buf)); vel[i] = StringToFloat(buf); }

	gBot = FindBot();
	if (gBot == -1) { PrintToServer("mtt: no bot"); return Plugin_Handled; }

	delete gLog;
	BuildPath(Path_SM, buf, sizeof(buf), "logs/mtt_%s.tsv", name);
	gLog = OpenFile(buf, "w");
	SetEntityMoveType(gBot, MOVETYPE_WALK);
	SetEntityGravity(gBot, 1.0);
	DispatchKeyValue(gBot, "targetname", gStartName);
	TeleportEntity(gBot, pos, gAng, vel);
	gTick = 0;
	gFirstG = GetGameTickCount() + 1;
	gRunning = true;
	PrintToServer("mtt: running %s on bot %d", name, gBot);
	return Plugin_Handled;
}

// mtt_name <name> : targetname the bot gets at the start of the next runs ("" = none)
public Action Cmd_Name(int args)
{
	GetCmdArg(1, gStartName, sizeof(gStartName));
	return Plugin_Handled;
}

// mtt_ent <hammerid> : print name of entity with that hammerid
public Action Cmd_Ent(int args)
{
	char buf[32], name[64], cls[64];
	GetCmdArg(1, buf, sizeof(buf));
	int hid = StringToInt(buf);
	for (int e = MaxClients + 1; e < 2048; e++)
	{
		if (!IsValidEntity(e) || !HasEntProp(e, Prop_Data, "m_iHammerID")) continue;
		if (GetEntProp(e, Prop_Data, "m_iHammerID") != hid) continue;
		GetEntPropString(e, Prop_Data, "m_iName", name, sizeof(name));
		GetEntityClassname(e, cls, sizeof(cls));
		PrintToServer("mtt_ent #%d %s name=\"%s\"", e, cls, name);
	}
	return Plugin_Handled;
}

int ScriptButtons(int t)
{
	int b = 0;
	for (int i = 0; i < gScriptN; i++)
		if (gScriptTick[i] <= t) b = gScriptBtn[i];
	return b;
}

public Action OnPlayerRunCmd(int client, int &buttons, int &impulse, float vel[3], float angles[3], int &weapon, int &subtype, int &cmdnum, int &tickcount, int &seed, int mouse[2])
{
	if (!gRunning || client != gBot)
		return Plugin_Continue;
	angles[0] = gAng[0]; angles[1] = gAng[1]; angles[2] = 0.0;
	vel[0] = gFwd; vel[1] = gSide; vel[2] = 0.0;
	buttons = ScriptButtons(gTick);
	return Plugin_Changed;
}

public void OnPlayerRunCmdPost(int client, int buttons, int impulse, const float vel[3], const float angles[3], int weapon, int subtype, int cmdnum, int tickcount, int seed, const int mouse[2])
{
	if (!gRunning || client != gBot)
		return;
	float o[3], v[3];
	GetClientAbsOrigin(client, o);
	GetEntPropVector(client, Prop_Data, "m_vecAbsVelocity", v);
	int ground = GetEntPropEnt(client, Prop_Data, "m_hGroundEntity");
	char nm[32];
	GetEntPropString(client, Prop_Data, "m_iName", nm, sizeof(nm));
	gLog.WriteLine("T\t%d\t%d\t%.3f\t%.3f\t%.3f\t%.2f\t%.2f\t%.2f\t%d\t%d\t%d\t%s", gTick, GetGameTickCount() - gFirstG, o[0], o[1], o[2], v[0], v[1], v[2], ground, (GetEntityFlags(client) & FL_DUCKING) ? 1 : 0, buttons, nm);
	gTick++;
	if (gTick >= gMaxTicks)
	{
		gRunning = false;
		CreateTimer(0.3, Timer_Close);
		PrintToServer("mtt: done");
	}
}

public Action Timer_Close(Handle t)
{
	if (!gRunning && gLog) { gLog.WriteLine("E\tdone"); gLog.Flush(); delete gLog; }
	return Plugin_Stop;
}
