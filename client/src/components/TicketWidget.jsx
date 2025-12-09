import { useState, useContext } from 'react';
import { Copy, Sparkles } from 'lucide-react';
import { SocketContext } from '../context/SocketContextProvider';
import { MessageContext } from '../context/MessageContextProvider';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import { Spinner } from '@/components/ui/spinner';

const TicketWidget = () => {
  const [question, setQuestion] = useState('');
  const [email, setEmail] = useState('');
  const [name, setName] = useState('');
  const [details, setDetails] = useState('');
  const [generatingSummary, setGeneratingSummary] = useState(false);
  const [copied, setCopied] = useState(false);

  const { socketContextValues } = useContext(SocketContext);
  const { messageContextValues } = useContext(MessageContext);
  const chatHistory = messageContextValues.message;

  // Format chat history as readable text
  const formatChatHistory = () => {
    if (!chatHistory || chatHistory.length === 0) return '';
    return chatHistory
      .map((msg) => {
        const sender = msg.sender === 'user' ? 'User' : 'Chatbot';
        const text = typeof msg.text === 'object' ? msg.text.response?.join('') || '' : msg.text;
        return `${sender}: ${text}`;
      })
      .join('\n\n');
  };

  // Handle copy transcript to Details field
  const handleCopyTranscript = () => {
    const transcript = formatChatHistory();
    if (transcript) {
      setDetails((prev) =>
        `${prev ? `${prev.trim()}\n\n` : ''}--- Chat Transcript ---\n${transcript}`
      );
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  // Handle AI Summary generation for Question field
  const handleAISummary = async () => {
    if (!chatHistory || chatHistory.length === 0) {
      alert('No chat history available to summarize.');
      return;
    }

    setGeneratingSummary(true);
    try {
      const historyText = formatChatHistory();

      const response = await fetch('/api/summarize-chat', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ chatHistory: historyText }),
      });

      if (!response.ok) {
        throw new Error('Failed to generate summary');
      }

      const data = await response.json();
      setQuestion((prev) =>
  `${prev ? `${prev.trim()}\n\n` : ''}=== Content Below is Summarized by AI ===\n${data.summary ?? ''}`
);
    } catch (error) {
      console.error('Error generating summary:', error);
      alert('Failed to generate summary. Please enter your question manually.');
    } finally {
      setGeneratingSummary(false);
    }
  };

  const handleTicketSubmit = (e) => {
    e.preventDefault();
    const formData = new FormData();
    formData.append('question', question);
    formData.append('email', email);
    formData.append('name', name);
    formData.append('details', details);
    formData.append('ua', navigator.userAgent);
    socketContextValues.offlineTicketSubmit(formData);
  };

  return (
    <form onSubmit={handleTicketSubmit} className="space-y-4">
      <div>
        <Label>Name</Label>
        <Input
          placeholder="Enter your name..."
          value={name}
          onChange={(e) => setName(e.target.value)}
          className="mt-1"
        />
      </div>
      <div>
        <div className="flex justify-between items-center mb-1">
          <Label>Question</Label>
          {chatHistory && chatHistory.length > 0 && (
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  type="button"
                  size="xs"
                  variant="outline"
                  onClick={handleAISummary}
                  disabled={generatingSummary}
                >
                  {generatingSummary ? (
                    <>
                      <Spinner className="h-3 w-3 mr-1" />
                      Generating...
                    </>
                  ) : (
                    <>
                      <Sparkles className="h-3 w-3 mr-1" />
                      AI Summary
                    </>
                  )}
                </Button>
              </TooltipTrigger>
              <TooltipContent className="bg-gray-900/80 text-white font-xs">Generate AI summary of chat history</TooltipContent>
            </Tooltip>
          )}
        </div>
        <Textarea
          placeholder="Enter your question..."
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          rows={3}
        />
      </div>
      <div>
        <div className="flex justify-between items-center mb-1">
          <Label>Details</Label>
          {chatHistory && chatHistory.length > 0 && (
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  type="button"
                  size="xs"
                  variant="outline"
                  onClick={handleCopyTranscript}
                >
                  <Copy className="h-3 w-3 mr-1" />
                  {copied ? 'Copied!' : 'Copy Transcript'}
                </Button>
              </TooltipTrigger>
              <TooltipContent className="bg-gray-900/80 text-white font-xs">Copy full chat transcript to details</TooltipContent>
            </Tooltip>
          )}
        </div>
        <Textarea
          placeholder="Enter details about your question..."
          value={details}
          onChange={(e) => setDetails(e.target.value)}
          rows={5}
        />
      </div>
      <div>
        <Label>Email</Label>
        <Input
          placeholder="Enter your email..."
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          className="mt-1"
        />
      </div>
      <Button type="submit" variant="miami" className="mt-2">
        Submit
      </Button>
    </form>
  );
};

export default TicketWidget;
