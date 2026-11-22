import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import { App } from './App';
import { AgentProvider } from './components/agents';
import { ToastProvider } from './components/ui';
import { InterfaceProvider } from './lib/interface-preferences';
import './styles.css';
import './styles/workspace-research.css';
import './styles/sibyl.css';
import './styles/interface.css';
import './styles/dark.css';

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <InterfaceProvider>
      <BrowserRouter>
        <ToastProvider>
          <AgentProvider>
            <App key="connected-workspace" />
          </AgentProvider>
        </ToastProvider>
      </BrowserRouter>
    </InterfaceProvider>
  </React.StrictMode>,
);
