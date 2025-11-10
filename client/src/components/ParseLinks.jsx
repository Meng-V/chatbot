import ReactMarkdown from 'react-markdown';
import gfm from 'remark-gfm';
import './ChatBotComponent.css';

/**
 * This component is used to parse links in the chat messages
 */
const MessageComponents = ({ msg }) => {
  // Clean up excessive whitespace for more compact display
  let message = msg
    .replace(/\n\n\n+/g, '\n\n')  // Max 2 newlines
    .replace(/^\s+|\s+$/g, '')     // Trim start/end whitespace
    .replace(/\n\s*\n\s*\n/g, '\n\n'); // Remove triple+ line breaks
  
  return (
    <span className='chat-message-container'>
      <ReactMarkdown
        remarkPlugins={[gfm]}
        // Used to customize the rendering of links
        // [noopener noreferrer] improves security when opening links in a new tab
        components={{
          a: ({ ...props }) => (
            <a
              {...props}
              className='styled-link'
              target='_blank'
              rel='noopener noreferrer'
            />
          ),
        }}
      >
        {message}
      </ReactMarkdown>
    </span>
  );
};

export default MessageComponents;
