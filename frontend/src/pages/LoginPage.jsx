import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useMutation } from '@tanstack/react-query';
import { Button, Container, Form } from 'react-bootstrap';
import { getApiError, login } from '../api/client.js';
import ErrorAlert from '../components/ErrorAlert.jsx';
import LoadingState from '../components/LoadingState.jsx';
import { useAuthStore } from '../store/authStore.js';

export default function LoginPage() {
  const navigate = useNavigate();
  const setAuth = useAuthStore((state) => state.setAuth);
  const [form, setForm] = useState({ email: '', password: '' });

  // Successful login seeds the persisted store before moving into the protected chat route.
  const mutation = useMutation({
    mutationFn: login,
    onSuccess: (data) => {
      setAuth(data);
      navigate('/chat');
    },
  });

  // Backend validation handles credential errors; the form only prevents the browser refresh.
  const handleSubmit = (event) => {
    event.preventDefault();
    mutation.mutate(form);
  };

  return (
    <main className="auth-page">
      <Container className="auth-layout">
        <section className="auth-copy">
          <h1>Welcome Back</h1>
          <p>Sign in to continue your grounded music research session.</p>
        </section>

        <section className="auth-panel" aria-label="Login form">
          <h2>Login</h2>
          <ErrorAlert message={mutation.isError ? getApiError(mutation.error, 'Login failed.') : ''} />
          <Form onSubmit={handleSubmit}>
            <Form.Group className="mb-3" controlId="login-email">
              <Form.Label>Email</Form.Label>
              <Form.Control
                type="email"
                value={form.email}
                onChange={(event) => setForm({ ...form, email: event.target.value })}
                required
              />
            </Form.Group>
            <Form.Group className="mb-3" controlId="login-password">
              <Form.Label>Password</Form.Label>
              <Form.Control
                type="password"
                value={form.password}
                onChange={(event) => setForm({ ...form, password: event.target.value })}
                required
              />
            </Form.Group>
            <Button className="w-100" type="submit" disabled={mutation.isPending}>
              Sign In
            </Button>
          </Form>
          {mutation.isPending ? <LoadingState label="Signing in..." /> : null}
          <p className="auth-switch">
            New here? <Link to="/register">Create an account</Link>
          </p>
        </section>
      </Container>
    </main>
  );
}
