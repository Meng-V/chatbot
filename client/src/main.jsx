import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App.jsx';
import './index.css';
import { SocketContextProvider } from './context/SocketContextProvider.jsx';
import { MessageContextProvider } from './context/MessageContextProvider.jsx';
import { Toaster } from '@/components/ui/sonner';
import { TooltipProvider } from '@/components/ui/tooltip';

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
