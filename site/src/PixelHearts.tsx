// A 7x6 pixel heart, drawn as rects so it stays crisp at any size.
const HEART = ['.XX.XX.', 'XXXXXXX', 'XXXXXXX', '.XXXXX.', '..XXX..', '...X...']

function Heart({ className }: { className: string }) {
  return (
    <svg className={`heart ${className}`} viewBox="0 0 7 6" shapeRendering="crispEdges" aria-hidden="true">
      {HEART.flatMap((row, y) => [...row].map((c, x) => (c === 'X' ? <rect key={`${x}-${y}`} x={x} y={y} width="1" height="1" /> : null)))}
    </svg>
  )
}

/** Two hearts rising above Vinnie while it pleads. */
export function PixelHearts() {
  return (
    <div className="hearts" aria-hidden="true">
      <Heart className="h1" />
      <Heart className="h2" />
    </div>
  )
}
