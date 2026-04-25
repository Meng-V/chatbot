import { createContext, useState, useMemo, useRef } from 'react';

const MessageContext = createContext();

const MessageContextProvider = ({ children }) => {
  const [message, setMessage] = useState([]);
  const [inputMessage, setInputMessage] = useState('');
  const [isTyping, setIsTyping] = useState(false);
  const [thinkingStartTime, setThinkingStartTime] = useState(null);
  // Use ref to avoid stale closure issues when stopThinking is called
  const thinkingStartTimeRef = useRef(null);

  const resetState = () => {
    setMessage([]);
    setInputMessage('');
    setIsTyping(false);
    setThinkingStartTime(null);
    thinkingStartTimeRef.current = null;
  };

  // Start tracking thinking time
  const startThinking = () => {
    const startTime = Date.now();
    setIsTyping(true);
    setThinkingStartTime(startTime);
    thinkingStartTimeRef.current = startTime; // Also store in ref for reliable access
  };

  // Stop thinking and return elapsed time in seconds
  const stopThinking = () => {
    // Use ref to get accurate start time (avoids stale closure)
    const startTime = thinkingStartTimeRef.current;
    const elapsed = startTime ? Math.round((Date.now() - startTime) / 1000) : 0;
    setIsTyping(false);
    setThinkingStartTime(null);
    thinkingStartTimeRef.current = null;
    return elapsed;
  };

  const addMessage = (message, sender, id = undefined, responseTime = null) => {
    const messageText =
      typeof message === 'object' && message.response
        ? message.response.join('\n')
        : typeof message === 'object' && typeof message.answer === 'string'
        ? message.answer
        : message;

    // Pull through the structured-output fields the synthesizer emits when
    // the v2 stack is live: { answer, citations: [{n, url, snippet}], confidence }.
    // Old/legacy responses won't have these -- they stay undefined and the
    // renderer falls back to the existing flat behavior.
    const citations =
      message && typeof message === 'object' && Array.isArray(message.citations)
        ? message.citations
        : undefined;
    const confidence =
      message && typeof message === 'object' && typeof message.confidence === 'string'
        ? message.confidence
        : undefined;

    setMessage((prevMessages) => {
      const updatedMessages = [
        ...prevMessages,
        {
          text: messageText,
          sender,
          messageId: id,
          responseTime: responseTime, // Time in seconds for bot responses
          timestamp: Date.now(),
          citations,
          confidence,
        },
      ];
      sessionStorage.setItem('chat_messages', JSON.stringify(updatedMessages));
      return updatedMessages;
    });
  };

  const updateMessageId = (tempMessageId, realMessageId) => {
    setMessage((prevMessages) => {
      const updatedMessages = prevMessages.map((msg) =>
        msg.messageId === tempMessageId
          ? { ...msg, messageId: realMessageId }
          : msg
      );
      sessionStorage.setItem('chat_messages', JSON.stringify(updatedMessages));
      return updatedMessages;
    });
  };

  const messageContextValues = useMemo(
    () => ({
      message,
      setMessage,
      inputMessage,
      setInputMessage,
      isTyping,
      setIsTyping,
      addMessage,
      updateMessageId,
      resetState,
      thinkingStartTime,
      startThinking,
      stopThinking,
    }),
    [message, inputMessage, isTyping, thinkingStartTime],
  );

  return (
    <MessageContext.Provider value={{ messageContextValues }}>
      {children}
    </MessageContext.Provider>
  );
};

export { MessageContext, MessageContextProvider };
