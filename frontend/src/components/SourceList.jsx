import { Accordion, Badge } from 'react-bootstrap';

export default function SourceList({ sources = [], routeSteps = [] }) {
  // Empty copy explains the inspector state before the first successful backend answer.
  if (!sources.length) {
    return (
      <p className="muted-copy">
        Sources will appear here after an answer is generated, including local knowledge-base chunks and trusted web evidence.
      </p>
    );
  }

  return (
    <section className="source-list" aria-label="Answer sources">
      {/* Route badges expose which evidence tiers were used without crowding each source row. */}
      {routeSteps.length ? (
        <div className="route-line">
          {routeSteps.map((step) => (
            <Badge bg="secondary" key={step}>
              {step}
            </Badge>
          ))}
        </div>
      ) : null}

      {/* Accordions keep full retrieved text available while preserving a compact inspector. */}
      <Accordion alwaysOpen flush>
        {sources.map((source, index) => (
          <Accordion.Item eventKey={`${index}`} key={`${source.title}-${index}`}>
            <Accordion.Header>
              <span className="source-heading">
                <strong>{source.title || source.source_name}</strong>
                <span>
                  {source.source_type} · {source.source_name} · score {Number(source.retrieval_score || 0).toFixed(3)}
                </span>
              </span>
            </Accordion.Header>
            <Accordion.Body>
              <p className="source-snippet">{source.snippet}</p>
              <details>
                <summary>Full retrieved text</summary>
                <p>{source.full_text || source.snippet}</p>
              </details>
              <div className="source-meta">
                <span>{source.source_name}</span>
                <span>Trust: {source.trust_level}</span>
                {source.url ? (
                  <a href={source.url} target="_blank" rel="noreferrer">
                    Open source
                  </a>
                ) : null}
              </div>
            </Accordion.Body>
          </Accordion.Item>
        ))}
      </Accordion>
    </section>
  );
}
