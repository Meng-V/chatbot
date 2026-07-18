import { useContext, useRef, useEffect, useState, useCallback } from 'react';
import { AlertTriangle, Clock } from 'lucide-react';
import MessageComponents from './ParseLinks';
import { SocketContext } from '../context/SocketContextProvider';
import { MessageContext } from '../context/MessageContextProvider';
import MessageRatingComponent from './MessageRatingComponent';
import HumanLibrarianWidget from './HumanLibrarianWidget';
import OfflineTicketWidget from './TicketWidget';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Alert, AlertTitle, AlertDescription } from '@/components/ui/alert';
import './ChatBotComponent.css';

const ChatBotComponent = ({ askUsStatus = { isOpen: false, hoursToday: null } }) => {
  const { socketContextValues } = useContext(SocketContext);
  const { messageContextValues } = useContext(MessageContext);
  const chatRef = useRef();
  const [widgetVisible, setWidgetVisible] = useState(false);
  const [showTicketForm, setShowTicketForm] = useState(false);
  const [elapsedTime, setElapsedTime] = useState(0);

  // Live timer effect - updates every second while thinking
  useEffect(() => {
    let interval;
    if (messageContextValues.isTyping && messageContextValues.thinkingStartTime) {
      // Update immediately
      setElapsedTime(Math.floor((Date.now() - messageContextValues.thinkingStartTime) / 1000));
      
      // Then update every second
      interval = setInterval(() => {
        const elapsed = Math.floor((Date.now() - messageContextValues.thinkingStartTime) / 1000);
        setElapsedTime(elapsed);
      }, 1000);
    } else {
      setElapsedTime(0);
    }
    
    return () => {
      if (interval) clearInterval(interval);
    };
  }, [messageContextValues.isTyping, messageContextValues.thinkingStartTime]);

  const handleFormSubmit = (e) => {
    e.preventDefault();
    if (messageContextValues.inputMessage && socketContextValues.socket) {
      messageContextValues.addMessage(
        messageContextValues.inputMessage,
        'user',
      );
      messageContextValues.setInputMessage('');
      // Use startThinking to begin timer
      messageContextValues.startThinking();
      socketContextValues.sendUserMessage(messageContextValues.inputMessage);
    }
  };

  // Format time for display
  const formatTime = useCallback((seconds) => {
    if (seconds < 60) {
      return `${seconds}s`;
    }
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}m ${secs}s`;
  }, []);

  useEffect(() => {
    if (chatRef.current) {
      chatRef.current.scrollTop = chatRef.current.scrollHeight;
    }
  }, [messageContextValues.message]);

  // Determine if we should show service issues alert
  const shouldShowServiceAlert =
    !socketContextValues.serviceHealthy ||
    socketContextValues.connectionErrors >= 3 ||
    (!socketContextValues.isConnected &&
      socketContextValues.attemptedConnection);

  // Auto-show librarian widget based on service status
  useEffect(() => {
    if (socketContextValues.showLibrarianWidget && !widgetVisible) {
      setWidgetVisible(true);
    }
  }, [socketContextValues.showLibrarianWidget, widgetVisible]);

  return (
    <>
      {/* Service Status Alert */}
      {shouldShowServiceAlert && (
        <Alert variant="warning" className="mb-4">
          <AlertTriangle className="h-4 w-4" />
          <div className="flex-1">
            <AlertTitle>Service Issue Detected!</AlertTitle>
            <AlertDescription>
              {!socketContextValues.serviceHealthy
                ? 'The chatbot service is experiencing technical difficulties. '
                : 'Unable to connect to the chatbot service. '}
              {askUsStatus.isOpen 
                ? 'Please talk to a human librarian for immediate assistance.'
                : 'Please submit a ticket and we\'ll get back to you.'}
            </AlertDescription>
          </div>
          {askUsStatus.isOpen ? (
            <Button
              size="sm"
              variant="default"
              onClick={() => setWidgetVisible(!widgetVisible)}
            >
              {widgetVisible ? 'Hide' : 'Chat with Human Librarian'}
            </Button>
          ) : (
            <Button
              size="sm"
              variant="default"
              onClick={() => setShowTicketForm(!showTicketForm)}
            >
              {showTicketForm ? 'Hide' : 'Submit a Ticket'}
            </Button>
          )}
        </Alert>
      )}

      {/* Human Librarian Widget - only shown during business hours */}
      {widgetVisible && askUsStatus.isOpen && (
        <div className="mb-4 p-4 border border-blue-200 rounded-md bg-blue-50">
          <div className="flex justify-between items-center mb-2">
            <span className="font-bold text-blue-700">
              Talk to a Human Librarian
            </span>
            <Button size="xs" variant="ghost" onClick={() => setWidgetVisible(false)}>
              ✕
            </Button>
          </div>
          <HumanLibrarianWidget />
        </div>
      )}

      {/* Ticket Form Widget - shown when human chat not available */}
      {showTicketForm && !askUsStatus.isOpen && (
        <div className="mb-4 p-4 border border-orange-200 rounded-md bg-orange-50">
          <div className="flex justify-between items-center mb-2">
            <span className="font-bold text-orange-700">
              Submit a Ticket
            </span>
            <Button size="xs" variant="ghost" onClick={() => setShowTicketForm(false)}>
              ✕
            </Button>
          </div>
          <OfflineTicketWidget />
        </div>
      )}

      <div ref={chatRef} className="chat">
        <div className="flex flex-col items-start gap-4">
          {messageContextValues.message.map((message, index) => {
            const adjustedMessage =
              typeof message.text === 'object'
                ? message.text.response.join('')
                : message.text;

            // Strip any legacy "References:" tail from the body text (the
            // structured citations array supersedes it).
            const bodyText = adjustedMessage.split(/\nReferences:\n/i)[0] || '';

            // Structured confidence (v2) wins over text heuristic (legacy).
            const lowConfidenceHint =
              message.confidence === 'low' ||
              /No strong matches found|Institutional knowledge service is temporarily unavailable|ask a clarifying question/i.test(
                adjustedMessage,
              );
            // Reliability gate: when the answer is uncertain or a refusal,
            // do NOT surface sources -- strip inline [n] markers and drop the
            // citations so no clickable "evidence" appears under an answer the
            // bot itself flagged as unreliable.
            const showSources = !lowConfidenceHint;
            const renderBody = showSources
              ? bodyText
              : bodyText.replace(/\s*\[\d+\]/g, '');
            const renderCitations = showSources ? message.citations : undefined;
            return (
              <div
                key={index}
                className={message.sender === 'user' ? 'self-end' : 'self-start'}
              >
                <div
                  className={`max-w-md px-5 py-3 rounded-md relative ${
                    message.sender === 'user'
                      ? 'bg-white border border-red-400'
                      : 'bg-gray-200'
                  } ${message.sender !== 'user' && message.responseTime != null ? 'bot-message-with-time' : ''}`}
                >
                  {/* Response time badge for bot messages */}
                  {message.sender !== 'user' && message.responseTime !== null && message.responseTime !== undefined && (
                    <div className="response-time-badge" title="Response time">
                      <Clock size={12} className="inline mr-1" />
                      {formatTime(message.responseTime)}
                    </div>
                  )}
                  <div
                    className={`whitespace-pre-line ${
                      message.sender === 'user' ? 'text-red-600' : 'text-black'
                    }`}
                  >
                    {typeof message.text === 'object' ? (
                      <div className="half-line-height">
                        <MessageComponents msg={renderBody} citations={renderCitations} />
                      </div>
                    ) : (
                      <MessageComponents msg={renderBody} citations={renderCitations} />
                    )}
                  </div>
                </div>
                {/* Sources footer (re-added 2026-06-16, operator request):
                    the inline [n] popover chip proved unclickable on the
                    embedded widget (portal popover + sandbox/popup quirks).
                    List the source links here instead, as small plain
                    anchors in normal document flow -- a real <a target=_blank>
                    that just navigates, no popover, right-click/copy work. */}
                {message.sender !== 'user' &&
                  renderCitations &&
                  renderCitations.length > 0 && (
                    <div className="mt-1 ml-1 px-4 text-[11px] leading-snug text-gray-500">
                      <span className="font-semibold text-gray-600">Sources</span>
                      <ul className="mt-0.5 space-y-0.5">
                        {renderCitations
                          .filter((c) => c && c.url)
                          .map((c, ci) => (
                            <li key={`src-${index}-${ci}`} className="flex gap-1">
                              <span className="shrink-0 text-gray-400">
                                [{c.n}]
                              </span>
                              <a
                                href={c.url}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="break-all text-blue-600 hover:underline"
                              >
                                {c.url}
                              </a>
                            </li>
                          ))}
                      </ul>
                    </div>
                  )}
                {/* Low-confidence handoff prompt REMOVED (operator request
                    2026-06-08): the auto-injected "This answer may be
                    uncertain / Submit a Ticket / Chat with Librarian" alert
                    is no longer shown under uncertain answers. The refusal
                    answer text itself already points the user to Ask Us, and
                    the operator runs a separate, user-initiated escalation
                    path. To restore, re-add an `Alert` gated on
                    `lowConfidenceHint` here. */}
                {message.sender !== 'user' && index !== 0 && (
                  <MessageRatingComponent message={message} />
                )}
              </div>
            );
          })}
          {messageContextValues.isTyping && (
            <div className="max-w-md px-5 py-3 rounded-md bg-gray-200 relative bot-message-with-time">
              <div className="thinking-timer" title="Time elapsed">
                <Clock size={14} className="inline mr-1 animate-pulse" />
                <span className="font-mono">{formatTime(elapsedTime)}</span>
              </div>
              <p>
                Chatbot is thinking <span className="dots"></span>
              </p>
            </div>
          )}
          {!socketContextValues.isConnected && (
            <div className="max-w-[350px] px-5 py-3 rounded-md bg-gray-200 self-start">
              <p className="text-black">
                Connecting to the chatbot <span className="dots"></span>
              </p>
            </div>
          )}
        </div>
      </div>

      <form onSubmit={handleFormSubmit}>
        <div className="flex gap-3">
          <Input
            value={messageContextValues.inputMessage}
            onChange={(e) => messageContextValues.setInputMessage(e.target.value)}
            placeholder="Type your message..."
            disabled={!socketContextValues.isConnected}
            className="flex-1"
          />
          <Button
            variant="miami"
            type="submit"
            disabled={!socketContextValues.isConnected}
          >
            Send
          </Button>
        </div>
      </form>
      <p className="text-xs pt-2 text-gray-500">
        Chatbot can make mistakes. 
        {askUsStatus.isOpen 
          ? ' Talk to a human librarian during business hours if needed.'
          : askUsStatus.hoursToday 
            ? ` Human chat available ${askUsStatus.hoursToday.open} - ${askUsStatus.hoursToday.close}. Submit a ticket for off-hours help.`
            : ' Submit a ticket for assistance.'}
      </p>
    </>
  );
};

export default ChatBotComponent;
