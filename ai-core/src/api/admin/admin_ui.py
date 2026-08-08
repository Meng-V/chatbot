"""
Shared look-and-feel for every operator surface.

Why this exists (operator feedback 2026-07-28: "the dashboard isn't
visually clear and the ticket handoffs are muddled"): the five admin
pages had grown five independent stylesheets and five different ways of
showing state, so nothing looked like part of one tool and there was no
way to tell at a glance what needed attention. This module owns:

  * one stylesheet (Miami red, cards, status pills, action buttons)
  * `page()` -- the shell every surface renders into, including a nav
    bar so you can move between queues without bouncing off the hub
  * `pill()` / `stat_card()` / `action()` -- the shared vocabulary for
    "what state is this in" and "what can I do about it"

Everything here is a pure string function: no I/O, no framework
imports, trivially unit-testable.
"""

from __future__ import annotations

import html
from typing import Optional


def e(v: object) -> str:
    """HTML-escape anything. All admin content is untrusted: ticket text
    and conversation transcripts quote patron input."""
    return html.escape("" if v is None else str(v))


# Miami University red is the anchor; everything else is neutral so the
# status colors are the only things competing for attention.
STYLE = """
:root{
  --miami:#b61e2e; --miami-dark:#8e1724;
  --ink:#1c1c1e; --muted:#6b7280; --line:#e5e7eb; --bg:#f7f7f8;
  --open:#b45309; --open-bg:#fef3c7;
  --prog:#1d4ed8; --prog-bg:#dbeafe;
  --done:#15803d; --done-bg:#dcfce7;
  --warn:#b91c1c; --warn-bg:#fee2e2;
}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
  font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",system-ui,sans-serif}
a{color:#1a4480}
header.top{background:var(--miami);color:#fff;padding:.7rem 1rem}
header.top .wrap{max-width:1080px;margin:0 auto;display:flex;
  align-items:center;gap:1rem;flex-wrap:wrap}
header.top b{font-size:1.05rem}
nav.tabs{max-width:1080px;margin:0 auto;padding:0 1rem;display:flex;
  gap:.25rem;flex-wrap:wrap;background:#fff;border-bottom:1px solid var(--line)}
nav.tabs a{padding:.6rem .9rem;text-decoration:none;color:var(--muted);
  border-bottom:3px solid transparent;font-weight:500;white-space:nowrap}
nav.tabs a:hover{color:var(--ink);background:#fafafa}
nav.tabs a.on{color:var(--miami);border-bottom-color:var(--miami);font-weight:600}
nav.tabs .badge{display:inline-block;min-width:1.2rem;margin-left:.35rem;
  padding:0 .35rem;border-radius:999px;background:var(--warn-bg);
  color:var(--warn);font-size:.75rem;font-weight:700;text-align:center}
main{max-width:1080px;margin:0 auto;padding:1.25rem 1rem 3rem}
h1{font-size:1.4rem;margin:.2rem 0 1rem}
h2{font-size:1.05rem;margin:1.8rem 0 .6rem;color:#374151}
p.lede{color:var(--muted);margin:.2rem 0 1.2rem}
/* Says what a GROUP of tools is for, so the grouping is legible without
   opening every card in it. */
p.sub{color:var(--muted);font-size:.88rem;margin:-.35rem 0 .75rem}

/* "Is the bot up?" is the only question during an incident, so it gets
   answered above everything else rather than in a card halfway down. */
.banner{border-radius:8px;padding:1rem 1.15rem;margin:0 0 1.3rem}
.banner.down{background:var(--warn-bg);border:2px solid var(--warn)}
.banner.down b{color:var(--warn);display:block;font-size:1.05rem;
  margin-bottom:.2rem}

/* stat cards -- the "what needs me now" row */
.stats{display:grid;gap:.75rem;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));
  margin-bottom:1.5rem}
.stat{background:#fff;border:1px solid var(--line);border-left:4px solid var(--line);
  border-radius:8px;padding:.9rem 1rem;text-decoration:none;color:inherit;display:block}
.stat:hover{box-shadow:0 1px 6px rgba(0,0,0,.08)}
.stat .n{font-size:1.9rem;font-weight:700;line-height:1.1}
.stat .lbl{color:var(--muted);font-size:.85rem;margin-top:.15rem}
.stat.needs{border-left-color:var(--warn)}
.stat.needs .n{color:var(--warn)}
.stat.calm{border-left-color:var(--done)}
.stat.calm .n{color:var(--done)}

/* cards replace wide tables so this works on a phone too */
.card{background:#fff;border:1px solid var(--line);border-radius:8px;
  padding:.9rem 1rem;margin-bottom:.7rem}
.card.attn{border-left:4px solid var(--warn)}
.card .meta{color:var(--muted);font-size:.82rem;display:flex;gap:.6rem;
  flex-wrap:wrap;align-items:center;margin-bottom:.45rem}
.card .q{font-weight:600;margin:.3rem 0}
.card .body{white-space:pre-wrap}
.card dl{margin:.4rem 0 0;display:grid;grid-template-columns:auto 1fr;
  gap:.15rem .6rem}
.card dt{color:var(--muted);font-size:.82rem;text-transform:uppercase;
  letter-spacing:.03em}
.card dd{margin:0}

/* status pills */
.pill{display:inline-block;padding:.1rem .5rem;border-radius:999px;
  font-size:.78rem;font-weight:600;white-space:nowrap}
.pill.open{background:var(--open-bg);color:var(--open)}
.pill.prog{background:var(--prog-bg);color:var(--prog)}
.pill.done{background:var(--done-bg);color:var(--done)}
.pill.warn{background:var(--warn-bg);color:var(--warn)}
.pill.flat{background:#f3f4f6;color:var(--muted)}

/* actions: explicit buttons, never a mystery "next state" toggle */
.acts{display:flex;gap:.4rem;flex-wrap:wrap;margin-top:.7rem}
.btn{display:inline-block;padding:.35rem .75rem;border-radius:6px;
  text-decoration:none;font-size:.86rem;font-weight:600;border:1px solid var(--line);
  background:#fff;color:var(--ink)}
.btn:hover{background:#fafafa}
.btn.primary{background:var(--miami);border-color:var(--miami);color:#fff}
.btn.primary:hover{background:var(--miami-dark)}
.btn.ghost{color:var(--muted)}
table{border-collapse:collapse;width:100%;background:#fff;font-size:.9rem}
th,td{border:1px solid var(--line);padding:.45rem .6rem;text-align:left;
  vertical-align:top}
th{background:#fafafa;font-size:.8rem;text-transform:uppercase;
  letter-spacing:.03em;color:var(--muted)}
.empty{background:#fff;border:1px dashed var(--line);border-radius:8px;
  padding:2rem 1rem;text-align:center;color:var(--muted)}
code{background:#f3f4f6;padding:.1rem .3rem;border-radius:3px;font-size:.85em}
small.dim{color:var(--muted)}
.note{background:#fff8e1;border:1px solid #e6d9a8;padding:.7rem 1rem;
  border-radius:6px}
form.inline{display:inline}
/* A form that reveals only the fields the chosen task uses hides its
   wrappers with [hidden]; make that beat any display rule above. */
[hidden]{display:none!important}
.ok{color:var(--done);font-weight:600}
.err{color:var(--warn);font-weight:600}
/* the passages an answer was built from, on the conversation page */
ul.sources{list-style:none;margin:.3rem 0 0;padding:0}
ul.sources li{display:flex;gap:.4rem;align-items:center;flex-wrap:wrap;
  padding:.25rem 0}
label{display:block;margin:.8rem 0 .25rem;font-weight:600}
input[type=text],input[type=email],textarea,select{width:100%;padding:.5rem;
  border:1px solid #bbb;border-radius:6px;font:inherit;background:#fff}
textarea{min-height:6rem}
button{padding:.5rem 1.1rem;font:inherit;font-weight:600;cursor:pointer;
  background:var(--miami);color:#fff;border:0;border-radius:6px}
"""

# Every operator surface, in the order an operator works them: things
# that need action first, reference material last.
#
# /admin/service is last but is NOT reference -- it is the stop button.
# It shipped with no way to reach it from the UI, so the only way to take
# the bot out of service was to already know the URL. Added 2026-08-08.
NAV = (
    ("/admin/", "Dashboard", None),
    ("/admin/tickets/view", "Tickets", "tickets"),
    ("/admin/review", "Flagged", "flagged"),
    ("/admin/corrections/view", "Corrections", None),
    ("/admin/cost", "Cost", None),
    ("/admin/service", "Service", None),
)


def nav(current: str, key: str = "", counts: Optional[dict] = None) -> str:
    """Render the tab bar. `current` is the path prefix to highlight;
    `counts` optionally puts a badge on the queues that need work."""
    kq = f"?key={e(key)}" if key else ""
    out = []
    for path, label, count_key in NAV:
        on = " class='on'" if current == path else ""
        badge = ""
        if counts and count_key and counts.get(count_key):
            badge = f"<span class='badge'>{e(counts[count_key])}</span>"
        out.append(f"<a href='{e(path)}{kq}'{on}>{e(label)}{badge}</a>")
    return f"<nav class='tabs'>{''.join(out)}</nav>"


def page(title: str, body: str, *, current: str = "", key: str = "",
         counts: Optional[dict] = None) -> str:
    """The shell every admin surface renders into."""
    return (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<title>{e(title)} — Smart Chatbot admin</title>"
        f"<style>{STYLE}</style></head><body>"
        "<header class='top'><div class='wrap'>"
        "<b>Smart Chatbot</b><span style='opacity:.85'>operator console</span>"
        "</div></header>"
        f"{nav(current, key, counts)}"
        f"<main>{body}</main></body></html>"
    )


def stat_card(href: str, n: object, label: str, *, needs: bool = False) -> str:
    """A big-number tile. `needs=True` colors it as work-to-do so the
    dashboard answers "is there anything for me?" without reading."""
    cls = "stat needs" if needs else "stat calm"
    return (f"<a class='{cls}' href='{e(href)}'>"
            f"<div class='n'>{e(n)}</div>"
            f"<div class='lbl'>{e(label)}</div></a>")


_PILL_CLASS = {
    "open": "open",
    "in_progress": "prog",
    "reviewed": "prog",   # legacy value, shown as in-progress
    "done": "done",
}
_PILL_LABEL = {
    "open": "open",
    "in_progress": "in progress",
    "reviewed": "in progress",
    "done": "done",
}


def pill(status: str, *, extra: str = "") -> str:
    """Status pill using ONE vocabulary across every surface."""
    s = (status or "open").lower()
    cls = _PILL_CLASS.get(s, "flat")
    label = _PILL_LABEL.get(s, s)
    return f"<span class='pill {cls}'>{e(label)}</span>{extra}"


def action(href: str, label: str, *, primary: bool = False,
           ghost: bool = False) -> str:
    cls = "btn primary" if primary else ("btn ghost" if ghost else "btn")
    return f"<a class='{cls}' href='{e(href)}'>{e(label)}</a>"


def empty(msg: str) -> str:
    return f"<div class='empty'>{e(msg)}</div>"


__all__ = ["NAV", "STYLE", "action", "e", "empty", "nav", "page", "pill",
           "stat_card"]
