export default function FavoriteList({ favorites, onDelete, isDeleting }) {
  if (!favorites?.enabled) {
    return <p className="muted-copy">Favorites are available on Creator and Pro plans.</p>;
  }

  if (!favorites.items.length) {
    return <p className="muted-copy">Favorite Spotify tracks will appear here.</p>;
  }

  return (
    <section className="saved-list" aria-label="Favorite tracks">
      {favorites.items.map((item) => (
        <article className="favorite-item" key={item.id}>
          {item.album_image ? <img src={item.album_image} alt="" loading="lazy" /> : null}
          <span>
            <strong>{item.track_name}</strong>
            <small>{item.artist_name}</small>
          </span>
          <a href={item.spotify_url} target="_blank" rel="noreferrer">
            Open
          </a>
          <button type="button" onClick={() => onDelete(item.id)} disabled={isDeleting}>
            Remove
          </button>
        </article>
      ))}
    </section>
  );
}
