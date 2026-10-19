import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import { App } from './App';
import { AgentProvider } from './components/agents';
import { ToastProvider } from './components/ui';
import './styles.css';

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <BrowserRouter>
      <ToastProvider>
        <AgentProvider>
          <App key="connected-workspace" />
        </AgentProvider>
      </ToastProvider>
    </BrowserRouter>
  </React.StrictMode>,
);
