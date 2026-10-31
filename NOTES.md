# Notes

## What is here

Small modules, each with one job, on `hoard.alfred` (folding, word-prefix matching, the
data folder) and nothing of the kernel.

| Module      | Owns                                                                  | Grows when                            |
| ----------- | --------------------------------------------------------------------- | ------------------------------------- |
| `store`     | the table of transitions; blocks, running, tasks, spelling            | a transition gets a column, a new read |
| `days`      | when a day starts, which day a moment is, the `@today`/`@week` words  | a new rule word                       |
| `durations` | spans as typed (`+15`, `-10 min`, `+1h30m`, `+30s`), first or last words; `h:mm` | a new unit |
| `timewords` | the last word of a line as a time                                     | a new way to say when                 |
| `commands`  | words that name a command (stop, today, week, bar…) and their prefixes | a new command word                   |
| `tags`      | tags in a line, aliases from the setting, time under each tag          | a tag gets a meaning beyond grouping  |
| `nudge`     | when to nudge and what to say, the launchd agent, how long the user has been idle | a new reason to stay quiet |
| `gaps`      | unclaimed time: the gap, the ladder and its level, display-on from `pmset`, splits | a new way to guess when a gap ended |
| `scope`     | which tasks a list is about (all, or one tag), adding that tag, task identity across aliases | a list scoped by more than one tag |
| `journal`   | edits as batches of ops on transitions, each batch's before-image, undo | a new kind of op |
| `edits`     | what text typed in the edit list means for a block, a task or a day; refusals | a new edit word |
| `editrows`  | the edit list's rows: hints, the planned change, the refusal | the edit list shows something new |
| `repeats`   | a reminder's repeat rule: read, next firing, wording, launchd schedule, `until` | a new kind of repeat |
| `remind`    | reading a reminder's time, the reminders table, one launchd agent per reminder | a repeating reminder |
| `present`   | Alfred rows: bare list, typed list, subtitles, the effect of a backfill | a row gets a key, a new row appears  |
| `ribbon`    | a day as cells, a range as a line per day, groups, totals, the list   | the view shows something new          |
| `view`      | the Text View JSON and its rerun                                      | a second view                         |
| `bar`       | the SwiftBar plugin: status line, unclaimed counter and its alerts, menu, the poke after a change | the menu gets a line |
| `cli`       | subcommands, settings, the database path                              | a new subcommand, a new setting       |

The canvas is `workflow/info.plist`: hotkey → script filter `t` → a conditional on `action`
(`view` to the Text View, else to `tally act "$action" "$1"`) → a notification with the
action's one line. ⇧↩ and ⌥↩ take the same path, carrying their own `action`. A second hotkey
goes straight to `tally act stop` and the same notification. The Text View runs the `view` script at the bundle root and ↩ copies its
text. A new action is a `variables.action` value in `present` and an entry in `cli.ACTIONS`; the
plist changes only when the action needs an Alfred object. `tests/test_workflow.py` cross-checks
the plist against the package, so a mismatch fails before Alfred sees it.

The menu bar is SwiftBar's, not ours: `bar.install` writes `tally.30s.sh` into SwiftBar's plugin
folder with the bundle path and the settings baked in, and that script either prints the menu
(`tally bar`) or acts (`start`, `stop`, `open`) when SwiftBar calls it with arguments, so every
click is one process and no state lives outside the database. `start` and `stop` from Alfred
poke SwiftBar through its URL scheme when the plugin exists. A status item of our own (forty
lines of Swift compiled into the data folder, as `hoard.alfred.apple` does) is the no-dependency
version; `bar.status` would be its one call.

Rows are a `TypedDict` like wisp's rather than hoard's `Item`, because they carry `action` and
`at` and `Item` carries one `verb`.

## The model

A transition is `(at, line, logged_at)`; an empty line is a stop. A block is a transition and the
`at` of the next one, so starting anything ends what was running by construction and no end is
ever stored. `logged_at` is when the transition was typed; a block whose `at` is more than ten
minutes before it is *backfilled* and the ribbon says so.

Times are local naive ISO strings to the minute. Changing time zone makes that day's blocks look
shifted and nothing else; a `tz` column is an additive migration if it ever matters.

`day_starts` is applied when reading, never when writing, so changing it recomputes every day.

A backfilled start is one insert. Later than the running task started, it ends it there. Earlier,
it becomes a past block: whatever ran at that time is cut there and the block ends at the next
transition, which is why the running task keeps running and `Now` does not move. The row's
subtitle spells this out before ↩.

## Nudges

A launchd agent with `StartInterval` runs `osascript` to ask Alfred for the external trigger
`nudge`, which runs `tally nudge` and posts whatever it prints through the canvas's
notification object. Going through Alfred rather than running the bundle from launchd keeps
the settings in one place and survives the bundle moving on reinstall. Ignoring a nudge writes
nothing: confirmation is the absence of a switch. Quiet when the last transition is younger than
the interval, when `ioreg`'s `HIDIdleTime` is longer than it, outside the hours, and at weekends
unless asked. With the SwiftBar plugin installed, `tally nudge` prints nothing and posts through
`swiftbar://notify` instead, with `href` set to `alfred://runtrigger/com.anokhin.tally/open/`
and the running task as the argument; the `open` external trigger (URL handler on) feeds `t`.
The href is one more layer of URL encoding inside the notify URL, so SwiftBar's decoding
hands Alfred its own link intact. Alfred's notifications do nothing on click, which is why
they stay the fallback only.

## Unclaimed time

A gap is not stored: `gaps.find` reads it from the transitions, the nudge hours and now, so
there is nothing to clean up and nothing carries over a night (the gap opens with the hours,
not at yesterday's stop). `gaps` imports only `durations` and `store`; `h:mm` moved to
`durations` so `nudge` no longer imports `present`, which closed an import cycle
(`nudge → present → remind → nudge`).

In `t`, `cli.claim` builds a `gaps.Claim`: the gap, the first step of the ladder as threshold,
and `woke`, a function that reads the power log. Only `claim_rows` calls it, so bare `t` and
every row without a typed task never spawn `pmset`; the lines are cached for a minute in the
workflow's cache folder so each keystroke does not. The display-on row is the last
`Display is turned on` strictly inside the gap, to the minute; nothing cleverer, on purpose.

A split is `gaps.split` (a comma, parts, the last part all line) and `gaps.fill` (starts from
the gap's start, or one problem). The row and `act claim` both run them, so they cannot
disagree; `act claim` records each start with `logged_at` now and the last one keeps running.

The menu bar's ladder is `bar.alert`, run by `tally bar` every 30 s before the menu prints. It
keeps the highest step each gap has rung in a one-row table, `ladder(start, level)`, so a step
rings once however often the plugin runs, a jump straight to red rings only the notification,
and a new gap (another start) clears it. Away (`HIDIdleTime` over the nudge interval) the step
is still recorded, so coming back does not set off an old alarm. The chime is `afplay` on
`Tink.aiff` through `Popen`, so the menu does not wait for it. With the plugin installed,
`tally nudge` says nothing for a gap: the counter has it.

## Editing

The model is still transitions only. An edit is a batch of three kinds of op on them (update
`at` or `line`, insert, delete), and before each op the row as it was goes into `before`
under the batch, an insert noting the new id; undo replays a batch's `before` backwards and
marks it undone. A block is edited through its own transition and the next: its start is its
`at`, its end is the next one's. Moving an end earlier inserts a stop unless a stop is next
(then the stop moves); later moves the next transition and so shortens what follows. Deleting
turns the block's transition into a stop, or removes it when a stop is already before it. The
edit list and `act apply` plan the same typed text with `edits.plan`, so the row and the act
cannot disagree; the target travels as the `target` variable (`block:<id>`, `task:<line>`,
`day:<date>`). Editing starts from ⌃↩ on any task row (and on Stop and the day rows); ⌘↩
opens the same list with `delete` as its argument, which Alfred types into the list; a task's edit list lists its
newest blocks under the hints, which is the only way to a single block. There is no `edit`
command word: it is too common in task names. Existing databases get the two new tables on the next connect.

## Reminders

A first word that is a time to come (`+15m`, `21:00`, `9pm`) makes the list a single reminder
row; a last word that is a time is a backfill, as before, so the two never compete. `act
remember` re-reads the typed text, stores a row in `reminders` (created on first use) and
writes a launchd agent with `StartCalendarInterval` at that month, day, hour and minute;
launchd runs calendar jobs missed during sleep on wake. The agent runs `osascript` to fire the
`remind` external trigger with the id, the workflow's `tally remind` prints the text into the
Large Type object (and SwiftBar's notify when the plugin is there), marks it shown, and boots
the agent out and deletes its plist. Without a year in the calendar interval a stale agent
would fire again a year later; firing and cancelling both remove it, which is why both go
through `remind.unschedule`. A reminder with seconds gets `StartInterval` (a countdown from
when it was set) instead, since the calendar has no seconds; launchd misses an interval that
falls in sleep, which is the price of the second. The Large Type object's config keys are from memory; if Alfred
shows `{query}` literally, double-click the object and set its text to `{query}`.

## Redundant transitions

`store.redundant` is the one rule for what changes nothing: of transitions sharing a minute
only the last counts, a transition repeating the task before it (or a stop after a stop, or a
stop before anything) is dropped. `store.record` deletes them after each insert; `journal.apply`
deletes them inside its batch, so undo brings them back with the rest. The rule only ever
compares a transition with its neighbours, so both look at `store.neighbours`, a few
transitions either side of the moment written (opening on a task, so a stop in the window
has its predecessor), instead of the whole table: a write costs the same in year ten as on
day one. Old untidy data is tidied by the next write near it, not by any write.

## Repeating reminders

A reminder row keeps `rule` (`daily`, `days:0,3`, `every:2700`, empty for once), `until`,
`typed` (what was typed, for ⌃↩) and `skip`; old databases get the columns on connect. A
repeat's agent never changes: launchd's calendar (`Weekday` 0 is Sunday) or `StartInterval`.
What changes is the row: `remind.fire` decides at each firing whether to show (not when
skipped), moves `at` to the next firing after now (so a firing caught up on wake does not
replay the missed ones), and ends the series once `until` is reached. ↩ on a ⏰ row goes from
the action conditional straight to Large Type with the text as its argument, so a preview
never touches the database. ⌃↩ goes back into `t` with the typed text as its argument and
`replace` as a variable; `remember` finishes the old reminder before adding the new one.

## Deliberately not here

- **Guessing more about a gap.** Activity sampling, idle-based stops, "lost time" totals, carrying
  a gap into the next day. The gap is empty time and the person decides what it was.

- **Undo of starts and stops.** `t undo` takes back edits; a start or stop from the list is
  one insert and is not journaled. ⌃↩ on the task, then `delete` on the block, is the way back.
- **Range insert.** `t parser 14:05-14:40` is two transitions, the second a copy of whatever ran
  at 14:40, so a block in the middle of another splits it. It is the first change with more than
  one row; `journal` is where it would go.
- **Day-end cap.** `t @yesterday` noticing a block that ran all night and offering a stop at a
  setting or at the time the Mac slept (`pmset -g log`). A plan row: describe, act on ↩.
- **Ranges of your own.** `@week` and `@month` (and their `last`) are the only ranges; `2026-10`
  or `2026-10-12..2026-10-18` would be two more lines in `days.asked`, and `range_label` would
  need to say a date range instead of this/last.
- **Pull from wisp.** A setting pointing at the log folder, and `t` listing open `.` tasks as
  start rows. One read of that folder; `wisp.records.read_folder` is the reader.
- **Icons per block.** A disc with the block drawn as a sector on a 24-hour face, cached by
  `(start, end, colour)` in the cache folder, as the row icon. wisp's `icons.py` draws PNGs
  with the standard library.
- **Export.** One CSV per month into a folder, for `grep` and backup. `store.transitions` over a
  window and `csv.writer`.
- **Sync.** The database is for one machine. A log that is append-only per machine, merged on
  read, is the honest multi-machine version; a database in Syncthing is not.
- **A model.** Nothing here needs one.
