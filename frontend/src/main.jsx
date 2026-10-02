import { serviceUrl } from './serviceUrl.js';
import React, { useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import App from './App.jsx';
import AuthGate from './Auth.jsx';
import AdminWorkspace from './AdminWorkspace.jsx';
import './styles.css';
import Introduction from './Introduction.jsx';

function Entry() {
  const [inApp, setInApp] = useState(() => window.location.pathname === serviceUrl('/agent') || window.location.hash === '#app');
  useEffect(() => {
    function navigate() {
      // Migrate old bookmarks to the canonical service URL.
      if (window.location.hash === '#app') window.history.replaceState(null, '', serviceUrl('/agent') + window.location.search);
      const active = window.location.pathname === serviceUrl('/agent');
      setInApp(active);
      if (active) window.scrollTo(0, 0);
    }
    navigate();
    window.addEventListener('popstate', navigate);
    window.addEventListener('hashchange', navigate);
    return () => { window.removeEventListener('popstate', navigate); window.removeEventListener('hashchange', navigate); };
  }, []);
  return <AuthGate>{(user, onLogout) => !inApp ? <Introduction /> : user.is_admin
    ? <AdminWorkspace key={user.user_id} user={user} onLogout={onLogout} />
    : <App key={user.user_id} user={user} onLogout={onLogout} />}</AuthGate>;
}

createRoot(document.getElementById('root')).render(<React.StrictMode><Entry /></React.StrictMode>);
