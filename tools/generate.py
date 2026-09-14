#!/usr/bin/env python3
"""Compile tic-tac-toe into a filesystem.

Every reachable board state is emitted as its own markdown page, and every legal
move is an ordinary link to the page for the position it produces. The result is
a game that runs on nothing at all: no JavaScript, no Actions, no server, no
token. GitHub's file viewer is the entire runtime.

    python tools/generate.py                    build game/ and README.md
    python tools/generate.py --check            fail if the tree on disk drifted
    python tools/generate.py --handle octocat   set the account links point at

Board encoding: nine characters over {x, o, _}, read left-to-right and
top-to-bottom, used directly as the filename. The visitor is x; the bot is o and
plays a deterministic minimax move, which is what makes the corpus reproducible
and therefore checkable.

Positions reached by different move orders converge on the same file, so this is
a game *graph*, not a game tree: 182 visitor-decision states rather than 439.
"""

import argparse
import functools
import pathlib
import sys

# The one constant every emitted link depends on. Relative links are unsafe here:
# a profile README renders at github.com/<handle>, where relative paths resolve
# against the profile root rather than the repository, and 404. So every link
# written below is absolute. Renaming the account, the repo or the default branch
# invalidates the whole corpus -- change it here, then regenerate.
HANDLE = "aryaptrha"
BRANCH = "main"

ROOT = pathlib.Path(__file__).resolve().parent.parent
TEMPLATE = pathlib.Path(__file__).resolve().parent / "readme.template.md"

EMPTY = "_" * 9
LINES = ((0, 1, 2), (3, 4, 5), (6, 7, 8),
         (0, 3, 6), (1, 4, 7), (2, 5, 8),
         (0, 4, 8), (2, 4, 6))
CELLS = ("a1", "b1", "c1", "a2", "b2", "c2", "a3", "b3", "c3")

MARK_X = "&times;"
MARK_O = "&#9711;"
DOT = "&middot;"
PAD = "&nbsp;&nbsp;"


# --------------------------------------------------------------------------- #
# the game

def winner(board):
    """Returns 'x', 'o', 'd' for a drawn full board, or None if still alive."""
    for a, b, c in LINES:
        if board[a] != "_" and board[a] == board[b] == board[c]:
            return board[a]
    return "d" if "_" not in board else None


def place(board, i, mark):
    return board[:i] + mark + board[i + 1:]


@functools.lru_cache(maxsize=None)
def score(board, turn):
    """Minimax value from the bot's side: +1 the bot wins, 0 draw, -1 it loses."""
    done = winner(board)
    if done == "o":
        return 1
    if done == "x":
        return -1
    if done == "d":
        return 0
    values = [score(place(board, i, turn), "x" if turn == "o" else "o")
              for i in range(9) if board[i] == "_"]
    return max(values) if turn == "o" else min(values)


def bot_move(board):
    """Best move, ties broken toward the lowest index so every run is identical."""
    return max((i for i in range(9) if board[i] == "_"),
               key=lambda i: (score(place(board, i, "o"), "x"), -i))


def resolve(board, i):
    """Where the visitor lands after playing cell i: their move, then the reply."""
    after = place(board, i, "x")
    if winner(after):
        return after
    return place(after, bot_move(after), "o")


def bot_first_board():
    """The position after the bot opens, for visitors who want a real chance."""
    return place(EMPTY, bot_move(EMPTY), "o")


def corpus():
    """Every board that needs a page, mapped to its kind."""
    pages = {}

    def visit(board):
        if board in pages:
            return
        done = winner(board)
        pages[board] = "terminal" if done else "decision"
        if done:
            return
        for i in range(9):
            if board[i] == "_":
                visit(resolve(board, i))

    visit(EMPTY)                # the visitor opens
    visit(bot_first_board())    # ...or lets the bot open
    # The empty board renders inline in README.md, so it needs no page of its own.
    # Nothing links to it either, which keeps every remaining file reachable.
    pages.pop(EMPTY, None)
    return pages


def number_endings(pages):
    """Stable numbering, so 'ending 88 of 216' is real and never shifts."""
    terminals = sorted(b for b, k in pages.items() if k == "terminal")
    tally = {}
    for board in terminals:
        tally[winner(board)] = tally.get(winner(board), 0) + 1
    return {board: (n, len(terminals), winner(board), tally[winner(board)])
            for n, board in enumerate(terminals, start=1)}


# --------------------------------------------------------------------------- #
# rendering

class Site:
    """Where this profile lives. Every URL in the corpus comes from here."""

    def __init__(self, handle, branch):
        self.handle = handle
        self.profile = "https://github.com/%s" % handle
        self.base = "https://github.com/%s/%s/blob/%s" % (handle, handle, branch)
        self.raw = "https://raw.githubusercontent.com/%s/%s/%s" % (handle, handle, branch)

    def page(self, board):
        return "%s/game/%s.md" % (self.base, board)


def board_table(board, site, playable):
    """The board as an HTML table. Empty cells are the links: the cell is the button."""
    rows = []
    for r in range(3):
        cells = []
        for c in range(3):
            i = r * 3 + c
            mark = board[i]
            if mark == "x":
                body = PAD + MARK_X + PAD
            elif mark == "o":
                body = PAD + MARK_O + PAD
            elif playable:
                # Padding sits inside the anchor so the whole strip is clickable.
                body = '<a href="%s" title="play %s">%s%s%s</a>' % (
                    site.page(resolve(board, i)), CELLS[i], PAD, DOT, PAD)
            else:
                body = PAD + "&nbsp;" + PAD
            cells.append('<td align="center">%s</td>' % body)
        rows.append("<tr>%s</tr>" % "".join(cells))
    return "<table>\n%s\n</table>" % "\n".join(rows)


LABELS = {1: "you win", 0: "a draw is still reachable", -1: "a forced loss"}


def prospect(board, i):
    """(value, label) for playing cell i, from the visitor's side, bot staying perfect."""
    after = place(board, i, "x")
    done = winner(after)
    if done == "x":
        return 1, "you win"    # unreachable; verify.py proves it over the corpus
    if done == "d":
        return 0, "a draw"
    value = -score(after, "o")           # flip to the visitor's point of view
    return value, LABELS[value]


def render_decision(board, site):
    plies = 9 - board.count("_")
    moves = [(CELLS[i],) + prospect(board, i) for i in range(9) if board[i] == "_"]
    options = "\n".join("- `%s` &rarr; %s" % (cell, label) for cell, _, label in moves)

    # A per-position count, because a fixed sentence here would be a lie on most
    # pages: early on nothing is lost yet, and by the end everything is.
    lost = sum(1 for _, value, _ in moves if value < 0)
    if lost == 0:
        verdict = "Every move here still holds the draw. That will not last."
    elif lost == len(moves):
        verdict = "Every move here is already lost."
    else:
        verdict = "%d of these %d moves are already lost." % (lost, len(moves))
    return """<div align="center">

%s

<sub>your move &middot; ply %d of 9</sub>

</div>

<details>
<summary><sub>show me where each move ends up</sub></summary>

<br>

%s

<sub>Read off the solved game, not guessed. %s</sub>

</details>

<div align="center">
<sub><a href="%s">start over</a> &middot; <a href="%s">let it move first</a></sub>
</div>
""" % (board_table(board, site, True), plies + 1, options, verdict,
       site.profile, site.page(bot_first_board()))


def render_terminal(board, site, endings):
    n, total, kind, same = endings[board]
    headline = {"o": "You lost.", "d": "A draw.", "x": "You won."}[kind]
    aside = {
        "o": "one of the %d endings where it beats you" % same,
        "d": "one of only %d where you hold it &mdash; the draw is the win" % same,
        "x": "which should be impossible; please open an issue",
    }[kind]
    return """<div align="center">

%s

<sub><b>%s</b></sub>

<sub>ending %d of %d &middot; %s</sub>

<br>

<sub><a href="%s">play again</a> &middot; <a href="%s">let it move first</a></sub>

</div>
""" % (board_table(board, site, False), headline, n, total, aside,
       site.profile, site.page(bot_first_board()))


def render_readme(pages, site):
    if not TEMPLATE.exists():
        sys.exit("missing template: %s" % TEMPLATE)
    terminals = [b for b, k in pages.items() if k == "terminal"]
    tally = {"o": 0, "d": 0, "x": 0}
    for board in terminals:
        tally[winner(board)] += 1
    fields = {
        "BOARD": board_table(EMPTY, site, True),
        "PAGES": len(pages),
        "DECISIONS": sum(1 for k in pages.values() if k == "decision"),
        "ENDINGS": len(terminals),
        "LOSSES": tally["o"],
        "DRAWS": tally["d"],
        "WINS": tally["x"],
        "BOTFIRST": site.page(bot_first_board()),
        "PROFILE": site.profile,
        "BASE": site.base,
        "RAW": site.raw,
        "HANDLE": site.handle,
    }
    text = TEMPLATE.read_text(encoding="utf-8")
    for key, value in fields.items():
        text = text.replace("{{%s}}" % key, str(value))
    return text


def build(site):
    """Every file this project generates, as {relative path: content}."""
    pages = corpus()
    endings = number_endings(pages)
    files = {"README.md": render_readme(pages, site)}
    for board, kind in pages.items():
        files["game/%s.md" % board] = (
            render_terminal(board, site, endings) if kind == "terminal"
            else render_decision(board, site))
    return files, pages


# --------------------------------------------------------------------------- #
# entry point

def main():
    ap = argparse.ArgumentParser(description="Compile tic-tac-toe into a filesystem.")
    ap.add_argument("--handle", default=HANDLE, help="GitHub account links point at")
    ap.add_argument("--branch", default=BRANCH, help="default branch (default: main)")
    ap.add_argument("--check", action="store_true",
                    help="compare against disk instead of writing; exit 1 on drift")
    args = ap.parse_args()

    site = Site(args.handle, args.branch)
    files, pages = build(site)
    decisions = sum(1 for k in pages.values() if k == "decision")

    if args.check:
        drift = []
        for rel, want in sorted(files.items()):
            path = ROOT / rel
            if not path.exists():
                drift.append("missing:  " + rel)
            elif path.read_text(encoding="utf-8") != want:
                drift.append("modified: " + rel)
        for path in sorted((ROOT / "game").glob("*.md")):
            if ("game/" + path.name) not in files:
                drift.append("stale:    game/" + path.name)
        if drift:
            print("\n".join(drift))
            print("")
            print("%d file(s) differ. Run: python tools/generate.py" % len(drift))
            return 1
        print("ok: %d files match, corpus is reproducible" % len(files))
        return 0

    game = ROOT / "game"
    game.mkdir(exist_ok=True)
    for path in game.glob("*.md"):
        if ("game/" + path.name) not in files:
            path.unlink()                          # drop states no longer reachable
    for rel, body in sorted(files.items()):
        (ROOT / rel).write_text(body, encoding="utf-8", newline="\n")

    print("wrote %d files: %d decision states, %d endings"
          % (len(files), decisions, len(pages) - decisions))
    if "{{" in site.handle:
        print("note: handle is still a placeholder -- rerun with --handle <you>")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
