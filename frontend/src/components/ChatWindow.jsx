import { useEffect, useRef } from 'react';
import { Button, Form } from 'react-bootstrap';
import MessageBubble from './MessageBubble.jsx';
import LoadingState from './LoadingState.jsx';

export default function ChatWindow({
  messages,
  question,
  onQuestionChange,
  onSubmit,
  onClear,
  onExampleSelect,
  isLoading,
}) {
  const endOfMessagesRef = useRef(null);
  const hasMessages = messages.length > 0;
  // Example prompts seed the composer without auto-submitting so users can edit before asking.
  const examples = [
    'What is house music?',
    'Recommend me energetic techno tracks for a late-night set.',
    'I want something dark, minimal, and hypnotic.',
  ];

  useEffect(() => {
    // Keep the newest turn in view after sends, responses, and loading-state changes.
    endOfMessagesRef.current?.scrollIntoView({
      block: 'end',
      behavior: hasMessages ? 'smooth' : 'auto',
    });
  }, [hasMessages, isLoading, messages.length]);

  return (
    <section className="chat-window" aria-label="SonicMind chat">
      <div className="message-list">
        {/* Render either the saved transcript or the empty prompt launcher in the same scroll region. */}
        {hasMessages ? (
          messages.map((message) => (
            <MessageBubble
              key={message.id}
              role={message.role}
              content={message.content}
              certainty={message.certainty}
            />
          ))
        ) : (
          <div className="empty-state">
            <h1>Ask SonicMind</h1>
            <p>Ask about electronic music, genres, artists, labels, tracks, and related recommendations.</p>
            <div className="example-prompts" aria-label="Example questions">
              {examples.map((example) => (
                <button type="button" key={example} onClick={() => onExampleSelect(example)}>
                  {example}
                </button>
              ))}
            </div>
          </div>
        )}
        {isLoading ? <LoadingState label="Retrieving evidence and composing an answer..." /> : null}
        <div className="message-list-end" ref={endOfMessagesRef} aria-hidden="true" />
      </div>

      {/* Keep the composer outside the scroll list so controls remain reachable during long answers. */}
      <Form className="composer" onSubmit={onSubmit}>
        <Form.Control
          as="textarea"
          rows={2}
          value={question}
          onChange={(event) => onQuestionChange(event.target.value)}
          placeholder="For example: What is house music?"
          aria-label="Question"
          disabled={isLoading}
        />
        <div className="composer-actions">
          <Button variant="outline-secondary" type="button" onClick={onClear} disabled={isLoading || !hasMessages}>
            Clear
          </Button>
          <Button variant="primary" type="submit" disabled={isLoading || !question.trim()}>
            Ask
          </Button>
        </div>
      </Form>
    </section>
  );
}
