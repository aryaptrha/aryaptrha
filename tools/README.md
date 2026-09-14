# How the game compiles

The profile README is playable. There is no JavaScript in it, no GitHub Action
behind it, no server anywhere, and no token to expire. Tic-tac-toe was solved
ahead of time and **emitted as a filesystem**: every reachable position is its own
markdown page, and every legal move is an ordinary link to the page for the
position it produces. GitHub's file viewer is the whole runtime.

```
                     424 pages committed
      208 decision states  +  216 endings
      198 endings you lose · 18 draws · 0 wins
                     782 distinct games playable
```

## The encoding

A filename *is* a board: nine characters over `{x, o, _}`, read left-to-right and
top-to-bottom. `game/xo__x____.md` is

```
 x o ·
 · x ·
 · · ·
```

`_` rather than `-` for empty, so no filename ever starts with a dash.

Addressing pages by position instead of by path is what keeps the repo small.
Reached by move order, this game has 1,252 nodes; but a position arrived at by
`a1, c1, b2` is the same position as one arrived at by `b2, c1, a1`, and shares a
file. So it is a **game graph, not a game tree** — 424 pages instead of 1,252, a
third of the files for exactly the same game.

The encoding also lets both openings live in one flat directory without colliding.
At a page where the visitor is to move, `count(x) == count(o)` if the visitor
opened and `count(o) == count(x) + 1` if the bot did, so the two subtrees can
never claim the same filename. Endings shared by both openings correctly share
one page.

## Why every link is absolute

A repository README resolves relative links against
`/<user>/<repo>/blob/<branch>/`. A **profile** README is rendered at
`github.com/<user>`, where relative paths resolve against the profile root
instead — and 404. Relative links would have looked fine in the repo and broken
on the one page that matters.

So every URL is absolute, built from a single constant at the top of
`generate.py`:

```python
HANDLE = "your-handle"
BRANCH = "main"
```

**This is the one real hazard in the project.** That constant is baked into all
424 files, so renaming the account, renaming the repository, or changing the
default branch breaks every link in the game at once. The fix is to edit those two
lines and regenerate — but nothing will warn you first, so look here when the
board suddenly 404s.

## The bot

Plain minimax, memoized, with one deliberate constraint: ties break toward the
lowest cell index. The bot therefore has no randomness at all, which is what makes
the corpus **reproducible** — and reproducibility is what makes `--check` mean
something. Regenerate on any machine and you get byte-identical output.

It is unbeatable, which is the point. `0` of the 216 endings is a win for the
visitor. 18 are draws. A draw is the best result available, and 65 of the 208
decision pages are positions where *every* remaining move is already lost.

## Working on it

```sh
python tools/generate.py                    # build game/ and README.md
python tools/generate.py --check            # exit 1 if the tree on disk drifted
python tools/generate.py --handle octocat   # override the account for one run
python tools/verify.py                      # check the game that shipped
```

Stdlib only, no dependencies, nothing to install.

Edit **`tools/readme.template.md`**, never `README.md` — the latter is generated
and your edits to it will be overwritten. The template's `{{PAGES}}`,
`{{ENDINGS}}`, `{{WINS}}` and friends are filled from the real corpus at build
time, so the numbers the README quotes cannot drift from the game it ships.

Any `{{PLACEHOLDER}}` left unfilled is a hard failure in `verify.py`. That is on
purpose: it makes shipping a profile that says `{{NAME}}` impossible.

## What `verify.py` actually proves

It does not import the generator or re-run its solver. Testing a solver against
itself would prove nothing about a rendering bug that wires a cell to the wrong
position — and that is the likeliest bug in a project like this one.

Instead it reads the emitted markdown, rebuilds the move graph from the links a
visitor would really click, and evaluates that graph by backward induction from
its endings. If the shipped links let a visitor force a win, it fails. The
README's claim is therefore a test over the artifact rather than a belief about
the code, which is a stronger thing to be able to say.

It also checks that every link resolves, that every page offers exactly as many
moves as it has empty cells, that no move overwrites a played cell, that finished
positions offer no moves, that every position is legal for either opening, and
that no page is orphaned or stale.

## Deliberately absent

No badge wall. No streak-stat, trophy or language card: those are third-party
services that go down, rate-limit and get mis-cached by GitHub's image proxy,
which is exactly the fragility this design exists to avoid. No animated typing
header, for the same reason. No visitor counter.

The theme-swapping hero is two hand-written SVGs of identical geometry, selected
by `<picture>` with `prefers-color-scheme`. They contain no `<text>` element on
purpose: GitHub serves them through its image proxy, so `currentColor` will not
inherit and any font is at the mercy of the reader's machine. Pure geometry has
neither problem.

The README does not explain that the art changes with your theme. Whoever
notices, notices.
