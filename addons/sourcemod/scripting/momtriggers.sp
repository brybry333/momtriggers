/*
 * Momentum Trigger Outputs
 *
 * Brings Momentum Mod's trigger outputs to CS:S:
 *   - OnJump / OnLand on every trigger (CBaseTrigger)
 *   - trigger_userinput (alias trigger_momentum_userinput) with OnKeyPressed / OnKeyHeld / OnKeyReleased
 *
 * Behaviour follows Momentum's own server code (decompiled from the Playtest build):
 *
 *   CBaseTrigger::Touch(other)                          runs every tick for each overlapping entity,
 *       if (!PassesTriggerFilters(other))                after the player's movement
 *           { EndTouch(other); return; }
 *       if (!IsTouching(other)) StartTouch(other);
 *       if (other is a player) {
 *           if (player->m_iJumpTick == tickcount) m_OnJump.FireOutput(other, this);
 *           if (player->m_iLandTick == tickcount) m_OnLand.FireOutput(other, this);
 *       }
 *       <trigger_userinput key outputs>
 *       BaseClass::Touch(other);
 *
 *   CBaseTrigger::EndTouch(other)
 *       if (IsTouching(other)) {
 *           if (other is a player && player->m_iJumpTick == tickcount)
 *               m_OnJump.FireOutput(other, this);         (before OnEndTouch)
 *           ...OnEndTouch...
 *       }
 *
 *   m_iJumpTick: set when CheckJumpButton succeeds.
 *   m_iLandTick: set at the end of FullWalkMove when the player is on ground and was not on ground
 *                at the end of the previous FullWalkMove (CheckFalling does not count).
 *
 * Momentum runs one player on a local server, so it always gets one movement command per tick.
 * A CS:S server can run several commands of one player in a single tick, so "this tick" is
 * tracked per command here, and each jump / landing fires a given trigger at most once.
 *
 * Landing is read without DHooks (SourceMod has no DHooks on 64-bit Linux): nothing can change the
 * ground state between the end of FullWalkMove and the first trigger touch of the same usercmd (or
 * PostThink when no trigger is touched), so that is where the "end of movement" state is taken.
 *
 * The outputs are fired through the engine's own output system: at map load the OnJump / OnLand /
 * OnKey* keyvalues are moved to an OnUser1-4 slot the trigger does not use, and firing calls
 * FireUserN with the player as activator (caller = the trigger, same as Momentum).
 *
 * Addition that Momentum does not have: trigger_userinput "interval" (seconds, default 0). OnKeyHeld
 * fires at most once per interval for each player instead of every tick. 0 keeps Momentum's behaviour.
 */

#pragma semicolon 1
#pragma newdecls required

#include <sourcemod>
#include <sdktools>
#include <sdkhooks>

#define PLUGIN_VERSION "1.1.0"

#define MARKER_KEY "_momtriggers"
#define MAX_ENTS 2048

enum
{
	OUT_JUMP = 0,
	OUT_LAND,
	OUT_PRESSED,
	OUT_HELD,
	OUT_RELEASED,
	OUT_COUNT
};

static const char g_sOutName[OUT_COUNT][] = { "OnJump", "OnLand", "OnKeyPressed", "OnKeyHeld", "OnKeyReleased" };
static const char g_sFireUser[5][] = { "", "FireUser1", "FireUser2", "FireUser3", "FireUser4" };

// trigger_userinput key choices -1 (none) .. 10, index = key + 1 (Momentum's table)
static const int g_iKeyButtons[12] = {
	0, IN_FORWARD, IN_BACK, IN_MOVELEFT, IN_MOVERIGHT, IN_JUMP, IN_DUCK, IN_ATTACK, IN_ATTACK2, IN_RELOAD, IN_SPEED, IN_WALK
};

enum struct TrigInfo
{
	int slot[OUT_COUNT];	// OnUserN carrying this output, 0 = none
	int buttons;			// trigger_userinput key mask
	bool userinput;
	float interval;			// trigger_userinput "interval": seconds between OnKeyHeld fires, 0 = every tick
}

enum struct LumpEnt
{
	char classname[64];
	char targetname[128];
	int ownSlots;			// OnUserN keyvalues on the entity itself (bits 1-4)
	int kinds;				// OUT_* bits present
	bool userinput;
}

enum struct UserRef
{
	char target[128];		// target of a FireUserN / AddOutput OnUserN action
	int owner;				// lump index of the entity owning the action
	int slot;
}

ArrayList g_Infos;
StringMap g_InfoByKey;		// "model|hammerid" -> g_Infos index

int g_EntInfo[MAX_ENTS];	// g_Infos index + 1, 0 = not ours
bool g_InList[MAX_ENTS][MAXPLAYERS + 1];	// Momentum's m_hTouchingEntities membership
int g_FiredJump[MAX_ENTS][MAXPLAYERS + 1];
int g_FiredLand[MAX_ENTS][MAXPLAYERS + 1];
int g_HeldTick[MAX_ENTS][MAXPLAYERS + 1];	// player tickbase of the last OnKeyHeld, -1 = none yet

int g_CmdClient;			// client whose usercmd is running, 0 = none
int g_CmdSerial[MAXPLAYERS + 1];
int g_JumpTick[MAXPLAYERS + 1];
int g_JumpCmd[MAXPLAYERS + 1];
int g_JumpId[MAXPLAYERS + 1];
int g_LandTick[MAXPLAYERS + 1];
int g_LandCmd[MAXPLAYERS + 1];
int g_LandId[MAXPLAYERS + 1];
bool g_WasOnGround[MAXPLAYERS + 1];
bool g_MoveDone[MAXPLAYERS + 1];		// end-of-movement state already taken for the running usercmd
bool g_HookAllTriggers;				// this map uses Momentum outputs: watch every trigger_*

Handle g_hPassesTriggerFilters;
bool g_bLate;
int g_iLumpCandidates;

ConVar g_cvDebug;

public Plugin myinfo =
{
	name = "Momentum Trigger Outputs",
	author = "brybry333",
	description = "Momentum Mod's OnJump / OnLand trigger outputs and trigger_userinput for CS:S",
	version = PLUGIN_VERSION,
	url = "https://github.com/brybry333/momtriggers"
};

public APLRes AskPluginLoad2(Handle myself, bool late, char[] error, int err_max)
{
	g_bLate = late;
	return APLRes_Success;
}

public void OnPluginStart()
{
	GameData gd = new GameData("momtriggers.games");
	if (gd == null)
		SetFailState("Missing gamedata/momtriggers.games.txt");

	StartPrepSDKCall(SDKCall_Entity);
	if (!PrepSDKCall_SetFromConf(gd, SDKConf_Virtual, "CBaseTrigger::PassesTriggerFilters"))
		SetFailState("Missing offset CBaseTrigger::PassesTriggerFilters");
	PrepSDKCall_AddParameter(SDKType_CBaseEntity, SDKPass_Pointer);
	PrepSDKCall_SetReturnInfo(SDKType_Bool, SDKPass_Plain);
	g_hPassesTriggerFilters = EndPrepSDKCall();
	if (g_hPassesTriggerFilters == null)
		SetFailState("Failed to set up CBaseTrigger::PassesTriggerFilters");

	delete gd;

	g_Infos = new ArrayList(sizeof(TrigInfo));
	g_InfoByKey = new StringMap();

	CreateConVar("momtriggers_version", PLUGIN_VERSION, "Momentum Trigger Outputs version", FCVAR_NOTIFY | FCVAR_DONTRECORD);
	g_cvDebug = CreateConVar("momtriggers_debug", "0", "Print every OnJump / OnLand / OnKey* this plugin fires to the server console.", _, true, 0.0, true, 1.0);

	RegAdminCmd("sm_momtriggers", Command_List, ADMFLAG_GENERIC, "List the triggers using Momentum outputs on this map");

	HookEvent("player_jump", Event_PlayerJump, EventHookMode_Post);

	for (int i = 1; i <= MaxClients; i++)
	{
		ResetClient(i);
		if (IsClientInGame(i))
		{
			SDKHook(i, SDKHook_PostThink, Hook_PostThink);
			g_WasOnGround[i] = GetEntPropEnt(i, Prop_Data, "m_hGroundEntity") != -1;
		}
	}

	if (g_bLate)
	{
		BuildInfos();
		if (g_Infos.Length == 0 && g_iLumpCandidates > 0)
			LogMessage("%d entities use Momentum outputs but this plugin was loaded after the map started; change map to enable them.", g_iLumpCandidates);

		g_HookAllTriggers = g_Infos.Length > 0;
		char classname[64];
		int maxEnts = GetMaxEntities();
		for (int ent = MaxClients + 1; g_HookAllTriggers && ent < maxEnts && ent < MAX_ENTS; ent++)
		{
			if (IsValidEntity(ent) && GetEntityClassname(ent, classname, sizeof(classname)) && strncmp(classname, "trigger_", 8) == 0)
				WatchTrigger(ent);
		}
	}
}

// ---------------------------------------------------------------------------------------------
// Map load: move the outputs into free OnUser slots, convert trigger_userinput
// ---------------------------------------------------------------------------------------------

public void OnMapInit(const char[] mapName)
{
	RewriteLump();
	BuildInfos();
	g_HookAllTriggers = g_Infos.Length > 0;
}

static int OutKind(const char[] key)
{
	for (int k = 0; k < OUT_COUNT; k++)
	{
		if (StrEqual(key, g_sOutName[k], false))
			return k;
	}
	return -1;
}

static int UserSlot(const char[] s, int prefixLen)
{
	// "OnUser1".."OnUser4" / "FireUser1".."FireUser4", optionally followed by a space (AddOutput)
	int c = s[prefixLen];
	if (c < '1' || c > '4')
		return 0;
	if (s[prefixLen + 1] != '\0' && s[prefixLen + 1] != ' ')
		return 0;
	return c - '0';
}

static bool IsUserInputClass(const char[] classname)
{
	return StrEqual(classname, "trigger_userinput", false) || StrEqual(classname, "trigger_momentum_userinput", false);
}

// Splits "target,input,param,delay,times" (',' or ESC separated).
static bool ParseOutput(const char[] value, char[] target, int tlen, char[] input, int ilen, char[] param, int plen)
{
	int sep = ',';
	for (int i = 0; value[i]; i++)
	{
		if (value[i] == 0x1B)
		{
			sep = 0x1B;
			break;
		}
	}

	int count = 0;
	for (int i = 0; value[i]; i++)
	{
		if (value[i] == sep)
			count++;
	}
	if (count != 4)
		return false;

	int field = 0, start = 0;
	for (int i = 0; ; i++)
	{
		if (value[i] != sep && value[i] != '\0')
			continue;

		int len = i - start + 1;	// incl. terminator
		if (field == 0)
			strcopy(target, len < tlen ? len : tlen, value[start]);
		else if (field == 1)
			strcopy(input, len < ilen ? len : ilen, value[start]);
		else if (field == 2)
		{
			strcopy(param, len < plen ? len : plen, value[start]);
			break;
		}
		field++;
		start = i + 1;
	}
	return true;
}

static bool NameMatches(const char[] pattern, const char[] name)
{
	if (!pattern[0] || !name[0])
		return false;

	int len = strlen(pattern);
	if (pattern[len - 1] == '*')
		return strncmp(pattern, name, len - 1, false) == 0;
	return StrEqual(pattern, name, false);
}

// Could this FireUserN / AddOutput action reach lump entity `idx`?
static bool RefHits(UserRef ref, int idx, LumpEnt le)
{
	if (ref.target[0] == '!')
	{
		if (StrEqual(ref.target, "!self", false) || StrEqual(ref.target, "!caller", false))
			return ref.owner == idx;
		// !activator can be anything; !player / !pvsplayer / !picker are players
		return StrEqual(ref.target, "!activator", false);
	}

	// the event queue falls back to classnames when no targetname matches
	return NameMatches(ref.target, le.targetname) || NameMatches(ref.target, le.classname);
}

static int KeyButtons(int key)
{
	if (key < -1 || key > 10)
	{
		LogMessage("trigger_userinput: unhandled key %d", key);
		return 0;
	}
	return g_iKeyButtons[key + 1];
}

static void RewriteLump()
{
	int n = EntityLump.Length();
	ArrayList ents = new ArrayList(sizeof(LumpEnt));
	ArrayList refs = new ArrayList(sizeof(UserRef));

	char key[128], value[2048], target[128], input[64], param[256];

	for (int i = 0; i < n; i++)
	{
		EntityLumpEntry e = EntityLump.Get(i);
		LumpEnt le;
		int len = e.Length;

		for (int j = 0; j < len; j++)
		{
			e.Get(j, key, sizeof(key), value, sizeof(value));

			if (StrEqual(key, "classname", false))
				strcopy(le.classname, sizeof(le.classname), value);
			else if (StrEqual(key, "targetname", false))
				strcopy(le.targetname, sizeof(le.targetname), value);

			if (strncmp(key, "OnUser", 6, false) == 0)
			{
				int s = UserSlot(key, 6);
				if (s && key[7] == '\0')
					le.ownSlots |= (1 << s);
			}

			int k = OutKind(key);
			if (k != -1)
				le.kinds |= (1 << k);

			if (ParseOutput(value, target, sizeof(target), input, sizeof(input), param, sizeof(param)))
			{
				int slot = 0;
				if (strncmp(input, "FireUser", 8, false) == 0)
					slot = UserSlot(input, 8);
				else if (StrEqual(input, "AddOutput", false) && strncmp(param, "OnUser", 6, false) == 0)
					slot = UserSlot(param, 6);
				else if (StrEqual(input, "AddOutput", false) && (strncmp(param, "OnJump ", 7, false) == 0 || strncmp(param, "OnLand ", 7, false) == 0))
					LogMessage("Entity %d adds \"%s\" at runtime with AddOutput; that is not supported, put the output in the map instead.", i, param);

				if (slot)
				{
					UserRef ref;
					strcopy(ref.target, sizeof(ref.target), target);
					ref.owner = i;
					ref.slot = slot;
					refs.PushArray(ref);
				}
			}
		}

		le.userinput = IsUserInputClass(le.classname);
		if (le.userinput)
			strcopy(le.classname, sizeof(le.classname), "trigger_multiple");
		else
			le.kinds &= (1 << OUT_JUMP) | (1 << OUT_LAND);	// key outputs only exist on trigger_userinput

		ents.PushArray(le);
		delete e;
	}

	int nrefs = refs.Length;
	for (int i = 0; i < n; i++)
	{
		LumpEnt le;
		ents.GetArray(i, le);
		if ((!le.kinds && !le.userinput) || strncmp(le.classname, "trigger_", 8, false) != 0)
			continue;

		int used = le.ownSlots;
		for (int r = 0; r < nrefs; r++)
		{
			UserRef ref;
			refs.GetArray(r, ref);
			if (RefHits(ref, i, le))
				used |= (1 << ref.slot);
		}

		int slots[OUT_COUNT];
		for (int k = 0; k < OUT_COUNT; k++)
		{
			if (!(le.kinds & (1 << k)))
				continue;

			for (int s = 4; s >= 1; s--)
			{
				if (!(used & (1 << s)))
				{
					slots[k] = s;
					used |= (1 << s);
					break;
				}
			}
			if (!slots[k])
				LogError("%s \"%s\" (lump entity %d): no free OnUser slot left for %s, it will not fire.", le.classname, le.targetname, i, g_sOutName[k]);
		}

		EntityLumpEntry e = EntityLump.Get(i);
		int len = e.Length;
		int keys[3] = { 0, -1, -1 };	// lookedkey, lookedkey2, lookedkey3 (Momentum defaults)

		for (int j = 0; j < len; j++)
		{
			e.Get(j, key, sizeof(key), value, sizeof(value));

			int k = OutKind(key);
			if (k != -1 && slots[k])
			{
				FormatEx(key, sizeof(key), "OnUser%d", slots[k]);
				e.Update(j, key);
			}
			else if (le.userinput)
			{
				if (StrEqual(key, "classname", false))
					e.Update(j, NULL_STRING, "trigger_multiple");
				else if (StrEqual(key, "lookedkey", false))
					keys[0] = StringToInt(value);
				else if (StrEqual(key, "lookedkey2", false))
					keys[1] = StringToInt(value);
				else if (StrEqual(key, "lookedkey3", false))
					keys[2] = StringToInt(value);
			}
		}

		int buttons = 0;
		if (le.userinput)
			buttons = KeyButtons(keys[0]) | KeyButtons(keys[1]) | KeyButtons(keys[2]);

		FormatEx(value, sizeof(value), "%d %d %d %d %d %d %d",
			slots[OUT_JUMP], slots[OUT_LAND], slots[OUT_PRESSED], slots[OUT_HELD], slots[OUT_RELEASED], buttons, le.userinput);
		e.Append(MARKER_KEY, value);
		delete e;
	}

	delete ents;
	delete refs;
}

// Reads the markers RewriteLump left in the lump (also works after a plugin reload).
static void BuildInfos()
{
	g_Infos.Clear();
	g_InfoByKey.Clear();
	g_iLumpCandidates = 0;

	char key[64], value[256], model[PLATFORM_MAX_PATH], hammerid[32], mapKey[PLATFORM_MAX_PATH + 32], parts[7][12];
	int n = EntityLump.Length();

	for (int i = 0; i < n; i++)
	{
		EntityLumpEntry e = EntityLump.Get(i);

		if (e.GetNextKey(MARKER_KEY, value, sizeof(value)) == -1)
		{
			if (e.FindKey("OnJump") != -1 || e.FindKey("OnLand") != -1
				|| (e.GetNextKey("classname", value, sizeof(value)) != -1 && IsUserInputClass(value)))
				g_iLumpCandidates++;
			delete e;
			continue;
		}

		if (ExplodeString(value, " ", parts, sizeof(parts), sizeof(parts[])) != 7)
		{
			delete e;
			continue;
		}

		TrigInfo ti;
		for (int k = 0; k < OUT_COUNT; k++)
			ti.slot[k] = StringToInt(parts[k]);
		ti.buttons = StringToInt(parts[5]);
		ti.userinput = StringToInt(parts[6]) != 0;

		for (int j = 0, len = e.Length; ti.userinput && j < len; j++)
		{
			e.Get(j, key, sizeof(key), value, sizeof(value));
			if (StrEqual(key, "interval", false))
				ti.interval = StringToFloat(value);
		}

		e.GetNextKey("model", model, sizeof(model));
		e.GetNextKey("hammerid", hammerid, sizeof(hammerid));
		delete e;

		FormatEx(mapKey, sizeof(mapKey), "%s|%d", model, StringToInt(hammerid));
		int existing;
		if (g_InfoByKey.GetValue(mapKey, existing))
		{
			LogError("Two map entities share model/hammerid \"%s\"; only the first one gets Momentum outputs.", mapKey);
			continue;
		}
		g_InfoByKey.SetValue(mapKey, g_Infos.PushArray(ti));
	}
}

// ---------------------------------------------------------------------------------------------
// Trigger registration
// ---------------------------------------------------------------------------------------------

public void OnEntityCreated(int entity, const char[] classname)
{
	if (entity > 0 && entity < MAX_ENTS)
		g_EntInfo[entity] = 0;

	if (g_HookAllTriggers && strncmp(classname, "trigger_", 8) == 0)
		SDKHook(entity, SDKHook_SpawnPost, Hook_SpawnPost);
}

public void OnEntityDestroyed(int entity)
{
	if (entity > 0 && entity < MAX_ENTS)
		g_EntInfo[entity] = 0;
}

public void Hook_SpawnPost(int entity)
{
	WatchTrigger(entity);
}

// Every trigger_* is watched so that the first trigger touch of a usercmd (whichever trigger it is,
// e.g. a teleport that changes the ground) takes the end-of-movement state before any trigger runs.
static void WatchTrigger(int entity)
{
	if (entity <= MaxClients || entity >= MAX_ENTS)
		return;
	SDKHook(entity, SDKHook_StartTouch, Hook_StartTouch);
	SDKHook(entity, SDKHook_Touch, Hook_Touch);
	SDKHook(entity, SDKHook_EndTouch, Hook_EndTouch);
	TryRegister(entity);
}

static void TryRegister(int entity)
{
	if (entity <= MaxClients || entity >= MAX_ENTS || !g_Infos.Length)
		return;
	if (!HasEntProp(entity, Prop_Data, "m_hTouchingEntities"))	// not a CBaseTrigger
		return;

	char model[PLATFORM_MAX_PATH], mapKey[PLATFORM_MAX_PATH + 32];
	GetEntPropString(entity, Prop_Data, "m_ModelName", model, sizeof(model));
	FormatEx(mapKey, sizeof(mapKey), "%s|%d", model, GetEntProp(entity, Prop_Data, "m_iHammerID"));

	int idx;
	if (!g_InfoByKey.GetValue(mapKey, idx))
		return;

	g_EntInfo[entity] = idx + 1;

	for (int i = 0; i <= MaxClients; i++)
	{
		g_InList[entity][i] = false;
		g_FiredJump[entity][i] = 0;
		g_FiredLand[entity][i] = 0;
		g_HeldTick[entity][i] = -1;
	}
}

// ---------------------------------------------------------------------------------------------
// Jump / land tracking
// ---------------------------------------------------------------------------------------------

static void ResetClient(int client)
{
	g_CmdSerial[client] = 0;
	g_JumpTick[client] = -1;
	g_JumpCmd[client] = 0;
	g_JumpId[client] = 0;
	g_LandTick[client] = -1;
	g_LandCmd[client] = 0;
	g_LandId[client] = 0;
	g_WasOnGround[client] = false;
	g_MoveDone[client] = true;

	for (int ent = 0; ent < MAX_ENTS; ent++)
	{
		if (g_EntInfo[ent])
		{
			g_InList[ent][client] = false;
			g_FiredJump[ent][client] = 0;
			g_FiredLand[ent][client] = 0;
			g_HeldTick[ent][client] = -1;
		}
	}
}

public void OnClientPutInServer(int client)
{
	ResetClient(client);
	SDKHook(client, SDKHook_PostThink, Hook_PostThink);
}

public void OnClientDisconnect(int client)
{
	if (g_CmdClient == client)
		g_CmdClient = 0;
	ResetClient(client);
}

public Action OnPlayerRunCmd(int client, int &buttons, int &impulse, float vel[3], float angles[3], int &weapon, int &subtype, int &cmdnum, int &tickcount, int &seed, int mouse[2])
{
	g_CmdSerial[client]++;
	g_CmdClient = client;
	g_MoveDone[client] = false;
	return Plugin_Continue;
}

public void OnPlayerRunCmdPost(int client, int buttons, int impulse, const float vel[3], const float angles[3], int weapon, int subtype, int cmdnum, int tickcount, int seed, const int mouse[2])
{
	if (g_CmdClient == client)
	{
		MovementEnd(client);
		g_CmdClient = 0;
	}
}

// RunCommand: movement, then ProcessImpacts (trigger touches first), then PostThink.
public void Hook_PostThink(int client)
{
	if (g_CmdClient == client)
		MovementEnd(client);
}

// CheckJumpButton succeeded (fired from inside the movement code).
public void Event_PlayerJump(Event event, const char[] name, bool dontBroadcast)
{
	int client = GetClientOfUserId(event.GetInt("userid"));
	if (!client)
		return;

	g_JumpTick[client] = GetGameTickCount();
	g_JumpCmd[client] = (g_CmdClient == client) ? g_CmdSerial[client] : 0;
	g_JumpId[client]++;
}

// Momentum (C2013GameMovement::FullWalkMove): landed = on ground at the end of the walk move, not on
// ground at the end of the previous one. Called once per usercmd, right after the movement.
static void MovementEnd(int client)
{
	if (g_MoveDone[client])
		return;
	g_MoveDone[client] = true;

	if (GetEntityMoveType(client) != MOVETYPE_WALK)	// FullWalkMove didn't run (ladder, noclip, ...)
		return;

	bool onGround = GetEntPropEnt(client, Prop_Data, "m_hGroundEntity") != -1;
	if (onGround && !g_WasOnGround[client])
	{
		g_LandTick[client] = GetGameTickCount();
		g_LandCmd[client] = g_CmdSerial[client];
		g_LandId[client]++;
	}
	g_WasOnGround[client] = onGround;
}

// "this tick" in Momentum terms: the current usercmd while it runs, otherwise the current tick.
static bool JumpedNow(int client)
{
	if (g_CmdClient == client)
		return g_JumpCmd[client] != 0 && g_JumpCmd[client] == g_CmdSerial[client];
	return g_JumpTick[client] == GetGameTickCount();
}

static bool LandedNow(int client)
{
	if (g_CmdClient == client)
		return g_LandCmd[client] != 0 && g_LandCmd[client] == g_CmdSerial[client];
	return g_LandTick[client] == GetGameTickCount();
}

// ---------------------------------------------------------------------------------------------
// Trigger hooks (pre: our outputs queue before the trigger's own, like in Momentum)
// ---------------------------------------------------------------------------------------------

static bool IsPlayer(int ent)
{
	return ent > 0 && ent <= MaxClients && IsClientInGame(ent);
}

static void Fire(int trigger, int slot, int out, int client)
{
	if (g_cvDebug.BoolValue)
	{
		char name[64];
		GetEntPropString(trigger, Prop_Data, "m_iName", name, sizeof(name));
		PrintToServer("[momtriggers] tick %d: %s on #%d \"%s\" (hammerid %d) by %N",
			GetGameTickCount(), g_sOutName[out], trigger, name, GetEntProp(trigger, Prop_Data, "m_iHammerID"), client);
	}
	AcceptEntityInput(trigger, g_sFireUser[slot], client, trigger);
}

static void TryFireJump(int trigger, TrigInfo ti, int client)
{
	if (ti.slot[OUT_JUMP] && JumpedNow(client) && g_FiredJump[trigger][client] != g_JumpId[client])
	{
		g_FiredJump[trigger][client] = g_JumpId[client];
		Fire(trigger, ti.slot[OUT_JUMP], OUT_JUMP, client);
	}
}

// trigger_userinput "interval": OnKeyHeld at most once per interval for each player. Counted in the
// player's own command ticks (tickbase), so commands that run late in one server tick still count as
// separate ticks. Releasing the keys or leaving the trigger does not restart it, so tapping can't beat it.
static bool HeldIntervalOver(int trigger, float interval, int client)
{
	if (interval <= 0.0)
		return true;

	int now = GetEntProp(client, Prop_Send, "m_nTickBase");
	int last = g_HeldTick[trigger][client];
	int wait = RoundToCeil(interval / GetTickInterval() - 0.001);
	if (last != -1 && now >= last && now - last < wait)
		return false;

	g_HeldTick[trigger][client] = now;
	return true;
}

public Action Hook_StartTouch(int trigger, int other)
{
	if (!IsPlayer(other))
		return Plugin_Continue;
	if (g_CmdClient == other)
		MovementEnd(other);

	if (g_EntInfo[trigger] && SDKCall(g_hPassesTriggerFilters, trigger, other))
		g_InList[trigger][other] = true;
	return Plugin_Continue;
}

public Action Hook_Touch(int trigger, int other)
{
	if (!IsPlayer(other))
		return Plugin_Continue;
	if (g_CmdClient == other)
		MovementEnd(other);
	if (!g_EntInfo[trigger])
		return Plugin_Continue;

	TrigInfo ti;
	g_Infos.GetArray(g_EntInfo[trigger] - 1, ti);

	if (!SDKCall(g_hPassesTriggerFilters, trigger, other))
	{
		// Momentum calls EndTouch here
		if (g_InList[trigger][other])
		{
			g_InList[trigger][other] = false;
			TryFireJump(trigger, ti, other);
		}
		return Plugin_Continue;
	}

	g_InList[trigger][other] = true;

	TryFireJump(trigger, ti, other);

	if (ti.slot[OUT_LAND] && LandedNow(other) && g_FiredLand[trigger][other] != g_LandId[other])
	{
		g_FiredLand[trigger][other] = g_LandId[other];
		Fire(trigger, ti.slot[OUT_LAND], OUT_LAND, other);
	}

	if (ti.userinput)
	{
		int mask = ti.buttons;
		int held = GetEntProp(other, Prop_Data, "m_nButtons");
		bool allHeld = (mask & ~held) == 0;

		if (ti.slot[OUT_PRESSED] && (GetEntProp(other, Prop_Data, "m_afButtonPressed") & mask) && allHeld)
			Fire(trigger, ti.slot[OUT_PRESSED], OUT_PRESSED, other);
		if (ti.slot[OUT_HELD] && allHeld && HeldIntervalOver(trigger, ti.interval, other))
			Fire(trigger, ti.slot[OUT_HELD], OUT_HELD, other);
		if (ti.slot[OUT_RELEASED] && (GetEntProp(other, Prop_Data, "m_afButtonReleased") & mask))
			Fire(trigger, ti.slot[OUT_RELEASED], OUT_RELEASED, other);
	}
	return Plugin_Continue;
}

public Action Hook_EndTouch(int trigger, int other)
{
	if (!g_EntInfo[trigger] || !IsPlayer(other) || !g_InList[trigger][other])
		return Plugin_Continue;

	g_InList[trigger][other] = false;

	TrigInfo ti;
	g_Infos.GetArray(g_EntInfo[trigger] - 1, ti);
	TryFireJump(trigger, ti, other);
	return Plugin_Continue;
}

// ---------------------------------------------------------------------------------------------

public Action Command_List(int client, int args)
{
	int count = 0;
	char classname[64], name[64];
	for (int ent = MaxClients + 1; ent < MAX_ENTS; ent++)
	{
		if (!g_EntInfo[ent] || !IsValidEntity(ent))
			continue;

		TrigInfo ti;
		g_Infos.GetArray(g_EntInfo[ent] - 1, ti);
		GetEntityClassname(ent, classname, sizeof(classname));
		GetEntPropString(ent, Prop_Data, "m_iName", name, sizeof(name));
		ReplyToCommand(client, "#%d %s%s \"%s\" hammerid %d: OnJump=OnUser%d OnLand=OnUser%d Pressed=OnUser%d Held=OnUser%d Released=OnUser%d buttons=%d interval=%.3f",
			ent, classname, ti.userinput ? " (trigger_userinput)" : "", name, GetEntProp(ent, Prop_Data, "m_iHammerID"),
			ti.slot[OUT_JUMP], ti.slot[OUT_LAND], ti.slot[OUT_PRESSED], ti.slot[OUT_HELD], ti.slot[OUT_RELEASED], ti.buttons, ti.interval);
		count++;
	}
	ReplyToCommand(client, "[momtriggers] %d trigger(s) registered (0 = output not used).", count);
	return Plugin_Handled;
}
