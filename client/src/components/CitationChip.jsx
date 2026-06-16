/**
 * Inline citation marker: renders `[n]` in answer text as a small, static
 * reference marker that maps the claim to the matching entry in the
 * "Sources" footer below the message.
 *
 * History: this used to be an interactive pill that opened a portal
 * popover with the snippet + a link. On the embedded widget that popover
 * proved unclickable (portal teardown + iframe sandbox / popup-blocker
 * swallowing the new-tab open). Per operator request (2026-06-16) the
 * clickable source links now live in the Sources footer
 * (ChatBotComponent), which are plain `<a target="_blank">` anchors in
 * normal document flow -- they just navigate, and right-click / copy
 * work. This marker is now intentionally non-interactive: it only shows
 * `[n]` so the reader can match a claim to its footer source.
 */
const CitationChip = ({ n }) => (
  <sup className="mx-0.5 align-super text-[10px] font-semibold text-red-600">
    [{n}]
  </sup>
);

export default CitationChip;
