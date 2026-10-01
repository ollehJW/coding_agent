import React from 'react';
import { createRoot } from 'react-dom/client';
import App from './App.jsx';
import AuthGate from './Auth.jsx';
import AdminWorkspace from './AdminWorkspace.jsx';
import './styles.css';

createRoot(document.getElementById('root')).render(<React.StrictMode><AuthGate>{(user, onLogout) => user.is_admin ? <AdminWorkspace key={user.user_id} user={user} onLogout={onLogout} /> : <App key={user.user_id} user={user} onLogout={onLogout} />}</AuthGate></React.StrictMode>);
