export function Placeholder({ title, description }: { title: string; description: string }) {
  return (
    <div className="placeholder">
      <h1>{title}</h1>
      <p>{description}</p>
      <p style={{ color: "#6b7280" }}>Coming in a later implementation phase.</p>
    </div>
  );
}
