# Notes

## What is here

Six small modules, each with one job, on `hoard.alfred` (folding, word-prefix matching, the
data folder) and nothing of the kernel.

| Module      | Owns                                                                  | Grows when                            |
| ----------- | --------------------------------------------------------------------- | ------------------------------------- |
| `store`     | the table of transitions; blocks, running, tasks, spelling            | a transition gets a column, a new read |
| `days`      | when a day starts, which day a moment is, the `@today`/`@week` words  | a new rule word                       |
| `timewords` | the last word of a line as a time                                     | a new way to say when                 |
| `commands`  | words that name a command (stop, today, week, bar…) and their prefixes | a new command word                   |
| `tags`      | tags in a line, aliases from the setting, time under each tag          | a tag gets a meaning beyond grouping  |
| `nudge`     | when to nudge and what to say, the launchd agent, how long the user has been idle | a new reason to stay quiet |
| `scope`     | which tasks a list is about (all, or one tag), adding that tag, task identity across aliases | a list scoped by more than one tag |
| `journal`   | edits as batches of ops on transitions, each batch's before-image, undo | a new kind of op |
| `edits`     | what text typed in the edit list means for a block, a task or a day; refusals | a new edit word |
| `editrows`  | the edit list's rows: hints, the planned change, the refusal | the edit list shows something new |
| `present`   | Alfred rows: bare list, typed list, subtitles, the effect of a backfill | a row gets a key, a new row appears  |
| `ribbon`    | a day as cells, a range as a line per day, groups, totals, the list   | the view shows something new          |
| `view`      | the Text View JSON and its rerun                                      | a second view                         |
| `bar`       | the SwiftBar plugin: status line, menu, where it goes, the poke after a change | the menu gets a line |
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
unless asked. A clickable nudge (click opens `t`) needs SwiftBar's notify URL or a helper app;
Alfred's notifications do nothing on click.

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
`day:<date>`). Existing databases get the two new tables on the next connect.

## Deliberately not here

- **Undo of starts and stops.** `t undo` takes back edits; a start or stop from the list is
  one insert and is not journaled. `t edit` and `delete` on the block is the way back.
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
