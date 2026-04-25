import { Children, Fragment } from 'react';
import ReactMarkdown from 'react-markdown';
import gfm from 'remark-gfm';
import CitationChip from './CitationChip';
import './ChatBotComponent.css';

/**
 * This component is used to parse links in the chat messages.
 *
 * If `citations` is provided (an array of {n, url, snippet}), any `[n]`
 * markers in the text are replaced with clickable CitationChip pills that
 * expand to show the source snippet + URL. If no citations are provided,
 * `[n]` markers render as plain text -- existing messages keep working
 * unchanged.
 */

// Splits a string on [n] markers and returns an array of strings + chips.
// Used inside markdown-rendered text nodes so the chips inherit the right
// flow (paragraph, list item, etc.) instead of breaking layout.
function injectChips(text, citationsByN, keyPrefix) {
  if (typeof text !== 'string' || !citationsByN || citationsByN.size === 0) {
    return text;
  }
  const re = /\[(\d+)\]/g;
  const parts = [];
  let last = 0;
  let match;
  let i = 0;
  while ((match = re.exec(text)) !== null) {
    if (match.index > last) {
      parts.push(text.slice(last, match.index));
    }
    const n = Number(match[1]);
    const citation = citationsByN.get(n);
    parts.push(
      <CitationChip key={`${keyPrefix}-c-${i++}-${n}`} n={n} citation={citation} />,
    );
    last = re.lastIndex;
  }
  if (last < text.length) {
    parts.push(text.slice(last));
  }
  return parts.length > 0 ? parts : text;
}

// Recursively walks markdown-rendered children, injecting chips into any
// string leaf. Wrapping element components (p, li, em, strong, code...) all
// hand their children to this so chips work everywhere -- not just bare
// paragraphs.
function transformChildren(children, citationsByN, keyPrefix) {
  return Children.map(children, (child, idx) => {
    if (typeof child === 'string') {
      const replaced = injectChips(child, citationsByN, `${keyPrefix}-${idx}`);
      if (Array.isArray(replaced)) {
        return <Fragment key={`${keyPrefix}-${idx}-frag`}>{replaced}</Fragment>;
      }
      return replaced;
    }
    return child;
  });
}

const MessageComponents = ({ msg, citations }) => {
  // Clean up excessive whitespace for more compact display
  let message = msg
    .replace(/\n\n\n+/g, '\n\n') // Max 2 newlines
    .replace(/^\s+|\s+$/g, '') // Trim start/end whitespace
    .replace(/\n\s*\n\s*\n/g, '\n\n'); // Remove triple+ line breaks

  // Build a Map<n, citation> once per render so injectChips is O(1).
  const citationsByN =
    citations && citations.length > 0
      ? new Map(citations.map((c) => [Number(c.n), c]))
      : null;

  // Wrap a markdown text-container component so its string children get
  // chip-replacement. Used for every element that can contain prose.
  const wrapText = (Tag) => {
    return ({ node, children, ...props }) => (
      <Tag {...props}>{transformChildren(children, citationsByN, Tag)}</Tag>
    );
  };

  return (
    <span className="chat-message-container">
      <ReactMarkdown
        remarkPlugins={[gfm]}
        components={{
          a: ({ ...props }) => (
            <a
              {...props}
              className="styled-link"
              target="_blank"
              rel="noopener noreferrer"
            />
          ),
          p: wrapText('p'),
          li: wrapText('li'),
          strong: wrapText('strong'),
          em: wrapText('em'),
          h1: wrapText('h1'),
          h2: wrapText('h2'),
          h3: wrapText('h3'),
          h4: wrapText('h4'),
        }}
      >
        {message}
      </ReactMarkdown>
    </span>
  );
};

export default MessageComponents;
