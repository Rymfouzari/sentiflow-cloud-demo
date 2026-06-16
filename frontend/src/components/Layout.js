import React, { useState, useEffect } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import {
  BarChart3, Target, Bell, Settings, LogOut,
  Home, LogIn, MessageSquare, LayoutDashboard, Info, Clock, Cpu,
  CreditCard, LifeBuoy,
} from 'lucide-react';
import './Layout.css';

function CollectTimer() {
  const [timeLeft, setTimeLeft] = useState('');
  const [lastCollect, setLastCollect] = useState(null);
  const [paused, setPaused] = useState(false);
  const [interval, setIntervalMin] = useState(15);
  const [pipelineInfo, setPipelineInfo] = useState(null);

    const checkStatus = () => {
    setPaused(true);
    setIntervalMin(15);
    setPipelineInfo(null);
  };

  useEffect(() => {
    checkStatus();
    const statusInterval = window.setInterval(checkStatus, 10000);
    // Ecouter l'event custom pour refresh instantané
    const onRefresh = () => checkStatus();
    window.addEventListener('sentiflow:refresh-timer', onRefresh);
    return () => {
      window.clearInterval(statusInterval);
      window.removeEventListener('sentiflow:refresh-timer', onRefresh);
    };
  }, []);

  useEffect(() => {
    if (paused) { setTimeLeft(''); return; }
    const update = () => {
      const now = new Date();
      const totalSec = now.getMinutes() * 60 + now.getSeconds();
      const intervalSec = interval * 60;
      const elapsed = totalSec % intervalSec;
      const remaining = intervalSec - elapsed;
      const min = Math.floor(remaining / 60);
      const sec = remaining % 60;
      setTimeLeft(`${min}:${sec.toString().padStart(2, '0')}`);

      if (remaining <= 1 && !lastCollect) {
        setLastCollect('Tweets collectes et analyses');
        setTimeout(() => setLastCollect(null), 15000);
      }
    };
    update();
    const timer = window.setInterval(update, 1000);
    return () => window.clearInterval(timer);
  }, [paused, interval, lastCollect]);

  return (
    <div>
      {!paused && (
        <div className="collect-timer">
          <Clock size={12} />
          <span>Collecte dans <strong>{timeLeft}</strong></span>
        </div>
      )}
      {pipelineInfo && pipelineInfo.next_train_in && (
        <div className="collect-timer" style={{ marginTop: 4 }}>
          <Cpu size={12} />
          <span>Training dans <strong>{pipelineInfo.next_train_in}</strong></span>
        </div>
      )}
      {pipelineInfo && pipelineInfo.last_result && (
        <div className="collect-notif" style={{
          marginTop: 4,
          background: pipelineInfo.last_result.replaced ? 'rgba(52,211,153,0.08)' : 'rgba(251,191,36,0.08)',
          borderColor: pipelineInfo.last_result.replaced ? 'rgba(52,211,153,0.15)' : 'rgba(251,191,36,0.15)',
          color: pipelineInfo.last_result.replaced ? '#34d399' : '#fbbf24',
        }}>
          TinyGPT: {pipelineInfo.last_result.replaced ? 'Nouveau modele actif' : 'Modele inchange'}
          {' '}({(pipelineInfo.last_result.new_score * 100).toFixed(0)}%)
        </div>
      )}
      {lastCollect && (
        <div className="collect-notif">
          {lastCollect}
        </div>
      )}
    </div>
  );
}

export default function Layout({ children }) {
  const { user, logout } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  const features = user?.features || {};
  const navItems = user
    ? [
        { path: '/', icon: <Home size={18} />, label: 'Accueil' },
        { path: '/assistant', icon: <MessageSquare size={18} />, label: 'Assistant IA' },
        ...(features.interactive_dashboard ? [{ path: '/dashboard', icon: <BarChart3 size={18} />, label: 'Dashboard' }] : []),
        { path: '/dashboards/generated', icon: <LayoutDashboard size={18} />, label: 'Mes rapports IA' },
        { path: '/cibles', icon: <Target size={18} />, label: 'Cibles' },
        ...(features.alerts ? [{ path: '/alertes', icon: <Bell size={18} />, label: 'Alertes' }] : []),
        { path: '/pricing', icon: <CreditCard size={18} />, label: 'Tarifs' },
        { path: '/support', icon: <LifeBuoy size={18} />, label: 'Support' },
        { path: '/about', icon: <Info size={18} />, label: 'A propos' },
        ...(user.is_admin ? [{ path: '/admin', icon: <Settings size={18} />, label: 'Admin' }] : []),
      ]
    : [
        { path: '/', icon: <Home size={18} />, label: 'Accueil' },
        { path: '/about', icon: <Info size={18} />, label: 'A propos' },
        { path: '/login', icon: <LogIn size={18} />, label: 'Connexion' },
      ];

  return (
    <div className="layout">
      <aside className="sidebar">
        <div className="sidebar-header">
          <div className="logo-row">
            <img src="/logo.png" alt="SentiFlow" className="logo-img" />
            <div>
              <h2>SentiFlow</h2>
              <p className="subtitle">Analyse de sentiments</p>
            </div>
          </div>
        </div>
        <nav className="sidebar-nav">
          {navItems.map((item) => (
            <Link
              key={item.path}
              to={item.path}
              className={`nav-item ${location.pathname === item.path ? 'active' : ''}`}
            >
              {item.icon}
              <span>{item.label}</span>
            </Link>
          ))}
        </nav>
        {user && (
          <div className="sidebar-footer">
            <CollectTimer />
            <div className="user-info">
              <div className="user-avatar">{user.username[0].toUpperCase()}</div>
              <div>
                <span className="user-name">{user.username}</span>
                {user.is_admin && <span className="badge">Admin</span>}
                {user.plan && (
                  <span className="badge" style={{
                    marginLeft: 4,
                    background: user.plan === 'premium' ? '#fbbf24' : user.plan === 'standard' ? '#5271ff' : '#3f3f46',
                    color: user.plan === 'premium' ? '#1c1917' : '#fff',
                  }}>
                    {user.plan}
                  </span>
                )}
              </div>
            </div>
            <button onClick={handleLogout} className="logout-btn">
              <LogOut size={16} />
              <span>Deconnexion</span>
            </button>
          </div>
        )}
      </aside>
      <main className="main-content">{children}</main>
    </div>
  );
}
