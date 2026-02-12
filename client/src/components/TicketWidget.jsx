import { useState, useContext } from 'react';
import { Copy, Sparkles } from 'lucide-react';
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
  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [submitError, setSubmitError] = useState(null);

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

      const isDev = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1';
      const summarizeUrl = isDev ? '/api/summarize-chat' : '/summarize-chat';

      const response = await fetch(summarizeUrl, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ chatHistory: historyText }),
      });

      if (!response.ok) {
        throw new Error(`Server returned ${response.status}`);
      }

      const data = await response.json();
      setQuestion((prev) =>
  `${prev ? `${prev.trim()}\n\n` : ''}=== Content Below is Summarized by AI ===\n${data.summary ?? ''}`
);
    } catch (error) {
      console.error('Error generating summary:', error);
      alert('Failed to generate summary. Please enter your question manually. ERROR: ' + error);
    } finally {
      setGeneratingSummary(false);
    }
  };

  const handleTicketSubmit = async (e) => {
    e.preventDefault();
    if (!question.trim()) {
      setSubmitError('Please enter a question.');
      return;
    }
    setSubmitting(true);
    setSubmitError(null);

    try {
      const isDev = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1';
      const ticketUrl = isDev ? '/api/ticket/create' : '/ticket/create';

      const response = await fetch(ticketUrl, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          question: question.trim().slice(0, 150),
          details: details.trim(),
          name: name.trim(),
          email: email.trim(),
          ua: navigator.userAgent,
        }),
      });

      const data = await response.json();

      if (!response.ok || data.error) {
        throw new Error(data.error || `Server returned ${response.status}`);
      }

      setSubmitted(true);
    } catch (error) {
      console.error('Ticket submission error:', error);
      setSubmitError(error.message || 'Failed to submit ticket. Please try again.');
    } finally {
      setSubmitting(false);
    }
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
      {submitError && (
        <div className="text-sm text-red-600">Failed to submit ticket. Please contact us at{' '}
        <a href="https://www.lib.miamioh.edu/about/organization/contact-us/">https://www.lib.miamioh.edu/about/organization/contact-us/</a>
        <span className="block text-xs text-gray-600 mt-1">Error message: {submitError}</span>
        </div>
      )}
      {submitted ? (
        <div className="rounded-md border border-green-200 bg-green-50 p-3 text-sm text-green-800">
          Your ticket has been submitted successfully. A librarian will follow up via email.
        </div>
      ) : (
        <Button type="submit" variant="miami" className="mt-2" disabled={submitting}>
          {submitting ? <><Spinner className="h-4 w-4 mr-1" />Submitting...</> : 'Submit'}
        </Button>
      )}
    </form>
  );
};

export default TicketWidget;
