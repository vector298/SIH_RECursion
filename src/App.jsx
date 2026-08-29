import { useState, useCallback, useEffect } from 'react';
import { BackendProvider } from './api/BackendContext';
import Backdrop from './components/Backdrop';
import TopNav from './components/TopNav';
import Landing from './pages/Landing';
import Dashboard from './pages/Dashboard';
import Cases from './pages/Cases';
import NewCase from './pages/NewCase';
import MatchIntelligence from './pages/MatchIntelligence';
import Comparison from './pages/Comparison';
import CaseDetail from './pages/CaseDetail';
import Geospatial from './pages/Geospatial';
import Analytics from './pages/Analytics';

export default function App() {
  const [route, setRoute] = useState('landing');
  const [params, setParams] = useState({});

  const go = useCallback((r, p = {}) => {
    setRoute(r);
    setParams(p);
    window.scrollTo({ top: 0, behavior: 'instant' in window ? 'instant' : 'auto' });
  }, []);

  useEffect(() => {
    document.title = route === 'landing'
      ? 'CASE//INTEL — Case Intelligence'
      : `CASE//INTEL — ${route.charAt(0).toUpperCase() + route.slice(1)}`;
  }, [route]);

  if (route === 'landing') {
    return (
      <BackendProvider>
        <Backdrop />
        <Landing go={go} />
      </BackendProvider>
    );
  }

  const pages = {
    dashboard: <Dashboard go={go} />,
    cases: <Cases go={go} />,
    newcase: <NewCase go={go} />,
    match: <MatchIntelligence go={go} params={params} />,
    compare: <Comparison go={go} params={params} />,
    case: <CaseDetail go={go} params={params} />,
    geo: <Geospatial go={go} />,
    analytics: <Analytics go={go} />,
  };

  return (
    <BackendProvider>
      <Backdrop />
      <div className="app">
        <TopNav route={route} go={go} />
        <main key={route + (params.id || '')} className="shell page-enter">
          {pages[route] || pages.dashboard}
        </main>
      </div>
    </BackendProvider>
  );
}
