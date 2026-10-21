# tally

Time logging by switching tasks, from Alfred. Type `t`, pick what you are doing, and the
clock follows: starting anything ends whatever was running, so there is no timer to remember.

```
t                        Resume review pr 212      today 0:25 · last 13:40–14:05    ← ↩ toggles back
                         Resume call with ola      today 0:30 · last 13:10–13:40
                         Resume mail               today 0:30 · last 09:40–10:10
                         Stop                      parser #lexer · 0:55 since 14:05
                         Today                     4:40 logged · ↩ shows the day
t parser                 Resume parser #lexer      today 2:40 · last 14:05–now
t write tests            Start write tests         ↩ from now
t mail 14:30             Resume mail               from 14:30 · ends parser #lexer at 14:30
t coffee -20m            Start coffee              from 14:40 · ends parser #lexer at 14:40
t @today                 Today                     4:40 logged · ↩ shows the day
t @week                  This week                 17:15 logged · ↩ shows the week
t bar                    Install the SwiftBar plugin   the running task in the menu bar
t st                     Stop                      parser #lexer · 0:55 since 14:05
t to                     Today                     4:40 logged · ↩ shows the day
```

## A day with tally

One Tuesday, every feature once. Each line is what you type, then what Alfred (or the menu bar)
says back. HYPER+] opens `t`, HYPER+[ opens `tw`.

```
08:55  t daily 9:00 standup ↩           Reminder set for daily 09:00: standup
09:00                                    STANDUP across the screen in Large Type; esc
09:00  HYPER+[ stand ↩                   standup #w from 09:00        tw adds #w by itself
09:20  t mail ↩                          mail from 09:20              starting ends standup
09:40  HYPER+[ parser ↩                  parser #w from 09:40
10:05  t ↩                               mail from 10:05              the previous task is on top:
10:15  t ↩                               parser #w from 10:15         t ↩ toggles the two
10:30  the stop hotkey                   parser #w · 0:15             off for coffee
```

Nothing runs now, and from here the menu bar (with SwiftBar) counts the time nobody claimed:

```
10:45  menu bar                          15m unclaimed                grey
11:00                                    30m unclaimed                yellow, and a Tink
11:15                                    45m unclaimed                orange, and a notification:
                                         “45 min unclaimed since 10:30”; a click opens t
11:15  t                                 Unclaimed 0:45 since 10:30   on top of the usual list
       t review pr 212                   Start review pr 212          ↩ from now
                                         Start review pr 212 since 11:02   display on · 0:13
                                         Start review pr 212 since 10:30   whole gap · 0:45
       ↓ ↩                               review pr 212 from 11:02     you were reading it since
                                                                      the screen woke up
```

Nothing is lost if you never answer: 10:30–11:02 stays untracked, and tomorrow starts clean.

```
12:00  t 12:45 lunch ↩                   Reminder set for 12:45: lunch
12:45                                    LUNCH in Large Type
12:45  t ⌥↩                              review pr 212 · 1:43         ⌥↩ stops from any row
13:50  menu bar                          65m unclaimed                red since 13:45
       t lunch 30, hallway chat 25, review pr 212
                                         Claim since 12:45: lunch 12:45–13:15,
                                         hallway chat 13:15–13:40, review pr 212 from 13:40
       ↩                                 lunch from 12:45, hallway chat from 13:15,
                                         review pr 212 from 13:40     the last part keeps running
14:00  t every 45m drink water until 18:00 ↩
                                         Reminder set for every 45 min: drink water
14:20  HYPER+[ parser 14:05              Resume parser #w             from 14:05 · ends review pr
       ↩                                 parser #w from 14:05         212 at 14:05 (a backfill)
14:35                                    “Still on parser #w · 0:30? Ignore to keep it.”
                                         a nudge (after t nudge ↩); ignoring it confirms
14:45                                    DRINK WATER in Large Type
14:50  t @re drink ⌥↩                    Skipping 15:30: drink water  the next one only
16:00  t hall ↓ ⌃↩  #w ↩                 Add #w · 1 block             the chat was work after all
16:05  t lunch ⌘↩ ↩                      Delete 1 block · 0:30        lunch is not work…
16:06  t un ↩                            Undone: Delete 1 block · 0:30   …but keep it anyway
16:30  t coffee -20m                     Start coffee                 from 16:10 · ends parser #w
                                                                      at 16:10; esc, not today
17:30  HYPER+[                           Today · 7:58 logged · #work 4:50
       t @today ↩                        the ribbon, totals by tag, every block
18:00  t st ↩                            parser #w · 3:55
```

And on Friday afternoon:

```
t @week ↩  t @lastweek ↩  t @month ↩     one ribbon line per day, totals, by tag
t @yesterday ⌃↩  #w ↩                    tag every block of a day
t parser ⌃↩  ↓ 09:40–10:05 ↩  end 10:00 ↩
                                         End parser at 10:00 instead of 10:05: one block
t @re standup ⌃↩                         daily 9:00 standup comes back into t:
       weekdays 9:15 standup ↩           Replaced with weekdays 09:15: standup
t @re drink ⇧↩                           Stopped 1 reminder: drink water
t @                                      every @word: @today, @week, @reminders…
t nu ↩                                   Nudges off
t ba ↩                                   SwiftBar plugin installed · …/tally.30s.sh
```

## Work

HYPER+[ (or the keyword `tw`) opens the same list for work only:

- the bare list shows only tasks tagged `#w` (or `#work`, or however **Tag aliases** spells it),
  and the Today row adds the work share, `6:00 logged · #work 2:30`;
- whatever you start gets `#w` added unless it already carries it, so `parser` becomes
  `parser #w`, and `parser` resumes `parser #w` if that exists;
- typed matches are work tasks only; backfill, ⇧↩, ⌥↩ and the command words work as in `t`.

HYPER+] (`t`) is unchanged: everything, no tag added. **Work tag** in the settings is `w`;
set it to `job` and HYPER+[ is about `#job`.

## Removing old entries

**⌘↩** on a task row (or Stop, or a day row) opens its edit list with `delete` already typed:
the row says what goes (`Delete 2 blocks · 2:40 · every block of parser becomes untracked`)
and ↩ there removes it, so a stray ⌘↩ removes nothing. Typing `delete` in any edit list does
the same: for one block, a whole task, or a whole day. `t undo` brings it back.

## Editing and tagging afterwards

Find the task the usual way, by typing in `t` or `tw` or among the recent ones, and press
**⌃↩** on it instead of ↩: its edit list opens and its time is left alone. **⌃↩ on Stop**
edits the running task. What you type there is the edit, and the row says what it will do
before you press ↩:

```
#w                Add #w · 2 blocks                every block of parser #lexer · 2 blocks, 2:40
#w -#lexer        Add #w, remove #lexer · 2 blocks
lexing #lexer     Rename 2 blocks to lexing #lexer
```

Below the hints, the task's newest blocks are listed (`14:05–now · 0:55`). ↩ on one opens that
block's own edit list, which also moves its time or deletes it:

```
#w                Add #w · 1 block                 parser #lexer · 11:05
start 11:30       Start parser at 11:30 instead of 11:05   untracked before it
start 10:30       Start parser at 10:30 instead of 11:05   takes from untracked time
end 13:30         End call at 13:30 instead of 13:40       untracked 13:30–13:40, then review
end 13:50         End call at 13:50 instead of 13:40       review now starts at 13:50
delete            Delete review                    13:40–14:05 becomes untracked
lexing            Rename 1 block to lexing
```

With nothing typed, these show as hints; ⇥ fills one in. An edit that cannot be done (a start
before the previous block, an end past the next one, a time that has not happened) is one row
saying why. **⌃↩ on the Today row** (or Yesterday, or a date) tags every block that day.

**`t undo`** shows the last edit and ↩ takes it back; again for the one before. Tags follow
**Tag aliases**, so adding `#w` to `parser #work` changes nothing, and `-#work` removes `#w`.
Moving a block's start earlier than when it was logged marks it backfilled on the ribbon.

## Stopping

Three ways, fastest first:

- **The stop hotkey.** The workflow has a second hotkey object that stops the running task
  without opening Alfred; a notification says what stopped and for how long. Alfred clears
  hotkeys on import, so double-click it and give it a key (HYPER+S, say).
- **⌥↩ on any task row.** `t` then ⌥↩ stops whatever runs; the subtitle says what and for how
  long before you press it.
- **`t st` ↩.** Typing a command word puts it on top (see below).

## Reminders

A time as the **first** word makes a reminder instead of a task:

```
t +15m stop the work      Remind 15:15: stop the work      in 15 min · in big letters then
t 21:00 stand up          Remind 21:00: stand up           in 6:00
t 9PM go out              Remind 21:00: go out
t 9:00 standup            Remind tomorrow 09:00: standup   (9:00 has passed today)
```

`+15`, `+15m`, `+15 m`, `+15 min` (all fifteen minutes), `+2h`, `+2 hours`, `+1h30m`, `+1 hour 30 min`,
`+30s`, `+30 sec`, `+1m30s` count from now; a bare number is minutes. Without seconds a reminder
lands on the minute and survives sleep; with seconds it is a countdown to the second, which
launchd can miss if the Mac sleeps through it; `21:00`, `9pm`, `9:30PM` are today, or tomorrow when
already past. At that minute Alfred shows the text in Large Type across the screen; with the
SwiftBar plugin a clickable notification stays behind too. If the Mac sleeps through it, it
shows on wake.

### Repeating

A repeat word with a time after it makes a repeating reminder; without the time it is still a
task (`t daily standup` starts one):

```
t daily 9:00 standup                 Remind daily 09:00: standup
t weekdays 18:30 stop the work       Remind weekdays 18:30: stop the work
t weekends 10:00 call mum
t mon,thu 19:00 gym                  also mon+thu, mon thu, monday, wed
t every 45m drink water              every 2h, every 90 min, every 90, every 30s
t every 45m drink water until 18:00  until a time, a day (fri) or a date (2026-11-30)
```

`until` means the nearest coming one: `until 18:00` is today's if still ahead, else tomorrow's;
`until fri` is the end of the coming Friday. Without it a repeat runs until stopped. Daily and
weekday repeats fire on the clock and catch up on wake; `every` counts from when it was set,
round the clock, and skips what falls in sleep.

### The list and its keys

`@reminders` (from `@re`) lists every pending reminder, next first; words after it narrow the
list. Bare `t` lists one-shot reminders and repeats due within the hour. Bare `@` lists every
@word. The SwiftBar menu has a Reminders submenu, and clicking a reminder's notification or a
menu entry opens `@reminders` with it on top. On a ⏰ row:

| Key | Does |
| --- | --- |
| ↩   | show it now in Large Type, a test; the schedule is untouched |
| ⌥↩  | cancel it; for a repeat, skip only the next firing |
| ⇧↩  | stop every pending reminder with this text |
| ⌃↩  | edit: what you typed comes back into `t`, and ↩ on the Replace row swaps it in |

A time **last** is still a backfill (`t standup 9:30`), so a time in the future there says to put
it first. Underneath, each reminder is a row in the database and a launchd agent
(`~/Library/LaunchAgents/com.anokhin.tally.remind.<id>.plist`) that asks Alfred to run the
workflow's `remind` trigger: once, on its calendar, or every so long. It removes itself when a
one-shot fires, when a repeat ends, and when either is cancelled.

## Nudges

`t nudge` ↩ turns them on: every 15 minutes between 09:00 and 19:00 on weekdays, a
notification says what tally thinks you are doing.

```
Still on parser #lexer · 0:42? Ignore to keep it.
Nothing running since 13:40. Ignore if you're away.
Nothing logged today. Type t to start.
```

With the SwiftBar plugin, the gap nudge (`Nothing running since…`) gives way to the unclaimed
counter below; the `Still on…?` nudge stays.

With the SwiftBar plugin installed (`t bar`), nudges come from SwiftBar and are clickable: a
click opens `t` with the running task typed in, so its row is on top with ⌥↩ to stop it, and
for a gap it opens the bare list with the previous task first. SwiftBar asks once for
permission to post notifications. Without the plugin, nudges come from Alfred and a click does
nothing.

Ignoring a nudge is the confirmation: nothing is written, the task keeps running or the gap
stays a gap. Anything else is a switch, done the usual way in `t`. A nudge is skipped when you
switched less than an interval ago, when the Mac has had no key press or mouse move for an
interval (nobody to read it; the next one comes when you are back), and outside the hours.

**Nudge every**, **Nudge between** and **Weekends** in the workflow settings change that; `0`
turns them off. Type `t nudge` twice after changing the interval, once off and once on, so
launchd picks it up. Underneath, a launchd agent (`~/Library/LaunchAgents/com.anokhin.tally.nudge.plist`)
asks Alfred to run the workflow's `nudge` trigger, so the check uses the workflow's settings and
the notification is Alfred's. The first time, macOS asks whether `osascript` may control Alfred;
say yes.

## Unclaimed time

Time with nothing running, within **Nudge between** (and on weekends only with **Weekends**), is
*unclaimed*: from today's last stop, or from the start of the hours if that is later. It is only
empty time. Nothing is lost, the ribbon and the totals are unchanged, and nothing carries over
to the next day. A running task is never stopped for you.

**In `t`** (no SwiftBar needed), once the gap reaches the first step of **Unclaimed ladder**
(15 min):

```
t                       Unclaimed 0:30 since 10:30       type what you are doing
t api-design            Start api-design                 ↩ from now
                        Start api-design since 10:42     display on · 0:18
                        Start api-design since 10:30     whole gap · 0:30
```

↩ always means *from now* on the top row; the rows under it claim back. *Display on* is the last
time the screen woke inside the gap (from `pmset -g log`, read only when you type and kept for a
minute); it is left out when there is none. ⇧↩ on any resume row is the whole gap too.

**A split** claims the gap for several things: parts by comma, each but the last with a length
(`30`, `30m`, `1h`, `1h30m`), filled in order from the start of the gap; the last part has no
length and keeps running, so `review pr 212` there is a name, not 212 minutes:

```
t standup 30, api-design        Claim since 10:30: standup 10:30–11:00, api-design from 11:00
t standup 1h, api-design        1:00 of parts is more than the 0:40 gap
```

In `tw` every part gets the work tag. With a task running there is no gap, and a split says so.
A comma in `t` always means a split.

**In the menu bar** (with SwiftBar), the counter shows only while nothing runs and climbs the
ladder, `15,30,45,60` by default:

| From   | Menu bar                  | And                                            |
| ------ | ------------------------- | ---------------------------------------------- |
| 15 min | `15m unclaimed`, grey     |                                                |
| 30 min | yellow                    | a Tink (**Unclaimed sounds** turns it off)     |
| 45 min | orange                    | a notification: `45 min unclaimed since 10:30` |
| 60 min | red, until claimed        | the notification once more                     |

A click on the notification, or on *Claim…* at the top of the menu, opens `t` with the gap on
top. When you are away (no key or mouse for a nudge interval) there is no sound and no
notification, and the counter keeps counting. Each step rings once per gap; the next gap starts
the ladder again. Run `t bar` again after changing the ladder or the hours, since the plugin
carries the settings.

## Command words

The first two letters of a command's name put its row above everything else, so `t st`,
`t to`, `t yes`, `t we`, `t la` and `t mo` reach Stop, Today, Yesterday, This week, Last week
and Last month, `t ba` the SwiftBar plugin, `t nu` the nudges and `t un` undo. `@re` lists reminders. The Start row for what you typed and the
matching tasks stay below, so typing on to `t standup` still finds it. With a leading `@`
(`@today`, `@week`) only the views are listed.

A block is the time between one transition and the next. The database holds transitions only
(`at`, `line`, `logged_at`); blocks, gaps, tallies and the ribbon are all read from that, so
nothing stored can disagree with anything else.

## Install

1. Build `dist/tally.alfredworkflow` with `make build` (or take it from Releases) and
   double-click it.
2. Optional: **Database folder**, if you want `tally.db` somewhere you can see. Empty means
   Alfred's data folder for the workflow, which survives updates.
3. Optional: **Tag aliases**, `w=work` by default: short tags and what they stand for, so
   `#w` counts as `#work`. Add more with commas, `w=work, l=lexer`.
4. Optional: **Day starts at**. With `04:00`, work at one in the morning belongs to the evening
   before. Every tally is recomputed from this, so changing it changes history too.
5. Optional: **Unclaimed ladder** (`15,30,45,60`: the minutes at which the counter shows,
   chimes, notifies and turns red; the first is also when `t` offers to claim) and
   **Unclaimed sounds**.
6. The hotkey objects are wired for HYPER+] (⌃⌥⇧⌘]) to open `t`, HYPER+[ to open `tw`, and
   nothing yet to stop. Alfred clears hotkeys on import, so double-click each once and press the
   combination you want.

## Requirements

| Needs                                         | For                                         |
| --------------------------------------------- | ------------------------------------------- |
| [Alfred 5](https://www.alfredapp.com) with the Powerpack | everything: workflows need the Powerpack |
| macOS's own `/usr/bin/python3` (3.9+)         | everything; it comes with the Command Line Tools, nothing else is installed |
| [SwiftBar](https://github.com/swiftbar/SwiftBar), optional (`brew install swiftbar`) | the running task in the menu bar, `t bar`, clickable nudges, the unclaimed counter and its ladder |

SwiftBar is the only optional piece, and nothing else depends on it. Without it, `t`, backfill,
stop, the views, reminders and claiming unclaimed time in `t` work the same, and gaps get the
plain `Nothing running since…` nudge; `t bar` says SwiftBar was not found instead of installing, and
starting or stopping a task never tries to reach it.

## The list

Bare `t` shows the previous task first, so `t ↩` goes back to it and `t ↩` again returns: two
tasks toggle with three keystrokes. Below it, the other tasks of the last seven days, newest
start first, at most seven; then **Stop**, which says what is running and for how long; then
**Today**, whose subtitle is the day's tally and whose ↩ opens the ribbon.

Typing replaces the list: the first row starts what you typed (**Start**) or resumes it when a
task with that line exists (**Resume**, with the line as it was first written); the rows below
are every past task matching by word prefix, newest start first, each ↩ resuming it verbatim.

| Key  | On a task row                                                                       |
| ---- | ----------------------------------------------------------------------------------- |
| ↩    | start now                                                                           |
| ⇧↩   | start where today's gap began (the last stop, or the start of the hours), filling it |
| ⌥↩   | stop the running task                                                               |
| ⌘C   | copy the line                                                                       |
| ⌘L   | large type                                                                          |

The task that is running is never restarted by picking it again: typed or found, its row reads
`parser #lexer is running · 0:55 since 14:05` and ↩ leaves it running, so its time keeps
counting from when it began. ⌥↩ on that row stops it and ⌃↩ edits it.

A start that changes nothing is not kept: the same task again right after itself (one block,
not two), switches undone within the same minute (no 0:00 blocks), a stop after a stop. Any
start, stop or edit tidies these away, older ones included.

Two tasks are the same task when their lines are the same after folding case, diacritics and
spacing. `parser #lexer` and `parser` are two tasks. A `#tag` anywhere in the line groups the
ribbon and nothing else.

## Backfill

A span back in time may come first or last: `-10m mail`, `-10 min mail`, `-10 mail`, `mail -20m`,
`mail -1 hour 20 min`; a clock time comes last: `mail 14:05` (first, a clock time is a reminder).
The block starts then instead of now, and the row's subtitle says what that does before you
press ↩:

- later than the running task started: `from 14:30 · ends parser at 14:30`
- earlier than it started: `11:30–14:05, before parser (which keeps running) · cuts call at 11:30`,
  a past block is inserted and the running task is untouched

A time in the future, or a time with no words before it, is one row that explains why it cannot
act.

## The day

`t @today`, `t @yesterday` or `t 2026-10-19` and ↩ open a Text View:

```
today · Tue 20 Oct · 4:40 logged

06      08      10      12      14      16      18      20
·············▓▓▞▞░░░░███████░▒▒▙▙███▶···························

█ #lexer          2:40
▓ #team           0:35
▒ call with ola   0:30
▞ mail            0:30
▙ review pr 212   0:25
░ untracked       1:15

09:05–09:40   0:35  standup #team
09:40–10:10   0:30  mail
11:05–12:50   1:45  parser #lexer
13:10–13:40   0:30  call with ola
13:40–14:05   0:25  review pr 212
14:05–now     0:55  parser #lexer
```

One cell is fifteen minutes; 06 to 22 is shown and widened when a block falls outside. Glyphs
go by rank of the day's totals, so the biggest group is always `█`. `░` is time between blocks
that nothing claims, `▶` is now, and `▚` marks a block logged more than ten minutes after it
started. Today's view refreshes every minute. ↩ copies the text.

### By tag

When any block that day has a tag, the view adds the time under each tag, a block counting
fully for every tag it carries (so the sum can be more than the day), and the untagged time
last:

```
by tag

#work       4:10
#lexer      2:40
#team       0:35
untagged    0:30
```

Short tags from **Tag aliases** are spelled out before anything is counted: with `w=work`,
`mail #w`, `review #W` and `parser #work` are all `#work`, on the ribbon, in the totals and in
this table. The block list keeps the lines as you typed them. Aliases are applied when reading,
so adding one regroups history too. They also make `parser #w` and `parser #work` one task for
resuming: typing either finds the other.

## The week and the month

`t @week`, `t @lastweek`, `t @month` or `t @lastmonth` open the same view with one line per day
up to today, the hours shared across the lines, and the totals over the range:

```
this week · 19 Oct – 25 Oct · 17:15 logged

        06      08      10      12      14      16      18      20      22
Mon 19  ················▓▓▓▓▓▓▓▓██████████████████████████████████████████████··  13:30
Tue 20  ·············▒▒▓▓░░░░███████░░░░░███▶···································   3:45

█ #lexer     14:10
▓ mail        2:30
▒ #team       0:35
░ untracked   2:10
```

Untracked time is counted inside each day, never across nights. A week runs Monday to Sunday.
The by-tag table follows the totals, over the whole range.

## The menu bar (optional, needs SwiftBar)

With [SwiftBar](https://github.com/swiftbar/SwiftBar) installed, `t bar` ↩ writes a plugin into
its plugin folder (read from SwiftBar's own settings, or from **SwiftBar plugins** if that
fails). The menu bar then shows the running task and its time, `parser #lexer 1:42`, or
the unclaimed counter (`30m unclaimed`) or `tally` when nothing runs, refreshed every thirty seconds and the moment you start or stop
anything from Alfred. Its menu is the bare `t` list: Stop, the recent tasks (click resumes),
Today, Open Tally, and at the bottom SwiftBar's own submenu for its preferences, refresh and
quit.

The plugin is one shell script that runs the workflow's own `tally bar`, so it needs nothing
else; run `t bar` again after moving the workflow or changing a setting. To remove it, delete
`tally.30s.sh` from SwiftBar's plugin folder, or quit SwiftBar: tally does not notice either.

## From a terminal

The same commands, the same data:

```
export alfred_workflow_data="$HOME/Library/Application Support/Alfred/Workflow Data/com.anokhin.tally"
uv run tally filter "par" | jq '.items[].title'
uv run tally act start "parser #lexer"
at=2026-10-20T14:05 uv run tally act start "parser #lexer"
uv run tally act stop
uv run tally act claim "standup 30, api-design"
uv run tally today            # or today @yesterday, today @week, today 2026-10-19
```

Set `db_path` or `alfred_workflow_data` as above so the terminal and Alfred share one database;
without either, the CLI uses `~/.local/share/hoard/tally`, a separate copy.

## Development

```
uv sync
uv run pytest
uv run --isolated --python 3.9 pytest    the interpreter the workflow runs on
make lint                                ruff, mypy
make check                               build, import from the bundle, smoke it
```

`NOTES.md` lists what is deliberately not here yet and where it would go.
