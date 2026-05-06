import { BrowserRouter, Navigate, NavLink, Route, Routes, useNavigate } from 'react-router-dom';
import { Button, Container, Navbar } from 'react-bootstrap';
import ChatPage from './pages/ChatPage.jsx';
import LandingPage from './pages/LandingPage.jsx';
import LoginPage from './pages/LoginPage.jsx';
import PricingPage from './pages/PricingPage.jsx';
import RegisterPage from './pages/RegisterPage.jsx';
import { useAuthStore } from './store/authStore.js';

// Shell owns app-level navigation chrome so page components can focus on their workflows.
function Shell() {
  const navigate = useNavigate();
  const { token, user, logout } = useAuthStore();

  // Clear persisted auth before redirecting so protected routes re-evaluate immediately.
  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  return (
    <div className="app-shell">
      <Navbar className="topbar" expand="md">
        <Container fluid="lg">
          <Navbar.Brand className="brand-mark" as={NavLink} to="/">
            SonicMind
          </Navbar.Brand>
          <div className="topbar-actions">
            <Button size="sm" variant="outline-light" as={NavLink} to="/pricing">
              Pricing
            </Button>
            {token && user ? (
              <>
                <span className="plan-chip">{user.plan || 'free'}</span>
                <span className="user-chip">{user.email}</span>
                <Button size="sm" variant="outline-light" onClick={handleLogout}>
                  Sign Out
                </Button>
              </>
            ) : (
              <>
                <Button size="sm" variant="outline-light" as={NavLink} to="/login">
                  Login
                </Button>
                <Button size="sm" variant="light" as={NavLink} to="/register">
                  Register
                </Button>
              </>
            )}
          </div>
        </Container>
      </Navbar>

      <Routes>
        <Route path="/" element={<LandingPage />} />
        <Route path="/login" element={<LoginPage />} />
        <Route path="/register" element={<RegisterPage />} />
        <Route path="/pricing" element={<PricingPage />} />
        <Route path="/chat" element={token ? <ChatPage /> : <Navigate to="/login" replace />} />
      </Routes>
    </div>
  );
}

export default function App() {
  // BrowserRouter wraps the full app because route guards depend on shared auth state.
  return (
    <BrowserRouter>
      <Shell />
    </BrowserRouter>
  );
}
