import { useState, useRef, useEffect } from 'react';
import { ExternalLink } from 'lucide-react';

/**
 * Inline citation pill: renders `[n]` in answer text as a clickable chip
 * that expands to show {snippet, source_url}. Click outside to dismiss.
 *
 * The synthesizer emits answers like "King opens at 7am [1] and closes at
 * 2am [2]." with a parallel `citations: [{n, url, snippet}]` array. This
 * component is what makes those numbers verifiable -- one click and the
 * user sees the exact passage the bot was reading from. That's the
 * trust-loop the rebuild plan is built around.
 *
 * Degrades cleanly: if `citation` is missing (number with no matching
 * entry, e.g. backend bug or stale message), renders as plain text so
 * we don't drop information silently.
 */
const CitationChip = ({ n, citation }) => {
  const [open, setOpen] = useState(false);
  const containerRef = useRef(null);

  // Dismiss on outside click. Listening at document scope rather than
  // a portal because the popover is positioned inline -- click within
  // the chip's wrapper shouldn't close.
  useEffect(() => {
    if (!open) return;
    const handler = (e) => {
      if (containerRef.current && !containerRef.current.contains(e.target)) {
        setOpen(false);
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [open]);

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
    <span ref={containerRef} className="relative inline-block align-baseline">
      <button
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
      {open && (
        <span
          role="tooltip"
          className="absolute z-10 left-0 top-full mt-1 w-80 max-w-[90vw] block px-3 py-2 text-xs text-left text-gray-800 bg-white border border-gray-300 rounded-md shadow-lg"
        >
          {displaySnippet && (
            <span className="block mb-2 whitespace-pre-wrap">
              “{displaySnippet}”
            </span>
          )}
          {url && (
            <a
              href={url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 text-blue-600 hover:underline break-all"
            >
              <ExternalLink size={12} className="shrink-0" />
              <span>{url}</span>
            </a>
          )}
        </span>
      )}
    </span>
  );
};

export default CitationChip;
