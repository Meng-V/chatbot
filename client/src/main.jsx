import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App.jsx';
import './index.css';
import { SocketContextProvider } from './context/SocketContextProvider.jsx';
import { MessageContextProvider } from './context/MessageContextProvider.jsx';
import { Toaster } from '@/components/ui/sonner';
import { TooltipProvider } from '@/components/ui/tooltip';
import { initSentry } from './observability/sentry.js';

// Fire-and-forget: no-ops without VITE_SENTRY_DSN. Not awaited --
// blocking first paint on a dynamic import is worse UX than the few
// ms before Sentry attaches; init() resolves near-immediately.
initSentry();

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <TooltipProvider>
      <MessageContextProvider>
        <SocketContextProvider>
          <App />
          <Toaster position="bottom-left" richColors />
        </SocketContextProvider>
      </MessageContextProvider>
    </TooltipProvider>
  </React.StrictMode>,
);
