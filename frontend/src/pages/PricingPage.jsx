import { useEffect, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { Badge, Button, Container, Modal } from 'react-bootstrap';
import {
  createCheckoutSession,
  createPortalSession,
  fetchAccountStatus,
  fetchPricing,
  getApiError,
} from '../api/client.js';
import ErrorAlert from '../components/ErrorAlert.jsx';
import LoadingState from '../components/LoadingState.jsx';
import { useAuthStore } from '../store/authStore.js';

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
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { token, user, setUser } = useAuthStore();
  const checkoutState = searchParams.get('checkout');
  const isPaymentProcessing = checkoutState === 'success';
  const pricingQuery = useQuery({ queryKey: ['pricing'], queryFn: fetchPricing });
  const accountQuery = useQuery({
    queryKey: ['account-status'],
    queryFn: fetchAccountStatus,
    enabled: Boolean(token),
    refetchInterval: isPaymentProcessing ? 2000 : false,
  });
  const pricing = pricingQuery.data || fallbackPricing;
  const usage = accountQuery.data?.usage;
  const currentPlan = usage?.current_plan || user?.plan || 'free';
  const paidPlanActive = ['creator', 'pro'].includes(currentPlan);

  useEffect(() => {
    // Refresh persisted account data after Stripe webhooks update backend-owned plan fields.
    if (accountQuery.data?.user) {
      setUser(accountQuery.data.user);
    }
  }, [accountQuery.data?.user, setUser]);

  useEffect(() => {
    // Checkout success only means Stripe accepted the redirect; the webhook still grants access.
    if (checkoutState === 'success') {
      setNotice('Payment received. SonicMind is syncing your plan from Stripe.');
    }
    if (checkoutState === 'canceled') {
      setNotice('Checkout was canceled. Your plan has not changed.');
      setSearchParams({}, { replace: true });
    }
  }, [checkoutState, setSearchParams]);

  useEffect(() => {
    if (isPaymentProcessing && paidPlanActive) {
      setNotice('Your paid plan is active.');
      setSearchParams({}, { replace: true });
    }
  }, [isPaymentProcessing, paidPlanActive, setSearchParams]);

  const checkoutMutation = useMutation({
    mutationFn: createCheckoutSession,
    onSuccess: (data) => {
      window.location.assign(data.url);
    },
  });

  const portalMutation = useMutation({
    mutationFn: createPortalSession,
    onSuccess: (data) => {
      window.location.assign(data.url);
    },
  });

  const handlePlanAction = (plan) => {
    // Logged-out visitors must authenticate before a Stripe session can be attached to their account.
    if (!token) {
      navigate('/login');
      return;
    }
    if (plan.code === 'free') {
      navigate('/chat');
      return;
    }
    if (paidPlanActive && plan.code !== 'free') {
      portalMutation.mutate();
      return;
    }
    checkoutMutation.mutate({ plan_code: plan.code });
  };

  const handleManageBilling = () => {
    if (!token) {
      navigate('/login');
      return;
    }
    portalMutation.mutate();
  };

  const handleExtraPackComingSoon = (label) => {
    setNotice(`${label} extra packs are not connected in this first Stripe subscription version.`);
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
        <ErrorAlert
          message={
            checkoutMutation.isError
              ? getApiError(checkoutMutation.error, 'Could not start checkout.')
              : portalMutation.isError
                ? getApiError(portalMutation.error, 'Could not open billing portal.')
                : ''
          }
        />

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
                disabled={checkoutMutation.isPending || portalMutation.isPending || (plan.code === currentPlan && plan.code === 'free')}
                onClick={() => handlePlanAction(plan)}
              >
                {paidPlanActive && plan.code !== 'free'
                  ? 'Manage Billing'
                  : plan.code === 'free'
                    ? currentPlan === 'free'
                      ? 'Current Plan'
                      : 'Open Chat'
                    : 'Upgrade'}
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
                <Button type="button" variant="outline-primary" onClick={() => handleExtraPackComingSoon(pack.price_label)}>
                  Coming Soon
                </Button>
              </article>
            ))}
          </div>
        </section>

        {paidPlanActive ? (
          <section className="billing-panel" aria-label="Billing management">
            <strong>Billing</strong>
            <span>Manage payment methods, invoices, and cancellation in Stripe.</span>
            <Button
              type="button"
              variant="light"
              disabled={portalMutation.isPending}
              onClick={handleManageBilling}
            >
              Manage Billing
            </Button>
          </section>
        ) : null}

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
