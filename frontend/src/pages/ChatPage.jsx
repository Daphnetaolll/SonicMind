import { useEffect, useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Badge, Button, Col, Container, Form, Modal, Row } from 'react-bootstrap';
import {
  deleteFavorite,
  deleteHistory,
  fetchAccountStatus,
  fetchFavorites,
  fetchHistory,
  getApiError,
  getUsageLimitDetail,
  saveFavorite,
  sendChatMessage,
} from '../api/client.js';
import ChatWindow from '../components/ChatWindow.jsx';
import ErrorAlert from '../components/ErrorAlert.jsx';
import FavoriteList from '../components/FavoriteList.jsx';
import HistoryList from '../components/HistoryList.jsx';
import SourceList from '../components/SourceList.jsx';
import SpotifyEmbed from '../components/SpotifyEmbed.jsx';
import { useAuthStore } from '../store/authStore.js';

// Convert backend turn pairs into renderable chat messages while tagging only the latest answer with certainty.
function flattenTurns(turns, latestResponse) {
  const messages = turns.flatMap((turn, index) => [
    {
      id: `turn-${index}-user`,
      role: 'user',
      content: turn.user,
    },
    {
      id: `turn-${index}-assistant`,
      role: 'assistant',
      content: turn.assistant,
      certainty: latestResponse && index === turns.length - 1 ? latestResponse.certainty : undefined,
    },
  ]);
  return messages;
}

function asHistoryArray(value) {
  // Saved JSON fields may come back null from older records, so restore only list-shaped artifacts.
  return Array.isArray(value) ? value : [];
}

export default function ChatPage() {
  const queryClient = useQueryClient();
  const {
    token,
    chatTurns,
    latestResponse,
    settings,
    setChatTurns,
    setLatestResponse,
    setUser,
    clearConversation,
    updateSettings,
  } = useAuthStore();
  const [question, setQuestion] = useState('');
  const [pendingQuestion, setPendingQuestion] = useState('');
  const [isSourcesOpen, setIsSourcesOpen] = useState(false);
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);
  const [isHistoryOpen, setIsHistoryOpen] = useState(false);
  const [isFavoritesOpen, setIsFavoritesOpen] = useState(false);
  const [activeHistoryId, setActiveHistoryId] = useState('');
  const [limitDetail, setLimitDetail] = useState(null);
  const [comingSoonMessage, setComingSoonMessage] = useState('');

  const accountQuery = useQuery({
    queryKey: ['account-status'],
    queryFn: fetchAccountStatus,
    enabled: Boolean(token),
  });
  const historyQuery = useQuery({
    queryKey: ['history'],
    queryFn: fetchHistory,
    enabled: Boolean(token),
  });
  const favoritesQuery = useQuery({
    queryKey: ['favorites'],
    queryFn: fetchFavorites,
    enabled: Boolean(token),
  });

  useEffect(() => {
    // Sync the persisted topbar user with fresh backend plan data after local plan changes or seed scripts.
    if (accountQuery.data?.user) {
      setUser(accountQuery.data.user);
    }
  }, [accountQuery.data?.user, setUser]);

  // Keep the mutation as the single source for loading/error state around a submitted question.
  const mutation = useMutation({
    mutationFn: sendChatMessage,
    onSuccess: (data) => {
      setLatestResponse(data);
      setChatTurns(data.chat_history);
      setQuestion('');
      setPendingQuestion('');
      setActiveHistoryId('');
      queryClient.invalidateQueries({ queryKey: ['account-status'] });
      queryClient.invalidateQueries({ queryKey: ['history'] });
    },
    onError: (error) => {
      setPendingQuestion('');
      const detail = getUsageLimitDetail(error);
      if (detail) {
        setLimitDetail(detail);
      }
    },
  });

  const clearHistoryMutation = useMutation({
    mutationFn: deleteHistory,
    onSuccess: () => {
      setActiveHistoryId('');
      queryClient.invalidateQueries({ queryKey: ['history'] });
    },
  });

  const favoriteMutation = useMutation({
    mutationFn: saveFavorite,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['favorites'] }),
  });

  const deleteFavoriteMutation = useMutation({
    mutationFn: deleteFavorite,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['favorites'] }),
  });

  // Include the pending question optimistically so users see their submission while retrieval runs.
  const messages = useMemo(() => {
    const flattened = flattenTurns(chatTurns, latestResponse);
    if (mutation.isPending && pendingQuestion) {
      flattened.push({
        id: 'pending-user-question',
        role: 'user',
        content: pendingQuestion,
      });
    }
    return flattened;
  }, [chatTurns, latestResponse, mutation.isPending, pendingQuestion]);

  // Submit trimmed text and pass retrieval settings through the API contract expected by FastAPI.
  const handleSubmit = (event) => {
    event.preventDefault();
    if (!question.trim()) {
      return;
    }

    const trimmedQuestion = question.trim();
    setPendingQuestion(trimmedQuestion);
    mutation.mutate({
      question: trimmedQuestion,
      chat_history: chatTurns,
      topk: usage?.features?.rag_top_k || settings.topk,
      max_history_turns: settings.maxHistoryTurns,
    });
  };

  // Clear both the transcript and the inspector details so stale sources do not linger.
  const handleClear = () => {
    clearConversation();
    setLatestResponse(null);
    setActiveHistoryId('');
  };

  const handleRestoreHistory = (item) => {
    // Rehydrate a saved answer into the same state shape that a fresh chat response uses.
    setActiveHistoryId(item.id);
    setPendingQuestion('');
    setQuestion('');
    setChatTurns([
      {
        user: item.question,
        assistant: item.answer,
      },
    ]);
    setLatestResponse({
      question: item.question,
      answer: item.answer,
      sources: asHistoryArray(item.sources_json),
      route_steps: [],
      spotify_cards: asHistoryArray(item.spotify_results_json),
      spotify_error: null,
    });
  };

  const responseUsage = latestResponse?.current_plan
    ? {
        current_plan: latestResponse.current_plan,
        current_plan_name: latestResponse.current_plan_name,
        remaining_questions: latestResponse.remaining_questions,
        remaining_daily_questions: latestResponse.remaining_daily_questions,
        remaining_monthly_questions: latestResponse.remaining_monthly_questions,
        extra_question_credits: latestResponse.extra_question_credits,
        features: latestResponse.plan_features,
      }
    : null;
  const usage = accountQuery.data?.usage || responseUsage;
  const favoritesEnabled = Boolean(usage?.features?.favorites);

  const handleFavorite = (card) => {
    // Store only browser-safe Spotify card fields; secrets never leave the backend.
    favoriteMutation.mutate({
      spotify_track_id: card.spotify_id,
      track_name: card.title,
      artist_name: card.metadata?.recommendation_artist || card.subtitle.split(' - ')[0] || card.subtitle,
      spotify_url: card.spotify_url,
      album_image: card.image_url,
      source_question: latestResponse?.question || '',
    });
  };

  const showComingSoon = (message) => {
    setComingSoonMessage(message || 'Coming Soon: payment integration is not connected in this portfolio build yet.');
  };

  return (
    <main className="chat-page">
      <Container fluid="lg">
        <Row className="g-4">
          <Col lg={8}>
            <ChatWindow
              messages={messages}
              question={question}
              onQuestionChange={setQuestion}
              onSubmit={handleSubmit}
              onClear={handleClear}
              onExampleSelect={setQuestion}
              isLoading={mutation.isPending}
            />
            {latestResponse?.certainty ? (
              <p className="chat-confidence-line">Latest answer confidence: {latestResponse.certainty.toLowerCase()}</p>
            ) : null}
            <ErrorAlert message={mutation.isError ? getApiError(mutation.error, 'The question could not be answered.') : ''} />
          </Col>

          <Col lg={4}>
            <aside className="inspector-panel">
              <section className="status-strip">
                <div>
                  <span>Plan</span>
                  <strong>{usage?.current_plan_name || '—'}</strong>
                </div>
                <div>
                  <span>Remaining</span>
                  <strong>{usage?.remaining_questions ?? '—'}</strong>
                </div>
                <div>
                  <span>Extra</span>
                  <strong>{usage?.extra_question_credits ?? '—'}</strong>
                </div>
              </section>

              <section className="details-panel">
                <h2>Spotify</h2>
                <SpotifyEmbed
                  cards={latestResponse?.spotify_cards || []}
                  error={latestResponse?.spotify_error}
                  canFavorite={favoritesEnabled}
                  onFavorite={handleFavorite}
                  isFavoriting={favoriteMutation.isPending}
                />
                <ErrorAlert message={favoriteMutation.isError ? getApiError(favoriteMutation.error, 'Could not save favorite.') : ''} />
              </section>

              <section className="details-panel collapsible-panel favorites-panel">
                <button
                  className="panel-toggle"
                  type="button"
                  aria-expanded={isFavoritesOpen}
                  onClick={() => setIsFavoritesOpen((current) => !current)}
                >
                  <span>
                    <strong>Favorites</strong>
                    <small>{favoritesQuery.data?.enabled ? `${favoritesQuery.data.items.length} tracks` : 'Creator / Pro'}</small>
                  </span>
                  <span className={`panel-toggle-icon ${isFavoritesOpen ? 'is-open' : ''}`} aria-hidden="true" />
                  <span className="visually-hidden">{isFavoritesOpen ? 'Collapse favorites' : 'Expand favorites'}</span>
                </button>
                {isFavoritesOpen ? (
                  <div className="panel-body">
                    <FavoriteList
                      favorites={favoritesQuery.data}
                      onDelete={(favoriteId) => deleteFavoriteMutation.mutate(favoriteId)}
                      isDeleting={deleteFavoriteMutation.isPending}
                    />
                  </div>
                ) : null}
              </section>

              <section className="details-panel collapsible-panel">
                <button
                  className="panel-toggle"
                  type="button"
                  aria-expanded={isSourcesOpen}
                  onClick={() => setIsSourcesOpen((current) => !current)}
                >
                  <span>
                    <strong>Sources</strong>
                    <small>{latestResponse?.sources?.length || 0} sources</small>
                  </span>
                  <span className={`panel-toggle-icon ${isSourcesOpen ? 'is-open' : ''}`} aria-hidden="true" />
                  <span className="visually-hidden">{isSourcesOpen ? 'Collapse sources' : 'Expand sources'}</span>
                </button>
                {isSourcesOpen ? (
                  <div className="panel-body">
                    <SourceList sources={latestResponse?.sources || []} routeSteps={latestResponse?.route_steps || []} />
                  </div>
                ) : null}
              </section>

              <section className="details-panel collapsible-panel">
                <button
                  className="panel-toggle"
                  type="button"
                  aria-expanded={isHistoryOpen}
                  onClick={() => setIsHistoryOpen((current) => !current)}
                >
                  <span>
                    <strong>Saved History</strong>
                    <small>{historyQuery.data?.enabled ? `${historyQuery.data.items.length} saved` : 'Creator / Pro'}</small>
                  </span>
                  <span className={`panel-toggle-icon ${isHistoryOpen ? 'is-open' : ''}`} aria-hidden="true" />
                  <span className="visually-hidden">{isHistoryOpen ? 'Collapse saved history' : 'Expand saved history'}</span>
                </button>
                {isHistoryOpen ? (
                  <div className="panel-body">
                    <HistoryList
                      history={historyQuery.data}
                      onClear={() => clearHistoryMutation.mutate()}
                      isClearing={clearHistoryMutation.isPending}
                      onRestore={handleRestoreHistory}
                      activeHistoryId={activeHistoryId}
                    />
                  </div>
                ) : null}
              </section>

              <section className="settings-panel collapsible-panel">
                <button
                  className="panel-toggle"
                  type="button"
                  aria-expanded={isSettingsOpen}
                  onClick={() => setIsSettingsOpen((current) => !current)}
                >
                  <span>
                    <strong>Settings</strong>
                    <small>
                      Top-K {usage?.features?.rag_top_k || settings.topk} · {settings.maxHistoryTurns} turns
                    </small>
                  </span>
                  <span className={`panel-toggle-icon ${isSettingsOpen ? 'is-open' : ''}`} aria-hidden="true" />
                  <span className="visually-hidden">{isSettingsOpen ? 'Collapse settings' : 'Expand settings'}</span>
                </button>
                {isSettingsOpen ? (
                  <div className="panel-body">
                    <Form.Group className="mb-3" controlId="topk">
                      <Form.Label>Plan context chunks</Form.Label>
                      <Badge bg="light" text="dark">
                        Top-K {usage?.features?.rag_top_k || settings.topk}
                      </Badge>
                    </Form.Group>
                    <Form.Group controlId="history-turns">
                      <Form.Label>Conversation turns</Form.Label>
                      <Form.Range
                        min={1}
                        max={5}
                        value={settings.maxHistoryTurns}
                        onChange={(event) => updateSettings({ maxHistoryTurns: Number(event.target.value) })}
                      />
                      <Badge bg="light" text="dark">
                        {settings.maxHistoryTurns} turns
                      </Badge>
                    </Form.Group>
                  </div>
                ) : null}
              </section>
            </aside>
          </Col>
        </Row>
      </Container>

      <Modal show={Boolean(limitDetail)} onHide={() => setLimitDetail(null)} centered>
        <Modal.Header closeButton>
          <Modal.Title>Question Limit Reached</Modal.Title>
        </Modal.Header>
        <Modal.Body>
          <p>{limitDetail?.message}</p>
          <p className="muted-copy">Your plan quota is enforced by the backend, so refreshing the page will not reset usage.</p>
        </Modal.Body>
        <Modal.Footer>
          <Button variant="outline-secondary" type="button" onClick={() => setLimitDetail(null)}>
            Close
          </Button>
          <Button type="button" variant="outline-primary" onClick={() => showComingSoon('Coming Soon: extra question packs are placeholders until payments are added.')}>
            Buy Extra Pack
          </Button>
          <Button type="button" variant="primary" onClick={() => showComingSoon('Coming Soon: upgrades will connect to Stripe in a later phase.')}>
            Upgrade
          </Button>
        </Modal.Footer>
      </Modal>

      <Modal show={Boolean(comingSoonMessage)} onHide={() => setComingSoonMessage('')} centered>
        <Modal.Header closeButton>
          <Modal.Title>Coming Soon</Modal.Title>
        </Modal.Header>
        <Modal.Body>{comingSoonMessage}</Modal.Body>
        <Modal.Footer>
          <Button type="button" onClick={() => setComingSoonMessage('')}>
            Got it
          </Button>
        </Modal.Footer>
      </Modal>
    </main>
  );
}
