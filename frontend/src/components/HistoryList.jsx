export default function HistoryList({ history, onClear, isClearing, onRestore, activeHistoryId }) {
  if (!history?.enabled) {
    return <p className="muted-copy">Saved history is available on Creator and Pro plans.</p>;
  }

  if (!history.items.length) {
    return <p className="muted-copy">No saved chats yet. Paid-plan answers will appear here after you ask.</p>;
  }

  return (
    <section className="saved-list" aria-label="Saved chat history">
      <button className="text-action" type="button" onClick={onClear} disabled={isClearing}>
        Clear saved history
      </button>
      {history.items.map((item) => {
        const isActive = item.id === activeHistoryId;
        const spotifyCount = Array.isArray(item.spotify_results_json) ? item.spotify_results_json.length : 0;

        return (
          <article className={`saved-item ${isActive ? 'is-active' : ''}`} key={item.id}>
            <button
              className="saved-item-button"
              type="button"
              onClick={() => onRestore?.(item)}
              aria-expanded={isActive}
              aria-controls={`saved-history-detail-${item.id}`}
            >
              <span className="saved-item-question">{item.question}</span>
              <span className="saved-item-preview">{item.answer}</span>
              <span className="saved-item-meta">
                {spotifyCount ? `${spotifyCount} Spotify ${spotifyCount === 1 ? 'track' : 'tracks'}` : 'No Spotify tracks'}
              </span>
            </button>
            {isActive ? (
              <div className="saved-item-detail" id={`saved-history-detail-${item.id}`}>
                {/* Keep the expanded answer in the history panel while the parent restores chat and Spotify state. */}
                <p>{item.answer}</p>
              </div>
            ) : null}
          </article>
        );
      })}
    </section>
  );
}
