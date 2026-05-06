import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Badge, Button, Container, Modal } from 'react-bootstrap';
import { fetchPricing } from '../api/client.js';
import ErrorAlert from '../components/ErrorAlert.jsx';
import LoadingState from '../components/LoadingState.jsx';

const fallbackPricing = {
  plans: [
    {
      code: 'free',
      name: 'Free',
      price_label: '$0/month',
      daily_limit: 5,
      monthly_limit: null,
      max_answer_tokens: 400,
      rag_top_k: 3,
      spotify_limit: 5,
      save_history: false,
      favorites: false,
      playlist_style: false,
    },
    {
      code: 'creator',
      name: 'Student / Creator',
      price_label: '$4.99/month',
      daily_limit: null,
      monthly_limit: 200,
      max_answer_tokens: 800,
      rag_top_k: 5,
      spotify_limit: 10,
      save_history: true,
      favorites: true,
      playlist_style: false,
    },
    {
      code: 'pro',
      name: 'Pro',
      price_label: '$8.99/month',
      daily_limit: null,
      monthly_limit: 1000,
      max_answer_tokens: 1200,
      rag_top_k: 8,
      spotify_limit: 15,
      save_history: true,
      favorites: true,
      playlist_style: true,
    },
  ],
  extra_packs: [
    { code: 'extra-50', price_label: '$2.99', question_credits: 50, expires_after_months: 12 },
    { code: 'extra-100', price_label: '$4.99', question_credits: 100, expires_after_months: 12 },
  ],
};

function limitLabel(plan) {
  if (plan.daily_limit) {
    return `${plan.daily_limit} questions/day`;
  }
  return `${plan.monthly_limit} questions/month`;
}

export default function PricingPage() {
  const [notice, setNotice] = useState('');
  const pricingQuery = useQuery({ queryKey: ['pricing'], queryFn: fetchPricing });
  const pricing = pricingQuery.data || fallbackPricing;

  // Pricing is public, but buttons remain placeholders until payment integration is intentionally added.
  const handleComingSoon = (label) => {
    setNotice(`${label} is coming soon. Payments are not connected yet, so this portfolio build keeps billing safe.`);
  };

  return (
    <main className="pricing-page">
      <Container fluid="lg">
        <section className="pricing-hero premium-hero">
          <span className="landing-kicker">Usage-aware product layer</span>
          <h1>Plans For Sonic Exploration</h1>
          <p>
            Start free, then unlock deeper retrieval, longer answers, more Spotify recommendations, saved history, and
            favorites when the project grows into a real product.
          </p>
        </section>

        {pricingQuery.isLoading ? <LoadingState label="Loading pricing..." /> : null}
        <ErrorAlert message={pricingQuery.isError ? 'Pricing is using local fallback data right now.' : ''} />

        <section className="pricing-grid" aria-label="SonicMind plans">
          {pricing.plans.map((plan) => (
            <article className={`plan-card ${plan.code === 'creator' ? 'is-featured' : ''}`} key={plan.code}>
              <div className="plan-card-header">
                <h2>{plan.name}</h2>
                {plan.code === 'creator' ? <Badge bg="light" text="dark">Student fit</Badge> : null}
                {plan.code === 'pro' ? <Badge bg="dark">Portfolio max</Badge> : null}
              </div>
              <strong className="plan-price">{plan.price_label}</strong>
              <ul>
                <li>{limitLabel(plan)}</li>
                <li>Answers up to {plan.max_answer_tokens} tokens</li>
                <li>RAG Top-K {plan.rag_top_k}</li>
                <li>Up to {plan.spotify_limit} Spotify recommendations</li>
                <li>{plan.save_history ? 'Saved chat history' : 'Temporary session history'}</li>
                <li>{plan.favorites ? 'Favorite tracks included' : 'Favorites not included'}</li>
                <li>{plan.playlist_style ? 'Playlist-style recommendations' : 'Standard recommendations'}</li>
              </ul>
              <Button
                type="button"
                variant={plan.code === 'free' ? 'outline-primary' : 'primary'}
                onClick={() => handleComingSoon(plan.name)}
              >
                Coming Soon
              </Button>
            </article>
          ))}
        </section>

        <section className="extra-pack-panel" aria-label="Extra question packs">
          <h2>Pay-As-You-Go Extra Packs</h2>
          <p>Extra questions are used only after your plan quota is gone and expire after 12 months.</p>
          <div className="extra-pack-grid">
            {pricing.extra_packs.map((pack) => (
              <article className="extra-pack" key={pack.code}>
                <strong>{pack.price_label}</strong>
                <span>{pack.question_credits} extra questions</span>
                <Button type="button" variant="outline-primary" onClick={() => handleComingSoon(pack.price_label)}>
                  Coming Soon
                </Button>
              </article>
            ))}
          </div>
        </section>

        <Modal show={Boolean(notice)} onHide={() => setNotice('')} centered>
          <Modal.Header closeButton>
            <Modal.Title>Coming Soon</Modal.Title>
          </Modal.Header>
          <Modal.Body>{notice}</Modal.Body>
          <Modal.Footer>
            <Button type="button" onClick={() => setNotice('')}>
              Got it
            </Button>
          </Modal.Footer>
        </Modal>
      </Container>
    </main>
  );
}
