import { useEffect, useState, useContext } from 'react';
import { Copy, Sparkles } from 'lucide-react';
import { MessageContext } from '../context/MessageContextProvider';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import { Spinner } from '@/components/ui/spinner';

/**
 * Functional component that renders a form to collect user info
 */
const UserInfoForm = ({ onFormSubmit, chatHistory }) => {
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [question, setQuestion] = useState('');
  const [copied, setCopied] = useState(false);
  const [summaryCopied, setSummaryCopied] = useState(false);
  const [generatingSummary, setGeneratingSummary] = useState(false);

  // Handle copy full chat history
  const handleCopyHistory = () => {
    // Format chat history as readable text
    const historyText = chatHistory
      .map((msg) => {
        const sender = msg.sender === 'user' ? 'You' : 'Chatbot';
        const text = typeof msg.text === 'object' ? msg.text.response?.join('') || '' : msg.text;
        return `${sender}: ${text}`;
      })
      .join('\n\n');
    
    const fullQuestion = question ? `${question}\n\n--- Previous Chat History ---\n${historyText}` : historyText;
    setQuestion(fullQuestion);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  // Handle copy AI-generated summary
  const handleCopySummary = async () => {
    setGeneratingSummary(true);
    try {
      // Format chat history for API
      const historyText = chatHistory
        .map((msg) => {
          const sender = msg.sender === 'user' ? 'User' : 'Chatbot';
          const text = typeof msg.text === 'object' ? msg.text.response?.join('') || '' : msg.text;
          return `${sender}: ${text}`;
        })
        .join('\n\n');

      // Call backend API to generate summary
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
      const summary = data.summary;

      // Add summary to question field
      const questionWithSummary = question 
        ? `${question}\n\n--- AI-Generated Chat Summary ---\n${summary}` 
        : summary;
      setQuestion(questionWithSummary);
      setSummaryCopied(true);
      setTimeout(() => setSummaryCopied(false), 2000);
    } catch (error) {
      console.error('Error generating summary:', error);
      alert('Failed to generate summary. Please try copying the full history instead.');
    } finally {
      setGeneratingSummary(false);
    }
  };

  // Handle form submission
  const handleSubmit = (e) => {
    e.preventDefault();
    onFormSubmit(name, email, question);
  };

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
      <div>
        <div className="flex justify-between items-center mb-1">
          <Label>Initial Question (optional)</Label>
          {chatHistory && chatHistory.length > 0 && (
            <div className="flex gap-2">
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button
                    type="button"
                    size="xs"
                    variant="outline"
                    onClick={handleCopyHistory}
                  >
                    <Copy className="h-3 w-3 mr-1" />
                    {copied ? 'Copied!' : 'Copy Full History'}
                  </Button>
                </TooltipTrigger>
                <TooltipContent>Copy full chat history</TooltipContent>
              </Tooltip>
            </div>
          )}
        </div>
        <Textarea
          placeholder="Enter your question..."
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          rows={4}
        />
      </div>
      <Button type="submit" variant="default" className="w-full">
        Start Chat with Librarian
      </Button>
    </form>
  );
};

/**
 * Functional component that renders the LibAnswers chat widget
 * @returns
 */
const HumanLibrarianWidget = () => {
  // Access message context for chat history
  const { messageContextValues } = useContext(MessageContext);
  
  // State to determine whether to show the form or the widget
  const [showForm, setShowForm] = useState(true);
  // User info
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [question, setQuestion] = useState('');
  const [formURL, setFormURL] = useState('');

  // Handle form submission
  const handleFormSubmit = (name, email, question) => {
    setName(name);
    setEmail(email);
    setQuestion(question);
    setShowForm(false); // Hide the form
  };

  useEffect(() => {
    const baseURL = import.meta.env.VITE_LIBANSWERS_WIDGET_URL;
    // Build URL with query parameters
    const params = new URLSearchParams();
    
    if (name) params.append('patron_name', name);
    if (email) params.append('patron_email', email);
    if (question) params.append('question', question);
    
    const queryString = params.toString();
    setFormURL(queryString ? `${baseURL}?${queryString}` : baseURL);
  }, [showForm, name, email, question]);

  return (
    <div>
      {showForm ? (
        <UserInfoForm 
          onFormSubmit={handleFormSubmit} 
          chatHistory={messageContextValues.message}
        />
      ) : (
        <div className="h-[60vh] overflow-y-auto">
          <iframe
            src={formURL}
            title="Chat Widget"
            width="100%"
            height="100%"
            style={{ border: 'none' }}
          />
        </div>
      )}
    </div>
  );
};

export default HumanLibrarianWidget;
