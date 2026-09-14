#!/usr/bin/env python3
"""Check the game that actually shipped.

This deliberately does not import the generator or re-run its solver. It reads
the emitted markdown off disk, rebuilds the move graph from the links a visitor
would really click, and proves the interesting claim by backward induction over
that graph:

    the best outcome available to a visitor is a draw

So the README's boast is a test over the shipped artifact, not a belief about the
code that produced it. A rendering bug that wired a cell to the wrong position
would survive any amount of testing of the solver alone, and is caught here.

    python tools/verify.py
"""

import functools
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
GAME = ROOT / "game"
README = ROOT / "README.md"

LINES = ((0, 1, 2), (3, 4, 5), (6, 7, 8),
         (0, 3, 6), (1, 4, 7), (2, 5, 8),
         (0, 4, 8), (2, 4, 6))

TABLE = re.compile(r"<table>(.*?)</table>", re.DOTALL)
LINK = re.compile(r"/game/([xo_]{9})\.md")
PLACEHOLDER = re.compile(r"\{\{[A-Z_]+\}\}")

failures = []
notes = []


def fail(message):
    failures.append(message)


def winner(board):
    for a, b, c in LINES:
        if board[a] != "_" and board[a] == board[b] == board[c]:
            return board[a]
    return "d" if "_" not in board else None


def board_links(text):
    """Links inside the board table only -- not the navigation links below it."""
    table = TABLE.search(text)
    return LINK.findall(table.group(1)) if table else []


# --------------------------------------------------------------------------- #
# load what shipped

if not README.exists():
    sys.exit("no README.md -- run: python tools/generate.py")

readme = README.read_text(encoding="utf-8")
files = sorted(GAME.glob("*.md"))
if not files:
    sys.exit("no pages in game/ -- run: python tools/generate.py")

graph = {}
for path in files:
    board = path.stem
    if len(board) != 9 or set(board) - set("xo_"):
        fail("bad filename, not a board encoding: game/%s.md" % path.name)
        continue
    graph[board] = board_links(path.read_text(encoding="utf-8"))

opening = board_links(readme)

# Reachability roots are not just the nine cells: "let it move first" sits in the
# navigation below the board rather than inside the table, and it opens a whole
# second subtree of its own.
roots = LINK.findall(readme)
entries = sorted(set(roots) - set(opening))


# --------------------------------------------------------------------------- #
# structure

for board, targets in sorted(graph.items()):
    done = winner(board)
    empties = board.count("_")

    if done and targets:
        fail("%s is finished (%s) but still offers %d moves" % (board, done, len(targets)))
    if not done and len(targets) != empties:
        fail("%s has %d empty cells but %d links" % (board, empties, len(targets)))

    # Either side may have opened, so the counts differ by at most one.
    xs, os_ = board.count("x"), board.count("o")
    if abs(xs - os_) > 1:
        fail("%s is not a legal position (%d x, %d o)" % (board, xs, os_))

    for target in targets:
        if target not in graph:
            fail("%s links to game/%s.md, which does not exist" % (board, target))
            continue
        added = sum(1 for i in range(9) if board[i] != target[i])
        # The visitor's move plus the bot's reply -- unless the visitor's move
        # ended the game, in which case there is no reply to make.
        expected = (1,) if winner(target) and target.count("o") == os_ else (2,)
        if added not in expected:
            fail("%s -> %s changes %d cells, expected %s"
                 % (board, target, added, expected[0]))
        for i in range(9):
            if board[i] != "_" and board[i] != target[i]:
                fail("%s -> %s overwrites a played cell" % (board, target))
                break

for target in opening:
    if target not in graph:
        fail("README links to game/%s.md, which does not exist" % target)
if len(opening) != 9:
    fail("README offers %d opening moves, expected 9" % len(opening))


# --------------------------------------------------------------------------- #
# reachability -- nothing orphaned, nothing stale

seen = set()
queue = list(roots)
while queue:
    board = queue.pop()
    if board in seen or board not in graph:
        continue
    seen.add(board)
    queue.extend(graph[board])

for board in sorted(set(graph) - seen):
    fail("game/%s.md is unreachable from the README" % board)


# --------------------------------------------------------------------------- #
# the claim: a draw is the ceiling

VALUE = {"x": 1, "d": 0, "o": -1}      # from the visitor's point of view


@functools.lru_cache(maxsize=None)
def best(board):
    """Best outcome the visitor can force from here, over the shipped links."""
    done = winner(board)
    if done:
        return VALUE[done]
    targets = graph.get(board) or []
    return max((best(t) for t in targets if t in graph), default=0)


wins = sorted(b for b in graph if winner(b) == "x")
if wins:
    fail("%d position(s) let the visitor win, e.g. %s" % (len(wins), wins[0]))

ceiling = max((best(t) for t in opening if t in graph), default=None)
if ceiling is None:
    fail("could not evaluate the opening position")
elif ceiling > 0:
    fail("the visitor can force a win -- the README's claim is false")
else:
    notes.append("best outcome when you open:   %s"
                 % {0: "a draw", -1: "a loss"}[ceiling])

# The same has to hold in the other direction, or "let it move first" is a trap
# that hands the visitor a win.
for entry in entries:
    if entry not in graph:
        fail("README links to game/%s.md, which does not exist" % entry)
    elif best(entry) > 0:
        fail("the visitor can force a win after game/%s.md" % entry)
    else:
        notes.append("best outcome when it opens: %s"
                     % {0: "a draw", -1: "a loss"}[best(entry)])


# --------------------------------------------------------------------------- #
# content still owed

left = sorted(set(PLACEHOLDER.findall(readme)))
if left:
    fail("README still has unfilled placeholders: %s" % ", ".join(left))


# --------------------------------------------------------------------------- #
# report

terminals = [b for b in graph if winner(b)]
tally = {}
for board in terminals:
    tally[winner(board)] = tally.get(winner(board), 0) + 1

print("pages      %d  (%d decision, %d endings)"
      % (len(graph), len(graph) - len(terminals), len(terminals)))
print("endings    %d you lose, %d draw, %d you win"
      % (tally.get("o", 0), tally.get("d", 0), tally.get("x", 0)))
for note in notes:
    print("proof      %s" % note)

if failures:
    print("")
    for message in failures:
        print("FAIL  %s" % message)
    print("")
    print("%d check(s) failed" % len(failures))
    raise SystemExit(1)

print("")
print("all checks passed")
