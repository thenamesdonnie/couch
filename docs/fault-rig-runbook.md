# Fault rig: the daytime session

About 15 minutes, in daylight, with you in the room and the TV on.

We break the console on purpose, one small way at a time, and watch whether
couchd would have fixed it. couchd is still only watching and writing things
down, so it never actually fixes anything. Nothing you do here is permanent.

Everything is undone automatically. Each command puts itself on a timer before
it breaks anything, so even if the laptop dies mid step, the console repairs
itself within a minute or two.

## The one line that stops everything

If anything looks wrong at any point, type this and it all goes back:

    ~/couch/tools/fault-rig restore --i-am-present

It is safe to run twice, or ten times, or when nothing is wrong.

## Before you start

1. TV on, Kodi on the home screen, no game running.
2. Do not touch the phone app during a step. It can start a transition and
   muddy the result. Between steps is fine.
3. Check everything is healthy:

       ~/couch/tools/fault-rig status

   You want to see `couchd: active`, `pad-home: active`, `nothing staged`,
   `game pids: 0`, `decoys: none`.

If you want to read what each test is for first:

    ~/couch/tools/fault-rig list

## Part 1: the six that need no game (about 6 minutes)

Each one prints its own verdict at the end. `VERDICT: couchd would have
repaired it` is a pass. Anything else, tell Claude the step number.

### Step 1. The pad routing goes wrong (20 seconds)

    ~/couch/tools/fault-rig inject joystick-drift --i-am-present

We tell Kodi the wrong thing about who owns the controller, which is what
happens after a Kodi crash restart.

On the TV: nothing. This one is invisible.
You should see the verdict within about 12 seconds.

### Step 2. A paused game that is not there (20 seconds)

    ~/couch/tools/fault-rig inject stale-suspended-flag --i-am-present

We leave behind the note that says "a game is paused" when nothing is.

On the TV: nothing. The phone might briefly show a paused game with a made up
name. It clears itself.

### Step 3. A game session with nobody driving it (about 1 minute)

    ~/couch/tools/fault-rig inject orphaned-session --i-am-present

We leave behind the note that says "a game is running", pointing at a program
that does not exist. This is the state you get when a launcher is killed.

On the TV: nothing.
This one is slow on purpose. The system waits 30 seconds before deciding a new
session is dead, so the verdict takes about 35 to 45 seconds. That wait is
correct behaviour, not a hang.

### Step 4. A frozen thing nobody paused (30 seconds)

    ~/couch/tools/fault-rig inject lost-thaw --i-am-present

We start a harmless stand in process that looks like a game, freeze it, and do
not write the paused note. The real thing this copies is a pause that half
happened.

On the TV: nothing. No real game is touched.

### Step 5. A paused game left on screen (30 seconds)

    ~/couch/tools/fault-rig inject frozen-game-visible --i-am-present

**This is the only step you will see.** A grey box appears over Kodi saying
FAULT-RIG DECOY. That is ours. It is not a game and Kodi has not crashed. It
disappears on its own at the end of the step.

### Step 6. An innocent bystander (30 seconds)

    ~/couch/tools/fault-rig inject bystander-process --i-am-present

The opposite test. We start a harmless process with a name that looks like a
Steam game, and check couchd does **not** grab it. This is the bug that used to
freeze random things.

On the TV: nothing. The phone may claim a game is running for a few seconds.
That is the old code being fooled, and it is part of what this step shows.

## Part 2: the two that need a real game (about 5 minutes)

Pick something offline and cheap to reload. Not an online game, freezing one
drops the connection.

### Step 7. Start a game

Launch it however you like, phone or a Kodi tile. Let it get to a menu.
Then check the rig can see it:

    ~/couch/tools/fault-rig status

`game pids` should be more than 0.

### Step 8. The real game, frozen with no paused note (30 seconds)

    ~/couch/tools/fault-rig inject lost-thaw --live --i-am-present

On the TV: the game freezes and the sound stops, exactly like a pause. It
unfreezes at the end of the step, about 20 to 30 seconds later.

If it is still frozen after that, run the restore line at the top of this page.

### Step 9. Steam quietly taking the controller (about 1 minute)

    ~/couch/tools/fault-rig inject menu-capture --i-am-present

This one needs your thumb. After you type it, the rig waits and says
`waiting for your PS hold`.

**Now press and hold the PS button** to send the game to sleep and land on
Kodi, like normal. The moment you land, the rig opens Steam's own menu behind
the scenes.

On the TV: Steam's Big Picture menu flashes over Kodi and closes again within
a second or two. **That closing is the system working**, not a fault.

This step is different from the others: both the old system and couchd answer
it, so what we are checking is that they agree, not who was faster.

### Step 10. Put the game away

    game-launch quit

Kodi home screen, controller back on Kodi.

## When you are done

    ~/couch/tools/fault-rig status

You want `nothing staged`, `pad-home: active`, `decoys: none`, and both flag
lines saying `None`. If any of that is off, run the restore line at the top.

Then tell Claude you are finished. The evidence is already written to
`~/couch/shadow/injections-<today>.jsonl` and Claude reads it from there.

## If something looks wrong

- Grey FAULT-RIG DECOY box still on screen: run the restore line.
- Game still frozen: run the restore line. If it is still frozen, PS tap to
  resume, or use the phone Screen tab.
- Controller does nothing: run the restore line. It always puts the controller
  watcher back, even if that was not what broke.
- Everything is confused: `systemctl --user restart pad-home couch`, then the
  restore line.
- Worst case, nothing here survives a reboot.

## Why the controller watcher goes away for a few seconds

Steps 1 to 5 stop the old controller service for the length of the step, so it
does not fix the fault before couchd has had a chance to notice it. During
those seconds the PS button does nothing. The rig always starts it again, from
three different places: at the end of the step, on its own timer, and again as
a final check whether or not anything else worked. If all three somehow failed,
`systemctl --user start pad-home` fixes it, and so does a reboot.
