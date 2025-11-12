import { Box, Button, FormControl, FormLabel, Input, Textarea, HStack, VStack, Icon, Tooltip, Spinner, Text } from '@chakra-ui/react';
import { useEffect, useState, useContext } from 'react';
import { MessageContext } from '../context/MessageContextProvider';
import { FiCopy } from 'react-icons/fi';
import { BsStars } from 'react-icons/bs';

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
    <form onSubmit={handleSubmit}>
      <FormControl isRequired>
        <FormLabel>Name</FormLabel>
        <Input
          placeholder='Enter your name...'
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
      </FormControl>
      <FormControl mt={2} isRequired>
        <FormLabel>Email</FormLabel>
        <Input
          type='email'
          placeholder='Enter your email...'
          value={email}
          onChange={(e) => setEmail(e.target.value)}
        />
      </FormControl>
      <FormControl mt={2}>
        <HStack justify='space-between' mb={1}>
          <FormLabel mb={0}>Initial Question (optional)</FormLabel>
          {chatHistory && chatHistory.length > 0 && (
            <HStack spacing={2}>
              {/* <Tooltip label='Copy AI-generated summary of conversation'>
                <Button
                  size='xs'
                  variant='outline'
                  colorScheme='purple'
                  leftIcon={generatingSummary ? <Spinner size='xs' /> : <Icon as={BsStars} />}
                  onClick={handleCopySummary}
                  isDisabled={generatingSummary}
                >
                  {generatingSummary ? 'Generating...' : summaryCopied ? 'Copied!' : 'Copy AI Summary'}
                </Button>
              </Tooltip> */}
              <Tooltip label='Copy full chat history'>
                <Button
                  size='xs'
                  variant='outline'
                  colorScheme='blue'
                  leftIcon={<Icon as={FiCopy} />}
                  onClick={handleCopyHistory}
                >
                  {copied ? 'Copied!' : 'Copy Full History'}
                </Button>
              </Tooltip>
            </HStack>
          )}
        </HStack>
        <Textarea
          placeholder='Enter your question...'
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          rows={4}
        />
      </FormControl>
      <Button type='submit' mt={3} colorScheme='blue' width='full'>
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
        <Box height='60vh' overflowY='auto'>
          <iframe
            src={formURL}
            title='Chat Widget'
            width='100%'
            height='100%'
            style={{ border: 'none' }}
          />
        </Box>
      )}
    </div>
  );
};

export default HumanLibrarianWidget;
