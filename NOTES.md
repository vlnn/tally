# Notes

## What is here

Six small modules, each with one job, on `hoard.alfred` (folding, word-prefix matching, the
data folder) and nothing of the kernel.

| Module      | Owns                                                                  | Grows when                            |
| ----------- | --------------------------------------------------------------------- | ------------------------------------- |
| `store`     | the table of transitions; blocks, running, tasks, spelling            | a transition gets a column, a new read |
| `days`      | when a day starts, which day a moment is, the `@today` rule words     | a new rule word                       |
| `timewords` | the last word of a line as a time                                     | a new way to say when                 |
| `present`   | Alfred rows: bare list, typed list, subtitles, the effect of a backfill | a row gets a key, a new row appears  |
| `ribbon`    | the day as cells, groups, totals, the block list                      | the view shows something new          |
| `view`      | the Text View JSON and its rerun                                      | a second view                         |
| `cli`       | subcommands, settings, the database path                              | a new subcommand, a new setting       |

The canvas is `workflow/info.plist`: hotkey → script filter `t` → a conditional on `action`
(`view` to the Text View, else to `tally act "$action" "$1"`) → a notification with the
action's one line. The Text View runs the `view` script at the bundle root and ↩ copies its
text. A new action is a `variables.action` value in `present` and an entry in `cli.ACTIONS`; the
plist changes only when the action needs an Alfred object. `tests/test_workflow.py` cross-checks
the plist against the package, so a mismatch fails before Alfred sees it.

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

## Deliberately not here

- **Undo.** Every change is one insert, and the first version has no way to take one back. When
  it comes: a `superseded` column pointing at the row that replaced it, every read filtered on
  `superseded is null`, a change as the set of rows it superseded, undo as clearing that column.
  The schema change is additive; `store.transitions` is the one query to touch.
- **Range insert.** `t parser 14:05-14:40` is two transitions, the second a copy of whatever ran
  at 14:40, so a block in the middle of another splits it. It is the first change with more than
  one row and the reason undo comes first.
- **Editing a block.** A keywordless menu on ⌘↩: *started* and *ended* retime this transition or
  the next one (an end is always someone else's start), *rename*, *trash*. wisp's `menu` script
  filter is the shape.
- **Day-end cap.** `t @yesterday` noticing a block that ran all night and offering a stop at a
  setting or at the time the Mac slept (`pmset -g log`). A plan row: describe, act on ↩.
- **Week and month.** `@week` and `@month` as seven or thirty ribbons stacked with a total per
  day, and the totals table over the range; `days.asked` returns a `Window`, so a range is a
  wider window and the ribbon's `scale` learns to label days. The tally the README mentions for
  yesterday, last week and last month lives here.
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
