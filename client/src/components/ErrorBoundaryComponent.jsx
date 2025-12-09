import React, { useState, useEffect } from 'react';
import { AlertTriangle, RefreshCw, MessageCircle } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Alert, AlertTitle, AlertDescription } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Spinner } from '@/components/ui/spinner';

const ErrorBoundaryComponent = ({ children, onLibrarianHelp }) => {
  const [serverStatus, setServerStatus] = useState('checking');
  const [lastHealthCheck, setLastHealthCheck] = useState(null);
  const [errorDetails, setErrorDetails] = useState(null);
  const [retryCount, setRetryCount] = useState(0);

  // Health check function
  const checkServerHealth = async () => {
    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 5000); // 5 second timeout

      const response = await fetch('/health', {
        signal: controller.signal,
        headers: {
          'Cache-Control': 'no-cache',
        },
      });

      clearTimeout(timeoutId);

      if (!response.ok) {
        throw new Error(
          `Server returned ${response.status}: ${response.statusText}`,
        );
      }

      const healthData = await response.json();
      setServerStatus(healthData.status || 'healthy');
      setLastHealthCheck(new Date());
      setErrorDetails(null);
      setRetryCount(0);

      // Check for degraded services
      if (healthData.status === 'degraded') {
        setErrorDetails({
          type: 'degraded',
          message: 'Some services are experiencing issues',
          services: healthData.services,
        });
      }

      return healthData;
    } catch (error) {
      console.error('Health check failed:', error);

      let errorType = 'network';
      let errorMessage = 'Unable to connect to the server';

      if (error.name === 'AbortError') {
        errorType = 'timeout';
        errorMessage = 'Server is taking too long to respond';
      } else if (error.message.includes('404')) {
        errorType = '404';
        errorMessage = 'Service endpoint not found';
      } else if (
        error.message.includes('500') ||
        error.message.includes('502') ||
        error.message.includes('503')
      ) {
        errorType = 'server_error';
        errorMessage = 'Server is experiencing internal issues';
      }

      setServerStatus('unhealthy');
      setErrorDetails({
        type: errorType,
        message: errorMessage,
        fullError: error.message,
      });
      setLastHealthCheck(new Date());
      setRetryCount((prev) => prev + 1);

      return null;
    }
  };

  // Periodic health checks - start with a delay to not block initial render
  useEffect(() => {
    // Initial health check after a short delay to not block UI
    const initialTimeout = setTimeout(() => {
      checkServerHealth();
    }, 2000);

    const interval = setInterval(() => {
      checkServerHealth();
    }, 60000); // Check every 60 seconds (less frequent to reduce load)

    return () => {
      clearTimeout(initialTimeout);
      clearInterval(interval);
    };
  }, []);

  // Note: Toast notifications are handled by the main App.jsx component

  const handleRetryConnection = () => {
    // Try health check first, if it fails multiple times, suggest refresh
    if (retryCount >= 2) {
      // After 2 failed attempts, refresh the page to reset everything
      window.location.reload();
    } else {
      // Simple retry for first few attempts
      setServerStatus('checking');
      checkServerHealth();
    }
  };

  const getStatusColor = () => {
    switch (serverStatus) {
      case 'healthy':
        return 'green';
      case 'degraded':
        return 'yellow';
      case 'unhealthy':
        return 'red';
      case 'checking':
        return 'blue';
      default:
        return 'gray';
    }
  };

  const getErrorIcon = () => {
    if (errorDetails?.type === 'timeout') return <Spinner size="sm" />;
    return <AlertTriangle className="h-4 w-4" />;
  };

  const renderErrorAlert = () => {
    // Only show alerts for actual errors, not during checking
    if (serverStatus === 'healthy' || serverStatus === 'checking') return null;

    return (
      <Alert variant="warning" className="mb-4 rounded-md">
        <AlertTriangle className="h-4 w-4" />
        <div className="flex-1">
          <AlertTitle className="text-sm">Service Notice</AlertTitle>
          <AlertDescription className="text-sm">
            {errorDetails?.message ||
              'Health check failed - but you can still use the chatbot.'}
          </AlertDescription>

          <div className="flex gap-2 mt-2">
            <Button
              size="xs"
              variant="outline"
              onClick={handleRetryConnection}
            >
              <RefreshCw className="h-3 w-3 mr-1" />
              {retryCount >= 2 ? 'Refresh Page' : 'Try Again'}
            </Button>
            <Button
              size="xs"
              variant="outline"
              className="text-green-600 border-green-600 hover:bg-green-600 hover:text-white"
              onClick={onLibrarianHelp}
            >
              <MessageCircle className="h-3 w-3 mr-1" />
              Get Help
            </Button>
          </div>
        </div>
      </Alert>
    );
  };

  const renderStatusBadge = () => {
    if (serverStatus === 'healthy') return null;

    const badgeVariant = {
      checking: 'blue',
      degraded: 'yellow',
      unhealthy: 'red',
    }[serverStatus] || 'default';

    return (
      <div className="fixed top-4 right-4 z-[1000]">
        <Badge variant={badgeVariant} className="px-3 py-1 text-xs flex items-center gap-2">
          {serverStatus === 'checking' && <Spinner size="xs" />}
          {serverStatus.toUpperCase()}
        </Badge>
      </div>
    );
  };

  return (
    <>
      {renderStatusBadge()}

      <div>
        {renderErrorAlert()}

        {/* Render children normally - never block UI */}
        <div>{children}</div>
      </div>
    </>
  );
};

export default ErrorBoundaryComponent;
