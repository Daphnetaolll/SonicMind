import { Alert } from 'react-bootstrap';

export default function ErrorAlert({ message }) {
  // Returning null keeps pages from reserving vertical space when there is no active error.
  if (!message) {
    return null;
  }

  return (
    <Alert variant="danger" className="error-alert">
      {message}
    </Alert>
  );
}
