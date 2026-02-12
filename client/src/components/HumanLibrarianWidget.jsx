import { useState, useContext } from 'react';
import { Copy, Sparkles, ClipboardCheck } from 'lucide-react';
import { MessageContext } from '../context/MessageContextProvider';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import { Spinner } from '@/components/ui/spinner';

/**
 * Functional component that renders a form to collect user info
 */
const UserInfoForm = ({ onFormSubmit, chatHistory }) => {
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [copied, setCopied] = useState(false);
  const [summaryCopied, setSummaryCopied] = useState(false);
  const [generatingSummary, setGeneratingSummary] = useState(false);
  const [previewText, setPreviewText] = useState(null);
  const [copySource, setCopySource] = useState(null);

  // Copy full chat transcript to clipboard
  const handleCopyHistory = async () => {
    const historyText = chatHistory
      .map((msg) => {
        const sender = msg.sender === 'user' ? 'You' : 'Chatbot';
        const text = typeof msg.text === 'object' ? msg.text.response?.join('') || '' : msg.text;
        return `${sender}: ${text}`;
      })
      .join('\n\n');

    try {
      await navigator.clipboard.writeText(historyText);
      setPreviewText(historyText);
      setCopySource('transcript');
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      console.error('Failed to copy to clipboard');
    }
  };

  // Generate AI summary and copy to clipboard
  const handleCopySummary = async () => {
    setGeneratingSummary(true);
    try {
      const historyText = chatHistory
        .map((msg) => {
          const sender = msg.sender === 'user' ? 'User' : 'Chatbot';
          const text = typeof msg.text === 'object' ? msg.text.response?.join('') || '' : msg.text;
          return `${sender}: ${text}`;
        })
        .join('\n\n');

      const isDev = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1';
      const summarizeUrl = isDev ? '/api/summarize-chat' : '/smartchatbot/api/summarize-chat';

      const response = await fetch(summarizeUrl, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ chatHistory: historyText }),
      });

      if (!response.ok) throw new Error(`Server returned ${response.status}`);

      const data = await response.json();
      await navigator.clipboard.writeText(data.summary);
      setPreviewText(data.summary);
      setCopySource('summary');
      setSummaryCopied(true);
      setTimeout(() => setSummaryCopied(false), 2000);
    } catch (error) {
      console.error('Error generating summary:', error);
      alert('Failed to generate summary. Please try Copy Transcript instead.');
    } finally {
      setGeneratingSummary(false);
    }
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    onFormSubmit(name, email);
  };

  const hasChatHistory = chatHistory && chatHistory.length > 0;

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div>
        <Label className="required">Name</Label>
        <Input
          placeholder="Enter your name..."
          value={name}
          onChange={(e) => setName(e.target.value)}
          required
          className="mt-1"
        />
      </div>
      <div>
        <Label className="required">Email</Label>
        <Input
          type="email"
          placeholder="Enter your email..."
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          required
          className="mt-1"
        />
      </div>

      {hasChatHistory && (
        <div className="rounded-md border border-blue-200 bg-blue-50 p-3 text-sm text-gray-700 space-y-2">
          <p className="font-medium text-blue-800">(Optional) Copy your bot conversation before connecting:</p>
          <div className="flex gap-2">
            <Tooltip>
              <TooltipTrigger asChild>
                <Button type="button" size="xs" variant="outline" onClick={handleCopyHistory}>
                  {copied ? <ClipboardCheck className="h-3 w-3 mr-1 text-green-600" /> : <Copy className="h-3 w-3 mr-1" />}
                  {copied ? 'Copied to clipboard!' : 'Copy Transcript'}
                </Button>
              </TooltipTrigger>
              <TooltipContent className="bg-gray-900/80 text-white text-xs">Copy full chat history to clipboard</TooltipContent>
            </Tooltip>
            <Tooltip>
              <TooltipTrigger asChild>
                <Button type="button" size="xs" variant="outline" onClick={handleCopySummary} disabled={generatingSummary}>
                  {generatingSummary ? (
                    <><Spinner className="h-3 w-3 mr-1" />Generating...</>
                  ) : (
                    <>{summaryCopied ? <ClipboardCheck className="h-3 w-3 mr-1 text-green-600" /> : <Sparkles className="h-3 w-3 mr-1" />}
                    {summaryCopied ? 'Copied to clipboard!' : 'AI Summary'}</>
                  )}
                </Button>
              </TooltipTrigger>
              <TooltipContent className="bg-gray-900/80 text-white text-xs">Generate AI summary and copy to clipboard</TooltipContent>
            </Tooltip>
          </div>
          <div className="rounded-md border border-gray-200 bg-gray-100 p-2 max-h-40 overflow-y-auto">
            <p className="text-xs text-gray-500 mb-1 font-medium">
              {copySource === 'transcript' ? '✅ Transcript copied to clipboard:' : copySource === 'summary' ? '✅ AI Summary copied to clipboard:' : 'Preview — click a button above to copy:'}
            </p>
            <pre className="text-xs text-gray-600 whitespace-pre-wrap break-words font-sans">
              {previewText || chatHistory.map((msg) => {
                const sender = msg.sender === 'user' ? 'You' : 'Chatbot';
                const text = typeof msg.text === 'object' ? msg.text.response?.join('') || '' : msg.text;
                return `${sender}: ${text}`;
              }).join('\n\n')}
            </pre>
          </div>
        </div>
      )}

      <Button type="submit" variant="default" className="w-full">
        Start Chat with Librarian
      </Button>
    </form>
  );
};

/**
 * Functional component that renders the LibAnswers chat widget
 */
const HumanLibrarianWidget = () => {
  const { messageContextValues } = useContext(MessageContext);

  const [showForm, setShowForm] = useState(true);
  const [widgetURL, setWidgetURL] = useState('');

  const handleFormSubmit = (name, email) => {
    const baseURL = process.env.TEST_LIBANSWERS_WIDGET_URL;

    if (!baseURL) {
      console.error('TEST_LIBANSWERS_WIDGET_URL is not configured in .env');
      return;
    }

    const params = new URLSearchParams();
    if (name) params.append('patron_name', name);
    if (email) params.append('patron_email', email);

    const queryString = params.toString();
    const finalURL = queryString ? `${baseURL}?${queryString}` : baseURL;
    setWidgetURL(finalURL);
    setShowForm(false);
  };

  return (
    <div>
      {showForm ? (
        <UserInfoForm
          onFormSubmit={handleFormSubmit}
          chatHistory={messageContextValues.message}
        />
      ) : (
        <div>
          <div className="rounded-md border border-amber-200 bg-amber-50 p-3 mb-2 text-sm text-gray-700">
            <p><strong>Say "hi"</strong> to start the chat. Once a librarian joins, <strong>paste</strong> your copied transcript (Ctrl+V / Cmd+V) to share your previous conversation.</p>
          </div>
          <div className="h-[55vh]">
            <iframe
              src={widgetURL}
              title="Chat with a Librarian"
              width="100%"
              height="100%"
              style={{ border: 'none' }}
              allow="microphone; camera"
            />
          </div>
        </div>
      )}
    </div>
  );
};

export default HumanLibrarianWidget;