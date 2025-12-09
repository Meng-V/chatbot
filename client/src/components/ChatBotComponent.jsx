import { useContext, useRef, useEffect, useState } from 'react';
import { AlertTriangle } from 'lucide-react';
import MessageComponents from './ParseLinks';
import { SocketContext } from '../context/SocketContextProvider';
import { MessageContext } from '../context/MessageContextProvider';
import MessageRatingComponent from './MessageRatingComponent';
import HumanLibrarianWidget from './HumanLibrarianWidget';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Alert, AlertTitle, AlertDescription } from '@/components/ui/alert';
import './ChatBotComponent.css';

const ChatBotComponent = () => {
  const { socketContextValues } = useContext(SocketContext);
  const { messageContextValues } = useContext(MessageContext);
  const chatRef = useRef();
  const [widgetVisible, setWidgetVisible] = useState(false);

  const handleFormSubmit = (e) => {
    e.preventDefault();
    if (messageContextValues.inputMessage && socketContextValues.socket) {
      messageContextValues.addMessage(
        messageContextValues.inputMessage,
        'user',
      );
      messageContextValues.setInputMessage('');
      messageContextValues.setIsTyping(true);
      socketContextValues.sendUserMessage(messageContextValues.inputMessage);
    }
  };

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
              Please contact a human librarian for immediate assistance.
            </AlertDescription>
          </div>
          <Button
            size="sm"
            variant="default"
            onClick={() => setWidgetVisible(!widgetVisible)}
          >
            {widgetVisible ? 'Hide' : 'Chat with Human Librarian'}
          </Button>
        </Alert>
      )}

      {/* Human Librarian Widget */}
      {widgetVisible && (
        <div className="mb-4 p-4 border border-blue-200 rounded-md bg-blue-50">
          <div className="flex justify-between items-center mb-2">
            <span className="font-bold text-blue-700">
              Chat with a Human Librarian
            </span>
            <Button size="xs" variant="ghost" onClick={() => setWidgetVisible(false)}>
              ✕
            </Button>
          </div>
          <HumanLibrarianWidget />
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
                  className={`max-w-md px-5 py-3 rounded-md ${
                    message.sender === 'user'
                      ? 'bg-white border border-red-400'
                      : 'bg-gray-200'
                  }`}
                >
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
                {/* Suggest human librarian when confidence appears low */}
                {message.sender !== 'user' && lowConfidenceHint && (
                  <div className="mt-2">
                    <Alert variant="info" className="flex items-center">
                      <AlertTriangle className="h-4 w-4" />
                      <span className="text-sm flex-1">
                        This answer may be uncertain. You can chat with a human librarian for faster help.
                      </span>
                      <Button
                        size="xs"
                        variant="default"
                        onClick={() => setWidgetVisible(true)}
                      >
                        Chat with Human Librarian
                      </Button>
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
            <div className="max-w-md px-5 py-3 rounded-md bg-gray-200">
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
            onChange={(e) =>
              messageContextValues.setInputMessage(e.target.value)
            }
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
        Chatbot can make mistakes, please contact librarians if needed.
      </p>
    </>
  );
};

export default ChatBotComponent;
