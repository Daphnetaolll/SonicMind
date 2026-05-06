import { Spinner } from 'react-bootstrap';

export default function LoadingState({ label = 'Loading...' }) {
  // role=status announces long-running retrieval/auth work without interrupting the user.
  return (
    <div className="loading-state" role="status" aria-live="polite">
      <Spinner animation="border" size="sm" />
      <span>{label}</span>
    </div>
  );
}
