import { useState, useRef, useEffect, useCallback } from 'react';
import { createPortal } from 'react-dom';
import { ExternalLink } from 'lucide-react';

/**
 * Inline citation pill: renders `[n]` in answer text as a clickable chip
 * that expands to show {snippet, source_url}. Click outside to dismiss.
 *
 * The popover is rendered through a PORTAL to document.body and positioned
 * with `position: fixed` against the chip's on-screen rect, clamped into
 * the viewport. This is the fix for the embedded narrow-widget clipping:
 * an inline `absolute` popover got cut off by the chat scroll container's
 * overflow no matter which side it anchored to. A portal escapes the
 * overflow entirely, and the clamp keeps it on-screen left AND right.
 *
 * Degrades cleanly: if `citation` is missing (number with no matching
 * entry, e.g. backend bug or stale message), renders as plain text so we
 * don't drop information silently.
 */
const POPOVER_WIDTH = 288; // px

const CitationChip = ({ n, citation }) => {
  const [open, setOpen] = useState(false);
  const [pos, setPos] = useState(null);
  const buttonRef = useRef(null);
  const popoverRef = useRef(null);

  const computePos = useCallback(() => {
    const btn = buttonRef.current;
    if (!btn) return;
    const r = btn.getBoundingClientRect();
    const margin = 8;
    const width = Math.min(POPOVER_WIDTH, window.innerWidth - margin * 2);
    let left = r.left;
    // Clamp so the popover never spills off either edge of the viewport.
    if (left + width > window.innerWidth - margin) {
      left = window.innerWidth - margin - width;
    }
    if (left < margin) left = margin;
    setPos({ top: r.bottom + 4, left, width });
  }, []);

  // While open: position under the chip, and close on outside click /
  // scroll / resize (re-anchoring a fixed popover on scroll is fiddly and
  // closing is the expected UX for a click-tooltip).
  useEffect(() => {
    if (!open) return;
    computePos();
    const onDocPointer = (e) => {
      if (
        buttonRef.current &&
        !buttonRef.current.contains(e.target) &&
        popoverRef.current &&
        !popoverRef.current.contains(e.target)
      ) {
        setOpen(false);
      }
    };
    const onScrollOrResize = () => setOpen(false);
    document.addEventListener('mousedown', onDocPointer);
    window.addEventListener('scroll', onScrollOrResize, true);
    window.addEventListener('resize', onScrollOrResize);
    return () => {
      document.removeEventListener('mousedown', onDocPointer);
      window.removeEventListener('scroll', onScrollOrResize, true);
      window.removeEventListener('resize', onScrollOrResize);
    };
  }, [open, computePos]);

  // Missing citation -- render the original `[n]` so info is preserved.
  if (!citation) {
    return <span className="text-gray-500">[{n}]</span>;
  }

  const { url, snippet } = citation;
  // Snippet can be long; cap for display, full text shown via title attr.
  const SNIPPET_DISPLAY_MAX = 280;
  const displaySnippet =
    snippet && snippet.length > SNIPPET_DISPLAY_MAX
      ? snippet.slice(0, SNIPPET_DISPLAY_MAX).trimEnd() + '…'
      : snippet || '';

  return (
    <>
      <button
        ref={buttonRef}
        type="button"
        onClick={() => setOpen((v) => !v)}
        title={snippet ? `Source ${n}: ${snippet.slice(0, 200)}` : `Source ${n}`}
        className={`inline-flex items-center justify-center align-baseline mx-0.5 px-1.5 h-5 min-w-[1.25rem] text-[11px] font-semibold leading-none rounded ${
          open
            ? 'bg-red-600 text-white'
            : 'bg-red-100 text-red-700 hover:bg-red-200'
        } cursor-pointer transition-colors`}
        aria-expanded={open}
        aria-label={`Source ${n}`}
      >
        {n}
      </button>
      {open &&
        pos &&
        createPortal(
          <span
            ref={popoverRef}
            role="tooltip"
            // Stop the pointer event from reaching the document-level
            // outside-click handler: without this, clicking the link could
            // tear down the popover before the click navigates, so the URL
            // felt "unclickable".
            onMouseDown={(e) => e.stopPropagation()}
            onClick={(e) => e.stopPropagation()}
            style={{
              position: 'fixed',
              top: pos.top,
              left: pos.left,
              width: pos.width,
              zIndex: 9999,
            }}
            className="block px-3 py-2 text-xs text-left text-gray-800 bg-white border border-gray-300 rounded-md shadow-lg break-words"
          >
            {displaySnippet && (
              <span className="block mb-2 whitespace-pre-wrap break-words">
                “{displaySnippet}”
              </span>
            )}
            {url && (
              <a
                href={url}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-start gap-1 text-blue-600 hover:underline"
              >
                <ExternalLink size={12} className="shrink-0 mt-0.5" />
                <span className="min-w-0 break-all">{url}</span>
              </a>
            )}
          </span>,
          document.body,
        )}
    </>
  );
};

export default CitationChip;
