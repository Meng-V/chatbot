import { useContext, useEffect, useState, useCallback } from 'react';
import { ArrowLeft, Clock } from 'lucide-react';
import { toast } from 'sonner';
import HumanLibrarianWidget from './components/HumanLibrarianWidget';
import OfflineTicketWidget from './components/OfflineTicketWidget';
import ChatBotComponent from './components/ChatBotComponent';
import ErrorBoundaryComponent from './components/ErrorBoundaryComponent';
import { SocketContext } from './context/SocketContextProvider';
import FeedbackFormComponent from './components/FeedbackFormComponent';
import useServerHealth from './hooks/useServerHealth';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';

const App = () => {
  const [isOpen, setIsOpen] = useState(true); // Open by default
  const [step, setStep] = useState('initial');
  const { socketContextValues } = useContext(SocketContext);
  const { serverStatus, needsAttention } = useServerHealth();
  
  // Ask Us Chat Service availability state
  const [askUsStatus, setAskUsStatus] = useState({
    isOpen: false,
    message: '',
    hoursToday: null,
    loading: true
  });

  // Fetch Ask Us Chat Service availability
  const checkAskUsAvailability = useCallback(async () => {
    try {
      const response = await fetch('/askus-hours/status');
      if (response.ok) {
        const data = await response.json();
        setAskUsStatus({
          isOpen: data.is_open,
          message: data.message || '',
          hoursToday: data.hours_today,
          loading: false
        });
      } else {
        setAskUsStatus(prev => ({ ...prev, loading: false }));
      }
    } catch (error) {
      console.error('Failed to check Ask Us availability:', error);
      setAskUsStatus(prev => ({ ...prev, loading: false }));
    }
  }, []);

  // Check availability on mount and every 5 minutes
  useEffect(() => {
    checkAskUsAvailability();
    const interval = setInterval(checkAskUsAvailability, 5 * 60 * 1000);
    return () => clearInterval(interval);
  }, [checkAskUsAvailability]);

  useEffect(() => {
    if (
      !socketContextValues.isConnected &&
      socketContextValues.attemptedConnection
    ) {
      toast.error('Connection Error', {
        description: askUsStatus.isOpen
          ? 'The Smart Chatbot is currently not available. Please talk to a human librarian during business hours or create a ticket for help.'
          : 'The Smart Chatbot is currently not available. Please create a ticket and we\'ll get back to you.',
        duration: 9000,
      });
    }
  }, [
    socketContextValues.isConnected,
    socketContextValues.attemptedConnection,
    askUsStatus.isOpen,
  ]);

  // Auto-redirect based on server health and business hours
  useEffect(() => {
    if (
      (serverStatus === 'unhealthy' ||
        (!socketContextValues.isConnected &&
          socketContextValues.attemptedConnection)) &&
      isOpen &&
      step === 'services'
    ) {
      if (askUsStatus.isOpen) {
        toast.warning('Service Unavailable', {
          description:
            'The Smart Chatbot is currently unavailable. Redirecting you to a human librarian for assistance.',
          duration: 5000,
        });
        setStep('humanLibrarian');
      } else {
        toast.warning('Service Unavailable', {
          description:
            'The Smart Chatbot is currently unavailable. Please submit a ticket and we\'ll get back to you.',
          duration: 5000,
        });
        setStep('ticket');
      }
    }
  }, [
    serverStatus,
    socketContextValues.isConnected,
    socketContextValues.attemptedConnection,
    isOpen,
    step,
    askUsStatus.isOpen,
  ]);

  // Handler for when user clicks "Talk to Librarian" from error boundary
  const handleLibrarianHelp = () => {
    if (!isOpen) {
      setIsOpen(true);
    }
    
    if (askUsStatus.isOpen) {
      setStep('humanLibrarian');
      toast.info('Connecting to Librarian', {
        description: 'Redirecting you to chat with a human librarian.',
        duration: 3000,
      });
    } else {
      setStep('ticket');
      toast.info('Submit a Ticket', {
        description: 'Human chat is currently offline. Please submit a ticket and we\'ll get back to you.',
        duration: 3000,
      });
    }
  };

  const handleClose = () => {
    setStep('initial');
    setIsOpen(false);
  };

  const isChatbotUnavailable =
    serverStatus === 'unhealthy' ||
    (!socketContextValues.isConnected && socketContextValues.attemptedConnection);

  return (
    <ErrorBoundaryComponent onLibrarianHelp={handleLibrarianHelp}>
      {/* Welcome background */}
      <div className="min-h-screen bg-gray-50 flex items-center justify-center p-4">
        <div
          className={`text-center mb-8 transition-all duration-300 ${
            isOpen ? 'opacity-30' : 'opacity-100 cursor-pointer hover:opacity-80 hover:-translate-y-0.5'
          } ${!isOpen ? 'focus:outline-none focus:ring-4 focus:ring-blue-400/60 focus:scale-[1.02] focus:-translate-y-0.5 focus:bg-blue-500/5' : ''}`}
          onClick={!isOpen ? () => setIsOpen(true) : undefined}
          onKeyDown={!isOpen ? (e) => {
            if (e.key === 'Enter' || e.key === ' ') {
              e.preventDefault();
              setIsOpen(true);
            }
          } : undefined}
          tabIndex={!isOpen ? 0 : -1}
          role={!isOpen ? 'button' : undefined}
          aria-label={!isOpen ? 'Open Smart Chatbot services' : undefined}
        >
          <img
            src='https://libapps.s3.amazonaws.com/accounts/190074/images/0721_STier1_Libraries_HS_186KW_K_Digital.png'
            height={80}
            width={200}
            alt='library logo'
            className="mx-auto mb-5"
          />
          <h2 className="text-2xl font-bold text-gray-700 mb-2">
            Welcome to the Smart Chatbot
          </h2>
          <p className="text-base text-gray-600">
            Get help with research, ask questions, or talk to a librarian
          </p>
          {!isOpen && (
            <p className="text-sm text-blue-500 mt-3 font-semibold">
              Get Started
            </p>
          )}
        </div>
      </div>

      <Dialog open={isOpen} onOpenChange={(open) => !open && handleClose()}>
        <DialogContent className="max-w-[450px] mx-4">
          <DialogHeader className="flex flex-row items-center justify-evenly ps-0">
            <img
              src='https://libapps.s3.amazonaws.com/accounts/190074/images/0721_STier1_Libraries_HS_186KW_K_Digital.png'
              height={50}
              width={120}
              alt='library logo'
            />
            <DialogTitle>Smart Chatbot</DialogTitle>
          </DialogHeader>
          
          <div className="flex justify-between">
            {step !== 'initial' && (
              <Button
                variant="outline"
                size="xs"
                className="ml-[7%] text-miami-red border-miami-red hover:bg-miami-red hover:text-white"
                onClick={() => setStep('initial')}
              >
                <ArrowLeft className="h-3 w-3 mr-1" />
                Back
              </Button>
            )}
            {step === 'services' && <FeedbackFormComponent />}
          </div>
          
          <div className="py-5">
            {step === 'initial' && (
              <div className="flex flex-col gap-3">
                <Button
                  variant="miami"
                  onClick={() => {
                    if (isChatbotUnavailable) {
                      toast.error('Chatbot Unavailable', {
                        description:
                          'The Smart Chatbot is currently unavailable. Please talk to a human librarian during business hours or submit a ticket.',
                        duration: 5000,
                      });
                      if (askUsStatus.isOpen) {
                        setStep('humanLibrarian');
                      } else {
                        setStep('ticket');
                      }
                    } else {
                      setStep('services');
                    }
                  }}
                  disabled={isChatbotUnavailable}
                  className={isChatbotUnavailable ? 'opacity-60' : ''}
                >
                  Library Chatbot{' '}
                  {(needsAttention ||
                    (!socketContextValues.isConnected &&
                      socketContextValues.attemptedConnection)) &&
                    '(Unavailable)'}
                </Button>
                
                {/* Show "Talk to human" only during business hours */}
                {askUsStatus.isOpen ? (
                  <Button variant="secondary" onClick={() => setStep('humanLibrarian')}>
                    Talk to a human librarian
                  </Button>
                ) : (
                  <div className="text-center text-sm text-gray-500 py-2">
                    <Clock className="inline-block w-4 h-4 mr-1" />
                    {askUsStatus.hoursToday ? (
                      <span>Human chat available {askUsStatus.hoursToday.open} - {askUsStatus.hoursToday.close}</span>
                    ) : (
                      <span>Human chat is currently offline</span>
                    )}
                  </div>
                )}
                
                <Button variant="secondary" onClick={() => setStep('ticket')}>
                  Create a ticket for offline help
                </Button>
              </div>
            )}
            {step === 'services' &&
              (serverStatus === 'healthy' && socketContextValues.isConnected ? (
                <ChatBotComponent askUsStatus={askUsStatus} />
              ) : (
                <div className="flex flex-col gap-4 text-center py-6">
                  <p className="text-red-500 font-bold">
                    Smart Chatbot is currently unavailable
                  </p>
                  <p className="text-gray-600 text-sm">
                    We're experiencing technical difficulties. 
                    {askUsStatus.isOpen 
                      ? ' Let us connect you with a human librarian.'
                      : ' Please submit a ticket and we\'ll get back to you.'}
                  </p>
                  {askUsStatus.isOpen ? (
                    <Button
                      variant="default"
                      onClick={() => setStep('humanLibrarian')}
                    >
                      Talk to a Human Librarian
                    </Button>
                  ) : (
                    <Button
                      variant="default"
                      onClick={() => setStep('ticket')}
                    >
                      Submit a Ticket
                    </Button>
                  )}
                </div>
              ))}
            {step === 'humanLibrarian' && <HumanLibrarianWidget />}
            {step === 'ticket' && <OfflineTicketWidget />}
          </div>
          
          {/* Bottom action button during chat - shows human chat or ticket based on availability */}
          {step === 'services' && (
            <Button
              size="sm"
              variant="miami"
              className="fixed bottom-10 right-20 mr-4"
              onClick={() => askUsStatus.isOpen ? setStep('humanLibrarian') : setStep('ticket')}
            >
              {askUsStatus.isOpen ? 'Chat with a human librarian' : 'Submit a ticket'}
            </Button>
          )}
        </DialogContent>
      </Dialog>
    </ErrorBoundaryComponent>
  );
};

export default App;
