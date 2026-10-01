import React, { useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import App from './App.jsx';
import AuthGate from './Auth.jsx';
import AdminWorkspace from './AdminWorkspace.jsx';
import './styles.css';
import Introduction from './Introduction.jsx';

function Entry() {
  const [inApp, setInApp] = useState(() => window.location.hash === '#app');
  useEffect(() => {
    function navigate() {
      setInApp(window.location.hash === '#app');
      if (window.location.hash === '#app') window.scrollTo(0, 0);
    }
    window.addEventListener('hashchange', navigate);
    return () => window.removeEventListener('hashchange', navigate);
  }, []);
  return inApp ? <AuthGate>{(user, onLogout) => user.is_admin
    ? <AdminWorkspace key={user.user_id} user={user} onLogout={onLogout} />
    : <App key={user.user_id} user={user} onLogout={onLogout} />}</AuthGate> : <Introduction />;
}

createRoot(document.getElementById('root')).render(<React.StrictMode><Entry /></React.StrictMode>);
