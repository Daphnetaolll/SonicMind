import { useState } from 'react';

export default function SpotifyEmbed({ cards = [], error, canFavorite = false, onFavorite, isFavoriting = false }) {
  const [fallbackUrl, setFallbackUrl] = useState('');
  const [activeImage, setActiveImage] = useState('');

  const openSpotifyPlayer = (playerUrl) => {
    setFallbackUrl(playerUrl);
    window.location.href = playerUrl;
  };

  // Backend Spotify failures are non-fatal because text answers and sources may still be usable.
  if (error) {
    return <p className="muted-copy">{error}</p>;
  }

  // Hide the player area until the backend finds source-grounded playable matches.
  if (!cards.length) {
    return (
      <p className="muted-copy">
        Spotify cards stay hidden until the backend finds source-grounded playable matches for this question.
      </p>
    );
  }

  return (
    <section
      className={`spotify-list ${activeImage ? 'has-dynamic-bg' : ''}`}
      aria-label="Spotify matches"
      onMouseLeave={() => setActiveImage('')}
    >
      <div
        className="spotify-dynamic-bg"
        style={{ backgroundImage: activeImage ? `url("${activeImage}")` : undefined }}
        aria-hidden="true"
      />
      {cards.map((card) => {
        const cardKey = card.embed_url || card.spotify_url;
        const playerUrl = card.spotify_url || card.embed_url;

        return (
          <div
            className="spotify-item"
            key={cardKey}
            onMouseEnter={() => setActiveImage(card.image_url || '')}
            onFocusCapture={() => setActiveImage(card.image_url || '')}
          >
            <div className="spotify-card-shell">
              <div className="spotify-artwork" aria-hidden="true">
                {card.image_url ? (
                  <img src={card.image_url} alt="" loading="lazy" />
                ) : (
                  <span className="spotify-artwork-fallback">{card.card_type}</span>
                )}
              </div>
              <div className="spotify-copy">
                <strong>{card.title}</strong>
                <span>{card.subtitle}</span>
                {card.metadata?.recommendation_source ? (
                  <small>{card.metadata.recommendation_source.replaceAll('_', ' ')} recommendation</small>
                ) : null}
              </div>
              <div className="spotify-actions">
                <button
                  className="spotify-open-link"
                  type="button"
                  onMouseDown={() => setFallbackUrl(playerUrl)}
                  onClick={() => openSpotifyPlayer(playerUrl)}
                >
                  Play on Spotify
                </button>
                {canFavorite && card.card_type === 'track' ? (
                  <button
                    className="spotify-favorite-button"
                    type="button"
                    onClick={() => onFavorite?.(card)}
                    disabled={isFavoriting}
                  >
                    Favorite
                  </button>
                ) : null}
              </div>
            </div>
            {fallbackUrl === playerUrl ? (
              <p className="spotify-fallback-link">
                If Spotify does not open, copy this player URL:
                <span>{playerUrl}</span>
              </p>
            ) : null}
          </div>
        );
      })}
    </section>
  );
}
