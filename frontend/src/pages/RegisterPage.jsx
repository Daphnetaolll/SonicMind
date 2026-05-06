import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useMutation } from '@tanstack/react-query';
import { Button, Container, Form } from 'react-bootstrap';
import { getApiError, register } from '../api/client.js';
import ErrorAlert from '../components/ErrorAlert.jsx';
import LoadingState from '../components/LoadingState.jsx';
import { useAuthStore } from '../store/authStore.js';

export default function RegisterPage() {
  const navigate = useNavigate();
  const setAuth = useAuthStore((state) => state.setAuth);
  const [form, setForm] = useState({
    display_name: '',
    email: '',
    password: '',
    confirm_password: '',
  });

  // Registration returns the same auth payload as login so account creation can enter chat immediately.
  const mutation = useMutation({
    mutationFn: register,
    onSuccess: (data) => {
      setAuth(data);
      navigate('/chat');
    },
  });

  // Password matching and length validation live on the backend; the page forwards the form shape directly.
  const handleSubmit = (event) => {
    event.preventDefault();
    mutation.mutate(form);
  };

  return (
    <main className="auth-page">
      <Container className="auth-layout">
        <section className="auth-copy">
          <h1>Create Your Account</h1>
          <p>Start with the free question quota and keep your research context across turns.</p>
        </section>

        <section className="auth-panel" aria-label="Register form">
          <h2>Register</h2>
          <ErrorAlert message={mutation.isError ? getApiError(mutation.error, 'Registration failed.') : ''} />
          <Form onSubmit={handleSubmit}>
            <Form.Group className="mb-3" controlId="register-name">
              <Form.Label>Display name</Form.Label>
              <Form.Control
                value={form.display_name}
                onChange={(event) => setForm({ ...form, display_name: event.target.value })}
              />
            </Form.Group>
            <Form.Group className="mb-3" controlId="register-email">
              <Form.Label>Email</Form.Label>
              <Form.Control
                type="email"
                value={form.email}
                onChange={(event) => setForm({ ...form, email: event.target.value })}
                required
              />
            </Form.Group>
            <Form.Group className="mb-3" controlId="register-password">
              <Form.Label>Password</Form.Label>
              <Form.Control
                type="password"
                value={form.password}
                minLength={8}
                onChange={(event) => setForm({ ...form, password: event.target.value })}
                required
              />
            </Form.Group>
            <Form.Group className="mb-3" controlId="register-confirm-password">
              <Form.Label>Confirm password</Form.Label>
              <Form.Control
                type="password"
                value={form.confirm_password}
                minLength={8}
                onChange={(event) => setForm({ ...form, confirm_password: event.target.value })}
                required
              />
            </Form.Group>
            <Button className="w-100" type="submit" disabled={mutation.isPending}>
              Create Account
            </Button>
          </Form>
          {mutation.isPending ? <LoadingState label="Creating account..." /> : null}
          <p className="auth-switch">
            Already registered? <Link to="/login">Sign in</Link>
          </p>
        </section>
      </Container>
    </main>
  );
}
