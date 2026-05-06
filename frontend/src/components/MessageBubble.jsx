export default function MessageBubble({ role, content, certainty }) {
  // Role-derived classes keep message alignment and bubble colors declarative.
  const isUser = role === 'user';

  return (
    <article className={`message-row ${isUser ? 'message-row-user' : 'message-row-assistant'}`}>
      <div className={`message-bubble ${isUser ? 'bubble-user' : 'bubble-assistant'}`}>
        {!isUser && certainty ? <div className="certainty-label">{certainty}</div> : null}
        <p>{content}</p>
      </div>
    </article>
  );
}
