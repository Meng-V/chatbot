import { useContext, useRef, useEffect, useState, useCallback } from 'react';
import { AlertTriangle, Clock } from 'lucide-react';
import MessageComponents from './ParseLinks';
import { SocketContext } from '../context/SocketContextProvider';
import { MessageContext } from '../context/MessageContextProvider';
import MessageRatingComponent from './MessageRatingComponent';
import HumanLibrarianWidget from './HumanLibrarianWidget';
import OfflineTicketWidget from './TicketWidget';
import ClarificationChoices from './ClarificationChoices';
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
  const [showDetailsInput, setShowDetailsInput] = useState(false);
  const [detailsInputValue, setDetailsInputValue] = useState('');
  const [pendingOriginalQuestion, setPendingOriginalQuestion] = useState('');

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

  // Handle clarification choice selection
  const handleClarificationChoice = useCallback((choice, originalQuestion, clarificationData) => {
    if (!socketContextValues.socket) return;
    
    // Start thinking animation
    messageContextValues.startThinking();
    
    // Send choice to backend
    socketContextValues.socket.emit('clarificationChoice', {
      choiceId: choice.id,
      originalQuestion: originalQuestion,
      clarificationData: clarificationData,
      conversationId: socketContextValues.conversationId
    });
  }, [socketContextValues.socket, socketContextValues.conversationId, messageContextValues]);

  // Handle providing more details after "None of the above"
  const handleProvideMoreDetails = useCallback((originalQuestion, additionalDetails) => {
    if (!socketContextValues.socket || !additionalDetails.trim()) return;
    
    // Add user's additional details as a message
    messageContextValues.addMessage(additionalDetails, 'user');
    
    // Start thinking animation
    messageContextValues.startThinking();
    
    // Send to backend
    socketContextValues.socket.emit('provideMoreDetails', {
      originalQuestion: originalQuestion,
      additionalDetails: additionalDetails,
      conversationId: socketContextValues.conversationId
    });
  }, [socketContextValues.socket, socketContextValues.conversationId, messageContextValues]);

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

  // Listen for requestMoreDetails event from backend
  useEffect(() => {
    if (!socketContextValues.socket) return;
    
    const handleRequestMoreDetails = (data) => {
      // Show input for additional details
      setShowDetailsInput(true);
      setPendingOriginalQuestion(data.originalQuestion || '');
      // Add bot's request message
      messageContextValues.addMessage(data.message, 'bot');
      messageContextValues.stopThinking();
    };
    
    socketContextValues.socket.on('requestMoreDetails', handleRequestMoreDetails);
    
    return () => {
      socketContextValues.socket.off('requestMoreDetails', handleRequestMoreDetails);
    };
  }, [socketContextValues.socket, messageContextValues]);

  // Handle submitting additional details
  const handleSubmitDetails = useCallback((e) => {
    e.preventDefault();
    if (detailsInputValue.trim()) {
      handleProvideMoreDetails(pendingOriginalQuestion, detailsInputValue);
      setDetailsInputValue('');
      setShowDetailsInput(false);
      setPendingOriginalQuestion('');
    }
  }, [detailsInputValue, pendingOriginalQuestion, handleProvideMoreDetails]);

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

            // Split out References block if present to render nicer citations
            const parts = adjustedMessage.split(/\nReferences:\n/i);
            const bodyText = parts[0] || '';
            const refsBlock = parts[1] || '';
            const references = refsBlock
              .split('\n')
              .map((l) => l.trim())
              .filter((l) => l.length > 0)
              .slice(0, 5);

            const lowConfidenceHint = /No strong matches found|Institutional knowledge service is temporarily unavailable|ask a clarifying question/i.test(
              adjustedMessage,
            );
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
                        <MessageComponents msg={bodyText} />
                      </div>
                    ) : (
                      <MessageComponents msg={bodyText} />
                    )}
                  </div>
                </div>
                {/* Render nicely formatted citations when available */}
                {message.sender !== 'user' && references.length > 0 && (
                  <div className="max-w-md mt-2 px-4 py-3 border border-gray-300 rounded-md bg-gray-50">
                    <h4 className="text-xs font-semibold mb-2 text-gray-700">
                      Sources
                    </h4>
                    <ul className="list-disc pl-4 space-y-1">
                      {references.map((line, i) => {
                        const urlMatch = line.match(/https?:\/\/\S+/);
                        const url = urlMatch ? urlMatch[0] : undefined;
                        return (
                          <li key={i} className="text-gray-700">
                            {url ? (
                              <a
                                href={url}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="text-blue-600 hover:underline"
                              >
                                {url}
                              </a>
                            ) : (
                              <span>{line}</span>
                            )}
                          </li>
                        );
                      })}
                    </ul>
                  </div>
                )}
                {/* Render clarification choices if present */}
                {message.sender !== 'user' && message.clarificationChoices && (
                  <ClarificationChoices
                    clarificationData={message.clarificationChoices}
                    onChoiceSelect={(choice) => handleClarificationChoice(
                      choice,
                      message.clarificationChoices.original_question,
                      message.clarificationChoices
                    )}
                    disabled={messageContextValues.isTyping}
                  />
                )}
                {/* Suggest human librarian or ticket when confidence appears low */}
                {message.sender !== 'user' && lowConfidenceHint && (
                  <div className="mt-2">
                    <Alert variant="info" className="flex items-center">
                      <AlertTriangle className="h-4 w-4" />
                      <span className="text-sm flex-1">
                        This answer may be uncertain. 
                        {askUsStatus.isOpen 
                          ? ' Talk to a human librarian for faster help.'
                          : ' Submit a ticket during off-hours or check back during business hours.'}
                      </span>
                      {askUsStatus.isOpen ? (
                        <Button
                          size="xs"
                          variant="default"
                          onClick={() => setWidgetVisible(true)}
                        >
                          Chat with Human Librarian
                        </Button>
                      ) : (
                        <Button
                          size="xs"
                          variant="default"
                          onClick={() => setShowTicketForm(true)}
                        >
                          Submit a Ticket
                        </Button>
                      )}
                    </Alert>
                  </div>
                )}
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

      {/* Show additional details input when "None of the above" is selected */}
      {showDetailsInput ? (
        <form onSubmit={handleSubmitDetails}>
          <div className="flex gap-3">
            <Input
              value={detailsInputValue}
              onChange={(e) => setDetailsInputValue(e.target.value)}
              placeholder="Please provide more details about your question..."
              autoFocus
              className="flex-1"
            />
            <Button
              variant="miami"
              type="submit"
              disabled={!detailsInputValue.trim()}
            >
              Send Details
            </Button>
          </div>
        </form>
      ) : (
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
      )}
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
