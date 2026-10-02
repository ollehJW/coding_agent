import { useEffect, useState } from 'react';
import { Loader2 } from 'lucide-react';
import { request } from './api.js';
import { serviceUrl } from './serviceUrl.js';
import './auth.css';


export async function goToPlatformLogin() {
  // The backend reads this origin from config.yaml, including direct legacy-port access.
  const response = await fetch(serviceUrl('/api/platform-auth'), { credentials: 'same-origin' });
  if (!response.ok) throw new Error('통합 로그인 설정을 확인할 수 없습니다.');
  const { platform_origin } = await response.json();
  const origin = new URL(platform_origin);
  const prefix = '/wiacoding';
  const path = window.location.pathname.startsWith(prefix + '/') ? window.location.pathname : prefix + window.location.pathname;
  const destination = path + window.location.search + window.location.hash;
  window.location.replace(origin.origin + '/login?next=' + encodeURIComponent(destination));
}

export default function AuthGate({ children }) {
  const [user, setUser] = useState(null);
  const [notice, setNotice] = useState('');
  useEffect(() => {
    let active = true;
    async function redirect() { try { await goToPlatformLogin(); } catch (e) { if(active) setNotice(e.message); } }
    async function refresh() {
      try {
        const value = await request('/auth/me');
        if (!active) return;
        if (value.must_change_password) { await redirect(); return; }
        setUser(value); setNotice('');
      } catch (e) {
        if (!active) return;
        if (e.status === 401) { setUser(null); await redirect(); }
        else setNotice(e.message);
      }
    }
    function expired() { setUser(null); redirect(); }
    refresh(); window.addEventListener('wiacoding-session-expired', expired); window.addEventListener('focus', refresh);
    return () => { active=false; window.removeEventListener('wiacoding-session-expired', expired); window.removeEventListener('focus', refresh); };
  }, []);
  async function logout() {
    try { await request('/auth/logout', {method:'POST',body:{}}); setUser(null); await goToPlatformLogin(); }
    catch (e) { setNotice(e.message); }
  }
  if (!user) return <div className="auth-page">{notice ? <p role="alert">{notice}</p> : <><Loader2 className="spin" size={32}/><span>통합 로그인 확인 중</span></>}</div>;
  return <>{notice && <div role="alert">{notice}</div>}{children(user, logout)}</>;
}
