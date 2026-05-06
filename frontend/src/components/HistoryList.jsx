export default function HistoryList({ history, onClear, isClearing }) {
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
      {history.items.map((item) => (
        <article className="saved-item" key={item.id}>
          <strong>{item.question}</strong>
          <p>{item.answer}</p>
        </article>
      ))}
    </section>
  );
}
