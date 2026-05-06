import { Link } from 'react-router-dom';
import { Button, Container } from 'react-bootstrap';
import { useAuthStore } from '../store/authStore.js';

const featureCards = [
  {
    title: 'Grounded Music Answers',
    body: 'RAG retrieval keeps genre, scene, label, and artist answers tied to SonicMind evidence.',
  },
  {
    title: 'Spotify-Aware Discovery',
    body: 'Recommendations are shown only for music questions and use backend-only Spotify credentials.',
  },
  {
    title: 'Plan-Based Limits',
    body: 'Free, Creator, and Pro plans demonstrate real product thinking without live billing risk.',
  },
];

export default function LandingPage() {
  const { token } = useAuthStore();

  return (
    <main className="landing-page">
      <Container fluid="lg">
        <section className="landing-hero">
          <div className="landing-kicker">Music RAG archive · React + FastAPI</div>
          <h1>SonicMind</h1>
          <p>
            Ask about electronic music history, scenes, genres, and listening directions, then turn grounded knowledge
            into source-aware Spotify discovery.
          </p>
          <div className="landing-actions">
            <Button as={Link} to={token ? '/chat' : '/login'} size="lg">
              {token ? 'Open Chat' : 'Start Listening'}
            </Button>
            <Button as={Link} to="/pricing" size="lg" variant="outline-light">
              View Pricing
            </Button>
          </div>
        </section>

        <section className="landing-feature-grid" aria-label="SonicMind feature highlights">
          {featureCards.map((feature) => (
            <article className="landing-feature-card" key={feature.title}>
              <span />
              <h2>{feature.title}</h2>
              <p>{feature.body}</p>
            </article>
          ))}
        </section>
      </Container>
    </main>
  );
}
