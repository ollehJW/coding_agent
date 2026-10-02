import { PlatformReturnLink, PlatformHomeLink } from './PlatformNavigation.jsx';
import { useState } from 'react';
import { Activity, FileText, Coins, UserRound, CodeXml, LogOut } from 'lucide-react';
import './accounts.css';
import AdminDashboard from './AdminDashboard.jsx';

export default function AdminWorkspace({ user, onLogout }) {
  const [view, setView] = useState('operations');
  const menus = [['operations', '운영 관리', Activity], ['prompts', '프롬프트 관리', FileText], ['tokens', '토큰 관리', Coins]];
  return <div className="app-shell admin-workspace">
    <aside className="sidebar">
      <div className="brand"><CodeXml size={32} /><div><strong>WiaCoding</strong><small>ADMIN WORKSPACE</small></div></div>
      <p className="nav-caption">ADMINISTRATION</p>
      <nav aria-label="관리자 메뉴">{menus.map(([key, title, Icon]) => <button key={key} className={view===key?'active':''} aria-current={view===key?'page':undefined} onClick={()=>setView(key)}><Icon size={18} />{title}</button>)}</nav>
      <div className="sidebar-bottom"><div className="lab-profile"><span className="lab-avatar" aria-hidden="true"><UserRound size={20} /></span><div><strong>{user.full_name}</strong><small>관리자</small></div></div><button className="sidebar-logout" onClick={onLogout}><LogOut size={15} />로그아웃</button></div>
    </aside>
    <div className="main-shell"><header className="topbar"><div className="breadcrumb"><PlatformHomeLink/> <span aria-hidden="true">&gt;</span> WiaCoding <span aria-hidden="true">&gt;</span><strong>{menus.find(item=>item[0]===view)[1]}</strong></div><div className="platform-topbar-actions"><span className="admin-badge">관리자</span><PlatformReturnLink/></div></header>
      {<AdminDashboard key={view} mode={view} />}
    </div>
  </div>;
}
